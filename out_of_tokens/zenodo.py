"""Deposit idea versions on Zenodo so that each gets a DOI.

Nothing here runs unless a maintainer has set the ZENODO_TOKEN secret; see
MAINTAINERS.md. Each version of an idea becomes one Zenodo record. Zenodo links
the versions of one idea itself and gives the idea a second DOI that always
points at the latest version (the "concept DOI").

A version is never deposited twice. Before anything is created, the account's
existing deposits are searched for one that already names the version's page as
its identical copy. A published match is reused, an unfinished draft is
completed, and only when there is none is a new deposit made.

The token is sent in the Authorization header only. It is never put in a URL,
a message or an exception.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from . import site
from .ideas import (
    CATEGORIES,
    SANDBOX_DOI_PREFIX,
    Idea,
    set_record_fields,
    split_front_matter,
    versions_of,
)

PRODUCTION = "https://zenodo.org/api"
SANDBOX = "https://sandbox.zenodo.org/api"
USER_AGENT = "out-of-tokens-depositor"

# Zenodo's "publication" upload type needs a publication type. "preprint" is
# the closest of its fixed list to a short public write-up that nobody has
# reviewed, and it is the type that scholarly indexes treat as citable text.
UPLOAD_TYPE = "publication"
PUBLICATION_TYPE = "preprint"

# (method, url, headers, body bytes or None) -> (status, parsed JSON or text)
Http = Callable[[str, str, dict, "bytes | None"], "tuple[int, object]"]


class ZenodoError(RuntimeError):
    """A Zenodo call failed. The message holds the call and the reply, never the token."""


def urllib_http(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, object]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as reply:
            status, raw = reply.status, reply.read()
    except urllib.error.HTTPError as exc:
        status, raw = exc.code, exc.read()
    text = raw.decode("utf-8", "replace")
    try:
        return status, json.loads(text) if text else None
    except ValueError:
        return status, text


class Client:
    def __init__(self, token: str, sandbox: bool = False, http: Http | None = None):
        self._token = token
        self._http = http or urllib_http
        self.sandbox = sandbox
        self.api = SANDBOX if sandbox else PRODUCTION

    def _call(self, method: str, url: str, payload=None, raw: bytes | None = None):
        if not url.startswith(self.api + "/"):
            # Follow only links that stay on the chosen Zenodo host, so the
            # token cannot be sent anywhere else.
            raise ZenodoError(f"refusing to call {url.split('?')[0]}: not under {self.api}")
        headers = {"Authorization": f"Bearer {self._token}", "User-Agent": USER_AGENT}
        body = raw
        if raw is not None:
            headers["Content-Type"] = "application/octet-stream"
        elif payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        status, reply = self._http(method, url, headers, body)
        if not 200 <= status < 300:
            detail = json.dumps(reply)[:600] if not isinstance(reply, str) else reply[:600]
            raise ZenodoError(f"{method} {url.split('?')[0]} returned {status}: {detail}")
        return reply

    def list_depositions(self) -> list[dict]:
        """Every deposit of the account, all versions, drafts included."""
        found, page = [], 1
        while True:
            batch = self._call(
                "GET", f"{self.api}/deposit/depositions?all_versions=true&size=100&page={page}"
            )
            if not isinstance(batch, list):
                raise ZenodoError("listing deposits did not return a list")
            found += batch
            if len(batch) < 100:
                return found
            page += 1

    def get(self, url: str) -> dict:
        return self._call("GET", url)

    def create(self, metadata: dict) -> dict:
        return self._call("POST", f"{self.api}/deposit/depositions", {"metadata": metadata})

    def update(self, deposition_id, metadata: dict) -> dict:
        return self._call(
            "PUT", f"{self.api}/deposit/depositions/{deposition_id}", {"metadata": metadata}
        )

    def new_version(self, deposition_id) -> dict:
        """Open a draft for the next version of a published record and return the draft."""
        reply = self._call(
            "POST", f"{self.api}/deposit/depositions/{deposition_id}/actions/newversion"
        )
        return self.get(reply["links"]["latest_draft"])

    def replace_files(self, deposition: dict, files: dict[str, bytes]) -> None:
        base = f"{self.api}/deposit/depositions/{deposition['id']}/files"
        for old in self._call("GET", base) or []:
            self._call("DELETE", f"{base}/{old['id']}")
        for name, data in files.items():
            self._call("PUT", f"{deposition['links']['bucket']}/{name}", raw=data)

    def publish(self, deposition_id) -> dict:
        return self._call(
            "POST", f"{self.api}/deposit/depositions/{deposition_id}/actions/publish"
        )


def build_metadata(idea: Idea, view: site.View, site_url: str) -> dict:
    """The Zenodo metadata for one version of an idea."""
    meta = idea.meta
    page = site.version_url(idea, view.version, site_url)
    creators = []
    for author in meta["authors"]:
        creator = {"name": author["name"]}
        if "orcid" in author:
            creator["orcid"] = author["orcid"]
        creators.append(creator)
    keywords = list(dict.fromkeys([*meta["tags"], CATEGORIES[meta["category"]], "Out of Tokens"]))
    description = (
        f"{site.abstract_html(view)}\n"
        f"<p>This is version {view.version} of idea {idea.id} on Out of Tokens, a public "
        "registry of ideas that their authors could not finish. Anyone may build it. "
        "If you do, please credit the authors. "
        f'Full text and later versions: <a href="{page}">{page}</a></p>'
    )
    return {
        "upload_type": UPLOAD_TYPE,
        "publication_type": PUBLICATION_TYPE,
        "title": view.title,
        "creators": creators,
        "description": description,
        "publication_date": str(view.date),
        "version": f"v{view.version}",
        "access_right": "open",
        "license": "cc-by-4.0",
        "keywords": keywords,
        "related_identifiers": [
            {"identifier": page, "relation": "isIdenticalTo"},
            {"identifier": site_url.rstrip("/") + "/", "relation": "isPartOf"},
        ],
        "notes": f"Out of Tokens {idea.id}v{view.version}. Estimated cost to build: {meta['estimated_cost']}",
    }


def pending(ideas: list[Idea]) -> tuple[list[tuple[Idea, int]], list[str]]:
    """(idea, version) pairs that still need a DOI, in deposit order, and the
    reasons for anything left out on purpose."""
    todo, skipped = [], []
    for idea in ideas:
        if idea.errors or not idea.id:
            continue
        missing = [v["version"] for v in idea.versions if not v.get("doi")]
        if not missing:
            continue
        if idea.meta.get("example"):
            skipped.append(f"{idea.id}: example entry, never deposited")
        elif idea.meta["status"] == "withdrawn":
            skipped.append(f"{idea.id}: withdrawn, no new deposit")
        elif any(v.get("doi") for v in idea.versions[missing[0] :]):
            skipped.append(
                f"{idea.id}: v{missing[0]} has no DOI but a later version has one; "
                "Zenodo cannot insert an earlier version"
            )
        else:
            todo += [(idea, number) for number in missing]
    return todo, skipped


def record_id(doi: str) -> str:
    match = re.search(r"zenodo\.(\d+)$", doi)
    if not match:
        raise ZenodoError(f"{doi} is not a Zenodo DOI, so its record cannot be versioned")
    return match.group(1)


def find_existing(depositions: list[dict], page: str) -> dict | None:
    """The deposit that already stands for the version page ``page``, if any.
    A published one is preferred over a draft."""
    want = page.rstrip("/").lower()
    matches = [
        d
        for d in depositions
        if any(
            str(r.get("identifier", "")).rstrip("/").lower() == want
            and str(r.get("relation", "")).lower() == "isidenticalto"
            for r in (d.get("metadata") or {}).get("related_identifiers") or []
        )
    ]
    matches.sort(key=lambda d: not d.get("submitted"))
    return matches[0] if matches else None


@dataclass
class Deposit:
    doi: str
    concept_doi: str | None
    reused: bool  # True when the record was already on Zenodo


def _result(published: dict, reused: bool) -> Deposit:
    doi = published.get("doi") or (published.get("metadata") or {}).get("doi")
    if not doi:
        raise ZenodoError("Zenodo published the record but returned no DOI")
    concept = published.get("conceptdoi")
    if not concept and published.get("conceptrecid"):
        concept = f"{doi.rsplit('.', 1)[0]}.{published['conceptrecid']}"
    return Deposit(doi, concept, reused)


def deposit_version(
    client: Client,
    idea: Idea,
    view: site.View,
    site_url: str,
    existing: list[dict],
    previous_doi: str | None,
    make_files: Callable[[str | None], dict[str, bytes]],
) -> Deposit:
    """Put one version on Zenodo and publish it, unless it is already there.

    ``existing`` is the account's deposit list. ``previous_doi`` is the DOI of
    the version before this one (None for version 1). ``make_files`` gets the
    DOI Zenodo has reserved for the record, so the files can print it.
    """
    page = site.version_url(idea, view.version, site_url)
    metadata = build_metadata(idea, view, site_url)
    found = find_existing(existing, page)
    if found and found.get("submitted"):
        return _result(found, reused=True)
    if found:
        draft = found  # an earlier run stopped half way; finish its draft
        client.update(draft["id"], metadata)
    elif view.version == 1:
        draft = client.create(metadata)
    else:
        if not previous_doi:
            raise ZenodoError(f"{idea.id}v{view.version}: the version before it has no DOI yet")
        draft = client.new_version(record_id(previous_doi))
        client.update(draft["id"], metadata)
    reserved = ((draft.get("metadata") or {}).get("prereserve_doi") or {}).get("doi")
    client.replace_files(draft, make_files(reserved))
    return _result(client.publish(draft["id"]), reused=False)


def apply_dois(text: str, version_dois: dict[int, str], concept_doi: str | None) -> str:
    """Return the idea file ``text`` with the given DOIs written into its front
    matter. A DOI that is already there is kept."""
    meta, _ = split_front_matter(text)
    versions = []
    for entry in versions_of(meta):
        entry = dict(entry)
        if not entry.get("doi") and entry["version"] in version_dois:
            entry["doi"] = version_dois[entry["version"]]
        versions.append(entry)
    return set_record_fields(text, versions, meta.get("doi") or concept_doi)


def is_sandbox_doi(doi: str | None) -> bool:
    return bool(doi) and doi.startswith(SANDBOX_DOI_PREFIX)

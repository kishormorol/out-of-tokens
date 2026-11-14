"""Load and validate idea files.

An idea is a Markdown file at ``ideas/<YYYY>/<id>-<slug>.md`` with YAML front
matter. This module is the single definition of that format: the validator, the
issue converter, the Zenodo depositor and the site builder all go through it.

Versions. The idea file always holds the latest version. The front matter key
``versions`` lists every version with its date; a file without that key has one
version, dated ``submitted``. When an idea is revised, the file as it was is
kept at ``versions/<id>/v<N>.md`` and is never edited again.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

STATUSES = ("open", "being-built", "built", "withdrawn")

# Subject categories. Every idea has exactly one; tags carry the rest.
CATEGORIES = {
    "nlp": "Language and text",
    "vision": "Vision and images",
    "speech": "Speech and audio",
    "health": "Health and medicine",
    "education": "Education",
    "science": "Science and research",
    "dev-tools": "Developer tools",
    "data": "Data and infrastructure",
    "robotics": "Robotics and hardware",
    "finance": "Finance and business",
    "civic": "Civic and public interest",
    "creative": "Creative work and media",
    "other": "Other",
}

WHY_UNFINISHED = (
    "llm-api-cost",
    "gpu-cost",
    "compute-cost",
    "data-cost",
    "hosting-cost",
    "funding",
    "time",
    "team",
    "other",
)

REQUIRED_SECTIONS = ("Problem", "Idea", "Approach", "What's done")

REQUIRED_KEYS = (
    "id",
    "title",
    "authors",
    "submitted",
    "status",
    "category",
    "tags",
    "why_unfinished",
    "estimated_cost",
)
OPTIONAL_KEYS = ("example", "built_from_this", "abstract", "versions", "doi", "withdrawn")

# Fields that make up the attribution record. Once an idea is on the main
# branch these may not change in a pull request without a maintainer override.
FROZEN_KEYS = ("id", "submitted", "authors")

ID_RE = re.compile(r"^OOT-(\d{4,})$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
TAG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")
GITHUB_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
ORCID_RE = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")
URL_RE = re.compile(r"^https?://[^\s<>\"']+$")
PATH_RE = re.compile(r"^ideas/(\d{4})/(OOT-\d{4,})-([^/]+)\.md$")
VERSION_PATH_RE = re.compile(r"^versions/(OOT-\d{4,})/v([1-9]\d*)\.md$")
DOI_RE = re.compile(r"^10\.\d{4,9}/[^\s\"<>]+$")
# sandbox.zenodo.org hands out test DOIs under this prefix. They do not resolve.
SANDBOX_DOI_PREFIX = "10.5072/"
ABSTRACT_MAX = 1500


class FormatError(ValueError):
    """The file is not front matter followed by a body."""


@dataclass
class Idea:
    path: str  # repo-relative, forward slashes
    meta: dict
    body: str
    errors: list[str] = field(default_factory=list)
    # Past versions read from versions/<id>/v<N>.md: {N: (front matter, body)}.
    frozen: dict[int, tuple[dict, str]] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return str(self.meta.get("id", ""))

    @property
    def versions(self) -> list[dict]:
        return versions_of(self.meta)

    @property
    def version(self) -> int:
        """Number of the latest version."""
        return len(self.versions)


def versions_of(meta: dict) -> list[dict]:
    """The version list. A file without 'versions' has one, dated 'submitted'."""
    raw = meta.get("versions")
    if isinstance(raw, list) and raw and all(isinstance(v, dict) for v in raw):
        return raw
    return [{"version": 1, "date": meta.get("submitted")}]


def content_of(meta: dict, body: str) -> tuple[str, str, str]:
    """The part of an idea that a version freezes: title, abstract and body."""
    abstract = meta.get("abstract")
    return (
        str(meta.get("title", "")).strip(),
        " ".join(abstract.split()) if isinstance(abstract, str) else "",
        body.replace("\r\n", "\n").strip(),
    )


def version_path(idea_id: str, number: int) -> str:
    return f"versions/{idea_id}/v{number}.md"


def split_front_matter(text: str) -> tuple[dict, str]:
    """Return (front matter mapping, body). Raises FormatError if malformed."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise FormatError("file must start with a '---' front matter line")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise FormatError("front matter is not closed by a '---' line")
    try:
        meta = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        raise FormatError(f"front matter is not valid YAML: {exc}") from exc
    if not isinstance(meta, dict):
        raise FormatError("front matter must be a YAML mapping")
    return meta, text[end + 5 :]


def orcid_checksum_ok(orcid: str) -> bool:
    """ISO 7064 MOD 11-2 check digit, as ORCID specifies."""
    digits = orcid.replace("-", "")
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    result = (12 - total % 11) % 11
    return digits[-1] == ("X" if result == 10 else str(result))


def _is_str(value, max_len: int) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= max_len and "\n" not in value


def _check_author(author, where: str) -> list[str]:
    if not isinstance(author, dict):
        return [f"{where}: must be a mapping with at least 'name'"]
    errors = []
    unknown = set(author) - {"name", "github", "orcid", "url"}
    if unknown:
        errors.append(f"{where}: unknown keys {sorted(unknown)}")
    if not _is_str(author.get("name"), 100):
        errors.append(f"{where}: 'name' is required (one line, at most 100 characters)")
    github = author.get("github")
    if github is not None and not (isinstance(github, str) and GITHUB_RE.match(github)):
        errors.append(f"{where}: 'github' must be a GitHub username without '@'")
    orcid = author.get("orcid")
    if orcid is not None:
        if not (isinstance(orcid, str) and ORCID_RE.match(orcid)):
            errors.append(f"{where}: 'orcid' must look like 0000-0002-1825-0097")
        elif not orcid_checksum_ok(orcid):
            errors.append(f"{where}: 'orcid' has a wrong check digit")
    url = author.get("url")
    if url is not None and not (isinstance(url, str) and URL_RE.match(url)):
        errors.append(f"{where}: 'url' must be an http(s) URL")
    return errors


BUILD_STAGES = ("building", "built")


def build_stage(entry: dict) -> str:
    """Entries written before 'stage' existed are finished projects."""
    return entry.get("stage", "built")


def _check_built(entry, where: str) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{where}: must be a mapping with 'name', 'url' and 'by'"]
    errors = []
    unknown = set(entry) - {"name", "url", "by", "date", "stage"}
    if unknown:
        errors.append(f"{where}: unknown keys {sorted(unknown)}")
    if "stage" in entry and entry["stage"] not in BUILD_STAGES:
        errors.append(f"{where}: 'stage' must be 'building' or 'built'")
    if not _is_str(entry.get("name"), 100):
        errors.append(f"{where}: 'name' is required")
    # A project that has only started may have nothing to link to yet.
    url_optional = entry.get("stage") == "building"
    if "url" in entry or not url_optional:
        if not (isinstance(entry.get("url"), str) and URL_RE.match(entry["url"])):
            errors.append(f"{where}: 'url' must be an http(s) URL")
    if not _is_str(entry.get("by"), 100):
        errors.append(f"{where}: 'by' (who built it) is required")
    if "date" in entry and type(entry["date"]) is not dt.date:
        errors.append(f"{where}: 'date' must be YYYY-MM-DD")
    return errors


def _check_doi(value, where: str) -> list[str]:
    if not (isinstance(value, str) and DOI_RE.match(value)):
        return [f"{where} must look like 10.5281/zenodo.1234567"]
    if value.startswith(SANDBOX_DOI_PREFIX):
        return [f"{where} is a Zenodo sandbox DOI; sandbox DOIs are not real and are not recorded"]
    return []


def _check_versions(meta: dict, today: dt.date) -> list[str]:
    raw = meta["versions"]
    if not isinstance(raw, list) or not raw or not all(isinstance(v, dict) for v in raw):
        return ["'versions' must be a non-empty list of mappings with 'version' and 'date'"]
    errors, previous = [], None
    for number, entry in enumerate(raw, 1):
        where = f"versions[{number}]"
        unknown = set(entry) - {"version", "date", "note", "doi"}
        if unknown:
            errors.append(f"{where}: unknown keys {sorted(map(str, unknown))}")
        if type(entry.get("version")) is not int or entry["version"] != number:
            errors.append(f"{where}: 'version' must be {number}; versions count up from 1 in order")
        date = entry.get("date")
        if type(date) is not dt.date:
            errors.append(f"{where}: 'date' must be an unquoted date, YYYY-MM-DD")
        else:
            if date > today + dt.timedelta(days=1):
                errors.append(f"{where}: 'date' ({date}) is in the future")
            if previous and date < previous:
                errors.append(f"{where}: 'date' is earlier than the version before it")
            if number == 1 and type(meta.get("submitted")) is dt.date and date != meta["submitted"]:
                errors.append(f"{where}: the date of version 1 must equal 'submitted'")
            previous = date
        if "note" in entry and not _is_str(entry["note"], 200):
            errors.append(f"{where}: 'note' must be one line of at most 200 characters")
        if number > 1 and "note" not in entry:
            errors.append(f"{where}: 'note' is required from version 2 on; say what changed")
        if "doi" in entry:
            errors += _check_doi(entry["doi"], f"{where}: 'doi'")
    return errors


def _check_withdrawn(meta: dict, today: dt.date) -> list[str]:
    block = meta.get("withdrawn")
    if meta.get("status") != "withdrawn":
        return ["'withdrawn' is only allowed with status 'withdrawn'"] if block is not None else []
    if not isinstance(block, dict):
        return ["status 'withdrawn' needs a 'withdrawn' mapping with 'date' and 'reason'"]
    errors = []
    unknown = set(block) - {"date", "reason"}
    if unknown:
        errors.append(f"withdrawn: unknown keys {sorted(map(str, unknown))}")
    date = block.get("date")
    if type(date) is not dt.date:
        errors.append("withdrawn: 'date' must be an unquoted date, YYYY-MM-DD")
    elif date > today + dt.timedelta(days=1):
        errors.append(f"withdrawn: 'date' ({date}) is in the future")
    elif type(meta.get("submitted")) is dt.date and date < meta["submitted"]:
        errors.append("withdrawn: 'date' is earlier than 'submitted'")
    reason = block.get("reason")
    if not _is_str(reason, 300) or len(reason.strip()) < 10:
        errors.append("withdrawn: 'reason' is required (one line of 10 to 300 characters)")
    return errors


def sections(body: str) -> list[str]:
    """Level-2 headings in the body, ignoring fenced code blocks."""
    found, in_fence = [], False
    for line in body.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            found.append(line[3:].strip())
    return found


def section_text(body: str, name: str) -> str:
    """The text under the level-2 heading ``name``, up to the next one."""
    out, in_fence, inside = [], False, False
    for line in body.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        elif not in_fence and line.startswith("## "):
            if inside:
                break
            inside = line[3:].strip() == name
            continue
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def validate_meta(meta: dict, body: str, today: dt.date | None = None) -> list[str]:
    """Check one idea's front matter and body. Returns a list of problems."""
    today = today or dt.date.today()
    errors = []

    for key in REQUIRED_KEYS:
        if key not in meta:
            errors.append(f"missing required field '{key}'")
    unknown = set(meta) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS)
    if unknown:
        errors.append(f"unknown fields {sorted(map(str, unknown))}")

    if "id" in meta and not (isinstance(meta["id"], str) and ID_RE.match(meta["id"])):
        errors.append("'id' must look like OOT-0001")

    if "title" in meta:
        title = meta["title"]
        if not _is_str(title, 120) or len(title.strip()) < 5:
            errors.append("'title' must be one line of 5 to 120 characters")

    if "authors" in meta:
        authors = meta["authors"]
        if not isinstance(authors, list) or not authors:
            errors.append("'authors' must be a non-empty list")
        else:
            for i, author in enumerate(authors, 1):
                errors += _check_author(author, f"authors[{i}]")

    if "submitted" in meta:
        submitted = meta["submitted"]
        if type(submitted) is not dt.date:
            errors.append("'submitted' must be an unquoted date, YYYY-MM-DD")
        elif submitted > today + dt.timedelta(days=1):
            errors.append(f"'submitted' ({submitted}) is in the future")

    if "status" in meta and meta["status"] not in STATUSES:
        errors.append(f"'status' must be one of {', '.join(STATUSES)}")

    if "category" in meta and not (
        isinstance(meta["category"], str) and meta["category"] in CATEGORIES
    ):
        errors.append(f"'category' must be one of {', '.join(CATEGORIES)}")

    if "abstract" in meta:
        abstract = meta["abstract"]
        if not isinstance(abstract, str) or not 0 < len(abstract.strip()) <= ABSTRACT_MAX:
            errors.append(f"'abstract' must be plain text of at most {ABSTRACT_MAX} characters")

    if "versions" in meta:
        errors += _check_versions(meta, today)
    if "doi" in meta:
        errors += _check_doi(meta["doi"], "'doi'")
    errors += _check_withdrawn(meta, today)

    if "tags" in meta:
        tags = meta["tags"]
        if not isinstance(tags, list) or not 1 <= len(tags) <= 8:
            errors.append("'tags' must be a list of 1 to 8 tags")
        else:
            for tag in tags:
                if not (isinstance(tag, str) and TAG_RE.match(tag)):
                    errors.append(
                        f"tag {tag!r} must be lowercase letters, digits and hyphens (max 30)"
                    )
            if len(set(map(str, tags))) != len(tags):
                errors.append("'tags' contains duplicates")

    if "why_unfinished" in meta:
        why = meta["why_unfinished"]
        if not isinstance(why, list) or not why:
            errors.append("'why_unfinished' must be a non-empty list")
        else:
            for reason in why:
                if reason not in WHY_UNFINISHED:
                    errors.append(
                        f"why_unfinished {reason!r} must be one of {', '.join(WHY_UNFINISHED)}"
                    )
            if len(set(map(str, why))) != len(why):
                errors.append("'why_unfinished' contains duplicates")

    if "estimated_cost" in meta and not _is_str(meta["estimated_cost"], 200):
        errors.append("'estimated_cost' must be a quoted one-line string, e.g. \"USD 3,000 in API calls\"")

    if "example" in meta and not isinstance(meta["example"], bool):
        errors.append("'example' must be true or false")

    built = meta.get("built_from_this", [])
    if not isinstance(built, list):
        errors.append("'built_from_this' must be a list")
        built = []
    for i, entry in enumerate(built, 1):
        errors += _check_built(entry, f"built_from_this[{i}]")
    if meta.get("status") == "built" and not any(
        isinstance(b, dict) and build_stage(b) == "built" for b in built
    ):
        errors.append("status 'built' needs at least one finished entry in 'built_from_this'")

    have = sections(body)
    for name in REQUIRED_SECTIONS:
        if name not in have:
            errors.append(f"body is missing the section '## {name}'")

    return errors


def validate_path(path: str, meta: dict) -> list[str]:
    match = PATH_RE.match(path)
    if not match:
        return ["path must be ideas/<YYYY>/<id>-<slug>.md"]
    year, file_id, slug = match.groups()
    errors = []
    if not SLUG_RE.match(slug):
        errors.append("slug in the file name must be lowercase letters, digits and hyphens")
    if isinstance(meta.get("id"), str) and meta["id"] != file_id:
        errors.append(f"file name says {file_id} but front matter says {meta['id']}")
    submitted = meta.get("submitted")
    if type(submitted) is dt.date and str(submitted.year) != year:
        errors.append(f"folder is {year} but 'submitted' is in {submitted.year}")
    return errors


def load_text(path: str, text: str, today: dt.date | None = None) -> Idea:
    try:
        meta, body = split_front_matter(text)
    except FormatError as exc:
        return Idea(path, {}, "", [str(exc)])
    errors = validate_path(path, meta) + validate_meta(meta, body, today)
    return Idea(path, meta, body, errors)


def load_all(root: Path, today: dt.date | None = None) -> list[Idea]:
    """Load every Markdown file under ``root/ideas``, sorted by path.

    Every .md file there is treated as an idea, so a stray file is reported
    instead of silently skipped. Duplicate ids are reported on the later file.
    Frozen past versions are read from ``root/versions`` into ``Idea.frozen``;
    a missing one, or a file there that no idea accounts for, is reported.
    """
    ideas, seen = [], {}
    for file in sorted((root / "ideas").rglob("*.md")):
        rel = file.relative_to(root).as_posix()
        idea = load_text(rel, file.read_text(encoding="utf-8"), today)
        if idea.id and idea.id in seen:
            idea.errors.append(f"id {idea.id} is already used by {seen[idea.id]}")
        elif idea.id:
            seen[idea.id] = rel
        ideas.append(idea)

    expected = set()
    for idea in ideas:
        if not idea.id or idea.id not in seen or seen[idea.id] != idea.path:
            continue
        for number in range(1, idea.version):
            rel = version_path(idea.id, number)
            expected.add(rel)
            file = root / rel
            if not file.is_file():
                idea.errors.append(
                    f"version {number} is missing: {rel} must hold the file as it was at that version"
                )
                continue
            try:
                meta, body = split_front_matter(file.read_text(encoding="utf-8"))
            except FormatError as exc:
                idea.errors.append(f"{rel}: {exc}")
                continue
            if meta.get("id") != idea.id:
                idea.errors.append(f"{rel}: front matter id is {meta.get('id')!r}, expected {idea.id}")
            idea.frozen[number] = (meta, body)
    versions_dir = root / "versions"
    if versions_dir.is_dir():
        for file in sorted(p for p in versions_dir.rglob("*") if p.is_file()):
            rel = file.relative_to(root).as_posix()
            if rel not in expected and file.name != "README.md":
                ideas.append(
                    Idea(rel, {}, "", ["no idea lists this version; versions/<id>/v<N>.md holds past versions only"])
                )
    return ideas


def set_record_fields(text: str, versions: list[dict] | None, doi: str | None) -> str:
    """Rewrite the top-level 'versions' and 'doi' keys of an idea file.

    Every other line of the file is left exactly as the author wrote it. The
    two keys are written in one fixed form at the end of the front matter. The
    result is parsed again and compared, so a file this cannot edit safely
    raises FormatError instead of being damaged.
    """
    text = text.replace("\r\n", "\n")
    meta, body = split_front_matter(text)
    end = text.find("\n---\n", 3)
    kept, skipping = [], False
    for line in text[4:end].split("\n"):
        if line.startswith("#"):
            skipping = False
        elif line and not line[0].isspace() and not line.startswith("-"):
            skipping = re.match(r"(doi|versions)\s*:", line) is not None
        if not skipping:
            kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    if doi:
        kept.append(f"doi: {json.dumps(doi)}")
    if versions:
        kept.append("versions:")
        for entry in versions:
            kept.append(f"  - version: {int(entry['version'])}")
            kept.append(f"    date: {entry['date'].isoformat()}")
            if entry.get("note"):
                kept.append(f"    note: {json.dumps(entry['note'], ensure_ascii=False)}")
            if entry.get("doi"):
                kept.append(f"    doi: {json.dumps(entry['doi'])}")
    result = "---\n" + "\n".join(kept) + "\n---\n" + body

    want = {k: v for k, v in meta.items() if k not in ("doi", "versions")}
    if doi:
        want["doi"] = doi
    if versions:
        want["versions"] = [
            {k: e[k] for k in ("version", "date", "note", "doi") if e.get(k)} for e in versions
        ]
    got, got_body = split_front_matter(result)
    if got != want or got_body != body:
        raise FormatError("could not rewrite 'versions' and 'doi' safely; edit the front matter by hand")
    return result


def next_id(used: list[str]) -> str:
    """The id after the highest one in ``used``. Gaps are never reused."""
    numbers = [int(m.group(1)) for m in map(ID_RE.match, used) if m]
    return f"OOT-{max(numbers, default=0) + 1:04d}"


def frozen_changes(old_meta: dict, new_meta: dict | None) -> list[str]:
    """Problems when a pull request touches an idea's attribution record."""
    if new_meta is None:
        return ["idea was removed; ideas are not deleted once merged"]
    return [
        f"'{key}' changed; the attribution record of a merged idea is frozen"
        for key in FROZEN_KEYS
        if old_meta.get(key) != new_meta.get(key)
    ]


def revision_changes(old_meta: dict, old_body: str, new: Idea, base: str = "main") -> list[str]:
    """Problems with how a pull request changes an idea's versions and content."""
    errors = []
    old_versions, new_versions = versions_of(old_meta), new.versions
    old_n, new_n = len(old_versions), len(new_versions)
    for old, cur in zip(old_versions, new_versions):
        for key in ("version", "date", "note"):
            if old.get(key) != cur.get(key):
                errors.append(f"version {old.get('version')}: '{key}' changed; past versions are frozen")
        if old.get("doi") and old.get("doi") != cur.get("doi"):
            errors.append(f"version {old.get('version')}: 'doi' changed; a DOI is permanent")
    if old_meta.get("doi") and old_meta.get("doi") != new.meta.get("doi"):
        errors.append("'doi' changed; a DOI is permanent")

    if old_meta.get("status") == "withdrawn":
        if new.meta.get("status") != "withdrawn" or old_meta.get("withdrawn") != new.meta.get("withdrawn"):
            errors.append("a withdrawal is permanent; 'status' and 'withdrawn' may not change")
        if new_n > old_n:
            errors.append("a withdrawn idea cannot get a new version")

    old_content, new_content = content_of(old_meta, old_body), content_of(new.meta, new.body)
    if new_n < old_n:
        errors.append("versions were removed; past versions are frozen")
    elif new_n == old_n:
        if new_content != old_content:
            errors.append(
                "title, abstract or body changed without a new version; start one with "
                f"'python -m out_of_tokens revise {new.id} --note \"what changed\"' before editing"
            )
    elif new_n == old_n + 1:
        frozen = new.frozen.get(old_n)
        target = version_path(new.id, old_n)
        if frozen and content_of(*frozen) != old_content:
            errors.append(
                f"{target} must hold version {old_n} as it is on {base}; "
                f"make it with 'git show {base}:{new.path} > {target}'"
            )
        if new_content == old_content:
            errors.append(f"version {new_n} has the same title, abstract and body as version {old_n}")
    else:
        errors.append("a pull request may add one new version at a time")
    return errors


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def check_against_base(root: Path, base: str, ideas: list[Idea]) -> dict[str, list[str]]:
    """Compare ideas with those on git ref ``base``. Returns {label: problems}.

    Ideas are matched by id, so renaming a file is allowed. Checked here: the
    frozen attribution fields, the append-only version list, that content only
    changes together with a new version, and that frozen copies stay as they are.
    """
    current = {idea.id: idea for idea in ideas if idea.id}
    problems: dict[str, list[str]] = {}
    listing = _git(root, "ls-tree", "-r", "--name-only", base, "--", "ideas")
    for path in filter(None, listing.split("\n")):
        if not path.endswith(".md"):
            continue
        try:
            old_meta, old_body = split_front_matter(_git(root, "show", f"{base}:{path}"))
        except FormatError:
            continue  # was already broken on the base; nothing to protect
        old_id = old_meta.get("id")
        if not isinstance(old_id, str):
            continue
        new = current.get(old_id)
        found = frozen_changes(old_meta, new.meta if new else None)
        if new:
            found += revision_changes(old_meta, old_body, new, base)
        if found:
            problems[new.path if new else path] = found
    # Files under versions/ are the frozen past. They can be added, never edited.
    changed = _git(root, "diff", "--no-renames", "--name-status", base, "--", "versions")
    for line in filter(None, changed.split("\n")):
        state, path = line.split("\t", 1)
        if state != "A":
            problems.setdefault(path, []).append(
                "a frozen version was changed or removed; files under versions/ are never edited"
            )
    return problems

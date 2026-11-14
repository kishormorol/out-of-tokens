"""Load and validate idea files.

An idea is a Markdown file at ``ideas/<YYYY>/<id>-<slug>.md`` with YAML front
matter. This module is the single definition of that format: the validator, the
issue converter and the site builder all go through it.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

STATUSES = ("open", "being-built", "built")

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
    "tags",
    "why_unfinished",
    "estimated_cost",
)
OPTIONAL_KEYS = ("example", "built_from_this")

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


class FormatError(ValueError):
    """The file is not front matter followed by a body."""


@dataclass
class Idea:
    path: str  # repo-relative, forward slashes
    meta: dict
    body: str
    errors: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return str(self.meta.get("id", ""))


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


def _check_built(entry, where: str) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{where}: must be a mapping with 'name', 'url' and 'by'"]
    errors = []
    unknown = set(entry) - {"name", "url", "by", "date"}
    if unknown:
        errors.append(f"{where}: unknown keys {sorted(unknown)}")
    if not _is_str(entry.get("name"), 100):
        errors.append(f"{where}: 'name' is required")
    if not (isinstance(entry.get("url"), str) and URL_RE.match(entry["url"])):
        errors.append(f"{where}: 'url' must be an http(s) URL")
    if not _is_str(entry.get("by"), 100):
        errors.append(f"{where}: 'by' (who built it) is required")
    if "date" in entry and type(entry["date"]) is not dt.date:
        errors.append(f"{where}: 'date' must be YYYY-MM-DD")
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
    if meta.get("status") == "built" and not built:
        errors.append("status 'built' needs at least one entry in 'built_from_this'")

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
    return ideas


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


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout


def check_against_base(root: Path, base: str, ideas: list[Idea]) -> dict[str, list[str]]:
    """Compare ideas with those on git ref ``base``. Returns {label: problems}.

    Ideas are matched by id, so renaming a file is allowed.
    """
    current = {idea.id: idea for idea in ideas if idea.id}
    problems: dict[str, list[str]] = {}
    listing = _git(root, "ls-tree", "-r", "--name-only", base, "--", "ideas")
    for path in filter(None, listing.split("\n")):
        if not path.endswith(".md"):
            continue
        try:
            old_meta, _ = split_front_matter(_git(root, "show", f"{base}:{path}"))
        except FormatError:
            continue  # was already broken on the base; nothing to protect
        old_id = old_meta.get("id")
        if not isinstance(old_id, str):
            continue
        new = current.get(old_id)
        found = frozen_changes(old_meta, new.meta if new else None)
        if found:
            problems[new.path if new else path] = found
    return problems

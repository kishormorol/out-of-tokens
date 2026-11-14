"""Turn a submitted GitHub issue form into an idea file.

The issue body is untrusted text. It is only ever parsed here and written into
a Markdown file; nothing from it is passed to a shell.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

import yaml

from . import ideas

# Labels of the form fields, in the order .github/ISSUE_TEMPLATE/idea.yml
# declares them. A test checks the two stay in step.
FIELDS = (
    ("title", "Idea title"),
    ("authors", "Authors"),
    ("category", "Subject category"),
    ("tags", "Tags"),
    ("why_unfinished", "Why is it unfinished?"),
    ("estimated_cost", "Estimated cost to build"),
    ("abstract", "Abstract"),
    ("problem", "Problem"),
    ("idea", "Idea"),
    ("approach", "Approach"),
    ("done", "What's done"),
    ("links", "Links to partial code or notes"),
    ("agreement", "Agreement"),
)

# Fields the first edition of the form did not have. An issue without them is
# still read; the validator then says what is missing.
ADDED_LATER = ("category", "abstract")

NO_RESPONSE = "_No response_"
BODY_SECTIONS = (
    ("problem", "Problem"),
    ("idea", "Idea"),
    ("approach", "Approach"),
    ("done", "What's done"),
    ("links", "Links"),
)


class IssueError(ValueError):
    """The issue cannot be converted; the message is shown to the submitter."""


def parse_form(body: str) -> dict[str, str]:
    """Split an issue-form body into {field key: text}.

    GitHub renders each field as ``### <label>`` followed by the answer. Only
    the known labels, in their declared order, are treated as separators, so a
    ``###`` heading typed inside an answer stays part of that answer.
    """
    lines = (body or "").replace("\r\n", "\n").split("\n")
    result: dict[str, str] = {}
    start, key, expect = None, None, 0
    for i, line in enumerate(lines + [None]):
        # The next label is the next field, or the one after the fields that
        # an issue made with the form's first edition does not have.
        found = None
        if line is not None and line.startswith("### "):
            for n in range(expect, len(FIELDS)):
                if line.strip() == f"### {FIELDS[n][1]}":
                    found = n
                if found is not None or FIELDS[n][0] not in ADDED_LATER:
                    break
        if line is None or found is not None:
            if key is not None:
                text = "\n".join(lines[start:i]).strip()
                result[key] = "" if text == NO_RESPONSE else text
            if found is not None:
                key, start, expect = FIELDS[found][0], i + 1, found + 1
    return result


def slugify(title: str, max_len: int = 50) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")
    return slug[:max_len].strip("-") or "idea"


def parse_authors(text: str, fallback_login: str) -> list[dict]:
    """One author per line: a name plus optional @github, ORCID and URL tokens."""
    authors = []
    for line in text.split("\n"):
        line = line.strip().lstrip("-*").strip()
        if not line:
            continue
        author, name = {}, []
        for token in line.replace(",", " ").split():
            bare = token.strip("<>()")
            if bare.startswith("@") and ideas.GITHUB_RE.match(bare[1:]):
                author["github"] = bare[1:]
            elif ideas.ORCID_RE.match(bare.removeprefix("https://orcid.org/")):
                author["orcid"] = bare.removeprefix("https://orcid.org/")
            elif ideas.URL_RE.match(bare):
                author["url"] = bare
            else:
                name.append(token)
        authors.append({"name": " ".join(name) or author.get("github", ""), **author})
    if not authors:
        authors = [{"name": fallback_login, "github": fallback_login}]
    return authors


def parse_tags(text: str) -> list[str]:
    tags = []
    for raw in re.split(r"[,\n]", text):
        tag = re.sub(r"[^a-z0-9]+", "-", raw.strip().lower()).strip("-")[:30].strip("-")
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def build_idea(
    issue: dict, idea_id: str, today: dt.date | None = None
) -> tuple[str, str]:
    """Return (repo-relative path, file text) for a GitHub ``issue`` object.

    ``submitted`` is the day the issue was opened (UTC) unless ``today`` is given.
    Raises IssueError listing every problem if the result would not validate.
    """
    form = parse_form(issue.get("body") or "")
    login = issue["user"]["login"]
    today = today or dt.date.fromisoformat(issue["created_at"][:10])

    agreement = form.get("agreement", "").lower()
    if "[x]" not in agreement or "[ ]" in agreement:
        raise IssueError("- Every box under Agreement must be ticked.")

    title = " ".join(form.get("title", "").split())
    meta = {
        "id": idea_id,
        "title": title,
        "authors": parse_authors(form.get("authors", ""), login),
        "submitted": today,
        "status": "open",
        "category": form.get("category", "").strip(),
        "tags": parse_tags(form.get("tags", "")),
        "why_unfinished": [w.strip() for w in form.get("why_unfinished", "").split(",") if w.strip()],
        "estimated_cost": " ".join(form.get("estimated_cost", "").split()),
    }
    abstract = " ".join(form.get("abstract", "").split())
    if abstract:
        meta["abstract"] = abstract
    parts = []
    for key, heading in BODY_SECTIONS:
        text = form.get(key, "")
        if not text and key == "done":
            # Issues opened through the API or CLI skip the form's required check.
            text = "Nothing yet."
        if text:
            parts.append(f"## {heading}\n\n{text}")
    body = "\n" + "\n\n".join(parts) + "\n"

    path = f"ideas/{today.year}/{idea_id}-{slugify(title)}.md"
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000)
    text = f"---\n{front}---\n{body}"

    # Validate what was actually written, not the dict we meant to write.
    idea = ideas.load_text(path, text, today)
    if idea.errors:
        raise IssueError("\n".join(f"- {e}" for e in idea.errors))
    return path, text

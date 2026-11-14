"""Tell an idea's authors when someone adds a project to its built_from_this list.

The notify-builders workflow calls this on pull requests. It compares the idea
file on main with the file in the pull request and, when there are new
projects, writes a comment that mentions the authors' GitHub accounts, so
GitHub notifies them.
"""

from __future__ import annotations

import yaml

from .ideas import build_stage

MARKER = "<!-- out-of-tokens:notify-builders -->"


def _front_matter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    try:
        meta = yaml.safe_load(text.split("---", 2)[1])
    except (yaml.YAMLError, IndexError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _key(entry: dict) -> tuple:
    return (str(entry.get("name", "")).strip().lower(), str(entry.get("by", "")).strip().lower())


def new_projects(base_text: str, head_text: str) -> list[dict]:
    """Entries in the pull request's built_from_this that main does not have."""
    old = {_key(b) for b in _front_matter(base_text).get("built_from_this", []) or [] if isinstance(b, dict)}
    head = _front_matter(head_text).get("built_from_this", []) or []
    return [b for b in head if isinstance(b, dict) and _key(b) not in old]


def comment(idea_id: str, base_text: str, head_text: str) -> str:
    """The comment to post, or an empty string when nothing new was added.

    Authors are taken from main, not from the pull request, so a pull request
    cannot change who gets mentioned."""
    added = new_projects(base_text, head_text)
    if not added:
        return ""
    handles = [
        a["github"]
        for a in _front_matter(base_text).get("authors", []) or []
        if isinstance(a, dict) and isinstance(a.get("github"), str) and a["github"].replace("-", "").isalnum()
    ]
    lines = [MARKER]
    if handles:
        lines.append(" ".join(f"@{h}" for h in handles) + f": someone is building on your idea {idea_id}.")
    else:
        lines.append(f"New project for idea {idea_id}. The authors have no GitHub account on record, so nobody was mentioned.")
    lines.append("")
    for b in added:
        stage = "building now" if build_stage(b) == "building" else "built"
        name = str(b.get("name", "")).replace("@", "@​")
        by = str(b.get("by", "")).replace("@", "@​")
        lines.append(f"- {name} by {by} ({stage})")
    lines.append("")
    lines.append("Authors, you can reply here. The project shows on the idea page once this is merged.")
    return "\n".join(lines)

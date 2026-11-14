"""Command line: python -m out_of_tokens <validate|build|next-id|from-issue>."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from . import ideas, issue, site

ROOT = Path(__file__).resolve().parent.parent


def cmd_validate(args) -> int:
    loaded = ideas.load_all(args.root)
    problems = {i.path: list(i.errors) for i in loaded if i.errors}
    if args.base:
        for path, found in ideas.check_against_base(args.root, args.base, loaded).items():
            problems.setdefault(path, []).extend(found)
    for path, found in sorted(problems.items()):
        for message in found:
            print(f"{path}: {message}")
            if os.environ.get("GITHUB_ACTIONS"):
                print(f"::error file={path}::{message}")
    if problems:
        print(f"\n{sum(map(len, problems.values()))} problem(s) in {len(problems)} file(s).")
        return 1
    print(f"{len(loaded)} idea(s) valid.")
    return 0


def cmd_build(args) -> int:
    loaded = ideas.load_all(args.root)
    if any(i.errors for i in loaded):
        print("Ideas do not validate; run 'python -m out_of_tokens validate'.", file=sys.stderr)
        return 1
    repo = os.environ.get("GITHUB_REPOSITORY")
    repo_url = args.repo_url or (f"https://github.com/{repo}" if repo else None)
    site_url = args.site_url
    if not site_url and repo:
        owner, name = repo.split("/", 1)
        site_url = f"https://{owner.lower()}.github.io/{name}"
    if not (repo_url and site_url):
        print(
            "warning: no --site-url/--repo-url and no GITHUB_REPOSITORY; "
            "using OWNER placeholders in credit lines and links.",
            file=sys.stderr,
        )
    site.build(
        loaded,
        args.out,
        site_url or "https://OWNER.github.io/out-of-tokens",
        repo_url or "https://github.com/OWNER/out-of-tokens",
    )
    print(f"Built {len(loaded)} idea page(s) into {args.out}")
    return 0


def cmd_next_id(args) -> int:
    print(ideas.next_id([i.id for i in ideas.load_all(args.root)]))
    return 0


def cmd_from_issue(args) -> int:
    event = json.loads(Path(args.event).read_text(encoding="utf-8"))
    gh_issue = event["issue"]
    used = [i.id for i in ideas.load_all(args.root)]
    used += re.findall(r"OOT-\d{4,}", args.reserved_refs or "")
    idea_id = ideas.next_id(used)
    try:
        path, text = issue.build_idea(gh_issue, idea_id)
    except issue.IssueError as exc:
        print(str(exc))
        return 2
    target = args.root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    # Only values made here from a fixed alphabet are handed to the workflow.
    outputs = {"id": idea_id, "path": path, "branch": f"idea/{idea_id}-issue-{int(gh_issue['number'])}"}
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as fh:
            fh.writelines(f"{k}={v}\n" for k, v in outputs.items())
    print(json.dumps(outputs))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="out_of_tokens", description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check every idea file")
    p.add_argument("--base", help="git ref to compare with; frozen fields may not differ from it")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("build", help="build the static site")
    p.add_argument("--out", type=Path, default=ROOT / "_site")
    p.add_argument("--site-url", help="public URL of the site, used in credit lines")
    p.add_argument("--repo-url", help="URL of the GitHub repository")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("next-id", help="print the next free idea id")
    p.set_defaults(func=cmd_next_id)

    p = sub.add_parser("from-issue", help="write an idea file from a GitHub issue event")
    p.add_argument("--event", required=True, help="path to the event JSON (GITHUB_EVENT_PATH)")
    p.add_argument("--reserved-refs", help="text containing ids held by open idea branches")
    p.set_defaults(func=cmd_from_issue)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

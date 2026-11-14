"""Command line: python -m out_of_tokens <command>. Run with -h for the list."""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

from . import ideas, issue, pdf, site, zenodo

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


def _urls(args) -> tuple[str | None, str | None]:
    """(site URL, repository URL) from the options or from GITHUB_REPOSITORY."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    repo_url = args.repo_url or (f"https://github.com/{repo}" if repo else None)
    site_url = args.site_url
    if not site_url and repo:
        owner, name = repo.split("/", 1)
        site_url = f"https://{owner.lower()}.github.io/{name}"
    return site_url, repo_url


def _valid_ideas(args) -> list[ideas.Idea] | None:
    loaded = ideas.load_all(args.root)
    if any(i.errors for i in loaded):
        print("Ideas do not validate; run 'python -m out_of_tokens validate'.", file=sys.stderr)
        return None
    return loaded


def cmd_build(args) -> int:
    loaded = _valid_ideas(args)
    if loaded is None:
        return 1
    site_url, repo_url = _urls(args)
    if not (repo_url and site_url):
        print(
            "warning: no --site-url/--repo-url and no GITHUB_REPOSITORY; "
            "using OWNER placeholders in credit lines and links.",
            file=sys.stderr,
        )
    chrome = pdf.find_chrome() if args.pdf != "off" else None
    if args.pdf == "on" and not chrome:
        print("No Chrome or Chromium found, so PDF files cannot be built.", file=sys.stderr)
        return 1
    if args.pdf == "auto" and not chrome:
        message = "No Chrome or Chromium found; the site is built without PDF files."
        print(f"::warning::{message}" if os.environ.get("GITHUB_ACTIONS") else message)
    urls = (
        site_url or "https://OWNER.github.io/out-of-tokens",
        repo_url or "https://github.com/OWNER/out-of-tokens",
    )
    try:
        site.build(loaded, args.out, *urls, chrome=chrome)
    except RuntimeError as exc:
        # Only printing a PDF raises this. With 'auto' the site matters more
        # than its PDF files, so build it again without them.
        if args.pdf != "auto":
            print(str(exc), file=sys.stderr)
            return 1
        message = f"PDF files were left out: {exc}"
        print(f"::warning::{message}" if os.environ.get("GITHUB_ACTIONS") else message)
        chrome = None
        site.build(loaded, args.out, *urls)
    print(f"Built {len(loaded)} idea page(s) into {args.out}" + (" with PDF files" if chrome else ""))
    return 0


def cmd_revise(args) -> int:
    loaded = _valid_ideas(args)
    if loaded is None:
        return 1
    idea = next((i for i in loaded if i.id == args.id), None)
    if idea is None:
        print(f"No idea with id {args.id}.", file=sys.stderr)
        return 1
    if idea.meta["status"] == "withdrawn":
        print(f"{idea.id} is withdrawn and cannot get a new version.", file=sys.stderr)
        return 1
    note = " ".join(args.note.split())
    if not 0 < len(note) <= 200:
        print("--note must be one line of at most 200 characters.", file=sys.stderr)
        return 1
    current = idea.version
    date = args.date or dt.datetime.now(dt.timezone.utc).date()
    file = args.root / idea.path
    text = file.read_text(encoding="utf-8")
    versions = [dict(v) for v in idea.versions]
    versions.append({"version": current + 1, "date": date, "note": note})
    try:
        revised = ideas.set_record_fields(text, versions, idea.meta.get("doi"))
    except ideas.FormatError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    frozen = args.root / ideas.version_path(idea.id, current)
    frozen.parent.mkdir(parents=True, exist_ok=True)
    frozen.write_text(text, encoding="utf-8")
    file.write_text(revised, encoding="utf-8")
    print(
        f"Kept version {current} at {frozen.relative_to(args.root).as_posix()} and started "
        f"version {current + 1} in {idea.path}.\n"
        "Now edit the idea file, run 'python -m out_of_tokens validate', "
        "and open a pull request with both files."
    )
    return 0


def cmd_list_versions(args) -> int:
    """One line per version: id, number, and the file that holds its text."""
    for idea in ideas.load_all(args.root):
        if idea.errors or not idea.id:
            continue
        for number in range(1, idea.version + 1):
            path = idea.path if number == idea.version else ideas.version_path(idea.id, number)
            print(f"{idea.id} {number} {path}")
    return 0


def cmd_zenodo(args) -> int:
    loaded = _valid_ideas(args)
    if loaded is None:
        return 1
    site_url, repo_url = _urls(args)
    if not (site_url and repo_url):
        print("Give --site-url and --repo-url; a deposit must carry the real addresses.", file=sys.stderr)
        return 1
    todo, skipped = zenodo.pending(loaded)
    for line in skipped:
        print(f"skipped {line}")
    if not todo:
        print("Nothing to deposit.")
        return 0
    if len(todo) > args.limit:
        print(f"{len(todo)} versions need a DOI; this run takes the first {args.limit}.")
        todo = todo[: args.limit]
    if args.dry_run:
        for idea, number in todo:
            view = site.views(idea)[number - 1]
            print(f"would deposit {idea.id}v{number}:")
            print(json.dumps(zenodo.build_metadata(idea, view, site_url), indent=2, ensure_ascii=False))
        return 0
    token = os.environ.pop("ZENODO_TOKEN", "").strip()
    if not token:
        print("ZENODO_TOKEN is not set, so nothing was deposited. See MAINTAINERS.md.")
        return 0
    sandbox = os.environ.get("ZENODO_SANDBOX", "").strip().lower() in ("true", "1", "yes")
    client = zenodo.Client(token, sandbox=sandbox)
    chrome = pdf.find_chrome()
    print(f"Depositing on {client.api.removesuffix('/api')}" + ("" if chrome else " (no browser found, so without PDF files)"))
    try:
        existing = client.list_depositions()
    except zenodo.ZenodoError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    done: dict[tuple[str, int], str] = {}
    failed: set[str] = set()
    for idea, number in todo:
        label = f"{idea.id}v{number}"
        if idea.id in failed:
            print(f"skipped {label}: an earlier version of it failed in this run")
            continue
        view = site.views(idea)[number - 1]
        source = idea.path if view.latest else ideas.version_path(idea.id, number)

        def make_files(reserved, idea=idea, view=view, source=source, label=label):
            files = {f"{label}.md": (args.root / source).read_bytes()}
            if chrome:
                stamped = dataclasses.replace(view, doi=reserved or view.doi)
                files[site.pdf_name(idea, view.version)] = site.version_pdf(
                    idea, stamped, site_url, repo_url, chrome
                )
            return files

        previous = None
        if number > 1:
            previous = done.get((idea.id, number - 1)) or idea.versions[number - 2].get("doi")
        try:
            result = zenodo.deposit_version(
                client, idea, view, site_url, existing, previous, make_files
            )
        except (zenodo.ZenodoError, RuntimeError, OSError, KeyError) as exc:
            print(f"error: {label}: {exc}", file=sys.stderr)
            failed.add(idea.id)
            continue
        done[(idea.id, number)] = result.doi
        how = "was already on Zenodo" if result.reused else "deposited"
        if sandbox or zenodo.is_sandbox_doi(result.doi):
            print(f"{label}: {how}, sandbox DOI {result.doi}. Sandbox DOIs are not written to the repository.")
            continue
        file = args.root / idea.path
        try:
            file.write_text(
                zenodo.apply_dois(file.read_text(encoding="utf-8"), {number: result.doi}, result.concept_doi),
                encoding="utf-8",
            )
        except ideas.FormatError as exc:
            print(f"error: {label}: has DOI {result.doi} but {idea.path} was not updated: {exc}", file=sys.stderr)
            failed.add(idea.id)
            continue
        print(f"{label}: {how}, DOI {result.doi}")
    return 1 if failed else 0


def cmd_notify_builders(args) -> int:
    from . import notify

    base = Path(args.base).read_text(encoding="utf-8") if Path(args.base).is_file() else ""
    head = Path(args.head).read_text(encoding="utf-8") if Path(args.head).is_file() else ""
    text = notify.comment(args.id, base, head)
    if text:
        print(text)
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
    p.add_argument(
        "--pdf",
        choices=("off", "auto", "on"),
        default="off",
        help="make a PDF of every version with headless Chrome: 'auto' if one is found, 'on' or fail",
    )
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("revise", help="start a new version of an idea")
    p.add_argument("id", help="the idea id, such as OOT-0001")
    p.add_argument("--note", required=True, help="one line that says what changed")
    p.add_argument("--date", type=dt.date.fromisoformat, help="date of the new version (default: today, UTC)")
    p.set_defaults(func=cmd_revise)

    p = sub.add_parser("list-versions", help="list every version and the file holding its text")
    p.set_defaults(func=cmd_list_versions)

    p = sub.add_parser("zenodo", help="deposit versions without a DOI on Zenodo (needs ZENODO_TOKEN)")
    p.add_argument("--site-url", help="public URL of the site")
    p.add_argument("--repo-url", help="URL of the GitHub repository")
    p.add_argument("--dry-run", action="store_true", help="print what would be sent and stop")
    p.add_argument("--limit", type=int, default=10, help="most versions to deposit in one run")
    p.set_defaults(func=cmd_zenodo)

    p = sub.add_parser("notify-builders", help="comment text telling authors about new projects")
    p.add_argument("--id", required=True, help="idea id, e.g. OOT-0003")
    p.add_argument("--base", required=True, help="the idea file as it is on main")
    p.add_argument("--head", required=True, help="the idea file as it is in the pull request")
    p.set_defaults(func=cmd_notify_builders)

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

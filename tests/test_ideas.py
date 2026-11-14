import datetime as dt
import subprocess
from pathlib import Path

import pytest

from out_of_tokens import ideas

ROOT = Path(__file__).resolve().parent.parent
TODAY = dt.date(2026, 11, 14)
PATH = "ideas/2026/OOT-0007-a-test-idea.md"

GOOD = """---
id: OOT-0007
title: A test idea
authors:
  - name: Ada Example
    github: ada-example
    orcid: 0000-0002-1825-0097
    url: https://ada.example
submitted: 2026-11-01
status: open
category: dev-tools
tags: [testing, example-tag]
why_unfinished: [llm-api-cost]
estimated_cost: "USD 100"
---

## Problem

p

## Idea

i

## Approach

a

## What's done

n
"""


def errors(text, path=PATH):
    return ideas.load_text(path, text, TODAY).errors


def test_good_idea_has_no_errors():
    assert errors(GOOD) == []


def test_repository_ideas_are_valid():
    loaded = ideas.load_all(ROOT)
    assert loaded, "the repository should ship at least one idea"
    assert {i.path: i.errors for i in loaded if i.errors} == {}


@pytest.mark.parametrize(
    "old, new, expected",
    [
        ("id: OOT-0007", "id: UB-7", "'id' must look like"),
        ("id: OOT-0007", "id: OOT-0008", "file name says OOT-0007"),
        ("title: A test idea", "title: Hey", "'title' must be"),
        ("    github: ada-example", "    github: '@ada'", "'github' must be"),
        ("0000-0002-1825-0097", "0000-0002-1825-0098", "wrong check digit"),
        ("0000-0002-1825-0097", "1234", "'orcid' must look like"),
        ("https://ada.example", "javascript:alert(1)", "'url' must be"),
        ("    url: https://ada.example", "    url: https://ada.example\n    email: a@b.c", "unknown keys"),
        ("submitted: 2026-11-01", "submitted: '2026-11-01'", "unquoted date"),
        ("submitted: 2026-11-01", "submitted: 2026-12-25", "in the future"),
        ("submitted: 2026-11-01", "submitted: 2025-11-01", "folder is 2026"),
        ("status: open", "status: done", "'status' must be one of"),
        ("status: open", "status: built", "needs at least one finished entry"),
        ("category: dev-tools", "category: cooking", "'category' must be one of"),
        ("category: dev-tools\n", "", "missing required field 'category'"),
        ("status: open", "status: open\nabstract: [a, b]", "'abstract' must be plain text"),
        ("status: open", "status: open\nabstract: " + "x" * 1501, "'abstract' must be plain text"),
        ("status: open", "status: open\ndoi: zenodo.123", "must look like 10.5281"),
        ("status: open", "status: open\ndoi: 10.5072/zenodo.123", "sandbox DOI"),
        ("status: open", "status: withdrawn", "needs a 'withdrawn' mapping"),
        ("status: open", "status: open\nwithdrawn: {date: 2026-11-02, reason: Changed my mind about it}", "only allowed with status 'withdrawn'"),
        ("status: open", "status: withdrawn\nwithdrawn: {date: 2026-11-02}", "'reason' is required"),
        ("status: open", "status: withdrawn\nwithdrawn: {date: 2026-10-01, reason: Changed my mind about it}", "earlier than 'submitted'"),
        ("status: open", "status: open\nversions: []", "'versions' must be a non-empty list"),
        ("status: open", "status: open\nversions: [{version: 2, date: 2026-11-01}]", "'version' must be 1"),
        ("status: open", "status: open\nversions: [{version: 1, date: 2026-11-02}]", "must equal 'submitted'"),
        ("status: open", "status: open\nversions: [{version: 1, date: 2026-11-01}, {version: 2, date: 2026-11-05}]", "'note' is required"),
        ("status: open", "status: open\nversions: [{version: 1, date: 2026-11-01}, {version: 2, date: 2026-10-05, note: x}]", "earlier than the version before"),
        ("status: open", "status: open\nversions: [{version: 1, date: 2026-11-01, doi: nope}]", "versions[1]: 'doi' must look like"),
        ("status: open", "status: open\nversions: [{version: 1, date: 2026-11-01, pdf: x}]", "versions[1]: unknown keys"),
        ("tags: [testing, example-tag]", "tags: []", "1 to 8 tags"),
        ("tags: [testing, example-tag]", "tags: [Machine Learning]", "must be lowercase"),
        ("tags: [testing, example-tag]", "tags: [a, a]", "duplicates"),
        ("why_unfinished: [llm-api-cost]", "why_unfinished: [laziness]", "must be one of"),
        ("why_unfinished: [llm-api-cost]", "why_unfinished: llm-api-cost", "non-empty list"),
        ('estimated_cost: "USD 100"', "estimated_cost: 100", "'estimated_cost' must be"),
        ('estimated_cost: "USD 100"\n', "", "missing required field 'estimated_cost'"),
        ("status: open", "status: open\nlicense: MIT", "unknown fields"),
        ("## Approach", "## Method", "missing the section '## Approach'"),
        ("authors:\n  - name: Ada Example", "authors:\n  - github: ada", "'name' is required"),
    ],
)
def test_each_rule_is_enforced(old, new, expected):
    assert old in GOOD
    found = errors(GOOD.replace(old, new))
    assert any(expected in e for e in found), found


def test_orcid_check_digit_x():
    assert ideas.orcid_checksum_ok("0000-0002-9079-593X")
    assert not ideas.orcid_checksum_ok("0000-0002-9079-5930")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("no front matter", "must start with"),
        ("---\nid: OOT-0007\n", "not closed"),
        ("---\n- a\n- b\n---\nbody", "must be a YAML mapping"),
        ("---\nid: [unclosed\n---\nbody", "not valid YAML"),
    ],
)
def test_malformed_files_are_reported_not_raised(text, expected):
    found = errors(text)
    assert len(found) == 1 and expected in found[0]


def test_bad_path():
    assert "path must be" in errors(GOOD, "ideas/OOT-0007-a-test-idea.md")[0]
    assert any("slug" in e for e in errors(GOOD, "ideas/2026/OOT-0007-Bad_Slug.md"))


def test_section_heading_inside_code_fence_does_not_count():
    body = GOOD.replace("## Approach\n\na", "```\n## Approach\n```")
    assert any("## Approach" in e for e in errors(body))


def test_built_from_this_entries():
    good = GOOD.replace(
        "status: open",
        "status: built\nbuilt_from_this:\n  - name: Thing\n    url: https://thing.example\n"
        "    by: Bo Builder\n    date: 2026-11-10",
    )
    assert errors(good) == []
    bad = good.replace("    url: https://thing.example\n", "")
    assert any("built_from_this[1]: 'url'" in e for e in errors(bad))


def test_next_id():
    assert ideas.next_id([]) == "OOT-0001"
    assert ideas.next_id(["OOT-0001", "OOT-0009", "OOT-0003", "junk"]) == "OOT-0010"
    assert ideas.next_id(["OOT-9999"]) == "OOT-10000"


def write(root, path, text):
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")


def test_duplicate_ids_and_stray_files(tmp_path):
    write(tmp_path, PATH, GOOD)
    write(tmp_path, "ideas/2026/OOT-0007-second-copy.md", GOOD)
    write(tmp_path, "ideas/notes.md", "hello")
    by_path = {i.path: i.errors for i in ideas.load_all(tmp_path, TODAY)}
    assert by_path[PATH] == []
    assert any("already used by" in e for e in by_path["ideas/2026/OOT-0007-second-copy.md"])
    assert by_path["ideas/notes.md"]


def git(root, *args):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=root, check=True, capture_output=True,
    )


@pytest.fixture
def repo(tmp_path):
    write(tmp_path, PATH, GOOD)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def against_base(repo):
    return ideas.check_against_base(repo, "main", ideas.load_all(repo, TODAY))


def test_frozen_fields_allow_normal_edits_and_renames(repo):
    edited = GOOD.replace("status: open", "status: being-built").replace("testing, ", "")
    (repo / PATH).unlink()
    write(repo, "ideas/2026/OOT-0007-renamed.md", edited)
    assert against_base(repo) == {}


def test_frozen_fields_reject_author_swap(repo):
    write(repo, PATH, GOOD.replace("Ada Example", "Mallory Thief"))
    assert "'authors' changed" in against_base(repo)[PATH][0]


def test_frozen_fields_reject_backdating_and_deletion(repo):
    write(repo, PATH, GOOD.replace("2026-11-01", "2026-01-01"))
    assert "'submitted' changed" in against_base(repo)[PATH][0]
    (repo / PATH).unlink()
    assert "removed" in against_base(repo)[PATH][0]


def test_new_idea_is_not_a_frozen_change(repo):
    write(repo, "ideas/2026/OOT-0008-new.md", GOOD.replace("OOT-0007", "OOT-0008"))
    assert against_base(repo) == {}


# --- versions, withdrawal and DOIs -----------------------------------------

V2 = "versions:\n  - version: 1\n    date: 2026-11-01\n  - version: 2\n    date: 2026-11-10\n    note: \"Sharper problem\"\n"
WITHDRAWN = "status: withdrawn\nwithdrawn:\n  date: 2026-11-12\n  reason: \"The author found the same idea already built.\""


def test_withdrawn_idea_with_a_reason_is_valid():
    assert errors(GOOD.replace("status: open", WITHDRAWN)) == []


def test_section_text():
    assert ideas.section_text("## Problem\n\none\n\ntwo\n\n## Idea\n\nthree\n", "Problem") == "one\n\ntwo"
    assert ideas.section_text("## Problem\n\n```\n## Idea\n```\n", "Idea") == ""


def test_an_idea_without_versions_has_one_dated_submitted():
    idea = ideas.load_text(PATH, GOOD, TODAY)
    assert idea.version == 1
    assert idea.versions == [{"version": 1, "date": dt.date(2026, 11, 1)}]


def test_set_record_fields_touches_nothing_else():
    text = GOOD.replace("tags: [testing, example-tag]", "tags: [testing, example-tag]   # a comment")
    versions = [
        {"version": 1, "date": dt.date(2026, 11, 1), "doi": "10.5281/zenodo.11"},
        {"version": 2, "date": dt.date(2026, 11, 10), "note": 'Fixed: "quotes" and # signs'},
    ]
    out = ideas.set_record_fields(text, versions, "10.5281/zenodo.10")
    front = text.split("\n---\n")[0]
    assert out.startswith(front + "\n")  # the author's lines, comment included, are untouched
    assert out.endswith(text.split("\n---\n", 1)[1])
    meta, _ = ideas.split_front_matter(out)
    assert meta["doi"] == "10.5281/zenodo.10" and meta["versions"] == versions
    # Running it again replaces the two keys instead of adding them twice.
    again = ideas.set_record_fields(out, versions, "10.5281/zenodo.10")
    assert again == out
    assert ideas.load_text(PATH, out, TODAY).errors == []


def test_set_record_fields_handles_any_yaml_style_or_refuses():
    flow = GOOD.replace("status: open", "status: open\nversions: [{version: 1, date: 2026-11-01}]\ndoi: 10.5281/zenodo.1")
    out = ideas.set_record_fields(flow, [{"version": 1, "date": dt.date(2026, 11, 1)}], None)
    assert "doi" not in ideas.split_front_matter(out)[0]
    unindented = GOOD.replace("status: open", "versions:\n- version: 1\n  date: 2026-11-01\nstatus: open")
    meta, _ = ideas.split_front_matter(ideas.set_record_fields(unindented, None, "10.5281/zenodo.1"))
    assert "versions" not in meta and meta["status"] == "open"
    odd = GOOD.replace("status: open", 'status: open\n"doi" : 10.5281/zenodo.9')
    with pytest.raises(ideas.FormatError):
        ideas.set_record_fields(odd, None, None)


def revised(text=GOOD, body_change=("\np\n", "\nbetter\n")):
    return text.replace(*body_change).replace("status: open\n", "status: open\n" + V2)


def test_past_versions_are_loaded_from_frozen_copies(tmp_path):
    write(tmp_path, PATH, revised())
    loaded = ideas.load_all(tmp_path, TODAY)
    assert any("version 1 is missing: versions/OOT-0007/v1.md" in e for e in loaded[0].errors)
    write(tmp_path, "versions/OOT-0007/v1.md", GOOD)
    write(tmp_path, "versions/README.md", "notes")
    (idea,) = ideas.load_all(tmp_path, TODAY)
    assert idea.errors == [] and idea.version == 2
    assert idea.frozen[1][0]["title"] == "A test idea" and "\np\n" in idea.frozen[1][1]


def test_stray_and_mismatched_frozen_copies_are_reported(tmp_path):
    write(tmp_path, PATH, revised())
    write(tmp_path, "versions/OOT-0007/v1.md", GOOD.replace("OOT-0007", "OOT-0008"))
    write(tmp_path, "versions/OOT-0007/v2.md", GOOD)
    write(tmp_path, "versions/OOT-0099/v1.md", GOOD)
    by_path = {i.path: i.errors for i in ideas.load_all(tmp_path, TODAY)}
    assert any("expected OOT-0007" in e for e in by_path[PATH])
    assert "no idea lists this version" in by_path["versions/OOT-0007/v2.md"][0]
    assert "no idea lists this version" in by_path["versions/OOT-0099/v1.md"][0]


def test_content_change_needs_a_new_version(repo):
    write(repo, PATH, GOOD.replace("\np\n", "\nbetter\n"))
    assert "without a new version" in against_base(repo)[PATH][0]
    write(repo, PATH, GOOD.replace("A test idea", "A better title"))
    assert "without a new version" in against_base(repo)[PATH][0]
    write(repo, PATH, GOOD.replace("status: open", "status: open\nabstract: Now with an abstract."))
    assert "without a new version" in against_base(repo)[PATH][0]


def test_a_revision_with_its_frozen_copy_passes(repo):
    write(repo, "versions/OOT-0007/v1.md", GOOD)
    write(repo, PATH, revised())
    assert against_base(repo) == {}


def test_a_revision_is_refused_when_the_frozen_copy_is_not_what_main_has(repo):
    write(repo, "versions/OOT-0007/v1.md", GOOD.replace("\np\n", "\nrewritten history\n"))
    write(repo, PATH, revised())
    (problem,) = against_base(repo)[PATH]
    assert "must hold version 1 as it is on main" in problem
    assert "git show main:" + PATH in problem


def test_a_revision_must_change_something_and_come_one_at_a_time(repo):
    write(repo, "versions/OOT-0007/v1.md", GOOD)
    write(repo, PATH, revised(body_change=("x-none", "x-none")))
    assert "same title, abstract and body" in against_base(repo)[PATH][0]
    v3 = V2 + "  - version: 3\n    date: 2026-11-11\n    note: again\n"
    write(repo, "versions/OOT-0007/v2.md", revised())
    write(repo, PATH, GOOD.replace("\np\n", "\nthird\n").replace("status: open\n", "status: open\n" + v3))
    assert "one new version at a time" in against_base(repo)[PATH][0]


@pytest.fixture
def repo_v2(repo):
    doi = V2.replace("    date: 2026-11-01\n", '    date: 2026-11-01\n    doi: "10.5281/zenodo.11"\n')
    write(repo, "versions/OOT-0007/v1.md", GOOD)
    write(repo, PATH, revised().replace(V2, 'doi: "10.5281/zenodo.10"\n' + doi))
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "v2")
    return repo


def test_past_versions_and_dois_are_frozen(repo_v2):
    current = (repo_v2 / PATH).read_text()
    assert against_base(repo_v2) == {}
    write(repo_v2, PATH, current.replace("date: 2026-11-10", "date: 2026-11-09"))
    assert "version 2: 'date' changed" in against_base(repo_v2)[PATH][0]
    write(repo_v2, PATH, current.replace("zenodo.11", "zenodo.99"))
    assert "version 1: 'doi' changed" in against_base(repo_v2)[PATH][0]
    write(repo_v2, PATH, current.replace("zenodo.10", "zenodo.98"))
    assert "'doi' changed; a DOI is permanent" in against_base(repo_v2)[PATH]
    # Adding a DOI to a version that has none is what the Zenodo workflow does.
    write(repo_v2, PATH, current.replace('    note: "Sharper problem"\n', '    note: "Sharper problem"\n    doi: "10.5281/zenodo.12"\n'))
    assert against_base(repo_v2) == {}
    # Dropping the newest version is refused; its frozen predecessor is still required.
    write(repo_v2, PATH, GOOD)
    assert any("versions were removed" in e for e in against_base(repo_v2)[PATH])


def test_frozen_copies_cannot_be_edited_or_deleted(repo_v2):
    frozen = "versions/OOT-0007/v1.md"
    write(repo_v2, frozen, GOOD.replace("Ada Example", "Mallory Thief"))
    assert "never edited" in against_base(repo_v2)[frozen][0]
    (repo_v2 / frozen).unlink()
    assert "never edited" in against_base(repo_v2)[frozen][0]


def test_withdrawing_is_allowed_and_then_permanent(repo):
    withdrawn = GOOD.replace("status: open", WITHDRAWN)
    write(repo, PATH, withdrawn)
    assert against_base(repo) == {}
    git(repo, "commit", "-q", "-am", "withdraw")
    write(repo, PATH, GOOD)
    assert "a withdrawal is permanent" in against_base(repo)[PATH][0]
    write(repo, PATH, withdrawn.replace("already built", "already built, twice"))
    assert "a withdrawal is permanent" in against_base(repo)[PATH][0]
    write(repo, "versions/OOT-0007/v1.md", withdrawn)
    write(repo, PATH, withdrawn.replace("\np\n", "\nbetter\n").replace("category:", V2 + "category:"))
    assert "a withdrawn idea cannot get a new version" in against_base(repo)[PATH]


def test_building_entries_may_skip_the_url():
    building = GOOD.replace(
        "status: open",
        "status: being-built\nbuilt_from_this:\n  - name: Early prototype\n    by: Bo Builder\n"
        "    stage: building\n    date: 2026-11-14",
    )
    assert errors(building) == []
    assert any("'stage' must be" in e for e in errors(building.replace("stage: building", "stage: soon")))
    # A finished entry still needs a link, and 'built' needs a finished entry.
    assert any("'url'" in e for e in errors(building.replace("    stage: building\n", "")))
    only_building = building.replace("status: being-built", "status: built")
    assert any("finished entry" in e for e in errors(only_building))

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
        ("status: open", "status: built", "needs at least one entry"),
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
    edited = GOOD.replace("status: open", "status: being-built").replace("\np\n", "\nbetter\n")
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

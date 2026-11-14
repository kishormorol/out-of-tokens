import datetime as dt
from pathlib import Path

import pytest
import yaml

from out_of_tokens import ideas, issue

ROOT = Path(__file__).resolve().parent.parent
TICKED = "- [X] mine\n- [X] cc by\n- [X] norm"


def form_body(**overrides):
    answers = {
        "Idea title": "Summaries of council meetings",
        "Authors": "Ada Example @ada-example 0000-0002-1825-0097 https://ada.example\nSecond Person",
        "Subject category": "civic",
        "Tags": "Civic Tech, summarisation",
        "Why is it unfinished?": "llm-api-cost, time",
        "Estimated cost to build": "USD 400 a month",
        "Abstract": "_No response_",
        "Problem": "Meetings are long.",
        "Idea": "Summarise them.",
        "Approach": "Transcribe, then summarise.",
        "What's done": "A scraper.",
        "Links to partial code or notes": "_No response_",
        "Agreement": TICKED,
    }
    answers.update(overrides)
    return "\r\n\r\n".join(f"### {label}\r\n\r\n{text}" for label, text in answers.items())


def gh_issue(**overrides):
    return {
        "number": 12,
        "created_at": "2026-11-03T23:59:00Z",
        "user": {"login": "ada-example", "id": 1},
        "body": form_body(**overrides),
    }


def test_form_labels_match_the_issue_template():
    template = yaml.safe_load((ROOT / ".github/ISSUE_TEMPLATE/idea.yml").read_text())
    fields = [(b["id"], b["attributes"]["label"]) for b in template["body"] if "id" in b]
    assert fields == list(issue.FIELDS)
    dropdown = next(b for b in template["body"] if b.get("id") == "why_unfinished")
    assert tuple(dropdown["attributes"]["options"]) == ideas.WHY_UNFINISHED
    dropdown = next(b for b in template["body"] if b.get("id") == "category")
    assert tuple(dropdown["attributes"]["options"]) == tuple(ideas.CATEGORIES)
    assert "multiple" not in dropdown["attributes"]  # one category per idea


def test_build_idea_round_trip():
    path, text = issue.build_idea(gh_issue(), "OOT-0003")
    assert path == "ideas/2026/OOT-0003-summaries-of-council-meetings.md"
    idea = ideas.load_text(path, text, dt.date(2026, 11, 14))
    assert idea.errors == []
    assert idea.meta["submitted"] == dt.date(2026, 11, 3)  # the day the issue was opened
    assert idea.meta["status"] == "open"
    assert idea.meta["category"] == "civic"
    assert "abstract" not in idea.meta and "versions" not in idea.meta
    assert idea.meta["tags"] == ["civic-tech", "summarisation"]
    assert idea.meta["why_unfinished"] == ["llm-api-cost", "time"]
    assert idea.meta["authors"] == [
        {
            "name": "Ada Example",
            "github": "ada-example",
            "orcid": "0000-0002-1825-0097",
            "url": "https://ada.example",
        },
        {"name": "Second Person"},
    ]
    assert ideas.sections(idea.body) == ["Problem", "Idea", "Approach", "What's done"]


def test_empty_authors_fall_back_to_the_issue_author():
    _, text = issue.build_idea(gh_issue(Authors="_No response_"), "OOT-0003")
    meta, _ = ideas.split_front_matter(text)
    assert meta["authors"] == [{"name": "ada-example", "github": "ada-example"}]


def test_heading_inside_an_answer_stays_in_that_answer():
    tricky = "Real problem.\n\n### Idea\n\nnot the idea field\n\n### Agreement\n\n- [ ] no"
    form = issue.parse_form(form_body(Problem=tricky))
    # The first "### Idea" line ends Problem (unavoidable), but a later known
    # label cannot be claimed twice and the real Agreement answer wins.
    assert form["agreement"] == TICKED
    assert form["title"] == "Summaries of council meetings"


def test_hostile_text_cannot_break_out_of_the_front_matter():
    hostile = 'x: y"\n---\nid: OOT-0001\nauthors: [{name: Mallory}]'
    _, text = issue.build_idea(
        gh_issue(**{"Idea title": "A title: with #yaml [chars]", "Estimated cost to build": hostile}),
        "OOT-0003",
    )
    meta, _ = ideas.split_front_matter(text)
    assert meta["id"] == "OOT-0003"
    assert meta["title"] == "A title: with #yaml [chars]"
    assert meta["authors"][0]["name"] == "Ada Example"
    assert "Mallory" in meta["estimated_cost"]  # kept as plain text, nothing more


@pytest.mark.parametrize(
    "overrides, expected",
    [
        ({"Agreement": "- [X] mine\n- [ ] cc by\n- [X] norm"}, "Agreement"),
        ({"Idea title": "Hey"}, "'title' must be"),
        ({"Tags": "!!!"}, "'tags' must be"),
        ({"Why is it unfinished?": "boredom"}, "must be one of"),
        ({"Subject category": "cooking"}, "'category' must be one of"),
        ({"Abstract": "x" * 1501}, "'abstract' must be plain text"),
        ({"Approach": "_No response_"}, "## Approach"),
    ],
)
def test_bad_submissions_are_refused_with_reasons(overrides, expected):
    with pytest.raises(issue.IssueError, match=expected):
        issue.build_idea(gh_issue(**overrides), "OOT-0003")


def test_blank_issue_is_refused():
    with pytest.raises(issue.IssueError):
        issue.build_idea({"number": 1, "created_at": "2026-11-03T00:00:00Z",
                          "user": {"login": "x", "id": 1}, "body": None}, "OOT-0003")


def test_slugify():
    assert issue.slugify("Héllo, Wörld! 2") == "hello-world-2"
    assert issue.slugify("আইডিয়া") == "idea"
    assert len(issue.slugify("word " * 40)) <= 50
    assert not issue.slugify("word " * 40).endswith("-")


def test_empty_whats_done_becomes_nothing_yet():
    # Issues opened through the API or CLI skip the form's required check.
    path, text = issue.build_idea(gh_issue(**{"What's done": "_No response_"}), "OOT-0003")
    idea = ideas.load_text(path, text, dt.date(2026, 11, 14))
    assert idea.errors == []
    assert "## What's done\n\nNothing yet." in text


def test_abstract_is_kept_as_one_plain_line():
    _, text = issue.build_idea(
        gh_issue(Abstract="Meetings are long:\r\n\r\n  nobody reads the minutes. # not a comment"), "OOT-0003"
    )
    meta, _ = ideas.split_front_matter(text)
    assert meta["abstract"] == "Meetings are long: nobody reads the minutes. # not a comment"


def test_issue_from_the_older_form_is_refused_for_the_missing_category_only():
    blocks = gh_issue()["body"].split("\r\n\r\n### ")
    old_form = "\r\n\r\n### ".join(
        b for b in blocks if not b.startswith(("Subject category", "Abstract"))
    )
    assert "### Idea title" in old_form and "category" not in old_form
    with pytest.raises(issue.IssueError) as caught:
        issue.build_idea({**gh_issue(), "body": old_form}, "OOT-0003")
    assert str(caught.value) == "- 'category' must be one of " + ", ".join(ideas.CATEGORIES)

from out_of_tokens import notify

BASE = """---
id: OOT-0009
authors:
  - name: Ada Example
    github: ada-example
  - name: No Account
built_from_this:
  - name: Old Thing
    url: https://old.example
    by: Someone
---
body
"""


def head(extra=""):
    return BASE.replace("    by: Someone\n", "    by: Someone\n" + extra)


def test_new_project_mentions_authors_from_main():
    text = notify.comment("OOT-0009", BASE, head("  - name: New Thing\n    by: Bo @spam\n    stage: building\n"))
    assert "@ada-example: someone is building on your idea OOT-0009." in text
    assert "- New Thing by Bo @​spam (building now)" in text
    assert notify.MARKER in text


def test_nothing_new_means_no_comment():
    assert notify.comment("OOT-0009", BASE, BASE) == ""


def test_pull_request_cannot_change_who_is_mentioned():
    evil = head("  - name: New\n    url: https://x.example\n    by: Bo\n").replace(
        "github: ada-example", "github: victim"
    )
    text = notify.comment("OOT-0009", BASE, evil)
    assert "@ada-example" in text and "@victim" not in text


def test_new_idea_file_has_no_base():
    assert notify.comment("OOT-0010", "", head("  - name: New\n    url: https://x.example\n    by: Bo\n")) != ""

import datetime as dt
import json
from pathlib import Path

from out_of_tokens import ideas, site
from out_of_tokens.__main__ import main

from .test_ideas import GOOD, PATH, TODAY, write
from .test_issue import gh_issue

SITE = "https://example.github.io/out-of-tokens"
REPO = "https://github.com/example/out-of-tokens"


def idea(text=GOOD):
    loaded = ideas.load_text(PATH, text, TODAY)
    assert loaded.errors == []
    return loaded


def test_credit_line_and_names():
    assert site.join_names(["A"]) == "A"
    assert site.join_names(["A", "B", "C"]) == "A, B and C"
    assert site.credit_line(idea(), SITE) == (
        'Based on the idea "A test idea" (OOT-0007) by Ada Example, '
        f"shared on Out of Tokens on 2026-11-01. {SITE}/ideas/OOT-0007/"
    )


def test_idea_page_escapes_hostile_content():
    hostile = GOOD.replace("A test idea", "Tom & <script>alert(1)</script>").replace(
        "\np\n",
        "\n<img src=x onerror=alert(1)> [click](javascript:alert(1)) ![pixel](https://t.example/p.gif)\n",
    )
    html = site.render_idea(idea(hostile), SITE, REPO)
    assert "<script>alert" not in html
    assert "<img" not in html
    assert 'href="javascript:' not in html
    assert "Tom &amp; &lt;script&gt;" in html


def test_build_writes_the_whole_site(tmp_path):
    built = GOOD.replace(
        "status: open",
        "status: built\nbuilt_from_this:\n  - name: Thing\n    url: https://thing.example\n"
        "    by: Bo Builder\n    date: 2026-11-10",
    )
    out = tmp_path / "site"
    (out / "stale").mkdir(parents=True)
    site.build([idea(built)], out, SITE, REPO)
    assert not (out / "stale").exists()
    for name in ("index.html", "style.css", "app.js", ".nojekyll", "badges/OOT-0007.svg"):
        assert (out / name).is_file(), name
    index = (out / "index.html").read_text()
    assert 'href="ideas/OOT-0007/"' in index and 'data-why="llm-api-cost"' in index
    page = (out / "ideas/OOT-0007/index.html").read_text()
    assert '<a rel="nofollow noopener" href="https://thing.example">Thing</a> by Bo Builder' in page
    assert f"{SITE}/badges/OOT-0007.svg" in page
    data = json.loads((out / "ideas.json").read_text())
    assert data[0]["id"] == "OOT-0007" and data[0]["submitted"] == "2026-11-01"
    assert data[0]["built_from_this"][0]["date"] == "2026-11-10"


def test_cli_validate_reports_and_fails(tmp_path, capsys):
    write(tmp_path, PATH, GOOD)
    assert main(["--root", str(tmp_path), "validate"]) == 0
    write(tmp_path, PATH, GOOD.replace("status: open", "status: nope"))
    assert main(["--root", str(tmp_path), "validate"]) == 1
    assert f"{PATH}: 'status' must be one of" in capsys.readouterr().out


def test_cli_build_refuses_invalid_ideas(tmp_path):
    write(tmp_path, PATH, GOOD.replace("status: open", "status: nope"))
    assert main(["--root", str(tmp_path), "build", "--out", str(tmp_path / "o")]) == 1
    assert not (tmp_path / "o").exists()


def test_cli_from_issue_takes_next_id_past_reserved_branches(tmp_path, monkeypatch, capsys):
    write(tmp_path, PATH, GOOD)
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"issue": gh_issue()}))
    out_file = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
    refs = "abc\trefs/heads/idea/OOT-0009-issue-4\n"
    code = main(["--root", str(tmp_path), "from-issue", "--event", str(event), "--reserved-refs", refs])
    assert code == 0
    path = "ideas/2026/OOT-0010-summaries-of-council-meetings.md"
    assert (tmp_path / path).is_file()
    assert out_file.read_text() == f"id=OOT-0010\npath={path}\nbranch=idea/OOT-0010-issue-12\n"
    assert main(["--root", str(tmp_path), "validate"]) == 0


def test_cli_from_issue_exit_2_on_bad_submission(tmp_path, capsys):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"issue": gh_issue(**{"Idea title": "Hey"})}))
    assert main(["--root", str(tmp_path), "from-issue", "--event", str(event)]) == 2
    assert "'title' must be" in capsys.readouterr().out
    assert not (tmp_path / "ideas").exists()

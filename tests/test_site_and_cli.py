import datetime as dt
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from out_of_tokens import ideas, site
from out_of_tokens.__main__ import main

from .test_ideas import GOOD, PATH, TODAY, V2, WITHDRAWN, git, write
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


# --- versions, abstract pages, categories, the feed --------------------------

DOIS = (
    'doi: "10.5281/zenodo.10"\n'
    + V2.replace("    date: 2026-11-01\n", '    date: 2026-11-01\n    doi: "10.5281/zenodo.11"\n')
    + '    doi: "10.5281/zenodo.12"\n'
)
REVISED = (
    GOOD.replace("A test idea", "A sharper idea")
    .replace("\np\n", "\nThe **new** problem.\n\nSecond paragraph.\n")
    .replace("status: open\n", "status: open\n" + DOIS)
)


def two_versions(tmp_path):
    write(tmp_path, PATH, REVISED)
    write(tmp_path, "versions/OOT-0007/v1.md", GOOD)
    (loaded,) = ideas.load_all(tmp_path, TODAY)
    assert loaded.errors == []
    return loaded


def test_abstract_falls_back_to_first_paragraphs_of_problem_and_idea(tmp_path):
    latest = site.views(two_versions(tmp_path))[-1]
    assert site.abstract_html(latest) == "<p>The <strong>new</strong> problem.</p>\n<p>i</p>"
    assert site.abstract_text(latest) == "The new problem. i"
    given = idea(GOOD.replace("status: open", "status: open\nabstract: Plain <b>text</b> & more."))
    assert site.abstract_html(site.views(given)[0]) == "<p>Plain &lt;b&gt;text&lt;/b&gt; &amp; more.</p>"


def test_main_page_shows_latest_version_with_history_and_dois(tmp_path):
    loaded = two_versions(tmp_path)
    page = site.render_idea(loaded, SITE, REPO)
    assert "<h1>A sharper idea</h1>" in page and "The <strong>new</strong> problem." in page
    assert '<h2>Abstract</h2>' in page
    assert '<a href="https://orcid.org/0000-0002-1825-0097">ORCID</a>' in page
    assert '<a href="../../categories/dev-tools/">Developer tools</a>' in page
    assert "<dt>DOI, all versions</dt><dd><a href=\"https://doi.org/10.5281/zenodo.10\">" in page
    assert '<li aria-current="true"><a href="v2/">v2</a> · 2026-11-10 · Sharper problem · ' in page
    assert '<li><a href="v1/">v1</a> · 2026-11-01 · <a href="https://doi.org/10.5281/zenodo.11">' in page
    assert f'<link rel="canonical" href="{SITE}/ideas/OOT-0007/">' in page
    assert '<meta name="citation_doi" content="10.5281/zenodo.10">' in page
    assert "print-btn" in page and ".pdf" not in page  # no PDF files in this build
    assert site.cite_as(loaded, SITE) == (
        "Ada Example (2026). A sharper idea. Out of Tokens, OOT-0007. https://doi.org/10.5281/zenodo.10"
    )
    entry = site.bibtex(loaded, SITE)
    assert "@misc{outoftokens_oot0007,\n" in entry
    assert "  doi          = {10.5281/zenodo.10},\n  url          = {https://doi.org/10.5281/zenodo.10}," in entry


def test_past_version_page_shows_the_frozen_text_and_points_to_the_latest(tmp_path):
    loaded = two_versions(tmp_path)
    first = site.views(loaded)[0]
    page = site.render_idea(loaded, SITE, REPO, first, pdf=True)
    assert "<h1>A test idea</h1>" in page and "<p>p</p>" in page and "new problem" not in page
    assert 'This is version 1, from 2026-11-01. The latest version is <a href="../">v2</a>.' in page
    assert '<link rel="stylesheet" href="../../../style.css">' in page
    assert '<a class="button" href="../v1/OOT-0007v1.pdf">Download PDF</a>' in page
    assert f'<meta name="citation_pdf_url" content="{SITE}/ideas/OOT-0007/v1/OOT-0007v1.pdf">' in page
    assert site.cite_as(loaded, SITE, first) == (
        "Ada Example (2026). A test idea. Out of Tokens, OOT-0007v1. https://doi.org/10.5281/zenodo.11"
    )
    assert "@misc{outoftokens_oot0007v1," in site.bibtex(loaded, SITE, first)
    assert "howpublished = {Out of Tokens idea OOT-0007, version 1}" in site.bibtex(loaded, SITE, first)


def test_citation_without_a_doi_uses_the_page_address():
    assert site.cite_as(idea(), SITE).endswith(f"Out of Tokens, OOT-0007. {SITE}/ideas/OOT-0007/")
    entry = site.bibtex(idea(), SITE)
    assert "doi" not in entry and f"url          = {{{SITE}/ideas/OOT-0007/}}" in entry
    assert "DOI" not in site.render_idea(idea(), SITE, REPO)


def test_withdrawn_page_shows_the_notice_and_keeps_the_text():
    page = site.render_idea(idea(GOOD.replace("status: open", WITHDRAWN)), SITE, REPO)
    assert "<strong>Withdrawn on 2026-11-12.</strong>" in page
    assert "The author found the same idea already built." in page
    assert "<p>p</p>" in page and 'class="chip status-withdrawn">Withdrawn<' in page


def test_build_writes_versions_categories_new_and_feed(tmp_path, monkeypatch):
    loaded = two_versions(tmp_path)
    printed = []

    def fake_print(html, out, chrome):
        printed.append((html.parent.name, out.name, chrome))
        out.write_bytes(b"%PDF-fake")

    monkeypatch.setattr(site, "html_to_pdf", fake_print)
    out = tmp_path / "site"
    site.build([loaded], out, SITE, REPO, chrome="/fake/chrome")
    for name in (
        "ideas/OOT-0007/index.html",
        "ideas/OOT-0007/v1/index.html",
        "ideas/OOT-0007/v2/index.html",
        "ideas/OOT-0007/v1/OOT-0007v1.pdf",
        "ideas/OOT-0007/v2/OOT-0007v2.pdf",
        "badges/OOT-0007.svg",
        "ideas.json",
        "new/index.html",
        "feed.xml",
        "categories/index.html",
        *(f"categories/{key}/index.html" for key in ideas.CATEGORIES),
    ):
        assert (out / name).is_file(), name
    assert printed == [("v1", "OOT-0007v1.pdf", "/fake/chrome"), ("v2", "OOT-0007v2.pdf", "/fake/chrome")]
    assert 'href="v2/OOT-0007v2.pdf">Download PDF' in (out / "ideas/OOT-0007/index.html").read_text()

    index = (out / "index.html").read_text()
    assert 'data-category="dev-tools"' in index and 'id="f-category"' in index
    assert "OOT-0007 (v2)" in index
    assert 'href="../../ideas/OOT-0007/"' in (out / "categories/dev-tools/index.html").read_text()
    assert "No ideas in this category yet." in (out / "categories/health/index.html").read_text()
    assert "1 idea</span>" in (out / "categories/index.html").read_text()

    new = (out / "new/index.html").read_text()
    assert new.index("OOT-0007v2 · Version 2: Sharper problem") < new.index("OOT-0007v1 · New idea")
    assert 'href="../ideas/OOT-0007/v1/">A test idea</a>' in new

    atom = "{http://www.w3.org/2005/Atom}"
    feed = ET.fromstring((out / "feed.xml").read_text())
    entries = feed.findall(atom + "entry")
    assert [e.find(atom + "id").text for e in entries] == [
        f"{SITE}/ideas/OOT-0007/v2/",
        f"{SITE}/ideas/OOT-0007/v1/",
    ]
    assert entries[0].find(atom + "title").text == "OOT-0007v2: A sharper idea (version 2)"
    assert entries[0].find(atom + "updated").text == "2026-11-10T00:00:00Z"
    assert entries[0].find(atom + "summary").text == "The new problem. i"
    assert entries[0].find(atom + "category").get("term") == "dev-tools"
    assert feed.find(atom + "updated").text == "2026-11-10T00:00:00Z"
    assert feed.find(atom + "link[@rel='self']").get("href") == f"{SITE}/feed.xml"

    (entry,) = json.loads((out / "ideas.json").read_text())
    assert entry["doi"] == "10.5281/zenodo.10" and entry["category"] == "dev-tools"
    assert entry["abstract"] == "The new problem. i"
    assert entry["versions"] == [
        {"version": 1, "date": "2026-11-01", "url": f"{SITE}/ideas/OOT-0007/v1/",
         "doi": "10.5281/zenodo.11", "pdf": f"{SITE}/ideas/OOT-0007/v1/OOT-0007v1.pdf"},
        {"version": 2, "date": "2026-11-10", "url": f"{SITE}/ideas/OOT-0007/v2/", "note": "Sharper problem",
         "doi": "10.5281/zenodo.12", "pdf": f"{SITE}/ideas/OOT-0007/v2/OOT-0007v2.pdf"},
    ]
    # Keys that existed before versions were added are still there.
    assert {"id", "title", "authors", "submitted", "status", "tags", "url", "source", "credit"} <= set(entry)


def test_empty_feed_is_still_valid_xml():
    feed = ET.fromstring(site.render_feed([], SITE))
    assert feed.find("{http://www.w3.org/2005/Atom}updated").text


def test_feed_and_pages_escape_hostile_titles(tmp_path):
    hostile = idea(GOOD.replace("A test idea", "Tom & <script>alert(1)</script> ]]>"))
    feed = ET.fromstring(site.render_feed([hostile], SITE))
    assert "<script>" in feed.find("{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}title").text
    assert "<script>alert" not in site.render_new([hostile], REPO)
    assert "<script>alert" not in site.render_category("dev-tools", [hostile], REPO)


def test_cli_build_without_a_browser_has_no_pdf_and_on_fails(tmp_path, monkeypatch, capsys):
    from out_of_tokens import pdf

    write(tmp_path, PATH, GOOD)
    monkeypatch.setattr(pdf, "find_chrome", lambda: None)
    out = tmp_path / "o"
    assert main(["--root", str(tmp_path), "build", "--out", str(out), "--pdf", "auto"]) == 0
    assert "without PDF files" in capsys.readouterr().out
    assert (out / "ideas/OOT-0007/v1/index.html").is_file()
    assert not list(out.rglob("*.pdf"))
    assert main(["--root", str(tmp_path), "build", "--out", str(out), "--pdf", "on"]) == 1


def test_cli_build_auto_falls_back_when_printing_fails(tmp_path, monkeypatch, capsys):
    from out_of_tokens import pdf

    def broken(html, out, chrome):
        raise RuntimeError("could not print index.html to PDF: boom")

    write(tmp_path, PATH, GOOD)
    monkeypatch.setattr(pdf, "find_chrome", lambda: "/fake/chrome")
    monkeypatch.setattr(site, "html_to_pdf", broken)
    out = tmp_path / "o"
    assert main(["--root", str(tmp_path), "build", "--out", str(out), "--pdf", "auto"]) == 0
    assert "PDF files were left out" in capsys.readouterr().out
    assert "print-btn" in (out / "ideas/OOT-0007/index.html").read_text()
    assert main(["--root", str(tmp_path), "build", "--out", str(out), "--pdf", "on"]) == 1


def test_cli_revise_freezes_the_old_version_and_passes_the_base_check(tmp_path, capsys):
    write(tmp_path, PATH, GOOD)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    args = ["--root", str(tmp_path)]
    assert main([*args, "revise", "OOT-0007", "--note", "Sharper  problem", "--date", "2026-11-10"]) == 0
    assert "Kept version 1 at versions/OOT-0007/v1.md" in capsys.readouterr().out
    assert (tmp_path / "versions/OOT-0007/v1.md").read_text() == GOOD
    text = (tmp_path / PATH).read_text()
    meta, _ = ideas.split_front_matter(text)
    assert meta["versions"] == [
        {"version": 1, "date": dt.date(2026, 11, 1)},
        {"version": 2, "date": dt.date(2026, 11, 10), "note": "Sharper problem"},
    ]
    # Until the author edits the text, the new version is refused as empty.
    assert main([*args, "validate", "--base", "main"]) == 1
    assert "same title, abstract and body" in capsys.readouterr().out
    write(tmp_path, PATH, text.replace("\np\n", "\nbetter\n"))
    assert main([*args, "validate", "--base", "main"]) == 0
    assert main([*args, "list-versions"]) == 0
    assert capsys.readouterr().out.endswith(
        f"OOT-0007 1 versions/OOT-0007/v1.md\nOOT-0007 2 {PATH}\n"
    )


def test_cli_revise_refuses_unknown_and_withdrawn_ideas(tmp_path, capsys):
    write(tmp_path, PATH, GOOD.replace("status: open", WITHDRAWN))
    args = ["--root", str(tmp_path), "revise", "--note", "x"]
    assert main([*args, "OOT-0099"]) == 1
    assert main([*args, "OOT-0007"]) == 1
    assert "withdrawn" in capsys.readouterr().err
    assert not (tmp_path / "versions").exists()


def test_a_real_browser_prints_a_pdf_when_one_is_installed(tmp_path):
    import pytest

    from out_of_tokens import pdf

    chrome = pdf.find_chrome()
    if not chrome:
        pytest.skip("no Chrome or Chromium on this machine")
    out = tmp_path / "site"
    site.build([idea()], out, SITE, REPO, chrome=chrome)
    data = (out / "ideas/OOT-0007/v1/OOT-0007v1.pdf").read_bytes()
    assert data.startswith(b"%PDF-") and len(data) > 3000


def test_building_now_is_shown_apart_from_finished_projects(tmp_path):
    text = GOOD.replace(
        "status: open",
        "status: being-built\nbuilt_from_this:\n  - name: Early prototype\n    by: Bo Builder\n"
        "    stage: building\n    date: 2026-11-14\n  - name: Thing\n    url: https://thing.example\n"
        "    by: Al Ready",
    )
    out = tmp_path / "site"
    site.build([idea(text)], out, SITE, REPO)
    page = (out / "ideas/OOT-0007/index.html").read_text()
    now = page.split("<h2>Building now</h2>")[1].split("</section>")[0]
    done = page.split("<h2>Built from this</h2>")[1].split("</section>")[0]
    assert "Early prototype by Bo Builder (since 2026-11-14)" in now and "Thing" not in now
    assert "Thing</a> by Al Ready" in done and "Early prototype" not in done
    assert '<span class="chip building">1 building</span>' in (out / "index.html").read_text()

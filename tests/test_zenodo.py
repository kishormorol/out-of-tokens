"""Zenodo deposits, against a small in-memory stand-in for the Zenodo API.

No test here opens a network connection: every call goes to FakeZenodo.
"""

import datetime as dt
import json
import re

import pytest

from out_of_tokens import ideas, pdf, site, zenodo
from out_of_tokens.__main__ import main

from .test_ideas import GOOD, PATH, TODAY, V2, WITHDRAWN, write

SITE = "https://example.github.io/out-of-tokens"
REPO = "https://github.com/example/out-of-tokens"
TOKEN = "s3cret-token-value"
V1_PAGE = f"{SITE}/ideas/OOT-0007/v1/"


class FakeZenodo:
    """Enough of Zenodo's deposit API to check what the depositor sends."""

    def __init__(self, api=zenodo.PRODUCTION, prefix="10.5281", fail_on=None):
        self.api, self.prefix, self.fail_on = api, prefix, fail_on
        self.records, self.files, self.calls, self.next_id = {}, {}, [], 100

    def __call__(self, method, url, headers, body):
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in url
        assert url.startswith(self.api + "/"), url
        path = url[len(self.api) :].split("?")[0]
        self.calls.append(f"{method} {path}")
        if self.fail_on and re.search(self.fail_on, f"{method} {path}"):
            return 500, {"message": "the stand-in was told to fail"}
        payload = json.loads(body) if body and headers.get("Content-Type") == "application/json" else None

        if path == "/deposit/depositions" and method == "GET":
            return 200, list(self.records.values())
        if path == "/deposit/depositions" and method == "POST":
            return 201, self._draft(payload["metadata"], concept=None)
        match = re.fullmatch(r"/files/b(\d+)/(.+)", path)
        if match and method == "PUT":
            self.files[int(match[1])][match[2]] = body
            return 201, {"key": match[2]}
        match = re.fullmatch(r"/deposit/depositions/(\d+)(/.*)?", path)
        record, rest = self.records[int(match[1])], match[2] or ""
        if rest == "" and method == "GET":
            return 200, record
        if rest == "" and method == "PUT":
            if record["submitted"]:
                return 403, {"message": "published records cannot be edited"}
            record["metadata"] = {**payload["metadata"], "prereserve_doi": record["metadata"]["prereserve_doi"]}
            return 200, record
        if rest == "/files" and method == "GET":
            return 200, [{"id": name, "filename": name} for name in self.files[record["id"]]]
        if rest.startswith("/files/") and method == "DELETE":
            del self.files[record["id"]][rest[len("/files/") :]]
            return 204, None
        if rest == "/actions/publish":
            if not self.files[record["id"]]:
                return 400, {"message": "a record needs at least one file"}
            record.update(
                submitted=True,
                state="done",
                doi=f"{self.prefix}/zenodo.{record['id']}",
                conceptdoi=f"{self.prefix}/zenodo.{record['conceptrecid']}",
            )
            return 202, record
        if rest == "/actions/newversion":
            draft = self._draft(dict(record["metadata"]), concept=record["conceptrecid"])
            self.files[draft["id"]] = dict(self.files[record["id"]])
            return 201, {**record, "links": {**record["links"], "latest_draft": draft["links"]["self"]}}
        raise AssertionError(f"unexpected call {method} {path}")

    def _draft(self, metadata, concept):
        self.next_id += 2
        number = self.next_id
        record = {
            "id": number,
            "conceptrecid": str(concept or number - 1),
            "submitted": False,
            "state": "unsubmitted",
            "metadata": {**metadata, "prereserve_doi": {"doi": f"{self.prefix}/zenodo.{number}", "recid": number}},
            "links": {
                "self": f"{self.api}/deposit/depositions/{number}",
                "bucket": f"{self.api}/files/b{number}",
            },
        }
        self.records[number] = record
        self.files[number] = {}
        return record

    def published(self):
        return [r for r in self.records.values() if r["submitted"]]


def load(tmp_path, text=GOOD, frozen=None):
    write(tmp_path, PATH, text)
    for number, old in (frozen or {}).items():
        write(tmp_path, f"versions/OOT-0007/v{number}.md", old)
    (idea,) = ideas.load_all(tmp_path, TODAY)
    assert idea.errors == []
    return idea


def files_for(reserved):
    return {"OOT-0007.md": f"text with {reserved}".encode()}


def deposit(fake, idea, number, previous=None, sandbox=False):
    client = zenodo.Client(TOKEN, sandbox=sandbox, http=fake)
    view = site.views(idea)[number - 1]
    return zenodo.deposit_version(
        client, idea, view, SITE, client.list_depositions(), previous, files_for
    )


def test_metadata_payload(tmp_path):
    idea = load(tmp_path, GOOD.replace("status: open", "status: open\nabstract: A <short> abstract."))
    assert zenodo.build_metadata(idea, site.views(idea)[0], SITE) == {
        "upload_type": "publication",
        "publication_type": "preprint",
        "title": "A test idea",
        "creators": [{"name": "Ada Example", "orcid": "0000-0002-1825-0097"}],
        "description": (
            "<p>A &lt;short&gt; abstract.</p>\n"
            "<p>This is version 1 of idea OOT-0007 on Out of Tokens, a public registry of ideas "
            "that their authors could not finish. Anyone may build it. If you do, please credit "
            f'the authors. Full text and later versions: <a href="{V1_PAGE}">{V1_PAGE}</a></p>'
        ),
        "publication_date": "2026-11-01",
        "version": "v1",
        "access_right": "open",
        "license": "cc-by-4.0",
        "keywords": ["testing", "example-tag", "Developer tools", "Out of Tokens"],
        "related_identifiers": [
            {"identifier": V1_PAGE, "relation": "isIdenticalTo"},
            {"identifier": SITE + "/", "relation": "isPartOf"},
        ],
        "notes": "Out of Tokens OOT-0007v1. Estimated cost to build: USD 100",
    }


def test_metadata_without_orcid_or_abstract_falls_back(tmp_path):
    text = GOOD.replace("    orcid: 0000-0002-1825-0097\n", "").replace("\np\n", "\nThe *problem*.\n")
    idea = load(tmp_path, text)
    payload = zenodo.build_metadata(idea, site.views(idea)[0], SITE)
    assert payload["creators"] == [{"name": "Ada Example"}]
    assert payload["description"].startswith("<p>The <em>problem</em>.</p>\n<p>i</p>\n<p>This is version 1")


def test_first_version_is_created_filled_and_published(tmp_path):
    fake = FakeZenodo()
    result = deposit(fake, load(tmp_path), 1)
    assert result == zenodo.Deposit("10.5281/zenodo.102", "10.5281/zenodo.101", reused=False)
    assert fake.calls == [
        "GET /deposit/depositions",
        "POST /deposit/depositions",
        "GET /deposit/depositions/102/files",
        "PUT /files/b102/OOT-0007.md",
        "POST /deposit/depositions/102/actions/publish",
    ]
    # The files were made after Zenodo reserved the DOI, so they can print it.
    assert fake.files[102] == {"OOT-0007.md": b"text with 10.5281/zenodo.102"}
    assert fake.records[102]["metadata"]["title"] == "A test idea"


def test_same_version_is_never_deposited_twice(tmp_path):
    fake = FakeZenodo()
    idea = load(tmp_path)
    first = deposit(fake, idea, 1)
    fake.calls.clear()
    again = deposit(fake, idea, 1)
    assert again == zenodo.Deposit(first.doi, first.concept_doi, reused=True)
    assert fake.calls == ["GET /deposit/depositions"]  # looked, found it, sent nothing
    assert len(fake.published()) == 1


def test_a_draft_left_by_a_failed_run_is_finished_not_duplicated(tmp_path):
    idea = load(tmp_path)
    fake = FakeZenodo(fail_on="publish")
    with pytest.raises(zenodo.ZenodoError):
        deposit(fake, idea, 1)
    assert len(fake.records) == 1 and not fake.published()
    fake.fail_on = None
    result = deposit(fake, idea, 1)
    assert len(fake.records) == 1 and result.doi == "10.5281/zenodo.102" and not result.reused
    assert "POST /deposit/depositions" not in fake.calls[5:]


def test_second_version_is_a_new_version_of_the_same_zenodo_record(tmp_path):
    fake = FakeZenodo()
    first = deposit(fake, load(tmp_path), 1)
    revised = GOOD.replace("\np\n", "\nbetter\n").replace("status: open\n", "status: open\n" + V2)
    idea = load(tmp_path, revised, frozen={1: GOOD})
    fake.calls.clear()
    second = deposit(fake, idea, 2, previous=first.doi)
    assert second == zenodo.Deposit("10.5281/zenodo.104", first.concept_doi, reused=False)
    assert fake.calls == [
        "GET /deposit/depositions",
        "POST /deposit/depositions/102/actions/newversion",
        "GET /deposit/depositions/104",
        "PUT /deposit/depositions/104",
        "GET /deposit/depositions/104/files",
        "DELETE /deposit/depositions/104/files/OOT-0007.md",  # the copy of the v1 file goes
        "PUT /files/b104/OOT-0007.md",
        "POST /deposit/depositions/104/actions/publish",
    ]
    meta = fake.records[104]["metadata"]
    assert meta["version"] == "v2" and meta["publication_date"] == "2026-11-10"
    assert meta["related_identifiers"][0]["identifier"] == f"{SITE}/ideas/OOT-0007/v2/"
    # The first record still stands for v1 only.
    assert zenodo.find_existing(list(fake.records.values()), V1_PAGE)["id"] == 102


def test_second_version_needs_the_doi_of_the_first(tmp_path):
    revised = GOOD.replace("\np\n", "\nbetter\n").replace("status: open\n", "status: open\n" + V2)
    idea = load(tmp_path, revised, frozen={1: GOOD})
    with pytest.raises(zenodo.ZenodoError, match="the version before it has no DOI"):
        deposit(FakeZenodo(), idea, 2)
    with pytest.raises(zenodo.ZenodoError, match="not a Zenodo DOI"):
        deposit(FakeZenodo(), idea, 2, previous="10.1234/elsewhere")


def test_concept_doi_is_built_from_the_concept_record_when_zenodo_omits_it():
    reply = {"doi": "10.5281/zenodo.102", "conceptrecid": "101"}
    assert zenodo._result(reply, False).concept_doi == "10.5281/zenodo.101"
    with pytest.raises(zenodo.ZenodoError, match="returned no DOI"):
        zenodo._result({"conceptrecid": "101"}, False)


def test_errors_never_carry_the_token_and_calls_stay_on_the_zenodo_host(tmp_path):
    fake = FakeZenodo(fail_on="POST /deposit/depositions$")
    with pytest.raises(zenodo.ZenodoError) as caught:
        deposit(fake, load(tmp_path), 1)
    assert TOKEN not in str(caught.value) and "returned 500" in str(caught.value)
    client = zenodo.Client(TOKEN, http=fake)
    with pytest.raises(zenodo.ZenodoError, match="refusing to call"):
        client.get("https://evil.example/api/deposit/depositions/1")
    draft = FakeZenodo()._draft({}, None)
    draft["links"]["bucket"] = "https://zenodo.org.evil.example/api/files/b"
    with pytest.raises(zenodo.ZenodoError, match="refusing to call"):
        zenodo.Client(TOKEN, http=lambda *a: (200, [])).replace_files(draft, {"a.md": b"x"})


def test_sandbox_client_uses_the_sandbox_host(tmp_path):
    fake = FakeZenodo(api=zenodo.SANDBOX, prefix="10.5072")
    result = deposit(fake, load(tmp_path), 1, sandbox=True)
    assert zenodo.is_sandbox_doi(result.doi) and not zenodo.is_sandbox_doi("10.5281/zenodo.1")


def test_pending_skips_examples_withdrawn_and_versions_with_a_doi(tmp_path):
    def variant(number, change=lambda t: t):
        text = change(GOOD.replace("OOT-0007", f"OOT-000{number}"))
        write(tmp_path, f"ideas/2026/OOT-000{number}-x.md", text)

    variant(1, lambda t: t.replace("status: open", "status: open\nexample: true"))
    variant(2, lambda t: t.replace("status: open", WITHDRAWN))
    variant(3, lambda t: t.replace("status: open", 'status: open\nversions: [{version: 1, date: 2026-11-01, doi: "10.5281/zenodo.5"}]'))
    variant(4)
    variant(5, lambda t: t.replace("\np\n", "\nbetter\n").replace("status: open\n", "status: open\n" + V2))
    write(tmp_path, "versions/OOT-0005/v1.md", GOOD.replace("OOT-0007", "OOT-0005"))
    variant(6, lambda t: t.replace("\np\n", "\nbetter\n").replace(
        "status: open\n", "status: open\n" + V2.replace('note: "Sharper problem"', 'note: x\n    doi: "10.5281/zenodo.9"')))
    write(tmp_path, "versions/OOT-0006/v1.md", GOOD.replace("OOT-0007", "OOT-0006"))
    loaded = ideas.load_all(tmp_path, TODAY)
    assert {i.path: i.errors for i in loaded if i.errors} == {}
    todo, skipped = zenodo.pending(loaded)
    assert [(i.id, n) for i, n in todo] == [("OOT-0004", 1), ("OOT-0005", 1), ("OOT-0005", 2)]
    assert [s.split(":")[0] for s in skipped] == ["OOT-0001", "OOT-0002", "OOT-0006"]
    assert "example entry" in skipped[0] and "withdrawn" in skipped[1] and "later version" in skipped[2]


def test_write_back_adds_dois_and_keeps_the_ones_already_there():
    out = zenodo.apply_dois(GOOD, {1: "10.5281/zenodo.102"}, "10.5281/zenodo.101")
    meta, body = ideas.split_front_matter(out)
    assert meta["doi"] == "10.5281/zenodo.101"
    assert meta["versions"] == [{"version": 1, "date": dt.date(2026, 11, 1), "doi": "10.5281/zenodo.102"}]
    assert body == ideas.split_front_matter(GOOD)[1]
    assert ideas.load_text(PATH, out, TODAY).errors == []
    assert ideas.revision_changes(*ideas.split_front_matter(GOOD), ideas.load_text(PATH, out, TODAY)) == []

    v2 = out.replace("---\n\n## Problem", '  - version: 2\n    date: 2026-11-10\n    note: "n"\n---\n\n## Problem')
    out2 = zenodo.apply_dois(v2, {1: "10.5281/zenodo.999", 2: "10.5281/zenodo.104"}, "10.5281/zenodo.888")
    meta2, _ = ideas.split_front_matter(out2)
    assert meta2["doi"] == "10.5281/zenodo.101"  # a DOI is never overwritten
    assert [v["doi"] for v in meta2["versions"]] == ["10.5281/zenodo.102", "10.5281/zenodo.104"]


# --- the command, as the workflow runs it -----------------------------------


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Run 'zenodo' in a repository with one idea, against a FakeZenodo."""
    write(tmp_path, PATH, GOOD)
    monkeypatch.delenv("ZENODO_TOKEN", raising=False)
    monkeypatch.delenv("ZENODO_SANDBOX", raising=False)
    monkeypatch.setattr(pdf, "find_chrome", lambda: None)
    state = {"fake": FakeZenodo(), "root": tmp_path}

    def no_network(*args):
        raise AssertionError("a test tried to reach the network")

    monkeypatch.setattr(zenodo, "urllib_http", no_network)

    def run(*extra, token=TOKEN, sandbox=None, fake=None):
        if fake is not None:
            state["fake"] = fake
        monkeypatch.setattr(zenodo, "urllib_http", state["fake"] if token else no_network)
        if token:
            monkeypatch.setenv("ZENODO_TOKEN", token)
        if sandbox:
            monkeypatch.setenv("ZENODO_SANDBOX", sandbox)
        return main(["--root", str(tmp_path), "zenodo", "--site-url", SITE, "--repo-url", REPO, *extra])

    state["run"] = run
    return state


def test_cli_without_a_token_does_nothing_and_succeeds(cli, capsys):
    assert cli["run"](token=None) == 0
    assert "ZENODO_TOKEN is not set, so nothing was deposited" in capsys.readouterr().out
    assert (cli["root"] / PATH).read_text() == GOOD


def test_cli_dry_run_prints_the_payload_without_a_token(cli, capsys):
    assert cli["run"]("--dry-run", token=None) == 0
    out = capsys.readouterr().out
    assert "would deposit OOT-0007v1:" in out and '"publication_type": "preprint"' in out
    assert (cli["root"] / PATH).read_text() == GOOD


def test_cli_deposits_writes_dois_back_and_is_idempotent(cli, capsys):
    assert cli["run"]() == 0
    out = capsys.readouterr().out
    assert "OOT-0007v1: deposited, DOI 10.5281/zenodo.102" in out and TOKEN not in out
    text = (cli["root"] / PATH).read_text()
    meta, _ = ideas.split_front_matter(text)
    assert meta["doi"] == "10.5281/zenodo.101" and meta["versions"][0]["doi"] == "10.5281/zenodo.102"
    assert main(["--root", str(cli["root"]), "validate"]) == 0
    assert list(cli["fake"].files[102]) == ["OOT-0007v1.md"]
    assert cli["fake"].files[102]["OOT-0007v1.md"] == GOOD.encode()

    # Run again with the DOI on file: nothing is sent at all.
    cli["fake"].calls.clear()
    assert cli["run"]() == 0
    assert "Nothing to deposit." in capsys.readouterr().out and cli["fake"].calls == []

    # Run again as if the write-back was never merged: the record is found, not repeated.
    write(cli["root"], PATH, GOOD)
    assert cli["run"]() == 0
    assert "OOT-0007v1: was already on Zenodo, DOI 10.5281/zenodo.102" in capsys.readouterr().out
    assert len(cli["fake"].published()) == 1
    assert (cli["root"] / PATH).read_text() == text


def test_cli_deposits_two_versions_in_one_run_in_order(cli, capsys):
    revised = GOOD.replace("\np\n", "\nbetter\n").replace("status: open\n", "status: open\n" + V2)
    write(cli["root"], PATH, revised)
    write(cli["root"], "versions/OOT-0007/v1.md", GOOD)
    assert cli["run"]() == 0
    meta, _ = ideas.split_front_matter((cli["root"] / PATH).read_text())
    assert [v["doi"] for v in meta["versions"]] == ["10.5281/zenodo.102", "10.5281/zenodo.104"]
    assert meta["doi"] == "10.5281/zenodo.101"
    assert cli["fake"].files[102]["OOT-0007v1.md"] == GOOD.encode()  # v1 is the frozen copy
    # v2 is the idea file as it stands, which by then carries the DOI of v1.
    (name, sent), = cli["fake"].files[104].items()
    assert name == "OOT-0007v2.md" and b"\nbetter\n" in sent and b"10.5281/zenodo.102" in sent
    assert main(["--root", str(cli["root"]), "validate"]) == 0


def test_cli_on_the_sandbox_never_writes_to_the_repository(cli, capsys):
    fake = FakeZenodo(api=zenodo.SANDBOX, prefix="10.5072")
    assert cli["run"](sandbox="true", fake=fake) == 0
    out = capsys.readouterr().out
    assert "Depositing on https://sandbox.zenodo.org" in out
    assert "sandbox DOI 10.5072/zenodo.102" in out and "not written to the repository" in out
    assert (cli["root"] / PATH).read_text() == GOOD
    assert len(fake.published()) == 1


def test_cli_reports_a_failed_deposit_and_keeps_going(cli, capsys):
    write(cli["root"], "ideas/2026/OOT-0008-other.md", GOOD.replace("OOT-0007", "OOT-0008"))
    fake = FakeZenodo(fail_on="POST /deposit/depositions/102/actions/publish")
    assert cli["run"](fake=fake) == 1
    captured = capsys.readouterr()
    assert "error: OOT-0007v1:" in captured.err and TOKEN not in captured.err + captured.out
    assert "OOT-0008v1: deposited" in captured.out
    assert (cli["root"] / PATH).read_text() == GOOD
    assert "doi" in ideas.split_front_matter((cli["root"] / "ideas/2026/OOT-0008-other.md").read_text())[0]


def test_cli_uploads_a_pdf_that_prints_the_reserved_doi(cli, monkeypatch):
    monkeypatch.setattr(pdf, "find_chrome", lambda: "/fake/chrome")
    seen = {}

    def fake_pdf(idea, view, site_url, repo_url, chrome):
        seen["doi"] = view.doi
        return b"%PDF-fake"

    monkeypatch.setattr(site, "version_pdf", fake_pdf)
    assert cli["run"]() == 0
    assert seen["doi"] == "10.5281/zenodo.102"
    assert cli["fake"].files[102]["OOT-0007v1.pdf"] == b"%PDF-fake"


def test_cli_refuses_placeholder_addresses(cli, monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert main(["--root", str(cli["root"]), "zenodo"]) == 1
    assert "real addresses" in capsys.readouterr().err

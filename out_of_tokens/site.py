"""Build the static site from the ideas folder.

Output is plain HTML with relative links, so it works under any base path
(a GitHub Pages project site, a custom domain, or a local file server).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from html import escape, unescape
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from markdown_it import MarkdownIt

from .ideas import CATEGORIES, Idea, section_text
from .pdf import html_to_pdf

STATIC_DIR = Path(__file__).parent / "static"

WHY_LABELS = {
    "llm-api-cost": "LLM API cost",
    "gpu-cost": "GPU cost",
    "compute-cost": "Compute cost",
    "data-cost": "Data cost",
    "hosting-cost": "Hosting cost",
    "funding": "Funding",
    "time": "Time",
    "team": "Team",
    "other": "Other",
}
STATUS_LABELS = {
    "open": "Open",
    "being-built": "Being built",
    "built": "Built",
    "withdrawn": "Withdrawn",
}
FEED = "feed.xml"  # the Atom feed; this path is public and must not change


@dataclass
class View:
    """One version of an idea, ready to show."""

    version: int
    date: dt.date
    note: str | None
    doi: str | None
    title: str
    abstract: str | None
    body: str
    latest: bool


def views(idea: Idea) -> list[View]:
    """Every version of ``idea``, oldest first. Dates, notes and DOIs come from
    the idea file; the title, abstract and body of a past version come from its
    frozen copy."""
    out, last = [], idea.version
    for entry in idea.versions:
        number = entry["version"]
        meta, body = (idea.meta, idea.body) if number == last else idea.frozen[number]
        abstract = meta.get("abstract")
        out.append(
            View(
                version=number,
                date=entry["date"],
                note=entry.get("note"),
                doi=entry.get("doi"),
                title=str(meta.get("title") or idea.meta["title"]),
                abstract=abstract if isinstance(abstract, str) else None,
                body=body,
                latest=number == last,
            )
        )
    return out


def abstract_html(view: View) -> str:
    """The abstract as HTML. Without an 'abstract' field it is the first
    paragraph of Problem followed by the first paragraph of Idea."""
    if view.abstract:
        parts = re.split(r"\n\s*\n", view.abstract.strip())
        return "\n".join(f"<p>{escape(' '.join(p.split()))}</p>" for p in parts)
    firsts = []
    for name in ("Problem", "Idea"):
        text = section_text(view.body, name)
        if text:
            firsts.append(re.split(r"\n\s*\n", text)[0])
    return _markdown().render("\n\n".join(firsts)).strip()


def abstract_text(view: View) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", abstract_html(view))).split())


def _markdown() -> MarkdownIt:
    # Idea bodies come from strangers. Raw HTML is escaped, images are off (no
    # tracking pixels or hotlinking), and markdown-it refuses javascript: links.
    md = MarkdownIt("commonmark", {"html": False}).enable("table").disable("image")

    def link_open(self, tokens, idx, options, env):
        tokens[idx].attrSet("rel", "nofollow noopener")
        return self.renderToken(tokens, idx, options, env)

    md.add_render_rule("link_open", link_open)
    return md


def join_names(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def idea_url(idea: Idea, site_url: str) -> str:
    return f"{site_url.rstrip('/')}/ideas/{idea.id}/"


def version_url(idea: Idea, version: int, site_url: str) -> str:
    return f"{idea_url(idea, site_url)}v{version}/"


def pdf_name(idea: Idea, version: int) -> str:
    return f"{idea.id}v{version}.pdf"


def cite_as(idea: Idea, site_url: str, view: View | None = None) -> str:
    """A plain citation. For the main page it names the idea and uses the DOI
    for all versions; for a version page it names that version and its DOI."""
    names = join_names([a["name"] for a in idea.meta["authors"]])
    if view:
        doi, label, url = view.doi, f"{idea.id}v{view.version}", version_url(idea, view.version, site_url)
        year, title = view.date.year, view.title
    else:
        latest = views(idea)[-1]
        doi, label, url = idea.meta.get("doi") or latest.doi, idea.id, idea_url(idea, site_url)
        year, title = idea.meta["submitted"].year, latest.title
    where = f"https://doi.org/{doi}" if doi else url
    return f"{names} ({year}). {title}. Out of Tokens, {label}. {where}"


def credit_line(idea: Idea, site_url: str) -> str:
    names = join_names([a["name"] for a in idea.meta["authors"]])
    return (
        f'Based on the idea "{idea.meta["title"]}" ({idea.id}) by {names}, '
        f"shared on Out of Tokens on {idea.meta['submitted']}. {idea_url(idea, site_url)}"
    )


def badge_markdown(idea: Idea, site_url: str) -> str:
    base = site_url.rstrip("/")
    return (
        f"[![Built from Out of Tokens idea {idea.id}]({base}/badges/{idea.id}.svg)]"
        f"({idea_url(idea, site_url)})"
    )


def bibtex(idea: Idea, site_url: str, view: View | None = None) -> str:
    def tex(text: str) -> str:
        for ch in "\\&%$#_{}":
            text = text.replace(ch, "" if ch == "\\" else "\\" + ch)
        return text

    authors = " and ".join(tex(a["name"]) for a in idea.meta["authors"])
    key = "outoftokens_" + idea.id.lower().replace("-", "")
    how = f"Out of Tokens idea {idea.id}"
    if view:
        doi, url = view.doi, version_url(idea, view.version, site_url)
        year, title = view.date.year, view.title
        key += f"v{view.version}"
        how += f", version {view.version}"
    else:
        latest = views(idea)[-1]
        doi, url = idea.meta.get("doi") or latest.doi, idea_url(idea, site_url)
        year, title = idea.meta["submitted"].year, latest.title
    fields = [
        ("author", authors),
        ("title", tex(title)),
        ("year", str(year)),
        ("howpublished", how),
    ]
    if doi:
        fields += [("doi", doi), ("url", f"https://doi.org/{doi}")]
    else:
        fields.append(("url", url))
    fields.append(("note", "Idea text licensed CC BY 4.0"))
    body = ",\n".join(f"  {name:<12} = {{{value}}}" for name, value in fields)
    return f"@misc{{{key},\n{body}\n}}"


def badge_svg(idea_id: str) -> str:
    left, right = "built from idea", idea_id
    lw, rw = 6.2 * len(left) + 12, 6.8 * len(right) + 12
    width = lw + rw
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="20" '
        f'role="img" aria-label="{left}: {right}">'
        f"<title>{left}: {right}</title>"
        f'<rect width="{width:.0f}" height="20" rx="3" fill="#3b3b3b"/>'
        f'<rect x="{lw:.0f}" width="{rw:.0f}" height="20" rx="3" fill="#0b6e4f"/>'
        f'<rect x="{lw:.0f}" width="4" height="20" fill="#0b6e4f"/>'
        '<g fill="#fff" text-anchor="middle" '
        'font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        f'<text x="{lw / 2:.1f}" y="14">{left}</text>'
        f'<text x="{lw + rw / 2:.1f}" y="14">{right}</text>'
        "</g></svg>\n"
    )


def _page(title: str, root: str, content: str, repo_url: str, head: str = "") -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="stylesheet" href="{root}style.css">
<link rel="alternate" type="application/atom+xml" title="Out of Tokens: new ideas and versions" href="{root}{FEED}">
{head}</head>
<body>
<header class="site">
  <a class="brand" href="{root or './'}">Out of Tokens</a>
  <nav>
    <a href="{root or './'}">Ideas</a>
    <a href="{root}new/">New</a>
    <a href="{root}categories/">Categories</a>
    <a href="{escape(repo_url)}/issues/new?template=idea.yml">Share an idea</a>
    <a href="{escape(repo_url)}/blob/main/ATTRIBUTION.md">Giving credit</a>
    <a href="{escape(repo_url)}">GitHub</a>
  </nav>
</header>
<main>
{content}
</main>
<footer class="site">
  Idea text is licensed <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>;
  code is MIT. Ideas themselves cannot be owned: crediting the people who had them is a
  norm this project asks for, not something a licence can force.
  <a href="{root}{FEED}">Atom feed</a>.
</footer>
<script src="{root}app.js"></script>
</body>
</html>
"""


def _author_html(author: dict) -> str:
    out = escape(author["name"])
    links = []
    if "github" in author:
        links.append(f'<a href="https://github.com/{escape(author["github"])}">GitHub</a>')
    if "orcid" in author:
        links.append(f'<a href="https://orcid.org/{escape(author["orcid"])}">ORCID</a>')
    if "url" in author:
        links.append(f'<a rel="nofollow noopener" href="{escape(author["url"])}">web</a>')
    return out + (f' <span class="links">({", ".join(links)})</span>' if links else "")


def _chips(idea: Idea) -> str:
    meta = idea.meta
    chips = [f'<span class="chip status-{meta["status"]}">{STATUS_LABELS[meta["status"]]}</span>']
    chips += [f'<span class="chip why">{escape(WHY_LABELS[w])}</span>' for w in meta["why_unfinished"]]
    chips += [f'<span class="chip tag">#{escape(t)}</span>' for t in meta["tags"]]
    if meta.get("example"):
        chips.insert(0, '<span class="chip example">Example</span>')
    return "".join(chips)


def _options(label: str, values: list[tuple[str, str]]) -> str:
    opts = "".join(f'<option value="{escape(v)}">{escape(text)}</option>' for v, text in values)
    return f'<option value="">{label}</option>{opts}'


def _card(idea: Idea, root: str) -> str:
    meta = idea.meta
    names = join_names([a["name"] for a in meta["authors"]])
    search = escape(f"{meta['title']} {names} {idea.id}".lower())
    version = f" (v{idea.version})" if idea.version > 1 else ""
    category = meta["category"]
    return (
        f'<li class="card" data-status="{meta["status"]}" data-category="{category}" '
        f'data-why="{escape(" ".join(meta["why_unfinished"]))}" '
        f'data-tags="{escape(" ".join(meta["tags"]))}" data-text="{search}">'
        f'<a class="title" href="{root}ideas/{idea.id}/">{escape(meta["title"])}</a>'
        f'<p class="meta">{idea.id}{version} · '
        f'<a href="{root}categories/{category}/">{escape(CATEGORIES[category])}</a> · '
        f'{escape(names)} · {meta["submitted"]} · est. {escape(meta["estimated_cost"])}</p>'
        f'<p class="chips">{_chips(idea)}</p></li>'
    )


def _newest_first(ideas: list[Idea]) -> list[Idea]:
    return sorted(ideas, key=lambda i: (i.meta["submitted"], i.id), reverse=True)


def render_index(ideas: list[Idea], repo_url: str) -> str:
    tags = sorted({t for i in ideas for t in i.meta["tags"]})
    whys = [w for w in WHY_LABELS if any(w in i.meta["why_unfinished"] for i in ideas)]
    cards = [_card(idea, "") for idea in _newest_first(ideas)]
    content = f"""<section class="intro">
<h1>Great ideas, empty wallets.</h1>
<p>Share it, keep the credit. These are startup and project ideas whose authors ran out of
API budget, tokens or GPUs before they could finish. Anyone may build them. If you do,
credit the people who had the idea.</p>
<p>Out of Tokens works as preprints for ideas. Each idea has a permanent id, dated
versions and a citation. See what is <a href="new/">new</a>, or browse by
<a href="categories/">category</a>.</p>
</section>
<form class="filters" id="filters" onsubmit="return false">
  <input type="search" id="f-text" placeholder="Search title, author or id" aria-label="Search">
  <select id="f-category" aria-label="Category">{_options("Any category", list(CATEGORIES.items()))}</select>
  <select id="f-why" aria-label="Why unfinished">{_options("Any reason", [(w, WHY_LABELS[w]) for w in whys])}</select>
  <select id="f-tag" aria-label="Tag">{_options("Any tag", [(t, "#" + t) for t in tags])}</select>
  <select id="f-status" aria-label="Status">{_options("Any status", list(STATUS_LABELS.items()))}</select>
</form>
<p class="count" id="count">{len(ideas)} ideas</p>
<ul class="cards" id="cards">
{chr(10).join(cards)}
</ul>
<p class="empty" id="empty" hidden>No ideas match these filters.</p>"""
    return _page("Out of Tokens: great ideas, empty wallets", "", content, repo_url)


def render_categories(ideas: list[Idea], repo_url: str) -> str:
    rows = []
    for key, label in CATEGORIES.items():
        count = sum(1 for i in ideas if i.meta["category"] == key)
        rows.append(
            f'<li><a href="{key}/">{escape(label)}</a> '
            f'<span class="meta">{count} {"idea" if count == 1 else "ideas"}</span></li>'
        )
    content = f"""<p class="crumb"><a href="../">All ideas</a> / Categories</p>
<h1>Categories</h1>
<p class="lead">Every idea has one subject category. Tags on each idea say the rest.</p>
<ul class="plain">
{chr(10).join(rows)}
</ul>"""
    return _page("Categories · Out of Tokens", "../", content, repo_url)


def render_category(key: str, ideas: list[Idea], repo_url: str) -> str:
    mine = [i for i in _newest_first(ideas) if i.meta["category"] == key]
    cards = "\n".join(_card(idea, "../../") for idea in mine)
    listing = (
        f'<ul class="cards">\n{cards}\n</ul>' if mine else "<p>No ideas in this category yet.</p>"
    )
    label = CATEGORIES[key]
    content = f"""<p class="crumb"><a href="../../">All ideas</a> / <a href="../">Categories</a> / {escape(label)}</p>
<h1>{escape(label)}</h1>
<p class="count">{len(mine)} {"idea" if len(mine) == 1 else "ideas"}</p>
{listing}"""
    return _page(f"{label} · Out of Tokens", "../../", content, repo_url)


def events(ideas: list[Idea]) -> list[tuple[Idea, View]]:
    """Every version of every idea, newest first."""
    pairs = [(idea, view) for idea in ideas for view in views(idea)]
    return sorted(pairs, key=lambda p: (p[1].date, p[0].id, p[1].version), reverse=True)


def render_new(ideas: list[Idea], repo_url: str, limit: int = 100) -> str:
    rows = []
    for idea, view in events(ideas)[:limit]:
        names = join_names([a["name"] for a in idea.meta["authors"]])
        what = "New idea" if view.version == 1 else f"Version {view.version}: {view.note or 'revised'}"
        rows.append(
            f'<li class="card"><a class="title" href="../ideas/{idea.id}/v{view.version}/">'
            f"{escape(view.title)}</a>"
            f'<p class="meta">{view.date} · {idea.id}v{view.version} · {escape(what)} · '
            f"{escape(names)}</p></li>"
        )
    listing = (
        '<ul class="cards">\n' + "\n".join(rows) + "\n</ul>" if rows else "<p>Nothing yet.</p>"
    )
    content = f"""<p class="crumb"><a href="../">All ideas</a> / New</p>
<h1>New</h1>
<p class="lead">New ideas and new versions, most recent first. The same list is available
as an <a href="../{FEED}">Atom feed</a>.</p>
{listing}"""
    return _page("New · Out of Tokens", "../", content, repo_url)


def render_feed(ideas: list[Idea], site_url: str, limit: int = 50) -> str:
    base = site_url.rstrip("/")
    listed = events(ideas)[:limit]
    updated = max((view.date for _, view in listed), default=None)
    stamp = lambda date: f"{date}T00:00:00Z"  # noqa: E731
    entries = []
    for idea, view in listed:
        url = version_url(idea, view.version, site_url)
        authors = "".join(
            f"<author><name>{xml_escape(a['name'])}</name></author>" for a in idea.meta["authors"]
        )
        what = "" if view.version == 1 else f" (version {view.version})"
        category = idea.meta["category"]
        entries.append(
            "<entry>"
            f"<id>{xml_escape(url)}</id>"
            f"<title>{xml_escape(f'{idea.id}v{view.version}: {view.title}{what}')}</title>"
            f'<link rel="alternate" type="text/html" href="{xml_escape(url)}"/>'
            f"<published>{stamp(view.date)}</published><updated>{stamp(view.date)}</updated>"
            f"{authors}"
            f'<category term="{category}" label="{xml_escape(CATEGORIES[category])}"/>'
            f"<summary>{xml_escape(abstract_text(view))}</summary>"
            "</entry>"
        )
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"<id>{xml_escape(base)}/</id>\n"
        "<title>Out of Tokens: new ideas and versions</title>\n"
        "<subtitle>Preprints for ideas. Share it, keep the credit.</subtitle>\n"
        f'<link rel="self" type="application/atom+xml" href="{xml_escape(base)}/{FEED}"/>\n'
        f'<link rel="alternate" type="text/html" href="{xml_escape(base)}/"/>\n'
        f"<updated>{stamp(updated) if updated else '1970-01-01T00:00:00Z'}</updated>\n"
        + "\n".join(entries)
        + "\n</feed>\n"
    )


def _copy_block(label: str, text: str, extra: str = "") -> str:
    return (
        f'<div class="copy{extra}"><div class="copy-head"><span>{label}</span>'
        f'<button type="button" class="copy-btn">Copy</button></div>'
        f"<pre><code>{escape(text)}</code></pre></div>"
    )


def _doi_link(doi: str) -> str:
    return f'<a href="https://doi.org/{escape(doi)}">{escape(doi)}</a>'


def _head(idea: Idea, view: View | None, site_url: str, pdf: bool) -> str:
    shown = view or views(idea)[-1]
    canonical = version_url(idea, view.version, site_url) if view else idea_url(idea, site_url)
    tags = [
        f'<link rel="canonical" href="{escape(canonical)}">',
        f'<meta name="description" content="{escape(abstract_text(shown)[:300])}">',
        f'<meta name="citation_title" content="{escape(shown.title)}">',
    ]
    tags += [
        f'<meta name="citation_author" content="{escape(a["name"])}">' for a in idea.meta["authors"]
    ]
    tags.append(f'<meta name="citation_publication_date" content="{shown.date:%Y/%m/%d}">')
    tags.append(f'<meta name="citation_abstract_html_url" content="{escape(canonical)}">')
    doi = shown.doi if view else (idea.meta.get("doi") or shown.doi)
    if doi:
        tags.append(f'<meta name="citation_doi" content="{escape(doi)}">')
    if pdf:
        url = version_url(idea, shown.version, site_url) + pdf_name(idea, shown.version)
        tags.append(f'<meta name="citation_pdf_url" content="{escape(url)}">')
    return "\n".join(tags) + "\n"


def render_idea(
    idea: Idea,
    site_url: str,
    repo_url: str,
    view: View | None = None,
    pdf: bool = False,
    root: str | None = None,
) -> str:
    """One idea page. ``view`` None is the idea's main page, showing the latest
    version at ``ideas/<id>/``. With a view it is that version's own page at
    ``ideas/<id>/v<N>/``. ``pdf`` says whether PDF files are being built."""
    meta = idea.meta
    all_views = views(idea)
    latest = all_views[-1]
    shown = view or latest
    here = "../" if view else ""  # path to the idea's main page
    if root is None:
        root = "../../../" if view else "../../"
    authors = join_names([_author_html(a) for a in meta["authors"]])
    built = meta.get("built_from_this", [])
    edit_url = f"{repo_url}/edit/main/{idea.path}"
    category = meta["category"]
    label = f"{idea.id}v{shown.version}"
    page_url = version_url(idea, view.version, site_url) if view else idea_url(idea, site_url)
    if built:
        items = "".join(
            f'<li><a rel="nofollow noopener" href="{escape(b["url"])}">{escape(b["name"])}</a>'
            f' by {escape(b["by"])}{" (" + str(b["date"]) + ")" if "date" in b else ""}</li>'
            for b in built
        )
        built_html = f"<ul>{items}</ul>"
    else:
        built_html = "<p>Nothing yet.</p>"

    notices = []
    if meta.get("example"):
        notices.append(
            '<p class="notice">This is an example entry written to show the format. '
            "It is not a real submission.</p>"
        )
    if meta["status"] == "withdrawn":
        gone = meta["withdrawn"]
        notices.append(
            f'<p class="notice withdrawn"><strong>Withdrawn on {gone["date"]}.</strong> '
            f'Reason given: {escape(gone["reason"])} '
            "The record and its versions stay public.</p>"
        )
    if view and not view.latest:
        notices.append(
            f'<p class="notice old">This is version {view.version}, from {view.date}. '
            f'The latest version is <a href="../">v{latest.version}</a>.</p>'
        )

    record = [
        ("Identifier", label),
        ("Subject", f'<a href="{root}categories/{category}/">{escape(CATEGORIES[category])}</a>'),
        ("Submitted", f'{meta["submitted"]} (v1)'),
    ]
    if shown.version > 1:
        record.append(("This version", f"v{shown.version}, {shown.date}"))
    record.append(("Estimated cost to build", escape(meta["estimated_cost"])))
    if not view and meta.get("doi"):
        record.append(("DOI, all versions", _doi_link(meta["doi"])))
    if shown.doi:
        record.append((f"DOI, v{shown.version}", _doi_link(shown.doi)))
    record.append(("Licence", '<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>'))
    record_html = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in record)

    history = []
    for item in reversed(all_views):
        bits = [f'<a href="{here}v{item.version}/">v{item.version}</a>', str(item.date)]
        if item.note:
            bits.append(escape(item.note))
        if item.doi:
            bits.append(_doi_link(item.doi))
        if pdf:
            bits.append(f'<a href="{here}v{item.version}/{pdf_name(idea, item.version)}">PDF</a>')
        current = ' aria-current="true"' if item.version == shown.version else ""
        history.append(f"<li{current}>{' · '.join(bits)}</li>")

    if pdf:
        pdf_href = f"{here}v{shown.version}/{pdf_name(idea, shown.version)}"
        actions = f'<a class="button" href="{pdf_href}">Download PDF</a>'
    else:
        actions = '<button type="button" class="button print-btn">Print or save as PDF</button>'

    print_head = " · ".join(
        ["Out of Tokens", label, str(shown.date), escape(page_url)]
        + ([f"https://doi.org/{escape(shown.doi)}"] if shown.doi else [])
    )
    content = f"""<article class="idea">
<p class="crumb"><a href="{root}">All ideas</a> / <a href="{root}categories/{category}/">{escape(CATEGORIES[category])}</a> / {label if view else idea.id}</p>
<p class="print-only print-head">{print_head}</p>
{chr(10).join(notices)}
<h1>{escape(shown.title)}</h1>
<p class="authors">{authors}</p>
<p class="chips">{_chips(idea)}</p>
<section class="abstract">
<h2>Abstract</h2>
{abstract_html(shown)}
</section>
<dl class="record">{record_html}</dl>
<p class="actions screen-only">{actions}</p>
<div class="body">
{_markdown().render(shown.body)}
</div>
<section class="versions">
<h2>Versions</h2>
<ul class="plain">
{chr(10).join(history)}
</ul>
<p class="meta screen-only">An author can revise an idea with a pull request. Past versions stay
readable here. <a href="{escape(repo_url)}/blob/main/CONTRIBUTING.md#revise-an-idea">How to revise</a>.</p>
</section>
<section class="built screen-only">
<h2>Built from this</h2>
{built_html}
<p class="meta">Built it, or building it? <a href="{escape(edit_url)}">Add your project</a>
to <code>built_from_this</code> with a pull request.</p>
</section>
<section class="credit">
<h2>Cite and credit this idea</h2>
<p class="screen-only">If you build on this idea, put the credit line in your README, paper or about page.</p>
{_copy_block("Cite as", cite_as(idea, site_url, view))}
{_copy_block("Credit line", credit_line(idea, site_url), " screen-only")}
{_copy_block("Badge (Markdown)", badge_markdown(idea, site_url), " screen-only")}
{_copy_block("BibTeX", bibtex(idea, site_url, view), " screen-only")}
<p class="meta screen-only"><a href="{escape(repo_url)}/blob/main/{escape(idea.path)}">Source file</a> ·
<a href="{escape(repo_url)}/commits/main/{escape(idea.path)}">History (the public record of who shared it and when)</a></p>
</section>
</article>"""
    title = f"{shown.title} · Out of Tokens {label if view else idea.id}"
    return _page(title, root, content, repo_url, _head(idea, view, site_url, pdf))


def _jsonable(value):
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return str(value) if isinstance(value, dt.date) else value


def catalogue_entry(idea: Idea, site_url: str, pdf: bool) -> dict:
    entry = _jsonable({k: v for k, v in idea.meta.items() if k not in ("versions", "abstract")})
    entry.setdefault("built_from_this", [])
    entry["abstract"] = abstract_text(views(idea)[-1])
    entry["versions"] = []
    for view in views(idea):
        url = version_url(idea, view.version, site_url)
        item = {"version": view.version, "date": str(view.date), "url": url}
        if view.note:
            item["note"] = view.note
        if view.doi:
            item["doi"] = view.doi
        if pdf:
            item["pdf"] = url + pdf_name(idea, view.version)
        entry["versions"].append(item)
    entry["url"] = idea_url(idea, site_url)
    entry["source"] = idea.path
    entry["credit"] = credit_line(idea, site_url)
    return entry


def build(
    ideas: list[Idea], out: Path, site_url: str, repo_url: str, chrome: str | None = None
) -> None:
    """Write the whole site to ``out``, replacing what is there.

    ``chrome`` is the path of a headless browser. When given, each version also
    gets a PDF; without it the pages offer the browser's print dialog.
    """
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC_DIR, out)
    has_pdf = bool(chrome)
    (out / ".nojekyll").write_text("")
    (out / "index.html").write_text(render_index(ideas, repo_url), encoding="utf-8")
    (out / "new").mkdir()
    (out / "new" / "index.html").write_text(render_new(ideas, repo_url), encoding="utf-8")
    (out / FEED).write_text(render_feed(ideas, site_url), encoding="utf-8")
    (out / "categories").mkdir()
    (out / "categories" / "index.html").write_text(
        render_categories(ideas, repo_url), encoding="utf-8"
    )
    for key in CATEGORIES:
        (out / "categories" / key).mkdir()
        (out / "categories" / key / "index.html").write_text(
            render_category(key, ideas, repo_url), encoding="utf-8"
        )
    (out / "badges").mkdir()
    catalogue = []
    for idea in ideas:
        page = out / "ideas" / idea.id
        page.mkdir(parents=True)
        (page / "index.html").write_text(
            render_idea(idea, site_url, repo_url, pdf=has_pdf), encoding="utf-8"
        )
        for view in views(idea):
            folder = page / f"v{view.version}"
            folder.mkdir()
            html = folder / "index.html"
            html.write_text(
                render_idea(idea, site_url, repo_url, view, pdf=has_pdf), encoding="utf-8"
            )
            if chrome:
                html_to_pdf(html, folder / pdf_name(idea, view.version), chrome)
        (out / "badges" / f"{idea.id}.svg").write_text(badge_svg(idea.id))
        catalogue.append(catalogue_entry(idea, site_url, has_pdf))
    (out / "ideas.json").write_text(
        json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def version_pdf(idea: Idea, view: View, site_url: str, repo_url: str, chrome: str) -> bytes:
    """The PDF of one version as bytes, for a deposit. ``view.doi`` is printed on it."""
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        shutil.copy(STATIC_DIR / "style.css", folder / "style.css")
        html = folder / "index.html"
        html.write_text(
            render_idea(idea, site_url, repo_url, view, pdf=True, root=""), encoding="utf-8"
        )
        target = folder / "out.pdf"
        html_to_pdf(html, target, chrome)
        return target.read_bytes()

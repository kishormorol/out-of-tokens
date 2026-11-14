"""Build the static site from the ideas folder.

Output is plain HTML with relative links, so it works under any base path
(a GitHub Pages project site, a custom domain, or a local file server).
"""

from __future__ import annotations

import json
import shutil
from html import escape
from pathlib import Path

from markdown_it import MarkdownIt

from .ideas import Idea

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
STATUS_LABELS = {"open": "Open", "being-built": "Being built", "built": "Built"}


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


def bibtex(idea: Idea, site_url: str) -> str:
    def tex(text: str) -> str:
        for ch in "\\&%$#_{}":
            text = text.replace(ch, "" if ch == "\\" else "\\" + ch)
        return text

    authors = " and ".join(tex(a["name"]) for a in idea.meta["authors"])
    key = "outoftokens_" + idea.id.lower().replace("-", "")
    return (
        f"@misc{{{key},\n"
        f"  author       = {{{authors}}},\n"
        f"  title        = {{{tex(idea.meta['title'])}}},\n"
        f"  year         = {{{idea.meta['submitted'].year}}},\n"
        f"  howpublished = {{Out of Tokens idea {idea.id}}},\n"
        f"  url          = {{{idea_url(idea, site_url)}}},\n"
        f"  note         = {{Idea text licensed CC BY 4.0}}\n"
        f"}}"
    )


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


def _page(title: str, root: str, content: str, repo_url: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<link rel="stylesheet" href="{root}style.css">
</head>
<body>
<header class="site">
  <a class="brand" href="{root}">Out of Tokens</a>
  <nav>
    <a href="{root}">Ideas</a>
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


def render_index(ideas: list[Idea], repo_url: str) -> str:
    ordered = sorted(ideas, key=lambda i: (i.meta["submitted"], i.id), reverse=True)
    tags = sorted({t for i in ideas for t in i.meta["tags"]})
    whys = [w for w in WHY_LABELS if any(w in i.meta["why_unfinished"] for i in ideas)]
    cards = []
    for idea in ordered:
        meta = idea.meta
        names = join_names([a["name"] for a in meta["authors"]])
        search = escape(f"{meta['title']} {names} {idea.id}".lower())
        cards.append(
            f'<li class="card" data-status="{meta["status"]}" '
            f'data-why="{escape(" ".join(meta["why_unfinished"]))}" '
            f'data-tags="{escape(" ".join(meta["tags"]))}" data-text="{search}">'
            f'<a class="title" href="ideas/{idea.id}/">{escape(meta["title"])}</a>'
            f'<p class="meta">{idea.id} · {escape(names)} · {meta["submitted"]} · '
            f'est. {escape(meta["estimated_cost"])}</p>'
            f'<p class="chips">{_chips(idea)}</p></li>'
        )
    content = f"""<section class="intro">
<h1>Great ideas, empty wallets.</h1>
<p>Share it, keep the credit. These are startup and project ideas whose authors ran out of
API budget, tokens or GPUs before they could finish. Anyone may build them. If you do,
credit the people who had the idea.</p>
</section>
<form class="filters" id="filters" onsubmit="return false">
  <input type="search" id="f-text" placeholder="Search title, author or id" aria-label="Search">
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


def _copy_block(label: str, text: str) -> str:
    return (
        f'<div class="copy"><div class="copy-head"><span>{label}</span>'
        f'<button type="button" class="copy-btn">Copy</button></div>'
        f"<pre><code>{escape(text)}</code></pre></div>"
    )


def render_idea(idea: Idea, site_url: str, repo_url: str) -> str:
    meta = idea.meta
    authors = join_names([_author_html(a) for a in meta["authors"]])
    built = meta.get("built_from_this", [])
    edit_url = f"{repo_url}/edit/main/{idea.path}"
    if built:
        items = "".join(
            f'<li><a rel="nofollow noopener" href="{escape(b["url"])}">{escape(b["name"])}</a>'
            f' by {escape(b["by"])}{" (" + str(b["date"]) + ")" if "date" in b else ""}</li>'
            for b in built
        )
        built_html = f"<ul>{items}</ul>"
    else:
        built_html = "<p>Nothing yet.</p>"
    example = (
        '<p class="notice">This is an example entry written to show the format. '
        "It is not a real submission.</p>"
        if meta.get("example")
        else ""
    )
    content = f"""<article class="idea">
<p class="crumb"><a href="../../">All ideas</a> / {idea.id}</p>
{example}
<h1>{escape(meta["title"])}</h1>
<p class="meta">By {authors} · shared {meta["submitted"]}</p>
<p class="chips">{_chips(idea)}</p>
<p class="meta">Estimated cost to build: {escape(meta["estimated_cost"])}</p>
<div class="body">
{_markdown().render(idea.body)}
</div>
<section class="built">
<h2>Built from this</h2>
{built_html}
<p class="meta">Built it, or building it? <a href="{escape(edit_url)}">Add your project</a>
to <code>built_from_this</code> with a pull request.</p>
</section>
<section class="credit">
<h2>Credit this idea</h2>
<p>If you build on this idea, put this line in your README, paper or about page.</p>
{_copy_block("Credit line", credit_line(idea, site_url))}
{_copy_block("Badge (Markdown)", badge_markdown(idea, site_url))}
{_copy_block("BibTeX", bibtex(idea, site_url))}
<p class="meta"><a href="{escape(repo_url)}/blob/main/{escape(idea.path)}">Source file</a> ·
<a href="{escape(repo_url)}/commits/main/{escape(idea.path)}">History (the public record of who shared it and when)</a></p>
</section>
</article>"""
    return _page(f"{meta['title']} · Out of Tokens {idea.id}", "../../", content, repo_url)


def build(ideas: list[Idea], out: Path, site_url: str, repo_url: str) -> None:
    """Write the whole site to ``out``, replacing what is there."""
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(STATIC_DIR, out)
    (out / ".nojekyll").write_text("")
    (out / "index.html").write_text(render_index(ideas, repo_url), encoding="utf-8")
    (out / "badges").mkdir()
    catalogue = []
    for idea in ideas:
        page = out / "ideas" / idea.id
        page.mkdir(parents=True)
        (page / "index.html").write_text(render_idea(idea, site_url, repo_url), encoding="utf-8")
        (out / "badges" / f"{idea.id}.svg").write_text(badge_svg(idea.id))
        catalogue.append(
            {
                **{k: v for k, v in idea.meta.items() if k != "submitted"},
                "submitted": str(idea.meta["submitted"]),
                "built_from_this": [
                    {**b, **({"date": str(b["date"])} if "date" in b else {})}
                    for b in idea.meta.get("built_from_this", [])
                ],
                "url": idea_url(idea, site_url),
                "source": idea.path,
                "credit": credit_line(idea, site_url),
            }
        )
    (out / "ideas.json").write_text(
        json.dumps(catalogue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

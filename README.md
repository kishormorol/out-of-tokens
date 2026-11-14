# Out of Tokens

**Great ideas, empty wallets. Share it, keep the credit.**

Out of Tokens is a public registry of startup and project ideas that their authors could
not finish, because the LLM API bill, the GPU hours or the compute cost more than they
could pay. Anyone may build an idea from the registry. In return, builders are asked to
credit the people who had it.

Each idea is one Markdown file in [`ideas/`](ideas/). The registry runs on GitHub alone: an
issue form for submissions, four small workflows, and a static site on GitHub Pages. It
needs only a free GitHub repository, so it costs nothing to keep running.

## What is in an idea

```yaml
---
id: OOT-0001
title: Plain-language summaries of every city council meeting
authors:
  - name: Example Author        # github, orcid and url are optional
submitted: 2026-11-14
status: open                    # open, being-built or built
tags: [civic-tech, summarisation]
why_unfinished: [llm-api-cost, time]
estimated_cost: "Roughly USD 400 a month in LLM API calls"
---
```

The body has four required sections, `## Problem`, `## Idea`, `## Approach` and
`## What's done`, and an optional `## Links` for partial code. The two files in
[`ideas/2026/`](ideas/2026/) are examples that show the format. They are marked
`example: true` and were written for illustration.

## What this can and cannot do

This section is the honest part, and it comes before the instructions on purpose.

**An idea cannot be owned.** Copyright protects the words used to describe an idea. It does
not protect the idea itself, in the United States (17 U.S.C. § 102(b)) or under the
international TRIPS agreement (Article 9(2)). A licence only governs what copyright covers.
As a result, no licence in this repository can force a person who builds your idea to
credit you, pay you or ask you first.

**What the registry gives you instead:**

1. **A licence on your text.** The write-up of each idea is licensed
   [CC BY 4.0](LICENSE-CONTENT). Anyone who copies, translates or adapts your text must
   credit you. That duty covers the text, and it stops there.
2. **A public, dated record.** Your idea enters the repository through a merged pull
   request. The Git history, the pull request page and the issue page show who shared it
   and when. GitHub records those times, independently of you and the maintainers. An
   optional workflow adds an [OpenTimestamps](proofs/README.md) proof that is independent
   of GitHub as well.
3. **A norm with a paper trail.** [ATTRIBUTION.md](ATTRIBUTION.md) asks every builder to
   credit the authors, and each idea page gives a ready credit line, a badge and a BibTeX
   entry. Builders list their project under "Built from this" on the idea page. A builder
   who skips the credit can be shown the record, in public.

**What you give up by sharing:**

- Your idea becomes public and stays public. Git history and forks keep a copy even if the
  file is removed later.
- Publishing an idea can end your own chance to patent it, at once in many countries and
  after a grace period in others. It also makes the idea prior art, which makes it harder
  for anyone else to patent it.
- Do not share anything secret, anything you may want to patent, or anything that belongs
  to an employer, a client or a co-author who has not agreed.

Nothing here is legal advice. If money or a patent depends on the answer, ask a lawyer
before you submit.

## Share an idea

1. Open a new issue and choose **Share an idea**. The form asks for the fields above.
2. A maintainer reads it and adds the `accepted` label.
3. A workflow turns the issue into a pull request that adds your idea with the next free
   id. You are the author of that commit.
4. When the pull request is merged, your idea is on the record and on the site.

You can also open a pull request yourself. Copy [`templates/idea.md`](templates/idea.md),
and see [CONTRIBUTING.md](CONTRIBUTING.md).

## Build an idea and give credit

1. Pick an idea whose status is `open`. Read its history if you want to see when it was
   shared.
2. Build it. Permission is already given.
3. Credit the authors in your README, paper or about page. The idea page gives the exact
   line to copy. [ATTRIBUTION.md](ATTRIBUTION.md) has the details.
4. Open a pull request that adds your project to `built_from_this` in the idea file, and
   sets `status` to `being-built` or `built`.

```yaml
status: built
built_from_this:
  - name: Council Digest
    url: https://example.org/council-digest
    by: Your Name
    date: 2027-02-01
```

## Run it locally

The tooling is a small Python package with two dependencies, PyYAML and markdown-it-py.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest                    # unit tests
.venv/bin/python -m out_of_tokens validate    # check every idea file
.venv/bin/python -m out_of_tokens next-id     # the next free id
.venv/bin/python -m out_of_tokens build       # write the site to _site/
```

Open `_site/index.html` in a browser to see the result.

## Licence and citation

- Idea text in `ideas/` and `proofs/`: [CC BY 4.0](LICENSE-CONTENT), with credit due to
  the authors named in each file.
- Code, workflows and everything else: [MIT](LICENSE).
- To cite the registry, use [CITATION.cff](CITATION.cff). To cite one idea, use the BibTeX
  entry on its page.

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[code of conduct](CODE_OF_CONDUCT.md).

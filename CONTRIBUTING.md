# Contributing

There are three ways to contribute: share an idea, record a project built from an idea, or
improve the tooling. Please read the "What this can and cannot do" section of the
[README](README.md) before you share anything.

## Share an idea with the form

Open a new issue with the **Share an idea** form. A maintainer reviews it and adds the
`accepted` label, and a workflow opens a pull request with your idea file. You do not need
Git for this route.

## Share an idea with a pull request

1. Fork the repository and set up the tools (see "Run it locally" in the README).
2. Run `python -m out_of_tokens next-id` to get the next free id.
3. Copy `templates/idea.md` to `ideas/<YYYY>/<id>-<slug>.md`, where `<YYYY>` is the year
   of `submitted` and `<slug>` is a short lowercase name with hyphens.
4. Fill it in and run `python -m out_of_tokens validate`.
5. Open the pull request. If another idea takes your id first, a maintainer will ask you
   to renumber.

### Field rules

| Field | Rule |
| --- | --- |
| `id` | `OOT-` and at least four digits. It never changes and is never reused. |
| `title` | One line, 5 to 120 characters. |
| `authors` | At least one. `name` is required. `github` (no `@`), `orcid` and `url` are optional. |
| `submitted` | The date you open the issue or pull request, `YYYY-MM-DD`, without quotes. |
| `status` | `open`, `being-built` or `built`. New ideas start as `open`. |
| `tags` | 1 to 8, lowercase letters, digits and hyphens. |
| `why_unfinished` | One or more of `llm-api-cost`, `gpu-cost`, `compute-cost`, `data-cost`, `hosting-cost`, `funding`, `time`, `team`, `other`. |
| `estimated_cost` | One quoted line in your own words. Say what the money or compute is for. |
| `example` | Only for the sample entries. Leave it out. |
| `built_from_this` | Added later by builders. Each entry has `name`, `url`, `by` and an optional `date`. |

The body needs the sections `## Problem`, `## Idea`, `## Approach` and `## What's done`.
`## Links` is optional. Raw HTML and images are not rendered on the site.

### What to share and what to keep

- Share your own ideas, or ideas whose every author agreed to the submission.
- Write the idea in your own words. Text copied from elsewhere cannot be licensed by you.
- Leave out secrets, personal data about other people, and anything owned by an employer
  or client.
- By submitting, you license the text under CC BY 4.0. That licence cannot be withdrawn.
  A maintainer can take a file off the site on request, but Git history and forks keep it.

## Record a project built from an idea

Edit the idea file, add one entry to `built_from_this`, and set `status` if it changed.
Change nothing else. Please credit the authors in your project first, as
[ATTRIBUTION.md](ATTRIBUTION.md) describes.

## Improve the tooling

The code lives in `out_of_tokens/`: `ideas.py` defines the format and the validator,
`issue.py` converts an issue form, and `site.py` builds the site. Tests are in `tests/`.
Add or update a test with every change and run `python -m pytest` before you open a pull
request. Please keep the project free to run: no servers, no paid services, and no new
dependency without a reason stated in the pull request.

## For maintainers

- Labels: the form adds `idea`. Create an `accepted` label and add it to an issue to start
  the conversion. Only people with triage rights can add labels, which is the gate.
- Review for: one idea per issue, the author's own words, no secrets or personal data, no
  spam, and the code of conduct. Do not judge whether an idea is good.
- A pull request opened by the workflow does not start the Validate workflow on its own.
  The conversion already validated the file. Close and reopen the pull request if you want
  the check to show on it.
- The frozen-field check fails when `id`, `submitted` or `authors` of a merged idea change,
  or when an idea is deleted. Merge over it only for a real correction that the original
  authors asked for, and say so in the pull request.
- Merge idea pull requests with a merge commit or a squash that keeps the submitter as the
  author, so the history names them.

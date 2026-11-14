# Contributing

There are four ways to contribute: share an idea, revise or withdraw an idea you shared,
record a project built from an idea, or improve the tooling. Please read the "What this can and cannot do" section of the
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
| `status` | `open`, `being-built`, `built` or `withdrawn`. New ideas start as `open`. |
| `category` | Exactly one of the subject categories listed below. |
| `tags` | 1 to 8, lowercase letters, digits and hyphens. |
| `why_unfinished` | One or more of `llm-api-cost`, `gpu-cost`, `compute-cost`, `data-cost`, `hosting-cost`, `funding`, `time`, `team`, `other`. |
| `estimated_cost` | One quoted line in your own words. Say what the money or compute is for. |
| `abstract` | Optional. Plain text, at most 1500 characters, no Markdown. Without it the page shows the first paragraph of Problem and the first paragraph of Idea. |
| `versions` | Written by `revise`. Leave it out of a new idea: a file without it has one version, dated `submitted`. |
| `withdrawn` | Only with `status: withdrawn`. A `date` and a one-line `reason`. |
| `doi` | Written by the Zenodo workflow. Never add one by hand. |
| `example` | Only for the sample entries. Leave it out. |
| `built_from_this` | Added later by builders. Each entry has `name`, `url`, `by` and an optional `date`. |

The body needs the sections `## Problem`, `## Idea`, `## Approach` and `## What's done`.
`## Links` is optional. Raw HTML and images are not rendered on the site.

### Subject categories

Pick the one that fits best. Use tags for everything else.

| Category | Covers |
| --- | --- |
| `nlp` | Language and text |
| `vision` | Vision and images |
| `speech` | Speech and audio |
| `health` | Health and medicine |
| `education` | Education |
| `science` | Science and research |
| `dev-tools` | Developer tools |
| `data` | Data and infrastructure |
| `robotics` | Robotics and hardware |
| `finance` | Finance and business |
| `civic` | Civic and public interest |
| `creative` | Creative work and media |
| `other` | Anything else |

### What to share and what to keep

- Share your own ideas, or ideas whose every author agreed to the submission.
- Write the idea in your own words. Text copied from elsewhere cannot be licensed by you.
- Leave out secrets, personal data about other people, and anything owned by an employer
  or client.
- By submitting, you license the text under CC BY 4.0. That licence cannot be withdrawn.
  A maintainer can take a file off the site on request, but Git history and forks keep it.

## Revise an idea

Only an author of the idea should open a revision. A maintainer checks that before merging.

1. Start from an up-to-date copy of `main`, before you change anything.
2. Run `python -m out_of_tokens revise OOT-0001 --note "what changed"` with your id. This
   does two things. It copies the idea file as it is now to `versions/OOT-0001/v1.md`,
   which becomes the frozen first version. It also adds the next version, with today's
   date and your note, to `versions` in the front matter.
3. Edit the idea file. You may change the title, the abstract and the body.
4. Run `python -m out_of_tokens validate` and open a pull request that contains both the
   idea file and the new file under `versions/`.

Rules that the check enforces:

- `id`, `authors` and `submitted` never change.
- A change to the title, the abstract or the body needs a new version. A change to
  `status`, `tags`, `category` or `built_from_this` does not.
- One pull request adds one version. Each version after the first needs a `note`.
- The frozen copy must hold the previous version as it is on `main`. If you edited first
  and ran `revise` afterwards, restore it with the `git show` command that the check prints.
- Files under `versions/` are never edited or deleted.

Without Git on your machine you can do the same on github.com: copy the raw idea file into
a new file at `versions/<id>/v<N>.md`, then edit the idea file and add the new entry to
`versions` by hand, in the same pull request. The result looks like this:

```yaml
versions:
  - version: 1
    date: 2026-11-14
  - version: 2
    date: 2026-12-01
    note: "Added a cost breakdown"
```

After the merge, the idea page shows the new version, and `/ideas/<id>/v1/` keeps showing
the old one.

## Withdraw an idea

An author can withdraw an idea, for example because it turned out to be wrong, already
built, or shared by mistake. Open a pull request that changes the status and adds the
reason, and nothing else:

```yaml
status: withdrawn
withdrawn:
  date: 2026-12-05
  reason: "One line that says why, 10 to 300 characters."
```

The idea page then shows the notice above the text. The text, every version and any DOI
stay on the record, because other people may already have cited or built on them. A
withdrawal is permanent, and a withdrawn idea cannot get a new version. If something must
truly come off the site, for example personal data, write to a maintainer instead.

## Record a project built from an idea

Edit the idea file, add one entry to `built_from_this`, and set `status` if it changed.
Change nothing else. Please credit the authors in your project first, as
[ATTRIBUTION.md](ATTRIBUTION.md) describes.

## Improve the tooling

The code lives in `out_of_tokens/`: `ideas.py` defines the format and the validator,
`issue.py` converts an issue form, `site.py` builds the site, `pdf.py` prints the PDF
files and `zenodo.py` registers DOIs. Tests are in `tests/`.
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
  when an idea is deleted, when its text changes without a new version, when a past
  version or a DOI is altered, or when a withdrawal is undone. Merge over it only for a
  real correction that the original authors asked for, and say so in the pull request.
- For a revision or a withdrawal, check that the person who opened the pull request is one
  of the idea's authors. The tooling cannot check that.
- DOIs are off until you connect Zenodo. [MAINTAINERS.md](MAINTAINERS.md) has the steps.
- Merge idea pull requests with a merge commit or a squash that keeps the submitter as the
  author, so the history names them.

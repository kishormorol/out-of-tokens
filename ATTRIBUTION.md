# Builders acknowledge

This is the norm of Out of Tokens. It is a promise between people, and the README explains
why it cannot be a legal duty for the idea itself.

> If you build something from an idea in this registry, you say so, in public, and you
> name the people who had the idea.

## How to credit

Every idea page on the site has a section called "Credit this idea" with three snippets
that are ready to copy. They follow these patterns.

**Credit line**, for a README, an about page, a launch post or a paper's acknowledgements:

```text
Based on the idea "<title>" (<id>) by <authors>, shared on Out of Tokens on <date>. <idea URL>
```

**Badge**, for a README:

```markdown
[![Built from Out of Tokens idea <id>](<site URL>/badges/<id>.svg)](<idea URL>)
```

**Citation**, for a paper. Use the BibTeX entry on the idea page. If your project has a
`CITATION.cff`, add the idea under `references`, as shown in
[`templates/CITATION.cff`](templates/CITATION.cff).

Then add your project to `built_from_this` in the idea file with a pull request. That link
back is what lets the authors, and the next reader, see what became of the idea.

## What counts as building from an idea

- You read the idea here and then built it, in whole or in part: credit it.
- You took one part of it, such as the approach or the data plan: credit it and say which
  part.
- You had the same idea on your own and built it before you saw this registry: you owe
  nothing. A short note such as "a similar idea was shared as OOT-0001" is still a kind
  thing to add.

## What the authors can expect

- Their names stay on the idea. The `id`, `submitted` and `authors` fields of a merged idea
  are frozen, and a check fails any pull request that changes them.
- The record is public: the Git history of the file, the merged pull request and, where
  enabled, an OpenTimestamps proof in [`proofs/`](proofs/README.md).
- The idea text is under CC BY 4.0. A person who copies or adapts the text itself must give
  credit by law.

## When credit is missing

1. Write to the builder first, with a link to the idea and its history. Most missing
   credits are oversights.
2. If that does not work, open an issue here. Maintainers can record the project under
   "Built from this" with a note, so the link exists on the public record.
3. Maintainers do not make legal claims on anyone's behalf, and they do not judge who
   thought of something first beyond what the record shows.

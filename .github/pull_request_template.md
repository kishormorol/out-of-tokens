<!-- Tick the part that applies and delete the rest. -->

### Adding an idea

- [ ] The file is `ideas/<YYYY>/<id>-<slug>.md` and uses the next free id (`python -m out_of_tokens next-id`).
- [ ] This is my own idea, or every listed author agreed to this submission.
- [ ] I license the idea text under CC BY 4.0 and understand it is public and permanent.

### Revising or withdrawing my idea

- [ ] I am an author of this idea.
- [ ] Revision: I ran `python -m out_of_tokens revise <id> --note "..."` before editing, and this pull request has both the idea file and the new file under `versions/`.
- [ ] Withdrawal: I set `status: withdrawn` and added `withdrawn` with a date and a reason, and changed nothing else.

### Adding my project to "Built from this"

- [ ] I added one entry to `built_from_this` and changed nothing else in the idea, apart from `status` if it applies.
- [ ] My project credits the idea's authors (see ATTRIBUTION.md).

### Changing code or docs

- [ ] `python -m pytest` passes.

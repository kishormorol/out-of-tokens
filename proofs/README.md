# Timestamp proofs

This folder is optional. It is filled by the `Timestamp` workflow, which uses
[OpenTimestamps](https://opentimestamps.org), a free service that needs no account.

For each idea the workflow stores two files:

- `proofs/<id>/idea.md`: a frozen copy of the idea file as it was when it was merged.
- `proofs/<id>/idea.md.ots`: a proof that this exact file existed at a certain time. The
  proof is anchored in the Bitcoin blockchain, so it does not depend on GitHub or on the
  maintainers of this repository.

## Verify a proof

```sh
pip install opentimestamps-client
ots info proofs/OOT-0001/idea.md.ots       # show what the proof contains
ots upgrade proofs/OOT-0001/idea.md.ots    # complete a proof that is still pending
ots verify proofs/OOT-0001/idea.md.ots     # needs access to a Bitcoin node
```

A new proof is "pending" for a few hours until Bitcoin confirms it. The workflow tries to
complete pending proofs each time it runs. The website opentimestamps.org can also verify a
proof in the browser without a Bitcoin node.

## What a proof shows

A proof shows that the text existed by the stated time. It does not show who wrote it, and
it does not show that nobody had the idea earlier. Together with the merged pull request it
is good evidence of when an idea was shared here, and that is all it claims.

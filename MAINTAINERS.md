# Maintainer notes

Day-to-day review is described under "For maintainers" in [CONTRIBUTING.md](CONTRIBUTING.md).
This file covers the one thing that needs an account outside GitHub: DOIs.

## Turning on Zenodo DOIs

The `Zenodo DOI` workflow gives every version of every accepted idea a DOI. It is off
until the repository has a secret named `ZENODO_TOKEN`. Without the secret the workflow
ends after its first step with a notice, and nothing else in the repository depends on it.

### What it does once it is on

- It runs after each push to `main` that touches `ideas/` or `versions/`, and it can be
  started by hand from the Actions tab.
- For each version that has no DOI, it creates a Zenodo record with the idea's Markdown
  file and, when the runner has Chrome, its PDF. The first version creates a new record.
  A later version is added as a new version of the same record.
- It publishes the record. A published Zenodo record is permanent. It cannot be deleted,
  and its files cannot be changed.
- It opens a pull request named "Record Zenodo DOIs" that writes the DOIs into the front
  matter. Merge it soon. While it is open, the workflow makes no further deposits.
- Example entries (`example: true`) and withdrawn ideas are never deposited.

The record type sent to Zenodo is "publication" with the publication type "preprint".
Zenodo offers a fixed list of types. "Preprint" is the closest one to a short public
write-up that has not been reviewed, and scholarly indexes treat it as citable text. To
use a different type, change `PUBLICATION_TYPE` in `out_of_tokens/zenodo.py` before the
first real deposit. "proposal" and "other" are the nearest alternatives.

### It never deposits a version twice

Three things guard against that. A version with a DOI in its front matter is skipped. A
run does nothing while a DOI pull request is still open. Before creating anything, the
workflow also lists the account's existing Zenodo records and reuses the one that already
names the version's page, so a record made by a run that failed half way is completed
instead of repeated.

### Try it on the sandbox first

Zenodo has a test site whose records and DOIs are not real. Use it for the first run.

1. Create an account at <https://sandbox.zenodo.org>. It is separate from the real site.
2. There, open Applications in your account settings and create a personal access token
   with the scopes `deposit:write` and `deposit:actions`.
3. In this repository, open Settings, then Secrets and variables, then Actions. Add a
   repository **secret** named `ZENODO_TOKEN` with the sandbox token as its value. On the
   Variables tab, add a repository **variable** named `ZENODO_SANDBOX` with the value `true`.
4. Start the `Zenodo DOI` workflow by hand from the Actions tab.
5. Read the log of the deposit step, and look at the records in your sandbox account.

With `ZENODO_SANDBOX` set to `true`, nothing is written to the repository and no pull
request is opened. Sandbox DOIs start with `10.5072` and do not resolve, and the validator
refuses them in idea files. Only real ideas are deposited, so while the registry holds
only the two example entries the run reports that there is nothing to deposit.

To see what would be sent without any account, run this on your machine:

```sh
python -m out_of_tokens zenodo --dry-run \
  --site-url https://kishormorol.github.io/out-of-tokens \
  --repo-url https://github.com/kishormorol/out-of-tokens
```

### Go live

1. Create an account at <https://zenodo.org> and a personal access token there with the
   same two scopes, `deposit:write` and `deposit:actions`.
2. Replace the value of the `ZENODO_TOKEN` secret with the real token.
3. Delete the `ZENODO_SANDBOX` variable, or set it to `false`.
4. Start the workflow by hand once. It deposits every accepted version that has no DOI
   yet, at most ten in one run, and opens the pull request with the DOIs.
5. Merge that pull request. Checks do not start on their own for a pull request opened by
   a workflow, so close and reopen it if you want the check to run first.

### Keep the token safe

- Put the token only in the repository secret. Do not paste it into a file, an issue, a
  pull request or a workflow log.
- The workflow runs on pushes to `main` and by hand. It does not run on pull requests, so
  code from a pull request cannot read the token.
- The code sends the token only in a request header, and only to the Zenodo host.
- If the token may have leaked, delete it in your Zenodo account settings and make a new one.

### Turn it off again

Delete the `ZENODO_TOKEN` secret. Existing DOIs keep working, and new versions get no DOI.

### When a deposit fails

The workflow run is marked failed and the log names the idea and Zenodo's answer.
Successful deposits from the same run still arrive in the pull request. Fix the cause and
start the workflow again. It picks up where it stopped.

If Zenodo has a record but the DOI never reached the repository, start the workflow again.
It finds the record and writes the DOI back without creating a second one.

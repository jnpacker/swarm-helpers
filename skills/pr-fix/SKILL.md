---
name: pr-fix
description: Fix a PR's merge conflicts, failing CI checks (test/lint), or unresolved review comments, then push the fix directly to the PR branch.
---

# PR Fix Skill

Diagnose and fix a pull request that is blocked by merge conflicts, failing CI
checks, or unresolved review comments. Pushes the fix directly to the PR
branch — no new branches, no new Jira tickets.

**When to use:** The PR already exists and is blocked. Use `start-work` +
`finish-work` instead when you are doing net-new feature or bug work.

---

## Step 1 — Parse args

Read the PR identifier from the user's args. Accept any of:

- Full GitHub URL: `https://github.com/OWNER/REPO/pull/NUMBER`
- Short form: `OWNER/REPO#NUMBER`
- Number only (when already inside the repo): `58`

If no arg is provided, ask the user for the PR URL or number before continuing.
Derive `owner`, `repo`, and `pr_number` from whatever form is given.

---

## Step 2 — Fetch PR state and classify the problem

Call the GitHub API (via MCP tools or `gh pr view`) to retrieve:
- `mergeable_state` — `dirty` means merge conflicts
- `head.ref` — the branch name to check out
- `head.sha` — the current head commit
- PR title and branch name

Call the GitHub API to get CI status:
- Any check with `conclusion == "failure"` is a CI failure

Call the GitHub API to get review threads:
- Filter for unresolved threads (`isResolved == false`)
- Note which are from `coderabbitai[bot]` vs. human reviewers

**Classify into one or more problem types:**

| Problem | Signal |
|---|---|
| Merge conflict | `mergeable_state == "dirty"` |
| CI failure | Any check run with `conclusion == "failure"` |
| Review comments | Unresolved threads, especially from `coderabbitai[bot]` |

If multiple problems exist, fix them in this order: **merge conflicts → CI → review comments** (conflicts block CI; CI must pass before review comments matter).

Summarize what you found to the user before proceeding.

---

## Step 2.5 — Discover and update the linked Jira ticket (if present)

Inspect the PR title and branch name for a Jira ticket key pattern (e.g., `PROJ-123`). Common locations:
- Branch name: `feat/PROJ-123-short-description` or `PROJ-123-fix-thing`
- PR title: `fix(PROJ-123): description` or `PROJ-123 — description`

If a ticket key is found:
1. Fetch the Jira issue to confirm it exists and is accessible.
2. Post a comment on the Jira ticket summarizing the fix plan:
   - Which problem type(s) were detected (conflicts / CI failure / review comments)
   - Brief description of the intended fix approach
   - Link to the PR

If no ticket key is found, continue without Jira integration — not all PRs have linked issues.

> **Tooling note:** Use whatever Jira integration is available in the current environment — MCP Jira tools, the Jira REST API, or the `jira` CLI. The steps above are tool-agnostic.

---

## Step 3 — Check out the PR branch

```bash
git fetch origin <head.ref>
git checkout <head.ref>
```

If the branch already exists locally and is behind, fast-forward it:

```bash
git checkout <head.ref>
git pull --ff-only origin <head.ref>
```

If `--ff-only` fails (local diverged), do not force-reset — confirm with the user first.

Confirm you are on the right branch and at the right commit before making any changes.

---

## Step 4A — Fix: Merge Conflicts

**Only follow this section if merge conflicts were detected.**

```bash
git fetch origin <base.ref>
git merge origin/<base.ref>
```

Identify all conflicted files:

```bash
git diff --name-only --diff-filter=U
```

For each conflicted file:
1. Read the file — look for `<<<<<<<`, `=======`, `>>>>>>>` markers.
2. Understand both sides: **ours** (PR branch) vs. **theirs** (base branch).
3. Resolve by keeping the correct content. When in doubt:
   - Keep PR branch changes for files the PR intentionally modified.
   - Keep base branch changes for files the PR did not touch.
   - Merge both when the changes are in different parts of the file.
4. Write the resolved file (no conflict markers remaining).
5. `git add <file>`

After resolving all files:

```bash
git commit -S -s -m "chore: resolve merge conflicts with <base.ref>"
```

---

## Step 4B — Fix: CI Failures

**Only follow this section if failing check runs were detected.**

For each failing check run:

1. **Identify the failure type** from the check run name (e.g., "Lint Go", "Test Python", "Build").
2. **Map the check to a local command** using the repo's `Makefile`, `CLAUDE.md`, or CI workflow file (`.github/workflows/`). Read the workflow YAML to find the exact command the CI runs.
3. **Reproduce locally** — run the same command:
   ```bash
   make test        # or whatever the CI runs
   make lint
   go test ./...
   ```
4. **Read the failure output carefully.** Common patterns:
   - **Test timeout / hang** → look for infinite loops or blocking calls in the test or the code under test
   - **Assertion error** → read the expected vs. actual values; trace back to the source
   - **Import error / missing dependency** → check `requirements.txt`, `go.mod`
   - **Lint violation** → fix the flagged line; re-run to confirm clean
   - **Compilation error** → fix the type/syntax error at the reported line
5. **Apply the fix** to the source file(s).
6. **Re-run the failing command** to confirm it passes before committing.
7. **Run the full test suite** (if fast) to confirm no regressions.

Commit the fix:

```bash
git commit -S -s -m "fix: <short description of what was wrong>

<one or two sentences on root cause and fix>
"
```

---

## Step 4C — Fix: Review Comments

**Only follow this section if unresolved review threads exist.**

Fetch all unresolved threads via the GitHub API.

For each unresolved thread:

1. **Read the thread body** — understand what the reviewer is asking.
2. **Locate the file and line** from the thread's `path` and `line` fields.
3. **Classify the comment:**
   - **Suggestion with replacement** → apply it verbatim unless you have a strong reason not to.
   - **Nitpick / style** → apply it; these are usually straightforward.
   - **Correctness concern** → investigate before applying; verify the bug is real.
   - **Question / clarification** → if a code fix answers it, make the fix; otherwise note it in a PR comment reply.
4. **Apply the fix** to the file.

After addressing all threads, commit:

```bash
git commit -S -s -m "fix: address review comments

- <bullet per issue addressed>
"
```

If a comment raises a concern you intentionally disagree with, do **not** silently skip it — note it in the PR comment you post in Step 6.

---

## Step 5 — Validate before pushing

Run the full local check suite to make sure the fixes don't introduce new failures.
Use whatever targets the repo exposes (check `Makefile` and `CLAUDE.md`):

```bash
make lint   # if available
make test   # if available and fast
```

If any check fails, return to the relevant Step 4 section and fix it before continuing.

---

## Step 6 — Push to the PR branch

Use whatever GitHub integration is available — GitHub MCP tools, `gh pr push`, or plain `git push`:

```bash
git push origin <head.ref>
```

Do **not** force-push unless the branch history requires it (e.g., a rebase-based conflict resolution). If force-push is needed, confirm with the user first.

---

## Step 7 — Post a summary comment on the PR and update Jira

**On the PR**, post a brief summary comment:

**Structure:**
- What problem type(s) were fixed (merge conflict / CI failure / review comments)
- For CI failures: which check was failing, root cause in one sentence, what changed
- For review comments: how many threads addressed, any intentionally skipped and why
- Confirmation that local checks pass

Keep it concise — one or two short paragraphs. Reviewers and CI will do the final verification.

**On the Jira ticket** (if one was found in Step 2.5), post a follow-up comment:
- Summary of what was fixed
- Link to the specific commit(s) pushed
- Confirmation that CI passed locally

---

## Important notes

- **No new branches.** Push directly to the PR's head branch.
- **No new Jira tickets.** This skill fixes an existing PR inline. If you discover a separate, non-trivial bug while fixing, note it in the PR comment for the author to file separately.
- **GitHub operations** can use GitHub MCP tools when available, or fall back to `git`/`gh` CLI — use whatever is present in the environment.
- **Minimal commits.** One commit per problem type (conflict, CI, review) is ideal.
- **Confirm before force-pushing.** Always ask the user before `git push --force`.
- **Don't over-fix.** Scope the commit to what's needed to unblock the PR. Save refactoring for a separate PR.

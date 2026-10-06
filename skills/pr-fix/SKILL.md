---
name: pr-fix
description: Fix a PR's merge conflicts, failing CI checks (test/lint), or unresolved review comments, then push the fix directly to the PR branch.
category: Fleet Engineering
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

## Step 3.5 — Shared pre-write gate

Before any write operation in Steps 4-7 (file edits, commits, pushes, PR/Jira comments, or thread resolution):

- If plan/read-only mode is active, stop and ask the user to switch to Build mode first.
- In non-plan mode, request explicit user confirmation before executing writes.

Re-check this gate immediately before each write step; do not assume a prior confirmation still applies.

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

Fetch review threads using a resolution-aware source (GitHub GraphQL or GitHub MCP review-thread APIs) with pagination.

For every fetched thread, record:
- Stable thread ID (for example, GraphQL `PRRT_...` node ID)
- File path and line
- `isResolved` state
- Latest comment body/author

Do not use APIs or scripts that only return a flattened comment list without thread IDs or resolution state.

For each unresolved thread:

1. **Read the thread body** — understand what the reviewer is asking. Note whether the review is from `coderabbitai[bot]` or a human reviewer.
2. **Locate the file and line** from the thread's `path` and `line` fields.
3. **Evaluate whether the fix is warranted:**
   - Spend ample thinking on whether this is genuinely an issue that needs to be addressed.
   - **Major & Critical findings (security vulnerabilities, functional bugs, resource leaks, data loss)**:
     - **Must be fixed or block merge:** Major and Critical CodeRabbit or reviewer findings **cannot be declined solely as out of scope**. In accordance with repository review policy, they must either be resolved directly on the PR branch or explicitly block the merge.
     - **Dismissal only for verified false positives:** A Major or Critical finding may only be dismissed if full-codebase inspection conclusively proves it is a false positive. Always document the concrete technical justification in the PR reply and summary.
   - **Check scope and intent:** Is this comment directly related to the original intent of the PR or one of the necessary review fixes?
   - **Reject out-of-scope / tangential suggestions:** For non-blocking suggestions, stylistic preferences, speculative micro-optimizations, or tangential refactoring outside the PR's scope, use discretion to decline or defer them rather than creating unnecessary churn. Explain why in the PR response/summary (or recommend a follow-up issue if it is a valid separate improvement).
   - **Filter false positives:** Automated reviewers analyze diff hunks in isolation and lack full-repo context. Verify technical validity against the whole codebase before assuming the reviewer is correct.
4. **Review implications and blast radius before applying:**
   - **Take into account that fixing an issue might create new issues.**
   - Analyze secondary impacts: callers, type contracts, error handling paths, nil/null safety, concurrency/race conditions, and behavioral invariants across the repo.
   - **Never apply AI / CodeRabbit suggestions blindly or verbatim:** Treat suggestions as advisory cues rather than copy-paste patches. CodeRabbit snippets may hallucinate APIs, break invariants, or introduce subtle regressions. Always adapt the fix so it integrates safely and idiomatically with existing project conventions without creating new bugs.
5. **Apply the fix** to the file(s) carefully.

After addressing all warranted threads, commit:

```bash
git commit -S -s -m "fix: address review comments

- <bullet per issue addressed>
"
```

If a comment raises an unwarranted concern or is intentionally declined/skipped, do **not** silently ignore it — document the reasoning in the PR comment you post in Step 7.

---

## Step 5 — Validate before pushing

1. **Review the diff for unintended side effects:**
   Inspect the changes across the branch:
   ```bash
   git diff origin/<base.ref>
   ```
   Critically evaluate whether the fixes introduced any regressions, altered unexpected behavior, or created new issues.

2. **Run local check suites:**
   Run the full local check suite to make sure the fixes don't introduce new failures. Use whatever targets the repo exposes (check `Makefile` and `CLAUDE.md`):

   ```bash
   make lint   # if available
   make test   # if available and fast
   ```

If any check fails or secondary issues are spotted in the diff, return to the relevant Step 4 section and fix it before continuing.

---

## Step 6 — Push to the PR branch

Use whatever GitHub integration is available — GitHub MCP tools, `gh pr push`, or plain `git push`:

```bash
git push origin <head.ref>
```

Do **not** force-push unless the branch history requires it (e.g., a rebase-based conflict resolution). If force-push is needed, confirm with the user first.

---

## Step 7 — Post a summary comment on the PR and update Jira

Before any Step 7 write operation (PR thread replies, thread resolution, PR summary comment, Jira updates):

- If plan/read-only mode is active, stop and ask the user to switch to Build mode first.
- In non-plan mode, request explicit user confirmation before executing these writes.

Before posting the summary, use the Step 4C resolution-aware thread data to handle each addressed unresolved thread:

- Add a concise thread reply describing the fix and include the commit SHA.
- Resolve the thread after replying (for example via GitHub MCP `resolve_thread`).
- Do **not** resolve threads that were declined, deferred, or still need reviewer input.

**On the PR**, post a brief summary comment:

**Title:** `## 🛠️ PR Fix Summary`

**Structure:**
- What problem type(s) were fixed (merge conflict / CI failure / review comments)
- For CI failures: which check was failing, root cause in one sentence, what changed
- For review comments: how many threads addressed, any intentionally skipped/declined and why
- Confirmation that local checks and diff implication review pass
- **CodeRabbit re-review trigger:** If (and only if) unresolved review comments from **`coderabbitai[bot]`** were among the issues addressed and pushed, include:
  ```markdown
  @coderabbitai review and approve
  ```
  *(Do NOT include this tag if only merge conflicts, CI failures, or human-only comments were fixed).*

Keep it concise — one or two short paragraphs. Reviewers and CI will do the final verification.

**On the Jira ticket** (if one was found in Step 2.5), post a follow-up comment:
- Summary of what was fixed
- Link to the specific commit(s) pushed
- Confirmation that CI passed locally

---

## Important notes

- **No new branches.** Push directly to the PR's head branch.
- **No new Jira tickets.** This skill fixes an existing PR inline. If you discover a separate, non-trivial bug while fixing, note it in the PR comment for the author to file separately.
- **Evaluate fix implications.** Always consider secondary impacts — a fix (especially from automated reviewers like CodeRabbit) must not create new bugs, break callers, or introduce regressions.
- **Scope discipline.** Spend ample time deciding if a review fix is warranted. Do not apply out-of-scope or tangential suggestions that deviate from the PR's original intent.
- **Trigger CodeRabbit re-review when applicable.** Always include `@coderabbitai review and approve` in the PR comment when CodeRabbit review comments were addressed and pushed.
- **GitHub operations** can use GitHub MCP tools when available, or fall back to `git`/`gh` CLI — use whatever is present in the environment.
- **Minimal commits.** One commit per problem type (conflict, CI, review) is ideal.
- **Confirm before a force push.** Always ask the user before using destructive git push flags.
- **Don't over-fix.** Scope the commit to what's needed to unblock the PR. Save refactoring for a separate PR.

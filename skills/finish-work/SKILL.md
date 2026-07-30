---
name: finish-work
description: Use when the user runs /finish-work or asks to wrap up, commit, push, open a PR, and update Jira for the current work session. Commits, pushes, opens PR, and links to Jira. Optionally runs a pre-commit review-fix cycle if the user asks for one.
---

Wrap up the current work session: commit, push, open a PR, post an implementation summary, and update Jira. Optionally run a pre-commit review-and-fix cycle first, if the user asks for it.

## Step 1 — Identify the Jira ticket

Derive the Jira ticket from the current branch name by extracting the Jira ID prefix (e.g. `FLD-29/fix-branch-naming` → ticket `FLD-29`). The Jira ID is the portion before the first `/` (or the entire branch name if there is no `/`). If the branch name does not contain a recognizable Jira ticket ID, ask the user for the ticket key.

## Step 2 — Detect fork vs. direct-push workflow

Run `git remote -v` and inspect the remotes **before doing anything else**:

**Fork workflow** — `origin` and `upstream` point to different repos (e.g. `jnpacker/repo` and `OrgName/repo`):
- All pushes go to **`origin`** (your fork).
- PRs must be opened manually by the user: `origin/<branch>` → `upstream/main` (cross-account, cannot be created via MCP tools).

**Direct workflow** — `origin` and `upstream` point to the same URL, or only one remote exists:
- Push to **`origin`** and create the PR via `mcp__github-*` tools targeting the upstream `main`.

## Step 3 — Compose a commit message

Use conventional commits format: one subject line + short body. Include `Jira: <TICKET>` in the body. No quotes or special characters.

## Step 4 — Create the branch

- If on `main` or `master`: `git checkout -b <JIRA-ID>/<short-description>` where `<short-description>` is a kebab-case slug derived from the Jira ticket summary (e.g. `FLD-29/fix-branch-naming`).
- If already on a feature branch, use it.

## Step 4.5 — Run pre-commit review-fix cycle (opt-in)

This step is **off by default**. Only run it if the user explicitly asked
for a pre-commit review as part of this `/finish-work` request (e.g. "run
review-fix", "review before committing", `--review`). A prior, separate
invocation of `pr-review-fix` in the same session does not count — only run
it here if asked again for this session's wrap-up.

If requested, run the `pr-review-fix` skill against the current
uncommitted changes before anything is committed:

1. Load the `pr-review-fix` skill.
2. Run it against the current working directory, diffing against the branch
   this work will merge into (the repo's default branch, e.g. `main`).
3. It stages, reviews across its model rotation, fixes issues in place, and
   finishes with `git reset --mixed` — leaving all changes (original work +
   fixes) unstaged again. Nothing is committed by this step.
4. Note the consolidated report (issues found/fixed per pass) so it can be
   mentioned in the PR comment in Step 7.

If not requested, proceed directly to Step 5 with the code as-is.

## Step 5 — Stage, commit, and push

Push to **`origin`** as determined in Step 2.

```
git add <modified files>
git commit -S -s -m "<subject line>"
git push -u origin <branch>
```

## Step 6 — Create a PR (direct workflow only)

Skip this step if using the fork workflow — notify the user:
> "Branch pushed to your fork (`origin`). Please open the PR manually from `<fork-owner>/<repo>` → `<upstream-owner>/<repo>` on GitHub."

Use the repo's PR template if one exists (check `.github/pull_request_template.md`). Include the Jira link in the PR body.

## Step 7 — Post implementation summary to the PR

Post the implementation summary as a **comment on the PR**. Cover:

- What changed (files modified, new files, key functions or sections affected)
- Tests added or confirmed passing
- Known gaps or follow-up items
- The pre-commit review-fix result from Step 4.5, if it ran (e.g. "Pre-commit review: 4-pass cycle, 6 issues found and fixed" or "Pre-commit review: clean across 4 passes")

If using the fork workflow, paste the summary in chat so the user can add it after opening the PR.

## Step 8 — Update Jira

- Post a Jira comment with `mcp__jira-mcp-server__add_comment`: commit message subject + body + PR link.
- Transition the ticket to `Review` status with `mcp__jira-mcp-server__transition_issue`.
- Ask if the user wants to log implementation time.

## Step 9 — Remind the user

Confirm tests exist and pass. If using the fork workflow, remind the user to open the PR from their fork before the branch is reviewed.

---

## Dependencies

### CLI tools
- `git` — branch, commit, push operations

### MCP tools
- `mcp__github-*` — create the PR in direct workflow when the repo supports MCP-based PR creation
- `mcp__jira-mcp-server__add_comment` — post implementation summary to Jira
- `mcp__jira-mcp-server__transition_issue` — move ticket to Review status

### Related skills
- `start-work` — creates the Jira sub-task this skill closes out
- `pr-review-fix` — pre-commit multi-model review-and-fix cycle, run in Step 4.5 only if the user explicitly asks for it
- `pr-review` — optional read-only review process a human can still run after the PR is opened

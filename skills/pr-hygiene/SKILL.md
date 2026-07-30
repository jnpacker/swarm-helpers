---
name: pr-hygiene
description: Use when managing PR lifecycle across workspace repositories — scans every cloned repo for stale open PRs, converts inactive PRs to draft with a warning after 4 business days, closes stale drafts after 5 more business days, and detects PRs needing re-review after new commits. Designed for scheduled runs over one or more repos cloned under a workspace directory (e.g. /sandbox). NOT for reviewing PR content or code quality — see `pr-review` for that.
---

# PR Hygiene

Scans open pull requests across every git repository in the current
workspace and enforces a staleness policy: PRs that go quiet are converted
to draft with a warning, and drafts that stay quiet are closed. PRs that
receive new commits are automatically restored and queued for re-review.

**Supporting files:**
- `scripts/pr-hygiene.py` — discovers repos, scans open PRs, and outputs a
  classified JSON action plan (read-only; performs no writes)

**Important:** the script uses `uv` for automatic dependency management.
Run it directly (e.g. `scripts/pr-hygiene.py`). If `uv` is not available,
fall back to `python3 scripts/pr-hygiene.py` — it has no external
dependencies beyond the standard library.

## Staleness policy

| Day (business days) | Condition | Action |
|---|---|---|
| 0–3 | No new commits, still open | No action |
| 4 | No new commits since day 0 | Convert to draft, add `stale` label, post warning comment |
| 4–8 (5 more biz days after draft) | Still no new commits | No action (grace period) |
| 9 (5 biz days after the draft comment) | Still no new commits | Close as stale |
| Any point while in draft | New commit pushed after the draft comment | Take out of draft, remove `stale` label, clock resets to 0, request re-review |
| Any point while open (non-draft) | New commit pushed after the last review | Request re-review (not stale — no draft/close action) |

PRs with the `do-not-stale` label are exempt from all staleness actions.
PRs a human put into draft (no `stale` label present) are never touched —
this skill only acts on drafts it created itself, identified by the
`stale` label plus its own marker comment.

## Step 1 — Discover repositories

The workspace root is the directory containing one or more cloned repos
(e.g. `/sandbox` in scheduled runs, or the current directory otherwise).
Ask the user for the workspace root if it isn't obvious from context —
default to the current working directory's parent if the agent is already
inside a single repo, or `/sandbox` in scheduled/agent-swarm contexts.

The script performs discovery itself (walks up to two levels deep for
`.git` directories and resolves `owner/repo` from each `origin` remote),
so this step is just confirming the root path with the user, not a
separate manual scan.

## Step 2 — Scan PRs

Run the scanning script against the workspace root:

```bash
scripts/pr-hygiene.py <WORKSPACE_ROOT>
```

The script prints a JSON action plan to stdout, e.g.:

```json
{
  "scanned_at": "2026-07-30T12:00:00Z",
  "workspace_root": "/sandbox",
  "repos": [
    {
      "owner": "stolostron",
      "repo": "console",
      "prs": [
        {
          "number": 4521,
          "title": "Fix table sorting",
          "author": "jdoe",
          "branch": "fix-table-sort",
          "is_draft": false,
          "labels": [],
          "jira_key": null,
          "action": "needs-draft",
          "reason": "5 business day(s) since last commit",
          "days": 5
        }
      ],
      "error": null
    }
  ],
  "summary": { "total_repos": 1, "total_prs": 1, "needs-draft": 1 }
}
```

If a repo entry has a non-null `error` (e.g. `gh` auth failure for that
org), report it and continue with the remaining repos — don't abort the
whole run over one broken repo (graceful degradation).

If `total_prs` is 0, report "No open PRs found across N repo(s)." and stop.

## Step 3 — Present the summary and confirm

Render the action plan as a markdown table grouped by repo, one row per PR
that has a proposed action (skip `healthy`, `human-draft`, `draft-waiting`,
and `exempt` rows in the table but mention their counts in a one-line
summary):

| Repo | PR | Title | Author | Action | Reason |
|---|---|---|---|---|---|
| stolostron/console | #4521 | Fix table sorting | jdoe | Convert to draft | 5 business days since last commit |
| stolostron/console | #4498 | Update deps | asmith | Close as stale | 5 business days in draft with no new commits |
| acme-org/agentic-sdlc | #12 | Add hygiene skill | jdoe2 | Restore from draft + re-review | commit pushed after hygiene draft comment |

**Ask the user to confirm before executing any actions.** This skill
modifies PR state (draft/ready, labels, comments, closures) and these are
external side effects that require explicit confirmation per project
policy. If running unattended (e.g. a scheduled agent run with no human in
the loop), treat the run configuration's own approval as the confirmation
and proceed, but still print the full plan in the final report for audit.

## Step 4 — Execute actions

For each PR in the action plan, run the corresponding action using the
`gh` CLI. Use `mcp__github-*` MCP tools instead if they are available and
preferred in this environment — the `gh` CLI commands below are the
canonical fallback (P2).

### 4a. `needs-draft` — convert to draft

```bash
gh pr ready <NUMBER> --repo <OWNER>/<REPO> --undo
gh pr edit <NUMBER> --repo <OWNER>/<REPO> --add-label stale
gh pr comment <NUMBER> --repo <OWNER>/<REPO> --body "$(cat <<'EOF'
**PR Hygiene: Converted to draft**

This PR has had no new commits for 4 business days and has been converted to draft.

It will be **closed automatically in 5 business days** if no new commits are pushed.

To prevent automatic closure, push a commit or add the `do-not-stale` label.

*-- PR Hygiene Agent*
EOF
)"
```

The exact comment text matters: Step 2's classification logic on the next
run finds this comment by matching the string `PR Hygiene: Converted to
draft` to determine when the draft clock started. Do not reword it.

### 4b. `needs-undraft` — restore from draft and request re-review

```bash
gh pr ready <NUMBER> --repo <OWNER>/<REPO>
gh pr edit <NUMBER> --repo <OWNER>/<REPO> --remove-label stale
gh pr comment <NUMBER> --repo <OWNER>/<REPO> --body "$(cat <<'EOF'
**PR Hygiene: Restored from draft**

New commits detected since this PR was flagged as stale. This PR has been taken out of draft and the staleness clock has been reset. Re-review has been requested from previous reviewers.

*-- PR Hygiene Agent*
EOF
)"
```

Then request re-review from every reviewer listed in the action plan's
`reviewers` field for this PR:

```bash
gh api repos/<OWNER>/<REPO>/pulls/<NUMBER>/requested_reviewers \
  --method POST \
  --field "reviewers[]=<login1>" \
  --field "reviewers[]=<login2>"
```

If `reviewers` is empty (no one had reviewed yet), skip the re-review
request — there's no one to re-request from.

### 4c. `needs-close` — close as stale

```bash
gh pr comment <NUMBER> --repo <OWNER>/<REPO> --body "$(cat <<'EOF'
**PR Hygiene: Closed as stale**

This PR has been in draft with no new commits for 5 business days since it was flagged and has been closed as stale.

You are welcome to reopen it when it is ready for review. The branch has not been deleted.

*-- PR Hygiene Agent*
EOF
)"
gh pr close <NUMBER> --repo <OWNER>/<REPO>
```

If the action plan entry has a non-null `jira_key`, add a brief comment to
the linked Jira issue noting the PR was closed as stale
(`mcp__jira-mcp-server__add_comment`). This is best-effort — if the Jira
MCP tool is unavailable or the issue doesn't exist, note the gap in the
final report and continue (graceful degradation, P5). Never create a new
Jira issue as part of this skill.

### 4d. `needs-rereview` — request re-review only

Same re-review request as 4b, but do **not** touch draft status, labels,
or post a comment — the PR is still active, just needs fresh eyes on a
new commit:

```bash
gh api repos/<OWNER>/<REPO>/pulls/<NUMBER>/requested_reviewers \
  --method POST \
  --field "reviewers[]=<login1>"
```

### 4e. No action

`healthy`, `human-draft`, `draft-waiting`, and `exempt` PRs require no
action. Log them in the final report's counts only.

## Step 5 — Final report

After executing all actions, print a summary:

```
=== PR HYGIENE COMPLETE ===
Workspace:    <workspace_root>
Repos scanned: <N> (<N> with errors)
PRs scanned:   <N>

Converted to draft:      <N>
Restored + re-reviewed:  <N>
Closed as stale:         <N>
Re-review requested:     <N>
No action needed:        <N> (healthy: N, human-draft: N, draft-waiting: N, exempt: N)

Errors:
  <repo> — <error message>
  PR #<N> in <repo> — <error message>

Jira updates:
  <ISSUE-KEY> — commented (PR closed as stale) / skipped: <reason>
```

## Anti-patterns

- **Never touch a draft PR without the `stale` label.** That means a human
  drafted it intentionally — leave it alone regardless of age.
- **Never reword the draft-conversion comment.** The classification logic
  depends on matching its exact marker text on the next run.
- **Never force-push or modify PR branches.** This skill only changes PR
  metadata (draft state, labels, comments, open/closed state) — never
  code.
- **Never create new Jira issues.** Only comment on an issue already
  linked via the PR title or branch name.
- **Don't guess `owner/repo`.** If a repo's `origin` remote can't be
  parsed, skip it and report the gap rather than guessing.

## Dependencies

### CLI tools
- `gh` — GitHub CLI, authenticated via `GH_TOKEN` (or `GH_TOKEN_<ORG>` per
  the multi-org token pattern in `practices/opencode-setup.md`)
- `python3` (>= 3.11) or `uv` — to run `scripts/pr-hygiene.py`

### MCP tools
- `mcp__github-*` — optional alternative to the `gh` CLI commands in Step 4
- `mcp__jira-mcp-server__add_comment` — optional Jira comment on closure
  (graceful degradation if unavailable)

### Related skills
- `pr-review` — for reviewing PR content/code quality (not lifecycle)
- `pr-fix` — for fixing a blocked PR (conflicts, CI, review comments)

### Supporting files
- `scripts/pr-hygiene.py` — repo discovery, PR scanning, business-day
  calculation, and classification (read-only; outputs a JSON action plan)

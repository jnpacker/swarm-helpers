#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Scan workspace repositories for PR hygiene issues and classify each open PR.

Discovers every git repo under a workspace root, lists its open PRs via the
`gh` CLI, and classifies each PR into an action based on a staleness policy:

  - Open (non-draft) PR idle >= 4 business days (no new commits)
      -> needs-draft   (convert to draft, label `stale`, warn)
  - Draft PR with `stale` label and a commit pushed after the hygiene
    agent's draft comment
      -> needs-undraft (take out of draft, remove `stale`, reset clock,
                         request re-review from prior reviewers)
  - Draft PR with `stale` label, no new commits, >= 5 business days since
    the draft comment
      -> needs-close   (close as stale)
  - Draft PR with `stale` label, no new commits, < 5 business days
      -> draft-waiting (no action yet)
  - Draft PR without a `stale` label
      -> human-draft   (a human drafted it; never touch)
  - Open (non-draft) PR with a commit pushed after the last review
      -> needs-rereview (request re-review only; not stale)
  - PR with the `do-not-stale` label
      -> exempt        (never touch)
  - Anything else
      -> healthy

This script is read-only: it never calls `gh pr edit`, `gh pr close`, or
`gh pr comment`. It only reads PR state and prints a JSON action plan for
the calling skill to execute after user confirmation.

Usage:
    ./pr-hygiene.py [WORKSPACE_ROOT]

Example:
    ./pr-hygiene.py /sandbox
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

DRAFT_COMMENT_MARKER = "PR Hygiene: Converted to draft"
STALE_LABEL = "stale"
EXEMPT_LABEL = "do-not-stale"
DRAFT_DAYS_THRESHOLD = 4
CLOSE_DAYS_THRESHOLD = 5
MAX_REPO_DEPTH = 2

# Track which token source currently populates GH_TOKEN so we can
# re-resolve when scanning a repo in a different org.
_original_gh_token: str | None = os.environ.get("GH_TOKEN")
_active_token_source: str | None = "GH_TOKEN" if _original_gh_token else None


def resolve_gh_token(org: str) -> None:
    """Resolve GH_TOKEN per-org, falling back to GH_TOKEN_<ORG> if unset.

    When scanning repos across multiple GitHub orgs, each org may need a
    different token.  This function ensures the correct token is active:

    - If the caller's original environment already had GH_TOKEN set, that
      global token is used for every org (no per-org override).
    - Otherwise, it looks for GH_TOKEN_<ORG> and sets GH_TOKEN for the
      current org, replacing any previously set per-org token when the org
      changes.

    Never prints token values -- only variable names.
    """
    global _active_token_source

    normalized_org = org.lower().replace("-", "_")
    org_var = f"GH_TOKEN_{normalized_org}"

    # If the user's original environment had GH_TOKEN, always use it.
    if _original_gh_token:
        os.environ["GH_TOKEN"] = _original_gh_token
        _active_token_source = "GH_TOKEN"
        return

    # Already using the right org-specific token.
    if _active_token_source == org_var:
        return

    org_token = os.environ.get(org_var)

    if org_token:
        os.environ["GH_TOKEN"] = org_token
        _active_token_source = org_var
        print(f"GH_TOKEN not set; using {org_var}", file=sys.stderr)
        return

    # No token for this org — clear any previously set per-org token so
    # gh falls back to its own auth (gh auth login) rather than using a
    # stale token from a different org.
    if _active_token_source and _active_token_source != "GH_TOKEN":
        os.environ.pop("GH_TOKEN", None)
    _active_token_source = None

    available = sorted(k for k in os.environ if k.startswith("GH_TOKEN_"))
    if available:
        available_msg = (
            "Available GH_TOKEN_* variables in the environment (names only, no values):\n"
            + "".join(f"  {k}\n" for k in available)
        )
    else:
        available_msg = "No GH_TOKEN_* variables found in the environment."

    print(
        f"WARNING: GH_TOKEN is not set and no org-specific fallback {org_var} was found.\n"
        f"{available_msg}\n"
        f"Skipping repos under this org unless GH_TOKEN is already valid globally.",
        file=sys.stderr,
    )


def gh_json(*args: str) -> object:
    """Run a gh command and return parsed JSON (object, list, or scalar)."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def gh_paginate(endpoint: str) -> list:
    """Fetch all pages from a gh REST endpoint, flattened into one list."""
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        capture_output=True,
        text=True,
        check=True,
    )
    pages = json.loads(result.stdout)
    items: list = []
    for page in pages:
        if isinstance(page, list):
            items.extend(page)
        else:
            items.append(page)
    return items


def discover_repos(workspace_root: str) -> list[dict]:
    """Walk workspace_root for git repos (max depth) and resolve owner/repo.

    Returns a list of {"path", "owner", "repo"} dicts. Directories without a
    resolvable GitHub remote are skipped with a note on stderr.
    """
    repos = []
    root = os.path.abspath(workspace_root)
    if not os.path.isdir(root):
        return repos

    for entry in sorted(os.listdir(root)):
        candidate = os.path.join(root, entry)
        if not os.path.isdir(candidate):
            continue
        if os.path.isdir(os.path.join(candidate, ".git")):
            owner_repo = resolve_owner_repo(candidate)
            if owner_repo:
                owner, repo = owner_repo
                repos.append({"path": candidate, "owner": owner, "repo": repo})
            else:
                print(
                    f"WARNING: could not resolve GitHub owner/repo for {candidate}, skipping",
                    file=sys.stderr,
                )
            continue
        # One level deeper (e.g. workspace_root/org/repo)
        if MAX_REPO_DEPTH >= 2:
            try:
                sub_entries = sorted(os.listdir(candidate))
            except OSError:
                continue
            for sub_entry in sub_entries:
                sub_candidate = os.path.join(candidate, sub_entry)
                if os.path.isdir(os.path.join(sub_candidate, ".git")):
                    owner_repo = resolve_owner_repo(sub_candidate)
                    if owner_repo:
                        owner, repo = owner_repo
                        repos.append({"path": sub_candidate, "owner": owner, "repo": repo})
                    else:
                        print(
                            f"WARNING: could not resolve GitHub owner/repo for {sub_candidate}, skipping",
                            file=sys.stderr,
                        )

    return repos


def resolve_owner_repo(repo_path: str) -> tuple[str, str] | None:
    """Parse the `origin` remote URL of a local git repo into (owner, repo)."""
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    url = result.stdout.strip()
    # Matches both SSH (git@github.com:owner/repo.git) and HTTPS
    # (https://github.com/owner/repo.git) remote URL forms.
    match = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", url)
    if not match:
        return None
    return match.group(1), match.group(2)


def list_open_prs(owner: str, repo: str) -> list:
    """List open PRs with the fields needed for classification."""
    return gh_json(
        "pr",
        "list",
        "--repo",
        f"{owner}/{repo}",
        "--state",
        "open",
        "--limit",
        "1000",
        "--json",
        "number,title,isDraft,createdAt,labels,author,headRefName",
    )


def get_pr_commits(owner: str, repo: str, pr_number: int) -> list:
    return gh_paginate(f"repos/{owner}/{repo}/pulls/{pr_number}/commits")


def get_pr_comments(owner: str, repo: str, pr_number: int) -> list:
    return gh_paginate(f"repos/{owner}/{repo}/issues/{pr_number}/comments")


def get_pr_reviews(owner: str, repo: str, pr_number: int) -> list:
    return gh_paginate(f"repos/{owner}/{repo}/pulls/{pr_number}/reviews")


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def business_days_between(start: datetime, end: datetime) -> int:
    """Count weekdays (Mon-Fri) strictly between start and end, no holiday calendar."""
    if end <= start:
        return 0
    days = 0
    cursor = start
    while cursor.date() < end.date():
        cursor = cursor + timedelta(days=1)
        if cursor.weekday() < 5:  # Mon=0 .. Fri=4
            days += 1
    return days


def last_commit_date(commits: list) -> datetime | None:
    dates = []
    for c in commits:
        commit_info = c.get("commit", {})
        committer = commit_info.get("committer") or {}
        author = commit_info.get("author") or {}
        raw = committer.get("date") or author.get("date")
        if raw:
            dates.append(parse_iso(raw))
    return max(dates) if dates else None


def last_review_date(reviews: list) -> datetime | None:
    dates = [parse_iso(r["submitted_at"]) for r in reviews if r.get("submitted_at")]
    return max(dates) if dates else None


def get_reviewers(reviews: list, author_login: str | None = None) -> list[str]:
    seen = []
    for r in reviews:
        login = (r.get("user") or {}).get("login")
        if login and login != author_login and login not in seen:
            seen.append(login)
    return seen


def find_hygiene_draft_comment(comments: list) -> datetime | None:
    """Return the timestamp of the most recent hygiene draft-conversion comment."""
    matches = [
        parse_iso(c["created_at"])
        for c in comments
        if DRAFT_COMMENT_MARKER in (c.get("body") or "")
    ]
    return max(matches) if matches else None


def pr_label_names(pr: dict) -> list[str]:
    """Extract label names from a PR's `labels` field."""
    return [label["name"] for label in pr.get("labels", [])]


def extract_jira_key(pr: dict) -> str | None:
    """Best-effort Jira issue key extraction from title or branch name."""
    pattern = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
    for field in (pr.get("title"), pr.get("headRefName")):
        if field:
            match = pattern.search(field)
            if match:
                return match.group(0)
    return None


def classify_pr(pr: dict, commits: list, comments: list, reviews: list, now: datetime) -> dict:
    labels = pr_label_names(pr)

    if EXEMPT_LABEL in labels:
        return {"action": "exempt", "reason": f"has `{EXEMPT_LABEL}` label"}

    is_draft = pr["isDraft"]
    has_stale_label = STALE_LABEL in labels

    commit_date = last_commit_date(commits)
    hygiene_comment_date = find_hygiene_draft_comment(comments)

    author_login = (pr.get("author") or {}).get("login")

    if is_draft and has_stale_label:
        if hygiene_comment_date is None:
            # Label present but no marker comment found -- don't assume ownership.
            return {"action": "human-draft", "reason": "stale label without hygiene comment"}

        if commit_date and commit_date > hygiene_comment_date:
            return {
                "action": "needs-undraft",
                "reason": "commit pushed after hygiene draft comment",
                "reviewers": get_reviewers(reviews, author_login),
            }

        days_since_draft = business_days_between(hygiene_comment_date, now)
        if days_since_draft >= CLOSE_DAYS_THRESHOLD:
            return {
                "action": "needs-close",
                "reason": f"{days_since_draft} business day(s) in draft with no new commits",
                "days": days_since_draft,
            }
        return {
            "action": "draft-waiting",
            "reason": f"{days_since_draft} business day(s) in draft (closes at {CLOSE_DAYS_THRESHOLD})",
            "days": days_since_draft,
        }

    if is_draft and not has_stale_label:
        return {"action": "human-draft", "reason": "draft without stale label"}

    # Open (non-draft) PR.
    review_date = last_review_date(reviews)
    needs_rereview = bool(review_date and commit_date and commit_date > review_date)

    reference_date = commit_date or parse_iso(pr["createdAt"])
    days_idle = business_days_between(reference_date, now)

    if days_idle >= DRAFT_DAYS_THRESHOLD:
        return {
            "action": "needs-draft",
            "reason": f"{days_idle} business day(s) since last commit",
            "days": days_idle,
        }

    if needs_rereview:
        return {
            "action": "needs-rereview",
            "reason": "commit pushed after last review",
            "reviewers": get_reviewers(reviews, author_login),
        }

    return {"action": "healthy", "reason": f"{days_idle} business day(s) idle", "days": days_idle}


def scan_repo(owner: str, repo: str) -> dict:
    resolve_gh_token(owner)
    entry: dict = {"owner": owner, "repo": repo, "prs": [], "error": None}

    try:
        prs = list_open_prs(owner, repo)
    except subprocess.CalledProcessError as exc:
        entry["error"] = f"gh pr list failed: {exc.stderr.strip() if exc.stderr else exc}"
        return entry

    now = datetime.now(timezone.utc)

    for pr in prs:
        pr_number = pr["number"]
        try:
            commits = get_pr_commits(owner, repo, pr_number)
            comments = get_pr_comments(owner, repo, pr_number)
            reviews = get_pr_reviews(owner, repo, pr_number)
        except subprocess.CalledProcessError as exc:
            entry["prs"].append(
                {
                    "number": pr_number,
                    "title": pr["title"],
                    "error": f"failed to fetch PR detail: {exc.stderr.strip() if exc.stderr else exc}",
                }
            )
            continue

        classification = classify_pr(pr, commits, comments, reviews, now)
        entry["prs"].append(
            {
                "number": pr_number,
                "title": pr["title"],
                "author": (pr.get("author") or {}).get("login"),
                "branch": pr["headRefName"],
                "is_draft": pr["isDraft"],
                "labels": pr_label_names(pr),
                "jira_key": extract_jira_key(pr),
                **classification,
            }
        )

    return entry


def main() -> None:
    if "--help" in sys.argv or "-h" in sys.argv:
        print(__doc__)
        sys.exit(0)

    workspace_root = sys.argv[1] if len(sys.argv) > 1 else "."

    repos = discover_repos(workspace_root)
    if not repos:
        print(
            json.dumps(
                {
                    "error": f"no git repositories found under {os.path.abspath(workspace_root)}",
                    "repos": [],
                    "summary": {},
                }
            )
        )
        sys.exit(1)

    results = []
    action_counts: dict[str, int] = {}

    for r in repos:
        entry = scan_repo(r["owner"], r["repo"])
        results.append(entry)
        for pr in entry["prs"]:
            action = pr.get("action", "error")
            action_counts[action] = action_counts.get(action, 0) + 1

    output = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "workspace_root": os.path.abspath(workspace_root),
        "repos": results,
        "summary": {
            "total_repos": len(results),
            "total_prs": sum(len(r["prs"]) for r in results),
            **action_counts,
        },
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()

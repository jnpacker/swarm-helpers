#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""gh-commit — create a GitHub API commit (Verified) and optionally open a PR.

Replaces `git commit -S && git push && gh pr create` in agent workflows.
Commits created via the GitHub Git Data API are automatically marked Verified
by GitHub regardless of whether the author has a GPG or SSH signing key.

Usage:
    gh-commit --branch <branch> --message "<msg>" [options]

    # Full example (auto-detects repo from git remote):
    gh-commit --branch ACM-1234 --base main \\
              --message "feat: add widget" \\
              --pr-title "feat: add widget" \\
              --pr-body "Jira: https://redhat.atlassian.net/browse/ACM-1234"

Token:
    GH_TOKEN (required)
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

GITHUB_API = "https://api.github.com"
DEFAULT_AUTHOR_NAME = "Swarm Agentic SDLC"
DEFAULT_AUTHOR_EMAIL = "noreply@github.com"


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------

def resolve_token() -> str:
    """Return GH_TOKEN from the environment, or exit with a clear error."""
    val = os.environ.get("GH_TOKEN")
    if val:
        return val
    print("ERROR: GH_TOKEN is not set.", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def api(token: str, method: str, path: str, body: Optional[dict] = None) -> dict:
    """Make a GitHub API request; exit on non-2xx."""
    url = f"{GITHUB_API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "gh-commit/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # Only log status code, not response body (which may contain sensitive data).
        print(
            f"ERROR: GitHub API {method} {url} returned {exc.code}",
            file=sys.stderr,
        )
        sys.exit(1)


def api_get_optional(token: str, path: str) -> Optional[dict]:
    """GET that returns None on 404 instead of exiting."""
    url = f"{GITHUB_API}{path}"
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "gh-commit/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        # Only log status code, not response body (which may contain sensitive data).
        print(
            f"ERROR: GitHub API GET {url} returned {exc.code}",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def run(args: list[str], cwd: Optional[str] = None) -> str:
    """Run a subprocess and return stdout, or exit on failure."""
    result = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        # Only log command and exit code, not stderr (which may contain sensitive data).
        print(
            f"ERROR: {' '.join(args)} failed with exit code {result.returncode}",
            file=sys.stderr,
        )
        sys.exit(1)
    return result.stdout.strip()


def detect_repo() -> str:
    """Parse owner/repo from git remote origin URL.

    Handles:
      https://github.com/owner/repo.git
      git@github.com:owner/repo.git
      ssh://git@ssh.github.com:443/owner/repo.git
    """
    url = run(["git", "remote", "get-url", "origin"])
    # HTTPS
    if url.startswith("https://github.com/"):
        return url[len("https://github.com/"):].removesuffix(".git")
    # ssh:// URLs (including ssh.github.com:443) — use urlparse to strip host/port
    if url.startswith("ssh://"):
        parsed = urlparse(url)
        if parsed.hostname in {"github.com", "ssh.github.com"}:
            return parsed.path.lstrip("/").removesuffix(".git")
    # SCP-style git@github.com:owner/repo.git
    if url.startswith("git@github.com:"):
        return url.split(":", 1)[1].removesuffix(".git")
    print("ERROR: Cannot parse owner/repo from git remote origin URL.", file=sys.stderr)
    sys.exit(1)


def local_head_sha() -> str:
    """Return the SHA of the local HEAD commit."""
    return run(["git", "rev-parse", "HEAD"])


def staged_entries() -> tuple[list[tuple[str, str, str, Optional[str]]], set[str]]:
    """Return (entries, deleted_paths) where entries are (mode, path, blob_sha, old_path_or_None).

    Uses `git ls-files -s` after `git add -A` to read the staging index,
    preserving file mode (100644 regular, 100755 executable, 120000 symlink, 160000 gitlink)
    and detecting renames/deletions correctly. Blob SHAs come from the index, not the working tree.

    Returns list of (mode, path, blob_sha, old_path):
      - blob_sha is the object SHA from the index (guaranteed to match staged state)
      - old_path is set for renames (original path to delete from tree)
      - old_path is None for regular adds/modifications
      - For deletions, blob_sha is None

    Deleted files are detected by diffing HEAD vs. the index.
    """
    # Stage everything.
    run(["git", "add", "-A"])

    # Determine which paths are actually changed (bounds the tree payload to
    # only touched files — prevents sending the entire index to the API).
    changed_raw = run(["git", "diff", "--cached", "--name-only", "-z"])
    changed_paths = {p for p in changed_raw.split("\0") if p}

    if not changed_paths:
        print("ERROR: No changes staged. Nothing to commit.", file=sys.stderr)
        sys.exit(1)

    # ls-files -s: <mode> <object> <stage> <file>
    # Read the full index but keep only paths that appear in the cached diff.
    ls_output = run(["git", "ls-files", "-s"])
    staged: dict[str, tuple[str, str]] = {}  # path -> (mode, blob_sha)
    for line in ls_output.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta = parts[0].split()
        if len(meta) >= 2 and parts[1] in changed_paths:
            mode = meta[0]
            blob_sha = meta[1]
            staged[parts[1]] = (mode, blob_sha)

    # Find deleted files: in HEAD but not in staging index.
    try:
        head_files_raw = run(["git", "ls-tree", "-r", "--name-only", "HEAD"])
        head_files = set(head_files_raw.splitlines()) if head_files_raw else set()
    except SystemExit:
        # No HEAD yet (initial commit) — nothing can be deleted.
        head_files = set()

    staged_paths = set(staged.keys())
    deleted = head_files - staged_paths

    # Detect renames via diff-index: "R<score>\t<old>\t<new>"
    renames: dict[str, str] = {}  # new_path -> old_path
    diff_raw = subprocess.run(
        ["git", "diff", "--cached", "--diff-filter=R", "--name-status", "-M"],
        capture_output=True, text=True, check=False,
    )
    if diff_raw.returncode == 0:
        for line in diff_raw.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) == 3 and parts[0].startswith("R"):
                renames[parts[2]] = parts[1]

    # Exclude rename sources from deleted: the old path is already handled
    # via old_path on the rename target entry; adding it again would produce
    # duplicate tree entries and can cause the GitHub trees API request to fail.
    deleted -= set(renames.values())

    entries = []
    # Add/modify staged files.
    for path, (mode, blob_sha) in staged.items():
        old_path = renames.get(path)
        entries.append((mode, path, blob_sha, old_path))
    # Deleted files (blob_sha=None signals deletion).
    for path in deleted:
        entries.append(("100644", path, None, None))  # mode irrelevant for deletes

    return entries, deleted


# ---------------------------------------------------------------------------
# Core workflow
# ---------------------------------------------------------------------------

def resolve_base_ref(
    token: str, repo: str, branch: str, base: str, local_sha: str
) -> tuple[str, str, bool]:
    """Return (parent_commit_sha, base_tree_sha, branch_exists).

    If the branch already exists remotely, verifies that the remote SHA matches
    the local HEAD SHA — aborts if they differ to prevent silent clobbering.

    If the branch does not exist, verifies that local HEAD matches the remote
    base branch before starting from base — aborts if they diverge to prevent
    silently overwriting upstream changes.
    """
    ref = api_get_optional(token, f"/repos/{repo}/git/ref/heads/{branch}")
    if ref:
        remote_sha = ref["object"]["sha"]
        if remote_sha != local_sha:
            print(
                f"ERROR: Remote branch '{branch}' is at {remote_sha[:12]} but "
                f"local HEAD is {local_sha[:12]}. Pull or rebase before committing "
                f"to avoid silently clobbering remote changes.",
                file=sys.stderr,
            )
            sys.exit(1)
        commit = api(token, "GET", f"/repos/{repo}/git/commits/{remote_sha}")
        return remote_sha, commit["tree"]["sha"], True

    # Branch doesn't exist yet — verify local HEAD matches remote base before
    # using it as the parent, to prevent silently overwriting upstream changes.
    ref = api(token, "GET", f"/repos/{repo}/git/ref/heads/{base}")
    base_sha = ref["object"]["sha"]
    if base_sha != local_sha:
        print(
            f"ERROR: Base branch '{base}' is at {base_sha[:12]} but "
            f"local HEAD is {local_sha[:12]}. Fetch or rebase before committing "
            f"to avoid silently clobbering base changes.",
            file=sys.stderr,
        )
        sys.exit(1)
    commit = api(token, "GET", f"/repos/{repo}/git/commits/{base_sha}")
    return base_sha, commit["tree"]["sha"], False


def find_open_pr(token: str, repo: str, branch: str) -> Optional[str]:
    """Return the HTML URL of an existing open PR for this branch, or None."""
    owner = repo.split("/")[0]
    prs = api(token, "GET",
              f"/repos/{repo}/pulls?head={owner}:{branch}&state=open&per_page=1")
    if isinstance(prs, list) and prs:
        return prs[0]["html_url"]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a GitHub API commit (Verified) and optionally open a PR.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--repo", help="owner/repo (auto-detected from git remote if omitted)")
    parser.add_argument("--branch", required=True, help="Target branch name")
    parser.add_argument("--base", default="main", help="Base branch (default: main)")
    parser.add_argument("--message", required=True, help="Commit message")
    parser.add_argument("--pr-title", help="PR title (skips PR creation if omitted)")
    parser.add_argument("--pr-body", default="", help="PR body text")
    parser.add_argument("--author-name", default=DEFAULT_AUTHOR_NAME)
    parser.add_argument("--author-email", default=DEFAULT_AUTHOR_EMAIL)
    parser.add_argument("--no-signoff", action="store_true",
                        help="Disable automatic Signed-off-by trailer (signoff is on by default)")
    args = parser.parse_args()

    token = resolve_token()
    repo = args.repo or detect_repo()

    # Build commit message with optional signoff.
    message = args.message
    if not args.no_signoff:
        signoff = f"Signed-off-by: {args.author_name} <{args.author_email}>"
        if signoff not in message:
            message = f"{message}\n\n{signoff}"

    # 1. Capture local HEAD SHA before any staging (used for divergence check).
    local_sha = local_head_sha()

    # 2. Detect staged files with correct modes and blob SHAs (also runs git add -A).
    entries, deleted_paths = staged_entries()
    print(f"Changed files: {len(entries)} ({len(deleted_paths)} deleted)", file=sys.stderr)

    # 3. Resolve parent commit and base tree, verifying no remote divergence.
    parent_sha, base_tree_sha, branch_exists = resolve_base_ref(
        token, repo, args.branch, args.base, local_sha
    )

    # 4. Build tree entries from staged index (not working tree).
    # staged_entries() provides blob SHAs directly from the index, ensuring
    # the commit matches the staged state exactly (no filter/CRLF/LFS divergence).
    tree_entries = []
    for mode, path, blob_sha, old_path in entries:
        if blob_sha is None:
            # Deletion: set sha to null to remove from tree.
            tree_entries.append({
                "path": path,
                "mode": mode,
                "type": "blob",
                "sha": None,
            })
        else:
            # Use the blob SHA from the staging index directly.
            # This ensures the commit matches the exact staged state.
            obj_type = "commit" if mode == "160000" else ("blob" if mode != "120000" else "blob")
            tree_entries.append({
                "path": path,
                "mode": mode,
                "type": obj_type,
                "sha": blob_sha,
            })
            # For renames: also delete the old path.
            if old_path:
                tree_entries.append({
                    "path": old_path,
                    "mode": "100644",
                    "type": "blob",
                    "sha": None,
                })

    # 5. Create tree.
    tree = api(token, "POST", f"/repos/{repo}/git/trees", {
        "base_tree": base_tree_sha,
        "tree": tree_entries,
    })

    # 6. Create commit — GitHub marks this Verified automatically.
    commit = api(token, "POST", f"/repos/{repo}/git/commits", {
        "message": message,
        "tree": tree["sha"],
        "parents": [parent_sha],
        "author": {
            "name": args.author_name,
            "email": args.author_email,
        },
    })
    commit_sha = commit["sha"]

    # 7. Update or create the branch ref.
    if branch_exists:
        api(token, "PATCH", f"/repos/{repo}/git/refs/heads/{args.branch}", {
            "sha": commit_sha,
            "force": False,
        })
    else:
        api(token, "POST", f"/repos/{repo}/git/refs", {
            "ref": f"refs/heads/{args.branch}",
            "sha": commit_sha,
        })

    # 8. Optionally create a PR (reuses existing open PR if present).
    pr_url = ""
    if args.pr_title:
        existing = find_open_pr(token, repo, args.branch)
        if existing:
            pr_url = existing
            print(f"PR already exists: {pr_url}", file=sys.stderr)
        else:
            pr = api(token, "POST", f"/repos/{repo}/pulls", {
                "title": args.pr_title,
                "body": args.pr_body,
                "head": args.branch,
                "base": args.base,
            })
            pr_url = pr["html_url"]

    # 9. Structured output for agent consumption.
    print(f"commit={commit_sha}")
    print(f"branch={args.branch}")
    if pr_url:
        print(f"pr={pr_url}")


if __name__ == "__main__":
    main()

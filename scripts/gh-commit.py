#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""gh-commit — create a cryptographically Verified commit via the GitHub API
and optionally open a PR.

Replaces `git commit -S && git push && gh pr create` in agent workflows.

How signing works (and how it does not):

- A `Signed-off-by:` trailer (added by default here, as with `git commit -s`)
  is a DCO attestation in the commit message. It is NOT a cryptographic
  signature and never makes a commit show as "Verified" on its own.
- Commits created through the Git Data API are signed by GitHub only under
  narrow conditions: the request must NOT override `author`, `committer`, or
  `signature` (any override suppresses GitHub's own signature), and the token
  must be one GitHub signs API commits for — GitHub App installation tokens
  are; user PATs generally are not. With those conditions met, GitHub signs
  the commit itself and the API reports `verification.verified == true`.
- This script therefore omits author/committer/signature from the commit
  request entirely and FAILS CLOSED unless the API response reports
  `verification.verified` as exactly boolean `true`: it refuses to update or
  create any branch ref and refuses to open a PR. A successful HTTP response
  alone is never treated as proof of verification, and there is no fallback
  to a local unsigned `git commit` + push.
- `--signoff-name` / `--signoff-email` (legacy aliases: `--author-name` /
  `--author-email`) affect ONLY the DCO trailer in the commit message —
  never the commit's author or committer identity, which GitHub derives
  from the token.

Staging contract: this script commits exactly what is ALREADY staged in the
local index. It never runs `git add` — the caller stages the intended
changes first, so unrelated working-tree files cannot be swept into the
commit, and untouched tracked files are never mistaken for deletions.

Usage:
    gh-commit --branch <branch> --message "<msg>" [options]

    # Full example (auto-detects repo from git remote):
    gh-commit --branch ACM-1234 --base main \\
              --message "feat: add widget" \\
              --pr-title "feat: add widget" \\
              --pr-body "Jira: https://redhat.atlassian.net/browse/ACM-1234"

Token:
    GH_TOKEN (required) — must be a token whose API commits GitHub signs
    (a GitHub App installation token); otherwise every run fails closed.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

GITHUB_API = "https://api.github.com"
DEFAULT_SIGNOFF_NAME = "Swarm Agentic SDLC"
DEFAULT_SIGNOFF_EMAIL = "noreply@github.com"


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
            "User-Agent": "gh-commit/2.0",
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
            "User-Agent": "gh-commit/2.0",
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
    """Run a subprocess and return stdout as text, or exit on failure."""
    result = subprocess.run(args, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        # Only log command and exit code, not stderr (which may contain sensitive data).
        print(
            f"ERROR: {' '.join(args)} failed with exit code {result.returncode}",
            file=sys.stderr,
        )
        sys.exit(1)
    return result.stdout.strip()


def run_bytes(args: list[str], cwd: Optional[str] = None) -> bytes:
    """Run a subprocess and return stdout as raw bytes, or exit on failure."""
    result = subprocess.run(args, capture_output=True, cwd=cwd)
    if result.returncode != 0:
        print(
            f"ERROR: {' '.join(args)} failed with exit code {result.returncode}",
            file=sys.stderr,
        )
        sys.exit(1)
    return result.stdout


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


def staged_entries() -> tuple[list[tuple[str, str, str]], set[str]]:
    """Return (entries, deleted_paths) read from the ALREADY-STAGED index.

    This function never stages anything — no `git add` is run. The caller
    stages exactly the intended changes before invoking the script, so
    unrelated working-tree files can never be swept into the commit.

    Deletions come from the staged diff itself (`--diff-filter=D`), never
    from "in HEAD but not in the changed set" — that older heuristic treated
    every untouched tracked file as deleted whenever only a subset of files
    was staged.

    Returns:
      entries: list of (mode, path, blob_sha) for staged
        additions/modifications. blob_sha is the local index object SHA; the
        blob content must still be uploaded to GitHub (see upload_blob)
        because local blob SHAs are unknown to GitHub until uploaded.
      deleted_paths: set of paths staged for deletion (including rename
        source paths, which are removed via explicit deletion entries).
    """
    changed_raw = run(["git", "diff", "--cached", "--name-only", "-z"])
    changed_paths = [p for p in changed_raw.split("\0") if p]
    if not changed_paths:
        print(
            "ERROR: Nothing is staged. Stage the intended changes with "
            "`git add` first — this script never stages files itself and "
            "will not commit unstaged work.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Deletions staged in the index.
    deleted_raw = run(
        ["git", "diff", "--cached", "--diff-filter=D", "--name-only", "-z"]
    )
    deleted_paths = {p for p in deleted_raw.split("\0") if p}

    # Renames via cached diff: "R<score>\t<old>\t<new>"
    renames: dict[str, str] = {}  # new_path -> old_path
    rename_raw = run(
        ["git", "diff", "--cached", "--diff-filter=R", "--name-status", "-M"]
    )
    for line in rename_raw.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            renames[parts[2]] = parts[1]

    # Rename sources are removed from the tree via explicit deletion entries.
    deleted_paths |= set(renames.values())

    # ls-files -s: <mode> <object> <stage>\t<file> — read the full index but
    # keep only staged additions/modifications (rename sources and deletions
    # are legitimately absent from the index).
    wanted = set(changed_paths) - deleted_paths
    ls_output = run(["git", "ls-files", "-s"])
    entries: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for line in ls_output.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        meta = parts[0].split()
        if len(meta) < 2 or parts[1] not in wanted:
            continue
        entries.append((meta[0], parts[1], meta[1]))
        seen.add(parts[1])

    missing = wanted - seen
    if missing:
        print(
            "ERROR: Staged path(s) missing from the index: "
            f"{', '.join(sorted(missing))}",
            file=sys.stderr,
        )
        sys.exit(1)

    return entries, deleted_paths


def upload_blob(token: str, repo: str, blob_sha: str) -> str:
    """Upload the staged blob's content to GitHub and return its blob SHA.

    Local index blob SHAs are content-addressed but unknown to GitHub until
    they are uploaded, so every staged blob must go through the blobs API
    before it can be referenced from a tree. Uploading content that already
    exists remotely is idempotent — GitHub returns the same SHA.
    """
    content = run_bytes(["git", "cat-file", "blob", blob_sha])
    result = api(token, "POST", f"/repos/{repo}/git/blobs", {
        "content": base64.b64encode(content).decode(),
        "encoding": "base64",
    })
    return result["sha"]


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


def ref_still_at(
    token: str, repo: str, branch: str, base: str,
    branch_exists: bool, expected_sha: str,
) -> bool:
    """Re-read the target/base ref after commit creation, before publication.

    Guards against a concurrent push landing between the initial divergence
    check and the ref update: if anything moved, the caller must abort rather
    than overwrite or interleave unrelated work. The freshly created commit
    is simply left unattached (nothing points at it).
    """
    if branch_exists:
        ref = api_get_optional(token, f"/repos/{repo}/git/ref/heads/{branch}")
        return bool(ref) and ref["object"]["sha"] == expected_sha
    # Branch was expected to be new: it must still not exist, and the base
    # must still be where we built on it.
    if api_get_optional(token, f"/repos/{repo}/git/ref/heads/{branch}"):
        return False
    base_ref = api_get_optional(token, f"/repos/{repo}/git/ref/heads/{base}")
    return bool(base_ref) and base_ref["object"]["sha"] == expected_sha


def require_verified(commit: dict) -> None:
    """Fail closed unless GitHub reports the commit as cryptographically verified.

    A 2xx from the commit endpoint proves the commit object exists, not that
    it is signed — verification is a separate, explicit field that must be
    exactly boolean true. Anything else (false, null, missing, or a
    non-boolean value) means unsigned or unknown, and publication stops
    before any branch ref is touched and before any PR is created.
    """
    verification = commit.get("verification") or {}
    verified = verification.get("verified")
    if verified is not True:
        sha = str(commit.get("sha", "unknown"))
        print(
            f"ERROR: commit {sha[:12]} is not verified by GitHub "
            f"(verification.verified={verified!r}, "
            f"reason={verification.get('reason')!r}). The commit was NOT "
            f"attached to any branch and no PR was created. Do not fall back "
            f"to unsigned commits — resolve signing (use a token GitHub "
            f"signs API commits for, e.g. a GitHub App installation token, "
            f"and keep author/committer/signature unset) and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)


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
        description="Create a Verified GitHub API commit and optionally open a "
                    "PR. Fails closed unless GitHub verifies the commit "
                    "signature before any branch or PR is touched.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--repo", help="owner/repo (auto-detected from git remote if omitted)")
    parser.add_argument("--branch", required=True, help="Target branch name")
    parser.add_argument("--base", default="main", help="Base branch (default: main)")
    parser.add_argument("--message", required=True, help="Commit message")
    parser.add_argument("--pr-title", help="PR title (skips PR creation if omitted)")
    parser.add_argument("--pr-body", default="", help="PR body text")
    parser.add_argument("--signoff-name", "--author-name", dest="signoff_name",
                        default=DEFAULT_SIGNOFF_NAME,
                        help="Name for the Signed-off-by DCO trailer only — "
                             "never the commit author identity")
    parser.add_argument("--signoff-email", "--author-email", dest="signoff_email",
                        default=DEFAULT_SIGNOFF_EMAIL,
                        help="Email for the Signed-off-by DCO trailer only — "
                             "never the commit committer identity")
    parser.add_argument("--no-signoff", action="store_true",
                        help="Disable automatic Signed-off-by trailer (signoff is on by default)")
    args = parser.parse_args()

    token = resolve_token()
    repo = args.repo or detect_repo()

    # Build commit message with optional DCO signoff. The trailer is an
    # attestation in the message text, not a cryptographic signature.
    message = args.message
    if not args.no_signoff:
        signoff = f"Signed-off-by: {args.signoff_name} <{args.signoff_email}>"
        if signoff not in message:
            message = f"{message}\n\n{signoff}"

    # 1. Capture local HEAD SHA before anything else (used for divergence check).
    local_sha = local_head_sha()

    # 2. Read the already-staged index — this never stages anything itself.
    entries, deleted_paths = staged_entries()
    print(f"Staged files: {len(entries)} changed, {len(deleted_paths)} deleted",
          file=sys.stderr)

    # 3. Resolve parent commit and base tree, verifying no remote divergence.
    parent_sha, base_tree_sha, branch_exists = resolve_base_ref(
        token, repo, args.branch, args.base, local_sha
    )

    # 4. Build tree entries. Upload each staged blob first: local index blob
    #    SHAs are content-addressed but unknown to GitHub until uploaded.
    tree_entries = []
    for mode, path, blob_sha in entries:
        if mode == "160000":
            # Submodule gitlink: references a commit object, not a blob.
            tree_entries.append({
                "path": path,
                "mode": mode,
                "type": "commit",
                "sha": blob_sha,
            })
            continue
        remote_blob_sha = upload_blob(token, repo, blob_sha)
        tree_entries.append({
            "path": path,
            "mode": mode,
            "type": "blob",
            "sha": remote_blob_sha,
        })
    for path in sorted(deleted_paths):
        # Deletion: sha null removes the path from the base tree.
        tree_entries.append({
            "path": path,
            "mode": "100644",
            "type": "blob",
            "sha": None,
        })

    # 5. Create tree.
    tree = api(token, "POST", f"/repos/{repo}/git/trees", {
        "base_tree": base_tree_sha,
        "tree": tree_entries,
    })

    # 6. Create the commit WITHOUT author/committer/signature overrides.
    #    Overriding any identity field suppresses GitHub's own signature;
    #    omitting them lets GitHub derive the identity from the token and
    #    sign the commit (for token types it signs API commits for, e.g.
    #    GitHub App installation tokens).
    commit = api(token, "POST", f"/repos/{repo}/git/commits", {
        "message": message,
        "tree": tree["sha"],
        "parents": [parent_sha],
    })
    commit_sha = commit["sha"]

    # 7. Verification gate — fail closed BEFORE any branch or PR write.
    #    A successful API response alone does NOT mean the commit is signed.
    require_verified(commit)

    # 8. Re-check the remote ref before publication: abort if anything moved
    #    between the divergence check and now (concurrent push protection).
    #    The verified commit is left unattached rather than overwriting.
    if not ref_still_at(token, repo, args.branch, args.base, branch_exists, parent_sha):
        print(
            f"ERROR: Remote ref moved while the commit was being created — "
            f"expected {parent_sha[:12]}. The verified commit {commit_sha[:12]} "
            f"was left unattached; synchronize and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    # 9. Update or create the branch ref (never forced).
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

    # 10. Optionally create a PR (reuses existing open PR if present).
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

    # 11. Structured output for agent consumption.
    print(f"commit={commit_sha}")
    print(f"branch={args.branch}")
    if pr_url:
        print(f"pr={pr_url}")


if __name__ == "__main__":
    main()

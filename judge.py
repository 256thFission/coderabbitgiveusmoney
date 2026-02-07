#!/usr/bin/env python3
"""
judge.py — CodeRabbit AI Judge Pipeline

Forks each HVT's top repo, creates a PR showing the full codebase,
comments @coderabbitai with a Linus Torvalds judging prompt, polls
for responses, and saves grades/verdicts/badges.

Prerequisites:
    1. Run precompute.py first to populate precomputed.json.
    2. Set GITHUB_TOKENS in .env (same as precompute.py).
    3. Set CODERABBIT_API_KEY in .env (for the aggregate report).
    4. Ensure CodeRabbit GitHub App is installed on your account
       with "All repositories" access so it reviews forks.

Usage:
    python judge.py                  # Run full pipeline
    python judge.py --phase fork     # Only fork repos
    python judge.py --phase pr       # Only create PRs
    python judge.py --phase comment  # Only post judging comments
    python judge.py --phase poll     # Only poll for responses
    python judge.py --phase report   # Only generate aggregate report
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GITHUB_API = "https://api.github.com"
CODERABBIT_API = "https://api.coderabbit.ai/api/v1"
PRECOMPUTED_FILE = Path("precomputed.json")
STATE_FILE = Path("judge_state.json")
RESULTS_FILE = Path("judge_results.json")
ORPHAN_BRANCH = "wall-of-shame-baseline"
POLL_INTERVAL = 30  # seconds between polls
POLL_TIMEOUT = 600  # 10 minutes max wait per PR

# ---------------------------------------------------------------------------
# Auth — use a single ADMIN token for all write operations (fork/PR/comment)
# ---------------------------------------------------------------------------
ADMIN_TOKEN = os.environ.get("ADMIN", "")
if not ADMIN_TOKEN:
    sys.exit("ERROR: ADMIN env var not set. Add your GitHub PAT to .env as ADMIN=ghp_...")

CODERABBIT_API_KEY = os.environ.get("CODERABBIT_API_KEY", "")

# ---------------------------------------------------------------------------
# The Judging Prompt
# ---------------------------------------------------------------------------
JUDGE_PROMPT = """@coderabbitai

Act as Linus Torvalds reviewing this entire repository. Be brutally honest and technically specific.

Analyze ALL the code visible in this pull request diff and provide your evaluation in **exactly** this JSON format inside a fenced code block:

```json
{
  "grade": "<letter grade from F- to A+>",
  "verdict": "<A savage, technical one-liner roast. Reference specific code patterns or files you see. No emojis. Max 200 chars.>",
  "badge": "<One humorous badge they deserve, e.g. Over-Engineered, Copy-Paste Artisan, Dependency Hoarder>"
}
```

**Grading rubric:**
- **A range**: Genuinely impressive — clean architecture, good tests, thoughtful error handling
- **B range**: Competent but unremarkable — works fine, nothing exciting
- **C range**: Mediocre — works but has obvious issues (no tests, messy structure, etc.)
- **D range**: Barely functional — poor organization, no docs, questionable decisions
- **F range**: Actively harmful to anyone who reads it

**What to evaluate:**
1. Code organization and architecture
2. Error handling (try-catch? or YOLO?)
3. Documentation quality (README, comments)
4. Dependency hygiene (200 deps for a todo app?)
5. Naming conventions (meaningful or `x`, `temp`, `asdf`?)
6. Testing (any tests at all?)
7. Overall engineering taste

Be harsh but fair. Every roast MUST reference something real in the code. Do not be generic."""


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------
GITHUB_HEADERS = {
    "Authorization": f"Bearer {ADMIN_TOKEN}",
    "Accept": "application/vnd.github+json",
}


def gh(method: str, path: str, retries: int = 3, **kwargs) -> requests.Response:
    """Make a GitHub REST API call with retries using the ADMIN token."""
    url = f"{GITHUB_API}{path}" if path.startswith("/") else path
    for attempt in range(retries):
        resp = requests.request(method, url, headers=GITHUB_HEADERS, timeout=30, **kwargs)
        if resp.status_code in (502, 503, 429):
            wait = 2 ** attempt
            print(f"  GitHub {resp.status_code}, retry in {wait}s…")
            time.sleep(wait)
            continue
        return resp
    return resp  # return last attempt even if failed


def get_auth_user() -> str:
    """Get the authenticated GitHub username."""
    resp = gh("GET", "/user")
    resp.raise_for_status()
    return resp.json()["login"]


# ---------------------------------------------------------------------------
# State management (resumable pipeline)
# ---------------------------------------------------------------------------
def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Phase 1: Fork repos
# ---------------------------------------------------------------------------
def fork_repo(owner: str, repo: str, auth_user: str) -> str | None:
    """Fork a repo. Returns the fork's full_name or None on failure."""
    # Check if fork already exists
    resp = gh("GET", f"/repos/{auth_user}/{repo}")
    if resp.status_code == 200 and resp.json().get("fork"):
        return resp.json()["full_name"]

    # Create fork
    resp = gh("POST", f"/repos/{owner}/{repo}/forks", json={})
    if resp.status_code in (200, 202):
        return resp.json()["full_name"]

    # Handle 404 (repo doesn't exist or is private)
    if resp.status_code == 404:
        print(f"  404 — repo not found or private")
        return None

    print(f"  Fork failed: {resp.status_code} {resp.text[:200]}")
    return None


def phase_fork(precomputed: dict, state: dict) -> dict:
    """Fork all HVT top repos."""
    auth_user = get_auth_user()
    print(f"\n{'='*60}")
    print(f"PHASE 1: FORKING REPOS (as {auth_user})")
    print(f"{'='*60}")

    for username, data in precomputed.items():
        user_state = state.get(username, {})
        if user_state.get("fork_name"):
            continue

        top_repos = data.get("top_repos", [])
        if not top_repos:
            print(f"  [{username}] No repos — skipping")
            continue

        repo_name = top_repos[0]
        print(f"  [{username}] Forking {username}/{repo_name}…", end=" ", flush=True)

        fork_name = fork_repo(username, repo_name, auth_user)
        if fork_name:
            print(f"→ {fork_name}")
            state.setdefault(username, {})["fork_name"] = fork_name
            state[username]["repo_name"] = repo_name
        else:
            print("FAILED")
            state.setdefault(username, {})["error"] = "fork_failed"

        save_state(state)
        time.sleep(2)  # Be nice — forks are expensive operations

    return state


# ---------------------------------------------------------------------------
# Phase 2: Create orphan branches + PRs
# ---------------------------------------------------------------------------
def create_base_branch(fork_name: str, default_branch: str) -> str | None:
    """Create a branch from the repo's oldest reachable commit.

    This ensures common history with the default branch so GitHub allows
    a PR between them. The diff will show ~all code as additions.
    """
    # Get the oldest commit by fetching the last page of commits
    resp = gh("GET", f"/repos/{fork_name}/commits",
              params={"sha": default_branch, "per_page": 1})
    if resp.status_code != 200:
        print(f"  Failed to list commits: {resp.status_code}")
        return None

    # Follow the 'last' link to find the initial commit
    link_header = resp.headers.get("Link", "")
    oldest_sha = None

    if "last" in link_header:
        # Extract last page URL
        import re as _re
        last_match = _re.search(r'<([^>]+)>;\s*rel="last"', link_header)
        if last_match:
            last_resp = gh("GET", last_match.group(1))
            if last_resp.status_code == 200 and last_resp.json():
                oldest_sha = last_resp.json()[-1]["sha"]

    if not oldest_sha:
        # Small repo — the first request already has the only commit(s)
        commits = resp.json()
        if commits:
            oldest_sha = commits[-1]["sha"]

    if not oldest_sha:
        print(f"  No commits found")
        return None

    # Create or update branch pointing to the oldest commit
    resp = gh("POST", f"/repos/{fork_name}/git/refs", json={
        "ref": f"refs/heads/{ORPHAN_BRANCH}",
        "sha": oldest_sha,
    })
    if resp.status_code == 422:
        resp = gh("PATCH", f"/repos/{fork_name}/git/refs/heads/{ORPHAN_BRANCH}",
                  json={"sha": oldest_sha, "force": True})
    if resp.status_code not in (200, 201):
        print(f"  Failed to create branch: {resp.status_code} {resp.text[:200]}")
        return None

    return oldest_sha


def create_pr(fork_name: str, default_branch: str) -> int | None:
    """Create a PR from default branch → orphan branch. Returns PR number."""
    owner = fork_name.split("/")[0]

    # Check for existing open PR
    resp = gh("GET", f"/repos/{fork_name}/pulls", params={
        "head": f"{owner}:{default_branch}",
        "base": ORPHAN_BRANCH,
        "state": "open",
    })
    if resp.status_code == 200:
        prs = resp.json()
        if prs:
            return prs[0]["number"]

    # Create new PR
    resp = gh("POST", f"/repos/{fork_name}/pulls", json={
        "title": "Wall of Shame: Full Repository Code Review",
        "head": default_branch,
        "base": ORPHAN_BRANCH,
        "body": (
            "Automated full-codebase review for the **Wall of Shame** hackathon project.\n\n"
            "This PR diffs the entire repository against an empty baseline so CodeRabbit "
            "can analyze all the code at once."
        ),
    })
    if resp.status_code in (200, 201):
        return resp.json()["number"]

    print(f"  PR creation failed: {resp.status_code} {resp.text[:200]}")
    return None


def phase_pr(precomputed: dict, state: dict) -> dict:
    """Create orphan branches and PRs for all forked repos."""
    print(f"\n{'='*60}")
    print(f"PHASE 2: CREATING PRS")
    print(f"{'='*60}")

    for username in precomputed:
        user_state = state.get(username, {})
        fork_name = user_state.get("fork_name")
        if not fork_name:
            continue
        if user_state.get("pr_number"):
            continue

        print(f"  [{username}] {fork_name}…", end=" ", flush=True)

        # Get default branch
        resp = gh("GET", f"/repos/{fork_name}")
        if resp.status_code != 200:
            print(f"Fork not ready yet ({resp.status_code})")
            continue
        default_branch = resp.json()["default_branch"]

        # Create base branch from oldest commit
        sha = create_base_branch(fork_name, default_branch)
        if not sha:
            print("orphan branch failed")
            continue

        # Create PR
        pr_num = create_pr(fork_name, default_branch)
        if pr_num:
            print(f"PR #{pr_num}")
            state[username]["pr_number"] = pr_num
            state[username]["default_branch"] = default_branch
        else:
            print("PR failed")

        save_state(state)
        time.sleep(1)

    return state


# ---------------------------------------------------------------------------
# Phase 3: Post judging comments
# ---------------------------------------------------------------------------
def phase_comment(precomputed: dict, state: dict) -> dict:
    """Post @coderabbitai judging comments on all PRs."""
    print(f"\n{'='*60}")
    print(f"PHASE 3: POSTING JUDGING COMMENTS")
    print(f"{'='*60}")

    for username in precomputed:
        user_state = state.get(username, {})
        if not user_state.get("pr_number"):
            continue
        if user_state.get("comment_posted"):
            continue

        fork_name = user_state["fork_name"]
        pr_number = user_state["pr_number"]
        print(f"  [{username}] Commenting on {fork_name} PR #{pr_number}…", end=" ", flush=True)

        # First: trigger CodeRabbit to actually review (it skips non-default base branches)
        gh("POST", f"/repos/{fork_name}/issues/{pr_number}/comments",
           json={"body": "@coderabbitai review"})
        time.sleep(2)

        # Second: post the judging prompt
        resp = gh("POST", f"/repos/{fork_name}/issues/{pr_number}/comments",
                  json={"body": JUDGE_PROMPT})

        if resp.status_code in (200, 201):
            print("OK")
            state[username]["comment_posted"] = True
            state[username]["comment_time"] = datetime.now(timezone.utc).isoformat()
        else:
            print(f"FAILED ({resp.status_code})")

        save_state(state)
        time.sleep(1)

    return state


# ---------------------------------------------------------------------------
# Phase 4: Poll for CodeRabbit responses
# ---------------------------------------------------------------------------
def parse_coderabbit_response(body: str) -> dict:
    """Extract grade, verdict, badge from CodeRabbit's markdown response."""
    # Strategy 1: JSON code block
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", body, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return {
                "quality_grade": str(data.get("grade", "Pending")),
                "verdict": str(data.get("verdict", "Pending review...")),
                "coderabbit_badge": str(data.get("badge", "Unknown")),
            }
        except json.JSONDecodeError:
            pass

    # Strategy 2: Look for bold-labelled fields
    grade = re.search(r"\*\*(?:GRADE|Grade|grade)\*\*[:\s]*([A-F][+-]?)", body)
    verdict = re.search(r"\*\*(?:VERDICT|Verdict|verdict)\*\*[:\s]*\"?([^\"\\n]+)\"?", body)
    badge = re.search(r"\*\*(?:BADGE|Badge|badge)\*\*[:\s]*\"?([^\"\\n]+)\"?", body)

    # Strategy 3: Loose search
    if not grade:
        grade = re.search(r"(?:grade|Grade)[:\s]+([A-F][+-]?)", body)
    if not verdict:
        verdict = re.search(r"(?:verdict|Verdict)[:\s]+\"([^\"]+)\"", body)
    if not badge:
        badge = re.search(r"(?:badge|Badge)[:\s]+\"?([A-Za-z][^\"\\n]{2,40})\"?", body)

    return {
        "quality_grade": grade.group(1) if grade else "Pending",
        "verdict": verdict.group(1).strip() if verdict else extract_first_roast(body),
        "coderabbit_badge": badge.group(1).strip() if badge else "Unknown",
    }


def extract_first_roast(body: str) -> str:
    """Fallback: grab the first sentence that looks like a roast."""
    sentences = re.split(r"[.!]\s", body)
    for s in sentences:
        s = s.strip()
        if len(s) > 30 and not s.startswith(("I", "The PR", "This pull", "Here")):
            return s[:200]
    return "Pending review…"


def phase_poll(precomputed: dict, state: dict) -> dict:
    """Poll for CodeRabbit responses on all commented PRs."""
    print(f"\n{'='*60}")
    print(f"PHASE 4: POLLING FOR CODERABBIT RESPONSES")
    print(f"{'='*60}")

    pending = []
    for username in precomputed:
        user_state = state.get(username, {})
        if not user_state.get("comment_posted"):
            continue
        if user_state.get("response_parsed"):
            continue
        pending.append(username)

    if not pending:
        print("  No pending responses to poll.")
        return state

    print(f"  Waiting for {len(pending)} responses…\n")
    start = time.time()

    while pending and (time.time() - start) < POLL_TIMEOUT:
        still_pending = []
        for username in pending:
            user_state = state[username]
            fork_name = user_state["fork_name"]
            pr_number = user_state["pr_number"]
            since = user_state.get("comment_time", "2026-01-01T00:00:00Z")

            resp = gh("GET", f"/repos/{fork_name}/issues/{pr_number}/comments",
                      params={"since": since})
            if resp.status_code != 200:
                still_pending.append(username)
                continue

            found = False
            for comment in resp.json():
                login = comment["user"]["login"].lower()
                if "coderabbit" not in login:
                    continue
                body = comment["body"]
                # Skip auto-generated status/action comments
                skip_phrases = [
                    "auto-generated comment",
                    "Review skipped",
                    "Actions performed",
                    "Review triggered",
                    "finishing_touch_checkbox",
                ]
                if any(phrase in body for phrase in skip_phrases):
                    continue
                if len(body) < 200:
                    continue
                if True:
                    result = parse_coderabbit_response(body)
                    print(f"  [{username}] ✓ Grade: {result['quality_grade']}  "
                          f"Badge: {result['coderabbit_badge']}")
                    state[username]["response_parsed"] = True
                    state[username]["result"] = result
                    state[username]["raw_response"] = body
                    save_state(state)
                    found = True
                    break

            if not found:
                still_pending.append(username)

        pending = still_pending
        if pending:
            elapsed = int(time.time() - start)
            print(f"  … {len(pending)} still waiting ({elapsed}s elapsed)")
            time.sleep(POLL_INTERVAL)

    if pending:
        print(f"\n  Timed out on {len(pending)} users: {pending}")
        for username in pending:
            state[username]["result"] = {
                "quality_grade": "Pending",
                "verdict": "Pending review…",
                "coderabbit_badge": "Unknown",
            }
            save_state(state)

    return state


# ---------------------------------------------------------------------------
# Phase 5: Aggregate CodeRabbit report (bonus)
# ---------------------------------------------------------------------------
def phase_report(precomputed: dict, state: dict) -> dict:
    """Call the CodeRabbit Reports API for an aggregate Wall of Shame report."""
    if not CODERABBIT_API_KEY:
        print("\n  CODERABBIT_API_KEY not set — skipping aggregate report.")
        return state

    print(f"\n{'='*60}")
    print(f"PHASE 5: GENERATING AGGREGATE REPORT")
    print(f"{'='*60}")

    # Collect all fork repo names
    fork_repos = []
    for username in precomputed:
        user_state = state.get(username, {})
        fork_name = user_state.get("fork_name")
        if fork_name:
            fork_repos.append(fork_name.split("/")[1])

    prompt = (
        "You are Linus Torvalds compiling the ultimate Wall of Shame.\n\n"
        "For each repository in this report, analyze CodeRabbit's review findings "
        "and provide:\n"
        "1. A Code Quality Grade (F- to A+)\n"
        "2. A savage one-liner roast referencing real code issues\n"
        "3. A humorous badge they deserve\n\n"
        "Format each entry as a markdown table row:\n"
        "| Repository | Grade | Verdict | Badge |\n\n"
        "Be brutally honest. No emojis.\n\n"
        "<include_bot_comments>"
    )

    try:
        resp = requests.post(
            f"{CODERABBIT_API}/report.generate",
            headers={
                "x-coderabbitai-api-key": CODERABBIT_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "from": "2026-01-01",
                "to": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "promptTemplate": "Custom",
                "prompt": prompt,
                "groupBy": "REPOSITORY",
            },
            timeout=600,
        )

        if resp.status_code == 200:
            report = resp.json()
            report_file = Path("coderabbit_report.json")
            report_file.write_text(json.dumps(report, indent=2))
            print(f"  Report saved to {report_file}")
        else:
            print(f"  Report API returned {resp.status_code}: {resp.text[:300]}")

    except Exception as e:
        print(f"  Report API error: {e}")

    return state


# ---------------------------------------------------------------------------
# Export: merge precomputed + judge results → judge_results.json
# ---------------------------------------------------------------------------
def export_results(precomputed: dict, state: dict) -> None:
    """Write judge_results.json with CodeRabbit grades."""
    results = {}
    for username in precomputed:
        user_state = state.get(username, {})
        result = user_state.get("result", {
            "quality_grade": "Pending",
            "verdict": "Pending review…",
            "coderabbit_badge": "Unknown",
        })
        results[username] = result

    RESULTS_FILE.write_text(json.dumps(results, indent=2))

    graded = sum(1 for r in results.values() if r["quality_grade"] not in ("Pending", "Error"))
    print(f"\n{'='*60}")
    print(f"RESULTS: {graded}/{len(results)} users graded")
    print(f"Saved to {RESULTS_FILE}")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="CodeRabbit AI Judge Pipeline")
    parser.add_argument("--phase", choices=["fork", "pr", "comment", "poll", "report", "all"],
                        default="all", help="Run a specific phase (default: all)")
    args = parser.parse_args()

    if not PRECOMPUTED_FILE.exists():
        sys.exit(f"ERROR: {PRECOMPUTED_FILE} not found. Run precompute.py first.")

    precomputed = json.loads(PRECOMPUTED_FILE.read_text())
    state = load_state()

    print(f"Wall of Shame — CodeRabbit Judge Pipeline")
    print(f"Users: {len(precomputed)}  |  Token: ADMIN  |  Phase: {args.phase}")

    phases = {
        "fork": [phase_fork],
        "pr": [phase_pr],
        "comment": [phase_comment],
        "poll": [phase_poll],
        "report": [phase_report],
        "all": [phase_fork, phase_pr, phase_comment, phase_poll, phase_report],
    }

    for phase_fn in phases[args.phase]:
        state = phase_fn(precomputed, state)

    export_results(precomputed, state)


if __name__ == "__main__":
    main()

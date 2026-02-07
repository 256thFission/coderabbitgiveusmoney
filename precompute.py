#!/usr/bin/env python3
"""
Precompute scraper — fetches GitHub profile data for a list of usernames
via the GraphQL API with multi-token rotation and resumability.

Usage:
    1. Copy .env.example to .env and fill in your GitHub tokens.
    2. Populate usernames.txt (one username per line).
    3. conda env create -f environment.yml && conda activate coderabbit
    4. python precompute.py
"""

import itertools
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()

GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"
USERNAMES_FILE = Path("usernames.txt")
OUTPUT_FILE = Path("precomputed.json")

# ---------------------------------------------------------------------------
# Token rotation
# ---------------------------------------------------------------------------
raw_tokens = os.environ.get("GITHUB_TOKENS", "")
if not raw_tokens:
    sys.exit("ERROR: GITHUB_TOKENS not set. Copy .env.example to .env and add your tokens.")

tokens: list[str] = [t.strip() for t in raw_tokens.split(",") if t.strip()]
token_cycle = itertools.cycle(tokens)
token_cooldowns: dict[str, float] = {}  # token -> reset_timestamp


def get_next_headers() -> dict[str, str]:
    """Return Authorization headers using the next available token (round-robin)."""
    now = time.time()
    for _ in range(len(tokens)):
        token = next(token_cycle)
        if token_cooldowns.get(token, 0) <= now:
            return {"Authorization": f"bearer {token}"}
    # All tokens exhausted — sleep until the earliest reset
    earliest = min(token_cooldowns.values())
    wait = max(0, earliest - now + 1)
    print(f"  All tokens exhausted. Sleeping {wait:.0f}s until rate-limit reset…")
    time.sleep(wait)
    return get_next_headers()


def record_rate_limit(token_header: str, response: requests.Response) -> None:
    """Check response headers and record cooldown if a token is exhausted."""
    remaining = response.headers.get("X-RateLimit-Remaining")
    reset_at = response.headers.get("X-RateLimit-Reset")
    if remaining is not None and int(remaining) == 0 and reset_at is not None:
        # Extract the raw token from the header
        raw = token_header.replace("bearer ", "")
        token_cooldowns[raw] = float(reset_at)
        print(f"  Token …{raw[-4:]} exhausted. Will reset at {datetime.fromtimestamp(float(reset_at), tz=timezone.utc).isoformat()}")


# ---------------------------------------------------------------------------
# GraphQL query
# ---------------------------------------------------------------------------
PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    login
    name
    bio
    company
    location
    followers {
      totalCount
    }
    repositories(first: 10, orderBy: {field: STARGAZERS, direction: DESC}, ownerAffiliations: OWNER) {
      nodes {
        name
        stargazerCount
        primaryLanguage { name }
        description
      }
      totalCount
    }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
    }
  }
}
"""

RECENT_COMMITS_QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 5, orderBy: {field: PUSHED_AT, direction: DESC}, ownerAffiliations: OWNER) {
      nodes {
        name
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 10, author: {id: null}) {
                nodes {
                  message
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

# Simpler commit query that doesn't filter by author (works without user node ID)
RECENT_COMMITS_QUERY_SIMPLE = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 5, orderBy: {field: PUSHED_AT, direction: DESC}, ownerAffiliations: OWNER) {
      nodes {
        name
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 10) {
                nodes {
                  message
                  author {
                    user { login }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

# ---------------------------------------------------------------------------
# Emoji scoring
# ---------------------------------------------------------------------------
EMOJI_RE = re.compile(
    "["
    "\U0001f600-\U0001f64f"  # emoticons
    "\U0001f300-\U0001f5ff"  # symbols & pictographs
    "\U0001f680-\U0001f6ff"  # transport & map
    "\U0001f1e0-\U0001f1ff"  # flags
    "\U00002702-\U000027b0"
    "\U000024c2-\U0001f251"
    "]+",
    flags=re.UNICODE,
)

# Also count GitHub-style :emoji: shortcodes
SHORTCODE_RE = re.compile(r":[a-z0-9_+-]+:")


def count_emojis(texts: list[str]) -> int:
    total = 0
    for t in texts:
        total += len(EMOJI_RE.findall(t))
        total += len(SHORTCODE_RE.findall(t))
    return total


# ---------------------------------------------------------------------------
# Scraping logic
# ---------------------------------------------------------------------------
MAX_RETRIES = 5
INITIAL_BACKOFF = 0.5  # seconds


def graphql(query: str, variables: dict) -> dict:
    """Execute a GitHub GraphQL query with token rotation and exponential backoff."""
    for attempt in range(MAX_RETRIES):
        headers = get_next_headers()
        resp = requests.post(
            GITHUB_GRAPHQL_URL,
            json={"query": query, "variables": variables},
            headers=headers,
            timeout=30,
        )
        record_rate_limit(headers["Authorization"], resp)

        if resp.status_code in (502, 503, 429):
            wait = INITIAL_BACKOFF * (2 ** attempt)
            print(f"  GitHub returned {resp.status_code}, retrying in {wait:.1f}s…")
            time.sleep(wait)
            continue

        resp.raise_for_status()
        data = resp.json()
        if "errors" in data:
            raise RuntimeError(f"GraphQL errors: {data['errors']}")
        return data

    resp.raise_for_status()  # final attempt failed — raise
    return {}  # unreachable


def scrape_user(username: str) -> dict | None:
    """Fetch profile + recent commits for a single user. Returns dict or None on 404."""
    try:
        profile_data = graphql(PROFILE_QUERY, {"login": username})
    except RuntimeError as e:
        if "Could not resolve to a User" in str(e):
            return None
        raise

    user = profile_data["data"]["user"]
    if user is None:
        return None

    # Aggregate stars
    total_stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])
    top_repos = [r["name"] for r in user["repositories"]["nodes"]]

    contributions = user["contributionsCollection"]
    commits_last_year = (
        contributions["totalCommitContributions"]
        + contributions["restrictedContributionsCount"]
    )

    # Fetch recent commit messages for emoji scoring
    commit_messages: list[str] = []
    try:
        commits_data = graphql(RECENT_COMMITS_QUERY_SIMPLE, {"login": username})
        repos = commits_data["data"]["user"]["repositories"]["nodes"]
        for repo in repos:
            ref = repo.get("defaultBranchRef")
            if not ref:
                continue
            target = ref.get("target")
            if not target:
                continue
            history = target.get("history", {}).get("nodes", [])
            for commit in history:
                # Only count commits authored by this user
                author_user = (commit.get("author") or {}).get("user")
                if author_user and author_user.get("login", "").lower() == username.lower():
                    commit_messages.append(commit["message"])
    except Exception:
        pass  # Non-critical — emoji score defaults to 0

    emoji_score = count_emojis(commit_messages)

    return {
        "stars": total_stars,
        "commits_last_year": commits_last_year,
        "emoji_score": emoji_score,
        "top_repos": top_repos,
        "bio": user.get("bio") or "",
        "name": user.get("name") or "",
        "company": user.get("company") or "",
        "location": user.get("location") or "",
        "followers": user["followers"]["totalCount"],
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def load_usernames() -> list[str]:
    if not USERNAMES_FILE.exists():
        sys.exit(f"ERROR: {USERNAMES_FILE} not found. Create it with one username per line.")
    lines = USERNAMES_FILE.read_text().splitlines()
    names = []
    seen = set()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        lower = line.lower()
        if lower not in seen:
            seen.add(lower)
            names.append(line)
    return names


def load_existing() -> dict:
    if OUTPUT_FILE.exists():
        return json.loads(OUTPUT_FILE.read_text())
    return {}


def save(data: dict) -> None:
    OUTPUT_FILE.write_text(json.dumps(data, indent=2))


def main() -> None:
    usernames = load_usernames()
    print(f"Loaded {len(usernames)} usernames from {USERNAMES_FILE}")
    print(f"Using {len(tokens)} GitHub token(s)")

    existing = load_existing()
    already = sum(1 for u in usernames if u.lower() in {k.lower() for k in existing})
    if already:
        print(f"Resuming — {already} already scraped, {len(usernames) - already} remaining")

    existing_lower = {k.lower(): k for k in existing}

    for i, username in enumerate(usernames, 1):
        if username.lower() in existing_lower:
            continue

        print(f"[{i}/{len(usernames)}] Scraping {username}…", end=" ", flush=True)
        try:
            result = scrape_user(username)
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        if result is None:
            print("NOT FOUND (skipped)")
            continue

        existing[username] = result
        save(existing)
        print(f"OK — {result['stars']}★  {result['commits_last_year']} commits  {result['emoji_score']} emoji")

    print(f"\nDone. {len(existing)} users saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

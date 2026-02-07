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
RAW_DATA_DIR = Path("raw_data")

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
# Fetches comprehensive commit history: 100 repos, 100 commits per repo
RECENT_COMMITS_QUERY_SIMPLE = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 100, orderBy: {field: PUSHED_AT, direction: DESC}, ownerAffiliations: OWNER) {
      nodes {
        name
        defaultBranchRef {
          target {
            ... on Commit {
              history(first: 100) {
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

README_QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(first: 10, orderBy: {field: STARGAZERS, direction: DESC}, ownerAffiliations: OWNER) {
      nodes {
        name
        object(expression: "HEAD:README.md") {
          ... on Blob {
            text
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
# Toxicity detection
# ---------------------------------------------------------------------------
_detoxify_model = None


def get_toxicity_model():
    """Lazy-load the Detoxify model to avoid startup overhead."""
    global _detoxify_model
    if _detoxify_model is None:
        from detoxify import Detoxify

        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _detoxify_model = Detoxify("original", device=device)
        print(f"    Toxicity model loaded on {device}")
    return _detoxify_model


def find_worst_commit(texts: list[str]) -> dict | None:
    """
    Analyze toxicity in individual commit messages.
    Returns dict with the worst commit (highest score on any axis).
    Returns None if no commits available or analysis fails.
    """
    if not texts:
        return None

    try:
        model = get_toxicity_model()
        results = model.predict(texts)

        # Define toxicity axes
        axes = ["toxicity", "severe_toxicity", "obscene", "threat", "insult", "identity_attack"]

        # Find the worst commit (highest score on any axis)
        worst_idx = None
        worst_axis = None
        worst_score = 0.0

        for idx, text in enumerate(texts):
            for axis in axes:
                score = float(results[axis][idx])
                if score > worst_score:
                    worst_score = score
                    worst_idx = idx
                    worst_axis = axis

        if worst_idx is None:
            return None

        # Get all scores for the worst commit
        worst_text = texts[worst_idx]
        all_scores = {axis: float(results[axis][worst_idx]) for axis in axes}

        return {
            "message": worst_text,
            "toxicity_axis": worst_axis,
            "toxicity_score": worst_score,
            "all_scores": all_scores,
        }
    except Exception as e:
        print(f"    Finding worst commit failed: {e}")
        return None


def analyze_toxicity(texts: list[str]) -> dict:
    """
    Analyze toxicity in a list of texts (commit messages).
    Returns dict with averaged toxicity scores.
    Returns all zeros if input is empty or model fails.
    """
    keys = ["toxicity", "severe_toxicity", "obscene", "threat", "insult", "identity_attack"]
    zero = {k: 0.0 for k in keys}
    zero["worst_commit_toxicity"] = 0.0
    zero["worst_commit_msg"] = ""

    if not texts:
        return zero

    try:
        import torch
        model = get_toxicity_model()
        all_scores = {k: [] for k in keys}

        # Process in small batches to avoid CUDA OOM
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            with torch.no_grad():
                results = model.predict(batch)
            for k in keys:
                all_scores[k].extend(results[k])

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Find the single most toxic commit
        tox = all_scores["toxicity"]
        worst_idx = max(range(len(tox)), key=lambda i: tox[i])

        avg = {
            k: float(sum(all_scores[k]) / len(all_scores[k]))
            for k in keys
        }
        avg["worst_commit_toxicity"] = float(tox[worst_idx])
        avg["worst_commit_msg"] = texts[worst_idx]
        return avg
    except Exception as e:
        print(f"    Toxicity analysis failed: {e}")
        return zero


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

    # Fetch READMEs for emoji scoring
    readme_texts: list[str] = []
    readme_dict: dict[str, str] = {}  # Store {repo_name: readme_content}
    try:
        readme_data = graphql(README_QUERY, {"login": username})
        repos = readme_data["data"]["user"]["repositories"]["nodes"]
        for repo in repos:
            repo_name = repo.get("name", "unknown")
            obj = repo.get("object")
            if obj and "text" in obj:
                readme_content = obj["text"]
                readme_texts.append(readme_content)
                readme_dict[repo_name] = readme_content
    except Exception:
        pass  # Non-critical — defaults to empty list/dict

    # Combine emoji counts from commits AND READMEs
    emoji_score = count_emojis(commit_messages + readme_texts)

    # Analyze toxicity in commit messages
    toxicity_scores = analyze_toxicity(commit_messages)

    # Find worst commit (highest toxicity on any axis)
    worst_commit = find_worst_commit(commit_messages)

    # Save raw data for future analysis
    save_raw_data(username, commit_messages, readme_dict, worst_commit)

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
        "toxicity": toxicity_scores["toxicity"],
        "severe_toxicity": toxicity_scores["severe_toxicity"],
        "obscene": toxicity_scores["obscene"],
        "threat": toxicity_scores["threat"],
        "insult": toxicity_scores["insult"],
        "identity_attack": toxicity_scores["identity_attack"],
        "worst_commit_toxicity": toxicity_scores["worst_commit_toxicity"],
        "worst_commit_msg": toxicity_scores["worst_commit_msg"],
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


def save_raw_data(username: str, commit_messages: list[str], readme_data: dict, worst_commit: dict | None = None) -> None:
    """
    Save raw commit messages, README content, and worst commit to user-specific directory.

    Args:
        username: GitHub username
        commit_messages: List of commit message strings
        readme_data: Dict of {repo_name: readme_content}
        worst_commit: Dict from find_worst_commit() or None
    """
    user_dir = RAW_DATA_DIR / username
    user_dir.mkdir(parents=True, exist_ok=True)

    # Save commits
    commits_file = user_dir / "commits.json"
    commits_file.write_text(json.dumps(commit_messages, indent=2))

    # Save READMEs
    readmes_file = user_dir / "readmes.json"
    readmes_file.write_text(json.dumps(readme_data, indent=2))

    # Save worst commit
    if worst_commit:
        worst_file = user_dir / "worst_commit.json"
        worst_file.write_text(json.dumps(worst_commit, indent=2))


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
        print(f"OK — {result['stars']}★  {result['commits_last_year']} commits  {result['emoji_score']} emoji  toxicity={result['toxicity']:.3f}")

    print(f"\nDone. {len(existing)} users saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

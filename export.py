#!/usr/bin/env python3
"""
export.py — Merge precomputed.json + judge results → frontend/public/data.json

Computes derived fields (sus_score_percentile, badges, roles) and produces
the final JSON array the React frontend expects.

Usage:
    python export.py
"""

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PRECOMPUTED_FILE = Path("precomputed.json")
JUDGE_RESULTS_FILE = Path("judge_results.json")
JUDGE_STATE_FILE = Path("judge_state.json")
USERNAMES_FILE = Path("usernames.txt")
RAW_DATA_DIR = Path("raw_data")
OUTPUT_FILE = Path("frontend/public/data.json")

# ---------------------------------------------------------------------------
# Grade ordering (numeric value for ranking)
# ---------------------------------------------------------------------------
GRADE_ORDER = {
    "A+": 13, "A": 12, "A-": 11,
    "B+": 10, "B": 9,  "B-": 8,
    "C+": 7,  "C": 6,  "C-": 5,
    "D+": 4,  "D": 3,  "D-": 2,
    "F+": 1,  "F": 0,  "F-": -1,
}

# Reverse: numeric value → grade letter
NUM_TO_GRADE = {v: k for k, v in GRADE_ORDER.items()}

# Standard bell curve: cumulative percentile thresholds (from best to worst).
# Each tuple is (cumulative_percentile_cutoff, grade).
# A student at percentile p (0 = worst, 100 = best) gets the first grade
# whose cutoff is >= p.
CURVE_THRESHOLDS = [
    (3,  "F"),
    (8,  "D-"),
    (15, "D"),
    (23, "D+"),
    (35, "C-"),
    (50, "C"),
    (65, "C+"),
    (77, "B-"),
    (88, "B"),
    (95, "B+"),
    (99, "A-"),
    (100, "A"),
]


def curve_grades(judge_results: dict) -> dict:
    """Apply a standard bell curve to CodeRabbit grades.

    Preserves the relative ranking from CodeRabbit but redistributes
    grades along a normal distribution so the median is ~C/C+.
    Users with 'Pending' grades are left unchanged.
    """
    # Collect graded users with their numeric score
    graded = []
    for username, result in judge_results.items():
        raw_grade = result.get("quality_grade", "Pending")
        numeric = GRADE_ORDER.get(raw_grade)
        if numeric is not None:
            graded.append((username, numeric))

    if not graded:
        return judge_results

    # Sort by original grade ascending (worst first)
    graded.sort(key=lambda x: x[1])

    n = len(graded)
    curved = dict(judge_results)  # shallow copy

    for rank, (username, _orig_numeric) in enumerate(graded):
        # Percentile: 0 = worst, 100 = best
        percentile = (rank / max(n - 1, 1)) * 100

        # Find the curved grade for this percentile
        new_grade = "A+"
        for cutoff, grade in CURVE_THRESHOLDS:
            if percentile <= cutoff:
                new_grade = grade
                break

        curved[username] = dict(curved[username])
        curved[username]["quality_grade"] = new_grade

    return curved


# ---------------------------------------------------------------------------
# Role parsing from usernames.txt
# ---------------------------------------------------------------------------
def parse_roles() -> dict[str, str]:
    """Parse role prefixes from usernames.txt.

    Supported formats:
        judge:username   → role = "judge"
        org:username     → role = "organizer"
        username         → role = "participant"
    """
    roles: dict[str, str] = {}
    if not USERNAMES_FILE.exists():
        return roles

    for line in USERNAMES_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("judge:"):
            username = line.split(":", 1)[1].strip()
            roles[username.lower()] = "judge"
        elif line.startswith("org:"):
            username = line.split(":", 1)[1].strip()
            roles[username.lower()] = "organizer"
        else:
            roles.setdefault(line.lower(), "participant")

    return roles


# ---------------------------------------------------------------------------
# Sus score: emoji density → percentile
# ---------------------------------------------------------------------------
def compute_sus_percentiles(users: dict) -> dict[str, int]:
    """Rank users by emoji_score and assign 0-100 percentile."""
    scores = []
    for username, data in users.items():
        scores.append((username, data.get("emoji_score", 0)))

    # Sort by emoji score ascending
    scores.sort(key=lambda x: x[1])

    n = len(scores)
    percentiles = {}
    for rank, (username, _score) in enumerate(scores):
        # Percentile: what fraction of users have a lower score
        percentiles[username] = int((rank / max(n - 1, 1)) * 100)

    return percentiles


# ---------------------------------------------------------------------------
# README-derived badges
# ---------------------------------------------------------------------------
BADGE_IMG_RE = re.compile(r"!\[.*?\]\(")


def compute_badges(username: str, top_repo_name: str | None) -> list[str]:
    """Compute heuristic badges from README content."""
    badges = []
    readme_file = RAW_DATA_DIR / username / "readmes.json"

    if not readme_file.exists():
        badges.append("Empty README Enthusiast")
        return badges

    try:
        readmes: dict[str, str] = json.loads(readme_file.read_text())
    except (json.JSONDecodeError, OSError):
        badges.append("Empty README Enthusiast")
        return badges

    # Focus on the top repo's README
    top_readme = readmes.get(top_repo_name, "") if top_repo_name else ""

    # If no README for top repo, check if any README exists at all
    if not top_readme and not readmes:
        badges.append("Empty README Enthusiast")
        return badges

    # Use top repo README, or longest available README as fallback
    readme = top_readme or max(readmes.values(), key=len, default="")

    # Empty README Enthusiast: < 50 chars
    if len(readme) < 50:
        badges.append("Empty README Enthusiast")

    # Novel Writer: > 5,000 chars
    if len(readme) > 5000:
        badges.append("Novel Writer")

    # Badges Hoarder: 5+ badge images
    badge_count = len(BADGE_IMG_RE.findall(readme))
    if badge_count >= 5:
        badges.append("Badges Hoarder")

    # No Tests, No Problem: README never mentions "test" or "ci"
    readme_lower = readme.lower()
    if "test" not in readme_lower and "ci" not in readme_lower:
        badges.append("No Tests, No Problem")

    return badges


# ---------------------------------------------------------------------------
# Verdict cleanup
# ---------------------------------------------------------------------------
HTML_TAG_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def clean_verdict(verdict: str) -> str:
    """Strip HTML comments and rate-limit noise from CodeRabbit verdicts."""
    if not verdict:
        return "Pending review..."
    # Rate-limited responses contain HTML comments + "Rate Limit Exceeded"
    if "Rate Limit Exceeded" in verdict:
        return "CodeRabbit was rate-limited. Awaiting judgment..."
    # Strip any HTML comments
    cleaned = HTML_TAG_RE.sub("", verdict).strip()
    return cleaned or "Pending review..."


# ---------------------------------------------------------------------------
# Load judge results (from judge_results.json or judge_state.json)
# ---------------------------------------------------------------------------
def load_judge_results() -> dict[str, dict]:
    """Load CodeRabbit judge results. Tries judge_results.json first,
    then falls back to extracting from judge_state.json."""
    if JUDGE_RESULTS_FILE.exists():
        return json.loads(JUDGE_RESULTS_FILE.read_text())

    # Fallback: extract from judge_state.json
    if JUDGE_STATE_FILE.exists():
        state = json.loads(JUDGE_STATE_FILE.read_text())
        results = {}
        for username, user_state in state.items():
            if "result" in user_state:
                results[username] = user_state["result"]
        if results:
            print(f"  (Loaded {len(results)} results from judge_state.json fallback)")
            return results

    return {}


# ---------------------------------------------------------------------------
# Main export
# ---------------------------------------------------------------------------
def main() -> None:
    if not PRECOMPUTED_FILE.exists():
        print(f"ERROR: {PRECOMPUTED_FILE} not found. Run precompute.py first.")
        return

    precomputed: dict = json.loads(PRECOMPUTED_FILE.read_text())
    judge_results_raw = load_judge_results()
    judge_results = curve_grades(judge_results_raw)
    roles = parse_roles()
    sus_percentiles = compute_sus_percentiles(precomputed)

    graded_count = sum(
        1 for r in judge_results_raw.values()
        if GRADE_ORDER.get(r.get("quality_grade", "Pending")) is not None
    )
    print(f"Precomputed: {len(precomputed)} users")
    print(f"Judge results: {graded_count} graded (bell curve applied)")
    print(f"Roles parsed: {sum(1 for v in roles.values() if v != 'participant')} non-participant")

    output = []
    for username, data in precomputed.items():
        top_repos = data.get("top_repos", [])
        top_repo_name = top_repos[0] if top_repos else None

        # Judge results (with fallbacks)
        jr = judge_results.get(username, {})

        # Badges from README heuristics
        badges = compute_badges(username, top_repo_name)

        entry = {
            "username": username,
            "name": data.get("name") or username,
            "bio": data.get("bio") or "",
            "role": roles.get(username.lower(), "participant"),
            "avatar_url": f"https://github.com/{username}.png",
            "stars": data.get("stars", 0),
            "commits_last_year": data.get("commits_last_year", 0),
            "followers": data.get("followers", 0),
            "top_repo": {
                "name": top_repo_name or "unknown",
                "stars": data.get("stars", 0),  # total stars (best approximation)
                "language": None,
                "description": None,
            } if top_repo_name else None,
            "quality_grade": jr.get("quality_grade", "Pending"),
            "verdict": clean_verdict(jr.get("verdict", "")),
            "coderabbit_badge": jr.get("coderabbit_badge") if jr.get("quality_grade", "Pending") != "Pending" else None,
            "sus_score_percentile": sus_percentiles.get(username, 0),
            "worst_commit_msg": data.get("worst_commit_msg", ""),
            "worst_commit_toxicity": data.get("worst_commit_toxicity", 0.0),
            "badges": badges,
            "emoji_score": data.get("emoji_score", 0),
        }

        output.append(entry)

    # Write output
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(output, indent=2))

    graded = sum(1 for e in output if e["quality_grade"] not in ("Pending", "Error"))
    print(f"\nExported {len(output)} users to {OUTPUT_FILE}")
    print(f"  Graded: {graded}  |  Pending: {len(output) - graded}")
    print(f"  Badges assigned: {sum(len(e['badges']) for e in output)}")


if __name__ == "__main__":
    main()

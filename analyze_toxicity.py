#!/usr/bin/env python3
"""
Quick toxicity analyzer for a single user.
Usage: python analyze_toxicity.py USERNAME
"""

import json
import sys
from pathlib import Path
from detoxify import Detoxify

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_toxicity.py USERNAME")
        print("Example: python analyze_toxicity.py 256thfission")
        sys.exit(1)

    username = sys.argv[1]
    commits_file = Path(f"raw_data/{username}/commits.json")

    if not commits_file.exists():
        print(f"❌ No data found for {username}")
        print(f"   Expected file: {commits_file}")
        sys.exit(1)

    # Load commits
    with open(commits_file) as f:
        commits = json.load(f)

    if not commits:
        print(f"❌ No commits found for {username}")
        sys.exit(1)

    # Analyze toxicity
    model = Detoxify('original')
    results = model.predict(commits)

    # Calculate stats
    toxicity_scores = results['toxicity']
    avg_toxicity = float(toxicity_scores.mean())
    max_toxicity = float(toxicity_scores.max())
    max_idx = toxicity_scores.argmax()
    worst_commit = commits[max_idx]

    # Find worst on each axis
    worst_by_axis = {}
    for axis in ['toxicity', 'severe_toxicity', 'obscene', 'threat', 'insult', 'identity_attack']:
        scores = results[axis]
        idx = scores.argmax()
        worst_by_axis[axis] = (float(scores[idx]), commits[idx])

    # Print results
    print(f"\n{'='*80}")
    print(f"TOXICITY ANALYSIS: {username}")
    print(f"{'='*80}\n")

    print(f"📊 SUMMARY")
    print(f"   Total commits: {len(commits)}")
    print(f"   Average toxicity: {avg_toxicity:.3f}")
    print(f"   Worst commit: {max_toxicity:.3f}\n")

    # Find the absolute worst on any axis
    worst_overall = None
    worst_overall_score = 0
    worst_overall_axis = None

    for axis, (score, commit) in worst_by_axis.items():
        if score > worst_overall_score:
            worst_overall_score = score
            worst_overall = commit
            worst_overall_axis = axis

    print(f"⚠️  WORST COMMIT")
    print(f"   Axis: {worst_overall_axis}")
    print(f"   Score: {worst_overall_score:.3f}")
    print(f"   Message: \"{worst_overall[:100]}{'...' if len(worst_overall) > 100 else ''}\"")

    print(f"\n{'='*80}\n")

if __name__ == "__main__":
    main()

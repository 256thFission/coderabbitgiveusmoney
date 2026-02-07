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

    # Calculate stats (handle both numpy arrays and lists)
    toxicity_scores = results['toxicity']
    if hasattr(toxicity_scores, 'mean'):
        # numpy array
        avg_toxicity = float(toxicity_scores.mean())
        max_toxicity = float(toxicity_scores.max())
        max_idx = int(toxicity_scores.argmax())
    else:
        # list
        import statistics
        avg_toxicity = float(statistics.mean(toxicity_scores))
        max_toxicity = float(max(toxicity_scores))
        max_idx = toxicity_scores.index(max_toxicity)

    # Find worst on each axis
    worst_by_axis = {}
    for axis in ['toxicity', 'severe_toxicity', 'obscene', 'threat', 'insult', 'identity_attack']:
        scores = results[axis]
        if hasattr(scores, 'argmax'):
            # numpy array
            idx = int(scores.argmax())
        else:
            # list
            idx = scores.index(max(scores))
        worst_by_axis[axis] = (float(scores[idx]), commits[idx])

    # Find the absolute worst on any axis
    worst_overall = None
    worst_overall_score = 0
    worst_overall_axis = None
    worst_overall_idx = None

    for axis, (score, commit) in worst_by_axis.items():
        if score > worst_overall_score:
            worst_overall_score = score
            worst_overall = commit
            worst_overall_axis = axis
            # Find index of this commit in the list
            for i, c in enumerate(commits):
                if c == commit:
                    worst_overall_idx = i
                    break

    # Print results
    print(f"\n{'='*80}")
    print(f"TOXICITY ANALYSIS: {username}")
    print(f"{'='*80}\n")

    print(f"📊 SUMMARY")
    print(f"   Total commits: {len(commits)}")
    print(f"   Average toxicity: {avg_toxicity:.3f}")
    print(f"   Worst commit overall: {max_toxicity:.3f}\n")

    print(f"⚠️  WORST COMMIT (Highest on any axis)")
    print(f"   Axis: {worst_overall_axis}")
    print(f"   Score: {worst_overall_score:.3f}")
    print(f"   Message: \"{worst_overall[:100]}{'...' if len(worst_overall) > 100 else ''}\"")

    if worst_overall_idx is not None:
        print(f"\n📋 ALL TOXICITY SCORES FOR WORST COMMIT:")
        for axis in ['toxicity', 'severe_toxicity', 'obscene', 'threat', 'insult', 'identity_attack']:
            score_val = results[axis][worst_overall_idx]
            score = float(score_val) if not isinstance(score_val, float) else score_val
            print(f"   {axis:20s}: {score:.3f}")

    print(f"\n{'='*80}\n")

    # Save worst commit data to file
    all_scores_dict = {}
    if worst_overall_idx is not None:
        for axis in ['toxicity', 'severe_toxicity', 'obscene', 'threat', 'insult', 'identity_attack']:
            score_val = results[axis][worst_overall_idx]
            all_scores_dict[axis] = float(score_val) if not isinstance(score_val, float) else score_val

    worst_commit_data = {
        "message": worst_overall,
        "toxicity_axis": worst_overall_axis,
        "toxicity_score": worst_overall_score,
        "all_scores": all_scores_dict
    }

    worst_file = Path(f"raw_data/{username}/worst_commit.json")
    worst_file.write_text(json.dumps(worst_commit_data, indent=2))
    print(f"✅ Worst commit analysis saved to {worst_file}\n")

if __name__ == "__main__":
    main()

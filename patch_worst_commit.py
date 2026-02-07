#!/usr/bin/env python3
"""
Patch precomputed.json with worst_commit_toxicity and worst_commit_msg
using already-saved raw_data/<user>/commits.json.
No GitHub API calls needed.
"""

import json
from pathlib import Path

OUTPUT_FILE = Path("precomputed.json")
RAW_DATA_DIR = Path("raw_data")


def main():
    if not OUTPUT_FILE.exists():
        print("No precomputed.json found.")
        return

    data = json.loads(OUTPUT_FILE.read_text())
    print(f"Loaded {len(data)} users from {OUTPUT_FILE}")

    # Lazy-load model only if needed
    model = None

    patched = 0
    for username, info in data.items():
        # Skip if already has worst commit data
        if info.get("worst_commit_msg"):
            print(f"  {username}: already has worst_commit_msg, skipping")
            patched += 1
            continue

        # Load cached commits
        commits_file = RAW_DATA_DIR / username.lower() / "commits.json"
        if not commits_file.exists():
            # Try exact case
            commits_file = RAW_DATA_DIR / username / "commits.json"
        if not commits_file.exists():
            print(f"  {username}: no cached commits found, setting defaults")
            info["worst_commit_toxicity"] = 0.0
            info["worst_commit_msg"] = ""
            continue

        texts = json.loads(commits_file.read_text())
        if not texts:
            print(f"  {username}: empty commits, setting defaults")
            info["worst_commit_toxicity"] = 0.0
            info["worst_commit_msg"] = ""
            continue

        # Load model on first use
        if model is None:
            import torch
            from detoxify import Detoxify
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = Detoxify("original", device=device)
            print(f"Toxicity model loaded on {device}")
            _torch = torch
        else:
            import torch as _torch

        # Batch predict
        axes = ["toxicity", "severe_toxicity", "obscene", "threat", "insult", "identity_attack"]
        all_scores = {k: [] for k in axes}
        batch_size = 32
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            with _torch.no_grad():
                results = model.predict(batch)
            for k in axes:
                all_scores[k].extend(results[k])

        if _torch.cuda.is_available():
            _torch.cuda.empty_cache()

        # Find worst commit (highest score on any axis)
        worst_idx = None
        worst_score = 0.0
        for idx in range(len(texts)):
            for axis in axes:
                score = float(all_scores[axis][idx])
                if score > worst_score:
                    worst_score = score
                    worst_idx = idx

        if worst_idx is not None:
            info["worst_commit_toxicity"] = worst_score
            info["worst_commit_msg"] = texts[worst_idx]
            # Also save worst_commit.json
            worst_data = {
                "message": texts[worst_idx],
                "toxicity_score": worst_score,
                "all_scores": {axis: float(all_scores[axis][worst_idx]) for axis in axes},
            }
            worst_file = (RAW_DATA_DIR / username / "worst_commit.json")
            if worst_file.parent.exists():
                worst_file.write_text(json.dumps(worst_data, indent=2))
        else:
            info["worst_commit_toxicity"] = 0.0
            info["worst_commit_msg"] = ""

        patched += 1
        print(f"  {username}: worst={worst_score:.3f} \"{(texts[worst_idx] if worst_idx is not None else '')[:60]}\"")

    OUTPUT_FILE.write_text(json.dumps(data, indent=2))
    print(f"\nDone. Patched {patched}/{len(data)} users in {OUTPUT_FILE}")


if __name__ == "__main__":
    main()

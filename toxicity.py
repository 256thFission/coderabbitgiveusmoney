#!/usr/bin/env python3
"""
Toxicity detection module using the Detoxify library.
"""

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Toxicity detection
# ---------------------------------------------------------------------------
_detoxify_model = None


def get_toxicity_model():
    """Lazy-load the Detoxify model to avoid startup overhead."""
    global _detoxify_model
    if _detoxify_model is None:
        from detoxify import Detoxify

        _detoxify_model = Detoxify("original")
    return _detoxify_model


def analyze_toxicity(texts: list[str]) -> dict:
    """
    Analyze toxicity in a list of texts (commit messages).
    Returns dict with averaged toxicity scores.
    Returns all zeros if input is empty or model fails.
    """
    if not texts:
        return {
            "toxicity": 0.0,
            "severe_toxicity": 0.0,
            "obscene": 0.0,
            "threat": 0.0,
            "insult": 0.0,
            "identity_attack": 0.0,
        }

    try:
        model = get_toxicity_model()
        results = model.predict(texts)

        # Average scores across all texts
        return {
            key: float(results[key].mean())
            for key in [
                "toxicity",
                "severe_toxicity",
                "obscene",
                "threat",
                "insult",
                "identity_attack",
            ]
        }
    except Exception as e:
        print(f"    Toxicity analysis failed: {e}")
        return {
            "toxicity": 0.0,
            "severe_toxicity": 0.0,
            "obscene": 0.0,
            "threat": 0.0,
            "insult": 0.0,
            "identity_attack": 0.0,
        }


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


def save_worst_commit(username: str, worst_commit: dict) -> None:
    """
    Save the worst commit analysis to user's raw data directory.

    Args:
        username: GitHub username
        worst_commit: Dict from find_worst_commit()
    """
    if worst_commit is None:
        return

    user_dir = Path("raw_data") / username
    user_dir.mkdir(parents=True, exist_ok=True)

    worst_file = user_dir / "worst_commit.json"
    worst_file.write_text(json.dumps(worst_commit, indent=2))

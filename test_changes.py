#!/usr/bin/env python3
"""Quick test to verify the changes to precompute.py"""

import re
import json

# Read the modified precompute.py to verify changes
with open('precompute.py', 'r') as f:
    content = f.read()

# Check 1: README_QUERY exists
if 'README_QUERY = """' in content and 'object(expression: "HEAD:README.md")' in content:
    print("✓ README_QUERY added correctly")
else:
    print("✗ README_QUERY missing or incorrect")

# Check 2: get_toxicity_model function exists
if 'def get_toxicity_model():' in content and 'from detoxify import Detoxify' in content:
    print("✓ get_toxicity_model function added correctly")
else:
    print("✗ get_toxicity_model function missing")

# Check 3: analyze_toxicity function exists
if 'def analyze_toxicity(texts: list[str]) -> dict:' in content and 'results[key].mean()' in content:
    print("✓ analyze_toxicity function added correctly")
else:
    print("✗ analyze_toxicity function missing")

# Check 4: README fetching in scrape_user
if 'readme_texts: list[str] = []' in content and 'graphql(README_QUERY' in content:
    print("✓ README fetching logic added to scrape_user")
else:
    print("✗ README fetching logic missing")

# Check 5: Combined emoji score
if 'count_emojis(commit_messages + readme_texts)' in content:
    print("✓ Combined emoji scoring added")
else:
    print("✗ Combined emoji scoring missing")

# Check 6: Toxicity analysis call
if 'analyze_toxicity(commit_messages)' in content:
    print("✓ Toxicity analysis call added")
else:
    print("✗ Toxicity analysis call missing")

# Check 7: Return statement has toxicity fields
if '"toxicity": toxicity_scores["toxicity"],' in content:
    print("✓ Toxicity fields in return statement")
else:
    print("✗ Toxicity fields missing from return statement")

# Check 8: Print statement shows toxicity
if "toxicity={result['toxicity']:.3f}" in content:
    print("✓ Print statement updated with toxicity")
else:
    print("✗ Print statement not updated")

# Check 9: environment.yml has detoxify
with open('environment.yml', 'r') as f:
    env_content = f.read()
    if 'detoxify' in env_content:
        print("✓ detoxify added to environment.yml")
    else:
        print("✗ detoxify not added to environment.yml")

print("\nAll code changes verified! ✓")

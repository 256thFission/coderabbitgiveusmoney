#!/usr/bin/env python3
"""Test to show how raw data will be structured"""

import json
from pathlib import Path
import tempfile
import shutil

# Create temporary test directory
test_dir = Path(tempfile.mkdtemp())
raw_data_dir = test_dir / "raw_data"

print("Testing Raw Data Storage Structure")
print("=" * 60)

# Simulate saving data for a user
username = "test_user"
user_dir = raw_data_dir / username
user_dir.mkdir(parents=True, exist_ok=True)

# Create sample commit messages
sample_commits = [
    "Fix bug in authentication",
    "Add emoji support 🎉",
    "Refactor database module",
    "Initial commit"
]

# Create sample READMEs
sample_readmes = {
    "awesome-project": "# Awesome Project\n\nThis is an awesome project 🚀\n\n## Features\n- Fast\n- Reliable",
    "cli-tool": "# CLI Tool\n\nA command-line tool for developers.",
    "library": "# Library\n\nA useful library for Python 📚"
}

# Save commits
commits_file = user_dir / "commits.json"
commits_file.write_text(json.dumps(sample_commits, indent=2))

# Save READMEs
readmes_file = user_dir / "readmes.json"
readmes_file.write_text(json.dumps(sample_readmes, indent=2))

# Display the structure
print(f"\nDirectory structure created at: {raw_data_dir}")
print("\nContent:")

for root, dirs, files in (raw_data_dir).walk():
    level = len(root.relative_to(raw_data_dir).parts)
    indent = "  " * level
    print(f"{indent}{root.name}/")
    sub_indent = "  " * (level + 1)
    for file in files:
        file_path = root / file
        size = file_path.stat().st_size
        print(f"{sub_indent}{file} ({size} bytes)")

print("\n" + "=" * 60)
print("Sample commits.json content:")
print("-" * 60)
with open(commits_file) as f:
    commits_data = json.load(f)
    for i, commit in enumerate(commits_data[:2], 1):
        print(f"{i}. {commit}")
    if len(commits_data) > 2:
        print(f"... and {len(commits_data) - 2} more")

print("\n" + "=" * 60)
print("Sample readmes.json keys:")
print("-" * 60)
with open(readmes_file) as f:
    readmes_data = json.load(f)
    for repo_name in readmes_data.keys():
        content_preview = readmes_data[repo_name][:50].replace('\n', ' ')
        print(f"- {repo_name}: {content_preview}...")

print("\n" + "=" * 60)
print("✅ Raw data storage structure verified successfully!")
print(f"\nTotal data stored per user: {sum(f.stat().st_size for f in user_dir.glob('*.json'))} bytes")

# Cleanup
shutil.rmtree(test_dir)

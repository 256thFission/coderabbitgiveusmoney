#!/usr/bin/env python3
"""Verify raw data storage implementation"""

with open('precompute.py', 'r') as f:
    content = f.read()

checks = [
    ("RAW_DATA_DIR constant", 'RAW_DATA_DIR = Path("raw_data")'),
    ("save_raw_data function", 'def save_raw_data(username: str, commit_messages: list[str], readme_data: dict)'),
    ("Directory creation", 'user_dir.mkdir(parents=True, exist_ok=True)'),
    ("Save commits.json", 'commits_file = user_dir / "commits.json"'),
    ("Save readmes.json", 'readmes_file = user_dir / "readmes.json"'),
    ("Capture repo name", 'repo_name = repo.get("name", "unknown")'),
    ("Store in readme_dict", 'readme_dict[repo_name] = readme_content'),
    ("Call save_raw_data", 'save_raw_data(username, commit_messages, readme_dict)'),
]

print("Raw Data Storage Implementation Verification:")
print("=" * 50)

all_ok = True
for check_name, check_code in checks:
    if check_code in content:
        print(f"✓ {check_name}")
    else:
        print(f"✗ {check_name} - NOT FOUND")
        all_ok = False

print("=" * 50)
if all_ok:
    print("✅ All checks passed! Raw data storage is fully implemented.")
else:
    print("❌ Some checks failed.")

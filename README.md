# Git Gud Bud

A "Wall of Shame" (or employment opportunity) that scrapes GitHub profiles, analyzes them, and uses CodeRabbit to generate brutal AI code reviews to create a leaderboard of hackers.

Built by Phillip, Zackery, and Hummam.

## Process

Given a list of GitHub usernames, the pipeline:

1. **Scrapes** profile data, commit history, and READMEs via the GitHub GraphQL API.
2. **Scores toxicity** of commit messages locally using Detoxify, surfacing each user's worst commit.
3. **Computes a "sus score"** from emoji density across commits and READMEs (percentile-ranked).
4. **Assigns heuristic badges** from README analysis (e.g. "Empty README Enthusiast", "No Tests, No Problem").
5. **Judges code quality with CodeRabbit** -- forks each user's top repo, opens a full-codebase PR, and prompts CodeRabbit (as Linus Torvalds) to grade it, roast it, and assign a badge.
6. **Exports** everything to a static JSON file consumed by a React frontend.

## How We Used CodeRabbit

CodeRabbit is the core of the judging pipeline (`judge.py`). For each target user's most-starred repository, the pipeline:

1. Forks the repo into our account.
2. Creates a branch pointing at the repo's oldest commit, then opens a PR from `main` into that branch. This forces GitHub to diff the entire codebase as new additions.
3. Comments `@coderabbitai review` to trigger a full review, then posts a structured judging prompt asking CodeRabbit to act as Linus Torvalds and return a JSON block containing a letter grade (F- to A+), a one-liner roast referencing real code, and a humorous badge.
4. Polls PR comments until CodeRabbit responds, then parses the grade/verdict/badge from the reply.
5. Calls the CodeRabbit Custom Reports API (`/api/v1/report.generate`) to produce an aggregate report across all reviewed repos.

Grades are bell-curved in `export.py` so the distribution follows a normal curve regardless of CodeRabbit's raw grading tendencies.

The entire pipeline is resumable -- each phase (fork, PR, comment, poll, report) saves state to `judge_state.json` and skips already-completed work on re-run.

## Stack

| Layer | Tool |
|---|---|
| Scraper | Python 3.12, GitHub GraphQL API, multi-token rotation |
| Toxicity | Detoxify (local, offline) |
| AI Judge | CodeRabbit GitHub App + Custom Reports API |
| Frontend | React 19, Vite, DoodleCSS |
| Data | Precomputed JSON (no live backend) |



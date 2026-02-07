# The Wall of Shame — Hackathon Plan (Merged & Final)

High-speed spec for an 8-hour hackathon. Pipeline: **precompute → analyze → judge → display**.
50 "High Value Targets" (HVTs), one repo each, maximum depth.

---

## 1. The Stack

| Layer | Tool | Notes |
|---|---|---|
| **Scraper** | Python 3.12, `requests` | Already built (`precompute.py`). Two-tier: surface then deep. |
| **Toxicity** | `detoxify` (local) | Runs offline over commit messages. No API cost. |
| **AI Judge** | [CodeRabbit Custom Reports API](https://docs.coderabbit.ai/guides/custom-reports) | Linus Torvalds persona. One call per HVT repo. |
| **Data Store** | `scraped_data.db` (SQLite) | Single source of truth. Export to `frontend/public/data.json` for the UI. |
| **Frontend** | React + Vite + [DoodleCSS](https://chr15m.github.io/DoodleCSS/) | Static site. No live backend. "Scrappy-chic" aesthetic. |

---

## 2. Phase 0: Precompute & Deep Scraping (Pre-Hackathon)

**Goal:** Identify 50 HVTs from a larger pool, then deep-scrape their #1 repo.

### 2.1 Two-Tier Scraper (`precompute.py` — already exists)

**Tier 1 (Surface — already implemented):**
1. Read `usernames.txt` (judges, organizers, top participants).
2. Fetch per user: top 10 repos by stars, total stars, follower count, commits last year, bio.
3. Output: `precomputed.json` (resumable, deduped).

**Tier 2 (Deep — needs to be added):**
1. Rank all scraped users by `stars × commits_last_year`.
2. Take the **Top 50** as HVTs.
3. For each HVT's #1 repo (most-starred), fetch:
   - `README.md` contents (via REST API: `GET /repos/{owner}/{repo}/readme`).
   - Last **100 commit messages** on the default branch (paginated GraphQL).
4. Save everything into `scraped_data.db` (SQLite).

### 2.2 Auth & Rate Limiting (already implemented)

Three-token rotation in `.env`. 15,000 req/hr effective. Round-robin with cooldown tracking.
50 users × ~4 queries each = ~200 queries. Finishes in under a minute.

### 2.3 `usernames.txt` Format

```
# Judges (tag: judge)
judge:username1
judge:username2

# Organizers (tag: organizer)
org:username3

# Participants (no tag needed)
username4
username5
```

Parse the prefix to tag roles in the DB. Simple `split(":")` logic.

---

## 3. Phase 1: Toxicity & Sus Analysis (Hours 0–1)

Runs locally, no API calls. Fast even on a laptop.

### 3.1 Detoxify — "Heinous Commit Search"

For each HVT's 100 commit messages:
1. Run `detoxify.Detoxify('original').predict(message)` on each.
2. Record the single message with the highest `toxicity` score → "Worst Commit Msg".
3. Store `worst_commit_msg`, `worst_commit_toxicity` in DB.

### 3.2 Sus Score (Emoji Density Percentile)

Already partially implemented (emoji regex + shortcode counting):
1. Count total emojis across the 100 commit messages.
2. Calculate `emoji_density = emoji_count / total_characters` (guard div-by-zero).
3. Rank all 50 HVTs by density → assign **percentile 0–100**.
4. Store `sus_score_percentile` in DB.

### 3.3 README-Derived Badges

Quick heuristic checks on the README (no AI needed):
- **"Empty README Enthusiast"** — README < 50 chars or missing.
- **"Novel Writer"** — README > 5,000 chars.
- **"Badges Hoarder"** — README contains 5+ `![badge]` image links.
- **"No Tests, No Problem"** — README never mentions "test" or "ci".

Store as a JSON array of badge strings per user.

---

## 4. Phase 2: The CodeRabbit Judge (Hours 1–3)

### 4.1 Custom Report Trigger

For each HVT's top repo, call the CodeRabbit Custom Reports API with:

> **Instructions:** "Act as Linus Torvalds. Analyze the README and architecture of this repo.
> 1. Provide a 'Code Quality Grade' from F- to A+.
> 2. Write a savage, technical one-liner roast (the 'Verdict').
> 3. Identify one 'Badge' they deserve (e.g., Over-engineered, Bloated, Documentation Hater).
> 4. Strictly no emojis."

### 4.2 Response Parsing & Cache

Save the raw CodeRabbit JSON to SQLite immediately. Parse out:
- `quality_grade` (string: "F-" to "A+")
- `verdict` (string: the one-liner roast)
- `coderabbit_badge` (string: the AI-assigned badge)

If CodeRabbit is slow or flaky, the rest of the pipeline still works — the UI just shows "Pending review…" for ungraded users.

---

## 5. Phase 3: The UI (Hours 3–6)

### 5.1 Setup

```bash
npm create vite@latest frontend -- --template react
# Add DoodleCSS via CDN in index.html
```

### 5.2 The "Wall of Shame" Table (`Scoreboard.jsx`)

**Ranking formula:** `(stars × commits) / (sus_score_percentile + 1)`

| Column | Source |
|---|---|
| **Rank** | Computed from formula above |
| **Name** | Avatar + GitHub handle. "Judge" / "Organizer" tag if applicable. |
| **Quality Grade** | CodeRabbit letter grade (e.g., **D-**) |
| **Sus Score** | Percentile, shown as a hand-drawn progress bar |
| **Worst Commit** | The Detoxify-flagged message, truncated |

**Filters:** Tabs or buttons for All / Judges / Organizers / Participants.

### 5.3 The Details Modal (`RoastModal.jsx`)

Click a row → `doodle-border` modal:
- **The Verdict:** Full Linus one-liner from CodeRabbit.
- **Badges:** Visual stickers — both heuristic badges + CodeRabbit badge.
- **Top Repo Stats:** Star count, primary language, worst commit message in full.
- **Toxicity Meter:** Visual bar for the worst commit's toxicity score.

### 5.4 Featured Judges Section

**Yes** — pin judges/organizers at the top in a highlighted "Featured" row group.
People grading you see themselves first. High visibility = high impact.

---

## 6. Phase 4: Polish & Deploy (Hours 6–8)

1. **Export:** Python script runs `generate_data_json()` → writes `frontend/public/data.json`.
2. **Deploy:** `npm run build` → Netlify or Vercel. Static site, no backend needed.
3. **Vibes:**
   - "Re-Scrape" button → toast: "Wait your turn, peasant."
   - Doodle-style loading skeletons.
   - Dark/light toggle if time permits.

---

## Design Decisions (Hackathon Pragmatism)

| Question | Decision | Rationale |
|---|---|---|
| **50 vs. more targets?** | **50 is correct.** | Deep > wide. 100 commits × 50 people = rich data. More targets = shallower analysis. |
| **100 commits enough?** | **Yes.** | At 50 people, 100 commits is plenty for toxicity signal. Diminishing returns past that. |
| **Detoxify vs. API sentiment?** | **Detoxify (local).** | Zero latency, no API key, runs on CPU in seconds for 5,000 messages. |
| **SQLite vs. JSON?** | **SQLite for pipeline, JSON for UI.** | SQLite prevents data loss mid-pipeline. JSON is the static export the frontend reads. |
| **`gql` library?** | **Skip it.** | `requests` + raw GraphQL strings already works in `precompute.py`. No reason to add a dep. |
| **Featured Judges section?** | **Yes.** | Judges see themselves first → memorable → better score for us. |
| **Backend API?** | **No.** | Python overwrites `data.json`. React reads it with `fetch()`. Zero server infra. |

---

## The "Hack" List (Time Savers)

- **Precompute everything:** All GitHub scraping done before the hackathon. Zero API wait on day-of.
- **Three-token rotation:** 15k req/hr. Set it up once, forget it.
- **No backend API:** Python writes `data.json` → React reads it. Done.
- **Hardcode the threshold:** Top 50 by `stars × commits`. No UI knob needed.
- **Ignore error handling:** If a profile 404s, `continue`. If CodeRabbit times out, show "Pending".
- **Resumable everything:** Scraper skips already-scraped users. Judge skips already-judged repos.
- *dges are free:** README heuristics take 10 lines of Python and add huge visual value.*Ba

---

## File Structure (Target)

```
├── .env                    # GitHub tokens (gitignored)
├── .env.example
├── usernames.txt           # Input: one username per line, with optional role prefix
├── precompute.py           # Tier 1 + Tier 2 scraper (already exists, needs Tier 2)
├── analyze.py              # Detoxify toxicity + sus score + README badges
├── judge.py                # CodeRabbit API calls + response parsing
├── export.py               # SQLite → data.json for the frontend
├── scraped_data.db         # SQLite (gitignored)
├── environment.yml         # Conda deps
├── frontend/
│   ├── public/
│   │   └── data.json       # Generated by export.py
│   ├── src/
│   │   ├── App.jsx
│   │   ├── Scoreboard.jsx
│   │   ├── RoastModal.jsx
│   │   └── main.jsx
│   ├── index.html          # DoodleCSS CDN link here
│   ├── package.json
│   └── vite.config.js
└── plan.md                 # This file
```

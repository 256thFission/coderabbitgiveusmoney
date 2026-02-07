This is a high-speed technical specification designed for an 8-hour hackathon. The focus is on a "Linear" pipeline: precompute scrapes, filter, judge, and display.

Since you are on a clock, avoid complex auth or multi-tenant logic. Use a single flat file or a local SQLite database for speed.

---

## 1. The Stack

* **Backend/Scraper:** Python (fastest for data munging).
* **Orchestration:** Simple `main.py` script (No Celery/Redis, just loops).
* **Data Store:** `data.db` (SQLite) or `results.json`.
* **Frontend:** React + Vite + DoodleCSS (Static site fetching the JSON).
* **AI:** CodeRabbit API + OpenAI (for the Linus personality layer).

---

## 2. Phase 0: Precompute All Scraping (Before the Hackathon)

The scraping phase is the biggest rate-limit bottleneck. **Do it all ahead of time** so the hackathon hours are spent on the judge + UI.

### 2.1 The Master Username List

Build a single `usernames.txt` (or `usernames.json`) containing **every** username you want to scrape. This includes:

* **Judges** — all hackathon judges' GitHub usernames.
* **Organizers** — all organizer GitHub usernames.
* **Participants / Targets** — stargazers of popular repos, followers of famous devs, hackathon attendees, etc.

Curate this list manually or pull it programmatically (e.g., scrape the hackathon's attendee page, fetch stargazers of `facebook/react`, etc.). Deduplicate before running.

### 2.2 GitHub Auth — Three-Token Rotation

Unauthenticated GitHub API: 60 requests/hour. Authenticated: **5,000 requests/hour per token**. With three accounts rotating, you get an effective **15,000 requests/hour**.

**Setup:**

1. Create a `.env` file (gitignored) with three GitHub Personal Access Tokens:
   ```
   GITHUB_TOKENS=ghp_token1,ghp_token2,ghp_token3
   ```
2. In the scraper, load the tokens and rotate with a simple round-robin:
   ```python
   import os, itertools

   tokens = os.environ["GITHUB_TOKENS"].split(",")
   token_cycle = itertools.cycle(tokens)

   def get_next_headers():
       token = next(token_cycle)
       return {"Authorization": f"bearer {token}"}
   ```
3. On each API call, use `get_next_headers()`. This spreads load across three accounts evenly.
4. **Rate-limit awareness:** After each response, check `X-RateLimit-Remaining`. If a token is exhausted, skip it until `X-RateLimit-Reset`. A simple approach:
   ```python
   import time

   token_cooldowns = {}  # token -> reset_timestamp

   def get_next_headers():
       now = time.time()
       for _ in range(len(tokens)):
           token = next(token_cycle)
           if token_cooldowns.get(token, 0) <= now:
               return {"Authorization": f"bearer {token}"}
       # All tokens exhausted — sleep until the earliest reset
       earliest = min(token_cooldowns.values())
       time.sleep(max(0, earliest - now + 1))
       return get_next_headers()
   ```

### 2.3 The Precompute Script (`precompute.py`)

This script runs **before** the hackathon. It reads `usernames.txt`, scrapes all data via the GitHub GraphQL API, and dumps results to `precomputed.json` (or SQLite).

**Per-user data to fetch (single GraphQL query):**

* Top 10 repos by stars (name, stargazerCount, primaryLanguage, description).
* Total star count across all repos.
* Contribution count for the last year.
* Last 50 commit messages (for emoji scoring).
* Bio, company, location, followers count.

**Resumability:** The script should skip usernames that are already in the output file. This way if it crashes or you hit a long cooldown, you just re-run it and it picks up where it left off.

**Output format (`precomputed.json`):**
```json
{
  "torvalds": {
    "stars": 200000,
    "commits_last_year": 3200,
    "emoji_score": 0,
    "top_repos": ["linux"],
    "bio": "...",
    "scraped_at": "2026-02-07T..."
  }
}
```

### 2.4 Timing Estimate

* ~2 GraphQL queries per user (profile + commits).
* 15,000 req/hr with 3 tokens → ~7,500 users/hr.
* For a list of 1,000 usernames, this finishes in under 10 minutes.
* For 10,000 usernames, ~1.5 hours. Run it the night before.

---

## 3. Phase 1: The Judge (Hours 0-3)

With precomputed data already in hand, jump straight to judging on hackathon day.

### 3.1 Filtering

Load `precomputed.json`. Apply the threshold:
* `total_stars > 10` OR `commits_last_year > 500`.

This produces the "High Value Targets" list.

### 3.2 CodeRabbit Integration

Referencing the [Custom Reports Guide](https://docs.coderabbit.ai/guides/custom-reports):

1. **Trigger:** For each HVT, pass their top repo URL to the CodeRabbit Custom Reports API.
2. **The Prompt:** Use the `instructions` field to force the "Linus Torvalds" persona.
   * *Prompt:* "Analyze this code. Be incredibly cynical. Find one specific architectural flaw. End with a one-sentence insult starting with 'Even a sub-standard gopher...'. No emojis."

### 3.3 Storage Structure

Save the output immediately to your local DB so you don't re-run expensive API calls if the frontend crashes.

| username | stars | emoji_score | cr_summary | linus_insult | is_judge | is_organizer |
| --- | --- | --- | --- | --- | --- | --- |
| torvalds | 200k | 0 | Kernel god. | "This code is so bloated..." | false | false |
| judge1 | 5k | 3 | Clean arch. | "Your code offends me..." | true | false |

Tag judges and organizers so the UI can highlight or feature them separately.

---

## 4. Phase 2: The UI (Hours 3-6)

This needs to be "Scrappy-Chic."

### Vite + DoodleCSS Setup

1. `npm create vite@latest frontend --template react`
2. Add DoodleCSS via CDN in `index.html`.
3. **The Layout:**
   * **Header:** `<h1>` with a hand-drawn border.
   * **The Table:** Standard `<table>` tag. DoodleCSS styles it automatically.
   * **Ranking:** Sort by `stars * commits / (emoji_score + 1)`.
   * **Judge/Organizer Badges:** Visually tag judges and organizers with a badge or different row color.

### Component Plan

* `Scoreboard.jsx`: Maps through your `results.json`. Supports filtering by role (all / judges / organizers / participants).
* `RoastModal.jsx`: A simple conditional render that shows the CodeRabbit summary when a row is clicked.

---

## 5. Phase 3: Polish & Deployment (Hours 6-8)

* **Vibe Check:** Add a "Hand-drawn" toggle or a "Re-Scrape" button that just triggers a toast saying "Wait your turn, peasant."
* **Deployment:** Push the frontend to Vercel or Netlify. Host `results.json` as a static file in `/public` — no live backend needed.

---

## The "Hack" List (Time Savers)

* **Precompute everything:** All GitHub scraping is done before the hackathon. Zero API wait time on the day.
* **Three-token rotation:** 15k req/hr instead of 5k. Set it up once, forget about it.
* **Don't build a backend API:** Just have your Python script overwrite `frontend/public/data.json`. React fetches it with `useEffect`.
* **Hardcode the Threshold:** Don't make it adjustable. Pick a number and move on.
* **Ignore Error Handling:** If a GitHub profile 404s, just `continue` the loop.
* **Resumable scraper:** If it crashes, re-run and it skips already-scraped users.

#!/usr/bin/env python3
"""
FastAPI service for GitHub scraper with optional toxicity analysis.
Run with: uvicorn api:app --reload --port 8000
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

from scraper import scrape_user
from toxicity import analyze_toxicity

# Load environment
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="GitRanker API",
    description="Scrape GitHub user data and analyze toxicity",
    version="1.0.0"
)

# Database file
DB_FILE = Path("scrape_results.json")


# ============================================================================
# Pydantic Models
# ============================================================================

class ScrapeRequest(BaseModel):
    username: str
    analyze_toxicity: bool = False  # Run toxicity analysis after scraping


class ScrapeResponse(BaseModel):
    username: str
    status: str
    data: Optional[dict] = None
    error: Optional[str] = None
    toxicity: Optional[dict] = None


# ============================================================================
# Database helpers
# ============================================================================

def load_db() -> dict:
    """Load results database."""
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {}


def save_db(data: dict) -> None:
    """Save results database."""
    DB_FILE.write_text(json.dumps(data, indent=2))


def get_user_data(username: str) -> Optional[dict]:
    """Get cached user data from database."""
    db = load_db()
    return db.get(username.lower())


def save_user_data(username: str, data: dict) -> None:
    """Save user data to database."""
    db = load_db()
    db[username.lower()] = data
    save_db(db)


# ============================================================================
# Toxicity analysis (background task)
# ============================================================================

def analyze_user_toxicity(username: str) -> dict:
    """Analyze toxicity for a user (background task)."""
    try:
        commits_file = Path(f"raw_data/{username}/commits.json")
        if not commits_file.exists():
            return {"error": "No commits found"}

        with open(commits_file) as f:
            commits = json.load(f)

        if not commits:
            return {"error": "No commits to analyze"}

        # Analyze
        toxicity_scores = analyze_toxicity(commits)

        # Update database
        db = load_db()
        if username.lower() in db:
            db[username.lower()]["toxicity"] = toxicity_scores
            save_db(db)

        return toxicity_scores
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Health check."""
    return {
        "status": "ok",
        "service": "GitRanker API",
        "endpoints": {
            "POST /scrape": "Scrape a GitHub user",
            "GET /user/{username}": "Get cached user data",
            "GET /stats": "Get scraping statistics"
        }
    }


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_user(request: ScrapeRequest, background_tasks: BackgroundTasks):
    """
    Scrape a GitHub user and optionally analyze toxicity.

    - **username**: GitHub username to scrape
    - **analyze_toxicity**: If true, run toxicity analysis after scraping (async)
    """
    username = request.username.strip()

    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")

    try:
        # Scrape user
        print(f"Scraping {username}...")
        result = scrape_user(username)

        if result is None:
            return ScrapeResponse(
                username=username,
                status="error",
                error="User not found"
            )

        # Save to database
        save_user_data(username, result)

        response = ScrapeResponse(
            username=username,
            status="success",
            data=result
        )

        # Schedule toxicity analysis if requested
        if request.analyze_toxicity:
            background_tasks.add_task(analyze_user_toxicity, username)
            response.status = "success_with_toxicity_pending"

        return response

    except Exception as e:
        return ScrapeResponse(
            username=username,
            status="error",
            error=str(e)
        )


@app.get("/user/{username}", response_model=ScrapeResponse)
async def get_user(username: str):
    """Get cached user data."""
    username = username.strip()
    data = get_user_data(username)

    if not data:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found in cache")

    toxicity = data.get("toxicity")

    return ScrapeResponse(
        username=username,
        status="cached",
        data=data,
        toxicity=toxicity
    )


@app.post("/toxicity/{username}")
async def run_toxicity(username: str):
    """Manually run toxicity analysis for a user."""
    username = username.strip()

    # Check if user was scraped
    data = get_user_data(username)
    if not data:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found. Scrape them first.")

    try:
        toxicity_scores = analyze_user_toxicity(username)
        return {
            "username": username,
            "status": "success",
            "toxicity": toxicity_scores
        }
    except Exception as e:
        return {
            "username": username,
            "status": "error",
            "error": str(e)
        }


@app.get("/stats")
async def get_stats():
    """Get scraping statistics."""
    db = load_db()

    users_with_toxicity = sum(1 for u in db.values() if u.get("toxicity"))

    return {
        "total_users_scraped": len(db),
        "users_with_toxicity_analysis": users_with_toxicity,
        "database_file": str(DB_FILE),
        "raw_data_dir": "raw_data/",
        "users": list(db.keys())
    }


@app.delete("/user/{username}")
async def delete_user(username: str):
    """Delete a user from the cache."""
    username = username.strip()
    db = load_db()

    if username.lower() not in db:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")

    del db[username.lower()]
    save_db(db)

    return {"status": "deleted", "username": username}


# ============================================================================
# Batch operations
# ============================================================================

@app.post("/scrape-batch")
async def scrape_batch(usernames: list[str], analyze_toxicity: bool = False, background_tasks: BackgroundTasks = None):
    """
    Scrape multiple users.

    - **usernames**: List of GitHub usernames
    - **analyze_toxicity**: If true, run toxicity analysis for all users
    """
    results = []

    for username in usernames:
        try:
            result = scrape_user(username)
            if result:
                save_user_data(username, result)
                results.append({
                    "username": username,
                    "status": "success"
                })

                # Schedule toxicity if requested
                if analyze_toxicity and background_tasks:
                    background_tasks.add_task(analyze_user_toxicity, username)
            else:
                results.append({
                    "username": username,
                    "status": "not_found"
                })
        except Exception as e:
            results.append({
                "username": username,
                "status": "error",
                "error": str(e)
            })

    return {
        "total": len(usernames),
        "results": results
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

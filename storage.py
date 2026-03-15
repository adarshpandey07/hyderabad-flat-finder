"""Persistence layer: JSON/CSV storage with deduplication."""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import config

logger = logging.getLogger(__name__)


class PostStore:
    """Manages post storage in JSON/CSV with deduplication."""

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or config.DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.json_path = self.data_dir / "posts.json"
        self.csv_path = self.data_dir / "posts.csv"
        self.last_run_path = self.data_dir / "last_run.json"

        self.posts: list[dict] = self._load_json()

    def _load_json(self) -> list[dict]:
        """Load existing posts from JSON file."""
        if self.json_path.exists():
            try:
                with open(self.json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load posts.json: {e}")
        return []

    def is_duplicate(self, new_post: dict) -> bool:
        """Check if a post is a duplicate using URL and content similarity."""
        new_url = new_post.get("post_url", "")
        new_text = new_post.get("description", "")

        # Only compare against recent posts for performance
        cutoff = datetime.now() - timedelta(days=config.DEDUP_LOOKBACK_DAYS)

        for existing in self.posts:
            # Level 1: URL match
            if new_url and existing.get("post_url") and new_url == existing["post_url"]:
                return True

            # Level 2: Content similarity (only recent posts)
            existing_date = existing.get("scraped_at", "")
            try:
                if existing_date:
                    post_dt = datetime.fromisoformat(existing_date)
                    if post_dt < cutoff:
                        continue
            except ValueError:
                pass

            existing_text = existing.get("description", "")
            if new_text and existing_text:
                ratio = SequenceMatcher(None, new_text, existing_text).ratio()
                if ratio > config.SIMILARITY_THRESHOLD:
                    return True

            # Level 3: Same phone + same price = likely duplicate
            new_phones = set(new_post.get("phone_numbers", []))
            existing_phones = set(existing.get("phone_numbers", []))
            if (
                new_phones
                and existing_phones
                and new_phones & existing_phones
                and new_post.get("price") == existing.get("price")
            ):
                return True

        return False

    def add_posts(self, posts: list[dict]) -> list[dict]:
        """Add posts, filtering out duplicates. Returns only NEW posts."""
        new_posts = []
        for post in posts:
            if not self.is_duplicate(post):
                self.posts.append(post)
                new_posts.append(post)
            else:
                logger.debug(f"Duplicate skipped: {post.get('post_url', 'no-url')}")

        logger.info(f"Added {len(new_posts)} new posts ({len(posts) - len(new_posts)} duplicates)")
        return new_posts

    def save(self) -> None:
        """Persist posts to JSON and CSV files."""
        self._save_json()
        self._save_csv()
        self._save_last_run()

    def _save_json(self) -> None:
        """Write all posts to JSON file."""
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(self.posts, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"Saved {len(self.posts)} posts to {self.json_path}")

    def _save_csv(self) -> None:
        """Export posts to CSV file."""
        if not self.posts:
            return

        fields = [
            "date", "group_name", "location", "price", "description",
            "contact", "post_url", "bhk_type", "relevance_score", "scraped_at",
        ]

        with open(self.csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(self.posts)
        logger.info(f"Exported {len(self.posts)} posts to {self.csv_path}")

    def _save_last_run(self) -> None:
        """Save last run metadata."""
        meta = {
            "last_run": datetime.now().isoformat(),
            "total_posts": len(self.posts),
        }
        with open(self.last_run_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

    def get_last_run_time(self) -> datetime | None:
        """Get the timestamp of the last scraper run."""
        if self.last_run_path.exists():
            try:
                with open(self.last_run_path, "r") as f:
                    data = json.load(f)
                return datetime.fromisoformat(data["last_run"])
            except (json.JSONDecodeError, KeyError, ValueError):
                pass
        return None

    def cleanup_old_posts(self, days: int = None) -> int:
        """Remove posts older than N days. Returns count of removed posts."""
        days = days or config.CLEANUP_AFTER_DAYS
        cutoff = datetime.now() - timedelta(days=days)
        before = len(self.posts)

        kept = []
        for post in self.posts:
            scraped = post.get("scraped_at", "")
            try:
                if scraped and datetime.fromisoformat(scraped) < cutoff:
                    continue
            except ValueError:
                pass
            kept.append(post)

        removed = before - len(kept)
        self.posts = kept
        if removed:
            logger.info(f"Cleaned up {removed} posts older than {days} days")
        return removed

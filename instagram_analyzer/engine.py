"""High-level analysis engine and business logic for Instagram Follower Analyzer with multi-tenancy."""

import csv
import io
import json
from typing import Dict, List, Optional, Tuple
from instagram_analyzer.database import Database
from instagram_analyzer.models import (
    AuditMetrics,
    DecisionType,
    DiffResult,
    InstagramAccount,
    RelationshipType,
    SnapshotMeta,
)
from instagram_analyzer.parser import ParsedEntry, parse_file, parse_zip_archive
from instagram_analyzer.sample_data import generate_sample_dataset


BRAND_KEYWORDS = {
    "official", "news", "mag", "times", "daily", "club", "co", "lab", "hq",
    "studio", "press", "media", "f1", "nba", "apple", "google", "nike", "patagonia"
}


def suggest_tags(username: str) -> List[str]:
    """Provide intelligent suggested tags based on username structure."""
    u = username.lower()
    tags = []
    if any(k in u for k in BRAND_KEYWORDS):
        tags.append("brand_or_media")
    if any(k in u for k in ["tech", "code", "dev", "ai", "crypto", "data"]):
        tags.append("tech")
    if any(k in u for k in ["fit", "gym", "run", "climb", "surf"]):
        tags.append("fitness")
    if any(k in u for k in ["photo", "art", "design", "film", "vintage"]):
        tags.append("creative")
    return tags


class FollowerEngine:
    def __init__(self, db: Optional[Database] = None, db_path: Optional[str] = None):
        self.db = db or Database(db_path=db_path)

    def load_sample_demo(self, snapshot_name: str = "Interactive Demo Snapshot", user_id: int = 1) -> int:
        """Seed database with realistic demo dataset scoped to a user."""
        followers, following = generate_sample_dataset()
        snap_id = self.db.save_snapshot(
            name=snapshot_name,
            followers=followers,
            following=following,
            user_id=user_id,
        )

        accounts = self.db.get_accounts(snapshot_id=snap_id, user_id=user_id, limit=500)
        for acc in accounts:
            tags = suggest_tags(acc.username)
            if tags:
                self.db.record_decision(
                    username=acc.username,
                    decision=acc.decision,
                    user_id=user_id,
                    tags=tags,
                )
        return snap_id

    def ingest_files(
        self,
        snapshot_name: str,
        followers_file: Optional[str] = None,
        following_file: Optional[str] = None,
        zip_file: Optional[str] = None,
        user_id: int = 1,
    ) -> int:
        """Parse uploaded or local files and store snapshot in database."""
        if zip_file:
            followers, following = parse_zip_archive(zip_file)
        elif followers_file and following_file:
            followers = parse_file(followers_file)
            following = parse_file(following_file)
        else:
            raise ValueError("Must provide either a zip file or both followers and following files")

        if not followers and not following:
            raise ValueError("No follower or following records could be extracted from files")

        snap_id = self.db.save_snapshot(
            name=snapshot_name,
            followers=followers,
            following=following,
            user_id=user_id,
        )

        accounts = self.db.get_accounts(snapshot_id=snap_id, user_id=user_id, limit=1000)
        for acc in accounts:
            tags = suggest_tags(acc.username)
            if tags:
                self.db.record_decision(
                    username=acc.username,
                    decision=acc.decision,
                    user_id=user_id,
                    tags=tags,
                )

        return snap_id

    def recompute(self, snapshot_id: Optional[int] = None, user_id: int = 1) -> AuditMetrics:
        """Recalculate metrics for current snapshot scoped to user."""
        return self.db.compute_metrics(snapshot_id=snapshot_id, user_id=user_id)

    def swipe(
        self,
        username: str,
        decision: DecisionType,
        user_id: int = 1,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> AuditMetrics:
        """Apply a swipe decision and immediately recompute metrics."""
        self.db.record_decision(
            username=username,
            decision=decision,
            user_id=user_id,
            tags=tags,
            notes=notes,
        )
        return self.recompute(user_id=user_id)

    def undo(self, user_id: int = 1) -> Tuple[Optional[Dict[str, str]], AuditMetrics]:
        """Undo last swipe decision and recompute."""
        restored = self.db.undo_last_decision(user_id=user_id)
        metrics = self.recompute(user_id=user_id)
        return restored, metrics

    def batch_decide(
        self,
        usernames: List[str],
        decision: DecisionType,
        user_id: int = 1,
        tags: Optional[List[str]] = None,
    ) -> AuditMetrics:
        """Apply decision to multiple accounts at once."""
        for u in usernames:
            self.db.record_decision(username=u, decision=decision, user_id=user_id, tags=tags)
        return self.recompute(user_id=user_id)

    def export_data(
        self,
        format_type: str = "csv",
        snapshot_id: Optional[int] = None,
        user_id: int = 1,
        relationship: Optional[RelationshipType] = None,
        decision: Optional[DecisionType] = None,
    ) -> str:
        """Export accounts into CSV, JSON, or Markdown checklist."""
        accounts = self.db.get_accounts(
            snapshot_id=snapshot_id,
            user_id=user_id,
            relationship=relationship,
            decision=decision,
            limit=50000,
        )

        if format_type == "json":
            return json.dumps([a.model_dump() for a in accounts], indent=2)

        elif format_type == "markdown":
            output = ["# Instagram Follower Audit Checklist\n"]
            output.append(f"Total Accounts: {len(accounts)}\n")
            output.append("| Status | Username | Relationship | Decision | Tags | Followed At | Profile Link |")
            output.append("|---|---|---|---|---|---|---|")
            for a in accounts:
                box = "[x]" if a.decision == DecisionType.UNFOLLOWED else "[ ]"
                tags_str = ", ".join(a.tags) if a.tags else "-"
                date_str = a.followed_at or "-"
                output.append(
                    f"| {box} | @{a.username} | {a.relationship.value} | {a.decision.value} | {tags_str} | {date_str} | [{a.username}]({a.profile_url}) |"
                )
            return "\n".join(output)

        else:  # CSV default
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["username", "relationship", "decision", "tags", "followed_at", "profile_url", "notes"])
            for a in accounts:
                writer.writerow([
                    a.username,
                    a.relationship.value,
                    a.decision.value,
                    ";".join(a.tags),
                    a.followed_at or "",
                    a.profile_url,
                    a.notes or "",
                ])
            return buf.getvalue()

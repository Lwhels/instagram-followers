"""SQLite database storage engine for Instagram Follower Analyzer."""

import json
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from instagram_analyzer.models import (
    AuditMetrics,
    DecisionType,
    DiffResult,
    InstagramAccount,
    RelationshipType,
    SnapshotMeta,
)
from instagram_analyzer.parser import ParsedEntry


class Database:
    def __init__(self, db_path: str = "follower_vault.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    follower_count INTEGER DEFAULT 0,
                    following_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    display_name TEXT,
                    profile_url TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS snapshot_relations (
                    snapshot_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    is_follower INTEGER NOT NULL DEFAULT 0,
                    is_following INTEGER NOT NULL DEFAULT 0,
                    followed_at TEXT,
                    relationship TEXT NOT NULL,
                    PRIMARY KEY (snapshot_id, username),
                    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
                    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_decisions (
                    username TEXT PRIMARY KEY,
                    decision TEXT NOT NULL DEFAULT 'unreviewed',
                    tags TEXT DEFAULT '[]',
                    notes TEXT,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS decision_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    previous_decision TEXT,
                    new_decision TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_relations_snapshot ON snapshot_relations(snapshot_id);
                CREATE INDEX IF NOT EXISTS idx_relations_rel ON snapshot_relations(relationship);
                CREATE INDEX IF NOT EXISTS idx_decisions_dec ON user_decisions(decision);
            """)

    def save_snapshot(
        self,
        name: str,
        followers: List[ParsedEntry],
        following: List[ParsedEntry],
        timestamp: Optional[str] = None,
    ) -> int:
        """Create a new snapshot and compute relationships."""
        now = timestamp or datetime.utcnow().isoformat()
        follower_map = {f.username: f for f in followers}
        following_map = {f.username: f for f in following}
        all_usernames = set(follower_map.keys()) | set(following_map.keys())

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO snapshots (name, created_at, follower_count, following_count)
                VALUES (?, ?, ?, ?)
                """,
                (name, now, len(followers), len(following)),
            )
            snapshot_id = cursor.lastrowid

            for uname in all_usernames:
                entry = following_map.get(uname) or follower_map.get(uname)
                cursor.execute(
                    """
                    INSERT INTO users (username, display_name, profile_url, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(username) DO UPDATE SET
                        profile_url = excluded.profile_url,
                        last_seen = excluded.last_seen
                    """,
                    (uname, None, entry.profile_url, now, now),
                )

                # Ensure user_decisions entry exists
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO user_decisions (username, decision, tags, notes, updated_at)
                    VALUES (?, 'unreviewed', '[]', NULL, ?)
                    """,
                    (uname, now),
                )

                is_follower = 1 if uname in follower_map else 0
                is_following = 1 if uname in following_map else 0

                if is_follower and is_following:
                    rel = RelationshipType.MUTUAL.value
                elif is_following and not is_follower:
                    rel = RelationshipType.UNRECIPROCATED.value
                elif is_follower and not is_following:
                    rel = RelationshipType.FAN.value
                else:
                    rel = RelationshipType.NEITHER.value

                followed_at = None
                if entry and entry.timestamp_str:
                    followed_at = entry.timestamp_str

                cursor.execute(
                    """
                    INSERT INTO snapshot_relations (snapshot_id, username, is_follower, is_following, followed_at, relationship)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (snapshot_id, uname, is_follower, is_following, followed_at, rel),
                )

            conn.commit()
            return snapshot_id

    def get_latest_snapshot_id(self) -> Optional[int]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT id FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
            return row["id"] if row else None

    def list_snapshots(self) -> List[SnapshotMeta]:
        with self._get_connection() as conn:
            rows = conn.execute("SELECT * FROM snapshots ORDER BY id DESC").fetchall()
            return [
                SnapshotMeta(
                    id=r["id"],
                    name=r["name"],
                    created_at=r["created_at"],
                    follower_count=r["follower_count"],
                    following_count=r["following_count"],
                )
                for r in rows
            ]

    def record_decision(
        self,
        username: str,
        decision: DecisionType,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Mutate a user's decision in the database and record history for undo."""
        now = datetime.utcnow().isoformat()
        clean_uname = username.strip().lstrip("@").lower()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            existing = cursor.execute(
                "SELECT decision, tags, notes FROM user_decisions WHERE username = ?",
                (clean_uname,),
            ).fetchone()

            prev_decision = existing["decision"] if existing else "unreviewed"
            tags_json = json.dumps(tags if tags is not None else (json.loads(existing["tags"]) if existing and existing["tags"] else []))

            cursor.execute(
                """
                INSERT INTO user_decisions (username, decision, tags, notes, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    decision = excluded.decision,
                    tags = excluded.tags,
                    notes = coalesce(excluded.notes, user_decisions.notes),
                    updated_at = excluded.updated_at
                """,
                (clean_uname, decision.value, tags_json, notes, now),
            )

            cursor.execute(
                """
                INSERT INTO decision_history (username, previous_decision, new_decision, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (clean_uname, prev_decision, decision.value, now),
            )
            conn.commit()

    def undo_last_decision(self) -> Optional[Dict[str, str]]:
        """Undo the most recent decision and restore previous state."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            last = cursor.execute(
                "SELECT * FROM decision_history ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if not last:
                return None

            username = last["username"]
            prev_decision = last["previous_decision"] or "unreviewed"
            now = datetime.utcnow().isoformat()

            cursor.execute(
                """
                UPDATE user_decisions
                SET decision = ?, updated_at = ?
                WHERE username = ?
                """,
                (prev_decision, now, username),
            )
            cursor.execute("DELETE FROM decision_history WHERE id = ?", (last["id"],))
            conn.commit()
            return {"username": username, "restored_decision": prev_decision}

    def compute_metrics(self, snapshot_id: Optional[int] = None) -> AuditMetrics:
        """Recompute current audit metrics for the specified snapshot."""
        sid = snapshot_id or self.get_latest_snapshot_id()
        if not sid:
            return AuditMetrics()

        with self._get_connection() as conn:
            snap = conn.execute("SELECT * FROM snapshots WHERE id = ?", (sid,)).fetchone()
            if not snap:
                return AuditMetrics()

            query = """
                SELECT
                    sr.relationship,
                    coalesce(ud.decision, 'unreviewed') as decision
                FROM snapshot_relations sr
                LEFT JOIN user_decisions ud ON sr.username = ud.username
                WHERE sr.snapshot_id = ?
            """
            rows = conn.execute(query, (sid,)).fetchall()

            total_followers = snap["follower_count"]
            total_following = snap["following_count"]
            mutual_count = 0
            fan_count = 0
            unreciprocated_raw_count = 0
            whitelisted_count = 0
            unfollow_candidates_count = 0
            unfollowed_count = 0
            vip_count = 0
            actionable_unreciprocated = 0

            for r in rows:
                rel = r["relationship"]
                dec = r["decision"]

                if rel == RelationshipType.MUTUAL.value:
                    mutual_count += 1
                elif rel == RelationshipType.FAN.value:
                    fan_count += 1
                elif rel == RelationshipType.UNRECIPROCATED.value:
                    unreciprocated_raw_count += 1
                    if dec == DecisionType.WHITELIST.value:
                        whitelisted_count += 1
                    elif dec == DecisionType.UNFOLLOW_CANDIDATE.value:
                        unfollow_candidates_count += 1
                        actionable_unreciprocated += 1
                    elif dec == DecisionType.UNFOLLOWED.value:
                        unfollowed_count += 1
                    elif dec == DecisionType.VIP.value:
                        vip_count += 1
                    else:  # unreviewed
                        actionable_unreciprocated += 1

            reciprocity = (mutual_count / total_following * 100.0) if total_following > 0 else 0.0

            return AuditMetrics(
                snapshot_id=sid,
                total_following=total_following,
                total_followers=total_followers,
                mutual_count=mutual_count,
                fan_count=fan_count,
                unreciprocated_raw_count=unreciprocated_raw_count,
                whitelisted_count=whitelisted_count,
                unfollow_candidates_count=unfollow_candidates_count,
                unfollowed_count=unfollowed_count,
                vip_count=vip_count,
                actionable_unreciprocated_count=actionable_unreciprocated,
                reciprocity_rate=round(reciprocity, 2),
            )

    def get_accounts(
        self,
        snapshot_id: Optional[int] = None,
        relationship: Optional[RelationshipType] = None,
        decision: Optional[DecisionType] = None,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[InstagramAccount]:
        """Fetch accounts matching criteria."""
        sid = snapshot_id or self.get_latest_snapshot_id()
        if not sid:
            return []

        conditions = ["sr.snapshot_id = ?"]
        params = [sid]

        if relationship:
            conditions.append("sr.relationship = ?")
            params.append(relationship.value)

        if decision:
            conditions.append("coalesce(ud.decision, 'unreviewed') = ?")
            params.append(decision.value)

        if search:
            conditions.append("sr.username LIKE ?")
            params.append(f"%{search.strip().lower()}%")

        where_clause = " AND ".join(conditions)
        sql = f"""
            SELECT
                sr.username,
                u.profile_url,
                u.display_name,
                sr.followed_at,
                sr.relationship,
                coalesce(ud.decision, 'unreviewed') as decision,
                coalesce(ud.tags, '[]') as tags,
                ud.notes,
                u.first_seen,
                u.last_seen
            FROM snapshot_relations sr
            JOIN users u ON sr.username = u.username
            LEFT JOIN user_decisions ud ON sr.username = ud.username
            WHERE {where_clause}
            ORDER BY
                CASE coalesce(ud.decision, 'unreviewed')
                    WHEN 'unreviewed' THEN 0
                    WHEN 'unfollow_candidate' THEN 1
                    WHEN 'whitelist' THEN 2
                    WHEN 'vip' THEN 3
                    ELSE 4
                END,
                sr.username ASC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            accounts = []
            for r in rows:
                tags = []
                try:
                    tags = json.loads(r["tags"])
                except Exception:
                    tags = []
                accounts.append(
                    InstagramAccount(
                        username=r["username"],
                        profile_url=r["profile_url"],
                        display_name=r["display_name"],
                        followed_at=r["followed_at"],
                        relationship=RelationshipType(r["relationship"]),
                        decision=DecisionType(r["decision"]),
                        tags=tags,
                        notes=r["notes"],
                        first_seen=r["first_seen"],
                        last_seen=r["last_seen"],
                    )
                )
            return accounts

    def get_swipe_deck(
        self,
        snapshot_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[InstagramAccount]:
        """Fetch candidate accounts for swipe UI (unreciprocated and unreviewed)."""
        sid = snapshot_id or self.get_latest_snapshot_id()
        if not sid:
            return []

        sql = """
            SELECT
                sr.username,
                u.profile_url,
                u.display_name,
                sr.followed_at,
                sr.relationship,
                coalesce(ud.decision, 'unreviewed') as decision,
                coalesce(ud.tags, '[]') as tags,
                ud.notes,
                u.first_seen,
                u.last_seen
            FROM snapshot_relations sr
            JOIN users u ON sr.username = u.username
            LEFT JOIN user_decisions ud ON sr.username = ud.username
            WHERE sr.snapshot_id = ?
              AND sr.relationship = 'unreciprocated'
              AND coalesce(ud.decision, 'unreviewed') = 'unreviewed'
            ORDER BY sr.followed_at ASC, sr.username ASC
            LIMIT ?
        """
        with self._get_connection() as conn:
            rows = conn.execute(sql, (sid, limit)).fetchall()
            deck = []
            for r in rows:
                tags = []
                try:
                    tags = json.loads(r["tags"])
                except Exception:
                    tags = []
                deck.append(
                    InstagramAccount(
                        username=r["username"],
                        profile_url=r["profile_url"],
                        display_name=r["display_name"],
                        followed_at=r["followed_at"],
                        relationship=RelationshipType(r["relationship"]),
                        decision=DecisionType(r["decision"]),
                        tags=tags,
                        notes=r["notes"],
                        first_seen=r["first_seen"],
                        last_seen=r["last_seen"],
                    )
                )
            return deck

    def diff_snapshots(self, snapshot_a_id: int, snapshot_b_id: int) -> DiffResult:
        """Compare two snapshots to find follower dynamics."""
        with self._get_connection() as conn:
            snap_a = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_a_id,)).fetchone()
            snap_b = conn.execute("SELECT * FROM snapshots WHERE id = ?", (snapshot_b_id,)).fetchone()

            if not snap_a or not snap_b:
                raise ValueError("One or both snapshot IDs not found")

            # Snapshot A
            rows_a = conn.execute(
                "SELECT username, is_follower, is_following FROM snapshot_relations WHERE snapshot_id = ?",
                (snapshot_a_id,),
            ).fetchall()
            followers_a = {r["username"] for r in rows_a if r["is_follower"]}
            following_a = {r["username"] for r in rows_a if r["is_following"]}

            # Snapshot B
            rows_b = conn.execute(
                "SELECT username, is_follower, is_following FROM snapshot_relations WHERE snapshot_id = ?",
                (snapshot_b_id,),
            ).fetchall()
            followers_b = {r["username"] for r in rows_b if r["is_follower"]}
            following_b = {r["username"] for r in rows_b if r["is_following"]}

            lost_followers_unames = followers_a - followers_b
            new_followers_unames = followers_b - followers_a
            unfollowed_by_you_unames = following_a - following_b
            new_following_unames = following_b - following_a

            def make_accs(unames):
                return [InstagramAccount(username=u) for u in sorted(unames)]

            return DiffResult(
                snapshot_a_id=snapshot_a_id,
                snapshot_b_id=snapshot_b_id,
                snapshot_a_name=snap_a["name"],
                snapshot_b_name=snap_b["name"],
                lost_followers=make_accs(lost_followers_unames),
                new_followers=make_accs(new_followers_unames),
                unfollowed_by_you=make_accs(unfollowed_by_you_unames),
                new_following=make_accs(new_following_unames),
            )

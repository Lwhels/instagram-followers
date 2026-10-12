"""SQLite database storage engine for Instagram Follower Analyzer with multi-tenancy support."""

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
    UploadJobResponse,
    UploadJobStatus,
)
from instagram_analyzer.parser import ParsedEntry


class Database:
    def __init__(self, db_path: Optional[str] = None):
        raw_path = db_path or os.getenv("DATABASE_PATH", os.getenv("DATABASE_URL", "follower_vault.db"))
        if raw_path.startswith("sqlite:///"):
            raw_path = raw_path.replace("sqlite:///", "")
        self.db_path = raw_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _migrate_existing_tables(self, conn: sqlite3.Connection):
        """Perform non-destructive schema migrations for existing databases."""
        tables_to_check = {
            "snapshots": "user_id INTEGER NOT NULL DEFAULT 1",
            "snapshot_relations": "user_id INTEGER NOT NULL DEFAULT 1",
            "user_decisions": "user_id INTEGER NOT NULL DEFAULT 1",
            "decision_history": "user_id INTEGER NOT NULL DEFAULT 1",
        }
        allowed_tables = {"user_accounts", "snapshot_relations", "user_decisions", "decision_history"}
        for table, col_def in tables_to_check.items():
            if table not in allowed_tables:
                continue
            # Check if table exists
            table_exists = conn.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()[0]
            if table_exists:
                columns = [
                    row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()  # nosec B608
                ]
                col_name = col_def.split()[0]
                if col_name not in columns and re.match(r"^[a-zA-Z0-9_ ]+$", col_def):
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")  # nosec B608

    def _init_db(self):
        with self._get_connection() as conn:
            # 1. First create tables that may not exist
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS app_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    display_name TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS upload_jobs (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    file_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    total_items INTEGER DEFAULT 0,
                    processed_items INTEGER DEFAULT 0,
                    progress_percent REAL DEFAULT 0.0,
                    snapshot_id INTEGER,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    follower_count INTEGER DEFAULT 0,
                    following_count INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_accounts (
                    user_id INTEGER NOT NULL DEFAULT 1,
                    username TEXT NOT NULL,
                    display_name TEXT,
                    profile_url TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    PRIMARY KEY (user_id, username),
                    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS snapshot_relations (
                    snapshot_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    username TEXT NOT NULL,
                    is_follower INTEGER NOT NULL DEFAULT 0,
                    is_following INTEGER NOT NULL DEFAULT 0,
                    followed_at TEXT,
                    relationship TEXT NOT NULL,
                    PRIMARY KEY (snapshot_id, username),
                    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS user_decisions (
                    user_id INTEGER NOT NULL DEFAULT 1,
                    username TEXT NOT NULL,
                    decision TEXT NOT NULL DEFAULT 'unreviewed',
                    tags TEXT DEFAULT '[]',
                    notes TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, username),
                    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS decision_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL DEFAULT 1,
                    username TEXT NOT NULL,
                    previous_decision TEXT,
                    new_decision TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES app_users(id) ON DELETE CASCADE
                );
            """)

            # 2. Check and migrate columns if database was created with an earlier version
            self._migrate_existing_tables(conn)

            # 3. Create indices safely
            conn.executescript("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_user ON snapshots(user_id);
                CREATE INDEX IF NOT EXISTS idx_relations_snapshot ON snapshot_relations(snapshot_id);
                CREATE INDEX IF NOT EXISTS idx_relations_user ON snapshot_relations(user_id);
                CREATE INDEX IF NOT EXISTS idx_decisions_user_dec ON user_decisions(user_id, decision);
                CREATE INDEX IF NOT EXISTS idx_jobs_user ON upload_jobs(user_id);
            """)

            # Ensure default demo user exists for backwards compatibility
            now = datetime.utcnow().isoformat()
            conn.execute(
                """
                INSERT OR IGNORE INTO app_users (id, email, password_hash, display_name, created_at, updated_at)
                VALUES (1, 'demo@followervault.local', '$2b$12$e8F5Yq.VqVqVqVqVqVqVq.fakehashforbackwardcompat', 'Demo User', ?, ?)
                """,
                (now, now),
            )
            conn.commit()

    # -------------------------------------------------------------
    # User Authentication Management
    # -------------------------------------------------------------
    def create_user(self, email: str, password_hash: str, display_name: Optional[str] = None) -> int:
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO app_users (email, password_hash, display_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (email.strip().lower(), password_hash, display_name or email.split("@")[0], now, now),
            )
            conn.commit()
            return cursor.lastrowid

    def get_user_by_email(self, email: str) -> Optional[dict]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM app_users WHERE email = ?",
                (email.strip().lower(),),
            ).fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[dict]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM app_users WHERE id = ?",
                (user_id,),
            ).fetchone()
            return dict(row) if row else None

    # -------------------------------------------------------------
    # Upload Job Management
    # -------------------------------------------------------------
    def create_upload_job(self, job_id: str, user_id: int, filename: str, file_type: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO upload_jobs (id, user_id, filename, file_type, status, stage, progress_percent, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 0.0, ?)
                """,
                (job_id, user_id, filename, file_type, UploadJobStatus.PENDING.value, "queued", now),
            )
            conn.commit()

    def update_upload_job(
        self,
        job_id: str,
        status: Optional[UploadJobStatus] = None,
        stage: Optional[str] = None,
        progress: Optional[float] = None,
        total_items: Optional[int] = None,
        processed_items: Optional[int] = None,
    ) -> None:
        updates = []
        params = []
        if status:
            updates.append("status = ?")
            params.append(status.value)
        if stage:
            updates.append("stage = ?")
            params.append(stage)
        if progress is not None:
            updates.append("progress_percent = ?")
            params.append(progress)
        if total_items is not None:
            updates.append("total_items = ?")
            params.append(total_items)
        if processed_items is not None:
            updates.append("processed_items = ?")
            params.append(processed_items)

        allowed_setters = {"status = ?", "stage = ?", "progress_percent = ?", "total_items = ?", "processed_items = ?"}
        if not updates or not all(u in allowed_setters for u in updates):
            return

        params.append(job_id)
        sql = f"UPDATE upload_jobs SET {', '.join(updates)} WHERE id = ?"  # nosec B608
        with self._get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    def complete_upload_job(self, job_id: str, snapshot_id: int) -> None:
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE upload_jobs
                SET status = ?, stage = 'completed', progress_percent = 100.0, snapshot_id = ?, completed_at = ?
                WHERE id = ?
                """,
                (UploadJobStatus.COMPLETED.value, snapshot_id, now, job_id),
            )
            conn.commit()

    def fail_upload_job(self, job_id: str, error_message: str) -> None:
        now = datetime.utcnow().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE upload_jobs
                SET status = ?, stage = 'failed', error_message = ?, completed_at = ?
                WHERE id = ?
                """,
                (UploadJobStatus.FAILED.value, error_message, now, job_id),
            )
            conn.commit()

    def get_upload_job(self, job_id: str, user_id: int) -> Optional[UploadJobResponse]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM upload_jobs WHERE id = ? AND user_id = ?",
                (job_id, user_id),
            ).fetchone()
            if not row:
                return None
            return UploadJobResponse(
                job_id=row["id"],
                user_id=row["user_id"],
                filename=row["filename"],
                file_type=row["file_type"],
                status=UploadJobStatus(row["status"]),
                stage=row["stage"],
                total_items=row["total_items"],
                processed_items=row["processed_items"],
                progress_percent=row["progress_percent"],
                snapshot_id=row["snapshot_id"],
                error_message=row["error_message"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
            )

    # -------------------------------------------------------------
    # Snapshots & Follower Relational Logic (Scoped to user_id)
    # -------------------------------------------------------------
    def save_snapshot(
        self,
        name: str,
        followers: List[ParsedEntry],
        following: List[ParsedEntry],
        user_id: int = 1,
        timestamp: Optional[str] = None,
    ) -> int:
        now = timestamp or datetime.utcnow().isoformat()
        follower_map = {f.username: f for f in followers}
        following_map = {f.username: f for f in following}
        all_usernames = set(follower_map.keys()) | set(following_map.keys())

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO snapshots (user_id, name, created_at, follower_count, following_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, name, now, len(followers), len(following)),
            )
            snapshot_id = cursor.lastrowid

            for uname in all_usernames:
                entry = following_map.get(uname) or follower_map.get(uname)
                cursor.execute(
                    """
                    INSERT INTO user_accounts (user_id, username, display_name, profile_url, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user_id, username) DO UPDATE SET
                        profile_url = excluded.profile_url,
                        last_seen = excluded.last_seen
                    """,
                    (user_id, uname, None, entry.profile_url, now, now),
                )

                # Ensure user_decisions entry exists for this user_id
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO user_decisions (user_id, username, decision, tags, notes, updated_at)
                    VALUES (?, ?, 'unreviewed', '[]', NULL, ?)
                    """,
                    (user_id, uname, now),
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

                followed_at = entry.timestamp_str if entry else None

                cursor.execute(
                    """
                    INSERT INTO snapshot_relations (snapshot_id, user_id, username, is_follower, is_following, followed_at, relationship)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (snapshot_id, user_id, uname, is_follower, is_following, followed_at, rel),
                )

            conn.commit()
            return snapshot_id

    def get_latest_snapshot_id(self, user_id: int = 1) -> Optional[int]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM snapshots WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            return row["id"] if row else None

    def list_snapshots(self, user_id: int = 1) -> List[SnapshotMeta]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshots WHERE user_id = ? ORDER BY id DESC",
                (user_id,),
            ).fetchall()
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
        user_id: int = 1,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> None:
        now = datetime.utcnow().isoformat()
        clean_uname = username.strip().lstrip("@").lower()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            existing = cursor.execute(
                "SELECT decision, tags, notes FROM user_decisions WHERE user_id = ? AND username = ?",
                (user_id, clean_uname),
            ).fetchone()

            prev_decision = existing["decision"] if existing else "unreviewed"
            tags_json = json.dumps(tags if tags is not None else (json.loads(existing["tags"]) if existing and existing["tags"] else []))

            cursor.execute(
                """
                INSERT INTO user_decisions (user_id, username, decision, tags, notes, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, username) DO UPDATE SET
                    decision = excluded.decision,
                    tags = excluded.tags,
                    notes = coalesce(excluded.notes, user_decisions.notes),
                    updated_at = excluded.updated_at
                """,
                (user_id, clean_uname, decision.value, tags_json, notes, now),
            )

            cursor.execute(
                """
                INSERT INTO decision_history (user_id, username, previous_decision, new_decision, timestamp)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, clean_uname, prev_decision, decision.value, now),
            )
            conn.commit()

    def undo_last_decision(self, user_id: int = 1) -> Optional[Dict[str, str]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            last = cursor.execute(
                "SELECT * FROM decision_history WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
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
                WHERE user_id = ? AND username = ?
                """,
                (prev_decision, now, user_id, username),
            )
            cursor.execute("DELETE FROM decision_history WHERE id = ?", (last["id"],))
            conn.commit()
            return {"username": username, "restored_decision": prev_decision}

    def compute_metrics(self, snapshot_id: Optional[int] = None, user_id: int = 1) -> AuditMetrics:
        sid = snapshot_id or self.get_latest_snapshot_id(user_id=user_id)
        if not sid:
            return AuditMetrics()

        with self._get_connection() as conn:
            snap = conn.execute(
                "SELECT * FROM snapshots WHERE id = ? AND user_id = ?",
                (sid, user_id),
            ).fetchone()
            if not snap:
                return AuditMetrics()

            query = """
                SELECT
                    sr.relationship,
                    coalesce(ud.decision, 'unreviewed') as decision
                FROM snapshot_relations sr
                LEFT JOIN user_decisions ud ON sr.username = ud.username AND ud.user_id = ?
                WHERE sr.snapshot_id = ? AND sr.user_id = ?
            """
            rows = conn.execute(query, (user_id, sid, user_id)).fetchall()

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
                    else:
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
        user_id: int = 1,
        relationship: Optional[RelationshipType] = None,
        decision: Optional[DecisionType] = None,
        search: Optional[str] = None,
        limit: int = 500,
        offset: int = 0,
    ) -> List[InstagramAccount]:
        sid = snapshot_id or self.get_latest_snapshot_id(user_id=user_id)
        if not sid:
            return []

        conditions = ["sr.snapshot_id = ?", "sr.user_id = ?"]
        params = [sid, user_id]

        if relationship:
            conditions.append("sr.relationship = ?")
            params.append(relationship.value)

        if decision:
            conditions.append("coalesce(ud.decision, 'unreviewed') = ?")
            params.append(decision.value)

        if search:
            escaped_search = (
                search.strip()
                .lower()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            conditions.append("sr.username LIKE ? ESCAPE '\\'")
            params.append(f"%{escaped_search}%")

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
            JOIN user_accounts u ON sr.username = u.username AND u.user_id = sr.user_id
            LEFT JOIN user_decisions ud ON sr.username = ud.username AND ud.user_id = sr.user_id
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
        """  # nosec B608
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
        user_id: int = 1,
        limit: int = 50,
    ) -> List[InstagramAccount]:
        sid = snapshot_id or self.get_latest_snapshot_id(user_id=user_id)
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
            JOIN user_accounts u ON sr.username = u.username AND u.user_id = sr.user_id
            LEFT JOIN user_decisions ud ON sr.username = ud.username AND ud.user_id = sr.user_id
            WHERE sr.snapshot_id = ?
              AND sr.user_id = ?
              AND sr.relationship = 'unreciprocated'
              AND coalesce(ud.decision, 'unreviewed') = 'unreviewed'
            ORDER BY sr.followed_at ASC, sr.username ASC
            LIMIT ?
        """
        with self._get_connection() as conn:
            rows = conn.execute(sql, (sid, user_id, limit)).fetchall()
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

    def diff_snapshots(self, snapshot_a_id: int, snapshot_b_id: int, user_id: int = 1) -> DiffResult:
        with self._get_connection() as conn:
            snap_a = conn.execute(
                "SELECT * FROM snapshots WHERE id = ? AND user_id = ?",
                (snapshot_a_id, user_id),
            ).fetchone()
            snap_b = conn.execute(
                "SELECT * FROM snapshots WHERE id = ? AND user_id = ?",
                (snapshot_b_id, user_id),
            ).fetchone()

            if not snap_a or not snap_b:
                raise ValueError("One or both snapshot IDs not found for this user")

            rows_a = conn.execute(
                "SELECT username, is_follower, is_following FROM snapshot_relations WHERE snapshot_id = ? AND user_id = ?",
                (snapshot_a_id, user_id),
            ).fetchall()
            followers_a = {r["username"] for r in rows_a if r["is_follower"]}
            following_a = {r["username"] for r in rows_a if r["is_following"]}

            rows_b = conn.execute(
                "SELECT username, is_follower, is_following FROM snapshot_relations WHERE snapshot_id = ? AND user_id = ?",
                (snapshot_b_id, user_id),
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

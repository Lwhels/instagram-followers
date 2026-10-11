"""Cloud Firestore storage backend for Follower Vault.
Implements the Document Bucketing Pattern to ensure 100% compatibility with
Firebase's free Spark Tier (prevents exceeding the 20k writes / 50k reads quota).
"""

import json
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

# Chunk accounts into buckets of 500 to stay well under the 1 MB Firestore document limit
BUCKET_SIZE = 500


class FirestoreStorage:
    def __init__(self, client=None, project_id: Optional[str] = None):
        """
        Initialize Firestore storage adapter.
        If client is None, attempts to load from google.cloud.firestore.
        """
        if client:
            self.db = client
        else:
            try:
                import firebase_admin
                from firebase_admin import credentials, firestore

                if not firebase_admin._apps:
                    firebase_admin.initialize_app()
                self.db = firestore.client()
            except Exception:
                from google.cloud import firestore
                self.db = firestore.Client(project=project_id)

    def _user_ref(self, user_id: str):
        return self.db.collection("users").document(str(user_id))

    def _decisions_ref(self, user_id: str):
        return self._user_ref(user_id).collection("settings").document("decisions")

    def save_snapshot(
        self,
        name: str,
        followers: List[ParsedEntry],
        following: List[ParsedEntry],
        user_id: str = "demo_user",
        timestamp: Optional[str] = None,
    ) -> str:
        """
        Save snapshot using the Document Bucketing Pattern.
        Instead of creating 1 document per account (which wastes thousands of writes),
        we store followers and following lists in bucketed documents.
        """
        now = timestamp or datetime.utcnow().isoformat()
        snapshot_id = f"snap_{int(datetime.utcnow().timestamp())}"

        f_map = {f.username: f.timestamp_str for f in followers}
        fg_map = {f.username: f.timestamp_str for f in following}
        all_unames = sorted(list(set(f_map.keys()) | set(fg_map.keys())))

        # 1. Write snapshot metadata (1 write)
        snap_ref = self._user_ref(user_id).collection("snapshots").document(snapshot_id)
        snap_ref.set({
            "id": snapshot_id,
            "name": name,
            "created_at": now,
            "follower_count": len(followers),
            "following_count": len(following),
        })

        # 2. Write bucketed account documents (e.g. 2,000 accounts = 4 writes)
        batch = self.db.batch()
        batch_count = 0

        for i in range(0, len(all_unames), BUCKET_SIZE):
            chunk = all_unames[i : i + BUCKET_SIZE]
            accounts_data = []

            for uname in chunk:
                is_f = uname in f_map
                is_fg = uname in fg_map
                if is_f and is_fg:
                    rel = RelationshipType.MUTUAL.value
                elif is_fg and not is_f:
                    rel = RelationshipType.UNRECIPROCATED.value
                elif is_f and not is_fg:
                    rel = RelationshipType.FAN.value
                else:
                    rel = RelationshipType.NEITHER.value

                accounts_data.append({
                    "u": uname,
                    "rel": rel,
                    "t": fg_map.get(uname) or f_map.get(uname),
                })

            bucket_ref = snap_ref.collection("buckets").document(f"bucket_{i // BUCKET_SIZE}")
            batch.set(bucket_ref, {"accounts": accounts_data})
            batch_count += 1

            if batch_count >= 400:  # Commit before Firestore's 500 batch limit
                batch.commit()
                batch = self.db.batch()
                batch_count = 0

        if batch_count > 0:
            batch.commit()

        return snapshot_id

    def record_decision(
        self,
        username: str,
        decision: DecisionType,
        user_id: str = "demo_user",
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> None:
        """Update user decision dictionary in a single document (1 write)."""
        now = datetime.utcnow().isoformat()
        clean_u = username.strip().lstrip("@").lower()
        dec_ref = self._decisions_ref(user_id)

        dec_data = {
            "decision": decision.value,
            "tags": tags or [],
            "notes": notes,
            "updated_at": now,
        }
        dec_ref.set({clean_u: dec_data}, merge=True)

    def get_decisions(self, user_id: str = "demo_user") -> Dict[str, dict]:
        """Fetch all user decisions (1 read)."""
        doc = self._decisions_ref(user_id).get()
        return doc.to_dict() or {} if doc.exists else {}

    def get_snapshot_accounts(self, snapshot_id: str, user_id: str = "demo_user") -> List[InstagramAccount]:
        """Fetch all accounts in a snapshot across buckets (1-3 reads total)."""
        snap_ref = self._user_ref(user_id).collection("snapshots").document(snapshot_id)
        bucket_docs = snap_ref.collection("buckets").stream()
        decisions = self.get_decisions(user_id)

        accounts = []
        for b in bucket_docs:
            data = b.to_dict()
            for item in data.get("accounts", []):
                u = item["u"]
                user_dec = decisions.get(u, {})
                dec = user_dec.get("decision", DecisionType.UNREVIEWED.value)
                tags = user_dec.get("tags", [])
                notes = user_dec.get("notes")

                accounts.append(
                    InstagramAccount(
                        username=u,
                        followed_at=item.get("t"),
                        relationship=RelationshipType(item["rel"]),
                        decision=DecisionType(dec),
                        tags=tags,
                        notes=notes,
                    )
                )
        return accounts

    def compute_metrics(self, snapshot_id: str, user_id: str = "demo_user") -> AuditMetrics:
        """Compute metrics in memory from bucketed snapshot documents."""
        accounts = self.get_snapshot_accounts(snapshot_id, user_id)
        snap_doc = self._user_ref(user_id).collection("snapshots").document(snapshot_id).get()
        snap_meta = snap_doc.to_dict() or {}

        total_followers = snap_meta.get("follower_count", 0)
        total_following = snap_meta.get("following_count", 0)
        mutual_count = 0
        fan_count = 0
        unreciprocated_raw_count = 0
        whitelisted_count = 0
        unfollow_candidates_count = 0
        actionable_unreciprocated = 0

        for a in accounts:
            if a.relationship == RelationshipType.MUTUAL:
                mutual_count += 1
            elif a.relationship == RelationshipType.FAN:
                fan_count += 1
            elif a.relationship == RelationshipType.UNRECIPROCATED:
                unreciprocated_raw_count += 1
                if a.decision == DecisionType.WHITELIST:
                    whitelisted_count += 1
                elif a.decision == DecisionType.UNFOLLOW_CANDIDATE:
                    unfollow_candidates_count += 1
                    actionable_unreciprocated += 1
                elif a.decision == DecisionType.UNREVIEWED:
                    actionable_unreciprocated += 1

        reciprocity = (mutual_count / total_following * 100.0) if total_following > 0 else 0.0

        return AuditMetrics(
            total_following=total_following,
            total_followers=total_followers,
            mutual_count=mutual_count,
            fan_count=fan_count,
            unreciprocated_raw_count=unreciprocated_raw_count,
            whitelisted_count=whitelisted_count,
            unfollow_candidates_count=unfollow_candidates_count,
            actionable_unreciprocated_count=actionable_unreciprocated,
            reciprocity_rate=round(reciprocity, 2),
        )

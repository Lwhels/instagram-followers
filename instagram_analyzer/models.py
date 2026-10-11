"""Data models for Instagram Follower Analyzer."""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class RelationshipType(str, Enum):
    UNRECIPROCATED = "unreciprocated"  # You follow them, they do not follow you
    MUTUAL = "mutual"                  # Both follow each other
    FAN = "fan"                        # They follow you, you do not follow them
    NEITHER = "neither"


class DecisionType(str, Enum):
    UNREVIEWED = "unreviewed"
    WHITELIST = "whitelist"                # Keep/safe: celebrity, brand, inspiration, mentor
    UNFOLLOW_CANDIDATE = "unfollow_candidate"  # Flagged to unfollow
    UNFOLLOWED = "unfollowed"              # Already unfollowed
    VIP = "vip"                            # Close friend / high priority


class InstagramAccount(BaseModel):
    username: str
    profile_url: str = ""
    display_name: Optional[str] = None
    followed_at: Optional[str] = None
    relationship: RelationshipType = RelationshipType.UNRECIPROCATED
    decision: DecisionType = DecisionType.UNREVIEWED
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None

    def __init__(self, **data):
        super().__init__(**data)
        if not self.profile_url and self.username:
            self.profile_url = f"https://www.instagram.com/{self.username}"


class SnapshotMeta(BaseModel):
    id: int
    name: str
    created_at: str
    follower_count: int
    following_count: int


class AuditMetrics(BaseModel):
    snapshot_id: Optional[int] = None
    total_following: int = 0
    total_followers: int = 0
    mutual_count: int = 0
    fan_count: int = 0
    unreciprocated_raw_count: int = 0
    whitelisted_count: int = 0
    unfollow_candidates_count: int = 0
    unfollowed_count: int = 0
    vip_count: int = 0
    actionable_unreciprocated_count: int = 0  # Raw unreciprocated minus whitelisted & unfollowed
    reciprocity_rate: float = 0.0             # (mutual / total_following) * 100


class SwipeAction(BaseModel):
    username: str
    decision: DecisionType
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class BatchDecisionRequest(BaseModel):
    usernames: List[str]
    decision: DecisionType
    tags: Optional[List[str]] = None


class DiffResult(BaseModel):
    snapshot_a_id: int
    snapshot_b_id: int
    snapshot_a_name: str
    snapshot_b_name: str
    lost_followers: List[InstagramAccount] = Field(default_factory=list)
    new_followers: List[InstagramAccount] = Field(default_factory=list)
    unfollowed_by_you: List[InstagramAccount] = Field(default_factory=list)
    new_following: List[InstagramAccount] = Field(default_factory=list)

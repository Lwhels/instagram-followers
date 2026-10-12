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
    username: str = Field(..., min_length=1, max_length=60)
    decision: DecisionType
    tags: Optional[List[str]] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=1000)


class BatchDecisionRequest(BaseModel):
    usernames: List[str] = Field(..., min_length=1, max_length=5000)
    decision: DecisionType
    tags: Optional[List[str]] = Field(None, max_length=50)


class DiffResult(BaseModel):
    snapshot_a_id: int
    snapshot_b_id: int
    snapshot_a_name: str
    snapshot_b_name: str
    lost_followers: List[InstagramAccount] = Field(default_factory=list)
    new_followers: List[InstagramAccount] = Field(default_factory=list)
    unfollowed_by_you: List[InstagramAccount] = Field(default_factory=list)
    new_following: List[InstagramAccount] = Field(default_factory=list)


# Authentication & Multi-Tenancy Models
class UserRegisterRequest(BaseModel):
    email: str = Field(
        ...,
        min_length=3,
        max_length=255,
        pattern=r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$",
    )
    password: str = Field(..., min_length=6, max_length=128)
    display_name: Optional[str] = Field(None, max_length=100)


class UserLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class UploadJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadJobResponse(BaseModel):
    job_id: str
    user_id: int
    filename: str
    file_type: str
    status: UploadJobStatus
    stage: str
    total_items: int = 0
    processed_items: int = 0
    progress_percent: float = 0.0
    snapshot_id: Optional[int] = None
    error_message: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


"""Instagram Follower Analyzer & Swipe Deck."""

__version__ = "2.0.0"

from instagram_analyzer.engine import FollowerEngine
from instagram_analyzer.database import Database
from instagram_analyzer.parser import parse_file, parse_zip_archive
from instagram_analyzer.models import RelationshipType, DecisionType

__all__ = [
    "FollowerEngine",
    "Database",
    "parse_file",
    "parse_zip_archive",
    "RelationshipType",
    "DecisionType",
]

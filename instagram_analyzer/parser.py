"""Instagram export parser supporting HTML, JSON, ZIP archives, and raw text formats."""

import io
import json
import os
import re
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from bs4 import BeautifulSoup


class ParsedEntry:
    def __init__(self, username: str, profile_url: str = "", timestamp_str: Optional[str] = None):
        cleaned = _clean_username(username)
        self.username = cleaned
        self.profile_url = f"https://www.instagram.com/{cleaned}" if cleaned else "https://www.instagram.com"
        self.timestamp_str = str(timestamp_str)[:64] if timestamp_str else None

    def __hash__(self):
        return hash(self.username)

    def __eq__(self, other):
        if isinstance(other, ParsedEntry):
            return self.username == other.username
        if isinstance(other, str):
            return self.username == other.lower()
        return False

    def __repr__(self):
        return f"<ParsedEntry username={self.username} time={self.timestamp_str}>"


def _clean_username(raw: str) -> str:
    """Extract and validate clean username from string or URL."""
    if not raw:
        return ""
    raw = raw.strip()
    if "/" in raw:
        match = re.search(r"instagram\.com/(?:_u/)?([a-zA-Z0-9_.]{1,30})", raw)
        if match:
            u = match.group(1).lower().strip(".")
            return u if re.match(r"^[a-zA-Z0-9_.]{1,30}$", u) else ""
    cleaned = raw.lstrip("@").strip().lower().strip(".")
    if re.match(r"^[a-zA-Z0-9_.]{1,30}$", cleaned):
        return cleaned
    return ""


def parse_html_content(html_content: str) -> List[ParsedEntry]:
    """Parse Instagram HTML follower/following export content."""
    soup = BeautifulSoup(html_content, "html.parser")
    entries: List[ParsedEntry] = []
    seen: Set[str] = set()

    for a_tag in soup.find_all("a"):
        text = a_tag.text.strip()
        href = a_tag.get("href", "")
        username = ""

        if href:
            clean = _clean_username(href)
            if clean and clean not in {"about", "legal", "privacy", "help", "developer", "accounts"}:
                username = clean
        if not username and text:
            username = _clean_username(text)

        if not username or username in seen:
            continue

        # Look for timestamp in next sibling or parent sibling container
        timestamp_str = None
        parent_div = a_tag.find_parent("div")
        if parent_div:
            # Check direct sibling or container siblings
            for sibling in parent_div.find_next_siblings("div"):
                s_text = sibling.text.strip()
                if any(m in s_text for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]) or re.search(r"\b\d{4}\b", s_text):
                    timestamp_str = s_text
                    break

        seen.add(username)
        profile_url = href if href and "instagram.com" in href else f"https://www.instagram.com/{username}"
        entries.append(ParsedEntry(username=username, profile_url=profile_url, timestamp_str=timestamp_str))

    return entries


def parse_json_content(json_content: str) -> List[ParsedEntry]:
    """Parse Instagram JSON follower/following export content."""
    data = json.loads(json_content)
    entries: List[ParsedEntry] = []
    seen: Set[str] = set()

    # Normalize top level container
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        if "relationships_following" in data:
            items = data["relationships_following"]
        elif "relationships_followers" in data:
            items = data["relationships_followers"]
        else:
            for val in data.values():
                if isinstance(val, list):
                    items.extend(val)

    for item in items:
        if not isinstance(item, dict):
            continue

        # Pattern 1: string_list_data array
        sld = item.get("string_list_data", [])
        if sld and isinstance(sld, list):
            for sub in sld:
                raw_val = sub.get("value", "") or sub.get("href", "")
                uname = _clean_username(raw_val)
                if uname and uname not in seen:
                    ts = sub.get("timestamp")
                    ts_str = None
                    if ts:
                        try:
                            ts_str = datetime.utcfromtimestamp(int(ts)).strftime("%b %d, %Y %I:%M %p")
                        except Exception:
                            ts_str = str(ts)
                    seen.add(uname)
                    href = sub.get("href", f"https://www.instagram.com/{uname}")
                    entries.append(ParsedEntry(username=uname, profile_url=href, timestamp_str=ts_str))
        else:
            # Pattern 2: direct title or value
            val = item.get("title", "") or item.get("value", "")
            uname = _clean_username(val)
            if uname and uname not in seen:
                seen.add(uname)
                entries.append(ParsedEntry(username=uname))

    return entries


def parse_text_lines(text: str) -> List[ParsedEntry]:
    """Parse plain text list of usernames."""
    entries: List[ParsedEntry] = []
    seen: Set[str] = set()

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        uname = _clean_username(line)
        if uname and uname not in seen:
            seen.add(uname)
            entries.append(ParsedEntry(username=uname))

    return entries


def parse_file(file_path: str) -> List[ParsedEntry]:
    """Auto-detect format and parse file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if ext == ".json":
        return parse_json_content(content)
    elif ext in {".html", ".htm"}:
        return parse_html_content(content)
    else:
        # Try JSON first, then HTML, fallback to text
        try:
            return parse_json_content(content)
        except Exception:
            if "<html" in content.lower() or "<a " in content.lower():
                return parse_html_content(content)
            return parse_text_lines(content)


def parse_zip_archive(zip_bytes_or_path) -> Tuple[List[ParsedEntry], List[ParsedEntry]]:
    """
    Inspect a zip archive from Instagram export.
    Returns (followers, following).
    """
    followers: List[ParsedEntry] = []
    following: List[ParsedEntry] = []

    with zipfile.ZipFile(zip_bytes_or_path, "r") as z:
        namelist = z.namelist()

        follower_files = [
            n for n in namelist
            if re.search(r"^followers?.*?\.(html|json)$", os.path.basename(n), re.I)
        ]
        following_files = [
            n for n in namelist
            if re.search(r"^following.*?\.(html|json)$", os.path.basename(n), re.I)
        ]

        MAX_MEMBER_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
        for fname in follower_files:
            info = z.getinfo(fname)
            if info.file_size > MAX_MEMBER_SIZE_BYTES:
                continue
            content = z.read(fname).decode("utf-8", errors="ignore")
            if fname.lower().endswith(".json"):
                followers.extend(parse_json_content(content))
            else:
                followers.extend(parse_html_content(content))

        for fname in following_files:
            info = z.getinfo(fname)
            if info.file_size > MAX_MEMBER_SIZE_BYTES:
                continue
            content = z.read(fname).decode("utf-8", errors="ignore")
            if fname.lower().endswith(".json"):
                following.extend(parse_json_content(content))
            else:
                following.extend(parse_html_content(content))

    # De-duplicate
    f_dict = {f.username: f for f in followers}
    fg_dict = {f.username: f for f in following}
    return list(f_dict.values()), list(fg_dict.values())

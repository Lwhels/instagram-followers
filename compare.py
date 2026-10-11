#!/usr/bin/env python3
"""
Instagram Follower Analyzer - Fast Comparison Script
Backwards-compatible runner for comparing follower exports.
For full interactive web UI, run: python -m instagram_analyzer serve
"""

import os
import sys
from instagram_analyzer.parser import parse_file

def main():
    followers_file = "followers_kayla.html"
    following_file = "following_kayla.html"

    # Allow custom CLI arguments: python compare.py <followers> <following>
    if len(sys.argv) >= 3:
        followers_file = sys.argv[1]
        following_file = sys.argv[2]
    elif len(sys.argv) == 2 and (sys.argv[1] in ["-h", "--help"]):
        print("Usage: python compare.py [followers.html] [following.html]")
        print("Or run the full UI: python -m instagram_analyzer serve")
        sys.exit(0)

    # Fallbacks if default files do not exist
    if not os.path.exists(followers_file):
        for candidate in ["followers_1.html", "followers.html", "followers_1.json"]:
            if os.path.exists(candidate):
                followers_file = candidate
                break

    if not os.path.exists(following_file):
        for candidate in ["following.html", "following_1.html", "following.json"]:
            if os.path.exists(candidate):
                following_file = candidate
                break

    if not os.path.exists(followers_file) or not os.path.exists(following_file):
        print("Error: Could not locate followers or following export files.")
        print(f"Looked for: {followers_file} and {following_file}")
        print("Place your export files in this directory, or run with arguments:")
        print("  python compare.py <followers_file> <following_file>")
        print("Or explore the interactive demo with: python -m instagram_analyzer demo && python -m instagram_analyzer serve")
        sys.exit(1)

    print(f"Parsing followers from: {followers_file}")
    followers = parse_file(followers_file)
    print(f"Parsing following from: {following_file}")
    following = parse_file(following_file)

    f_set = {f.username for f in followers}
    fg_set = {f.username for f in following}

    not_following_back = sorted(fg_set - f_set)
    fans = sorted(f_set - fg_set)
    mutuals = sorted(f_set & fg_set)

    print("\n" + "=" * 50)
    print("INSTAGRAM RELATIONSHIP BREAKDOWN")
    print("=" * 50)
    print(f"Total Following:    {len(fg_set)}")
    print(f"Total Followers:    {len(f_set)}")
    print(f"Mutuals:            {len(mutuals)}")
    print(f"Fans (Follow You):  {len(fans)}")
    print(f"Unreciprocated:     {len(not_following_back)}")
    reciprocity = (len(mutuals) / len(fg_set) * 100) if fg_set else 0
    print(f"Reciprocity Rate:   {reciprocity:.1f}%")
    print("=" * 50)

    print("\nPeople you follow who don't follow you back:")
    for user in not_following_back:
        print(f"  @{user}")

    print(f"\nTotal not following back: {len(not_following_back)}")
    print("\nTip: Launch the interactive Tinder-style swipe deck with:")
    print("  python -m instagram_analyzer serve")

if __name__ == "__main__":
    main()

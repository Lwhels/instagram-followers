"""Command line interface for Instagram Follower Analyzer."""

import argparse
import os
import sys
import uvicorn
from instagram_analyzer.engine import FollowerEngine
from instagram_analyzer.parser import parse_file
from instagram_analyzer.models import RelationshipType, DecisionType


def print_banner():
    banner = r"""
  ___           _          ___     _ _                             
 |_ _|_ _  ____| |_ __ _  | __|__ | | |_____ __ _____ _ _ ___ _  _ 
  | || ' \(_-<  _| '_/ _` | | _/ _ \| | / _ \ V  V / -_) '_/ _ \ || |
 |___|_||_/__/\__|_| \__,_| |_|\___/|_|_\___/\_/\_/\___|_| \___/\_, |
                                                                |__/ 
    -- Privacy-First Follower Auditor & Interactive Swipe Deck --
    """
    print(banner)


def cmd_compare(args):
    """Direct CLI comparison between followers and following files."""
    print(f"[*] Parsing followers: {args.followers}")
    followers = parse_file(args.followers)
    print(f"[*] Parsing following: {args.following}")
    following = parse_file(args.following)

    f_set = {f.username for f in followers}
    fg_set = {f.username for f in following}

    not_following_back = sorted(fg_set - f_set)
    fans = sorted(f_set - fg_set)
    mutuals = sorted(f_set & fg_set)

    print("\n" + "=" * 50)
    print("ANALYSIS SUMMARY")
    print("=" * 50)
    print(f"Following:          {len(fg_set)}")
    print(f"Followers:          {len(f_set)}")
    print(f"Mutuals:            {len(mutuals)}")
    print(f"Fans (they follow): {len(fans)}")
    print(f"Unreciprocated:     {len(not_following_back)}")
    reciprocity = (len(mutuals) / len(fg_set) * 100) if fg_set else 0
    print(f"Reciprocity Rate:   {reciprocity:.1f}%")

    if args.save_db:
        engine = FollowerEngine(db_path=args.db)
        snap_id = engine.ingest_files(
            snapshot_name=args.name or "CLI Import",
            followers_file=args.followers,
            following_file=args.following,
        )
        print(f"\n[+] Saved snapshot to database: snapshot #{snap_id} in {args.db}")

    print("\nPeople you follow who don't follow you back:")
    for u in not_following_back[: args.limit]:
        print(f"  - @{u} (https://www.instagram.com/{u})")
    if len(not_following_back) > args.limit:
        print(f"  ... and {len(not_following_back) - args.limit} more.")


def cmd_demo(args):
    """Seed demo data into the database."""
    engine = FollowerEngine(db_path=args.db)
    snap_id = engine.load_sample_demo(snapshot_name="Interactive Demo Snapshot")
    metrics = engine.recompute(snapshot_id=snap_id)
    print(f"[+] Loaded rich demo dataset into {args.db} (Snapshot ID: {snap_id})")
    print(f"    - Following:      {metrics.total_following}")
    print(f"    - Followers:      {metrics.total_followers}")
    print(f"    - Mutuals:        {metrics.mutual_count}")
    print(f"    - Unreciprocated: {metrics.unreciprocated_raw_count}")
    print(f"    - Reciprocity:    {metrics.reciprocity_rate}%\n")
    print("[*] Run 'python -m instagram_analyzer serve' to explore in the interactive Swipe UI!")


def cmd_serve(args):
    """Start web server."""
    port = int(os.getenv("PORT", args.port))
    host = os.getenv("HOST", args.host)
    print_banner()
    print(f"[*] Starting Instagram Follower Analyzer on http://{host}:{port}")
    print("[*] Press Ctrl+C to stop.")
    uvicorn.run("instagram_analyzer.api:app", host=host, port=port, reload=args.reload)


def main():
    parser = argparse.ArgumentParser(description="Instagram Follower Analyzer & Swipe Deck")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Compare
    p_comp = subparsers.add_parser("compare", help="Compare followers and following files")
    p_comp.add_argument("followers", help="Path to followers file (html/json)")
    p_comp.add_argument("following", help="Path to following file (html/json)")
    p_comp.add_argument("--save-db", action="store_true", help="Save results into local SQLite vault")
    p_comp.add_argument("--name", default="CLI Import", help="Snapshot name")
    p_comp.add_argument("--db", default="follower_vault.db", help="Path to SQLite database")
    p_comp.add_argument("--limit", type=int, default=30, help="Max accounts to print")

    # Demo
    p_demo = subparsers.add_parser("demo", help="Load rich sample demo data into database")
    p_demo.add_argument("--db", default="follower_vault.db", help="Path to SQLite database")

    # Serve
    p_serve = subparsers.add_parser("serve", help="Launch interactive web & desktop UI")
    p_serve.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"), help="Host to bind (default: 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")), help="Port to bind")
    p_serve.add_argument("--reload", action="store_true", help="Auto reload")
    p_serve.add_argument("--db", default="follower_vault.db", help="Path to SQLite database")

    args = parser.parse_args()

    if args.command == "compare":
        cmd_compare(args)
    elif args.command == "demo":
        cmd_demo(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        # Default behavior: if compare.py style arguments or no args, show help
        print_banner()
        parser.print_help()


if __name__ == "__main__":
    main()

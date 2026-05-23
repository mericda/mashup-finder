#!/usr/bin/env python3
"""
Mashup Finder
Usage: python3 app.py [--port 8080] [--no-open] [--db PATH]
"""
import argparse

from db import DEFAULT_DB_PATH
from importer import run_sync
from server import MashupServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--db", default=DEFAULT_DB_PATH)
    args = parser.parse_args()

    print("Syncing Djay Pro library...", flush=True)
    result = run_sync(args.db)
    if result["added"] or result["updated"] or result["removed"]:
        print(f"  +{result['added']} added, {result['updated']} updated, "
              f"{result['removed']} removed", flush=True)
    else:
        print("  Library up to date.", flush=True)

    print(f"\n  Mashup Finder running at http://127.0.0.1:{args.port}\n", flush=True)
    server = MashupServer(db_path=args.db, port=args.port, auto_open=not args.no_open)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()

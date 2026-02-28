#!/usr/bin/env python3
"""
Djay Pro Mashup Compatibility Finder

Reads Djay Pro's track analysis data (BPM, musical key) and finds
mashup-compatible track pairs using Camelot wheel harmonic mixing rules.
"""

import argparse
import csv
import glob
import os
import plistlib
import sys
from collections import defaultdict

# --- Camelot Wheel Mapping ---
# keyIndex 0-11: Major keys (C, C#, D, ..., B) -> Camelot B side
# keyIndex 12-23: Minor keys (C, C#, D, ..., B) -> Camelot A side

# keyIndex mapping: pairs of (major, relative minor) in chromatic order
# Even indices = major (B), odd indices = minor (A)
KEYINDEX_TO_CAMELOT = [
    "8B",  "8A",   # 0,1:  C maj / A min
    "3B",  "3A",   # 2,3:  Db maj / Bb min
    "10B", "10A",  # 4,5:  D maj / B min
    "5B",  "5A",   # 6,7:  Eb maj / C min
    "12B", "12A",  # 8,9:  E maj / C# min
    "7B",  "7A",   # 10,11: F maj / D min
    "2B",  "2A",   # 12,13: Gb maj / Eb min
    "9B",  "9A",   # 14,15: G maj / E min
    "4B",  "4A",   # 16,17: Ab maj / F min
    "11B", "11A",  # 18,19: A maj / F# min
    "6B",  "6A",   # 20,21: Bb maj / G min
    "1B",  "1A",   # 22,23: B maj / Ab min
]
KEYINDEX_TO_NAME = [
    "C maj",  "A min",   "Db maj", "Bb min",  "D maj",  "B min",
    "Eb maj", "C min",   "E maj",  "C# min",  "F maj",  "D min",
    "Gb maj", "Eb min",  "G maj",  "E min",   "Ab maj", "F min",
    "A maj",  "F# min",  "Bb maj", "G min",   "B maj",  "Ab min",
]

METADATA_DIR = os.path.expanduser(
    "~/Library/Group Containers/VJXTL73S8G.com.algoriddim.userdata/"
    "Library/Application Support/Algoriddim/Metadata"
)


def key_index_to_camelot(key_index):
    """Convert Djay Pro keyIndex (0-23) to Camelot notation (e.g. '8B', '5A')."""
    if key_index < 0 or key_index > 23:
        return None
    return KEYINDEX_TO_CAMELOT[key_index]


def key_index_to_name(key_index):
    """Convert keyIndex to human-readable key name."""
    if key_index < 0 or key_index > 23:
        return "Unknown"
    return KEYINDEX_TO_NAME[key_index]


def parse_camelot(camelot_str):
    """Parse '8B' -> (8, 'B')."""
    letter = camelot_str[-1]
    number = int(camelot_str[:-1])
    return number, letter


def are_keys_compatible(camelot1, camelot2):
    """
    Check if two Camelot keys are harmonically compatible.
    Returns (is_compatible, match_type).

    Rules:
    - Same key: perfect match
    - ±1 on the wheel (same letter): adjacent match
    - Same number, different letter: relative major/minor
    """
    if camelot1 is None or camelot2 is None:
        return False, None

    num1, let1 = parse_camelot(camelot1)
    num2, let2 = parse_camelot(camelot2)

    if num1 == num2 and let1 == let2:
        return True, "same_key"

    if let1 == let2:
        diff = abs(num1 - num2)
        if diff == 1 or diff == 11:  # 11 wraps around (12->1)
            return True, "adjacent"

    if num1 == num2 and let1 != let2:
        return True, "relative"

    return False, None


def bpm_compatible(bpm1, bpm2, bpm_range):
    """
    Check if two BPMs are compatible, considering half/double time.
    Returns (is_compatible, effective_bpm2, match_type).
    """
    diff = abs(bpm1 - bpm2)
    if diff <= bpm_range:
        return True, bpm2, "direct"

    # Half-time match (e.g., 130 vs 65)
    if abs(bpm1 - bpm2 * 2) <= bpm_range:
        return True, bpm2 * 2, "double"
    if abs(bpm1 * 2 - bpm2) <= bpm_range:
        return True, bpm2, "half"

    return False, bpm2, None


def load_tracks():
    """Load all track metadata from Djay Pro."""
    pattern = os.path.join(METADATA_DIR, "**", "*.djayMetadata")
    files = glob.glob(pattern, recursive=True)

    tracks = []
    errors = 0
    for fp in files:
        try:
            with open(fp, "rb") as f:
                d = plistlib.load(f)

            info = d.get("info", {})
            key_info = d.get("keyInfo", {})
            beat_info = d.get("deepBeatTrackerInfo", {})

            name = info.get("Name", "")
            artist = info.get("Artist", "")
            if not name:
                continue

            bpm = beat_info.get("bpm", 0)
            key_index = key_info.get("keyIndex", -1)
            camelot = key_index_to_camelot(key_index)

            if bpm <= 0 or camelot is None:
                continue

            tracks.append({
                "name": name,
                "artist": artist,
                "bpm": round(bpm, 1),
                "key_index": key_index,
                "camelot": camelot,
                "key_name": key_index_to_name(key_index),
                "bpm_confidence": beat_info.get("bpmConfidence", 0),
                "key_confidence": key_info.get("keyConfidence", 0),
                "duration": info.get("Duration", 0),
            })
        except Exception:
            errors += 1

    return tracks, errors


def find_mashup_pairs(tracks, bpm_range=6):
    """Find all mashup-compatible pairs."""
    # Group tracks by Camelot key and compatible keys for faster lookup
    key_groups = defaultdict(list)
    for i, t in enumerate(tracks):
        key_groups[t["camelot"]].append(i)

    pairs = []
    seen = set()

    for i, track_a in enumerate(tracks):
        cam_a = track_a["camelot"]
        num_a, let_a = parse_camelot(cam_a)

        # Find all compatible Camelot keys
        compatible_keys = set()
        compatible_keys.add(cam_a)  # same key

        # Adjacent keys (±1, same letter)
        prev_num = 12 if num_a == 1 else num_a - 1
        next_num = 1 if num_a == 12 else num_a + 1
        compatible_keys.add(f"{prev_num}{let_a}")
        compatible_keys.add(f"{next_num}{let_a}")

        # Relative major/minor (same number, different letter)
        other_let = "A" if let_a == "B" else "B"
        compatible_keys.add(f"{num_a}{other_let}")

        # Check all tracks in compatible key groups
        for compat_key in compatible_keys:
            for j in key_groups.get(compat_key, []):
                if j <= i:
                    continue
                pair_key = (i, j)
                if pair_key in seen:
                    continue

                track_b = tracks[j]

                # Same artist/track skip
                if (track_a["name"] == track_b["name"]
                        and track_a["artist"] == track_b["artist"]):
                    continue

                bpm_ok, effective_bpm, bpm_match = bpm_compatible(
                    track_a["bpm"], track_b["bpm"], bpm_range
                )
                if not bpm_ok:
                    continue

                _, key_match = are_keys_compatible(cam_a, track_b["camelot"])

                # Score: prefer close BPM + high confidence + same key
                bpm_diff = abs(track_a["bpm"] - effective_bpm)
                bpm_score = max(0, 1 - bpm_diff / bpm_range)
                key_score = {"same_key": 1.0, "relative": 0.7, "adjacent": 0.5}.get(key_match, 0)
                confidence = (track_a["key_confidence"] + track_b["key_confidence"]) / 2
                score = (bpm_score * 0.4 + key_score * 0.4 + confidence * 0.2)

                seen.add(pair_key)
                pairs.append({
                    "track_a": track_a,
                    "track_b": track_b,
                    "bpm_diff": round(bpm_diff, 1),
                    "bpm_match": bpm_match,
                    "key_match": key_match,
                    "score": round(score, 3),
                })

    pairs.sort(key=lambda p: p["score"], reverse=True)
    return pairs


def filter_pairs(pairs, search=None, track_name=None):
    """Filter pairs by artist search or track name."""
    if search:
        search_lower = search.lower()
        pairs = [
            p for p in pairs
            if search_lower in p["track_a"]["artist"].lower()
            or search_lower in p["track_b"]["artist"].lower()
            or search_lower in p["track_a"]["name"].lower()
            or search_lower in p["track_b"]["name"].lower()
        ]
    if track_name:
        track_lower = track_name.lower()
        pairs = [
            p for p in pairs
            if track_lower in p["track_a"]["name"].lower()
            or track_lower in p["track_b"]["name"].lower()
        ]
    return pairs


def format_duration(seconds):
    """Format seconds as M:SS."""
    if not seconds:
        return "?"
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m}:{s:02d}"


def print_pairs(pairs, top_n=30):
    """Print pairs as a formatted table."""
    if not pairs:
        print("No compatible pairs found.")
        return

    print(f"\n{'#':>3}  {'Score':>5}  {'Track A':<40} {'BPM':>6} {'Key':>4}  "
          f"{'<>':^4}  {'Track B':<40} {'BPM':>6} {'Key':>4}  {'Match':>10}")
    print("-" * 170)

    for idx, p in enumerate(pairs[:top_n], 1):
        a = p["track_a"]
        b = p["track_b"]
        label_a = f"{a['artist'][:18]} - {a['name'][:18]}"
        label_b = f"{b['artist'][:18]} - {b['name'][:18]}"
        bpm_info = f"{p['bpm_diff']:+.0f}" if p["bpm_match"] == "direct" else f"{p['bpm_match']}"
        key_info = {"same_key": "SAME", "adjacent": "ADJ", "relative": "REL"}.get(p["key_match"], "?")

        print(f"{idx:>3}  {p['score']:>5.2f}  {label_a:<40} {a['bpm']:>6.1f} {a['camelot']:>4}  "
              f"{'<->':^4}  {label_b:<40} {b['bpm']:>6.1f} {b['camelot']:>4}  "
              f"{key_info:>4} {bpm_info:>5}")


def export_csv(pairs, filename="mashup-pairs.csv"):
    """Export pairs to CSV."""
    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Score", "Artist A", "Track A", "BPM A", "Key A", "Camelot A",
            "Artist B", "Track B", "BPM B", "Key B", "Camelot B",
            "BPM Diff", "BPM Match", "Key Match"
        ])
        for p in pairs:
            a, b = p["track_a"], p["track_b"]
            writer.writerow([
                p["score"], a["artist"], a["name"], a["bpm"], a["key_name"], a["camelot"],
                b["artist"], b["name"], b["bpm"], b["key_name"], b["camelot"],
                p["bpm_diff"], p["bpm_match"], p["key_match"]
            ])
    return filename


def main():
    parser = argparse.ArgumentParser(
        description="Find mashup-compatible track pairs from your Djay Pro library"
    )
    parser.add_argument("--bpm-range", type=float, default=6,
                        help="BPM tolerance for matching (default: 6)")
    parser.add_argument("--search", type=str, default=None,
                        help="Filter by artist or track name")
    parser.add_argument("--track", type=str, default=None,
                        help="Find pairs for a specific track name")
    parser.add_argument("--top", type=int, default=30,
                        help="Number of top pairs to display (default: 30)")
    parser.add_argument("--csv", type=str, default=None,
                        help="Export all pairs to CSV (default: mashup-pairs.csv)")
    parser.add_argument("--list-keys", action="store_true",
                        help="Show track count by Camelot key")
    args = parser.parse_args()

    print("Loading Djay Pro library...")
    tracks, errors = load_tracks()
    print(f"Loaded {len(tracks)} tracks with BPM + key data", end="")
    if errors:
        print(f" ({errors} files skipped)")
    else:
        print()

    if not tracks:
        print("No tracks found. Is Djay Pro installed?")
        sys.exit(1)

    if args.list_keys:
        print(f"\n{'Camelot':>8} {'Key':>15} {'Count':>6}")
        print("-" * 32)
        counts = defaultdict(int)
        for t in tracks:
            counts[t["camelot"]] += 1
        for ki in range(24):
            cam = key_index_to_camelot(ki)
            name = key_index_to_name(ki)
            print(f"{cam:>8} {name:>15} {counts.get(cam, 0):>6}")
        print(f"\n{'Total':>24} {len(tracks):>6}")
        return

    print(f"Finding mashup-compatible pairs (BPM range: ±{args.bpm_range})...")
    pairs = find_mashup_pairs(tracks, bpm_range=args.bpm_range)
    print(f"Found {len(pairs)} compatible pairs")

    pairs = filter_pairs(pairs, search=args.search, track_name=args.track)
    if args.search or args.track:
        print(f"After filtering: {len(pairs)} pairs")

    print_pairs(pairs, top_n=args.top)

    csv_file = args.csv if args.csv else "mashup-pairs.csv"
    if pairs:
        export_csv(pairs, csv_file)
        print(f"\nAll {len(pairs)} pairs exported to {csv_file}")


if __name__ == "__main__":
    main()

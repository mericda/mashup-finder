import glob
import json
import os
import plistlib
import struct
import zlib
from statistics import stdev

from db import init_db, DEFAULT_DB_PATH
from matching import key_index_to_camelot, key_index_to_name, build_key_groups, precompute_top_pairs

METADATA_DIR = os.path.expanduser(
    "~/Library/Group Containers/VJXTL73S8G.com.algoriddim.userdata/"
    "Library/Application Support/Algoriddim/Metadata"
)

SOURCE_MAP = {1: "local", 3: "tidal", 4: "soundcloud", 7: "apple_music"}


def _decode_float32_blob(blob):
    if not blob:
        return []
    try:
        data = zlib.decompress(blob)
        n = len(data) // 4
        return list(struct.unpack(f">{n}f", data[:n * 4]))
    except Exception:
        return []


def _compute_bpm_stability(beat_times):
    if len(beat_times) < 3:
        return 0.0
    intervals = [beat_times[i + 1] - beat_times[i] for i in range(len(beat_times) - 1)]
    return round(stdev(intervals), 6)


def _parse_bpm_segments(change_times_blob, bpms_blob):
    times = _decode_float32_blob(change_times_blob)
    bpms = _decode_float32_blob(bpms_blob)
    return [{"time": round(float(t), 3), "bpm": round(float(b), 2)}
            for t, b in zip(times, bpms)]


def parse_plist_file(path):
    """Parse a .djayMetadata file into a DB-ready dict. Returns None on failure."""
    try:
        with open(path, "rb") as f:
            d = plistlib.load(f)
    except Exception:
        return None

    info = d.get("info", {})
    ki = d.get("keyInfo", {})
    bi = d.get("deepBeatTrackerInfo", {})
    gi = d.get("newGainInfo", {})
    wave = d.get("waveInfoCompact", {})
    colors = d.get("waveColorsInfo", {})

    name = info.get("Name", "")
    if not name:
        return None

    key_index = ki.get("keyIndex", -1)
    camelot = key_index_to_camelot(key_index)
    bpm = bi.get("bpm", 0)
    if bpm <= 0 or camelot is None:
        return None

    beats_blob = bi.get("compressedBeats")
    beat_times = _decode_float32_blob(beats_blob)
    bpm_segments = _parse_bpm_segments(
        bi.get("compressedBPMChangeTimes"), bi.get("compressedPrevalentBPMs")
    )

    return {
        "name": name,
        "artist": info.get("Artist", ""),
        "duration": int(info.get("Duration", 0)),
        "source": SOURCE_MAP.get(info.get("source"), "local"),
        "persistent_id": info.get("persistentID", ""),
        "quality": info.get("quality", 0),
        "camelot": camelot,
        "key_name": key_index_to_name(key_index),
        "key_conf": round(ki.get("keyConfidence", 0), 4),
        "second_key": key_index_to_camelot(ki.get("secondKeyIndex", -1)),
        "tuning": round(ki.get("keyReferenceTuning", 440), 2),
        "bpm": round(bpm, 1),
        "analyzed_bpm": round(bi.get("analyzedBPM", bpm), 1),
        "bpm_conf": round(bi.get("bpmConfidence", 0), 4),
        "straight": int(bi.get("straightGrid", False)),
        "forced_straight": int(bi.get("forcedStraightGrid", False)),
        "grid_dev": round(bi.get("straightGridDistance", 0), 4),
        "first_downbeat": bi.get("firstDownBeatIndex", 0),
        "time_signature": bi.get("timeSignatureIndex", 4),
        "beat_count": len(beat_times),
        "bpm_stability": _compute_bpm_stability(beat_times),
        "bpm_segment_count": len(bpm_segments),
        "bpm_segments": json.dumps(bpm_segments),
        "energy": round(gi.get("AutoTitleGain", -11), 2),
        "dyn_range": round(gi.get("AutoTitleGainLoudnessRange", 6), 2),
        "transient_count": len(_decode_float32_blob(bi.get("compressedTransientPositions"))),
        "waveform_low": wave.get("compressedLowRateWaveSamples"),
        "waveform_max": wave.get("compressedLowRateWaveSamplesMax"),
        "waveform_colors": colors.get("compressedNormalRateWaveSamplesColors"),
        "beats_blob": beats_blob,
        "transient_pos": bi.get("compressedTransientPositions"),
        "transient_energy": bi.get("compressedTransientEnergies"),
        "file_path": path,
        "file_mtime": os.path.getmtime(path),
    }


TRACK_COLS = [
    "name", "artist", "duration", "source", "persistent_id", "quality",
    "camelot", "key_name", "key_conf", "second_key", "tuning", "bpm",
    "analyzed_bpm", "bpm_conf", "straight", "forced_straight", "grid_dev",
    "first_downbeat", "time_signature", "beat_count", "bpm_stability",
    "bpm_segment_count", "bpm_segments", "energy", "dyn_range",
    "transient_count", "waveform_low", "waveform_max", "waveform_colors",
    "beats_blob", "transient_pos", "transient_energy", "file_mtime",
]

_UPSERT_SQL = (
    f"INSERT INTO tracks (file_path, {', '.join(TRACK_COLS)}) "
    f"VALUES (?, {', '.join('?' for _ in TRACK_COLS)}) "
    f"ON CONFLICT(file_path) DO UPDATE SET "
    f"{', '.join(f'{c}=excluded.{c}' for c in TRACK_COLS)}"
)


def _upsert_track(conn, track):
    conn.execute(_UPSERT_SQL, [track["file_path"]] + [track.get(c) for c in TRACK_COLS])


def _recompute_top_pairs(conn):
    rows = conn.execute(
        "SELECT id, name, artist, bpm, camelot, key_conf, energy, dyn_range, "
        "straight, grid_dev, tuning, second_key, bpm_stability, bpm_segment_count "
        "FROM tracks"
    ).fetchall()
    tracks = [dict(r) for r in rows]
    key_groups = build_key_groups(tracks)
    top = precompute_top_pairs(tracks, key_groups, top_n=500)

    with conn:  # atomic: if anything fails, delete is rolled back
        conn.execute("DELETE FROM top_pairs")
        for p in top:
            conn.execute("""
                INSERT INTO top_pairs
                (track_a_id, track_b_id, score, bpm_diff, bpm_match, key_match,
                 energy_diff, grid_match, tuning_diff, dr_diff, warnings,
                 bpm_score, key_score, energy_score, grid_score, dr_score,
                 tuning_score, conf_score, second_key_match)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [
                p["track_a"]["id"], p["track_b"]["id"],
                p["score"], p["bpm_diff"], p["bpm_match"], p["key_match"],
                p["energy_diff"], int(p["grid_match"]), p["tuning_diff"], p["dr_diff"],
                json.dumps(p["warnings"]),
                p["bpm_score"], p["key_score"], p["energy_score"], p["grid_score"],
                p["dr_score"], p["tuning_score"], p["conf_score"], int(p["second_key_match"]),
            ])


def run_sync(db_path=DEFAULT_DB_PATH, metadata_dir=METADATA_DIR):
    """Sync Djay Pro metadata -> SQLite. Returns {added, updated, removed, skipped}."""
    conn = init_db(db_path)

    existing = {
        r["file_path"]: (r["id"], r["file_mtime"])
        for r in conn.execute("SELECT id, file_path, file_mtime FROM tracks")
    }

    on_disk = set(glob.glob(os.path.join(metadata_dir, "**", "*.djayMetadata"), recursive=True))
    added = updated = removed = skipped = 0

    for path in on_disk:
        mtime = os.path.getmtime(path)
        if path in existing:
            if abs(mtime - existing[path][1]) < 0.01:
                continue
            track = parse_plist_file(path)
            if track:
                _upsert_track(conn, track)
                updated += 1
            else:
                skipped += 1
        else:
            track = parse_plist_file(path)
            if track:
                _upsert_track(conn, track)
                added += 1
            else:
                skipped += 1

    for path, (track_id, _) in existing.items():
        if path not in on_disk:
            conn.execute("DELETE FROM tracks WHERE id=?", [track_id])
            removed += 1

    conn.commit()

    if added or updated or removed:
        _recompute_top_pairs(conn)

    conn.close()
    return {"added": added, "updated": updated, "removed": removed, "skipped": skipped}

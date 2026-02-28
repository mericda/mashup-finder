#!/usr/bin/env python3
"""
Djay Pro Mashup Finder — Web App

A slick dark-themed web UI for finding mashup-compatible track pairs
from your Djay Pro library. Zero dependencies beyond Python stdlib.

Usage: python3 djay-mashup-app.py [--port 8080]
"""

import glob
import json
import os
import plistlib
import sys
import webbrowser
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ---------- Djay Pro metadata parsing ----------

# keyIndex mapping: pairs of (major, relative minor) in chromatic order
# Even indices = major (B), odd indices = minor (A)
# 0=C maj, 1=A min, 2=Db maj, 3=Bb min, 4=D maj, 5=B min, ...
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

# Camelot colors for the wheel — each number gets a hue
CAMELOT_COLORS = {
    1: "#FF6B6B", 2: "#FF8E53", 3: "#FFC853", 4: "#E8FF53",
    5: "#88FF53", 6: "#53FFB2", 7: "#53FFF5", 8: "#53C8FF",
    9: "#5388FF", 10: "#8853FF", 11: "#C853FF", 12: "#FF53E8",
}


def key_index_to_camelot(key_index):
    if key_index < 0 or key_index > 23:
        return None
    return KEYINDEX_TO_CAMELOT[key_index]


def key_index_to_name(key_index):
    if key_index < 0 or key_index > 23:
        return "Unknown"
    return KEYINDEX_TO_NAME[key_index]


def parse_camelot(s):
    return int(s[:-1]), s[-1]


def get_compatible_keys(camelot):
    num, let = parse_camelot(camelot)
    keys = {camelot}
    prev_n = 12 if num == 1 else num - 1
    next_n = 1 if num == 12 else num + 1
    keys.add(f"{prev_n}{let}")
    keys.add(f"{next_n}{let}")
    other = "A" if let == "B" else "B"
    keys.add(f"{num}{other}")
    return keys


def key_match_type(cam1, cam2):
    if cam1 == cam2:
        return "same"
    n1, l1 = parse_camelot(cam1)
    n2, l2 = parse_camelot(cam2)
    if n1 == n2 and l1 != l2:
        return "relative"
    if l1 == l2:
        diff = abs(n1 - n2)
        if diff == 1 or diff == 11:
            return "adjacent"
    return None


def load_tracks():
    pattern = os.path.join(METADATA_DIR, "**", "*.djayMetadata")
    files = glob.glob(pattern, recursive=True)
    tracks = []
    for idx, fp in enumerate(files):
        try:
            with open(fp, "rb") as f:
                d = plistlib.load(f)
            info = d.get("info", {})
            ki = d.get("keyInfo", {})
            bi = d.get("deepBeatTrackerInfo", {})
            name = info.get("Name", "")
            if not name:
                continue
            bpm = bi.get("bpm", 0)
            key_index = ki.get("keyIndex", -1)
            camelot = key_index_to_camelot(key_index)
            if bpm <= 0 or camelot is None:
                continue
            gi = d.get("newGainInfo", {})
            second_ki = ki.get("secondKeyIndex", -1)
            second_cam = key_index_to_camelot(second_ki)
            tracks.append({
                "id": len(tracks),
                "name": name,
                "artist": info.get("Artist", ""),
                "bpm": round(bpm, 1),
                "camelot": camelot,
                "key_name": key_index_to_name(key_index),
                "key_conf": round(ki.get("keyConfidence", 0), 2),
                "bpm_conf": round(bi.get("bpmConfidence", 0), 2),
                "duration": int(info.get("Duration", 0)),
                "energy": round(gi.get("AutoTitleGain", -11), 1),
                "dyn_range": round(gi.get("AutoTitleGainLoudnessRange", 6), 1),
                "straight": bi.get("straightGrid", False),
                "grid_dev": round(bi.get("straightGridDistance", 0.1), 4),
                "tuning": round(ki.get("keyReferenceTuning", 440), 1),
                "second_key": second_cam,
            })
        except Exception:
            pass
    return tracks


# ---------- Pair finding ----------

def find_pairs_for_track(track_id, tracks, key_groups, bpm_range=6, limit=200):
    t = tracks[track_id]
    compat_keys = get_compatible_keys(t["camelot"])
    pairs = []
    for ck in compat_keys:
        for j in key_groups.get(ck, []):
            if j == track_id:
                continue
            other = tracks[j]
            if t["name"] == other["name"] and t["artist"] == other["artist"]:
                continue
            # BPM check
            diff = abs(t["bpm"] - other["bpm"])
            bpm_match = "direct"
            eff_diff = diff
            if diff > bpm_range:
                d2 = abs(t["bpm"] - other["bpm"] * 2)
                d3 = abs(t["bpm"] * 2 - other["bpm"])
                if d2 <= bpm_range:
                    eff_diff = d2
                    bpm_match = "double"
                elif d3 <= bpm_range:
                    eff_diff = d3
                    bpm_match = "half"
                else:
                    continue
            km = key_match_type(t["camelot"], other["camelot"])
            bpm_score = max(0, 1 - eff_diff / bpm_range)
            key_score = {"same": 1.0, "relative": 0.7, "adjacent": 0.5}.get(km, 0)
            conf = (t["key_conf"] + other["key_conf"]) / 2

            # Energy similarity (AutoTitleGain) — penalize >6dB difference
            energy_diff = abs(t["energy"] - other["energy"])
            energy_score = max(0, 1 - energy_diff / 12)

            # Grid compatibility — bonus if both straight
            both_straight = t["straight"] and other["straight"]
            grid_score = 1.0 if both_straight else (0.5 if t["straight"] == other["straight"] else 0.3)

            # Dynamic range similarity
            dr_diff = abs(t["dyn_range"] - other["dyn_range"])
            dr_score = max(0, 1 - dr_diff / 10)

            # Tuning mismatch
            tuning_diff = abs(t["tuning"] - other["tuning"])
            tuning_ok = tuning_diff <= 3.0
            tuning_score = 1.0 if tuning_diff <= 1.0 else (0.7 if tuning_ok else 0.3)

            # Secondary key bonus
            second_key_bonus = 0
            if t.get("second_key") and other.get("second_key"):
                if t["second_key"] == other["second_key"]:
                    second_key_bonus = 0.05

            # Weighted score: BPM 25%, Key 30%, Energy 15%, Grid 10%, DR 5%, Tuning 10%, Confidence 5%
            score = round(
                bpm_score * 0.25
                + key_score * 0.30
                + energy_score * 0.15
                + grid_score * 0.10
                + dr_score * 0.05
                + tuning_score * 0.10
                + conf * 0.05
                + second_key_bonus,
                3,
            )

            # Build warnings list
            warnings = []
            if not tuning_ok:
                warnings.append("tuning")
            if energy_diff > 8:
                warnings.append("energy")
            if t["straight"] != other["straight"]:
                warnings.append("grid")

            pairs.append({
                "track": other,
                "score": score,
                "bpm_diff": round(eff_diff, 1),
                "bpm_match": bpm_match,
                "key_match": km,
                "energy_diff": round(energy_diff, 1),
                "grid_match": both_straight,
                "tuning_diff": round(tuning_diff, 1),
                "dr_diff": round(dr_diff, 1),
                "warnings": warnings,
            })
    pairs.sort(key=lambda p: p["score"], reverse=True)
    return pairs[:limit]


def search_pairs(query, tracks, key_groups, bpm_range=6, key_filter=None, limit=100):
    q = query.lower()
    matching = [
        t for t in tracks
        if q in t["name"].lower() or q in t["artist"].lower()
    ]
    if key_filter:
        matching = [t for t in matching if t["camelot"] == key_filter]
    all_pairs = []
    seen = set()
    for t in matching[:50]:
        pairs = find_pairs_for_track(t["id"], tracks, key_groups, bpm_range, 50)
        for p in pairs:
            pair_key = tuple(sorted([t["id"], p["track"]["id"]]))
            if pair_key in seen:
                continue
            seen.add(pair_key)
            all_pairs.append({
                "track_a": t,
                "track_b": p["track"],
                "score": p["score"],
                "bpm_diff": p["bpm_diff"],
                "bpm_match": p["bpm_match"],
                "key_match": p["key_match"],
            })
    all_pairs.sort(key=lambda p: p["score"], reverse=True)
    return all_pairs[:limit]


# ---------- HTML / CSS / JS Frontend ----------

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mashup Finder</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #0a0a0f;
  --surface: #12121a;
  --surface2: #1a1a28;
  --surface3: #222236;
  --border: #2a2a40;
  --text: #e8e8f0;
  --text2: #8888a8;
  --accent: #7c5cfc;
  --accent2: #00d4aa;
  --pink: #ff6b9d;
  --orange: #ff8e53;
  --cyan: #00d4ff;
  --radius: 12px;
  --glow: 0 0 20px rgba(124, 92, 252, 0.15);
  --row-h: 54px;
  --pair-h: 82px;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  overflow-x: hidden;
}

/* --- Header --- */
.header {
  padding: 20px 32px;
  display: flex;
  align-items: center;
  gap: 16px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(124,92,252,0.06) 0%, transparent 100%);
}
.header h1 {
  font-size: 22px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--accent), var(--cyan));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  letter-spacing: -0.5px;
}
.header .badge {
  background: var(--surface2);
  border: 1px solid var(--border);
  padding: 4px 12px;
  border-radius: 20px;
  font-size: 12px;
  color: var(--text2);
}
.header .badge span { color: var(--accent2); font-weight: 600; }

/* --- Search --- */
.search-area {
  padding: 20px 32px;
  display: flex;
  gap: 12px;
  align-items: center;
}
.search-box {
  flex: 1;
  position: relative;
}
.search-box input {
  width: 100%;
  padding: 14px 20px 14px 48px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 15px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.search-box input:focus {
  border-color: var(--accent);
  box-shadow: var(--glow);
}
.search-box input::placeholder { color: var(--text2); }
.search-box .icon {
  position: absolute;
  left: 16px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text2);
  font-size: 18px;
}

/* --- Filters --- */
.filters {
  padding: 0 32px 16px;
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
}
.filter-group {
  display: flex;
  align-items: center;
  gap: 8px;
}
.filter-label {
  font-size: 12px;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: 600;
}
.bpm-slider {
  -webkit-appearance: none;
  width: 120px;
  height: 4px;
  border-radius: 2px;
  background: var(--surface3);
  outline: none;
}
.bpm-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  box-shadow: 0 0 8px rgba(124,92,252,0.4);
}
.bpm-val {
  font-size: 14px;
  color: var(--accent);
  font-weight: 600;
  min-width: 32px;
}
.match-toggles {
  display: flex;
  gap: 4px;
}
.match-btn, .sort-btn {
  padding: 5px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text2);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}
.match-btn.active {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(124,92,252,0.1);
}
.sort-btn.active {
  border-color: var(--accent2);
  color: var(--accent2);
  background: rgba(0,212,170,0.1);
}
.match-btn:hover, .sort-btn:hover { border-color: var(--text2); }

/* --- Main layout --- */
.main {
  display: flex;
  gap: 0;
  height: calc(100vh - 160px);
  padding: 0 32px 20px;
}
.panel {
  flex: 1;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.panel-left { margin-right: 10px; }
.panel-right { margin-left: 10px; }
.panel-header {
  padding: 12px 18px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--surface2);
  flex-shrink: 0;
  gap: 8px;
}
.panel-header .count {
  background: var(--surface3);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 11px;
}
.sort-group {
  display: flex;
  gap: 4px;
  margin-left: auto;
}
.panel-body {
  overflow-y: auto;
  flex: 1;
  position: relative;
  scrollbar-width: thin;
  scrollbar-color: var(--surface3) transparent;
}
.panel-body::-webkit-scrollbar { width: 6px; }
.panel-body::-webkit-scrollbar-track { background: transparent; }
.panel-body::-webkit-scrollbar-thumb { background: var(--surface3); border-radius: 3px; }

/* --- Virtual list --- */
.vlist-spacer { width: 100%; }
.vlist-viewport { position: relative; width: 100%; }

/* --- Track list --- */
.track-item {
  height: var(--row-h);
  padding: 0 18px;
  border-bottom: 1px solid rgba(42,42,64,0.5);
  cursor: pointer;
  transition: background 0.15s;
  display: flex;
  align-items: center;
  gap: 14px;
  position: absolute;
  left: 0;
  right: 0;
}
.track-item:hover { background: var(--surface2); }
.track-item.selected { background: rgba(124,92,252,0.1); border-left: 3px solid var(--accent); }
.track-info { flex: 1; min-width: 0; }
.track-name {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.track-artist {
  font-size: 12px;
  color: var(--text2);
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.track-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}
.meta-pill {
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.pill-bpm {
  background: rgba(0,212,170,0.12);
  color: var(--accent2);
}
.pill-key {
  color: #fff;
  min-width: 32px;
  text-align: center;
}
.pill-dur {
  background: var(--surface3);
  color: var(--text2);
}

/* --- Pair cards --- */
.pair-card {
  height: var(--pair-h);
  padding: 0 18px;
  border-bottom: 1px solid rgba(42,42,64,0.5);
  transition: background 0.15s;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  position: absolute;
  left: 0;
  right: 0;
}
.pair-card:hover { background: var(--surface2); }
.pair-score {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 800;
  flex-shrink: 0;
  position: relative;
}
.pair-score::before {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2.5px solid;
  border-color: inherit;
  opacity: 0.3;
}
.pair-score.high { border-color: var(--accent2); color: var(--accent2); }
.pair-score.med { border-color: var(--orange); color: var(--orange); }
.pair-score.low { border-color: var(--text2); color: var(--text2); }
.pair-track-info { flex: 1; min-width: 0; }
.pair-track-name {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pair-track-artist {
  font-size: 12px;
  color: var(--text2);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pair-badges {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  align-items: center;
}
.badge-match {
  padding: 3px 8px;
  border-radius: 5px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.badge-same { background: rgba(0,212,170,0.15); color: var(--accent2); }
.badge-adjacent { background: rgba(124,92,252,0.15); color: var(--accent); }
.badge-relative { background: rgba(255,107,157,0.15); color: var(--pink); }
.badge-bpm {
  background: var(--surface3);
  color: var(--text2);
  font-weight: 600;
}
.badge-warn {
  padding: 3px 6px;
  border-radius: 5px;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  background: rgba(255,80,80,0.15);
  color: #ff5050;
}
.badge-good {
  padding: 3px 6px;
  border-radius: 5px;
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  background: rgba(0,212,170,0.12);
  color: var(--accent2);
}
.pill-energy {
  background: rgba(255,142,83,0.12);
  color: var(--orange);
}
.pill-grid {
  background: rgba(124,92,252,0.12);
  color: var(--accent);
}
.pair-detail {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
  margin-top: 2px;
}

/* --- Camelot Wheel --- */
.wheel-container {
  padding: 16px 32px;
  display: flex;
  justify-content: center;
  gap: 24px;
  align-items: flex-start;
}
.wheel-wrap {
  position: relative;
  width: 280px;
  height: 280px;
  flex-shrink: 0;
}
.wheel-seg {
  cursor: pointer;
  transition: opacity 0.15s, transform 0.15s;
}
.wheel-seg:hover { opacity: 0.85; }
.wheel-seg.active { filter: brightness(1.4) drop-shadow(0 0 6px currentColor); }
.wheel-seg.dimmed { opacity: 0.2; }
.wheel-seg text {
  font-size: 10px;
  font-weight: 700;
  fill: #fff;
  text-anchor: middle;
  dominant-baseline: central;
  pointer-events: none;
}
.wheel-center {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: var(--bg);
  border: 2px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: var(--text2);
  cursor: pointer;
  z-index: 2;
  transition: border-color 0.2s;
}
.wheel-center:hover { border-color: var(--accent); }
.wheel-legend {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 8px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text2);
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

/* --- Empty states --- */
.empty {
  padding: 60px 20px;
  text-align: center;
  color: var(--text2);
}
.empty .icon { font-size: 48px; margin-bottom: 12px; opacity: 0.4; }
.empty p { font-size: 14px; line-height: 1.6; }

/* --- Loading --- */
.spinner {
  width: 24px;
  height: 24px;
  border: 3px solid var(--surface3);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  margin: 40px auto;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* --- Responsive --- */
@media (max-width: 900px) {
  .main { flex-direction: column; height: auto; }
  .panel-left, .panel-right { margin: 0 0 10px 0; max-height: 50vh; }
  .wheel-container { flex-direction: column; align-items: center; }
}
</style>
</head>
<body>

<div class="header">
  <h1>Mashup Finder</h1>
  <div class="badge"><span id="trackCount">...</span> tracks loaded</div>
</div>

<div class="search-area">
  <div class="search-box">
    <span class="icon">&#9906;</span>
    <input type="text" id="searchInput" placeholder="Search tracks by artist or title..." autocomplete="off" />
  </div>
</div>

<div class="filters">
  <div class="filter-group">
    <span class="filter-label">BPM Range</span>
    <input type="range" class="bpm-slider" id="bpmSlider" min="2" max="20" value="6" />
    <span class="bpm-val" id="bpmVal">&plusmn;6</span>
  </div>
  <div class="filter-group">
    <span class="filter-label">Match</span>
    <div class="match-toggles">
      <button class="match-btn active" data-match="same">Same</button>
      <button class="match-btn active" data-match="adjacent">Adj</button>
      <button class="match-btn active" data-match="relative">Rel</button>
    </div>
  </div>
  <div class="filter-group" style="margin-left:auto">
    <span class="filter-label" id="keyFilterLabel" style="cursor:pointer;color:var(--accent)" onclick="clearKeyFilter()">
      Key: All
    </span>
  </div>
</div>

<div class="wheel-container" id="wheelContainer">
  <div class="wheel-wrap">
    <svg id="camelotWheel" viewBox="0 0 280 280" width="280" height="280"></svg>
    <div class="wheel-center" onclick="clearKeyFilter()" title="Clear key filter">ALL</div>
  </div>
  <div class="wheel-legend">
    <div class="legend-item"><div class="legend-dot" style="background:var(--accent2)"></div> Outer = Major (B)</div>
    <div class="legend-item"><div class="legend-dot" style="background:var(--accent)"></div> Inner = Minor (A)</div>
    <div class="legend-item" style="margin-top:8px;font-size:10px;opacity:0.6">Click a segment to filter by key</div>
  </div>
</div>

<div class="main">
  <div class="panel panel-left">
    <div class="panel-header">
      <span>Library</span>
      <div class="sort-group">
        <button class="sort-btn" data-sort="name" data-panel="left" onclick="toggleSort('left','name')">A-Z</button>
        <button class="sort-btn" data-sort="bpm" data-panel="left" onclick="toggleSort('left','bpm')">BPM</button>
        <button class="sort-btn" data-sort="key" data-panel="left" onclick="toggleSort('left','key')">Key</button>
        <button class="sort-btn" data-sort="energy" data-panel="left" onclick="toggleSort('left','energy')">NRG</button>
      </div>
      <span class="count" id="leftCount">0</span>
    </div>
    <div class="panel-body" id="trackListScroller">
      <div class="vlist-spacer" id="trackListSpacer">
        <div class="vlist-viewport" id="trackList"></div>
      </div>
    </div>
  </div>
  <div class="panel panel-right">
    <div class="panel-header">
      <span>Mashup Matches</span>
      <div class="sort-group">
        <button class="sort-btn active" data-sort="score" data-panel="right" onclick="toggleSort('right','score')">Score</button>
        <button class="sort-btn" data-sort="bpm" data-panel="right" onclick="toggleSort('right','bpm')">BPM</button>
        <button class="sort-btn" data-sort="key" data-panel="right" onclick="toggleSort('right','key')">Key</button>
      </div>
      <span class="count" id="rightCount">0</span>
    </div>
    <div class="panel-body" id="pairListScroller">
      <div class="vlist-spacer" id="pairListSpacer">
        <div class="vlist-viewport" id="pairList"></div>
      </div>
    </div>
  </div>
</div>

<script>
// --- Constants ---
const ROW_H = 54;
const PAIR_H = 82;
const BUFFER = 10;
const CAMELOT_COLORS = {
  1:'#FF6B6B',2:'#FF8E53',3:'#FFC853',4:'#E8FF53',
  5:'#88FF53',6:'#53FFB2',7:'#53FFF5',8:'#53C8FF',
  9:'#5388FF',10:'#8853FF',11:'#C853FF',12:'#FF53E8'
};
// Camelot sort order: 1A,1B,2A,2B,...12A,12B
function camelotOrder(c) {
  const n = parseInt(c);
  const l = c.slice(-1);
  return n * 2 + (l === 'B' ? 1 : 0);
}

// --- State ---
let allTracks = [];
let filteredTracks = [];
let pairData = [];
let filteredPairs = [];
let selectedTrackId = null;
let activeKeyFilter = null;
let activeMatchTypes = new Set(['same', 'adjacent', 'relative']);
let leftSort = { key: 'name', dir: 1 };
let rightSort = { key: 'score', dir: -1 };
let searchTimeout = null;

// --- Init ---
document.addEventListener('DOMContentLoaded', async () => {
  const stats = await api('/api/stats');
  document.getElementById('trackCount').textContent = stats.track_count.toLocaleString();
  buildWheel(stats.key_counts);
  // Load ALL tracks
  const data = await api('/api/tracks?limit=99999');
  allTracks = data.tracks;
  applyFiltersAndSort();
});

async function api(url) { return (await fetch(url)).json(); }

// --- Search ---
const searchInput = document.getElementById('searchInput');
searchInput.addEventListener('input', () => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => applyFiltersAndSort(), 150);
});

// --- Filtering & Sorting ---
function applyFiltersAndSort() {
  const q = searchInput.value.toLowerCase();
  filteredTracks = allTracks;
  if (q) {
    filteredTracks = filteredTracks.filter(t =>
      t.name.toLowerCase().includes(q) || t.artist.toLowerCase().includes(q)
    );
  }
  if (activeKeyFilter) {
    filteredTracks = filteredTracks.filter(t => t.camelot === activeKeyFilter);
  }
  sortTracks();
  document.getElementById('leftCount').textContent = filteredTracks.length.toLocaleString();
  renderVirtualList('left');
}

function sortTracks() {
  const { key, dir } = leftSort;
  filteredTracks.sort((a, b) => {
    if (key === 'name') return dir * a.name.localeCompare(b.name);
    if (key === 'bpm') return dir * (a.bpm - b.bpm);
    if (key === 'key') return dir * (camelotOrder(a.camelot) - camelotOrder(b.camelot));
    if (key === 'energy') return dir * (a.energy - b.energy);
    return 0;
  });
}

function sortPairs() {
  const { key, dir } = rightSort;
  filteredPairs.sort((a, b) => {
    if (key === 'score') return dir * (a.score - b.score);
    if (key === 'bpm') return dir * (a.track.bpm - b.track.bpm);
    if (key === 'key') return dir * (camelotOrder(a.track.camelot) - camelotOrder(b.track.camelot));
    return 0;
  });
}

function toggleSort(panel, key) {
  const state = panel === 'left' ? leftSort : rightSort;
  if (state.key === key) {
    state.dir *= -1;
  } else {
    state.key = key;
    state.dir = key === 'name' ? 1 : key === 'score' ? -1 : 1;
  }
  // Update button states
  document.querySelectorAll(`.sort-btn[data-panel="${panel}"]`).forEach(btn => {
    const isActive = btn.dataset.sort === key;
    btn.classList.toggle('active', isActive);
    if (isActive) {
      const arrow = state.dir === 1 ? '\u25B2' : '\u25BC';
      const labels = { name: 'A-Z', bpm: 'BPM', key: 'Key', score: 'Score', energy: 'NRG' };
      btn.textContent = labels[key] + ' ' + arrow;
    } else {
      const labels = { name: 'A-Z', bpm: 'BPM', key: 'Key', score: 'Score', energy: 'NRG' };
      btn.textContent = labels[btn.dataset.sort];
    }
  });
  if (panel === 'left') {
    sortTracks();
    renderVirtualList('left');
  } else {
    sortPairs();
    renderVirtualList('right');
  }
}

// --- Virtual Scrolling ---
function renderVirtualList(panel) {
  const isLeft = panel === 'left';
  const scroller = document.getElementById(isLeft ? 'trackListScroller' : 'pairListScroller');
  const spacer = document.getElementById(isLeft ? 'trackListSpacer' : 'pairListSpacer');
  const viewport = document.getElementById(isLeft ? 'trackList' : 'pairList');
  const items = isLeft ? filteredTracks : filteredPairs;
  const itemH = isLeft ? ROW_H : PAIR_H;

  if (!items.length) {
    spacer.style.height = '200px';
    viewport.innerHTML = isLeft
      ? '<div class="empty" style="position:static"><div class="icon">&#9835;</div><p>No tracks found</p></div>'
      : '<div class="empty" style="position:static"><div class="icon">&#8596;</div><p>Select a track to find mashup matches</p></div>';
    return;
  }

  const totalH = items.length * itemH;
  spacer.style.height = totalH + 'px';

  // Remove old listener, add new
  const handler = () => drawVisible(scroller, viewport, items, itemH, isLeft);
  scroller._vhandler && scroller.removeEventListener('scroll', scroller._vhandler);
  scroller._vhandler = handler;
  scroller.addEventListener('scroll', handler, { passive: true });
  handler();
}

function drawVisible(scroller, viewport, items, itemH, isLeft) {
  const scrollTop = scroller.scrollTop;
  const viewH = scroller.clientHeight;
  const startIdx = Math.max(0, Math.floor(scrollTop / itemH) - BUFFER);
  const endIdx = Math.min(items.length, Math.ceil((scrollTop + viewH) / itemH) + BUFFER);

  let html = '';
  for (let i = startIdx; i < endIdx; i++) {
    const top = i * itemH;
    html += isLeft ? trackHTML(items[i], top) : pairHTML(items[i], top);
  }
  viewport.innerHTML = html;
}

function trackHTML(t, top) {
  const dur = t.duration ? `${Math.floor(t.duration/60)}:${String(t.duration%60).padStart(2,'0')}` : '';
  const num = parseInt(t.camelot);
  const color = CAMELOT_COLORS[num] || '#888';
  const sel = t.id === selectedTrackId ? ' selected' : '';
  const gridIcon = t.straight ? '\u25A6' : '\u223F';
  return `<div class="track-item${sel}" style="top:${top}px" onclick="selectTrack(${t.id})">
    <div class="track-info">
      <div class="track-name">${esc(t.name)}</div>
      <div class="track-artist">${esc(t.artist)}</div>
    </div>
    <div class="track-meta">
      ${dur ? `<span class="meta-pill pill-dur">${dur}</span>` : ''}
      <span class="meta-pill pill-energy" title="Energy: ${t.energy}dB">${t.energy}dB</span>
      <span class="meta-pill pill-grid" title="${t.straight ? 'Straight grid' : 'Swing/live feel'}">${gridIcon}</span>
      <span class="meta-pill pill-bpm">${t.bpm}</span>
      <span class="meta-pill pill-key" style="background:${color}88">${t.camelot}</span>
    </div>
  </div>`;
}

function pairHTML(p, top) {
  const t = p.track;
  const num = parseInt(t.camelot);
  const color = CAMELOT_COLORS[num] || '#888';
  const pct = Math.round(p.score * 100);
  const scoreClass = pct >= 80 ? 'high' : pct >= 50 ? 'med' : 'low';
  const matchBadge = p.key_match === 'same' ? 'badge-same' : p.key_match === 'adjacent' ? 'badge-adjacent' : 'badge-relative';
  const matchLabel = p.key_match === 'same' ? 'SAME' : p.key_match === 'adjacent' ? 'ADJ' : 'REL';
  const bpmLabel = p.bpm_match === 'direct' ? `\u0394${p.bpm_diff}` : p.bpm_match === 'double' ? '2x' : '\u00BDx';
  // Warning & detail badges
  const warns = (p.warnings || []);
  let detailHTML = '';
  if (p.grid_match) detailHTML += '<span class="badge-good">GRID OK</span>';
  else if (warns.includes('grid')) detailHTML += '<span class="badge-warn">GRID \u2260</span>';
  if (warns.includes('tuning')) detailHTML += `<span class="badge-warn">TUNE \u0394${p.tuning_diff}Hz</span>`;
  if (warns.includes('energy')) detailHTML += `<span class="badge-warn">NRG \u0394${p.energy_diff}dB</span>`;
  else if (p.energy_diff !== undefined && p.energy_diff <= 3) detailHTML += `<span class="badge-good">NRG \u2248</span>`;
  return `<div class="pair-card" style="top:${top}px" onclick="selectTrack(${t.id})">
    <div class="pair-score ${scoreClass}">${pct}</div>
    <div class="pair-track-info">
      <div class="pair-track-name">${esc(t.name)}</div>
      <div class="pair-track-artist">${esc(t.artist)}</div>
      <div class="pair-detail">${detailHTML}</div>
    </div>
    <div class="pair-badges">
      <span class="badge-match ${matchBadge}">${matchLabel}</span>
      <span class="meta-pill pill-bpm">${t.bpm}</span>
      <span class="meta-pill pill-key" style="background:${color}88">${t.camelot}</span>
      <span class="badge-match badge-bpm">${bpmLabel}</span>
    </div>
  </div>`;
}

// --- Track selection ---
async function selectTrack(id) {
  selectedTrackId = id;
  renderVirtualList('left');  // re-render to show selection
  // Load pairs
  const bpm = document.getElementById('bpmSlider').value;
  const data = await api(`/api/pairs?track=${id}&bpm_range=${bpm}&limit=999`);
  pairData = data.pairs;
  applyPairFilters();
}

function applyPairFilters() {
  filteredPairs = pairData.filter(p => activeMatchTypes.has(p.key_match));
  sortPairs();
  document.getElementById('rightCount').textContent = filteredPairs.length.toLocaleString();
  document.getElementById('pairListScroller').scrollTop = 0;
  renderVirtualList('right');
}

// --- BPM slider ---
const bpmSlider = document.getElementById('bpmSlider');
bpmSlider.addEventListener('input', () => {
  document.getElementById('bpmVal').textContent = `\u00B1${bpmSlider.value}`;
});
bpmSlider.addEventListener('change', () => {
  if (selectedTrackId !== null) selectTrack(selectedTrackId);
});

// --- Match type toggles ---
document.querySelectorAll('.match-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const m = btn.dataset.match;
    btn.classList.toggle('active');
    if (activeMatchTypes.has(m)) activeMatchTypes.delete(m);
    else activeMatchTypes.add(m);
    if (pairData.length) applyPairFilters();
  });
});

// --- Camelot Wheel ---
function buildWheel(keyCounts) {
  const svg = document.getElementById('camelotWheel');
  const cx = 140, cy = 140;
  const outerR = 130, midR = 95, innerR = 55;
  for (let i = 0; i < 12; i++) {
    const num = i + 1;
    const startAngle = (i * 30 - 105) * Math.PI / 180;
    const endAngle = ((i + 1) * 30 - 105) * Math.PI / 180;
    const color = CAMELOT_COLORS[num];
    // Outer ring (B = Major)
    const outerPath = arcPath(cx, cy, midR, outerR, startAngle, endAngle);
    const outerKey = `${num}B`;
    const outerG = svgEl('g', {class: 'wheel-seg', 'data-key': outerKey});
    outerG.innerHTML = `<path d="${outerPath}" fill="${color}" fill-opacity="0.6" stroke="var(--bg)" stroke-width="1.5"/>`;
    const oMid = (startAngle + endAngle) / 2;
    outerG.innerHTML += `<text x="${cx + (midR+outerR)/2*Math.cos(oMid)}" y="${cy + (midR+outerR)/2*Math.sin(oMid)}">${outerKey}</text>`;
    outerG.onclick = () => setKeyFilter(outerKey);
    svg.appendChild(outerG);
    // Inner ring (A = Minor)
    const innerPath = arcPath(cx, cy, innerR, midR, startAngle, endAngle);
    const innerKey = `${num}A`;
    const innerG = svgEl('g', {class: 'wheel-seg', 'data-key': innerKey});
    innerG.innerHTML = `<path d="${innerPath}" fill="${color}" fill-opacity="0.35" stroke="var(--bg)" stroke-width="1.5"/>`;
    const iMid = (startAngle + endAngle) / 2;
    innerG.innerHTML += `<text x="${cx + (innerR+midR)/2*Math.cos(iMid)}" y="${cy + (innerR+midR)/2*Math.sin(iMid)}">${innerKey}</text>`;
    innerG.onclick = () => setKeyFilter(innerKey);
    svg.appendChild(innerG);
  }
}

function arcPath(cx, cy, r1, r2, a1, a2) {
  const x1=cx+r1*Math.cos(a1),y1=cy+r1*Math.sin(a1),
        x2=cx+r2*Math.cos(a1),y2=cy+r2*Math.sin(a1),
        x3=cx+r2*Math.cos(a2),y3=cy+r2*Math.sin(a2),
        x4=cx+r1*Math.cos(a2),y4=cy+r1*Math.sin(a2);
  return `M ${x1} ${y1} L ${x2} ${y2} A ${r2} ${r2} 0 0 1 ${x3} ${y3} L ${x4} ${y4} A ${r1} ${r1} 0 0 0 ${x1} ${y1} Z`;
}

function svgEl(tag, attrs) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  return el;
}

// --- Key filter ---
function setKeyFilter(key) {
  activeKeyFilter = key;
  document.getElementById('keyFilterLabel').innerHTML = `Key: <strong>${key}</strong> &#10005;`;
  const num = parseInt(key);
  const let_ = key.slice(-1);
  const prev = num === 1 ? 12 : num - 1;
  const next = num === 12 ? 1 : num + 1;
  const other = let_ === 'A' ? 'B' : 'A';
  const compat = new Set([key, `${prev}${let_}`, `${next}${let_}`, `${num}${other}`]);
  document.querySelectorAll('.wheel-seg').forEach(seg => {
    const k = seg.dataset.key;
    seg.classList.toggle('active', k === key);
    seg.classList.toggle('dimmed', !compat.has(k));
  });
  selectedTrackId = null;
  pairData = [];
  filteredPairs = [];
  document.getElementById('rightCount').textContent = '0';
  renderVirtualList('right');
  applyFiltersAndSort();
}

function clearKeyFilter() {
  activeKeyFilter = null;
  document.getElementById('keyFilterLabel').textContent = 'Key: All';
  document.querySelectorAll('.wheel-seg').forEach(seg => {
    seg.classList.remove('active', 'dimmed');
  });
  applyFiltersAndSort();
}

// --- Util ---
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
</script>
</body>
</html>"""

# ---------- HTTP Server ----------

class MashupHandler(BaseHTTPRequestHandler):
    tracks = []
    key_groups = {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/":
            self._html(HTML_PAGE)
        elif path == "/api/stats":
            counts = defaultdict(int)
            for t in self.tracks:
                counts[t["camelot"]] += 1
            self._json({
                "track_count": len(self.tracks),
                "key_counts": dict(counts),
            })
        elif path == "/api/tracks":
            q = params.get("q", [""])[0].lower()
            key = params.get("key", [None])[0]
            limit = int(params.get("limit", [99999])[0])
            results = self.tracks
            if q:
                results = [
                    t for t in results
                    if q in t["name"].lower() or q in t["artist"].lower()
                ]
            if key:
                results = [t for t in results if t["camelot"] == key]
            self._json({"tracks": results[:limit]})
        elif path == "/api/pairs":
            track_id = params.get("track", [None])[0]
            bpm_range = float(params.get("bpm_range", [6])[0])
            limit = int(params.get("limit", [9999])[0])
            if track_id is not None:
                track_id = int(track_id)
                pairs = find_pairs_for_track(
                    track_id, self.tracks, self.key_groups, bpm_range, limit
                )
                self._json({"pairs": pairs})
            else:
                q = params.get("q", [""])[0]
                key = params.get("key", [None])[0]
                pairs = search_pairs(
                    q, self.tracks, self.key_groups, bpm_range, key, limit
                )
                self._json({"pairs": pairs})
        else:
            self.send_error(404)

    def _json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, content):
        body = content.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # Suppress request logs


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Djay Pro Mashup Finder Web App")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--no-open", action="store_true", help="Don't open browser automatically")
    args = parser.parse_args()

    print("Loading Djay Pro library...", flush=True)
    tracks = load_tracks()
    print(f"Loaded {len(tracks)} tracks", flush=True)

    key_groups = defaultdict(list)
    for i, t in enumerate(tracks):
        key_groups[t["camelot"]].append(i)

    MashupHandler.tracks = tracks
    MashupHandler.key_groups = dict(key_groups)

    server = HTTPServer(("127.0.0.1", args.port), MashupHandler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"\n  Mashup Finder running at {url}\n", flush=True)

    if not args.no_open:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()

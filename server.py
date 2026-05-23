import base64
import json
import re
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from db import get_conn, DEFAULT_DB_PATH
from matching import find_pairs_for_track, build_key_groups

# HTML_PAGE copied from djay-mashup-app.py lines 383–1681
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
.mode-tabs {
  display: flex;
  gap: 4px;
  margin-left: 16px;
}
.mode-tab {
  padding: 6px 16px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text2);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.mode-tab.active {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(124,92,252,0.12);
}
.mode-tab:hover { border-color: var(--text2); }

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

/* --- Top pair cards (both tracks shown) --- */
.top-pair-card {
  height: 110px;
  padding: 8px 18px;
  border-bottom: 1px solid rgba(42,42,64,0.5);
  transition: background 0.15s;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
  position: absolute;
  left: 0;
  right: 0;
}
.top-pair-card:hover { background: var(--surface2); }
.top-pair-tracks { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.top-pair-row { display: flex; align-items: center; gap: 10px; }
.top-pair-row .track-info { flex: 1; min-width: 0; }
.top-pair-vs {
  font-size: 10px;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 1px;
  padding-left: 2px;
}
.top-pair-card .pair-info-btn {
  width: 28px; height: 28px; border-radius: 50%;
  border: 1px solid var(--border); background: var(--surface2);
  color: var(--text2); font-size: 14px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s; flex-shrink: 0;
}
.top-pair-card .pair-info-btn:hover { border-color: var(--accent); color: var(--accent); }

/* --- Info button on pair cards in library mode --- */
.pair-card .pair-info-btn {
  width: 24px; height: 24px; border-radius: 50%;
  border: 1px solid var(--border); background: var(--surface2);
  color: var(--text2); font-size: 12px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s; flex-shrink: 0;
}
.pair-card .pair-info-btn:hover { border-color: var(--accent); color: var(--accent); }

/* --- Detail Modal --- */
.modal-backdrop {
  position: fixed; inset: 0; background: rgba(0,0,0,0.7);
  z-index: 1000; display: flex; align-items: center; justify-content: center;
  animation: fadeIn 0.15s;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.modal-content {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; width: 480px; max-width: 92vw; max-height: 85vh;
  overflow-y: auto; padding: 28px; position: relative;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
  animation: slideUp 0.2s;
}
@keyframes slideUp { from { transform: translateY(20px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
.modal-close {
  position: absolute; top: 12px; right: 12px; width: 32px; height: 32px;
  border-radius: 50%; border: 1px solid var(--border); background: var(--surface2);
  color: var(--text2); font-size: 18px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.modal-close:hover { border-color: var(--accent); color: var(--accent); }
.modal-score-circle {
  width: 72px; height: 72px; border-radius: 50%; margin: 0 auto 20px;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px; font-weight: 800; position: relative;
}
.modal-score-circle::before {
  content: ''; position: absolute; inset: 0; border-radius: 50%;
  border: 3px solid; border-color: inherit; opacity: 0.3;
}
.modal-tracks { display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; }
.modal-track {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; background: var(--surface2); border-radius: 8px;
}
.modal-track .track-info { flex: 1; min-width: 0; }
.modal-vs { text-align: center; font-size: 10px; color: var(--text2); text-transform: uppercase; letter-spacing: 1px; }
.modal-bars { display: flex; flex-direction: column; gap: 10px; margin-top: 16px; }
.bar-row { display: flex; align-items: center; gap: 10px; }
.bar-label { width: 80px; font-size: 12px; color: var(--text2); text-align: right; flex-shrink: 0; }
.bar-track { flex: 1; height: 20px; background: var(--surface2); border-radius: 4px; overflow: hidden; position: relative; }
.bar-fill { height: 100%; border-radius: 4px; transition: width 0.4s ease; }
.bar-weight { width: 36px; font-size: 10px; color: var(--text2); text-align: center; flex-shrink: 0; }
.bar-val { position: absolute; right: 6px; top: 50%; transform: translateY(-50%); font-size: 10px; font-weight: 700; color: var(--text); }
.modal-badges { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; justify-content: center; }
.modal-badge {
  padding: 4px 10px; border-radius: 6px; font-size: 11px; font-weight: 700;
}

/* --- Mode transitions --- */
body.mode-top .panel-left { display: none; }
body.mode-top .panel-right { margin-left: 0; }

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
.waveform-wrap { margin-top: 20px; }
.waveform-label {
  font-size: 11px; color: var(--text2); text-transform: uppercase;
  letter-spacing: 0.5px; font-weight: 600; margin-bottom: 4px;
}
.waveform-canvas {
  width: 100%; height: 64px; border-radius: 6px;
  background: var(--surface2); display: block; margin-bottom: 12px;
}
</style>
</head>
<body>

<div class="header">
  <h1>Mashup Finder</h1>
  <div class="mode-tabs">
    <button class="mode-tab active" data-mode="library" onclick="setMode('library')">Library</button>
    <button class="mode-tab" data-mode="top" onclick="setMode('top')">Top Matches</button>
  </div>
  <div class="badge"><span id="trackCount">...</span> tracks loaded</div>
  <button id="importBtn" onclick="triggerImport()" style="margin-left:auto;padding:6px 14px;border-radius:8px;border:1px solid var(--border);background:var(--surface2);color:var(--text2);font-size:12px;font-weight:600;cursor:pointer;transition:border-color 0.15s" onmouseover="this.style.borderColor='var(--accent)'" onmouseout="this.style.borderColor='var(--border)'">↻ Import</button>
  <div id="importStatus" style="font-size:12px;color:var(--text2);display:none;white-space:nowrap"></div>
</div>

<div class="modal-backdrop" id="detailModal" style="display:none" onclick="if(event.target===this)closeModal()">
  <div class="modal-content" id="modalBody"></div>
</div>

<div id="loadingOverlay" style="position:fixed;inset:0;z-index:2000;background:var(--bg);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px;transition:opacity 0.4s">
  <h1 style="font-size:32px;font-weight:700;background:linear-gradient(135deg,var(--accent),var(--cyan));-webkit-background-clip:text;-webkit-text-fill-color:transparent">Mashup Finder</h1>
  <div class="spinner" style="width:36px;height:36px;border-width:4px"></div>
  <div id="loadingDetail" style="color:var(--text2);font-size:14px">Starting up...</div>
  <div style="width:240px;height:4px;border-radius:2px;background:var(--surface3);overflow:hidden;margin-top:4px">
    <div id="loadingBar" style="height:100%;width:0%;background:linear-gradient(90deg,var(--accent),var(--cyan));border-radius:2px;transition:width 0.5s ease"></div>
  </div>
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
  <div class="filter-group">
    <span class="filter-label">BPM</span>
    <div class="match-toggles">
      <button class="match-btn active bpm-match-btn" data-bpm-match="direct">1x</button>
      <button class="match-btn active bpm-match-btn" data-bpm-match="double">2x</button>
      <button class="match-btn active bpm-match-btn" data-bpm-match="half">&frac12;x</button>
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
const TOP_PAIR_H = 110;
const BUFFER = 10;
const CAMELOT_COLORS = {
  1:'#FF6B6B',2:'#FF8E53',3:'#FFC853',4:'#E8FF53',
  5:'#88FF53',6:'#53FFB2',7:'#53FFF5',8:'#53C8FF',
  9:'#5388FF',10:'#8853FF',11:'#C853FF',12:'#FF53E8'
};
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
let topPairsData = [];
let filteredTopPairs = [];
let selectedTrackId = null;
let activeKeyFilter = null;
let activeMatchTypes = new Set(['same', 'adjacent', 'relative']);
let activeBpmMatchTypes = new Set(['direct', 'double', 'half']);
let leftSort = { key: 'name', dir: 1 };
let rightSort = { key: 'score', dir: -1 };
let searchTimeout = null;
let currentMode = 'library'; // 'library' or 'top'

// --- Init ---
const stageProgress = { starting: 5, loading: 20, indexing: 50, precomputing: 70, ready: 100 };

document.addEventListener('DOMContentLoaded', () => {
  pollStatus();
});

async function pollStatus() {
  try {
    const status = await api('/api/status');
    const overlay = document.getElementById('loadingOverlay');
    document.getElementById('loadingDetail').textContent = status.detail;
    document.getElementById('loadingBar').style.width = (stageProgress[status.stage] || 0) + '%';
    if (status.stage === 'ready') {
      // Data is ready — load it
      const stats = await api('/api/stats');
      document.getElementById('trackCount').textContent = stats.track_count.toLocaleString();
      buildWheel(stats.key_counts);
      const data = await api('/api/tracks?limit=99999');
      allTracks = data.tracks;
      applyFiltersAndSort();
      // Fade out overlay
      overlay.style.opacity = '0';
      setTimeout(() => overlay.style.display = 'none', 400);
      return;
    }
  } catch(e) {}
  setTimeout(pollStatus, 500);
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

async function api(url) { return (await fetch(url)).json(); }

// --- Mode switching ---
function setMode(mode) {
  currentMode = mode;
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.toggle('active', t.dataset.mode === mode));
  document.body.classList.toggle('mode-top', mode === 'top');
  if (mode === 'top') {
    loadTopPairs();
  } else {
    // Restore library view
    filteredPairs = pairData.filter(p => activeMatchTypes.has(p.key_match));
    sortPairs();
    document.getElementById('rightCount').textContent = filteredPairs.length.toLocaleString();
    renderVirtualList('right');
  }
  applyFiltersAndSort();
}

async function loadTopPairs() {
  const data = await api('/api/top-pairs?limit=500');
  topPairsData = data.pairs;
  applyTopPairFilters();
}

function applyTopPairFilters() {
  const q = searchInput.value.toLowerCase();
  filteredTopPairs = topPairsData;
  if (q) {
    filteredTopPairs = filteredTopPairs.filter(p =>
      p.track_a.name.toLowerCase().includes(q) || p.track_a.artist.toLowerCase().includes(q) ||
      p.track_b.name.toLowerCase().includes(q) || p.track_b.artist.toLowerCase().includes(q)
    );
  }
  if (activeKeyFilter) {
    filteredTopPairs = filteredTopPairs.filter(p =>
      p.track_a.camelot === activeKeyFilter || p.track_b.camelot === activeKeyFilter
    );
  }
  filteredTopPairs = filteredTopPairs.filter(p => activeMatchTypes.has(p.key_match));
  filteredTopPairs = filteredTopPairs.filter(p => activeBpmMatchTypes.has(p.bpm_match));
  // Sort
  const { key, dir } = rightSort;
  filteredTopPairs.sort((a, b) => {
    if (key === 'score') return dir * (a.score - b.score);
    if (key === 'bpm') return dir * (a.track_a.bpm - b.track_a.bpm);
    if (key === 'key') return dir * (camelotOrder(a.track_a.camelot) - camelotOrder(b.track_a.camelot));
    return 0;
  });
  document.getElementById('rightCount').textContent = filteredTopPairs.length.toLocaleString();
  renderVirtualList('right');
}

// --- Search ---
const searchInput = document.getElementById('searchInput');
searchInput.addEventListener('input', () => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    applyFiltersAndSort();
    if (currentMode === 'top') applyTopPairFilters();
  }, 150);
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
  document.querySelectorAll(`.sort-btn[data-panel="${panel}"]`).forEach(btn => {
    const isActive = btn.dataset.sort === key;
    btn.classList.toggle('active', isActive);
    if (isActive) {
      const arrow = state.dir === 1 ? '▲' : '▼';
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
    if (currentMode === 'top') {
      applyTopPairFilters();
    } else {
      sortPairs();
      renderVirtualList('right');
    }
  }
}

// --- Virtual Scrolling ---
function renderVirtualList(panel) {
  const isLeft = panel === 'left';
  const scroller = document.getElementById(isLeft ? 'trackListScroller' : 'pairListScroller');
  const spacer = document.getElementById(isLeft ? 'trackListSpacer' : 'pairListSpacer');
  const viewport = document.getElementById(isLeft ? 'trackList' : 'pairList');
  const isTopMode = !isLeft && currentMode === 'top';
  const items = isLeft ? filteredTracks : (isTopMode ? filteredTopPairs : filteredPairs);
  const itemH = isLeft ? ROW_H : (isTopMode ? TOP_PAIR_H : PAIR_H);

  if (!items.length) {
    spacer.style.height = '200px';
    let emptyMsg;
    if (isLeft) {
      emptyMsg = '<div class="empty" style="position:static"><div class="icon">&#9835;</div><p>No tracks found</p></div>';
    } else if (isTopMode) {
      emptyMsg = '<div class="empty" style="position:static"><div class="icon">&#9733;</div><p>No top pairs found matching filters</p></div>';
    } else {
      emptyMsg = '<div class="empty" style="position:static"><div class="icon">&#8596;</div><p>Select a track to find mashup matches</p></div>';
    }
    viewport.innerHTML = emptyMsg;
    return;
  }

  const totalH = items.length * itemH;
  spacer.style.height = totalH + 'px';

  const renderFn = isLeft ? 'track' : (isTopMode ? 'topPair' : 'pair');
  const handler = () => drawVisible(scroller, viewport, items, itemH, renderFn);
  scroller._vhandler && scroller.removeEventListener('scroll', scroller._vhandler);
  scroller._vhandler = handler;
  scroller.addEventListener('scroll', handler, { passive: true });
  handler();
}

function drawVisible(scroller, viewport, items, itemH, renderFn) {
  const scrollTop = scroller.scrollTop;
  const viewH = scroller.clientHeight;
  const startIdx = Math.max(0, Math.floor(scrollTop / itemH) - BUFFER);
  const endIdx = Math.min(items.length, Math.ceil((scrollTop + viewH) / itemH) + BUFFER);

  let html = '';
  for (let i = startIdx; i < endIdx; i++) {
    const top = i * itemH;
    if (renderFn === 'track') html += trackHTML(items[i], top);
    else if (renderFn === 'topPair') html += topPairHTML(items[i], top, i);
    else html += pairHTML(items[i], top, i);
  }
  viewport.innerHTML = html;
}

function trackHTML(t, top) {
  const dur = t.duration ? `${Math.floor(t.duration/60)}:${String(t.duration%60).padStart(2,'0')}` : '';
  const num = parseInt(t.camelot);
  const color = CAMELOT_COLORS[num] || '#888';
  const sel = t.id === selectedTrackId ? ' selected' : '';
  const gridIcon = t.straight ? '▦' : '∿';
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

function pairHTML(p, top, idx) {
  const t = p.track;
  const num = parseInt(t.camelot);
  const color = CAMELOT_COLORS[num] || '#888';
  const pct = Math.round(p.score * 100);
  const scoreClass = pct >= 80 ? 'high' : pct >= 50 ? 'med' : 'low';
  const matchBadge = p.key_match === 'same' ? 'badge-same' : p.key_match === 'adjacent' ? 'badge-adjacent' : 'badge-relative';
  const matchLabel = p.key_match === 'same' ? 'SAME' : p.key_match === 'adjacent' ? 'ADJ' : 'REL';
  const bpmLabel = p.bpm_match === 'direct' ? `Δ${p.bpm_diff}` : p.bpm_match === 'double' ? '2x' : '½x';
  const warns = (p.warnings || []);
  let detailHTML = '';
  if (p.grid_match) detailHTML += '<span class="badge-good">GRID OK</span>';
  else if (warns.includes('grid')) detailHTML += '<span class="badge-warn">GRID ≠</span>';
  if (warns.includes('tuning')) detailHTML += `<span class="badge-warn">TUNE Δ${p.tuning_diff}Hz</span>`;
  if (warns.includes('energy')) detailHTML += `<span class="badge-warn">NRG Δ${p.energy_diff}dB</span>`;
  else if (p.energy_diff !== undefined && p.energy_diff <= 3) detailHTML += `<span class="badge-good">NRG ≈</span>`;
  if (warns.includes('variable_bpm')) detailHTML += '<span class="badge-warn">VAR BPM</span>';
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
    <button class="pair-info-btn" onclick="event.stopPropagation();showDetailFromLibrary(${idx})" title="Detail breakdown">i</button>
  </div>`;
}

function topPairHTML(p, top, idx) {
  const a = p.track_a, b = p.track_b;
  const numA = parseInt(a.camelot), numB = parseInt(b.camelot);
  const colA = CAMELOT_COLORS[numA] || '#888', colB = CAMELOT_COLORS[numB] || '#888';
  const pct = Math.round(p.score * 100);
  const scoreClass = pct >= 80 ? 'high' : pct >= 50 ? 'med' : 'low';
  const matchBadge = p.key_match === 'same' ? 'badge-same' : p.key_match === 'adjacent' ? 'badge-adjacent' : 'badge-relative';
  const matchLabel = p.key_match === 'same' ? 'SAME' : p.key_match === 'adjacent' ? 'ADJ' : 'REL';
  const bpmBadge = p.bpm_match === 'double' ? '<span class="badge-match badge-bpm" style="background:rgba(0,212,255,0.15);color:var(--cyan)">2x</span>' : p.bpm_match === 'half' ? '<span class="badge-match badge-bpm" style="background:rgba(0,212,255,0.15);color:var(--cyan)">&frac12;x</span>' : '';
  const varBpmBadge = (p.warnings && p.warnings.includes('variable_bpm'))
    ? '<span class="badge-warn" style="font-size:9px;padding:2px 5px">VAR BPM</span>' : '';
  return `<div class="top-pair-card" style="top:${top}px" onclick="showDetailFromTop(${idx})">
    <div class="pair-score ${scoreClass}">${pct}</div>
    <div class="top-pair-tracks">
      <div class="top-pair-row">
        <div class="track-info">
          <div class="track-name" style="font-size:13px">${esc(a.name)}</div>
          <div class="track-artist">${esc(a.artist)}</div>
        </div>
        <span class="meta-pill pill-bpm">${a.bpm}</span>
        <span class="meta-pill pill-key" style="background:${colA}88">${a.camelot}</span>
      </div>
      <div class="top-pair-vs">vs</div>
      <div class="top-pair-row">
        <div class="track-info">
          <div class="track-name" style="font-size:13px">${esc(b.name)}</div>
          <div class="track-artist">${esc(b.artist)}</div>
        </div>
        <span class="meta-pill pill-bpm">${b.bpm}</span>
        <span class="meta-pill pill-key" style="background:${colB}88">${b.camelot}</span>
      </div>
    </div>
    <div class="pair-badges" style="flex-direction:column;gap:4px">
      <span class="badge-match ${matchBadge}">${matchLabel}</span>
      ${bpmBadge}${varBpmBadge}
    </div>
    <button class="pair-info-btn" onclick="event.stopPropagation();showDetailFromTop(${idx})" title="Detail breakdown">i</button>
  </div>`;
}

// --- Detail Modal ---
function showDetailFromLibrary(idx) {
  const p = filteredPairs[idx];
  if (!p) return;
  const src = allTracks[selectedTrackId];
  showDetailModal(src, p.track, p);
}

function showDetailFromTop(idx) {
  const p = filteredTopPairs[idx];
  if (!p) return;
  showDetailModal(p.track_a, p.track_b, p);
}

function showDetailModal(trackA, trackB, p) {
  const pct = Math.round(p.score * 100);
  const scoreClass = pct >= 80 ? 'high' : pct >= 50 ? 'med' : 'low';
  const numA = parseInt(trackA.camelot), numB = parseInt(trackB.camelot);
  const colA = CAMELOT_COLORS[numA] || '#888', colB = CAMELOT_COLORS[numB] || '#888';

  const bars = [
    { label: 'Key', score: p.key_score, weight: '30%', color: 'var(--accent2)' },
    { label: 'BPM', score: p.bpm_score, weight: '25%', color: 'var(--cyan)' },
    { label: 'Energy', score: p.energy_score, weight: '15%', color: 'var(--orange)' },
    { label: 'Tuning', score: p.tuning_score, weight: '10%', color: 'var(--pink)' },
    { label: 'Grid', score: p.grid_score, weight: '10%', color: 'var(--accent)' },
    { label: 'Dynamics', score: p.dr_score, weight: '5%', color: '#E8FF53' },
    { label: 'Confidence', score: p.conf_score, weight: '5%', color: '#53FFB2' },
  ];

  let barsHTML = bars.map(b => {
    const val = b.score !== undefined ? b.score : 0;
    const pctVal = Math.round(val * 100);
    return `<div class="bar-row">
      <div class="bar-label">${b.label}</div>
      <div class="bar-track">
        <div class="bar-fill" style="width:${pctVal}%;background:${b.color}"></div>
        <div class="bar-val">${pctVal}%</div>
      </div>
      <div class="bar-weight">${b.weight}</div>
    </div>`;
  }).join('');

  let badgesHTML = '';
  if (p.second_key_match) {
    badgesHTML += `<span class="modal-badge badge-same">Secondary Key Match: ${p.second_key_a}</span>`;
  }
  if (p.tuning_a !== undefined && p.tuning_b !== undefined && p.tuning_a === p.tuning_b && p.tuning_a !== 440) {
    badgesHTML += `<span class="modal-badge badge-same">Same Tuning: ${p.tuning_a}Hz</span>`;
  }
  const warns = p.warnings || [];
  if (warns.includes('tuning')) badgesHTML += `<span class="modal-badge badge-warn">Tuning Mismatch: ${p.tuning_a}Hz vs ${p.tuning_b}Hz</span>`;
  if (warns.includes('energy')) badgesHTML += `<span class="modal-badge badge-warn">Energy Gap: ${p.energy_diff}dB</span>`;
  if (warns.includes('grid')) badgesHTML += `<span class="modal-badge badge-warn">Grid Mismatch</span>`;
  if (warns.includes('variable_bpm')) badgesHTML += `<span class="modal-badge badge-warn">Variable BPM</span>`;

  const matchLabel = p.key_match === 'same' ? 'Same Key' : p.key_match === 'adjacent' ? 'Adjacent Key' : 'Relative Key';
  const bpmLabel = p.bpm_match === 'direct' ? `Δ${p.bpm_diff} BPM` : p.bpm_match === 'double' ? 'Double Time' : 'Half Time';

  document.getElementById('modalBody').innerHTML = `
    <button class="modal-close" onclick="closeModal()">×</button>
    <div class="modal-score-circle ${scoreClass}" style="border-color:${scoreClass==='high'?'var(--accent2)':scoreClass==='med'?'var(--orange)':'var(--text2)'};color:${scoreClass==='high'?'var(--accent2)':scoreClass==='med'?'var(--orange)':'var(--text2)'}">${pct}</div>
    <div style="text-align:center;margin-bottom:16px">
      <span class="badge-match badge-${p.key_match === 'same' ? 'same' : p.key_match === 'adjacent' ? 'adjacent' : 'relative'}" style="font-size:12px">${matchLabel}</span>
      <span class="badge-match badge-bpm" style="font-size:12px">${bpmLabel}</span>
    </div>
    <div class="modal-tracks">
      <div class="modal-track">
        <span class="meta-pill pill-key" style="background:${colA}88">${trackA.camelot}</span>
        <div class="track-info">
          <div class="track-name" style="font-size:14px">${esc(trackA.name)}</div>
          <div class="track-artist">${esc(trackA.artist)}</div>
        </div>
        <span class="meta-pill pill-bpm">${trackA.bpm}</span>
      </div>
      <div class="modal-vs">vs</div>
      <div class="modal-track">
        <span class="meta-pill pill-key" style="background:${colB}88">${trackB.camelot}</span>
        <div class="track-info">
          <div class="track-name" style="font-size:14px">${esc(trackB.name)}</div>
          <div class="track-artist">${esc(trackB.artist)}</div>
        </div>
        <span class="meta-pill pill-bpm">${trackB.bpm}</span>
      </div>
    </div>
    <div style="font-size:12px;color:var(--text2);text-transform:uppercase;letter-spacing:0.5px;font-weight:600;margin-bottom:8px">Score Breakdown</div>
    <div class="modal-bars">${barsHTML}</div>
    ${badgesHTML ? '<div class="modal-badges">' + badgesHTML + '</div>' : ''}
  <div class="waveform-wrap">
    <div class="waveform-label">${esc(trackA.name)}</div>
    <canvas id="waveformA" class="waveform-canvas" height="64"></canvas>
    <div class="waveform-label">${esc(trackB.name)}</div>
    <canvas id="waveformB" class="waveform-canvas" height="64"></canvas>
  </div>
`;
  document.getElementById('detailModal').style.display = 'flex';
  loadWaveforms(trackA.id, trackB.id);
}

function closeModal() {
  document.getElementById('detailModal').style.display = 'none';
}

async function loadWaveforms(idA, idB) {
  const [dataA, dataB] = await Promise.all([
    api(`/api/tracks/${idA}/waveform`),
    api(`/api/tracks/${idB}/waveform`),
  ]);
  renderWaveform('waveformA', dataA);
  renderWaveform('waveformB', dataB);
}

function _b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

async function _zlibDecompress(bytes) {
  // Strip 2-byte zlib header, use raw deflate
  const ds = new DecompressionStream('deflate-raw');
  const writer = ds.writable.getWriter();
  const reader = ds.readable.getReader();
  const chunks = [];
  const done = reader.read().then(function pump({ done, value }) {
    if (done) return;
    chunks.push(value);
    return reader.read().then(pump);
  });
  writer.write(bytes.slice(2));
  writer.close();
  await done;
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) { out.set(chunk, offset); offset += chunk.length; }
  return out;
}

async function renderWaveform(canvasId, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const W = canvas.parentElement ? canvas.parentElement.clientWidth || 424 : 424;
  const H = 64;
  canvas.width = W;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'var(--surface2)';
  ctx.fillRect(0, 0, W, H);

  if (!data.waveform_colors) return;
  let colorBytes, ampBytes;
  try { colorBytes = await _zlibDecompress(_b64ToBytes(data.waveform_colors)); } catch(e) { return; }
  try { ampBytes = await _zlibDecompress(_b64ToBytes(data.waveform_low)); } catch(e) {}

  const nColor = colorBytes.length >> 1;
  const nAmp = ampBytes ? (ampBytes.length >> 1) : 0;
  let maxAmp = 0;
  if (nAmp > 0) {
    for (let i = 0; i < nAmp; i++) {
      const v = ((ampBytes[i*2] << 8) | ampBytes[i*2+1]);
      if (v > maxAmp) maxAmp = v;
    }
  }

  for (let x = 0; x < W; x++) {
    const ci = Math.floor(x / W * nColor);
    const hi = colorBytes[ci * 2], lo = colorBytes[ci * 2 + 1];
    const rgb = (hi << 8) | lo;
    const r = ((rgb >> 11) & 0x1F) << 3;
    const g = ((rgb >> 5) & 0x3F) << 2;
    const b = (rgb & 0x1F) << 3;

    let barH = H * 0.5;
    if (nAmp > 0 && maxAmp > 0) {
      const ai = Math.floor(x / W * nAmp);
      const amp = ((ampBytes[ai*2] << 8) | ampBytes[ai*2+1]) / maxAmp;
      barH = Math.max(2, amp * H);
    }
    const y0 = (H - barH) / 2;
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fillRect(x, y0, 1, barH);
  }

  // Beat tick marks
  if (data.beats) {
    try {
      const beatBytes = await _zlibDecompress(_b64ToBytes(data.beats));
      const view = new DataView(beatBytes.buffer);
      const nBeats = beatBytes.length >> 2;
      if (nBeats > 1) {
        const lastBeat = view.getFloat32((nBeats - 1) * 4, false);
        ctx.strokeStyle = 'rgba(255,255,255,0.18)';
        ctx.lineWidth = 1;
        for (let i = 0; i < nBeats; i++) {
          const t = view.getFloat32(i * 4, false);
          const x = Math.floor(t / lastBeat * W);
          ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
        }
      }
    } catch(e) {}
  }
}

// --- Track selection ---
async function selectTrack(id) {
  if (currentMode === 'top') return; // In top mode, clicks open detail
  selectedTrackId = id;
  renderVirtualList('left');
  const bpm = document.getElementById('bpmSlider').value;
  const data = await api(`/api/pairs?track=${id}&bpm_range=${bpm}&limit=999`);
  pairData = data.pairs;
  applyPairFilters();
}

function applyPairFilters() {
  filteredPairs = pairData.filter(p => activeMatchTypes.has(p.key_match) && activeBpmMatchTypes.has(p.bpm_match));
  sortPairs();
  document.getElementById('rightCount').textContent = filteredPairs.length.toLocaleString();
  document.getElementById('pairListScroller').scrollTop = 0;
  renderVirtualList('right');
}

// --- BPM slider ---
const bpmSlider = document.getElementById('bpmSlider');
bpmSlider.addEventListener('input', () => {
  document.getElementById('bpmVal').textContent = `±${bpmSlider.value}`;
});
bpmSlider.addEventListener('change', () => {
  if (selectedTrackId !== null) selectTrack(selectedTrackId);
});

// --- Match type toggles ---
document.querySelectorAll('.match-btn[data-match]').forEach(btn => {
  btn.addEventListener('click', () => {
    const m = btn.dataset.match;
    btn.classList.toggle('active');
    if (activeMatchTypes.has(m)) activeMatchTypes.delete(m);
    else activeMatchTypes.add(m);
    if (currentMode === 'top') applyTopPairFilters();
    else if (pairData.length) applyPairFilters();
  });
});
document.querySelectorAll('.bpm-match-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const m = btn.dataset.bpmMatch;
    btn.classList.toggle('active');
    if (activeBpmMatchTypes.has(m)) activeBpmMatchTypes.delete(m);
    else activeBpmMatchTypes.add(m);
    if (currentMode === 'top') applyTopPairFilters();
    else if (pairData.length) applyPairFilters();
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
  if (currentMode === 'top') applyTopPairFilters();
  else renderVirtualList('right');
  applyFiltersAndSort();
}

function clearKeyFilter() {
  activeKeyFilter = null;
  document.getElementById('keyFilterLabel').textContent = 'Key: All';
  document.querySelectorAll('.wheel-seg').forEach(seg => {
    seg.classList.remove('active', 'dimmed');
  });
  applyFiltersAndSort();
  if (currentMode === 'top') applyTopPairFilters();
}

// --- Util ---
function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
async function triggerImport() {
  const btn = document.getElementById('importBtn');
  const status = document.getElementById('importStatus');
  btn.textContent = '↻ Syncing...';
  btn.disabled = true;
  status.style.display = 'none';
  try {
    const data = await fetch('/api/import', { method: 'POST' }).then(r => r.json());
    status.textContent = `+${data.added} added, ${data.updated} updated, ${data.removed} removed`;
    status.style.display = 'block';
    if (data.added || data.updated || data.removed) {
      const res = await api('/api/tracks?limit=99999');
      allTracks = res.tracks;
      document.getElementById('trackCount').textContent = allTracks.length.toLocaleString();
      applyFiltersAndSort();
      if (currentMode === 'top') loadTopPairs();
    }
  } catch(e) {
    status.textContent = 'Import failed';
    status.style.display = 'block';
  }
  btn.textContent = '↻ Import';
  btn.disabled = false;
}
</script>
</body>
</html>"""

TRACK_SCALAR_COLS = [
    "id", "name", "artist", "bpm", "analyzed_bpm", "camelot", "key_name",
    "key_conf", "second_key", "tuning", "bpm_conf", "duration", "energy",
    "dyn_range", "straight", "forced_straight", "grid_dev", "first_downbeat",
    "time_signature", "beat_count", "bpm_stability", "bpm_segment_count",
    "bpm_segments", "transient_count", "source", "persistent_id",
]

_WAVEFORM_RE = re.compile(r"^/api/tracks/(\d+)/waveform$")


def _row_to_dict(row, cols):
    row_keys = row.keys()
    return {c: row[c] for c in cols if c in row_keys}


class MashupHandler(BaseHTTPRequestHandler):
    db_path = DEFAULT_DB_PATH

    def do_GET(self):
        parsed = urlparse(self.path)
        path, params = parsed.path, parse_qs(parsed.query)

        if path == "/":
            self._html(HTML_PAGE)
            return

        conn = None
        try:
            conn = get_conn(self.db_path)
            if path == "/api/status":
                self._json({"stage": "ready", "detail": "Ready"})

            elif path == "/api/stats":
                count = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
                rows = conn.execute(
                    "SELECT camelot, COUNT(*) n FROM tracks GROUP BY camelot"
                ).fetchall()
                self._json({"track_count": count,
                            "key_counts": {r["camelot"]: r["n"] for r in rows}})

            elif path == "/api/tracks":
                q = params.get("q", [""])[0].lower()
                key = params.get("key", [None])[0]
                limit = int(params.get("limit", [99999])[0])
                sql = f"SELECT {', '.join(TRACK_SCALAR_COLS)} FROM tracks WHERE 1=1"
                args = []
                if q:
                    sql += " AND (LOWER(name) LIKE ? OR LOWER(artist) LIKE ?)"
                    args += [f"%{q}%", f"%{q}%"]
                if key:
                    sql += " AND camelot=?"
                    args.append(key)
                sql += f" LIMIT {limit}"
                rows = conn.execute(sql, args).fetchall()
                self._json({"tracks": [_row_to_dict(r, TRACK_SCALAR_COLS) for r in rows]})

            elif path == "/api/pairs":
                track_id = params.get("track", [None])[0]
                bpm_range = float(params.get("bpm_range", [6])[0])
                limit = int(params.get("limit", [9999])[0])
                if track_id is None:
                    self._json({"pairs": []})
                    return
                track_id = int(track_id)
                row = conn.execute(
                    f"SELECT {', '.join(TRACK_SCALAR_COLS)} FROM tracks WHERE id=?",
                    [track_id]
                ).fetchone()
                if not row:
                    self._json({"pairs": []})
                    return
                track = _row_to_dict(row, TRACK_SCALAR_COLS)
                all_rows = conn.execute(
                    f"SELECT {', '.join(TRACK_SCALAR_COLS)} FROM tracks"
                ).fetchall()
                all_tracks = [_row_to_dict(r, TRACK_SCALAR_COLS) for r in all_rows]
                tracks_by_id = {t["id"]: t for t in all_tracks}
                key_groups = build_key_groups(all_tracks)
                pairs = find_pairs_for_track(track, tracks_by_id, key_groups, bpm_range, limit)
                self._json({"pairs": pairs})

            elif path == "/api/top-pairs":
                offset = int(params.get("offset", [0])[0])
                limit = int(params.get("limit", [50])[0])
                min_score = float(params.get("min_score", [0])[0])
                q = params.get("q", [""])[0].lower()
                key = params.get("key", [None])[0]
                match_types = params.get("match", [None])[0]
                allowed = set(match_types.split(",")) if match_types else None

                sql = """
                    SELECT tp.*,
                        a.id a_id, a.name a_name, a.artist a_artist,
                        a.bpm a_bpm, a.camelot a_camelot,
                        b.id b_id, b.name b_name, b.artist b_artist,
                        b.bpm b_bpm, b.camelot b_camelot,
                        a.bpm_segment_count a_bsc, b.bpm_segment_count b_bsc
                    FROM top_pairs tp
                    JOIN tracks a ON tp.track_a_id = a.id
                    JOIN tracks b ON tp.track_b_id = b.id
                    WHERE tp.score >= ?
                """
                args = [min_score]
                if q:
                    sql += (" AND (LOWER(a.name) LIKE ? OR LOWER(a.artist) LIKE ?"
                            " OR LOWER(b.name) LIKE ? OR LOWER(b.artist) LIKE ?)")
                    args += [f"%{q}%"] * 4
                if key:
                    sql += " AND (a.camelot = ? OR b.camelot = ?)"
                    args += [key, key]
                if allowed:
                    placeholders = ",".join("?" for _ in allowed)
                    sql += f" AND tp.key_match IN ({placeholders})"
                    args += list(allowed)
                sql += " ORDER BY tp.score DESC"

                all_rows = conn.execute(sql, args).fetchall()
                results = []
                for r in all_rows:
                    results.append({
                        "track_a": {"id": r["a_id"], "name": r["a_name"],
                                    "artist": r["a_artist"], "bpm": r["a_bpm"],
                                    "camelot": r["a_camelot"],
                                    "bpm_segment_count": r["a_bsc"]},
                        "track_b": {"id": r["b_id"], "name": r["b_name"],
                                    "artist": r["b_artist"], "bpm": r["b_bpm"],
                                    "camelot": r["b_camelot"],
                                    "bpm_segment_count": r["b_bsc"]},
                        "score": r["score"], "bpm_diff": r["bpm_diff"],
                        "bpm_match": r["bpm_match"], "key_match": r["key_match"],
                        "energy_diff": r["energy_diff"], "grid_match": r["grid_match"],
                        "tuning_diff": r["tuning_diff"], "dr_diff": r["dr_diff"],
                        "warnings": json.loads(r["warnings"] or "[]"),
                        "bpm_score": r["bpm_score"], "key_score": r["key_score"],
                        "energy_score": r["energy_score"], "grid_score": r["grid_score"],
                        "dr_score": r["dr_score"], "tuning_score": r["tuning_score"],
                        "conf_score": r["conf_score"],
                        "second_key_match": r["second_key_match"],
                    })
                self._json({"pairs": results[offset:offset + limit], "total": len(results)})

            elif _WAVEFORM_RE.match(path):
                track_id = int(_WAVEFORM_RE.match(path).group(1))
                row = conn.execute(
                    "SELECT beats_blob, waveform_low, waveform_max, waveform_colors, "
                    "transient_pos, transient_energy FROM tracks WHERE id=?",
                    [track_id]
                ).fetchone()
                if not row:
                    self.send_error(404)
                    return
                # NOTE: key "beats" (not "beats_blob") as expected by frontend and tests
                self._json({
                    "beats": base64.b64encode(row["beats_blob"] or b"").decode(),
                    "waveform_low": base64.b64encode(row["waveform_low"] or b"").decode(),
                    "waveform_max": base64.b64encode(row["waveform_max"] or b"").decode(),
                    "waveform_colors": base64.b64encode(row["waveform_colors"] or b"").decode(),
                    "transient_pos": base64.b64encode(row["transient_pos"] or b"").decode(),
                    "transient_energy": base64.b64encode(row["transient_energy"] or b"").decode(),
                })

            else:
                self.send_error(404)
        except ValueError as e:
            self.send_error(400, str(e))
        finally:
            if conn:
                conn.close()

    def do_POST(self):
        if self.path == "/api/import":
            from importer import run_sync
            self._json(run_sync(self.db_path))
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
        pass


class MashupServer:
    def __init__(self, db_path=DEFAULT_DB_PATH, port=8080, auto_open=True):
        handler = type("H", (MashupHandler,), {"db_path": db_path})
        self._server = HTTPServer(("127.0.0.1", port), handler)
        if auto_open:
            import webbrowser
            webbrowser.open(f"http://127.0.0.1:{port}")

    def serve_forever(self):
        self._server.serve_forever()

    def shutdown(self):
        self._server.shutdown()

"""PROTOTYPE: Three dashboard layouts, switchable with ?variant=A|B|C."""

# Question: Which layout best supports equal-weight night comparison and
# synchronized SpO2/respiration review? Synthetic data only; throw this away.

from __future__ import annotations

import argparse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


HTML = r"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Schlafdaten - UI-Prototyp</title>
  <style>
    :root {
      --paper: #eef3f5;
      --surface: #f9fbfb;
      --ink: #17242b;
      --muted: #687980;
      --grid: #cbd6db;
      --oxygen: #287d8e;
      --breath: #b45f3c;
      --stage: #6e5c8f;
      --stress: #777b47;
      --battery: #3e8064;
      --shadow: 0 16px 44px rgba(29, 48, 57, .12);
      color-scheme: light;
    }

    * { box-sizing: border-box; }
    html { background: var(--paper); color: var(--ink); }
    body {
      margin: 0;
      min-width: 320px;
      font-family: "Segoe UI", system-ui, sans-serif;
      background:
        linear-gradient(rgba(40,125,142,.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(40,125,142,.035) 1px, transparent 1px),
        var(--paper);
      background-size: 24px 24px;
    }
    button, input, textarea { font: inherit; }
    button:focus-visible, input:focus-visible, textarea:focus-visible {
      outline: 3px solid rgba(40,125,142,.28);
      outline-offset: 2px;
    }
    button { cursor: pointer; }
    .shell { width: min(1440px, calc(100% - 32px)); margin: 0 auto; padding: 24px 0 108px; }
    .topbar {
      display: flex; align-items: flex-end; justify-content: space-between; gap: 20px;
      border-bottom: 1px solid var(--ink); padding-bottom: 14px; margin-bottom: 18px;
    }
    .eyebrow, .label, th, .mono {
      font-family: "Cascadia Mono", Consolas, monospace;
      font-size: 11px; letter-spacing: .07em; text-transform: uppercase;
    }
    h1, h2, h3, p { margin-top: 0; }
    h1, h2, h3 { font-family: Bahnschrift, "Arial Narrow", sans-serif; font-weight: 560; }
    h1 { margin-bottom: 2px; font-size: clamp(27px, 4vw, 48px); letter-spacing: -.035em; }
    h2 { font-size: 23px; margin-bottom: 14px; }
    h3 { font-size: 16px; margin-bottom: 8px; }
    .muted { color: var(--muted); }
    .prototype-flag {
      padding: 7px 10px; border: 1px solid var(--breath); color: #7a321c;
      background: #fff4ed; font: 700 11px "Cascadia Mono", Consolas, monospace;
    }
    .state-line {
      display: flex; flex-wrap: wrap; gap: 8px 18px; align-items: center;
      margin-bottom: 18px; color: var(--muted); font-size: 12px;
    }
    .state-line b { color: var(--ink); font-weight: 650; }
    .panel { background: rgba(249,251,251,.96); border: 1px solid var(--grid); box-shadow: 0 8px 24px rgba(29,48,57,.05); }
    .panel-pad { padding: 18px; }
    .section-head { display: flex; justify-content: space-between; gap: 16px; align-items: start; margin-bottom: 12px; }
    .section-head p { margin: 0; color: var(--muted); font-size: 13px; }
    .controls { display: flex; flex-wrap: wrap; gap: 8px; }
    .chip, .axis-button, .night-button {
      border: 1px solid var(--grid); background: var(--surface); color: var(--ink); padding: 7px 10px;
    }
    .chip.active, .axis-button.active, .night-button.active { border-color: var(--ink); box-shadow: inset 0 -3px 0 var(--oxygen); }
    .night-button { text-align: left; min-width: 124px; }
    .night-button strong, .night-button span { display: block; }
    .night-button span { color: var(--muted); font-size: 12px; margin-top: 2px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid var(--grid); padding: 9px 10px; text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 600; }
    td:not(:first-child) { font-variant-numeric: tabular-nums; }
    tr:last-child td { border-bottom: 0; }
    .trace-stack { border-top: 1px solid var(--grid); }
    .trace-row {
      display: grid; grid-template-columns: 126px minmax(0, 1fr) 86px;
      min-height: 74px; align-items: center; border-bottom: 1px solid var(--grid);
    }
    .trace-row:last-child { border-bottom: 0; }
    .trace-label { padding: 10px 12px; }
    .trace-label strong { display: block; font: 600 12px "Cascadia Mono", Consolas, monospace; }
    .trace-label span, .trace-summary { color: var(--muted); font-size: 11px; }
    .trace-summary { padding-right: 12px; text-align: right; font-variant-numeric: tabular-nums; }
    .plot { position: relative; height: 66px; padding: 6px 0; }
    .plot svg { width: 100%; height: 100%; display: block; overflow: visible; }
    .plot-grid { stroke: var(--grid); stroke-width: .5; stroke-dasharray: 2 3; }
    .plot-line { fill: none; stroke-width: 2; vector-effect: non-scaling-stroke; }
    .stage-band { display: flex; height: 30px; margin: 14px 0; border: 1px solid var(--grid); overflow: hidden; }
    .stage-band span { min-width: 5px; }
    .stage-deep { background: #594675; }
    .stage-light { background: #9b8bb5; }
    .stage-rem { background: #6c8bb8; }
    .stage-awake { background: #d7a177; }
    .legend { display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 11px; }
    .dot { display: inline-block; width: 8px; height: 8px; margin-right: 5px; }
    .note-form { display: grid; gap: 9px; }
    textarea, input[type="text"] { width: 100%; border: 1px solid var(--grid); background: white; padding: 9px 10px; color: var(--ink); }
    textarea { resize: vertical; min-height: 76px; }
    .save-button { justify-self: start; border: 0; background: var(--ink); color: white; padding: 9px 13px; }
    .coverage-list { list-style: none; padding: 0; margin: 0; font-size: 12px; }
    .coverage-list li { display: flex; justify-content: space-between; gap: 12px; border-bottom: 1px solid var(--grid); padding: 7px 0; }
    .coverage-list li:last-child { border: 0; }
    .status-ok { color: #2f6f55; }
    .status-empty { color: #87502c; }

    /* A: trace first */
    .variant-a .hero-grid { display: grid; grid-template-columns: 1fr 330px; gap: 16px; }
    .variant-a .trace-panel { min-width: 0; }
    .variant-a .comparison { margin-top: 16px; }
    .variant-a .night-strip { display: flex; gap: 8px; margin-bottom: 14px; overflow-x: auto; padding-bottom: 4px; }

    /* B: night ledger */
    .variant-b .ledger { display: grid; grid-template-columns: repeat(3, minmax(270px, 1fr)); gap: 12px; overflow-x: auto; }
    .variant-b .night-column { min-width: 270px; padding: 16px; }
    .variant-b .night-column.selected { border-color: var(--ink); box-shadow: inset 0 4px 0 var(--oxygen), var(--shadow); }
    .variant-b .metric-pairs { display: grid; grid-template-columns: 1fr 1fr; gap: 0 12px; margin-bottom: 12px; }
    .variant-b .metric { border-bottom: 1px solid var(--grid); padding: 7px 0; }
    .variant-b .metric small, .variant-b .metric strong { display: block; }
    .variant-b .metric small { color: var(--muted); }
    .variant-b .mini-trace { border-top: 1px solid var(--grid); padding-top: 8px; margin-top: 8px; }
    .variant-b .mini-trace .plot { height: 45px; }
    .variant-b .ledger-footer { display: grid; grid-template-columns: 2fr 1fr; gap: 12px; margin-top: 12px; }

    /* C: split workbench */
    .variant-c .workbench { display: grid; grid-template-columns: 280px minmax(0, 1fr) 300px; gap: 12px; align-items: start; }
    .variant-c .rail, .variant-c .inspector { padding: 14px; position: sticky; top: 12px; }
    .variant-c .rail-list { display: grid; gap: 7px; }
    .variant-c .rail-item { border: 1px solid var(--grid); background: white; padding: 10px; text-align: left; }
    .variant-c .rail-item.active { border-color: var(--ink); box-shadow: inset 4px 0 0 var(--oxygen); }
    .variant-c .rail-item .rail-date { display: flex; justify-content: space-between; font-weight: 650; }
    .variant-c .rail-metrics { display: flex; gap: 10px; color: var(--muted); font-size: 11px; margin-top: 5px; }
    .variant-c .focus { min-width: 0; }
    .variant-c .focus-head { display: flex; justify-content: space-between; gap: 12px; align-items: start; padding: 18px 18px 8px; }
    .variant-c .quick-metrics { display: flex; flex-wrap: wrap; gap: 1px; background: var(--grid); border-top: 1px solid var(--grid); border-bottom: 1px solid var(--grid); }
    .variant-c .quick-metric { flex: 1 1 100px; background: var(--surface); padding: 10px; }
    .variant-c .quick-metric small, .variant-c .quick-metric strong { display: block; }
    .variant-c .quick-metric small { color: var(--muted); font-size: 10px; }
    .variant-c .inspector section + section { border-top: 1px solid var(--grid); padding-top: 14px; margin-top: 14px; }

    .switcher {
      position: fixed; z-index: 10; left: 50%; bottom: 18px; transform: translateX(-50%);
      display: flex; align-items: center; gap: 7px; padding: 8px;
      background: #10191e; color: white; border-radius: 999px; box-shadow: 0 12px 38px rgba(0,0,0,.28);
    }
    .switcher button { width: 38px; height: 34px; border: 1px solid #425159; background: #1d2a30; color: white; border-radius: 99px; }
    .switch-label { min-width: 220px; text-align: center; font: 12px "Cascadia Mono", Consolas, monospace; }
    .switch-label small { display: block; color: #aebbc0; margin-top: 2px; }

    @media (max-width: 1050px) {
      .variant-a .hero-grid, .variant-b .ledger-footer { grid-template-columns: 1fr; }
      .variant-c .workbench { grid-template-columns: 230px minmax(0,1fr); }
      .variant-c .inspector { grid-column: 1 / -1; position: static; display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
      .variant-c .inspector section + section { border: 0; padding: 0; margin: 0; }
    }
    @media (max-width: 700px) {
      .shell { width: min(100% - 18px, 1440px); padding-top: 12px; }
      .topbar { align-items: start; }
      .topbar .muted { display: none; }
      .trace-row { grid-template-columns: 92px minmax(0,1fr); }
      .trace-summary { display: none; }
      .variant-c .workbench { grid-template-columns: 1fr; }
      .variant-c .rail, .variant-c .inspector { position: static; }
      .variant-c .rail-list { display: flex; overflow-x: auto; }
      .variant-c .rail-item { min-width: 190px; }
      .variant-c .inspector { display: block; }
      .variant-c .inspector section + section { border-top: 1px solid var(--grid); padding-top: 14px; margin-top: 14px; }
      .switch-label { min-width: 172px; }
    }
    @media (prefers-reduced-motion: reduce) { * { scroll-behavior: auto !important; } }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div>
        <div class="eyebrow">Lokale Schlafdaten</div>
        <h1>Schlafverlauf</h1>
        <div class="muted">Drei Nächte vergleichen · Signale gemeinsam prüfen</div>
      </div>
      <div class="prototype-flag">PROTOTYP · SYNTHETISCHE DATEN</div>
    </header>
    <div id="state-line" class="state-line"></div>
    <main id="app"></main>
  </div>
  <nav class="switcher" aria-label="Prototypvarianten">
    <button id="previous" type="button" aria-label="Vorherige Variante">←</button>
    <div class="switch-label" id="switch-label"></div>
    <button id="next" type="button" aria-label="Nächste Variante">→</button>
  </nav>
  <script>
    const nights = [
      {
        id: 0, date: "18. Sep", weekday: "Freitag", start: "23:18", end: "06:41", duration: "7 h 02",
        score: "78", spo2: "96,1 %", respiration: "14,2/min", hrv: "41 ms", stress: "18", battery: "+37",
        tags: "spätes Essen", note: "Beispielnotiz. Nicht gespeichert.",
        stages: [["light",22],["deep",16],["light",18],["rem",12],["awake",4],["light",17],["rem",11]],
        oxygen: [96.8,96.4,96.6,96.1,null,95.9,96.3,96.0,95.6,96.2,96.5,96.1,96.4,96.6],
        breath: [14.1,13.8,14.4,14.7,14.3,13.9,14.2,14.6,14.0,13.7,14.1,14.5,14.2,14.0],
        heart: [56,54,52,51,53,55,57,54,52,51,52,55,58,57],
        stressLine: [17,14,12,11,15,18,21,16,13,12,14,19,22,18],
        batteryLine: [34,37,40,44,47,50,54,57,60,63,66,69,71,73]
      },
      {
        id: 1, date: "20. Sep", weekday: "Sonntag", start: "00:07", end: "07:16", duration: "6 h 43",
        score: "72", spo2: "95,6 %", respiration: "14,8/min", hrv: "36 ms", stress: "22", battery: "+29",
        tags: "Alkohol", note: "Synthetischer Eintrag zur Beurteilung des Layouts.",
        stages: [["light",18],["deep",11],["awake",5],["light",23],["rem",10],["awake",4],["light",19],["rem",10]],
        oxygen: [96.0,95.8,95.5,95.7,95.1,95.4,null,null,95.3,95.8,95.6,95.4,95.9,96.1],
        breath: [14.4,14.9,15.1,14.7,15.3,14.8,15.0,14.6,14.9,15.2,14.7,14.5,14.8,14.6],
        heart: [59,57,56,58,61,60,58,57,55,56,59,61,60,58],
        stressLine: [23,21,19,24,27,25,22,20,18,21,24,28,25,22],
        batteryLine: [29,31,33,35,38,41,44,46,49,51,53,55,57,58]
      },
      {
        id: 2, date: "22. Sep", weekday: "Dienstag", start: "22:54", end: "06:22", duration: "7 h 14",
        score: "84", spo2: "96,4 %", respiration: "13,9/min", hrv: "45 ms", stress: "15", battery: "+42",
        tags: "Training", note: "",
        stages: [["light",17],["deep",19],["light",15],["rem",14],["awake",3],["light",16],["deep",7],["rem",9]],
        oxygen: [96.5,96.7,96.4,96.2,96.6,96.3,96.5,96.7,96.4,96.1,96.5,96.8,96.6,96.7],
        breath: [13.8,13.6,14.0,14.2,13.9,13.7,13.8,14.1,13.9,13.6,13.8,14.0,13.9,13.7],
        heart: [54,52,50,49,51,53,52,50,49,50,52,54,53,52],
        stressLine: [14,12,10,9,12,15,16,13,11,10,12,16,17,15],
        batteryLine: [31,35,39,43,47,51,55,59,63,66,69,72,74,76]
      }
    ];

    const variants = {
      A: { name: "Signal zuerst", render: renderA },
      B: { name: "Nacht-Ledger", render: renderB },
      C: { name: "Analysebank", render: renderC }
    };
    const keys = Object.keys(variants);
    const requested = new URLSearchParams(location.search).get("variant")?.toUpperCase();
    const state = { variant: variants[requested] ? requested : "A", selected: 0, axis: "Uhrzeit", saved: false };

    function segments(values) {
      const pieces = [];
      let current = [];
      values.forEach((value, index) => {
        if (value === null) {
          if (current.length) pieces.push(current);
          current = [];
        } else current.push([index, value]);
      });
      if (current.length) pieces.push(current);
      return pieces;
    }

    function plot(values, color) {
      const present = values.filter(value => value !== null);
      const min = Math.min(...present), max = Math.max(...present), span = max - min || 1;
      const lines = segments(values).map(part => {
        const points = part.map(([index, value]) => {
          const x = index * (100 / (values.length - 1));
          const y = 35 - ((value - min) / span) * 28;
          return `${x.toFixed(2)},${y.toFixed(2)}`;
        }).join(" ");
        return `<polyline class="plot-line" stroke="${color}" points="${points}"/>`;
      }).join("");
      return `<div class="plot"><svg viewBox="0 0 100 40" preserveAspectRatio="none" role="img" aria-label="Synthetische Zeitreihe"><line class="plot-grid" x1="0" y1="20" x2="100" y2="20"/>${lines}</svg></div>`;
    }

    function stageBand(night) {
      const labels = { deep: "Tief", light: "Leicht", rem: "REM", awake: "Wach" };
      return `<div class="stage-band" aria-label="Synthetische Schlafphasen">${night.stages.map(([stage,width]) => `<span class="stage-${stage}" style="flex:${width}" title="${labels[stage]}"></span>`).join("")}</div>`;
    }

    function legend() {
      return `<div class="legend"><span><i class="dot stage-deep"></i>Tief</span><span><i class="dot stage-light"></i>Leicht</span><span><i class="dot stage-rem"></i>REM</span><span><i class="dot stage-awake"></i>Wach</span></div>`;
    }

    function traceRow(label, unit, values, color, summary) {
      return `<div class="trace-row"><div class="trace-label"><strong>${label}</strong><span>${unit}</span></div>${plot(values,color)}<div class="trace-summary">${summary}</div></div>`;
    }

    function fullTrace(night) {
      return `<div class="trace-stack">
        <div class="trace-row"><div class="trace-label"><strong>Schlafphasen</strong><span>Garmin</span></div><div>${stageBand(night)}${legend()}</div><div class="trace-summary">${night.duration}</div></div>
        ${traceRow("SpO2", "%", night.oxygen, "var(--oxygen)", night.spo2)}
        ${traceRow("Respiration", "Atemzüge/min", night.breath, "var(--breath)", night.respiration)}
        ${traceRow("Herzfrequenz", "Schläge/min", night.heart, "var(--stage)", "Verlauf")}
        ${traceRow("Stress", "Garmin", night.stressLine, "var(--stress)", night.stress)}
        ${traceRow("Body Battery", "Garmin", night.batteryLine, "var(--battery)", night.battery)}
      </div>`;
    }

    function comparisonTable() {
      const rows = [
        ["Zeitraum", n => `${n.start}-${n.end}`], ["Schlafdauer", n => n.duration], ["Garmin Score", n => n.score],
        ["SpO2 Mittel", n => n.spo2], ["Respiration Mittel", n => n.respiration], ["HRV", n => n.hrv],
        ["Stress", n => n.stress], ["Body Battery", n => n.battery], ["Tags", n => n.tags || "-"]
      ];
      return `<div style="overflow:auto"><table><thead><tr><th>Merkmal</th>${nights.map(n => `<th>${n.date}</th>`).join("")}</tr></thead><tbody>${rows.map(([label,read]) => `<tr><td>${label}</td>${nights.map(n => `<td>${read(n)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    }

    function axisControls() {
      return `<div class="controls"><button class="axis-button ${state.axis === "Uhrzeit" ? "active" : ""}" data-axis="Uhrzeit">Uhrzeit</button><button class="axis-button ${state.axis === "Seit Schlafbeginn" ? "active" : ""}" data-axis="Seit Schlafbeginn">Seit Schlafbeginn</button></div>`;
    }

    function annotation(night) {
      return `<div class="note-form"><label class="label" for="tags">Tags</label><input id="tags" type="text" value="${night.tags}" placeholder="z. B. Alkohol, Training"><label class="label" for="note">Notiz</label><textarea id="note" placeholder="Beobachtung zur Nacht">${night.note}</textarea><button class="save-button" id="save-note" type="button">Notiz speichern</button><span class="muted" id="save-state">${state.saved ? "Im Prototyp gespeichert" : "Nur im Arbeitsspeicher"}</span></div>`;
    }

    function coverage() {
      return `<ul class="coverage-list"><li><span>Schlaf</span><b class="status-ok">Daten</b></li><li><span>SpO2</span><b class="status-ok">Daten mit Lücke</b></li><li><span>Respiration</span><b class="status-ok">Daten</b></li><li><span>HRV</span><b class="status-ok">Daten</b></li><li><span>Body Battery Events</span><b class="status-empty">Abgerufen, keine Daten</b></li></ul>`;
    }

    function renderA() {
      const night = nights[state.selected];
      return `<div class="variant-a">
        <div class="night-strip">${nights.map(n => `<button class="night-button ${n.id === state.selected ? "active" : ""}" data-night="${n.id}"><strong>${n.date}</strong><span>${n.start}-${n.end} · ${n.tags || "ohne Tags"}</span></button>`).join("")}</div>
        <div class="hero-grid">
          <section class="panel trace-panel"><div class="panel-pad section-head"><div><div class="eyebrow">Ausgewählte Nacht</div><h2>${night.weekday}, ${night.date}</h2><p>Gemeinsame Zeitachse · keine medizinische Auswertung</p></div>${axisControls()}</div>${fullTrace(night)}</section>
          <aside class="panel panel-pad"><div class="eyebrow">Anmerkung</div><h2>${night.duration}</h2>${annotation(night)}<div style="height:18px"></div><div class="eyebrow">Datenlage</div>${coverage()}</aside>
        </div>
        <section class="panel panel-pad comparison"><div class="section-head"><div><div class="eyebrow">Vergleich</div><h2>Drei aufgezeichnete Nächte</h2></div><div class="controls"><span class="chip active">Alle Signale</span><span class="chip">Nur Unterschiede</span></div></div>${comparisonTable()}</section>
      </div>`;
    }

    function renderB() {
      return `<div class="variant-b">
        <div class="section-head"><div><div class="eyebrow">Nacht-Ledger</div><h2>Jede Nacht als vollständige Spalte</h2><p>Direkter Vergleich ohne separate Detailansicht.</p></div>${axisControls()}</div>
        <div class="ledger">${nights.map(n => `<article class="panel night-column ${n.id === state.selected ? "selected" : ""}" data-night="${n.id}"><div class="eyebrow">${n.weekday}</div><h2>${n.date}</h2><div class="muted">${n.start}-${n.end} · ${n.duration}</div>${stageBand(n)}${legend()}<div class="metric-pairs"><div class="metric"><small>SpO2</small><strong>${n.spo2}</strong></div><div class="metric"><small>Respiration</small><strong>${n.respiration}</strong></div><div class="metric"><small>HRV</small><strong>${n.hrv}</strong></div><div class="metric"><small>Stress</small><strong>${n.stress}</strong></div></div><div class="mini-trace"><span class="label">SpO2</span>${plot(n.oxygen,"var(--oxygen)")}</div><div class="mini-trace"><span class="label">Respiration</span>${plot(n.breath,"var(--breath)")}</div><div class="mini-trace"><span class="label">Herzfrequenz</span>${plot(n.heart,"var(--stage)")}</div><div class="label" style="margin-top:12px">Tags</div><div>${n.tags || "-"}</div></article>`).join("")}</div>
        <div class="ledger-footer"><section class="panel panel-pad"><div class="eyebrow">Gemeinsame Kennzahlen</div>${comparisonTable()}</section><section class="panel panel-pad"><div class="eyebrow">Anmerkung für ${nights[state.selected].date}</div>${annotation(nights[state.selected])}</section></div>
      </div>`;
    }

    function renderC() {
      const night = nights[state.selected];
      return `<div class="variant-c"><div class="workbench">
        <aside class="panel rail"><div class="section-head"><div><div class="eyebrow">Historie</div><h2>Nächte</h2></div></div><input type="text" value="" placeholder="Datum oder Tag filtern" aria-label="Nächte filtern"><div style="height:10px"></div><div class="rail-list">${nights.map(n => `<button class="rail-item ${n.id === state.selected ? "active" : ""}" data-night="${n.id}"><span class="rail-date"><span>${n.date}</span><span>${n.duration}</span></span><span class="rail-metrics"><span>${n.spo2}</span><span>${n.respiration}</span></span></button>`).join("")}</div><div style="height:14px"></div><div class="eyebrow">Vergleich</div><p class="muted">Alle drei Nächte ausgewählt</p><button class="save-button" type="button">Vergleich öffnen</button></aside>
        <section class="panel focus"><div class="focus-head"><div><div class="eyebrow">Analysebank</div><h2>${night.weekday}, ${night.date}</h2><p class="muted">${night.start}-${night.end} · ${night.tags || "ohne Tags"}</p></div>${axisControls()}</div><div class="quick-metrics"><div class="quick-metric"><small>Schlafdauer</small><strong>${night.duration}</strong></div><div class="quick-metric"><small>SpO2</small><strong>${night.spo2}</strong></div><div class="quick-metric"><small>Respiration</small><strong>${night.respiration}</strong></div><div class="quick-metric"><small>HRV</small><strong>${night.hrv}</strong></div><div class="quick-metric"><small>Stress</small><strong>${night.stress}</strong></div></div>${fullTrace(night)}</section>
        <aside class="panel inspector"><section><div class="eyebrow">Notizen und Tags</div><h3>${night.date}</h3>${annotation(night)}</section><section><div class="eyebrow">Datenlage</div><h3>Abrufstatus</h3>${coverage()}</section><section><div class="eyebrow">Hinweis</div><p class="muted">Garmin-Werte werden dargestellt, nicht medizinisch bewertet. Lücken bleiben sichtbar.</p></section></aside>
      </div></div>`;
    }

    function bind() {
      document.querySelectorAll("[data-night]").forEach(element => element.addEventListener("click", () => { state.selected = Number(element.dataset.night); state.saved = false; render(); }));
      document.querySelectorAll("[data-axis]").forEach(element => element.addEventListener("click", () => { state.axis = element.dataset.axis; render(); }));
      document.querySelector("#save-note")?.addEventListener("click", () => { state.saved = true; render(); });
    }

    function setVariant(key) {
      state.variant = key;
      const url = new URL(location.href);
      url.searchParams.set("variant", key);
      history.replaceState({}, "", url);
      render();
    }

    function cycle(step) {
      const index = keys.indexOf(state.variant);
      setVariant(keys[(index + step + keys.length) % keys.length]);
    }

    function render() {
      const current = variants[state.variant];
      document.querySelector("#app").innerHTML = current.render();
      document.querySelector("#switch-label").innerHTML = `${state.variant} - ${current.name}<small>Pfeiltasten wechseln</small>`;
      document.querySelector("#state-line").innerHTML = `<span><b>Variante ${state.variant}</b> ${current.name}</span><span><b>Nacht</b> ${nights[state.selected].date}</span><span><b>Achse</b> ${state.axis}</span><span><b>Notizen</b> ${state.saved ? "Prototypzustand geändert" : "unverändert"}</span>`;
      bind();
    }

    document.querySelector("#previous").addEventListener("click", () => cycle(-1));
    document.querySelector("#next").addEventListener("click", () => cycle(1));
    document.addEventListener("keydown", event => {
      const tag = document.activeElement?.tagName;
      if (["INPUT", "TEXTAREA"].includes(tag) || document.activeElement?.isContentEditable) return;
      if (event.key === "ArrowLeft") cycle(-1);
      if (event.key === "ArrowRight") cycle(1);
    });
    render();
  </script>
</body>
</html>
"""


class PrototypeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib hook name
        path = self.path.split("?", 1)[0]
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/prototype/dashboard?variant=A")
            self.end_headers()
            return
        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if path != "/prototype/dashboard":
            self.send_error(404)
            return

        encoded = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Throwaway sleep dashboard UI prototype")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args(argv)
    url = f"http://127.0.0.1:{args.port}/prototype/dashboard?variant=A"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), PrototypeHandler)
    print(f"PROTOTYPE - synthetic data only: {url}")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Signals & Shifts — Automated Pipeline
--------------------------------------
Reads signals.json, applies freshness updates (Signal of the Week rotation,
timestamps), generates the full site HTML, and deploys to Netlify.

v1 — simple rotation/freshness system. Can be extended later with RSS/API
feeds for real signal detection.
"""

import os
import sys
import json
import hashlib
import re
import shutil
import urllib.request
import urllib.error
import time
from datetime import datetime, timezone
from collections import Counter

# ── CONFIG ──────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = SCRIPT_DIR
DEPLOY_DIR = os.path.join(PROJECT_DIR, 'deploy')
SIGNALS_FILE = os.path.join(PROJECT_DIR, 'signals.json')

SITE_ID = os.environ.get('NETLIFY_SITE_ID', '976ac64e-9d8a-41b5-9ce9-5f886b205e57')
AUTH_TOKEN = os.environ.get('NETLIFY_TOKEN', 'nfp_PLKgWZbdCNqyN8Cbvob9n2JszWQGXvkC927c')
API_BASE = 'https://api.netlify.com/api/v1'
NTFY_TOPIC = 'signals-shifts-ml'

DOMAINS = ['music', 'design', 'food', 'fashion', 'tech']
STAGES = ['emerging', 'accelerating', 'mainstream', 'peaking', 'declining']


# ── HELPERS ─────────────────────────────────────────────────────────────────

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def load_signals():
    """Load signals.json and return parsed data."""
    with open(SIGNALS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_signals(data):
    """Save signals data back to signals.json."""
    with open(SIGNALS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Saved {len(data['signals'])} signals to signals.json")


def get_week_number():
    """Get ISO week number for the current date."""
    now = datetime.now(timezone.utc)
    return now.isocalendar()[1]


def get_edition_label():
    """Get the current month/year edition label (e.g. 'March 2026')."""
    now = datetime.now(timezone.utc)
    return now.strftime('%B %Y')


def get_edition_short():
    """Get short edition (e.g. 'MAR 2026')."""
    now = datetime.now(timezone.utc)
    return now.strftime('%b %Y').upper()


def get_date_iso():
    """Get today's date as ISO string."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


# ── SIGNAL OF THE WEEK ─────────────────────────────────────────────────────

def select_signal_of_the_week(signals):
    """
    Deterministic weekly rotation of Signal of the Week.
    Uses week number to cycle through all signals, preferring 'accelerating'
    stage signals as they are the most dynamic.
    """
    week = get_week_number()

    # Prefer accelerating signals for SOTW — they're the most interesting
    accelerating = [s for s in signals if s['stage'] == 'accelerating']
    if not accelerating:
        accelerating = signals

    idx = week % len(accelerating)
    return accelerating[idx]


# ── STATS CALCULATION ───────────────────────────────────────────────────────

def calculate_stats(signals):
    """Calculate dashboard stats from signal data."""
    total = len(signals)
    domains = len(set(s['domain'] for s in signals))
    stage_counts = Counter(s['stage'] for s in signals)
    domain_counts = Counter(s['domain'] for s in signals)
    momentum_counts = Counter(s['momentum'] for s in signals)

    return {
        'total': total,
        'domains': domains,
        'stage_counts': dict(stage_counts),
        'domain_counts': dict(domain_counts),
        'momentum_counts': dict(momentum_counts),
        'accelerating': stage_counts.get('accelerating', 0),
        'emerging': stage_counts.get('emerging', 0),
    }


# ── FRESHNESS UPDATES ──────────────────────────────────────────────────────

def update_freshness(data):
    """
    Update timestamps and metadata for freshness.
    In v1, this simply updates the lastUpdated field.
    Future versions could check RSS/API feeds and adjust signal stages.
    """
    today = get_date_iso()
    edition = get_edition_label()

    data['meta']['lastUpdated'] = today
    data['meta']['edition'] = edition

    log(f"Updated metadata: edition={edition}, lastUpdated={today}")
    return data


# ── HTML GENERATION ─────────────────────────────────────────────────────────

def generate_signal_card(signal):
    """Generate HTML for a single signal card."""
    sid = signal['id']
    domain = signal['domain']
    stage = signal['stage']
    momentum = signal['momentum']
    title = signal['title']
    description = signal['description']
    evidence = signal.get('evidence', [])
    connections = signal.get('connections', [])

    # Momentum display
    if momentum == 'up':
        momentum_html = '<div class="momentum-indicator up"><span class="momentum-arrow">&#9650;</span> Rising</div>'
    elif momentum == 'down':
        momentum_html = '<div class="momentum-indicator down"><span class="momentum-arrow">&#9660;</span> Falling</div>'
    else:
        momentum_html = '<div class="momentum-indicator steady"><span class="momentum-arrow">&#9654;</span> Plateau</div>'

    # Domain display name
    domain_display = domain.capitalize()

    # Stage display
    stage_display = stage.capitalize()

    # Lifecycle progress
    stage_index = STAGES.index(stage)
    if stage_index == 0:
        progress_width = '0'
    else:
        progress_width = f'calc({stage_index * 25}% - 4px)'

    # Lifecycle dots
    dots_html = ''
    for i in range(5):
        if i < stage_index:
            dots_html += '<div class="lifecycle-dot passed"></div>\n'
        elif i == stage_index:
            dots_html += '<div class="lifecycle-dot active"></div>\n'
        else:
            dots_html += '<div class="lifecycle-dot"></div>\n'

    # Lifecycle labels
    labels_html = ''
    for i, s in enumerate(STAGES):
        cls = 'lifecycle-label active-label' if i == stage_index else 'lifecycle-label'
        labels_html += f'<span class="{cls}">{s.capitalize()}</span>\n'

    # Evidence links
    evidence_html = ''
    for e in evidence:
        evidence_html += f'<a href="#" class="evidence-link">{html_escape(e)}</a>\n'

    # Connection dots
    connection_dots = ''
    connection_names = []
    for c in connections:
        connection_dots += f'<div class="connection-dot" style="background: var(--{c})"></div>\n'
        connection_names.append(c.capitalize())

    connection_title = f'Connected to: {", ".join(connection_names)}' if connection_names else ''

    return f'''                <div class="shift-card" data-domain="{domain}" data-stage="{stage}">
                    <div class="card-domain-strip"></div>
                    <div class="card-body">
                        <div class="shift-card-top">
                            <div class="shift-card-top-left">
                                <span class="shift-domain-tag">{domain_display}</span>
                                <span class="shift-stage {stage}">{stage_display}</span>
                            </div>
                            {momentum_html}
                        </div>
                        <h3 class="shift-headline">{html_escape(title)}</h3>
                        <p class="shift-analysis">{html_escape(description)}</p>
                        <div class="lifecycle">
                            <div class="lifecycle-track">
                                <div class="lifecycle-line"></div>
                                <div class="lifecycle-progress" style="width: {progress_width}"></div>
                                <div class="lifecycle-stages">
                                    {dots_html}
                                </div>
                            </div>
                            <div class="lifecycle-labels">
                                {labels_html}
                            </div>
                        </div>
                    </div>
                    <div class="card-footer">
                        <div class="shift-evidence">
                            {evidence_html}
                        </div>
                        <div class="card-connections" title="{html_escape(connection_title)}">
                            {connection_dots}
                        </div>
                    </div>
                </div>
'''


def html_escape(text):
    """Simple HTML escape."""
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))


def generate_lifecycle_svg(signals):
    """Generate the lifecycle curve SVG with signal dots."""
    # Group signals by stage
    by_stage = {}
    for s in signals:
        by_stage.setdefault(s['stage'], []).append(s)

    # Positions for each stage region on the curve
    stage_regions = {
        'emerging': {'x_start': 90, 'x_end': 185, 'y_base': 240, 'y_step': -3, 'color': '#22C55E'},
        'accelerating': {'x_start': 245, 'x_end': 430, 'y_base': 200, 'y_step': -10, 'color': '#3B82F6'},
        'mainstream': {'x_start': 450, 'x_end': 575, 'y_base': 55, 'y_step': -4, 'color': '#F59E0B'},
        'peaking': {'x_start': 620, 'x_end': 720, 'y_base': 45, 'y_step': 14, 'color': '#EF4444'},
        'declining': {'x_start': 770, 'x_end': 810, 'y_base': 185, 'y_step': 15, 'color': '#6B7280'},
    }

    dots_svg = ''
    for stage, sigs in by_stage.items():
        if stage not in stage_regions:
            continue
        region = stage_regions[stage]
        count = len(sigs)
        if count == 0:
            continue

        x_span = region['x_end'] - region['x_start']
        x_step = x_span / max(count, 1)

        for i, sig in enumerate(sigs):
            x = region['x_start'] + i * x_step
            y = region['y_base'] + i * region['y_step']
            color = region['color']
            opacity = 0.8 if i < count // 2 + 1 else 0.6

            # Short label
            label = sig['title']
            if len(label) > 16:
                words = label.split()
                label = words[0]
                if len(words) > 1 and len(label + ' ' + words[1]) < 16:
                    label += ' ' + words[1]

            r = 5 if stage == 'declining' and count == 1 else 4
            text_y = y - 9
            if i % 2 == 1:
                text_y = y + 14

            dots_svg += f'                <circle cx="{x:.0f}" cy="{y:.0f}" r="{r}" fill="{color}" opacity="{opacity}"/>'
            dots_svg += f'<text x="{x:.0f}" y="{text_y:.0f}" fill="rgba(255,255,255,0.5)" font-size="7" text-anchor="middle">{html_escape(label)}</text>\n'

    # Legend
    legend_items = []
    for stage in STAGES:
        count = len(by_stage.get(stage, []))
        color = stage_regions.get(stage, {}).get('color', '#999')
        legend_items.append(
            f'<div style="display:flex;align-items:center;gap:6px;font-size:0.72rem;color:rgba(255,255,255,0.4);">'
            f'<span style="width:8px;height:8px;border-radius:50%;background:{color};display:inline-block;"></span> '
            f'{stage.capitalize()} ({count})</div>'
        )
    legend_html = '\n            '.join(legend_items)

    return f'''    <section class="lifecycle-section" style="max-width:1100px;margin:0 auto;padding:2rem 2rem 3rem;">
        <div style="text-align:center;margin-bottom:2rem;">
            <div style="font-family:var(--mono);font-size:0.65rem;letter-spacing:0.15em;text-transform:uppercase;color:var(--accent);margin-bottom:0.5rem;">The Curve</div>
            <h2 style="font-family:var(--heading);font-size:1.6rem;letter-spacing:-0.02em;margin-bottom:0.5rem;">Where every shift sits right now</h2>
            <p style="font-size:0.9rem;color:var(--muted);max-width:560px;margin:0 auto;line-height:1.6;">{len(signals)} shifts plotted on the adoption lifecycle. The interesting stories are at the edges -- what's just emerging, and what's starting to decline.</p>
        </div>
        <div style="position:relative;max-width:900px;margin:0 auto;overflow-x:auto;">
            <svg viewBox="0 0 900 340" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:auto;display:block;">
                <line x1="80" y1="240" x2="840" y2="240" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>
                <path d="M80,240 C160,238 200,220 280,180 C340,150 400,80 460,50 C520,30 560,28 600,40 C640,55 700,120 760,180 C800,210 830,235 840,240" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="2"/>
                <path d="M80,240 C160,238 200,220 280,180 C340,150 400,80 460,50 C520,30 560,28 600,40 C640,55 700,120 760,180 C800,210 830,235 840,240" fill="url(#curveGrad)" opacity="0.06"/>
                <defs>
                    <linearGradient id="curveGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="var(--accent, #E8564B)"/>
                        <stop offset="100%" stop-color="transparent"/>
                    </linearGradient>
                </defs>
                <text x="140" y="270" fill="rgba(255,255,255,0.3)" font-size="10" font-family="monospace" text-anchor="middle" letter-spacing="1">EMERGING</text>
                <text x="320" y="270" fill="rgba(255,255,255,0.3)" font-size="10" font-family="monospace" text-anchor="middle" letter-spacing="1">ACCELERATING</text>
                <text x="500" y="270" fill="rgba(255,255,255,0.3)" font-size="10" font-family="monospace" text-anchor="middle" letter-spacing="1">MAINSTREAM</text>
                <text x="660" y="270" fill="rgba(255,255,255,0.3)" font-size="10" font-family="monospace" text-anchor="middle" letter-spacing="1">PEAKING</text>
                <text x="800" y="270" fill="rgba(255,255,255,0.3)" font-size="10" font-family="monospace" text-anchor="middle" letter-spacing="1">DECLINING</text>
{dots_svg}
            </svg>
        </div>
        <div style="display:flex;justify-content:center;gap:2rem;margin-top:1.5rem;flex-wrap:wrap;">
            {legend_html}
        </div>
    </section>'''


def generate_sotw_data_js(signals, data):
    """Generate the sotwData JavaScript array from signals.json."""
    # Build SOTW entries — each signal gets a why + watch from its analysis field
    sotw_entries = []
    signal_meta_entries = []

    for s in signals:
        sid = s['id']
        title = s['title']
        domain = s['domain']
        stage = s['stage']
        desc = s['description']
        analysis = s.get('analysis', '')

        # For "why" — use the analysis field
        why = analysis if analysis else desc

        # For "watch" — generate a forward-looking statement
        watch = f"Watch for developments in {domain} that signal the next phase of this shift."

        # Escape for JS strings
        def js_escape(text):
            return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

        sotw_entries.append(
            f'            {{ id: "{sid}", why: "{js_escape(why)}", watch: "{js_escape(watch)}" }}'
        )
        signal_meta_entries.append(
            f'            "{sid}": {{ title: "{js_escape(title)}", domain: "{domain}", stage: "{stage}", desc: "{js_escape(desc)}" }}'
        )

    sotw_js = ',\n'.join(sotw_entries)
    meta_js = ',\n'.join(signal_meta_entries)
    signal_ids = json.dumps([s['id'] for s in signals])

    return sotw_js, meta_js, signal_ids


def generate_html(data):
    """Generate the full site HTML from signals data."""
    signals = data['signals']
    stats = calculate_stats(signals)
    edition = get_edition_label()
    edition_short = get_edition_short()
    today = get_date_iso()
    week_num = get_week_number()
    sotw = select_signal_of_the_week(signals)

    # Generate signal cards grouped by domain
    all_cards = ''
    for domain in DOMAINS:
        domain_signals = [s for s in signals if s['domain'] == domain]
        for i, sig in enumerate(domain_signals):
            comment_num = i + 1
            all_cards += f'\n                <!-- {domain.upper()} {comment_num} -->\n'
            all_cards += generate_signal_card(sig)

    # Generate lifecycle SVG
    lifecycle_svg = generate_lifecycle_svg(signals)

    # Generate Signal of the Week JS data
    sotw_js, meta_js, signal_ids_json = generate_sotw_data_js(signals, data)

    # Stage bar widths (percentage of max = total)
    total = stats['total']
    stage_bar_data = {}
    for stage in STAGES:
        count = stats['stage_counts'].get(stage, 0)
        width = round(count / total * 100) if total > 0 else 0
        stage_bar_data[stage] = {'count': count, 'width': width}

    # Build the full HTML
    # We read the existing CSS from the static file, but generate HTML content dynamically
    # For this pipeline, we read the existing index.html up to </style></head> as the CSS template,
    # then generate the body content from data.

    # Read the existing index.html to extract the full CSS
    existing_html_path = os.path.join(PROJECT_DIR, 'index.html')
    with open(existing_html_path, 'r', encoding='utf-8') as f:
        existing_html = f.read()

    # Extract everything from start to </style>\n</head>
    head_end_marker = '</style>\n</head>'
    head_end_idx = existing_html.find(head_end_marker)
    if head_end_idx == -1:
        head_end_marker = '</style></head>'
        head_end_idx = existing_html.find(head_end_marker)

    if head_end_idx >= 0:
        head_section = existing_html[:head_end_idx + len(head_end_marker)]
    else:
        log("WARNING: Could not find head section marker, using full existing HTML as fallback")
        # Fallback: just use the existing HTML
        return existing_html

    # Update dynamic parts in the head
    total_signals = stats['total']
    temporal = datetime.now(timezone.utc).strftime('%Y-%m')

    head_section = re.sub(
        r'<meta property="og:title" content="[^"]*">',
        f'<meta property="og:title" content="Signals &amp; Shifts -- {edition} Snapshot">',
        head_section
    )
    og_desc = f'{total_signals} cultural shifts across music, design, food, fashion and tech -- tracked monthly on a lifecycle curve from emerging to declining. {edition} edition.'
    head_section = re.sub(
        r'<meta property="og:description" content="[^"]*">',
        f'<meta property="og:description" content="{og_desc}">',
        head_section
    )
    head_section = re.sub(
        r'<meta name="twitter:title" content="[^"]*">',
        f'<meta name="twitter:title" content="Signals &amp; Shifts -- {edition} Snapshot">',
        head_section
    )
    head_section = re.sub(
        r'"edition": "[^"]*"',
        f'"edition": "{edition}"',
        head_section
    )
    head_section = re.sub(
        r'"datePublished": "[^"]*"',
        f'"datePublished": "{today}"',
        head_section
    )
    head_section = re.sub(
        r'"dateModified": "[^"]*"',
        f'"dateModified": "{today}"',
        head_section
    )
    head_section = re.sub(
        r'"temporalCoverage": "[^"]*"',
        f'"temporalCoverage": "{temporal}"',
        head_section
    )
    schema_desc = f'{total_signals} cultural shifts across 5 domains tracked on a lifecycle curve from emerging to declining'
    head_section = re.sub(
        r'"description": "(\d+) cultural shifts across 5 domains[^"]*"',
        f'"description": "{schema_desc}"',
        head_section
    )

    # Generate the body
    body_html = f'''<body>

    <!-- HEADER -->
    <header class="header">
        <div class="container">
            <div class="header-inner">
                <div class="header-brand">
                    <a href="/" class="header-logo">Signals <span>&amp;</span> Shifts</a>
                    <span class="header-edition">{edition_short}</span>
                </div>
                <div class="header-actions">
                    <div class="header-links">
                        <a href="#methodology">Methodology</a>
                        <a href="#about">About</a>
                        <a href="#subscribe">Subscribe</a>
                        <a href="https://culturalcapitallabs.com" target="_blank" rel="noopener">CCL</a>
                    </div>
                    <button class="theme-toggle" id="themeToggleBtn" aria-label="Toggle theme">
                        <span class="icon-moon">&#9789;</span>
                        <span class="icon-sun">&#9788;</span>
                    </button>
                </div>
            </div>
        </div>
    </header>

    <!-- HERO -->
    <section class="hero">
        <div class="container">
            <div class="hero-layout">
                <div class="hero-content">
                    <div class="hero-date"><span class="pulse"></span> {edition} Snapshot</div>
                    <h1>Tracking the slow changes that <em>reshape culture</em></h1>
                    <p class="hero-sub">Not breaking news. Not trending topics. The deeper currents that take months to surface and years to play out. Five domains, observed monthly.</p>
                </div>
                <div class="dashboard-stats">
                    <div class="dashboard-stats-title">Dashboard</div>
                    <div class="stats-grid">
                        <div class="stat-item">
                            <div class="stat-number" data-count="{stats['total']}">0</div>
                            <div class="stat-label">Shifts tracked</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number accent" data-count="{stats['domains']}">0</div>
                            <div class="stat-label">Domains</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number" data-count="{stats['accelerating']}">0</div>
                            <div class="stat-label">Accelerating</div>
                        </div>
                        <div class="stat-item">
                            <div class="stat-number" data-count="{stats['emerging']}">0</div>
                            <div class="stat-label">Emerging</div>
                        </div>
                    </div>
                    <div class="stage-distribution">
                        <div class="stage-dist-title">Stage Distribution</div>
                        <div class="stage-bars">
                            <div class="stage-bar-row">
                                <span class="stage-bar-label">Emerging</span>
                                <div class="stage-bar-track"><div class="stage-bar-fill emerging" data-width="{stage_bar_data['emerging']['width']}"></div></div>
                                <span class="stage-bar-count">{stage_bar_data['emerging']['count']}</span>
                            </div>
                            <div class="stage-bar-row">
                                <span class="stage-bar-label">Accelerating</span>
                                <div class="stage-bar-track"><div class="stage-bar-fill accelerating" data-width="{stage_bar_data['accelerating']['width']}"></div></div>
                                <span class="stage-bar-count">{stage_bar_data['accelerating']['count']}</span>
                            </div>
                            <div class="stage-bar-row">
                                <span class="stage-bar-label">Mainstream</span>
                                <div class="stage-bar-track"><div class="stage-bar-fill mainstream" data-width="{stage_bar_data['mainstream']['width']}"></div></div>
                                <span class="stage-bar-count">{stage_bar_data['mainstream']['count']}</span>
                            </div>
                            <div class="stage-bar-row">
                                <span class="stage-bar-label">Peaking</span>
                                <div class="stage-bar-track"><div class="stage-bar-fill peaking" data-width="{stage_bar_data['peaking']['width']}"></div></div>
                                <span class="stage-bar-count">{stage_bar_data['peaking']['count']}</span>
                            </div>
                            <div class="stage-bar-row">
                                <span class="stage-bar-label">Declining</span>
                                <div class="stage-bar-track"><div class="stage-bar-fill declining" data-width="{stage_bar_data['declining']['width']}"></div></div>
                                <span class="stage-bar-count">{stage_bar_data['declining']['count']}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- SIGNAL OF THE WEEK -->
    <section style="padding: 40px 24px 0; max-width: 1180px; margin: 0 auto;">
        <div class="signal-of-week" id="signalOfWeek">
            <div class="sotw-strip"></div>
            <div class="sotw-inner">
                <div class="sotw-label">Signal of the Week <span class="sotw-week-badge" id="sotwWeek">Week {week_num}</span></div>
                <div class="sotw-layout">
                    <div class="sotw-main">
                        <div class="sotw-meta">
                            <span class="shift-domain-tag" id="sotwDomain" style="background: var(--{sotw['domain']}-bg); color: var(--{sotw['domain']});">{sotw['domain'].capitalize()}</span>
                            <span class="shift-stage {sotw['stage']}" id="sotwStage">{sotw['stage'].capitalize()}</span>
                            <span class="new-badge">New</span>
                        </div>
                        <h2 class="sotw-headline" id="sotwHeadline">{html_escape(sotw['title'])}</h2>
                        <p class="sotw-description" id="sotwDescription">{html_escape(sotw['description'])}</p>
                    </div>
                    <div class="sotw-sidebar">
                        <div class="sotw-why">
                            <div class="sotw-why-label">Why this matters now</div>
                            <p id="sotwWhy">{html_escape(sotw.get('analysis', sotw['description']))}</p>
                        </div>
                        <div class="sotw-watch">
                            <div class="sotw-watch-label">What to watch</div>
                            <p id="sotwWatch">Watch for developments in {sotw['domain']} that signal the next phase of this shift.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- LIFECYCLE CURVE -->
{lifecycle_svg}

    <!-- FILTER BAR -->
    <nav class="filter-bar" id="filterBar">
        <div class="container">
            <div class="filter-bar-inner">
                <span class="filter-label">Domain</span>
                <div class="filter-group" id="domainFilters">
                    <button class="filter-btn active" data-domain="all">All<span class="btn-count">{stats['total']}</span></button>'''

    for domain in DOMAINS:
        count = stats['domain_counts'].get(domain, 0)
        body_html += f'''
                    <button class="filter-btn" data-domain="{domain}">{domain.capitalize()}<span class="btn-count">{count}</span></button>'''

    body_html += f'''
                </div>
                <div class="filter-divider"></div>
                <span class="filter-label">Stage</span>
                <div class="filter-group" id="stageFilters">
                    <button class="filter-btn active" data-stage="all">All</button>'''

    for stage in STAGES:
        body_html += f'''
                    <button class="filter-btn" data-stage="{stage}">{stage.capitalize()}</button>'''

    body_html += f'''
                </div>
                <span class="results-count" id="resultsCount">{stats['total']} shifts</span>
            </div>
        </div>
    </nav>

    <!-- MAIN CONTENT -->
    <main class="main-content">
        <div class="container">

            <div class="shifts-grid" id="shiftsGrid">
{all_cards}
            </div>

            <!-- Cross-domain insight -->
            <div class="cross-domain-insight" id="crossDomainInsight">
                <div class="cdi-label">Cross-Domain Pattern</div>
                <h3 class="cdi-headline">AI is simultaneously the most accelerating force in culture and the catalyst for counter-movements everywhere</h3>
                <p class="cdi-body">AI-generated music, AI design tools, and AI agents are all accelerating. But at the same time, vinyl sales are climbing, craft and tactile design are returning, and the anti-phone movement is growing. The pattern: every acceleration creates its own backlash. The winners are the ones who understand both sides of the tension.</p>
                <div class="cdi-domains">
                    <span class="cdi-domain-pill music">Music</span>
                    <span class="cdi-domain-pill design">Design</span>
                    <span class="cdi-domain-pill tech">Tech</span>
                    <span class="cdi-domain-pill fashion">Fashion</span>
                </div>
            </div>

            <!-- No results state -->
            <div class="no-results" id="noResults">
                <div class="no-results-icon">&#8709;</div>
                <h3>No shifts match these filters</h3>
                <p>Try adjusting your domain or stage filters to see results.</p>
            </div>

            <!-- How We Track -->
            <div class="how-we-track" id="methodology">
                <div class="hwt-header">
                    <div class="hwt-label">Methodology</div>
                    <h3 class="hwt-title">How We Track</h3>
                    <p class="hwt-subtitle">Signals &amp; Shifts uses a consistent framework to identify, classify, and stage cultural movements across five domains.</p>
                </div>

                <div class="hwt-grid">
                    <div class="hwt-block">
                        <h4>What is a signal?</h4>
                        <p>A signal is an early indicator of change -- a data point, behaviour, product launch, or cultural moment that suggests something is moving. Signals are evidence. A single restaurant opening is a signal. Three restaurant openings in the same format is a pattern.</p>
                    </div>
                    <div class="hwt-block">
                        <h4>What is a shift?</h4>
                        <p>A shift is the larger movement that multiple signals point towards. When enough signals align in the same direction, they form a shift -- a genuine change in how people behave, consume, or create. Shifts take months to form and years to fully play out.</p>
                    </div>
                    <div class="hwt-block">
                        <h4>How signals are identified</h4>
                        <p>A combination of media scanning (200+ sources), social listening, industry trend reports, market data, and editorial judgment. The goal is pattern recognition -- finding the thread that connects seemingly unrelated data points across different domains.</p>
                    </div>
                    <div class="hwt-block">
                        <h4>Cross-domain connections</h4>
                        <p>The most interesting insights come from connections between domains. When the same underlying force appears in music, food, and fashion simultaneously, that's a deeper cultural current. Every shift is mapped for cross-domain connections.</p>
                    </div>
                </div>

                <div class="hwt-stages">
                    <div class="hwt-stage-item">
                        <div class="hwt-stage-dot"></div>
                        <div class="hwt-stage-name">Emerging</div>
                        <div class="hwt-stage-desc">Early signals. Niche audiences. Not yet visible to mainstream.</div>
                    </div>
                    <div class="hwt-stage-item">
                        <div class="hwt-stage-dot"></div>
                        <div class="hwt-stage-name">Accelerating</div>
                        <div class="hwt-stage-desc">Growing fast. Media coverage increasing. Early adopters engaged.</div>
                    </div>
                    <div class="hwt-stage-item">
                        <div class="hwt-stage-dot"></div>
                        <div class="hwt-stage-name">Mainstream</div>
                        <div class="hwt-stage-desc">Widely adopted. Established market presence. Known to general public.</div>
                    </div>
                    <div class="hwt-stage-item">
                        <div class="hwt-stage-dot"></div>
                        <div class="hwt-stage-name">Peaking</div>
                        <div class="hwt-stage-desc">Maximum saturation. Counter-movements forming. Losing novelty.</div>
                    </div>
                    <div class="hwt-stage-item">
                        <div class="hwt-stage-dot"></div>
                        <div class="hwt-stage-name">Declining</div>
                        <div class="hwt-stage-desc">Fading relevance. Being replaced or absorbed. Historical interest.</div>
                    </div>
                </div>

                <div class="hwt-footer">
                    <div class="hwt-footer-note"><strong>Signals updated weekly.</strong> Stages reassessed quarterly.</div>
                    <div class="hwt-footer-note">{stats['total']} shifts tracked across {stats['domains']} domains -- {edition}</div>
                </div>
            </div>

            <!-- Submit a Signal -->
            <div class="submit-signal" id="submitSignal">
                <div class="submit-signal-header">
                    <div class="submit-signal-label">Contribute</div>
                    <h3 class="submit-signal-title">Submit a Signal</h3>
                    <p class="submit-signal-subtitle">Spotted something we're missing? We're always looking for emerging signals across music, design, food, fashion, and tech.</p>
                </div>
                <form class="submit-form" id="submitSignalForm">
                    <div>
                        <label for="signalTitle">Signal Title</label>
                        <input type="text" id="signalTitle" name="signalTitle" placeholder="e.g. 'Dumbphones as fashion accessory'" required>
                    </div>
                    <div>
                        <label for="signalDomain">Domain</label>
                        <select id="signalDomain" name="signalDomain" required>
                            <option value="" disabled selected>Select a domain</option>
                            <option value="music">Music</option>
                            <option value="design">Design</option>
                            <option value="food">Food</option>
                            <option value="fashion">Fashion</option>
                            <option value="tech">Tech</option>
                        </select>
                    </div>
                    <div class="full-width">
                        <label for="signalWhy">Why It Matters</label>
                        <textarea id="signalWhy" name="signalWhy" placeholder="What are you seeing? Why does this signal matter? What evidence do you have?" rows="3" required></textarea>
                    </div>
                    <div>
                        <button type="submit" class="submit-btn" id="submitSignalBtn">Submit Signal</button>
                    </div>
                    <p class="submit-note">Submissions are reviewed for inclusion in future editions.</p>
                </form>
            </div>

            <!-- Previous Editions -->
            <div class="archive-section" id="archive">
                <div class="archive-label">Previous Editions</div>
                <div class="archive-list">
                    <div class="archive-item active">
                        <div class="archive-item-left">
                            <span class="archive-item-date">{edition}</span>
                            <span class="archive-badge current">Current Edition</span>
                        </div>
                        <span class="archive-item-count">{stats['total']} shifts</span>
                    </div>
                    <div class="archive-item disabled">
                        <div class="archive-item-left">
                            <span class="archive-item-date">March 2026</span>
                            <span class="archive-badge coming-soon">Launch Edition</span>
                        </div>
                        <span class="archive-item-count">40</span>
                    </div>
                </div>
            </div>

        </div>
    </main>

    <!-- FEATURED INSIGHT -->
    <section class="featured-insight">
        <div class="container">
            <div class="insight-inner">
                <div class="insight-label">The {edition.split()[0]} Shift</div>
                <blockquote class="insight-quote">
                    "The creator economy is splitting in two. On one side: AI-powered volume. On the other: human-curated taste. The winners will be the ones who know which side they're on."
                </blockquote>
                <p class="insight-attribution">-- Signals &amp; Shifts Analysis, {edition}</p>
            </div>
        </div>
    </section>

    <!-- ABOUT -->
    <section class="about" id="about">
        <div class="container">
            <div class="about-grid">
                <div class="about-block">
                    <h3>About this project</h3>
                    <p><strong>Signals &amp; Shifts</strong> is a weekly culture tracker. It captures the bigger picture -- the shifts that take months to play out, not the stories that trend for a day.</p>
                    <p>Five domains. {stats['total']} shifts. Updated weekly. Each shift is placed on a lifecycle curve from emerging to declining, so you can see not just what's happening, but where it's heading.</p>
                    <p>Built by <a href="https://mikelitman.me" target="_blank" rel="noopener">Mike Litman</a> at <a href="https://culturalcapitallabs.com" target="_blank" rel="noopener">Cultural Capital Labs</a>.</p>
                </div>
                <div class="about-block">
                    <h3>Methodology</h3>
                    <div class="methodology-list">
                        <div class="method-item">
                            <div class="method-icon">&#9673;</div>
                            <div class="method-text">
                                <strong>Signal detection</strong>
                                Scanning hundreds of sources across each domain for early indicators of change.
                            </div>
                        </div>
                        <div class="method-item">
                            <div class="method-icon">&#9670;</div>
                            <div class="method-text">
                                <strong>Pattern matching</strong>
                                Identifying when multiple signals point in the same direction -- the difference between noise and a shift.
                            </div>
                        </div>
                        <div class="method-item">
                            <div class="method-icon">&#9711;</div>
                            <div class="method-text">
                                <strong>Lifecycle staging</strong>
                                Placing each shift on a curve from emerging to declining based on market data, cultural saturation, and momentum.
                            </div>
                        </div>
                        <div class="method-item">
                            <div class="method-icon">&#10042;</div>
                            <div class="method-text">
                                <strong>Cross-domain mapping</strong>
                                Drawing connections between shifts in different domains to reveal deeper patterns.
                            </div>
                        </div>
                    </div>
                </div>
                <div class="about-block">
                    <h3>Ecosystem</h3>
                    <ul class="ecosystem-list">
                        <li>
                            <a href="https://cultureterminal.com" target="_blank" rel="noopener">CultureTerminal</a>
                            <span class="ecosystem-arrow">Daily signals</span>
                        </li>
                        <li>
                            <a href="https://therelevanceindex.com" target="_blank" rel="noopener">The Relevance Index</a>
                            <span class="ecosystem-arrow">Brand scoring</span>
                        </li>
                        <li>
                            <a href="https://thepattern.media" target="_blank" rel="noopener">The Pattern</a>
                            <span class="ecosystem-arrow">Culture intelligence</span>
                        </li>
                        <li>
                            <a href="https://culturalcapitallabs.com" target="_blank" rel="noopener">Cultural Capital Labs</a>
                            <span class="ecosystem-arrow">The studio</span>
                        </li>
                    </ul>
                </div>
            </div>
        </div>
    </section>

    <!-- SUBSCRIBE -->
    <section class="subscribe" id="subscribe">
        <div class="container">
            <div class="subscribe-inner">
                <h3>Get the weekly snapshot</h3>
                <p>Signals &amp; Shifts delivered to your inbox once a week. No noise, just the patterns that take time to see.</p>
                <form class="subscribe-form" action="https://buttondown.com/api/emails/embed-subscribe/signalsandshifts" method="post" target="_blank">
                    <input type="email" name="email" placeholder="you@example.com" required>
                    <button type="submit">Subscribe</button>
                </form>
                <p class="subscribe-note">Weekly. Free. Unsubscribe anytime.</p>
            </div>
        </div>
    </section>

    <!-- FOOTER -->
    <footer class="footer">
        <div class="container">
            <div class="footer-inner">
                <div class="footer-left">
                    Signals &amp; Shifts {datetime.now(timezone.utc).year} &middot; A <a href="https://culturalcapitallabs.com" target="_blank" rel="noopener">Cultural Capital Labs</a> project
                </div>
                <div class="footer-right">
                    <a href="https://cultureterminal.com" target="_blank" rel="noopener">CultureTerminal</a>
                    <a href="https://therelevanceindex.com" target="_blank" rel="noopener">Relevance Index</a>
                    <a href="https://mikelitman.me" target="_blank" rel="noopener">mikelitman.me</a>
                </div>
            </div>
        </div>
    </footer>

    <!-- Scroll to top -->
    <button class="scroll-top" id="scrollTop" aria-label="Scroll to top">&#8593;</button>

    <!-- Theme toggle script (separate for resilience) -->
    <script>
    window.toggleTheme = function() {{
        var html = document.documentElement;
        var current = html.getAttribute('data-theme');
        var next = current === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-theme', next);
        try {{ localStorage.setItem('ss-theme', next); }} catch(e) {{}}
    }};
    try {{
        var saved = localStorage.getItem('ss-theme');
        if (saved) document.documentElement.setAttribute('data-theme', saved);
    }} catch(e) {{}}
    var _themeBtn = document.getElementById('themeToggleBtn');
    if (_themeBtn) _themeBtn.addEventListener('click', function() {{ toggleTheme(); }});
    </script>

    <!-- Animated counters and bars (separate for resilience) -->
    <script>
    (function() {{
        function animateCounters() {{
            document.querySelectorAll('[data-count]').forEach(function(el) {{
                var target = parseInt(el.dataset.count);
                var duration = 1200;
                var start = performance.now();
                function tick(now) {{
                    var elapsed = now - start;
                    var progress = Math.min(elapsed / duration, 1);
                    var eased = 1 - Math.pow(1 - progress, 3);
                    el.textContent = Math.round(target * eased);
                    if (progress < 1) requestAnimationFrame(tick);
                }}
                requestAnimationFrame(tick);
            }});
        }}
        function animateBars() {{
            document.querySelectorAll('.stage-bar-fill').forEach(function(bar) {{
                var width = bar.dataset.width;
                setTimeout(function() {{ bar.style.width = width + '%'; }}, 300);
            }});
        }}
        animateCounters();
        animateBars();
    }})();
    </script>

    <!-- Filtering system (separate for resilience) -->
    <script>
    (function() {{
        var activeDomain = 'all';
        var activeStage = 'all';
        var domainBtns = document.querySelectorAll('#domainFilters .filter-btn');
        var stageBtns = document.querySelectorAll('#stageFilters .filter-btn');
        var cards = document.querySelectorAll('.shift-card');
        var grid = document.getElementById('shiftsGrid');
        var noResults = document.getElementById('noResults');
        var resultsCount = document.getElementById('resultsCount');
        var crossInsight = document.getElementById('crossDomainInsight');

        function applyFilters() {{
            var visible = 0;
            var delay = 0;
            cards.forEach(function(card) {{
                var matchDomain = activeDomain === 'all' || card.dataset.domain === activeDomain;
                var matchStage = activeStage === 'all' || card.dataset.stage === activeStage;
                if (matchDomain && matchStage) {{
                    card.classList.remove('filtered-out');
                    card.classList.add('entering');
                    card.style.animationDelay = (delay * 50) + 'ms';
                    setTimeout(function() {{ card.classList.remove('entering'); }}, 400 + delay * 50);
                    visible++;
                    delay++;
                }} else {{
                    card.classList.add('filtered-out');
                    card.classList.remove('entering');
                }}
            }});
            resultsCount.textContent = visible + (visible === 1 ? ' shift' : ' shifts');
            noResults.classList.toggle('visible', visible === 0);
            grid.style.display = visible === 0 ? 'none' : '';
            if (crossInsight) {{
                crossInsight.style.display = (activeDomain === 'all' && activeStage === 'all') ? '' : 'none';
            }}
            document.querySelectorAll('#shiftsGrid > div[style*="border-left"]').forEach(function(quote) {{
                quote.style.display = (activeDomain === 'all' && activeStage === 'all') ? '' : 'none';
            }});
        }}

        domainBtns.forEach(function(btn) {{
            btn.addEventListener('click', function() {{
                domainBtns.forEach(function(b) {{ b.classList.remove('active'); }});
                btn.classList.add('active');
                activeDomain = btn.dataset.domain;
                applyFilters();
            }});
        }});

        stageBtns.forEach(function(btn) {{
            btn.addEventListener('click', function() {{
                stageBtns.forEach(function(b) {{ b.classList.remove('active'); }});
                btn.classList.add('active');
                activeStage = btn.dataset.stage;
                applyFilters();
            }});
        }});

        var scrollBtn = document.getElementById('scrollTop');
        var ticking = false;
        window.addEventListener('scroll', function() {{
            if (!ticking) {{
                requestAnimationFrame(function() {{
                    scrollBtn.classList.toggle('visible', window.scrollY > 600);
                    ticking = false;
                }});
                ticking = true;
            }}
        }});

        document.addEventListener('keydown', function(e) {{
            if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
            if (e.key === 'd' && !e.ctrlKey && !e.metaKey) {{ toggleTheme(); }}
            var domainMap = {{ '1': 'all', '2': 'music', '3': 'design', '4': 'food', '5': 'fashion', '6': 'tech' }};
            if (domainMap[e.key] && !e.ctrlKey && !e.metaKey) {{
                activeDomain = domainMap[e.key];
                domainBtns.forEach(function(b) {{
                    b.classList.toggle('active', b.dataset.domain === activeDomain);
                }});
                applyFilters();
            }}
        }});

        if ('IntersectionObserver' in window) {{
            var observer = new IntersectionObserver(function(entries) {{
                entries.forEach(function(entry) {{
                    if (entry.isIntersecting) {{
                        entry.target.classList.add('entering');
                        setTimeout(function() {{ entry.target.classList.remove('entering'); }}, 400);
                        observer.unobserve(entry.target);
                    }}
                }});
            }}, {{ threshold: 0.1 }});
            cards.forEach(function(card) {{ observer.observe(card); }});
        }}
    }})();
    </script>

    <!-- Signal of the Week rotation (separate for resilience) -->
    <script>
    (function() {{
        var sotwData = [
{sotw_js}
        ];

        var now = new Date();
        var startOfYear = new Date(now.getFullYear(), 0, 1);
        var weekNum = Math.ceil(((now - startOfYear) / 86400000 + startOfYear.getDay() + 1) / 7);
        var sotwIndex = weekNum % sotwData.length;
        var featured = sotwData[sotwIndex];

        var signalMeta = {{
{meta_js}
        }};

        var domainColors = {{
            music: {{ bg: 'var(--music-bg)', color: 'var(--music)' }},
            design: {{ bg: 'var(--design-bg)', color: 'var(--design)' }},
            food: {{ bg: 'var(--food-bg)', color: 'var(--food)' }},
            fashion: {{ bg: 'var(--fashion-bg)', color: 'var(--fashion)' }},
            tech: {{ bg: 'var(--tech-bg)', color: 'var(--tech)' }}
        }};

        var meta = signalMeta[featured.id];
        if (meta) {{
            var dc = domainColors[meta.domain] || domainColors.tech;
            var weekBadge = document.getElementById('sotwWeek');
            var domainTag = document.getElementById('sotwDomain');
            var stageTag = document.getElementById('sotwStage');
            var headline = document.getElementById('sotwHeadline');
            var desc = document.getElementById('sotwDescription');
            var whyEl = document.getElementById('sotwWhy');
            var watchEl = document.getElementById('sotwWatch');

            if (weekBadge) weekBadge.textContent = 'Week ' + weekNum;
            if (domainTag) {{
                domainTag.textContent = meta.domain.charAt(0).toUpperCase() + meta.domain.slice(1);
                domainTag.style.background = dc.bg;
                domainTag.style.color = dc.color;
            }}
            if (stageTag) {{
                stageTag.textContent = meta.stage.charAt(0).toUpperCase() + meta.stage.slice(1);
                stageTag.className = 'shift-stage ' + meta.stage;
            }}
            if (headline) headline.textContent = meta.title;
            if (desc) desc.textContent = meta.desc;
            if (whyEl) whyEl.textContent = featured.why;
            if (watchEl) watchEl.textContent = featured.watch;
        }}
    }})();
    </script>

    <!-- Voting system (separate for resilience) -->
    <script>
    (function() {{
        var STORAGE_KEY = 'signals-shifts-votes';
        var signalIds = {signal_ids_json};

        function seededRandom(seed) {{
            var x = Math.sin(seed) * 10000;
            return x - Math.floor(x);
        }}

        function getVotes() {{
            try {{
                var data = localStorage.getItem(STORAGE_KEY);
                return data ? JSON.parse(data) : {{}};
            }} catch(e) {{ return {{}}; }}
        }}

        function saveVotes(data) {{
            try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); }} catch(e) {{}}
        }}

        function getSimulatedCounts(signalId) {{
            var hash = 0;
            for (var i = 0; i < signalId.length; i++) {{
                hash = ((hash << 5) - hash) + signalId.charCodeAt(i);
                hash |= 0;
            }}
            var base = Math.floor(seededRandom(hash) * 30) + 8;
            var early = Math.floor(seededRandom(hash + 1) * base * 0.3);
            var late = Math.floor(seededRandom(hash + 2) * base * 0.2);
            var right = base - early - late;
            if (right < 0) right = 0;
            return {{ early: early, right: right, late: late, total: base }};
        }}

        function getConsensus(counts) {{
            if (counts.right >= counts.early && counts.right >= counts.late) return 'About right';
            if (counts.early > counts.late) return 'Too early';
            return 'Too late';
        }}

        var cards = document.querySelectorAll('.shift-card');
        var votes = getVotes();

        cards.forEach(function(card, index) {{
            if (index >= signalIds.length) return;
            var signalId = signalIds[index];
            card.setAttribute('data-signal-id', signalId);

            var topLeft = card.querySelector('.shift-card-top-left');
            if (topLeft) {{
                var badge = document.createElement('span');
                badge.className = 'new-badge';
                badge.textContent = 'New';
                topLeft.appendChild(badge);
            }}

            var simCounts = getSimulatedCounts(signalId);
            var userVote = votes[signalId];

            if (userVote) {{
                if (userVote === 'early') simCounts.early++;
                else if (userVote === 'right') simCounts.right++;
                else if (userVote === 'late') simCounts.late++;
                simCounts.total++;
            }}

            var voteBar = document.createElement('div');
            voteBar.className = 'vote-bar';

            var label = document.createElement('span');
            label.className = 'vote-label';
            label.textContent = 'Stage:';

            var btnEarly = document.createElement('button');
            btnEarly.className = 'vote-btn' + (userVote === 'early' ? ' voted' : '');
            btnEarly.textContent = 'Too early';
            btnEarly.setAttribute('data-vote', 'early');

            var btnRight = document.createElement('button');
            btnRight.className = 'vote-btn' + (userVote === 'right' ? ' voted' : '');
            btnRight.textContent = 'About right';
            btnRight.setAttribute('data-vote', 'right');

            var btnLate = document.createElement('button');
            btnLate.className = 'vote-btn' + (userVote === 'late' ? ' voted' : '');
            btnLate.textContent = 'Too late';
            btnLate.setAttribute('data-vote', 'late');

            var count = document.createElement('span');
            count.className = 'vote-count';
            count.textContent = simCounts.total + ' voted';

            var consensus = document.createElement('span');
            consensus.className = 'vote-consensus';
            consensus.textContent = getConsensus(simCounts);

            voteBar.appendChild(label);
            voteBar.appendChild(btnEarly);
            voteBar.appendChild(btnRight);
            voteBar.appendChild(btnLate);
            voteBar.appendChild(count);
            voteBar.appendChild(consensus);

            var footer = card.querySelector('.card-footer');
            if (footer) {{
                footer.parentNode.insertBefore(voteBar, footer.nextSibling);
            }}

            var btns = [btnEarly, btnRight, btnLate];
            btns.forEach(function(btn) {{
                btn.addEventListener('click', function() {{
                    var voteVal = btn.getAttribute('data-vote');
                    var currentVotes = getVotes();
                    if (currentVotes[signalId] === voteVal) return;
                    var wasVoted = currentVotes[signalId];
                    var freshCounts = getSimulatedCounts(signalId);
                    if (wasVoted) {{
                        freshCounts[wasVoted === 'early' ? 'early' : wasVoted === 'right' ? 'right' : 'late']++;
                        freshCounts.total++;
                    }}
                    if (wasVoted) {{
                        freshCounts[wasVoted === 'early' ? 'early' : wasVoted === 'right' ? 'right' : 'late']--;
                        freshCounts.total--;
                    }}
                    freshCounts[voteVal === 'early' ? 'early' : voteVal === 'right' ? 'right' : 'late']++;
                    freshCounts.total++;
                    currentVotes[signalId] = voteVal;
                    saveVotes(currentVotes);
                    btns.forEach(function(b) {{ b.classList.remove('voted'); }});
                    btn.classList.add('voted');
                    count.textContent = freshCounts.total + ' voted';
                    consensus.textContent = getConsensus(freshCounts);
                }});
            }});
        }});
    }})();
    </script>

    <!-- Submit signal form (separate for resilience) -->
    <script>
    (function() {{
        var form = document.getElementById('submitSignalForm');
        if (!form) return;
        form.addEventListener('submit', function(e) {{
            e.preventDefault();
            var title = document.getElementById('signalTitle').value.trim();
            var domain = document.getElementById('signalDomain').value;
            var why = document.getElementById('signalWhy').value.trim();
            if (!title || !domain || !why) return;
            try {{
                var submissions = JSON.parse(localStorage.getItem('signals-shifts-submissions') || '[]');
                submissions.push({{ title: title, domain: domain, why: why, date: new Date().toISOString() }});
                localStorage.setItem('signals-shifts-submissions', JSON.stringify(submissions));
            }} catch(ex) {{}}
            var btn = document.getElementById('submitSignalBtn');
            btn.textContent = 'Submitted!';
            btn.classList.add('submitted');
            setTimeout(function() {{
                form.reset();
                btn.textContent = 'Submit Signal';
                btn.classList.remove('submitted');
            }}, 3000);
        }});
    }})();
    </script>

    <!-- Scroll to top (separate for resilience) -->
    <script>
    (function() {{
        var scrollBtn = document.getElementById('scrollTop');
        if (!scrollBtn) return;
        scrollBtn.addEventListener('click', function() {{
            window.scrollTo({{ top: 0, behavior: 'smooth' }});
        }});
    }})();
    </script>

</body>
</html>'''

    full_html = head_section + '\n' + body_html
    return full_html


# ── DEPLOY ──────────────────────────────────────────────────────────────────

def sha1_file(filepath):
    """Calculate SHA1 hash of a file."""
    h = hashlib.sha1()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()


def sha1_bytes(data):
    """Calculate SHA1 hash of bytes."""
    return hashlib.sha1(data).hexdigest()


def collect_deploy_files(deploy_dir):
    """Collect all files in deploy directory with their SHA1 hashes."""
    files = {}
    for root, dirs, filenames in os.walk(deploy_dir):
        for fname in filenames:
            filepath = os.path.join(root, fname)
            rel_path = '/' + os.path.relpath(filepath, deploy_dir)
            sha = sha1_file(filepath)
            files[rel_path] = {'sha': sha, 'path': filepath}
    return files


def api_request(method, path, data=None, content_type='application/json'):
    """Make a Netlify API request."""
    url = f'{API_BASE}{path}'
    headers = {
        'Authorization': f'Bearer {AUTH_TOKEN}',
        'Content-Type': content_type,
    }
    if data is not None and content_type == 'application/json':
        body = json.dumps(data).encode('utf-8')
    elif data is not None:
        body = data
    else:
        body = None

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        log(f"HTTP {e.code}: {error_body[:500]}")
        raise


def get_content_type(filepath):
    """Get content type for a file."""
    ext_map = {
        '.html': 'text/html',
        '.json': 'application/octet-stream',
        '.js': 'application/javascript',
        '.css': 'text/css',
        '.xml': 'application/xml',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.svg': 'image/svg+xml',
        '.webp': 'image/webp',
        '.txt': 'text/plain',
        '.ico': 'image/x-icon',
    }
    _, ext = os.path.splitext(filepath)
    return ext_map.get(ext.lower(), 'application/octet-stream')


def deploy_to_netlify(deploy_dir):
    """Deploy the deploy directory to Netlify using REST API."""
    log("Collecting deploy files...")
    files = collect_deploy_files(deploy_dir)
    file_manifest = {path: info['sha'] for path, info in files.items()}
    log(f"Found {len(files)} files to deploy")

    log("Creating deploy...")
    deploy_data = {'files': file_manifest}
    deploy = api_request('POST', f'/sites/{SITE_ID}/deploys', deploy_data)
    deploy_id = deploy['id']
    required = deploy.get('required', [])
    log(f"Deploy ID: {deploy_id}")
    log(f"Files to upload: {len(required)} of {len(files)}")

    if required:
        # Build SHA -> file path lookup
        sha_to_info = {}
        for path, info in files.items():
            if info['sha'] in required:
                sha_to_info[info['sha']] = (info['path'], path)

        uploaded = 0
        for sha in required:
            if sha not in sha_to_info:
                log(f"  Warning: SHA {sha} not found locally, skipping")
                continue

            filepath, rel_path = sha_to_info[sha]
            with open(filepath, 'rb') as f:
                file_data = f.read()

            ct = get_content_type(filepath)
            try:
                api_request('PUT', f'/deploys/{deploy_id}/files{rel_path}', file_data, ct)
                uploaded += 1
                if uploaded % 10 == 0 or uploaded == len(required):
                    log(f"  Uploaded {uploaded}/{len(required)} files")
            except Exception as e:
                log(f"  Error uploading {rel_path}: {e}")

        log(f"Uploaded {uploaded} files")

    # Wait for deploy to be ready
    log("Checking deploy status...")
    for attempt in range(10):
        time.sleep(3)
        status = api_request('GET', f'/deploys/{deploy_id}')
        state = status.get('state', 'unknown')
        log(f"  Status: {state}")
        if state == 'ready':
            url = status.get('ssl_url', status.get('url', 'unknown'))
            log(f"Deploy successful: {url}")
            return True, url
        elif state in ('error', 'failed'):
            log(f"Deploy failed: {status.get('error_message', 'unknown error')}")
            return False, None

    log("Deploy still processing after 30 seconds")
    return False, None


# ── NOTIFICATIONS ───────────────────────────────────────────────────────────

def send_notification(title, message):
    """Send ntfy notification."""
    try:
        data = message.encode('utf-8')
        req = urllib.request.Request(
            f'https://ntfy.sh/{NTFY_TOPIC}',
            data=data,
            headers={
                'Title': title,
                'Priority': '3',
                'Tags': 'signal,chart_with_upwards_trend',
            },
            method='POST'
        )
        urllib.request.urlopen(req, timeout=10)
        log(f"Notification sent to {NTFY_TOPIC}")
    except Exception as e:
        log(f"Failed to send notification: {e}")


# ── MAIN PIPELINE ───────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("Signals & Shifts Pipeline v1")
    log("=" * 60)

    # Step 1: Load signals
    log("\n--- Loading signals ---")
    data = load_signals()
    signals = data['signals']
    log(f"Loaded {len(signals)} signals across {len(set(s['domain'] for s in signals))} domains")

    # Step 2: Update freshness
    log("\n--- Updating freshness ---")
    data = update_freshness(data)

    # Step 3: Select Signal of the Week
    sotw = select_signal_of_the_week(signals)
    log(f"Signal of the Week: {sotw['title']} ({sotw['domain']}/{sotw['stage']})")

    # Step 4: Calculate stats
    stats = calculate_stats(signals)
    log(f"Stats: {stats['total']} signals, {stats['accelerating']} accelerating, {stats['emerging']} emerging")

    # Step 5: Save updated signals.json
    log("\n--- Saving updates ---")
    save_signals(data)

    # Step 6: Generate HTML
    log("\n--- Generating HTML ---")
    html = generate_html(data)
    log(f"Generated {len(html):,} characters of HTML")

    # Step 7: Prepare deploy directory
    log("\n--- Preparing deploy ---")
    os.makedirs(DEPLOY_DIR, exist_ok=True)

    # Write index.html
    deploy_html = os.path.join(DEPLOY_DIR, 'index.html')
    with open(deploy_html, 'w', encoding='utf-8') as f:
        f.write(html)
    log(f"Written {os.path.getsize(deploy_html):,} bytes to deploy/index.html")

    # Copy signals.json to deploy
    deploy_json = os.path.join(DEPLOY_DIR, 'signals.json')
    shutil.copy2(SIGNALS_FILE, deploy_json)
    log("Copied signals.json to deploy/")

    # Preserve archive directory if it exists
    archive_src = os.path.join(PROJECT_DIR, 'deploy', 'archive')
    if os.path.isdir(archive_src):
        log("Archive directory preserved in deploy/")

    # Step 8: Deploy to Netlify
    log("\n--- Deploying to Netlify ---")
    success, url = deploy_to_netlify(DEPLOY_DIR)

    # Step 9: Send notification
    log("\n--- Sending notification ---")
    edition = get_edition_label()
    if success:
        ntfy_total = stats['total']
        ntfy_sotw = sotw['title']
        send_notification(
            'Signals & Shifts updated',
            f'{edition} edition deployed.\n'
            f'{ntfy_total} signals | SOTW: {ntfy_sotw}\n'
            f'{url}'
        )
    else:
        send_notification(
            'Signals & Shifts deploy FAILED',
            f'Pipeline ran but deploy failed. Check logs.'
        )

    log("\n" + "=" * 60)
    log("Pipeline complete" + (" (deployed)" if success else " (deploy failed)"))
    log("=" * 60)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

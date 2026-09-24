#!/usr/bin/env python3
"""Generate self-hosted neon profile stat cards for the NeonBhoot profile README.

Reads the GitHub API (REST + GraphQL) and renders SVG cards directly into
the repo's assets/ directory -- no third-party image services involved.

Env:
  STATS_TOKEN   personal token (includes private contributions); optional
  GITHUB_TOKEN  fallback token (public data only)
  PROFILE_USER  GitHub username (default: NeonBhoot)
  OUT_DIR       output directory (default: assets)

Writes: stats-dark.svg, stats-light.svg, streak-dark.svg, streak-light.svg,
        top-langs-dark.svg, top-langs-light.svg, activity-dark.svg,
        activity-light.svg
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"
USER = os.environ.get("PROFILE_USER", "NeonBhoot")
OUT = os.environ.get("OUT_DIR", "assets")
TOKEN = os.environ.get("STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
PRIVATE_OK = bool(os.environ.get("STATS_TOKEN"))

THEMES = {
    "dark": {
        "bg": "#0B0B12", "border": "#1E4D3A", "title": "#39FF8F",
        "text": "#E6EDF3", "muted": "#8B949E", "track": "#1C2330",
        "accent": "#34E0FF", "accent2": "#39FF8F", "grid": "#1C2330",
    },
    "light": {
        "bg": "#FFFFFF", "border": "#D0D7DE", "title": "#0A7A4E",
        "text": "#1F2328", "muted": "#57606A", "track": "#EAEEF2",
        "accent": "#0969DA", "accent2": "#0A7A4E", "grid": "#EAEEF2",
    },
}

LANG_COLORS = {
    "Kotlin": "#A97BFF", "Java": "#B07219", "TypeScript": "#3178C6",
    "JavaScript": "#F1E05A", "Dart": "#00B4AB", "HTML": "#E34C26",
    "CSS": "#563D7C", "Python": "#3572A5", "Shell": "#89E051",
    "C++": "#F34B7D", "C": "#555555", "Go": "#00ADD8", "Rust": "#DEA584",
    "PHP": "#4F5D95", "Ruby": "#701516", "Swift": "#F05138",
    "Vue": "#41B883", "SCSS": "#C6538C", "Dockerfile": "#384D54",
    "PowerShell": "#012456", "Jupyter Notebook": "#DA5B0B",
}

FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def http(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "neonbhoot-profile-stats")
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        raise RuntimeError("HTTP %s for %s: %s" % (e.code, url, detail))


def paged_get(url):
    """GET with Link-header pagination; returns concatenated list items."""
    items = []
    while url:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "neonbhoot-profile-stats")
        if TOKEN:
            req.add_header("Authorization", "Bearer " + TOKEN)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode()
                link = resp.headers.get("Link", "")
        except urllib.error.HTTPError as e:
            raise RuntimeError("HTTP %s for %s: %s" % (e.code, url, e.read().decode()[:200]))
        data = json.loads(body)
        items += data if isinstance(data, list) else [data]
        nxt = None
        for part in link.split(","):
            if 'rel="next"' in part:
                nxt = part[part.find("<") + 1:part.find(">")]
        url = nxt
    return items


def search_count(query):
    import urllib.parse
    data = http("GET", API + "/search/issues?q=" + urllib.parse.quote(query) +
                "&per_page=1")
    return data.get("total_count", 0)


def fetch_all():
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=365)
    since_s = since.strftime("%Y-%m-%d")

    repos = paged_get(API + "/user/repos?per_page=100")
    owned = [r for r in repos if not r.get("fork")]
    stars = sum(r.get("stargazers_count", 0) for r in owned)

    lang_bytes = {}
    commit_dates = []
    for r in owned:
        full = r["full_name"]
        try:
            langs = http("GET", r["languages_url"])
        except RuntimeError:
            langs = {}
        for lang, b in langs.items():
            lang_bytes[lang] = lang_bytes.get(lang, 0) + b
        try:
            commits = paged_get(
                API + "/repos/%s/commits?author=%s&since=%sT00:00:00Z&per_page=100"
                % (full, USER, since_s))
        except RuntimeError:
            commits = []
        for c in commits:
            dt = ((c.get("commit") or {}).get("author") or {}).get("date", "")
            if dt >= since_s:
                commit_dates.append(dt[:10])
    total_bytes = sum(lang_bytes.values()) or 1
    top_langs = sorted(lang_bytes.items(), key=lambda kv: kv[1], reverse=True)[:8]
    top_langs = [(l, b / total_bytes * 100) for l, b in top_langs]

    from collections import Counter
    daily = Counter(commit_dates)
    day_list, counts = [], []
    for i in range(365):
        d = (since + timedelta(days=i + 1)).strftime("%Y-%m-%d")
        day_list.append(d)
        counts.append(daily.get(d, 0))

    cur = 0
    for c in reversed(counts):
        if c > 0:
            cur += 1
        elif cur == 0:
            continue  # trailing zero-days (today) don't break the streak
        else:
            break
    longest = run = 0
    for c in counts:
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)

    commits_n = len(commit_dates)
    prs = search_count("author:%s type:pr created:>%s" % (USER, since_s))
    issues = search_count("author:%s type:issue created:>%s" % (USER, since_s))

    tail_weeks = [sum(counts[i:i + 7]) for i in range(len(counts) - 182, len(counts), 7)]
    week_dates = [day_list[i] for i in range(len(counts) - 182, len(counts), 7)]

    return {
        "total": commits_n + prs + issues,
        "commits": commits_n,
        "prs": prs,
        "issues": issues,
        "stars": stars,
        "repos": len(owned),
        "cur_streak": cur,
        "longest_streak": longest,
        "top_langs": top_langs,
        "weeks": tail_weeks,
        "week_dates": week_dates,
        "private": PRIVATE_OK,
    }


def card_open(w, h, t):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" role="img">' % (w, h, w, h)
        + '<rect x="1" y="1" width="%d" height="%d" rx="12" fill="%s" '
        'stroke="%s" stroke-width="1.5"/>' % (w - 2, h - 2, t["bg"], t["border"])
    )


def title_row(t, title, subtitle, y=36):
    s = ('<text x="24" y="%d" font-family="%s" font-size="18" font-weight="700" '
         'fill="%s">%s</text>') % (y, FONT, t["title"], esc(title))
    if subtitle:
        s += ('<text x="24" y="%d" font-family="%s" font-size="12" fill="%s">%s</text>'
              % (y + 20, FONT, t["muted"], esc(subtitle)))
    return s


def render_stats(d, theme):
    t = THEMES[theme]
    W, H = 520, 216
    s = card_open(W, H, t)
    sub = "last 12 months" + ("  ·  🔒 incl. private" if d["private"] else "  ·  public only")
    s += title_row(t, "GitHub Stats", sub)
    items = [
        ("Total Contributions", d["total"]),
        ("Commits", d["commits"]),
        ("Pull Requests", d["prs"]),
        ("Issues", d["issues"]),
        ("Stars Earned", d["stars"]),
        ("Repositories", d["repos"]),
    ]
    for i, (label, val) in enumerate(items):
        col, row = i % 2, i // 2
        x = 28 + col * 256
        y = 108 + row * 38
        dot = t["accent"] if i % 2 == 0 else t["accent2"]
        s += '<circle cx="%d" cy="%d" r="5" fill="%s"/>' % (x, y - 4, dot)
        s += ('<text x="%d" y="%d" font-family="%s" font-size="13" fill="%s">%s</text>'
              % (x + 16, y, FONT, t["muted"], esc(label)))
        s += ('<text x="%d" y="%d" text-anchor="end" font-family="%s" font-size="17" '
              'font-weight="700" fill="%s">%s</text>'
              % (x + 228, y, FONT, t["text"], f"{val:,}"))
    return s + "</svg>"


def render_streak(d, theme):
    t = THEMES[theme]
    W, H = 440, 216
    s = card_open(W, H, t)
    s += title_row(t, "Streak", "keep the neon burning")
    cx, cy, r = 96, 128, 58
    import math
    C = 2 * math.pi * r
    frac = min(d["cur_streak"] / max(d["longest_streak"], 1), 1.0) if d["longest_streak"] else 0.0
    s += ('<defs><linearGradient id="rg" x1="0" y1="0" x2="1" y2="1">'
          '<stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/>'
          "</linearGradient></defs>" % (t["accent2"], t["accent"]))
    s += '<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="12"/>' % (
        cx, cy, r, t["track"])
    s += ('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="url(#rg)" stroke-width="12" '
          'stroke-linecap="round" stroke-dasharray="%.1f %.1f" transform="rotate(-90 %d %d)"/>'
          % (cx, cy, r, C * frac, C, cx, cy))
    s += ('<text x="%d" y="%d" text-anchor="middle" font-family="%s" font-size="34" '
          'font-weight="800" fill="%s">%d</text>' % (cx, cy + 6, FONT, t["text"], d["cur_streak"]))
    s += ('<text x="%d" y="%d" text-anchor="middle" font-family="%s" font-size="12" '
          'fill="%s">days</text>' % (cx, cy + 26, FONT, t["muted"]))
    rows = [("Current Streak", d["cur_streak"]), ("Longest Streak", d["longest_streak"]),
            ("Total Contributions", d["total"])]
    for i, (label, val) in enumerate(rows):
        y = 96 + i * 40
        s += ('<text x="196" y="%d" font-family="%s" font-size="13" fill="%s">%s</text>'
              % (y, FONT, t["muted"], esc(label)))
        s += ('<text x="412" y="%d" text-anchor="end" font-family="%s" font-size="19" '
              'font-weight="700" fill="%s">%s</text>' % (y, FONT, t["text"], f"{val:,}"))
    return s + "</svg>"


def render_top_langs(d, theme):
    t = THEMES[theme]
    W, H = 460, 300
    s = card_open(W, H, t)
    s += title_row(t, "Most Used Languages", "by code size")
    y = 78
    for lang, pct in d["top_langs"]:
        color = LANG_COLORS.get(lang, "#8B949E")
        s += ('<text x="24" y="%d" font-family="%s" font-size="13" fill="%s">%s</text>'
              % (y, FONT, t["text"], esc(lang)))
        bx, bw = 150, 200
        s += '<rect x="%d" y="%d" width="%d" height="10" rx="5" fill="%s"/>' % (
            bx, y - 9, bw, t["track"])
        s += '<rect x="%d" y="%d" width="%.1f" height="10" rx="5" fill="%s"/>' % (
            bx, y - 9, bw * pct / 100.0, color)
        s += ('<text x="436" y="%d" text-anchor="end" font-family="%s" font-size="12" '
              'fill="%s">%.1f%%</text>' % (y, FONT, t["muted"], pct))
        y += 27
    if not d["top_langs"]:
        s += ('<text x="24" y="110" font-family="%s" font-size="13" fill="%s">'
              "no language data</text>" % (FONT, t["muted"]))
    return s + "</svg>"


def render_activity(d, theme):
    t = THEMES[theme]
    W, H = 740, 250
    s = card_open(W, H, t)
    s += title_row(t, "Contribution Activity", "last 26 weeks")
    weeks = d["weeks"]
    n = len(weeks)
    if n < 2:
        return s + "</svg>"
    x0, x1, y0, y1 = 52, W - 24, 84, 208
    mx = max(weeks) or 1
    pts = [(x0 + i * (x1 - x0) / (n - 1), y1 - (v / mx) * (y1 - y0)) for i, v in enumerate(weeks)]
    for frac in (0, 0.5, 1.0):
        gy = y1 - frac * (y1 - y0)
        val = int(round(mx * frac))
        s += '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-dasharray="4 4"/>' % (
            x0, gy, x1, gy, t["grid"])
        s += ('<text x="%d" y="%.1f" text-anchor="end" font-family="%s" font-size="10" '
              'fill="%s">%d</text>' % (x0 - 8, gy + 3, FONT, t["muted"], val))
    s += ('<defs><linearGradient id="ag" x1="0" y1="0" x2="0" y2="1">'
          '<stop offset="0" stop-color="%s" stop-opacity="0.45"/>'
          '<stop offset="1" stop-color="%s" stop-opacity="0.02"/>'
          "</linearGradient></defs>" % (t["accent2"], t["accent2"]))
    line = "M%.1f,%.1f " % pts[0] + " ".join("L%.1f,%.1f" % p for p in pts[1:])
    area = line + " L%.1f,%.1f L%.1f,%.1f Z" % (pts[-1][0], y1, pts[0][0], y1)
    s += '<path d="%s" fill="url(#ag)"/>' % area
    s += '<path d="%s" fill="none" stroke="%s" stroke-width="2.5" stroke-linejoin="round"/>' % (
        line, t["accent"])
    seen = set()
    for i, dt in enumerate(d["week_dates"]):
        try:
            mon = datetime.strptime(dt[:10], "%Y-%m-%d").strftime("%b")
        except ValueError:
            continue
        if mon in seen:
            continue
        seen.add(mon)
        x = x0 + i * (x1 - x0) / (n - 1)
        s += ('<text x="%.1f" y="%d" text-anchor="middle" font-family="%s" font-size="10" '
              'fill="%s">%s</text>' % (x, y1 + 18, FONT, t["muted"], mon))
    return s + "</svg>"


def main():
    data = fetch_all()
    os.makedirs(OUT, exist_ok=True)
    renderers = {
        "stats": render_stats,
        "streak": render_streak,
        "top-langs": render_top_langs,
        "activity": render_activity,
    }
    for name, fn in renderers.items():
        for theme in ("dark", "light"):
            path = os.path.join(OUT, "%s-%s.svg" % (name, theme))
            with open(path, "w", encoding="utf-8") as f:
                f.write(fn(data, theme))
    summary = {k: v for k, v in data.items() if k not in ("top_langs", "weeks", "week_dates")}
    summary["top_langs"] = [(l, round(p, 1)) for l, p in data["top_langs"]]
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()

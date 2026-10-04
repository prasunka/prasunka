"""Render the skyline and high-score SVGs for the profile readme.

Every repository the token can see, public or private, feeds the graphics, but only
aggregates are drawn: no repository names, descriptions or commit messages.

Usage: python scripts/graphics.py [--data sample.json]
Without --data, fetches from the GitHub GraphQL API using PROFILE_TOKEN.
"""
import argparse, datetime as dt, json, math, os, random, urllib.error, urllib.request

REPOS_QUERY = """
query($cursor: String, $since: GitTimestamp!, $week: GitTimestamp!) {
  viewer {
    login createdAt
    repositories(ownerAffiliations: OWNER, isFork: false, first: 50, after: $cursor,
                 orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        name createdAt primaryLanguage { name }
        defaultBranchRef { target { ... on Commit {
          total: history { totalCount }
          recent: history(since: $since) { totalCount }
          week: history(since: $week) { totalCount }
        } } }
      }
    }
  }
}
"""

CALENDAR_QUERY = """
query($from: DateTime!, $to: DateTime!) {
  viewer { contributionsCollection(from: $from, to: $to) {
    contributionCalendar { weeks { contributionDays { date contributionCount } } }
  } }
}
"""

# 3x5 pixel font
FONT = {
    "0": "111101101101111", "1": "010110010010111", "2": "111001111100111", "3": "111001111001111",
    "4": "101101111001001", "5": "111100111001111", "6": "111100111101111", "7": "111001001001001",
    "8": "111101111101111", "9": "111101111001111", "A": "010101111101101", "B": "110101110101110",
    "C": "011100100100011", "D": "110101101101110", "E": "111100110100111", "F": "111100110100100",
    "G": "011100101101011", "H": "101101111101101", "I": "111010010010111", "J": "001001001101010",
    "K": "101101110101101", "L": "100100100100111", "M": "101111111101101", "N": "110101101101101",
    "O": "010101101101010", "P": "110101110100100", "Q": "010101101110011", "R": "110101110101101",
    "S": "011100010001110", "T": "111010010010010", "U": "101101101101111", "V": "101101101101010",
    "W": "101101111111101", "X": "101101010101101", "Y": "101101010010010", "Z": "111001010100111",
    " ": "000000000000000", ".": "000000000000010", "-": "000000111000000", "+": "000010111010000",
    "#": "101111101111101", "/": "001001010100100", "=": "000111000111000",
}

LEGEND_SCALE = 0.6
SKY_BANDS = 4
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
SYNODIC_MONTH = 29.530588853
NEW_MOON = dt.datetime(2000, 1, 6, 18, 14, tzinfo=dt.timezone.utc)

THEME = """
:root{--bg:#f6f8fa;--on:#1f2328;--txt:#57606a;--body:#d0d7de;--win:#bfc6cd;--star:transparent;
--s0:#dce8f5;--s1:#e8eef5;--s2:#f4ebe3;--s3:#f8dcc4;--far:#e3e8ee;--moond:transparent;--sun:#f0b429;--beacon:#cf222e;
--c0:#1a7f37;--c1:#0969da;--c2:#bf8700;--c3:#8250df;--c4:#cf222e;--c5:#6e7781}
@media(prefers-color-scheme:dark){:root{--bg:#0d1117;--on:#7ee787;--txt:#8b949e;--body:#21262d;--win:#30363d;--star:#e6edf3;
--s0:#0d1117;--s1:#0f1525;--s2:#141a31;--s3:#1d1c3a;--far:#171c2c;--moond:#1d2436;--sun:transparent;--beacon:#ff6b6b;
--c0:#7ee787;--c1:#58a6ff;--c2:#e3b341;--c3:#bc8cff;--c4:#ff7b72;--c5:#8b949e}}
.bg{fill:var(--bg)}.far{fill:var(--far)}.moond{fill:var(--moond)}.sun{fill:var(--sun)}.beacon{fill:var(--beacon)}.met{fill:var(--star)}.s0{fill:var(--s0)}.s1{fill:var(--s1)}.s2{fill:var(--s2)}.s3{fill:var(--s3)}.on{fill:var(--on)}.txt{fill:var(--txt)}.body{fill:var(--body)}.win{fill:var(--win)}.star{fill:var(--star)}
.tw{animation:tw 4s steps(1) infinite}.lit{opacity:0;animation:on .3s steps(2) forwards}
.beacon{animation:beacon 2.4s steps(1) infinite}.met{opacity:0;animation:met 15s linear 4s infinite}
@keyframes beacon{60%{opacity:.15}}
@keyframes met{0%{transform:translate(0,0);opacity:0}1%{opacity:1}6%{opacity:1}9%{transform:translate(-30px,30px);opacity:0}100%{transform:translate(-30px,30px);opacity:0}}
@keyframes on{to{opacity:1}}@keyframes tw{0%,80%{opacity:1}90%{opacity:.2}}
@media(prefers-reduced-motion:reduce){.tw,.lit,.beacon,.met{animation:none}.lit{opacity:1}.met{display:none}}
""" + "".join(f".c{i}{{fill:var(--c{i})}}" for i in range(6))


def gql(query, variables, token):
    req = urllib.request.Request("https://api.github.com/graphql", json.dumps({"query": query, "variables": variables}).encode(),
                                 {"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    # Logs are public: report failures without echoing API responses, which may describe private repos.
    try:
        with urllib.request.urlopen(req) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"GitHub API request failed with HTTP {e.code}") from None
    if "errors" in out:
        raise SystemExit(f"GitHub API returned {len(out['errors'])} error(s); details withheld from public logs")
    return out["data"]["viewer"]


def fetch(token):
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=30)).isoformat()
    week = (now - dt.timedelta(days=7)).isoformat()
    repos, cursor = [], None
    while True:
        viewer = gql(REPOS_QUERY, {"cursor": cursor, "since": since, "week": week}, token)
        page = viewer["repositories"]
        for r in page["nodes"]:
            target = (r["defaultBranchRef"] or {}).get("target") or {}
            repos.append({"name": r["name"], "createdAt": r["createdAt"],
                          "language": (r["primaryLanguage"] or {}).get("name"),
                          "commits": target.get("total", {}).get("totalCount", 0),
                          "recent": target.get("recent", {}).get("totalCount", 0),
                          "week": target.get("week", {}).get("totalCount", 0)})
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    cal = gql(CALENDAR_QUERY, {"from": (now - dt.timedelta(days=364)).isoformat(), "to": now.isoformat()}, token)
    weeks = cal["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [{"date": d["date"], "count": d["contributionCount"]} for w in weeks for d in w["contributionDays"]]
    return {"login": viewer["login"], "createdAt": viewer["createdAt"], "repos": repos, "days": days}


def text_cells(s, x, y):
    cells = []
    for i, ch in enumerate(s.upper()):
        glyph = FONT.get(ch, FONT[" "])
        cells += [(x + i * 4 + b % 3, y + b // 3) for b, bit in enumerate(glyph) if bit == "1"]
    return cells


def text_width(s):
    return len(s) * 4 - 1


def path(cls, cells, extra=""):
    d = "".join(f"M{x} {y}h1v1h-1z" for x, y in cells)
    return f'<path class="{cls}" d="{d}"{extra}/>' if cells else ""


def svg(w, h, body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" shape-rendering="crispEdges" '
            f'role="img" aria-label="{label}"><style>{THEME}</style><rect class="bg" width="{w}" height="{h}"/>{body}</svg>')


def palette(repos):
    """Language -> color index: top 5 by repo count (ties favour newer repos), the rest share the last."""
    counts = {}
    for r in reversed(repos):
        if r["language"]: counts[r["language"]] = counts.get(r["language"], 0) + 1
    ranked = sorted(counts, key=lambda k: -counts[k])
    return {name: i for i, name in enumerate(ranked[:5])}, ranked


def sky(w, ground):
    """Banded gradient, dithered from each band into the next with a 4x4 Bayer matrix."""
    band = ground / SKY_BANDS
    out = []
    for k in range(SKY_BANDS):
        rows = [y for y in range(ground) if min(int(y / band), SKY_BANDS - 1) == k]
        out.append(f'<rect class="s{k}" x="0" y="{rows[0]}" width="{w}" height="{len(rows)}"/>')
    for y in range(ground):
        pos = y / band
        k = min(int(pos), SKY_BANDS - 1)
        if k < SKY_BANDS - 1 and pos - k > 0.5:
            t = (pos - k - 0.5) * 32
            out.append(path(f"s{k + 1}", [(x, y) for x in range(w) if BAYER[y % 4][x % 4] < t]))
    return out


def disc(cx, cy, size):
    """Pixel centres of a disc, with unit-circle coordinates."""
    r = size / 2
    for j in range(size):
        for i in range(size):
            u, v = (i + 0.5 - r) / r, (j + 0.5 - r) / r
            if u * u + v * v <= 1:
                yield cx + i, cy + j, u, v


def moon(cx, cy, when, size=9):
    """Moon phase on `when`: lit cells and earthshine cells."""
    phase = ((when - NEW_MOON).total_seconds() / 86400 / SYNODIC_MONTH) % 1
    k = math.cos(2 * math.pi * phase)
    lit, dark = [], []
    for x, y, u, v in disc(cx, cy, size):
        edge = k * math.sqrt(1 - v * v)
        (lit if (u > edge if phase < 0.5 else u < -edge) else dark).append((x, y))
    return lit, dark


def skyline(repos, colors, ranked, now):
    rng = random.Random(42)
    n = len(repos)
    slot = max(4, min(9, 120 // max(n, 1)))
    legend = ranked[:5] + (["OTHER"] if len(ranked) > 5 else [])
    legend_w = sum(text_width(name) + 9 for name in legend) - 9
    w = max(128, n * slot + 8, round(legend_w * LEGEND_SCALE) + 16)
    ground, h = 46, 54
    x0 = (w - n * slot) // 2
    top_c = max((r["commits"] for r in repos), default=1) or 1
    top_r = max((r["recent"] for r in repos), default=1) or 1

    out = sky(w, ground)
    mx, my = w - 16, 3
    stars = [(x, y) for x, y in ((rng.randrange(w), rng.randrange(ground - 14)) for _ in range(w // 4))
             if not (mx - 2 <= x <= mx + 10 and y <= my + 10)]
    out += [path("star", stars[len(stars) // 3:]), path("star tw", stars[: len(stars) // 3])]
    lit_moon, dark_moon = moon(mx, my, now)
    out += [path("moond", dark_moon), path("star", lit_moon),
            path("sun", [(x, y) for x, y, _, _ in disc(mx + 1, my + 1, 7)])]
    out.append('<g class="met">' + "".join(
        f'<rect x="{w * 0.6 + d:.0f}" y="{9 - d}" width="1" height="1" opacity="{o}"/>'
        for d, o in ((0, 1), (1, .8), (2, .6), (3, .4), (4, .25), (5, .12))) + "</g>")

    # Distant skyline for depth: random silhouettes behind the real buildings.
    x = 0
    while x < w:
        fw, fh = rng.randint(3, 7), rng.randint(4, 20)
        out.append(f'<rect class="far" x="{x}" y="{ground - fh}" width="{fw}" height="{fh}"/>')
        x += fw + rng.randint(0, 2)

    # Lit windows sit over the dim ones and switch on after load, busiest building first.
    body, windows_all, lit, beacons = [], [], [], []
    for i, r in enumerate(repos):
        bw = slot - 1
        bh = 6 + round(30 * math.log1p(r["commits"]) / math.log1p(top_c))
        x, top = x0 + i * slot, ground - bh
        body += [(x + c, y) for c in range(bw) for y in range(top, ground)]
        # Antennas are scenery; a beacon on top marks commits in the last 7 days.
        if (i % 4 == 1 or r.get("week")) and bw >= 3:
            body += [(x + bw // 2, top - k) for k in (1, 2, 3)]
        if r.get("week"):
            beacons.append((x + bw // 2, top - 4))
        windows = [(x + c, y) for y in range(top + 2, ground - 1, 2) for c in range(1, bw - 1, 2)]
        windows_all += windows
        share = math.sqrt(r["recent"] / top_r) if r["recent"] else 0
        if share:
            on = rng.sample(windows, max(1, round(len(windows) * share)))
            lit.append((r["recent"], f"c{colors.get(r['language'], 5)}", on))
    out += [path("body", body), path("win", windows_all)]
    for k, (bx, by) in enumerate(beacons):
        out.append(f'<rect class="beacon" x="{bx}" y="{by}" width="1" height="1" style="animation-delay:{k * 0.8 % 2.4:.1f}s"/>')
    for rank, (_, cls, cells) in enumerate(sorted(lit, key=lambda t: -t[0])):
        out.append(path(f"{cls} lit", cells, f' style="animation-delay:{0.8 + rank * 0.35:.2f}s"'))
    out.append(f'<rect class="txt" x="0" y="{ground}" width="{w}" height="1"/>')

    # Legend is drawn at a smaller scale than the city so it reads as a caption.
    items, x = [], 0
    for k, name in enumerate(legend):
        items.append(path(f"c{k}", [(x + a, b) for a in range(3) for b in range(1, 4)]))
        items.append(path("txt", text_cells(name, x + 5, 0)))
        x += text_width(name) + 9
    lx = (w - legend_w * LEGEND_SCALE) / 2
    out.append(f'<g transform="translate({lx:.2f} {ground + 3}) scale({LEGEND_SCALE})">{"".join(items)}</g>')
    return svg(w, h, "".join(out), f"Skyline of {n} projects, public and private")


def streak(counts):
    best = cur = 0
    for c in counts:
        cur = cur + 1 if c else 0
        best = max(best, cur)
    return best


def scores(data, repos):
    counts = [d["count"] for d in data["days"]]
    years = dt.date.today().year - int(data["createdAt"][:4])
    rows = [("CONTRIBUTIONS", f"{sum(counts)}"),
            ("BEST STREAK", f"{streak(counts)} DAYS"),
            ("BUSIEST DAY", f"{max(counts, default=0)}"),
            ("PROJECTS", f"{len(repos)}"),
            ("LANGUAGES", f"{len({r['language'] for r in repos if r['language']})}"),
            ("YEARS PLAYED", f"{years}")]
    w, h = 128, 76
    out = [path("on", text_cells("HIGH SCORES", (w - text_width("HIGH SCORES")) // 2, 5))]
    for i, (label, value) in enumerate(rows):
        y = 17 + i * 8
        vx = w - 10 - text_width(value)
        lx = 10 + text_width(label) + 3
        out += [path(f"c{i % 6}", text_cells(label, 10, y) + text_cells(value, vx, y)),
                path("win", [(x, y + 4) for x in range(lx, vx - 2, 2)])]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("UPDATED %d %b %Y").upper()
    out.append(path("txt", text_cells(stamp, (w - text_width(stamp)) // 2, h - 9)))
    return svg(w, h, "".join(out), "High scores: " + ", ".join(f"{a.lower()} {b.lower()}" for a, b in rows))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    args = ap.parse_args()
    if not args.data and not os.environ.get("PROFILE_TOKEN"):
        raise SystemExit("PROFILE_TOKEN is not set: add a read-only fine-grained token as a repository secret")
    data = json.load(open(args.data)) if args.data else fetch(os.environ["PROFILE_TOKEN"])
    repos = [r for r in data["repos"] if r["name"] != data["login"] and r["commits"]]
    colors, ranked = palette(repos)
    os.makedirs("assets", exist_ok=True)
    open("assets/skyline.svg", "w").write(skyline(repos, colors, ranked, dt.datetime.now(dt.timezone.utc)))
    open("assets/scores.svg", "w").write(scores(data, repos))


if __name__ == "__main__":
    main()

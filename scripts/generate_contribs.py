#!/usr/bin/env python3
"""
generate_contribs.py

Fetches a GitHub user's contribution calendar via the GitHub GraphQL API and
renders it as an isometric-block SVG, in both a light and a dark palette,
for embedding in a profile README.

Color and height are deliberately decoupled:
    - COLOR matches GitHub's own contribution-intensity buckets (0-4), so the
      palette reads the same way GitHub's native graph does.
    - HEIGHT is driven by the raw contribution count run through a log curve,
      so a single contribution still visibly registers, and an extremely busy
      day doesn't turn into a spike that dwarfs everything else on the chart.

Usage:
    python generate_contribs.py --username vusi-kunene-matlou --out output
    python generate_contribs.py --mock --out output          # local preview, no API calls

Environment:
    GH_README_TOKEN   A GitHub token with at least `read:user` scope.
                       Required unless --mock is passed. Falls back to
                       GITHUB_TOKEN (e.g. the workflow's built-in token) if
                       GH_README_TOKEN isn't set.
"""

import argparse
import datetime
import json
import math
import os
import random
import sys
import urllib.request

GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""

# --- Palettes -----------------------------------------------------------

LIGHT = {
    "bg": "#ffffff",
    "levels": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
    "text": "#24292f",
}

DARK = {
    "bg": "#0d1117",
    "levels": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
    "text": "#c9d1d9",
}


# --- Data fetching --------------------------------------------------------

def fetch_contributions(username: str, token: str):
    body = json.dumps({"query": QUERY, "variables": {"login": username}}).encode()
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "contrib-art-generator",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())

    if "errors" in payload:
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")

    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return weeks


def mock_contributions(weeks_count: int = 53):
    """Generate plausible-looking mock contribution data for local preview."""
    random.seed(42)
    today = datetime.date.today()
    start = today - datetime.timedelta(weeks=weeks_count)
    # align to the most recent Sunday on/before start
    start -= datetime.timedelta(days=(start.weekday() + 1) % 7)

    weeks = []
    day = start
    for _ in range(weeks_count):
        week_days = []
        for _ in range(7):
            # weight towards low activity, with occasional bursts (including
            # a few outliers) so the log-height curve has something to show off
            base = random.choices(
                [0, 1, 2, 3, 4, 6, 9, 15, 25],
                weights=[28, 24, 17, 11, 8, 5, 3, 2, 1],
            )[0]
            week_days.append({"date": day.isoformat(), "contributionCount": base})
            day += datetime.timedelta(days=1)
        weeks.append({"contributionDays": week_days})
    return weeks


def quantize(count: int) -> int:
    """Map a raw contribution count to a 0-4 COLOR intensity level (GitHub-style buckets)."""
    if count == 0:
        return 0
    if count <= 2:
        return 1
    if count <= 4:
        return 2
    if count <= 7:
        return 3
    return 4


def log_height(count: int, max_count: int, min_h: float = 1.5, max_h: float = 11.0) -> float:
    """
    Map a raw contribution count to a cube HEIGHT using a log curve.

    - count == 0            -> 0 (flat tile, no cube)
    - count == 1             -> min_h (still visibly a cube, not invisible)
    - count approaching the busiest day in the dataset -> max_h
    - a day 10x busier than another does NOT get a height 10x taller;
      the curve compresses that gap so no single day dominates the chart
    """
    if count <= 0:
        return 0.0
    if max_count <= 1:
        # Degenerate case: everything is 0 or 1 contribution, no need to scale.
        return min_h

    # log1p keeps count=1 from being log(1)=0; +1 on both count and max_count
    # keeps the ratio well-behaved at the low end.
    ratio = math.log1p(count) / math.log1p(max_count)
    ratio = min(max(ratio, 0.0), 1.0)
    return min_h + ratio * (max_h - min_h)


# --- Isometric SVG rendering ---------------------------------------------

def iso_project(col: int, row: int, tile_w: float, tile_h: float):
    """Project (col, row) grid coordinates into isometric screen space."""
    x = (col - row) * (tile_w / 2)
    y = (col + row) * (tile_h / 2)
    return x, y


def render_svg(weeks, palette: dict, title: str = "") -> str:
    tile_w, tile_h = 14.0, 8.0

    n_weeks = len(weeks)
    n_days = 7

    # Find the busiest single day across the whole dataset so log_height can
    # scale relative to this user's own activity rather than a fixed constant.
    max_count = 0
    for week in weeks:
        for day in week["contributionDays"]:
            max_count = max(max_count, day["contributionCount"])

    max_cube_height = 11.0  # keep in sync with log_height's default max_h

    # Compute the bounding box of the isometric projection first, so we can
    # translate everything into positive coordinate space with padding.
    xs, ys = [], []
    for col in range(n_weeks):
        for row in range(n_days):
            x, y = iso_project(col, row, tile_w, tile_h)
            xs += [x, x + tile_w]
            ys += [y, y + tile_h + max_cube_height]

    pad = 24
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = (max_x - min_x) + pad * 2
    height = (max_y - min_y) + pad * 2 + (30 if title else 0)

    def tx(x):
        return x - min_x + pad

    def ty(y):
        return y - min_y + pad + (30 if title else 0)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" '
        f'width="{width:.0f}" height="{height:.0f}" font-family="Segoe UI, Helvetica, Arial, sans-serif">',
        f'<rect x="0" y="0" width="{width:.1f}" height="{height:.1f}" fill="{palette["bg"]}" rx="12" />',
    ]

    if title:
        parts.append(
            f'<text x="{pad}" y="{20}" fill="{palette["text"]}" font-size="13" '
            f'font-weight="600">{title}</text>'
        )

    # Draw back-to-front (by row+col) so isometric cubes overlap correctly.
    cells = []
    for col, week in enumerate(weeks):
        for row, day in enumerate(week["contributionDays"]):
            level = quantize(day["contributionCount"])          # -> COLOR
            h = log_height(day["contributionCount"], max_count)  # -> HEIGHT
            cells.append((col, row, level, h, day["date"], day["contributionCount"]))

    cells.sort(key=lambda c: (c[0] + c[1]))

    for col, row, level, h, date, count in cells:
        x, y = iso_project(col, row, tile_w, tile_h)
        x, y = tx(x), ty(y)
        color = palette["levels"][level]
        # Flat tiles (no contributions) still get a thin sliver so the grid
        # reads as a continuous surface rather than gaps.
        draw_h = h if h > 0 else 1.5

        # top face (rhombus)
        top = (
            f'<polygon points="{x + tile_w/2:.1f},{y - draw_h:.1f} '
            f'{x + tile_w:.1f},{y + tile_h/2 - draw_h:.1f} '
            f'{x + tile_w/2:.1f},{y + tile_h - draw_h:.1f} '
            f'{x:.1f},{y + tile_h/2 - draw_h:.1f}" fill="{color}" />'
        )
        # left face
        left = (
            f'<polygon points="{x:.1f},{y + tile_h/2 - draw_h:.1f} '
            f'{x + tile_w/2:.1f},{y + tile_h - draw_h:.1f} '
            f'{x + tile_w/2:.1f},{y + tile_h:.1f} '
            f'{x:.1f},{y + tile_h/2:.1f}" fill="{color}" opacity="0.75" />'
        )
        # right face
        right = (
            f'<polygon points="{x + tile_w/2:.1f},{y + tile_h - draw_h:.1f} '
            f'{x + tile_w:.1f},{y + tile_h/2 - draw_h:.1f} '
            f'{x + tile_w:.1f},{y + tile_h/2:.1f} '
            f'{x + tile_w/2:.1f},{y + tile_h:.1f}" fill="{color}" opacity="0.55" />'
        )

        parts.append(f'<g><title>{date}: {count} contributions</title>{top}{left}{right}</g>')

    parts.append("</svg>")
    return "\n".join(parts)


# --- Main -----------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate isometric GitHub contribution art.")
    parser.add_argument("--username", default=os.environ.get("GITHUB_USERNAME", ""))
    parser.add_argument("--out", default="output")
    parser.add_argument("--mock", action="store_true", help="Use generated mock data, skip API calls.")
    args = parser.parse_args()

    if args.mock:
        weeks = mock_contributions()
    else:
        token = os.environ.get("GH_README_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("GH_README_TOKEN (or GITHUB_TOKEN) environment variable is required (or pass --mock).")
        if not args.username:
            sys.exit("--username is required (or pass --mock).")
        weeks = fetch_contributions(args.username, token)

    os.makedirs(args.out, exist_ok=True)

    light_svg = render_svg(weeks, LIGHT, title="Contribution Activity")
    dark_svg = render_svg(weeks, DARK, title="Contribution Activity")

    with open(os.path.join(args.out, "contribs-light.svg"), "w") as f:
        f.write(light_svg)
    with open(os.path.join(args.out, "contribs-dark.svg"), "w") as f:
        f.write(dark_svg)

    print(f"Wrote {args.out}/contribs-light.svg and {args.out}/contribs-dark.svg")


if __name__ == "__main__":
    main()
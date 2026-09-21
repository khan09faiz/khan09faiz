"""Renders every profile graphic as one sumi-e set.

The cards share a washi-paper language borrowed from the portfolio site:
ink wash that deepens with volume, vermillion seal accents, hairline rules
and monospace legends. One API round trip feeds all six cards, so the whole
README stays consistent and fully self-hosted.
"""

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request

USERNAME = os.environ.get("GITHUB_USER", "khan09faiz")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT_DIR = os.environ.get("OUT_DIR", "assets")

# Palette lifted from the portfolio's CSS custom properties.
PAPER = "#fdfcfa"
RAISED = "#fffffe"
SUNK = "#f6f4f0"
SUMI = "#1a1816"
SUMI_SOFT = "#5c564f"
MIST = "#a8a096"
RULE = "#e2ddd5"

VERMILLION = "#bf2a22"
GOLD = "#a68438"
SAKURA = "#e9a8b9"
INDIGO = "#2f4858"

# Ink wash: pale at the horizon, full sumi in the foreground.
WASH = [
    (0.00, (232, 228, 221)),
    (0.28, (186, 181, 173)),
    (0.52, (133, 127, 119)),
    (0.74, (84, 78, 71)),
    (0.90, (48, 44, 41)),
    (1.00, (26, 24, 22)),
]

SANS = "Inter, Segoe UI, Helvetica Neue, Helvetica, Arial, sans-serif"
MONO = "JetBrains Mono, SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace"

DEVICON = "https://cdn.jsdelivr.net/gh/devicons/devicon/icons/{}.svg"
ICON_LIMIT = 30_000

# GitHub language name -> devicon slug.
LANG_ICON = {
    "Python": "python/python-original",
    "Jupyter Notebook": "jupyter/jupyter-original",
    "JavaScript": "javascript/javascript-original",
    "TypeScript": "typescript/typescript-original",
    "HTML": "html5/html5-original",
    "CSS": "css3/css3-original",
    "SCSS": "sass/sass-original",
    "Java": "java/java-original",
    "C++": "cplusplus/cplusplus-original",
    "C": "c/c-original",
    "C#": "csharp/csharp-original",
    "Shell": "bash/bash-original",
    "Dockerfile": "docker/docker-original",
    "Go": "go/go-original",
    "Rust": "rust/rust-original",
    "PHP": "php/php-original",
    "Ruby": "ruby/ruby-original",
    "Kotlin": "kotlin/kotlin-original",
    "Dart": "dart/dart-original",
    "PowerShell": "powershell/powershell-original",
    "PLpgSQL": "postgresql/postgresql-original",
    "Vue": "vuejs/vuejs-original",
}

STACK = [
    (
        "AI &#38; MACHINE LEARNING",
        [
            ("Python", "python/python-original", "#3776AB"),
            ("PyTorch", "pytorch/pytorch-original", "#EE4C2C"),
            ("TensorFlow", "tensorflow/tensorflow-original", "#FF6F00"),
            ("Keras", "keras/keras-original", "#D00000"),
            ("OpenCV", "opencv/opencv-original", "#5C3EE8"),
            ("scikit&#8209;learn", "scikitlearn/scikitlearn-original", "#F7931E"),
            ("Pandas", "pandas/pandas-original", "#150458"),
            ("NumPy", "numpy/numpy-original", "#013243"),
            ("Jupyter", "jupyter/jupyter-original", "#F37626"),
        ],
    ),
    (
        "LLMs, GENAI &#38; DATA",
        [
            # devicon ships no mark for these four, so they render as wordmarks.
            ("LangChain", None, "#1C3C3C"),
            ("FAISS", None, "#4267B2"),
            ("Power BI", None, "#C8A200"),
            ("Matplotlib", "matplotlib/matplotlib-original", "#11557C"),
            ("PostgreSQL", "postgresql/postgresql-original", "#4169E1"),
            ("MongoDB", "mongodb/mongodb-original", "#47A248"),
            ("MySQL", "mysql/mysql-original", "#4479A1"),
            ("SQLite", "sqlite/sqlite-original", "#003B57"),
        ],
    ),
    (
        "ENTERPRISE &#38; CLOUD",
        [
            ("SAP ABAP", None, "#0FAAFF"),
            ("SAP HANA", None, "#0FAAFF"),
            ("Azure", "azure/azure-original", "#0078D4"),
            ("C", "c/c-original", "#A8B9CC"),
            ("React", "react/react-original", "#61DAFB"),
            ("FastAPI", "fastapi/fastapi-original", "#009688"),
            ("Git", "git/git-original", "#F05032"),
            ("GitHub", "github/github-original", "#1a1816"),
        ],
    ),
]

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                 orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

# Names that would overflow a treemap tile at any sensible size.
LANG_SHORT = {
    "Jupyter Notebook": "Jupyter",
    "Objective-C": "Obj-C",
    "Visual Basic .NET": "VB.NET",
}

_icon_cache = {}


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def fetch():
    body = json.dumps({"query": QUERY, "variables": {"login": USERNAME}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": USERNAME,
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def weekly(user):
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
    starts = [w["contributionDays"][0]["date"] for w in cal["weeks"]]
    return weeks, starts, cal["totalContributions"]


def daily(user):
    cal = user["contributionsCollection"]["contributionCalendar"]
    return [
        (d["date"], d["contributionCount"])
        for w in cal["weeks"]
        for d in w["contributionDays"]
    ]


def streaks(days):
    longest = run = 0
    for _, count in days:
        run = run + 1 if count > 0 else 0
        longest = max(longest, run)
    current = 0
    for i in range(len(days) - 1, -1, -1):
        if days[i][1] > 0:
            current += 1
        elif i == len(days) - 1:
            continue  # today may simply not have landed yet
        else:
            break
    return current, longest


# --------------------------------------------------------------------------- #
# Colour helpers
# --------------------------------------------------------------------------- #


def ink(t):
    """Sample the wash ramp; 0 is a pale horizon, 1 is loaded sumi."""
    t = min(max(t, 0.0), 1.0)
    for i in range(len(WASH) - 1):
        p0, c0 = WASH[i]
        p1, c1 = WASH[i + 1]
        if t <= p1:
            u = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
            return "#%02x%02x%02x" % tuple(
                round(c0[k] + (c1[k] - c0[k]) * u) for k in range(3)
            )
    return "#%02x%02x%02x" % WASH[-1][1]


def luminance(hex_color):
    h = (hex_color or "#5c564f").lstrip("#")
    if len(h) != 6:
        h = "5c564f"
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255


def for_paper(hex_color):
    """Deepen very light brand colours so they hold against washi."""
    h = (hex_color or "#5c564f").lstrip("#")
    if len(h) != 6:
        h = "5c564f"
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    if lum <= 0.66:
        return f"#{h}"
    k = (lum - 0.66) / 0.34 * 0.46
    return "#%02x%02x%02x" % (round(r * (1 - k)), round(g * (1 - k)), round(b * (1 - k)))


def readable_on(hex_color):
    return "#1a1816" if luminance(hex_color) > 0.58 else "#fdfcfa"


def fit(text, width, size, ratio=0.58):
    """Clip a label to the space a tile actually has, with an ellipsis."""
    budget = max(int(width / (size * ratio)), 3)
    if len(text) <= budget:
        return text
    return text[: budget - 1].rstrip() + "&#8230;"


def jitter(index, salt):
    digest = hashlib.sha256(f"{USERNAME}:{salt}:{index}".encode()).digest()
    return int.from_bytes(digest[:4], "big") / 0xFFFFFFFF


# --------------------------------------------------------------------------- #
# SVG scaffolding
# --------------------------------------------------------------------------- #


def defs(extra=""):
    return f'''<defs>
    <filter id="fiber" x="0" y="0" width="100%" height="100%">
      <feTurbulence type="fractalNoise" baseFrequency="0.82" numOctaves="4" />
      <feColorMatrix type="saturate" values="0" />
    </filter>
    <pattern id="tooth" width="7" height="7" patternTransform="rotate(38)"
             patternUnits="userSpaceOnUse">
      <line x1="0" y1="0" x2="0" y2="7" stroke="#ffffff" stroke-width="1"
            stroke-opacity="0.13" />
    </pattern>
    <style>
      /* An SVG embedded through &lt;img&gt; restarts its timeline every time the
         host page re-rasterises, so nothing that carries meaning is allowed to
         depend on an animation finishing. Text animates on transform only --
         worst case a label sits a few pixels low, never invisible. */
      @keyframes stroke {{ from {{ stroke-dashoffset: 1; }} to {{ stroke-dashoffset: 0; }} }}
      @keyframes rise {{ from {{ transform: translateY(10px); }} to {{ transform: translateY(0); }} }}
      @keyframes settle {{ from {{ transform: translateY(16px); }} to {{ transform: translateY(0); }} }}
      @keyframes breathe {{ 0%, 100% {{ opacity: 0.35; }} 50% {{ opacity: 1; }} }}
      @keyframes press {{ from {{ transform: scale(0.82) rotate(-7deg); }}
                          to {{ transform: scale(1) rotate(0deg); }} }}
      .br path {{ stroke-dasharray: 1; animation: stroke 2.4s ease-out backwards; }}
      .rg {{ animation: settle 1.1s cubic-bezier(.2,.75,.3,1) backwards; }}
      .tx {{ animation: rise 0.7s cubic-bezier(.2,.7,.3,1) backwards; }}
      .sp {{ animation: breathe 3.6s ease-in-out infinite; }}
      .seal {{ transform-box: fill-box; transform-origin: center;
               animation: press 0.9s cubic-bezier(.2,1.2,.35,1) backwards; }}
      @media (prefers-reduced-motion: reduce) {{
        .br path, .rg, .tx, .sp, .seal {{ animation: none; }}
      }}
    </style>
    {extra}
  </defs>'''


def doc(w, h, label, body, extra_defs=""):
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'role="img" aria-label="{label}">'
        f"{defs(extra_defs)}{body}</svg>\n"
    )


def frame(w, h, title, right=""):
    """Paper ground, title block and hairline rule shared by every panel."""
    note = (
        f'<text x="{w - 24}" y="31" fill="{MIST}" font-size="11.5" font-family="{MONO}" '
        f'text-anchor="end">{right}</text>'
        if right
        else ""
    )
    return f'''<rect width="{w}" height="{h}" rx="14" fill="{RAISED}" />
  <rect width="{w}" height="{h}" rx="14" filter="url(#fiber)" opacity="0.035" />
  <rect x="24" y="21" width="3" height="12" rx="1.5" fill="{VERMILLION}" />
  <text x="36" y="31" fill="{SUMI}" font-size="12" font-family="{MONO}"
        letter-spacing="2.4" opacity="0.88">{title}</text>{note}
  <line x1="24" y1="45" x2="{w - 24}" y2="45" stroke="{RULE}" stroke-width="1" />'''


def outline(w, h):
    return (
        f'<rect x="0.75" y="0.75" width="{w - 1.5}" height="{h - 1.5}" rx="14" '
        f'fill="none" stroke="{RULE}" stroke-width="1.5" />'
    )


def icon(slug, x, y, size):
    """Inline a devicon as a nested <svg>; external refs never load inside <img>."""
    if slug not in _icon_cache:
        try:
            with urllib.request.urlopen(DEVICON.format(slug), timeout=20) as resp:
                raw = resp.read().decode("utf-8", "replace")
            if len(raw) > ICON_LIMIT:
                raw = None
        except (urllib.error.URLError, TimeoutError, OSError):
            raw = None
        if raw:
            raw = re.sub(r"<\?xml.*?\?>", "", raw, flags=re.S)
            raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)
            m = re.search(r'viewBox="([^"]+)"', raw)
            view = m.group(1) if m else "0 0 128 128"
            inner = re.sub(r"^.*?<svg[^>]*>", "", raw, flags=re.S)
            inner = re.sub(r"</svg>\s*$", "", inner, flags=re.S)
            _icon_cache[slug] = (view, inner.strip())
        else:
            _icon_cache[slug] = None

    entry = _icon_cache.get(slug)
    if not entry:
        return ""
    view, inner = entry
    return (
        f'<svg x="{x:.1f}" y="{y:.1f}" width="{size}" height="{size}" '
        f'viewBox="{view}" overflow="visible">{inner}</svg>'
    )


def chips(items, x, y, size=10.5):
    """Outlined pills; width estimated from the monospace advance."""
    out = ""
    cx = x
    for label in items:
        chars = len(re.sub(r"&#\d+;", "_", label))
        w = chars * size * 0.62 + 22
        out += (
            f'<rect x="{cx:.1f}" y="{y:.1f}" width="{w:.1f}" height="23" rx="11.5" '
            f'fill="{SUNK}" stroke="{MIST}" stroke-opacity="0.55" stroke-width="1" />'
            f'<text x="{cx + w / 2:.1f}" y="{y + 15.5:.1f}" fill="{SUMI_SOFT}" '
            f'font-size="{size}" font-family="{MONO}" letter-spacing="0.8" '
            f'text-anchor="middle">{label}</text>'
        )
        cx += w + 9
    return out


TRACKING = 1.1


def status_pill(text, x, y, size=11):
    """Availability badge: a breathing dot plus static text that never hides."""
    chars = len(re.sub(r"&#\d+;", "_", text))
    w = chars * (size * 0.62 + TRACKING) + 52
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="28" rx="14" '
        f'fill="{VERMILLION}" fill-opacity="0.08" stroke="{VERMILLION}" '
        f'stroke-opacity="0.45" stroke-width="1" />'
        f'<circle class="sp" cx="{x + 19:.1f}" cy="{y + 14:.1f}" r="4.5" fill="{VERMILLION}" />'
        f'<text x="{x + 33:.1f}" y="{y + 18:.1f}" fill="{VERMILLION}" font-size="{size}" '
        f'font-family="{MONO}" font-weight="600" letter-spacing="{TRACKING}">{text}</text>'
    )


def seal(cx, cy, r, lines, delay=0.8):
    """A hanko-style vermillion stamp. Letterforms only -- no CJK font risk."""
    rows = ""
    step = r * 0.76
    top = cy - step * (len(lines) - 1) / 2
    for i, text in enumerate(lines):
        rows += (
            f'<text x="{cx:.1f}" y="{top + i * step + 5:.1f}" fill="{PAPER}" '
            f'font-size="{r * 0.46:.1f}" font-weight="700" font-family="{MONO}" '
            f'letter-spacing="1" text-anchor="middle">{text}</text>'
        )
    return (
        f'<g class="seal" style="animation-delay:{delay:.2f}s">'
        f'<rect x="{cx - r:.1f}" y="{cy - r:.1f}" width="{r * 2:.1f}" height="{r * 2:.1f}" '
        f'rx="{r * 0.28:.1f}" fill="{VERMILLION}" fill-opacity="0.94" />'
        f'<rect x="{cx - r:.1f}" y="{cy - r:.1f}" width="{r * 2:.1f}" height="{r * 2:.1f}" '
        f'rx="{r * 0.28:.1f}" fill="url(#tooth)" />'
        f'<rect x="{cx - r + 4:.1f}" y="{cy - r + 4:.1f}" width="{r * 2 - 8:.1f}" '
        f'height="{r * 2 - 8:.1f}" rx="{r * 0.2:.1f}" fill="none" stroke="{PAPER}" '
        f'stroke-opacity="0.55" stroke-width="1.2" />'
        f"{rows}</g>"
    )


# --------------------------------------------------------------------------- #
# Ink-wash ridges shared by the header and the footer
# --------------------------------------------------------------------------- #

LAYERS = 6
SAMPLES = 190


def smoothstep(t):
    return t * t * (3 - 2 * t)


def noise_1d(n, knots, salt):
    grid = [jitter(i, salt) for i in range(knots)]
    out = []
    for i in range(n):
        u = i / (n - 1) * (knots - 1)
        k0 = min(int(u), knots - 2)
        t = smoothstep(u - k0)
        out.append(grid[k0] * (1 - t) + grid[k0 + 1] * t)
    return out


def resample(values, n, phase=0.0):
    m = len(values)
    if m < 2:
        return [0.0] * n
    out = []
    for i in range(n):
        u = ((i / (n - 1) + phase) % 1.0) * (m - 1)
        i0 = min(int(u), m - 2)
        t = u - i0
        out.append(values[i0] * (1 - t) + values[i0 + 1] * t)
    return out


def blur(values, radius=2):
    n = len(values)
    return [
        sum(values[max(0, i - radius) : min(n, i + radius + 1)])
        / len(values[max(0, i - radius) : min(n, i + radius + 1)])
        for i in range(n)
    ]


def build_ridges(weeks):
    """One normalised ridgeline per depth layer, far to near."""
    peak = max(weeks) or 1
    norm = [(c / peak) ** 0.62 for c in weeks]
    ridges = []
    for layer in range(LAYERS):
        signal = resample(norm, SAMPLES, phase=0.11 * layer)
        grain = noise_1d(SAMPLES, 5 + 2 * layer, f"ridge-{layer}")
        mix = 0.62 - 0.07 * layer  # near ridges lean on noise, far on the data
        ridges.append(blur([mix * s + (1 - mix) * g for s, g in zip(signal, grain)], 2))
    return ridges


def ridge_bands(ridges, w, h, top=0.30, opacity=1.0):
    """Layered silhouettes: pale at the horizon, full sumi in front."""
    out = ""
    last = len(ridges) - 1
    for layer, values in enumerate(ridges):
        t = layer / last if last else 1.0
        base = h * (top + (1.0 - top - 0.02) * (layer / max(last, 1)))
        amp = h * (0.16 + 0.10 * t)
        pts = [
            (i / (SAMPLES - 1) * w, base - v * amp)
            for i, v in enumerate(values)
        ]
        d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            mx = (x0 + x1) / 2
            d += f"C{mx:.1f} {y0:.1f},{mx:.1f} {y1:.1f},{x1:.1f} {y1:.1f}"
        fill = d + f"L{w:.1f} {h:.1f}L0 {h:.1f}Z"
        shade = ink(0.14 + 0.86 * t)
        out += (
            f'<g class="rg" style="animation-delay:{0.10 + 0.09 * layer:.2f}s">'
            f'<path d="{fill}" fill="{shade}" fill-opacity="{(0.34 + 0.52 * t) * opacity:.2f}" />'
            f'<g class="br"><path d="{d}" pathLength="1" fill="none" stroke="{shade}" '
            f'stroke-width="{1.0 + 0.7 * t:.2f}" stroke-opacity="{0.55 * opacity:.2f}" '
            f'stroke-linecap="round" style="animation-delay:{0.12 * layer:.2f}s" /></g></g>'
        )
    return out


# --------------------------------------------------------------------------- #
# Cards
# --------------------------------------------------------------------------- #

HEAD_W, HEAD_H = 1200, 340

NAME = "Mohammad Faiz Khan"
ROLE = "AI/ML Engineer &#38; Full&#8209;Stack Developer"
TAGLINE = "a builder who thinks in algorithms and dreams in code"
CREDENTIALS = ["B.TECH CSE &#183; AI &#38; ML", "EX&#8209;ACCENTURE", "EX&#8209;ONGC",
               "EX&#8209;TENET NETWORKS"]
AVAILABILITY = "OPEN TO FULL&#8209;TIME ROLES &#38; FREELANCE WORK"


def render_header(user, ridges):
    weeks, _, total = weekly(user)
    peak = max(weeks) or 1
    span = max(len(weeks) - 1, 1)

    # Two brush ticks per bird, one bird for each of the busiest weeks. Only
    # the open right-of-centre sky is used: the left sits under the scrim that
    # carries the name, the far right is where the seal lands.
    birds = ""
    ranked = [i for i in sorted(range(len(weeks)), key=lambda k: weeks[k], reverse=True)
              if weeks[i] > 0 and 0.48 < i / span < 0.86][:4]
    for n, i in enumerate(ranked):
        x = i / span * HEAD_W
        y = HEAD_H * (0.12 + 0.20 * jitter(i, "bird"))
        w = 4.5 + 3.0 * (weeks[i] / peak)
        birds += (
            f'<path class="sp" d="M{x:.1f} {y:.1f}q{w:.1f} {-w * 0.75:.1f} {w * 2:.1f} 0'
            f'q{w:.1f} {-w * 0.75:.1f} {w * 2:.1f} 0" fill="none" stroke="{SUMI_SOFT}" '
            f'stroke-width="1.6" stroke-linecap="round" stroke-opacity="0.7" '
            f'style="animation-delay:{1.0 + 0.16 * n:.2f}s" />'
        )

    grads = f'''<linearGradient id="scrim" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{PAPER}" stop-opacity="0.97" />
      <stop offset="42%" stop-color="{PAPER}" stop-opacity="0.80" />
      <stop offset="78%" stop-color="{PAPER}" stop-opacity="0" />
    </linearGradient>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{RAISED}" />
      <stop offset="100%" stop-color="{SUNK}" />
    </linearGradient>
    <radialGradient id="dawn" cx="74%" cy="26%" r="46%">
      <stop offset="0%" stop-color="{SAKURA}" stop-opacity="0.30" />
      <stop offset="100%" stop-color="{SAKURA}" stop-opacity="0" />
    </radialGradient>
    <clipPath id="headClip"><rect width="{HEAD_W}" height="{HEAD_H}" rx="16" /></clipPath>'''

    body = f'''<g clip-path="url(#headClip)">
    <rect width="{HEAD_W}" height="{HEAD_H}" fill="url(#sky)" />
    <rect width="{HEAD_W}" height="{HEAD_H}" fill="url(#dawn)" />
    <circle cx="{HEAD_W * 0.76:.0f}" cy="{HEAD_H * 0.27:.0f}" r="46" fill="{GOLD}"
            fill-opacity="0.16" />
    {ridge_bands(ridges, HEAD_W, HEAD_H)}{birds}
    <rect width="{HEAD_W}" height="{HEAD_H}" fill="url(#scrim)" />
    <rect width="{HEAD_W}" height="{HEAD_H}" filter="url(#fiber)" opacity="0.045" />
    <g class="tx" style="animation-delay:0.15s">
      <text x="64" y="116" fill="{SUMI}" font-size="52" font-weight="700" letter-spacing="1.5"
            font-family="{SANS}">{NAME}</text>
    </g>
    <g class="tx" style="animation-delay:0.30s">
      <rect x="66" y="138" width="26" height="3" rx="1.5" fill="{VERMILLION}" />
      <text x="104" y="147" fill="{VERMILLION}" font-size="18.5" font-weight="600"
            letter-spacing="0.6" font-family="{SANS}">{ROLE}</text>
    </g>
    <g class="tx" style="animation-delay:0.45s">
      <text x="66" y="186" fill="{SUMI_SOFT}" font-size="14.5" font-family="{MONO}"
            opacity="0.95">{TAGLINE}</text>
    </g>
    <g class="tx" style="animation-delay:0.60s">{chips(CREDENTIALS, 65, 202)}</g>
    <g class="tx" style="animation-delay:0.72s">{status_pill(AVAILABILITY, 65, 238)}</g>
    <g class="tx" style="animation-delay:0.85s">
      <text x="66" y="296" fill="{MIST}" font-size="12.5" font-family="{MONO}">ridgeline brushed from {total:,} contributions this year</text>
    </g>
    {seal(HEAD_W - 96, 84, 40, ["M F K"], 0.95)}
  </g>
  <rect x="0.75" y="0.75" width="{HEAD_W - 1.5}" height="{HEAD_H - 1.5}" rx="16" fill="none"
        stroke="{RULE}" stroke-width="1.5" />'''
    return doc(HEAD_W, HEAD_H, f"{NAME} -- contribution ridgeline", body, grads)


FOOT_W, FOOT_H = 1200, 160

CLOSING = "Still sketching the next system."
INVITE = "Open to full&#8209;time roles and freelance work &#8212; ML systems, computer vision, and data engineering."
CONTACT = ("khan09faiz@gmail.com &#183; portfolio&#8209;faiz&#8209;nu.vercel.app "
           "&#183; Delhi, India")


def render_footer(ridges):
    grads = f'''<linearGradient id="fscrim" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="{PAPER}" stop-opacity="0.96" />
      <stop offset="58%" stop-color="{PAPER}" stop-opacity="0.84" />
      <stop offset="88%" stop-color="{PAPER}" stop-opacity="0.38" />
      <stop offset="100%" stop-color="{PAPER}" stop-opacity="0" />
    </linearGradient>
    <clipPath id="footClip"><rect width="{FOOT_W}" height="{FOOT_H}" rx="16" /></clipPath>'''

    body = f'''<g clip-path="url(#footClip)">
    <rect width="{FOOT_W}" height="{FOOT_H}" fill="{RAISED}" />
    <g opacity="0.85">{ridge_bands(ridges, FOOT_W, FOOT_H * 1.32, top=0.30, opacity=0.85)}</g>
    <rect width="{FOOT_W}" height="{FOOT_H}" fill="url(#fscrim)" />
    <rect width="{FOOT_W}" height="{FOOT_H}" filter="url(#fiber)" opacity="0.04" />
    <g class="tx" style="animation-delay:0.2s">
      <text x="{FOOT_W / 2}" y="66" fill="{SUMI}" font-size="20" font-weight="600"
            text-anchor="middle" font-family="{SANS}">{CLOSING}</text>
      <text x="{FOOT_W / 2}" y="94" fill="{SUMI_SOFT}" font-size="13.5" text-anchor="middle"
            font-family="{SANS}">{INVITE}</text>
      <text x="{FOOT_W / 2}" y="122" fill="{MIST}" font-size="11.5" text-anchor="middle"
            font-family="{MONO}">{CONTACT}</text>
    </g>
  </g>
  <rect x="0.75" y="0.75" width="{FOOT_W - 1.5}" height="{FOOT_H - 1.5}" rx="16" fill="none"
        stroke="{RULE}" stroke-width="1.5" />'''
    return doc(FOOT_W, FOOT_H, "footer", body, grads)


ACT_W, ACT_H = 1200, 300

MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def render_activity(user):
    weeks, starts, total = weekly(user)
    pad_l, pad_r, pad_t, pad_b = 28, 28, 88, 56
    plot_w = ACT_W - pad_l - pad_r
    plot_h = ACT_H - pad_t - pad_b
    base_y = pad_t + plot_h
    peak = max(weeks) or 1
    span = max(len(weeks) - 1, 1)

    pts = [
        (pad_l + i / span * plot_w, base_y - (c / peak) * plot_h)
        for i, c in enumerate(weeks)
    ]
    d = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        mx = (x0 + x1) / 2
        d += f"C{mx:.1f} {y0:.1f},{mx:.1f} {y1:.1f},{x1:.1f} {y1:.1f}"
    area = d + f"L{pts[-1][0]:.1f} {base_y:.1f}L{pts[0][0]:.1f} {base_y:.1f}Z"

    steps = 9
    bands = "".join(
        f'<rect x="{pad_l}" y="{base_y - plot_h * (i + 1) / steps:.1f}" width="{plot_w}" '
        f'height="{plot_h / steps + 1:.1f}" fill="{ink(i / (steps - 1))}" fill-opacity="0.9" />'
        for i in range(steps)
    )
    grid = "".join(
        f'<line x1="{pad_l}" y1="{base_y - plot_h * f:.1f}" x2="{ACT_W - pad_r}" '
        f'y2="{base_y - plot_h * f:.1f}" stroke="{RULE}" stroke-width="1" '
        f'stroke-dasharray="3 5" />'
        for f in (0.25, 0.5, 0.75, 1.0)
    )

    ticks = ""
    seen, last_x = set(), -999.0
    for i, s in enumerate(starts):
        month = s[:7]
        if month in seen:
            continue
        seen.add(month)
        x = pad_l + i / span * plot_w
        if x - last_x < 46:
            continue
        last_x = x
        ticks += (
            f'<line x1="{x:.1f}" y1="{base_y}" x2="{x:.1f}" y2="{base_y + 6}" '
            f'stroke="{MIST}" stroke-width="1" />'
            f'<text x="{x:.1f}" y="{base_y + 22}" fill="{MIST}" font-size="10.5" '
            f'font-family="{MONO}" text-anchor="middle">{MONTHS[int(s[5:7]) - 1]}</text>'
        )

    hi = weeks.index(peak)
    hx = pad_l + hi / span * plot_w
    hy = base_y - plot_h
    anchor = "end" if hx > ACT_W - 120 else "middle"
    callout = (
        f'<line x1="{hx:.1f}" y1="{hy:.1f}" x2="{hx:.1f}" y2="{hy - 12:.1f}" '
        f'stroke="{VERMILLION}" stroke-width="1" stroke-opacity="0.75" />'
        f'<circle class="sp" cx="{hx:.1f}" cy="{hy:.1f}" r="3.5" fill="{VERMILLION}" />'
        f'<text x="{hx - 10 if anchor == "end" else hx:.1f}" y="{hy - 18:.1f}" '
        f'fill="{VERMILLION}" font-size="11" font-family="{MONO}" '
        f'text-anchor="{anchor}">peak {peak}</text>'
    )
    scale = "".join(
        f'<rect x="{pad_l + i * 22}" y="{ACT_H - 23}" width="22" height="5" '
        f'fill="{ink(i / 7)}" />'
        for i in range(8)
    )

    body = f'''{frame(ACT_W, ACT_H, "BRUSH PROFILE &#183; 52 WEEKS", f"{total:,} contributions")}
  {grid}
  <clipPath id="washClip"><path d="{area}" /></clipPath>
  <g clip-path="url(#washClip)">{bands}
    <rect x="{pad_l}" y="{pad_t}" width="{plot_w}" height="{plot_h}" fill="url(#tooth)" />
  </g>
  <path d="{d}" fill="none" stroke="{SUMI}" stroke-width="1.7" stroke-opacity="0.9"
        stroke-linejoin="round" stroke-linecap="round" />
  <line x1="{pad_l}" y1="{base_y}" x2="{ACT_W - pad_r}" y2="{base_y}" stroke="{MIST}"
        stroke-width="1.2" />
  {ticks}{callout}{scale}
  <text x="{pad_l + 8 * 22 + 10}" y="{ACT_H - 18}" fill="{MIST}" font-size="10.5"
        font-family="{MONO}">light &#8594; heavy weekly volume</text>
  {outline(ACT_W, ACT_H)}'''
    return doc(ACT_W, ACT_H, "weekly contribution brush profile", body)


LANG_W, LANG_H = 592, 320


def _worst(row, side):
    total = sum(row)
    if total <= 0 or side <= 0:
        return float("inf")
    return max(
        (side * side * max(row)) / (total * total),
        (total * total) / (side * side * min(row)),
    )


def squarify(values, x, y, w, h):
    """Squarified treemap: areas must already sum to w*h, sorted descending."""
    rects = []
    vals = list(values)
    while vals:
        row, rest = [vals[0]], vals[1:]
        while rest:
            side = min(w, h)
            if _worst(row + [rest[0]], side) <= _worst(row, side):
                row.append(rest.pop(0))
            else:
                break
        total = sum(row)
        if w >= h:
            rw = total / h if h else 0
            ry = y
            for v in row:
                rh = v / rw if rw else 0
                rects.append((x, ry, rw, rh))
                ry += rh
            x, w = x + rw, w - rw
        else:
            rh = total / w if w else 0
            rx = x
            for v in row:
                rw2 = v / rh if rh else 0
                rects.append((rx, y, rw2, rh))
                rx += rw2
            y, h = y + rh, h - rh
        vals = rest
    return rects


def render_languages(user):
    # Count repositories per language: raw byte counts let notebooks swamp everything.
    totals, colors = {}, {}
    for repo in user["repositories"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + 1
            colors[name] = edge["node"]["color"]

    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:7]
    grand = sum(v for _, v in ranked) or 1

    px, py = 28, 64
    pw, ph = LANG_W - 56, LANG_H - 64 - 26
    rects = squarify([v / grand * (pw * ph) for _, v in ranked], px, py, pw, ph)

    tiles = ""
    for i, ((name, count), (rx, ry, rw, rh)) in enumerate(zip(ranked, rects)):
        col = for_paper(colors.get(name))
        gap = 2.0
        bx, by = rx + gap, ry + gap
        bw, bh = max(rw - gap * 2, 1), max(rh - gap * 2, 1)
        fg = readable_on(col)
        share = count / grand * 100
        short = LANG_SHORT.get(name, name)

        inner = ""
        if bw >= 92 and bh >= 62:
            inner = (
                f"{icon(LANG_ICON.get(name, ''), bx + 12, by + 12, 22)}"
                f'<text x="{bx + 12:.1f}" y="{by + 56:.1f}" fill="{fg}" font-size="13.5" '
                f'font-weight="600" font-family="{SANS}">{fit(short, bw - 24, 13.5)}</text>'
                f'<text x="{bx + 12:.1f}" y="{by + 75:.1f}" fill="{fg}" fill-opacity="0.8" '
                f'font-size="11.5" font-family="{MONO}">{count} repos &#183; {share:.0f}%</text>'
            )
        elif bw >= 60 and bh >= 46:
            inner = (
                f"{icon(LANG_ICON.get(name, ''), bx + 10, by + 10, 18)}"
                f'<text x="{bx + 10:.1f}" y="{by + 46:.1f}" fill="{fg}" font-size="11.5" '
                f'font-weight="600" font-family="{SANS}">{fit(short, bw - 20, 11.5)}</text>'
            )
        elif bw >= 30 and bh >= 30:
            inner = icon(LANG_ICON.get(name, ""), bx + bw / 2 - 9, by + bh / 2 - 9, 18)

        tiles += (
            f'<g class="tx" style="animation-delay:{0.07 * i:.2f}s">'
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="7" '
            f'fill="{col}" fill-opacity="0.93" />'
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="7" '
            f'fill="url(#tooth)" />'
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="7" '
            f'fill="none" stroke="{SUMI}" stroke-opacity="0.12" stroke-width="1" />'
            f"{inner}</g>"
        )

    body = f'''{frame(LANG_W, LANG_H, "INK BLOCKS &#183; LANGUAGES",
                      f"{user['repositories']['totalCount']} repos")}
  {tiles}
  {outline(LANG_W, LANG_H)}'''
    return doc(LANG_W, LANG_H, "language composition", body)


STAT_W, STAT_H = 592, 320


def streak_tile(x, y, w, h, value, unit, label, accent, delay):
    return (
        f'<g class="tx" style="animation-delay:{delay:.2f}s">'
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{accent}" '
        f'fill-opacity="0.09" stroke="{accent}" stroke-opacity="0.42" stroke-width="1" />'
        f'<text x="{x + w / 2}" y="{y + 54}" fill="{SUMI}" font-size="42" font-weight="700" '
        f'text-anchor="middle" font-family="{SANS}">{value}</text>'
        f'<text x="{x + w / 2}" y="{y + 74}" fill="{accent}" font-size="11" '
        f'text-anchor="middle" font-family="{MONO}" letter-spacing="1.6">{unit}</text>'
        f'<text x="{x + w / 2}" y="{y + 95}" fill="{SUMI_SOFT}" font-size="10" '
        f'text-anchor="middle" font-family="{MONO}" letter-spacing="1.3">{label}</text>'
        f"</g>"
    )


def render_stats(user):
    days = daily(user)
    current, longest = streaks(days)
    contrib = user["contributionsCollection"]
    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])

    commits = contrib["totalCommitContributions"]
    prs = contrib["totalPullRequestContributions"]
    issues = contrib["totalIssueContributions"]
    mix = [
        ("Commits", commits, VERMILLION),
        ("Pull requests", prs, INDIGO),
        ("Issues", issues, GOLD),
    ]
    top = max(commits, prs, issues, 1)

    tiles = streak_tile(28, 62, 132, 110, current, "DAY" if current == 1 else "DAYS",
                        "CURRENT STREAK", VERMILLION, 0.10)
    tiles += streak_tile(168, 62, 132, 110, longest, "DAY" if longest == 1 else "DAYS",
                         "LONGEST STREAK", INDIGO, 0.18)

    bar_x = 316
    bar_w = STAT_W - 28 - bar_x
    rows = ""
    for i, (label, value, color) in enumerate(mix):
        ry = 82 + i * 38
        rows += (
            f'<g class="tx" style="animation-delay:{0.24 + 0.06 * i:.2f}s">'
            f'<text x="{bar_x}" y="{ry}" fill="{SUMI_SOFT}" font-size="12" '
            f'font-family="{SANS}">{label}</text>'
            f'<text x="{STAT_W - 28}" y="{ry}" fill="{SUMI}" font-size="14" font-weight="700" '
            f'font-family="{MONO}" text-anchor="end">{value:,}</text>'
            f'<rect x="{bar_x}" y="{ry + 8}" width="{bar_w}" height="7" rx="3.5" '
            f'fill="{SUMI}" fill-opacity="0.07" />'
            # Deliberately not wiped: a bar that starts at scaleX(0) is invisible
            # every time the host page re-rasterises the image.
            f'<rect x="{bar_x}" y="{ry + 8}" '
            f'width="{max(bar_w * value / top, 5):.1f}" height="7" rx="3.5" fill="{color}" />'
            f"</g>"
        )

    # Last 30 days on the same wash ramp the ridges use.
    recent = days[-30:]
    peak = max((c for _, c in recent), default=0) or 1
    cell, gap = 14, 4
    strip = ""
    for i, (_, count) in enumerate(recent):
        sx = 28 + i * (cell + gap)
        fill = ink(0.28 + 0.72 * (count / peak)) if count else SUMI
        op = "1" if count else "0.07"
        strip += (
            f'<rect x="{sx}" y="232" width="{cell}" height="{cell}" rx="3.5" '
            f'fill="{fill}" fill-opacity="{op}" />'
        )

    figures = [
        (f"{user['repositories']['totalCount']}", "REPOS"),
        (f"{stars:,}", "STARS"),
        (f"{user['followers']['totalCount']}", "FOLLOWERS"),
    ]
    foot = ""
    for i, (value, label) in enumerate(figures):
        fx = 28 + i * 138
        foot += (
            f'<g class="tx" style="animation-delay:{0.44 + 0.05 * i:.2f}s">'
            f'<text x="{fx}" y="297" fill="{SUMI}" font-size="17" font-weight="700" '
            f'font-family="{SANS}">{value}</text>'
            f'<text x="{fx + 8 + len(value) * 10}" y="297" fill="{MIST}" font-size="10" '
            f'font-family="{MONO}" letter-spacing="1.2">{label}</text></g>'
        )

    body = f'''{frame(STAT_W, STAT_H, "ACTIVITY &#183; 12 MONTHS", "@" + USERNAME)}
  {tiles}{rows}
  <text x="28" y="220" fill="{SUMI_SOFT}" font-size="10" font-family="{MONO}"
        letter-spacing="1.6">LAST 30 DAYS</text>
  {strip}
  <line x1="28" y1="268" x2="{STAT_W - 28}" y2="268" stroke="{RULE}" stroke-width="1" />
  {foot}
  {outline(STAT_W, STAT_H)}'''
    return doc(STAT_W, STAT_H, "activity statistics", body)


CONTACT_W, CONTACT_H = 1200, 200

FORM_URL = "khan09faiz.github.io/khan09faiz"
PORTFOLIO = "portfolio&#8209;faiz&#8209;nu.vercel.app"

ENQUIRIES = [
    ("Freelance project", "scoped work, contract, or consulting", True),
    ("Full&#8209;time role", "open to offers and interviews", False),
    ("Something else", "collaboration, questions, or hello", False),
]


def render_contact():
    """Mirrors the three choices on the linked form. The card itself is a link:
    GitHub strips scripts and forms from README SVG, so nothing here is live."""
    gap = 12
    ow = (CONTACT_W - 48 - gap * 2) / 3
    oy, oh = 62, 62

    options = ""
    for i, (label, hint, checked) in enumerate(ENQUIRIES):
        ox = 24 + i * (ow + gap)
        dot = (
            f'<circle cx="{ox + 26:.1f}" cy="{oy + 31}" r="4.5" fill="{VERMILLION}" />'
            if checked
            else ""
        )
        options += (
            f'<g class="tx" style="animation-delay:{0.12 + 0.07 * i:.2f}s">'
            f'<rect x="{ox:.1f}" y="{oy}" width="{ow:.1f}" height="{oh}" rx="10" '
            f'fill="{SUNK}" stroke="{VERMILLION if checked else MIST}" '
            f'stroke-opacity="{0.45 if checked else 0.35}" stroke-width="1" />'
            f'<circle cx="{ox + 26:.1f}" cy="{oy + 31}" r="9" fill="none" '
            f'stroke="{VERMILLION if checked else MIST}" stroke-width="1.5" />{dot}'
            f'<text x="{ox + 48:.1f}" y="{oy + 27}" fill="{SUMI}" font-size="13.5" '
            f'font-weight="600" font-family="{SANS}">{label}</text>'
            f'<text x="{ox + 48:.1f}" y="{oy + 45}" fill="{MIST}" font-size="11" '
            f'font-family="{MONO}">{hint}</text></g>'
        )

    cta_w = 268
    body = f'''{frame(CONTACT_W, CONTACT_H, "CONTACT &#183; GET IN TOUCH", "pick one, write a line")}
  {options}
  <g class="tx" style="animation-delay:0.34s">
    <rect x="24" y="148" width="{cta_w}" height="30" rx="15" fill="{VERMILLION}"
          fill-opacity="0.10" stroke="{VERMILLION}" stroke-opacity="0.5" stroke-width="1" />
    <text x="{24 + cta_w / 2}" y="167.5" fill="{VERMILLION}" font-size="11.5"
          font-family="{MONO}" font-weight="600" letter-spacing="1.1"
          text-anchor="middle">OPEN THE CONTACT FORM &#8594;</text>
    <text x="{CONTACT_W - 24}" y="162" fill="{MIST}" font-size="11.5" font-family="{MONO}"
          text-anchor="end">{PORTFOLIO} &#183; {FORM_URL}</text>
    <text x="{24 + cta_w + 18}" y="167.5" fill="{SUMI_SOFT}" font-size="11.5"
          font-family="{SANS}">replies land in my inbox</text>
  </g>
  {outline(CONTACT_W, CONTACT_H)}'''
    return doc(CONTACT_W, CONTACT_H, "contact", body)


STACK_W = 1200


def render_stack():
    """Uniform tile grid: a centred glyph over a brand-accented plinth."""
    label_x, grid_x, right = 26, 196, STACK_W - 26
    tile_w, tile_h, gap = 94, 86, 9
    per_row = max(int((right - grid_x + gap) // (tile_w + gap)), 1)

    out = ""
    y = 60
    delay = 0.0
    for bi, (heading, items) in enumerate(STACK):
        if bi:
            out += (
                f'<line x1="26" y1="{y - 17:.1f}" x2="{right}" y2="{y - 17:.1f}" '
                f'stroke="{RULE}" stroke-width="1" />'
            )
        rows = (len(items) + per_row - 1) // per_row
        band_h = rows * tile_h + (rows - 1) * gap

        for i, (name, slug, color) in enumerate(items):
            tx = grid_x + (i % per_row) * (tile_w + gap)
            ty = y + (i // per_row) * (tile_h + gap)
            tone = for_paper(color)
            glyph = icon(slug, tx + tile_w / 2 - 15, ty + 13, 30) if slug else ""
            if glyph:
                mark = glyph
                label = (
                    f'<text x="{tx + tile_w / 2:.1f}" y="{ty + 66}" fill="{SUMI}" '
                    f'font-size="11.5" text-anchor="middle" '
                    f'font-family="{SANS}">{name}</text>'
                )
            else:
                # No devicon: set the name itself as the mark, sized to the tile.
                plain = re.sub(r"&#\d+;", "-", name)
                size = min(17.0, (tile_w - 22) / (len(plain) * 0.62))
                mark = (
                    f'<text x="{tx + tile_w / 2:.1f}" y="{ty + tile_h / 2 + 2:.1f}" '
                    f'fill="{tone}" font-size="{size:.1f}" font-weight="700" '
                    f'letter-spacing="0.4" text-anchor="middle" '
                    f'font-family="{SANS}">{name}</text>'
                )
                label = ""
            out += (
                f'<g class="tx" style="animation-delay:{delay:.2f}s">'
                f'<rect x="{tx:.1f}" y="{ty}" width="{tile_w}" height="{tile_h}" rx="11" '
                f'fill="{SUNK}" stroke="{tone}" stroke-opacity="0.32" stroke-width="1" />'
                f'<rect x="{tx + 26:.1f}" y="{ty + tile_h - 9}" width="{tile_w - 52}" '
                f'height="3" rx="1.5" fill="{tone}" fill-opacity="0.9" />'
                f"{mark}{label}</g>"
            )
            delay += 0.02

        # Shrink rather than let a heading run under the first tile.
        plain = re.sub(r"&#\d+;", "-", heading)
        gutter = grid_x - label_x - 14
        hsize, track = 10.5, 1.6
        while len(plain) * (hsize * 0.62 + track) > gutter and hsize > 7.5:
            hsize -= 0.25
            track = max(0.8, track - 0.05)
        out += (
            f'<text x="{label_x}" y="{y + band_h / 2 + 4:.1f}" fill="{SUMI_SOFT}" '
            f'font-size="{hsize:.2f}" font-family="{MONO}" '
            f'letter-spacing="{track:.2f}">{heading}</text>'
        )
        y += band_h + 34

    height = y - 34 + 26
    body = f'''{frame(STACK_W, height, "TOOLKIT &#183; TECHNOLOGY", "legend")}
  {out}
  {outline(STACK_W, height)}'''
    return doc(STACK_W, height, "technology toolkit", body)


def main():
    user = fetch()
    weeks, _, _ = weekly(user)
    ridges = build_ridges(weeks)

    os.makedirs(OUT_DIR, exist_ok=True)
    cards = {
        "header.svg": render_header(user, ridges),
        "stack.svg": render_stack(),
        "languages.svg": render_languages(user),
        "stats.svg": render_stats(user),
        "activity.svg": render_activity(user),
        "contact.svg": render_contact(),
        "footer.svg": render_footer(ridges),
    }
    for name, svg in cards.items():
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {name} ({len(svg):,} bytes)")


if __name__ == "__main__":
    main()

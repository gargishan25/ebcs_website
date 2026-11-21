"""Small helpers: time zones, access control, text rendering, inline SVG charts."""
import math
import re
from datetime import datetime, timezone
from functools import wraps

from flask import abort, current_app, redirect, request, url_for
from flask_login import current_user
from markupsafe import Markup, escape

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


# ------------------------------------------------------------- time zones ---
def _tz():
    name = current_app.config.get("COACHING_TZ", "America/Los_Angeles")
    try:
        return ZoneInfo(name)
    except Exception:  # missing tz database: degrade to UTC rather than crash
        return timezone.utc


def to_local(dt):
    """UTC-naive -> local-aware."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(_tz())


def local_to_utc(naive_local):
    """Local-naive (from a form) -> UTC-naive (for storage)."""
    return naive_local.replace(tzinfo=_tz()).astimezone(timezone.utc).replace(tzinfo=None)


def local_now():
    return datetime.now(_tz())


def fmt_dt(dt, style="full"):
    d = to_local(dt)
    if d is None:
        return ""
    time = d.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")
    if style == "time":
        return time
    if style == "date":
        return d.strftime("%b %d, %Y").replace(" 0", " ")
    if style == "short":
        return d.strftime("%a %b %d").replace(" 0", " ")
    return f"{d.strftime('%a %b %d').replace(' 0', ' ')}, {time}"


def relative(dt):
    """'in 3d', '2h ago', 'just now'."""
    if dt is None:
        return ""
    delta = (dt - datetime.utcnow()).total_seconds()
    future = delta > 0
    s = abs(delta)
    if s < 60:
        return "just now"
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= size:
            n = int(s // size)
            return f"in {n}{unit}" if future else f"{n}{unit} ago"
    return ""


def minutes_label(m):
    m = int(m or 0)
    h, r = divmod(m, 60)
    if h and r:
        return f"{h}h {r}m"
    if h:
        return f"{h}h"
    return f"{r}m"


# --------------------------------------------------------- access control ---
def roles_required(*roles):
    """Require login plus one of the given roles. Admins pass every check."""

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("coaching.login", next=request.full_path))
            if current_user.role not in roles and not current_user.is_admin:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return deco


def safe_next(target):
    """Only allow same-site relative redirects."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


# ---------------------------------------------------------- text rendering ---
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def render_body(text):
    """Tiny, safe markup: blank line = paragraph, '- ' = bullet, **bold**."""
    if not text:
        return Markup("")
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.splitlines()
        if all(l.strip().startswith("- ") for l in lines):
            items = "".join(f"<li>{_inline(l.strip()[2:])}</li>" for l in lines)
            out.append(f"<ul>{items}</ul>")
        else:
            out.append("<p>" + "<br>".join(_inline(l) for l in lines) + "</p>")
    return Markup("".join(out))


def _inline(s):
    return _BOLD.sub(r"<strong>\1</strong>", str(escape(s)))


# ------------------------------------------------------------- SVG charts ---
def radar_svg(axes, values, size=260, previous=None):
    """Skill radar. axes: [(key,label)], values/previous: {key: 0..5}."""
    n = len(axes)
    cx = cy = size / 2
    r = size / 2 - 42
    pts = lambda vals: " ".join(
        f"{cx + r * (vals.get(k, 0) / 5) * math.sin(2 * math.pi * i / n):.1f},"
        f"{cy - r * (vals.get(k, 0) / 5) * math.cos(2 * math.pi * i / n):.1f}"
        for i, (k, _) in enumerate(axes)
    )
    parts = [f'<svg class="radar" viewBox="0 0 {size} {size}" role="img" aria-label="Skill map">']
    for ring in range(1, 6):
        rr = r * ring / 5
        ring_pts = " ".join(
            f"{cx + rr * math.sin(2 * math.pi * i / n):.1f},{cy - rr * math.cos(2 * math.pi * i / n):.1f}"
            for i in range(n)
        )
        parts.append(f'<polygon class="radar-ring" points="{ring_pts}"/>')
    for i, (k, label) in enumerate(axes):
        ax = cx + r * math.sin(2 * math.pi * i / n)
        ay = cy - r * math.cos(2 * math.pi * i / n)
        parts.append(f'<line class="radar-axis" x1="{cx}" y1="{cy}" x2="{ax:.1f}" y2="{ay:.1f}"/>')
        lx = cx + (r + 18) * math.sin(2 * math.pi * i / n)
        ly = cy - (r + 18) * math.cos(2 * math.pi * i / n)
        anchor = "middle" if abs(lx - cx) < 8 else ("start" if lx > cx else "end")
        parts.append(
            f'<text class="radar-label" x="{lx:.1f}" y="{ly + 4:.1f}" text-anchor="{anchor}">{escape(label)}'
            f'<tspan class="radar-val" dx="4">{values.get(k, 0)}</tspan></text>'
        )
    if previous:
        parts.append(f'<polygon class="radar-prev" points="{pts(previous)}"/>')
    parts.append(f'<polygon class="radar-shape" points="{pts(values)}"/>')
    parts.append("</svg>")
    return Markup("".join(parts))


def bars_svg(values, labels, height=78, unit=""):
    """Compact column chart. Highlights the last bar. The bars stretch to fit
    the card; the date labels are plain HTML underneath so text never
    stretches or overlaps."""
    slot, w_bar = 26, 18
    width = len(values) * slot
    top = max(values) if values and max(values) > 0 else 1
    parts = [f'<div class="bars-wrap"><svg class="bars" viewBox="0 0 {width} {height}" '
             f'preserveAspectRatio="none" role="img">']
    for i, v in enumerate(values):
        h = max(2, height * v / top) if v else 2
        x = i * slot + (slot - w_bar) / 2
        cls = "bar bar-now" if i == len(values) - 1 else "bar"
        parts.append(
            f'<rect class="{cls}" x="{x}" y="{height - h:.1f}" width="{w_bar}" height="{h:.1f}" rx="2">'
            f"<title>{escape(labels[i])}: {v}{unit}</title></rect>"
        )
    parts.append('</svg><div class="bar-labels">')
    parts.extend(f"<span>{escape(l)}</span>" for l in labels)
    parts.append("</div></div>")
    return Markup("".join(parts))


def ring_svg(fraction, size=88, stroke=8):
    """Progress ring, 0..1."""
    fraction = max(0.0, min(1.0, fraction or 0))
    r = (size - stroke) / 2
    c = 2 * math.pi * r
    return Markup(
        f'<svg class="ring" viewBox="0 0 {size} {size}" width="{size}" height="{size}">'
        f'<circle class="ring-track" cx="{size/2}" cy="{size/2}" r="{r}" stroke-width="{stroke}"/>'
        f'<circle class="ring-fill" cx="{size/2}" cy="{size/2}" r="{r}" stroke-width="{stroke}" '
        f'stroke-dasharray="{c:.1f}" stroke-dashoffset="{c * (1 - fraction):.1f}" '
        f'transform="rotate(-90 {size/2} {size/2})"/></svg>'
    )

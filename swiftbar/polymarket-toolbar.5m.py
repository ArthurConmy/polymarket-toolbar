#!/usr/bin/env python3
# <xbar.title>Polymarket Toolbar</xbar.title>
# <xbar.version>1.0.0</xbar.version>
# <xbar.author>Codex</xbar.author>
# <xbar.desc>Configurable Polymarket monitor for the macOS menu bar.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>

import base64
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zlib


SCRIPT_PATH = Path(__file__).resolve()
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
DEFAULT_CLOB = "https://clob.polymarket.com"
DEFAULT_GAMMA = "https://gamma-api.polymarket.com"
DEFAULT_CACHE_PATH = "~/Library/Caches/polymarket-swiftbar-toolbar.json"
DEFAULT_TWENTY20_STATE_PATH = "~/.config/twenty20-toolbar/state.json"
DEFAULT_TITLE_COLOR = "#ffffff"
DEFAULT_MOVE_EPSILON = 0.0025
DEFAULT_METADATA_REFRESH_SECONDS = 6 * 60 * 60
DEFAULT_COLORS = [
    "#34d399",
    "#fbbf24",
    "#60a5fa",
    "#f472b6",
    "#a78bfa",
    "#fb7185",
]

CLOB = DEFAULT_CLOB
GAMMA = DEFAULT_GAMMA
MOVE_EPSILON = DEFAULT_MOVE_EPSILON


def argv_config_path():
    for idx, arg in enumerate(sys.argv[1:]):
        if arg.startswith("--config="):
            return Path(arg.split("=", 1)[1]).expanduser()
        if arg == "--config" and idx + 2 <= len(sys.argv[1:]):
            return Path(sys.argv[idx + 2]).expanduser()
    return None


def config_candidates():
    explicit = argv_config_path()
    if explicit:
        return [explicit]

    env_path = os.environ.get("POLYMARKET_SWIFTBAR_CONFIG") or os.environ.get(
        "POLYMARKET_TOOLBAR_CONFIG"
    )
    if env_path:
        return [Path(env_path).expanduser()]

    return [
        SCRIPT_PATH.with_name("polymarket-markets.json"),
        SCRIPT_PATH.with_suffix(".json"),
        SCRIPT_PATH.parent.parent / "config" / "markets.json",
        SCRIPT_PATH.parent.parent / "config" / "markets.example.json",
        Path("~/.config/polymarket-swiftbar/markets.json").expanduser(),
    ]


def load_config():
    tried = []
    for path in config_candidates():
        tried.append(str(path))
        if path.exists():
            with path.open("r", encoding="utf-8") as handle:
                config = json.load(handle)
            return config, path
    raise FileNotFoundError("no config file found; tried " + ", ".join(tried))


def expand_path(value):
    return Path(os.path.expandvars(str(value))).expanduser()


def load_twenty20_state(config):
    if not config.get("twenty20_title_prefix", False):
        return None
    path = expand_path(config.get("twenty20_state_path", DEFAULT_TWENTY20_STATE_PATH))
    try:
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
            state["_path"] = str(path)
            return state
    except Exception:
        return {"missing": True, "_path": str(path)}


def fetch_json(url, timeout=12):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Origin": "https://polymarket.com",
            "Referer": "https://polymarket.com/",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def dns_resolution_summary(hosts):
    parts = []
    seen = set()
    for host in hosts:
        if not host or host in seen:
            continue
        seen.add(host)
        try:
            ips = sorted(set(socket.gethostbyname_ex(host)[2]))
        except OSError:
            continue
        if ips:
            parts.append(f"{host}->{','.join(ips[:3])}")
    return "; ".join(parts)


def summarize_fetch_error(error):
    text = str(error)
    if "CERTIFICATE_VERIFY_FAILED" in text and "self signed certificate" in text:
        hosts = [
            urllib.parse.urlparse(base).hostname
            for base in (CLOB, GAMMA)
        ]
        summary = dns_resolution_summary(hosts)
        if summary:
            return (
                "network/DNS filter likely: "
                f"{summary}; TLS saw a self-signed certificate, using stale cache"
            )
        return "TLS saw a self-signed certificate; likely network/DNS filter, using stale cache"
    return text


def url_with_query(base, params):
    return f"{base}?{urllib.parse.urlencode(params)}"


def to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def jsonish(value, fallback=None):
    if value is None:
        return [] if fallback is None else fallback
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return [] if fallback is None else fallback
    return value


def slug_from_event_url(url):
    if not url:
        return None
    path = urllib.parse.urlparse(url).path.strip("/")
    parts = [part for part in path.split("/") if part]
    if not parts:
        return None
    if "event" in parts:
        idx = parts.index("event")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return parts[-1]


def event_url_from_slug(slug):
    return f"https://polymarket.com/event/{slug}" if slug else ""


def cache_key_for_metadata(raw):
    source = raw.get("source") or {}
    event_slug = (
        raw.get("event_slug")
        or source.get("event_slug")
        or slug_from_event_url(raw.get("event_url") or source.get("event_url"))
    )
    selector = {
        "market_id": str(raw.get("market_id") or source.get("market_id") or ""),
        "market_slug": raw.get("market_slug") or source.get("market_slug") or "",
        "group_item_title": raw.get("group_item_title")
        or source.get("group_item_title")
        or "",
        "question_contains": raw.get("question_contains")
        or source.get("question_contains")
        or "",
    }
    return event_slug, json.dumps(selector, sort_keys=True)


def fetch_event(event_slug):
    url = url_with_query(f"{GAMMA}/events", {"slug": event_slug})
    data = fetch_json(url)
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    raise RuntimeError(f"no event metadata for slug {event_slug}")


def contains_all(text, needles):
    if isinstance(needles, str):
        needles = [needles]
    lowered = str(text or "").lower()
    return all(str(needle).lower() in lowered for needle in needles)


def select_child_market(event, raw):
    source = raw.get("source") or {}
    markets = event.get("markets") or []
    if not markets:
        raise RuntimeError(f"event {event.get('slug')} has no child markets")

    market_id = str(raw.get("market_id") or source.get("market_id") or "")
    if market_id:
        matches = [market for market in markets if str(market.get("id")) == market_id]
        if matches:
            return matches[0]
        raise RuntimeError(f"market_id {market_id} not found in event {event.get('slug')}")

    market_slug = raw.get("market_slug") or source.get("market_slug")
    if market_slug:
        matches = [market for market in markets if market.get("slug") == market_slug]
        if matches:
            return matches[0]
        raise RuntimeError(f"market_slug {market_slug} not found in event {event.get('slug')}")

    group_title = raw.get("group_item_title") or source.get("group_item_title")
    if group_title:
        matches = [
            market
            for market in markets
            if str(market.get("groupItemTitle", "")).lower() == str(group_title).lower()
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise RuntimeError(f"group_item_title {group_title} matched multiple markets")

    question_contains = raw.get("question_contains") or source.get("question_contains")
    if question_contains:
        matches = [
            market
            for market in markets
            if contains_all(market.get("question", ""), question_contains)
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise RuntimeError("question_contains matched multiple markets")

    open_markets = [market for market in markets if not market.get("closed")]
    if len(open_markets) == 1:
        return open_markets[0]
    if len(markets) == 1:
        return markets[0]
    raise RuntimeError(
        "config must include market_id, market_slug, group_item_title, or question_contains"
    )


def load_metadata(raw, cache, refresh_seconds):
    event_slug, selector_key = cache_key_for_metadata(raw)
    if not event_slug:
        return None, None

    now = int(time.time())
    cache.setdefault("metadata", {})
    metadata_key = f"{event_slug}|{selector_key}"
    cached = cache["metadata"].get(metadata_key)
    if cached and now - int(cached.get("fetched_at", 0)) < refresh_seconds:
        return cached.get("event"), cached.get("market")

    try:
        event = fetch_event(event_slug)
        market = select_child_market(event, raw)
        cache["metadata"][metadata_key] = {
            "fetched_at": now,
            "event": {
                "slug": event.get("slug"),
                "title": event.get("title"),
                "endDate": event.get("endDate"),
            },
            "market": market,
        }
        return cache["metadata"][metadata_key]["event"], market
    except Exception:
        if cached:
            return cached.get("event"), cached.get("market")
        raise


def parse_color(value, index=0):
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(max(0, min(255, int(part))) for part in value)
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r"#?[0-9a-fA-F]{6}", text):
            text = text.lstrip("#")
            return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))
    return parse_color(DEFAULT_COLORS[index % len(DEFAULT_COLORS)])


def color_to_hex(color):
    return "#{:02x}{:02x}{:02x}".format(*color)


def slugify_key(value):
    key = re.sub(r"[^a-zA-Z0-9]+", "_", str(value).lower()).strip("_")
    return key or "market"


def token_from_outcome(raw, market, outcome):
    token_id = raw.get("token_id")
    if token_id:
        return str(token_id)

    tokens_obj = raw.get("tokens") or {}
    yes_token = raw.get("yes_token") or tokens_obj.get("yes")
    no_token = raw.get("no_token") or tokens_obj.get("no")
    if str(outcome).lower() == "yes" and yes_token:
        return str(yes_token)
    if str(outcome).lower() == "no" and no_token:
        return str(no_token)

    if market:
        outcomes = jsonish(market.get("outcomes"), [])
        token_ids = jsonish(market.get("clobTokenIds"), [])
        for idx, name in enumerate(outcomes):
            if str(name).lower() == str(outcome).lower() and idx < len(token_ids):
                return str(token_ids[idx])

    raise RuntimeError("missing token_id and could not resolve outcome token from metadata")


def normalize_market(raw, index, cache, metadata_refresh_seconds):
    source = raw.get("source") or {}
    event_url = raw.get("event_url") or source.get("event_url")
    event_slug = raw.get("event_slug") or source.get("event_slug") or slug_from_event_url(event_url)

    event = None
    market = None
    needs_metadata = not raw.get("token_id")
    needs_metadata = needs_metadata and not (
        raw.get("yes_token") or raw.get("no_token") or raw.get("tokens")
    )
    if event_slug and (
        needs_metadata
        or not raw.get("question")
        or not raw.get("end")
        or not raw.get("market_slug")
    ):
        event, market = load_metadata(raw, cache, metadata_refresh_seconds)

    outcome = raw.get("outcome") or raw.get("display_outcome") or "Yes"
    token_id = token_from_outcome(raw, market, outcome)
    market_id = str(raw.get("market_id") or source.get("market_id") or "")
    if market and not market_id:
        market_id = str(market.get("id") or "")

    bar = raw.get("bar") or raw.get("label") or raw.get("name")
    if not bar and market:
        bar = market.get("groupItemTitle") or market.get("question")
    if not bar:
        bar = market_id or f"Market {index + 1}"

    color = parse_color(raw.get("color"), index)
    question = raw.get("question") or (market or {}).get("question") or bar
    end = raw.get("end") or raw.get("endDate") or (market or {}).get("endDate") or (event or {}).get("endDate")
    if not end:
        raise RuntimeError(f"{bar}: missing end date")

    return {
        "key": raw.get("key") or slugify_key(market_id or bar),
        "bar": str(bar),
        "bar_short": str(raw.get("bar_short") or raw.get("short_label") or bar),
        "name": str(raw.get("name") or question),
        "question": str(question),
        "event_url": event_url or event_url_from_slug(event_slug),
        "event_slug": event_slug or "",
        "market_slug": raw.get("market_slug") or (market or {}).get("slug") or "",
        "market_id": market_id,
        "token_id": token_id,
        "display_outcome": str(outcome),
        "display_label": str(raw.get("display_label") or raw.get("outcome_label") or outcome),
        "end": str(end),
        "color": color,
        "color_hex": color_to_hex(color),
    }


def normalize_config(config, cache):
    global CLOB, GAMMA, MOVE_EPSILON
    CLOB = config.get("clob_base_url") or DEFAULT_CLOB
    GAMMA = config.get("gamma_base_url") or DEFAULT_GAMMA
    MOVE_EPSILON = to_float(config.get("move_epsilon")) or DEFAULT_MOVE_EPSILON
    refresh_seconds = int(
        config.get("metadata_refresh_seconds", DEFAULT_METADATA_REFRESH_SECONDS)
    )

    specs = []
    seen = set()
    for index, raw in enumerate(config.get("markets") or []):
        spec = normalize_market(raw, index, cache, refresh_seconds)
        original_key = spec["key"]
        suffix = 2
        while spec["key"] in seen:
            spec["key"] = f"{original_key}_{suffix}"
            suffix += 1
        seen.add(spec["key"])
        specs.append(spec)
    if not specs:
        raise RuntimeError("config contains no markets")
    return specs


def clob_price(token_id, side):
    data = fetch_json(url_with_query(f"{CLOB}/price", {"token_id": token_id, "side": side}))
    return to_float(data.get("price"))


def clob_midpoint(token_id):
    data = fetch_json(url_with_query(f"{CLOB}/midpoint", {"token_id": token_id}))
    return to_float(data.get("mid"))


def clob_history(token_id, interval="1d", fidelity=15):
    data = fetch_json(
        url_with_query(
            f"{CLOB}/prices-history",
            {"market": token_id, "interval": interval, "fidelity": fidelity},
        )
    )
    history = []
    for point in data.get("history", []):
        price = to_float(point.get("p"))
        timestamp = point.get("t")
        if price is not None and timestamp is not None:
            history.append({"t": int(timestamp), "p": price})
    return history


def fetch_market(spec, config):
    errors = []
    bid = ask = mid = None
    history = []
    token_id = spec["token_id"]
    interval = config.get("history_interval", "1d")
    fidelity = int(config.get("history_fidelity", 15))

    for label, func in [
        ("bid", lambda: clob_price(token_id, "buy")),
        ("ask", lambda: clob_price(token_id, "sell")),
        ("mid", lambda: clob_midpoint(token_id)),
        ("history", lambda: clob_history(token_id, interval=interval, fidelity=fidelity)),
    ]:
        try:
            value = func()
            if label == "bid":
                bid = value
            elif label == "ask":
                ask = value
            elif label == "mid":
                mid = value
            else:
                history = value
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    if mid is None and bid is not None and ask is not None:
        mid = (bid + ask) / 2
    if mid is None and history:
        mid = history[-1]["p"]
    if mid is None:
        raise RuntimeError("; ".join(errors) or "no current price")

    now = int(time.time())
    if not history or history[-1]["t"] < now - 60:
        history = history + [{"t": now, "p": mid}]

    return {
        "key": spec["key"],
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "history": history[-240:],
        "fetched_at": now,
        "errors": errors,
    }


def load_cache(path):
    try:
        with path.open("r", encoding="utf-8") as handle:
            cache = json.load(handle)
        cache.setdefault("markets", {})
        cache.setdefault("metadata", {})
        return cache
    except Exception:
        return {"markets": {}, "metadata": {}}


def save_cache(path, cache):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(cache, handle)
        tmp.replace(path)
    except Exception:
        pass


def percent(value, decimals=1):
    if value is None:
        return "n/a"
    return f"{value * 100:.{decimals}f}%"


def human_duration(seconds):
    seconds = max(0, int(seconds or 0))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def signed_pp(value):
    if value is None:
        return "n/a"
    return f"{value * 100:+.1f}pp"


def compact_signed_pct(value):
    if value is None:
        return "n/a"
    pct = value * 100
    if abs(pct) >= 10:
        return f"{pct:+.0f}%"
    if abs(pct) >= 1:
        return f"{pct:+.1f}%".replace(".0%", "%")
    return f"{pct:+.1f}%"


def price_at_or_before(history, target_ts):
    if not history:
        return None
    previous = history[0]["p"]
    for point in history:
        if point["t"] > target_ts:
            break
        previous = point["p"]
    return previous


def change_since(market, seconds):
    history = market.get("history") or []
    current = market.get("mid")
    if current is None or not history:
        return None
    prior = price_at_or_before(history, int(time.time()) - seconds)
    if prior is None:
        return None
    return current - prior


def last_7am_timestamp():
    # Anchor to the user's local system timezone, not UTC.
    local_now = dt.datetime.now().astimezone()
    seven = local_now.replace(hour=7, minute=0, second=0, microsecond=0)
    if local_now < seven:
        seven -= dt.timedelta(days=1)
    return int(seven.timestamp())


def change_since_7am(market):
    history = market.get("history") or []
    current = market.get("mid")
    if current is None or not history:
        return None
    prior = price_at_or_before(history, last_7am_timestamp())
    if prior is None:
        return None
    return current - prior


def active_title_window():
    return "1h" if int(time.time() // 300) % 2 == 0 else "7am"


def move_color(change):
    if change is None or abs(change) < MOVE_EPSILON:
        return "#9ca3af"
    magnitude = abs(change)
    if change > 0:
        if magnitude >= 0.05:
            return "#047857"
        if magnitude >= 0.02:
            return "#059669"
        return "#10b981"
    if magnitude >= 0.05:
        return "#b91c1c"
    if magnitude >= 0.02:
        return "#dc2626"
    return "#ef4444"


def move_marker(change):
    if change is None or abs(change) < MOVE_EPSILON:
        return "⚪"
    if change > 0:
        return "🟩" if change >= 0.05 else "🟢"
    return "🟥" if change <= -0.05 else "🔴"


def title_marker(market, window):
    change = change_since(market, 3600) if window == "1h" else change_since_7am(market)
    return f"{move_marker(change)}{compact_signed_pct(change)} {window}"


def online_display_count():
    try:
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPDisplaysDataType"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        count = result.stdout.count("Online: Yes")
        return count or 1
    except Exception:
        return 1


def sparkline(history, width=32):
    values = [point["p"] for point in history if point.get("p") is not None]
    if not values:
        return "n/a"

    if len(values) > width:
        values = [
            values[int(i * (len(values) - 1) / max(width - 1, 1))]
            for i in range(width)
        ]

    blocks = "▁▂▃▄▅▆▇█"
    lo = min(values)
    hi = max(values)
    span = hi - lo
    if span < 0.001:
        return blocks[len(blocks) // 2] * len(values)
    chars = []
    for value in values:
        idx = int(round((value - lo) / span * (len(blocks) - 1)))
        chars.append(blocks[max(0, min(idx, len(blocks) - 1))])
    return "".join(chars)


def safe_label(text):
    value = str(text).replace("|", "/")
    return "".join(
        " " if ord(char) < 32 or ord(char) == 127 else char for char in value
    ).strip()


def safe_swiftbar_url(value):
    text = str(value or "").strip()
    if not text:
        return None
    if "|" in text or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 for char in text
    ):
        return None
    parsed = urllib.parse.urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return text


def safe_plain_param(value):
    text = str(value)
    if re.fullmatch(r"[-_./A-Za-z0-9]+", text):
        return text
    return None


def parse_utc(value):
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def countdown(end_iso):
    now = dt.datetime.now(dt.timezone.utc)
    remaining = parse_utc(end_iso) - now
    seconds = int(remaining.total_seconds())
    if seconds <= 0:
        return "ended"
    days, rem = divmod(seconds, 86400)
    hours = rem // 3600
    if days:
        return f"{days}d {hours}h"
    minutes = (rem % 3600) // 60
    return f"{hours}h {minutes}m"


def png_chunk(kind, data):
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def encode_png(width, height, pixels):
    raw = b"".join(b"\x00" + bytes(channel for px in row for channel in px) for row in pixels)
    payload = png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += png_chunk(b"IDAT", zlib.compress(raw, 9))
    payload += png_chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + payload


def put_pixel(pixels, x, y, color):
    height = len(pixels)
    width = len(pixels[0]) if height else 0
    if 0 <= x < width and 0 <= y < height:
        pixels[y][x] = color


def draw_line(pixels, x0, y0, x1, y1, color, thickness=1):
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        radius = max(0, thickness - 1)
        for oy in range(-radius, radius + 1):
            for ox in range(-radius, radius + 1):
                put_pixel(pixels, x0 + ox, y0 + oy, color)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


TINY_FONT = {
    "0": ("111", "101", "101", "101", "111"),
    "1": ("010", "110", "010", "010", "111"),
    "2": ("111", "001", "111", "100", "111"),
    "3": ("111", "001", "111", "001", "111"),
    "4": ("101", "101", "111", "001", "001"),
    "5": ("111", "100", "111", "001", "111"),
    "6": ("111", "100", "111", "101", "111"),
    "7": ("111", "001", "010", "010", "010"),
    "8": ("111", "101", "111", "101", "111"),
    "9": ("111", "101", "111", "001", "111"),
    "%": ("101", "001", "010", "100", "101"),
    "-": ("000", "000", "111", "000", "000"),
}


def draw_text(pixels, x, y, text, color):
    cursor = x
    for char in str(text):
        if char == " ":
            cursor += 2
            continue
        glyph = TINY_FONT.get(char)
        if not glyph:
            cursor += 4
            continue
        for row_idx, row in enumerate(glyph):
            for col_idx, bit in enumerate(row):
                if bit == "1":
                    put_pixel(pixels, cursor + col_idx, y + row_idx, color)
        cursor += 4


def text_width(text):
    total = 0
    for char in str(text):
        total += 2 if char == " " else 4
    return max(0, total - 1)


def nice_axis_bounds(lo, hi):
    lo_pct = max(0, math.floor(lo * 100 / 10) * 10)
    hi_pct = min(100, math.ceil(hi * 100 / 10) * 10)
    if hi_pct - lo_pct < 20:
        center = (hi_pct + lo_pct) / 2
        lo_pct = max(0, math.floor((center - 10) / 10) * 10)
        hi_pct = min(100, math.ceil((center + 10) / 10) * 10)
    return lo_pct / 100, hi_pct / 100


def chart_image(markets, specs, width=320, height=92):
    bg = (17, 24, 39)
    grid = (45, 55, 72)
    axis = (148, 163, 184)
    pixels = [[bg for _ in range(width)] for _ in range(height)]
    left = 34 if width >= 180 else 8
    right, top, bottom = 8, 7, 8

    series = []
    for spec in specs:
        market = markets.get(spec["key"]) or {}
        values = [point["p"] for point in market.get("history", []) if point.get("p") is not None]
        if market.get("mid") is not None:
            values = values + [market["mid"]]
        if values:
            series.append((spec, values[-96:]))

    if not series:
        return None

    all_values = [value for _, values in series for value in values]
    lo = max(0.0, min(all_values) - 0.03)
    hi = min(1.0, max(all_values) + 0.03)
    if hi - lo < 0.08:
        center = (hi + lo) / 2
        lo = max(0.0, center - 0.04)
        hi = min(1.0, center + 0.04)
    lo, hi = nice_axis_bounds(lo, hi)

    major_ticks = [hi, (hi + lo) / 2, lo]
    minor_ticks = [lo + (hi - lo) * i / 4 for i in (1, 3)]
    for tick in minor_ticks:
        y = top + round((hi - tick) / (hi - lo) * (height - top - bottom - 1))
        if width >= 180:
            for x in range(left - 3, left):
                put_pixel(pixels, x, y, grid)

    for tick in major_ticks:
        y = top + round((hi - tick) / (hi - lo) * (height - top - bottom - 1))
        label = f"{round(tick * 100):.0f}%"
        if width >= 180:
            draw_text(pixels, max(0, left - text_width(label) - 5), max(0, y - 2), label, axis)
            for x in range(left - 5, left + 3):
                put_pixel(pixels, x, y, axis)
        for x in range(left, width - right):
            put_pixel(pixels, x, y, grid)

    for i in range(4):
        y = top + round(i * (height - top - bottom - 1) / 3)
        for x in range(left, width - right):
            put_pixel(pixels, x, y, grid)
    if width >= 180:
        for y in range(top, height - bottom):
            put_pixel(pixels, left - 1, y, axis)

    for spec, values in series:
        color = tuple(spec["color"])
        points = []
        for i, value in enumerate(values):
            x = left if len(values) == 1 else left + round(
                i * (width - left - right - 1) / (len(values) - 1)
            )
            y = top + round((hi - value) / (hi - lo) * (height - top - bottom - 1))
            points.append((x, y))
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            draw_line(pixels, x0, y0, x1, y1, color, thickness=2)
        if points:
            x, y = points[-1]
            for oy in range(-2, 3):
                for ox in range(-2, 3):
                    put_pixel(pixels, x + ox, y + oy, color)

    return base64.b64encode(encode_png(width, height, pixels)).decode("ascii")


def fetch_all(specs, config, cache):
    cache.setdefault("markets", {})
    display = {}
    errors = []
    fresh_count = 0

    for spec in specs:
        try:
            market = fetch_market(spec, config)
            display[spec["key"]] = market
            cache["markets"][spec["key"]] = market
            fresh_count += 1
        except Exception as exc:
            cached = cache["markets"].get(spec["key"])
            if cached:
                cached = dict(cached)
                cached["stale"] = True
                display[spec["key"]] = cached
            errors.append(f"{spec['bar']}: {summarize_fetch_error(exc)}")

    return display, errors, fresh_count


def title_piece(spec, market, window, short=False, show_movement=True):
    label = spec["bar_short"] if short else spec["bar"]
    if show_movement:
        return f"{label} {percent(market.get('mid'), 0)} {title_marker(market, window)}"
    return f"{label} {percent(market.get('mid'), 0)}"


def title_for(specs, markets, config, display_count):
    stale = any(market.get("stale") for market in markets.values())
    window = active_title_window()
    use_short = display_count > 1
    if display_count <= 1 and config.get("single_display_uses_short_labels", False):
        use_short = True
    max_markets = int(config.get("title_market_limit", len(specs)))
    show_movement = config.get("title_show_movement", True)
    pieces = [
        title_piece(
            spec,
            markets.get(spec["key"], {}),
            window,
            short=use_short,
            show_movement=show_movement,
        )
        for spec in specs[:max_markets]
    ]
    title = "  ".join(pieces)
    if len(specs) > max_markets:
        title += f" +{len(specs) - max_markets}"
    if stale:
        title += " stale"
    return title


def twenty20_status(state):
    if not state:
        return None
    if state.get("missing"):
        return {
            "title": "20 off",
            "color": "#f59e0b",
            "lines": [
                f"20/20 state missing: {safe_label(state.get('_path', 'unknown'))} | color=#f59e0b"
            ],
        }

    required = int(state.get("required_breaks_today") or 0)
    done = int(state.get("registered_breaks_today") or 0)
    active = float(state.get("active_seconds_today") or 0)
    idle = state.get("idle_seconds")
    holding = bool(state.get("holding"))
    hold = float(state.get("hold_seconds") or 0)
    behind = max(0, required - done)
    color = "#ef4444" if behind else DEFAULT_TITLE_COLOR
    title = f"20 {int(hold)}s" if holding else "20"
    if holding:
        color = DEFAULT_TITLE_COLOR

    lines = [
        f"20/20: {done}/{required} registered | color={color}",
        f"Time on computer today: {human_duration(active)}",
        f"Needed now: floor({human_duration(active)} / 20m) = {required}",
    ]
    if idle is not None:
        lines.append(f"System idle: {human_duration(float(idle))}")
    if behind:
        lines.append(f"Behind by {behind} 20/20/20 break(s) | color=#ef4444")
    else:
        lines.append("20/20 on pace | color=#10b981")
    state_path = state.get("_path")
    if state_path:
        request_path = safe_plain_param(Path(state_path).with_name("register-request"))
        if request_path:
            lines.append(
                "Register 20/20 now | "
                f"bash=/usr/bin/touch param1={request_path} terminal=false refresh=true"
            )
    if state.get("last_break_at"):
        lines.append(f"Last registered: {safe_label(state['last_break_at'])}")
    if state.get("hold_key_codes"):
        codes = ", ".join(str(code) for code in state["hold_key_codes"])
        lines.append(f"Hold key codes: {safe_label(codes)}")
    if state.get("last_event"):
        lines.append(f"Last event: {safe_label(state['last_event'])}")
    if state.get("last_error"):
        lines.append(f"20/20 warning: {safe_label(state['last_error'])} | color=#f59e0b")
    return {"title": title, "color": color, "lines": lines}


def print_open_pages(specs):
    urls = [
        url
        for url in (safe_swiftbar_url(spec.get("event_url")) for spec in specs)
        if url
    ]
    if not urls:
        return
    if len(urls) == 1:
        label = "Open page"
    elif len(urls) == 2:
        label = "Open both pages"
    else:
        label = f"Open {len(urls)} pages"
    params = " ".join(f"param{idx + 1}={url}" for idx, url in enumerate(urls[:8]))
    print(f"{label} | bash=/usr/bin/open {params} terminal=false")


def print_menu(specs, markets, config, config_path, errors):
    display_count = online_display_count()
    title_color = (
        os.environ.get("POLYMARKET_SWIFTBAR_TITLE_COLOR")
        or config.get("title_color")
        or DEFAULT_TITLE_COLOR
    )
    title = title_for(specs, markets, config, display_count)
    twenty20 = twenty20_status(load_twenty20_state(config))
    if twenty20:
        title = f"{twenty20['title']} {title}"
        title_color = twenty20["color"]

    image_option = ""
    if display_count > 1 and config.get("show_mini_chart_on_multi_display", True):
        mini_image = chart_image(markets, specs, width=86, height=18)
        image_option = f" image={mini_image}" if mini_image else ""
    print(f"{safe_label(title)} | color={title_color}{image_option}")
    print("---")
    if display_count <= 1:
        print(safe_label(title))
        print("---")

    if twenty20:
        for line in twenty20["lines"]:
            print(line)
        print("---")

    big_image = chart_image(
        markets,
        specs,
        width=int(config.get("chart_width", 340)),
        height=int(config.get("chart_height", 96)),
    )
    if big_image:
        print(f"1d overlay | image={big_image}")
        print("---")

    for spec in specs:
        market = markets.get(spec["key"], {})
        one_hour = change_since(market, 3600)
        six_hours = change_since(market, 21600)
        one_day = change_since(market, 86400)
        since_7am = change_since_7am(market)
        fetched = market.get("fetched_at")
        fetched_text = "unknown"
        if fetched:
            fetched_text = dt.datetime.fromtimestamp(fetched).strftime("%H:%M:%S")
        status = " stale cache" if market.get("stale") else ""
        event_url = safe_swiftbar_url(spec.get("event_url"))
        row_options = [f"color={move_color(one_hour)}"]
        if event_url:
            row_options.insert(0, f"href={event_url}")
        print(
            f"{safe_label(spec['name'])}: {percent(market.get('mid'))} "
            f"{move_marker(one_hour)} {signed_pp(one_hour)} 1h, "
            f"{move_marker(since_7am)} {signed_pp(since_7am)} since 7am{status} | "
            f"{' '.join(row_options)}"
        )
        print(f"--Bid / ask: {percent(market.get('bid'))} / {percent(market.get('ask'))}")
        print(f"--1d spark: {sparkline(market.get('history') or [])}")
        print(f"--Change 1h: {signed_pp(one_hour)} | color={move_color(one_hour)}")
        print(f"--Change since 7am: {signed_pp(since_7am)} | color={move_color(since_7am)}")
        print(f"--Change 6h / 24h: {signed_pp(six_hours)} / {signed_pp(one_day)}")
        print(f"--Resolves in: {countdown(spec['end'])}")
        print(f"--Last fetched: {fetched_text}")
        print(
            f"--Tracked outcome: {safe_label(spec.get('display_outcome', 'Yes'))} "
            f"({safe_label(spec.get('display_label', ''))})"
        )
        print(f"--Question: {safe_label(spec['question'])}")
        if spec.get("market_id"):
            print(f"--Market ID: {safe_label(spec['market_id'])}")
        if spec.get("market_slug"):
            print(f"--Market slug: {safe_label(spec['market_slug'])}")
        if event_url:
            print(f"--Open Polymarket page | href={event_url}")

    print("---")
    print_open_pages(specs)
    print("Refresh now | refresh=true")
    print("---")
    ids = ", ".join(spec["market_id"] for spec in specs if spec.get("market_id")) or "n/a"
    print(f"Tracks market IDs: {ids} | color=#6b7280")
    print(f"Config: {config_path} | color=#6b7280")
    if errors:
        print("---")
        for error in errors[:6]:
            print(f"Fetch warning: {safe_label(error)} | color=#b45309")


def main():
    try:
        config, config_path = load_config()
        cache_path = expand_path(config.get("cache_path", DEFAULT_CACHE_PATH))
        cache = load_cache(cache_path)
        specs = normalize_config(config, cache)
        markets, errors, fresh_count = fetch_all(specs, config, cache)
        if not markets:
            raise RuntimeError("; ".join(errors) or "no market data")
        if fresh_count or cache.get("metadata"):
            save_cache(cache_path, cache)
        print_menu(specs, markets, config, config_path, errors)
    except Exception as exc:
        print("Polymarket unavailable | color=#b91c1c")
        print("---")
        print(f"Error: {safe_label(exc)}")
        print("Refresh now | refresh=true")


if __name__ == "__main__":
    main()

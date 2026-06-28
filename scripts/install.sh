#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
plugin_dir="${SWIFTBAR_PLUGIN_DIR:-$HOME/Library/Application Support/SwiftBar/Plugins}"
plugin_name="${POLYMARKET_SWIFTBAR_PLUGIN_NAME:-polymarket-toolbar.5m.py}"
config_path="${POLYMARKET_SWIFTBAR_CONFIG_PATH:-$HOME/.config/polymarket-swiftbar/markets.json}"
config_source="${POLYMARKET_SWIFTBAR_CONFIG_SOURCE:-$repo_dir/config/markets.json}"
overwrite_config=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)
      if [[ $# -lt 2 ]]; then
        echo "--config requires a path" >&2
        exit 2
      fi
      config_source="$2"
      shift 2
      ;;
    --config=*)
      config_source="${1#--config=}"
      shift
      ;;
    --overwrite-config)
      overwrite_config=true
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--config PATH] [--overwrite-config]"
      echo
      echo "Installs the SwiftBar plugin and, when needed, the config file."
      echo "By default it uses config/markets.json, then the Republicans 2028 example,"
      echo "then config/markets.example.json."
      echo
      echo "Installed config defaults to:"
      echo "$config_path"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: $0 [--config PATH] [--overwrite-config]" >&2
      exit 2
      ;;
  esac
done

if [[ ! -f "$config_source" ]]; then
  config_source="$repo_dir/examples/republicans-2028-presidential-election.json"
fi

if [[ ! -f "$config_source" ]]; then
  config_source="$repo_dir/config/markets.example.json"
fi

if [[ ! -f "$config_source" ]]; then
  echo "Config source not found: $config_source" >&2
  exit 1
fi

mkdir -p "$plugin_dir"
mkdir -p "$(dirname "$config_path")"
cp "$repo_dir/swiftbar/polymarket-toolbar.5m.py" "$plugin_dir/$plugin_name"
chmod +x "$plugin_dir/$plugin_name"

defaults write com.ameba.SwiftBar "NSStatusItem VisibleCC $plugin_name" -bool true 2>/dev/null || true
defaults write com.ameba.SwiftBar "NSStatusItem Preferred Position $plugin_name" -int 3000 2>/dev/null || true

if [[ "$overwrite_config" == true || ! -f "$config_path" ]]; then
  cp "$config_source" "$config_path"
fi
chmod 0644 "$config_path"

echo "Installed SwiftBar plugin:"
echo "$plugin_dir/$plugin_name"
echo
echo "Config file:"
echo "$config_path"
echo "Config source:"
echo "$config_source"
echo
echo "Refresh in SwiftBar, or run:"
echo "open 'swiftbar://refreshplugin?plugin=$plugin_name'"

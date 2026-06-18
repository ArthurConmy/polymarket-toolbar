#!/usr/bin/env bash
set -euo pipefail

plugin_dir="${SWIFTBAR_PLUGIN_DIR:-$HOME/Library/Application Support/SwiftBar/Plugins}"
plugin_name="${POLYMARKET_SWIFTBAR_PLUGIN_NAME:-polymarket-toolbar.5m.py}"
config_path="${POLYMARKET_SWIFTBAR_CONFIG_PATH:-$HOME/.config/polymarket-swiftbar/markets.json}"
legacy_plugin_config="$plugin_dir/${POLYMARKET_SWIFTBAR_CONFIG_NAME:-polymarket-markets.json}"
remove_config=false

for arg in "$@"; do
  case "$arg" in
    --remove-config)
      remove_config=true
      ;;
    -h|--help)
      echo "Usage: $0 [--remove-config]"
      echo
      echo "Removes the installed SwiftBar plugin. Keeps the installed config unless"
      echo "--remove-config is passed."
      echo
      echo "Config path:"
      echo "$config_path"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: $0 [--remove-config]" >&2
      exit 2
      ;;
  esac
done

plugin_path="$plugin_dir/$plugin_name"

if [[ -e "$plugin_path" ]]; then
  rm -f "$plugin_path"
  echo "Removed SwiftBar plugin:"
  echo "$plugin_path"
else
  echo "SwiftBar plugin was not installed:"
  echo "$plugin_path"
fi

if [[ "$remove_config" == true ]]; then
  if [[ -e "$config_path" ]]; then
    rm -f "$config_path"
    echo
    echo "Removed config:"
    echo "$config_path"
  else
    echo
    echo "Config was not present:"
    echo "$config_path"
  fi
  if [[ -e "$legacy_plugin_config" ]]; then
    rm -f "$legacy_plugin_config"
    echo
    echo "Removed legacy plugin-directory config:"
    echo "$legacy_plugin_config"
  fi
else
  echo
  echo "Kept config:"
  echo "$config_path"
  if [[ -e "$legacy_plugin_config" ]]; then
    echo
    echo "Legacy plugin-directory config still exists:"
    echo "$legacy_plugin_config"
  fi
  echo
  echo "To remove config too, run:"
  echo "$0 --remove-config"
fi

echo
echo "Refresh SwiftBar, or run:"
echo "open 'swiftbar://refreshplugin?plugin=$plugin_name'"

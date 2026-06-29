#!/usr/bin/env bash
set -euo pipefail

plugin_dir="${SWIFTBAR_PLUGIN_DIR:-$HOME/Library/Application Support/SwiftBar/Plugins}"
app_dir="${TWENTY20_APP_DIR:-$HOME/Library/Application Support/polymarket-toolbar}"
watcher_app="${TWENTY20_WATCHER_APP:-$HOME/Applications/Twenty20 Watcher.app}"
state_path="${TWENTY20_STATE_PATH:-$HOME/.config/twenty20-toolbar/state.json}"
launch_agent="$HOME/Library/LaunchAgents/com.arthurconmy.twenty20-watcher.plist"
label="com.arthurconmy.twenty20-watcher"
remove_state=false

for arg in "$@"; do
  case "$arg" in
    --remove-state)
      remove_state=true
      ;;
    -h|--help)
      echo "Usage: $0 [--remove-state]"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

launchctl bootout "gui/$UID/$label" 2>/dev/null || true
rm -f "$launch_agent"
rm -f "$plugin_dir/twenty20-toolbar.1m.py"
rm -f "$plugin_dir/00-twenty20-toolbar.1m.py"
rm -f "$app_dir/twenty20-watcher"
rm -f "$app_dir/twenty20-watcher-launcher.zsh"
rm -rf "$watcher_app"

if [[ "$remove_state" == true ]]; then
  rm -f "$state_path"
fi

echo "Removed 20/20/20 SwiftBar plugin and watcher."
if [[ "$remove_state" == true ]]; then
  echo "Removed state: $state_path"
else
  echo "Kept state: $state_path"
fi

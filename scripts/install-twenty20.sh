#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
plugin_dir="${SWIFTBAR_PLUGIN_DIR:-$HOME/Library/Application Support/SwiftBar/Plugins}"
app_dir="${TWENTY20_APP_DIR:-$HOME/Library/Application Support/polymarket-toolbar}"
state_path="${TWENTY20_STATE_PATH:-$HOME/.config/twenty20-toolbar/state.json}"
launch_agent="$HOME/Library/LaunchAgents/com.arthurconmy.twenty20-watcher.plist"
binary="$app_dir/twenty20-watcher"
label="com.arthurconmy.twenty20-watcher"

mkdir -p "$plugin_dir" "$app_dir" "$(dirname "$state_path")" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

swiftc "$repo_dir/twenty20/twenty20-watcher.swift" -o "$binary"
chmod +x "$binary"

cp "$repo_dir/swiftbar/twenty20-toolbar.1m.py" "$plugin_dir/twenty20-toolbar.1m.py"
chmod +x "$plugin_dir/twenty20-toolbar.1m.py"

cat > "$launch_agent" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$label</string>
  <key>ProgramArguments</key>
  <array>
    <string>$binary</string>
    <string>--state</string>
    <string>$state_path</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$HOME/Library/Logs/twenty20-watcher.out.log</string>
  <key>StandardErrorPath</key>
  <string>$HOME/Library/Logs/twenty20-watcher.err.log</string>
</dict>
</plist>
PLIST

launchctl bootout "gui/$UID/$label" 2>/dev/null || true
launchctl bootstrap "gui/$UID" "$launch_agent"
launchctl kickstart -k "gui/$UID/$label"

echo "Installed 20/20/20 SwiftBar plugin:"
echo "$plugin_dir/twenty20-toolbar.1m.py"
echo
echo "Installed watcher:"
echo "$binary"
echo
echo "LaunchAgent:"
echo "$launch_agent"
echo
echo "State file:"
echo "$state_path"
echo
echo "If F6 is not detected, grant Accessibility permission to twenty20-watcher"
echo "or to the terminal app that installed it, then rerun this script."

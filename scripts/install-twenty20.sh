#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
  echo "Do not run this installer with sudo." >&2
  echo "This is a per-user LaunchAgent and must be installed from the normal user shell." >&2
  exit 2
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
plugin_dir="${SWIFTBAR_PLUGIN_DIR:-$HOME/Library/Application Support/SwiftBar/Plugins}"
app_dir="${TWENTY20_APP_DIR:-$HOME/Library/Application Support/polymarket-toolbar}"
state_path="${TWENTY20_STATE_PATH:-$HOME/.config/twenty20-toolbar/state.json}"
launch_agent="$HOME/Library/LaunchAgents/com.arthurconmy.twenty20-watcher.plist"
binary="$app_dir/twenty20-watcher"
label="com.arthurconmy.twenty20-watcher"

source_file="$repo_dir/twenty20/twenty20-watcher.swift"

mkdir -p "$plugin_dir" "$app_dir" "$(dirname "$state_path")" "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

if [[ ! -x "$binary" || "$source_file" -nt "$binary" ]]; then
  rm -f "$binary"
  swiftc "$source_file" -o "$binary"
  codesign --force --sign - --identifier "$label" "$binary" >/dev/null 2>&1 || true
  chmod +x "$binary"
fi

# The stable UI is now the Polymarket SwiftBar item prefixed with 20/20 state.
# Remove any standalone 20/20 status item so macOS does not reorder/flicker items.
rm -f "$plugin_dir/twenty20-toolbar.1m.py" "$plugin_dir/00-twenty20-toolbar.1m.py"
defaults delete com.ameba.SwiftBar "NSStatusItem VisibleCC twenty20-toolbar.1m.py" 2>/dev/null || true
defaults delete com.ameba.SwiftBar "NSStatusItem Preferred Position twenty20-toolbar.1m.py" 2>/dev/null || true
defaults delete com.ameba.SwiftBar "NSStatusItem VisibleCC 00-twenty20-toolbar.1m.py" 2>/dev/null || true
defaults delete com.ameba.SwiftBar "NSStatusItem Preferred Position 00-twenty20-toolbar.1m.py" 2>/dev/null || true

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

echo "Installed watcher:"
echo "$binary"
echo
echo "LaunchAgent:"
echo "$launch_agent"
echo
echo "State file:"
echo "$state_path"
echo
echo "If Right Option is not detected, grant Accessibility permission to twenty20-watcher"
echo "or to the terminal app that installed it, then restart the watcher:"
echo "launchctl kickstart -k gui/$UID/$label"

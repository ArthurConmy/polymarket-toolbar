#!/usr/bin/env bash
set -euo pipefail

plugin_name="${POLYMARKET_SWIFTBAR_PLUGIN_NAME:-polymarket-toolbar.5m.py}"

defaults -currentHost write -globalDomain NSStatusItemSpacing -int 6
defaults -currentHost write -globalDomain NSStatusItemSelectionPadding -int 4
defaults write com.ameba.SwiftBar "NSStatusItem Preferred Position $plugin_name" -float 3000

killall ControlCenter 2>/dev/null || true
killall SystemUIServer 2>/dev/null || true

echo "Applied compact menu-bar spacing and pinned SwiftBar position for $plugin_name."
echo "Restart SwiftBar if the item has not moved yet."

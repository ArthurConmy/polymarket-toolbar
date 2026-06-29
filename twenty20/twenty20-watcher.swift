import AppKit
import ApplicationServices
import Foundation
import IOKit

private let defaultStatePath = ("~/.config/twenty20-toolbar/state.json" as NSString).expandingTildeInPath
private let defaultHoldKeyCodes: Set<Int64> = [61]
private let holdTargetSeconds = 20.0
private let activeBucketSeconds = 20.0 * 60.0
private let idleCutoffSeconds = 5.0 * 60.0

struct State: Codable {
    var date: String
    var activeSecondsToday: Double
    var registeredBreaksToday: Int
    var requiredBreaksToday: Int
    var lastBreakAt: String?
    var lastUpdatedAt: String
    var watcherPID: Int32
    var holding: Bool
    var holdStartedAt: String?
    var holdSeconds: Double
    var idleSeconds: Double?
    var countingActiveTime: Bool?
    var eventTapEnabled: Bool
    var accessibilityTrusted: Bool
    var holdKeyCodes: [Int64]?
    var lastEvent: String?
    var lastError: String?

    enum CodingKeys: String, CodingKey {
        case date
        case activeSecondsToday = "active_seconds_today"
        case registeredBreaksToday = "registered_breaks_today"
        case requiredBreaksToday = "required_breaks_today"
        case lastBreakAt = "last_break_at"
        case lastUpdatedAt = "last_updated_at"
        case watcherPID = "watcher_pid"
        case holding
        case holdStartedAt = "hold_started_at"
        case holdSeconds = "hold_seconds"
        case idleSeconds = "idle_seconds"
        case countingActiveTime = "counting_active_time"
        case eventTapEnabled = "event_tap_enabled"
        case accessibilityTrusted = "accessibility_trusted"
        case holdKeyCodes = "hold_key_codes"
        case lastEvent = "last_event"
        case lastError = "last_error"
    }
}

final class Twenty20Watcher {
    private let stateURL: URL
    private let encoder = JSONEncoder()
    private let decoder = JSONDecoder()
    private let isoFormatter: ISO8601DateFormatter
    private let dayFormatter: DateFormatter
    private var state: State
    private var lastTick: Date
    private var holdStart: Date?
    private var registeredThisHold = false
    private var eventTap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private let holdKeyCodes: Set<Int64>

    init(statePath: String) {
        stateURL = URL(fileURLWithPath: (statePath as NSString).expandingTildeInPath)
        holdKeyCodes = Twenty20Watcher.parseHoldKeyCodes(
            ProcessInfo.processInfo.environment["TWENTY20_HOLD_KEY_CODES"]
        )
        isoFormatter = ISO8601DateFormatter()
        isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        dayFormatter = DateFormatter()
        dayFormatter.calendar = Calendar(identifier: .gregorian)
        dayFormatter.locale = Locale(identifier: "en_US_POSIX")
        dayFormatter.timeZone = .current
        dayFormatter.dateFormat = "yyyy-MM-dd"
        lastTick = Date()
        state = Twenty20Watcher.loadState(
            from: stateURL,
            decoder: decoder,
            today: dayFormatter.string(from: Date()),
            now: isoFormatter.string(from: Date())
        )
        resetForTodayIfNeeded()
        save()
    }

    func run() {
        setupEventTap()
        Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.tick()
        }
        Timer.scheduledTimer(withTimeInterval: 0.2, repeats: true) { [weak self] _ in
            self?.checkHold()
        }
        RunLoop.main.run()
    }

    private static func loadState(
        from url: URL,
        decoder: JSONDecoder,
        today: String,
        now: String
    ) -> State {
        if let data = try? Data(contentsOf: url),
           let decoded = try? decoder.decode(State.self, from: data) {
            return decoded
        }
        return State(
            date: today,
            activeSecondsToday: 0,
            registeredBreaksToday: 0,
            requiredBreaksToday: 0,
            lastBreakAt: nil,
            lastUpdatedAt: now,
            watcherPID: getpid(),
            holding: false,
            holdStartedAt: nil,
            holdSeconds: 0,
            idleSeconds: nil,
            countingActiveTime: true,
            eventTapEnabled: false,
            accessibilityTrusted: AXIsProcessTrusted(),
            holdKeyCodes: nil,
            lastEvent: nil,
            lastError: nil
        )
    }

    private static func parseHoldKeyCodes(_ raw: String?) -> Set<Int64> {
        guard let raw else {
            return defaultHoldKeyCodes
        }
        let parsed = raw
            .split(separator: ",")
            .compactMap { Int64(String($0).trimmingCharacters(in: .whitespacesAndNewlines)) }
        if parsed.isEmpty {
            return defaultHoldKeyCodes
        }
        return Set(parsed)
    }

    private func holdKeyCodeList() -> String {
        holdKeyCodes.sorted().map(String.init).joined(separator: ",")
    }

    private func todayString() -> String {
        dayFormatter.string(from: Date())
    }

    private func nowString() -> String {
        isoFormatter.string(from: Date())
    }

    private func resetForTodayIfNeeded() {
        let today = todayString()
        if state.date != today {
            state.date = today
            state.activeSecondsToday = 0
            state.registeredBreaksToday = 0
            state.requiredBreaksToday = 0
            state.lastBreakAt = nil
            state.holding = false
            state.holdStartedAt = nil
            state.holdSeconds = 0
            holdStart = nil
            registeredThisHold = false
        }
        state.requiredBreaksToday = Int(floor(state.activeSecondsToday / activeBucketSeconds))
        state.watcherPID = getpid()
        state.accessibilityTrusted = AXIsProcessTrusted()
        state.holdKeyCodes = holdKeyCodes.sorted()
        state.lastUpdatedAt = nowString()
    }

    private func tick() {
        let now = Date()
        resetForTodayIfNeeded()
        let delta = max(0, min(now.timeIntervalSince(lastTick), 5.0))
        let idleSeconds = systemIdleSeconds()
        let countingActiveTime = idleSeconds.map { $0 < idleCutoffSeconds } ?? true
        state.idleSeconds = idleSeconds
        state.countingActiveTime = countingActiveTime
        if countingActiveTime {
            state.activeSecondsToday += delta
        }
        state.requiredBreaksToday = Int(floor(state.activeSecondsToday / activeBucketSeconds))
        lastTick = now
        save()
    }

    private func systemIdleSeconds() -> Double? {
        let service = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("IOHIDSystem"))
        guard service != 0 else {
            return nil
        }
        defer { IOObjectRelease(service) }

        guard let unmanaged = IORegistryEntryCreateCFProperty(
            service,
            "HIDIdleTime" as CFString,
            kCFAllocatorDefault,
            0
        ) else {
            return nil
        }

        let value = unmanaged.takeRetainedValue()
        guard let number = value as? NSNumber else {
            return nil
        }
        return number.doubleValue / 1_000_000_000.0
    }

    private func save() {
        resetForTodayIfNeeded()
        do {
            let directory = stateURL.deletingLastPathComponent()
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            let data = try encoder.encode(state)
            let tmp = stateURL.appendingPathExtension("tmp")
            try data.write(to: tmp, options: [.atomic])
            if FileManager.default.fileExists(atPath: stateURL.path) {
                _ = try FileManager.default.replaceItemAt(stateURL, withItemAt: tmp)
            } else {
                try FileManager.default.moveItem(at: tmp, to: stateURL)
            }
        } catch {
            fputs("twenty20-watcher save failed: \(error)\n", stderr)
        }
    }

    private func setupEventTap() {
        let accessibilityTrusted = AXIsProcessTrusted()
        state.accessibilityTrusted = accessibilityTrusted

        let mask = 1 << CGEventType.flagsChanged.rawValue

        let callback: CGEventTapCallBack = { _, type, event, refcon in
            guard let refcon else { return Unmanaged.passUnretained(event) }
            let watcher = Unmanaged<Twenty20Watcher>.fromOpaque(refcon).takeUnretainedValue()
            watcher.handleEvent(type: type, event: event)
            return Unmanaged.passUnretained(event)
        }

        let refcon = Unmanaged.passUnretained(self).toOpaque()
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: CGEventMask(mask),
            callback: callback,
            userInfo: refcon
        ) else {
            state.eventTapEnabled = false
            if accessibilityTrusted {
                state.lastError = "Event tap unavailable. Restart the watcher or reinstall the 20/20 extension."
            } else {
                state.lastError = "Accessibility permission missing for Twenty20 Watcher.app."
            }
            save()
            return
        }

        eventTap = tap
        runLoopSource = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetMain(), runLoopSource, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
        state.eventTapEnabled = true
        state.lastError = accessibilityTrusted ? nil : "Accessibility permission missing for Twenty20 Watcher.app."
        state.lastEvent = "watching hold keyCodes=\(holdKeyCodeList())"
        save()
    }

    private func modifierMask(for keyCode: Int64) -> CGEventFlags? {
        switch keyCode {
        case 56, 60:
            return .maskShift
        case 58, 61:
            return .maskAlternate
        case 59, 62:
            return .maskControl
        case 54, 55:
            return .maskCommand
        default:
            return nil
        }
    }

    private func handleEvent(type: CGEventType, event: CGEvent) {
        if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
            if let eventTap {
                CGEvent.tapEnable(tap: eventTap, enable: true)
            }
            state.eventTapEnabled = true
            state.lastEvent = "event tap re-enabled"
            save()
            return
        }

        guard type == .flagsChanged else {
            return
        }
        let keyCode = event.getIntegerValueField(.keyboardEventKeycode)
        state.lastEvent = "flagsChanged keyCode=\(keyCode) flags=\(event.flags.rawValue)"

        if holdKeyCodes.contains(keyCode) {
            let source = "hold keyCode \(keyCode)"
            if let mask = modifierMask(for: keyCode) {
                if event.flags.contains(mask) {
                    beginHold(source: source)
                } else {
                    endHold(source: source)
                }
            } else {
                beginHold(source: source)
            }
        }
        save()
    }

    private func beginHold(source: String) {
        if holdStart == nil {
            holdStart = Date()
            registeredThisHold = false
            state.holding = true
            state.holdStartedAt = nowString()
            state.holdSeconds = 0
            state.lastEvent = "\(source) down"
            save()
        }
    }

    private func endHold(source: String) {
        if holdStart != nil {
            state.lastEvent = "\(source) up"
        }
        holdStart = nil
        registeredThisHold = false
        state.holding = false
        state.holdStartedAt = nil
        state.holdSeconds = 0
        save()
    }

    private func checkHold() {
        guard let holdStart else { return }
        resetForTodayIfNeeded()
        let seconds = Date().timeIntervalSince(holdStart)
        state.holding = true
        state.holdSeconds = seconds
        if seconds >= holdTargetSeconds && !registeredThisHold {
            registeredThisHold = true
            registerBreak()
            flashWhite()
        }
        save()
    }

    private func registerBreak() {
        resetForTodayIfNeeded()
        state.registeredBreaksToday += 1
        state.lastBreakAt = nowString()
        state.lastEvent = "registered 20/20/20"
    }

    private func flashWhite() {
        DispatchQueue.main.async {
            let windows = NSScreen.screens.map { screen -> NSWindow in
                let window = NSWindow(
                    contentRect: screen.frame,
                    styleMask: .borderless,
                    backing: .buffered,
                    defer: false,
                    screen: screen
                )
                window.level = .screenSaver
                window.backgroundColor = .white
                window.isOpaque = true
                window.ignoresMouseEvents = true
                window.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
                window.makeKeyAndOrderFront(nil)
                return window
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.18) {
                for window in windows {
                    window.orderOut(nil)
                }
            }
        }
    }
}

func argumentValue(named name: String) -> String? {
    let args = CommandLine.arguments
    for index in args.indices {
        if args[index] == name, index + 1 < args.count {
            return args[index + 1]
        }
        if args[index].hasPrefix("\(name)=") {
            return String(args[index].dropFirst(name.count + 1))
        }
    }
    return nil
}

let statePath = argumentValue(named: "--state") ?? defaultStatePath
let watcher = Twenty20Watcher(statePath: statePath)
watcher.run()

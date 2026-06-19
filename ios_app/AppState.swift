//
//  AppState.swift
//  AutoBot iOS - 全局状态管理
//
//  关键修复:
//  - log() 不再把每条日志发送到服务器 (避免 WebSocket 日志循环)
//  - 使用 URLComponents 构建 WebSocket URL
//  - 简洁的连接流程
//

import Foundation
import UIKit
import WebKit
import SwiftUI
import Combine

@MainActor
class AppState: ObservableObject {
    // 连接状态
    @Published var connectionStatus: ConnectionStatus = .disconnected
    @Published var serverAddress: String = "http://192.168.1.8:8550"
    @Published var logs: [LogEntry] = []

    // 当前平台
    @Published var currentPlatform: String = ""

    // WebSocket 管理器
    private var wsManager: WebSocketManager?

    // 设备信息
    var deviceInfo: [String: Any] {
        let device = UIDevice.current
        return [
            "device_id": device.identifierForVendor?.uuidString ?? UUID().uuidString,
            "device_name": device.name,
            "system_version": "\(device.systemName) \(device.systemVersion)",
            "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0",
            "model": device.model,
            "screen_width": Int(UIScreen.main.bounds.width),
            "screen_height": Int(UIScreen.main.bounds.height)
        ]
    }

    // WebView
    weak var webView: WKWebView?

    private func evaluateJS(_ js: String) async throws -> [String: Any] {
        guard let wv = webView else {
            return ["success": false, "message": "WebView 未准备好"]
        }
        return try await withCheckedThrowingContinuation { continuation in
            wv.evaluateJavaScript(js) { result, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }
                if let dict = result as? [String: Any] {
                    continuation.resume(returning: dict)
                } else if let bool = result as? Bool {
                    continuation.resume(returning: ["success": bool])
                } else if let str = result as? String {
                    continuation.resume(returning: ["result": str])
                } else {
                    continuation.resume(returning: ["success": true])
                }
            }
        }
    }

    func startup() {
        log("🚀 AutoBot 启动")

        // 从 UserDefaults 读取
        if let saved = UserDefaults.standard.string(forKey: "serverAddress"), !saved.isEmpty {
            serverAddress = saved
        }

        connect()
    }

    // 规范化并保存地址
    func saveServerAddress() {
        var addr = serverAddress
            .trimmingCharacters(in: .whitespacesAndNewlines)

        if !addr.lowercased().hasPrefix("http://") && !addr.lowercased().hasPrefix("https://") {
            addr = "http://" + addr
        }

        while addr.hasSuffix("/") {
            addr.removeLast()
        }

        serverAddress = addr
        UserDefaults.standard.set(addr, forKey: "serverAddress")
    }

    func connect() {
        saveServerAddress()
        log("🔌 连接服务器: \(serverAddress)")
        connectionStatus = .connecting

        disconnect()

        Task {
            await doConnect()
        }
    }

    // 构建 WebSocket URL
    private func buildWebSocketURL() -> URL? {
        // 先尝试用 URLComponents
        if let components = URLComponents(string: serverAddress) {
            var wsComponents = components
            if components.scheme == "http" {
                wsComponents.scheme = "ws"
            } else if components.scheme == "https" {
                wsComponents.scheme = "wss"
            }
            wsComponents.path = "/ws/app/connect"
            if let url = wsComponents.url {
                return url
            }
        }

        // fallback：手动拼接
        var hostStr = serverAddress
        for prefix in ["http://", "https://"] {
            if let range = hostStr.range(of: prefix, options: .caseInsensitive) {
                hostStr.removeSubrange(range)
                break
            }
        }
        if let slashRange = hostStr.firstIndex(of: "/") {
            hostStr = String(hostStr[..<slashRange])
        }
        return URL(string: "ws://\(hostStr)/ws/app/connect")
    }

    private func doConnect() async {
        guard let wsURL = buildWebSocketURL() else {
            log("❌ 无效的服务器地址")
            connectionStatus = .error("无效地址")
            return
        }

        wsManager = WebSocketManager(url: wsURL)

        wsManager?.onLog = { [weak self] message in
            Task { @MainActor in
                self?.log("   \(message)")
            }
        }

        wsManager?.onConnected = { [weak self] in
            Task { @MainActor in
                self?.log("✅ 已连接")
                self?.connectionStatus = .connected
                self?.sendRegister()
            }
        }

        wsManager?.onDisconnected = { [weak self] reason in
            Task { @MainActor in
                self?.log("⚠️ 已断开: \(reason)")
                self?.connectionStatus = .disconnected
            }
        }

        wsManager?.onMessage = { [weak self] message in
            Task { @MainActor in
                self?.handleMessage(message)
            }
        }

        wsManager?.onError = { [weak self] error in
            Task { @MainActor in
                self?.log("❌ 错误: \(error)")
                self?.connectionStatus = .error(error)
            }
        }

        wsManager?.connect()
    }

    func disconnect() {
        wsManager?.disconnect()
        wsManager = nil
        connectionStatus = .disconnected
    }

    private func sendRegister() {
        var msg: [String: Any] = ["type": "register"]
        msg.merge(deviceInfo) { (_, new) in new }
        wsManager?.sendJSON(msg)
        log("📨 设备已注册")
    }

    private func handleMessage(_ message: [String: Any]) {
        let type = message["type"] as? String ?? ""

        switch type {
        case "welcome":
            log("🎉 注册成功")

        case "command":
            executeCommand(message)

        case "pong":
            break

        default:
            log("📩 消息: \(type)")
        }
    }

    private func executeCommand(_ message: [String: Any]) {
        let commandId = message["command_id"] as? String ?? ""
        let action = message["action"] as? String ?? ""
        let platform = message["platform"] as? String ?? ""
        let params = message["params"] as? [String: Any] ?? [:]

        log("⚙️ 执行: \(action)")

        Task {
            var result: [String: Any] = [
                "type": "result",
                "command_id": commandId,
                "success": false,
                "message": ""
            ]

            do {
                switch action {
                case "open_platform":
                    try await actionOpenPlatform(params)
                    result["success"] = true
                    result["message"] = "已打开"

                case "scroll":
                    try await actionScroll(params)
                    result["success"] = true
                    result["message"] = "已滚动"

                case "like":
                    try await actionLike(params)
                    result["success"] = true
                    result["message"] = "已点赞"

                case "comment":
                    try await actionComment(params)
                    result["success"] = true
                    result["message"] = "已评论"

                case "follow":
                    try await actionFollow(params)
                    result["success"] = true
                    result["message"] = "已关注"

                case "message":
                    try await actionMessage(params)
                    result["success"] = true
                    result["message"] = "已私信"

                case "custom_js":
                    if let js = params["js"] as? String {
                        let data = try await evaluateJS(js)
                        result["success"] = true
                        result["data"] = data
                    }
                default:
                    result["message"] = "未知操作"
                }
            } catch {
                result["success"] = false
                result["message"] = "失败: \(error.localizedDescription)"
            }

            wsManager?.sendJSON(result)
            log("✅ \(action) 完成")
        }
    }

    // ====== 操作 ======

    private func actionOpenPlatform(_ params: [String: Any]) async throws {
        currentPlatform = params["platform"] as? String ?? "xiaohongshu"

        let urlString = currentPlatform == "douyin"
            ? "https://www.douyin.com"
            : "https://www.xiaohongshu.com"

        guard let url = URL(string: urlString) else {
            throw NSError(domain: "AutoBot", code: -1, userInfo: [:])
        }

        webView?.load(URLRequest(url: url))
        log("🌐 打开: \(urlString)")
        try await Task.sleep(nanoseconds: 3_000_000_000)
    }

    private func actionScroll(_ params: [String: Any]) async throws {
        let direction = params["direction"] as? String ?? "up"
        let count = params["count"] as? Int ?? 1
        let interval = params["interval"] as? Double ?? 1.5

        log("📜 滚动 \(direction) x\(count)")

        for i in 0..<count {
            let js = direction == "up"
                ? "window.scrollBy(0, window.innerHeight * 0.8); true;"
                : "window.scrollBy(0, -window.innerHeight * 0.8); true;"
            _ = try await evaluateJS(js)
            if i < count - 1 {
                try await Task.sleep(nanoseconds: UInt64(interval * 1_000_000_000))
            }
        }
    }

    private func actionLike(_ params: [String: Any]) async throws {
        log("❤️ 点赞")
        let js = AutomationScripts.likeScript(for: currentPlatform)
        _ = try await evaluateJS(js)
    }

    private func actionComment(_ params: [String: Any]) async throws {
        let text = params["text"] as? String ?? "很棒！"
        log("💬 评论: \(text)")
        let js = AutomationScripts.commentScript(for: currentPlatform, text: text)
        _ = try await evaluateJS(js)
    }

    private func actionFollow(_ params: [String: Any]) async throws {
        log("👤 关注")
        let js = AutomationScripts.followScript(for: currentPlatform)
        _ = try await evaluateJS(js)
    }

    private func actionMessage(_ params: [String: Any]) async throws {
        let text = params["text"] as? String ?? "你好！"
        log("📨 私信: \(text)")
        let js = AutomationScripts.messageScript(for: currentPlatform, text: text)
        _ = try await evaluateJS(js)
    }

    // ====== 日志 ======
    func log(_ message: String) {
        let entry = LogEntry(text: message, time: Date())
        logs.append(entry)
        // 限制最多 200 条日志
        if logs.count > 200 {
            logs.removeFirst(logs.count - 200)
        }
        // 注意：不再把日志发送到服务器，避免 WebSocket 循环
    }
}

enum ConnectionStatus: Equatable {
    case disconnected
    case connecting
    case connected
    case error(String)

    var text: String {
        switch self {
        case .disconnected: return "未连接"
        case .connecting: return "连接中..."
        case .connected: return "已连接"
        case .error: return "连接错误"
        }
    }

    var color: Color {
        switch self {
        case .disconnected: return .gray
        case .connecting: return .orange
        case .connected: return .green
        case .error: return .red
        }
    }
}

struct LogEntry: Identifiable {
    let id = UUID()
    let text: String
    let time: Date
}

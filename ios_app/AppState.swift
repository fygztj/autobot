//
//  AppState.swift
//  AutoBot iOS 自动化助手 - 全局状态管理
//
// 工作原理:
// 1. 通过 WebSocket 连接 PC 端服务器
// 2. 在 App 内部的 WKWebView 中加载目标平台网页
// 3. 通过 JavaScript 注入实现自动化操作（点赞/评论/关注等）
//
// 重要说明:
// - 小红书/抖音等平台网页版需要先登录才能操作
// - 用户需要先在 App 的"浏览器" Tab 中手动登录
// - 登录后 Cookie 会自动保存，后续可以自动操作
//

import Foundation
import SwiftUI
import WebKit
import Combine

// ============================================================
// MARK: - JS 执行结果（统一解析 JSON 字符串）
// ============================================================

struct JSResult {
    let success: Bool
    let message: String
    let raw: [String: Any]

    static func parse(_ obj: Any?) -> JSResult {
        // 情况1: obj 是一个 Swift 字典（evaluateJavaScript 直接返回）
        if let dict = obj as? [String: Any] {
            let success = dict["success"] as? Bool ?? false
            let message = dict["message"] as? String ?? ""
            return JSResult(success: success, message: message, raw: dict)
        }

        // 情况2: obj 是一个 JSON 字符串（我们的脚本统一返回 JSON.stringify）
        if let str = obj as? String {
            if let data = str.data(using: .utf8),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                let success = json["success"] as? Bool ?? false
                let message = json["message"] as? String ?? ""
                return JSResult(success: success, message: message, raw: json)
            }
            // 作为纯文本处理
            return JSResult(success: !str.isEmpty, message: str, raw: ["text": str])
        }

        // 情况3: obj 是 NSNull
        if obj is NSNull {
            return JSResult(success: false, message: "JS 返回了 null", raw: [:])
        }

        // 情况4: 其他
        return JSResult(success: false, message: "无法解析 JS 返回值: \(String(describing: obj))", raw: [:])
    }
}

// ============================================================
// MARK: - 连接状态
// ============================================================

enum ConnectionStatus {
    case disconnected
    case connecting
    case connected
    case error(String)

    var text: String {
        switch self {
        case .disconnected: return "未连接"
        case .connecting: return "连接中..."
        case .connected: return "已连接"
        case .error(let msg): return "错误: \(msg)"
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

// ============================================================
// MARK: - 日志条目
// ============================================================

struct LogEntry: Identifiable {
    let id = UUID()
    let text: String
    let time: Date
}

// ============================================================
// MARK: - App 全局状态
// ============================================================

class AppState: ObservableObject {

    // 显式声明 objectWillChange，确保 ObservableObject protocol conformance
    let objectWillChange = ObservableObjectPublisher()

    // MARK: - UI 状态

    @Published var connectionStatus: ConnectionStatus = .disconnected
    @Published var currentPlatform: String = ""
    @Published var logs: [LogEntry] = []
    @Published var shouldOpenBrowser: Bool = false
    @Published var serverAddress: String {
        didSet {
            UserDefaults.standard.set(serverAddress, forKey: "serverAddress")
        }
    }

    // MARK: - WebView 引用

    weak var webView: WKWebView?

    // MARK: - WebSocket 管理器

    private var wsManager: WebSocketManager?

    // MARK: - 初始化

    init() {
        self.serverAddress = UserDefaults.standard.string(forKey: "serverAddress")
            ?? "http://192.168.1.8:8550"

        log("🚀 AutoBot 启动")
        log("📝 服务器地址: \(self.serverAddress)")
    }

    /// App 启动时调用（在 UI 出现后，确保 WebView 已创建）
    func startup() {
        Task { [weak self] in
            try? await Task.sleep(nanoseconds: 2_000_000_000) // 2 秒
            await self?.connect()
        }
    }

    // MARK: - 连接 / 断开

    func connect() async {
        disconnect()

        let wsUrl = serverAddress
            .replacingOccurrences(of: "http://", with: "ws://")
            .replacingOccurrences(of: "https://", with: "wss://")
            .appending("/ws/app/connect")

        guard let url = URL(string: wsUrl) else {
            log("❌ 无效的服务器地址: \(wsUrl)")
            connectionStatus = .error("无效地址")
            return
        }

        log("🔌 开始连接: \(wsUrl)")
        connectionStatus = .connecting

        wsManager = WebSocketManager(url: url)

        wsManager?.onConnected = { [weak self] in
            Task { @MainActor in
                self?.log("✅ WebSocket 已连接")
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

    // MARK: - 注册设备到服务器

    private func sendRegister() {
        let device = UIDevice.current
        let info: [String: Any] = [
            "type": "register",
            "device_id": device.identifierForVendor?.uuidString ?? UUID().uuidString,
            "device_name": device.name,
            "system_version": "\(device.systemName) \(device.systemVersion)",
            "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0",
            "model": device.model,
            "screen_width": Int(UIScreen.main.bounds.width),
            "screen_height": Int(UIScreen.main.bounds.height)
        ]
        wsManager?.sendJSON(info)
        log("📨 设备已注册: \(device.name)")
    }

    // MARK: - 接收并处理服务器指令

    private func handleMessage(_ message: [String: Any]) {
        let type = message["type"] as? String ?? ""

        guard type == "command" else {
            if type != "welcome" {
                log("📩 消息: \(type)")
            }
            return
        }

        let commandId = message["command_id"] as? String ?? ""
        let action = message["action"] as? String ?? ""
        let platform = message["platform"] as? String ?? ""
        let params = message["params"] as? [String: Any] ?? [:]

        log("🎯 收到指令: action=\(action), platform=\(platform)")

        // 触发 ContentView 切换到浏览器 Tab
        shouldOpenBrowser = true

        // 同步平台状态
        if currentPlatform != platform && !platform.isEmpty {
            currentPlatform = platform
        }

        Task {
            var success = false
            var msg = ""

            do {
                try await executeAction(action, platform: platform, params: params)
                success = true
                msg = "\(action) 执行成功"
            } catch {
                success = false
                msg = error.localizedDescription
                log("❌ 执行失败: \(msg)")
            }

            let result: [String: Any] = [
                "type": "result",
                "command_id": commandId,
                "success": success,
                "message": msg
            ]
            wsManager?.sendJSON(result)
        }
    }

    // MARK: - 动作分发

    private func executeAction(_ action: String, platform: String, params: [String: Any]) async throws {
        switch action {
        case "open_platform":
            try await actionOpenPlatform(platform)

        case "scroll":
            let direction = params["direction"] as? String ?? "up"
            try await actionScroll(direction: direction)

        case "like":
            try await actionLike(platform)

        case "comment":
            let text = params["text"] as? String ?? "很棒！"
            try await actionComment(platform, text: text)

        case "follow":
            try await actionFollow(platform)

        case "message":
            let text = params["text"] as? String ?? "你好"
            try await actionMessage(platform, text: text)

        case "click_first_post":
            try await actionClickFirstPost(platform)

        case "page_info":
            let result = try await evaluateJS(AutomationScripts.pageInfoScript())
            log("📋 页面信息: \(result.message)")

        case "custom_js":
            if let js = params["js"] as? String {
                _ = try await evaluateJS(js)
            }

        default:
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "未知操作: \(action)"])
        }

        log("✅ \(action) 完成")
    }

    // MARK: - 具体操作实现

    private func actionOpenPlatform(_ platform: String) async throws {
        let urlStr = AutomationScripts.url(for: platform)

        guard let url = URL(string: urlStr) else {
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "无效的 URL: \(urlStr)"])
        }

        guard let wv = webView else {
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "WebView 未准备好。请先切换到 App 的『浏览器』Tab"])
        }

        log("🌐 正在加载: \(urlStr)")
        log("💡 提示: 页面打开后需要手动登录，Cookie 会自动保存。如无法显示页面，尝试在 App 中切换到『浏览器』Tab。")

        wv.load(URLRequest(url: url))

        // 等待页面加载完成（最多 20 秒）
        var waited: UInt64 = 0
        var lastTitle = ""
        while waited < 20_000_000_000 {
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            waited += 1_500_000_000

            let pageInfo = try? await evaluateJavaScript("(function(){try{return JSON.stringify({title:document.title||'',url:location.href||'',readyState:document.readyState||'',elementCount:document.querySelectorAll('*').length,bodyText:(document.body?document.body.innerText||'':'').substring(0,200)});}catch(e){return JSON.stringify({success:false,message:e.message});}})();")

            if let pi = pageInfo as? String,
               let data = pi.data(using: .utf8),
               let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                let title = json["title"] as? String ?? ""
                let elementCount = json["elementCount"] as? Int ?? 0
                let bodyText = json["bodyText"] as? String ?? ""
                let curUrl = json["url"] as? String ?? ""

                if title != lastTitle {
                    log("   └ 页面标题: \(title)")
                    log("   └ 页面 URL: \(curUrl)")
                    log("   └ 元素数: \(elementCount), body 预览: \(bodyText.prefix(80))")
                    lastTitle = title
                }

                if elementCount > 50 {
                    log("✅ 页面已加载完成")

                    if title.contains("登录") || title.contains("login") || bodyText.contains("请登录") || bodyText.contains("需要登录") {
                        log("⚠️  检测到登录页 — 请在下方 WebView 中手动登录后再执行其他操作")
                    }
                    return
                }
            }
        }

        log("⏰ 页面加载超时（可能需要手动登录或网络问题），继续执行")
    }

    private func actionScroll(direction: String, count: Int = 1) async throws {
        log("📜 滚动: direction=\(direction), count=\(count)")
        let delta = direction == "up" ? "400" : "-400"
        for i in 0..<count {
            _ = try? await evaluateJavaScript("window.scrollBy(0,\(delta));JSON.stringify({success:true});")
            if i < count - 1 {
                try? await Task.sleep(nanoseconds: 800_000_000)
            }
        }
    }

    private func actionLike(_ platform: String) async throws {
        log("❤️ 点赞 (platform=\(platform))")

        // 先检测页面是否有内容
        let preCheck = try? await evaluateJavaScript("(function(){try{var btns=document.querySelectorAll('button,a,div,span');var count=0;for(var i=0;i<btns.length;i++){var t=(btns[i].innerText||btns[i].textContent||'').trim();if(t.length>0 && t.length<30) count++;}return JSON.stringify({success:true,total:btns.length,textNodes:count,title:document.title||''});}catch(e){return JSON.stringify({success:false,message:e.message});}})();")
        if let s = preCheck as? String,
           let d = s.data(using: .utf8),
           let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
            let total = j["total"] as? Int ?? 0
            let title = j["title"] as? String ?? ""
            log("   └ 页面检测: 总元素=\(total), title=\(title.prefix(50))")
            if total < 20 {
                log("   ⚠️  页面元素过少，可能未加载完成或需要登录")
            }
        }

        // 执行脚本
        let result = try await evaluateJS(AutomationScripts.likeScript(for: platform))

        if result.success {
            log("💡 成功: \(result.message)")
        } else {
            log("❌ 点赞失败: \(result.message)")
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "点赞失败: \(result.message)"])
        }
    }

    private func actionComment(_ platform: String, text: String) async throws {
        log("💬 评论: \(text)")
        let result = try await evaluateJS(AutomationScripts.commentScript(for: platform, text: text))
        if result.success {
            log("💡 \(result.message)")
        } else {
            log("❌ 评论失败: \(result.message)")
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "评论失败: \(result.message)"])
        }
    }

    private func actionFollow(_ platform: String) async throws {
        log("👤 关注")
        let result = try await evaluateJS(AutomationScripts.followScript(for: platform))
        if result.success {
            log("💡 \(result.message)")
        } else {
            log("❌ 关注失败: \(result.message)")
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "关注失败: \(result.message)"])
        }
    }

    private func actionMessage(_ platform: String, text: String) async throws {
        log("📨 私信: \(text)")
        // 目前复用 comment 脚本作为简单的私信操作
        let result = try await evaluateJS(AutomationScripts.commentScript(for: platform, text: text))
        if result.success {
            log("💡 \(result.message)")
        } else {
            log("❌ 私信失败: \(result.message)")
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "私信失败: \(result.message)"])
        }
    }

    private func actionClickFirstPost(_ platform: String) async throws {
        log("📌 点击第一篇帖子")
        let result = try await evaluateJS(AutomationScripts.clickFirstPostScript(for: platform))
        if result.success {
            log("💡 \(result.message)")
            try await Task.sleep(nanoseconds: 2_000_000_000)
        } else {
            log("❌ 点击失败: \(result.message)")
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "点击帖子失败: \(result.message)"])
        }
    }

    // MARK: - JS 执行

    /// 统一的 JS 执行接口: 执行脚本，解析其返回的 JSON 字符串
    private func evaluateJS(_ js: String) async throws -> JSResult {
        guard let wv = webView else {
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "WebView 未准备好。请先切换到 App 的『浏览器』Tab"])
        }

        return try await withCheckedThrowingContinuation { continuation in
            wv.evaluateJavaScript(js) { result, error in
                if let error = error {
                    let nsErr = error as NSError
                    let detail = nsErr.userInfo["WKJavaScriptExceptionMessage"] as? String
                        ?? nsErr.userInfo["message"] as? String
                        ?? nsErr.localizedDescription
                    continuation.resume(throwing: NSError(
                        domain: "AutoBot", code: -1,
                        userInfo: [NSLocalizedDescriptionKey: "JS 执行异常: \(detail)"]
                    ))
                    return
                }
                continuation.resume(returning: JSResult.parse(result))
            }
        }
    }

    /// 直接执行 JS，返回原始结果（不做 JSON 解析）。当 JS 内有异常时，会通过 Swift 错误抛出。
    private func evaluateJavaScript(_ js: String) async throws -> Any? {
        guard let wv = webView else {
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: "WebView 未准备好"])
        }
        return try await withCheckedThrowingContinuation { continuation in
            wv.evaluateJavaScript(js) { result, error in
                if let error = error {
                    continuation.resume(throwing: error)
                    return
                }
                continuation.resume(returning: result)
            }
        }
    }

    // MARK: - 日志

    func log(_ message: String) {
        let entry = LogEntry(text: message, time: Date())
        DispatchQueue.main.async {
            self.logs.append(entry)
            if self.logs.count > 500 {
                self.logs.removeFirst(self.logs.count - 500)
            }
        }
    }
}

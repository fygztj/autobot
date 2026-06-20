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

    @Published var authToken: String {
        didSet {
            UserDefaults.standard.set(authToken, forKey: "authToken")
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
        self.authToken = UserDefaults.standard.string(forKey: "authToken") ?? ""

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
            "token": authToken,
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

        case "click_random_note":
            try await actionClickRandomNote(platform)

        case "go_back":
            try await actionGoBack()

        case "collect":
            try await actionCollect(platform)

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
            let result = try await evaluateJS(AutomationScripts.observeScript())
            log("📋 页面信息: \(result.message)")

        case "observe":
            let obs = try await evaluateJS(AutomationScripts.observeScript())
            log("👁️ 观察: \(obs.message)")

        case "run_agent":
            // 旧版 Agent → 兼容到 v3 工作模式
            let rounds = params["rounds"] as? Int ?? 5
            let enableLike = params["like"] as? Bool ?? false
            let enableCollect = params["collect"] as? Bool ?? false
            let enableFollow = params["follow"] as? Bool ?? false
            let enableComment = params["comment"] as? Bool ?? false
            let commentTexts = params["comment_texts"] as? [String] ?? ["很棒！"]

            // 构建兼容的 v3 配置
            var compatConfig = TaskConfig()
            compatConfig.mode = .work
            compatConfig.platform = platform
            compatConfig.work.defaultProbabilities.likeRate = enableLike ? 0.9 : 0.0
            compatConfig.work.defaultProbabilities.collectRate = enableCollect ? 0.8 : 0.0
            compatConfig.work.defaultProbabilities.followRate = enableFollow ? 0.3 : 0.0
            compatConfig.work.defaultProbabilities.commentRate = enableComment ? 0.5 : 0.0
            compatConfig.work.mainLine.defaultReplies = commentTexts.isEmpty ? ["很棒！"] : commentTexts
            compatConfig.work.totalDurationMinutes = 0 // 不限时
            try await runAgentV3(platform: platform, config: compatConfig)

        case "run_task_v3":
            // v3 双模式引擎
            if let configDict = params["config"] as? [String: Any],
               let config = TaskConfig.fromDict(configDict) {
                try await runAgentV3(platform: platform, config: config)
            } else {
                throw NSError(domain: "AutoBot", code: -1,
                             userInfo: [NSLocalizedDescriptionKey: "无效的任务配置"])
            }

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
        log("📜 平滑滚动: direction=\(direction), count=\(count)")
        for i in 0..<count {
            let result = try await evaluateJS(AutomationScripts.scrollScript(direction: direction))
            log("   └ \(result.message)")
            if i < count - 1 {
                try? await Task.sleep(nanoseconds: 600_000_000)
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

    private func actionClickRandomNote(_ platform: String) async throws {
        log("🎲 随机点击笔记")
        let result = try await evaluateJS(AutomationScripts.clickRandomNoteScript(for: platform))
        if result.success {
            log("💡 \(result.message)")
            try await Task.sleep(nanoseconds: 2_000_000_000)
        } else {
            log("❌ 随机点击失败: \(result.message)")
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: result.message])
        }
    }

    private func actionGoBack() async throws {
        log("⬅️ 返回上一页")
        let result = try await evaluateJS(AutomationScripts.goBackScript())
        if result.success {
            log("💡 \(result.message)")
            try await Task.sleep(nanoseconds: 1_500_000_000)
        } else {
            log("⚠️ \(result.message)")
        }
    }

    private func actionCollect(_ platform: String) async throws {
        log("⭐ 收藏笔记")
        let result = try await evaluateJS(AutomationScripts.collectScript(for: platform))
        if result.success {
            log("💡 \(result.message)")
        } else {
            log("❌ 收藏失败: \(result.message)")
            throw NSError(domain: "AutoBot", code: -1,
                         userInfo: [NSLocalizedDescriptionKey: result.message])
        }
    }

    // MARK: - 🤖 Agent v3 双模式引擎

    /// v3 入口：根据模式分发
    private func runAgentV3(platform: String, config: TaskConfig) async throws {
        let modeName = config.mode == .nurture ? "🌱 养号模式" : "💼 工作模式"
        log("🤖 Agent v3 启动: \(modeName) | 平台: \(platform)")

        switch config.mode {
        case .nurture:
            try await runNurtureMode(platform: platform, config: config)
        case .work:
            try await runWorkMode(platform: platform, config: config)
        }

        log("🤖 Agent v3 完成")
    }

    // MARK: - 🌱 养号模式

    private func runNurtureMode(platform: String, config: TaskConfig) async throws {
        let nurture = config.nurture
        // 随机总执行时长（秒）
        let totalDuration = nurture.durationRange.random()
        log("🌱 养号模式: 关键词=\(nurture.searchKeywords), 总时长≈\(totalDuration)s, 点赞率=\(Int(nurture.likeRate * 100))%")
        log("   📋 useSearch=\(nurture.useSearch), searchKeywords.count=\(nurture.searchKeywords.count)")

        // 1. 打开平台
        try await actionOpenPlatform(platform)
        try? await Task.sleep(nanoseconds: 3_000_000_000)

        var startTime = Date()
        var noteCount = 0

        if nurture.useSearch && !nurture.searchKeywords.isEmpty {
            log("   ✅ 进入搜索模式")
            // 搜索模式：在时间范围内循环浏览各关键词的搜索结果
            var keywordIndex = 0

            while Date().timeIntervalSince(startTime) < Double(totalDuration) {
                let keyword = nurture.searchKeywords[keywordIndex % nurture.searchKeywords.count]
                log("   🔍 [关键词 \(keywordIndex + 1)/\(nurture.searchKeywords.count)] 搜索: \(keyword)")

                // 执行搜索
                log("      📡 正在执行搜索脚本...")
                let searchResult = try? await evaluateJS(AutomationScripts.searchScript(keyword: keyword))
                if let success = searchResult?.raw["success"] as? Bool, success {
                    log("      🔎 搜索脚本执行成功")
                } else {
                    log("      ⚠️ 搜索脚本执行失败")
                }
                // 等待页面加载完成
                try? await Task.sleep(nanoseconds: 5_000_000_000)
                // 检查当前页面URL
                let urlResult = try? await evaluateJS("(function(){return JSON.stringify({url:location.href});})()")
                if let url = urlResult?.raw["url"] as? String {
                    log("      🌐 当前页面: \(url.prefix(80))")
                }

                // 在当前搜索结果中持续浏览，直到超时或切换关键词
                var timeInKeyword = 0.0
                let maxTimePerKeyword = Double(totalDuration) / Double(max(nurture.searchKeywords.count, 1))

                while Date().timeIntervalSince(startTime) < Double(totalDuration)
                       && timeInKeyword < maxTimePerKeyword {
                    log("      📖 浏览第 \(noteCount + 1) 篇")

                    do {
                        try await actionClickRandomNote(platform)
                        noteCount += 1
                        try? await Task.sleep(nanoseconds: 2_500_000_000)

                        // 进入笔记后立即暂停所有视频（防止自动播放）
                        try? await evaluateJS(AutomationScripts.pauseVideoScript())
                        
                        // 检测是否为视频笔记
                        let contentResult = try? await evaluateJS(AutomationScripts.extractContentScript())
                        let isVideo = contentResult?.raw["isVideo"] as? Bool ?? false

                        if isVideo {
                            // 视频笔记：不播放视频，只浏览评论区
                            log("      🎬 检测到视频笔记，跳过播放，浏览评论")
                            // 浏览评论区
                            try? await evaluateJS(AutomationScripts.browseCommentsScript(scrollCount: 2))
                            try? await Task.sleep(nanoseconds: 3_000_000_000)
                        } else {
                            // 图文笔记：正常浏览
                            let viewNs = UInt64(nurture.viewTimeRange.random() * 1_000_000_000)
                            try? await Task.sleep(nanoseconds: viewNs)

                            // 概率点赞
                            if Double.random(in: 0...1) < nurture.likeRate {
                                do { try await actionLike(platform); log("      ❤️ 已点赞") }
                                catch { log("      ⚠️ 点赞跳过") }
                                try? await Task.sleep(nanoseconds: 800_000_000)
                            }
                        }

                        // 返回搜索结果
                        _ = try? await evaluateJS(AutomationScripts.goBackScript())
                        try? await Task.sleep(nanoseconds: 1_000_000_000)

                        // 滑动页面，避免总是点击同一个笔记
                        _ = try? await evaluateJS(AutomationScripts.scrollScript(direction: "up"))
                        try? await Task.sleep(nanoseconds: 1_500_000_000)

                        // 笔记间休息
                        let restNs = UInt64(nurture.restRange.random() * 1_000_000_000)
                        try? await Task.sleep(nanoseconds: restNs)

                    } catch {
                        log("      ⚠️ 本篇跳过")
                        _ = try? await evaluateJS(AutomationScripts.goBackScript())
                        try? await Task.sleep(nanoseconds: 1_500_000_000)
                    }

                    timeInKeyword = Date().timeIntervalSince(startTime)
                }

                // 切换到下一个关键词，额外休息
                keywordIndex += 1
                let kwRest = UInt64(nurture.keywordRestRange.random() * 1_000_000_000)
                log("   😴 切换关键词，休息 \(kwRest / 1_000_000_000)s...")
                try? await Task.sleep(nanoseconds: kwRest)
            }

        } else {
            // 非搜索模式：在时间范围内持续浏览推荐页
            while Date().timeIntervalSince(startTime) < Double(totalDuration) {
                _ = try? await evaluateJS(AutomationScripts.scrollScript(direction: "up"))
                try? await Task.sleep(nanoseconds: 1_500_000_000)

                do {
                    try await actionClickRandomNote(platform)
                    noteCount += 1
                    try? await Task.sleep(nanoseconds: 2_000_000_000)

                    // 检测是否为视频笔记
                    let contentResult = try? await evaluateJS(AutomationScripts.extractContentScript())
                    let isVideo = contentResult?.raw["isVideo"] as? Bool ?? false

                    if isVideo {
                        // 视频笔记：不播放视频，只浏览评论区
                        log("      🎬 检测到视频笔记，跳过播放，浏览评论")
                        try? await evaluateJS(AutomationScripts.browseCommentsScript(scrollCount: 2))
                        try? await Task.sleep(nanoseconds: 3_000_000_000)
                    } else {
                        // 图文笔记：正常浏览
                        let vt = UInt64(nurture.viewTimeRange.random() * 1_000_000_000)
                        try? await Task.sleep(nanoseconds: vt)

                        if Double.random(in: 0...1) < nurture.likeRate {
                            try? await actionLike(platform)
                        }
                    }

                    _ = try? await evaluateJS(AutomationScripts.goBackScript())
                    try? await Task.sleep(nanoseconds: 1_000_000_000)

                    // 滑动页面，避免总是点击同一个笔记
                    _ = try? await evaluateJS(AutomationScripts.scrollScript(direction: "up"))
                    try? await Task.sleep(nanoseconds: 1_500_000_000)

                    try? await Task.sleep(nanoseconds: UInt64(nurture.restRange.random() * 1_000_000_000))
                } catch {
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                }
            }
        }

        let elapsed = Int(Date().timeIntervalSince(startTime))
        log("🌱 养号完成: 共浏览 \(noteCount) 篇, 耗时 \(elapsed)s")
    }

    // MARK: - 💼 工作模式

    private func runWorkMode(platform: String, config: TaskConfig) async throws {
        let work = config.work
        log("💼 工作模式启动")
        log("   主线: \(work.mainLine.name)(关键词:\(work.mainLine.keywords)) | 次线: \(work.secondaryLine.name)(关键词:\(work.secondaryLine.keywords))")
        log("   交替: 主\(work.alternation.mainRounds)轮 → 次\(work.alternation.secondaryRounds)轮")

        // 打开平台
        try await actionOpenPlatform(platform)
        try? await Task.sleep(nanoseconds: 3_000_000_000)

        // 生成交替序列
        let sequence = work.alternation.generateSequence(count: 10)
        var totalProcessed = 0
        let maxTotal = work.totalDurationMinutes > 0 ? work.totalDurationMinutes * 6 : 60 // 大约估算

        for (si, lineType) in sequence.enumerated() {
            if work.totalDurationMinutes > 0 && totalProcessed >= maxTotal {
                log("   ⏱️ 达到时长限制，停止执行")
                break
            }

            let lineConfig = lineType == "main" ? work.mainLine : work.secondaryLine
            let probs = config.effectiveProbabilities(forLine: lineType)
            let notesInThisRound = lineConfig.notesPerRound

            log("--- 🔀 第\(si+1)轮: \(lineConfig.name) (\(notesInThisRound)篇笔记) ---")

            // 执行该线路的笔记浏览
            for ri in 1...notesInThisRound {
                totalProcessed += 1
                log("   [\(lineConfig.name) - \(ri)/\(notesInThisRound)] 处理笔记 #\(totalProcessed)")

                // 滚动寻找新内容
                _ = try? await evaluateJS(AutomationScripts.scrollScript(direction: "up"))
                try? await Task.sleep(nanoseconds: 1_200_000_000)
                _ = try? await evaluateJS(AutomationScripts.scrollScript(direction: "up"))
                try? await Task.sleep(nanoseconds: 800_000_000)

                // 点击一篇笔记
                do {
                    try await actionClickRandomNote(platform)
                    try? await Task.sleep(nanoseconds: 3_000_000_000) // 等详情页加载

                    // ===== 内容识别 =====
                    let contentResult = try? await evaluateJS(AutomationScripts.extractContentScript())
                    var noteTitle = ""
                    var noteTags: [String] = []
                    var noteAuthor = ""

                    if let cr = contentResult?.raw as? String,
                       let cd = cr.data(using: .utf8),
                       let cj = try? JSONSerialization.jsonObject(with: cd) as? [String: Any] {
                        noteTitle = cj["noteTitle"] as? String ?? ""
                        noteTags = cj["tags"] as? [String] ?? []
                        noteAuthor = cj["author"] as? String ?? ""

                        log("   📝 标题: \(noteTitle.prefix(50))")
                        if !noteTags.isEmpty { log("   🏷️ 标签: \(noteTags.prefix(5).joined(separator: ", "))") }
                        if !noteAuthor.isEmpty { log("   ✍️ 作者: \(noteAuthor)") }
                    }

                    // ===== 模拟浏览（停留）=====
                    let browseTime = UInt64(work.viewTimeRange.random() * 1_000_000_000)
                    log("   👀 浏览中 \(browseTime / 1_000_000_000)s...")
                    try? await Task.sleep(nanoseconds: browseTime)

                    // ===== 概率性互动 =====

                    // 点赞
                    if probs.should(.like) {
                        do { try await actionLike(platform); log("   ❤️ 已点赞") }
                        catch { log("   ⚠️ 点赞失败") }
                        try? await Task.sleep(nanoseconds: 800_000_000)
                    }

                    // 收藏
                    if probs.should(.collect) {
                        do { try await actionCollect(platform); log("   ⭐ 已收藏") }
                        catch { log("   ⚠️ 收藏失败") }
                        try? await Task.sleep(nanoseconds: 600_000_000)
                    }

                    // 关注作者
                    if probs.should(.follow) {
                        do { try await actionFollow(platform); log("   ➕ 已关注 \(noteAuthor)") }
                        catch { log("   ⚠️ 关注失败") }
                        try? await Task.sleep(nanoseconds: 600_000_000)
                    }

                    // ===== 评论区处理 =====
                    if work.browseComments {
                        log("   💬 进入评论区...")

                        // 滚动到评论区
                        _ = try? await evaluateJS(AutomationScripts.scrollToCommentsScript())
                        try? await Task.sleep(nanoseconds: 2_000_000_000)

                        // 浏览评论（滚动加载更多）
                        _ = try? await evaluateJS(AutomationScripts.browseCommentsScript(scrollCount: work.commentScrollCount))
                        try? await Task.sleep(nanoseconds: 2_000_000_000)

                        // 提取评论信息
                        let commentResult = try? await evaluateJS(AutomationScripts.extractCommentsScript())
                        var commentCount = 0
                        if let cStr = commentResult?.raw as? String,
                           let cData = cStr.data(using: .utf8),
                           let cJson = try? JSONSerialization.jsonObject(with: cData) as? [String: Any] {
                            commentCount = cJson["count"] as? Int ?? 0
                            log("   📊 发现 \(commentCount) 条评论")
                        }

                        // 评论笔记（概率性 + 智能回复）
                        if probs.should(.comment) {
                            let replyText = config.generateSmartReply(contentTitle: noteTitle, contentTags: noteTags, line: lineType)
                            let (shouldMention, mentionAccount) = config.shouldMention(line: lineType)

                            var finalReply = replyText
                            if shouldMention && !mentionAccount.isEmpty {
                                finalReply = "\(replyText) \(mentionAccount)"
                                log("   📢 评论(含@): \(finalReply)")
                            } else {
                                log("   📢 评论: \(finalReply)")
                            }

                            do { try await actionComment(platform, text: finalReply) }
                            catch { log("   ⚠️ 评论发送失败") }
                            try? await Task.sleep(nanoseconds: 1_500_000_000)
                        }

                        // 回复他人评论（概率性）
                        if probs.should(.reply) && commentCount > 0 {
                            let replyText = config.generateSmartReply(contentTitle: noteTitle, contentTags: noteTags, line: lineType)
                            log("   ↩️ 回复评论: \(replyText)")
                            _ = try? await evaluateJS(AutomationScripts.replyToCommentScript(commentIndex: -1, replyText: replyText)) // -1 = random
                            try? await Task.sleep(nanoseconds: 1_500_000_000)
                        }

                        // 给评论点赞（概率性，在主线下更积极）
                        let commentLikeProb = lineType == "main" ? 0.25 : 0.08
                        if Double.random(in: 0...1) < commentLikeProb {
                            _ = try? await evaluateJS(AutomationScripts.likeCommentScript(commentIndex: -1))
                            log("   ❤️ 已给评论点赞")
                            try? await Task.sleep(nanoseconds: 600_000_000)
                        }
                    }

                    // 返回列表
                    _ = try? await evaluateJS(AutomationScripts.goBackScript())

                    // 笔记间休息
                    let restNs = UInt64(work.restBetweenNotes.random() * 1_000_000_000)
                    log("   😴 休息 \(restNs / 1_000_000_000)s...")
                    try? await Task.sleep(nanoseconds: restNs)

                } catch {
                    log("   ⚠️ 笔记处理异常，返回列表")
                    _ = try? await evaluateJS(AutomationScripts.goBackScript())
                    try? await Task.sleep(nanoseconds: 2_000_000_000)
                }
            }

            // 主线/次线切换间的较长休息
            let lineRest = UInt64(work.restBetweenLines.random() * 1_000_000_000)
            log("   ☕ \(lineConfig.name) 结束，切换休息 \(lineRest / 1_000_000_000)s...")
            try? await Task.sleep(nanoseconds: lineRest)
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

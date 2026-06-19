//
//  WebSocketManager.swift
//  WebSocket 连接管理 - 修复版
//
//  修复:
//  1. 移除 timeoutIntervalForResource=15 (导致15秒后自动断开)
//  2. 对 pong/log 类型消息不打印日志 (避免日志刷屏)
//  3. 对 type=log 的发送不打印日志 (避免循环)
//  4. 心跳从 30 秒改为 10 秒
//

import Foundation

class WebSocketManager: NSObject, URLSessionWebSocketDelegate {
    private var url: URL
    private var webSocketTask: URLSessionWebSocketTask?
    private var session: URLSession?
    private var pingTimer: Timer?

    // 回调
    var onConnected: (() -> Void)?
    var onDisconnected: ((String) -> Void)?
    var onMessage: (([String: Any]) -> Void)?
    var onError: ((String) -> Void)?
    var onLog: ((String) -> Void)?

    private var isConnected = false
    private var connectionTimeoutTimer: Timer?

    init(url: URL) {
        self.url = url
        super.init()
    }

    func connect() {
        onLog?("🌐 连接: \(url.absoluteString)")

        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 15
        // 移除 timeoutIntervalForResource —— 它会导致 WebSocket 在 15 秒后自动断开
        session = URLSession(configuration: configuration, delegate: self, delegateQueue: OperationQueue())

        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.setValue("autobot-ios", forHTTPHeaderField: "User-Agent")

        webSocketTask = session?.webSocketTask(with: request)
        webSocketTask?.resume()

        onLog?("⏳ 等待握手...")

        // 连接超时
        DispatchQueue.main.async { [weak self] in
            self?.connectionTimeoutTimer = Timer.scheduledTimer(withTimeInterval: 15.0, repeats: false) { [weak self] _ in
                guard let self = self else { return }
                if !self.isConnected {
                    self.onLog?("⏰ 连接超时")
                    self.onError?("连接失败")
                    self.cleanup()
                }
            }
        }

        receiveMessage()
    }

    func disconnect() {
        onLog?("🔌 主动断开")
        cleanup()
    }

    private func cleanup() {
        pingTimer?.invalidate()
        pingTimer = nil
        connectionTimeoutTimer?.invalidate()
        connectionTimeoutTimer = nil
        webSocketTask?.cancel(with: .goingAway, reason: nil)
        webSocketTask = nil
        session?.invalidateAndCancel()
        session = nil
        isConnected = false
    }

    // MARK: - URLSessionWebSocketDelegate

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didOpenWithProtocol protocol: String?) {
        onLog?("✅ 握手成功!")
        connectionTimeoutTimer?.invalidate()
        connectionTimeoutTimer = nil
        isConnected = true
        onConnected?()

        // 心跳 10 秒一次
        DispatchQueue.main.async { [weak self] in
            self?.pingTimer = Timer.scheduledTimer(withTimeInterval: 10.0, repeats: true) { _ in
                self?.sendPing()
            }
        }
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        onLog?("🔌 连接关闭 (code: \(closeCode.rawValue))")
        let reasonStr = reason.flatMap { String(data: $0, encoding: .utf8) } ?? "无"
        onDisconnected?("连接关闭: \(reasonStr)")
        cleanup()
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if let error = error {
            onLog?("❌ 错误: \(error.localizedDescription)")
            if !isConnected {
                onError?("连接失败: \(error.localizedDescription)")
            } else {
                onDisconnected?("连接断开")
            }
            cleanup()
        }
    }

    private func sendPing() {
        guard let task = webSocketTask else { return }
        task.sendPing { [weak self] error in
            if error != nil {
                self?.onLog?("⚠️ Ping 失败")
            }
        }
    }

    private func receiveMessage() {
        guard let task = webSocketTask else { return }

        task.receive { [weak self] result in
            guard let self = self else { return }

            switch result {
            case .success(let message):
                switch message {
                case .string(let text):
                    // 解析 JSON，只对非 pong/非高频消息打印日志
                    if let data = text.data(using: .utf8),
                       let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        let msgType = json["type"] as? String ?? ""
                        if msgType != "pong" && msgType != "log" {
                            self.onLog?("📨 收到: \(text.prefix(80))")
                        }
                        DispatchQueue.main.async {
                            self.onMessage?(json)
                        }
                    } else {
                        // 非 JSON 消息，简短打印
                        self.onLog?("📨 非 JSON: \(text.prefix(50))")
                    }

                case .data(let data):
                    if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                        DispatchQueue.main.async {
                            self.onMessage?(json)
                        }
                    }

                @unknown default:
                    break
                }

                self.receiveMessage()

            case .failure(let error):
                self.onLog?("❌ 接收失败: \(error.localizedDescription)")
                if self.isConnected {
                    DispatchQueue.main.async {
                        self.onDisconnected?("连接断开")
                    }
                }
                self.cleanup()
            }
        }
    }

    func sendJSON(_ dict: [String: Any]) {
        guard JSONSerialization.isValidJSONObject(dict),
              let data = try? JSONSerialization.data(withJSONObject: dict),
              let text = String(data: data, encoding: .utf8) else {
            onLog?("⚠️ JSON 序列化失败")
            return
        }

        // log 类型消息不打印（避免循环）
        let msgType = dict["type"] as? String ?? ""
        if msgType != "log" {
            // 只对关键消息打印
            if msgType == "register" || msgType == "result" || msgType == "command" || msgType == "heartbeat" {
                onLog?("📤 发送: \(msgType)")
            }
        }

        webSocketTask?.send(.string(text)) { [weak self] error in
            if let error = error {
                self?.onLog?("❌ 发送失败: \(error.localizedDescription)")
            }
        }
    }

    func send(_ text: String) {
        webSocketTask?.send(.string(text)) { [weak self] error in
            if let error = error {
                self?.onLog?("❌ 发送失败: \(error.localizedDescription)")
            }
        }
    }
}

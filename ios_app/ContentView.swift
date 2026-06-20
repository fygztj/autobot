//
//  ContentView.swift
//  AutoBot 主界面
//

import SwiftUI
import WebKit
import Combine


struct ContentView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            BrowserTabView()
                .tabItem {
                    Label("浏览器", systemImage: "globe")
                }
                .tag(0)

            ConsoleView()
                .tabItem {
                    Label("控制台", systemImage: "terminal")
                }
                .tag(1)

            SettingsView()
                .tabItem {
                    Label("设置", systemImage: "gear")
                }
                .tag(2)
        }
        .onChange(of: appState.shouldOpenBrowser) { newValue in
            if newValue {
                selectedTab = 0
                appState.shouldOpenBrowser = false
            }
        }
    }
}


// ============================================================
// MARK: - 浏览器视图（核心自动化执行区域）
// ============================================================

struct BrowserTabView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var webViewHolder = WebViewHolder()

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Circle()
                    .fill(appState.connectionStatus.color)
                    .frame(width: 10, height: 10)
                Text(appState.connectionStatus.text)
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
                Spacer()
                if !appState.currentPlatform.isEmpty {
                    Text("📱 \(appState.currentPlatform)")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(Color(.systemGray6))

            AutoBotWebView(holder: webViewHolder)
                .edgesIgnoringSafeArea(.bottom)
        }
        .onAppear {
            appState.webView = webViewHolder.webView
        }
    }
}

// 用 ObservableObject 持有 webView，确保它不会在 view 重渲染时被重建
class WebViewHolder: ObservableObject {
    let webView: WKWebView
    // 显式声明 objectWillChange，保证 ObservableObject 协议被正确实现
    let objectWillChange = ObservableObjectPublisher()

    init() {
        let config = WKWebViewConfiguration()
        config.preferences.javaScriptEnabled = true
        config.preferences.javaScriptCanOpenWindowsAutomatically = true
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        config.processPool = WKProcessPool()
        config.allowsInlineMediaPlayback = true

        let web = WKWebView(frame: .zero, configuration: config)
        web.allowsBackForwardNavigationGestures = true
        web.allowsLinkPreview = false
        web.scrollView.bounces = true
        if #available(iOS 16.4, *) {
            web.isInspectable = true
        }

        // ⚠️ 使用桌面版 Mac Safari UA
        // 原因: 小红书手机 UA 会强制重定向到 App Store 下载页
        // 桌面 UA 返回桌面网页版，可在手机浏览器正常显示和操作
        web.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15"
        // 可选: 移动 UA — 留作用户切换
        // "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1"

        self.webView = web
    }
}


// ============================================================
// MARK: - 统一的 WebView 包装
// ============================================================

struct AutoBotWebView: UIViewRepresentable {
    let holder: WebViewHolder

    func makeUIView(context: Context) -> WKWebView {
        holder.webView.navigationDelegate = context.coordinator
        holder.webView.uiDelegate = context.coordinator
        return holder.webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(holder: holder)
    }

    class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        var holder: WebViewHolder

        init(holder: WebViewHolder) {
            self.holder = holder
        }

        /// 拦截请求 — 阻止跳转到 App Store / 下载页
        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            let url = navigationAction.request.url?.absoluteString ?? ""

            // 如果目标是 App Store / iTunes / app 下载链接 → 取消
            if url.contains("itunes.apple.com") ||
               url.contains("apps.apple.com") ||
               url.contains("xiaohongshu.com/download") ||
               url.contains("market://") {
                print("🚫 拦截到 App Store 下载重定向: \(url)")
                decisionHandler(.cancel)
                return
            }

            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            print("🌐 页面加载完成: \(webView.url?.absoluteString ?? "")")
        }

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
            print("❌ 页面加载失败: \(error.localizedDescription)")
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
            print("❌ 导航失败: \(error.localizedDescription)")
        }

        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            completionHandler()
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            completionHandler(true)
        }

        func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
            // 新窗口 → 在当前 webView 中加载，避免跳出
            if navigationAction.targetFrame == nil {
                webView.load(navigationAction.request)
            }
            return nil
        }
    }
}


// ============================================================
// MARK: - 控制台视图
// ============================================================

struct ConsoleView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Circle()
                    .fill(appState.connectionStatus.color)
                    .frame(width: 12, height: 12)
                Text("连接状态: \(appState.connectionStatus.text)")
                    .font(.system(size: 14, weight: .medium))
                Spacer()
            }
            .padding(.horizontal, 16)
            .padding(.top, 16)

            HStack {
                Text("服务器: \(appState.serverAddress)")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                Spacer()
            }
            .padding(.horizontal, 16)

            ScrollView {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(appState.logs) { entry in
                        HStack(alignment: .top, spacing: 6) {
                            Text(formatTime(entry.time))
                                .font(.system(size: 11))
                                .foregroundColor(.gray)
                            Text(entry.text)
                                .font(.system(size: 12))
                                .foregroundColor(.primary)
                            Spacer()
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
            }
        }
    }

    private func formatTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm:ss"
        return formatter.string(from: date)
    }
}


// ============================================================
// MARK: - 设置视图
// ============================================================

struct SettingsView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        Form {
            Section(header: Text("服务器设置")) {
                TextField("服务器地址 (如 http://192.168.1.8:8550)",
                         text: Binding(
                            get: { appState.serverAddress },
                            set: { newValue in appState.serverAddress = newValue }
                         ))
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled(true)
                    .keyboardType(.URL)

                SecureField("连接 Token（公网部署时必填，局域网可留空）",
                           text: Binding(
                            get: { appState.authToken },
                            set: { newValue in appState.authToken = newValue }
                           ))
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled(true)
            }

            Section(header: Text("连接操作")) {
                Button(action: {
                    Task {
                        await appState.connect()
                    }
                }) {
                    HStack {
                        Image(systemName: "link.circle.fill")
                            .foregroundColor(.green)
                        Text("重新连接")
                    }
                }

                Button(action: {
                    appState.disconnect()
                }) {
                    HStack {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.red)
                        Text("断开连接")
                    }
                }
            }

            Section(header: Text("使用说明")) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("1. 局域网: 确保 iPhone 和 Mac 在同一 WiFi，Token 可留空")
                        .font(.system(size: 13))
                    Text("2. 公网部署: 需填写 Token（与 PC 端一致），服务器地址填 Cloudflare Tunnel 地址")
                        .font(.system(size: 13))
                    Text("3. PC 端发送 open_platform 后，App 会自动在浏览器中打开小红书/抖音网页版")
                        .font(.system(size: 13))
                    Text("4. 请先在浏览器 Tab 中手动登录你的账号（仅需一次）")
                        .font(.system(size: 13))
                    Text("5. 登录后，PC 端即可控制自动点赞/评论/关注等")
                        .font(.system(size: 13))
                    Text("5. 如果点赞失败，请检查是否已登录、页面是否已加载完成")
                        .font(.system(size: 13))
                        .foregroundColor(.orange)
                }
                .padding(.vertical, 6)
            }

            Section(header: Text("关于")) {
                HStack {
                    Text("App 版本")
                    Spacer()
                    Text(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")
                        .foregroundColor(.secondary)
                }
                HStack {
                    Text("平台")
                    Spacer()
                    Text("iOS " + UIDevice.current.systemVersion)
                        .foregroundColor(.secondary)
                }
            }
        }
    }
}

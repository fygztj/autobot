//
//  BrowserView.swift
//  WKWebView 包装 - 用于加载目标平台页面和执行 JS 自动化脚本
//

import SwiftUI
import WebKit

// SwiftUI 包装的 WKWebView
struct BrowserViewRepresentable: UIViewRepresentable {
    let webView = WKWebView()

    func makeUIView(context: Context) -> WKWebView {
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        webView.allowsBackForwardNavigationGestures = true
        webView.scrollView.bounces = true
        webView.customUserAgent = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1 AutoBot/1.0"

        // 注入基础脚本
        let js = """
        // AutoBot 全局对象
        window.AutoBot = {
            version: '1.0',
            debug: false
        };
        console.log('AutoBot JS 环境就绪');
        true;
        """
        let script = WKUserScript(source: js, injectionTime: .atDocumentEnd, forMainFrameOnly: true)
        webView.configuration.userContentController.addUserScript(script)

        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {
        // 页面更新
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    // 加载 URL
    func loadURL(_ url: URL) {
        webView.load(URLRequest(url: url))
    }

    // 执行 JS - 异步返回结果
    func evaluateJavaScript(_ javaScriptString: String) async throws -> [String: Any] {
        return try await withCheckedThrowingContinuation { continuation in
            webView.evaluateJavaScript(javaScriptString) { result, error in
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

    class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate {
        var parent: BrowserViewRepresentable

        init(_ parent: BrowserViewRepresentable) {
            self.parent = parent
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

        // 允许弹窗
        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            completionHandler()
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            completionHandler(true)
        }
    }
}

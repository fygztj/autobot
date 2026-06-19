//
//  AutoBotApp.swift
//  自动化助手 - 通过 WebSocket 接收 PC 端指令执行自动化操作
//

import SwiftUI

@main
struct AutoBotApp: App {
    @StateObject private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .onAppear {
                    // 启动后自动连接服务器
                    appState.startup()
                }
        }
    }
}

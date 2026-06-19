//
//  ContentView.swift
//  主界面 - 显示连接状态、日志和浏览器视图
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject var appState: AppState
    @State private var isShowingSettings = false
    @State private var tempAddress = ""

    var body: some View {
        TabView {
            // Tab 1: 浏览器（自动化操作在这里执行）
            BrowserTabView()
                .tabItem {
                    Label("浏览器", systemImage: "globe")
                }

            // Tab 2: 控制台（显示连接状态和日志）
            ConsoleView()
                .tabItem {
                    Label("控制台", systemImage: "terminal")
                }

            // Tab 3: 设置
            SettingsView()
                .tabItem {
                    Label("设置", systemImage: "gear")
                }
        }
        .onAppear {
            tempAddress = appState.serverAddress
        }
    }
}

// ========== 浏览器视图 ==========
struct BrowserTabView: View {
    @EnvironmentObject var appState: AppState
    @State private var browserView = BrowserViewRepresentable()

    var body: some View {
        VStack(spacing: 0) {
            // 顶部状态条
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
            .padding(.vertical, 8)
            .background(Color(.systemGray6))

            // WebView
            browserView
                .onAppear {
                    appState.webView = browserView.webView
                }
        }
        .edgesIgnoringSafeArea(.bottom)
    }
}

// ========== 控制台视图 ==========
struct ConsoleView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        VStack(spacing: 12) {
            // 连接状态卡片
            VStack(spacing: 8) {
                HStack {
                    Circle()
                        .fill(appState.connectionStatus.color)
                        .frame(width: 12, height: 12)
                    Text("连接状态")
                        .font(.headline)
                    Spacer()
                    Text(appState.connectionStatus.text)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }

                HStack {
                    Text("服务器")
                        .font(.subheadline)
                    Spacer()
                    Text(appState.serverAddress)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }

                HStack {
                    Button(action: {
                        if appState.connectionStatus == .connected {
                            appState.disconnect()
                        } else {
                            appState.connect()
                        }
                    }) {
                        HStack {
                            Image(systemName: appState.connectionStatus == .connected ? "link.circle.fill" : "link.badge.plus")
                            Text(appState.connectionStatus == .connected ? "断开连接" : "连接服务器")
                        }
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(appState.connectionStatus == .connected ? Color.red.opacity(0.1) : Color.green.opacity(0.1))
                        .foregroundColor(appState.connectionStatus == .connected ? .red : .green)
                        .cornerRadius(8)
                    }
                    Spacer()
                }
            }
            .padding(12)
            .background(Color(.systemGray6))
            .cornerRadius(12)
            .padding(.horizontal)

            // 日志
            VStack(alignment: .leading, spacing: 8) {
                Text("日志")
                    .font(.headline)
                    .padding(.horizontal)

                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 4) {
                            ForEach(appState.logs) { log in
                                HStack(alignment: .top) {
                                    Text(DateFormatter.localizedString(from: log.time, dateStyle: .none, timeStyle: .medium))
                                        .font(.system(size: 11))
                                        .foregroundColor(.gray)
                                        .frame(width: 80, alignment: .leading)
                                    Text(log.text)
                                        .font(.system(size: 13))
                                }
                                .id(log.id)
                            }
                        }
                        .padding(.horizontal, 12)
                        .onChange(of: appState.logs.count) { _ in
                            if let last = appState.logs.last {
                                withAnimation {
                                    proxy.scrollTo(last.id, anchor: .bottom)
                                }
                            }
                        }
                    }
                }
                .frame(maxHeight: .infinity)
                .background(Color(.systemGray6))
                .cornerRadius(12)
            }
            .padding(.horizontal)
        }
        .padding(.top, 12)
    }
}

// ========== 设置视图 ==========
struct SettingsView: View {
    @EnvironmentObject var appState: AppState
    @State private var serverAddress: String = ""

    var body: some View {
        Form {
            Section(header: Text("服务器设置")) {
                HStack {
                    Text("服务器地址")
                    TextField("http://192.168.1.100:8550", text: $serverAddress)
                        .multilineTextAlignment(.trailing)
                        .autocapitalization(.none)
                        .keyboardType(.URL)
                }

                Button(action: {
                    appState.serverAddress = serverAddress
                    UserDefaults.standard.set(serverAddress, forKey: "serverAddress")
                    appState.disconnect()
                    appState.connect()
                }) {
                    HStack {
                        Spacer()
                        Text("保存并重连")
                            .foregroundColor(.blue)
                        Spacer()
                    }
                }
            }

            Section(header: Text("设备信息")) {
                HStack {
                    Text("设备名称")
                    Spacer()
                    Text(appState.deviceInfo["device_name"] as? String ?? "")
                        .foregroundColor(.secondary)
                }
                HStack {
                    Text("系统版本")
                    Spacer()
                    Text(appState.deviceInfo["system_version"] as? String ?? "")
                        .foregroundColor(.secondary)
                }
                HStack {
                    Text("App 版本")
                    Spacer()
                    Text(appState.deviceInfo["app_version"] as? String ?? "")
                        .foregroundColor(.secondary)
                }
                HStack {
                    Text("设备 ID")
                    Spacer()
                    Text(String((appState.deviceInfo["device_id"] as? String ?? "").prefix(8)) + "...")
                        .foregroundColor(.secondary)
                        .font(.system(size: 12))
                }
            }

            Section(header: Text("关于")) {
                HStack {
                    Text("AutoBot 自动化助手")
                    Spacer()
                    Text("v1.0")
                        .foregroundColor(.secondary)
                }
                Text("内部使用 - 通过 PC 端控制执行自动化操作")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            }
        }
        .onAppear {
            serverAddress = appState.serverAddress
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(AppState())
}

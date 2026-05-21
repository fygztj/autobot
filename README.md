# autobot - 双平台移动端自动化工具

支持 Android 和 iOS 双平台的自动化工具，提供 OCR 文字识别、图像模板匹配、模拟人类操作等功能。

## 功能特性

- ✅ **双平台支持**：Android (ADB) 和 iOS (tidevice/pymobiledevice3)
- ✅ **智能识别**：OCR 文字识别 + 图像模板匹配
- ✅ **人类模拟**：随机偏移、随机延迟、逐字符输入
- ✅ **任务调度**：Cron 定时 + 间隔执行
- ✅ **多设备管理**：同时控制多台设备，自动分配任务
- ✅ **Web UI**：可视化管理界面

## 安装依赖

```bash
pip install -r requirements.txt
```

## 设备配置

### Android 设备

1. 开启 **USB 调试**（开发者选项中）
2. 通过 USB 连接电脑
3. 验证连接：
   ```bash
   adb devices
   ```

### iOS 设备

#### ⚠️ 项目状态说明
`alibaba/tidevice` 项目已暂停维护，当前不支持 iOS 17+。推荐使用更活跃的替代方案：
- **pymobiledevice3** - 社区活跃的替代方案
- **tidevice3** - 原作者基于 pymobiledevice3 的封装

#### 方式一：使用 tidevice (适用于 iOS 16 及以下)

1. 安装 tidevice：
   ```bash
   pip install tidevice
   ```

2. iOS 设备配置：
   - iOS 16+ 需开启开发者选项：设置 → 隐私与安全性 → 开发者模式 → 重启后确认打开
   - 通过 USB 连接电脑
   - 在设备上信任电脑

3. 验证连接：
   ```bash
   tidevice list
   ```

#### 配置 WDA (WebDriverAgent) - 重要！

iOS 设备需要安装并运行 WDA 才能使用点击、滑动等完整自动化功能。有以下几种方式：

##### 方式 A：使用 Mac + Xcode (最可靠)

1. 克隆 WebDriverAgent：
   ```bash
   git clone https://github.com/appium/WebDriverAgent.git
   cd WebDriverAgent
   ```

2. 在 Xcode 中打开 `WebDriverAgent.xcodeproj`

3. 配置签名：
   - 选中 WebDriverAgent 项目
   - 进入 Signing & Capabilities
   - 勾选 "Automatically manage signing"
   - 选择你的开发者账号（免费账号即可）
   - 修改 Bundle ID 为唯一标识符（如 `com.你的名字.WebDriverAgentRunner`）
   - 对 WebDriverAgentLib、WebDriverAgentRunner、IntegrationApp 都进行相同配置

4. 安装到设备：
   - Target 选择 `WebDriverAgentRunner`
   - 选择你的 iOS 设备
   - 长按运行按钮选择 `Test`，开始编译部署

5. 信任开发者：
   - 手机上：设置 → 通用 → VPN与设备管理 → 信任你的开发者应用

##### 方式 B：使用已签名的 WDA.ipa

如果你有已签名好的 WDA.ipa 文件，可以直接安装：
```bash
tidevice install WebDriverAgent.ipa
```

##### 方式 C：使用 pymobiledevice3 (推荐用于 iOS 17+)

1. 安装 pymobiledevice3：
   ```bash
   pip install pymobiledevice3
   ```

2. 查看设备：
   ```bash
   pymobiledevice3 list
   ```

3. 具体使用方式请参考 pymobiledevice3 文档。

#### 使用 tidevice 启动 WDA

WDA 安装到设备后，使用以下命令启动：
```bash
tidevice xcuitest -B com.facebook.wda.WebDriverAgent.Runner
```

注意替换 Bundle ID 为你实际使用的。

## 启动服务

```bash
python backend/main.py
```

访问 http://localhost:8550 打开 Web UI。

## 任务配置

### Android 应用包名

常见应用包名：
- 微信：`com.tencent.mm`
- 抖音：`com.ss.android.ugc.aweme`
- 小红书：`com.xingin.xhs`

### iOS 应用 Bundle ID

常见应用 Bundle ID：
- 微信：`com.tencent.xin`
- 抖音：`com.ss.iphone.ugc.Aweme`
- 小红书：`com.xingin.XHSGuide`

## 注意事项

- iOS 设备需要配置 WDA (WebDriverAgent) 才能使用完整功能（点击、滑动等）
- iOS 17+ 建议使用 pymobiledevice3 替代 tidevice
- OCR 功能需要联网下载模型（首次使用）
- 请遵守相关平台规定，勿用于非法用途

## 项目结构

```
autobot/
├── backend/
│   ├── main.py          # 入口
│   ├── adb_client.py    # Android 客户端
│   ├── ios_client.py    # iOS 客户端
│   ├── device_manager.py  # 设备管理
│   ├── actions/         # 触控、截图
│   ├── vision/          # OCR、图像匹配
│   ├── tasks/           # 任务管理、调度
│   ├── api/             # REST API
│   └── web/             # Web UI
├── requirements.txt
└── README.md
```

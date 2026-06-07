# iOS 自动化启动指南

## 📋 准备工作

### 设备要求
- iOS 设备已连接到电脑
- 设备已信任开发者（设置 → 通用 → VPN 与设备管理）
- Developer Mode 已开启（设置 → 隐私与安全性 → Developer Mode）

### 软件要求
- Xcode 已安装
- tidevice 已安装
- Python 环境已配置

---

## 🚀 启动步骤

### 步骤1：启动后端服务

```bash
cd /Users/gzt/project/autobot
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8550
```

### 步骤2：启动 WebDriverAgent（WDA）

**方式一：通过 Xcode 启动（推荐）**

1. 打开 Xcode
2. 打开项目：`/Users/gzt/project/autobot/WebDriverAgent/WebDriverAgent.xcodeproj`
3. 在顶部工具栏选择：
   - **Scheme**: `IntegrationApp`
   - **Device**: 选择你的 iOS 设备
4. 点击 **Run** 按钮（▶️）
5. 等待设备屏幕显示 **"automation running"**

**方式二：通过命令行启动（需要开发者镜像）**

```bash
# 设置环境变量
export TIDEVICE_HOME=/Users/gzt/project/autobot/data/app_data/tidevice

# 启动 WDA
tidevice -u <设备UDID> launch com.freeBirdBot.WebDriverAgentRunner

# 启动端口转发
iproxy 8100 8100
```

### 步骤3：验证 WDA 连接

```bash
# 测试 WDA 是否正常运行
curl http://localhost:8100/status

# 预期输出：
# {"sessionId":"xxx","value":{"state":"success",...}}
```

### 步骤4：启动任务

1. 打开浏览器访问：http://localhost:8550
2. 在设备列表中选择你的 iOS 设备
3. 点击"执行任务"按钮

---

## ⚠️ 常见问题

### Q1：设备上没有显示 "automation running"

**解决方案**：
1. 检查设备是否已连接
2. 检查 Xcode 是否选择了正确的设备
3. 尝试重启设备后重新运行

### Q2：端口连接被拒绝

**解决方案**：
```bash
# 检查端口转发
ps aux | grep iproxy

# 如果没有运行，启动端口转发
iproxy 8100 8100 &
```

### Q3：WDA 挂起（Hang detected）

**解决方案**：
1. 在 Xcode 中点击 **Stop** 按钮
2. 等待10秒
3. 重新点击 **Run** 按钮

### Q4：需要重启设备才能正常工作

**解决方案**：
- 这是 iOS 18.5 的已知问题
- 建议每天第一次使用时重启设备
- 之后可以通过 Xcode 重启 WDA，无需重启设备

---

## 📝 常用命令

```bash
# 查看设备列表
idevice_id -l

# 查看已安装的应用
tidevice applist

# 启动端口转发
iproxy 8100 8100 &

# 测试 WDA 连接
curl http://localhost:8100/status

# 获取当前前台应用
curl http://localhost:8100/wda/activeAppInfo
```

---

## 📁 项目结构

```
autobot/
├── WebDriverAgent/          # WDA 项目
├── backend/                 # 后端代码
│   ├── ios_client.py        # iOS 客户端
│   ├── device_manager.py    # 设备管理器
│   └── apps/                # 应用执行器
├── data/app_data/tidevice/  # tidevice 数据目录
└── STARTUP_GUIDE.md         # 本文件
```

---

## 📞 故障排除流程

```
问题现象 → 检查项 → 解决方案

1. 设备不显示 → 检查 USB 连接 → 重新插拔设备
2. WDA 不启动 → 检查签名配置 → 在 Xcode 中检查 Signing
3. 端口被拒绝 → 检查 iproxy → 重启端口转发
4. 任务执行失败 → 检查应用是否在前台 → 手动打开应用
```

---

**最后更新**: 2026-06-07
**版本**: v1.0
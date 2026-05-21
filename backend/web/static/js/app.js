/**
 * autobot Web UI - Main JavaScript
 */

const API = {
    async get(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    async post(url, data) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    async put(url, data) {
        const res = await fetch(url, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
    async del(url) {
        const res = await fetch(url, { method: 'DELETE' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    },
};

function toast(msg, type = 'info') {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
}

// ======================= 设备面板 =======================

// 切换任务模式
function switchTaskMode() {
    const isAdvanced = document.getElementById('advancedMode').checked;
    document.getElementById('normalTaskSection').style.display = isAdvanced ? 'none' : 'block';
    document.getElementById('advancedTaskSection').style.display = isAdvanced ? 'block' : 'none';
}

// 解析高级任务配置
function getAdvancedConfig() {
    return {
        app: document.getElementById('advApp').value,
        topics: document.getElementById('advTopics').value.split('\n').map(t => t.trim()).filter(t => t),
        like_config: {
            enabled: document.getElementById('advLikeEnabled').checked,
            rate: parseFloat(document.getElementById('advLikeRate').value) || 0
        },
        comment_config: {
            enabled: document.getElementById('advCommentEnabled').checked,
            rate: parseFloat(document.getElementById('advCommentRate').value) || 0
        },
        mention_config: {
            enabled: document.getElementById('advMentionEnabled').checked,
            rate: parseFloat(document.getElementById('advMentionRate').value) || 0
        },
        comment_templates: document.getElementById('advCommentTemplates').value.split('\n').map(t => t.trim()).filter(t => t),
        mention_users: document.getElementById('advMentionUsers').value.split('\n').map(t => t.trim()).filter(t => t),
        view_interval: {
            min_sec: parseFloat(document.getElementById('advViewMin').value) || 2,
            max_sec: parseFloat(document.getElementById('advViewMax').value) || 4
        },
        like_interval: {
            min_sec: parseFloat(document.getElementById('advLikeMin').value) || 0.5,
            max_sec: parseFloat(document.getElementById('advLikeMax').value) || 1.5
        },
        comment_interval: {
            min_sec: parseFloat(document.getElementById('advCommentMin').value) || 2,
            max_sec: parseFloat(document.getElementById('advCommentMax').value) || 5
        },
        mention_interval: {
            min_sec: parseFloat(document.getElementById('advMentionMin').value) || 1,
            max_sec: parseFloat(document.getElementById('advMentionMax').value) || 3
        },
        force_work_min: parseInt(document.getElementById('advForceWorkMin').value) || 60,
        force_sleep_min: parseInt(document.getElementById('advForceSleepMin').value) || 30,
        max_view_count: parseInt(document.getElementById('advMaxViewCount').value) || 500
    };
}

async function refreshDevices() {
    try {
        const data = await API.get('/api/devices');
        const container = document.getElementById('deviceList');
        if (!data.devices.length) {
            container.innerHTML = '<div class="empty-state">暂无已连接设备<br>请通过 USB 连接 Android 或 iOS 设备</div>';
            return;
        }
        container.innerHTML = data.devices.map(d => `
            <div class="device-card">
                <div class="model">
                    <span class="os-badge os-${d.os_type}">${d.os_type}</span>
                    ${d.info.model || '未知设备'}
                </div>
                <div class="serial">${d.serial}</div>
                <div>
                    ${d.os_type === 'Android' ? `Android ${d.info.android_version || '?'}` : `iOS ${d.info.os_version || '?'}`}
                    | ${d.info.screen_width || '?'}x${d.info.screen_height || '?'}
                </div>
                <div class="status ${d.is_busy ? 'status-busy' : 'status-idle'}">
                    ${d.is_busy ? '● 忙碌' : '● 空闲'}
                </div>
                <div style="margin-top:8px">
                    <button class="btn btn-sm btn-default" onclick="showDeviceOCR('${d.serial}')">OCR 识别</button>
                </div>
            </div>
        `).join('');
        document.getElementById('deviceCount').textContent = data.total;
        document.getElementById('idleCount').textContent = data.devices.filter(d => !d.is_busy).length;
    } catch (e) {
        console.error(e);
    }
}

async function showDeviceOCR(serial) {
    try {
        toast('正在识别...', 'info');
        const data = await API.get(`/api/devices/${serial}/ocr`);
        const texts = data.texts.map(t => `${t.text} (${t.confidence})`).join('\n');
        alert(`屏幕文字:\n\n${texts}`);
    } catch (e) {
        toast('OCR 识别失败', 'error');
    }
}

// ======================= 任务面板 =======================

async function refreshTasks() {
    try {
        const data = await API.get('/api/tasks');
        const container = document.getElementById('taskList');
        if (!data.tasks.length) {
            container.innerHTML = '<div class="empty-state">暂无任务<br>点击下方按钮创建新任务</div>';
            return;
        }
        container.innerHTML = data.tasks.map(t => `
            <div class="task-item">
                <div class="task-header">
                    <span class="task-name">${t.name}</span>
                    <span class="task-app">${t.is_advanced ? '⭐ 高级' : (t.app || '通用')}</span>
                </div>
                <div class="task-meta">
                    ${t.is_advanced ? 
                        `主题: ${(t.advanced_config?.topics || []).join(', ')} | 点赞:${(t.advanced_config?.like_config?.rate * 100) || 0}% 评论:${(t.advanced_config?.comment_config?.rate * 100) || 0}%` :
                        `操作步骤: ${(t.actions || []).length}`
                    } |
                    定时规则: ${t.schedule && t.schedule.type ? t.schedule.type : '手动执行'} |
                    已执行: ${t.run_count}次 (成功${t.success_count} / 失败${t.fail_count})
                    ${t.enabled ? '' : ' | <span style="color:#ff4d4f">已禁用</span>'}
                </div>
                <div class="task-actions">
                    <button class="btn btn-sm btn-success" onclick="runTask('${t.task_id}')">▶ 执行</button>
                    <button class="btn btn-sm btn-primary" onclick="runTaskAll('${t.task_id}')">▶ 全部执行</button>
                    <button class="btn btn-sm btn-default" onclick="editTask('${t.task_id}')">编辑</button>
                    <button class="btn btn-sm btn-danger" onclick="deleteTask('${t.task_id}')">删除</button>
                </div>
            </div>
        `).join('');
        document.getElementById('taskCount').textContent = data.total;
    } catch (e) {
        console.error(e);
    }
}

async function runTask(taskId) {
    try {
        await API.post(`/api/tasks/${taskId}/run`);
        toast('任务已提交执行', 'success');
    } catch (e) {
        toast('执行失败: ' + e.message, 'error');
    }
}

async function runTaskAll(taskId) {
    try {
        await API.post(`/api/tasks/${taskId}/run-all`);
        toast('任务已分发到所有空闲设备', 'success');
    } catch (e) {
        toast('执行失败: ' + e.message, 'error');
    }
}

async function deleteTask(taskId) {
    if (!confirm('确定要删除此任务吗？')) return;
    try {
        await API.del(`/api/tasks/${taskId}`);
        toast('任务已删除', 'success');
        refreshTasks();
    } catch (e) {
        toast('删除失败', 'error');
    }
}

// ======================= 创建任务 =======================

let actionList = [];

function addAction() {
    const container = document.getElementById('actionList');
    const idx = actionList.length;
    actionList.push({ type: 'tap', params: {} });

    const row = document.createElement('div');
    row.className = 'action-row';
    row.id = `action-${idx}`;
    row.innerHTML = `
        <span class="drag-handle">☰</span>
        <select class="form-control" onchange="updateActionType(${idx}, this.value)">
            <option value="tap">点击坐标</option>
            <option value="tap_text">点击文字(OCR)</option>
            <option value="tap_image">点击图片(模板匹配)</option>
            <option value="swipe_up">向上滑动</option>
            <option value="swipe_down">向下滑动</option>
            <option value="swipe_left">向左滑动</option>
            <option value="swipe_right">向右滑动</option>
            <option value="type">输入文字</option>
            <option value="long_press">长按</option>
            <option value="press_back">返回键</option>
            <option value="press_home">Home键</option>
            <option value="press_enter">回车键</option>
            <option value="wait">等待</option>
            <option value="random_wait">随机等待</option>
            <option value="start_app">启动应用</option>
            <option value="stop_app">停止应用</option>
            <option value="wait_text">等待文字出现</option>
            <option value="wait_image">等待图片出现</option>
            <option value="scroll_until_text">滚动查找文字</option>
            <option value="swipe_up_multiple">连续滑动</option>
            <option value="swipe_to_refresh">下拉刷新</option>
            <option value="screenshot">截图</option>
        </select>
        <input class="form-control" id="action-params-${idx}" placeholder="参数 (JSON格式，如: {} )"/>
        <button class="btn btn-sm btn-danger" onclick="removeAction(${idx})">✕</button>
    `;
    container.appendChild(row);
}

function updateActionType(idx, type) {
    actionList[idx].type = type;
    // 设置默认参数
    const defaults = {
        tap: { x: 0.5, y: 0.5 },
        tap_text: { text: '在这里输入要点击的文字' },
        tap_image: { template: 'template.png' },
        swipe_up: { distance: 0.5 },
        swipe_down: { distance: 0.5 },
        swipe_left: { distance: 0.5 },
        swipe_right: { distance: 0.5 },
        type: { text: '要输入的文字' },
        long_press: { x: 0.5, y: 0.5, duration_ms: 1000 },
        wait: { seconds: 1.0 },
        random_wait: { min: 0.5, max: 2.0 },
        start_app: { package: 'com.tencent.mm' },
        stop_app: { package: 'com.tencent.mm' },
        wait_text: { text: '文字', timeout: 10 },
        scroll_until_text: { text: '文字', max_scrolls: 10 },
        swipe_up_multiple: { count: 3, interval: 1.0 },
    };
    const params = defaults[type] || {};
    actionList[idx].params = params;
    document.getElementById(`action-params-${idx}`).value = JSON.stringify(params, null, 2);
}

function removeAction(idx) {
    actionList.splice(idx, 1);
    const el = document.getElementById(`action-${idx}`);
    if (el) el.remove();
    // 重建索引
    rebuildActionList();
}

function rebuildActionList() {
    const container = document.getElementById('actionList');
    const rows = container.querySelectorAll('.action-row');
    rows.forEach((row, i) => {
        row.id = `action-${i}`;
        row.querySelector('select').setAttribute('onchange', `updateActionType(${i}, this.value)`);
        row.querySelector('input').id = `action-params-${i}`;
        const btn = row.querySelector('button');
        if (btn) btn.setAttribute('onclick', `removeAction(${i})`);
    });
}

async function createTask() {
    const name = document.getElementById('taskName').value.trim();
    const description = document.getElementById('taskDesc').value.trim();
    const scheduleType = document.getElementById('scheduleType').value;
    const isAdvanced = document.getElementById('advancedMode').checked;

    if (!name) { toast('请输入任务名称', 'error'); return; }

    let schedule = {};
    if (scheduleType === 'cron') {
        schedule = {
            type: 'cron',
            hour: document.getElementById('cronHour').value || '*',
            minute: document.getElementById('cronMinute').value || '0',
        };
    } else if (scheduleType === 'interval') {
        schedule = {
            type: 'interval',
            minutes: parseInt(document.getElementById('intervalMinutes').value) || 30,
        };
    }

    let taskData = {
        name,
        description,
        schedule,
        target_devices: [],
        is_advanced: isAdvanced
    };

    if (isAdvanced) {
        taskData.app = document.getElementById('advApp').value;
        taskData.actions = [];
        taskData.advanced_config = getAdvancedConfig();
    } else {
        // 收集所有 action 的当前参数
        for (let i = 0; i < actionList.length; i++) {
            const paramsEl = document.getElementById(`action-params-${i}`);
            if (paramsEl) {
                try {
                    actionList[i].params = JSON.parse(paramsEl.value);
                } catch (e) {
                    toast(`步骤 ${i+1} 参数格式错误`, 'error');
                    return;
                }
            }
        }
        taskData.app = document.getElementById('taskApp').value;
        taskData.actions = actionList;
    }

    try {
        const task = await API.post('/api/tasks', taskData);
        toast('任务创建成功', 'success');
        actionList = [];
        document.getElementById('actionList').innerHTML = '';
        document.getElementById('taskName').value = '';
        document.getElementById('taskDesc').value = '';
        refreshTasks();
    } catch (e) {
        toast('创建失败: ' + e.message, 'error');
    }
}

// ======================= 初始化和定时刷新 =======================

document.addEventListener('DOMContentLoaded', () => {
    refreshDevices();
    refreshTasks();

    // 定时刷新
    setInterval(refreshDevices, 5000);
    setInterval(refreshTasks, 5000);

    // 定时配置切换
    document.getElementById('scheduleType').addEventListener('change', function() {
        document.getElementById('cronConfig').style.display = this.value === 'cron' ? 'block' : 'none';
        document.getElementById('intervalConfig').style.display = this.value === 'interval' ? 'block' : 'none';
    });
});

// ======================= 编辑任务(简易版) =======================

async function editTask(taskId) {
    try {
        const task = await API.get(`/api/tasks/${taskId}`);
        const newName = prompt('任务名称:', task.name);
        if (!newName) return;
        const enabled = confirm('启用该任务? (确定=启用, 取消=禁用)');
        await API.put(`/api/tasks/${taskId}`, {
            name: newName,
            enabled: enabled,
        });
        toast('任务已更新', 'success');
        refreshTasks();
    } catch (e) {
        toast('编辑失败', 'error');
    }
}
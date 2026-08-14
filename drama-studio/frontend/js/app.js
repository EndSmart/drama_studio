/**
 * Drama Studio 前端逻辑
 * - 加载 provider 配置
 * - 创建项目、启动流水线
 * - WebSocket 实时进度
 * - 查看产物、下载成片
 */

let currentProjectId = null;
let ws = null;
let providerData = null;

// 交互式精修模式相关状态
let currentMode = 'auto';                       // 'auto' | 'interactive'
let interactiveStages = [];                     // 阶段 key 顺序
let interactiveCurrent = null;                  // 当前阶段 key
let currentEnvelope = null;                     // 当前阶段产物信封
let interactiveConfig = null;                   // {target_duration, llm_provider, ...}
let interactiveApiKeys = null;                  // {llm_api_key, video_api_key, image_api_key}
let currentUserRole = null;                     // 'admin' | 'user'

// ============ 初始化 ============
document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
});

// ============ 登录鉴权 ============
async function checkAuth() {
    try {
        const resp = await fetch('/api/me');
        if (resp.ok) {
            const me = await resp.json();
            onAuthed(me);
            return;
        }
    } catch (e) { /* ignore */ }
    // 未登录：展示登录遮罩
    document.getElementById('loginOverlay').style.display = 'flex';
}

function onAuthed(me) {
    document.getElementById('loginOverlay').style.display = 'none';
    document.getElementById('userPill').style.display = 'inline-flex';
    document.getElementById('userName').textContent = me.username;
    document.getElementById('btnUserMgmt').style.display =
        (me.role === 'admin') ? 'inline-block' : 'none';
    currentUserRole = me.role;
    loadProviders();
    updateProviderHint();
}

async function doLogin() {
    const username = document.getElementById('loginUser').value.trim();
    const password = document.getElementById('loginPass').value;
    if (!username || !password) { showLoginHint('请输入用户名和密码'); return; }

    const btn = document.getElementById('btnLogin');
    btn.disabled = true;
    btn.textContent = '登录中…';
    try {
        const resp = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            showLoginHint(err.detail || '登录失败');
            return;
        }
        const me = await resp.json();
        onAuthed(me);
        document.getElementById('loginUser').value = '';
        document.getElementById('loginPass').value = '';
        document.getElementById('loginHint').textContent = '';
    } catch (e) {
        showLoginHint('登录失败: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '登录';
    }
}

function showLoginHint(msg) {
    document.getElementById('loginHint').textContent = msg;
}

async function logout() {
    try { await fetch('/api/logout', { method: 'POST' }); } catch (e) {}
    document.getElementById('userPill').style.display = 'none';
    document.getElementById('btnUserMgmt').style.display = 'none';
    // 重置界面
    resetUI();
    if (ws) { try { ws.close(); } catch (e) {} ws = null; }
    document.getElementById('loginOverlay').style.display = 'flex';
    showLoginHint('');
}

// ============ 用户管理（仅管理员） ============
async function showUserMgmt() {
    try {
        const resp = await fetch('/api/users');
        if (!resp.ok) { showToast('无权访问'); return; }
        const data = await resp.json();
        const meName = document.getElementById('userName').textContent;
        const list = document.getElementById('userList');
        list.innerHTML = data.users.map(u => `
            <div class="user-item">
                <div class="user-info">
                    <span class="user-name">${escapeHtml(u.username)}</span>
                    <span class="user-role ${u.role}">${u.role === 'admin' ? '管理员' : '普通用户'}</span>
                </div>
                ${u.username === meName ? '' : '<button class="btn btn-ghost btn-sm" onclick="deleteUser(\'' + escapeHtml(u.username) + '\')">删除</button>'}
            </div>
        `).join('');
        document.getElementById('userModal').style.display = 'flex';
    } catch (e) {
        showToast('加载用户失败: ' + e.message);
    }
}

function closeUserMgmt() {
    document.getElementById('userModal').style.display = 'none';
}

async function addUser() {
    const username = document.getElementById('newUserName').value.trim();
    const password = document.getElementById('newUserPass').value;
    const role = document.getElementById('newUserRole').value;
    if (!username || !password) { showToast('请填写用户名和密码'); return; }
    try {
        const resp = await fetch('/api/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role }),
        });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            showToast(err.detail || '添加失败');
            return;
        }
        document.getElementById('newUserName').value = '';
        document.getElementById('newUserPass').value = '';
        showUserMgmt();
    } catch (e) {
        showToast('添加失败: ' + e.message);
    }
}

async function deleteUser(username) {
    if (!confirm('确定删除用户「' + username + '」？')) return;
    try {
        const resp = await fetch('/api/users/' + encodeURIComponent(username), { method: 'DELETE' });
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            showToast(err.detail || '删除失败');
            return;
        }
        showUserMgmt();
    } catch (e) {
        showToast('删除失败: ' + e.message);
    }
}

async function loadProviders() {
    try {
        const resp = await fetch('/api/providers');
        providerData = await resp.json();
        populateSelect('llmProvider', providerData.llm, 'key', 'name');
        populateSelect('videoProvider', providerData.video, 'key', 'name');
        populateSelect('imageProvider', providerData.image, 'key', 'name');
        // 设置默认
        document.getElementById('llmProvider').value = providerData.defaults.llm;
        document.getElementById('videoProvider').value = providerData.defaults.video;
        document.getElementById('imageProvider').value = providerData.defaults.image;
    } catch (e) {
        showToast('加载配置失败: ' + e.message);
    }
}

function populateSelect(id, items, valKey, labelKey) {
    const sel = document.getElementById(id);
    sel.innerHTML = '';
    (items || []).forEach(item => {
        const opt = document.createElement('option');
        opt.value = item[valKey];
        opt.textContent = `${item[labelKey]}${item.configured ? ' ✓' : ''}`;
        sel.appendChild(opt);
    });
}

function updateProviderHint() {
    if (!providerData) return;
    const llm = providerData.llm || [];
    const configured = llm.filter(p => p.configured).map(p => p.name);
    const hint = document.getElementById('providerHint');
    if (configured.length) {
        hint.textContent = `✅ 已配置环境变量: ${configured.join('、')}。未配置的需在下方输入 API Key。`;
    } else {
        hint.textContent = '💡 所有模型均需在下方输入 API Key（或设置环境变量）。视频/图像平台同理。';
    }
}

// ============ 启动流水线 ============
async function startPipeline() {
    const theme = document.getElementById('theme').value.trim();
    if (!theme) { showToast('请输入创作主题'); return; }

    // 切换面板：auto 显示进度面板，interactive 在创建项目后显示精修面板
    document.querySelector('.setup-panel').style.display = 'block';
    document.querySelector('.progress-panel').style.display = 'block';
    document.getElementById('interactivePanel').style.display = 'none';

    const config = {
        target_duration: parseInt(document.getElementById('duration').value) || 60,
        aspect_ratio: document.getElementById('aspectRatio').value,
        style: document.getElementById('style').value,
        genre_hint: document.getElementById('genreHint').value.trim(),
        llm_provider: document.getElementById('llmProvider').value,
        video_provider: document.getElementById('videoProvider').value,
        image_provider: document.getElementById('imageProvider').value,
    };

    const apiKeys = {
        llm_api_key: document.getElementById('llmApiKey').value.trim(),
        video_api_key: document.getElementById('videoApiKey').value.trim(),
        image_api_key: document.getElementById('imageApiKey').value.trim(),
    };

    // 创建项目
    const btn = document.getElementById('btnGenerate');
    btn.disabled = true;
    btn.textContent = '⏳ 创建项目中...';
    resetUI();

    try {
        const resp = await fetch('/api/projects', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ theme, config })
        });
        if (!resp.ok) throw new Error((await resp.json()).detail || '创建失败');
        const project = await resp.json();
        currentProjectId = project.id;

        // 交互式精修模式：创建项目后即进入分步工作区（不再一键跑完）
        if (currentMode === 'interactive') {
            btn.disabled = false;
            btn.textContent = '⚡ 开始制作短剧';
            await enterInteractive(project.id, config, apiKeys);
            return;
        }

        connectWS(project.id);
        addLog('system', '系统', `项目创建成功: ${project.id}`);

        // 启动流水线
        btn.textContent = '⏳ 智能体集群工作中...';
        const runResp = await fetch(`/api/projects/${project.id}/run`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                llm_provider: config.llm_provider,
                api_key: apiKeys.llm_api_key || null,
                config
            })
        });
        if (!runResp.ok) throw new Error((await runResp.json()).detail || '启动失败');
        addLog('system', '系统', '智能体集群已启动，9 阶段流水线执行中...');
    } catch (e) {
        showToast('启动失败: ' + e.message);
        btn.disabled = false;
        btn.textContent = '⚡ 开始制作短剧';
    }
}

// ============ WebSocket 进度 ============
function connectWS(projectId) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws/${projectId}`);

    ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'pong' || msg.type === 'connected') return;
        handleProgress(msg);
    };
    ws.onclose = () => { /* 可重连 */ };
}

function handleProgress(event) {
    const stage = event.stage;
    const status = event.status;
    const message = event.message || '';

    if (stage === 'pipeline') {
        if (status === 'completed') {
            markStageAllDone();
            showResult();
        } else if (status === 'failed') {
            markError();
            addLog('error', stage, message);
            const btn = document.getElementById('btnGenerate');
            btn.disabled = false;
            btn.textContent = '⚡ 开始制作短剧';
            showToast('制作失败: ' + message);
        }
        return;
    }

    const stageEl = document.querySelector(`.stage[data-stage="${stage}"]`);
    if (status === 'running') {
        stageEl?.classList.add('active');
        addLog('info', stage, message);
        updateProgress(stage);
    } else if (status === 'completed') {
        stageEl?.classList.remove('active');
        stageEl?.classList.add('done');
        addLog('success', stage, message);
    } else if (status === 'failed') {
        stageEl?.classList.add('error');
        addLog('error', stage, message);
    }
}

function updateProgress(stage) {
    const stages = ['director', 'screenwriter', 'storyboarder', 'character_designer', 'video_producer', 'editor'];
    const idx = stages.indexOf(stage);
    const pct = Math.round(((idx + 1) / stages.length) * 100);
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressText').textContent = `当前阶段: ${stageName(stage)} (${pct}%)`;
}

function stageName(stage) {
    const map = {
        director: '总导演分析',
        screenwriter: '编剧创作',
        storyboarder: '分镜设计',
        character_designer: '角色设计',
        video_producer: '视频生成',
        editor: '剪辑成片',
    };
    return map[stage] || stage;
}

function markStageAllDone() {
    document.querySelectorAll('.stage').forEach(el => {
        el.classList.remove('active');
        el.classList.add('done');
    });
    document.getElementById('progressFill').style.width = '100%';
    document.getElementById('progressText').textContent = '✅ 全部完成';
}

function markError() {
    const current = document.querySelector('.stage.active');
    if (current) { current.classList.remove('active'); current.classList.add('error'); }
}

// ============ 日志 ============
function addLog(type, stage, message) {
    const logArea = document.getElementById('logArea');
    document.getElementById('logEmpty').style.display = 'none';

    const now = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    const line = document.createElement('div');
    line.className = `log-line ${type}`;
    line.innerHTML = `<span class="ts">${now}</span><span class="stage-tag">[${stageName(stage)}]</span><span class="msg">${escapeHtml(message)}</span>`;
    logArea.appendChild(line);
    logArea.scrollTop = logArea.scrollHeight;
}

function escapeHtml(str) {
    return String(str).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function resetUI() {
    document.getElementById('logArea').innerHTML = '<div class="log-empty" id="logEmpty">进度日志将在这里显示</div>';
    document.getElementById('resultArea').style.display = 'none';
    document.querySelectorAll('.stage').forEach(el => {
        el.className = 'stage';
    });
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('progressText').textContent = '等待开始...';
}

// ============ 结果 ============
async function showResult() {
    const resp = await fetch(`/api/projects/${currentProjectId}`);
    const state = await resp.json();
    const result = state.result || {};

    document.getElementById('resultArea').style.display = 'block';
    document.getElementById('resultMeta').innerHTML = `
        时长: <b>${(result.duration_seconds || 0).toFixed(1)} 秒</b><br>
        镜头数: <b>${result.shot_count || 0}</b> 个<br>
        字幕: <b>${result.subtitle_count || 0}</b> 条<br>
        状态: <b style="color:#22c55e">${state.status}</b>
    `;
    const btn = document.getElementById('btnGenerate');
    btn.disabled = false;
    btn.textContent = '⚡ 开始制作短剧';
}

function downloadFinal() {
    if (!currentProjectId) return;
    window.location.href = `/api/projects/${currentProjectId}/final`;
}

// ============ 项目历史 ============
async function showProjects() {
    const resp = await fetch('/api/projects');
    const data = await resp.json();
    const list = document.getElementById('projectsList');
    if (!data.projects.length) {
        list.innerHTML = '<p style="color:#8a90a0;text-align:center;padding:20px">暂无项目</p>';
    } else {
        list.innerHTML = data.projects.map(p => `
            <div class="project-item" onclick="loadProject('${p.id}')">
                <div class="p-title">${escapeHtml(p.title)}</div>
                <div class="p-meta">ID: ${p.id} · 状态: ${p.status} · ${p.updated_at || ''}</div>
            </div>
        `).join('');
    }
    document.getElementById('projectsModal').style.display = 'flex';
}

function closeProjects() {
    document.getElementById('projectsModal').style.display = 'none';
}

async function loadProject(id) {
    currentProjectId = id;
    closeProjects();
    connectWS(id);
    resetUI();
    addLog('system', '系统', `已加载项目: ${id}`);

    const resp = await fetch(`/api/projects/${id}`);
    const state = await resp.json();
    // 恢复进度显示
    const stagesDone = Object.entries(state.stages || {})
        .filter(([, v]) => v.status === 'completed')
        .map(([k]) => k);
    stagesDone.forEach(s => {
        const el = document.querySelector(`.stage[data-stage="${s}"]`);
        el?.classList.add('done');
    });
    if (state.status === 'completed') {
        markStageAllDone();
        showResult();
    }
}

// ============ 产物 ============
async function viewArtifacts() {
    if (!currentProjectId) return;
    const resp = await fetch(`/api/projects/${currentProjectId}/artifacts`);
    const data = await resp.json();
    const list = document.getElementById('artifactsList');
    if (!data.artifacts.length) {
        list.innerHTML = '<p style="color:#8a90a0;text-align:center;padding:20px">暂无产物</p>';
    } else {
        list.innerHTML = data.artifacts.map(a => `
            <div class="project-item" onclick="viewArtifactContent('${a.path}')">
                <div class="p-title">📄 ${escapeHtml(a.path.split('/').pop())}</div>
                <div class="p-meta">${escapeHtml(a.path)} · ${formatSize(a.size)}</div>
            </div>
        `).join('');
    }
    document.getElementById('artifactsModal').style.display = 'flex';
}

function closeArtifacts() {
    document.getElementById('artifactsModal').style.display = 'none';
}

async function viewArtifactContent(path) {
    const resp = await fetch(`/api/projects/${currentProjectId}/artifacts/content?path=${encodeURIComponent(path)}`);
    if (!resp.ok) return;
    const data = await resp.json();
    const win = window.open('', '_blank');
    win.document.write(`<pre style="font-size:12px;white-space:pre-wrap;word-break:break-all;padding:20px">${escapeHtml(data.content)}</pre>`);
    win.document.close();
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
    return (bytes/(1024*1024)).toFixed(1) + ' MB';
}

// ============ Toast ============
function showToast(msg) {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 3000);
}

// ============ 制作模式切换 ============
function setMode(m) {
    currentMode = m;
    document.querySelectorAll('#modeToggle .seg').forEach(b => {
        b.classList.toggle('active', b.dataset.mode === m);
    });
}

// ============ 交互式精修 ============
async function enterInteractive(projectId, config, apiKeys) {
    document.querySelector('.setup-panel').style.display = 'none';
    document.querySelector('.progress-panel').style.display = 'none';
    document.getElementById('interactivePanel').style.display = 'block';
    document.getElementById('interactiveResult').style.display = 'none';
    interactiveConfig = config;
    interactiveApiKeys = apiKeys;

    try {
        const resp = await fetch(`/api/projects/${projectId}/stages`);
        const data = await resp.json();
        interactiveStages = data.order || [];
        renderStepper();
        if (interactiveStages.length) {
            await runStage(interactiveStages[0], 'run');
        }
    } catch (e) {
        showToast('加载阶段失败: ' + e.message);
    }
}

async function runStage(stage, action, instruction = null) {
    setStageLoading(true);
    const body = {
        stage: stage,
        action: action,
        llm_provider: interactiveConfig.llm_provider,
        api_key: interactiveApiKeys.llm_api_key || null,
        video_provider: interactiveConfig.video_provider,
        video_api_key: interactiveApiKeys.video_api_key || null,
        image_provider: interactiveConfig.image_provider,
        image_api_key: interactiveApiKeys.image_api_key || null,
        config: interactiveConfig,
        instruction: instruction,
    };
    if (action === 'save') {
        body.content = document.getElementById('stageEditor').value;
    }
    try {
        const resp = await fetch(`/api/projects/${currentProjectId}/stage`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!resp.ok) throw new Error((await resp.json()).detail || '执行失败');
        const data = await resp.json();
        currentEnvelope = data.artifact;
        interactiveCurrent = stage;
        renderStageEditor(currentEnvelope);
    } catch (e) {
        showToast('阶段执行失败: ' + e.message);
    } finally {
        setStageLoading(false);
    }
}

function renderStageEditor(env) {
    updateStepper(env.stage);
    document.getElementById('stageTitle').textContent = env.label;
    document.getElementById('stageHint').textContent = env.hint || '';

    // 只读上下文
    const ctxBox = document.getElementById('stageContext');
    if (env.context && env.context.length) {
        ctxBox.style.display = 'block';
        document.getElementById('stageContextContent').textContent =
            env.context.map(c => c.content).join('\n\n');
    } else {
        ctxBox.style.display = 'none';
    }

    // 可编辑产物
    const editor = document.getElementById('stageEditor');
    editor.value = env.content || '';
    editor.readOnly = !env.editable;
    editor.classList.toggle('readonly', !env.editable);
    document.getElementById('stageInstruction').value = '';

    // 按钮显隐
    const showEdit = !!env.editable;
    document.getElementById('btnSaveContinue').style.display = showEdit ? '' : 'none';
    document.getElementById('btnRefine').style.display = showEdit ? '' : 'none';
    document.getElementById('btnPrev').disabled =
        interactiveStages.indexOf(env.stage) <= 0;

    // 末阶段：展示完成结果
    if (!env.next_stage) {
        showInteractiveResult(env);
    } else {
        document.getElementById('interactiveResult').style.display = 'none';
    }
}

function showInteractiveResult(env) {
    const result = safeParse(env.content) || {};
    document.getElementById('interactiveResult').style.display = 'block';
    document.getElementById('interactiveResultMeta').innerHTML = `
        时长: <b>${(result.duration_seconds || 0).toFixed(1)} 秒</b><br>
        镜头数: <b>${result.shot_count || 0}</b> 个<br>
        字幕: <b>${result.subtitle_count || 0}</b> 条<br>
        状态: <b style="color:#22c55e">${result.downloadable ? '可下载' : '已完成'}</b>
    `;
}

async function stageSaveContinue() {
    const env = currentEnvelope;
    if (!env) return;
    if (env.editable) {
        await runStage(env.stage, 'save');
    }
    if (!env.next_stage) {
        showInteractiveResult(env);
        return;
    }
    await runStage(env.next_stage, 'run');
}

async function stageRefine() {
    const instr = document.getElementById('stageInstruction').value.trim();
    if (!instr) { showToast('请先填写润色 / 修改指令'); return; }
    await runStage(interactiveCurrent, 'refine', instr);
}

async function stageRerun() {
    await runStage(interactiveCurrent, 'run');
}

async function stagePrev() {
    const idx = interactiveStages.indexOf(interactiveCurrent);
    if (idx <= 0) return;
    await runStage(interactiveStages[idx - 1], 'run');
}

function setStageLoading(b) {
    ['btnSaveContinue', 'btnRefine', 'btnRerun', 'btnPrev'].forEach(id => {
        document.getElementById(id).disabled = b;
    });
    document.getElementById('stageLoading').style.display = b ? 'inline' : 'none';
}

function toggleContext() {
    const c = document.getElementById('stageContextContent');
    c.style.display = (c.style.display === 'none') ? 'block' : 'none';
}

// ============ 步骤条 ============
function renderStepper() {
    const el = document.getElementById('stepper');
    el.innerHTML = interactiveStages.map((s, i) =>
        `<div class="step" id="step-${s}" data-stage="${s}">
            <span class="step-dot">${i + 1}</span>
            <span class="step-label">${stageLabel(s)}</span>
         </div>`).join('');
}

function updateStepper(current) {
    const idx = interactiveStages.indexOf(current);
    interactiveStages.forEach((s, i) => {
        const el = document.getElementById('step-' + s);
        if (!el) return;
        el.classList.remove('active', 'done');
        if (i < idx) el.classList.add('done');
        else if (i === idx) el.classList.add('active');
    });
}

function stageLabel(s) {
    const map = {
        screenwriter: '编剧', storyboarder: '分镜',
        character_designer: '角色', video_producer: '视频', editor: '剪辑',
    };
    return map[s] || s;
}

function safeParse(str) {
    try { return JSON.parse(str); } catch (e) { return null; }
}

// ============ 系统提示词管理 ============
let currentPromptScope = 'project';
let promptsData = [];
const PROMPT_SCOPE_LABEL = { default: '默认', global: '全局', project: '本项目' };

function showPrompts() {
    if (!currentProjectId) {
        currentPromptScope = 'global';
    }
    const canGlobal = currentUserRole === 'admin';
    // 项目按钮
    const projBtn = document.getElementById('scopeProjectBtn');
    const globBtn = document.getElementById('scopeGlobalBtn');
    if (!currentProjectId) {
        projBtn.style.opacity = '0.4';
        projBtn.style.pointerEvents = 'none';
    } else {
        projBtn.style.opacity = '1';
        projBtn.style.pointerEvents = 'auto';
    }
    // 全局按钮（仅管理员可改全局默认）
    if (!canGlobal) {
        globBtn.style.opacity = '0.4';
        globBtn.style.pointerEvents = 'none';
        globBtn.title = '全局默认仅管理员可修改';
        if (currentPromptScope === 'global') currentPromptScope = 'project';
    } else {
        globBtn.style.opacity = '1';
        globBtn.style.pointerEvents = 'auto';
        globBtn.title = '';
    }
    document.getElementById('promptScopeHint').textContent = currentProjectId
        ? '当前作用域针对项目：' + currentProjectId + (canGlobal ? '' : '（全局默认仅管理员可改）')
        : '未选择项目，仅能编辑全局默认提示词（需管理员）';
    document.getElementById('promptsModal').style.display = 'flex';
    setPromptScope(currentPromptScope);
}

function closePrompts() {
    document.getElementById('promptsModal').style.display = 'none';
}

function setPromptScope(scope) {
    currentPromptScope = scope;
    document.querySelectorAll('#promptScopeToggle .seg').forEach(b => {
        b.classList.toggle('active', b.dataset.scope === scope);
    });
    loadPrompts();
}

async function loadPrompts() {
    try {
        const url = currentProjectId
            ? `/api/prompts?project_id=${encodeURIComponent(currentProjectId)}`
            : '/api/prompts';
        const resp = await fetch(url);
        if (!resp.ok) throw new Error((await resp.json()).detail || '加载失败');
        const data = await resp.json();
        promptsData = data.prompts || [];
        renderPrompts();
    } catch (e) {
        showToast('加载提示词失败: ' + e.message);
    }
}

function renderPrompts() {
    const list = document.getElementById('promptsList');
    // 按阶段分组
    const groups = {};
    promptsData.forEach(p => {
        (groups[p.stage_label] = groups[p.stage_label] || []).push(p);
    });
    list.innerHTML = Object.entries(groups).map(([stageLabel, items]) => `
        <div class="prompt-block">
            <div class="prompt-block-title">${escapeHtml(stageLabel)}</div>
            ${items.map(p => {
                const initial = (currentPromptScope === 'project' ? p.project : p.global) !== null
                    ? (currentPromptScope === 'project' ? p.project : p.global)
                    : p.effective;
                const scopeTag = (currentPromptScope === 'project' ? p.project : p.global) !== null
                    ? PROMPT_SCOPE_LABEL[currentPromptScope] : '默认';
                const tagClass = (currentPromptScope === 'project' ? p.project : p.global) !== null
                    ? currentPromptScope : 'default';
                return `
                <div class="prompt-field">
                    <div class="prompt-field-label">${escapeHtml(p.key_label)}
                        <span class="scope-tag ${tagClass}">${scopeTag}</span></div>
                    <textarea class="prompt-textarea" id="prompt-${p.stage}-${p.key}" data-initial="${escapeHtml(initial || '')}">${escapeHtml(initial || '')}</textarea>
                </div>`;
            }).join('')}
        </div>
    `).join('');
}

async function savePrompts() {
    let saved = 0, failed = 0;
    for (const p of promptsData) {
        const ta = document.getElementById(`prompt-${p.stage}-${p.key}`);
        if (!ta) continue;
        const val = ta.value;
        const initial = ta.dataset.initial || '';
        if (val === initial) continue; // 未修改则不写
        try {
            const resp = await fetch('/api/prompts', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    scope: currentPromptScope,
                    project_id: currentProjectId || undefined,
                    stage: p.stage, key: p.key, text: val,
                }),
            });
            if (!resp.ok) throw new Error((await resp.json()).detail || '保存失败');
            saved++;
        } catch (e) {
            failed++;
            showToast('保存失败: ' + e.message);
        }
    }
    if (saved) showToast(`已保存 ${saved} 项提示词`);
    else if (!failed) showToast('没有改动');
    if (!failed) loadPrompts();
}

async function resetPrompts() {
    if (!confirm('确认将当前作用域的提示词重置为代码默认？此操作会清除对应覆盖。')) return;
    try {
        const resp = await fetch('/api/prompts/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                scope: currentPromptScope,
                project_id: currentProjectId || undefined,
            }),
        });
        if (!resp.ok) throw new Error((await resp.json()).detail || '重置失败');
        showToast('已重置为默认');
        loadPrompts();
    } catch (e) {
        showToast('重置失败: ' + e.message);
    }
}

// ============ 角色管理 ============
let charactersData = [];

function showCharacters() {
    if (!currentProjectId) { showToast('请先创建项目'); return; }
    document.getElementById('charactersModal').style.display = 'flex';
    loadCharacters();
}

function closeCharacters() {
    document.getElementById('charactersModal').style.display = 'none';
}

async function loadCharacters() {
    try {
        const resp = await fetch(`/api/projects/${currentProjectId}/characters`);
        if (!resp.ok) throw new Error((await resp.json()).detail || '加载失败');
        const data = await resp.json();
        charactersData = data.characters || [];
        renderCharacters();
    } catch (e) {
        showToast('加载角色失败: ' + e.message);
    }
}

function renderCharacters() {
    const list = document.getElementById('charactersList');
    if (!charactersData.length) {
        list.innerHTML = '<p style="color:#8a90a0;text-align:center;padding:20px">暂无角色，点击「新增角色」添加。</p>';
        return;
    }
    list.innerHTML = charactersData.map((c, i) => {
        const appr = c.appearance || {};
        const apprRows = Object.entries(appr).map(([k, v], ri) => `
            <div class="appearance-row">
                <input class="char-input" placeholder="字段名" value="${escapeHtml(k)}" oninput="updateAppearanceKey(${i}, ${ri}, this.value)">
                <input class="char-input" placeholder="字段值" value="${escapeHtml(v)}" oninput="updateAppearanceVal(${i}, ${ri}, this.value)">
                <button class="btn-del-sm" onclick="removeAppearance(${i}, ${ri})">✕</button>
            </div>
        `).join('');
        return `
        <div class="char-card">
            <div class="char-card-head">
                <span class="char-index">角色 #${i + 1}</span>
                <button class="btn-del-sm" onclick="removeCharacter(${i})">🗑 删除角色</button>
            </div>
            <div class="field">
                <label>姓名 name</label>
                <input class="char-input" value="${escapeHtml(c.name || '')}" oninput="updateCharField(${i}, 'name', this.value)">
            </div>
            <div class="field">
                <label>定位 role</label>
                <select class="char-input" onchange="updateCharField(${i}, 'role', this.value)">
                    ${['主角','配角','反派'].map(r => `<option value="${r}" ${c.role === r ? 'selected' : ''}>${r}</option>`).join('')}
                </select>
            </div>
            <div class="field">
                <label>性格 personality</label>
                <textarea class="char-input" rows="2" oninput="updateCharField(${i}, 'personality', this.value)">${escapeHtml(c.personality || '')}</textarea>
            </div>
            <div class="char-appearance-title">外貌 appearance（字段自由，可增删）</div>
            ${apprRows}
            <button class="btn-add-sm" onclick="addAppearance(${i})">＋ 添加外貌字段</button>
            <div class="field" style="margin-top:10px">
                <label>一致性 seed_prompt（影响后续角色一致性）</label>
                <textarea class="char-input" rows="2" oninput="updateCharField(${i}, 'seed_prompt', this.value)">${escapeHtml(c.seed_prompt || '')}</textarea>
            </div>
        </div>`;
    }).join('');
}

function addCharacter() {
    charactersData.push({ name: '', role: '主角', personality: '', appearance: {}, seed_prompt: '' });
    renderCharacters();
}

function removeCharacter(i) {
    charactersData.splice(i, 1);
    renderCharacters();
}

function updateCharField(i, field, val) {
    charactersData[i][field] = val;
}

function addAppearance(i) {
    const c = charactersData[i];
    c.appearance = c.appearance || {};
    // 用一个唯一键避免覆盖
    let key = '新字段';
    let n = 1;
    while (key in c.appearance) { key = '新字段' + (++n); }
    c.appearance[key] = '';
    renderCharacters();
}

function updateAppearanceKey(i, ri, val) {
    const c = charactersData[i];
    const keys = Object.keys(c.appearance || {});
    const oldKey = keys[ri];
    if (val === oldKey) return;
    const entries = Object.entries(c.appearance);
    const newEntries = {};
    entries.forEach(([k, v], idx) => {
        if (idx === ri) newEntries[val] = v;
        else newEntries[k] = v;
    });
    c.appearance = newEntries;
}

function updateAppearanceVal(i, ri, val) {
    const c = charactersData[i];
    const keys = Object.keys(c.appearance || {});
    const k = keys[ri];
    c.appearance[k] = val;
}

function removeAppearance(i, ri) {
    const c = charactersData[i];
    const keys = Object.keys(c.appearance || {});
    const newObj = {};
    keys.forEach((k, idx) => { if (idx !== ri) newObj[k] = c.appearance[k]; });
    c.appearance = newObj;
    renderCharacters();
}

async function saveCharacters() {
    try {
        const resp = await fetch(`/api/projects/${currentProjectId}/characters`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ characters: charactersData }),
        });
        if (!resp.ok) throw new Error((await resp.json()).detail || '保存失败');
        const data = await resp.json();
        charactersData = data.characters || [];
        renderCharacters();
        showToast(`已保存 ${data.count} 个角色`);
    } catch (e) {
        showToast('保存角色失败: ' + e.message);
    }
}


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

// ============ 初始化 ============
document.addEventListener('DOMContentLoaded', async () => {
    await loadProviders();
    updateProviderHint();
});

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

// Templates 功能模块
// 加载到 index.html 中的 #templates-content

let currentLogAgentId = null;

async function loadTemplates() {
    const el = document.getElementById('templates-content');
    el.innerHTML = '<div class="empty-state" style="padding:40px 20px;">加载中...</div>';
    
    try {
        templatesData = await fetch(`${API_BASE}/api/agents/templates`).then(r => r.json());
        agentsData = await fetch(`${API_BASE}/api/agents/instances`).then(r => r.json());
        
        if (templatesData.length === 0) {
            el.innerHTML = `
<div class="section">
    <div class="section-header">
        <h2>📋 模板实例</h2>
        <button class="btn" onclick="showCreateTemplate()">+ 新建模板</button>
    </div>
    <div class="empty-state" style="padding:40px 20px;">暂无模板，点击上方按钮创建</div>
</div>`;
            return;
        }
        
        el.innerHTML = `
<div class="section">
    <div class="section-header">
        <h2>📋 模板实例</h2>
        <button class="btn" onclick="showCreateTemplate()">+ 新建模板</button>
    </div>`;
        
        el.innerHTML += templatesData.map(t => {
            const agent = agentsData.find(a => a.template_id === t.id);
            return `<div class="template-instance">
    <div class="template-header">
        <div>
            <div class="template-title">${t.name}</div>
            <div class="template-meta">ID: ${t.id.slice(0,8)} | 镜像: ${t.image}${t.description ? ' | 描述: ' + t.description : ''}</div>
        </div>
        <div class="actions">
            <button class="action-btn" onclick="editTemplate('${t.id}')">编辑</button>
            <button class="action-btn danger" onclick="deleteTemplate('${t.id}')">删除</button>
        </div>
    </div>
    ${agent ? `<div class="template-info">
        <div class="info-item"><div class="info-label">状态</div><div class="info-value"><span class="status ${getStatusClass(agent.status)}">${getStatusText(agent.status)}</span></div></div>
        <div class="info-item"><div class="info-label">端口</div><div class="info-value port-num">${agent.host_port || '-'}</div></div>
        <div class="info-item"><div class="info-label">容器ID</div><div class="info-value container-id" style="font-family:monospace;font-size:11px;" title="${agent.container_id || ''}">${agent.container_id ? agent.container_id : '-'}</div></div>
    </div>
    ${agent.status === 'error' && agent.config && agent.config.error ? `<div style="background:rgba(218,54,51,0.1);border-left:3px solid #da3633;padding:10px 15px;margin:10px 0;border-radius:4px;color:#f85149;font-size:12px;">❌ ${agent.config.error}</div>` : ''}
    <div class="actions" style="justify-content:center">
        ${agent.status === 'running' && agent.host_port ? `<button class="action-btn primary" onclick="openUI('${agent.host_port}')">🌐 打开 UI</button>` : ''}
        ${agent.status === 'running' ? `<button class="action-btn warning" onclick="showConfig('${agent.id}')">⚙️ 配置</button>` : ''}
        ${agent.status === 'running' ? `<button class="action-btn" onclick="stopAgent('${agent.id}')">⏹️停</止</button>` : (agent.status === 'stopped' || agent.status === 'error') ? `<button class="action-btn success" onclick="startAgent('${agent.id}')">▶️启动</button>` : ``}
        <div class="log-tabs" style="display:flex;gap:5px;margin-bottom:10px;">
        ${agent.status !== 'creating' && agent.container_id ? `${agent.status === 'creating' ? '' : `<button class="action-btn" onclick="viewLogs('${agent.id}', 'combined')">📋 合并日志</button><button class="action-btn" onclick="viewLogs('${agent.id}', 'creation')">🔨 创建日志</button><button class="action-btn" onclick="viewLogs('${agent.id}', 'container')">📦 容器日志</button><button class="action-btn" onclick="viewLogs('${agent.id}', 'config')">⚙️ 配置日志</button>`}` : ''}
        </div>
    </div>` : '<div class="empty-state" style="padding:20px">该模板尚未创建实例</div>'}
</div>`;
        }).join('');
        
        el.innerHTML += '</div>';
        
        // 如果有正在创建的实例，继续轮询
        const creatingAgents = agentsData.filter(a => a.status === 'creating');
        if (creatingAgents.length > 0) {
            console.log(`检测到 ${creatingAgents.length} 个创建中的实例，3秒后继续检查...`);
            setTimeout(loadTemplates, 3000);
        } else {
            console.log('所有实例创建完成');
        }
    } catch (e) {
        el.innerHTML = `<div class="empty-state" style="padding:40px 20px;">加载失败: ${e.message}</div>`;
    }
}

async function startAgent(id, btn) {
    if (btn) btn.disabled = true;
    await fetch(`${API_BASE}/api/agents/instances/${id}/start`, {method:'POST'});
    loadTemplates();
    loadProjects();
}

async function stopAgent(id, btn) {
    if (btn) btn.disabled = true;
    await fetch(`${API_BASE}/api/agents/instances/${id}/stop`, {method:'POST'});
    loadTemplates();
    loadProjects();
}

let currentLogType = 'combined'; // 默认日志类型

async function viewLogs(id, logType = 'combined') {
    currentLogAgentId = id;
    currentLogType = logType;
    document.getElementById('logs-modal').classList.add('active');
    
    // 根据日志类型加载相应内容
    if (logType === 'combined') {
        await loadCombinedLogs();
    } else if (logType === 'creation') {
        await loadCreationLogs();
    } else if (logType === 'container') {
        await loadContainerLogs();
    } else if (logType === 'config') {
        await loadConfigLogs();
    }
}

async function loadCombinedLogs() {
    if (!currentLogAgentId) return;
    
    document.getElementById('logs-content').textContent = '加载中...';
    
    try {
        const [logsRes, creationRes, configRes] = await Promise.all([
            fetch(`${API_BASE}/api/agents/instances/${currentLogAgentId}/logs?tail=50`).then(r => r.json()),
            fetch(`${API_BASE}/api/agents/instances/${currentLogAgentId}/creation-logs`).then(r => r.json()),
            fetch(`${API_BASE}/api/agents/instances/${currentLogAgentId}/config-logs`).then(r => r.json())
        ]);
        
        const content = [];
        
        if (logsRes.logs) {
            content.push('--- 📄 容器日志（最近50行） ---');
            content.push(logsRes.logs);
        }
        
        if (creationRes.logs && creationRes.logs !== '暂无创建日志') {
            content.push('\n--- 🔨 创建日志 ---');
            content.push(creationRes.logs);
        }
        
        if (configRes.logs && configRes.logs.length > 0) {
            content.push('\n--- ⚙️ 配置变更日志 ---');
            configRes.logs.forEach(log => {
                const time = new Date(log.created_at).toLocaleString('zh-CN');
                content.push(`[${time}] ${log.description}`);
                if (log.old_value) content.push(`  旧配置: ${JSON.stringify(log.old_value, null, 2)}`);
                if (log.new_value) content.push(`  新配置: ${JSON.stringify(log.new_value, null, 2)}`);
            });
        }
        
        document.getElementById('logs-content').textContent = content.join('\n') || '暂无日志';
    } catch(e) {
        document.getElementById('logs-content').textContent = '获取日志失败: ' + e.message;
    }
}

async function loadCreationLogs() {
    if (!currentLogAgentId) return;
    
    document.getElementById('logs-content').textContent = '加载中...';
    
    try {
        const d = await fetch(`${API_BASE}/api/agents/instances/${currentLogAgentId}/creation-logs`).then(r => r.json());
        document.getElementById('logs-content').textContent = d.logs || '暂无创建日志';
    } catch(e) {
        document.getElementById('logs-content').textContent = '获取日志失败: ' + e.message;
    }
}

async function loadConfigLogs() {
    if (!currentLogAgentId) return;
    
    document.getElementById('logs-content').textContent = '加载中...';
    
    try {
        const d = await fetch(`${API_BASE}/api/agents/instances/${currentLogAgentId}/config-logs`).then(r => r.json());
        if (d.logs && d.logs.length > 0) {
            const content = d.logs.map(log => {
                const time = new Date(log.created_at).toLocaleString('zh-CN');
                let text = `[${time}] ${log.description}`;
                if (log.old_value) text += `\n  旧配置: ${JSON.stringify(log.old_value, null, 2)}`;
                if (log.new_value) text += `\n  新配置: ${JSON.stringify(log.new_value, null, 2)}`;
                return text;
            });
            document.getElementById('logs-content').textContent = content.join('\n\n' + '='.repeat(50) + '\n\n');
        } else {
            document.getElementById('logs-content').textContent = '暂无配置变更日志';
        }
    } catch(e) {
        document.getElementById('logs-content').textContent = '获取日志失败: ' + e.message;
    }
}

async function loadContainerLogs() {
    if (!currentLogAgentId) return;
    document.getElementById('logs-content').textContent = '加载中...';
    try {
        const d = await fetch(`${API_BASE}/api/agents/instances/${currentLogAgentId}/logs?tail=100`).then(r => r.json());
        document.getElementById('logs-content').textContent = d.logs || '暂无容器日志';
    } catch(e) {
        document.getElementById('logs-content').textContent = '获取容器日志失败: ' + e.message;
    }
}

async function showConfig(id) {
    currentAgentId = id;
    document.getElementById('config-modal').classList.add('active');
    const a = await fetch(`${API_BASE}/api/agents/instances/${id}`).then(r => r.json());
    document.getElementById('cfg-agent-id').value = id;
    if (a.config) {
        document.getElementById('cfg-provider').value = a.config.provider || 'openai';
        document.getElementById('cfg-token').value = a.config.gateway_token || '';
    }
}

async function saveConfig() {
    const id = document.getElementById('cfg-agent-id').value;
    await fetch(`${API_BASE}/api/agents/instances/${id}/config`, {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({provider:document.getElementById('cfg-provider').value,ai_key:document.getElementById('cfg-apikey').value,gateway_token:document.getElementById('cfg-token').value})
    });
    closeModal('config-modal');
    alert('配置已保存并应用');
}

async function editTemplate(id) {
    try {
        const t = await fetch(`${API_BASE}/api/agents/templates/${id}`).then(r => r.json());
        const agents = await fetch(`${API_BASE}/api/agents/instances?template_id=${id}`).then(r => r.json());
        const agent = agents.find(a => a.template_id === id);
        
        document.getElementById('edit-tpl-id').value = id;
        document.getElementById('edit-agent-id').value = agent ? agent.id : '';
        document.getElementById('edit-tpl-name').value = t.name || '';
        document.getElementById('edit-tpl-desc').value = t.description || '';
        document.getElementById('edit-container-id').value = agent && agent.container_id ? agent.container_id : '';
        document.getElementById('container-check-result').textContent = '';
        document.getElementById('container-check-result').style.color = '';
        document.getElementById('edit-template-modal').classList.add('active');
    } catch(e) {
        alert('加载模板失败: ' + e.message);
    }
}

async function checkContainerExists() {
    const containerId = document.getElementById('edit-container-id').value.trim();
    const resultEl = document.getElementById('container-check-result');
    
    if (!containerId) {
        resultEl.textContent = '请输入容器ID';
        resultEl.style.color = '#f85149';
        return;
    }
    
    resultEl.textContent = '检查中...';
    resultEl.style.color = '#8b949e';
    
    try {
        // Docker 支持 12 位或 64 位 ID
        const containerInfo = await fetch(`${API_BASE}/api/containers/${containerId}`).then(r => r.json());
        
        if (containerInfo.exists) {
            resultEl.textContent = `✅ 容器存在: ${containerInfo.name} (${containerInfo.status})`;
            resultEl.style.color = '#3fb950';
            document.getElementById('edit-container-id').value = containerInfo.id; // 更新为完整 64 位 ID
        } else {
            resultEl.textContent = '❌ 容器不存在，请检查ID是否正确';
            resultEl.style.color = '#f85149';
        }
    } catch(e) {
        resultEl.textContent = '检查失败: ' + e.message;
        resultEl.style.color = '#f85149';
    }
}

async function submitEditTemplate() {
    const tplId = document.getElementById('edit-tpl-id').value;
    const agentId = document.getElementById('edit-agent-id').value;
    const name = document.getElementById('edit-tpl-name').value.trim();
    const description = document.getElementById('edit-tpl-desc').value.trim();
    const containerId = document.getElementById('edit-container-id').value.trim();
    
    if (!name) { alert('请输入模板名称'); return; }
    
    try {
        let containerUpdateData = null;
        if (agentId && containerId) {
            const containerInfo = await fetch(`${API_BASE}/api/containers/${containerId}`).then(r => r.json());
            
            if (!containerInfo.exists) {
                alert('❌ 保存失败：指定的容器ID不存在，请检查后再试');
                return;
            }
            
            let hostPort = null;
            if (containerInfo.ports) {
                for (const [key, bindings] of Object.entries(containerInfo.ports)) {
                    if (Array.isArray(bindings) && bindings.length > 0) {
                        hostPort = parseInt(bindings[0].HostPort);
                        break;
                    }
                }
            }
            
            containerUpdateData = {
                container_id: containerInfo.id,
                container_name: containerInfo.name,
                host_port: hostPort
            };
        }
        
        await fetch(`${API_BASE}/api/agents/templates/${tplId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });
        
        if (agentId && containerUpdateData) {
            await fetch(`${API_BASE}/api/agents/instances/${agentId}/update-container`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(containerUpdateData)
            });
        }
        
        closeModal('edit-template-modal');
        loadTemplates();
        alert('✅ 保存成功');
    } catch(e) {
        alert('❌ 保存失败: ' + e.message);
    }
}

function deleteTemplate(id) {
    if (!confirm('确定要删除此模板吗？关联的实例和容器也会被删除。')) return;
    
    fetch(`${API_BASE}/api/agents/templates/${id}`, {method:'DELETE'})
        .then(r => r.json())
        .then(data => {
            alert(data.message || '✅ 删除成功');
            loadTemplates();
        })
        .catch(e => alert('❌ 删除失败: ' + e.message));
}

// ========== 新建模板 ==========
async function showCreateTemplate() {
    console.log('打开新建模板弹窗');
    await refreshUsedPorts();
    document.getElementById('tpl-name').value = '';
    document.getElementById('tpl-desc').value = '';
    document.getElementById('port-error').style.display = 'none';
    const autoPort = findAvailablePort();
    document.getElementById('tpl-host-port').value = autoPort || '';
    
    // 加载本地镜像
    await refreshLocalImages();
    
    document.getElementById('template-modal').classList.add('active');
    console.log('弹窗已打开');
}

function autoAssignPort() {
    const port = findAvailablePort();
    if (port) {
        document.getElementById('tpl-host-port').value = port;
        document.getElementById('port-error').style.display = 'none';
    } else {
        document.getElementById('port-error').textContent = '无法找到可用端口';
        document.getElementById('port-error').style.display = 'block';
    }
}

async function submitCreateTemplate() {
    const name = document.getElementById('tpl-name').value.trim();
    const description = document.getElementById('tpl-desc').value.trim();
    const imageSelect = document.getElementById('tpl-image');
    const image = imageSelect.value;
    const hostPort = document.getElementById('tpl-host-port').value.trim();
    
    console.log('提交创建模板:', { name, image, hostPort });
    
    if (!name) { alert('请输入模板名称'); return; }
    if (!image) { alert('请选择 Docker 镜像'); return; }
    
    // 检查端口
    if (hostPort) {
        const check = checkPortAvailable(hostPort);
        if (!check.valid) {
            document.getElementById('port-error').textContent = check.msg;
            document.getElementById('port-error').style.display = 'block';
            return;
        }
    }
    
    const payload = { 
        name, 
        description, 
        image,
        host_port: hostPort ? parseInt(hostPort) : null
    };
    
    try {
        const resp = await fetch(`${API_BASE}/api/agents/templates`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (!resp.ok) {
            const err = await resp.json();
            alert('创建失败: ' + (err.detail || err.message || '未知错误'));
            return;
        }
        
        closeModal('template-modal');
        loadTemplates();
        alert('✅ 模板创建成功');
    } catch(e) { 
        alert('创建失败: ' + e.message); 
    }
}

async function refreshLocalImages() {
    const select = document.getElementById('tpl-image');
    if (!select) {
        console.error('找不到 tpl-image 元素');
        return;
    }
    select.innerHTML = '<option value="">加载中...</option>';
    
    try {
        console.log('正在获取本地镜像...');
        const images = await fetch(`${API_BASE}/api/docker/images`).then(r => r.json());
        console.log('获取到镜像:', images);
        if (images.length === 0) {
            select.innerHTML = '<option value="">暂无本地镜像</option>';
        } else {
            select.innerHTML = images.map(img => 
                `<option value="${img.tag}">${img.tag} (${(img.size / 1024 / 1024).toFixed(1)} MB)</option>`
            ).join('');
        }
    } catch(e) {
        console.error('获取镜像失败:', e);
        select.innerHTML = '<option value="">加载失败</option>';
    }
}

async function refreshUsedPorts() {
    try {
        const agents = await fetch(`${API_BASE}/api/agents/instances`).then(r => r.json());
        usedPorts = agents.map(a => a.host_port).filter(p => p);
        console.log('已用端口:', usedPorts);
        return usedPorts;
    } catch(e) {
        console.error('获取端口失败:', e);
        return [];
    }
}

function findAvailablePort() {
    // 从 30001 开始查找可用端口（端口池范围）
    for (let port = 30001; port <= 30500; port++) {
        if (!usedPorts.includes(port)) {
            return port;
        }
    }
    return null;
}

let usedPorts = [];
function checkPortAvailable(port) {
    if (usedPorts.includes(parseInt(port))) {
        return { valid: false, msg: '端口已被占用' };
    }
    return { valid: true };
}

// 添加缺失的函数
function switchLogTab(tab) { 
    if (tab === 'combined') loadCombinedLogs(); 
    else if (tab === 'creation') loadCreationLogs(); 
    else if (tab === 'container') loadContainerLogs();
    else if (tab === 'config') loadConfigLogs(); 
}

async function loadProjects() { 
    const p = await fetch(API_BASE + '/api/projects').then(r => r.json()); 
    console.log('projects loaded:', p); 
}

document.addEventListener('DOMContentLoaded', function() { 
    loadTemplates(); 
    setInterval(loadTemplates, 30000); 
});

// Projects 功能模块
// 加载到 index.html 中的 #projects-content

async function loadProjects() {
    const el = document.getElementById('projects-content');
    el.innerHTML = '<div class="empty-state" style="padding:40px 20px;">加载中...</div>';
    
    try {
        const p = await fetch(`${API_BASE}/api/projects`).then(r => r.json());
        
        if (p.length === 0) {
            el.innerHTML = `
<div class="section">
    <div class="section-header">
        <h2>📁 项目列表</h2>
        <button class="btn" onclick="showCreateProject()">+ 新建项目</button>
    </div>
    <div class="empty-state" style="padding:40px 20px;">暂无项目，点击上方按钮创建</div>
</div>`;
            return;
        }
        
        agentsData = await fetch(`${API_BASE}/api/agents/instances`).then(r => r.json());
        
        for (let x of p) {
            x.projectAgents = agentsData.filter(a => a.project_id === x.id);
        }
        
        el.innerHTML = `
<div class="section">
    <div class="section-header">
        <h2>📁 项目列表</h2>
        <button class="btn" onclick="showCreateProject()">+ 新建项目</button>
    </div>`;
        
        el.innerHTML += p.map(x => `
<div class="project-card">
    <div class="project-header" onclick="toggle('proj-${x.id}')">
        <div>
            <div class="project-name">${x.name}${x.projectAgents.length > 0 ? `<span class="badge">${x.projectAgents.length} 实例</span>` : ''}</div>
            <div class="template-meta">ID: ${x.id.slice(0,8)} | ${x.description || '无描述'}</div>
        </div>
        <div class="actions" onclick="event.stopPropagation()">
            <button class="action-btn" onclick="cloneTemplateToProject('${x.id}')">📋 克隆模板</button>
            <button class="action-btn" onclick="archiveProject('${x.id}')">归档</button>
            <button class="action-btn danger" onclick="deleteProject('${x.id}')">删除</button>
        </div>
    </div>
    <div id="proj-${x.id}" class="project-instances hidden">
        ${x.projectAgents.length > 0 ? `
        <table class="instance-table">
            <thead><tr><th>实例名称</th><th>容器ID</th><th>端口</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
                ${x.projectAgents.map(a => `
                <tr>
                    <td>${a.name}${a.id === x.main_agent_id ? '<span class="badge">主</span>' : ''}</td>
                    <td class="container-id" style="font-family:monospace;font-size:11px;" title="${a.container_id || ''}">${a.container_id || '-'}</td>
                    <td class="port-num">${a.host_port || '-'}</td>
                    <td><span class="status ${getStatusClass(a.status)}">${getStatusText(a.status)}</span></td>
                    <td class="actions">
                        ${a.host_port ? `<button class="action-btn primary" onclick="openUI('${a.host_port}')">UI</button>` : ''}
                        <button class="action-btn warning" onclick="showConfig('${a.id}')">配置</button>
                        ${a.status === 'running' ? `<button class="action-btn" onclick="stopAgent('${a.id}')">停止</button>` : `<button class="action-btn success" onclick="startAgent('${a.id}')">启动</button>`}
                    </td>
                </tr>
                `).join('')}
            </tbody>
        </table>` : ''}
    </div>
</div>
        `).join('');
        
        el.innerHTML += '</div>';
    } catch(e) {
        el.innerHTML = `<div class="empty-state" style="padding:40px 20px;">加载失败: ${e.message}</div>`;
    }
}

function archiveProject(id) {
    if (!confirm('确定要归档此项目吗？')) return;
    fetch(`${API_BASE}/api/projects/${id}/archive`, {method:'POST'})
        .then(r => r.json())
        .then(data => {
            alert(data.message || '✅ 归档成功');
            loadProjects();
        })
        .catch(e => alert('❌ 归档失败: ' + e.message));
}

function deleteProject(id) {
    if (!confirm('确定要删除此项目吗？所有关联的实例和容器也会被删除。')) return;
    
    fetch(`${API_BASE}/api/projects/${id}`, {method:'DELETE', headers:{'Content-Type':'application/json'}, body:JSON.stringify({force:true})})
        .then(r => r.json())
        .then(data => {
            alert(data.message || '✅ 删除成功');
            loadProjects();
        })
        .catch(e => alert('❌ 删除失败: ' + e.message));
}

function cloneTemplateToProject(projectId) {
    fetch(`${API_BASE}/api/agents/templates`)
        .then(r => r.json())
        .then(templates => {
            if (templates.length === 0) {
                alert('没有可用的模板');
                return;
            }
            
            const options = templates.map(t => `${t.id.slice(0,8)} - ${t.name}`).join('\n');
            const tid = prompt('输入要克隆的模板ID:\n' + options);
            
            if (!tid) return;
            
            fetch(`${API_BASE}/api/projects/${projectId}/clone-template`, {
                method:'POST',
                headers:{'Content-Type':'application/json'},
                body:JSON.stringify({template_id:tid})
            })
            .then(r => r.json())
            .then(data => {
                alert(data.message || '✅ 克隆成功');
                loadProjects();
            })
            .catch(e => alert('❌ 克隆失败: ' + e.message));
        })
        .catch(e => alert('❌ 加载模板失败: ' + e.message));
}

function showCreateProject() {
    document.getElementById('proj-name').value = '';
    document.getElementById('proj-desc').value = '';
    document.getElementById('project-modal').classList.add('active');
}

async function submitCreateProject() {
    const name = document.getElementById('proj-name').value.trim();
    const description = document.getElementById('proj-desc').value.trim();
    
    if (!name) { alert('请输入项目名称'); return; }
    
    try {
        await fetch(`${API_BASE}/api/projects`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });
        closeModal('project-modal');
        loadProjects();
        alert('✅ 项目创建成功');
    } catch(e) {
        alert('❌ 创建失败: ' + e.message);
    }
}

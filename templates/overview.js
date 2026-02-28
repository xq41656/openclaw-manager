// Overview 功能模块
// 加载到 index.html 中的 #overview-content

async function loadContainers() {
    const el = document.getElementById('overview-content');
    el.innerHTML = '<div class="empty-state" style="padding:40px 20px;">加载中...</div>';
    
    try {
        const c = await fetch(`${API_BASE}/api/containers/all`).then(r => r.json());
        el.innerHTML = c.length === 0 
            ? '<div class="empty-state" style="padding:40px 20px;">暂无容器</div>'
            : `
<div class="section">
    <div class="section-header"><h2>📦 Docker 容器</h2><button class="btn" onclick="loadContainers()">🔄 刷新</button></div>
    <table><thead><tr><th>ID</th><th>名称</th><th>镜像</th><th>状态</th><th>端口</th></tr></thead>
    <tbody id="containers-tbody">
        ${c.map(x => `
        <tr>
            <td class="container-id" style="font-family:monospace;font-size:12px;" title="${x.id}">${x.id}</td>
            <td>${x.name}</td>
            <td class="image-tag">${x.image}</td>
            <td><span class="status ${getStatusClass(x.state)}"><span class="status-dot"></span>${getStatusText(x.state)}</span></td>
            <td>${formatPorts(x.ports)}</td>
        </tr>
        `).join('')}
    </tbody></table>
</div>`;
    } catch(e) {
        el.innerHTML = `<div class="empty-state" style="padding:40px 20px;">加载失败: ${e.message}</div>`;
    }
}

function formatPorts(p) {
    if (!p || Object.keys(p).length === 0) return '-';
    return Object.entries(p).map(([k,v]) => Array.isArray(v) 
        ? v.map(h => `${h.HostPort}:${k.split('/')[0]}`).join(',')
        : `${k}>${v}`
    ).join(', ');
}

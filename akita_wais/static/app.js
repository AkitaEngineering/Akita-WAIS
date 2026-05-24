document.addEventListener('DOMContentLoaded', () => {
    
    // UI Elements
    const btnRefresh = document.getElementById('btn-refresh-servers');
    const serverList = document.getElementById('server-list');
    const fileList = document.getElementById('file-list');
    const serverTitle = document.getElementById('current-server-title');
    const searchInput = document.getElementById('search-input');
    const btnSearch = document.getElementById('btn-search');
    const statusText = document.getElementById('connection-status');
    const statusDot = document.getElementById('status-dot');
    
    let currentServerHash = null;

    // Show Toast Notification
    function showToast(message) {
        const toast = document.getElementById('toast');
        document.getElementById('toast-message').innerText = message;
        toast.classList.remove('hidden');
        setTimeout(() => {
            toast.classList.add('hidden');
        }, 3000);
    }

    // Fetch and display servers
    async function refreshServers() {
        serverList.innerHTML = '<div class="empty-state">Refreshing nodes...</div>';
        try {
            const res = await fetch('/api/servers');
            const data = await res.json();
            
            if (data.servers && data.servers.length > 0) {
                serverList.innerHTML = '';
                data.servers.forEach(server => {
                    const div = document.createElement('div');
                    div.className = `server-item ${server.hash === currentServerHash ? 'active' : ''}`;
                    div.innerHTML = `
                        <div class="server-name">${server.name}</div>
                        <div class="server-hash">${server.hash}</div>
                    `;
                    div.onclick = () => connectToServer(server);
                    serverList.appendChild(div);
                });
            } else {
                serverList.innerHTML = '<div class="empty-state">No nodes found on network.</div>';
            }
        } catch (e) {
            serverList.innerHTML = `<div class="empty-state">Error: ${e.message}</div>`;
        }
    }

    // Connect to a server
    async function connectToServer(server) {
        showToast(`Connecting to ${server.name}...`);
        
        // Update UI state
        document.querySelectorAll('.server-item').forEach(el => el.classList.remove('active'));
        
        try {
            const res = await fetch('/api/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hash: server.hash })
            });
            const data = await res.json();
            
            if (res.ok) {
                currentServerHash = server.hash;
                serverTitle.innerText = server.name;
                statusText.innerText = "Connected";
                statusDot.className = "dot green";
                searchInput.disabled = false;
                btnSearch.disabled = false;
                showToast("Connection established.");
                refreshServers(); // Re-render to show active state
                fetchFiles();
            } else {
                showToast(data.error || "Connection failed");
            }
        } catch (e) {
            showToast("Network error connecting to server.");
        }
    }

    // Fetch files from connected server
    async function fetchFiles() {
        if (!currentServerHash) return;
        
        fileList.innerHTML = '<div class="empty-state">Loading files...</div>';
        try {
            const res = await fetch('/api/files');
            const data = await res.json();
            
            if (data.status === 'ok') {
                renderFiles(data.files);
            } else {
                fileList.innerHTML = `<div class="empty-state">Error: ${data.message}</div>`;
            }
        } catch (e) {
            fileList.innerHTML = `<div class="empty-state">Network error retrieving files.</div>`;
        }
    }

    // Render file grid
    function renderFiles(files) {
        if (!files || files.length === 0) {
            fileList.innerHTML = '<div class="empty-state">No files found on this server.</div>';
            return;
        }

        fileList.innerHTML = '';
        files.forEach(filename => {
            const ext = filename.split('.').pop().toUpperCase();
            
            const card = document.createElement('div');
            card.className = 'file-card';
            card.innerHTML = `
                <div class="file-icon">📄</div>
                <div class="file-name">${filename}</div>
                <button class="btn-download" data-file="${filename}">Download</button>
            `;
            
            card.querySelector('.btn-download').onclick = () => downloadFile(filename);
            fileList.appendChild(card);
        });
    }

    // Search files
    async function searchFiles() {
        const query = searchInput.value.trim();
        if (!query) return fetchFiles();
        
        fileList.innerHTML = '<div class="empty-state">Searching...</div>';
        try {
            const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
            const data = await res.json();
            
            if (data.status === 'ok') {
                renderFiles(data.results);
            } else {
                fileList.innerHTML = `<div class="empty-state">Error: ${data.message}</div>`;
            }
        } catch (e) {
            fileList.innerHTML = `<div class="empty-state">Search failed.</div>`;
        }
    }

    // Download file logic
    async function downloadFile(filename) {
        showToast(`Requesting ${filename}...`);
        try {
            const res = await fetch('/api/download', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename })
            });
            const data = await res.json();
            
            if (data.status === 'ok') {
                showToast(`Download complete: ${filename}`);
            } else {
                showToast(`Download failed: ${data.message}`);
            }
        } catch (e) {
            showToast("Network error during download.");
        }
    }

    // Event Listeners
    btnRefresh.addEventListener('click', refreshServers);
    btnSearch.addEventListener('click', searchFiles);
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') searchFiles();
    });

    // Auto-refresh servers periodically
    refreshServers();
    setInterval(refreshServers, 10000);
});

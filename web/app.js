const form = document.getElementById("download-form");
const urlInput = document.getElementById("url");
const statusEl = document.getElementById("status");
const filesEl = document.getElementById("files");
const refreshBtn = document.getElementById("refresh-files");

let pollTimer = null;

function setStatus(data) {
    statusEl.textContent = JSON.stringify(data, null, 2);
}

async function loadFiles() {
    const response = await fetch("/api/files");
    const data = await response.json();
    filesEl.innerHTML = "";

    if (!data.files || data.files.length === 0) {
        const li = document.createElement("li");
        li.textContent = "No files yet";
        filesEl.appendChild(li);
        return;
    }

    data.files.forEach((file) => {
        const li = document.createElement("li");
        const mb = (file.size_bytes / (1024 * 1024)).toFixed(2);
        li.textContent = `${file.name} (${mb} MB)`;
        filesEl.appendChild(li);
    });
}

async function pollStatus(taskId) {
    if (pollTimer) {
        clearInterval(pollTimer);
    }

    pollTimer = setInterval(async () => {
        const response = await fetch(`/api/status/${taskId}`);
        const data = await response.json();
        setStatus(data);

        if (data.status === "completed" || data.status === "failed") {
            clearInterval(pollTimer);
            pollTimer = null;
            await loadFiles();
        }
    }, 1500);
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const url = urlInput.value.trim();
    if (!url) {
        setStatus({ error: "Enter a URL" });
        return;
    }

    setStatus({ status: "Sending request..." });

    const response = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
    });

    const data = await response.json();
    setStatus(data);

    if (response.ok && data.task_id) {
        await pollStatus(data.task_id);
    }
});

refreshBtn.addEventListener("click", () => {
    loadFiles().catch((error) => setStatus({ error: String(error) }));
});

loadFiles().catch((error) => setStatus({ error: String(error) }));

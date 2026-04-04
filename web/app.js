const form = document.getElementById("download-form");
const urlInput = document.getElementById("url");
const loadFormatsBtn = document.getElementById("load-formats");
const qualitySelect = document.getElementById("quality");
const formatsStatusEl = document.getElementById("formats-status");
const downloadBtn = document.getElementById("download-btn");
const statusEl = document.getElementById("status");
const filesEl = document.getElementById("files");
const refreshBtn = document.getElementById("refresh-files");

let pollTimer = null;
let loadedFormatsUrl = "";

function setStatus(data) {
    statusEl.textContent = JSON.stringify(data, null, 2);
}

function setFormatsStatus(message, isError = false) {
    formatsStatusEl.textContent = message;
    formatsStatusEl.classList.toggle("error", isError);
}

function formatBytes(bytes) {
    if (!bytes || bytes <= 0) {
        return "~ size unknown";
    }
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatLabel(format) {
    const parts = [];
    if (format.quality) {
        parts.push(format.quality);
    } else if (format.resolution) {
        parts.push(format.resolution);
    }
    if (format.ext) {
        parts.push(String(format.ext).toUpperCase());
    }
    if (format.fps) {
        parts.push(`${format.fps} fps`);
    }
    if (format.filesize) {
        parts.push(formatBytes(format.filesize));
    }
    if (format.note) {
        parts.push(`(${format.note})`);
    }
    return parts.join(" • ");
}

function resetFormats() {
    qualitySelect.innerHTML = "<option value=\"\">Load qualities first</option>";
    qualitySelect.disabled = true;
    downloadBtn.disabled = true;
    loadedFormatsUrl = "";
}

async function loadFormats() {
    const url = urlInput.value.trim();
    if (!url) {
        setFormatsStatus("Enter URL first", true);
        resetFormats();
        return;
    }

    setFormatsStatus("Loading available qualities...");
    loadFormatsBtn.disabled = true;
    qualitySelect.disabled = true;
    downloadBtn.disabled = true;

    try {
        const response = await fetch(`/api/formats?url=${encodeURIComponent(url)}`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Failed to load qualities");
        }

        const formats = Array.isArray(data.formats) ? data.formats : [];
        if (formats.length === 0) {
            throw new Error("No quality options found for this URL");
        }

        qualitySelect.innerHTML = "";

        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "Select quality";
        qualitySelect.appendChild(placeholder);

        formats.forEach((format) => {
            const option = document.createElement("option");
            option.value = format.format_id;
            option.textContent = formatLabel(format);
            qualitySelect.appendChild(option);
        });

        qualitySelect.disabled = false;
        qualitySelect.selectedIndex = 1;
        downloadBtn.disabled = false;
        loadedFormatsUrl = url;
        setFormatsStatus(`Loaded ${formats.length} quality options (video + best audio)`);
    } catch (error) {
        resetFormats();
        setFormatsStatus(String(error), true);
        setStatus({ error: String(error) });
    } finally {
        loadFormatsBtn.disabled = false;
    }
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
            downloadBtn.disabled = !qualitySelect.value;
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

    const formatId = qualitySelect.value;
    if (!formatId || loadedFormatsUrl !== url) {
        setStatus({ error: "Load qualities and choose one option before downloading" });
        return;
    }

    setStatus({ status: "Sending request..." });
    downloadBtn.disabled = true;

    const response = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, format_id: formatId }),
    });

    const data = await response.json();
    setStatus(data);

    if (response.ok && data.task_id) {
        await pollStatus(data.task_id);
    } else {
        downloadBtn.disabled = false;
    }
});

loadFormatsBtn.addEventListener("click", () => {
    loadFormats().catch((error) => {
        setFormatsStatus(String(error), true);
        setStatus({ error: String(error) });
    });
});

urlInput.addEventListener("input", () => {
    if (urlInput.value.trim() !== loadedFormatsUrl) {
        resetFormats();
        setFormatsStatus("URL changed. Load qualities again.");
    }
});

qualitySelect.addEventListener("change", () => {
    downloadBtn.disabled = !qualitySelect.value;
});

refreshBtn.addEventListener("click", () => {
    loadFiles().catch((error) => setStatus({ error: String(error) }));
});

loadFiles().catch((error) => setStatus({ error: String(error) }));

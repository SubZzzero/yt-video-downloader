window.createPlaylistModeController = function createPlaylistModeController(options) {
    const checkbox = options.checkbox;
    const qualityGroup = options.qualityGroup;
    const playlistHint = options.playlistHint;
    const audioOnlyCheckbox = options.audioOnlyCheckbox;
    const listeners = new Set();

    function isEnabled() {
        return Boolean(checkbox?.checked);
    }

    function hintMessage() {
        if (!isEnabled()) {
            return "";
        }

        if (audioOnlyCheckbox?.checked) {
            return "Playlist mode will download every entry as MP3 using the selected bitrate.";
        }

        return "Playlist mode will prefer 1080p for each entry and fall back to the best lower quality. It will never download higher than 1080p.";
    }

    function apply() {
        const enabled = isEnabled();
        if (qualityGroup) {
            qualityGroup.hidden = enabled;
        }
        if (playlistHint) {
            playlistHint.hidden = !enabled;
            playlistHint.textContent = hintMessage();
        }

        listeners.forEach((listener) => listener(enabled));
    }

    function subscribe(listener) {
        listeners.add(listener);
        return function unsubscribe() {
            listeners.delete(listener);
        };
    }

    checkbox?.addEventListener("change", apply);
    audioOnlyCheckbox?.addEventListener("change", () => {
        if (isEnabled()) {
            apply();
        }
    });

    return {
        isEnabled,
        apply,
        subscribe,
    };
};

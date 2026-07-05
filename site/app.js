const audio = document.querySelector("#audio");
const dataBase = String(window.HARVARD_RADIO_DATA_BASE || "").replace(/\/+$/, "");
const dataUrl = (path) => {
  if (!dataBase || !path || !path.startsWith("./")) return path;
  return `${dataBase}/${path.slice(2)}`;
};
const splashScreen = document.querySelector("#splash-screen");
const splashStartedAt = Date.now();
let splashDismissed = false;
const playButton = document.querySelector("#play-button");
const progress = document.querySelector("#progress");
const elapsed = document.querySelector("#elapsed");
const duration = document.querySelector("#duration");
const languageButtons = [...document.querySelectorAll("[data-language]")];
let episode;
let archive = [];
let currentEpisodePath = "./episodes/latest.json";
let language = localStorage.getItem("harvard-radio-language") || "zh";
let playbackSpeed = Number(localStorage.getItem("harvard-radio-speed") || "1");
let captionSize = localStorage.getItem("harvard-radio-caption-size") || "standard";
let autoplayNext = localStorage.getItem("harvard-radio-autoplay") === "true";
const transcripts = { zh: [], en: [] };
const scripts = { zh: "", en: "" };
let activeCueIndex = 0;
let captionMotion = 1;
let touchStartY = null;
let lastLatestCheck = 0;
let languageSwitchToken = 0;

const updateMediaSession = () => {
  if (!("mediaSession" in navigator) || !window.MediaMetadata || !episode) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: episode.title[language],
    artist: language === "zh" ? "哈佛公报电台" : "Harvard Gazette Radio",
    album: episode.date,
    artwork: [
      {
        src: new URL("./icon-192.png", window.location.href).href,
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: new URL("./icon-512.png", window.location.href).href,
        sizes: "512x512",
        type: "image/png",
      },
    ],
  });
};

const dismissSplash = () => {
  if (splashDismissed) return;
  splashDismissed = true;
  const minimumDisplay = 900;
  const delay = Math.max(0, minimumDisplay - (Date.now() - splashStartedAt));
  window.setTimeout(() => {
    splashScreen.classList.add("is-leaving");
    document.body.classList.remove("splash-active");
    window.setTimeout(() => splashScreen.remove(), 500);
  }, delay);
};

const formatTime = (seconds) => {
  if (!Number.isFinite(seconds)) return "00:00";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
};

const srtSeconds = (value) => {
  const [hours, minutes, rest] = value.split(":");
  const [seconds, millis] = rest.split(",");
  return Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds) + Number(millis) / 1000;
};

const splitCue = (cue, nextLanguage) => {
  const limit = nextLanguage === "zh" ? 22 : 42;
  const phrases = cue.text.match(/[^，。！？；,.!?;]+[，。！？；,.!?;]?/g) || [cue.text];
  const chunks = phrases.flatMap((phrase) => {
    const trimmed = phrase.trim();
    if (trimmed.length <= limit) return [trimmed];
    const pieces = [];
    for (let index = 0; index < trimmed.length; index += limit) {
      pieces.push(trimmed.slice(index, index + limit));
    }
    return pieces;
  }).filter(Boolean);
  const punctuation = /^[，。！？；：、,.!?;:'"“”‘’…—）)\]】]+$/;
  const normalizedChunks = [];
  chunks.forEach((chunk) => {
    if (punctuation.test(chunk) && normalizedChunks.length) {
      normalizedChunks[normalizedChunks.length - 1] += chunk;
      return;
    }
    const leading = chunk.match(/^([，。！？；：、,.!?;:'"“”‘’…—）)\]】]+)(.+)$/);
    if (leading && normalizedChunks.length) {
      normalizedChunks[normalizedChunks.length - 1] += leading[1];
      normalizedChunks.push(leading[2]);
      return;
    }
    normalizedChunks.push(chunk);
  });
  const parts = [];
  normalizedChunks.forEach((chunk) => {
    const previous = parts[parts.length - 1];
    if (previous && previous.length + chunk.length <= limit) {
      parts[parts.length - 1] = previous + chunk;
    } else {
      parts.push(chunk);
    }
  });
  const totalCharacters = parts.reduce((sum, part) => sum + part.length, 0);
  let cursor = cue.start;
  return parts.map((part, index) => {
    const remaining = cue.end - cue.start;
    const span = index === parts.length - 1
      ? cue.end - cursor
      : remaining * (part.length / totalCharacters);
    const result = { start: cursor, end: cursor + span, text: part };
    cursor += span;
    return result;
  });
};

const parseSrt = (content, nextLanguage) =>
  content
    .trim()
    .split(/\n\s*\n/)
    .map((block) => {
      const lines = block.split("\n");
      const timingIndex = lines.findIndex((line) => line.includes(" --> "));
      if (timingIndex < 0) return null;
      const [start, end] = lines[timingIndex].split(" --> ");
      return {
        start: srtSeconds(start.trim()),
        end: srtSeconds(end.trim()),
        text: lines.slice(timingIndex + 1).join(" ").trim(),
      };
    })
    .filter(Boolean)
    .flatMap((cue) => splitCue(cue, nextLanguage));

const renderCaption = () => {
  const cues = transcripts[language];
  const caption = document.querySelector("#live-caption");
  const currentLine = caption.querySelector(".caption-current");
  const nextLine = caption.querySelector(".caption-next");
  if (!cues.length) {
    currentLine.textContent = language === "zh"
      ? "节目开始后，这里将同步显示口播内容。"
      : "The transcript will follow the broadcast here.";
    nextLine.textContent = "";
    delete currentLine.dataset.cueIndex;
    delete nextLine.dataset.cueIndex;
    return;
  }
  const currentTime = audio.currentTime;
  let index = cues.findIndex((cue) => currentTime >= cue.start && currentTime <= cue.end);
  if (index < 0) index = Math.max(0, cues.findIndex((cue) => cue.start > currentTime) - 1);
  const currentText = cues[index]?.text || "";
  const nextText = cues[index + 1]?.text || "";
  activeCueIndex = index;
  currentLine.dataset.cueIndex = String(index);
  nextLine.dataset.cueIndex = String(Math.min(index + 1, cues.length - 1));
  if (currentLine.textContent !== currentText) {
    currentLine.textContent = currentText;
    nextLine.textContent = nextText;
    caption.animate(
      [
        { opacity: 0.25, transform: `translateY(${captionMotion * 12}px)` },
        { opacity: 1, transform: "translateY(0)" },
      ],
      { duration: 320, easing: "cubic-bezier(.22,.72,.25,1)" },
    );
    captionMotion = 1;
  }
};

const seekToCue = (index) => {
  const cues = transcripts[language];
  const targetIndex = Math.max(0, Math.min(index, cues.length - 1));
  const target = cues[targetIndex];
  if (!target) return;
  captionMotion = targetIndex < activeCueIndex ? -1 : 1;
  audio.currentTime = target.start + 0.01;
  renderCaption();
};

const loadTranscript = async (nextLanguage) => {
  const transcript = episode.transcript?.[nextLanguage];
  const fallback = `./audio/latest-${nextLanguage}`;
  const [srt, text] = await Promise.all([
    fetch(dataUrl(transcript?.srt || `${fallback}.srt`), { cache: "no-store" }).then((response) => response.text()),
    fetch(dataUrl(transcript?.text || `${fallback}.txt`), { cache: "no-store" }).then((response) => response.text()),
  ]);
  transcripts[nextLanguage] = parseSrt(srt, nextLanguage);
  scripts[nextLanguage] = text.trim();
  renderCaption();
};

const renderEpisode = () => {
  document.querySelector(".episode").dataset.language = language;
  document.querySelector("#episode-date").textContent = episode.date;
  document.querySelector("#episode-title").textContent = episode.title[language];
  document.querySelector("#stories-title").textContent = language === "zh" ? "今日故事" : "Today’s stories";
  document.querySelector("#transcript-title").textContent = language === "zh" ? "同步口播" : "Live transcript";
  document.querySelector("#full-script-button").childNodes[0].textContent = language === "zh" ? "查看全文 " : "Full script ";
  const list = document.querySelector("#story-list");
  list.replaceChildren(
    ...episode.stories.map((story) => {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.className = "story-link";
      link.classList.toggle("without-image", !story.image);
      link.href = story.url || "#";
      link.target = story.url ? "_blank" : "";
      link.rel = story.url ? "noopener noreferrer" : "";
      if (story.image) {
        const image = document.createElement("img");
        image.className = "story-image";
        image.src = dataUrl(story.image);
        image.alt = "";
        image.loading = "lazy";
        link.append(image);
      }
      const copy = document.createElement("div");
      copy.className = "story-copy";
      const heading = document.createElement("h3");
      heading.textContent = story.display?.[language] || story[language];
      const source = document.createElement("p");
      source.textContent = story.source;
      copy.append(heading, source);
      link.append(copy);
      const arrow = document.createElement("span");
      arrow.className = "story-arrow";
      arrow.setAttribute("aria-hidden", "true");
      arrow.innerHTML = '<svg viewBox="0 0 24 24"><path d="m9 5 7 7-7 7"/></svg>';
      link.append(arrow);
      item.append(link);
      return item;
    }),
  );
  audio.src = dataUrl(episode.audio[language]);
  updateMediaSession();
  audio.playbackRate = playbackSpeed;
  playButton.classList.remove("playing");
  playButton.setAttribute("aria-label", language === "zh" ? "播放" : "Play");
  renderCaption();
};

const setLanguage = (next) => {
  if (next === language) return;
  const switchToken = ++languageSwitchToken;
  const wasPlaying = !audio.paused;
  const completion = Number.isFinite(audio.duration) && audio.duration > 0
    ? audio.currentTime / audio.duration
    : Number(progress.value) / 100;
  audio.pause();
  language = next;
  localStorage.setItem("harvard-radio-language", language);
  languageButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.language === language);
  });
  renderEpisode();
  loadTranscript(language);
  const restorePosition = () => {
    if (switchToken !== languageSwitchToken) return;
    if (Number.isFinite(audio.duration) && audio.duration > 0) {
      audio.currentTime = Math.min(audio.duration - 0.01, Math.max(0, completion * audio.duration));
    }
    renderCaption();
    if (wasPlaying) audio.play().catch(() => {});
  };
  if (audio.readyState >= HTMLMediaElement.HAVE_METADATA) restorePosition();
  else audio.addEventListener("loadedmetadata", restorePosition, { once: true });
};

const loadEpisode = async (path, shouldPlay = false) => {
  audio.pause();
  const response = await fetch(dataUrl(path), { cache: "no-store" });
  if (!response.ok) throw new Error("Episode unavailable");
  episode = await response.json();
  currentEpisodePath = path;
  transcripts.zh = [];
  transcripts.en = [];
  scripts.zh = "";
  scripts.en = "";
  renderEpisode();
  Promise.allSettled([loadTranscript("zh"), loadTranscript("en")]);
  if (shouldPlay) audio.play();
};

const showView = (target) => {
  document.querySelectorAll(".view").forEach((view) => {
    view.hidden = target !== "today" && !view.classList.contains(`view-${target}`)
      ? view.id !== `${target}-view`
      : target !== "today" && view.classList.contains("view-today");
  });
  document.querySelectorAll(".view-today").forEach((view) => {
    view.hidden = target !== "today";
  });
  document.querySelector("#archive-view").hidden = target !== "archive";
  document.querySelector("#settings-view").hidden = target !== "settings";
  document.querySelectorAll("[data-view-target]").forEach((button) => {
    const active = button.dataset.viewTarget === target;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  window.scrollTo({ top: 0, behavior: "smooth" });
};

const renderArchive = () => {
  const list = document.querySelector("#archive-list");
  list.replaceChildren(...archive.map((item) => {
    const row = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    const date = document.createElement("span");
    date.className = "archive-date";
    date.textContent = item.id.slice(5).replace("-", ".");
    const copy = document.createElement("span");
    copy.className = "archive-copy";
    const title = document.createElement("strong");
    title.textContent = item.title[language] || item.title.zh;
    const subject = document.createElement("small");
    subject.textContent = item.emailSubject;
    copy.append(title, subject);
    const arrow = document.createElement("span");
    arrow.className = "archive-arrow";
    arrow.setAttribute("aria-hidden", "true");
    arrow.textContent = "›";
    button.append(date, copy, arrow);
    button.addEventListener("click", async () => {
      await loadEpisode(item.path);
      showView("today");
    });
    row.append(button);
    return row;
  }));
};

const applySettings = () => {
  audio.playbackRate = playbackSpeed;
  document.documentElement.dataset.captionSize = captionSize;
  languageButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.language === language);
  });
  document.querySelector("#setting-language").value = language;
  document.querySelector("#setting-speed").value = String(playbackSpeed);
  document.querySelector("#setting-caption-size").value = captionSize;
  document.querySelector("#setting-autoplay").checked = autoplayNext;
};

playButton.addEventListener("click", () => {
  if (audio.paused) audio.play();
  else audio.pause();
});

audio.addEventListener("play", () => {
  playButton.classList.add("playing");
  playButton.setAttribute("aria-label", language === "zh" ? "暂停" : "Pause");
});

audio.addEventListener("pause", () => {
  playButton.classList.remove("playing");
  playButton.setAttribute("aria-label", language === "zh" ? "播放" : "Play");
});

audio.addEventListener("loadedmetadata", () => {
  duration.textContent = formatTime(audio.duration);
});

audio.addEventListener("timeupdate", () => {
  elapsed.textContent = formatTime(audio.currentTime);
  progress.value = audio.duration ? String((audio.currentTime / audio.duration) * 100) : "0";
  renderCaption();
});

audio.addEventListener("ended", async () => {
  if (!autoplayNext) return;
  const current = archive.findIndex((item) => item.path === currentEpisodePath);
  const next = archive[current + 1];
  if (next) await loadEpisode(next.path, true);
});

progress.addEventListener("input", () => {
  if (audio.duration) audio.currentTime = (Number(progress.value) / 100) * audio.duration;
});

document.querySelector("#back-button").addEventListener("click", () => {
  audio.currentTime = Math.max(0, audio.currentTime - 15);
});

document.querySelector("#forward-button").addEventListener("click", () => {
  audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 15);
});

if ("mediaSession" in navigator) {
  navigator.mediaSession.setActionHandler("play", () => audio.play());
  navigator.mediaSession.setActionHandler("pause", () => audio.pause());
  navigator.mediaSession.setActionHandler("seekbackward", () => {
    audio.currentTime = Math.max(0, audio.currentTime - 15);
  });
  navigator.mediaSession.setActionHandler("seekforward", () => {
    audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 15);
  });
}

languageButtons.forEach((button) => {
  button.addEventListener("click", () => {
    setLanguage(button.dataset.language);
    renderArchive();
  });
});

document.querySelectorAll("[data-view-target]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.viewTarget));
});

document.querySelector("#setting-language").addEventListener("change", (event) => {
  setLanguage(event.target.value);
  renderArchive();
});

document.querySelector("#setting-speed").addEventListener("change", (event) => {
  playbackSpeed = Number(event.target.value);
  localStorage.setItem("harvard-radio-speed", String(playbackSpeed));
  audio.playbackRate = playbackSpeed;
});

document.querySelector("#setting-caption-size").addEventListener("change", (event) => {
  captionSize = event.target.value;
  localStorage.setItem("harvard-radio-caption-size", captionSize);
  document.documentElement.dataset.captionSize = captionSize;
});

document.querySelector("#setting-autoplay").addEventListener("change", (event) => {
  autoplayNext = event.target.checked;
  localStorage.setItem("harvard-radio-autoplay", String(autoplayNext));
});

const captionTrack = document.querySelector("#live-caption");
captionTrack.addEventListener("click", (event) => {
  const line = event.target.closest("[data-cue-index]");
  if (line) seekToCue(Number(line.dataset.cueIndex));
});
captionTrack.addEventListener("touchstart", (event) => {
  touchStartY = event.changedTouches[0].clientY;
}, { passive: true });
captionTrack.addEventListener("touchend", (event) => {
  if (touchStartY === null) return;
  const delta = event.changedTouches[0].clientY - touchStartY;
  touchStartY = null;
  if (Math.abs(delta) < 24) return;
  seekToCue(activeCueIndex + (delta < 0 ? 1 : -1));
}, { passive: true });

const dialog = document.querySelector("#script-dialog");
document.querySelector("#full-script-button").addEventListener("click", () => {
  document.querySelector("#dialog-title").textContent = language === "zh" ? "完整口播稿" : "Full broadcast script";
  document.querySelector("#full-script").textContent = scripts[language];
  dialog.showModal();
});

document.querySelector("#close-script-button").addEventListener("click", () => dialog.close());
dialog.addEventListener("click", (event) => {
  if (event.target === dialog) dialog.close();
});

loadEpisode("./episodes/latest.json")
  .then(() => {
    lastLatestCheck = Date.now();
    applySettings();
    dismissSplash();
  })
  .catch(() => {
    document.querySelector("#episode-title").textContent = "今日节目暂时无法载入";
    dismissSplash();
  });

fetch(dataUrl("./episodes/index.json"), { cache: "no-store" })
  .then((response) => response.json())
  .then((items) => {
    archive = items;
    renderArchive();
  })
  .catch(() => {
    archive = [];
    renderArchive();
  });

const refreshLatestEpisode = async () => {
  if (document.hidden || !audio.paused || Date.now() - lastLatestCheck < 5 * 60 * 1000) return;
  lastLatestCheck = Date.now();
  try {
    const response = await fetch(dataUrl("./episodes/latest.json"), { cache: "no-store" });
    if (!response.ok) return;
    const latest = await response.json();
    const currentVersion = `${episode?.date || ""}|${episode?.audio?.zh || ""}`;
    const latestVersion = `${latest?.date || ""}|${latest?.audio?.zh || ""}`;
    if (latestVersion !== currentVersion) {
      await loadEpisode("./episodes/latest.json");
    }
  } catch {
    // Keep the last playable episode when a background refresh temporarily fails.
  }
};

document.addEventListener("visibilitychange", refreshLatestEpisode);

window.setTimeout(dismissSplash, 5000);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    const registration = await navigator.serviceWorker.register("./service-worker.js");
    registration.update();
  });
}

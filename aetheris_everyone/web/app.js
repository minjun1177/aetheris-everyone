// Aetheris Everyone - the window.
"use strict";

/* ------------------------------------------------------------------ api */

const TOKEN = (() => {
  const fromUrl = new URLSearchParams(location.search).get("t");
  if (fromUrl) {
    sessionStorage.setItem("aetheris-token", fromUrl);
    history.replaceState(null, "", "/");
    return fromUrl;
  }
  return sessionStorage.getItem("aetheris-token") || "";
})();

async function api(path, body) {
  const options = { method: body === undefined ? "GET" : "POST", headers: { "X-Token": TOKEN } };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  try {
    const response = await fetch("/api/" + path, options);
    return await response.json();
  } catch (error) {
    return { ok: false, error: "network", detail: String(error) };
  }
}

/* ---------------------------------------------------------------- icons */

const ICONS = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  folderPlus: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v5M9.5 13.5h5"/>',
  shield: '<path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z"/>',
  clip: '<path d="M21 11.5l-8.6 8.6a5 5 0 0 1-7.1-7.1l8.6-8.6a3.3 3.3 0 0 1 4.7 4.7l-8.6 8.6a1.7 1.7 0 0 1-2.4-2.4l7.9-7.9"/>',
  up: '<path d="M12 19V5M5 12l7-7 7 7"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  doc: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M13 15h4"/>',
  pencil: '<path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  trash: '<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h8"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  checkCircle: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.01"/>',
  undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
  cloud: '<path d="M7 18a5 5 0 0 1-.6-10A6 6 0 0 1 18 9a4.5 4.5 0 0 1-.5 9z"/>',
  sparkle: '<path d="M12 3l2.2 6.3L20.5 12l-6.3 2.2L12 20.5l-2.2-6.3L3.5 12l6.3-2.7z"/>',
  table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
  down: '<path d="M6 9l6 6 6-6"/>',
  lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.01"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M15 8l2 2"/>',
  download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  power: '<path d="M12 3v9M6.3 6.3a8 8 0 1 0 11.4 0"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/>',
  wand: '<path d="M15 4V2M15 10V8M11 6h2M17 6h2M4 20l11-11"/>',
  back: '<path d="M19 12H5M11 18l-6-6 6-6"/>',
};

function icon(name, cls = "i") {
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
}

/* ---------------------------------------------------------------- dom */

function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const $ = (id) => document.getElementById(id);

function toast(text, ms = 2600) {
  const node = h("div", { class: "toast", text });
  $("toasts").append(node);
  setTimeout(() => node.remove(), ms);
}

function baseName(path) {
  if (!path) return "";
  const parts = String(path).replace(/[\\/]+$/, "").split(/[\\/]/);
  return parts[parts.length - 1] || path;
}

function formatBytes(n) {
  if (!n) return "0";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i >= 3 ? 1 : 0)}${units[i]}`;
}

function openUrl(url) { api("open", { url }); }

function formatTokens(n) {
  n = Number(n) || 0;
  if (n < 1000) return String(n);
  if (n < 1e6) return `${(n / 1000).toFixed(n < 10000 ? 1 : 0)}k`;
  return `${(n / 1e6).toFixed(1)}M`;
}

/* The chat's tokens so far, and for a local model how full its memory was last time. */
function renderUsage() {
  const line = $("usageLine");
  const used = S.conv && S.conv.usage;
  if (!used || !(used.input || used.output)) { line.textContent = ""; line.title = ""; return; }
  let text = t("usage.chat", { n: formatTokens(used.input + used.output) });
  const limit = S.usageLimit || (settingsNow().provider === "ollama" ? settingsNow().context_tokens : 0);
  if (limit && used.last_input) {
    const pct = Math.min(100, Math.round((used.last_input / limit) * 100));
    text += ` · ${t("usage.context", { pct })}`;
    line.classList.toggle("warn-text", pct >= 85);
  } else line.classList.remove("warn-text");
  line.textContent = text;
  line.title = t("usage.detail", { input: used.input.toLocaleString(), output: used.output.toLocaleString() });
}

/* --------------------------------------------------------------- state */

const S = {
  state: null,
  convId: null,
  conv: null,
  busy: null,
  attachments: [],
  quote: "",           // part of a message the person selected to answer or ask about
  live: {},            // reply id -> {text, thinking, el}
  liveTools: {},       // call id -> element
  approvals: {},       // approval id -> event
  adopt: false,
  ollama: null,
  engineStarting: false,
};

function settingsNow() { return (S.state && S.state.settings) || {}; }

function applyTheme() {
  const theme = settingsNow().theme || "auto";
  const dark = theme === "dark" || (theme === "auto" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);

async function refreshState() {
  const state = await api("state");
  if (!state || state.error) return;
  S.state = state;
  S.busy = state.busy;
  setLanguage(state.settings.language);
  applyTheme();
  for (const event of state.approvals || []) S.approvals[event.id] = event;
  renderChrome();
  renderConvList();
  renderEngine();
}

/* ------------------------------------------------------------- chrome */

function renderChrome() {
  $("newChat").innerHTML = icon("plus") + `<span>${t("nav.new")}</span>`;
  $("openSettings").innerHTML = icon("gear") + `<span>${t("nav.settings")}</span>`;
  $("toggleSidebar").innerHTML = icon("menu");
  $("attachBtn").innerHTML = icon("clip");
  $("attachBtn").title = t("composer.attach");
  $("input").placeholder = t("composer.placeholder");
  $("carefulText").textContent = t("composer.careful");
  $("carefulLabel").title = t("composer.careful.desc");
  $("carefulToggle").checked = !!settingsNow().careful;
  $("composerHint").textContent = t("composer.hint");
  $("dropOverlay").firstElementChild.textContent = t("composer.drop");
  renderFolderChip();
  renderSafetyChip();
  renderSendButton();
  renderTitle();
  renderBanner();
  renderModelChip();
  renderUsage();
}

function currentFolder() {
  return (S.conv && S.conv.folder) || settingsNow().work_folder || (S.state && S.state.default_folder) || "";
}

function renderTitle() {
  $("convTitle").textContent = (S.conv && S.conv.title) || "Aetheris Everyone";
  const button = $("exportChat");
  button.innerHTML = icon("download");
  button.title = t("top.export");
  button.hidden = !(S.conv && S.conv.id && S.conv.ui && S.conv.ui.length);
}

async function exportChat() {
  if (!S.convId) return;
  const result = await api("conversation/export", { id: S.convId, language: LANG });
  if (!result.ok) return toast(errText(result.error));
  toast(t("top.export.ok", { name: baseName(result.path) }), 3600);
  api("reveal", { path: result.path });
}

function renderFolderChip() {
  const folder = currentFolder();
  $("folderChip").innerHTML = icon("folder") + `<span>${escapeHtml(baseName(folder) || t("top.folder"))}</span>` + icon("down");
  $("folderChip").title = `${t("top.folder")}: ${folder}`;
}

function renderSafetyChip() {
  const level = settingsNow().safety || "balanced";
  $("safetyChip").innerHTML = icon("shield") + `<span>${escapeHtml(t("safety." + level).replace(/ \(.*\)$/, ""))}</span>` + icon("down");
  $("safetyChip").title = t("top.safety");
}

function closeMenus() {
  $("folderMenu").hidden = true;
  $("safetyMenu").hidden = true;
  $("modelMenu").hidden = true;
}

/* ---------------------------------------------------------- model picker */

const MODEL_CACHE = {};        // provider -> [model names], read once per window

function shortModel(name) {
  return String(name || "").replace(/^hf\.co\/[^/]+\//, "").replace(/:latest$/, "");
}

function renderModelChip() {
  const s = settingsNow();
  const name = (S.state && S.state.model) || "";
  $("modelChip").innerHTML = `<span>${escapeHtml(shortModel(name) || t("status.none"))}</span>` + icon("down");
  $("modelChip").title = `${t("model.pick")}: ${(S.state && S.state.provider_label) || ""} · ${name}`;
  $("modelChip").hidden = !s.setup_done;
}

async function modelsOf(provider) {
  if (MODEL_CACHE[provider]) return MODEL_CACHE[provider];
  const result = provider === "ollama" ? await api("ollama/status") : await api("provider/test", { provider });
  const models = (result && result.models) || [];
  if (models.length) MODEL_CACHE[provider] = models;
  return models;
}

async function openModelMenu() {
  const menu = $("modelMenu");
  const wasOpen = !menu.hidden;
  closeMenus();
  if (wasOpen) return;
  const s = settingsNow();
  const keys = (S.state && S.state.keys) || {};
  const providers = ["ollama", ...["anthropic", "openai", "gemini"].filter((p) => keys[p])];
  const pick = async (provider, model) => {
    closeMenus();
    const result = await api("provider/use", { provider, model });
    if (!result.ok) return toast(errText(result.error));
    await refreshState();
    toast(t("model.switched", { model: shortModel(model) }), 1800);
  };
  const body = h("div", { class: "model-list" }, h("div", { class: "muted pad", text: t("model.loading") }));
  menu.replaceChildren(body, h("button", { class: "foot", html: icon("gear") + `<span>${escapeHtml(t("model.settings"))}</span>`,
    onclick: () => { closeMenus(); openSettings("ai"); } }));
  menu.hidden = false;
  const sections = await Promise.all(providers.map(async (provider) => [provider, await modelsOf(provider)]));
  if (menu.hidden) return;
  const nodes = [];
  for (const [provider, models] of sections) {
    if (!models.length) continue;
    nodes.push(h("div", { class: "menu-label", text: PROVIDER_LABELS[provider] || provider }));
    for (const model of models) {
      const current = provider === s.provider && model === S.state.model;
      nodes.push(h("button", { class: current ? "sel" : "", title: model, onclick: () => pick(provider, model) },
        h("span", { class: "opt-title", text: shortModel(model) }), current ? h("span", { html: icon("check") }) : null));
    }
  }
  body.replaceChildren(...(nodes.length ? nodes : [h("div", { class: "muted pad", text: t("model.none") })]));
}

const PROVIDER_LABELS = { ollama: "Ollama", anthropic: "Claude (Anthropic)", openai: "ChatGPT (OpenAI)", gemini: "Gemini (Google)" };

function openFolderMenu() {
  const menu = $("folderMenu");
  const wasOpen = !menu.hidden;
  closeMenus();
  if (wasOpen) return;
  const folder = currentFolder();
  menu.replaceChildren(
    h("div", { class: "path", text: folder }),
    h("button", { html: icon("external") + `<span>${t("top.folder.open")}</span>`, onclick: () => { closeMenus(); api("reveal", { path: folder }); } }),
    h("button", { html: icon("folder") + `<span>${t("top.folder.change")}</span>`, onclick: () => { closeMenus(); chooseFolder(); } }),
  );
  menu.hidden = false;
}

async function chooseFolder() {
  const picked = await api("pick_folder", { initial: currentFolder() });
  if (!picked.path) return;
  if (S.conv && S.conv.id && S.conv.ui && S.conv.ui.length) {
    const result = await api("conversation/folder", { id: S.conv.id, folder: picked.path });
    if (result.error === "busy") return toast(t("err.busy"));
    if (result.ok) S.conv.folder = result.folder;
  } else {
    const result = await api("settings", { work_folder: picked.path });
    if (S.conv) S.conv.folder = result.settings && result.settings.work_folder;
  }
  await refreshState();
  if (!S.conv || !S.conv.ui || !S.conv.ui.length) renderThread();
}

function openSafetyMenu() {
  const menu = $("safetyMenu");
  const wasOpen = !menu.hidden;
  closeMenus();
  if (wasOpen) return;
  const current = settingsNow().safety || "balanced";
  menu.replaceChildren(...["ask", "balanced", "auto"].map((level) =>
    h("button", {
      class: level === current ? "sel" : "",
      onclick: async () => { closeMenus(); await api("settings", { safety: level }); await refreshState(); },
    }, h("div", {}, h("div", { class: "opt-title", text: t("safety." + level) }), h("div", { class: "opt-desc", text: t(`safety.${level}.desc`) })))));
  menu.hidden = false;
}

function renderBanner() {
  const banner = $("approvalBanner");
  const elsewhere = Object.values(S.approvals).find((a) => a.conversation !== S.convId);
  if (!elsewhere) { banner.hidden = true; return; }
  banner.replaceChildren(h("span", { html: icon("alert") }), h("span", { text: t("approve.waiting") }),
    h("button", { class: "btn small", text: t("approve.go"), onclick: () => openConversation(elsewhere.conversation) }));
  banner.hidden = false;
}

/* --------------------------------------------------------- engine pill */

async function pollOllama() {
  if (settingsNow().provider !== "ollama" || !settingsNow().setup_done) return;
  S.ollama = await api("ollama/status");
  renderEngine();
}

function renderEngine() {
  const s = settingsNow();
  const button = $("engineStatus");
  let led = "on";
  let name = S.state ? S.state.model : "";
  const remote = s.provider === "ollama" && S.ollama && S.ollama.local === false;
  let sub = S.state ? (s.provider === "ollama" ? (remote ? hostName(S.ollama.host) : t("status.local")) : S.state.provider_label) : "";
  if (!s.setup_done || !name) {
    led = "off"; name = t("status.none"); sub = "";
  } else if (s.provider === "ollama" && S.ollama && !S.ollama.running) {
    led = S.engineStarting ? "wait" : "off";
    sub = remote ? t("status.remote_off", { host: hostName(S.ollama.host) }) : S.engineStarting ? t("status.starting") : t("status.off");
  }
  button.innerHTML = `<span class="led ${led}"></span><span class="txt"><b>${escapeHtml(name)}</b><small>${escapeHtml(sub)}</small></span>`;
}

function hostName(url) {
  try { return new URL(url).host; } catch (_) { return String(url || ""); }
}

async function engineClicked() {
  const s = settingsNow();
  if (!s.setup_done) return openSetup(0);
  if (s.provider === "ollama" && S.ollama && !S.ollama.running && S.ollama.local !== false) return startEngine();
  openSettings("ai");
}

async function startEngine() {
  S.engineStarting = true;
  renderEngine();
  await api("ollama/start", {});
  S.engineStarting = false;
  await pollOllama();
}

/* ----------------------------------------------------- conversation list */

function renderConvList() {
  const list = $("convList");
  const items = (S.state && S.state.conversations) || [];
  if (!items.length) { list.replaceChildren(h("div", { class: "empty-nav", text: t("nav.empty") })); return; }
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime() / 1000;
  const groups = [[t("nav.today"), []], [t("nav.yesterday"), []], [t("nav.earlier"), []]];
  for (const item of items) {
    const when = item.updated || 0;
    groups[when >= startToday ? 0 : when >= startToday - 86400 ? 1 : 2][1].push(item);
  }
  const nodes = [];
  for (const [label, group] of groups) {
    if (!group.length) continue;
    nodes.push(h("div", { class: "conv-group", text: label }));
    for (const item of group) nodes.push(convRow(item));
  }
  list.replaceChildren(...nodes);
}

function convRow(item) {
  const row = h("div", { class: "conv" + (item.id === S.convId ? " active" : ""), title: item.title, onclick: () => openConversation(item.id) },
    S.busy === item.id ? h("span", { class: "dot" }) : null,
    h("span", { class: "title", text: item.title || "…" }),
    h("span", { class: "acts" },
      h("button", { title: t("nav.rename"), html: icon("pencil"), onclick: (e) => { e.stopPropagation(); renameConv(row, item); } }),
      h("button", { title: t("nav.delete"), html: icon("trash"), onclick: (e) => { e.stopPropagation(); deleteConv(item); } })));
  return row;
}

function renameConv(row, item) {
  const input = h("input", { value: item.title || "" });
  const done = async (save) => {
    if (save && input.value.trim()) {
      const result = await api("conversation/rename", { id: item.id, title: input.value.trim() });
      if (result.conversations) S.state.conversations = result.conversations;
      if (S.conv && S.conv.id === item.id) S.conv.title = input.value.trim();
      renderTitle();
    }
    renderConvList();
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) done(true);
    if (e.key === "Escape") done(false);
  });
  input.addEventListener("blur", () => done(true));
  input.addEventListener("click", (e) => e.stopPropagation());
  row.replaceChildren(input);
  input.focus();
  input.select();
}

function deleteConv(item) {
  confirmModal(t("confirm.delete.title"), t("confirm.delete.body"), t("confirm.ok"), async () => {
    const result = await api("conversation/delete", { id: item.id });
    if (!result.ok) return toast(t("err.busy"));
    S.state.conversations = result.conversations;
    if (S.convId === item.id) newChat();
    renderConvList();
  });
}

async function openConversation(id) {
  closeMenus();
  hideSettings();
  const data = await api("conversation?id=" + encodeURIComponent(id));
  if (!data || data.error) return;
  S.convId = id;
  S.conv = data;
  S.live = {};
  S.liveTools = {};
  renderChrome();
  renderConvList();
  renderThread();
  if (window.innerWidth <= 900) $("app").classList.add("collapsed");
}

function newChat() {
  hideSettings();
  S.convId = null;
  S.conv = null;
  S.live = {};
  S.liveTools = {};
  renderChrome();
  renderConvList();
  renderThread();
  $("input").focus();
}

/* --------------------------------------------------------------- thread */

const EXAMPLES = [
  ["folder", "organize"], ["doc", "summary"], ["book", "word"],
  ["table", "excel"], ["globe", "web"], ["image", "photo"],
];

function nearBottom() {
  const box = $("messages");
  return box.scrollHeight - box.scrollTop - box.clientHeight < 160;
}

function scrollDown(force) {
  const box = $("messages");
  if (force || nearBottom()) box.scrollTop = box.scrollHeight;
}

function threadNode() {
  let thread = $("messages").querySelector(".thread");
  if (!thread) {
    $("messages").replaceChildren();
    thread = h("div", { class: "thread" });
    $("messages").append(thread);
  }
  return thread;
}

function renderWelcome() {
  const folder = currentFolder();
  $("messages").replaceChildren(h("div", { class: "welcome" },
    h("img", { class: "logo", src: "icon.svg", alt: "" }),
    h("h1", { text: t("welcome.title") }),
    h("p", { text: t("welcome.sub") }),
    h("div", { class: "folder-line" }, `${t("top.folder")}: `,
      h("button", { html: icon("folder") + " " + escapeHtml(folder), onclick: openFolderMenu, title: folder })),
    h("div", { class: "examples" }, ...EXAMPLES.map(([ic, key]) =>
      h("button", { class: "example", onclick: () => useExample(key) },
        h("div", { class: "ex-icon", html: icon(ic) }),
        h("b", { text: t(`ex.${key}.t`) }),
        h("span", { text: t(`ex.${key}.p`) }))))));
}

function useExample(key) {
  const input = $("input");
  input.value = t(`ex.${key}.p`);
  autosize();
  input.focus();
  if (key === "photo") $("fileInput").click();
}

function renderThread() {
  const items = (S.conv && S.conv.ui) || [];
  const busyHere = !!S.busy && S.busy === S.convId;
  if (!items.length && !busyHere) return renderWelcome();
  $("messages").replaceChildren();
  const thread = threadNode();
  for (const item of items) {
    const node = renderItem(item);
    if (node) thread.append(node);
  }
  for (const approval of Object.values(S.approvals)) {
    if (approval.conversation === S.convId) thread.append(approvalCard(approval));
  }
  if (busyHere && !Object.keys(S.live).length) {
    thread.append(liveReply("__waiting__").el);
  }
  markLastRequest();
  scrollDown(true);
}

/* Edit or retry the last request: the chat goes back to before it (files stay as they are). */
function markLastRequest() {
  for (const old of document.querySelectorAll("#messages .user-actions")) old.remove();
  if (S.busy || !S.convId) return;
  const requests = document.querySelectorAll("#messages .msg.user");
  const last = requests[requests.length - 1];
  if (!last) return;
  last.append(h("div", { class: "user-actions" },
    h("button", { html: icon("pencil") + escapeHtml(t("msg.edit")), onclick: () => retakeLast(false) }),
    h("button", { html: icon("undo") + escapeHtml(t("msg.retry")), onclick: () => retakeLast(true) })));
}

async function retakeLast(resend) {
  if (S.busy) return toast(t("err.busy"));
  const result = await api("conversation/rewind", { id: S.convId });
  if (!result.ok) return toast(errText(result.error));
  await openConversation(S.convId);
  $("input").value = result.text || "";
  setQuote(result.quote || "");
  S.attachments = (result.attachments || []).map((a) => ({ name: a.name, path: a.path, uploading: false,
    preview: a.image ? `/api/file?t=${encodeURIComponent(TOKEN)}&path=${encodeURIComponent(a.path)}` : null }));
  renderAttachments();
  autosize();
  if (resend) send(); else $("input").focus();
}

function renderItem(item) {
  switch (item.kind) {
    case "user": return userMessage(item);
    case "assistant": return aiMessage(item);
    case "tool": return toolCard(item);
    case "changes": return changesCard(item);
    case "notice": return h("div", { class: "notice" }, h("span", { html: icon("info") }), h("span", { text: t("notice." + item.code) }));
    case "error": return errorCard(item);
    default: return null;
  }
}

function userMessage(item) {
  const atts = (item.attachments || []).map((a) => a.image
    ? h("img", { class: "thumb", src: `/api/file?t=${encodeURIComponent(TOKEN)}&path=${encodeURIComponent(a.path)}`, alt: a.name })
    : h("span", { class: "att", html: icon("file") + " " + escapeHtml(a.name) }));
  return h("div", { class: "msg user" }, h("div", { class: "bubble" },
    item.quote ? h("div", { class: "quote", text: item.quote }) : null,
    atts.length ? h("div", { class: "atts" }, ...atts) : null,
    item.text && item.text !== "(see attached)" ? h("div", { text: item.text }) : null));
}

function aiShell(content) {
  return h("div", { class: "msg ai" }, h("div", { class: "avatar" }, h("img", { src: "icon.svg", alt: "" })), content);
}

function aiMessage(item) {
  const bubble = h("div", { class: "bubble" });
  if (item.thinking) {
    bubble.append(h("details", { class: "thoughts" }, h("summary", { text: t("msg.thoughts") }), h("div", { text: item.thinking })));
  }
  if (item.text) {
    bubble.append(h("div", { class: "md", html: renderMarkdown(item.text) }));
    bubble.append(h("div", { class: "msg-actions" }, h("button", {
      html: icon("copy") + t("msg.copy"),
      onclick: () => copyText(item.text),
    }), item.usage ? h("span", { class: "tokens", title: t("usage.detail", { input: item.usage.input.toLocaleString(), output: item.usage.output.toLocaleString() }),
      text: `${formatTokens(item.usage.input)} → ${formatTokens(item.usage.output)} ${t("usage.tokens")}` }) : null));
  }
  return aiShell(bubble);
}

function copyText(text) {
  const done = () => toast(t("msg.copied"), 1400);
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
  } else fallbackCopy(text, done);
}

function fallbackCopy(text, done) {
  const area = h("textarea", { style: "position:fixed;opacity:0" });
  area.value = text;
  document.body.append(area);
  area.select();
  try { document.execCommand("copy"); done(); } catch (_) { /* nothing */ }
  area.remove();
}

function liveReply(id) {
  if (S.live[id]) return S.live[id];
  const md = h("div", { class: "md" });
  const thoughts = h("details", { class: "thoughts", hidden: true }, h("summary", { text: t("msg.thoughts") }), h("div"));
  const waiting = h("div", { class: "thinking-live" }, h("span", { class: "dots" }, h("i"), h("i"), h("i")), h("span", { text: t("msg.thinking") }));
  const el = aiShell(h("div", { class: "bubble" }, thoughts, waiting, md));
  const live = { text: "", thinking: "", el, md, thoughts, waiting, queued: false };
  S.live[id] = live;
  return live;
}

function paintLive(live) {
  if (live.queued) return;
  live.queued = true;
  requestAnimationFrame(() => {
    live.queued = false;
    const stick = nearBottom();
    if (live.thinking) {
      live.thoughts.hidden = false;
      live.thoughts.lastElementChild.textContent = live.thinking;
    }
    if (live.text.trim()) {
      live.waiting.hidden = true;
      live.md.innerHTML = renderMarkdown(live.text);
      live.md.classList.add("cursor");
    }
    if (stick) scrollDown(true);
  });
}

const TOOL_ICONS = {
  list_folder: "folder", find_files: "search", search_text: "search", read_file: "eye",
  write_file: "doc", edit_file: "pencil", create_folder: "folderPlus", move: "arrow",
  copy: "copy", delete: "trash", run_command: "terminal", web_search: "globe", read_webpage: "globe",
  remember: "book", forget: "x", view_image: "image",
};

function toolArg(args) {
  if (!args) return "";
  if (args.command) return args.command;
  if (args.source && args.destination) return `${baseName(args.source)} → ${baseName(args.destination)}`;
  if (args.path) return args.path === "." ? "" : args.path;
  return args.query || args.url || args.pattern || args.text || "";
}

function toolCard(item) {
  const status = item.status || "running";
  const label = STRINGS.en["tool." + item.name] ? t("tool." + item.name) : t("tool.other");
  const state = status === "running"
    ? h("span", { class: "tstate" }, h("span", { class: "spinner" }), t("tool.running"))
    : h("span", { class: "tstate", html: icon(status === "ok" ? "check" : status === "denied" ? "x" : "alert") + escapeHtml(t("tool." + status)) });
  const card = h("div", { class: `tool ${status}` },
    h("div", { class: "tool-head", onclick: () => card.classList.toggle("open") },
      h("span", { class: "ticon", html: icon(TOOL_ICONS[item.name] || "sparkle") }),
      h("span", { class: "tlabel", text: label }),
      h("span", { class: "targ", text: toolArg(item.args), title: toolArg(item.args) }),
      state),
    h("div", { class: "tool-body" },
      item.args && item.args.reason ? h("div", { class: "reason", text: item.args.reason }) : null,
      item.args && item.args.command ? h("pre", { text: "$ " + item.args.command }) : null,
      item.image ? h("img", { class: "tool-thumb", alt: "", src: `/api/file?t=${encodeURIComponent(TOKEN)}&path=${encodeURIComponent(item.image)}` }) : null,
      item.result ? h("pre", { text: item.result }) : null));
  if (status === "error" || item.image) card.classList.add("open");
  return card;
}

function changesCard(item) {
  const files = item.files || [];
  const card = h("div", { class: "changes" + (item.undone ? " undone" : "") });
  const rows = files.map((f) => h("div", { class: "change-row" },
    h("span", { class: `kind ${f.kind}`, text: t("changes." + f.kind) }),
    h("span", { class: "name", title: f.path }, baseName(f.path), f.from ? h("small", { text: `← ${movedFrom(f)}` }) : null),
    item.undone || f.kind === "deleted" ? null : h("span", { class: "row-acts" },
      f.kind !== "folder" ? h("button", { class: "btn small ghost", text: t("changes.open"), onclick: () => api("open", { path: f.path }) }) : null,
      h("button", { class: "btn small ghost", text: t("changes.reveal"), onclick: () => api("reveal", { path: f.path }) }))));
  const foot = h("div", { class: "changes-foot" }, item.undone
    ? h("span", { class: "badge", html: icon("undo") + escapeHtml(t("changes.undone")) })
    : item.expired ? h("span", { class: "badge", html: icon("info") + escapeHtml(t("changes.expired")) })
    : h("button", { class: "btn small", html: icon("undo") + escapeHtml(t("changes.undo")), onclick: () => undoChanges(item, false) }));
  card.append(h("div", { class: "changes-head", html: icon("checkCircle") + escapeHtml(t("changes.title", { n: files.length })) }), ...rows, foot);
  return card;
}

function movedFrom(f) {
  const before = baseName(f.from);
  if (before !== baseName(f.path)) return before;
  const parent = String(f.from).replace(/[\\/][^\\/]*$/, "");
  return baseName(parent) + "/";
}

async function undoChanges(item, force) {
  const conversation = S.convId;
  const result = await api("undo", { conversation, change: item.change_id, force });
  if (result.error === "busy") return toast(t("err.busy"));
  if (result.conflicts && result.conflicts.length) {
    const list = h("ul", {}, ...result.conflicts.map((p) => h("li", { text: p })));
    return confirmModal(t("changes.conflict.title"), [t("changes.conflict.body"), list], t("changes.conflict.go"), () => undoChanges(item, true));
  }
  toast(result.ok ? t("changes.undo.ok") : t("changes.undo.partial"));
  if (S.convId === conversation) await openConversation(conversation);
}

function errText(code) {
  return STRINGS.en["err." + code] ? t("err." + code) : t("err.other");
}

function errorCard(item) {
  const code = item.code || "other";
  const acts = [];
  if (code === "ollama_down") acts.push(h("button", { class: "btn small primary", html: icon("power") + escapeHtml(t("err.ollama_down.act")), onclick: startEngine }));
  if (code === "model_missing" || code === "no_model") acts.push(h("button", { class: "btn small primary", html: icon("download") + escapeHtml(t("err.model_missing.act")), onclick: () => openSetup(settingsNow().provider === "ollama" ? 3 : 2) }));
  if (code === "bad_key" || code === "no_key") acts.push(h("button", { class: "btn small primary", html: icon("key") + escapeHtml(t("err.key.act")), onclick: () => openSetup(2) }));
  if (!["bad_key", "no_key", "no_model"].includes(code)) acts.push(h("button", { class: "btn small", html: icon("undo") + escapeHtml(t("err.retry")), onclick: () => retakeLast(true) }));
  const message = errText(code);
  return h("div", { class: "error-card" }, h("span", { html: icon("alert") }),
    h("div", {}, h("div", { text: message }),
      item.detail && code !== "ollama_down" ? h("div", { class: "detail", text: item.detail }) : null,
      acts.length ? h("div", { class: "acts" }, ...acts) : null));
}

/* ------------------------------------------------------------ approvals */

function approvalWhat(r) {
  switch (r.tool) {
    case "write_file": return t(r.append ? "approve.append" : r.exists ? "approve.write.replace" : "approve.write.new");
    case "edit_file": return t("approve.edit");
    case "delete": return t("approve.delete");
    case "move": return t("approve.move");
    case "copy": return t("approve.copy");
    case "create_folder": return t("approve.mkdir");
    case "run_command": return t("approve.run");
    case "remember": return t("approve.remember");
    default: return t("approve.read");
  }
}

function approvalCard(event) {
  const r = event.request || {};
  const card = h("div", { class: "approval", id: "approval-" + event.id });
  const parts = [
    h("h4", { html: icon("shield") + escapeHtml(t("approve.title")) + (r.outside ? ` <span class="pill">${escapeHtml(t("approve.outside"))}</span>` : "") }),
    h("div", { class: "what", text: approvalWhat(r) }),
  ];
  if (r.tool === "run_command") {
    if (r.reason) parts.push(h("div", { class: "reason", text: r.reason }));
    parts.push(h("div", { class: "target", text: r.command }));
    parts.push(h("div", { class: "note warn", text: t("approve.run.note") }));
  } else if (r.tool === "remember") {
    parts.push(h("div", { class: "target", text: r.text }));
    parts.push(h("div", { class: "note", text: t("approve.remember.note") }));
  } else {
    parts.push(h("div", { class: "target", text: r.target ? `${r.path}\n→ ${r.target}` : r.path }));
    if (r.tool === "delete") parts.push(h("div", { class: "note", text: t("approve.delete.note") }));
    if (r.preview) parts.push(h("details", {}, h("summary", { text: t("approve.preview") }), h("pre", { text: r.preview })));
    if (r.tool === "edit_file") {
      parts.push(h("details", { open: true }, h("summary", { text: `${t("approve.before")} → ${t("approve.after")}` }),
        h("pre", { class: "diff-old", text: r.old || "" }), h("pre", { class: "diff-new", text: r.new || "" })));
    }
  }
  const answer = (value) => async () => {
    card.classList.add("answered");
    await api("approve", { id: event.id, answer: value });
  };
  // A program is asked about every time: "for this chat" is not offered for it.
  parts.push(h("div", { class: "acts" },
    h("button", { class: "btn primary", html: icon("check") + escapeHtml(t("approve.allow")), onclick: answer("allow") }),
    r.tool === "run_command" ? null : h("button", { class: "btn", text: t("approve.always"), onclick: answer("always") }),
    h("button", { class: "btn ghost", html: icon("x") + escapeHtml(t("approve.deny")), onclick: answer("deny") })));
  card.append(...parts);
  return card;
}

/* --------------------------------------------------------------- events */

function connectEvents() {
  const source = new EventSource("/api/events?t=" + encodeURIComponent(TOKEN));
  let opened = false;
  source.onopen = async () => {
    if (opened) {
      await refreshState();
      if (S.convId) await openConversation(S.convId);
    }
    opened = true;
  };
  source.onmessage = (message) => {
    let event;
    try { event = JSON.parse(message.data); } catch (_) { return; }
    handleEvent(event);
  };
}

function isHere(event) {
  if (event.conversation && S.adopt && !S.convId) {
    S.convId = event.conversation;
    S.conv = { id: event.conversation, ui: [], title: "", folder: currentFolder() };
    S.adopt = false;
  }
  return event.conversation === S.convId;
}

function handleEvent(event) {
  switch (event.type) {
    case "turn_start":
      S.busy = event.conversation;
      for (const old of document.querySelectorAll("#messages .user-actions")) old.remove();
      if (isHere(event)) { if (!$("messages").querySelector(".thread")) threadNode(); }
      renderSendButton();
      refreshConvSoon();
      break;
    case "turn_end":
      S.busy = null;
      if (isHere(event)) {
        for (const live of Object.values(S.live)) live.el.remove();
        S.live = {};
        for (const el of Object.values(S.liveTools)) el.remove();
        S.liveTools = {};
      }
      renderSendButton();
      refreshConvSoon(true);
      if (isHere(event)) markLastRequest();
      break;
    case "reply_start":
      if (!isHere(event)) break;
      dropWaiting();
      threadNode().append(liveReply(event.id).el);
      scrollDown();
      break;
    case "delta": {
      if (!isHere(event)) break;
      const live = liveReply(event.id);
      if (!live.el.isConnected) threadNode().append(live.el);
      if (event.kind === "thinking") live.thinking += event.text;
      else live.text += event.text;
      paintLive(live);
      break;
    }
    case "retry": {
      if (!isHere(event)) break;
      const live = liveReply(event.id);
      if (!live.el.isConnected) threadNode().append(live.el);
      live.waiting.hidden = false;
      live.waiting.lastElementChild.textContent = t("msg.retrying", { seconds: event.seconds, attempt: event.attempt, of: event.of });
      scrollDown();
      break;
    }
    case "usage":
      if (event.conversation === S.convId && S.conv) {
        S.conv.usage = event.total;
        S.usageLimit = event.limit;
        renderUsage();
      }
      break;
    case "reply_empty":
      if (!isHere(event)) break;
      if (S.live[event.id]) { S.live[event.id].el.remove(); delete S.live[event.id]; }
      break;
    case "tool_start": {
      if (!isHere(event)) break;
      dropWaiting();
      const card = toolCard({ name: event.name, args: event.args, status: "running" });
      S.liveTools[event.id] = card;
      threadNode().append(card);
      scrollDown();
      break;
    }
    case "item":
      if (!isHere(event)) break;
      placeItem(event.item);
      break;
    case "approval":
      S.approvals[event.id] = event;
      if (isHere(event)) { threadNode().append(approvalCard(event)); scrollDown(true); }
      renderBanner();
      break;
    case "approval_done": {
      delete S.approvals[event.id];
      const card = $("approval-" + event.id);
      if (card) {
        card.classList.add("answered");
        card.querySelector(".what").textContent += ` — ${t("approve.answered." + event.answer)}`;
        setTimeout(() => card.remove(), 1200);
      }
      renderBanner();
      break;
    }
    case "settings_changed":
      for (const key of Object.keys(MODEL_CACHE)) delete MODEL_CACHE[key];   // a model pulled, a key added
      refreshState().then(pollOllama);
      break;
    case "pull":
    case "install":
      if (window.onJobEvent) window.onJobEvent(event);
      break;
    default:
      break;
  }
}

function dropWaiting() {
  if (S.live.__waiting__) { S.live.__waiting__.el.remove(); delete S.live.__waiting__; }
}

function placeItem(item) {
  if (!S.conv) return;
  S.conv.ui.push(item);
  if (item.kind === "user" && !S.conv.title) {
    S.conv.title = item.text.slice(0, 40);
    renderTitle();
  }
  const node = renderItem(item);
  if (!node) return;
  const thread = threadNode();
  if (item.kind === "assistant" && S.live[item.id]) {
    S.live[item.id].el.replaceWith(node);
    delete S.live[item.id];
  } else if (item.kind === "tool" && S.liveTools[item.id]) {
    S.liveTools[item.id].replaceWith(node);
    delete S.liveTools[item.id];
  } else {
    thread.append(node);
  }
  if (item.kind === "user") {
    thread.append(liveReply("__waiting__").el);
    scrollDown(true);
  } else {
    // keep any live reply below what just landed
    for (const live of Object.values(S.live)) if (live.el.isConnected) thread.append(live.el);
    scrollDown();
  }
}

let convTimer = null;
function refreshConvSoon(alsoState) {
  clearTimeout(convTimer);
  convTimer = setTimeout(async () => {
    if (alsoState) await refreshState();
    else {
      const state = await api("state");
      if (state && !state.error) { S.state = state; renderConvList(); }
    }
  }, 300);
}

/* ------------------------------------------------------------- composer */

function autosize() {
  const input = $("input");
  input.style.height = "auto";
  input.style.height = Math.min(220, input.scrollHeight) + "px";
  renderSendButton();
}

function renderSendButton() {
  const button = $("sendBtn");
  const busyHere = S.busy && (S.busy === S.convId || !S.convId);
  if (S.busy && busyHere) {
    button.className = "send stop";
    button.innerHTML = icon("stop");
    button.title = t("composer.stop");
    button.disabled = false;
  } else {
    button.className = "send";
    button.innerHTML = icon("up");
    button.title = t("composer.send");
    button.disabled = !$("input").value.trim() && !S.attachments.length;
  }
}

async function send() {
  if (S.busy && (S.busy === S.convId || !S.convId)) {
    await api("stop", {});
    return;
  }
  const text = $("input").value.trim();
  if (!text && !S.attachments.length) return;
  if (S.attachments.some((a) => a.uploading)) return toast(t("composer.uploading"));
  if (!settingsNow().setup_done) return openSetup(0);
  if (S.busy) return toast(t("err.busy"));
  const attachments = S.attachments.map((a) => a.path);
  if (!S.convId) S.adopt = true;
  const result = await api("send", { conversation: S.convId, text, attachments, quote: S.quote });
  if (!result.ok) {
    S.adopt = false;
    return toast(errText(result.error));
  }
  if (!S.convId || S.convId !== result.conversation) {
    S.convId = result.conversation;
    if (!S.conv || S.conv.id !== result.conversation) {
      S.conv = { id: result.conversation, ui: [], title: text.slice(0, 40), folder: currentFolder() };
    }
    S.adopt = false;
  }
  $("input").value = "";
  S.attachments = [];
  setQuote("");
  renderAttachments();
  autosize();
  renderTitle();
}

/* ------------------------------------------- answering a selected part */

const QUOTE_LIMIT = 4000;

function setQuote(text) {
  S.quote = String(text || "").trim().slice(0, QUOTE_LIMIT);
  const row = $("quoteRow");
  row.hidden = !S.quote;
  if (S.quote) {
    row.replaceChildren(h("span", { html: icon("undo") }), h("span", { class: "q", text: S.quote }),
      h("button", { title: t("quote.remove"), html: icon("x"), onclick: () => setQuote("") }));
  }
}

function selectedInThread() {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
  const text = selection.toString().trim();
  const range = selection.getRangeAt(0);
  const start = range.commonAncestorContainer;
  const node = start.nodeType === 1 ? start : start.parentElement;
  if (!text || !node || !node.closest("#messages .msg .bubble, #messages .msg .md")) return null;
  return { text, rect: range.getBoundingClientRect() };
}

function hideSelectBar() { $("selectBar").hidden = true; }

function showSelectBar() {
  const found = selectedInThread();
  const bar = $("selectBar");
  if (!found) return hideSelectBar();
  const ask = (prompt) => () => {
    hideSelectBar();
    setQuote(found.text);
    window.getSelection().removeAllRanges();
    if (prompt && !S.busy) { $("input").value = prompt; autosize(); send(); return; }
    if (prompt) $("input").value = prompt;
    autosize();
    $("input").focus();
  };
  bar.replaceChildren(
    h("button", { html: icon("undo") + `<span>${escapeHtml(t("quote.reply"))}</span>`, onclick: ask("") }),
    h("button", { html: icon("sparkle") + `<span>${escapeHtml(t("quote.explain"))}</span>`, onclick: ask(t("quote.explain.prompt")) }),
    h("button", { html: icon("copy") + `<span>${escapeHtml(t("msg.copy"))}</span>`, onclick: () => { hideSelectBar(); copyText(found.text); } }));
  bar.hidden = false;
  const width = bar.offsetWidth;
  const left = Math.max(8, Math.min(window.innerWidth - width - 8, found.rect.left + found.rect.width / 2 - width / 2));
  const top = found.rect.top > 56 ? found.rect.top - bar.offsetHeight - 8 : found.rect.bottom + 8;
  bar.style.left = `${left}px`;
  bar.style.top = `${top}px`;
}

function setupSelectBar() {
  document.addEventListener("mouseup", (e) => { if (!(e.target.closest && e.target.closest("#selectBar"))) setTimeout(showSelectBar, 0); });
  document.addEventListener("keyup", (e) => { if (e.shiftKey) showSelectBar(); });
  $("selectBar").addEventListener("mousedown", (e) => e.preventDefault());   // keep the selection
  $("messages").addEventListener("scroll", hideSelectBar);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideSelectBar(); });
}

function renderAttachments() {
  $("attachRow").replaceChildren(...S.attachments.map((a, index) => h("span", { class: "att-chip", title: a.name },
    a.preview ? h("img", { src: a.preview, alt: "" }) : h("span", { html: icon(a.uploading ? "download" : "file") }),
    h("span", { text: a.uploading ? `${a.name} · ${t("composer.uploading")}` : a.name }),
    h("button", { html: icon("x"), onclick: () => { S.attachments.splice(index, 1); renderAttachments(); renderSendButton(); } }))));
  renderSendButton();
}

// Photos larger than this get a reduced copy for the AI: the services refuse big
// pictures, and a phone photo is often 5-10 MB. The original stays for file work.
const SHRINK_OVER = 3_000_000;

async function shrinkImage(file) {
  if (!/^image\/(jpeg|png|webp)$/.test(file.type || "") || file.size <= SHRINK_OVER) return null;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, 2048 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const g = canvas.getContext("2d");
    g.fillStyle = "#fff";
    g.fillRect(0, 0, canvas.width, canvas.height);
    g.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    if (bitmap.close) bitmap.close();
    return await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.85));
  } catch (_) {
    return null;                     // the server tells the AI the picture was too large
  }
}

async function addFiles(fileList) {
  for (const file of Array.from(fileList || [])) {
    const entry = { name: file.name || "image.png", uploading: true, preview: null, path: "" };
    if (file.type && file.type.startsWith("image/")) entry.preview = URL.createObjectURL(file);
    S.attachments.push(entry);
    renderAttachments();
    try {
      const response = await fetch("/api/upload", {
        method: "POST",
        headers: { "X-Token": TOKEN, "X-Filename": encodeURIComponent(entry.name) },
        body: file,
      });
      const result = await response.json();
      if (!result.ok) throw new Error(result.error);
      const small = await shrinkImage(file);
      if (small) {
        await fetch("/api/upload", {
          method: "POST",
          headers: { "X-Token": TOKEN, "X-Small-For": encodeURIComponent(result.path) },
          body: small,
        }).catch(() => null);
      }
      entry.path = result.path;
      entry.uploading = false;
    } catch (error) {
      S.attachments.splice(S.attachments.indexOf(entry), 1);
      toast(errText(error && error.message));
    }
    renderAttachments();
  }
}

function setupComposer() {
  const input = $("input");
  input.addEventListener("input", autosize);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      send();
    }
  });
  input.addEventListener("paste", (e) => {
    const files = Array.from(e.clipboardData ? e.clipboardData.files : []);
    if (files.length) { e.preventDefault(); addFiles(files); }
  });
  $("sendBtn").addEventListener("click", send);
  $("attachBtn").addEventListener("click", () => $("fileInput").click());
  $("fileInput").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });
  $("carefulToggle").addEventListener("change", (e) => api("settings", { careful: e.target.checked }));

  let depth = 0;
  window.addEventListener("dragenter", (e) => {
    if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes("Files")) return;
    depth++;
    $("dropOverlay").hidden = false;
  });
  window.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) $("dropOverlay").hidden = true; });
  window.addEventListener("dragover", (e) => e.preventDefault());
  window.addEventListener("drop", (e) => {
    e.preventDefault();
    depth = 0;
    $("dropOverlay").hidden = true;
    if (e.dataTransfer && e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
  });
}

/* --------------------------------------------------------------- modals */

function modal(content, { big = false, closable = true } = {}) {
  const box = h("div", { class: "modal" + (big ? " big" : "") });
  const overlay = h("div", { class: "overlay" }, box);
  const close = () => { overlay.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape" && closable) close(); };
  if (closable) overlay.addEventListener("mousedown", (e) => { if (e.target === overlay) close(); });
  document.addEventListener("keydown", onKey);
  $("modalRoot").append(overlay);
  if (content) box.append(...[content].flat());
  return { box, close };
}

function confirmModal(title, body, okLabel, onOk) {
  const m = modal([
    h("h2", { text: title }),
    ...[body].flat().map((b) => (b instanceof Node ? b : h("p", { class: "lead", text: b }))),
    h("div", { class: "modal-foot" }, h("div", { class: "right" },
      h("button", { class: "btn", text: t("confirm.cancel"), onclick: () => m.close() }),
      h("button", { class: "btn danger", text: okLabel, onclick: () => { m.close(); onOk(); } }))),
  ]);
}

/* ------------------------------------------------- shared settings fields */

// An address with a "check" button; saved only once the check succeeds.
function checkedField({ label, desc, value, placeholder, check, save, okText }) {
  const input = h("input", { class: "input", value: value || "", placeholder, autocomplete: "off", spellcheck: "false" });
  const status = h("div", { style: "margin-top:6px;font-size:13px" });
  const run = async () => {
    status.replaceChildren(h("span", { class: "muted", text: t("setup.cloud.checking") }));
    const result = await check(input.value.trim());
    if (!result.ok) {
      status.replaceChildren(h("div", { class: "err-text", text: errText(result.error) }),
        result.detail ? h("small", { class: "muted", text: result.detail }) : null);
      return;
    }
    await save(result);
    status.replaceChildren(h("span", { class: "ok-text", html: icon("check") + escapeHtml(okText(result)) }));
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
  return h("div", { class: "field" }, label ? h("label", { text: label }) : null,
    h("div", { class: "row" }, input, h("button", { class: "btn", text: t("settings.check"), onclick: run })),
    desc ? h("small", { text: desc }) : null, status);
}

function ollamaHostField(onSaved) {
  return checkedField({
    label: t("settings.ollama_host"), desc: t("settings.ollama_host.desc"),
    value: settingsNow().ollama_host, placeholder: "http://127.0.0.1:11434",
    check: (host) => api("ollama/test", { host }),
    save: async (result) => { await api("settings", { ollama_host: result.host }); await refreshState(); if (onSaved) onSaved(); },
    okText: (result) => t("settings.check.ok", { version: result.version || "?" }),
  });
}

/* ----------------------------------------------------------------- setup */

const CLOUD = {
  gemini: { name: "Gemini (Google)", url: "https://aistudio.google.com/app/apikey", note: "setup.cloud.gemini.free" },
  anthropic: { name: "Claude (Anthropic)", url: "https://console.anthropic.com/settings/keys" },
  openai: { name: "ChatGPT (OpenAI)", url: "https://platform.openai.com/api-keys" },
};

function openSetup(startStep = 0) {
  const s = settingsNow();
  const W = {
    step: startStep,
    agreed: !!s.accepted_terms,
    engine: s.provider === "ollama" || !s.provider ? "local" : "cloud",
    cloud: s.provider && s.provider !== "ollama" ? s.provider : "gemini",
    cloudModels: [], cloudModel: "", cloudOk: false, cloudError: "",
    model: s.models && s.models.ollama || "", status: null, sizes: {}, job: null,
    folder: s.work_folder || (S.state && S.state.default_folder) || "",
  };
  if (W.step === 3 && W.engine === "cloud") W.step = 2;
  const m = modal(null, { big: true, closable: !!s.setup_done });
  let poll = null;

  const STEPS = 5; // welcome, terms, engine, local|cloud, folder
  const go = (step) => { W.step = step; draw(); };
  const foot = (canNext, onNext, nextLabel) => h("div", { class: "modal-foot" },
    W.step > 0 ? h("button", { class: "btn ghost", text: t("setup.back"), onclick: () => go(W.step - 1) }) : h("span"),
    h("div", { class: "right" }, h("button", { class: "btn primary", disabled: !canNext, text: nextLabel || t("setup.next"), onclick: onNext })));
  const steps = () => h("div", { class: "steps" }, ...Array.from({ length: STEPS }, (_, i) => h("i", { class: i <= W.step ? "on" : "" })));

  function draw() {
    clearInterval(poll);
    window.onJobEvent = null;
    const body = [steps()];
    if (W.step === 0) body.push(...stepWelcome());
    if (W.step === 1) body.push(...stepTerms());
    if (W.step === 2) body.push(...stepEngine());
    if (W.step === 3) body.push(...(W.engine === "local" ? stepLocal() : stepCloud()));
    if (W.step === 4) body.push(...stepFolder());
    m.box.replaceChildren(...body);
  }

  function stepWelcome() {
    const lang = h("select", { class: "input", style: "width:auto" },
      h("option", { value: "auto", text: t("lang.auto") }), h("option", { value: "ko", text: "한국어" }), h("option", { value: "en", text: "English" }));
    lang.value = settingsNow().language || "auto";
    lang.addEventListener("change", async () => { await api("settings", { language: lang.value }); await refreshState(); draw(); });
    return [
      h("div", { class: "hero" }, h("img", { src: "icon.svg", alt: "" }), h("h2", { text: t("setup.welcome.title") }), h("p", { class: "lead", text: t("setup.welcome.body") })),
      h("ul", { class: "features" },
        h("li", { html: icon("sparkle") + escapeHtml(t("setup.welcome.f1")) }),
        h("li", { html: icon("undo") + escapeHtml(t("setup.welcome.f2")) }),
        h("li", { html: icon("lock") + escapeHtml(t("setup.welcome.f3")) })),
      h("div", { class: "row" }, h("span", { class: "muted", text: t("setup.language") }), lang),
      foot(true, () => go(1)),
    ];
  }

  function stepTerms() {
    const box = h("input", { type: "checkbox" });
    box.checked = W.agreed;
    const next = foot(W.agreed, () => go(2));
    box.addEventListener("change", () => { W.agreed = box.checked; next.querySelector(".btn.primary").disabled = !W.agreed; });
    return [
      h("h2", { text: t("setup.terms.title") }),
      h("ul", { class: "terms" }, ...[1, 2, 3, 4, 5].map((n) => h("li", { html: icon(["folder", "terminal", "cloud", "alert", "book"][n - 1]) + `<span>${escapeHtml(t("setup.terms." + n))}</span>` }))),
      h("label", { class: "check" }, box, t("setup.terms.agree")),
      next,
    ];
  }

  function stepEngine() {
    const card = (key, ic) => h("button", { class: "choice" + (W.engine === key ? " sel" : ""), onclick: () => { W.engine = key; draw(); } },
      h("div", { class: "c-icon", html: icon(ic) }), h("b", { text: t(`setup.engine.${key}`) }), h("span", { text: t(`setup.engine.${key}.desc`) }));
    return [
      h("h2", { text: t("setup.engine.title") }),
      h("p", { class: "lead", text: t("setup.engine.lead") }),
      h("div", { class: "choice-grid" }, card("local", "chip"), card("cloud", "cloud")),
      foot(true, async () => { await api("settings", { accepted_terms: true }); go(3); }),
    ];
  }

  /* -- local -- */
  function stepLocal() {
    const area = h("div");
    const refresh = async () => {
      W.status = await api("ollama/status");
      paintLocal(area);
      if (W.status && W.status.running) {
        for (const choice of W.status.choices || []) {
          if (W.sizes[choice.id] === undefined) {
            W.sizes[choice.id] = null;
            api("ollama/size?model=" + encodeURIComponent(choice.id)).then((r) => { W.sizes[choice.id] = r.bytes || 0; paintLocal(area); });
          }
        }
      }
    };
    window.onJobEvent = (event) => { W.job = event; paintLocal(area); if (["done", "failed", "cancelled", "manual"].includes(event.stage)) refresh(); };
    const jobs = (S.state && S.state.jobs) || {};
    if (!W.job && (jobs.pull || jobs.install) && S.state.job_running) W.job = jobs.pull || jobs.install;
    refresh();
    poll = setInterval(refresh, 4000);
    return [h("h2", { text: t("setup.local.title") }), area];
  }

  function paintLocal(area) {
    const st = W.status;
    if (!st) { area.replaceChildren(h("div", { class: "progress indeterminate" }, h("div"))); return; }
    const nodes = [];
    const job = W.job;
    // engine row
    let engineText, engineCls = "todo", engineActs = [];
    if (st.running) { engineText = st.local === false ? t("setup.local.remote", { host: st.host }) : t("setup.local.engine.ok"); engineCls = "ok"; }
    else if (st.local === false) engineText = t("setup.local.remote.off", { host: st.host });
    else if (st.installed) {
      engineText = t("setup.local.engine.off");
      engineActs.push(h("button", { class: "btn small primary", html: icon("power") + escapeHtml(t("setup.local.start")), onclick: async (e) => { e.target.disabled = true; await api("ollama/start", {}); refreshLocal(); } }));
    } else {
      engineText = t("setup.local.engine.missing");
      if (st.can_install) engineActs.push(h("button", { class: "btn small primary", disabled: job && job.type === "install" && !["failed", "done", "manual"].includes(job.stage), html: icon("download") + escapeHtml(t("setup.local.install")), onclick: () => { W.job = { type: "install", stage: "download", completed: 0, total: 0 }; api("ollama/install", {}); paintLocal(area); } }));
      engineActs.push(h("button", { class: "btn small", html: icon("external") + escapeHtml(t("setup.local.installpage")), onclick: () => openUrl("https://ollama.com/download") }));
    }
    nodes.push(h("div", { class: "status-row " + engineCls }, h("span", { class: "sicon", html: icon(engineCls === "ok" ? "check" : "chip") }),
      h("div", { class: "stext" }, h("b", { text: t("setup.local.engine") }), h("small", { text: engineText })), ...engineActs));
    if (W.hostOpen === undefined) W.hostOpen = st.local === false && !st.running;
    const hostBox = h("details", { style: "margin:8px 0 4px", open: W.hostOpen },
      h("summary", { class: "muted", text: t("setup.local.host") }),
      ollamaHostField(() => { W.sizes = {}; refreshLocal(); }));
    hostBox.addEventListener("toggle", () => { W.hostOpen = hostBox.open; });
    nodes.push(hostBox);
    if (job && job.type === "install" && !st.running) {
      const text = { download: t("setup.local.downloading"), verify: t("setup.local.verifying"), installer: t("setup.local.installer"), unpack: t("setup.local.waiting"), waiting: t("setup.local.waiting"), manual: t("setup.local.manual"), failed: t("setup.local.failed") }[job.stage] || "";
      const pct = job.total ? Math.round((job.completed / job.total) * 100) : 0;
      nodes.push(h("div", { class: "howto" }, h("div", { text: text + (job.stage === "download" && job.total ? ` ${pct}%` : "") }),
        ["download", "verify", "waiting", "installer", "unpack"].includes(job.stage) ? h("div", { class: "progress" + (job.total && job.stage === "download" ? "" : " indeterminate") }, h("div", { style: `width:${pct}%` })) : null,
        job.detail ? h("small", { class: "muted", text: job.detail }) : null));
    }
    // model section
    if (st.running) {
      nodes.push(h("h3", { text: t("setup.local.model") }), h("p", { class: "muted", style: "margin:0 0 10px;font-size:13px", text: t("setup.local.ram", { ram: st.ram_gb }) }));
      const installed = st.models || [];
      const choices = (st.choices || []).map((c) => c.id);
      const pulling = job && job.type === "pull" && job.stage === "download";
      const options = (st.choices || []).map((c) => {
        const have = installed.includes(c.id) || installed.includes(c.id + ":latest");
        const size = W.sizes[c.id];
        return h("button", { class: "model-opt" + (W.model === c.id ? " sel" : ""), onclick: () => { W.model = c.id; paintLocal(area); } },
          h("span", { html: icon("chip") }),
          h("span", { class: "mtext" },
            h("b", {}, t("setup.local.tier." + c.tier), h("span", { class: "muted", style: "font-weight:500", text: ` · ${c.id}` }),
              c.id === st.recommended ? h("span", { class: "tag", text: t("setup.local.forpc") }) : null,
              have ? h("span", { class: "tag ok", text: t("setup.local.installed") }) : null),
            h("small", { text: t(`setup.local.tier.${c.tier}.desc`) + (size ? ` · ${t("setup.local.size", { size: formatBytes(size) })}` : "") })));
      });
      for (const name of installed) {
        if (choices.includes(name) || choices.includes(name.replace(/:latest$/, ""))) continue;
        options.push(h("button", { class: "model-opt" + (W.model === name ? " sel" : ""), onclick: () => { W.model = name; paintLocal(area); } },
          h("span", { html: icon("chip") }), h("span", { class: "mtext" }, h("b", {}, name, h("span", { class: "tag ok", text: t("setup.local.installed") })))));
      }
      if (!W.model) W.model = installed.find((n) => choices.includes(n)) || st.recommended;
      nodes.push(h("div", { class: "models" }, ...options));
      const custom = h("input", { class: "input", placeholder: "e.g. qwen3:8b", value: choices.includes(W.model) || installed.includes(W.model) ? "" : W.model });
      custom.addEventListener("change", () => { if (custom.value.trim()) { W.model = custom.value.trim(); paintLocal(area); } });
      nodes.push(h("details", { style: "margin-top:10px" }, h("summary", { class: "muted", text: t("setup.local.custom") }), h("div", { class: "field" }, custom)));
      if (job && job.type === "pull") {
        const pct = job.total ? Math.round((job.completed / job.total) * 100) : 0;
        const label = job.stage === "done" ? t("setup.local.pull.done") : job.stage === "failed" ? `${t("setup.local.pull.failed")}: ${job.detail || ""}`
          : t("setup.local.pulling", { done: formatBytes(job.completed || 0), total: job.total ? formatBytes(job.total) : "?" });
        nodes.push(h("div", { class: "howto", style: "margin-top:12px" }, h("div", { class: job.stage === "failed" ? "err-text" : "", text: `${job.model || ""} — ${label}` }),
          job.stage === "download" ? h("div", { class: "progress" + (job.total ? "" : " indeterminate") }, h("div", { style: `width:${pct}%` })) : null,
          job.stage === "download" ? h("button", { class: "btn small", text: t("setup.local.cancel"), onclick: () => api("job/cancel", {}) }) : null));
      }
      const have = installed.includes(W.model) || installed.includes(W.model + ":latest");
      const actions = h("div", { class: "modal-foot" },
        h("button", { class: "btn ghost", text: t("setup.back"), onclick: () => go(2) }),
        h("div", { class: "right" }, have
          ? h("button", { class: "btn primary", text: t("setup.next"), onclick: async () => { await api("provider/use", { provider: "ollama", model: W.model }); await refreshState(); go(4); } })
          : h("button", { class: "btn primary", disabled: pulling, html: icon("download") + escapeHtml(t("setup.local.get")), onclick: () => { W.job = { type: "pull", model: W.model, stage: "download", completed: 0, total: 0 }; api("ollama/pull", { model: W.model }); paintLocal(area); } })));
      nodes.push(actions);
    } else {
      nodes.push(h("div", { class: "modal-foot" }, h("button", { class: "btn ghost", text: t("setup.back"), onclick: () => go(2) }), h("span")));
    }
    const focused = document.activeElement;
    const keepFocus = focused && area.contains(focused) && focused.tagName === "INPUT";
    if (keepFocus) return;   // do not repaint under someone typing
    area.replaceChildren(...nodes);

    function refreshLocal() { api("ollama/status").then((r) => { W.status = r; paintLocal(area); }); }
  }

  /* -- cloud -- */
  function stepCloud() {
    const info = CLOUD[W.cloud];
    const hasKey = S.state && S.state.keys && S.state.keys[W.cloud];
    const key = h("input", { class: "input", type: "password", placeholder: hasKey ? t("setup.cloud.key.saved") : t("setup.cloud.key.paste"), autocomplete: "off" });
    const status = h("div");
    const modelSelect = h("select", { class: "input" });
    const nextBtn = h("button", { class: "btn primary", disabled: !W.cloudOk, text: t("setup.next"), onclick: async () => {
      await api("provider/use", { provider: W.cloud, model: modelSelect.value || W.cloudModel });
      await refreshState();
      go(4);
    } });
    const fillModels = () => {
      modelSelect.replaceChildren(...W.cloudModels.map((name) => h("option", { value: name, text: name })));
      modelSelect.value = W.cloudModel;
    };
    const check = async () => {
      status.replaceChildren(h("span", { class: "muted", text: t("setup.cloud.checking") }));
      const result = await api("provider/test", { provider: W.cloud, key: key.value.trim() });
      if (result.ok) {
        W.cloudOk = true; W.cloudModels = result.models || []; W.cloudModel = result.suggested || W.cloudModels[0] || "";
        status.replaceChildren(h("span", { class: "ok-text", html: icon("check") + escapeHtml(t("setup.cloud.ok")) }));
        fillModels();
        modelField.hidden = false;
        await refreshState();
      } else {
        W.cloudOk = false;
        const code = result.error || "other";
        status.replaceChildren(h("div", { class: "err-text", text: errText(code) }),
          result.detail ? h("small", { class: "muted", text: result.detail }) : null);
      }
      nextBtn.disabled = !W.cloudOk;
    };
    const modelField = h("div", { class: "field", hidden: !W.cloudOk }, h("label", { text: t("setup.cloud.model") }), modelSelect);
    if (W.cloudOk) fillModels();
    if (hasKey && !W.cloudOk) setTimeout(check, 0);
    return [
      h("h2", { text: t("setup.cloud.title") }),
      h("div", { class: "tabs" }, ...Object.entries(CLOUD).map(([id, c]) => h("button", {
        class: W.cloud === id ? "sel" : "", text: c.name,
        onclick: () => { W.cloud = id; W.cloudOk = false; W.cloudModels = []; draw(); },
      }))),
      info.note ? h("p", { class: "ok-text", style: "margin:0 0 10px;font-size:13.5px", text: t(info.note) }) : null,
      h("div", { class: "howto" }, h("b", { text: t("setup.cloud.how") }),
        h("ol", {}, h("li", { text: t("setup.cloud.step1") }), h("li", { text: t("setup.cloud.step2") }), h("li", { text: t("setup.cloud.step3") })),
        h("button", { class: "btn small", html: icon("external") + escapeHtml(t("setup.cloud.open")), onclick: () => openUrl(info.url) })),
      h("div", { class: "field" }, h("label", { text: t("setup.cloud.key") }),
        h("div", { class: "row" }, key, h("button", { class: "btn", text: t("setup.cloud.check"), onclick: check }))),
      status,
      modelField,
      h("div", { class: "modal-foot" }, h("button", { class: "btn ghost", text: t("setup.back"), onclick: () => go(2) }), h("div", { class: "right" }, nextBtn)),
    ];
  }

  /* -- folder -- */
  function stepFolder() {
    const box = h("div", { class: "folder-box", html: icon("folder") + `<span>${escapeHtml(W.folder)}</span>` });
    return [
      h("h2", { text: t("setup.folder.title") }),
      h("p", { class: "lead", text: t("setup.folder.body") }),
      box,
      h("div", { class: "row", style: "margin-top:10px" },
        h("button", { class: "btn", html: icon("folder") + escapeHtml(t("setup.folder.choose")), onclick: async () => {
          const picked = await api("pick_folder", { initial: W.folder });
          if (picked.path) { W.folder = picked.path; draw(); }
        } }),
        h("span", { class: "muted", style: "font-size:13px", text: t("setup.folder.tip") })),
      foot(true, async () => {
        await api("settings", { work_folder: W.folder, setup_done: true, accepted_terms: true });
        await refreshState();
        clearInterval(poll);
        window.onJobEvent = null;
        m.close();
        pollOllama();
        if (!S.conv || !S.conv.ui || !S.conv.ui.length) renderThread();
      }, t("setup.done")),
    ];
  }

  const originalClose = m.close;
  m.close = () => { clearInterval(poll); window.onJobEvent = null; originalClose(); };
  draw();
}

/* -------------------------------------------------------------- settings */

// Settings open in the main area, in place of the chat (like a desktop app's
// preferences page), with their sections listed down the left.
const SETTINGS_SECTIONS = [
  ["general", "gear"], ["ai", "chip"], ["memory", "book"], ["usage", "table"], ["storage", "trash"], ["about", "info"],
];
const SETTINGS_PAGES = {};

function settingsOpen() { return !$("settingsView").hidden; }

function hideSettings() {
  if (!settingsOpen()) return;
  $("settingsView").hidden = true;
  $("settingsView").replaceChildren();
  for (const id of ["topbar", "messages", "composer"]) $(id).hidden = false;
  $("openSettings").classList.remove("sel");
}

function closeSettings() {
  hideSettings();
  if (S.convId) openConversation(S.convId); else renderThread();
}

function openSettings(tab = "general") {
  closeMenus();
  for (const id of ["topbar", "messages", "composer"]) $(id).hidden = true;
  $("settingsView").hidden = false;
  $("openSettings").classList.add("sel");
  if (window.innerWidth <= 900) $("app").classList.add("collapsed");
  let current = SETTINGS_SECTIONS.some(([id]) => id === tab) ? tab : "general";
  let choosingSearxng = false;
  const m = { close: closeSettings };

  const draw = () => {
    if (!settingsOpen()) return;
    const nav = h("nav", { class: "settings-nav" }, ...SETTINGS_SECTIONS.map(([id, ic]) =>
      h("button", { class: current === id ? "sel" : "", html: icon(ic) + `<span>${escapeHtml(t("settings.page." + id))}</span>`, onclick: () => { current = id; draw(); } })));
    const body = (SETTINGS_PAGES[current] || general)();
    $("settingsView").replaceChildren(
      h("header", { class: "settings-head" },
        h("button", { class: "icon-btn", title: t("settings.back"), html: icon("back"), onclick: closeSettings }),
        h("h1", { text: t("settings.title") })),
      h("div", { class: "settings-body" }, nav,
        h("div", { class: "settings-page" }, h("h2", { text: t("settings.page." + current) }), ...body)));
  };
  window.redrawSettings = draw;

  const select = (options, value, onChange) => {
    const node = h("select", { class: "input" }, ...options.map(([v, label]) => h("option", { value: v, text: label })));
    node.value = value;
    node.addEventListener("change", () => onChange(node.value));
    return node;
  };

  function general() {
    const s = settingsNow();
    return [
      h("div", { class: "field" }, h("label", { text: t("settings.language") }),
        select([["auto", t("lang.auto")], ["ko", "한국어"], ["en", "English"]], s.language || "auto", async (v) => { await api("settings", { language: v }); await refreshState(); renderThread(); draw(); })),
      h("div", { class: "field" }, h("label", { text: t("settings.theme") }),
        select([["auto", t("settings.theme.auto")], ["light", t("settings.theme.light")], ["dark", t("settings.theme.dark")]], s.theme || "auto", async (v) => { await api("settings", { theme: v }); await refreshState(); })),
      h("div", { class: "field" }, h("label", { text: t("settings.safety") }),
        h("div", { class: "seg" }, ...["ask", "balanced", "auto"].map((level) => h("button", {
          class: (s.safety || "balanced") === level ? "sel" : "",
          onclick: async () => { await api("settings", { safety: level }); await refreshState(); draw(); },
        }, h("div", { class: "opt-title", text: t("safety." + level) }), h("div", { class: "opt-desc", text: t(`safety.${level}.desc`) }))))),
      commandsField(s),
      ...searchFields(s),
    ];
  }

  function commandsField(s) {
    const box = h("input", { type: "checkbox" });
    box.checked = !!s.allow_commands;
    box.addEventListener("change", async () => { await api("settings", { allow_commands: box.checked }); await refreshState(); toast(t("settings.saved")); });
    return h("div", { class: "field" },
      h("label", { class: "switch" }, box, h("span", { class: "track" }, h("span", { class: "thumb" })), h("span", { text: t("settings.commands") })),
      h("small", { text: t("settings.commands.desc") }));
  }

  function searchFields(s) {
    const engine = choosingSearxng ? "searxng" : (s.search_engine || "auto");
    const nodes = [h("div", { class: "field" }, h("label", { text: t("settings.search") }),
      select([["auto", t("settings.search.auto")], ["searxng", t("settings.search.searxng")]], engine, async (v) => {
        // SearXNG is switched on only once its address has been checked.
        choosingSearxng = v === "searxng" && !s.searxng_url;
        if (!choosingSearxng) {
          await api("settings", { search_engine: v });
          await refreshState();
          toast(t("settings.saved"));
        }
        draw();
      }))];
    if (engine === "searxng") {
      nodes.push(checkedField({
        label: t("settings.searxng_url"), desc: t("settings.searxng_url.desc"),
        value: s.searxng_url, placeholder: "http://192.168.0.10:8080",
        check: (url) => api("search/test", { url }),
        save: async (result) => {
          choosingSearxng = false;
          await api("settings", { searxng_url: result.url, search_engine: "searxng" });
          await refreshState();
        },
        okText: (result) => t("settings.search.ok", { count: result.count }),
      }));
    }
    return nodes;
  }

  function ai() {
    const s = settingsNow();
    const label = s.provider === "ollama" ? `${t("settings.local")} (Ollama)` : S.state.provider_label;
    const modelSelect = h("select", { class: "input" }, h("option", { value: S.state.model, text: S.state.model || "…" }));
    modelSelect.value = S.state.model;
    modelSelect.addEventListener("change", async () => {
      await api("provider/use", { provider: s.provider, model: modelSelect.value });
      await refreshState();
      toast(t("settings.saved"));
    });
    const load = s.provider === "ollama"
      ? api("ollama/status").then((r) => r.models || [])
      : api("provider/test", { provider: s.provider }).then((r) => r.models || []);
    load.then((models) => {
      if (!models.length) return;
      if (!models.includes(S.state.model) && S.state.model) models.unshift(S.state.model);
      modelSelect.replaceChildren(...models.map((name) => h("option", { value: name, text: name })));
      modelSelect.value = S.state.model;
    });
    const nodes = [
      h("div", { class: "status-row ok" }, h("span", { class: "sicon", html: icon(s.provider === "ollama" ? "chip" : "cloud") }),
        h("div", { class: "stext" }, h("b", { text: label }), h("small", { text: S.state.model || "" })),
        h("button", { class: "btn small", text: t("settings.change_ai"), onclick: () => { m.close(); openSetup(2); } })),
      h("div", { class: "field" }, h("label", { text: t("settings.model") }), modelSelect),
    ];
    if (s.provider === "ollama") {
      nodes.push(h("div", { class: "field" }, h("label", { text: t("settings.memory") }),
        select([["8192", "8K"], ["16384", "16K"], ["32768", "32K"], ["65536", "64K"]], String(s.context_tokens || 16384),
          async (v) => { await api("settings", { context_tokens: Number(v) }); await refreshState(); toast(t("settings.saved")); }),
        h("small", { text: t("settings.memory.desc") })));
      nodes.push(ollamaHostField(() => { pollOllama(); draw(); }));
    } else if (S.state.keys && S.state.keys[s.provider]) {
      nodes.push(h("div", { class: "row", style: "margin-top:12px" },
        h("button", { class: "btn small", html: icon("key") + escapeHtml(t("settings.key.forget")), onclick: () =>
          confirmModal(t("settings.key.forget"), [S.state.provider_label], t("settings.key.forget"), async () => {
            await api("provider/forget", { provider: s.provider });
            await refreshState();
            toast(t("settings.key.forgot"));
            draw();
          }) })));
    }
    return nodes;
  }

  function memoryTab() {
    const s = settingsNow();
    const box = h("input", { type: "checkbox" });
    box.checked = s.memory !== false;
    box.addEventListener("change", async () => { await api("settings", { memory: box.checked }); await refreshState(); toast(t("settings.saved")); });
    const items = (S.state && S.state.memories) || [];
    const forget = (id) => async () => {
      const result = await api("memory/delete", { id });
      if (result.memories) S.state.memories = result.memories;
      draw();
    };
    return [
      h("div", { class: "field" },
        h("label", { class: "switch" }, box, h("span", { class: "track" }, h("span", { class: "thumb" })), h("span", { text: t("settings.mem.toggle") })),
        h("small", { text: t("settings.mem.desc") })),
      items.length
        ? h("div", { class: "memories" }, ...items.map((item) => h("div", { class: "change-row" },
          h("span", { class: "name", text: item.text }),
          h("span", { class: "row-acts" }, h("button", { class: "btn small ghost", html: icon("trash") + escapeHtml(t("settings.mem.delete")), onclick: forget(item.id) })))))
        : h("p", { class: "muted", text: t("settings.mem.empty") }),
      items.length ? h("div", { class: "row", style: "margin-top:12px" }, h("button", { class: "btn small", text: t("settings.mem.clear"), onclick: () =>
        confirmModal(t("settings.mem.clear"), t("settings.mem.clear.body"), t("settings.mem.clear"), async () => {
          const result = await api("memory/clear", {});
          if (result.memories) S.state.memories = result.memories;
          draw();
        }) })) : null,
    ];
  }

  Object.assign(SETTINGS_PAGES, { general, ai, memory: memoryTab, usage: usagePage, storage: storagePage, about });

  function storagePage() {
    const s = settingsNow();
    const sizes = h("div", { class: "kv" }, h("span", { class: "muted", text: t("model.loading") }));
    const load = () => api("storage").then((r) => {
      sizes.replaceChildren(
        h("span", { text: t("storage.history") }), h("span", { class: "v", text: `${formatBytes(r.history.bytes)} · ${t("storage.sets", { n: r.history.sets })}` }), h("span"),
        h("span", { text: t("storage.attachments") }), h("span", { class: "v", text: formatBytes(r.attachments) }), h("span"));
    });
    load();
    const prune = (all) => async () => {
      const result = await api("storage/prune", { all });
      toast(t("storage.pruned", { n: result.removed || 0 }));
      load();                     // the chat is drawn again, without those Undo buttons, on the way back
    };
    return [
      h("p", { class: "lead muted", text: t("storage.lead") }),
      sizes,
      h("div", { class: "field" }, h("label", { text: t("storage.keep") }),
        select([["7", t("storage.days", { n: 7 })], ["30", t("storage.days", { n: 30 })], ["90", t("storage.days", { n: 90 })],
          ["365", t("storage.days", { n: 365 })], ["0", t("storage.forever")]], String(s.history_days ?? 90),
          async (v) => { await api("settings", { history_days: Number(v) }); await refreshState(); toast(t("settings.saved")); }),
        h("small", { text: t("storage.keep.desc") })),
      h("div", { class: "row", style: "margin-top:12px; flex-wrap: wrap" },
        h("button", { class: "btn small", text: t("storage.prune.old"), onclick: prune(false) }),
        h("button", { class: "btn small", text: t("storage.prune.all"), onclick: () =>
          confirmModal(t("storage.prune.all"), t("storage.prune.all.body"), t("storage.prune.all"), prune(true)) })),
    ];
  }

  function usagePage() {
    const area = h("div", {}, h("p", { class: "muted", text: t("model.loading") }));
    api("usage").then((result) => {
      const months = (result && result.months) || [];
      if (!months.length) { area.replaceChildren(h("p", { class: "muted", text: t("usage.none") })); return; }
      area.replaceChildren(...months.slice(0, 6).map((month) => h("div", { class: "usage-month" },
        h("h3", { text: month.month }),
        h("div", { class: "md" }, h("div", { class: "table-wrap" }, h("table", {},
          h("thead", {}, h("tr", {}, ...[t("usage.col.model"), t("usage.col.requests"), t("usage.col.input"), t("usage.col.output")].map((c) => h("th", { text: c })))),
          h("tbody", {}, ...month.items.map((item) => h("tr", {},
            h("td", { title: item.model }, h("b", { text: shortModel(item.model) }), h("div", { class: "muted", text: PROVIDER_LABELS[item.provider] || item.provider })),
            h("td", { text: item.requests.toLocaleString() }),
            h("td", { text: item.input.toLocaleString() }),
            h("td", { text: item.output.toLocaleString() }))))))))));
    });
    return [h("p", { class: "lead muted", text: t("usage.lead") }), area];
  }

  function about() {
    return [
      h("div", { class: "hero" }, h("img", { src: "icon.svg", alt: "" }), h("h2", { text: "Aetheris Everyone" }), h("p", { class: "lead", text: t("app.tagline") })),
      h("div", { class: "kv" },
        h("span", { text: t("settings.version") }), h("span", { class: "v", text: S.state.version }), h("span"),
        h("span", { text: t("settings.data") }), h("span", { class: "v", text: S.state.data_dir || "" }),
        h("button", { class: "btn small", text: t("settings.open"), onclick: () => api("reveal", { path: S.state.data_dir }) }),
        h("span", { text: t("settings.keys") }), h("span", { class: "v", text: t("settings.keys." + (S.state.key_storage || "file")) }), h("span"),
        h("span", { text: "GitHub" }), h("span", { class: "v", text: "minjun1177/aetheris-everyone" }),
        h("button", { class: "btn small", html: icon("external"), onclick: () => openUrl("https://github.com/minjun1177/aetheris-everyone") })),
      S.state.can_shortcut ? h("div", { class: "row", style: "margin-top:16px" },
        h("button", { class: "btn small", html: icon("plus") + escapeHtml(t("settings.shortcut")), onclick: async () => {
          const r = await api("shortcut", {});
          toast(r.ok ? t("settings.shortcut.ok") : t("err.other"));
        } })) : null,
      h("p", { class: "muted", style: "font-size:13px;margin-top:18px", text: t("settings.based") + " · Apache-2.0" }),
    ];
  }

  draw();
}

/* ------------------------------------------------------------------ init */

async function init() {
  setupComposer();
  setupSelectBar();
  $("newChat").addEventListener("click", newChat);
  $("openSettings").addEventListener("click", () => (settingsOpen() ? closeSettings() : openSettings()));
  $("engineStatus").addEventListener("click", engineClicked);
  $("exportChat").addEventListener("click", exportChat);
  $("modelChip").addEventListener("click", (e) => { e.stopPropagation(); openModelMenu(); });
  $("toggleSidebar").addEventListener("click", () => $("app").classList.toggle("collapsed"));
  $("folderChip").addEventListener("click", (e) => { e.stopPropagation(); openFolderMenu(); });
  $("safetyChip").addEventListener("click", (e) => { e.stopPropagation(); openSafetyMenu(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && settingsOpen() && !$("modalRoot").children.length) closeSettings();
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".menu-wrap")) closeMenus();
    const link = e.target.closest("a[data-url]");
    if (link) { e.preventDefault(); openUrl(link.dataset.url); }
    const copy = e.target.closest(".copy-code");
    if (copy) copyText(copy.closest(".code").querySelector("code").textContent);
  });
  if (window.innerWidth <= 900) $("app").classList.add("collapsed");

  await refreshState();
  connectEvents();
  if (S.busy) await openConversation(S.busy);
  else renderThread();
  autosize();
  if (!settingsNow().setup_done) openSetup(0);
  else pollOllama();
  setInterval(pollOllama, 20000);
  $("input").focus();
}

init();

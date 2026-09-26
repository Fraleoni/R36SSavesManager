"use strict";

const element = (identifier) => document.getElementById(identifier);
const state = { csrf: "", systems: [], roms: [], selected: null, file: null, preview: null,
  page: 0, busy: false, demo: false, backup: null, result: null, error: null, language: "en", connected: false,
  autoState: null };
const pageSize = 8;
const catalogs = {};

function translate(key, parameters = {}) {
  const text = catalogs[state.language]?.[key] ?? catalogs.en?.[key] ?? key;
  return text.replace(/\{(\w+)\}/g, (placeholder, name) => String(parameters[name] ?? placeholder));
}

class LocalizedError extends Error {
  constructor(key, parameters = {}) {
    super(translate(key, parameters));
    this.key = key;
    this.parameters = parameters;
  }
}

function renderError() {
  element("error").hidden = !state.error;
  element("error").textContent = state.error ? translate(state.error.key || "request_failed", state.error.parameters) : "";
}

function showError(error) {
  state.error = error;
  renderError();
}

function clearError() { state.error = null; renderError(); }
function sizeLabel(size) { return size < 1024 ? `${size} B` : `${(size / 1024).toLocaleString(state.language, { maximumFractionDigits: 1 })} KiB`; }
function params(values) { return new URLSearchParams(values).toString(); }

function renderLanguage() {
  document.documentElement.lang = state.language;
  element("language").value = state.language;
  for (const attribute of ["text", "title", "aria-label", "placeholder"]) {
    const dataAttribute = attribute === "text" ? "data-i18n" : "data-i18n-" + attribute;
    for (const target of document.querySelectorAll("[" + dataAttribute + "]")) {
      const text = translate(target.getAttribute(dataAttribute));
      if (attribute === "text") target.textContent = text;
      else target.setAttribute(attribute, text);
    }
  }
  renderSystemLabels(); renderControls(); renderError();
}

function renderSystemLabels() {
  for (const option of element("system").options) {
    const system = state.systems.find((system) => system.id === option.value);
    option.textContent = system.available ? system.label : translate("unavailable", { label: system.label });
  }
}

async function fetchResponse(path, options = {}) {
  try {
    return await fetch(path, { ...options, credentials: "same-origin",
      headers: { ...options.headers, "X-Language": state.language } });
  } catch {
    throw new LocalizedError("network_error");
  }
}

function inputExtensions() {
  const system = state.systems.find((system) => system.id === element("system").value);
  return system?.input_extensions || (system ? [system.extension] : []);
}

function fileExtension(file) { return file.name.slice(file.name.lastIndexOf(".")).toLowerCase(); }

function authenticated(value) {
  if (!value) invalidateAutoState();
  element("login").hidden = value;
  element("app").hidden = !value;
  element("logout").hidden = !value || state.demo;
  element("initial").hidden = true;
}

async function request(path, options = {}) {
  const headers = { ...options.headers };
  if (options.method === "POST") headers["X-CSRF-Token"] = state.csrf;
  const response = await fetchResponse(path, { ...options, headers });
  const body = await response.json();
  if (!response.ok) {
    if (response.status === 401) authenticated(false);
    throw new LocalizedError(body.error_key || "request_failed", body.parameters);
  }
  return body;
}

function post(path, body) {
  return request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

function invalidate() {
  state.preview = null;
  element("preview").hidden = true;
  element("closed").checked = false;
  element("overwrite").checked = false;
  element("success").hidden = true;
  state.backup = null;
  state.result = null;
}

function invalidateAutoState() {
  state.autoState = null;
  element("autoStateClosed").checked = false;
  element("autoStateConfirm").checked = false;
}

function renderAutoState() {
  const preview = state.autoState;
  element("checkAutoState").disabled = state.busy || !state.selected;
  element("autoStateDetails").hidden = !preview;
  element("autoStateChecks").hidden = !preview?.exists;
  element("deleteAutoState").hidden = !preview?.exists;
  element("autoStateClosed").disabled = state.busy;
  element("autoStateConfirm").disabled = state.busy;
  element("deleteAutoState").disabled = state.busy || !preview?.exists
    || !element("autoStateClosed").checked || !element("autoStateConfirm").checked;
  element("autoStatePath").textContent = preview?.destination || "";
  element("autoStateStatus").textContent = preview
    ? translate(preview.deleted ? "auto_state_deleted" : preview.exists ? "auto_state_present" : "auto_state_missing") : "";
}

function renderControls() {
  for (const identifier of ["system", "search", "saveFile", "chooseFile", "language", "refresh", "logout", "downloadCurrent", "downloadBackup", "closed", "overwrite"]) {
    element(identifier).disabled = state.busy;
  }
  const extensions = inputExtensions();
  element("saveFile").accept = extensions.join(",");
  element("saveFileLabel").textContent = translate("file_types", { extensions: extensions.join(" / ") });
  element("previewButton").disabled = state.busy || !state.selected || !state.file
    || !extensions.includes(fileExtension(state.file));
  element("previewButton").textContent = translate(state.busy ? "busy" : "preview");
  element("importButton").disabled = state.busy || !state.preview || !element("closed").checked
    || (state.preview.exists && !element("overwrite").checked);
  element("selectedName").textContent = state.selected ? state.selected.rom : translate("no_rom");
  element("fileInfo").textContent = state.file ? `${state.file.name} / ${sizeLabel(state.file.size)}` : translate("no_file");
  element("mode").textContent = translate(state.connected ? (state.demo ? "demo" : "local_network") : "local");
  element("connection").textContent = state.demo ? translate("local_preview") : location.host;
  if (state.preview) {
    element("saveState").textContent = translate(state.preview.exists ? "existing_save" : "new_save", { size: sizeLabel(state.preview.size) });
    if (element("system").value === "psx") element("saveState").textContent += " / " + translate("whole_card");
  }
  if (state.result) {
    element("resultInfo").textContent = translate(state.result.backup ? "result_backup" : "result_new", { size: sizeLabel(state.result.bytes) });
  }
  renderAutoState(); renderRows();
}

function renderRows() {
  const search = element("search").value.trim().toLocaleLowerCase();
  const filtered = state.roms.filter((record) => record.rom.toLocaleLowerCase().includes(search));
  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  state.page = Math.min(state.page, pages - 1);
  element("count").textContent = translate("rom_count", { count: filtered.length.toLocaleString(state.language) });
  element("pageLabel").textContent = translate("page_count", { page: state.page + 1, pages });
  element("previous").disabled = state.busy || state.page === 0;
  element("next").disabled = state.busy || state.page + 1 >= pages;
  const list = element("romList");
  list.replaceChildren();
  if (state.busy && !state.roms.length) {
    const message = document.createElement("p"); message.className = "empty"; message.textContent = translate("loading_library"); list.append(message);
  } else if (!filtered.length) {
    const message = document.createElement("p"); message.className = "empty"; message.textContent = translate("empty_library"); list.append(message);
  }
  for (const record of filtered.slice(state.page * pageSize, (state.page + 1) * pageSize)) {
    const label = document.createElement("label");
    label.className = "rom-row" + (state.selected?.rom === record.rom ? " selected" : "");
    const radio = document.createElement("input");
    radio.type = "radio"; radio.name = "rom"; radio.value = record.rom;
    radio.checked = state.selected?.rom === record.rom; radio.disabled = state.busy;
    radio.addEventListener("change", () => {
      state.selected = record; invalidate(); invalidateAutoState(); clearError(); renderControls();
      Array.from(element("romList").querySelectorAll("input")).find((input) => input.value === record.rom)?.focus();
    });
    const text = document.createElement("span");
    const name = document.createElement("span"); name.className = "rom-name"; name.textContent = record.name;
    const detail = document.createElement("span"); detail.className = "rom-detail"; detail.textContent = record.rom;
    text.append(name, detail);
    const saved = document.createElement("span"); saved.className = record.saved ? "saved" : "unsaved";
    saved.textContent = translate(record.saved ? "present" : "absent");
    label.append(radio, text, saved); list.append(label);
  }
}

async function task(operation) {
  if (state.busy) return;
  state.busy = true; clearError(); renderControls();
  try { await operation(); } catch (error) { showError(error); }
  finally { state.busy = false; renderControls(); }
}

function suggestRom() {
  if (!state.file) return;
  const stem = state.file.name.replace(/\.(srm|sav|mcd|mcr)$/i, "").toLocaleLowerCase();
  const matches = state.roms.filter((record) => record.name.toLocaleLowerCase() === stem);
  if (matches.length === 1) {
    if (state.selected?.rom !== matches[0].rom) invalidateAutoState();
    state.selected = matches[0]; element("search").value = matches[0].name; state.page = 0;
  }
}

async function loadRoms() {
  invalidate(); invalidateAutoState(); state.roms = []; state.selected = null; state.page = 0;
  if (state.file && !inputExtensions().includes(fileExtension(state.file))) {
    state.file = null; element("saveFile").value = "";
  }
  element("search").value = ""; renderControls();
  if (!element("system").value) throw new LocalizedError("no_system");
  const response = await request("/api/roms?" + params({ system: element("system").value }));
  state.roms = response.roms; suggestRom();
}

async function loadSystems() {
  const response = await request("/api/systems"); state.systems = response.systems;
  element("system").replaceChildren();
  for (const system of state.systems) {
    const option = document.createElement("option"); option.value = system.id;
    option.disabled = !system.available; element("system").append(option);
  }
  renderSystemLabels();
  const available = state.systems.find((system) => system.available);
  if (available) element("system").value = available.id;
  await loadRoms();
}

async function download(path) {
  const response = await fetchResponse(path);
  if (!response.ok) {
    if (response.status === 401) authenticated(false);
    const body = await response.json(); throw new LocalizedError(body.error_key || "download_failed", body.parameters);
  }
  const blob = await response.blob(); const url = URL.createObjectURL(blob);
  const link = document.createElement("a"); link.href = url;
  const disposition = response.headers.get("Content-Disposition");
  link.download = disposition?.includes("UTF-8''") ? decodeURIComponent(disposition.split("UTF-8''")[1]) : "save.srm";
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

element("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault(); clearError(); element("loginButton").disabled = true;
  try {
    if (!element("password").value) throw new LocalizedError("invalid_password");
    const response = await post("/api/login", { password: element("password").value });
    state.csrf = response.csrf; element("password").value = ""; authenticated(true);
    await task(loadSystems);
  } catch (error) { showError(error); }
  finally { element("loginButton").disabled = false; }
});

element("logout").addEventListener("click", () => task(async () => {
  await post("/api/logout", {}); state.csrf = ""; invalidate(); authenticated(false);
}));
element("system").addEventListener("change", () => task(loadRoms));
element("refresh").addEventListener("click", () => task(loadRoms));
element("search").addEventListener("input", () => { state.page = 0; renderRows(); });
element("previous").addEventListener("click", () => { state.page--; renderRows(); });
element("next").addEventListener("click", () => { state.page++; renderRows(); });
element("closed").addEventListener("change", renderControls);
element("overwrite").addEventListener("change", renderControls);
element("autoStateClosed").addEventListener("change", renderControls);
element("autoStateConfirm").addEventListener("change", renderControls);
element("checkAutoState").addEventListener("click", () => task(async () => {
  invalidateAutoState();
  state.autoState = await post("/api/auto-state/preview", { system: element("system").value, rom: state.selected.rom });
}));
element("deleteAutoState").addEventListener("click", () => task(async () => {
  if (!state.autoState?.exists || !element("autoStateClosed").checked || !element("autoStateConfirm").checked) return;
  const ticket = state.autoState.ticket;
  invalidateAutoState();
  const result = await post("/api/auto-state/delete", { ticket, closed: true, confirmed: true });
  state.autoState = { ...result, exists: false };
}));
function selectSaveFiles(files) {
  if (state.busy || element("app").hidden) return;
  invalidate(); clearError(); state.file = files.length === 1 ? files[0] : null;
  if (files.length > 1) showError(new LocalizedError("one_file"));
  if (state.file && (!inputExtensions().includes(fileExtension(state.file)) || state.file.size === 0 || state.file.size > 16 * 1024 * 1024)) {
    showError(new LocalizedError("invalid_file", { extensions: inputExtensions().join(" / ") }));
    state.file = null;
  }
  if (state.file && [".mcd", ".mcr"].includes(fileExtension(state.file)) && state.file.size !== 131072) {
    showError(new LocalizedError("card_size"));
    state.file = null;
  }
  const selection = new DataTransfer();
  if (state.file) selection.items.add(state.file);
  element("saveFile").files = selection.files;
  suggestRom(); renderControls();
}

element("saveFile").addEventListener("change", () => selectSaveFiles(element("saveFile").files));
element("chooseFile").addEventListener("click", () => element("saveFile").click());
element("language").addEventListener("change", () => {
  state.language = element("language").value;
  try { localStorage.setItem("r36s-language", state.language); } catch {}
  renderLanguage();
});

let dragDepth = 0;
function resetDrag() {
  dragDepth = 0;
  element("upload").classList.remove("drag-active");
}
function isFileDrag(event) { return Array.from(event.dataTransfer?.types || []).includes("Files"); }
document.addEventListener("dragenter", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault(); dragDepth++;
  element("upload").classList.toggle("drag-active", !state.busy && !element("app").hidden);
});
document.addEventListener("dragover", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = state.busy || element("app").hidden ? "none" : "copy";
});
document.addEventListener("dragleave", () => {
  dragDepth = Math.max(0, dragDepth - 1);
  if (!dragDepth) resetDrag();
});
document.addEventListener("drop", (event) => {
  if (!isFileDrag(event)) return;
  event.preventDefault(); resetDrag();
  if (state.busy || element("app").hidden) return;
  if (Array.from(event.dataTransfer.items).some((item) => item.webkitGetAsEntry?.()?.isDirectory)) {
    selectSaveFiles([]);
    showError(new LocalizedError("not_folder"));
    return;
  }
  selectSaveFiles(event.dataTransfer.files);
});
document.addEventListener("dragend", resetDrag);
window.addEventListener("blur", resetDrag);

element("previewButton").addEventListener("click", () => task(async () => {
  invalidate();
  const extension = fileExtension(state.file);
  if ([".mcd", ".mcr"].includes(extension)) {
    const header = new Uint8Array(await state.file.slice(0, 128).arrayBuffer());
    const checksum = header.slice(0, 127).reduce((value, byte) => value ^ byte, 0);
    if (state.file.size !== 131072 || header[0] !== 77 || header[1] !== 67 || checksum !== header[127]) {
      throw new LocalizedError("card_invalid");
    }
  }
  state.preview = await post("/api/preview", { system: element("system").value, rom: state.selected.rom, extension });
  element("destination").textContent = state.preview.destination;
  element("saveState").classList.toggle("warning", state.preview.exists);
  element("overwriteLabel").hidden = !state.preview.exists;
  element("downloadCurrent").hidden = !state.preview.exists;
  element("preview").hidden = false;
}));

element("importButton").addEventListener("click", () => task(async () => {
  const system = element("system").value; const rom = state.selected.rom;
  const query = params({ ticket: state.preview.ticket, closed: "yes", overwrite: element("overwrite").checked ? "yes" : "no" });
  let result;
  try {
    result = await request("/api/import?" + query, { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: state.file });
  } catch (error) {
    invalidate(); throw error;
  }
  invalidate(); state.selected.saved = true; state.result = result;
  element("success").hidden = false;
  element("resultPath").textContent = result.destination;
  state.backup = result.backup_id ? "/api/backup?" + params({ system, rom, name: result.backup_id }) : null;
  element("downloadBackup").hidden = !state.backup;
}));
element("downloadCurrent").addEventListener("click", () => task(() => download("/api/save?" + params({ system: element("system").value, rom: state.selected.rom }))));
element("downloadBackup").addEventListener("click", () => task(() => download(state.backup)));

async function start() {
  try {
    const english = await fetch("/locales/en.json");
    if (!english.ok) throw new Error("catalog");
    catalogs.en = await english.json();
    try {
      const italian = await fetch("/locales/it.json");
      if (italian.ok) catalogs.it = await italian.json();
    } catch {}
  } catch {
    element("initial").textContent = "Cannot load translations. Reload the page to try again.";
    element("language").disabled = true;
    return;
  }
  try {
    const savedLanguage = localStorage.getItem("r36s-language");
    if (["en", "it"].includes(savedLanguage)) state.language = savedLanguage;
  } catch {}
  renderLanguage();
  try {
    const session = await request("/api/session"); state.csrf = session.csrf || ""; state.demo = session.demo;
    state.connected = true;
    element("mode").classList.toggle("demo", state.demo);
    renderControls();
    authenticated(session.authenticated);
    if (session.authenticated) await task(loadSystems);
  } catch (error) { element("initial").hidden = true; showError(error); }
}
start();
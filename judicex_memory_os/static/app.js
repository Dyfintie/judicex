const appEl = document.getElementById("app");
const state = {
  matters: [],
  activeMatterId: "",
  defaults: {},
  health: {},
  sidebarOpen: window.matchMedia("(min-width: 768px)").matches,
  recentUserTurns: [],
  lastResult: null,
  lastContext: null,
  visualizations: {},
  workflowPacks: [],
  tabularReviews: [],
  agentMemories: [],
  officialBundles: [],
  authStatus: {configured: false, authenticated: true},
  onboarding: {completed: false},
  chatSessions: [],
  llmSettings: null,
  llmModelOptions: {},
  llmModelOptionsCacheKey: {},
  llmModelOptionsStatus: {},
  activeChatSessionId: "",
  pendingDeleteChatSessionId: "",
  currentView: "",
  folders: [],
  draftTemplates: [],
  tools: [],
  activeDocumentId: "",
  currentDocument: null,
  lastEditId: "",
  activeReview: null,
  activeReviewFilter: "",
  activeReviewSortKey: "",
  pdfZoom: 1,
  pdfPage: 1,
  editingWorkflowId: "",
  pageWorkflow: {selectedId: "", thesis: "", label: "", requirements: "", status: "", output: "", editingId: ""},
  pageReview: {query: "", viewName: "", status: ""},
  pageDraft: {selectedId: "", asOfDate: "", instruction: "", params: "", title: "", paramList: "", body: "", status: "", preview: "", previewTitle: "", previewMeta: ""},
  pageTool: {selectedName: "", args: "", output: ""},
  pageSettings: {status: ""},
  pageSearch: {query: "", scope: "all", status: "", results: []},
  pageMemory: {query: "", kind: "preference", title: "", content: "", tags: "", status: "", editingId: ""},
  pageSources: {status: "", asOfDate: new Date().toISOString().slice(0, 10)},
  pageSecurity: {status: ""},
  pageBackup: {status: ""},
  artifacts: [],
  activeArtifact: null,
  messageCopies: {},
  messageCopySeq: 0,
};

const els = {
  sidebar: document.getElementById("sidebar"),
  sidebarToggle: document.getElementById("sidebarToggle"),
  sidebarClose: document.getElementById("sidebarClose"),
  sidebarBackdrop: document.getElementById("sidebarBackdrop"),
  mainShell: document.getElementById("mainShell"),
  healthBadge: document.getElementById("healthBadge"),
  primaryNav: document.getElementById("primaryNav"),
  chatSessionList: document.getElementById("chatSessionList"),
  chatDeleteModal: document.getElementById("chatDeleteModal"),
  chatDeleteModalText: document.getElementById("chatDeleteModalText"),
  chatDeleteCancel: document.getElementById("chatDeleteCancel"),
  chatDeleteConfirm: document.getElementById("chatDeleteConfirm"),
  newChatBtn: document.getElementById("newChatBtn"),
  searchBtn: document.getElementById("searchBtn"),
  chatShell: document.querySelector(".chat-shell"),
  pageShell: document.getElementById("pageShell"),
  pageBackButton: document.getElementById("pageBackButton"),
  pageEyebrow: document.getElementById("pageEyebrow"),
  pageTitle: document.getElementById("pageTitle"),
  pageSubtitle: document.getElementById("pageSubtitle"),
  pageContent: document.getElementById("pageContent"),
  pageOpenPanelButton: document.getElementById("pageOpenPanelButton"),
  matterList: document.getElementById("matterList"),
  activeMatterTitle: document.getElementById("activeMatterTitle"),
  activeMatterMeta: document.getElementById("activeMatterMeta"),
  newMatterToggle: document.getElementById("newMatterToggle"),
  newMatterForm: document.getElementById("newMatterForm"),
  workspacePanel: document.getElementById("workspacePanel"),
  detailToggle: document.getElementById("detailToggle"),
  composerPanelButton: document.getElementById("composerPanelButton"),
  detailClose: document.getElementById("detailClose"),
  refreshState: document.getElementById("refreshState"),
  modelInput: document.getElementById("modelInput"),
  areaInput: document.getElementById("areaInput"),
  messageList: document.getElementById("messageList"),
  chatForm: document.getElementById("chatForm"),
  questionInput: document.getElementById("questionInput"),
  sendButton: document.getElementById("sendButton"),
  dropZone: document.getElementById("dropZone"),
  chooseFiles: document.getElementById("chooseFiles"),
  fileInput: document.getElementById("fileInput"),
  uploadStatus: document.getElementById("uploadStatus"),
  thesisInput: document.getElementById("thesisInput"),
  workflowPackSelect: document.getElementById("workflowPackSelect"),
  analyzeButton: document.getElementById("analyzeButton"),
  folderCount: document.getElementById("folderCount"),
  folderNameInput: document.getElementById("folderNameInput"),
  createFolderButton: document.getElementById("createFolderButton"),
  folderPanel: document.getElementById("folderPanel"),
  documentCount: document.getElementById("documentCount"),
  documentsPanel: document.getElementById("documentsPanel"),
  documentViewerBox: document.getElementById("documentViewerBox"),
  documentPreviewTitle: document.getElementById("documentPreviewTitle"),
  documentPreviewMeta: document.getElementById("documentPreviewMeta"),
  documentDownloadLink: document.getElementById("documentDownloadLink"),
  documentDocxLink: document.getElementById("documentDocxLink"),
  ocrDocumentButton: document.getElementById("ocrDocumentButton"),
  compareCurrentButton: document.getElementById("compareCurrentButton"),
  pdfViewerShell: document.getElementById("pdfViewerShell"),
  pdfZoomOut: document.getElementById("pdfZoomOut"),
  pdfZoomIn: document.getElementById("pdfZoomIn"),
  pdfZoomLabel: document.getElementById("pdfZoomLabel"),
  pdfPageInput: document.getElementById("pdfPageInput"),
  pdfPageCount: document.getElementById("pdfPageCount"),
  pdfNativeFrame: document.getElementById("pdfNativeFrame"),
  documentPreviewContent: document.getElementById("documentPreviewContent"),
  documentAnnotationNote: document.getElementById("documentAnnotationNote"),
  addAnnotationButton: document.getElementById("addAnnotationButton"),
  annotationPanel: document.getElementById("annotationPanel"),
  documentCommentInput: document.getElementById("documentCommentInput"),
  addCommentButton: document.getElementById("addCommentButton"),
  commentPanel: document.getElementById("commentPanel"),
  documentVersionPanel: document.getElementById("documentVersionPanel"),
  documentComparePanel: document.getElementById("documentComparePanel"),
  documentEditContent: document.getElementById("documentEditContent"),
  saveDocumentEditButton: document.getElementById("saveDocumentEditButton"),
  applyDocumentEditButton: document.getElementById("applyDocumentEditButton"),
  documentEditDiff: document.getElementById("documentEditDiff"),
  workflowThesisInput: document.getElementById("workflowThesisInput"),
  runWorkflowButton: document.getElementById("runWorkflowButton"),
  workflowPanel: document.getElementById("workflowPanel"),
  editWorkflowButton: document.getElementById("editWorkflowButton"),
  updateWorkflowButton: document.getElementById("updateWorkflowButton"),
  duplicateWorkflowButton: document.getElementById("duplicateWorkflowButton"),
  deleteWorkflowButton: document.getElementById("deleteWorkflowButton"),
  workflowLabelInput: document.getElementById("workflowLabelInput"),
  workflowRequirementsInput: document.getElementById("workflowRequirementsInput"),
  createWorkflowButton: document.getElementById("createWorkflowButton"),
  workflowCreateStatus: document.getElementById("workflowCreateStatus"),
  workflowVersionPanel: document.getElementById("workflowVersionPanel"),
  visualizationPanel: document.getElementById("visualizationPanel"),
  tabularQueryInput: document.getElementById("tabularQueryInput"),
  createReviewButton: document.getElementById("createReviewButton"),
  saveReviewViewButton: document.getElementById("saveReviewViewButton"),
  reviewCsvLink: document.getElementById("reviewCsvLink"),
  reviewXlsxLink: document.getElementById("reviewXlsxLink"),
  reviewDocxLink: document.getElementById("reviewDocxLink"),
  reviewFilterInput: document.getElementById("reviewFilterInput"),
  reviewSortSelect: document.getElementById("reviewSortSelect"),
  reviewViewNameInput: document.getElementById("reviewViewNameInput"),
  reviewPanel: document.getElementById("reviewPanel"),
  draftTemplateSelect: document.getElementById("draftTemplateSelect"),
  draftAsOfDate: document.getElementById("draftAsOfDate"),
  draftParamsInput: document.getElementById("draftParamsInput"),
  createDraftButton: document.getElementById("createDraftButton"),
  previewDraftButton: document.getElementById("previewDraftButton"),
  draftStatus: document.getElementById("draftStatus"),
  draftPreviewPanel: document.getElementById("draftPreviewPanel"),
  draftTemplateTitleInput: document.getElementById("draftTemplateTitleInput"),
  draftTemplateParamsInput: document.getElementById("draftTemplateParamsInput"),
  draftTemplateBodyInput: document.getElementById("draftTemplateBodyInput"),
  saveDraftTemplateButton: document.getElementById("saveDraftTemplateButton"),
  toolSelect: document.getElementById("toolSelect"),
  toolArgsInput: document.getElementById("toolArgsInput"),
  runToolButton: document.getElementById("runToolButton"),
  toolOutput: document.getElementById("toolOutput"),
  factsPanel: document.getElementById("factsPanel"),
  sourcesPanel: document.getElementById("sourcesPanel"),
  auditPanel: document.getElementById("auditPanel"),
  artifactPanel: document.getElementById("artifactPanel"),
  artifactTitle: document.getElementById("artifactTitle"),
  artifactMeta: document.getElementById("artifactMeta"),
  artifactPreviewContent: document.getElementById("artifactPreviewContent"),
  artifactClose: document.getElementById("artifactClose"),
  artifactDownloadNative: document.getElementById("artifactDownloadNative"),
  artifactDownloadDocx: document.getElementById("artifactDownloadDocx"),
  artifactDownloadPdf: document.getElementById("artifactDownloadPdf"),
};

if (els.modelInput) {
  els.modelInput.value = appEl.dataset.defaultModel || "";
}
els.areaInput.value = appEl.dataset.defaultArea || "civile";
if (els.draftAsOfDate) {
  els.draftAsOfDate.value = new Date().toISOString().slice(0, 10);
}

const CHAT_SESSION_KEY = "judicex.activeChatSession";
const viewConfig = {
  chat: {
    path: "/chat",
    title: "Chat",
    subtitle: "Domande, upload rapido e risposte con fonti verificabili.",
  },
  onboarding: {
    path: "/onboarding",
    title: "Primo avvio",
    subtitle: "Configura Judicex in pochi passaggi: fascicolo, documenti, fonti e prima domanda.",
  },
  search: {
    path: "/search",
    title: "Cerca",
    subtitle: "Trova chat, messaggi, fascicoli, documenti, fatti e memoria assistente.",
  },
  dashboard: {
    path: "/dashboard",
    title: "Dashboard fascicolo",
    subtitle: "Vista sintetica di KPI, parti, importi, scadenze, timeline e copertura documentale.",
  },
  documents: {
    path: "/documents",
    title: "Documenti",
    subtitle: "Caricamento, anteprima, download, cartelle, OCR, annotazioni e revisioni.",
  },
  workflows: {
    path: "/workflows",
    title: "Workflow",
    subtitle: "Costruzione, versionamento, duplicazione, cancellazione ed esecuzione dei workflow sul fascicolo.",
  },
  tables: {
    path: "/tables",
    title: "Tabelle",
    subtitle: "Tabular review modificabile con filtri, ordinamento, viste salvate ed export.",
  },
  drafts: {
    path: "/drafts",
    title: "Atti",
    subtitle: "Generazione atti, preview e editor template guidato.",
  },
  tools: {
    path: "/tools",
    title: "Tool",
    subtitle: "Esecuzione diretta dei tool di memoria e ricerca interna.",
  },
  settings: {
    path: "/settings",
    title: "Centro Judicex",
    subtitle: "Accesso a fascicoli, documenti, workflow, tabelle, atti, tool e configurazione AI.",
  },
  provider: {
    path: "/provider-ai",
    title: "Provider AI",
    subtitle: "Scegli provider, endpoint e modello senza modificare codice o variabili interne.",
  },
  memory: {
    path: "/memory",
    title: "Memoria assistente",
    subtitle: "Preferenze, lezioni operative e note che guidano il modo di lavorare di Judicex.",
  },
  sources: {
    path: "/sources",
    title: "Fonti normative",
    subtitle: "Importa raccolte ufficiali nel database locale con un click.",
  },
  security: {
    path: "/security",
    title: "Sicurezza locale",
    subtitle: "Imposta una password locale per proteggere la memoria sul computer.",
  },
  backup: {
    path: "/backup",
    title: "Backup e ripristino",
    subtitle: "Esporta o ripristina database SQLite e allegati locali.",
  },
  matters: {
    path: "/matters",
    title: "Fascicoli",
    subtitle: "Selezione e creazione fascicoli.",
  },
};

function isDesktop() {
  return window.matchMedia("(min-width: 768px)").matches;
}

function setSidebar(open) {
  state.sidebarOpen = open;
  els.sidebar.style.transform = open ? "translateX(0)" : "translateX(-100%)";
  els.sidebarBackdrop.classList.toggle("hidden", !open || isDesktop());
}

function toggleDetails(open) {
  els.workspacePanel.classList.toggle("hidden", !open);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: options.body instanceof FormData
      ? options.headers || {}
      : {"Content-Type": "application/json", ...(options.headers || {})},
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function nl2br(value) {
  return escapeHtml(value).replace(/\n/g, "<br>");
}

function renderMarkdown(value) {
  const blocks = String(value || "").split(/```/);
  return blocks.map((block, index) => {
    if (index % 2 === 1) {
      const lines = block.replace(/^\w+\n/, "").replace(/\n$/, "");
      return `<pre class="my-3 overflow-auto rounded-md bg-slate-950 p-3 text-xs leading-5 text-slate-100"><code>${escapeHtml(lines)}</code></pre>`;
    }
    return renderMarkdownText(block);
  }).join("");
}

function renderMarkdownText(value) {
  const lines = String(value || "").split(/\n/);
  const html = [];
  let listItems = [];
  const flushList = () => {
    if (!listItems.length) return;
    html.push(`<ul class="my-2 list-disc space-y-1 pl-5">${listItems.join("")}</ul>`);
    listItems = [];
  };

  lines.forEach((line) => {
    const bullet = line.match(/^\s*[-*]\s+(.+)$/);
    if (bullet) {
      listItems.push(`<li>${renderInlineMarkdown(bullet[1])}</li>`);
      return;
    }
    flushList();
    if (!line.trim()) {
      html.push(`<div class="h-3"></div>`);
      return;
    }
    html.push(`<p>${renderInlineMarkdown(line)}</p>`);
  });
  flushList();
  return html.join("");
}

function renderInlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a class="text-accent underline" href="$2" target="_blank" rel="noreferrer">$1</a>')
    .replace(/`([^`]+)`/g, '<code class="rounded bg-slate-100 px-1 py-0.5 text-xs">$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

function pathToView() {
  const path = window.location.pathname || "/";
  const matched = Object.entries(viewConfig).find(([, config]) => config.path === path);
  if (matched) return matched[0];
  const name = path.replace(/^\/+|\/+$/g, "") || "chat";
  return viewConfig[name] ? name : "chat";
}

function navigateView(view, push = true) {
  const nextView = viewConfig[view] ? view : "chat";
  state.currentView = nextView;
  const config = viewConfig[nextView];
  if (push && window.location.pathname !== config.path) {
    history.pushState({view: nextView}, "", config.path);
  }
  if (els.chatShell) els.chatShell.classList.toggle("app-hidden", nextView !== "chat");
  if (els.pageShell) els.pageShell.classList.toggle("app-hidden", nextView === "chat");
  if (els.pageBackButton) {
    const showBack = nextView !== "chat" && nextView !== "settings";
    els.pageBackButton.classList.toggle("hidden", !showBack);
    els.pageBackButton.classList.toggle("inline-flex", showBack);
  }
  if (els.pageTitle) els.pageTitle.textContent = config.title;
  if (els.pageSubtitle) els.pageSubtitle.textContent = config.subtitle;
  if (els.pageEyebrow) els.pageEyebrow.textContent = activeMatter()?.title || "Judicex";
  document.querySelectorAll("[data-view]").forEach((link) => {
    link.classList.toggle("is-active", link.dataset.view === nextView);
  });
  if (nextView !== "chat") {
    renderDedicatedView();
  }
  afterDedicatedRender(nextView);
  if (!isDesktop()) {
    setSidebar(false);
  }
}

function afterDedicatedRender(view) {
  if (view === "provider") {
    void refreshProviderModels();
  }
}

async function loadChatSessions() {
  if (!els.chatSessionList) return;
  const payload = await api("/api/chat-sessions");
  state.chatSessions = payload.sessions || [];
  if (!state.activeChatSessionId) {
    try {
      const saved = localStorage.getItem(CHAT_SESSION_KEY) || "";
      if (saved && state.chatSessions.some((session) => session.id === saved)) {
        state.activeChatSessionId = saved;
      }
    } catch (error) {}
  }
  renderChatSessions();
}

function renderChatSessions() {
  if (!els.chatSessionList) return;
  els.chatSessionList.innerHTML = state.chatSessions.length
    ? state.chatSessions.map((session) => {
      const active = session.id === state.activeChatSessionId;
      const count = Number(session.message_count || 0);
      return `
        <button data-chat-session-id="${escapeHtml(session.id)}" class="chat-session-item nav-row ${active ? "is-active" : ""} mb-1 min-w-0 w-full rounded-md px-2.5 py-2 text-left" title="Tasto destro per eliminare">
          <div class="truncate text-sm text-gray-800">${escapeHtml(session.title || "Nuova chat")}</div>
          <div class="mt-0.5 text-xs text-gray-500">${escapeHtml(count)} messaggi</div>
        </button>
      `;
    }).join("")
    : `<div class="px-3 py-3 text-sm text-gray-500">Nessuna chat salvata.</div>`;
  document.querySelectorAll(".chat-session-item").forEach((button) => {
    button.addEventListener("click", () => loadChatSession(button.dataset.chatSessionId));
    button.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      openChatDeleteModal(button.dataset.chatSessionId);
    });
  });
}

function findChatSession(sessionId) {
  return state.chatSessions.find((session) => session.id === sessionId);
}

function openChatDeleteModal(sessionId) {
  if (!sessionId || !els.chatDeleteModal) return;
  const session = findChatSession(sessionId);
  state.pendingDeleteChatSessionId = sessionId;
  if (els.chatDeleteModalText) {
    els.chatDeleteModalText.textContent = `La chat "${session?.title || "Nuova chat"}" verra eliminata definitivamente.`;
  }
  els.chatDeleteModal.classList.remove("hidden");
  els.chatDeleteModal.classList.add("flex");
  els.chatDeleteConfirm?.focus();
}

function closeChatDeleteModal() {
  state.pendingDeleteChatSessionId = "";
  if (!els.chatDeleteModal) return;
  els.chatDeleteModal.classList.add("hidden");
  els.chatDeleteModal.classList.remove("flex");
}

async function createChatSession({title = "", select = true} = {}) {
  const payload = await api("/api/chat-sessions", {
    method: "POST",
    body: JSON.stringify({
      title,
      matter_id: state.activeMatterId || "",
    }),
  });
  state.chatSessions = payload.sessions || [];
  const session = payload.session;
  if (select && session) {
    state.activeChatSessionId = session.id;
    try { localStorage.setItem(CHAT_SESSION_KEY, session.id); } catch (error) {}
    els.messageList.innerHTML = "";
    resetMessageCopies();
    document.body.classList.remove("has-messages");
    state.recentUserTurns = [];
  }
  renderChatSessions();
  return session;
}

async function ensureChatSession(seedTitle = "") {
  if (state.activeChatSessionId && state.chatSessions.some((session) => session.id === state.activeChatSessionId)) {
    return state.activeChatSessionId;
  }
  const title = seedTitle ? seedTitle.replace(/\s+/g, " ").slice(0, 70) : "Nuova chat";
  const session = await createChatSession({title, select: true});
  return session.id;
}

async function loadChatSession(sessionId, options = {}) {
  if (!sessionId) return;
  const payload = await api(`/api/chat-sessions/${encodeURIComponent(sessionId)}`);
  const session = payload.session;
  state.activeChatSessionId = session.id;
  try { localStorage.setItem(CHAT_SESSION_KEY, session.id); } catch (error) {}
  renderChatSessions();
  els.messageList.innerHTML = "";
  resetMessageCopies();
  (session.messages || []).forEach((message) => {
    appendMessage(message.role, message.content, message.metadata?.label || "");
  });
  state.recentUserTurns = (session.messages || [])
    .filter((message) => message.role === "user")
    .map((message) => message.content)
    .slice(-6);
  document.body.classList.toggle("has-messages", (session.messages || []).length > 0);
  if (options.navigate !== false) {
    navigateView("chat");
  }
}

async function deleteChatSession(sessionId) {
  if (!sessionId) return;
  const payload = await api(`/api/chat-sessions/${encodeURIComponent(sessionId)}`, {method: "DELETE"});
  state.chatSessions = payload.sessions || [];
  if (state.activeChatSessionId === sessionId) {
    state.activeChatSessionId = "";
    try { localStorage.removeItem(CHAT_SESSION_KEY); } catch (error) {}
    els.messageList.innerHTML = "";
    resetMessageCopies();
    document.body.classList.remove("has-messages");
    state.recentUserTurns = [];
  }
  renderChatSessions();
}

async function persistChatMessage(role, content, metadata = {}) {
  const sessionId = await ensureChatSession(role === "user" ? content : "");
  const payload = await api(`/api/chat-sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    body: JSON.stringify({role, content, metadata}),
  });
  state.chatSessions = payload.sessions || [];
  renderChatSessions();
  return payload.message;
}

async function loadState() {
  const payload = await api("/api/state");
  state.matters = payload.matters || [];
  state.defaults = payload.defaults || {};
  state.health = payload.health || {};
  state.llmSettings = payload.llm || null;
  state.agentMemories = payload.agent_memories || [];
  state.officialBundles = payload.official_bundles || [];
  state.onboarding = payload.onboarding || {completed: false};
  els.healthBadge.textContent = `${payload.health?.matters || 0} fascicoli`;
  renderWorkflowOptions(payload.workflow_packs || []);
  await loadAuthStatus();
  if (!state.draftTemplates.length) await loadDraftTemplates();
  if (!state.tools.length) await loadTools();
  await loadChatSessions();
  renderMatterList();
  if (!state.activeMatterId && state.matters.length) {
    await selectMatter(state.matters[0].id);
  } else {
    renderActiveMatter();
    renderDedicatedView();
  }
  if (state.activeChatSessionId && !els.messageList.children.length) {
    await loadChatSession(state.activeChatSessionId, {navigate: false});
  }
  const initialView = pathToView();
  if (!state.onboarding.completed && !state.matters.length && initialView === "chat") {
    navigateView("onboarding", false);
  } else {
    navigateView(initialView, false);
  }
}

async function loadAuthStatus() {
  try {
    state.authStatus = await api("/api/auth/status");
  } catch (error) {
    state.authStatus = {configured: false, authenticated: true};
  }
}

function renderWorkflowOptions(workflowPacks) {
  if (!els.workflowPackSelect) return;
  state.workflowPacks = workflowPacks || [];
  els.workflowPackSelect.innerHTML = workflowPacks.length
    ? workflowPacks.map((pack) => {
      const source = pack.source === "sqlite" ? " · creato" : "";
      return `<option value="${escapeHtml(pack.id)}">${escapeHtml(pack.label || pack.id)}${escapeHtml(source)}</option>`;
    }).join("")
    : `<option value="">Nessun workflow</option>`;
}

function renderMatterList() {
  els.matterList.innerHTML = state.matters.length
    ? state.matters.map((matter) => {
      const active = matter.id === state.activeMatterId;
      return `
        <button data-matter-id="${escapeHtml(matter.id)}" class="matter-item mb-1 w-full rounded-md px-3 py-3 text-left hover:bg-slate-50 ${active ? "is-active" : ""}">
          <div class="truncate text-sm font-medium">${escapeHtml(matter.title)}</div>
          <div class="mt-1 truncate text-xs text-muted">${escapeHtml(matter.client_name || "Senza cliente")} · ${escapeHtml(matter.area || "area")}</div>
        </button>
      `;
    }).join("")
    : `<div class="px-3 py-6 text-sm text-muted">Nessun fascicolo.</div>`;
  document.querySelectorAll(".matter-item").forEach((item) => {
    item.addEventListener("click", () => selectMatter(item.dataset.matterId));
  });
}

function activeMatter() {
  return state.matters.find((matter) => matter.id === state.activeMatterId) || null;
}

async function selectMatter(matterId) {
  state.activeMatterId = matterId;
  renderMatterList();
  renderActiveMatter();
  await refreshMatterContext();
  if (!isDesktop()) {
    setSidebar(false);
  }
}

function renderActiveMatter() {
  const matter = activeMatter();
  if (!matter) {
    els.activeMatterTitle.textContent = "Nessun fascicolo";
    els.activeMatterMeta.textContent = "Workspace legale verificabile";
    return;
  }
  els.activeMatterTitle.textContent = matter.title;
  els.activeMatterMeta.textContent = `${matter.title}${matter.client_name ? ` · ${matter.client_name}` : ""}`;
}

async function refreshMatterContext() {
  if (!state.activeMatterId) {
    state.lastContext = null;
    els.factsPanel.innerHTML = `<div class="text-muted">Nessun fascicolo selezionato.</div>`;
    renderDedicatedView();
    return;
  }
  const payload = await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/context`);
  const context = payload.context || {};
  state.lastContext = context;
  await loadMatterFolders();
  renderMatterDocuments(context.documents || []);
  await loadTabularReviews();
  await loadVisualizations();
  const facts = [
    ...(context.parties || []),
    ...(context.amounts || []),
    ...(context.deadlines || []),
    ...(context.timeline || []),
  ].slice(0, 12);
  els.factsPanel.innerHTML = facts.length
    ? facts.map(renderFact).join("")
    : `<div class="text-muted">Nessun fatto estratto.</div>`;
  renderDedicatedView();
}

function renderMatterDocuments(documents) {
  if (!els.documentsPanel) return;
  if (els.documentCount) {
    els.documentCount.textContent = documents.length ? `${documents.length}` : "";
  }
  const folderOptions = (selected) => [
    `<option value="">Nessuna cartella</option>`,
    ...state.folders.map((folder) => `<option value="${escapeHtml(folder.id)}" ${folder.id === selected ? "selected" : ""}>${escapeHtml(folder.name)}</option>`),
  ].join("");
  els.documentsPanel.innerHTML = documents.length
    ? documents.map((document) => {
      const title = document.title || document.filename || "Documento";
      const kind = document.kind || document.mime_type || "documento";
      const created = document.created_at ? String(document.created_at).slice(0, 10) : "";
      return `
        <div class="rounded-md border border-line bg-white p-3">
          <div class="min-w-0">
            <div class="truncate text-sm font-medium text-ink">${escapeHtml(title)}</div>
            <div class="mt-1 truncate text-xs text-gray-500">${escapeHtml(kind)}${created ? ` · ${escapeHtml(created)}` : ""}</div>
          </div>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <button data-document-id="${escapeHtml(document.id)}" class="open-document rounded-md bg-ink px-2 py-1 text-xs font-medium text-white" type="button">Apri</button>
            <a class="rounded-md border border-line px-2 py-1 text-xs text-gray-600 hover:bg-gray-50" href="/api/matter-documents/${encodeURIComponent(document.id)}/download" target="_blank">Download</a>
            <a class="rounded-md border border-line px-2 py-1 text-xs text-gray-600 hover:bg-gray-50" href="/api/matter-documents/${encodeURIComponent(document.id)}/download?format=docx" target="_blank">DOCX</a>
            <select data-document-id="${escapeHtml(document.id)}" class="document-folder-select h-7 max-w-full rounded-md border border-line px-2 text-xs text-gray-600">
              ${folderOptions(document.folder_id || document.metadata?.folder_id || "")}
            </select>
          </div>
        </div>
      `;
    }).join("")
    : `<div class="rounded-md border border-line bg-white px-3 py-6 text-center text-sm text-gray-500">Nessun documento nel fascicolo.</div>`;
  document.querySelectorAll(".open-document").forEach((button) => {
    button.addEventListener("click", () => openMatterDocument(button.dataset.documentId));
  });
  document.querySelectorAll(".document-folder-select").forEach((select) => {
    select.addEventListener("change", async () => {
      await api(`/api/matter-documents/${encodeURIComponent(select.dataset.documentId)}/folder`, {
        method: "PATCH",
        body: JSON.stringify({folder_id: select.value}),
      });
      await refreshMatterContext();
    });
  });
}

async function loadMatterFolders() {
  if (!state.activeMatterId || !els.folderPanel) return;
  const payload = await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/folders`);
  state.folders = payload.folders || [];
  renderFolders();
}

function renderFolders() {
  if (!els.folderPanel) return;
  if (els.folderCount) {
    els.folderCount.textContent = state.folders.length ? `${state.folders.length}` : "";
  }
  els.folderPanel.innerHTML = state.folders.length
    ? state.folders.map((folder) => `
      <div class="flex items-center justify-between rounded-md border border-line px-2 py-1.5">
        <span class="truncate text-sm">${escapeHtml(folder.name)}</span>
        <span class="ml-2 shrink-0 text-xs text-gray-400">${escapeHtml(folder.document_count || 0)}</span>
      </div>
    `).join("")
    : `<div class="rounded-md border border-line bg-gray-50 px-3 py-3 text-xs text-gray-500">Nessuna cartella.</div>`;
}

async function openMatterDocument(documentId, options = {}) {
  const payload = await api(`/api/matter-documents/${encodeURIComponent(documentId)}/preview`);
  const sameDocument = state.activeDocumentId === documentId;
  state.activeDocumentId = documentId;
  state.currentDocument = payload.document;
  state.currentDocumentPreview = payload.preview || {};
  state.currentDocumentVersions = payload.versions || [];
  state.currentDocumentEdits = payload.edits || [];
  state.currentDocumentAnnotations = payload.annotations || [];
  state.currentDocumentComments = payload.comments || [];
  if (!sameDocument) {
    state.pdfPage = 1;
    state.pdfZoom = 1;
  }
  renderDocumentViewer(payload.document, payload.preview || {}, payload.versions || [], payload.edits || [], payload.annotations || [], payload.comments || []);
  if (options.openPanel !== false) {
    toggleDetails(true);
  }
  renderDedicatedView();
}

function renderDocumentViewer(document, preview, versions, edits, annotations = [], comments = []) {
  if (!els.documentViewerBox) return;
  els.documentViewerBox.classList.remove("hidden");
  els.documentViewerBox.open = true;
  els.documentPreviewTitle.textContent = document.title || "Documento";
  els.documentPreviewMeta.textContent = `${document.kind || "documento"} · ${String(document.updated_at || document.created_at || "").slice(0, 19)}`;
  els.documentDownloadLink.href = `/api/matter-documents/${encodeURIComponent(document.id)}/download`;
  els.documentDocxLink.href = `/api/matter-documents/${encodeURIComponent(document.id)}/download?format=docx`;
  renderNativeDocumentPreview(preview);
  els.documentPreviewContent.textContent = document.content || "";
  els.documentEditContent.value = document.content || "";
  renderAnnotations(annotations);
  renderComments(comments);
  renderDocumentVersions(versions);
  const latestEdit = edits[0] || null;
  state.lastEditId = latestEdit?.id || "";
  els.documentEditDiff.textContent = latestEdit?.diff?.length
    ? latestEdit.diff.join("\n")
    : "";
  els.documentComparePanel.textContent = "";
}

function renderNativeDocumentPreview(preview) {
  if (!els.pdfViewerShell) return;
  const hasNative = preview.source_url && ["pdf", "image"].includes(preview.viewer);
  els.pdfViewerShell.classList.toggle("hidden", !hasNative);
  if (!hasNative) {
    els.pdfNativeFrame.removeAttribute("src");
    return;
  }
  els.pdfPageCount.textContent = `/ ${preview.page_count || 1}`;
  els.pdfPageInput.max = preview.page_count || 1;
  els.pdfPageInput.value = state.pdfPage;
  els.pdfZoomLabel.textContent = `${Math.round(state.pdfZoom * 100)}%`;
  const hash = preview.viewer === "pdf"
    ? `#page=${state.pdfPage}&zoom=${Math.round(state.pdfZoom * 100)}`
    : "";
  els.pdfNativeFrame.src = `${preview.source_url}${hash}`;
  els.pdfNativeFrame.style.transform = `scale(${state.pdfZoom})`;
  els.pdfNativeFrame.style.width = `${100 / state.pdfZoom}%`;
  els.pdfNativeFrame.style.height = `${100 / state.pdfZoom}%`;
}

function renderAnnotations(annotations) {
  if (!els.annotationPanel) return;
  els.annotationPanel.innerHTML = annotations.length
    ? annotations.map((annotation) => `
      <div class="rounded-md border border-line px-2 py-1.5">
        <div class="flex items-center justify-between gap-2">
          <span class="font-medium">Pagina ${escapeHtml(annotation.page_number)}</span>
          <button data-annotation-id="${escapeHtml(annotation.id)}" class="delete-annotation text-gray-400 hover:text-red-600" type="button">Elimina</button>
        </div>
        <div class="mt-0.5 text-gray-600">${escapeHtml(annotation.note || "Annotazione")}</div>
      </div>
    `).join("")
    : `<div class="rounded-md border border-line bg-gray-50 px-2 py-2 text-gray-500">Nessuna annotazione.</div>`;
  document.querySelectorAll(".delete-annotation").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/document-annotations/${encodeURIComponent(button.dataset.annotationId)}`, {method: "DELETE"});
      await openMatterDocument(state.activeDocumentId);
    });
  });
}

function renderComments(comments) {
  if (!els.commentPanel) return;
  els.commentPanel.innerHTML = comments.length
    ? comments.map((comment) => `
      <div class="rounded-md border border-line px-2 py-1.5">
        <div class="flex items-center justify-between gap-2">
          <span class="font-medium">${escapeHtml(comment.status || "open")}</span>
          <button data-comment-id="${escapeHtml(comment.id)}" class="resolve-comment text-gray-400 hover:text-ink" type="button">Risolvi</button>
        </div>
        <div class="mt-0.5 text-gray-600">${escapeHtml(comment.body)}</div>
      </div>
    `).join("")
    : `<div class="rounded-md border border-line bg-gray-50 px-2 py-2 text-gray-500">Nessun commento.</div>`;
  document.querySelectorAll(".resolve-comment").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/document-comments/${encodeURIComponent(button.dataset.commentId)}`, {
        method: "PATCH",
        body: JSON.stringify({status: "resolved"}),
      });
      await openMatterDocument(state.activeDocumentId);
    });
  });
}

function renderDocumentVersions(versions) {
  els.documentVersionPanel.innerHTML = versions.length
    ? versions.map((version) => `
      <div class="rounded-md border border-line px-2 py-1.5">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div class="font-medium">v${escapeHtml(version.version_number)} · ${escapeHtml(version.reason || "versione")}</div>
          <div class="flex gap-1">
            <button data-version-id="${escapeHtml(version.id)}" class="compare-version rounded border border-line px-1.5 py-0.5 text-[11px]" type="button">Diff</button>
            <button data-version-id="${escapeHtml(version.id)}" class="restore-version rounded border border-line px-1.5 py-0.5 text-[11px]" type="button">Ripristina</button>
          </div>
        </div>
        <div class="mt-0.5 text-gray-500">${escapeHtml(String(version.created_at || "").slice(0, 19))}</div>
      </div>
    `).join("")
    : `<div class="rounded-md border border-line bg-gray-50 px-2 py-2 text-gray-500">Nessuna versione.</div>`;
  document.querySelectorAll(".compare-version").forEach((button) => {
    button.addEventListener("click", async () => {
      const payload = await api(`/api/matter-documents/${encodeURIComponent(state.activeDocumentId)}/versions/${encodeURIComponent(button.dataset.versionId)}/compare`);
      els.documentComparePanel.textContent = (payload.comparison?.diff || []).join("\n");
    });
  });
  document.querySelectorAll(".restore-version").forEach((button) => {
    button.addEventListener("click", async () => {
      await api(`/api/matter-documents/${encodeURIComponent(state.activeDocumentId)}/versions/${encodeURIComponent(button.dataset.versionId)}/restore`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      await refreshMatterContext();
      await openMatterDocument(state.activeDocumentId);
    });
  });
}

function renderFact(fact) {
  const value = fact.value
    ? `${fact.value}${fact.unit ? ` ${fact.unit}` : ""}`
    : fact.date_value || fact.text;
  return `
    <div class="rounded-md border border-line p-2">
      <div class="text-xs font-semibold text-muted">${escapeHtml(fact.fact_type || fact.type || "fact")}</div>
      <div class="mt-1 text-sm">${escapeHtml(fact.label || "")}: ${escapeHtml(value)}</div>
    </div>
  `;
}

function appendMessage(role, content, meta = "") {
  const align = role === "user" ? "justify-end" : "justify-start";
  const bubble = role === "user" ? "bg-ink text-white" : "bg-white border border-line";
  const width = role === "user" ? "max-w-2xl" : "max-w-3xl";
  const copyId = registerMessageCopy(content);
  const copyButton = role === "user"
    ? "border-white/20 text-white/70 hover:bg-white/10 hover:text-white"
    : "border-line text-gray-500 hover:bg-gray-50 hover:text-ink";
  const metaText = meta ? String(meta).trim() : "";
  const headerHtml = metaText
    ? `
        <div class="mb-2 flex items-center justify-between gap-3">
          <div class="min-w-0 text-xs opacity-70">${escapeHtml(metaText)}</div>
          <button data-copy-message-id="${copyId}" class="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border px-2 text-xs transition ${copyButton}" type="button" title="Copia messaggio">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
            <span>Copia</span>
          </button>
        </div>`
    : `
        <button data-copy-message-id="${copyId}" class="absolute right-3 top-3 inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border px-2 text-xs opacity-0 transition group-hover:opacity-100 ${copyButton}" type="button" title="Copia messaggio">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
          <span>Copia</span>
        </button>`;
  const html = `
    <div class="mb-4 flex ${align}">
      <div class="group relative ${width} rounded-lg ${bubble} px-5 py-4">
        ${headerHtml}
        <div class="space-y-1 text-sm leading-6">${renderMarkdown(content)}</div>
      </div>
    </div>
  `;
  els.messageList.insertAdjacentHTML("beforeend", html);
  scrollChatToBottom();
}

function registerMessageCopy(content) {
  state.messageCopySeq += 1;
  const id = String(state.messageCopySeq);
  state.messageCopies[id] = String(content || "");
  return id;
}

function resetMessageCopies() {
  state.messageCopies = {};
  state.messageCopySeq = 0;
}

async function copyMessageText(button) {
  const id = button?.dataset?.copyMessageId || "";
  const text = state.messageCopies[id] || "";
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      copyTextFallback(text);
    }
    setCopyButtonLabel(button, "Copiato");
  } catch (error) {
    copyTextFallback(text);
    setCopyButtonLabel(button, "Copiato");
  }
}

function copyTextFallback(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  textarea.remove();
}

function setCopyButtonLabel(button, label) {
  const labelNode = button?.querySelector("span");
  if (!labelNode) return;
  const previous = labelNode.textContent || "Copia";
  labelNode.textContent = label;
  window.setTimeout(() => {
    labelNode.textContent = previous;
  }, 1200);
}

function resetQuestionInputHeight() {
  if (!els.questionInput) return;
  els.questionInput.style.height = "";
  els.questionInput.style.overflowY = "hidden";
}

function scrollChatToBottom() {
  requestAnimationFrame(() => {
    if (document.body.classList.contains("has-messages")) {
      window.scrollTo({top: document.documentElement.scrollHeight, behavior: "auto"});
      return;
    }
    if (els.messageList) {
      els.messageList.scrollTop = els.messageList.scrollHeight;
    }
  });
}

function renderResult(result) {
  state.lastResult = result;
  // No status badge in the bubble — the assistant should read like a person,
  // not a system. The status remains available via renderAudit for QA.
  appendMessage("assistant", result.answer || "", "");
  renderSources(result.citations || []);
  renderAudit(result);
  if (result.case_facts?.length) {
    els.factsPanel.innerHTML = result.case_facts.map((fact) => `
      <div class="rounded-md border border-line p-2">
        <div class="text-xs font-semibold text-slate-500">case fact</div>
        <div class="mt-1 text-sm">${escapeHtml(fact.text)}</div>
      </div>
    `).join("") + els.factsPanel.innerHTML;
  }
}

function detectRequestedArtifactFormat(question) {
  const text = String(question || "").toLowerCase();
  if (/\b(pdf|\.pdf)\b/.test(text)) return "pdf";
  if (/\b(word|docx|\.docx|doc\b|\.doc)\b/.test(text)) return "docx";
  if (/\b(markdown|\.md)\b/.test(text)) return "md";
  if (/\b(txt|\.txt|testo semplice|file di testo)\b/.test(text)) return "txt";
  const asksFile = /\b(file|scaricabile|scaricare|download|documento)\b/.test(text);
  const asksCreate = /\b(crea|creami|genera|generami|prepara|preparami|redigi|trasforma|salva)\b/.test(text);
  return asksFile && asksCreate ? "docx" : "";
}

function artifactTitleFromQuestion(question, content) {
  const text = String(question || "").toLowerCase();
  if (text.includes("diffida")) return "Diffida di pagamento";
  if (text.includes("decreto ingiuntivo")) return "Ricorso per decreto ingiuntivo";
  if (text.includes("contratto")) return "Contratto";
  if (text.includes("parere")) return "Parere legale";
  if (text.includes("memo") || text.includes("memorandum")) return "Memorandum legale";
  const firstLine = String(content || "").split(/\n/).map((line) => line.trim()).find(Boolean);
  if (firstLine && firstLine.length <= 90 && !firstLine.endsWith(".")) return firstLine;
  return "Documento Judicex";
}

function artifactContentFromResult(result) {
  const sections = Array.isArray(result?.sections) ? result.sections : [];
  const draftSection = sections.find((section) => {
    const label = `${section?.type || ""} ${section?.title || ""}`.toLowerCase();
    return /draft|bozza|atto|documento|diffida|ricorso|contratto/.test(label);
  });
  if (draftSection?.content) {
    return [draftSection.title, draftSection.content].filter(Boolean).join("\n\n").trim();
  }
  const answer = String(result?.answer || "").trim();
  const extracted = extractDraftBlock(answer);
  return extracted || answer;
}

function extractDraftBlock(answer) {
  const text = String(answer || "").trim();
  if (!text) return "";
  const lower = text.toLowerCase();
  const markers = [
    "bozza diffida",
    "bozza di diffida",
    "bozza ricorso",
    "bozza atto",
    "bozza:",
    "testo dell'atto",
    "testo del documento",
    "documento:",
  ];
  for (const marker of markers) {
    const index = lower.indexOf(marker);
    if (index >= 0 && text.length - index > 180) {
      return text.slice(index).replace(/^[^:\n]*:\s*/i, "").trim();
    }
  }
  const legalStart = lower.search(/\b(mittente|soggetto|all'attenzione di|spett\.le|egregi signori|oggetto:)/);
  if (legalStart >= 0 && text.length - legalStart > 180) {
    return text.slice(legalStart).trim();
  }
  return "";
}

async function maybeCreateArtifactFromChat(question, result) {
  const format = detectRequestedArtifactFormat(question);
  if (!format) return null;
  const content = artifactContentFromResult(result);
  if (!content.trim()) return null;
  const title = artifactTitleFromQuestion(question, content);
  try {
    const payload = await api("/api/artifacts", {
      method: "POST",
      body: JSON.stringify({
        title,
        content,
        format,
        session_id: state.activeChatSessionId,
        matter_id: state.activeMatterId,
        save_to_matter: Boolean(state.activeMatterId),
        metadata: {
          created_from: "chat",
          requested_format: format,
          question_excerpt: String(question || "").slice(0, 600),
          result_status: String(result?.status || ""),
        },
      }),
    });
    if (payload.artifact) {
      state.artifacts.unshift(payload.artifact);
      appendArtifactCard(payload.artifact, payload.document);
      openArtifactPreview(payload.artifact);
      return payload.artifact;
    }
  } catch (error) {
    appendMessage("assistant", `Non sono riuscito a creare il file: ${error.message}`, "documento");
  }
  return null;
}

function appendArtifactCard(artifact, document = null) {
  const title = artifact?.title || "Documento Judicex";
  const format = artifactFormatLabel(artifact?.format);
  const downloadUrl = artifactDownloadUrl(artifact, artifact?.format || "docx");
  const docLine = document?.id ? "Salvato anche nei documenti del fascicolo." : "Salvato nella chat come documento generato.";
  const html = `
    <div class="mb-4 flex justify-start">
      <div class="w-full max-w-3xl rounded-lg border border-line bg-white px-4 py-3 shadow-sm">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="text-sm font-semibold text-ink">${escapeHtml(title)}</div>
            <div class="mt-1 text-xs leading-5 text-gray-500">${escapeHtml(format)} pronto. ${escapeHtml(docLine)}</div>
          </div>
          <div class="flex shrink-0 flex-wrap gap-2">
            <button data-artifact-open="${escapeHtml(artifact.id)}" class="h-8 rounded-md border border-line px-3 text-xs text-gray-700 hover:bg-gray-50" type="button">Anteprima</button>
            <a class="h-8 rounded-md bg-ink px-3 py-2 text-xs font-medium text-white hover:bg-black" href="${downloadUrl}">Scarica</a>
          </div>
        </div>
      </div>
    </div>
  `;
  els.messageList.insertAdjacentHTML("beforeend", html);
  scrollChatToBottom();
}

async function openArtifactById(artifactId) {
  const payload = await api(`/api/artifacts/${encodeURIComponent(artifactId)}`);
  if (payload.artifact) {
    openArtifactPreview(payload.artifact);
  }
}

function openArtifactPreview(artifact) {
  if (!artifact || !els.artifactPanel) return;
  state.activeArtifact = artifact;
  els.artifactTitle.textContent = artifact.title || "Documento Judicex";
  els.artifactMeta.textContent = `${artifactFormatLabel(artifact.format)} generato da Judicex`;
  els.artifactPreviewContent.textContent = artifact.content || artifact.excerpt || "";
  const id = encodeURIComponent(artifact.id);
  if (els.artifactDownloadNative) {
    els.artifactDownloadNative.href = `/api/artifacts/${id}/download?format=${encodeURIComponent(artifact.format || "docx")}`;
    els.artifactDownloadNative.textContent = `Scarica ${artifactFormatLabel(artifact.format)}`;
  }
  if (els.artifactDownloadDocx) {
    els.artifactDownloadDocx.href = `/api/artifacts/${id}/download?format=docx`;
  }
  if (els.artifactDownloadPdf) {
    els.artifactDownloadPdf.href = `/api/artifacts/${id}/download?format=pdf`;
  }
  els.artifactPanel.classList.remove("hidden");
  document.body.classList.add("has-artifact");
}

function closeArtifactPreview() {
  if (els.artifactPanel) els.artifactPanel.classList.add("hidden");
  document.body.classList.remove("has-artifact");
  state.activeArtifact = null;
}

function artifactFormatLabel(format) {
  const normalized = String(format || "").toLowerCase();
  return {
    docx: "Word",
    pdf: "PDF",
    md: "Markdown",
    txt: "Testo",
  }[normalized] || "Documento";
}

function artifactDownloadUrl(artifact, format) {
  if (!artifact?.id) return "#";
  return `/api/artifacts/${encodeURIComponent(artifact.id)}/download?format=${encodeURIComponent(format || artifact.format || "docx")}`;
}

function answerStatusLabel(status) {
  const normalized = String(status || "").toLowerCase();
  return {
    operational: "risposta pronta",
    grounded: "con fonti",
    limited: "con fonti parziali",
    abstain: "servono fonti",
    chat: "judicex",
    analysis: "analisi",
  }[normalized] || "judicex";
}

function agentStatusClasses(status) {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "completed" || normalized === "grounded" || normalized === "operational" || normalized === "analysis") {
    return "border-emerald-200 bg-emerald-50 text-emerald-800";
  }
  if (normalized === "running") {
    return "border-ink bg-ink text-white";
  }
  if (normalized === "limited" || normalized === "skipped") {
    return "border-amber-200 bg-amber-50 text-amber-800";
  }
  if (normalized === "failed" || normalized === "error") {
    return "border-red-200 bg-red-50 text-red-800";
  }
  return "border-line bg-sidebar text-muted";
}

function statusLabel(status) {
  const normalized = String(status || "pending").toLowerCase();
  const labels = {
    completed: "completato",
    running: "in corso",
    limited: "limitato",
    operational: "operativo",
    analysis: "analisi",
    grounded: "fondato",
    abstain: "non risponde",
    chat: "chat",
    failed: "bloccato",
    skipped: "saltato",
    pending: "in attesa",
  };
  return labels[normalized] || normalized;
}

function renderAgentStep(step, index) {
  const title = step?.title || `Passaggio ${index + 1}`;
  const detail = step?.detail || "";
  const status = step?.status || "pending";
  return `
    <div class="rounded-md border border-line bg-white px-3 py-2">
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0 text-[13px] font-semibold text-ink">${escapeHtml(title)}</div>
        <span class="shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium ${agentStatusClasses(status)}">${escapeHtml(statusLabel(status))}</span>
      </div>
      ${detail ? `<div class="mt-1 text-[12.5px] leading-5 text-muted">${escapeHtml(detail)}</div>` : ""}
    </div>
  `;
}

function renderAgentTrace(trace) {
  if (!trace.length) return;
  const wrap = document.createElement("div");
  wrap.className = "mb-4 flex justify-start";
  wrap.innerHTML = `
    <div class="w-full max-w-3xl rounded-lg border border-line bg-panel px-4 py-3 shadow-soft">
      <div class="mb-3 flex items-center justify-between gap-3">
        <div class="text-[12px] font-semibold uppercase tracking-[0.12em] text-muted">Attivita assistente</div>
        <div class="text-[12px] text-subtle">${escapeHtml(trace.length)} passaggi</div>
      </div>
      <div class="space-y-2">
        ${trace.map((step, index) => renderAgentStep(step, index)).join("")}
      </div>
    </div>
  `;
  els.messageList.appendChild(wrap);
  scrollChatToBottom();
}

function renderSources(citations) {
  els.sourcesPanel.innerHTML = citations.length
    ? citations.map((citation) => `
      <div class="rounded-md border border-line p-2">
        <div class="text-xs font-semibold text-muted">[${escapeHtml(citation.index)}] ${escapeHtml(citation.id)}</div>
        <div class="mt-1 text-sm">${escapeHtml(citation.title)}</div>
        <div class="mt-1 break-all text-xs text-muted">${escapeHtml(citation.source_ref)}</div>
      </div>
    `).join("")
    : `<div class="text-muted">Nessuna fonte citata.</div>`;
}

function renderAudit(payload) {
  els.auditPanel.textContent = JSON.stringify({
    status: payload.status,
    intent_route: payload.intent_route,
    legal_issues: payload.legal_issues,
    agent_trace: payload.agent_trace,
    matter_analysis: payload.matter_analysis,
    answer_contract: payload.answer_contract,
    semantic_verifier: payload.semantic_verifier,
    coverage: payload.coverage,
    matter_coverage: payload.matter_coverage,
  }, null, 2);
}

async function loadDraftTemplates() {
  if (!els.draftTemplateSelect) return;
  const payload = await api("/api/draft-templates");
  state.draftTemplates = payload.templates || [];
  els.draftTemplateSelect.innerHTML = state.draftTemplates.length
    ? state.draftTemplates.map((template) => `<option value="${escapeHtml(template.id || template.name)}">${escapeHtml(template.title || template.name)}${template.source === "sqlite" ? " · creato" : ""}</option>`).join("")
    : `<option value="">Nessun template</option>`;
}

async function loadTools() {
  if (!els.toolSelect) return;
  const payload = await api("/api/tools");
  state.tools = payload.tools || [];
  els.toolSelect.innerHTML = state.tools.length
    ? state.tools.map((tool) => `<option value="${escapeHtml(tool.name)}">${escapeHtml(tool.name)}</option>`).join("")
    : `<option value="">Nessun tool</option>`;
}

async function loadTabularReviews() {
  if (!state.activeMatterId || !els.reviewPanel) return;
  const payload = await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/tabular-reviews`);
  state.tabularReviews = payload.reviews || [];
  renderReviewList(state.tabularReviews);
}

async function loadVisualizations() {
  if (!state.activeMatterId || !els.visualizationPanel) return;
  const payload = await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/visualizations`);
  state.visualizations = payload.visualizations || {};
  renderVisualizations(state.visualizations);
}

function renderVisualizations(payload) {
  if (!els.visualizationPanel) return;
  els.visualizationPanel.innerHTML = renderVisualizationMarkup(payload, "grid-cols-3");
}

function renderBarList(title, items) {
  if (!items.length) return "";
  const max = Math.max(...items.map((item) => Number(item.value) || 0), 1);
  return `
    <div class="mt-3">
      <div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-500">${escapeHtml(title)}</div>
      <div class="space-y-1">
        ${items.map((item) => {
          const value = Number(item.value) || 0;
          const width = Math.max(8, Math.round((value / max) * 100));
          return `
            <div>
              <div class="mb-0.5 flex justify-between gap-2 text-[11px] text-gray-600">
                <span class="truncate">${escapeHtml(item.label)}</span>
                <span>${escapeHtml(value)}</span>
              </div>
              <div class="h-1.5 rounded-full bg-gray-100">
                <div class="h-1.5 rounded-full bg-ink" style="width:${width}%"></div>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    </div>
  `;
}

function renderTimeline(items) {
  if (!items.length) return "";
  return `
    <div class="mt-3">
      <div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-gray-500">Timeline</div>
      <div class="space-y-1">
        ${items.slice(0, 8).map((item) => `
          <div class="rounded-md border border-line px-2 py-1.5">
            <div class="font-medium">${escapeHtml(item.date)}</div>
            <div class="mt-0.5 line-clamp-2 text-gray-500">${escapeHtml(item.label || item.text)}</div>
          </div>
        `).join("")}
      </div>
    </div>
  `;
}

function currentContext() {
  return state.lastContext || {};
}

function pageEmpty(message) {
  return `<div class="rounded-md border border-line bg-white px-4 py-8 text-center text-sm text-gray-500">${escapeHtml(message)}</div>`;
}

function pageSection(title, body, extraClass = "") {
  return `
    <section class="rounded-md border border-line bg-white p-4 ${extraClass}">
      <div class="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-500">${escapeHtml(title)}</div>
      ${body}
    </section>
  `;
}

function renderDedicatedView(view = state.currentView) {
  if (!els.pageContent || !view || view === "chat") return;
  const config = viewConfig[view] || viewConfig.dashboard;
  if (els.pageTitle) els.pageTitle.textContent = config.title;
  if (els.pageSubtitle) els.pageSubtitle.textContent = config.subtitle;
  if (els.pageEyebrow) els.pageEyebrow.textContent = activeMatter()?.title || "Nessun fascicolo";
  const renderers = {
    onboarding: renderDedicatedOnboarding,
    search: renderDedicatedSearch,
    dashboard: renderDedicatedDashboard,
    documents: renderDedicatedDocuments,
    workflows: renderDedicatedWorkflows,
    tables: renderDedicatedTables,
    drafts: renderDedicatedDrafts,
    tools: renderDedicatedTools,
    settings: renderDedicatedSettings,
    provider: renderDedicatedProviderSettings,
    memory: renderDedicatedMemory,
    sources: renderDedicatedSources,
    security: renderDedicatedSecurity,
    backup: renderDedicatedBackup,
    matters: renderDedicatedMatters,
  };
  els.pageContent.innerHTML = (renderers[view] || renderDedicatedDashboard)();
}

function renderDedicatedOnboarding() {
  const hasMatter = Boolean(state.activeMatterId || state.matters.length);
  const hasProvider = Boolean(state.llmSettings?.provider);
  const hasSources = Number(state.health?.documents || 0) > 0;
  return `
    <div class="grid gap-4 lg:grid-cols-[1.1fr_.9fr]">
      ${pageSection("Percorso consigliato", `
        <div class="space-y-3">
          ${onboardingStep("1", "Scegli il motore AI", hasProvider, "Ollama locale, OpenAI, Claude o nessun LLM.", "provider")}
          ${onboardingStep("2", "Crea un fascicolo", hasMatter, "Apri una pratica e collega documenti, chat e analisi.", "matters")}
          ${onboardingStep("3", "Carica documenti", Boolean(currentContext().documents?.length), "PDF, DOCX, immagini, testo, CSV o JSON.", "documents")}
          ${onboardingStep("4", "Importa fonti normative", hasSources, "Porta gli articoli nel database locale.", "sources")}
          ${onboardingStep("5", "Fai la prima domanda", false, "Chiedi un parere operativo, una checklist o una bozza.", "chat")}
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          <button data-page-action="complete-onboarding" class="h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Segna completato</button>
          <button data-page-action="open-view" data-target-view="chat" class="h-9 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Vai alla chat</button>
        </div>
      `)}
      ${pageSection("Metodo semplice", `
        <div class="space-y-3 text-sm leading-6 text-gray-600">
          <p>Judicex lavora meglio quando ha un fascicolo, documenti e fonti. La memoria assistente conserva preferenze e lezioni operative, ma non sostituisce le fonti normative.</p>
          <p>Per iniziare senza configurazioni: crea un fascicolo, carica almeno un documento e chiedi una checklist pratica.</p>
        </div>
      `)}
    </div>
  `;
}

function onboardingStep(number, title, done, text, view) {
  return `
    <button data-page-action="open-view" data-target-view="${escapeHtml(view)}" class="flex w-full items-center gap-3 rounded-md border border-line bg-white p-3 text-left transition hover:border-gray-300 hover:shadow-sm" type="button">
      <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${done ? "bg-emerald-50 text-emerald-700" : "bg-gray-100 text-gray-700"}">${done ? "✓" : escapeHtml(number)}</span>
      <span class="min-w-0">
        <span class="block text-sm font-semibold text-ink">${escapeHtml(title)}</span>
        <span class="mt-0.5 block text-xs leading-5 text-gray-500">${escapeHtml(text)}</span>
      </span>
    </button>
  `;
}

function renderDedicatedDashboard() {
  const context = currentContext();
  if (!state.activeMatterId) return pageEmpty("Crea o seleziona un fascicolo per vedere la dashboard.");
  const facts = [
    ...(context.parties || []),
    ...(context.amounts || []),
    ...(context.deadlines || []),
    ...(context.timeline || []),
  ];
  return `
    <div class="space-y-4">
      ${pageSection("Visualizzazioni", `
        <div class="text-xs">${renderVisualizationMarkup(state.visualizations || {}, "md:grid-cols-6")}</div>
      `)}
      ${pageSection("Fatti principali", facts.length ? `
        <div class="grid gap-2 md:grid-cols-2">${facts.slice(0, 10).map(renderFact).join("")}</div>
      ` : `<div class="text-sm text-gray-500">Nessun fatto estratto.</div>`)}
    </div>
  `;
}

function renderDedicatedSearch() {
  const scope = state.pageSearch.scope || "all";
  const scopes = [
    ["all", "Tutto"],
    ["chat", "Chat"],
    ["matters", "Fascicoli"],
    ["documents", "Documenti"],
    ["facts", "Fatti"],
    ["memory", "Memoria assistente"],
  ];
  return `
    ${pageSection("Ricerca", `
      <div class="space-y-2">
        <input id="pageSearchQuery" class="h-10 rounded-md border border-line px-3 text-sm outline-none focus:border-ink" value="${escapeHtml(state.pageSearch.query || "")}" placeholder="Cerca una chat, un messaggio, un fascicolo, un documento...">
        <select id="pageSearchScope" class="h-10 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink">
          ${scopes.map(([value, label]) => `<option value="${value}" ${scope === value ? "selected" : ""}>${label}</option>`).join("")}
        </select>
        <button data-page-action="run-search" class="h-10 rounded-md bg-ink px-4 text-sm font-medium text-white" type="button">Cerca</button>
      </div>
      <div id="pageSearchStatus" class="mt-3 text-sm text-gray-500">${escapeHtml(state.pageSearch.status || "")}</div>
    `)}
    ${renderSearchResults()}
  `;
}

function renderSearchResults() {
  const results = state.pageSearch.results || [];
  if (!results.length) {
    return pageEmpty(state.pageSearch.query ? "Nessun risultato trovato." : "Scrivi una parola o premi Cerca per vedere gli elementi recenti.");
  }
  return `
    <div class="grid gap-3">
      ${results.map((item) => `
        <button data-page-action="open-search-result"
                data-result-type="${escapeHtml(item.type || "")}"
                data-session-id="${escapeHtml(item.session_id || "")}"
                data-matter-id="${escapeHtml(item.matter_id || "")}"
                data-document-id="${escapeHtml(item.document_id || "")}"
                class="group rounded-md border border-line bg-white p-4 text-left shadow-sm transition hover:border-gray-300 hover:shadow-md"
                type="button">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="rounded-full border border-line bg-gray-50 px-2 py-1 text-[11px] uppercase tracking-wide text-gray-500">${escapeHtml(searchTypeLabel(item.type))}</span>
                <span class="truncate text-sm font-semibold text-ink">${escapeHtml(item.title || "Risultato")}</span>
              </div>
              <div class="mt-1 text-xs text-gray-500">${escapeHtml(item.subtitle || "")}</div>
            </div>
            <span class="text-xs text-gray-400">${escapeHtml(formatDateShort(item.updated_at || ""))}</span>
          </div>
          <div class="mt-3 line-clamp-3 text-sm leading-6 text-gray-600">${escapeHtml(item.excerpt || "")}</div>
        </button>
      `).join("")}
    </div>
  `;
}

function searchTypeLabel(type) {
  return {
    chat: "Chat",
    message: "Messaggio",
    matter: "Fascicolo",
    document: "Documento",
    fact: "Fatto",
    memory: "Memoria",
  }[type] || "Risultato";
}

function formatDateShort(value) {
  return value ? String(value).slice(0, 16).replace("T", " ") : "";
}

function renderDedicatedDocuments() {
  const context = currentContext();
  if (!state.activeMatterId) return pageEmpty("Crea o seleziona un fascicolo prima di gestire i documenti.");
  const documents = context.documents || [];
  const upload = `
    <div class="flex flex-wrap items-center gap-2">
      <input id="pageFileInput" type="file" multiple class="hidden"
             accept=".pdf,.docx,.txt,.md,.markdown,.csv,.json,.png,.jpg,.jpeg,.webp,.tif,.tiff,.bmp,.gif,.heic,image/*,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document">
      <button data-page-action="upload-docs" class="h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Carica documenti</button>
      <input id="pageFolderName" class="h-9 min-w-56 rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Nuova cartella">
      <button data-page-action="create-folder" class="h-9 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Crea cartella</button>
      <a class="h-9 rounded-md border border-line px-3 py-2 text-sm text-gray-700 hover:bg-gray-50" href="/api/matters/${encodeURIComponent(state.activeMatterId)}/export?format=docx" target="_blank">Esporta DOCX</a>
      <a class="h-9 rounded-md border border-line px-3 py-2 text-sm text-gray-700 hover:bg-gray-50" href="/api/matters/${encodeURIComponent(state.activeMatterId)}/export?format=zip" target="_blank">Esporta ZIP</a>
      <span id="pageDocumentStatus" class="text-sm text-gray-500"></span>
    </div>
  `;
  const list = documents.length
    ? `<div class="grid gap-3 lg:grid-cols-2">${documents.map(renderPageDocumentCard).join("")}</div>`
    : pageEmpty("Nessun documento nel fascicolo.");
  const viewer = renderPageDocumentViewer();
  return `
    ${pageSection("Caricamento e cartelle", upload)}
    <div class="space-y-4">
      ${pageSection(`Documenti (${documents.length})`, list)}
      ${pageSection("Viewer dedicato", viewer || `<div class="text-sm text-gray-500">Apri un documento per vedere anteprima, download e testo estratto.</div>`)}
    </div>
  `;
}

function renderPageDocumentCard(document) {
  const title = document.title || document.filename || "Documento";
  const kind = document.kind || document.mime_type || "documento";
  const created = document.created_at ? String(document.created_at).slice(0, 10) : "";
  return `
    <article class="rounded-md border border-line p-3">
      <div class="truncate text-sm font-medium text-ink">${escapeHtml(title)}</div>
      <div class="mt-1 truncate text-xs text-gray-500">${escapeHtml(kind)}${created ? ` · ${escapeHtml(created)}` : ""}</div>
      <div class="mt-3 flex flex-wrap gap-2">
        <button data-page-action="open-document" data-document-id="${escapeHtml(document.id)}" class="h-8 rounded-md bg-ink px-3 text-xs font-medium text-white" type="button">Apri</button>
        <button data-page-action="open-document-panel" data-document-id="${escapeHtml(document.id)}" class="h-8 rounded-md border border-line px-3 text-xs text-gray-700 hover:bg-gray-50" type="button">Pannello</button>
        <a class="h-8 rounded-md border border-line px-3 py-2 text-xs text-gray-700 hover:bg-gray-50" href="/api/matter-documents/${encodeURIComponent(document.id)}/download" target="_blank">Download</a>
        <a class="h-8 rounded-md border border-line px-3 py-2 text-xs text-gray-700 hover:bg-gray-50" href="/api/matter-documents/${encodeURIComponent(document.id)}/download?format=docx" target="_blank">DOCX</a>
      </div>
    </article>
  `;
}

function renderPageDocumentViewer() {
  const document = state.currentDocument;
  if (!document) return "";
  const preview = state.currentDocumentPreview || {};
  const native = preview.source_url && ["pdf", "image"].includes(preview.viewer)
    ? `<iframe class="h-[520px] w-full rounded-md border border-line bg-white" src="${preview.source_url}${preview.viewer === "pdf" ? `#page=${state.pdfPage}&zoom=${Math.round(state.pdfZoom * 100)}` : ""}" title="Anteprima documento"></iframe>`
    : "";
  return `
    <div class="mb-3">
      <div class="truncate text-base font-semibold">${escapeHtml(document.title || "Documento")}</div>
      <div class="mt-1 text-xs text-gray-500">${escapeHtml(document.kind || "documento")} · ${escapeHtml(String(document.updated_at || document.created_at || "").slice(0, 19))}</div>
      <div class="mt-3 flex flex-wrap gap-2">
        <a class="h-8 rounded-md border border-line px-3 py-2 text-xs text-gray-700 hover:bg-gray-50" href="/api/matter-documents/${encodeURIComponent(document.id)}/download" target="_blank">Download</a>
        <a class="h-8 rounded-md border border-line px-3 py-2 text-xs text-gray-700 hover:bg-gray-50" href="/api/matter-documents/${encodeURIComponent(document.id)}/download?format=docx" target="_blank">DOCX</a>
        <button data-page-action="ocr-document" class="h-8 rounded-md border border-line px-3 text-xs text-gray-700 hover:bg-gray-50" type="button">OCR AI</button>
      </div>
    </div>
    ${native}
    <pre id="pageDocumentText" class="mt-3 max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-gray-50 p-3 text-xs leading-5 text-gray-700">${escapeHtml(document.content || "")}</pre>
  `;
}

function renderDedicatedWorkflows() {
  const packs = state.workflowPacks || [];
  const selected = state.pageWorkflow.selectedId || els.workflowPackSelect?.value || packs[0]?.id || "";
  state.pageWorkflow.selectedId = selected;
  const options = packs.length
    ? packs.map((pack) => `<option value="${escapeHtml(pack.id)}" ${pack.id === selected ? "selected" : ""}>${escapeHtml(pack.label || pack.id)}${pack.source === "sqlite" ? " · creato" : ""}</option>`).join("")
    : `<option value="">Nessun workflow</option>`;
  return `
    <div class="space-y-4">
      ${pageSection("Esecuzione", `
        <select id="pageWorkflowSelect" class="h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink">${options}</select>
        <textarea id="pageWorkflowThesis" rows="5" class="mt-3 w-full resize-y rounded-md border border-line p-3 text-sm outline-none focus:border-ink" placeholder="Obiettivo o tesi da verificare">${escapeHtml(state.pageWorkflow.thesis || "")}</textarea>
        <div class="mt-3 flex flex-wrap gap-2">
          <button data-page-action="run-workflow" class="h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Esegui</button>
          <button data-page-action="load-workflow" class="h-9 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Carica</button>
          <button data-page-action="duplicate-workflow" class="h-9 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Duplica</button>
          <button data-page-action="delete-workflow" class="h-9 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Elimina</button>
        </div>
        <pre id="pageWorkflowOutput" class="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-md bg-gray-950 p-3 text-xs leading-5 text-white">${escapeHtml(state.pageWorkflow.output || state.pageWorkflow.status || "")}</pre>
      `)}
      ${pageSection("Builder workflow", `
        <input id="pageWorkflowLabel" class="h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Nome workflow" value="${escapeHtml(state.pageWorkflow.label || "")}">
        <textarea id="pageWorkflowRequirements" rows="12" class="mt-3 w-full resize-y rounded-md border border-line p-3 font-mono text-xs leading-5 outline-none focus:border-ink" placeholder="Un requisito per riga: Etichetta | parole fatto | parole documento | obbligatorio/opzionale | suggerimento">${escapeHtml(state.pageWorkflow.requirements || "")}</textarea>
        <div class="mt-3 flex flex-wrap gap-2">
          <button data-page-action="create-workflow" class="h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Crea e usa</button>
          <button data-page-action="update-workflow" class="h-9 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Aggiorna selezionato</button>
        </div>
        <div id="pageWorkflowStatus" class="mt-3 text-sm text-gray-500">${escapeHtml(state.pageWorkflow.status || "")}</div>
      `)}
    </div>
  `;
}

function renderDedicatedTables() {
  if (!state.activeMatterId) return pageEmpty("Crea o seleziona un fascicolo prima di creare tabelle.");
  const reviews = state.tabularReviews || [];
  const list = reviews.length
    ? reviews.map((review) => `
      <button data-page-action="open-review" data-review-id="${escapeHtml(review.id)}" class="mb-1 w-full rounded-md border border-line px-3 py-2 text-left hover:bg-gray-50" type="button">
        <div class="truncate text-sm font-medium">${escapeHtml(review.title)}</div>
        <div class="mt-0.5 text-xs text-gray-500">${escapeHtml(review.row_count || 0)} righe</div>
      </button>
    `).join("")
    : `<div class="text-sm text-gray-500">Nessuna tabella salvata.</div>`;
  const table = state.activeReview ? renderPageReviewTable(state.activeReview) : `<div class="text-sm text-gray-500">Crea o apri una tabella per modificarla.</div>`;
  return `
    <div class="space-y-4">
      ${pageSection("Tabelle salvate", `
        <input id="pageTabularQuery" class="h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Filtro tabella" value="${escapeHtml(state.pageReview.query || "")}">
        <button data-page-action="create-review" class="mt-2 h-9 w-full rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Crea tabella</button>
        <div id="pageReviewStatus" class="mt-2 text-sm text-gray-500">${escapeHtml(state.pageReview.status || "")}</div>
        <div class="mt-4 max-h-[520px] overflow-auto">${list}</div>
      `)}
      ${pageSection("Review modificabile", table)}
    </div>
  `;
}

function renderPageReviewTable(review) {
  const columns = review.columns || [];
  const rows = filteredSortedReviewRows(review);
  return `
    <div class="mb-3 flex flex-wrap items-center gap-2">
      <input id="pageReviewFilter" class="h-8 rounded-md border border-line px-3 text-xs outline-none focus:border-ink" placeholder="Filtra vista" value="${escapeHtml(state.activeReviewFilter || "")}">
      <select id="pageReviewSort" class="h-8 rounded-md border border-line px-3 text-xs outline-none focus:border-ink">
        <option value="">Ordine originale</option>
        ${columns.map((column) => `<option value="${escapeHtml(column.key)}" ${state.activeReviewSortKey === column.key ? "selected" : ""}>${escapeHtml(column.label || column.key)}</option>`).join("")}
      </select>
      <input id="pageReviewViewName" class="h-8 rounded-md border border-line px-3 text-xs outline-none focus:border-ink" placeholder="Nome vista" value="${escapeHtml(state.pageReview.viewName || "")}">
      <button data-page-action="save-review-view" class="h-8 rounded-md border border-line px-3 text-xs text-gray-700 hover:bg-gray-50" type="button">Salva vista</button>
      <a class="h-8 rounded-md border border-line px-3 py-2 text-xs text-gray-700 hover:bg-gray-50" href="/api/tabular-reviews/${encodeURIComponent(review.id)}/export?format=csv" target="_blank">CSV</a>
      <a class="h-8 rounded-md border border-line px-3 py-2 text-xs text-gray-700 hover:bg-gray-50" href="/api/tabular-reviews/${encodeURIComponent(review.id)}/export?format=xlsx" target="_blank">XLSX</a>
      <a class="h-8 rounded-md border border-line px-3 py-2 text-xs text-gray-700 hover:bg-gray-50" href="/api/tabular-reviews/${encodeURIComponent(review.id)}/export?format=docx" target="_blank">DOCX</a>
    </div>
    <div class="overflow-auto">
      <table class="min-w-full border-collapse text-left text-xs">
        <thead><tr>${columns.map((column) => `<th class="border border-line bg-gray-50 px-2 py-1 font-semibold">${escapeHtml(column.label || column.key)}</th>`).join("")}</tr></thead>
        <tbody>
          ${rows.length ? rows.map(({row, originalIndex}) => `
            <tr>${columns.map((column) => `<td class="min-w-[150px] max-w-[280px] align-top border border-line px-2 py-1"><div contenteditable="true" data-row-index="${originalIndex}" data-key="${escapeHtml(column.key)}" class="page-editable-cell min-h-5 outline-none">${escapeHtml(row[column.key] || "")}</div></td>`).join("")}</tr>
          `).join("") : `<tr><td class="border border-line px-2 py-2 text-gray-500" colspan="${columns.length || 1}">Nessuna riga.</td></tr>`}
        </tbody>
      </table>
    </div>
  `;
}

function renderDedicatedDrafts() {
  const templates = state.draftTemplates || [];
  const selected = state.pageDraft.selectedId || els.draftTemplateSelect?.value || "";
  state.pageDraft.selectedId = selected;
  const asOfDate = state.pageDraft.asOfDate || new Date().toISOString().slice(0, 10);
  const options = templates.length
    ? templates.map((template) => {
      const value = template.id || template.name;
      return `<option value="${escapeHtml(value)}" ${value === selected ? "selected" : ""}>${escapeHtml(template.title || template.name)}${template.source === "sqlite" ? " · creato" : ""}</option>`;
    }).join("")
    : `<option value="">Nessun template</option>`;
  const previewText = state.pageDraft.preview || "";
  const previewTitle = state.pageDraft.previewTitle || "Anteprima atto";
  const previewMeta = state.pageDraft.previewMeta || (previewText ? "Bozza generata" : "Nessuna bozza ancora");
  const previewBody = previewText
    ? `<article class="judicex-paper">${escapeHtml(previewText)}</article>`
    : `<div class="flex h-full min-h-[420px] flex-col items-center justify-center gap-2 text-center">
         <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" class="text-gray-300"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="13" y2="17"/></svg>
         <div class="text-sm font-medium text-gray-500">L'anteprima dell'atto apparira qui</div>
         <div class="max-w-xs text-xs leading-5 text-gray-400">Scrivi a sinistra cosa deve preparare Judicex e premi <span class="font-medium text-gray-600">Prepara atto</span>. Il documento viene impaginato come un foglio Word.</div>
       </div>`;
  return `
    <div class="judicex-drafts-split grid gap-4 lg:grid-cols-[minmax(360px,440px)_1fr]">
      <div class="space-y-4">
        ${pageSection("Scrivi all'agente", `
          <textarea id="pageDraftInstruction" rows="9" class="w-full resize-y rounded-md border border-line p-3 text-base leading-7 outline-none focus:border-ink" placeholder="Esempio: prepara un ricorso per decreto ingiuntivo per Alfa S.r.l. contro Beta S.r.l. per euro 12.000, tribunale di Milano, causale fatture non pagate.">${escapeHtml(state.pageDraft.instruction || "")}</textarea>
          <div class="mt-3 grid gap-2 md:grid-cols-[1fr_160px]">
            <select id="pageDraftTemplateSelect" class="h-10 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink">
              <option value="">Scegli automaticamente</option>
              ${options}
            </select>
            <input id="pageDraftAsOfDate" class="h-10 rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Data norme" value="${escapeHtml(asOfDate)}">
          </div>
          <div class="mt-3 flex flex-wrap gap-2">
            <button data-page-action="assistant-draft" class="h-10 rounded-md bg-ink px-4 text-sm font-medium text-white" type="button">Prepara atto</button>
            <button data-page-action="preview-draft" class="h-10 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Anteprima manuale</button>
          </div>
          <div id="pageDraftStatus" class="mt-3 text-sm text-gray-500">${escapeHtml(state.pageDraft.status || "")}</div>
        `)}
        <details class="rounded-md border border-line bg-white">
          <summary class="cursor-pointer px-4 py-3 text-sm font-medium text-gray-700">Compilazione manuale</summary>
          <div class="border-t border-line p-4">
            <label class="block text-xs font-semibold uppercase tracking-wide text-gray-500" for="pageDraftParams">Dati dell'atto</label>
            <textarea id="pageDraftParams" rows="8" class="mt-1 w-full resize-y rounded-md border border-line p-3 text-sm leading-6 outline-none focus:border-ink" placeholder="attore: Mario Rossi&#10;convenuto: Beta S.r.l.&#10;tribunale: Milano&#10;oggetto: recupero credito">${escapeHtml(state.pageDraft.params || "")}</textarea>
            <div class="mt-2 text-xs text-gray-500">Scrivi un dato per riga nel formato nome: valore.</div>
            <div class="mt-3 flex flex-wrap gap-2">
              <button data-page-action="create-draft" class="h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Genera e salva</button>
            </div>
          </div>
        </details>
        <details class="rounded-md border border-line bg-white">
          <summary class="cursor-pointer px-4 py-3 text-sm font-medium text-gray-700">Modelli personali</summary>
          <div class="border-t border-line p-4">
            <input id="pageDraftTemplateTitle" class="h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Titolo template" value="${escapeHtml(state.pageDraft.title || "")}">
            <input id="pageDraftTemplateParams" class="mt-3 h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Campi richiesti: attore, convenuto, tribunale" value="${escapeHtml(state.pageDraft.paramList || "")}">
            <textarea id="pageDraftTemplateBody" rows="14" class="mt-3 w-full resize-y rounded-md border border-line p-3 text-sm leading-6 outline-none focus:border-ink" placeholder="Testo dell'atto. Usa {attore}, {convenuto}, {tribunale} dove vuoi inserire i dati.">${escapeHtml(state.pageDraft.body || "")}</textarea>
            <button data-page-action="save-draft-template" class="mt-3 h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Salva template</button>
          </div>
        </details>
      </div>
      <aside class="judicex-drafts-preview lg:sticky lg:top-6">
        <div class="flex h-full min-h-[640px] flex-col overflow-hidden rounded-md border border-line bg-gray-100">
          <div class="flex items-center justify-between gap-3 border-b border-line bg-white px-4 py-3">
            <div class="min-w-0">
              <div class="truncate text-sm font-semibold text-ink">${escapeHtml(previewTitle)}</div>
              <div class="mt-0.5 truncate text-xs text-gray-500">${escapeHtml(previewMeta)}</div>
            </div>
            <div class="flex items-center gap-2">
              <button data-page-action="copy-draft-preview" class="h-8 rounded-md border border-line bg-white px-3 text-xs text-gray-700 hover:bg-gray-50 ${previewText ? "" : "opacity-50 pointer-events-none"}" type="button">Copia</button>
            </div>
          </div>
          <div class="flex-1 overflow-auto p-6">
            ${previewBody}
          </div>
        </div>
      </aside>
    </div>
  `;
}

function renderDedicatedTools() {
  const tools = state.tools || [];
  const selected = state.pageTool.selectedName || els.toolSelect?.value || tools[0]?.name || "";
  state.pageTool.selectedName = selected;
  const options = tools.length
    ? tools.map((tool) => `<option value="${escapeHtml(tool.name)}" ${tool.name === selected ? "selected" : ""}>${escapeHtml(tool.name)}</option>`).join("")
    : `<option value="">Nessun tool</option>`;
  const selectedTool = tools.find((tool) => tool.name === selected);
  return pageSection("Esecuzione tool", `
    <div class="space-y-4">
      <div>
        <select id="pageToolSelect" class="h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink">${options}</select>
        <div class="mt-3 rounded-md border border-line bg-gray-50 p-3 text-xs leading-5 text-gray-600">${escapeHtml(selectedTool?.description || "Seleziona un tool.")}</div>
        <textarea id="pageToolArgs" rows="8" class="mt-3 w-full resize-y rounded-md border border-line p-3 text-sm leading-6 outline-none focus:border-ink" placeholder="query: cerca nei documenti&#10;limite: 10">${escapeHtml(state.pageTool.args || "")}</textarea>
        <button data-page-action="run-tool" class="mt-3 h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Esegui tool</button>
      </div>
      <pre id="pageToolOutput" class="min-h-[360px] overflow-auto whitespace-pre-wrap rounded-md bg-gray-950 p-3 text-xs leading-5 text-white">${escapeHtml(state.pageTool.output || "")}</pre>
    </div>
  `);
}

function renderDedicatedMemory() {
  const query = state.pageMemory.query || "";
  const memories = (state.agentMemories || []).filter((item) => {
    if (!query) return true;
    const haystack = `${item.title || ""} ${item.excerpt || item.content || ""} ${item.kind || ""} ${(item.tags || []).join(" ")}`.toLowerCase();
    return haystack.includes(query.toLowerCase());
  });
  const list = memories.length
    ? memories.map((item) => `
      <article class="rounded-md border border-line bg-white p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="text-sm font-semibold text-ink">${escapeHtml(item.title || "Memoria")}</div>
            <div class="mt-1 text-xs text-gray-500">${escapeHtml(memoryKindLabel(item.kind))}${item.scope ? ` · ${escapeHtml(item.scope)}` : ""}</div>
          </div>
          <div class="flex gap-2">
            <button data-page-action="edit-memory" data-memory-id="${escapeHtml(item.id)}" class="h-8 rounded-md border border-line px-3 text-xs text-gray-700 hover:bg-gray-50" type="button">Modifica</button>
            <button data-page-action="delete-memory" data-memory-id="${escapeHtml(item.id)}" class="h-8 rounded-md px-3 text-xs text-gray-500 hover:bg-gray-100 hover:text-ink" type="button">Elimina</button>
          </div>
        </div>
        <div class="mt-3 whitespace-pre-wrap text-sm leading-6 text-gray-600">${escapeHtml(item.excerpt || item.content || "")}</div>
        ${(item.tags || []).length ? `<div class="mt-3 flex flex-wrap gap-1">${(item.tags || []).map((tag) => `<span class="rounded-full border border-line bg-gray-50 px-2 py-1 text-[11px] text-gray-500">${escapeHtml(tag)}</span>`).join("")}</div>` : ""}
      </article>
    `).join("")
    : pageEmpty("Nessuna memoria assistente salvata.");
  return `
    <div class="grid gap-4 lg:grid-cols-[.9fr_1.1fr]">
      ${pageSection(state.pageMemory.editingId ? "Modifica memoria" : "Nuova memoria", `
        <label class="text-xs font-semibold uppercase tracking-wide text-gray-500" for="pageMemoryKind">Tipo</label>
        <select id="pageMemoryKind" class="mt-1 h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink">
          ${["preference", "instruction", "lesson", "decision", "note"].map((kind) => `<option value="${kind}" ${state.pageMemory.kind === kind ? "selected" : ""}>${memoryKindLabel(kind)}</option>`).join("")}
        </select>
        <input id="pageMemoryTitle" class="mt-3 h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Titolo" value="${escapeHtml(state.pageMemory.title || "")}">
        <textarea id="pageMemoryContent" rows="8" class="mt-3 w-full resize-y rounded-md border border-line p-3 text-sm leading-6 outline-none focus:border-ink" placeholder="Esempio: per recupero crediti B2B usa prima una checklist pratica e poi una strategia.">${escapeHtml(state.pageMemory.content || "")}</textarea>
        <input id="pageMemoryTags" class="mt-3 h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Tag separati da virgola" value="${escapeHtml(state.pageMemory.tags || "")}">
        <div class="mt-3 flex flex-wrap gap-2">
          <button data-page-action="save-memory" class="h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">${state.pageMemory.editingId ? "Aggiorna" : "Salva"}</button>
          ${state.pageMemory.editingId ? `<button data-page-action="clear-memory-form" class="h-9 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Annulla</button>` : ""}
        </div>
        <div class="mt-3 text-sm text-gray-500">${escapeHtml(state.pageMemory.status || "")}</div>
      `)}
      ${pageSection("Memorie salvate", `
        <input id="pageMemoryQuery" class="h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Cerca nella memoria assistente" value="${escapeHtml(query)}">
        <div class="mt-3 grid gap-3">${list}</div>
      `)}
    </div>
  `;
}

function memoryKindLabel(kind) {
  return {
    preference: "Preferenza",
    instruction: "Istruzione",
    lesson: "Lezione",
    decision: "Decisione",
    note: "Nota",
  }[kind] || kind || "Nota";
}

function renderDedicatedSources() {
  const bundles = state.officialBundles || [];
  const list = bundles.length
    ? bundles.map((bundle) => {
      const expected = Number(bundle.documents || 0);
      const imported = Number(bundle.imported || 0);
      const complete = expected > 0 && imported >= expected;
      const partial = imported > 0 && !complete;
      const badgeClass = complete
        ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
        : partial
          ? "bg-amber-50 text-amber-700 border border-amber-200"
          : "bg-gray-50 text-gray-600 border border-line";
      const badgeLabel = complete
        ? `${imported}/${expected} importati`
        : partial
          ? `${imported}/${expected} importati (parziale)`
          : `0/${expected} non importato`;
      const buttonLabel = complete ? "Aggiorna" : (partial ? "Completa import" : "Importa");
      const buttonClass = complete
        ? "h-9 rounded-md border border-line bg-white px-3 text-sm text-gray-700 hover:bg-gray-50"
        : "h-9 rounded-md bg-ink px-3 text-sm font-medium text-white";
      return `
      <article class="rounded-md border border-line bg-white p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="text-sm font-semibold text-ink">${escapeHtml(bundle.name)}</div>
            <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">
              <span class="inline-flex items-center rounded-full px-2 py-0.5 ${badgeClass}">${escapeHtml(badgeLabel)}</span>
              <span>${escapeHtml((bundle.areas || []).join(", "))}</span>
            </div>
          </div>
          <button data-page-action="import-sources" data-bundle-name="${escapeHtml(bundle.name)}" class="${buttonClass}" type="button">${escapeHtml(buttonLabel)}</button>
        </div>
        <div class="mt-3 text-sm leading-6 text-gray-600">${escapeHtml(bundle.description || "")}</div>
      </article>
    `;
    }).join("")
    : pageEmpty("Nessuna raccolta disponibile.");
  return `
    <div class="space-y-4">
      ${pageSection("Importazione", `
        <div class="grid gap-3 md:grid-cols-[220px_1fr]">
          <input id="pageSourcesAsOfDate" class="h-9 rounded-md border border-line px-3 text-sm outline-none focus:border-ink" value="${escapeHtml(state.pageSources.asOfDate || "")}" placeholder="YYYY-MM-DD">
          <div class="text-sm leading-6 text-gray-600">La data serve a chiedere a Normattiva il testo vigente. L'importazione richiede connessione internet.</div>
        </div>
        <div id="pageSourcesStatus" class="mt-3 text-sm text-gray-500">${escapeHtml(state.pageSources.status || "")}</div>
      `)}
      <div class="grid gap-3 md:grid-cols-2">${list}</div>
    </div>
  `;
}

function renderDedicatedSecurity() {
  const configured = Boolean(state.authStatus?.configured);
  return `
    <div class="grid gap-4 lg:grid-cols-[.9fr_1.1fr]">
      ${pageSection("Password locale", `
        <div class="rounded-md border border-line bg-gray-50 p-3 text-sm text-gray-600">
          Stato: ${configured ? "password locale attiva" : "nessuna password locale impostata"}.
        </div>
        <input id="pageSecurityPassword" type="password" class="mt-3 h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Nuova password locale">
        <button data-page-action="set-local-password" class="mt-3 h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Salva password</button>
        ${configured ? `<button data-page-action="logout" class="ml-2 mt-3 h-9 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Esci</button>` : ""}
        <div class="mt-3 text-sm text-gray-500">${escapeHtml(state.pageSecurity.status || "")}</div>
      `)}
      ${pageSection("Nota sicurezza", `
        <div class="space-y-3 text-sm leading-6 text-gray-600">
          <p>La password protegge l'accesso locale all'app. Non trasforma Judicex in un sistema multiutente o SaaS.</p>
          <p>Per dati reali usa anche cifratura disco, backup sicuri e variabili ambiente per le API key.</p>
        </div>
      `)}
    </div>
  `;
}

function renderDedicatedBackup() {
  return `
    <div class="grid gap-4 lg:grid-cols-2">
      ${pageSection("Backup", `
        <div class="text-sm leading-6 text-gray-600">Scarica un archivio ZIP con database SQLite e allegati locali.</div>
        <a class="mt-3 inline-flex h-9 items-center rounded-md bg-ink px-3 text-sm font-medium text-white" href="/api/backup" target="_blank">Scarica backup</a>
      `)}
      ${pageSection("Ripristino", `
        <input id="pageRestoreFile" type="file" accept=".zip,application/zip" class="block w-full rounded-md border border-line p-2 text-sm">
        <button data-page-action="restore-backup" class="mt-3 h-9 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Ripristina backup</button>
        <div class="mt-3 text-sm text-gray-500">${escapeHtml(state.pageBackup.status || "")}</div>
      `)}
    </div>
  `;
}

function renderSettingsHub() {
  const matter = activeMatter();
  const cards = [
    {
      key: "dashboard",
      title: "Dashboard",
      text: "KPI, timeline, parti, importi e copertura del fascicolo.",
      action: "open-view",
      view: "dashboard",
      badge: matter ? "Fascicolo attivo" : "Richiede fascicolo",
    },
    {
      key: "search",
      title: "Cerca",
      text: "Trova chat, messaggi, fascicoli, documenti e fatti estratti.",
      action: "open-view",
      view: "search",
      badge: "Globale",
    },
    {
      key: "matters",
      title: "Fascicoli",
      text: "Crea, seleziona e organizza le pratiche in memoria SQLite.",
      action: "open-view",
      view: "matters",
      badge: `${state.matters.length} salvati`,
    },
    {
      key: "documents",
      title: "Documenti",
      text: "Upload, viewer, OCR, download, cartelle e revisioni.",
      action: "open-view",
      view: "documents",
      badge: matter ? "Workspace" : "Prima crea fascicolo",
    },
    {
      key: "workflows",
      title: "Workflow",
      text: "Esecuzione, builder, requisiti, versioni e duplicazione.",
      action: "open-view",
      view: "workflows",
      badge: `${state.workflowPacks.length || 0} template`,
    },
    {
      key: "tables",
      title: "Tabelle",
      text: "Review modificabile, filtri, ordinamento, viste ed export.",
      action: "open-view",
      view: "tables",
      badge: `${state.tabularReviews.length || 0} viste`,
    },
    {
      key: "drafts",
      title: "Atti",
      text: "Generazione documenti, preview ed editor template.",
      action: "open-view",
      view: "drafts",
      badge: `${state.draftTemplates.length || 0} template`,
    },
    {
      key: "tools",
      title: "Tool",
      text: "Esecuzione diretta dei tool locali di ricerca e memoria.",
      action: "open-view",
      view: "tools",
      badge: `${state.tools.length || 0} tool`,
    },
    {
      key: "provider",
      title: "Provider AI",
      text: "OpenAI, Claude, Ollama, endpoint compatibili o nessun LLM.",
      action: "open-view",
      view: "provider",
      badge: state.llmSettings?.provider_label || "AI",
    },
    {
      key: "memory",
      title: "Memoria assistente",
      text: "Preferenze, istruzioni, decisioni e lezioni operative.",
      action: "open-view",
      view: "memory",
      badge: `${state.agentMemories.length || 0} note`,
    },
    {
      key: "sources",
      title: "Fonti normative",
      text: "Importa raccolte ufficiali nel database locale.",
      action: "open-view",
      view: "sources",
      badge: `${state.officialBundles.length || 0} raccolte`,
    },
    {
      key: "backup",
      title: "Backup",
      text: "Esporta e ripristina SQLite e allegati locali.",
      action: "open-view",
      view: "backup",
      badge: "Locale",
    },
    {
      key: "security",
      title: "Sicurezza",
      text: "Password locale per proteggere l'accesso alla memoria.",
      action: "open-view",
      view: "security",
      badge: state.authStatus?.configured ? "Attiva" : "Da impostare",
    },
  ];
  return `
    <div class="mb-5">
      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        ${cards.map((card) => `
          <button data-page-action="${escapeHtml(card.action)}" ${card.view ? `data-target-view="${escapeHtml(card.view)}"` : ""} class="group min-h-[150px] rounded-md border border-line bg-white p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-gray-300 hover:shadow-md" type="button">
            <div class="mb-4 flex items-start justify-between gap-3">
              <div class="flex h-11 w-11 items-center justify-center rounded-md border border-line bg-gray-50 text-ink group-hover:bg-ink group-hover:text-white">
                ${settingsHubIcon(card.key)}
              </div>
              <span class="max-w-[120px] truncate rounded-full border border-line bg-gray-50 px-2 py-1 text-[11px] text-gray-500">${escapeHtml(card.badge || "")}</span>
            </div>
            <div class="text-sm font-semibold text-ink">${escapeHtml(card.title)}</div>
            <div class="mt-2 line-clamp-3 text-xs leading-5 text-gray-500">${escapeHtml(card.text)}</div>
          </button>
        `).join("")}
      </div>
    </div>
  `;
}

function settingsHubIcon(key) {
  const icons = {
    dashboard: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M7 14l3-3 3 2 5-6"/></svg>`,
    search: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/></svg>`,
    matters: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7h6l2 2h10v10a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><path d="M3 7V5a2 2 0 012-2h4l2 2h4"/></svg>`,
    documents: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/></svg>`,
    workflows: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 3v6h6"/><path d="M18 21v-6h-6"/><path d="M6 9a9 9 0 019 9"/><path d="M18 15A9 9 0 019 6"/></svg>`,
    tables: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 5h18v14H3z"/><path d="M3 10h18M8 5v14M16 5v14"/></svg>`,
    drafts: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>`,
    tools: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a4 4 0 105.66 5.66L12 20.31 3.69 12l8.35-8.35a4 4 0 002.66 2.65z"/></svg>`,
    provider: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v3"/><path d="M12 18v3"/><path d="M3 12h3"/><path d="M18 12h3"/><path d="M7.8 7.8l-2-2"/><path d="M18.2 18.2l-2-2"/><path d="M16.2 7.8l2-2"/><path d="M5.8 18.2l2-2"/><circle cx="12" cy="12" r="4"/></svg>`,
    memory: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3a7 7 0 017 7c0 5-7 11-7 11S5 15 5 10a7 7 0 017-7z"/><circle cx="12" cy="10" r="2"/></svg>`,
    sources: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>`,
    backup: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><path d="M7 10l5 5 5-5"/><path d="M12 15V3"/></svg>`,
    security: `<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
  };
  return icons[key] || icons.provider;
}

function renderDedicatedSettings() {
  return renderSettingsHub();
}

function renderDedicatedProviderSettings() {
  const settings = state.llmSettings || {};
  const providers = settings.providers || [];
  const provider = settings.provider || "ollama";
  const options = providers.map((item) => `
    <option value="${escapeHtml(item.id)}" ${item.id === provider ? "selected" : ""}>${escapeHtml(item.label)}</option>
  `).join("");
  const selectedProvider = providerMeta(provider, settings);
  const modelValue = providerModelValue(provider, settings);
  const baseUrlValue = providerBaseUrlValue(provider, settings);
  const disabled = provider === "none" ? "disabled" : "";
  const modelOptions = providerModelOptions(provider, settings);
  const modelSelectOptions = modelOptions.length
    ? modelOptions.map((item) => `<option value="${escapeHtml(item)}" ${item === modelValue ? "selected" : ""}>${escapeHtml(item)}</option>`).join("")
    : `<option value="">Nessun modello disponibile</option>`;
  const modelStatus = state.llmModelOptionsStatus[provider] || "";
  const keyText = selectedProvider.api_key_env
    ? `${selectedProvider.api_key_env}: ${settings.api_key_present ? "configurata" : "mancante"}`
    : provider === "none" ? "Nessuna chiave richiesta." : "Nessuna chiave richiesta.";
  return `
    <div class="space-y-4">
      ${pageSection("Provider AI", `
        <label class="text-xs font-semibold uppercase tracking-wide text-gray-500" for="pageSettingsProvider">Provider</label>
        <select id="pageSettingsProvider" class="mt-1 h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink">${options}</select>
        <label class="mt-4 block text-xs font-semibold uppercase tracking-wide text-gray-500" for="pageSettingsModel">Modello</label>
        <div class="mt-1 flex gap-2">
          <select id="pageSettingsModel" class="h-9 min-w-0 flex-1 rounded-md border border-line px-3 text-sm outline-none focus:border-ink disabled:bg-gray-50 disabled:text-gray-400" ${disabled}>${modelSelectOptions}</select>
          <button data-page-action="refresh-provider-models" class="h-9 shrink-0 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50 disabled:text-gray-400" type="button" ${provider === "none" ? "disabled" : ""}>Aggiorna</button>
        </div>
        <div id="pageModelOptionsStatus" class="mt-2 min-h-4 text-xs text-gray-500">${escapeHtml(modelStatus)}</div>
        <label class="mt-4 block text-xs font-semibold uppercase tracking-wide text-gray-500" for="pageSettingsBaseUrl">Base URL</label>
        <input id="pageSettingsBaseUrl" class="mt-1 h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink disabled:bg-gray-50 disabled:text-gray-400" value="${escapeHtml(baseUrlValue)}" placeholder="${escapeHtml(selectedProvider.default_base_url || "")}" ${disabled}>
        <div class="mt-4 rounded-md border border-line bg-gray-50 p-3 text-sm text-gray-600">${escapeHtml(keyText)}</div>
        <div class="mt-4 flex flex-wrap gap-2">
          <button data-page-action="save-settings" class="h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Salva</button>
          <button data-page-action="test-settings" class="h-9 rounded-md border border-line px-3 text-sm text-gray-700 hover:bg-gray-50" type="button">Test connessione</button>
        </div>
        <div id="pageSettingsStatus" class="mt-3 text-sm text-gray-500">${escapeHtml(state.pageSettings.status || "")}</div>
      `)}
      ${pageSection("Note OSS e sicurezza", `
        <div class="space-y-3 text-sm leading-6 text-gray-600">
          <p>Le API key non vengono salvate nella UI. Si configurano nel file <code class="rounded bg-gray-100 px-1 py-0.5 text-xs">.env</code> o come variabili ambiente.</p>
          <p>Provider supportati: Ollama locale, OpenAI, Claude/Anthropic, endpoint OpenAI compatibile e modalità senza LLM.</p>
          <p>La modalità senza LLM mantiene disponibili fascicoli, upload, tabelle, documenti, workflow deterministici e tool locali; le risposte generative restano disattivate.</p>
        </div>
      `)}
    </div>
  `;
}

function renderDedicatedMatters() {
  const list = state.matters.length
    ? state.matters.map((matter) => `
      <article class="group flex min-h-[178px] flex-col justify-between rounded-md border border-line bg-white p-4 transition hover:border-gray-300 hover:shadow-sm ${matter.id === state.activeMatterId ? "ring-1 ring-ink" : ""}">
        <button data-page-action="select-matter" data-matter-id="${escapeHtml(matter.id)}" class="block flex-1 text-left" type="button">
          <div class="mb-4 flex items-start justify-between gap-3">
            <div class="flex h-12 w-14 shrink-0 items-end rounded-md border border-line bg-gray-50 px-2 pb-2">
              <div class="h-7 w-full rounded-sm bg-white shadow-sm"></div>
            </div>
            <span class="rounded-full border border-line px-2 py-1 text-[11px] text-gray-500">${escapeHtml(matter.status || "open")}</span>
          </div>
          <div class="min-w-0">
            <div class="line-clamp-2 text-sm font-semibold leading-5 text-ink">${escapeHtml(matter.title)}</div>
            <div class="mt-2 truncate text-xs text-gray-500">${escapeHtml(matter.client_name || "Senza cliente")}</div>
            <div class="mt-1 truncate text-xs text-gray-500">${escapeHtml(matter.area || "Area non indicata")}</div>
          </div>
        </button>
        <div class="mt-4 flex items-center justify-between gap-2 border-t border-line pt-3">
          <button data-page-action="select-matter" data-matter-id="${escapeHtml(matter.id)}" class="h-8 rounded-md border border-line px-3 text-xs font-medium text-gray-700 hover:bg-gray-50" type="button">Apri</button>
          <button data-page-action="delete-matter" data-matter-id="${escapeHtml(matter.id)}" class="h-8 rounded-md px-3 text-xs font-medium text-gray-500 hover:bg-gray-100 hover:text-ink" type="button">Elimina</button>
        </div>
      </article>
    `).join("")
    : `<div class="rounded-md border border-dashed border-line bg-white px-4 py-10 text-center text-sm text-gray-500">Nessun fascicolo. Crea il primo dalla sezione sopra.</div>`;
  return `
    <div class="space-y-4">
      ${pageSection("Nuovo fascicolo", `
        <input id="pageMatterTitle" class="h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Titolo fascicolo">
        <input id="pageMatterClient" class="mt-3 h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Cliente">
        <input id="pageMatterArea" class="mt-3 h-9 w-full rounded-md border border-line px-3 text-sm outline-none focus:border-ink" placeholder="Area" value="${escapeHtml(els.areaInput.value || state.defaults.area || "civile")}">
        <textarea id="pageMatterSummary" rows="5" class="mt-3 w-full resize-y rounded-md border border-line p-3 text-sm outline-none focus:border-ink" placeholder="Sintesi"></textarea>
        <button data-page-action="create-matter" class="mt-3 h-9 rounded-md bg-ink px-3 text-sm font-medium text-white" type="button">Crea fascicolo</button>
        <div id="pageMatterStatus" class="mt-3 text-sm text-gray-500"></div>
      `)}
      ${pageSection("Fascicoli", `<div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">${list}</div>`)}
    </div>
  `;
}

function renderVisualizationMarkup(payload, gridClass = "grid-cols-3") {
  const kpis = payload.kpis || {};
  const kpiItems = [
    ["Documenti", kpis.documents || 0],
    ["Fatti", kpis.facts || 0],
    ["Cartelle", kpis.folders || 0],
    ["Parti", kpis.parties || 0],
    ["Importi", kpis.amounts || 0],
    ["Scadenze", kpis.deadlines || 0],
  ];
  return `
    <div class="grid ${gridClass} gap-2">
      ${kpiItems.map(([label, value]) => `
        <div class="rounded-md border border-line bg-gray-50 p-2">
          <div class="text-[10px] uppercase tracking-wide text-gray-500">${escapeHtml(label)}</div>
          <div class="mt-1 text-lg font-semibold text-ink">${escapeHtml(value)}</div>
        </div>
      `).join("")}
    </div>
    ${renderBarList("Documenti per tipo", payload.documents_by_kind || [])}
    ${renderBarList("Fatti per tipo", payload.facts_by_type || [])}
    ${renderTimeline(payload.timeline || [])}
  `;
}

function renderReviewList(reviews) {
  if (!els.reviewPanel) return;
  els.reviewPanel.innerHTML = reviews.length
    ? reviews.map((review) => `
      <button data-review-id="${escapeHtml(review.id)}" class="open-review mb-1 w-full rounded-md border border-line px-2 py-2 text-left hover:bg-gray-50" type="button">
        <div class="truncate font-medium">${escapeHtml(review.title)}</div>
        <div class="mt-0.5 text-gray-500">${escapeHtml(review.row_count || 0)} righe</div>
      </button>
    `).join("")
    : `<div class="rounded-md border border-line bg-gray-50 px-3 py-3 text-gray-500">Nessuna tabella salvata.</div>`;
  document.querySelectorAll(".open-review").forEach((button) => {
    button.addEventListener("click", async () => {
      const payload = await api(`/api/tabular-reviews/${encodeURIComponent(button.dataset.reviewId)}`);
      renderReviewTable(payload.review);
    });
  });
}

function renderReviewTable(review) {
  const columns = review.columns || [];
  const rows = filteredSortedReviewRows(review);
  state.activeReview = review;
  refreshReviewExportLinks(review);
  if (els.reviewSortSelect) {
    els.reviewSortSelect.innerHTML = [`<option value="">Ordine originale</option>`]
      .concat(columns.map((column) => `<option value="${escapeHtml(column.key)}" ${state.activeReviewSortKey === column.key ? "selected" : ""}>${escapeHtml(column.label || column.key)}</option>`))
      .join("");
  }
  els.reviewPanel.innerHTML = `
    <div class="mb-2 font-medium">${escapeHtml(review.title)}</div>
    <table class="min-w-full border-collapse text-left">
      <thead>
        <tr>${columns.map((column) => `<th class="border border-line bg-gray-50 px-2 py-1 font-semibold">${escapeHtml(column.label || column.key)}</th>`).join("")}</tr>
      </thead>
      <tbody>
        ${rows.length ? rows.map(({row, originalIndex}) => `
          <tr>${columns.map((column) => `<td class="min-w-[140px] max-w-[260px] align-top border border-line px-2 py-1"><div contenteditable="true" data-row-index="${originalIndex}" data-key="${escapeHtml(column.key)}" class="editable-cell min-h-5 outline-none">${escapeHtml(row[column.key] || "")}</div></td>`).join("")}</tr>
        `).join("") : `<tr><td class="border border-line px-2 py-2 text-gray-500" colspan="${columns.length || 1}">Nessuna riga.</td></tr>`}
      </tbody>
    </table>
  `;
  document.querySelectorAll(".editable-cell").forEach((cell) => {
    cell.addEventListener("blur", async () => {
      await api(`/api/tabular-reviews/${encodeURIComponent(review.id)}/cell`, {
        method: "PATCH",
        body: JSON.stringify({
          row_index: Number(cell.dataset.rowIndex),
          key: cell.dataset.key,
          value: cell.textContent,
        }),
      });
    });
  });
}

function filteredSortedReviewRows(review) {
  const filterSource = state.currentView === "tables"
    ? state.activeReviewFilter
    : (els.reviewFilterInput?.value || state.activeReviewFilter || "");
  const filter = String(filterSource || "").toLowerCase().trim();
  let rows = (review.rows || []).map((row, originalIndex) => ({row, originalIndex}));
  if (filter) {
    rows = rows.filter(({row}) => Object.values(row).join(" ").toLowerCase().includes(filter));
  }
  const sortKey = state.currentView === "tables"
    ? state.activeReviewSortKey
    : (els.reviewSortSelect?.value || state.activeReviewSortKey);
  if (sortKey) {
    rows.sort((a, b) => String(a.row[sortKey] || "").localeCompare(String(b.row[sortKey] || ""), "it", {numeric: true}));
  }
  return rows;
}

function refreshReviewExportLinks(review) {
  const links = [
    [els.reviewCsvLink, "csv"],
    [els.reviewXlsxLink, "xlsx"],
    [els.reviewDocxLink, "docx"],
  ];
  links.forEach(([link, format]) => {
    if (!link) return;
    link.href = `/api/tabular-reviews/${encodeURIComponent(review.id)}/export?format=${format}`;
    link.classList.remove("hidden");
  });
}

function parseJsonObject(raw, fallback = {}) {
  const text = String(raw || "").trim();
  if (!text) return fallback;
  if (!text.startsWith("{")) {
    const parsed = {};
    text.split(/\n+/).forEach((line) => {
      const clean = line.trim();
      if (!clean) return;
      const separator = clean.includes(":") ? ":" : clean.includes("=") ? "=" : "";
      if (!separator) {
        throw new Error("Scrivi i dati come nome: valore, uno per riga.");
      }
      const [key, ...rest] = clean.split(separator);
      const name = key.trim();
      const value = rest.join(separator).trim();
      if (name) parsed[name] = value;
    });
    return parsed;
  }
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    throw new Error("Formato non valido. Usa nome: valore, uno per riga.");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Formato non valido. Usa nome: valore, uno per riga.");
  }
  return parsed;
}

function parseWorkflowRequirements(raw) {
  return String(raw || "")
    .split(/\n+/)
    .map((line, index) => {
      const parts = line.split("|").map((part) => part.trim());
      const label = parts[0] || "";
      if (!label) return null;
      const requiredRaw = (parts[3] || "obbligatorio").toLowerCase();
      return {
        id: `req_${index + 1}_${label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "")}`,
        label,
        description: label,
        fact_terms: splitTerms(parts[1] || label),
        document_terms: splitTerms(parts[2] || parts[1] || label),
        required: !["no", "false", "opzionale", "optional"].includes(requiredRaw),
        suggestion: parts[4] || `Caricare o indicare elementi per: ${label}`,
      };
    })
    .filter(Boolean);
}

function fillWorkflowBuilder(workflow, versions = []) {
  const definition = workflow.definition || {};
  const profile = (definition.profiles || [])[0] || {};
  els.workflowLabelInput.value = workflow.label || definition.label || "";
  els.workflowRequirementsInput.value = (profile.requirements || []).map((req) => [
    req.label || req.id || "",
    (req.fact_terms || req.factTypes || []).join(", "),
    (req.document_terms || []).join(", "),
    req.required === false ? "opzionale" : "obbligatorio",
    req.suggestion || "",
  ].join(" | ")).join("\n");
  if (els.workflowVersionPanel) {
    els.workflowVersionPanel.innerHTML = versions.length
      ? versions.map((version) => `
        <div class="rounded-md border border-line px-2 py-1.5">
          <div class="font-medium">v${escapeHtml(version.version_number)} · ${escapeHtml(version.reason || "versione")}</div>
          <div class="text-gray-500">${escapeHtml(String(version.created_at || "").slice(0, 19))}</div>
        </div>
      `).join("")
      : `<div class="rounded-md border border-line bg-gray-50 px-2 py-2 text-gray-500">Nessuna versione workflow.</div>`;
  }
}

function splitTerms(value) {
  return String(value || "")
    .split(/[,;]+/)
    .map((part) => part.trim().toLowerCase())
    .filter(Boolean);
}

function updateTracePlaceholder(node, trace) {
  if (!node) return;
  const current = currentThinkingStep(trace);
  const title = node.querySelector("[data-thinking-title]");
  const detail = node.querySelector("[data-thinking-detail]");
  const count = node.querySelector("[data-thinking-count]");
  if (title) title.textContent = friendlyThinkingTitle(current?.title || "Judicex sta lavorando");
  if (detail) detail.textContent = friendlyThinkingDetail(current?.detail || "Preparo la risposta.");
  if (count) count.textContent = trace.length ? `${trace.length} attività` : "";
  scrollChatToBottom();
}

function currentThinkingStep(trace) {
  const items = Array.isArray(trace) ? trace : [];
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (String(items[index]?.status || "").toLowerCase() === "running") {
      return items[index];
    }
  }
  return items[items.length - 1] || null;
}

function friendlyThinkingTitle(title) {
  const raw = String(title || "").replace(/^Tool:\s*/i, "").trim();
  const labels = {
    "Pianifico lavoro": "Capisco cosa serve",
    "memoria agente": "Controllo la memoria assistente",
    "ricerca legale": "Cerco nelle fonti disponibili",
    "composizione risposta": "Preparo la risposta",
    "fascicolo": "Leggo il fascicolo",
  };
  return labels[raw] || raw || "Judicex sta lavorando";
}

function friendlyThinkingDetail(detail) {
  const text = String(detail || "").trim();
  if (!text) return "Sto preparando una risposta ordinata.";
  return text
    .replace("Uso il motore legale con memoria normativa e controllo citazioni.", "Verifico le fonti disponibili.")
    .replace("Compongo una risposta pratica usando i risultati dei tool disponibili.", "Organizzo domande, rischi, strategia e bozza.")
    .replace("Cerco preferenze, decisioni e lezioni operative già salvate.", "Controllo se ci sono preferenze o note utili.");
}

async function streamAnswer(payload, placeholder) {
  const response = await fetch("/api/answer/stream", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  if (!response.ok || !response.body) {
    const errorPayload = await response.json().catch(() => ({}));
    throw new Error(errorPayload.error || `HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;
  let streamError = null;
  const trace = [];

  while (true) {
    const {done, value} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream: true});
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const rawEvent of events) {
      const parsed = parseSseEvent(rawEvent);
      if (!parsed) continue;
      if (parsed.event === "step") {
        trace.push(parsed.data);
        updateTracePlaceholder(placeholder, trace);
      } else if (parsed.event === "result") {
        result = parsed.data;
      } else if (parsed.event === "error") {
        streamError = parsed.data;
      }
    }
  }
  if (streamError) {
    throw new Error(streamError.message || "Errore streaming.");
  }
  if (!result) {
    throw new Error("Risposta streaming non ricevuta.");
  }
  return result;
}

function parseSseEvent(rawEvent) {
  const lines = rawEvent.split(/\n/);
  const event = (lines.find((line) => line.startsWith("event:")) || "").slice(6).trim();
  const dataLines = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim());
  if (!event) return null;
  return {event, data: dataLines.length ? JSON.parse(dataLines.join("\n")) : {}};
}

function workflowRequirementsText(workflow) {
  const definition = workflow.definition || {};
  const profile = (definition.profiles || [])[0] || {};
  return (profile.requirements || []).map((req) => [
    req.label || req.id || "",
    (req.fact_terms || req.factTypes || []).join(", "),
    (req.document_terms || []).join(", "),
    req.required === false ? "opzionale" : "obbligatorio",
    req.suggestion || "",
  ].join(" | ")).join("\n");
}

function syncPageFields(event) {
  const target = event.target;
  if (!target?.id) return;
  const value = target.value;
  if (target.id === "pageWorkflowSelect") state.pageWorkflow.selectedId = value;
  if (target.id === "pageWorkflowThesis") state.pageWorkflow.thesis = value;
  if (target.id === "pageWorkflowLabel") state.pageWorkflow.label = value;
  if (target.id === "pageWorkflowRequirements") state.pageWorkflow.requirements = value;
  if (target.id === "pageTabularQuery") state.pageReview.query = value;
  if (target.id === "pageReviewViewName") state.pageReview.viewName = value;
  if (target.id === "pageDraftTemplateSelect") state.pageDraft.selectedId = value;
  if (target.id === "pageDraftAsOfDate") state.pageDraft.asOfDate = value;
  if (target.id === "pageDraftInstruction") state.pageDraft.instruction = value;
  if (target.id === "pageDraftParams") state.pageDraft.params = value;
  if (target.id === "pageDraftTemplateTitle") state.pageDraft.title = value;
  if (target.id === "pageDraftTemplateParams") state.pageDraft.paramList = value;
  if (target.id === "pageDraftTemplateBody") state.pageDraft.body = value;
  if (target.id === "pageToolSelect") state.pageTool.selectedName = value;
  if (target.id === "pageToolArgs") state.pageTool.args = value;
  if (target.id === "pageSearchQuery") state.pageSearch.query = value;
  if (target.id === "pageSearchScope") state.pageSearch.scope = value || "all";
  if (target.id === "pageMemoryQuery") state.pageMemory.query = value;
  if (target.id === "pageMemoryKind") state.pageMemory.kind = value || "note";
  if (target.id === "pageMemoryTitle") state.pageMemory.title = value;
  if (target.id === "pageMemoryContent") state.pageMemory.content = value;
  if (target.id === "pageMemoryTags") state.pageMemory.tags = value;
  if (target.id === "pageSourcesAsOfDate") state.pageSources.asOfDate = value;
}

async function handlePageAction(action, button) {
  if (action === "open-view") return navigateView(button.dataset.targetView || "settings");
  if (action === "complete-onboarding") return completeOnboarding();
  if (action === "run-search") return runPageSearch();
  if (action === "open-search-result") return openSearchResult(button);
  if (action === "refresh-provider-models") return refreshProviderModels({force: true});
  if (action === "upload-docs") return document.getElementById("pageFileInput")?.click();
  if (action === "create-folder") return createPageFolder();
  if (action === "open-document") return openMatterDocument(button.dataset.documentId, {openPanel: false});
  if (action === "open-document-panel") return openMatterDocument(button.dataset.documentId, {openPanel: true});
  if (action === "ocr-document") return runPageOcr();
  if (action === "run-workflow") return runPageWorkflow();
  if (action === "load-workflow") return loadPageWorkflow();
  if (action === "create-workflow") return createPageWorkflow();
  if (action === "update-workflow") return updatePageWorkflow();
  if (action === "duplicate-workflow") return duplicatePageWorkflow();
  if (action === "delete-workflow") return deletePageWorkflow();
  if (action === "create-review") return createPageReview();
  if (action === "open-review") return openPageReview(button.dataset.reviewId);
  if (action === "save-review-view") return savePageReviewView();
  if (action === "assistant-draft") return assistantPageDraft();
  if (action === "preview-draft") return previewPageDraft();
  if (action === "create-draft") return createPageDraft();
  if (action === "save-draft-template") return savePageDraftTemplate();
  if (action === "copy-draft-preview") return copyDraftPreview();
  if (action === "run-tool") return runPageTool();
  if (action === "save-settings") return savePageSettings();
  if (action === "test-settings") return testPageSettings();
  if (action === "save-memory") return savePageMemory();
  if (action === "edit-memory") return editPageMemory(button.dataset.memoryId);
  if (action === "delete-memory") return deletePageMemory(button.dataset.memoryId);
  if (action === "clear-memory-form") return clearPageMemoryForm();
  if (action === "import-sources") return importSourceBundle(button.dataset.bundleName);
  if (action === "set-local-password") return setLocalPassword();
  if (action === "logout") return logoutLocal();
  if (action === "restore-backup") return restoreBackup();
  if (action === "select-matter") {
    await selectMatter(button.dataset.matterId);
    if (state.currentView === "matters") navigateView("dashboard");
    return;
  }
  if (action === "create-matter") return createPageMatter();
  if (action === "delete-matter") return deletePageMatter(button.dataset.matterId);
}

async function completeOnboarding() {
  const payload = await api("/api/onboarding/complete", {
    method: "POST",
    body: JSON.stringify({}),
  });
  state.onboarding = payload.onboarding || {completed: true};
  navigateView("chat");
}

async function runPageSearch() {
  state.pageSearch.query = document.getElementById("pageSearchQuery")?.value.trim() || "";
  state.pageSearch.scope = document.getElementById("pageSearchScope")?.value || state.pageSearch.scope || "all";
  state.pageSearch.status = "Cerco...";
  renderDedicatedView("search");
  try {
    const query = new URLSearchParams({
      q: state.pageSearch.query,
      scope: state.pageSearch.scope,
      matter_id: state.activeMatterId || "",
      top_k: "12",
    });
    const payload = await api(`/api/search?${query.toString()}`);
    state.pageSearch.results = payload.results || [];
    state.pageSearch.status = state.pageSearch.results.length
      ? `${state.pageSearch.results.length} risultati trovati.`
      : "Nessun risultato trovato.";
  } catch (error) {
    state.pageSearch.results = [];
    state.pageSearch.status = error.message;
  }
  renderDedicatedView("search");
}

async function openSearchResult(button) {
  const type = button.dataset.resultType || "";
  const sessionId = button.dataset.sessionId || "";
  const matterId = button.dataset.matterId || "";
  const documentId = button.dataset.documentId || "";
  if (type === "chat" || type === "message") {
    await loadChatSession(sessionId);
    return;
  }
  if (matterId) {
    await selectMatter(matterId);
  }
  if (type === "document" && documentId) {
    navigateView("documents");
    await openMatterDocument(documentId, {openPanel: false});
    return;
  }
  navigateView(type === "matter" || type === "fact" ? "dashboard" : "documents");
}

async function createPageFolder() {
  await ensureActiveMatter();
  const input = document.getElementById("pageFolderName");
  const status = document.getElementById("pageDocumentStatus");
  const name = input?.value.trim() || "";
  if (!name) return;
  if (status) status.textContent = "Creo cartella...";
  await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/folders`, {
    method: "POST",
    body: JSON.stringify({name}),
  });
  if (input) input.value = "";
  if (status) status.textContent = "Cartella creata.";
  await refreshMatterContext();
}

async function runPageOcr() {
  if (!state.activeDocumentId) return;
  const output = document.getElementById("pageDocumentText");
  if (output) output.textContent = "OCR AI in corso con Ollama...";
  const payload = await api(`/api/matter-documents/${encodeURIComponent(state.activeDocumentId)}/ocr`, {
    method: "POST",
    body: JSON.stringify({apply: true}),
  });
  if (payload.document) {
    await refreshMatterContext();
    await openMatterDocument(payload.document.id, {openPanel: false});
  } else if (output) {
    const ocr = payload.ocr || {};
    output.textContent = ocr.text || ocr.note || ocr.status || "OCR completato senza testo.";
  }
}

async function runPageWorkflow() {
  await ensureActiveMatter();
  const thesis = state.pageWorkflow.thesis || document.getElementById("pageWorkflowThesis")?.value.trim() || "analisi generale del fascicolo";
  state.pageWorkflow.thesis = thesis;
  state.pageWorkflow.selectedId = document.getElementById("pageWorkflowSelect")?.value || state.pageWorkflow.selectedId;
  state.pageWorkflow.output = "Esecuzione workflow...";
  renderDedicatedView("workflows");
  try {
    const payload = await api("/api/workflows/run", {
      method: "POST",
      body: JSON.stringify({
        matter_id: state.activeMatterId,
        thesis,
        workflow_pack: state.pageWorkflow.selectedId,
      }),
    });
    state.pageWorkflow.output = analysisToText(payload.analysis);
  } catch (error) {
    state.pageWorkflow.output = error.message;
  }
  renderDedicatedView("workflows");
}

async function loadPageWorkflow() {
  state.pageWorkflow.selectedId = document.getElementById("pageWorkflowSelect")?.value || state.pageWorkflow.selectedId;
  try {
    const payload = await api(`/api/workflows/${encodeURIComponent(state.pageWorkflow.selectedId)}`);
    state.pageWorkflow.editingId = payload.workflow.id;
    state.pageWorkflow.label = payload.workflow.label || payload.workflow.definition?.label || "";
    state.pageWorkflow.requirements = workflowRequirementsText(payload.workflow);
    state.pageWorkflow.status = `Workflow caricato: ${payload.workflow.label}`;
  } catch (error) {
    state.pageWorkflow.editingId = "";
    state.pageWorkflow.status = "I workflow builtin si possono duplicare o usare, non modificare direttamente.";
  }
  renderDedicatedView("workflows");
}

async function createPageWorkflow() {
  const label = state.pageWorkflow.label || document.getElementById("pageWorkflowLabel")?.value.trim() || "";
  const requirementsRaw = state.pageWorkflow.requirements || document.getElementById("pageWorkflowRequirements")?.value || "";
  const requirements = parseWorkflowRequirements(requirementsRaw);
  if (!label || !requirements.length) {
    state.pageWorkflow.status = "Inserisci nome e almeno un requisito.";
    renderDedicatedView("workflows");
    return;
  }
  const payload = await api("/api/workflows", {
    method: "POST",
    body: JSON.stringify({label, match_terms: label, requirements}),
  });
  renderWorkflowOptions(payload.workflow_packs || []);
  state.pageWorkflow.selectedId = payload.workflow.id;
  state.pageWorkflow.editingId = payload.workflow.id;
  state.pageWorkflow.status = `Workflow creato: ${payload.workflow.label}`;
  if (els.workflowPackSelect) els.workflowPackSelect.value = payload.workflow.id;
  renderDedicatedView("workflows");
}

async function updatePageWorkflow() {
  const workflowId = state.pageWorkflow.editingId || document.getElementById("pageWorkflowSelect")?.value || state.pageWorkflow.selectedId;
  const label = state.pageWorkflow.label || document.getElementById("pageWorkflowLabel")?.value.trim() || "";
  const requirements = parseWorkflowRequirements(state.pageWorkflow.requirements || document.getElementById("pageWorkflowRequirements")?.value || "");
  if (!workflowId || !requirements.length) return;
  try {
    const payload = await api(`/api/workflows/${encodeURIComponent(workflowId)}`, {
      method: "PATCH",
      body: JSON.stringify({label, match_terms: label, requirements, reason: "page_builder"}),
    });
    renderWorkflowOptions(payload.workflow_packs || []);
    state.pageWorkflow.selectedId = payload.workflow.id;
    state.pageWorkflow.editingId = payload.workflow.id;
    state.pageWorkflow.status = `Workflow aggiornato: ${payload.workflow.label}`;
  } catch (error) {
    state.pageWorkflow.status = error.message;
  }
  renderDedicatedView("workflows");
}

async function duplicatePageWorkflow() {
  const workflowId = document.getElementById("pageWorkflowSelect")?.value || state.pageWorkflow.selectedId;
  try {
    const payload = await api(`/api/workflows/${encodeURIComponent(workflowId)}/duplicate`, {
      method: "POST",
      body: JSON.stringify({label: `${state.pageWorkflow.label || "Workflow"} copia`}),
    });
    renderWorkflowOptions(payload.workflow_packs || []);
    state.pageWorkflow.selectedId = payload.workflow.id;
    state.pageWorkflow.editingId = payload.workflow.id;
    state.pageWorkflow.label = payload.workflow.label || "";
    state.pageWorkflow.requirements = workflowRequirementsText(payload.workflow);
    state.pageWorkflow.status = `Workflow duplicato: ${payload.workflow.label}`;
  } catch (error) {
    state.pageWorkflow.status = error.message;
  }
  renderDedicatedView("workflows");
}

async function deletePageWorkflow() {
  const workflowId = document.getElementById("pageWorkflowSelect")?.value || state.pageWorkflow.selectedId;
  if (!workflowId.startsWith("custom:")) {
    state.pageWorkflow.status = "I workflow builtin non si eliminano.";
    renderDedicatedView("workflows");
    return;
  }
  const payload = await api(`/api/workflows/${encodeURIComponent(workflowId)}`, {method: "DELETE"});
  renderWorkflowOptions(payload.workflow_packs || []);
  state.pageWorkflow.selectedId = state.workflowPacks[0]?.id || "";
  state.pageWorkflow.editingId = "";
  state.pageWorkflow.status = "Workflow eliminato.";
  renderDedicatedView("workflows");
}

async function createPageReview() {
  await ensureActiveMatter();
  state.pageReview.query = document.getElementById("pageTabularQuery")?.value.trim() || state.pageReview.query || "";
  state.pageReview.status = "Creo tabella...";
  renderDedicatedView("tables");
  try {
    const payload = await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/tabular-reviews`, {
      method: "POST",
      body: JSON.stringify({query: state.pageReview.query}),
    });
    state.activeReview = payload.review;
    state.pageReview.status = `Tabella creata: ${payload.review.title}`;
    await loadTabularReviews();
  } catch (error) {
    state.pageReview.status = error.message;
  }
  renderDedicatedView("tables");
}

async function openPageReview(reviewId) {
  const payload = await api(`/api/tabular-reviews/${encodeURIComponent(reviewId)}`);
  state.activeReview = payload.review;
  renderDedicatedView("tables");
}

async function savePageReviewView() {
  if (!state.activeReview) return;
  state.pageReview.viewName = document.getElementById("pageReviewViewName")?.value.trim() || state.pageReview.viewName || "Vista";
  const payload = await api(`/api/tabular-reviews/${encodeURIComponent(state.activeReview.id)}/views`, {
    method: "POST",
    body: JSON.stringify({
      name: state.pageReview.viewName,
      filter_text: state.activeReviewFilter,
      sort_key: state.activeReviewSortKey,
      sort_dir: "asc",
      columns: state.activeReview.columns || [],
    }),
  });
  state.pageReview.status = `Vista salvata: ${payload.view?.name || state.pageReview.viewName}`;
  renderDedicatedView("tables");
}

async function assistantPageDraft() {
  await ensureActiveMatter();
  state.pageDraft.instruction = document.getElementById("pageDraftInstruction")?.value.trim() || "";
  state.pageDraft.selectedId = document.getElementById("pageDraftTemplateSelect")?.value || "";
  state.pageDraft.asOfDate = document.getElementById("pageDraftAsOfDate")?.value.trim() || state.pageDraft.asOfDate;
  if (!state.pageDraft.instruction) {
    state.pageDraft.status = "Scrivi prima cosa deve preparare Judicex.";
    renderDedicatedView("drafts");
    return;
  }
  state.pageDraft.status = "Preparo l'atto...";
  state.pageDraft.preview = "";
  state.pageDraft.previewTitle = "Anteprima atto";
  state.pageDraft.previewMeta = "Generazione in corso...";
  renderDedicatedView("drafts");
  try {
    const payload = await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/drafts/assistant`, {
      method: "POST",
      body: JSON.stringify({
        instruction: state.pageDraft.instruction,
        template_name: state.pageDraft.selectedId,
        as_of_date: state.pageDraft.asOfDate,
      }),
    });
    const draft = payload.draft || {};
    if (draft.status === "needs_info") {
      state.pageDraft.selectedId = draft.template || state.pageDraft.selectedId;
      state.pageDraft.params = humanFieldsFromParams(draft.suggested_params || {}, draft.missing_params || []);
      state.pageDraft.status = `Mi servono questi dati: ${(draft.missing_params || []).join(", ")}`;
      state.pageDraft.preview = `${draft.title || "Atto"}\n\n${draft.reason || "Completa i dati mancanti nella sezione Compilazione manuale."}`;
      state.pageDraft.previewTitle = draft.title || "Anteprima atto";
      state.pageDraft.previewMeta = "Servono altri dati per completare la bozza";
      renderDedicatedView("drafts");
      return;
    }
    if (payload.document) {
      state.pageDraft.status = `Atto salvato: ${payload.document.title}`;
      state.pageDraft.preview = draft.rendered || "";
      state.pageDraft.previewTitle = payload.document.title || draft.title || "Atto generato";
      state.pageDraft.previewMeta = `Salvato nel fascicolo · ${new Date().toLocaleString("it-IT")}`;
      await refreshMatterContext();
      await openMatterDocument(payload.document.id, {openPanel: false});
    } else {
      state.pageDraft.status = draft.reason || "Atto non generato.";
      state.pageDraft.preview = draft.rendered || "";
      state.pageDraft.previewTitle = draft.title || "Anteprima atto";
      state.pageDraft.previewMeta = draft.reason || "Bozza non salvata";
    }
  } catch (error) {
    state.pageDraft.status = error.message;
  }
  renderDedicatedView("drafts");
}

function humanFieldsFromParams(params, missing = []) {
  const lines = [];
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value) lines.push(`${key}: ${value}`);
  });
  (missing || []).forEach((key) => {
    if (!Object.prototype.hasOwnProperty.call(params || {}, key)) {
      lines.push(`${key}: `);
    }
  });
  return lines.join("\n");
}

async function previewPageDraft() {
  state.pageDraft.selectedId = document.getElementById("pageDraftTemplateSelect")?.value || state.pageDraft.selectedId;
  state.pageDraft.params = document.getElementById("pageDraftParams")?.value || state.pageDraft.params || "";
  try {
    const payload = await api(`/api/draft-templates/${encodeURIComponent(state.pageDraft.selectedId)}/preview`, {
      method: "POST",
      body: JSON.stringify({params: parseJsonObject(state.pageDraft.params, {})}),
    });
    state.pageDraft.preview = payload.rendered || "";
    state.pageDraft.previewTitle = payload.title || state.pageDraft.previewTitle || "Anteprima atto";
    state.pageDraft.previewMeta = `Anteprima manuale · ${new Date().toLocaleString("it-IT")}`;
    state.pageDraft.status = "Anteprima aggiornata.";
  } catch (error) {
    state.pageDraft.status = "Anteprima disponibile per i template creati qui. Per quelli predefiniti usa Genera e salva.";
  }
  renderDedicatedView("drafts");
}

async function copyDraftPreview() {
  const text = state.pageDraft.preview || "";
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const helper = document.createElement("textarea");
      helper.value = text;
      helper.setAttribute("readonly", "");
      helper.style.position = "absolute";
      helper.style.left = "-9999px";
      document.body.appendChild(helper);
      helper.select();
      document.execCommand("copy");
      helper.remove();
    }
    state.pageDraft.status = "Anteprima copiata negli appunti.";
  } catch (error) {
    state.pageDraft.status = `Copia non riuscita: ${error.message}`;
  }
  renderDedicatedView("drafts");
}

async function createPageDraft() {
  await ensureActiveMatter();
  state.pageDraft.selectedId = document.getElementById("pageDraftTemplateSelect")?.value || state.pageDraft.selectedId;
  state.pageDraft.asOfDate = document.getElementById("pageDraftAsOfDate")?.value.trim() || state.pageDraft.asOfDate;
  state.pageDraft.params = document.getElementById("pageDraftParams")?.value || state.pageDraft.params || "";
  state.pageDraft.status = "Genero atto...";
  renderDedicatedView("drafts");
  try {
    const payload = await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/drafts`, {
      method: "POST",
      body: JSON.stringify({
        template_name: state.pageDraft.selectedId,
        as_of_date: state.pageDraft.asOfDate,
        params: parseJsonObject(state.pageDraft.params, {}),
      }),
    });
    if (payload.document) {
      state.pageDraft.status = `Atto salvato: ${payload.document.title}`;
      await refreshMatterContext();
      await openMatterDocument(payload.document.id, {openPanel: false});
    } else {
      state.pageDraft.status = payload.draft?.reason || "Atto non generato.";
    }
  } catch (error) {
    state.pageDraft.status = error.message;
  }
  renderDedicatedView("drafts");
}

async function savePageDraftTemplate() {
  const title = document.getElementById("pageDraftTemplateTitle")?.value.trim() || state.pageDraft.title || "";
  const body = document.getElementById("pageDraftTemplateBody")?.value.trim() || state.pageDraft.body || "";
  const paramList = document.getElementById("pageDraftTemplateParams")?.value || state.pageDraft.paramList || "";
  if (!title || !body) {
    state.pageDraft.status = "Inserisci titolo e corpo del template.";
    renderDedicatedView("drafts");
    return;
  }
  const payload = await api("/api/draft-templates", {
    method: "POST",
    body: JSON.stringify({title, name: title, body, required_params: splitTerms(paramList)}),
  });
  state.draftTemplates = payload.templates || [];
  if (els.draftTemplateSelect) {
    els.draftTemplateSelect.innerHTML = state.draftTemplates.map((template) => `<option value="${escapeHtml(template.id || template.name)}">${escapeHtml(template.title || template.name)}${template.source === "sqlite" ? " · creato" : ""}</option>`).join("");
    els.draftTemplateSelect.value = payload.template.id;
  }
  state.pageDraft.selectedId = payload.template.id;
  state.pageDraft.status = `Template salvato: ${payload.template.title}`;
  renderDedicatedView("drafts");
}

async function runPageTool() {
  state.pageTool.selectedName = document.getElementById("pageToolSelect")?.value || state.pageTool.selectedName;
  state.pageTool.args = document.getElementById("pageToolArgs")?.value || state.pageTool.args || "";
  state.pageTool.output = "Esecuzione tool...";
  renderDedicatedView("tools");
  try {
    const payload = await api("/api/tools/call", {
      method: "POST",
      body: JSON.stringify({name: state.pageTool.selectedName, arguments: parseJsonObject(state.pageTool.args, {})}),
    });
    state.pageTool.output = JSON.stringify(payload.result, null, 2);
  } catch (error) {
    state.pageTool.output = error.message;
  }
  renderDedicatedView("tools");
}

function providerMeta(providerId, settings = state.llmSettings || {}) {
  return (settings.providers || []).find((item) => item.id === providerId) || {};
}

function providerStoredValue(section, providerId, settings = state.llmSettings || {}) {
  const values = settings[section] || {};
  if (Object.prototype.hasOwnProperty.call(values, providerId)) {
    return String(values[providerId] || "");
  }
  return "";
}

function providerModelValue(providerId, settings = state.llmSettings || {}) {
  const stored = providerStoredValue("models", providerId, settings);
  if (stored) return stored;
  if (settings.provider === providerId && settings.model) return String(settings.model);
  return String(providerMeta(providerId, settings).default_model || "");
}

function providerBaseUrlValue(providerId, settings = state.llmSettings || {}) {
  const stored = providerStoredValue("base_urls", providerId, settings);
  if (stored) return stored;
  if (settings.provider === providerId && settings.base_url) return String(settings.base_url);
  return String(providerMeta(providerId, settings).default_base_url || "");
}

function providerModelOptions(providerId, settings = state.llmSettings || {}) {
  const selected = providerModelValue(providerId, settings);
  const fetched = state.llmModelOptions[providerId] || [];
  const options = [...(fetched.length ? fetched : (providerMeta(providerId, settings).model_options || []))];
  if (selected && !options.includes(selected)) options.unshift(selected);
  return options;
}

async function refreshProviderModels({force = false} = {}) {
  const current = state.llmSettings || {models: {}, base_urls: {}};
  const provider = document.getElementById("pageSettingsProvider")?.value || current.provider || "ollama";
  if (provider === "none") {
    state.llmModelOptions[provider] = [];
    state.llmModelOptionsStatus[provider] = "";
    return;
  }
  const baseUrl = document.getElementById("pageSettingsBaseUrl")?.value.trim() || providerBaseUrlValue(provider, current);
  const model = document.getElementById("pageSettingsModel")?.value || providerModelValue(provider, current);
  const cacheKey = `${provider}|${baseUrl}`;
  if (!force && state.llmModelOptionsCacheKey[provider] === cacheKey && state.llmModelOptions[provider]?.length) return;

  state.llmModelOptionsStatus[provider] = provider === "ollama" ? "Leggo i modelli installati in Ollama..." : "Carico modelli disponibili...";
  const statusNode = document.getElementById("pageModelOptionsStatus");
  if (statusNode) statusNode.textContent = state.llmModelOptionsStatus[provider];
  try {
    const query = new URLSearchParams({provider, base_url: baseUrl, model});
    const payload = await api(`/api/settings/llm/models?${query.toString()}`);
    const models = payload.models || [];
    state.llmModelOptions[provider] = models;
    state.llmModelOptionsCacheKey[provider] = cacheKey;
    if (models.length && provider === "ollama" && !models.includes(model)) {
      const nextModels = {...(current.models || {}), [provider]: models[0]};
      state.llmSettings = {...current, provider, model: models[0], models: nextModels};
    }
    state.llmModelOptionsStatus[provider] = payload.status === "ok"
      ? `${models.length} modelli disponibili${payload.source === "ollama" ? " da Ollama" : ""}.`
      : payload.message || "Non riesco a leggere i modelli, uso la lista predefinita.";
  } catch (error) {
    state.llmModelOptionsStatus[provider] = error.message;
  }
  if (state.currentView === "provider") renderDedicatedView("provider");
}

function switchPageSettingsProvider(provider) {
  const current = state.llmSettings || {models: {}, base_urls: {}};
  const previousProvider = current.provider || "ollama";
  const models = {...(current.models || {})};
  const baseUrls = {...(current.base_urls || {})};
  const currentModelInput = document.getElementById("pageSettingsModel");
  const currentBaseUrlInput = document.getElementById("pageSettingsBaseUrl");
  if (previousProvider && previousProvider !== provider) {
    models[previousProvider] = currentModelInput?.value.trim() || "";
    baseUrls[previousProvider] = currentBaseUrlInput?.value.trim() || "";
  }
  const nextSettings = {...current, provider, models, base_urls: baseUrls};
  state.llmSettings = {
    ...nextSettings,
    model: providerModelValue(provider, nextSettings),
    base_url: providerBaseUrlValue(provider, nextSettings),
  };
  state.pageSettings.status = "";
  renderDedicatedView(state.currentView || "provider");
  void refreshProviderModels({force: true});
}

function readPageSettings() {
  const current = state.llmSettings || {models: {}, base_urls: {}};
  const provider = document.getElementById("pageSettingsProvider")?.value || current.provider || "ollama";
  const models = {...(current.models || {})};
  const baseUrls = {...(current.base_urls || {})};
  models[provider] = document.getElementById("pageSettingsModel")?.value.trim() || "";
  baseUrls[provider] = document.getElementById("pageSettingsBaseUrl")?.value.trim() || "";
  return {
    provider,
    model: models[provider],
    base_url: baseUrls[provider],
    models,
    base_urls: baseUrls,
    temperature: current.temperature || 0,
  };
}

async function savePageSettings() {
  const next = readPageSettings();
  state.llmSettings = {...(state.llmSettings || {}), ...next};
  state.pageSettings.status = "Salvo impostazioni...";
  renderDedicatedView(state.currentView || "provider");
  try {
    const payload = await api("/api/settings/llm", {
      method: "PATCH",
      body: JSON.stringify(next),
    });
    state.llmSettings = payload.settings;
    state.defaults.model = payload.settings.model;
    state.defaults.host = payload.settings.base_url;
    state.defaults.provider = payload.settings.provider;
    state.pageSettings.status = `Impostazioni salvate: ${payload.settings.provider_label} / ${payload.settings.model || "nessun modello"}`;
  } catch (error) {
    state.pageSettings.status = error.message;
  }
  renderDedicatedView(state.currentView || "provider");
}

async function testPageSettings() {
  const next = readPageSettings();
  state.llmSettings = {...(state.llmSettings || {}), ...next};
  state.pageSettings.status = "Test connessione...";
  renderDedicatedView(state.currentView || "provider");
  try {
    const payload = await api("/api/settings/llm/test", {
      method: "POST",
      body: JSON.stringify(next),
    });
    state.llmSettings = payload.settings;
    state.pageSettings.status = `Test completato: ${payload.result?.message || payload.result?.status || "ok"}`;
  } catch (error) {
    state.pageSettings.status = error.message;
  }
  renderDedicatedView(state.currentView || "provider");
}

async function savePageMemory() {
  const payload = {
    kind: state.pageMemory.kind || document.getElementById("pageMemoryKind")?.value || "note",
    title: state.pageMemory.title || document.getElementById("pageMemoryTitle")?.value.trim() || "",
    content: state.pageMemory.content || document.getElementById("pageMemoryContent")?.value.trim() || "",
    tags: splitTerms(state.pageMemory.tags || document.getElementById("pageMemoryTags")?.value || ""),
    importance: 0.75,
    source: "web",
  };
  if (!payload.title || !payload.content) {
    state.pageMemory.status = "Inserisci titolo e contenuto.";
    renderDedicatedView("memory");
    return;
  }
  const editingId = state.pageMemory.editingId;
  const response = await api(editingId ? `/api/agent-memory/${encodeURIComponent(editingId)}` : "/api/agent-memory", {
    method: editingId ? "PATCH" : "POST",
    body: JSON.stringify(payload),
  });
  state.agentMemories = response.memories || [];
  state.pageMemory = {query: state.pageMemory.query, kind: payload.kind, title: "", content: "", tags: "", status: editingId ? "Memoria aggiornata." : "Memoria salvata.", editingId: ""};
  renderDedicatedView("memory");
}

function editPageMemory(memoryId) {
  const item = state.agentMemories.find((memory) => memory.id === memoryId);
  if (!item) return;
  state.pageMemory = {
    query: state.pageMemory.query,
    kind: item.kind || "note",
    title: item.title || "",
    content: item.content || item.excerpt || "",
    tags: (item.tags || []).join(", "),
    status: "Modifica la memoria e salva.",
    editingId: item.id,
  };
  renderDedicatedView("memory");
}

async function deletePageMemory(memoryId) {
  if (!memoryId) return;
  const item = state.agentMemories.find((memory) => memory.id === memoryId);
  if (item && !window.confirm(`Eliminare la memoria "${item.title}"?`)) return;
  const response = await api(`/api/agent-memory/${encodeURIComponent(memoryId)}`, {method: "DELETE"});
  state.agentMemories = response.memories || [];
  if (state.pageMemory.editingId === memoryId) clearPageMemoryForm();
  state.pageMemory.status = "Memoria eliminata.";
  renderDedicatedView("memory");
}

function clearPageMemoryForm() {
  state.pageMemory = {query: state.pageMemory.query, kind: "preference", title: "", content: "", tags: "", status: "", editingId: ""};
  renderDedicatedView("memory");
}

async function importSourceBundle(bundleName) {
  if (!bundleName) return;
  state.pageSources.asOfDate = document.getElementById("pageSourcesAsOfDate")?.value.trim() || state.pageSources.asOfDate;
  state.pageSources.status = `Scarico da Normattiva il bundle ${bundleName}...`;
  renderDedicatedView("sources");
  try {
    const payload = await api(`/api/official-bundles/${encodeURIComponent(bundleName)}/sync`, {
      method: "POST",
      body: JSON.stringify({as_of_date: state.pageSources.asOfDate}),
    });
    state.health = payload.health || state.health;
    if (Array.isArray(payload.bundles)) {
      state.officialBundles = payload.bundles;
    }
    const ingested = payload.result?.documents || [];
    const skipped = payload.result?.skipped || [];
    const bundle = (state.officialBundles || []).find((b) => b.name === bundleName);
    const expected = Number(bundle?.documents || ingested.length || 0);
    const imported = Number(bundle?.imported || ingested.length || 0);
    if (skipped.length) {
      state.pageSources.status = `Importazione completata con avvisi: ${imported}/${expected} articoli. ${skipped.length} non recuperati da Normattiva.`;
    } else {
      state.pageSources.status = `Importazione completata: ${imported}/${expected} articoli aggiornati alla data ${state.pageSources.asOfDate || "odierna"}.`;
    }
  } catch (error) {
    state.pageSources.status = `Importazione fallita: ${error.message}`;
  }
  renderDedicatedView("sources");
}

async function setLocalPassword() {
  const password = document.getElementById("pageSecurityPassword")?.value || "";
  state.pageSecurity.status = "Salvo password...";
  renderDedicatedView("security");
  try {
    await api("/api/security/password", {
      method: "POST",
      body: JSON.stringify({password}),
    });
    await loadAuthStatus();
    state.pageSecurity.status = "Password locale attivata.";
  } catch (error) {
    state.pageSecurity.status = error.message;
  }
  renderDedicatedView("security");
}

async function logoutLocal() {
  await api("/api/auth/logout", {method: "POST", body: JSON.stringify({})});
  window.location.reload();
}

async function restoreBackup() {
  const input = document.getElementById("pageRestoreFile");
  const file = input?.files?.[0];
  if (!file) {
    state.pageBackup.status = "Seleziona un file ZIP di backup.";
    renderDedicatedView("backup");
    return;
  }
  if (!window.confirm("Ripristinare questo backup? Il database corrente verra copiato come pre_restore e poi sostituito.")) return;
  state.pageBackup.status = "Ripristino in corso...";
  renderDedicatedView("backup");
  const form = new FormData();
  form.append("file", file);
  try {
    await api("/api/restore", {method: "POST", body: form});
    state.pageBackup.status = "Backup ripristinato. Ricarico Judicex...";
    window.setTimeout(() => window.location.reload(), 800);
  } catch (error) {
    state.pageBackup.status = error.message;
    renderDedicatedView("backup");
  }
}

async function createPageMatter() {
  const payload = {
    title: document.getElementById("pageMatterTitle")?.value.trim() || "",
    client_name: document.getElementById("pageMatterClient")?.value.trim() || "",
    area: document.getElementById("pageMatterArea")?.value.trim() || els.areaInput.value.trim() || "civile",
    summary: document.getElementById("pageMatterSummary")?.value.trim() || "",
  };
  if (!payload.title) return;
  const result = await api("/api/matters", {method: "POST", body: JSON.stringify(payload)});
  state.matters = result.matters || [];
  state.activeMatterId = result.matter.id;
  renderMatterList();
  renderActiveMatter();
  await refreshMatterContext();
  navigateView("dashboard");
}

async function deletePageMatter(matterId) {
  const matter = state.matters.find((item) => item.id === matterId);
  if (!matter) return;
  const confirmed = window.confirm(`Eliminare il fascicolo "${matter.title}"?\n\nDocumenti, dati estratti e chat collegate al fascicolo verranno rimossi dalla memoria locale.`);
  if (!confirmed) return;
  const payload = await api(`/api/matters/${encodeURIComponent(matterId)}`, {method: "DELETE"});
  state.matters = payload.matters || [];
  await loadChatSessions();
  if (state.activeMatterId === matterId) {
    state.activeMatterId = state.matters[0]?.id || "";
    state.lastContext = null;
    state.visualizations = {};
    state.tabularReviews = [];
    state.folders = [];
    state.currentDocument = null;
    state.activeDocumentId = "";
    state.activeReview = null;
    state.activeChatSessionId = "";
    if (state.activeMatterId) {
      await refreshMatterContext();
    } else {
      renderActiveMatter();
      renderDedicatedView("matters");
    }
  }
  renderMatterList();
  renderActiveMatter();
  renderDedicatedView("matters");
}

document.querySelectorAll("[data-view]").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    navigateView(link.dataset.view);
  });
});

window.addEventListener("popstate", () => navigateView(pathToView(), false));

if (els.pageOpenPanelButton) {
  els.pageOpenPanelButton.addEventListener("click", () => toggleDetails(true));
}

if (els.pageBackButton) {
  els.pageBackButton.addEventListener("click", () => navigateView("settings"));
}

if (els.newChatBtn) {
  els.newChatBtn.addEventListener("click", async () => {
    await createChatSession({title: "Nuova chat", select: true});
    navigateView("chat");
    if (els.questionInput) {
      els.questionInput.value = "";
      resetQuestionInputHeight();
      els.questionInput.focus();
    }
  });
}

if (els.searchBtn) {
  els.searchBtn.addEventListener("click", () => navigateView("search"));
}

if (els.pageContent) {
  els.pageContent.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-page-action]");
    if (!button) return;
    event.preventDefault();
    try {
      await handlePageAction(button.dataset.pageAction, button);
    } catch (error) {
      appendMessage("assistant", error.message, "errore");
    }
  });
  els.pageContent.addEventListener("input", (event) => {
    syncPageFields(event);
    if (event.target.id === "pageReviewFilter") {
      state.activeReviewFilter = event.target.value;
      renderDedicatedView("tables");
    }
    if (event.target.id === "pageMemoryQuery") {
      renderDedicatedView("memory");
    }
  });
  els.pageContent.addEventListener("keydown", async (event) => {
    if (event.target.id === "pageSearchQuery" && event.key === "Enter") {
      event.preventDefault();
      await runPageSearch();
    }
  });
  els.pageContent.addEventListener("change", async (event) => {
    syncPageFields(event);
    if (event.target.id === "pageFileInput") {
      await uploadFiles(event.target.files, {openPanel: false});
      event.target.value = "";
      renderDedicatedView("documents");
    }
    if (event.target.id === "pageReviewSort") {
      state.activeReviewSortKey = event.target.value;
      renderDedicatedView("tables");
    }
    if (event.target.id === "pageDraftTemplateSelect") {
      const value = event.target.value;
      state.pageDraft.selectedId = value;
      if (value.startsWith("tpl:")) {
        try {
          const payload = await api(`/api/draft-templates/${encodeURIComponent(value)}`);
          state.pageDraft.title = payload.template.title || "";
          state.pageDraft.paramList = (payload.template.required_params || []).join(", ");
          state.pageDraft.body = payload.template.body || "";
        } catch (error) {}
      }
      renderDedicatedView("drafts");
    }
    if (event.target.id === "pageToolSelect") {
      state.pageTool.selectedName = event.target.value;
      renderDedicatedView("tools");
    }
    if (event.target.id === "pageSettingsProvider") {
      switchPageSettingsProvider(event.target.value);
    }
    if (event.target.id === "pageSettingsBaseUrl" && state.currentView === "provider") {
      void refreshProviderModels({force: true});
    }
  });
  els.pageContent.addEventListener("blur", async (event) => {
    const cell = event.target;
    if (!cell.classList?.contains("page-editable-cell") || !state.activeReview) return;
    try {
      await api(`/api/tabular-reviews/${encodeURIComponent(state.activeReview.id)}/cell`, {
        method: "PATCH",
        body: JSON.stringify({
          row_index: Number(cell.dataset.rowIndex),
          key: cell.dataset.key,
          value: cell.textContent,
        }),
      });
    } catch (error) {
      state.pageReview.status = error.message;
      renderDedicatedView("tables");
    }
  }, true);
}

if (els.messageList) {
  els.messageList.addEventListener("click", async (event) => {
    const artifactButton = event.target.closest("[data-artifact-open]");
    if (artifactButton) {
      event.preventDefault();
      await openArtifactById(artifactButton.dataset.artifactOpen);
      return;
    }
    const button = event.target.closest("[data-copy-message-id]");
    if (!button) return;
    event.preventDefault();
    await copyMessageText(button);
  });
}

if (els.artifactClose) {
  els.artifactClose.addEventListener("click", closeArtifactPreview);
}

els.newMatterToggle.addEventListener("click", () => {
  els.newMatterForm.classList.toggle("hidden");
});

if (els.detailToggle) {
  els.detailToggle.addEventListener("click", () => toggleDetails(true));
}
if (els.composerPanelButton) {
  els.composerPanelButton.addEventListener("click", () => toggleDetails(true));
}
els.detailClose.addEventListener("click", () => toggleDetails(false));
els.sidebarToggle.addEventListener("click", () => setSidebar(!state.sidebarOpen));
els.sidebarClose.addEventListener("click", () => setSidebar(false));
els.sidebarBackdrop.addEventListener("click", () => setSidebar(false));
window.addEventListener("resize", () => {
  if (isDesktop() && state.sidebarOpen) {
    setSidebar(true);
  }
});

els.newMatterForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(els.newMatterForm);
  const payload = Object.fromEntries(form.entries());
  const result = await api("/api/matters", {method: "POST", body: JSON.stringify(payload)});
  state.matters = result.matters || [];
  state.activeMatterId = result.matter.id;
  els.newMatterForm.reset();
  els.newMatterForm.classList.add("hidden");
  renderMatterList();
  renderActiveMatter();
  await refreshMatterContext();
});

els.refreshState.addEventListener("click", loadState);

if (els.createFolderButton) {
  els.createFolderButton.addEventListener("click", async () => {
    await ensureActiveMatter();
    const name = els.folderNameInput.value.trim();
    if (!name) return;
    await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/folders`, {
      method: "POST",
      body: JSON.stringify({name}),
    });
    els.folderNameInput.value = "";
    await refreshMatterContext();
  });
}

if (els.runWorkflowButton) {
  els.runWorkflowButton.addEventListener("click", () => els.analyzeButton.click());
}

if (els.createWorkflowButton) {
  els.createWorkflowButton.addEventListener("click", async () => {
    const label = els.workflowLabelInput.value.trim();
    const requirements = parseWorkflowRequirements(els.workflowRequirementsInput.value);
    if (!label || !requirements.length) {
      els.workflowCreateStatus.textContent = "Inserisci nome e almeno un requisito.";
      return;
    }
    els.workflowCreateStatus.textContent = "Creo workflow...";
    try {
      const payload = await api("/api/workflows", {
        method: "POST",
        body: JSON.stringify({
          label,
          match_terms: label,
          requirements,
        }),
      });
      renderWorkflowOptions(payload.workflow_packs || []);
      els.workflowPackSelect.value = payload.workflow.id;
      els.workflowCreateStatus.textContent = `Workflow creato: ${payload.workflow.label}`;
    } catch (error) {
      els.workflowCreateStatus.textContent = error.message;
    }
  });
}

if (els.editWorkflowButton) {
  els.editWorkflowButton.addEventListener("click", async () => {
    const workflowId = els.workflowPackSelect.value;
    try {
      const payload = await api(`/api/workflows/${encodeURIComponent(workflowId)}`);
      state.editingWorkflowId = payload.workflow.id;
      fillWorkflowBuilder(payload.workflow, payload.versions || []);
      els.workflowCreateStatus.textContent = `Workflow caricato: ${payload.workflow.label}`;
    } catch (error) {
      state.editingWorkflowId = "";
      els.workflowCreateStatus.textContent = "I workflow builtin si possono duplicare o usare, non modificare direttamente.";
    }
  });
}

if (els.updateWorkflowButton) {
  els.updateWorkflowButton.addEventListener("click", async () => {
    const workflowId = state.editingWorkflowId || els.workflowPackSelect.value;
    const requirements = parseWorkflowRequirements(els.workflowRequirementsInput.value);
    if (!workflowId || !requirements.length) return;
    try {
      const payload = await api(`/api/workflows/${encodeURIComponent(workflowId)}`, {
        method: "PATCH",
        body: JSON.stringify({
          label: els.workflowLabelInput.value.trim(),
          match_terms: els.workflowLabelInput.value.trim(),
          requirements,
          reason: "ui_builder",
        }),
      });
      renderWorkflowOptions(payload.workflow_packs || []);
      els.workflowPackSelect.value = payload.workflow.id;
      state.editingWorkflowId = payload.workflow.id;
      fillWorkflowBuilder(payload.workflow, payload.versions || []);
      els.workflowCreateStatus.textContent = `Workflow aggiornato: ${payload.workflow.label}`;
    } catch (error) {
      els.workflowCreateStatus.textContent = error.message;
    }
  });
}

if (els.duplicateWorkflowButton) {
  els.duplicateWorkflowButton.addEventListener("click", async () => {
    const workflowId = els.workflowPackSelect.value;
    try {
      const payload = await api(`/api/workflows/${encodeURIComponent(workflowId)}/duplicate`, {
        method: "POST",
        body: JSON.stringify({label: `${els.workflowPackSelect.options[els.workflowPackSelect.selectedIndex]?.text || "Workflow"} copia`}),
      });
      renderWorkflowOptions(payload.workflow_packs || []);
      els.workflowPackSelect.value = payload.workflow.id;
      state.editingWorkflowId = payload.workflow.id;
      fillWorkflowBuilder(payload.workflow, []);
      els.workflowCreateStatus.textContent = `Workflow duplicato: ${payload.workflow.label}`;
    } catch (error) {
      els.workflowCreateStatus.textContent = error.message;
    }
  });
}

if (els.deleteWorkflowButton) {
  els.deleteWorkflowButton.addEventListener("click", async () => {
    const workflowId = els.workflowPackSelect.value;
    if (!workflowId.startsWith("custom:")) {
      els.workflowCreateStatus.textContent = "I workflow builtin non si eliminano.";
      return;
    }
    const payload = await api(`/api/workflows/${encodeURIComponent(workflowId)}`, {method: "DELETE"});
    renderWorkflowOptions(payload.workflow_packs || []);
    state.editingWorkflowId = "";
    els.workflowCreateStatus.textContent = "Workflow eliminato.";
  });
}

if (els.createReviewButton) {
  els.createReviewButton.addEventListener("click", async () => {
    await ensureActiveMatter();
    els.reviewPanel.innerHTML = `<div class="rounded-md border border-line bg-gray-50 px-3 py-3 text-gray-500">Creo tabella...</div>`;
    try {
      const payload = await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/tabular-reviews`, {
        method: "POST",
        body: JSON.stringify({
          query: els.tabularQueryInput.value.trim(),
        }),
      });
      renderReviewTable(payload.review);
    } catch (error) {
      els.reviewPanel.innerHTML = `<div class="rounded-md border border-red-200 bg-red-50 px-3 py-3 text-red-700">${escapeHtml(error.message)}</div>`;
    }
  });
}

if (els.reviewFilterInput) {
  els.reviewFilterInput.addEventListener("input", () => {
    if (state.activeReview) renderReviewTable(state.activeReview);
  });
}

if (els.reviewSortSelect) {
  els.reviewSortSelect.addEventListener("change", () => {
    state.activeReviewSortKey = els.reviewSortSelect.value;
    if (state.activeReview) renderReviewTable(state.activeReview);
  });
}

if (els.saveReviewViewButton) {
  els.saveReviewViewButton.addEventListener("click", async () => {
    if (!state.activeReview) return;
    const payload = await api(`/api/tabular-reviews/${encodeURIComponent(state.activeReview.id)}/views`, {
      method: "POST",
      body: JSON.stringify({
        name: els.reviewViewNameInput.value.trim() || "Vista",
        filter_text: els.reviewFilterInput.value.trim(),
        sort_key: els.reviewSortSelect.value,
        sort_dir: "asc",
        columns: state.activeReview.columns || [],
      }),
    });
    els.reviewViewNameInput.value = payload.view?.name || "";
  });
}

if (els.createDraftButton) {
  els.createDraftButton.addEventListener("click", async () => {
    await ensureActiveMatter();
    els.draftStatus.textContent = "Genero atto...";
    try {
      const payload = await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/drafts`, {
        method: "POST",
        body: JSON.stringify({
          template_name: els.draftTemplateSelect.value,
          as_of_date: els.draftAsOfDate.value.trim(),
          params: parseJsonObject(els.draftParamsInput.value, {}),
        }),
      });
      if (payload.document) {
        els.draftStatus.textContent = `Atto salvato: ${payload.document.title}`;
        await refreshMatterContext();
        await openMatterDocument(payload.document.id);
      } else {
        els.draftStatus.textContent = payload.draft?.reason || "Atto non generato.";
        renderAudit(payload.draft || payload);
      }
    } catch (error) {
      els.draftStatus.textContent = error.message;
    }
  });
}

if (els.previewDraftButton) {
  els.previewDraftButton.addEventListener("click", async () => {
    try {
      const payload = await api(`/api/draft-templates/${encodeURIComponent(els.draftTemplateSelect.value)}/preview`, {
        method: "POST",
        body: JSON.stringify({params: parseJsonObject(els.draftParamsInput.value, {})}),
      });
      els.draftPreviewPanel.textContent = payload.rendered || "";
      els.draftStatus.textContent = "Anteprima aggiornata.";
    } catch (error) {
      els.draftStatus.textContent = "Anteprima disponibile per i template creati qui. Per quelli predefiniti usa Genera e salva.";
    }
  });
}

if (els.saveDraftTemplateButton) {
  els.saveDraftTemplateButton.addEventListener("click", async () => {
    const title = els.draftTemplateTitleInput.value.trim();
    const body = els.draftTemplateBodyInput.value.trim();
    if (!title || !body) {
      els.draftStatus.textContent = "Inserisci titolo e corpo del template.";
      return;
    }
    const payload = await api("/api/draft-templates", {
      method: "POST",
      body: JSON.stringify({
        title,
        name: title,
        body,
        required_params: splitTerms(els.draftTemplateParamsInput.value),
      }),
    });
    state.draftTemplates = payload.templates || [];
    els.draftTemplateSelect.innerHTML = state.draftTemplates.map((template) => `<option value="${escapeHtml(template.id || template.name)}">${escapeHtml(template.title || template.name)}${template.source === "sqlite" ? " · creato" : ""}</option>`).join("");
    els.draftTemplateSelect.value = payload.template.id;
    els.draftStatus.textContent = `Template salvato: ${payload.template.title}`;
  });
}

if (els.draftTemplateSelect) {
  els.draftTemplateSelect.addEventListener("change", async () => {
    const value = els.draftTemplateSelect.value;
    if (!value.startsWith("tpl:")) return;
    const payload = await api(`/api/draft-templates/${encodeURIComponent(value)}`);
    els.draftTemplateTitleInput.value = payload.template.title || "";
    els.draftTemplateParamsInput.value = (payload.template.required_params || []).join(", ");
    els.draftTemplateBodyInput.value = payload.template.body || "";
  });
}

if (els.runToolButton) {
  els.runToolButton.addEventListener("click", async () => {
    els.toolOutput.textContent = "Esecuzione tool...";
    try {
      const payload = await api("/api/tools/call", {
        method: "POST",
        body: JSON.stringify({
          name: els.toolSelect.value,
          arguments: parseJsonObject(els.toolArgsInput.value, {}),
        }),
      });
      els.toolOutput.textContent = JSON.stringify(payload.result, null, 2);
    } catch (error) {
      els.toolOutput.textContent = error.message;
    }
  });
}

if (els.saveDocumentEditButton) {
  els.saveDocumentEditButton.addEventListener("click", async () => {
    if (!state.activeDocumentId) return;
    const payload = await api(`/api/matter-documents/${encodeURIComponent(state.activeDocumentId)}/edits`, {
      method: "POST",
      body: JSON.stringify({revised_content: els.documentEditContent.value}),
    });
    const edit = payload.edit;
    state.lastEditId = edit.id;
    els.documentEditDiff.textContent = (edit.diff || []).join("\n");
  });
}

if (els.applyDocumentEditButton) {
  els.applyDocumentEditButton.addEventListener("click", async () => {
    if (!state.lastEditId) return;
    const payload = await api(`/api/document-edits/${encodeURIComponent(state.lastEditId)}/apply`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    if (payload.document) {
      await refreshMatterContext();
      await openMatterDocument(payload.document.id);
    }
  });
}

if (els.pdfZoomIn) {
  els.pdfZoomIn.addEventListener("click", async () => {
    state.pdfZoom = Math.min(2, state.pdfZoom + 0.15);
    if (state.activeDocumentId) await openMatterDocument(state.activeDocumentId);
  });
}

if (els.pdfZoomOut) {
  els.pdfZoomOut.addEventListener("click", async () => {
    state.pdfZoom = Math.max(0.5, state.pdfZoom - 0.15);
    if (state.activeDocumentId) await openMatterDocument(state.activeDocumentId);
  });
}

if (els.pdfPageInput) {
  els.pdfPageInput.addEventListener("change", async () => {
    state.pdfPage = Math.max(1, Number(els.pdfPageInput.value || 1));
    if (state.activeDocumentId) await openMatterDocument(state.activeDocumentId);
  });
}

if (els.ocrDocumentButton) {
  els.ocrDocumentButton.addEventListener("click", async () => {
    if (!state.activeDocumentId) return;
    els.documentPreviewContent.textContent = "OCR in corso...";
    const payload = await api(`/api/matter-documents/${encodeURIComponent(state.activeDocumentId)}/ocr`, {
      method: "POST",
      body: JSON.stringify({apply: true}),
    });
    const ocr = payload.ocr || {};
    els.documentPreviewContent.textContent = ocr.text || ocr.note || ocr.status || "OCR completato senza testo.";
    if (payload.document) {
      await refreshMatterContext();
      await openMatterDocument(payload.document.id);
    }
  });
}

if (els.addAnnotationButton) {
  els.addAnnotationButton.addEventListener("click", async () => {
    if (!state.activeDocumentId) return;
    const note = els.documentAnnotationNote.value.trim();
    if (!note) return;
    await api(`/api/matter-documents/${encodeURIComponent(state.activeDocumentId)}/annotations`, {
      method: "POST",
      body: JSON.stringify({page_number: state.pdfPage || 1, note}),
    });
    els.documentAnnotationNote.value = "";
    await openMatterDocument(state.activeDocumentId);
  });
}

if (els.addCommentButton) {
  els.addCommentButton.addEventListener("click", async () => {
    if (!state.activeDocumentId) return;
    const body = els.documentCommentInput.value.trim();
    if (!body) return;
    await api(`/api/matter-documents/${encodeURIComponent(state.activeDocumentId)}/comments`, {
      method: "POST",
      body: JSON.stringify({body}),
    });
    els.documentCommentInput.value = "";
    await openMatterDocument(state.activeDocumentId);
  });
}

if (els.compareCurrentButton) {
  els.compareCurrentButton.addEventListener("click", async () => {
    if (!state.activeDocumentId) return;
    const payload = await api(`/api/matter-documents/${encodeURIComponent(state.activeDocumentId)}/versions`);
    const latest = (payload.versions || [])[0];
    if (!latest) return;
    const comparison = await api(`/api/matter-documents/${encodeURIComponent(state.activeDocumentId)}/versions/${encodeURIComponent(latest.id)}/compare`);
    els.documentComparePanel.textContent = (comparison.comparison?.diff || []).join("\n");
  });
}

els.chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = els.questionInput.value.trim();
  if (!question) return;
  await ensureChatSession(question);
  els.questionInput.value = "";
  resetQuestionInputHeight();
  appendMessage("user", question);
  await persistChatMessage("user", question);
  state.recentUserTurns.push(question);
  state.recentUserTurns = state.recentUserTurns.slice(-6);
  els.sendButton.disabled = true;
  const placeholder = appendThinkingPlaceholder();
  try {
    const result = await streamAnswer({
      question,
      area: els.areaInput.value.trim(),
      matter_id: state.activeMatterId,
      recent_user_turns: state.recentUserTurns.slice(0, -1),
    }, placeholder);
    removePlaceholder(placeholder);
    renderResult(result);
    await persistChatMessage("assistant", result.answer || result.reason || "Risposta completata.", {
      status: result.status || "",
      citations: (result.citations || []).length,
      label: "risposta",
    });
    await maybeCreateArtifactFromChat(question, result);
    await refreshMatterContext();
  } catch (error) {
    removePlaceholder(placeholder);
    appendMessage("assistant", error.message, "errore");
    await persistChatMessage("assistant", error.message, {label: "errore"});
  } finally {
    els.sendButton.disabled = false;
  }
});

function appendThinkingPlaceholder() {
  const wrap = document.createElement("div");
  wrap.className = "mb-4 flex justify-start judicex-thinking";
  wrap.innerHTML = `
    <div class="w-full max-w-2xl rounded-lg border border-line bg-white px-4 py-3 shadow-sm">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <div class="text-sm font-medium text-ink">Judicex sta lavorando</div>
          <div data-thinking-title class="mt-1 text-xs font-medium text-gray-600">Capisco cosa serve</div>
          <div data-thinking-detail class="mt-0.5 text-xs leading-5 text-gray-500">Leggo la richiesta e preparo i passaggi utili.</div>
        </div>
        <span class="inline-flex items-center gap-1">
          <span class="thinking-dot"></span>
          <span class="thinking-dot"></span>
          <span class="thinking-dot"></span>
        </span>
      </div>
      <div data-thinking-count class="mt-2 text-[11px] text-gray-400"></div>
    </div>
  `;
  els.messageList.appendChild(wrap);
  scrollChatToBottom();
  return wrap;
}

function removePlaceholder(node) {
  if (node && node.parentNode) node.parentNode.removeChild(node);
}

els.analyzeButton.addEventListener("click", async () => {
  await ensureActiveMatter();
  const thesis = els.workflowThesisInput?.value.trim() || els.thesisInput.value.trim() || els.questionInput.value.trim() || "analisi generale del fascicolo";
  appendMessage("user", thesis, "analisi fascicolo");
  try {
    const payload = await api("/api/workflows/run", {
      method: "POST",
      body: JSON.stringify({
        matter_id: state.activeMatterId,
        thesis,
        workflow_pack: els.workflowPackSelect.value,
      }),
    });
    const analysis = payload.analysis;
    renderResult({
      status: "analysis",
      answer: analysisToText(analysis),
      matter_analysis: analysis,
      case_facts: [],
      citations: [],
      answer_contract: {status: "skipped", reason: "manual_matter_analysis"},
      semantic_verifier: {status: "skipped", reason: "manual_matter_analysis"},
    });
    if (els.workflowPanel) {
      els.workflowPanel.innerHTML = `<div class="rounded-md border border-line bg-gray-50 p-2 text-xs leading-5">${nl2br(analysisToText(analysis))}</div>`;
    }
  } catch (error) {
    appendMessage("assistant", error.message, "errore");
  }
});

function analysisToText(analysis) {
  const lines = [
    `Analisi fascicolo: ${analysis.profile?.label || "profilo"}.`,
    `Stato: ${analysis.status} (${analysis.readiness_score}%).`,
  ];
  if (analysis.present_requirements?.length) {
    lines.push("Elementi presenti:");
    analysis.present_requirements.forEach((item) => lines.push(`- ${item.label}`));
  }
  if (analysis.partial_requirements?.length) {
    lines.push("Elementi parziali:");
    analysis.partial_requirements.forEach((item) => lines.push(`- ${item.label}`));
  }
  if (analysis.missing_requirements?.length) {
    lines.push("Elementi mancanti:");
    analysis.missing_requirements.forEach((item) => lines.push(`- ${item.label}: ${item.suggestion}`));
  }
  if (analysis.next_actions?.length) {
    lines.push("Prossime azioni:");
    analysis.next_actions.forEach((item) => lines.push(`- ${item}`));
  }
  return lines.join("\n");
}

els.chooseFiles.addEventListener("click", () => els.fileInput.click());
els.fileInput.addEventListener("change", () => uploadFiles(els.fileInput.files));

["dragenter", "dragover"].forEach((name) => {
  els.dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    els.dropZone.classList.add("border-accent", "bg-slate-50");
  });
});

["dragleave", "drop"].forEach((name) => {
  els.dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    els.dropZone.classList.remove("border-accent", "bg-slate-50");
  });
});

els.dropZone.addEventListener("drop", (event) => uploadFiles(event.dataTransfer.files));

els.chatDeleteCancel?.addEventListener("click", closeChatDeleteModal);
els.chatDeleteConfirm?.addEventListener("click", async () => {
  const sessionId = state.pendingDeleteChatSessionId;
  closeChatDeleteModal();
  await deleteChatSession(sessionId);
});
els.chatDeleteModal?.addEventListener("click", (event) => {
  if (event.target === els.chatDeleteModal) closeChatDeleteModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !els.chatDeleteModal?.classList.contains("hidden")) {
    closeChatDeleteModal();
  }
});

async function uploadFiles(files, options = {}) {
  if (!files?.length) return;
  await ensureActiveMatter();
  const body = new FormData();
  Array.from(files).forEach((file) => body.append("files", file));
  els.uploadStatus.textContent = `${files.length} file in caricamento...`;
  try {
    const payload = await api(`/api/matters/${encodeURIComponent(state.activeMatterId)}/documents`, {
      method: "POST",
      body,
    });
    const ok = payload.uploads.filter((item) => item.status === "ok").length;
    const failed = payload.uploads.length - ok;
    const errors = payload.uploads
      .filter((item) => item.status === "error")
      .map((item) => `${item.filename}: ${item.error}`)
      .join(" | ");
    els.uploadStatus.textContent = errors ? `${ok} caricati, ${failed} errori - ${errors}` : `${ok} file caricati`;
    await refreshMatterContext();
    renderAudit(payload);
    if (options.openPanel !== false) {
      toggleDetails(true);
    }
  } catch (error) {
    els.uploadStatus.textContent = error.message;
  }
}

async function ensureActiveMatter() {
  if (state.activeMatterId) return state.activeMatterId;
  const payload = {
    title: "Documenti recenti",
    client_name: "",
    area: els.areaInput.value.trim() || state.defaults.area || "civile",
    summary: "Fascicolo automatico per upload e prime analisi."
  };
  const result = await api("/api/matters", {method: "POST", body: JSON.stringify(payload)});
  state.matters = result.matters || [];
  state.activeMatterId = result.matter.id;
  renderMatterList();
  renderActiveMatter();
  return state.activeMatterId;
}

loadState().catch((error) => {
  appendMessage("assistant", error.message, "errore inizializzazione");
});
setSidebar(state.sidebarOpen);

const statuses = ["inbox", "ready", "in_progress", "blocked", "review", "done"];
const labels = {
  inbox: "Inbox",
  ready: "Ready",
  in_progress: "In progress",
  blocked: "Blocked",
  review: "Review",
  done: "Done",
};
const involvement = {
  low: ["Low touch", "Agent can deliver; human reviews."],
  medium: ["Collaborative", "Needs editor work or a bounded decision."],
  high: ["Human led", "Creative, directional, or hands-on work."],
};

const state = {
  tickets: [],
  project: "",
  selectedId: null,
  search: "",
  intervention: "all",
  initialized: false,
  refreshTimer: null,
  browsingPath: "",
};

const byId = (id) => document.getElementById(id);

function syncThemeButton() {
  const dark = document.documentElement.dataset.theme === "dark";
  byId("theme-toggle").textContent = dark ? "☀ Light" : "☾ Dark";
  byId("theme-toggle").setAttribute(
    "aria-label",
    dark ? "Switch to light theme" : "Switch to dark theme",
  );
}

syncThemeButton();

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "Something went wrong");
    error.status = response.status;
    throw error;
  }
  return data;
}

function setNotice(message, isError = false) {
  const notice = byId("notice");
  notice.textContent = message;
  notice.classList.toggle("error", isError);
}

function applyProject(data, announce = true) {
  state.tickets = data.tickets || [];
  state.project = data.project;
  state.initialized = data.initialized;
  byId("project-name").textContent = data.name;
  byId("project-path").value = data.project;
  byId("initialize-project").classList.toggle("hidden", data.initialized);
  byId("controls").classList.toggle("hidden", !data.initialized);
  byId("board").classList.toggle("hidden", !data.initialized);
  if (announce) {
    setNotice(
      data.initialized
        ? `${state.tickets.length} Markdown ticket${state.tickets.length === 1 ? "" : "s"} loaded`
        : "This folder does not have a .kanban board yet",
    );
  }
  renderBoard();
  startRefreshing();
}

async function openPath(path) {
  try {
    const data = await api("/api/open", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    applyProject(data);
  } catch (error) {
    setNotice(error.message, true);
  }
}

function filteredTickets() {
  const query = state.search.trim().toLowerCase();
  return state.tickets.filter((ticket) => {
    if (state.intervention !== "all" && ticket.intervention !== state.intervention) {
      return false;
    }
    const haystack = [
      ticket.id,
      ticket.title,
      ticket.category,
      ticket.type,
      ...(ticket.tags || []),
      ticket.body,
    ].join(" ").toLowerCase();
    return !query || haystack.includes(query);
  });
}

function element(name, className, text) {
  const node = document.createElement(name);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function ticketCard(ticket) {
  const card = element("button", "ticket-card");
  card.type = "button";
  card.draggable = true;
  card.dataset.ticketId = ticket.id;
  card.addEventListener("click", () => openTicket(ticket.id));
  card.addEventListener("dragstart", (event) => {
    event.dataTransfer.setData("text/plain", ticket.id);
    event.dataTransfer.effectAllowed = "move";
    card.classList.add("dragging");
  });
  card.addEventListener("dragend", () => card.classList.remove("dragging"));

  const top = element("span", "ticket-topline");
  top.append(element("span", "ticket-id", ticket.id));
  if (ticket.priority) top.append(element("span", `priority priority-${ticket.priority}`));
  card.append(top, element("strong", "", ticket.title));

  const meta = element("span", "ticket-meta");
  meta.append(element("span", `intervention intervention-${ticket.intervention}`, involvement[ticket.intervention][0]));
  if (ticket.type) meta.append(element("span", "", ticket.type));
  card.append(meta);

  if (ticket.blocked_by?.length) {
    card.append(element("span", "dependency", `Blocked by ${ticket.blocked_by.join(", ")}`));
  }
  return card;
}

function makeColumn(status, tickets) {
  const column = element("article", `column column-${status}`);
  column.dataset.status = status;
  column.addEventListener("dragover", (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    column.classList.add("drop-target");
  });
  column.addEventListener("dragleave", () => column.classList.remove("drop-target"));
  column.addEventListener("drop", async (event) => {
    event.preventDefault();
    column.classList.remove("drop-target");
    const ticketId = event.dataTransfer.getData("text/plain");
    await moveTicket(ticketId, status);
  });

  const header = element("div", "column-header");
  const title = element("div");
  title.append(element("span", "column-kicker", status === "ready" ? "Categorized backlog" : "Workflow"));
  title.append(element("h2", "", labels[status]));
  header.append(title, element("span", "count", String(tickets.length)));
  column.append(header);

  if (status === "ready") {
    column.classList.add("ready-column");
    const categories = new Map();
    tickets.forEach((ticket) => {
      if (!categories.has(ticket.category)) categories.set(ticket.category, []);
      categories.get(ticket.category).push(ticket);
    });
    [...categories.entries()].sort(([a], [b]) => a.localeCompare(b)).forEach(([category, items]) => {
      const section = element("section", "category");
      const heading = element("div", "category-heading");
      heading.append(element("h3", "", category), element("span", "", String(items.length)));
      const list = element("div", "card-list");
      items.forEach((ticket) => list.append(ticketCard(ticket)));
      section.append(heading, list);
      column.append(section);
    });
  } else {
    const list = element("div", "card-list");
    tickets.forEach((ticket) => list.append(ticketCard(ticket)));
    column.append(list);
  }

  if (!tickets.length) column.append(element("p", "empty", "Nothing here"));
  return column;
}

function renderBoard() {
  const board = byId("board");
  board.replaceChildren();
  const tickets = filteredTickets();
  const displayOrder = ["ready", "inbox", "in_progress", "blocked", "review", "done"];
  displayOrder.forEach((status) => {
    board.append(makeColumn(status, tickets.filter((ticket) => ticket.status === status)));
  });
  byId("ticket-total").textContent = `${state.tickets.length} tickets · local-first · no account required`;
}

function renderMarkdown(source) {
  const container = byId("drawer-body");
  container.replaceChildren();
  source.split(/\r?\n/).forEach((line) => {
    if (line.startsWith("## ")) container.append(element("h3", "", line.slice(3)));
    else if (line.startsWith("- [ ] ")) container.append(element("p", "", `☐ ${line.slice(6)}`));
    else if (line.toLowerCase().startsWith("- [x] ")) container.append(element("p", "", `☑ ${line.slice(6)}`));
    else if (line.startsWith("- ")) container.append(element("p", "", `• ${line.slice(2)}`));
    else if (line) container.append(element("p", "", line));
    else container.append(document.createElement("br"));
  });
}

function openTicket(ticketId) {
  const ticket = state.tickets.find((item) => item.id === ticketId);
  if (!ticket) return;
  state.selectedId = ticketId;
  byId("drawer-id").textContent = ticket.id;
  byId("drawer-title").textContent = ticket.title;

  const facts = byId("drawer-facts");
  facts.replaceChildren();
  [
    ["Category", ticket.category],
    ["Human involvement", involvement[ticket.intervention][0], involvement[ticket.intervention][1]],
    ["Type", ticket.type || "Unspecified"],
  ].forEach(([label, value, detail]) => {
    const fact = element("div");
    fact.append(element("span", "", label), element("strong", "", value));
    if (detail) fact.append(element("small", "", detail));
    facts.append(fact);
  });

  renderMarkdown(ticket.body);
  const mover = byId("status-mover");
  mover.replaceChildren();
  statuses.forEach((status) => {
    const button = element("button", ticket.status === status ? "active" : "", labels[status]);
    button.addEventListener("click", () => moveTicket(ticket.id, status));
    mover.append(button);
  });
  byId("ticket-scrim").classList.remove("hidden");
}

async function moveTicket(ticketId, status) {
  const ticket = state.tickets.find((item) => item.id === ticketId);
  if (!ticket || ticket.status === status) return;
  try {
    const updated = await api(`/api/tickets/${encodeURIComponent(ticketId)}`, {
      method: "PATCH",
      body: JSON.stringify({ status, modified_ns: ticket.modified_ns }),
    });
    state.tickets = state.tickets.map((item) => item.id === ticketId ? updated : item);
    setNotice(`${ticketId} moved to ${labels[status]}`);
    renderBoard();
    if (state.selectedId === ticketId) openTicket(ticketId);
  } catch (error) {
    setNotice(error.message, true);
    await refreshTickets();
  }
}

async function refreshTickets() {
  if (document.hidden) return;
  try {
    const data = await api("/api/tickets");
    const before = JSON.stringify([
      state.project,
      state.initialized,
      state.tickets.map((ticket) => [ticket.id, ticket.modified_ns]),
    ]);
    const after = JSON.stringify([
      data.project,
      data.initialized,
      data.tickets.map((ticket) => [ticket.id, ticket.modified_ns]),
    ]);
    if (before !== after) applyProject(data, false);
  } catch {
    // The next explicit action will surface a useful error.
  }
}

function startRefreshing() {
  if (state.refreshTimer) clearInterval(state.refreshTimer);
  state.refreshTimer = setInterval(refreshTickets, 2000);
}

async function loadStartupProject() {
  try {
    applyProject(await api("/api/tickets"));
  } catch (error) {
    if (error.status !== 409) setNotice(error.message, true);
  }
}

byId("open-project").addEventListener("click", () => byId("project-picker").scrollIntoView({ behavior: "smooth" }));
byId("theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("kanban-md-theme", next);
  syncThemeButton();
});
byId("load-project").addEventListener("click", () => openPath(byId("project-path").value));
byId("project-path").addEventListener("keydown", (event) => {
  if (event.key === "Enter") openPath(event.currentTarget.value);
});
async function browseDirectory(path = "") {
  try {
    const data = await api(`/api/directories?path=${encodeURIComponent(path)}`);
    state.browsingPath = data.drives ? "::drives" : data.current;
    byId("folder-current").textContent = data.current;
    byId("folder-up").disabled = !data.parent;
    byId("folder-up").dataset.path = data.parent || "";
    byId("choose-folder").disabled = data.drives;
    const list = byId("folder-list");
    list.replaceChildren();
    data.directories.forEach((directory) => {
      const button = element("button", "folder-row");
      button.type = "button";
      button.append(element("span", "folder-icon", "▰"), element("span", "", directory.name));
      button.addEventListener("dblclick", () => browseDirectory(directory.path));
      button.addEventListener("click", () => {
        list.querySelectorAll(".folder-row").forEach((item) => item.classList.remove("selected"));
        button.classList.add("selected");
        state.browsingPath = directory.path;
      });
      list.append(button);
    });
    byId("folder-scrim").classList.remove("hidden");
  } catch (error) {
    setNotice(error.message, true);
  }
}

byId("browse-project").addEventListener("click", () => {
  browseDirectory(byId("project-path").value.trim());
});
byId("folder-drives").addEventListener("click", () => browseDirectory("::drives"));
byId("folder-up").addEventListener("click", (event) => browseDirectory(event.currentTarget.dataset.path));
byId("folder-list").addEventListener("dblclick", () => {});
byId("cancel-folder").addEventListener("click", () => byId("folder-scrim").classList.add("hidden"));
byId("choose-folder").addEventListener("click", async () => {
  if (!state.browsingPath || state.browsingPath === "::drives") return;
  byId("folder-scrim").classList.add("hidden");
  byId("project-path").value = state.browsingPath;
  await openPath(state.browsingPath);
});
byId("folder-scrim").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.classList.add("hidden");
});
byId("initialize-project").addEventListener("click", async () => {
  try {
    applyProject(await api("/api/initialize", { method: "POST", body: "{}" }));
  } catch (error) {
    setNotice(error.message, true);
  }
});
byId("search").addEventListener("input", (event) => {
  state.search = event.target.value;
  renderBoard();
});
byId("intervention-filter").addEventListener("click", (event) => {
  const button = event.target.closest("[data-level]");
  if (!button) return;
  state.intervention = button.dataset.level;
  document.querySelectorAll(".filter").forEach((item) => item.classList.toggle("active", item === button));
  renderBoard();
});
async function showNextId() {
  const label = byId("create-id");
  label.textContent = "…";
  try {
    label.textContent = (await api("/api/next-id")).id;
  } catch (error) {
    label.textContent = "unavailable";
    setNotice(error.message, true);
  }
}

byId("new-ticket").addEventListener("click", () => {
  byId("create-scrim").classList.remove("hidden");
  showNextId();
});
byId("cancel-create").addEventListener("click", () => byId("create-scrim").classList.add("hidden"));
byId("submit-create").addEventListener("click", async () => {
  try {
    const ticket = await api("/api/tickets", {
      method: "POST",
      body: JSON.stringify({
        title: byId("create-title").value,
        category: byId("create-category").value,
        intervention: byId("create-intervention").value,
      }),
    });
    state.tickets.push(ticket);
    byId("create-title").value = "";
    byId("create-scrim").classList.add("hidden");
    setNotice(`${ticket.id} created in Inbox`);
    renderBoard();
  } catch (error) {
    setNotice(error.message, true);
  }
});
byId("close-ticket").addEventListener("click", () => byId("ticket-scrim").classList.add("hidden"));
byId("ticket-scrim").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.classList.add("hidden");
});
byId("create-scrim").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.classList.add("hidden");
});

loadStartupProject();
startRefreshing();

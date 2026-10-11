/**
 * Follower Vault - Multi-Tenant Interactive Frontend Engine
 * Includes User Authentication, Async Upload Progress Polling, and Swipe Triage
 */

// Sound FX Synth (Web Audio API)
class SoundFX {
  constructor() {
    this.enabled = true;
    this.ctx = null;
  }

  init() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) this.ctx = new AudioCtx();
    }
  }

  playWhoosh(direction = 1) {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;
    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    const now = this.ctx.currentTime;
    osc.type = "sine";
    const startFreq = direction > 0 ? 300 : 500;
    const endFreq = direction > 0 ? 600 : 200;
    osc.frequency.setValueAtTime(startFreq, now);
    osc.frequency.exponentialRampToValueAtTime(endFreq, now + 0.15);
    gain.gain.setValueAtTime(0.08, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.15);
    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start(now);
    osc.stop(now + 0.15);
  }

  playChime(type = "success") {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;
    const now = this.ctx.currentTime;
    const freqs = type === "success" ? [523.25, 659.25] : [440, 349.23];
    freqs.forEach((f, i) => {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(f, now + i * 0.08);
      gain.gain.setValueAtTime(0.06, now + i * 0.08);
      gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.08 + 0.2);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start(now + i * 0.08);
      osc.stop(now + i * 0.08 + 0.2);
    });
  }
}

const sfx = new SoundFX();

// State
const state = {
  currentUser: null,
  token: localStorage.getItem("vault_token") || null,
  activeTab: "swipe",
  metrics: null,
  deck: [],
  currentCardIndex: 0,
  activeSnapshotId: null,
  snapshots: [],
  tableAccounts: [],
  tableFilter: "all",
  tableSearch: "",
  selectedUsernames: new Set(),
};

// Utilities
function hashColor(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const h = Math.abs(hash % 360);
  return `linear-gradient(135deg, hsl(${h}, 70%, 55%), hsl(${(h + 40) % 360}, 80%, 45%))`;
}

function showToast(message, icon = "ℹ️") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `<span>${icon}</span> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 2800);
}

// Authenticated Fetch Helper
async function apiFetch(url, options = {}) {
  const headers = options.headers || {};
  if (state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
  }
  options.headers = headers;
  const res = await fetch(url, options);
  if (res.status === 401 && state.token) {
    // Token expired or invalid
    state.token = null;
    localStorage.removeItem("vault_token");
    renderAuthHeader();
  }
  return res;
}

// Auth API Calls
async function fetchMe() {
  if (!state.token) return null;
  try {
    const res = await apiFetch("/api/auth/me");
    if (res.ok) return await res.json();
  } catch (err) {}
  return null;
}

async function loginApi(email, password) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  return await res.json();
}

async function registerApi(email, password, display_name) {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name }),
  });
  return await res.json();
}

async function demoLoginApi() {
  const res = await fetch("/api/auth/demo", { method: "POST" });
  return await res.json();
}

// Core API Calls
async function fetchStatus() {
  const res = await apiFetch("/api/status");
  return await res.json();
}

async function fetchMetrics(snapshotId = null) {
  const url = snapshotId ? `/api/metrics?snapshot_id=${snapshotId}` : "/api/metrics";
  const res = await apiFetch(url);
  return await res.json();
}

async function fetchSnapshots() {
  const res = await apiFetch("/api/snapshots");
  return await res.json();
}

async function fetchDeck(limit = 60) {
  const url = state.activeSnapshotId ? `/api/swipe/deck?snapshot_id=${state.activeSnapshotId}&limit=${limit}` : `/api/swipe/deck?limit=${limit}`;
  const res = await apiFetch(url);
  return await res.json();
}

async function postDecision(username, decision, tags = [], notes = null) {
  const res = await apiFetch("/api/swipe/decision", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, decision, tags, notes }),
  });
  return await res.json();
}

async function postUndo() {
  const res = await apiFetch("/api/swipe/undo", { method: "POST" });
  return await res.json();
}

async function postRecompute() {
  const url = state.activeSnapshotId ? `/api/recompute?snapshot_id=${state.activeSnapshotId}` : "/api/recompute";
  const res = await apiFetch(url, { method: "POST" });
  return await res.json();
}

async function postDemoLoad() {
  const res = await apiFetch("/api/demo/load", { method: "POST" });
  return await res.json();
}

async function fetchAccounts(params = {}) {
  const query = new URLSearchParams(params);
  if (state.activeSnapshotId) query.set("snapshot_id", state.activeSnapshotId);
  const res = await apiFetch(`/api/accounts?${query.toString()}`);
  return await res.json();
}

// Metrics Rendering
function renderMetrics(metrics) {
  state.metrics = metrics;
  if (!metrics) return;

  const rate = metrics.reciprocity_rate || 0;
  const gaugeFill = document.getElementById("gaugeFill");
  const gaugeVal = document.getElementById("gaugeVal");
  if (gaugeFill && gaugeVal) {
    const circumference = 283;
    const offset = circumference - (rate / 100) * circumference;
    gaugeFill.style.strokeDasharray = `${circumference}`;
    gaugeFill.style.strokeDashoffset = `${offset}`;
    gaugeVal.textContent = `${rate}%`;
  }

  document.getElementById("kpiTotalFollowing").textContent = metrics.total_following.toLocaleString();
  document.getElementById("kpiTotalFollowers").textContent = metrics.total_followers.toLocaleString();
  document.getElementById("kpiMutuals").textContent = metrics.mutual_count.toLocaleString();
  document.getElementById("kpiFans").textContent = metrics.fan_count.toLocaleString();
  document.getElementById("kpiWhitelisted").textContent = metrics.whitelisted_count.toLocaleString();
  document.getElementById("kpiActionable").textContent = metrics.actionable_unreciprocated_count.toLocaleString();
  document.getElementById("kpiRawUnreciprocated").textContent = metrics.unreciprocated_raw_count.toLocaleString();

  const deckBadge = document.getElementById("deckBadge");
  if (deckBadge) deckBadge.textContent = metrics.actionable_unreciprocated_count;
}

// Swipe Deck Rendering
function renderDeck() {
  const container = document.getElementById("deckContainer");
  container.innerHTML = "";

  const remaining = state.deck.slice(state.currentCardIndex);

  if (remaining.length === 0) {
    container.innerHTML = `
      <div class="swipe-card" style="align-items: center; justify-content: center; text-align: center;">
        <div style="font-size: 3rem; margin-bottom: 12px;">🎉</div>
        <h3 style="margin-bottom: 8px;">Inbox Zero Achieved!</h3>
        <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 16px;">
          You have triaged all unreciprocated accounts. Explore the Audit Table or recompute metrics!
        </p>
        <button class="btn btn-secondary" onclick="loadDeck()">Fetch More Accounts</button>
      </div>
    `;
    return;
  }

  const cardsToShow = remaining.slice(0, 3);
  cardsToShow.forEach((acc, idx) => {
    const cardEl = document.createElement("div");
    cardEl.className = "swipe-card";
    if (idx === 1) cardEl.classList.add("card-bg-1");
    if (idx === 2) cardEl.classList.add("card-bg-2");

    const initials = acc.username.slice(0, 2).toUpperCase();
    const gradient = hashColor(acc.username);

    // Stamps
    const stampKeep = document.createElement("div");
    stampKeep.className = "stamp stamp-keep";
    stampKeep.textContent = "KEEP / SAFE";

    const stampUnfollow = document.createElement("div");
    stampUnfollow.className = "stamp stamp-unfollow";
    stampUnfollow.textContent = "UNFOLLOW";

    const stampVip = document.createElement("div");
    stampVip.className = "stamp stamp-vip";
    stampVip.textContent = "★ VIP";

    cardEl.appendChild(stampKeep);
    cardEl.appendChild(stampUnfollow);
    cardEl.appendChild(stampVip);

    // Header
    const headerRow = document.createElement("div");
    headerRow.className = "card-header-row";
    headerRow.innerHTML = `
      <div class="card-avatar" style="background: ${gradient};">${initials}</div>
      <div class="card-titles">
        <a class="card-username" href="${acc.profile_url}" target="_blank" rel="noopener">
          @${acc.username}
          <span style="font-size: 0.75rem; color: #38bdf8;">↗</span>
        </a>
        <div class="card-followed-at">
          ${acc.followed_at ? `🗓️ Followed ${acc.followed_at}` : "🗓️ Followed date unknown"}
        </div>
      </div>
    `;

    // Body
    const bodySection = document.createElement("div");
    bodySection.className = "card-body-section";

    const statusChip = document.createElement("div");
    statusChip.className = "status-chip unreciprocated";
    statusChip.innerHTML = `⚠️ Does Not Follow You Back`;

    const tagsRow = document.createElement("div");
    tagsRow.className = "tags-row";
    if (acc.tags && acc.tags.length > 0) {
      acc.tags.forEach(t => {
        const tb = document.createElement("span");
        tb.className = "tag-badge suggested";
        tb.textContent = `#${t}`;
        tagsRow.appendChild(tb);
      });
    }

    const quickActions = document.createElement("div");
    quickActions.className = "card-quick-actions";
    const commonTags = ["Brand", "Celebrity", "Friend", "Creator"];
    commonTags.forEach(tagName => {
      const pill = document.createElement("button");
      pill.type = "button";
      pill.className = "pill-toggle";
      pill.textContent = `+ ${tagName}`;
      pill.onclick = (e) => {
        e.stopPropagation();
        pill.classList.toggle("active");
        if (!acc._selectedTags) acc._selectedTags = new Set(acc.tags || []);
        if (pill.classList.contains("active")) {
          acc._selectedTags.add(tagName.toLowerCase());
        } else {
          acc._selectedTags.delete(tagName.toLowerCase());
        }
      };
      quickActions.appendChild(pill);
    });

    bodySection.appendChild(statusChip);
    if (tagsRow.children.length > 0) bodySection.appendChild(tagsRow);
    bodySection.appendChild(quickActions);

    // Footer
    const footerLink = document.createElement("div");
    footerLink.className = "card-footer-link";
    footerLink.innerHTML = `
      <span style="font-size: 0.75rem; color: var(--text-muted);">Swipe or press [← / →]</span>
      <a class="ig-external-link" href="${acc.profile_url}" target="_blank" rel="noopener">
        View on Instagram ↗
      </a>
    `;

    cardEl.appendChild(headerRow);
    cardEl.appendChild(bodySection);
    cardEl.appendChild(footerLink);

    if (idx === 0) {
      setupCardGestures(cardEl, acc);
    }

    container.appendChild(cardEl);
  });
}

function setupCardGestures(cardEl, account) {
  let isDragging = false;
  let startX = 0;
  let startY = 0;
  let currentX = 0;
  let currentY = 0;

  const stampKeep = cardEl.querySelector(".stamp-keep");
  const stampUnfollow = cardEl.querySelector(".stamp-unfollow");
  const stampVip = cardEl.querySelector(".stamp-vip");

  function onPointerDown(e) {
    if (e.target.closest("button") || e.target.closest("a")) return;
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    cardEl.style.transition = "none";
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  }

  function onPointerMove(e) {
    if (!isDragging) return;
    currentX = e.clientX - startX;
    currentY = e.clientY - startY;
    const rotate = currentX * 0.08;

    cardEl.style.transform = `translate(${currentX}px, ${currentY}px) rotate(${rotate}deg)`;

    const threshold = 60;
    if (currentX > 20) {
      stampKeep.style.opacity = Math.min(1, (currentX - 20) / threshold);
      stampUnfollow.style.opacity = 0;
      stampVip.style.opacity = 0;
    } else if (currentX < -20) {
      stampUnfollow.style.opacity = Math.min(1, (-currentX - 20) / threshold);
      stampKeep.style.opacity = 0;
      stampVip.style.opacity = 0;
    } else if (currentY < -40) {
      stampVip.style.opacity = Math.min(1, (-currentY - 40) / threshold);
      stampKeep.style.opacity = 0;
      stampUnfollow.style.opacity = 0;
    } else {
      stampKeep.style.opacity = 0;
      stampUnfollow.style.opacity = 0;
      stampVip.style.opacity = 0;
    }
  }

  function onPointerUp() {
    if (!isDragging) return;
    isDragging = false;
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);

    const triggerThreshold = 110;
    if (currentX > triggerThreshold) {
      completeSwipe(cardEl, account, "whitelist", 1);
    } else if (currentX < -triggerThreshold) {
      completeSwipe(cardEl, account, "unfollow_candidate", -1);
    } else if (currentY < -triggerThreshold) {
      completeSwipe(cardEl, account, "vip", 0, -1);
    } else {
      cardEl.style.transition = "transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)";
      cardEl.style.transform = "translate(0, 0) rotate(0deg)";
      stampKeep.style.opacity = 0;
      stampUnfollow.style.opacity = 0;
      stampVip.style.opacity = 0;
    }
  }

  cardEl.addEventListener("pointerdown", onPointerDown);
}

async function completeSwipe(cardEl, account, decision, dirX = 1, dirY = 0) {
  sfx.playWhoosh(dirX);

  const tags = account._selectedTags ? Array.from(account._selectedTags) : (account.tags || []);
  cardEl.style.transition = "transform 0.35s ease-in, opacity 0.3s";
  const offX = dirX !== 0 ? dirX * (window.innerWidth + 200) : 0;
  const offY = dirY < 0 ? -window.innerHeight : 0;
  cardEl.style.transform = `translate(${offX}px, ${offY}px) rotate(${dirX * 35}deg)`;
  cardEl.style.opacity = "0";

  state.currentCardIndex++;
  setTimeout(() => {
    renderDeck();
  }, 220);

  try {
    const res = await postDecision(account.username, decision, tags);
    if (res.metrics) {
      renderMetrics(res.metrics);
    }
    const decLabels = {
      whitelist: "Kept in Whitelist",
      unfollow_candidate: "Flagged for Unfollow",
      vip: "Marked as VIP",
    };
    showToast(`@${account.username}: ${decLabels[decision] || decision}`, "✓");
  } catch (err) {
    showToast(`Error updating @${account.username}`, "⚠️");
  }
}

function triggerSwipe(decision) {
  const remaining = state.deck.slice(state.currentCardIndex);
  if (remaining.length === 0) return;
  const card = document.querySelector("#deckContainer .swipe-card");
  if (!card) return;

  const account = remaining[0];
  const dirX = decision === "whitelist" ? 1 : decision === "unfollow_candidate" ? -1 : 0;
  const dirY = decision === "vip" ? -1 : 0;
  completeSwipe(card, account, decision, dirX, dirY);
}

async function handleUndo() {
  try {
    const res = await postUndo();
    if (res.success && res.restored) {
      sfx.playChime("undo");
      showToast(`Restored @${res.restored.username}`, "↩️");
      if (state.currentCardIndex > 0) {
        state.currentCardIndex--;
      }
      if (res.metrics) renderMetrics(res.metrics);
      renderDeck();
    }
  } catch (err) {
    showToast("Nothing to undo", "ℹ️");
  }
}

async function loadDeck() {
  const deck = await fetchDeck(60);
  state.deck = deck;
  state.currentCardIndex = 0;
  renderDeck();
}

// Audit Table
async function loadTable() {
  const params = {};
  if (state.tableFilter === "unreciprocated") {
    params.relationship = "unreciprocated";
  } else if (state.tableFilter === "actionable") {
    params.relationship = "unreciprocated";
    params.decision = "unreviewed";
  } else if (state.tableFilter === "whitelist") {
    params.decision = "whitelist";
  } else if (state.tableFilter === "unfollow_candidate") {
    params.decision = "unfollow_candidate";
  } else if (state.tableFilter === "mutual") {
    params.relationship = "mutual";
  } else if (state.tableFilter === "fan") {
    params.relationship = "fan";
  }

  if (state.tableSearch) {
    params.search = state.tableSearch;
  }

  const accounts = await fetchAccounts(params);
  state.tableAccounts = accounts;
  renderTable(accounts);
}

function renderTable(accounts) {
  const tbody = document.getElementById("tableBody");
  tbody.innerHTML = "";

  if (accounts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 32px;">No accounts match the current filter.</td></tr>`;
    return;
  }

  accounts.forEach(acc => {
    const tr = document.createElement("tr");
    const isChecked = state.selectedUsernames.has(acc.username);

    tr.innerHTML = `
      <td>
        <input type="checkbox" class="row-checkbox" data-username="${acc.username}" ${isChecked ? "checked" : ""}>
      </td>
      <td>
        <div class="account-cell">
          <div class="mini-avatar" style="background: ${hashColor(acc.username)}">${acc.username.slice(0, 2).toUpperCase()}</div>
          <div>
            <a href="${acc.profile_url}" target="_blank" rel="noopener" style="color: var(--text-main); font-weight: 600; text-decoration: none;">
              @${acc.username}
            </a>
          </div>
        </div>
      </td>
      <td>
        <span class="status-chip ${acc.relationship}">
          ${acc.relationship}
        </span>
      </td>
      <td>
        <span class="tag-badge ${acc.decision}">
          ${acc.decision}
        </span>
      </td>
      <td>
        ${acc.tags && acc.tags.length > 0 ? acc.tags.map(t => `<span class="tag-badge">#${t}</span>`).join(" ") : "-"}
      </td>
      <td style="color: var(--text-muted); font-size: 0.8rem;">
        ${acc.followed_at || "-"}
      </td>
      <td>
        <div class="table-actions">
          <button class="table-action-btn" onclick="quickDecide('${acc.username}', 'whitelist')">✓ Keep</button>
          <button class="table-action-btn" onclick="quickDecide('${acc.username}', 'unfollow_candidate')">✕ Flag</button>
          <a class="table-action-btn" href="${acc.profile_url}" target="_blank" rel="noopener">↗ IG</a>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll(".row-checkbox").forEach(cb => {
    cb.addEventListener("change", (e) => {
      const u = e.target.dataset.username;
      if (e.target.checked) state.selectedUsernames.add(u);
      else state.selectedUsernames.delete(u);
      updateBatchBar();
    });
  });
}

async function quickDecide(username, decision) {
  const res = await postDecision(username, decision);
  showToast(`@${username}: ${decision}`, "✓");
  if (res.metrics) renderMetrics(res.metrics);
  loadTable();
}

function updateBatchBar() {
  const count = state.selectedUsernames.size;
  const bar = document.getElementById("batchBar");
  const countEl = document.getElementById("batchCount");
  if (count > 0) {
    bar.style.display = "flex";
    countEl.textContent = count;
  } else {
    bar.style.display = "none";
  }
}

async function handleBatchAction(decision) {
  const usernames = Array.from(state.selectedUsernames);
  if (usernames.length === 0) return;

  const res = await apiFetch("/api/batch/decision", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ usernames, decision }),
  });
  const data = await res.json();
  showToast(`Updated ${data.updated_count} accounts`, "✓");
  state.selectedUsernames.clear();
  updateBatchBar();
  if (data.metrics) renderMetrics(data.metrics);
  loadTable();
  loadDeck();
}

// Diff Engine
async function loadDiffView() {
  const snaps = await fetchSnapshots();
  state.snapshots = snaps;
  const selA = document.getElementById("diffSnapA");
  const selB = document.getElementById("diffSnapB");
  selA.innerHTML = "";
  selB.innerHTML = "";

  snaps.forEach(s => {
    selA.innerHTML += `<option value="${s.id}">${s.name} (${s.created_at.slice(0, 10)})</option>`;
    selB.innerHTML += `<option value="${s.id}">${s.name} (${s.created_at.slice(0, 10)})</option>`;
  });

  if (snaps.length > 1) {
    selB.selectedIndex = 1;
  }
}

async function runDiff() {
  const idA = document.getElementById("diffSnapA").value;
  const idB = document.getElementById("diffSnapB").value;
  if (!idA || !idB) return;

  const res = await apiFetch(`/api/snapshots/diff?snapshot_a_id=${idA}&snapshot_b_id=${idB}`, { method: "POST" });
  const data = await res.json();

  renderDiffList("diffLostFollowers", data.lost_followers);
  renderDiffList("diffNewFollowers", data.new_followers);
  renderDiffList("diffUnfollowedByYou", data.unfollowed_by_you);
  renderDiffList("diffNewFollowing", data.new_following);
}

function renderDiffList(elementId, items) {
  const el = document.getElementById(elementId);
  el.innerHTML = "";
  if (!items || items.length === 0) {
    el.innerHTML = `<div style="color: var(--text-muted); font-size: 0.8rem; padding: 12px;">No changes found.</div>`;
    return;
  }
  items.forEach(a => {
    const item = document.createElement("div");
    item.className = "diff-list-item";
    item.innerHTML = `
      <span>@${a.username}</span>
      <a class="table-action-btn" href="${a.profile_url}" target="_blank" rel="noopener">↗</a>
    `;
    el.appendChild(item);
  });
}

// Global Keyboard Navigation
window.addEventListener("keydown", (e) => {
  if (state.activeTab !== "swipe") return;
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

  if (e.key === "ArrowLeft" || e.key.toLowerCase() === "a") {
    e.preventDefault();
    triggerSwipe("unfollow_candidate");
  } else if (e.key === "ArrowRight" || e.key.toLowerCase() === "d") {
    e.preventDefault();
    triggerSwipe("whitelist");
  } else if (e.key === "ArrowUp" || e.key.toLowerCase() === "w") {
    e.preventDefault();
    triggerSwipe("vip");
  } else if (e.key === " " || e.key === "ArrowDown" || e.key.toLowerCase() === "s") {
    e.preventDefault();
    state.currentCardIndex++;
    renderDeck();
  } else if (e.key.toLowerCase() === "u" || ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z")) {
    e.preventDefault();
    handleUndo();
  }
});

// Auth Header UI
function renderAuthHeader() {
  const container = document.getElementById("authHeaderArea");
  if (!container) return;
  container.innerHTML = "";

  if (state.currentUser) {
    const email = state.currentUser.email;
    const initial = email.charAt(0).toUpperCase();
    container.innerHTML = `
      <div class="user-pill">
        <div class="user-pill-avatar">${initial}</div>
        <span>${state.currentUser.display_name || email}</span>
      </div>
      <button class="btn btn-secondary btn-icon-only" id="btnLogout" title="Sign Out">
        🚪
      </button>
    `;
    document.getElementById("btnLogout").addEventListener("click", () => {
      state.token = null;
      state.currentUser = null;
      localStorage.removeItem("vault_token");
      renderAuthHeader();
      showToast("Signed out", "👋");
      initApp();
    });
  } else {
    container.innerHTML = `
      <button class="btn btn-primary" id="btnOpenAuth">
        🔑 Sign In
      </button>
    `;
    document.getElementById("btnOpenAuth").addEventListener("click", () => {
      document.getElementById("authDialog").showModal();
    });
  }
}

// App Initialization
async function initApp() {
  if (state.token) {
    state.currentUser = await fetchMe();
  }
  renderAuthHeader();

  const status = await fetchStatus();
  if (status.has_data) {
    const metrics = await fetchMetrics();
    renderMetrics(metrics);
    await loadDeck();
    document.getElementById("welcomePrompt").style.display = "none";
  } else {
    document.getElementById("welcomePrompt").style.display = "block";
  }

  // Tabs
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-view").forEach(v => v.classList.remove("active"));

      btn.classList.add("active");
      const tabKey = btn.dataset.tab;
      state.activeTab = tabKey;
      document.getElementById(`view-${tabKey}`).classList.add("active");

      if (tabKey === "table") loadTable();
      if (tabKey === "diff") loadDiffView();
    });
  });

  // Table filter pills
  document.querySelectorAll(".filter-pill").forEach(p => {
    p.addEventListener("click", () => {
      document.querySelectorAll(".filter-pill").forEach(x => x.classList.remove("active"));
      p.classList.add("active");
      state.tableFilter = p.dataset.filter;
      loadTable();
    });
  });

  // Search
  let searchTimeout = null;
  const searchInput = document.getElementById("tableSearchInput");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        state.tableSearch = e.target.value.trim();
        loadTable();
      }, 250);
    });
  }

  // Sound toggle
  const soundBtn = document.getElementById("btnToggleSound");
  if (soundBtn) {
    soundBtn.addEventListener("click", () => {
      sfx.enabled = !sfx.enabled;
      soundBtn.innerHTML = sfx.enabled ? "🔊 Sound" : "🔇 Muted";
      showToast(sfx.enabled ? "Audio FX Enabled" : "Audio FX Muted");
    });
  }

  // Recompute
  const recomputeBtn = document.getElementById("btnRecompute");
  if (recomputeBtn) {
    recomputeBtn.addEventListener("click", async () => {
      recomputeBtn.disabled = true;
      recomputeBtn.innerHTML = "🔄 Computing...";
      const freshMetrics = await postRecompute();
      sfx.playChime("success");
      renderMetrics(freshMetrics);
      showToast("Metrics recomputed & up to date!", "✓");
      recomputeBtn.disabled = false;
      recomputeBtn.innerHTML = "🔄 Recompute";
    });
  }

  // Demo Banner Button
  const demoBannerBtn = document.getElementById("btnDemoBanner");
  if (demoBannerBtn) {
    demoBannerBtn.addEventListener("click", async () => {
      const authData = await demoLoginApi();
      state.token = authData.access_token;
      state.currentUser = authData.user;
      localStorage.setItem("vault_token", state.token);
      renderAuthHeader();
      sfx.playChime("success");
      showToast("Connected as Demo User!", "⚡");
      initApp();
    });
  }

  setupAuthModal();
  setupUploadModal();
}

// Auth Modal
function setupAuthModal() {
  const authDialog = document.getElementById("authDialog");
  const closeBtn = document.getElementById("btnCloseAuth");
  const form = document.getElementById("authForm");
  const tabLogin = document.getElementById("tabAuthLogin");
  const tabRegister = document.getElementById("tabAuthRegister");
  const title = document.getElementById("authModalTitle");
  const groupName = document.getElementById("groupDisplayName");
  const submitBtn = document.getElementById("btnAuthSubmit");
  const errorMsg = document.getElementById("authErrorMsg");
  const demoQuickBtn = document.getElementById("btnAuthDemoQuick");

  let isRegister = false;

  if (closeBtn) closeBtn.addEventListener("click", () => authDialog.close());

  function setMode(registerMode) {
    isRegister = registerMode;
    errorMsg.style.display = "none";
    if (isRegister) {
      tabRegister.classList.add("active");
      tabLogin.classList.remove("active");
      title.textContent = "Create an Account";
      groupName.style.display = "flex";
      submitBtn.textContent = "Create Account";
    } else {
      tabLogin.classList.add("active");
      tabRegister.classList.remove("active");
      title.textContent = "Sign In to Follower Vault";
      groupName.style.display = "none";
      submitBtn.textContent = "Sign In";
    }
  }

  if (tabLogin) tabLogin.addEventListener("click", () => setMode(false));
  if (tabRegister) tabRegister.addEventListener("click", () => setMode(true));

  if (demoQuickBtn) {
    demoQuickBtn.addEventListener("click", async () => {
      const authData = await demoLoginApi();
      state.token = authData.access_token;
      state.currentUser = authData.user;
      localStorage.setItem("vault_token", state.token);
      authDialog.close();
      renderAuthHeader();
      sfx.playChime("success");
      showToast("Signed in as Demo User!", "⚡");
      initApp();
    });
  }

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorMsg.style.display = "none";
      const email = document.getElementById("authEmail").value;
      const password = document.getElementById("authPassword").value;
      const displayName = document.getElementById("authDisplayName").value;

      try {
        let authData;
        if (isRegister) {
          authData = await registerApi(email, password, displayName);
        } else {
          authData = await loginApi(email, password);
        }

        if (authData.access_token) {
          state.token = authData.access_token;
          state.currentUser = authData.user;
          localStorage.setItem("vault_token", state.token);
          authDialog.close();
          renderAuthHeader();
          sfx.playChime("success");
          showToast(`Welcome ${state.currentUser.display_name || email}!`, "🎉");
          initApp();
        } else {
          errorMsg.textContent = authData.detail || "Authentication failed";
          errorMsg.style.display = "block";
        }
      } catch (err) {
        errorMsg.textContent = err.message || "Network error";
        errorMsg.style.display = "block";
      }
    });
  }
}

// Upload Modal with Async Polling
function setupUploadModal() {
  const uploadDialog = document.getElementById("uploadDialog");
  const openUploadBtn = document.getElementById("btnOpenUpload");
  const closeUploadBtn = document.getElementById("btnCloseUpload");
  const uploadForm = document.getElementById("uploadForm");
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("uploadFileInput");
  const progressScreen = document.getElementById("uploadProgressScreen");
  const stageName = document.getElementById("progressStageName");
  const percentText = document.getElementById("progressPercent");
  const barFill = document.getElementById("progressBarFill");

  if (openUploadBtn) {
    openUploadBtn.addEventListener("click", () => {
      uploadForm.style.display = "block";
      progressScreen.style.display = "none";
      uploadDialog.showModal();
    });
  }

  if (closeUploadBtn) closeUploadBtn.addEventListener("click", () => uploadDialog.close());

  if (dropzone && fileInput) {
    dropzone.addEventListener("click", () => fileInput.click());
    dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("dragover"); });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
      if (e.dataTransfer.files.length > 0) {
        fileInput.files = e.dataTransfer.files;
        document.getElementById("dropzoneText").textContent = `Selected: ${fileInput.files[0].name}`;
      }
    });
    fileInput.addEventListener("change", () => {
      if (fileInput.files.length > 0) {
        document.getElementById("dropzoneText").textContent = `Selected: ${fileInput.files[0].name}`;
      }
    });
  }

  if (uploadForm) {
    uploadForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const files = fileInput.files;
      if (!files || files.length === 0) {
        alert("Please select an export file (.zip, .html, or .json)");
        return;
      }

      const file = files[0];
      const formData = new FormData();
      formData.append("file", file);
      formData.append("snapshot_name", document.getElementById("snapNameInput").value || "Imported Export");

      // Switch to progress screen
      uploadForm.style.display = "none";
      progressScreen.style.display = "flex";
      stageName.textContent = "Uploading archive...";
      percentText.textContent = "10%";
      barFill.style.width = "10%";

      try {
        const res = await apiFetch("/api/uploads/start", {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Upload rejected");
        }

        const job = await res.json();
        pollJob(job.job_id);
      } catch (err) {
        alert("Upload error: " + err.message);
        uploadForm.style.display = "block";
        progressScreen.style.display = "none";
      }
    });
  }

  function pollJob(jobId) {
    const interval = setInterval(async () => {
      try {
        const res = await apiFetch(`/api/uploads/${jobId}`);
        if (!res.ok) {
          clearInterval(interval);
          return;
        }
        const job = await res.json();
        const p = Math.max(15, Math.round(job.progress_percent));
        barFill.style.width = `${p}%`;
        percentText.textContent = `${p}%`;
        stageName.textContent = `Stage: ${job.stage.replace(/_/g, " ")}...`;

        if (job.status === "completed") {
          clearInterval(interval);
          barFill.style.width = "100%";
          percentText.textContent = "100%";
          stageName.textContent = "Audit complete!";
          sfx.playChime("success");
          showToast("Export analyzed & indexed into vault!", "🎉");
          setTimeout(() => {
            uploadDialog.close();
            initApp();
          }, 600);
        } else if (job.status === "failed") {
          clearInterval(interval);
          alert("Processing failed: " + (job.error_message || "Unknown error"));
          uploadForm.style.display = "block";
          progressScreen.style.display = "none";
        }
      } catch (err) {
        clearInterval(interval);
      }
    }, 400);
  }
}

document.addEventListener("DOMContentLoaded", initApp);

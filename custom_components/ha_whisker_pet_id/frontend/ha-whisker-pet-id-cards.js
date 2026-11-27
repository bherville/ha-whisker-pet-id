/* Built-in Lovelace cards for HA Whisker Pet ID */

const CARD_VERSION = "0.4.1";

const DEFAULT_HEALTH_ENTITY = "sensor.ha_whisker_pet_id_health_summary";
const DEFAULT_HISTORY_ENTITY = "sensor.ha_whisker_pet_id_alert_history";
const DEFAULT_AI_ENTITY = "sensor.ha_whisker_pet_id_ai_pet_id_status";

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function titleCaseWords(raw) {
  return String(raw || "")
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function slugifyPet(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function formatTimestamp(isoOrText) {
  if (!isoOrText) return "—";
  const raw = String(isoOrText);
  const parsed = new Date(raw);
  if (Number.isNaN(parsed.getTime())) {
    return raw.length > 22 ? raw.slice(0, 22) : raw;
  }
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function resolvePetAvatarUrl(hass, petName) {
  const slug = slugifyPet(petName);
  if (!slug) return "";
  if (hass && hass.states) {
    const candidates = [
      `sensor.ha_whisker_pet_id_${slug}_health_summary`,
      `sensor.ha_whisker_pet_id_${slug}`,
    ];
    for (const eid of candidates) {
      const pic = hass.states[eid]?.attributes?.entity_picture;
      if (pic) return String(pic);
    }
  }
  return `/local/ha_whisker_pet_id/pets/${slug}.jpg`;
}

function isEntityReady(stateObj) {
  return Boolean(
    stateObj &&
      stateObj.state !== undefined &&
      stateObj.state !== "unavailable"
  );
}

function renderPagerHtml(totalItems, page, pageSize) {
  if (totalItems <= pageSize) return "";
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const safePage = Math.min(Math.max(0, page), totalPages - 1);
  const start = safePage * pageSize;
  const end = Math.min(start + pageSize, totalItems);
  return `
    <div class="pager">
      <span class="pager-info">Showing ${start + 1}–${end} of ${totalItems}</span>
      <div class="pager-controls">
        <button class="pager-btn" data-page="prev" type="button" ${safePage <= 0 ? "disabled" : ""}>
          Prev
        </button>
        <span class="pager-page">Page ${safePage + 1} / ${totalPages}</span>
        <button class="pager-btn" data-page="next" type="button" ${safePage >= totalPages - 1 ? "disabled" : ""}>
          Next
        </button>
      </div>
    </div>
  `;
}

const SHARED_STYLES = `
  :host {
    display: block;
    font-family: var(--paper-font-body1_-_font-family, inherit);
    color: var(--primary-text-color);
  }
  ha-card {
    padding: 16px;
    border-radius: var(--ha-card-border-radius, 12px);
    background: var(--ha-card-background, var(--card-background-color, #fff));
    box-sizing: border-box;
    container-type: inline-size;
  }
  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }
  .title {
    font-size: 1.08rem;
    font-weight: 600;
    letter-spacing: -0.01em;
    color: var(--primary-text-color);
    margin: 0;
  }
  .subtitle {
    font-size: 0.8rem;
    color: var(--secondary-text-color);
    margin-top: 2px;
  }
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.76rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    border: 1px solid transparent;
    white-space: nowrap;
  }
  .badge.ok {
    background: rgba(67, 160, 71, 0.14);
    color: var(--success-color, #43a047);
    border-color: rgba(67, 160, 71, 0.3);
  }
  .badge.warn {
    background: rgba(251, 140, 0, 0.14);
    color: var(--warning-color, #fb8c00);
    border-color: rgba(251, 140, 0, 0.35);
  }
  .badge.err {
    background: rgba(229, 57, 53, 0.14);
    color: var(--error-color, #e53935);
    border-color: rgba(229, 57, 53, 0.35);
  }
  .badge.info {
    background: rgba(3, 169, 244, 0.14);
    color: var(--primary-color, #03a9f4);
    border-color: rgba(3, 169, 244, 0.3);
  }
  .badge.muted {
    background: rgba(128, 128, 128, 0.14);
    color: var(--secondary-text-color);
    border-color: rgba(128, 128, 128, 0.25);
  }
  .callout {
    padding: 10px 12px;
    border-radius: 10px;
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.08));
    border-left: 3px solid var(--primary-color, #03a9f4);
    margin-bottom: 12px;
    font-size: 0.88rem;
    line-height: 1.4;
  }
  .callout.warn {
    border-left-color: var(--warning-color, #fb8c00);
  }
  .callout.err {
    border-left-color: var(--error-color, #e53935);
  }
  .callout.ok {
    border-left-color: var(--success-color, #43a047);
  }
  .metrics {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
  }
  .metric-pill {
    display: inline-flex;
    align-items: baseline;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 8px;
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.08));
    font-size: 0.78rem;
    color: var(--secondary-text-color);
  }
  .metric-pill strong {
    color: var(--primary-text-color);
    font-weight: 600;
  }
  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 12px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.28));
    background: transparent;
    color: var(--secondary-text-color);
    font-size: 0.78rem;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
  }
  .chip:hover {
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.12));
    color: var(--primary-text-color);
  }
  .chip.active {
    background: rgba(3, 169, 244, 0.16);
    border-color: var(--primary-color, #03a9f4);
    color: var(--primary-color, #03a9f4);
    font-weight: 600;
  }
  .chip-avatar {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    object-fit: cover;
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.2));
  }
  .baselines {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 12px;
  }
  .cat-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 5px 10px 5px 6px;
    border-radius: 999px;
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.08));
    border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.18));
    font-size: 0.8rem;
  }
  .cat-avatar {
    width: 24px;
    height: 24px;
    border-radius: 50%;
    object-fit: cover;
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.2));
  }
  .cat-weight {
    color: var(--secondary-text-color);
    font-variant-numeric: tabular-nums;
  }
  .table-wrap {
    overflow-x: auto;
    border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
    border-radius: 10px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
  }
  th {
    text-align: left;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--secondary-text-color);
    padding: 8px 8px;
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.08));
    border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
    white-space: nowrap;
  }
  td {
    padding: 8px 8px;
    border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.14));
    vertical-align: top;
    line-height: 1.35;
  }
  tr:last-child td {
    border-bottom: none;
  }
  .inline-weight {
    display: none;
    font-size: 0.75rem;
    color: var(--secondary-text-color);
    font-variant-numeric: tabular-nums;
  }
  .status-pill {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: capitalize;
    white-space: nowrap;
  }
  .status-pill.active,
  .status-pill.alert {
    background: rgba(229, 57, 53, 0.15);
    color: var(--error-color, #e53935);
  }
  .status-pill.watch,
  .status-pill.suggest,
  .status-pill.uncertain {
    background: rgba(251, 140, 0, 0.15);
    color: var(--warning-color, #fb8c00);
  }
  .status-pill.resolved,
  .status-pill.reassigned {
    background: rgba(67, 160, 71, 0.15);
    color: var(--success-color, #43a047);
  }
  .status-pill.confirmed,
  .status-pill.unassigned {
    background: rgba(3, 169, 244, 0.14);
    color: var(--primary-color, #03a9f4);
  }
  .status-pill.muted {
    background: rgba(128, 128, 128, 0.15);
    color: var(--secondary-text-color);
  }
  .pager {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-top: 10px;
    font-size: 0.78rem;
    color: var(--secondary-text-color);
    flex-wrap: wrap;
  }
  .pager-info {
    font-variant-numeric: tabular-nums;
  }
  .pager-controls {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }
  .pager-page {
    font-variant-numeric: tabular-nums;
  }
  .pager-btn {
    padding: 4px 10px;
    border-radius: 8px;
    border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.28));
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.08));
    color: var(--primary-text-color);
    font-size: 0.76rem;
    font-weight: 500;
    font-family: inherit;
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease;
  }
  .pager-btn:hover:not(:disabled) {
    background: rgba(3, 169, 244, 0.14);
    border-color: var(--primary-color, #03a9f4);
  }
  .pager-btn:disabled {
    opacity: 0.45;
    cursor: default;
  }
  .empty {
    padding: 18px 12px;
    text-align: center;
    color: var(--secondary-text-color);
    font-size: 0.85rem;
  }
  .mono {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }
  @container (max-width: 470px) {
    .col-weight {
      display: none;
    }
    .inline-weight {
      display: block;
      margin-top: 2px;
    }
    th,
    td {
      padding: 6px 6px;
      font-size: 0.78rem;
    }
  }
`;

class WhiskerHealthArchiveCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {
      title: "Pet Health & Alert Archive",
      health_entity: DEFAULT_HEALTH_ENTITY,
      alert_history_entity: DEFAULT_HISTORY_ENTITY,
      page_size: 8,
      max_rows: 25,
    };
    this._filter = "all";
    this._page = 0;
    this._lastSig = "";
  }

  static getStubConfig() {
    return {
      title: "Pet Health & Alert Archive",
      health_entity: DEFAULT_HEALTH_ENTITY,
      alert_history_entity: DEFAULT_HISTORY_ENTITY,
      page_size: 8,
      max_rows: 25,
    };
  }

  getGridOptions() {
    return {
      columns: "full",
      min_columns: 12,
    };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid card configuration");
    }
    const maxRows = Math.max(1, Number(config.max_rows || 25));
    const pageSize = Math.max(1, Number(config.page_size || 8));
    this._config = {
      title: config.title || "Pet Health & Alert Archive",
      health_entity: config.health_entity || DEFAULT_HEALTH_ENTITY,
      alert_history_entity: config.alert_history_entity || DEFAULT_HISTORY_ENTITY,
      page_size: pageSize,
      max_rows: maxRows,
    };
    this._page = 0;
    this._lastSig = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const hState = hass?.states?.[this._config.health_entity];
    const aState = hass?.states?.[this._config.alert_history_entity];
    const sig = `${hState?.last_updated || ""}|${hState?.state || ""}|${aState?.last_updated || ""}|${aState?.state || ""}`;
    if (sig !== this._lastSig) {
      this._lastSig = sig;
      this._render();
    }
  }

  getCardSize() {
    return 5;
  }

  _badgeClass(status) {
    const val = String(status || "unknown").toLowerCase();
    if (val === "normal") return "ok";
    if (val === "watch") return "warn";
    if (val === "alert") return "err";
    return "muted";
  }

  _render() {
    if (!this.shadowRoot) return;
    const hEntity = this._hass?.states?.[this._config.health_entity];
    const aEntity = this._hass?.states?.[this._config.alert_history_entity];

    const hReady = isEntityReady(hEntity);
    const aReady = isEntityReady(aEntity);

    if (!this._hass || (!hReady && !aReady)) {
      this.shadowRoot.innerHTML = `
        <style>${SHARED_STYLES}</style>
        <ha-card>
          <div class="header">
            <h2 class="title">${escapeHtml(this._config.title)}</h2>
            <span class="badge muted">Unavailable</span>
          </div>
          <div class="empty">
            Waiting for <code>${escapeHtml(this._config.health_entity)}</code> and
            <code>${escapeHtml(this._config.alert_history_entity)}</code>.
          </div>
        </ha-card>
      `;
      return;
    }

    const overall = hReady ? String(hEntity.state || "unknown") : "unknown";
    const hAttrs = hEntity?.attributes || {};
    const aAttrs = aEntity?.attributes || {};
    const badgeCls = this._badgeClass(overall);

    const activeCount = aReady ? Number(aEntity.state || 0) : 0;
    const totalLogged = Number(aAttrs.total_logged || 0);
    const resolvedCount = Number(aAttrs.resolved_count || 0);
    const headline = hAttrs.headline || "No health summary generated yet.";
    const lastGenerated = formatTimestamp(hAttrs.last_generated_at);

    const recentAlerts = Array.isArray(aAttrs.recent_alerts)
      ? aAttrs.recent_alerts
      : Array.isArray(aAttrs.active_alerts)
        ? aAttrs.active_alerts
        : [];

    const countsByPet =
      aAttrs.counts_by_pet && typeof aAttrs.counts_by_pet === "object"
        ? Object.keys(aAttrs.counts_by_pet).sort()
        : [];

    const alertPetSet = new Set(countsByPet);
    for (const item of recentAlerts) {
      if (Array.isArray(item?.pets)) {
        for (const pet of item.pets) {
          if (pet) alertPetSet.add(String(pet));
        }
      }
    }
    const petNames = Array.from(alertPetSet).sort();

    if (
      this._filter !== "all" &&
      this._filter !== "active" &&
      !petNames.includes(this._filter)
    ) {
      this._filter = "all";
      this._page = 0;
    }

    const allFiltered = recentAlerts
      .filter((item) => {
        if (this._filter === "all") return true;
        if (this._filter === "active") {
          return String(item?.status || "").toLowerCase() === "active";
        }
        const pets = Array.isArray(item?.pets) ? item.pets.map(String) : [];
        return pets.includes(this._filter);
      })
      .slice(0, this._config.max_rows);

    const pageSize = this._config.page_size;
    const totalPages = Math.max(1, Math.ceil(allFiltered.length / pageSize));
    this._page = Math.min(Math.max(0, this._page), totalPages - 1);
    const start = this._page * pageSize;
    const pageRows = allFiltered.slice(start, start + pageSize);

    const petChipsHtml = petNames
      .map((pet) => {
        const avatar = resolvePetAvatarUrl(this._hass, pet);
        const activeCls = this._filter === pet ? "active" : "";
        return `
          <button class="chip ${activeCls}" data-filter="${escapeHtml(pet)}" type="button">
            <img class="chip-avatar" src="${escapeHtml(avatar)}" alt="${escapeHtml(pet)}" onerror="this.style.display='none'" />
            <span>${escapeHtml(pet)}</span>
          </button>
        `;
      })
      .join("");

    const rowsHtml = pageRows.length
      ? pageRows
          .map((item) => {
            const status = String(item?.status || "active").toLowerCase();
            const sev = String(item?.severity || status).toLowerCase();
            const pillClass = status === "resolved" ? "resolved" : sev === "watch" ? "watch" : "active";
            const pets = Array.isArray(item?.pets) && item.pets.length ? item.pets.join(", ") : "Household";
            const opened = formatTimestamp(item?.opened_at || item?.last_seen_at);
            const source = titleCaseWords(item?.source || "alert");
            return `
              <tr>
                <td><span class="status-pill ${escapeHtml(pillClass)}">${escapeHtml(status)}</span></td>
                <td><strong>${escapeHtml(pets)}</strong></td>
                <td>${escapeHtml(item?.headline || "—")}</td>
                <td class="mono">${escapeHtml(source)}</td>
                <td class="mono">${escapeHtml(opened)}</td>
              </tr>
            `;
          })
          .join("")
      : `<tr><td colspan="5" class="empty">No alerts matching this filter.</td></tr>`;

    const pagerHtml = renderPagerHtml(allFiltered.length, this._page, pageSize);

    this.shadowRoot.innerHTML = `
      <style>${SHARED_STYLES}</style>
      <ha-card>
        <div class="header">
          <div>
            <h2 class="title">${escapeHtml(this._config.title)}</h2>
            <div class="subtitle">Last summary: ${escapeHtml(lastGenerated)}</div>
          </div>
          <span class="badge ${escapeHtml(badgeCls)}">${escapeHtml(overall)}</span>
        </div>

        <div class="callout ${escapeHtml(badgeCls)}">
          ${escapeHtml(headline)}
        </div>

        <div class="metrics">
          <span class="metric-pill"><strong>${activeCount}</strong> Active Alerts</span>
          <span class="metric-pill"><strong>${resolvedCount}</strong> Resolved</span>
          <span class="metric-pill"><strong>${totalLogged}</strong> Total Logged</span>
          <span class="metric-pill"><strong>${Number(hAttrs.total_visits || 0)}</strong> Visits (Window)</span>
        </div>

        <div class="filters">
          <button class="chip ${this._filter === "all" ? "active" : ""}" data-filter="all" type="button">
            All (${recentAlerts.length})
          </button>
          <button class="chip ${this._filter === "active" ? "active" : ""}" data-filter="active" type="button">
            Active (${activeCount})
          </button>
          ${petChipsHtml}
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>Pet</th>
                <th>Alert</th>
                <th>Source</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
        ${pagerHtml}
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll("button.chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._filter = btn.getAttribute("data-filter") || "all";
        this._page = 0;
        this._render();
      });
    });

    this.shadowRoot.querySelectorAll("button.pager-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const dir = btn.getAttribute("data-page");
        if (dir === "prev" && this._page > 0) {
          this._page -= 1;
          this._render();
        } else if (dir === "next" && this._page < totalPages - 1) {
          this._page += 1;
          this._render();
        }
      });
    });
  }
}

class WhiskerAutoPetIdCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {
      title: "Smart Cat ID",
      entity: DEFAULT_AI_ENTITY,
      page_size: 5,
      max_rows: 25,
    };
    this._page = 0;
    this._lastSig = "";
  }

  static getStubConfig() {
    return {
      title: "Smart Cat ID",
      entity: DEFAULT_AI_ENTITY,
      page_size: 5,
      max_rows: 25,
    };
  }

  getGridOptions() {
    return {
      columns: "full",
      min_columns: 12,
    };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid card configuration");
    }
    const maxRows = Math.max(1, Number(config.max_rows || 25));
    const pageSize = Math.max(1, Number(config.page_size || 5));
    this._config = {
      title: config.title || "Smart Cat ID",
      entity: config.entity || DEFAULT_AI_ENTITY,
      page_size: pageSize,
      max_rows: maxRows,
    };
    this._page = 0;
    this._lastSig = "";
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const stateObj = hass?.states?.[this._config.entity];
    const sig = `${stateObj?.last_updated || ""}|${stateObj?.state || ""}`;
    if (sig !== this._lastSig) {
      this._lastSig = sig;
      this._render();
    }
  }

  getCardSize() {
    return 5;
  }

  _modeBadgeClass(mode) {
    const val = String(mode || "off").toLowerCase();
    if (val === "auto_reassign") return "ok";
    if (val === "dry_run") return "info";
    if (val === "backoff") return "warn";
    return "muted";
  }

  _formatMode(mode) {
    const val = String(mode || "off").toLowerCase();
    if (val === "auto_reassign") return "Auto-Fix On";
    if (val === "dry_run") return "Preview Mode";
    if (val === "backoff") return "Paused (Limit)";
    if (val === "off") return "Paused";
    return titleCaseWords(mode);
  }

  _formatStage(stage) {
    const val = String(stage || "").toLowerCase();
    if (val === "hybrid_fast_path") return "Weight Match";
    if (val === "gemini_thumbnail") return "AI Photo";
    if (val === "gemini_video") return "AI Video";
    if (val === "scale_glitch") return "Scale Glitch";
    if (val === "gemini_error") return "AI Retry";
    return stage ? titleCaseWords(stage) : "—";
  }

  _formatAction(action) {
    const val = String(action || "").toLowerCase();
    if (val === "reassigned") return "Reassigned";
    if (val === "confirmed") return "Confirmed";
    if (val === "unassigned_scale_glitch" || val === "unassigned") return "Cleared";
    if (val === "suggested") return "Suggested";
    if (val === "uncertain") return "Needs Review";
    if (val === "kept") return "Kept";
    return action ? titleCaseWords(action) : "—";
  }

  _actionClass(action) {
    const val = String(action || "").toLowerCase();
    if (val.includes("reassign")) return "reassigned";
    if (val.includes("confirm")) return "confirmed";
    if (val.includes("unassign")) return "unassigned";
    if (val.includes("suggest") || val.includes("uncertain")) return "uncertain";
    return "muted";
  }

  _render() {
    if (!this.shadowRoot) return;
    const entity = this._hass?.states?.[this._config.entity];

    if (!this._hass || !isEntityReady(entity)) {
      this.shadowRoot.innerHTML = `
        <style>${SHARED_STYLES}</style>
        <ha-card>
          <div class="header">
            <h2 class="title">${escapeHtml(this._config.title)}</h2>
            <span class="badge muted">Unavailable</span>
          </div>
          <div class="empty">
            Waiting for <code>${escapeHtml(this._config.entity)}</code>.
          </div>
        </ha-card>
      `;
      return;
    }

    const modeState = String(entity.state || "off");
    const attrs = entity.attributes || {};
    const badgeCls = this._modeBadgeClass(modeState);
    const badgeLabel = this._formatMode(modeState);
    const baselines =
      attrs.clean_baselines && typeof attrs.clean_baselines === "object"
        ? Object.entries(attrs.clean_baselines).sort(([a], [b]) => a.localeCompare(b))
        : [];
    const decisions = Array.isArray(attrs.recent_decisions)
      ? attrs.recent_decisions.slice(0, this._config.max_rows)
      : [];

    const pageSize = this._config.page_size;
    const totalPages = Math.max(1, Math.ceil(decisions.length / pageSize));
    this._page = Math.min(Math.max(0, this._page), totalPages - 1);
    const start = this._page * pageSize;
    const pageRows = decisions.slice(start, start + pageSize);

    const baselinesHtml = baselines.length
      ? baselines
          .map(([pet, lbs]) => {
            const avatar = resolvePetAvatarUrl(this._hass, pet);
            const wt = Number.isFinite(Number(lbs)) ? `${Number(lbs).toFixed(2)} lb` : "—";
            return `
              <span class="cat-pill">
                <img class="cat-avatar" src="${escapeHtml(avatar)}" alt="${escapeHtml(pet)}" onerror="this.style.display='none'" />
                <strong>${escapeHtml(pet)}</strong>
                <span class="cat-weight">${escapeHtml(wt)}</span>
              </span>
            `;
          })
          .join("")
      : `<span class="metric-pill">Learning clean weights…</span>`;

    const rowsHtml = pageRows.length
      ? pageRows
          .map((d) => {
            const time = formatTimestamp(d?.local_time || d?.timestamp);
            const wt = Number.isFinite(Number(d?.weight_lbs))
              ? `${Number(d.weight_lbs).toFixed(2)} lb`
              : "—";
            const fromPet = d?.from_pet || "Unassigned";
            const toPet = d?.to_pet || "—";
            const route = fromPet === toPet ? `${toPet}` : `${fromPet} → ${toPet}`;
            const method = this._formatStage(d?.stage);
            const resultLabel = this._formatAction(d?.action);
            const conf = d?.confidence ? ` (${titleCaseWords(d.confidence)})` : "";
            const actionCls = this._actionClass(d?.action);
            return `
              <tr>
                <td class="mono">${escapeHtml(time)}</td>
                <td class="col-weight mono">${escapeHtml(wt)}</td>
                <td>
                  <strong>${escapeHtml(route)}</strong>
                  <div class="inline-weight">${escapeHtml(wt)}</div>
                </td>
                <td>${escapeHtml(method)}${escapeHtml(conf)}</td>
                <td><span class="status-pill ${escapeHtml(actionCls)}">${escapeHtml(resultLabel)}</span></td>
              </tr>
            `;
          })
          .join("")
      : `<tr><td colspan="5" class="empty">No recent Smart Cat ID activity recorded yet.</td></tr>`;

    const errorBanner = attrs.last_error
      ? `<div class="callout warn">Last notice: ${escapeHtml(attrs.last_error)}</div>`
      : "";

    const pagerHtml = renderPagerHtml(decisions.length, this._page, pageSize);

    this.shadowRoot.innerHTML = `
      <style>${SHARED_STYLES}</style>
      <ha-card>
        <div class="header">
          <div>
            <h2 class="title">${escapeHtml(this._config.title)}</h2>
            <div class="subtitle">Last check: ${escapeHtml(formatTimestamp(attrs.last_run_at))}</div>
          </div>
          <span class="badge ${escapeHtml(badgeCls)}">${escapeHtml(badgeLabel)}</span>
        </div>

        ${errorBanner}

        <div class="metrics">
          <span class="metric-pill"><strong>${Number(attrs.auto_reassigned_count || 0)}</strong> Reassigned</span>
          <span class="metric-pill"><strong>${Number(attrs.fast_path_count || 0)}</strong> Weight Match</span>
          <span class="metric-pill"><strong>${Number(attrs.gemini_calls_count || 0)}</strong> AI Vision</span>
          <span class="metric-pill"><strong>${Number(attrs.scale_unassigned_count || 0)}</strong> Scale Glitches</span>
          <span class="metric-pill"><strong>${Number(attrs.uncertain_count || 0)}</strong> Needs Review</span>
        </div>

        <div class="baselines">
          ${baselinesHtml}
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th class="col-weight">Weight</th>
                <th>Cat</th>
                <th>Method</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
        ${pagerHtml}
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll("button.pager-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const dir = btn.getAttribute("data-page");
        if (dir === "prev" && this._page > 0) {
          this._page -= 1;
          this._render();
        } else if (dir === "next" && this._page < totalPages - 1) {
          this._page += 1;
          this._render();
        }
      });
    });
  }
}

if (!customElements.get("whisker-health-archive-card")) {
  customElements.define("whisker-health-archive-card", WhiskerHealthArchiveCard);
}
if (!customElements.get("whisker-auto-pet-id-card")) {
  customElements.define("whisker-auto-pet-id-card", WhiskerAutoPetIdCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "whisker-health-archive-card")) {
  window.customCards.push({
    type: "whisker-health-archive-card",
    name: "Whisker Health & Alert Archive",
    description:
      "Displays household health summary, interactive cat filter chips, and alert history table.",
    preview: true,
    documentationURL:
      "https://gitlab.com/bherville/home-assistant/ha-whisker-pet-id",
  });
}
if (!window.customCards.some((card) => card.type === "whisker-auto-pet-id-card")) {
  window.customCards.push({
    type: "whisker-auto-pet-id-card",
    name: "Whisker Smart Cat ID",
    description:
      "Displays Smart Cat ID status, clean weight baselines with cat avatars, and paginated visit corrections.",
    preview: true,
    documentationURL:
      "https://gitlab.com/bherville/home-assistant/ha-whisker-pet-id",
  });
}

console.info(
  `%c HA-WHISKER-PET-ID %c v${CARD_VERSION} `,
  "color:#fff;background:#03a9f4;font-weight:700;padding:2px 6px;border-radius:4px 0 0 4px;",
  "color:#03a9f4;background:#e1f5fe;font-weight:700;padding:2px 6px;border-radius:0 4px 4px 0;"
);

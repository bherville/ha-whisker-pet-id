/* Built-in Lovelace cards for HA Whisker Pet ID */

const CARD_VERSION = "0.7.2";

const DEFAULT_HEALTH_ENTITY = "sensor.ha_whisker_pet_id_health_summary";
const DEFAULT_HISTORY_ENTITY = "sensor.ha_whisker_pet_id_alert_history";
const DEFAULT_AI_ENTITY = "sensor.ha_whisker_pet_id_ai_pet_id_status";
const DEFAULT_FIX_BUTTON_ENTITY = "button.ha_whisker_pet_id_fix_pet_id_mismatches";

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

function renderSnapshotsHtml(snapshots, fallbackUrl) {
  const list = Array.isArray(snapshots)
    ? snapshots.filter((s) => s && typeof s.url === "string" && s.url.trim())
    : [];
  if (!list.length && typeof fallbackUrl === "string" && fallbackUrl.trim()) {
    list.push({ label: "Freeze-Frame", url: fallbackUrl.trim() });
  }
  const safeList = list.filter((s) => /^(?:\/|https?:\/\/)/i.test(String(s.url).trim()));
  if (!safeList.length) return "";
  const cards = safeList
    .map((item) => {
      const url = String(item.url).trim();
      const label = item.label || "Camera";
      return `
        <a class="snapshot-card" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">
          <img class="snapshot-img" src="${escapeHtml(url)}" alt="${escapeHtml(label)}" loading="lazy" onerror="this.closest('.snapshot-card').style.display='none'" />
          <div class="snapshot-caption">
            <span>${escapeHtml(label)}</span>
            <span>Open ↗</span>
          </div>
        </a>
      `;
    })
    .join("");
  return `
    <div class="snapshot-section">
      <div class="detail-label">Camera Freeze-Frames</div>
      <div class="snapshot-grid">${cards}</div>
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
  .header-actions {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .action-btn {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 999px;
    border: 1px solid rgba(3, 169, 244, 0.35);
    background: rgba(3, 169, 244, 0.14);
    color: var(--primary-color, #03a9f4);
    font-size: 0.75rem;
    font-weight: 600;
    font-family: inherit;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s ease, border-color 0.15s ease;
  }
  .action-btn:hover:not(:disabled) {
    background: rgba(3, 169, 244, 0.24);
    border-color: var(--primary-color, #03a9f4);
  }
  .action-btn:disabled {
    opacity: 0.6;
    cursor: default;
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
  .alert-row,
  .decision-row {
    cursor: pointer;
    transition: background 0.12s ease;
  }
  .alert-row:hover td,
  .decision-row:hover td {
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.08));
  }
  .alert-row:focus-visible,
  .decision-row:focus-visible {
    outline: 2px solid var(--primary-color, #03a9f4);
    outline-offset: -2px;
  }
  .status-cell,
  .time-cell {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    white-space: nowrap;
  }
  .expand-icon {
    display: inline-block;
    width: 14px;
    font-size: 0.75rem;
    color: var(--secondary-text-color);
    transition: transform 0.15s ease;
    text-align: center;
  }
  .alert-row.expanded .expand-icon,
  .decision-row.expanded .expand-icon {
    transform: rotate(90deg);
  }
  .detail-row td {
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.06));
    padding: 10px 12px;
  }
  .detail-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 8px 14px;
    font-size: 0.78rem;
  }
  .detail-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .detail-label {
    font-size: 0.68rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--secondary-text-color);
  }
  .detail-value {
    color: var(--primary-text-color);
    word-break: break-word;
  }
  .detail-note {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid var(--divider-color, rgba(127, 127, 127, 0.16));
    font-size: 0.78rem;
    color: var(--primary-text-color);
    line-height: 1.4;
    word-break: break-word;
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
  .pet-cell {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
  }
  .row-avatar {
    width: 22px;
    height: 22px;
    border-radius: 50%;
    object-fit: cover;
    flex-shrink: 0;
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.2));
  }
  .alert-main {
    font-weight: 500;
    color: var(--primary-text-color);
    line-height: 1.35;
  }
  .alert-meta {
    font-size: 0.72rem;
    color: var(--secondary-text-color);
    margin-top: 2px;
  }
  .inline-when {
    display: none;
  }
  .snap-badge {
    font-size: 0.72rem;
    opacity: 0.85;
    margin-left: 4px;
  }
  .snapshot-section {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--divider-color, rgba(127, 127, 127, 0.16));
  }
  .snapshot-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 10px;
    margin-top: 6px;
  }
  .snapshot-card {
    display: block;
    border: 1px solid var(--divider-color, rgba(127, 127, 127, 0.24));
    border-radius: 8px;
    overflow: hidden;
    text-decoration: none;
    background: var(--card-background-color, rgba(0, 0, 0, 0.2));
    transition: border-color 0.15s ease;
  }
  .snapshot-card:hover {
    border-color: var(--primary-color, #03a9f4);
  }
  .snapshot-img {
    display: block;
    width: 100%;
    max-height: 220px;
    object-fit: cover;
    background: #000;
  }
  .snapshot-caption {
    padding: 5px 8px;
    font-size: 0.72rem;
    color: var(--secondary-text-color);
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 6px;
  }
  @container (max-width: 470px) {
    .col-weight,
    .col-when {
      display: none;
    }
    .inline-weight {
      display: block;
      margin-top: 2px;
    }
    .inline-when {
      display: inline;
    }
    th,
    td {
      padding: 6px 6px;
      font-size: 0.78rem;
    }
    .status-pill {
      padding: 2px 6px;
      font-size: 0.7rem;
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
      default_filter: "active",
      page_size: 8,
      max_rows: 25,
    };
    this._filter = "active";
    this._page = 0;
    this._expandedIds = new Set();
    this._lastSig = "";
  }

  static getStubConfig() {
    return {
      title: "Pet Health & Alert Archive",
      health_entity: DEFAULT_HEALTH_ENTITY,
      alert_history_entity: DEFAULT_HISTORY_ENTITY,
      default_filter: "active",
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
    const defaultFilter =
      String(config.default_filter || "active").toLowerCase() === "all"
        ? "all"
        : "active";
    this._config = {
      title: config.title || "Pet Health & Alert Archive",
      health_entity: config.health_entity || DEFAULT_HEALTH_ENTITY,
      alert_history_entity: config.alert_history_entity || DEFAULT_HISTORY_ENTITY,
      default_filter: defaultFilter,
      page_size: pageSize,
      max_rows: maxRows,
    };
    this._filter = defaultFilter;
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

  _formatSource(source) {
    const val = String(source || "").toLowerCase();
    if (val === "health_cluster") return "Repeat-Visit Cluster";
    if (val === "health_summary") return "AI Health Summary";
    if (val === "pet_id_review") return "Smart Cat ID Review";
    return titleCaseWords(source || "alert");
  }

  _formatAlertCategory(source) {
    const val = String(source || "").toLowerCase();
    if (val === "health_cluster") return "Repeat Visits";
    if (val === "health_summary") return "Health Check";
    if (val === "pet_id_review") return "Cat ID Review";
    return titleCaseWords(source || "alert");
  }

  _formatAlertHeadline(item) {
    let text = String(item?.headline || "—").trim();
    const pets = Array.isArray(item?.pets) ? item.pets.map(String) : [];
    if (pets.length === 1) {
      const prefix = `${pets[0]}:`;
      if (text.toLowerCase().startsWith(prefix.toLowerCase())) {
        text = text.slice(prefix.length).trim();
      }
    }
    text = text
      .replace(/\b(\d+(?:\.\d+)?)\s*m\b/g, (_, num) => `${Math.round(Number(num))} min`)
      .replace(/\bzero-waste\b/gi, "with no waste")
      .replace(/\((\d+)\s+with no waste\)/gi, "($1 with no waste)");
    return text || "—";
  }

  _formatRowStatusLabel(item) {
    const status = String(item?.status || "active").toLowerCase();
    if (status === "resolved") return "Resolved";
    const sev = String(item?.severity || status).toLowerCase();
    return sev === "watch" ? "Watch" : "Alert";
  }

  _rowStatusClass(item) {
    const status = String(item?.status || "active").toLowerCase();
    if (status === "resolved") return "resolved";
    const sev = String(item?.severity || status).toLowerCase();
    return sev === "watch" ? "watch" : "active";
  }

  _renderAlertDetailsHtml(item) {
    const fields = [];
    const addField = (label, value) => {
      if (value === null || value === undefined || value === "") return;
      fields.push(`
        <div class="detail-item">
          <span class="detail-label">${escapeHtml(label)}</span>
          <span class="detail-value">${escapeHtml(value)}</span>
        </div>
      `);
    };

    const sourceRaw = String(item?.source || "").toLowerCase();
    addField("Source", this._formatSource(item?.source));
    addField("Severity", titleCaseWords(item?.severity || item?.status || "info"));
    addField("Opened", formatTimestamp(item?.opened_at));
    addField("Last Seen", formatTimestamp(item?.last_seen_at));
    if (item?.resolved_at) {
      addField("Resolved", formatTimestamp(item.resolved_at));
    }
    if (Array.isArray(item?.notified_services) && item.notified_services.length) {
      addField("Notified", item.notified_services.join(", "));
    }

    const details =
      item?.details && typeof item.details === "object" && !Array.isArray(item.details)
        ? item.details
        : {};
    const consumedKeys = new Set();
    let noteText = "";

    if (sourceRaw === "health_cluster") {
      if (details.count !== undefined) {
        addField("Visits", String(details.count));
        consumedKeys.add("count");
      }
      if (details.duration_minutes !== undefined) {
        addField("Duration", `${details.duration_minutes} min`);
        consumedKeys.add("duration_minutes");
      }
      if (details.zero_waste_count !== undefined) {
        addField("Zero-Waste", String(details.zero_waste_count));
        consumedKeys.add("zero_waste_count");
      }
      if (details.start || details.end) {
        addField(
          "Window",
          `${formatTimestamp(details.start)} → ${formatTimestamp(details.end)}`
        );
        consumedKeys.add("start");
        consumedKeys.add("end");
      }
      consumedKeys.add("pet_name");
    } else if (sourceRaw === "health_summary") {
      if (details.generation_mode) {
        addField("Mode", titleCaseWords(details.generation_mode));
        consumedKeys.add("generation_mode");
      }
      if (details.clusters_detected !== undefined) {
        addField("Clusters", String(details.clusters_detected));
        consumedKeys.add("clusters_detected");
      }
      if (details.flagged_visits_count !== undefined) {
        addField("Flagged Visits", String(details.flagged_visits_count));
        consumedKeys.add("flagged_visits_count");
      }
      if (
        details.pet_statuses &&
        typeof details.pet_statuses === "object" &&
        !Array.isArray(details.pet_statuses)
      ) {
        const statusSummary = Object.entries(details.pet_statuses)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([pet, st]) => `${pet}: ${titleCaseWords(st || "unknown")}`)
          .join(", ");
        addField("Pet Statuses", statusSummary);
        consumedKeys.add("pet_statuses");
      }
      if (details.alert_message) {
        noteText = String(details.alert_message);
        consumedKeys.add("alert_message");
      }
      consumedKeys.add("household_headline");
    } else if (sourceRaw === "pet_id_review") {
      if (details.weight_lbs !== undefined && details.weight_lbs !== null) {
        addField("Weight", `${Number(details.weight_lbs).toFixed(2)} lb`);
        consumedKeys.add("weight_lbs");
      }
      if (details.local_time) {
        addField("Visit Time", formatTimestamp(details.local_time));
        consumedKeys.add("local_time");
      }
      if (details.stage) {
        addField("Method", titleCaseWords(details.stage));
        consumedKeys.add("stage");
      }
      if (details.confidence) {
        addField("Confidence", titleCaseWords(details.confidence));
        consumedKeys.add("confidence");
      }
      if (details.reasoning) {
        noteText = String(details.reasoning);
        consumedKeys.add("reasoning");
      }
    }

    for (const [key, val] of Object.entries(details)) {
      if (
        consumedKeys.has(key) ||
        key === "snapshots" ||
        key === "snapshot_url" ||
        val === null ||
        val === undefined ||
        val === ""
      ) {
        continue;
      }
      if (typeof val === "object") continue;
      addField(titleCaseWords(key), String(val));
    }

    if (item?.alert_id) {
      addField("Alert ID", String(item.alert_id));
    }

    const noteHtml = noteText
      ? `<div class="detail-note">${escapeHtml(noteText)}</div>`
      : "";
    const snapsHtml = renderSnapshotsHtml(details.snapshots, details.snapshot_url);

    return `
      <div class="detail-grid">${fields.join("")}</div>
      ${noteHtml}
      ${snapsHtml}
    `;
  }

  _toggleRow(alertKey) {
    if (!alertKey) return;
    if (this._expandedIds.has(alertKey)) {
      this._expandedIds.delete(alertKey);
    } else {
      this._expandedIds.add(alertKey);
    }
    this._render();
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
          .map((item, idx) => {
            const pillLabel = this._formatRowStatusLabel(item);
            const pillClass = this._rowStatusClass(item);
            const petList = Array.isArray(item?.pets) ? item.pets.map(String).filter(Boolean) : [];
            const petLabel = petList.length ? petList.join(", ") : "Household";
            const primaryPet = petList.length === 1 ? petList[0] : "";
            const avatarUrl = primaryPet ? resolvePetAvatarUrl(this._hass, primaryPet) : "";
            const avatarHtml = avatarUrl
              ? `<img class="row-avatar" src="${escapeHtml(avatarUrl)}" alt="${escapeHtml(primaryPet)}" onerror="this.style.display='none'" />`
              : "";
            const cleanHeadline = this._formatAlertHeadline(item);
            const category = this._formatAlertCategory(item?.source);
            const opened = formatTimestamp(item?.opened_at || item?.last_seen_at);
            const hasSnaps = Boolean(
              (Array.isArray(item?.details?.snapshots) && item.details.snapshots.length) ||
                item?.details?.snapshot_url
            );
            const snapIconHtml = hasSnaps
              ? `<span class="snap-badge" title="Freeze-frame available">📷</span>`
              : "";
            const alertKey = String(
              item?.alert_id || `${item?.source || "alert"}:${item?.opened_at || ""}:${start + idx}`
            );
            const isExpanded = this._expandedIds.has(alertKey);
            const mainRow = `
              <tr class="alert-row ${isExpanded ? "expanded" : ""}" data-alert-key="${escapeHtml(alertKey)}" tabindex="0" role="button" aria-expanded="${isExpanded ? "true" : "false"}">
                <td>
                  <span class="pet-cell">
                    <span class="expand-icon">▸</span>
                    ${avatarHtml}
                    <strong>${escapeHtml(petLabel)}</strong>
                  </span>
                </td>
                <td>
                  <div class="alert-main">${escapeHtml(cleanHeadline)}</div>
                  <div class="alert-meta">${escapeHtml(category)}<span class="inline-when"> · ${escapeHtml(opened)}</span>${snapIconHtml}</div>
                </td>
                <td><span class="status-pill ${escapeHtml(pillClass)}">${escapeHtml(pillLabel)}</span></td>
                <td class="col-when mono">${escapeHtml(opened)}</td>
              </tr>
            `;
            const detailRow = isExpanded
              ? `<tr class="detail-row"><td colspan="4">${this._renderAlertDetailsHtml(item)}</td></tr>`
              : "";
            return mainRow + detailRow;
          })
          .join("")
      : `<tr><td colspan="4" class="empty">${
          this._filter === "active"
            ? "All clear — no active alerts right now."
            : "No alerts matching this filter."
        }</td></tr>`;

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
          <button class="chip ${this._filter === "active" ? "active" : ""}" data-filter="active" type="button">
            Active (${activeCount})
          </button>
          <button class="chip ${this._filter === "all" ? "active" : ""}" data-filter="all" type="button">
            All (${recentAlerts.length})
          </button>
          ${petChipsHtml}
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Cat</th>
                <th>What Happened</th>
                <th>Status</th>
                <th class="col-when">When</th>
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

    this.shadowRoot.querySelectorAll("tr.alert-row").forEach((row) => {
      const key = row.getAttribute("data-alert-key") || "";
      row.addEventListener("click", () => {
        this._toggleRow(key);
      });
      row.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          this._toggleRow(key);
        }
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
      fix_button_entity: DEFAULT_FIX_BUTTON_ENTITY,
      page_size: 5,
      max_rows: 25,
    };
    this._page = 0;
    this._expandedIds = new Set();
    this._runningFix = false;
    this._lastSig = "";
  }

  static getStubConfig() {
    return {
      title: "Smart Cat ID",
      entity: DEFAULT_AI_ENTITY,
      fix_button_entity: DEFAULT_FIX_BUTTON_ENTITY,
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
    const fixButtonEntity =
      config.fix_button_entity === false || config.fix_button_entity === ""
        ? ""
        : config.fix_button_entity || DEFAULT_FIX_BUTTON_ENTITY;
    this._config = {
      title: config.title || "Smart Cat ID",
      entity: config.entity || DEFAULT_AI_ENTITY,
      fix_button_entity: fixButtonEntity,
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
    const btnObj = this._config.fix_button_entity
      ? hass?.states?.[this._config.fix_button_entity]
      : null;
    const sig = `${stateObj?.last_updated || ""}|${stateObj?.state || ""}|${btnObj?.last_updated || ""}|${btnObj?.state || ""}`;
    if (sig !== this._lastSig) {
      this._lastSig = sig;
      this._render();
    }
  }

  getCardSize() {
    return 5;
  }

  async _triggerFixMismatches() {
    if (!this._hass || !this._config.fix_button_entity || this._runningFix) return;
    this._runningFix = true;
    this._render();
    try {
      await this._hass.callService("button", "press", {
        entity_id: this._config.fix_button_entity,
      });
    } finally {
      this._runningFix = false;
      this._render();
    }
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
    if (val === "needs_review" || val === "uncertain") return "Needs Review";
    if (val.startsWith("dry_run_")) {
      return `Suggested (${titleCaseWords(val.slice("dry_run_".length))})`;
    }
    if (val === "suggested") return "Suggested";
    if (val === "kept") return "Kept";
    return action ? titleCaseWords(action) : "—";
  }

  _actionClass(action) {
    const val = String(action || "").toLowerCase();
    if (val.includes("reassign")) return "reassigned";
    if (val.includes("confirm")) return "confirmed";
    if (val.includes("unassign")) return "unassigned";
    if (
      val.includes("suggest") ||
      val.includes("uncertain") ||
      val.includes("review") ||
      val.startsWith("dry_run_")
    ) {
      return "uncertain";
    }
    return "muted";
  }

  _formatConfidence(d) {
    const label = d?.confidence ? titleCaseWords(d.confidence) : "";
    const rawScore = d?.confidence_score;
    const score = Number(rawScore);
    if (
      rawScore !== null &&
      rawScore !== undefined &&
      rawScore !== "" &&
      Number.isFinite(score)
    ) {
      const pct = score >= 0 && score <= 1 ? `${Math.round(score * 100)}%` : `${Math.round(score)}%`;
      return label ? `${label} (${pct})` : pct;
    }
    return label || "—";
  }

  _toggleRow(decisionKey) {
    if (!decisionKey) return;
    if (this._expandedIds.has(decisionKey)) {
      this._expandedIds.delete(decisionKey);
    } else {
      this._expandedIds.add(decisionKey);
    }
    this._render();
  }

  _renderDecisionDetailsHtml(d, baselinesObj) {
    const fields = [];
    const addField = (label, value) => {
      if (value === null || value === undefined || value === "") return;
      fields.push(`
        <div class="detail-item">
          <span class="detail-label">${escapeHtml(label)}</span>
          <span class="detail-value">${escapeHtml(value)}</span>
        </div>
      `);
    };

    const fromPet = d?.from_pet || "Unassigned";
    const toPet = d?.to_pet || "Unassigned";
    const hasWeight =
      d?.weight_lbs !== null &&
      d?.weight_lbs !== undefined &&
      d?.weight_lbs !== "" &&
      Number.isFinite(Number(d.weight_lbs));
    const measuredNum = hasWeight ? Number(d.weight_lbs) : null;

    addField("Original Cat", fromPet);
    addField("Verified Cat", toPet);
    addField("Measured Weight", measuredNum !== null ? `${measuredNum.toFixed(2)} lb` : "—");

    const baselineRaw = baselinesObj && toPet ? baselinesObj[toPet] : undefined;
    if (
      baselineRaw !== null &&
      baselineRaw !== undefined &&
      Number.isFinite(Number(baselineRaw))
    ) {
      const baseNum = Number(baselineRaw);
      let baseText = `${toPet} ${baseNum.toFixed(2)} lb`;
      if (measuredNum !== null) {
        const diff = measuredNum - baseNum;
        const sign = diff >= 0 ? "+" : "";
        baseText += ` (Δ ${sign}${diff.toFixed(2)} lb)`;
      }
      addField("Baseline Diff", baseText);
    }

    addField("Method", this._formatStage(d?.stage));
    addField("Confidence", this._formatConfidence(d));

    if (
      d?.visual_match !== null &&
      d?.visual_match !== undefined &&
      d?.visual_match !== ""
    ) {
      const vm =
        typeof d.visual_match === "boolean"
          ? d.visual_match
            ? "Yes"
            : "No"
          : String(d.visual_match);
      addField("Visual Match", vm);
    }

    addField("Result", this._formatAction(d?.action));
    addField("Visit Time", formatTimestamp(d?.local_time || d?.timestamp));
    if (d?.processed_at) {
      addField("Processed", formatTimestamp(d.processed_at));
    }
    if (d?.event_id) {
      addField("Event ID", String(d.event_id));
    }

    const noteHtml = d?.reasoning
      ? `<div class="detail-note">${escapeHtml(d.reasoning)}</div>`
      : "";
    const snapsHtml = renderSnapshotsHtml(d?.snapshots, d?.snapshot_url);

    return `
      <div class="detail-grid">${fields.join("")}</div>
      ${noteHtml}
      ${snapsHtml}
    `;
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
          .map((d, idx) => {
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
            const hasSnaps = Boolean(
              (Array.isArray(d?.snapshots) && d.snapshots.length) || d?.snapshot_url
            );
            const snapIconHtml = hasSnaps
              ? `<span class="snap-badge" title="Freeze-frame available">📷</span>`
              : "";
            const actionCls = this._actionClass(d?.action);
            const decisionKey = String(
              d?.event_id ||
                `${d?.local_time || d?.timestamp || ""}:${d?.weight_lbs || ""}:${start + idx}`
            );
            const isExpanded = this._expandedIds.has(decisionKey);
            const mainRow = `
              <tr class="decision-row ${isExpanded ? "expanded" : ""}" data-decision-key="${escapeHtml(decisionKey)}" tabindex="0" role="button" aria-expanded="${isExpanded ? "true" : "false"}">
                <td class="mono">
                  <span class="time-cell">
                    <span class="expand-icon">▸</span>
                    <span>${escapeHtml(time)}</span>
                  </span>
                </td>
                <td class="col-weight mono">${escapeHtml(wt)}</td>
                <td>
                  <strong>${escapeHtml(route)}</strong>
                  <div class="inline-weight">${escapeHtml(wt)}</div>
                </td>
                <td>${escapeHtml(method)}${escapeHtml(conf)}${snapIconHtml}</td>
                <td><span class="status-pill ${escapeHtml(actionCls)}">${escapeHtml(resultLabel)}</span></td>
              </tr>
            `;
            const detailRow = isExpanded
              ? `<tr class="detail-row"><td colspan="5">${this._renderDecisionDetailsHtml(
                  d,
                  attrs.clean_baselines || {}
                )}</td></tr>`
              : "";
            return mainRow + detailRow;
          })
          .join("")
      : `<tr><td colspan="5" class="empty">No recent Smart Cat ID activity recorded yet.</td></tr>`;

    const errorBanner = attrs.last_error
      ? `<div class="callout warn">Last notice: ${escapeHtml(attrs.last_error)}</div>`
      : "";

    const pagerHtml = renderPagerHtml(decisions.length, this._page, pageSize);
    const hasFixBtn = Boolean(
      this._config.fix_button_entity &&
        this._hass?.states?.[this._config.fix_button_entity]
    );
    const fixBtnHtml = hasFixBtn
      ? `<button class="action-btn" data-action="fix-pet-ids" type="button" ${
          this._runningFix ? "disabled" : ""
        }>${this._runningFix ? "Checking…" : "Fix Mismatches"}</button>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>${SHARED_STYLES}</style>
      <ha-card>
        <div class="header">
          <div>
            <h2 class="title">${escapeHtml(this._config.title)}</h2>
            <div class="subtitle">Last check: ${escapeHtml(formatTimestamp(attrs.last_run_at))}</div>
          </div>
          <div class="header-actions">
            ${fixBtnHtml}
            <span class="badge ${escapeHtml(badgeCls)}">${escapeHtml(badgeLabel)}</span>
          </div>
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

    const fixBtn = this.shadowRoot.querySelector('button[data-action="fix-pet-ids"]');
    if (fixBtn) {
      fixBtn.addEventListener("click", () => {
        this._triggerFixMismatches();
      });
    }

    this.shadowRoot.querySelectorAll("tr.decision-row").forEach((row) => {
      const key = row.getAttribute("data-decision-key") || "";
      row.addEventListener("click", () => {
        this._toggleRow(key);
      });
      row.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          this._toggleRow(key);
        }
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
      "Displays household health summary, interactive cat filter chips, and expandable alert details.",
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
      "Displays Smart Cat ID status, clean weight baselines with cat avatars, and paginated visit corrections with clickable details.",
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

/* Built-in Lovelace cards for HA Whisker Pet ID */

const CARD_VERSION = "0.4.0";

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
    padding: 8px 10px;
    background: var(--secondary-background-color, rgba(127, 127, 127, 0.08));
    border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.2));
    white-space: nowrap;
  }
  td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--divider-color, rgba(127, 127, 127, 0.14));
    vertical-align: top;
    line-height: 1.35;
  }
  tr:last-child td {
    border-bottom: none;
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
`;

class WhiskerHealthArchiveCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {
      title: "Pet Health & Alert Archive",
      health_entity: DEFAULT_HEALTH_ENTITY,
      alert_history_entity: DEFAULT_HISTORY_ENTITY,
      max_rows: 15,
    };
    this._filter = "all";
    this._lastSig = "";
  }

  static getStubConfig() {
    return {
      title: "Pet Health & Alert Archive",
      health_entity: DEFAULT_HEALTH_ENTITY,
      alert_history_entity: DEFAULT_HISTORY_ENTITY,
      max_rows: 15,
    };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid card configuration");
    }
    this._config = {
      title: config.title || "Pet Health & Alert Archive",
      health_entity: config.health_entity || DEFAULT_HEALTH_ENTITY,
      alert_history_entity: config.alert_history_entity || DEFAULT_HISTORY_ENTITY,
      max_rows: Math.max(1, Number(config.max_rows || 15)),
    };
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
    }

    const filtered = recentAlerts
      .filter((item) => {
        if (this._filter === "all") return true;
        if (this._filter === "active") {
          return String(item?.status || "").toLowerCase() === "active";
        }
        const pets = Array.isArray(item?.pets) ? item.pets.map(String) : [];
        return pets.includes(this._filter);
      })
      .slice(0, this._config.max_rows);

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

    const rowsHtml = filtered.length
      ? filtered
          .map((item) => {
            const status = String(item?.status || "active").toLowerCase();
            const sev = String(item?.severity || status).toLowerCase();
            const pillClass = status === "resolved" ? "resolved" : sev === "watch" ? "watch" : "active";
            const pets = Array.isArray(item?.pets) && item.pets.length ? item.pets.join(", ") : "Household";
            const opened = formatTimestamp(item?.opened_at || item?.last_seen_at);
            const source = String(item?.source || "alert").replace(/_/g, " ");
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
      </ha-card>
    `;

    this.shadowRoot.querySelectorAll("button.chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        this._filter = btn.getAttribute("data-filter") || "all";
        this._render();
      });
    });
  }
}

class WhiskerAutoPetIdCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {
      title: "Hybrid + Gemini Auto-Pet-ID",
      entity: DEFAULT_AI_ENTITY,
      max_rows: 12,
    };
    this._lastSig = "";
  }

  static getStubConfig() {
    return {
      title: "Hybrid + Gemini Auto-Pet-ID",
      entity: DEFAULT_AI_ENTITY,
      max_rows: 12,
    };
  }

  setConfig(config) {
    if (!config || typeof config !== "object") {
      throw new Error("Invalid card configuration");
    }
    this._config = {
      title: config.title || "Hybrid + Gemini Auto-Pet-ID",
      entity: config.entity || DEFAULT_AI_ENTITY,
      max_rows: Math.max(1, Number(config.max_rows || 12)),
    };
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
    const baselines =
      attrs.clean_baselines && typeof attrs.clean_baselines === "object"
        ? Object.entries(attrs.clean_baselines).sort(([a], [b]) => a.localeCompare(b))
        : [];
    const decisions = Array.isArray(attrs.recent_decisions)
      ? attrs.recent_decisions.slice(0, this._config.max_rows)
      : [];

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
      : `<span class="metric-pill">Clean baselines learning…</span>`;

    const rowsHtml = decisions.length
      ? decisions
          .map((d) => {
            const time = formatTimestamp(d?.local_time || d?.timestamp);
            const wt = Number.isFinite(Number(d?.weight_lbs))
              ? `${Number(d.weight_lbs).toFixed(2)} lb`
              : "—";
            const fromPet = d?.from_pet || "Unassigned";
            const toPet = d?.to_pet || "—";
            const route = fromPet === toPet ? `${toPet}` : `${fromPet} -> ${toPet}`;
            const stage = String(d?.stage || "—").replace(/_/g, " ");
            const action = String(d?.action || "—").replace(/_/g, " ");
            const conf = d?.confidence ? String(d.confidence) : "—";
            const actionCls = this._actionClass(d?.action);
            return `
              <tr>
                <td class="mono">${escapeHtml(time)}</td>
                <td class="mono">${escapeHtml(wt)}</td>
                <td><strong>${escapeHtml(route)}</strong></td>
                <td>${escapeHtml(stage)} (${escapeHtml(conf)})</td>
                <td><span class="status-pill ${escapeHtml(actionCls)}">${escapeHtml(action)}</span></td>
              </tr>
            `;
          })
          .join("")
      : `<tr><td colspan="5" class="empty">No Auto-Pet-ID decisions recorded yet.</td></tr>`;

    const errorBanner = attrs.last_error
      ? `<div class="callout warn">Last notice: ${escapeHtml(attrs.last_error)}</div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>${SHARED_STYLES}</style>
      <ha-card>
        <div class="header">
          <div>
            <h2 class="title">${escapeHtml(this._config.title)}</h2>
            <div class="subtitle">Last cycle: ${escapeHtml(formatTimestamp(attrs.last_run_at))}</div>
          </div>
          <span class="badge ${escapeHtml(badgeCls)}">${escapeHtml(modeState)}</span>
        </div>

        ${errorBanner}

        <div class="metrics">
          <span class="metric-pill"><strong>${Number(attrs.auto_reassigned_count || 0)}</strong> Reassigned</span>
          <span class="metric-pill"><strong>${Number(attrs.fast_path_count || 0)}</strong> Fast-Path</span>
          <span class="metric-pill"><strong>${Number(attrs.gemini_calls_count || 0)}</strong> Gemini Calls</span>
          <span class="metric-pill"><strong>${Number(attrs.scale_unassigned_count || 0)}</strong> Glitches</span>
          <span class="metric-pill"><strong>${Number(attrs.uncertain_count || 0)}</strong> Uncertain</span>
        </div>

        <div class="baselines">
          ${baselinesHtml}
        </div>

        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Weight</th>
                <th>Assignment</th>
                <th>Stage</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
      </ha-card>
    `;
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
    name: "Whisker Auto-Pet-ID Audit",
    description:
      "Displays Auto-Pet-ID mode, clean cat weight baselines with avatars, and recent AI/fast-path decisions.",
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

/* 3D Print Cost Card - list of all prints booked by the 3D Print Cost Analyzer.
 *
 * type: custom:print-cost-card
 * title: 3D-Druckkosten      # optional
 * page_size: 25              # optional, prints per "mehr anzeigen"
 */
class PrintCostCard extends HTMLElement {
  setConfig(config) {
    this._cfg = Object.assign({ title: '3D-Druckkosten', page_size: 25 }, config || {});
    this._printer = this._printer || '';
    this._month = this._month || '';
    this._open = this._open || null;
    this._limit = this._cfg.page_size;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: 'open' });
      this.shadowRoot.addEventListener('click', ev => this._click(ev));
      this.shadowRoot.addEventListener('change', ev => this._change(ev));
    }
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._start();
  }

  connectedCallback() { if (this._hass && !this._timer) this._start(); }
  disconnectedCallback() { clearInterval(this._timer); this._timer = null; }
  _start() { this._load(); clearInterval(this._timer); this._timer = setInterval(() => this._load(), 60000); }
  getCardSize() { return 8; }
  getGridOptions() { return { columns: 'full', rows: 'auto', min_rows: 4 }; }

  async _load() {
    if (!this._hass) return;
    try {
      this._data = await this._hass.callWS({ type: 'print_cost_analyzer/jobs' });
      this._err = null;
    } catch (e) {
      this._err = (e && e.message) || String(e);
    }
    this._render();
  }

  _click(ev) {
    const more = ev.target.closest('[data-more]');
    if (more) { this._limit += this._cfg.page_size; this._render(); return; }
    const row = ev.target.closest('[data-job]');
    if (row && !ev.target.closest('a')) {
      this._open = this._open === row.dataset.job ? null : row.dataset.job;
      this._render();
    }
  }

  _change(ev) {
    if (ev.target.id === 'printer') this._printer = ev.target.value;
    if (ev.target.id === 'month') this._month = ev.target.value;
    this._limit = this._cfg.page_size;
    this._render();
  }

  _eur(v) { return v == null ? '–' : v.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' }); }
  _num(v, d, u) { return v == null ? '–' : v.toLocaleString('de-DE', { maximumFractionDigits: d, minimumFractionDigits: d }) + (u ? ' ' + u : ''); }
  _dur(s) {
    if (s == null) return '–';
    const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
    return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`;
  }
  _date(iso) {
    return iso ? new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '–';
  }
  _monthKey(iso) { const d = new Date(iso); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; }
  _esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
  _result(r) {
    return { finished: ['Fertig', 'ok'], failed: ['Fehlgeschlagen', 'bad'], cancelled: ['Abgebrochen', 'warn'] }[r] || [r || '–', 'warn'];
  }

  _render() {
    if (!this.shadowRoot || !this._cfg) return;
    const d = this._data || { jobs: [], active: [], printers: [] };
    const months = [...new Set(d.jobs.map(j => this._monthKey(j.started_at)))];
    const mName = k => { const [y, m] = k.split('-'); return new Date(y, m - 1, 1).toLocaleString('de-DE', { month: 'long', year: 'numeric' }); };
    const jobs = d.jobs.filter(j => (!this._printer || j.printer === this._printer) && (!this._month || this._monthKey(j.started_at) === this._month));
    const sum = k => jobs.reduce((a, j) => a + (j[k] || 0), 0);
    const opt = (v, l, sel) => `<option value="${this._esc(v)}" ${sel ? 'selected' : ''}>${this._esc(l)}</option>`;

    const running = d.active.filter(j => !j.ended_at).map(j => `
      <div class="run"><span class="dot"></span><b>${this._esc(j.printer)}</b> druckt „${this._esc(j.name)}“ seit ${this._date(j.started_at)}</div>`).join('');

    const rows = jobs.slice(0, this._limit).map(j => {
      const [rl, rc] = this._result(j.result);
      const open = this._open === j.id;
      const fil = (j.filaments || []).map(f => `
        <div class="fil"><i style="background:#${this._esc(f.color || '888')}"></i>
          <span class="fn">#${f.spool_id ?? '–'} ${this._esc(f.name)}</span>
          <span>${this._num(f.grams, 1, 'g')}</span><span class="c">${this._eur(f.cost)}</span></div>`).join('');
      const notes = [
        j.filament_source === 'slicer' ? 'Filament laut Slicer geschätzt – in Spoolman wurde nichts gebucht.' : '',
        j.missing_price ? 'Für mindestens eine Spule fehlt der Preis in Spoolman.' : '',
        j.partial ? 'Beginn verpasst (HA war offline) – Strom nur teilweise erfasst.' : '',
      ].filter(Boolean).map(n => `<div class="note">${n}</div>`).join('');
      const mw = j.makerworld_id ? `<a href="https://makerworld.com/de/models/${j.makerworld_id}" target="_blank" rel="noreferrer">Modell auf MakerWorld ↗</a>` : '';
      return `
        <div class="job ${open ? 'open' : ''}" data-job="${j.id}">
          <div class="thumb">${j.image ? `<img src="${this._esc(j.image)}" loading="lazy" alt="">` : '<ha-icon icon="mdi:printer-3d"></ha-icon>'}</div>
          <div class="main">
            <div class="name">${this._esc(j.name)}</div>
            <div class="meta">${this._esc(j.printer)} · ${this._date(j.started_at)} · ${this._dur(j.duration_s)}</div>
          </div>
          <div class="right"><div class="total">${this._eur(j.total_cost)}</div><span class="badge ${rc}">${rl}</span></div>
          ${open ? `
          <div class="details">
            <div class="grid">
              <div><span>Beginn</span><b>${this._date(j.started_at)}</b></div>
              <div><span>Ende</span><b>${this._date(j.ended_at)}</b></div>
              <div><span>Dauer</span><b>${this._dur(j.duration_s)}</b></div>
              <div><span>Drucker</span><b>${this._esc(j.printer)}</b></div>
            </div>
            <div class="sec">Strom</div>
            <div class="line"><span>${this._num(j.energy_kwh, 3, 'kWh')} × ${this._num(j.energy_price, 4, '€/kWh')}</span><b>${this._eur(j.energy_cost)}</b></div>
            <div class="sec">Filament · ${this._num(j.filament_grams, 1, 'g')}</div>
            ${fil || '<div class="line"><span>kein Verbrauch erfasst</span><b>–</b></div>'}
            <div class="line sum"><span>Filament gesamt</span><b>${this._eur(j.filament_cost)}</b></div>
            <div class="line total2"><span>Druck gesamt</span><b>${this._eur(j.total_cost)}</b></div>
            ${notes}
            <div class="foot">${mw}<span class="id">ID ${j.id}${j.file ? ' · ' + this._esc(j.file) : ''}</span></div>
          </div>` : ''}
        </div>`;
    }).join('');

    this.shadowRoot.innerHTML = `
      <style>
        :host { display:block; }
        ha-card { padding:16px; }
        .head { display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:10px; }
        h2 { margin:0; font-size:1.3rem; font-weight:500; }
        select { background:var(--card-background-color); color:var(--primary-text-color); border:1px solid var(--divider-color); border-radius:8px; padding:6px 8px; font:inherit; }
        .filters { display:flex; gap:8px; flex-wrap:wrap; }
        .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px; margin:14px 0; }
        .kpi { background:rgba(127,127,127,.08); border-radius:10px; padding:10px 12px; }
        .kpi span { display:block; font-size:.75rem; color:var(--secondary-text-color); }
        .kpi b { font-size:1.15rem; font-weight:500; }
        .run { display:flex; align-items:center; gap:8px; padding:8px 10px; margin-bottom:6px; border-radius:8px; background:rgba(46,164,79,.12); font-size:.9rem; }
        .dot { width:8px; height:8px; border-radius:50%; background:#2ea44f; box-shadow:0 0 0 4px rgba(46,164,79,.25); }
        .job { display:grid; grid-template-columns:56px 1fr auto; gap:12px; align-items:center; padding:10px 6px; border-top:1px solid var(--divider-color); cursor:pointer; }
        .job:hover { background:rgba(127,127,127,.05); }
        .thumb { width:56px; height:56px; border-radius:8px; background:rgba(127,127,127,.12); display:flex; align-items:center; justify-content:center; overflow:hidden; }
        .thumb img { width:100%; height:100%; object-fit:contain; }
        .name { font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .main { min-width:0; }
        .meta { font-size:.82rem; color:var(--secondary-text-color); margin-top:2px; }
        .right { text-align:right; }
        .total { font-weight:600; }
        .badge { display:inline-block; margin-top:4px; font-size:.7rem; padding:1px 8px; border-radius:999px; }
        .badge.ok { background:rgba(46,164,79,.18); } .badge.bad { background:rgba(214,74,74,.25); } .badge.warn { background:rgba(232,176,74,.25); }
        .details { grid-column:1 / -1; padding:6px 4px 4px 68px; cursor:default; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:8px; margin-bottom:8px; }
        .grid span, .sec { font-size:.72rem; color:var(--secondary-text-color); text-transform:uppercase; letter-spacing:.05em; }
        .grid b { display:block; font-weight:500; font-size:.9rem; }
        .sec { margin:10px 0 4px; }
        .line, .fil { display:flex; justify-content:space-between; gap:10px; padding:4px 0; font-size:.9rem; }
        .fil { display:grid; grid-template-columns:14px 1fr auto 80px; align-items:center; }
        .fil i { width:12px; height:12px; border-radius:3px; border:1px solid rgba(127,127,127,.4); }
        .fil .c { text-align:right; }
        .fn { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        .sum { border-top:1px dashed var(--divider-color); margin-top:4px; }
        .total2 { border-top:1px solid var(--divider-color); margin-top:6px; padding-top:8px; font-size:1rem; }
        .note { font-size:.8rem; color:var(--warning-color, #e8b04a); margin-top:6px; }
        .foot { display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px; margin-top:10px; font-size:.78rem; color:var(--secondary-text-color); }
        a { color:var(--primary-color); text-decoration:none; }
        .more { text-align:center; padding:10px; color:var(--primary-color); cursor:pointer; border-top:1px solid var(--divider-color); }
        .empty, .err { padding:18px 6px; color:var(--secondary-text-color); border-top:1px solid var(--divider-color); }
        .err { color:var(--error-color); }
        @media (max-width: 520px) { .details { padding-left:4px; } }
      </style>
      <ha-card>
        <div class="head">
          <h2>${this._esc(this._cfg.title)}</h2>
          <div class="filters">
            <select id="printer">${opt('', 'Alle Drucker', !this._printer)}${d.printers.map(p => opt(p, p, p === this._printer)).join('')}</select>
            <select id="month">${opt('', 'Alle Monate', !this._month)}${months.map(m => opt(m, mName(m), m === this._month)).join('')}</select>
          </div>
        </div>
        <div class="kpis">
          <div class="kpi"><span>Drucke</span><b>${jobs.length}</b></div>
          <div class="kpi"><span>Strom</span><b>${this._eur(sum('energy_cost'))}</b></div>
          <div class="kpi"><span>Filament</span><b>${this._eur(sum('filament_cost'))}</b></div>
          <div class="kpi"><span>Gesamt</span><b>${this._eur(sum('total_cost'))}</b></div>
        </div>
        ${running}
        ${this._err ? `<div class="err">Daten nicht lesbar: ${this._esc(this._err)}</div>` : ''}
        ${rows || (this._err ? '' : '<div class="empty">Noch keine Drucke erfasst. Der nächste fertige Druck erscheint hier automatisch.</div>')}
        ${jobs.length > this._limit ? `<div class="more" data-more>Weitere ${Math.min(this._cfg.page_size, jobs.length - this._limit)} anzeigen</div>` : ''}
      </ha-card>`;
  }
}

if (!customElements.get('print-cost-card')) customElements.define('print-cost-card', PrintCostCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: 'print-cost-card', name: '3D-Druckkosten', description: 'Alle Drucke mit Strom- und Filamentkosten (3D Print Cost Analyzer).' });

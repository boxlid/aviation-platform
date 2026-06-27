/* Sonic Flight — frontend */
const SF = {};
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const el = (t, c, h) => { const e = document.createElement(t); if (c) e.className = c; if (h != null) e.innerHTML = h; return e; };

async function getJSON(u) { const r = await fetch(u); return r.json(); }
async function send(u, m, b) { const r = await fetch(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : null }); return r.json(); }

const fmtNum = n => (n == null ? '—' : Number(n).toLocaleString());
const esc = s => (s == null ? '' : String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])));

function fmtInterval(sec) {
  if (sec == null) return '—';
  if (sec % 604800 === 0) return (sec / 604800) + 'w';
  if (sec % 86400 === 0) return (sec / 86400) + 'd';
  if (sec % 3600 === 0) return (sec / 3600) + 'h';
  if (sec % 60 === 0) return (sec / 60) + 'm';
  return sec + 's';
}
function ago(ts) {
  if (!ts) return 'never';
  const d = (Date.now() - new Date(ts).getTime()) / 1000;
  if (d < 60) return Math.floor(d) + 's ago';
  if (d < 3600) return Math.floor(d / 60) + 'm ago';
  if (d < 86400) return Math.floor(d / 3600) + 'h ago';
  return Math.floor(d / 86400) + 'd ago';
}
const dt = ts => ts ? new Date(ts).toLocaleString() : '—';
const catBadge = c => c ? `<span class="badge cat-${esc(c)}">${esc(c)}</span>` : '<span class="muted">—</span>';
const cleanType = t => !t ? '' : t.replace('_airport', '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
const statusPill = s => `<span class="status-pill st-${esc(s)}"><span class="dot-s"></span>${esc(s)}</span>`;

/* ── Dashboard ─────────────────────────────────────────────── */
SF.dashboard = async () => {
  const s = await getJSON('/api/stats');
  const cards = [
    ['Charter Aircraft', fmtNum(s.aircraft), 'on Part 135 certificates'],
    ['Operators', fmtNum(s.operators), 'certificate holders'],
    ['ADS-B Ready', fmtNum(s.adsb_ready), 'tails with Mode S hex'],
    ['Registry Records', fmtNum(s.registry), 'full US aircraft registry'],
  ];
  $('#stats').innerHTML = cards.map(([k, v, sub]) => `
    <div class="panel stat"><div class="glow"></div><div class="k">${k}</div><div class="v">${v}</div><div class="sub">${sub}</div></div>`).join('');

  const maxCat = Math.max(...s.by_category.map(c => +c.n), 1);
  $('#cats').innerHTML = s.by_category.map(c => `
    <div style="margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;margin-bottom:5px;font-size:13px">
        <span>${catBadge(c.category)}</span><span class="dim">${fmtNum(c.n)}</span></div>
      <div class="bar"><i style="width:${(c.n / maxCat * 100).toFixed(1)}%"></i></div>
    </div>`).join('');

  $('#topops').innerHTML = s.top_operators.map((o, i) => `
    <tr><td class="muted">${i + 1}</td><td>${esc(o.operator_name)}</td><td class="dim" style="text-align:right">${fmtNum(o.n)}</td></tr>`).join('');

  $('#svc-health').innerHTML = s.services.map(v => `
    <div style="display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.04)">
      ${statusPill(v.enabled ? v.status : 'paused')}
      <span style="flex:1">${esc(v.display_name)}</span>
      <span class="muted" style="font-size:12px">${v.last_finished_at ? ago(v.last_finished_at) : '—'}</span>
    </div>`).join('');
};

/* ── Fleet ─────────────────────────────────────────────────── */
SF.fleet = async () => {
  const run = async () => {
    const q = $('#q').value, cat = $('#cat').value, adsb = $('#adsb').checked;
    const params = new URLSearchParams({ limit: 200 });
    if (q) params.set('q', q);
    if (cat) params.set('category', cat);
    if (adsb) params.set('adsb_ready', 'true');
    const rows = await getJSON('/api/fleet?' + params);
    $('#count').textContent = rows.length + (rows.length === 200 ? '+' : '') + ' aircraft';
    $('#tbody').innerHTML = rows.length ? rows.map(r => `
      <tr>
        <td class="tail">${esc(r.n_number)}</td>
        <td>${catBadge(r.category)}</td>
        <td>${esc(r.manufacturer || '')} <span class="dim">${esc(r.model || r.make_model_series || '')}</span></td>
        <td>${esc(r.operator_name)}</td>
        <td class="hex">${esc(r.mode_s_hex || '—')}</td>
        <td class="muted">${esc(r.registered_owner || '—')}</td>
        <td class="muted">${esc(r.fsdo || '')}</td>
      </tr>`).join('') : '<tr><td colspan="7" class="empty">No matching aircraft</td></tr>';
  };
  $('#q').addEventListener('input', debounce(run, 300));
  $('#cat').addEventListener('change', run);
  $('#adsb').addEventListener('change', run);
  run();
};

/* ── Reusable sortable table ───────────────────────────────────
   Wire click-to-sort on a <table class="sortable"> with th[data-key][data-type].
   Returns {update(rows)} so a search box can refresh the data in place. */
SF.sortable = (table, rows, rowHTML) => {
  const tbody = table.querySelector('tbody');
  const ncols = table.querySelectorAll('thead th').length;
  let key = null, type = 'str', dir = 1;
  const cmp = (a, b) => {
    if (type === 'num') return (parseFloat(a) || 0) - (parseFloat(b) || 0);
    return String(a == null ? '' : a).localeCompare(String(b == null ? '' : b));
  };
  const draw = () => {
    const r = key ? [...rows].sort((x, y) => cmp(x[key], y[key]) * dir) : rows;
    tbody.innerHTML = r.length ? r.map(rowHTML).join('') : `<tr><td colspan="${ncols}" class="empty">No results</td></tr>`;
    table.querySelectorAll('th[data-key]').forEach(th => { th.dataset.dir = th.dataset.key === key ? (dir > 0 ? 'asc' : 'desc') : ''; });
  };
  table.querySelectorAll('th[data-key]').forEach(th => {
    th.onclick = () => {
      if (key === th.dataset.key) dir = -dir;
      else { key = th.dataset.key; type = th.dataset.type || 'str'; dir = 1; }
      draw();
    };
  });
  draw();
  return { update(newRows) { rows = newRows; draw(); } };
};

/* ── Operators (sortable + drill-down links) ───────────────── */
SF.operators = async () => {
  const tbl = $('#tbl');
  const rowHTML = o => `
    <tr>
      <td><a href="/operator/${encodeURIComponent(o.certificate_designator)}">${esc(o.operator_name)}</a></td>
      <td class="num"><b>${fmtNum(o.fleet_size)}</b></td>
      <td class="num dim">${fmtNum(o.jets)}</td>
      <td class="num dim">${fmtNum(o.turboprops)}</td>
      <td class="num dim">${fmtNum(o.helicopters)}</td>
      <td>${o.fsdo ? `<a href="/fsdo?name=${encodeURIComponent(o.fsdo)}">${esc(o.fsdo)}</a>` : '<span class="muted">—</span>'}</td>
    </tr>`;
  let sorter = null;
  const run = async () => {
    const q = $('#q').value;
    const rows = await getJSON('/api/operators?limit=400' + (q ? '&q=' + encodeURIComponent(q) : ''));
    $('#count').textContent = rows.length + ' operators';
    sorter = sorter ? (sorter.update(rows), sorter) : SF.sortable(tbl, rows, rowHTML);
  };
  $('#q').addEventListener('input', debounce(run, 300));
  run();
};

/* ── Operator detail (fleet) ───────────────────────────────── */
SF.operatorDetail = async (designator) => {
  const d = await getJSON('/api/operators/' + encodeURIComponent(designator));
  if (!d || !d.operator) { $('#op-name').textContent = 'Operator not found'; return; }
  const o = d.operator;
  $('#op-name').textContent = o.operator_name;
  $('#op-meta').innerHTML = [
    ['Fleet', fmtNum(o.fleet_size)], ['Jets', fmtNum(o.jets)],
    ['Turboprop', fmtNum(o.turboprops)], ['Helicopters', fmtNum(o.helicopters)],
  ].map(([k, v]) => `<div class="panel stat"><div class="glow"></div><div class="k">${k}</div><div class="v">${v}</div></div>`).join('')
    + `<div class="panel pad" style="grid-column:1/-1"><span class="muted">Certificate</span> <b>${esc(o.certificate_designator)}</b>
        &nbsp;·&nbsp; <span class="muted">FSDO</span> ${o.fsdo ? `<a href="/fsdo?name=${encodeURIComponent(o.fsdo)}">${esc(o.fsdo)}</a>` : '—'}</div>`;
  const rowHTML = r => `
    <tr>
      <td class="tail">${esc(r.n_number)}</td>
      <td>${catBadge(r.category)}</td>
      <td>${esc(r.manufacturer || '')} <span class="dim">${esc(r.model || r.make_model_series || '')}</span></td>
      <td class="hex">${esc(r.mode_s_hex || '—')}</td>
      <td class="muted">${esc(r.registered_owner || '—')}</td>
      <td class="num muted">${esc(r.year_mfr || '')}</td>
    </tr>`;
  SF.sortable($('#tbl'), d.fleet, rowHTML);
};

/* ── FSDO detail (operators based there) ───────────────────── */
SF.fsdoDetail = async () => {
  const name = new URLSearchParams(location.search).get('name') || '';
  $('#fsdo-name').textContent = name || 'FSDO';
  const d = await getJSON('/api/fsdo?name=' + encodeURIComponent(name));
  $('#fsdo-meta').innerHTML = [
    ['FSDO', esc(name), '15px'], ['Operators', fmtNum(d.totals && d.totals.ops), '30px'],
    ['Aircraft', fmtNum(d.totals && d.totals.aircraft), '30px'],
  ].map(([k, v, fs]) => `<div class="panel stat"><div class="k">${k}</div><div class="v" style="font-size:${fs}">${v}</div></div>`).join('');
  const rowHTML = o => `
    <tr>
      <td><a href="/operator/${encodeURIComponent(o.certificate_designator)}">${esc(o.operator_name)}</a></td>
      <td class="num"><b>${fmtNum(o.fleet_size)}</b></td>
      <td class="num dim">${fmtNum(o.jets)}</td>
      <td class="num dim">${fmtNum(o.turboprops)}</td>
      <td class="num dim">${fmtNum(o.helicopters)}</td>
    </tr>`;
  SF.sortable($('#tbl'), d.operators, rowHTML);
};

/* ── Airports (OurAirports) ────────────────────────────────── */
SF.airports = async () => {
  const tbl = $('#tbl');
  const rowHTML = a => `
    <tr>
      <td><a href="/airport/${encodeURIComponent(a.ident)}">${esc(a.name)}</a></td>
      <td class="muted">${esc(cleanType(a.type))}</td>
      <td class="tail">${esc(a.iata_code || '')}</td>
      <td class="dim">${esc(a.icao_code || a.ident)}</td>
      <td>${esc(a.municipality || '')}</td>
      <td class="muted">${esc(a.iso_country || '')}</td>
      <td class="num">${a.longest_runway_ft ? '<b>' + fmtNum(a.longest_runway_ft) + '</b> ft' : '<span class="muted">—</span>'}</td>
      <td class="num dim">${fmtNum(a.runway_count)}</td>
    </tr>`;
  let sorter = null;
  const run = async () => {
    const params = new URLSearchParams({ limit: 300, min_runway: $('#minrwy').value });
    if ($('#q').value) params.set('q', $('#q').value);
    if ($('#country').value) params.set('country', $('#country').value);
    const rows = await getJSON('/api/airports?' + params);
    $('#count').textContent = rows.length + (rows.length === 300 ? '+' : '') + ' airports';
    sorter = sorter ? (sorter.update(rows), sorter) : SF.sortable(tbl, rows, rowHTML);
  };
  ['#q', '#country'].forEach(s => $(s).addEventListener('input', debounce(run, 300)));
  $('#minrwy').addEventListener('change', run);
  run();
};

/* ── Airport detail (everything we have) ───────────────────── */
SF.airportDetail = async (ident) => {
  const d = await getJSON('/api/airports/' + encodeURIComponent(ident));
  if (!d || !d.airport) { $('#ap-name').textContent = 'Airport not found'; return; }
  const a = d.airport, cap = d.capability || {};
  $('#ap-name').textContent = a.name;
  const coords = (a.latitude_deg != null && a.longitude_deg != null)
    ? `${(+a.latitude_deg).toFixed(4)}, ${(+a.longitude_deg).toFixed(4)}` : '—';
  const field = (k, v) => v != null && v !== '' && v !== undefined
    ? `<div><div class="k muted" style="font-size:11px;text-transform:uppercase;letter-spacing:1px">${k}</div><div style="margin-top:3px">${esc(v)}</div></div>` : '';
  const link = (k, url) => url ? `<div><div class="k muted" style="font-size:11px;text-transform:uppercase;letter-spacing:1px">${k}</div><div style="margin-top:3px"><a href="${esc(url)}" target="_blank" rel="noopener">open ↗</a></div></div>` : '';
  const cards = [
    ['Size', cleanType(a.type) || '—'],
    ['Longest runway', cap.longest_runway_ft ? fmtNum(cap.longest_runway_ft) + ' ft' : '—'],
    ['Runways', fmtNum(cap.runway_count)],
    ['Elevation', a.elevation_ft != null && a.elevation_ft !== '' ? fmtNum(a.elevation_ft) + ' ft' : '—'],
  ];
  $('#ap-meta').innerHTML = cards.map(([k, v]) =>
    `<div class="panel stat"><div class="glow"></div><div class="k">${k}</div><div class="v" style="font-size:22px">${esc(v)}</div></div>`).join('')
    + `<div class="panel pad" style="grid-column:1/-1;display:flex;flex-wrap:wrap;gap:26px">
        ${field('IATA', a.iata_code)} ${field('ICAO', a.icao_code)} ${field('Ident', a.ident)}
        ${field('Local', a.local_code)} ${field('GPS', a.gps_code)}
        ${field('Country', a.iso_country)} ${field('Region', a.iso_region)} ${field('City', a.municipality)}
        ${field('Continent', a.continent)} ${field('Coordinates', coords)}
        ${field('Scheduled service', a.scheduled_service ? 'Yes' : 'No')}
        ${link('Website', a.home_link)} ${link('Wikipedia', a.wikipedia_link)}
      </div>`;
  const rwy = (d.runways || []).map(r => ({ ...r, ends: `${r.le_ident || ''}/${r.he_ident || ''}` }));
  const rowHTML = r => `
    <tr>
      <td class="tail">${esc(r.ends)}</td>
      <td class="num">${r.length_ft ? '<b>' + fmtNum(r.length_ft) + '</b> ft' : '—'}</td>
      <td class="num dim">${r.width_ft ? fmtNum(r.width_ft) + ' ft' : '—'}</td>
      <td>${esc(r.surface || '—')}</td>
      <td class="muted">${r.lighted ? 'Yes' : 'No'}</td>
      <td>${r.closed ? '<span style="color:var(--bad)">Closed</span>' : '<span style="color:var(--good)">Open</span>'}</td>
    </tr>`;
  SF.sortable($('#tbl'), rwy, rowHTML);
};

/* ── Charter routes (T-100) ────────────────────────────────── */
SF.routes = async () => {
  const run = async () => {
    const q = $('#q').value, origin = $('#origin').value, dest = $('#dest').value;
    const params = new URLSearchParams({ limit: 300 });
    if (q) params.set('q', q);
    if (origin) params.set('origin', origin);
    if (dest) params.set('dest', dest);
    const rows = await getJSON('/api/routes?' + params);
    $('#count').textContent = rows.length + (rows.length === 300 ? '+' : '') + ' routes';
    $('#tbody').innerHTML = rows.length ? rows.map(r => `
      <tr>
        <td>${esc(r.carrier_name)}</td>
        <td class="tail">${esc(r.origin)}</td>
        <td><span class="tail">${esc(r.dest)}</span> <span class="muted" style="font-size:12px">${esc(r.dest_city || '')}</span></td>
        <td style="text-align:right"><b>${fmtNum(Math.round(r.departures))}</b></td>
        <td style="text-align:right" class="dim">${fmtNum(Math.round(r.passengers))}</td>
        <td style="text-align:right" class="muted">${fmtNum(r.distance)}</td>
        <td style="text-align:right" class="muted">${fmtNum(r.months)}</td>
      </tr>`).join('') : '<tr><td colspan="7" class="empty">No charter segments — run the BTS T-100 Segment service.</td></tr>';
  };
  ['#q', '#origin', '#dest'].forEach(s => $(s).addEventListener('input', debounce(run, 300)));
  run();
};

/* ── Emails ────────────────────────────────────────────────── */
SF.emails = async () => {
  const status = await getJSON('/api/gmail/status');
  const banner = $('#gmail-banner');
  const params = new URLSearchParams(location.search);
  if (params.get('connected')) banner.innerHTML = '<div class="note">✓ Gmail connected. Run the Gmail Ingestion service to pull email.</div>';
  else if (params.get('error')) banner.innerHTML = `<div class="note" style="border-color:var(--bad)">Gmail error: ${esc(params.get('error'))}</div>`;
  else if (!status.has_credentials) banner.innerHTML = '<div class="note">Gmail not configured. Add <code>secrets/gmail_credentials.json</code> (Google Cloud OAuth client), then connect.</div>';
  else if (!status.connected) banner.innerHTML = '<div class="note">Gmail credentials present. <a class="btn sm primary" href="/api/gmail/connect">Connect Gmail</a></div>';
  else banner.innerHTML = '<div class="note">✓ Gmail connected.</div>';

  const run = async () => {
    const q = $('#q').value;
    const rows = await getJSON('/api/emails?limit=80' + (q ? '&q=' + encodeURIComponent(q) : ''));
    $('#count').textContent = rows.length + ' emails';
    $('#tbody').innerHTML = rows.length ? rows.map(r => `
      <tr><td><b>${esc(r.from_name || r.from_addr)}</b><br><span class="muted" style="font-size:12px">${esc(r.from_addr)}</span></td>
      <td>${esc(r.subject || '(no subject)')}<br><span class="muted" style="font-size:12px">${esc(r.snippet || '')}</span></td>
      <td class="muted" style="white-space:nowrap">${dt(r.internal_ts)}</td></tr>`).join('')
      : '<tr><td colspan="3" class="empty">No emails yet — connect Gmail and run the Gmail Ingestion service.</td></tr>';
  };
  $('#q').addEventListener('input', debounce(run, 300));
  run();
};

/* ── Services list ─────────────────────────────────────────── */
SF.services = async () => {
  const render = async () => {
    const rows = await getJSON('/api/services');
    $('#tbody').innerHTML = rows.map(s => {
      const st = s.enabled ? s.status : 'paused';
      return `<tr>
        <td><a href="/settings/services/${s.name}"><b>${esc(s.display_name)}</b></a><br><span class="muted" style="font-size:12px">${esc(s.description)}</span></td>
        <td>${statusPill(st)}</td>
        <td>${intervalEditor(s)}</td>
        <td class="muted" style="white-space:nowrap">${s.last_finished_at ? ago(s.last_finished_at) : 'never'}</td>
        <td style="white-space:nowrap">${actions(s)}</td>
      </tr>`;
    }).join('');
    bind();
  };
  const intervalEditor = s => `
    <select data-int="${s.name}" class="range">
      ${[['5m',300],['15m',900],['1h',3600],['6h',21600],['12h',43200],['1d',86400],['1w',604800]]
        .map(([l,v]) => `<option value="${v}" ${v===s.interval_seconds?'selected':''}>${l}</option>`).join('')}
      ${[300,900,3600,21600,43200,86400,604800].includes(s.interval_seconds) ? '' : `<option value="${s.interval_seconds}" selected>${fmtInterval(s.interval_seconds)}</option>`}
    </select>`;
  const actions = s => `
    <button class="btn sm" data-run="${s.name}">Run now</button>
    ${s.enabled
      ? `<button class="btn sm danger" data-pause="${s.name}">Pause</button>`
      : `<button class="btn sm primary" data-resume="${s.name}">Restart</button>`}
    <a class="btn sm ghost" href="/settings/services/${s.name}">Logs</a>`;
  const bind = () => {
    $$('[data-run]').forEach(b => b.onclick = async () => { b.disabled = true; b.textContent = 'Running…'; await send(`/api/services/${b.dataset.run}/run`, 'POST'); setTimeout(render, 800); });
    $$('[data-pause]').forEach(b => b.onclick = async () => { await send(`/api/services/${b.dataset.pause}/pause`, 'POST'); render(); });
    $$('[data-resume]').forEach(b => b.onclick = async () => { await send(`/api/services/${b.dataset.resume}/resume`, 'POST'); render(); });
    $$('[data-int]').forEach(sel => sel.onchange = async () => { await send(`/api/services/${sel.dataset.int}/interval`, 'PATCH', { seconds: +sel.value }); });
  };
  render();
  setInterval(render, 5000);
};

/* ── Service detail + logs ─────────────────────────────────── */
SF.serviceDetail = async (name) => {
  const render = async () => {
    const s = await getJSON('/api/services/' + name);
    if (!s) return;
    $('#svc-title').textContent = s.display_name;
    $('#svc-desc').textContent = s.description;
    const st = s.enabled ? s.status : 'paused';
    $('#svc-meta').innerHTML = [
      ['Status', statusPill(st)],
      ['Interval', fmtInterval(s.interval_seconds)],
      ['Last run', dt(s.last_finished_at)],
      ['Duration', s.last_duration_ms != null ? s.last_duration_ms + ' ms' : '—'],
      ['Next run', s.enabled ? dt(s.next_run_at) : 'paused'],
      ['Last result', s.last_result ? `<span class="hex">${esc(JSON.stringify(s.last_result))}</span>` : (s.last_error ? `<span style="color:var(--bad)">${esc(s.last_error)}</span>` : '—')],
    ].map(([k, v]) => `<div class="panel pad"><div class="k muted" style="font-size:11px;text-transform:uppercase;letter-spacing:1px">${k}</div><div style="margin-top:6px">${v}</div></div>`).join('');

    const logs = await getJSON(`/api/services/${name}/logs?limit=300`);
    $('#logs').innerHTML = logs.length ? logs.map(l => `
      <div class="logline"><span class="t">${dt(l.ts)}</span><span class="lv lv-${esc(l.level)}">${esc(l.level)}</span><span>${esc(l.message)}</span></div>`).join('')
      : '<div class="empty">No logs yet</div>';
  };
  $('#run-btn').onclick = async () => { $('#run-btn').disabled = true; await send(`/api/services/${name}/run`, 'POST'); setTimeout(() => { $('#run-btn').disabled = false; render(); }, 900); };
  render();
  setInterval(render, 4000);
};

function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

/* ── Notification bell dot — shown ONLY when there is an unread notification ── */
SF.checkNotifications = async () => {
  try {
    const n = await getJSON('/api/notifications?limit=1');
    const bell = document.getElementById('bell');
    if (!bell) return;
    const dot = bell.querySelector('.dot');
    if (n.unread > 0 && !dot) { const s = document.createElement('span'); s.className = 'dot'; bell.appendChild(s); }
    else if (!n.unread && dot) dot.remove();
  } catch (e) { /* bell stays clean on error */ }
};
document.addEventListener('DOMContentLoaded', SF.checkNotifications);

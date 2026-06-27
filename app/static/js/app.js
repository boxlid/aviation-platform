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

/* ── Operators ─────────────────────────────────────────────── */
SF.operators = async () => {
  const run = async () => {
    const q = $('#q').value;
    const rows = await getJSON('/api/operators?limit=200' + (q ? '&q=' + encodeURIComponent(q) : ''));
    $('#count').textContent = rows.length + ' operators';
    $('#tbody').innerHTML = rows.map(r => `
      <tr>
        <td>${esc(r.operator_name)}</td>
        <td style="text-align:right"><b>${fmtNum(r.fleet_size)}</b></td>
        <td style="text-align:right" class="dim">${fmtNum(r.jets)}</td>
        <td style="text-align:right" class="dim">${fmtNum(r.turboprops)}</td>
        <td style="text-align:right" class="dim">${fmtNum(r.helicopters)}</td>
        <td class="muted">${esc(r.fsdo || '')}</td>
      </tr>`).join('');
  };
  $('#q').addEventListener('input', debounce(run, 300));
  run();
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

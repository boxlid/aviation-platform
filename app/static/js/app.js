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
const titleCase = s => !s ? s : String(s).toLowerCase().replace(/\b[a-z]/g, c => c.toUpperCase())
  .replace(/\b(Llc|Inc|Llp|Lllp|Lp|Pc|Pa|Usa|Us|Ii|Iii|Iv)\b/g, m => m.toUpperCase());
const statusPill = s => `<span class="status-pill st-${esc(s)}"><span class="dot-s"></span>${esc(s)}</span>`;

/* FAA registration decodes */
const REGTYPE = { '1': 'Individual', '2': 'Partnership', '3': 'Corporation', '4': 'Co-owned', '5': 'Government', '7': 'LLC', '8': 'Non-citizen corp', '9': 'Non-citizen co-owned' };
const regType = c => REGTYPE[c] || (c ? 'Type ' + c : '—');
const STATUS = {
  V: ['Valid', 'good'], T: ['Valid (trustee)', 'good'],
  R: ['Registration pending', 'warn'], M: ['Valid / pending', 'warn'], N: ['Non-citizen review', 'warn'],
  A: ['Triennial mailed', 'warn'], S: ['Triennial mailed', 'warn'],
  E: ['Revoked', 'bad'], W: ['Deregistered', 'bad'], D: ['Expired dealer', 'bad'], X: ['Enforcement letter', 'bad'],
  Z: ['Reserved', 'neutral'],
};
const statusInfo = c => !c ? ['—', 'neutral'] : (STATUS[c] || (/^\d+$/.test(c) ? ['In process', 'warn'] : [c, 'neutral']));
const statusBadge = c => { const [l, t] = statusInfo(c); return `<span class="badge st-tier-${t}">${esc(l)}</span>`; };
const seats = v => { const n = parseInt(v, 10); return n ? n : '—'; };

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
        <td><a class="tail" href="/aircraft/${encodeURIComponent(r.n_number)}">${esc(r.n_number)}</a></td>
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
      <td><a class="tail" href="/aircraft/${encodeURIComponent(r.n_number)}">${esc(r.n_number)}</a></td>
      <td>${catBadge(r.category)}</td>
      <td>${esc(r.manufacturer || '')} <span class="dim">${esc(r.model || r.make_model_series || '')}</span></td>
      <td class="num">${seats(r.num_seats)}</td>
      <td class="hex">${esc(r.mode_s_hex || '—')}</td>
      <td>${statusBadge(r.status_code)}</td>
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

/* ── Aircraft / tail detail ────────────────────────────────── */
SF.aircraftDetail = async (n) => {
  const d = await getJSON('/api/aircraft/' + encodeURIComponent(n));
  if (!d) { $('#ac-name').textContent = 'Aircraft not found'; return; }
  const r = d.registry || {};
  $('#ac-name').innerHTML = `${esc(d.n_number)} ${r.manufacturer ? '<span class="muted" style="font-size:14px">' + esc(titleCase(r.manufacturer)) + ' ' + esc(r.model || '') + '</span>' : ''}`;
  $('#ac-stats').innerHTML = [
    ['Category', r.category || '—'], ['Seats', seats(r.num_seats)],
    ['Engine', r.engine_type || '—'], ['Year', r.year_mfr || '—'],
  ].map(([k, v]) => `<div class="panel stat"><div class="glow"></div><div class="k">${k}</div><div class="v" style="font-size:20px">${esc(v)}</div></div>`).join('');

  const kv = (k, v) => (v == null || v === '') ? '' : `<div class="kv"><span class="kv-k">${k}</span><span class="kv-v">${v}</span></div>`;
  const ownerLoc = [titleCase(r.city), r.state].filter(Boolean).join(', ');
  $('#ac-info').innerHTML =
    kv('Manufacturer', esc(titleCase(r.manufacturer))) + kv('Model', esc(r.model)) +
    kv('Aircraft type', esc(r.aircraft_type)) + kv('Engine type', esc(r.engine_type)) +
    kv('Engines', r.num_engines ? parseInt(r.num_engines, 10) : '') + kv('Seats', r.num_seats ? seats(r.num_seats) : '') +
    kv('Serial number', esc(r.serial_number)) +
    kv('Mode S (hex)', r.mode_s_hex ? '<span class="hex">' + esc(r.mode_s_hex) + '</span>' : '') +
    kv('Mode S (octal)', esc(r.mode_s_code_octal)) +
    kv('Registration', statusBadge(r.status_code)) +
    kv('Registered owner', esc(titleCase(r.registrant_name))) +
    kv('Owner type', esc(regType(r.registrant_type))) +
    kv('Owner location', esc(ownerLoc));

  SF.sortable($('#ac-ops'), d.operators, o => `
    <tr><td><a href="/operator/${encodeURIComponent(o.certificate_designator)}">${esc(o.operator_name)}</a></td>
    <td class="tail">${esc(o.certificate_designator)}</td>
    <td>${o.fsdo ? `<a href="/fsdo?name=${encodeURIComponent(o.fsdo)}">${esc(o.fsdo)}</a>` : '<span class="muted">—</span>'}</td></tr>`);

  // External trackers + photos (link out — no API needed)
  const reg = encodeURIComponent(d.n_number), hex = (r.mode_s_hex || '').toLowerCase();
  const links = [];
  if (hex) links.push(['ADS-B Exchange', `https://globe.adsbexchange.com/?icao=${hex}`]);
  links.push(['Flightradar24', `https://www.flightradar24.com/data/aircraft/${d.n_number.toLowerCase()}`]);
  links.push(['FlightAware', `https://www.flightaware.com/live/flight/${reg}`]);
  links.push(['JetPhotos', `https://www.jetphotos.com/registration/${reg}`]);
  links.push(['Planespotters', `https://www.planespotters.net/photos/reg/${reg}`]);
  $('#ac-links').innerHTML = '<div class="section-title" style="margin-top:0">Track &amp; photos <span class="line"></span></div>'
    + '<div style="display:flex;flex-wrap:wrap;gap:8px">'
    + links.map(([t, u]) => `<a class="btn sm" href="${u}" target="_blank" rel="noopener">${t} ↗</a>`).join('')
    + '</div>';

  $('#ac-adsb').innerHTML = r.mode_s_hex
    ? `Live in-app position &amp; home-base inference will appear here once an ADS-B movement feed is wired. Join key: Mode S hex <span class="hex">${esc(r.mode_s_hex)}</span>.`
    : 'No Mode S hex on file — ADS-B tracking unavailable for this tail.';
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
  const a = d.airport, cap = d.capability || {}, faa = d.faa || {};
  $('#ap-name').textContent = a.name;
  const lat = a.latitude_deg, lon = a.longitude_deg;
  const coords = (lat != null && lon != null) ? `${(+lat).toFixed(4)}, ${(+lon).toFixed(4)}` : '—';

  // Top stat cards
  const cards = [
    ['Size', cleanType(a.type) || '—'],
    ['Longest runway', cap.longest_runway_ft ? fmtNum(cap.longest_runway_ft) + ' ft' : '—'],
    ['Runways', fmtNum(cap.runway_count)],
    ['Elevation', a.elevation_ft != null && a.elevation_ft !== '' ? fmtNum(a.elevation_ft) + ' ft' : '—'],
  ];
  $('#ap-stats').innerHTML = cards.map(([k, v]) =>
    `<div class="panel stat"><div class="glow"></div><div class="k">${k}</div><div class="v" style="font-size:22px">${esc(v)}</div></div>`).join('');

  // Vertical key/value pane — label left, value right
  const kv = (k, v) => (v == null || v === '' ) ? '' : `<div class="kv"><span class="kv-k">${k}</span><span class="kv-v">${v}</span></div>`;
  const kvLink = (k, url) => url ? `<div class="kv"><span class="kv-k">${k}</span><span class="kv-v"><a href="${esc(url)}" target="_blank" rel="noopener">open ↗</a></span></div>` : '';
  // Drop redundant codes (Ident/Local/GPS that just duplicate IATA/ICAO), render as a compact 2-col grid
  const codes = new Set([a.iata_code, a.icao_code].filter(Boolean));
  const extra = [['Ident', a.ident], ['Local', a.local_code], ['GPS', a.gps_code]].filter(([k, v]) => v && !codes.has(v));
  $('#ap-info').innerHTML = '<div class="kv-grid">' +
    kv('IATA', esc(a.iata_code)) + kv('ICAO', esc(a.icao_code)) +
    extra.map(([k, v]) => kv(k, esc(v))).join('') +
    kv('City', esc(titleCase(a.municipality))) + kv('Region', esc(a.iso_region)) + kv('Country', esc(a.iso_country)) +
    kv('Coordinates', esc(coords)) + kv('Elevation', a.elevation_ft != null ? fmtNum(a.elevation_ft) + ' ft' : '') +
    kv('Scheduled', a.scheduled_service ? 'Yes' : 'No') +
    (faa && faa.owner_name ? kv('Owner', esc(titleCase(faa.owner_name))) + kv('Owner phone', esc(faa.owner_phone)) : '') +
    (faa && faa.manager_name ? kv('Manager', esc(titleCase(faa.manager_name))) + kv('Manager phone', esc(faa.manager_phone)) : '') +
    kvLink('Website', a.home_link) + kvLink('Wikipedia', a.wikipedia_link) +
    '</div>';

  // Map (Leaflet + CARTO dark tiles — no API key)
  if (lat != null && lon != null && window.L) {
    const map = L.map('map', { zoomControl: true, attributionControl: true }).setView([+lat, +lon], 12);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
      maxZoom: 19, attribution: '© OpenStreetMap © CARTO'
    }).addTo(map);
    L.circleMarker([+lat, +lon], { radius: 8, color: '#3ce0ff', fillColor: '#3ce0ff', fillOpacity: 0.55, weight: 2 })
      .addTo(map).bindPopup(esc(a.name));
    setTimeout(() => map.invalidateSize(), 120);
  } else {
    $('#map').innerHTML = '<div class="empty">No coordinates</div>';
  }

  // Runways
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

  SF.airportWeather(ident);
};

/* ── Airport weather (aviationweather.gov) ─────────────────── */
const zulu = s => { const d = new Date(s * 1000); const p = n => String(n).padStart(2, '0'); return `${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}Z`; };
const ceiling = clouds => {
  const c = (clouds || []).filter(x => ['BKN', 'OVC', 'OVX'].includes(x.cover) && x.base != null);
  return c.length ? Math.min(...c.map(x => x.base)) : null;
};
const cloudStr = clouds => (clouds || []).map(c => c.cover + (c.base != null ? ' ' + fmtNum(c.base) : '')).join(', ') || 'Clear';

SF.airportWeather = async (ident) => {
  const wx = $('#wx');
  wx.innerHTML = '<div class="section-title">Weather <span class="line"></span></div><div class="panel pad muted">Loading weather…</div>';
  const w = await getJSON('/api/airports/' + encodeURIComponent(ident) + '/weather');
  let html = '<div class="section-title">Weather <span class="line"></span></div>';
  if (!w || (!w.metar && !w.taf)) {
    wx.innerHTML = html + '<div class="note">No reporting weather station at this airport.</div>';
    return;
  }
  const m = w.metar;
  if (m) {
    const fc = m.fltCat || '—';
    const inHg = m.altim != null ? (m.altim / 33.8639).toFixed(2) + ' inHg' : '—';
    const ceil = ceiling(m.clouds);
    const wind = m.wdir != null ? `${m.wdir === 0 && m.wspd ? 'VRB' : m.wdir + '°'} @ ${fmtNum(m.wspd || 0)} kt${m.wgst ? ' G' + m.wgst : ''}` : '—';
    const cells = [
      ['Wind', wind], ['Visibility', m.visib != null ? m.visib + ' SM' : '—'],
      ['Ceiling', ceil != null ? fmtNum(ceil) + ' ft' : 'Unlimited'], ['Clouds', cloudStr(m.clouds)],
      ['Temp', m.temp != null ? Math.round(m.temp) + '°C' : '—'], ['Dewpoint', m.dewp != null ? Math.round(m.dewp) + '°C' : '—'],
      ['Altimeter', inHg],
    ];
    html += `<div class="panel pad wx-now">
      <div class="wx-head">
        <span class="fc fc-${esc(fc)}">${esc(fc)}</span>
        <div><b>Current conditions</b><br><span class="muted" style="font-size:12px">Observed ${m.obsTime ? ago(m.obsTime * 1000) : '—'} · ${esc(m.name || ident)}</span></div>
      </div>
      <div class="wx-grid">${cells.map(([k, v]) => `<div><div class="kv-k">${k}</div><div class="wx-v">${esc(v)}</div></div>`).join('')}</div>
      <div class="logs" style="margin-top:12px;max-height:none">${esc(m.rawOb || '')}</div>
    </div>`;
  }
  const t = w.taf;
  if (t) {
    const periods = (t.fcsts || []).map(f => {
      const chg = f.fcstChange ? esc(f.fcstChange) + (f.probability ? ' ' + f.probability + '%' : '') : 'FROM';
      const wind = f.wdir != null ? `${f.wdir}° @ ${fmtNum(f.wspd || 0)}kt${f.wgst ? 'G' + f.wgst : ''}` : '—';
      return `<tr><td class="muted" style="white-space:nowrap">${zulu(f.timeFrom)}–${zulu(f.timeTo)}</td>
        <td><span class="badge">${chg}</span></td><td>${wind}</td><td>${f.visib != null ? esc(f.visib) + ' SM' : '—'}</td>
        <td>${esc(cloudStr(f.clouds))}</td><td class="muted">${esc(f.wxString || '')}</td></tr>`;
    }).join('');
    html += `<div class="panel pad" style="margin-top:14px">
      <div style="display:flex;justify-content:space-between;align-items:baseline">
        <b>Forecast (TAF)</b><span class="muted" style="font-size:12px">Issued ${t.issueTime ? new Date(t.issueTime).toLocaleString() : '—'}</span></div>
      <div class="logs" style="margin:10px 0;max-height:none">${esc(t.rawTAF || '')}</div>
      <table><thead><tr><th>Period (Z)</th><th>Type</th><th>Wind</th><th>Vis</th><th>Clouds</th><th>Wx</th></tr></thead><tbody>${periods}</tbody></table>
    </div>`;
  }
  if (w.hazards && w.hazards.length) {
    html += `<div class="panel pad" style="margin-top:14px"><b>Active hazards over this airport</b>` +
      w.hazards.map(h => `<div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.05)">
        <span class="badge" style="color:var(--warn);border-color:var(--warn)">${esc(h.hazard || h.source)}</span>
        <span class="muted" style="font-size:12px;margin-left:8px">until ${h.validTimeTo ? zulu(h.validTimeTo) : '—'}${h.altitudeLow != null ? ' · FL' + h.altitudeLow + '–' + h.altitudeHi : ''}</span>
        <div class="logs" style="margin-top:6px;max-height:none">${esc((h.raw || '').slice(0, 400))}</div></div>`).join('') + `</div>`;
  }
  if (w.pireps && w.pireps.length) {
    html += `<div class="panel pad" style="margin-top:14px"><b>Nearby pilot reports</b>` +
      w.pireps.map(p => `<div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,.05);font-size:12.5px">
        <span class="muted">${p.obsTime ? ago(p.obsTime * 1000) : ''} · ${esc(p.acType || '')}${p.fltLvl ? ' · FL' + p.fltLvl : ''}</span>
        <div class="hex" style="margin-top:3px">${esc(p.rawOb || '')}</div></div>`).join('') + `</div>`;
  }
  wx.innerHTML = html;
};

/* ── Charter routes (T-100) ────────────────────────────────── */
SF.routes = async () => {
  const tbl = $('#tbl');
  const routeUrl = r => `/route?carrier=${encodeURIComponent(r.unique_carrier)}&origin=${encodeURIComponent(r.origin)}&dest=${encodeURIComponent(r.dest)}`;
  const rowHTML = r => `
    <tr>
      <td><a href="${routeUrl(r)}">${esc(r.carrier_name)}</a></td>
      <td><a class="tail" href="${routeUrl(r)}">${esc(r.origin)}</a></td>
      <td>${esc(r.origin_city || '')}</td>
      <td class="muted">${esc(r.origin_state || '')}</td>
      <td><a class="tail" href="${routeUrl(r)}">${esc(r.dest)}</a></td>
      <td>${esc(r.dest_city || '')}</td>
      <td class="muted">${esc(r.dest_state || '')}</td>
      <td class="num"><b>${fmtNum(Math.round(r.departures))}</b></td>
      <td class="num dim">${fmtNum(Math.round(r.passengers))}</td>
      <td class="num muted">${fmtNum(r.distance)}</td>
    </tr>`;
  let sorter = null;
  const run = async () => {
    const params = new URLSearchParams({ limit: 500 });
    if ($('#q').value) params.set('q', $('#q').value);
    if ($('#origin').value) params.set('origin', $('#origin').value);
    if ($('#dest').value) params.set('dest', $('#dest').value);
    const rows = await getJSON('/api/routes?' + params);
    $('#count').textContent = rows.length + (rows.length === 500 ? '+' : '') + ' routes';
    sorter = sorter ? (sorter.update(rows), sorter) : SF.sortable(tbl, rows, rowHTML);
  };
  ['#q', '#origin', '#dest'].forEach(s => $(s).addEventListener('input', debounce(run, 300)));
  run();
};

/* ── Route detail (T-100) ──────────────────────────────────── */
SF.routeDetail = async () => {
  const p = new URLSearchParams(location.search);
  const d = await getJSON('/api/route?carrier=' + encodeURIComponent(p.get('carrier') || '') +
    '&origin=' + encodeURIComponent(p.get('origin') || '') + '&dest=' + encodeURIComponent(p.get('dest') || ''));
  if (!d || !d.summary) { $('#rt-title').textContent = 'Route not found'; return; }
  const s = d.summary;
  const oLink = d.origin_airport ? `<a href="/airport/${encodeURIComponent(d.origin_airport.ident)}">${esc(d.origin)}</a>` : esc(d.origin);
  const dLink = d.dest_airport ? `<a href="/airport/${encodeURIComponent(d.dest_airport.ident)}">${esc(d.dest)}</a>` : esc(d.dest);
  $('#rt-title').innerHTML = `${esc(s.carrier_name)} &nbsp;·&nbsp; ${oLink} → ${dLink}`;
  $('#rt-sub').innerHTML = `${esc(s.origin_city || '')}, ${esc(s.origin_state || '')} → ${esc(s.dest_city || '')}, ${esc(s.dest_state || '')}`;
  const cards = [
    ['Departures', fmtNum(Math.round(s.departures))], ['Passengers', fmtNum(Math.round(s.passengers))],
    ['Seats', fmtNum(Math.round(s.seats))], ['Distance', s.distance ? fmtNum(s.distance) + ' mi' : '—'],
    ['Months active', fmtNum(s.months)], ['Avg pax/dep', s.departures ? (s.passengers / s.departures).toFixed(1) : '—'],
  ];
  $('#rt-stats').innerHTML = cards.map(([k, v]) =>
    `<div class="panel stat"><div class="glow"></div><div class="k">${k}</div><div class="v" style="font-size:22px">${esc(v)}</div></div>`).join('');

  const M = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  SF.sortable($('#rt-monthly'), d.monthly.map(m => ({ ...m, period: `${M[m.month]} ${m.year}` })), m => `
    <tr><td>${esc(m.period)}</td><td class="num"><b>${fmtNum(Math.round(m.departures))}</b></td>
    <td class="num dim">${fmtNum(Math.round(m.seats))}</td><td class="num dim">${fmtNum(Math.round(m.passengers))}</td></tr>`);
  SF.sortable($('#rt-aircraft'), d.aircraft, a => `
    <tr><td>${esc(a.aircraft_name || '—')}</td><td class="tail">${esc(a.aircraft_type)}</td>
    <td class="num"><b>${fmtNum(Math.round(a.departures))}</b></td>
    <td class="num dim">${fmtNum(Math.round(a.passengers))}</td></tr>`);
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

/* QuChen VPN — 前端逻辑 */
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
// 设置入口：用于显示更新红点（此前未定义，paintUpdate 会在此抛 ReferenceError）
const navBtn = document.querySelector('.nav-item[data-page="settings"]');

let API = null;
let STATE = null;
let NODES = [];
let MOCK = false;
let filterProto = 'all';
let filterCountry = '全部';
let nodeLimit = 120;
const G_SELECT = '🚀 节点选择';
const G_AUTO = '♻️ 自动选择';
const G_FALLBACK = '🔯 故障转移';
let drawerLimit = 200;
let searchText = '';
let drawerTab = 'all';
let drawerSearch = '';
let pendingNode = null;
let timer = null;
let lastLogLen = -1;

/* ---------------------------------------------------------------- 工具 */
const fmtRate = (n) => {
  n = Number(n) || 0;
  if (n < 1024) return n + 'B/s';
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + 'KB/s';
  return (n / 1024 / 1024).toFixed(2) + 'MB/s';
};
const fmtSize = (n) => {
  n = Number(n) || 0;
  if (n < 1024) return n + ' B';
  if (n < 1024 ** 2) return (n / 1024).toFixed(1) + ' KB';
  if (n < 1024 ** 3) return (n / 1024 ** 2).toFixed(2) + ' MB';
  return (n / 1024 ** 3).toFixed(2) + ' GB';
};
const fmtDur = (s) => {
  s = Math.max(0, Number(s) || 0);
  const h = String(Math.floor(s / 3600)).padStart(2, '0');
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${h}:${m}:${ss}`;
};
const delayClass = (d) => (!d ? 'd-none' : d < 150 ? 'd-good' : d < 400 ? 'd-mid' : 'd-bad');
const delayText = (d) => (!d ? '待测速' : d + ' ms');

function toast(msg, kind = 'ok') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  $('#toastWrap').appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(6px)';
    el.style.transition = 'all .2s';
    setTimeout(() => el.remove(), 220);
  }, 2600);
}

/* ---------------------------------------------------------------- 桥接 */
let _booted = false;
function bridgeReady() {
  if (_booted || !window.pywebview || !window.pywebview.api) return;
  _booted = true;
  API = window.pywebview.api;
  boot();
}
// The bridge may already be there: pywebview can fire 'pywebviewready' before this script runs.
if (window.pywebview && window.pywebview.api) bridgeReady();
else window.addEventListener('pywebviewready', bridgeReady);

/* 浏览器内预览（无 pywebview 时用假数据，保证界面可独立调试） */
function mockApi() {
  MOCK = true;
  const nodes = [];
  const countries = [['🇭🇰', '香港'], ['🇯🇵', '日本'], ['🇸🇬', '新加坡'], ['🇺🇸', '美国'], ['🇩🇪', '德国'], ['🇰🇷', '韩国']];
  let i = 0;
  for (const [flag, name] of countries) {
    for (let k = 1; k <= 6; k++) {
      nodes.push({
        name: `${flag} ${name} ${String(++i).padStart(2, '0')}`, type: ['vmess', 'vless', 'trojan', 'ss'][k % 4],
        server: `node-${i}.example.com`, port: 443, delay: 60 + ((i * 37) % 380), country: name, flag,
      });
    }
  }
  const st = {
    version: '1.0.0', connected: false, node: nodes[0].name, node_country: '香港', node_type: 'vmess',
    node_count: nodes.length, pool_updated: '11-09 20:10', uptime: 0, up: 0, down: 0,
    total_up: 1024 * 300, total_down: 1024 * 1024 * 40, mode: 'rule', sys_proxy: true, tun: false,
    mixed_port: 7890, ctrl_port: 9090, admin: false, task: { running: false, msg: '', progress: 0 },
    logs: ['20:10:01 [core] 演示模式'], theme: 'light', auto_start: false, auto_connect: false,
    sources: [], harvested: 13528, stats_days: [], stat_total: { up: 0, down: 0 },
  };
  return {
    bootstrap: async () => ({ state: st, nodes, home: 'C:/Users/you/AppData/Roaming/QuChenVPN' }),
    state: async () => st,
    nodes: async () => nodes,
    connect: async () => { st.connected = true; st.task.msg = '连接成功'; return { ok: true }; },
    disconnect: async () => { st.connected = false; return { ok: true }; },
    select_node: async (n) => { st.node = n; return { ok: true }; },
    set_mode: async (m) => { st.mode = m; return { ok: true }; },
    set_sys_proxy: async (v) => ({ ok: true }),
    set_tun: async (v) => ({ ok: true }),
    test_speed: async () => { st.task = { running: true, kind: 'speed', msg: '测速中…', progress: 40 }; return { ok: true }; },
    refresh: async () => { st.task = { running: true, kind: 'refresh', msg: '抓取订阅源…', progress: 20 }; return { ok: true }; },
    diagnose: async () => ({ items: [{ name: '内核进程', ok: true, msg: '演示' }] }),
    logs: async () => st.logs,
    win_min: async () => { }, win_max: async () => { }, win_close: async () => { },
    drag: async () => { }, resize_edge: async () => { },
    win_pos: async () => ({ ok: false }), win_move: async () => ({ ok: false }),
    node_page: async () => ({ ok: true, nodes: st.nodes || [] }),
    open_url: async () => { }, copy: async () => { },
    set_autostart: async () => ({ ok: true }), set_auto_connect: async () => ({ ok: true }),
    restart_core: async () => ({ ok: true }), live_logs: async () => st.logs,
    set_theme: async (t) => { st.theme = t; return { ok: true }; },
  };
}

function withTimeout(pr, ms, fallback) {
  return Promise.race([pr, new Promise((res) => setTimeout(() => res(fallback), ms))]);
}

async function boot() {
  try {
    // 首屏等后端太久＝白屏"卡死"，给超时兜底并重试
    const data = await withTimeout(API.bootstrap(), 8000, null);
    if (!data) {
      toast('后端响应较慢，正在重试…', 'err');
      setTimeout(boot, 1500);
      return;
    }
    STATE = data.state;
    NODES = data.nodes || [];
    const _kvHome = $('#kvHome');
    if (data.home && _kvHome) _kvHome.textContent = data.home;
    const _kvRepo = $('#kvRepo');
    if (data.state && data.state.repo && _kvRepo) _kvRepo.textContent = 'github.com/' + data.state.repo;
    paint();
    startPolling();
    // 告诉后端首屏已经出来了：自动连接/重活都排在这之后，避免开机抢资源把窗口卡住
    if (API && API.ready) { try { API.ready(); } catch (e) { /* ignore */ } }
    setTimeout(() => checkUpdate(true), 2500);
  } catch (e) {
    console.error(e);
    toast('初始化失败: ' + e, 'err');
  }
}

function startPolling() {
  if (timer) clearInterval(timer);
  timer = setInterval(tick, 1000);
}

async function tick() {
  // 窗口不可见时不拉状态，省下的开销还给界面
  if (document.hidden) return;
  try {
    const s = await API.state();
    if (!s) return;
    STATE = s;
    paint();
    // 测速要跑好几分钟。旧版只在全部结束时刷列表，中途用户一条“测好的线路”都看不到，
    // 也没法挑一条连。这里测速进行中每 4 秒轻量回刷一次（只取前 400 条），结果边测边冒出来。
    const sp = s.speed || {};
    if (sp.running && Date.now() - lastLiveReload > 4000) {
      lastLiveReload = Date.now();
      liveReloadNodes();
    }
  } catch (e) { /* ignore */ }
}

let lastLiveReload = 0;
let liveReloadBusy = false;
async function liveReloadNodes() {
  if (MOCK || liveReloadBusy) return;
  liveReloadBusy = true;
  try {
    // 只取前 240 条（后端已按延迟排序，测出来的线路就排在最前面），避免每次回刷把 2500 条 JSON 灌进 WebView
    const r = await API.node_page(0, 240);
    const list = (r && (r.nodes || (Array.isArray(r) ? r : null))) || null;
    if (list && list.length) {
      if (allNodesLoaded) {
        // 已经拉过全量列表时不能在测速中途被 240 条覆盖掉（否则搜索/翻页会丢节点），只把新测到的延迟合并进去
        const byName = {};
        list.forEach((n) => (byName[n.name] = n));
        NODES.forEach((n) => {
          const hit = byName[n.name];
          if (hit && hit.delay) n.delay = hit.delay;
        });
      } else {
        NODES = list;
      }
      renderNodeTable();
    }
  } catch (e) { /* ignore */ }
  liveReloadBusy = false;
}

/* ---------------------------------------------------------------- 渲染 */
function paint() {
  const s = STATE;
  if (!s) return;
  try { watchConnect(s); } catch (e) { /* ignore */ }
  try { watchTask(s); } catch (e) { /* ignore */ }

  $('#verText').textContent = s.version;
  $$('.ver-inline').forEach((e) => (e.textContent = s.version));

  // 顶栏
  const pill = $('#tbStatus');
  pill.classList.toggle('on', !!s.connected);
  $('#tbState').textContent = s.connected ? '已连接' : '未连接';
  $('#tbUp').textContent = fmtRate(s.up);
  $('#tbDown').textContent = fmtRate(s.down);

  // 首页连接区
  $('#connState').textContent = s.connected ? '已连接' : '未连接';
  $('#connState').classList.toggle('on', !!s.connected);
  $('#connTime').textContent = s.connected ? fmtDur(s.uptime) : '--:--:--';
  $('#connRing').classList.toggle('on', !!s.connected);
  $('#connBtnText').textContent = s.connected ? '断开连接' : '立即连接';
  $('#connHint').textContent = s.connected
    ? '连接已启动，现在可以切换到其他应用使用。'
    : '连接已关闭，点击圆形按钮开始加速。';
  $('#spdDown').textContent = fmtRate(s.down);
  $('#spdUp').textContent = fmtRate(s.up);

  // 账号区
  $('#accName').textContent = s.connected ? (s.node || '免费节点池') : '免费节点池';
  $('#accPlan').textContent = s.connected
    ? `QuChen · ${s.node_type ? s.node_type.toUpperCase() : '代理'} · ${s.node_country || '自动'}`
    : 'QuChen · 公开节点池无限流量';
  $('#statUsed').textContent = fmtSize((s.total_up || 0) + (s.total_down || 0));
  $('#statTotal').textContent = '无限';
  const pct = Math.min(100, (((s.total_up || 0) + (s.total_down || 0)) / (100 * 1024 ** 3)) * 100);
  $('#accBar').style.width = Math.max(pct, 1.5) + '%';
  $('#statPoolTime').textContent = s.pool_updated || '—';

  // 当前节点
  const cur = NODES.find((n) => n.name === (s.node || ''));
  $('#curFlag').innerHTML = flagSvg(cur ? cur.country : (s.node_country || '其他'));
  $('#curNode').textContent = s.node ? stripFlag(s.node) : '未选择节点';

  // 模式
  $$('#segMode .seg-item').forEach((b) => b.classList.toggle('active', b.dataset.mode === s.mode));
  $('#modeDesc').textContent = s.mode === 'global'
    ? '全局连接：所有流量都走代理，适合网页打不开时切换。'
    : '智能分流：国内直连、国外走代理，日常使用推荐。';
  $('#swSysProxy').checked = !!(s.sys_proxy_setting !== undefined ? s.sys_proxy_setting : s.sys_proxy);
  $('#swTun').checked = !!s.tun;

  // 节点池
  $('#poolFootText').textContent =
    `已加载 ${s.node_count} 条线路 · 更新于 ${s.pool_updated || '未知'}`;
  const _setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
  _setTxt('kvPort', s.mixed_port || '—');
  _setTxt('kvCtrl', s.ctrl_port || '—');
  _setTxt('kvAdmin', s.admin ? '已获得' : '未获得（TUN 需要）');
  _setTxt('kvVer', s.version || '—');
  const _sw = $('#swAutoStart'); if (_sw) _sw.checked = !!s.auto_start;
  $('#swAutoConnect').checked = !!s.auto_connect;

  // 任务条
  const t = s.task || {};
  const bar = $('#taskbar');
  if (t.running) {
    bar.classList.add('show');
    $('#taskText').textContent = t.msg || '正在处理…';
    $('#taskFill').style.width = (t.progress || 0) + '%';
  } else {
    bar.classList.remove('show');
  }

  paintUpdate(s.update || {});

  if (document.body.classList.contains('dark') !== (s.theme === 'dark')) {
    document.body.classList.toggle('dark', s.theme === 'dark');
  }

  // 日志页 / 抽屉延迟刷新
  if ($('#page-logs').classList.contains('active') && s.logs && s.logs.length !== lastLogLen) {
    lastLogLen = s.logs.length;
    $('#logBox').textContent = s.logs.join('\n');
    $('#logBox').scrollTop = $('#logBox').scrollHeight;
  }
  if (s.nodes_dirty) NODES = s.nodes_dirty;

  renderSources(s);
  renderTraffic(s);
}

function forceUpdateGate(u) {
  let el = document.getElementById('forceUpdate');
  if (!u || !u.has_update) { if (el) el.remove(); return; }
  if (!el) {
    el = document.createElement('div');
    el.id = 'forceUpdate';
    el.innerHTML = '<div class="fu-card"><h2>需要更新到 <span id="fuVer"></span></h2>' +
      '<p>这个版本已经停止支持。更新会保留你的线路与设置。</p>' +
      '<button id="fuGo" class="btn-blue">立即更新</button><p id="fuMsg" class="small"></p></div>';
    document.body.appendChild(el);
    document.getElementById('fuGo').onclick = async () => {
      const m = document.getElementById('fuMsg');
      m.textContent = '正在下载…';
      try {
        const d = await API.download_update();
        if (!d || !d.ok) { m.textContent = (d && d.msg) || '下载失败，请稍后再试。'; return; }
        m.textContent = '正在安装，程序会自动重启…';
        await API.install_update();
      } catch (e) { m.textContent = '更新失败：' + e; }
    };
  }
  document.getElementById('fuVer').textContent = u.latest || '';
}

function paintUpdate(u) {
  forceUpdateGate(u);
  if (!u) return;
  const _kvLatest = $('#kvLatest');
  if (u.latest && _kvLatest) _kvLatest.textContent = u.latest;
  const _msg = $('#kvUpdateMsg');
  if (_msg) {
    _msg.textContent = u.msg || '尚未检查';
    if (u.has_update) {
      _msg.style.color = 'var(--blue)';
      _msg.textContent = u.msg || ('发现新版本 ' + u.latest);
    } else {
      _msg.style.color = '';
    }
  }
  const _notes = $('#updateNotes');
  if (_notes) _notes.textContent = u.notes || '';
  const box = $('#updateBox');
  if (box) box.classList.toggle('show', !!(u.has_update || u.downloading || u.ready));
  const _fill = $('#updateFill');
  if (_fill) _fill.style.width = (u.progress || 0) + '%';
  const btn = $('#btnDoUpdate');
  if (btn) {
    if (u.ready) btn.textContent = '重启并安装';
    else if (u.downloading) btn.textContent = '下载中 ' + (u.progress || 0) + '%';
    else btn.textContent = '立即更新';
  }
  // 设置页入口红点
  if (navBtn) {
    let dot = navBtn.querySelector('.badge-dot');
    if (u.has_update && !dot) {
      dot = document.createElement('span');
      dot.className = 'badge-dot';
      navBtn.appendChild(dot);
    } else if (!u.has_update && dot) dot.remove();
  }
}

async function checkUpdate(silent) {
  try {
    const r = await API.check_update(true);
    paintUpdate(r);
    if (!silent) {
      toast(r.msg || '检查完成', r.has_update ? 'ok' : 'ok');
    } else if (r && r.has_update) {
      toast('发现新版本 ' + r.latest + '，可到「设置」页更新');
    }
  } catch (e) {
    if (!silent) toast('检查失败: ' + e, 'err');
  }
}

async function doUpdate() {
  const u = (STATE && STATE.update) || {};
  if (u.ready) {
    const r = await API.install_update();
    toast(r.ok ? '正在重启安装…' : (r.msg || '安装失败'), r.ok ? 'ok' : 'err');
    return;
  }
  const r = await API.download_update();
  if (!r.ok) return toast(r.msg || '下载失败', 'err');
  toast('开始下载更新包…');
}

function renderSources(s) {
  const src = s.sources || [];
  const ok = src.filter((x) => !x.err && x.nodes > 0);
  const total = src.reduce((a, x) => a + (x.nodes || 0), 0);
  $('#srcSummary').innerHTML = `
    <div class="sum-card"><div class="sum-label">订阅源</div><div class="sum-value blue">${ok.length} / ${src.length}</div></div>
    <div class="sum-card"><div class="sum-label">抓取节点</div><div class="sum-value">${total.toLocaleString()}</div></div>
    <div class="sum-card"><div class="sum-label">去重后</div><div class="sum-value">${(s.harvested || 0).toLocaleString()}</div></div>
    <div class="sum-card"><div class="sum-label">可用线路</div><div class="sum-value green">${s.node_count}</div></div>`;
  if (!src.length) {
    $('#srcList').innerHTML = '<div class="empty">还没有抓取记录，点击右上角“立即更新”开始抓取。</div>';
    return;
  }
  $('#srcList').innerHTML = src.map((x) => `
    <div class="src-row">
      <svg class="ic16 blue"><use href="#i-link"/></svg>
      <div><div class="src-name">${esc(x.name)}</div>
        <div class="src-url">${x.kind ? '格式 ' + esc(x.kind) : ''} ${x.bytes ? '· ' + fmtSize(x.bytes) : ''}</div></div>
      <div>${x.nodes ? x.nodes + ' 节点' : '—'}</div>
      <div>${x.ms ? x.ms + ' ms' : '—'}</div>
      <div>${x.err ? `<span class="badge bad">失败</span>` : `<span class="badge ok">正常</span>`}</div>
      <div></div>
    </div>`).join('');
}

function renderTraffic(s) {
  const up = s.total_up || 0;
  const down = s.total_down || 0;
  $('#trafficCards').innerHTML = `
    <div class="tr-card"><div class="tr-label"><svg class="ic13"><use href="#i-up"/></svg>本次上传</div><div class="tr-value up">${fmtSize(up)}</div></div>
    <div class="tr-card"><div class="tr-label"><svg class="ic13"><use href="#i-down"/></svg>本次下载</div><div class="tr-value down">${fmtSize(down)}</div></div>
    <div class="tr-card"><div class="tr-label"><svg class="ic13"><use href="#i-chart"/></svg>本次合计</div><div class="tr-value">${fmtSize(up + down)}</div></div>`;
  const days = (s.stats_days || []).slice().sort((a, b) => (a[0] < b[0] ? 1 : -1));
  if (!days.length) {
    $('#trafficList').innerHTML = '<div class="empty">暂无历史记录，连接后会自动统计。</div>';
    return;
  }
  const max = Math.max(...days.map((d) => (d[1].up || 0) + (d[1].down || 0)), 1);
  $('#trafficList').innerHTML = days.map(([date, d]) => {
    const tot = (d.up || 0) + (d.down || 0);
    return `<div class="tr-row">
      <div class="tr-date">${date}</div>
      <div>${fmtSize(tot)}</div>
      <div class="tr-bar"><i style="width:${Math.max(2, (tot / max) * 100)}%"></i></div>
      <div style="text-align:right;color:var(--text-3)">${fmtSize(d.up || 0)} ↑</div>
    </div>`;
  }).join('');
}

const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

/* ---------------------------------------------------------------- 节点表 */
function filteredNodes() {
  return NODES.filter((n) => {
    if (filterProto === 'secure' && (n.type === 'http' || n.type === 'socks5')) return false;
    if (filterProto === 'plain' && !(n.type === 'http' || n.type === 'socks5')) return false;
    if (filterProto === 'verified' && !n.delay) return false;
    if (filterCountry !== '全部' && n.country !== filterCountry) return false;
    if (searchText) {
      const q = searchText.toLowerCase();
      if (!(n.name + ' ' + n.type + ' ' + n.server + ' ' + n.country).toLowerCase().includes(q)) return false;
    }
    return true;
  });
}

function renderNodeTable() {
  const countries = {};
  NODES.forEach((n) => (countries[n.country] = (countries[n.country] || 0) + 1));
  const top = Object.entries(countries).sort((a, b) => b[1] - a[1]);
  const protoChips = [['all', '全部'], ['secure', '加密线路'], ['plain', '公共代理'], ['verified', '已测速']]
    .map(([k, label]) => `<button class="chip pchip ${filterProto === k ? 'active' : ''}" data-proto="${k}">${label}</button>`).join('');
  const chips = [['全部', NODES.length]].concat(top.slice(0, 12));
  $('#countryChips').innerHTML = protoChips +
    `<span style="width:1px;background:var(--line-2);margin:0 4px"></span>` +
    chips.map(([c, n]) =>
      `<button class="chip ${c === filterCountry ? 'active' : ''}" data-country="${esc(c)}">${esc(c)} ${n}</button>`).join('');

  const rows = filteredNodes();
  const shown = rows.slice(0, nodeLimit);
  const rest = rows.length - shown.length;
  const cur = STATE ? STATE.node : '';
  $('#nodeTable').innerHTML = `
    <div class="trow head"><div></div><div>节点（共 ${rows.length} 条${rest > 0 ? `，已显示 ${shown.length}` : ''}）</div><div>协议</div><div>延迟</div><div>操作</div></div>` +
    (shown.length ? shown.map((n) => `
      <div class="trow">
        <div class="tflag">${flagSvg(n.country)}</div>
        <div class="tname" title="${esc(n.server)}:${n.port}">${esc(stripFlag(n.name))}</div>
        <div><span class="ttag">${esc(n.type)}</span></div>
        <div class="tdelay ${delayClass(n.delay)}">${delayText(n.delay)}</div>
        <div>${n.name === cur
          ? '<button class="pick used">使用中</button>'
          : `<button class="pick" data-use="${esc(n.name)}">使用</button>`}</div>
      </div>`).join('')
      : '<div class="empty">没有匹配的节点</div>') +
    (rest > 0 ? `<div style="display:flex;gap:8px;justify-content:center;padding:12px 0">
        <button class="pick" data-more="120">再显示 120 条（还剩 ${rest}）</button>
        <button class="pick" data-more="all">显示全部 ${rows.length} 条</button>
      </div>` : '');
}

/* ---------------------------------------------------------------- 抽屉 */
function drawerNodes() {
  let list = NODES;
  if (drawerSearch) {
    const q = drawerSearch.toLowerCase();
    list = list.filter((n) => (n.name + n.type + n.server).toLowerCase().includes(q));
  }
  return list;
}

function renderDrawer() {
  const cur = STATE ? STATE.node : '';
  $('#dcName').textContent = drawerTab === 'auto'
    ? '自动选择 · 按延迟自动切换'
    : drawerTab === 'fallback'
      ? '故障转移 · 主线路失败自动换'
      : (cur || '未选择');
  $$('#drawerTabs .dtab').forEach((b) => b.classList.toggle('active', b.dataset.tab === drawerTab));
  const list = drawerNodes();
  const shownList = list.slice(0, drawerLimit);
  const rest = list.length - shownList.length;
  const html = shownList.map((n) => `
    <button class="dnode ${(pendingNode || cur) === n.name ? 'on' : ''}" data-node="${esc(n.name)}">
      <span class="radio"></span>
      ${flagSvg(n.country, 'flag dflag')}
      <span class="dnode-name">${esc(stripFlag(n.name))}</span>
      <span class="dnode-type">${esc(n.type)}</span>
      <span class="dnode-delay ${delayClass(n.delay)}">${delayText(n.delay)}</span>
    </button>`).join('');
  $('#drawerList').innerHTML = html
    ? html + (rest > 0
      ? `<button class="dnode" data-dmore="300" style="justify-content:center;color:var(--blue)">
           加载更多（还剩 ${rest} 条，共 ${list.length} 条）</button>`
      : '')
    : '<div class="empty">没有匹配节点</div>';
}

function openDrawer() {
  pendingNode = STATE ? STATE.node : null;
  drawerLimit = 200;
  drawerSearch = '';
  const srch = $('#drawerSearch'); if (srch) srch.value = '';
  renderDrawer();
  $('#drawer').classList.add('show');
  $('#drawerMask').classList.add('show');
}
function closeDrawer() {
  $('#drawer').classList.remove('show');
  $('#drawerMask').classList.remove('show');
}

/* ---------------------------------------------------------------- 动作 */
let prevConnected = null;
let prevTask = null;

let prevSpeedSeq = null;
let prevSpeedRunning = false;

/** 测速结束后自动把结果刷进列表。
 *  注意：测速状态用 state.speed 判断，不能用 state.task —— 测速期间用户点连接会把 task
 *  改成 connect，只盯 task 就永远等不到“测速结束”，于是“测好了也看不到已测速线路”。*/
async function watchTask(painted) {
  const t = (painted && painted.task) || {};
  const sp = (painted && painted.speed) || {};
  if (sp.seq !== undefined) {
    const running = !!sp.running;
    if (prevSpeedSeq === null) {
      prevSpeedSeq = sp.seq; prevSpeedRunning = running;
    } else if (sp.seq !== prevSpeedSeq || (prevSpeedRunning && !running)) {
      prevSpeedSeq = sp.seq; prevSpeedRunning = running;
      allNodesLoaded = false;
      await loadAllNodes(true);
      renderNodeTable(); renderDrawer();
      toast(sp.msg || '测速完成', sp.ok_count ? 'ok' : '');
      return;
    } else {
      prevSpeedRunning = running;
    }
  }
  const snapshot = `${t.kind || ''}:${t.running ? 1 : 0}`;
  if (prevTask === null) { prevTask = snapshot; return; }
  if (prevTask === snapshot) return;
  const wasRunning = prevTask && prevTask.endsWith(':1');
  prevTask = snapshot;
  if (!wasRunning || t.running) return;
  if (t.kind === 'refresh') {
    allNodesLoaded = false;
    await loadAllNodes(true);
    renderNodeTable(); renderDrawer();
  }
}

let allNodesLoaded = false;
/** 首屏只拿到前 240 条节点，节点页/搜索需要全量时再一次性拉过来。*/
async function loadAllNodes(force) {
  if (MOCK) return;
  if (allNodesLoaded && !force) return;
  try {
    const r = await API.node_page(0, 0);
    if (r && r.ok && r.nodes && r.nodes.length) {
      NODES = r.nodes;
      allNodesLoaded = true;
      renderNodeTable();
    }
  } catch (e) { /* ignore */ }
}

function watchConnect(painted) {
  const now = !!(painted && painted.connected);
  if (prevConnected === null) { prevConnected = now; return; }
  if (now === prevConnected) return;
  prevConnected = now;
  if (now) {
    if (painted.sys_proxy_setting && !painted.sys_proxy) toast('已连接，但系统代理未接管，请到设置检查', 'err');
    else toast('连接成功');
  } else {
    toast('已断开连接');
  }
}

async function doToggle() {
  if (MOCK) { toast(STATE.connected ? '已断开' : '已连接'); STATE.connected = !STATE.connected; paint(); return; }
  const t = (STATE && STATE.task) || {};
  // 测速/换线都是后台任务，不该拦住连接：旧代码一律拦下，用户看着进度条却点不动连接
  if (t.running && t.kind !== 'speed' && t.kind !== 'switch') { toast('任务进行中，请稍候', 'err'); return; }
  const wasConnected = !!(STATE && STATE.connected);
  const btn = $('#btnConnect');
  // 连接要跑内核启动 + 出口校验，动辄十几秒。旧代码整段时间把按钮 busy（CSS 里 pointer-events:none），
  // 用户点了没反应又点不动，只能干等。这里只在“断开”时短暂上锁，连接全程保持可点。
  if (wasConnected) {
    btn.classList.add('busy');
    $('#connBtnText').textContent = '正在断开…';
  } else {
    $('#connBtnText').textContent = '正在连接…';
  }
  try {
    const r = wasConnected ? await API.disconnect() : await API.connect();
    if (!r.ok) toast(r.msg || '操作失败', 'err');
    else if (r.pending) toast(r.msg || (wasConnected ? '正在断开…' : '正在连接，请稍候…'));
    else if (wasConnected) toast('已断开连接');
    else if (r.sys_proxy === false && STATE && STATE.sys_proxy_setting) toast('已连接，但系统代理未接管，请到设置检查', 'err');
    else toast(r.msg || '连接成功');
    const s = await API.state();
    STATE = s; paint();
  } catch (e) { toast('操作失败: ' + e, 'err'); }
  btn.classList.remove('busy');
}

async function selectNode(name) {
  try {
    const r = await API.select_node(name);
    if (r && r.ok) {
      toast(r.msg || '已切换线路');
      // 后端改成异步：切换/出口校验在后台跑，进度靠轮询刷新
      if (!r.pending) { STATE = await API.state(); paint(); }
    } else toast((r && r.msg) || '切换失败', 'err');
  } catch (e) { toast('切换失败: ' + e, 'err'); }
}

async function refreshPool() {
  try {
    const r = await API.refresh();
    if (!r.ok) return toast(r.msg || '任务进行中', 'err');
    toast('开始抓取并测速，预计 1-3 分钟');
  } catch (e) { toast('启动失败: ' + e, 'err'); }
}

async function testAll() {
  try {
    const r = await API.test_speed();
    if (!r.ok) return toast(r.msg || '任务进行中', 'err');
    toast('开始测速，结果会自动刷新到列表…');
    // 不再 1.2s 后抢跑拉一次：那时测速还没结束，拉到的是没延迟的空数据。
    // 测速结束由 watchTask 统一刷新。
  } catch (e) { toast('启动失败: ' + e, 'err'); }
}

async function runDiag() {
  $('#diagList').innerHTML = '<div class="empty">诊断中…</div>';
  try {
    const r = await API.diagnose();
    $('#diagList').innerHTML = (r.items || []).map((i) => `
      <div class="diag-row">
        <div class="diag-ico ${i.ok ? 'ok' : 'bad'}">${i.ok ? '✓' : '!'}</div>
        <div class="diag-name">${esc(i.name)}</div>
        <div class="diag-msg">${esc(i.msg)}</div>
      </div>`).join('');
  } catch (e) { $('#diagList').innerHTML = `<div class="empty">诊断失败: ${esc(e)}</div>`; }
}

/* ---------------------------------------------------------------- 事件 */
function bindEvents() {
  // 页面切换
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-page]');
    if (!btn) return;
    const page = btn.dataset.page;
    const node = btn.closest('.nav-item');
    if (node) { $$('.nav-item').forEach((b) => b.classList.remove('active')); node.classList.add('active'); }
    $$('.page').forEach((p) => p.classList.remove('active'));
    const el = $('#page-' + page);
    if (el) el.classList.add('active');
    if (page === 'nodes') { loadAllNodes(); renderNodeTable(); }
    if (page === 'logs') {
      $('#logBox').textContent = (STATE && STATE.logs || []).join('\n');
    }
  });

  // 窗口控制
  $('#btnMin').onclick = () => API && API.win_min();
  $('#btnMax').onclick = () => API && API.win_max();
  $('#btnClose').onclick = () => API && API.win_close();
  // 窗口拖动：只用「自定义拖动」这一条通道（记录屏幕坐标 + SetWindowPos 跟随）。
  // 旧版先试 Win32 的 ReleaseCapture+SendMessage(WM_NCLBUTTONDOWN)，那玩意儿一旦接管鼠标捕获，
  // mousemove/mouseup/click 全都不再派发给页面：表现就是“窗口拖不动、右上角按钮点了没反应”。
  // 单通道反而稳：未越过 4px 阈值时完全不动鼠标，单击照常派发。
  let dragState = null;
  let dragSeq = 0;
  $('#titlebar').addEventListener('mousedown', async (e) => {
    if (e.target.closest('button, a, input')) return;
    if (typeof e.button === 'number' && e.button !== 0) return;
    if (!API) return;
    const seq = ++dragSeq;
    const st = { sx: e.screenX, sy: e.screenY, moved: false, wx: 0, wy: 0, tx: 0, ty: 0, t: 0 };
    dragState = st;
    try {
      const pos = await API.win_pos();
      // 期间用户可能已松手或又按下一次，别把旧坐标写进新状态
      if (pos && pos.ok && dragState === st && seq === dragSeq) {
        st.wx = pos.x; st.wy = pos.y; st.tx = pos.x; st.ty = pos.y;
        st.scale = pos.scale || 1;
        st.ready = true;
      } else if (dragState === st) {
        // 拿不到窗口坐标就别拖：否则 tx/ty 从 0 起算，窗口会直接跳到屏幕左上角
        dragState = null;
      }
    } catch (err) {
      if (dragState === st) dragState = null;
    }
  });
  window.addEventListener('mousemove', (e) => {
    if (!dragState || !dragState.ready) return;
    const dx = e.screenX - dragState.sx;
    const dy = e.screenY - dragState.sy;
    if (!dragState.moved) {
      if (Math.abs(dx) + Math.abs(dy) < 4) return;   // 阈值内还算单击
      dragState.moved = true;
    }
    const now = Date.now();
    if (dragState.t && now - dragState.t < 8) return;   // 节流，避免 IPC 打满
    dragState.t = now;
    const sc = dragState.scale || 1;   // CSS px → 物理 px
    dragState.tx = dragState.wx + dx * sc;
    dragState.ty = dragState.wy + dy * sc;
    try { API.win_move(dragState.tx, dragState.ty); } catch (err) { /* ignore */ }
  });
  const endDrag = () => { dragState = null; };
  window.addEventListener('mouseup', endDrag);
  window.addEventListener('blur', endDrag);
  $('#titlebar').addEventListener('dblclick', (e) => {
    if (e.target.closest('button, a, input')) return;
    if (API) API.win_max();
  });

  // 主题
  $('#btnTheme').onclick = async () => {
    const dark = !document.body.classList.contains('dark');
    document.body.classList.toggle('dark', dark);
    if (!MOCK && API) await API.set_theme(dark ? 'dark' : 'light');
  };

  // 连接
  $('#btnConnect').onclick = doToggle;
  $('#segMode').onclick = async (e) => {
    const b = e.target.closest('.seg-item');
    if (!b) return;
    await API.set_mode(b.dataset.mode);
    STATE.mode = b.dataset.mode;
    paint();
  };
  $('#swSysProxy').onchange = async (e) => { await API.set_sys_proxy(e.target.checked); toast(e.target.checked ? '已开启系统代理' : '已关闭系统代理'); };
  $('#swTun').onchange = async (e) => {
    const r = await API.set_tun(e.target.checked);
    if (e.target.checked) toast('TUN 需要管理员权限，重连后生效');
  };

  // 节点
  $('#btnPickNode').onclick = openDrawer;
  $('#drawerClose').onclick = closeDrawer;
  $('#drawerMask').onclick = closeDrawer;
  $('#drawerSearch').oninput = (e) => { drawerSearch = e.target.value.trim(); drawerLimit = 200; renderDrawer(); };
  $$('#drawerTabs .dtab').forEach((b) => {
    b.onclick = async () => {
      drawerTab = b.dataset.tab;
      drawerLimit = 200;
      renderDrawer();
      if (drawerTab === 'all') return;
      const target = drawerTab === 'auto' ? G_AUTO : G_FALLBACK;
      const r = await API.set_group(G_SELECT, target);
      if (r && r.ok) toast(drawerTab === 'auto' ? '已切换为自动选择' : '已切换为故障转移');
      else toast(r && r.msg ? r.msg : '切换失败，请先连接', 'err');
    };
  });
  $('#drawerList').onclick = (e) => {
    const more = e.target.closest('[data-dmore]');
    if (more) {
      drawerLimit += Number(more.dataset.dmore || 300);
      renderDrawer();
      return;
    }
    const b = e.target.closest('.dnode');
    if (!b) return;
    pendingNode = b.dataset.node;
    renderDrawer();
  };
  $('#drawerDone').onclick = async () => {
    if (pendingNode) await selectNode(pendingNode);
    closeDrawer();
  };
  $('#drawerTest').onclick = testAll;
  $('#drawerRefresh').onclick = refreshPool;

  $('#nodeSearch').oninput = (e) => { searchText = e.target.value.trim(); nodeLimit = 120; loadAllNodes(); renderNodeTable(); };
  $('#countryChips').onclick = (e) => {
    const c = e.target.closest('.chip');
    if (!c) return;
    if (c.dataset.proto) filterProto = c.dataset.proto;
    else filterCountry = c.dataset.country;
    nodeLimit = 120;
    renderNodeTable();
  };
  $('#nodeTable').onclick = (e) => {
    const more = e.target.closest('[data-more]');
    if (more) {
      nodeLimit = more.dataset.more === 'all'
        ? filteredNodes().length
        : nodeLimit + Number(more.dataset.more || 120);
      renderNodeTable();
      return;
    }
    const b = e.target.closest('[data-use]');
    if (b) selectNode(b.dataset.use);
  };
  $('#btnTestAll').onclick = testAll;
  $('#btnRefreshPool2').onclick = refreshPool;
  $('#btnRefreshPool3').onclick = refreshPool;
  $('#btnRefreshPool').onclick = refreshPool;
  $('#btnRenew').onclick = refreshPool;
  $('#btnNoticeRefresh').onclick = refreshPool;
  $('#btnNoticeDownload').onclick = () => $('[data-page="nodes"]').click();
  $('#btnNoticeReload').onclick = () => { tick(); toast('状态已刷新'); };
  $('#btnDiag').onclick = () => { $('[data-page="diag"]').click(); runDiag(); };
  $('#btnRunDiag').onclick = runDiag;
  $('#btnRestartCore').onclick = async () => {
    const r = await API.restart_core();
    toast(r.ok ? '内核已重置' : (r.msg || '重置失败'), r.ok ? 'ok' : 'err');
  };
  $('#btnClearLogs').onclick = () => { $('#logBox').textContent = ''; };
  $('#btnCopyDomain').onclick = async () => {
    const el = $('#kvHome');
    await API.copy(el ? el.textContent : '');
    toast('已复制数据目录');
  };
  const _btnCopyHome = $('#btnCopyHome');
  if (_btnCopyHome) _btnCopyHome.onclick = async () => {
    const el = $('#kvHome');
    await API.copy(el ? el.textContent : '');
    toast('已复制数据目录');
  };
  $('#btnAbout').onclick = () => $('[data-page="about"]').click();
  $('#btnHelpHome').onclick = () => $('[data-page="diag"]').click();
  const _sw2 = $('#swAutoStart'); if (_sw2) _sw2.onchange = async (e) => { await API.set_autostart(e.target.checked); toast(e.target.checked ? '已设置开机自启' : '已取消开机自启'); };
  $('#swAutoConnect').onchange = async (e) => { await API.set_auto_connect(e.target.checked); toast('设置已保存'); };
  const _btnCheckUpdate = $('#btnCheckUpdate');
  if (_btnCheckUpdate) _btnCheckUpdate.onclick = () => checkUpdate(false);
  const _btnDoUpdate = $('#btnDoUpdate');
  if (_btnDoUpdate) _btnDoUpdate.onclick = doUpdate;
  const _btnSaveToken = $('#btnSaveToken');
  if (_btnSaveToken) _btnSaveToken.onclick = async () => {
    const inp = $('#inpToken');
    const r = await API.set_update_token((inp && inp.value) || '');
    toast(r && r.ok ? (r.msg || '已保存') : ((r && r.msg) || '保存失败'), r && r.ok ? 'ok' : 'err');
    if (inp) inp.value = '';
    API.check_update(true).then(paintUpdate).catch(() => {});
  };
  $('#btnReloadTraffic').onclick = () => tick();
  document.addEventListener('click', (e) => {
    const b = e.target.closest('[data-open]');
    if (b) API.open_url(b.dataset.open);
  });

  // 快捷键
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); doToggle(); }
    if (e.ctrlKey && (e.key === 'l' || e.key === 'L')) { e.preventDefault(); openDrawer(); }
    if (e.ctrlKey && (e.key === 'r' || e.key === 'R')) { e.preventDefault(); refreshPool(); }
    if (e.key === 'Escape') closeDrawer();
  });

  // 窗口缩放手柄
  const edges = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'];
  edges.forEach((dir) => {
    const el = document.createElement('div');
    el.className = 'rs rs-' + dir;
    el.addEventListener('mousedown', (ev) => { ev.preventDefault(); API && API.resize_edge(dir); });
    document.body.appendChild(el);
  });
}

/* ---------------------------------------------------------------- 启动 */
(function init() {
  const style = document.createElement('style');
  style.textContent = `
    .rs{position:fixed;z-index:70}
    .rs-n{top:0;left:6px;right:6px;height:5px;cursor:ns-resize}
    .rs-s{bottom:0;left:6px;right:6px;height:5px;cursor:ns-resize}
    .rs-e{top:6px;bottom:6px;right:0;width:5px;cursor:ew-resize}
    .rs-w{top:6px;bottom:6px;left:0;width:5px;cursor:ew-resize}
    .rs-ne{top:0;right:0;width:10px;height:10px;cursor:nesw-resize}
    .rs-nw{top:0;left:0;width:10px;height:10px;cursor:nwse-resize}
    .rs-se{bottom:0;right:0;width:10px;height:10px;cursor:nwse-resize}
    .rs-sw{bottom:0;left:0;width:10px;height:10px;cursor:nesw-resize}
  `;
  document.head.appendChild(style);
  bindEvents();
  // 若 5 秒内 pywebview 未就绪，进入浏览器预览模式
  // Only a real browser preview may fall back to demo data; the desktop app must keep waiting for the bridge.
  const inBrowser = /^https?:$/.test(location.protocol);
  setTimeout(() => { if (!_booted && inBrowser) { API = mockApi(); boot(); } else if (!_booted) { bridgeReady(); } }, 5000);
})();

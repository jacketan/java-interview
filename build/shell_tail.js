let mermaidReady = false;
function initMermaid() {
  const dark = document.documentElement.dataset.theme === 'dark';
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: 'loose',
    theme: dark ? 'dark' : 'default',
    fontFamily: '-apple-system,"PingFang SC","Microsoft YaHei",sans-serif',
    flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' },
    sequence: { useMaxWidth: true, wrap: true, width: 190 },
    gantt: { useMaxWidth: true }
  });
  mermaidReady = true;
}
async function renderDiagrams(scope) {
  if (!mermaidReady) initMermaid();
  const nodes = [...scope.querySelectorAll('pre.mermaid:not([data-processed])')];
  for (const n of nodes) {
    if (!n.dataset.src) n.dataset.src = n.textContent;
    try {
      await mermaid.run({ nodes: [n], suppressErrors: true });
      if (!n.querySelector('svg')) throw new Error('渲染未产生图形');
    } catch (e) {
      const box = n.closest('.diagram') || n;
      box.classList.add('diagram-error');
      box.innerHTML = '⚠ 该图渲染失败：' + esc(String(e.message || e)) + '\n\n' + esc(n.dataset.src);
    }
  }
}
function resetDiagrams(scope) {
  scope.querySelectorAll('pre.mermaid').forEach(n => {
    if (n.dataset.src) n.textContent = n.dataset.src;
    n.removeAttribute('data-processed');
  });
}

/* ---------- 章节切换 ---------- */
let current = null;
function show(id, push) {
  const c = byId.get(id) || CHAPTERS[0];
  if (current === c.id) { window.scrollTo({ top: 0 }); return; }
  document.querySelectorAll('.chapter.active').forEach(s => s.classList.remove('active'));
  const sec = document.getElementById(c.id);
  sec.classList.add('active');
  current = c.id;
  document.querySelectorAll('.nav a.item').forEach(a => a.classList.toggle('active', a.dataset.ch === c.id));
  document.getElementById('crumb').textContent = c.group + ' / ' + c.title;
  document.getElementById('results').classList.remove('on');
  content.style.display = '';
  window.scrollTo({ top: 0 });
  if (push !== false && location.hash !== '#' + c.id) history.replaceState(null, '', '#' + c.id);
  try { localStorage.setItem('jikb.last', c.id); } catch (e) {}
  renderDiagrams(sec);
  const active = nav.querySelector('a.item.active');
  if (active) active.scrollIntoView({ block: 'nearest' });
}
document.addEventListener('click', e => {
  const a = e.target.closest('a[data-ch]');
  if (a) { e.preventDefault(); show(a.dataset.ch); }
});
document.getElementById('prevTop').onclick = () => step(-1);
document.getElementById('nextTop').onclick = () => step(1);
function step(d) {
  const i = CHAPTERS.findIndex(c => c.id === current);
  const t = CHAPTERS[i + d];
  if (t) show(t.id);
}

/* ---------- 主题 ---------- */
const themeBtn = document.getElementById('themeBtn');
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  themeBtn.textContent = t === 'dark' ? '浅色' : '深色';
  try { localStorage.setItem('jikb.theme', t); } catch (e) {}
  if (mermaidReady) {
    const secs = [...document.querySelectorAll('.chapter')];
    secs.forEach(resetDiagrams);
    mermaidReady = false;
    initMermaid();
    const sec = document.getElementById(current);
    if (sec) renderDiagrams(sec);
  }
}
themeBtn.onclick = () => setTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

/* ---------- 放大看图 ---------- */
const zoom = document.getElementById('zoom');
const zoomInner = document.getElementById('zoomInner');
document.addEventListener('click', e => {
  const dg = e.target.closest('.diagram');
  if (!dg || dg.classList.contains('diagram-error')) return;
  const svg = dg.querySelector('svg');
  if (!svg) return;
  zoomInner.innerHTML = '';
  zoomInner.appendChild(svg.cloneNode(true));
  zoom.classList.add('on');
});
zoom.onclick = () => zoom.classList.remove('on');
document.addEventListener('keydown', e => { if (e.key === 'Escape') zoom.classList.remove('on'); });

/* ---------- 搜索 ---------- */
const search = document.getElementById('search');
const results = document.getElementById('results');
let textCache = new Map();
function textOf(c) {
  if (!textCache.has(c.id)) {
    const sec = document.getElementById(c.id);
    textCache.set(c.id, sec.textContent.replace(/\s+/g, ' '));
  }
  return textCache.get(c.id);
}
function fullTextSearch(q) {
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return [];
  const hits = [];
  for (const c of CHAPTERS) {
    const text = textOf(c);
    const low = text.toLowerCase();
    if (!terms.every(t => low.includes(t))) continue;
    const first = low.indexOf(terms[0]);
    const start = Math.max(0, first - 70);
    let snip = text.slice(start, start + 230);
    terms.forEach(t => {
      snip = snip.replace(new RegExp('(' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'gi'), '<mark>$1</mark>');
    });
    hits.push({ c, snip: (start > 0 ? '…' : '') + snip + '…' });
    if (hits.length >= 60) break;
  }
  return hits;
}
function runSearch() {
  const q = search.value.trim();
  if (!q) { results.classList.remove('on'); content.style.display = ''; return; }
  const hits = fullTextSearch(q);
  results.innerHTML = '<h2>全文检索：' + esc(q) + '（' + hits.length + ' 章命中）</h2>' +
    (hits.length ? hits.map(h =>
      '<div class="hit" data-ch="' + h.c.id + '"><div class="t">' + esc(h.c.title) +
      '</div><div class="p">' + esc(h.c.group) + '</div><div class="s">' + h.snip + '</div></div>').join('')
      : '<div class="empty">没有匹配内容，换个关键词试试。</div>');
  results.classList.add('on');
  content.style.display = 'none';
  window.scrollTo({ top: 0 });
  results.querySelectorAll('.hit').forEach(el => el.onclick = () => {
    search.value = '';
    filterNav('');
    results.classList.remove('on');
    show(el.dataset.ch);
  });
}
function filterNav(q) {
  const k = q.trim().toLowerCase();
  nav.querySelectorAll('a.item').forEach(a => {
    const t = byId.get(a.dataset.ch).title.toLowerCase();
    a.classList.toggle('hidden', !!k && !t.includes(k));
  });
  nav.querySelectorAll('.group').forEach(g => {
    let n = g.nextElementSibling, any = false;
    while (n && n.classList.contains('item')) { if (!n.classList.contains('hidden')) any = true; n = n.nextElementSibling; }
    g.style.display = any ? '' : 'none';
  });
}
search.addEventListener('input', () => { filterNav(search.value); if (!search.value.trim()) { results.classList.remove('on'); content.style.display = ''; } });
search.addEventListener('keydown', e => {
  if (e.key === 'Enter') runSearch();
  if (e.key === 'Escape') { search.value = ''; filterNav(''); results.classList.remove('on'); content.style.display = ''; }
});
document.addEventListener('keydown', e => {
  if (e.key === '/' && document.activeElement !== search) { e.preventDefault(); search.focus(); }
});
document.getElementById('menuBtn').onclick = () => document.getElementById('sidebar').classList.toggle('open');
document.getElementById('printBtn').onclick = async () => {
  const btn = document.getElementById('printBtn');
  const old = btn.textContent;
  btn.textContent = '渲染中…';
  const sec = document.getElementById(current);
  resetDiagrams(sec);
  await renderDiagrams(sec);
  btn.textContent = old;
  window.print();
};

/* ---------- 进度条 ---------- */
addEventListener('scroll', () => {
  const h = document.documentElement.scrollHeight - innerHeight;
  document.getElementById('progress').style.width = (h > 0 ? (scrollY / h) * 100 : 0) + '%';
}, { passive: true });

/* ---------- 启动 ---------- */
// location.hash 对非 ASCII 字符会做百分号编码，必须先解码再查表
function hashId() {
  try { return decodeURIComponent(location.hash.slice(1) || ''); } catch (e) { return ''; }
}
addEventListener('hashchange', () => show(hashId() || CHAPTERS[0].id));
let last = null;
try {
  const t = localStorage.getItem('jikb.theme');
  if (t) setTheme(t);
  last = localStorage.getItem('jikb.last');
} catch (e) {}
show(hashId() || last || CHAPTERS[0].id, false);
</script>
</body>
</html>

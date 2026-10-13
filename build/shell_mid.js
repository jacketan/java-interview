const byId = new Map(CHAPTERS.map(c => [c.id, c]));
const esc = s => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

/* ---------- 渲染正文 ---------- */
const content = document.getElementById('content');
const frag = document.createDocumentFragment();
CHAPTERS.forEach((c, i) => {
  const sec = document.createElement('section');
  sec.className = 'chapter';
  sec.id = c.id;
  sec.dataset.index = i;
  sec.innerHTML = c.html;
  const nav = document.createElement('div');
  nav.className = 'chapter-nav';
  const prev = CHAPTERS[i-1], next = CHAPTERS[i+1];
  nav.innerHTML = (prev ? '<a href="#'+prev.id+'" data-ch="'+prev.id+'">← '+esc(prev.title)+'</a>' : '<span></span>') +
                  (next ? '<a href="#'+next.id+'" data-ch="'+next.id+'">'+esc(next.title)+' →</a>' : '<span></span>');
  sec.appendChild(nav);
  frag.appendChild(sec);
});
content.appendChild(frag);

/* ---------- 侧栏导航 ---------- */
const nav = document.getElementById('nav');
let lastGroup = null;
CHAPTERS.forEach(c => {
  if (c.group !== lastGroup) {
    lastGroup = c.group;
    const g = document.createElement('div');
    g.className = 'group';
    g.textContent = c.group;
    nav.appendChild(g);
  }
  const a = document.createElement('a');
  a.className = 'item';
  a.href = '#' + c.id;
  a.dataset.ch = c.id;
  const stars = (c.subtitle.match(/★+☆*/) || [''])[0];
  a.innerHTML = esc(c.title) + (stars ? '<span class="stars">' + stars + ' · ' + c.diagrams + ' 图</span>' : '');
  nav.appendChild(a);
});

/* ---------- Mermaid ---------- */

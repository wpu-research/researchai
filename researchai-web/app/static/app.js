// ResearchAI arayüzü — derleme adımı yok, tek modül.
const $app = document.getElementById('app');
const S = { meta: null, project: null, stage: 1, srcFilter: 'selected', poll: null, panelSig: '', disclosureLang: 'tr' };

const STAGE = {
  1: { c: 'var(--s1)', what: 'Ham fikir netleşir: araştırma sorusu, kapsam, arama sorguları ve ölçütler yazılır.', tools: 'Kapsam kartı · arama sorguları' },
  2: { c: 'var(--s2)', what: 'OpenAlex, Crossref, Semantic Scholar, arXiv, TR Dizin ve DergiPark taranır; adaylar ilgiye göre elenir.', tools: '6 kaynak · tekilleştirme · LLM eleme' },
  3: { c: 'var(--s3)', what: 'Seçili kaynaklardan not çıkarılır; temalar, kimsenin sınamadığı boşluklar ve hipotezler kurulur.', tools: 'Not çıkarma · boşluk haritası' },
  4: { c: 'var(--s4)', what: 'Yöntem ve veri planı yazılır. Sonuçları siz girersiniz: sistem veri uydurmaz, deney kodu çalıştırmaz.', tools: 'Yöntem planı · TR veri kaynakları' },
  5: { c: 'var(--s5)', what: 'Kanıta bağlı taslak: her olgusal cümle seçili bir kaynağa bağlanır ve kaynağın özetiyle denetlenir.', tools: 'Bölüm bölüm yazım · iddia-kaynak denetimi' },
  6: { c: 'var(--s6)', what: 'Metodoloji şeması ve (veri girdiyseniz) sonuç grafikleri üretilir; şema kodu düzenlenebilir.', tools: 'Mermaid · Chart.js' },
  7: { c: 'var(--s7)', what: 'Atıflar bağımsız kaynaklarda doğrulanır, yerel benzerlik taranır, iki farklı modelle kör hakem simülasyonu yapılır.', tools: 'verify_citation · benzerlik · 2 hakem' },
  8: { c: 'var(--s8)', what: 'Başlık, öz ve anahtar kelimeler hazırlanır; Markdown, LaTeX, BibTeX ve YZ kullanım beyanı indirilir.', tools: 'Dışa aktarım · beyan' },
};

// ---------------------------------------------------------------- yardımcılar
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const lines = (a) => (Array.isArray(a) ? a.join('\n') : a || '');
const unlines = (s) => s.split('\n').map((x) => x.trim()).filter(Boolean);
const fmtDate = (t) => (t ? new Date(t * 1000).toLocaleString('tr-TR', { dateStyle: 'medium', timeStyle: 'short' }) : '');
const ul = (a) => (a && a.length ? `<ul class="list-plain">${a.map((x) => `<li>${esc(typeof x === 'string' ? x : JSON.stringify(x))}</li>`).join('')}</ul>` : '<span class="muted">—</span>');

async function api(method, path, body) {
  const r = await fetch(path, { method, headers: body ? { 'content-type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((x) => x.msg).join('; ') : d || `HTTP ${r.status}`);
  }
  return data;
}

let toastT;
function toast(msg, bad = false) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast show${bad ? ' bad' : ''}`;
  clearTimeout(toastT);
  toastT = setTimeout(() => (t.className = 'toast'), bad ? 5200 : 2600);
}

async function act(fn, okMsg) {
  try {
    const r = await fn();
    if (okMsg) toast(okMsg);
    return r;
  } catch (e) {
    toast(e.message, true);
    return null;
  }
}

// ---------------------------------------------------------------- tema
(function theme() {
  const saved = (() => { try { return localStorage.getItem('theme'); } catch { return null; } })();
  if (saved) document.documentElement.dataset.theme = saved;
  document.getElementById('theme-btn').onclick = () => {
    const dark = document.documentElement.dataset.theme
      ? document.documentElement.dataset.theme === 'dark'
      : matchMedia('(prefers-color-scheme: dark)').matches;
    const next = dark ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('theme', next); } catch {}
  };
})();

// ---------------------------------------------------------------- yönlendirme
window.addEventListener('hashchange', route);
async function route() {
  clearTimeout(S.poll);
  S.panelSig = '';
  const m = location.hash.match(/^#\/p\/([\w-]+)(?:\/(\d))?/);
  if (m) {
    S.stage = Number(m[2] || 0);
    await loadProject(m[1]);
  } else {
    S.project = null;
    await renderHome();
  }
  window.scrollTo({ top: 0 });
}

async function boot() {
  S.meta = await api('GET', '/api/meta').catch(() => null);
  const chip = document.getElementById('llm-chip');
  if (S.meta?.llm) {
    chip.className = 'chip chip-ok';
    chip.innerHTML = `<span class="dot"></span>${esc(S.meta.models.main.split('/').pop())}`;
    chip.title = `Ana: ${S.meta.models.main}\nHızlı: ${S.meta.models.fast}\nHakem B: ${S.meta.models.reviewer}`;
  } else {
    chip.className = 'chip chip-bad';
    chip.textContent = 'LLM anahtarı yok';
  }
  route();
}

// ---------------------------------------------------------------- ana sayfa
async function renderHome() {
  const list = await api('GET', '/api/projects').catch(() => []);
  const dp = S.meta?.dergipark;
  $app.innerHTML = `
  <section class="hero">
    <div>
      <div class="eyebrow">Fikirden makaleye · 8 aşama · 3 insan kapısı</div>
      <h1>Araştırmanızı <em>kanıta bağlı</em> biçimde, adım adım kurun.</h1>
      <p class="lead">ResearchAI her aşamada öneri üretir, kararı size bırakır. Atıflar bağımsız kaynaklarda doğrulanır,
      veri uydurulmaz ve yapay zekâ kullanımı dürüstçe kayda geçer.</p>
      <div class="pipeline-mini">
        ${Object.entries(S.meta?.stages || {}).map(([n, name]) => `
          <div class="pm-step" style="--c:${STAGE[n].c}">${n}. ${esc(name)}
            <small>${esc(STAGE[n].tools.split(' · ')[0])}</small>
            ${S.meta.gates.includes(Number(n)) ? '<span class="gate-dot" title="İnsan kapısı"></span>' : ''}
          </div>`).join('')}
      </div>
      <p class="small muted" style="margin-top:14px">
        DergiPark yerel dizini: ${dp ? (dp.running ? 'toplanıyor…' : `${dp.records.toLocaleString('tr-TR')} kayıt`) : '—'}
        · Turuncu nokta: insan kapısı</p>
    </div>
    <form class="card new-card stack" id="new-form">
      <div><h2>Yeni araştırma</h2><p class="muted small" style="margin:0">Ham fikrinizi yazın; ilk aşama onu kapsam kartına çevirir.</p></div>
      <label class="field"><span>Çalışma adı</span><input type="text" name="title" required minlength="2" placeholder="ör. Antroposen ve dijital yüce"></label>
      <label class="field"><span>Alan</span><input type="text" name="field" placeholder="ör. Sanat kuramı, eğitim bilimleri"></label>
      <label class="field"><span>Ham fikir</span><textarea name="idea" required minlength="10" rows="5" placeholder="Neyi merak ediyorsunuz? Neden önemli? Elinizde veri var mı?"></textarea></label>
      <div class="row">
        <label class="field" style="flex:1"><span>Makale dili</span>
          <select name="language"><option value="tr">Türkçe</option><option value="en">English</option></select></label>
        <button class="btn btn-primary" style="align-self:flex-end">Projeyi başlat →</button>
      </div>
    </form>
  </section>
  <div class="section-head"><h2>Projeler</h2><span class="muted small">${list.length} proje</span></div>
  ${list.length ? `<div class="projects">${list.map(projectCard).join('')}</div>`
    : '<div class="empty">Henüz proje yok. “Yeni araştırma” formuyla ilk çalışmanızı başlatın.</div>'}`;
  document.getElementById('new-form').onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    const r = await act(() => api('POST', '/api/projects', f));
    if (r) location.hash = `#/p/${r.id}/1`;
  };
}

function projectCard(p) {
  const done = p.done || 0;
  return `<a class="card pcard" href="#/p/${esc(p.id)}">
    <div class="row"><span class="eyebrow">${esc(p.field || 'Araştırma')}</span><span class="spacer"></span>
      <span class="chip ${done === 8 ? 'chip-ok' : ''}">${done === 8 ? 'Tamamlandı' : `${done}/8`}</span></div>
    <h3>${esc(p.title)}</h3><p>${esc(p.idea)}</p>
    <div class="progress-dots">${[1, 2, 3, 4, 5, 6, 7, 8].map((n) => `<i class="${n <= done ? 'on' : ''}" style="--c:${STAGE[n].c}"></i>`).join('')}</div>
    <div class="small muted" style="margin-top:10px">Son güncelleme ${esc(fmtDate(p.updated_at))}</div></a>`;
}

// ---------------------------------------------------------------- proje
async function loadProject(id, quiet = false) {
  const p = await api('GET', `/api/projects/${id}`).catch((e) => { if (!quiet) toast(e.message, true); return null; });
  if (!p) { if (!quiet) location.hash = '#/'; return; }
  S.project = p;
  if (!S.stage) {
    const next = p.stages.find((s) => !s.approved_at);
    S.stage = next ? next.n : 8;
  }
  renderProject();
  clearTimeout(S.poll);
  if (p.stages.some((s) => s.running || s.status === 'running')) S.poll = setTimeout(() => loadProject(id, true), 2000);
}

function stageState(s, p) {
  const prevOk = s.n === 1 || p.stages[s.n - 2].approved_at;
  if (s.running || s.status === 'running') return 'running';
  if (s.approved_at) return 'approved';
  if (!prevOk) return 'locked';
  if (s.status === 'ready') return 'ready';
  if (s.status === 'error') return 'error';
  return 'idle';
}
const STATE_LABEL = { running: 'Çalışıyor…', approved: 'Onaylandı', locked: 'Kilitli', ready: 'Onay bekliyor', error: 'Hata', idle: 'Hazır değil' };

function renderProject() {
  const p = S.project;
  const st = p.stages[S.stage - 1];
  const tokens = p.usage.reduce((a, u) => a + (u.p || 0) + (u.c || 0), 0);
  const sig = JSON.stringify([S.stage, st.status, st.updated_at, st.approved_at, st.progress, S.srcFilter, p.sources.length]);
  const railHtml = `
    ${p.stages.map((s) => {
      const state = stageState(s, p);
      return `<button class="rail-item ${state} ${s.n === S.stage ? 'active' : ''}" style="--c:${STAGE[s.n].c}" data-go="${s.n}">
        <span class="rail-num">${state === 'approved' ? '✓' : s.n}</span>
        <span class="rail-text"><b>${esc(s.name)}</b><small>${STATE_LABEL[state]}</small></span>
        ${s.gate ? '<span class="gate-tag">Kapı</span>' : ''}</button>`;
    }).join('')}
    <div class="rail-foot">${tokens.toLocaleString('tr-TR')} token · ${p.usage.reduce((a, u) => a + u.n, 0)} LLM çağrısı</div>`;

  if (!document.getElementById('rail')) {
    $app.innerHTML = `
    <div class="proj-head">
      <div style="flex:1;min-width:0">
        <a href="#/" class="small muted" style="text-decoration:none">← Projeler</a>
        <h1>${esc(p.title)}</h1><p>${esc(p.idea)}</p>
      </div>
      <button class="btn btn-ghost btn-sm btn-danger" id="del-btn">Sil</button>
    </div>
    <div class="layout"><nav class="card rail" id="rail"></nav><section class="card panel" id="panel"></section></div>`;
    document.getElementById('del-btn').onclick = async () => {
      if (!confirm('Proje ve tüm çıktıları kalıcı olarak silinsin mi?')) return;
      if (await act(() => api('DELETE', `/api/projects/${p.id}`), 'Proje silindi')) location.hash = '#/';
    };
  }
  document.getElementById('rail').innerHTML = railHtml;
  document.querySelectorAll('[data-go]').forEach((b) => (b.onclick = () => (location.hash = `#/p/${p.id}/${b.dataset.go}`)));
  if (sig !== S.panelSig) {
    S.panelSig = sig;
    renderPanel();
  }
}

function renderPanel() {
  const p = S.project;
  const s = p.stages[S.stage - 1];
  const state = stageState(s, p);
  const panel = document.getElementById('panel');
  panel.style.setProperty('--stage', STAGE[s.n].c);
  const hasData = s.data && Object.keys(s.data).length > 0;
  const runLabel = hasData ? 'Yeniden çalıştır' : 'Çalıştır';
  panel.innerHTML = `
    <div class="panel-head">
      <div class="row"><span class="eyebrow">Aşama ${s.n} / 8</span>${s.gate ? '<span class="gate-tag">İnsan kapısı</span>' : ''}</div>
      <h2 style="margin-top:8px"><span class="num">${s.n}</span>${esc(s.name)}</h2>
      <p>${esc(STAGE[s.n].what)}</p>
      <div class="panel-actions">
        ${state === 'running'
          ? `<button class="btn btn-sm" data-act="cancel">Durdur</button>`
          : `<button class="btn btn-stage" data-act="run" ${state === 'locked' || !S.meta?.llm ? 'disabled' : ''}>${runLabel}</button>`}
        ${s.n === 8 ? `<input type="text" id="venue" placeholder="Hedef dergi (ör. Sanat & Tasarım Dergisi)" value="${esc(s.data?.venue || '')}" style="max-width:340px">` : ''}
        <span class="small muted">${state === 'locked' ? `Önce ${s.n - 1}. aşamayı onaylayın.` : esc(STAGE[s.n].tools)}</span>
      </div>
    </div>
    <div class="panel-body">
      ${state === 'running' ? `<div class="status-line"><span class="spinner"></span><span>${esc(s.progress || 'Çalışıyor…')}</span></div>` : ''}
      ${s.status === 'error' && s.error ? `<div class="error-box"><b>Hata:</b> ${esc(s.error)}</div>` : ''}
      <div id="stage-body">${hasData || s.n === 2 && p.sources.length ? STAGE_VIEW[s.n](s, p) : emptyStage(s, state)}</div>
      ${approveBox(s, state, hasData)}
    </div>`;
  bindPanel(s, p);
}

function emptyStage(s, state) {
  if (state === 'running') return '<div class="stack"><div class="skeleton" style="width:70%"></div><div class="skeleton"></div><div class="skeleton" style="width:85%"></div></div>';
  if (state === 'locked') return `<div class="empty">Bu aşama, ${s.n - 1}. aşama onaylanınca açılır.</div>`;
  return `<div class="empty">Henüz çıktı yok. <b>Çalıştır</b> ile başlayın.</div>`;
}

function approveBox(s, state, hasData) {
  if (state === 'running' || state === 'locked' || !hasData) return '';
  if (s.approved_at) {
    return `<div class="approved-banner"><span style="font-size:20px">✓</span><div><b>Onaylandı</b> · ${esc(fmtDate(s.approved_at))}
      ${s.approval_note ? `<p>“${esc(s.approval_note)}”</p>` : ''}
      ${s.n < 8 ? `<p><a href="#/p/${S.project.id}/${s.n + 1}">${s.n + 1}. aşamaya geç →</a></p>` : ''}</div></div>`;
  }
  return `<div class="approve-box ${s.gate ? 'gate' : ''}">
    <h3>${s.gate ? '⚑ İnsan kapısı' : 'Onay'}</h3>
    <p class="small muted" style="margin:0 0 10px">${s.gate
      ? 'Bu aşamayı ilerletmek bilinçli bir karar ister. Neyi incelediğinizi ve neden onayladığınızı yazın; not YZ kullanım beyanına girer.'
      : 'Çıktıyı inceleyip gerekirse düzenledikten sonra onaylayın. Onay, beyanda bu aşamanın insan incelemesinden geçtiğini kaydeder.'}</p>
    <textarea id="approve-note" rows="2" placeholder="${s.gate ? 'ör. Hipotez H2\'yi seçtim; tema 3 kaynakları zayıf, 4. aşamada saha verisiyle desteklenecek.' : 'İsteğe bağlı not'}"></textarea>
    <div class="row" style="margin-top:10px"><button class="btn btn-primary" data-act="approve">Onayla ve ilerle</button></div></div>`;
}

function bindPanel(s, p) {
  const panel = document.getElementById('panel');
  panel.querySelectorAll('[data-act]').forEach((el) => {
    el.onclick = async () => {
      const a = el.dataset.act;
      if (a === 'run') {
        const body = s.n === 8 ? { venue: document.getElementById('venue')?.value || '' } : undefined;
        if (await act(() => api('POST', `/api/projects/${p.id}/stages/${s.n}/run`, body), 'Aşama başlatıldı')) loadProject(p.id);
      } else if (a === 'cancel') {
        await act(() => api('POST', `/api/projects/${p.id}/stages/${s.n}/cancel`));
        loadProject(p.id);
      } else if (a === 'approve') {
        const note = document.getElementById('approve-note').value;
        if (await act(() => api('POST', `/api/projects/${p.id}/stages/${s.n}/approve`, { note }), 'Onaylandı')) {
          if (s.n < 8) location.hash = `#/p/${p.id}/${s.n + 1}`;
          else loadProject(p.id);
        }
      }
    };
  });
  STAGE_BIND[s.n]?.(s, p);
}

async function saveStage(data, msg = 'Kaydedildi') {
  const p = S.project;
  if (await act(() => api('PUT', `/api/projects/${p.id}/stages/${S.stage}`, { data }), msg)) {
    S.panelSig = '';
    loadProject(p.id);
  }
}

// ---------------------------------------------------------------- aşama görünümleri
const STAGE_VIEW = {};
const STAGE_BIND = {};

// 1. Fikir
const F1 = [
  ['title', 'Başlık önerisi', 'text'], ['research_question', 'Araştırma sorusu', 'area'],
  ['sub_questions', 'Alt sorular (satır başına bir)', 'lines'], ['scope', 'Kapsam', 'area'],
  ['out_of_scope', 'Kapsam dışı', 'area'], ['method_type', 'Yöntem türü', 'method'],
  ['keywords', 'Anahtar kelimeler', 'lines'], ['search_queries', 'Arama sorguları (2. aşama bunları kullanır)', 'lines'],
  ['inclusion', 'Dahil etme ölçütleri', 'lines'], ['exclusion', 'Dışlama ölçütleri', 'lines'], ['year_from', 'En erken yıl', 'num'],
];
STAGE_VIEW[1] = (s) => {
  const d = s.data;
  const field = ([k, label, t]) => {
    const v = d[k];
    let input;
    if (t === 'text') input = `<input type="text" data-k="${k}" value="${esc(v)}">`;
    else if (t === 'num') input = `<input type="number" data-k="${k}" data-t="num" value="${esc(v ?? '')}" placeholder="boş: sınır yok">`;
    else if (t === 'method') input = `<select data-k="${k}">${[['empirical', 'Ampirik (nicel/nitel veri)'], ['humanities', 'Beşeri bilimler / kuramsal'], ['review', 'Derleme'], ['mixed', 'Karma']]
      .map(([o, l]) => `<option value="${o}" ${v === o ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
    else input = `<textarea data-k="${k}" data-t="${t}" rows="${t === 'lines' ? Math.max(2, (v || []).length + 1) : 2}">${esc(t === 'lines' ? lines(v) : v)}</textarea>`;
    return `<label class="field"><span>${label}</span>${input}</label>`;
  };
  return `<div class="grid-2">${F1.map(field).join('')}</div>
    ${d.risks?.length ? `<div class="subhead">Riskler</div><div class="warn-box">${ul(d.risks)}</div>` : ''}
    <div class="row" style="margin-top:16px"><button class="btn" id="save1">Değişiklikleri kaydet</button>
    <span class="small muted">Kaydetmek bu ve sonraki aşamaların onayını düşürür.</span></div>`;
};
STAGE_BIND[1] = () => {
  const b = document.getElementById('save1');
  if (!b) return;
  b.onclick = () => {
    const data = {};
    document.querySelectorAll('#stage-body [data-k]').forEach((el) => {
      const t = el.dataset.t;
      data[el.dataset.k] = t === 'lines' ? unlines(el.value) : t === 'num' ? (el.value ? Number(el.value) : null) : el.value;
    });
    saveStage(data);
  };
};

// 2. Literatür
STAGE_VIEW[2] = (s, p) => {
  const d = s.data || {};
  const sel = p.sources.filter((x) => x.selected).length;
  const list = S.srcFilter === 'selected' ? p.sources.filter((x) => x.selected) : p.sources;
  const errs = Object.entries(d.errors || {});
  return `
    <div class="stats">
      <div class="stat"><b>${d.raw ?? '—'}</b><span>tekil sonuç</span></div>
      <div class="stat"><b>${d.candidates ?? p.sources.length}</b><span>elenen aday</span></div>
      <div class="stat ok"><b>${sel}</b><span>seçili kaynak</span></div>
      <div class="stat"><b>${(d.queries || []).length}</b><span>sorgu</span></div>
    </div>
    ${errs.length ? `<div class="warn-box" style="margin-top:14px"><b>Yanıt vermeyen kaynaklar:</b> ${errs.map(([k, v]) => `${esc(k)} (${esc(v.slice(0, 60))})`).join(' · ')}</div>` : ''}
    <div class="subhead">Kaynaklar</div>
    <div class="src-tools">
      <div class="seg"><button data-f="selected" class="${S.srcFilter === 'selected' ? 'on' : ''}">Seçili (${sel})</button>
        <button data-f="all" class="${S.srcFilter === 'all' ? 'on' : ''}">Tümü (${p.sources.length})</button></div>
      <span class="small muted">Puan: 3 doğrudan ilgili · 2 ilgili · 1 dolaylı · 0 ilgisiz. Seçimi değiştirmek onayı düşürür.</span>
    </div>
    <div class="block" style="padding:4px 12px">${list.length ? list.map(srcRow).join('') : '<p class="muted" style="padding:14px 0">Bu görünümde kaynak yok.</p>'}</div>
    <details class="add"><summary>+ Kaynağı elle ekle (kitap, tez, arşiv belgesi…)</summary>
      <form id="add-src" class="grid-2" style="margin-top:12px">
        <label class="field"><span>Başlık</span><input type="text" name="title" required></label>
        <label class="field"><span>Yazarlar (virgülle değil, satırla)</span><textarea name="authors" rows="2" placeholder="Soyad, Ad"></textarea></label>
        <label class="field"><span>Yıl</span><input type="number" name="year"></label>
        <label class="field"><span>Dergi / yayınevi</span><input type="text" name="venue"></label>
        <label class="field"><span>DOI</span><input type="text" name="doi"></label>
        <label class="field"><span>Özet (iddia denetimi için gerekli)</span><textarea name="abstract" rows="2"></textarea></label>
        <div><button class="btn">Ekle</button></div>
      </form></details>`;
};
function srcRow(x) {
  const pp = x.paper;
  const au = (pp.authors || []).slice(0, 3).join('; ') + ((pp.authors || []).length > 3 ? ' vd.' : '');
  const link = pp.doi ? `https://doi.org/${pp.doi}` : pp.url;
  return `<div class="src">
    <input type="checkbox" data-src="${x.i}" ${x.selected ? 'checked' : ''} aria-label="Seç">
    <span class="score score-${x.score ?? 'x'}" title="İlgi puanı">${x.score ?? '–'}</span>
    <div><div class="src-title">${link ? `<a href="${esc(link)}" target="_blank" rel="noopener">${esc(pp.title)}</a>` : esc(pp.title)} <span class="ref">[${x.i}]</span></div>
      <div class="src-meta">${esc(au)}${pp.year ? ` · ${pp.year}` : ''}${pp.venue ? ` · ${esc(pp.venue)}` : ''}</div>
      <div class="row" style="gap:6px;margin-top:4px"><span class="tags">${(pp.found_in || []).map((f) => `<span class="tag ${f === 'trdizin' || f === 'dergipark' ? 'tag-tr' : ''}">${esc(f)}</span>`).join('')}</span>
        ${!pp.abstract ? '<span class="tag">özet yok</span>' : ''}</div>
      ${x.reason ? `<div class="src-reason">${esc(x.reason)}</div>` : ''}</div></div>`;
}
STAGE_BIND[2] = (s, p) => {
  document.querySelectorAll('[data-f]').forEach((b) => (b.onclick = () => { S.srcFilter = b.dataset.f; S.panelSig = ''; renderProject(); }));
  document.querySelectorAll('[data-src]').forEach((c) => (c.onchange = async () => {
    await act(() => api('PUT', `/api/projects/${p.id}/sources/${c.dataset.src}`, { selected: c.checked }));
    const src = p.sources.find((x) => x.i === Number(c.dataset.src));
    if (src) src.selected = c.checked;
    p.stages[1].approved_at = null;
    S.panelSig = '';
    loadProject(p.id, true);
  }));
  const f = document.getElementById('add-src');
  if (f) f.onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(f));
    const body = { title: d.title, authors: unlines(d.authors), year: d.year ? Number(d.year) : null, venue: d.venue || null, doi: d.doi || null, abstract: d.abstract || null };
    if (await act(() => api('POST', `/api/projects/${p.id}/sources`, body), 'Kaynak eklendi')) { S.panelSig = ''; loadProject(p.id); }
  };
};

// 3. Sentez
const refChips = (ids, p) => (ids || []).length ? `<span class="refs">${ids.map((i) => {
  const src = p.sources.find((x) => x.i === Number(i));
  return `<span class="ref" title="${esc(src ? src.paper.title : 'bilinmeyen kaynak')}">[${esc(i)}]</span>`;
}).join('')}</span>` : '';
STAGE_VIEW[3] = (s, p) => {
  const d = s.data;
  const chosen = new Set(d.chosen || []);
  return `
    <div class="subhead">Temalar</div>
    <div class="blocks">${(d.themes || []).map((t) => `<div class="block"><h4>${esc(t.name)}</h4><p>${esc(t.summary)}</p>${refChips(t.sources, p)}</div>`).join('')}</div>
    <div class="subhead">Boşluk haritası</div>
    <div class="stack">${(d.gaps || []).map((g) => `<div class="block" style="border-left:4px solid var(--stage)"><h4>${esc(g.gap)}</h4><p>${esc(g.why)}</p>${refChips(g.sources, p)}</div>`).join('')}</div>
    ${(d.tensions || []).length ? `<div class="subhead">Kaynaklar arası gerilimler</div><div class="warn-box">${ul(d.tensions)}</div>` : ''}
    <div class="subhead">Hipotezler — taslakta kullanılacakları seçin</div>
    <div>${(d.hypotheses || []).map((h) => `<label class="hyp ${chosen.has(h.id) ? 'on' : ''}">
      <input type="checkbox" data-h="${esc(h.id)}" ${chosen.has(h.id) ? 'checked' : ''}>
      <div><b>${esc(h.id)}</b> <span style="font-weight:600">${esc(h.text)}</span>
        <div class="small muted" style="margin-top:4px"><b style="color:var(--ink-3);font-family:inherit">Dayanak:</b> ${esc(h.rationale)}</div>
        <div class="small muted"><b style="color:var(--ink-3);font-family:inherit">Nasıl sınanır:</b> ${esc(h.test)}</div></div></label>`).join('')}</div>
    <div class="row" style="margin-top:12px"><button class="btn" id="save3">Seçimi kaydet</button></div>`;
};
STAGE_BIND[3] = () => {
  document.querySelectorAll('[data-h]').forEach((c) => (c.onchange = () => c.closest('.hyp').classList.toggle('on', c.checked)));
  const b = document.getElementById('save3');
  if (b) b.onclick = () => saveStage({ chosen: [...document.querySelectorAll('[data-h]:checked')].map((c) => c.dataset.h) }, 'Hipotez seçimi kaydedildi');
};

// 4. Deney / Veri
STAGE_VIEW[4] = (s) => {
  const d = s.data;
  const pl = d.plan || {};
  return `
    <div class="subhead">Yöntem planı (öneri)</div>
    <dl class="kv">
      <dt>Desen</dt><dd>${esc(pl.design)}</dd>
      <dt>Birimler / değişkenler</dt><dd>${ul(pl.units)}</dd>
      <dt>Çözümleme</dt><dd>${esc(pl.analysis)}</dd>
      <dt>Adımlar</dt><dd>${pl.steps?.length ? `<ol class="list-plain">${pl.steps.map((x) => `<li>${esc(x)}</li>`).join('')}</ol>` : '—'}</dd>
      <dt>Etik / izin</dt><dd>${esc(pl.ethics)}</dd>
      <dt>Geçerlik tehditleri</dt><dd>${ul(pl.threats)}</dd>
    </dl>
    ${(pl.data_sources || []).length ? `<div class="subhead">Veri kaynakları</div>
      <table class="tbl"><thead><tr><th>Kaynak</th><th>Neden</th><th>Erişim</th></tr></thead><tbody>
      ${pl.data_sources.map((x) => `<tr><td><b>${esc(x.name)}</b> ${x.tr_specific ? '<span class="tag tag-tr">TR</span>' : ''}</td><td>${esc(x.why)}</td><td>${esc(x.access)}</td></tr>`).join('')}
      </tbody></table>` : ''}
    <div class="subhead">Sizin sonuçlarınız</div>
    <div class="note-box" style="margin-bottom:12px">Taslağın Bulgular/Çözümleme bölümü <b>yalnız buraya yazdıklarınızdan</b> üretilir. Boş bırakırsanız taslakta
      <span class="placeholder">[VERİ BEKLENİYOR]</span> yer tutucuları çıkar; sistem sonuç uydurmaz.</div>
    <label class="field"><span>Sonuçlar ve gözlemler (sayılar, temalar, alıntılar…)</span><textarea id="results" rows="7">${esc(d.results)}</textarea></label>
    <label class="field" style="margin-top:12px"><span>Veri tablosu (CSV, isteğe bağlı; 6. aşama grafik üretir)</span>
      <textarea id="csv" class="code" rows="5" placeholder="yil,deger\n2020,12\n2021,18">${esc(d.csv)}</textarea></label>
    <div class="row" style="margin-top:12px"><button class="btn" id="save4">Sonuçları kaydet</button></div>`;
};
STAGE_BIND[4] = () => {
  const b = document.getElementById('save4');
  if (b) b.onclick = () => saveStage({ results: document.getElementById('results').value, csv: document.getElementById('csv').value }, 'Sonuçlar kaydedildi');
};

// 5. Taslak
const VERDICT = { yes: ['c-yes', 'destekliyor'], partial: ['c-partial', 'kısmen'], no: ['c-no', 'desteklemiyor'], cannot_access: ['c-na', 'erişilemedi'] };
function renderDraftText(sec, si, claims) {
  const mine = claims.map((c, k) => ({ ...c, k })).filter((c) => c.section === si);
  const paras = [];
  for (const para of sec.text.split(/\n\s*\n/)) {
    let out = '';
    let ptext = para.trim();
    if (!ptext) continue;
    for (const c of mine) {
      const at = ptext.indexOf(c.text);
      if (at < 0) continue;
      out += fmtInline(ptext.slice(0, at));
      const vs = Object.values(c.verdicts || {}).map((v) => v.v);
      const cls = c.flag === 'not_in_results' ? 'v-fab' : c.flag ? 'v-flag' : vs.includes('no') ? 'v-no' : vs.includes('partial') ? 'v-partial' : '';
      out += `<span class="sent ${cls}" data-claim="${c.k}">${fmtInline(c.text, c.verdicts)}</span> `;
      ptext = ptext.slice(at + c.text.length);
    }
    out += fmtInline(ptext);
    paras.push(`<p>${out}</p>`);
  }
  return paras.join('');
}
function fmtInline(t, verdicts) {
  let h = esc(t);
  h = h.replace(/\[(VERİ BEKLENİYOR[^\]]*|VERI BEKLENIYOR[^\]]*|kaynak gerekli)\]/gi, '<span class="placeholder">[$1]</span>');
  h = h.replace(/\[(\d+(?:\s*[,;–-]\s*\d+)*)\]/g, (m, g) => g.split(/\s*[,;]\s*/).map((n) => {
    const v = verdicts?.[n.trim()]?.v;
    return `<span class="cite ${v ? VERDICT[v]?.[0] || 'c-na' : 'c-na'}">${esc(n.trim())}</span>`;
  }).join(''));
  return h.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
}
STAGE_VIEW[5] = (s, p) => {
  const d = s.data;
  const cs = d.claims_summary || {};
  const claims = d.claims || [];
  if (S.editDraft) {
    return `<div class="warn-box" style="margin-bottom:14px">Düzenlenen taslakta iddia-kaynak denetimi eskir; 7. aşamada yeniden denetlemek için taslağı yeniden üretmeniz gerekir. Atıfları <code>[kaynak no]</code> biçiminde bırakın.</div>
      ${(d.sections || []).map((sec, i) => `<label class="field" style="margin-top:12px"><span>${esc(sec.title)}</span><textarea data-sec="${i}" rows="12">${esc(sec.text)}</textarea></label>`).join('')}
      <div class="row" style="margin-top:12px"><button class="btn btn-primary" id="save5">Kaydet</button><button class="btn btn-ghost" id="cancel5">Vazgeç</button></div>`;
  }
  return `
    <div class="stats">
      <div class="stat"><b>${cs.sentences ?? 0}</b><span>cümle</span></div>
      <div class="stat"><b>${cs.cited ?? 0}</b><span>atıflı cümle</span></div>
      <div class="stat ok"><b>${cs.yes ?? 0}</b><span>destekleniyor</span></div>
      <div class="stat warn"><b>${cs.partial ?? 0}</b><span>kısmen</span></div>
      <div class="stat bad"><b>${cs.no ?? 0}</b><span>desteklenmiyor</span></div>
      <div class="stat"><b>${(cs.cannot_access ?? 0) + (cs.needs_source ?? 0) + (cs.unknown_ref ?? 0)}</b><span>erişilemedi / kaynak gerek</span></div>
      <div class="stat ${cs.not_in_results ? 'bad' : ''}"><b>${cs.not_in_results ?? 0}</b><span>sonuçlarda olmayan bulgu</span></div>
    </div>
    ${cs.not_in_results ? `<div class="error-box" style="margin-top:14px"><b>${cs.not_in_results} cümle</b>, 4. aşamada girdiğiniz sonuçlarda olmayan bir bulgu ya da veri toplaması iddia ediyor (kırmızı zeminli cümleler). Bunları silin ya da sonuçlarınızı tamamlayın.</div>` : ''}
    ${d.claims_stale ? '<div class="warn-box" style="margin-top:14px">Taslak elle düzenlendi; aşağıdaki iddia denetimi eski metne aittir.</div>' : ''}
    <div class="row" style="margin:18px 0 6px"><div class="legend">
      <span><span class="cite c-yes">n</span> özet destekliyor</span><span><span class="cite c-partial">n</span> kısmen</span>
      <span><span class="cite c-no">n</span> desteklemiyor</span><span><span class="cite c-na">n</span> özet yok</span></div>
      <span class="spacer"></span><button class="btn btn-sm" id="edit5">Metni düzenle</button></div>
    <p class="small muted" style="margin:0 0 18px">Bir cümleye tıklayınca denetim gerekçesi açılır. Denetim yalnız kaynak özetine dayanır; tam metni siz okumalısınız.</p>
    <article class="draft">${(d.sections || []).map((sec, i) => `<h3>${esc(sec.title)}</h3>${renderDraftText(sec, i, claims)}`).join('')}</article>`;
};
STAGE_BIND[5] = (s, p) => {
  const e = document.getElementById('edit5');
  if (e) e.onclick = () => { S.editDraft = true; S.panelSig = ''; renderProject(); };
  const c = document.getElementById('cancel5');
  if (c) c.onclick = () => { S.editDraft = false; S.panelSig = ''; renderProject(); };
  const sv = document.getElementById('save5');
  if (sv) sv.onclick = () => {
    const sections = (s.data.sections || []).map((sec, i) => ({ ...sec, text: document.querySelector(`[data-sec="${i}"]`).value }));
    S.editDraft = false;
    saveStage({ sections }, 'Taslak kaydedildi');
  };
  document.querySelectorAll('[data-claim]').forEach((el) => (el.onclick = (ev) => showClaim(ev, s.data.claims[Number(el.dataset.claim)], p)));
};
function showClaim(ev, c, p) {
  document.querySelector('.pop')?.remove();
  const pop = document.createElement('div');
  pop.className = 'pop';
  const rows = c.refs.map((i) => {
    const src = p.sources.find((x) => x.i === i);
    const v = c.verdicts?.[String(i)];
    const [cls, lbl] = v ? VERDICT[v.v] || ['c-na', v.v] : ['c-na', 'denetlenmedi'];
    return `<div class="v"><span class="cite ${cls}">${i}</span><div><b>${esc(lbl)}</b> — ${esc(v?.note || '')}
      <div class="small muted">${esc(src ? src.paper.title : 'Seçili kaynaklarda yok')}</div></div></div>`;
  }).join('');
  const flag = c.flag === 'needs_source' ? '<div class="warn-box small" style="margin-top:8px">Model bu cümle için kaynak bulamadı.</div>'
    : c.flag === 'not_in_results' ? `<div class="error-box small" style="margin:8px 0 0"><b>Sonuçlarınızda yok:</b> çalışmanın kendi bulgusu gibi yazılmış ama 4. aşamada girdiğiniz sonuçlarda karşılığı yok. ${esc(c.note || '')}</div>`
    : c.flag === 'unknown_ref' ? '<div class="error-box small" style="margin:8px 0 0">Seçili kaynaklarda olmayan bir numaraya atıf var.</div>' : '';
  pop.innerHTML = `<div class="eyebrow">İddia denetimi</div>${rows || '<p class="muted" style="margin:8px 0 0">Bu cümlede atıf yok.</p>'}${flag}`;
  document.body.appendChild(pop);
  const r = ev.target.closest('.sent').getBoundingClientRect();
  const top = r.bottom + 8 + pop.offsetHeight > innerHeight ? r.top - pop.offsetHeight - 8 : r.bottom + 8;
  pop.style.top = `${Math.max(8, top)}px`;
  pop.style.left = `${Math.min(Math.max(8, r.left), innerWidth - pop.offsetWidth - 8)}px`;
  setTimeout(() => document.addEventListener('click', function off(e2) {
    if (!pop.contains(e2.target)) { pop.remove(); document.removeEventListener('click', off); }
  }), 0);
}

// 6. Görsel
let mermaidMod;
async function renderMermaid(code, host) {
  try {
    mermaidMod ||= (await import('https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs')).default;
    const dark = getComputedStyle(document.body).colorScheme === 'dark' || document.documentElement.dataset.theme === 'dark';
    mermaidMod.initialize({ startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'neutral', fontFamily: 'Inter' });
    const { svg } = await mermaidMod.render(`m${Date.now()}`, code);
    host.innerHTML = svg;
  } catch (e) {
    host.innerHTML = `<div class="error-box">Şema çizilemedi: ${esc(e.message || e)}. Kodu düzeltip “Çiz”e basın.</div>`;
  }
}
let chartLib;
function loadChart() {
  if (chartLib) return chartLib;
  chartLib = new Promise((res, rej) => {
    const sc = document.createElement('script');
    sc.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js';
    sc.onload = () => res(window.Chart);
    sc.onerror = rej;
    document.head.appendChild(sc);
  });
  return chartLib;
}
STAGE_VIEW[6] = (s) => {
  const d = s.data;
  return `
    <div class="subhead">Şekil 1 — Metodoloji şeması</div>
    <figure class="figure" style="margin:0"><div class="mermaid-host" id="mmd"><div class="skeleton"></div></div>
      <figcaption>${esc(d.mermaid_caption)}</figcaption></figure>
    <details class="add"><summary>Şema kodunu düzenle (Mermaid)</summary>
      <textarea id="mmd-code" class="code" rows="10" style="margin-top:10px">${esc(d.mermaid)}</textarea>
      <div class="row" style="margin-top:8px"><button class="btn btn-sm" id="mmd-draw">Çiz</button><button class="btn btn-sm" id="mmd-save">Kaydet</button></div></details>
    ${(d.charts || []).length ? `<div class="subhead">Veri grafikleri</div>${d.charts.map((c, i) => `<figure class="figure" style="margin:0 0 14px">
      <canvas id="chart${i}" height="120"></canvas><figcaption>${esc(c.title)} — ${esc(c.caption)}</figcaption></figure>`).join('')}`
      : '<div class="note-box" style="margin-top:18px">Veri grafiği yok: 4. aşamada CSV girerseniz burada sonuç grafikleri önerilir.</div>'}`;
};
STAGE_BIND[6] = async (s) => {
  const d = s.data;
  const host = document.getElementById('mmd');
  if (!host) return;
  renderMermaid(d.mermaid || 'flowchart TD\n  A["şema yok"]', host);
  document.getElementById('mmd-draw').onclick = () => renderMermaid(document.getElementById('mmd-code').value, host);
  document.getElementById('mmd-save').onclick = () => saveStage({ mermaid: document.getElementById('mmd-code').value }, 'Şema kaydedildi');
  if ((d.charts || []).length && d.table) {
    const Chart = await loadChart().catch(() => null);
    if (!Chart) return;
    const css = getComputedStyle(document.documentElement);
    const palette = ['--s2', '--s6', '--s3', '--s1', '--s7'].map((v) => css.getPropertyValue(v).trim());
    const ink = css.getPropertyValue('--ink-2').trim();
    const grid = css.getPropertyValue('--line').trim();
    const cols = d.table.columns;
    d.charts.forEach((c, i) => {
      const xi = cols.indexOf(c.x);
      const num = (v) => Number(String(v).replace(',', '.'));
      const datasets = c.y.map((y, k) => {
        const yi = cols.indexOf(y);
        const data = c.type === 'scatter' ? d.table.rows.map((r) => ({ x: num(r[xi]), y: num(r[yi]) })) : d.table.rows.map((r) => num(r[yi]));
        return { label: y, data, backgroundColor: palette[k % palette.length], borderColor: palette[k % palette.length], borderWidth: 2, pointRadius: 3, tension: .25 };
      });
      new Chart(document.getElementById(`chart${i}`), {
        type: c.type === 'scatter' ? 'scatter' : c.type === 'line' ? 'line' : 'bar',
        data: { labels: c.type === 'scatter' ? undefined : d.table.rows.map((r) => r[xi]), datasets },
        options: { responsive: true, plugins: { legend: { labels: { color: ink } } },
          scales: { x: { ticks: { color: ink }, grid: { color: grid }, title: { display: true, text: c.x, color: ink } },
                    y: { ticks: { color: ink }, grid: { color: grid } } } },
      });
    });
  }
};

// 7. Doğrulama
const VSTAT = { verified: ['chip-ok', 'doğrulandı'], uncertain: ['chip-warn', 'belirsiz'], mismatch: ['chip-bad', 'uyuşmazlık'], not_found: ['chip-bad', 'bulunamadı'] };
const DEC = { accept: ['chip-ok', 'Kabul'], minor: ['chip-info', 'Küçük düzeltme'], major: ['chip-warn', 'Büyük düzeltme'], reject: ['chip-bad', 'Ret'] };
STAGE_VIEW[7] = (s, p) => {
  const d = s.data;
  const v = d.verification || {};
  const cs = d.claims_summary || {};
  const cited = p.sources.filter((x) => x.verify);
  return `
    <div class="subhead">Atıf doğrulama — ${d.cited ?? 0} kaynak</div>
    <div class="stats">
      <div class="stat ok"><b>${v.verified ?? 0}</b><span>doğrulandı</span></div>
      <div class="stat warn"><b>${v.uncertain ?? 0}</b><span>belirsiz</span></div>
      <div class="stat bad"><b>${(v.mismatch ?? 0) + (v.not_found ?? 0)}</b><span>uyuşmazlık / bulunamadı</span></div>
      <div class="stat ${cs.no ? 'bad' : ''}"><b>${cs.no ?? 0}</b><span>desteklenmeyen iddia</span></div>
      <div class="stat ${cs.not_in_results ? 'bad' : ''}"><b>${cs.not_in_results ?? 0}</b><span>sonuçlarda olmayan bulgu</span></div>
    </div>
    <p class="small muted">“Bulunamadı” atıfın uydurma olduğunu kanıtlamaz; kitap ve yerel kaynaklar çoğu dizinde yoktur. Her bayrağa insan gözüyle bakın.</p>
    <div class="block" style="padding:4px 14px">${cited.map((x) => {
      const r = x.verify;
      const [cls, lbl] = VSTAT[r.status] || ['', r.status];
      const ev = (r.evidence || []).map((e) => e.source).filter((a, i, arr) => arr.indexOf(a) === i);
      return `<div class="src" style="grid-template-columns:110px 1fr"><span class="chip ${cls}">${lbl}</span>
        <div><div class="src-title">${esc(x.paper.title)} <span class="ref">[${x.i}]</span></div>
        <div class="src-meta">${ev.length ? `Kanıt: ${ev.map(esc).join(', ')}` : 'Bağımsız kanıt yok'}${r.confidence ? ` · güven: ${esc(r.confidence)}` : ''}</div></div></div>`;
    }).join('') || '<p class="muted">Doğrulanan kaynak yok.</p>'}</div>

    <div class="subhead">Yerel benzerlik taraması</div>
    ${(d.similarity || []).length ? `<div class="stack">${d.similarity.map((f) => `<div class="block" style="border-left:4px solid var(--warn)">
      <p>“${esc(f.sentence)}”</p><div class="small muted" style="margin-top:6px">Kaynak [${f.source}] özetiyle %${Math.round(f.overlap * 100)} örtüşen 5'li sözcük dizisi — yeniden yazın ya da tırnak içinde alıntılayın.</div></div>`).join('')}</div>`
      : '<div class="note-box">Kaynak özetleriyle belirgin örtüşen cümle bulunmadı. Bu, tam metin intihal taraması değildir; dergiye göndermeden önce iThenticate/Turnitin raporu alın.</div>'}

    <div class="subhead">Kör hakem simülasyonu — iki farklı model</div>
    <div class="grid-2">${(d.reviews || []).map((r) => r.error ? `<div class="block review"><h4>${esc(r.reviewer)}</h4><p class="small muted">${esc(r.model)}</p><div class="error-box" style="margin-top:10px">${esc(r.error)}</div></div>`
      : `<div class="block review stack">
        <div class="row"><h4>${esc(r.reviewer)}</h4><span class="spacer"></span><span class="chip decision ${(DEC[r.decision] || [''])[0]}">${esc((DEC[r.decision] || [, r.decision])[1])}</span></div>
        <div class="small muted" style="margin-top:2px">${esc(r.model)}</div>
        <p>${esc(r.summary)}</p>
        <div><div class="eyebrow">Güçlü yanlar</div>${ul(r.strengths)}</div>
        <div><div class="eyebrow">Zayıf yanlar</div>${ul(r.weaknesses)}</div>
        <div><div class="eyebrow">Zorunlu değişiklikler</div>${ul(r.required_changes)}</div>
        ${(r.questions || []).length ? `<div><div class="eyebrow">Yazara sorular</div>${ul(r.questions)}</div>` : ''}</div>`).join('')}</div>`;
};

// 8. Gönderim
STAGE_VIEW[8] = (s, p) => {
  const d = s.data;
  const L = p.language;
  return `
    <div class="grid-2">
      <div class="block stack"><div class="eyebrow">Türkçe</div><h3 style="font-size:20px">${esc(d.title_tr)}</h3>
        <p>${esc(d.abstract_tr)}</p><div class="tags">${(d.keywords_tr || []).map((k) => `<span class="tag">${esc(k)}</span>`).join('')}</div></div>
      <div class="block stack"><div class="eyebrow">English</div><h3 style="font-size:20px">${esc(d.title_en)}</h3>
        <p>${esc(d.abstract_en)}</p><div class="tags">${(d.keywords_en || []).map((k) => `<span class="tag">${esc(k)}</span>`).join('')}</div></div>
    </div>
    <div class="subhead">İndir</div>
    <div class="downloads">
      <a class="btn" href="/api/projects/${p.id}/export/md" download>Makale (.md)</a>
      <a class="btn" href="/api/projects/${p.id}/export/tex" download>LaTeX (.tex)</a>
      <a class="btn" href="/api/projects/${p.id}/export/bib" download>Kaynakça (.bib)</a>
    </div>
    <p class="small muted">LaTeX dosyası <code>biblatex</code> (APA) ve aynı klasördeki <code>references.bib</code> ile derlenir; .bib dosyasını bu adla kaydedin.
      Dergi şablonuna uyarlama ${d.venue ? `(<b>${esc(d.venue)}</b>)` : ''} elle yapılmalıdır.</p>
    <div class="subhead">Yapay zekâ kullanım beyanı</div>
    <div class="row" style="margin-bottom:10px"><div class="seg"><button data-dl="tr" class="${S.disclosureLang === 'tr' ? 'on' : ''}">Türkçe</button><button data-dl="en" class="${S.disclosureLang === 'en' ? 'on' : ''}">English</button></div>
      <span class="spacer"></span><button class="btn btn-sm" id="copy-disc">Kopyala</button></div>
    <div id="disc" class="md-out"><div class="skeleton"></div></div>
    <p class="small muted">Beyan günlükten üretilir ve gerçeği iyileştirmez: onaylanmamış aşamalar “incelenmedi” diye yazılır. Bu aşamayı onayladıktan sonra beyan güncellenir.</p>`;
};
STAGE_BIND[8] = async (s, p) => {
  const box = document.getElementById('disc');
  if (!box) return;
  document.querySelectorAll('[data-dl]').forEach((b) => (b.onclick = () => { S.disclosureLang = b.dataset.dl; S.panelSig = ''; renderProject(); }));
  const r = await api('GET', `/api/projects/${p.id}/export/disclosure?lang=${S.disclosureLang}`).catch((e) => ({ markdown: e.message, warnings: [] }));
  box.textContent = r.markdown + (r.warnings.length ? `\n\n⚠ ${r.warnings.join('\n⚠ ')}` : '');
  document.getElementById('copy-disc').onclick = () => navigator.clipboard.writeText(r.markdown).then(() => toast('Beyan kopyalandı'));
};

boot();

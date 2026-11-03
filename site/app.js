(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const CATEGORIES = ["全部", "产能布局", "贸易政策", "物流风险", "科技原料", "综合"];
  const state = {articles: [], status: null, days: 7, category: "全部", query: "", page: "feed", isPreview: true, generatedAt: null, loaded: false};
  const FAVORITES = "chainbrief-favorites-v1";
  const ARCHIVE = "chainbrief-last-news-v1";
  const getJSON = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
  const localGet = key => { try { return localStorage.getItem(key); } catch {return null;} };
  let favorites = getJSON(FAVORITES, {});
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const safeHref = (url) => { try { let u = new URL(url); return /^(https?:)$/.test(u.protocol) ? u.href : "#"; } catch { return "#"; } };
  const fmtDate = (time, dayOnly=false) => {
    const d = new Date(time);
    if (Number.isNaN(+d)) return "时间未标注";
    return new Intl.DateTimeFormat("zh-CN", dayOnly ? {year:"numeric",month:"2-digit",day:"2-digit"} : {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).format(d);
  };
  const daysAgo = (v) => Date.now() - new Date(v).getTime();
  function getVisible() {
    const a = state.page === "saved" ? Object.values(favorites) : state.articles;
    const maxAge = state.days * 864e5;
    return a.filter(x => (state.page === "saved" || daysAgo(x.published_at) <= maxAge) && daysAgo(x.published_at) >= -3 * 3600e3)
      .filter(x => state.category === "全部" || x.category === state.category)
      .filter(x => !state.query || [x.title,x.summary,x.source,x.category].join(" ").toLocaleLowerCase().includes(state.query))
      .sort((a,b) => new Date(b.published_at) - new Date(a.published_at));
  }
  function drawFilters() {
    $("filters").innerHTML = CATEGORIES.map(c => `<button class="filter ${state.category === c ? 'active' : ''}" data-category="${esc(c)}" aria-pressed="${state.category === c}">${esc(c)}</button>`).join("");
  }
  function render() {
    drawFilters();
    const visible = getVisible();
    const title = state.page === "saved" ? "我的收藏" : "最新关注";
    document.querySelector(".section-heading h2").textContent = title;
    $("feed-count").textContent = `共 ${visible.length} 篇`;
    $("stat-total").textContent = state.articles.length;
    $("stat-sources").textContent = new Set(state.articles.map(a=>a.source)).size;
    $("stat-new").textContent = state.articles.filter(a=>daysAgo(a.published_at) <= 864e5 && daysAgo(a.published_at) >= -3 * 3600e3).length;
    $("feed-view").hidden = state.page === "about";
    $("about-view").hidden = state.page !== "about";
    $("about-updated").textContent = state.generatedAt ? fmtDate(state.generatedAt) : "尚无成功更新时间";
    const ok = state.status?.success_sources ?? 0;
    $("about-status").textContent = state.status?.checked_at ? `最近检查 ${fmtDate(state.status.checked_at)}；${ok}/${state.status.total_sources ?? 0} 个新闻源成功响应。` : "尚未部署自动更新（本地预览）";
    $("diagnostics").textContent = state.status?.sources?.length ? state.status.sources.map(s=>`${s.ok ? '✓':'×'} ${s.source}｜${s.ok ? `${s.accepted ?? 0} 篇符合条件` : s.error}`).join("\n") : "暂无新闻源诊断，发布到网站后自动生成。";
    document.querySelectorAll(".nav-item").forEach(b=>b.classList.toggle("active",b.dataset.page===state.page));
    if (!visible.length) {
      $("article-list").innerHTML = `<div class="empty-state"><div class="empty-symbol">⌕</div><h3>${state.page === "saved" ? '还没有收藏的新闻' : '当前筛选下暂无新闻'}</h3><p>尝试切换近7天、选择「全部」或清除关键词。<br/>若是网络更新失败，请在「关于」查看诊断。</p><a href="https://news.google.com/search?q=%E5%85%A8%E7%90%83%E4%BE%9B%E5%BA%94%E9%93%BE&hl=zh-CN&gl=CN&ceid=CN%3Azh-Hans" target="_blank" rel="noopener noreferrer">前往 Google 新闻查看 ↗</a></div>`;
      return;
    }
    $("article-list").innerHTML = visible.map(a => {
      const saved = Boolean(favorites[a.id]);
      const link = safeHref(a.url);
      return `<article class="article-card"><div class="card-meta"><span class="category">${esc(a.category || '综合')}</span><span class="dot-sep"></span><time datetime="${esc(a.published_at)}">${fmtDate(a.published_at, a.date_precision === 'day')}</time>${a.origin === '公开报道预置' ? '<span class="dot-sep"></span><span>初始示例</span>' : ''}</div><h3 class="article-title"><a href="${esc(link)}" target="_blank" rel="noopener noreferrer">${esc(a.title)}</a></h3>${a.summary ? `<p class="summary">${esc(a.summary)}</p>` : '<p class="summary">点击查看原始报道。部分 RSS 来源仅提供标题，不提供可靠摘要。</p>'}<div class="card-footer"><span class="card-source">${esc(a.source || '来源未注明')}</span><div class="card-actions"><button class="bookmark-btn ${saved ? 'saved':''}" data-save="${esc(a.id)}" aria-label="${saved ? '取消收藏':'收藏新闻'}" title="${saved ? '取消收藏':'收藏新闻'}"><svg class="icon"><use href="#i-bookmark"/></svg></button><a class="read-link" href="${esc(link)}" target="_blank" rel="noopener noreferrer">看原文 <svg class="icon"><use href="#i-external"/></svg></a></div></div></article>`;
    }).join("");
  }
  function setBanner(message, type="ok") {
    $("data-message").textContent = message;
    $("data-banner").dataset.status = type;
  }
  async function fetchJSON(path) {
    const controller = new AbortController();
    const t = setTimeout(()=>controller.abort(), 12000);
    try { const resp = await fetch(path + '?v=' + Date.now(), {cache:'no-store', signal:controller.signal}); if (!resp.ok) throw Error(`HTTP ${resp.status}`); return await resp.json(); }
    finally {clearTimeout(t);}
  }
  async function refresh() {
    if (location.protocol === "file:" || location.protocol === "about:") {
      state.articles = window.CHAINBRIEF_SEED?.articles || [];
      state.generatedAt = window.CHAINBRIEF_SEED?.generated_at || null;
      state.isPreview = true;
      state.loaded = true;
      setBanner("本地预览：这是 2026年11月2—3日的真实中文新闻示例；上传到网站后将自动更新。", "warn");
      render();
      return;
    }
    setBanner("正在检查新闻数据…");
    try {
      const payload = await fetchJSON("./data/news.json");
      if (!Array.isArray(payload.articles)) throw Error("新闻数据格式无效");
      state.articles = payload.articles;
      state.generatedAt = payload.generated_at;
      state.isPreview = false;
      try {localStorage.setItem(ARCHIVE, JSON.stringify(payload));} catch {}
      try {state.status = await fetchJSON("./data/status.json");} catch {state.status = null;}
      const seeded = state.articles.length > 0 && state.articles.every(a=>a.origin==='公开报道预置');
      if (seeded) {
        setBanner("目前为初始示例新闻；部署完成并运行自动更新后将显示最新中文报道。", "warn");
      } else if (state.generatedAt && daysAgo(state.generatedAt) > 36*3600e3) {
        setBanner("新闻数据已超过36小时未成功更新，请进入「关于」查看诊断。", "warn");
      } else if (!state.articles.length) {
        setBanner("暂未抓到新闻。请进入「关于」查看数据源诊断。", "warn");
      } else {
        setBanner(`新闻数据更新于 ${fmtDate(state.generatedAt)} · 自动聚合中文报道，非人工审核`);
      }
    } catch (e) {
      const archive = getJSON(ARCHIVE, null);
      const base = archive?.articles?.length ? archive : window.CHAINBRIEF_SEED;
      state.articles = Array.isArray(base?.articles) ? base.articles : [];
      state.generatedAt = base?.generated_at || null;
      state.isPreview = true;
      state.status = null;
      setBanner(location.protocol === 'file:' ? '本地预览模式：显示预置新闻；上传网站后才能自动更新。' : '新闻数据暂时不可读取，显示上次保存的新闻。', 'warn');
    }
    state.loaded = true;
    render();
  }
  function init() {
    const now = new Date();
    $("hero-date").textContent = new Intl.DateTimeFormat("zh-CN", {year:'numeric',month:'long',day:'numeric',weekday:'short'}).format(now);
    const theme = localGet('chainbrief-theme') || 'light';
    document.documentElement.dataset.theme = theme;
    $("btn-theme").addEventListener('click',()=>{
      let t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = t;
      try {localStorage.setItem('chainbrief-theme',t);} catch {}
    });
    $("btn-update").addEventListener('click',refresh);
    $("search-input").addEventListener('input',e=>{state.query=e.target.value.trim().toLocaleLowerCase();$("clear-search").hidden=!state.query;render()});
    $("clear-search").addEventListener('click',()=>{$("search-input").value='';state.query='';$("clear-search").hidden=true;render()});
    document.querySelectorAll('.seg').forEach(btn=>btn.addEventListener('click',()=>{state.days=Number(btn.dataset.days);document.querySelectorAll('.seg').forEach(b=>b.classList.toggle('active',b===btn));render()}));
    $("filters").addEventListener('click',e=>{let btn=e.target.closest('button[data-category]'); if(btn){state.category=btn.dataset.category;render()}});
    $("article-list").addEventListener('click',e=>{let btn=e.target.closest('button[data-save]'); if (!btn)return; let id=btn.dataset.save; let article=state.articles.find(a=>a.id===id) || Object.values(favorites).find(a=>a.id===id); if(!article)return; if(favorites[id])delete favorites[id];else favorites[id]=article; try{localStorage.setItem(FAVORITES,JSON.stringify(favorites))}catch{};render()});
    document.querySelectorAll('.nav-item').forEach(btn=>btn.addEventListener('click',()=>{state.page=btn.dataset.page;state.category='全部';state.query='';$("search-input").value='';$("clear-search").hidden=true;render();window.scrollTo({top:0,behavior:'smooth'})}));
    state.articles = window.CHAINBRIEF_SEED?.articles || [];
    state.generatedAt = window.CHAINBRIEF_SEED?.generated_at || null;
    render();
    refresh();
    if (location.protocol.startsWith('http') && 'serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(()=>{});
    document.addEventListener('visibilitychange',()=>{if (!document.hidden && state.loaded && !state.isPreview) refresh()});
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init);else init();
})();

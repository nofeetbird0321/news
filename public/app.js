/* D · progressive visual-journal reader. No framework, no content rewriting. */
(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const readerMemory = new Map();
  const mediaBound = new WeakSet();
  const nextFrame = callback => requestAnimationFrame(callback);
  const safeFocus = element => { if (element?.isConnected) element.focus({preventScroll: true}); };
  function currentTheme() { return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light'; }
  function paintTheme() {
    const dark = currentTheme() === 'dark';
    const button = $('#theme-btn');
    if (button) {
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('aria-label', dark ? '切换为亮色主题' : '切换为暗色主题');
    }
    $('meta[name="theme-color"]')?.setAttribute('content', dark ? '#20241e' : '#fffefa');
  }
  paintTheme();
  $('#theme-btn')?.addEventListener('click', () => {
    const style = document.createElement('style');
    style.textContent = '*,*::before,*::after{transition:none!important}';
    document.head.append(style);
    const next = currentTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('xz.theme', next); } catch {}
    paintTheme();
    void document.documentElement.offsetHeight;
    nextFrame(() => nextFrame(() => style.remove()));
  });

  // Filter the existing static cards; content and native links work without JS.
  const discovery = $('[data-discovery]');
  if (discovery) {
    const grid = $('[data-news-grid]');
    const cards = $$('.news-card', grid);
    const search = $('#story-search');
    const clear = $('[data-clear-search]');
    const empty = $('[data-search-empty]');
    const normalize = value => value.normalize('NFKC').toLocaleLowerCase().trim();
    const index = cards.map(card => normalize(card.dataset.search || ''));
    let kind = 'all', layout = discovery.dataset.defaultView;
    function render(writeURL = true) {
      const terms = normalize(search.value).split(/\s+/).filter(Boolean);
      let count = 0;
      cards.forEach((card, i) => {
        card.hidden = !(kind === 'all' || card.dataset.kind === kind) || !terms.every(term => index[i].includes(term));
        if (!card.hidden) count++;
      });
      grid.dataset.layout = layout;
      grid.classList.toggle('is-filtered', kind !== 'all' || terms.length > 0);
      $$('[data-filter]', discovery).forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === kind)));
      $$('[data-layout]', discovery).forEach(button => button.setAttribute('aria-pressed', String(button.dataset.layout === layout)));
      $('[data-result-count]').textContent = count === cards.length ? `${count} 篇文章 · 最新在前` : `找到 ${count} 篇 · 共 ${cards.length} 篇`;
      clear.hidden = !search.value;
      empty.hidden = count !== 0;
      $('[data-empty-description]').textContent = search.value.trim() ? `试试更短的关键词，或清除「${search.value.trim()}」与类型筛选。` : '这个类型暂时没有文章，试试查看全部内容。';
      if (writeURL) {
        const url = new URL(location.href);
        for (const [key, value] of [['q', search.value.trim()], ['type', kind === 'all' ? '' : kind], ['view', layout === discovery.dataset.defaultView ? '' : layout]]) {
          if (value) url.searchParams.set(key, value); else url.searchParams.delete(key);
        }
        history.replaceState(history.state, '', url.pathname + url.search + url.hash);
      }
    }
    function restore() {
      if (location.pathname.startsWith('/a/')) return;
      const params = new URLSearchParams(location.search);
      search.value = params.get('q') || '';
      kind = ['text', 'video'].includes(params.get('type')) ? params.get('type') : 'all';
      layout = ['journal', 'list'].includes(params.get('view')) ? params.get('view') : discovery.dataset.defaultView;
      render(false);
    }
    search.addEventListener('input', () => render());
    clear.addEventListener('click', () => { search.value = ''; render(); search.focus(); });
    $$('[data-filter]', discovery).forEach(button => button.addEventListener('click', () => { kind = button.dataset.filter; render(); }));
    $$('[data-layout]', discovery).forEach(button => button.addEventListener('click', () => { layout = button.dataset.layout; render(); }));
    $('[data-reset-filters]').addEventListener('click', () => { kind = 'all'; search.value = ''; render(); search.focus(); });
    window.addEventListener('popstate', restore);
    discovery.hidden = false;
    restore();
  }
  function suspendMedia(root) {
    $$('video,audio', root).forEach(media => { try { media.pause(); } catch {} });
    $$('iframe[src]', root).forEach(frame => {
      frame.dataset.pausedSrc = frame.getAttribute('src');
      frame.removeAttribute('src');
    });
  }
  function resumeEmbeds(root) {
    $$('iframe[data-paused-src]', root).forEach(frame => {
      frame.setAttribute('src', frame.dataset.pausedSrc);
      delete frame.dataset.pausedSrc;
    });
  }
  function bindMedia(root) {
    $$('img,video,audio', root).forEach(media => {
      if (mediaBound.has(media)) return;
      mediaBound.add(media);
      const figure = media.closest('.media-figure');
      const notice = figure && $('.media-error', figure);
      let bufferingTimer = null, requestedPlayback = false;
      function clearBuffering() {
        clearTimeout(bufferingTimer); bufferingTimer = null;
        if (notice?.dataset.mediaState === 'buffering') notice.hidden = true;
      }
      const failed = () => {
        requestedPlayback = false; clearBuffering();
        const cover = media.closest('[data-cover]');
        if (cover) cover.closest('.news-card')?.classList.add('media-failed');
        if (figure) {
          if (notice) {
            notice.textContent = /^(VIDEO|AUDIO)$/.test(media.tagName)
              ? '此处暂时无法播放，请通过下方原文链接观看或收听。'
              : '图片未能载入，请通过下方原文链接查看。';
            notice.dataset.mediaState = 'failed'; notice.hidden = false;
          }
          media.hidden = true;
          if (media.tagName === 'VIDEO') {
            const poster = $('[data-video-fallback]', figure);
            if (poster) poster.hidden = false;
          }
        }
      };
      media.addEventListener('error', failed);
      if (/^(VIDEO|AUDIO)$/.test(media.tagName)) {
        const armBuffering = () => {
          if (!requestedPlayback || bufferingTimer || media.hidden) return;
          bufferingTimer = setTimeout(() => {
            bufferingTimer = null;
            if (notice && figure.isConnected && requestedPlayback && !media.hidden && !media.closest('[hidden]')) {
              notice.textContent = '外部媒体暂未能继续播放，可通过下方原文链接观看或收听。';
              notice.dataset.mediaState = 'buffering'; notice.hidden = false;
            }
          }, 10000);
        };
        media.addEventListener('play', () => { requestedPlayback = true; armBuffering(); });
        media.addEventListener('waiting', armBuffering);
        media.addEventListener('stalled', armBuffering);
        media.addEventListener('playing', clearBuffering);
        ['pause', 'ended', 'emptied'].forEach(name => media.addEventListener(name, () => {
          requestedPlayback = false; clearBuffering();
        }));
      }
      if (media.tagName === 'IMG' && media.complete && media.naturalWidth === 0) failed();
    });
  }
  bindMedia(document);

  // Accessible manual-activation tabs; no JS leaves both complete sections and links intact.
  function enhanceReader(article, scroller, onView) {
    const tablist = $('[data-tabs]', article);
    if (!tablist) return null;
    const tabs = $$('[data-view]', tablist);
    const panels = $$('[data-reader-panel]', article);
    const id = article.dataset.articleId;
    const memory = readerMemory.get(id) || {positions: {}, view: 'rewrite'};
    readerMemory.set(id, memory);
    const isWindow = scroller === window;
    const getTop = () => isWindow ? window.scrollY : scroller.scrollTop;
    const setTop = value => { if (isWindow) window.scrollTo(0, value); else scroller.scrollTop = value; };
    const toolbar = tablist.closest('.reader-tabs');
    const position = $('.reading-position', toolbar);
    const progress = $('progress', toolbar);
    const percent = $('[data-reading-percent]', toolbar);
    let progressFrame = null;
    function updateProgress() {
      progressFrame = null;
      if (!article.isConnected || !progress) return;
      const panel = panels.find(item => !item.hidden);
      if (!panel) return;
      const viewport = isWindow ? window.innerHeight : scroller.clientHeight;
      const origin = isWindow ? 0 : scroller.getBoundingClientRect().top;
      const top = panel.getBoundingClientRect().top - origin;
      const distance = panel.getBoundingClientRect().height - viewport + toolbar.offsetHeight;
      const value = distance <= 0 ? (top < viewport ? 100 : 0) : Math.round(Math.max(0, Math.min(1, (toolbar.offsetHeight - top) / distance)) * 100);
      progress.value = value;
      percent.textContent = value + '%';
    }
    function scheduleProgress() { if (progressFrame == null) progressFrame = nextFrame(updateProgress); }
    if (position) position.hidden = false;
    scroller.addEventListener('scroll', scheduleProgress, {passive: true});
    window.addEventListener('resize', scheduleProgress);
    article.addEventListener('load', scheduleProgress, true);
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(scheduleProgress) : null;
    panels.forEach(panel => observer?.observe(panel));
    const toolbarTop = () => Math.max(0, toolbar.getBoundingClientRect().top + getTop() - (isWindow ? 0 : scroller.getBoundingClientRect().top));
    let view = null, generation = 0;
    article.classList.add('reader-enhanced');
    tablist.setAttribute('role', 'tablist');
    tabs.forEach(tab => {
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-controls', tab.dataset.view);
    });
    panels.forEach(panel => {
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('tabindex', '0');
      panel.setAttribute('aria-labelledby', 'tab-' + panel.dataset.readerPanel);
    });
    function remember() { if (view) memory.positions[view] = getTop(); memory.view = view; }
    function show(next, {initial = false, updateURL = true} = {}) {
      if (!['rewrite', 'original'].includes(next) || view === next) return;
      const thisGeneration = ++generation;
      if (view) {
        remember();
        const old = panels.find(panel => panel.dataset.readerPanel === view);
        if (old) suspendMedia(old);
      }
      view = next;
      memory.view = next;
      panels.forEach(panel => {
        panel.hidden = panel.dataset.readerPanel !== next;
        if (!panel.hidden) resumeEmbeds(panel);
        else suspendMedia(panel);
      });
      tabs.forEach(tab => {
        const selected = tab.dataset.view === next;
        tab.setAttribute('aria-selected', String(selected));
        tab.setAttribute('tabindex', selected ? '0' : '-1');
      });
      if (updateURL) onView(next);
      const saved = memory.positions[next];
      // First rewrite starts at its title; first original starts at the visible tab bar.
      if (!initial || next === 'original' || saved != null) {
        nextFrame(() => {
          if (thisGeneration === generation && article.isConnected) setTop(saved ?? toolbarTop());
        });
      }
      scheduleProgress();
    }
    tabs.forEach(tab => tab.addEventListener('click', event => {
      if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
      event.preventDefault();
      show(tab.dataset.view);
    }));
    tablist.addEventListener('keydown', event => {
      const index = tabs.indexOf(document.activeElement);
      if (index < 0) return;
      if (event.key === ' ') { event.preventDefault(); show(tabs[index].dataset.view); return; }
      let target = null;
      if (event.key === 'ArrowRight') target = tabs[(index + 1) % tabs.length];
      if (event.key === 'ArrowLeft') target = tabs[(index - 1 + tabs.length) % tabs.length];
      if (event.key === 'Home') target = tabs[0];
      if (event.key === 'End') target = tabs.at(-1);
      if (target) { event.preventDefault(); safeFocus(target); }
    });
    show(location.hash === '#original' ? 'original' : 'rewrite', {initial: true, updateURL: false});
    bindMedia(article);
    return {show, remember, dispose() {
      scroller.removeEventListener('scroll', scheduleProgress);
      window.removeEventListener('resize', scheduleProgress);
      article.removeEventListener('load', scheduleProgress, true);
      observer?.disconnect();
      if (progressFrame != null) cancelAnimationFrame(progressFrame);
    }};
  }
  function replaceViewURL(view) {
    const url = new URL(location.href);
    url.hash = view === 'original' ? 'original' : 'rewrite';
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
  }
  const directArticle = $('.site-main > [data-article-id]');
  if (directArticle) {
    const direct = enhanceReader(directArticle, window, replaceViewURL);
    window.addEventListener('hashchange', () => direct?.show(location.hash === '#original' ? 'original' : 'rewrite', {updateURL: false}));
    window.addEventListener('pagehide', () => { direct?.remember(); suspendMedia(directArticle); });
  }

  const sheet = $('#reader-sheet');
  const grid = $('[data-news-grid]');
  if (!sheet || !grid) return;
  const scroll = $('.sheet-scroll', sheet);
  const closeButton = $('[data-close-sheet]', sheet);
  const pageRoots = $$('.site-header,.site-main,.site-footer');
  const listTitle = document.title;
  const listCanonical = $('link[rel="canonical"]')?.href;
  const cache = new Map();
  let active = null, controller = null, viewController = null, sequence = 0;
  const canAnimate = !window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  history.scrollRestoration = 'manual';
  const sheetState = () => history.state?.xzSheet;
  const safePath = path => /^\/a\/[a-z0-9-]+\/?$/.test(path);
  const prefetching = new Map();
  const readerURLs = new Map($$('[data-open-reader]', grid).map(a => [new URL(a.href, location.href).pathname, a.dataset.readerSrc]));
  const requestURL = path => readerURLs.get(path) || path;
  // Warm only a link the reader shows intent to open; never preload media or all stories.
  function prefetchArticle(event) {
    if (event.type === 'pointerover' && event.pointerType === 'touch') return;
    const connection = navigator.connection;
    if (connection?.saveData || /(^|-)2g$/.test(connection?.effectiveType || '')) return;
    const anchor = event.target.closest?.('[data-open-reader]');
    if (!anchor) return;
    const url = new URL(anchor.href, location.href), path = url.pathname;
    if (url.origin !== location.origin || !safePath(path) || cache.has(path) || prefetching.has(path) || prefetching.size >= 2) return;
    const abort = new AbortController();
    const timer = setTimeout(() => abort.abort(), 8000);
    const promise = fetch(requestURL(path), {signal: abort.signal, priority: 'low', headers: {'Accept': 'text/html'}})
      .then(response => { if (!response.ok) throw new Error('Prefetch failed'); return response.text(); })
      .then(html => {
        const raw = new DOMParser().parseFromString(html, 'text/html').querySelector('[data-article-id]');
        if (!raw || '/a/' + raw.dataset.articleId !== path.replace(/\/$/, '')) return null;
        cache.set(path, html);
        if (cache.size > 12) cache.delete(cache.keys().next().value);
        return html;
      }).catch(() => null).finally(() => { clearTimeout(timer); if (prefetching.get(path)?.promise === promise) prefetching.delete(path); });
    prefetching.set(path, {promise, abort});
  }
  grid.addEventListener('pointerover', prefetchArticle);
  grid.addEventListener('focusin', prefetchArticle);
  grid.addEventListener('pointerdown', prefetchArticle);
  async function readyPrefetch(path) {
    const pending = prefetching.get(path);
    if (!pending) return null;
    let timer;
    try {
      // A click is foreground work. Do not inherit an eight-second speculative
      // request deadline when that request is queued or stalled on a slow link.
      const ready = await Promise.race([pending.promise, new Promise(resolve => { timer = setTimeout(() => resolve(null), 120); })]);
      if (!ready) pending.abort.abort();
      return ready;
    } finally { clearTimeout(timer); }
  }
  function togglePageInert(value) { pageRoots.forEach(element => { element.inert = value; }); }
  function showSheet(keyboard) {
    if (sheet.open) return;
    document.body.classList.add('sheet-open');
    togglePageInert(true);
    if (typeof sheet.showModal === 'function') sheet.showModal();
    else { sheet.setAttribute('open', ''); sheet.classList.add('sheet-fallback'); sheet.setAttribute('role', 'dialog'); sheet.setAttribute('aria-modal', 'true'); }
    if (!keyboard && canAnimate && typeof sheet.animate === 'function') {
      sheet.animate([{transform: 'translateY(16px)', opacity: .8}, {transform: 'translateY(0)', opacity: 1}], {duration: 180, easing: 'cubic-bezier(.23,1,.32,1)'});
    }
    safeFocus(closeButton);
  }
  function loading() {
    scroll.setAttribute('aria-busy', 'true');
    scroll.innerHTML = '<div class="sheet-status" role="status"><p>正在打开文章…</p><div aria-hidden="true"><div class="skeleton-title"></div><div class="skeleton-title short"></div><div class="skeleton-line"></div><div class="skeleton-line"></div><div class="skeleton-line short"></div></div></div>';
    scroll.scrollTop = 0;
  }
  function errorState(path, sourceURL) {
    scroll.removeAttribute('aria-busy');
    scroll.replaceChildren();
    const status = document.createElement('section'); status.className = 'sheet-status'; status.setAttribute('role', 'alert');
    const title = document.createElement('h2'); title.textContent = '文章暂时未能打开';
    const description = document.createElement('p'); description.textContent = '选刊和阅读位置都还在。可以重试，或打开独立文章页。';
    const retry = document.createElement('button'); retry.type = 'button'; retry.className = 'retry-button'; retry.textContent = '重试'; retry.addEventListener('click', () => loadArticle(path, sourceURL));
    const link = document.createElement('a'); link.href = path; link.textContent = '独立文章页 ↗';
    status.append(title, description, retry, link);
    if (sourceURL) { const source = document.createElement('a'); source.href = sourceURL; source.target = '_blank'; source.rel = 'noopener noreferrer'; source.textContent = '去原文 ↗'; status.append(source); }
    scroll.append(status);
  }
  async function loadArticle(path, sourceURL = '') {
    if (!safePath(path)) return;
    const ownSequence = ++sequence;
    controller?.abort();
    viewController?.remember(); viewController?.dispose(); viewController = null;
    suspendMedia(scroll);
    loading();
    controller = new AbortController();
    const signal = controller.signal;
    const timeout = setTimeout(() => controller?.signal === signal && controller.abort(), 12000);
    try {
      let html = cache.get(path) || await readyPrefetch(path);
      if (ownSequence !== sequence || !active) return;
      if (signal.aborted) throw new Error('Article load timed out');
      if (!html) {
        const response = await fetch(requestURL(path), {signal, priority: 'high', headers: {'Accept': 'text/html'}});
        if (!response.ok) throw new Error('HTTP ' + response.status);
        html = await response.text();
      }
      if (ownSequence !== sequence || !active) return;
      const parsed = new DOMParser().parseFromString(html, 'text/html');
      const raw = $('[data-article-id]', parsed);
      if (!raw || '/a/' + raw.dataset.articleId !== path.replace(/\/$/, '')) throw new Error('Article mismatch');
      cache.set(path, html);
      if (cache.size > 12) cache.delete(cache.keys().next().value);
      const article = document.importNode(raw, true);
      // Set panel visibility before attaching media to the live document.
      viewController = enhanceReader(article, scroll, view => {
        replaceViewURL(view);
        $('[data-sheet-permalink]', sheet).href = location.pathname + location.search + location.hash;
      });
      scroll.replaceChildren(article);
      scroll.removeAttribute('aria-busy');
      document.title = parsed.title;
      $('link[rel="canonical"]')?.setAttribute('href', location.origin + path);
      $('[data-sheet-permalink]', sheet).href = path + location.hash;
      nextFrame(() => { if (ownSequence === sequence) bindMedia(article); });
    } catch (error) {
      if (ownSequence !== sequence || !active) return;
      errorState(path, sourceURL);
    } finally { clearTimeout(timeout); }
  }
  function openFromCard(anchor, keyboard) {
    const url = new URL(anchor.href, location.href);
    if (url.origin !== location.origin || !safePath(url.pathname)) return false;
    const state = {path: url.pathname, listURL: location.pathname + location.search + location.hash, listY: window.scrollY, focusId: anchor.id, sourceURL: anchor.dataset.sourceUrl || ''};
    history.replaceState({...history.state, xzList: {url: state.listURL, y: state.listY, focusId: state.focusId}}, '', location.href);
    history.pushState({xzSheet: state}, '', url.pathname);
    active = state;
    $('[data-sheet-permalink]', sheet).href = url.pathname;
    showSheet(keyboard);
    loadArticle(state.path, state.sourceURL);
    return true;
  }
  function finishClose() {
    const previous = active;
    ++sequence;
    controller?.abort(); controller = null;
    viewController?.remember(); viewController?.dispose(); viewController = null;
    suspendMedia(scroll);
    if (typeof sheet.close === 'function' && sheet.open) sheet.close();
    sheet.removeAttribute('open'); sheet.classList.remove('sheet-fallback');
    togglePageInert(false);
    document.body.classList.remove('sheet-open');
    scroll.replaceChildren(); scroll.removeAttribute('aria-busy');
    active = null;
    document.title = listTitle;
    if (listCanonical) $('link[rel="canonical"]')?.setAttribute('href', listCanonical);
    nextFrame(() => {
      if (active) return;
      window.scrollTo(0, previous?.listY ?? history.state?.xzList?.y ?? 0);
      safeFocus(document.getElementById(previous?.focusId || history.state?.xzList?.focusId || '') || $('.edition-line h1'));
    });
  }
  function requestClose() {
    if (!active) return;
    if (sheetState()) history.back(); else finishClose();
  }
  grid.addEventListener('click', event => {
    const anchor = event.target.closest('[data-open-reader]');
    if (!anchor || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey || anchor.target === '_blank' || anchor.hasAttribute('download')) return;
    if (openFromCard(anchor, event.detail === 0)) event.preventDefault();
  });
  closeButton.addEventListener('click', requestClose);
  sheet.addEventListener('cancel', event => { event.preventDefault(); requestClose(); });
  sheet.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); requestClose(); return; }
    if (event.key !== 'Tab') return;
    const focusables = $$('a[href],button:not(:disabled),[tabindex="0"],video[controls],audio[controls]', sheet).filter(element => !element.closest('[hidden]'));
    const first = focusables[0], last = focusables.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === sheet)) { event.preventDefault(); safeFocus(last); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); safeFocus(first); }
  });
  window.addEventListener('popstate', () => {
    const state = sheetState();
    if (state && safePath(state.path)) {
      active = state;
      showSheet(true);
      loadArticle(state.path, state.sourceURL);
    } else if (active) finishClose();
  });
  window.addEventListener('pagehide', () => { viewController?.remember(); suspendMedia(scroll); controller?.abort(); });
})();

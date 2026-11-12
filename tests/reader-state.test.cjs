/* State/DOM tests, not browser screenshots or layout measurements. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM, VirtualConsole} = require('jsdom');
const root = path.join(__dirname, '..');
const script = fs.readFileSync(path.join(root, 'public/app.js'), 'utf8');
const articles = JSON.parse(fs.readFileSync(path.join(root, 'public/articles.json'), 'utf8'));
const articleCount = articles.length;
// Corpus-independent ids: newest three articles by site ingest order.
const [ID_A, ID_B, ID_C] = articles.map(a => a.id);
const EMBER_ID = (articles.find(a => /Ember/.test(a.title + ' ' + a.dek)) || {}).id;
const SITE = 'https://news.nofeetbird.tech';
const homeHTML = fs.readFileSync(path.join(root, 'public/index.html'), 'utf8');
const VIDEO_ID = (homeHTML.match(/id="story-([a-z0-9-]+)" data-kind="video"/) || [])[1];
const pageWith = needle => articles.map(a => a.id).find(id => fs.readFileSync(path.join(root, 'public/a', id + '.html'), 'utf8').includes(needle));
const NATIVE_VIDEO_ID = pageWith('<video');
const EMBED_ID = pageWith('<iframe');
const html = name => fs.readFileSync(path.join(root, 'public', name), 'utf8');
const responseHTML = url => html(url.slice(1) + (url.endsWith('.html') ? '' : '.html'));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(predicate, message) {
  const end = Date.now() + 1400;
  while (!predicate()) { if (Date.now() > end) throw new Error('Timed out: ' + message); await pause(10); }
}
async function frames() { await pause(45); }
function setup({page = 'index.html', url = SITE + '/', fetcher, blockedStorage = false, nativeDialog = true} = {}) {
  const errors = [], requests = [], pauses = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', error => errors.push(error.message));
  const dom = new JSDOM(html(page), {url, runScripts: 'outside-only', pretendToBeVisual: true, virtualConsole});
  const w = dom.window, d = w.document;
  w.scrollTo = (x, y) => Object.defineProperty(w, 'scrollY', {configurable: true, value: y});
  w.matchMedia = () => ({matches: false});
  w.HTMLMediaElement.prototype.pause = function () { pauses.push(this); };
  w.HTMLDialogElement.prototype.showModal = nativeDialog ? function () { this.setAttribute('open', ''); } : undefined;
  w.HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  if (blockedStorage) Object.defineProperty(w, 'localStorage', {get() { throw new Error('Storage blocked'); }});
  w.fetch = async (url, options) => {
    requests.push({url, options});
    if (fetcher) return fetcher(url, options, requests.length);
    return {ok: true, text: async () => responseHTML(url)};
  };
  w.eval(script);
  const $ = selector => d.querySelector(selector);
  const click = (element, options = {}) => {
    const e = new w.MouseEvent('click', {bubbles: true, cancelable: true, button: 0, detail: 1, ...options});
    element.dispatchEvent(e); return e;
  };
  return {dom, w, d, $, click, requests, pauses, errors};
}

test('card opens a real clean deep link; only rewrite is initially shown', async t => {
  const s = setup(); t.after(() => s.dom.window.close());
  const anchor = s.$('[data-open-reader]'); const event = s.click(anchor);
  assert.equal(event.defaultPrevented, true);
  assert.equal(s.w.location.pathname, anchor.getAttribute('href'));
  assert.equal(s.$('#reader-sheet').open, true);
  await until(() => s.$('#reader-sheet [data-article-id]'), 'article');
  assert.equal(s.requests.length, 1);
  assert.equal(s.$('#rewrite').hidden, false);
  assert.equal(s.$('#original').hidden, true);
  assert.equal(s.$('[data-tabs]').getAttribute('role'), 'tablist');
  assert.equal(s.$('[data-view="rewrite"]').getAttribute('aria-selected'), 'true');
  assert.equal(s.$('.site-main').inert, true);
  assert.deepEqual(s.errors, []);
});

test('tabs retain independent positions and original has a shareable fragment', async t => {
  const s = setup(); t.after(() => s.dom.window.close()); s.click(s.$('#read-' + ID_A));
  await until(() => s.$('#reader-sheet [data-article-id]'), 'article'); await frames();
  const scroller = s.$('.sheet-scroll'); scroller.scrollTop = 311;
  s.click(s.$('[data-view="original"]')); await frames(); scroller.scrollTop = 81;
  assert.equal(s.w.location.hash, '#original');
  assert.equal(s.$('#rewrite').hidden, true);
  assert.equal(s.$('#original').hidden, false);
  assert.match(s.$('[data-sheet-permalink]').href, /#original$/);
  s.click(s.$('[data-view="rewrite"]')); await frames(); assert.equal(scroller.scrollTop, 311);
  s.click(s.$('[data-view="original"]')); await frames(); assert.equal(scroller.scrollTop, 81);
  assert.ok(s.$('#original .prose').textContent.trim().length > 0);
});

test('close/back restores list scroll and focus; Forward reopens the cached reader', async t => {
  const s = setup(); t.after(() => s.dom.window.close());
  const anchor = s.$('#read-' + ID_B); anchor.focus(); s.w.scrollTo(0, 730);
  s.click(anchor); await until(() => s.$('#reader-sheet [data-article-id]'), 'open');
  s.click(s.$('[data-view="original"]')); await frames(); s.$('.sheet-scroll').scrollTop = 117;
  s.click(s.$('[data-close-sheet]'));
  await until(() => !s.$('#reader-sheet').open, 'close'); await frames();
  assert.equal(s.w.location.pathname, '/'); assert.equal(s.w.scrollY, 730);
  assert.equal(s.d.activeElement, anchor); assert.equal(s.$('.site-main').inert, false);
  assert.equal(s.d.title, '新知 · AI、Web3 与数据的一手长文');
  s.w.history.forward(); await until(() => s.$('#reader-sheet [data-article-id]'), 'forward'); await frames();
  assert.equal(s.w.location.pathname, '/a/' + ID_B);
  assert.equal(s.$('#original').hidden, false); assert.equal(s.$('.sheet-scroll').scrollTop, 117);
  assert.equal(s.requests.length, 1);
});

test('Escape and fallback focus loop keep the reader escapable', async t => {
  const s = setup(); t.after(() => s.dom.window.close()); s.click(s.$('[data-open-reader]'));
  await until(() => s.$('#reader-sheet [data-article-id]'), 'reader');
  const close = s.$('[data-close-sheet]'); close.focus();
  close.dispatchEvent(new s.w.KeyboardEvent('keydown', {key: 'Tab', shiftKey: true, bubbles: true, cancelable: true}));
  assert.notEqual(s.d.activeElement, close);
  close.dispatchEvent(new s.w.KeyboardEvent('keydown', {key: 'Escape', bubbles: true, cancelable: true}));
  await until(() => !s.$('#reader-sheet').open, 'escape');
});

test('modified clicks remain native links and do not fetch', t => {
  const s = setup(); t.after(() => s.dom.window.close());
  const event = s.click(s.$('[data-open-reader]'), {ctrlKey: true});
  assert.equal(event.defaultPrevented, false); assert.equal(s.requests.length, 0); assert.equal(s.$('#reader-sheet').open, false);
});

test('failed fetch offers retry, independent route and original; retry recovers', async t => {
  const s = setup({fetcher: async (url, options, n) => n === 1 ? {ok: false, status: 503} : {ok: true, text: async () => responseHTML(url)}});
  t.after(() => s.dom.window.close()); s.click(s.$('[data-open-reader]'));
  await until(() => s.$('.retry-button'), 'error');
  assert.match(s.$('.sheet-status').textContent, /独立文章页/);
  assert.match(s.$('.sheet-status').textContent, /去原文/);
  assert.equal(s.$('.sheet-scroll').hasAttribute('aria-busy'), false);
  s.click(s.$('.retry-button')); await until(() => s.$('#reader-sheet [data-article-id]'), 'retry');
  assert.equal(s.requests.length, 2);
});

test('closing aborts a pending fetch and late response cannot reopen the sheet', async t => {
  let resolve;
  const s = setup({fetcher: url => new Promise(r => { resolve = () => r({ok: true, text: async () => responseHTML(url)}); })});
  t.after(() => s.dom.window.close()); s.click(s.$('[data-open-reader]'));
  assert.match(s.$('.sheet-status').textContent, /正在打开/);
  s.click(s.$('[data-close-sheet]')); await until(() => !s.$('#reader-sheet').open, 'close pending');
  assert.equal(s.requests[0].options.signal.aborted, true); resolve(); await frames();
  assert.equal(s.$('#reader-sheet').open, false); assert.equal(s.$('#reader-sheet [data-article-id]'), null);
  assert.equal(s.w.location.pathname, '/');
});

test('media errors have source fallbacks; media is paused when changing panels', {skip: VIDEO_ID ? false : '当前内容中没有含视频的文章'}, async t => {
  const s = setup(); t.after(() => s.dom.window.close());
  const cover = s.$('[data-cover] img'); cover.dispatchEvent(new s.w.Event('error'));
  assert.equal(cover.closest('.news-card').classList.contains('media-failed'), true);
  assert.ok(cover.closest('.news-card').querySelector('.cover-error-link').href.startsWith('https://'));
  s.click(s.$('#read-' + VIDEO_ID)); await until(() => s.$('#reader-sheet video'), 'video');
  s.click(s.$('[data-view="original"]')); await frames();
  const video = s.$('#original video'); const before = s.pauses.length;
  video.dispatchEvent(new s.w.Event('error'));
  assert.equal(video.hidden, true); assert.equal(video.closest('figure').querySelector('.media-error').hidden, false);
  s.click(s.$('[data-view="rewrite"]')); assert.ok(s.pauses.length > before);
});

test('hidden original embeds are unloaded and restored without autoplay', {skip: EMBED_ID ? false : '当前内容中没有含嵌入播放器的文章'}, async t => {
  const s = setup(); t.after(() => s.dom.window.close()); s.click(s.$('#read-' + EMBED_ID));
  await until(() => s.$('#reader-sheet iframe'), 'embed');
  const iframe = s.$('#original iframe'); assert.equal(iframe.hasAttribute('src'), false); assert.ok(iframe.dataset.pausedSrc);
  s.click(s.$('[data-view="original"]')); assert.match(iframe.src, /youtube-nocookie/); assert.ok(!iframe.src.includes('autoplay=1'));
  s.click(s.$('[data-view="rewrite"]')); assert.equal(iframe.hasAttribute('src'), false);
});

test('standalone deep route upgrades tabs; arrow keys only move focus', async t => {
  const s = setup({page: 'a/' + ID_C + '.html', url: SITE + '/a/' + ID_C + '#original'});
  t.after(() => s.dom.window.close()); await frames();
  assert.equal(s.$('#original').hidden, false); assert.equal(s.$('#rewrite').hidden, true); assert.equal(s.requests.length, 0);
  const original = s.$('[data-view="original"]'); original.focus();
  original.dispatchEvent(new s.w.KeyboardEvent('keydown', {key: 'ArrowLeft', bubbles: true, cancelable: true}));
  assert.equal(s.d.activeElement, s.$('[data-view="rewrite"]')); assert.equal(s.$('#original').hidden, false);
  s.click(s.$('[data-view="rewrite"]')); await frames(); s.w.scrollTo(0, 450);
  s.click(original); await frames(); s.w.scrollTo(0, 620);
  s.click(s.$('[data-view="rewrite"]')); await frames(); assert.equal(s.w.scrollY, 450);
});

test('blocked storage does not break theme switching', t => {
  const s = setup({blockedStorage: true}); t.after(() => s.dom.window.close());
  s.click(s.$('#theme-btn')); assert.equal(s.d.documentElement.dataset.theme, 'dark');
  assert.equal(s.$('#theme-btn').getAttribute('aria-pressed'), 'true');
  assert.equal(s.$('meta[name="theme-color"]').content, '#20241e'); assert.deepEqual(s.errors, []);
});

test('unexpected HTML cannot be displayed as the requested article', async t => {
  const s = setup({fetcher: async () => ({ok: true, text: async () => html('a/' + ID_B + '.html')})});
  t.after(() => s.dom.window.close()); s.click(s.$('#read-' + ID_A));
  await until(() => s.$('.retry-button'), 'article mismatch'); assert.equal(s.$('#reader-sheet [data-article-id]'), null);
});


test('missing native dialog support has an accessible closeable fallback', async t => {
  const s = setup({nativeDialog: false}); t.after(() => s.dom.window.close()); s.click(s.$('[data-open-reader]'));
  await until(() => s.$('#reader-sheet [data-article-id]'), 'fallback');
  assert.equal(s.$('#reader-sheet').classList.contains('sheet-fallback'), true);
  assert.equal(s.$('#reader-sheet').getAttribute('aria-modal'), 'true');
  assert.equal(s.$('#reader-sheet').getAttribute('role'), 'dialog');
  s.click(s.$('[data-close-sheet]')); await until(() => !s.$('#reader-sheet').open, 'fallback close');
});

test('all generated HTML parses without HTML5 errors; CSS parses without runtime style errors', t => {
  const parse5 = require('parse5');
  const files = fs.readdirSync(path.join(root, 'public')).filter(f => f.endsWith('.html')).map(f => path.join(root, 'public', f));
  files.push(...fs.readdirSync(path.join(root, 'public/a')).filter(f => f.endsWith('.html')).map(f => path.join(root, 'public/a', f)));
  for (const file of files) { const errors = []; parse5.parse(fs.readFileSync(file, 'utf8'), {onParseError: error => errors.push(error)}); assert.deepEqual(errors, [], file); }
  const errors = []; const vc = new VirtualConsole(); vc.on('jsdomError', error => errors.push(error.message));
  const dom = new JSDOM('<!doctype html><style>' + html('app.css') + '</style>', {virtualConsole: vc});
  t.after(() => dom.window.close()); assert.deepEqual(errors, []); assert.ok(dom.window.document.styleSheets[0].cssRules.length > 100);
});


test('the same native video is in rewrite and original; both pause on hide/close', {skip: NATIVE_VIDEO_ID ? false : '当前内容中没有含原生视频的文章'}, async t => {
  const s = setup(); t.after(() => s.dom.window.close()); s.click(s.$('#read-' + NATIVE_VIDEO_ID));
  await until(() => s.$('#rewrite video'), 'rewrite video');
  const rewrite = s.$('#rewrite video'), original = s.$('#original video');
  assert.equal(rewrite.src, original.src); assert.equal(rewrite.preload, 'none'); assert.equal(rewrite.autoplay, false);
  if (rewrite.dataset.originalPoster) { assert.match(rewrite.poster, /\/media\//); assert.match(rewrite.dataset.originalPoster, /^https:/); }
  else assert.equal(rewrite.hasAttribute('poster'), false); // poster is optional; never invented
  const before = s.pauses.length; s.click(s.$('[data-view="original"]'));
  assert.ok(s.pauses.slice(before).includes(rewrite));
  const next = s.pauses.length; s.click(s.$('[data-close-sheet]'));
  await until(() => !s.$('#reader-sheet').open, 'close');
  assert.ok(s.pauses.slice(next).includes(original));
});

test('rewrite embeds unload when hidden just like original embeds', {skip: EMBED_ID ? false : '当前内容中没有含嵌入播放器的文章'}, async t => {
  const s = setup(); t.after(() => s.dom.window.close()); s.click(s.$('#read-' + EMBED_ID));
  await until(() => s.$('#rewrite iframe'), 'rewrite iframe');
  const rewrite = s.$('#rewrite iframe'), original = s.$('#original iframe');
  assert.match(rewrite.src, /youtube-nocookie/); assert.equal(original.hasAttribute('src'), false);
  s.click(s.$('[data-view="original"]'));
  assert.equal(rewrite.hasAttribute('src'), false); assert.match(original.src, /youtube-nocookie/);
  s.click(s.$('[data-close-sheet]')); await until(() => !s.$('#reader-sheet').open, 'close embeds');
  assert.equal(original.hasAttribute('src'), false);
});

test('user-requested stalled media gets honest recovery and clears on playback/pause', {skip: NATIVE_VIDEO_ID ? false : '当前内容中没有含原生视频的文章'}, async t => {
  const s = setup({page: 'a/' + NATIVE_VIDEO_ID + '.html', url: SITE + '/a/' + NATIVE_VIDEO_ID});
  t.after(() => s.dom.window.close());
  const timers = new Map(); let nextId = 1000000;
  const realSet = s.w.setTimeout.bind(s.w), realClear = s.w.clearTimeout.bind(s.w);
  s.w.setTimeout = (cb, ms, ...args) => { if (ms === 10000) { const id = ++nextId; timers.set(id, cb); return id; } return realSet(cb, ms, ...args); };
  s.w.clearTimeout = id => { if (timers.has(id)) timers.delete(id); else realClear(id); };
  const video = s.$('#rewrite video'), figure = video.closest('figure'), notice = figure.querySelector('.media-error');
  assert.equal(notice.hidden, true); video.dispatchEvent(new s.w.Event('waiting')); assert.equal(timers.size, 0);
  video.dispatchEvent(new s.w.Event('play')); video.dispatchEvent(new s.w.Event('waiting')); assert.equal(timers.size, 1);
  const [id, callback] = [...timers][0]; timers.delete(id); callback();
  assert.equal(notice.hidden, false); assert.equal(notice.dataset.mediaState, 'buffering'); assert.equal(video.hidden, false);
  assert.match(notice.textContent, /暂未能继续播放/);
  video.dispatchEvent(new s.w.Event('playing')); assert.equal(notice.hidden, true);
  video.dispatchEvent(new s.w.Event('waiting')); assert.equal(timers.size, 1);
  video.dispatchEvent(new s.w.Event('pause')); assert.equal(timers.size, 0);
  video.dispatchEvent(new s.w.Event('error')); assert.equal(video.hidden, true);
  const fallback = figure.querySelector('[data-video-fallback]'); // only rendered when the source has a poster
  if (video.dataset.originalPoster) assert.equal(fallback.hidden, false); else assert.equal(fallback, null);
  assert.equal(notice.dataset.mediaState, 'failed'); assert.match(notice.textContent, /暂时无法播放/);
  assert.equal(figure.querySelector('figcaption a').href, articles.find(a => a.id === NATIVE_VIDEO_ID).source_url);
});

test('discovery combines case-insensitive search and type, with a recoverable empty state', t => {
  const s = setup(); t.after(() => s.dom.window.close());
  const search = s.$('#story-search');
  search.value = 'EMBER'; search.dispatchEvent(new s.w.Event('input', {bubbles: true}));
  assert.equal(s.d.querySelectorAll('.news-card:not([hidden])').length, 1);
  assert.match(s.$('.news-card:not([hidden])').textContent, /Ember/);
  s.click(s.$('[data-filter="video"]'));
  assert.equal(s.d.querySelectorAll('.news-card:not([hidden])').length, 0);
  assert.equal(s.$('[data-search-empty]').hidden, false);
  assert.match(s.$('[data-empty-description]').textContent, /EMBER/);
  s.click(s.$('[data-reset-filters]'));
  assert.equal(s.d.querySelectorAll('.news-card:not([hidden])').length, articleCount);
  assert.equal(s.$('[data-search-empty]').hidden, true);
  assert.equal(s.d.activeElement, search);
  assert.equal(s.w.location.search, '');
});

test('query and layout deep links survive a reader round trip and Forward', async t => {
  const s = setup({url: SITE + '/?q=Ember&type=text&view=list'});
  t.after(() => s.dom.window.close());
  assert.equal(s.$('#story-search').value, 'Ember');
  assert.equal(s.$('[data-news-grid]').dataset.layout, 'list');
  const card = s.$('.news-card:not([hidden]) [data-open-reader]');
  assert.ok(card.href.endsWith('/a/' + EMBER_ID));
  s.click(card); await until(() => s.$('#reader-sheet [data-article-id]'), 'article');
  s.click(s.$('[data-close-sheet]')); await until(() => !s.$('#reader-sheet').open, 'close');
  await frames();
  assert.equal(s.w.location.search, '?q=Ember&type=text&view=list');
  assert.equal(s.$('#story-search').value, 'Ember');
  assert.equal(s.d.querySelectorAll('.news-card:not([hidden])').length, 1);
  assert.equal(s.d.activeElement, card);
  s.w.history.forward(); await until(() => s.$('#reader-sheet [data-article-id]'), 'forward');
  assert.equal(s.$('#reader-sheet [data-article-id]').dataset.articleId, EMBER_ID);
});

test('archive defaults to a readable list; invalid URL controls fall back safely', t => {
  const s = setup({page: 'archive.html', url: SITE + '/archive?type=unknown&view=unknown&q=%3Csvg%3E'});
  t.after(() => s.dom.window.close());
  assert.equal(s.$('[data-news-grid]').dataset.layout, 'list');
  assert.equal(s.$('[data-filter="all"]').getAttribute('aria-pressed'), 'true');
  assert.equal(s.$('[data-empty-description]').querySelector('svg'), null);
  assert.match(s.$('[data-empty-description]').textContent, /<svg>/);
  s.click(s.$('[data-clear-search]'));
  assert.equal(s.w.location.search, '');
  assert.equal(s.d.activeElement, s.$('#story-search'));
});

test('Space activates the focused article version without scrolling the page', async t => {
  const s = setup(); t.after(() => s.dom.window.close());
  s.click(s.$('[data-open-reader]')); await until(() => s.$('#reader-sheet [data-article-id]'), 'article');
  const tab = s.$('[data-view="original"]'); tab.focus();
  const event = new s.w.KeyboardEvent('keydown', {key: ' ', bubbles: true, cancelable: true});
  tab.dispatchEvent(event);
  assert.equal(event.defaultPrevented, true);
  assert.equal(s.$('#original').hidden, false);
  assert.equal(s.w.location.hash, '#original');
});

test('intent prefetch is shared with click and never preloads every story', async t => {
  let finish;
  const s = setup({fetcher: url => new Promise(resolve => { finish = () => resolve({ok: true, text: async () => responseHTML(url)}); })});
  t.after(() => s.dom.window.close());
  assert.equal(s.requests.length, 0);
  const link = s.$('#read-' + ID_C);
  link.dispatchEvent(new s.w.Event('pointerover', {bubbles: true}));
  link.dispatchEvent(new s.w.Event('pointerover', {bubbles: true}));
  s.click(link);
  assert.equal(s.requests.length, 1);
  finish();
  await until(() => s.$('#reader-sheet [data-article-id]'), 'prefetched reader');
  assert.equal(s.requests.length, 1);
  assert.equal(s.requests[0].options.priority, 'low');
});

test('failed or mismatched prefetch does not poison a later article open', async t => {
  const s = setup({fetcher: async (url, options, n) => ({ok: true, text: async () => n === 1 ? html('a/' + ID_B + '.html') : responseHTML(url)})});
  t.after(() => s.dom.window.close());
  const link = s.$('#read-' + ID_C);
  link.dispatchEvent(new s.w.Event('pointerover', {bubbles: true}));
  await frames(); s.click(link);
  await until(() => s.$('#reader-sheet [data-article-id]'), 'correct article');
  assert.equal(s.$('#reader-sheet [data-article-id]').dataset.articleId, ID_C);
  assert.equal(s.requests.length, 2);
});

test('data saver disables speculative fetch but permits explicit reading', async t => {
  const s = setup(); t.after(() => s.dom.window.close());
  Object.defineProperty(s.w.navigator, 'connection', {value: {saveData: true}});
  const link = s.$('#read-' + ID_C);
  link.dispatchEvent(new s.w.Event('pointerover', {bubbles: true}));
  link.focus(); assert.equal(s.requests.length, 0);
  s.click(link); await until(() => s.$('#reader-sheet [data-article-id]'), 'explicit reader');
  assert.equal(s.requests.length, 1);
});

test('click escapes a stalled low-priority prefetch and requests the reader at high priority', async t => {
  const s = setup({fetcher: (url, options) => options.priority === 'low'
    ? new Promise(() => {})
    : Promise.resolve({ok: true, text: async () => responseHTML(url)})});
  t.after(() => s.dom.window.close());
  const link = s.$('#read-' + ID_C);
  link.dispatchEvent(new s.w.Event('pointerover', {bubbles: true}));
  const start = Date.now();
  s.click(link);
  await until(() => s.$('#reader-sheet [data-article-id]'), 'foreground reader despite stalled prefetch');
  assert.ok(Date.now() - start < 1000);
  assert.equal(s.requests.length, 2);
  assert.equal(s.requests[0].options.signal.aborted, true);
  assert.equal(s.requests[1].options.priority, 'high');
  assert.match(s.requests[1].url, new RegExp('^/read/' + ID_C + '\\.[a-f0-9]{12}\\.html$'));
  assert.equal(s.w.location.pathname, '/a/' + ID_C);
});

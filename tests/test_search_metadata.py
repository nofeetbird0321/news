import json
import re
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET
from test_build import Tags, build

ROOT = Path(__file__).resolve().parents[1]

class SearchMetadata(unittest.TestCase):
    def test_sitemap_matches_canonical_inventory(self):
        articles = list((ROOT / 'content/articles').glob('*.json'))
        tree = ET.parse(ROOT / 'public/sitemap.xml')
        urls = [u.text for u in tree.findall('.//{*}loc')]
        expected = {'https://news.nofeetbird.tech' + route for route in ['/', '/archive', '/about']}
        expected.update('https://news.nofeetbird.tech/a/' + p.stem for p in articles)
        self.assertEqual(set(urls), expected)
        self.assertEqual(len(urls), len(expected))
        self.assertIn('Sitemap: https://news.nofeetbird.tech/sitemap.xml', (ROOT / 'public/robots.txt').read_text())
        self.assertNotIn('lastmod', (ROOT / 'public/sitemap.xml').read_text())

    def test_article_metadata_describes_visible_source_and_preserves_dates(self):
        for path in (ROOT / 'content/articles').glob('*.json'):
            a = json.loads(path.read_text())
            page = (ROOT / 'public/a' / (a['id'] + '.html')).read_text()
            data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S).group(1))
            node = next(n for n in data['@graph'] if n['@type'] == 'Article')
            self.assertEqual(node['headline'], a['title'])
            self.assertEqual(node['citation'], a['source']['url'])
            self.assertEqual(node['datePublished'], a.get('ingested_at') or a['date'])
            self.assertEqual(node.get('dateModified'), a.get('updated_at'))
            self.assertIn('中文改写：', page)
            self.assertIn(a['source']['url'].replace('&', '&amp;'), page)
            self.assertNotIn('noindex', page)

    def test_fingerprinted_assets_exist_and_match_current_bytes(self):
        home = (ROOT / 'public/index.html').read_text()
        for ext in ('css', 'js'):
            asset = re.search(r'/static/app\.[a-f0-9]{12}\.' + ext, home).group(0)
            self.assertEqual((ROOT / 'public' / asset.lstrip('/')).read_bytes(), (ROOT / 'public' / ('app.' + ext)).read_bytes())
        headers = (ROOT / 'public/_headers').read_text()
        self.assertIn('/static/*\n  Cache-Control: public, max-age=31536000, immutable', headers)
        error = (ROOT / 'public/404.html').read_text()
        self.assertIn('content="noindex"', error)
        self.assertFalse(Tags(error).select('link', rel='canonical'))

    def test_first_paint_and_interaction_need_no_external_app_assets(self):
        for page in [ROOT / 'public/index.html', next((ROOT / 'public/a').glob('*.html'))]:
            doc = Tags(page.read_text())
            self.assertFalse(doc.select('link', rel='stylesheet'))
            self.assertTrue(doc.select('style', **{'data-source': build.CSS_FILE}))
            scripts = doc.select('script')
            self.assertFalse(any(s.get('src', '').startswith('/static/') for s in scripts))
            self.assertTrue(any(s.get('data-source') == build.JS_FILE for s in scripts))

    def test_reader_payloads_preserve_complete_article_and_have_no_shell_requests(self):
        home = Tags((ROOT / 'public/index.html').read_text())
        links = {a['href']: a['data-reader-src'] for a in home.select('a') if 'data-open-reader' in a}
        for a in build.load_articles():
            url = links['/a/' + a['id']]
            self.assertEqual(url, build.reader_url(a))
            content = (ROOT / 'public' / url.lstrip('/')).read_text()
            self.assertIn(build.render_article(a), content)
            doc = Tags(content)
            self.assertFalse(doc.select('script'))
            self.assertFalse(doc.select('link', rel='stylesheet'))
            self.assertTrue(doc.select('meta', name='robots', content='noindex'))
            self.assertLess(len(content), len((ROOT / 'public/a' / (a['id'] + '.html')).read_text()))

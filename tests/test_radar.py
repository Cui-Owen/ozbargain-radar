import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT))
import install
import deal_status
import fetch_deals
import fetch_groceries
import fetch_comments
import price_inspector


class Response:
    def __init__(self, body): self.body = body.encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.body


class RadarTests(unittest.TestCase):
    def test_status_priority(self):
        now = datetime(2026, 10, 28, tzinfo=timezone.utc)
        cases = [({'expiry': '2027-01-01T00:00:00Z', 'title-msg': 'Expired'}, 'expired'),
                 ({'title-msg': 'Out of stock'}, 'out_of_stock'),
                 ({'expiry': '2026-10-28T00:00:00Z'}, 'expired'),
                 ({'starting': '2026-10-29T00:00:00+00:00'}, 'upcoming'),
                 ({'expiry': '2027-01-01T00:00:00Z'}, 'active'),
                 ({'expiry': 'bad'}, 'unknown'),
                 ({'expiry': '2027-01-01T00:00:00'}, 'unknown'), ({}, 'unknown')]
        for meta, expected in cases:
            with self.subTest(meta=meta):
                self.assertEqual(deal_status.deal_status(meta, now=now), expected)

    def test_price_claim_is_not_verified(self):
        result = price_inspector.inspect_deal_pricing('SSD $100 ATL @ Amazon AU')
        self.assertTrue(result['is_atl'])
        self.assertFalse(result['history_verified'])
        self.assertIn('声称', result['status_badge'])
        self.assertTrue(result['verification_links']['price_hipster'].startswith('https://pricehipster.com/?q='))
        self.assertIn('camelcamelcamel', result['verification_links'])

    def test_half_price_does_not_claim_cycle(self):
        result = price_inspector.inspect_deal_pricing('Milk 50% off')
        self.assertTrue(result['is_half_price'])
        self.assertNotIn('周期', result['status_badge'])

    def test_feed_modes(self):
        self.assertEqual(fetch_deals.resolve_feed_url('electronics'), 'https://www.ozbargain.com.au/cat/electrical-electronics/deals/feed')
        self.assertEqual(fetch_deals.resolve_feed_url('deals', 'popular'), 'https://www.ozbargain.com.au/feed')

    def test_feed_availability_and_votes(self):
        items = []
        for n, flags, votes in [(1, '', 15), (2, 'Expired', 25), (3, 'Out of stock', 40), (4, '', 1)]:
            items.append(f'<item><title>Deal {n}</title><link>https://www.ozbargain.com.au/node/{n}</link><oz:meta votes-pos="{votes}" title-msg="{flags}" /></item>')
        body = '<rss xmlns:oz="https://www.ozbargain.com.au"><channel>' + ''.join(items) + '</channel></rss>'
        with patch('urllib.request.urlopen', return_value=Response(body)):
            result = fetch_deals.fetch_feed_deals('https://example.com/rss', min_votes=10)
            self.assertEqual([x['node_id'] for x in result], ['1'])
            self.assertEqual(result[0]['status'], 'unknown')
            all_items = fetch_deals.fetch_feed_deals('https://example.com/rss', only_active=False)
            self.assertEqual(len(all_items), 4)

    def test_latest_preserves_all_items_and_low_votes(self):
        items = []
        for n in range(36):
            items.append(f'<item><title>Deal {n}</title><link>https://www.ozbargain.com.au/node/{n}</link><oz:meta votes-pos="{n % 2}" votes-neg="1" /></item>')
        body = '<rss xmlns:oz="https://www.ozbargain.com.au"><channel>' + ''.join(items) + '</channel></rss>'
        with patch('urllib.request.urlopen', side_effect=lambda *a, **k: Response(body)):
            results = fetch_deals.fetch_deals()
            self.assertEqual(len(results), 36)
            self.assertEqual(results[0]['net_votes'], -1)
            self.assertEqual(len(fetch_deals.fetch_deals(limit=0)), 36)
            self.assertEqual(len(fetch_deals.fetch_deals(limit=7)), 7)
            self.assertEqual(len(fetch_deals.fetch_deals(min_votes=0)), 18)
            categories = fetch_deals.fetch_multiple_categories(['computing', 'gaming'])
            self.assertEqual([len(categories[c]) for c in ['computing', 'gaming']], [36, 36])
            self.assertEqual(fetch_deals.fetch_deals(mode='popular'), [])

    def test_general_scan_excludes_only_targeted_half_price(self):
        titles = ['Coles Half Price Weekly Specials', 'Woolworths 50% Off Coffee',
                  'Woolies Half-Price Offers', 'WWS 半价', 'Amazon 50% Off Coffee',
                  'Coles Mobile $99 Plan', 'Coffee Half Price']
        body = '<rss><channel>' + ''.join(f'<item><title>{t}</title><link>https://www.ozbargain.com.au/node/{i}</link></item>' for i, t in enumerate(titles)) + '</channel></rss>'
        with patch('urllib.request.urlopen', side_effect=lambda *a, **k: Response(body)):
            result = fetch_deals.fetch_deals(exclude_supermarket_half_price=True)
            self.assertEqual([x['title'] for x in result], titles[4:])
            self.assertEqual(len(fetch_deals.fetch_deals()), 7)
        self.assertTrue(fetch_deals.is_supermarket_half_price('Coffee 50% Off', 'https://www.coles.com.au/'))
        self.assertFalse(fetch_deals.is_supermarket_half_price('Coffee 50% Off', 'https://www.amazon.com.au/'))

    def test_grocery_full_feed_keeps_low_votes_and_later_sources(self):
        def response(req, **kwargs):
            store = 'Coles' if 'coles.com.au' in req.full_url else 'Woolworths'
            offset = 0 if store == 'Coles' else 100
            items = ''.join(f'<item><title>{store} Half Price Item {i}</title><link>https://www.ozbargain.com.au/node/{i + offset}</link></item>' for i in range(36))
            return Response('<rss><channel>' + items + '</channel></rss>')
        with patch('urllib.request.urlopen', side_effect=response):
            result = fetch_groceries.fetch_groceries(only_half_price=True)
            self.assertEqual(len(result), 72)
            self.assertEqual(len(fetch_groceries.fetch_groceries(limit=7)), 7)

    def test_feed_errors_are_visible(self):
        with patch('urllib.request.urlopen', side_effect=OSError('offline')):
            with self.assertRaisesRegex(RuntimeError, 'Unable to read RSS'):
                fetch_deals.fetch_feed_deals('https://example.com/rss')

    def test_unit_prices(self):
        for title, result in [('Prawns 500g $12', '$24.00/kg'), ('Milk 1.5L $3', '$2.00/L'),
                              ('Spice 12.5g $2', '$160.00/kg'), ('Milk 2 x 1L $5', '')]:
            with self.subTest(title=title):
                self.assertEqual(fetch_groceries.estimate_unit_price(title), result)

    def test_comments_keep_first_actual_comment(self):
        body = '<title>A Deal - OzBargain</title><div class="submitted">OP</div><div class="content"><p>Deal text here.</p></div><div id="comments"><div class="comment-wrap" id="comment-1"><div class="meta"><div class="submitted"><strong>Alice</strong></div></div><div class="content"><p>The warranty requires an Australian invoice.</p></div></div><div class="comment-wrap" id="comment-2"><div class="submitted"><strong>Bob</strong></div><div class="content"><p>Thanks!</p></div></div>'
        with patch('urllib.request.urlopen', return_value=Response(body)):
            result = fetch_comments.fetch_deal_comments('123')
        self.assertEqual(result['substantive_count'], 1)
        self.assertEqual(result['comments'][0]['author'], 'Alice')
        self.assertIn('Current page', result['coverage'])

    def test_no_comment_section_does_not_extract_description(self):
        with patch('urllib.request.urlopen', return_value=Response('<div class="submitted">OP</div><div class="content"><p>This is the deal description.</p></div>')):
            self.assertEqual(fetch_comments.fetch_deal_comments('123')['comments'], [])

    def test_cli_help(self):
        for script in ['fetch_deals.py', 'fetch_groceries.py', 'fetch_comments.py']:
            subprocess.run([sys.executable, str(ROOT / 'scripts' / script), '--help'], check=True, capture_output=True)


class InstallationTests(unittest.TestCase):
    def test_clone_update_pin_and_protect(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source, dest = base / 'source', base / 'installed'
            source.mkdir()
            def git(*args): return subprocess.check_output(['git', *args], cwd=source, text=True)
            git('init', '-b', 'main')
            git('config', 'user.email', 'test@example.com')
            git('config', 'user.name', 'Test')
            (source / 'SKILL.md').write_text('test')
            (source / 'VERSION').write_text('1.0.0')
            git('add', '.')
            git('commit', '-m', 'initial')
            git('tag', 'v1.0.0')
            install.install(str(source), dest, 'main')
            self.assertEqual((dest / 'VERSION').read_text(), '1.0.0')
            (source / 'VERSION').write_text('1.0.1')
            git('add', '.')
            git('commit', '-m', 'update')
            install.install(str(source), dest, 'main')
            self.assertEqual((dest / 'VERSION').read_text(), '1.0.1')
            install.install(str(source), dest, 'v1.0.0')
            self.assertEqual((dest / 'VERSION').read_text(), '1.0.0')
            install.install(str(source), dest, 'main')
            self.assertEqual((dest / 'VERSION').read_text(), '1.0.1')
            (dest / 'VERSION').write_text('local')
            with self.assertRaisesRegex(ValueError, 'Local changes'):
                install.install(str(source), dest, 'main')
            self.assertEqual((dest / 'VERSION').read_text(), 'local')

    def test_unmanaged_directory_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / 'SKILL.md').write_text('private local skill')
            with self.assertRaisesRegex(ValueError, 'unmanaged'):
                install.install('unused', dest, 'main')
            self.assertEqual((dest / 'SKILL.md').read_text(), 'private local skill')


if __name__ == '__main__':
    unittest.main()

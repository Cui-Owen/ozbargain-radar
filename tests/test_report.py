import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import render_report as report


def source(node):
    return {'node_id': str(node), 'title': 'Oil Engine {} $29.99 @ Auto'.format(node),
            'link': 'https://www.ozbargain.com.au/node/{}'.format(node),
            'description_snippet': '5L bottle. Pickup only.', 'net_votes': 0}


def annotation(record):
    return {'node_id': record['node_id'], 'source_hash': report.digest(record),
            'group': '汽车', 'priority': 2,
            'intro': {'text': '汽车机油', 'quote': 'Oil Engine'},
            'offer_quote': '$29.99', 'conditions_quote': 'Pickup only.',
            'note': {'text': '五升装', 'quote': '5L bottle.'}}


class BoundReportTests(unittest.TestCase):
    def test_256_chinese_titles_keep_same_node_links(self):
        sources = [source(n) for n in range(1000, 1256)]
        items = [annotation(s) for s in sources]
        for s, item in zip(sources, items):
            item['title_zh'] = {'text': '汽车机油 ' + s['node_id'], 'quote': s['title']}
        result = report.render(sources, items)
        rows = [line for line in result.splitlines() if line.startswith('| 汽车机油 ')]
        self.assertEqual(len(rows), 256)
        for s, row in zip(sources, rows):
            self.assertIn('汽车机油 ' + s['node_id'], row)
            self.assertIn('](' + s['link'] + ')', row)

    def test_chinese_product_title_preserves_identifiers_and_link(self):
        s = source(1)
        s['title'] = 'Gulf Western 10W-40 Engine Oil 5L $29.99 @ Auto'
        item = annotation(s)
        item['intro'] = {'text': '汽车发动机润滑用油', 'quote': 'Engine Oil'}
        item['title_zh'] = {'text': 'Gulf Western 10W-40 发动机油 5L', 'quote': s['title']}
        result = report.render([s], [item])
        self.assertIn('Gulf Western 10W-40 发动机油 5L', result)
        self.assertNotIn(s['title'], result)
        self.assertIn('](https://www.ozbargain.com.au/node/1)', result)
        for title in ['Gulf Western 10W-30 发动机油 5L',
                      'Gulf Western 10W-40 发动机油 10L',
                      'Gulf Western 发动机油 5L', 'Gulf Western 10W-40 Oil 5L']:
            item['title_zh']['text'] = title
            with self.subTest(title=title), self.assertRaises(ValueError):
                report.render([s], [item])

    def test_chinese_title_rejects_wrong_evidence_and_empty_translation(self):
        s = source(1)
        item = annotation(s)
        for text, evidence in [('汽车机油', 'Oil Engine'), ('', s['title']),
                               ('汽车机油 $29.99', s['title'])]:
            item['title_zh'] = {'text': text, 'quote': evidence}
            with self.subTest(text=text), self.assertRaises(ValueError):
                report.render([s], [item])

    def test_256_records_keep_original_title_link_pair_in_every_row(self):
        sources = [source(n) for n in range(1000, 1256)]
        result = report.render(sources, [annotation(s) for s in sources])
        rows = [line for line in result.splitlines() if re.match(r'\| Oil Engine ', line)]
        self.assertEqual(len(rows), 256)
        self.assertEqual(result.count('### 汽车'), 18)
        for row, record in zip(rows, sources):
            self.assertIn(record['title'], row)
            self.assertIn('](' + record['link'] + ')', row)
        self.assertEqual(len(re.findall(r'\]\(https://www.ozbargain.com.au/node/[0-9]+\)', result)), 256)

    def test_swapped_or_unknown_node_cannot_keep_source_hash(self):
        sources = [source(1), source(2)]
        items = [annotation(s) for s in sources]
        items[0]['node_id'], items[1]['node_id'] = items[1]['node_id'], items[0]['node_id']
        with self.assertRaisesRegex(ValueError, 'source hash'):
            report.render(sources, items)
        items = [annotation(source(999))]
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            report.render(sources, items)

    def test_missing_and_duplicate_rows_fail(self):
        sources = [source(1), source(2)]
        one = annotation(sources[0])
        for items in ([one], [one, one]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                report.render(sources, items)

    def test_modified_snapshot_fails_hash_check(self):
        s = source(1)
        item = annotation(s)
        s['title'] = 'Different product $20'
        with self.assertRaisesRegex(ValueError, 'source hash'):
            report.render([s], [item])

    def test_source_node_link_mismatch_and_foreign_host_fail(self):
        for url in ['https://www.ozbargain.com.au/node/2',
                    'https://www.ozbargain.com.au.evil.example/node/1',
                    'https://www.ozbargain.com.au@evil.example/node/1']:
            s = source(1)
            s['link'] = url
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'node/link'):
                report.render([s], [annotation(s)])

    def test_model_cannot_add_price_or_link_or_unsupported_quote(self):
        s = source(1)
        bad_changes = [('offer_quote', '$19.99'), ('link', 'https://example.com'),
                       ('intro', {'text': 'https://example.com', 'quote': 'Oil Engine'}),
                       ('note', {'text': '$1', 'quote': '5L bottle.'}),
                       ('note', {'text': '半价', 'quote': '50% off'})]
        for field, value in bad_changes:
            item = annotation(s)
            item[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                report.render([s], [item])

    def test_source_markdown_cannot_inject_table_cells_or_links(self):
        s = source(1)
        s['title'] += ' | [Fake](https://evil.example)\n<b>text</b>'
        item = annotation(s)
        item['intro'] = {'text': '[文字] | 内容', 'quote': 'Oil Engine'}
        result = report.render([s], [item])
        self.assertIn(r'\|', result)
        self.assertNotIn('[Fake](', result)
        self.assertNotIn('<b>', result)
        self.assertEqual(result.count('](https://'), 1)

    def test_merge_deduplicates_whole_records_and_rejects_title_conflict(self):
        s = source(1)
        updated = dict(s, net_votes=20)
        merged = report.merge([[s], {'automotive': [updated]}])
        self.assertEqual(merged, [s])
        updated['title'] = 'Other product'
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            report.merge([[s], [updated]])

    def test_cli_prepare_render_verify_and_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            input_path = base / 'raw.json'
            input_path.write_text(json.dumps([source(1)]), encoding='utf-8')
            directory = base / 'report'
            script = str(Path(report.__file__))
            def cli(*args):
                return subprocess.run([sys.executable, script, *map(str, args)], capture_output=True, text=True)
            self.assertEqual(cli('prepare', input_path, '--out', directory).returncode, 0)
            # No accidental reuse of old batch annotations.
            self.assertNotEqual(cli('prepare', input_path, '--out', directory).returncode, 0)
            notes = directory / 'batch-001.annotations.json'
            notes.write_text(json.dumps([annotation(source(1))]), encoding='utf-8')
            output = base / 'table.md'
            args = ['--snapshot', directory / 'snapshot.json', '--annotations', notes, '--output', output]
            self.assertEqual(cli('render', *args).returncode, 0)
            self.assertEqual(cli('verify', *args).returncode, 0)
            output.write_text(output.read_text(encoding='utf-8').replace('/node/1)', '/node/2)'), encoding='utf-8')
            self.assertNotEqual(cli('verify', *args).returncode, 0)


if __name__ == '__main__':
    unittest.main()

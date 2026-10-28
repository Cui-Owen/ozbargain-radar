#!/usr/bin/env python3
"""Bind chat tables to captured records. No network access or model calls."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


def digest(record):
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def identity(record):
    node = str(record.get('node_id', ''))
    link = record.get('link', '')
    if not isinstance(link, str):
        raise ValueError('Source link must be text')
    parsed = urlsplit(link)
    if (not re.fullmatch(r'[0-9]+', node) or parsed.scheme != 'https'
            or parsed.netloc not in ('www.ozbargain.com.au', 'ozbargain.com.au')
            or parsed.path.rstrip('/') != '/node/' + node
            or parsed.query or parsed.fragment):
        raise ValueError('Source node/link mismatch: ' + node)
    if not isinstance(record.get('title'), str) or not record['title'].strip():
        raise ValueError('Missing source title: ' + node)
    return node


def flatten(data):
    if isinstance(data, list):
        for value in data:
            yield from flatten(value)
    elif isinstance(data, dict):
        if 'node_id' in data:
            yield data
        else:
            for value in data.values():
                yield from flatten(value)
    else:
        raise ValueError('Expected deal list or category-to-deal-list mapping')


def merge(inputs):
    records = {}
    for data in inputs:
        for record in flatten(data):
            node = identity(record)
            if node in records:
                old = records[node]
                if old['title'] != record['title'] or old['link'] != record['link']:
                    raise ValueError('Conflicting identity for node ' + node)
                # Keep the first complete record; never combine fields across feeds.
                continue
            records[node] = record
    return list(records.values())


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def prepare(inputs, out, batch_size=15):
    if not 1 <= batch_size <= 25:
        raise ValueError('batch-size must be between 1 and 25')
    records = merge(inputs)
    out = Path(out)
    # A new directory prevents stale batch files from an earlier larger scan.
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'snapshot.json', records)
    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        prefix = 'batch-{:03d}'.format(start // batch_size + 1)
        write_json(out / (prefix + '.source.json'),
                   [{'source_hash': digest(r), 'record': r} for r in batch])
        write_json(out / (prefix + '.annotations.json'), [
            {'node_id': str(r['node_id']), 'source_hash': digest(r),
             'group': '其他', 'priority': 2,
             'title_zh': {'text': '', 'quote': r['title']},
             'intro': {'text': '', 'quote': ''},
             'offer_quote': '', 'conditions_quote': '',
             'note': {'text': '', 'quote': ''}} for r in batch])
    return len(records)


def cell(value):
    # Escape all source/annotation content; only this module can create links/HTML.
    text = html.escape(str(value), quote=False)
    text = re.sub(r'([\\`*_\[\]{}()!|#~])', r'\\\1', text)
    return re.sub(r'[\r\n]+', ' ', text).strip()


def corpus(record):
    # Evidence must come from captured text, never model-produced price intelligence.
    return '\n'.join(str(record.get(k) or '') for k in
                     ('title', 'description_snippet', 'snippet', 'description', 'body'))


def quote(record, value):
    if not isinstance(value, str):
        raise ValueError('Evidence quote must be text')
    if value and value not in corpus(record):
        raise ValueError('Evidence quote not found in node ' + str(record['node_id']))
    return value


def explained(record, value, required=False):
    if not isinstance(value, dict) or set(value) != {'text', 'quote'}:
        raise ValueError('Explanation requires text and quote')
    text, evidence = value['text'], value['quote']
    if not isinstance(text, str) or (required and not text.strip()):
        raise ValueError('Missing introduction for node ' + str(record['node_id']))
    if bool(text.strip()) != bool(evidence):
        raise ValueError('Explanation must have source evidence')
    quote(record, evidence)
    # Links and amounts belong to the source fields, not free-form explanations.
    if re.search(r'https?://|/node/|\$|\d+\s*%', text, re.I):
        raise ValueError('Explanation cannot supply URLs, prices or percentages')
    return text


ANNOTATION_KEYS = {'node_id', 'source_hash', 'group', 'priority', 'intro',
                   'offer_quote', 'conditions_quote', 'note'}


def chinese_title(record, value):
    text = explained(record, value, required=True)
    if value['quote'] != record['title']:
        raise ValueError('Chinese title must bind to the complete source title')
    if not re.search(r'[\u4e00-\u9fff]', text):
        raise ValueError('Chinese title must contain Chinese text')
    original = record['title']
    numbers = set(re.findall(r'\d+(?:\.\d+)?', original))
    if not set(re.findall(r'\d+(?:\.\d+)?', text)) <= numbers:
        raise ValueError('Chinese title introduces unsupported numbers')
    # Preserve mixed letter/digit identifiers and technical units, e.g. P110M,
    # 10W-40, 5L, 256GB. Ordinary count/pack wording may be translated.
    tokens = re.findall(r'[A-Za-z0-9]+(?:[.+/\-][A-Za-z0-9]+)*', original)
    protected = [t for t in tokens if re.search(r'[A-Za-z]', t) and re.search(r'\d', t)
                 and not re.fullmatch(r'\d+[-/]?(?:count|pack|pk|pcs|pieces)', t, re.I)]
    for token in protected:
        if not re.search(r'(?<![A-Za-z0-9])' + re.escape(token) + r'(?![A-Za-z0-9])', text, re.I):
            raise ValueError('Chinese title omits or changes identifier: ' + token)
    return text


def bind(records, annotations):
    sources = {identity(r): r for r in records}
    if len(sources) != len(records):
        raise ValueError('Snapshot contains duplicate nodes')
    seen = set()
    bound = []
    for item in annotations:
        if not isinstance(item, dict) or set(item) not in (ANNOTATION_KEYS, ANNOTATION_KEYS | {'title_zh'}):
            raise ValueError('Unexpected annotation fields')
        node = str(item['node_id'])
        if node not in sources or node in seen:
            raise ValueError('Unknown or duplicate annotation node: ' + node)
        seen.add(node)
        source = sources[node]
        if item['source_hash'] != digest(source):
            raise ValueError('Stale or mismatched source hash: ' + node)
        if not isinstance(item['group'], str) or not item['group'].strip():
            raise ValueError('Missing category')
        if type(item['priority']) is not int or not 0 <= item['priority'] <= 3:
            raise ValueError('Priority must be 0..3')
        if 'title_zh' in item:
            chinese_title(source, item['title_zh'])
        intro = explained(source, item['intro'], required=True)
        note = explained(source, item['note'])
        offer = quote(source, item['offer_quote'])
        conditions = quote(source, item['conditions_quote'])
        bound.append((source, item, intro, note, offer, conditions))
    if seen != set(sources):
        raise ValueError('Missing annotations for {} source nodes'.format(len(set(sources) - seen)))
    return sorted(bound, key=lambda row: (row[1]['group'], row[1]['priority']))


def render(records, annotations, batch_size=15):
    if not 1 <= batch_size <= 25:
        raise ValueError('batch-size must be between 1 and 25')
    bound = bind(records, annotations)
    lines = ['共 {} 条；以下链接与原标题绑定至同一抓取快照。'.format(len(bound)), '']
    current_group, index = None, 0
    for source, item, intro, note, offer, conditions in bound:
        group = item['group']
        if group != current_group:
            current_group, index = group, 0
        if index % batch_size == 0:
            suffix = '（续 {}）'.format(index // batch_size + 1) if index else ''
            lines += ['### ' + cell(group) + suffix, '',
                      '| 商品与介绍 | 到手价与折扣（原文） | 购买条件（原文） | 优惠说明 | 商家与来源 |',
                      '| --- | --- | --- | --- | --- |']
        # Legacy annotations still render their original title. New batches require
        # a validated Chinese title; source titles stay in the immutable snapshot.
        title = item['title_zh']['text'] if 'title_zh' in item else source['title']
        product = cell(title) + '<br>' + cell(intro)
        host = urlsplit(source.get('merchant_url') or '').hostname or source.get('store') or ''
        origin = (cell(host) + '；' if host else '') + '[原帖 ' + str(source['node_id']) + '](' + source['link'] + ')'
        info = []
        if source.get('published'):
            info.append(cell(source['published']))
        if 'net_votes' in source:
            info.append(cell(source['net_votes']) + ' 票')
        if info:
            origin += '<br>' + '；'.join(info)
        lines.append('| ' + ' | '.join([product, cell(offer or '见原标题'),
                                      cell(conditions or '未注明'), cell(note or '—'), origin]) + ' |')
        index += 1
        if index % batch_size == 0:
            lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare', help='Merge captured JSON and create annotation batches')
    prep.add_argument('inputs', nargs='+')
    prep.add_argument('--out', required=True)
    prep.add_argument('--batch-size', type=int, default=15)
    for name in ('render', 'verify'):
        sub = commands.add_parser(name)
        sub.add_argument('--snapshot', required=True)
        sub.add_argument('--annotations', nargs='+', required=True)
        sub.add_argument('--output', required=True)
        sub.add_argument('--batch-size', type=int, default=15)
    args = parser.parse_args()
    if args.command == 'prepare':
        print('Prepared {} records'.format(prepare([read_json(p) for p in args.inputs], args.out, args.batch_size)))
        return
    annotations = []
    for path in args.annotations:
        value = read_json(path)
        if not isinstance(value, list):
            raise ValueError('Annotations must be a list')
        annotations.extend(value)
    result = render(read_json(args.snapshot), annotations, args.batch_size)
    if args.command == 'verify':
        if Path(args.output).read_text(encoding='utf-8') != result:
            raise ValueError('Report differs from bound renderer output')
        print('Report matches captured records and annotations; live URLs not checked')
    else:
        Path(args.output).write_text(result, encoding='utf-8')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    try:
        main()
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)

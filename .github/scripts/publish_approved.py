#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经验之书·自动发布：把 GitHub 仓库中标为 approved 的投稿 issue 解析为经验卡，写入 index.html 的 EXPS，并给 issue 打「已发布」标签 + 关闭。
运行环境：GitHub Actions（仓库根目录），依赖 GH_TOKEN / GH_REPO 环境变量。
"""
import json, os, re, sys, urllib.request

TOKEN = os.environ.get('GH_TOKEN', '')
REPO = os.environ.get('GH_REPO', '')
if not TOKEN or not REPO:
    sys.exit('需要 GH_TOKEN 与 GH_REPO')

API = f'https://api.github.com/repos/{REPO}'

CAT_MAP = {'择路进阶': 'zljj', '生活健康': 'shjk', '智能培训': 'aipe', '投资理财': 'tzxf'}
ACT_MAP = {'zljj': '择路', 'shjk': '成家', 'aipe': '立业', 'tzxf': '远行'}


def gh(url, method='GET', data=None):
    req = urllib.request.Request(url, method=method)
    req.add_header('Authorization', f'token {TOKEN}')
    req.add_header('Accept', 'application/vnd.github+json')
    body = None
    if data is not None:
        req.add_header('Content-Type', 'application/json')
        body = json.dumps(data).encode('utf-8')
    try:
        with urllib.request.urlopen(req, data=body, timeout=60) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        err = e.read().decode('utf-8', 'ignore')[:300]
        sys.exit(f'GitHub API 失败 {url} -> {e.code}: {err}')


def parse_body(body):
    """GitHub issue form 的 body 形如 '### 经验标题\\n\\n值\\n\\n### 经验全文\\n\\n...'"""
    fields = {}
    for part in re.split(r'\n### ', '\n' + (body or '')):
        part = part.strip()
        if not part:
            continue
        lines = part.split('\n', 1)
        key = lines[0].strip()
        val = lines[1].strip() if len(lines) > 1 else ''
        fields[key] = val
    return fields


def split_steps(text):
    """步骤文本按行拆分，去掉行首序号。"""
    out = []
    for ln in (text or '').split('\n'):
        ln = ln.strip()
        if not ln:
            continue
        ln = re.sub(r'^(第[一二三四五六七八九十]+步|[①②③④⑤⑥⑦⑧⑨⑩]|\d+[\.、)])\s*', '', ln)
        out.append(ln)
    return out


def main():
    issues = gh(f'{API}/issues?state=open&labels=approved&per_page=50')
    todo = [i for i in issues if not any(l['name'] == '已发布' for l in i['labels'])]
    if not todo:
        print('no approved issue to publish')
        return

    with open('index.html', encoding='utf-8') as f:
        html = f.read()
    m = re.search(r'(var EXPS = \[)(.*?)(\n\s*\];)', html, re.S)
    if not m:
        sys.exit('index.html 中未找到 var EXPS 数组')
    arr = m.group(2)
    ids = re.findall(r'"id":"exp_(\d+)"', arr)
    max_id = max(int(i) for i in ids) if ids else 800

    published = []
    for issue in todo:
        f = parse_body(issue.get('body') or '')
        title = (f.get('经验标题') or issue['title']).replace('[经验]', '').strip()
        if not title:
            continue
        cat_name = (f.get('所属分类') or '择路进阶').strip()
        cat = CAT_MAP.get(cat_name, 'zljj')
        steps = split_steps(f.get('步骤'))
        new = {
            'id': f'exp_{max_id + 1}',
            't': title[:80],
            'cat': cat,
            'act': ACT_MAP[cat],
            'g': 'B',
            'u': 0,
            'a': steps,
            'fail': (f.get('失败排查') or '').strip(),
            's': (f.get('适用场景') or '').strip(),
            'c': (f.get('参考来源') or '用户投稿').strip(),
        }
        full = (f.get('经验全文') or '').strip()
        if full:
            new['full'] = full[:3000]
        max_id += 1
        published.append((issue['number'], new))

    if not published:
        print('no valid issue parsed')
        return

    # 在最后一个 } 后统一插入 ,\n{new}
    insert_json = ''.join('\n' + json.dumps(e, ensure_ascii=False) for _, e in published)
    last_brace = arr.rfind('}')
    after = arr[last_brace + 1:]
    sep = ',' if ',' in after else ''
    new_arr = arr[:last_brace + 1] + sep + insert_json + '\n'
    html = html[:m.start(2)] + new_arr + html[m.end(2):]

    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(html)

    # 打「已发布」标签并关闭
    for num, e in published:
        cur = next(i for i in todo if i['number'] == num)
        labels = [l['name'] for l in cur['labels']] + ['已发布']
        gh(f'{API}/issues/{num}', method='PATCH', data={'labels': labels, 'state': 'closed'})

    print(f'published {len(published)}: ' + ', '.join(f'#{n} {e["id"]} {e["t"][:20]}' for n, e in published))


if __name__ == '__main__':
    main()

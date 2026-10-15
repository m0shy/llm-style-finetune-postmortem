import os, re, sys

bad = []
for dp, _, fs in os.walk('.'):
    if '.git' in dp:
        continue
    for fn in fs:
        if not fn.endswith('.md'):
            continue
        p = os.path.join(dp, fn)
        with open(p, encoding='utf-8') as fh:
            text = fh.read()
        for m in re.finditer(r'\[[^\]]*\]\(([^)]+)\)', text):
            t = m.group(1).split('#')[0]
            if not t or t.startswith(('http://', 'https://', 'mailto:')):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(dp, t))):
                bad.append(p + ': ' + t)
print('\n'.join(bad) if bad else 'all relative links OK')
sys.exit(1 if bad else 0)

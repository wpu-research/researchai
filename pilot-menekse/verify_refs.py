import re, json, sys, time, urllib.request, urllib.parse, unicodedata
SRC=sys.argv[1]; OUT=sys.argv[2]
txt=open(SRC,encoding='utf-8').read()
sec=txt.split('## KAYNAKLAR',1)[1].split('## YAPAY ZEKA',1)[0]
refs=[r.strip() for r in sec.split('\n\n') if re.match(r'^[A-ZÇĞİÖŞÜa-z]',r.strip()) and not r.strip().startswith(':::')]
def norm(s):
    s=unicodedata.normalize('NFKD',s.lower().replace('ı','i'))
    s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9 ]',' ',s)
def toks(s): return {w for w in norm(s).split() if len(w)>2}
def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'ResearchAI-pilot (mailto:research@wpu.edu.tr)'})
    with urllib.request.urlopen(req,timeout=25) as r: return json.load(r)
res=[]
for ref in refs:
    clean=re.sub(r'\*','',ref)
    m=re.match(r'^(.+?)\((\d{4})[a-z]?\)\.\s*(.+)$',clean,re.S)
    if not m: res.append({'ref':clean[:90],'status':'parse_fail'}); continue
    auth,year,rest=m.group(1),m.group(2),m.group(3)
    sur=norm(auth.split(',')[0]).split()
    sur=sur[0] if sur else ''
    title=rest.split('. ')[0]
    doi=re.search(r'https://doi\.org/(\S+?)(?:\s|$|\))',clean)
    rec={'ref':clean[:110],'year':year,'surname':sur,'title':title[:90]}
    try:
        if doi:
            d=doi.group(1).rstrip('.')
            msg=get('https://api.crossref.org/works/'+urllib.parse.quote(d,safe='/'))['message']
            how='doi'
        else:
            q=urllib.parse.quote(f'{title} {auth}')
            items=get(f'https://api.crossref.org/works?query.bibliographic={q}&rows=1')['message']['items']
            if not items: rec['status']='no_doi_not_found'; res.append(rec); time.sleep(.3); continue
            msg=items[0]; how='search'
        ct=' '.join(msg.get('title',[''])); cy=str((msg.get('issued',{}).get('date-parts',[[None]])[0] or [None])[0])
        ca=' '.join(norm(a.get('family','')) for a in msg.get('author',[]))
        tj=len(toks(title)&toks(ct))/max(1,len(toks(ct)))
        yd=abs(int(cy)-int(year)) if cy.isdigit() else 99
        rec.update(how=how,cr_title=ct[:90],cr_year=cy,title_overlap=round(tj,2),author_ok=sur in ca if msg.get('author') else None,year_ok=cy==year)
        ok=tj>=0.6 and yd<=1 and (rec['author_ok'] in (True,None))
        if tj>=0.6 and 1<yd<=4 and rec['author_ok'] in (True,None): rec['note']='year_differs_check_print_vs_online'
        if how=='search': rec['status']='search_match' if ok else 'search_weak'
        else: rec['status']='verified' if ok else ('year_check' if rec.get('note') else 'MISMATCH')
    except Exception as ex:
        rec['status']='error' if doi else 'no_doi_error'; rec['err']=str(ex)[:60]
    res.append(rec); time.sleep(.3)
json.dump(res,open(OUT,'w'),ensure_ascii=False,indent=1)
from collections import Counter
print(len(refs),Counter(r['status'] for r in res))
for r in res:
    if r['status'] in('MISMATCH','error','parse_fail'): print(r['status'],'|',r['ref'],'|',{k:r.get(k) for k in('cr_title','cr_year','title_overlap','author_ok','year_ok','err')})

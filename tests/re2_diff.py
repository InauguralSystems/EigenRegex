#!/usr/bin/env python3
"""Generate differential fixtures.  google-re2, never Python re, is the oracle."""
import importlib.metadata,json,re
from pathlib import Path
import re2
VERSION=importlib.metadata.version('google-re2')
OUT=Path(__file__).with_name('re2_expected.eigs'); CASES=[]
# Convert google-re2's Python string indices to EigenRegex's UTF-8 byte offsets.
def bytepos(s,p): return -1 if p<0 else len(s[:p].encode('utf-8'))
def spans(s,m,r):
 return [bytepos(s,x) for pair in [m.span(),*[m.span(i) for i in range(1,r.groups+1)]] for x in pair]
def add(feature,pattern,subjects,operation='search'):
 try: rx=re2.compile(pattern)
 except Exception as e:
  CASES.append({'feature':feature,'pattern':pattern,'compile_ok':False,'subject':'','spans':None,'named':{}}); return
 if not subjects: CASES.append({'feature':feature,'pattern':pattern,'compile_ok':True,'subject':'','compile_only':True}); return
 for subject in subjects:
  if operation=='replace':
   CASES.append({'feature':feature,'pattern':pattern,'compile_ok':True,'operation':operation,'subject':subject,'replacement':'#','output':rx.sub('#',subject)}); continue
  if operation=='find_all':
   data=subject; found=[]; pos=0
   while pos <= len(data):
    m=rx.search(data,pos)
    if not m: break
    found.append(spans(subject,m,rx)); a,b=m.span()
    if b>a: pos=b
    elif b==len(data): break
    else:
     pos=b+1

   CASES.append({'feature':feature,'pattern':pattern,'compile_ok':True,'operation':operation,'subject':subject,'all_spans':found}); continue
  m=rx.search(subject); ss=spans(subject,m,rx) if m else None
  named={n:[bytepos(subject,x) for x in m.span(i)] for raw,i in rx.groupindex.items() for n in [raw.decode('utf-8') if isinstance(raw,bytes) else raw]} if m else {}
  CASES.append({'feature':feature,'pattern':pattern,'compile_ok':True,'subject':subject,'spans':ss,'named':named})
def properties():
 forms=['%s','^%s$','(%s)','%s+','%s+?','(%s|x)','(x|%s)','x%s','%sx','%s?']
 subjects=['Aé中𐐀','aǅʰ','7Ⅷ²','!+—',' \u2028','xyz','𐐨!7','']
 for family,cats in {'property_letters':['L','Lu','Ll','Lt','Lm','Lo'],'property_numbers':['N','Nd','Nl','No'],'property_psz':['P','S','Z']}.items():
  target=72 if family=='property_letters' else 50
  for i in range(target):
   cat=cats[i%len(cats)]; token=('\\P' if (i//len(cats))%2 else '\\p')+'{'+cat+'}'
   add(family,forms[(i//(2*len(cats)))%len(forms)]%token,subjects)
def main():
 # Existing feature families, all evaluated directly by RE2.
 for word in ['cat','dog','a1','x_y','Z9']:
  for f in [r'\b%s\b',r'^\b%s\b$',r'(\b%s\b)',r'\b(%s)\b',r'\b%s\b!',r'!\b%s\b',r'(\b%s\b|never)',r'(never|\b%s\b)',r'\b%s+\b',r'\b%s\b.*']:
   add('boundary',f%word,[word,'!'+word+'!','É'+word,'nothing'])
 for token in ['cat','Dog','É','Ä','Σ','σ','ς']:
  for f in ['%s','^%s$','(%s)','%s+','%s+?','(%s|never)','(never|%s)','[x]%s','%s[0-9]?','%s.*']:
   add('casefold','(?i)'+f%token,[token,token.swapcase(),'!'+token.swapcase()+'!','nothing'])
 for i in range(50):
  name=['alpha','bravo','charlie','delta','echo'][i%5]+str(i); add('named',f'(?P<{name}>a'+('?' if i%2 else '+')+')',['','a','aaa','!a!'])
 properties()
 uncased=['中','文','€','😀','🧪','א','ا','ह','ก','あ','ア','한','々','∞','→']
 for scalar in uncased:
  for form in ['(?i)%s','(?i)^%s$']:
   add('casefold_uncased',form%scalar,[scalar,'!'+scalar+'!','x'+scalar,scalar+'x'])
 for scalar in uncased[:10]: add('casefold_uncased','(?i)K'+scalar,['k'+scalar,'K'+scalar,scalar])
 for p in ['a(?i)b','A(?i)b','ab(?i)c','(a(?i)b)c','(a|b(?i)c)d','x(?i:ab)y']:
  for suffix in ['','+','?','|q','c','中']: add('inline_flags',p+suffix,['ab','aB','Ab','AB','abc','bCd','q','中'])
 for token in [r'\p{Lu}',r'\p{Ll}',r'\P{Lu}',r'\P{Ll}',r'\p{L}',r'\P{L}']:
  for form in ['(?i)%s','(?i)^%s$','(?i)(%s)','x(?i)%s','(?i:%s)','(?i)%s+']:
   add('casefold_property',form%token,['K','k','K','S','s','ſ','µ','μ','Μ','Ä','ä','中','𐐀','𐐨','!'])
 # Every member of every multi-member Unicode 15.0 C/S simple-fold class is
 # exercised in both roles: once as the pattern and against the entire class.
 fold_path=Path(__file__).parents[1]/'.cache'/'ucd'/'15.0.0'/'CaseFolding.txt'
 if not fold_path.is_file(): raise SystemExit('missing cached CaseFolding.txt; run tools/gen_unicode_categories.py')
 parent={}
 def find(x):
  parent.setdefault(x,x)
  while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
  return x
 def union(a,b):
  a,b=find(a),find(b)
  if a!=b: parent[b]=a
 for raw in fold_path.read_text().splitlines():
  line=raw.split('#',1)[0].strip()
  if line:
   a,status,b,*_=[x.strip() for x in line.split(';')]
   if status in ('C','S'): union(int(a,16),int(b,16))
 groups={}
 for cp in parent: groups.setdefault(find(cp),[]).append(chr(cp))
 for chars in groups.values():
  if len(chars)>1:
   for char in chars: add('casefold_closure','(?i)'+re.escape(char),chars)
 # Preserve the round-5 distinct-pattern floor in addition to full closure.
 add('casefold_closure','(?i)^a$',['a','A'])
 # At least 30 class/range patterns under ignore-case.
 bodies=['a-z','A-Z0-9_','^a-z','É-Ü','a-zÉ','A-Fx-z','0-9a-f','^É-Ü','K-S','Σ-Ω','a-cX-Z','^A-Z','À-Ö','ø-ÿ','a-z0-3']
 for i in range(30):
  b=bodies[i%len(bodies)]; p=('(' if i>=15 else '')+('^' if i%3==0 else '')+'(?i)['+b+']'+(['','+','$'][i%3])+(')' if i>=15 else '')
  add('casefold_class',p,['ABC','abc','123_','é','É','Ö','×','Σ','ω','ı','中','Aé'])
 # Zero-width find-all is compared in byte offsets over multibyte subjects.
 for i in range(30):
  base=[r'\b',r'\B',r'^',r'$',r'^|$',r'\b|$'][i%6]; p=['%s','(%s)','%s|never','never|%s','((%s))'][i//6] % base
  add('boundary_find_all',p,['éa中','中_a','é','😀x',''],operation='find_all')
 # Replacement must copy a complete scalar when an empty match advances, and
 # find-all must likewise resume only at scalar boundaries.
 replace_subjects=['é','中','😀','é中😀','aé','中a','😀a','éa中😀']
 replacement_patterns=[r'x*',r'a*',r'x*x*',r'a*a*',r'z*z*',r'.?',r'é?',r'中?',r'😀?',r'[a-z]*',
  r'(x*)',r'(a*)',r'(x*x*)',r'(a*a*)',r'(z*z*)',r'(.)?',r'(é)?',r'(中)?',r'(😀)?',r'([a-z]*)',
  r'x*|q',r'a*|q',r'x*x*|q',r'a*a*|q',r'z*z*|q',r'.?|q',r'é?|q',r'中?|q',r'😀?|q',r'[a-z]*|q']
 for p in replacement_patterns:
  add('unicode_replace',p,replace_subjects,operation='replace')
 # Every leftmost start of a consuming atom is checked over 2/3/4-byte text.
 consume_subjects=['éa','中a','😀a','!é','!中','!😀','é中😀a']
 atoms=['.',r'.\b','[a-z]','[^a]','a','é','中','😀','(.)','(.|a)']
 for i in range(30): add('unicode_match_start',atoms[i%len(atoms)]+(['','?','+'][i//10]),consume_subjects)
 # Compile acceptance: quantifier matrix and capture-name matrix.
 for wrapper in ['%s','(%s)','x|%s']:
  for q in ['*','+','?','{0}','{1}','{3}','{1,}','{1,3}','*?','+?','??','{1,3}?']:
   add('standalone_flag_quantifier',wrapper % ('(?i)'+q),[])
 names=['1','1x','é','中','_','_x','x1','Δ2','١','１','Ⅷ','́','x́','＿','€','😀','²','℘','','-','x-y','x y','.','x!','x/y',':','x:y','x.y','x@y','x#y','x$y','x%y','x&y','x*y','x+y','x=y','x?y','x[y','x]y','x{y','x}y']
 for name in names: add('capture_name_matrix',f'(?P<{name}>a)',[])
 add('capture_name_matrix','(?P<x>a)(?P<x>b)',[])
 # Loud documented exclusions: RE2 accepts compound properties/categories that EigenRegex intentionally excludes (#38).
 compound=[]
 for token in [r'\p{L}',r'\P{L}',r'\p{Nd}']:
  for left,right in [('','a'),('a',''),('0-9','_'),('^','a'),('a-z','0-9'),('_','A-Z'),('[:alpha:]','x'),('x','-'),('-','x'),('ab','cd')]:
   compound.append('['+left+token+right+']')
 for p in compound+[r'\p{M}',r'\p{Zs}']: add('documented_exclusion',p,[])
 enc=lambda x:json.dumps(x,ensure_ascii=False,separators=(',',':'))
 header=f'# Generated by tests/re2_diff.py with google-re2 {VERSION}; do not edit.\nre2_oracle_version is {enc(VERSION)}\nre2_diff_cases is []\n'
 OUT.write_text(header+''.join('append of [re2_diff_cases,'+enc(c)+']\n' for c in CASES))
 for f in sorted({c['feature'] for c in CASES}):
  x=[c for c in CASES if c['feature']==f]; print(f'feature={f} patterns={len({c["pattern"] for c in x})} subjects={len(x)} oracle=google-re2-{VERSION}')
if __name__=='__main__': main()

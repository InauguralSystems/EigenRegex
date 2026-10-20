#!/usr/bin/env python3
import json,re,unicodedata
from pathlib import Path
O=Path(__file__).with_name('re2_expected.eigs'); C=[]
def bp(s,p): return -1 if p<0 else len(s[:p].encode())
def add(f,p,ss,fl=0,oracle=None):
 r=re.compile(oracle or p,fl)
 for s in ss:
  m=r.search(s); spans=None; named={}
  if m:
   spans=[bp(s,x) for q in [m.span(),*[m.span(i) for i in range(1,r.groups+1)]] for x in q]
   named={n:[bp(s,x) for x in m.span(i)] for n,i in r.groupindex.items()}
  C.append({'feature':f,'pattern':p,'subject':s,'spans':spans,'named':named})
def reject(f,p,error):
 C.append({'feature':f,'pattern':p,'subject':'','spans':None,'named':{},'compile_error':error})
_CATEGORY_CACHE={}
def category_class(cat,neg=False):
 if (cat,neg) in _CATEGORY_CACHE: return _CATEGORY_CACHE[(cat,neg)]
 chunks=[]; start=None
 for cp in range(0x110000):
  yes=not (0xd800<=cp<=0xdfff) and (unicodedata.category(chr(cp)).startswith(cat) if len(cat)==1 else unicodedata.category(chr(cp))==cat)
  if yes and start is None:start=cp
  if start is not None and (not yes or cp==0x10ffff):
   end=cp if yes else cp-1
   esc=lambda n:('\\u%04x' if n<=0xffff else '\\U%08x')%n
   chunks.append(esc(start) if start==end else esc(start)+'-'+esc(end));start=None
 out='['+('^' if neg else '')+''.join(chunks)+']'
 _CATEGORY_CACHE[(cat,neg)]=out
 return out
def oracle_pattern(p):
 def sub(m): return category_class(m.group(2),m.group(1)=='P')
 return re.sub(r'\\([pP])\{(L|Lu|Ll|Lt|Lm|Lo|N|Nd|Nl|No|P|S|Z)\}',sub,p)
def properties():
 families={'property_letters':['L','Lu','Ll','Lt','Lm','Lo'], 'property_numbers':['N','Nd','Nl','No'], 'property_psz':['P','S','Z']}
 subjects=['Aé中𐐀','aǅʰ','7Ⅷ²','!+—',' \u2028','xyz','𐐨!7','']
 forms=['%s','^%s$','(%s)','%s+','%s+?','(%s|x)','(x|%s)','x%s','%sx','%s?']
 for family,cats in families.items():
  made=0
  # 60 distinct patterns per family: category, polarity, and ten constructs.
  for cat in cats:
   for neg in (False,True):
    token=('\\P' if neg else '\\p')+'{'+cat+'}'
    for form in forms:
     if made>=60: break
     p=form%token; add(family,p,subjects,oracle=oracle_pattern(p)); made+=1
    if made>=60: break
   if made>=60: break
  # Exercise property spellings inside classes, especially scalar negation.
  for cat in cats:
   for token,op in [('[\\p{'+cat+'}]','\\p{'+cat+'}'),('[^\\p{'+cat+'}]','\\P{'+cat+'}')]:
    add(family,token,subjects,oracle=oracle_pattern(op));made+=1
  # Small families need additional class-spelled forms to reach the bar.
  i=0
  while made<50:
   cat=cats[i%len(cats)]; token='[^\\p{'+cat+'}]' if i%2 else '[\\p{'+cat+'}]'
   p=forms[(i//len(cats))%len(forms)]%token
   if not any(c['feature']==family and c['pattern']==p for c in C):
    # [^\p] is \P; [\p] is \p for the Python oracle.
    op=('\\P{'+cat+'}') if token.startswith('[^') else ('\\p{'+cat+'}')
    add(family,p,subjects,oracle=oracle_pattern(forms[(i//len(cats))%len(forms)]%op));made+=1
   i+=1
def round5():
 # Uncased scalars must remain complete UTF-8 sequences under ignore-case.
 uncased=['中','文','€','😀','🧪','א','ا','ह','ก','あ','ア','한','々','∞','→']
 forms=['(?i)%s','(?i)^%s$','x(?i)%s','(?i:A%s)','(?i)(%s|Q)']
 for scalar in uncased:
  for form in forms[:2]:
   p=form%scalar; add('casefold_uncased',p,[scalar,'!'+scalar+'!','x'+scalar,scalar+'x'])
 for scalar in uncased[:10]:
  p='(?i)K'+scalar; add('casefold_uncased',p,['k'+scalar,'K'+scalar,scalar,'k'])

 # Python 3.11 rejects a global inline flag away from the start.  For the
 # oracle only, x(?i)y is translated to the equivalent scoped x(?i:y).
 inline=[('a(?i)b','a(?i:b)'),('A(?i)b','A(?i:b)'),
         ('ab(?i)c','ab(?i:c)'),('(a(?i)b)c','(a(?i:b))c'),
         ('(a|b(?i)c)d','(a|b(?i:c))d'),('x(?i:ab)y','x(?i:ab)y')]
 suffixes=['','+','?','|q','c','中']
 for raw,oracle in inline:
  for suffix in suffixes:
   p=raw+suffix; op=oracle+suffix
   add('inline_flags',p,['ab','aB','Ab','AB','abc','aBc','xabY','xABy','bCd','q','中'],oracle=op)

 tokens=[r'\p{Lu}',r'\p{Ll}',r'\P{Lu}',r'\P{Ll}',r'\p{L}',r'\P{L}']
 forms=['(?i)%s','(?i)^%s$','(?i)(%s)','x(?i)%s','(?i:%s)','(?i)%s+']
 subjects=['K','k','K','S','s','ſ','µ','μ','Μ','Ä','ä','中','𐐀','𐐨','!']
 for token in tokens:
  for form in forms:
   p=form%token; op=oracle_pattern(p.replace('x(?i)','x(?i:') + (')' if p.startswith('x(?i)') else ''))
   add('casefold_property',p,subjects,oracle=op)

 # Exercise every member in both roles for every full multi-member closure.
 seen=set()
 for cp in range(0x110000):
  if 0xd800<=cp<=0xdfff: continue
  c=chr(cp); members={c}
  todo=[c]
  while todo:
   x=todo.pop()
   for y in (x.lower(),x.upper(),x.title(),x.casefold()):
    if len(y)==1 and y not in members: members.add(y);todo.append(y)
  key=tuple(sorted(members))
  if len(key)>1 and key not in seen:
   seen.add(key)
   for pattern in key: add('casefold_closure','(?i)'+re.escape(pattern),list(key))

 invalid=['1x','-x','x-y','x y','é','中','😀','.x','x!','x/y',':x','x:y','x.y','x@y','x#y','x$y','x%y','x&y','x*y','x+y','x=y','x?y','x[y','x]y','x{y','x}y','x,y','x;y','x<y','x\\y']
 for name in invalid: reject('named_invalid','(?P<'+name+'>a)','invalid named capture identifier: '+name)
def main():
 bf=[r'\b%s\b',r'^\b%s\b$',r'(\b%s\b)',r'\b(%s)\b',r'\b%s\b!',r'!\b%s\b',r'(\b%s\b|never)',r'(never|\b%s\b)',r'\b%s+\b',r'\b%s\b.*']
 for t in ['cat','dog','a1','x_y','Z9']:
  for f in bf:add('boundary',f%t,[t,'!'+t+'!','x'+t,t+' tail','É'+t,'nothing'],re.ASCII)
 ff=['%s','^%s$','(%s)','%s+','%s+?','(%s|never)','(never|%s)','[x]%s','%s[0-9]?','%s.*']
 for t,others in [('cat',['CAT']),('Dog',['dOG']),('É',['é']),('Ä',['ä']),('Σ',['Σ','σ','ς']),('σ',['Σ','σ','ς']),('ς',['Σ','σ','ς'])]:
  for f in ff:add('casefold','(?i)'+f%t,[t,*others,*['!'+u+'!' for u in others],*['x'+u for u in others],'nothing'])
 nf=['(?P<%s>%s)','^(?P<%s>%s)$','(?P<%s>%s+)','(?P<%s>%s+?)','(?P<%s>%s|q)','(q|(?P<%s>%s))','(?P<%s>[%s])','(?P<%s>%s)?','(?P<%s>%s)*','((?P<%s>%s))']
 for root,t in [('alpha','a'),('bravo','b'),('charlie','c'),('delta','d'),('echo','e')]:
  for i,f in enumerate(nf):add('named',f%(root+str(i),t),[t,t*3,'!'+t+'!','q','','z'])
 properties()
 round5()
 enc=lambda x:json.dumps(x,ensure_ascii=False,separators=(',',':'))
 O.write_text('# Generated by tests/re2_diff.py; do not edit.\nre2_diff_cases is []\n' + ''.join('append of [re2_diff_cases,'+enc(c)+']\n' for c in C))
 for f in ['boundary','casefold','named','property_letters','property_numbers','property_psz','casefold_uncased','inline_flags','casefold_property','casefold_closure','named_invalid']:
  x=[c for c in C if c['feature']==f];print(f"generated feature={f} patterns={len(set(c['pattern'] for c in x))} subjects={len(x)}")
if __name__=='__main__':main()

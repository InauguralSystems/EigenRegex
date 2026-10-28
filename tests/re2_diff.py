#!/usr/bin/env python3
"""Generate differential fixtures.  google-re2, never Python re, is the oracle."""
import argparse,importlib.metadata,json,re,subprocess,tempfile
from pathlib import Path
import re2
VERSION=importlib.metadata.version('google-re2')
OUT=Path(__file__).with_name('re2_expected.eigs'); CASES=[]
# Convert google-re2's Python string indices to EigenRegex's UTF-8 byte offsets.
def bytepos(s,p): return -1 if p<0 else len(s[:p].encode('utf-8'))
def spans(s,m,r):
 return [bytepos(s,x) for pair in [m.span(),*[m.span(i) for i in range(1,r.groups+1)]] for x in pair]
def enc_string(s):
 out=[]
 escapes={'\\':'\\\\','"':'\\"','\n':'\\n','\t':'\\t','\r':'\\r'}
 for char in s:
  cp=ord(char)
  if cp==0: raise ValueError('cannot encode U+0000 in an EigenScript string literal: the lexer treats NUL as end of source')
  if 0xD800<=cp<=0xDFFF: raise ValueError(f'cannot encode U+{cp:04X}: surrogate code points are not Unicode scalars')
  out.append(escapes.get(char,char))
 return '"'+''.join(out)+'"'
def enc(value):
 if isinstance(value,str): return enc_string(value)
 if value is None: return 'null'
 if value is True: return 'true'
 if value is False: return 'false'
 if isinstance(value,(int,float)): return json.dumps(value,separators=(',',':'))
 if isinstance(value,list): return '['+','.join(enc(item) for item in value)+']'
 if isinstance(value,dict): return '{'+','.join(enc_string(key)+':'+enc(item) for key,item in value.items())+'}'
 raise TypeError(f'cannot encode {type(value).__name__} as an EigenScript literal')
def self_check(eigenscript):
 subject='\u0001\u0008'
 source='re2_generator_selfcheck_subject is '+enc(subject)+'\nprint of [len of re2_generator_selfcheck_subject,ord of re2_generator_selfcheck_subject[0],ord of re2_generator_selfcheck_subject[1]]\n'
 with tempfile.TemporaryDirectory() as tmp:
  path=Path(tmp)/'re2_generator_selfcheck.eigs'
  path.write_text(source,encoding='utf-8',newline='')
  raw=path.read_bytes()
  if subject.encode('utf-8') not in raw: raise SystemExit('self-check failed: U+0001 and U+0008 did not survive in the generated .eigs file as the same bytes')
  result=subprocess.run([eigenscript,str(path)],capture_output=True,text=True)
  if result.returncode or result.stdout.strip()!='[2, 1, 8]':
   raise SystemExit(f'self-check failed: EigenScript did not read back length 2 and code points U+0001/U+0008 (rc={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r})')
 try: enc_string('\0')
 except ValueError as error:
  if 'U+0000' not in str(error): raise
 else: raise SystemExit('self-check failed: encoder accepted unrepresentable U+0000')
 print('self-check: raw bytes and EigenScript readback agree for U+0001/U+0008; U+0000 refused')
def add(feature,pattern,subjects,operation='search'):
 try: rx=re2.compile(pattern)
 except Exception as e:
  CASES.append({'feature':feature,'pattern':pattern,'compile_ok':False,'subject':'','spans':None,'named':{}}); return
 if not subjects: CASES.append({'feature':feature,'pattern':pattern,'compile_ok':True,'subject':'','compile_only':True}); return
 for subject in subjects:
  if operation=='replace':
   CASES.append({'feature':feature,'pattern':pattern,'compile_ok':True,'operation':operation,'subject':subject,'replacement':'#','output':rx.sub('#',subject)}); continue
  if operation=='fullmatch':
   m=rx.fullmatch(subject)
   # Python and google-re2 are independent oracles for this contract.  Refuse
   # to generate a fixture unless both choose identical captures.
   py=re.fullmatch(pattern,subject)
   rs=spans(subject,m,rx) if m else None
   ps=[bytepos(subject,x) for pair in [py.span(),*[py.span(i) for i in range(1,rx.groups+1)]] for x in pair] if py else None
   if rs != ps: raise SystemExit(f'fullmatch oracles disagree: {pattern!r} on {subject!r}: google-re2={rs}, python={ps}')
   CASES.append({'feature':feature,'pattern':pattern,'compile_ok':True,'operation':operation,'subject':subject,'spans':rs}); continue
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
 # Every category added by #38, in both positive and negative form.
 new_categories=['M','Mn','Mc','Me','C','Cc','Cf','Cs','Co','Zs','Zl','Zp',
  'Pc','Pd','Ps','Pe','Pi','Pf','Po','Sm','Sc','Sk','So']
 category_subjects=['A','7','\u0301','\u0903','\u0488','\u0001','\u0378','\u200d','\ue000',' ',
  '\u2028','\u2029','_','-','(',')','«','»','!','+','$','^','😀','中','']
 for cat in new_categories:
  for prefix in ['\\p','\\P']:
   add('property_remaining',prefix+'{'+cat+'}',category_subjects)
 # More than fifty distinct unions of properties, literals, and ranges,
 # including whole-class negation. Python's stdlib `re` oracle cannot parse
 # \p, so google-re2 supplies expected results directly for these cases.
 tokens=[r'\p{L}',r'\P{L}',r'\p{N}',r'\p{M}',r'\p{Zs}',r'\p{Pc}']
 forms=['[%s0-9]','[0-9%s]','[%s_]','[_%s]','[%sa-z]','[a-z%s]',
  r'[%s\p{N}]',r'[\p{N}%s]','[^%s_]','[^_%s]']
 compound_subjects=['A','é','中','7','Ⅷ','_','-',' ','\u0301','😀','!','']
 for token in tokens:
  for form in forms:
   add('compound_property_class',form%token,compound_subjects)
def main(eigenscript=None):
 # Full-string priority is not leftmost-first search followed by an end check:
 # shorter preferred alternatives must be bypassed if only a later one ends at
 # the subject boundary.  Capture rows also pin the surviving path's priority.
 for pattern,subject in [
  ('a|ab','ab'),('ab|a','ab'),('a*?','aaa'),('a|',''),('|a','a'),
  ('(a)|(ab)','ab'),('(ab)|(a)','ab'),('((a)|ab)','ab')]:
  add('fullmatch',pattern,[subject],operation='fullmatch')
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
 # Negated sets exercise normalization before scalar complement: pattern order,
 # duplicates, overlap, non-ASCII, and ignore-case must not affect membership.
 neg_bodies=['za','zaza','zac','éa','é-éa','中a中','😀a😀','zaA-Z','Σσς','ÿÀ-Ö','a-cb-d','𐐀𐐨a','KkK','sſS','µΜμ']
 for i in range(30):
  body=neg_bodies[i%len(neg_bodies)]
  pattern=('(?i)' if i>=15 else '')+'[^'+body+']'+(['','+','$'][i%3])
  add('negated_class_sets',pattern,['z','a','b','é','É','中','😀','K','ſ','μ','𐐀','!','éa','😀a'])
 # RE2 shorthands are ASCII positive sets, but their complements consume one
 # complete Unicode scalar.  Cover every form on 2/3/4-byte text, around word
 # assertions, and under simple folding (notably Kelvin sign for (?i)\\w).
 shorthand_subjects=['éa','中a','😀a','é_','中7','😀 ','K','ſ','𐐀x','!é','!中','!😀']
 shorthand_forms=['%s','^%s','%s$','(%s)','%s+','%s?','%s\\b','%s\\B','\\b%s','\\B%s']
 shorthands=[r'\d',r'\D',r'\s',r'\S',r'\w',r'\W']
 for i in range(30):
  token=shorthands[i%len(shorthands)]
  pattern=shorthand_forms[(i//len(shorthands))%len(shorthand_forms)]%token
  if i%2: pattern='(?i)'+pattern
  add('unicode_shorthand',pattern,shorthand_subjects)
 # Inclusive scalar ranges spanning each UTF-8 width boundary.
 boundary_ranges=[('\x7f','\x80'),('\u07ff','\u0800'),('\uffff','𐀀')]
 range_forms=['[%s-%s]','^[%s-%s]$','([%s-%s])','[%s-%s]+','x|[%s-%s]','[%s-%s]|x','(?i)[%s-%s]','(?i)([%s-%s])','[%s-%s]?','[^%s-%s]']
 for form in range_forms:
  for lo,hi in boundary_ranges:
   add('utf8_boundary_ranges',form%(lo,hi),[lo,hi,'x','é','中','😀',lo+hi])
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
 # Parse-time issue #48: captureless groups in nested, alternated, and
 # quantified positions, plus every unsupported backreference spelling.
 noncapturing_bodies=['a','ab','a|b','(?:a)','(?:a|b)c','a(?:b|c)','(?:ab)+','(?:a?b)*','(?:a|bc){1,2}','']
 noncapturing_forms=['(?:%s)','^(?:%s)$','x(?:%s)','(?:%s)y','((?:%s))','(?:(?:%s))','(?:%s)|z']
 for i in range(35):
  body=noncapturing_bodies[i%len(noncapturing_bodies)]
  add('noncapturing_group',noncapturing_forms[(i//len(noncapturing_bodies))%len(noncapturing_forms)]%body,
      ['','a','b','ab','abc','xaby','abab','z'])
 for p in [r'(a)\1',r'(a)\2',r'(a)\3',r'(a)\4',r'(a)\5',r'(a)\6',r'(a)\7',r'(a)\8',r'(a)\9',
           r'(?P<x>a)(?P=x)',r'(?P<x>a)\k<x>',r'(a)\k<1>']:
  add('backreference_refusal',p,[])
 # Parse-time issue #49: supported escapes get RE2 values, while unknown
 # alphanumeric escapes are compile refusals rather than literal fallbacks.
 for p in [r'\n',r'\t',r'\r',r'\f',r'\v',r'\a',r'\x41',r'\x{41}',r'\x{1F600}',r'\Acat',r'cat\z',
           r'[\n]',r'[\t]',r'[\x41]',r'[\x{1F600}]']:
  add('supported_escape',p,['','A','cat','cat\n','\n','\t','\r','\f','\v','\a','😀','xcat','catx'])
 for p in [r'\q',r'\y',r'\e',r'\g',r'\h',r'\i',r'\j',r'\l',r'\m',r'\o',r'\u0041']:
  add('unknown_escape_refusal',p,[])
 for p in [r'[^\x{0}-\x{10FFFF}]',r'(?i)[^\x{0}-\x{10FFFF}]']:
  add('empty_scalar_class',p,['','A','é','中','😀','\n'])
 header=f'# Generated by tests/re2_diff.py with google-re2 {VERSION}; do not edit.\nre2_oracle_version is {enc(VERSION)}\nre2_diff_cases is []\n'
 OUT.write_text(header+''.join('append of [re2_diff_cases,'+enc(c)+']\n' for c in CASES),encoding='utf-8',newline='')
 for f in sorted({c['feature'] for c in CASES}):
  x=[c for c in CASES if c['feature']==f]; print(f'feature={f} patterns={len({c["pattern"] for c in x})} subjects={len(x)} oracle=google-re2-{VERSION}')
 if eigenscript: self_check(eigenscript)
if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('--self-check',metavar='EIGENSCRIPT',help='also verify control-character output with this pinned EigenScript binary')
 args=parser.parse_args()
 main(args.self_check)

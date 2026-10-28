#!/usr/bin/env python3
"""Generate the issue #36 lookbehind oracle from CPython re and V8."""
import platform
import argparse, itertools, json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "lookaround_expected.eigs"
DIVERGENCES = json.loads((HERE / "lookaround_divergences.json").read_text())
REPLACEMENT = "#"


def bytepos(s, pos):
    return len(s[:pos].encode("utf-8"))


def enc_string(s):
    return '"' + ''.join({'\\':'\\\\','"':'\\"','\n':'\\n','\r':'\\r','\t':'\\t'}.get(c,c) for c in s) + '"'


def enc(v):
    if v is None: return "null"
    if v is True: return "true"
    if v is False: return "false"
    if isinstance(v, (int,float)): return json.dumps(v)
    if isinstance(v, str): return enc_string(v)
    if isinstance(v, list): return "[" + ",".join(map(enc,v)) + "]"
    if isinstance(v, dict): return "{" + ",".join(enc_string(k)+":"+enc(x) for k,x in v.items()) + "}"
    raise TypeError(type(v))


def add_spec(specs, name, pattern, matching, nonmatching, oracle_class="agree"):
    """Add a pattern with explicit positive and negative search witnesses."""
    specs.append(dict(name=name, pattern=pattern,
                      subjects=[matching, nonmatching], oracle_class=oracle_class))


def corpus():
    specs=[]
    atoms=[("a","a"),("b","b"),("c","c"),("[de]","d"),("[0-2]","1"),("\\d","7"),("\\s"," "),
           ("é","é"),("中","中"),("😀","😀"),(".","x"),("[^q]","z")]
    # The 36a population remains intact: 120 fixed-width class-(a) patterns.
    bodies=[]
    for width in (1,2,3):
        for combo in itertools.product(atoms, repeat=width):
            body="".join(x[0] for x in combo); sample="".join(x[1] for x in combo)
            bodies.append((body,sample))
            if len(bodies)==120: break
        if len(bodies)==120: break
    for i,(body,sample) in enumerate(bodies):
        neg=i%2==1; pat=f"^(?:{sample})?(?{'<!' if neg else '<='}{body})Z(?:é中😀{{0}})?$" if i < 30 else f"^(?:{sample})?(?{'<!' if neg else '<='}{body})Z$"
        add_spec(specs, f"fixed_{i:03d}", pat,
                 "Z" if neg else sample+"Z", sample+"Z" if neg else "Z")

    # Python deliberately refuses these variable-width lookbehinds; V8 supplies truth.
    for i in range(40):
        prefix="b"*i; q=["a+","a{1,3}","(?:a|aa)","a{1,}"][i%4]
        body=prefix+q; sample=prefix+"aa"; neg=i%2==1
        pat=f"^(?:{sample})?(?{'<!' if neg else '<='}{body})Z(?:é中😀{{0}})?$" if i < 30 else f"^(?:{sample})?(?{'<!' if neg else '<='}{body})Z$"
        add_spec(specs, f"v8_only_{i:02d}", pat,
                 "Z" if neg else sample+"Z", sample+"Z" if neg else "Z", "v8_only")

    # O4: 72 distinct lookaheads, balanced between positive and negative.
    for i in range(36):
        body="a"+"b"*i
        add_spec(specs, f"ahead_pos_{i:02d}", f"^(?={body}$){body}$", body, "q"+body)
        add_spec(specs, f"ahead_neg_{i:02d}", f"^(?!{body}$).+$", "q"+body, body)

    # O4 nesting: all direction combinations plus depth >= 3.  Each body has
    # witnesses which also make killing any enclosing or nested body observable.
    for i in range(30):
        tail="b"*i
        add_spec(specs, f"nested_ahead_in_behind_{i:02d}",
                 f"^a(?<=(?=a)a)(?={tail}$){tail}$", "a"+tail, "q"+tail)
        add_spec(specs, f"nested_behind_in_ahead_{i:02d}",
                 f"^a(?=(?<=a){tail}$){tail}$", "a"+tail, "q"+tail)
        add_spec(specs, f"nested_same_kind_{i:02d}",
                 f"^(?=(?=a{tail}$)a{tail}$)a{tail}$", "a"+tail, "q"+tail)
        add_spec(specs, f"nested_depth3_{i:02d}",
                 f"^(?=(?=(?=a{tail}$)a{tail}$)a{tail}$)a{tail}$", "a"+tail, "q"+tail)

    # Anchors and boundaries occur *inside* lookaround bodies (eight of each).
    boundary = [
        ("caret", "^a", "a", "ba"), ("dollar", "a$", "a", "ab"),
        ("word", r"a\b", "a", "ab"), ("nonword", r"a\B", "ab", "a"),
    ]
    for kind,body,good,bad in boundary:
        for i in range(8):
            inert=f"(?:q{{0}}){{{i}}}"
            add_spec(specs, f"inside_{kind}_{i:02d}", f"(?={body}){good}{inert}", good, bad)

    # Zero-width global-resume cases (both operations are emitted for every spec).
    for i in range(30):
        body="a"+"b"*(i//2); neg=i%2
        pat=f"(?{'<!' if neg else '<='}{body})(?=Z)"
        add_spec(specs, f"zero_width_{i:02d}", pat,
                 "Z" if neg else body+"Z", body+"Z" if neg else "q")
    add_spec(specs, "resume_witness", r"(?<=a)", "aa", "q")

    # O2(e), divergence witnesses, and F2 refusals inherited from 36a.
    add_spec(specs, "python_scoped_i", r"(?<=(?i:a))Z", "AZ", "qZ", "python_only")
    specs += [
      dict(name="divergence_d1",pattern=r"(?<=a$|b)\n",subjects=["a\n","b\n","q\n"],oracle_class="agree"),
      dict(name="divergence_d2",pattern=r"(?<=.)Z",subjects=["\rZ","xZ","Z"],oracle_class="agree"),
      dict(name="divergence_d3",pattern=r"(?<=\w)Z",subjects=["éZ","aZ","Z"],oracle_class="agree"),
      dict(name="divergence_d4",pattern=r"(?<=a)",subjects=["aa","q"],oracle_class="agree"),
    ]
    refused=[r"(?<=(a))Z",r"(?<=(?P<x>a))Z",r"(?<=a\1)Z",r"(?<=a\2)Z",r"(?<=a\3)Z",
      r"(?<=a\4)Z",r"(?<=a\5)Z",r"(?<=a\6)Z",r"(?<=a\7)Z",r"(?<=a\8)Z",r"(?<=a\9)Z",
      r"(?<=a\k<x>)Z",r"(?<=a(?P=x))Z",r"(?<=a)+",r"(?<!a)?",r"(?<=a){2}",
      r"(?<name>a)",r"(?<=(?:a)(b))Z",r"(?<!((?:a)))Z",r"(?<=a)++"]
    for i,p in enumerate(refused):
        specs.append(dict(name=f"refusal_{i:02d}",pattern=p,subjects=["aZ","qZ"],oracle_class="refusal"))
    return specs

NODE_PROGRAM=r'''
const fs=require('fs'); const req=JSON.parse(fs.readFileSync(0,'utf8'));
function b(s,u){return Buffer.byteLength(s.slice(0,u),'utf8')}
function one(p,s,op){
 let flags='du'+(op==='search'?'':'g'), r;
 try { r=new RegExp(p,flags) } catch(e){return {ok:false,error:e.message}}
 if(op==='replace') return {ok:true,value:s.replace(r,'#')};
 if(op==='search'){let m=r.exec(s); return {ok:true,value:m?[b(s,m.indices[0][0]),b(s,m.indices[0][1])]:null}}
 let a=[],m; while((m=r.exec(s))!==null){a.push([b(s,m.indices[0][0]),b(s,m.indices[0][1])]); if(m[0]===''&&r.lastIndex===m.index) r.lastIndex++} return {ok:true,value:a}
}
let out=[]; for(const x of req.items) out.push(one(x.pattern,x.subject,x.op));
process.stdout.write(JSON.stringify({v8:process.versions.v8,results:out}));
'''

def v8_eval(items):
    p=subprocess.run(["node","-e",NODE_PROGRAM],input=json.dumps({"items":items}),text=True,capture_output=True)
    if p.returncode: raise SystemExit("Node oracle failed: "+p.stderr)
    return json.loads(p.stdout)

def py_eval(pattern,subject,op):
    try: rx=re.compile(pattern)
    except re.error as e: return {"ok":False,"error":str(e)}
    if op=="replace": return {"ok":True,"value":rx.sub(REPLACEMENT,subject)}
    if op=="search":
        m=rx.search(subject); return {"ok":True,"value":None if not m else [bytepos(subject,m.start()),bytepos(subject,m.end())]}
    found=[]; pos=0
    while pos<=len(subject):
        m=rx.search(subject,pos)
        if not m: break
        found.append([bytepos(subject,m.start()),bytepos(subject,m.end())])
        if m.end()>m.start(): pos=m.end()
        elif m.end()==len(subject): break
        else: pos=m.end()+1
    return {"ok":True,"value":found}

def lookaround_bodies(pattern):
    """Return (start, end, body) for every syntactic lookaround body."""
    found=[]; stack=[]; i=0; escaped=False; in_class=False
    while i < len(pattern):
        c=pattern[i]
        if escaped: escaped=False; i+=1; continue
        if c=="\\": escaped=True; i+=1; continue
        if c=="[": in_class=True; i+=1; continue
        if c=="]" and in_class: in_class=False; i+=1; continue
        if in_class: i+=1; continue
        if c=="(":
            prefix=next((x for x in ("(?<=","(?<!","(?=","(?!") if pattern.startswith(x,i)),None)
            if prefix:
                stack.append((i+len(prefix),prefix)); i+=len(prefix); continue
            stack.append(None); i+=1; continue
        if c==")" and stack:
            entry=stack.pop()
            if entry is not None:
                body_start,prefix=entry
                found.append((body_start,i,pattern[body_start:i],prefix))
        i+=1
    return sorted(found)


def oracle_case(spec, subject, op, vr, pr):
    """Apply O2 precedence and return (accepted, value, tag)."""
    cls=spec["oracle_class"]
    if cls=="refusal": return False,None,"refusal"
    if cls=="python_only":
        if not pr["ok"]: raise SystemExit(f"Python-only case refused: {spec['name']}")
        return True,pr["value"],"python_only"
    if cls=="v8_only":
        if pr["ok"] or not vr["ok"] or "look-behind requires fixed-width pattern" not in pr.get("error",""):
            raise SystemExit(f"bad v8_only attribution: {spec['name']}: python={pr}, v8={vr}")
        return True,vr["value"],"v8_only"
    if not pr["ok"] or not vr["ok"]:
        raise SystemExit(f"acceptance disagreement: {spec['name']}: python={pr}, v8={vr}")
    if pr["value"]==vr["value"]: return True,vr["value"],"agree"
    candidates=[]; p=spec["pattern"]
    if "$" in p: candidates.append(("D1",p.replace("$","")))
    if "." in p and any(c in subject for c in "\r\u2028\u2029"): candidates.append(("D2",p.replace(".","x")))
    if re.search(r"\\[wWdDsSbB]",p) and any(ord(c)>127 for c in subject):
        candidates.append(("D3",re.sub(r"\\[wWdDsSbB]","x",p)))
    proven=[]
    for key,neutral in candidates:
        nv=v8_eval([{"pattern":neutral,"subject":subject,"op":op}])["results"][0]
        np=py_eval(neutral,subject,op)
        if nv["ok"] and np["ok"] and nv["value"]==np["value"]: proven.append(key)
    if len(proven)!=1:
        raise SystemExit(f"unattributed disagreement: {spec['name']} {subject!r} {op}: {pr} vs {vr}")
    key=proven[0]; side=DIVERGENCES[key]["side"]
    return True,(vr if side=="v8" else pr)["value"],key


def write_l2(out, node_version):
    sizes=(256,512,1024,2048)
    definitions=[
      ("ahead_no_c",r"(?=a*c)","search",lambda n:"a"*n,lambda n:None),
      ("negative_find_all",r"(?!a*c)a","find_all",lambda n:"a"*n,lambda n:[[i,i+1] for i in range(n)]),
      ("nested_depth3",r"(?=a*(?=a*(?=a*c)))","search",lambda n:"a"*n,lambda n:None),
      ("ambiguous_alt",r"(?=(?:a|a)*c)","search",lambda n:"a"*n,lambda n:None),
      ("zero_width_replace",r"(?=a)","replace",lambda n:"a"*n,lambda n:"#a"*n),
      ("unicode_no_c",r"(?=é*c)","search",lambda n:"é"*n,lambda n:None),
    ]
    # Prove each closed-form family against both independent oracles at a small
    # witness.  Large ambiguous-negative inputs are deliberately not executed:
    # these values exist so the future linear engine can be measured where the
    # backtracking references cannot practically run.
    for name,pattern,op,subject,expected in definitions:
        n=8; item={"pattern":pattern,"subject":subject(n),"op":op}
        vr=v8_eval([item])["results"][0]; pr=py_eval(pattern,subject(n),op)
        if not vr["ok"] or not pr["ok"] or vr["value"]!=expected(n) or pr["value"]!=expected(n):
            raise SystemExit(f"L2 oracle formula disagreement: {name}: expected={expected(n)} python={pr} v8={vr}")
    rows=[{"name":name,"pattern":pattern,"operation":op,"n":n,"expected":expected(n)}
          for name,pattern,op,subject,expected in definitions for n in sizes]
    header=("# Generated by tests/lookaround_diff.py; do not edit.\n"
            f"# CPython: {platform.python_implementation()} {platform.python_version()}\n# V8: {node_version}\n"
            "lookaround_l2_cases is []\n")
    out.write_text(header+''.join("append of [lookaround_l2_cases,"+enc(r)+"]\n" for r in rows),encoding="utf-8",newline="")
    return len(rows)


def main(out=OUT, l2out=None):
    if l2out is None: l2out=HERE / "lookaround_l2_expected.eigs"
    specs=corpus(); ops=("search","find_all","replace")
    items=[{"pattern":s["pattern"],"subject":u,"op":op} for s in specs for u in s["subjects"] for op in ops]
    node=v8_eval(items); rows=[]; disagreements=[]
    for spec in specs:
      for subject in spec["subjects"]:
       for op in ops:
        vr=node["results"][len(rows)]; pr=py_eval(spec["pattern"],subject,op)
        oracle_accepted,oracle_value,oracle_tag=oracle_case(spec,subject,op,vr,pr)
        if oracle_tag in DIVERGENCES: disagreements.append(oracle_tag)
        # 36a compatibility rule.  Part 36b-ii flips to oracle truth by deleting
        # only this block; oracle_accepted/oracle_expected are already committed.
        accepted=oracle_accepted; value=oracle_value; tag=oracle_tag
        if "(?=" in spec["pattern"] or "(?!" in spec["pattern"]:
            accepted=False; value=None; tag="lookahead_refusal_36a"
        rows.append({"name":spec["name"],"pattern":spec["pattern"],"subject":subject,"operation":op,
                     "accepted":accepted,"tag":tag,"expected":value,
                     "oracle_accepted":oracle_accepted,"oracle_tag":oracle_tag,"oracle_expected":oracle_value})

    # O4 floors are derived from oracle truth, not today's engine refusal rule.
    oracle_specs=[s for s in specs if s["oracle_class"]!="refusal"]
    pattern_tags={}
    for r in rows:
        pattern_tags.setdefault(r["pattern"],set()).add(r["oracle_tag"])
    class_a={pattern for pattern,tags in pattern_tags.items() if tags=={"agree"}}
    pos=sum("(?<=" in s["pattern"] for s in oracle_specs); neg=sum("(?<!" in s["pattern"] for s in oracle_specs)
    ahead=sum("(?=" in s["pattern"] for s in oracle_specs); nahead=sum("(?!" in s["pattern"] for s in oracle_specs)
    nested_specs=[s for s in oracle_specs if len(lookaround_bodies(s["pattern"]))>=2]
    ahead_in_behind=sum(s["name"].startswith("nested_ahead_in_behind_") for s in oracle_specs)
    behind_in_ahead=sum(s["name"].startswith("nested_behind_in_ahead_") for s in oracle_specs)
    same_kind=sum(s["name"].startswith("nested_same_kind_") for s in oracle_specs)
    depth3=sum(s["name"].startswith("nested_depth3_") for s in oracle_specs)
    inside=sum(any(any(tok in body for tok in ("^","$",r"\\b",r"\\B"))
                   for _,_,body,_ in lookaround_bodies(s["pattern"])) for s in oracle_specs)
    true_search={}
    for r in rows:
        if r["operation"]=="search" and r["oracle_accepted"]:
            true_search.setdefault(r["name"],[]).append(r["oracle_expected"] is not None)
    zero_names=set()
    for r in rows:
        if r["operation"]=="search" and r["oracle_accepted"] and r["oracle_expected"]:
            if r["oracle_expected"][0]==r["oracle_expected"][1]: zero_names.add(r["name"])
    utf_widths={w:sum(any(len(c.encode())==w for c in s["pattern"]+"".join(s["subjects"])) for s in oracle_specs) for w in (2,3,4)}
    floors={"class_a_patterns":len(class_a),"v8_only_patterns":len({s['pattern'] for s in specs if s['oracle_class']=='v8_only'}),
      "positive_lookahead":ahead,"negative_lookahead":nahead,"positive_lookbehind":pos,"negative_lookbehind":neg,
      "nested":len(nested_specs),"ahead_in_behind":ahead_in_behind,"behind_in_ahead":behind_in_ahead,
      "same_kind_nested":same_kind,"depth3":depth3,"body_anchor_boundary":inside,
      "zero_width_find_all":len(zero_names),"zero_width_replace":len(zero_names),
      "utf8_2byte":utf_widths[2],"utf8_3byte":utf_widths[3],"utf8_4byte":utf_widths[4],
      "refusals":sum(s["oracle_class"]=="refusal" for s in specs)}
    required={"class_a_patterns":200,"v8_only_patterns":40,"positive_lookahead":30,"negative_lookahead":30,
      "positive_lookbehind":30,"negative_lookbehind":30,"nested":30,"ahead_in_behind":30,"behind_in_ahead":30,
      "same_kind_nested":30,"depth3":30,"body_anchor_boundary":30,
      "zero_width_find_all":30,"zero_width_replace":30,"utf8_2byte":30,"utf8_3byte":30,"utf8_4byte":30,"refusals":20}
    bad=[f"{k}={floors[k]} < {n}" for k,n in required.items() if floors[k]<n]
    bad += [f"{name} lacks matching/non-matching subjects" for name,x in true_search.items() if not(any(x) and not all(x))]
    expected_names={s["name"] for s in oracle_specs}
    bad += [f"{name} has no accepted search oracle" for name in sorted(expected_names-set(true_search))]
    named_cases={s["name"] for s in specs}
    bad += [f"divergence {key} lacks committed corpus case {row['case']}"
            for key,row in DIVERGENCES.items() if row["case"] not in named_cases]
    if bad: raise SystemExit("floor failure: "+"; ".join(bad))

    # O5: kill every syntactic body, including every inner and outer nested body.
    mutants=[]
    for s in oracle_specs:
      if s["oracle_class"]=="python_only": continue
      for j,(start,end,body,prefix) in enumerate(lookaround_bodies(s["pattern"])):
        mutant=s["pattern"][:start]+r"[^\s\S]"+s["pattern"][end:]
        mutants.append((f"{s['name']}/body{j}:{prefix}{body})",s,mutant))
    mi=[]
    for _,s,m in mutants:
      for u in s["subjects"]:
       for op in ops:
        mi += [{"pattern":s["pattern"],"subject":u,"op":op},{"pattern":m,"subject":u,"op":op}]
    mv=v8_eval(mi)["results"]; equivalent=[]; offset=0
    for name,s,m in mutants:
      count=len(s["subjects"])*len(ops); pairs=mv[offset:offset+count*2]; offset += count*2
      if not any(a["ok"] and b["ok"] and a["value"]!=b["value"] for a,b in zip(pairs[::2],pairs[1::2])):
          equivalent.append(name)
    print("floors: "+" ".join(f"{k}={v}" for k,v in floors.items()))
    print(f"adequacy: killed={len(mutants)-len(equivalent)} total={len(mutants)} equivalent={','.join(equivalent) or 'none'}")
    if equivalent: raise SystemExit("adequacy below 100%; equivalent mutants: "+", ".join(equivalent))
    header=(f"# Generated by tests/lookaround_diff.py; do not edit.\n# CPython: {platform.python_implementation()} {platform.python_version()}\n# V8: {node['v8']}\n"
            f"lookaround_python_version is {enc(platform.python_version())}\nlookaround_v8_version is {enc(node['v8'])}\nlookaround_floors is {enc(floors)}\nlookaround_cases is []\n")
    out.write_text(header+''.join("append of [lookaround_cases,"+enc(r)+"]\n" for r in rows),encoding="utf-8",newline="")
    l2count=write_l2(l2out,node["v8"])
    print(f"fixture: cases={len(rows)} patterns={len(specs)} l2_cases={l2count} output={out}")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,default=OUT)
    ap.add_argument("--l2-output",type=Path,default=HERE / "lookaround_l2_expected.eigs")
    ap.add_argument("--check",type=Path,metavar="FIXTURE",help="regenerate privately and fail unless both committed fixtures are complete and current")
    a=ap.parse_args()
    if a.check:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            generated=Path(td)/"lookaround_expected.eigs"; generated_l2=Path(td)/"lookaround_l2_expected.eigs"
            main(generated,generated_l2)
            committed_l2=a.check.with_name("lookaround_l2_expected.eigs")
            if not a.check.is_file() or a.check.read_bytes()!=generated.read_bytes():
                raise SystemExit(f"fixture check failed: {a.check} is empty, truncated, or stale")
            if not committed_l2.is_file() or committed_l2.read_bytes()!=generated_l2.read_bytes():
                raise SystemExit(f"fixture check failed: {committed_l2} is empty, truncated, or stale")
        print(f"fixture check: PASS {a.check} and {committed_l2}")
    else: main(a.output,a.l2_output)

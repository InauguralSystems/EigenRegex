#!/usr/bin/env python3
"""Generate the issue #36 lookbehind oracle from CPython re and V8."""
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


def corpus():
    specs=[]
    atoms=[("a","a"),("b","b"),("c","c"),("[de]","d"),("[0-2]","1"),("\\d","7"),("\\s"," "),
           ("é","é"),("中","中"),("😀","😀"),(".","x"),("[^q]","z")]
    # 120 fixed-width class-(a) patterns, balanced between positive/negative.
    bodies=[]
    for width in (1,2,3):
        for combo in itertools.product(atoms, repeat=width):
            body="".join(x[0] for x in combo); sample="".join(x[1] for x in combo)
            bodies.append((body,sample,[x[0] for x in combo]))
            if len(bodies)==120: break
        if len(bodies)==120: break
    for i,(body,sample,nodes) in enumerate(bodies):
        neg=i%2==1; pat=f"(?{'<!' if neg else '<='}{body})Z"
        subjects=[("Z" if neg else sample+"Z"),(sample+"Z" if neg else "Z")]
        subjects.append(subjects[0]+"é中😀")
        specs.append(dict(name=f"fixed_{i:03d}",pattern=pat,subjects=subjects,nodes=nodes,oracle_class="agree"))
    # 40 Python-variable-width/V8-only patterns.
    for i in range(40):
        prefix="b"*i; q=["a+","a{1,3}","(?:a|aa)","a{1,}"][i%4]
        body=prefix+q; sample=prefix+"aa"
        neg=i%2==1; pat=f"(?{'<!' if neg else '<='}{body})Z"
        subjects=[("Z" if neg else sample+"Z"),(sample+"Z" if neg else "Z")]
        specs.append(dict(name=f"v8_only_{i:02d}",pattern=pat,subjects=subjects,nodes=[body],oracle_class="v8_only"))
    # Thirty zero-width patterns exercise global resume for both operations.
    for i in range(30):
        body="a"+"b"*(i//2); sample=body
        neg=i%2; pat=f"(?{'<!' if neg else '<='}{body})(?=Z)"
        subjects=[("Z" if neg else sample+"Z"),(sample+"Z" if neg else "q")]
        specs.append(dict(name=f"zero_width_{i:02d}",pattern=pat,subjects=subjects,nodes=[body],oracle_class="agree"))
    # The required resume-point witness.
    specs.append(dict(name="resume_witness",pattern="(?<=a)",subjects=["aa","q"],nodes=["a"],oracle_class="agree"))
    # O2(e): scoped ignore-case is deliberately Python-only and ASCII-only.
    specs.append(dict(name="python_scoped_i",pattern="(?<=(?i:a))Z",subjects=["AZ","qZ"],nodes=["(?i:a)"],oracle_class="python_only"))
    # Committed divergence witnesses. D4 uses the mandated scalar-resume Python loop.
    specs += [
      dict(name="divergence_d1",pattern=r"(?<=a$|b)\n",subjects=["a\n","b\n","q\n"],nodes=["a$|b"],oracle_class="agree"),
      dict(name="divergence_d2",pattern=r"(?<=.)Z",subjects=["\rZ","xZ","Z"],nodes=["."],oracle_class="agree"),
      dict(name="divergence_d3",pattern=r"(?<=\w)Z",subjects=["éZ","aZ"],nodes=[r"\w"],oracle_class="agree"),
      dict(name="divergence_d4",pattern=r"(?<=a)",subjects=["aa","q"],nodes=["a"],oracle_class="agree"),
    ]
    # F2/refusal and acceptance-disagreement corpus.
    refused=[r"(?<=(a))Z",r"(?<=(?P<x>a))Z",r"(?<=a\1)Z",r"(?<=a\2)Z",r"(?<=a\3)Z",
      r"(?<=a\4)Z",r"(?<=a\5)Z",r"(?<=a\6)Z",r"(?<=a\7)Z",r"(?<=a\8)Z",r"(?<=a\9)Z",
      r"(?<=a\k<x>)Z",r"(?<=a(?P=x))Z",r"(?<=a)+",r"(?<!a)?",r"(?<=a){2}",
      r"(?<name>a)",r"(?<=(?:a)(b))Z",r"(?<!((?:a)))Z",r"(?<=a)++"]
    for i,p in enumerate(refused): specs.append(dict(name=f"refusal_{i:02d}",pattern=p,subjects=["aZ","qZ"],nodes=[],oracle_class="refusal"))
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

def main(out=OUT):
    specs=corpus(); ops=("search","find_all","replace")
    items=[{"pattern":s["pattern"],"subject":u,"op":op} for s in specs for u in s["subjects"] for op in ops]
    node=v8_eval(items); rows=[]; disagreements=[]
    for spec in specs:
      for subject in spec["subjects"]:
       for op in ops:
        vr=node["results"][len(rows)]; pr=py_eval(spec["pattern"],subject,op); cls=spec["oracle_class"]
        if cls=="refusal": value=None; accepted=False; tag="refusal"
        elif cls=="python_only":
            if not pr["ok"]: raise SystemExit(f"Python-only case refused: {spec['name']}")
            value=pr["value"]; accepted=True; tag="python_only"
        elif cls=="v8_only":
            if pr["ok"] or not vr["ok"] or "look-behind requires fixed-width pattern" not in pr.get("error",""):
                raise SystemExit(f"bad v8_only attribution: {spec['name']}: python={pr}, v8={vr}")
            value=vr["value"]; accepted=True; tag="v8_only"
        else:
            if not pr["ok"] or not vr["ok"]: raise SystemExit(f"acceptance disagreement: {spec['name']}: python={pr}, v8={vr}")
            if pr["value"]!=vr["value"]:
                # Only committed constructs may disagree; neutralization must agree.
                candidates=[]
                p=spec["pattern"]
                if "$" in p: candidates.append(("D1",p.replace("$","")))
                if "." in p and any(c in subject for c in "\r\u2028\u2029"): candidates.append(("D2",p.replace(".","x")))
                if re.search(r"\\[wWdDsSbB]",p) and any(ord(c)>127 for c in subject): candidates.append(("D3",re.sub(r"\\[wWdDsSbB]","x",p)))
                proven=[]
                for key,neutral in candidates:
                    nv=v8_eval([{"pattern":neutral,"subject":subject,"op":op}])["results"][0]; np=py_eval(neutral,subject,op)
                    if nv["ok"] and np["ok"] and nv["value"]==np["value"]: proven.append(key)
                if len(proven)!=1: raise SystemExit(f"unattributed disagreement: {spec['name']} {subject!r} {op}: {pr} vs {vr}")
                key=proven[0]; disagreements.append(key); side=DIVERGENCES[key]["side"]
                value=(vr if side=="v8" else pr)["value"]; tag=key
            else: value=vr["value"]; tag="agree"
            accepted=True
        rows.append({"name":spec["name"],"pattern":spec["pattern"],"subject":subject,"operation":op,"accepted":accepted,"tag":tag,"expected":value})
    # O4 runtime floors.
    accepted_specs=[s for s in specs if s["oracle_class"] in ("agree","v8_only","python_only")]
    agree=len({s["pattern"] for s in specs if s["oracle_class"]=="agree"})
    v8only=len({s["pattern"] for s in specs if s["oracle_class"]=="v8_only"})
    pos=sum("(?<=" in s["pattern"] for s in accepted_specs); neg=sum("(?<!" in s["pattern"] for s in accepted_specs)
    zero={s["name"] for s in specs if s["name"].startswith("zero_width_") or s["name"]=="resume_witness"}
    utf_widths={width:sum(any(len(c.encode())==width for c in s["pattern"]+"".join(s["subjects"])) for s in accepted_specs) for width in (2,3,4)}
    refusals=sum(s["oracle_class"]=="refusal" for s in specs)
    floors={"agree_patterns":agree,"v8_only_patterns":v8only,"positive_lookbehind":pos,"negative_lookbehind":neg,
            "zero_width_find_all":len(zero),"zero_width_replace":len(zero),"utf8_2byte":utf_widths[2],
            "utf8_3byte":utf_widths[3],"utf8_4byte":utf_widths[4],"refusals":refusals}
    required={"agree_patterns":120,"v8_only_patterns":40,"positive_lookbehind":30,"negative_lookbehind":30,
              "zero_width_find_all":30,"zero_width_replace":30,"refusals":20}
    bad=[f"{k}={floors[k]} < {n}" for k,n in required.items() if floors[k]<n]
    # Every accepted pattern must have a matching and non-matching search subject.
    byname={}
    for r in rows:
      if r["operation"]=="search" and r["accepted"]: byname.setdefault(r["name"],[]).append(r["expected"] is not None)
    bad += [f"{name} lacks matching/non-matching subjects" for name,x in byname.items() if not (any(x) and not all(x))]
    bad += [f"UTF-8 width {width} has only {count} patterns" for width,count in utf_widths.items() if count<30]
    if bad: raise SystemExit("floor failure: "+"; ".join(bad))
    # O5: replace each declared body node, one at a time; every mutant must flip a V8 value.
    mutants=[]
    for s in accepted_specs:
      if s["oracle_class"]=="python_only": continue
      start=s["pattern"].find("(?<=")+4 if "(?<=" in s["pattern"] else s["pattern"].find("(?<!")+4
      cursor=start
      for j,nodepart in enumerate(s["nodes"]):
        at=s["pattern"].find(nodepart,cursor)
        mutant=s["pattern"][:at]+r"[^\s\S]"+s["pattern"][at+len(nodepart):]
        mutants.append((f"{s['name']}/node{j}:{nodepart}",s,mutant)); cursor=at+len(nodepart)
    mi=[]
    for _,s,m in mutants:
      for u in s["subjects"]:
       for op in ops:
        mi += [{"pattern":s["pattern"],"subject":u,"op":op},{"pattern":m,"subject":u,"op":op}]
    mv=v8_eval(mi)["results"]; equivalent=[]; offset=0
    for name,s,m in mutants:
      count=len(s["subjects"])*3; pairs=mv[offset:offset+count*2]; offset += count*2
      if not any(a["ok"] and b["ok"] and a["value"]!=b["value"] for a,b in zip(pairs[::2],pairs[1::2])): equivalent.append(name)
    print("floors: "+" ".join(f"{k}={v}" for k,v in floors.items()))
    print(f"adequacy: killed={len(mutants)-len(equivalent)} total={len(mutants)} equivalent={','.join(equivalent) or 'none'}")
    if equivalent: raise SystemExit("adequacy below 100%; equivalent mutants: "+", ".join(equivalent))
    header=(f"# Generated by tests/lookaround_diff.py; do not edit.\n# CPython: {sys.version.replace(chr(10),' ')}\n# V8: {node['v8']}\n"
            f"lookaround_python_version is {enc(sys.version)}\nlookaround_v8_version is {enc(node['v8'])}\nlookaround_floors is {enc(floors)}\nlookaround_cases is []\n")
    out.write_text(header+''.join("append of [lookaround_cases,"+enc(r)+"]\n" for r in rows),encoding="utf-8",newline="")
    print(f"fixture: cases={len(rows)} patterns={len(specs)} output={out}")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--output",type=Path,default=OUT)
    ap.add_argument("--check",type=Path,metavar="FIXTURE",help="regenerate privately and fail unless FIXTURE is complete and current")
    a=ap.parse_args()
    if a.check:
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            generated=Path(td)/"lookaround_expected.eigs"; main(generated)
            if not a.check.is_file() or a.check.read_bytes()!=generated.read_bytes():
                raise SystemExit(f"fixture check failed: {a.check} is empty, truncated, or stale")
        print(f"fixture check: PASS {a.check}")
    else: main(a.output)

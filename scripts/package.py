#!/usr/bin/env python3
"""Create a portable source/full ZIP, excluding private configs and binaries."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from validate import ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--kind",choices=("source","full"),default="source")
    p.add_argument("--final",action="store_true")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.final:
        if args.kind!="full": p.error("final requires kind=full")
        pdf=ROOT/"report"/"report.pdf"
        if not pdf.exists() or pdf.read_bytes()[:5]!=b"%PDF-": p.error("missing real report/report.pdf")
        team=(ROOT/"report"/"team.csv").read_text()
        if "TO_FILL" in team: p.error("fill all three names and student IDs in report/team.csv")
        official=[]
        for path in (ROOT/"results"/"raw").rglob("metadata.json"):
            if (path.parent/"COMPLETE").exists():
                m=json.loads(path.read_text())
                if m.get("cluster") in ("Atlas","Vanda"): official.append(m)
        if not any(m.get("nodes",0)>=2 for m in official):
            p.error("no complete official multi-node run found")
    include_dirs={"src","scripts","configs","docs","report"}
    if args.kind=="full": include_dirs.update(("results","figures","jobs"))
    output=args.output or ROOT/"dist"/f"DSA5208_Project3_{args.kind}.zip"
    output=output.resolve()
    output.parent.mkdir(parents=True,exist_ok=True)
    files=[]
    for path in sorted(ROOT.rglob('*')):
        if not path.is_file() or path.is_symlink(): continue
        rel=path.relative_to(ROOT)
        if path.resolve()==output or rel.as_posix()=="SHA256SUMS.txt" or path.name==".DS_Store": continue
        if len(rel.parts)==1 and (rel.suffix in (".zip",".gz",".sha256")): continue
        if "__pycache__" in rel.parts or rel.suffix in (".pyc",".o"): continue
        if rel.as_posix() in ("configs/cluster.env","configs/site_modules.sh"): continue
        if len(rel.parts)==1 or rel.parts[0] in include_dirs:
            files.append(path)
    manifest=[]
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for path in files:
            rel=path.relative_to(ROOT).as_posix()
            data=path.read_bytes()
            z.writestr("Project3/"+rel,data)
            manifest.append(hashlib.sha256(data).hexdigest()+"  "+rel)
        z.writestr("Project3/SHA256SUMS.txt",'\n'.join(manifest)+'\n')
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(output.suffix+".sha256").write_text(digest+"  "+output.name+"\n")
    print(f"Wrote {output} ({len(files)} files)")
    print(f"SHA256: {digest}")
    if not args.final: print("This is an interim package, not a completed assignment submission.")


if __name__=="__main__": main()

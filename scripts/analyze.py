#!/usr/bin/env python3
"""Summarize complete runs without mixing workloads, sources or CPU models."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics

from validate import ROOT

PROVENANCE=("cluster","cpu_model","source_hash","build_signature")
WORKLOAD=("problem","mode","n","max_iters","check_interval","tolerance","profile")
GROUP=PROVENANCE+WORKLOAD+("family","variant","nodes","ranks","threads")


def key(record,fields):
    return tuple(record.get(x,"") for x in fields)


def summarize(records):
    groups={}
    for record in records:
        seconds=record["solve_seconds_max"]
        if not math.isfinite(seconds) or seconds<=0:
            raise ValueError("nonpositive/nonfinite measurement")
        groups.setdefault(key(record,GROUP),[]).append(record)
    result=[]
    for rows in groups.values():
        row={f:rows[0].get(f,"") for f in GROUP}
        values=[r["solve_seconds_max"] for r in rows]
        row.update(cores=rows[0]["cores"],samples=len(values),
                   median_seconds=statistics.median(values),
                   min_seconds=min(values),max_seconds=max(values),
                   iterations_min=min(r["iterations"] for r in rows),
                   iterations_max=max(r["iterations"] for r in rows),
                   residual_max=max(r["final_residual"] for r in rows),
                   error_l2_max=max(r["relative_error_l2"] for r in rows),
                   all_converged=all(r["converged"] for r in rows),
                   speedup="",efficiency="",weak_efficiency="",
                   points_per_core=rows[0]["n"]**2/rows[0]["cores"])
        result.append(row)
    # A strong-scaling baseline must match numerical work, provenance AND family.
    bases={key(r,PROVENANCE+WORKLOAD+("family",)):r for r in result if r["variant"]=="serial"}
    for r in result:
        baseline=bases.get(key(r,PROVENANCE+WORKLOAD+("family",)))
        if baseline:
            r["speedup"]=baseline["median_seconds"]/r["median_seconds"]
            r["efficiency"]=r["speedup"]/r["cores"]
    weak_fields=PROVENANCE+("problem","mode","max_iters","check_interval","tolerance","profile","variant","threads")
    for r in result:
        if r["family"]!="weak": continue
        candidates=[b for b in result if b["family"]=="weak" and key(b,weak_fields)==key(r,weak_fields) and b["cores"]==1]
        if candidates:
            b=candidates[0]
            if abs(r["points_per_core"]/b["points_per_core"]-1)<=0.02:
                r["weak_efficiency"]=b["median_seconds"]/r["median_seconds"]
    return sorted(result,key=lambda r:(str(key(r,PROVENANCE)),r["family"],r["n"],r["cores"],r["variant"],r["threads"]))


def make_plots(rows,folder):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    folder.mkdir(parents=True,exist_ok=True)
    groups={}
    # Preserve every setting that should remain fixed within a curve.
    fields=PROVENANCE+("family","problem","mode","n","max_iters","check_interval","tolerance","profile")
    for r in rows:
        if r["family"]=="weak":
            k=key(r,tuple(f for f in fields if f!="n"))
        else: k=key(r,fields)
        groups.setdefault(k,[]).append(r)
    for number,subset in enumerate(groups.values(),1):
        family=subset[0]["family"]
        cluster=subset[0]["cluster"]
        if family in ("strong","weak"):
            fig,axes=plt.subplots(1,3,figsize=(13,4))
            for variant in sorted(set(r["variant"] for r in subset)):
                points=sorted((r for r in subset if r["variant"]==variant),key=lambda r:r["cores"])
                x=[r["cores"] for r in points]
                med=[r["median_seconds"] for r in points]
                errors=[[r["median_seconds"]-r["min_seconds"] for r in points],
                        [r["max_seconds"]-r["median_seconds"] for r in points]]
                axes[0].errorbar(x,med,yerr=errors,marker="o",label=variant,capsize=3)
                for axis,metric in zip(axes[1:],("speedup","efficiency") if family=="strong" else ("points_per_core","weak_efficiency")):
                    valid=[r for r in points if r[metric]!=""]
                    if valid: axis.plot([r["cores"] for r in valid],[r[metric] for r in valid],"o-",label=variant)
            labels=("Time (s)","Speedup vs serial","Efficiency") if family=="strong" else ("Time (s)","Interior points/core","Weak efficiency")
            for axis,label in zip(axes,labels):
                axis.set_xlabel("Used CPU cores")
                axis.set_ylabel(label)
                axis.grid(alpha=0.3)
                if axis.lines: axis.legend()
        else:
            subset=sorted(subset,key=lambda r:(r["nodes"],r["ranks"],r["threads"],r["variant"]))
            fig,axis=plt.subplots(figsize=(max(7,len(subset)*0.7),4))
            labels=[f"{r['variant']}\n{r['nodes']}node {r['ranks']}p×{r['threads']}t" for r in subset]
            med=[r["median_seconds"] for r in subset]
            errors=[[r["median_seconds"]-r["min_seconds"] for r in subset],
                    [r["max_seconds"]-r["median_seconds"] for r in subset]]
            axis.bar(range(len(subset)),med,yerr=errors,capsize=3)
            axis.set_xticks(range(len(subset)),labels,rotation=30,ha="right")
            axis.set_ylabel("Time (s)")
            axis.grid(axis="y",alpha=0.3)
        local=" — LOCAL DEVELOPMENT ONLY" if cluster not in ("Atlas","Vanda") else ""
        fig.suptitle(f"{cluster}: {family}, {subset[0]['mode']}{local}")
        fig.tight_layout()
        fig.savefig(folder/f"{number:02d}-{family}.png",dpi=180)
        fig.savefig(folder/f"{number:02d}-{family}.pdf")
        plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,default=ROOT/"results"/"raw")
    p.add_argument("--output",type=Path,default=ROOT/"results"/"summary")
    p.add_argument("--figures",type=Path,default=ROOT/"figures")
    p.add_argument("--official-only",action="store_true")
    p.add_argument("--plots",action="store_true")
    args=p.parse_args()
    records=[]
    for path in sorted(args.input.rglob("measurements.jsonl")):
        if not (path.parent/"COMPLETE").exists():
            print(f"Skipping incomplete run: {path.parent}")
            continue
        for line in path.read_text().splitlines():
            r=json.loads(line)
            if not args.official_only or r["cluster"] in ("Atlas","Vanda"):
                records.append(r)
    if not records: p.error("no complete matching runs found")
    rows=summarize(records)
    args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/"summary.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (args.output/"summary.json").write_text(json.dumps(rows,indent=2)+"\n")
    if args.plots: make_plots(rows,args.figures)
    print(f"Summarized {len(records)} measured repetitions, {len(rows)} configurations: {args.output}")
    print("Blank speedup/efficiency means no matching serial baseline; do not fill it by guessing.")


if __name__=="__main__": main()

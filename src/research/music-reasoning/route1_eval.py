"""The question straight: do the real chart tracks land on the right hisia genre?

Queries : the 283 distinct YouTube-trending recordings matched to Deezer
          previews, with Apple's genre label.
Index   : the 340 generated hisia tracks.

The hisia side gets two independent labellings, because "the genre of a
generated track" is not a given:
  prompt  - read out of the SA3 prompt it was generated from (regex, families.py)
  chart   - the modal Apple genre of that region's own chart in that week, i.e.
            the genre of the material the prompt was written from. No regex in
            the loop.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from families import lib_family, real_family

R = Path(__file__).resolve().parent
SITE = R.parents[2]
lib = {t["id"]: t for t in json.load(open(SITE / "library.json"))["tracks"]}
meta = {m["key"]: m for m in json.load(open(R / "real_meta.json"))}
gen = json.load(open(R / "real_genres.json"))

def load(sub, ids):
    keep, M = [], []
    for i in ids:
        f = R / "emb" / sub / f"{i}.npy"
        if f.exists():
            v = np.load(f).astype(np.float32)
            M.append(v / np.linalg.norm(v)); keep.append(i)
    return keep, np.stack(M)

lib_ids, L = load("lib", list(lib))
real_ids, Q = load("real", list(meta))

# one row per recording
seen, keep = set(), []
for i, k in enumerate(real_ids):
    fp = str(meta[k].get("deezer_id") or f'{meta[k]["artist"]}|{meta[k]["title"]}'.lower())
    if fp not in seen:
        seen.add(fp); keep.append(i)
U, ukeys = Q[keep], [real_ids[i] for i in keep]
uy = [real_family((gen.get(k) or {}).get("label")) for k in ukeys]
uy = [None if v == "other" else v for v in uy]
print(f"queries: {len(ukeys)} distinct recordings, {sum(1 for v in uy if v)} with a usable label")

# label the hisia tracks from the charts they were written from
region_week = defaultdict(Counter)
for k, m in meta.items():
    f = real_family((gen.get(k) or {}).get("label"))
    if f and f != "other":
        region_week[m["region"]][f] += 1
lab_chart = {}
for i in lib_ids:
    c = region_week.get(lib[i]["region"])
    lab_chart[i] = c.most_common(1)[0][0] if c else None
lab_prompt = {i: lib_family(lib[i]["sa3_prompt"]) for i in lib_ids}
print("hisia labelled from prompts:", Counter(lab_prompt.values()).most_common())
print("hisia labelled from charts :", Counter(lab_chart.values()).most_common())
agree = sum(1 for i in lib_ids if lab_prompt[i] == lab_chart[i]) / len(lib_ids)
print(f"the two labellings agree on {agree:.0%} of the library\n")

S = U @ L.T
truth = [v for v in uy if v]
maj = Counter(truth).most_common(1)[0]
print(f"baseline: always '{maj[0]}'  acc={maj[1]/len(truth):.3f}  "
      f"macro-recall={1/len(set(truth)):.3f}")

def knn(labels, k=5):
    order = np.argsort(-S, axis=1)
    out = []
    for i in range(len(ukeys)):
        c = Counter()
        for j in order[i, :k]:
            lab = labels[lib_ids[j]]
            if lab:
                c[lab] += float(S[i, j])
        out.append(c.most_common(1)[0][0] if c else None)
    return out

def score(pred, name):
    ok = [(t, p) for t, p in zip(uy, pred) if t]
    acc = sum(1 for t, p in ok if t == p) / len(ok)
    per = defaultdict(lambda: [0, 0])
    for t, p in ok:
        per[t][1] += 1; per[t][0] += (t == p)
    mr = sum(v[0] / v[1] for v in per.values()) / len(per)
    print(f"{name:38s} acc={acc:.3f}  macro-recall={mr:.3f}")
    return per

print()
score(knn(lab_prompt), "kNN over hisia, prompt labels (k=5)")
per = score(knn(lab_chart), "kNN over hisia, chart labels (k=5)")

def auc(s, pos):
    pos_s, neg_s = s[pos], s[~pos]
    if not len(pos_s) or not len(neg_s):
        return None
    allv = np.concatenate([pos_s, neg_s]); order = allv.argsort()
    ranks = np.empty_like(order, dtype=float); ranks[order] = np.arange(1, len(allv) + 1)
    return (ranks[:len(pos_s)].sum() - len(pos_s) * (len(pos_s) + 1) / 2) / (len(pos_s) * len(neg_s))

print("\ndetection: rank every real track by cosine to the hisia genre prototype")
print(f"{'family':16s} {'hisia n':>7s} {'real n':>7s} {'AUC-prompt':>11s} {'AUC-chart':>10s}")
for fam, n in Counter(truth).most_common():
    pos = np.array([v == fam for v in uy])
    row = []
    for labels in (lab_prompt, lab_chart):
        idx = [j for j, i in enumerate(lib_ids) if labels[i] == fam]
        if not idx:
            row.append(None); continue
        p = L[idx].mean(axis=0); p /= np.linalg.norm(p)
        row.append(auc(U @ p, pos))
    npro = len([1 for i in lib_ids if lab_prompt[i] == fam])
    f = lambda v: f"{v:.3f}" if v is not None else "  -  "
    print(f"{fam:16s} {npro:7d} {n:7d} {f(row[0]):>11s} {f(row[1]):>10s}")

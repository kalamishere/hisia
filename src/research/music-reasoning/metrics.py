"""Per-class scoring for the three routes to a genre name.

Overall accuracy flatters whatever always says "pop" - 37% of these charts are
labelled Pop by Apple. Macro recall (mean per-class recall) is the number that
says whether a route can tell classes apart at all; the majority-class baseline
scores 1/n_classes on it by construction.
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
            v = np.load(f).astype(np.float32); M.append(v / np.linalg.norm(v)); keep.append(i)
    return keep, np.stack(M)

lib_ids, L = load("lib", list(lib))
real_ids, Q = load("real", list(meta))
truth = {k: real_family((gen.get(k) or {}).get("label")) for k in real_ids}
# "other" is Apple giving up (Worldwide / Soundtrack / Christian) - scoring
# against it would measure the label, not the audio.
truth = {k: (v if v != "other" else None) for k, v in truth.items()}
lib_fam = {i: lib_family(lib[i]["sa3_prompt"]) for i in lib_ids}

def fp(k):
    m = meta[k]
    return str(m.get("deezer_id") or f'{m["artist"]}|{m["title"]}'.lower())
fps = [fp(k) for k in real_ids]

def knn_vote(S, labels, k=5):
    out = []
    order = np.argsort(-S, axis=1)
    for i in range(S.shape[0]):
        c = Counter()
        for j in order[i, :k]:
            if S[i, j] < -1:   # masked
                continue
            lab = labels[j]
            if lab:
                c[lab] += float(S[i, j])
        out.append(c.most_common(1)[0][0] if c else None)
    return out

def macro(pairs, label):
    ok = [(t, p) for t, p in pairs if t]
    per = defaultdict(lambda: [0, 0])
    for t, p in ok:
        per[t][1] += 1
        per[t][0] += (t == p)
    rec = {k: v[0] / v[1] for k, v in per.items()}
    n_cls = len(per)
    acc = sum(1 for t, p in ok if t == p) / len(ok)
    mr = sum(rec.values()) / n_cls
    print(f"{label:34s} n={len(ok):3d} classes={n_cls:2d}  acc={acc:.3f}  macro-recall={mr:.3f}")
    return rec, per

print("classes present:", Counter(v for v in truth.values() if v and v != "other").most_common())
maj = Counter(v for v in truth.values() if v).most_common(1)[0]
n_cls = len({v for v in truth.values() if v})
print(f"\nbaseline: always '{maj[0]}'  acc={maj[1]/sum(1 for v in truth.values() if v):.3f}  "
      f"macro-recall={1/n_cls:.3f}\n")

# route 1: nearest hisia library tracks
S1 = Q @ L.T
p1 = knn_vote(S1, [lib_fam[i] for i in lib_ids])
macro([(truth[k], p) for k, p in zip(real_ids, p1)], "1. kNN over hisia library")

# route 2: nearest real chart tracks (duplicates masked)
S2 = Q @ Q.T
np.fill_diagonal(S2, -2)
for i in range(len(real_ids)):
    for j in range(i + 1, len(real_ids)):
        if fps[i] == fps[j]:
            S2[i, j] = S2[j, i] = -2
p2 = knn_vote(S2, [truth[k] for k in real_ids])
macro([(truth[k], p) for k, p in zip(real_ids, p2)], "2. kNN over real chart previews")

# route 3: CLAP text prompts, no library at all
z = np.load(R / "zeroshot_scores.npz", allow_pickle=True)
zk = list(z["keys"]); zf = list(z["families"]); Z = z["scores"]
p3 = [zf[int(np.argmax(Z[zk.index(k)]))] if k in zk else None for k in real_ids]
macro([(truth[k], p) for k, p in zip(real_ids, p3)], "3. CLAP text zero-shot")

# route 4: zero-shot, corpus-centred (the trick from research/LOCAL_TAGS.md)
Zc = (Z - Z.mean(axis=0)) / (Z.std(axis=0) + 1e-9)
p4 = [zf[int(np.argmax(Zc[zk.index(k)]))] if k in zk else None for k in real_ids]
rec4, per4 = macro([(truth[k], p) for k, p in zip(real_ids, p4)], "4. zero-shot, corpus-centred")

print("\nper-class recall, route 4:")
for fam, (hit, n) in sorted(per4.items(), key=lambda kv: -kv[1][1])[:12]:
    print(f"   {fam:18s} {hit:3d}/{n:<3d} {hit/n:.2f}")

# region, the claim the site actually makes
p2r = knn_vote(S2, [meta[k]["region"] for k in real_ids])
macro([(meta[k]["region"], p) for k, p in zip(real_ids, p2r)], "\nregion: kNN over real previews")

# ---------------------------------------------------------------- top-3 + fusion
# A description doesn't need one word. "afro / dance / hiphop, in that order"
# is usable if the truth is in there, so score top-3 too - and try the obvious
# combination of the two routes that carry signal.
FAMS = sorted({v for v in truth.values() if v} | set(zf))
fi = {f: i for i, f in enumerate(FAMS)}

def knn_scores(S, labels, k=8):
    out = np.zeros((S.shape[0], len(FAMS)), dtype=np.float32)
    order = np.argsort(-S, axis=1)
    for i in range(S.shape[0]):
        for j in order[i, :k]:
            if S[i, j] < -1:
                continue
            lab = labels[j]
            if lab in fi:
                out[i, fi[lab]] += float(S[i, j])
    return out

def norm(M):
    m = M - M.mean(axis=1, keepdims=True)
    return m / (m.std(axis=1, keepdims=True) + 1e-9)

K2 = norm(knn_scores(S2, [truth[k] for k in real_ids]))
Zf = np.zeros_like(K2)
for i, k in enumerate(real_ids):
    if k in zk:
        for f, s in zip(zf, Zc[zk.index(k)]):
            Zf[i, fi[f]] = s
Zf = norm(Zf)

def topn(M, n=3):
    idx = np.argsort(-M, axis=1)[:, :n]
    return [[FAMS[j] for j in row] for row in idx]

def score_topn(M, label):
    t3 = topn(M, 3)
    t1 = [r[0] for r in t3]
    ok = [(truth[k], a, b) for k, a, b in zip(real_ids, t1, t3) if truth[k]]
    acc = sum(1 for t, a, _ in ok if t == a) / len(ok)
    acc3 = sum(1 for t, _, b in ok if t in b) / len(ok)
    per = defaultdict(lambda: [0, 0])
    for t, a, _ in ok:
        per[t][1] += 1; per[t][0] += (t == a)
    mr = sum(v[0] / v[1] for v in per.values()) / len(per)
    print(f"{label:34s} acc={acc:.3f}  top3={acc3:.3f}  macro-recall={mr:.3f}")

print()
score_topn(K2, "2. kNN real previews (k=8)")
score_topn(Zf, "4. zero-shot centred")
score_topn(K2 + Zf, "5. both, summed")
score_topn(2 * K2 + Zf, "5b. kNN weighted x2")
# where top-3 chance sits: 3 / 12 classes = 0.25 if the classes were balanced,
# and 0.414 + next two most common = the majority top-3 to beat
maj3 = Counter(v for v in truth.values() if v).most_common(3)
tot = sum(1 for v in truth.values() if v)
print(f"{'   baseline: three commonest classes':34s} top3={sum(c for _, c in maj3)/tot:.3f}")

print("\nper-class, route 2 (kNN over real previews, k=8):")
t1 = [r[0] for r in topn(K2, 3)]
per = defaultdict(lambda: [0, 0])
for k, p in zip(real_ids, t1):
    if truth[k]:
        per[truth[k]][1] += 1; per[truth[k]][0] += (truth[k] == p)
for fam, (hit, n) in sorted(per.items(), key=lambda kv: -kv[1][1]):
    print(f"   {fam:16s} {hit:3d}/{n:<3d} {hit/n:.2f}")

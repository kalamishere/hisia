"""Does CLAP closeness to the hisia library tell you what a real track is?

Query set : 296 real chart previews (week 2026-09-07), region known, Apple
            genre label fetched from iTunes Search.
Library   : the 340 published hisia tracks - synthetic, each carrying the
            prompt it was generated from and its region.

Three questions, three numbers:
  A  real -> library kNN: predict the query's REGION and GENRE FAMILY from its
     neighbours. Baseline = most-common class.
  B  real -> real leave-one-out: the same prediction with real neighbours.
     This is the ceiling; A can only be as good as the synthetic library is
     representative.
  C  the domain gap itself: cosine distributions within/between corpora.
"""
import json, re, sys
from collections import Counter
from pathlib import Path
import numpy as np

R = Path(__file__).parent
lib = json.load(open(R.parent.parent.parent / "library.json"))["tracks"]
real_meta = json.load(open(R / "real_meta.json"))
real_gen = json.load(open(R / "real_genres.json"))

from families import lib_family, real_family

# --- vectors --------------------------------------------------------------
def load(ids, sub):
    keep, M = [], []
    for i in ids:
        f = R / "emb" / sub / f"{i}.npy"
        if f.exists():
            v = np.load(f).astype(np.float32)
            M.append(v / np.linalg.norm(v)); keep.append(i)
    return keep, np.stack(M)

lib_by_id = {t["id"]: t for t in lib}
lib_ids, L = load([t["id"] for t in lib], "lib")
real_ids, Q = load([m["key"] for m in real_meta], "real")
rm = {m["key"]: m for m in real_meta}
print(f"library {len(lib_ids)} vectors   real {len(real_ids)} vectors")

lib_region = {i: lib_by_id[i]["region"] for i in lib_ids}
lib_fam    = {i: lib_family(lib_by_id[i]["sa3_prompt"]) for i in lib_ids}
real_region= {i: rm[i]["region"] for i in real_ids}
real_fam   = {i: real_family((real_gen.get(i) or {}).get("label")) for i in real_ids}

def vote(neigh, labeller, sims):
    c = Counter()
    for n, s in zip(neigh, sims):
        lab = labeller(n)
        if lab is not None:
            c[lab] += s
    return c.most_common(1)[0][0] if c else None

def report(name, pairs, chance_pool):
    ok = [p for p in pairs if p[0] is not None and p[1] is not None]
    if not ok:
        print(f"{name}: no labelled pairs"); return
    acc = sum(1 for t, p in ok if t == p) / len(ok)
    base = Counter(chance_pool).most_common(1)[0]
    print(f"{name:38s} n={len(ok):3d}  acc={acc:.3f}   majority-class baseline "
          f"{base[0]}={base[1]/len(chance_pool):.3f}")
    return acc

K = 5
S = Q @ L.T                      # real x library cosines
order = np.argsort(-S, axis=1)

pairs_region, pairs_fam = [], []
for qi, qid in enumerate(real_ids):
    top = order[qi, :K]
    neigh = [lib_ids[j] for j in top]
    sims  = S[qi, top]
    pairs_region.append((real_region[qid], vote(neigh, lambda n: lib_region[n], sims)))
    pairs_fam.append((real_fam[qid],       vote(neigh, lambda n: lib_fam[n], sims)))

print("\nA. real track -> hisia library (k=5, similarity-weighted vote)")
report("   region", pairs_region, [real_region[i] for i in real_ids])
report("   genre family", pairs_fam,
       [f for f in (real_fam[i] for i in real_ids) if f])

SR = Q @ Q.T
np.fill_diagonal(SR, -2)
# A chart hit appears in several regions as the SAME recording. Left in, those
# duplicates hand test B a free correct genre (cosine 1.0 with itself) and a
# guaranteed wrong region. Mask every pair that shares a deezer_id, or an
# artist+title when the id is missing.
def _fp(k):
    m = rm[k]
    return str(m.get("deezer_id") or f'{m["artist"]}|{m["title"]}'.lower())
fps = [_fp(k) for k in real_ids]
dupes = 0
for i in range(len(real_ids)):
    for j in range(i + 1, len(real_ids)):
        if fps[i] == fps[j]:
            SR[i, j] = SR[j, i] = -2
            dupes += 1
print(f"masked {dupes} cross-region duplicate pairs "
      f"({len(set(fps))} distinct recordings among {len(real_ids)} chart slots)")
orderR = np.argsort(-SR, axis=1)
pr_region, pr_fam = [], []
for qi, qid in enumerate(real_ids):
    top = orderR[qi, :K]
    neigh = [real_ids[j] for j in top]
    sims = SR[qi, top]
    pr_region.append((real_region[qid], vote(neigh, lambda n: real_region[n], sims)))
    pr_fam.append((real_fam[qid],       vote(neigh, lambda n: real_fam[n], sims)))

print("\nB. real track -> other real tracks, leave-one-out (the ceiling)")
report("   region", pr_region, [real_region[i] for i in real_ids])
report("   genre family", pr_fam, [f for f in (real_fam[i] for i in real_ids) if f])

print("\nC. cosine distributions")
def stats(M, label):
    v = M[np.triu_indices_from(M, 1)] if M.shape[0] == M.shape[1] else M.ravel()
    v = v[v > -1.5]
    print(f"   {label:28s} mean={v.mean():.3f}  p10={np.percentile(v,10):.3f}  "
          f"p90={np.percentile(v,90):.3f}  max={v.max():.3f}")
LL = L @ L.T; np.fill_diagonal(LL, -2)
stats(LL, "library <-> library")
stats(SR, "real <-> real")
stats(S,  "real <-> library")

# within-vs-between region, on the real side (the claim the README bounds)
same = [SR[i, j] for i in range(len(real_ids)) for j in range(i+1, len(real_ids))
        if real_region[real_ids[i]] == real_region[real_ids[j]]]
diff = [SR[i, j] for i in range(len(real_ids)) for j in range(i+1, len(real_ids))
        if real_region[real_ids[i]] != real_region[real_ids[j]]]
print(f"   real same-region mean={np.mean(same):.3f}   diff-region mean={np.mean(diff):.3f}")

json.dump({"k": K,
           "A_region": pairs_region, "A_family": pairs_fam,
           "B_region": pr_region, "B_family": pr_fam},
          open(R / "eval_raw.json", "w"), indent=1)

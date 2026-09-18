"""If we have N tracks labelled amapiano, does an amapiano track find them?

That is a detection question, not a 12-way classification, so it is scored as
one: for each family, average the N labelled vectors into a prototype, then ask
how well cosine-to-prototype separates that family from everything else (ROC
AUC, and precision@N). A prior that always says "pop" scores 0.5 here, so the
number is not flattered by Apple's label distribution.

Two reference sets, the same queries:
  real      - prototypes built from other REAL chart previews (leave-one-out)
  generated - prototypes built from hisia's SYNTHETIC tracks, labelled by the
              prompt they were generated from

and a learning curve: AUC as a function of how many labelled tracks the
prototype was averaged from.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path
import numpy as np
from families import lib_family, real_family

R = Path(__file__).resolve().parent
SITE = R.parents[2]
rng = np.random.default_rng(0)

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

real_ids, Q = load("real", list(meta))
lib_ids, L = load("lib", list(lib))

# Apple's own word, kept as-is where it is specific (Amapiano stays Amapiano
# instead of being folded into "afro"); families.py only for the coarse pass.
FINE = {"Amapiano": "amapiano", "Afrobeats": "afrobeats", "Afro-Pop": "afrobeats",
        "Afro-Beat": "afrobeats", "Afro-fusion": "afrobeats",
        "Urbano latino": "reggaeton", "Música Mexicana": "regional-mex",
        "Sertanejo": "sertanejo", "Forró": "sertanejo", "K-Pop": "kpop",
        "J-Pop": "jpop", "Hip-Hop/Rap": "hiphop", "Rap": "hiphop",
        "Underground Rap": "hiphop", "South African Hip-Hop": "hiphop",
        "Arabic Pop": "arabic", "Egyptian Pop": "arabic", "Arabic": "arabic",
        "Dance": "dance", "House": "dance", "Electronic": "dance",
        "Reggae": "reggae", "Modern Dancehall": "dancehall",
        "African Dancehall": "dancehall", "Country": "country",
        "R&B/Soul": "rnb", "Rock": "rock", "Hard Rock": "rock",
        "Bollywood": "indian", "Tamil": "indian", "Telugu": "indian",
        "Mbalax": "mbalax", "Pop": "pop", "Indie Pop": "pop",
        "Mandopop": "mandopop", "Cantopop/HK-Pop": "cantopop"}

def fine_label(k):
    lab = (gen.get(k) or {}).get("label")
    return FINE.get(lab)

y = {k: fine_label(k) for k in real_ids}
# one row per RECORDING, not per chart slot: the same track charts in several
# cities and several weeks, and duplicates would be both prototype and query.
seen, uniq = {}, []
for i, k in enumerate(real_ids):
    fp = str(meta[k].get("deezer_id") or f'{meta[k]["artist"]}|{meta[k]["title"]}'.lower())
    if fp not in seen:
        seen[fp] = i; uniq.append(i)
U = Q[uniq]; ukeys = [real_ids[i] for i in uniq]
uy = [y[k] for k in ukeys]
print(f"{len(real_ids)} chart slots -> {len(ukeys)} distinct recordings")
print("labelled:", Counter(v for v in uy if v).most_common())

def auc(scores, positive):
    pos = scores[positive]; neg = scores[~positive]
    if len(pos) == 0 or len(neg) == 0:
        return None
    # rank-based AUC = P(random positive scores above random negative)
    allv = np.concatenate([pos, neg])
    order = allv.argsort()
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(allv) + 1)
    rp = ranks[:len(pos)].sum()
    return (rp - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))

def detect(proto_vecs, proto_labels, fam, held_out_mask=None):
    """AUC + precision@N for one family, scoring every distinct recording."""
    idx = [i for i, l in enumerate(proto_labels) if l == fam]
    if not idx:
        return None
    p = proto_vecs[idx].mean(axis=0)
    p /= np.linalg.norm(p)
    s = U @ p
    pos = np.array([l == fam for l in uy])
    if held_out_mask is not None:       # leave-one-out: don't score the prototypes
        s = s[held_out_mask]; pos = pos[held_out_mask]
    a = auc(s, pos)
    n_pos = int(pos.sum())
    topn = np.argsort(-s)[:max(n_pos, 1)]
    prec = float(pos[topn].mean()) if n_pos else 0.0
    return {"n_proto": len(idx), "n_pos": n_pos, "auc": a, "prec_at_n": prec}

print("\n--- prototypes from REAL previews (leave-one-out: prototype tracks excluded from scoring)")
print(f"{'family':14s} {'n_proto':>7s} {'n_query+':>8s} {'AUC':>6s} {'prec@N':>7s}")
fams = [f for f, c in Counter(v for v in uy if v).most_common() if c >= 4]
rows = []
for fam in fams:
    idx = np.array([i for i, l in enumerate(uy) if l == fam])
    rng.shuffle(idx)
    half = max(2, len(idx) // 2)
    proto_idx, query_mask = idx[:half], np.ones(len(uy), bool)
    query_mask[proto_idx] = False
    p = U[proto_idx].mean(axis=0); p /= np.linalg.norm(p)
    s = (U @ p)[query_mask]
    pos = np.array([l == fam for l in uy])[query_mask]
    a = auc(s, pos)
    n_pos = int(pos.sum())
    prec = float(pos[np.argsort(-s)[:max(n_pos, 1)]].mean())
    rows.append((fam, half, n_pos, a, prec))
    print(f"{fam:14s} {half:7d} {n_pos:8d} {a:6.3f} {prec:7.2f}")

print("\n--- prototypes from GENERATED hisia tracks (labelled by their prompt)")
lib_lab = {i: lib_family(lib[i]["sa3_prompt"]) for i in lib_ids}
# coarse on both sides here, since the prompts only support coarse families
coarse_q = [real_family((gen.get(k) or {}).get("label")) for k in ukeys]
coarse_q = [None if c == "other" else c for c in coarse_q]
print(f"{'family':14s} {'n_proto':>7s} {'n_query+':>8s} {'AUC':>6s} {'prec@N':>7s}")
for fam in sorted({c for c in coarse_q if c}):
    idx = [i for i, k in enumerate(lib_ids) if lib_lab[k] == fam]
    if not idx:
        continue
    p = L[idx].mean(axis=0); p /= np.linalg.norm(p)
    s = U @ p
    pos = np.array([c == fam for c in coarse_q])
    a = auc(s, pos); n_pos = int(pos.sum())
    prec = float(pos[np.argsort(-s)[:max(n_pos, 1)]].mean())
    print(f"{fam:14s} {len(idx):7d} {n_pos:8d} {a:6.3f} {prec:7.2f}")

print("\n--- learning curve: AUC vs how many labelled tracks the prototype averages")
big = [f for f, c in Counter(v for v in uy if v).most_common() if c >= 12][:6]
sizes = [1, 2, 3, 5, 8, 12]
print(f"{'family':14s} " + " ".join(f"N={n:<5d}" for n in sizes))
for fam in big:
    idx = np.array([i for i, l in enumerate(uy) if l == fam])
    line = []
    for n in sizes:
        if n >= len(idx):
            line.append("  -   "); continue
        aucs = []
        for _ in range(20):
            pick = rng.choice(idx, n, replace=False)
            mask = np.ones(len(uy), bool); mask[pick] = False
            p = U[pick].mean(axis=0); p /= np.linalg.norm(p)
            s = (U @ p)[mask]
            pos = np.array([l == fam for l in uy])[mask]
            aucs.append(auc(s, pos))
        line.append(f"{np.mean(aucs):.3f} ")
    print(f"{fam:14s} " + " ".join(line))

print("\n--- prototype from WORDS, same queries (no labelled tracks at all)")
tp = np.load(R / "text_protos.npz", allow_pickle=True)
tv, tf = tp["vecs"], list(tp["families"])
print(f"{'family':14s} {'n_query+':>8s} {'AUC-text':>9s} {'AUC-audio(all N)':>17s}")
for fam in [f for f, c in Counter(v for v in uy if v).most_common() if c >= 3]:
    pos = np.array([l == fam for l in uy])
    if fam in tf:
        st = U @ tv[tf.index(fam)]
        at = auc(st, pos)
    else:
        at = None
    idx = [i for i, l in enumerate(uy) if l == fam]
    p = U[idx].mean(axis=0); p /= np.linalg.norm(p)
    # audio prototype scored on held-out only would need a split; here it is the
    # optimistic in-sample number, printed as the ceiling next to the text one
    aa = auc(U @ p, pos)
    print(f"{fam:14s} {int(pos.sum()):8d} "
          f"{(f'{at:.3f}' if at is not None else '   -  '):>9s} {aa:17.3f}")

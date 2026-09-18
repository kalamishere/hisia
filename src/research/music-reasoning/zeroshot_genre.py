"""The other way to name a genre: ask CLAP's text side directly.

If a plain text prompt ("this is the sound of amapiano") beats retrieval over a
library, the library is not earning its place. Writes zeroshot_scores.npz:
one score per (real preview, family).
"""
import json, sys
from pathlib import Path
import numpy as np

R = Path(__file__).resolve().parent
CKPT = str(Path.home() / (".cache/huggingface/hub/models--lukewys--laion_clap/snapshots/"
                          "b3708341862f581175dba5c356a4ebf74a9b6651/"
                          "music_audioset_epoch_15_esc_90.14.pt"))

FAMILIES = {
    "afro":  ["afrobeats", "afropop from east africa with log drums", "bongo flava and amapiano"],
    "latin": ["reggaeton and latin urbano", "regional mexican corridos", "brazilian funk and sertanejo"],
    "east-asian-pop": ["k-pop", "japanese idol pop", "mandopop ballad"],
    "indian": ["bollywood film music", "hindi film song", "tamil film music"],
    "arabic": ["arabic pop", "khaleeji music", "egyptian mahraganat"],
    "dance": ["dance music", "electronic house track", "edm club track"],
    "hiphop": ["hip hop", "rap music", "trap beat"],
    "rnb": ["r&b", "soul music", "contemporary rnb"],
    "rock": ["rock music", "indie rock band", "guitar rock"],
    "pop": ["pop music", "mainstream radio pop", "pop song"],
    "reggae": ["reggae", "dancehall", "roots reggae"],
    "country": ["country music", "nashville country song", "country ballad"],
}
TEMPLATE = "this is the sound of {}"   # +0.07 precision in the sas-patch report

def main():
    import laion_clap
    model = laion_clap.CLAP_Module(enable_fusion=False, amodel="HTSAT-base")
    model.load_ckpt(CKPT)
    names, vecs = [], []
    for fam, phrasings in FAMILIES.items():
        t = model.get_text_embedding([TEMPLATE.format(p) for p in phrasings],
                                     use_tensor=False)
        v = np.asarray(t).mean(axis=0)
        vecs.append(v / np.linalg.norm(v)); names.append(fam)
    T = np.stack(vecs).astype(np.float32)

    meta = json.load(open(R / "real_meta.json"))
    keys, A = [], []
    for m in meta:
        f = R / "emb/real" / f"{m['key']}.npy"
        if f.exists():
            v = np.load(f).astype(np.float32)
            A.append(v / np.linalg.norm(v)); keys.append(m["key"])
    S = np.stack(A) @ T.T
    np.savez(R / "zeroshot_scores.npz", scores=S, families=np.array(names),
             keys=np.array(keys))
    print("wrote", S.shape, "scores")

main()

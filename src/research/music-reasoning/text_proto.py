"""Same detection test, prototype from WORDS instead of labelled tracks.

If "this is the sound of amapiano" separates amapiano as well as 12 labelled
amapiano tracks do, the labels aren't what's carrying the result.
"""
import json
from pathlib import Path
import numpy as np

R = Path(__file__).resolve().parent
CKPT = str(Path.home() / (".cache/huggingface/hub/models--lukewys--laion_clap/snapshots/"
                          "b3708341862f581175dba5c356a4ebf74a9b6651/"
                          "music_audioset_epoch_15_esc_90.14.pt"))
FINE_TEXT = {
    "amapiano": ["amapiano", "south african amapiano with log drums", "piano house from johannesburg"],
    "afrobeats": ["afrobeats", "afropop from west africa", "bongo flava afro-pop"],
    "hiphop": ["hip hop", "rap music", "trap beat"],
    "pop": ["pop music", "mainstream radio pop", "pop song"],
    "dance": ["dance music", "electronic house track", "edm club track"],
    "arabic": ["arabic pop", "khaleeji music", "egyptian mahraganat"],
    "kpop": ["k-pop", "korean idol pop", "kpop dance track"],
    "reggaeton": ["reggaeton", "latin urbano with a dembow beat", "perreo reggaeton"],
    "indian": ["bollywood film music", "hindi film song", "tamil film music"],
    "rock": ["rock music", "indie rock band", "guitar rock"],
    "regional-mex": ["regional mexican corridos", "banda and mariachi", "corridos tumbados"],
    "reggae": ["reggae", "roots reggae", "one drop reggae"],
    "dancehall": ["dancehall", "jamaican dancehall riddim", "modern dancehall"],
    "rnb": ["r&b", "soul music", "contemporary rnb"],
    "sertanejo": ["sertanejo", "brazilian sertanejo", "sertanejo universitario"],
}
import laion_clap
m = laion_clap.CLAP_Module(enable_fusion=False, amodel="HTSAT-base")
m.load_ckpt(CKPT)
names, V = [], []
for fam, ps in FINE_TEXT.items():
    t = np.asarray(m.get_text_embedding([f"this is the sound of {p}" for p in ps],
                                        use_tensor=False)).mean(axis=0)
    V.append(t / np.linalg.norm(t)); names.append(fam)
np.savez(R / "text_protos.npz", vecs=np.stack(V).astype(np.float32),
         families=np.array(names))
print("wrote", len(names), "text prototypes")

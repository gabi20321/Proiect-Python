import hashlib
import numpy as np
from typing import List, Dict, Any, Tuple
from database import get_all_tracks, get_conn

#lista genuri principale pt codificare vectoriala
GENRE_LIST = [
    "Pop", "Rap/Hip-Hop", "Rock", "Dance", "R&B", "Alternative",
    "Electro", "Folk", "Reggae", "Jazz", "Classical", "Metal"
]


def _hash_bucket(text: str, buckets: int) -> int:#calculare index hash pt artist sau tag
    h = hashlib.md5(text.lower().strip().encode("utf-8")).hexdigest()
    return int(h[:8], 16) % buckets


def build_track_vector(track: Dict[str, Any]) -> np.ndarray:#transformare piesa in vector normalizat de 32 dimensiuni
    vec = np.zeros(32, dtype=np.float32)

    #valori numerice standardizate pt bpm, gain, an si rank
    bpm = float(track.get("bpm") or 120.0)
    gain = float(track.get("gain") or -8.0)
    year = float(track.get("release_year") or 2018)
    rank = float(track.get("rank") or 50000)

    vec[0] = np.clip((bpm - 60.0) / 140.0, 0.0, 1.0) * 1.2
    vec[1] = np.clip((gain + 20.0) / 20.0, 0.0, 1.0) * 0.8
    vec[2] = np.clip((year - 1970.0) / 56.0, 0.0, 1.0) * 1.0
    vec[3] = np.clip(rank / 1000000.0, 0.0, 1.0) * 0.6

    #codificare gen si taguri
    genre = track.get("genre", "Pop")
    if genre in GENRE_LIST:
        vec[4 + GENRE_LIST.index(genre)] = 2.0

    for tag in track.get("tags", []):
        if tag in GENRE_LIST:
            vec[4 + GENRE_LIST.index(tag)] = max(vec[4 + GENRE_LIST.index(tag)], 1.5)
        else:
            b = _hash_bucket(str(tag), 8)
            vec[16 + b] += 0.8

    #amprenta artistului
    artist = track.get("artist", "Unknown")
    art_bucket = _hash_bucket(artist, 8)
    vec[24 + art_bucket] = 1.8

    #normalizare l2 a vectorului
    norm = np.linalg.norm(vec)
    if norm > 1e-8:
        vec /= norm
    return vec


class TasteModel:
    def __init__(self, liked_tracks: List[Dict[str, Any]], disliked_tracks: List[Dict[str, Any]]):#construire profil utilizator din like si dislike
        self.liked_tracks = liked_tracks
        self.disliked_tracks = disliked_tracks

        self.liked_vecs = [build_track_vector(t) for t in liked_tracks]
        self.disliked_vecs = [build_track_vector(t) for t in disliked_tracks]

        self.artist_counts: Dict[str, List[int]] = {}
        self.genre_counts: Dict[str, List[int]] = {}

        for t in liked_tracks:#numaram aprecierile pe artist si gen
            a, g = t.get("artist", ""), t.get("genre", "Pop")
            self.artist_counts.setdefault(a, [0, 0])[0] += 1
            self.genre_counts.setdefault(g, [0, 0])[0] += 1

        for t in disliked_tracks:#numaram respingerile pe artist si gen
            a, g = t.get("artist", ""), t.get("genre", "Pop")
            self.artist_counts.setdefault(a, [0, 0])[1] += 1
            self.genre_counts.setdefault(g, [0, 0])[1] += 1

    def bayesian_affinity(self, counts: List[int]) -> float:#calcul afinitate cu penalizare pe dislike
        l_cnt, d_cnt = counts[0], counts[1]
        return (l_cnt - 1.5 * d_cnt) / (l_cnt + d_cnt + 3.0)

    def score_candidate(self, track: Dict[str, Any], cand_vec: np.ndarray) -> Tuple[float, str]:#calcul scor pt o piesa candidata
        if not self.liked_vecs:
            return 0.0, "Piesa populara din catalog"

        sims_pos = [float(np.dot(cand_vec, lv)) for lv in self.liked_vecs]
        best_idx = int(np.argmax(sims_pos))
        max_pos = sims_pos[best_idx]
        mean_pos = float(np.mean(sims_pos))
        base_score = 0.65 * max_pos + 0.35 * mean_pos

        #penalizare daca seamana prea mult cu o piesa exclusa
        penalty = 0.0
        if self.disliked_vecs:
            sims_neg = [float(np.dot(cand_vec, dv)) for dv in self.disliked_vecs]
            max_neg = max(sims_neg)
            tau = 0.72
            if max_neg > tau:
                penalty = 0.85 * ((max_neg - tau) / (1.0 - tau))

        art = track.get("artist", "")
        gen = track.get("genre", "Pop")
        art_aff = self.bayesian_affinity(self.artist_counts.get(art, [0, 0]))
        gen_aff = self.bayesian_affinity(self.genre_counts.get(gen, [0, 0]))

        final = base_score - penalty + 0.25 * art_aff + 0.20 * gen_aff

        #explicatie scurta pt recomandare
        ref_track = self.liked_tracks[best_idx]
        if art == ref_track.get("artist"):
            reason = f"Acelasi artist cu '{ref_track.get('title')[:18]}'"
        elif gen == ref_track.get("genre") and abs(track.get("bpm", 120) - ref_track.get("bpm", 120)) <= 15:
            reason = f"Vibe {gen} ({int(track.get('bpm', 120))} BPM) ca '{ref_track.get('title')[:15]}'"
        else:
            reason = f"Similara cu '{ref_track.get('title')[:16]}' ({ref_track.get('artist')[:14]})"

        return float(final), reason


def run_ials_numpy(user_id: int, all_tracks: List[Dict[str, Any]], factors: int = 8, iterations: int = 4) -> Dict[str, float]:#filtrare colaborativa ials in numpy
    conn = get_conn()
    try:
        rows = conn.execute("SELECT user_id, track_id, signal, rating FROM interactions").fetchall()
    finally:
        conn.close()

    if len(rows) < 4:
        return {}

    user_ids = sorted(list({r["user_id"] for r in rows} | {user_id}))
    track_ids = [t["id"] for t in all_tracks]
    u_map = {u: i for i, u in enumerate(user_ids)}
    t_map = {t: i for i, t in enumerate(track_ids)}

    m, n = len(user_ids), len(track_ids)
    if m < 2 or n < 2:
        return {}

    P = np.zeros((m, n), dtype=np.float32)
    C = np.ones((m, n), dtype=np.float32)
    alpha = 15.0
    reg = 0.1

    for r in rows:#construire matrice de preferinte si incredere
        uid, tid = r["user_id"], r["track_id"]
        if uid in u_map and tid in t_map:
            val = float(r["signal"] or 0)
            if r["rating"]:
                val += (float(r["rating"]) - 5.0) / 5.0
            if val > 0:
                P[u_map[uid], t_map[tid]] = 1.0
                C[u_map[uid], t_map[tid]] = 1.0 + alpha * val

    rng = np.random.default_rng(42)
    X = rng.normal(0, 0.1, size=(m, factors)).astype(np.float32)
    Y = rng.normal(0, 0.1, size=(n, factors)).astype(np.float32)
    I_f = np.eye(factors, dtype=np.float32) * reg

    for _ in range(iterations):#optimizare alternativa pt utilizatori si piese
        YtY = Y.T @ Y
        for u in range(m):
            Cu = np.diag(C[u] - 1.0)
            A = YtY + Y.T @ Cu @ Y + I_f
            b = Y.T @ (C[u] * P[u])
            X[u] = np.linalg.solve(A, b)

        XtX = X.T @ X
        for i in range(n):
            Ci = np.diag(C[:, i] - 1.0)
            A = XtX + X.T @ Ci @ X + I_f
            b = X.T @ (C[:, i] * P[:, i])
            Y[i] = np.linalg.solve(A, b)

    u_idx = u_map[user_id]
    preds = X[u_idx] @ Y.T
    return {track_ids[i]: float(preds[i]) for i in range(n)}


def recommend_for_user(user_id: int, top_k: int = 24, lambda_mmr: float = 0.78) -> List[Dict[str, Any]]:#generare lista finala de recomandari
    all_tracks = get_all_tracks()
    if not all_tracks:
        return []

    conn = get_conn()
    try:
        inter_rows = conn.execute(
            "SELECT track_id, signal, rating FROM interactions WHERE user_id = ?", (user_id,)
        ).fetchall()
    finally:
        conn.close()

    liked_ids = set()
    disliked_ids = set()
    for r in inter_rows:#separam piesele apreciate de cele excluse
        sig = r["signal"] or 0
        rat = r["rating"] or 0
        if sig == 1 or rat >= 7:
            liked_ids.add(r["track_id"])
        elif sig == -1 or (0 < rat <= 4):
            disliked_ids.add(r["track_id"])

    liked_tracks = [t for t in all_tracks if t["id"] in liked_ids]
    disliked_tracks = [t for t in all_tracks if t["id"] in disliked_ids]

    if not liked_tracks:
        return []

    taste = TasteModel(liked_tracks, disliked_tracks)
    ials_scores = run_ials_numpy(user_id, all_tracks)
    n_events = len(liked_tracks) + len(disliked_tracks)
    cf_weight = n_events / (n_events + 20.0) if ials_scores else 0.0

    candidates = []
    cand_vecs = []

    for track in all_tracks:#calculam scorul combinat pt fiecare piesa neascultata
        tid = track["id"]
        if tid in liked_ids or tid in disliked_ids:
            continue

        vec = build_track_vector(track)
        c_score, reason = taste.score_candidate(track, vec)
        cf_score = ials_scores.get(tid, 0.0)

        blended = (1.0 - cf_weight) * c_score + cf_weight * cf_score
        if blended > 0.15:
            t_copy = track.copy()
            t_copy["raw_score"] = blended
            t_copy["match_score"] = int(np.clip(blended * 95.0, 40, 99))
            t_copy["reason"] = reason
            candidates.append(t_copy)
            cand_vecs.append(vec)

    if not candidates:
        return []

    #diversificare rezultate cu mmr ca sa nu domine un singur artist
    selected_indices: List[int] = []
    remaining = list(range(len(candidates)))

    while remaining and len(selected_indices) < top_k:
        best_idx = -1
        best_mmr = -1e9
        for idx in remaining:
            rel = candidates[idx]["raw_score"]
            if not selected_indices:
                div_penalty = 0.0
            else:
                max_sim = max(float(np.dot(cand_vecs[idx], cand_vecs[s])) for s in selected_indices)
                same_artist_cnt = sum(
                    1 for s in selected_indices if candidates[s]["artist"] == candidates[idx]["artist"]
                )
                div_penalty = max_sim + (0.25 * same_artist_cnt)

            mmr_val = lambda_mmr * rel - (1.0 - lambda_mmr) * div_penalty
            if mmr_val > best_mmr:
                best_mmr = mmr_val
                best_idx = idx

        selected_indices.append(best_idx)
        remaining.remove(best_idx)

    final_recs = [candidates[i] for i in selected_indices]
    final_recs.sort(key=lambda x: x["match_score"], reverse=True)
    return final_recs
from collections import Counter
from database import load_json, save_json, USERS_FILE, CATALOG_FILE, search_and_download_tracks

def toggle_user_feedback(username, track_id, feedback_type):#salvare like sau dislike in json
    users = load_json(USERS_FILE, {})
    if username not in users:
        return "none"

    user_data = users[username]
    favorites = user_data.setdefault("favorites", [])
    excluded = user_data.setdefault("excluded", [])
    track_id = str(track_id)

    if feedback_type == "like":#adaugare sau scoatere de la favorite
        if track_id in favorites:
            favorites.remove(track_id)
            state = "none"
        else:
            favorites.append(track_id)
            if track_id in excluded:
                excluded.remove(track_id)
            state = "liked"
    elif feedback_type == "dislike":#adaugare sau scoatere de la excluse
        if track_id in excluded:
            excluded.remove(track_id)
            state = "none"
        else:
            excluded.append(track_id)
            if track_id in favorites:
                favorites.remove(track_id)
            state = "disliked"
    else:
        state = "none"

    save_json(USERS_FILE, users)
    return state

def get_track_feedback_state(username, track_id):#verif daca piesa are deja like/dislike
    users = load_json(USERS_FILE, {})
    user_data = users.get(username, {})
    track_id = str(track_id)
    if track_id in user_data.get("favorites", []):
        return "liked"
    if track_id in user_data.get("excluded", []):
        return "disliked"
    return "none"

def get_recommendations_for_user(username):#calculare recomandari pe baza profilului
    users = load_json(USERS_FILE, {})
    catalog = load_json(CATALOG_FILE, [])

    user_info = users.get(username, {})
    favorites = set(str(x) for x in user_info.get("favorites", []))
    excluded = set(str(x) for x in user_info.get("excluded", []))

    if not favorites:
        return []

    fav_tracks = [t for t in catalog if str(t.get("id")) in favorites]
    disliked_tracks = [t for t in catalog if str(t.get("id")) in excluded]

    if not fav_tracks:
        return []

    #extragem preferintele din like-uri
    liked_genres = Counter(t.get("genre", "Pop") for t in fav_tracks)
    liked_artists = Counter(t.get("artist", "") for t in fav_tracks)
    years = [t.get("year", 2015) for t in fav_tracks if isinstance(t.get("year"), int)]
    avg_year = sum(years) / len(years) if years else 2015

    #extragem ce nu ii place din dislike-uri
    disliked_genres = Counter(t.get("genre", "") for t in disliked_tracks)
    disliked_artists = set(t.get("artist", "") for t in disliked_tracks)

    #daca sunt prea putine piese in catalog, descarcam automat piese noi similare
    top_genre = liked_genres.most_common(1)[0][0]
    top_artist = liked_artists.most_common(1)[0][0]
    unseen = [t for t in catalog if str(t.get("id")) not in favorites and str(t.get("id")) not in excluded]
    if len(unseen) < 15:
        search_and_download_tracks(f"{top_artist} {top_genre}")
        catalog = load_json(CATALOG_FILE, [])

    total_likes = len(fav_tracks)
    recommendations = []

    for track in catalog:#calculam scorul pt fiecare piesa
        t_id = str(track.get("id", ""))
        if t_id in favorites or t_id in excluded:
            continue

        genre = track.get("genre", "Pop")
        artist = track.get("artist", "Unknown")
        year = track.get("year", 2015) if isinstance(track.get("year"), int) else 2015

        score = 0.0

        if genre in liked_genres:#puncte pt gen
            genre_ratio = liked_genres[genre] / total_likes
            score += 30 + (15 * genre_ratio)

        if artist in liked_artists:#puncte pt artist
            score += 30

        year_diff = abs(avg_year - year)#puncte pt anul lansarii
        score += max(0.0, 25.0 - (year_diff * 1.5))

        if artist in disliked_artists:#penalizare dislike artist
            score -= 50.0
        if genre in disliked_genres and genre not in liked_genres:#penalizare dislike gen
            score -= 35.0

        final_score = round(min(99.0, max(0.0, score)), 1)

        if final_score >= 35.0:#pastram doar ce trece pragul
            track_copy = track.copy()
            track_copy["match_score"] = final_score
            recommendations.append(track_copy)

    recommendations.sort(key=lambda x: x["match_score"], reverse=True)#sortare descrescatoare
    return recommendations
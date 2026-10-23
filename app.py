"""
Application : SMAC Booking & Tour Analyzer (Version Native Streamlit Cloud)
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Literal
import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="SMAC Booking Analyzer",
    page_icon="🎛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

TypologieSalle = Literal[
    "Club / Scène locale",
    "SMAC (Petite jauge)",
    "SMAC (Jauge moyenne)",
    "SMAC (Grande jauge)",
    "Zénith / Arena",
    "Festival",
]

@dataclass
class SalleReference:
    nom: str
    ville: str
    jauge: int
    typologie: TypologieSalle
    budget_moyen_plateau: int

REFERENTIEL_SALLES_CONNUES: dict[str, SalleReference] = {
    "le stockfish": SalleReference("Le Stockfish", "Nice", 300, "Club / Scène locale", 2500),
    "le rex": SalleReference("Le Rex", "Toulouse", 400, "SMAC (Petite jauge)", 3500),
    "la maroquinerie": SalleReference("La Maroquinerie", "Paris", 500, "SMAC (Petite jauge)", 4500),
    "le chabada": SalleReference("Le Chabada", "Angers", 900, "SMAC (Jauge moyenne)", 8500),
    "l'autre canal": SalleReference("L'Autre Canal", "Nancy", 1300, "SMAC (Grande jauge)", 13000),
    "paloma": SalleReference("Paloma", "Nîmes", 1450, "SMAC (Grande jauge)", 15000),
    "le bikini": SalleReference("Le Bikini", "Toulouse", 1500, "SMAC (Grande jauge)", 16000),
    "l'aéronef": SalleReference("L'Aéronef", "Lille", 1900, "SMAC (Grande jauge)", 18000),
    "l'olympia": SalleReference("L'Olympia", "Paris", 2000, "Zénith / Arena", 30000),
    "zénith paris - la villette": SalleReference("Zénith Paris - La Villette", "Paris", 6800, "Zénith / Arena", 65000),
}

def qualifier_salle(nom_salle: str, ville: str) -> SalleReference:
    nom_clean = nom_salle.strip().lower()
    for cle, ref in REFERENTIEL_SALLES_CONNUES.items():
        if cle in nom_clean:
            return SalleReference(nom_salle, ville, ref.jauge, ref.typologie, ref.budget_moyen_plateau)
    
    if any(m in nom_clean for m in ["festival", "hellfest", "eurock"]):
        return SalleReference(nom_salle, ville, 8000, "Festival", 18000)
    if any(m in nom_clean for m in ["zénith", "zenith", "arena", "stade"]):
        return SalleReference(nom_salle, ville, 5500, "Zénith / Arena", 45000)
    
    return SalleReference(nom_salle, ville, 750, "SMAC (Jauge moyenne)", 7500)

def get_spotify_token():
    try:
        client_id = st.secrets["SPOTIFY_CLIENT_ID"]
        client_secret = st.secrets["SPOTIFY_CLIENT_SECRET"]
    except Exception:
        return None

    auth_url = "https://accounts.spotify.com/api/token"
    auth_response = requests.post(auth_url, {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    
    if auth_response.status_code == 200:
        return auth_response.json().get("access_token")
    return None

def fetch_spotify_data(artist_query, token):
    if not token:
        return {"popularite": 50, "auditeurs_mensuels": 100000, "genres": []}
    
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(f"https://api.spotify.com/v1/search?q={artist_query}&type=artist&limit=1", headers=headers)
    if res.status_code == 200:
        items = res.json().get("artists", {}).get("items", [])
        if items:
            artist = items[0]
            followers = artist.get("followers", {}).get("total", 5000)
            return {
                "popularite": artist.get("popularity", 50),
                "auditeurs_mensuels": followers * 12,
                "genres": artist.get("genres", [])
            }
    return {"popularite": 50, "auditeurs_mensuels": 100000, "genres": []}

@st.cache_data(ttl=1800)
def recuperer_donnees_completes(nom_artiste: str):
    try:
        setlist_key = st.secrets["SETLIST_FM_API_KEY"]
    except Exception:
        setlist_key = None

    concerts = []
    if setlist_key:
        headers = {"Accept": "application/json", "x-api-key": setlist_key, "User-Agent": "SMAC-App/1.0"}
        search_res = requests.get(f"https://api.setlist.fm/rest/1.0/search/artists?artistName={nom_artiste}&p=1&sort=relevance", headers=headers)
        
        if search_res.status_code == 200:
            artists = search_res.json().get("artist", [])
            if artists:
                mbid = artists[0].get("mbid")
                setlist_res = requests.get(f"https://api.setlist.fm/rest/1.0/artist/{mbid}/setlists?p=1", headers=headers)
                if setlist_res.status_code == 200:
                    for item in setlist_res.json().get("setlist", []):
                        venue = item.get("venue", {})
                        if venue and venue.get("name") and item.get("eventDate"):
                            parts = item.get("eventDate").split("-")
                            date_iso = f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else item.get("eventDate")
                            concerts.append({
                                "date": date_iso,
                                "salle": venue.get("name"),
                                "ville": venue.get("city", {}).get("name", "N/C"),
                            })

    spotify_token = get_spotify_token()
    spotify_info = fetch_spotify_data(nom_artiste, spotify_token)

    if concerts:
        lignes = []
        for c in concerts:
            ref = qualifier_salle(c["salle"], c["ville"])
            lignes.append({
                "Date": c["date"],
                "Salle / Événement": ref.nom,
                "Ville": ref.ville,
                "Typologie": ref.typologie,
                "Jauge Max": ref.jauge,
                "Affluence Estimée": int(ref.jauge * 0.85),
                "Cachet Estimé (€ HT)": ref.budget_moyen_plateau,
            })
        return pd.DataFrame(lignes), spotify_info, "API Live (Setlist.fm + Spotify)"

    # Mode secours si pas de clé ou pas de résultats
    salles_ref = list(REFERENTIEL_SALLES_CONNUES.values())
    lignes_mock = [{
        "Date": "2026-03-15", "Salle / Événement": r.nom, "Ville": r.ville, 
        "Typologie": r.typologie, "Jauge Max": r.jauge, 
        "Affluence Estimée": int(r.jauge*0.8), "Cachet Estimé (€ HT)": r.budget_moyen_plateau
    } for r in salles_ref[:5]]
    return pd.DataFrame(lignes_mock), spotify_info, "Simulation (Mode hors-clé / Fallback)"

def main():
    st.title("🎛️ Analyseur SMAC — Multi-sources")
    
    with st.sidebar:
        st.header("🏛️ Profil de la salle")
        jauge_user = st.slider("Jauge maximale", 150, 2500, 450, 50)
        budget_user = st.slider("Budget max / plateau (€ HT)", 1000, 35000, 6000, 500)

    artiste = st.text_input("Nom de l'artiste", value="Psykup")

    if artiste:
        with st.spinner("Récupération des données en cours..."):
            df, spotify_info, mode = recuperer_donnees_completes(artiste)

        st.caption(f"⚡ Source : {mode}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Popularité Spotify", f"{spotify_info.get('popularite', 0)} / 100")
        c2.metric("Auditeurs Mensuels Estimés", f"{spotify_info.get('auditeurs_mensuels', 0):,} auditeurs".replace(",", " "))
        c3.metric("Genres", ", ".join(spotify_info.get('genres', ['N/C'])[:3]))

        st.divider()
        st.dataframe(df, use_container_width=True)

if __name__ == "__main__":
    main()

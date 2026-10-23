"""
Application : SMAC Booking & Tour Analyzer (Multi-sources + Moteur de Cohérence)
Plateforme : Streamlit Community Cloud (Native Python)
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
    page_title="SMAC Booking & Tour Analyzer",
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

# Référentiel des salles pour associer jauge et budget moyen aux salles de tournée
REFERENTIEL_SALLES_CONNUES: dict[str, SalleReference] = {
    "le stockfish": SalleReference("Le Stockfish", "Nice", 300, "Club / Scène locale", 2500),
    "le point éphémère": SalleReference("Le Point Éphémère", "Paris", 300, "Club / Scène locale", 2200),
    "le rex": SalleReference("Le Rex", "Toulouse", 400, "SMAC (Petite jauge)", 3500),
    "la maroquinerie": SalleReference("La Maroquinerie", "Paris", 500, "SMAC (Petite jauge)", 4500),
    "le chabada": SalleReference("Le Chabada", "Angers", 900, "SMAC (Jauge moyenne)", 8500),
    "le 106": SalleReference("Le 106", "Rouen", 1100, "SMAC (Jauge moyenne)", 10000),
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
    
    if any(m in nom_clean for m in ["festival", "hellfest", "eurock", "solidays"]):
        return SalleReference(nom_salle, ville, 8000, "Festival", 18000)
    if any(m in nom_clean for m in ["zénith", "zenith", "arena", "stade"]):
        return SalleReference(nom_salle, ville, 5500, "Zénith / Arena", 45000)
    if any(m in nom_clean for m in ["club", "bar", "pub", "cave"]):
        return SalleReference(nom_salle, ville, 280, "Club / Scène locale", 2000)
    
    # Par défaut, estimation SMAC intermédiaire
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
                "Taux Remplissage (%)": 85,
                "Cachet Estimé (€ HT)": ref.budget_moyen_plateau,
            })
        return pd.DataFrame(lignes), spotify_info, "API Live (Setlist.fm + Spotify)"

    # Mode secours (Fallback déterministe si pas de clé ou artiste introuvable)
    seed_val = int(hashlib.md5(nom_artiste.strip().lower().encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed_val)
    salles_ref = list(REFERENTIEL_SALLES_CONNUES.values())
    echantillon = salles_ref[:5]
    
    lignes_mock = []
    for i, r in enumerate(echantillon):
        remplissage = round(rng.uniform(0.70, 0.98), 2)
        lignes_mock.append({
            "Date": f"2026-0{i+1}-15",
            "Salle / Événement": r.nom,
            "Ville": r.ville,
            "Typologie": r.typologie,
            "Jauge Max": r.jauge,
            "Affluence Estimée": int(r.jauge * remplissage),
            "Taux Remplissage (%)": int(remplissage * 100),
            "Cachet Estimé (€ HT)": r.budget_moyen_plateau,
        })
    return pd.DataFrame(lignes_mock), spotify_info, "Simulation (Mode secours / Fallback)"

# --- MOTEUR DE COHÉRENCE ET DE SCORING FINANCIER ---
def evaluer_coherence_ligne(jauge_salle: int, budget_salle: int, typologie: str, jauge_user: int, budget_user: int) -> str:
    if typologie == "Festival":
        return "⚪ Festival (Hors barème SMAC)"
    
    ratio_jauge = jauge_salle / jauge_user
    ratio_budget = budget_salle / budget_user

    if 0.65 <= ratio_jauge <= 1.35 and ratio_budget <= 1.15:
        return "🟢 Cible directe (Profil équivalent)"
    if ratio_jauge <= 1.75 and ratio_budget <= 1.45:
        return "🟠 Négociation / Co-prod requise"
    if ratio_jauge < 0.65:
        return "🔵 Sous-dimensionné (Potentiel tête d'affiche)"
    return "🔴 Surdimensionné (Hors jauge / budget)"

def calculer_diagnostic_global(df_tournee: pd.DataFrame, jauge_user: int, budget_user: int) -> dict:
    df_salles = df_tournee[df_tournee["Typologie"] != "Festival"].copy()
    if df_salles.empty:
        df_salles = df_tournee.copy()

    jauge_mediane = int(df_salles["Jauge Max"].median())
    cachet_median = int(df_salles["Cachet Estimé (€ HT)"].median())

    ecart_jauge_pct = ((jauge_user - jauge_mediane) / jauge_mediane) * 100
    ratio_budget = budget_user / cachet_median

    dates_compatibles = df_tournee["Diagnostic Ligne"].str.startswith(("🟢", "🔵")).sum()
    taux_recurrence = int((dates_compatibles / len(df_tournee)) * 100)

    score_budget = min(100.0, ratio_budget * 85.0)
    penalite_jauge = max(0.0, (jauge_mediane - jauge_user) / jauge_mediane * 100.0)
    score_global = int(max(0.0, min(100.0, score_budget - (penalite_jauge * 0.4))))

    if score_global >= 72 and budget_user >= (cachet_median * 0.85):
        statut = "Compatible"
        badge = "🟢 COMPATIBLE — Cible Prioritaire"
        recommandation = "L'artiste évolue régulièrement dans des salles de jauge et de budget équivalents. Risque financier maîtrisé."
    elif score_global >= 45:
        statut = "Risqué"
        badge = "🟠 RISQUÉ — Montage Spécifique Requis"
        recommandation = "Écart notable entre les standards récents de la tournée et votre configuration. Envisagez un minimum garanti réduit ou une coréalisation."
    else:
        statut = "Hors budget"
        badge = "🔴 HORS BUDGET / SURDIMENSIONNÉ"
        recommandation = "L'artiste se produit sur un segment supérieur. L'équilibre économique est mathématiquement déficitaire sur votre jauge."

    return {
        "statut": statut,
        "badge": badge,
        "score": score_global,
        "jauge_mediane": jauge_mediane,
        "ecart_jauge_pct": int(ecart_jauge_pct),
        "cachet_median": cachet_median,
        "ecart_budget_eur": budget_user - cachet_median,
        "taux_recurrence": taux_recurrence,
        "recommandation": recommandation,
    }

def main():
    with st.sidebar:
        st.header("🏛️ Profil de votre salle")
        nom_salle_user = st.text_input("Nom de la structure", value="Le Stockfish")
        jauge_user = st.slider("Jauge maximale", 150, 2500, 300, 50)
        budget_user = st.slider("Budget max / plateau (€ HT)", 1000, 35000, 3000, 500)
        prix_billet = st.number_input("Prix moyen du billet net (€)", 5, 80, 18, 1)

    st.title("🎛️ Analyseur de Faisabilité Booking & Tournée")
    st.markdown(f"Croisement des données pour **{nom_salle_user}** (*Jauge : **{jauge_user} pl.** | Budget : **{budget_user:,} € HT**)*.")

    with st.form("form_artiste"):
        col1, col2 = st.columns([3, 1])
        with col1:
            artiste = st.text_input("Nom de l'artiste ou du groupe", value="Psykup")
        with col2:
            st.write("")
            lancer = st.form_submit_button("🔍 Lancer l'analyse", use_container_width=True, type="primary")

    if lancer or artiste:
        with st.spinner("Analyse des tournées et de la notoriété en cours..."):
            df_tournee, spotify_info, mode = recuperer_donnees_completes(artiste)

        st.caption(f"⚡ Source : {mode}")

        # Indicateurs Spotify
        c1, c2, c3 = st.columns(3)
        c1.metric("Popularité Spotify", f"{spotify_info.get('popularite', 0)} / 100")
        c2.metric("Auditeurs Mensuels Estimés", f"{spotify_info.get('auditeurs_mensuels', 0):,} auditeurs".replace(",", " "))
        c3.metric("Genres", ", ".join(spotify_info.get('genres', ['N/C'])[:3]))

        st.divider()

        # Application du moteur de cohérence sur chaque ligne du tableau
        df_tournee["Diagnostic Ligne"] = df_tournee.apply(
            lambda r: evaluer_coherence_ligne(r["Jauge Max"], r["Cachet Estimé (€ HT)"], r["Typologie"], jauge_user, budget_user),
            axis=1
        )

        diag = calculer_diagnostic

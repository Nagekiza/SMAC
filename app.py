"""
Application : SMAC Booking & Tour Analyzer (MusicBrainz + Setlist.fm + Spotify Corrigé)
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
    page_title="SMAC Booking & Tour Analyzer — Pro",
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

REFERENTIEL_SALLES_CONNUES: dict[str, SalleReference] = {
    "le stockfish": SalleReference("Le Stockfish", "Nice", 300, "Club / Scène locale"),
    "le point éphémère": SalleReference("Le Point Éphémère", "Paris", 300, "Club / Scène locale"),
    "le rex": SalleReference("Le Rex", "Toulouse", 400, "SMAC (Petite jauge)"),
    "la maroquinerie": SalleReference("La Maroquinerie", "Paris", 500, "SMAC (Petite jauge)"),
    "le chabada": SalleReference("Le Chabada", "Angers", 900, "SMAC (Jauge moyenne)"),
    "le 106": SalleReference("Le 106", "Rouen", 1100, "SMAC (Jauge moyenne)"),
    "l'autre canal": SalleReference("L'Autre Canal", "Nancy", 1300, "SMAC (Grande jauge)"),
    "paloma": SalleReference("Paloma", "Nîmes", 1450, "SMAC (Grande jauge)"),
    "le bikini": SalleReference("Le Bikini", "Toulouse", 1500, "SMAC (Grande jauge)"),
    "l'aéronef": SalleReference("L'Aéronef", "Lille", 1900, "SMAC (Grande jauge)"),
    "l'olympia": SalleReference("L'Olympia", "Paris", 2000, "Zénith / Arena"),
    "zénith paris - la villette": SalleReference("Zénith Paris - La Villette", "Paris", 6800, "Zénith / Arena"),
}

def qualifier_salle(nom_salle: str, ville: str) -> SalleReference:
    nom_clean = nom_salle.strip().lower()
    for cle, ref in REFERENTIEL_SALLES_CONNUES.items():
        if cle in nom_clean:
            return SalleReference(nom_salle, ville, ref.jauge, ref.typologie)
    
    if any(m in nom_clean for m in ["festival", "hellfest", "eurock", "solidays"]):
        return SalleReference(nom_salle, ville, 8000, "Festival")
    if any(m in nom_clean for m in ["zénith", "zenith", "arena", "stade"]):
        return SalleReference(nom_salle, ville, 5500, "Zénith / Arena")
    if any(m in nom_clean for m in ["club", "bar", "pub", "cave"]):
        return SalleReference(nom_salle, ville, 280, "Club / Scène locale")
    
    return SalleReference(nom_salle, ville, 750, "SMAC (Jauge moyenne)")

def get_spotify_token():
    client_id, client_secret = None, None
    try:
        if st.secrets and "SPOTIFY_CLIENT_ID" in st.secrets:
            client_id = st.secrets["SPOTIFY_CLIENT_ID"]
        if st.secrets and "SPOTIFY_CLIENT_SECRET" in st.secrets:
            client_secret = st.secrets["SPOTIFY_CLIENT_SECRET"]
    except Exception:
        pass

    if not client_id or not client_secret:
        return None

    auth_url = "https://accounts.spotify.com/api/token"
    auth_str = f"{client_id}:{client_secret}"
    import base64
    b64_auth = base64.b64encode(auth_str.encode()).decode()
    headers = {"Authorization": f"Basic {b64_auth}", "Content-Type": "application/x-www-form-urlencoded"}
    
    try:
        res = requests.post(auth_url, data={"grant_type": "client_credentials"}, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json().get("access_token")
    except Exception:
        pass
    return None

def fetch_spotify_data(artist_query, token):
    if not token:
        return {"popularite": 50, "auditeurs_mensuels": 25000, "genres": []}
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(f"https://api.spotify.com/v1/search?q={artist_query}&type=artist&limit=5", headers=headers, timeout=5)
        if res.status_code == 200:
            items = res.json().get("artists", {}).get("items", [])
            if items:
                items = sorted(items, key=lambda x: x.get("popularity", 0), reverse=True)
                artist = items[0]
                popularity = artist.get("popularity", 50)
                followers = artist.get("followers", {}).get("total", 5000)
                
                # CORRECTION : Estimation réaliste et proportionnelle basée sur les followers
                auditeurs = int(followers * 2.2)
                
                return {
                    "popularite": popularity,
                    "auditeurs_mensuels": auditeurs,
                    "genres": artist.get("genres", [])
                }
    except Exception:
        pass
    return {"popularite": 50, "auditeurs_mensuels": 25000, "genres": []}

def estimer_cachet_par_popularite(popularite: int) -> int:
    if popularite >= 85:
        return random.randint(80000, 200000)
    elif popularite >= 70:
        return random.randint(30000, 75000)
    elif popularite >= 50:
        return random.randint(8000, 25000)
    elif popularite >= 30:
        return random.randint(3000, 7500)
    else:
        return random.randint(1200, 2800)

def get_artist_mbid(artist_name: str) -> str | None:
    url = f"https://musicbrainz.org/ws/2/artist/?query={artist_name}&fmt=json"
    headers = {"User-Agent": "SMACBookingAnalyzer/2.0 (contact@votre-smac.fr)"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            artists = res.json().get("artists", [])
            if artists:
                return artists[0].get("id")
    except Exception:
        pass
    return None

@st.cache_data(ttl=1800)
def recuperer_donnees_completes(nom_artiste: str):
    setlist_key = None
    try:
        if st.secrets and "SETLIST_FM_API_KEY" in st.secrets:
            setlist_key = st.secrets["SETLIST_FM_API_KEY"]
    except Exception:
        pass

    spotify_token = get_spotify_token()
    spotify_info = fetch_spotify_data(nom_artiste, spotify_token)
    cachet_estime = estimer_cachet_par_popularite(spotify_info["popularite"])

    concerts = []
    if setlist_key:
        try:
            headers = {"Accept": "application/json", "x-api-key": setlist_key, "User-Agent": "SMAC-App/1.0"}
            mbid = get_artist_mbid(nom_artiste)
            
            if mbid:
                setlist_res = requests.get(f"https://api.setlist.fm/rest/1.0/artist/{mbid}/setlists?p=1", headers=headers, timeout=5)
            else:
                search_res = requests.get(f"https://api.setlist.fm/rest/1.0/search/artists?artistName={nom_artiste}&p=1&sort=relevance", headers=headers, timeout=5)
                if search_res.status_code == 200:
                    artists = search_res.json().get("artist", [])
                    if artists:
                        mbid = artists[0].get("mbid")
                        setlist_res = requests.get(f"https://api.setlist.fm/rest/1.0/artist/{mbid}/setlists?p=1", headers=headers, timeout=5)
                    else:
                        setlist_res = None
                else:
                    setlist_res = None

            if setlist_res and setlist_res.status_code == 200:
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
        except Exception:
            pass

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
                "Cachet Estimé (€ HT)": cachet_estime,
            })
        return pd.DataFrame(lignes), spotify_info, cachet_estime, "API Live (MusicBrainz + Setlist.fm + Spotify)"

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
            "Ville": r.ville if i > 0 else "Marseille",
            "Typologie": r.typologie,
            "Jauge Max": r.jauge,
            "Affluence Estimée": int(r.jauge * remplissage),
            "Taux Remplissage (%)": int(remplissage * 100),
            "Cachet Estimé (€ HT)": cachet_estime,
        })
    return pd.DataFrame(lignes_mock), spotify_info, cachet_estime, "Simulation (Mode secours / Fallback)"

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

def calculer_diagnostic_global(df_tournee: pd.DataFrame, jauge_user: int, budget_user: int, cachet_estime: int) -> dict:
    df_salles = df_tournee[df_tournee["Typologie"] != "Festival"].copy()
    if df_salles.empty:
        df_salles = df_tournee.copy()

    jauge_mediane = int(df_salles["Jauge Max"].median())
    ratio_budget = budget_user / cachet_estime

    ecart_jauge_pct = ((jauge_user - jauge_mediane) / jauge_mediane) * 100
    dates_compatibles = df_tournee["Diagnostic Ligne"].str.startswith(("🟢", "🔵")).sum()
    taux_recurrence = int((dates_compatibles / len(df_tournee)) * 100)

    score_budget = min(100.0, ratio_budget * 85.0)
    penalite_jauge = max(0.0, (jauge_mediane - jauge_user) / jauge_mediane * 100.0)
    score_global = int(max(0.0, min(100.0, score_budget - (penalite_jauge * 0.4))))

    if score_global >= 72 and budget_user >= (cachet_estime * 0.85):
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
        recommandation = "L'artiste se produit sur un segment supérieur (Stades / Arénas). L'équilibre économique est mathématiquement déficitaire sur votre jauge."

    return {
        "statut": statut,
        "badge": badge,
        "score": score_global,
        "jauge_mediane": jauge_mediane,
        "ecart_jauge_pct": int(ecart_jauge_pct),
        "cachet_median": cachet_estime,
        "ecart_budget_eur": budget_user - cachet_estime,
        "taux_recurrence": taux_recurrence,
        "recommandation": recommandation,
    }

def analyser_routage_geographique(df_tournee: pd.DataFrame) -> list[str]:
    villes_proches = ["marseille", "toulon", "cannes", "antibes", "monaco", "menton", "lyon", "turin", "milan", "gênes", "nice"]
    conseils = []
    for _, row in df_tournee.iterrows():
        ville_salle = str(row["Ville"]).lower()
        for v in villes_proches:
            if v in ville_salle:
                conseils.append(f"💡 **Opportunité de routage :** Passage récent à **{row['Ville']}** ({row['Date']}). Pensez à mutualiser les frais logistiques.")
                break
    return list(set(conseils))

def main():
    with st.sidebar:
        st.header("🏛️ Profil de votre salle")
        nom_salle_user = st.text_input("Nom de la structure", value="Le Stockfish")
        jauge_user = st.slider("Jauge maximale", 150, 2500, 300, 50)
        budget_user = st.slider("Budget max / plateau (€ HT)", 1000, 35000, 3000, 500)
        
        st.divider()
        st.subheader("💰 Simulateur de charges annexes")
        frais_tech = st.number_input("Frais techniques annexes (€ HT)", 0, 5000, 300, 50)
        vhr_catering = st.number_input("Frais VHR (Hôtel / Repas) (€ HT)", 0, 3000, 400, 50)

        st.divider()
        st.subheader("🔑 Statut des API")
        has_spotify = get_spotify_token() is not None
        has_setlist = False
        try:
            has_setlist = st.secrets and "SETLIST_FM_API_KEY" in st.secrets
        except Exception:
            pass
        
        st.markdown(f"Spotify API : {'🟢 Connecté' if has_spotify else '🔴 Non détecté (Fallback)'}")
        st.markdown(f"Setlist.fm API : {'🟢 Connecté' if has_setlist else '🔴 Non détecté (Fallback)'}")

    st.title("🎛️ Analyseur de Faisabilité Booking & Tournée")
    st.markdown(f"Croisement des données pour **{nom_salle_user}** (*Jauge : **{jauge_user} pl.** | Budget : **{budget_user:,} € HT**)*.")

    with st.form("form_artiste"):
        col1, col2 = st.columns([3, 1])
        with col1:
            artiste = st.text_input("Nom de l'artiste ou du groupe", value="Dombrance")
        with col2:
            st.write("")
            lancer = st.form_submit_button("🔍 Lancer l'analyse", use_container_width=True, type="primary")

    if lancer or artiste:
        with st.spinner("Analyse MusicBrainz, Setlist.fm et Spotify en cours..."):
            df_tournee, spotify_info, cachet_estime, mode = recuperer_donnees_completes(artiste)

        st.caption(f"⚡ Source : {mode}")

        c1, c2, c3 = st.columns(3)
        c1.metric("Popularité Spotify", f"{spotify_info.get('popularite', 0)} / 100")
        c2.metric("Auditeurs Mensuels Estimés", f"{spotify_info.get('auditeurs_mensuels', 0):,} auditeurs".replace(",", " "))
        c3.metric("Genres", ", ".join(spotify_info.get('genres', ['N/C'])[:3]))

        st.divider()

        df_tournee["Diagnostic Ligne"] = df_tournee.apply(
            lambda r: evaluer_coherence_ligne(r["Jauge Max"], r["Cachet Estimé (€ HT)"], r["Typologie"], jauge_user, budget_user),
            axis=1
        )

        diag = calculer_diagnostic_global(df_tournee, jauge_user, budget_user, cachet_estime)

        st.subheader(f"Résultat d'analyse : {artiste.upper()}")
        if diag["statut"] == "Compatible":
            st.success(f"**{diag['badge']}** — {diag['recommandation']}")
        elif diag["statut"] == "Risqué":
            st.warning(f"**{diag['badge']}** — {diag['recommandation']}")
        else:
            st.error(f"**{diag['badge']}** — {diag['recommandation']}")

        cout_global_reel = cachet_estime + frais_tech + vhr_catering

        k1, k2, k3 = st.columns(3)
        k1.metric("Score de Compatibilité", f"{diag['score']} / 100", f"{diag['taux_recurrence']}% de salles similaires")
        k2.metric("Jauge Médiane Tournée", f"{diag['jauge_mediane']} pl.", f"{diag['ecart_jauge_pct']:+d}% vs vous")
        k3.metric("Coût Global Réel (Cachet + Frais)", f"{cout_global_reel:,} € HT", f"Dont {frais_tech + vhr_catering} € de charges")

        st.divider()

        conseils_routage = analyser_routage_geographique(df_tournee)
        if conseils_routage:
            st.subheader("🗺️ Recommandations de Routage Géographique")
            for conseil in conseils_routage:
                st.info(conseil)
            st.divider()

        st.subheader("📋 Historique récent et adéquation par salle")
        st.dataframe(
            df_tournee,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Date": st.column_config.TextColumn("Date"),
                "Jauge Max": st.column_config.NumberColumn("Jauge Salle", format="%d pl."),
                "Cachet Estimé (€ HT)": st.column_config.NumberColumn("Cachet Estimé", format="%d € HT"),
                "Diagnostic Ligne": st.column_config.TextColumn("Cohérence avec votre salle", width="large"),
            }
        )

        st.subheader("📊 Comparaison des jauges de tournée (hors festivals)")
        df_graph = df_tournee[df_tournee["Typologie"] != "Festival"].set_index("Salle / Événement")
        if not df_graph.empty:
            df_graph["Votre Jauge Max"] = jauge_user
            st.bar_chart(df_graph[["Jauge Max", "Affluence Estimée", "Votre Jauge Max"]], height=300)

if __name__ == "__main__":
    main()

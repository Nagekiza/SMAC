"""
Application : SMAC Booking & Tour Analyzer
Objectif : Aide à la décision pour la programmation de musiques actuelles.
 Croise l'historique de tournée d'un artiste avec les contraintes de jauge
 et de budget d'une salle de spectacle.
Prérequis : Python 3.10+, Streamlit, Pandas
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Literal

import pandas as pd
import streamlit as st

# =====================================================================
# 1. CONFIGURATION DE LA PAGE & STYLES
# =====================================================================
st.set_page_config(
    page_title="SMAC Booking Analyzer",
    page_icon="🎛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =====================================================================
# 2. MODÈLES DE DONNÉES & RÉFÉRENTIEL MÉTIER (SMAC / SALLES)
# =====================================================================
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
    budget_moyen_plateau: int  # Estimation du cachet moyen pratiqué en € HT


# Base de référence représentative du réseau français des musiques actuelles
REFERENTIEL_SALLES: dict[str, SalleReference] = {
    "Le Stockfish": SalleReference("Le Stockfish", "Nice", 300, "Club / Scène locale", 2500),
    "Le Point Éphémère": SalleReference("Le Point Éphémère", "Paris", 300, "Club / Scène locale", 2200),
    "Le Rex": SalleReference("Le Rex", "Toulouse", 400, "SMAC (Petite jauge)", 3500),
    "La Maroquinerie": SalleReference("La Maroquinerie", "Paris", 500, "SMAC (Petite jauge)", 4500),
    "Le Chabada": SalleReference("Le Chabada", "Angers", 900, "SMAC (Jauge moyenne)", 8500),
    "Le 106": SalleReference("Le 106", "Rouen", 1100, "SMAC (Jauge moyenne)", 10000),
    "L'Autre Canal": SalleReference("L'Autre Canal", "Nancy", 1300, "SMAC (Grande jauge)", 13000),
    "Paloma": SalleReference("Paloma", "Nîmes", 1450, "SMAC (Grande jauge)", 15000),
    "Le Bikini": SalleReference("Le Bikini", "Toulouse", 1500, "SMAC (Grande jauge)", 16000),
    "La Coopérative de Mai": SalleReference("La Coopérative de Mai", "Clermont-Ferrand", 1500, "SMAC (Grande jauge)", 15500),
    "L'Aéronef": SalleReference("L'Aéronef", "Lille", 1900, "SMAC (Grande jauge)", 18000),
    "L'Olympia": SalleReference("L'Olympia", "Paris", 2000, "Zénith / Arena", 30000),
    "Zénith Paris - La Villette": SalleReference("Zénith Paris - La Villette", "Paris", 6800, "Zénith / Arena", 65000),
    "Hellfest (Valley Stage)": SalleReference("Hellfest (Valley Stage)", "Clisson", 5000, "Festival", 12000),
    "Les Eurockéennes": SalleReference("Les Eurockéennes", "Belfort", 12000, "Festival", 35000),
}

# Historiques pré-configurés pour la démonstration
HISTORIQUES_MOCK: dict[str, list[dict]] = {
    "psykup": [
        {"date": "2026-03-14", "salle": "Le Rex", "remplissage_estime": 0.92},
        {"date": "2026-03-21", "salle": "Le Stockfish", "remplissage_estime": 0.95},
        {"date": "2026-04-04", "salle": "La Maroquinerie", "remplissage_estime": 0.88},
        {"date": "2026-04-18", "salle": "Le Chabada", "remplissage_estime": 0.65},
        {"date": "2026-06-20", "salle": "Hellfest (Valley Stage)", "remplissage_estime": 1.00},
    ],
    "7 weeks": [
        {"date": "2026-02-10", "salle": "Le Point Éphémère", "remplissage_estime": 0.85},
        {"date": "2026-02-24", "salle": "Le Stockfish", "remplissage_estime": 0.90},
        {"date": "2026-03-07", "salle": "Le Rex", "remplissage_estime": 0.80},
        {"date": "2026-03-28", "salle": "La Maroquinerie", "remplissage_estime": 0.78},
        {"date": "2026-05-15", "salle": "La Coopérative de Mai", "remplissage_estime": 0.55},
    ],
    "josman": [
        {"date": "2026-01-30", "salle": "Le Bikini", "remplissage_estime": 1.00},
        {"date": "2026-02-14", "salle": "L'Aéronef", "remplissage_estime": 1.00},
        {"date": "2026-03-10", "salle": "L'Olympia", "remplissage_estime": 1.00},
        {"date": "2026-04-22", "salle": "Zénith Paris - La Villette", "remplissage_estime": 0.98},
        {"date": "2026-07-04", "salle": "Les Eurockéennes", "remplissage_estime": 0.95},
    ],
}


# =====================================================================
# 3. MODULE D'ACQUISITION ET D'EXTRACTION DE DONNÉES
# =====================================================================
@st.cache_data(ttl=3600)
def extraire_historique_tournee(nom_artiste: str) -> pd.DataFrame:
    """
    Récupère l'historique de tournée d'un artiste.
    En production, cette fonction interroge l'API Setlist.fm ou Bandsintown
    puis croise les noms de salles avec la base CNM / SMAC.
    Ici, elle utilise les profils calibrés ou génère un historique déterministe.
    """
    cle_artiste = nom_artiste.strip().lower()

    if cle_artiste in HISTORIQUES_MOCK:
        dates_brutes = HISTORIQUES_MOCK[cle_artiste]
    else:
        # Génération déterministe basée sur le hash du nom pour garantir
        # la reproductibilité des tests sur n'importe quel artiste saisi
        seed_val = int(hashlib.md5(cle_artiste.encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(seed_val)
        toutes_les_salles = list(REFERENTIEL_SALLES.keys())

        # Sélection d'un segment cohérent de salles (évite de mélanger club 200p et Zénith)
        index_depart = rng.randint(0, max(0, len(toutes_les_salles) - 6))
        echantillon_salles = toutes_les_salles[index_depart : index_depart + 5]

        dates_brutes = [
            {
                "date": f"2026-0{i + 1}-{rng.randint(10, 28)}",
                "salle": nom_salle,
                "remplissage_estime": round(rng.uniform(0.65, 1.0), 2),
            }
            for i, nom_salle in enumerate(echantillon_salles)
        ]

    lignes = []
    for entree in dates_brutes:
        ref = REFERENTIEL_SALLES[entree["salle"]]
        affluence = int(ref.jauge * entree["remplissage_estime"])
        lignes.append(
            {
                "Date": entree["date"],
                "Salle / Événement": ref.nom,
                "Ville": ref.ville,
                "Typologie": ref.typologie,
                "Jauge Max": ref.jauge,
                "Affluence Estimée": affluence,
                "Taux Remplissage (%)": int(entree["remplissage_estime"] * 100),
                "Cachet Estimé (€ HT)": ref.budget_moyen_plateau,
            }
        )

    return pd.DataFrame(lignes)


# =====================================================================
# 4. MOTEUR DE CROISEMENT ET D'AIDE À LA DÉCISION
# =====================================================================
def evaluer_coherence_ligne(
    jauge_salle_tournee: int,
    budget_salle_tournee: int,
    typologie: str,
    jauge_utilisateur: int,
    budget_utilisateur: int,
) -> str:
    """Évalue la proximité d'une date passée avec le profil de la salle utilisatrice."""
    if typologie == "Festival":
        return "⚪ Festival (Hors barème SMAC)"

    ratio_jauge = jauge_salle_tournee / jauge_utilisateur
    ratio_budget = budget_salle_tournee / budget_utilisateur

    if 0.65 <= ratio_jauge <= 1.35 and ratio_budget <= 1.15:
        return "🟢 Cible directe (Profil équivalent)"
    if ratio_jauge <= 1.75 and ratio_budget <= 1.45:
        return "🟠 Négociation / Co-prod requise"
    if ratio_jauge < 0.65:
        return "🔵 Sous-dimensionné (Potentiel tête d'affiche)"
    return "🔴 Surdimensionné (Hors jauge / budget)"


def calculer_diagnostic_global(
    df_tournee: pd.DataFrame,
    jauge_utilisateur: int,
    budget_utilisateur: int,
) -> dict:
    """
    Croise les métriques médianes de la tournée (hors festivals) avec
    les capacités financières et d'accueil du programmateur.
    """
    # Exclusion des festivals pour ne pas biaiser la jauge médiane en salle
    df_salles = df_tournee[df_tournee["Typologie"] != "Festival"].copy()
    if df_salles.empty:
        df_salles = df_tournee.copy()

    jauge_mediane = int(df_salles["Jauge Max"].median())
    cachet_median = int(df_salles["Cachet Estimé (€ HT)"].median())

    # Calcul des écarts
    ecart_jauge_pct = ((jauge_utilisateur - jauge_mediane) / jauge_mediane) * 100
    ratio_budget = budget_utilisateur / cachet_median

    # Comptage des dates compatibles
    dates_compatibles = df_tournee["Diagnostic Ligne"].str.startswith(("🟢", "🔵")).sum()
    taux_recurrence = int((dates_compatibles / len(df_tournee)) * 100)

    # Algorithme de scoring sur 100
    score_budget = min(100.0, ratio_budget * 85.0)
    penalite_jauge = max(0.0, (jauge_mediane - jauge_utilisateur) / jauge_mediane * 100.0)
    score_global = int(max(0.0, min(100.0, score_budget - (penalite_jauge * 0.4))))

    # Détermination du statut de faisabilité
    if score_global >= 72 and budget_utilisateur >= (cachet_median * 0.85):
        statut = "Compatible"
        badge = "🟢 COMPATIBLE — Cible Prioritaire"
        recommandation = (
            "L'artiste évolue régulièrement dans des salles de jauge et de budget équivalents. "
            "Le risque financier est maîtrisé pour une proposition de cession directe."
        )
    elif score_global >= 45:
        statut = "Risqué"
        badge = "🟠 RISQUÉ — Montage Spécifique Requis"
        recommandation = (
            "Écart notable entre les standards récents de la tournée et votre configuration. "
            "Envisagez un contrat de coréalisation avec minimum garanti réduit, une date de "
            "routage (off de festival) ou un fort soutien billetterie."
        )
    else:
        statut = "Hors budget"
        badge = "🔴 HORS BUDGET / SURDIMENSIONNÉ"
        recommandation = (
            "L'artiste se produit actuellement sur un segment supérieur (Grandes SMAC / Zéniths). "
            "L'équilibre économique du plateau est mathématiquement déficitaire sur votre jauge."
        )

    return {
        "statut": statut,
        "badge": badge,
        "score": score_global,
        "jauge_mediane": jauge_mediane,
        "ecart_jauge_pct": int(ecart_jauge_pct),
        "cachet_median": cachet_median,
        "ecart_budget_eur": budget_utilisateur - cachet_median,
        "taux_recurrence": taux_recurrence,
        "recommandation": recommandation,
    }


# =====================================================================
# 5. INTERFACE UTILISATEUR (SIDEBAR & MAIN PANEL)
# =====================================================================
def main() -> None:
    # --- BARRE LATÉRALE : CONFIGURATION DE LA SALLE ---
    with st.sidebar:
        st.header("🏛️ Profil de votre salle")
        st.caption("Paramétrez vos contraintes d'exploitation pour calibrer le moteur.")

        nom_salle_user = st.text_input(
            "Nom de votre structure",
            value="Ma Salle / SMAC",
        )

        categorie_smac = st.selectbox(
            "Catégorie / Modèle économique",
            options=[
                "Club / Lieu intermédiaire (Jauge < 400)",
                "SMAC - Petite jauge (300 - 600 pl.)",
                "SMAC - Jauge intermédiaire (600 - 1200 pl.)",
                "SMAC - Grande capacité (> 1200 pl.)",
            ],
            index=1,
        )

        # Valeurs par défaut dynamiques selon la catégorie choisie
        presets = {
            "Club / Lieu intermédiaire (Jauge < 400)": (300, 3000),
            "SMAC - Petite jauge (300 - 600 pl.)": (450, 5000),
            "SMAC - Jauge intermédiaire (600 - 1200 pl.)": (850, 9500),
            "SMAC - Grande capacité (> 1200 pl.)": (1400, 16000),
        }
        def_jauge, def_budget = presets[categorie_smac]

        jauge_utilisateur = st.slider(
            "Jauge maximale (debout)",
            min_value=150,
            max_value=2500,
            value=def_jauge,
            step=50,
            help="Capacité d'accueil maximale en configuration concert.",
        )

        budget_utilisateur = st.slider(
            "Budget artistique max / plateau (€ HT)",
            min_value=1000,
            max_value=35000,
            value=def_budget,
            step=500,
            help="Enveloppe maximale allouée au contrat de cession (hors coûts d'accueil/technique).",
        )

        prix_billet_moyen = st.number_input(
            "Prix moyen du billet net (€)",
            min_value=5,
            max_value=80,
            value=18,
            step=1,
        )

        st.divider()
        st.caption(
            "💡 **Artistes pré-calibrés pour test :** `Psykup` (Club/SMAC), "
            "`7 Weeks` (Rock/Indé), `Josman` (Grande SMAC/Zénith). Tout autre nom "
            "génère une simulation déterministe."
        )

    # --- PANNEAU PRINCIPAL ---
    st.title("🎛️ Analyseur de Faisabilité Booking & Tournée")
    st.markdown(
        f"Croisement des données de tournée avec le profil **{nom_salle_user}** "
        f"*(Jauge : **{jauge_utilisateur} pl.** | Budget cible : **{budget_utilisateur:,} € HT**)*."
    )

    # Formulaire de recherche
    with st.form(key="form_recherche_artiste"):
        col_input, col_btn = st.columns([3, 1])
        with col_input:
            artiste_saisi = st.text_input(
                "Nom de l'artiste ou du groupe à analyser",
                value="Psykup",
                placeholder="Ex: Psykup, 7 Weeks, Josman...",
            )
        with col_btn:
            st.write("")  # Alignement vertical
            lancer_analyse = st.form_submit_button(
                "🔍 Lancer l'analyse de tournée",
                use_container_width=True,
                type="primary",
            )

    if lancer_analyse or artiste_saisi:
        if not artiste_saisi.strip():
            st.warning("Veuillez saisir un nom d'artiste valide pour lancer l'analyse.")
            return

        # 1. Extraction des données
        df_tournee = extraire_historique_tournee(artiste_saisi)

        # 2. Enrichissement ligne par ligne
        df_tournee["Diagnostic Ligne"] = df_tournee.apply(
            lambda row: evaluer_coherence_ligne(
                jauge_salle_tournee=row["Jauge Max"],
                budget_salle_tournee=row["Cachet Estimé (€ HT)"],
                typologie=row["Typologie"],
                jauge_utilisateur=jauge_utilisateur,
                budget_utilisateur=budget_utilisateur,
            ),
            axis=1,
        )

        # 3. Calcul du diagnostic global
        diag = calculer_diagnostic_global(
            df_tournee=df_tournee,
            jauge_utilisateur=jauge_utilisateur,
            budget_utilisateur=budget_utilisateur,
        )

        # --- AFFICHAGE DU BANDEAU DE DÉCISION ---
        st.subheader(f"Résultat d'analyse pour : {artiste_saisi.upper()}")

        if diag["statut"] == "Compatible":
            st.success(f"**{diag['badge']}** — {diag['recommandation']}")
        elif diag["statut"] == "Risqué":
            st.warning(f"**{diag['badge']}** — {diag['recommandation']}")
        else:
            st.error(f"**{diag['badge']}** — {diag['recommandation']}")

        # --- INDICATEURS CLÉS (st.metric) ---
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)

        with kpi1:
            st.metric(
                label="Score de Compatibilité",
                value=f"{diag['score']} / 100",
                delta=f"{diag['taux_recurrence']}% de salles similaires",
                delta_color="normal" if diag["score"] >= 50 else "inverse",
            )

        with kpi2:
            st.metric(
                label="Jauge Médiane Tournée",
                value=f"{diag['jauge_mediane']} pl.",
                delta=f"{diag['ecart_jauge_pct']:+d}% vs votre jauge",
                delta_color="normal" if diag["ecart_jauge_pct"] >= -20 else "inverse",
            )

        with kpi3:
            st.metric(
                label="Cachet Médian Estimé",
                value=f"{diag['cachet_median']:,} € HT",
                delta=f"{diag['ecart_budget_eur']:+,} € vs votre budget",
                delta_color="normal" if diag["ecart_budget_eur"] >= 0 else "inverse",
            )

        with kpi4:
            # Calcul du point mort billetterie pour couvrir le cachet médian
            billets_point_mort = int(diag["cachet_median"] / max(1, prix_billet_moyen))
            taux_point_mort = int((billets_point_mort / jauge_utilisateur) * 100)
            st.metric(
                label="Point Mort Billetterie (Cession)",
                value=f"{taux_point_mort}% de jauge",
                delta=f"{billets_point_mort} billets à {prix_billet_moyen} €",
                delta_color="off",
            )

        st.divider()

        # --- TABLEAU RÉCAPITULATIF DES DATES RÉCENTES ---
        st.subheader("📋 Historique récent des salles et adéquation budgétaire")

        st.dataframe(
            df_tournee,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Date": st.column_config.DateColumn("Date", format="DD/MM/YYYY"),
                "Jauge Max": st.column_config.NumberColumn("Jauge Salle", format="%d pl."),
                "Affluence Estimée": st.column_config.NumberColumn("Affluence", format="%d pers."),
                "Taux Remplissage (%)": st.column_config.ProgressColumn(
                    "Remplissage",
                    help="Taux de remplissage estimé sur la date",
                    format="%d%%",
                    min_value=0,
                    max_value=100,
                ),
                "Cachet Estimé (€ HT)": st.column_config.NumberColumn(
                    "Cachet Estimé",
                    format="%d € HT",
                ),
                "Diagnostic Ligne": st.column_config.TextColumn(
                    "Cohérence avec votre salle",
                    width="large",
                ),
            },
        )

        # --- GRAPHIQUE COMPARATIF DES JAUGES ---
        st.subheader("📊 Comparaison des jauges de la tournée (hors festivals)")
        df_graph = df_tournee[df_tournee["Typologie"] != "Festival"].set_index("Salle / Événement")
        if not df_graph.empty:
            df_graph["Votre Jauge Max"] = jauge_utilisateur
            st.bar_chart(
                df_graph[["Jauge Max", "Affluence Estimée", "Votre Jauge Max"]],
                height=320,
            )


if __name__ == "__main__":
    main()
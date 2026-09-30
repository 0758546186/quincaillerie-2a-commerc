import streamlit as st
import pandas as pd
from datetime import datetime

# Configuration de la page
st.set_page_config(page_title="2A-COMMERCE - Gestion Quincaillerie", layout="wide")

# Logo et Titre
st.title("🏗️ 2A-COMMERCE - Gestion de Quincaillerie")

# --- FONCTION DE CHARGEMENT VIA EXPORT CSV GOOGLE SHEETS ---
@st.cache_data(ttl=2)
def charger_donnees():
    try:
        SHEET_ID = "1XVI4h6XZ_-RAZio-ScbbSOwvWXmT3S49vtuKM66EhtM"
        url_csv = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Catalogue"
        
        df_cat = pd.read_csv(url_csv, skiprows=3)
        df_cat = df_cat.dropna(subset=["Désignation"])
        return df_cat
    except Exception as e:
        st.error(f"Erreur de lecture du tableau : {e}")
        return pd.DataFrame()

# Chargement des données
df = charger_donnees()

if df.empty:
    st.warning("⚠️ Impossible de charger les données du catalogue. Vérifiez le lien du Google Sheet.")
else:
    # Création des onglets principaux
    tab1, tab2, tab3 = st.tabs(["🛒 Ventes / Caisse", "📦 Arrivages / Entrées", "📊 Stock & Alertes"])

    # --- ONGLET 1 : VENTES ---
    with tab1:
        st.subheader("🛒 Enregistrement d'une Vente")
        st.dataframe(df, use_container_width=True)

    # --- ONGLET 2 : ARRIVAGES ---
    with tab2:
        st.subheader("📦 Entrée de Stock / Arrivage")
        liste_produits = df["Désignation"].tolist() if "Désignation" in df.columns else []
        produit_choisi = st.selectbox("Choisir le produit réapprovisionné", options=liste_produits)
        qte_recue = st.number_input("Quantité reçue", min_value=1, step=1, value=10)
        
        if st.button("Valider la réception"):
            st.success(f"Réception enregistrée pour {produit_choisi} (+{qte_recue})")

    # --- ONGLET 3 : STOCK & ALERTES ---
    with tab3:
        st.subheader("📊 État du Stock et Alertes")
        if "Statut Stock" in df.columns:
            alertes = df[df["Statut Stock"] == "RÉAPPROVISIONNER"]
            if not alertes.empty:
                st.warning(f"⚠ {len(alertes)} article(s) nécessitent un réapprovisionnement.")
                st.dataframe(alertes, use_container_width=True)
            else:
                st.success("✅ Tous les niveaux de stock sont suffisants.")
        else:
            st.dataframe(df, use_container_width=True)

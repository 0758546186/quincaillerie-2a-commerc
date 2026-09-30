import pandas as pd
import streamlit as st 
import urllib.parse
from datetime import datetime
import os
from fpdf import FPDF
from streamlit_gsheets import GSheetsConnection

# --- CONFIGURATION DE LA PAGE STREAMLIT ---
st.set_page_config(
    page_title="Quincaillerie 2A-Commerce",
    page_icon="📦",
    layout="wide"
)

# --- URL DU FICHIER GOOGLE SHEETS ---
URL_SHEET = "https://docs.google.com/spreadsheets/d/1XVl4h6XZ_-RAZio-ScbbSOwvWXmT3S49vtuKM66EhtM/edit"

# Initialisation de la connexion Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)
# --- FONCTION DE CHARGEMENT DES DONNÉES DEPUIS GOOGLE SHEETS ---
@st.cache_data(ttl=2)
def charger_donnees():
    try:
        SHEET_ID = "1XVl4h6XZ_-RAZio-ScbbSOwvWXmT3S49vtuKM66EhtM"
        url_csv = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Catalogue"
        
        # 1. Lecture brute
        raw_df = pd.read_csv(url_csv, header=None)
        
        # 2. Détection dynamique de l'en-tête[cite: 1]
        header_idx = None
        for i, row in raw_df.iterrows():
            row_text = " ".join([str(val).lower() for val in row.fillna('').values])
            if "désignation" in row_text or "designation" in row_text or "marque" in row_text:
                header_idx = i
                break
                
        if header_idx is not None:
            df_cat = pd.read_csv(url_csv, skiprows=header_idx)
        else:
            df_cat = pd.read_csv(url_csv, skiprows=2)
            
        # 3. Nettoyage des noms de colonnes[cite: 1]
        df_cat.columns = df_cat.columns.astype(str).str.strip()
        
        # 4. Suppression des lignes sans désignation[cite: 1]
        col_desig = [c for c in df_cat.columns if "désignation" in c.lower() or "designation" in c.lower()]
        if col_desig:
            df_cat = df_cat.dropna(subset=[col_desig[0]])
            
        # 5. Conversion numérique uniquement sur les vraies colonnes de chiffres (en ignorant Statut)[cite: 1]
        for col in df_cat.columns:
            col_lower = col.lower()
            if any(k in col_lower for k in ["stock", "prix", "seuil", "entrées", "sorties"]) and "statut" not in col_lower:
                val_clean = (
                    df_cat[col]
                    .astype(str)
                    .str.replace(',', '.', regex=False)
                    .str.replace(r'[^\d.]', '', regex=True)
                )
                df_cat[col] = pd.to_numeric(val_clean, errors='coerce').fillna(0)
                
        return df_cat
    except Exception as e:
        st.error(f"Erreur lors du chargement de Google Sheets : {e}")
        return pd.DataFrame()
# Chargement initial du dataframe
df = charger_donnees()

# --- BLOC ALERTE STOCK & WHATSAPP (BARRE LATÉRALE) ---
CONTACTS = {"Destinataire 1": "2250102996002", "Destinataire 2": "2250707066335"}
seuil_minimum = 5

if not df.empty and "Stock Actuel" in df.columns:
    stock_critique = df[df["Stock Actuel"] <= seuil_minimum]

    if not stock_critique.empty:
        st.sidebar.error(f"🚨 **ALERTE LE STOCK A ATTEINT LE SEUIL MINIMUM ({len(stock_critique)})**")

        liste_produits = ""
        for _, row in stock_critique.iterrows():
            liste_produits += f"• {row['Désignation']} (Reste : {int(row['Stock Actuel'])})\n"

        message = (
            "Salut ! Voici la liste des produits arrivés au seuil critique"
            f" (<= {seuil_minimum} unités) :\n\n"
            f"{liste_produits}\nMerci de prévoir le réapprovisionnement !"
        )

        message_encode = urllib.parse.quote(message)

        st.sidebar.markdown("---")
        st.sidebar.subheader("📩 Message direct")
        choix_destinataire = st.sidebar.selectbox("Sélectionner :", list(CONTACTS.keys()))
        numero_destinataire = CONTACTS[choix_destinataire]

        lien_direct = f"https://wa.me/{numero_destinataire}?text={message_encode}"

        st.sidebar.markdown(
            f"""
            <a href="{lien_direct}" target="_blank">
                <button style="
                    background-color: #25D366;
                    color: white;
                    border: none;
                    padding: 10px 12px;
                    border-radius: 6px;
                    font-weight: bold;
                    cursor: pointer;
                    width: 100%;
                    margin-bottom: 10px;">
                    📲 Envoyer à {choix_destinataire}
                </button>
            </a>
            """,
            unsafe_allow_html=True,
        )


# --- FONCTION DE GÉNÉRATION DU REÇU PDF ---
def generer_recu_pdf(nom_client, panier, total_general):
    pdf = FPDF()
    pdf.add_page()

    if os.path.exists("logo.png"):
        pdf.image("logo.png", x=10, y=8, w=30)

    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "2A-COMMERCE QUINCAILLERIE", ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, "Vente de Matériaux de Construction & Outillage", ln=True, align="C")
    pdf.cell(0, 6, "Abidjan, Côte d'Ivoire", ln=True, align="C")
    pdf.ln(5)
    
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(100, 6, f"Client : {nom_client}")
    pdf.cell(0, 6, f"Date : {date_str}", ln=True, align="R")
    pdf.ln(5)
    
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(90, 8, " Article / Désignation", border=1, fill=True)
    pdf.cell(25, 8, "Qté", border=1, align="C", fill=True)
    pdf.cell(35, 8, "Prix Unitaire", border=1, align="R", fill=True)
    pdf.cell(40, 8, "Total FCFA", border=1, align="R", fill=True, ln=True)
    
    pdf.set_font("Helvetica", "", 9)
    for item in panier:
        pdf.cell(90, 7, f" {str(item['Désignation'])[:45]}", border=1)
        pdf.cell(25, 7, str(item['Quantité']), border=1, align="C")
        pdf.cell(35, 7, f"{item['Prix Unitaire']:,} FCFA", border=1, align="R")
        pdf.cell(40, 7, f"{item['Total']:,} FCFA", border=1, align="R", ln=True)
        
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(150, 9, "TOTAL À PAYER : ", border=0, align="R")
    pdf.cell(40, 9, f"{total_general:,} FCFA", border=1, align="R")
    
    pdf.ln(15)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, "Merci pour votre confiance et à bientôt !", ln=True, align="C")
    
    os.makedirs("factures", exist_ok=True)
    nom_fichier_pdf = f"factures/Recu_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(nom_fichier_pdf)
    return nom_fichier_pdf


# --- FONCTION DE MISE À JOUR DU STOCK (VENTE) ---
def enregistrer_vente_excel(panier, nom_client):
    try:
        df_cat = conn.read(spreadsheet=URL_SHEET, worksheet="Catalogue", skiprows=3, ttl=0)
        df_cat = df_cat.dropna(subset=["Désignation"])

        try:
            df_mouv = conn.read(spreadsheet=URL_SHEET, worksheet="Mouvements", skiprows=3, ttl=0)
        except Exception:
            df_mouv = pd.DataFrame()

        date_jour = datetime.now().strftime("%Y-%m-%d")
        nouvelles_lignes_mouv = []

        for item in panier:
            desig = item["Désignation"]
            qte_vendue = item["Quantité"]
            prix_u = item["Prix Unitaire"]
            total_vente = item["Total"]

            idx = df_cat[df_cat["Désignation"] == desig].index

            if not idx.empty:
                i = idx[0]
                df_cat.at[i, "Sorties"] = df_cat.at[i, "Sorties"] + qte_vendue
                df_cat.at[i, "Stock Actuel"] = df_cat.at[i, "Stock Actuel"] - qte_vendue

                seuil = df_cat.at[i, "Seuil Alerte"]
                stock_actuel = df_cat.at[i, "Stock Actuel"]
                if pd.notna(seuil) and stock_actuel <= seuil:
                    df_cat.at[i, "Statut Stock"] = "RÉAPPROVISIONNER"
                else:
                    df_cat.at[i, "Statut Stock"] = "OK"

                code_art = df_cat.at[i, "Code Article"] if "Code Article" in df_cat.columns else f"ART-{desig[:3].upper()}"

            nouvelles_lignes_mouv.append({
                "Date": date_jour,
                "Type Mouvement": "Sortie",
                "Code Article": code_art,
                "Catégorie": desig,
                "Quantité": qte_vendue,
                "Prix Unitaire (FCFA)": prix_u,
                "Total FCFA": total_vente,
                "Client / Fournisseur": nom_client,
            })

        if nouvelles_lignes_mouv:
            df_nouv_mouv = pd.DataFrame(nouvelles_lignes_mouv)
            df_mouv = pd.concat([df_mouv, df_nouv_mouv], ignore_index=True)

        conn.update(spreadsheet=URL_SHEET, worksheet="Catalogue", data=df_cat, range="A4")
        conn.update(spreadsheet=URL_SHEET, worksheet="Mouvements", data=df_mouv, range="A4")

        st.cache_data.clear()
        return True

    except Exception as e:
        st.error(f"Erreur lors de la mise à jour Google Sheets : {e}")
        return False


# --- FONCTION DE RÉAPPROVISIONNEMENT (ENTRÉE DE STOCK) ---
def enregistrer_reapprovisionnement_sheets(desig, qte_recue, nom_fournisseur, prix_u):
    try:
        df_cat = conn.read(spreadsheet=URL_SHEET, worksheet="Catalogue", skiprows=3, ttl=0)
        df_cat = df_cat.dropna(subset=["Désignation"])

        try:
            df_mouv = conn.read(spreadsheet=URL_SHEET, worksheet="Mouvements", skiprows=3, ttl=0)
        except Exception:
            df_mouv = pd.DataFrame()

        idx = df_cat[df_cat["Désignation"] == desig].index

        if not idx.empty:
            i = idx[0]

            entrees_actuelles = df_cat.at[i, "Entrées"] if pd.notna(df_cat.at[i, "Entrées"]) else 0
            nouvelle_entree = entrees_actuelles + qte_recue
            df_cat.at[i, "Entrées"] = nouvelle_entree

            sorties_actuelles = df_cat.at[i, "Sorties"] if pd.notna(df_cat.at[i, "Sorties"]) else 0
            nouveau_stock = nouvelle_entree - sorties_actuelles
            df_cat.at[i, "Stock Actuel"] = nouveau_stock

            seuil = df_cat.at[i, "Seuil Alerte"]
            if pd.notna(seuil) and nouveau_stock <= seuil:
                df_cat.at[i, "Statut Stock"] = "RÉAPPROVISIONNER"
            else:
                df_cat.at[i, "Statut Stock"] = "OK"

            code_art = df_cat.at[i, "Code Article"] if "Code Article" in df_cat.columns else ""

            nouvelle_ligne_mouv = {
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Type Mouvement": "Entrée",
                "Code Article": code_art,
                "Catégorie": desig,
                "Quantité": qte_recue,
                "Prix Unitaire (FCFA)": prix_u,
                "Total FCFA": qte_recue * prix_u,
                "Client / Fournisseur": nom_fournisseur,
            }

            df_mouv = pd.concat([df_mouv, pd.DataFrame([nouvelle_ligne_mouv])], ignore_index=True)

            conn.update(spreadsheet=URL_SHEET, worksheet="Catalogue", data=df_cat, range="A4")
            conn.update(spreadsheet=URL_SHEET, worksheet="Mouvements", data=df_mouv, range="A4")
            st.cache_data.clear()

            return True

        st.warning(f"Article introuvable dans le Catalogue : {desig}")
        return False

    except Exception as e:
        st.error(f"Erreur lors de l'enregistrement du réapprovisionnement : {e}")
        return False


# --- APPLICATION PRINCIPALE ---
if df.empty:
    st.stop()

if "panier" not in st.session_state:
    st.session_state.panier = []

st.title("📦 Quincaillerie 2A-Commerce — Gestion & Caisse")

# --- NAVIGATION PRINCIPALE VIA ONGLETS ---
tab1, tab2, tab3 = st.tabs([
    "🛒 Ventes / Caisse",
    "📦 Arrivages / Entrées",
    "📊 Stock & Alertes"
])

# --- ONGLET 1 : VENTES / CAISSE ---
with tab1:
    col_recherche, col_panier = st.columns([2, 1])

    with col_recherche:
        st.subheader("🔎 Recherche au Comptoir")
        mot_cle = st.text_input("Saisissez un nom d'article, marque ou catégorie (ex: Ciment, Tuyau, 110) :")
    # --- RECHERCHE AU COMPTOIR SÉCURISÉE ---
      # --- RECHERCHE ET SELECTION ARTICLE ---
     # --- RECHERCHE ET SELECTION ARTICLE ---
        if mot_cle and not df.empty:
            mot_cle_clean = str(mot_cle).strip().lower()

            # Détection des colonnes
            def trouver_colonne(mots_cles, default_idx=0):
                for col in df.columns:
                    if any(kw in str(col).lower() for kw in mots_cles):
                        return col
                return df.columns[default_idx] if len(df.columns) > default_idx else df.columns[0]

            c_desig = trouver_colonne(["désignation", "designation"])
            c_marque = trouver_colonne(["marque"])
            c_cat = trouver_colonne(["catégorie", "categorie"])
            c_prix = trouver_colonne(["prix vente", "prix de vente"])
            c_seuil_vente = trouver_colonne(["seuil mini de vente", "seuil mini"])
            c_stock_init = trouver_colonne(["stock initial"])
            c_stock_actuel = trouver_colonne(["stock actuel"])
            c_seuil_alerte = trouver_colonne(["seuil alerte"])
            c_statut = trouver_colonne(["statut stock", "statut"])

            # Filtrage sur le mot-clé
            mask_desig = df[c_desig].astype(str).str.lower().str.contains(mot_cle_clean, regex=False, na=False)
            mask_marque = df[c_marque].astype(str).str.lower().str.contains(mot_cle_clean, regex=False, na=False)
            mask_cat = df[c_cat].astype(str).str.lower().str.contains(mot_cle_clean, regex=False, na=False)

            resultat = df[mask_desig | mask_marque | mask_cat]

            if not resultat.empty:
                st.success(f"{len(resultat)} article(s) trouvé(s)")
                
                # Tableau récapitulatif
                cols_brutes = [c_marque, c_desig, c_cat, c_prix, c_stock_init, c_stock_actuel, c_seuil_alerte, c_statut]
                cols_affichage = list(dict.fromkeys([c for c in cols_brutes if c in df.columns]))
                st.dataframe(resultat[cols_affichage], use_container_width=True)
                
                st.divider()
                st.subheader("🛒 Ajouter un produit à la vente")
                
                article_choisi = st.selectbox(
                    "Choisissez l'article exact :", 
                    options=resultat[c_desig].unique()
                )

                # Code metric 

                row_article = resultat[resultat[c_desig] == article_choisi].iloc[0]
                
                prix_conseille = row_article[c_prix] if pd.notna(row_article[c_prix]) else 0
                prix_plancher = row_article[c_seuil_vente] if pd.notna(row_article[c_seuil_vente]) else 0
                stock_actuel_val = int(row_article[c_stock_actuel]) if pd.notna(row_article[c_stock_actuel]) else 0

                # 📊 AFFICHAGE ÉPURÉ COMPACT SPÉCIAL MOBILE
                st.markdown(f"""
                <div style="display: flex; gap: 8px; justify-content: space-between; margin-top: 10px; margin-bottom: 15px; flex-wrap: nowrap;">
                    <div style="background-color: #e8f4f8; padding: 6px 10px; border-radius: 6px; flex: 1; text-align: center;">
                        <span style="font-size: 11px; color: #1f77b4; display: block; font-weight: 500;">Prix Conseillé</span>
                        <strong style="font-size: 13px; color: #0d47a1;">{prix_conseille:,.0f} FCFA</strong>
                    </div>
                    <div style="background-color: #fff8e1; padding: 6px 10px; border-radius: 6px; flex: 1; text-align: center;">
                        <span style="font-size: 11px; color: #b78103; display: block; font-weight: 500;">Prix Plancher Min</span>
                        <strong style="font-size: 13px; color: #b78103;">{prix_plancher:,.0f} FCFA</strong>
                    </div>
                    <div style="background-color: #e8f5e9; padding: 6px 10px; border-radius: 6px; flex: 1; text-align: center;">
                        <span style="font-size: 11px; color: #2e7d32; display: block; font-weight: 500;">Stock Actuel</span>
                        <strong style="font-size: 14px; color: #1b5e20;">{stock_actuel_val} pcs</strong>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # 🛒 SAISIE DE LA QUANTITÉ ET DU PRIX
                col_qte, col_prix, col_btn = st.columns([1, 1, 1])
                with col_qte:
                    qte = st.number_input("Quantité :", min_value=1, value=1, step=1)
                with col_prix:
                    prix_applique = st.number_input(
                        "Prix Unitaire Appliqué (FCFA) :", 
                        value=float(prix_conseille) if pd.notna(prix_conseille) else 0.0
                    )
                with col_btn:
                    st.write("")
                    st.write("")
                    if st.button("➕ Ajouter au Panier"):
                        if prix_plancher > 0 and prix_applique < prix_plancher:
                            st.error(f"❌ Prix inférieur au plancher ({prix_plancher:,.0f} FCFA).")
                        elif qte > stock_actuel_val:
                            st.warning(f"⚠️️ Stock insuffisant ! Disponible : {stock_actuel_val}")
                        else:
                            st.session_state.panier.append({
                                "Désignation": article_choisi,
                                "Catégorie": row_article[c_cat] if pd.notna(row_article[c_cat]) else "",
                                "Quantité": qte,
                                "Prix Unitaire": int(prix_applique),
                                "Total": int(qte * prix_applique)
                            })
                            st.success("Article ajouté au panier !")
                            st.rerun()
            else:
                st.warning(f"Aucun article ne correspond à '{mot_cle}'.")

    # --- PARTIE DROITE : GESTION DU PANIER & VALIDATION DE LA VENTE ---
    with col_panier:
        st.subheader("🛒 Panier en Cours")
        
        if st.session_state.panier:
            df_panier = pd.DataFrame(st.session_state.panier)
            st.table(df_panier[["Désignation", "Quantité", "Total"]])
            
            total_general = df_panier["Total"].sum()
            st.markdown(f"### **Total Général : {total_general:,} FCFA**")
            
            nom_client = st.text_input("Nom du Client (optionnel) :", value="Client Comptoir")
            
            col_v1, col_v2 = st.columns(2)
            with col_v1:
                if st.button("❌ Vider le panier"):
                    st.session_state.panier = []
                    st.rerun()
                
            with col_v2:
                if st.button("✅ Valider la Vente", type="primary"):
                    succes = enregistrer_vente_excel(st.session_state.panier, nom_client)
                    
                    if succes:
                        pdf_path = generer_recu_pdf(nom_client, st.session_state.panier, total_general)
                        st.success("🎉 Vente validée !")
                        
                        if os.path.exists(pdf_path):
                            with open(pdf_path, "rb") as file:
                                st.download_button(
                                    label="📄 Télécharger le Reçu PDF",
                                    data=file,
                                    file_name=os.path.basename(pdf_path),
                                    mime="application/pdf"
                                )
                        st.session_state.panier = []
                    else:
                        st.error("❌ Erreur lors de l'enregistrement de la vente.")
        else:
            st.info("Le panier est actuellement vide.")

# --- ONGLET 2 : ARRIVAGES / ENTRÉES ---
with tab2:
    st.header("📦 Enregistrement d'un Arrivage (Réapprovisionnement)")

    if not df.empty:
        with st.form("form_reapprovisionnement"):
            col1, col2 = st.columns(2)

            # Recherche sécurisée de la colonne Désignation
            col_desig_nom = [c for c in df.columns if "désignation" in c.lower() or "designation" in c.lower()]
            col_cible = col_desig_nom[0] if col_desig_nom else df.columns[0]

            with col1:
                liste_produits = df[col_cible].dropna().unique().tolist()
                produit_choisi = st.selectbox("Sélectionner l'article reçu", options=liste_produits)
                qte_recue = st.number_input("Quantité reçue (unités)", min_value=1, step=1, value=1)

            with col2:
                nom_fournisseur = st.text_input("Fournisseur / Origine", value="Fournisseur Divers")
                prix_achat = st.number_input("Prix d'achat unitaire (FCFA)", min_value=0, step=500, value=0)

            bouton_valider = st.form_submit_button("✅ Valider l'entrée en stock")

            if bouton_valider:
                if produit_choisi:
                    succes = enregistrer_reapprovisionnement_sheets(
                        produit_choisi, qte_recue, nom_fournisseur, prix_achat
                    )
                    if succes:
                        st.success(f"Stock de **{produit_choisi}** augmenté de +{qte_recue} unités avec succès !")
                        st.rerun()
                else:
                    st.error("Veuillez sélectionner un produit valide.")
    else:
        st.error("Le catalogue d'articles est actuellement vide ou inaccessible.")

# --- ONGLET 3 : STOCK & ALERTES ---
with tab3:
    st.subheader("🚨 Produits en Alerte de Stock (RÉAPPROVISIONNER)")

    if not df.empty:
        # Détection dynamique des colonnes
        def trouver_colonne(mots_cles, default_idx=0):
            for col in df.columns:
                if any(kw in str(col).lower() for kw in mots_cles):
                    return col
            return df.columns[default_idx] if len(df.columns) > default_idx else df.columns[0]

        c_statut = trouver_colonne(["statut"])
        c_marque = trouver_colonne(["marque"])
        c_desig = trouver_colonne(["désignation", "designation"])
        c_cat = trouver_colonne(["catégorie", "categorie"])
        c_stock = trouver_colonne(["stock actuel", "stock"])
        c_seuil = trouver_colonne(["seuil alerte", "seuil mini", "seuil"])

        # Filtrage souple sur le statut d'alerte
        mask_alerte = df[c_statut].astype(str).str.contains("RÉAPPROVISIONNER|REAPPROVISIONNER|ALERTE", case=False, na=False)
        
        # Sélection des colonnes disponibles sans doublons
        cols_souhaitees = [c_marque, c_desig, c_cat, c_stock, c_seuil]
        cols_existantes = [c for c in cols_souhaitees if c in df.columns]
        cols_uniques = list(dict.fromkeys(cols_existantes))
        
        df_alertes = df[mask_alerte][cols_uniques]

        if not df_alertes.empty:
            st.warning(f"Il y a actuellement **{len(df_alertes)}** articles nécessitant un réapprovisionnement.")
            st.dataframe(df_alertes, use_container_width=True)
        else:
            st.success("Tous les niveaux de stock sont corrects !")
    else:
        st.info("Aucune donnée disponible.")




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
URL_SHEET = "https://docs.google.com/spreadsheets/d/1_-SIVoV08ZeA3fgPkn_qQFn7-EVtTCps/edit"

# Initialisation de la connexion Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FONCTION DE CHARGEMENT DES DONNÉES DEPUIS GOOGLE SHEETS ---
@st.cache_data(ttl=5)
def charger_donnees():
    try:
        df_cat = conn.read(spreadsheet=URL_SHEET, worksheet="Catalogue", skiprows=3, ttl=0)
        df_cat = df_cat.dropna(subset=["Désignation"])
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
        
        if mot_cle:
            mask_desig = df["Désignation"].astype(str).str.contains(mot_cle, case=False, na=False)
            mask_marque = df["Marque"].astype(str).str.contains(mot_cle, case=False, na=False)
            mask_cat = df["Catégorie"].astype(str).str.contains(mot_cle, case=False, na=False)
            
            resultat = df[mask_desig | mask_marque | mask_cat]
            
            if not resultat.empty:
                st.success(f"{len(resultat)} article(s) trouvé(s)")
                
                cols_affichage = [
                    "Marque", "Désignation", "Catégorie", 
                    "Prix Vente (FCFA)", "Seuil mini de vente", 
                    "Stock Actuel", "Statut Stock"
                ]
                st.dataframe(resultat[cols_affichage], use_container_width=True)
                
                st.divider()
                st.subheader("🛒 Ajouter un produit à la vente")
                
                article_choisi = st.selectbox(
                    "Choisissez l'article exact :", 
                    options=resultat["Désignation"].unique()
                )
                
                row_article = resultat[resultat["Désignation"] == article_choisi].iloc[0]
                
                st.info(
                    f"**Prix de vente conseillé :** {row_article['Prix Vente (FCFA)']:,} FCFA | "
                    f"**Prix plancher (Seuil mini) :** {row_article['Seuil mini de vente'] if pd.notna(row_article['Seuil mini de vente']) else 'Non défini'} FCFA | "
                    f"**Stock disponible :** {row_article['Stock Actuel']}"
                )
                
                col_qte, col_prix, col_btn = st.columns([1, 1, 1])
                with col_qte:
                    qte = st.number_input("Quantité :", min_value=1, value=1, step=1)
                with col_prix:
                    prix_applique = st.number_input(
                        "Prix Unitaire Appliqué (FCFA) :", 
                        value=float(row_article["Prix Vente (FCFA)"]) if pd.notna(row_article["Prix Vente (FCFA)"]) else 0.0
                    )
                with col_btn:
                    st.write("")
                    st.write("")
                    if st.button("➕ Ajouter au Panier"):
                        seuil_mini = row_article["Seuil mini de vente"]
                        if pd.notna(seuil_mini) and prix_applique < seuil_mini:
                            st.error(f"❌ Impossible ! Le prix ne peut pas être inférieur au prix plancher de {seuil_mini:,} FCFA.")
                        elif qte > row_article["Stock Actuel"]:
                            st.warning("⚠️ Attention, la quantité demandée dépasse le stock actuel !")
                        else:
                            st.session_state.panier.append({
                                "Désignation": article_choisi,
                                "Catégorie": row_article["Catégorie"],
                                "Quantité": qte,
                                "Prix Unitaire": int(prix_applique),
                                "Total": int(qte * prix_applique)
                            })
                            st.success("Article ajouté au panier !")
                            st.rerun()
            else:
                st.warning(f"Aucun article ne correspond à '{mot_cle}'.")

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
                        st.success("🎉 Vente validée et stock mis à jour dans Google Sheets !")
                        
                        with open(pdf_path, "rb") as file:
                            st.download_button(
                                label="📄 Télécharger le Reçu PDF",
                                data=file,
                                file_name=os.path.basename(pdf_path),
                                mime="application/pdf"
                            )
                        st.session_state.panier = []
        else:
            st.info("Le panier est actuellement vide.")


# --- ONGLET 2 : ARRIVAGES / ENTRÉES ---
with tab2:
    st.header("📦 Enregistrement d'un Arrivage (Réapprovisionnement)")

    with st.form("form_reapprovisionnement"):
        col1, col2 = st.columns(2)

        with col1:
            liste_produits = df["Désignation"].dropna().unique().tolist()
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


# --- ONGLET 3 : STOCK & ALERTES ---
with tab3:
    st.subheader("🚨 Produits en Alerte de Stock (RÉAPPROVISIONNER)")

    if "Statut Stock" in df.columns:
        df_alertes = df[df["Statut Stock"] == "RÉAPPROVISIONNER"][["Marque", "Désignation", "Catégorie", "Stock Actuel", "Seuil Alerte"]]
        if not df_alertes.empty:
            st.warning(f"Il y a actuellement **{len(df_alertes)}** articles nécessitant un réapprovisionnement.")
            st.dataframe(df_alertes, use_container_width=True)
        else:
            st.success("Tous les niveaux de stock sont corrects !")

import pandas as pd
import streamlit as st 
import urllib.parse
from datetime import datetime
import os
from fpdf import FPDF
import json
from streamlit_gsheets import GSheetsConnection
import gspread
from google.oauth2.service_account import Credentials



# --- CONFIGURATION DE LA PAGE STREAMLIT ---
st.set_page_config(
    page_title="Quincaillerie 2A-Commerce",
    page_icon="📦",
    layout="wide"
)

# --- URL DU FICHIER GOOGLE SHEETS ---
URL_SHEET = "https://docs.google.com/spreadsheets/d/1XVl4h6XZ_-RAZio-ScbbSOwvWXmT3S49vtuKM66EhtM/edit"

# Initialisation native avec les secrets TOML Streamlit
if "gcp_service_account" in st.secrets:
    service_account_info = dict(st.secrets["gcp_service_account"])
else:
    st.error("Section [gcp_service_account] introuvable dans les Secrets Streamlit.")
    st.stop()

# Connexion unique à Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- FONCTION DE CHARGEMENT DES DONNÉES DEPUIS GOOGLE SHEETS ---
@st.cache_data(ttl=60)
def charger_donnees():
    try:
        # TENTATIVE 1 : Utilisation de gspread si les secrets sont configurés
        if "gcp_service_account" in st.secrets:
            client = obtenir_connexion_gsheets()
            SHEET_ID = "1XVl4h6XZ_-RAZio-ScbbSOwvWXmT3S49vtuKM66EhtM"
            sheet = client.open_by_key(SHEET_ID).worksheet("Catalogue")
            records = sheet.get_all_records()
            df = pd.DataFrame(records)
            df.columns = df.columns.str.strip()
            return df
    except Exception:
        pass

    # TENTATIVE 2 : Lien d'accès direct Google Viz (plus stable que /export?format=csv)
    try:
        SHEET_ID = "1XVl4h6XZ_-RAZio-ScbbSOwvWXmT3S49vtuKM66EhtM"
        url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Catalogue"
        df = pd.read_csv(url)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Erreur lors du chargement des données : {e}")
        return None


# --- CONNEXION SÉCURISÉE À GOOGLE SHEETS VIA STREAMLIT SECRETS ---
@st.cache_resource
def obtenir_connexion_gsheets():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    return client


# --- FONCTION DE MISE À JOUR DU STOCK DANS GOOGLE SHEETS ---
def mettre_a_jour_stock_gsheet(panier, mode="vente"):
    try:
        client = obtenir_connexion_gsheets()
        SHEET_ID = "1XVl4h6XZ_-RAZio-ScbbSOwvWXmT3S49vtuKM66EhtM"
        sheet = client.open_by_key(SHEET_ID).worksheet("Catalogue")
        
        donnees = sheet.get_all_values()
        
        header_idx = None
        headers = []
        for i, row in enumerate(donnees):
            row_text = " ".join([str(v).lower() for v in row])
            if "désignation" in row_text or "designation" in row_text:
                header_idx = i
                headers = [str(h).strip().lower() for h in row]
                break

        if header_idx is None:
            return False, "En-tête non trouvé dans le Sheet."

        idx_desig = next((i for i, h in enumerate(headers) if "désignation" in h or "designation" in h), None)
        idx_stock = next((i for i, h in enumerate(headers) if "stock actuel" in h or "stock" in h), None)

        if idx_desig is None or idx_stock is None:
            return False, "Colonnes introuvables."

        for item in panier:
            nom_article = item["Désignation"]
            qte = item["Quantité"]

            for row_num in range(header_idx + 1, len(donnees)):
                if donnees[row_num][idx_desig].strip().lower() == nom_article.strip().lower():
                    try:
                        val_actuelle = float(donnees[row_num][idx_stock].replace(',', '.'))
                    except ValueError:
                        val_actuelle = 0.0

                    if mode == "vente":
                        nouveau_stock = max(0, int(val_actuelle - qte))
                    else:
                        nouveau_stock = int(val_actuelle + qte)

                    sheet.update_cell(row_num + 1, idx_stock + 1, nouveau_stock)
                    break

        st.cache_data.clear()
        return True, "Stock mis à jour avec succès !"

    except Exception as e:
        return False, f"Erreur Google Sheets : {e}"


# --- CHARGEMENT INITIAL DU DATAFRAME ---
df = charger_donnees()
# Chargement initial du dataframe
df_initial = charger_donnees()
df = df_initial if df_initial is not None else pd.DataFrame()


# --- BLOC ALERTE STOCK & WHATSAPP (BARRE LATÉRALE) ---
CONTACTS = {"Destinataire 1": "2250102996002", "Destinataire 2": "2250707066335"}
seuil_minimum = 5

if not df.empty and "Stock Actuel" in df.columns:
    # Convertir la colonne Stock Actuel en nombre (remplace les erreurs/textes par 0)
    df["Stock Actuel Num"] = pd.to_numeric(df["Stock Actuel"].astype(str).str.replace(',', '.'), errors='coerce').fillna(0)
    
    # Filtrer les stocks critiques avec la version numérique
    stock_critique = df[df["Stock Actuel Num"] <= seuil_minimum]

    if not stock_critique.empty:
        st.sidebar.error(f"🚨 **ALERTE LE STOCK A ATTEINT LE SEUIL MINIMUM ({len(stock_critique)})**")

        liste_produits = ""
        for _, row in stock_critique.iterrows():
            liste_produits += f"• {row['Désignation']} (Reste : {int(row['Stock Actuel Num'])})\n"

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
def encode_latin1(texte):
    """Convertit les caractères accentués/spéciaux pour éviter UnicodeEncodeError dans FPDF"""
    if texte is None:
        return ""
    if not isinstance(texte, str):
        texte = str(texte)
    # Remplacer les apostrophes typographiques et espaces insecables fréquents
    texte = texte.replace("’", "'").replace("–", "-")
    return texte.encode('latin-1', 'replace').decode('latin-1')

def generer_recu_pdf(nom_client, panier, total_general):
    pdf = FPDF()
    pdf.add_page()

    if os.path.exists("logo.png"):
        pdf.image("logo.png", x=10, y=8, w=30)

    # Entête entreprise
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, encode_latin1("2A-COMMERCE QUINCAILLERIE"), ln=True, align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, encode_latin1("Vente de Matériaux de Construction & Outillage"), ln=True, align="C")
    pdf.cell(0, 6, encode_latin1("Angré Château — Abidjan, Côte d'Ivoire"), ln=True, align="C")
    pdf.ln(5)
    
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    
    # Infos Vente & Client
    date_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(100, 6, encode_latin1(f"Client : {nom_client}"))
    pdf.cell(0, 6, encode_latin1(f"Date : {date_str}"), ln=True, align="R")
    pdf.ln(5)
    
    # Entête du tableau
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(90, 8, encode_latin1(" Article / Désignation"), border=1, fill=True)
    pdf.cell(25, 8, encode_latin1("Qté"), border=1, align="C", fill=True)
    pdf.cell(35, 8, encode_latin1(" Unitaire"), border=1, align="R", fill=True)
    pdf.cell(40, 8, encode_latin1("Total FCFA"), border=1, align="R", fill=True, ln=True)
    
    # Lignes du panier
    pdf.set_font("Helvetica", "", 9)
    for item in panier:
        designation = encode_latin1(str(item.get('Désignation', item.get('article', 'Article')))[:45])
        quantite = encode_latin1(str(item.get('Quantité', item.get('quantite', 1))))
        _unitaire = encode_latin1(f"{item.get(' Unitaire', item.get('prix_unitaire', 0)):,} FCFA")
        total_ligne = encode_latin1(f"{item.get('Total', item.get('total', 0)):,} FCFA")

        pdf.cell(90, 7, f" {designation}", border=1)
        pdf.cell(25, 7, quantite, border=1, align="C")
        pdf.cell(35, 7, prix_unitaire, border=1, align="R")
        pdf.cell(40, 7, total_ligne, border=1, align="R", ln=True)
        
    # Total
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(150, 9, encode_latin1("TOTAL À PAYER : "), border=0, align="R")
    pdf.cell(40, 9, encode_latin1(f"{total_general:,} FCFA"), border=1, align="R")
    
    # Pied de page
    pdf.ln(15)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(0, 5, encode_latin1("Merci pour votre confiance et à bientôt !"), ln=True, align="C")
    
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

               # Conversion sécurisée des prix
                try:
                    p_cons_num = float(str(prix_conseille).replace(' ', '').replace(',', '.'))
                    txt_prix_conseille = f"{p_cons_num:,.0f}".replace(',', ' ')
                except (ValueError, TypeError):
                    txt_prix_conseille = str(prix_conseille)

                try:
                    p_plan_num = float(str(prix_plancher).replace(' ', '').replace(',', '.'))
                    txt_prix_plancher = f"{p_plan_num:,.0f}".replace(',', ' ')
                except (ValueError, TypeError):
                    txt_prix_plancher = str(prix_plancher)

                # 📊 AFFICHAGE ÉPURÉ COMPACT SPÉCIAL MOBILE
                st.markdown(f"""
                <div style="display: flex; gap: 8px; justify-content: space-between; margin-top: 10px; margin-bottom: 15px; flex-wrap: nowrap;">
                    <div style="background-color: #e8f4f8; padding: 6px 10px; border-radius: 6px; flex: 1; text-align: center;">
                        <span style="font-size: 11px; color: #1f77b4; display: block; font-weight: 500;">Prix Conseillé</span>
                        <strong style="font-size: 13px; color: #0d47a1;">{txt_prix_conseille} FCFA</strong>
                    </div>
                    <div style="background-color: #fff8e1; padding: 6px 10px; border-radius: 6px; flex: 1; text-align: center;">
                        <span style="font-size: 11px; color: #b78103; display: block; font-weight: 500;">Prix Plancher Min</span>
                        <strong style="font-size: 13px; color: #b78103;">{txt_prix_plancher} </strong>
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
                    qte = st.number_input("Quantité :", min_value=1, value=1, step=1, key="input_qte_vente")
                
                with col_prix:
                    # Nettoyage sécurisé pour extraire uniquement la valeur numérique
                    if pd.notna(prix_conseille):
                        val_clean = "".join(c for c in str(prix_conseille) if c.isdigit() or c in ['.', ',']).replace(',', '.')
                        prix_valeur_num = float(val_clean) if val_clean else 0.0
                    else:
                        prix_valeur_num = 0.0

                    prix_applique = st.number_input(
                        "Prix Unitaire Appliqué (FCFA) :", 
                        value=prix_valeur_num,
                        key="input_prix_vente"
                    )

                with col_btn:
                    st.write("") # Espacement pour aligner verticalement
                    st.write("")
                    if st.button("➕ Ajouter au Panier", use_container_width=True, key="btn_ajouter_panier"):
                        if prix_plancher_num > 0 and prix_applique < prix_plancher_num:
                            st.error(f"❌ Prix inférieur au plancher ({prix_plancher_num:,.0f} FCFA).")
                        elif qte > stock_actuel_val:
                            st.warning(f"⚠️ Stock insuffisant ! Disponible : {stock_actuel_val}")
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

# --- PARTIE DROITE : GESTION DU PANIER & VALIDATION DE LA VENTE ---
    with col_panier:
        st.subheader("🛒 Panier en Cours")
        
        if st.session_state.panier:
            df_panier = pd.DataFrame(st.session_state.panier)
            st.table(df_panier[["Désignation", "Quantité", "Total"]])
            
            total_general = df_panier["Total"].sum()
            st.markdown(f"### **Total Général : {total_general:,} FCFA**")
            
            nom_client = st.text_input("Nom du Client (optionnel) :", value="Client Comptoir")
            
            # Définition obligatoire des deux colonnes
            col_v1, col_v2 = st.columns(2)
            
            with col_v1:
                if st.button("❌ Vider le panier"):
                    st.session_state.panier = []
                    st.rerun()
                
            with col_v2:
                if st.button("✅ Valider la Vente", type="primary"):
                    with st.spinner("Mise à jour du Google Sheet en cours..."):
                        # 1. Mise à jour du stock
                        succes, msg = mettre_a_jour_stock_gsheet(st.session_state.panier, mode="vente")
                        
# 2. Enregistrement dans l'onglet Mouvements
                        if succes:
                            try:
                                df_mouvements = conn.read(worksheet="Mouvements", ttl=0)
                                date_jour = datetime.now().strftime("%Y-%m-%d")
                                nouvelles_lignes = []
                                
                                for item in st.session_state.panier:
                                    nouvelles_lignes.append({
                                        "Date": str(date_jour),
                                        "Type Mouvement": "Sortie",
                                        "Code Article": str(item.get("Code Article", item.get("Code", item.get("code", "ART")))),
                                        "Catégorie": str(item.get("Catégorie", item.get("categorie", ""))),
                                        "Quantité": int(item.get("Quantité", item.get("quantite", 1))),
                                        "Prix Unitaire (FCFA)": float(item.get("Prix Unitaire", item.get("prix_unitaire", 0))),
                                        "Total FCFA": float(item.get("Total", item.get("total", 0))),
                                        "Client / Fournisseur": str(nom_client)
                                    })
                                
                                df_nouv = pd.DataFrame(nouvelles_lignes)
                                
                                # Fusion et nettoyage des valeurs NaN (évite le HTTP 400)
                                df_final_mouv = pd.concat([df_mouvements, df_nouv], ignore_index=True)
                                df_final_mouv = df_final_mouv.fillna("")
                                
                                # Envoi à Google Sheets
                                conn.update(worksheet="Mouvements", data=df_final_mouv)
                            except Exception as e_mouv:
                                st.warning(f"Stock mis à jour, mais enregistrement Mouvements échoué : {e_mouv}")

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




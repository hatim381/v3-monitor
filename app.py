import streamlit as st
import requests
import pandas as pd
import sqlite3
import os
import altair as alt
from datetime import datetime, timedelta

# --- CONFIGURATION ---
st.set_page_config(page_title="V³ Monitor - EFREI Edition", page_icon="🚲", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS (EFREI COLORS & LIGHT THEME FORCE) ---
st.markdown("""
    <style>
    /* FORCE LIGHT THEME: Overwrite Streamlit dark mode defaults if config fails */
    :root {
        --primary-color: #005DAA;
        --background-color: #FFFFFF;
        --secondary-background-color: #F0F2F6;
        --text-color: #000000;
        --font: "sans serif";
    }
    
    /* Force background to white */
    .stApp {
        background-color: #FFFFFF !important;
        color: #000000 !important;
    }
    
    /* Sidebar background */
    [data-testid="stSidebar"] {
        background-color: #F0F2F6 !important;
    }
    [data-testid="stSidebar"] * {
        color: #000000 !important;
    }

    /* Force text colors to black for readability */
    p, div, label, span, li {
        color: #000000 !important;
    }

    /* Couleurs EFREI : Bleu #005DAA, Bleu Clair #5BC5F2 */
    
    /* Titres en bleu EFREI */
    h1, h2, h3, h4, .stMetric label {
        color: #005DAA !important;
    }
    
    /* Barres de progression */
    .stProgress > div > div > div > div {
        background-color: #005DAA;
    }
    
    /* Boutons */
    .stButton button {
        background-color: #005DAA;
        color: white !important; /* Force white text on blue buttons */
        border-radius: 8px;
    }
    .stButton button:hover {
        background-color: #004a87;
        color: white !important;
    }
    
    /* Onglets */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-weight: bold;
        color: #000000 !important; /* Tab labels black */
    }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] p {
        color: #005DAA !important; /* Selected tab blue */
    }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        border-bottom-color: #005DAA;
    }
    </style>
""", unsafe_allow_html=True)

API_KEY = "PWX0HJQMSI"
API_URL = f"https://data.bordeaux-metropole.fr/geojson?key={API_KEY}&typename=ci_vcub_p"

# --- FONCTIONS ---

@st.cache_data(ttl=60)
def get_live_data():
    """Récupère les données en direct via l'API Bordeaux Métropole"""
    try:
        response = requests.get(API_URL)
        response.raise_for_status()
        data = response.json()
        
        stations = data['features']
        processed_data = []

        for s in stations:
            props = s['properties']
            geometry = s['geometry']['coordinates']
            
            # Extraction des données (clés minuscules selon l'API TBM)
            nom = props.get('nom', 'Inconnue')
            total = int(props.get('nbvelos', 0))
            elec = int(props.get('nbelec', 0))
            classic = int(props.get('nbclassiq', 0))
            places = int(props.get('nbplaces', 0))
            etat = props.get('etat', 'DECONNECTEE')
            
            # Calcul de la couleur pour la map
            if total == 0:
                color = '#FF0000' # Rouge (Vide)
            elif total < 5:
                color = '#FFA500' # Orange (Faible)
            else:
                color = '#005DAA' # Bleu EFREI (OK)

            # On ne garde que les stations connectées ou avec des données
            if etat == 'CONNECTEE' or total > 0 or places > 0:
                processed_data.append({
                    'Station': nom,
                    'Total': total,
                    '⚡ Électriques': elec,
                    '🚲 Classiques': classic,
                    'Places': places,
                    'lat': geometry[1],
                    'lon': geometry[0],
                    'color': color,
                    'size': 20 if total > 0 else 10
                })

        return pd.DataFrame(processed_data)
    except Exception as e:
        st.error(f"Erreur API TBM : {e}")
        return pd.DataFrame()

def get_history_stats(hours_lookback=24):
    """Lit la DB pour calculer les mouvements sur les X dernières heures"""
    if not os.path.exists(DB_NAME):
        return None, None

    try:
        conn = sqlite3.connect(DB_NAME)
        
        # On filtre pour ne pas charger 1 an de données d'un coup
        time_threshold = (datetime.now() - timedelta(hours=hours_lookback)).strftime("%Y-%m-%d %H:%M:%S")
        
        query = f"""
            SELECT timestamp, station_name, free_bikes 
            FROM stations_history 
            WHERE timestamp > '{time_threshold}'
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return pd.DataFrame(), pd.Series()

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # --- ALGORITHME DE MOUVEMENT ---
        # Trie par station puis par temps
        df_sorted = df.sort_values(['station_name', 'timestamp'])
        
        # Calcule la différence absolue avec la ligne précédente pour chaque station
        # Ex: 10h00 (12 vélos) -> 10h05 (10 vélos) = Mouvement de 2
        df_sorted['mouvement'] = df_sorted.groupby('station_name')['free_bikes'].diff().abs()
        
        # On remplit les NaN (première ligne de chaque station) par 0
        df_sorted['mouvement'] = df_sorted['mouvement'].fillna(0)

        # Total des mouvements par station
        top_stations = df_sorted.groupby('station_name')['mouvement'].sum().sort_values(ascending=False).head(10)
        
        return df_sorted, top_stations

    except Exception as e:
        st.error(f"Erreur SQL : {e}")
        return None, None

def get_recent_logs(limit=50):
    """Récupère les derniers logs bruts de la DB"""
    if not os.path.exists(DB_NAME):
        return pd.DataFrame()
    
    try:
        conn = sqlite3.connect(DB_NAME)
        query = f"""
            SELECT timestamp, station_name, free_bikes, empty_slots 
            FROM stations_history 
            ORDER BY timestamp DESC 
            LIMIT {limit}
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        st.error(f"Erreur SQL Logs : {e}")
        return pd.DataFrame()

# --- INTERFACE ---

st.title("🚲 V³ Bordeaux - Monitor")
st.markdown("Dashboard temps réel via l'API officielle Bordeaux Métropole.")

# Sidebar Filters
with st.sidebar:
    st.header("🔍 Filtres & Options")
    if st.button("🔄 Actualiser les données", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    
    st.markdown("---")
    min_bikes = st.slider("Afficher stations avec au moins X vélos :", 0, 20, 0)
    show_elec_only = st.checkbox("Seulement avec vélos électriques")

# Logo EFREI
col_logo, col_title = st.columns([1, 4])
with col_logo:
    st.image("data:image/png;base64,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", width=150)
with col_title:
    st.title("🚲 V³ Bordeaux - Monitor")

st.markdown("Dashboard temps réel via l'API officielle Bordeaux Métropole.")

# --- LIVE ONLY (No History in this version) ---
df_live = get_live_data()

if not df_live.empty:
    # Application des filtres Sidebar
    df_filtered = df_live[df_live['Total'] >= min_bikes].copy()
    if show_elec_only:
        df_filtered = df_filtered[df_filtered['⚡ Électriques'] > 0]

    # Métriques Globales
    total_bikes = df_live['Total'].sum()
    total_slots = df_live['Places'].sum()
    occupancy = (total_bikes / (total_bikes + total_slots) * 100) if (total_bikes + total_slots) > 0 else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stations actives", len(df_filtered))
    c2.metric("Total Vélos", total_bikes)
    c3.metric("⚡ Dont Électriques", df_live['⚡ Électriques'].sum())
    c4.metric("Taux de Remplissage", f"{occupancy:.1f}%")

    col_map, col_data = st.columns([3, 2])
    
    with col_map:
        # Map avec couleurs dynamiques
        st.map(df_filtered, latitude='lat', longitude='lon', size='size', color='color')
        st.caption(f"🔴 Vide | 🟠 < 5 vélos | 🔵 > 5 vélos")

    with col_data:
        search = st.text_input("🔎 Rechercher une station", placeholder="Ex: Victoire")
        
        df_display = df_filtered.copy()
        if search:
            df_display = df_display[df_display['Station'].str.contains(search, case=False)]
        
        # Affichage propre avec barres de progression pour le stock
        st.dataframe(
            df_display[['Station', 'Total', '⚡ Électriques', 'Places']],
            hide_index=True,
            use_container_width=True,
            column_config={
                "Total": st.column_config.ProgressColumn(
                    "Total", format="%d", min_value=0, max_value=40,
                ),
                "⚡ Électriques": st.column_config.NumberColumn(
                    "⚡ Elec.", format="%d"
                )
            }
        )
else:
    st.warning("Impossible de récupérer les données API.")
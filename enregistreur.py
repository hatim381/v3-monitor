import requests
import sqlite3
import time
from datetime import datetime
import os

# Configuration
DB_NAME = os.getenv("DB_PATH", "bordeaux.db")
API_URL = "https://api.citybik.es/v2/networks/v3-bordeaux"
HEADERS = {'User-Agent': 'Mozilla/5.0'}
INTERVALLE = 60  # Enregistrer toutes les 60 secondes

def init_db():
    """Crée la base de données si elle n'existe pas"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # On stocke : date, nom de la station, vélos dispos
    c.execute('''CREATE TABLE IF NOT EXISTS stations_history
                 (timestamp DATETIME, station_name TEXT, free_bikes INTEGER, empty_slots INTEGER)''')
    conn.commit()
    conn.close()
    print(f"Base de données initialisée : {DB_NAME}")

def save_data():
    """Récupère les données API et les sauvegarde"""
    try:
        response = requests.get(API_URL, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        
        timestamp = datetime.now()
        stations = data['network']['stations']
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        
        print(f"[{timestamp.strftime('%H:%M:%S')}] Enregistrement de {len(stations)} stations...")
        
        for s in stations:
            c.execute("INSERT INTO stations_history VALUES (?, ?, ?, ?)", 
                      (timestamp, s['name'], s['free_bikes'], s['empty_slots']))
            
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Erreur : {e}")

import sys

if __name__ == "__main__":
    init_db()
    
    # Mode "One Shot" pour GitHub Actions (lance une fois et s'arrête)
    if "--once" in sys.argv:
        print("Mode ONE SHOT activé.")
        save_data()
        exit(0)

    print("L'enregistreur est lancé. Laissez cette fenêtre ouverte pour accumuler des données.")
    print("Appuyez sur Ctrl+C pour arrêter.")
    
    while True:
        save_data()
        time.sleep(INTERVALLE)


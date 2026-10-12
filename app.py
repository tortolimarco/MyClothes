import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import psycopg2
import psycopg2.extras

app = Flask(__name__)
app.secret_key = 'super_secret_key_per_myclothes'  # Chiave segreta per le sessioni

# Connessione al database PostgreSQL su Supabase (con connection pooling sulla porta 6543)
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres.wmnotzgjuamxsgczwpmt:TuaPasswordQui@aws-0-eu-central-1.pooler.supabase.com:6543/postgres')

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
    return conn

# Inizializzazione delle tabelle nel database se non esistono
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Tabella Utenti
    cur.execute("""
        CREATE TABLE IF NOT EXISTS utenti (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
    """)
    
    # Tabella Ordini (Aggiornata per PayPal automatico)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ordini (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES utenti(id),
            paypal_order_id TEXT,
            importo REAL NOT NULL,
            stato TEXT DEFAULT 'Pagato',
            data_ordine TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Tabella Recensioni
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recensioni (
            id SERIAL PRIMARY KEY,
            autore TEXT NOT NULL,
            testo TEXT NOT NULL,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Tabella Chat
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chat (
            id SERIAL PRIMARY KEY,
            mittente TEXT NOT NULL,
            messaggio TEXT NOT NULL,
            data TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Tabella Log Visitatori (Tracciamento anonimo)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS visitatori (
            id SERIAL PRIMARY KEY,
            ip TEXT,
            user_agent TEXT,
            session_id TEXT,
            data_visita TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    conn.commit()
    cur.close()
    conn.close()

# Eseguiamo l'inizializzazione all'avvio
try:
    init_db()
except Exception as e:
    print(f"Errore durante l'inizializzazione del database: {e}")

@app.before_request
def registra_visitatore():
    # Evitiamo di tracciare le richieste interne o statiche se necessario
    if request.endpoint == 'static':
        return
        
    ip = request.remote_addr
    user_agent = request.headers.get('User-Agent', 'Sconosciuto')
    session_id = session.get('sid', 'anonimo')
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO visitatori (ip, user_agent, session_id) VALUES (%s, %s, %s)", (ip, user_agent, session_id))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore tracciamento visitatore: {e}")

# ---- ROTTA: INDEX (Homepage & Catalogo) ----
@app.route('/')
def index():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM recensioni ORDER BY data DESC;")
        recensioni = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore caricamento recensioni: {e}")
        recensioni = []
        
    return render_template('index.html', recensioni=recensioni)

# ---- ROTTA: LOGIN & REGISTRAZIONE ----
@app.route('/login', methods=['GET', 'POST'])
def login():
    errore = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Cerca se l'utente esiste già
            cur.execute("SELECT * FROM utenti WHERE username = %s AND password = %s", (username, password))
            utente = cur.fetchone()
            
            if utente:
                session['user_id'] = utente['id']
                session['username'] = utente['username']
                cur.close()
                conn.close()
                return redirect(url_for('index'))
            else:
                # Se non esiste, lo registriamo automaticamente per comodità
                try:
                    cur.execute("INSERT INTO utenti (username, password) VALUES (%s, %s) RETURNING id;", (username, password))
                    new_user = cur.fetchone()
                    conn.commit()
                    
                    session['user_id'] = new_user['id']
                    session['username'] = username
                    cur.close()
                    conn.close()
                    return redirect(url_for('index'))
                except Exception as reg_err:
                    conn.rollback()
                    errore = "Credenziali non valide o utente già esistente con altra password."
            
            cur.close()
            conn.close()
        except Exception as e:
            errore = f"Errore di connessione al database: {str(e)}"
            
    return render_template('login.html', errore=errore)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# ---- ROTTA: CHECKOUT & PAGAMENTO AUTOMATICO PAYPAL ----
@app.route('/conferma-pagamento-paypal', methods=['POST'])
def conferma_pagamento_paypal():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Utente non autenticato'}), 401
        
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'error': 'Dati non validi'}), 400
        
    order_id = data.get('orderID')
    details = data.get('details')
    
    if not details or details.get('status') != 'COMPLETED':
        return jsonify({'success': False, 'error': 'Pagamento PayPal non completato'}), 400

    user_id = session['user_id']
    
    try:
        importo = float(details['purchase_units'][0]['amount']['value'])
    except (KeyError, ValueError, TypeError):
        importo = 0.0

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Inserisce l'ordine direttamente come 'Pagato'
        cur.execute("""
            INSERT INTO ordini (user_id, paypal_order_id, importo, stato)
            VALUES (%s, %s, %s, 'Pagato')
            RETURNING id;
        """, (user_id, order_id, importo))
        
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ---- ROTTA: MIEI ORDINI (Reindirizzamento post-pagamento) ----
@app.route('/miei-ordini')
def miei_ordini():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    user_id = session['user_id']
    ordini = []
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, paypal_order_id, importo, stato, data_ordine 
            FROM ordini 
            WHERE user_id = %s 
            ORDER BY data_ordine DESC;
        """, (user_id,))
        ordini = cur.fetchall()
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore recupero ordini: {e}")
    
    return render_template('miei_ordini.html', ordini=ordini)

# ---- ROTTA: ADMIN (Pannello di controllo) ----
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    auth = request.args.get('pwd') == 'myclothesadmin' or session.get('is_admin')
    errore = None
    
    if request.method == 'POST':
        if request.form.get('password') == 'myclothesadmin':
            session['is_admin'] = True
            auth = True
        else:
            errore = "Password errata"

    if not auth:
        return render_template('admin.html', auth=False, errore=errore)

    ordini = []
    utenti = []
    visitatori = []

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Recupera tutti gli ordini
        cur.execute("""
            SELECT ordini.*, utenti.username 
            FROM ordini 
            JOIN utenti ON ordini.user_id = utenti.id 
            ORDER BY data_ordine DESC;
        """)
        ordini = cur.fetchall()
        
        # Recupera utenti registrati
        cur.execute("SELECT * FROM utenti;")
        utenti = cur.fetchall()
        
        # Recupera visitatori
        cur.execute("SELECT * FROM visitatori ORDER BY data_visita DESC LIMIT 50;")
        visitatori = cur.fetchall()
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Errore caricamento dati admin: {e}")
    
    return render_template('admin.html', auth=True, ordini=ordini, utenti=utenti, visitatori=visitatori)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)

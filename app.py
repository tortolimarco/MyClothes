from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import uuid
import os
import psycopg2
import psycopg2.extras

app = Flask(__name__)
app.secret_key = "chiave_segreta_super_sicura_myclothes"

ADMIN_PASSWORD = "myclothesadmin!"

# Prende la connessione da Render (Supabase), altrimenti usa un fallback locale se testato in locale
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
    else:
        raise RuntimeError("DATABASE_URL non configurata!")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabella Utenti Registrati
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS utenti (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            user_id TEXT NOT NULL,
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Tabella Visitatori / Accessi al sito
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS visitatori (
            user_id TEXT PRIMARY KEY,
            user_agent TEXT,
            ip_address TEXT,
            ultimo_accesso TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Tabella Chat
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            mittente TEXT NOT NULL,
            testo TEXT,
            immagine TEXT
        )
    ''')
    # Tabella Ordini (Aggiornata per PayPal automatico e rimozione bonifico)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ordini (
            id TEXT PRIMARY KEY,
            codice TEXT NOT NULL,
            user_id TEXT NOT NULL,
            email TEXT NOT NULL,
            prodotto TEXT NOT NULL,
            importo TEXT NOT NULL,
            metodo TEXT NOT NULL,
            stato TEXT NOT NULL,
            motivo_annullamento TEXT,
            nome TEXT,
            indirizzo TEXT,
            citta TEXT,
            paypal_order_id TEXT
        )
    ''')
    # Tabella Recensioni
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recensioni (
            id SERIAL PRIMARY KEY,
            ordine_id TEXT NOT NULL,
            codice_ordine TEXT NOT NULL,
            email TEXT NOT NULL,
            prodotto TEXT NOT NULL,
            stelle INTEGER NOT NULL,
            commento TEXT,
            immagine TEXT,
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Tabella Contatore Ordini
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contatore (
            id INTEGER PRIMARY KEY,
            valore INTEGER NOT NULL
        )
    ''')
    cursor.execute('SELECT valore FROM contatore WHERE id = 1')
    if not cursor.fetchone():
        cursor.execute('INSERT INTO contatore (id, valore) VALUES (1, 0)')
    
    conn.commit()
    cursor.close()
    conn.close()

# Inizializza il database all'avvio
init_db()

def get_current_user():
    return session.get('user_email')

def get_user_id():
    if 'user_email' in session:
        email = session['user_email']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM utenti WHERE email = %s', (email,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            uid = row[0]
            registra_visitatore(uid)
            return uid
            
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
        
    uid = session['user_id']
    registra_visitatore(uid)
    return uid

def registra_visitatore(uid):
    user_agent = request.headers.get('User-Agent', 'Dispositivo sconosciuto')
    ip_address = request.remote_addr or 'IP non disponibile'
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO visitatori (user_id, user_agent, ip_address, ultimo_accesso)
        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET 
        ultimo_accesso = CURRENT_TIMESTAMP,
        user_agent = EXCLUDED.user_agent,
        ip_address = EXCLUDED.ip_address
    ''', (uid, user_agent, ip_address))
    conn.commit()
    cursor.close()
    conn.close()

@app.route('/')
def home():
    uid = get_user_id()
    user_email = get_current_user()
    
    auth_error = session.pop('auth_error', None)
    active_tab = session.pop('active_tab', 'login')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT mittente, testo, immagine FROM chat WHERE user_id = %s', (uid,))
    chat_rows = cursor.fetchall()
    chat_utente = [{"mittente": r['mittente'], "testo": r['testo'], "immagine": r['immagine']} for r in chat_rows]
    
    cursor.execute('SELECT id, codice, prodotto, importo, metodo, stato, motivo_annullamento, nome, indirizzo, citta FROM ordini WHERE user_id = %s', (uid,))
    ord_rows = cursor.fetchall()
    ordini_utente = [{
        "id": r['id'], "codice": r['codice'], "prodotto": r['prodotto'], "importo": r['importo'],
        "metodo": r['metodo'], "stato": r['stato'], "motivo_annullamento": r['motivo_annullamento'],
        "nome": r['nome'], "indirizzo": r['indirizzo'], "citta": r['citta']
    } for r in ord_rows]

    cursor.execute('SELECT codice_ordine, email, prodotto, stelle, commento, immagine FROM recensioni ORDER BY id DESC')
    rec_rows = cursor.fetchall()
    tutte_recensioni = [{
        "codice_ordine": r['codice_ordine'], "email": r['email'], "prodotto": r['prodotto'],
        "stelle": r['stelle'], "commento": r['commento'], "immagine": r['immagine']
    } for r in rec_rows]
    
    cursor.close()
    conn.close()
    
    return render_template('index.html', 
                           user_email=user_email,
                           auth_error=auth_error,
                           active_tab=active_tab,
                           chat_utente=chat_utente, 
                           ordini_utente=ordini_utente,
                           tutte_recensioni=tutte_recensioni)

@app.route('/login-utente', methods=['POST'])
def login_utente():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    
    if not email or not password:
        session['auth_error'] = "Inserisci sia l'email che la password per accedere."
        session['active_tab'] = 'login'
        return redirect(url_for('home'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT password, user_id FROM utenti WHERE email = %s', (email,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if not row:
        session['auth_error'] = "Account non trovato. Registrati prima!"
        session['active_tab'] = 'login'
        return redirect(url_for('home'))
        
    if row['password'] != password:
        session['auth_error'] = "Password errata! Riprova."
        session['active_tab'] = 'login'
        return redirect(url_for('home'))
        
    session['user_email'] = email
    session['user_id'] = row['user_id']
    return redirect(url_for('home'))

@app.route('/registra-utente', methods=['POST'])
def registra_utente():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    password_confirm = request.form.get('password_confirm', '').strip()
    
    if not email or not password or not password_confirm:
        session['auth_error'] = "Compila tutti i campi inclusa la password."
        session['active_tab'] = 'register'
        return redirect(url_for('home'))
        
    if password != password_confirm:
        session['auth_error'] = "Le due password non coincidono!"
        session['active_tab'] = 'register'
        return redirect(url_for('home'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT email FROM utenti WHERE email = %s', (email,))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        session['auth_error'] = "Questa email è già registrata! Effettua il login."
        session['active_tab'] = 'register'
        return redirect(url_for('home'))
        
    user_id = session.get('user_id', str(uuid.uuid4()))
    cursor.execute('INSERT INTO utenti (email, password, user_id) VALUES (%s, %s, %s)', (email, password, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    session['user_email'] = email
    session['user_id'] = user_id
    return redirect(url_for('home'))

@app.route('/login-google', methods=['POST'])
def login_google():
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '').strip()
    
    if not email or not password:
        return jsonify({"status": "error", "message": "Email e password richieste."}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT password, user_id FROM utenti WHERE email = %s', (email,))
    row = cursor.fetchone()
    
    if row:
        if row['password'] != password:
            cursor.close()
            conn.close()
            return jsonify({"status": "error", "message": "Password errata per questo account!"}), 401
        user_id = row['user_id']
    else:
        user_id = session.get('user_id', str(uuid.uuid4()))
        cursor.execute('INSERT INTO utenti (email, password, user_id) VALUES (%s, %s, %s)', (email, password, user_id))
        conn.commit()
        
    cursor.close()
    conn.close()
    session['user_email'] = email
    session['user_id'] = user_id
    return jsonify({"status": "success"})

@app.route('/logout-utente')
def logout_utente():
    session.pop('user_email', None)
    session.pop('user_id', None)
    return redirect(url_for('home'))

@app.route('/invia', methods=['POST'])
def invia():
    uid = get_user_id()
    data = request.get_json() or {}
    testo = data.get('testo', '')
    immagine = data.get('immagine', '')
    
    if testo or immagine:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO chat (user_id, mittente, testo, immagine) VALUES (%s, %s, %s, %s)', (uid, 'cliente', testo, immagine))
        conn.commit()
        cursor.close()
        conn.close()
    return jsonify({"status": "success"})

@app.route('/api/chat-utente', methods=['GET'])
def api_chat_utente():
    uid = get_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT mittente, testo, immagine FROM chat WHERE user_id = %s', (uid,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{"mittente": r['mittente'], "testo": r['testo'], "immagine": r['immagine']} for r in rows])

@app.route('/api/ordini-utente', methods=['GET'])
def api_ordini_utente():
    uid = get_user_id()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, codice, prodotto, importo, metodo, stato, motivo_annullamento, nome, indirizzo, citta FROM ordini WHERE user_id = %s', (uid,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{
        "id": r['id'], "codice": r['codice'], "prodotto": r['prodotto'], "importo": r['importo'],
        "metodo": r['metodo'], "stato": r['stato'], "motivo_annullamento": r['motivo_annullamento'],
        "nome": r['nome'], "indirizzo": r['indirizzo'], "citta": r['citta']
    } for r in rows])

# ---- NUOVA ROTTA PAYPAL AUTOMATICA ----
@app.route('/registra-pagamento', methods=['POST'])
def registra_pagamento():
    if not get_current_user():
        return jsonify({"status": "error", "message": "Devi accedere per acquistare."}), 401
        
    uid = get_user_id()
    email = get_current_user()
    data = request.get_json() or {}
    
    paypal_order_id = data.get('paypal_order_id')
    prodotto = data.get('prodotto')
    importo = data.get('importo')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT valore FROM contatore WHERE id = 1')
    val = cursor.fetchone()['valore'] + 1
    cursor.execute('UPDATE contatore SET valore = %s WHERE id = 1', (val,))
    
    codice_ordine = f"#{val:04d}"
    ordine_id = str(uuid.uuid4())[:8]
    
    # Stato impostato direttamente a "Pagato - Inserisci Spedizione" in modo automatico
    cursor.execute('''
        INSERT INTO ordini (id, codice, user_id, email, prodotto, importo, metodo, stato, motivo_annullamento, nome, indirizzo, citta, paypal_order_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (ordine_id, codice_ordine, uid, email, prodotto, importo, 'PayPal (Automatico)', 'Pagato - Inserisci Spedizione', '', '', '', '', paypal_order_id))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({"status": "success", "ordine_id": ordine_id})

@app.route('/salva-spedizione/<ordine_id>', methods=['POST'])
def salva_spedizione(ordine_id):
    nome = request.form.get('nome')
    indirizzo = request.form.get('indirizzo')
    citta = request.form.get('citta')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE ordini SET nome = %s, indirizzo = %s, citta = %s, stato = %s WHERE id = %s', (nome, indirizzo, citta, 'In elaborazione', ordine_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    return redirect(url_for('home'))

@app.route('/elimina-ordine-cliente/<ordine_id>', methods=['POST'])
def elimina_ordine_cliente(ordine_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ordini WHERE id = %s AND (stato = %s OR stato = %s)', (ordine_id, 'Arrivato', 'Annullato'))
    conn.commit()
    cursor.close()
    conn.close()
    
    return redirect(url_for('home'))

@app.route('/invia-recensione/<ordine_id>', methods=['POST'])
def invia_recensione(ordine_id):
    email = get_current_user()
    if not email:
        return jsonify({"status": "error", "message": "Devi essere loggato."}), 401
        
    data = request.get_json() or {}
    stelle = int(data.get('stelle', 5))
    commento = data.get('commento', '').strip()
    immagine = data.get('immagine', '')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT codice, prodotto, stato FROM ordini WHERE id = %s', (ordine_id,))
    row = cursor.fetchone()
    if row and row['stato'] == 'Arrivato':
        codice_ordine = row['codice']
        prodotto = row['prodotto']
        
        cursor.execute('''
            INSERT INTO recensioni (ordine_id, codice_ordine, email, prodotto, stelle, commento, immagine)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (ordine_id, codice_ordine, email, prodotto, stelle, commento, immagine))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success"})
        
    cursor.close()
    conn.close()
    return jsonify({"status": "error", "message": "Ordine non valido o non ancora arrivato."}), 400

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('admin_logged_in'):
        return render_template('admin.html')
    
    errore = False
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return render_template('admin.html')
        else:
            errore = True
            
    return render_template('login.html', errore=errore)

@app.route('/logout-admin')
def logout_admin():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin'))

@app.route('/annulla-ordine/<ordine_id>', methods=['POST'])
def annulla_ordine(ordine_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    motivo = request.form.get('motivo', 'Nessun motivo specificato.')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE ordini SET stato = %s, motivo_annullamento = %s WHERE id = %s', ('Annullato', motivo, ordine_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/aggiorna-stato/<ordine_id>', methods=['POST'])
def aggiorna_stato(ordine_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    nuovo_stato = request.form.get('nuovo_stato')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE ordini SET stato = %s WHERE id = %s', (nuovo_stato, ordine_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/archivia-ordine/<ordine_id>', methods=['POST'])
def archivia_ordine(ordine_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE ordini SET stato = %s WHERE id = %s AND (stato = %s OR stato = %s)', ('Archiviato', ordine_id, 'Arrivato', 'Annullato'))
    conn.commit()
    cursor.close()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/elimina-recensione/<int:rec_id>', methods=['POST'])
def elimina_recensione(rec_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM recensioni WHERE id = %s', (rec_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/api/admin/dati', methods=['GET'])
def api_admin_dati():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error"}), 401
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, codice, user_id, email, prodotto, importo, metodo, stato, motivo_annullamento, nome, indirizzo, citta FROM ordini')
    rows = cursor.fetchall()
    
    tutti_ordini = []
    archivio_ordini = []
    
    for r in rows:
        ord_obj = {
            "id": r['id'], "codice": r['codice'], "user_id": r['user_id'], "email": r['email'],
            "prodotto": r['prodotto'], "importo": r['importo'], "metodo": r['metodo'], "stato": r['stato'],
            "motivo_annullamento": r['motivo_annullamento'], "nome": r['nome'], "indirizzo": r['indirizzo'], "citta": r['citta']
        }
        if r['stato'] == 'Archiviato':
            archivio_ordini.append(ord_obj)
        else:
            tutti_ordini.append(ord_obj)
            
    cursor.execute('SELECT user_id, mittente, testo, immagine FROM chat')
    chat_rows = cursor.fetchall()
    chat_per_utente = {}
    for cr in chat_rows:
        u_id = cr['user_id']
        if u_id not in chat_per_utente:
            chat_per_utente[u_id] = []
        chat_per_utente[u_id].append({"mittente": cr['mittente'], "testo": cr['testo'], "immagine": cr['immagine']})
        
    cursor.execute('SELECT email, password, user_id, data_creazione FROM utenti')
    user_rows = cursor.fetchall()
    lista_utenti = [{"email": ur['email'], "password": ur['password'], "user_id": ur['user_id'], "data": str(ur['data_creazione'])} for ur in user_rows]
    email_per_uid = {ur['user_id']: ur['email'] for ur in user_rows}

    cursor.execute('SELECT user_id, user_agent, ip_address, ultimo_accesso FROM visitatori ORDER BY ultimo_accesso DESC')
    visitatori_rows = cursor.fetchall()
    
    registered_uids = {ur['user_id'] for ur in user_rows}
    
    visitatori_non_registrati = []
    for vr in visitatori_rows:
        v_uid = vr['user_id']
        if v_uid not in registered_uids:
            visitatori_non_registrati.append({
                "user_id": v_uid,
                "user_agent": vr['user_agent'],
                "ip": vr['ip_address'],
                "ultimo_accesso": str(vr['ultimo_accesso'])
            })

    cursor.execute('SELECT id, ordine_id, codice_ordine, email, prodotto, stelle, commento, immagine FROM recensioni ORDER BY id DESC')
    rec_rows = cursor.fetchall()
    lista_recensioni = [{
        "id": r['id'], "ordine_id": r['ordine_id'], "codice_ordine": r['codice_ordine'], "email": r['email'],
        "prodotto": r['prodotto'], "stelle": r['stelle'], "commento": r['commento'], "immagine": r['immagine']
    } for r in rec_rows]
    
    cursor.close()
    conn.close()
    
    return jsonify({
        "tutti_ordini": tutti_ordini,
        "archivio_ordini": archivio_ordini,
        "chat_per_utente": chat_per_utente,
        "lista_utenti": lista_utenti,
        "visitatori_non_registrati": visitatori_non_registrati,
        "lista_recensioni": lista_recensioni,
        "email_per_uid": email_per_uid
    })

@app.route('/api/admin/chat/<user_id>', methods=['GET'])
def api_admin_get_chat(user_id):
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error"}), 401
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT mittente, testo, immagine FROM chat WHERE user_id = %s', (user_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify([{"mittente": r['mittente'], "testo": r['testo'], "immagine": r['immagine']} for r in rows])

@app.route('/api/admin/rispondi/<user_id>', methods=['POST'])
def api_admin_rispondi(user_id):
    if not session.get('admin_logged_in'):
        return jsonify({"status":

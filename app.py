from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import uuid
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "chiave_segreta_super_sicura_myclothes"

ADMIN_PASSWORD = "myclothesadmin!"
DB_NAME = "myclothes.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tabella Utenti
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS utenti (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            user_id TEXT NOT NULL,
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Tabella Chat
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            mittente TEXT NOT NULL,
            testo TEXT,
            immagine TEXT
        )
    ''')
    # Tabella Ordini
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
            citta TEXT
        )
    ''')
    # Tabella Recensioni
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recensioni (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    conn.close()

init_db()

def get_current_user():
    return session.get('user_email')

def get_user_id():
    if 'user_email' in session:
        email = session['user_email']
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM utenti WHERE email = ?', (email,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
            
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

@app.route('/')
def home():
    uid = get_user_id()
    user_email = get_current_user()
    
    auth_error = session.pop('auth_error', None)
    active_tab = session.pop('active_tab', 'login')
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Prendi chat utente
    cursor.execute('SELECT mittente, testo, immagine FROM chat WHERE user_id = ?', (uid,))
    chat_rows = cursor.fetchall()
    chat_utente = [{"mittente": r[0], "testo": r[1], "immagine": r[2]} for r in chat_rows]
    
    # Prendi ordini utente
    cursor.execute('SELECT id, codice, prodotto, importo, metodo, stato, motivo_annullamento, nome, indirizzo, citta FROM ordini WHERE user_id = ?', (uid,))
    ord_rows = cursor.fetchall()
    ordini_utente = [{
        "id": r[0], "codice": r[1], "prodotto": r[2], "importo": r[3],
        "metodo": r[4], "stato": r[5], "motivo_annullamento": r[6],
        "nome": r[7], "indirizzo": r[8], "citta": r[9]
    } for r in ord_rows]

    # Prendi tutte le recensioni per la homepage
    cursor.execute('SELECT codice_ordine, email, prodotto, stelle, commento, immagine FROM recensioni ORDER BY id DESC')
    rec_rows = cursor.fetchall()
    tutte_recensioni = [{
        "codice_ordine": r[0], "email": r[1], "prodotto": r[2],
        "stelle": r[3], "commento": r[4], "immagine": r[5]
    } for r in rec_rows]
    
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
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT password, user_id FROM utenti WHERE email = ?', (email,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        session['auth_error'] = "Account non trovato. Registrati prima!"
        session['active_tab'] = 'login'
        return redirect(url_for('home'))
        
    if row[0] != password:
        session['auth_error'] = "Password errata! Riprova."
        session['active_tab'] = 'login'
        return redirect(url_for('home'))
        
    session['user_email'] = email
    session['user_id'] = row[1]
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
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT email FROM utenti WHERE email = ?', (email,))
    if cursor.fetchone():
        conn.close()
        session['auth_error'] = "Questa email è già registrata! Effettua il login."
        session['active_tab'] = 'register'
        return redirect(url_for('home'))
        
    user_id = str(uuid.uuid4())
    cursor.execute('INSERT INTO utenti (email, password, user_id) VALUES (?, ?, ?)', (email, password, user_id))
    conn.commit()
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
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT password, user_id FROM utenti WHERE email = ?', (email,))
    row = cursor.fetchone()
    
    if row:
        if row[0] != password:
            conn.close()
            return jsonify({"status": "error", "message": "Password errata per questo account!"}), 401
        user_id = row[1]
    else:
        user_id = str(uuid.uuid4())
        cursor.execute('INSERT INTO utenti (email, password, user_id) VALUES (?, ?, ?)', (email, password, user_id))
        conn.commit()
        
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
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO chat (user_id, mittente, testo, immagine) VALUES (?, ?, ?, ?)', (uid, 'cliente', testo, immagine))
        conn.commit()
        conn.close()
    return jsonify({"status": "success"})

@app.route('/api/chat-utente', methods=['GET'])
def api_chat_utente():
    uid = get_user_id()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT mittente, testo, immagine FROM chat WHERE user_id = ?', (uid,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"mittente": r[0], "testo": r[1], "immagine": r[2]} for r in rows])

@app.route('/api/ordini-utente', methods=['GET'])
def api_ordini_utente():
    uid = get_user_id()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT id, codice, prodotto, importo, metodo, stato, motivo_annullamento, nome, indirizzo, citta FROM ordini WHERE user_id = ?', (uid,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{
        "id": r[0], "codice": r[1], "prodotto": r[2], "importo": r[3],
        "metodo": r[4], "stato": r[5], "motivo_annullamento": r[6],
        "nome": r[7], "indirizzo": r[8], "citta": r[9]
    } for r in rows])

@app.route('/registra-pagamento', methods=['POST'])
def registra_pagamento():
    if not get_current_user():
        return jsonify({"status": "error", "message": "Devi accedere per acquistare."}), 401
        
    uid = get_user_id()
    email = get_current_user()
    data = request.get_json() or {}
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT valore FROM contatore WHERE id = 1')
    val = cursor.fetchone()[0] + 1
    cursor.execute('UPDATE contatore SET valore = ? WHERE id = 1', (val,))
    
    codice_ordine = f"#{val:04d}"
    ordine_id = str(uuid.uuid4())[:8]
    
    cursor.execute('''
        INSERT INTO ordini (id, codice, user_id, email, prodotto, importo, metodo, stato, motivo_annullamento, nome, indirizzo, citta)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ordine_id, codice_ordine, uid, email, data.get('prodotto'), data.get('importo'), data.get('metodo'), 'In attesa di verifica pagamento', '', '', '', ''))
    
    conn.commit()
    conn.close()
    
    return jsonify({"status": "success"})

@app.route('/salva-spedizione/<ordine_id>', methods=['POST'])
def salva_spedizione(ordine_id):
    nome = request.form.get('nome')
    indirizzo = request.form.get('indirizzo')
    citta = request.form.get('citta')
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE ordini SET nome = ?, indirizzo = ?, citta = ?, stato = "In elaborazione" WHERE id = ?', (nome, indirizzo, citta, ordine_id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('home'))

@app.route('/elimina-ordine-cliente/<ordine_id>', methods=['POST'])
def elimina_ordine_cliente(ordine_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ordini WHERE id = ? AND (stato = "Arrivato" OR stato = "Annullato")', (ordine_id,))
    conn.commit()
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
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('SELECT codice, prodotto, stato FROM ordini WHERE id = ?', (ordine_id,))
    row = cursor.fetchone()
    if row and row[2] == 'Arrivato':
        codice_ordine = row[0]
        prodotto = row[1]
        
        cursor.execute('''
            INSERT INTO recensioni (ordine_id, codice_ordine, email, prodotto, stelle, commento, immagine)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (ordine_id, codice_ordine, email, prodotto, stelle, commento, immagine))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
        
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

@app.route('/conferma-pagamento/<ordine_id>', methods=['POST'])
def conferma_pagamento(ordine_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE ordini SET stato = "Pagamento Verificato - Inserisci Spedizione" WHERE id = ?', (ordine_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/annulla-ordine/<ordine_id>', methods=['POST'])
def annulla_ordine(ordine_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    motivo = request.form.get('motivo', 'Nessun motivo specificato.')
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE ordini SET stato = "Annullato", motivo_annullamento = ? WHERE id = ?', (motivo, ordine_id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/aggiorna-stato/<ordine_id>', methods=['POST'])
def aggiorna_stato(ordine_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    nuovo_stato = request.form.get('nuovo_stato')
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE ordini SET stato = ? WHERE id = ?', (nuovo_stato, ordine_id))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/archivia-ordine/<ordine_id>', methods=['POST'])
def archivia_ordine(ordine_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE ordini SET stato = "Archiviato" WHERE id = ? AND (stato = "Arrivato" OR stato = "Annullato")', (ordine_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/elimina-recensione/<int:rec_id>', methods=['POST'])
def elimina_recensione(rec_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM recensioni WHERE id = ?', (rec_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/api/admin/dati', methods=['GET'])
def api_admin_dati():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error"}), 401
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Prendi tutti gli Ordini
    cursor.execute('SELECT id, codice, user_id, email, prodotto, importo, metodo, stato, motivo_annullamento, nome, indirizzo, citta FROM ordini')
    rows = cursor.fetchall()
    
    tutti_ordini = []
    archivio_ordini = []
    
    for r in rows:
        ord_obj = {
            "id": r[0], "codice": r[1], "user_id": r[2], "email": r[3],
            "prodotto": r[4], "importo": r[5], "metodo": r[6], "stato": r[7],
            "motivo_annullamento": r[8], "nome": r[9], "indirizzo": r[10], "citta": r[11]
        }
        if r[7] == 'Archiviato':
            archivio_ordini.append(ord_obj)
        else:
            tutti_ordini.append(ord_obj)
            
    # Prendi tutte le Chat
    cursor.execute('SELECT user_id, mittente, testo, immagine FROM chat')
    chat_rows = cursor.fetchall()
    chat_per_utente = {}
    for cr in chat_rows:
        u_id = cr[0]
        if u_id not in chat_per_utente:
            chat_per_utente[u_id] = []
        chat_per_utente[u_id].append({"mittente": cr[1], "testo": cr[2], "immagine": cr[3]})
        
    # Prendi tutti gli Utenti Registrati
    cursor.execute('SELECT email, password, user_id FROM utenti')
    user_rows = cursor.fetchall()
    lista_utenti = [{"email": ur[0], "password": ur[1], "user_id": ur[2]} for ur in user_rows]
    email_per_uid = {ur[2]: ur[0] for ur in user_rows}

    # Prendi tutte le Recensioni
    cursor.execute('SELECT id, ordine_id, codice_ordine, email, prodotto, stelle, commento, immagine FROM recensioni ORDER BY id DESC')
    rec_rows = cursor.fetchall()
    lista_recensioni = [{
        "id": r[0], "ordine_id": r[1], "codice_ordine": r[2], "email": r[3],
        "prodotto": r[4], "stelle": r[5], "commento": r[6], "immagine": r[7]
    } for r in rec_rows]
    
    conn.close()
    
    return jsonify({
        "tutti_ordini": tutti_ordini,
        "archivio_ordini": archivio_ordini,
        "chat_per_utente": chat_per_utente,
        "lista_utenti": lista_utenti,
        "lista_recensioni": lista_recensioni,
        "email_per_uid": email_per_uid
    })

@app.route('/api/admin/chat/<user_id>', methods=['GET'])
def api_admin_get_chat(user_id):
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error"}), 401
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT mittente, testo, immagine FROM chat WHERE user_id = ?', (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"mittente": r[0], "testo": r[1], "immagine": r[2]} for r in rows])

@app.route('/api/admin/rispondi/<user_id>', methods=['POST'])
def api_admin_rispondi(user_id):
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error"}), 401
        
    data = request.get_json() or {}
    testo_risposta = data.get('risposta', '').strip()
    
    if testo_risposta:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO chat (user_id, mittente, testo, immagine) VALUES (?, ?, ?, ?)', (user_id, 'admin', testo_risposta, ''))
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    return jsonify({"status": "empty"}), 400

if __name__ == '__main__':
    app.run(debug=True)

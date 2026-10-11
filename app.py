from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import uuid

app = Flask(__name__)
app.secret_key = "chiave_segreta_super_sicura_myclothes"

ADMIN_PASSWORD = "GhiaccioBlu6767"

UTENTI = {}           # email -> {'password': str, 'user_id': str}
CHAT_PER_UTENTE = {}  # user_id -> lista messaggi unita
ORDINI_PER_UTENTE = {}# user_id -> lista ordini attivi
ARCHIVIO_ORDINI = []  # Lista globale ordini archiviati (admin)
TUTTI_GLI_ORDINI = [] # Lista globale admin

CONTATORE_ORDINI = 0

def get_current_user():
    return session.get('user_email')

def get_user_id():
    if 'user_email' in session:
        email = session['user_email']
        if email in UTENTI:
            return UTENTI[email]['user_id']
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    return session['user_id']

@app.route('/')
def home():
    uid = get_user_id()
    user_email = get_current_user()
    
    auth_error = session.pop('auth_error', None)
    active_tab = session.pop('active_tab', 'login')
    
    return render_template('index.html', 
                           user_email=user_email,
                           auth_error=auth_error,
                           active_tab=active_tab,
                           chat_utente=CHAT_PER_UTENTE.get(uid, []), 
                           ordini_utente=ORDINI_PER_UTENTE.get(uid, []))

@app.route('/login-utente', methods=['POST'])
def login_utente():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    
    if not email or not password:
        session['auth_error'] = "Inserisci sia l'email che la password per accedere."
        session['active_tab'] = 'login'
        return redirect(url_for('home'))
        
    if email not in UTENTI:
        session['auth_error'] = "Account non trovato. Registrati prima!"
        session['active_tab'] = 'login'
        return redirect(url_for('home'))
        
    if UTENTI[email]['password'] != password:
        session['auth_error'] = "Password errata! Riprova."
        session['active_tab'] = 'login'
        return redirect(url_for('home'))
        
    session['user_email'] = email
    session['user_id'] = UTENTI[email]['user_id']
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
        
    if email in UTENTI:
        session['auth_error'] = "Questa email è già registrata! Effettua il login."
        session['active_tab'] = 'register'
        return redirect(url_for('home'))
        
    if password != password_confirm:
        session['auth_error'] = "Le due password non coincidono!"
        session['active_tab'] = 'register'
        return redirect(url_for('home'))
        
    user_id = str(uuid.uuid4())
    UTENTI[email] = {'password': password, 'user_id': user_id}
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
        
    if email in UTENTI:
        if UTENTI[email]['password'] != password:
            return jsonify({"status": "error", "message": "Password errata per questo account!"}), 401
        user_id = UTENTI[email]['user_id']
    else:
        user_id = str(uuid.uuid4())
        UTENTI[email] = {'password': password, 'user_id': user_id}
        
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
    
    if uid not in CHAT_PER_UTENTE:
        CHAT_PER_UTENTE[uid] = []
        
    if testo or immagine:
        CHAT_PER_UTENTE[uid].append({
            "mittente": "cliente",
            "testo": testo,
            "immagine": immagine
        })
    return jsonify({"status": "success"})

@app.route('/api/chat-utente', methods=['GET'])
def api_chat_utente():
    uid = get_user_id()
    return jsonify(CHAT_PER_UTENTE.get(uid, []))

@app.route('/api/ordini-utente', methods=['GET'])
def api_ordini_utente():
    uid = get_user_id()
    return jsonify(ORDINI_PER_UTENTE.get(uid, []))

@app.route('/registra-pagamento', methods=['POST'])
def registra_pagamento():
    global CONTATORE_ORDINI
    if not get_current_user():
        return jsonify({"status": "error", "message": "Devi accedere per acquistare."}), 401
        
    uid = get_user_id()
    data = request.get_json() or {}
    
    CONTATORE_ORDINI += 1
    codice_ordine = f"#{CONTATORE_ORDINI:04d}"
    ordine_id = str(uuid.uuid4())[:8]
    
    nuovo_ordine = {
        "id": ordine_id,
        "codice": codice_ordine,
        "user_id": uid,
        "email": get_current_user(),
        "prodotto": data.get('prodotto'),
        "importo": data.get('importo'),
        "metodo": data.get('metodo'),
        "stato": "In attesa di verifica pagamento",
        "motivo_annullamento": "",
        "nome": "",
        "indirizzo": "",
        "citta": ""
    }
    
    if uid not in ORDINI_PER_UTENTE:
        ORDINI_PER_UTENTE[uid] = []
    
    ORDINI_PER_UTENTE[uid].append(nuovo_ordine)
    TUTTI_GLI_ORDINI.append(nuovo_ordine)
    
    return jsonify({"status": "success"})

@app.route('/salva-spedizione/<ordine_id>', methods=['POST'])
def salva_spedizione(ordine_id):
    uid = get_user_id()
    nome = request.form.get('nome')
    indirizzo = request.form.get('indirizzo')
    citta = request.form.get('citta')
    
    for ord in TUTTI_GLI_ORDINI:
        if ord['id'] == ordine_id:
            ord['nome'] = nome
            ord['indirizzo'] = indirizzo
            ord['citta'] = citta
            ord['stato'] = "In elaborazione"
            
    if uid in ORDINI_PER_UTENTE:
        for o_cli in ORDINI_PER_UTENTE[uid]:
            if o_cli['id'] == ordine_id:
                o_cli['nome'] = nome
                o_cli['indirizzo'] = indirizzo
                o_cli['citta'] = citta
                o_cli['stato'] = "In elaborazione"
                
    return redirect(url_for('home'))

@app.route('/elimina-ordine-cliente/<ordine_id>', methods=['POST'])
def elimina_ordine_cliente(ordine_id):
    uid = get_user_id()
    if uid in ORDINI_PER_UTENTE:
        for o in ORDINI_PER_UTENTE[uid]:
            if o['id'] == ordine_id and (o['stato'] == 'Arrivato' or o['stato'] == 'Annullato'):
                ORDINI_PER_UTENTE[uid].remove(o)
                break
    return redirect(url_for('home'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('admin_logged_in'):
        email_per_uid = {u_data['user_id']: email for email, u_data in UTENTI.items()}
        return render_template('admin.html', 
                               tutti_ordini=TUTTI_GLI_ORDINI, 
                               archivio_ordini=ARCHIVIO_ORDINI,
                               chat_per_utente=CHAT_PER_UTENTE,
                               email_per_uid=email_per_uid)
    
    errore = False
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            email_per_uid = {u_data['user_id']: email for email, u_data in UTENTI.items()}
            return render_template('admin.html', 
                                   tutti_ordini=TUTTI_GLI_ORDINI, 
                                   archivio_ordini=ARCHIVIO_ORDINI,
                                   chat_per_utente=CHAT_PER_UTENTE,
                                   email_per_uid=email_per_uid)
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
        
    for ord in TUTTI_GLI_ORDINI:
        if ord['id'] == ordine_id:
            ord['stato'] = "Pagamento Verificato - Inserisci Spedizione"
            u_id = ord['user_id']
            if u_id in ORDINI_PER_UTENTE:
                for o_cli in ORDINI_PER_UTENTE[u_id]:
                    if o_cli['id'] == ordine_id:
                        o_cli['stato'] = "Pagamento Verificato - Inserisci Spedizione"
                        
    return redirect(url_for('admin'))

@app.route('/annulla-ordine/<ordine_id>', methods=['POST'])
def annulla_ordine(ordine_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    motivo = request.form.get('motivo', 'Nessun motivo specificato.')
    
    for ord in TUTTI_GLI_ORDINI:
        if ord['id'] == ordine_id:
            ord['stato'] = "Annullato"
            ord['motivo_annullamento'] = motivo
            u_id = ord['user_id']
            if u_id in ORDINI_PER_UTENTE:
                for o_cli in ORDINI_PER_UTENTE[u_id]:
                    if o_cli['id'] == ordine_id:
                        o_cli['stato'] = "Annullato"
                        o_cli['motivo_annullamento'] = motivo
                        
    return redirect(url_for('admin'))

@app.route('/aggiorna-stato/<ordine_id>', methods=['POST'])
def aggiorna_stato(ordine_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    nuovo_stato = request.form.get('nuovo_stato')
    for ord in TUTTI_GLI_ORDINI:
        if ord['id'] == ordine_id:
            ord['stato'] = nuovo_stato
            u_id = ord['user_id']
            if u_id in ORDINI_PER_UTENTE:
                for o_cli in ORDINI_PER_UTENTE[u_id]:
                    if o_cli['id'] == ordine_id:
                        o_cli['stato'] = nuovo_stato
                        
    return redirect(url_for('admin'))

@app.route('/archivia-ordine/<ordine_id>', methods=['POST'])
def archivia_ordine(ordine_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
        
    for ord in TUTTI_GLI_ORDINI:
        if ord['id'] == ordine_id and (ord['stato'] == 'Arrivato' or ord['stato'] == 'Annullato'):
            ARCHIVIO_ORDINI.append(ord)
            TUTTI_GLI_ORDINI.remove(ord)
            break
            
    return redirect(url_for('admin'))

# API AJAX per aggiornamento in tempo reale del pannello admin
@app.route('/api/admin/dati', methods=['GET'])
def api_admin_dati():
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error"}), 401
    email_per_uid = {u_data['user_id']: email for email, u_data in UTENTI.items()}
    return jsonify({
        "tutti_ordini": TUTTI_GLI_ORDINI,
        "archivio_ordini": ARCHIVIO_ORDINI,
        "chat_per_utente": CHAT_PER_UTENTE,
        "email_per_uid": email_per_uid
    })

@app.route('/api/admin/chat/<user_id>', methods=['GET'])
def api_admin_get_chat(user_id):
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error"}), 401
    return jsonify(CHAT_PER_UTENTE.get(user_id, []))

@app.route('/api/admin/rispondi/<user_id>', methods=['POST'])
def api_admin_rispondi(user_id):
    if not session.get('admin_logged_in'):
        return jsonify({"status": "error"}), 401
        
    data = request.get_json() or {}
    testo_risposta = data.get('risposta', '').strip()
    
    if testo_risposta:
        if user_id not in CHAT_PER_UTENTE:
            CHAT_PER_UTENTE[user_id] = []
        CHAT_PER_UTENTE[user_id].append({
            "mittente": "admin",
            "testo": testo_risposta,
            "immagine": ""
        })
        return jsonify({"status": "success"})
    return jsonify({"status": "empty"}), 400

if __name__ == '__main__':
    app.run(debug=True)

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    session,
    redirect,
    url_for,
)
import uuid
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "chiave_segreta_super_sicura_myclothes"

ADMIN_PASSWORD = "myclothesadmin!"
DB_NAME = "myclothes.db"

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
  import psycopg2
  import psycopg2.pool

  db_pool = psycopg2.pool.SimpleConnectionPool(
      1, 10, DATABASE_URL, sslmode="require"
  )


def get_db_connection():
  if DATABASE_URL:
    return db_pool.getconn()
  else:
    return sqlite3.connect(DB_NAME)


def release_db_connection(conn):
  if DATABASE_URL:
    try:
      db_pool.putconn(conn)
    except Exception:
      pass
  else:
    conn.close()


def execute_query(cursor, query, params=None):
  if params is None:
    params = ()
  if DATABASE_URL:
    formatted_query = query.replace("?", "%s")
    cursor.execute(formatted_query, params)
  else:
    cursor.execute(query, params)
  return cursor


def init_db():
  conn = get_db_connection()
  cursor = conn.cursor()

  tables = [
      (
          "utenti",
          """
        CREATE TABLE IF NOT EXISTS utenti (
            email TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            user_id TEXT NOT NULL,
            data_creazione TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
      ),
      (
          "visitatori",
          """
        CREATE TABLE IF NOT EXISTS visitatori (
            user_id TEXT PRIMARY KEY,
            user_agent TEXT,
            ip_address TEXT,
            ultimo_accesso TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """,
      ),
      (
          "chat",
          (
              """
        CREATE TABLE IF NOT EXISTS chat (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            mittente TEXT NOT NULL,
            testo TEXT,
            immagine TEXT
        )
    """
              if DATABASE_URL
              else """
        CREATE TABLE IF NOT EXISTS chat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            mittente TEXT NOT NULL,
            testo TEXT,
            immagine TEXT
        )
    """
          ),
      ),
      (
          "ordini",
          """
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
    """,
      ),
      (
          "recensioni",
          (
              """
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
    """
              if DATABASE_URL
              else """
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
    """
          ),
      ),
      (
          "contatore",
          """
        CREATE TABLE IF NOT EXISTS contatore (
            id INTEGER PRIMARY KEY,
            valore INTEGER NOT NULL
        )
    """,
      ),
  ]

  for name, sql in tables:
    cursor.execute(sql)

  cursor.execute("SELECT valore FROM contatore WHERE id = 1")
  if not cursor.fetchone():
    cursor.execute("INSERT INTO contatore (id, valore) VALUES (1, 0)")

  conn.commit()
  cursor.close()
  release_db_connection(conn)


init_db()


def get_current_user():
  return session.get("user_email")


def get_user_id():
  if "user_email" in session:
    email = session["user_email"]
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_query(cursor, "SELECT user_id FROM utenti WHERE email = ?", (email,))
    row = cursor.fetchone()
    cursor.close()
    release_db_connection(conn)
    if row:
      uid = row[0]
      registra_visitatore(uid)
      return uid

  if "user_id" not in session:
    session["user_id"] = str(uuid.uuid4())

  uid = session["user_id"]
  registra_visitatore(uid)
  return uid


def registra_visitatore(uid):
  user_agent = request.headers.get("User-Agent", "Dispositivo sconosciuto")
  ip_address = request.remote_addr or "IP non disponibile"

  conn = get_db_connection()
  cursor = conn.cursor()
  try:
    execute_query(
        cursor,
        """
            INSERT INTO visitatori (user_id, user_agent, ip_address, ultimo_accesso)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET 
            ultimo_accesso = CURRENT_TIMESTAMP,
            user_agent = excluded.user_agent,
            ip_address = excluded.ip_address
        """,
        (uid, user_agent, ip_address),
    )
    conn.commit()
  except Exception:
    conn.rollback()
  finally:
    cursor.close()
    release_db_connection(conn)


@app.route("/")
def home():
  uid = get_user_id()
  user_email = get_current_user()

  auth_error = session.pop("auth_error", None)
  active_tab = session.pop("active_tab", "login")

  conn = get_db_connection()
  cursor = conn.cursor()

  execute_query(
      cursor,
      "SELECT mittente, testo, immagine FROM chat WHERE user_id = ?",
      (uid,),
  )
  chat_utente = [
      {"mittente": r[0], "testo": r[1], "immagine": r[2]}
      for r in cursor.fetchall()
  ]

  execute_query(
      cursor,
      (
          "SELECT id, codice, prodotto, importo, metodo, stato,"
          " motivo_annullamento, nome, indirizzo, citta FROM ordini WHERE"
          " user_id = ?"
      ),
      (uid,),
  )
  ordini_utente = [
      {
          "id": r[0],
          "codice": r[1],
          "prodotto": r[2],
          "importo": r[3],
          "metodo": r[4],
          "stato": r[5],
          "motivo_annullamento": r[6],
          "nome": r[7],
          "indirizzo": r[8],
          "citta": r[9],
      }
      for r in cursor.fetchall()
  ]

  execute_query(
      cursor,
      (
          "SELECT codice_ordine, email, prodotto, stelle, commento, immagine"
          " FROM recensioni ORDER BY id DESC"
      ),
  )
  tutte_recensioni = [
      {
          "codice_ordine": r[0],
          "email": r[1],
          "prodotto": r[2],
          "stelle": r[3],
          "commento": r[4],
          "immagine": r[5],
      }
      for r in cursor.fetchall()
  ]

  cursor.close()
  release_db_connection(conn)

  return render_template(
      "index.html",
      user_email=user_email,
      auth_error=auth_error,
      active_tab=active_tab,
      chat_utente=chat_utente,
      ordini_utente=ordini_utente,
      tutte_recensioni=tutte_recensioni,
  )


@app.route("/login-utente", methods=["POST"])
def login_utente():
  email = request.form.get("email", "").strip().lower()
  password = request.form.get("password", "").strip()

  if not email or not password:
    session["auth_error"] = (
        "Inserisci sia l'email che la password per accedere."
    )
    session["active_tab"] = "login"
    return redirect(url_for("home"))

  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor, "SELECT password, user_id FROM utenti WHERE email = ?", (email,)
  )
  row = cursor.fetchone()
  cursor.close()
  release_db_connection(conn)

  if not row:
    session["auth_error"] = "Account non trovato. Registrati prima!"
    session["active_tab"] = "login"
    return redirect(url_for("home"))

  if row[0] != password:
    session["auth_error"] = "Password errata! Riprova."
    session["active_tab"] = "login"
    return redirect(url_for("home"))

  session["user_email"] = email
  session["user_id"] = row[1]
  return redirect(url_for("home"))


@app.route("/registra-utente", methods=["POST"])
def registra_utente():
  email = request.form.get("email", "").strip().lower()
  password = request.form.get("password", "").strip()
  password_confirm = request.form.get("password_confirm", "").strip()

  if not email or not password or not password_confirm:
    session["auth_error"] = "Compila tutti i campi inclusa la password."
    session["active_tab"] = "register"
    return redirect(url_for("home"))

  if password != password_confirm:
    session["auth_error"] = "Le due password non coincidono!"
    session["active_tab"] = "register"
    return redirect(url_for("home"))

  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(cursor, "SELECT email FROM utenti WHERE email = ?", (email,))
  if cursor.fetchone():
    cursor.close()
    release_db_connection(conn)
    session["auth_error"] = "Questa email è già registrata! Effettua il login."
    session["active_tab"] = "register"
    return redirect(url_for("home"))

  user_id = session.get("user_id", str(uuid.uuid4()))
  execute_query(
      cursor,
      "INSERT INTO utenti (email, password, user_id) VALUES (?, ?, ?)",
      (email, password, user_id),
  )
  conn.commit()
  cursor.close()
  release_db_connection(conn)

  session["user_email"] = email
  session["user_id"] = user_id
  return redirect(url_for("home"))


@app.route("/login-google", methods=["POST"])
def login_google():
  data = request.get_json() or {}
  email = data.get("email", "").strip().lower()
  password = data.get("password", "").strip()

  if not email or not password:
    return (
        jsonify(
            {"status": "error", "message": "Email e password richieste."}
        ),
        400,
    )

  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor, "SELECT password, user_id FROM utenti WHERE email = ?", (email,)
  )
  row = cursor.fetchone()

  if row:
    if row[0] != password:
      cursor.close()
      release_db_connection(conn)
      return (
          jsonify({
              "status": "error",
              "message": "Password errata per questo account!",
          }),
          401,
      )
    user_id = row[1]
  else:
    user_id = session.get("user_id", str(uuid.uuid4()))
    execute_query(
        cursor,
        "INSERT INTO utenti (email, password, user_id) VALUES (?, ?, ?)",
        (email, password, user_id),
    )
    conn.commit()

  cursor.close()
  release_db_connection(conn)
  session["user_email"] = email
  session["user_id"] = user_id
  return jsonify({"status": "success"})


@app.route("/logout-utente")
def logout_utente():
  session.pop("user_email", None)
  session.pop("user_id", None)
  return redirect(url_for("home"))


@app.route("/invia", methods=["POST"])
def invia():
  uid = get_user_id()
  data = request.get_json() or {}
  testo = data.get("testo", "")
  immagine = data.get("immagine", "")

  if testo or immagine:
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_query(
        cursor,
        (
            "INSERT INTO chat (user_id, mittente, testo, immagine) VALUES (?,"
            " ?, ?, ?)"
        ),
        (uid, "cliente", testo, immagine),
    )
    conn.commit()
    cursor.close()
    release_db_connection(conn)
  return jsonify({"status": "success"})


@app.route("/api/chat-utente", methods=["GET"])
def api_chat_utente():
  uid = get_user_id()
  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      "SELECT mittente, testo, immagine FROM chat WHERE user_id = ?",
      (uid,),
  )
  rows = cursor.fetchall()
  cursor.close()
  release_db_connection(conn)
  return jsonify(
      [{"mittente": r[0], "testo": r[1], "immagine": r[2]} for r in rows]
  )


@app.route("/api/ordini-utente", methods=["GET"])
def api_ordini_utente():
  uid = get_user_id()
  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      (
          "SELECT id, codice, prodotto, importo, metodo, stato,"
          " motivo_annullamento, nome, indirizzo, citta FROM ordini WHERE"
          " user_id = ?"
      ),
      (uid,),
  )
  rows = cursor.fetchall()
  cursor.close()
  release_db_connection(conn)
  return jsonify([
      {
          "id": r[0],
          "codice": r[1],
          "prodotto": r[2],
          "importo": r[3],
          "metodo": r[4],
          "stato": r[5],
          "motivo_annullamento": r[6],
          "nome": r[7],
          "indirizzo": r[8],
          "citta": r[9],
      }
      for r in rows
  ])


@app.route("/registra-pagamento", methods=["POST"])
def registra_pagamento():
  if not get_current_user():
    return (
        jsonify(
            {"status": "error", "message": "Devi accedere per acquistare."}
        ),
        401,
    )

  uid = get_user_id()
  email = get_current_user()
  data = request.get_json() or {}

  conn = get_db_connection()
  cursor = conn.cursor()

  execute_query(cursor, "SELECT valore FROM contatore WHERE id = 1")
  val = cursor.fetchone()[0] + 1
  execute_query(cursor, "UPDATE contatore SET valore = ? WHERE id = 1", (val,))

  codice_ordine = f"#{val:04d}"
  ordine_id = str(uuid.uuid4())[:8]

  execute_query(
      cursor,
      """
        INSERT INTO ordini (id, codice, user_id, email, prodotto, importo, metodo, stato, motivo_annullamento, nome, indirizzo, citta)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
      (
          ordine_id,
          codice_ordine,
          uid,
          email,
          data.get("prodotto"),
          data.get("importo"),
          data.get("metodo"),
          "In attesa di verifica pagamento",
          "",
          "",
          "",
          "",
      ),
  )

  conn.commit()
  cursor.close()
  release_db_connection(conn)

  return jsonify({"status": "success"})


@app.route("/salva-spedizione/<ordine_id>", methods=["POST"])
def salva_spedizione(ordine_id):
  nome = request.form.get("nome")
  indirizzo = request.form.get("indirizzo")
  citta = request.form.get("citta")

  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      (
          "UPDATE ordini SET nome = ?, indirizzo = ?, citta = ?, stato = 'In"
          " elaborazione' WHERE id = ?"
      ),
      (nome, indirizzo, citta, ordine_id),
  )
  conn.commit()
  cursor.close()
  release_db_connection(conn)

  return redirect(url_for("home"))


@app.route("/elimina-ordine-cliente/<ordine_id>", methods=["POST"])
def elimina_ordine_cliente(ordine_id):
  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      (
          "DELETE FROM ordini WHERE id = ? AND (stato = 'Arrivato' OR stato ="
          " 'Annullato')"
      ),
      (ordine_id,),
  )
  conn.commit()
  cursor.close()
  release_db_connection(conn)

  return redirect(url_for("home"))


@app.route("/invia-recensione/<ordine_id>", methods=["POST"])
def invia_recensione(ordine_id):
  email = get_current_user()
  if not email:
    return jsonify({"status": "error", "message": "Devi essere loggato."}), 401

  data = request.get_json() or {}
  stelle = int(data.get("stelle", 5))
  commento = data.get("commento", "").strip()
  immagine = data.get("immagine", "")

  conn = get_db_connection()
  cursor = conn.cursor()

  execute_query(
      cursor,
      "SELECT codice, prodotto, stato FROM ordini WHERE id = ?",
      (ordine_id,),
  )
  row = cursor.fetchone()
  if row and row[2] == "Arrivato":
    codice_ordine = row[0]
    prodotto = row[1]

    execute_query(
        cursor,
        """
            INSERT INTO recensioni (ordine_id, codice_ordine, email, prodotto, stelle, commento, immagine)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (ordine_id, codice_ordine, email, prodotto, stelle, commento, immagine),
    )
    conn.commit()
    cursor.close()
    release_db_connection(conn)
    return jsonify({"status": "success"})

  cursor.close()
  release_db_connection(conn)
  return (
      jsonify({
          "status": "error",
          "message": "Ordine non valido o non ancora arrivato.",
      }),
      400,
  )


@app.route("/admin", methods=["GET", "POST"])
def admin():
  if session.get("admin_logged_in"):
    return render_template("admin.html")

  errore = False
  if request.method == "POST":
    if request.form.get("password") == ADMIN_PASSWORD:
      session["admin_logged_in"] = True
      return render_template("admin.html")
    else:
      errore = True

  return render_template("login.html", errore=errore)


@app.route("/logout-admin")
def logout_admin():
  session.pop("admin_logged_in", None)
  return redirect(url_for("admin"))


@app.route("/conferma-pagamento/<ordine_id>", methods=["POST"])
def conferma_pagamento(ordine_id):
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin"))

  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      (
          "UPDATE ordini SET stato = 'Pagamento Verificato - Inserisci"
          " Spedizione' WHERE id = ?"
      ),
      (ordine_id,),
  )
  conn.commit()
  cursor.close()
  release_db_connection(conn)

  return redirect(url_for("admin"))


@app.route("/annulla-ordine/<ordine_id>", methods=["POST"])
def annulla_ordine(ordine_id):
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin"))

  motivo = request.form.get("motivo", "Nessun motivo specificato.")
  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      (
          "UPDATE ordini SET stato = 'Annullato', motivo_annullamento = ? WHERE"
          " id = ?"
      ),
      (motivo, ordine_id),
  )
  conn.commit()
  cursor.close()
  release_db_connection(conn)

  return redirect(url_for("admin"))


@app.route("/aggiorna-stato/<ordine_id>", methods=["POST"])
def aggiorna_stato(ordine_id):
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin"))

  nuovo_stato = request.form.get("nuovo_stato")
  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      "UPDATE ordini SET stato = ? WHERE id = ?",
      (nuovo_stato, ordine_id),
  )
  conn.commit()
  cursor.close()
  release_db_connection(conn)

  return redirect(url_for("admin"))


@app.route("/archivia-ordine/<ordine_id>", methods=["POST"])
def archivia_ordine(ordine_id):
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin"))

  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      (
          "UPDATE ordini SET stato = 'Archiviato' WHERE id = ? AND (stato ="
          " 'Arrivato' OR stato = 'Annullato')"
      ),
      (ordine_id,),
  )
  conn.commit()
  cursor.close()
  release_db_connection(conn)

  return redirect(url_for("admin"))


@app.route("/elimina-recensione/<int:rec_id>", methods=["POST"])
def elimina_recensione(rec_id):
  if not session.get("admin_logged_in"):
    return redirect(url_for("admin"))

  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(cursor, "DELETE FROM recensioni WHERE id = ?", (rec_id,))
  conn.commit()
  cursor.close()
  release_db_connection(conn)

  return redirect(url_for("admin"))


@app.route("/api/admin/dati", methods=["GET"])
def api_admin_dati():
  if not session.get("admin_logged_in"):
    return jsonify({"status": "error"}), 401

  conn = get_db_connection()
  cursor = conn.cursor()

  execute_query(
      cursor,
      (
          "SELECT id, codice, user_id, email, prodotto, importo, metodo, stato,"
          " motivo_annullamento, nome, indirizzo, citta FROM ordini"
      ),
  )
  rows = cursor.fetchall()

  tutti_ordini = []
  archivio_ordini = []
  for r in rows:
    ord_obj = {
        "id": r[0],
        "codice": r[1],
        "user_id": r[2],
        "email": r[3],
        "prodotto": r[4],
        "importo": r[5],
        "metodo": r[6],
        "stato": r[7],
        "motivo_annullamento": r[8],
        "nome": r[9],
        "indirizzo": r[10],
        "citta": r[11],
    }
    if r[7] == "Archiviato":
      archivio_ordini.append(ord_obj)
    else:
      tutti_ordini.append(ord_obj)

  execute_query(cursor, "SELECT user_id, mittente, testo, immagine FROM chat")
  chat_rows = cursor.fetchall()
  chat_per_utente = {}
  for cr in chat_rows:
    u_id = cr[0]
    if u_id not in chat_per_utente:
      chat_per_utente[u_id] = []
    chat_per_utente[u_id].append(
        {"mittente": cr[1], "testo": cr[2], "immagine": cr[3]}
    )

  execute_query(
      cursor, "SELECT email, password, user_id, data_creazione FROM utenti"
  )
  user_rows = cursor.fetchall()
  lista_utenti = [
      {
          "email": ur[0],
          "password": ur[1],
          "user_id": ur[2],
          "data": str(ur[3]),
      }
      for ur in user_rows
  ]
  email_per_uid = {ur[2]: ur[0] for ur in user_rows}

  execute_query(
      cursor,
      (
          "SELECT user_id, user_agent, ip_address, ultimo_accesso FROM"
          " visitatori ORDER BY ultimo_accesso DESC"
      ),
  )
  visitatori_rows = cursor.fetchall()
  registered_uids = {ur[2] for ur in user_rows}

  visitatori_non_registrati = []
  for vr in visitatori_rows:
    v_uid = vr[0]
    if v_uid not in registered_uids:
      visitatori_non_registrati.append({
          "user_id": v_uid,
          "user_agent": vr[1],
          "ip": vr[2],
          "ultimo_accesso": str(vr[3]),
      })

  execute_query(
      cursor,
      (
          "SELECT id, ordine_id, codice_ordine, email, prodotto, stelle,"
          " commento, immagine FROM recensioni ORDER BY id DESC"
      ),
  )
  rec_rows = cursor.fetchall()
  lista_recensioni = [
      {
          "id": r[0],
          "ordine_id": r[1],
          "codice_ordine": r[2],
          "email": r[3],
          "prodotto": r[4],
          "stelle": r[5],
          "commento": r[6],
          "immagine": r[7],
      }
      for r in rec_rows
  ]

  cursor.close()
  release_db_connection(conn)

  return jsonify({
      "tutti_ordini": tutti_ordini,
      "archivio_ordini": archivio_ordini,
      "chat_per_utente": chat_per_utente,
      "lista_utenti": lista_utenti,
      "visitatori_non_registrati": visitatori_non_registrati,
      "lista_recensioni": lista_recensioni,
      "email_per_uid": email_per_uid,
  })


@app.route("/api/admin/chat/<user_id>", methods=["GET"])
def api_admin_get_chat(user_id):
  if not session.get("admin_logged_in"):
    return jsonify({"status": "error"}), 401
  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      "SELECT mittente, testo, immagine FROM chat WHERE user_id = ?",
      (user_id,),
  )
  rows = cursor.fetchall()
  cursor.close()
  release_db_connection(conn)
  return jsonify(
      [{"mittente": r[0], "testo": r[1], "immagine": r[2]} for r in rows]
  )


@app.route("/api/admin/rispondi/<user_id>", methods=["POST"])
def api_admin_rispondi(user_id):
  if not session.get("admin_logged_in"):
    return jsonify({"status": "error"}), 401

  data = request.get_json() or {}
  testo_risposta = data.get("risposta", "").strip()

  if testo_risposta:
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_query(
        cursor,
        (
            "INSERT INTO chat (user_id, mittente, testo, immagine) VALUES (?,"
            " ?, ?, ?)"
        ),
        (user_id, "admin", testo_risposta, ""),
    )
    conn.commit()
    cursor.close()
    release_db_connection(conn)
    return jsonify({"status": "success"})
  return jsonify({"status": "empty"}), 400


if __name__ == "__main__":
  app.run(debug=True)

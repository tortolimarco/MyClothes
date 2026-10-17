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
import secrets
import hmac
import time
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
# Secrets must be supplied by the hosting environment. The fallback keeps local
# development usable but intentionally invalidates sessions after a restart.
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_urlsafe(48)
app.config.update(
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
DB_NAME = os.environ.get("DB_NAME", "myclothes.db")
LOGIN_ATTEMPTS = {}


def rate_limited(key, limit=5, window=900):
  now = time.monotonic()
  attempts = [stamp for stamp in LOGIN_ATTEMPTS.get(key, []) if now - stamp < window]
  if len(attempts) >= limit:
    LOGIN_ATTEMPTS[key] = attempts
    return True
  attempts.append(now)
  LOGIN_ATTEMPTS[key] = attempts
  return False


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self' 'unsafe-inline' https://translate.google.com https://translate.googleapis.com; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://paypal.me",
    )
    return response


def same_origin_request():
    expected = request.host_url.rstrip("/")
    origin = request.headers.get("Origin")
    if origin:
        return origin.rstrip("/") == expected
    referer = request.headers.get("Referer")
    if referer:
        parsed = urlparse(referer)
        return f"{parsed.scheme}://{parsed.netloc}" == expected
    return True


def csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


@app.context_processor
def inject_security_helpers():
    return {"csrf_token": csrf_token}


@app.before_request
def reject_cross_origin_mutations():
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not same_origin_request():
        return jsonify({"status": "error", "message": "Richiesta non autorizzata."}), 403
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        supplied_token = request.headers.get("X-CSRF-Token") or request.form.get("_csrf_token")
        expected_token = session.get("_csrf_token")
        if not supplied_token or not expected_token or not hmac.compare_digest(supplied_token, expected_token):
            return jsonify({"status": "error", "message": "Token CSRF non valido."}), 403
    return None

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


def migrate_legacy_passwords():
  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(cursor, "SELECT email, password FROM utenti")
  rows = cursor.fetchall()
  for email, stored_password in rows:
    if stored_password and not stored_password.startswith(("scrypt:", "pbkdf2:")):
      execute_query(
          cursor,
          "UPDATE utenti SET password = ? WHERE email = ?",
          (generate_password_hash(stored_password), email),
      )
  conn.commit()
  cursor.close()
  release_db_connection(conn)


init_db()
migrate_legacy_passwords()


def get_current_user():
  return session.get("user_email")


def mask_email(email):
  if not email or "@" not in email:
    return "Cliente"
  local, domain = email.split("@", 1)
  visible = (local[:1] + "***") if local else "***"
  return f"{visible}@{domain}"


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
      "SELECT id, mittente, testo, immagine FROM chat WHERE user_id = ?"
      " ORDER BY id ASC",
      (uid,),
  )
  chat_utente = [
      {"id": r[0], "mittente": r[1], "testo": r[2], "immagine": r[3]}
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
          "email": mask_email(r[1]),
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

  if rate_limited(f"user:{request.remote_addr}:{email}"):
    session["auth_error"] = "Troppi tentativi. Riprova più tardi."
    session["active_tab"] = "login"
    return redirect(url_for("home"))

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

  stored_password = row[0] or ""
  valid_password = (
      check_password_hash(stored_password, password)
      if stored_password.startswith(("scrypt:", "pbkdf2:"))
      else hmac.compare_digest(stored_password, password)
  )
  if not valid_password:
    session["auth_error"] = "Password errata! Riprova."
    session["active_tab"] = "login"
    return redirect(url_for("home"))

  LOGIN_ATTEMPTS.pop(f"user:{request.remote_addr}:{email}", None)
  # Upgrade legacy plaintext passwords after a successful login.
  if not stored_password.startswith(("scrypt:", "pbkdf2:")):
    conn = get_db_connection()
    cursor = conn.cursor()
    execute_query(cursor, "UPDATE utenti SET password = ? WHERE email = ?", (generate_password_hash(password), email))
    conn.commit()
    cursor.close()
    release_db_connection(conn)
  session.clear()
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
  if len(password) < 12:
    session["auth_error"] = "La password deve contenere almeno 12 caratteri."
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
      (email, generate_password_hash(password), user_id),
  )
  conn.commit()
  cursor.close()
  release_db_connection(conn)

  session["user_email"] = email
  session["user_id"] = user_id
  return redirect(url_for("home"))


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
      "SELECT id, mittente, testo, immagine FROM chat WHERE user_id = ?"
      " ORDER BY id ASC",
      (uid,),
  )
  rows = cursor.fetchall()
  cursor.close()
  release_db_connection(conn)
  return jsonify(
      [{"id": r[0], "mittente": r[1], "testo": r[2], "immagine": r[3]} for r in rows]
  )


@app.route("/api/chat/modifica/<int:msg_id>", methods=["POST"])
def modifica_messaggio(msg_id):
  uid = get_user_id()
  data = request.get_json() or {}
  nuovo_testo = data.get("testo", "").strip()

  if not nuovo_testo:
    return jsonify({"status": "error", "message": "Testo vuoto"}), 400

  conn = get_db_connection()
  cursor = conn.cursor()

  if session.get("admin_logged_in"):
    execute_query(
        cursor,
        "UPDATE chat SET testo = ? WHERE id = ?",
        (nuovo_testo, msg_id),
    )
  else:
    execute_query(
        cursor,
        "UPDATE chat SET testo = ? WHERE id = ? AND user_id = ? AND mittente ="
        " 'cliente'",
        (nuovo_testo, msg_id, uid),
    )

  conn.commit()
  cursor.close()
  release_db_connection(conn)
  return jsonify({"status": "success"})


@app.route("/api/chat/elimina/<int:msg_id>", methods=["POST"])
def elimina_messaggio(msg_id):
  uid = get_user_id()
  conn = get_db_connection()
  cursor = conn.cursor()

  if session.get("admin_logged_in"):
    execute_query(cursor, "DELETE FROM chat WHERE id = ?", (msg_id,))
  else:
    execute_query(
        cursor,
        "DELETE FROM chat WHERE id = ? AND user_id = ? AND mittente = 'cliente'",
        (msg_id, uid),
    )

  conn.commit()
  cursor.close()
  release_db_connection(conn)
  return jsonify({"status": "success"})


@app.route("/api/admin/chat/svuota/<user_id>", methods=["POST"])
def api_admin_svuota_chat(user_id):
  if not session.get("admin_logged_in"):
    return jsonify({"status": "error"}), 401

  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(cursor, "DELETE FROM chat WHERE user_id = ?", (user_id,))
  conn.commit()
  cursor.close()
  release_db_connection(conn)
  return jsonify({"status": "success"})


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
  prodotto = str(data.get("prodotto", "")).strip()
  metodo = str(data.get("metodo", "")).strip()
  try:
    importo = Decimal(str(data.get("importo", "")))
  except (InvalidOperation, ValueError):
    return jsonify({"status": "error", "message": "Importo non valido."}), 400
  if not prodotto or len(prodotto) > 200 or metodo != "PayPal" or importo <= 0 or importo > Decimal("100000"):
    return jsonify({"status": "error", "message": "Dati ordine non validi."}), 400

  conn = get_db_connection()
  cursor = conn.cursor()

  execute_query(cursor, "SELECT valore FROM contatore WHERE id = 1")
  val = cursor.fetchone()[0] + 1
  execute_query(cursor, "UPDATE contatore SET valore = ? WHERE id = 1", (val,))

  codice_ordine = f"#{val:04d}"
  ordine_id = str(uuid.uuid4())

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
          prodotto,
          str(importo.quantize(Decimal("0.01"))),
          metodo,
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
  uid = get_user_id() if get_current_user() else None
  if not uid:
    return redirect(url_for("home"))
  nome = request.form.get("nome", "").strip()
  indirizzo = request.form.get("indirizzo", "").strip()
  citta = request.form.get("citta", "").strip()
  if not all((nome, indirizzo, citta)) or any(len(v) > 200 for v in (nome, indirizzo, citta)):
    return redirect(url_for("home"))

  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      (
          "UPDATE ordini SET nome = ?, indirizzo = ?, citta = ?, stato = 'In"
          " elaborazione' WHERE id = ? AND user_id = ? AND stato = 'Pagamento Verificato - Inserisci Spedizione'"
      ),
      (nome, indirizzo, citta, ordine_id, uid),
  )
  conn.commit()
  cursor.close()
  release_db_connection(conn)

  return redirect(url_for("home"))


@app.route("/elimina-ordine-cliente/<ordine_id>", methods=["POST"])
def elimina_ordine_cliente(ordine_id):
  uid = get_user_id() if get_current_user() else None
  if not uid:
    return redirect(url_for("home"))
  conn = get_db_connection()
  cursor = conn.cursor()
  execute_query(
      cursor,
      (
          "DELETE FROM ordini WHERE id = ? AND user_id = ? AND (stato = 'Arrivato' OR stato ="
          " 'Annullato')"
      ),
      (ordine_id, uid),
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
      "SELECT codice, prodotto, stato FROM ordini WHERE id = ? AND user_id = ?",
      (ordine_id, get_user_id()),
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
    if rate_limited(f"admin:{request.remote_addr}"):
      return render_template("login.html", errore=True), 429
    if ADMIN_PASSWORD and hmac.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
      LOGIN_ATTEMPTS.pop(f"admin:{request.remote_addr}", None)
      session.clear()
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
      cursor, "SELECT email, user_id, data_creazione FROM utenti"
  )
  user_rows = cursor.fetchall()
  lista_utenti = [
      {
          "email": ur[0],
          "user_id": ur[1],
          "data": str(ur[2]),
      }
      for ur in user_rows
  ]
  email_per_uid = {ur[2]: ur[0] for ur in user_rows}

  execute_query(
      cursor,
      (
          "SELECT user_id, user_agent, ip_address, ultimo_accesso FROM"
          " visitatori ORDER BY ultimo_accesso DESC LIMIT 10"
      ),
  )
  visitatori_rows = cursor.fetchall()

  visitatori_completi = []
  for vr in visitatori_rows:
    v_uid = vr[0]
    registrato = v_uid in email_per_uid
    email_assoc = email_per_uid.get(v_uid, "")
    visitatori_completi.append({
        "user_id": v_uid,
        "user_agent": vr[1],
        "ip": vr[2],
        "ultimo_accesso": str(vr[3]),
        "registrato": registrato,
        "email": email_assoc,
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
      "visitatori_non_registrati": visitatori_completi,
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
      "SELECT id, mittente, testo, immagine FROM chat WHERE user_id = ?"
      " ORDER BY id ASC",
      (user_id,),
  )
  rows = cursor.fetchall()
  cursor.close()
  release_db_connection(conn)
  return jsonify(
      [{"id": r[0], "mittente": r[1], "testo": r[2], "immagine": r[3]} for r in rows]
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
  app.run(debug=False)

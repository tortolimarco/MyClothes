# Audit di sicurezza MyClothes

**Target:** `https://myclothes-n36x.onrender.com`  
**Repository analizzato:** `https://github.com/tortolimarco/MyClothes`  
**Commit esaminato:** `5fa0818`  
**Metodo:** analisi statica del codice, cronologia Git, controlli HTTP passivi e verifiche non distruttive. Non sono stati eseguiti brute force, pagamenti, cancellazioni o esfiltrazioni.

## Rischi critici

### 1. Segreto Flask hardcoded e possibile falsificazione delle sessioni

`app.py` contiene un valore statico usato come `app.secret_key`. Flask firma i cookie di sessione con questo valore. Poiché il codice è pubblico, chiunque può tentare di costruire cookie validi e impostare flag come `admin_logged_in` senza conoscere la password admin. Il segreto deve essere casuale, lungo, presente solo nelle variabili d’ambiente e ruotato immediatamente.

**Impatto:** impersonificazione admin, accesso a chat, ordini, indirizzi, email, IP e dati account; modifica o cancellazione dei dati.

### 2. Password amministratore hardcoded e pubblica

Una password amministratore è assegnata direttamente in `app.py`. Non è necessario eseguire brute force: la credenziale è già esposta nel codice. Deve essere revocata e sostituita con una variabile d’ambiente robusta, con rate limiting, MFA e logging degli accessi.

### 3. Password degli utenti memorizzate e restituite in chiaro

Le password sono salvate direttamente nella colonna `utenti.password`. L’endpoint autenticato `/api/admin/dati` seleziona e invia la colonna password al browser admin; `admin.html` le visualizza. Anche un singolo accesso admin compromesso espone tutte le password e gli utenti possono averle riutilizzate altrove.

**Azione urgente:** invalidare le password attuali, migrare ad Argon2id o almeno `werkzeug.security.generate_password_hash`, rimuovere il campo dai payload admin e imporre il reset di tutti gli account.

### 4. Autorizzazioni mancanti su ordini e recensioni

`/salva-spedizione/<ordine_id>` e `/elimina-ordine-cliente/<ordine_id>` modificano o eliminano ordini senza verificare che l’ordine appartenga all’utente autenticato. `/invia-recensione/<ordine_id>` controlla solo che l’ordine sia arrivato, non che appartenga all’utente corrente.

**Impatto:** alterazione di indirizzi, stato degli ordini, cancellazione di ordini e recensioni fraudolente tramite ID di un altro utente.

### 5. XSS nei dati dinamici

`index.html` e `admin.html` costruiscono HTML con `innerHTML` concatenando dati provenienti da chat, recensioni, ordini, email, indirizzi, motivi e immagini. Esempi: `chatBox.innerHTML = html`, `container.innerHTML = html`, `msgBox.innerHTML = html`. I dati devono essere inseriti con `textContent`/DOM API o sottoposti a sanitizzazione contestuale; gli URL immagine devono essere validati tramite allowlist.

**Impatto:** esecuzione di JavaScript nel browser degli utenti o dell’amministratore, furto della sessione, operazioni eseguite nel loro contesto e lettura dei dati visibili.

## Rischi alti

### 6. CSRF assente

I form e le chiamate AJAX che modificano dati non includono token CSRF. Sono coinvolti login/registrazione, messaggi, recensioni, indirizzi, ordini e azioni admin. `SameSite` è una difesa aggiuntiva, non sostituisce la validazione server-side del token.

### 7. ID ordine prevedibile e controllo di proprietà assente

L’ID viene generato con `str(uuid.uuid4())[:8]`, quindi è troncato. Anche se non è immediatamente enumerabile, riduce lo spazio di ricerca e diventa pericoloso insieme alle autorizzazioni mancanti.

### 8. Pagamenti non verificati dal server

`/registra-pagamento` accetta dal browser prodotto, importo e metodo e crea un ordine “in attesa”. Non c’è una verifica server-side del prezzo né una conferma PayPal tramite API/webhook. Un utente può dichiarare un importo arbitrario o creare ordini falsi. Il server non deve mai fidarsi del prezzo inviato dal client.

### 9. Login “Google” non è OAuth

Il client chiede email e password tramite `prompt()` e invia la password a `/login-google`. Questa funzione deve essere rimossa completamente e sostituita con OAuth/OpenID Connect ufficiale. Non bisogna mai chiedere una password Google al proprio sito.

### 10. Protezioni HTTP e sessione insufficienti

La risposta pubblica osservata non includeva `Secure` e `SameSite` sul cookie di sessione e non includeva CSP, HSTS, `X-Content-Type-Options`, protezione anti-framing e `Referrer-Policy`. L’HTTP redirige a HTTPS, ma non sostituisce il flag `Secure` né HSTS.

## Rischi medi e operativi

- `app.run(debug=True)` è presente nel codice: se avviato direttamente in produzione, può esporre il debugger.
- Nessun rate limiting su login admin, login utenti o endpoint di scrittura.
- Nessun limite server-side su dimensione di testo, immagini base64 o richieste: possibile consumo di memoria/database.
- IP, User-Agent, email, indirizzi, chat e recensioni sono raccolti con ampia visibilità admin; servono minimizzazione, retention e protezione degli accessi.
- Il repository è pubblico: anche dopo aver rimosso le credenziali dal file corrente, i segreti della cronologia Git restano esposti e devono essere considerati compromessi.
- `requirements.txt` non fissa versioni e non include una pipeline di audit dipendenze.

## Piano di bonifica

1. Ruotare subito `SECRET_KEY`, password admin, `DATABASE_URL`, credenziali PayPal e qualsiasi segreto storico; invalidare tutte le sessioni.
2. Impostare il repository privato finché la bonifica non è completata.
3. Migrare password a hashing Argon2id/bcrypt, eliminare la restituzione delle password e forzare reset account.
4. Rifare il controllo autorizzativo centralizzato per ogni risorsa con `user_id` e usare UUID completi.
5. Aggiungere CSRF server-side a tutti i POST e alle API mutanti.
6. Rimuovere `/login-google` e implementare OAuth ufficiale.
7. Eliminare `innerHTML` non sicuro o applicare encoding/sanitizzazione contestuale; validare e ricodificare le immagini.
8. Integrare un checkout PayPal ufficiale e verificare importo/stato tramite API e webhook firmati.
9. Configurare cookie `Secure; HttpOnly; SameSite=Lax/Strict`, CSP, HSTS, `nosniff`, anti-framing e Referrer-Policy.
10. Aggiungere rate limiting, limiti payload/upload, logging senza password e scansione automatica delle dipendenze.
11. Eseguire migrazione e test in ambiente separato, poi pubblicare solo dopo revisione e rotazione dei segreti.

## Stato

L’audit è completato. **Non ho pubblicato modifiche e non ho usato la password admin esposta per accedere al pannello.** Il sito non deve essere considerato sicuro finché i punti critici sopra non sono corretti e i segreti non sono ruotati.

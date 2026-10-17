# Configurazione sicura su Render

Questa versione richiede due variabili d’ambiente nel servizio Render:

- `SECRET_KEY`: una stringa casuale lunga almeno 48 caratteri.
- `ADMIN_PASSWORD`: una password admin lunga almeno 20 caratteri, diversa da qualsiasi password utente.

Su Render: apri il servizio → **Environment** → aggiungi le due variabili → salva e fai un nuovo deploy.

Non inserire queste variabili nel repository GitHub e non inviarle in chat.

## Prima del deploy

1. Imposta il repository GitHub come privato.
2. Ruota qualsiasi credenziale PayPal, database o API che sia mai stata presente nel repository o nella cronologia Git.
3. Considera compromesse tutte le password utenti memorizzate prima della migrazione e avvisa gli utenti di cambiarle, soprattutto se le hanno riutilizzate altrove.
4. Non usare ancora il flusso PayPal per ordini reali: questa versione valida formato e importo, ma la conferma del pagamento deve ancora essere collegata alle API/webhook ufficiali PayPal.

## Cosa protegge questa versione

- Password utenti hashate e migrazione automatica delle vecchie password in chiaro.
- Nessuna password restituita all’interfaccia admin.
- Cookie `Secure`, `HttpOnly` e `SameSite=Lax`.
- Token CSRF per form e chiamate AJAX.
- Controllo same-origin e rate limiting di base per i login.
- Controlli di proprietà su spedizioni, cancellazioni e recensioni.
- Header HTTP di sicurezza.
- Sanitizzazione dei dati dinamici nelle chat, negli ordini e nelle recensioni.
- Rimozione del finto login Google che chiedeva la password Google.
- ID ordine completi invece di UUID troncati.

La sicurezza non è una garanzia assoluta: dopo il deploy servono anche backup, aggiornamenti dipendenze, monitoraggio degli accessi e una vera integrazione PayPal verificata server-side.

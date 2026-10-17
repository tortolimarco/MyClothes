import os

from app import app, execute_query, get_db_connection

app.config.update(TESTING=True)
client = app.test_client()


def csrf_headers(test_client):
    with test_client.session_transaction() as session:
        return {'X-CSRF-Token': session['_csrf_token']}

response = client.get('/')
assert response.status_code == 200
for header in (
    'Strict-Transport-Security',
    'X-Content-Type-Options',
    'X-Frame-Options',
    'Referrer-Policy',
    'Permissions-Policy',
    'Content-Security-Policy',
):
    assert header in response.headers, header

response = client.post(
    '/registra-utente',
    data={
        'email': 'alice@example.com',
        'password': 'CorrectHorseBatteryStaple!',
        'password_confirm': 'CorrectHorseBatteryStaple!',
    },
    headers=csrf_headers(client),
    follow_redirects=False,
)
assert response.status_code == 302

conn = get_db_connection()
cursor = conn.cursor()
execute_query(cursor, 'SELECT password FROM utenti WHERE email = ?', ('alice@example.com',))
stored_password = cursor.fetchone()[0]
cursor.close()
conn.close()
assert stored_password != 'CorrectHorseBatteryStaple!'
assert stored_password.startswith(('scrypt:', 'pbkdf2:'))

response = client.post('/invia', json={'testo': 'test'}, headers={'Origin': 'https://evil.example'})
assert response.status_code == 403

anonymous = app.test_client()
assert anonymous.post('/salva-spedizione/not-an-order', data={'nome': 'x', 'indirizzo': 'y', 'citta': 'z'}).status_code == 403
assert anonymous.post('/elimina-ordine-cliente/not-an-order').status_code == 403
assert anonymous.get('/api/admin/dati').status_code == 401

print('SECURITY TESTS PASSED')

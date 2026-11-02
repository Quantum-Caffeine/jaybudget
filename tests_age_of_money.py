import os, tempfile
tmp = tempfile.TemporaryDirectory()
os.environ['BUDGET_DATA_DIR'] = tmp.name

import sys
sys.path.insert(0, r'd:\GitHub\ynab-clone')
from app.main import init, app, calculate_age_of_money
from fastapi.testclient import TestClient

init()
client = TestClient(app)

# 1. Créer 2 comptes cash
acc1 = client.post('/api/accounts', json={'name': 'Compte Courant', 'kind': 'checking', 'opening_balance': 0, 'profile_id': 1}).json()['id']
acc2 = client.post('/api/accounts', json={'name': 'Compte Épargne', 'kind': 'savings', 'opening_balance': 0, 'profile_id': 1}).json()['id']

# 2. Entrée d'argent de 1000$ le 2026-01-01
client.post('/api/transactions', json={'account_id': acc1, 'tx_date': '2026-01-01', 'amount': 1000.0})

# 3. Transfert interne de 400$ du compte 1 vers compte 2 le 2026-01-05 (ne doit pas compter comme sortie)
client.post('/api/transactions', json={'account_id': acc1, 'tx_date': '2026-01-05', 'amount': -400.0, 'transfer_account_id': acc2})
client.post('/api/transactions', json={'account_id': acc2, 'tx_date': '2026-01-05', 'amount': 400.0, 'transfer_account_id': acc1})

# 4. Première dépense réelle de 200$ le 2026-01-11 (10 jours après l'entrée du 01-01)
client.post('/api/transactions', json={'account_id': acc1, 'tx_date': '2026-01-11', 'amount': -200.0})

# 5. Deuxième dépense réelle de 300$ le 2026-01-21 (20 jours après l'entrée du 01-01)
client.post('/api/transactions', json={'account_id': acc2, 'tx_date': '2026-01-21', 'amount': -300.0})

# Calcul de l'Âge de l'argent: (10 + 20) / 2 = 15 jours
aom = calculate_age_of_money(profile_id=1)
assert aom == 15, f"Attendu 15 jours, obtenu {aom}"

# Test via l'API dashboard
dash = client.get('/api/dashboard?profile_id=1').json()
assert 'age_of_money' in dash, "age_of_money manquant dans /api/dashboard"
assert dash['age_of_money'] == 15, f"Dashboard retourne {dash.get('age_of_money')}"

print("ALL AGE OF MONEY TESTS PASSED!")

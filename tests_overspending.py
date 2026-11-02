import os, tempfile
tmp = tempfile.TemporaryDirectory()
os.environ['BUDGET_DATA_DIR'] = tmp.name

import sys
sys.path.insert(0, r'd:\GitHub\ynab-clone')
from app.main import init, app
from fastapi.testclient import TestClient

init()
client = TestClient(app)

# 1. Créer 2 comptes: 1 compte chèques (cash), 1 carte de crédit
acc_cash = client.post('/api/accounts', json={'name': 'Compte Chèques', 'kind': 'checking', 'opening_balance': 2000.0, 'profile_id': 1}).json()['id']
acc_credit = client.post('/api/accounts', json={'name': 'Visa Infinite', 'kind': 'credit', 'opening_balance': 0.0, 'profile_id': 1}).json()['id']

# 2. Créer 1 groupe et 3 catégories
gid = client.post('/api/groups', json={'name': 'Dépenses', 'profile_id': 1}).json()['id']
cat_cash_over = client.post('/api/categories', json={'group_id': gid, 'name': 'Loyer', 'nature': 'Dépense'}).json()['id']
cat_credit_over = client.post('/api/categories', json={'group_id': gid, 'name': 'Restaurants', 'nature': 'Dépense'}).json()['id']
cat_good = client.post('/api/categories', json={'group_id': gid, 'name': 'Électricité', 'nature': 'Dépense'}).json()['id']

# Mois du test: 2026-11
month = '2026-11'

# Catégorie 1: Loyer -> Assigné 500$, Dépense Chèques (cash) 600$ => Dépassement cash (-100$)
client.post('/api/assign', json={'category_id': cat_cash_over, 'month': month, 'assigned': 500.0})
client.post('/api/transactions', json={'account_id': acc_cash, 'category_id': cat_cash_over, 'tx_date': '2026-11-05', 'amount': -600.0})

# Catégorie 2: Restaurants -> Assigné 100$, Dépense Carte Crédit 150$ => Dépassement crédit (-50$)
client.post('/api/assign', json={'category_id': cat_credit_over, 'month': month, 'assigned': 100.0})
client.post('/api/transactions', json={'account_id': acc_credit, 'category_id': cat_credit_over, 'tx_date': '2026-11-10', 'amount': -150.0})

# Catégorie 3: Électricité -> Assigné 200$, Dépense Carte Crédit 80$ => Positif (+120$)
client.post('/api/assign', json={'category_id': cat_good, 'month': month, 'assigned': 200.0})
client.post('/api/transactions', json={'account_id': acc_credit, 'category_id': cat_good, 'tx_date': '2026-11-12', 'amount': -80.0})

# Récupérer le budget
b = client.get(f'/api/budget?month={month}&profile_id=1').json()
c_loyer = next(c for c in b if c['id'] == cat_cash_over)
c_resto = next(c for c in b if c['id'] == cat_credit_over)
c_hydro = next(c for c in b if c['id'] == cat_good)

# Vérifications
assert c_loyer['available'] == -100.0
assert c_loyer['overspending_type'] == 'cash', f"Attendu cash, reçu {c_loyer.get('overspending_type')}"

assert c_resto['available'] == -50.0
assert c_resto['overspending_type'] == 'credit', f"Attendu credit, reçu {c_resto.get('overspending_type')}"

assert c_hydro['available'] == 120.0
assert c_hydro['overspending_type'] is None, f"Attendu None, reçu {c_hydro.get('overspending_type')}"

# Test supplémentaire: Mixte avec priorité au cash
# Si Resto a en plus 110$ de dépense cash (donc cash_activity = -110$, pour 100$ assigné) => cash_overspent
client.post('/api/transactions', json={'account_id': acc_cash, 'category_id': cat_credit_over, 'tx_date': '2026-11-15', 'amount': -110.0})
b2 = client.get(f'/api/budget?month={month}&profile_id=1').json()
c_resto2 = next(c for c in b2 if c['id'] == cat_credit_over)
assert c_resto2['available'] == -160.0 # 100 - 150 - 110
assert c_resto2['overspending_type'] == 'cash', f"Attendu cash en cas de dépassement cash partiel, reçu {c_resto2.get('overspending_type')}"

print("ALL OVERSPENDING TESTS PASSED!")

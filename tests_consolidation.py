import os, tempfile, glob
tmp = tempfile.TemporaryDirectory()
os.environ['BUDGET_DATA_DIR'] = tmp.name

import sys
sys.path.insert(0, r'd:\GitHub\ynab-clone')
from app.main import init, app, db
from fastapi.testclient import TestClient

init()
client = TestClient(app)

# 1. Créer 2 comptes: 1 chèques (opening: 500$), 1 crédit (opening: 0$)
acc_cash = client.post('/api/accounts', json={'name': 'Chèques Consolidation', 'kind': 'checking', 'opening_balance': 500.0, 'profile_id': 1}).json()['id']
acc_credit = client.post('/api/accounts', json={'name': 'Visa Consolidation', 'kind': 'credit', 'opening_balance': 0.0, 'profile_id': 1}).json()['id']

# 2. Créer 1 groupe, 1 catégorie et 1 cible
gid = client.post('/api/groups', json={'name': 'Vie courante', 'profile_id': 1}).json()['id']
cid = client.post('/api/categories', json={'group_id': gid, 'name': 'Alimentation', 'nature': 'Dépense'}).json()['id']
client.post('/api/targets', json={'category_id': cid, 'kind': 'refill', 'amount': 250.0})

# 3. Ajouter des transactions:
# - Entrée d'argent de 1000$ sur le compte chèques
client.post('/api/transactions', json={'account_id': acc_cash, 'tx_date': '2026-10-01', 'amount': 1000.0})
# - Dépense de 200$ sur chèques
client.post('/api/transactions', json={'account_id': acc_cash, 'category_id': cid, 'tx_date': '2026-10-05', 'amount': -200.0})
# - Dépense de 150$ sur carte de crédit
client.post('/api/transactions', json={'account_id': acc_credit, 'category_id': cid, 'tx_date': '2026-10-06', 'amount': -150.0})

# Assigner 300$ au mois d'octobre
client.post('/api/assign', json={'category_id': cid, 'month': '2026-10', 'assigned': 300.0})

# Solde calculé avant consolidation:
# Chèques: 500 + 1000 - 200 = 1300$
# Crédit: 0 - 150 = -150$
# Patrimoine net: 1300 - 150 = 1150$

# 4. Exécuter la consolidation / repartir à neuf
res_fresh = client.post('/api/fresh-start', json={'profile_id': 1})
assert res_fresh.status_code == 200, f"Erreur fresh-start: {res_fresh.text}"
data = res_fresh.json()
assert data['ok'] is True
assert data['backup_created'] is True

# 5. Vérifications post-consolidation:
# - Transactions réinitialisées à 0
txs = client.get('/api/transactions?profile_id=1').json()
assert len(txs) == 0, f"Attendu 0 transactions, obtenu {len(txs)}"

# - Assignations réinitialisées à 0
b = client.get('/api/budget?month=2026-10&profile_id=1').json()
c_alim = next(c for c in b if c['id'] == cid)
assert c_alim['assigned'] == 0.0, f"Assigné attendu 0, obtenu {c_alim['assigned']}"

# - Catégorie, cible et groupe toujours présents intacts
assert c_alim['name'] == 'Alimentation'
assert c_alim['target_amount'] == 250.0

# - Nouveaux soldes initiaux des comptes
accs = client.get('/api/accounts?profile_id=1').json()
a_cash = next(a for a in accs if a['id'] == acc_cash)
a_credit = next(a for a in accs if a['id'] == acc_credit)
assert a_cash['opening_balance'] == 1300.0, f"Opening balance chèques attendu 1300, obtenu {a_cash['opening_balance']}"
assert a_cash['balance'] == 1300.0
assert a_credit['opening_balance'] == -150.0, f"Opening balance crédit attendu -150, obtenu {a_credit['opening_balance']}"
assert a_credit['balance'] == -150.0

# - Dashboard après consolidation
dash = client.get('/api/dashboard?profile_id=1').json()
assert dash['ready'] == 1300.0, f"Prêt à répartir attendu 1300, obtenu {dash['ready']}"
assert dash['net_worth'] == 1150.0, f"Patrimoine attendu 1150, obtenu {dash['net_worth']}"

# - Vérification présence fichier backup sur disque
backups = glob.glob(os.path.join(tmp.name, "budget_backup_before_fresh_start_*.db"))
assert len(backups) >= 1, "Le fichier de sauvegarde automatique n'a pas été trouvé"

print("ALL CONSOLIDATION / FRESH-START TESTS PASSED!")

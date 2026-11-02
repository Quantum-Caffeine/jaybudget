import os, tempfile
tmp = tempfile.TemporaryDirectory()
os.environ['BUDGET_DATA_DIR'] = tmp.name

import sys
sys.path.insert(0, r'd:\GitHub\ynab-clone')
from app.main import init, app, db
from fastapi.testclient import TestClient

init()
client = TestClient(app)

# 1. Création d'un groupe et de 2 catégories
res_grp = client.post('/api/groups', json={'name': 'Dépenses courantes', 'profile_id': 1})
gid = res_grp.json()['id']

res_cat1 = client.post('/api/categories', json={'group_id': gid, 'name': 'Épicerie', 'nature': 'Dépense'})
cid1 = res_cat1.json()['id']

res_cat2 = client.post('/api/categories', json={'group_id': gid, 'name': 'Transport', 'nature': 'Dépense'})
cid2 = res_cat2.json()['id']

# Configurer une cible sur cid1 (Épicerie: 300$/mois) et cid2 (Transport: 100$/mois)
client.post('/api/targets', json={'category_id': cid1, 'kind': 'refill', 'amount': 300.0})
client.post('/api/targets', json={'category_id': cid2, 'kind': 'refill', 'amount': 100.0})

# --- TEST 1: Underfunded ---
# En 2026-05, rien n'est assigné, donc le besoin est de 300 et 100
res_quick = client.post('/api/quick-assign', json={'month': '2026-05', 'mode': 'underfunded', 'profile_id': 1})
assert res_quick.status_code == 200
data = res_quick.json()
assert data['ok'] is True
assert data['count'] == 2

b_may = client.get('/api/budget?month=2026-05&profile_id=1').json()
c1_may = next(c for c in b_may if c['id'] == cid1)
c2_may = next(c for c in b_may if c['id'] == cid2)
assert c1_may['assigned'] == 300.0
assert c2_may['assigned'] == 100.0

# --- TEST 2: Last Month ---
# En 2026-06, on copie le mois précédent (2026-05)
res_last = client.post('/api/quick-assign', json={'month': '2026-06', 'mode': 'last_month', 'profile_id': 1})
assert res_last.status_code == 200
assert res_last.json()['ok'] is True
assert res_last.json()['count'] == 2

b_june = client.get('/api/budget?month=2026-06&profile_id=1').json()
c1_june = next(c for c in b_june if c['id'] == cid1)
c2_june = next(c for c in b_june if c['id'] == cid2)
assert c1_june['assigned'] == 300.0
assert c2_june['assigned'] == 100.0

# --- TEST 3: Reset ---
# On réinitialise 2026-06
res_reset = client.post('/api/quick-assign', json={'month': '2026-06', 'mode': 'reset', 'profile_id': 1})
assert res_reset.status_code == 200
assert res_reset.json()['ok'] is True
assert res_reset.json()['count'] == 2

b_june_after = client.get('/api/budget?month=2026-06&profile_id=1').json()
c1_june_after = next(c for c in b_june_after if c['id'] == cid1)
c2_june_after = next(c for c in b_june_after if c['id'] == cid2)
assert c1_june_after['assigned'] == 0.0
assert c2_june_after['assigned'] == 0.0

print("ALL QUICK-ASSIGN TESTS PASSED!")

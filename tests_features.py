import os, tempfile
tmp = tempfile.TemporaryDirectory()
os.environ['BUDGET_DATA_DIR'] = tmp.name

import sys
sys.path.insert(0, r'd:\GitHub\ynab-clone')
from app.main import init, app, add_profile
from fastapi.testclient import TestClient

init()
client = TestClient(app)

# 1. Create account & category
res_cat = client.post('/api/categories', json={'group_id': 1, 'name': 'Test Cat', 'nature': 'Dépense'})
assert res_cat.status_code == 200
cid = res_cat.json()['id']

# 2. Patch category
res_patch = client.patch(f'/api/categories/{cid}', json={'name': 'Renamed Cat', 'nature': 'Épargne'})
assert res_patch.status_code == 200
cats = client.get('/api/categories?profile_id=1').json()
found = next(c for c in cats if c['id'] == cid)
assert found['name'] == 'Renamed Cat'
assert found['nature'] == 'Épargne'

# 3. Move money between categories
res_cat2 = client.post('/api/categories', json={'group_id': 1, 'name': 'Cat 2', 'nature': 'Dépense'})
cid2 = res_cat2.json()['id']
client.post('/api/assign', json={'category_id': cid, 'month': '2026-10', 'assigned': 100})
client.post('/api/assign', json={'category_id': cid2, 'month': '2026-10', 'assigned': 50})

res_move = client.post('/api/move-money', json={
    'from_category_id': cid,
    'to_category_id': cid2,
    'month': '2026-10',
    'amount': 30
})
assert res_move.status_code == 200
assert res_move.json()['from_assigned'] == 70.0
assert res_move.json()['to_assigned'] == 80.0

# 4. Activity filtering on transactions
res_acc = client.post('/api/accounts', json={'name': 'Compte Test', 'opening_balance': 500, 'profile_id': 1})
aid = res_acc.json()['id']

tx1 = client.post('/api/transactions', json={
    'account_id': aid, 'tx_date': '2026-10-15', 'payee': 'Costco', 'amount': -45.5, 'category_id': cid
}).json()['id']

tx_filtered = client.get(f'/api/transactions?category_id={cid}&month=2026-10&profile_id=1').json()
assert len(tx_filtered) == 1
assert tx_filtered[0]['id'] == tx1

# 5. Patch transaction inline category
client.patch(f'/api/transactions/{tx1}', json={'category_id': cid2})
tx_cat2 = client.get(f'/api/transactions?category_id={cid2}&month=2026-10&profile_id=1').json()
assert len(tx_cat2) == 1
assert tx_cat2[0]['id'] == tx1

# 6. Delete category safety check
res_del_blocked = client.delete(f'/api/categories/{cid2}')
assert res_del_blocked.status_code == 400 # Has transactions

client.delete(f'/api/transactions/{tx1}')
res_del_ok = client.delete(f'/api/categories/{cid2}')
assert res_del_ok.status_code == 200

print("ALL NEW FEATURES TESTS PASSED SUCCESSFULLY!")

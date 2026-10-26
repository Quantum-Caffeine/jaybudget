import os, tempfile
tmp = tempfile.TemporaryDirectory()
os.environ['BUDGET_DATA_DIR'] = tmp.name

import sys
sys.path.insert(0, r'd:\GitHub\ynab-clone')
from app.main import init, app
from fastapi.testclient import TestClient

init()
client = TestClient(app)

# 1. Test approve-all endpoint
res_acc = client.post('/api/accounts', json={'name': 'Compte Test', 'opening_balance': 1000, 'profile_id': 1})
aid = res_acc.json()['id']

# Add 3 unapproved transactions
t1 = client.post('/api/transactions', json={'account_id': aid, 'tx_date': '2026-10-05', 'amount': -20, 'approved': False}).json()['id']
t2 = client.post('/api/transactions', json={'account_id': aid, 'tx_date': '2026-10-10', 'amount': -30, 'approved': False}).json()['id']
t3 = client.post('/api/transactions', json={'account_id': aid, 'tx_date': '2026-09-15', 'amount': -40, 'approved': False}).json()['id']

# Approve only month 2026-10
res_app = client.post('/api/transactions/approve-all?month=2026-10&profile_id=1')
assert res_app.status_code == 200
assert res_app.json()['approved_count'] == 2

# Verify t1 and t2 are approved, t3 still unapproved
tx_oct = client.get('/api/transactions?month=2026-10&profile_id=1').json()
assert all(t['approved'] == 1 for t in tx_oct)

tx_sep = client.get('/api/transactions?month=2026-09&profile_id=1').json()
assert any(t['id'] == t3 and t['approved'] == 0 for t in tx_sep)

# Approve all remaining
res_app_all = client.post('/api/transactions/approve-all?profile_id=1')
assert res_app_all.json()['approved_count'] == 1

# 2. Test Split Transactions creation
res_cat1 = client.post('/api/categories', json={'group_id': 1, 'name': 'Supermarché Test', 'nature': 'Dépense'})
cid1 = res_cat1.json()['id']
res_cat2 = client.post('/api/categories', json={'group_id': 1, 'name': 'Vêtements Test', 'nature': 'Dépense'})
cid2 = res_cat2.json()['id']

res_split = client.post('/api/transactions', json={
    'account_id': aid,
    'tx_date': '2026-10-15',
    'payee': 'Costco',
    'amount': -150.0,
    'splits': [
        {'category_id': cid1, 'amount': -100.0},
        {'category_id': cid2, 'amount': -50.0}
    ],
    'approved': True
})
assert res_split.status_code == 200
split_id = res_split.json()['id']

# Check budget activity reflects both categories
res_b = client.get('/api/budget?month=2026-10&profile_id=1').json()
b_map = {c['id']: c for c in res_b}
assert b_map[cid1]['activity'] == -100.0
assert b_map[cid2]['activity'] == -50.0

print("ALL SPLIT & APPROVE-ALL AUTOMATED TESTS PASSED!")

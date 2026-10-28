import os, tempfile
tmp = tempfile.TemporaryDirectory()
os.environ['BUDGET_DATA_DIR'] = tmp.name

import sys
sys.path.insert(0, r'd:\GitHub\ynab-clone')
from app.main import init, app, apply_rules, db
from fastapi.testclient import TestClient

init()
client = TestClient(app)

res_acc = client.post('/api/accounts', json={'name': 'Compte Test', 'opening_balance': 1000, 'profile_id': 1})
aid = res_acc.json()['id']
res_cat = client.post('/api/categories', json={'group_id': 1, 'name': 'Station Essence', 'nature': 'Dépense'})
cid = res_cat.json()['id']

# 1. Add historical transaction
client.post('/api/transactions', json={'account_id': aid, 'payee': 'Petro-Canada', 'amount': -55.0, 'category_id': cid})

# 2. Test apply_rules matching by historical payee
with db() as c:
    r = apply_rules(c, 'Petro-Canada')
    assert r is not None, "apply_rules should match historical payee"
    assert r['category_id'] == cid, f"Expected category {cid}, got {r['category_id']}"
    
    # Case insensitivity & whitespace
    r2 = apply_rules(c, '  petro-canada  ')
    assert r2 is not None and r2['category_id'] == cid

# 3. Test payees endpoint
res_payees = client.get('/api/payees?profile_id=1')
assert res_payees.status_code == 200
p_list = res_payees.json()
assert len(p_list) >= 1
assert any(p['name'] == 'Petro-Canada' and p['category_id'] == cid for p in p_list)

print("ALL PAYEE AUTO-CATEGORIZATION TESTS PASSED!")

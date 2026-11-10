import os, tempfile
tmp = tempfile.TemporaryDirectory()
os.environ['BUDGET_DATA_DIR'] = tmp.name
from app.main import app, add_account, add_transaction, accounts
from fastapi.testclient import TestClient

client = TestClient(app)

# 1. Rapprochement avec format francophone (virgule et espaces)
a1 = add_account({'name': 'Chèques', 'opening_balance': 1000})['id']
add_transaction({'account_id': a1, 'tx_date': '2026-11-01', 'payee': 'Salaire', 'amount': 250.50, 'cleared': True, 'approved': True})

res = client.post('/api/reconcile', json={'account_id': a1, 'statement_balance': '1 250,50', 'create_adjustment': False})
assert res.status_code == 200, res.text
assert res.json()['difference'] == 0.0, res.json()

# 2. Suppression de compte et suppression en cascade des virements liés
a2 = add_account({'name': 'Épargne', 'opening_balance': 500})['id']
client.post('/api/transactions', json={'account_id': a1, 'transfer_account_id': a2, 'amount': -100, 'payee': 'Épargne', 'cleared': True})

txs_before = client.get(f'/api/transactions?account_id={a2}').json()
assert len(txs_before) == 1

# Suppression du compte a1
res_del = client.delete(f'/api/accounts/{a1}')
assert res_del.status_code == 200

acc_list = client.get('/api/accounts').json()
assert not any(a['id'] == a1 for a in acc_list)

txs_after = client.get(f'/api/transactions?account_id={a2}').json()
assert len(txs_after) == 0, 'Twin transfer was not deleted'

print('ALL ACCOUNTS & RECONCILIATION TESTS PASSED!')

import os, tempfile, io
tmp = tempfile.TemporaryDirectory()
os.environ['BUDGET_DATA_DIR'] = tmp.name

import sys
sys.path.insert(0, r'd:\GitHub\ynab-clone')
from app.main import init, app, add_profile
from fastapi.testclient import TestClient

init()
client = TestClient(app)

plan_csv = '''"Month","Category Group/Category","Category Group","Category","Assigned","Activity","Available"
"Oct 2026","Factures: Hydro","Factures","Hydro",150.00$,-100.00$,50.00$
"Oct 2026","Alimentation: Épicerie","Alimentation","Épicerie",400.00$,-250.00$,150.00$
'''

reg_csv = '''"Account","Flag","Date","Payee","Category Group/Category","Category Group","Category","Memo","Outflow","Inflow","Cleared"
"Compte Courant","","2026/10/01","Starting Balance","Inflow: Ready to Assign","Inflow","Ready to Assign","",0.00$,1000.00$,"Cleared"
"Compte Courant","","2026/10/05","Hydro-Québec","Factures: Hydro","Factures","Hydro","Facture octobre",100.00$,0.00$,"Cleared"
"Compte Courant","","2026/10/10","Transfer : Épargne","","","","Virement",200.00$,0.00$,"Cleared"
"Épargne","","2026/10/10","Transfer : Compte Courant","","","","Virement",0.00$,200.00$,"Cleared"
'''

files = {
    'plan_file': ('Plan.csv', io.BytesIO(plan_csv.encode('utf-8-sig')), 'text/csv'),
    'register_file': ('Register.csv', io.BytesIO(reg_csv.encode('utf-8-sig')), 'text/csv')
}

res = client.post('/api/import/ynab?profile_id=1', files=files)
assert res.status_code == 200, res.text
data = res.json()
print("Import response:", data)
assert data['groups_imported'] >= 2
assert data['categories_imported'] >= 2
assert data['assigned_months_imported'] >= 2
assert data['accounts_created'] == 2
assert data['transactions_imported'] == 3 # Hydro + 2 transfer legs (starting balance goes to opening_balance)

# Check accounts balance
res_acc = client.get('/api/accounts?profile_id=1')
accs = {a['name']: a['balance'] for a in res_acc.json()}
print("Accounts balance:", accs)
assert accs['Compte Courant'] == 700.0 # 1000 - 100 - 200
assert accs['Épargne'] == 200.0 # 0 + 200

# Check budget available
res_b = client.get('/api/budget?month=2026-10&profile_id=1')
cats = {c['name']: c for c in res_b.json()}
print("Hydro category in budget:", cats['Hydro'])
assert cats['Hydro']['assigned'] == 150.0
assert cats['Hydro']['activity'] == -100.0
assert cats['Hydro']['available'] == 50.0

print("ALL YNAB IMPORT TESTS PASSED!")

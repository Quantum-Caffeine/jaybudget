import os, tempfile, unittest.mock
tmp = tempfile.TemporaryDirectory()
os.environ['BUDGET_DATA_DIR'] = tmp.name

import sys
sys.path.insert(0, r"d:\GitHub\ynab-clone")
from app.main import app, add_profile, add_account, categories, budget
from fastapi.testclient import TestClient

client = TestClient(app)

# Mock data returned by YNAB API
mock_budgets_data = {
    'budgets': [
        {'id': 'budget-123', 'name': 'Mon Budget Perso', 'last_modified_on': '2026-11-18'}
    ]
}

mock_categories_data = {
    'category_groups': [
        {
            'name': 'Factures Fixes',
            'hidden': False,
            'deleted': False,
            'categories': [
                {
                    'name': 'Hydro',
                    'hidden': False,
                    'deleted': False,
                    'goal_type': 'NEED',
                    'goal_target': 165000, # 165.00$
                    'goal_target_date': '2026-11-20',
                    'goal_day': 20,
                    'goal_cadence': 1,
                    'goal_cadence_frequency': 1
                },
                {
                    'name': 'Assurance Auto',
                    'hidden': False,
                    'deleted': False,
                    'goal_type': 'TB',
                    'goal_target': 1200000, # 1200.00$
                    'goal_target_date': '2027-05-15',
                    'goal_day': 15,
                    'goal_cadence': 13, # yearly
                    'goal_cadence_frequency': 1
                }
            ]
        }
    ]
}

def fake_ynab_request(endpoint, token):
    if endpoint == 'budgets':
        return mock_budgets_data
    elif 'categories' in endpoint:
        return mock_categories_data
    return {}

with unittest.mock.patch('app.main.ynab_api_request', side_effect=fake_ynab_request):
    # Test 1: Get budgets
    r_budgets = client.get('/api/import/ynab-api/budgets?token=test-token')
    assert r_budgets.status_code == 200, r_budgets.text
    budgets = r_budgets.json()
    assert len(budgets) == 1
    assert budgets[0]['name'] == 'Mon Budget Perso'

    # Test 2: Import targets
    r_import = client.post('/api/import/ynab-api/targets', json={
        'token': 'test-token',
        'profile_id': 1
    })
    assert r_import.status_code == 200, r_import.text
    res = r_import.json()
    print("Import targets response:", res)
    assert res['targets_imported'] == 2

    # Test 3: Check targets in budget
    b = client.get('/api/budget?month=2026-11&profile_id=1').json()
    hydro = next(c for c in b if c['name'] == 'Hydro')
    assert hydro['target_amount'] == 165.0
    assert hydro['due_date'] == '2026-11-20'
    assert hydro['due_day'] == 20
    assert hydro['frequency'] == 'monthly'

    assurance = next(c for c in b if c['name'] == 'Assurance Auto')
    assert assurance['target_amount'] == 1200.0
    assert assurance['due_date'] == '2027-05-15'
    assert assurance['frequency'] == 'yearly'

print("ALL YNAB API TESTS PASSED SUCCESSFULLY!")

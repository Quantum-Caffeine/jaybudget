"""Contrôles de fumée sans serveur: API et moteur de budget."""
import os, tempfile
tmp=tempfile.TemporaryDirectory(); os.environ['BUDGET_DATA_DIR']=tmp.name
from app.main import add_account, categories, add_transaction, assign, budget, dashboard, report, add_profile, target
a=add_account({'name':'Chèques','opening_balance':1000})['id']
cat=categories()[0]['id']
add_transaction({'account_id':a,'tx_date':'2026-09-01','payee':'Épicerie','amount':-125,'category_id':cat,'approved':True})
assign({'category_id':cat,'month':'2026-09','assigned':200})
b=budget('2026-09'); row=next(x for x in b if x['id']==cat)
assert row['available']==75.0, row
assert dashboard('2026-09')['net_worth']==875.0
assert report()['expenses']
target({'category_id':cat,'kind':'refill','amount':200,'frequency':'monthly','due_day':1})
assert next(x for x in budget('2026-09') if x['id']==cat)['recommendation']==125.0
family=add_profile({'name':'Famille'})['id']
assert len(categories(family))==4
assert add_account({'name':'Compte Famille','profile_id':family})['id']
print('Smoke test OK')

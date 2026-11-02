import csv, hashlib, hmac, io, json, os, re, secrets, shutil, sqlite3, uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

ROOT = Path(os.getenv("BUDGET_DATA_DIR", "data")); ROOT.mkdir(parents=True, exist_ok=True)
DB = ROOT / "budget.db"

def month_now(): return date.today().strftime("%Y-%m")
def money(v): return round(float(v or 0), 2)
@contextmanager
def db():
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    try: yield c; c.commit()
    finally: c.close()

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS profiles(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS groups(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, label TEXT, profile_id INTEGER DEFAULT 1, position INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY, group_id INTEGER NOT NULL REFERENCES groups(id), name TEXT NOT NULL, nature TEXT DEFAULT 'Dépense', saving_type TEXT DEFAULT '', hidden INTEGER DEFAULT 0, UNIQUE(group_id,name));
CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, kind TEXT DEFAULT 'checking', opening_balance REAL DEFAULT 0, closed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS category_month(category_id INTEGER, month TEXT, assigned REAL DEFAULT 0, PRIMARY KEY(category_id,month));
CREATE TABLE IF NOT EXISTS targets(id INTEGER PRIMARY KEY, category_id INTEGER NOT NULL UNIQUE REFERENCES categories(id), kind TEXT NOT NULL, amount REAL NOT NULL, due_date TEXT, repeat_months INTEGER DEFAULT 1, note TEXT DEFAULT '', frequency TEXT DEFAULT 'monthly', due_day INTEGER, due_weekday INTEGER, rollover_policy TEXT DEFAULT 'carry', project_category_id INTEGER, completed_on TEXT);
CREATE TABLE IF NOT EXISTS payees(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS rules(id INTEGER PRIMARY KEY, pattern TEXT NOT NULL, payee_id INTEGER REFERENCES payees(id), category_id INTEGER REFERENCES categories(id), memo TEXT DEFAULT '', active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY, account_id INTEGER NOT NULL REFERENCES accounts(id), tx_date TEXT NOT NULL, payee TEXT DEFAULT '', memo TEXT DEFAULT '', amount REAL NOT NULL, category_id INTEGER REFERENCES categories(id), splits TEXT DEFAULT '[]', transfer_account_id INTEGER REFERENCES accounts(id), transfer_id TEXT, imported_id TEXT UNIQUE, cleared INTEGER DEFAULT 0, approved INTEGER DEFAULT 0, flag TEXT DEFAULT '', recurring TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS reconciliations(id INTEGER PRIMARY KEY, account_id INTEGER, reconciled_on TEXT, statement_balance REAL, cleared_balance REAL, adjustment REAL DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_tx_date ON transactions(tx_date); CREATE INDEX IF NOT EXISTS ix_tx_account ON transactions(account_id);
'''
def add_column(c, table, definition):
  name=definition.split()[0]
  if name not in [x['name'] for x in c.execute(f'PRAGMA table_info({table})')]: c.execute(f'ALTER TABLE {table} ADD COLUMN {definition}')
def seed_profile(c, profile_id):
  defaults=[('Dépenses essentielles','Logement','Dépense',''),('Dépenses essentielles','Épicerie','Dépense',''),('Dépenses courantes','Transport','Dépense',''),('Épargne et projets','Fonds d’urgence','Épargne','Urgence')]
  groups={}
  for position,label in enumerate(['Dépenses essentielles','Dépenses courantes','Épargne et projets'],1):
    internal=f'{profile_id}:{label}'
    c.execute('INSERT OR IGNORE INTO groups(name,label,profile_id,position) VALUES(?,?,?,?)',(internal,label,profile_id,position))
    groups[label]=c.execute('SELECT id FROM groups WHERE name=?',(internal,)).fetchone()[0]
  for group,name,nature,saving in defaults:
    c.execute('INSERT OR IGNORE INTO categories(group_id,name,nature,saving_type) VALUES(?,?,?,?)',(groups[group],name,nature,saving))
def init():
  with db() as c:
    c.executescript(SCHEMA)
    # Les colonnes suivantes rendent la mise à jour non destructive pour les bases V2 existantes.
    add_column(c,'groups','label TEXT');add_column(c,'groups','profile_id INTEGER DEFAULT 1');add_column(c,'accounts','profile_id INTEGER DEFAULT 1')
    for field in ['frequency TEXT DEFAULT \'monthly\'','due_day INTEGER','due_weekday INTEGER','rollover_policy TEXT DEFAULT \'carry\'','project_category_id INTEGER','completed_on TEXT']: add_column(c,'targets',field)
    c.execute("INSERT OR IGNORE INTO profiles(id,name) VALUES(1,'Budget principal')")
    c.execute("UPDATE groups SET profile_id=1 WHERE profile_id IS NULL");c.execute('UPDATE groups SET label=name WHERE label IS NULL')
    if not c.execute('SELECT 1 FROM groups LIMIT 1').fetchone(): seed_profile(c,1)
init()
app=FastAPI(title='Budget Libre V2')

# --- Authentification par NIP (optionnelle) ---
BUDGET_PIN = os.getenv('BUDGET_PIN', '').strip()

def _pin_token(pin: str) -> str:
    """Génère un jeton de session déterministe à partir du NIP."""
    return hmac.new(pin.encode(), b'budget-libre-session', hashlib.sha256).hexdigest()

LOGIN_HTML = '''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Budget Libre — Connexion</title>
<style>*{box-sizing:border-box}body{margin:0;font:16px system-ui,sans-serif;background:#f6f8f8;display:flex;align-items:center;justify-content:center;min-height:100vh}
.card{background:#fff;border-radius:12px;padding:32px;box-shadow:0 4px 24px #0001;width:min(360px,90vw);text-align:center}
h1{color:#0b5d5c;margin:0 0 8px;font-size:22px}p{color:#476464;font-size:14px;margin:0 0 24px}
input{width:100%;padding:12px;border:1px solid #d9e2e1;border-radius:8px;font:inherit;text-align:center;letter-spacing:6px;font-size:20px;margin-bottom:16px}
input:focus{outline:2px solid #0b5d5c;border-color:#0b5d5c}
button{width:100%;padding:12px;background:#0b5d5c;color:#fff;border:0;border-radius:8px;font:inherit;cursor:pointer}
.error{color:#b42318;font-size:13px;margin-bottom:12px;display:none}</style></head>
<body><div class="card"><h1>🔒 Budget Libre</h1><p>Entrez votre NIP pour accéder à l'application.</p>
<form method="POST" action="/api/login"><input name="pin" type="password" placeholder="••••" autocomplete="current-password" autofocus required>
<div class="error" id="err">NIP incorrect</div>
<button>Déverrouiller</button></form>
<script>if(location.search.includes('fail'))document.getElementById('err').style.display='block'</script>
</div></body></html>'''

if BUDGET_PIN:
    class PinAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            path = request.url.path
            # Toujours autoriser la page de login et les assets du SW
            if path in ('/api/login', '/login'):
                return await call_next(request)
            expected = _pin_token(BUDGET_PIN)
            cookie = request.cookies.get('budget_session', '')
            if cookie == expected:
                return await call_next(request)
            # API → 401 JSON ; page → redirige vers login
            if path.startswith('/api/'):
                return Response('{"detail":"Non authentifié"}', status_code=401, media_type='application/json')
            return HTMLResponse(LOGIN_HTML)
    app.add_middleware(PinAuthMiddleware)

@app.get('/login')
def login_page():
    return HTMLResponse(LOGIN_HTML)

@app.post('/api/login')
async def login(request: Request):
    form = await request.form()
    pin = (form.get('pin') or '').strip()
    if not BUDGET_PIN or pin == BUDGET_PIN:
        resp = Response(status_code=303, headers={'location': '/'})
        resp.set_cookie('budget_session', _pin_token(pin), max_age=365*86400, httponly=True, samesite='lax')
        return resp
    return Response(status_code=303, headers={'location': '/login?fail=1'})

@app.post('/api/logout')
def logout():
    resp = Response('{"ok":true}', media_type='application/json')
    resp.delete_cookie('budget_session')
    return resp

@app.get('/api/profiles')
def profiles():
 with db() as c:return rows(c,'SELECT * FROM profiles ORDER BY id')
@app.post('/api/profiles')
def add_profile(p:dict):
 name=(p.get('name') or '').strip()
 if not name: raise HTTPException(400,'Le nom du profil est requis')
 with db() as c:
  try: pid=c.execute('INSERT INTO profiles(name) VALUES(?)',(name,)).lastrowid
  except sqlite3.IntegrityError: raise HTTPException(400,'Ce profil existe déjà')
  seed_profile(c,pid)
 return {'id':pid,'name':name}

def rows(c, sql, args=()): return [dict(x) for x in c.execute(sql,args).fetchall()]
def category_amount(tx):
  s=json.loads(tx['splits'] or '[]')
  return s if s else ([{'category_id':tx['category_id'],'amount':tx['amount']}] if tx['category_id'] else [])
def apply_rules(c,payee):
  if not payee: return None
  # 1. Règles explicites configurées
  for r in c.execute('SELECT rules.*,payees.name payee_name FROM rules LEFT JOIN payees ON payees.id=rules.payee_id WHERE active=1').fetchall():
    if re.search(r['pattern'],payee,re.I): return dict(r)
  # 2. Règle intelligente basée sur l'historique : catégorie la plus fréquente / récente pour ce marchand
  hist = c.execute('''SELECT category_id, memo FROM transactions 
                      WHERE LOWER(TRIM(payee))=LOWER(TRIM(?)) AND category_id IS NOT NULL 
                      GROUP BY category_id ORDER BY COUNT(*) DESC, tx_date DESC LIMIT 1''', (payee,)).fetchone()
  if hist:
    return {'category_id': hist['category_id'], 'memo': hist['memo'] or ''}
  return None
def tx_create(c,p):
  p={**p}; p['amount']=money(p.get('amount')); p['tx_date']=p.get('tx_date') or date.today().isoformat()
  p['splits']=json.dumps(p.get('splits') or [])
  cur=c.execute('''INSERT INTO transactions(account_id,tx_date,payee,memo,amount,category_id,splits,transfer_account_id,transfer_id,imported_id,cleared,approved,flag,recurring)
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(p['account_id'],p['tx_date'],p.get('payee',''),p.get('memo',''),p['amount'],p.get('category_id'),p['splits'],p.get('transfer_account_id'),p.get('transfer_id'),p.get('imported_id'),int(bool(p.get('cleared'))),int(bool(p.get('approved'))),p.get('flag',''),p.get('recurring','')))
  return cur.lastrowid

@app.get('/api/dashboard')
def dashboard(month: str=month_now(), profile_id:int=1):
 with db() as c:
  balance=c.execute('SELECT COALESCE(SUM(opening_balance),0)+COALESCE((SELECT SUM(amount) FROM transactions WHERE account_id IN (SELECT id FROM accounts WHERE profile_id=?)),0) FROM accounts WHERE closed=0 AND profile_id=?',(profile_id,profile_id)).fetchone()[0]
  
  # Soldes initiaux positifs (comptes de liquidités / chèques / épargne)
  cash_opening=c.execute("SELECT COALESCE(SUM(opening_balance),0) FROM accounts WHERE closed=0 AND profile_id=? AND kind IN ('checking','savings','cash') AND opening_balance>0",(profile_id,)).fetchone()[0]
  
  # Tous les revenus (entrées d'argent à répartir) perçus jusqu'à ce mois inclusivement
  inflows_up_to_month=c.execute('''SELECT COALESCE(SUM(amount),0) FROM transactions 
    WHERE account_id IN (SELECT id FROM accounts WHERE profile_id=?) 
      AND category_id IS NULL AND transfer_account_id IS NULL 
      AND substr(tx_date,1,7)<=?''',(profile_id, month)).fetchone()[0]
      
  # Tous les montants assignés aux catégories jusqu'à ce mois inclusivement
  assigned_up_to_month=c.execute('''SELECT COALESCE(SUM(cm.assigned),0) FROM category_month cm 
    JOIN categories ca ON ca.id=cm.category_id 
    JOIN groups g ON g.id=ca.group_id 
    WHERE cm.month<=? AND g.profile_id=?''',(month, profile_id)).fetchone()[0]
    
  ready=cash_opening + inflows_up_to_month - assigned_up_to_month
  return {'month':month,'net_worth':money(balance),'ready':money(ready),'accounts':rows(c,"SELECT a.*, round(a.opening_balance+COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.account_id=a.id),0),2) balance FROM accounts a WHERE closed=0 AND profile_id=? ORDER BY name",(profile_id,))}

def target_recommendation(target, available, today):
  if not target['target_amount']: return 0
  amount=float(target['target_amount']); kind=target['target_kind'] or 'refill'; due=target['due_date']
  # Renflouer remplit l'enveloppe à chaque période; les deux autres accumulent vers un objectif.
  if kind=='refill': return money(max(0,amount-available))
  if due:
   try:
    deadline=datetime.strptime(due,'%Y-%m-%d').date(); months=max(1,(deadline.year-today.year)*12+deadline.month-today.month+1)
    return money(max(0,amount-available)/months)
   except ValueError: pass
  return money(max(0,amount-available))
@app.get('/api/budget')
def budget(month: str=month_now(), profile_id:int=1):
 with db() as c:
  q='''SELECT g.id group_id,COALESCE(g.label,g.name) group_name,c.id,c.name,c.nature,c.saving_type,c.hidden,COALESCE(cm.assigned,0) assigned,
  COALESCE((SELECT SUM(CASE WHEN t.splits='[]' THEN t.amount ELSE 0 END) FROM transactions t WHERE t.category_id=c.id AND substr(t.tx_date,1,7)=?),0)+
  COALESCE((SELECT SUM(CAST(json_extract(j.value,'$.amount') AS REAL)) FROM transactions t,json_each(t.splits) j WHERE CAST(json_extract(j.value,'$.category_id') AS INTEGER)=c.id AND substr(t.tx_date,1,7)=?),0) activity,
  t.kind target_kind,t.amount target_amount,t.due_date,t.repeat_months,t.note,t.frequency,t.due_day,t.due_weekday,t.rollover_policy FROM categories c JOIN groups g ON g.id=c.group_id LEFT JOIN category_month cm ON cm.category_id=c.id AND cm.month=? LEFT JOIN targets t ON t.category_id=c.id WHERE c.hidden=0 AND g.profile_id=? ORDER BY g.position,g.name,c.name'''
  out=rows(c,q,(month,month,month,profile_id))
  # Pré-calcul des soldes antérieurs en 3 requêtes au lieu de N+1
  prior_assigned={r['category_id']:r['total'] for r in rows(c,'SELECT category_id,COALESCE(SUM(assigned),0) total FROM category_month WHERE month<? GROUP BY category_id',(month,))}
  prior_direct={r['category_id']:r['total'] for r in rows(c,"SELECT t.category_id,COALESCE(SUM(t.amount),0) total FROM transactions t WHERE t.splits='[]' AND t.category_id IS NOT NULL AND t.tx_date<? GROUP BY t.category_id",(month+'-01',))}
  prior_splits={r['cat_id']:r['total'] for r in rows(c,"SELECT CAST(json_extract(j.value,'$.category_id') AS INTEGER) cat_id,COALESCE(SUM(CAST(json_extract(j.value,'$.amount') AS REAL)),0) total FROM transactions t,json_each(t.splits) j WHERE t.splits!='[]' AND t.tx_date<? GROUP BY cat_id",(month+'-01',))}
  today=date.today()
  for x in out:
   cid=x['id']
   prior=prior_assigned.get(cid,0)+prior_direct.get(cid,0)+prior_splits.get(cid,0)
   x['available']=money(prior+x['assigned']+x['activity'])
   x['recommendation']=target_recommendation(x,x['available'],today)
  return out

@app.post('/api/assign')
def assign(p:dict):
 with db() as c:
  c.execute('INSERT INTO category_month(category_id,month,assigned) VALUES(?,?,?) ON CONFLICT(category_id,month) DO UPDATE SET assigned=excluded.assigned',(p['category_id'],p['month'],money(p['assigned'])))
 return {'ok':True}

@app.post('/api/quick-assign')
def quick_assign(p:dict):
 month = p.get('month')
 mode = p.get('mode', 'underfunded') # underfunded, last_month, reset
 profile_id = int(p.get('profile_id', 1))
 if not month: raise HTTPException(400, 'Mois requis')
 
 count = 0
 with db() as c:
  if mode == 'reset':
   cur = c.execute('''DELETE FROM category_month WHERE month=? AND category_id IN 
     (SELECT ca.id FROM categories ca JOIN groups g ON g.id=ca.group_id WHERE g.profile_id=?)''', (month, profile_id))
   count = cur.rowcount
  elif mode == 'last_month':
   # Calcul du mois précédent
   y, m = map(int, month.split('-'))
   prev_date = (date(y, m, 1) - timedelta(days=1))
   prev_month = prev_date.strftime('%Y-%m')
   prev_assigned = rows(c, '''SELECT cm.category_id, cm.assigned FROM category_month cm 
     JOIN categories ca ON ca.id=cm.category_id 
     JOIN groups g ON g.id=ca.group_id 
     WHERE cm.month=? AND g.profile_id=?''', (prev_month, profile_id))
   for row in prev_assigned:
    if row['assigned'] > 0:
     c.execute('''INSERT INTO category_month(category_id, month, assigned) VALUES(?,?,?) 
       ON CONFLICT(category_id, month) DO UPDATE SET assigned=excluded.assigned''', 
       (row['category_id'], month, money(row['assigned'])))
     count += 1
  else: # underfunded : assigner selon la recommandation de cible
   b_list = budget(month=month, profile_id=profile_id)
   for cat in b_list:
    rec = cat.get('recommendation') or 0
    if rec > 0:
     new_val = money(cat.get('assigned', 0) + rec)
     c.execute('''INSERT INTO category_month(category_id, month, assigned) VALUES(?,?,?) 
       ON CONFLICT(category_id, month) DO UPDATE SET assigned=excluded.assigned''', 
       (cat['id'], month, new_val))
     count += 1
     
 return {'ok': True, 'count': count, 'mode': mode}

@app.get('/api/groups')
def groups(profile_id:int=1):
 with db() as c: return rows(c,'SELECT id,COALESCE(label,name) name,position,profile_id FROM groups WHERE profile_id=? ORDER BY position,name',(profile_id,))
@app.post('/api/groups')
def add_group(p:dict):
 with db() as c:
  pid=int(p.get('profile_id',1)); label=p['name'].strip(); internal=f'{pid}:{label}:{uuid.uuid4().hex[:6]}'
  return {'id':c.execute('INSERT INTO groups(name,label,profile_id,position) VALUES(?,?,?,?)',(internal,label,pid,p.get('position',99))).lastrowid}
@app.get('/api/categories')
def categories(profile_id:int=1):
 with db() as c: return rows(c,'SELECT c.*,COALESCE(g.label,g.name) group_name FROM categories c JOIN groups g ON g.id=c.group_id WHERE g.profile_id=? ORDER BY g.position,c.name',(profile_id,))
@app.patch('/api/categories/{cid}')
def patch_category(cid:int, p:dict):
 with db() as c:
  allowed = {'name', 'group_id', 'nature', 'saving_type', 'hidden'}
  vals = {k: p[k] for k in p if k in allowed}
  if not vals: return {'ok': True}
  c.execute('UPDATE categories SET ' + ','.join(k+'=?' for k in vals) + ' WHERE id=?', (*vals.values(), cid))
 return {'ok': True}

@app.delete('/api/categories/{cid}')
def delete_category(cid:int):
 with db() as c:
  tx_count = c.execute('SELECT COUNT(*) FROM transactions WHERE category_id=?', (cid,)).fetchone()[0]
  if tx_count > 0:
   raise HTTPException(400, f'Impossible de supprimer : {tx_count} transaction(s) sont encore associées à cette catégorie.')
  c.execute('DELETE FROM category_month WHERE category_id=?', (cid,))
  c.execute('DELETE FROM targets WHERE category_id=?', (cid,))
  c.execute('DELETE FROM categories WHERE id=?', (cid,))
 return {'ok': True}

@app.patch('/api/groups/{gid}')
def patch_group(gid:int, p:dict):
 with db() as c:
  allowed = {'label', 'position'}
  vals = {k: p[k] for k in p if k in allowed}
  if 'name' in p and 'label' not in vals: vals['label'] = p['name']
  if not vals: return {'ok': True}
  c.execute('UPDATE groups SET ' + ','.join(k+'=?' for k in vals) + ' WHERE id=?', (*vals.values(), gid))
 return {'ok': True}

@app.delete('/api/groups/{gid}')
def delete_group(gid:int):
 with db() as c:
  cat_count = c.execute('SELECT COUNT(*) FROM categories WHERE group_id=?', (gid,)).fetchone()[0]
  if cat_count > 0:
   raise HTTPException(400, f'Impossible de supprimer : ce groupe contient encore {cat_count} catégorie(s).')
  c.execute('DELETE FROM groups WHERE id=?', (gid,))
 return {'ok': True}

@app.post('/api/move-money')
def move_money(p:dict):
 from_cat = p.get('from_category_id')
 to_cat = p.get('to_category_id')
 month = p.get('month')
 amount = money(p.get('amount', 0))
 if amount <= 0 or not from_cat or not to_cat or from_cat == to_cat or not month:
  raise HTTPException(400, 'Paramètres de déplacement invalides')
 with db() as c:
  cur_from = c.execute('SELECT COALESCE(assigned,0) FROM category_month WHERE category_id=? AND month=?', (from_cat, month)).fetchone()
  cur_to = c.execute('SELECT COALESCE(assigned,0) FROM category_month WHERE category_id=? AND month=?', (to_cat, month)).fetchone()
  from_val = (cur_from[0] if cur_from else 0.0) - amount
  to_val = (cur_to[0] if cur_to else 0.0) + amount
  c.execute('INSERT INTO category_month(category_id,month,assigned) VALUES(?,?,?) ON CONFLICT(category_id,month) DO UPDATE SET assigned=excluded.assigned', (from_cat, month, money(from_val)))
  c.execute('INSERT INTO category_month(category_id,month,assigned) VALUES(?,?,?) ON CONFLICT(category_id,month) DO UPDATE SET assigned=excluded.assigned', (to_cat, month, money(to_val)))
 return {'ok': True, 'from_assigned': money(from_val), 'to_assigned': money(to_val)}

@app.post('/api/categories')
def add_category(p:dict):
 with db() as c: return {'id':c.execute('INSERT INTO categories(group_id,name,nature,saving_type) VALUES(?,?,?,?)',(p['group_id'],p['name'],p.get('nature','Dépense'),p.get('saving_type',''))).lastrowid}
@app.get('/api/accounts')
def accounts(profile_id:int=1):
 with db() as c:return rows(c,"SELECT a.*,round(a.opening_balance+COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.account_id=a.id),0),2) balance FROM accounts a WHERE a.profile_id=? ORDER BY closed,name",(profile_id,))
@app.post('/api/accounts')
def add_account(p:dict):
 with db() as c:return {'id':c.execute('INSERT INTO accounts(name,kind,opening_balance,profile_id) VALUES(?,?,?,?)',(p['name'],p.get('kind','checking'),money(p.get('opening_balance')),p.get('profile_id',1))).lastrowid}

@app.get('/api/transactions')
def transactions(account_id:Optional[int]=None, category_id:Optional[int]=None, q:str='', month:str='', profile_id:int=1):
 with db() as c:
  sql='''SELECT t.*,a.name account_name,c.name category_name FROM transactions t JOIN accounts a ON a.id=t.account_id LEFT JOIN categories c ON c.id=t.category_id WHERE a.profile_id=?'''; args=[profile_id]
  if account_id: sql+=' AND t.account_id=?';args.append(account_id)
  if category_id: sql+=' AND (t.category_id=? OR (t.splits!=\'[]\' AND EXISTS(SELECT 1 FROM json_each(t.splits) WHERE CAST(json_extract(value,\'$.category_id\') AS INTEGER)=?)))';args.extend([category_id, category_id])
  if month: sql+=' AND substr(t.tx_date,1,7)=?';args.append(month)
  if q: sql+=' AND (t.payee LIKE ? OR t.memo LIKE ? OR c.name LIKE ?)';args += ['%'+q+'%']*3
  return rows(c,sql+' ORDER BY t.tx_date DESC,t.id DESC LIMIT 500',args)
@app.post('/api/transactions/approve-all')
def approve_all(month:Optional[str]=None, profile_id:int=1):
 with db() as c:
  sql = 'UPDATE transactions SET approved=1 WHERE approved=0 AND account_id IN (SELECT id FROM accounts WHERE profile_id=?)'
  args = [profile_id]
  if month:
   sql += ' AND substr(tx_date, 1, 7)=?'
   args.append(month)
  cur = c.execute(sql, args)
  return {'approved_count': cur.rowcount}

@app.post('/api/transactions')
def add_transaction(p:dict):
 with db() as c:
  if p.get('transfer_account_id'):
   token=str(uuid.uuid4());p['transfer_id']=token; first=tx_create(c,p)
   second={**p,'account_id':p['transfer_account_id'],'transfer_account_id':p['account_id'],'amount':-money(p['amount']),'category_id':None,'splits':[],'transfer_id':token,'payee':'Transfert · '+p.get('payee',''),'approved':True};tx_create(c,second)
  else: first=tx_create(c,p)
  return {'id':first}
@app.patch('/api/transactions/{txid}')
def patch_transaction(txid:int,p:dict):
 allowed={'cleared','approved','flag','category_id','memo','payee'}
 vals={k:p[k] for k in p if k in allowed}
 if not vals: return {'ok':True}
 with db() as c:
  c.execute('UPDATE transactions SET '+','.join(k+'=?' for k in vals)+' WHERE id=?',(*vals.values(),txid))
 return {'ok':True}
@app.delete('/api/transactions/{txid}')
def delete_transaction(txid:int):
 with db() as c:
  t=c.execute('SELECT transfer_id FROM transactions WHERE id=?',(txid,)).fetchone()
  if not t: raise HTTPException(404,'Transaction introuvable')
  c.execute('DELETE FROM transactions WHERE '+('transfer_id=?' if t['transfer_id'] else 'id=?'),(t['transfer_id'] or txid,))
 return {'ok':True}

@app.post('/api/targets')
def target(p:dict):
 with db() as c:
  project_category_id=None
  if p['kind']=='project':
   source=c.execute('SELECT c.name,g.id group_id FROM categories c JOIN groups g ON g.id=c.group_id WHERE c.id=?',(p['category_id'],)).fetchone()
   reserve='Banque de projet · '+source['name']
   found=c.execute('SELECT id FROM categories WHERE group_id=? AND name=?',(source['group_id'],reserve)).fetchone()
   project_category_id=found['id'] if found else c.execute("INSERT INTO categories(group_id,name,nature,saving_type) VALUES(?,?,?,?)",(source['group_id'],reserve,'Épargne','Banque de projet')).lastrowid
  c.execute('''INSERT INTO targets(category_id,kind,amount,due_date,repeat_months,note,frequency,due_day,due_weekday,rollover_policy,project_category_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)
  ON CONFLICT(category_id) DO UPDATE SET kind=excluded.kind,amount=excluded.amount,due_date=excluded.due_date,repeat_months=excluded.repeat_months,note=excluded.note,frequency=excluded.frequency,due_day=excluded.due_day,due_weekday=excluded.due_weekday,rollover_policy=excluded.rollover_policy,project_category_id=COALESCE(excluded.project_category_id,targets.project_category_id)''',(p['category_id'],p['kind'],money(p['amount']),p.get('due_date'),p.get('repeat_months',1),p.get('note',''),p.get('frequency','monthly'),p.get('due_day'),p.get('due_weekday'),p.get('rollover_policy','carry'),project_category_id))
 return {'ok':True}
@app.get('/api/rules')
def rules(profile_id:int=1):
 with db() as c:return rows(c,'SELECT r.*,c.name category_name FROM rules r LEFT JOIN categories c ON c.id=r.category_id LEFT JOIN groups g ON g.id=c.group_id WHERE g.profile_id=? OR c.id IS NULL ORDER BY r.id DESC',(profile_id,))
@app.post('/api/rules')
def rule(p:dict):
 with db() as c:return {'id':c.execute('INSERT INTO rules(pattern,category_id,memo) VALUES(?,?,?)',(p['pattern'],p.get('category_id'),p.get('memo',''))).lastrowid}

@app.get('/api/payees')
def get_payees(profile_id:int=1):
 with db() as c:
  sql = '''SELECT t.payee as name, t.category_id, COUNT(*) as count 
           FROM transactions t 
           JOIN accounts a ON a.id=t.account_id 
           WHERE a.profile_id=? AND t.payee IS NOT NULL AND TRIM(t.payee)!='' 
           GROUP BY LOWER(TRIM(t.payee)) 
           ORDER BY count DESC, t.tx_date DESC LIMIT 300'''
  return rows(c, sql, (profile_id,))

def parse_ofx(raw):
 text=raw.decode('cp1252',errors='replace').replace('\r','')
 blocks=re.findall(r'<STMTTRN>(.*?)(?=<STMTTRN>|</BANKTRANLIST>)',text,re.S|re.I)
 def val(block,key):
  m=re.search(r'<'+key+r'>\s*([^<\n]+)',block,re.I);return m.group(1).strip() if m else ''
 result=[]
 for b in blocks:
  d=val(b,'DTPOSTED')[:8]; d=f'{d[:4]}-{d[4:6]}-{d[6:8]}' if len(d)==8 else date.today().isoformat()
  result.append({'imported_id':val(b,'FITID'),'tx_date':d,'amount':money(val(b,'TRNAMT').replace(',','.')),'payee':val(b,'NAME') or val(b,'MEMO'),'memo':val(b,'MEMO'),'cleared':True,'approved':False})
 return result
@app.post('/api/import/ofx')
async def import_ofx(account_id:int, file:UploadFile=File(...)):
 raw=await file.read(); parsed=parse_ofx(raw)
 if not parsed: raise HTTPException(400,'Aucune transaction OFX reconnue')
 added=dupes=0
 with db() as c:
  for p in parsed:
   exists=c.execute('SELECT 1 FROM transactions WHERE imported_id=?',(p['imported_id'],)).fetchone() if p['imported_id'] else c.execute('SELECT 1 FROM transactions WHERE account_id=? AND tx_date=? AND amount=? AND payee=?',(account_id,p['tx_date'],p['amount'],p['payee'])).fetchone()
   if exists: dupes+=1;continue
   r=apply_rules(c,p['payee']); p.update({'account_id':account_id,'category_id':r['category_id'] if r else None,'memo':(r['memo'] or p['memo']) if r else p['memo']});tx_create(c,p);added+=1
 return {'imported':added,'duplicates':dupes,'found':len(parsed)}

def clean_money_ynab(v):
    if not v: return 0.0
    v = v.replace('$', '').replace(' ', '').replace(',', '.')
    return round(float(v), 2)

def ynab_month_to_iso(m):
    m_map = {'Jan':'01','Feb':'02','Mar':'03','Apr':'04','May':'05','Jun':'06',
             'Jul':'07','Aug':'08','Sep':'09','Oct':'10','Nov':'11','Dec':'12'}
    p = m.strip().split()
    if len(p) == 2 and p[0] in m_map:
        return f'{p[1]}-{m_map[p[0]]}'
    return m.strip()

@app.post('/api/import/ynab')
async def import_ynab(profile_id: int, plan_file: UploadFile = File(...), register_file: Optional[UploadFile] = File(None)):
    plan_bytes = await plan_file.read()
    try:
        plan_text = plan_bytes.decode('utf-8-sig')
    except Exception:
        plan_text = plan_bytes.decode('cp1252', errors='replace')
    
    plan_reader = list(csv.DictReader(io.StringIO(plan_text)))
    if not plan_reader or 'Category Group' not in plan_reader[0] or 'Category' not in plan_reader[0]:
        raise HTTPException(400, "Le fichier Plan ne semble pas être un export CSV YNAB valide (colonnes requises: 'Category Group', 'Category').")
    
    reg_reader = []
    if register_file:
        reg_bytes = await register_file.read()
        try:
            reg_text = reg_bytes.decode('utf-8-sig')
        except Exception:
            reg_text = reg_bytes.decode('cp1252', errors='replace')
        reg_reader = list(csv.DictReader(io.StringIO(reg_text)))

    with db() as c:
        existing_groups = {g['label']: g['id'] for g in rows(c, "SELECT id, COALESCE(label, name) label FROM groups WHERE profile_id=?", (profile_id,))}
        existing_cats = {(cat['group_id'], cat['name']): cat['id'] for cat in rows(c, "SELECT c.id, c.group_id, c.name FROM categories c JOIN groups g ON g.id=c.group_id WHERE g.profile_id=?", (profile_id,))}
        
        max_pos = c.execute("SELECT COALESCE(MAX(position), 0) FROM groups WHERE profile_id=?", (profile_id,)).fetchone()[0]

        groups_map = dict(existing_groups)
        categories_map = dict(existing_cats)

        for r in plan_reader:
            g_name = (r.get('Category Group') or '').strip()
            c_name = (r.get('Category') or '').strip()
            if not g_name or not c_name:
                continue

            if g_name not in groups_map:
                max_pos += 1
                internal = f"{profile_id}:{g_name}:{uuid.uuid4().hex[:6]}"
                c.execute("INSERT INTO groups(name, label, profile_id, position) VALUES(?,?,?,?)",
                          (internal, g_name, profile_id, max_pos))
                gid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                groups_map[g_name] = gid
            gid = groups_map[g_name]

            if (gid, c_name) not in categories_map:
                nature = 'Épargne' if ('Épargne' in g_name or 'Réserve' in g_name or 'Savings' in g_name) else 'Dépense'
                c.execute("INSERT INTO categories(group_id, name, nature) VALUES(?,?,?)", (gid, c_name, nature))
                cid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                categories_map[(gid, c_name)] = cid

        assigned_count = 0
        for r in plan_reader:
            g_name = (r.get('Category Group') or '').strip()
            c_name = (r.get('Category') or '').strip()
            if not g_name or not c_name:
                continue
            gid = groups_map[g_name]
            cid = categories_map[(gid, c_name)]
            iso_m = ynab_month_to_iso(r.get('Month', ''))
            assigned = clean_money_ynab(r.get('Assigned', '0'))
            if assigned != 0:
                c.execute("INSERT INTO category_month(category_id, month, assigned) VALUES(?,?,?) ON CONFLICT(category_id, month) DO UPDATE SET assigned=excluded.assigned",
                          (cid, iso_m, assigned))
                assigned_count += 1

        tx_added = 0
        acc_created = 0

        if reg_reader:
            existing_accs = {a['name']: a['id'] for a in rows(c, "SELECT id, name FROM accounts WHERE profile_id=?", (profile_id,))}
            
            starting_balances = {}
            for r in reg_reader:
                if (r.get('Payee') or '').strip() == 'Starting Balance':
                    acc = (r.get('Account') or '').strip()
                    if acc:
                        starting_balances[acc] = clean_money_ynab(r.get('Inflow')) - clean_money_ynab(r.get('Outflow'))

            accounts_map = dict(existing_accs)
            for r in reg_reader:
                acc_name = (r.get('Account') or '').strip()
                if not acc_name or acc_name in accounts_map:
                    continue
                kind = 'credit' if any(k in acc_name.lower() for k in ['visa', 'mastercard', 'rogers', 'credit', 'carte']) else ('savings' if any(k in acc_name.lower() for k in ['épargne', 'epargne', 'trouv', 'savings']) else 'checking')
                op_bal = starting_balances.get(acc_name, 0.0)
                c.execute("INSERT INTO accounts(name, kind, opening_balance, profile_id) VALUES(?,?,?,?)",
                          (acc_name, kind, op_bal, profile_id))
                aid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
                accounts_map[acc_name] = aid
                acc_created += 1

            transfers_list = []
            for idx, r in enumerate(reg_reader):
                if (r.get('Payee') or '').strip().startswith('Transfer : '):
                    transfers_list.append((idx, r))

            transfer_tokens = {}
            for i, (idx1, t1) in enumerate(transfers_list):
                if idx1 in transfer_tokens: continue
                tgt = (t1.get('Payee') or '').strip()[11:].strip()
                for j, (idx2, t2) in enumerate(transfers_list):
                    if j == i or idx2 in transfer_tokens: continue
                    if (t2.get('Account') or '').strip() == tgt and (t2.get('Payee') or '').strip() == 'Transfer : ' + (t1.get('Account') or '').strip():
                        if t1.get('Date') == t2.get('Date') and t1.get('Outflow') == t2.get('Inflow') and t1.get('Inflow') == t2.get('Outflow'):
                            tok = str(uuid.uuid4())
                            transfer_tokens[idx1] = (tok, accounts_map.get(tgt))
                            transfer_tokens[idx2] = (tok, accounts_map.get((t1.get('Account') or '').strip()))
                            break

            for idx, r in enumerate(reg_reader):
                payee = (r.get('Payee') or '').strip()
                if payee == 'Starting Balance':
                    continue
                acc_name = (r.get('Account') or '').strip()
                if not acc_name or acc_name not in accounts_map:
                    continue
                aid = accounts_map[acc_name]
                d = (r.get('Date') or '').strip().replace('/', '-')
                outflow = clean_money_ynab(r.get('Outflow'))
                inflow = clean_money_ynab(r.get('Inflow'))
                amt = inflow - outflow
                cleared = 1 if r.get('Cleared') in ('Cleared', 'Reconciled') else 0
                memo = (r.get('Memo') or '').strip()
                flag = (r.get('Flag') or '').strip()

                g_name = (r.get('Category Group') or '').strip()
                c_name = (r.get('Category') or '').strip()
                cat_id = None
                if g_name and c_name and not (g_name == 'Inflow' and c_name == 'Ready to Assign'):
                    gid = groups_map.get(g_name)
                    if gid:
                        cat_id = categories_map.get((gid, c_name))

                transfer_tok, transfer_acc_id = transfer_tokens.get(idx, (None, None))
                
                exists = c.execute("SELECT 1 FROM transactions WHERE account_id=? AND tx_date=? AND amount=? AND payee=? AND memo=?",
                                   (aid, d, amt, payee, memo)).fetchone()
                if exists:
                    continue

                c.execute("INSERT INTO transactions(account_id, tx_date, payee, memo, amount, category_id, splits, transfer_account_id, transfer_id, cleared, approved, flag) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                          (aid, d, payee, memo, amt, cat_id, '[]', transfer_acc_id, transfer_tok, cleared, 1, flag))
                tx_added += 1

    return {
        'ok': True,
        'groups_imported': len(groups_map),
        'categories_imported': len(categories_map),
        'assigned_months_imported': assigned_count,
        'accounts_created': acc_created,
        'transactions_imported': tx_added
    }

@app.post('/api/reconcile')
def reconcile(p:dict):
 with db() as c:
  cleared=c.execute('SELECT COALESCE(SUM(amount),0) FROM transactions WHERE account_id=? AND cleared=1',(p['account_id'],)).fetchone()[0]+c.execute('SELECT opening_balance FROM accounts WHERE id=?',(p['account_id'],)).fetchone()[0]
  adjustment=money(p['statement_balance'])-cleared
  if adjustment and p.get('create_adjustment'): tx_create(c,{'account_id':p['account_id'],'tx_date':date.today().isoformat(),'payee':'Ajustement de rapprochement','memo':'Créé lors du rapprochement','amount':adjustment,'cleared':True,'approved':True})
  c.execute('INSERT INTO reconciliations(account_id,reconciled_on,statement_balance,cleared_balance,adjustment) VALUES(?,?,?,?,?)',(p['account_id'],date.today().isoformat(),p['statement_balance'],cleared,adjustment))
 return {'cleared_balance':money(cleared),'difference':money(adjustment)}

@app.get('/api/report')
def report(months:int=12,profile_id:int=1):
 cutoff=date.today().replace(day=1)
 with db() as c:
  tx=rows(c,"SELECT t.*,c.name category_name,COALESCE(g.label,g.name) group_name FROM transactions t JOIN accounts a ON a.id=t.account_id LEFT JOIN categories c ON c.id=t.category_id LEFT JOIN groups g ON g.id=c.group_id WHERE t.tx_date>=date(?,?) AND a.profile_id=?",(cutoff.isoformat(),f'-{months-1} months',profile_id))
  expenses={}; income={}; trend={}
  for t in tx:
   m=t['tx_date'][:7];trend.setdefault(m,{'income':0,'expenses':0})
   if t['amount']>0 and not t['category_id']: income[t['payee'] or 'Revenus']=income.get(t['payee'] or 'Revenus',0)+t['amount'];trend[m]['income']+=t['amount']
   for z in category_amount(t):
    if float(z['amount'])<0:
     key=t['category_name'] or 'Non catégorisé'; expenses[key]=expenses.get(key,0)-float(z['amount']);trend[m]['expenses']-=float(z['amount'])
  return {'expenses':expenses,'income':income,'trend':trend,'average_expense':money(sum(expenses.values())/max(1,months)),'net_worth':money(c.execute('SELECT COALESCE(SUM(opening_balance),0)+COALESCE((SELECT SUM(amount) FROM transactions WHERE account_id IN (SELECT id FROM accounts WHERE profile_id=?)),0) FROM accounts WHERE profile_id=?',(profile_id,profile_id)).fetchone()[0])}

@app.get('/api/backup')
def backup():
 target=ROOT/'backup-budget-libre.db';shutil.copy2(DB,target);return FileResponse(target,filename=f'budget-libre-{date.today()}.db')
@app.post('/api/restore')
async def restore(file:UploadFile=File(...)):
 raw=await file.read()
 if raw[:16]!=b'SQLite format 3\x00':raise HTTPException(400,'Fichier SQLite invalide')
 tmp=ROOT/'restore.tmp';tmp.write_bytes(raw)
 try:
  test=sqlite3.connect(tmp);test.execute('SELECT name FROM sqlite_master WHERE type="table" AND name="transactions"').fetchone();test.close();shutil.move(tmp,DB)
 except Exception: tmp.unlink(missing_ok=True);raise HTTPException(400,'Sauvegarde incompatible')
 return {'ok':True}

app.mount('/',StaticFiles(directory=Path(__file__).parent/'static',html=True),name='static')

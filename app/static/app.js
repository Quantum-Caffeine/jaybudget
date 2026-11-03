const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
let state={accounts:[],categories:[],groups:[],profiles:[],payees:[],currentAccountId:null,profile:+localStorage.getItem('budget-profile')||1,month:new Date().toISOString().slice(0,7)};
const api=async(u,o={})=>{let r=await fetch('/api/'+u,{headers:o.body instanceof FormData?{}:{'Content-Type':'application/json'},...o});if(!r.ok)throw new Error(await r.text());return r.headers.get('content-type')?.includes('json')?r.json():r};
const cash=n=>new Intl.NumberFormat('fr-CA',{style:'currency',currency:'CAD'}).format(n||0);
const esc=s=>String(s??'').replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
function openModal(id){$('#'+id).showModal()} window.openModal=openModal;
const qs=()=>`profile_id=${state.profile}`;

async function seed(){
  [state.profiles,state.accounts,state.categories,state.groups,state.payees]=await Promise.all([
    api('profiles'),api('accounts?'+qs()),api('categories?'+qs()),api('groups?'+qs()),api('payees?'+qs())
  ]);
  $('#profileSelect').innerHTML=state.profiles.map(p=>`<option value="${p.id}" ${p.id===state.profile?'selected':''}>${esc(p.name)}</option>`).join('');
  const accountOpts=state.accounts.map(a=>`<option value="${a.id}">${esc(a.name)} (${cash(a.balance)})</option>`).join('');
  $('#txAccount').innerHTML=accountOpts;
  $('#txTransfer').innerHTML='<option value="">Aucun</option>'+accountOpts;
  $('#txCategory').innerHTML='<option value="">Entrée à répartir</option>'+state.categories.map(c=>`<option value="${c.id}">${esc(c.group_name)} — ${esc(c.name)}</option>`).join('');
  $('#catGroup').innerHTML=state.groups.map(g=>`<option value="${g.id}">${esc(g.name)}</option>`).join('');
  $('#editCatGroup').innerHTML=state.groups.map(g=>`<option value="${g.id}">${esc(g.name)}</option>`).join('');
  
  // Remplir la liste d'autocomplétion des marchands
  if($('#payeesList')){
    $('#payeesList').innerHTML=state.payees.map(p=>`<option value="${esc(p.name)}">`).join('');
  }
  
    $('#txForm [name=tx_date]').value=new Date().toISOString().slice(0,10);
  updateSidebarAccounts();
}


function updateSidebarAccounts(){
  let el = $('#sidebarAccounts');
  if(!el) return;
  el.innerHTML = state.accounts.map(a => `
    <button class="sidebar-acc-btn ${state.currentAccountId === a.id ? 'active' : ''}" onclick="filterByAccount(${a.id})">
      <span class="sidebar-acc-name" title="${esc(a.name)}">${esc(a.name)}</span>
      <span class="sidebar-acc-bal ${a.balance < 0 ? 'bad' : 'good'}">${cash(a.balance)}</span>
    </button>
  `).join('');
}

window.filterByAccount = async function(accId){
  state.currentAccountId = accId;
  $$('aside button').forEach(x => x.classList.remove('active'));
  let btnTx = $('aside [data-page="transactions"]');
  if(btnTx) btnTx.classList.add('active');
  $$('.page').forEach(x => x.classList.add('hidden'));
  $('#transactions').classList.remove('hidden');
  document.body.classList.remove('nav-open');
  updateSidebarAccounts();
  await renderTransactions();
};

window.clearAccountFilter = async function(){
  state.currentAccountId = null;
  updateSidebarAccounts();
  await renderTransactions();
};

async function home(){
  let d=await api('dashboard?month='+state.month+'&'+qs());
  $('#summary').innerHTML=`À répartir <b class="${d.ready<0?'bad':'good'}">${cash(d.ready)}</b> · Patrimoine <b>${cash(d.net_worth)}</b>${d.age_of_money !== null ? ' · ⏳ Âge de l\'argent <b>' + d.age_of_money + ' j</b>' : ''}`;
}

function page(title,toolbar,content){
  return `<div class="toolbar"><h1>${title}</h1>${toolbar||''}</div>${content}`;
}

// -------------------------------------------------------------
// VUE BUDGET
// -------------------------------------------------------------
async function renderBudget(){
  let data=await api('budget?month='+state.month+'&'+qs()),
      d=await api('dashboard?month='+state.month+'&'+qs()),
      last=null, html='';

  for(const c of data){
    if(c.group_name!==last){
      last=c.group_name;
      html+=`<tr class="group-row"><td colspan="5">
        <span>${esc(last)}</span>
        <span class="group-actions">
          <button class="btn-icon" title="Modifier le groupe" onclick="editGroup(${c.group_id}, '${esc(last)}')">✏️</button>
        </span>
      </td></tr>`;
    }
    let target=c.target_amount?`<span class="target">${esc(c.target_kind)} · ${cash(c.target_amount)}<br>À assigner : <b>${cash(c.recommendation)}</b></span>`:'<button onclick="targetFor('+c.id+')">Cible</button>';
    
    html+=`<tr>
      <td>
        <b>${esc(c.name)}</b>
        <span class="cat-actions">
          <button class="btn-icon" title="Modifier la catégorie" onclick="editCategory(${c.id})">✏️</button>
        </span>
        <br><span class="small">${esc(c.nature)} ${c.saving_type?'· '+esc(c.saving_type):''}</span>
      </td>
      <td>${target}</td>
      <td class="number">
        <input class="assign" onchange="assign(${c.id},this.value)" value="${c.assigned}" type="number" step="0.01">
      </td>
      <td class="number ${c.activity<0?'bad':''}">
        <span class="clickable" title="Voir le détail des opérations du mois" onclick="showActivity(${c.id},'${esc(c.name)}')">${cash(c.activity)}</span>
      </td>
      <td class="number available">
        <div style="display:inline-flex;align-items:center;justify-content:flex-end;gap:5px">
          ${c.available < 0 ? (c.overspending_type === 'credit' ? '<span class="badge-pill badge-credit" title="Dépassement par carte de crédit">💳 Crédit</span>' : '<span class="badge-pill badge-cash" title="Dépassement en espèces / chèques">⚠️ Cash</span>') : ''}
          <span class="pill-avail ${c.available < 0 ? (c.overspending_type === 'credit' ? 'credit-overspent' : 'cash-overspent') : (c.available === 0 ? 'zero' : 'good')} clickable" 
                title="${c.available < 0 ? (c.overspending_type === 'credit' ? 'Dépassement par carte de crédit (dette non budgétée). Cliquer pour combler.' : 'Dépassement de liquidités (impacte le Prêt à répartir !). Cliquer pour combler.') : (c.available === 0 ? 'Solde nul. Cliquer pour déplacer.' : 'Disponible. Cliquer pour déplacer.')}" 
                onclick="openMoveMoney(${c.id},'${esc(c.name)}',${c.available})">${cash(c.available)}</span>
        </div>
      </td>
    </tr>`;
  }

  $('#budget').innerHTML=page('Budget',`
    <div style="display:flex;align-items:center;gap:6px">
      <button class="btn-icon" title="Mois précédent" onclick="shiftMonth(-1)">◀</button>
      <input type="month" value="${state.month}" onchange="state.month=this.value;renderBudget();home()" style="font-weight:600">
      <button class="btn-icon" title="Mois suivant" onclick="shiftMonth(1)">▶</button>
    </div>
    <div class="dropdown">
      <button type="button" class="btn-secondary" onclick="toggleQuickAssignMenu(event)" title="Options d'assignation automatique">⚡ Auto-assigner ▾</button>
      <div id="quickAssignMenu" class="dropdown-menu">
        <button type="button" class="dropdown-item" onclick="runQuickAssign('underfunded')">🎯 <b>Selon les cibles</b><br><span class="subtext">Combler le besoin des catégories</span></button>
        <button type="button" class="dropdown-item" onclick="runQuickAssign('last_month')">📋 <b>Copier le mois dernier</b><br><span class="subtext">Reprendre les assignations passées</span></button>
        <hr class="dropdown-divider">
        <button type="button" class="dropdown-item danger-item" onclick="runQuickAssign('reset')">🗑️ <b>Réinitialiser à zéro</b><br><span class="subtext">Effacer les assignations de ce mois</span></button>
        <hr class="dropdown-divider">
        <button type="button" class="dropdown-item" onclick="openModal('freshStartModal')" style="color:#b45309">🔄 <b>Repartir à neuf...</b><br><span class="subtext">Consolidation annuelle (Fresh Start)</span></button>
      </div>
    </div>
    <button class="primary" onclick="openModal('categoryModal')">➕ Catégorie</button>
    <button class="primary" onclick="openModal('txModal')">➕ Transaction</button>
  `, `
    <div class="metrics">
      <div class="metric"><span>Prêt à répartir</span><strong class="${d.ready<0?'bad':'good'}">${cash(d.ready)}</strong></div>
      <div class="metric" title="Temps moyen écoulé entre l'arrivée d'un dollar et sa dépense (Objectif YNAB: >30 jours)"><span>Âge de l'argent</span><strong>${d.age_of_money !== null ? d.age_of_money + ' jours' : '—'}</strong></div>
      <div class="metric"><span>Assigné ce mois</span><strong>${cash(data.reduce((a,c)=>a+c.assigned,0))}</strong></div>
      <div class="metric"><span>Disponible dans les catégories</span><strong>${cash(data.reduce((a,c)=>a+c.available,0))}</strong></div>
      <div class="metric"><span>Patrimoine</span><strong>${cash(d.net_worth)}</strong></div>
    </div>
    <div class="card">
      <table class="budget-table">
        <thead><tr><th>Catégorie</th><th>Cible</th><th class="number">Assigné</th><th class="number">Activité</th><th class="number">Disponible</th></tr></thead>
        <tbody>${html||'<tr><td colspan="5" class="empty">Créez vos catégories pour commencer.</td></tr>'}</tbody>
      </table>
    </div>
  `);
}

window.shiftMonth=function(offset){
  let [y,m]=state.month.split('-').map(Number);
  let d=new Date(y, m-1+offset, 1);
  state.month=d.toISOString().slice(0,7);
  renderBudget();
  home();
};

window.assign=async(id,value)=>{
  await api('assign',{method:'POST',body:JSON.stringify({category_id:id,month:state.month,assigned:value})});
  renderBudget();
  home();
};

window.toggleQuickAssignMenu=function(e){
  e.stopPropagation();
  let m=document.getElementById('quickAssignMenu');
  if(m) m.classList.toggle('show');
};

window.runQuickAssign=async function(mode){
  let m=document.getElementById('quickAssignMenu');
  if(m) m.classList.remove('show');
  
  if(mode==='reset'){
    if(!confirm(`Êtes-vous certain de vouloir réinitialiser toutes les assignations pour le mois ${state.month} ?`)) return;
  } else if(mode==='last_month'){
    if(!confirm(`Copier les montants assignés du mois précédent vers ${state.month} ?`)) return;
  }

  try {
    let res = await api('quick-assign', {
      method: 'POST',
      body: JSON.stringify({
        month: state.month,
        profile_id: state.profile || 1,
        mode: mode
      })
    });
    if(res.ok){
      await renderBudget();
      home();
    }
  } catch(err){
    alert('Erreur lors de l\'auto-assignation : '+err.message);
  }
};

document.addEventListener('click', ()=>{
  let m=document.getElementById('quickAssignMenu');
  if(m) m.classList.remove('show');
});

window.targetFor=id=>{$('#targetCategoryId').value=id;openModal('targetModal')};

// -------------------------------------------------------------
// GESTION DES CATÉGORIES & GROUPES
// -------------------------------------------------------------
window.editCategory=function(cid){
  let c=state.categories.find(x=>x.id===cid);
  if(!c)return;
  $('#editCatId').value=c.id;
  $('#editCatName').value=c.name;
  $('#editCatGroup').value=c.group_id;
  $('#editCatNature').value=c.nature||'Dépense';
  $('#editCatSavingType').value=c.saving_type||'';
  openModal('editCategoryModal');
};

$('#editCategoryForm').onsubmit=async e=>{
  e.preventDefault();
  let cid=+$('#editCatId').value;
  let p={
    name:$('#editCatName').value.trim(),
    group_id:+$('#editCatGroup').value,
    nature:$('#editCatNature').value,
    saving_type:$('#editCatSavingType').value.trim()
  };
  try{
    await api('categories/'+cid,{method:'PATCH',body:JSON.stringify(p)});
    $('#editCategoryModal').close();
    await seed();
    await renderBudget();
  }catch(err){
    alert('Erreur: '+err.message);
  }
};

$('#btnDeleteCat').onclick=async()=>{
  let cid=+$('#editCatId').value;
  let c=state.categories.find(x=>x.id===cid);
  let cname=c?c.name:'cette catégorie';
  if(!confirm(`Êtes-vous certain de vouloir supprimer la catégorie "${cname}" ?`)) return;
  try{
    await api('categories/'+cid,{method:'DELETE'});
    $('#editCategoryModal').close();
    await seed();
    await renderBudget();
    home();
  }catch(err){
    alert(err.message);
  }
};

window.editGroup=async function(gid, currentName){
  let newName=prompt('Nouveau nom pour ce groupe :', currentName);
  if(!newName || newName.trim()===currentName) return;
  try{
    await api('groups/'+gid,{method:'PATCH',body:JSON.stringify({name:newName.trim()})});
    await seed();
    await renderBudget();
  }catch(err){
    alert(err.message);
  }
};

// -------------------------------------------------------------
// DÉPLACER DE L'ARGENT (MOVE MONEY)
// -------------------------------------------------------------
window.openMoveMoney=function(fromCatId, fromCatName, currentAvailable){
  $('#moveFromCatId').value=fromCatId;
  $('#moveFromCatName').value=`${fromCatName} (Disponible: ${cash(currentAvailable)})`;
  $('#moveAmount').value=currentAvailable > 0 ? currentAvailable : '';
  $('#moveToCatId').innerHTML=state.categories
    .filter(c=>c.id!==fromCatId)
    .map(c=>`<option value="${c.id}">${esc(c.group_name)} — ${esc(c.name)}</option>`).join('');
  openModal('moveMoneyModal');
};

$('#moveMoneyForm').onsubmit=async e=>{
  e.preventDefault();
  let p={
    from_category_id:+$('#moveFromCatId').value,
    to_category_id:+$('#moveToCatId').value,
    amount:+$('#moveAmount').value,
    month:state.month
  };
  try{
    await api('move-money',{method:'POST',body:JSON.stringify(p)});
    $('#moveMoneyModal').close();
    await renderBudget();
    home();
  }catch(err){
    alert('Erreur: '+err.message);
  }
};

// -------------------------------------------------------------
// POPUP ACTIVITÉ DÉTAILLÉE
// -------------------------------------------------------------
window.showActivity=async function(catId, catName){
  $('#activityModalTitle').textContent=`Activité : ${catName}`;
  $('#activityModalSubtitle').textContent=`Toutes les opérations du mois (${state.month})`;
  $('#activityModalRows').innerHTML='<tr><td colspan="5" class="empty">Chargement...</td></tr>';
  openModal('activityModal');
  try{
    let txs=await api(`transactions?category_id=${catId}&month=${state.month}&${qs()}`);
    if(!txs.length){
      $('#activityModalRows').innerHTML='<tr><td colspan="5" class="empty">Aucune transaction pour ce mois.</td></tr>';
      return;
    }
    $('#activityModalRows').innerHTML=txs.map(t=>`<tr>
      <td>${t.tx_date}</td>
      <td>${esc(t.account_name)}</td>
      <td><b>${esc(t.payee||'—')}</b></td>
      <td><span class="small">${esc(t.memo||'')}</span></td>
      <td class="number ${t.amount<0?'bad':'good'}">${cash(t.amount)}</td>
    </tr>`).join('');
  }catch(err){
    $('#activityModalRows').innerHTML=`<tr><td colspan="5" class="empty bad">Erreur : ${err.message}</td></tr>`;
  }
};

// -------------------------------------------------------------
// VUE TRANSACTIONS AVEC CATÉGORISATION INLINE
// -------------------------------------------------------------
async function renderTransactions(){
  let url = 'transactions?month=' + state.month + '&' + qs();
  if(state.currentAccountId){
    url += '&account_id=' + state.currentAccountId;
  }
  let tx = await api(url);
  
  let unapprovedCount = tx.filter(t => !t.approved).length;
  let banner = '';
  if(unapprovedCount > 0){
    banner = `<div style="background:#fef3f2;border:1px solid #fecdca;color:#b42318;padding:10px 14px;border-radius:8px;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;">
      <span>⚠️ <b>${unapprovedCount} transaction(s)</b> en attente d'approbation pour ce filtre.</span>
      <button class="primary" style="background:#b42318;border-color:#b42318;padding:6px 12px;font-size:13px;" onclick="approveAll()">✅ Tout approuver</button>
    </div>`;
  }
  
  let currentAcc = state.accounts.find(a => a.id === state.currentAccountId);
  let title = currentAcc ? esc(currentAcc.name) : 'Toutes les transactions';
  let accountFilterBadge = currentAcc ? `
    <span class="tag" style="background:#e0f2fe;color:#0369a1;font-size:13px;padding:4px 8px;display:inline-flex;align-items:center;gap:6px;">
      Compte : <b>${esc(currentAcc.name)}</b> (Solde: ${cash(currentAcc.balance)})
      <button type="button" class="btn-icon" style="color:#0369a1;padding:0;" onclick="clearAccountFilter()" title="Afficher tous les comptes">✕</button>
    </span>
  ` : '';

  let rows = tx.map(t => {
    let catSelect = '';
    let splits = [];
    try { splits = JSON.parse(t.splits || '[]'); } catch(e){}
    
    if(t.transfer_account_id){
      catSelect = `<span class="tag">Transfert</span>`;
    }else if(splits && splits.length > 0){
      let splitDetails = splits.map(s => {
        let cat = state.categories.find(c => c.id === s.category_id);
        return `${cat ? cat.name : 'Catégorie inconnue'}: ${cash(s.amount)}`;
      }).join('&#10;');
      catSelect = `<span class="tag clickable" style="background:#e0f2fe;color:#0369a1;" title="${splitDetails}">✂️ Ventilée (${splits.length})</span>`;
    }else{
      catSelect = `<select class="cat-select-inline" onchange="patchTx(${t.id},{category_id:this.value?+this.value:null})">
        <option value="">Entrée à répartir</option>
        ${state.categories.map(c => `<option value="${c.id}" ${c.id === t.category_id ? 'selected' : ''}>${esc(c.group_name)} — ${esc(c.name)}</option>`).join('')}
      </select>`;
    }
    return `<tr>
      <td>${t.tx_date}</td>
      <td>${esc(t.account_name)}</td>
      <td><b>${esc(t.payee || '—')}</b>${t.memo ? '<br><span class="small">' + esc(t.memo) + '</span>' : ''}</td>
      <td>${catSelect}</td>
      <td class="number ${t.amount < 0 ? 'bad' : 'good'}">${cash(t.amount)}</td>
      <td>
        <input type="checkbox" ${t.cleared ? 'checked' : ''} onchange="patchTx(${t.id},{cleared:this.checked})" title="Compensée">
        <input type="checkbox" ${t.approved ? 'checked' : ''} onchange="patchTx(${t.id},{approved:this.checked})" title="Approuvée">
      </td>
      <td><button class="btn-icon danger" onclick="deleteTx(${t.id})" title="Supprimer la transaction">✕</button></td>
    </tr>`;
  }).join('');

  $('#transactions').innerHTML = page(title, `
    <div style="display:flex;align-items:center;gap:6px">
      <button class="btn-icon" title="Mois précédent" onclick="shiftTxMonth(-1)">◀</button>
      <input type="month" value="${state.month}" onchange="state.month=this.value;renderTransactions()" style="font-weight:600">
      <button class="btn-icon" title="Mois suivant" onclick="shiftTxMonth(1)">▶</button>
    </div>
    ${accountFilterBadge}
    <input id="searchTx" placeholder="Rechercher..." oninput="searchTx(this.value)">
    <button class="primary" onclick="openModal('txModal')">➕ Transaction</button>
  `, `
    ${banner}
    <div class="card">
      <table>
        <thead><tr><th>Date</th><th>Compte</th><th>Bénéficiaire</th><th>Catégorie</th><th class="number">Montant</th><th>État</th><th></th></tr></thead>
        <tbody id="txRows">${rows || '<tr><td colspan="7" class="empty">Aucune transaction pour ce mois.</td></tr>'}</tbody>
      </table>
    </div>
  `);
}


window.approveAll = async function(){
  try {
    let res = await api(`transactions/approve-all?month=${state.month}&${qs()}`, {method: 'POST'});
    await renderTransactions();
    home();
  } catch(err){
    alert('Erreur: ' + err.message);
  }
};

window.shiftTxMonth=function(offset){
  let [y,m]=state.month.split('-').map(Number);
  let d=new Date(y, m-1+offset, 1);
  state.month=d.toISOString().slice(0,7);
  renderTransactions();
};

window.searchTx=async q=>{
  let tx=await api('transactions?q='+encodeURIComponent(q)+'&'+qs());
  $('#txRows').innerHTML=tx.map(t=>{
    let catSelect='';
    if(t.transfer_account_id){
      catSelect=`<span class="tag">Transfert</span>`;
    }else{
      catSelect=`<select class="cat-select-inline" onchange="patchTx(${t.id},{category_id:this.value?+this.value:null})">
        <option value="">Entrée à répartir</option>
        ${state.categories.map(c=>`<option value="${c.id}" ${c.id===t.category_id?'selected':''}>${esc(c.group_name)} — ${esc(c.name)}</option>`).join('')}
      </select>`;
    }
    return `<tr>
      <td>${t.tx_date}</td>
      <td>${esc(t.account_name)}</td>
      <td><b>${esc(t.payee||'—')}</b>${t.memo?'<br><span class="small">'+esc(t.memo)+'</span>':''}</td>
      <td>${catSelect}</td>
      <td class="number ${t.amount<0?'bad':'good'}">${cash(t.amount)}</td>
      <td>
        <input type="checkbox" ${t.cleared?'checked':''} onchange="patchTx(${t.id},{cleared:this.checked})" title="Compensée">
        <input type="checkbox" ${t.approved?'checked':''} onchange="patchTx(${t.id},{approved:this.checked})" title="Approuvée">
      </td>
      <td><button class="btn-icon danger" onclick="deleteTx(${t.id})" title="Supprimer la transaction">✕</button></td>
    </tr>`;
  }).join('');
};

window.patchTx=async(id,p)=>{
  await api('transactions/'+id,{method:'PATCH',body:JSON.stringify(p)});
  home();
  renderBudget();
};

window.deleteTx=async id=>{
  if(confirm('Supprimer cette transaction ?')){
    await api('transactions/'+id,{method:'DELETE'});
    renderTransactions();
    home();
    renderBudget();
  }
};

// -------------------------------------------------------------
// VUE COMPTES & RAPPROCHEMENT
// -------------------------------------------------------------
async function renderAccounts(){
  let accounts=await api('accounts?'+qs());
  $('#accounts').innerHTML=page('Comptes',`<button class="primary" onclick="openModal('accountModal')">➕ Compte</button>`,`
    <div class="card">${accounts.map(a=>`
      <div class="account">
        <div>
          <b>${esc(a.name)}</b><br>
          <span class="small">${({checking:'Chèques',savings:'Épargne',cash:'Espèces',credit:'Carte de crédit',loan:'Prêt'})[a.kind]||a.kind}</span>
        </div>
        <strong class="${a.balance<0?'bad':'good'}">${cash(a.balance)}</strong>
        <button onclick="reconcile(${a.id},'${esc(a.name)}')">Rapprocher</button>
      </div>`).join('')||'<div class="empty">Ajoutez votre premier compte.</div>'}
    </div>
    <div class="card">
      <h2>Comptes et cartes</h2>
      <p>Les cartes de crédit utilisent un solde négatif. Enregistrez le paiement comme un transfert depuis votre compte courant vers la carte.</p>
    </div>
  `);
}

window.reconcile=async(id,name)=>{
  let statement_balance=prompt('Solde du relevé pour '+name);
  if(statement_balance===null)return;
  let d=await api('reconcile',{method:'POST',body:JSON.stringify({account_id:id,statement_balance,create_adjustment:false})});
  alert(`Solde compensé : ${cash(d.cleared_balance)}\nÉcart : ${cash(d.difference)}\nVous pouvez créer une transaction d'ajustement si nécessaire.`);
};

// -------------------------------------------------------------
// VUE RÈGLES & IMPORTS
// -------------------------------------------------------------
async function renderRules(){
  let rules=await api('rules?'+qs());
  $('#rules').innerHTML=page('Règles et imports','',`
  <div class="card">
    <h2>📥 Importer un budget complet YNAB (CSV)</h2>
    <p>Importe directement tes catégories, les budgets assignés mois par mois, tes comptes et l'ensemble de tes transactions depuis les exports YNAB.</p>
    <form id="ynabImportForm" class="formgrid">
      <label class="wide">Fichier Plan (ex: <i>... - Plan.csv</i>)<input name="plan_file" type="file" accept=".csv" required></label>
      <label class="wide">Fichier Registre / Transactions (optionnel, ex: <i>... - Register.csv</i>)<input name="register_file" type="file" accept=".csv"></label>
      <footer><button class="primary">Importer le Plan YNAB</button></footer>
    </form>
    <p id="ynabImportResult" style="font-weight:600;margin-top:10px"></p>
  </div>
  
  <div class="card">
    <h2>Importer un relevé bancaire OFX / QFX</h2>
    <p>Les opérations déjà importées sont écartées grâce à l'identifiant bancaire (FITID), avec un contrôle de secours sur date, montant et bénéficiaire.</p>
    <form id="importForm" class="formgrid">
      <label>Compte<select name="account_id">${state.accounts.map(a=>`<option value="${a.id}">${esc(a.name)}</option>`)}</select></label>
      <label>Fichier OFX/QFX<input name="file" type="file" accept=".ofx,.qfx" required></label>
      <footer><button class="primary">Importer</button></footer>
    </form>
    <p id="importResult"></p>
  </div>
  
  <div class="card">
    <h2>Règles de catégorisation</h2>
    <form id="ruleForm" class="formgrid">
      <label>Expression / mot à reconnaître<input name="pattern" required placeholder="COSTCO|IGA"></label>
      <label>Catégorie<select name="category_id"><option value="">Sans catégorie</option>${state.categories.map(c=>`<option value="${c.id}">${esc(c.group_name)} — ${esc(c.name)}</option>`)}</select></label>
      <footer><button class="primary">Créer la règle</button></footer>
    </form>
    <table>
      <thead><tr><th>Motif</th><th>Catégorie</th></tr></thead>
      <tbody>${rules.map(r=>`<tr><td>${esc(r.pattern)}</td><td>${esc(r.category_name||'—')}</td></tr>`).join('')}</tbody>
    </table>
  </div>`);
  
  $('#ynabImportForm').onsubmit=importYnab;
  $('#importForm').onsubmit=importOfx;
  $('#ruleForm').onsubmit=saveRule;
}

async function importYnab(e){
  e.preventDefault();
  let f=new FormData(e.target);
  let resEl=$('#ynabImportResult');
  resEl.textContent="Importation en cours...";
  try{
    let r=await fetch('/api/import/ynab?profile_id='+state.profile,{method:'POST',body:f});
    if(!r.ok){
      let err=await r.text();
      resEl.textContent="Erreur lors de l'import: "+err;
      return;
    }
    let d=await r.json();
    resEl.textContent=`Succès ! ${d.groups_imported} groupes, ${d.categories_imported} catégories, ${d.assigned_months_imported} assignations mensuelles, ${d.accounts_created} comptes créés et ${d.transactions_imported} transactions importées.`;
    await seed();
    await home();
    await renderBudget();
  }catch(err){
    resEl.textContent="Erreur réseau ou fichier: "+err.message;
  }
}

async function importOfx(e){
  e.preventDefault();
  let f=new FormData(e.target);
  let account=f.get('account_id');
  let r=await fetch('/api/import/ofx?account_id='+account,{method:'POST',body:f});
  let d=await r.json();
  $('#importResult').textContent=`${d.imported} opération(s) ajoutée(s), ${d.duplicates} doublon(s) ignorée(s) sur ${d.found}.`;
  home();
  renderBudget();
}

async function saveRule(e){
  e.preventDefault();
  let p=Object.fromEntries(new FormData(e.target));
  await api('rules',{method:'POST',body:JSON.stringify(p)});
  renderRules();
}

// -------------------------------------------------------------
// VUE RAPPORTS & PARAMÈTRES
// -------------------------------------------------------------
async function renderReports(){
  let r=await api('report?months=12&'+qs()), max=Math.max(1,...Object.values(r.expenses));
  let chart=Object.entries(r.expenses).sort((a,b)=>b[1]-a[1]).map(([n,v])=>`<div class="chart-row"><span>${esc(n)}</span><div class="bar"><i style="width:${v/max*100}%"></i></div><b class="number">${cash(v)}</b></div>`).join('');
  let trend=Object.entries(r.trend).map(([m,v])=>`<tr><td>${m}</td><td class="number good">${cash(v.income)}</td><td class="number bad">${cash(v.expenses)}</td><td class="number">${cash(v.income-v.expenses)}</td></tr>`).join('');
  $('#reports').innerHTML=page('Rapports','',`
    <div class="metrics">
      <div class="metric"><span>Patrimoine actuel</span><strong>${cash(r.net_worth)}</strong></div>
      <div class="metric"><span>Moyenne mensuelle des dépenses</span><strong class="bad">${cash(r.average_expense)}</strong></div>
      <div class="metric"><span>Sources de revenus</span><strong>${Object.keys(r.income).length}</strong></div>
      <div class="metric"><span>Catégories dépensées</span><strong>${Object.keys(r.expenses).length}</strong></div>
    </div>
    <div class="card"><h2>Dépenses par catégorie — 12 mois</h2>${chart||'<p class="empty">Pas encore de dépenses catégorisées.</p>'}</div>
    <div class="card"><h2>Flux mensuel</h2><table><thead><tr><th>Mois</th><th class="number">Revenus</th><th class="number">Dépenses</th><th class="number">Écart</th></tr></thead><tbody>${trend}</tbody></table></div>
  `);
}

async function renderSettings(){
  $('#settings').innerHTML=page('Données et sauvegardes','',`
    <div class="card" style="border-left:4px solid #b45309">
      <h2>🔄 Consolidation / Repartir à neuf (Fresh Start)</h2>
      <p>Commence une nouvelle année ou période propre sans traîner l'historique des anciennes transactions. Vos comptes, catégories et cibles sont conservés. Vos soldes bancaires actuels deviennent vos soldes de départ.</p>
      <button type="button" class="primary" style="background:#b45309;border-color:#b45309" onclick="openModal('freshStartModal')">Recommencer à neuf</button>
    </div>
    <div class="card">
      <h2>Sauvegarde</h2>
      <p>Télécharge une copie SQLite complète de ton budget. Conserve-la dans un emplacement sûr et chiffré.</p>
      <a href="/api/backup"><button class="primary">Télécharger la sauvegarde</button></a>
    </div>
    <div class="card">
      <h2>Restaurer une sauvegarde</h2>
      <p class="bad">La restauration remplace le budget actuel. Rafraîchis la page après confirmation.</p>
      <form id="restoreForm"><input type="file" name="file" accept=".db" required> <button>Restaurer</button></form>
    </div>
    <div class="card">
      <h2>Application installable</h2>
      <p>Budget Libre peut être installé depuis le menu du navigateur sur téléphone ou ordinateur. Les données restent sur ton serveur.</p>
    </div>
  `);
  $('#restoreForm').onsubmit=async e=>{
    e.preventDefault();
    if(!confirm('Remplacer le budget actuel ?'))return;
    let r=await fetch('/api/restore',{method:'POST',body:new FormData(e.target)});
    if(r.ok)location.reload();else alert(await r.text());
  };
}

const renders={budget:renderBudget,transactions:renderTransactions,accounts:renderAccounts,rules:renderRules,reports:renderReports,settings:renderSettings};

$$('aside [data-page]').forEach(b=>b.onclick=async()=>{
  $$('aside button').forEach(x=>x.classList.remove('active'));
  b.classList.add('active');
  if(b.dataset.page === 'transactions'){
    state.currentAccountId = null; // Voir tous les comptes par défaut
    updateSidebarAccounts();
  }
  $$('.page').forEach(x=>x.classList.add('hidden'));
  $('#'+b.dataset.page).classList.remove('hidden');
  document.body.classList.remove('nav-open');
  await renders[b.dataset.page]();
});

$$('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());

// -------------------------------------------------------------
// GESTION DES TRANSACTIONS VENTILÉES (SPLIT)
// -------------------------------------------------------------
let isSplitMode = false;

window.toggleSplitMode = function(enable){
  isSplitMode = enable;
  if(enable){
    $('#singleCatContainer').style.display = 'none';
    $('#txTransferLabel').style.display = 'none';
    $('#splitSection').style.display = 'block';
    if($('#splitRows').children.length === 0){
      addSplitRow();
      addSplitRow();
    }
    updateSplitCalculation();
  }else{
    $('#singleCatContainer').style.display = 'grid';
    $('#txTransferLabel').style.display = 'grid';
    $('#splitSection').style.display = 'none';
    $('#splitRows').innerHTML = '';
    $('#btnSaveTx').disabled = false;
  }
};

window.addSplitRow = function(catId=null, amount=''){
  let tr = document.createElement('tr');
  tr.innerHTML = `
    <td>
      <select class="split-cat" style="width:100%" required>
        <option value="">Sélectionner une catégorie...</option>
        ${state.categories.map(c=>`<option value="${c.id}" ${c.id===catId?'selected':''}>${esc(c.group_name)} — ${esc(c.name)}</option>`).join('')}
      </select>
    </td>
    <td>
      <input type="number" step="0.01" class="split-amt" value="${amount}" placeholder="0.00" style="width:100%;text-align:right" required oninput="updateSplitCalculation()">
    </td>
    <td>
      <button type="button" class="btn-icon danger" onclick="this.closest('tr').remove();updateSplitCalculation()">✕</button>
    </td>
  `;
  $('#splitRows').appendChild(tr);
  updateSplitCalculation();
};

window.updateSplitCalculation = function(){
  if(!isSplitMode) return;
  let totalTx = parseFloat($('#txAmount').value || 0);
  let rows = [...$$('#splitRows tr')];
  let sumSplits = rows.reduce((acc, tr) => {
    let v = parseFloat(tr.querySelector('.split-amt').value || 0);
    return acc + v;
  }, 0);
  
  let remaining = Math.round((totalTx - sumSplits) * 100) / 100;
  let ind = $('#splitBalanceIndicator');
  let btnSave = $('#btnSaveTx');
  
  if(Math.abs(remaining) < 0.001 && rows.length >= 2){
    ind.innerHTML = `<span style="color:var(--green)">✓ Équilibré (${cash(sumSplits)})</span>`;
    btnSave.disabled = false;
  }else{
    ind.innerHTML = `<span style="color:#b42318">Reste à répartir : ${cash(remaining)} (Total: ${cash(totalTx)})</span>`;
    btnSave.disabled = true;
  }
};


// Auto-remplissage de la catégorie basé sur le marchand
$('#txPayee')?.addEventListener('input', function(){
  let val = this.value.trim().toLowerCase();
  if(!val || isSplitMode) return;
  let match = state.payees.find(p => p.name.trim().toLowerCase() === val);
  if(match && match.category_id){
    $('#txCategory').value = match.category_id;
  }
});

$('#txAmount').oninput = function(){
  if(isSplitMode) updateSplitCalculation();
};

$('#txForm').onsubmit=async e=>{
  e.preventDefault();
  let p=Object.fromEntries(new FormData(e.target));
  p.cleared=$('#txForm [name=cleared]').checked;
  p.approved=$('#txForm [name=approved]').checked;
  ['account_id','category_id','transfer_account_id'].forEach(k=>p[k]=p[k]?+p[k]:null);
  
  if(isSplitMode){
    let rows = [...$$('#splitRows tr')];
    let splits = rows.map(tr => ({
      category_id: +tr.querySelector('.split-cat').value,
      amount: parseFloat(tr.querySelector('.split-amt').value || 0)
    })).filter(s => s.category_id && s.amount !== 0);
    p.splits = splits;
    p.category_id = null;
  }
  
  await api('transactions',{method:'POST',body:JSON.stringify(p)});
  $('#txModal').close();
  e.target.reset();
  toggleSplitMode(false);
  await seed();
  renderTransactions();
  renderBudget();
  home();
};

$('#categoryForm').onsubmit=async e=>{
  e.preventDefault();
  let p=Object.fromEntries(new FormData(e.target));
  p.group_id=+p.group_id;
  await api('categories',{method:'POST',body:JSON.stringify(p)});
  $('#categoryModal').close();
  e.target.reset();
  await seed();
  renderBudget();
};

$('#accountForm').onsubmit=async e=>{
  e.preventDefault();
  let p=Object.fromEntries(new FormData(e.target));
  p.profile_id=state.profile;
  await api('accounts',{method:'POST',body:JSON.stringify(p)});
  $('#accountModal').close();
  e.target.reset();
  await seed();
  await renderAccounts();
  await home();
};

$('#targetForm').onsubmit=async e=>{
  e.preventDefault();
  let p=Object.fromEntries(new FormData(e.target));
  ['category_id','due_day','due_weekday'].forEach(k=>p[k]=p[k]?+p[k]:null);
  await api('targets',{method:'POST',body:JSON.stringify(p)});
  $('#targetModal').close();
  await renderBudget();
};

$('#profileSelect').onchange=async e=>{
  state.profile=+e.target.value;
  localStorage.setItem('budget-profile',state.profile);
  await seed();
  await home();
  await renderBudget();
};

$('#newProfile').onclick=async()=>{
  let name=prompt('Nom du nouveau profil');
  if(!name)return;
  let p=await api('profiles',{method:'POST',body:JSON.stringify({name})});
  state.profile=p.id;
  localStorage.setItem('budget-profile',state.profile);
  await seed();
  await home();
  await renderBudget();
};

// -------------------------------------------------------------
// GESTION DU MODE SOMBRE / CLAIR
// -------------------------------------------------------------

// -------------------------------------------------------------
// CONSOLIDATION / REPARTIR À NEUF (FRESH START)
// -------------------------------------------------------------
window.confirmFreshStart = async function(){
  let modal = document.getElementById('freshStartModal');
  if(modal && modal.close) modal.close();
  
  if(!confirm('Êtes-vous certain de vouloir repartir à neuf ? Vos soldes bancaires actuels seront conservés comme soldes de départ, et les anciennes transactions seront archivées.')) return;
  
  try {
    let res = await api('fresh-start', {
      method: 'POST',
      body: JSON.stringify({ profile_id: state.profile || 1 })
    });
    if(res.ok){
      alert(`Consolidation réussie !\n\n- ${res.accounts_updated} compte(s) consolidé(s) avec leurs soldes bancaires réels.\n- Une sauvegarde de sécurité a été créée sur le serveur.\n- Vos catégories et cibles sont intactes, prêtes pour la nouvelle année.`);
      await seed();
      await home();
      await renderBudget();
      document.querySelector('aside button[data-page="budget"]')?.click();
    }
  } catch(err){
    alert('Erreur lors de la consolidation : ' + err.message);
  }
};
window.initTheme = function(){
  const saved = localStorage.getItem('budget-theme');
  const isDark = saved === 'dark' || (!saved && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  if(isDark){
    document.body.classList.add('dark');
    document.documentElement.classList.add('dark');
  } else {
    document.body.classList.remove('dark');
    document.documentElement.classList.remove('dark');
  }
  updateThemeIcon();
};

window.toggleTheme = function(){
  const isDark = document.body.classList.toggle('dark');
  if(isDark){
    document.documentElement.classList.add('dark');
    localStorage.setItem('budget-theme', 'dark');
  } else {
    document.documentElement.classList.remove('dark');
    localStorage.setItem('budget-theme', 'light');
  }
  updateThemeIcon();
};

function updateThemeIcon(){
  const btn = document.getElementById('themeToggle');
  if(btn){
    const isDark = document.body.classList.contains('dark');
    btn.textContent = isDark ? '☀️' : '🌙';
    btn.title = isDark ? 'Passer en mode clair' : 'Passer en mode sombre';
  }
}

(async()=>{
  initTheme();
  await seed();
  await home();
  await renderBudget();
  if('serviceWorker'in navigator)navigator.serviceWorker.register('/sw.js');
})().catch(e=>alert('Erreur : '+e.message));

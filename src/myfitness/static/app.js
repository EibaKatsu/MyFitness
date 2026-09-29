const state = { activities: [], weights: [], meals: [], syncs: [] };
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const localDate = (iso) => new Intl.DateTimeFormat('ja-JP', {dateStyle:'medium', timeStyle:'short'}).format(new Date(iso));
const toLocalInput = (iso = new Date().toISOString()) => {
  const date = new Date(iso); const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
};
const inputToIso = (value) => new Date(value).toISOString();
const optionalNumber = (id) => $(id).value === '' ? null : Number($(id).value);

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type':'application/json'}, ...options});
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try { const body = await response.json(); message = body.detail || message; } catch (_) {}
    throw new Error(Array.isArray(message) ? '入力内容を確認してください。' : message);
  }
  return response.status === 204 ? null : response.json();
}
function showMessage(message, error = false) {
  $('message').hidden = !message; $('message').textContent = message || '';
  $('message').style.background = error ? '#fee9e6' : '#e4f3eb';
}
function duration(seconds) {
  if (seconds == null) return '—'; const total = Math.round(seconds);
  const h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` : `${m}:${String(s).padStart(2,'0')}`;
}
function pace(row) {
  if (!row.distance_m || !row.duration_s) return '—';
  const sec = row.duration_s / (row.distance_m / 1000); if (!Number.isFinite(sec)) return '—';
  return `${Math.floor(sec/60)}:${String(Math.round(sec%60)).padStart(2,'0')} /km`;
}
function renderActivities() {
  const filter = $('activity-filter').value;
  const rows = state.activities.filter(a => filter === 'all' || a.activity_type === filter);
  $('activities-body').innerHTML = rows.length ? rows.map(a => `<tr><td>${esc(localDate(a.start_time))}</td><td>${esc(a.activity_type_label || a.activity_type)}</td><td>${a.distance_m == null ? '—' : (a.distance_m/1000).toFixed(2)+' km'}</td><td>${duration(a.duration_s)}</td><td>${pace(a)}</td><td>${a.avg_hr == null ? '—' : esc(a.avg_hr)+' bpm'}</td></tr>`).join('') : '<tr><td colspan="6" class="muted">表示する活動がありません。</td></tr>';
}
function renderWeights() {
  $('weights-list').innerHTML = state.weights.length ? state.weights.map(w => `<article class="entry-item"><div><span class="muted">${esc(localDate(w.recorded_at))}</span><strong>${Number(w.weight_kg).toFixed(1)} kg</strong><span>${esc(w.note || '')}</span></div><div class="item-actions"><button data-edit-weight="${esc(w.id)}" class="secondary">編集</button><button data-delete-weight="${esc(w.id)}" class="danger">削除</button></div></article>`).join('') : '<p class="muted">記録はまだありません。</p>';
}
const mealNames = {breakfast:'朝食', lunch:'昼食', dinner:'夕食', snack:'間食', other:'その他'};
function renderMeals() {
  $('meals-list').innerHTML = state.meals.length ? state.meals.map(m => { const nutrients = [['kcal',m.calories_kcal],['P',m.protein_g],['F',m.fat_g],['C',m.carbs_g]].filter(x => x[1] != null).map(x => `${x[0]} ${x[1]}`).join(' / '); return `<article class="entry-item"><div><span class="muted">${esc(localDate(m.recorded_at))} · ${esc(mealNames[m.meal_type] || m.meal_type)}</span><strong>${esc(m.description)}</strong><span class="muted">${esc(nutrients)}</span></div><div class="item-actions"><button data-edit-meal="${esc(m.id)}" class="secondary">編集</button><button data-delete-meal="${esc(m.id)}" class="danger">削除</button></div></article>`; }).join('') : '<p class="muted">記録はまだありません。</p>';
}
function renderSync() {
  const last = state.syncs[0];
  $('last-sync').textContent = last ? `最終同期: ${localDate(last.started_at)} / ${last.status === 'success' ? '成功' : last.status === 'failed' ? '失敗' : '処理中'}` : '同期履歴はありません。';
}
async function loadDashboard() {
  try { Object.assign(state, await api('/api/dashboard')); renderActivities(); renderWeights(); renderMeals(); renderSync(); showMessage(''); }
  catch (error) { showMessage(error.message, true); }
}
function resetWeight() { $('weight-form').reset(); $('weight-id').value=''; $('weight-at').value=toLocalInput(); $('weight-cancel').hidden=true; }
function resetMeal() { $('meal-form').reset(); $('meal-id').value=''; $('meal-at').value=toLocalInput(); $('meal-cancel').hidden=true; }

$('sync-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const button=$('sync-button'); button.disabled=true; button.textContent='同期中…'; $('sync-result').textContent='Garminへ接続しています。画面を閉じずにお待ちください。';
  try { const r=await api('/api/sync',{method:'POST',body:JSON.stringify({start_date:$('sync-start').value,end_date:$('sync-end').value})}); $('sync-result').textContent=`完了: 追加 ${r.added_count}件 / 更新 ${r.updated_count}件 / スキップ ${r.skipped_count}件`; await loadDashboard(); }
  catch(error) { $('sync-result').textContent=`失敗: ${error.message}`; showMessage(error.message,true); }
  finally { button.disabled=false; button.textContent='活動データ取得'; }
});
$('weight-form').addEventListener('submit', async (event) => { event.preventDefault(); const id=$('weight-id').value; const body={recorded_at:inputToIso($('weight-at').value),weight_kg:Number($('weight-kg').value),note:$('weight-note').value||null}; try { await api(id?`/api/weights/${id}`:'/api/weights',{method:id?'PUT':'POST',body:JSON.stringify(body)}); resetWeight(); await loadDashboard(); } catch(error){showMessage(error.message,true);} });
$('meal-form').addEventListener('submit', async (event) => { event.preventDefault(); const id=$('meal-id').value; const body={recorded_at:inputToIso($('meal-at').value),meal_type:$('meal-type').value,description:$('meal-description').value,calories_kcal:optionalNumber('meal-calories'),protein_g:optionalNumber('meal-protein'),fat_g:optionalNumber('meal-fat'),carbs_g:optionalNumber('meal-carbs')}; try { await api(id?`/api/meals/${id}`:'/api/meals',{method:id?'PUT':'POST',body:JSON.stringify(body)}); resetMeal(); await loadDashboard(); } catch(error){showMessage(error.message,true);} });
document.addEventListener('click', async (event) => {
  const target=event.target; const weightId=target.dataset.editWeight, deleteWeight=target.dataset.deleteWeight, mealId=target.dataset.editMeal, deleteMeal=target.dataset.deleteMeal;
  if(weightId){const w=state.weights.find(x=>x.id===weightId); $('weight-id').value=w.id; $('weight-at').value=toLocalInput(w.recorded_at); $('weight-kg').value=w.weight_kg; $('weight-note').value=w.note||''; $('weight-cancel').hidden=false;}
  if(mealId){const m=state.meals.find(x=>x.id===mealId); $('meal-id').value=m.id; $('meal-at').value=toLocalInput(m.recorded_at); $('meal-type').value=m.meal_type; $('meal-description').value=m.description; $('meal-calories').value=m.calories_kcal??''; $('meal-protein').value=m.protein_g??''; $('meal-fat').value=m.fat_g??''; $('meal-carbs').value=m.carbs_g??''; $('meal-cancel').hidden=false;}
  if(deleteWeight && confirm('この体重記録を削除しますか？')){try{await api(`/api/weights/${deleteWeight}`,{method:'DELETE'});await loadDashboard();}catch(error){showMessage(error.message,true);}}
  if(deleteMeal && confirm('この食事記録を削除しますか？')){try{await api(`/api/meals/${deleteMeal}`,{method:'DELETE'});await loadDashboard();}catch(error){showMessage(error.message,true);}}
});
$('weight-cancel').addEventListener('click',resetWeight); $('meal-cancel').addEventListener('click',resetMeal); $('activity-filter').addEventListener('change',renderActivities); $('reload').addEventListener('click',loadDashboard);
const today=new Date(); const start=new Date(today); start.setDate(start.getDate()-89); $('sync-end').value=today.toISOString().slice(0,10); $('sync-start').value=start.toISOString().slice(0,10); resetWeight(); resetMeal(); loadDashboard();

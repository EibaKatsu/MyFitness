const state = { activities: [], weights: [], meals: [], syncs: [], growth: null };
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(
  /[&<>'"]/g,
  (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char],
);
const localDate = (iso) => new Intl.DateTimeFormat('ja-JP', {
  dateStyle: 'medium', timeStyle: 'short',
}).format(new Date(iso));
const shortDate = (iso) => new Intl.DateTimeFormat('ja-JP', {
  month: 'numeric', day: 'numeric',
}).format(new Date(iso));
const toLocalInput = (iso = new Date().toISOString()) => {
  const date = new Date(iso);
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
};
const inputToIso = (value) => new Date(value).toISOString();
const optionalNumber = (id) => $(id).value === '' ? null : Number($(id).value);
const optionalText = (id) => $(id).value.trim() || null;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' }, ...options,
  });
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch (_) { /* The status is enough when a non-JSON proxy response is returned. */ }
    throw new Error(Array.isArray(message) ? '入力内容を確認してください。' : message);
  }
  return response.status === 204 ? null : response.json();
}

function showMessage(message, error = false) {
  $('message').hidden = !message;
  $('message').textContent = message || '';
  $('message').style.background = error ? '#fee9e6' : '#e4f3eb';
}

function duration(seconds) {
  if (seconds == null) return '—';
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const rest = total % 60;
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
    : `${minutes}:${String(rest).padStart(2, '0')}`;
}

function paceFor(distanceM, durationS) {
  if (!distanceM || !durationS) return '—';
  const seconds = Math.round(durationS / (distanceM / 1000));
  if (!Number.isFinite(seconds)) return '—';
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} /km`;
}

function renderActivities() {
  const filter = $('activity-filter').value;
  const rows = state.activities.filter(
    (activity) => filter === 'all' || activity.activity_type === filter,
  );
  $('activities-body').innerHTML = rows.length ? rows.map((activity) => `
    <tr>
      <td>${esc(localDate(activity.start_time))}</td>
      <td>${esc(activity.activity_type_label || activity.activity_type)}</td>
      <td>${activity.distance_m == null ? '—' : `${(activity.distance_m / 1000).toFixed(2)} km`}</td>
      <td>${duration(activity.duration_s)}</td>
      <td>${paceFor(activity.distance_m, activity.duration_s)}</td>
      <td>${activity.avg_hr == null ? '—' : `${esc(activity.avg_hr)} bpm`}</td>
      <td><button class="secondary detail-button" data-activity-detail="${esc(activity.id)}">詳細</button></td>
    </tr>`).join('') : '<tr><td colspan="7" class="muted">表示する活動がありません。</td></tr>';
}

function renderWeights() {
  $('weights-list').innerHTML = state.weights.length ? state.weights.map((weight) => `
    <article class="entry-item"><div>
      <span class="muted">${esc(localDate(weight.recorded_at))}</span>
      <strong>${Number(weight.weight_kg).toFixed(1)} kg</strong><span>${esc(weight.note || '')}</span>
    </div><div class="item-actions">
      <button data-edit-weight="${esc(weight.id)}" class="secondary">編集</button>
      <button data-delete-weight="${esc(weight.id)}" class="danger">削除</button>
    </div></article>`).join('') : '<p class="muted">記録はまだありません。</p>';
}

const mealNames = {
  breakfast: '朝食', lunch: '昼食', dinner: '夕食', snack: '間食', other: 'その他',
};
function renderMeals() {
  $('meals-list').innerHTML = state.meals.length ? state.meals.map((meal) => {
    const nutrients = [
      ['kcal', meal.calories_kcal], ['P', meal.protein_g],
      ['F', meal.fat_g], ['C', meal.carbs_g],
    ].filter((item) => item[1] != null).map((item) => `${item[0]} ${item[1]}`).join(' / ');
    return `<article class="entry-item"><div>
      <span class="muted">${esc(localDate(meal.recorded_at))} · ${esc(mealNames[meal.meal_type] || meal.meal_type)}</span>
      <strong>${esc(meal.description)}</strong><span class="muted">${esc(nutrients)}</span>
    </div><div class="item-actions">
      <button data-edit-meal="${esc(meal.id)}" class="secondary">編集</button>
      <button data-delete-meal="${esc(meal.id)}" class="danger">削除</button>
    </div></article>`;
  }).join('') : '<p class="muted">記録はまだありません。</p>';
}

function renderSync() {
  const last = state.syncs[0];
  const names = { success: '成功', failed: '失敗', running: '処理中' };
  $('last-sync').textContent = last
    ? `最終同期: ${localDate(last.started_at)} / ${names[last.status] || last.status}`
    : '同期履歴はありません。';
}

async function loadDashboard() {
  try {
    Object.assign(state, await api('/api/dashboard'));
    renderActivities(); renderWeights(); renderMeals(); renderSync();
    await loadGrowth();
    showMessage('');
  } catch (error) {
    showMessage(error.message, true);
  }
}

const metricConfig = {
  efficiency_index: { label: '有酸素効率指数', unit: '', baseline: 100 },
  weekly_distance_km: { label: '週間走行距離', unit: 'km' },
  weekly_elevation_m: { label: '週間獲得標高', unit: 'm' },
  decoupling_pct: { label: '心拍ドリフト', unit: '%' },
};

async function loadGrowth() {
  const days = $('growth-period').value;
  state.growth = await api(`/api/analytics/growth?period_days=${days}`);
  renderGrowth();
}

function renderGrowth() {
  const metric = $('growth-metric').value;
  const config = metricConfig[metric];
  const points = (state.growth?.points || []).filter((point) => point[metric] != null);
  $('growth-definition').textContent = state.growth?.definitions?.[metric] || '';
  if (!points.length) {
    $('growth-chart').innerHTML = '<text x="450" y="160" text-anchor="middle" class="chart-axis">表示に必要な活動データがありません</text>';
    $('growth-summary').textContent = '同期を行うと推移が表示されます。';
    return;
  }
  const latest = points[points.length - 1][metric];
  if (metric === 'efficiency_index') {
    const change = latest - 100;
    $('growth-summary').textContent = `現在 ${latest.toFixed(1)}　基準比 ${change >= 0 ? '+' : ''}${change.toFixed(1)}%　対象 ${state.growth.eligible_activity_count}件`;
  } else {
    $('growth-summary').textContent = `直近 ${latest.toLocaleString('ja-JP')} ${config.unit}`;
  }
  drawLineChart(points, metric, config);
}

function drawLineChart(points, metric, config) {
  const svg = $('growth-chart');
  const width = 900; const height = 330;
  const margin = { left: 72, right: 24, top: 22, bottom: 58 };
  const plotW = width - margin.left - margin.right;
  const plotH = height - margin.top - margin.bottom;
  const dates = points.map((point) => new Date(point.date).getTime());
  const values = points.map((point) => Number(point[metric]));
  let xMin = Math.min(...dates); let xMax = Math.max(...dates);
  if (xMin === xMax) { xMin -= 7 * 86400000; xMax += 7 * 86400000; }
  let yMin = Math.min(...values); let yMax = Math.max(...values);
  if (config.baseline != null) {
    yMin = Math.min(yMin, config.baseline); yMax = Math.max(yMax, config.baseline);
  }
  const padding = Math.max((yMax - yMin) * 0.15, metric === 'efficiency_index' ? 2 : 1);
  yMin -= padding; yMax += padding;
  const x = (value) => margin.left + ((value - xMin) / (xMax - xMin)) * plotW;
  const y = (value) => margin.top + (1 - ((value - yMin) / (yMax - yMin))) * plotH;
  const yTicks = Array.from({ length: 5 }, (_, index) => yMin + ((yMax - yMin) * index) / 4);
  const xTickCount = Math.min(5, points.length);
  const xTicks = Array.from({ length: xTickCount }, (_, index) => (
    xMin + ((xMax - xMin) * index) / Math.max(xTickCount - 1, 1)
  ));
  const path = points.map((point, index) => `${index ? 'L' : 'M'} ${x(dates[index]).toFixed(1)} ${y(point[metric]).toFixed(1)}`).join(' ');
  const baseline = config.baseline == null ? '' : `<line class="chart-baseline" x1="${margin.left}" x2="${width - margin.right}" y1="${y(config.baseline)}" y2="${y(config.baseline)}"/><text class="chart-axis" x="${width - margin.right - 4}" y="${y(config.baseline) - 7}" text-anchor="end">基準 100</text>`;
  svg.innerHTML = `
    <rect class="chart-frame" x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}"/>
    ${yTicks.map((tick) => `<line class="chart-grid" x1="${margin.left}" x2="${width - margin.right}" y1="${y(tick)}" y2="${y(tick)}"/><text class="chart-axis" x="${margin.left - 10}" y="${y(tick) + 4}" text-anchor="end">${tick.toFixed(metric === 'weekly_elevation_m' ? 0 : 1)}</text>`).join('')}
    ${xTicks.map((tick) => `<text class="chart-axis" x="${x(tick)}" y="${height - 28}" text-anchor="middle">${shortDate(new Date(tick).toISOString())}</text>`).join('')}
    ${baseline}<path class="chart-line" d="${path}"/>
    ${points.map((point, index) => `<circle class="chart-point" tabindex="0" data-chart-index="${index}" cx="${x(dates[index])}" cy="${y(point[metric])}" r="5"/>`).join('')}
    <text class="chart-axis-title" x="${margin.left + plotW / 2}" y="${height - 5}" text-anchor="middle">期間</text>
    <text class="chart-axis-title" transform="translate(17 ${margin.top + plotH / 2}) rotate(-90)" text-anchor="middle">${esc(config.label)}${config.unit ? ` (${config.unit})` : ''}</text>`;
  svg.querySelectorAll('[data-chart-index]').forEach((element) => {
    const show = () => showChartTooltip(
      element, points[Number(element.dataset.chartIndex)], metric, config,
    );
    element.addEventListener('mouseenter', show); element.addEventListener('focus', show);
    element.addEventListener('mouseleave', hideChartTooltip);
    element.addEventListener('blur', hideChartTooltip);
  });
}

function showChartTooltip(element, point, metric, config) {
  const tooltip = $('chart-tooltip');
  const svg = $('growth-chart');
  const scale = svg.clientWidth / 900;
  tooltip.textContent = `${point.date}　${point[metric]}${config.unit}`;
  tooltip.style.left = `${Number(element.getAttribute('cx')) * scale}px`;
  tooltip.style.top = `${Number(element.getAttribute('cy')) * scale}px`;
  tooltip.hidden = false;
}
function hideChartTooltip() { $('chart-tooltip').hidden = true; }

async function openActivityDetail(id) {
  const dialog = $('activity-dialog');
  $('detail-title').textContent = '読み込み中…'; $('detail-summary').innerHTML = '';
  $('detail-status').hidden = true; dialog.showModal();
  try { renderActivityDetail(await api(`/api/activities/${id}`)); }
  catch (error) { $('detail-status').hidden = false; $('detail-status').textContent = error.message; }
}

function metricCard(label, value) {
  return `<div class="metric-card"><span>${esc(label)}</span><strong>${esc(value ?? '—')}</strong></div>`;
}

function renderActivityDetail(detail) {
  const activity = detail.activity;
  $('detail-title').textContent = activity.activity_name || '活動詳細';
  const detailStatus = activity.details_synced_at
    ? activity.detail_sync_error
    : (activity.detail_sync_error || '詳細データは未取得です。「活動データ取得」を再実行してください。');
  $('detail-status').hidden = !detailStatus;
  $('detail-status').textContent = detailStatus || '';
  $('detail-summary').innerHTML = [
    metricCard('日時', localDate(activity.start_time)),
    metricCard('距離', activity.distance_m == null ? '—' : `${(activity.distance_m / 1000).toFixed(2)} km`),
    metricCard('経過時間', duration(activity.elapsed_duration_s || activity.duration_s)),
    metricCard('平均ペース', paceFor(activity.distance_m, activity.duration_s)),
    metricCard('平均 / 最大心拍', activity.avg_hr == null ? '—' : `${activity.avg_hr} / ${activity.max_hr ?? '—'} bpm`),
    metricCard('獲得 / 下降標高', `${activity.elevation_gain_m ?? '—'} / ${activity.elevation_loss_m ?? '—'} m`),
    metricCard('平均ケイデンス', activity.avg_run_cadence_spm == null ? '—' : `${Math.round(activity.avg_run_cadence_spm)} spm`),
    metricCard('平均パワー', activity.avg_power_w == null ? '—' : `${Math.round(activity.avg_power_w)} W`),
    metricCard('有酸素 / 無酸素TE', `${activity.training_effect ?? '—'} / ${activity.anaerobic_training_effect ?? '—'}`),
    metricCard('トレーニング負荷', activity.activity_training_load == null
      ? '—' : Number(activity.activity_training_load).toFixed(1)),
    metricCard('心拍ドリフト', activity.aerobic_decoupling_pct == null ? '—' : `${Number(activity.aerobic_decoupling_pct).toFixed(1)} %`),
    metricCard('時系列データ', `${detail.samples.length} 点`),
  ].join('');
  renderZones(detail.hr_zones); renderContext(detail.weather, detail.gear);
  renderLaps(detail.laps); fillAnnotation(activity.id, detail.annotation || {});
}

function renderZones(zones) {
  const total = zones.reduce((sum, zone) => sum + Number(zone.seconds_in_zone || 0), 0);
  $('detail-zones').innerHTML = zones.length ? zones.map((zone) => {
    const percent = total ? Number(zone.seconds_in_zone || 0) / total * 100 : 0;
    return `<div class="zone-row"><strong>Z${esc(zone.zone_number)}</strong><div class="zone-bar"><i style="width:${percent.toFixed(1)}%"></i></div><span>${duration(zone.seconds_in_zone)}</span></div>`;
  }).join('') : '<p class="muted">心拍ゾーンデータはありません。</p>';
}

function renderContext(weather, gear) {
  const rows = [];
  if (weather) {
    rows.push(`天候: ${esc(weather.weather_description || '—')}`);
    rows.push(`気温（Garmin値）: ${weather.temperature_raw ?? '—'} / 湿度: ${weather.relative_humidity_pct ?? '—'}%`);
    rows.push(`風速（Garmin値）: ${weather.wind_speed_raw ?? '—'} ${esc(weather.wind_direction_compass || '')}`);
  }
  if (gear.length) {
    rows.push(`ギア: ${gear.map((item) => esc(item.display_name || item.model || item.gear_type)).join(', ')}`);
  }
  $('detail-context').innerHTML = rows.length
    ? rows.map((row) => `<div>${row}</div>`).join('')
    : '<p class="muted">天候・ギアデータはありません。</p>';
}

function renderLaps(laps) {
  $('detail-laps').innerHTML = laps.length ? laps.map((lap) => `<tr>
    <td>${esc(lap.lap_index)}</td><td>${lap.distance_m == null ? '—' : `${(lap.distance_m / 1000).toFixed(2)} km`}</td>
    <td>${duration(lap.duration_s)}</td><td>${paceFor(lap.distance_m, lap.duration_s)}</td>
    <td>${lap.avg_hr ?? '—'}</td><td>${lap.elevation_gain_m ?? '—'} m</td>
  </tr>`).join('') : '<tr><td colspan="6" class="muted">ラップデータはありません。</td></tr>';
}

function fillAnnotation(activityId, annotation) {
  $('annotation-activity-id').value = activityId;
  $('annotation-category').value = annotation.training_category || '';
  $('annotation-rpe').value = annotation.session_rpe ?? '';
  $('annotation-fatigue').value = annotation.fatigue_score ?? '';
  $('annotation-pain').value = annotation.pain_score ?? '';
  $('annotation-surface').value = annotation.surface || '';
  $('annotation-completion').value = annotation.completion_status || '';
  $('annotation-race').checked = Boolean(annotation.is_race);
  $('annotation-goal').value = annotation.training_goal || '';
  $('annotation-notes').value = annotation.notes || '';
}

function resetWeight() {
  $('weight-form').reset(); $('weight-id').value = '';
  $('weight-at').value = toLocalInput(); $('weight-cancel').hidden = true;
}
function resetMeal() {
  $('meal-form').reset(); $('meal-id').value = '';
  $('meal-at').value = toLocalInput(); $('meal-cancel').hidden = true;
}

$('sync-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const button = $('sync-button'); button.disabled = true; button.textContent = '同期中…';
  $('sync-result').textContent = 'Garminへ接続しています。詳細取得には数分かかる場合があります。';
  try {
    const result = await api('/api/sync', {
      method: 'POST', body: JSON.stringify({
        start_date: $('sync-start').value, end_date: $('sync-end').value,
      }),
    });
    const more = result.detail_has_more ? '（未取得の詳細あり。再同期で続行）' : '';
    $('sync-result').textContent = `完了: 活動追加 ${result.added_count}件 / 更新 ${result.updated_count}件 / 詳細 ${result.detail_synced_count}件 / 詳細失敗 ${result.detail_failed_count}件 ${more}`;
    await loadDashboard();
  } catch (error) {
    $('sync-result').textContent = `失敗: ${error.message}`; showMessage(error.message, true);
  } finally { button.disabled = false; button.textContent = '活動データ取得'; }
});

$('annotation-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const id = $('annotation-activity-id').value;
  const body = {
    training_category: $('annotation-category').value || null,
    session_rpe: optionalNumber('annotation-rpe'),
    fatigue_score: optionalNumber('annotation-fatigue'),
    pain_score: optionalNumber('annotation-pain'),
    surface: $('annotation-surface').value || null,
    completion_status: $('annotation-completion').value || null,
    is_race: $('annotation-race').checked,
    training_goal: optionalText('annotation-goal'), notes: optionalText('annotation-notes'),
  };
  try {
    await api(`/api/activities/${id}/annotation`, {
      method: 'PUT', body: JSON.stringify(body),
    });
    $('detail-status').hidden = false; $('detail-status').textContent = '練習メモを保存しました。';
  } catch (error) {
    $('detail-status').hidden = false; $('detail-status').textContent = error.message;
  }
});

$('weight-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const id = $('weight-id').value;
  const body = { recorded_at: inputToIso($('weight-at').value), weight_kg: Number($('weight-kg').value), note: $('weight-note').value || null };
  try { await api(id ? `/api/weights/${id}` : '/api/weights', { method: id ? 'PUT' : 'POST', body: JSON.stringify(body) }); resetWeight(); await loadDashboard(); } catch (error) { showMessage(error.message, true); }
});

$('meal-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const id = $('meal-id').value;
  const body = { recorded_at: inputToIso($('meal-at').value), meal_type: $('meal-type').value, description: $('meal-description').value, calories_kcal: optionalNumber('meal-calories'), protein_g: optionalNumber('meal-protein'), fat_g: optionalNumber('meal-fat'), carbs_g: optionalNumber('meal-carbs') };
  try { await api(id ? `/api/meals/${id}` : '/api/meals', { method: id ? 'PUT' : 'POST', body: JSON.stringify(body) }); resetMeal(); await loadDashboard(); } catch (error) { showMessage(error.message, true); }
});

document.addEventListener('click', async (event) => {
  const target = event.target;
  if (target.dataset.activityDetail) await openActivityDetail(target.dataset.activityDetail);
  const weightId = target.dataset.editWeight; const deleteWeight = target.dataset.deleteWeight;
  const mealId = target.dataset.editMeal; const deleteMeal = target.dataset.deleteMeal;
  if (weightId) { const row = state.weights.find((item) => item.id === weightId); $('weight-id').value = row.id; $('weight-at').value = toLocalInput(row.recorded_at); $('weight-kg').value = row.weight_kg; $('weight-note').value = row.note || ''; $('weight-cancel').hidden = false; }
  if (mealId) { const row = state.meals.find((item) => item.id === mealId); $('meal-id').value = row.id; $('meal-at').value = toLocalInput(row.recorded_at); $('meal-type').value = row.meal_type; $('meal-description').value = row.description; $('meal-calories').value = row.calories_kcal ?? ''; $('meal-protein').value = row.protein_g ?? ''; $('meal-fat').value = row.fat_g ?? ''; $('meal-carbs').value = row.carbs_g ?? ''; $('meal-cancel').hidden = false; }
  if (deleteWeight && confirm('この体重記録を削除しますか？')) { try { await api(`/api/weights/${deleteWeight}`, { method: 'DELETE' }); await loadDashboard(); } catch (error) { showMessage(error.message, true); } }
  if (deleteMeal && confirm('この食事記録を削除しますか？')) { try { await api(`/api/meals/${deleteMeal}`, { method: 'DELETE' }); await loadDashboard(); } catch (error) { showMessage(error.message, true); } }
});

$('detail-close').addEventListener('click', () => $('activity-dialog').close());
$('weight-cancel').addEventListener('click', resetWeight);
$('meal-cancel').addEventListener('click', resetMeal);
$('activity-filter').addEventListener('change', renderActivities);
$('growth-metric').addEventListener('change', renderGrowth);
$('growth-period').addEventListener('change', loadGrowth);
$('reload').addEventListener('click', loadDashboard);

const today = new Date(); const start = new Date(today); start.setDate(start.getDate() - 89);
$('sync-end').value = today.toISOString().slice(0, 10);
$('sync-start').value = start.toISOString().slice(0, 10);
resetWeight(); resetMeal(); loadDashboard();

const $ = (q) => document.querySelector(q);
let games = [], ratings = {}, recommendations = {}, baseline = '', autoEnabled = false;
let dispatcherInstalled = false;
const safe = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function tierLabel(tier) { return ({platinum:'Platinum',gold:'Gold',silver:'Silver',bronze:'Bronze',borked:'Borked',native:'Native',unknown:'No tier'})[String(tier).toLowerCase()] || tier; }
function initials(name) { return name.replace(/[^a-z0-9 ]/gi,'').split(/\s+/).slice(0,2).map(x=>x[0]||'').join('').toUpperCase() || '•'; }
function render() {
  const query = $('#search').value.trim().toLowerCase(), filter = $('#filter').value;
  const filtered = games.filter(g => (!query || g.name.toLowerCase().includes(query)) &&
    (filter === 'all' || (filter === 'override' && g.selected !== 'Steam default') || (filter === 'rated' && ratings[g.appid] && ratings[g.appid].tier !== 'unavailable') || (filter === 'unrated' && !ratings[g.appid])));
  $('#visible-count').textContent = filtered.length;
  if (!filtered.length) { $('#rows').innerHTML = `<div class="empty">${games.length ? 'No games match those filters.' : 'No installed Steam games found.'}</div>`; return; }
  $('#rows').innerHTML = filtered.map(g => {
    const r = ratings[g.appid];
    const recommendation = recommendations[g.appid];
    const windowsGame = g.oslist.toLowerCase().includes('windows');
    const recommendedVersion = !windowsGame ? 'Native Linux game' :
      (recommendation && recommendation.tool ? recommendation.version : 'Steam default');
    const recommendationReason = !windowsGame ? 'Steam handles compatibility automatically' :
      (recommendation && recommendation.tool ?
        `${recommendation.installed ? '' : 'Steam will install this version · '}${recommendation.reason}` :
       (recommendation && recommendation.unavailable ? 'Report data unavailable' :
        (recommendation === null ? 'No strong match; Steam default is safer' : 'Run version scan')));
    const tier = r && r.tier && r.tier !== 'unavailable' ? `<div class="tier"><strong>${safe(tierLabel(r.tier))}</strong>${r.confidence ? ` · ${safe(r.confidence)} confidence` : ''}</div><div class="tier-cap">Community compatibility</div>` : `<div class="tier-none">${r ? 'Data unavailable' : 'Not checked'}</div><div class="tier-cap">Community compatibility</div>`;
    return `<article class="game-row"><div class="game-cell"><div class="game-cover">${safe(initials(g.name))}</div><div class="game-title-wrap"><div class="game-name" title="${safe(g.name)}">${safe(g.name)}</div><div class="game-id">APP ${safe(g.appid)}</div></div></div><div class="setting ${g.selected === 'Steam default' ? 'default' : ''}">${g.selected === 'Steam default' ? 'Steam default' : `<span class="setting-chip">${safe(g.selected)}</span>`}</div><div class="recommend"><span class="rec-dot"></span><div class="rec-block"><div class="rec-version">${safe(recommendedVersion)}</div><div class="rec-note">${safe(recommendationReason)}</div></div></div><div class="community">${tier}</div><a class="row-link" href="https://www.protondb.com/app/${safe(g.appid)}" target="_blank" rel="noreferrer" title="Open ProtonDB">↗</a></article>`;
  }).join('');
}
async function load() {
  try {
    const data = await (await fetch('/api/library')).json(); games = data.games; baseline = data.baseline;
    $('#game-count').textContent = data.count.toLocaleString(); $('#tool-count').textContent = data.tools.length.toLocaleString();
    $('#status').textContent = data.steam_found ? 'Steam library connected' : 'Steam library not found';
    $('#rows').innerHTML = data.steam_found ? '<div class="loading"><span class="spinner"></span> Preparing library…</div>' : '<div class="empty">Steam was not found in the standard Linux locations.</div>';
    const state = await (await fetch('/api/status')).json(); dispatcherInstalled=!!state.dispatcher_installed; setAutoState(state);
    if (!dispatcherInstalled) $('#status').textContent='One-time setup needed';
    render();
  } catch(e) { $('#status').textContent = 'Could not read Steam library'; $('#rows').innerHTML = '<div class="empty">Could not read Steam data. Check the terminal for details.</div>'; }
}
function toast(message) { const el=$('#toast'); el.textContent=message; el.classList.add('show'); setTimeout(()=>el.classList.remove('show'),3300); }
function setAutoState(state={}) {
  autoEnabled=!!state.enabled; dispatcherInstalled=state.dispatcher_installed ?? dispatcherInstalled;
  const button=$('#auto-mode'), label=$('#auto-status');
  button.textContent=autoEnabled?'Pause background updates':(dispatcherInstalled?'Enable background updates':'Setup instructions'); button.classList.toggle('enabled',autoEnabled);
  label.textContent=!autoEnabled?'Off':(state.pending_disable?'Turning off after Steam closes':
    (state.pending?(state.steam_running?'Waiting for Steam to close':'Installing or applying Proton versions'):'On'));
  label.classList.toggle('on',autoEnabled);
}
async function refreshRatings() {
  if (!games.length) { toast('No installed games to look up.'); return; }
  const button=$('#refresh'); button.disabled=true; button.innerHTML='<span class="spinner"></span> Checking…'; $('#status').textContent='Checking reports and ProtonDB';
  try {
    const [recResponse] = await Promise.all([
      fetch('/api/recommendations').then(r=>r.json()),
      ...Array.from({length:Math.ceil(games.length/30)},(_,i)=>games.slice(i*30,(i+1)*30)).map(batch=>{
        const ids=batch.map(g=>g.appid).join(',');
        return fetch(`/api/protondb?ids=${ids}`).then(r=>r.json()).then(data=>Object.assign(ratings,data));
      })
    ]);
    recommendations=recResponse.recommendations||{}; render();
    const ok=Object.values(ratings).filter(r=>r.tier!=='unavailable').length;
    const proposed=Object.values(recommendations).filter(r=>r&&r.tool).length;
    let syncResult=null;
    if (dispatcherInstalled) {
      syncResult=await (await fetch('/api/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:true})})).json();
      if (syncResult.state) setAutoState({...syncResult.state,dispatcher_installed:true});
    }
    $('#status').textContent=dispatcherInstalled?'Launch choices refreshed':'Preview ready · setup needed';
    toast(dispatcherInstalled?(syncResult?.message||`Found ${proposed} evidence-backed matches.`):`Preview only: run python3 install.py once, restart Steam, then choose Proton Picker as the default Proton tool. Found ${proposed} possible matches; ProtonDB ratings loaded for ${ok} games.`);
  } catch(e) { $('#status').textContent='Version check failed'; toast('Could not reach the report sources. Try again when online.'); }
  finally { button.disabled=false; button.innerHTML='<span>↻</span> Refresh launch choices'; }
}
async function toggleAuto() {
  const button=$('#auto-mode'); button.disabled=true;
  try {
    const response=await fetch('/api/auto',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!autoEnabled})});
    const result=await response.json();
    if (!response.ok || result.status==='error') throw new Error(result.message||'Could not change Auto Mode.');
    setAutoState({...result.state, dispatcher_installed:dispatcherInstalled, pending:result.status==='queued'||result.status==='installing'});
    $('#status').textContent=result.message; toast(result.message);
  } catch(e) { toast(e.message||'Could not change Auto Mode.'); }
  finally { button.disabled=false; }
}
$('#search').addEventListener('input',render); $('#filter').addEventListener('change',render); $('#refresh').addEventListener('click',refreshRatings); $('#auto-mode').addEventListener('click',toggleAuto); load();

const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
let state = null;
let browser = {device:'', share:'', path:'', mode:'read'};

function notify(message, error=false){const n=$('#notice');n.textContent=message;n.className='notice'+(error?' error':'');setTimeout(()=>n.classList.add('hidden'),3500)}
async function api(url, options={}){const response=await fetch(url,options);let data;try{data=await response.json()}catch{data={error:await response.text()}}if(!response.ok)throw new Error(data.error||`Request failed (${response.status})`);return data}
function formatSize(bytes){if(bytes<1024)return `${bytes} B`;if(bytes<1048576)return `${(bytes/1024).toFixed(1)} KB`;return `${(bytes/1048576).toFixed(1)} MB`}

async function loadState(){
  try{state=await api('/api/state');render()}catch(error){notify(error.message,true)}
}
function render(){
  const s=state.settings;$('#identity').textContent=s.device_name;$('#deviceName').value=s.device_name;$('#pairMode').value=s.pairing_mode;
  $('#quality').value=s.remote_quality;$('#qualityValue').textContent=`${s.remote_quality}%`;$('#unattended').checked=s.unattended_enabled;
  $('#unattendedPinRow').classList.toggle('hidden',!s.unattended_enabled);
  $('#shares').innerHTML=s.shares.length?s.shares.map(x=>`<div class="share"><div class="folder-icon">▰</div><div><div class="share-name">${esc(x.name)}</div><div class="share-path">${esc(x.path)}</div></div><span class="badge ${x.mode}">${x.mode==='full'?'Full access':'Read only'}</span><button class="remove" data-remove-share="${x.id}">Remove</button></div>`).join(''):'<div class="empty">Nothing shared yet.</div>';
  $('#peers').innerHTML=state.peers.length?state.peers.map(peer=>`<div class="device ${peer.online?'':'offline'}"><div class="device-head"><div class="device-icon">▣</div><div><div class="device-name">${esc(peer.name)}</div><div class="device-meta">${peer.online?'Online':'Offline'} · ${peer.share_count} share${peer.share_count===1?'':'s'}</div></div></div><div class="device-actions">${peer.paired?`<button class="primary" data-browse="${peer.device_id}">Browse files</button><button class="ghost" data-remote="${peer.device_id}">Remote support</button>`:`<button class="primary" data-pair="${peer.device_id}">Pair computer</button>`}</div></div>`).join(''):'<div class="empty">No other LANLink computers found. Install and start LANLink on another PC on this network.</div>';
  const pairRequests=state.pairing_requests.filter(x=>x.status==='pending'); const remoteRequests=state.remote_requests;
  $('#requestsSection').classList.toggle('hidden',!pairRequests.length&&!remoteRequests.length);
  $('#requests').innerHTML=[...pairRequests.map(x=>`<div class="request"><div><strong>${esc(x.device_name)}</strong><div class="device-meta">Wants to pair and browse your shares</div></div><div class="request-actions"><button class="primary small" data-pair-decision="${x.request_id}:approve">Approve</button><button class="danger small" data-pair-decision="${x.request_id}:reject">Reject</button></div></div>`),...remoteRequests.map(x=>`<div class="request"><div><strong>${esc(x.device_name)}</strong><div class="device-meta">Requests ${x.control?'screen and control':'view-only'} access</div></div><div class="request-actions"><button class="primary small" data-remote-decision="${x.request_id}:approve">Approve</button><button class="danger small" data-remote-decision="${x.request_id}:reject">Reject</button></div></div>`)].join('');
  $('#trusted').innerHTML=state.trusted_devices.length?`<h3>Trusted computers</h3>${state.trusted_devices.map(x=>`<div class="trusted-row"><span>${esc(x.name)}</span><span><button class="ghost small" data-trusted="${x.device_id}:${x.blocked?'unblock':'block'}">${x.blocked?'Unblock':'Block'}</button> <button class="danger small" data-trusted="${x.device_id}:revoke">Revoke</button></span></div>`).join('')}`:'';
}

document.addEventListener('click',async event=>{
  const b=event.target.closest('button');if(!b)return;
  try{
    if(b.id==='addShare')$('#shareDialog').showModal();
    if(b.id==='refresh')await loadState();
    if(b.id==='chooseFolder'){const r=await api('/api/pick-folder',{method:'POST'});if(r.path)$('#sharePath').value=r.path}
    if(b.dataset.removeShare){if(confirm('Stop sharing this location? No files will be deleted.'))await api(`/api/shares/${b.dataset.removeShare}`,{method:'DELETE'});await loadState()}
    if(b.dataset.pair){const pin=prompt('Enter the other PC’s pairing PIN if it uses one, or leave blank for on-screen approval.','')??'';const r=await api(`/api/peers/${b.dataset.pair}/pair`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin})});notify(r.status==='approved'?'Paired successfully':'Pairing request sent');pollPair(b.dataset.pair)}
    if(b.dataset.pairDecision){const [id,action]=b.dataset.pairDecision.split(':');await api(`/api/pairing/${id}/${action}`,{method:'POST'});await loadState()}
    if(b.dataset.remoteDecision){const [id,action]=b.dataset.remoteDecision.split(':');await api(`/api/remote/${id}/${action}`,{method:'POST'});await loadState()}
    if(b.dataset.trusted){const [id,action]=b.dataset.trusted.split(':');await api(`/api/trusted/${id}/${action}`,{method:'POST'});await loadState()}
    if(b.dataset.browse)await openBrowser(b.dataset.browse);
    if(b.dataset.remote)window.open(`/remote/${b.dataset.remote}`,'_blank');
    if(b.id==='goUp'){browser.path=browser.path.split('/').slice(0,-1).join('/');await loadFiles()}
    if(b.id==='newFolder'){const name=prompt('New folder name');if(name){const path=[browser.path,name].filter(Boolean).join('/');await fileOperation({operation:'mkdir',path});await loadFiles()}}
    if(b.dataset.openFolder){browser.path=[browser.path,b.dataset.openFolder].filter(Boolean).join('/');await loadFiles()}
    if(b.dataset.download){location.href=`/api/peers/${browser.device}/download/${browser.share}?path=${encodeURIComponent([browser.path,b.dataset.download].filter(Boolean).join('/'))}`}
    if(b.dataset.fileAction){const [action,name]=b.dataset.fileAction.split(':');const path=[browser.path,name].filter(Boolean).join('/');if(action==='delete'&&confirm(`Delete “${name}”?`)){await fileOperation({operation:'delete',path});await loadFiles()}if(action==='rename'){const next=prompt('New name',name);if(next){await fileOperation({operation:'rename',path,name:next});await loadFiles()}}if(action==='copy'){const dest=prompt('Copy to path (including new name)',path+' - Copy');if(dest){await fileOperation({operation:'copy',path,destination:dest});await loadFiles()}}}
  }catch(error){notify(error.message,true)}
});

$('#shareForm').addEventListener('submit',async event=>{event.preventDefault();try{await api('/api/shares',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:$('#sharePath').value,name:$('#shareName').value,mode:$('#shareMode').value})});$('#shareDialog').close();event.target.reset();await loadState();notify('Folder shared')}catch(error){notify(error.message,true)}});
$('#quality').addEventListener('input',()=>$('#qualityValue').textContent=`${$('#quality').value}%`);
$('#unattended').addEventListener('change',()=>$('#unattendedPinRow').classList.toggle('hidden',!$('#unattended').checked));
$('#saveSettings').addEventListener('click',async()=>{try{const body={device_name:$('#deviceName').value,pairing_mode:$('#pairMode').value,remote_quality:Number($('#quality').value),unattended_enabled:$('#unattended').checked};if($('#pairPin').value)body.pairing_pin=$('#pairPin').value;if($('#unattendedPin').value)body.unattended_pin=$('#unattendedPin').value;await api('/api/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});$('#pairPin').value='';$('#unattendedPin').value='';await loadState();notify('Settings saved')}catch(error){notify(error.message,true)}});

async function pollPair(device){for(let i=0;i<60;i++){await new Promise(r=>setTimeout(r,2000));try{const result=await api(`/api/peers/${device}/pair`);if(result.status==='approved'){notify('Computer paired');await loadState();return}if(result.status==='rejected'){notify('Pairing was rejected',true);return}}catch(error){if(i>2){notify(error.message,true);return}}}}
async function openBrowser(device){browser={device,share:'',path:'',mode:'read'};const peer=state.peers.find(x=>x.device_id===device);$('#browserTitle').textContent=peer?.name||'Files';$('#browserDialog').showModal();const shares=await api(`/api/peers/${device}/shares`);$('#browserTools').classList.add('hidden');$('#fileList').innerHTML='';$('#breadcrumb').textContent='Choose a shared location';$('#shareChooser').innerHTML=shares.length?shares.map(x=>`<div class="share-choice" data-share="${x.id}" data-mode="${x.mode}"><strong>${esc(x.name)}</strong><span class="badge ${x.mode}">${x.mode==='full'?'Full access':'Read only'}</span></div>`).join(''):'<div class="empty">This computer has no shared folders.</div>';document.querySelectorAll('[data-share]').forEach(el=>el.onclick=async()=>{browser.share=el.dataset.share;browser.mode=el.dataset.mode;browser.path='';$('#shareChooser').classList.add('hidden');$('#browserTools').classList.remove('hidden');$('#uploadFile').parentElement.classList.toggle('hidden',browser.mode!=='full');$('#newFolder').classList.toggle('hidden',browser.mode!=='full');await loadFiles()})}
async function loadFiles(){const files=await api(`/api/peers/${browser.device}/files/${browser.share}?path=${encodeURIComponent(browser.path)}`);$('#breadcrumb').textContent=browser.path||'/';$('#fileList').innerHTML=files.length?files.map(f=>`<div class="file-row"><span>${f.directory?'▰':'▤'}</span><span class="file-name" ${f.directory?`data-open-folder="${esc(f.name)}"`:''}>${esc(f.name)}</span><span class="file-size">${f.directory?'':formatSize(f.size)}</span><span class="file-actions">${f.directory?'':`<button data-download="${esc(f.name)}">Download</button>`}${browser.mode==='full'?`<button data-file-action="rename:${esc(f.name)}">Rename</button><button data-file-action="copy:${esc(f.name)}">Copy</button><button data-file-action="delete:${esc(f.name)}">Delete</button>`:''}</span></div>`).join(''):'<div class="empty">This folder is empty.</div>'}
async function fileOperation(body){return api(`/api/peers/${browser.device}/operation/${browser.share}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})}
$('#uploadFile').addEventListener('change',async event=>{const file=event.target.files[0];if(!file)return;const data=new FormData();data.append('path',browser.path);data.append('file',file);try{await api(`/api/peers/${browser.device}/upload/${browser.share}`,{method:'POST',body:data});notify('Upload complete');await loadFiles()}catch(error){notify(error.message,true)}event.target.value=''});

loadState();setInterval(loadState,4000);

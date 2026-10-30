const $=id=>document.getElementById(id);
const CFG={image:{ext:['png','jpg','jpeg','webp'],acc:'.png,.jpg,.jpeg,.webp',hint:'PNG, JPG, JPEG or WEBP'},
 video:{ext:['mp4','mov','webm','mkv','avi','m4v'],acc:'.mp4,.mov,.webm,.mkv,.avi,.m4v',hint:'MP4, MOV, WEBM, MKV, AVI, M4V'}};
let mode='image',localUrl=null;
function setMode(m){mode=m;document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.dataset.t===m));
 $('file').accept=CFG[m].acc;$('hint').textContent=CFG[m].hint;reset();}
function msg(t,c){const e=$('msg');e.hidden=!t;e.textContent=t||'';e.className='msg '+(c||'');}
function reset(){$('result').hidden=true;$('prog').hidden=true;$('drop').hidden=false;msg('');if(localUrl)URL.revokeObjectURL(localUrl);}
function progress(p,t){$('prog').hidden=false;$('bar').style.width=(p*100)+'%';$('ptxt').textContent=t;}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>setMode(t.dataset.t));
$('again').onclick=reset;
const d=$('drop');d.onclick=()=>$('file').click();d.onkeydown=e=>{if(e.key==='Enter')$('file').click()};
['dragover','dragenter'].forEach(e=>d.addEventListener(e,ev=>{ev.preventDefault();d.classList.add('over')}));
['dragleave','drop'].forEach(e=>d.addEventListener(e,ev=>{ev.preventDefault();d.classList.remove('over')}));
d.addEventListener('drop',e=>handle(e.dataTransfer.files[0]));$('file').onchange=e=>{handle(e.target.files[0]);e.target.value=''};
function upload(f){return new Promise((res,rej)=>{const x=new XMLHttpRequest(),fd=new FormData();fd.append('file',f);
 x.open('POST','/api/'+mode);x.upload.onprogress=e=>e.lengthComputable&&progress(e.loaded/e.total*.5,'Uploading… '+Math.round(e.loaded/e.total*100)+'%');
 x.upload.onload=()=>progress(.5,'Detecting and removing watermark…');
 x.onload=()=>{let j={};try{j=JSON.parse(x.responseText)}catch{}x.status<300?res(j):rej(new Error(j.error||'Server error.'))};
 x.onerror=()=>rej(new Error('Network error. Is the server running?'));x.send(fd);});}
async function handle(f){
 if(!f)return;msg('');const ext=f.name.split('.').pop().toLowerCase();
 if(!CFG[mode].ext.includes(ext))return msg('Unsupported file type. Use: '+CFG[mode].hint+'.','err');
 localUrl=URL.createObjectURL(f);progress(0,'Starting…');
 try{const j=await upload(f);let url;
  if(mode==='image')url=j.url;
  else{for(;;){await new Promise(r=>setTimeout(r,1000));const s=await (await fetch('/api/job/'+j.job)).json();
    if(s.status==='error')throw new Error(s.error);if(s.status==='done'){url=s.url;break}
    progress(.5+s.progress*.5,'Processing video… '+Math.round(s.progress*100)+'%');}}
  show(url,j.detected);}
 catch(e){$('prog').hidden=true;msg(e.message,'err');}}
function show(url,detected){
 $('prog').hidden=true;$('drop').hidden=true;$('result').hidden=false;
 $('dl').href=url+'?dl=1';$('dl').download='';
 const v=mode==='video';$('cmp').hidden=v;$('vid').hidden=!v;
 if(v){$('vid').src=url;}else{$('before').src=localUrl;$('after').src=url;
  $('after').onload=()=>{$('before').style.setProperty('--w',$('cmp').clientWidth+'px')};}
 msg(v?'Done! Your video is ready.':detected===false?'Done. Watermark position estimated (low contrast) — check the result.':'Done! Watermark removed.','ok');}
$('slider').oninput=e=>{const p=e.target.value;$('clip').style.width=p+'%';$('cmp').style.setProperty('--p',p+'%')};
addEventListener('resize',()=>$('before').style.setProperty('--w',$('cmp').clientWidth+'px'));
setMode('image');

const $ = (id) => document.getElementById(id);
const state = {image: null, picture: null, boxes: [], revision: 0, labels: {}, before: 0, loading: 0, dirty: false};
async function api(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || '请求失败');
  return body;
}
function message(id, text) { $(id).textContent = text; }
function option(select, value, text) { const item = document.createElement('option'); item.value = value; item.textContent = text; select.append(item); }
async function loadImages(reset = false) {
  const data = await api(`/api/v1/label-images?before=${reset ? 0 : state.before}`);
  if (reset) $('image-list').replaceChildren();
  if (!Object.keys(state.labels).length) {
    state.labels = data.labels;
    Object.entries(data.labels).forEach(([value, text]) => option($('label'), value, text));
  }
  data.images.forEach((record) => {
    const button = document.createElement('button'); button.type = 'button';
    const labels = {draft:'草稿',ready:'已确认',excluded:'已排除'};
    button.textContent = `${record.image.scene} · ${labels[record.annotation?.status] || '未标注'}\n${record.image.image_id}`;
    button.onclick = () => selectImage(record.image.image_id).catch(e => message('save-status', e.message));
    $('image-list').append(button);
  });
  if (data.images.length) state.before = data.images.at(-1).cursor;
  $('more').disabled = data.images.length < 30;
}
async function selectImage(id) {
  if (state.dirty && !window.confirm('有未保存标注，放弃修改并切换图片？')) return;
  const generation = ++state.loading;
  $('save').disabled = true;
  state.picture = null;
  const record = await api(`/api/v1/annotations/${encodeURIComponent(id)}`);
  if (generation !== state.loading) return;
  state.image = record.image; state.revision = record.revision;
  const annotation = record.annotation;
  state.boxes = annotation?.boxes || [];
  ['reviewer', 'group_id', 'notes'].forEach(key => { $(key === 'group_id' ? 'group' : key).value = annotation?.[key] || ''; });
  $('quality').value = annotation?.quality || 'usable'; $('status').value = annotation?.status || 'draft';
  $('negative').checked = annotation?.negative || false;
  state.dirty = false;
  message('selected-image', `${id} · ${record.image.scene} · ${record.image.width}×${record.image.height}`);
  message('save-status', '');
  const picture = new Image();
  picture.onload = () => {
    if (generation !== state.loading) return;
    state.picture = picture; $('canvas').width = picture.naturalWidth; $('canvas').height = picture.naturalHeight;
    $('save').disabled = false; draw(); renderBoxes();
  };
  picture.onerror = () => { if (generation === state.loading) message('save-status', '原图加载失败，请重新选择。'); };
  picture.src = `/api/v1/images/${encodeURIComponent(id)}/file`;
}
function draw(preview) {
  const canvas = $('canvas'), ctx = canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if (!state.picture) return;
  ctx.drawImage(state.picture,0,0);
  [...state.boxes, ...(preview ? [preview] : [])].forEach((box, i) => {
    ctx.strokeStyle = '#ffca28'; ctx.lineWidth = 2;
    ctx.strokeRect(box.x*canvas.width,box.y*canvas.height,box.w*canvas.width,box.h*canvas.height);
    ctx.font = '16px sans-serif'; ctx.fillStyle = '#ffca28';
    ctx.fillText(`${i+1} ${state.labels[box.label]}`, box.x*canvas.width+3, Math.max(18,box.y*canvas.height+18));
  });
}
function renderBoxes() {
  $('boxes').replaceChildren();
  state.boxes.forEach((box, index) => {
    const row = document.createElement('li'); row.textContent = `${state.labels[box.label]} `;
    const button = document.createElement('button'); button.type = 'button'; button.textContent = `删除框 ${index+1}`;
    button.onclick = () => {state.boxes.splice(index,1); state.dirty=true; renderBoxes(); draw();};
    row.append(button); $('boxes').append(row);
  });
}
function addBox(box) {
  if (!state.picture) return message('save-status','请先选择图片。');
  if (state.boxes.length >= 100 || ![box.x,box.y,box.w,box.h].every(Number.isFinite) || box.x<0 || box.y<0 || box.w<=0 || box.h<=0 || box.x+box.w>1.000001 || box.y+box.h>1.000001) return message('save-status','框必须位于图片内，且最多 100 个。');
  state.boxes.push(box); state.dirty=true; $('negative').checked=false; draw(); renderBoxes();
}
$('add-box').onclick = () => addBox({label:$('label').value,x:Number($('box-x').value)/$('canvas').width,y:Number($('box-y').value)/$('canvas').height,w:Number($('box-w').value)/$('canvas').width,h:Number($('box-h').value)/$('canvas').height});
let start = null;
function point(event) {const r=$('canvas').getBoundingClientRect();return {x:Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),y:Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))};}
function rectangle(end) {return {label:$('label').value,x:Math.min(start.x,end.x),y:Math.min(start.y,end.y),w:Math.abs(start.x-end.x),h:Math.abs(start.y-end.y)};}
$('canvas').onpointerdown = e => {if(state.picture){start=point(e);$('canvas').setPointerCapture(e.pointerId);}};
$('canvas').onpointermove = e => {if(start)draw(rectangle(point(e)));};
$('canvas').onpointerup = e => {if(start){const box=rectangle(point(e));start=null;if(box.w*$('canvas').width>=3&&box.h*$('canvas').height>=3)addBox(box);else draw();}};
$('canvas').onpointercancel = () => {start=null;draw();};
['reviewer','group','quality','status','negative','notes'].forEach(id => $(id).oninput=()=>{state.dirty=true;});
$('save').onclick = async () => {
  if (!state.image || !state.picture) return;
  const generation=state.loading;
  $('save').disabled=true;
  try {
    const body={revision:state.revision,reviewer:$('reviewer').value,group_id:$('group').value,status:$('status').value,quality:$('quality').value,negative:$('negative').checked,notes:$('notes').value,boxes:state.boxes};
    const result=await api(`/api/v1/annotations/${state.image.image_id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    if(generation!==state.loading)return;
    state.revision=result.revision;state.dirty=false;message('save-status','标注已保存。');await loadImages(true);
  } catch(e){message('save-status',e.message);} finally {if(generation===state.loading)$('save').disabled=false;}
};
$('capture').onclick = async () => {
  $('capture').disabled=true;
  try {
    const record=await api('/api/v1/captures',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({experiment:$('experiment').value})});
    message('capture-status',`等待相机上传：${record.request_id}`);
    for(let i=0;i<25;i++) {
      const capture=await api(`/api/v1/captures/${record.request_id}`);
      if(capture.image){message('capture-status',`图片已收到：${capture.image.image_id}`);await loadImages(true);await selectImage(capture.image.image_id);return;}
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
    message('capture-status','等待超时，请检查相机网络；稍后可刷新图片查看迟到的上传。');
  }catch(e){message('capture-status',e.message);}finally{$('capture').disabled=false;}
};
$('refresh').onclick=()=>loadImages(true).catch(e=>message('capture-status',e.message));
$('more').onclick=()=>loadImages().catch(e=>message('capture-status',e.message));
$('export').onclick=async()=>{
  $('export').disabled=true;
  try{const response=await fetch('/api/v1/annotations/export');if(!response.ok)throw new Error((await response.json()).detail);
    const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='physlab-annotations.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message('export-status','已导出已确认标注。');
  }catch(e){message('export-status',e.message);}finally{$('export').disabled=false;}
};
window.addEventListener('beforeunload',event=>{if(state.dirty){event.preventDefault();event.returnValue='';}});
async function initialize(){const data=await api('/api/v1/experiments');data.experiments.forEach(e=>option($('experiment'),e.id,e.name));await loadImages(true);}
initialize().catch(e=>message('capture-status',e.message));

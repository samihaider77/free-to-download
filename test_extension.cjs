const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const store = {};
const event = () => ({addListener(fn) {this.fn = fn;}});
const chrome = {
  runtime: {id:'test',onInstalled:event(),onStartup:event(),onMessage:event()},
  contextMenus: {onClicked:event()},
  webRequest: {onResponseStarted:event()},
  tabs: {onRemoved:event(),onUpdated:event()},
  storage: {session: {async get(k){return {[k]:store[k]};},async set(v){Object.assign(store,v);},async remove(k){delete store[k];}}}
};
const context=vm.createContext({chrome,URL,Date,console});
vm.runInContext(fs.readFileSync(__dirname+'/browser-extension/background.js','utf8'),context);
async function capture(url,type,tabId=1,frameId=3,extra=[]) {
  chrome.webRequest.onResponseStarted.fn({url,tabId,frameId,statusCode:200,responseHeaders:[{name:'Content-Type',value:type},...extra]});
  await vm.runInContext('storageQueue',context);
}
(async()=>{
  // LinkedIn-style HLS pieces served as video/mp4 must not be offered as videos.
  await capture('https://dms.example/vid/hls-720p/B4D/1/179','video/mp4',5,0,[{name:'Content-Length',value:'1379'},
    {name:'Content-Disposition',value:'inline; filename="init_output_hls_2dad.mp4"'}]);
  await capture('https://dms.example/vid/hls-720p/B4D/2/179','video/mp4',5,0,[{name:'Content-Length',value:'2400000'},
    {name:'Content-Disposition',value:'inline; filename="segment_output_hls_2dad_1.mp4"'}]);
  await capture('https://rr1.googlevideo.com/videoplayback?itag=399&range=0-2000000','video/mp4',5,0,[{name:'Content-Length',value:'2000001'}]);
  await capture('https://cdn.example/clip.mp4','video/mp4',5,0,[{name:'Content-Range',value:'bytes 0-1023/52428800'}]);
  assert.equal(JSON.stringify(store['media-5'].map(item=>[item.url,item.size])),JSON.stringify([['https://cdn.example/clip.mp4',52428800]]));
  await capture('https://cdn.example/master.m3u8','application/vnd.apple.mpegurl');
  await capture('https://cdn.example/segment.ts','video/mp2t');
  await capture('https://cdn.example/segment.m4s','video/mp4');
  await capture('https://cdn.example/page','text/html');
  await capture('https://cdn.example/master.m3u8','application/vnd.apple.mpegurl');
  assert.equal(store['media-1'].length,1);
  await capture('https://cdn.example/other.mp4','video/mp4',2);
  assert.equal(store['media-2'].length,1);
  const get=(sender)=>new Promise(resolve=>chrome.runtime.onMessage.fn({type:'media-list'},sender,resolve));
  assert.equal((await get({id:'test',tab:{id:1},frameId:3})).items.length,1);
  assert.equal((await get({id:'test',tab:{id:1},frameId:9})).items.length,0);
  chrome.tabs.onUpdated.fn(1,{status:'loading'});
  await vm.runInContext('storageQueue',context);
  assert.equal(store['media-1'],undefined);
  // Automatic pairing: no stored token -> POST /pair, store it, then send the download with it.
  // A 401 (app reinstalled, new token) re-pairs once and retries.
  const calls=[]; let appToken='first';
  context.fetch=async (url,options={})=>{
    calls.push(`${options.method||'GET'} ${new URL(url).pathname} ${options.headers?.Authorization||''}`.trim());
    if (url.endsWith('/pair')) return {ok:true,status:200,json:async()=>({token:appToken,version:'0.6.0'})};
    const ok=options.headers.Authorization===`Bearer ${appToken}`;
    return {ok,status:ok?202:401,json:async()=>ok?{accepted:1}:{error:'bad token'}};
  };
  context.AbortSignal={timeout:()=>undefined};
  let local={};
  chrome.storage.local={async get(keys){return Object.fromEntries([].concat(keys).filter(k=>k in local).map(k=>[k,local[k]]));},async set(v){Object.assign(local,v);}};
  const download=()=>new Promise(resolve=>chrome.runtime.onMessage.fn({type:'download',urls:['https://cdn.example/a.zip']},{id:'test'},resolve));
  assert.equal((await download()).accepted,1);
  assert.equal(JSON.stringify(calls),JSON.stringify(['POST /pair','POST /downloads Bearer first']));
  appToken='second'; calls.length=0;
  assert.equal((await download()).accepted,1);
  assert.equal(JSON.stringify(calls),JSON.stringify(['POST /downloads Bearer first','POST /pair','POST /downloads Bearer second']));
  // App closed: the extension asks the browser to start it (native messaging), waits, then downloads.
  let appOpen=false; const launches=[];
  context.setTimeout=(fn)=>fn();  // no real waiting in tests
  chrome.runtime.sendNativeMessage=async(host,msg)=>{launches.push(host); appOpen=true; return {started:true};};
  context.fetch=async(url,options={})=>{
    if (!appOpen) throw new TypeError('Failed to fetch');
    if (url.endsWith('/pair')) return {ok:true,status:200,json:async()=>({token:'third',version:'0.6.1'})};
    return {ok:true,status:202,json:async()=>({accepted:1})};
  };
  local={token:'third'};
  assert.equal((await download()).accepted,1);
  assert.equal(JSON.stringify(launches),JSON.stringify(['com.free_to_download.launcher']));
  // Launcher not registered (app never run on this PC): a clear message with the reason, not "Failed to fetch".
  appOpen=false; chrome.runtime.sendNativeMessage=async()=>{throw new Error('Specified native messaging host not found.');};
  assert.match((await download()).error,/Couldn't start Free-to-Download automatically \(Specified native messaging host not found\.\)/);
  // Launcher ran but the app never answered: a "still starting" message after the wait.
  chrome.runtime.sendNativeMessage=async()=>({started:true});
  assert.match((await download()).error,/starting but is taking a while/);
  console.log('PASS: manifest detection, segment exclusion, deduplication, tab/frame isolation, navigation cleanup and automatic pairing');
})().catch(error=>{console.error(error);process.exitCode=1;});

const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const store = {};
const event = () => ({addListener(fn) {this.fn = fn;}});
const chrome = {
  runtime: {id:'test',onInstalled:event(),onMessage:event()},
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
  console.log('PASS: manifest detection, segment exclusion, deduplication, tab/frame isolation and navigation cleanup');
})().catch(error=>{console.error(error);process.exitCode=1;});

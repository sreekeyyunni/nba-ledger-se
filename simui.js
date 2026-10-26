// Season-sim helpers shared by the Trade machine and the Transaction grader.
// Loads data/sim_data.json once, matches Ledger player names to the sim's, and
// returns playoff and title odds before and after a set of moves. A move whose
// player is already on the receiving team (a trade that has happened) is
// undone for the "before" side instead, so past deals read the same way as
// hypothetical ones. Fires a "seasonsim" event on document when ready.
(function(){
  var SIMS=2000,data=null,names=null,cache={};
  var norm=function(s){return String(s||"").normalize("NFD").replace(/[̀-ͯ]/g,"").toLowerCase().replace(/[.'’]/g,"").replace(/\b(jr|sr|ii|iii|iv)\b/g,"").replace(/[^a-z]+/g," ").trim()};
  var ALIAS={"ronald holland":"ron holland"};   // NBA.com vs Basketball Reference spelling
  var key=function(s){var k=norm(s);return ALIAS[k]||k};
  // sim_data can list one player under both sources' spellings; keep the first and re-rate that team
  function dedupe(d){
    var seen=new Set(),hit=new Set();
    d.players=d.players.filter(function(p){var k=key(p[0])+"|"+p[1];if(seen.has(k)){hit.add(p[1]);return false}seen.add(k);return true});
    hit.forEach(function(t){d.teams[t].roster=SeasonSim.teamRating(d,d.players.filter(function(p){return p[1]===t}))});
  }
  function load(){
    if(!window.SeasonSim)return;
    fetch("data/sim_data.json").then(function(r){if(!r.ok)throw 0;return r.json()}).then(function(d){
      dedupe(d);data=d;names=new Map();d.players.forEach(function(p){names.set(key(p[0]),p)});
      document.dispatchEvent(new Event("seasonsim"));
    }).catch(function(){});
  }
  function run(moves){var k=JSON.stringify(moves);if(!cache[k])cache[k]=SeasonSim.run(data,{sims:SIMS,moves:moves}).teams;return cache[k]}
  // moves: [{name, from, to}] with Ledger names and team codes
  function odds(moves){
    if(!data)return null;
    var pre=[],post=[],miss=[],teams=new Set();
    moves.forEach(function(m){
      var p=names.get(key(m.name));
      if(!p){miss.push(m.name);return}
      if(m.from)teams.add(m.from);if(m.to)teams.add(m.to);
      if(p[1]===m.to&&m.from)pre.push({player:p[0],to:m.from});     // already happened: undo it for "before"
      else post.push({player:p[0],to:m.to||null});
    });
    if(!pre.length&&!post.length)return{miss:miss,teams:{}};
    var b=run(pre),a=run(post),out={};
    teams.forEach(function(t){if(b[t])out[t]={before:b[t],after:a[t]}});
    return{teams:out,miss:miss,past:pre.length>0&&!post.length};
  }
  var pct=function(x){return x>=0.995?">99%":x<0.005&&x>0?"<1%":Math.round(x*100)+"%"};
  function arrow(b,a){var d=Math.round((a-b)*100);return '<span class="num">'+pct(b)+' → '+pct(a)+'</span>'+(d?' <span class="'+(d>0?"pos":"neg")+'">('+(d>0?"+":"")+d+')</span>':"")}
  // <dt>/<dd> rows for a kv list
  function rows(res,team){
    if(!res||!res.teams[team])return"";
    var o=res.teams[team],b=o.before,a=o.after,dw=a.projW-b.projW;
    return '<dt>Playoff odds</dt><dd>'+arrow(b.playoffs,a.playoffs)+'</dd><dt>Title odds</dt><dd>'+arrow(b.title,a.title)+'</dd><dt>Projected wins</dt><dd><span class="num">'+b.projW.toFixed(1)+' → '+a.projW.toFixed(1)+'</span>'+(Math.abs(dw)>=0.1?' <span class="'+(dw>0?"pos":"neg")+'">('+(dw>0?"+":"")+dw.toFixed(1)+')</span>':"")+'</dd>';
  }
  window.SimUI={ready:function(){return!!data},base:function(){return data?run([]):null},odds:odds,rows:rows,pct:pct,data:function(){return data},norm:norm};
  if(window.SeasonSim)load();else document.addEventListener("DOMContentLoaded",load);
})();

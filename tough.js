(function(){
function csv(t){var r=[],row=[],f="",q=false;for(var i=0;i<t.length;i++){var c=t[i];if(q){if(c=='"'){if(t[i+1]=='"'){f+='"';i++}else q=false}else f+=c}else if(c=='"')q=true;else if(c==','){row.push(f);f=""}else if(c=='\n'){row.push(f);r.push(row);row=[];f=""}else if(c!='\r')f+=c}if(f||row.length){row.push(f);r.push(row)}var h=r.shift();return r.filter(function(x){return x.length>1}).map(function(x){var o={};h.forEach(function(k,j){o[k]=x[j]});return o})}
function get(n){return fetch("data/"+n+".csv").then(function(r){if(!r.ok)throw new Error(n);return r.text()}).then(csv)}
var N=function(x){var v=parseFloat(x);return isNaN(v)?0:v};
var esc=function(s){return String(s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})};
var m=function(v){return(v<0?"−":"+")+"$"+Math.abs(v).toFixed(1)+"M"};
var NAMES={ATL:"Hawks",BOS:"Celtics",BRK:"Nets",CHO:"Hornets",CHI:"Bulls",CLE:"Cavaliers",DAL:"Mavericks",DEN:"Nuggets",DET:"Pistons",GSW:"Warriors",HOU:"Rockets",IND:"Pacers",LAC:"Clippers",LAL:"Lakers",MEM:"Grizzlies",MIA:"Heat",MIL:"Bucks",MIN:"Timberwolves",NOP:"Pelicans",NYK:"Knicks",OKC:"Thunder",ORL:"Magic",PHI:"76ers",PHO:"Suns",POR:"Trail Blazers",SAC:"Kings",SAS:"Spurs",TOR:"Raptors",UTA:"Jazz",WAS:"Wizards"};
var logo=function(t){return '<img src="logos/'+t+'.png" alt="">'};
var STATUS={"over 2nd apron":3,"over 1st apron":2,"over tax":1};
window.toughData=function(){return Promise.all(["team_summary","cap_sheet","team_power","draft_picks","contract_value","contracts_clean","trade_values"].map(function(n){return get(n).catch(function(){return[]})})).then(function(d){
  var ts=d[0],cap=d[1],pw=d[2],picks=d[3],cv=d[4],cc=d[5],tv=d[6];
  if(!ts.length)return null;
  var capBy={};cap.forEach(function(r){(capBy[r.Team]=capBy[r.Team]||{})[r.season]=r});
  var rec={};pw.forEach(function(r){rec[r.team]={w:N(r.wins),l:N(r.losses)}});
  var owed={};picks.forEach(function(r){if(r.round==="1"&&r.original_team!==r.owner&&!/SWAP/.test(r.pick_id))owed[r.original_team]=(owed[r.original_team]||0)+1});
  var nets=ts.map(function(r){return N(r.net_m)}).sort(function(a,b){return a-b});
  // ---- teams ----
  var teams=ts.map(function(r){
    var t=r.Team,c=capBy[t]||{},now=(c["2026-27"]||{}).status||"",nxt=(c["2027-28"]||{}).status||"",R=rec[t]||{w:0,l:0},g=R.w+R.l,pct=g?R.w/g:.5;
    var net=N(r.net_m),dead=N(r.dead_m),ow=owed[t]||0,why=[],s=0;
    s+=Math.max(0,-net)/30;if(net<-20)why.push("contracts "+m(net)+" underwater");
    s+=(STATUS[now]||0)*0.9;if(STATUS[now])why.push(now);
    s+=(STATUS[nxt]||0)*0.6;if(STATUS[nxt]>=2)why.push("still "+nxt+" next year");
    s+=Math.max(0,.5-pct)*8*Math.min(1,g/10);if(g&&pct<.4)why.push(R.w+"-"+R.l+" start");
    s+=dead/15;if(dead>=10)why.push("$"+dead.toFixed(0)+"M dead money");
    s+=ow*0.5;if(ow>=2)why.push(ow+" own firsts owed away");
    if(r.worst_contract&&s>2)why.push("worst deal: "+r.worst_contract);
    var mandate=STATUS[now]?"cut":pct<.4&&net<0?"rebuild":"retool";
    return{t:t,s:s,why:why,mandate:mandate}
  }).sort(function(a,b){return b.s-a.s});
  // ---- players ----
  var tvBy={};tv.forEach(function(r){tvBy[r.Player+"|"+r.Team]=r});
  var ccBy={};cc.forEach(function(r){ccBy[r.Player+"|"+r.Team]=r});
  var crunch=function(t){return STATUS[((capBy[t]||{})["2027-28"]||{}).status]||0};
  var dispute=[],good=[],bad=[];
  cv.forEach(function(p){
    var k=p.Player+"|"+p.Team,c=ccBy[k]||{},v=tvBy[k]||{},sur=N(p.healthy_surplus_m),sal=N(p.salary_m),small=/small/.test(p.flag||"");
    if(small)return;
    var next=c["2027-28"],opt=c.option_years||"",rookie=p.rookie_scale==="True";
    var free=!next||next==="0"?(rookie?"restricted free agent":"free agent"):/2027-28:PO/.test(opt)?"player option":/2027-28:TO/.test(opt)?"team option":"";
    var age=N(v.Age);
    if(free&&free!=="team option"&&sur>=6&&age&&age<33){var cr=crunch(p.Team);dispute.push({p:p,s:sur+cr*4,why:free+" after this season, worth "+m(sur)+" over his $"+sal.toFixed(1)+"M"+(cr?"; "+NAMES[p.Team]+" "+((capBy[p.Team]||{})["2027-28"]||{}).status+" next year":"")})}
    var yl=N(v.years_left),R=rec[p.Team]||{w:0,l:0},g=R.w+R.l,pct=g?R.w/g:.5;
    if(yl>=3&&sur>=8&&g>=5&&pct<.4&&!rookie)good.push({p:p,s:sur,why:yl+" years left, "+m(sur)+" of value on a "+R.w+"-"+R.l+" team"});
    if(yl>=3&&N(v.trade_value_m)<-40)bad.push({p:p,s:-N(v.trade_value_m),why:yl+" years at $"+sal.toFixed(1)+"M, trade value "+m(N(v.trade_value_m))});
  });
  var srt=function(a){return a.sort(function(x,y){return y.s-x.s})};
  return{teams:teams,dispute:srt(dispute),good:srt(good),bad:srt(bad),NAMES:NAMES,href:function(x){return "gm.html#"+new URLSearchParams({team:x.t,mandate:x.mandate,why:NAMES[x.t]+": "+(x.why.slice(0,3).join(" · ")||"a little of everything")}).toString()}}
})};
})();

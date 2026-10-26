// Play-style fit, shared by every page. Each player gets a score in nine style roles from NBA.com
// play-type and tracking data; a team's supply of a role is the minutes-weighted average of its roster.
// A trade fits when it fills roles the team is short on without piling onto ones it already has.
// Usage: await StyleFit.ready; StyleFit.trade("WAS",["Out Name"],["In Name"]) -> {score,label,reasons,...}
(function(){
  var ROLES=[
    {k:"creator",w:1.0,name:"shot creation",need:"on-ball shot creation",dup:"another on-ball creator"},
    {k:"shooter",w:1.0,name:"shooting",need:"catch-and-shoot shooting",dup:"more spot-up shooting than it needs"},
    {k:"rim",w:0.8,name:"rim pressure",need:"drives and finishing at the rim",dup:"another driver in a crowded paint"},
    {k:"playmaker",w:0.8,name:"playmaking",need:"passing and playmaking",dup:"another lead passer"},
    {k:"roller",w:0.5,name:"rim running",need:"a roll man and cutter",dup:"another rim runner"},
    {k:"rebounder",w:0.6,name:"rebounding",need:"rebounding",dup:"more size on the glass"},
    {k:"rimprot",w:0.8,name:"rim protection",need:"rim protection",dup:"a second rim protector"},
    {k:"post",w:0.3,name:"post scoring",need:"a post scorer",dup:"more post-ups"},
    {k:"disruptor",w:0.4,name:"steals and deflections",need:"perimeter disruption",dup:"more gamblers"}
  ];
  var USAGE_W=0.6,HOLE=1,DUP=0.35;
  var P={},byTeam={},TS={},teamGapFixed={},sdS={},mS={},ready=false,res,rej;
  var readyP=new Promise(function(a,b){res=a;rej=b});

  function parseCSV(t){
    var rows=t.trim().split("\n").map(function(l){var out=[],cur="",q=false;l=l.replace(/\r$/,"");for(var i=0;i<l.length;i++){var c=l[i];if(c==='"')q=!q;else if(c===","&&!q){out.push(cur);cur=""}else cur+=c}out.push(cur);return out});
    var h=rows.shift();return rows.map(function(r){var o={};h.forEach(function(k,i){o[k]=r[i]==null?"":r[i]});return o});
  }
  function num(v){return v===""||v==null||isNaN(+v)?null:+v}
  function zfun(vals){var v=vals.filter(function(x){return x!=null}),m=v.reduce(function(a,b){return a+b},0)/v.length,sd=Math.sqrt(v.reduce(function(a,b){return a+(b-m)*(b-m)},0)/v.length)||1;return function(x){return x==null?0:(x-m)/sd}}
  function shrink(v,n,prior,k){return v==null?prior:(v*n+prior*k)/(n+k)}
  function clamp(x,a,b){return Math.max(a,Math.min(b,x))}

  function build(ps,cv,ts,lg){
    var proj={};cv.forEach(function(r){proj[r.Player+"|"+r.Team]=num(r.proj_MP)||0});
    var rows=ps.map(function(r){var o={name:r.Player,team:r.Team,mp:num(r.mp)||0,season:r.season};
      var f=function(k){return num(r[k])||0},fq=function(k){return num(r[k+"_freq"])||0},pp=function(k){return num(r[k+"_ppp"])};
      var g=o.mp/36||1;
      o.usg=num(r.usg_pct)||0.18;
      var cpo=(num(r.prbh_poss)||0)+(num(r.iso_poss)||0),cpts=(pp("prbh")||0)*(num(r.prbh_poss)||0)+(pp("iso")||0)*(num(r.iso_poss)||0);
      o.creVol=o.usg*(fq("prbh")+fq("iso"));o.creEff=shrink(cpo?cpts/cpo:null,cpo,0.88,60);
      o.csVol=f("cs_fga_pg");o.csEff=shrink(num(r.cs_efg),f("cs_fga_pg")*Math.max(g/2,1),0.53,6);
      o.rimAtt=f("ra_fga_share")*f("fga_pg");o.drives=f("drives_pg");o.raEff=shrink(num(r.ra_fg_pct),o.rimAtt*Math.max(g/2,1),0.66,8);
      o.ast=num(r.ast_pct)||0;o.astPts=f("ast_pts_created_pg");
      o.rollVol=(fq("prroll")+fq("cut")+fq("putback"))*o.usg;
      o.reb=num(r.reb_pct)||0;
      o.blk=num(r.blk_pct)||0;o.rimD=f("rim_dfga_pg");o.rimDEff=shrink(num(r.rim_dfg_pct),o.rimD*Math.max(g/2,1),0.64,10);
      o.postVol=fq("post")*o.usg;o.stl=num(r.stl_pct)||0;
      o.w=Math.max(proj[r.Player+"|"+r.Team]||0,0);o.rel=o.mp/(o.mp+400);
      return o});
    var base=rows.filter(function(o){return o.mp>=500});
    var Z={};["creVol","creEff","csVol","csEff","rimAtt","drives","raEff","ast","astPts","rollVol","reb","blk","rimD","rimDEff","postVol","stl","usg"].forEach(function(k){Z[k]=zfun(base.map(function(o){return o[k]}))});
    rows.forEach(function(o){var z=function(k){return Z[k](o[k])},s={};
      s.creator=0.75*z("creVol")+0.45*z("creEff")*clamp(z("creVol")+1,0,2)/2;
      s.shooter=0.45*z("csVol")+0.65*z("csEff");
      s.rim=0.45*z("rimAtt")+0.35*z("drives")+0.3*z("raEff");
      s.playmaker=0.7*z("ast")+0.4*z("astPts");
      s.roller=z("rollVol");
      s.rebounder=z("reb");
      s.rimprot=0.6*z("blk")+0.35*z("rimD")-0.3*z("rimDEff")*clamp(o.rimD/2,0,1);
      s.post=z("postVol");
      s.disruptor=z("stl");
      for(var k in s)s[k]=clamp(s[k],-2.5,3.5)*o.rel;
      o.s=s;o.u=z("usg")*o.rel;P[o.name]=o;(byTeam[o.team]=byTeam[o.team]||[]).push(o.name)});
    // team-level style stats that sharpen a need (fixed through a trade)
    var tz={},T=ts.filter(function(r){return r.Team});
    function tzf(k,f){var vals=T.map(function(r){return f?f(r):num(r[k])});var zz=zfun(vals);T.forEach(function(r,i){(tz[r.Team]=tz[r.Team]||{})[k]=zz(vals[i])})}
    tzf("cs_efg");tzf("three",function(r){return (num(r.corner3_fga_share)||0)+(num(r.atb3_fga_share)||0)});tzf("ra_fga_share");
    tzf("cre",function(r){var a=num(r.off_prbh_freq)||0,b=num(r.off_iso_freq)||0;return a+b?((num(r.off_prbh_ppp)||0)*a+(num(r.off_iso_ppp)||0)*b)/(a+b):null});
    tzf("off_oreb_pct");tzf("def_oreb_pct");tzf("passes_pg");tzf("def_tov_pct");tzf("drtg");
    T.forEach(function(r){var z=tz[r.Team];TS[r.Team]=r;
      teamGapFixed[r.Team]={creator:-z.cre,shooter:-(0.6*z.cs_efg+0.4*z.three),rim:-z.ra_fga_share,playmaker:-z.passes_pg,roller:0,rebounder:-(0.5*z.off_oreb_pct-0.5*z.def_oreb_pct),rimprot:0.5*z.drtg,post:0,disruptor:-z.def_tov_pct}});
    // spread of team supply across the league, to turn supply into a need in standard units
    var sup=Object.keys(byTeam).map(function(t){return supply(byTeam[t])});
    ROLES.concat([{k:"usage"}]).forEach(function(R){var v=sup.map(function(s){return s[R.k]});var m=v.reduce(function(a,b){return a+b},0)/v.length;mS[R.k]=m;sdS[R.k]=Math.sqrt(v.reduce(function(a,b){return a+(b-m)*(b-m)},0)/v.length)||1});
  }
  // minutes-weighted role averages; players with no projection still count a little
  function supply(names){var W=0,s={usage:0};ROLES.forEach(function(R){s[R.k]=0});
    names.forEach(function(n){var o=P[n];if(!o)return;var w=Math.max(o.w,150);W+=w;ROLES.forEach(function(R){s[R.k]+=w*o.s[R.k]});s.usage+=w*o.u});
    if(W)for(var k in s)s[k]/=W;return s}
  function gaps(team,names){var s=supply(names),fx=teamGapFixed[team]||{},g={};
    ROLES.forEach(function(R){g[R.k]=clamp(0.65*(-(s[R.k]-mS[R.k])/sdS[R.k])+0.35*(fx[R.k]||0),-2.5,2.5)});
    g.usage=(s.usage-mS.usage)/sdS.usage;return g}
  function cost(g){var c=0;ROLES.forEach(function(R){var x=g[R.k];c+=R.w*(x>0?HOLE*x*x:DUP*x*x)});if(g.usage>0)c+=USAGE_W*g.usage*g.usage;return c}
  function rosterOf(team,opt){return (opt&&opt.roster)||byTeam[team]||[]}
  function label(s){return s>=4?"Great fit":s>=1.5?"Good fit":s>-1.5?"Neutral fit":s>-4?"Awkward fit":"Poor fit"}
  function rankOf(team,k){var t=Object.keys(byTeam).map(function(x){return{t:x,g:gaps(x,byTeam[x])[k]}}).sort(function(a,b){return a.g-b.g});for(var i=0;i<t.length;i++)if(t[i].t===team)return i+1;return null}

  // How well one player's strengths line up with a team's needs (need measured without him).
  function match(o,g){var parts=ROLES.map(function(R){var p=Math.max(o.s[R.k],0),x=g[R.k];return{R:R,v:R.w*p*(x>0?x:0.5*x)}});return{v:parts.reduce(function(s,q){return s+q.v},0),parts:parts}}
  function share(o){return clamp(Math.max(o.w,300)/2000,0.2,1.3)}
  // Fit of a trade for one team: incoming players scored against the roster they join, minus what the
  // outgoing players were filling. Quality is left to trade value; this is only about the role mix.
  function trade(team,outs,ins,opt){
    if(!ready)return null;
    outs=(outs||[]).filter(function(n){return P[n]});ins=(ins||[]).filter(function(n){return P[n]});
    var before=rosterOf(team,opt),core=before.filter(function(n){return outs.indexOf(n)<0}),gc=gaps(team,core),pool=[],raw=0;
    var per=ins.map(function(n){var o=P[n],m=match(o,gc),a=share(o),v=a*m.v;raw+=v;m.parts.forEach(function(q){pool.push({n:n,R:q.R,v:a*q.v,dir:1})});return{name:n,score:Math.round(10*Math.tanh(v/2.5)*10)/10,roles:topRoles(n)}});
    outs.forEach(function(n){var o=P[n],m=match(o,gaps(team,before.filter(function(x){return x!==n}))),a=share(o);raw-=a*m.v;m.parts.forEach(function(q){pool.push({n:n,R:q.R,v:-a*q.v,dir:-1})})});
    var g1=gaps(team,core.concat(ins)),g0=gaps(team,before);
    if(g1.usage>0.8&&g1.usage>g0.usage+0.25)raw-=0.6*(g1.usage-Math.max(g0.usage,0.8));
    var score=Math.round(10*Math.tanh(raw/4)*10)/10,reasons=[];
    pool.filter(function(q){return Math.abs(q.v)>0.15}).sort(function(x,y){return Math.abs(y.v)-Math.abs(x.v)}).slice(0,3).forEach(function(q){
      if(q.dir>0)reasons.push(q.v>0?{good:true,text:q.n+" adds "+q.R.need+(gc[q.R.k]>0.6?", a weak spot":"")}:{good:false,text:q.n+" is "+q.R.dup});
      else reasons.push(q.v<0?{good:false,text:"Losing "+q.n+" leaves less "+q.R.name}:{good:true,text:q.n+"'s "+q.R.name+" was doubled up anyway"})});
    if(g1.usage>0.8&&g1.usage>g0.usage+0.25)reasons.push({good:false,text:"Too many players who need the ball"});
    return{team:team,score:score,label:label(score),reasons:reasons,players:per,before:g0,after:g1};
  }
  function topRoles(n){var o=P[n];if(!o)return[];return ROLES.map(function(R){return{k:R.k,name:R.name,v:o.s[R.k]}}).filter(function(x){return x.v>=0.8}).sort(function(a,b){return b.v-a.v}).slice(0,3).map(function(x){return x.name})}
  // Roster balance for team grades: 100 means no holes and no big pile-ups.
  function balance(team,opt){if(!ready)return null;var g=gaps(team,rosterOf(team,opt)),c=cost(g);
    var needs=ROLES.filter(function(R){return g[R.k]>0.6}).sort(function(a,b){return g[b.k]-g[a.k]}).map(function(R){return R.name});
    var strengths=ROLES.filter(function(R){return g[R.k]<-0.6}).sort(function(a,b){return g[a.k]-g[b.k]}).map(function(R){return R.name});
    return{score:Math.round(clamp(100-9*c,0,100)),needs:needs,strengths:strengths,gaps:g}}
  function profile(n){var o=P[n];if(!o)return null;return{name:n,team:o.team,season:o.season,mp:o.mp,roles:topRoles(n),scores:o.s}}

  window.StyleFit={ready:readyP,trade:trade,balance:balance,profile:profile,label:label,roles:ROLES,has:function(n){return !!P[n]},roster:function(t){return (byTeam[t]||[]).slice()},teams:function(){return Object.keys(byTeam)}};
  Promise.all(["player_styles","contract_value","team_styles","team_styles_league"].map(function(n){return fetch("data/"+n+".csv").then(function(r){if(!r.ok)throw new Error(n);return r.text()})}))
    .then(function(t){build(parseCSV(t[0]),parseCSV(t[1]),parseCSV(t[2]),parseCSV(t[3])[0]);ready=true;res(window.StyleFit);document.dispatchEvent(new Event("stylefit"))})
    .catch(function(e){console.warn("Style fit unavailable:",e.message);res(null)});
})();

// Shared top bar for every page of the app: page links plus the team picked on "My team".
(function(){
  // Five sections, each with its own tab row; [href, label, page key]
  var SECTIONS=[["Home",[["home.html","Home","landing"]]],
    ["My team",[["index.html#home","Roster & value","home"],["capsheet.html","Cap sheet","capsheet"],["styles.html","Play styles","styles"]]],
    ["League",[["index.html#players","Players","players"],["index.html#teams","Teams & standings","teams"],["outlook.html","Outlook","outlook"],["tough.html","Tough spots","tough"],["grader.html","Transactions","grader"],["sentiment.html","Sentiment","sentiment"]]],
    ["Front office",[["index.html#trade","Trade machine","trade"],["gm.html","Be the GM","gm"],["desk.html","AI GM","desk"],["offseason.html","Offseason","offseason"]]],
    ["Games",[["predict.html","Predictions","predict"],["sim.html","Season sim","sim"],["series.html","Starting 5","series"],["guess.html","Guess the player","guess"]]]];
  var page=(document.currentScript&&document.currentScript.dataset.page)||"";
  var css=".appnav{display:flex;align-items:center;gap:6px 14px;flex-wrap:wrap;padding:8px max(16px,env(safe-area-inset-right,0px)) 8px max(16px,env(safe-area-inset-left,0px));background:#16212D;color:#fff;font:500 13px 'IBM Plex Sans',system-ui,-apple-system,sans-serif;line-height:1.3;position:relative;z-index:40}"+
    ".appnav a{text-decoration:none}"+
    ".appnav .brand{font:700 16px 'Barlow Condensed','Arial Narrow',system-ui,sans-serif;letter-spacing:.06em;text-transform:uppercase;color:#fff;white-space:nowrap}"+
    ".appnav .links{display:flex;gap:2px;flex-wrap:nowrap;overflow-x:auto;min-width:0;flex:1 1 auto;scrollbar-width:none}"+
    ".appnav .links::-webkit-scrollbar{display:none}"+
    ".appnav .links a{color:#C9D3DE;padding:5px 9px;border-radius:5px;white-space:nowrap}"+
    ".appnav .links a:hover{color:#fff;background:rgba(255,255,255,.09)}"+
    ".appnav .links a[aria-current=page]{background:#C2410C;color:#fff}"+
    ".appnav .links a:focus-visible,.appnav .mt:focus-visible,.appnav .brand:focus-visible{outline:2px solid #F08A4B;outline-offset:2px}"+
    ".appnav .mt{display:flex;align-items:center;gap:6px;color:#fff;white-space:nowrap;font-size:12.5px}"+
    ".appnav .mt img{width:22px;height:22px;object-fit:contain;background:#fff;border-radius:50%;padding:1px}"+
    ".appnav .mt select{font:600 12.5px 'IBM Plex Sans',system-ui,sans-serif;color:#fff;background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.25);border-radius:5px;padding:4px 6px;max-width:190px;cursor:pointer}"+
    ".appnav .mt select option{color:#16212D;background:#fff}"+
    ".appnav .mt select:focus-visible{outline:2px solid #F08A4B;outline-offset:2px}"+
    ".appnav .tabs{order:4;flex-basis:100%;display:flex;gap:2px;overflow-x:auto;scrollbar-width:none;border-top:1px solid rgba(255,255,255,.12);padding-top:6px;margin-top:2px}"+
    ".appnav .tabs::-webkit-scrollbar{display:none}"+
    ".appnav .tabs a{color:#C9D3DE;padding:3px 9px;border-radius:999px;white-space:nowrap;font-size:12.5px}"+
    ".appnav .tabs a:hover{color:#fff}.appnav .tabs a[aria-current=page]{color:#fff;box-shadow:inset 0 0 0 1px #F08A4B}"+
    "@media (max-width:640px){.appnav .links{order:3;flex-basis:100%}.appnav .mt{margin-left:auto}}";
  var st=document.createElement("style");st.textContent=css;document.head.appendChild(st);
  var nav=document.createElement("nav");nav.className="appnav";nav.setAttribute("aria-label","App pages");
  function current(){if(page!=="ledger")return page;var h=(location.hash||"#home").slice(1).split("/")[0];return h==="player"?"players":h||"home"}
  function team(){try{return localStorage.getItem("myTeam")}catch(e){return null}}
  var TEAMS={ATL:"Atlanta Hawks",BOS:"Boston Celtics",BRK:"Brooklyn Nets",CHO:"Charlotte Hornets",CHI:"Chicago Bulls",CLE:"Cleveland Cavaliers",DAL:"Dallas Mavericks",DEN:"Denver Nuggets",DET:"Detroit Pistons",GSW:"Golden State Warriors",HOU:"Houston Rockets",IND:"Indiana Pacers",LAC:"LA Clippers",LAL:"Los Angeles Lakers",MEM:"Memphis Grizzlies",MIA:"Miami Heat",MIL:"Milwaukee Bucks",MIN:"Minnesota Timberwolves",NOP:"New Orleans Pelicans",NYK:"New York Knicks",OKC:"Oklahoma City Thunder",ORL:"Orlando Magic",PHI:"Philadelphia 76ers",PHO:"Phoenix Suns",POR:"Portland Trail Blazers",SAC:"Sacramento Kings",SAS:"San Antonio Spurs",TOR:"Toronto Raptors",UTA:"Utah Jazz",WAS:"Washington Wizards"};
  // Your-team switcher: every page reads the saved team on load, so a change reloads the page
  function teamPicker(t){
    var ok=t&&TEAMS[t];
    return '<label class="mt" title="Your team">'+(ok?'<img src="logos/'+t+'.png" alt="">':"")+'<select aria-label="Your team">'+(ok?"":'<option value="">Pick your team</option>')+
      Object.keys(TEAMS).sort(function(a,b){return TEAMS[a].localeCompare(TEAMS[b])}).map(function(k){return '<option value="'+k+'"'+(k===t?" selected":"")+">"+TEAMS[k]+"</option>"}).join("")+"</select></label>";
  }
  nav.addEventListener("change",function(e){if(e.target.matches(".mt select")&&e.target.value){try{localStorage.setItem("myTeam",e.target.value)}catch(_){}location.reload()}});
  function draw(){
    var cur=current(),t=team();
    var sec=SECTIONS.filter(function(s){return s[1].some(function(p){return p[2]===cur})})[0];
    nav.innerHTML='<a class="brand" href="home.html">NBA Asset Tracker</a><div class="links">'+SECTIONS.map(function(s){return '<a href="'+s[1][0][0]+'"'+(s===sec?' aria-current="page"':"")+">"+s[0]+"</a>"}).join("")+"</div>"+
      (sec&&sec[1].length>1?'<div class="tabs">'+sec[1].map(function(p){return '<a href="'+p[0]+'"'+(p[2]===cur?' aria-current="page"':"")+">"+p[1]+"</a>"}).join("")+"</div>":"")+
      teamPicker(t);
    var on=nav.querySelector(".tabs [aria-current]"),ls=nav.querySelector(".tabs");if(on&&ls&&ls.scrollWidth>ls.clientWidth)ls.scrollLeft=Math.max(0,on.offsetLeft-ls.offsetLeft-24);
  }
  document.body.insertBefore(nav,document.body.firstChild);draw();
  window.addEventListener("hashchange",draw);
  window.addEventListener("storage",function(e){if(e.key==="myTeam")draw()});
  window.appNav={refresh:draw,team:team,setTeam:function(t){try{t?localStorage.setItem("myTeam",t):localStorage.removeItem("myTeam")}catch(e){}draw()}};
})();

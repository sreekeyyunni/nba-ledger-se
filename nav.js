// Shared top bar for every page of the app: page links plus the team picked on "My team".
(function(){
  var PAGES=[["index.html#home","My team","home"],["index.html#players","Players","players"],["index.html#teams","Teams","teams"],["index.html#trade","Trade machine","trade"],["gm.html","Be the GM","gm"],["desk.html","AI GM","desk"],["grader.html","Transactions","grader"],["offseason.html","Offseason","offseason"],["capsheet.html","Cap sheet","capsheet"],["styles.html","Play styles","styles"],["sim.html","Season sim","sim"],["series.html","Starting 5","series"],["predict.html","Predictions","predict"],["sentiment.html","Sentiment","sentiment"],["guess.html","Guess the player","guess"]];
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
    "@media (max-width:640px){.appnav .links{order:3;flex-basis:100%}.appnav .mt{margin-left:auto}}";
  var st=document.createElement("style");st.textContent=css;document.head.appendChild(st);
  var nav=document.createElement("nav");nav.className="appnav";nav.setAttribute("aria-label","App pages");
  function current(){if(page!=="ledger")return page;var h=(location.hash||"#home").slice(1).split("/")[0];return h==="player"?"players":h||"home"}
  function team(){try{return localStorage.getItem("myTeam")}catch(e){return null}}
  function draw(){
    var cur=current(),t=team();
    nav.innerHTML='<a class="brand" href="index.html#home">NBA Asset Tracker</a><div class="links">'+PAGES.map(function(p){return '<a href="'+p[0]+'"'+(p[2]===cur?' aria-current="page"':"")+">"+p[1]+"</a>"}).join("")+"</div>"+
      (t&&/^[A-Z]{3}$/.test(t)?'<a class="mt" href="index.html#home" title="Your team"><img src="logos/'+t+'.png" alt="">'+t+"</a>":'<a class="mt" href="index.html#home">Pick your team</a>');
    var on=nav.querySelector("[aria-current]"),ls=nav.querySelector(".links");if(on&&ls&&ls.scrollWidth>ls.clientWidth)ls.scrollLeft=Math.max(0,on.offsetLeft-ls.offsetLeft-24);
  }
  document.body.insertBefore(nav,document.body.firstChild);draw();
  window.addEventListener("hashchange",draw);
  window.addEventListener("storage",function(e){if(e.key==="myTeam")draw()});
  window.appNav={refresh:draw,team:team,setTeam:function(t){try{t?localStorage.setItem("myTeam",t):localStorage.removeItem("myTeam")}catch(e){}draw()}};
})();

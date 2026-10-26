/*
 Season simulator: plays out the rest of the 2026-27 season thousands of times
 from sim_data.json (written by sim_data.py) and counts how often each team
 makes the play-in, the playoffs, each round and the title.

   const data = await (await fetch("data/sim_data.json")).json();
   SeasonSim.run(data, {sims: 5000})                 -> odds per team
   SeasonSim.compare(data, [{player: "Bradley Beal", to: "WAS"}])
                                                     -> before/after odds for a trade
 A move with to: null takes the player off his team (waived, injured for the year).

 Game model is predict.py's: home margin = home rating - away rating + home
 court - back-to-back penalty, win probability = normal CDF(margin / 11.5).
 Each simulated season also nudges every team's rating by a random amount
 (team_sd, 2 points) because ratings this early are uncertain; without it the
 odds come out far too sure. Ties in the standings are broken by coin flip.
 Every season uses its own seed, so a trade and the baseline see the same
 luck and the difference is the trade, not noise.
*/
(function (root) {
  "use strict";

  function rng(seed) {             // mulberry32
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function normal(r) {
    let u = r();
    while (u === 0) u = r();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * r());
  }

  function cdf(x) {                // normal CDF (Abramowitz-Stegun 7.1.26 erf)
    const z = Math.abs(x) / Math.SQRT2, t = 1 / (1 + 0.3275911 * z);
    const erf = 1 - t * (0.254829592 + t * (-0.284496736 + t * (1.421413741 + t * (-1.453152027 + t * 1.061405429)))) * Math.exp(-z * z);
    return x >= 0 ? 0.5 * (1 + erf) : 0.5 * (1 - erf);
  }

  // predict.py's team_rating: minutes go to players in order of minutes per game until 240
  function teamRating(data, roster) {
    const p = data.params;
    const pool = roster.map(x => [x[2], x[3] * x[4]]).sort((a, b) => b[1] - a[1]);
    let minutes = 0, ws = 0;
    for (const [ws48, mpg] of pool) {
      const m = Math.min(mpg, 240 - minutes);
      if (m <= 0) break;
      minutes += m;
      ws += ws48 * m / 48;
    }
    ws += p.replacement_ws48 * (240 - minutes) / 48;
    return ((ws - 0.5) * p.points_per_win_pct - p.mean_raw) * p.spread;
  }

  function applyMoves(data, moves) {
    const byName = new Map(data.players.map(x => [x[0].toLowerCase(), x]));
    const players = data.players.map(x => x.slice());
    const index = new Map(players.map((x, i) => [x[0].toLowerCase(), i]));
    const touched = new Set();
    for (const mv of moves || []) {
      const i = index.get(String(mv.player).toLowerCase());
      if (i === undefined || !byName.has(String(mv.player).toLowerCase())) throw new Error("unknown player: " + mv.player);
      touched.add(players[i][1]);
      if (mv.to) { players[i][1] = mv.to; touched.add(mv.to); }
      else players[i][1] = null;
    }
    return {players, touched};
  }

  // rest-of-season rating per team (roster + form), after any moves
  function ratings(data, moves) {
    const {players, touched} = applyMoves(data, moves);
    const out = {};
    for (const [t, info] of Object.entries(data.teams)) {
      const roster = touched.has(t) ? teamRating(data, players.filter(x => x[1] === t)) : info.roster;
      out[t] = roster + info.form;
    }
    return out;
  }

  function seriesWinner(r, hi, lo, R, p) {   // best of 7, hi has home court (2-2-1-1-1)
    const homeHi = [1, 1, 0, 0, 1, 0, 1];
    let a = 0, b = 0, g = 0;
    while (a < 4 && b < 4) {
      const m = (r[hi] - r[lo]) + (homeHi[g] ? p.home_court : -p.home_court);
      if (R() < cdf(m / p.margin_sd)) a++; else b++;
      g++;
    }
    return a === 4 ? hi : lo;
  }

  function game(r, home, away, R, p) {        // single game, true if home wins
    return R() < cdf((r[home] - r[away] + p.home_court) / p.margin_sd);
  }

  function run(data, opts) {
    opts = opts || {};
    const sims = opts.sims || 5000, seed = opts.seed || 20262027, p = data.params;
    const base = ratings(data, opts.moves);
    const teams = Object.keys(data.teams);
    const id = new Map(teams.map((t, i) => [t, i]));
    const n = teams.length;
    const games = data.games.map(g => [id.get(g[1]), id.get(g[2]), g[3], g[4]]);
    const conf = {E: [], W: []};
    teams.forEach((t, i) => conf[data.teams[t].conf].push(i));
    const zero = () => new Float64Array(n);
    const s = {wins: zero(), playin: zero(), top6: zero(), playoffs: zero(), semis: zero(),
               confFinals: zero(), finals: zero(), title: zero()};
    const seeds = teams.map(() => new Float64Array(15));
    const r = new Float64Array(n), w = new Float64Array(n);

    for (let k = 0; k < sims; k++) {
      const R = rng(seed + k * 7919);
      for (let i = 0; i < n; i++) {
        r[i] = base[teams[i]] + p.team_sd * normal(R);
        w[i] = data.teams[teams[i]].w;
      }
      for (const [a, h, b2bA, b2bH] of games) {
        const m = r[h] - r[a] + p.home_court - p.back_to_back * b2bH + p.back_to_back * b2bA;
        if (R() < cdf(m / p.margin_sd)) w[h]++; else w[a]++;
      }
      for (let i = 0; i < n; i++) s.wins[i] += w[i];

      const champs = [];
      for (const c of ["E", "W"]) {
        const tie = new Map(conf[c].map(i => [i, R()]));
        const order = conf[c].slice().sort((x, y) => (w[y] - w[x]) || (tie.get(y) - tie.get(x)));
        order.forEach((t, i) => { seeds[t][i]++; if (i < 6) s.top6[t]++; else if (i < 10) s.playin[t]++; });
        // play-in: 7 v 8 for the 7 seed; loser hosts the 9 v 10 winner for the 8 seed
        const [s7, s8, s9, s10] = order.slice(6, 10);
        const win78 = game(r, s7, s8, R, p) ? s7 : s8, lose78 = win78 === s7 ? s8 : s7;
        const win910 = game(r, s9, s10, R, p) ? s9 : s10;
        const eighth = game(r, lose78, win910, R, p) ? lose78 : win910;
        const bracket = order.slice(0, 6).concat([win78, eighth]);
        bracket.forEach(t => s.playoffs[t]++);
        const better = (x, y) => (w[x] > w[y] || (w[x] === w[y] && tie.get(x) > tie.get(y))) ? [x, y] : [y, x];
        const play = (x, y) => { const [hi, lo] = better(x, y); return seriesWinner(r, hi, lo, R, p); };
        const q = [play(bracket[0], bracket[7]), play(bracket[3], bracket[4]),
                   play(bracket[2], bracket[5]), play(bracket[1], bracket[6])];
        q.forEach(t => s.semis[t]++);
        const f = [play(q[0], q[1]), play(q[2], q[3])];
        f.forEach(t => s.confFinals[t]++);
        const champ = play(f[0], f[1]);
        s.finals[champ]++;
        champs.push(champ);
      }
      const [e, wc] = champs;
      const hi = w[e] >= w[wc] ? e : wc;     // Finals home court by record
      s.title[seriesWinner(r, hi, hi === e ? wc : e, R, p)]++;
    }

    const out = {};
    teams.forEach((t, i) => {
      const info = data.teams[t];
      out[t] = {conf: info.conf, rating: +base[t].toFixed(2), w: info.w, l: info.l,
                projW: +(s.wins[i] / sims).toFixed(1),
                playin: s.playin[i] / sims, top6: s.top6[i] / sims, playoffs: s.playoffs[i] / sims,
                semis: s.semis[i] / sims, confFinals: s.confFinals[i] / sims,
                finals: s.finals[i] / sims, title: s.title[i] / sims,
                seeds: Array.from(seeds[i], x => x / sims)};
      out[t].projL = +(info.w + info.l + data.games.filter(g => g[1] === t || g[2] === t).length - out[t].projW).toFixed(1);
    });
    return {teams: out, sims};
  }

  // before/after odds for a set of moves; same seeds, so deltas are the moves' effect
  function compare(data, moves, opts) {
    opts = Object.assign({}, opts);
    const before = run(data, Object.assign({}, opts, {moves: []}));
    const after = run(data, Object.assign({}, opts, {moves}));
    const delta = {};
    for (const t of Object.keys(before.teams)) {
      const b = before.teams[t], a = after.teams[t], d = {};
      for (const k of ["rating", "projW", "playin", "top6", "playoffs", "semis", "confFinals", "finals", "title"]) d[k] = a[k] - b[k];
      delta[t] = d;
    }
    return {before: before.teams, after: after.teams, delta, touched: [...applyMoves(data, moves).touched].filter(Boolean)};
  }

  const api = {run, compare, ratings, teamRating};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SeasonSim = api;
})(typeof window !== "undefined" ? window : this);

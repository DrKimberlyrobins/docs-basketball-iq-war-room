'use strict';

const $ = id => document.getElementById(id);
const escape = value => String(value ?? '—').replace(/[&<>"']/g, char => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
})[char]);
const formatTime = date => new Intl.DateTimeFormat('en-US', {
  hour: 'numeric', minute: '2-digit', timeZone: 'America/Chicago', timeZoneName: 'short'
}).format(new Date(date));
const formatDate = date => new Intl.DateTimeFormat('en-US', {
  weekday: 'long', month: 'long', day: 'numeric', year: 'numeric', timeZone: 'UTC'
}).format(new Date(date + 'T12:00:00Z'));
const link = (label, url) => /^https:\/\//.test(url) ? `<a href="${escape(url)}">${escape(label)}</a>` : escape(label);
const logo = team => /^https:\/\//.test(team.logo) ? `<img src="${escape(team.logo)}" alt="" loading="lazy">` : '';
const panel = (title, content) => `<section class="panel"><h3>${escape(title)}</h3>${content}</section>`;
const table = (columns, rows, cls = '') => `<div class="scroll" tabindex="0" role="region" aria-label="${escape(columns[0])} table"><table class="${cls}"><thead><tr>${columns.map(col => `<th scope="col">${escape(col)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr><th scope="row">${escape(row[0])}</th>${row.slice(1).map(value => `<td>${escape(value)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
const pair = (game, values) => game.teams.map((team, idx) => `${escape(team.name)} ${escape(values[idx])}`).join(' · ');
const signed = number => number > 0 ? `+${number}` : String(number);

function playerPanel(team) {
  const stats = team.stats;
  const labels = [
    ['expected', 'Minutes'], ['points', 'Scoring'], ['reb', 'Rebounding'], ['ast', 'Playmaking']
  ];
  const leaders = labels.map(([key, label]) =>
    `<p><strong>${label}</strong> ${team.top[key].map(p => `${escape(p.name)} (${p.value})`).join(' · ') || '—'}</p>`
  ).join('');
  const starters = team.players.filter(p => p.role === 'Projected starter');
  const bench = team.players.filter(p => p.role !== 'Projected starter' && p.expected >= 8);
  return `<div><h3>${logo(team)}${escape(team.name)}</h3>
    <p><strong>Projected five</strong> ${escape(starters.map(p => p.name).join(', ') || 'Unavailable')}</p>
    <p><strong>Primary bench</strong> ${escape(bench.map(p => p.name).join(', ') || 'Unavailable')}</p>
    ${leaders}
    <p class="muted">Adjusted offense ${escape(stats.adjO)} · Defense ${escape(stats.adjD)} · Tempo ${escape(stats.pace)}</p>
    <p class="muted">Opponent strength ${escape(stats.sos)} (${stats.sosGames} rated opponents across ${stats.sample} box scores)</p>
    <p>${team.availability ? `${link('RotoWire availability', team.availability.source)} observed ${formatTime(team.availability.checked)}` : 'Availability source pending'}</p>
    ${team.alerts.map(alert => `<p class="status">${escape(alert)}</p>`).join('')}
  </div>`;
}

function playerTable(team) {
  const rows = team.players.map(p => [
    p.name,p.pos,p.status,p.role,p.expected,p.minutes,p.logs.map(n => n ?? '—').join(' / '),p.gp,
    p.points,p.fga,p.three,p.fta,p.reb,p.oreb,null,p.ast,null,p.usage,p.to,p.blk,p.tendencies
  ]);
  return panel(`${team.name} player intelligence`, table([
    'Player','Pos','Availability','Rotation','Proj min','Avg min','Last five min','GP','PTS','FGA','3PA','FTA',
    'REB','OREB','REB chances','AST','Potential AST','Est. USG%','TO','BLK','Observed tendencies'
  ],rows,'players') + `<p class="sources">${link('ESPN team schedule',team.source)} · ${team.logs.map(g => link(g.opponent,g.url)).join(' · ')}</p>`);
}

function scouting(game) {
  if (game.scouting) return panel('Scouting read',`<p>${escape(game.scouting.read)}</p><p><strong>Watch</strong> ${escape(game.scouting.watch)}</p><p class="sources">${game.scouting.sources.map(([label,url]) => link(label,url)).join(' · ')}</p>`);
  const lines = game.teams.map(team => {
    const {fga, fta, oreb, ast, blk, three} = team.top;
    const leaders = [[fga,'shot attempts'],[fta,'free-throw attempts'],[oreb,'offensive rebounds'],[ast,'assists'],[blk,'blocks'],[three,'three-point attempts']];
    const tendencies = leaders.filter(([values]) => values[0]?.value > 0).map(([values, stat]) => `${values[0].name} leads in ${stat} (${values[0].value}/g)`);
    return `<p><strong>${escape(team.name)}</strong> ${escape(tendencies.join(' · ') || 'Insufficient box scores')}</p>`;
  });
  const unavailable = game.teams.flatMap(team => team.players.filter(p => p.status.includes('Out')).map(p => p.name));
  return panel('Box-score scouting read',lines.join('')+`<p><strong>Watch</strong> ${unavailable.length ? `Track the rotation around ${escape(unavailable.join(', '))} and which projected bench players absorb the minutes.` : 'Track whether the expected lead creators handle the ball against pressure and whether the leading offensive rebounders win second chances.'} Shooting swings, foul trouble and late lineup news can shift the score.</p>`);
}

function show(game, history) {
  const receipt = history[game.id];
  const prediction = game.projection || receipt?.projection;
  const forecastStamp = game.projection ? '' : receipt ? ' · Saved '+formatTime(receipt.captured) : '';
  const market = game.market || receipt?.market;
  const grade = receipt?.grade;
  const firstHalf = game.halfMarket || receipt?.halfMarket?.quote;
  $('matchup').innerHTML = `<div class="headline"><div><h2>${game.teams.map(t => escape(t.name)).join(' vs. ')}</h2>
    <p class="muted">${formatTime(game.tip)} · ${escape(game.venue)} · ${game.neutral ? 'Neutral court' : 'Home court'} · ${link('ESPN game center',game.source)}</p></div></div>
    ${panel('Lineups and rotation leaders', `<div class="leaders">${game.teams.map(playerPanel).join('')}</div>`)}
    ${scouting(game)}
    ${panel('Matchup comparison',table(['Category',...game.teams.map(t=>t.name),'Measure'],game.comparison.map(r=>[r.label,...r.values.map(v=>v==null?null:Math.round(v*10)/10),r.meaning])))}
    ${prediction ? panel('Independent projection',`<div class="score-grid"><div class="score">First half<strong>${pair(game,prediction.half)}</strong>Total ${prediction.halfTotal}</div>
    <div class="score">Full game<strong>${pair(game,prediction.full)}</strong>Total ${prediction.total} · ${escape(prediction.winner)}</div></div>
    <p class="muted">About ${prediction.pace} possessions per team${forecastStamp}. ${prediction.margin<=2 ? 'The projected margin is two points or less and can flip with a single possession.' : 'Scoring depends on the projected minutes and the teams’ shot conversion.'}</p>`) : panel('Independent projection','No eligible forecast available.')}
    ${market ? panel('Sportsbook comparison',`<p>${escape(market.provider)} via ESPN · observed ${formatTime(market.observed)}</p>
      <p>${pair(game,market.spread.map(signed))} · Full-game total ${market.total}</p>
      <p><strong>Model side</strong> ${market.side ? `${escape(market.side)} ${signed(market.spreadLine)} (${market.spreadGap}-point difference)` : 'Even at displayed precision'}</p>
      <p><strong>Model total</strong> ${market.totalDirection ? `${escape(market.totalDirection)} ${market.total} (${market.totalGap}-point difference)` : 'Even at displayed precision'}</p>`) : ''}
    ${firstHalf ? panel('First-half sportsbook comparison',`<p>${escape(firstHalf.provider)} via ${link('Maddux Sports',firstHalf.source)} · observed ${formatTime(firstHalf.observed)}</p>
      <p>${pair(game,firstHalf.spread.map(signed))} · 1H total ${firstHalf.total}</p>
      <p><strong>Model side</strong> ${firstHalf.sideIndex == null ? 'Even at displayed precision' : `${escape(game.teams[firstHalf.sideIndex].name)} ${signed(firstHalf.spread[firstHalf.sideIndex])} (${firstHalf.spreadGap}-point difference)`}</p>
      <p><strong>Model total</strong> ${firstHalf.totalDirection ? `${firstHalf.totalDirection} ${firstHalf.total} (${firstHalf.totalGap}-point difference)` : 'Even at displayed precision'}</p>`) : ''}
    ${grade ? panel('Final and grade',`<p>${pair(game,grade.final)} · total missed by ${grade.gameError} · side ${escape(grade.spreadResult)} · total ${escape(grade.totalResult)} · 1H side ${escape(grade.halfSpreadResult)} · 1H total ${escape(grade.halfTotalResult)}</p>`) : ''}
    ${game.teams.map(playerTable).join('')}`;
  document.querySelectorAll('.game').forEach(button => button.setAttribute('aria-current',String(button.dataset.id === game.id)));
}

function render(board, history) {
  $('day').textContent = formatDate(board.date);
  $('asof').textContent = `${board.matchups.length} games · research snapshot ${formatTime(board.captured)}`;
  $('games').innerHTML = board.matchups.map(g => `<button class="game" type="button" data-id="${escape(g.id)}"><small>${formatTime(g.tip)} · ${escape(g.state)}</small>${g.teams.map(team=>`<span>${logo(team)}${escape(team.name)}</span>`).join('')}</button>`).join('');
  const initial = board.matchups.find(g => '#' + g.id === location.hash) ?? board.matchups[0];
  if (initial) show(initial,history);
  else $('matchup').textContent = 'No men’s Division I games listed for this date.';
  $('games').addEventListener('click', event => {
    const id = event.target.closest('button')?.dataset.id;
    const game = board.matchups.find(g => g.id === id);
    if (!game) return;
    window.history.replaceState(null,'','#'+id);
    show(game,history);
  });
  const receipts = Object.values(history).sort((a,b) => b.tip.localeCompare(a.tip));
  $('records').innerHTML = table(['Matchup','Tip (CT)','Saved (CT)','1H forecast','Game forecast','Full final','Winner grade','ATS','Total'],
    receipts.map(r => [r.names.join(' vs. '),new Intl.DateTimeFormat('en-CA',{timeZone:'America/Chicago'}).format(new Date(r.tip))+' '+formatTime(r.tip),formatTime(r.captured),r.projection.half.join('–'),r.projection.full.join('–'),r.grade?.final.join('–'),
      r.grade?.winnerCorrect == null ? null : r.grade.winnerCorrect ? 'Correct' : 'Miss',r.grade?.spreadResult,r.grade?.totalResult]));
  $('methodology').innerHTML = `<p>${link('CBS schedule',board.scheduleSource)} · ${link('Bart Torvik team ratings',board.ratingSource)}. ESPN supplies the player box scores and final scores. RotoWire supplies depth-chart projections and availability where found. Availability remains unconfirmed unless a source explicitly confirms it.</p>
    <p>Player averages are per appearance in the available season box scores. Last-five logs run oldest to newest. Blank entries indicate no recorded appearance or an unavailable metric. Minutes blend recent and season minutes, with reduced weight for a player missing the previous game and zero minutes when reported out. Game-time-decision minutes assume the player participates.</p>
    <p>Estimated usage is the player’s share of team shot, free-throw and turnover actions adjusted for floor time. Free-throw attempts indicate foul-line activity. Rebounding chances, contested rebounds, potential assists, individual assignments, returning-player designations, rotation experience and film-based decision quality are not consistently available.</p>
    <p>Scores blend opponent-adjusted efficiencies and tempo with projected rotation scoring. First-half scores use each team’s prior first-half scoring share. The model has no calibrated probabilities. Market figures come after the independent projection. First-half quotes use the book named by Maddux Sports. Kambi, team-total quotes and alternates are not integrated.</p>
    <p>The grade uses the first saved pregame receipt. Full-game grades include overtime. The matchup can show a newer pregame forecast while the original dated receipt remains in history.</p>`;
}

$('print').addEventListener('click',() => window.print());
if (window.IQ_SNAPSHOT) {
  render(window.IQ_SNAPSHOT.board,window.IQ_SNAPSHOT.history);
} else {
  Promise.all(['board','history'].map(async name => {
    const response = await fetch(`data/${name}.json`,{cache:'no-cache'});
    if (!response.ok) throw new Error(name);
    return response.json();
  })).then(([board,history]) => render(board,history)).catch(() => {
    $('asof').textContent = 'The matchup data could not be loaded.';
  });
}

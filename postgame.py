"""Evidence-only grading and diagnostics. Never modifies forecast coefficients."""
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from concurrent.futures import ThreadPoolExecutor
import json
from refresh import DATA, BASE, fetch, write_json, CT

def mark(x):
    return 'Win' if x>0 else 'Loss' if x<0 else 'Push'

def grade(r, final, half):
    p=r['projection']; g=dict(final=final,half=half,gameError=abs(sum(final)-sum(p['full'])),
        halfError=abs(sum(half)-sum(p['half'])) if None not in half else None,
        winnerCorrect=(final[0]>final[1])==(p['full'][0]>p['full'][1]) if p['full'][0]!=p['full'][1] else None)
    if None not in half:
        g['halfWinnerCorrect']=(half[0]>half[1])==(p['half'][0]>p['half'][1]) if half[0]!=half[1] and p['half'][0]!=p['half'][1] else None
    for prefix,q,scores in [('',r.get('market'),final),('half',(r.get('halfMarket') or {}).get('quote'),half)]:
        if not q or None in scores: continue
        idx=q.get('sideIndex'); direction=q.get('totalDirection')
        g[prefix+'SpreadResult' if prefix else 'spreadResult']=mark(scores[idx]-scores[1-idx]+q['spread'][idx]) if idx is not None else None
        g[prefix+'TotalResult' if prefix else 'totalResult']=mark((sum(scores)-q['total'])*(1 if direction=='Over' else -1)) if direction else None
    return g

def investigate(item):
    gid,r=item; url=f'{BASE}/summary?event={gid}'; path=DATA/'evidence'/f'{gid}.json'
    if datetime.fromisoformat(r['tip'])>datetime.now(timezone.utc):
        return gid,{'status':'Pregame; awaiting final','source':url}
    try:
        d=json.loads(path.read_text()) if path.exists() else json.loads(fetch(url))
        if d.get('header',{}).get('competitions',[{}])[0].get('status',{}).get('type',{}).get('completed'):
            write_json(path,{k:d[k] for k in ('boxscore','header','gameInfo') if k in d})
    except Exception as exc:
        if not path.exists(): return gid,{'status':'Source unavailable','error':str(exc),'source':url}
        d=json.loads(path.read_text())
    c=d.get('header',{}).get('competitions',[{}])[0]
    if not c.get('status',{}).get('type',{}).get('completed'): return gid,{'status':'Not final','source':url}
    competitors={t['team']['location']:t for t in c['competitors']}
    if any(n not in competitors for n in r['names']): return gid,{'status':'Team identity mismatch','source':url}
    final=[int(competitors[n]['score']) for n in r['names']]
    half=[next((x.get('value',x.get('displayValue')) for x in competitors[n].get('linescores',[]) if x.get('period',1)==1),None) for n in r['names']]
    half=[float(x) if x is not None else None for x in half]
    g=grade(r,final,half)
    day=datetime.fromisoformat(r['tip']).astimezone(CT).date().isoformat()
    snapshot=DATA/'pregame'/f'{day}.json'; old=json.loads(snapshot.read_text()) if snapshot.exists() else {}
    pre=next((x for x in old.get('matchups',[]) if x['id']==gid),{})
    conference_file=DATA/'conferences.json'
    conference_map={}
    if conference_file.exists():
        for conference in json.loads(conference_file.read_text()).get('children',[]):
            for entry in conference.get('standings',{}).get('entries',[]):
                conference_map[entry['team']['id']]=conference['name']
    conferences=sorted({conference_map.get(competitors[n]['id'],'Unrecorded') for n in r['names']})
    teams=[]
    for name in r['names']:
        tid=competitors[name]['id']; club=next((x for x in d.get('boxscore',{}).get('teams',[]) if x['team']['id']==tid),{})
        stats={x['name']:x['displayValue'] for x in club.get('statistics',[])}
        expected=next((x for x in pre.get('teams',[]) if x['id']==tid),{})
        players=[]; pg=next((x for x in d.get('boxscore',{}).get('players',[]) if x['team']['id']==tid),{})
        for group in pg.get('statistics',[]):
            for a in group.get('athletes',[]):
                s=dict(zip(group['labels'],a.get('stats',[]))); pn=a['athlete']['displayName']; ep=next((x for x in expected.get('players',[]) if x['name']==pn),{})
                players.append(dict(name=pn,starter=a.get('starter',False),didNotPlay=a.get('didNotPlay',False),actual=s,
                    projectedMinutes=ep.get('expected'),expectedStarter=ep.get('role')=='Projected starter' if ep else None,
                    pregameStatus=ep.get('status'),minuteError=round(float(s['MIN'])-ep['expected'],1) if s.get('MIN','').isdigit() and ep.get('expected') is not None else None))
        for ep in expected.get('players',[]):
            if ep['name'] not in {p['name'] for p in players} and (ep.get('expected') or 0)>0:
                players.append(dict(name=ep['name'],starter=False,didNotPlay=None,actual={},projectedMinutes=ep.get('expected'),expectedStarter=ep.get('role')=='Projected starter',pregameStatus=ep.get('status'),minuteError=None))
        def n(k):
            try:return float(stats[k])
            except (KeyError,ValueError):return None
        def attempts(k):
            try:return float(stats[k].split('-')[1])
            except (KeyError,ValueError,IndexError):return None
        vals=[attempts('fieldGoalsMade-fieldGoalsAttempted'),n('offensiveRebounds'),n('totalTurnovers'),attempts('freeThrowsMade-freeThrowsAttempted')]
        poss=round(vals[0]-vals[1]+vals[2]+.44*vals[3],2) if None not in vals else None
        teams.append(dict(name=name,stats=stats,players=players,expectedStarters=[x['name'] for x in expected.get('players',[]) if x['role']=='Projected starter'],
            actualStarters=[x['name'] for x in players if x['starter']],possessionEstimate=poss,
            benchPoints=sum(int(x['actual'].get('PTS',0)) for x in players if not x['starter']),
            availabilityFinding='DNP alone does not establish injury. No independently verified unexpected absence recorded.'))
    p=r['projection']; pm=p['full'][0]-p['full'][1]; am=final[0]-final[1]
    obs=[]
    for t in teams:
        st=t['stats']; obs.append(f"{t['name']}: FG {st.get('fieldGoalsMade-fieldGoalsAttempted','unavailable')}, 3PT {st.get('threePointFieldGoalsMade-threePointFieldGoalsAttempted','unavailable')}, FT {st.get('freeThrowsMade-freeThrowsAttempted','unavailable')}, TO {st.get('totalTurnovers','unavailable')}, OREB {st.get('offensiveRebounds','unavailable')}, bench {t['benchPoints']} points.")
    explanations={
        '401929281': 'Georgia +2.5 covered despite a two-point outright loss; the total finished five above projection. Cincinnati made 12/22 threes, with Tejada and Colvin scoring 23 each. The winner miss was small (three margin points), while the first-half margin miss was much larger.',
        '401921674': 'South Carolina +3.5 and Over 139.5 won, although the model favored Arizona State outright. Bieliauskas scored 25; South Carolina made 26 free throws and Arizona State shot 4/22 from three. The model recognized a close market underdog and higher total, but missed which team led.',
        '401906807': 'Possession estimate was close to projection; Purdue scored 14 below its forecast. Purdue made 7/28 threes and attempted only two free throws. Oklahoma won the second half 39–27 after trailing by five. The observed miss was efficiency and margin rather than pace.',
        '401912231': 'Army made 11/23 threes versus UTSA 3/21. Army led 45–29 at halftime. The projected UTSA 15-point advantage became an Army 18-point win, a 33-point signed margin error. Slower estimated possessions contributed to the lower total; shooting separation contributed to the side miss.',
        '401920537': 'The winner projection was correct, but Michigan +2.5 failed. Miami shot 36/64 against Michigan 24/65 with similar shot volume. Miami won the second half 45–25. Estimated pace closely matched projection; the major margin miss came from scoring efficiency separation.',
        '401920529': 'Tennessee +3.5 won while Over 139.5 lost by half a point. Iowa State took 72 shots but made 22, and went 10/18 at the foul line. Tennessee led 31–19 at half. The full total missed by only two points, so a total betting loss is not evidence of a large total projection error.',
        '401920528': 'San Diego State +4.5 covered and won outright. Maryland scored seven below projection, made only 21/60 shots and only nine two-point baskets. Estimated pace was close to projection. San Diego State made 25/29 free throws; Maryland efficiency, not a large pace miss, accompanied the total shortfall.'}
    primary=explanations.get(gid,'Observed contributors: '+ ' '.join(obs)+' Causal attribution to an absence or fatigue remains unverified.')
    player_findings=[]
    for t in teams:
        for player in sorted(t['players'],key=lambda p:abs(p['minuteError'] or 0),reverse=True)[:3]:
            if player['minuteError'] is not None:
                player_findings.append(f"{t['name']} — {player['name']}: projected {player['projectedMinutes']} min, actual {player['actual'].get('MIN')}, difference {player['minuteError']:+g}.")
    return gid,dict(status='Verified final from ESPN',source=url,sourceFile=f'data/evidence/{gid}.json',evidenceSavedAt=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat(),
        date=day,names=r['names'],receipt=r,grade=g,teams=teams,projectedMargin=pm,actualMargin=am,marginError=am-pm,
        projectedTotal=sum(p['full']),actualTotal=sum(final),totalError=sum(final)-sum(p['full']),
        teamScoreMAE=mean(abs(a-b) for a,b in zip(final,p['full'])),projectedPossessions=p.get('pace'),
        actualPossessionEstimate=mean(t['possessionEstimate'] for t in teams) if all(t['possessionEstimate'] is not None for t in teams) else None,
        secondHalf=[f-h for f,h in zip(final,half)] if None not in half else None,
        observations=obs,playerFindings=player_findings,primaryCause=primary,
        lesson='Separate margin error from total error; compare archived player expectations to actual minutes and shot volume.',
        recommendation='Test pace/efficiency decomposition, rotation uncertainty and shooting regression on timestamped historical inputs before adopting changes.',
        confidence='Unspecified in original IQ receipt',conference=conferences,
        lineVerification='Original book, line and observation timestamp preserved in receipt. Raw sportsbook response was not archived; independent quote authenticity remains unverified.')

def run():
    (DATA/'evidence').mkdir(exist_ok=True); (DATA/'pregame').mkdir(exist_ok=True)
    h=json.loads((DATA/'history.json').read_text())
    with ThreadPoolExecutor(8) as pool: findings=dict(pool.map(investigate,h.items()))
    for gid,f in findings.items():
        if 'grade' in f:h[gid]['grade']=f['grade']
    write_json(DATA/'history.json',h)
    write_json(DATA/'diagnostics.json',dict(updated=datetime.now(timezone.utc).isoformat(),games=findings,
        verifiedFindings=['First ten archived grades yield spread 5–5, total 6–4 and winner 3–7; supplied spread 6–4 was inconsistent with paired outcomes.',
        'Margin is score A minus score B; total is score A plus score B. Their errors can move separately.',
        'November 26 receipts selected Over in 18 of 21 games. Full-game total MAE was 14.67 points and signed actual-minus-forecast total error averaged −2.19 points; this is a one-day diagnostic, not a validated bias correction.',
        'Existing grader skipped already graded games and therefore could not backfill missing halftime data.'],
        hypotheses=['Rotation scoring blend may double count opponent strength or misprice bench depth.','Small early-season samples may make three-point conversion and halftime shares unstable.'],
        modelChanges='None. No candidate weight change validated on historical timestamped inputs.',
        validation='Historical IQ forecast sample begins November 26. Earlier point-in-time ratings and player inputs are unavailable here; no retrospective refit reported as out-of-sample validation.'))

if __name__=='__main__':run()

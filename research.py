"""Build the player and matchup report from timestamped pregame inputs."""
from collections import defaultdict
from datetime import datetime, timezone
from difflib import get_close_matches
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo
import html, json, os, re, unicodedata

ROOT = Path(os.environ.get('IQ_INPUTS', Path(__file__).resolve().parent / 'inputs'))
SITE = Path(__file__).resolve().parent / 'site'
CT = ZoneInfo('America/Chicago')
NOW = datetime.now(timezone.utc)
DAY = os.environ.get('IQ_DATE', NOW.astimezone(CT).date().isoformat())
BASE = 'https://www.espn.com/mens-college-basketball'
RWB = 'https://www.rotowire.com/daily/ncaab/lineups.php?site=DraftKings'

def load(path):
    return json.loads(path.read_text())

def key(s):
    s = re.sub(r'(?i)\s+(jr\.?|sr\.?|ii|iii|iv|v)$', '', s)
    return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', s.lower()).encode('ascii','ignore').decode())

def rw_data():
    lookup = {}
    for p in sorted(ROOT.glob('rw*.html')):
        source = RWB + ('&slateID=' + p.stem[2:] if p.stem != 'rw' else '')
        stamp = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()
        for card in p.read_text().split('<div class="lineup is-nfl">')[1:]:
            if not re.search(r'lineup__time.*?' + datetime.fromisoformat(DAY).strftime('%m/%d'), card):
                continue
            names = re.findall(r'class="lineup__logo"[^>]+alt="([^"]+)"', card)[:2]
            lists = re.findall(r'class="lineup__list is-(?:visit|home)"[^>]*>(.*?)</ul>',card,re.S)
            for name, lineup in zip(names,lists):
                starters, injuries = (lineup.split('>Injuries</li>',1)+[''])[:2]
                def players(section):
                    return [dict(name=html.unescape(n), pos=pos.strip(), status=st.strip()) for pos,n,st in
                            re.findall(r'lineup__pos"[^>]*>([^<]+)</div>\s*<a title="([^"]+)"[^>]*>[^<]+</a>\s*<span class="lineup__ir">([^<]*)</span>',section)]
                lookup[key(html.unescape(name))] = dict(source=source, checked=stamp, starters=players(starters), injuries=players(injuries))
    return lookup

def attempt(s):
    return int(s.split('-')[1])

def intstat(s):
    return int(s) if s.isdigit() else 0

def norm_rating(name):
    aliases = {'miami':'Miami FL','omaha':'Nebraska Omaha','ut san antonio':'UTSA','army west point':'Army','saint mary\'s':'Saint Mary\'s','st. john\'s':'St. John\'s','jacksonville state':'Jacksonville St.','michigan state':'Michigan St.','arizona state':'Arizona St.','san diego state':'San Diego St.','iowa state':'Iowa St.','utah state':'Utah St.','kansas state':'Kansas St.'}
    return key(aliases.get(name.lower(),name))

rw = rw_data()
ratings = {key(row[1]):row for row in load(ROOT/'torvik.json')}
hist = defaultdict(list)
for p in (ROOT/'raw').glob('game*.json'):
    d=load(p)
    comp=d.get('header',{}).get('competitions',[{}])[0]
    if not comp.get('status',{}).get('type',{}).get('completed') or datetime.fromisoformat(comp['date']) >= NOW:
        continue
    box=d.get('boxscore',{})
    bteams={t['team']['id']:{x['name']:x['displayValue'] for x in t['statistics']} for t in box.get('teams',[])}
    scores={t['id']:t for t in comp['competitors']}
    if len(scores)!=2:
        continue
    for t in box.get('players',[]):
        tid=t['team']['id']
        oth=next(i for i in scores if i!=tid)
        rows=[]
        for group in t['statistics']:
            for a in group['athletes']:
                if a.get('didNotPlay') or not a['stats']:
                    continue
                person=a['athlete']
                stats=dict(zip(group['labels'],a['stats']))
                if not {'MIN','PTS','FG','3PT','FT','REB','OREB','AST','TO','BLK','STL'} <= stats.keys():
                    continue
                mins=intstat(stats['MIN'])
                rows.append(dict(id=person['id'], name=person['displayName'], position=person.get('position',{}).get('abbreviation','—'),
                          starter=a.get('starter',False), minutes=mins, points=intstat(stats['PTS']),
                          fga=attempt(stats['FG']), three=attempt(stats['3PT']), fta=attempt(stats['FT']),
                          reb=intstat(stats['REB']), oreb=intstat(stats['OREB']), ast=intstat(stats['AST']),
                          to=intstat(stats['TO']), blk=intstat(stats['BLK']), stl=intstat(stats['STL'])))
        if not rows:
            continue
        def defstats(i):
            z=bteams.get(i,{})
            return [float(z[k]) if k in z else None for k in ('pointsInPaint','threePointFieldGoalPct')]
        total_minutes=sum(a['minutes'] for a in rows)
        team_actions=sum(a['fga']+.44*a['fta']+a['to'] for a in rows)
        for a in rows:
            a['actions']=a['fga']+.44*a['fta']+a['to']
        half=scores[tid].get('linescores',[])
        hist[tid].append(dict(id=comp['id'],date=comp['date'],players=rows,minutes=total_minutes, actions=team_actions,
            half=int(half[0]['displayValue']) if half else None, score=int(scores[tid]['score']),
            opponent=scores[oth]['team']['location'], opponentDefense=defstats(oth)))

def rounded(n):
    return round(n,1)

def assess(t):
    tid=t['id']
    club=t['team']
    name=club['location']
    games=sorted(hist[tid],key=lambda g:g['date'])
    matches=[key(name),key(club.get('shortDisplayName','')),norm_rating(name)]
    for original, alias in [('Pittsburgh','Pitt'),('Saint Mary’s','Saint Marys'),('Connecticut','UConn'),('St. John’s','St. Johns'),('Jacksonville State','Jacksonville St')]:
        if key(name)==key(original): matches.append(key(alias))
    source=next((rw[k] for k in matches if k in rw),None)
    rating=next((ratings[k] for k in matches if k in ratings),None)
    last=games[-5:]
    names={}
    records=defaultdict(list)
    for g in games:
        for a in g['players']:
            k=key(a['name'])
            names[k]=a['name']
            records[k].append((g,a))
    def match(n):
        k=key(n)
        if k in names:
            return k
        surname=key(re.sub(r'(?i)\s+jr\.?$', '', n).split()[-1])
        alike=[p for p,q in names.items() if key(re.sub(r'(?i)\s+jr\.?$', '', q).split()[-1])==surname and p[0]==k[0]]
        return alike[0] if len(alike)==1 else k
    slots=[match(a['name']) for a in source['starters']] if source else []
    listed_injuries={match(a['name']):a for a in source['injuries']} if source else {}
    out={k for k,a in listed_injuries.items() if a['status'] in ('Out','OFS')}
    validated=len(slots)==len(set(slots))==5 and not set(slots)&out
    observed=[key(a['name']) for a in games[-1]['players'] if a['starter'] and key(a['name']) not in out] if games else []
    first=slots if validated else observed
    pmap={match(a['name']):a['pos'] for a in source['starters']} if source else {}
    for k,a in listed_injuries.items():
        names.setdefault(k,a['name'])
    for a in source['starters'] if source else []:
        names.setdefault(match(a['name']),a['name'])
    players=[]
    for k,n in names.items():
        rec=records[k]
        rows=[a for g,a in rec]
        mins=sum(a['minutes'] for a in rows)
        expected_actions=sum(g['actions']*a['minutes']/(g['minutes']/5) for g,a in rec if g['minutes'])
        avgs={f:rounded(mean(a[f] for a in rows)) if rows else None for f in ('minutes','points','fga','three','fta','reb','oreb','ast','to','blk','stl')}
        dated={g['id']:a['minutes'] for g,a in rec}
        logs=[dated.get(g['id']) for g in last]
        recent=[m for m in logs if m is not None]
        prediction=0 if k in out else (.65*mean(recent)+.35*avgs['minutes']) if recent else None
        if prediction is not None and prediction > 0 and logs and logs[-1] is None:
            prediction*=.6
        status=listed_injuries.get(k,{}).get('status') or ('GTD' if source and any(match(a['name'])==k and a['status']=='GTD' for a in source['starters']) else 'Unconfirmed')
        players.append(dict(name=n, pos=pmap.get(k) or (rows[-1]['position'] if rows else listed_injuries.get(k,{}).get('pos','—')),
            status={'GTD':'Game-time decision','OFS':'Out for season'}.get(status,status),
            role='Projected starter' if k in first else 'Bench / depth', expected=prediction, logs=logs, gp=len(rows),
            usage=rounded(100*sum(a['actions'] for a in rows)/expected_actions) if expected_actions else None,
            **avgs))
    total=sum(p['expected'] or 0 for p in players)
    for p in players:
        if p['expected'] and total:
            p['expected']=rounded(min(40,200*p['expected']/total))
    players.sort(key=lambda p:(p['role']!='Projected starter',-(p['expected'] or 0)))
    rotation=[p for p in players if (p['expected'] or 0)>=8 or p['role']=='Projected starter']
    def leaders(f):
        return sorted([p for p in rotation if p[f] is not None and p['status'] not in ('Out','Out for season')],key=lambda p:p[f],reverse=True)[:2]
    top={f:[{'name':p['name'],'value':p[f]} for p in leaders(f)] for f in ('points','reb','ast','expected','fga','fta','oreb','blk','three')}
    for p in players:
        clues=[]
        for stat,label in [('fga','shot volume'),('fta','free-throw volume'),('oreb','offensive rebounding'),('ast','recorded assists'),('blk','blocks'),('three','three-point attempts')]:
            if p[stat] and any(x['name']==p['name'] for x in top[stat]):
                clues.append(f"Top two in {label} ({p[stat]:g}/game)")
        if (p['expected'] or 0)>=20 and p['fga'] is not None and p['fga']<=4:
            clues.append('Low shot volume for expected floor time')
        if (p['expected'] or 0)>=20 and p['ast'] is not None and p['ast']<=1:
            clues.append('Limited recorded assists for expected floor time')
        p['tendencies']=' · '.join(clues) if clues else 'See box-score profile'
    def avg_def(i):
        v=[g['opponentDefense'][i] for g in games if g['opponentDefense'][i] is not None]
        return rounded(mean(v)) if v else None
    opp_ratings=[ratings[norm_rating(g['opponent'])] for g in games if norm_rating(g['opponent']) in ratings]
    halves=[g['half']/g['score'] for g in games if g['half'] is not None and g['score']]
    alerts=[]
    if source and not validated: alerts.append('RotoWire lineup contains a duplicate or unavailable starter. Using prior starters as a fallback.')
    if validated and observed and set(first)!=set(observed): alerts.append('RotoWire projection differs from the most recent documented starting five.')
    if not source: alerts.append('Prior starts used for projection. No RotoWire slate entry matched.')
    if sum(p['role']=='Projected starter' for p in players)<5: alerts.append('Fewer than five starters could be projected from available evidence.')
    for p in players:
        if p['status'] not in ('Unconfirmed','Out','Out for season'): alerts.append(f"{p['name']} is a game-time decision. Minutes are conditional on playing.")
    return dict(name=name, id=tid, logo=club['logo'], players=players, top=top, alerts=alerts,
                availability=source and {k:source[k] for k in ('source','checked')}, lastStarters=[names[k] for k in observed],
                stats=dict(sample=len(games), adjO=rounded(rating[4]) if rating else None,adjD=rounded(rating[6]) if rating else None,
                pace=rounded(rating[-1]) if rating else None, sos=rounded(mean(r[4]-r[6] for r in opp_ratings)) if opp_ratings else None,
                sosGames=len(opp_ratings), paint=avg_def(0), perimeter=avg_def(1), halfShare=mean(halves) if halves else None),
                source=f'{BASE}/team/schedule/_/id/{tid}/season/2027', logs=[{'opponent':g['opponent'],'url':f'{BASE}/boxscore/_/gameId/{g["id"]}'} for g in last])

def projection(teams, neutral):
    a,b=teams
    sa,sb=a['stats'],b['stats']
    if any(s[k] is None for s in (sa,sb) for k in ('adjO','adjD','pace')):
        return None
    center=mean(r[4] for r in ratings.values())
    pace=mean([sa['pace'],sb['pace']])
    full=[]
    for team,own,opp,home in [(a,sa,sb,-1),(b,sb,sa,1)]:
        rotation=[p for p in team['players'] if p['expected'] and p['minutes'] and p['points'] is not None]
        points=sum(p['expected']*p['points']/p['minutes'] for p in rotation)
        baseline=(own['adjO']+opp['adjD']-center)*pace/100
        value=.78*baseline+.22*points if len(rotation)>=6 else baseline
        full.append(round(value+(0 if neutral else home*1.5)))
    half=[round(v*(.49 if s['halfShare'] is None else .49+.5*(s['halfShare']-.49))) for v,s in zip(full,(sa,sb))]
    return dict(full=full, half=half, pace=rounded(pace), total=sum(full), halfTotal=sum(half), margin=abs(full[0]-full[1]),
                winner=teams[full[1]>full[0]]['name'] if full[0]!=full[1] else 'Even at displayed precision')

def compare(teams):
    a,b=teams
    rows=[]
    for label, field in [('Primary scorers','points'),('Rebounders','reb'),('Playmakers','ast')]:
        values=[sum(x['value'] for x in t['top'][field]) if len(t['top'][field])==2 else None for t in teams]
        rows.append(dict(label=label,values=values,meaning='Combined per-game averages of the two leaders'))
    for label,role in [('Starting five','Projected starter'),('Bench','Bench / depth')]:
        vals=[]
        for t in teams:
            pool=[p for p in t['players'] if p['role']==role and (p['expected'] or 0)>=8 and p['points'] is not None and p['minutes']]
            vals.append(rounded(sum(p['points']*p['expected']/p['minutes'] for p in pool)) if len(pool)>=(5 if role=='Projected starter' else 2) else None)
        rows.append(dict(label=label,values=vals,meaning='Projected scoring contribution only'))
    for label,k in [('Interior defense','paint'),('Perimeter defense','perimeter')]:
        rows.append(dict(label=label,values=[t['stats'][k] for t in teams],meaning='Opponent paint points per game' if k=='paint' else 'Opponent three-point FG percentage'))
    return rows

def build():
    board=load(ROOT/'espn.json')
    notes=load(SITE/'data'/'scouting-notes.json')
    matchups=[]
    for event in sorted(board['events'],key=lambda e:e['date']):
        c=event['competitions'][0]
        tip=datetime.fromisoformat(event['date'])
        if tip.astimezone(CT).date().isoformat()!=DAY:
            continue
        ts=[assess(t) for t in sorted(c['competitors'],key=lambda t:t['homeAway'])]
        projected=projection(ts,c.get('neutralSite',False)) if tip>NOW and event['status']['type']['name']=='STATUS_SCHEDULED' else None
        matchups.append(dict(id=event['id'],tip=event['date'],venue=c.get('venue',{}).get('fullName'),neutral=c.get('neutralSite',False),
           source=f'{BASE}/game/_/gameId/{event["id"]}', teams=ts,projection=projected, comparison=compare(ts),
           scouting=notes.get(event['id']), state=event['status']['type']['description'],
           final=[int(t['score']) for t in sorted(c['competitors'],key=lambda t:t['homeAway'])] if event['status']['type']['completed'] and all(str(t.get('score','')).isdigit() for t in c['competitors']) else None))
    return dict(date=DAY,captured=NOW.isoformat(),ratingSource='https://barttorvik.com/trank.php?year=2027',
        scheduleSource='https://www.cbssports.com/college-basketball/schedule/ALL/'+DAY.replace('-','')+'/', matchups=matchups)

if __name__ == '__main__':
    report=build()
    (SITE/'data'/'board.json').write_text(json.dumps(report,indent=2)+'\n')
    for g in report['matchups']:
        print(datetime.fromisoformat(g['tip']).astimezone(CT).strftime('%H:%M'),[t['name'] for t in g['teams']],[(t['stats']['sample'],t['availability'] is not None,t['stats']['adjO'],len(t['players'])) for t in g['teams']],g['projection'] and g['projection']['full'])

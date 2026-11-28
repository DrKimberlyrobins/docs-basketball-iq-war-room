"""Refresh the slate, archive the first pregame forecast, and grade finals."""
import concurrent.futures
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import urllib.request
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parent
DATA = PROJECT / 'site' / 'data'
CT = ZoneInfo('America/Chicago')
BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball'
RW = 'https://www.rotowire.com/daily/ncaab/lineups.php?site=DraftKings'

def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent':'BasketballIQBoard/1.0'})
    return urllib.request.urlopen(request, timeout=15).read()

def scoreboard(day):
    return json.loads(fetch(f'{BASE}/scoreboard?dates={day.replace("-", "")}&groups=50&limit=500'))

def season(day):
    d = datetime.fromisoformat(day)
    return d.year + (d.month >= 7)

def write_json(path, data):
    path.write_text(json.dumps(data, indent=2)+'\n')

def download(root, target, url, cache=False):
    path = root / target
    if cache and path.exists():
        return json.loads(path.read_text())
    try:
        content = fetch(url)
        data = json.loads(content) if path.suffix=='.json' else content.decode()
        path.write_bytes(content)
        return data
    except (OSError,ValueError) as exc:
        print(f'{target}: {exc}')
        if path.exists() and path.suffix=='.json':
            return json.loads(path.read_text())
        return {}

def gather_ratings(root, day):
    year = season(day)
    cache = DATA / f'torvik-{year}.json'
    url = f'https://barttorvik.com/{year}_team_results.json'
    try:
        rows = json.loads(fetch(url))
        if not isinstance(rows, list) or not rows or not all(
            isinstance(row, list) and len(row) >= 8 and isinstance(row[1], str)
            and all(isinstance(row[i], (int, float)) for i in (4, 6, -1))
            for row in rows
        ):
            raise ValueError('Unexpected team ratings format')
        cached = dict(observed=datetime.now(timezone.utc).isoformat(), rows=rows)
        cache.write_text(json.dumps(cached, separators=(',', ':')) + '\n')
        observed = None
    except (OSError, ValueError) as exc:
        print(f'{url}: {exc}')
        cached = json.loads(cache.read_text()) if cache.exists() else dict(rows=[], observed=None)
        observed = cached['observed']
        print(f'Using ratings retrieved at {observed}.' if observed else 'No saved season ratings available.')
    write_json(root/'torvik.json', cached['rows'])
    return observed


def gather(root, day):
    (root/'raw').mkdir(parents=True, exist_ok=True)
    slate = scoreboard(day)
    write_json(root/'espn.json',slate)
    teams = {t['id'] for e in slate['events'] for t in e['competitions'][0]['competitors']}
    ratings_as_of = gather_ratings(root, day)
    for path in root.glob('rw*.html'):
        path.unlink()
    lineups = download(root,'rw.html',RW)
    slates = set(re.findall(r'site=DraftKings&amp;slateID=(\d+)',lineups)) if isinstance(lineups,str) else set()
    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        jobs=[pool.submit(download,root,f'raw/team{i}.json',f'{BASE}/teams/{i}/schedule?season={season(day)}') for i in teams]
        lineup_jobs=[pool.submit(download,root,f'rw{i}.html',f'{RW}&slateID={i}') for i in slates]
        games = {event['id'] for job in jobs for event in job.result().get('events',[])
                 if event['competitions'][0]['status']['type']['completed']
                 and datetime.fromisoformat(event['date']).astimezone(CT).date().isoformat() < day}
        boxes=[pool.submit(download,root,f'raw/game{i}.json',f'{BASE}/summary?event={i}',True) for i in games]
        for job in lineup_jobs+boxes:
            job.result()
    return ratings_as_of

def attach_markets(board, slate, stamp):
    events={e['id']:e for e in slate['events']}
    for game in board['matchups']:
        event=events.get(game['id'])
        if not game['projection'] or not event or event['status']['type']['name']!='STATUS_SCHEDULED':
            continue
        if stamp>=datetime.fromisoformat(event['date']):
            continue
        quotes=event['competitions'][0].get('odds') or []
        quote=next((q for q in quotes if q.get('details') and isinstance(q.get('spread'),(int,float)) and isinstance(q.get('overUnder'),(int,float))),None)
        if not quote:
            continue
        favorite=0 if quote['awayTeamOdds'].get('favorite') else 1
        lines=[abs(quote['spread'])]*2
        lines[favorite]*=-1
        full=game['projection']['full']
        edge=round(full[0]-full[1]+lines[0],1)
        total=round(sum(full)-quote['overUnder'],1)
        name=[t['name'] for t in game['teams']]
        side=0 if edge>0 else 1
        market=dict(provider=quote['provider']['name'], observed=stamp.isoformat(), spread=lines,
            total=quote['overUnder'], side=name[side] if edge else None, sideIndex=side if edge else None, spreadLine=lines[side] if edge else None,
            spreadGap=abs(edge), totalDirection='Over' if total>0 else 'Under' if total<0 else None,totalGap=abs(total))
        game['market']=market

HALF_SOURCE = 'https://madduxsports.com/college-basketball-lines-1st-half.php'

def attach_first_half(board, page, stamp):
    payload=re.search(r'var data = (\{[^\n]+\});',page)
    if not payload:
        return
    odds=json.loads(payload[1])
    aliases={'texassanantonio':'utsa','centralflorida':'ucf','miamiflorida':'miami','saintmarysca':'saintmarys','nebraskaomaha':'omaha'}
    def normalize(name):
        name=re.sub('[^a-z0-9]','',name.lower())
        return aliases.get(name,name)
    fixtures={}
    for event in odds.get('schedulers',[]):
        names=tuple(normalize(n) for n in re.split(r'<br\s*/?>',event['team_names']))
        tip=datetime.fromisoformat(event['raw_date'])
        if tip>stamp and not event.get('is_started') and len(names)==2:
            fixtures[(frozenset(names),tip)]=(event,names)
    for game in board['matchups']:
        if not game['projection']:
            continue
        names=tuple(normalize(t['name']) for t in game['teams'])
        match=fixtures.get((frozenset(names),datetime.fromisoformat(game['tip'])))
        if not match:
            continue
        event,ordered=match
        for provider,book in [('28','DraftKings'),('41','Circa'),('25','Pinnacle')]:
            quote=event['odds'].get(provider,{}).get('2',{})
            total_text=next((m for k in ('away','home') if (m:=re.fullmatch(r'(\d+(?:\.\d+)?)[uo][+-]\d+',quote.get(k,'')))),None)
            try:
                spread=[float(quote['ps'][f'{side}_spread']) for side in ('away','home')]
            except (KeyError, ValueError, TypeError):
                continue
            quote_time=quote.get('change_time')
            if not total_text or not quote_time or datetime.fromtimestamp(quote_time,timezone.utc)>stamp or sum(spread)!=0:
                continue
            if ordered!=names:
                spread.reverse()
            total=float(total_text[1])
            score=game['projection']['half']
            gap=round(score[0]-score[1]+spread[0],1)
            total_gap=round(sum(score)-total,1)
            idx=0 if gap>0 else 1 if gap<0 else None
            game['halfMarket']=dict(provider=book,source=HALF_SOURCE,observed=stamp.isoformat(),spread=spread,total=total,
                sideIndex=idx,spreadGap=abs(gap),totalDirection='Over' if total_gap>0 else 'Under' if total_gap<0 else None,totalGap=abs(total_gap))
            break

def archive(board, prior_boards):
    path=DATA/'history.json'
    history=json.loads(path.read_text()) if path.exists() else {}
    for game in board['matchups']:
        captured=game.get('projectionAsOf', board['captured'])
        tip=datetime.fromisoformat(game['tip'])
        if not game['projection'] or datetime.fromisoformat(captured)>=tip:
            continue
        market=game.get('market')
        if market and datetime.fromisoformat(market['observed'])>=tip:
            market=None
        receipt=dict(tip=game['tip'],captured=captured, names=[t['name'] for t in game['teams']],
            projection=game['projection'], market=market)
        if game.get('ratingsAsOf'):
            receipt['ratingsAsOf']=game['ratingsAsOf']
        history.setdefault(game['id'],receipt)
        if game.get('halfMarket') and datetime.fromisoformat(game['halfMarket']['observed'])<tip:
            receipt=history[game['id']]
            receipt.setdefault('halfMarket',dict(quote=game['halfMarket'],score=game['projection']['half'],
                projectedAt=captured))
    for slate in prior_boards:
        for event in slate['events']:
            receipt=history.get(event['id'])
            if not receipt or event['status']['type']['name']!='STATUS_FINAL':
                continue
            score={t['team']['location']:t for t in event['competitions'][0]['competitors']}
            if not all(n in score and str(score[n].get('score','')).isdigit() for n in receipt['names']):
                continue
            final=[int(score[n]['score']) for n in receipt['names']]
            half=[(score[n].get('linescores') or [{}])[0].get('value') for n in receipt['names']]
            p=receipt['projection']
            grade=dict(final=final, half=half, gameError=abs(sum(final)-p['total']),
                halfError=abs(sum(half)-p['halfTotal']) if all(isinstance(v,(int,float)) for v in half) else None,
                winnerCorrect=(p['winner']==receipt['names'][final[1]>final[0]]) if p['full'][0]!=p['full'][1] else None)
            q=receipt.get('market')
            if q:
                idx=q['sideIndex']
                def result(margin):
                    return 'Win' if margin>0 else 'Loss' if margin<0 else 'Push'
                grade['spreadResult']=result(final[idx]-final[1-idx]+q['spreadLine']) if idx is not None else None
                grade['totalResult']=result((sum(final)-q['total'])*(1 if q['totalDirection']=='Over' else -1)) if q['totalDirection'] else None
            half_receipt=receipt.get('halfMarket')
            if half_receipt and all(isinstance(v,(int,float)) for v in half):
                quote=half_receipt['quote']
                idx=quote['sideIndex']
                def mark(margin):
                    return 'Win' if margin>0 else 'Loss' if margin<0 else 'Push'
                grade['halfSpreadResult']=mark(half[idx]-half[1-idx]+quote['spread'][idx]) if idx is not None else None
                grade['halfTotalResult']=mark((sum(half)-quote['total'])*(1 if quote['totalDirection']=='Over' else -1)) if quote['totalDirection'] else None
            receipt['grade']=grade
    write_json(path,history)

def main():
    day=datetime.now(CT).date()
    root=Path(os.environ.get('IQ_INPUTS', PROJECT/'inputs')).resolve()
    root.mkdir(parents=True,exist_ok=True)
    os.environ.update(IQ_INPUTS=str(root),IQ_DATE=day.isoformat())
    ratings_as_of=gather(root,day.isoformat())
    import research
    board=research.build()
    if ratings_as_of:
        for game in board['matchups']:
            if game['projection']:
                game['ratingsAsOf']=ratings_as_of
                for team in game['teams']:
                    team['alerts'].append('Bart Torvik ratings retrieved at '+ratings_as_of)
    fresh=scoreboard(day.isoformat())
    stamp=datetime.now(timezone.utc)
    fallback_path=DATA/'pregame'/f'{day.isoformat()}.json'
    fallback=json.loads(fallback_path.read_text()) if fallback_path.exists() else {}
    if fallback.get('date')==day.isoformat():
        saved={g['id']:g for g in fallback.get('matchups',[])}
        for game in board['matchups']:
            prior=saved.get(game['id'])
            if game['projection'] is None and prior and prior.get('projection') and stamp<datetime.fromisoformat(game['tip']):
                game.update({k:prior[k] for k in ('projection','teams','comparison')})
                game['projectionAsOf']=prior.get('projectionAsOf', fallback['captured'])
                if prior.get('ratingsAsOf'):
                    game['ratingsAsOf']=prior['ratingsAsOf']
                for team in game['teams']:
                    team['alerts'].append('Ratings unavailable: projection retained from '+game['projectionAsOf'])
    fresh_events={e['id']:e for e in fresh['events']}
    for game in board['matchups']:
        event=fresh_events.get(game['id'])
        if not event or event['status']['type']['name']!='STATUS_SCHEDULED' or stamp>=datetime.fromisoformat(event['date']):
            game['projection']=None
    attach_markets(board,fresh,stamp)
    try:
        page=fetch(HALF_SOURCE).decode()
        attach_first_half(board,page,datetime.now(timezone.utc))
    except (OSError,ValueError) as exc:
        print(f'First-half quote feed: {exc}')
    snapshot=DATA/'pregame'/f'{day.isoformat()}.json'
    snapshot.parent.mkdir(exist_ok=True)
    if not snapshot.exists():
        write_json(snapshot,board)
    else:
        # Keep each game's first forecast, including games missing from the initial slate.
        saved={game['id']:game for game in fallback.get('matchups',[])}
        for game in board['matchups']:
            prior=saved.get(game['id'])
            if game['projection'] and (not prior or not prior['projection']):
                saved[game['id']]=dict(game, projectionAsOf=game.get('projectionAsOf', board['captured']))
        if list(saved.values())!=fallback.get('matchups',[]):
            write_json(snapshot,dict(fallback, matchups=list(saved.values())))
    prior_boards=[fresh]
    try:
        prior_boards.append(scoreboard((day-timedelta(days=1)).isoformat()))
    except (OSError, ValueError) as exc:
        print(f'Previous-day scoreboard: {exc}')
    archive(board,prior_boards)
    from postgame import run
    run()
    write_json(DATA/'board.json',board)

if __name__=='__main__':
    main()

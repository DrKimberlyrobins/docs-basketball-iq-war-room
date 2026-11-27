"""Deploy the verified Pages artifact through GitHub's REST API."""
import json, os, time, urllib.request, subprocess

def request(url, data=None, token=None):
    if url.startswith('https://api.github.com/'):
        args=['gh','api',url,'-H','Accept: application/vnd.github+json']
        if data is not None:args+=['--method','POST','--input','-']
        response=subprocess.run(args,input=json.dumps(data) if data is not None else None,text=True,capture_output=True,check=True)
        return json.loads(response.stdout)
    headers={'Accept':'application/vnd.github+json','Authorization':'Bearer '+(token or os.environ['GH_TOKEN'])}
    if data is not None:headers['Content-Type']='application/json'
    req=urllib.request.Request(url,data=json.dumps(data).encode() if data is not None else None,headers=headers)
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

base='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']
name=os.environ['PAGES_ARTIFACT']
for attempt in range(12):
    artifacts=request(base+'/actions/runs/'+os.environ['GITHUB_RUN_ID']+'/artifacts')['artifacts']
    matching=[a for a in artifacts if a['name']==name and not a.get('expired')]
    if len(matching)==1:break
    time.sleep(5)
else:raise RuntimeError('Expected exactly one verified Pages artifact')
id_token=request(os.environ['ACTIONS_ID_TOKEN_REQUEST_URL'],token=os.environ['ACTIONS_ID_TOKEN_REQUEST_TOKEN'])['value']
deployment=request(base+'/pages/deployments',{'artifact_id':matching[0]['id'],'pages_build_version':os.environ['GITHUB_SHA'],'oidc_token':id_token})
with open(os.environ['GITHUB_OUTPUT'],'a') as output:output.write('page_url='+deployment['page_url']+'\n')
for attempt in range(60):
    status=request(base+'/pages/deployments/'+str(deployment['id']))
    print('Pages deployment status:',status.get('status'))
    if status.get('status')=='succeed':break
    if status.get('status') in ('succeeded','success'):break
    if status.get('status') in ('failed','cancelled','deployment_failed'):raise RuntimeError('Pages deployment failed')
    time.sleep(5)
else:raise RuntimeError('Pages deployment did not complete within five minutes')
print('Published:',deployment['page_url'])

import os,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from engine import ff

def main():
 with tempfile.TemporaryDirectory() as tmp:
  os.environ['REELFORGE_TOKEN']='integration-test-secret-12345';os.environ['REELFORGE_DATA']=tmp+'/data'
  from fastapi.testclient import TestClient
  from app import app
  c=TestClient(app);headers={'Authorization':'Bearer '+os.environ['REELFORGE_TOKEN']}
  assert c.get('/health').status_code==401
  assert c.get('/health',headers=headers).status_code==200
  v=Path(tmp)/'clip.mp4';a=Path(tmp)/'music.wav'
  ff(['-f','lavfi','-i','color=green:s=180x320:r=30:d=2','-c:v','libx264','-threads','1',v])
  ff(['-f','lavfi','-i','sine=frequency=400:duration=5',a])
  assert c.post('/jobs',headers=headers,data={'config':'{"duration":900}'},files={'clips':('v.mp4',v.read_bytes(),'video/mp4')}).status_code==422
  assert c.post('/jobs',headers=headers,data={'config':'{}'},files={'clips':('v.mp4',v.read_bytes(),'video/mp4')}).status_code==400
  r=c.post('/jobs',headers=headers,data={'config':'{"duration":5}'},files=[('clips',('v.mp4',v.read_bytes(),'video/mp4')),('music',('music.wav',a.read_bytes(),'audio/wav'))]);assert r.status_code==200,r.text
  ident=r.json()['id'];deadline=time.time()+90
  while time.time()<deadline:
   status=c.get('/jobs/'+ident,headers=headers).json()
   if status['status'] in ('done','error'):break
   time.sleep(.1)
  assert status['status']=='done',status
  result=c.get('/jobs/'+ident+'/video',headers=headers);assert result.status_code==200 and len(result.content)>1000
  assert c.get('/jobs/'+ident+'/video').status_code==401
  assert c.delete('/jobs/'+ident,headers=headers).status_code==200
  assert c.get('/jobs/'+ident,headers=headers).status_code==404
  print('PASS authentication, invalid configuration, missing music, upload, asynchronous render, status, protected download, deletion')
if __name__=='__main__':main()

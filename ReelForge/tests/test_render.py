"""Real encoding integration checks, not mocks of FFmpeg."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from engine import ff,render,probe,duration,normalize,join,write_ass,TEMPLATES

def main():
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp); clips=[]
  for i,color in enumerate(['red','blue']):
   p=root/f'input-{i}.mp4'
   ff(['-f','lavfi','-i',f'color=c={color}:s=180x320:r=30:d=3','-f','lavfi','-i','sine=frequency=330:duration=3','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-c:a','aac','-shortest',p]);clips.append(p)
  music=root/'music.wav';ff(['-f','lavfi','-i','sine=frequency=880:duration=6',music])
  for template in TEMPLATES:
   folder=root/template;folder.mkdir()
   out=render(folder,clips,music,{'template':template,'mode':'music','duration':5,'bpm':120,'quality':'720'})
   info=probe(out);v=next(s for s in info['streams'] if s['codec_type']=='video')
   assert (v['width'],v['height'])==(720,1280)
   assert any(s['codec_type']=='audio' for s in info['streams'])
   assert abs(duration(out)-5)<.15,(template,duration(out))
   print('PASS',template,round(duration(out),2))
  folder=root/'speech';folder.mkdir();parts=[]
  for i,p in enumerate(clips):
   part=folder/f'part-{i}.mp4';normalize(p,part,0,1,TEMPLATES['clean'],180,320,True);parts.append(part)
  joined=folder/'joined.mp4';join(parts,joined,'fade',180,320,True)
  assert abs(duration(joined)-2)<.2
  ass=folder/'captions.ass';write_ass(ass,[(0,1,'Привет мир'),(1,2,'Тест речи')],180,320)
  ff(['-i',joined,'-vf',f"ass='{ass}'",'-c:v','libx264','-threads','1','-c:a','copy',folder/'subtitled.mp4'])
  assert (folder/'subtitled.mp4').stat().st_size>1000
  print('PASS speech cuts + audio + Cyrillic subtitle burn-in; recognition requires model separately')
if __name__=='__main__': main()

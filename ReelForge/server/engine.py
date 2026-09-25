"""Small deterministic renderer. FFmpeg required; speech adds faster-whisper."""
import json, math, subprocess
from pathlib import Path
import numpy as np

TEMPLATES = {
    'clean': dict(name='Clean Cut', transition='fade', ramp=False, effect='null'),
    'velocity': dict(name='Velocity', transition='smoothleft', ramp=True, effect='eq=contrast=1.08:saturation=1.15'),
    'flash': dict(name='Flash Pop', transition='fadewhite', ramp=False, effect='eq=saturation=1.2'),
    'cinema': dict(name='Cinema', transition='fadeblack', ramp=False, effect='eq=contrast=1.1:saturation=0.8'),
    'zoom': dict(name='Zoom Flow', transition='zoomin', ramp=True, effect='null'),
}

def run(args):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800)
    if p.returncode:
        raise RuntimeError(p.stderr.decode(errors='replace')[-3000:])
    return p.stdout

def ff(args):
    return run(['ffmpeg','-hide_banner','-loglevel','error','-y','-filter_complex_threads','1',*map(str,args)])

def probe(path):
    return json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))

def duration(path):
    return float(probe(path)['format']['duration'])

def beat_cuts(music, total, bpm):
    """Energy-onset snapping around a tempo grid. Not semantic music analysis."""
    pcm=ff(['-i',music,'-t',total,'-vn','-ac','1','-ar','8000','-f','f32le','pipe:1'])
    audio=np.frombuffer(pcm,dtype='<f4')
    hop=160
    audio=audio[:len(audio)//hop*hop]
    if len(audio)<hop*3: return [0.,total]
    energy=np.sqrt(np.mean(audio.reshape(-1,hop)**2,axis=1))
    onset=np.maximum(np.diff(energy,prepend=0),0)
    step=4*60/bpm
    cuts=[0.]
    for center in np.arange(step,total-0.7,step):
        lo=max(0,int((center-.18)/.02)); hi=min(len(onset),int((center+.18)/.02)+1)
        t=(lo+int(np.argmax(onset[lo:hi])))*.02 if hi>lo else float(center)
        if t-cuts[-1]>.7 and total-t>.7: cuts.append(round(t,3))
    return cuts+[total]

def normalize(source,out,start,length,template,width,height,speech=False):
    d=duration(source)
    if d<.1: raise ValueError('Видео слишком короткое')
    base=f'scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,fps=30,settb=AVTB,setpts=PTS-STARTPTS'
    if template['ramp'] and not speech:
        # Monotonic time map: rate smoothly varies from 0.625x to 2.5x.
        base+=f",setpts='(T+0.6*{length}/(2*PI)*sin(2*PI*T/{length}))/TB',fps=30"
    base+=','+template['effect']+',format=yuv420p'
    args=['-stream_loop','-1','-ss',start,'-i',source]
    has_audio=any(s['codec_type']=='audio' for s in probe(source)['streams'])
    if speech and has_audio:
        args+=['-t',length,'-vf',base,'-af','aresample=48000,asetpts=PTS-STARTPTS','-ac','2','-c:a','aac']
    else: args+=['-t',length,'-vf',base,'-an']
    ff([*args,'-c:v','libx264','-preset','veryfast','-crf','21','-threads','2',out])

def join(parts,out,transition,width,height,speech=False):
    args=[]
    for p in parts: args+=['-i',p]
    if len(parts)==1:
        ff([*args,'-c','copy',out]); return
    if speech:
        inputs=''.join(f'[{i}:v][{i}:a]' for i in range(len(parts)))
        graph=f'{inputs}concat=n={len(parts)}:v=1:a=1[v][a]'
        maps=['-map','[v]','-map','[a]','-c:a','aac']
    else:
        graph=';'.join(f'[{i}:v]settb=AVTB,setpts=PTS-STARTPTS[v{i}]' for i in range(len(parts)))+';'
        elapsed=duration(parts[0]); previous='v0'; chains=[]
        for i in range(1,len(parts)):
            label=f'x{i}'
            chains.append(f'[{previous}][v{i}]xfade=transition={transition}:duration=0.2:offset={elapsed-.2:.6f}[{label}]')
            elapsed+=duration(parts[i])-.2; previous=label
        graph+=';'.join(chains); maps=['-map',f'[{previous}]','-an']
    ff([*args,'-filter_complex',graph,*maps,'-c:v','libx264','-pix_fmt','yuv420p','-preset','veryfast','-threads','2',out])

def speech_plan(source,limit,language):
    from faster_whisper import WhisperModel
    import os
    model=WhisperModel(os.environ.get('WHISPER_MODEL','small'),device='cpu',compute_type='int8')
    segments,_=model.transcribe(str(source),language=None if language=='auto' else language,word_timestamps=True,vad_filter=True)
    spans=[]; captions=[]; elapsed=0.; source_duration=duration(source)
    for seg in segments:
        if elapsed>=limit: break
        start=max(0.,seg.start-.08); end=min(source_duration,seg.end+.12,start+limit-elapsed)
        if end-start<.1: continue
        spans.append((start,end-start))
        words=list(seg.words or [])
        for i in range(0,len(words),4):
            group=words[i:i+4]
            a=elapsed+max(0,group[0].start-start); b=elapsed+min(end-start,group[-1].end-start)
            if b>a: captions.append((a,b,' '.join(w.word.strip() for w in group)))
        elapsed+=end-start
    if not spans: raise ValueError('Речь не найдена. Попробуйте другой клип или язык.')
    return spans,captions

def ass_time(t):
    cs=round(t*100); return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'

def write_ass(path,captions,w,h):
    size=round(w*.065)
    header=f'''[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{size},&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,35,35,{round(h*.2)},1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    for a,b,text in captions:
        text=text.replace('\\','').replace('{','').replace('}','').replace('\n',' ')
        header+=f'Dialogue: 0,{ass_time(a)},{ass_time(b)},Default,,0,0,0,,{{\\fad(70,70)}}{text}\n'
    path.write_text(header,encoding='utf-8')

def render(folder,clips,music,config,progress=lambda p,s:None):
    folder=Path(folder); template=TEMPLATES[config['template']]
    w,h=(1080,1920) if config.get('quality')=='1080' else (720,1280)
    total=float(config['duration']); parts=[]; captions=[]
    speech=config['mode']=='speech'
    progress(8,'Анализ речи' if speech else 'Анализ ритма')
    if speech:
        spans,captions=speech_plan(clips[0],total,config.get('language','auto'))
        plan=[(clips[0],start,length) for start,length in spans]
    else:
        if not music: raise ValueError('Выберите музыку')
        total=min(total,duration(music))
        if total<1: raise ValueError('Музыкальный файл слишком короткий')
        cuts=beat_cuts(music,total,config.get('bpm',120))
        plan=[(clips[i%len(clips)],0,b-a+(.2 if i<len(cuts)-2 else 0)) for i,(a,b) in enumerate(zip(cuts,cuts[1:]))]
    for i,(source,start,length) in enumerate(plan):
        progress(15+int(60*i/len(plan)),f'Монтаж {i+1}/{len(plan)}')
        p=folder/f'part-{i}.mp4'; normalize(source,p,start,length,template,w,h,speech); parts.append(p)
    progress(78,'Переходы')
    joined=folder/'joined.mp4'; join(parts,joined,template['transition'],w,h,speech)
    progress(90,'Экспорт')
    out=folder/'result.mp4'
    if speech:
        ass=folder/'captions.ass'; write_ass(ass,captions,w,h)
        # Controlled UUID directory; escape Windows drive separator for FFmpeg.
        safe=ass.resolve().as_posix().replace(':','\\:')
        ff(['-i',joined,'-vf',f"ass='{safe}'",'-c:v','libx264','-preset','veryfast','-threads','2','-c:a','copy','-movflags','+faststart',out])
    else:
        ff(['-i',joined,'-i',music,'-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','192k','-t',min(total,duration(joined)),'-movflags','+faststart',out])
    progress(100,'Готово')
    return out

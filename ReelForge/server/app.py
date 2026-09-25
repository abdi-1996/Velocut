import json, os, secrets, shutil, threading, time, uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ValidationError
from engine import render, probe, TEMPLATES

TOKEN=os.environ.get('REELFORGE_TOKEN','')
if len(TOKEN)<16: raise RuntimeError('Set REELFORGE_TOKEN to at least 16 characters')
ROOT=Path(os.environ.get('REELFORGE_DATA','data')).resolve(); ROOT.mkdir(parents=True,exist_ok=True)
app=FastAPI(title='ReelForge personal render server')
pool=ThreadPoolExecutor(max_workers=1); lock=threading.Lock(); jobs={}

class Config(BaseModel):
    mode: Literal['music','speech']='music'
    template: Literal['clean','velocity','flash','cinema','zoom']='clean'
    duration: int=Field(15,ge=5,le=60)
    bpm: int=Field(120,ge=60,le=200)
    quality: Literal['720','1080']='720'
    language: Literal['auto','ru','en','kk','uz','tr','fr']='auto'

def auth(authorization: str=Header(default='')):
    if not secrets.compare_digest(authorization,'Bearer '+TOKEN): raise HTTPException(401,'Неверный ключ сервера')

def get_job(job_id):
    with lock: item=jobs.get(job_id)
    if not item: raise HTTPException(404,'Задание не найдено; возможно, сервер перезапущен')
    return item

@app.get('/health',dependencies=[Depends(auth)])
def health(): return {'ok':True,'templates':TEMPLATES}

@app.post('/jobs',dependencies=[Depends(auth)])
async def create(config: str=Form(...), clips: list[UploadFile]=File(...), music: UploadFile|None=File(None)):
    try: cfg=Config.model_validate_json(config)
    except ValidationError as e: raise HTTPException(422,str(e))
    if not 1<=len(clips)<=12: raise HTTPException(400,'Выберите от 1 до 12 клипов')
    if cfg.mode=='speech' and len(clips)!=1: raise HTTPException(400,'Для речи выберите один клип')
    if cfg.mode=='music' and not music: raise HTTPException(400,'Добавьте музыку')
    with lock:
        if sum(j['status'] in ('uploading','queued','running') for j in jobs.values())>=3: raise HTTPException(429,'Очередь заполнена')
        ident=uuid.uuid4().hex
        jobs[ident]={'id':ident,'status':'uploading','progress':0,'message':'Загрузка','created':time.time()}
    folder=ROOT/ident; folder.mkdir(); total=0
    async def save(upload,name):
        nonlocal total
        p=folder/name
        with p.open('wb') as target:
            while chunk:=await upload.read(1024*1024):
                total+=len(chunk)
                if total>500*1024*1024: raise HTTPException(413,'Лимит задания — 500 МБ')
                target.write(chunk)
        await upload.close()
        try: info=probe(p)
        except Exception: raise HTTPException(400,'Не удалось прочитать медиафайл')
        kind='audio' if name=='music' else 'video'
        if not any(s['codec_type']==kind for s in info['streams']): raise HTTPException(400,f'Файл не содержит {kind}')
        if float(info['format'].get('duration',0))>600: raise HTTPException(400,'Клип должен быть короче 10 минут')
        return p
    try:
        sources=[await save(c,f'clip-{i}') for i,c in enumerate(clips)]
        audio=await save(music,'music') if music else None
    except Exception:
        shutil.rmtree(folder,ignore_errors=True)
        with lock: jobs.pop(ident,None)
        raise
    with lock: jobs[ident].update(status='queued',message='В очереди')
    def work():
        def update(value,message):
            with lock: jobs[ident].update(progress=value,message=message)
        try:
            with lock: jobs[ident]['status']='running'
            render(folder,sources,audio,cfg.model_dump(),update)
            with lock: jobs[ident]['status']='done'
        except Exception as e:
            with lock: jobs[ident].update(status='error',message=str(e)[-1800:])
        finally:
            for p in folder.iterdir():
                if p.name!='result.mp4': p.unlink(missing_ok=True)
    pool.submit(work)
    return {'id':ident}

@app.get('/jobs/{ident}',dependencies=[Depends(auth)])
def status(ident:str): return dict(get_job(ident))

@app.get('/jobs/{ident}/video',dependencies=[Depends(auth)])
def video(ident:str):
    if get_job(ident)['status']!='done': raise HTTPException(409,'Видео ещё не готово')
    return FileResponse(ROOT/ident/'result.mp4',media_type='video/mp4',filename='ReelForge.mp4')

@app.delete('/jobs/{ident}',dependencies=[Depends(auth)])
def delete(ident:str):
    if get_job(ident)['status'] in ('uploading','queued','running'): raise HTTPException(409,'Дождитесь завершения')
    shutil.rmtree(ROOT/ident,ignore_errors=True)
    with lock: jobs.pop(ident,None)
    return {'ok':True}

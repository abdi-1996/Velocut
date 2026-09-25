import React, {useEffect, useRef, useState} from 'react';
import {Alert, AppState, ActivityIndicator, Keyboard, KeyboardAvoidingView, Platform, Pressable, SafeAreaView, ScrollView, StyleSheet, Switch, Text, TextInput, View} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import * as SecureStore from 'expo-secure-store';
import {useVideoPlayer, VideoView} from 'expo-video';

type Asset={uri:string;name:string;mimeType:string};
type Job={id:string;status:string;progress:number;message:string};
const templates=[
 {id:'clean',name:'Clean Cut',hint:'Мягкие склейки · чистый цвет',icon:'◒',color:'#B7ED86'},
 {id:'velocity',name:'Velocity',hint:'Speed ramp · плавный сдвиг',icon:'↗',color:'#B5A1FF'},
 {id:'flash',name:'Flash Pop',hint:'Белая вспышка · яркий цвет',icon:'✦',color:'#F8C87C'},
 {id:'cinema',name:'Cinema',hint:'Затемнение · приглушённый цвет',icon:'◐',color:'#91CBE6'},
 {id:'zoom',name:'Zoom Flow',hint:'Приближение · speed ramp',icon:'◎',color:'#F6A7C8'},
];
function Preview({uri}:{uri:string}) {
 const player=useVideoPlayer(uri,p=>{p.loop=true;});
 return <VideoView player={player} style={{width:'100%',aspectRatio:9/16,maxHeight:480}} nativeControls contentFit="contain"/>;
}
export default function App(){
 const [server,setServer]=useState('');const [token,setToken]=useState('');
 const [mode,setMode]=useState<'music'|'speech'>('music');const [template,setTemplate]=useState('velocity');
 const [clips,setClips]=useState<Asset[]>([]);const [music,setMusic]=useState<Asset|null>(null);
 const [duration,setDuration]=useState(15);const [bpm,setBpm]=useState('120');const [hd,setHd]=useState(false);
 const [language,setLanguage]=useState('auto');const [busy,setBusy]=useState(false);
 const [job,setJob]=useState<Job|null>(null);const [result,setResult]=useState<string|null>(null);
 const [settings,setSettings]=useState(true);const [hint,setHint]=useState('');
 const polling=useRef(false);const jobConnection=useRef({url:'',key:''});
 useEffect(()=>{(async()=>{const saved=await SecureStore.getItemAsync('connection');if(saved){const c=JSON.parse(saved);setServer(c.url);setToken(c.key);setSettings(false);jobConnection.current=c;}const pending=await SecureStore.getItemAsync('pending');if(pending){const p=JSON.parse(pending);jobConnection.current=p.connection;setJob(p.job);setBusy(true);}})().catch(()=>setHint('Не удалось восстановить настройки'));},[]);
 const connection=()=>({url:server.trim().replace(/\/$/,''),key:token.trim()});
 async function request(path:string,options:RequestInit={},c=connection()){
   const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),30*60*1000);
   try{const r=await fetch(c.url+path,{...options,signal:controller.signal,headers:{Authorization:`Bearer ${c.key}`,...options.headers}});
   if(!r.ok){let message=`Ошибка ${r.status}`;try{const e=await r.json();message=typeof e.detail==='string'?e.detail:JSON.stringify(e.detail);}catch{}throw new Error(message);}return r;}finally{clearTimeout(timer);}
 }
 async function connect(){try{const c=connection();if(!/^https?:\/\//.test(c.url))throw new Error('Укажите полный адрес http:// или https://');await request('/health');await SecureStore.setItemAsync('connection',JSON.stringify(c));setHint('Сервер подключён');setSettings(false);}catch(e:any){Alert.alert('Подключение',e.message);}}
 async function selectClips(){try{const p=await ImagePicker.requestMediaLibraryPermissionsAsync();if(!p.granted)throw new Error('Разрешите доступ к видео в настройках телефона');const r=await ImagePicker.launchImageLibraryAsync({mediaTypes:['videos'],allowsMultipleSelection:mode==='music',selectionLimit:12,quality:1});if(!r.canceled){setClips(r.assets.map((a,i)=>({uri:a.uri,name:a.fileName||`clip-${i}.mp4`,mimeType:a.mimeType||'video/mp4'})));setResult(null);}}catch(e:any){Alert.alert('Импорт',e.message);}}
 async function selectMusic(){try{const r=await DocumentPicker.getDocumentAsync({type:'audio/*',copyToCacheDirectory:true});if(!r.canceled)setMusic({uri:r.assets[0].uri,name:r.assets[0].name,mimeType:r.assets[0].mimeType||'audio/mpeg'});}catch(e:any){Alert.alert('Музыка',e.message);}}
 async function start(){
  try{Keyboard.dismiss();if(!server||token.length<16)throw new Error('Сначала подключите сервер');if(!clips.length)throw new Error('Добавьте видео');if(mode==='music'&&!music)throw new Error('Добавьте музыку');if(mode==='music'&&(!/^\d+$/.test(bpm)||+bpm<60||+bpm>200))throw new Error('Темп должен быть от 60 до 200 BPM');
   setBusy(true);setResult(null);setJob(null);setHint('Загрузка файлов. Оставьте приложение открытым.');
   const data=new FormData();data.append('config',JSON.stringify({mode,template,duration,bpm:+bpm||120,quality:hd?'1080':'720',language}));
   (mode==='speech'?clips.slice(0,1):clips).forEach(a=>data.append('clips',{uri:a.uri,name:a.name,type:a.mimeType} as any));
   if(mode==='music'&&music)data.append('music',{uri:music.uri,name:music.name,type:music.mimeType} as any);
   const c=connection();const response=await request('/jobs',{method:'POST',body:data},c);const {id}=await response.json();
   const j={id,status:'queued',progress:0,message:'В очереди'};jobConnection.current=c;await SecureStore.setItemAsync('pending',JSON.stringify({job:j,connection:c}));setJob(j);setHint('');
  }catch(e:any){setBusy(false);setHint('');Alert.alert('Монтаж',e.message);}
 }
 useEffect(()=>{
  if(!job||['done','error'].includes(job.status))return;
  let stopped=false;
  async function poll(){if(polling.current)return;polling.current=true;
   try{const c=jobConnection.current;const r=await request(`/jobs/${job!.id}`,{},c);const next:Job=await r.json();if(stopped)return;
    if(next.status==='done'){
      setHint('Скачивание результата…');
      const file=FileSystem.documentDirectory+`reel-${next.id}.mp4`;
      const downloaded=await FileSystem.downloadAsync(c.url+`/jobs/${next.id}/video`,file,{headers:{Authorization:`Bearer ${c.key}`}});
      if(downloaded.status!==200)throw new Error('Не удалось скачать результат');
      if(stopped)return;setResult(downloaded.uri);setBusy(false);setHint('Видео сохранено в приложении');await SecureStore.deleteItemAsync('pending');
    }
    if(next.status==='error'){setBusy(false);await SecureStore.deleteItemAsync('pending');setHint(next.message);}
    setJob(next);
   }catch(e:any){if(!stopped)setHint('Связь с сервером: '+e.message+'. Повтор через 3 секунды.');}
   finally{polling.current=false;}
  }
  poll();const timer=setInterval(poll,3000);const sub=AppState.addEventListener('change',s=>{if(s==='active')poll();});
  return()=>{stopped=true;clearInterval(timer);sub.remove();};
 },[job?.id,job?.status]);
 async function clearResult(){try{await request(`/jobs/${job!.id}`,{method:'DELETE'},jobConnection.current);if(result)await FileSystem.deleteAsync(result,{idempotent:true});setResult(null);setJob(null);setHint('Результат удалён');}catch(e:any){Alert.alert('Удаление',e.message);}}
 const button=(text:string,onPress:()=>void,primary=false)=><Pressable disabled={busy} onPress={onPress} style={[s.button,primary&&s.primary,busy&&{opacity:.4}]}><Text style={[s.buttonText,primary&&{color:'#12170D'}]}>{text}</Text></Pressable>;
 return <SafeAreaView style={s.root}><KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==='ios'?'padding':undefined}><ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
  <View style={s.row}><View><Text style={s.eyebrow}>YOUR MOMENTS. IN MOTION.</Text><Text style={s.logo}>reelforge<Text style={{color:'#C3F578'}}> ✦</Text></Text></View><Pressable disabled={busy} onPress={()=>setSettings(!settings)}><Text style={s.settings}>⚙</Text></Pressable></View>
  <Text style={s.hero}>Твой следующий{`\n`}сильный рилс.</Text><Text style={s.muted}>Видео → шаблон → готовый монтаж</Text>
  {settings&&<View style={s.panel}><Text style={s.title}>Подключение сервера</Text><Text style={s.muted}>Адрес ПК или сервера обработки</Text><TextInput editable={!busy} value={server} onChangeText={setServer} placeholder="https://your-server.example" placeholderTextColor="#697080" autoCapitalize="none" keyboardType="url" style={s.input}/><TextInput editable={!busy} value={token} onChangeText={setToken} placeholder="Ключ сервера" placeholderTextColor="#697080" secureTextEntry autoCapitalize="none" style={s.input}/>{button('Проверить подключение',connect)}</View>}
  <View style={[s.row,{marginVertical:24}]}>{(['music','speech'] as const).map(m=><Pressable disabled={busy} key={m} onPress={()=>{setMode(m);if(m==='speech')setClips(c=>c.slice(0,1));}} style={[s.tab,mode===m&&s.active]}><Text style={[s.buttonText,mode===m&&{color:'#C3F578'}]}>{m==='music'?'♫ Под музыку':'◉ Разговорный'}</Text></Pressable>)}</View>
  <Text style={s.title}>01 / Исходники</Text>
  {button(clips.length?`Выбрано клипов: ${clips.length} · заменить`:'+ Добавить видео',selectClips)}
  {clips.map((c,i)=><View style={s.file} key={c.uri+i}><Text numberOfLines={1} style={[s.muted,{flex:1}]}>{i+1}. {c.name}</Text><Pressable disabled={busy} onPress={()=>setClips(clips.filter((_,j)=>j!==i))}><Text style={s.remove}>×</Text></Pressable></View>)}
  {mode==='music'?button(music?`♫ ${music.name}`:'+ Добавить музыку',selectMusic):<Text style={s.muted}>Один клип с речью. Паузы между фразами будут сокращены, субтитры появятся автоматически.</Text>}
  {mode==='music'&&<><Text style={[s.title,{marginTop:26}]}>02 / Выбери настроение</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{gap:12,paddingVertical:14}}>{templates.map(t=><Pressable key={t.id} disabled={busy} onPress={()=>setTemplate(t.id)} style={[s.card,{borderColor:template===t.id?t.color:'#292D39'}]}><View style={[s.art,{backgroundColor:t.color}]}><Text style={s.symbol}>{t.icon}</Text><Text style={s.tag}>{template===t.id?'ВЫБРАН':'ШАБЛОН'}</Text></View><Text style={s.cardTitle}>{t.name}</Text><Text style={s.small}>{t.hint}</Text></Pressable>)}</ScrollView><Text style={s.small}>Стартовые шаблоны. Каталог трендов пока не подключён.</Text></>}
  <Text style={[s.title,{marginTop:26}]}>{mode==='music'?'03':'02'} / Параметры</Text>
  <View style={[s.row,{marginVertical:12}]}>{[15,30,60].map(n=><Pressable disabled={busy} key={n} style={[s.chip,duration===n&&s.active]} onPress={()=>setDuration(n)}><Text style={s.buttonText}>{n} сек</Text></Pressable>)}</View>
  {mode==='music'?<View style={s.row}><Text style={[s.muted,{flex:1}]}>Темп музыки, BPM</Text><TextInput editable={!busy} value={bpm} onChangeText={setBpm} keyboardType="number-pad" maxLength={3} style={[s.input,{width:86,textAlign:'center'}]}/></View>:<><Text style={s.muted}>Язык речи</Text><ScrollView horizontal contentContainerStyle={{gap:8,marginVertical:12}}>{['auto','ru','en','kk','uz','tr','fr'].map(l=><Pressable disabled={busy} key={l} onPress={()=>setLanguage(l)} style={[s.chip,l===language&&s.active]}><Text style={s.buttonText}>{l==='auto'?'Авто':l.toUpperCase()}</Text></Pressable>)}</ScrollView></>}
  <View style={s.row}><View style={{flex:1}}><Text style={s.buttonText}>Экспорт Full HD</Text><Text style={s.small}>{hd?'1080 × 1920':'720 × 1280'} · 9:16 · MP4</Text></View><Switch disabled={busy} value={hd} onValueChange={setHd} trackColor={{true:'#698C3B'}} thumbColor={hd?'#C3F578':'#AAA'}/></View>
  <Text style={[s.small,{marginVertical:18}]}>Обработка на подключённом сервере. До 12 клипов и 500 МБ на монтаж. Звук исходников в музыкальном режиме заменяется выбранной музыкой.</Text>
  {button('✦  Создать рилс',start,true)}
  {busy&&<View style={s.panel}><ActivityIndicator color="#C3F578"/><Text style={s.title}>{job?.message||'Загрузка файлов'}</Text><View style={s.track}><View style={[s.fill,{width:`${job?.progress||0}%`}]}/></View><Text style={s.small}>После загрузки сервер продолжает монтаж при сворачивании приложения.</Text></View>}
  {!!hint&&<Text selectable style={[s.muted,{marginVertical:14}]}>{hint}</Text>}
  {result&&<View style={s.panel}><Text style={s.title}>Рилс готов</Text><Preview uri={result}/>{button('Сохранить / поделиться',()=>{Sharing.shareAsync(result,{mimeType:'video/mp4',UTI:'public.mpeg-4'}).catch(e=>Alert.alert('Экспорт',e.message));},true)}{button('Удалить результат с сервера',clearResult)}</View>}
  <Text style={s.footer}>REELFORGE · DEVELOPMENT MVP</Text>
 </ScrollView></KeyboardAvoidingView></SafeAreaView>;
}
const s=StyleSheet.create({root:{flex:1,backgroundColor:'#101219'},page:{padding:22,paddingBottom:44},row:{flexDirection:'row',alignItems:'center',gap:10},eyebrow:{fontSize:9,letterSpacing:2,color:'#89909E'},logo:{fontSize:29,fontWeight:'800',color:'#FFF'},settings:{fontSize:30,color:'#B3BAC7',padding:12},hero:{fontSize:35,fontWeight:'800',lineHeight:41,color:'#F5F6FA',marginTop:30,marginBottom:12},muted:{fontSize:14,color:'#A4AAB8',lineHeight:21},small:{fontSize:12,color:'#89909E',lineHeight:18},title:{color:'#E8EBF1',fontSize:16,fontWeight:'700',marginBottom:10},panel:{backgroundColor:'#191D28',padding:17,borderRadius:20,gap:12,marginTop:20},input:{borderWidth:1,borderColor:'#353B4A',borderRadius:12,padding:13,color:'#FFF',fontSize:15,marginVertical:5},button:{backgroundColor:'#242A38',padding:17,borderRadius:15,alignItems:'center',marginVertical:8},primary:{backgroundColor:'#C3F578'},buttonText:{color:'#E9ECF3',fontWeight:'600',fontSize:14},tab:{flex:1,backgroundColor:'#1A1E28',paddingVertical:14,borderRadius:12,alignItems:'center',borderWidth:1,borderColor:'#262C38'},active:{backgroundColor:'#2A3522',borderColor:'#97BB65'},card:{width:172,padding:10,borderWidth:2,borderRadius:19,backgroundColor:'#181C26'},art:{height:168,borderRadius:12,alignItems:'center',justifyContent:'center'},symbol:{fontSize:92,color:'#20251D'},tag:{fontSize:8,letterSpacing:2,color:'#20251D',marginTop:5},cardTitle:{fontSize:18,fontWeight:'700',color:'#F1F3F7',marginVertical:10},chip:{borderWidth:1,borderColor:'#303644',paddingHorizontal:18,paddingVertical:12,borderRadius:12},file:{flexDirection:'row',alignItems:'center',gap:10},remove:{color:'#EBA4AC',fontSize:26,padding:8},track:{height:6,borderRadius:3,backgroundColor:'#353C46',overflow:'hidden'},fill:{height:6,backgroundColor:'#C3F578'},footer:{color:'#555F70',fontSize:10,letterSpacing:2,textAlign:'center',marginTop:30}});

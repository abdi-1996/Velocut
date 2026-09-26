import React, {useEffect, useState} from 'react';
import {Alert, ActivityIndicator, Keyboard, KeyboardAvoidingView, Platform, Pressable, SafeAreaView, ScrollView, StyleSheet, Switch, Text, TextInput, View} from 'react-native';
import {NativeModule, requireNativeModule} from 'expo';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import {useVideoPlayer, VideoView} from 'expo-video';

type Asset={uri:string;name:string};
type Progress={value:number;message:string};
type Output={uri:string;duration:number;width:number;height:number};
declare class Renderer extends NativeModule<{progress:(e:Progress)=>void}> {
 capabilities(language:string):{local:boolean;speech:boolean};
 render(options:Record<string,unknown>):Promise<Output>;
 cancel():void;
}
const renderer=requireNativeModule<Renderer>('ReelRenderer');
const saved=FileSystem.documentDirectory+'reelforge-last.json';
const templates=[
 {id:'hero',name:'Hero Impact',hint:'Бит · рывок · shake',icon:'ϟ',color:'#ADBFFF'},
 {id:'redline',name:'Redline',hint:'Красный · slow · титры',icon:'R',color:'#FF7B83'},
 {id:'clean',name:'Clean Cut',hint:'Мягкие переходы',icon:'◒',color:'#B7ED86'},
 {id:'velocity',name:'Velocity',hint:'Speed ramp · сдвиг',icon:'↗',color:'#B5A1FF'},
 {id:'flash',name:'Flash Pop',hint:'Белые вспышки',icon:'✦',color:'#F8C87C'},
 {id:'cinema',name:'Cinema',hint:'Переход через чёрный',icon:'◐',color:'#91CBE6'},
 {id:'zoom',name:'Zoom Flow',hint:'Zoom · speed ramp',icon:'◎',color:'#F6A7C8'},
];
function Preview({uri,ratio}:{uri:string;ratio:number}){
 const player=useVideoPlayer(uri,p=>{p.loop=true;});
 return <VideoView player={player} style={{width:'100%',aspectRatio:ratio,maxHeight:460}} nativeControls contentFit="contain"/>;
}
function Button({title,onPress,disabled=false,primary=false}:{title:string;onPress:()=>void;disabled?:boolean;primary?:boolean}){
 return <Pressable disabled={disabled} onPress={onPress} style={[s.button,primary&&s.primary,disabled&&{opacity:.4}]}><Text style={[s.buttonText,primary&&{color:'#12170D'}]}>{title}</Text></Pressable>;
}
export default function App(){
 const [mode,setMode]=useState<'music'|'speech'>('music');const [template,setTemplate]=useState('hero');
 const [clips,setClips]=useState<Asset[]>([]);const [music,setMusic]=useState<Asset|null>(null);
 const [aspect,setAspect]=useState('16:9');const [autoBeat,setAutoBeat]=useState(true);const [selectMoments,setSelectMoments]=useState(true);const [depthText,setDepthText]=useState(false);const [intensity,setIntensity]=useState(0.65);
 const [duration,setDuration]=useState(15);const [bpm,setBpm]=useState('120');const [hd,setHd]=useState(false);
 const [language,setLanguage]=useState('ru-RU');const [captions,setCaptions]=useState<'none'|'auto'|'manual'>('none');const [text,setText]=useState('');
 const [busy,setBusy]=useState(false);const [progress,setProgress]=useState<Progress>({value:0,message:''});
 const [result,setResult]=useState<Output|null>(null);const [status,setStatus]=useState('');
 const canRecognize=renderer.capabilities(language).speech;
 useEffect(()=>{const sub=renderer.addListener('progress',setProgress);(async()=>{if((await FileSystem.getInfoAsync(saved)).exists){const last=JSON.parse(await FileSystem.readAsStringAsync(saved)) as Output;if((await FileSystem.getInfoAsync(last.uri)).exists)setResult(last);}})().catch(()=>{});return()=>sub.remove();},[]);
 async function selectClips(){try{const p=await ImagePicker.requestMediaLibraryPermissionsAsync();if(!p.granted)throw new Error('Разрешите доступ к галерее в настройках телефона');const r=await ImagePicker.launchImageLibraryAsync({mediaTypes:['videos'],allowsMultipleSelection:mode==='music',selectionLimit:12,quality:1});if(!r.canceled)setClips(r.assets.map((a,i)=>({uri:a.uri,name:a.fileName||`Клип ${i+1}`})));}catch(e){Alert.alert('Импорт',String(e));}}
 async function selectMusic(){try{const r=await DocumentPicker.getDocumentAsync({type:'audio/*',copyToCacheDirectory:true});if(!r.canceled)setMusic({uri:r.assets[0].uri,name:r.assets[0].name});}catch(e){Alert.alert('Музыка',String(e));}}
 async function start(){
  Keyboard.dismiss();
  if(!clips.length){Alert.alert('Добавьте видео');return;}
  if(mode==='music'&&!music){Alert.alert('Добавьте музыку');return;}
  if(mode==='music'&&!autoBeat&&(!/^\d+$/.test(bpm)||+bpm<60||+bpm>200)){Alert.alert('Темп должен быть от 60 до 200 BPM');return;}
  if(captions==='manual'&&!text.trim()){Alert.alert('Введите текст титров');return;}
  if(captions==='auto'&&!canRecognize){Alert.alert('Нет офлайн-модели','Выберите ручной текст или монтаж без субтитров.');return;}
  setBusy(true);setStatus('');setProgress({value:0,message:'Подготовка на телефоне'});
  try{
   const output=await renderer.render({clips:(mode==='speech'?clips.slice(0,1):clips).map(c=>c.uri),music:mode==='music'?music?.uri:null,mode,template,duration,bpm:+bpm||120,quality:hd?'1080':'720',language,captions,text,aspect,autoBeat,selectMoments,depthText,intensity});
   setResult(output);await FileSystem.writeAsStringAsync(saved,JSON.stringify(output));setStatus('Ролик готов. Он сохранён в приложении.');
  }catch(e){const message=e instanceof Error?e.message:String(e);setStatus(message);if(!/отмен|cancel/i.test(message))Alert.alert('Монтаж',message);}
  finally{setBusy(false);}
 }
 async function removeResult(){if(!result)return;try{await FileSystem.deleteAsync(result.uri,{idempotent:true});await FileSystem.deleteAsync(saved,{idempotent:true});setResult(null);setStatus('Ролик удалён из приложения');}catch(e){Alert.alert('Удаление',String(e));}}
 return <SafeAreaView style={s.root}><KeyboardAvoidingView style={{flex:1}} behavior={Platform.OS==='ios'?'padding':undefined}><ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
  <View style={s.row}><View style={{flex:1}}><Text style={s.eyebrow}>YOUR MOMENTS. IN MOTION.</Text><Text style={s.logo}>reelforge<Text style={{color:'#C3F578'}}> ✦</Text></Text></View><View style={s.badge}><Text style={{color:'#C3F578',fontSize:11}}>● НА ТЕЛЕФОНЕ</Text></View></View>
  <Text style={s.hero}>Твой следующий{`\n`}сильный рилс.</Text><Text style={s.muted}>Видео → шаблон → готовый монтаж</Text>
  <View style={[s.row,{marginVertical:24}]}>{(['music','speech'] as const).map(m=><Pressable disabled={busy} key={m} onPress={()=>{setMode(m);setCaptions('none');if(m==='speech')setClips(c=>c.slice(0,1));}} style={[s.tab,mode===m&&s.active]}><Text style={[s.buttonText,mode===m&&{color:'#C3F578'}]}>{m==='music'?'♫ Под музыку':'◉ Разговорный'}</Text></Pressable>)}</View>
  <Text style={s.title}>01 / Исходники</Text>
  <Button disabled={busy} title={clips.length?`Клипов: ${clips.length} · заменить`:'+ Добавить видео'} onPress={selectClips}/>
  {clips.map((c,i)=><View style={s.file} key={c.uri+i}><Text numberOfLines={1} style={[s.muted,{flex:1}]}>{i+1}. {c.name}</Text><Pressable disabled={busy} onPress={()=>setClips(clips.filter((_,j)=>j!==i))}><Text style={s.remove}>×</Text></Pressable></View>)}
  {mode==='music'?<Button disabled={busy} title={music?`♫ ${music.name}`:'+ Добавить музыку'} onPress={selectMusic}/>:<Text style={s.muted}>Один клип. Приложение сократит тихие паузы. Выберите автосубтитры ниже, если они нужны.</Text>}
  {mode==='music'&&<><Text style={[s.title,{marginTop:26}]}>02 / Выбери настроение</Text><ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{gap:12,paddingVertical:14}}>{templates.map(t=><Pressable key={t.id} disabled={busy} onPress={()=>setTemplate(t.id)} style={[s.card,{borderColor:template===t.id?t.color:'#292D39'}]}><View style={[s.art,{backgroundColor:t.color}]}><Text style={s.symbol}>{t.icon}</Text><Text style={s.tag}>{template===t.id?'ВЫБРАН':'ШАБЛОН'}</Text></View><Text style={s.cardTitle}>{t.name}</Text><Text style={s.small}>{t.hint}</Text></Pressable>)}</ScrollView><Text style={s.small}>7 шаблонов. Hero Impact — динамичные склейки и рывки скорости. Redline — красный акцент и плавный ритм.</Text></>}
  {mode==='music'&&['hero','redline'].includes(template)&&<View style={s.panel}>
   <Text style={s.title}>Характер эдита</Text>
   <View style={s.row}>{[[0.4,'Мягко'],[0.65,'Средне'],[1,'Сильно']].map(([value,label])=><Pressable disabled={busy} key={value} onPress={()=>setIntensity(+value)} style={[s.chip,intensity===value&&s.active]}><Text style={s.buttonText}>{label}</Text></Pressable>)}</View>
   <View style={s.row}><Text style={[s.muted,{flex:1}]}>Подбирать участки с движением</Text><Switch disabled={busy} value={selectMoments} onValueChange={setSelectMoments}/></View>
   <Text style={s.small}>Выбор по изменению изображения. Для точного сюжета заранее обрежьте исходники и расставьте их по порядку.</Text>
  </View>}
  <Text style={[s.title,{marginTop:26}]}>Текст и субтитры</Text>
  <View style={s.row}>{(['none',...(mode==='speech'?['auto']:[]),'manual'] as ('none'|'auto'|'manual')[]).map(c=><Pressable disabled={busy} key={c} onPress={()=>setCaptions(c)} style={[s.chip,c===captions&&s.active]}><Text style={s.buttonText}>{c==='none'?'Без текста':c==='auto'?'Авто':'Свой текст'}</Text></Pressable>)}</View>
  {captions==='manual'&&<><TextInput editable={!busy} value={text} onChangeText={setText} multiline maxLength={1200} style={[s.input,{minHeight:90}]} placeholder="Каждая строка — отдельный титр" placeholderTextColor="#697080"/><Text style={s.small}>Строки распределяются равномерно по ролику. Для Redline используйте короткие слова.</Text></>}
  {mode==='music'&&template==='redline'&&captions==='manual'&&<View style={s.panel}><View style={s.row}><Text style={[s.muted,{flex:1}]}>Текст за человеком · бета</Text><Switch disabled={busy} value={depthText} onValueChange={setDepthText}/></View><Text style={s.small}>Маска строится на iPhone. Экспорт дольше; волосы, быстрые движения и несколько людей могут давать неточные края.</Text></View>}
  {captions==='auto'&&<><ScrollView horizontal contentContainerStyle={{gap:8,marginVertical:12}}>{[['ru-RU','Русский'],['en-US','English'],['fr-FR','Français'],['tr-TR','Türkçe']].map(([l,label])=><Pressable disabled={busy} key={l} onPress={()=>setLanguage(l)} style={[s.chip,l===language&&s.active]}><Text style={s.buttonText}>{label}</Text></Pressable>)}</ScrollView><Text style={s.small}>{canRecognize?'Распознавание выполняется на телефоне.':'Офлайн-модель этого языка недоступна. Выберите ручной текст или другой язык.'}</Text></>}
  <Text style={[s.title,{marginTop:26}]}>Формат кадра</Text>
  <View style={[s.row,{marginVertical:12}]}>{['9:16','16:9','1:1'].map(a=><Pressable disabled={busy} key={a} style={[s.chip,aspect===a&&s.active]} onPress={()=>setAspect(a)}><Text style={s.buttonText}>{a}</Text></Pressable>)}</View>
  <Text style={[s.title,{marginTop:26}]}>Длительность и качество</Text>
  <View style={[s.row,{marginVertical:12}]}>{[15,30,60].map(n=><Pressable disabled={busy} key={n} style={[s.chip,duration===n&&s.active]} onPress={()=>setDuration(n)}><Text style={s.buttonText}>{n} сек</Text></Pressable>)}</View>
  {mode==='music'&&<View style={s.row}><Text style={[s.muted,{flex:1}]}>Автоматически определить темп</Text><Switch disabled={busy} value={autoBeat} onValueChange={setAutoBeat}/></View>}
  {mode==='music'&&!autoBeat&&<View style={s.row}><Text style={[s.muted,{flex:1}]}>Темп музыки, BPM</Text><TextInput editable={!busy} value={bpm} onChangeText={setBpm} keyboardType="number-pad" maxLength={3} style={[s.input,{width:86,textAlign:'center'}]}/></View>}
  <View style={s.row}><View style={{flex:1}}><Text style={s.buttonText}>Экспорт Full HD</Text><Text style={s.small}>{hd?'1080p':'720p'} · {aspect} · MP4</Text></View><Switch disabled={busy} value={hd} onValueChange={setHd} trackColor={{true:'#698C3B'}} thumbColor={hd?'#C3F578':'#AAA'}/></View>
  <Text style={[s.small,{marginVertical:18}]}>Монтаж работает без ПК. Во время экспорта оставьте приложение открытым. Видео обрезается по центру под выбранный формат.{mode==='music'?' Звук клипов заменяется музыкой; короткие клипы повторяются.':''}</Text>
  <Button disabled={busy} title="✦  Создать рилс" onPress={start} primary/>
  {busy&&<View style={s.panel}><ActivityIndicator color="#C3F578"/><Text style={s.title}>{progress.message}</Text><View style={s.track}><View style={[s.fill,{width:`${Math.min(100,Math.max(0,progress.value*100))}%`}]}/></View><Text style={s.small}>{Math.round(progress.value*100)}%</Text><Button title="Отменить монтаж" onPress={()=>renderer.cancel()}/></View>}
  {!!status&&<Text selectable style={[s.muted,{marginVertical:14}]}>{status}</Text>}
  {result&&!busy&&<View style={s.panel}><Text style={s.title}>Твой ролик · {result.duration.toFixed(1)} сек</Text><Preview uri={result.uri} ratio={result.width/result.height}/><Button title="Сохранить в галерею / поделиться" onPress={()=>Sharing.shareAsync(result.uri,{mimeType:'video/mp4',UTI:'public.mpeg-4'}).catch(e=>Alert.alert('Экспорт',String(e)))} primary/><Button title="Удалить из приложения" onPress={removeResult}/></View>}
  <Text style={s.footer}>REELFORGE 0.3 · ON DEVICE</Text>
 </ScrollView></KeyboardAvoidingView></SafeAreaView>;
}
const s=StyleSheet.create({root:{flex:1,backgroundColor:'#101219'},page:{padding:22,paddingBottom:44},row:{flexDirection:'row',alignItems:'center',gap:10},badge:{backgroundColor:'#27331F',padding:9,borderRadius:9},eyebrow:{fontSize:9,letterSpacing:2,color:'#89909E'},logo:{fontSize:29,fontWeight:'800',color:'#FFF'},hero:{fontSize:35,fontWeight:'800',lineHeight:41,color:'#F5F6FA',marginTop:30,marginBottom:12},muted:{fontSize:14,color:'#A4AAB8',lineHeight:21},small:{fontSize:12,color:'#89909E',lineHeight:18},title:{color:'#E8EBF1',fontSize:16,fontWeight:'700',marginBottom:10},panel:{backgroundColor:'#191D28',padding:17,borderRadius:20,gap:12,marginTop:20},input:{borderWidth:1,borderColor:'#353B4A',borderRadius:12,padding:13,color:'#FFF',fontSize:15,marginVertical:5},button:{backgroundColor:'#242A38',padding:17,borderRadius:15,alignItems:'center',marginVertical:8},primary:{backgroundColor:'#C3F578'},buttonText:{color:'#E9ECF3',fontWeight:'600',fontSize:14},tab:{flex:1,backgroundColor:'#1A1E28',paddingVertical:14,borderRadius:12,alignItems:'center',borderWidth:1,borderColor:'#262C38'},active:{backgroundColor:'#2A3522',borderColor:'#97BB65'},card:{width:172,padding:10,borderWidth:2,borderRadius:19,backgroundColor:'#181C26'},art:{height:168,borderRadius:12,alignItems:'center',justifyContent:'center'},symbol:{fontSize:92,color:'#20251D'},tag:{fontSize:8,letterSpacing:2,color:'#20251D',marginTop:5},cardTitle:{fontSize:18,fontWeight:'700',color:'#F1F3F7',marginVertical:10},chip:{borderWidth:1,borderColor:'#303644',paddingHorizontal:15,paddingVertical:12,borderRadius:12},file:{flexDirection:'row',alignItems:'center',gap:10},remove:{color:'#EBA4AC',fontSize:26,padding:8},track:{height:6,borderRadius:3,backgroundColor:'#353C46',overflow:'hidden'},fill:{height:6,backgroundColor:'#C3F578'},footer:{color:'#555F70',fontSize:10,letterSpacing:2,textAlign:'center',marginTop:30}});

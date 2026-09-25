// Run from this directory: node bootstrap.mjs
import {spawnSync} from 'node:child_process';
import {copyFileSync,existsSync,readFileSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=dirname(fileURLToPath(import.meta.url));
const target=resolve(root,'reelforge-app');
if(existsSync(target)){console.error('reelforge-app already exists. Keep your changes; choose another folder.');process.exit(1);}
function run(args,cwd){const r=spawnSync(process.platform==='win32'?'npx.cmd':'npx',args,{cwd,stdio:'inherit',shell:process.platform==='win32'});if(r.status!==0)process.exit(r.status||1);}
run(['--yes','create-expo-app@latest',target,'--template','blank-typescript'],root);
run(['expo','install','expo-video','expo-image-picker','expo-document-picker','expo-file-system','expo-sharing','expo-secure-store'],target);
await import('./configure.mjs');

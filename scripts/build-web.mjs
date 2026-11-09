import {build} from 'esbuild';
import {readFile, writeFile, copyFile, cp, rm} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
const root = process.cwd();
const source = path.join(root, '.build/generated-client');
await rm(source, {recursive:true,force:true});
await cp(path.join(root, '.build/pui-client'), source, {recursive:true});
const output = path.join(root, 'dist/pyodide');
function replaceOnce(source, before, after) {
  if (source.split(before).length !== 2) throw Error(`Upstream bootstrap changed: ${before}`);
  return source.replace(before, after);
}
let worker = await readFile(path.join(source, 'pyodide/worker.js'), 'utf8');
worker = replaceOnce(worker, "await python.loadPackage(['pygments', 'matplotlib']);", "await python.loadPackage(['pillow']);");
worker = replaceOnce(worker, "python.registerJsModule('_pui_bridge',{", `python.registerJsModule('_labelate_bridge', {
  modified:value=>postMessage({type:'labelate-dirty',epoch,value:Boolean(value)}),
});
python.registerJsModule('_pui_bridge',{`);
worker = replaceOnce(worker, 'from PUI.cookbook.app import Cookbook\n_pui_task = Cookbook().start()',
  'from labelate.app import Labelate\n_labelate_app = Labelate()\n_pui_task = _labelate_app.start()');
worker = worker.replaceAll('cookbook', 'Labelate').replaceAll('Cookbook', 'Labelate');
await writeFile(path.join(source, 'pyodide/worker.js'), worker);
let client = await readFile(path.join(source, 'pyodide/client.js'), 'utf8');
client = replaceOnce(client, "if(m.type==='downloads'){", `if(m.type==='labelate-dirty'){
  window.dispatchEvent(new CustomEvent('labelate-dirty',{detail:m.value}));return;
}
if(m.type==='downloads'){`);
client = client.replaceAll('cookbook', 'Labelate');
await writeFile(path.join(source, 'pyodide/client.js'), client);
const hash = createHash('sha256').update(await readFile(path.join(output, 'app.zip'))).digest('hex');
const options = {entryPoints:['client','worker'].map(n=>path.join(source,`pyodide/${n}.js`)),
  outdir:output,bundle:true,format:'esm',platform:'browser',target:['es2022']};
const probe = await build({...options,write:false});
const identity = createHash('sha256').update(hash);
for(const file of probe.outputFiles) identity.update(file.contents);
const version = identity.digest('hex');
await build({...options,minify:true,define:{__PUI_BUILD__:JSON.stringify(version),__PUI_ARCHIVE_HASH__:JSON.stringify(hash)},legalComments:'eof'});
await copyFile(path.join(source,'shared/client.css'),path.join(output,'client.css'));
console.log(`Built Labelate ${version.slice(0,12)}`);

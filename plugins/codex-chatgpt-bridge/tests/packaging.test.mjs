import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,copyFile,writeFile,readFile,realpath,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';

test('installer prepares the actual checkout path without calling Codex',{skip:process.platform!=='win32'},async t=>{
  const root=await mkdtemp(join(tmpdir(),'bridge public path '));
  t.after(()=>rm(root,{recursive:true,force:true}));
  await mkdir(join(root,'scripts'));await mkdir(join(root,'src'));
  await copyFile(fileURLToPath(new URL('../scripts/install.ps1',import.meta.url)),join(root,'scripts/install.ps1'));
  await writeFile(join(root,'src/server.mjs'),'// offline fixture');
  const result=spawnSync('pwsh',['-NoProfile','-File',join(root,'scripts/install.ps1'),'-PrepareOnly'],{encoding:'utf8',timeout:20000});
  assert.equal(result.status,0,result.stderr);
  const config=JSON.parse(await readFile(join(root,'.mcp.json'),'utf8'));
  // Windows runners may expose TEMP through an 8.3 alias; compare file targets.
  assert.equal(await realpath(config.mcpServers.chatgpt_bridge.args[0]),await realpath(join(root,'src/server.mjs')));
  assert.deepEqual(config.mcpServers.chatgpt_bridge.args.slice(1),['--stdio']);
  assert.match(result.stdout,/no Codex configuration or browser changed/);
});

test('public examples do not assert a previous user authorization',async()=>{
  for(const name of ['pro-review','work-check']){
    const example=JSON.parse(await readFile(new URL(`../examples/${name}.json`,import.meta.url),'utf8'));
    assert.equal(example.authorization,'');
    assert.deepEqual(example.source_refs,[]);
  }
});

#!/usr/bin/env node
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';
import { readFile } from 'node:fs/promises';
import { BridgeCore, routeTask } from './core.mjs';

const string={type:'string'};
const submitProperties={work_unit_id:string,goal:string,context:string,acceptance:string,mode:{enum:['chat','work']},model:{enum:['GPT-6 Pro','GPT-6.1 Sol']},authorization:string,source_refs:{type:'array',items:string}};
export const toolDefinitions=[
  {name:'bridge_route',description:'Deterministic routing suggestion; root performs semantic decomposition.',inputSchema:{type:'object',properties:submitProperties,additionalProperties:false}},
  {name:'bridge_submit',description:'Submit one authorized durable cloud task. Does not execute cloud output.',inputSchema:{type:'object',properties:submitProperties,required:['work_unit_id','goal','authorization'],additionalProperties:false}},
  {name:'bridge_poll',description:'Observe task state without resending.',inputSchema:{type:'object',properties:{work_unit_id:string},required:['work_unit_id'],additionalProperties:false}},
  {name:'bridge_result',description:'Read a bounded response slice for root review.',inputSchema:{type:'object',properties:{work_unit_id:string,offset:{type:'integer',minimum:0},limit:{type:'integer',minimum:1,maximum:8000}},required:['work_unit_id'],additionalProperties:false}},
  {name:'bridge_status',description:'Read browser adapter availability.',inputSchema:{type:'object',properties:{},additionalProperties:false}},
  {name:'bridge_close',description:'Root decision closes local pending work only; does not stop remote work or delete data.',inputSchema:{type:'object',properties:{work_unit_id:string,reason:string,disposition:{enum:['accepted','rejected','abandoned']}},required:['work_unit_id','reason','disposition'],additionalProperties:false}},
  {name:'bridge_reconcile',description:'Read-only recovery of unknown send via an exact existing conversation match; never resends.',inputSchema:{type:'object',properties:{work_unit_id:string},required:['work_unit_id'],additionalProperties:false}}
];
export async function dispatch(core, name, args={}) { if(name==='bridge_route')return routeTask(args);const method={bridge_submit:'submit',bridge_poll:'poll',bridge_result:'result',bridge_status:'status',bridge_close:'close',bridge_reconcile:'reconcile'}[name];if(!method)throw new Error(`Unknown tool: ${name}`);return core[method](args); }
export async function handleRpc(core,request) {
  if(!request||request.jsonrpc!=='2.0'||typeof request.method!=='string')return {jsonrpc:'2.0',id:request?.id??null,error:{code:-32600,message:'Invalid Request'}};
  if(!Object.hasOwn(request,'id'))return null;
  const reply=result=>({jsonrpc:'2.0',id:request.id,result});
  if(request.method==='initialize')return reply({protocolVersion:'2024-11-05',capabilities:{tools:{}},serverInfo:{name:'codex-chatgpt-bridge',version:'0.1.1'}});
  if(request.method==='ping')return reply({});
  if(request.method==='tools/list')return reply({tools:toolDefinitions});
  if(request.method==='tools/call') {try {const result=await dispatch(core,request.params?.name,request.params?.arguments??{});return reply({content:[{type:'text',text:JSON.stringify(result)}]});}catch(e){return reply({isError:true,content:[{type:'text',text:JSON.stringify({code:e.code??'TOOL_ERROR',message:String(e.message??e)})}]});}}
  return {jsonrpc:'2.0',id:request.id,error:{code:-32601,message:'Method not found'}};
}
async function main() {
  let adapter;try { const {BrowserAdapter}=await import('./browser.mjs');adapter=new BrowserAdapter(); }catch(e){adapter={submit:async()=>{throw e;},poll:async()=>{throw e;},status:async()=>({state:'unavailable',message:e.message})};}
  const core=new BridgeCore({adapter});const argv=process.argv.slice(2);
  if(argv.length&&argv[0]!=='--stdio') {try {const command=argv.shift();let args={};if(argv[0]==='--json'&&argv.length===2)args=JSON.parse(argv[1]);else if(argv[0]==='--input'&&argv.length===2)args=JSON.parse(await readFile(argv[1],'utf8'));else if(argv.length)throw new Error('Usage: route|submit|poll|result|status [--json JSON | --input file]');process.stdout.write(JSON.stringify(await dispatch(core,`bridge_${command}`,args))+'\n');}catch(e){process.stdout.write(JSON.stringify({isError:true,code:e.code??'CLI_ERROR',message:e.message})+'\n');process.exitCode=1;}return;}
  const lines=createInterface({input:process.stdin,crlfDelay:Infinity});for await(const line of lines) {if(!line.trim())continue;let reply;try{reply=await handleRpc(core,JSON.parse(line));}catch(e){reply={jsonrpc:'2.0',id:null,error:{code:-32700,message:'Parse error'}};}if(reply)process.stdout.write(JSON.stringify(reply)+'\n');}
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){await main();await new Promise(resolve=>process.stdout.write('',resolve));process.exit(process.exitCode||0);}

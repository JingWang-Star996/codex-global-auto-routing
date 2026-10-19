import { mkdir, readFile, writeFile, rename, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { homedir } from 'node:os';
import { createHash, randomUUID } from 'node:crypto';

const ID = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;
const ACTIVE = new Set(['created', 'dispatching', 'submitted', 'running', 'unknown_submission', 'needs_attention']);
const INPUT_KEYS = ['work_unit_id','goal','context','acceptance','mode','model','authorization','source_refs'];
const sha = value => createHash('sha256').update(value).digest('hex');
export class BridgeError extends Error { constructor(code, message) { super(message); this.code = code; } }
function fail(code, message) { throw new BridgeError(code, message); }
function idCheck(id) { if (typeof id !== 'string' || !ID.test(id)) fail('INVALID_ID', 'work_unit_id must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$'); }
function keys(input, allowed) { if (!input || typeof input !== 'object' || Array.isArray(input)) fail('INVALID_INPUT','Expected object'); for (const key of Object.keys(input)) if (!allowed.includes(key)) fail('INVALID_INPUT', `Unsupported field: ${key}`); }
function normalize(input) {
  keys(input, INPUT_KEYS); idCheck(input.work_unit_id);
  for (const field of ['goal','authorization']) if (typeof input[field] !== 'string' || !input[field].trim()) fail('INVALID_INPUT', `${field} requires nonempty human-provided text`);
  for (const field of ['context','acceptance']) if (input[field] !== undefined && typeof input[field] !== 'string') fail('INVALID_INPUT', `${field} must be text`);
  const mode = input.mode ?? 'chat'; if (!['chat','work'].includes(mode)) fail('INVALID_INPUT','mode must be chat or work');
  const model = mode === 'chat' ? 'GPT-6 Pro' : 'GPT-6.1 Sol';
  if (input.model !== undefined && input.model !== model) fail('INVALID_INPUT', `mode ${mode} requires ${model}`);
  const source_refs = input.source_refs ?? []; if (!Array.isArray(source_refs) || !source_refs.every(x => typeof x === 'string')) fail('INVALID_INPUT','source_refs must be string array');
  const payload = {work_unit_id:input.work_unit_id,goal:input.goal,context:input.context??'',acceptance:input.acceptance??'',mode,model,authorization:input.authorization,source_refs};
  if (JSON.stringify(payload).length > 24000) fail('INPUT_TOO_LARGE','Total input exceeds 24000 characters');
  return payload;
}
export function routeTask(input = {}) {
  keys(input, ['goal','context','acceptance','mode','model','authorization','source_refs','work_unit_id']);
  const text = [input.goal,input.context,input.acceptance].filter(x=>typeof x==='string').join('\n');
  if (text.length > 24000) fail('INPUT_TOO_LARGE','Total input exceeds 24000 characters');
  const local = /(?:shell|terminal|文件写入|修改代码|执行命令|密钥|password|secret|登录|验证码|发布|支付|权限|授权判断|删除|迁移)/i.test(text);
  const cloud = /(?:独立复核|开放探索|卡住|云端|ChatGPT|GPT-6 Pro)/i.test(text);
  const recommendation=local?'local':input.mode==='work'?'cloud_work_candidate':cloud?'cloud_candidate':'local';
  return {recommendation,reason:local?'规则匹配到本地执行或授权敏感动作，交主协调者判断。':recommendation==='local'?'默认由本地主协调者直接处理。':'明确请求云端 Work、独立复核、开放探索或受阻协助，交主协调者审阅后提交。',method:'deterministic_keyword_rules',semantic_decomposition:false,authorization_required:true,actual_model:'unknown',quota:'unknown'};
}
export class BridgeCore {
  constructor({stateDir = process.env.CHATGPT_BRIDGE_STATE || join(homedir(),'.codex','state','chatgpt-bridge'),adapter} = {}) { this.stateDir=stateDir; this.adapter=adapter; }
  async locked(fn) {
    await mkdir(this.stateDir,{recursive:true}); const lock = join(this.stateDir,'.lock');
    try { await mkdir(lock); } catch(e) { if(e.code==='EEXIST') fail('BRIDGE_LOCKED','Another process owns bridge lock; inspect stale lock after confirming its process has stopped.'); throw e; }
    try { await writeFile(join(lock,'owner.json'),JSON.stringify({pid:process.pid,at:new Date().toISOString()})); return await fn(); } finally { await rm(lock,{recursive:true,force:true}); }
  }
  dir(id) { idCheck(id); return join(this.stateDir,id); }
  async read(id) { try { return JSON.parse(await readFile(join(this.dir(id),'job.json'),'utf8')); } catch(e) { if(e.code==='ENOENT') fail('NOT_FOUND','Job not found'); throw e; } }
  async save(job) { job.updated_at=new Date().toISOString(); const dir=this.dir(job.work_unit_id); await mkdir(dir,{recursive:true}); const temp=join(dir,`job.${randomUUID()}.tmp`); await writeFile(temp,JSON.stringify(job,null,2),'utf8'); await rename(temp,join(dir,'job.json')); }
  async activeJob(except) {
    const {readdir}=await import('node:fs/promises');
    for(const name of await readdir(this.stateDir)) if(ID.test(name)&&name!==except) { try {const job=await this.read(name);if(!job.closed_at&&ACTIVE.has(job.state))return name;} catch(e){if(e.code!=='NOT_FOUND')throw e;} }
  }
  summary(job) { return {work_unit_id:job.work_unit_id,state:job.state,closed_at:job.closed_at??null,disposition:job.disposition??null,conversation_url:job.conversation_url??null,observed_model:job.observed_model??'unknown',observed_mode:job.observed_mode??'unknown',actual_model:'unknown',quota:'unknown',review_status:job.review_status??'not_ready',summary:(job.summary??'').slice(0,1500),summary_truncated:!!job.summary_truncated,job_path:join(this.dir(job.work_unit_id),'job.json'),response_path:job.response_path??null,response_sha256:job.response_sha256??null,limitations:['UI observation does not verify backend model or quota','Cloud response requires root review; no automatic execution'],error:job.error??null}; }
  async submit(input) {
    const payload=normalize(input), payload_hash=sha(JSON.stringify(payload));
    return this.locked(async()=>{
      let old;try{old=await this.read(payload.work_unit_id);}catch(e){if(e.code!=='NOT_FOUND')throw e;}
      if(old) {if(old.payload_hash!==payload_hash)fail('IDEMPOTENCY_CONFLICT','Same work_unit_id has different payload');if(old.state==='blocked')fail('BLOCKED','Previous attempt blocked; inspect job before creating a new work unit');return this.summary(old);}
      const active=await this.activeJob();if(active)fail('ACTIVE_JOB',`Active job already exists: ${active}`);
      const job={...payload,payload_hash,state:'created',send_attempted:false,created_at:new Date().toISOString(),actual_model:'unknown',quota:'unknown'};await this.save(job);
      const checkpoint=async patch=>{keys(patch,['state','page_url','send_attempted','dispatch_phase','conversation_url','observed_model','observed_mode','evidence']);if(patch.send_attempted===false&&job.send_attempted)fail('INVALID_CHECKPOINT','Cannot clear send_attempted');if(patch.state&&!['created','dispatching','blocked','needs_attention'].includes(patch.state))fail('INVALID_CHECKPOINT','Invalid checkpoint state');Object.assign(job,patch);if(job.send_attempted)job.state='dispatching';await this.save(job);};
      try { const result=await this.adapter.submit({...job},checkpoint);if(result?.state!=='submitted')fail('INVALID_ADAPTER_RESULT','submit must return submitted');for(const key of ['conversation_url','observed_model','observed_mode'])if(result[key]!==undefined)job[key]=result[key];job.state='submitted';job.send_attempted=true;await this.save(job); }
      catch(e) {job.state=job.send_attempted?'unknown_submission':'blocked';job.error={code:e.code??'SUBMIT_FAILED',message:String(e.message??e)};await this.save(job);fail(job.send_attempted?'UNKNOWN_SUBMISSION':'BLOCKED',`${job.state}: ${job.error.message}`);}
      return this.summary(job);
    });
  }
  async poll(input) {
    keys(input,['work_unit_id']);idCheck(input.work_unit_id);
    return this.locked(async()=>{ const job=await this.read(input.work_unit_id);if(job.closed_at)fail('JOB_CLOSED','Local job is closed; no further automatic polling');if(job.state==='completed')return this.summary(job);if(['blocked','created','dispatching','unknown_submission'].includes(job.state))fail('UNSAFE_STATE',`Cannot poll automatically from ${job.state}; human reconciliation required`);
      let result;try {result=await this.adapter.poll({...job});}catch(e){fail('POLL_FAILED',String(e.message??e));}
      if(!result||!['running','completed','needs_attention'].includes(result.state))fail('INVALID_ADAPTER_RESULT','Invalid poll state');
      if(result.state==='completed') {const evidence=result.evidence;if(typeof result.response_text!=='string'||!result.response_text.trim()||evidence?.done_marker!==true||evidence?.response_footer_visible!==true||evidence?.stop_visible!==false||evidence?.task_marker!==true)fail('COMPLETION_EVIDENCE_REQUIRED','Completion requires response text, matching task/done markers, visible response footer, and no stop control');const text=result.response_text;const target=join(this.dir(job.work_unit_id),'response.md');const temp=target+'.'+randomUUID()+'.tmp';await writeFile(temp,text,'utf8');await rename(temp,target);job.response_path=target;job.response_sha256=sha(text);job.summary=text.slice(0,1500);job.summary_truncated=text.length>1500;job.review_status='pending_root_review';job.evidence=evidence;}
      job.state=result.state;await this.save(job);return this.summary(job);
    });
  }
  async result(input) {
    keys(input,['work_unit_id','offset','limit']);idCheck(input.work_unit_id);const offset=input.offset??0,limit=input.limit??1500;if(!Number.isSafeInteger(offset)||offset<0||!Number.isSafeInteger(limit)||limit<1||limit>8000)fail('INVALID_INPUT','offset >= 0 and limit 1..8000 required');
    const job=await this.read(input.work_unit_id);if(job.state!=='completed')fail('RESULT_NOT_READY',`Job state is ${job.state}`);const body=await readFile(join(this.dir(job.work_unit_id),'response.md'),'utf8');if(sha(body)!==job.response_sha256)fail('RESULT_HASH_MISMATCH','Response hash mismatch');return {...this.summary(job),text:body.slice(offset,offset+limit),offset,limit,total_chars:body.length,truncated:offset+limit<body.length};
  }
  async status(input={}) { keys(input,[]);return {adapter:await this.adapter.status(),actual_model:'unknown',quota:'unknown',state_dir:this.stateDir}; }
  async reconcile(input) {
    keys(input,['work_unit_id']);idCheck(input.work_unit_id);
    return this.locked(async()=>{const job=await this.read(input.work_unit_id);
      if(job.closed_at)fail('JOB_CLOSED','Closed jobs cannot be reconciled');
      if(!['dispatching','unknown_submission'].includes(job.state))fail('UNSAFE_STATE','Reconcile requires dispatching or unknown_submission');
      let observed;try {observed=await this.adapter.reconcile({...job});}catch(e){job.state='unknown_submission';await this.save(job);fail('RECONCILE_FAILED',String(e.message??e));}
      let url;try{url=new URL(observed?.conversation_url);}catch{}
      if(observed?.state!=='submitted'||observed?.evidence?.task_identity_exact!==true||!url||url.origin!=='https://chatgpt.com'||!/^\/c\/[A-Za-z0-9_-]+\/?$/.test(url.pathname)||url.search||url.hash){job.state='unknown_submission';await this.save(job);fail('RECONCILE_UNVERIFIED','No unique existing conversation with exact task identity; no resend performed');}
      job.previous_error=job.error??null;delete job.error;job.conversation_url=observed.conversation_url;job.reconcile_evidence=observed.evidence;job.state='submitted';await this.save(job);return this.summary(job);
    });
  }
  async close(input) {
    keys(input,['work_unit_id','reason','disposition']);idCheck(input.work_unit_id);
    if(typeof input.reason!=='string'||!input.reason.trim()||input.reason.length>2000||!['accepted','rejected','abandoned'].includes(input.disposition))fail('INVALID_INPUT','reason (1..2000 chars) and disposition accepted/rejected/abandoned required');
    return this.locked(async()=>{const job=await this.read(input.work_unit_id);
      if(input.disposition==='accepted'&&job.state!=='completed')fail('NOT_COMPLETED','Only completed jobs can be accepted');
      if(['unknown_submission','dispatching'].includes(job.state)&&input.disposition!=='abandoned')fail('UNKNOWN_SUBMISSION','Unknown submission may only be abandoned; remote work may still be running');
      if(job.closed_at){if(job.disposition!==input.disposition||job.close_reason!==input.reason)fail('CLOSE_CONFLICT','Job already closed with a different decision');}
      else {job.closed_at=new Date().toISOString();job.disposition=input.disposition;job.close_reason=input.reason;job.review_status=input.disposition==='accepted'?'accepted_by_root':input.disposition;await this.save(job);}
      return {...this.summary(job),closed_at:job.closed_at,disposition:job.disposition,close_reason:job.close_reason,remote_stopped:false,notice:'Only local pending work is closed. Remote work may still be running; no remote stop or data deletion was performed.'};
    });
  }
}

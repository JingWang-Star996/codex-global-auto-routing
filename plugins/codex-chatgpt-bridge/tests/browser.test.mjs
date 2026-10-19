import test from 'node:test';
import assert from 'node:assert/strict';
import {safeConversationUrl,buildPrompt,BrowserAdapter,exactPromptMatch,completionDecision} from '../src/browser.mjs';
test('conversation identity accepts only exact ChatGPT conversations',()=>{
  assert.equal(safeConversationUrl('https://chatgpt.com/c/abc-123'),true);
  for(const u of ['https://chatgpt.com.evil.test/c/abc','https://evil.test/c/abc','http://chatgpt.com/c/abc','https://chatgpt.com/c/abc?redirect=x','https://chatgpt.com/','file:///c:/secret']) assert.equal(safeConversationUrl(u),false);
});
test('similar task ids and additional turns cannot match the frozen prompt',()=>{
  const expected=buildPrompt({work_unit_id:'unit',goal:'A',acceptance:'B'});
  assert.equal(exactPromptMatch(expected,expected),true);
  assert.equal(exactPromptMatch(expected.replace(/:unit/g,':unit2'),expected),false);
  assert.equal(exactPromptMatch(expected+'\nextra',expected),false);
});
test('completion fails closed for unknown, running, truncated and marker-in-prose',()=>{
  const base={response:'result\nCODEX_BRIDGE_DONE:unit',id:'unit',stopVisible:false,footerVisible:true,turnState:'complete'};
  assert.equal(completionDecision(base),true);
  assert.equal(completionDecision({...base,turnState:'in_progress'}),false);
  assert.equal(completionDecision({...base,stopVisible:true}),false);
  assert.equal(completionDecision({...base,response:'prose CODEX_BRIDGE_DONE:unit'}),false);
  assert.equal(completionDecision({...base,response:'result\nCODEX_BRIDGE_DONE:unit2'}),false);
  assert.throws(()=>completionDecision({...base,stopVisible:undefined}),/unknown/);
});
test('prompt contains bounded task identity and does not claim referenced files read',()=>{
  const s=buildPrompt({work_unit_id:'one',goal:'分析',context:'资料',acceptance:'给出处',source_refs:['local-source']});
  assert.match(s,/CODEX_BRIDGE_TASK:one/);assert.match(s,/CODEX_BRIDGE_DONE:one/);assert.match(s,/不代表你已经读取/);assert.match(s,/local-source/);
});
test('remote debugging cannot be redirected to a non-CHR endpoint',async()=>{
  const old=process.env.CHATGPT_BRIDGE_CDP;process.env.CHATGPT_BRIDGE_CDP='https://evil.test';
  try{await assert.rejects(new BrowserAdapter().connect(),/cdp_endpoint_denied/);}finally{if(old===undefined)delete process.env.CHATGPT_BRIDGE_CDP;else process.env.CHATGPT_BRIDGE_CDP=old;}
});

import {spawn} from 'node:child_process';import fs from 'node:fs/promises';import {chromium as pw} from 'playwright';import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../',import.meta.url)).replace(/\/$/,'');
const backend=spawn(process.env.PYTHON_EXECUTABLE||'python',[root+'/backend/tests/browser_server.py'],{cwd:root+'/backend',env:{...process.env,PYTHONPATH:root+'/backend'},stdio:'ignore'});
const frontend=spawn('npm',['start'],{cwd:root+'/frontend',env:{...process.env,PORT:'8124'},stdio:'ignore'});
let browser;
const checks=[];function assert(value,label){if(!value)throw Error(label);checks.push(label)}
try{
 for(let i=0;i<100;i++){try{const r=await fetch('http://127.0.0.1:8124');const b=await fetch('http://127.0.0.1:8123/health');if(r.ok&&b.ok)break}catch{}await new Promise(r=>setTimeout(r,200))}
 browser=await pw.launch({executablePath:process.env.PLAYWRIGHT_EXECUTABLE_PATH||undefined,headless:true,args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000}});const page=await context.newPage();
 await page.goto('http://127.0.0.1:8124');await page.getByRole('button',{name:'Owner access',exact:true}).click();await page.getByLabel('Workspace access token').fill('qa-owner-only-local-test-token-32chars');await page.getByRole('button',{name:'Connect',exact:true}).click();await page.getByRole('heading',{name:'Roast Studio',exact:true}).waitFor();
 assert(await page.locator('.desktopSidebar').isVisible(),'desktop navigation visible');
 await page.getByLabel('Incoming message').fill('You are late to the meeting again.');await page.getByRole('button',{name:'Generate roast',exact:true}).click();await page.locator('.reply').getByText('savage response for UI workflow testing.',{exact:true}).waitFor();
 assert((await page.locator('.reply').innerText()).includes('savage'),'successful UI workflow using labelled test provider');
 await page.getByRole('button',{name:'New roast',exact:false}).first().click();await page.getByLabel('Incoming message').fill('You are late to the meeting again.');await page.getByRole('button',{name:'Generate roast',exact:true}).click();await page.locator('.reply').getByText('savage response for UI workflow testing.',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Conversations',exact:true}).first().click();await page.locator('.conversation').first().waitFor();assert(await page.locator('.conversation').count()===2,'two separate conversations created');
 await page.locator('.conversation').first().click();assert((await page.locator('.thread').innerText()).includes('UI workflow testing'),'conversation reopened with messages');await page.reload();await page.getByRole('button',{name:'Sign out',exact:true}).first().waitFor();assert(await page.locator('.desktopSidebar').isVisible(),'session persists after refresh');
 await page.getByLabel('Incoming message').fill('__FAIL_QA__');await page.getByRole('button',{name:'Generate roast',exact:true}).click();await page.locator('.errorBanner').waitFor();await page.waitForTimeout(8000);assert(await page.locator('.errorBanner').isVisible(),'generation error remains visible after toast timeout');
 const out=root+'/docs/previews';await fs.mkdir(out,{recursive:true});await page.screenshot({path:out+'/qa-desktop.png',fullPage:true});
 for(const width of [320,390,720]){
  await page.setViewportSize({width,height:844});assert(await page.getByRole('button',{name:'Open navigation',exact:true}).isVisible(),'mobile menu '+width);assert(!(await page.locator('.desktopSidebar').isVisible()),'desktop sidebar hidden '+width);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal overflow '+width);
  await page.getByRole('button',{name:'Open navigation',exact:true}).click();await page.getByRole('dialog',{name:'Workspace',exact:true}).waitFor();await page.getByRole('button',{name:'Close navigation',exact:true}).press('Escape');assert(!(await page.getByRole('dialog',{name:'Workspace',exact:true}).isVisible()),'Escape closes menu '+width);
  await page.locator('.mobileControlsButton').click();const dialog=page.getByRole('dialog',{name:'Your controls',exact:true});await dialog.waitFor();await dialog.getByLabel('Reply language').selectOption('hindi');await dialog.getByLabel('Custom voice').fill('Dry librarian voice');await dialog.getByRole('button',{name:'Done',exact:true}).click();await page.locator('.mobileControlsButton').click();assert(await dialog.getByLabel('Reply language').inputValue()==='hindi','drawer preserves language '+width);assert(await dialog.getByLabel('Custom voice').inputValue()==='Dry librarian voice','drawer preserves voice '+width);
  await dialog.getByRole('button',{name:'Close controls',exact:true}).press('Tab');assert(await page.evaluate(()=>document.querySelector('#mobile-roast-controls').contains(document.activeElement)),'focus stays in controls '+width);
  if(width===390)await page.screenshot({path:out+'/qa-mobile-controls.png',fullPage:true});
  await dialog.getByRole('button',{name:'Done',exact:true}).click();
 }
 await page.setViewportSize({width:1440,height:1000});assert(await page.locator('.desktopSidebar').isVisible(),'desktop layout restored after resize');
 await fs.writeFile('/tmp/roastai-ui-results.json',JSON.stringify({checks,provider:'local labelled test double, not live Gemini'},null,2));console.log(JSON.stringify({passed:checks.length,checks},null,2));
}catch(e){console.error(e);process.exitCode=1}finally{await browser?.close();backend.kill();frontend.kill()}

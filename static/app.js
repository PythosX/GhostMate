let selectedId=null;
const $=id=>document.getElementById(id);
function esc(s){return String(s??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]))}
function example(t){$("dm").value=t;$("dm").focus()}
async function loadStats(){const r=await fetch("/api/stats");const d=await r.json();$("sMessages").textContent=d.messages;$("sReplies").textContent=d.replies;$("sEscalations").textContent=d.escalations}
async function loadConversations(){
 const r=await fetch("/api/conversations"); const data=await r.json(); const box=$("conversationList");
 box.innerHTML=data.length?data.map(c=>`<div class="conversation ${selectedId===c.id?"selected":""}" onclick="openConversation(${c.id})"><b>${esc(c.sender_name)}</b>${c.status!=="active"?'<span class="badge">ATTENTION</span>':''}<p>${esc(c.last_message||"No messages")}</p></div>`).join(""):`<div class="placeholder">No conversations yet.</div>`;
}
async function openConversation(id){
 selectedId=id; const r=await fetch(`/api/conversations/${id}`); const d=await r.json();
 $("chatName").textContent=d.conversation.sender_name;$("chatStatus").textContent=d.conversation.status.toUpperCase();renderMessages(d.messages);loadConversations();
}
function renderMessages(ms){
 $("messages").innerHTML=ms.length?ms.map(m=>`<div class="msg ${m.sender}">${esc(m.message)}<small>${m.sender==="ghostmate"?"GhostMate":"Sender"}</small></div>`).join(""):`<div class="placeholder">No messages.</div>`;
 $("messages").scrollTop=$("messages").scrollHeight;
}
async function sendDM(){
 const msg=$("dm").value.trim(); if(!msg)return;
 const sender=$("sender").value.trim()||"Demo User";
 const id=selectedId?String(selectedId):"demo-"+sender.toLowerCase().replace(/[^a-z0-9]+/g,"-");
 const r=await fetch("/api/incoming",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({sender_id:id,sender_name:sender,message:msg})});
 const d=await r.json(); if(!r.ok){alert(d.error);return}
 selectedId=d.conversation_id;$("dm").value="";renderMessages(d.history);showDecision(d.decision);await loadConversations();await loadStats();
}
function showDecision(d){
 $("decisionBadge").textContent=d.action==="escalate"?"ESCALATION":"AUTO REPLY";
 $("decisionBadge").style.color=d.action==="escalate"?"#ff7f94":"#6fe5ab";
 $("decision").innerHTML=`<div class="decision-card"><label>AI DECISION</label><div class="big ${d.action==="escalate"?"high":"low"}">${esc(d.intent)}</div>
 <div class="kv"><div><span>PRIORITY</span><b>${d.priority}/100</b></div><div><span>CONFIDENCE</span><b>${Math.round(d.confidence*100)}%</b></div><div><span>ACTION</span><b>${d.action}</b></div><div><span>HUMAN</span><b>${d.action==="escalate"?"REQUIRED":"NOT REQUIRED"}</b></div></div>
 <div class="reason"><b>Decision explanation</b><br>${esc(d.reason)}</div><div class="draft"><b>Response</b><br>${esc(d.reply)}</div>
 <div class="action ${d.action==="escalate"?"escalate":"auto"}">${d.action==="escalate"?"🚨 Creator attention required":"✓ GhostMate replied automatically"}</div>
 ${d.action==="escalate"?`<div class="buttons"><button class="approve" onclick="approve(${d.decision_id})">Approve Draft</button><button onclick="takeover(${d.decision_id})">Take Over</button></div>`:""}</div>`;
}
async function approve(id){await fetch(`/api/decision/${id}/approve`,{method:"POST"});if(selectedId)openConversation(selectedId);loadStats()}
async function takeover(id){await fetch(`/api/decision/${id}/takeover`,{method:"POST"});alert("Human takeover recorded for this demo.")}
loadConversations();loadStats();setInterval(()=>{loadConversations();loadStats()},5000);

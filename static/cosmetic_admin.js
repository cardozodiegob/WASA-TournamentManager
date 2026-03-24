/* ============================================================
   Cosmetic Admin — Shared JS for Create & Edit pages
   ============================================================ */

/* ---------- Canvas effect engine (mirrors profile.html) ---------- */
var CANVAS_EFFECTS={
sunburst_rays:function(cv){
  var ctx=cv.getContext('2d'),w=cv.width,h=cv.height,angle=0;
  (function draw(){ctx.clearRect(0,0,w,h);ctx.save();ctx.translate(w/2,h/2);ctx.globalAlpha=0.15;
  for(var i=0;i<12;i++){ctx.rotate(Math.PI/6);ctx.beginPath();ctx.moveTo(0,0);var l=Math.max(w,h);
  ctx.lineTo(l*Math.cos(angle+i*0.1),l*Math.sin(angle+i*0.1));ctx.lineTo(l*Math.cos(angle+i*0.1+0.15),l*Math.sin(angle+i*0.1+0.15));
  ctx.closePath();ctx.fillStyle='hsl('+(i*30+angle*50)%360+',80%,60%)';ctx.fill();}ctx.restore();angle+=0.005;requestAnimationFrame(draw);})();
},
electric_border:function(cv){
  var ctx=cv.getContext('2d'),w=cv.width,h=cv.height;
  function bolt(x1,y1,x2,y2,d){if(d<=0){ctx.lineTo(x2,y2);return;}var mx=(x1+x2)/2+(Math.random()-0.5)*d*15,my=(y1+y2)/2+(Math.random()-0.5)*d*15;bolt(x1,y1,mx,my,d-1);bolt(mx,my,x2,y2,d-1);}
  (function draw(){ctx.clearRect(0,0,w,h);ctx.strokeStyle='rgba(0,200,255,0.7)';ctx.lineWidth=1.5;ctx.shadowColor='#00c8ff';ctx.shadowBlur=8;
  for(var i=0;i<4;i++){var s=Math.floor(Math.random()*4),sx,sy,ex,ey;if(s===0){sx=Math.random()*w;sy=0;ex=Math.random()*w;ey=0;}else if(s===1){sx=w;sy=Math.random()*h;ex=w;ey=Math.random()*h;}else if(s===2){sx=Math.random()*w;sy=h;ex=Math.random()*w;ey=h;}else{sx=0;sy=Math.random()*h;ex=0;ey=Math.random()*h;}ctx.beginPath();ctx.moveTo(sx,sy);bolt(sx,sy,ex,ey,4);ctx.stroke();}ctx.shadowBlur=0;setTimeout(function(){requestAnimationFrame(draw);},80);})();
},
fire_aura:function(cv){
  var ctx=cv.getContext('2d'),w=cv.width,h=cv.height,ps=[];
  for(var i=0;i<60;i++)ps.push({x:Math.random()*w,y:h+Math.random()*20,vy:-(1+Math.random()*2),vx:(Math.random()-0.5)*0.5,life:Math.random(),r:2+Math.random()*3});
  (function draw(){ctx.clearRect(0,0,w,h);for(var i=0;i<ps.length;i++){var p=ps[i];p.x+=p.vx;p.y+=p.vy;p.life-=0.008;if(p.life<=0){p.x=Math.random()*w;p.y=h+5;p.vy=-(1+Math.random()*2);p.vx=(Math.random()-0.5)*0.5;p.life=1;}var a=p.life*0.6;var g=ctx.createRadialGradient(p.x,p.y,0,p.x,p.y,p.r*2);g.addColorStop(0,'rgba(255,200,50,'+a+')');g.addColorStop(0.5,'rgba(255,100,20,'+a*0.6+')');g.addColorStop(1,'rgba(255,30,0,0)');ctx.beginPath();ctx.arc(p.x,p.y,p.r*2,0,Math.PI*2);ctx.fillStyle=g;ctx.fill();}requestAnimationFrame(draw);})();
},
smoke_trail:function(cv){
  var ctx=cv.getContext('2d'),w=cv.width,h=cv.height,ps=[];
  for(var i=0;i<30;i++)ps.push({x:Math.random()*w,y:h+Math.random()*30,vy:-(0.3+Math.random()*0.7),vx:(Math.random()-0.5)*0.3,life:Math.random(),r:5+Math.random()*10});
  (function draw(){ctx.clearRect(0,0,w,h);for(var i=0;i<ps.length;i++){var p=ps[i];p.x+=p.vx;p.y+=p.vy;p.r+=0.05;p.life-=0.004;if(p.life<=0){p.x=Math.random()*w;p.y=h+10;p.vy=-(0.3+Math.random()*0.7);p.vx=(Math.random()-0.5)*0.3;p.life=1;p.r=5+Math.random()*10;}ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fillStyle='rgba(180,180,200,'+p.life*0.15+')';ctx.fill();}requestAnimationFrame(draw);})();
},
matrix_rain:function(cv){
  var ctx=cv.getContext('2d'),w=cv.width,h=cv.height,fs=12,cols=Math.floor(w/fs),drops=[];
  for(var i=0;i<cols;i++)drops[i]=Math.random()*-100;var chars='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%^&*';
  (function draw(){ctx.fillStyle='rgba(0,0,0,0.05)';ctx.fillRect(0,0,w,h);ctx.fillStyle='rgba(0,255,70,0.35)';ctx.font=fs+'px monospace';for(var i=0;i<drops.length;i++){ctx.fillText(chars[Math.floor(Math.random()*chars.length)],i*fs,drops[i]*fs);if(drops[i]*fs>h&&Math.random()>0.975)drops[i]=0;drops[i]+=0.5;}setTimeout(function(){requestAnimationFrame(draw);},50);})();
},
lightning:function(cv){
  var ctx=cv.getContext('2d'),w=cv.width,h=cv.height,timer=0;
  function branch(x,y,a,d,l){if(d<=0||l<2)return;var ex=x+Math.cos(a)*l,ey=y+Math.sin(a)*l;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(ex,ey);ctx.stroke();branch(ex,ey,a+(Math.random()-0.5)*1.2,d-1,l*0.7);if(Math.random()>0.5)branch(ex,ey,a+(Math.random()-0.5)*1.5,d-1,l*0.5);}
  (function draw(){ctx.clearRect(0,0,w,h);timer++;if(timer%15===0){ctx.strokeStyle='rgba(180,200,255,0.6)';ctx.lineWidth=1.5;ctx.shadowColor='#b4c8ff';ctx.shadowBlur=10;branch(Math.random()*w,0,Math.PI/2+(Math.random()-0.5)*0.5,6,30+Math.random()*20);ctx.shadowBlur=0;}requestAnimationFrame(draw);})();
},
plasma_field:function(cv){
  var ctx=cv.getContext('2d'),w=cv.width,h=cv.height,blobs=[];
  for(var i=0;i<5;i++)blobs.push({x:Math.random()*w,y:Math.random()*h,vx:(Math.random()-0.5)*0.8,vy:(Math.random()-0.5)*0.8,r:30+Math.random()*40,hue:Math.random()*360});
  (function draw(){ctx.clearRect(0,0,w,h);for(var i=0;i<blobs.length;i++){var b=blobs[i];b.x+=b.vx;b.y+=b.vy;b.hue=(b.hue+0.5)%360;if(b.x<0||b.x>w)b.vx*=-1;if(b.y<0||b.y>h)b.vy*=-1;var g=ctx.createRadialGradient(b.x,b.y,0,b.x,b.y,b.r);g.addColorStop(0,'hsla('+b.hue+',80%,60%,0.15)');g.addColorStop(1,'hsla('+b.hue+',80%,60%,0)');ctx.beginPath();ctx.arc(b.x,b.y,b.r,0,Math.PI*2);ctx.fillStyle=g;ctx.fill();}requestAnimationFrame(draw);})();
},
snowfall_sparkle:function(cv){
  var ctx=cv.getContext('2d'),w=cv.width,h=cv.height,ps=[];
  for(var i=0;i<50;i++)ps.push({x:Math.random()*w,y:Math.random()*h,vy:0.5+Math.random()*1,vx:(Math.random()-0.5)*0.3,r:1+Math.random()*3,o:0.3+Math.random()*0.5,tw:Math.random()*Math.PI*2});
  (function draw(){ctx.clearRect(0,0,w,h);for(var i=0;i<ps.length;i++){var p=ps[i];p.x+=p.vx+Math.sin(p.tw)*0.2;p.y+=p.vy;p.tw+=0.03;if(p.y>h){p.y=-5;p.x=Math.random()*w;}if(p.x<0)p.x=w;if(p.x>w)p.x=0;var a=p.o*(0.5+0.5*Math.sin(p.tw*3));ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);ctx.fillStyle='rgba(255,255,255,'+a+')';ctx.fill();if(p.r>2){ctx.beginPath();ctx.moveTo(p.x-p.r*1.5,p.y);ctx.lineTo(p.x+p.r*1.5,p.y);ctx.moveTo(p.x,p.y-p.r*1.5);ctx.lineTo(p.x,p.y+p.r*1.5);ctx.strokeStyle='rgba(255,255,255,'+a*0.5+')';ctx.lineWidth=0.5;ctx.stroke();}}requestAnimationFrame(draw);})();
}
};

var CANVAS_EFFECT_KEYS=Object.keys(CANVAS_EFFECTS);

/* ---------- SVG filter presets ---------- */
var SVG_PRESETS={
  turbulence:{label:'Turbulence',build:function(p){return '<feTurbulence type="turbulence" baseFrequency="'+(p.freq||0.05)+'" numOctaves="'+(p.oct||3)+'" result="t"/><feDisplacementMap in="SourceGraphic" in2="t" scale="'+(p.scale||15)+'" xChannelSelector="R" yChannelSelector="G"/>';}},
  fractal_noise:{label:'Fractal Noise',build:function(p){return '<feTurbulence type="fractalNoise" baseFrequency="'+(p.freq||0.03)+'" numOctaves="'+(p.oct||4)+'" result="n"/><feDisplacementMap in="SourceGraphic" in2="n" scale="'+(p.scale||10)+'" xChannelSelector="R" yChannelSelector="G"/>';}},
  blur:{label:'Gaussian Blur',build:function(p){return '<feGaussianBlur in="SourceGraphic" stdDeviation="'+(p.radius||2)+'"/>';}},
  color_shift:{label:'Color Matrix',build:function(p){var h=(p.hue||0)*Math.PI/180,c=Math.cos(h).toFixed(3),s=Math.sin(h).toFixed(3);return '<feColorMatrix type="hueRotate" values="'+(p.hue||0)+'"/>';}},
  glow_filter:{label:'Glow',build:function(p){return '<feGaussianBlur in="SourceGraphic" stdDeviation="'+(p.radius||3)+'" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>';}},
  emboss:{label:'Emboss',build:function(p){var s=p.strength||1;return '<feConvolveMatrix order="3" kernelMatrix="-'+s+' -'+s+' 0 -'+s+' '+s+' '+s+' 0 '+s+' '+s+'"/>';}}
};

/* ---------- Effect-type CSS generators ---------- */
/* Each returns {css, keyframes} strings from friendly params */
var EFFECT_GENERATORS={
  glow:function(p){
    var c=p.color||'#ffd700',i=p.intensity||10,s=p.speed||2;
    var kf='@keyframes cGlow{0%,100%{filter:drop-shadow(0 0 '+i+'px '+c+')}50%{filter:drop-shadow(0 0 '+(i*2)+'px '+c+')}}';
    return {css:'animation:cGlow '+s+'s ease-in-out infinite;',kf:kf};
  },
  pulse:function(p){
    var c=p.color||'#6c5ce7',s=p.speed||1.5,mn=p.min_scale||0.97,mx=p.max_scale||1.03;
    var kf='@keyframes cPulse{0%,100%{transform:scale('+mn+');box-shadow:0 0 8px '+c+'44}50%{transform:scale('+mx+');box-shadow:0 0 20px '+c+'88}}';
    return {css:'animation:cPulse '+s+'s ease-in-out infinite;',kf:kf};
  },
  sparkle:function(p){
    var c=p.color||'#ffffff',s=p.speed||3;
    var kf='@keyframes cSparkle{0%,100%{text-shadow:0 0 4px '+c+',2px -2px 6px '+c+'44}25%{text-shadow:-2px 1px 6px '+c+',3px 2px 8px '+c+'66}50%{text-shadow:1px -1px 8px '+c+',−1px 3px 10px '+c+'88}75%{text-shadow:2px 2px 6px '+c+',-2px -1px 8px '+c+'44}}';
    return {css:'animation:cSparkle '+s+'s ease-in-out infinite;',kf:kf};
  },
  rainbow:function(p){
    var s=p.speed||4,dir=p.direction||'right';
    var kf='@keyframes cRainbow{0%{filter:hue-rotate(0deg)}100%{filter:hue-rotate(360deg)}}';
    return {css:'background:linear-gradient(to '+dir+',#ff0000,#ff7700,#ffff00,#00ff00,#0077ff,#8800ff,#ff0000);background-size:200% 200%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:cRainbow '+s+'s linear infinite;',kf:kf};
  },
  shadow:function(p){
    var c=p.color||'#000000',x=p.offset_x||3,y=p.offset_y||3,b=p.blur||6,s=p.speed||0;
    if(s>0){
      var kf='@keyframes cShadow{0%,100%{box-shadow:'+x+'px '+y+'px '+b+'px '+c+'}50%{box-shadow:'+(x*-1)+'px '+(y*-1)+'px '+(b*1.5)+'px '+c+'}}';
      return {css:'animation:cShadow '+s+'s ease-in-out infinite;',kf:kf};
    }
    return {css:'box-shadow:'+x+'px '+y+'px '+b+'px '+c+';',kf:''};
  },
  particle:function(p){
    var c=p.color||'#ffd700',s=p.speed||3;
    var kf='@keyframes cParticle{0%{box-shadow:inset 0 0 10px '+c+'44,0 0 10px '+c+'22}33%{box-shadow:inset 0 0 20px '+c+'66,5px -5px 15px '+c+'33}66%{box-shadow:inset 0 0 10px '+c+'44,-5px 5px 15px '+c+'33}100%{box-shadow:inset 0 0 10px '+c+'44,0 0 10px '+c+'22}}';
    return {css:'animation:cParticle '+s+'s ease-in-out infinite;',kf:kf};
  },
  holographic:function(p){
    var s=p.speed||5,i=p.intensity||60;
    var kf='@keyframes cHolo{0%{background-position:0% 50%;filter:brightness(1) contrast(1.1)}50%{background-position:100% 50%;filter:brightness(1.2) contrast(1.2)}100%{background-position:0% 50%;filter:brightness(1) contrast(1.1)}}';
    return {css:'background:linear-gradient(135deg,#ff00cc33,#3333ff33,#00ffcc33,#ffff0033,#ff00cc33);background-size:'+i*4+'% '+i*4+'%;animation:cHolo '+s+'s ease infinite;',kf:kf};
  },
  glitch:function(p){
    var c1=p.color||'#ff0000',c2=p.color2||'#00ffff',s=p.speed||0.5;
    var kf='@keyframes cGlitch{0%,100%{text-shadow:2px 0 '+c1+',-2px 0 '+c2+';transform:translate(0)}20%{text-shadow:-2px 0 '+c1+',2px 0 '+c2+';transform:translate(-2px,1px)}40%{text-shadow:2px 0 '+c1+',-2px 0 '+c2+';transform:translate(2px,-1px)}60%{text-shadow:-1px 0 '+c1+',1px 0 '+c2+';transform:translate(1px,2px)}80%{text-shadow:1px 0 '+c1+',-1px 0 '+c2+';transform:translate(-1px,-2px)}}';
    return {css:'animation:cGlitch '+s+'s steps(1) infinite;',kf:kf};
  },
  animated_gradient:function(p){
    var c1=p.color||'#667eea',c2=p.color2||'#764ba2',a=p.angle||135,s=p.speed||4;
    var kf='@keyframes cGrad{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}';
    return {css:'background:linear-gradient('+a+'deg,'+c1+','+c2+','+c1+');background-size:200% 200%;animation:cGrad '+s+'s ease infinite;',kf:kf};
  }
};

/* ---------- Effect-type friendly control definitions ---------- */
/* Each key maps to an array of {id,label,type,default,...} */
var EFFECT_CONTROLS={
  glow:[
    {id:'color',label:'Glow Color',type:'color',def:'#ffd700'},
    {id:'intensity',label:'Intensity (px)',type:'number',def:10,min:2,max:50},
    {id:'speed',label:'Speed (s)',type:'number',def:2,min:0.3,max:10,step:0.1}
  ],
  pulse:[
    {id:'color',label:'Pulse Color',type:'color',def:'#6c5ce7'},
    {id:'speed',label:'Speed (s)',type:'number',def:1.5,min:0.3,max:10,step:0.1},
    {id:'min_scale',label:'Min Scale',type:'number',def:0.97,min:0.8,max:1,step:0.01},
    {id:'max_scale',label:'Max Scale',type:'number',def:1.03,min:1,max:1.3,step:0.01}
  ],
  sparkle:[
    {id:'color',label:'Sparkle Color',type:'color',def:'#ffffff'},
    {id:'speed',label:'Speed (s)',type:'number',def:3,min:0.5,max:10,step:0.1}
  ],
  rainbow:[
    {id:'speed',label:'Speed (s)',type:'number',def:4,min:0.5,max:15,step:0.1},
    {id:'direction',label:'Direction',type:'select',def:'right',opts:['right','left','top','bottom']}
  ],
  shadow:[
    {id:'color',label:'Shadow Color',type:'color',def:'#000000'},
    {id:'offset_x',label:'Offset X (px)',type:'number',def:3,min:-20,max:20},
    {id:'offset_y',label:'Offset Y (px)',type:'number',def:3,min:-20,max:20},
    {id:'blur',label:'Blur (px)',type:'number',def:6,min:0,max:40},
    {id:'speed',label:'Animate (s, 0=static)',type:'number',def:0,min:0,max:10,step:0.1}
  ],
  particle:[
    {id:'color',label:'Particle Color',type:'color',def:'#ffd700'},
    {id:'speed',label:'Speed (s)',type:'number',def:3,min:0.5,max:10,step:0.1}
  ],
  holographic:[
    {id:'speed',label:'Speed (s)',type:'number',def:5,min:1,max:15,step:0.1},
    {id:'intensity',label:'Intensity',type:'number',def:60,min:20,max:100}
  ],
  glitch:[
    {id:'color',label:'Color 1',type:'color',def:'#ff0000'},
    {id:'color2',label:'Color 2',type:'color',def:'#00ffff'},
    {id:'speed',label:'Speed (s)',type:'number',def:0.5,min:0.1,max:3,step:0.1}
  ],
  animated_gradient:[
    {id:'color',label:'Color 1',type:'color',def:'#667eea'},
    {id:'color2',label:'Color 2',type:'color',def:'#764ba2'},
    {id:'angle',label:'Angle (°)',type:'number',def:135,min:0,max:359},
    {id:'speed',label:'Speed (s)',type:'number',def:4,min:0.5,max:15,step:0.1}
  ]
};

/* ---------- SVG preset control definitions ---------- */
var SVG_CONTROLS={
  turbulence:[
    {id:'freq',label:'Frequency',type:'number',def:0.05,min:0.001,max:0.5,step:0.005},
    {id:'oct',label:'Octaves',type:'number',def:3,min:1,max:8},
    {id:'scale',label:'Displacement',type:'number',def:15,min:1,max:60}
  ],
  fractal_noise:[
    {id:'freq',label:'Frequency',type:'number',def:0.03,min:0.001,max:0.5,step:0.005},
    {id:'oct',label:'Octaves',type:'number',def:4,min:1,max:8},
    {id:'scale',label:'Displacement',type:'number',def:10,min:1,max:60}
  ],
  blur:[{id:'radius',label:'Radius (px)',type:'number',def:2,min:0.5,max:20,step:0.5}],
  color_shift:[{id:'hue',label:'Hue Rotate (°)',type:'number',def:90,min:0,max:360}],
  glow_filter:[{id:'radius',label:'Glow Radius',type:'number',def:3,min:1,max:15,step:0.5}],
  emboss:[{id:'strength',label:'Strength',type:'number',def:1,min:0.5,max:5,step:0.5}]
};

/* ---------- Helper: build a row of controls from a definition array ---------- */
function _buildControlRow(controls, prefix, onchange){
  var h='<div style="display:flex;gap:.75rem;flex-wrap:wrap;align-items:end">';
  for(var i=0;i<controls.length;i++){
    var c=controls[i], iid=prefix+'-ef-'+c.id;
    h+='<div class="fg" style="margin:0;min-width:100px"><label class="fl">'+c.label+'</label>';
    if(c.type==='color'){
      h+='<input type="color" id="'+iid+'" value="'+c.def+'" oninput="'+onchange+'">';
    }else if(c.type==='select'){
      h+='<select id="'+iid+'" class="fs" onchange="'+onchange+'">';
      for(var j=0;j<c.opts.length;j++) h+='<option value="'+c.opts[j]+'"'+(c.opts[j]===c.def?' selected':'')+'>'+c.opts[j]+'</option>';
      h+='</select>';
    }else{
      h+='<input type="number" id="'+iid+'" class="fi" value="'+c.def+'"'+(c.min!=null?' min="'+c.min+'"':'')+(c.max!=null?' max="'+c.max+'"':'')+(c.step?' step="'+c.step+'"':'')+' style="width:90px" oninput="'+onchange+'">';
    }
    h+='</div>';
  }
  return h+'</div>';
}

/* ---------- Read control values from DOM ---------- */
function _readControls(controls, prefix){
  var p={};
  for(var i=0;i<controls.length;i++){
    var c=controls[i], el=document.getElementById(prefix+'-ef-'+c.id);
    if(!el)continue;
    p[c.id]=(c.type==='number')?parseFloat(el.value):el.value;
  }
  return p;
}

/* ---------- CSS labels per mode ---------- */
var cssLabels={'css':'CSS Data','svg_filter':'SVG Filter XML','canvas':'Effect Key'};

/* ---------- Image help text per category ---------- */
var imageHelp={
  'badge':'Upload a small icon (recommended 32×32px). If provided, replaces the emoji badge on profiles.',
  'avatar_frame':'Upload a frame overlay image (recommended 130×130px with transparency). Applied around the user avatar.',
  'name_color':'Optional. If uploaded, shown as a thumbnail in the shop and admin list.',
  'name_effect':'Optional. If uploaded, shown as a thumbnail in the shop and admin list.',
  'profile_border':'Optional. If uploaded, shown as a thumbnail in the shop and admin list.',
  'profile_banner':'Optional. If uploaded, shown as a thumbnail in the shop and admin list.',
  'profile_background':'Optional. If uploaded, shown as a thumbnail in the shop and admin list.',
  'profile_effect':'Optional. If uploaded, shown as a thumbnail in the shop and admin list.',
  'chat_flair':'Upload a small icon (recommended 24×24px). If provided, replaces the emoji flair in chat.',
  'title':'Optional. If uploaded, shown as a thumbnail in the shop and admin list.'
};

/* ==========================================================
   buildFriendly(cat, mode, effectType, prefix)
   Renders friendly controls into #<prefix>-friendly
   ========================================================== */
function buildFriendly(cat, mode, effectType, prefix){
  var wrap=document.getElementById(prefix+'-friendly');
  if(!wrap)return;
  wrap.innerHTML='';
  var oc="syncCssFromFriendly('"+prefix+"')";
  var html='';

  /* --- CANVAS mode: show effect key picker --- */
  if(mode==='canvas'){
    html+='<div class="fg" style="margin:0"><label class="fl">Canvas Effect</label><select id="'+prefix+'-canvas-key" class="fs" onchange="'+oc+'">';
    for(var i=0;i<CANVAS_EFFECT_KEYS.length;i++){
      html+='<option value="'+CANVAS_EFFECT_KEYS[i]+'">'+CANVAS_EFFECT_KEYS[i].replace(/_/g,' ')+'</option>';
    }
    html+='</select></div>';
    wrap.innerHTML=html;
    return;
  }

  /* --- SVG mode: show preset picker + params --- */
  if(mode==='svg_filter'){
    html+='<div class="fg" style="margin:0;margin-bottom:.75rem"><label class="fl">SVG Preset</label><select id="'+prefix+'-svg-preset" class="fs" onchange="onSvgPresetChange(\''+prefix+'\')">';
    var keys=Object.keys(SVG_PRESETS);
    for(var i=0;i<keys.length;i++) html+='<option value="'+keys[i]+'">'+SVG_PRESETS[keys[i]].label+'</option>';
    html+='</select></div><div id="'+prefix+'-svg-params"></div>';
    wrap.innerHTML=html;
    onSvgPresetChange(prefix);
    return;
  }

  /* --- CSS mode: category controls + effect type controls --- */
  /* Category-specific basic controls */
  if(cat==='name_color'){
    html+='<div style="display:flex;gap:.75rem;align-items:end;margin-bottom:.75rem"><div class="fg" style="margin:0"><label class="fl">Text Color</label><input type="color" id="'+prefix+'-fc1" value="#ffd700" oninput="'+oc+'"></div></div>';
  }else if(cat==='profile_border'){
    html+='<div style="display:flex;gap:.75rem;align-items:end;margin-bottom:.75rem"><div class="fg" style="margin:0"><label class="fl">Border Color</label><input type="color" id="'+prefix+'-fc1" value="#6c5ce7" oninput="'+oc+'"></div><div class="fg" style="margin:0"><label class="fl">Width (px)</label><input type="number" id="'+prefix+'-fw" class="fi" value="3" min="1" max="20" style="width:80px" oninput="'+oc+'"></div></div>';
  }else if(cat==='profile_banner'||cat==='profile_background'){
    html+='<div style="display:flex;gap:.75rem;align-items:end;margin-bottom:.75rem"><div class="fg" style="margin:0"><label class="fl">Color 1</label><input type="color" id="'+prefix+'-fc1" value="#667eea" oninput="'+oc+'"></div><div class="fg" style="margin:0"><label class="fl">Color 2</label><input type="color" id="'+prefix+'-fc2" value="#764ba2" oninput="'+oc+'"></div><div class="fg" style="margin:0"><label class="fl">Angle (°)</label><input type="number" id="'+prefix+'-fa" class="fi" value="135" min="0" max="359" style="width:80px" oninput="'+oc+'"></div></div>';
  }else if(cat==='badge'||cat==='chat_flair'){
    html+='<div class="fg" style="margin:0;margin-bottom:.75rem"><label class="fl">Emoji or Symbol</label><input type="text" id="'+prefix+'-ft" class="fi" placeholder="e.g. 🏆 ⭐ 🔥" style="max-width:200px" oninput="'+oc+'"></div>';
  }else if(cat==='title'){
    html+='<div class="fg" style="margin:0;margin-bottom:.75rem"><label class="fl">Title Text</label><input type="text" id="'+prefix+'-ft" class="fi" placeholder="e.g. Legend" style="max-width:200px" oninput="'+oc+'"></div>';
  }

  /* Effect-type controls (only if not 'none') */
  if(effectType && effectType!=='none' && EFFECT_CONTROLS[effectType]){
    html+='<div style="margin-top:.5rem;padding:.75rem;border:1px solid var(--brd);border-radius:8px;background:var(--bg2)">';
    html+='<div style="font-size:.8rem;font-weight:600;color:var(--acc);margin-bottom:.5rem"><i class="fas fa-wand-magic-sparkles"></i> '+effectType.replace(/_/g,' ')+' effect</div>';
    html+=_buildControlRow(EFFECT_CONTROLS[effectType], prefix, oc);
    html+='</div>';
  }

  wrap.innerHTML=html;
}

/* ---------- SVG preset change handler ---------- */
function onSvgPresetChange(prefix){
  var sel=document.getElementById(prefix+'-svg-preset');
  if(!sel)return;
  var key=sel.value, wrap=document.getElementById(prefix+'-svg-params');
  if(!wrap)return;
  var controls=SVG_CONTROLS[key]||[];
  var oc="syncCssFromFriendly('"+prefix+"')";
  wrap.innerHTML=_buildControlRow(controls, prefix, oc);
  syncCssFromFriendly(prefix);
}

/* ==========================================================
   syncCssFromFriendly(prefix)
   Reads friendly controls and writes combined CSS to the input
   ========================================================== */
function syncCssFromFriendly(prefix){
  var catEl=document.getElementById(prefix+'-category');
  var modeEl=document.getElementById(prefix+'-effect-mode');
  var etEl=document.getElementById(prefix+'-effect-type');
  var inp=document.getElementById(prefix+'-css-input');
  if(!inp)return;
  var cat=catEl?catEl.value:'';
  var mode=modeEl?modeEl.value:'css';
  var et=etEl?etEl.value:'none';

  /* Canvas mode */
  if(mode==='canvas'){
    var ck=document.getElementById(prefix+'-canvas-key');
    inp.value=ck?ck.value:'';
    _updatePreview(prefix);
    return;
  }

  /* SVG mode */
  if(mode==='svg_filter'){
    var ps=document.getElementById(prefix+'-svg-preset');
    if(!ps){_updatePreview(prefix);return;}
    var key=ps.value, controls=SVG_CONTROLS[key]||[];
    var params=_readControls(controls, prefix);
    var preset=SVG_PRESETS[key];
    inp.value=preset?preset.build(params):'';
    _updatePreview(prefix);
    return;
  }

  /* CSS mode: category base + effect type */
  var baseCss='';
  if(cat==='name_color'){
    var c=document.getElementById(prefix+'-fc1');
    if(c) baseCss='color:'+c.value+';';
  }else if(cat==='profile_border'){
    var c=document.getElementById(prefix+'-fc1'),w=document.getElementById(prefix+'-fw');
    if(c&&w) baseCss='border:'+(w.value||3)+'px solid '+c.value+';';
  }else if(cat==='profile_banner'||cat==='profile_background'){
    var c1=document.getElementById(prefix+'-fc1'),c2=document.getElementById(prefix+'-fc2'),a=document.getElementById(prefix+'-fa');
    if(c1&&c2&&a) baseCss='background:linear-gradient('+(a.value||135)+'deg,'+c1.value+','+c2.value+');';
  }else if(cat==='badge'||cat==='chat_flair'||cat==='title'){
    var t=document.getElementById(prefix+'-ft');
    if(t){inp.value=t.value;_updatePreview(prefix);return;}
  }

  /* Add effect type CSS + keyframes */
  var effectCss='', effectKf='';
  if(et && et!=='none' && EFFECT_GENERATORS[et] && EFFECT_CONTROLS[et]){
    var params=_readControls(EFFECT_CONTROLS[et], prefix);
    var gen=EFFECT_GENERATORS[et](params);
    effectCss=gen.css||'';
    effectKf=gen.kf||'';
  }

  inp.value=baseCss+effectCss+(effectKf?' '+effectKf:'');
  _updatePreview(prefix);
}

/* ==========================================================
   renderPreview(el, cat, cssData, mode)
   Renders a live preview into the given element
   ========================================================== */
function renderPreview(el, cat, cssData, mode){
  if(!el)return;
  /* Stop any running canvas animation */
  if(el._animFrame){cancelAnimationFrame(el._animFrame);el._animFrame=null;}
  el.innerHTML='';el.removeAttribute('style');el.style.transition='all .1s';
  if(!cssData){el.innerHTML='<span style="color:var(--tm);font-size:.82rem">No data</span>';return;}

  /* SVG filter */
  if(mode==='svg_filter'){
    var fid='pf-'+Math.random().toString(36).substr(2,6);
    el.innerHTML='<svg style="position:absolute;width:0;height:0"><defs><filter id="'+fid+'">'+cssData+'</filter></defs></svg><div style="width:60px;height:60px;border-radius:8px;background:var(--bg3);filter:url(#'+fid+')"></div>';
    return;
  }

  /* Canvas */
  if(mode==='canvas'){
    var key=cssData.trim();
    if(CANVAS_EFFECTS[key]){
      var cvWrap=document.createElement('div');
      cvWrap.style.cssText='width:200px;height:80px;border-radius:8px;background:#1a1a2e;position:relative;overflow:hidden';
      var cv=document.createElement('canvas');cv.width=200;cv.height=80;
      cv.style.cssText='position:absolute;top:0;left:0;width:100%;height:100%';
      cvWrap.appendChild(cv);el.appendChild(cvWrap);
      CANVAS_EFFECTS[key](cv);
    }else{
      el.innerHTML='<div style="font-size:.82rem;color:var(--tm)">Canvas: <code>'+cssData+'</code></div>';
    }
    return;
  }

  /* Content categories */
  if(cat==='badge'||cat==='chat_flair'){
    el.innerHTML='<span style="font-size:1.5rem">'+cssData+'</span> <span style="font-weight:600;color:var(--t1)">SampleUser</span>';
    return;
  }
  if(cat==='title'){
    el.innerHTML='<span style="font-weight:600;color:var(--t1)">SampleUser</span><br><span style="display:inline-block;padding:.15rem .6rem;border-radius:6px;font-size:.75rem;font-weight:700;background:var(--acc2,#6c5ce722);color:var(--acc)">'+cssData+'</span>';
    return;
  }

  /* CSS mode: extract keyframes */
  var inline=cssData, kf='';
  var ki=cssData.indexOf('@keyframes');
  if(ki>-1){inline=cssData.substring(0,ki).trim().replace(/;$/,'');kf=cssData.substring(ki);}
  var st=kf?'<style>'+kf+'</style>':'';

  if(cat==='name_color'||cat==='name_effect'){
    el.innerHTML=st+'<span style="font-size:1.3rem;font-weight:700;'+inline+'">SampleUser</span>';
  }else if(cat==='profile_border'||cat==='avatar_frame'){
    el.innerHTML=st+'<div style="width:60px;height:60px;border-radius:50%;background:var(--bg3);'+inline+'"></div>';
  }else if(cat==='profile_banner'||cat==='profile_background'){
    el.innerHTML=st+'<div style="width:200px;height:80px;border-radius:8px;'+inline+'"></div>';
  }else if(cat==='profile_effect'){
    el.innerHTML=st+'<div style="width:120px;height:80px;border-radius:8px;background:var(--bg3);position:relative;overflow:hidden;'+inline+'"></div>';
  }else{
    el.innerHTML=st+'<div style="width:60px;height:60px;border-radius:8px;background:var(--bg3);'+inline+'"></div>';
  }
}

/* ---------- Convenience: update preview for a prefix ---------- */
function _updatePreview(prefix){
  var cat=document.getElementById(prefix+'-category');
  var mode=document.getElementById(prefix+'-effect-mode');
  var css=document.getElementById(prefix+'-css-input');
  var prev=document.getElementById(prefix+'-preview');
  if(cat&&mode&&css&&prev) renderPreview(prev, cat.value, css.value, mode.value);
}

/* ---------- Toggle collapsible sections ---------- */
function toggleSection(id){
  var el=document.getElementById(id);
  var icon=document.getElementById(id+'-icon');
  var isOpen=el.classList.toggle('open');
  if(icon){
    if(isOpen){icon.classList.remove('fa-plus');icon.classList.add('fa-minus');}
    else{icon.classList.remove('fa-minus');icon.classList.add('fa-plus');}
  }
}

/* ==========================================================
   Page-level init helpers — called from each template
   ========================================================== */
function initCosmeticPage(prefix, rarityPriceRanges){
  /* Wire up category change */
  var catEl=document.getElementById(prefix+'-category');
  var modeEl=document.getElementById(prefix+'-effect-mode');
  var etEl=document.getElementById(prefix+'-effect-type');
  var rarEl=document.getElementById(prefix+'-rarity');

  function rebuild(){
    var cat=catEl?catEl.value:'';
    var mode=modeEl?modeEl.value:'css';
    var et=etEl?etEl.value:'none';
    buildFriendly(cat, mode, et, prefix);
    /* Update CSS label */
    var lbl=document.getElementById(prefix+'-css-label');
    if(lbl) lbl.textContent=cssLabels[mode]||'CSS Data';
    /* Update image help */
    var ih=document.getElementById(prefix+'-image-help');
    if(ih) ih.textContent=imageHelp[cat]||'';
    _updatePreview(prefix);
  }

  if(catEl) catEl.addEventListener('change', rebuild);
  if(modeEl) modeEl.addEventListener('change', rebuild);
  if(etEl) etEl.addEventListener('change', rebuild);

  /* Price hint */
  function updatePriceHint(){
    var r=rarEl?rarEl.value:'';
    var el=document.getElementById(prefix+'-price-hint');
    if(el&&rarityPriceRanges&&rarityPriceRanges[r])
      el.textContent='Recommended: '+rarityPriceRanges[r][0]+'–'+rarityPriceRanges[r][1]+' 🪙';
  }
  if(rarEl) rarEl.addEventListener('change', updatePriceHint);

  /* CSS input manual typing */
  var cssInp=document.getElementById(prefix+'-css-input');
  if(cssInp) cssInp.addEventListener('input', function(){_updatePreview(prefix);});

  /* Initial render */
  rebuild();
  updatePriceHint();
}

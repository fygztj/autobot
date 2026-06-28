//
//  AutomationScripts.swift
//  自动化引擎 v2 - 坐标级点击 + Agent 自主循环
//
// 核心设计：
// 1. 点击使用精确坐标 MouseEvent（绕过 React 合成事件系统）
// 2. 所有操作前先 scrollIntoView 确保可见性
// 3. 提供页面观察接口，供 Agent 决策
//

import Foundation

enum AutomationScripts {

    // ============================================================
    // MARK: - 平台 URL
    // ============================================================

    static func url(for platform: String) -> String {
        switch platform {
        case "douyin": return "https://www.douyin.com"
        default: return "https://www.xiaohongshu.com/explore"
        }
    }

    // ============================================================
    // MARK: - 页面观察（Agent 的"眼睛"）
    // ============================================================

    /// 全面观察当前页面状态，返回结构化信息供 Agent 决策
    static func observeScript() -> String {
        return """
        (function(){try{
            var url = location.href;
            var title = document.title || '';
            var scrollY = window.pageYOffset || 0;
            var viewH = window.innerHeight;
            var docH = document.documentElement.scrollHeight;

            // 判断页面类型
            var pageType = 'unknown';
            if (url.indexOf('/explore') >= 0 || url.indexOf('/discover') >= 0 || url.indexOf('/feed') >= 0) pageType = 'list';
            else if (url.indexOf('/note/') >= 0 || url.indexOf('/discovery/') >= 0) pageType = 'detail';
            else if (url.indexOf('login') >= 0 || url.indexOf('signin') >= 0) pageType = 'login';
            else if (url.indexOf('user_profile') >= 0 || url.indexOf('/user/') >= 0) pageType = 'profile';

            // 收集可见的笔记卡片信息
            var notes = [];
            try {
                // 小红书桌面版笔记选择器
                var cards = document.querySelectorAll('section.note-item, section[class*="note"], a[href*="/note/"], div[class*="feeds-item"], div[class*="note-card"], article');
                for (var i = 0; i < cards.length; i++) {
                    var el = cards[i];
                    var r = el.getBoundingClientRect();
                    if (r.width < 50 || r.height < 50) continue;
                    if (r.top > viewH || r.bottom < 0) continue; // 不在可视区

                    var noteInfo = {
                        index: i,
                        top: Math.round(r.top),
                        left: Math.round(r.left),
                        width: Math.round(r.width),
                        height: Math.round(r.height),
                        centerX: Math.round(r.left + r.width / 2),
                        centerY: Math.round(r.top + r.height / 2),
                        tag: el.tagName,
                        className: (el.className || '').toString().substring(0, 80),
                        href: ''
                    };

                    // 提取链接
                    var linkEl = el.tagName === 'A' ? el : el.querySelector('a[href*="/note/"], a[href*="/explore/"]');
                    if (linkEl) noteInfo.href = (linkEl.getAttribute('href') || '').substring(0, 120);

                    // 尝试提取标题文本
                    var titleEl = el.querySelector('[class*="title"], h1, h2, h3, [class*="content"] span');
                    if (titleEl) noteInfo.titleText = (titleEl.innerText || titleEl.textContent || '').trim().substring(0, 100);

                    // 尝试提取作者
                    var authorEl = el.querySelector('[class*="author"], [class*="user"], [class*="name"]');
                    if (authorEl) noteInfo.author = (authorEl.innerText || authorEl.textContent || '').trim().substring(0, 50);

                    notes.push(noteInfo);
                }
            } catch(e) {}

            // 检测详情页的操作按钮位置
            var detailButtons = [];
            try {
                if (pageType === 'detail') {
                    var btns = document.querySelectorAll('button, [role="button"], [class*="btn"], a[class*="action"], div[tabindex]');
                    for (var j = 0; j < btns.length && j < 30; j++) {
                        var br = btns[j].getBoundingClientRect();
                        if (br.width <= 0 || br.height <= 0) continue;
                        if (br.top > viewH || br.bottom < 0) continue;

                        var text = (btns[j].innerText || btns[j].textContent || btns[j].getAttribute('aria-label') || '').trim().substring(0, 20);
                        var cls = (btns[j].className || '').toString().substring(0, 60);

                        detailButtons.push({
                            text: text,
                            classHint: cls,
                            x: Math.round(br.left + br.width / 2),
                            y: Math.round(br.top + br.height / 2),
                            w: Math.round(br.width),
                            h: Math.round(br.height)
                        });
                    }
                }
            } catch(e) {}

            return JSON.stringify({
                success: true,
                pageType: pageType,
                url: url.substring(0, 150),
                title: title,
                scrollY: scrollY,
                viewHeight: viewH,
                docHeight: docH,
                canScrollDown: (scrollY + viewH < docH - 100),
                canScrollUp: (scrollY > 100),
                visibleNotes: notes,
                detailButtons: detailButtons,
                totalElements: document.querySelectorAll('*').length
            });
        } catch(e) { return JSON.stringify({success:false, message:'观察异常:'+e.message}); }})();
        """
    }

    /// 轻量级快速观察（仅返回基本信息）
    static func quickObserveScript() -> String {
        return """
        (function(){try{
            var url=location.href;var sy=window.pageYOffset||0;
            var pt='unknown';
            if(url.indexOf('/explore')>=0||url.indexOf('/discover')>=0)pt='list';
            else if(url.indexOf('/note/')>=0)pt='detail';
            else if(url.indexOf('login')>=0)pt='login';

            var nc=0;
            try{nc=document.querySelectorAll('section,a[href*="/note/"],article,[class*="feeds"]').length;}catch(e){}

            return JSON.stringify({success:true,pageType:pt,url:url.substring(0,120),scrollY:sy,noteCount:nc,docHeight:document.documentElement.scrollHeight});
        }catch(e){return JSON.stringify({success:false,message:e.message});}})();
        """
    }

    // ============================================================
    // MARK: - 核心点击引擎（坐标级精确点击）
    // ============================================================

    /// 通用坐标点击 - 最可靠的点击方式，绕过 React 事件系统
    /// 先 scrollIntoView 确保可见 → 计算中心坐标 → 在该坐标派发完整的鼠标事件序列
    private static func coordinateClickJS(selector: String, index: Int = 0) -> String {
        return """
        (function(){try{
            var els = document.querySelectorAll('\(selector)');
            if (!els || els.length === 0 || !els[\(index)]) return JSON.stringify({success:false, message:'未找到元素: \(selector)[\(index)]'});
            var el = els[\(index)];

            // Step 1: 滚动到可见区域
            el.scrollIntoView({behavior:'instant',block:'center',inline:'center'});
            // 强制重排确保坐标准确
            void el.offsetHeight;

            // Step 2: 获取精确坐标
            var rect = el.getBoundingClientRect();
            var cx = Math.round(rect.left + rect.width / 2);
            var cy = Math.round(rect.top + rect.height / 2);

            // Step 3: 完整的鼠标事件序列（模拟真实用户点击）
            function fire(type, x, y) {
                var evt = new MouseEvent(type, {
                    bubbles: true, cancelable: true, view: window,
                    clientX: x, clientY: y, screenX: x, screenY: y,
                    button: 0, buttons: type === 'mouseup' ? 0 : 1,
                    relatedTarget: null
                });
                el.dispatchEvent(evt);
                // 同时在 document 级别派发（React 事件委托监听 document/root）
                var docEvt = new MouseEvent(type, {
                    bubbles: true, cancelable: true, view: window,
                    clientX: x, clientY: y, screenX: x, screenY: y,
                    button: 0, buttons: type === 'mouseup' ? 0 : 1,
                    target: el, relatedTarget: null
                });
                document.dispatchEvent(docEvt);
            }

            // mousedown → mouseup → click 完整序列
            fire('mousedown', cx, cy);
            fire('mouseup', cx, cy);
            fire('click', cx, cy);

            // 额外：尝试 focus + 触摸事件
            if (typeof el.focus === 'function') { try { el.focus(); } catch(e) {} }

            return JSON.stringify({
                success:true,
                message:'已点击 ('+cx+','+cy+')',
                debug:{selector:'\(selector)',index:\(index),x:cx,y:cy,w:Math.round(rect.width),h:Math.round(rect.height),tag:el.tagName}
            });
        } catch(e) { return JSON.stringify({success:false, message:'点击异常:'+e.message}); }})();
        """
    }

    /// 通过 CSS 选择器点击元素
    static func clickBySelectorScript(_ selector: String, index: Int = 0) -> String {
        return coordinateClickJS(selector: selector, index: index)
    }

    /// 通过坐标直接点击（最底层方式）
    static func coordinateClickScript(x: Int, y: Int) -> String {
        return """
        (function(){try{
            var target = null;
            // 找到坐标下的元素
            var el = document.elementFromPoint(\(x), \(y));
            if (!el) return JSON.stringify({success:false, message:'坐标(\(x),\(y))下没有元素'});

            target = el;
            // 如果找到的是子元素，向上找可交互的父元素（最多3层）
            for (var up = 0; up < 3; up++) {
                var p = target.parentElement;
                if (!p) break;
                var pr = p.getBoundingClientRect();
                if (pr.width > 20 && pr.height > 20) { target = p; break; }
                target = p;
            }

            function fire(type, px, py) {
                var evt = new MouseEvent(type, {
                    bubbles:true, cancelable:true, view:window,
                    clientX:px, clientY:py, screenX:px, screenY:py,
                    button:0, buttons:type==='mouseup'?0:1
                });
                target.dispatchEvent(evt);
                document.dispatchEvent(new MouseEvent(type, {
                    bubbles:true, cancelable:true, view:window,
                    clientX:px, clientY:py, screenX:px, screenY:py,
                    button:0, buttons:type==='mouseup'?0:1, target:target
                }));
            }
            fire('mousedown', \(x), \(y));
            fire('mouseup', \(x), \(y));
            fire('click', \(x), \(y));
            if (typeof target.focus === 'function') try{target.focus();}catch(e){}

            return JSON.stringify({success:true, message:'坐标点击('+\(x)+','+\(y)+')', tag:target.tagName, class:(target.className||'').toString().substring(0,60)});
        } catch(e) { return JSON.stringify({success:false, message:e.message}); }})();
        """
    }

    // ============================================================
    // MARK: - 平滑滚动
    // ============================================================

    static func scrollScript(direction: String) -> String {
        let delta = (direction == "up") ? "400" : "-400"
        return """
        (function(){try{
            var startY=window.pageYOffset||document.documentElement.scrollTop||0;
            var targetY=startY+\(delta);
            var scrolled=false;
            var scrollEl=null;

            var candidates=[document.scrollingElement,document.documentElement,document.body];
            var allDivs=document.querySelectorAll('div');
            for(var i=0;i<allDivs.length;i++){
                var d=allDivs[i];
                var cs=window.getComputedStyle(d);
                if(cs.overflowY==='auto' || cs.overflowY==='scroll' || cs.overflow==='auto' || cs.overflow==='scroll'){
                    candidates.push(d);
                }
            }

            for(var j=0;j<candidates.length;j++){
                var el=candidates[j];
                if(!el)continue;
                try{
                    var height=el.scrollHeight||0;
                    var clientHeight=el.clientHeight||0;
                    if(height>clientHeight+100){
                        scrollEl=el;
                        break;
                    }
                }catch(e){}
            }

            if(!scrollEl){
                scrollEl=document.scrollingElement||document.documentElement||document.body;
            }

            try{
                scrollEl.scrollBy({top: \(delta), behavior: 'smooth'});
                scrolled=true;
            }catch(e){}

            if(!scrolled){
                var t0=null;
                function step(ts){if(!t0)t0=ts;var p=Math.min((ts-t0)/500,1);var e=1-Math.pow(1-p,3);window.scrollTo(0,startY+(targetY-startY)*e);if(p<1)requestAnimationFrame(step);}
                requestAnimationFrame(step);
            }

            setTimeout(function(){
                var endY=window.pageYOffset||document.documentElement.scrollTop||0;
                var diff=endY-startY;
                if(Math.abs(diff)<50){
                    try{scrollEl.scrollTo({top: startY+\(delta), behavior: 'smooth'});}catch(e){}
                }
            },600);

            return JSON.stringify({success:true,message:'平滑滚动 '+\(delta)+'px',startY:startY,targetY:targetY,scrollEl:scrollEl?scrollEl.tagName:'null'});
        }catch(e){return JSON.stringify({success:false,message:e.message});}})();
        """
    }

    /// 滚动到指定像素位置
    static func scrollToPixelScript(y: Int) -> String {
        return """
        (function(){try{
            var startY=window.pageYOffset||0;var t0=null;
            function step(ts){if(!t0)t0=ts;var p=Math.min((ts-t0)/600,1);var e=1-Math.pow(1-p,3);window.scrollTo(0,startY+(\(y)-startY)*e);if(p<1)requestAnimationFrame(step);}
            requestAnimationFrame(step);
            return JSON.stringify({success:true, message:'滚动到 y=\(y)'});
        }catch(e){return JSON.stringify({success:false,message:e.message});}})();
        """
    }

    // ============================================================
    // MARK: - 点赞（使用坐标点击引擎）
    // ============================================================

    static func likeScript(for platform: String) -> String {
        switch platform {
        case "douyin": return douyinLikeScript()
        default: return xiaohongshuLikeScript()
        }
    }

    private static func xiaohongshuLikeScript() -> String {
        return """
        (function(){try{
            var result = null;

            // ===== 策略1: 通过观察找到点赞按钮的坐标并点击 =====
            var obs = (function(){
                try {
                    var btns = document.querySelectorAll('button, [role="button"], [class*="action"], [class*="like"], [class*="heart"], [tabindex], a[tabindex], div[tabindex]');
                    var candidates = [];
                    for (var i = 0; i < btns.length; i++) {
                        var r = btns[i].getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) continue;
                        if (r.top < 0 || r.bottom > window.innerHeight) continue;

                        var text = (btns[i].innerText || btns[i].textContent || btns[i].getAttribute('aria-label') || '').trim();
                        var cls = (btns[i].className || '').toString();

                        // 高优先级: 明确含赞/like/heart 关键词
                        var score = 0;
                        if (text.indexOf('赞') >= 0 || text.toLowerCase().indexOf('like') >= 0) score += 10;
                        if (cls.toLowerCase().indexOf('like') >= 0 || cls.indexOf('heart') >= 0 || cls.indexOf('collect') >= 0) score += 8;
                        if (cls.indexOf('action') >= 0 || cls.indexOf('interact') >= 0) score += 5;
                        // 底部操作栏区域的按钮优先
                        if (r.top > window.innerHeight * 0.6) score += 3;
                        // 小尺寸按钮更可能是图标按钮
                        if (r.width < 80 && r.height < 80) score += 2;

                        if (score > 0) {
                            candidates.push({el: btns[i], score: score, text: text, cls: cls, x: Math.round(r.left+r.width/2), y: Math.round(r.top+r.height/2)});
                        }
                    }
                    // 按 score 排序
                    candidates.sort(function(a,b){return b.score-a.score;});
                    return candidates.slice(0, 5);
                } catch(e) { return []; }
            })();

            if (obs.length > 0) {
                var best = obs[0];
                var el = best.el;

                // scrollIntoView + 坐标点击
                el.scrollIntoView({block:'center'}); void el.offsetHeight;
                var rect = el.getBoundingClientRect();
                var cx = Math.round(rect.left + rect.width/2);
                var cy = Math.round(rect.top + rect.height/2);

                function fire(t,x,y){var e=new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,screenX:x,screenY:y,button:0,buttons:t==='mouseup'?0:1});el.dispatchEvent(e);document.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,screenX:x,screenY:y,button:0,buttons:t==='mouseup'?0:1,target:el}));}
                fire('mousedown',cx,cy);fire('mouseup',cx,cy);fire('click',cx,cy);

                result = {success:true, message:'策略1: 点击了「'+best.text+'」按钮('+cx+','+cy+')', method:'coordinate', targetText: best.text};
            }

            // ===== 策略2: SVG path 心形图标 =====
            if (!result) {
                var paths = document.querySelectorAll('path');
                for (var pi = 0; pi < paths.length && pi < 50; pi++) {
                    var d = paths[pi].getAttribute('d') || '';
                    if (d.length > 60 && d.indexOf('M') >= 0 && (d.indexOf('C') >= 0 || d.indexOf('Q') >= 0)) {
                        var pr = paths[pi].getBoundingClientRect();
                        if (pr.width > 0 && pr.height > 0 && pr.top > 0 && pr.top < window.innerHeight) {
                            // 向上找可交互父元素
                            var parent = paths[pi].parentElement;
                            for (var up = 0; up < 4 && parent; up++) {
                                var par = parent.getBoundingClientRect();
                                if (par.width > 10 && par.height > 10) {
                                    parent.scrollIntoView({block:'center'}); void parent.offsetHeight;
                                    var pcx = Math.round(par.left + par.width/2);
                                    var pcy = Math.round(par.top + par.height/2);
                                    function f2(t,x,y){var ev=new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,button:0,buttons:t==='mouseup'?0:1});parent.dispatchEvent(ev);document.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,target:parent}));}
                                    f2('mousedown',pcx,pcy);f2('mouseup',pcx,pcy);f2('click',pcx,pcy);
                                    result = {success:true, message:'策略2: 点击了心形path父元素(第'+(up+1)+'层)('+pcx+','+pcy+')'};
                                    break;
                                }
                                parent = parent.parentElement;
                            }
                            if (result) break;
                        }
                    }
                }
            }

            // ===== 策略3: 文本匹配"赞" =====
            if (!result) {
                var all = document.querySelectorAll('button, a, span, div');
                for (var j = 0; j < all.length && j < 200; j++) {
                    var txt = (all[j].innerText || all[j].textContent || '').trim();
                    if ((txt === '赞' || txt === '点赞' || txt === '喜欢')) {
                        var ar = all[j].getBoundingClientRect();
                        if (ar.width > 0 && ar.height > 0) {
                            all[j].scrollIntoView({block:'center'}); void all[j].offsetHeight;
                            var ax = Math.round(ar.left + ar.width/2);
                            var ay = Math.round(ar.top + ar.height/2);
                            function f3(t,x,y){var ev=new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,button:0});all[j].dispatchEvent(ev);}
                            f3('mousedown',ax,ay);f3('mouseup',ax,ay);f3('click',ax,ay);
                            result = {success:true, message:'策略3: 点击了文本「'+txt+'」('+ax+','+ay+')'};
                            break;
                        }
                    }
                }
            }

            if (result) return JSON.stringify(result);

            // 诊断
            var dbgTotal = document.querySelectorAll('button, [role="button"]').length;
            return JSON.stringify({success:false, message:'未找到点赞元素', debug:{totalButtons:dbgTotal, pageUrl:location.href.substring(0,100)}});
        } catch(e) { return JSON.stringify({success:false, message:'JS异常:'+e.message}); }})();
        """
    }

    private static func douyinLikeScript() -> String {
        return """
        (function(){try{
            var obs=(function(){var b=document.querySelectorAll('[class*="like"],[class*="heart"],[class*="Love"],button');var c=[];for(var i=0;i<b.length;i++){var r=b[i].getBoundingClientRect();if(r.width>0&&r.height>0&&r.top>0&&r.top<window.innerHeight){c.push({el:b[i],x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)});}}return c;})();
            if(obs.length>0){var best=obs[0];best.el.scrollIntoView({block:'center'});void best.el.offsetHeight;var cr=best.el.getBoundingClientRect();var cx=Math.round(cr.left+cr.width/2);var cy=Math.round(cr.top+cr.height/2);function f(t){var e=new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,button:0,buttons:t==='mouseup'?0:1});best.el.dispatchEvent(e);document.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,target:best.el}));}f('mousedown');f('mouseup');f('click');return JSON.stringify({success:true,message:'已点赞('+cx+','+cy+')'});}
            return JSON.stringify({success:false,message:'未找到点赞按钮'});
        }catch(e){return JSON.stringify({success:false,message:'JS异常'});}})();
        """
    }

    // ============================================================
    // MARK: - 点击笔记（使用坐标点击引擎）
    // ============================================================

    /// 点击第一篇可见笔记
    static func clickFirstPostScript(for platform: String) -> String {
        return """
        (function(){try{
            // 收集所有可能的笔记元素
            var selectors = 'a[href*="/note/"], a[href*="/explore/"], section[class*="note"], div[class*="note-card"], div[class*="feeds-item"], article, section[class*="item"]';
            var items = document.querySelectorAll(selectors);
            var target = null;

            for (var i = 0; i < items.length; i++) {
                var r = items[i].getBoundingClientRect();
                // 必须足够大且在可视区内
                if (r.width > 100 && r.height > 100 && r.top > 0 && r.top < window.innerHeight * 0.85 && r.bottom > 0) {
                    target = items[i]; break;
                }
            }

            // 兜底：找任意可见的大链接
            if (!target) {
                var links = document.querySelectorAll('a[href]');
                for (var j = 0; j < links.length; j++) {
                    var lr = links[j].getBoundingClientRect();
                    if (lr.width > 100 && lr.height > 60 && lr.top > 0 && lr.top < window.innerHeight * 0.9) {
                        target = links[j]; break;
                    }
                }
            }

            if (!target) return JSON.stringify({success:false, message:'未找到可点击的笔记'});

            // 坐标点击
            target.scrollIntoView({behavior:'instant', block:'center'}); void target.offsetHeight;
            var tr = target.getBoundingClientRect();
            var tx = Math.round(tr.left + tr.width / 2);
            var ty = Math.round(tr.top + tr.height / 2);

            function fire(t, x, y) {
                var evt = new MouseEvent(t, {bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,screenX:x,screenY:y,button:0,buttons:t==='mouseup'?0:1});
                target.dispatchEvent(evt);
                document.dispatchEvent(new MouseEvent(t, {bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,target:target}));
            }
            fire('mousedown', tx, ty);
            fire('mouseup', tx, ty);
            fire('click', tx, ty);

            var href = '';
            if (target.tagName === 'A') href = target.getAttribute('href') || '';
            else { var tl = target.querySelector('a[href]'); if (tl) href = tl.getAttribute('href') || ''; }

            return JSON.stringify({success:true, message:'点击笔记 ('+tx+','+ty+')', href:href.substring(0,100)});
        } catch(e) { return JSON.stringify({success:false, message:'JS异常:'+e.message}); }})();
        """
    }

    /// 随机点击一篇可见笔记
    static func clickRandomNoteScript(for platform: String) -> String {
        return """
        (function(){try{
            var sel = 'a[href*="/note/"], a[href*="/explore/"], a[href*="/search_result/"], section[class*="note"], div[class*="note-card"], div[class*="feeds-item"], div[class*="search-item"], article, div[class*="card"]';
            var items = document.querySelectorAll(sel);
            var candidates = [];

            for (var i = 0; i < items.length; i++) {
                var r = items[i].getBoundingClientRect();
                if (r.width > 80 && r.height > 80 && r.top > 20 && r.top < window.innerHeight * 0.9 && r.bottom > 20) {
                    candidates.push(items[i]);
                }
            }

            if (candidates.length === 0) {
                var links = document.querySelectorAll('a[href]');
                for (var j = 0; j < links.length; j++) {
                    var lr = links[j].getBoundingClientRect();
                    if (lr.width > 80 && lr.height > 60 && lr.top > 20 && lr.top < window.innerHeight * 0.8) candidates.push(links[j]);
                }
            }

            if (candidates.length === 0) return JSON.stringify({success:false, message:'页面没有可见的笔记卡片'});

            var idx = Math.floor(Math.random() * candidates.length);
            var target = candidates[idx];

            target.scrollIntoView({behavior:'instant', block:'center'}); void target.offsetHeight;
            var tr = target.getBoundingClientRect();
            var tx = Math.round(tr.left + tr.width / 2);
            var ty = Math.round(tr.top + tr.height / 2);

            function fire(t, x, y) {
                var evt = new MouseEvent(t, {bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,button:0,buttons:t==='mouseup'?0:1});
                target.dispatchEvent(evt);
                document.dispatchEvent(new MouseEvent(t, {bubbles:true,cancelable:true,view:window,clientX:x,clientY:y,target:target}));
            }
            fire('mousedown', tx, ty);
            fire('mouseup', tx, ty);
            fire('click', tx, ty);

            return JSON.stringify({success:true, message:'随机点击第'+(idx+1)+'/'+candidates.length+'篇笔记 ('+tx+','+ty+')'});
        } catch(e) { return JSON.stringify({success:false, message:'JS异常:'+e.message}); }})();
        """
    }

    // ============================================================
    // MARK: - 其他操作
    // ============================================================

    static func goBackScript() -> String {
        return """
        (function(){try{if(window.history.length>1){window.history.back();return JSON.stringify({success:true,message:'已返回'});}return JSON.stringify({success:false,message:'无法返回'});}catch(e){return JSON.stringify({success:false,message:e.message});}})();
        """
    }

    static func collectScript(for platform: String) -> String {
        return """
        (function(){try{
            var sel='[class*="collect"],[class*="Collect"],[class*="star"],[class*="bookmark"]';
            var els=document.querySelectorAll(sel);
            var target=null;
            for(var i=0;i<els.length&&i<15;i++){var r=els[i].getBoundingClientRect();if(r.width>0&&r.height>0&&r.top>0&&r.top<window.innerHeight){target=els[i];break;}}
            if(!target){
                var ps=document.querySelectorAll('path');for(var j=0;j<ps.length&&j<30;j++){var d=ps[j].getAttribute('d')||'';if(d.length>40&&d.indexOf('M')>=0){var pr=ps[j].getBoundingClientRect();if(pr.width>0&&pr.height>0&&pr.top>0&&pr.top<window.innerHeight){target=ps[j];for(var u=0;u<3;u++){var p=target.parentElement;if(!p)break;var pp=p.getBoundingClientRect();if(pp.width>10&&pp.height>10){target=p;break;}target=p;}break;}}}}
            if(!target)return JSON.stringify({success:false,message:'未找到收藏按钮'});
            target.scrollIntoView({block:'center'});void target.offsetHeight;
            var tr=target.getBoundingClientRect();var tx=Math.round(tr.left+tr.width/2);var ty=Math.round(tr.top+tr.height/2);
            function f(t){var e=new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:tx,clientY:ty,button:0,buttons:t==='mouseup'?0:1});target.dispatchEvent(e);document.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:tx,clientY:ty,target:target}));}
            f('mousedown');f('mouseup');f('click');
            return JSON.stringify({success:true,message:'已收藏('+tx+','+ty+')'});
        }catch(e){return JSON.stringify({success:false,message:'JS异常:'+e.message});}})();
        """
    }

    static func followScript(for platform: String) -> String {
        return """
        (function(){try{
            var all=document.querySelectorAll('button,a,span,div');var target=null;
            for(var i=0;i<all.length&&i<200;i++){var t=(all[i].innerText||all[i].textContent||'').trim();if((t==='关注'||t==='+ 关注'||t==='Follow'||t==='+Follow')){var r=all[i].getBoundingClientRect();if(r.width>0&&r.height>0&&r.top>0&&r.top<window.innerHeight){target=all[i];break;}}}
            if(!target){var fc=document.querySelectorAll('[class*="follow"]');for(var j=0;j<fc.length&&j<20;j++){var fr=fc[j].getBoundingClientRect();if(fr.width>0&&fr.height>0&&fr.top>0&&fr.top<window.innerHeight){target=fc[j];break;}}}
            if(!target)return JSON.stringify({success:false,message:'未找到关注按钮'});
            target.scrollIntoView({block:'center'});void target.offsetHeight;
            var tr=target.getBoundingClientRect();var tx=Math.round(tr.left+tr.width/2);var ty=Math.round(tr.top+tr.height/2);
            function f(t){var e=new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:tx,clientY:ty,button:0});target.dispatchEvent(e);}
            f('mousedown');f('mouseup');f('click');
            return JSON.stringify({success:true,message:'已关注'});
        }catch(e){return JSON.stringify({success:false,message:'JS异常:'+e.message});}})();
        """
    }

    static func commentScript(for platform: String, text: String) -> String {
        let escaped = text.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "'", with: "\\'").replacingOccurrences(of: "\"", with: "\\\"").replacingOccurrences(of: "\n", with: " ").replacingOccurrences(of: "\r", with: "")
        return """
        (function(){try{
            var input=null;var tas=document.querySelectorAll('textarea');for(var i=0;i<tas.length;i++){input=tas[i];break;}
            if(!input){var ins=document.querySelectorAll('input[type="text"]');for(var j=0;j<ins.length;j++){var ph=(ins[j].getAttribute('placeholder')||'').toLowerCase();if(ph.indexOf('评论')>=0||ph.indexOf('留言')>=0){input=ins[j];break;}}}
            if(!input)return JSON.stringify({success:false,message:'未找到评论输入框'});
            input.scrollIntoView({block:'center'});void input.offsetHeight;
            var ir=input.getBoundingClientRect();var ix=Math.round(ir.left+ir.width/2);var iy=Math.round(ir.top+ir.height/2);
            // 点击聚焦
            function f(t){var e=new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:ix,clientY:iy,button:0});input.dispatchEvent(e);}f('mousedown');f('mouseup');f('click');
            input.focus();
            // 输入文本
            input.value='\(escaped)';
            var ie=new Event('input',{bubbles:true});input.dispatchEvent(ie);
            var ce=new Event('change',{bubbles:true});input.dispatchEvent(ce);
            // 找发送按钮
            var btns=document.querySelectorAll('button,a,div,span');var sBtn=null;
            for(var k=0;k<btns.length;k++){var bt=(btns[k].innerText||'').trim();if(bt==='发送'||bt==='评论'||bt.indexOf('发送')>=0){var br=btns[k].getBoundingClientRect();if(br.width>0&&br.height>0){sBtn=btns[k];break;}}}
            if(sBtn){sBtn.scrollIntoView({block:'center'});void sBtn.offsetHeight;var sr=sBtn.getBoundingClientRect();var sx=Math.round(sr.left+sr.width/2);var sy=Math.round(sr.top+sr.height/2);
            function sf(t){var e=new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:sx,clientY:sy,button:0});sBtn.dispatchEvent(e);document.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:sx,clientY:sy,target:sBtn}));}
            sf('mousedown');sf('mouseup');sf('click');return JSON.stringify({success:true,message:'已发送评论'});}
            return JSON.stringify({success:false,message:'未找到发送按钮'});
        }catch(e){return JSON.stringify({success:false,message:'JS异常:'+e.message});}})();
        """
    }

    // ============================================================
    // MARK: - 内容识别（Agent 的"理解"能力）
    // ============================================================

    /// 提取当前笔记/视频的完整内容信息（标题、作者、标签、正文、点赞数等）
    static func extractContentScript() -> String {
        return """
        (function(){try{
            var info = { success:true };
            info.url = location.href.substring(0, 200);
            info.title = document.title || '';

            // 标题提取
            var titleEl = document.querySelector('h1, [class*="title"], [class*="Title"], [data-testid="note-title"]');
            if (titleEl) info.noteTitle = (titleEl.innerText || titleEl.textContent || '').trim().substring(0, 200);
            else {
                // 兜底：找最大的文本块
                var allText = document.querySelectorAll('span, div, p');
                var best = ''; var bestLen = 0;
                for (var i = 0; i < allText.length && i < 50; i++) {
                    var t = (allText[i].innerText || '').trim();
                    if (t.length > bestLen && t.length < 300) { best = t; bestLen = t.length; }
                }
                if (bestLen > 10) info.noteTitle = best.substring(0, 200);
            }

            // 作者信息
            var authorEl = document.querySelector('[class*="author"], [class*="user-name"], [class*="nickname"], [class*="User"], a[href*="/user/"]');
            if (authorEl) info.author = (authorEl.innerText || authorEl.textContent || '').trim().substring(0, 50);

            // 标签/话题
            var tags = [];
            var tagEls = document.querySelectorAll('[class*="tag"], [class*="topic"], [class*="hash"], a[href*="/search_result/"]');
            for (var ti = 0; ti < tagEls.length && ti < 20; ti++) {
                var tagText = (tagEls[ti].innerText || tagEls[ti].textContent || '').trim();
                if (tagText && tagText.length < 30 && tagText.indexOf('#') >= 0) tags.push(tagText.replace(/#/g, ''));
                else if (tagText && tagText.length < 30) tags.push(tagText);
            }
            // 额外从标题中提取 #标签#
            var rawTitle = info.noteTitle || '';
            var hashMatches = rawTitle.match(/#[^#]+#/g);
            if (hashMatches) { for (var hi = 0; hi < hashMatches.length; hi++) { var h = hashMatches[hi].replace(/#/g, ''); if (h.length > 0 && h.length < 30) tags.push(h); }}
            info.tags = tags.slice(0, 15);

            // 正文内容摘要
            var bodyEl = document.querySelector('[class*="desc"], [class*="content"], [class*="note-text"], [class*="post-content"], article');
            if (bodyEl) info.bodyPreview = (bodyEl.innerText || bodyEl.textContent || '').trim().substring(0, 500);

            // 互动数据
            var likeEl = document.querySelector('[class*="like-count"], [class*="LikeCount"], span[class*="count"]');
            if (likeEl) { var ln = parseInt((likeEl.innerText || '').replace(/[^0-9]/g, '')); if (!isNaN(ln)) info.likeCount = ln; }

            // 页面类型判断
            if (info.url.indexOf('/note/') >= 0 || info.url.indexOf('/discovery/') >= 0) info.pageType = 'detail';
            else if (info.url.indexOf('/explore') >= 0 || info.url.indexOf('/feed') >= 0) info.pageType = 'list';
            else if (info.url.indexOf('/search_result') >= 0) info.pageType = 'search';
            else info.pageType = 'other';

            // 检测是否为视频笔记
            var videoTags = document.querySelectorAll('video, [class*="video"], [class*="Video"], [data-video], video source, div[class*="player"]');
            info.isVideo = videoTags.length > 0;

            return JSON.stringify(info);
        } catch(e) { return JSON.stringify({success:false, message:'识别异常:'+e.message}); }})();
        """
    }

    /// 提取评论区信息（评论列表、评论者、评论内容）
    static func extractCommentsScript() -> String {
        return """
        (function(){try{
            var comments = [];
            // 小红书评论区选择器
            var selectors = '[class*="comment"], [class*="Comment"], [class*="reply"], [class*="Reply"], section[class*="comment"]';
            var items = document.querySelectorAll(selectors + ', div[class*="comment-item"], div[class*="comment-item"]');

            for (var i = 0; i < items.length && i < 20; i++) {
                var el = items[i];
                var r = el.getBoundingClientRect();
                if (r.width < 30 || r.height < 20) continue;

                var text = (el.innerText || el.textContent || '').trim();

                // 过滤掉太短或太长的（可能是容器元素）
                if (text.length < 2 || text.length > 500) continue;

                // 尝试提取评论者名字
                var author = '';
                var authEl = el.querySelector('[class*="author"], [class*="user"], [class*="name"], [class*="nick"]');
                if (authEl) author = (authEl.innerText || authEl.textContent || '').trim().substring(0, 30);

                // 如果文本包含作者名，去掉它
                if (author && text.startsWith(author)) text = text.substring(author.length).trim();

                comments.push({
                    index: comments.length,
                    author: author,
                    text: text.substring(0, 200),
                    hasLikeButton: (el.querySelector('[class*="like"], [class*="heart"]') !== null),
                    y: Math.round(r.top)
                });
            }

            return JSON.stringify({
                success: true,
                count: comments.length,
                comments: comments,
                commentSectionY: (function(){
                    var header = document.querySelector('[class*="comment-header"], [class*="CommentHeader"], h3:contains("评论")');
                    if (header) return Math.round(header.getBoundingClientRect().top);
                    // 找"评论"文字位置
                    var all = document.querySelectorAll('*');
                    for (var j = 0; j < all.length; j++) {
                        if ((all[j].innerText || '').indexOf('评论') === 0 && (all[j].innerText || '').length < 10) {
                            return Math.round(all[j].getBoundingClientRect().top);
                        }
                    }
                    return -1;
                })()
            });
        } catch(e) { return JSON.stringify({success:false, message:'异常:'+e.message}); }})();
        """
    }

    /// 暂停所有视频播放
    static func pauseVideoScript() -> String {
        return """
        (function(){try{
            // 暂停所有视频
            var videos = document.querySelectorAll('video');
            for(var i=0; i<videos.length; i++){
                videos[i].pause();
            }
            // 移除自动播放属性
            videos.forEach(function(v){
                v.removeAttribute('autoplay');
                v.removeAttribute('autoPlay');
                v.muted = true;
            });
            return JSON.stringify({success:true, message:'已暂停视频'});
        }catch(e){return JSON.stringify({success:false, message:'暂停失败:'+e.message});}})();
        """
    }

    /// 搜索关键词 - 分步骤模拟真实用户操作
    static func findSearchEntryScript() -> String {
        return """
        (function(){try{
            var allElements = document.querySelectorAll('a, button, div, span, svg, img');
            var candidates = [];
            var viewH = window.innerHeight;
            
            for (var i = 0; i < allElements.length; i++) {
                var el = allElements[i];
                var r = el.getBoundingClientRect();
                
                if (r.width < 20 || r.height < 20 || r.width > 400) continue;
                if (r.top < 0 || r.top > viewH * 0.3) continue;
                if (r.left < 0 || r.left > window.innerWidth - 50) continue;
                
                var text = (el.innerText || el.textContent || '').trim();
                var cls = (el.className || '').toString();
                var ariaLabel = el.getAttribute('aria-label') || '';
                var placeholder = el.getAttribute('placeholder') || '';
                var tag = el.tagName;
                
                var score = 0;
                
                if (placeholder.indexOf('搜索') >= 0) score += 100;
                if (ariaLabel.indexOf('搜索') >= 0) score += 80;
                if (text === '搜索' || text === 'Search') score += 70;
                if (cls.toLowerCase().indexOf('search') >= 0) score += 60;
                if (cls.indexOf('Search') >= 0) score += 50;
                if (cls.toLowerCase().indexOf('input') >= 0 && r.width > 100 && r.width < 400) score += 40;
                if (tag === 'INPUT' && (r.width > 150 || placeholder.length > 0)) score += 30;
                if (r.top < 80 && r.width > 100) score += 20;
                if (cls.indexOf('icon') >= 0 && r.width < 50 && r.height < 50 && r.top < 100) score += 10;
                
                if (score > 0) {
                    candidates.push({
                        el: el,
                        score: score,
                        tag: tag,
                        text: text.substring(0, 30),
                        cls: cls.substring(0, 60),
                        placeholder: placeholder.substring(0, 30),
                        ariaLabel: ariaLabel,
                        x: Math.round(r.left + r.width / 2),
                        y: Math.round(r.top + r.height / 2),
                        w: Math.round(r.width),
                        h: Math.round(r.height)
                    });
                }
            }
            
            candidates.sort(function(a,b){return b.score - a.score;});
            var top = candidates.slice(0, 5);
            
            return JSON.stringify({
                success: top.length > 0,
                found: top.length > 0,
                candidates: top,
                count: candidates.length
            });
        }catch(e){return JSON.stringify({success:false, error:e.message, candidates:[], found:false});}})();
        """
    }
    
    static func clickSearchEntryScript() -> String {
        return """
        (function(){try{
            var allElements = document.querySelectorAll('a, button, div, span, svg, img, input');
            var candidates = [];
            var viewH = window.innerHeight;
            
            for (var i = 0; i < allElements.length; i++) {
                var el = allElements[i];
                var r = el.getBoundingClientRect();
                
                if (r.width < 20 || r.height < 20 || r.width > 500) continue;
                if (r.top < -20 || r.top > viewH * 0.5) continue;
                
                var text = (el.innerText || el.textContent || '').trim();
                var cls = (el.className || '').toString();
                var ariaLabel = el.getAttribute('aria-label') || '';
                var placeholder = el.getAttribute('placeholder') || '';
                var tag = el.tagName;
                
                var score = 0;
                if (placeholder.indexOf('搜索') >= 0) score += 100;
                if (placeholder.indexOf('Search') >= 0) score += 90;
                if (ariaLabel.indexOf('搜索') >= 0) score += 80;
                if (text === '搜索') score += 70;
                if (cls.indexOf('search-input') >= 0) score += 85;
                if (cls.toLowerCase().indexOf('search') >= 0) score += 60;
                if (cls.indexOf('Search') >= 0) score += 50;
                if (tag === 'INPUT' && (r.width > 100 || placeholder.length > 0)) score += 40;
                if (r.top < 100 && r.width > 100) score += 20;
                
                if (score > 0) candidates.push({el:el, score:score, tag:tag, cls:cls});
            }
            
            candidates.sort(function(a,b){return b.score - a.score;});
            
            if (candidates.length === 0) {
                return JSON.stringify({success:false, message:'未找到搜索入口'});
            }
            
            var best = candidates[0].el;
            
            if (best.tagName !== 'INPUT' && best.querySelector) {
                var innerInput = best.querySelector('input, [contenteditable]');
                if (innerInput) {
                    var ir = innerInput.getBoundingClientRect();
                    if (ir.width > 10) {
                        best = innerInput;
                    }
                }
            }
            
            best.scrollIntoView({block:'center', behavior:'instant'});
            void best.offsetHeight;
            
            var rect = best.getBoundingClientRect();
            var cx = Math.round(rect.left + rect.width/2);
            var cy = Math.round(rect.top + rect.height/2);
            
            function fire(t,x,y,target){
                var evt = new MouseEvent(t, {
                    bubbles:true, cancelable:true, view:window,
                    clientX:x, clientY:y, screenX:x, screenY:y,
                    button:0, buttons:t==='mouseup'?0:1
                });
                target.dispatchEvent(evt);
                document.dispatchEvent(new MouseEvent(t, {
                    bubbles:true, cancelable:true, view:window,
                    clientX:x, clientY:y, screenX:x, screenY:y,
                    button:0, buttons:t==='mouseup'?0:1, target:target
                }));
            }
            
            fire('mousedown', cx, cy, best);
            setTimeout(function(){
                fire('mouseup', cx, cy, best);
            }, 50);
            setTimeout(function(){
                fire('click', cx, cy, best);
            }, 100);
            
            if (typeof best.focus === 'function') {
                try { best.focus(); } catch(e) {}
            }
            
            return JSON.stringify({
                success:true, 
                message:'已点击搜索入口',
                clickedTag: best.tagName,
                clickedClass: (best.className||'').toString().substring(0,80),
                x: cx,
                y: cy,
                w: Math.round(rect.width),
                h: Math.round(rect.height)
            });
        }catch(e){return JSON.stringify({success:false, message:'点击失败:'+e.message});}})();
        """
    }
    
    static func inputSearchKeywordScript(keyword: String) -> String {
        let escaped = keyword.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "'", with: "\\'").replacingOccurrences(of: "\"", with: "\\\"")
        return """
        (function(){try{
            var kw='\(escaped)';
            
            var allInputs = document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]), textarea, [contenteditable="true"]');
            var candidates = [];
            
            for (var i = 0; i < allInputs.length; i++) {
                var el = allInputs[i];
                var r = el.getBoundingClientRect();
                var placeholder = el.placeholder || el.getAttribute('placeholder') || '';
                var ariaLabel = el.getAttribute('aria-label') || '';
                var type = el.type || '';
                var tag = el.tagName;
                var cls = (el.className || '').toString();
                var parentCls = el.parentElement ? (el.parentElement.className || '').toString() : '';
                
                if (r.width < 30 || r.height < 15) continue;
                
                var score = 0;
                if (placeholder.indexOf('搜索') >= 0) score += 100;
                if (placeholder.indexOf('Search') >= 0) score += 90;
                if (ariaLabel.indexOf('搜索') >= 0) score += 80;
                if (type === 'search') score += 70;
                if (tag === 'INPUT' && cls.toLowerCase().indexOf('search') >= 0) score += 60;
                if (parentCls.toLowerCase().indexOf('search') >= 0) score += 50;
                if (r.top < window.innerHeight * 0.4 && tag === 'INPUT' && r.width > 80) score += 30;
                if (r.top < 150 && r.width > 100) score += 20;
                
                candidates.push({
                    el: el,
                    score: score,
                    tag: tag,
                    type: type,
                    placeholder: placeholder.substring(0, 30),
                    cls: cls.substring(0, 60),
                    parentCls: parentCls.substring(0, 60),
                    top: Math.round(r.top),
                    left: Math.round(r.left),
                    w: Math.round(r.width),
                    h: Math.round(r.height)
                });
            }
            
            candidates.sort(function(a,b){return b.score - a.score;});
            
            var searchInput = null;
            var debugInfo = [];
            for (var c = 0; c < candidates.length && c < 8; c++) {
                var cand = candidates[c];
                debugInfo.push({
                    tag: cand.tag,
                    type: cand.type,
                    placeholder: cand.placeholder,
                    cls: cand.cls,
                    score: cand.score,
                    top: cand.top,
                    w: cand.w
                });
                if (cand.score > 0 && !searchInput) {
                    searchInput = cand.el;
                }
            }
            
            if (!searchInput && candidates.length > 0) {
                for (var d = 0; d < candidates.length; d++) {
                    if (candidates[d].tag === 'INPUT' && candidates[d].w > 100) {
                        searchInput = candidates[d].el;
                        break;
                    }
                }
            }
            
            if (!searchInput && candidates.length > 0) {
                searchInput = candidates[0].el;
            }
            
            if (!searchInput) {
                return JSON.stringify({success:false, message:'页面上没有任何输入框', debug: debugInfo});
            }
            
            searchInput.scrollIntoView({block:'center', behavior:'instant'});
            void searchInput.offsetHeight;
            searchInput.focus();
            
            if (searchInput.tagName === 'INPUT' || searchInput.tagName === 'TEXTAREA') {
                var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
                if (searchInput.tagName === 'TEXTAREA') {
                    nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
                }
                
                if (nativeInputValueSetter && nativeInputValueSetter.set) {
                    nativeInputValueSetter.set.call(searchInput, kw);
                } else {
                    searchInput.value = kw;
                }
            } else {
                searchInput.textContent = kw;
                searchInput.innerText = kw;
            }
            
            searchInput.dispatchEvent(new Event('input', {bubbles:true}));
            searchInput.dispatchEvent(new Event('change', {bubbles:true}));
            
            setTimeout(function(){
                var enterKeyCode = 13;
                searchInput.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', keyCode:enterKeyCode, which:enterKeyCode, bubbles:true, cancelable:true}));
                searchInput.dispatchEvent(new KeyboardEvent('keypress', {key:'Enter', keyCode:enterKeyCode, which:enterKeyCode, bubbles:true, cancelable:true}));
                searchInput.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', keyCode:enterKeyCode, which:enterKeyCode, bubbles:true, cancelable:true}));
            }, 300);
            
            return JSON.stringify({
                success:true, 
                message:'已输入关键词: ' + kw,
                inputTag: searchInput.tagName,
                inputClass: (searchInput.className||'').toString().substring(0,60),
                inputPlaceholder: searchInput.placeholder || '',
                debug: debugInfo
            });
        }catch(e){return JSON.stringify({success:false, message:'输入失败:'+e.message});}})();
        """
    }

    /// 浏览评论区（滚动查看更多评论）
    static func browseCommentsScript(scrollCount: Int = 2) -> String {
        return """
        (function(){try{
            var count=\(scrollCount);
            var scrolled=0;
            function scrollDown(){
                var sy=window.pageYOffset||document.documentElement.scrollTop;
                var target=sy+400;
                var t0=null;
                function step(ts){if(!t0)t0=ts;var p=Math.min((ts-t0)/400,1);var e=1-Math.pow(1-p,3);window.scrollTo(0,sy+(target-sy)*e);if(p<1)requestAnimationFrame(step);}
                requestAnimationFrame(step);
            }
            for(var i=0;i<count;i++){scrollDown();scrolled++;}
            return JSON.stringify({success:true, message:'已浏览评论区，滚动了'+scrolled+'次'});
        }catch(e){return JSON.stringify({success:false, message:'浏览异常:'+e.message});}})();
        """
    }

    /// 给指定评论点赞（通过坐标点击评论的点赞按钮）
    static func likeCommentScript(commentIndex: Int = 0) -> String {
        return """
        (function(){try{
            var selectors='[class*="comment"], [class*="Comment"]';
            var items=document.querySelectorAll(selectors+',div[class*="comment-item"]');
            var targets=[];
            for(var i=0;i<items.length;i++){
                var r=items[i].getBoundingClientRect();
                if(r.width>30&&r.height>20&&r.top>0&&r.top<window.innerHeight){
                    var btn=items[i].querySelector('[class*="like"],[class*="heart"],[class*="Like"]');
                    if(btn){targets.push({container:items[i],btn:btn,x:Math.round(r.left+r.width/2),y:Math.round(r.top+r.height/2)});}
                }
            }
            if(targets.length===0)return JSON.stringify({success:false, message:'没有找到可点赞的评论'});
            var idx=\(commentIndex)<targets.length?\(commentIndex):Math.floor(Math.random()*targets.length);
            var target=targets[idx];
            target.btn.scrollIntoView({block:'center'});void target.btn.offsetHeight;
            var tr=target.btn.getBoundingClientRect();var cx=Math.round(tr.left+tr.width/2);var cy=Math.round(tr.top+tr.height/2);
            function f(t){var e=new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,button:0,buttons:t==='mouseup'?0:1});target.btn.dispatchEvent(e);document.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,target:target.btn}));}
            f('mousedown');f('mouseup');f('click');
            return JSON.stringify({success:true, message:'已点赞第'+(idx+1)+'条评论('+cx+','+cy+')'});
        }catch(e){return JSON.stringify({success:false, message:'异常:'+e.message});}})();
        """
    }

    /// 回复指定评论
    static func replyToCommentScript(commentIndex: Int = 0, replyText: String) -> String {
        let escaped = replyText.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "'", with: "\\'").replacingOccurrences(of: "\"", with: "\\\"").replacingOccurrences(of: "\n", with: " ")
        return """
        (function(){try{
            var text='\(escaped)';
            var sel='[class*="comment"], [class*="Comment"]';
            var items=document.querySelectorAll(sel+',div[class*="comment-item"]');
            var targets=[];
            for(var i=0;i<items.length;i++){
                var r=items[i].getBoundingClientRect();
                if(r.width>30&&r.height>20&&r.top>0&&r.top<window.innerHeight)targets.push(items[i]);
            }
            if(targets.length===0)return JSON.stringify({success:false, message:'没有找到评论'});
            var idx=\(commentIndex)<targets.length?\(commentIndex):Math.floor(Math.random()*targets.length);
            var container=targets[idx];

            // 点击评论区域展开回复框
            container.scrollIntoView({block:'center'});void container.offsetHeight;
            var cr=container.getBoundingClientRect();var cx=Math.round(cr.left+cr.width/2);var cy=Math.round(cr.top+cr.height/2);
            function f(t){var e=new MouseEvent(t,{bubbles:true,cancelable:true,view:window,clientX:cx,clientY:cy,button:0});container.dispatchEvent(e);}f('mousedown');f('mouseup');f('click');

            // 等一下再尝试输入
            var ta=container.querySelector('textarea,[contenteditable="true"],input[type="text"]');
            if(!ta){ta=document.querySelector('textarea,[contenteditable="true"]');}
            if(ta){
                ta.focus();ta.value=text;
                ta.dispatchEvent(new Event('input',{bubbles:true}));
                ta.dispatchEvent(new Event('change',{bubbles:true}));
                // 找回复按钮
                var btns=container.querySelectorAll('button,a,span,div');
                for(var k=0;k<btns.length;k++){
                    var bt=(btns[k].innerText||'').trim();
                    if(bt==='发送'||bt==='回复'||bt.indexOf('发送')>=0||bt.indexOf('回复')>=0){
                        btns[k].click();break;
                    }
                }
                return JSON.stringify({success:true, message:'已回复第'+(idx+1)+'条评论'});
            }
            return JSON.stringify({success:false, message:'未找到回复输入框'});
        }catch(e){return JSON.stringify({success:false, message:'异常:'+e.message});}})();
        """
    }

    /// 滚动到评论区位置
    static func scrollToCommentsScript() -> String {
        return """
        (function(){try{
            // 方法1: 找包含"评论"文字的元素
            var all=document.querySelectorAll('*');
            var found=null;
            for(var i=0;i<all.length&&!found;i++){
                var t=(all[i].innerText||'').trim();
                if((t==='评论'||t==='评论 (\\d+)'||t.indexOf('评论')===0)&&t.length<15){
                    var r=all[i].getBoundingClientRect();
                    if(r.top>0){found=all[i];}
                }
            }
            if(found){
                found.scrollIntoView({behavior:'instant',block:'start'});void found.offsetHeight;
                return JSON.stringify({success:true, message:'已滚动到评论区'});
            }
            // 方法2: 滚动到页面底部附近（评论区通常在底部）
            var docH=document.documentElement.scrollHeight;
            var target=Math.max(0,docH-window.innerHeight-200);
            var startY=window.pageYOffset||0;var t0=null;
            function step(ts){if(!t0)t0=ts;var p=Math.min((ts-t0)/600,1);var e=1-Math.pow(1-p,3);window.scrollTo(0,startY+(target-startY)*e);if(p<1)requestAnimationFrame(step);}
            requestAnimationFrame(step);
            return JSON.stringify({success:true, message:'已滚动到页面下方'});
        }catch(e){return JSON.stringify({success:false, message:'异常:'+e.message});}})();
        """
    }
}

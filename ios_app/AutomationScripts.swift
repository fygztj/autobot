//
//  AutomationScripts.swift
//  各平台的自动化脚本
//

import Foundation

enum AutomationScripts {

    // ============================================================
    // MARK: - 平台 URL
    // ============================================================

    static func url(for platform: String) -> String {
        switch platform {
        case "douyin":
            return "https://www.douyin.com"
        default:
            return "https://www.xiaohongshu.com/explore"
        }
    }

    // ============================================================
    // MARK: - 页面信息（用于诊断）
    // ============================================================

    static func pageInfoScript() -> String {
        return """
        (function(){try{
            var title = document.title || '';
            var url = location.href || '';
            var elementCount = document.querySelectorAll('*').length;
            var bodyText = (document.body ? document.body.innerText || '' : '').substring(0, 200);
            return JSON.stringify({success:true, title:title, url:url, elementCount:elementCount, bodyPreview:bodyText});
        } catch(e) {
            return JSON.stringify({success:false, message:e.message});
        }})();
        """
    }

    // ============================================================
    // MARK: - 滚动
    // ============================================================

    static func scrollScript(direction: String) -> String {
        let delta = (direction == "up") ? "400" : "-400"
        return """
        (function(){try{
            window.scrollBy(0, \(delta));
            return JSON.stringify({success:true, message:'已滚动 \(delta) px'});
        } catch(e) {
            return JSON.stringify({success:false, message:e.message});
        }})();
        """
    }

    // ============================================================
    // MARK: - 点赞
    // ============================================================

    static func likeScript(for platform: String) -> String {
        switch platform {
        case "douyin":
            return douyinLikeScript()
        default:
            return xiaohongshuLikeScript()
        }
    }

    private static func xiaohongshuLikeScript() -> String {
        return """
        (function(){try{
            var clicked = null;
            var msg = '';
            function isVisible(el) {
                try {
                    if (!el) return false;
                    var rect = el.getBoundingClientRect();
                    if (rect.width <= 0 || rect.height <= 0) return false;
                    if (rect.top >= window.innerHeight || rect.bottom <= 0) return false;
                    return true;
                } catch(e) { return true; }
            }
            function doClick(el) {
                try {
                    if (typeof el.click === 'function') { el.click(); return true; }
                } catch(e1) {}
                try {
                    var ev = document.createEvent('MouseEvents');
                    ev.initMouseEvent('click', true, true, window, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
                    el.dispatchEvent(ev);
                    return true;
                } catch(e2) {}
                return false;
            }

            // 策略1: SVG path 心形图标
            var paths = document.querySelectorAll('path');
            for (var i = 0; i < paths.length && i < 50; i++) {
                var d = paths[i].getAttribute('d') || '';
                if (d.length > 60 && d.indexOf('M') >= 0 && (d.indexOf('C') >= 0 || d.indexOf('Q') >= 0)) {
                    if (isVisible(paths[i])) { if (doClick(paths[i])) { clicked = paths[i]; msg = '策略1a: 点击心形path'; break; } }
                    var parent = paths[i].parentElement;
                    for (var up = 0; up < 4 && parent; up++) {
                        if (isVisible(parent)) { if (doClick(parent)) { clicked = parent; msg = '策略1b: 点击心形path父元素'; break; } }
                        parent = parent.parentElement;
                    }
                    if (clicked) break;
                }
            }

            // 策略2: 文本含"赞"的元素
            if (!clicked) {
                var all = document.querySelectorAll('button, a, span, div');
                for (var j = 0; j < all.length && j < 200; j++) {
                    var text = (all[j].innerText || all[j].textContent || '').trim();
                    if ((text === '赞' || text === '点赞') && isVisible(all[j])) {
                        if (doClick(all[j])) { clicked = all[j]; msg = '策略2: 文本含赞'; break; }
                    }
                }
            }

            // 策略3: class 含 like/heart
            if (!clicked) {
                var cls = document.querySelectorAll('[class*="like"], [class*="Like"], [class*="heart"], [class*="Heart"]');
                for (var k = 0; k < cls.length && k < 30; k++) {
                    if (isVisible(cls[k])) { if (doClick(cls[k])) { clicked = cls[k]; msg = '策略3: 类名含like/heart'; break; } }
                }
            }

            if (clicked) { return JSON.stringify({success:true, message:msg}); }
            return JSON.stringify({success:false, message:'未找到点赞元素'});
        } catch(e) {
            return JSON.stringify({success:false, message:'JS异常: ' + e.message});
        }})();
        """
    }

    private static func douyinLikeScript() -> String {
        return """
        (function(){try{
            var clicked = null;
            function isVisible(el) {
                try { var r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.top < window.innerHeight && r.bottom > 0; }
                catch(e) { return true; }
            }
            function doClick(el) {
                try { if (typeof el.click === 'function') { el.click(); return true; } } catch(e1) {}
                try { var ev = document.createEvent('MouseEvents'); ev.initMouseEvent('click', true, true, window, 0, 0, 0, 0, 0, false, false, false, false, 0, null); el.dispatchEvent(ev); return true; } catch(e2) {}
                return false;
            }
            var c1 = document.querySelectorAll('[class*="like"], [class*="heart"], [class*="Like"], [class*="Heart"]');
            for (var i = 0; i < c1.length && i < 30; i++) { if (isVisible(c1[i]) && doClick(c1[i])) { clicked = c1[i]; break; } }
            if (!clicked) { var all = document.querySelectorAll('button, a, span'); for (var j = 0; j < all.length && j < 200; j++) { var t = (all[j].innerText||'').trim(); if (t==='赞'&&isVisible(all[j])&&doClick(all[j])){ clicked=all[j]; break; }}}
            if (clicked) { return JSON.stringify({success:true, message:'已点赞'}); }
            return JSON.stringify({success:false, message:'未找到点赞元素'});
        } catch(e) { return JSON.stringify({success:false, message:'JS异常'}); }})();
        """
    }

    // ============================================================
    // MARK: - 评论
    // ============================================================

    static func commentScript(for platform: String, text: String) -> String {
        let escaped = text
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "'", with: "\\'")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: "")

        return """
        (function(){try{
            var commentText = '\(escaped)';
            var input = null;
            var tas = document.querySelectorAll('textarea');
            for (var i = 0; i < tas.length; i++) { input = tas[i]; break; }
            if (!input) { return JSON.stringify({success:false, message:'未找到评论输入框'}); }
            input.focus(); input.value = commentText;
            try { var e1 = document.createEvent('Event'); e1.initEvent('input', true, true); input.dispatchEvent(e1); } catch(ex) {}
            var btns = document.querySelectorAll('button, a, div, span');
            for (var k = 0; k < btns.length; k++) { var t = (btns[k].innerText||'').trim(); if (t==='发送'||t==='评论') { try { btns[k].click(); } catch(e2) {} return JSON.stringify({success:true, message:'已发送评论'}); }}
            return JSON.stringify({success:false, message:'未找到发送按钮'});
        } catch(e) { return JSON.stringify({success:false, message:'JS异常'}); }})();
        """
    }

    // ============================================================
    // MARK: - 关注
    // ============================================================

    static func followScript(for platform: String) -> String {
        return """
        (function(){try{
            var clicked = null;
            function isVisible(el) { try { var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; } catch(e){return true;} }
            function doClick(el) { try { if(typeof el.click==='function'){el.click();return true;} }catch(e1){} try{var ev=document.createEvent('MouseEvents');ev.initMouseEvent('click',true,true,window,0,0,0,0,0,false,false,false,false,0,null);el.dispatchEvent(ev);return true;}catch(e2){} return false; }
            var all = document.querySelectorAll('button,a,span,div');
            for(var i=0;i<all.length&&i<200;i++){var t=(all[i].innerText||all[i].textContent||'').trim();if((t==='关注'||t==='+ 关注'||t==='Follow')&&isVisible(all[i])){if(doClick(all[i])){clicked=all[i];break;}}}
            if(clicked){return JSON.stringify({success:true,message:'已关注'});}
            return JSON.stringify({success:false,message:'未找到关注按钮'});
        }catch(e){return JSON.stringify({success:false,message:'JS异常'});}})();
        """
    }

    // ============================================================
    // MARK: - 点击第一篇帖子
    // ============================================================

    static func clickFirstPostScript(for platform: String) -> String {
        return """
        (function(){try{
            var clicked=null;
            function isVisible(el){try{var r=el.getBoundingClientRect();return r.width>50&&r.height>50&&r.top<window.innerHeight&&r.bottom>0;}catch(e){return true;}}
            function doClick(el){try{if(typeof el.click==='function'){el.click();return true;}}catch(e1){}try{var ev=document.createEvent('MouseEvents');ev.initMouseEvent('click',true,true,window,0,0,0,0,0,false,false,false,false,0,null);el.dispatchEvent(ev);return true;}catch(e2){}return false;}
            var links=document.querySelectorAll('a[href]');
            for(var i=0;i<links.length;i++){var h=links[i].getAttribute('href')||'';if(h.indexOf('/explore/')>=0||h.indexOf('/note/')>=0||h.indexOf('/discovery/')>=0){if(isVisible(links[i])&&doClick(links[i])){clicked=links[i];break;}}}
            if(!clicked){for(var j=0;j<links.length;j++){if(isVisible(links[j])&&doClick(links[j])){clicked=links[j];break;}}}
            if(clicked){return JSON.stringify({success:true,message:'已点击帖子'});}
            return JSON.stringify({success:false,message:'未找到可点击的帖子'});
        }catch(e){return JSON.stringify({success:false,message:'JS异常'});}})();
        """
    }
}

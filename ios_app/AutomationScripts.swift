//
//  AutomationScripts.swift
//  各平台的自动化脚本 - 在 WKWebView 中通过 JS 注入执行
//

import Foundation

enum AutomationScripts {
    // ========== 点赞 ==========
    static func likeScript(for platform: String) -> String {
        switch platform {
        case "xiaohongshu":
            return xiaohongshuLikeScript()
        default:
            return xiaohongshuLikeScript()
        }
    }

    // ========== 评论 ==========
    static func commentScript(for platform: String, text: String) -> String {
        let escapedText = text.replacingOccurrences(of: "'", with: "\\'")
                              .replacingOccurrences(of: "\"", with: "\\\"")
                              .replacingOccurrences(of: "\n", with: " ")

        switch platform {
        case "xiaohongshu":
            return xiaohongshuCommentScript(text: escapedText)
        default:
            return xiaohongshuCommentScript(text: escapedText)
        }
    }

    // ========== 关注 ==========
    static func followScript(for platform: String) -> String {
        switch platform {
        case "xiaohongshu":
            return xiaohongshuFollowScript()
        default:
            return xiaohongshuFollowScript()
        }
    }

    // ========== 私信 ==========
    static func messageScript(for platform: String, text: String) -> String {
        let escapedText = text.replacingOccurrences(of: "'", with: "\\'")
                              .replacingOccurrences(of: "\"", with: "\\\"")
                              .replacingOccurrences(of: "\n", with: " ")

        switch platform {
        case "xiaohongshu":
            return xiaohongshuMessageScript(text: escapedText)
        default:
            return xiaohongshuMessageScript(text: escapedText)
        }
    }

    // ========== 小红书: 点赞 ==========
    private static func xiaohongshuLikeScript() -> String {
        return """
        (function() {
            // 策略1: 找包含 "点赞" 的按钮或图标
            var btn = null;
            var candidates = document.querySelectorAll('button, [class*="like"], [class*="Like"], [data-type="like"], [aria-label*="赞"], [class*="icon"]');
            for (var i = 0; i < candidates.length; i++) {
                var el = candidates[i];
                var txt = (el.textContent || el.getAttribute('aria-label') || el.className || '').toLowerCase();
                if (txt.indexOf('like') >= 0 || txt.indexOf('赞') >= 0) {
                    var rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0 && rect.top > 0 && rect.top < window.innerHeight) {
                        btn = el;
                        break;
                    }
                }
            }

            // 策略2: 找 SVG 图标中的心形
            if (!btn) {
                var svgs = document.querySelectorAll('svg');
                for (var j = 0; j < svgs.length; j++) {
                    var svg = svgs[j];
                    var parent = svg.closest('button, a, span, div');
                    if (parent) {
                        var rect = parent.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && rect.top > 0 && rect.top < window.innerHeight) {
                            // 判断是否在页面中下部分（通常互动按钮在那里）
                            if (rect.top > window.innerHeight * 0.4) {
                                btn = parent;
                                break;
                            }
                        }
                    }
                }
            }

            if (btn) {
                btn.click();
                return { success: true, message: '已点击点赞' };
            }
            return { success: false, message: '未找到点赞按钮' };
        })();
        """
    }

    // ========== 小红书: 评论 ==========
    private static func xiaohongshuCommentScript(text: String) -> String {
        return """
        (function() {
            // 1. 找评论输入框
            var inputs = document.querySelectorAll('textarea, input[type="text"], [contenteditable]');
            var commentInput = null;

            for (var i = 0; i < inputs.length; i++) {
                var input = inputs[i];
                var ph = (input.getAttribute('placeholder') || input.getAttribute('aria-label') || '').toLowerCase();
                if (ph.indexOf('评论') >= 0 || ph.indexOf('comment') >= 0 || ph.indexOf('说点') >= 0) {
                    commentInput = input;
                    break;
                }
            }

            // 如果没找到特定输入框，尝试页面中的第一个 textarea
            if (!commentInput) {
                commentInput = document.querySelector('textarea');
            }

            if (!commentInput) {
                return { success: false, message: '未找到评论输入框' };
            }

            // 2. 输入内容
            commentInput.focus();
            commentInput.value = '\(text)';
            commentInput.dispatchEvent(new Event('input', { bubbles: true }));
            commentInput.dispatchEvent(new Event('change', { bubbles: true }));

            // 3. 触发发送按钮
            var sendBtn = null;
            var btns = document.querySelectorAll('button');
            for (var j = 0; j < btns.length; j++) {
                var b = btns[j];
                var bt = (b.textContent || '').toLowerCase().trim();
                if (bt === '发送' || bt === '发布' || bt === 'send' || b.getAttribute('aria-label') === '发送') {
                    sendBtn = b;
                    break;
                }
            }

            if (sendBtn) {
                sendBtn.click();
                return { success: true, message: '已发布评论' };
            }
            return { success: true, message: '已输入内容（未找到发送按钮或自动发送）' };
        })();
        """
    }

    // ========== 小红书: 关注 ==========
    private static func xiaohongshuFollowScript() -> String {
        return """
        (function() {
            // 找关注按钮
            var candidates = document.querySelectorAll('button, a, span');
            var followBtn = null;

            for (var i = 0; i < candidates.length; i++) {
                var el = candidates[i];
                var txt = (el.textContent || '').trim();
                if (txt === '关注' || txt === '＋关注' || txt === '+ 关注' || txt.toLowerCase() === 'follow') {
                    var rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {
                        followBtn = el;
                        break;
                    }
                }
            }

            if (followBtn) {
                followBtn.click();
                return { success: true, message: '已点击关注' };
            }
            return { success: false, message: '未找到关注按钮（可能已关注）' };
        })();
        """
    }

    // ========== 小红书: 私信 ==========
    private static func xiaohongshuMessageScript(text: String) -> String {
        return """
        (function() {
            // 1. 找私信/聊天按钮
            var msgBtn = null;
            var candidates = document.querySelectorAll('button, a');
            for (var i = 0; i < candidates.length; i++) {
                var el = candidates[i];
                var txt = (el.textContent || '').trim();
                if (txt.indexOf('私信') >= 0 || txt.toLowerCase().indexOf('message') >= 0 || txt.toLowerCase().indexOf('chat') >= 0) {
                    msgBtn = el;
                    break;
                }
            }

            if (msgBtn) {
                msgBtn.click();
                setTimeout(function() {
                    // 2. 找消息输入框
                    var input = document.querySelector('textarea, input[type="text"]');
                    if (input) {
                        input.focus();
                        input.value = '\(text)';
                        input.dispatchEvent(new Event('input', { bubbles: true }));

                        // 3. 发送
                        var sendBtns = document.querySelectorAll('button');
                        for (var j = 0; j < sendBtns.length; j++) {
                            if ((sendBtns[j].textContent || '').trim() === '发送') {
                                sendBtns[j].click();
                                break;
                            }
                        }
                    }
                }, 1500);
                return { success: true, message: '已发送私信' };
            }
            return { success: false, message: '未找到私信入口' };
        })();
        """
    }
}

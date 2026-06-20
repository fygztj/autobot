//
//  TaskConfig.swift
//  双模式任务配置模型
//

import Foundation

// MARK: - 任务模式

enum TaskMode: String, Codable {
    case nurture = "nurture"    // 养号模式
    case work = "work"          // 工作模式
}

// MARK: - 时间范围

struct TimeRange: Codable {
    var min: Int    // 秒
    var max: Int    // 秒

    func random() -> Int {
        guard max > min else { return min }
        return Int.random(in: min...max)
    }
}

// MARK: - 概率配置

struct ProbabilityConfig: Codable {
    /// 点赞概率 (0.0 ~ 1.0)
    var likeRate: Double = 0.6
    /// 评论笔记概率
    var commentRate: Double = 0.25
    /// 回复他人评论概率
    var replyRate: Double = 0.15
    /// 收藏概率
    var collectRate: Double = 0.1
    /// 关注作者概率
    var followRate: Double = 0.03

    /// 判断是否应该执行某个操作
    func should(_ action: Action) -> Bool {
        switch action {
        case .like: return Double.random(in: 0...1) < likeRate
        case .comment: return Double.random(in: 0...1) < commentRate
        case .reply: return Double.random(in: 0...1) < replyRate
        case .collect: return Double.random(in: 0...1) < collectRate
        case .follow: return Double.random(in: 0...1) < followRate
        }
    }

    enum Action { case like, comment, reply, collect, follow }
}

// MARK: - 内容线配置（主线/次线）

struct ContentLineConfig: Codable {
    /// 线路名称
    var name: String
    /// 关注的关键词列表（用于内容匹配）
    var keywords: [String] = []
    /// 主题标签
    var topics: [String] = []
    /// 该线路的概率覆盖（覆盖全局默认值）
    var probabilities: ProbabilityConfig?
    /// @提及的账号列表
    var mentionAccounts: [String] = []
    /// 在评论中@账号的概率（仅主线有效）
    var mentionProbability: Double = 0.0
    /// 默认回复模板（无关键词匹配时使用）
    var defaultReplies: [String] = []
    /// 关键词 → 回复模板映射
    var keywordReplies: [String: [String]] = [:]
    /// 每轮该线路执行的笔记数量
    var notesPerRound: Int = 3
}

// MARK: - 养号模式配置

struct NurtureModeConfig: Codable {
    /// 搜索关键词列表
    var searchKeywords: [String] = []
    /// 是否使用搜索模式（false 则浏览推荐页）
    var useSearch: Bool = true
    /// 点赞概率 (0.0 ~ 1.0)
    var likeRate: Double = 0.7
    /// 总执行时间范围(秒) — 在此时间内随机结束，不按篇数计算
    var durationRange: TimeRange = TimeRange(min: 120, max: 300)
    /// 每篇笔记浏览时间范围(秒)
    var viewTimeRange: TimeRange = TimeRange(min: 3, max: 8)
    /// 笔记间休息时间(秒)
    var restRange: TimeRange = TimeRange(min: 2, max: 5)
    /// 关键词间切换的额外休息时间(秒)
    var keywordRestRange: TimeRange = TimeRange(min: 5, max: 15)
}

// MARK: - 工作模式配置

struct WorkModeConfig: Codable {
    /// 主线配置
    var mainLine: ContentLineConfig = ContentLineConfig(
        name: "主线",
        keywords: [],
        mentionAccounts: [],
        mentionProbability: 0.3,
        defaultReplies: ["学到了！感谢分享", "太有用了，已收藏", "写得很好，支持一下"],
        keywordReplies: [:],
        notesPerRound: 3
    )

    /// 次线配置
    var secondaryLine: ContentLineConfig = ContentLineConfig(
        name: "次线",
        keywords: [],
        defaultReplies: ["不错哦", "挺好的", "赞一个"],
        keywordReplies: [:],
        notesPerRound: 2
    )

    /// 交替模式
    var alternation: AlternationConfig = AlternationConfig()

    /// 全局默认概率（被各线路的 probabilities 覆盖）
    var defaultProbabilities: ProbabilityConfig = ProbabilityConfig(
        likeRate: 0.65,
        commentRate: 0.3,
        replyRate: 0.2,
        collectRate: 0.08,
        followRate: 0.03
    )

    /// 每篇笔记浏览时间(秒)
    var viewTimeRange: TimeRange = TimeRange(min: 5, max: 15)

    /// 笔记间休息时间(秒)
    var restBetweenNotes: TimeRange = TimeRange(min: 3, max: 8)

    /// 主线/次线切换间的休息时间(秒)
    var restBetweenLines: TimeRange = TimeRange(min: 15, max: 40)

    /// 总执行时间限制(分钟)，0 表示不限制
    var totalDurationMinutes: Int = 0

    /// 是否浏览评论区
    var browseComments: Bool = true

    /// 评论区滚动次数
    var commentScrollCount: Int = 2
}

// MARK: - 交替配置

struct AlternationConfig: Codable {
    /// 连续执行主线多少轮
    var mainRounds: Int = 3
    /// 连续执行次线多少轮
    var secondaryRounds: Int = 2
    /// 起始线路: "main" 或 "secondary"
    var startWith: String = "main"

    /// 生成交替序列
    func generateSequence(count: Int) -> [String] {
        var sequence: [String] = []
        var current = startWith
        for _ in 0..<count {
            if current == "main" {
                for _ in 0..<mainRounds { sequence.append("main") }
                current = "secondary"
            } else {
                for _ in 0..<secondaryRounds { sequence.append("secondary") }
                current = "main"
            }
        }
        return sequence
    }
}

// MARK: - 完整任务配置

struct TaskConfig: Codable {
    var mode: TaskMode = .work
    var platform: String = "xiaohongshu"

    // 养号模式
    var nurture: NurtureModeConfig = NurtureModeConfig()

    // 工作模式
    var work: WorkModeConfig = WorkModeConfig()

    // ===== 辅助方法 =====

    /// 获取当前线路的有效概率配置
    func effectiveProbabilities(forLine line: String?) -> ProbabilityConfig {
        switch mode {
        case .nurture:
            return ProbabilityConfig(likeRate: nurture.likeRate, commentRate: 0, replyRate: 0, collectRate: 0, followRate: 0)
        case .work:
            if line == "main", let mainProb = work.mainLine.probabilities {
                return mergeProbabilities(base: work.defaultProbabilities, override: mainProb)
            } else if line == "secondary", let secProb = work.secondaryLine.probabilities {
                return mergeProbabilities(base: work.defaultProbabilities, override: secProb)
            } else {
                return work.defaultProbabilities
            }
        }
    }

    /// 获取当前线路的配置
    func currentLineConfig(forLine line: String) -> ContentLineConfig? {
        guard mode == .work else { return nil }
        return line == "main" ? work.mainLine : work.secondaryLine
    }

    private func mergeProbabilities(base: ProbabilityConfig, override: ProbabilityConfig) -> ProbabilityConfig {
        return ProbabilityConfig(
            likeRate: override.likeRate > 0 ? override.likeRate : base.likeRate,
            commentRate: override.commentRate > 0 ? override.commentRate : base.commentRate,
            replyRate: override.replyRate > 0 ? override.replyRate : base.replyRate,
            collectRate: override.collectRate > 0 ? override.collectRate : base.collectRate,
            followRate: override.followRate > 0 ? override.followRate : base.followRate
        )
    }

    /// 根据内容和当前线路生成智能回复
    func generateSmartReply(contentTitle: String, contentTags: [String], line: String?) -> String {
        let config = mode == .work ? (line == "main" ? work.mainLine : work.secondaryLine) : nil
        let defaults = config?.defaultReplies ?? ["很棒！支持一下"]

        // 1. 尝试关键词精确匹配
        if let kwReplies = config?.keywordReplies {
            for (keyword, replies) in kwReplies {
                if contentTitle.contains(keyword) || contentTags.contains(where: { $0.contains(keyword) }) {
                    return replies.randomElement() ?? defaults.randomElement()!
                }
            }
        }

        // 2. 尝试线路关键词模糊匹配
        if let keywords = config?.keywords {
            for keyword in keywords where !keyword.isEmpty {
                if contentTitle.lowercased().contains(keyword.lowercased()) ||
                   contentTags.contains(where: { $0.lowercased().contains(keyword.lowercased()) }) {
                    // 找到相关内容，返回带感情的默认回复
                    let emotional = ["这个内容很有价值！", "说得对，学习了", "深有同感", "太真实了", "这就是我想要的"]
                    return emotional.randomElement() ?? defaults.randomElement()!
                }
            }
        }

        // 3. 使用默认回复
        return defaults.randomElement()!
    }

    /// 决定是否在评论中@账号
    func shouldMention(line: String?) -> (should: Bool, account: String) {
        guard mode == .work, line == "main" else { return (false, "") }
        let config = work.mainLine
        guard !config.mentionAccounts.isEmpty else { return (false, "") }
        let should = Double.random(in: 0...1) < config.mentionProbability
        let account = config.mentionAccounts.randomElement() ?? ""
        return (should, account)
    }

    /// 序列化为字典（用于发送到 App）
    func toDict() -> [String: Any] {
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(self),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return [:]
        }
        return json
    }

    /// 从字典初始化
    static func fromDict(_ dict: [String: Any]) -> TaskConfig? {
        print("[TaskConfig] fromDict called with dict: \(dict)")
        
        guard let data = try? JSONSerialization.data(withJSONObject: dict) else {
            print("[TaskConfig] Failed to serialize dict to data")
            return nil
        }
        
        do {
            let config = try JSONDecoder().decode(TaskConfig.self, from: data)
            print("[TaskConfig] Decoded successfully: mode=\(config.mode.rawValue), platform=\(config.platform)")
            return config
        } catch {
            print("[TaskConfig] Failed to decode: \(error.localizedDescription)")
            print("[TaskConfig] Error details: \(error)")
            return nil
        }
    }
}

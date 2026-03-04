# EverMemOS Skills - Quick Start Guide

从零到运行，只需 3 步 + 5 分钟！

## 📋 前提条件

只需要：
- ✅ Claude Code 已安装
- ✅ Python 3.8+ 已安装
- ✅ 能连接互联网

**就这么简单！** 不需要了解 MongoDB、Elasticsearch、Milvus 等。

---

## 🚀 Step 1: 安装 Skills（30 秒）

```bash
# 克隆 EverMemOS 项目（如果还没有）
git clone https://github.com/your-org/EverMemOS.git
cd EverMemOS

# 安装所有 skills 到 Claude Code
cp -r claude-skills/evermemos* ~/.claude/skills/

# 验证
ls ~/.claude/skills/
```

**应该看到：**
```
evermemos/
evermemos-setup/
evermemos-start/
evermemos-doctor/
```

✅ Skills 安装完成！

---

## 🎯 Step 2: 自动安装 EverMemOS（2 分钟）

打开 Claude Code，输入：

```
你: 帮我安装 EverMemOS

Claude: 好的！我来帮你快速设置 EverMemOS。

由于你是新手，我推荐 lite 模式 - 最简单，无需额外软件。

[自动执行: /evermemos-setup lite]

============================================================
                 EverMemOS Setup Wizard
============================================================

ℹ️  Detecting Setup Mode

ℹ️  OS: Linux 5.15.0
ℹ️  Recommended mode: lite (Minimal dependencies)

============================================================
                Installing Dependencies
============================================================

ℹ️  Checking Python version...
✅ Python 3.11.5

ℹ️  Checking uv package manager...
⚠️  uv not found

安装 uv 吗? (y/n):

[输入 y]

✅ uv installed successfully
✅ Dependencies installed

============================================================
              Setting Up Lite Mode
============================================================

ℹ️  Creating configuration...
✅ Created .env.lite
✅ Created data directory

============================================================
             Verifying Installation
============================================================

✅ Project directory: OK
✅ Source code: OK
✅ Configuration: OK
✅ Data directory: OK

============================================================
             Setup Complete! 🎉
============================================================

✅ EverMemOS is ready to use

ℹ️  Next steps:
  1. Start the server: /evermemos-start
  2. Try it out!

安装完成！现在启动服务...
```

✅ EverMemOS 已安装！

---

## ▶️ Step 3: 启动服务（30 秒）

```
你: 启动 EverMemOS

Claude: 好的，我来启动服务。

[自动执行: /evermemos-start]

🚀 Starting EverMemOS in background...
✅ EverMemOS started successfully (PID: 12345)
📝 Logs: logs/evermemos_<timestamp>.log
🌐 API: http://localhost:1995

服务已启动并运行中！
```

✅ 服务运行中！

---

## 🎉 完成！现在试试

### 存储信息

```
你: 记住：项目 Alpha 的目标是提升用户体验

Claude: [自动执行: /evermemos store "项目 Alpha 的目标是提升用户体验" user]

✅ 已记住！我会记住这个信息。
```

### 搜索记忆

```
你: 项目 Alpha 的目标是什么？

Claude: [自动执行: /evermemos search "项目 Alpha 目标" hybrid 5]

📁 找到相关记忆：

⏰ [2026-02-05 14:30:15]
💬 项目 Alpha 的目标是提升用户体验

根据我们之前的对话，项目 Alpha 的主要目标是提升用户体验。
```

### 查看最近对话

```
你: 我们今天讨论了什么？

Claude: [自动执行: /evermemos recent 10]

📜 今天的对话摘要：

1. [14:25] 安装 EverMemOS
2. [14:28] 启动服务
3. [14:30] 记录项目 Alpha 的目标
4. [14:32] 查询项目 Alpha 信息

我们主要完成了 EverMemOS 的安装和初始设置，
并开始使用记忆功能记录项目信息。
```

---

## 📊 对比传统方式

| 步骤 | 传统方式 | Skills 方式 |
|------|----------|-------------|
| **学习文档** | 30 分钟 | 0 分钟（对话式） |
| **安装依赖** | 15 分钟 | 2 分钟（自动） |
| **配置** | 10 分钟 | 0 分钟（自动） |
| **启动服务** | 5 分钟 | 30 秒 |
| **学习 API** | 20 分钟 | 0 分钟（自然语言） |
| **总计** | **80 分钟** | **5 分钟** |

---

## 🛠️ 常用命令

### 服务管理

```bash
# 启动
/evermemos-start

# 停止
/evermemos-start stop

# 重启
/evermemos-start restart

# 查看状态
/evermemos-start status

# 查看日志
/evermemos-start logs
```

### 记忆操作

```bash
# 搜索
/evermemos search "查询内容"

# 存储
/evermemos store "要记住的内容" user

# 最近历史
/evermemos recent 20
```

### 诊断和修复

```bash
# 健康检查
/evermemos-doctor

# 重新配置
/evermemos-setup
```

---

## 🎯 使用场景示例

### 场景 1: 项目知识管理

```
你: 记住：项目使用 PostgreSQL 数据库，端口 5432

Claude: ✅ 已记住

[第二天]

你: 数据库用的什么？端口是多少？

Claude: [搜索记忆]
项目使用 PostgreSQL 数据库，端口 5432。
```

### 场景 2: Bug 追踪

```
你: 记住：发现一个 bug - 用户登录后 token 会在 15 分钟后过期，
但刷新逻辑是 20 分钟触发的

Claude: ✅ 已记住这个 bug

[后来]

你: 那个 token 的 bug 是什么来着？

Claude: [搜索]
用户登录后 token 会在 15 分钟后过期，
但刷新逻辑是 20 分钟触发的。
```

### 场景 3: 代码审查

```
你: 记住：代码审查发现安全问题 - SQL 查询没有使用参数化，
存在 SQL 注入风险

Claude: ✅ 已记住

[审查另一个 PR 时]

你: 这段代码有没有类似的安全问题？

Claude: [读取代码 + 搜索过往记忆]
是的！这里也有 SQL 注入风险。

之前我们发现过类似问题：SQL 查询没有使用参数化。
这里应该改用参数化查询。
```

---

## 🐛 遇到问题？

### 问题：安装失败

```bash
# 运行诊断
/evermemos-doctor

# 会自动检测并提示修复方案
```

### 问题：服务无法启动

```bash
# 检查状态
/evermemos-start status

# 查看日志
/evermemos-start logs

# 运行诊断
/evermemos-doctor
```

### 问题：不知道怎么用

```bash
# 直接问 Claude
"EverMemOS 怎么用？"

# Claude 会提供引导和示例
```

---

## 📚 深入学习

### 详细文档

1. **核心功能**: [claude-skills/evermemos/SKILL.md](evermemos/SKILL.md)
2. **使用示例**: [claude-skills/evermemos/examples.md](evermemos/examples.md)
3. **安装指南**: [claude-skills/evermemos-setup/SKILL.md](evermemos-setup/SKILL.md)
4. **服务管理**: [claude-skills/evermemos-start/SKILL.md](evermemos-start/SKILL.md)
5. **故障诊断**: [claude-skills/evermemos-doctor/SKILL.md](evermemos-doctor/SKILL.md)

### 设计理念

- **零门槛理念**: [EVERMEMOS_SIMPLIFIED_ONBOARDING.md](../EVERMEMOS_SIMPLIFIED_ONBOARDING.md)
- **部署指南**: [CLAUDE_SKILLS_DEPLOYMENT.md](../CLAUDE_SKILLS_DEPLOYMENT.md)

---

## ✨ 高级特性

### 多模式支持

```bash
# Lite 模式（默认 - 最简单）
/evermemos-setup lite

# Standard 模式（Docker）
/evermemos-setup standard

# Full 模式（生产环境）
/evermemos-setup full
```

### 自定义配置

```bash
# 编辑配置文件
vi .env.lite

# 重启服务应用配置
/evermemos-start restart
```

### 查看详细日志

```bash
# 实时查看
tail -f $(ls -t logs/evermemos_*.log | head -1)

# 或使用 skill
/evermemos-start logs
```

---

## 🎯 总结

**你学会了：**

1. ✅ 3 步安装 EverMemOS（5 分钟）
2. ✅ 使用自然语言存储和搜索记忆
3. ✅ 管理服务（启动/停止/状态）
4. ✅ 诊断和修复问题

**不需要学习：**

- ❌ 命令行复杂操作
- ❌ 配置文件语法
- ❌ API 调用方式
- ❌ 进程管理
- ❌ 日志分析

**下一步：**

- 🚀 开始在实际工作中使用
- 📖 阅读详细文档了解更多
- 💡 探索高级功能
- 🤝 分享给团队成员

---

## 🆘 获取帮助

**有问题？** 直接问 Claude：

```
"EverMemOS 怎么用？"
"如何存储信息？"
"我遇到了错误"
"服务无法启动"
```

Claude 会自动：
- 🔍 诊断问题
- 💡 提供解决方案
- 🛠️ 必要时自动修复

---

**开始使用吧！** 🎉

如果这个快速开始指南对你有帮助，欢迎分享给其他人！

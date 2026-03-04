# EverMemOS Skill 安装指南

## 快速安装（推荐）

将 skill 复制到 Claude Code 的个人目录：

```bash
# 从 EverMemOS 项目目录执行
cp -r claude-skills/evermemos ~/.claude/skills/
```

安装完成！现在你可以在**任何项目**中使用 EverMemOS 的记忆功能。

---

## 验证安装

```bash
# 检查文件是否存在
ls -la ~/.claude/skills/evermemos/

# 测试 Python 客户端
python3 ~/.claude/skills/evermemos/scripts/evermemos_client.py

# 测试搜索功能（需要 EverMemOS 后端运行）
python3 ~/.claude/skills/evermemos/scripts/evermemos_client.py search "test" hybrid 5
```

---

## 配置（可选）

默认配置已可用。如需自定义，在 `~/.bashrc` 或 `~/.zshrc` 中添加：

```bash
export EVERMEMOS_BASE_URL="http://localhost:1995"
export EVERMEMOS_USER_ID="your_username"
# EVERMEMOS_GROUP_ID 无需手动设置，自动从当前工作目录派生（按项目隔离）
```

然后重启终端或执行 `source ~/.bashrc`

---

## 前置条件

1. **Python 3.7+** 已安装
2. **EverMemOS 后端** 正在运行：
   ```bash
   cd /path/to/EverMemOS
   uv run python src/run.py
   ```

---

## 使用方法

### 自动触发（推荐）

Claude Code 会自动识别以下场景并使用 EverMemOS：

```
# 查询过去对话
你: "我们之前讨论的 ES bug 是什么？"
Claude: [自动搜索记忆并回答]

# 存储信息
你: "记住：这个项目使用 hybrid 检索"
Claude: [自动存储到 EverMemOS]

# 获取历史
你: "我们今天做了什么？"
Claude: [自动获取最近记忆]
```

### 手动调用

```bash
# 搜索记忆
/evermemos search "ES sync bug" hybrid 5

# 存储信息
/evermemos store "项目使用 PostgreSQL 15" user

# 获取最近历史
/evermemos recent 20
```

---

## 文档

- **SKILL.md**: 完整的 skill 定义和使用说明
- **examples.md**: 15+ 个真实场景示例
- **CLAUDE_CODE_SKILL_GUIDE.md**: 详细集成指南（项目根目录）

---

## 更新 Skill

当 skill 有更新时，重新执行安装命令：

```bash
cp -r claude-skills/evermemos ~/.claude/skills/
```

---

## 卸载

```bash
rm -rf ~/.claude/skills/evermemos
```

---

## 文件结构

```
claude-skills/evermemos/          # 可分发的 skill 源文件
├── INSTALL.md                    # 本文件
├── SKILL.md                      # Skill 定义
├── examples.md                   # 使用示例
└── scripts/
    └── evermemos_client.py       # Python API 客户端

安装后:
~/.claude/skills/evermemos/       # Claude Code 读取位置
├── SKILL.md
├── examples.md
└── scripts/
    └── evermemos_client.py
```

---

## 工作原理

```
用户输入
    ↓
Claude Code（检测需要记忆功能）
    ↓
Skill: /evermemos (SKILL.md)
    ↓
Python 客户端 (evermemos_client.py)
    ↓
EverMemOS API (http://localhost:1995)
    ↓
存储后端 (MongoDB/ES/Milvus)
```

---

## 故障排除

### Skill 没有触发

1. 检查安装：`ls -la ~/.claude/skills/evermemos/SKILL.md`
2. 重启 Claude Code
3. 手动调用测试：`/evermemos search "test"`

### 连接错误

确认 EverMemOS 后端运行中：
```bash
curl http://localhost:1995
```

### 权限错误

```bash
chmod +x ~/.claude/skills/evermemos/scripts/evermemos_client.py
```

---

## 支持

- 详细文档: `CLAUDE_CODE_SKILL_GUIDE.md`
- 使用示例: `examples.md`
- Skill 定义: `SKILL.md`

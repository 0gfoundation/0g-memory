# Claude Skills for EverMemOS

## 安装

```bash
cp -r claude-skills/evermemos ~/.claude/skills/
```

## 包含的 Skill

### evermemos - 记忆功能

搜索、存储、回忆对话历史。Claude Code 会自动触发，也可手动调用：

```
/evermemos search <query>
/evermemos store <content>
/evermemos recent [limit]
```

## 配置（可选）

```bash
export API_BASE_URL="http://localhost:1995"
export MEMORY_USER_ID="your_username"
```

## 卸载

```bash
rm -rf ~/.claude/skills/evermemos
```

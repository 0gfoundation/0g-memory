---
name: evermemos-doctor
description: Manage and diagnose EverMemOS. Use for installation (install.sh), starting/stopping/restarting services (start_service.sh / stop_service.sh), checking service status, viewing logs, and health diagnostics. Trigger on any request to install, set up, start, stop, restart, check status, or troubleshoot EverMemOS.
argument-hint: ""
disable-model-invocation: false
allowed-tools: Bash(python3 *), Bash(bash *), Bash(./install.sh*), Bash(./start_service.sh*), Bash(./stop_service.sh*), Bash(./uninstall.sh*), Read
---

# EverMemOS Doctor - Health Check & Diagnostics

Automatically diagnose and troubleshoot EverMemOS issues. Like running `doctor` for your installation!

## Usage

```bash
/evermemos-doctor
```

## What It Does

Runs comprehensive health checks:

### 1. System Environment
- ✅ Python version (3.8+ required)
- ✅ Operating system compatibility
- ✅ Package manager (uv) availability

### 2. Project Structure
- ✅ Project directory exists
- ✅ Source code present
- ✅ Configuration files
- ✅ Data directory writable

### 3. Dependencies
- ✅ Python packages installed
- ✅ Required libraries available

### 4. Service Status
- ✅ Port availability (1995)
- ✅ Service running
- ✅ API accessible
- ✅ Log file analysis

### 5. System Resources
- ✅ Disk space available
- ✅ Memory available

## Automatic Usage

Claude will automatically run diagnostics when:

**User says:**
- "EverMemOS isn't working"
- "I'm getting an error"
- "Can you check if everything is OK?"
- "Help me debug this"
- "Something is broken"

**Claude responds:**
```
I'll run a health check to diagnose the issue.

[Runs: /evermemos-doctor]

Let me analyze the results and help fix any problems found.
```

## Example Output

```
============================================================
                 EverMemOS Health Check
============================================================

ℹ️  System Environment
ℹ️  OS: Linux 5.15.0
ℹ️  Architecture: x86_64

============================================================
                      Basic Checks
============================================================

✅ Python version (3.11.5)
✅ uv package manager
✅ Project directory
✅ Source code (src/)
✅ Configuration (pyproject.toml)
✅ Configuration file (.env.lite)
✅ Data directory
✅ Data directory (writable)

============================================================
                   Dependency Checks
============================================================

✅ Python dependencies

============================================================
                    Service Checks
============================================================

✅ Port 1995 (available)
❌ Service running
   Fix: Start with: /evermemos-start

============================================================
                    Resource Checks
============================================================

✅ Disk space (15.3 GB free)
✅ Memory (3.2 GB free)

============================================================
                        Summary
============================================================

✅ Passed: 11/12
❌ Failed: 1/12
⚠️  Warnings: 0

⚠️  Some checks failed. See fixes below.

============================================================
                    Suggested Fixes
============================================================

1. Service running
   Fix: Start with: /evermemos-start
```

## Usage Scenarios

### Scenario 1: After Fresh Install

```
User: I just installed EverMemOS, is it working?

Claude: Let me run a health check to verify everything is set up correctly.

[Executes: /evermemos-doctor]

Great news! All checks passed 🎉

The installation looks good. You're ready to:
1. Start the service: /evermemos-start
2. Try the memory features: /evermemos store "Test" user
```

---

### Scenario 2: Troubleshooting Startup Issues

```
User: EverMemOS won't start, I keep getting errors

Claude: I'll diagnose the problem for you.

[Executes: /evermemos-doctor]

============================================================
Found 2 issues:

1. Port 1995 (in use by another service)
   Fix: Change port in .env or stop conflicting service

2. Python dependencies
   Fix: Install with: uv sync
============================================================

I can see two problems:
1. Port 1995 is already in use by another program
2. Some Python packages are missing

Let me help you fix these:

First, let's install the dependencies:
[Executes: uv sync]

For the port conflict, would you like to:
a) Stop the other service using port 1995
b) Configure EverMemOS to use a different port
```

---

### Scenario 3: Performance Issues

```
User: EverMemOS is running but seems very slow

Claude: Let me check the system health and resource usage.

[Executes: /evermemos-doctor]

============================================================
⚠️  Warnings:
- Low memory: 0.4 GB free
- Found 15 errors in recent logs
============================================================

I found two issues affecting performance:

1. **Low Memory**: Only 400MB free
   - EverMemOS needs at least 500MB
   - Try closing other applications

2. **Errors in Logs**: 15 recent errors detected
   - Let me check the logs: /evermemos-start logs

[Checks logs and identifies specific issue]

The logs show MongoDB connection timeouts. Let me check
if MongoDB is running properly...
```

---

### Scenario 4: Unknown Issues

```
User: Something's not right but I don't know what

Claude: No problem! I'll run a comprehensive diagnostic.

[Executes: /evermemos-doctor]

============================================================
All checks passed! ✅
============================================================

Actually, everything looks healthy:
- ✅ Service is running
- ✅ API is accessible
- ✅ No errors in logs
- ✅ Good resource availability

Could you describe what behavior you're seeing? This will
help me investigate further.
```

---

## What Gets Checked

| Category | Checks |
|----------|--------|
| **System** | Python version, OS, architecture |
| **Project** | Directory structure, source code |
| **Config** | Environment files, settings |
| **Storage** | Data directory, permissions, disk space |
| **Dependencies** | Python packages, required libs |
| **Service** | Running status, PID, API access |
| **Network** | Port availability, connectivity |
| **Resources** | Disk space, memory, CPU |
| **Logs** | Recent errors, warnings |

## Common Issues & Fixes

### Issue: Python version too old
```
❌ Python version (need 3.8+, found 3.7)
Fix: Install Python 3.8 or higher
```

**Solution:**
```bash
# Ubuntu/Debian
sudo apt install python3.11

# macOS
brew install python@3.11
```

---

### Issue: uv not found
```
❌ uv package manager
Fix: Install with: curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Solution:** Claude can run the install command automatically.

---

### Issue: Configuration missing
```
❌ Configuration file
Fix: Run: /evermemos-setup to create configuration
```

**Solution:**
```bash
/evermemos-setup lite
```

---

### Issue: Port already in use
```
❌ Port 1995 (in use by another service)
Fix: Change port in .env or stop conflicting service
```

**Solution 1: Find and stop conflicting service**
```bash
lsof -i :1995
kill <PID>
```

**Solution 2: Change port**
Edit `.env` and set:
```
SERVER_PORT=1996
```

---

### Issue: Data directory not writable
```
❌ Data directory (writable)
Fix: Check permissions: chmod 755 data/
```

**Solution:**
```bash
chmod 755 data/
```

---

### Issue: Dependencies missing
```
❌ Python dependencies
Fix: Install with: uv sync
```

**Solution:**
```bash
cd /path/to/EverMemOS
uv sync
```

---

### Issue: Service not running
```
❌ Service running
Fix: Start with: /evermemos-start
```

**Solution:**
```bash
/evermemos-start
```

---

### Issue: Low disk space
```
❌ Disk space (0.3 GB free)
Fix: At least 500MB free space recommended
```

**Solution:** Free up disk space by removing unnecessary files.

---

## Integration with Other Skills

### After Setup
```
User: /evermemos-setup lite

Claude: Setup complete! Let me verify everything is working.

[Executes: /evermemos-doctor]

✅ All checks passed! Installation successful.
```

### Before Starting
```
User: /evermemos-start

Claude: Let me first check if everything is ready.

[Executes: /evermemos-doctor]

❌ Found issue: Dependencies missing

Installing dependencies first...
[Fixes issue]

Now starting the service...
```

### Periodic Health Checks
```
Claude: I notice you've been using EverMemOS for a while.
Would you like me to run a health check?

[User agrees]

[Executes: /evermemos-doctor]

Everything looks good! ✅
```

## When to Use

Use this skill when:

1. **After installation** - Verify setup
2. **Before starting** - Check prerequisites
3. **Troubleshooting** - Diagnose issues
4. **Periodic checks** - Ensure health
5. **Performance issues** - Check resources
6. **Unknown errors** - Find root cause

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | Some checks failed |

## Advanced Usage

### Run from command line
```bash
python3 ~/.claude/skills/evermemos-doctor/scripts/doctor.py
```

### Custom project directory
```bash
python3 scripts/doctor.py --project-dir /path/to/evermemos
```

### In scripts
```bash
if /evermemos-doctor; then
    echo "Health check passed"
else
    echo "Issues found"
fi
```

## Success Criteria

Doctor is satisfied when:

✅ All basic checks pass
✅ Dependencies installed
✅ Configuration valid
✅ Service can start
✅ No critical errors in logs
✅ Adequate resources available

## Limitations

- Cannot fix all issues automatically (yet)
- Some checks require service to be running
- Network issues may affect some checks
- Platform-specific checks may vary

## Future Enhancements

- Automatic fixing of common issues
- More detailed performance analysis
- Network connectivity tests
- Database connection validation
- Integration with monitoring tools

---

## Quick Reference

**Run diagnostic:**
```bash
/evermemos-doctor
```

**Common fixes:**
- Install deps: `uv sync`
- Start service: `/evermemos-start`
- Reconfigure: `/evermemos-setup`
- Check logs: `/evermemos-start logs`

**Get help:**
- Setup issues: `/evermemos-setup`
- Service issues: `/evermemos-start status`
- Configuration: `/evermemos-config`

---

The doctor is in! 🩺

---

## Service Management

In addition to diagnostics, this skill handles all EverMemOS lifecycle operations.

### Installation

**Trigger when user says:**
- "How do I install EverMemOS?"
- "Set up EverMemOS" / "Install EverMemOS for me"
- "Help me get EverMemOS running for the first time"

**Action:** Run the installer from the project root:
```bash
bash ./install.sh
```

After install, remind the user to:
1. Fill in API keys in `.env`
2. Download `zgs_kv` binary if needed
3. Run `./start_service.sh` to start services

---

### Start Services

**Trigger when user says:**
- "Start EverMemOS" / "启动 EverMemOS"
- "Run EverMemOS" / "Launch the service"

**Action (first-time start):**
```bash
bash ./start_service.sh
```

**Action (restart with existing stream ID):**
```bash
bash ./start_service.sh --restart
```

---

### Stop Services

**Trigger when user says:**
- "Stop EverMemOS" / "关闭 EverMemOS" / "Shut down the service"

**Action:**
```bash
bash ./stop_service.sh
```

---

### Restart Services

**Trigger when user says:**
- "Restart EverMemOS" / "重启 EverMemOS"
- "I just changed the config, apply it"

**Action:**
```bash
bash ./stop_service.sh && bash ./start_service.sh --restart
```

---

### Check Status

**Trigger when user says:**
- "Is EverMemOS running?" / "Check service status"
- "EverMemOS 跑起来了吗？"

**Action:**
```bash
python3 ~/.claude/skills/evermemos-start/scripts/service_manager.py status
```

---

### View Logs

**Trigger when user says:**
- "Show me the logs" / "EverMemOS logs"
- "What's in the log?"

**Action:**
```bash
python3 ~/.claude/skills/evermemos-start/scripts/service_manager.py logs
```

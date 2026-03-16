#!/usr/bin/env python3
"""
EverMemOS Service Manager

Start, stop, and manage EverMemOS services.
"""

import os
import sys
import subprocess
import signal
import time
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict


class ServiceManager:
    """Manages EverMemOS service lifecycle"""

    def __init__(self, project_dir: Optional[str] = None):
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        logs_dir = self.project_dir / "logs"
        self.pid_file = logs_dir / "evermemos.pid"
        # Point to the latest existing log file; overridden with a new timestamped
        # file when start() is called.
        existing_logs = sorted(logs_dir.glob("evermemos_*.log")) if logs_dir.exists() else []
        self.log_file = existing_logs[-1] if existing_logs else logs_dir / "evermemos.log"

    def is_running(self) -> bool:
        """Check if service is running"""
        if not self.pid_file.exists():
            return False

        try:
            pid = int(self.pid_file.read_text().strip())
            # Check if process exists
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, ValueError):
            # Process doesn't exist, clean up stale PID file
            self.pid_file.unlink(missing_ok=True)
            return False

    def get_status(self) -> Dict:
        """Get service status"""
        status = {
            "running": self.is_running(),
            "pid": None,
            "api_accessible": False,
            "mode": None
        }

        if status["running"]:
            status["pid"] = int(self.pid_file.read_text().strip())

            # Check API health endpoint
            try:
                req = urllib.request.Request("http://localhost:1995/health")
                with urllib.request.urlopen(req, timeout=2) as response:
                    status["api_accessible"] = response.status == 200
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
                pass

        # Check configuration file
        if (self.project_dir / ".env").exists():
            status["mode"] = "default"

        return status

    def start(self, background: bool = True) -> bool:
        """Start EverMemOS service"""
        if self.is_running():
            print("✅ EverMemOS is already running")
            return True

        # Ensure logs directory exists
        (self.project_dir / "logs").mkdir(exist_ok=True)

        # Create a new timestamped log file for this run (UTC)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.log_file = self.project_dir / "logs" / f"evermemos_{ts}.log"

        print(f"ℹ️  Using configuration: .env")

        # Always use .env
        env = os.environ.copy()
        cmd = ["uv", "run", "python", "src/run.py", "--env-file", ".env"]

        if background:
            print("🚀 Starting EverMemOS in background...")

            # Start process in background
            with open(self.log_file, "w") as log:
                process = subprocess.Popen(
                    cmd,
                    cwd=self.project_dir,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True
                )

            # Save PID
            self.pid_file.write_text(str(process.pid))

            # Wait a moment and verify
            time.sleep(2)

            if self.is_running():
                status = self.get_status()
                if status["api_accessible"]:
                    print(f"✅ EverMemOS started successfully (PID: {process.pid})")
                    print(f"📝 Logs: {self.log_file}")
                    print(f"🌐 API: http://localhost:1995")
                    return True
                else:
                    print("⚠️  Service started but API not accessible yet")
                    print(f"   Check logs: tail -f {self.log_file}")
                    return True
            else:
                print("❌ Failed to start service")
                print(f"   Check logs: cat {self.log_file}")
                return False
        else:
            # Run in foreground
            print("🚀 Starting EverMemOS (foreground mode)...")
            print("   Press Ctrl+C to stop")
            try:
                subprocess.run(cmd, cwd=self.project_dir, env=env)
                return True
            except KeyboardInterrupt:
                print("\n⏹️  Stopped by user")
                return True

    def stop(self) -> bool:
        """Stop EverMemOS service"""
        if not self.is_running():
            print("ℹ️  EverMemOS is not running")
            return True

        try:
            pid = int(self.pid_file.read_text().strip())
            print(f"⏹️  Stopping EverMemOS (PID: {pid})...")

            # Send SIGTERM
            os.kill(pid, signal.SIGTERM)

            # Wait for graceful shutdown
            for i in range(10):
                if not self.is_running():
                    print("✅ EverMemOS stopped successfully")
                    return True
                time.sleep(0.5)

            # Force kill if needed
            print("⚠️  Forcing shutdown...")
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)

            if not self.is_running():
                print("✅ EverMemOS stopped")
                return True
            else:
                print("❌ Failed to stop service")
                return False

        except ProcessLookupError:
            print("ℹ️  Process already stopped")
            self.pid_file.unlink(missing_ok=True)
            return True
        except Exception as e:
            print(f"❌ Error stopping service: {e}")
            return False

    def restart(self) -> bool:
        """Restart EverMemOS service"""
        print("🔄 Restarting EverMemOS...")
        self.stop()
        time.sleep(1)
        return self.start()

    def show_status(self):
        """Display service status"""
        status = self.get_status()

        print("\n" + "="*60)
        print(" "*20 + "EverMemOS Status")
        print("="*60 + "\n")

        if status["running"]:
            print(f"🟢 Status: Running")
            print(f"🆔 PID: {status['pid']}")

            if status["api_accessible"]:
                print(f"🌐 API: http://localhost:1995 ✅")
            else:
                print(f"🌐 API: http://localhost:1995 ❌ (not accessible)")

            if status["mode"]:
                print(f"⚙️  Mode: {status['mode']}")

            print(f"\n📝 Logs: tail -f {self.log_file}")
            print(f"⏹️  Stop: ./stop_service.sh")
        else:
            print(f"🔴 Status: Stopped")
            print(f"\n🚀 Start: /evermemos-start")

        print("\n" + "="*60 + "\n")

    def show_logs(self, lines: int = 50, follow: bool = False):
        """Show service logs"""
        if not self.log_file.exists():
            print("❌ No log file found")
            return

        if follow:
            # Follow logs (tail -f)
            print(f"📝 Following logs (Ctrl+C to stop)...")
            try:
                subprocess.run(["tail", "-f", str(self.log_file)])
            except KeyboardInterrupt:
                print("\n")
        else:
            # Show last N lines
            subprocess.run(["tail", f"-{lines}", str(self.log_file)])


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="EverMemOS Service Manager")
    parser.add_argument(
        "action",
        choices=["start", "stop", "restart", "status", "logs"],
        help="Action to perform"
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Run in foreground (for start)"
    )
    parser.add_argument(
        "--follow",
        action="store_true",
        help="Follow logs (for logs)"
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=50,
        help="Number of log lines to show (default: 50)"
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=None,
        help="Project directory (default: current directory)"
    )
    args = parser.parse_args()

    # Create manager
    manager = ServiceManager(project_dir=args.project_dir)

    # Execute action
    if args.action == "start":
        success = manager.start(background=not args.foreground)
        sys.exit(0 if success else 1)

    elif args.action == "stop":
        success = manager.stop()
        sys.exit(0 if success else 1)

    elif args.action == "restart":
        success = manager.restart()
        sys.exit(0 if success else 1)

    elif args.action == "status":
        manager.show_status()
        sys.exit(0)

    elif args.action == "logs":
        manager.show_logs(lines=args.lines, follow=args.follow)
        sys.exit(0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
EverMemOS Doctor - Health Check and Diagnostics

Automatically diagnose and fix common issues.
"""

import os
import sys
import subprocess
import platform
import json
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Doctor:
    """Diagnose and fix EverMemOS issues"""

    def __init__(self, project_dir: Optional[str] = None):
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.issues = []
        self.warnings = []
        self.checks_passed = 0
        self.checks_failed = 0

    def check(self, name: str, condition: bool, fix_cmd: Optional[str] = None) -> bool:
        """Run a check and record result"""
        if condition:
            print(f"✅ {name}")
            self.checks_passed += 1
            return True
        else:
            print(f"❌ {name}")
            self.checks_failed += 1
            self.issues.append((name, fix_cmd))
            return False

    def warn(self, message: str):
        """Record a warning"""
        print(f"⚠️  {message}")
        self.warnings.append(message)

    def info(self, message: str):
        """Print info message"""
        print(f"ℹ️  {message}")

    def header(self, text: str):
        """Print section header"""
        print(f"\n{'='*60}")
        print(f"{text:^60}")
        print(f"{'='*60}\n")

    def run_command(self, cmd: List[str]) -> Tuple[bool, str]:
        """Run command and return (success, output)"""
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0, result.stdout
        except Exception as e:
            return False, str(e)

    def check_python_version(self) -> bool:
        """Check Python version"""
        version = sys.version_info
        required_major, required_minor = 3, 8

        if version.major > required_major or \
           (version.major == required_major and version.minor >= required_minor):
            return self.check(
                f"Python version ({version.major}.{version.minor}.{version.micro})",
                True
            )
        else:
            return self.check(
                f"Python version (need 3.8+, found {version.major}.{version.minor})",
                False,
                "Install Python 3.8 or higher"
            )

    def check_uv(self) -> bool:
        """Check if uv is installed"""
        success, output = self.run_command(["which", "uv"])
        return self.check(
            "uv package manager",
            success,
            "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        )

    def check_project_structure(self) -> bool:
        """Check project directory structure"""
        checks = [
            ("Project directory", self.project_dir.exists()),
            ("Source code (src/)", (self.project_dir / "src").exists()),
            ("Configuration (pyproject.toml)", (self.project_dir / "pyproject.toml").exists()),
        ]

        all_good = True
        for name, condition in checks:
            if not self.check(name, condition):
                all_good = False

        return all_good

    def check_configuration(self) -> bool:
        """Check configuration files"""
        env_files = [".env", ".env.lite", ".env.production"]
        found = False

        for env_file in env_files:
            env_path = self.project_dir / env_file
            if env_path.exists():
                self.check(f"Configuration file ({env_file})", True)
                found = True
                break

        if not found:
            return self.check(
                "Configuration file",
                False,
                "Run: /evermemos-setup to create configuration"
            )

        return True

    def check_data_directory(self) -> bool:
        """Check data directory"""
        data_dir = self.project_dir / "data"

        if not data_dir.exists():
            return self.check(
                "Data directory",
                False,
                f"Create with: mkdir -p {data_dir}"
            )

        # Check if writable
        test_file = data_dir / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()
            return self.check("Data directory (writable)", True)
        except Exception as e:
            return self.check(
                "Data directory (writable)",
                False,
                f"Check permissions: chmod 755 {data_dir}"
            )

    def check_dependencies(self) -> bool:
        """Check if dependencies are installed"""
        # Try to import key packages
        try:
            import fastapi
            import uvicorn
            self.check("Python dependencies", True)
            return True
        except ImportError:
            return self.check(
                "Python dependencies",
                False,
                "Install with: uv sync"
            )

    def check_service_running(self) -> bool:
        """Check if service is running"""
        pid_file = self.project_dir / "logs" / "evermemos.pid"

        if not pid_file.exists():
            return self.check(
                "Service running",
                False,
                "Start with: /evermemos-start"
            )

        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if process exists
            return self.check(f"Service running (PID: {pid})", True)
        except (ProcessLookupError, ValueError):
            return self.check(
                "Service running",
                False,
                "Start with: /evermemos-start"
            )

    def check_api_accessible(self) -> bool:
        """Check if API is accessible"""
        try:
            response = requests.get("http://localhost:1995", timeout=3)
            return self.check(
                "API accessible (http://localhost:1995)",
                response.status_code in [200, 404]
            )
        except requests.exceptions.ConnectionError:
            return self.check(
                "API accessible",
                False,
                "Service may not be running or port is blocked"
            )
        except Exception as e:
            return self.check(
                "API accessible",
                False,
                f"Connection error: {str(e)}"
            )

    def check_port_available(self) -> bool:
        """Check if port 1995 is available or in use by EverMemOS"""
        import socket

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)

        try:
            result = sock.connect_ex(('localhost', 1995))
            sock.close()

            if result == 0:
                # Port is in use - check if it's our service
                try:
                    response = requests.get("http://localhost:1995", timeout=1)
                    self.check("Port 1995 (in use by EverMemOS)", True)
                    return True
                except:
                    return self.check(
                        "Port 1995 (in use by another service)",
                        False,
                        "Change port in .env or stop conflicting service"
                    )
            else:
                self.check("Port 1995 (available)", True)
                return True

        except Exception as e:
            self.warn(f"Could not check port: {e}")
            return True

    def check_disk_space(self) -> bool:
        """Check available disk space"""
        try:
            stat = os.statvfs(self.project_dir)
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)

            if free_gb < 0.5:
                return self.check(
                    f"Disk space ({free_gb:.1f} GB free)",
                    False,
                    "At least 500MB free space recommended"
                )
            elif free_gb < 2:
                self.warn(f"Low disk space: {free_gb:.1f} GB free")

            return self.check(f"Disk space ({free_gb:.1f} GB free)", True)

        except Exception as e:
            self.warn(f"Could not check disk space: {e}")
            return True

    def check_memory(self) -> bool:
        """Check available memory"""
        try:
            import psutil
            mem = psutil.virtual_memory()
            free_gb = mem.available / (1024**3)

            if free_gb < 0.5:
                self.warn(f"Low memory: {free_gb:.1f} GB free")

            return self.check(f"Memory ({free_gb:.1f} GB free)", free_gb >= 0.5)

        except ImportError:
            self.info("Install psutil for memory checks: pip install psutil")
            return True
        except Exception as e:
            self.warn(f"Could not check memory: {e}")
            return True

    def check_log_file(self) -> bool:
        """Check log file for recent errors"""
        logs_dir = self.project_dir / "logs"
        existing_logs = sorted(logs_dir.glob("evermemos_*.log")) if logs_dir.exists() else []
        log_file = existing_logs[-1] if existing_logs else None

        if log_file is None:
            self.info("No log file found (service not started yet)")
            return True

        try:
            # Read last 50 lines
            with open(log_file, 'r') as f:
                lines = f.readlines()[-50:]

            # Count errors
            errors = [line for line in lines if "ERROR" in line or "CRITICAL" in line]

            if errors:
                self.warn(f"Found {len(errors)} errors in recent logs")
                # Show first 3 errors
                for error in errors[:3]:
                    self.info(f"  {error.strip()}")
                return False
            else:
                return self.check("Recent logs (no errors)", True)

        except Exception as e:
            self.warn(f"Could not read log file: {e}")
            return True

    def run_diagnostics(self) -> bool:
        """Run all diagnostic checks"""
        self.header("EverMemOS Health Check")

        # System checks
        self.info("System Environment")
        self.info(f"OS: {platform.system()} {platform.release()}")
        self.info(f"Architecture: {platform.machine()}")
        print()

        # Basic checks
        self.header("Basic Checks")
        self.check_python_version()
        self.check_uv()
        self.check_project_structure()
        self.check_configuration()
        self.check_data_directory()

        # Dependency checks
        self.header("Dependency Checks")
        self.check_dependencies()

        # Service checks
        self.header("Service Checks")
        self.check_port_available()
        service_running = self.check_service_running()

        if service_running:
            self.check_api_accessible()
            self.check_log_file()

        # Resource checks
        self.header("Resource Checks")
        self.check_disk_space()
        self.check_memory()

        # Summary
        self.header("Summary")
        total_checks = self.checks_passed + self.checks_failed

        print(f"✅ Passed: {self.checks_passed}/{total_checks}")
        print(f"❌ Failed: {self.checks_failed}/{total_checks}")
        print(f"⚠️  Warnings: {len(self.warnings)}")

        if self.checks_failed == 0 and len(self.warnings) == 0:
            print("\n🎉 Everything looks good! EverMemOS is healthy.")
            return True
        elif self.checks_failed == 0:
            print("\n✅ All checks passed, but there are some warnings.")
            return True
        else:
            print("\n⚠️  Some checks failed. See fixes below.")
            self.show_fixes()
            return False

    def show_fixes(self):
        """Show suggested fixes for issues"""
        if not self.issues:
            return

        print("\n" + "="*60)
        print("Suggested Fixes")
        print("="*60 + "\n")

        for i, (issue, fix) in enumerate(self.issues, 1):
            print(f"{i}. {issue}")
            if fix:
                print(f"   Fix: {fix}")
            print()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="EverMemOS Health Check and Diagnostics"
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=None,
        help="Project directory (default: current directory)"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically fix issues (not yet implemented)"
    )

    args = parser.parse_args()

    # Create doctor
    doctor = Doctor(project_dir=args.project_dir)

    # Run diagnostics
    success = doctor.run_diagnostics()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

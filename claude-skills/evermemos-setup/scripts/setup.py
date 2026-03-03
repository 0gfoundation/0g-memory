#!/usr/bin/env python3
"""
EverMemOS Setup Script

Automated installation and initialization for EverMemOS.
"""

import os
import sys
import shutil
import subprocess
import platform
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class Colors:
    """Terminal colors"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


class SetupManager:
    """Manages EverMemOS setup process"""

    def __init__(self, project_dir: Optional[str] = None):
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.os_type = platform.system().lower()

    def print_header(self, text: str):
        """Print formatted header"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}{text:^60}{Colors.ENDC}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")

    def print_success(self, text: str):
        """Print success message"""
        print(f"{Colors.OKGREEN}✅ {text}{Colors.ENDC}")

    def print_warning(self, text: str):
        """Print warning message"""
        print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")

    def print_error(self, text: str):
        """Print error message"""
        print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")

    def print_info(self, text: str):
        """Print info message"""
        print(f"{Colors.OKCYAN}ℹ️  {text}{Colors.ENDC}")

    def run_command(self, cmd: List[str], check: bool = True, capture: bool = True) -> Tuple[bool, str]:
        """Run shell command and return (success, output)"""
        try:
            if capture:
                result = subprocess.run(
                    cmd,
                    check=check,
                    capture_output=True,
                    text=True,
                    timeout=300
                )
                return result.returncode == 0, result.stdout
            else:
                result = subprocess.run(cmd, check=check, timeout=300)
                return result.returncode == 0, ""
        except subprocess.CalledProcessError as e:
            if check:
                self.print_error(f"Command failed: {' '.join(cmd)}")
                if hasattr(e, 'stderr') and e.stderr:
                    self.print_error(f"Error: {e.stderr}")
            return False, ""
        except subprocess.TimeoutExpired:
            self.print_error(f"Command timeout: {' '.join(cmd)}")
            return False, ""
        except FileNotFoundError:
            return False, ""

    def check_command_exists(self, cmd: str) -> bool:
        """Check if command exists"""
        success, _ = self.run_command(["which", cmd], check=False)
        return success

    def check_python(self) -> bool:
        """Check Python version"""
        self.print_info("Checking Python version...")
        version = sys.version_info

        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.print_error(f"Python 3.8+ required, found {version.major}.{version.minor}")
            return False

        self.print_success(f"Python {version.major}.{version.minor}.{version.micro}")
        return True

    def check_uv(self) -> bool:
        """Check if uv is installed"""
        self.print_info("Checking uv package manager...")

        if self.check_command_exists("uv"):
            self.print_success("uv is installed")
            return True

        self.print_warning("uv not found")
        return False

    def install_uv(self) -> bool:
        """Install uv package manager"""
        self.print_info("Installing uv...")

        try:
            # Download and run installer
            install_cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"
            result = subprocess.run(
                install_cmd,
                shell=True,
                check=True,
                capture_output=True,
                text=True
            )

            # Reload PATH
            uv_bin = Path.home() / ".cargo" / "bin"
            if uv_bin.exists():
                os.environ["PATH"] = f"{uv_bin}:{os.environ['PATH']}"

            self.print_success("uv installed successfully")
            return True
        except Exception as e:
            self.print_error(f"Failed to install uv: {e}")
            return False

    def install_docker(self) -> bool:
        """Install Docker based on operating system"""
        self.print_info("Installing Docker...")

        os_type = self.os_type

        try:
            if os_type == "linux":
                return self._install_docker_linux()
            elif os_type == "darwin":
                return self._install_docker_macos()
            else:
                self.print_error(f"Automatic Docker installation not supported on {os_type}")
                self.print_info("Please install Docker manually:")
                self.print_info("  https://docs.docker.com/get-docker/")
                return False
        except Exception as e:
            self.print_error(f"Failed to install Docker: {e}")
            return False

    def _install_docker_linux(self) -> bool:
        """Install Docker on Linux"""
        self.print_info("Detected Linux system, installing Docker...")

        try:
            # Detect Linux distribution
            distro = None
            if Path("/etc/os-release").exists():
                with open("/etc/os-release") as f:
                    content = f.read()
                    if "ubuntu" in content.lower() or "debian" in content.lower():
                        distro = "debian"
                    elif "centos" in content.lower() or "rhel" in content.lower() or "fedora" in content.lower():
                        distro = "rhel"

            if distro == "debian":
                self.print_info("Installing Docker on Debian/Ubuntu...")

                commands = [
                    # Update package index
                    "sudo apt-get update",
                    # Install prerequisites
                    "sudo apt-get install -y ca-certificates curl gnupg",
                    # Add Docker's official GPG key
                    "sudo install -m 0755 -d /etc/apt/keyrings",
                    "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg",
                    "sudo chmod a+r /etc/apt/keyrings/docker.gpg",
                    # Set up repository
                    'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null',
                    # Update package index again
                    "sudo apt-get update",
                    # Install Docker
                    "sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin",
                ]

                for cmd in commands:
                    self.print_info(f"Running: {cmd}")
                    result = subprocess.run(
                        cmd,
                        shell=True,
                        check=True,
                        capture_output=True,
                        text=True
                    )

                # Start Docker service
                subprocess.run("sudo systemctl start docker", shell=True, check=True)
                subprocess.run("sudo systemctl enable docker", shell=True, check=True)

                # Add current user to docker group (optional, requires re-login)
                try:
                    username = os.environ.get("USER", os.environ.get("USERNAME"))
                    if username:
                        subprocess.run(f"sudo usermod -aG docker {username}", shell=True, check=True)
                        self.print_warning(f"Added {username} to docker group")
                        self.print_warning("You may need to log out and back in for group changes to take effect")
                except:
                    pass

                self.print_success("Docker installed successfully")
                return True

            elif distro == "rhel":
                self.print_info("Installing Docker on RHEL/CentOS/Fedora...")

                commands = [
                    "sudo yum install -y yum-utils",
                    "sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo",
                    "sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin",
                    "sudo systemctl start docker",
                    "sudo systemctl enable docker",
                ]

                for cmd in commands:
                    self.print_info(f"Running: {cmd}")
                    subprocess.run(cmd, shell=True, check=True)

                self.print_success("Docker installed successfully")
                return True

            else:
                self.print_error("Could not detect Linux distribution")
                self.print_info("Please install Docker manually:")
                self.print_info("  https://docs.docker.com/engine/install/")
                return False

        except subprocess.CalledProcessError as e:
            self.print_error(f"Installation failed: {e}")
            self.print_info("\nTroubleshooting:")
            self.print_info("  1. Make sure you have sudo privileges")
            self.print_info("  2. Check your internet connection")
            self.print_info("  3. Try manual installation: https://docs.docker.com/engine/install/")
            return False

    def _install_docker_macos(self) -> bool:
        """Install Docker on macOS"""
        self.print_info("Detected macOS system")

        # Check if Homebrew is available
        if self.check_command_exists("brew"):
            self.print_info("Installing Docker Desktop via Homebrew...")

            try:
                # Install Docker Desktop
                subprocess.run(
                    ["brew", "install", "--cask", "docker"],
                    check=True,
                    capture_output=True,
                    text=True
                )

                self.print_success("Docker Desktop installed")
                self.print_warning("Please start Docker Desktop from Applications")
                self.print_info("After Docker Desktop starts, re-run this setup")
                return True

            except subprocess.CalledProcessError:
                self.print_error("Homebrew installation failed")

        # Fallback to manual instructions
        self.print_info("\nTo install Docker on macOS:")
        self.print_info("  1. Download Docker Desktop:")
        self.print_info("     https://docs.docker.com/desktop/install/mac-install/")
        self.print_info("  2. Open the downloaded .dmg file")
        self.print_info("  3. Drag Docker to Applications")
        self.print_info("  4. Launch Docker from Applications")
        self.print_info("  5. Wait for Docker to start")
        self.print_info("  6. Re-run this setup")
        return False

    def install_docker_compose(self) -> bool:
        """Install Docker Compose based on operating system"""
        self.print_info("Installing Docker Compose...")

        os_type = self.os_type

        try:
            if os_type == "linux":
                return self._install_docker_compose_linux()
            elif os_type == "darwin":
                return self._install_docker_compose_macos()
            else:
                self.print_error(f"Automatic Docker Compose installation not supported on {os_type}")
                self.print_info("Please install Docker Compose manually:")
                self.print_info("  https://docs.docker.com/compose/install/")
                return False
        except Exception as e:
            self.print_error(f"Failed to install Docker Compose: {e}")
            return False

    def _install_docker_compose_linux(self) -> bool:
        """Install Docker Compose on Linux"""
        self.print_info("Detected Linux system, installing Docker Compose...")

        try:
            # Detect Linux distribution
            distro = None
            if Path("/etc/os-release").exists():
                with open("/etc/os-release") as f:
                    content = f.read()
                    if "ubuntu" in content.lower() or "debian" in content.lower():
                        distro = "debian"
                    elif "centos" in content.lower() or "rhel" in content.lower() or "fedora" in content.lower():
                        distro = "rhel"

            if distro == "debian":
                self.print_info("Installing Docker Compose plugin on Debian/Ubuntu...")

                commands = [
                    "sudo apt-get update",
                    "sudo apt-get install -y docker-compose-plugin",
                ]

                for cmd in commands:
                    self.print_info(f"Running: {cmd}")
                    result = subprocess.run(
                        cmd,
                        shell=True,
                        check=True,
                        capture_output=True,
                        text=True
                    )

                self.print_success("Docker Compose plugin installed successfully")
                return True

            elif distro == "rhel":
                self.print_info("Installing Docker Compose plugin on RHEL/CentOS/Fedora...")

                commands = [
                    "sudo yum install -y docker-compose-plugin",
                ]

                for cmd in commands:
                    self.print_info(f"Running: {cmd}")
                    subprocess.run(cmd, shell=True, check=True)

                self.print_success("Docker Compose plugin installed successfully")
                return True

            else:
                self.print_error("Could not detect Linux distribution")
                self.print_info("Please install Docker Compose manually:")
                self.print_info("  https://docs.docker.com/compose/install/")
                return False

        except subprocess.CalledProcessError as e:
            self.print_error(f"Installation failed: {e}")
            self.print_info("\nTroubleshooting:")
            self.print_info("  1. Make sure you have sudo privileges")
            self.print_info("  2. Check your internet connection")
            self.print_info("  3. Verify Docker is installed first")
            self.print_info("  4. Try manual installation: https://docs.docker.com/compose/install/")
            return False

    def _install_docker_compose_macos(self) -> bool:
        """Install Docker Compose on macOS"""
        self.print_info("Detected macOS system")

        # Docker Desktop for macOS includes Docker Compose v2
        self.print_info("Docker Desktop for macOS includes Docker Compose v2")
        self.print_info("If Docker is installed but Compose isn't working:")
        self.print_info("  1. Make sure Docker Desktop is running")
        self.print_info("  2. Check Docker Desktop version is up to date")
        self.print_info("  3. Try restarting Docker Desktop")
        self.print_info("\nIf Docker Desktop is old, update it:")

        if self.check_command_exists("brew"):
            self.print_info("  brew upgrade --cask docker")
        else:
            self.print_info("  Download latest from: https://docs.docker.com/desktop/install/mac-install/")

        return False

    def setup_docker_compose(self, non_interactive: bool = False) -> bool:
        """Check Docker / Docker Compose availability and verify docker-compose.yaml"""
        self.print_header("Setting Up Docker Compose")
        self.print_info("Standard mode uses Docker containers for all services")

        # Check Docker
        if not self.check_command_exists("docker"):
            self.print_warning("Docker is not installed")

            if non_interactive:
                self.print_error("Docker is required for standard mode")
                self.print_info("Install Docker: https://docs.docker.com/get-docker/")
                return False

            # Ask user if they want to auto-install
            self.print_info("\nDocker is required for standard mode.")
            response = input("Would you like to install Docker automatically? (y/n): ").lower()

            if response == 'y':
                if self.install_docker():
                    self.print_success("Docker installed! Verifying...")

                    # Reload PATH and check again
                    import time
                    time.sleep(2)

                    if not self.check_command_exists("docker"):
                        self.print_warning("Docker installed but not yet available")
                        self.print_info("Please:")
                        if self.os_type == "darwin":
                            self.print_info("  1. Start Docker Desktop from Applications")
                            self.print_info("  2. Wait for Docker to fully start")
                        else:
                            self.print_info("  1. Log out and back in (for group permissions)")
                            self.print_info("  2. Or run: newgrp docker")
                        self.print_info("  3. Re-run this setup")
                        return False
                else:
                    self.print_error("Automatic installation failed")
                    self.print_info("Please install Docker manually:")
                    self.print_info("  https://docs.docker.com/get-docker/")
                    return False
            else:
                self.print_info("Please install Docker manually:")
                self.print_info("  https://docs.docker.com/get-docker/")
                return False

        # Check Docker Compose
        has_compose_v1 = self.check_command_exists("docker-compose")
        has_compose_v2, _ = self.run_command(["docker", "compose", "version"], check=False)

        if not (has_compose_v1 or has_compose_v2):
            self.print_warning("Docker Compose is not available")

            if non_interactive:
                self.print_error("Docker Compose is required for standard mode")
                self.print_info("Install Docker Compose: https://docs.docker.com/compose/install/")
                return False

            # Ask user if they want to auto-install
            self.print_info("\nDocker Compose is required for standard mode.")

            # On macOS, Docker Desktop should include Compose
            if self.os_type == "darwin":
                self.print_warning("Docker Compose should be included with Docker Desktop")
                self.print_info("Make sure Docker Desktop is running and up to date")
                response = input("Try to verify again? (y/n): ").lower()
                if response == 'y':
                    import time
                    time.sleep(2)
                    has_compose_v2, _ = self.run_command(["docker", "compose", "version"], check=False)
                    if has_compose_v2:
                        self.print_success("Docker Compose is now available!")
                    else:
                        self.print_error("Docker Compose still not available")
                        self.print_info("Please:")
                        self.print_info("  1. Update Docker Desktop to latest version")
                        if self.check_command_exists("brew"):
                            self.print_info("     brew upgrade --cask docker")
                        self.print_info("  2. Or download from: https://docs.docker.com/desktop/install/mac-install/")
                        return False
                else:
                    return False
            else:
                # Linux - offer to install
                response = input("Would you like to install Docker Compose automatically? (y/n): ").lower()

                if response == 'y':
                    if self.install_docker_compose():
                        self.print_success("Docker Compose installed! Verifying...")

                        # Reload PATH and check again
                        import time
                        time.sleep(2)

                        has_compose_v2, _ = self.run_command(["docker", "compose", "version"], check=False)
                        if not has_compose_v2:
                            self.print_warning("Docker Compose installed but not yet available")
                            self.print_info("Please try:")
                            self.print_info("  1. Restart your terminal")
                            self.print_info("  2. Or run: hash -r")
                            self.print_info("  3. Re-run this setup")
                            return False
                    else:
                        self.print_error("Automatic installation failed")
                        self.print_info("Please install Docker Compose manually:")
                        self.print_info("  https://docs.docker.com/compose/install/")
                        return False
                else:
                    self.print_info("Please install Docker Compose manually:")
                    self.print_info("  https://docs.docker.com/compose/install/")
                    return False

        # Verify docker-compose.yaml exists (must be present after git clone)
        compose_file = self.project_dir / "docker-compose.yaml"
        if not compose_file.exists():
            self.print_error("docker-compose.yaml not found.")
            self.print_info("Make sure you cloned the full repository.")
            return False
        self.print_success("docker-compose.yaml found")

        # Create .env from env.template.0g.example if not exists
        env_file = self.project_dir / ".env"
        template_file = self.project_dir / "env.template.0g.example"
        if not env_file.exists():
            if template_file.exists():
                shutil.copy2(template_file, env_file)
                self.print_success("Created .env from env.template.0g.example")
                self.print_warning("Please edit .env and fill in your private keys and API keys")
            else:
                self.print_warning(".env not found and env.template.0g.example missing — please create .env manually")
        else:
            self.print_info(".env already exists")

        # Create data directory
        data_dir = self.project_dir / "data"
        data_dir.mkdir(exist_ok=True)
        self.print_success("Created data directory")

        return True

    def install_dependencies(self) -> bool:
        """Install Python dependencies"""
        self.print_header("Installing Dependencies")

        # Check if pyproject.toml exists
        if not (self.project_dir / "pyproject.toml").exists():
            self.print_error("pyproject.toml not found")
            return False

        # Install with uv
        self.print_info("Installing Python packages with uv...")
        os.chdir(self.project_dir)

        success, _ = self.run_command(["uv", "sync"], capture=False)
        if success:
            self.print_success("Dependencies installed")
            return True
        else:
            self.print_error("Failed to install dependencies")
            return False


    def install_claude_hooks(self) -> bool:
        """
        Copy EverMemOS skills to ~/.claude/skills/ and merge hooks into
        ~/.claude/settings.json (global, applies to all projects).

        Safe to run multiple times — already-configured hooks are skipped.
        """
        self.print_header("Installing Claude Code Integration")

        # ── Step 1: Copy skill directories ──────────────────────────────────
        skills_src = self.project_dir / "claude-skills"
        skills_dst = Path.home() / ".claude" / "skills"

        if not skills_src.exists():
            self.print_warning(f"claude-skills/ not found at {skills_src}, skipping")
            return False

        skills_dst.mkdir(parents=True, exist_ok=True)

        for skill_dir in sorted(skills_src.iterdir()):
            if skill_dir.is_dir() and skill_dir.name.startswith("evermemos"):
                dst = skills_dst / skill_dir.name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(skill_dir, dst)
                self.print_success(f"Installed skill: ~/.claude/skills/{skill_dir.name}/")

        # ── Step 2: Merge hooks into ~/.claude/settings.json ────────────────
        settings_path = Path.home() / ".claude" / "settings.json"

        # Load existing global settings (or start fresh)
        settings: dict = {}
        if settings_path.exists():
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self.print_warning(f"Could not read {settings_path}: {e}, will recreate")
                settings = {}

        # Ensure env vars are set so hooks know where to reach the backend
        if "env" not in settings:
            settings["env"] = {}
        settings["env"].setdefault("EVERMEMOS_BASE_URL", "http://localhost:1995")
        settings["env"].setdefault("EVERMEMOS_USER_ID", "claude_code_user")
        settings["env"].setdefault("EVERMEMOS_GROUP_ID", "session_2026")

        if "hooks" not in settings:
            settings["hooks"] = {}

        # Hook definitions: (event, matcher_or_None, command, timeout)
        new_hooks = [
            ("SessionStart",    "startup|clear|compact",
             "python3 \"$HOME/.claude/skills/evermemos/scripts/hook_session_start.py\"", 30),
            ("UserPromptSubmit", None,
             "python3 \"$HOME/.claude/skills/evermemos/scripts/hook_user_prompt.py\"",  15),
            ("PostToolUse",     "*",
             "python3 \"$HOME/.claude/skills/evermemos/scripts/hook_tool_use.py\"",     20),
            ("Stop",            None,
             "python3 \"$HOME/.claude/skills/evermemos/scripts/hook_stop.py\"",         30),
            ("SessionEnd",      None,
             "python3 \"$HOME/.claude/skills/evermemos/scripts/hook_session_end.py\"",  30),
        ]

        for event, matcher, command, timeout in new_hooks:
            existing = settings["hooks"].get(event, [])

            # Idempotent: skip if this script is already registered
            script_name = command.split("/")[-1].rstrip('"')
            already_present = any(
                script_name in h.get("command", "")
                for group in existing
                for h in group.get("hooks", [])
            )
            if already_present:
                self.print_info(f"Hook {event} already configured, skipping")
                continue

            hook_group: dict = {
                "hooks": [{"type": "command", "command": command, "timeout": timeout}]
            }
            if matcher:
                hook_group["matcher"] = matcher

            settings["hooks"].setdefault(event, []).append(hook_group)
            self.print_success(f"Added hook: {event}")

        # Write back
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
                f.write("\n")
            self.print_success("Updated ~/.claude/settings.json")
            return True
        except OSError as e:
            self.print_error(f"Failed to write settings.json: {e}")
            return False

    def run_setup(self, non_interactive: bool = False) -> bool:
        """Run complete setup process"""
        self.print_header("EverMemOS Setup")
        self.print_info("Installing EverMemOS with Docker containers")
        print()

        # Step 1: Check Python
        if not self.check_python():
            return False

        # Step 2: Check/Install uv
        if not self.check_uv():
            if non_interactive:
                self.print_error("uv is required for dependency management")
                return False

            self.print_info("uv is required for dependency management")
            response = input("Install uv now? (y/n): ").lower()
            if response == 'y':
                if not self.install_uv():
                    return False
            else:
                self.print_error("uv is required to continue")
                return False

        # Step 3: Install dependencies
        if not self.install_dependencies():
            return False

        # Step 4: Setup Docker services
        if not self.setup_docker_compose(non_interactive=non_interactive):
            return False

        # Step 5: Install skills + hooks into Claude Code global config
        if not self.install_claude_hooks():
            self.print_warning(
                "Claude Code hook installation failed — "
                "hooks won't auto-record across all projects. "
                "You can re-run setup to retry."
            )

        # Success
        self.print_header("Setup Complete! 🎉")
        self.print_success("EverMemOS is ready to use")
        print()
        self.print_info("Docker services started:")
        print("  • MongoDB: localhost:27017")
        print("  • Elasticsearch: localhost:19200")
        print("  • Milvus: localhost:19530")
        print("  • Redis: localhost:6379")
        print()
        self.print_info("Configuration: .env")
        print()
        self.print_info("Next steps:")
        print("  1. Configure API keys in .env file:")
        print("     cp env.template .env")
        print("     # Edit .env and set LLM_API_KEY and VECTORIZE_API_KEY")
        print()
        print("  2. Start EverMemOS:")
        print("     uv run python src/run.py --port 1995")
        print()
        print("  3. Check Docker status:")
        print("     docker ps")
        print()
        print("  4. View logs:")
        print("     docker-compose logs -f")
        print()

        return True


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description="EverMemOS Setup - Docker-based installation"
    )
    parser.add_argument(
        "--project-dir",
        type=str,
        default=None,
        help="Project directory (default: current directory)"
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run in non-interactive mode"
    )

    args = parser.parse_args()

    # Create setup manager
    manager = SetupManager(project_dir=args.project_dir)

    # Run setup
    success = manager.run_setup(non_interactive=args.non_interactive)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

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

    def _read_env_value(self, key: str, default: str = "") -> str:
        """Read a single key from .env file. Returns default if file or key not found."""
        env_file = self.project_dir / ".env"
        if not env_file.exists():
            return default
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip()
        except OSError:
            pass
        return default

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
        """Check Python version.

        Only requires 3.8+ to run this installer script.
        The application itself requires Python 3.12, which uv manages
        automatically via pyproject.toml (requires-python = ">=3.12,<3.13").
        """
        self.print_info("Checking Python version...")
        version = sys.version_info

        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.print_error(f"Python 3.8+ required to run this installer, found {version.major}.{version.minor}")
            return False

        self.print_success(f"Python {version.major}.{version.minor}.{version.micro} (uv will manage Python 3.12 for the application)")
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
        """Install uv package manager (brew on macOS, curl installer on Linux)"""
        self.print_info("Installing uv...")

        try:
            if self.os_type == "darwin":
                # macOS: prefer Homebrew
                if not self.check_command_exists("brew"):
                    self.print_error("Homebrew not found. Please install it from https://brew.sh and retry.")
                    return False
                self.print_info("Using Homebrew to install uv...")
                result = subprocess.run(
                    ["brew", "install", "uv"],
                    check=True,
                )
            else:
                # Linux: use the official curl installer
                self.print_info("Using curl installer to install uv...")
                install_cmd = "curl -LsSf https://astral.sh/uv/install.sh | sh"
                result = subprocess.run(
                    install_cmd,
                    shell=True,
                    check=True,
                )

            # Reload PATH — uv may be installed to ~/.local/bin or ~/.cargo/bin
            for candidate in [
                Path.home() / ".local" / "bin",
                Path.home() / ".cargo" / "bin",
            ]:
                if candidate.exists():
                    path_str = str(candidate)
                    if path_str not in os.environ["PATH"]:
                        os.environ["PATH"] = f"{path_str}:{os.environ['PATH']}"

            self.print_success("uv installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            self.print_error(f"Failed to install uv: {e}")
            if hasattr(e, "stderr") and e.stderr:
                self.print_error(e.stderr)
            return False
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
                )

                self.print_success("Docker Desktop installed")
                self.print_info("Launching Docker Desktop automatically...")
                try:
                    subprocess.run(["open", "-a", "Docker"], check=True)
                except subprocess.CalledProcessError:
                    pass  # May already be running; continue to wait

                # Poll until Docker daemon responds (up to 90 seconds)
                import time
                self.print_info("Waiting for Docker daemon to start (up to 90s)...")
                for i in range(90):
                    ok, _ = self.run_command(["docker", "info"], check=False)
                    if ok:
                        self.print_success("Docker daemon is running")
                        return True
                    if i > 0 and i % 15 == 0:
                        self.print_info(f"  Still waiting... ({i}s elapsed)")
                    time.sleep(1)

                self.print_error("Docker daemon did not start within 90 seconds")
                self.print_info("Please:")
                self.print_info("  1. Open Docker Desktop from Applications manually")
                self.print_info("  2. Wait for it to fully start (whale icon in menu bar stops animating)")
                self.print_info("  3. Re-run this setup")
                return False

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

        # Docker Desktop for macOS includes Docker Compose v2; check if it is
        # already usable before showing any error.
        has_compose, _ = self.run_command(["docker", "compose", "version"], check=False)
        if has_compose:
            self.print_success("Docker Compose (v2) is already available via Docker Desktop")
            return True

        # Not available yet — guide the user.
        self.print_info("Docker Desktop for macOS includes Docker Compose v2.")
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

        # Ensure env vars are set so hooks know where to reach the backend.
        # API_BASE_URL and EVERMEMOS_API_KEY use setdefault so that
        # remote_setup.py values (written afterwards for Scenario C) are not
        # overwritten if install_claude_hooks() is called again later.
        # MEMORY_USER_ID is always synced from .env so re-running install.sh
        # picks up any change the user made to that value.
        if "env" not in settings:
            settings["env"] = {}
        settings["env"].setdefault("API_BASE_URL", "http://localhost:1995")
        settings["env"].setdefault("EVERMEMOS_API_KEY", "")   # empty = no auth (local mode)
        user_id = self._read_env_value("MEMORY_USER_ID") or "default_user"
        old_uid = settings["env"].get("MEMORY_USER_ID", "")
        settings["env"]["MEMORY_USER_ID"] = user_id
        if old_uid and old_uid != user_id:
            self.print_info(f"Updated MEMORY_USER_ID: {old_uid} → {user_id}")

        if "hooks" not in settings:
            settings["hooks"] = {}

        # Resolve absolute python3 path to avoid PATH lookup failures when
        # Claude Code runs hooks in a restricted environment (common on macOS).
        python3_path = shutil.which("python3") or "python3"
        self.print_info(f"Using python3 at: {python3_path}")

        # Hook definitions: (event, matcher_or_None, command, timeout)
        new_hooks = [
            ("SessionStart",    "startup|clear|compact",
             f'"{python3_path}" "$HOME/.claude/skills/evermemos/scripts/hook_session_start.py"', 30),
            ("UserPromptSubmit", None,
             f'"{python3_path}" "$HOME/.claude/skills/evermemos/scripts/hook_user_prompt.py"',  15),
            ("PostToolUse",     "*",
             f'"{python3_path}" "$HOME/.claude/skills/evermemos/scripts/hook_tool_use.py"',     20),
            ("Stop",            None,
             f'"{python3_path}" "$HOME/.claude/skills/evermemos/scripts/hook_stop.py"',         30),
            ("SessionEnd",      None,
             f'"{python3_path}" "$HOME/.claude/skills/evermemos/scripts/hook_session_end.py"',  30),
        ]

        for event, matcher, command, timeout in new_hooks:
            existing = settings["hooks"].get(event, [])

            # Idempotent: skip if this exact command is already registered.
            # We match on the full command string so that an older registration
            # using bare "python3" is replaced by the new absolute-path command.
            already_present = any(
                h.get("command", "") == command
                for group in existing
                for h in group.get("hooks", [])
            )
            if already_present:
                self.print_info(f"Hook {event} already configured, skipping")
                continue

            # Remove any existing hook entry for this script so we can replace
            # it with the updated command (e.g. python3 path changed).
            script_name = command.split("/")[-1].rstrip('"')
            settings["hooks"][event] = [
                group for group in existing
                if not any(script_name in h.get("command", "")
                           for h in group.get("hooks", []))
            ]
            existing = settings["hooks"][event]

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

    def is_claude_code_installed(self) -> bool:
        """Check if Claude Code is installed: binary in PATH or ~/.claude/ exists."""
        if shutil.which("claude"):
            return True
        if (Path.home() / ".claude").exists():
            return True
        return False

    def is_opencode_installed(self) -> bool:
        """Check if OpenCode is installed: binary in PATH, ~/.config/opencode/ exists,
        or the official installer location (~/.opencode/bin/opencode) exists."""
        if shutil.which("opencode"):
            return True
        if (Path.home() / ".config" / "opencode").exists():
            return True
        if (Path.home() / ".opencode" / "bin" / "opencode").exists():
            return True
        return False

    def install_opencode_plugin(self) -> bool:
        """
        Copy EverMemOS plugin to ~/.config/opencode/plugins/ and register it
        in ~/.config/opencode/opencode.json (global, applies to all projects).

        Safe to run multiple times — already-configured entries are skipped.
        """
        self.print_header("Installing OpenCode Integration")

        # ── Step 1: Copy plugin directory ────────────────────────────────────
        plugin_src = self.project_dir / "opencode-skills" / "evermemos"
        plugin_dst = Path.home() / ".config" / "opencode" / "plugins" / "evermemos"

        if not plugin_src.exists():
            self.print_warning(f"opencode-skills/evermemos/ not found at {plugin_src}, skipping")
            return False

        if plugin_dst.exists():
            shutil.rmtree(plugin_dst)
        shutil.copytree(plugin_src, plugin_dst)
        self.print_success(f"Installed plugin: ~/.config/opencode/plugins/evermemos/")

        # ── Step 2: Merge into ~/.config/opencode/opencode.json ──────────────
        config_path = Path.home() / ".config" / "opencode" / "opencode.json"

        config: dict = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self.print_warning(f"Could not read {config_path}: {e}, will recreate")
                config = {}

        # Ensure $schema is present
        config.setdefault("$schema", "https://opencode.ai/config.json")

        # NOTE: OpenCode does not support an "env" key in opencode.json.
        # Remove it if a previous install accidentally wrote it.
        config.pop("env", None)

        # Config priority for the plugin (highest → lowest):
        #   1. Shell environment variables (set in ~/.bashrc or ~/.zshrc)
        #   2. ~/.config/opencode/evermemos.json  (written below for all scenarios)
        #   3. Built-in defaults
        # Relevant variables and their defaults:
        #   baseUrl   → http://localhost:1995  (overwritten by remote_setup.py for Scenario C)
        #   userId    → MEMORY_USER_ID from .env, or "default_user"
        #   apiKey    → (empty for local mode; set by remote_setup.py for Scenario C)

        # Register plugin using absolute path (tilde is not always resolved by OpenCode)
        plugin_entry = f"file://{Path.home()}/.config/opencode/plugins/evermemos/src/index.ts"
        if "plugin" not in config:
            config["plugin"] = []
        if plugin_entry not in config["plugin"]:
            config["plugin"].append(plugin_entry)
            self.print_success("Registered EverMemOS plugin in opencode.json")
        else:
            self.print_info("EverMemOS plugin already registered, skipping")

        # Write back
        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                f.write("\n")
            self.print_success("Updated ~/.config/opencode/opencode.json")
        except OSError as e:
            self.print_error(f"Failed to write opencode.json: {e}")
            return False

        # ── Step 3: Write ~/.config/opencode/evermemos.json (local defaults) ──
        # The plugin reads this file for userId/baseUrl/apiKey as a fallback to
        # env vars. remote_setup.py overwrites it for Scenario C; here we set
        # local-mode defaults so the user doesn't need to touch their shell profile.
        evermemos_config_path = config_path.parent / "evermemos.json"
        evermemos_config: dict = {}
        if evermemos_config_path.exists():
            try:
                with open(evermemos_config_path, "r", encoding="utf-8") as f:
                    evermemos_config = json.load(f)
            except (json.JSONDecodeError, OSError):
                evermemos_config = {}

        user_id = self._read_env_value("MEMORY_USER_ID") or "default_user"
        evermemos_config["baseUrl"] = "http://localhost:1995"  # always reset to local; remote_setup.py overwrites for Scenario C
        evermemos_config["userId"] = user_id  # always sync with .env

        try:
            with open(evermemos_config_path, "w", encoding="utf-8") as f:
                json.dump(evermemos_config, f, indent=2, ensure_ascii=False)
                f.write("\n")
            self.print_success(f"Updated ~/.config/opencode/evermemos.json (userId={user_id})")
        except OSError as e:
            self.print_warning(f"Failed to write evermemos.json: {e}")

        return True

    def is_openclaw_installed(self) -> bool:
        """Check if OpenClaw is installed: binary in PATH or ~/.openclaw/ exists."""
        if shutil.which("openclaw"):
            return True
        if (Path.home() / ".openclaw").exists():
            return True
        return False

    def install_openclaw_plugin(self) -> bool:
        """
        Install the EverMemOS plugin for OpenClaw using
        ``openclaw plugins install --link <path>``.

        This delegates to the OpenClaw CLI, which uses its own JSON5 parser to
        update ``~/.openclaw/openclaw.json5`` safely.  A ``plugins enable``
        call then activates the plugin.

        Safe to run multiple times — OpenClaw handles re-installs gracefully.
        """
        self.print_header("Installing OpenClaw Integration")

        plugin_src = self.project_dir / "openclaw-skills" / "evermemos"
        if not plugin_src.exists():
            self.print_warning(f"openclaw-skills/evermemos/ not found at {plugin_src}, skipping")
            return False

        openclaw_bin = shutil.which("openclaw")
        if not openclaw_bin:
            self.print_warning(
                "'openclaw' binary not found in PATH — "
                "cannot run 'openclaw plugins install'. "
                "Add OpenClaw to your PATH and re-run setup."
            )
            return False

        # ── Step 1: Link the plugin via OpenClaw CLI ──────────────────────────
        try:
            result = subprocess.run(
                [openclaw_bin, "plugins", "install", "--link", str(plugin_src)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                self.print_warning(
                    f"'openclaw plugins install --link' exited {result.returncode}: "
                    f"{result.stderr.strip() or result.stdout.strip()}"
                )
                return False
            self.print_success(f"Linked plugin: {plugin_src}")
        except subprocess.TimeoutExpired:
            self.print_warning("'openclaw plugins install --link' timed out")
            return False
        except OSError as e:
            self.print_warning(f"Failed to run openclaw CLI: {e}")
            return False

        # ── Step 2: Enable the plugin ─────────────────────────────────────────
        try:
            result = subprocess.run(
                [openclaw_bin, "plugins", "enable", "evermemos-openclaw"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if result.returncode != 0:
                # Non-fatal: plugin may already be enabled, or CLI may not support this command
                self.print_warning(
                    f"'openclaw plugins enable evermemos-openclaw' exited {result.returncode} "
                    f"(may already be enabled): {result.stderr.strip() or result.stdout.strip()}"
                )
            else:
                self.print_success("Enabled plugin: evermemos-openclaw")
        except (subprocess.TimeoutExpired, OSError) as e:
            self.print_warning(f"'openclaw plugins enable' failed: {e} — you may need to enable manually")

        # ── Step 3: Patch ~/.openclaw/openclaw.json with plugin config ───────
        config_path = Path.home() / ".openclaw" / "openclaw.json"

        config: dict = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self.print_warning(f"Could not read {config_path}: {e}, will recreate")
                config = {}

        plugin_id = "evermemos-openclaw"
        user_id = self._read_env_value("MEMORY_USER_ID") or "default_user"
        plugin_config_block = {
            "apiBaseUrl": "http://localhost:1995",
            "userId": user_id,
            "searchTopK": 5,
        }

        plugins = config.setdefault("plugins", {})
        entries = plugins.setdefault("entries", {})

        if plugin_id not in entries:
            entries[plugin_id] = {"enabled": True, "config": plugin_config_block}
            self.print_success(f"Added plugins.entries.{plugin_id} to openclaw.json")
        else:
            entry = entries[plugin_id]
            patched = False
            if not entry.get("enabled"):
                entry["enabled"] = True
                self.print_success(f"Set plugins.entries.{plugin_id}.enabled = true")
                patched = True
            if "config" not in entry:
                entry["config"] = plugin_config_block
                self.print_success(f"Added missing config block to plugins.entries.{plugin_id}")
                patched = True
            else:
                # Always sync userId with .env so re-running install.sh picks up changes
                if entry["config"].get("userId") != user_id:
                    entry["config"]["userId"] = user_id
                    self.print_success(f"Updated plugins.entries.{plugin_id}.config.userId={user_id}")
                    patched = True
            if not patched:
                self.print_info(f"plugins.entries.{plugin_id} already configured, skipping")

        load = plugins.setdefault("load", {})
        paths: list = load.setdefault("paths", [])
        plugin_path = str(plugin_src)
        if plugin_path not in paths:
            paths.append(plugin_path)
            self.print_success(f"Added {plugin_path} to plugins.load.paths")
        else:
            self.print_info("plugins.load.paths already contains plugin path, skipping")

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = config_path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                f.write("\n")
            tmp.replace(config_path)
            self.print_success("Updated ~/.openclaw/openclaw.json")
        except OSError as e:
            self.print_warning(f"Failed to write openclaw.json: {e}")
            self.print_info(
                "Please manually add to ~/.openclaw/openclaw.json:\n"
                f'  "plugins": {{"entries": {{"{plugin_id}": {{"enabled": true, '
                f'"config": {{"apiBaseUrl": "http://localhost:1995", '
                f'"userId": "default_user", "searchTopK": 5}}}}}}}}'
            )
            return False

        self.print_info("Restart the OpenClaw gateway to apply: openclaw gateway restart")
        return True

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
            self.print_info("uv is required for dependency management")

            if non_interactive:
                self.print_info("Non-interactive mode: installing uv automatically...")
                if not self.install_uv():
                    return False
            else:
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

        # Step 5: Install Claude Code integration (if Claude Code is installed)
        if self.is_claude_code_installed():
            if not self.install_claude_hooks():
                self.print_warning(
                    "Claude Code hook installation failed — "
                    "hooks won't auto-record across all projects. "
                    "You can re-run setup to retry."
                )
        else:
            self.print_info(
                "Claude Code not detected ('claude' not in PATH and ~/.claude/ not found), "
                "skipping Claude Code integration."
            )

        # Step 6: Install OpenCode integration (if OpenCode is installed)
        if self.is_opencode_installed():
            if not self.install_opencode_plugin():
                self.print_warning(
                    "OpenCode plugin installation failed — "
                    "you can re-run setup to retry."
                )
        else:
            self.print_info(
                "OpenCode not detected ('opencode' not in PATH, ~/.config/opencode/ and "
                "~/.opencode/bin/opencode not found), skipping OpenCode integration. "
                "Install OpenCode first, then re-run setup to enable it."
            )

        # Step 7: Install OpenClaw integration (if OpenClaw is installed)
        if self.is_openclaw_installed():
            if not self.install_openclaw_plugin():
                self.print_warning(
                    "OpenClaw plugin installation failed — "
                    "you can re-run setup to retry."
                )
        else:
            self.print_info(
                "OpenClaw not detected ('openclaw' not in PATH and ~/.openclaw/ not found), "
                "skipping OpenClaw integration. "
                "Install OpenClaw first, then re-run setup to enable it."
            )

        return True

    def run_hooks_only(self) -> bool:
        """Run only the editor integration steps (Steps 5-7), skipping Docker/deps.

        Used in remote-client mode where Docker is not required.
        """
        self.print_header("EverMemOS Editor Integration (Hooks Only)")

        # Step 5: Install Claude Code integration (if Claude Code is installed)
        if self.is_claude_code_installed():
            if not self.install_claude_hooks():
                self.print_warning(
                    "Claude Code hook installation failed — "
                    "hooks won't auto-record across all projects. "
                    "You can re-run setup to retry."
                )
        else:
            self.print_info(
                "Claude Code not detected ('claude' not in PATH and ~/.claude/ not found), "
                "skipping Claude Code integration."
            )

        # Step 6: Install OpenCode integration (if OpenCode is installed)
        if self.is_opencode_installed():
            if not self.install_opencode_plugin():
                self.print_warning(
                    "OpenCode plugin installation failed — "
                    "you can re-run setup to retry."
                )
        else:
            self.print_info(
                "OpenCode not detected ('opencode' not in PATH, ~/.config/opencode/ and "
                "~/.opencode/bin/opencode not found), skipping OpenCode integration. "
                "Install OpenCode first, then re-run setup to enable it."
            )

        # Step 7: Install OpenClaw integration (if OpenClaw is installed)
        if self.is_openclaw_installed():
            if not self.install_openclaw_plugin():
                self.print_warning(
                    "OpenClaw plugin installation failed — "
                    "you can re-run setup to retry."
                )
        else:
            self.print_info(
                "OpenClaw not detected ('openclaw' not in PATH and ~/.openclaw/ not found), "
                "skipping OpenClaw integration. "
                "Install OpenClaw first, then re-run setup to enable it."
            )

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
    parser.add_argument(
        "--hooks-only",
        action="store_true",
        help="Only install editor integrations (Claude Code / OpenCode / OpenClaw), skip Docker/deps. Used for remote-client mode."
    )

    args = parser.parse_args()

    # Create setup manager
    manager = SetupManager(project_dir=args.project_dir)

    # Run setup
    if args.hooks_only:
        success = manager.run_hooks_only()
    else:
        success = manager.run_setup(non_interactive=args.non_interactive)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

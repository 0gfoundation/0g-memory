#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memsys Bootstrap Script - Generic context loader and script runner

This script allows algorithm colleagues to run any test script without cognitive overhead, automatically handling:
- Python path setup
- Environment variable loading
- Dependency injection container initialization
- Mock mode support

Usage:
    python src/bootstrap.py [your script path] [arguments for your script...]

Examples:
    python src/bootstrap.py tests/algorithms/debug_my_model.py
    python src/bootstrap.py unit_test/memory_manager_single_test.py --verbose
    python src/bootstrap.py evaluation/dynamic_memory_evaluation/locomo_eval.py --dataset small
"""

import sys
import runpy
import argparse
import os
import nest_asyncio

nest_asyncio.apply()
import asyncio
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def file_path_to_module_name(target_path: Path, src_path: Path) -> str:
    """
    Convert file path to module name

    Args:
        target_path: Path to the target script
        src_path: Path to the src directory

    Returns:
        Module name, e.g., "api_layer.get_data.run_consumer"
    """
    # Ensure paths are absolute
    target_path = target_path.resolve()
    src_path = src_path.resolve()

    try:
        # First check if it's under the src directory
        if target_path.is_relative_to(src_path):
            # If under src, calculate relative to src
            relative_path = target_path.relative_to(src_path)
            module_name = (
                str(relative_path.with_suffix('')).replace('/', '.').replace('\\', '.')
            )
            return module_name
        else:
            # If not under src, calculate relative to project root
            project_root = src_path.parent
            relative_path = target_path.relative_to(project_root)
            module_name = (
                str(relative_path.with_suffix('')).replace('/', '.').replace('\\', '.')
            )
            return module_name
    except ValueError:
        # If relative path cannot be calculated, try relative to current directory
        try:
            relative_path = target_path.relative_to(Path.cwd())
            module_name = (
                str(relative_path.with_suffix('')).replace('/', '.').replace('\\', '.')
            )
            return module_name
        except ValueError:
            # Final fallback: use filename as module name
            return target_path.stem


async def setup_project_context(env_file=".env", mock_mode=False, client_only=False):
    """
    Set up project context environment - exactly copy the loading logic from run.py

    Args:
        env_file: Environment file to load
        mock_mode: Enable mock mode
        client_only: Skip all infrastructure initialization (MongoDB/Milvus/ES/ZeroG).
                     Only sets up Python path and loads .env (e.g. API_BASE_URL).
                     Use this when the script only calls the HTTP API (SimpleMemoryManager),
                     not when it needs direct DB access.
    """
    # Set flag to indicate we're running via bootstrap.py (not actual backend startup).
    # This serves two purposes:
    # 1. Prevents startup data sync from running (data_sync_validation_listener checks this
    #    flag and skips auto-sync when True, avoiding unnecessary sync in demo/test scripts).
    # 2. Prevents duplicate initialization in scripts like clear_kv_data.py, which skip
    #    calling setup_project_context() again when invoked via bootstrap.py.
    os.environ["BOOTSTRAP_MODE"] = "true"

    # Copy environment loading logic from run.py
    from import_parent_dir import add_parent_path

    add_parent_path(0)

    from common_utils.load_env import setup_environment

    if client_only:
        # Client-only mode: skip all DB connections.
        # We do NOT call setup_environment() here because it always calls sys.exit(1)
        # when check_env_var=None (the function returns False unless a specific env var
        # is found).  Instead, load .env and .evermemos_remote_secrets directly.
        from dotenv import load_dotenv
        from pathlib import Path as _Path

        project_dir = _Path(__file__).parent.parent  # src/../ = project root
        env_path = project_dir / env_file
        if env_path.exists():
            load_dotenv(env_path)
            logger.info("🌐 Loaded %s", env_path)
        else:
            logger.warning("🌐 %s not found, skipping", env_path)

        # Load .evermemos_remote_secrets (Scenario C credentials: EVERMEMOS_REMOTE_API_KEY)
        # and map to API_KEY so SimpleMemoryManager picks it up automatically.
        remote_secrets_path = project_dir / ".evermemos_remote_secrets"
        if remote_secrets_path.exists():
            load_dotenv(remote_secrets_path, override=False)
            remote_key = os.getenv("EVERMEMOS_REMOTE_API_KEY")
            if remote_key and not os.getenv("API_KEY"):
                os.environ["API_KEY"] = remote_key
            logger.info("🌐 Loaded .evermemos_remote_secrets (API_KEY set)")
        else:
            logger.info("🌐 .evermemos_remote_secrets not found (Scenario A, no auth needed)")

        # If MEMORY_REMOTE_URL is set, use it as API_BASE_URL so SimpleMemoryManager
        # calls the remote server instead of localhost.
        remote_url = os.getenv("MEMORY_REMOTE_URL")
        if remote_url:
            os.environ["API_BASE_URL"] = remote_url
            logger.info("🌐 API_BASE_URL set to MEMORY_REMOTE_URL: %s", remote_url)

        logger.info("🌐 Client-only mode: infrastructure initialization skipped")
        return

    # Set up environment (Python path and .env file)
    setup_environment(load_env_file_name=env_file, check_env_var="MONGODB_HOST")

    # Copy Mock mode check logic from run.py
    from core.di.utils import enable_mock_mode

    # Check if Mock mode is enabled: prioritize command-line argument, then environment variable
    if mock_mode or (
        os.getenv("MOCK_MODE") and os.getenv("MOCK_MODE").lower() == "true"
    ):
        enable_mock_mode()
        logger.info("🚀 Mock mode enabled")
    else:
        logger.info("🚀 Mock mode disabled")

    # Copy dependency injection setup from run.py
    from application_startup import setup_all

    # Execute dependency injection and async task setup at module load time
    setup_all()

    # Asynchronously start application lifespan
    try:
        from app import app

        if hasattr(app, "start_lifespan"):
            await app.start_lifespan()
            logger.info("✅ Application lifespan started successfully")
        else:
            logger.warning("⚠️ app instance has no start_lifespan method")
    except Exception as e:
        logger.warning(f"⚠️ Error starting application lifespan: {e}")
        # Do not raise exception, continue execution


async def async_main():
    """Async main function: parse arguments and run target script"""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Run Python script within full application context",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  python src/bootstrap.py tests/algorithms/debug_my_model.py
  python src/bootstrap.py unit_test/memory_manager_single_test.py --verbose
  python src/bootstrap.py evaluation/dynamic_memory_evaluation/locomo_eval.py --dataset small
  
Environment variables:
  MOCK_MODE=true    Enable Mock mode (for testing)
        """,
    )

    parser.add_argument("script_path", help="Path to the Python script to run")
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="Specify environment variable file to load (default: .env)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Enable Mock mode (for testing and development)",
    )
    parser.add_argument(
        "--client-only",
        action="store_true",
        help=(
            "Client-only mode: skip all infrastructure initialization (MongoDB/Milvus/ES/ZeroG). "
            "Use this when connecting to a remote API server (Scenario C). "
            "Set API_BASE_URL in .env to point to the remote server."
        ),
    )

    # Use parse_known_args so that flags like --client-only are correctly recognised
    # even when they appear after script_path.  Unknown args are passed to the target script.
    args, script_args = parser.parse_known_args()
    args.script_args = script_args

    print("🚀 Memsys Bootstrap Script")
    print("=" * 50)
    print(f"📄 Target script: {args.script_path}")
    print(f"📝 Script arguments: {args.script_args}")
    print(f"📄 Env File: {args.env_file}")
    print(f"🎭 Mock mode: {'Enabled' if args.mock else 'Disabled'}")
    print(f"🌐 Client-only mode: {'Enabled' if args.client_only else 'Disabled'}")
    print("=" * 50)

    # Set up project context (exactly copy logic from run.py)
    await setup_project_context(
        env_file=args.env_file,
        mock_mode=args.mock,
        client_only=args.client_only,
    )

    # Verify target script exists
    script_path = Path(args.script_path)
    if not script_path.exists():
        print(
            f"❌ Error: Script file does not exist: {args.script_path}", file=sys.stderr
        )
        sys.exit(1)

    # Prepare to execute target script
    # Key: modify sys.argv so the target script thinks it was called directly
    # This allows it to correctly receive its own arguments
    original_argv = sys.argv.copy()  # Backup original arguments
    sys.argv = [str(script_path)] + args.script_args

    print(f"\n🎬 Starting script execution: {args.script_path}")
    print("-" * 50)

    try:
        # Use runpy to execute target script
        # run_path executes the script as if 'python script_path' was called
        # run_name="__main__" ensures if __name__ == "__main__": block executes normally
        runpy.run_path(str(script_path), run_name="__main__")

    except ImportError as e:
        # If relative import error occurs, try running in module mode
        if "attempted relative import with no known parent package" in str(e):
            print(
                f"\n⚠️  Detected relative import error, trying to run in module mode..."
            )
            try:
                # Get src directory path
                src_path = Path(__file__).parent  # bootstrap.py is in src directory
                module_name = file_path_to_module_name(script_path, src_path)
                print(
                    f"📦 Interpreting path '{script_path}' as module '{module_name}', retrying..."
                )

                # Ensure script's sys.argv[0] remains the file path
                sys.argv[0] = str(script_path)
                runpy.run_module(module_name, run_name="__main__")

            except Exception as module_error:
                print(
                    f"\n❌ Module mode execution also failed: {module_error}",
                    file=sys.stderr,
                )
                print(f"Original error: {e}", file=sys.stderr)
                import traceback

                traceback.print_exc()
                sys.exit(1)
        else:
            # For other import errors, raise directly
            raise

    except SystemExit as e:
        # Target script may call sys.exit(), which is normal
        # Only propagate non-zero exit codes to avoid unnecessary stack traces
        if e.code is not None and e.code != 0:
            print(f"\n📋 Script exited with code: {e.code}")
            raise  # Re-raise to propagate the exit code
        else:
            print(f"\n📋 Script execution completed successfully")
    except Exception as e:
        print(f"\n❌ Script execution error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
    finally:
        # Restore original sys.argv
        sys.argv = original_argv
        print(f"\n🏁 Script execution finished: {args.script_path}")


def main():
    """Synchronous main entry point"""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n⚠️ User interrupted execution")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Execution failed: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()

"""CLI entry point for `signoff-mcp init`."""

import sys
from pathlib import Path

# Add root directory to sys.path if needed
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import init


def main() -> int:
    # If invoked as `signoff-mcp init ...`, strip the `init` subcommand from sys.argv
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        sys.argv.pop(1)
    return init.main()


if __name__ == "__main__":
    sys.exit(main())

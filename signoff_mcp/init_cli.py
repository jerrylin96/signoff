"""CLI entry point for `signoff-mcp init`."""

import sys
from signoff_mcp import init


def main() -> int:
    # If invoked as `signoff-mcp init ...`, strip the `init` subcommand from sys.argv
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        sys.argv.pop(1)
    return init.main()


if __name__ == "__main__":
    sys.exit(main())

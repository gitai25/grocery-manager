#!/usr/bin/env python3
"""Entry point scripts for Grocery Manager."""

import sys


def run_cli():
    """Run the CLI application."""
    from src.cli import main
    main()


def run_api():
    """Run the FastAPI server."""
    import uvicorn
    uvicorn.run("src.main:app", host="0.0.0.0", port=8000, reload=True)


def init_db():
    """Initialize the database."""
    import asyncio
    from src.core.database import init_db as _init_db

    asyncio.run(_init_db())
    print("Database initialized!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run.py [cli|api|init]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "cli":
        run_cli()
    elif command == "api":
        run_api()
    elif command == "init":
        init_db()
    else:
        print(f"Unknown command: {command}")
        print("Available commands: cli, api, init")
        sys.exit(1)

"""Setup script for Grocery Manager."""

from setuptools import setup, find_packages

setup(
    name="grocery-manager",
    version="0.1.0",
    description="Singapore Daily Essentials & Food Procurement Management System",
    author="AI2025",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "pydantic>=2.5.0",
        "pydantic-settings>=2.1.0",
        "sqlalchemy>=2.0.25",
        "aiosqlite>=0.19.0",
        "httpx>=0.26.0",
        "playwright>=1.41.0",
        "beautifulsoup4>=4.12.0",
        "apscheduler>=3.10.0",
        "click>=8.1.0",
        "rich>=13.7.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0.0",
    ],
    entry_points={
        "console_scripts": [
            "grocery-manager=src.cli:main",
        ],
    },
)

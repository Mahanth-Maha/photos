import os
import subprocess
from datetime import datetime

def run(cmd, cwd=None):
    print(f"> {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd)
    if result.returncode != 0:
        raise SystemExit(f"❌ Command failed: {cmd}")
try:
    import dotenv 
except ImportError:
    os.subprocess.run("pip install python-dotenv", shell=True)
    import dotenv

dotenv.load_dotenv()

# === Config entries (can also set via environment variables if preferred) ===
# REPO_URL = "https://github.com/Mahanth-Maha/photos.git"
# TARGET_BRANCH = "gh-pages"
# PUBLIC_DIR = "public"
# PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

REPO_URL = os.getenv("REPO_URL", "https://github.com/Mahanth-Maha/photos.git")
TARGET_BRANCH = os.getenv("TARGET_BRANCH", "gh-pages")
PUBLIC_DIR = os.getenv("PUBLIC_DIR", "public")
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 1. Commit any changes in main project to prevent checkout errors
print("💾 Committing local changes in the main project directory...")
run("git add .", cwd=PROJECT_ROOT)
try:
    run('git commit -m "chore: save local changes before deploy"', cwd=PROJECT_ROOT)
except SystemExit:
    # No changes to commit; safe to continue
    print("No local changes to commit.")

# 2. Build the Hugo site
print("🚀 Building Hugo site...")
run("hugo --minify", cwd=PROJECT_ROOT)

# 3. In public/, init git if missing and push to gh-pages branch
print(f"📁 Deploying contents of {PUBLIC_DIR} to branch {TARGET_BRANCH}...")

public_path = os.path.join(PROJECT_ROOT, PUBLIC_DIR)

if not os.path.exists(os.path.join(public_path, ".git")):
    print("Initializing git repo in public/ folder...")
    run("git init", cwd=public_path)
    run(f"git remote add origin {REPO_URL}", cwd=public_path)
else:
    print("Git repo already exists in public/.")

# Switch to (or create) the gh-pages branch
run(f"git checkout -B {TARGET_BRANCH}", cwd=public_path)

# Add all files and commit changes
run("git add .", cwd=public_path)
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
try:
    run(f'git commit -m "🚀 Deploy Pictures [{timestamp}]"', cwd=public_path)
except SystemExit:
    # No changes to commit; safe to continue
    print("No changes to commit in public/.")

# Force push the gh-pages branch to origin
run(f"git push -f origin {TARGET_BRANCH}", cwd=public_path)

print("✅ Deployment successful!")

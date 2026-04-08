from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import subprocess
import os
from datetime import datetime, timedelta

# --- Domain Models ---
class ReportResponse(BaseModel):
    content: str
    date: str

class CommitLog:
    def __init__(self, message: str, date: str = "", repo_name: str = ""):
        self.message = message
        self.date = date
        self.repo_name = repo_name

# --- Services ---
class GitService:
    """Handles all Git operations"""
    def __init__(self, repo_path: str):
        self.repo_path = repo_path

    def get_git_username(self) -> str:
        try:
            result = subprocess.run(
                ['git', 'config', 'user.name'],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except Exception:
            # Fallback if config is missing
            return ""

    def get_commits_by_range(self, since_date: str, until_date: str, display_name: str = "") -> list[CommitLog]:
        """Fetch commits for a specific date range."""
        author = self.get_git_username()
        # Using format: %ad for date, %s for subject
        cmd = [
            'git', 'log',
            '--all',
            '--pretty=format:%as|%s',
            '--no-merges',
            f'--since={since_date} 00:00:00',
            f'--until={until_date} 23:59:59'
        ]
        
        if author:
            cmd.append(f'--author={author}')
            
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            lines = result.stdout.split('\n')
            # Use a list for deduplication by (date, message) content
            unique_commits = []
            seen = set()
            for line in lines:
                if '|' not in line:
                    continue
                commit_date, msg = line.strip().split('|', 1)
                key = (commit_date, msg)
                if msg and key not in seen:
                    unique_commits.append(CommitLog(message=msg, date=commit_date, repo_name=display_name))
                    seen.add(key)
            
            return unique_commits
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git execution failed: {e.stderr}")
        except Exception as e:
            raise RuntimeError(f"Error accessing Git logs: {str(e)}")

class ReportService:
    """Handles report generation logic"""
    @staticmethod
    def generate_daily_report(date: str, commits: list[CommitLog], is_multi_day: bool = False) -> str:
        if not commits:
            return ""
        
        # Group by Date, then by Repo
        grouped = {}
        for commit in commits:
            d = commit.date
            if d not in grouped:
                grouped[d] = {}
            
            repo = commit.repo_name or "Other"
            if repo not in grouped[d]:
                grouped[d][repo] = []
            grouped[d][repo].append(commit.message)
            
        # Sort dates descending
        sorted_dates = sorted(grouped.keys(), reverse=True)
        
        content = ""
        for d in sorted_dates:
            if is_multi_day:
                # Format to "3月13日："
                try:
                    dt = datetime.strptime(d, "%Y-%m-%d")
                    date_header = dt.strftime("%-m月%-d日")
                    content += f"{date_header}：\n"
                except:
                    content += f"{d}：\n"
            
            for repo_name, messages in grouped[d].items():
                content += f"{repo_name}：\n"
                for idx, msg in enumerate(messages, start=1):
                    content += f"{idx}. {msg}\n"
            
            if is_multi_day:
                content += "\n" # Spacing between days
                
        return content.strip()

# --- FastAPI App ---
app = FastAPI(title="Daily Report Generator API")

# Add CORS Middleware to ensure Vue frontend can safely request it
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurable paths for the repositories on the user's desktop
REPO_PATHS = [
    os.path.expanduser("~/Desktop/x-mom-pc"),
    os.path.expanduser("~/Desktop/shxg-web"),
]

@app.get("/api/daily_report", response_model=ReportResponse, summary="Retrieve Git commits and generate daily report")
def get_daily_report(
    date: str = Query(..., description="Target date in YYYY-MM-DD format"),
    days: int = Query(1, description="Number of days to summarize")
):
    """
    Generate a daily report by fetching git commits from multiple repositories for a specific period.
    """
    all_commits = []
    found_any_repo = False
    
    try:
        until_dt = datetime.strptime(date, "%Y-%m-%d")
        since_dt = until_dt - timedelta(days=days-1)
        since_date = since_dt.strftime("%Y-%m-%d")
        until_date = until_dt.strftime("%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    for repo_path in REPO_PATHS:
        if os.path.exists(repo_path):
            found_any_repo = True
            # Extract a simple name from the path (e.g., 'mes-pc' or 'shxg-web')
            display_name = os.path.basename(repo_path).replace("-pc", "").replace("-web", "")
            
            git_service = GitService(repo_path=repo_path)
            try:
                repo_commits = git_service.get_commits_by_range(since_date, until_date, display_name=display_name)
                all_commits.extend(repo_commits)
            except Exception as e:
                # Log or skip if one repo fails
                print(f"Warning: Failed to fetch commits for {repo_path}: {e}")
                continue

    if not found_any_repo:
        raise HTTPException(
            status_code=500, 
            detail=f"None of the configured repositories were found on the Desktop."
        )

    # Generate content from aggregated commits
    report_content = ReportService.generate_daily_report(date, all_commits, is_multi_day=(days > 1))
    
    return ReportResponse(content=report_content, date=date)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

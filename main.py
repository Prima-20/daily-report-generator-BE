from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import subprocess
import os

# --- Domain Models ---
class ReportResponse(BaseModel):
    content: str
    date: str

class CommitLog:
    def __init__(self, message: str):
        self.message = message

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

    def get_commits_by_date(self, target_date: str) -> list[CommitLog]:
        """Fetch commits for a specific date."""
        author = self.get_git_username()
        # Using format: %s to only get commit subject
        cmd = [
            'git', 'log',
            '--pretty=format:%s',
            '--no-merges',
            f'--since={target_date} 00:00:00',
            f'--until={target_date} 23:59:59'
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
            return [CommitLog(message=line.strip()) for line in lines if line.strip()]
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Git execution failed: {e.stderr}")
        except Exception as e:
            raise RuntimeError(f"Error accessing Git logs: {str(e)}")

class ReportService:
    """Handles report generation logic"""
    @staticmethod
    def generate_daily_report(date: str, commits: list[CommitLog]) -> str:
        content = f"【工作日报】\n日期：{date}\n\n"
        
        content += "一、今日完成工作：\n"
        if not commits:
            content += "1. 按计划推进相关研发工作。\n"
        else:
            for idx, commit in enumerate(commits, start=1):
                content += f"{idx}. {commit.message}\n"
                
        content += "\n二、遇到的问题与解决方案：\n"
        content += "暂无阻塞性问题。\n"
        
        content += "\n三、明日工作计划：\n"
        content += "1. 继续推进相关模块研发联调工作\n"
        content += "2. 根据排期完成既定任务\n"
        
        content += "\n四、其他：\n"
        content += "无\n"
        
        return content

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

# Path to the MES-PC repository on the user's desktop
MES_PC_REPO_PATH = os.path.expanduser("~/Desktop/mes-pc")

@app.get("/api/daily_report", response_model=ReportResponse, summary="Retrieve Git commits and generate daily report")
def get_daily_report(date: str = Query(..., description="Target date in YYYY-MM-DD format")):
    """
    Generate a daily report by fetching git commits for the specific date.
    """
    if not os.path.exists(MES_PC_REPO_PATH):
        raise HTTPException(
            status_code=500, 
            detail=f"Repository not found at {MES_PC_REPO_PATH}. Please check the path."
        )

    git_service = GitService(repo_path=MES_PC_REPO_PATH)
    try:
        commits = git_service.get_commits_by_date(date)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    report_content = ReportService.generate_daily_report(date, commits)
    
    return ReportResponse(content=report_content, date=date)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

from pydantic import BaseModel
from typing import Optional, Dict

class JobInfo(BaseModel):
    job_id: str
    priority: str
    created_at: str
    user_name: str
    team_name: str
    status: str
    gpu_type: Optional[str] = None
    waiting_time: Optional[int] = None  # 대기 시간(초)

class WorkloadInfo(BaseModel):
    name: str
    namespace: str
    priority: int  # 숫자 우선순위 (예: 100, 200, 300)
    created_at: str
    resource_requests: Dict[str, str]  # 리소스 요구량 (예: {"example.com/gpu": "2"})
    labels: Optional[Dict[str, str]] = None
    annotations: Optional[Dict[str, str]] = None
    user_name: Optional[str] = None
    team_name: Optional[str] = None



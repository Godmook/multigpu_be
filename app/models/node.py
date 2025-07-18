from pydantic import BaseModel
from typing import List, Optional

class GPUInfo(BaseModel):
    uuid: str
    nvidia: str
    unique_id: str
    allocation: int  # 할당률(1~100)
    source: Optional[str] = "unknown"  # 정보 출처 (hami.io, node_status)
    pods: Optional[List[str]] = []  # 해당 GPU를 사용하는 Pod 이름 목록
    user_names: Optional[List[str]] = []  # 사용자 이름 목록
    team_names: Optional[List[str]] = []  # 팀 이름 목록

class NodeInfo(BaseModel):
    name: str
    gpu_type: str
    gpus: List[GPUInfo]



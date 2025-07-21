from fastapi import APIRouter, HTTPException
from app.services.job_manager import JobManager

router = APIRouter()

@router.get("/pending/", response_model=dict)
def get_pending_jobs():
    """
    Admit되지 않은 Job 목록 조회
    
    K8S에서 suspend=True 상태이거나 admit되지 않은 Job들을 조회합니다.
    
    **반환 데이터:**
    - `pending_jobs`: 대기중인 Job 목록
        - `job_id`: Job ID
        - `priority`: 우선순위 (Urgent, Normal 등)
        - `created_at`: 생성시간
        - `user_name`: 사용자 이름
        - `team_name`: 팀 이름
        - `status`: Job 상태
        - `gpu_type`: GPU 타입
        - `waiting_time`: 대기 시간(초)
    
    **예시 응답:**
    ```json
    {
      "pending_jobs": [
        {
          "job_id": "ml-training-job-001",
          "priority": "Urgent",
          "created_at": "2024-01-15T10:30:00Z",
          "user_name": "alice",
          "team_name": "ml-team",
          "status": "Pending",
          "gpu_type": "H100",
          "waiting_time": 3600
        }
      ]
    }
    ```
    """
    jm = JobManager()
    return {"pending_jobs": [j.dict() for j in jm.get_pending_jobs()]}

@router.get("/pending-workloads/", response_model=dict)
def get_pending_workloads():
    """
    Kueue에서 pending 상태의 Workload를 priority 내림차순, queue name별로 그룹핑해서 반환
    user_name, team_name은 example.com/member, example.com/team에서 추출
    """
    jm = JobManager()
    grouped = jm.get_pending_workloads()
    # queue별로 priority 내림차순 리스트 반환
    return {"pending_workloads": grouped}

@router.patch("/{job_id}/priority/", response_model=dict)
def update_job_priority(job_id: str, priority: str):
    """
    Job 우선순위 변경
    
    **매개변수:**
    - `job_id`: Job ID
    - `priority`: 새로운 우선순위 (Urgent, Normal 등)
    
    **반환 데이터:**
    - `job_id`: Job ID
    - `new_priority`: 변경된 우선순위
    
    **예시:**
    - `job_id`: ml-training-job-001
    - `priority`: Urgent
    """
    jm = JobManager()
    ok = jm.update_priority(job_id, priority)
    if not ok:
        raise HTTPException(500, "Priority update failed")
    return {"job_id": job_id, "new_priority": priority}

@router.get("/gpu-type/{gpu_type}/", response_model=dict)
def get_jobs_by_gpu_type(gpu_type: str):
    """
    특정 GPU 타입을 사용하는 노드/Job 통합 정보 조회
    
    **매개변수:**
    - `gpu_type`: GPU 타입 (H100, A100, RTX4090 등)
    
    **반환 데이터:**
    - `jobs`: 해당 GPU 타입을 사용하는 Job 목록
    
    **예시:**
    - `gpu_type`: H100
    """
    jm = JobManager()
    return {"jobs": jm.get_jobs_by_gpu_type(gpu_type)}

@router.delete("/{job_id}/", response_model=dict)
def delete_job(job_id: str, namespace: str = "default"):
    """
    Job 삭제
    
    **매개변수:**
    - `job_id`: Job ID
    - `namespace`: 네임스페이스 (기본값: default)
    
    **반환 데이터:**
    - `deleted`: 삭제 성공 여부
    - `job_id`: 삭제된 Job ID
    
    **예시:**
    - `job_id`: ml-training-job-001
    - `namespace`: default
    """
    jm = JobManager()
    try:
        success = jm.delete_job(job_id, namespace)
        if success:
            return {"deleted": True, "job_id": job_id}
        else:
            raise HTTPException(status_code=404, detail="Job not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

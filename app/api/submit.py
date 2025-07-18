from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.job_manager import JobManager, JobCreateRequest

router = APIRouter()

@router.post("/submit/", response_model=dict)
def submit_job(req: JobCreateRequest):
    """
    Job 제출 (Pydantic 모델 기반)
    
    Pydantic 모델을 사용하여 Job을 생성하고 K8S에 제출합니다.
    
    **요청 데이터:**
    - `name`: Job 이름 (선택사항, 자동 생성)
    - `namespace`: 네임스페이스 (기본값: default)
    - `gpu_count`: GPU 개수
    - `cpu_pct`: CPU 사용률 (%)
    - `mem_pct`: 메모리 사용률 (%)
    - `gpu_pct`: GPU 사용률 (%)
    - `user_name`: 사용자 이름
    - `team_name`: 팀 이름
    - `priority`: 우선순위 (Urgent, Normal)
    - `gpu_type`: GPU 타입 (선택사항)
    - `gang_scheduling`: Gang 스케줄링 사용 여부
    - `gang_count`: Gang 개수
    - `gang_id`: Gang ID
    
    **반환 데이터:**
    - `submitted`: 제출 성공 여부
    - `job_name`: 생성된 Job 이름
    
    **예시 요청:**
    ```json
    {
      "namespace": "default",
      "gpu_count": 2,
      "cpu_pct": 100,
      "mem_pct": 100,
      "gpu_pct": 100,
      "user_name": "alice",
      "team_name": "ml-team",
      "priority": "Urgent",
      "gpu_type": "H100",
      "gang_scheduling": true,
      "gang_count": 2,
      "gang_id": "my-gang"
    }
    ```
    
    **예시 응답:**
    ```json
    {
      "submitted": true,
      "job_name": "job-20240115120000-1234"
    }
    ```
    """
    jm = JobManager()
    try:
        job_name = jm.submit_job(req)
        return {"submitted": True, "job_name": job_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/submit-native/", response_model=dict)
def submit_native_job(job_manifest: dict):
    """
    Job 제출 (K8S Native manifest 기반)
    
    K8S Native Job manifest를 직접 받아서 생성하고 제출합니다.
    
    **요청 데이터:**
    - `job_manifest`: K8S Job manifest (딕셔너리 형태)
    
    **반환 데이터:**
    - `submitted`: 제출 성공 여부
    - `job_name`: 생성된 Job 이름
    
    **예시 요청:**
    ```json
    {
      "apiVersion": "batch/v1",
      "kind": "Job",
      "metadata": {
        "name": "my-job",
        "namespace": "default",
        "labels": {
          "app": "ml-training",
          "priority": "Urgent"
        },
        "annotations": {
          "user_name": "alice",
          "team_name": "ml-team"
        }
      },
      "spec": {
        "suspend": true,
        "template": {
          "spec": {
            "containers": [
              {
                "name": "main",
                "image": "nvidia/cuda:11.8-base",
                "resources": {
                  "requests": {
                    "example.com/gpu": "2"
                  }
                }
              }
            ]
          }
        }
      }
    }
    ```
    
    **예시 응답:**
    ```json
    {
      "submitted": true,
      "job_name": "my-job"
    }
    ```
    """
    jm = JobManager()
    try:
        job_name = jm.submit_native_job(job_manifest)
        return {"submitted": True, "job_name": job_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

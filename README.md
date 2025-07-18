# GPU_New_BE

쿠버네티스(K8S) 기반 GPU 리소스 관리/모니터링/제어 백엔드

## 주요 기능
- 노드 및 GPU 정보 조회 (violet-그래픽카드이름-001~0xx 패턴 필터링)
- Pod별 GPU 사용 현황 파악
- Kueue Workloads pending 상태 조회
- Admit되지 않은 Job 조회 및 우선순위 변경
- 그래픽카드별 노드/Job 통합 정보 제공
- Job 제출 기능 (Pydantic 모델 + K8S Native manifest)
- Job 삭제 기능

## 환경변수 설정
```bash
# K8S kubeconfig 경로 (선택사항)
export KUBECONFIG=/path/to/your/kubeconfig

# GPU 리소스 prefix 설정
# 테스트 환경: example.com
# 프로덕션 환경: nvidia.com
export GPU_RESOURCE_PREFIX=example.com

# CORS 설정
# 개발 환경: 모든 도메인 허용
export CORS_ORIGINS="*"

# 프로덕션 환경: 특정 도메인만 허용
export CORS_ORIGINS="https://your-frontend.com,https://admin.your-frontend.com"

# CORS credentials 허용 여부
export CORS_ALLOW_CREDENTIALS=true
```

## 프로젝트 구조
```
app/
  main.py                # FastAPI 엔트리포인트
  api/
    nodes.py             # Node/GPU 관련 API
    jobs.py              # Job/Workload 관련 API
    submit.py            # Job 제출 관련 API
  services/
    k8s_client.py        # 쿠버네티스 API 연동
    gpu_parser.py        # GPU 정보 파싱
    job_manager.py       # Job 관리/제어
  models/
    node.py              # Node/GPU 데이터 모델
    job.py               # Job/Workload 데이터 모델
    user.py              # 사용자/팀 데이터 모델
  config.py              # 환경설정
requirements.txt
README.md
```

## 실행 방법
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## API 문서
서버 실행 후 다음 URL에서 API 문서를 확인할 수 있습니다:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Swagger UI 특징
- 🎯 **인터랙티브 API 문서** - 브라우저에서 직접 API 테스트 가능
- 📝 **상세한 매개변수 설명** - 각 API의 요청/응답 구조 명시
- 💡 **예시 요청/응답** - 실제 사용 예시 제공
- 🔍 **API 그룹별 분류** - Nodes, Jobs, Submit 카테고리로 정리
- 🚀 **Try it out 기능** - 실제 API 호출 테스트 가능

## API 예시
- GET /nodes/ (violet-그래픽카드이름-001~0xx 패턴만)
- GET /nodes/{node_name}/gpus/
- GET /jobs/pending/ (Admit되지 않은 Job)
- GET /jobs/pending-workloads/ (Kueue pending Workloads)
- PATCH /jobs/{job_id}/priority/
- POST /jobs/submit/ (Pydantic 모델 기반)
- POST /jobs/submit-native/ (K8S Native manifest 기반)
- DELETE /jobs/{job_id}/

## Kueue Workloads 지원
- pending 상태 Workload 조회
- 우선순위 (숫자), 생성시간, 리소스 요구량 정보 제공
- 사용자/팀 정보 (annotation 기반)
- GPU 리소스 prefix 환경변수 지원 (example.com/gpu ↔ nvidia.com/gpu)

## CORS 설정
- 프론트엔드에서 API 호출 가능
- 환경변수로 허용 도메인 제어
- 개발/프로덕션 환경별 설정 분리

## WorkloadInfo 응답 예시
```json
{
  "pending_workloads": [
    {
      "name": "ml-training-workload",
      "namespace": "default",
      "priority": 100,  // 숫자 우선순위
      "created_at": "2024-01-15T10:30:00Z",
      "resource_requests": {
        "example.com/gpu": "2"
      },
      "user_name": "alice",
      "team_name": "ml-team"
    }
  ]
}
```



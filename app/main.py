from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import nodes, jobs, submit
from app.config import CORS_ORIGINS, CORS_ALLOW_CREDENTIALS

app = FastAPI(
    title="K8S GPU Backend API",
    description="""
    쿠버네티스(K8S) 기반 GPU 리소스 관리/모니터링/제어 백엔드 API
    
    ## 주요 기능
    * 🖥️ **노드 및 GPU 정보 조회** - violet-그래픽카드이름-001~0xx 패턴 필터링
    * 📊 **Pod별 GPU 사용 현황** - 실시간 GPU 할당률 및 사용자 정보
    * ⏳ **Kueue Workloads 관리** - pending 상태 Workload 조회 및 우선순위 관리
    * 🚀 **Job 제출 및 관리** - Pydantic 모델 + K8S Native manifest 지원
    * 🗑️ **Job 삭제** - 완료된 Job 정리
    
    ## 환경변수 설정
    ```bash
    export KUBECONFIG=/path/to/your/kubeconfig
    export GPU_RESOURCE_PREFIX=example.com  # 또는 nvidia.com
    export CORS_ORIGINS="*"
    ```
    
    ## API 그룹
    * **Nodes** - 노드 및 GPU 정보 관련 API
    * **Jobs** - Job 및 Workload 관리 API  
    * **Submit** - Job 제출 관련 API
    """,
    version="1.0.0",
    contact={
        "name": "K8S GPU Backend Team",
        "email": "admin@example.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,  # 환경변수에서 허용 도메인 가져오기
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

# 노드/GPU 관련 API
app.include_router(nodes.router, prefix="/nodes", tags=["Nodes"])
# Job/Workload 관련 API
app.include_router(jobs.router, prefix="/jobs", tags=["Jobs"])
# Job 제출 관련 API
app.include_router(submit.router, prefix="/jobs", tags=["Submit"])

@app.get("/", tags=["Root"])
def root():
    """
    API 루트 엔드포인트
    
    API 상태 확인 및 기본 정보를 반환합니다.
    """
    return {
        "message": "K8S GPU Backend API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }

@app.get("/health", tags=["Health"])
def health_check():
    """
    헬스 체크 엔드포인트
    
    API 서버의 상태를 확인합니다.
    """
    return {"status": "healthy", "timestamp": "2024-01-15T12:00:00Z"}



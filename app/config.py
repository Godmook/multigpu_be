import os
from dotenv import load_dotenv

load_dotenv()

KUBECONFIG = os.getenv("KUBECONFIG", None)  # K8S kubeconfig 경로
GPU_RESOURCE_PREFIX = os.getenv("GPU_RESOURCE_PREFIX", "example.com")  # GPU 리소스 prefix (example.com 또는 nvidia.com)

# CORS 설정
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")  # 쉼표로 구분된 허용 도메인 목록
CORS_ALLOW_CREDENTIALS = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"



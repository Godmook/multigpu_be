from fastapi import APIRouter, HTTPException
from app.services.k8s_client import K8SClient
from app.services.gpu_parser import GPUParser
from app.models.node import NodeInfo, GPUInfo
from app.config import KUBECONFIG

router = APIRouter()

@router.get("/", response_model=dict)
def get_nodes():
    """
    모든 노드 및 GPU 정보 조회
    
    violet-그래픽카드이름-001~0xx 패턴에 맞는 노드만 필터링하여 반환합니다.
    hami.io annotation이 없어도 노드 상태에서 GPU 정보를 종합적으로 조회합니다.
    
    **반환 데이터:**
    - `nodes`: 노드 목록
        - `name`: 노드 이름 (예: violet-h100-023)
        - `gpu_type`: GPU 타입 (예: H100, A100)
        - `gpu_count`: GPU 개수
        - `status`: 노드 상태 (Active, Available, Error)
        - `gpus`: GPU 정보 목록
            - `uuid`: GPU UUID
            - `nvidia`: GPU 타입
            - `unique_id`: 고유 ID
            - `allocation`: 할당률 (1~100)
            - `source`: 정보 출처 (hami.io, node_status)
            - `pods`: 해당 GPU를 사용하는 Pod 목록
            - `user_names`: 사용자 이름 목록
            - `team_names`: 팀 이름 목록
    
    **예시 응답:**
    ```json
    {
      "nodes": [
        {
          "name": "violet-h100-023",
          "gpu_type": "H100",
          "gpu_count": 8,
          "status": "Active",
          "gpus": [
            {
              "uuid": "GPU-UUID-123",
              "nvidia": "H100",
              "unique_id": "GPU-UUID-123",
              "allocation": 80,
              "source": "hami.io",
              "pods": ["pod-1", "pod-2"],
              "user_names": ["alice", "bob"],
              "team_names": ["ml-team", "ai-team"]
            }
          ]
        }
      ]
    }
    ```
    """
    k8s = K8SClient(KUBECONFIG)
    nodes = k8s.list_nodes().items
    result = []
    
    for node in nodes:
        name = node.metadata.name
        # violet-그래픽카드이름-001~0xx 패턴에 맞는 노드만 필터링
        if not GPUParser.is_valid_node_name(name):
            continue
            
        # 종합적인 GPU 정보 조회
        gpu_info = k8s.get_node_gpu_info(name)
        
        # GPU 상세 정보를 GPUInfo 모델로 변환
        gpus = []
        for gpu_detail in gpu_info['gpu_details']:
            gpu = GPUInfo(
                uuid=gpu_detail['uuid'],
                nvidia=gpu_info['gpu_type'],
                unique_id=gpu_detail['uuid'],
                allocation=gpu_detail['allocation'],
                source=gpu_detail['source']
            )
            gpus.append(gpu)
        
        node_info = NodeInfo(
            name=name,
            gpu_type=gpu_info['gpu_type'],
            gpus=gpus
        )
        
        # 추가 정보 포함
        node_dict = node_info.dict()
        node_dict['gpu_count'] = gpu_info['gpu_count']
        node_dict['status'] = gpu_info['status']
        
        if 'error' in gpu_info:
            node_dict['error'] = gpu_info['error']
        
        result.append(node_dict)
    
    return {"nodes": result}

@router.get("/{node_name}/gpus/", response_model=dict)
def get_node_gpus(node_name: str):
    """
    특정 노드의 GPU 상세 정보 조회
    
    **매개변수:**
    - `node_name`: 노드 이름 (violet-그래픽카드이름-001~0xx 패턴)
    
    **반환 데이터:**
    - `node`: 노드 이름
    - `gpu_type`: GPU 타입
    - `gpu_count`: GPU 개수
    - `status`: 노드 상태
    - `gpus`: GPU 정보 목록
    
    **예시:**
    - `node_name`: violet-h100-023
    """
    # 노드 이름 패턴 검증
    if not GPUParser.is_valid_node_name(node_name):
        raise HTTPException(400, "Invalid node name pattern. Expected: violet-그래픽카드이름-001~0xx")
    
    k8s = K8SClient(KUBECONFIG)
    gpu_info = k8s.get_node_gpu_info(node_name)
    
    if gpu_info['status'] == 'Error':
        raise HTTPException(404, f"Node not found or error: {gpu_info.get('error', 'Unknown error')}")
    
    # GPU 상세 정보를 GPUInfo 모델로 변환
    gpus = []
    for gpu_detail in gpu_info['gpu_details']:
        gpu = GPUInfo(
            uuid=gpu_detail['uuid'],
            nvidia=gpu_info['gpu_type'],
            unique_id=gpu_detail['uuid'],
            allocation=gpu_detail['allocation'],
            source=gpu_detail['source']
        )
        gpus.append(gpu)
    
    return {
        "node": node_name,
        "gpu_type": gpu_info['gpu_type'],
        "gpu_count": gpu_info['gpu_count'],
        "status": gpu_info['status'],
        "gpus": [g.dict() for g in gpus]
    }

@router.get("/{node_name}/gpus/{gpu_uuid}/pods/", response_model=dict)
def get_gpu_pods(node_name: str, gpu_uuid: str):
    """
    특정 GPU를 사용하는 Pod 정보 조회
    
    **매개변수:**
    - `node_name`: 노드 이름 (violet-그래픽카드이름-001~0xx 패턴)
    - `gpu_uuid`: GPU UUID
    
    **반환 데이터:**
    - `node`: 노드 이름
    - `gpu_uuid`: GPU UUID
    - `pods`: Pod 정보 목록
        - `pod_name`: Pod 이름
        - `namespace`: 네임스페이스
        - `allocation`: GPU 할당률
        - `user_name`: 사용자 이름
        - `team_name`: 팀 이름
    
    **예시:**
    - `node_name`: violet-h100-023
    - `gpu_uuid`: GPU-UUID-123
    """
    # 노드 이름 패턴 검증
    if not GPUParser.is_valid_node_name(node_name):
        raise HTTPException(400, "Invalid node name pattern. Expected: violet-그래픽카드이름-001~0xx")
    
    k8s = K8SClient(KUBECONFIG)
    pods = k8s.list_pods(node_name=node_name).items
    result = []
    for pod in pods:
        ann = pod.metadata.annotations or {}
        alloc = ann.get('hami.io/vgpu-devices-allocated', '')
        for g in GPUParser.parse_vgpu_devices_allocated(alloc):
            if g['uuid'] == gpu_uuid:
                result.append({
                    "pod_name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "allocation": g['allocation'],
                    #"user_name": ann.get('user_name', ''),
                    #"team_name": ann.get('team_name', '')
                })
    return {"node": node_name, "gpu_uuid": gpu_uuid, "pods": result}

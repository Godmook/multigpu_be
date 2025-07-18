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
    
    **반환 데이터:**
    - `nodes`: 노드 목록
        - `name`: 노드 이름 (예: violet-h100-023)
        - `gpu_type`: GPU 타입 (예: H100, A100)
        - `gpus`: GPU 정보 목록
            - `uuid`: GPU UUID
            - `nvidia`: GPU 타입
            - `unique_id`: 고유 ID
            - `allocation`: 할당률 (1~100)
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
          "gpus": [
            {
              "uuid": "GPU-UUID-123",
              "nvidia": "H100",
              "unique_id": "GPU-UUID-123",
              "allocation": 80,
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
        gpu_type = GPUParser.parse_node_name(name)
        # annotation에서 vgpu 정보 파싱
        ann = node.metadata.annotations or {}
        vgpu_info = GPUParser.parse_vgpu_devices_allocated(ann.get('hami.io/vgpu-devices-allocated', ''))
        gpus = [GPUInfo(uuid=g['uuid'], nvidia=gpu_type, unique_id=g['uuid'], allocation=g['allocation']) for g in vgpu_info]
        result.append(NodeInfo(name=name, gpu_type=gpu_type, gpus=gpus))
    return {"nodes": [n.dict() for n in result]}

@router.get("/{node_name}/gpus/", response_model=dict)
def get_node_gpus(node_name: str):
    """
    특정 노드의 GPU 상세 정보 조회
    
    **매개변수:**
    - `node_name`: 노드 이름 (violet-그래픽카드이름-001~0xx 패턴)
    
    **반환 데이터:**
    - `node`: 노드 이름
    - `gpus`: GPU 정보 목록
    
    **예시:**
    - `node_name`: violet-h100-023
    """
    # 노드 이름 패턴 검증
    if not GPUParser.is_valid_node_name(node_name):
        raise HTTPException(400, "Invalid node name pattern. Expected: violet-그래픽카드이름-001~0xx")
    
    k8s = K8SClient(KUBECONFIG)
    nodes = k8s.list_nodes().items
    node = next((n for n in nodes if n.metadata.name == node_name), None)
    if not node:
        raise HTTPException(404, "Node not found")
    gpu_type = GPUParser.parse_node_name(node_name)
    ann = node.metadata.annotations or {}
    vgpu_info = GPUParser.parse_vgpu_devices_allocated(ann.get('hami.io/vgpu-devices-allocated', ''))
    gpus = [GPUInfo(uuid=g['uuid'], nvidia=gpu_type, unique_id=g['uuid'], allocation=g['allocation']) for g in vgpu_info]
    return {"node": node_name, "gpus": [g.dict() for g in gpus]}

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

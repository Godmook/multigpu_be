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
    """
    k8s = K8SClient(KUBECONFIG)
    nodes = k8s.list_nodes().items
    result = []
    
    for node in nodes:
        name = node.metadata.name
        if not GPUParser.is_valid_node_name(name):
            continue
        gpu_info = k8s.get_node_gpu_info(name)
        # 물리 GPU 개수 추출 (nvidia.com/gpu)
        physical_gpu_count = gpu_info['gpu_count']
        # hami.io annotation에서 UUID/할당률만 추출, 부족하면 빈 값으로 채움
        ann = node.metadata.annotations or {}
        vgpu_info = GPUParser.parse_vgpu_devices_allocated(
            ann.get('hami.io/vgpu-devices-allocated', ''),
            physical_gpu_count
        )
        gpus = [
            GPUInfo(
                uuid=g['uuid'],
                nvidia=gpu_info['gpu_type'],
                unique_id=g['uuid'],
                allocation=g['allocation'],
                source=g.get('source', 'hami.io' if g['uuid'] else 'node_status')
            ) for g in vgpu_info
        ]
        node_info = NodeInfo(
            name=name,
            gpu_type=gpu_info['gpu_type'],
            gpus=gpus
        )
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
    """
    if not GPUParser.is_valid_node_name(node_name):
        raise HTTPException(400, "Invalid node name pattern. Expected: violet-그래픽카드이름-001~0xx")
    k8s = K8SClient(KUBECONFIG)
    gpu_info = k8s.get_node_gpu_info(node_name)
    if gpu_info['status'] == 'Error':
        raise HTTPException(404, f"Node not found or error: {gpu_info.get('error', 'Unknown error')}")
    physical_gpu_count = gpu_info['gpu_count']
    ann = k8s.core_v1.read_node(name=node_name).metadata.annotations or {}
    vgpu_info = GPUParser.parse_vgpu_devices_allocated(
        ann.get('hami.io/vgpu-devices-allocated', ''),
        physical_gpu_count
    )
    gpus = [
        GPUInfo(
            uuid=g['uuid'],
            nvidia=gpu_info['gpu_type'],
            unique_id=g['uuid'],
            allocation=g['allocation'],
            source=g.get('source', 'hami.io' if g['uuid'] else 'node_status')
        ) for g in vgpu_info
    ]
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
    """
    if not GPUParser.is_valid_node_name(node_name):
        raise HTTPException(400, "Invalid node name pattern. Expected: violet-그래픽카드이름-001~0xx")
    k8s = K8SClient(KUBECONFIG)
    pods = k8s.list_pods(node_name=node_name).items
    result = []
    for pod in pods:
        ann = pod.metadata.annotations or {}
        alloc = ann.get('hami.io/vgpu-devices-allocated', '')
        for g in GPUParser.parse_vgpu_devices_allocated(alloc, 0):
            if g['uuid'] == gpu_uuid:
                result.append({
                    "pod_name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "allocation": g['allocation'],
                })
    return {"node": node_name, "gpu_uuid": gpu_uuid, "pods": result}

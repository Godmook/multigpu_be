from fastapi import APIRouter, HTTPException
from app.services.k8s_client import K8SClient
from app.services.gpu_parser import GPUParser
from app.models.node import NodeInfo, GPUInfo
from app.config import KUBECONFIG

TEAM_ANNOT_KEY = "example.com/team"
MEMBER_ANNOT_KEY = "example.com/member"

router = APIRouter()

@router.get("/", response_model=dict)
def get_nodes():
    """
    모든 노드 및 GPU 정보 조회
    - 노드는 allocatable에서 물리 GPU 개수만 판단
    - 각 Pod의 annotation에서 hami.io/vgpu-devices-allocated를 읽어 노드별 GPU 할당 현황을 집계
    - drf.scheduler/gpu-job=true 라벨이 붙은 Running Pod만 대상으로 집계
    """
    k8s = K8SClient(KUBECONFIG)
    nodes = k8s.list_nodes().items
    pods = k8s.list_gpu_job_pods().items
    result = []
    for node in nodes:
        name = node.metadata.name
        if not GPUParser.is_valid_node_name(name):
            continue
        allocatable = node.status.allocatable or {}
        try:
            physical_gpu_count = int(allocatable.get('nvidia.com/gpu', '0'))
        except Exception:
            physical_gpu_count = 0
        gpu_usage = [{} for _ in range(physical_gpu_count)]
        pod_map = [[] for _ in range(physical_gpu_count)]
        user_map = [[] for _ in range(physical_gpu_count)]
        team_map = [[] for _ in range(physical_gpu_count)]
        for pod in pods:
            if pod.spec.node_name != name:
                continue
            ann = pod.metadata.annotations or {}
            vgpu_info = GPUParser.parse_vgpu_devices_allocated(
                ann.get('hami.io/vgpu-devices-allocated', ''),
                physical_gpu_count
            )
            team = ann.get(TEAM_ANNOT_KEY, "")
            member = ann.get(MEMBER_ANNOT_KEY, "")
            for idx, g in enumerate(vgpu_info):
                if g['uuid']:
                    pod_map[idx].append(pod.metadata.name)
                    if member:
                        user_map[idx].append(member)
                    if team:
                        team_map[idx].append(team)
                    gpu_usage[idx] = g
        gpus = []
        for idx in range(physical_gpu_count):
            g = gpu_usage[idx] if gpu_usage[idx] else {"uuid": "", "allocation": 0}
            gpus.append(GPUInfo(
                uuid=g["uuid"],
                nvidia=GPUParser.parse_node_name(name),
                unique_id=g["uuid"],
                allocation=g["allocation"],
                source="pod_annotation" if g["uuid"] else "node_status",
                pods=pod_map[idx],
                user_names=user_map[idx],
                team_names=team_map[idx]
            ))
        node_info = NodeInfo(
            name=name,
            gpu_type=GPUParser.parse_node_name(name),
            gpus=gpus
        )
        node_dict = node_info.dict()
        node_dict['gpu_count'] = physical_gpu_count
        node_dict['status'] = 'Active' if physical_gpu_count > 0 else 'NoGPU'
        result.append(node_dict)
    return {"nodes": result}

@router.get("/{node_name}/gpus/", response_model=dict)
def get_node_gpus(node_name: str):
    """
    특정 노드의 GPU 상세 정보 조회 (Pod 기반 할당 현황, label 필터 적용)
    """
    if not GPUParser.is_valid_node_name(node_name):
        raise HTTPException(400, "Invalid node name pattern. Expected: violet-그래픽카드이름-001~0xx")
    k8s = K8SClient(KUBECONFIG)
    node = next((n for n in k8s.list_nodes().items if n.metadata.name == node_name), None)
    if not node:
        raise HTTPException(404, "Node not found")
    allocatable = node.status.allocatable or {}
    try:
        physical_gpu_count = int(allocatable.get('nvidia.com/gpu', '0'))
    except Exception:
        physical_gpu_count = 0
    pods = k8s.list_gpu_job_pods(node_name=node_name).items
    gpu_usage = [{} for _ in range(physical_gpu_count)]
    pod_map = [[] for _ in range(physical_gpu_count)]
    user_map = [[] for _ in range(physical_gpu_count)]
    team_map = [[] for _ in range(physical_gpu_count)]
    for pod in pods:
        ann = pod.metadata.annotations or {}
        vgpu_info = GPUParser.parse_vgpu_devices_allocated(
            ann.get('hami.io/vgpu-devices-allocated', ''),
            physical_gpu_count
        )
        team = ann.get(TEAM_ANNOT_KEY, "")
        member = ann.get(MEMBER_ANNOT_KEY, "")
        for idx, g in enumerate(vgpu_info):
            if g['uuid']:
                pod_map[idx].append(pod.metadata.name)
                if member:
                    user_map[idx].append(member)
                if team:
                    team_map[idx].append(team)
                gpu_usage[idx] = g
    gpus = []
    for idx in range(physical_gpu_count):
        g = gpu_usage[idx] if gpu_usage[idx] else {"uuid": "", "allocation": 0}
        gpus.append(GPUInfo(
            uuid=g["uuid"],
            nvidia=GPUParser.parse_node_name(node_name),
            unique_id=g["uuid"],
            allocation=g["allocation"],
            source="pod_annotation" if g["uuid"] else "node_status",
            pods=pod_map[idx],
            user_names=user_map[idx],
            team_names=team_map[idx]
        ))
    return {
        "node": node_name,
        "gpu_type": GPUParser.parse_node_name(node_name),
        "gpu_count": physical_gpu_count,
        "status": 'Active' if physical_gpu_count > 0 else 'NoGPU',
        "gpus": [g.dict() for g in gpus]
    }

@router.get("/{node_name}/gpus/{gpu_uuid}/pods/", response_model=dict)
def get_gpu_pods(node_name: str, gpu_uuid: str):
    """
    특정 GPU를 사용하는 Pod 정보 조회 (label 필터 적용)
    """
    if not GPUParser.is_valid_node_name(node_name):
        raise HTTPException(400, "Invalid node name pattern. Expected: violet-그래픽카드이름-001~0xx")
    k8s = K8SClient(KUBECONFIG)
    pods = k8s.list_gpu_job_pods(node_name=node_name).items
    result = []
    for pod in pods:
        ann = pod.metadata.annotations or {}
        vgpu_info = GPUParser.parse_vgpu_devices_allocated(
            ann.get('hami.io/vgpu-devices-allocated', ''), 0)
        team = ann.get(TEAM_ANNOT_KEY, "")
        member = ann.get(MEMBER_ANNOT_KEY, "")
        for g in vgpu_info:
            if g['uuid'] == gpu_uuid:
                result.append({
                    "pod_name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "allocation": g['allocation'],
                    "user_name": member,
                    "team_name": team,
                })
    return {"node": node_name, "gpu_uuid": gpu_uuid, "pods": result}

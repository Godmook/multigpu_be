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
    k8s = K8SClient(KUBECONFIG)
    nodes = k8s.list_nodes().items
    pods = k8s.list_gpu_job_pods().items
    result = []
    GPU_SLOTS = 8
    for node in nodes:
        name = node.metadata.name
        if not GPUParser.is_valid_node_name(name):
            continue
        uuid_to_info = {}
        for pod in pods:
            if pod.spec.node_name != name:
                continue
            ann = pod.metadata.annotations or {}
            vgpu_info = GPUParser.parse_vgpu_devices_allocated(
                ann.get('hami.io/vgpu-devices-allocated', ''), 0
            )
            team = ann.get(TEAM_ANNOT_KEY, "")
            member = ann.get(MEMBER_ANNOT_KEY, "")
            for g in vgpu_info:
                uuid = g['uuid']
                if not uuid:
                    continue
                if uuid not in uuid_to_info:
                    uuid_to_info[uuid] = {
                        "allocation": 0,
                        "pods": [],
                        "user_names": [],
                        "team_names": [],
                    }
                uuid_to_info[uuid]["allocation"] += g["allocation"]
                uuid_to_info[uuid]["pods"].append(pod.metadata.name)
                if member:
                    uuid_to_info[uuid]["user_names"].append(member)
                if team:
                    uuid_to_info[uuid]["team_names"].append(team)
        # 결과 리스트 만들기 (최대 8개)
        gpus = []
        for uuid, info in list(uuid_to_info.items())[:GPU_SLOTS]:
            gpus.append(GPUInfo(
                uuid=uuid,
                nvidia=GPUParser.parse_node_name(name),
                unique_id=uuid,
                allocation=info["allocation"],
                source="pod_annotation",
                pods=info["pods"],
                user_names=info["user_names"],
                team_names=info["team_names"]
            ))
        # 부족하면 빈 값으로 채움
        while len(gpus) < GPU_SLOTS:
            gpus.append(GPUInfo(
                uuid="",
                nvidia=GPUParser.parse_node_name(name),
                unique_id="",
                allocation=0,
                source="node_status",
                pods=[],
                user_names=[],
                team_names=[]
            ))
        node_info = NodeInfo(
            name=name,
            gpu_type=GPUParser.parse_node_name(name),
            gpus=gpus
        )
        node_dict = node_info.dict()
        node_dict['gpu_count'] = GPU_SLOTS
        node_dict['status'] = 'Active' if GPU_SLOTS > 0 else 'NoGPU'
        result.append(node_dict)
    return {"nodes": result}

@router.get("/{node_name}/gpus/", response_model=dict)
def get_node_gpus(node_name: str):
    if not GPUParser.is_valid_node_name(node_name):
        raise HTTPException(400, "Invalid node name pattern. Expected: violet-그래픽카드이름-001~0xx")
    k8s = K8SClient(KUBECONFIG)
    node = next((n for n in k8s.list_nodes().items if n.metadata.name == node_name), None)
    if not node:
        raise HTTPException(404, "Node not found")
    pods = k8s.list_gpu_job_pods(node_name=node_name).items
    GPU_SLOTS = 8
    uuid_to_info = {}
    for pod in pods:
        ann = pod.metadata.annotations or {}
        vgpu_info = GPUParser.parse_vgpu_devices_allocated(
            ann.get('hami.io/vgpu-devices-allocated', ''), 0
        )
        team = ann.get(TEAM_ANNOT_KEY, "")
        member = ann.get(MEMBER_ANNOT_KEY, "")
        for g in vgpu_info:
            uuid = g['uuid']
            if not uuid:
                continue
            if uuid not in uuid_to_info:
                uuid_to_info[uuid] = {
                    "allocation": 0,
                    "pods": [],
                    "user_names": [],
                    "team_names": [],
                }
            uuid_to_info[uuid]["allocation"] += g["allocation"]
            uuid_to_info[uuid]["pods"].append(pod.metadata.name)
            if member:
                uuid_to_info[uuid]["user_names"].append(member)
            if team:
                uuid_to_info[uuid]["team_names"].append(team)
    gpus = []
    for uuid, info in list(uuid_to_info.items())[:GPU_SLOTS]:
        gpus.append(GPUInfo(
            uuid=uuid,
            nvidia=GPUParser.parse_node_name(node_name),
            unique_id=uuid,
            allocation=info["allocation"],
            source="pod_annotation",
            pods=info["pods"],
            user_names=info["user_names"],
            team_names=info["team_names"]
        ))
    while len(gpus) < GPU_SLOTS:
        gpus.append(GPUInfo(
            uuid="",
            nvidia=GPUParser.parse_node_name(node_name),
            unique_id="",
            allocation=0,
            source="node_status",
            pods=[],
            user_names=[],
            team_names=[]
        ))
    return {
        "node": node_name,
        "gpu_type": GPUParser.parse_node_name(node_name),
        "gpu_count": GPU_SLOTS,
        "status": 'Active' if GPU_SLOTS > 0 else 'NoGPU',
        "gpus": [g.dict() for g in gpus]
    }

@router.get("/{node_name}/gpus/{gpu_uuid}/pods/", response_model=dict)
def get_gpu_pods(node_name: str, gpu_uuid: str):
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

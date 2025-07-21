"""
FastAPI routes that expose GPU allocation information, now enriched with
per‑GPU **segments** so the frontend can easily draw stacked‑bar charts or pie
charts.

Key additions
-------------
1. **SegmentInfo** – a small Pydantic model describing how much of a GPU is
   consumed by one user‑and‑team pair and what percentage that represents.
2. `segments` field in every GPU dictionary returned by the API.  Each segment
   aggregates allocation across multiple pods that belong to the **same**
   (user, team) combination so the frontend doesn’t have to merge them.
3. 100 → percentage conversion handled server‑side so the UI can use the values
   directly without extra math.

The code purposefully avoids changing your existing `app.models.node.GPUInfo`
class to keep the patch self‑contained.  Instead, we construct plain `dict`s
for each GPU, which is fine because all three endpoints declare
`response_model=dict`.
"""

from __future__ import annotations

from typing import Dict, List, Tuple, DefaultDict
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.k8s_client import K8SClient
from app.services.gpu_parser import GPUParser
from app.config import KUBECONFIG

# ---------------------------------------------------------------------------
# Pydantic helper model
# ---------------------------------------------------------------------------

class SegmentInfo(BaseModel):
    """Aggregate view of GPU usage for one (user, team) pair."""

    user_name: str = Field(..., description="member annotation, may be empty")
    team_name: str = Field(..., description="team annotation, may be empty")
    allocation: int = Field(..., ge=0, le=100, description="Raw allocation value")

# ---------------------------------------------------------------------------
# Constants & router
# ---------------------------------------------------------------------------

TEAM_ANNOT_KEY = "example.com/team"
MEMBER_ANNOT_KEY = "example.com/member"
GPU_SLOTS = 8  # maximum number of vGPU partitions per physical GPU

router = APIRouter()

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _aggregate_gpu_usage(pods) -> Dict[str, Dict]:
    """Return per‑GPU aggregation dict derived from a list of Pod objects."""

    uuid_to_info: Dict[str, Dict] = {}

    for pod in pods:
        ann = pod.metadata.annotations or {}
        vgpu_info = GPUParser.parse_vgpu_devices_allocated(
            ann.get("hami.io/vgpu-devices-allocated", ""), 0
        )
        team = ann.get(TEAM_ANNOT_KEY, "")
        member = ann.get(MEMBER_ANNOT_KEY, "")

        for g in vgpu_info:
            uuid = g["uuid"] or ""
            if not uuid:
                continue  # skip malformed entries

            # Initialise container for this UUID.
            if uuid not in uuid_to_info:
                uuid_to_info[uuid] = {
                    "allocation_total": 0,
                    "pods": [],
                    "user_names": set(),
                    "team_names": set(),
                    "segment_alloc": defaultdict(int),  # key -> allocation
                }

            info = uuid_to_info[uuid]
            info["allocation_total"] += g["allocation"]
            info["pods"].append(pod.metadata.name)

            if member:
                info["user_names"].add(member)
            if team:
                info["team_names"].add(team)

            # Aggregate allocation per (user, team) pair.
            seg_key = (member, team)
            info["segment_alloc"][seg_key] += g["allocation"]

    return uuid_to_info


def _segments_from_alloc_map(seg_alloc: DefaultDict[Tuple[str, str], int], total: int) -> List[SegmentInfo]:
    """Convert aggregated allocation map to a sorted list of SegmentInfo."""
    segments: List[SegmentInfo] = []
    if total == 0:
        return segments
    for (member, team), alloc in seg_alloc.items():
        segments.append(
            SegmentInfo(
                user_name=member,
                team_name=team,
                allocation=alloc,
            )
        )
    # Sort big‑to‑small so the frontend can colour‑stack nicely.
    segments.sort(key=lambda s: s.allocation, reverse=True)
    return segments

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/", response_model=dict)
async def get_nodes():
    k8s = K8SClient(KUBECONFIG)
    nodes = k8s.list_nodes().items
    pods = k8s.list_gpu_job_pods().items

    result = []
    for node in nodes:
        name = node.metadata.name
        if not GPUParser.is_valid_node_name(name):
            continue

        agg = _aggregate_gpu_usage([p for p in pods if p.spec.node_name == name])
        gpus: List[dict] = []

        # Build response (max GPU_SLOTS entries)
        for uuid, info in list(agg.items())[:GPU_SLOTS]:
            segments = _segments_from_alloc_map(info["segment_alloc"], info["allocation_total"])
            gpus.append(
                {
                    "uuid": uuid,
                    "nvidia": GPUParser.parse_node_name(name),
                    "unique_id": uuid,
                    "allocation": info["allocation_total"],
                    "source": "pod_annotation",
                    "pods": info["pods"],
                    "segments": [s.dict() for s in segments],
                }
            )

        # Pad with empty entries so the consumer always sees GPU_SLOTS items.
        while len(gpus) < GPU_SLOTS:
            gpus.append(
                {
                    "uuid": "",
                    "nvidia": GPUParser.parse_node_name(name),
                    "unique_id": "",
                    "allocation": 0,
                    "source": "node_status",
                    "pods": [],
                    "segments": [],
                }
            )

        node_dict = {
            "name": name,
            "gpu_type": GPUParser.parse_node_name(name),
            "gpu_count": GPU_SLOTS,
            "status": "Active" if GPU_SLOTS > 0 else "NoGPU",
            "gpus": gpus,
        }
        result.append(node_dict)

    return {"nodes": result}


@router.get("/{node_name}/gpus/", response_model=dict)
async def get_node_gpus(node_name: str):
    if not GPUParser.is_valid_node_name(node_name):
        raise HTTPException(400, "Invalid node name pattern. Expected: violet-그래픽카드이름-001~0xx")

    k8s = K8SClient(KUBECONFIG)
    node = next((n for n in k8s.list_nodes().items if n.metadata.name == node_name), None)
    if not node:
        raise HTTPException(404, "Node not found")

    pods = k8s.list_gpu_job_pods(node_name=node_name).items
    agg = _aggregate_gpu_usage(pods)

    gpus: List[dict] = []
    for uuid, info in list(agg.items())[:GPU_SLOTS]:
        segments = _segments_from_alloc_map(info["segment_alloc"], info["allocation_total"])
        gpus.append(
            {
                "uuid": uuid,
                "nvidia": GPUParser.parse_node_name(node_name),
                "unique_id": uuid,
                "allocation": info["allocation_total"],
                "source": "pod_annotation",
                "pods": info["pods"],
                "segments": [s.dict() for s in segments],
            }
        )

    while len(gpus) < GPU_SLOTS:
        gpus.append(
            {
                "uuid": "",
                "nvidia": GPUParser.parse_node_name(node_name),
                "unique_id": "",
                "allocation": 0,
                "source": "node_status",
                "pods": [],
                "segments": [],
            }
        )

    return {
        "node": node_name,
        "gpu_type": GPUParser.parse_node_name(node_name),
        "gpu_count": GPU_SLOTS,
        "status": "Active" if GPU_SLOTS > 0 else "NoGPU",
        "gpus": gpus,
    }


@router.get("/{node_name}/gpus/{gpu_uuid}/pods/", response_model=dict)
async def get_gpu_pods(node_name: str, gpu_uuid: str):
    if not GPUParser.is_valid_node_name(node_name):
        raise HTTPException(400, "Invalid node name pattern. Expected: violet-그래픽카드이름-001~0xx")

    k8s = K8SClient(KUBECONFIG)
    pods = k8s.list_gpu_job_pods(node_name=node_name).items

    result = []
    for pod in pods:
        ann = pod.metadata.annotations or {}
        vgpu_info = GPUParser.parse_vgpu_devices_allocated(
            ann.get("hami.io/vgpu-devices-allocated", ""), 0
        )
        team = ann.get(TEAM_ANNOT_KEY, "")
        member = ann.get(MEMBER_ANNOT_KEY, "")
        for g in vgpu_info:
            if g["uuid"] == gpu_uuid:
                result.append(
                    {
                        "pod_name": pod.metadata.name,
                        "namespace": pod.metadata.namespace,
                        "allocation": g["allocation"],
                        "user_name": member,
                        "team_name": team,
                    }
                )

    return {"node": node_name, "gpu_uuid": gpu_uuid, "pods": result}

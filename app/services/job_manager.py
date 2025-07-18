import random
from datetime import datetime, timezone
from typing import Any, Optional
from kubernetes import client
from kubernetes.client.rest import ApiException
import logging
from app.config import KUBECONFIG, GPU_RESOURCE_PREFIX
from app.services.k8s_client import K8SClient
from app.models.job import JobInfo, WorkloadInfo

logger = logging.getLogger("job_manager")
logger.setLevel(logging.INFO)

# 리소스 계산 함수 (예시)
def calc_resources(gpu_count, cpu_pct, mem_pct):
    # GPU 1개당 CPU/메모리 기본값 예시
    base_cpu = 8
    base_mem = 64000  # Mi
    cpu = int(base_cpu * gpu_count * cpu_pct / 100)
    mem = int(base_mem * gpu_count * mem_pct / 100)
    return cpu, gpu_count, mem

# Job 생성 요청 모델 (FastAPI용)
from pydantic import BaseModel
class JobCreateRequest(BaseModel):
    name: Optional[str] = None
    namespace: str = "default"
    gpu_count: int
    cpu_pct: int
    mem_pct: int
    gpu_pct: int
    user_name: str
    team_name: str
    priority: str
    gpu_type: Optional[str] = None
    labels: Optional[dict] = None
    annotations: Optional[dict] = None
    gang_scheduling: Optional[bool] = False
    gang_count: Optional[int] = 1
    gang_id: Optional[str] = None
    pod_group_name: Optional[str] = None
    pod_group_total: Optional[int] = None

class JobManager:
    def __init__(self):
        self.k8s = K8SClient(KUBECONFIG)
        self.hami_scheduler = "hami-scheduler"
        self.gpu_node_label = {"hami.io/node-gpu": "true"}
        self.queue_name = "default"

    def submit_job(self, payload: JobCreateRequest) -> str:
        now = datetime.now(timezone.utc)
        name = payload.name or f"job-{now.strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"

        cpu_req = getattr(payload, "cpu_req", None) or calc_resources(payload.gpu_count, payload.cpu_pct, payload.mem_pct)[0]
        gpu_req = getattr(payload, "gpu_count", None) or calc_resources(payload.gpu_count, payload.cpu_pct, payload.mem_pct)[1]
        mem_req = getattr(payload, "mem_req", None) or calc_resources(payload.gpu_count, payload.cpu_pct, payload.mem_pct)[2]

        job_labels = getattr(payload, "labels", None) or {
            "app": "k8s-gpu-job",
            "kueue.x-k8s.io/queue-name": self.queue_name,
            "priority": payload.priority,
        }
        pod_labels = dict(job_labels)

        ann_job = getattr(payload, "annotations", None) or {}
        ann_pod = dict(ann_job)
        ann_pod.setdefault("hami.io/node-scheduler-policy", "binpack")
        ann_pod.setdefault("hami.io/gpu-scheduler-policy", "binpack")
        if getattr(payload, "gpu_type", None):
            ann_pod["nvidia.com/use-gputype"] = payload.gpu_type
        else:
            ann_pod.setdefault("nvidia.com/use-gputype", "A100,H100")

        parallelism = completions = getattr(payload, "gang_count", 1) if getattr(payload, "gang_scheduling", False) else 1

        if getattr(payload, "gang_scheduling", False):
            gid = getattr(payload, "gang_id", None) or getattr(payload, "pod_group_name", None)
            if gid:
                pod_labels["kueue.x-k8s.io/pod-group-name"] = gid
            if getattr(payload, "pod_group_total", None):
                ann_job["kueue.x-k8s.io/pod-group-total-count"] = str(payload.pod_group_total)

        res_spec = {
            "requests": {
                f"{GPU_RESOURCE_PREFIX}/gpu": str(gpu_req),
                "cpu": str(cpu_req),
                "memory": f"{mem_req}Mi",
            },
            "limits": {
                f"{GPU_RESOURCE_PREFIX}/gpu": str(gpu_req),
                "cpu": str(cpu_req),
                "memory": f"{mem_req}Mi",
                "nvidia.com/gpucores": str(payload.gpu_pct),
                "nvidia.com/gpumem-percentage": str(payload.gpu_pct),
            },
        }

        body = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=payload.namespace,
                labels=job_labels,
                annotations=ann_job
            ),
            spec=client.V1JobSpec(
                suspend=True,
                parallelism=parallelism,
                completions=completions,
                backoff_limit=2,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels=pod_labels, annotations=ann_pod),
                    spec=client.V1PodSpec(
                        scheduler_name=self.hami_scheduler,
                        containers=[
                            client.V1Container(
                                name="main",
                                image="ubuntu:18.04",
                                command=["sleep", str(random.randint(45,120))],
                                resources=client.V1ResourceRequirements(**res_spec)
                            )
                        ],
                        restart_policy="Never",
                        node_selector=self.gpu_node_label,
                        tolerations=[
                            client.V1Toleration(
                                key="gpu",
                                operator="Exists",
                                effect="NoSchedule"
                            )
                        ],
                    ),
                ),
            ),
        )

        try:
            self.k8s.batch_v1.create_namespaced_job(namespace=payload.namespace, body=body)
            logger.info("Job %s created", name)
        except ApiException as e:
            if e.status == 409:
                raise Exception("Job already exists")
            logger.error("K8s error: %s", e.body)
            raise Exception("Kubernetes API error")

        return name

    def submit_native_job(self, job_manifest: dict) -> str:
        """
        K8s native Job manifest를 그대로 받아서 생성
        이름이 중복되면 타임스탬프+랜덤값을 붙여 유니크하게 자동 변경
        """
        name = job_manifest.get("metadata", {}).get("name", "unknown")
        namespace = job_manifest.get("metadata", {}).get("namespace", "default")

        # 이름 중복 체크 및 유니크 이름 생성
        try:
            self.k8s.batch_v1.read_namespaced_job(name=name, namespace=namespace)
            # 이미 존재하면 유니크 이름으로 변경
            now = datetime.now(timezone.utc)
            unique_name = f"{name}-{now.strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}"
            job_manifest["metadata"]["name"] = unique_name
            name = unique_name
        except Exception:
            # 존재하지 않으면 그대로 진행
            pass

        meta = job_manifest.setdefault("metadata", {})
        labels = meta.setdefault("labels", {})
        annotations = meta.setdefault("annotations", {})
        pod_template = job_manifest.get("spec", {}).get("template", {})
        pod_meta = pod_template.setdefault("metadata", {})
        pod_labels = pod_meta.setdefault("labels", {})
        pod_annotations = pod_meta.setdefault("annotations", {})
        gang_id = labels.get("kueue.x-k8s.io/pod-group-name")
        gang_count = (
            annotations.get("kueue.x-k8s.io/pod-group-total-count")
            or meta.get("pod_group_total")
            or meta.get("gang_count")
        )
        if gang_id:
            labels["kueue.x-k8s.io/pod-group-name"] = gang_id
            pod_labels["kueue.x-k8s.io/pod-group-name"] = gang_id
        if gang_id and gang_count:
            annotations["kueue.x-k8s.io/pod-group-total-count"] = str(gang_count)
            pod_annotations["kueue.x-k8s.io/pod-group-total-count"] = str(gang_count)
        job_obj = client.ApiClient()._ApiClient__deserialize(job_manifest, "V1Job")
        try:
            self.k8s.batch_v1.create_namespaced_job(namespace=namespace, body=job_obj)
            logger.info("Job %s created", name)
        except ApiException as e:
            if e.status == 409:
                raise Exception("Job already exists")
            logger.error("K8s error: %s", e.body)
            raise Exception("Kubernetes API error")
        return name

    def delete_job(self, job_id: str, namespace: str = "default") -> bool:
        """Job 삭제"""
        try:
            self.k8s.batch_v1.delete_namespaced_job(name=job_id, namespace=namespace)
            logger.info("Job %s deleted", job_id)
            return True
        except ApiException as e:
            if e.status == 404:
                logger.warning("Job %s not found", job_id)
                return False
            logger.error("K8s error: %s", e.body)
            raise Exception("Kubernetes API error")

    def get_pending_jobs(self) -> list:
        """Kueue에서 admit되지 않은 Job 목록 조회 (예시: label/annotation 기반 필터링)"""
        jobs = self.k8s.list_jobs().items
        pending = []
        for job in jobs:
            # 예시: suspend=True, status.active==0, annotation/label 등으로 필터
            if getattr(job.spec, 'suspend', False):
                meta = job.metadata
                ann = meta.annotations or {}
                labels = meta.labels or {}
                pending.append(JobInfo(
                    job_id=meta.name,
                    priority=labels.get('priority', 'Normal'),
                    created_at=str(meta.creation_timestamp),
                    user_name=ann.get('user_name', ''),
                    team_name=ann.get('team_name', ''),
                    status='Pending',
                    gpu_type=ann.get('nvidia.com/use-gputype', None),
                    waiting_time=None
                ))
        return pending

    def get_pending_workloads(self) -> list:
        """Kueue에서 pending 상태의 Workload 목록 조회"""
        workloads_data = self.k8s.list_workloads()
        workloads = []
        
        for wl_data in workloads_data:
            # annotation에서 사용자/팀 정보 추출
            annotations = wl_data.get('annotations', {})
            user_name = annotations.get('user_name', '')
            team_name = annotations.get('team_name', '')
            
            workload = WorkloadInfo(
                name=wl_data['name'],
                namespace=wl_data['namespace'],
                priority=wl_data['priority'],
                created_at=wl_data['created_at'],
                resource_requests=wl_data['resource_requests'],
                labels=wl_data.get('labels'),
                annotations=annotations,
                user_name=user_name,
                team_name=team_name
            )
            workloads.append(workload)
        
        return workloads

    def update_priority(self, job_id: str, priority: str) -> bool:
        """Job 우선순위 변경 (label patch)"""
        try:
            body = {"metadata": {"labels": {"priority": priority}}}
            self.k8s.batch_v1.patch_namespaced_job(name=job_id, namespace="default", body=body)
            return True
        except Exception as e:
            logger.error(f"Priority update failed: {e}")
            return False

    def get_jobs_by_gpu_type(self, gpu_type: str) -> list:
        """특정 GPU 타입을 사용하는 노드/Job 통합 정보 조회"""
        jobs = self.k8s.list_jobs().items
        result = []
        for job in jobs:
            ann = (job.metadata.annotations or {})
            if ann.get('nvidia.com/use-gputype', '').upper() == gpu_type.upper():
                result.append(job.metadata.name)
        return result

from kubernetes import client, config
from typing import Any, List, Dict
from app.config import GPU_RESOURCE_PREFIX

class K8SClient:
    def __init__(self, kubeconfig: str = None):
        """쿠버네티스 클러스터 연결 초기화"""
        if kubeconfig:
            config.load_kube_config(config_file=kubeconfig)
        else:
            config.load_kube_config()
        self.core_v1 = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()
        self.batch_v1 = client.BatchV1Api()

    def list_nodes(self) -> Any:
        """모든 노드 정보 조회"""
        return self.core_v1.list_node()

    def list_pods(self, node_name: str = None) -> Any:
        """특정 노드의 Pod 목록 조회"""
        if node_name:
            return self.core_v1.list_pod_for_all_namespaces(field_selector=f'spec.nodeName={node_name}')
        return self.core_v1.list_pod_for_all_namespaces()

    def list_jobs(self) -> Any:
        """모든 Job 목록 조회"""
        return self.batch_v1.list_job_for_all_namespaces()

    def list_workloads(self) -> List[Dict]:
        """Kueue Workloads 조회 (pending 상태의 Workload만)"""
        try:
            # Kueue Workload API 호출
            workloads = self.custom_api.list_cluster_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                plural="workloads"
            )
            
            pending_workloads = []
            for workload in workloads.get('items', []):
                # pending 상태인 Workload만 필터링
                status = workload.get('status', {})
                if status.get('admission') is None:  # admit되지 않은 상태
                    metadata = workload.get('metadata', {})
                    spec = workload.get('spec', {})
                    
                    # 우선순위 추출 (priority 필드에서 숫자로)
                    priority = spec.get('priority', 0)
                    
                    # 생성시간 추출
                    creation_timestamp = metadata.get('creationTimestamp', '')
                    
                    # 리소스 요구량 추출
                    resource_requests = {}
                    for pod_set in spec.get('podSets', []):
                        for container in pod_set.get('template', {}).get('spec', {}).get('containers', []):
                            requests = container.get('resources', {}).get('requests', {})
                            for resource, amount in requests.items():
                                if resource.startswith(f'{GPU_RESOURCE_PREFIX}/'):
                                    resource_requests[resource] = amount
                    
                    pending_workloads.append({
                        'name': metadata.get('name', ''),
                        'namespace': metadata.get('namespace', ''),
                        'priority': priority,
                        'created_at': creation_timestamp,
                        'resource_requests': resource_requests,
                        'labels': metadata.get('labels', {}),
                        'annotations': metadata.get('annotations', {})
                    })
            
            return pending_workloads
            
        except Exception as e:
            print(f"Error fetching workloads: {e}")
            return []

    def get_workload_by_name(self, name: str, namespace: str = "default") -> Dict:
        """특정 Workload 조회"""
        try:
            workload = self.custom_api.get_namespaced_custom_object(
                group="kueue.x-k8s.io",
                version="v1beta1",
                namespace=namespace,
                plural="workloads",
                name=name
            )
            return workload
        except Exception as e:
            print(f"Error fetching workload {name}: {e}")
            return {}



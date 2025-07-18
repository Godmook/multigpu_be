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

    def get_node_gpu_info(self, node_name: str) -> Dict:
        """노드의 GPU 정보를 종합적으로 조회 (hami.io annotation + 노드 상태)"""
        try:
            # 노드 정보 조회
            node = self.core_v1.read_node(name=node_name)
            
            # 기본 GPU 정보 초기화
            gpu_info = {
                'node_name': node_name,
                'gpu_count': 0,
                'gpu_details': [],
                'status': 'Unknown'
            }
            
            # 1. hami.io annotation에서 GPU 정보 파싱
            annotations = node.metadata.annotations or {}
            vgpu_allocated = annotations.get('hami.io/vgpu-devices-allocated', '')
            
            if vgpu_allocated:
                # hami.io annotation이 있으면 파싱
                gpu_details = []
                for item in vgpu_allocated.split(','):
                    if ':' in item:
                        uuid, alloc = item.split(':', 1)
                        try:
                            gpu_details.append({
                                'uuid': uuid.strip(),
                                'allocation': int(alloc.strip()),
                                'source': 'hami.io'
                            })
                        except ValueError:
                            continue
                
                gpu_info['gpu_count'] = len(gpu_details)
                gpu_info['gpu_details'] = gpu_details
                gpu_info['status'] = 'Active'
            
            # 2. 노드 상태에서 GPU 정보 확인 (hami.io가 없을 경우)
            if gpu_info['gpu_count'] == 0:
                # 노드의 allocatable 리소스에서 GPU 확인
                allocatable = node.status.allocatable or {}
                
                # nvidia.com/gpu 리소스 확인
                nvidia_gpu = allocatable.get('nvidia.com/gpu', '0')
                if nvidia_gpu and nvidia_gpu != '0':
                    try:
                        gpu_count = int(nvidia_gpu)
                        gpu_info['gpu_count'] = gpu_count
                        gpu_info['status'] = 'Available'
                        
                        # 기본 GPU 상세 정보 생성
                        for i in range(gpu_count):
                            gpu_info['gpu_details'].append({
                                'uuid': f'GPU-{node_name}-{i:03d}',
                                'allocation': 0,
                                'source': 'node_status'
                            })
                    except ValueError:
                        pass
                
                # example.com/gpu 또는 다른 GPU 리소스 확인
                custom_gpu = allocatable.get(f'{GPU_RESOURCE_PREFIX}/gpu', '0')
                if custom_gpu and custom_gpu != '0' and gpu_info['gpu_count'] == 0:
                    try:
                        gpu_count = int(custom_gpu)
                        gpu_info['gpu_count'] = gpu_count
                        gpu_info['status'] = 'Available'
                        
                        # 기본 GPU 상세 정보 생성
                        for i in range(gpu_count):
                            gpu_info['gpu_details'].append({
                                'uuid': f'GPU-{node_name}-{i:03d}',
                                'allocation': 0,
                                'source': 'node_status'
                            })
                    except ValueError:
                        pass
            
            # 3. 노드 라벨에서 GPU 타입 확인
            labels = node.metadata.labels or {}
            gpu_type = labels.get('nvidia.com/gpu.product', 'Unknown')
            if gpu_type == 'Unknown':
                # 노드 이름에서 GPU 타입 추출 시도
                if 'h100' in node_name.lower():
                    gpu_type = 'H100'
                elif 'a100' in node_name.lower():
                    gpu_type = 'A100'
                elif 'rtx' in node_name.lower():
                    gpu_type = 'RTX'
            
            gpu_info['gpu_type'] = gpu_type
            
            return gpu_info
            
        except Exception as e:
            print(f"Error getting GPU info for node {node_name}: {e}")
            return {
                'node_name': node_name,
                'gpu_count': 0,
                'gpu_details': [],
                'status': 'Error',
                'gpu_type': 'Unknown',
                'error': str(e)
            }

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



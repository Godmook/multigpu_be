import re
from typing import List, Dict

class GPUParser:
    @staticmethod
    def parse_node_name(node_name: str) -> str:
        """노드 이름에서 GPU 타입 추출 (예: violet-h100-023 -> H100)"""
        # violet-그래픽카드이름-001~0xx 패턴 매칭
        pattern = r'^violet-([a-zA-Z0-9]+)-\d{3}$'
        match = re.match(pattern, node_name)
        if match:
            return match.group(1).upper()
        return "UNKNOWN"

    @staticmethod
    def is_valid_node_name(node_name: str) -> bool:
        """노드 이름이 violet-그래픽카드이름-001~0xx 패턴인지 확인"""
        pattern = r'^violet-([a-zA-Z0-9]+)-\d{3}$'
        return bool(re.match(pattern, node_name))

    @staticmethod
    def parse_vgpu_devices_allocated(annotation: str, physical_gpu_count: int) -> List[Dict]:
        """
        hami.io/vgpu-devices-allocated에서 GPU UUID, 할당률만 추출
        예: GPU-UUID,NVIDIA,143771,100:GPU-UUID2,NVIDIA,143771,100
        → [{uuid, allocation}, ...] (부족하면 빈 UUID/0으로 채움)
        """
        result = []
        if annotation:
            for item in annotation.split(':'):
                parts = item.split(',')
                if len(parts) >= 4:
                    uuid = parts[0]
                    try:
                        allocation = int(parts[3])
                    except Exception:
                        allocation = 0
                    result.append({"uuid": uuid, "allocation": allocation})
        # 부족하면 빈 UUID/0으로 채움
        while len(result) < physical_gpu_count:
            result.append({"uuid": "", "allocation": 0})
        return result

    @staticmethod
    def physical_gpu_count(vgpu_count: int) -> int:
        """VGPU 개수에서 실제 물리 GPU 개수 계산 (1/10)"""
        return vgpu_count // 10

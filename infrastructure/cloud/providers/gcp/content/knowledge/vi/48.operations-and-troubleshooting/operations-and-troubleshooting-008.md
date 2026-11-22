# Xử lý GKE node pressure, lỗi image pull và thiếu IP

Một ứng dụng trên Google Kubernetes Engine (GKE) có thể đột ngột tạo Pod ở trạng thái Pending, bị evict, không tải được container image hoặc không nhận được địa chỉ IP. Những sự cố này thường xuất hiện cùng lúc trong một đợt triển khai hay khi tải tăng, nhưng nguyên nhân nằm ở các lớp khác nhau: tài nguyên node, kubelet/container runtime, quyền truy cập registry hoặc quy hoạch địa chỉ mạng.

Runbook này hướng dẫn phân biệt và xử lý ba nhóm vấn đề:

- **Node pressure:** node thiếu memory, disk/ephemeral storage hoặc PID; kubelet có thể từ chối Pod mới hoặc evict workload.
- **Image pull failure:** Pod không tải được image từ Artifact Registry hay registry bên ngoài do sai tên/tag/digest, quyền, mạng hoặc định dạng image.
- **IP exhaustion:** cluster không còn địa chỉ phù hợp cho node, Pod hoặc Service; Pod có thể Pending dù CPU và memory vẫn còn.

Mục tiêu là xác định đúng lớp lỗi, bảo vệ workload và dữ liệu, khôi phục có kiểm soát, rồi bổ sung capacity hoặc sửa cấu hình để lỗi không tái diễn.

## 1. Phân loại triệu chứng trước khi thay đổi

Bắt đầu bằng việc xác định đối tượng bị ảnh hưởng và thông báo lỗi đầu tiên.

| Triệu chứng | Dấu hiệu quan sát | Nhóm nguyên nhân ưu tiên |
|---|---|---|
| Pod Pending | Event Insufficient memory, Insufficient cpu, Too many pods hoặc không cấp được IP | Scheduling, node capacity, IP |
| Pod bị evict | Reason Evicted, node condition MemoryPressure hoặc DiskPressure | Node pressure |
| Container không khởi động | ErrImagePull, ImagePullBackOff | Image, registry, IAM, network |
| Node NotReady | Node condition, kubelet hoặc runtime bất thường | Node/system pressure, network, control plane |
| Pod sandbox không tạo được | Event liên quan CNI/IP allocation | Pod IP range, CNI, node |
| Service không truy cập được | Pod có IP nhưng Service không hoạt động | Endpoint, selector, NetworkPolicy, Service IP/routing |
| Node pool không scale | Autoscaler báo quota, subnet hoặc resource constraint | Node IP range, quota, capacity |

Không bắt đầu bằng cách xóa Pod hoặc tăng node count ngay. Nếu nguyên nhân là image không tồn tại hoặc subnet hết IP, thêm node chỉ làm tình hình tốn kém hơn mà không giải quyết được lỗi.

### Xác định phạm vi

- Một Pod hay mọi Pod trong namespace?
- Một node hay toàn bộ node pool?
- Chỉ một zone hay nhiều zone?
- Chỉ workload mới deploy hay cả workload đang chạy?
- Chỉ một registry/image hay mọi image?
- Chỉ Pod IP, hay cả node IP và Service IP?

Ghi lại thời điểm bắt đầu, lần deploy gần nhất, thay đổi IAM/network, autoscaling event và các alert liên quan.

## 2. Thu thập bằng chứng ban đầu

Chọn đúng kubeconfig context và namespace trước khi chạy lệnh:

~~~bash
kubectl config current-context
kubectl get nodes -o wide
kubectl get pods -A -o wide
kubectl get events -A --sort-by=.lastTimestamp
~~~

Xem trạng thái cluster và node pool:

~~~bash
gcloud container clusters list --project="PROJECT_ID"
gcloud container clusters describe "CLUSTER_NAME" \
  --location="CLUSTER_LOCATION" \
  --project="PROJECT_ID"
~~~

Nếu cluster dùng regional control plane, CLUSTER_LOCATION thường là region; nếu zonal, đó là zone. Dùng đúng location trong cấu hình thực tế.

Lưu bằng chứng trước khi sửa:

- Pod name, namespace, node và event message.
- Node name, node pool, zone và conditions.
- Cluster/node pool version và cấu hình autoscaling.
- Timestamp UTC và change/release ID.
- Logs của workload, kubelet/container runtime và GKE events nếu có.
- Metrics CPU, memory, disk, IP allocation và quota.

Không đưa token, private key, image pull secret hoặc nội dung Secret Kubernetes vào ticket/log.

## 3. Hiểu các loại node pressure

Kubernetes node conditions thường biểu thị những trạng thái sau:

| Condition | Ý nghĩa | Hậu quả có thể gặp |
|---|---|---|
| MemoryPressure | Node thiếu memory khả dụng theo ngưỡng eviction | Pod bị evict, scheduling bị hạn chế |
| DiskPressure | Node thiếu dung lượng hoặc inode trên filesystem liên quan | Eviction, image/container creation thất bại |
| PIDPressure | Node gần cạn số process IDs | Không tạo thêm process/container |
| Ready=False/Unknown | Node không sẵn sàng hoặc mất heartbeat | Pod không được schedule bình thường, workload bị ảnh hưởng |

Node pressure không đồng nghĩa CPU luôn ở mức cao. Một node có CPU thấp vẫn có thể thiếu memory, ephemeral storage hoặc inode.

### Đọc condition và resource

~~~bash
kubectl describe node "NODE_NAME"
kubectl top nodes
kubectl describe pods -n "NAMESPACE" "POD_NAME"
~~~

kubectl top cần Metrics Server/metrics pipeline tương ứng và cung cấp số liệu sử dụng gần thời điểm quan sát. Nó không thay thế biểu đồ lịch sử hoặc số liệu filesystem/inode.

Trong output của describe node, chú ý:

- Conditions.
- Capacity và Allocatable.
- Allocated resources.
- Non-terminated Pods.
- Taints và labels.
- Events ở cuối output.

## 4. Phân biệt Capacity, Allocatable, Requests và Usage

Bốn khái niệm dễ bị nhầm:

- **Capacity:** tổng tài nguyên node có.
- **Allocatable:** phần Kubernetes có thể phân bổ cho workload sau khi trừ phần dành cho hệ thống.
- **Requests:** lượng tài nguyên Pod khai báo để scheduler đặt Pod.
- **Usage:** mức tiêu thụ thực tế theo thời điểm.

Scheduler chủ yếu dùng requests và allocatable để quyết định placement, không chỉ dựa vào CPU/memory đang sử dụng.

Ví dụ:

| Chỉ số memory | Giá trị minh họa |
|---|---:|
| Node capacity | 16 GiB |
| Allocatable | 14 GiB |
| Tổng requests đang đặt | 13 GiB |
| Usage hiện tại | 7 GiB |

Node có thể còn usage thấp nhưng chỉ còn ít allocatable chưa được request. Pod mới yêu cầu 2 GiB có thể không schedule được nếu không có node phù hợp.

Ngược lại, requests đặt quá thấp có thể khiến nhiều Pod được schedule trên cùng node; khi usage tăng, kubelet gặp MemoryPressure.

### Kiểm tra Pod requests/limits

~~~bash
kubectl get pods -n "NAMESPACE" -o json
kubectl describe node "NODE_NAME"
~~~

Có thể dùng kubectl get pod với output YAML để xem resources của Pod cụ thể. Kiểm tra cả container chính, sidecar và init containers; tổng resource Pod có thể lớn hơn phần nhìn thấy ở container ứng dụng.

## 5. Xử lý MemoryPressure

### Dấu hiệu

- Node condition MemoryPressure=True.
- Pod có reason Evicted hoặc event báo memory threshold.
- Container bị OOMKilled.
- Memory working set tăng, JVM heap/GC pressure hoặc cache tăng.
- Node có nhiều Pod requests thấp hơn mức dùng thực tế.

### Quy trình chẩn đoán

1. Xác định node và các Pod đang chiếm memory.
2. So sánh usage với requests/limits.
3. Kiểm tra lịch sử memory và thời điểm deploy/traffic spike.
4. Xem JVM heap, native memory, direct buffers, thread count và memory của sidecars.
5. Phân biệt container OOMKilled với node-level eviction.
6. Kiểm tra autoscaler có thể thêm node và quota có đủ không.

Ví dụ kiểm tra:

~~~bash
kubectl top pods -A --sort-by=memory
kubectl describe pod -n "NAMESPACE" "POD_NAME"
kubectl describe node "NODE_NAME"
~~~

### Khôi phục

- Nếu một workload bị memory leak, rollback hoặc triển khai bản sửa đã được kiểm thử.
- Nếu requests/limits không phản ánh workload, điều chỉnh theo dữ liệu đo và kiểm tra lại scheduling.
- Nếu tải tăng hợp lệ, scale workload và node pool trong giới hạn capacity.
- Nếu node pressure đã gây eviction, xác minh replica đã được tạo lại và ứng dụng phục hồi.
- Không tăng memory limit vô hạn; điều đó có thể chỉ chuyển lỗi từ container sang node.

### Java/Spring Boot

Với JVM containerized, đặt heap không vượt quá memory limit và dành headroom cho metaspace, thread stacks, direct buffers, native libraries và agent. Không lấy toàn bộ container memory làm Xmx.

Theo dõi GC pause, allocation rate, live heap, thread count và container memory. Một heap nhỏ hơn có thể gây GC quá nhiều; một heap quá lớn có thể khiến container OOMKilled khi native memory tăng.

## 6. Xử lý DiskPressure và ephemeral storage

Kubernetes node có nhiều loại dữ liệu tạm:

- Writable container layers.
- Container logs.
- emptyDir volumes.
- Image layers và image cache.
- Runtime/kubelet data.
- Dữ liệu tạm do ứng dụng tạo ra.

DiskPressure có thể do dung lượng filesystem thấp hoặc inode gần hết. Kiểm tra dung lượng còn trống mà bỏ qua inode có thể dẫn đến chẩn đoán sai.

### Dấu hiệu

- Node condition DiskPressure=True.
- Pod bị evict với thông báo ephemeral storage.
- Image pull hoặc unpack image thất bại.
- Container runtime không tạo được filesystem/layer.
- Log tăng đột biến hoặc file tạm không được dọn.

### Kiểm tra

~~~bash
kubectl describe node "NODE_NAME"
kubectl get pods -A -o wide
kubectl describe pod -n "NAMESPACE" "POD_NAME"
~~~

Trong GKE, dùng Cloud Logging và các metric hệ thống/node được bật để kiểm tra disk usage, filesystem và container logs. Quyền truy cập trực tiếp node phụ thuộc chế độ GKE, node image và chính sách tổ chức; không giả định có thể SSH vào mọi node.

### Khắc phục

- Giới hạn log verbosity và cấu hình retention/rotation phù hợp.
- Xóa file tạm theo quy trình của ứng dụng; không xóa trực tiếp runtime directories.
- Đặt ephemeral-storage requests/limits cho workload cần nhiều file tạm.
- Chuyển dữ liệu bền vững sang PersistentVolume hoặc dịch vụ lưu trữ phù hợp.
- Điều chỉnh node boot disk/node pool theo nhu cầu đã đo.
- Kiểm tra image size và dọn image cũ qua cơ chế runtime được hỗ trợ.

Không chạy lệnh xóa đệ quy vào thư mục container runtime/kubelet trên node đang phục vụ. Thao tác đó có thể làm hỏng container state và khiến node NotReady.

## 7. Xử lý PIDPressure

PIDPressure xảy ra khi node gần đạt giới hạn process IDs. Nguyên nhân thường gồm:

- Ứng dụng tạo quá nhiều process con.
- Process bị rò rỉ hoặc không được thu hồi.
- Sidecar/agent tạo nhiều worker.
- Container thiếu giới hạn hoặc ứng dụng fork không kiểm soát.
- Một workload bất thường chiếm phần lớn PID của node.

### Chẩn đoán

~~~bash
kubectl describe node "NODE_NAME"
kubectl top pods -A
kubectl get pods -A -o wide
~~~

Metric process/PID có thể cần node-level monitoring hoặc logs phù hợp. Không suy ra PID usage chỉ từ CPU/memory.

### Khắc phục

- Xác định Pod/process owner và sửa vòng đời process.
- Giới hạn concurrency/process pool trong ứng dụng.
- Kiểm tra sidecar, init container và agent.
- Cô lập workload gây sự cố nếu có thể làm an toàn.
- Điều chỉnh capacity/Pod density chỉ khi hiểu giới hạn node và chính sách GKE.

Tăng số node có thể phân tán workload, nhưng không chữa được process leak; autoscaling còn có thể nhân rộng một workload lỗi.

## 8. Taint, eviction và PodDisruptionBudget

Khi node gặp pressure, kubelet có thể áp dụng taint như node.kubernetes.io/memory-pressure hoặc node.kubernetes.io/disk-pressure. Scheduler dùng taints/tolerations để hạn chế Pod mới được đặt vào node không phù hợp.

Khi phải thay node, cần hiểu:

- **cordon** đánh dấu node không nhận Pod mới.
- **drain** evict Pod theo cơ chế Kubernetes, có thể bị chặn bởi PodDisruptionBudget (PDB).
- DaemonSet Pod được xử lý riêng khi drain.
- emptyDir data có thể mất khi Pod bị di chuyển.
- Stateful workload cần xem xét volume detach/attach và quorum.

Ví dụ thao tác có kiểm soát:

~~~bash
kubectl cordon "NODE_NAME"
kubectl get pdb -A
kubectl drain "NODE_NAME" --ignore-daemonsets
~~~

Lệnh drain có thể chờ hoặc thất bại nếu PDB không cho phép disruption. Chỉ dùng tùy chọn xóa dữ liệu emptyDir khi owner chấp thuận và dữ liệu có thể tái tạo. Trước khi drain, kiểm tra replica, topology, capacity node thay thế và lịch bảo trì.

Không xóa VM/node thủ công khỏi GKE node pool để xử lý pressure nếu node pool được GKE quản lý. Sử dụng cơ chế node pool upgrade/repair/resize được hỗ trợ.

## 9. Phân biệt OOMKilled, Evicted và CrashLoopBackOff

| Trạng thái/lý do | Ý nghĩa | Bước đầu tiên |
|---|---|---|
| OOMKilled | Container vượt memory limit hoặc bị hệ thống OOM kill | Kiểm tra limit, heap, memory usage |
| Evicted | Kubelet loại Pod do node pressure hoặc điều kiện eviction | Kiểm tra node conditions và eviction message |
| CrashLoopBackOff | Container khởi động rồi thoát liên tục | Xem previous logs, exit code và startup config |
| Pending | Pod chưa được schedule hoặc chưa tạo được sandbox | Đọc events và scheduler/CNI message |
| ContainerCreating | Runtime đang chuẩn bị container, có thể chờ image/volume/network | Events, image pull và volume attach |

Lấy logs của lần container trước:

~~~bash
kubectl logs -n "NAMESPACE" "POD_NAME" --previous
kubectl describe pod -n "NAMESPACE" "POD_NAME"
~~~

Một Pod có thể gặp nhiều trạng thái nối tiếp: Pending do image pull, sau đó CrashLoopBackOff do cấu hình. Luôn dựa trên event/time mới nhất, không chỉ cột STATUS trong kubectl get pods.

## 10. Chẩn đoán ErrImagePull và ImagePullBackOff

ErrImagePull biểu thị lần kéo image thất bại. ImagePullBackOff cho biết kubelet/runtime đang lùi thời gian trước khi thử lại. Đây thường là triệu chứng lặp lại, không phải nguyên nhân gốc.

### Kiểm tra image reference

~~~bash
kubectl describe pod -n "NAMESPACE" "POD_NAME"
kubectl get pod -n "NAMESPACE" "POD_NAME" -o yaml
~~~

Kiểm tra:

- Registry hostname đúng chưa.
- Project/repository/image path có đúng không.
- Tag hoặc digest tồn tại không.
- Image được build cho kiến trúc node (ví dụ amd64/arm64) hay chưa.
- Repository có bị đổi tên hoặc xóa không.
- Manifest dùng đúng image của môi trường hiện tại không.

Ưu tiên pin image theo digest trong production để bảo đảm deploy có thể lặp lại. Tag mutable như latest khiến khó xác định chính xác image nào đang được kéo.

### Đọc thông báo lỗi

| Event/message thường gặp | Hướng kiểm tra |
|---|---|
| manifest unknown / not found | Sai image path, tag hoặc digest |
| unauthorized / denied | IAM, registry credentials hoặc repository ACL |
| no basic auth credentials | Thiếu cấu hình xác thực registry ngoài |
| i/o timeout / DNS error | Egress, DNS, proxy hoặc registry endpoint |
| x509 certificate error | CA trust/TLS proxy |
| no matching manifest | Image không có platform/architecture phù hợp |
| toomanyrequests / rate limit | Registry quota hoặc giới hạn pull |
| no space left on device | Node disk/image filesystem pressure |

Không xử lý mọi lỗi bằng cách tạo imagePullSecret mới. Với Artifact Registry trên GKE, thường nên dùng quyền của node service account đúng repository; registry bên ngoài có thể cần cơ chế khác.

## 11. Artifact Registry: quyền kéo image trên GKE

Đối với image private trong Artifact Registry, node cần danh tính có quyền đọc repository. Trong mô hình GKE phổ biến, **kubelet/container runtime dùng node service account để kéo image**. Workload Identity của Pod dùng cho ứng dụng sau khi container chạy; nó không thay thế quyền pull image của node.

### Kiểm tra node service account

~~~bash
gcloud container clusters describe "CLUSTER_NAME" \
  --location="CLUSTER_LOCATION" \
  --project="PROJECT_ID" \
  --format="yaml(nodeConfig.serviceAccount,nodePools)"
~~~

Định dạng output có thể khác theo cluster mode/node pool. Có thể xem chi tiết node pool:

~~~bash
gcloud container node-pools describe "NODE_POOL" \
  --cluster="CLUSTER_NAME" \
  --location="CLUSTER_LOCATION" \
  --project="PROJECT_ID"
~~~

Xác minh node service account thực tế đang được dùng và IAM policy tại đúng repository.

### Cấp quyền tối thiểu

Ví dụ cấp Artifact Registry Reader ở cấp repository:

~~~bash
gcloud artifacts repositories add-iam-policy-binding "REPOSITORY" \
  --location="REPOSITORY_LOCATION" \
  --project="ARTIFACT_PROJECT_ID" \
  --member="serviceAccount:NODE_SERVICE_ACCOUNT_EMAIL" \
  --role="roles/artifactregistry.reader"
~~~

Chỉ thực hiện khi đã xác minh repository, node service account và approval. Nếu image nằm ở project khác, cấp quyền tại project/repository chứa image. Không cấp Project Owner hoặc Editor để giải quyết image pull.

### Workload Identity khác node identity

- Node identity: phục vụ các hoạt động cấp node như image pull theo cấu hình GKE.
- Workload identity: cấp danh tính cho ứng dụng trong Pod gọi Google Cloud APIs.
- Kubernetes service account: danh tính trong cluster và liên quan RBAC.

Phân biệt ba lớp này giúp tránh cấp quyền cho sai principal.

## 12. Registry bên ngoài, imagePullSecrets và mạng

Nếu image đến từ Docker Hub hoặc registry private khác, kiểm tra cơ chế authentication được nhà cung cấp hỗ trợ. Có thể dùng Kubernetes imagePullSecrets theo namespace, nhưng secret phải được bảo vệ và xoay vòng.

Ví dụ tham chiếu một secret đã được tạo an toàn:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: registry-check
  namespace: app-lab
spec:
  imagePullSecrets:
    - name: external-registry-credentials
  containers:
    - name: check
      image: registry.example.invalid/team/app@sha256:REPLACE_WITH_DIGEST
~~~

Đây là manifest minh họa, domain và digest không phải giá trị triển khai. Không commit nội dung secret vào Git; dùng secret management và GitOps secret integration phù hợp.

### Kiểm tra network

- DNS từ node tới registry.
- Egress firewall và Cloud NAT nếu node dùng private IP.
- Proxy settings và TLS certificate.
- VPC Service Controls hoặc organization policy nếu áp dụng.
- Rate limits và quota của registry.
- Private Google Access/đường truy cập Google APIs theo thiết kế mạng.

Nếu tất cả Pod trên node pool cùng lỗi pull, kiểm tra network/node identity trước khi sửa từng Pod. Nếu chỉ một image lỗi, kiểm tra path/tag/repository permissions trước.

## 13. Kiểm tra IP exhaustion trong GKE VPC-native

GKE VPC-native sử dụng alias IP ranges. Cần phân biệt ba nhóm địa chỉ:

| Loại IP | Phạm vi sử dụng | Nguồn cấp phổ biến |
|---|---|---|
| Node IP | Địa chỉ của VM/node trên VPC | Primary subnet range |
| Pod IP | Địa chỉ cho Pod trên các node | Secondary Pod range |
| Service ClusterIP | Địa chỉ nội bộ cho Kubernetes Service | Secondary Service range hoặc dải được cluster sử dụng |

Một cluster có thể hết Pod IP trong khi primary subnet vẫn còn địa chỉ node IP. Ngược lại, cluster có thể không tạo thêm node vì primary range hoặc quota VM đã hết, dù Pod range vẫn còn.

### Những yếu tố quyết định

- Kích thước primary subnet range.
- Kích thước secondary Pod range và Service range.
- Số node tối đa dự kiến.
- Số Pod tối đa trên mỗi node (maxPodsPerNode).
- Cách GKE cấp Pod CIDR cho từng node.
- Số lượng Service và địa chỉ ClusterIP đã dùng.
- Cụm dùng VPC-native hay mô hình networking khác.

Không lấy một phép tính CIDR đơn giản rồi coi đó là capacity chính xác. GKE cần cấp block cho node theo cấu hình Pod density; lượng địa chỉ dự trữ có thể khác số Pod đang chạy thực tế.

## 14. Nhận diện Pod IP exhaustion

Dấu hiệu:

- Pod ở Pending với event không tạo được Pod sandbox hoặc không cấp IP.
- GKE cluster/network event báo hết địa chỉ trong Pod secondary range.
- Node pool scale được nhưng Pod mới không khởi chạy.
- CNI/Dataplane báo lỗi allocation.
- Số Pod trên node hoặc node pool chạm cấu hình.

Kiểm tra:

~~~bash
kubectl get pods -A -o wide
kubectl get nodes -o wide
kubectl describe pod -n "NAMESPACE" "POD_NAME"
kubectl describe node "NODE_NAME"
~~~

Xem cấu hình IP allocation của cluster:

~~~bash
gcloud container clusters describe "CLUSTER_NAME" \
  --location="CLUSTER_LOCATION" \
  --project="PROJECT_ID" \
  --format="yaml(ipAllocationPolicy,network,subnetwork,defaultMaxPodsConstraint)"
~~~

Xem subnet và secondary ranges:

~~~bash
gcloud compute networks subnets describe "SUBNET_NAME" \
  --region="REGION" \
  --project="PROJECT_ID" \
  --format="yaml(ipCidrRange,secondaryIpRanges,network)"
~~~

Đối chiếu tên Pod secondary range và Service secondary range với cấu hình cluster. Đừng nhầm IP range của một cluster khác trong cùng subnet.

### Xác định đúng điểm cạn

- Pod range hết: không cấp được Pod IP cho node/workload mới.
- Primary range hết: có thể không tạo thêm node VM hoặc tài nguyên dùng primary IP.
- Service range hết: không cấp được ClusterIP mới cho Service.
- Per-node Pod allocation đạt giới hạn: một node không nhận thêm Pod dù toàn subnet còn địa chỉ.
- Node/Pod quota hoặc autoscaler limit: hết capacity do quota/cấu hình, không phải IP.

## 15. Khắc phục Pod IP range thiếu

Trước khi thay đổi:

1. Xác nhận cluster VPC-native và Pod range đang dùng.
2. Kiểm tra IP range có overlap với VPC, peering, VPN, on-prem hoặc subnet khác không.
3. Ước tính node count, max Pods/node và headroom cho tăng trưởng.
4. Kiểm tra tính năng GKE và loại cluster hỗ trợ mở rộng Pod ranges.
5. Lập kế hoạch IaC/network change, maintenance window và rollback.
6. Kiểm tra firewall, routes, peering và security appliances liên quan.

### Những phương án

- **Mở rộng secondary range hiện có** nếu loại subnet/range và điều kiện GKE cho phép; không được overlap với dải khác.
- **Thêm Pod secondary range** và cấu hình cluster/node pool dùng range bổ sung nếu GKE version/mode hỗ trợ.
- **Tạo cluster mới với CIDR được quy hoạch lại** khi cluster cũ có ràng buộc không thể mở rộng an toàn.
- **Điều chỉnh max Pods per node cho node pool mới** khi mật độ Pod hiện tại cao hơn nhu cầu; cần hiểu tác động tới CIDR allocation và scheduling.
- **Giảm Pod không còn cần thiết** hoặc dọn tài nguyên đã kết thúc, nhưng không coi đây là thay thế cho capacity planning.

Các thao tác mở rộng range và thêm Pod ranges có điều kiện cụ thể theo loại cluster, version và cấu hình mạng. Trước khi áp dụng, dùng tài liệu GKE hiện tại và kiểm tra CLI/API hỗ trợ; không chạy một lệnh mở rộng primary subnet với giả định nó tự mở rộng secondary range.

### Cảnh báo về overlap

Không tự chọn một CIDR trông còn trống. Kiểm tra tất cả subnet, peering, VPN, Interconnect và dải mạng on-prem. Một dải Pod mới bị overlap có thể tạo lỗi routing khó chẩn đoán hoặc làm mất kết nối giữa các mạng.

## 16. Khắc phục node IP exhaustion và node pool không scale

Khi autoscaler muốn tạo node nhưng không thành công, kiểm tra:

- Primary subnet range còn đủ địa chỉ không.
- Compute Engine quota theo region/zone.
- Node pool max size và cluster autoscaling limits.
- Resource availability của machine type/zone.
- Reservation, Spot/Preemptible constraints nếu dùng.
- Network tags, service account và node startup configuration.
- Các giới hạn organization policy.

Xem node pool:

~~~bash
gcloud container node-pools list \
  --cluster="CLUSTER_NAME" \
  --location="CLUSTER_LOCATION" \
  --project="PROJECT_ID"
~~~

Xem events và autoscaler status theo giao diện/Cloud Logging của GKE. Thông báo autoscaler có thể nêu lý do như insufficient resources, quota hoặc IP address exhaustion.

### Khôi phục

- Chỉ mở rộng subnet primary range khi đã kiểm tra overlap và giới hạn VPC.
- Xin quota phù hợp nếu quota là nguyên nhân.
- Điều chỉnh autoscaling min/max theo capacity và budget đã duyệt.
- Nếu zone hết capacity, đánh giá node pool/region/zone khác và tác động latency/HA.
- Không ép autoscaler vượt giới hạn hoặc xóa node hiện tại để nhường IP khi chưa rõ workload đang chạy.

## 17. Service IP exhaustion và sự khác biệt với Pod IP

Kubernetes Service loại ClusterIP cần một địa chỉ trong dải Service. Nếu dải này hết, tạo Service mới có thể thất bại dù Pod IP vẫn còn.

Dấu hiệu:

- Tạo Service mới trả lỗi không cấp được ClusterIP.
- Pod đang chạy và có IP, nhưng Service object mới không được tạo đúng.
- Số lượng Service/ClusterIP tiến gần giới hạn dải địa chỉ.

Kiểm tra:

~~~bash
kubectl get services -A
kubectl get services -A -o wide
kubectl describe service -n "NAMESPACE" "SERVICE_NAME"
~~~

Đối chiếu ipAllocationPolicy và Service range của cluster. Không xóa ClusterIP hoặc Service đang hoạt động để giải phóng địa chỉ nếu chưa xác định dependency và thời gian ảnh hưởng.

Giải pháp thường cần quy hoạch lại Service CIDR/cluster hoặc sử dụng kiến trúc cluster mới khi range không thể mở rộng theo điều kiện hiện tại. Việc đổi Service CIDR có thể có ràng buộc lớn; kiểm tra tài liệu GKE và kế hoạch migration trước khi thực hiện.

## 18. Không nhầm IP exhaustion với lỗi Service routing

Pod có IP không có nghĩa Service đã hoạt động. Khi client không gọi được service, kiểm tra theo chuỗi:

1. Pod Ready và có IP.
2. Service selector khớp labels Pod.
3. EndpointSlice chứa Pod endpoint.
4. NetworkPolicy cho phép traffic.
5. CNI/dataplane và kube-proxy/eBPF mode hoạt động.
6. DNS phân giải đúng service name.
7. Firewall/Load Balancer/Ingress route đúng.

Lệnh kiểm tra:

~~~bash
kubectl get svc -n "NAMESPACE"
kubectl get endpointslices -n "NAMESPACE"
kubectl get networkpolicy -A
kubectl get pods -n "NAMESPACE" --show-labels
~~~

Nếu EndpointSlice rỗng, có thể là selector hoặc readiness, không phải hết IP. Nếu Pod có IP nhưng không truy cập được, kiểm tra routing/policy trước khi mở rộng CIDR.

## 19. Quan sát GKE và thiết lập cảnh báo

Một dashboard vận hành nên có ít nhất:

| Nhóm | Tín hiệu | Mục đích |
|---|---|---|
| Node | Memory/Disk/PID pressure, Ready status | Phát hiện node sắp mất khả năng nhận workload |
| Scheduling | Pending Pod, unschedulable reasons | Nhận diện thiếu resource/IP |
| Storage | Ephemeral storage, filesystem, inode | Phát hiện DiskPressure |
| Container | Image pull errors, restart, OOMKilled | Phân loại startup/runtime |
| Network | Pod IP allocation, subnet ranges, Service count | Phát hiện cạn địa chỉ |
| Autoscaling | Desired/current nodes, failed scale-up | Phân biệt quota/IP/capacity |
| App | p95/p99, 5xx, request rate | Đo ảnh hưởng tới người dùng |

Cloud Monitoring có thể cung cấp metrics GKE/Compute Engine và alerting theo cấu hình observability. Tên metric và mức chi tiết phụ thuộc collection mode, agent và phiên bản. Cloud Logging chứa Kubernetes events, node/system logs và autoscaler messages khi các log tương ứng được bật.

### Alert nên báo trước khi chạm ngưỡng

- Memory/disk pressure condition xuất hiện.
- Ephemeral storage hoặc inode tăng bất thường.
- Pod Pending vượt thời gian cho phép.
- Image pull failures tăng theo tỷ lệ.
- Node pool scale-up thất bại.
- Pod/Service IP range còn ít headroom theo capacity plan.
- Số restart/OOMKilled vượt baseline.

Không chỉ cảnh báo khi Pod đã bị evict; cần cảnh báo theo xu hướng và phần capacity còn lại.

## 20. Runbook phối hợp khi nhiều lỗi xuất hiện cùng lúc

Ví dụ sau một release, Pod mới Pending, một số Pod cũ OOMKilled và một số container báo ImagePullBackOff.

Thực hiện theo thứ tự:

1. **Giữ nguyên bằng chứng:** chụp Pod events, node conditions, deployment revision và autoscaler logs.
2. **Xác định blast radius:** namespace, node pool, zone, image và service.
3. **Chặn rollout nếu lỗi do release:** pause/rollback theo quy trình release, không tiếp tục tạo Pod mới.
4. **Tách nguyên nhân:** pressure, image/registry, IP/network.
5. **Bảo vệ workload:** không drain node khi chưa có capacity và PDB; không xóa disk hoặc Pod stateful.
6. **Khắc phục gốc:** sửa resource requests, IAM/image, network hoặc CIDR.
7. **Khôi phục có kiểm soát:** canary một node pool hoặc workload trước.
8. **Xác minh SLO:** Pod Ready, API latency/error, queue và database connections.
9. **Đóng incident:** ghi timeline, root cause, tác động và action items.

### Khi nào rollback?

Rollback phù hợp nếu lỗi bắt đầu ngay sau thay đổi image, resource requests/limits, node selector, toleration hoặc manifest. Nếu lỗi là subnet exhaustion tồn tại từ trước, rollback image không giải quyết được IP. Cần tránh nhiều thay đổi không liên quan cùng lúc vì sẽ làm mất dấu nguyên nhân.

## 21. Phòng ngừa node pressure

- Đặt requests/limits theo profiling và tải đại diện.
- Theo dõi memory working set, GC, disk và inode.
- Đặt ephemeral-storage requests/limits cho workload tạo nhiều file.
- Dùng node pool phù hợp workload và tách batch/heavy jobs khi cần.
- Cấu hình autoscaling có min/max và quota headroom.
- Tránh đặt quá nhiều Pod trên node so với capacity thực.
- Kiểm soát log verbosity, retention và container image size.
- Dùng PDB, topology spread và readiness/liveness probes đúng mục đích.
- Kiểm thử capacity trước khi chạy campaign hoặc batch lớn.
- Có quy trình nâng node image/Kubernetes version và theo dõi sau nâng cấp.

### JVM workload

Với Java/Spring Boot:

- Đặt heap dựa trên container memory limit, không dựa trên RAM của máy lập trình.
- Theo dõi GC pause và native memory.
- Giới hạn thread pools và request concurrency.
- Tránh buffer/file tạm không giới hạn.
- Đặt timeout để request không giữ thread và connection quá lâu.
- Load test khi thay CPU/memory hoặc concurrency.

## 22. Phòng ngừa image pull failure

- Pin image bằng digest cho production.
- Dùng Artifact Registry repository và region được quy hoạch.
- Cấp roles/artifactregistry.reader cho đúng node service account ở đúng repository.
- Tách quyền node image pull và workload runtime identity.
- Kiểm tra image architecture phù hợp node pool.
- Quản lý image retention để không xóa tag/digest đang triển khai.
- Với registry ngoài, dùng imagePullSecrets được quản lý an toàn.
- Kiểm tra DNS, NAT, proxy, TLS và registry rate limits.
- Có pre-deploy check xác minh image tồn tại và có thể pull.
- Theo dõi image pull latency và lỗi trong rollout.

Một image digest bất biến giúp rollback chính xác hơn so với tag có thể bị ghi đè.

## 23. Capacity planning cho Pod, node và IP

Capacity planning phải tính cùng lúc ba lớp:

~~~text
Workload replicas
   |
   +-- Pod requests/limits and max Pods per node
           |
           +-- Node pool size and machine capacity
                   |
                   +-- Primary subnet range for nodes
                   +-- Secondary Pod range
                   +-- Service CIDR/range
~~~

### Bảng ước lượng

Lập bảng cho từng cluster:

| Thông số | Giá trị cần thu thập |
|---|---|
| Node count hiện tại/tối đa | Theo node pool và autoscaler |
| Max Pods per node | Cấu hình thực tế của cluster/node pool |
| Pod secondary range | CIDR, số địa chỉ và phần đã cấp |
| Primary subnet | CIDR và headroom cho node IP |
| Service range | CIDR và số ClusterIP đã sử dụng |
| Pod requests | CPU/memory/ephemeral storage theo workload |
| Quota | Compute, IP/network và các giới hạn liên quan |
| Growth forecast | Tăng trưởng replicas, cluster và peak traffic |

Tính toán nên bao gồm headroom cho rollout surge, autoscaling, node upgrade và zone failure. Nếu chỉ tính số Pod đang chạy hiện tại, cluster có thể hết IP đúng lúc cần scale hoặc nâng cấp.

### Rollout surge

Deployment rolling update có thể tạo thêm Pod tạm thời vượt số replica mong muốn. Capacity plan cần tính maxSurge, PDB, node pool và Pod CIDR allocation; nếu không, bản nâng cấp có thể bị kẹt dù steady-state trước đó đủ chỗ.

## 24. Bài thực hành: xử lý ba lỗi trong cluster lab

Tạo một cluster lab riêng, workload không chứa dữ liệu thật và budget/cleanup được xác định. Thực hành lần lượt, không cố tình làm cạn tài nguyên production.

### Bài A — Memory pressure

1. Deploy một workload test có requests/limits được kiểm soát.
2. Theo dõi kubectl top pods và node conditions.
3. Tạo tải tăng dần trong giới hạn an toàn.
4. Ghi nhận OOMKilled hoặc pressure events nếu xảy ra.
5. Điều chỉnh resource sizing và chạy lại.
6. Xác minh Pod Ready, node ổn định và SLO đạt.

Không cố tình làm node lab mất toàn bộ memory nếu cluster đang dùng chung.

### Bài B — ImagePullBackOff

1. Deploy Pod dùng tag không tồn tại trong registry lab.
2. Đọc event và xác định manifest unknown.
3. Thay image bằng digest tồn tại.
4. Nếu dùng private Artifact Registry, kiểm tra node service account có Reader trên repository.
5. Xác minh Pod pull thành công.
6. Thu hồi mọi quyền test tạm thời sau khi hoàn thành.

### Bài C — IP allocation

1. Đọc ipAllocationPolicy, subnet và secondary ranges của cluster lab.
2. Tính capacity dựa trên max Pods/node và node pool.
3. Quan sát events khi Pod không tạo sandbox do IP allocation.
4. Đối chiếu với node scale-up và primary subnet.
5. Lập phương án thêm Pod range hoặc tạo cluster lab mới với CIDR đủ rộng theo hỗ trợ GKE.
6. Không tự sửa CIDR trên cluster đang chạy nếu chưa có kế hoạch migration/rollback.

### Bài D — Viết báo cáo

Ghi lại:

- Triệu chứng và thời điểm.
- Event/condition đầu tiên.
- Nguyên nhân gốc.
- Thao tác khắc phục.
- Bằng chứng sau khôi phục.
- Cảnh báo hoặc capacity change phòng ngừa tái diễn.

## 25. Checklist phản ứng sự cố

### Node pressure

- [ ] Đã xác định Memory/Disk/PID pressure và node bị ảnh hưởng.
- [ ] Đã xem capacity, allocatable, requests và usage.
- [ ] Đã kiểm tra Pod evicted/OOMKilled và logs.
- [ ] Đã kiểm tra inode/ephemeral storage nếu DiskPressure.
- [ ] Đã kiểm tra PDB, replica và khả năng drain/replace.
- [ ] Đã khôi phục SLO và theo dõi node ổn định.

### Image pull

- [ ] Đã xác minh image path, tag/digest và architecture.
- [ ] Đã đọc Pod events và phân loại registry/network/auth.
- [ ] Đã xác minh node service account đối với Artifact Registry.
- [ ] Đã kiểm tra imagePullSecrets nếu registry ngoài.
- [ ] Đã kiểm tra DNS, egress, proxy, TLS và rate limit.
- [ ] Đã deploy thử và xác minh Pod Ready.

### IP exhaustion

- [ ] Đã phân biệt node IP, Pod IP và Service IP.
- [ ] Đã kiểm tra subnet primary/secondary ranges.
- [ ] Đã xác minh max Pods/node, node pool và autoscaler.
- [ ] Đã kiểm tra quota và capacity zone.
- [ ] Đã kiểm tra CIDR overlap với VPC/peering/VPN/on-prem.
- [ ] Đã có phương án mở rộng/migration được hỗ trợ và phê duyệt.

### Đóng incident

- [ ] Không còn Pod Pending bất thường hoặc pressure conditions.
- [ ] Node pool và autoscaler hoạt động đúng.
- [ ] Image pull thành công cho các workload cần thiết.
- [ ] Service endpoints, network và API SLO được xác minh.
- [ ] Không còn secret/test artifact không cần thiết.
- [ ] Root cause, timeline, owner và preventive actions được ghi lại.

## 26. Tài liệu tham khảo chính thức

- [GKE node auto-repair và node health](https://cloud.google.com/kubernetes-engine/docs/how-to/node-auto-repair)
- [GKE VPC-native clusters và IP address management](https://cloud.google.com/kubernetes-engine/docs/concepts/alias-ips)
- [GKE networking và Pod IP ranges](https://cloud.google.com/kubernetes-engine/docs/how-to/multi-pod-cidr)
- [Kubernetes node pressure và eviction](https://kubernetes.io/docs/concepts/scheduling-eviction/node-pressure-eviction/)
- [Kubernetes container images và image pull](https://kubernetes.io/docs/concepts/containers/images/)
- [Artifact Registry access control](https://cloud.google.com/artifact-registry/docs/access-control)
- [GKE troubleshooting](https://cloud.google.com/kubernetes-engine/docs/troubleshooting)

Tên metric, flags và tính năng networking có thể thay đổi theo GKE mode, version và cluster configuration. Trước khi thay đổi production, đối chiếu tài liệu hiện hành và output thực tế của cluster.

**Kết luận:** Node pressure, image pull failure và IP exhaustion có thể cùng làm Pod không sẵn sàng nhưng cần ba hướng chẩn đoán riêng. Khi kiểm tra conditions/events trước, xác định đúng identity và registry, phân biệt node/Pod/Service IP ranges, rồi khôi phục theo change control và SLO, đội vận hành có thể xử lý sự cố GKE nhanh hơn mà vẫn bảo vệ dữ liệu, workload và khả năng mở rộng lâu dài.


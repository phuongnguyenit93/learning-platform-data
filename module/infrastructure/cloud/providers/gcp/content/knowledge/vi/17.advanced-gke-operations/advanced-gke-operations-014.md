# Tối ưu tài nguyên và chi phí cluster GKE

> **Chương:** GKE nâng cao và vận hành  
> **Mô-đun:** **CLOUD_PROVIDERS_GCP** — Khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành và theo dõi độ tin cậy cùng chi phí.

Một cluster GKE có thể vừa **tốn tiền vì tài nguyên nhàn rỗi** vừa **gặp lỗi lúc tăng tải**. Tối ưu đúng không phải cắt CPU và số node bằng mọi giá: cần đo mức sử dụng thực tế, đặt yêu cầu tài nguyên hợp lý, mở rộng tự động đúng tầng, chọn loại hạ tầng phù hợp và kiểm chứng **SLO/RTO/RPO** sau thay đổi.

Bài học tập trung vào vận hành GKE thực tế: **đo → phân tích → thay đổi có kiểm soát → xác minh chi phí lẫn độ tin cậy**. Ví dụ sử dụng ứng dụng Java API và một batch worker; mọi lệnh thay đổi chỉ dành cho môi trường được cấp quyền.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt chi phí GKE **Standard**, **Autopilot Pod-based** và **Autopilot node-based**.
2. Đọc requests, limits, actual usage, node allocatable, Billing và cost allocation.
3. Chọn và phối hợp **HPA**, **VPA**, **cluster autoscaler**, **node pool auto-creation** và **ComputeClass**.
4. Tối ưu node pools, chọn On-demand/Spot/CUD mà không phá vỡ SLO.
5. Tìm chi phí ẩn từ storage, Load Balancer, cross-zone/region traffic, logs và images.
6. Thiết kế thử nghiệm rightsizing, kiểm tra autoscaling và đo tiết kiệm được xác nhận.
7. Chẩn đoán Pod Pending, OOMKilled, CPU throttling và node không scale down.

## 1. Hiểu hóa đơn trước khi tối ưu

| Thành phần | Điều thường được tính phí | Cách tối ưu |
|---|---|---|
| **GKE Standard** | Node Compute Engine VM, disk, hạ tầng phụ trợ và phí quản lý cluster | Giảm node-hours nhàn rỗi, rightsize Pods/nodes |
| **Autopilot general-purpose** | Nhiều workload dùng **Pod-based billing** theo Pod resource requests hợp lệ | Requests đúng, HPA, chọn ComputeClass phù hợp |
| **Autopilot specialized hardware** | Workload chọn machine series/accelerator có thể **node-based billing** và node management premium | Chọn phần cứng đúng nhu cầu, cải thiện packing |
| **Cluster management** | Phí quản lý theo chính sách/loại cluster; free-tier credits nếu đủ điều kiện | Kiểm kê cluster không dùng, cân nhắc kiến trúc |
| **PersistentVolume/disk, snapshot** | Dung lượng, IOPS/throughput tùy loại, snapshot | Xóa tài nguyên đã xác minh không cần, rightsize |
| **Load Balancer, external IP, egress, NAT** | Forwarding rule, IP, lưu lượng mạng và các SKU liên quan | Tránh LB không cần, giảm cross-zone traffic |
| **Artifact Registry, Logging, Monitoring** | Storage, truy xuất, log/metric ingestion và retention theo điều kiện | Giảm dữ liệu dư thừa có kiểm soát |

**Lưu ý về Autopilot:** một nhãn “Autopilot” không đủ để suy ra cách tính phí. General-purpose Pods thuộc các ComputeClasses được hỗ trợ thường tính theo Pod requests; Pod chọn phần cứng chuyên biệt như GPU, machine series hoặc một số ComputeClasses sử dụng **node-based billing**. Kiểm tra **ComputeClass, hardware và các SKU thật** trước khi so sánh. Không dùng một giá CPU giả định cho mọi cluster.

~~~mermaid
flowchart LR
    BILL["Cloud Billing\nProject, Service, SKU"] --> MODE{"Chế độ + ComputeClass?"}
    MODE -->|"Standard"| NODES["Node VM / disks / network"]
    MODE -->|"Autopilot general-purpose"| PODS["Pod-based requests"]
    MODE -->|"Autopilot specialized"| HARDWARE["Node-based hardware + premium"]
    NODES --> EXTRA["Phí chung: LB, IP, storage, logs"]
    PODS --> EXTRA
    HARDWARE --> EXTRA
~~~

### 1.1. Ba đơn vị cần phân biệt

- **Actual usage:** CPU/memory mà container thực sự tiêu thụ; phục vụ profiling và SLO.
- **Requests:** lượng scheduler dành để đặt Pod; cũng là cơ sở quan trọng để autoscaling và phân bổ chi phí.
- **Limits:** mức giới hạn runtime, đặc biệt memory có thể dẫn tới **OOMKilled**; CPU limit có thể dẫn tới **throttling**.

Trong **Standard**, đặt requests thấp hơn không tự giảm hóa đơn node ngay: cần cluster autoscaler **thực sự loại bớt node** hoặc chuyển workload sang node type rẻ hơn. Trong **Autopilot Pod-based**, requests có thể tác động trực tiếp tới tài nguyên tính phí sau khi GKE áp dụng default/minimum/ratio.

## 2. Lập baseline chi phí và độ tin cậy

Tối ưu mà không có baseline dễ dẫn đến một thay đổi trông tiết kiệm trong vài giờ nhưng gây scale-out, retry, chậm request hoặc downtime về sau.

**Đề xuất cửa sổ đo:** ít nhất **7 ngày** có cả đỉnh lưu lượng và giờ thấp điểm; với batch theo tháng, cần thêm chu kỳ batch đại diện. Ghi mốc trước thay đổi và cùng kỳ sau thay đổi.

| Nhóm chỉ số | Cần quan sát |
|---|---|
| Chi phí | Project/cluster/namespace/Service/SKU, credits, cost per request/job |
| Workload | Requests vs CPU/memory usage p50/p95/p99, OOM/restarts, queue lag |
| Node | Allocatable vs requested, node count theo giờ, Pending Pods |
| Trải nghiệm | Throughput, HTTP error rate, latency p95/p99, availability |
| Scale | HPA desired/current replicas; autoscaler scale-up/down events |
| Phụ trợ | PVC disk capacity, cross-zone egress, LB, log volume |

### 2.1. Lệnh kiểm kê chỉ đọc

~~~bash
PROJECT_ID="YOUR_PROJECT_ID"
CLUSTER="YOUR_GKE_CLUSTER"
LOCATION="asia-southeast1"
NAMESPACE="checkout"

gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --format="yaml(name,location,currentMasterVersion,autopilot,autoscaling,costManagementConfig)"

gcloud container node-pools list \
  --project="$PROJECT_ID" --cluster="$CLUSTER" --location="$LOCATION"

# Chỉ sau khi đã kết nối đúng cluster.
kubectl config current-context
kubectl get nodes -o wide
kubectl get deployments,hpa,vpa,pdb -n "$NAMESPACE"
kubectl get pods -n "$NAMESPACE" -o wide

# Phụ thuộc metrics API; có thể chưa khả dụng.
kubectl top pods -n "$NAMESPACE" --containers
kubectl top nodes
~~~

Lệnh **get vpa** có thể trả lỗi nếu API/resource chưa có hoặc người dùng thiếu RBAC; không mặc định cluster đã bật VPA. **kubectl top** chỉ cho biết mẫu đo hiện tại, không thay cho quan sát lịch sử hoặc distribution p95/p99.

Xem requests và lý do scheduler không đặt được Pod:

~~~bash
kubectl describe deployment checkout-api -n "$NAMESPACE"
kubectl describe nodes
kubectl get events -n "$NAMESPACE" \
  --sort-by=.metadata.creationTimestamp
~~~

**Node capacity không bằng allocatable:** Kubernetes giữ lại tài nguyên cho hệ thống, daemon và giới hạn khác. Khi tính số Pod đặt được, dùng **allocatable**, xem cả CPU, memory, ephemeral storage, IP address, topology và yêu cầu GPU/TPU.

### 2.2. KPI để không tối ưu mù

Một thử nghiệm nên có ít nhất **hai KPI**:

- **Hiệu quả:** cost/request, cost/job hoặc total cost theo cùng mức traffic; node-hours và tỷ lệ unallocated.
- **Độ tin cậy:** p95 latency, HTTP 5xx, OOM/restarts, job completion time, availability.

Nếu chi phí giảm 15% nhưng p95 latency tăng vượt SLO, đó **không phải tối ưu thành công**.

## 3. Rightsize requests và limits trước khi tăng/giảm nodes

Scheduler đặt Pods dựa trên **requests** và các constraints, không dựa vào mức CPU thấp lúc nhàn rỗi. Một Pod request 2 vCPU dù thường chỉ dùng 150m vẫn có thể giữ chỗ khiến cluster phải có thêm nodes.

### 3.1. Đơn vị thường gặp

| Khai báo | Ý nghĩa |
|---|---|
| cpu: 100m | 0,1 vCPU |
| cpu: 500m | 0,5 vCPU |
| cpu: "2" | 2 vCPU |
| memory: 256Mi | 256 MiB |
| memory: 1Gi | 1 GiB |

Ví dụ một API Java có 8 replicas, mỗi Pod request **1000m CPU và 2Gi RAM**: tổng request là **8 vCPU + 16Gi** trước khi tính hệ thống. Sau profiling, nếu có căn cứ giảm CPU request còn **500m**, tổng request CPU thành **4 vCPU**. Tuy nhiên, tiết kiệm tiền chỉ xuất hiện khi workload vẫn đáp ứng latency/throughput và cơ chế billing/node packing thực sự phản ánh phần request giảm.

### 3.2. Manifest tham khảo

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout-api
  namespace: checkout
spec:
  replicas: 3
  selector:
    matchLabels:
      app: checkout-api
  template:
    metadata:
      labels:
        app: checkout-api
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: app
          # Thay bằng image digest có thật đã được kiểm tra.
          image: asia-southeast1-docker.pkg.dev/PROJECT/REPO/checkout-api@sha256:ACTUAL_DIGEST
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
            limits:
              memory: "1Gi"
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 15
~~~

Đây là **manifest minh họa**, chưa sẵn chạy: cần image digest thật, endpoint health được Java app expose, namespace và quyền phù hợp. Trong một số môi trường không đặt CPU limit giúp tránh throttling, nhưng chỉ thực hiện nếu chính sách isolation/quota cho phép; Autopilot có thể áp đặt hoặc điều chỉnh limits theo ComputeClass.

**Đối với JVM:** đo cả **heap + non-heap + direct buffers + thread stacks + native memory**. Đặt memory limit bằng heap size sẽ dễ OOMKilled. Thực hiện load test và quan sát p99/GC pause trước khi thu nhỏ memory request/limit. Google Cloud lưu ý VPA chưa phù hợp để tự động sizing JVM memory do hạn chế nhận diện usage, nên cần kết hợp profiling ứng dụng.

### 3.3. Cách chọn giá trị mới

1. Đo peak/percentile của từng workload qua chu kỳ đại diện.
2. Tách steady-state khỏi cold start, batch spike và incident.
3. Chọn request có **headroom** đủ đáp ứng autoscaling latency, theo chính sách SLO.
4. Kiểm thử memory limit với JVM/OS overhead; theo dõi OOM, throttling và evictions.
5. Rollout từng phần, theo dõi, rồi mới mở rộng.
6. Nếu kết quả xấu, rollback Pod template/IaC; không giảm limits hàng loạt.

Đừng xem **utilization 100%** là mục tiêu bắt buộc. Cần một mức dự phòng cho burst, node maintenance, Pod reschedule và việc bổ sung capacity có độ trễ.

## 4. Bốn cơ chế autoscaling tác động vào các tầng khác nhau

| Cơ chế | Thay đổi gì? | Tín hiệu/điều kiện | Điểm cần cảnh giác |
|---|---|---|---|
| **HPA** (Horizontal Pod Autoscaler) | Số **Pod replicas** | CPU, memory, custom/external metrics | Metrics availability, min/max, cooldown |
| **VPA** (Vertical Pod Autoscaler) | **Requests/limits** mỗi container | Lịch sử resource usage | Có thể cần recreate Pod; xung đột với HPA cùng metric |
| **Cluster autoscaler** | Số **nodes** trong node pool Standard | Pending/unschedulable Pods theo requests, khả năng loại nodes | Min/max, PDB, affinity, local storage, capacity |
| **Node pool auto-creation** | **Node pools** mới phù hợp workloads | Pod specs, ComputeClasses/hardware constraints | Version support, quota, số pool, fragmentation |

~~~mermaid
flowchart TD
    LOAD["Lưu lượng / queue tăng"] --> HPA["HPA tăng replicas"]
    HPA --> PENDING["Pods mới cần được schedule"]
    PENDING --> CA["Cluster autoscaler\nthêm nodes nếu thiếu chỗ"]
    CA --> READY["Pods Ready / phục vụ"]
    HIST["Usage lịch sử"] --> VPA["VPA đề xuất requests"]
    VPA -. "Thay requests sau kiểm thử" .-> PENDING
    CLASS["ComputeClass + node pool auto-creation"] --> CA
~~~

Trong Autopilot, GKE quản lý nodes cho workload theo chế độ/ComputeClass, nên không áp dụng máy móc quy trình chỉnh node pool Standard vào Autopilot.

### 4.1. HPA tính theo requests, không phải CPU limit

Với HPA CPU utilization, tỷ lệ thường là **CPU usage / CPU request**. Ví dụ Pod đang dùng 400m trên request 500m → 80%; với target 60%, HPA có thể đề xuất tăng số replicas (có điều chỉnh theo tolerance, stabilization và dữ liệu thiếu).

Công thức trực giác cho một metric:

\[
\text{desired replicas} \approx
\left\lceil\text{current replicas}\times
\frac{\text{current utilization}}{\text{target utilization}}\right\rceil
\]

Controller thực tế còn tính điều kiện readiness, metrics và giới hạn. Giảm request từ 1000m xuống 500m mà không thay usage có thể làm **utilization HPA tăng**, khiến HPA thêm Pods. Đây là lý do không thể khẳng định giảm request chắc chắn giảm hóa đơn.

### 4.2. VPA và HPA có thể xung đột

VPA làm thay đổi CPU request; HPA dựa trên tỷ lệ usage/request để quyết định replicas. Nếu cả hai tự điều chỉnh **cùng CPU hoặc memory metric**, có thể phát sinh dao động.

Thực hành thận trọng:

- Dùng **VPA ở chế độ Off** để lấy khuyến nghị, review tối thiểu một chu kỳ traffic.
- Với HPA CPU, chỉ tự động áp VPA khi dùng cơ chế phối hợp **HPA rightsizing with VPA (Preview)** hoặc phương án multidimensional được GKE hỗ trợ và đã kiểm thử.
- Hoặc dùng VPA cho workload không chạy HPA cùng metric.
- HPA có thể kết hợp VPA khi HPA dựa trên **custom/external metrics** phù hợp, nhưng vẫn cần giám sát.
- Trên JVM, ưu tiên đo memory ở cấp ứng dụng trước khi tin tưởng tự động thay request.

### 4.3. Cluster autoscaler không đọc trực tiếp CPU “đang nhàn”

Một node đang CPU usage thấp nhưng có Pods request nhiều memory vẫn có thể **không đủ điều kiện scale down**. Cluster autoscaler còn xem liệu Pod trên node đó có thể chuyển sang node khác mà không vi phạm PDB, affinity, taints/tolerations, volume/topology, requests hay giới hạn node pool hay không.

Đặc biệt **không bật Compute Engine autoscaling riêng** cho Managed Instance Groups mà GKE dùng làm node pools: hai bộ điều khiển có thể xung đột với GKE cluster autoscaler.

## 5. Lab có kiểm soát: HPA, requests và ngân sách namespace

**Điều kiện:** dùng cluster lab đã được cho phép, namespace **checkout** và Deployment **checkout-api** đã có, app có image/health endpoints hợp lệ. Không chạy các thay đổi này trên production khi chưa có load test, owner approval và rollout plan.

### 5.1. HPA minh họa (autoscaling/v2)

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: checkout-api
  namespace: checkout
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: checkout-api
  minReplicas: 2
  maxReplicas: 8
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
    scaleUp:
      stabilizationWindowSeconds: 0
~~~

Các giới hạn **2–8** là giới hạn kỹ thuật HPA, **không phải ngân sách tiền tệ**. Nếu mỗi Pod cần CPU request lớn, maxReplicas=8 vẫn có thể đòi tạo node mới. Ngược lại, maxReplicas thấp quá có thể làm latency tăng dù cluster còn dư capacity.

Kiểm tra trước khi apply:

~~~bash
kubectl config current-context
kubectl get deployment checkout-api -n checkout
kubectl get hpa -n checkout
kubectl apply --dry-run=client -f hpa.yaml
~~~

Sau phê duyệt, nếu **hpa.yaml** chứa manifest trên và đúng context:

~~~bash
# THAY ĐỔI: tạo/cập nhật HPA của lab.
kubectl apply -f hpa.yaml

# CHỈ ĐỌC, cần metrics API hoạt động.
kubectl get hpa checkout-api -n checkout -w
kubectl describe hpa checkout-api -n checkout
kubectl top pods -n checkout --containers
~~~

Khi không có traffic hay CPU load, HPA **không tự tăng** đến 8. Muốn quan sát scale up, tạo **bounded load test** trong lab theo quyền được cấp, ghi p95 latency và error rate; đừng dùng một script stress vô giới hạn vào production.

### 5.2. ResourceQuota như ranh giới dung lượng

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: checkout-budget-guard
  namespace: checkout
spec:
  hard:
    requests.cpu: "8"
    requests.memory: 16Gi
    limits.memory: 24Gi
    pods: "30"
~~~

ResourceQuota có thể chặn Pod mới khi aggregate requests/limits vượt quota, giúp tránh một namespace chiếm hết cluster. Nó **không bảo đảm hóa đơn tối đa**: network, disks, node overhead, cluster fee hoặc tài nguyên ngoài namespace vẫn có phí.

**Rủi ro:** quota quá chặt có thể chặn rolling updates và HPA scale-up; cần để headroom cho **maxSurge, crash recovery và batch peak**. Thay đổi quota chỉ sau khi kiểm tra workload hiện có.

### 5.3. Thứ tự thử nghiệm

1. **Baseline**: chụp Deployment, HPA, events, CPU/memory usage, Billing và SLO.
2. **Dự đoán**: tính requests mới, replicas khi traffic đỉnh và node capacity cần có.
3. **Dry-run**: kiểm tra manifest và chính sách admission.
4. **Triển khai ít rủi ro**: canary hoặc một namespace/workload lab; không áp tất cả deployments cùng lúc.
5. **Load test**: xác minh scale up, readiness, p95, retries, backend DB limits.
6. **Scale down**: giảm traffic, quan sát HPA stabilization và sau đó node autoscaler.
7. **Đối chiếu**: node-hours/Pod-request-hours, Cloud Billing đã ghi nhận và errors.
8. **Rollback** nếu SLO suy giảm, hoặc commit IaC/GitOps nếu đạt.

HPA target thay đổi và sửa CPU requests là **hai thay đổi tác động lẫn nhau**; nên thực hiện tách bước để dễ truy nguyên.

## 6. Tối ưu node pools trong GKE Standard

### 6.1. Vì sao “CPU usage thấp” chưa đủ để xóa node?

Ví dụ 6 node cùng machine type, mỗi node có 4 vCPU và 16 GiB RAM. Tổng capacity lý thuyết **24 vCPU + 96 GiB**, nhưng allocatable thấp hơn do hệ thống. Nếu tổng Pod requests là 10 vCPU và 60 GiB, CPU có vẻ dư nhiều trong khi memory và topology có thể khiến chỉ có một vài nodes trống thật sự.

Cần xét **bin packing** theo đồng thời CPU/memory, số Pod/IP, topology, storage, taints, affinity và PDB. Không dùng phép tính **10/24 vCPU ≈ 42%** để suy ngay có thể giảm 58% node costs.

### 6.2. Node pool autoscaling và min/max

~~~bash
# CHỈ ĐỌC: node pools và cấu hình cluster.
gcloud container node-pools list \
  --project="$PROJECT_ID" --cluster="$CLUSTER" \
  --location="$LOCATION"

gcloud container node-pools describe "NODE_POOL_NAME" \
  --project="$PROJECT_ID" --cluster="$CLUSTER" \
  --location="$LOCATION" --format=yaml
~~~

Trong Standard:

- Chọn **min nodes** đủ cho capacity khi sự cố/maintenance; min quá cao giữ node idle.
- **Max nodes** phải phục vụ peak, nhưng không thay cho Cloud Billing Budget/Alert.
- Cluster autoscaler mở rộng khi **Pods không schedule được**, và giảm khi Pod có thể chuyển nơi an toàn.
- Node pool **từ vùng khác/GPU/arch khác** không mặc nhiên nhận mọi Pod; scheduling constraints cần phù hợp.
- Với một số **GKE versions mới** có tính năng **scale Standard cluster xuống 0 node khi idle** theo điều kiện và cấu hình riêng; không giả định mọi Standard cluster cũ tự scale về 0. Cần xem GKE version/feature availability trước khi thiết kế dev cluster ban đêm.

Ví dụ thay đổi node pool autoscaling **chỉ sau phê duyệt**:

~~~bash
# THAY ĐỔI HẠ TẦNG — min/max là ví dụ, không copy vào prod.
gcloud container clusters update "$CLUSTER" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --autoscaling-profile=optimize-utilization
~~~

Profile **optimize-utilization** có thể ưu tiên packing và scale-down mạnh hơn **balanced** (Standard). Nó có thể tăng số lần Pod bị di chuyển và thời gian chờ scale-up; cần đo readiness, PDB và SLO sau khi dùng. Không thay profile vì “chắc tiết kiệm” mà chưa xem cluster actual usage.

### 6.3. Node pool auto-creation và ComputeClass

**Node pool auto-creation** giúp GKE Standard tạo node pools mới phù hợp requests/accelerators, thay vì người vận hành luôn tạo sẵn pool. Có hai cách cấu hình chính:

- **Workload-level ComputeClass** (khuyến nghị ở GKE versions hỗ trợ): Pod yêu cầu ComputeClass và GKE tự tạo pool phù hợp.
- **Cluster-level node auto-provisioning**: cấu hình toàn cluster, có các resource limits và điều kiện phiên bản riêng.

Theo tài liệu hiện hành, ở GKE **1.33.3-gke.1136000+**, ComputeClass có thể bật node pool auto-creation mà không cần cluster-level node auto-provisioning. Ở các bản thấp hơn, cần bật cluster-level mechanism. Đó là **điều kiện theo phiên bản**, không nên sao chép policy sang cluster khác mà không kiểm tra.

Khi có nhiều ComputeClasses/node pools, phải tránh phân mảnh: những pool chỉ phục vụ 1–2 Pods hoặc affinity quá cụ thể có thể ngăn scale-down và tăng chi phí. Các selector/taints hữu ích cho isolation nhưng không miễn phí về mặt packing.

### 6.4. Cân bằng packing và availability

| Chỉnh sửa | Lợi ích | Rủi ro |
|---|---|---|
| Ít node pools hơn, machine phù hợp | Packing tốt hơn | Giảm tách biệt workload hoặc hardware choices |
| Node pool đa zone | Chịu lỗi zone tốt hơn | Cross-zone traffic/overhead cao hơn |
| Strict anti-affinity | Hạn chế đặt chung một node | Có thể sinh node nhàn rỗi |
| TopologySpreadConstraints | Phân bổ replica theo node/zone | Có thể làm scheduler khó đặt Pod |
| PDB | Giảm disruption tự nguyện | Ngăn drain/scale-down khi quá chặt |
| Node auto-creation | Phù hợp hardware theo nhu cầu | Thêm pools/churn nếu workload quá phân mảnh |
| optimize-utilization | Giảm nodes nhàn rỗi | Scale-down disruption và scale-up latency |

Đừng tắt **PDB** hoặc giảm số replicas critical service chỉ để ép node autoscaler scale down. Nên tối ưu requests/scheduling constraints và giữ đủ capacity cho rollout.

## 7. Compute choices: On-demand, Spot, CUD và Autopilot

### 7.1. Chọn theo khả năng chịu gián đoạn

| Loại workload | Tùy chọn nên cân nhắc | Điều kiện |
|---|---|---|
| API quan trọng, luôn phục vụ | On-demand / CUD cho baseline | Multi-zone, readiness, SLO, PDB |
| Batch xử lý lại được | **Spot nodes/Spot Pods** | Checkpoint, retry, idempotency, graceful shutdown |
| Worker theo queue có burst lớn | HPA/KEDA-compatible + Spot phần dự phòng | Không để queue durability chỉ trong Pod |
| Tải biến động, ít người vận hành nodes | Autopilot general-purpose | Kiểm tra Pod-based vs node-based billing |
| GPU inference/training | ComputeClass/hardware phù hợp | Tối ưu accelerator utilization, quota, image, batch sizing |
| Workload dài hạn ổn định | CUD hoặc commitment phù hợp | Dự báo baseline và hợp đồng, không mua chỉ theo peak |

Spot VMs/Pods có **giá thấp hơn** nhưng có thể bị thu hồi bất kỳ lúc nào và không có bảo đảm availability như On-demand. Trong Autopilot, Spot Pods được GKE quản lý trên Spot VMs; trên Standard, node pools/ComputeClasses có thể chọn Spot theo cấu hình. Không đặt primary database hoặc dịch vụ thanh toán không chịu được interruption lên Spot chỉ vì chênh lệch giá.

### 7.2. Spot manifest minh họa

Trên **Autopilot** khi dùng cách chọn Spot Pods được hỗ trợ, trong Pod template có thể thêm:

~~~yaml
spec:
  template:
    spec:
      nodeSelector:
        cloud.google.com/gke-spot: "true"
      containers:
        - name: worker
          image: asia-southeast1-docker.pkg.dev/PROJECT/REPO/worker@sha256:ACTUAL_DIGEST
          resources:
            requests:
              cpu: "500m"
              memory: "1Gi"
~~~

Đây là **trích đoạn Pod template**, không phải Deployment hoàn chỉnh. Đọc tài liệu GKE/ComputeClass của cluster; trong Autopilot, hệ thống tự gán taints/tolerations tương ứng cho Spot Pods. Trên Standard, phải đảm bảo đã có node pool/ComputeClass Spot tương thích và Pod scheduling rules đúng.

Ứng dụng cần xử lý **SIGTERM**, checkpoint và retry; đừng cho rằng nó luôn có đủ thời gian hoàn thành mọi job sau preemption notice.

### 7.3. CUD, reservation, architecture và phiên bản image

- **Committed Use Discounts** có thể tiết kiệm cho baseline ổn định theo hợp đồng, nhưng cam kết vẫn có nghĩa vụ chi phí khi workload giảm. Không mua cam kết cho peak ngắn hạn chưa dự báo tốt.
- **Reservations** đảm bảo capacity theo điều kiện, không tự biến mọi resource thành miễn phí; kiểm tra bill và cách dùng trong GKE.
- So sánh **E2/N2/C4/ARM-based** theo workload CPU/memory ratio và hiệu năng thực, không chỉ giá/vCPU.
- Khi đổi architecture sang ARM64, bảo đảm container image **multi-arch**, native libraries/JNI của Java và dependencies có bản tương thích.
- Đo **cost per transaction** và SLO sau khi đổi machine family; không so mỗi giá thuê node.

## 8. Chi phí ngoài CPU và RAM

| Nguồn tăng phí | Cách phát hiện | Hướng xử lý |
|---|---|---|
| **LoadBalancer Service** không còn dùng | Liệt kê Services và Google Cloud forwarding rules | Xóa đúng Service theo ownership, tránh xóa LB đang chia sẻ |
| **PVC/PV** còn giữ sau xóa workload | PVC/PV reclaim policy, disks list, Billing | Xác minh backup, owner/retention rồi dọn |
| **Cross-zone/region traffic** | Network egress SKUs, topology metrics | Co-locate khi phù hợp mà không phá HA |
| **Cloud NAT/external IP** | NAT metrics, address inventory, SKU | Chọn topology/địa chỉ hiệu quả, không tắt NAT gây pull lỗi |
| **Container images lớn** | Artifact Registry size/pulls | Multi-stage builds, images nhỏ, kiểm tra digest |
| **Log verbosity/cardinality cao** | Logging ingestion, metrics custom | Lọc log ít giá trị, giới hạn labels/cardinality, giữ audit cần thiết |
| **GKE system/DaemonSet overhead** | Per-node allocatable và DaemonSet requests | Không xóa agent quan trọng; xem số nodes/pools |
| **GPU/Local SSD nhàn rỗi** | Accelerator/device metrics | Dùng hardware chuyên biệt chỉ nơi cần |
| **Cluster dev luôn bật** | Node-hours theo giờ thấp điểm | Quy trình tắt/scale hợp lệ nếu không có dữ liệu/khách hàng phụ thuộc |

Service **ClusterIP** không tự tạo Google Cloud L4 load balancer; Service **LoadBalancer** có thể phát sinh phí forwarding rules/IP ngay cả khi ít request. Cấu hình **Ingress/Gateway** có thể tạo Application Load Balancer và resources riêng. Phải kiểm kê hạ tầng Google Cloud do controller tạo, không chỉ đếm Kubernetes objects.

Đối với PersistentVolume, hãy hiểu **reclaimPolicy=Retain/Delete**, backup và owner; không xóa volume theo một lệnh tìm kiếm chung rồi cho rằng dữ liệu không quan trọng.

## 9. GKE cost allocation và Cloud Billing BigQuery export

Trong cluster đa nhóm, nhìn tổng phí Compute Engine chưa đủ để biết **namespace nào chiếm phần lớn tài nguyên**. **GKE cost allocation** (trên cluster/chế độ hỗ trợ) gắn thông tin cluster, namespace và workload vào Cloud Billing, nhưng không bao phủ mọi SKU và không tính trực tiếp phí trên mỗi request.

### 9.1. Kiểm tra trước khi bật

~~~bash
gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --format="yaml(costManagementConfig)"
~~~

Với **Standard** cluster đủ điều kiện, quản trị viên có thể bật:

~~~bash
# THAY ĐỔI CLUSTER — chỉ chạy khi đã được phê duyệt.
gcloud container clusters update "$CLUSTER" \
  --project="$PROJECT_ID" --location="$LOCATION" \
  --enable-cost-allocation
~~~

Dữ liệu có thể cần **tới vài ngày** mới xuất hiện trong Billing, không hồi tố mọi chi phí trước khi bật. Không giả định cách bật và giới hạn Standard hoàn toàn giống tất cả Autopilot clusters.

### 9.2. Các nhãn phân bổ

| Nhãn trong billing export | Ý nghĩa |
|---|---|
| **goog-k8s-cluster-name** | Tên cluster |
| **k8s-namespace** | Namespace |
| **k8s-workload-type / k8s-workload-name** | Kiểu và tên workload |
| **k8s-label/KEY** | Kubernetes labels được hỗ trợ |
| **kube:unallocated** | Phần tài nguyên chưa được phân bổ vào workload |
| **kube:system-overhead** | Phần node dành cho hệ thống |

Giá trị **goog-k8s-unsupported-sku**, **goog-k8s-unknown** hoặc null cần được báo cáo riêng. Một chi phí không có namespace **không phải chi phí bằng 0**. PV/PVC và một số loại workload có giới hạn phân bổ riêng. GKE cost allocation có thể tăng dung lượng và chi phí BigQuery do số lượng tổ hợp namespace/labels.

### 9.3. SQL: tổng phí ròng theo namespace

Dùng **Cloud Billing detailed export** đã cấu hình và quyền BigQuery phù hợp. Thay project/dataset/table/date. Truy vấn có thể phát sinh phí BigQuery.

~~~sql
-- CHỈ ĐỌC. Không UNNEST labels trực tiếp để tránh nhân dòng cost.
WITH bill_rows AS (
  SELECT
    project.id AS project_id,
    COALESCE(
      (SELECT l.value FROM UNNEST(labels) AS l
       WHERE l.key = 'goog-k8s-cluster-name' LIMIT 1),
      'unattributed'
    ) AS cluster_name,
    COALESCE(
      (SELECT l.value FROM UNNEST(labels) AS l
       WHERE l.key = 'k8s-namespace' LIMIT 1),
      'unattributed'
    ) AS namespace,
    cost + COALESCE(
      (SELECT SUM(c.amount) FROM UNNEST(credits) AS c), 0
    ) AS net_cost
  FROM `YOUR_BILLING_PROJECT.YOUR_DATASET.gcp_billing_export_resource_v1_XXXX`
  WHERE usage_start_time >= TIMESTAMP('2026-11-01')
    AND usage_start_time < TIMESTAMP('2026-12-01')
)
SELECT project_id, cluster_name, namespace,
       ROUND(SUM(net_cost), 2) AS net_cost
FROM bill_rows
GROUP BY project_id, cluster_name, namespace
ORDER BY net_cost DESC;
~~~

**Giải thích:** scalar subqueries lấy nhãn/credits trên từng dòng, tránh nhân cost bởi nhiều nhãn. **credits.amount** có thể âm. Thuế, adjustments và kỳ hóa đơn có semantics riêng: để đối soát invoice, dùng **Cost table** và đúng invoice period. Phân tích hiệu quả cần ghép net cost với throughput/request count cùng cửa sổ thời gian.

Không đưa user ID/transaction ID vào Kubernetes Pod labels để chia phí: cardinality cao có thể làm dữ liệu Billing export phình to.

### 9.4. Dashboard tối thiểu

| KPI | Cách xác định |
|---|---|
| Cost per successful request/job | Net workload cost / số request/job thành công cùng kỳ |
| Node-hours | Tổng giờ node VM theo pool/type |
| Requests/allocatable | Tổng CPU, memory requests / node allocatable |
| Unallocated share | Chi phí chưa phân bổ / tổng chi phí trong phạm vi |
| Scaling health | Pending Pods, HPA/CA errors, scale-down blockers |
| Reliability | p95/p99 latency, 5xx, OOM, retry |

**Requests/allocatable không phải actual utilization.** Cần xem CPU và memory riêng, không quy thành một tỷ lệ tổng duy nhất.

## 10. Runbook tối ưu có thể rollback

~~~mermaid
flowchart TD
    B["Baseline: Billing + usage + SLO"] --> D["Chọn một giả thuyết đo được"]
    D --> P["Kiểm tra Pods, nodes, PDB và rollback"]
    P --> C["Canary/lab change"]
    C --> V{"SLO và hiệu quả đạt?"}
    V -- "Không" --> R["Rollback, ghi nhận nguyên nhân"]
    V -- "Có" --> E["Mở rộng bằng IaC/GitOps"]
    E --> M["Đo 7-14 ngày, đối chiếu Billing"]
    M --> B
~~~

1. **Ưu tiên** top workloads/pools/SKUs có chi phí cao; xác nhận owner.
2. **Baseline** 7 ngày hoặc chu kỳ batch tương ứng: usage percentiles, requests, events, Billing và SLO.
3. **Giả thuyết** cụ thể, ví dụ giảm CPU request 1000m → 600m để tăng packing mà p95 latency vẫn đạt.
4. **Guardrails:** canary, PDB, image digest, IaC version và rollback path.
5. **Thay đổi một biến mỗi lần**; không đồng thời đổi CPU request, HPA target, node pool và topology.
6. **Kiểm chứng** scale-up, scale-down, OOM, retry, latency và hoàn tất jobs.
7. **Đối chiếu** cost/request hoặc cost/job trên lưu lượng tương đương sau billing lag.
8. **Chốt/rollback** và lưu kết quả vào change record.

Mẫu ticket tối thiểu:

~~~text
WORKLOAD / OWNER / PROJECT / CLUSTER:
HYPOTHESIS:
BASELINE_WINDOW:
CURRENT_REQUESTS / PROPOSED_REQUESTS:
HPA / VPA / NODE_POOL_SETTINGS:
SLO_GUARDRAILS: p95, 5xx, OOM, Pending Pods
ROLLBACK: GitOps revision + image digest
COST_METRIC / TRAFFIC_WINDOW:
RESULT / APPROVER:
~~~

## 11. Chẩn đoán vì sao chi phí không giảm

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra |
|---|---|---|
| CPU usage thấp nhưng node không giảm | Memory requests, PDB, min nodes, affinity, volume | describe nodes; autoscaler logs |
| Pod **Pending** lâu | Quota, IP range, max nodes, hardware/taints | describe pod, cluster constraints |
| HPA hiển thị **unknown CPU** | Metrics API lỗi hoặc thiếu CPU requests | describe hpa, metrics server |
| HPA và VPA dao động | Cả hai tự chỉnh cùng metric | VPA mode, HPA metrics |
| Scale Pods nhưng app vẫn chậm | DB pool, queue, throttling, cold start | tracing, p99, DB metrics |
| OOMKilled sau rightsizing | JVM heap + native memory vượt limit | Pod lastState, logs --previous |
| Batch xong mà nodes chưa giảm | PDB, PV/local storage, DaemonSets hoặc pool min | get pods -A, autoscaler visibility |
| Spot batch retry nhiều | Preemption/thiếu capacity | checkpoint interval, events |
| Hóa đơn còn cao sau giảm replicas | Standard nodes/LB/disks/IP/logs vẫn có phí | Billing theo SKU |
| Cross-zone egress tăng | Pod/DB placement và traffic pattern | Network SKUs, topology |

~~~bash
# CHỈ ĐỌC.
kubectl get pods -A -o wide
kubectl describe hpa checkout-api -n checkout
kubectl describe deployment checkout-api -n checkout
kubectl get pdb -A
kubectl get pvc -A
kubectl get pv
kubectl get events -A --sort-by=.metadata.creationTimestamp
~~~

Nếu node không scale down, dùng **Cluster Autoscaler Visibility Logs** trong Cloud Logging để xem noScaleDown và blockers. Không xóa nodes thủ công khi GKE đang quản lý node pool.

**Ví dụ:** 6 nodes mỗi node CPU usage 20%, nhưng một Pod request memory lớn cùng PDB **minAvailable=6** ngăn việc chuyển Pod. Tắt PDB để ép scale-down có thể phá SLO; cách hợp lý là kiểm chứng memory request, node allocatable, topology và tính khả thi của việc dồn Pods.

## 12. Case study: API Java và nightly batch

**Bối cảnh giả định:** một GKE Standard regional cluster có:

- **checkout-api:** 6 replicas, request 1 vCPU và 2Gi mỗi Pod; HPA target CPU 60%.
- **Nightly batch:** 10 Pods, request 500m CPU và 1Gi RAM, chạy vài giờ.
- **Node pools:** 3 pools phần cứng gần giống nhau, min nodes tương đối cao.
- **Billing:** phần lớn phí nằm ở node VM, persistent disks và network egress.

### 12.1. Từ quan sát tới quyết định

| Quan sát | Giả thuyết cần kiểm thử | Điều kiện an toàn |
|---|---|---|
| Java CPU request lớn hơn usage đại diện | Giảm request từng bước để tăng packing | p99/GC/OOM và HPA phải đạt |
| Batch có input/output ở Cloud Storage | Chuyển phần retry được sang Spot | Checkpoint, idempotency và deadline |
| Node pools phân mảnh, min cao | Điều chỉnh min và xét auto-creation | PDB, topology và capacity |
| Pod xóa nhưng PVC còn | Kiểm kê disk/snapshot theo owner | Backup, retention, reclaimPolicy |
| DB liên zone gây egress cao | Kiểm tra locality theo topology | Không làm giảm HA/DR |
| Debug logs của batch quá nhiều | Giảm thông tin ít giá trị | Giữ audit và dữ liệu điều tra lỗi |

### 12.2. Ước tính minh họa, không phải giá Google Cloud

Giả sử 12 nodes có giá compute giả định **10 đơn vị/ngày/node**, các phí khác **50 đơn vị/ngày**. Khi kiểm chứng workload duy trì SLO với 9 nodes, và giả sử các phí khác không đổi:

\[
\begin{aligned}
C_{\text{trước}} &= 12 \times 10+50=170\\
C_{\text{sau}} &= 9 \times 10+50=140\\
\text{Tiết kiệm} &= (170-140)/170 \approx 17{,}6\%
\end{aligned}
\]

Giảm 25% node count trong tình huống này chỉ tương đương **17,6% tổng phí**, chưa kể chi phí Spot retries, egress, Logging hoặc discounts thay đổi. **Chỉ xem là tiết kiệm thực khi đo hóa đơn và traffic thực tế cùng kỳ.**

### 12.3. Điều kiện nghiệm thu

- Cost/request hoặc cost/job giảm với traffic so sánh được.
- p95/p99 latency, error rate và availability vẫn trong SLO.
- Batch hoàn thành trước deadline, retry được sau Spot preemption.
- Không có OOM hoặc Pending Pods kéo dài.
- Multi-zone distribution, PDB, IAM và chính sách backup vẫn đạt.
- Có phiên bản IaC/GitOps và dashboard theo dõi để rollback nếu cần.

## 13. Bài tập và câu hỏi tự kiểm tra

### 13.1. Chọn đúng cơ chế

| Tình huống | Đáp án định hướng |
|---|---|
| API tăng CPU load và cần thêm Pods | HPA |
| Cần khuyến nghị CPU/memory requests | VPA Off/recommendation |
| Standard cluster thiếu nodes để schedule Pods | Cluster autoscaler |
| Cần GKE tạo node pool mới phù hợp ComputeClass | Node pool auto-creation |
| Batch có checkpoint và chấp nhận gián đoạn | Spot |
| Tải ổn định dài hạn, dự báo được | Đánh giá CUD |
| Phân bổ chi phí đa nhóm theo namespace | GKE cost allocation/BigQuery export |
| Phí LB/IP còn dù request bằng 0 | Inventory LB, external IP, forwarding rules |

### 13.2. Tính toán

1. Deployment có 5 Pods, CPU request mỗi Pod **800m**. Tổng CPU requests?
2. HPA có 4 replicas, current utilization **90%**, target **60%**. Công thức gần đúng đề xuất bao nhiêu replicas?
3. CPU usage mỗi Pod **300m**; request đổi từ **600m** xuống **300m**. Tỷ lệ utilization của HPA thay đổi thế nào?
4. Phí ngày trước **200 đơn vị**, sau **175 đơn vị**, traffic và SLO tương đương. Giảm bao nhiêu phần trăm?
5. Vì sao actual CPU usage 10% không bảo đảm cluster autoscaler xóa được node?

**Đáp án:** (1) 4 vCPU; (2) khoảng 6 replicas trước các điều chỉnh controller; (3) từ 50% lên 100%, HPA có thể tăng replicas; (4) 12,5%; (5) do requests, memory, pool min, PDB, topology/affinity, volume hoặc khả năng chuyển Pods.

### 13.3. Câu hỏi thiết kế

- Vì sao giảm CPU request trên **Standard** chưa chắc làm chi phí giảm ngay?
- Trong Autopilot, điều kiện nào dẫn tới Pod-based so với node-based billing?
- Khi nào HPA + VPA cùng tồn tại gây xung đột? Biện pháp kiểm soát?
- Spot có phù hợp chạy primary transactional database không? Vì sao?
- Có nên phân bổ toàn bộ **kube:unallocated** cho một team không nếu chưa có quy tắc FinOps?
- Cần những metric nào để chứng minh tối ưu thực sự giảm cost per successful request?

**Hướng trả lời:** đối chiếu cơ chế billing, scheduler/controller, durability, SLO và actual usage/traffic cùng chu kỳ trước–sau. Không suy tiết kiệm từ việc giảm một con số requests đơn lẻ.

## 14. Tài liệu chính thức và checklist

- [GKE best practices: Cost optimization](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/cost-optimization)
- [GKE pricing](https://cloud.google.com/kubernetes-engine/pricing)
- [Autopilot overview và billing modes](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview)
- [Autopilot resource requests](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-resource-requests)
- [Horizontal Pod autoscaling](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/horizontalpodautoscaler)
- [Vertical Pod autoscaling](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/verticalpodautoscaler)
- [Cluster autoscaler](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler)
- [Node pool auto-creation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/node-auto-provisioning)
- [GKE cost allocation](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/cost-allocations)
- [Autopilot Spot Pods](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/autopilot-spot-pods)
- [Standard Spot VMs](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/spot-vms)
- [Troubleshoot cluster autoscaler scale-down](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/cluster-autoscaler-scale-down)

**Checklist áp dụng:** đúng cluster/context/owner → baseline Billing và SLO → rightsize requests/limits → chọn HPA/VPA → node packing/ComputeClass → Spot/CUD có kiểm soát → storage/network/logging → thử nghiệm canary → đo SLO và hóa đơn → chốt hoặc rollback.

**Kết nối với lộ trình CLOUD_PROVIDERS_GCP:** tối ưu GKE đòi hỏi kiến thức Compute Engine, IAM/Artifact Registry, VPC, lưu trữ, Cloud Billing và Cloud Monitoring. Mục tiêu cuối là **chi phí hợp lý cho mỗi công việc hoàn thành thành công**, không đánh đổi tính sẵn sàng, bảo mật hoặc khả năng phục hồi.








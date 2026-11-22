# Requests, limits và lập lịch workload trên GKE

> **Chương:** GKE cơ bản  
> **Bài học:** Requests, limits và lập lịch workload trên GKE  
> **Mô-đun:** CLOUD_PROVIDERS_GCP

Trong mô-đun **CLOUD_PROVIDERS_GCP**, người học khám phá Google Cloud từ tổ chức project, IAM và VPC đến Compute Engine, Google Kubernetes Engine (GKE), Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Qua các tình huống triển khai, người học cần biết lựa chọn dịch vụ, bảo vệ tài nguyên, tự động hóa phát hành, theo dõi độ tin cậy và tối ưu chi phí. Với **GKE**, những mục tiêu đó gắn trực tiếp với ba câu hỏi: **một Pod cần bao nhiêu tài nguyên, Kubernetes đặt Pod ở node nào, và điều gì xảy ra khi ứng dụng dùng nhiều hơn dự kiến?**

Kubernetes dùng **resource requests** để ra quyết định lập lịch, **resource limits** để giới hạn mức sử dụng lúc chạy và các **scheduling constraints** để đặt Pod lên node có đặc tính phù hợp. Trong GKE Standard, bạn quản lý node pools và cấu hình autoscaler. Với GKE Autopilot, Google Cloud quản lý nhiều chi tiết hạ tầng, đồng thời áp dụng các quy tắc riêng cho CPU, memory, ephemeral storage và loại phần cứng được chọn.

**Điểm cần nhớ ngay từ đầu:** tăng `limits.cpu` không giúp Pod hết `Pending` nếu **`requests.cpu`** không thể được đáp ứng. Tăng node count cũng không sửa được một `nodeSelector` sai. Và một Pod `Running` không có nghĩa Java API đủ RAM, không bị CPU throttling hoặc đã đạt SLO.

Tất cả project, namespace, cluster, image và số liệu trong bài là ví dụ. Các manifest/lệnh có thể tạo workload và phát sinh phí nếu áp vào cluster thật; chỉ thực thi trong môi trường được cấp quyền. Thứ tự hướng dẫn đi từ quan sát đến thiết kế, sau đó mới thử nghiệm có kiểm soát.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích `resources.requests` và `resources.limits` cho **CPU, memory và ephemeral-storage**.
2. Phân biệt **Node Capacity**, **Node Allocatable** và nguồn tài nguyên scheduler còn có thể gán cho Pods.
3. Dự đoán vì sao Pod `Pending` do `Insufficient cpu`, `Insufficient memory`, `Too many pods` hoặc constraint không khớp.
4. Mô tả **CPU throttling**, **OOMKilled**, **eviction** và các lớp QoS **Guaranteed, Burstable, BestEffort**.
5. Sử dụng nodeSelector, node affinity, Pod affinity/anti-affinity, taints/tolerations và topology spread constraints đúng mục đích.
6. Phân biệt tài nguyên và quyền kiểm soát trong **GKE Standard** với **GKE Autopilot**.
7. Kết hợp **Horizontal Pod Autoscaler (HPA)**, **Vertical Pod Autoscaler (VPA)** và **Cluster Autoscaler** mà không nhầm phạm vi.
8. Thiết kế Deployment cho **Java Orders API** với requests, limits, probes, nhiều replicas và phân bố theo zone.
9. Dùng `kubectl`, Google Cloud Console và Cloud Monitoring để điều tra tình huống scheduling, throttling, memory pressure.
10. Lựa chọn resource settings phù hợp với độ tin cậy, quota, khả năng mở rộng và chi phí.

## 2. Luồng lập lịch của Kubernetes trên GKE

~~~mermaid
flowchart TD
    Commit["CI/CD áp Deployment<br/>Orders API"] --> API["Kubernetes API server"]
    API --> RS["Deployment / ReplicaSet<br/>tạo Pods"]
    RS --> Pod["Pod chưa gán node"]
    Pod --> Scheduler["kube-scheduler"]
    Scheduler --> Filter["Lọc node<br/>requests + constraints"]
    Filter --> Score["Chấm điểm node khả thi"]
    Score --> Bind["Gán Pod vào node"]
    Bind --> Kubelet["kubelet + container runtime"]
    Kubelet --> Run["Java container chạy<br/>cgroups + probes"]
    HPA["HPA: số replicas"] -. "thay đổi Deployment" .-> RS
    CA["Cluster Autoscaler / Autopilot<br/>năng lực node"] -. "mở rộng node" .-> Filter
~~~

Từng thành phần làm một việc riêng:

- **Deployment/ReplicaSet** đảm bảo số Pod mong muốn theo template.
- **Scheduler** chọn node cho Pod chưa được gán, xem các tài nguyên được **request**, tập node đủ điều kiện và các quy tắc placement.
- **Kubelet** trên node chạy container, quan sát trạng thái và phối hợp runtime/kernel thực thi giới hạn tài nguyên.
- **HPA** điều chỉnh số Pod dựa trên metric khi có cấu hình.
- **Cluster Autoscaler** trong GKE Standard có thể bổ sung/thu hồi node theo nhu cầu tài nguyên và điều kiện; **Autopilot** quản lý năng lực node theo cách riêng.

**Scheduler không đợi CPU utilization thực tế lên 90% mới quyết định Pod nào có thể đặt.** Nó chủ yếu dùng *requests đã khai báo* cùng với allocatable và quy tắc scheduling. Do đó một cluster CPU usage thấp vẫn có thể không đặt được Pod mới nếu phần lớn CPU allocatable đã được các Pods khác request.

## 3. Requests và limits: ý nghĩa và cú pháp

### 3.1. Một container có hai bộ giá trị

~~~yaml
resources:
  requests:
    cpu: "500m"
    memory: "768Mi"
    ephemeral-storage: "1Gi"
  limits:
    cpu: "1000m"
    memory: "1536Mi"
    ephemeral-storage: "2Gi"
~~~

| Thuộc tính | Vai trò chính | Hệ quả điển hình |
|---|---|---|
| `requests.cpu` | Dự trù CPU khi scheduler chọn node; trọng số chia sẻ CPU lúc tranh chấp | Pod `Pending` nếu node thiếu CPU request còn trống |
| `limits.cpu` | Trần thời gian CPU cho container | Khi đạt trần, container có thể bị **CPU throttling**, không tự động bị kill |
| `requests.memory` | Dự trù bộ nhớ để lập lịch và làm tín hiệu bảo vệ dưới memory pressure | Pod có thể bị eviction khi vượt request và node thiếu RAM |
| `limits.memory` | Trần RAM của container qua cơ chế kernel/cgroups | Vượt mức có thể gây **OOMKilled**, container được restart theo policy |
| `requests.ephemeral-storage` | Tài nguyên lưu trữ cục bộ cần tính khi lập lịch | Thiếu local ephemeral storage có thể ngăn scheduling |
| `limits.ephemeral-storage` | Giới hạn dung lượng ephemeral storage được theo dõi | Vượt giới hạn có thể làm Pod bị **evict** |

**`requests` không phải cam kết “container luôn được dành riêng đúng một cục RAM và CPU vật lý” theo nghĩa tuyệt đối.** Kubernetes dựa vào requests để lập kế hoạch và cơ chế kernel để ưu tiên/protect tài nguyên; hiệu quả runtime còn phụ thuộc resource type, QoS, cgroups, tính năng kernel và trạng thái node.

### 3.2. Các đơn vị thường dùng

| Viết trong YAML | Diễn giải |
|---|---|
| `cpu: "1"` | Một CPU Kubernetes; về nguyên tắc một vCPU/core logic theo node |
| `cpu: "500m"` | 500 millicores = 0,5 CPU |
| `cpu: "100m"` | 0,1 CPU |
| `memory: "512Mi"` | 512 mebibytes (MiB), hệ cơ số 1024 |
| `memory: "1Gi"` | 1 gibibyte = 1024 MiB |
| `memory: "1000M"` | 1000 megabytes, **khác** `1000Mi` |
| `ephemeral-storage: "2Gi"` | 2 GiB ephemeral local storage |

**Cảnh báo đơn vị memory:** chữ `m` là milli, **không phải MB**. Ví dụ `memory: "400m"` là một giá trị cực nhỏ, không phải 400 MiB. Với RAM, dùng `Mi`/`Gi` rõ ràng để hạn chế nhầm lẫn.

### 3.3. Điều gì nếu không khai báo?

Trong Kubernetes nói chung:

- Nếu **`limits` có nhưng `requests` không có** cho một resource, request có thể được mặc định bằng limit đó khi Pod được admission, trừ khi cơ chế mặc định khác đã áp dụng.
- **LimitRange** ở namespace có thể cung cấp giá trị default/min/max và tỷ lệ.
- Không có CPU/memory request/limit rõ ràng không có nghĩa application được bảo vệ khi node gặp contention.
- Kubernetes có thể thay đổi hành vi theo resource quotas, admission controllers, namespace policies và tính năng version.

Với **GKE Autopilot**, hệ thống thường chủ động gán hoặc điều chỉnh requests, limits theo **ComputeClass, hardware, minimum/maximum, ratio và khả năng bursting**. Đừng áp quy tắc GKE Standard vào Autopilot mà không xem Pod **sau admission**.

## 4. CPU và memory được thực thi khác nhau

### 4.1. CPU là tài nguyên có thể chia sẻ theo thời gian

Linux container runtime thường dùng **cgroups** để quản lý CPU. Khi giới hạn CPU được đặt, container có thể bị **throttling** nếu dùng quá quota trong chu kỳ tương ứng.

Ví dụ:

- Request: `500m`.
- Limit: `1000m`.
- Ở node còn CPU trống, container có thể chạy vượt mức request khi quota cho phép.
- Khi CPU demand cao hơn `1000m` trong khoảng liên quan, kernel có thể trì hoãn luồng xử lý thay vì kết thúc tiến trình.

Triệu chứng Java: p95/p99 latency tăng, thread pool bị chờ CPU, GC pause dài hơn, request timeout dù dashboard “CPU trung bình” không cao. Cần đối chiếu **CPU throttling metrics**, CPU usage so với limit, JVM/GC và latency.

**Không tăng CPU limit vô điều kiện** nếu nút thắt là database, lock contention hoặc network. Trên GKE Standard, có trường hợp **không đặt CPU limit** nhưng vẫn đặt CPU request phù hợp để giảm throttling; cần cân nhắc multi-tenant safety và policy tổ chức. Autopilot có hành vi giới hạn/bursting riêng.

### 4.2. Memory không có cơ chế “throttle mềm” tương đương CPU

Một container có:

~~~yaml
requests:
  memory: "768Mi"
limits:
  memory: "1536Mi"
~~~

Nó có thể dùng hơn 768 MiB nếu node còn khả năng, nhưng khi chạm ngưỡng 1536 MiB và kernel không thể cấp phát thêm, tiến trình có thể bị giết do **out of memory (OOM)**. Kubernetes thường hiển thị `OOMKilled` và container exit code `137` khi tiến trình bị SIGKILL, nhưng exit code 137 **không chỉ** xảy ra vì OOM; phải xem `Last State`, events và logs.

Đối với Java, memory footprint không chỉ là **`-Xmx`**:

~~~text
Bộ nhớ container xấp xỉ:
  Java heap
+ metaspace, code cache
+ thread stacks
+ direct / native buffers
+ JNI / native libraries
+ runtime / OS allocations
+ memory-backed volumes (nếu có)
~~~

Nếu limit container là 1,5 GiB mà `-Xmx` đặt 1,5 GiB, rất dễ OOM trước khi heap đạt trần do các phần khác vẫn cần RAM. Cần cấu hình headroom, heap percentage, đo GC và kiểm thử thực.

### 4.3. Ephemeral storage khác PersistentVolume

**Ephemeral storage** gồm các phần local được Kubernetes theo dõi tùy tính năng/filesystem layout như writable container layer, container logs và `emptyDir` trên disk. Nó **không** là PersistentVolume dùng để bảo vệ dữ liệu lâu dài.

- Ghi log không giới hạn hoặc tải file tạm có thể làm cạn ephemeral storage.
- Nếu Pod vượt ephemeral-storage limit, kubelet có thể **evict** Pod.
- `emptyDir.medium: Memory` sử dụng **RAM**, được tính vào memory usage chứ không phải disk-backed ephemeral storage thông thường.
- PVC trên Persistent Disk/Hyperdisk là tài nguyên lưu trữ riêng, có topology/storage class và vòng đời khác.

Không dùng ephemeral storage để lưu đơn hàng hoặc hóa đơn cần tồn tại qua Pod replacement; dùng Cloud SQL, Cloud Storage hoặc PersistentVolume phù hợp.

## 5. Node capacity, allocatable và tính toán Pod request

### 5.1. Vì sao node 4 vCPU không thể cấp đủ 4 CPU cho Pods?

Node có hai thông số:

- **Capacity:** tổng CPU/RAM/Pod slots mà node công bố.
- **Allocatable:** phần tài nguyên khả dụng cho Pods sau khi trừ dự trữ hệ thống/kubelet và các giới hạn liên quan.

~~~text
Capacity (ví dụ):     4 CPU, 16 GiB RAM
Reserved/system:      phần CPU/RAM cho kubelet, OS, system daemons
Allocatable:          nhỏ hơn Capacity
Already requested:    Pods hệ thống + workload đã đặt
Available for new Pod = Allocatable - tổng Requests của Pods đang trên node
~~~

Ví dụ giả định một node có **allocatable CPU 3500m**, trong đó Pods đang request **3000m**. Một Pod mới request **750m** không thể đặt vào node đó, ngay cả khi CPU usage tại thời điểm kiểm tra chỉ 10%. Scheduler không dựa vào một điểm đo usage tức thời để bỏ qua reservation.

### 5.2. Pod nhiều container: cộng requests

~~~yaml
containers:
- name: orders-api
  resources:
    requests:
      cpu: "500m"
      memory: "768Mi"
- name: telemetry-sidecar
  resources:
    requests:
      cpu: "100m"
      memory: "128Mi"
~~~

Tổng requests của **hai application containers** là:

~~~text
CPU:    500m + 100m = 600m
Memory: 768Mi + 128Mi = 896Mi
~~~

Một Pod có **init containers** còn có cách tính *effective request* riêng: vì init containers thường chạy tuần tự, scheduler tính theo **giá trị lớn nhất của init container** so với **tổng application containers**, cộng **Pod overhead** khi có RuntimeClass tương ứng. Với sidecar kiểu init container có `restartPolicy: Always`, semantics resource calculation được điều chỉnh theo vòng đời chồng lấp; phải xem spec/version thực tế.

**Không đơn giản cộng mọi init container với mọi application container** hoặc chỉ xem resource block của container chính. Với nhiều Pod, sidecars và daemonsets, sai lệch nhỏ cũng làm cluster bị phân bổ sai đáng kể.

### 5.3. Đọc capacity/allocatable bằng kubectl

~~~bash
# Đọc các node trong cluster đã được cấp quyền.
kubectl get nodes -o wide

# Xem capacity, allocatable và bảng resource requests hiện tại.
kubectl describe node NODE_NAME

# Trích một phần thông tin dưới dạng YAML (nếu cần).
kubectl get node NODE_NAME -o yaml
~~~

Trong `kubectl describe node`, đọc hai phần:

- **Capacity / Allocatable**.
- **Allocated resources**: Requests/Limits của các Pods đã gán lên node.

Bảng `Allocated resources` là **những gì được khai báo**, không phải số CPU/RAM đang dùng thực tế. So với usage qua `kubectl top node` hoặc Cloud Monitoring để tìm overprovisioning và pressure.

## 6. QoS classes: Guaranteed, Burstable, BestEffort

Kubernetes phân Pod vào các **Quality of Service** classes để quản lý rủi ro khi node bị thiếu tài nguyên.

| QoS | Điều kiện CPU/memory phổ biến | Hành vi dưới node pressure |
|---|---|---|
| **Guaranteed** | Mọi container có CPU và memory **request = limit**, giá trị lớn hơn 0 | Thường được ưu tiên giữ lại hơn các lớp thấp |
| **Burstable** | Có ít nhất một CPU/memory request/limit nhưng không thỏa Guaranteed | Có thể bị eviction, phụ thuộc usage vượt request và pressure |
| **BestEffort** | Không container nào có CPU/memory request/limit | Dễ bị eviction trước khi node thiếu tài nguyên |

Ví dụ:

~~~yaml
# Guaranteed cho CPU/memory:
resources:
  requests:
    cpu: "500m"
    memory: "1Gi"
  limits:
    cpu: "500m"
    memory: "1Gi"
~~~

~~~yaml
# Burstable:
resources:
  requests:
    cpu: "250m"
    memory: "512Mi"
  limits:
    cpu: "1000m"
    memory: "1Gi"
~~~

**Quan trọng:** QoS là một yếu tố trong quyết định eviction. **Pod Priority**, lượng tài nguyên vượt request, loại node pressure và các điều kiện khác cũng ảnh hưởng Pod nào bị evict. `Guaranteed` **không hứa “Pod không thể bị giết”**: OOM tại container limit, lỗi node hoặc sự kiện khác vẫn có thể làm Pod ngừng chạy.

Các phiên bản Kubernetes mới có khả năng **Pod-level resource specification** theo feature gate/version, nhưng bài tập cơ bản dùng **container-level resources** để giữ tính tương thích và dễ đọc. Khi sử dụng các tính năng mới, kiểm tra phiên bản GKE và trạng thái enablement.

## 7. Từ tài nguyên tới việc Pod được schedule

Scheduler thường thực hiện hai giai đoạn tư duy:

1. **Filter:** loại node không đủ tài nguyên hoặc không đáp ứng điều kiện bắt buộc.
2. **Score:** chấm điểm những node còn phù hợp để quyết định placement.

~~~mermaid
flowchart TD
    P["Pod Orders API<br/>request 750m CPU, 1Gi RAM"]
    N1["Node A<br/>còn 500m CPU allocatable cho request"]
    N2["Node B<br/>còn 1000m CPU, 2Gi RAM<br/>khớp nodeSelector"]
    N3["Node C<br/>còn 1500m CPU<br/>nhưng có taint không toleration"]
    F["Scheduler filter"]
    B["Bind Pod to Node B"]
    P --> F
    N1 -. "Insufficient cpu" .-> F
    N2 --> F
    N3 -. "Untolerated taint" .-> F
    F --> B
~~~

Lý do không thể schedule gồm cả tài nguyên lẫn **constraints không khớp**:

| Thông điệp/Event điển hình | Ý nghĩa |
|---|---|
| `Insufficient cpu` | Không có node đủ CPU request còn khả dụng |
| `Insufficient memory` | Không có node đủ RAM request |
| `Insufficient ephemeral-storage` | Thiếu local ephemeral storage cho request |
| `Too many pods` / `OutOfPods` | Node chạm giới hạn số Pods |
| `node(s) didn't match Pod's node affinity/selector` | Nhãn node hoặc affinity rule không khớp |
| `had untolerated taint` | Pod thiếu toleration tương ứng |
| `didn't match pod affinity/anti-affinity` | Ràng buộc đồng vị trí/tách vị trí không thỏa |
| `volume node affinity conflict` | PVC/PV ràng buộc topology zone khác |
| `didn't match topology spread constraints` | Constraint phân bố quá chặt |
| `Insufficient nvidia.com/gpu` | Node không đủ GPU extended resource được request |

Thông điệp cụ thể phụ thuộc scheduler/GKE version. Một Pod có thể bị nhiều nguyên nhân cùng lúc; **đọc toàn bộ Events** chứ không lấy dòng đầu làm nguyên nhân duy nhất.

## 8. NodeSelector và node affinity

### 8.1. nodeSelector: ràng buộc nhãn đơn giản

~~~yaml
spec:
  template:
    spec:
      nodeSelector:
        kubernetes.io/arch: amd64
      containers:
      - name: orders-api
        image: IMAGE_URI
~~~

Pod chỉ chạy trên node có label `kubernetes.io/arch=amd64`. Nếu cluster chỉ có node `arm64`, Pod **Pending**, dù CPU/RAM còn rất nhiều.

Chỉ dùng label có sẵn/được quản lý theo hợp đồng. Đối với GKE Standard có node pools, có thể dựa vào nhãn do node pool cung cấp; **không sửa nhãn managed nodes của Autopilot theo thói quen quản trị Standard**.

### 8.2. Required vs preferred node affinity

- `requiredDuringSchedulingIgnoredDuringExecution`: điều kiện **bắt buộc** khi schedule.
- `preferredDuringSchedulingIgnoredDuringExecution`: ưu tiên **mềm**, scheduler có thể chọn node khác nếu không đáp ứng.
- `IgnoredDuringExecution`: thay đổi nhãn sau khi Pod đã chạy không tự động làm Pod bị evict theo quy tắc này.

Ví dụ ưu tiên node cùng region mà vẫn cho phép node khác khi cần:

~~~yaml
affinity:
  nodeAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 80
      preference:
        matchExpressions:
        - key: topology.kubernetes.io/zone
          operator: In
          values:
          - asia-southeast1-a
~~~

Khi workload **bắt buộc** dùng data disk theo zone hoặc phần cứng cụ thể, preferred rule có thể không đủ; dùng required affinity/topology phù hợp. Khi mục tiêu chỉ là tối ưu latency, preferred giảm nguy cơ Pod bị kẹt Pending.

### 8.3. Chọn zone không đồng nghĩa HA

Đặt tất cả replicas của API vào duy nhất zone A có thể làm đơn giản access tới zonal disk, nhưng **tăng rủi ro outage**. Đối với stateless API sau load balancer, nên phân bố đa zone trong regional GKE cluster. Đối với Pod stateful có PVC ràng buộc zone, phải kết hợp scheduler với storage topology và failover phù hợp; đừng ép PVC zonal sang zone khác bằng cách đổi nodeSelector.

## 9. Taints và tolerations: giữ node cho workload phù hợp

### 9.1. Taint khác toleration

Một node có thể mang taint:

~~~text
dedicated=batch:NoSchedule
~~~

Pod không có toleration tương ứng sẽ không được schedule lên node đó. Toleration minh họa:

~~~yaml
tolerations:
- key: dedicated
  operator: Equal
  value: batch
  effect: NoSchedule
~~~

Nhưng **toleration chỉ cho phép Pod được xem xét trên node có taint**; nó **không buộc Pod phải chọn node ấy**. Nếu bạn muốn workload batch chỉ đặt vào node pool batch, kết hợp **node affinity/nodeSelector**.

### 9.2. Ba effect phổ biến

| Taint effect | Ảnh hưởng |
|---|---|
| `NoSchedule` | Không schedule Pod mới thiếu toleration |
| `PreferNoSchedule` | Scheduler cố tránh nếu có lựa chọn phù hợp |
| `NoExecute` | Không chỉ chặn scheduling; còn có thể **evict Pods đang chạy** không toleration, theo `tolerationSeconds` khi áp dụng |

Trên GKE Standard, node-pool taints nên được thiết kế ở **node pool configuration** để node mới do autoscaler tạo có đúng taint. Sửa bằng tay trên một node riêng lẻ có thể không được bảo toàn sau scale/upgrade.

**Lưu ý bảo mật:** taint/toleration là cơ chế scheduling và isolation thực dụng, không phải boundary bảo mật thay IAM, network policy hoặc sandboxing container.

## 10. Pod affinity, anti-affinity và topology spread

### 10.1. Đặt Pod gần nhau hay tách xa nhau?

- **Pod affinity:** muốn chạy cùng topology domain với Pod khác có label cụ thể.
- **Pod anti-affinity:** muốn tránh cùng node/zone với Pod khác, tăng khả năng chống lỗi.
- **Topology spread constraints:** điều chỉnh mức lệch số replica trên các domain như zone hoặc hostname.

Ví dụ một ứng dụng Java cần có nhiều replicas tại nhiều zone. Với regional cluster và các node trải trên các zone:

~~~yaml
topologySpreadConstraints:
- maxSkew: 1
  topologyKey: topology.kubernetes.io/zone
  whenUnsatisfiable: ScheduleAnyway
  labelSelector:
    matchLabels:
      app: orders-api
~~~

**`ScheduleAnyway`** nghĩa là scheduler ưu tiên phân tán nhưng vẫn có thể schedule khi phân bố không lý tưởng. Với `DoNotSchedule`, một Pod có thể bị Pending nếu placement không thỏa; điều này nên được dùng khi yêu cầu chống lỗi và năng lực node đủ rõ.

### 10.2. Anti-affinity theo node

~~~yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        labelSelector:
          matchLabels:
            app: orders-api
        topologyKey: kubernetes.io/hostname
~~~

Ý nghĩa: tránh đặt hai Pod `orders-api` vào cùng một node khi có thể. Đây là **mềm**, không bảo đảm luôn tách node. Anti-affinity bắt buộc có thể làm Deployment Pending khi node pool nhỏ hoặc autoscaler chưa thể bổ sung node.

### 10.3. Quy tắc phân bố đi với autoscaling

Khi dùng topology spread constraints với cluster autoscaling, kiểm tra `nodeTaintsPolicy` và các lựa chọn về eligible domains. Hướng dẫn GKE khuyến nghị cân nhắc `nodeTaintsPolicy: Honor` cho những workload có topology spread và Cluster Autoscaler để giảm hành vi scale-down rồi scale-up lặp do hiểu khác nhau về node hợp lệ.

**Không coi `replicas: 3` tự động đồng nghĩa “mỗi zone một Pod”**. Nếu node chỉ tập trung ở một zone, scheduler không tạo ra zone mới. Cần node pools/ComputeClass/cluster topology phù hợp và ít nhất số domain đủ điều kiện.

## 11. GKE Standard và GKE Autopilot khác nhau ở resource management

| Chủ đề | GKE Standard | GKE Autopilot |
|---|---|---|
| Node pools | Người vận hành quản lý cấu hình, sizing, autoscaling | GKE quản lý phần lớn nền tảng node cho workload |
| Resource requests | Do manifest, LimitRange/admission xác định | GKE có default/min/max và điều chỉnh requests theo ComputeClass/hardware |
| CPU/memory ratio | Tùy machine type/cluster policy | Có **tỷ lệ CPU:RAM hợp lệ** theo ComputeClass |
| CPU limits | Kubernetes/cgroups thông thường, người vận hành chọn policy | Có điều chỉnh limits theo **bursting support** của cluster |
| Ephemeral storage | Theo Kubernetes/node capacity/cluster policy | Có default và giới hạn riêng; **limits bằng requests** cho ephemeral storage |
| Hardware | Chọn machine types/node pools | Chọn thông qua ComputeClass/hardware requests theo tính năng hỗ trợ |
| Scheduler constraints | Tự quản labels/taints/node pools | Một số constraints hoặc hard affinity có yêu cầu/giới hạn riêng |
| Pricing | Thường trả phí node/VM và các dịch vụ liên quan | Phụ thuộc mô hình **Pod-based hoặc node-based billing** và cấu hình workload |
| Troubleshooting | Xem cả node pool/autoscaler | Xem Pod sau admission, compute class, cấu hình Autopilot và capacity |

### 11.1. Autopilot có thể thêm request mặc định

Theo tài liệu hiện hành, một số built-in Autopilot ComputeClasses có default resource requests như:

| ComputeClass | CPU mặc định | RAM mặc định |
|---|---:|---:|
| General-purpose | 0,5 vCPU | 2 GiB |
| Balanced | 0,5 vCPU | 2 GiB |
| Scale-Out | 0,5 vCPU | 2 GiB |

Đây là **giá trị mặc định tham khảo theo tài liệu**, không phải quy định áp cho mọi GPU/Performance workload hoặc mọi version. Với non-DaemonSet containers, Autopilot còn có default ephemeral storage request; ví dụ hiện hành là **1 GiB**. Hãy kiểm tra bảng min/max, compute class và bursting ở tài liệu chính thức trước khi chọn một giá trị tuyệt đối.

### 11.2. CPU:memory ratio và giá trị bị điều chỉnh

Ví dụ bạn yêu cầu `1 vCPU` và `16Gi` trong **Scale-Out ComputeClass**. Nếu ratio tối đa được phép là **1 vCPU : 4GiB**, Autopilot có thể **tăng CPU request lên 4 vCPU** để đạt ratio. Bạn đặt request 1 vCPU nhưng hóa đơn và scheduling có thể dựa vào request được GKE điều chỉnh.

Autopilot cũng có thể:

- Tăng request thấp hơn mức minimum.
- Áp default khi không đặt request.
- Từ chối workload vượt maximum của hardware/ComputeClass.
- Điều chỉnh limits khi không hỗ trợ bursting.
- Điều chỉnh init-container requests theo policy riêng.

Vì vậy, sau `kubectl apply`, **đọc lại Pod đã được tạo** thay vì chỉ xem YAML trong Git để biết requests/limits thực tế.

### 11.3. Bursting và CPU limits trong Autopilot

| Cấu hình | Cluster **có bursting** | Cluster **không hỗ trợ bursting** |
|---|---|---|
| Request thấp hơn CPU limit | Pod có thể burst đến limit khi đủ tài nguyên | Autopilot có thể đặt limit bằng request |
| Có request, không đặt CPU limit | Có thể burst theo khả năng còn trống | Autopilot có thể thêm limit bằng request |
| Chỉ đặt CPU limit | Request được mặc định từ limit theo admission | Tương tự, đồng thời tuân thủ chính sách Autopilot |
| Request/limit ngoài min/max/ratio | Có thể bị chỉnh hoặc từ chối | Có thể bị chỉnh hoặc từ chối |

Với ephemeral storage trong Autopilot, **request và limit phải bằng nhau**; GKE có thể sửa cấu hình để thực thi. Đừng dùng một manifest có `ephemeral-storage request 1Gi`, `limit 5Gi` rồi kỳ vọng vẫn chạy đúng như trên Standard.

### 11.4. Autopilot có phải lúc nào cũng rẻ hơn Standard?

Không thể kết luận từ tên chế độ. **Requests** là một phần quan trọng trong sizing, scheduling và nhiều mô hình billing Autopilot. Standard tính chi phí theo node pools/machine types và phụ phí liên quan; Autopilot có thể tính theo workload resource requests hoặc node-based model trong những trường hợp nhất định.

Một Pod request quá cao nhưng thường xuyên dùng ít sẽ làm lãng phí năng lực và có thể tăng chi phí; một Pod request quá thấp có thể gây hiệu năng kém hoặc bị điều chỉnh trong Autopilot. Quyết định nên dựa vào **chi phí trên mỗi request/transaction đạt SLO**, không chỉ bill một Pod hay một VM riêng lẻ.

## 12. Thực hành A — Deployment Java Orders API trên GKE Standard

Bài lab giả định namespace `orders-lab` và OCI image **đã được build, push vào Docker repository và được cluster cấp quyền pull**. Ví dụ image:

~~~text
asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0
~~~

**Không dùng Maven JAR path làm image URI.** Artifact Registry Docker repository chứa OCI image; Maven artifact là một đầu vào để build image.

### 12.1. Manifest Deployment có requests, limits và topology spread

Lưu tệp `orders-deployment.yaml` trong môi trường lab được phép. Trong mẫu này, `topologySpreadConstraints` được đặt ở cấp **Pod spec**, cùng cấp với `containers`, không đặt bên trong từng container:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders-lab
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      terminationGracePeriodSeconds: 30
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone
        whenUnsatisfiable: ScheduleAnyway
        labelSelector:
          matchLabels:
            app: orders-api
      containers:
      - name: orders-api
        image: asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0
        ports:
        - containerPort: 8080
          name: http
        resources:
          requests:
            cpu: "500m"
            memory: "768Mi"
            ephemeral-storage: "1Gi"
          limits:
            cpu: "1000m"
            memory: "1536Mi"
            ephemeral-storage: "2Gi"
        env:
        - name: JAVA_TOOL_OPTIONS
          value: "-XX:MaxRAMPercentage=65.0"
        startupProbe:
          httpGet:
            path: /healthz
            port: http
          periodSeconds: 5
          failureThreshold: 24
        readinessProbe:
          httpGet:
            path: /ready
            port: http
          periodSeconds: 5
        livenessProbe:
          httpGet:
            path: /healthz
            port: http
          periodSeconds: 10
~~~

Giải thích:

- Mỗi replica request **0,5 vCPU**, **768 MiB** RAM và **1 GiB** ephemeral storage.
- Ba replicas request tổng **1,5 vCPU**, **2304 MiB** RAM và **3 GiB** ephemeral storage, **chưa tính** những containers khác, init containers, Pod overhead hoặc node system Pods.
- CPU có thể burst đến 1 vCPU khi khả năng còn lại cho phép trong Standard và policy tương ứng.
- Memory limit là **1536Mi**; phải đảm bảo heap + native footprint không vượt mức.
- `topologySpreadConstraints` đặt tại **`spec.template.spec`**, cùng cấp với `containers`.
- Image `PROJECT_ID` là placeholder, phải thay bằng image URI tồn tại thật và cho phép node/kubelet pull.
- Không tự tạo LoadBalancer Service public khi chưa có yêu cầu truy cập thật.

Đối với API thật, `/ready` và `/healthz` phải **thực sự tồn tại** trong image. Nếu ứng dụng chỉ có `/healthz`, cần chỉnh probes và kiểm tra logic trước khi triển khai. `startupProbe` tránh liveness quá sớm khi JVM warm-up; liveness không nên fail chỉ vì dependency bên ngoài tạm gián đoạn.

### 12.2. Readback và apply theo đúng môi trường

Lệnh quan sát kết nối:

~~~bash
gcloud container clusters list --project=PROJECT_ID
gcloud container clusters get-credentials CLUSTER_NAME \
  --project=PROJECT_ID \
  --location=CLUSTER_LOCATION

kubectl config current-context
kubectl get namespace orders-lab
~~~

`get-credentials` thay đổi **kubeconfig trên môi trường CLI**, không thay cluster. Đảm bảo đang trỏ đúng cluster. Nếu namespace chưa có và bạn được phép tạo:

~~~bash
kubectl create namespace orders-lab
~~~

**Lệnh sau tạo/cập nhật workload thật:**

~~~bash
kubectl apply --dry-run=server -f orders-deployment.yaml
kubectl apply -f orders-deployment.yaml

kubectl get deployment orders-api -n orders-lab
kubectl get pods -n orders-lab -o wide
kubectl rollout status deployment/orders-api -n orders-lab
~~~

**`--dry-run=server`** vẫn gửi yêu cầu tới API server để validation/admission nhưng không tạo resource lâu dài; nó có thể phụ thuộc quyền và webhooks được cấu hình. Hãy xem kết quả trước khi apply thật. Nếu cluster đang dùng GitOps/Helm, không thao tác tay vào workload do controller khác sở hữu mà chưa có quy trình.

## 13. Thực hành B — Manifest Autopilot có request/limit tương thích

Ví dụ cho **General-purpose Autopilot**, với một container Java API ổn định và tài nguyên minh họa:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders-lab
spec:
  replicas: 3
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      containers:
      - name: orders-api
        image: asia-southeast1-docker.pkg.dev/PROJECT_ID/java-images/orders-api:1.0.0
        resources:
          requests:
            cpu: "500m"
            memory: "2Gi"
            ephemeral-storage: "1Gi"
          limits:
            cpu: "500m"
            memory: "2Gi"
            ephemeral-storage: "1Gi"
        ports:
        - containerPort: 8080
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          periodSeconds: 5
~~~

Cấu hình này đặt cùng giá trị request và limit cho CPU/RAM/ephemeral storage, tránh trông chờ bursting, và là một điểm xuất phát dễ kiểm soát. Nó **không phải giá trị tối ưu mặc định cho mọi Java workload**. Phải kiểm chứng p95 latency, GC và memory footprint.

Nếu muốn CPU burst trong Autopilot, trước tiên xác định cluster **có hỗ trợ bursting không**, ComputeClass phù hợp và ảnh hưởng tới billing/scheduling; đặt request nhỏ hơn limit chỉ khi hành vi đó được hỗ trợ.

Đọc lại Pod đã tạo:

~~~bash
kubectl get pods -n orders-lab
kubectl get pod POD_NAME -n orders-lab -o yaml
kubectl describe pod POD_NAME -n orders-lab
~~~

Đặc biệt đọc `spec.containers[].resources` **trên Pod**, không chỉ manifest của Deployment. Autopilot admission có thể đã tự điều chỉnh giá trị.

## 14. HPA, VPA và Cluster Autoscaler giải quyết các lớp khác nhau

### 14.1. Ba công cụ, ba câu hỏi

| Công cụ | Điều gì thay đổi? | Dựa trên điều gì? |
|---|---|---|
| **Horizontal Pod Autoscaler (HPA)** | **Số replicas của workload** | CPU/memory utilization, custom/external metrics theo adapter |
| **Vertical Pod Autoscaler (VPA)** | **Resource requests/limits đề xuất hoặc cập nhật cho Pod** | Phân tích usage lịch sử và chính sách VPA |
| **Cluster Autoscaler (Standard)** | **Số nodes** trong node pools được cấu hình | Pods không schedule được, requests, constraints và scaling policy |
| **Autopilot node management** | Capacity phía dưới để phục vụ workload | GKE quản lý dựa trên Pod requirements/ComputeClass |

~~~mermaid
flowchart TD
    Traffic["Lưu lượng tăng"] --> Metrics["Metrics: CPU / RPS"]
    Metrics --> HPA["HPA tăng số Pods"]
    HPA --> Pending["Một số Pod chưa có node phù hợp"]
    Pending --> CA["Cluster Autoscaler<br/>hoặc Autopilot cung cấp capacity"]
    CA --> Nodes["Nodes phù hợp được bổ sung"]
    Nodes --> Pods["Pods được schedule"]
    VPA["VPA theo dữ liệu sử dụng"] -. "Đề xuất/chỉnh request mỗi Pod" .-> HPA
~~~

**Không nhầm:** HPA không tự tăng RAM limit của Pod; Cluster Autoscaler không tăng CPU limit của container; VPA không làm tăng số replicas chỉ vì QPS lên cao.

### 14.2. HPA sử dụng CPU utilization dựa vào request

Giả sử một Pod request `500m CPU`, đo CPU usage `400m`:

~~~text
CPU utilization theo HPA = CPU usage / CPU request
                          = 400m / 500m
                          = 80%
~~~

Nếu HPA target 60%, nó có tín hiệu mở rộng replicas (sau khi tính trung bình các Pods, tolerance, stabilization và các quy tắc khác). **Đây không phải “80% của CPU limit 1000m”**. Thay request từ `500m` sang `1000m` mà usage không đổi khiến tỷ lệ từ 80% xuống 40% và có thể thay đổi quyết định HPA.

Nếu container thiếu CPU request cần cho phép tính CPU utilization, HPA có thể không xác định metric như kỳ vọng hoặc bỏ qua Pods trong tính toán tùy trường hợp. Vì thế **requests đúng là nền tảng của HPA CPU-based**.

### 14.3. Ví dụ HPA manifest

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: orders-api-hpa
  namespace: orders-lab
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  minReplicas: 3
  maxReplicas: 12
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
~~~

Khi dùng HPA, tránh để một pipeline/nhà vận hành khác liên tục ghi `spec.replicas` cố định lên cùng Deployment. Đặt `minReplicas/maxReplicas` hợp lý với SLO, quota và chi phí. HPA cần metrics pipeline hoạt động; ngoài CPU có thể dùng custom/external metrics theo khả năng cluster.

### 14.4. VPA không phải HPA thứ hai

VPA có thể đề xuất resource sizing cho workload mà không cần sửa ngay. Ví dụ cấu hình **chỉ khuyến nghị**:

~~~yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: orders-api-vpa
  namespace: orders-lab
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: orders-api
  updatePolicy:
    updateMode: "Off"
~~~

VPA phải được **hỗ trợ/bật** trong cluster GKE liên quan. `Off` nghĩa là dùng recommendations mà không tự động thay requests. Xem:

~~~bash
kubectl get vpa -n orders-lab
kubectl describe vpa orders-api-vpa -n orders-lab
~~~

Không dùng VPA cập nhật tự động các resource mà HPA đang dùng làm nguồn utilization khi chưa thiết kế phối hợp: VPA đổi request có thể đổi mẫu số tính HPA, tạo vòng điều chỉnh khó dự đoán. Một chiến lược an toàn là **VPA recommendation-only để chọn baseline**, HPA autoscale theo traffic/resource, Cluster Autoscaler cung cấp node capacity.

### 14.5. Khi nào Cluster Autoscaler không cứu được Pod Pending?

- Request của một Pod **lớn hơn khả năng của mọi machine type/node pool hợp lệ**.
- Node selector/affinity chọn nhãn không tồn tại ở node pool templates.
- Taint/toleration, topology spread hoặc PVC node affinity tạo điều kiện không thể thỏa.
- Max node count, regional quota, IP exhaustion hoặc capacity ở zone bị giới hạn.
- ResourceQuota/LimitRange/admission không cho tạo hoặc thay đổi Pod.
- GPU hardware yêu cầu không có hoặc không đủ quota.
- Một số ràng buộc chính sách và timing scale-up.

**Không bật autoscaling rồi giả định tất cả Pending tự được sửa.** Xem `kubectl describe pod`, log/metrics autoscaler và giới hạn node pool; điều chỉnh đúng nguyên nhân.

## 15. ResourceQuota, LimitRange và namespace governance

### 15.1. LimitRange: guardrail cho mỗi container/Pod

Namespace có thể định nghĩa default, min và max resources. Ví dụ một LimitRange chỉ cho containers:

~~~yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: orders-limits
  namespace: orders-lab
spec:
  limits:
  - type: Container
    defaultRequest:
      cpu: "250m"
      memory: "512Mi"
    default:
      cpu: "1000m"
      memory: "1Gi"
    min:
      cpu: "100m"
      memory: "128Mi"
    max:
      cpu: "2000m"
      memory: "4Gi"
~~~

Default chỉ áp dụng khi trường tương ứng không được cung cấp và khi có policy phù hợp. Với Autopilot, các giá trị admission/minimum/ratio của GKE có thể tương tác với LimitRange; cần kiểm tra Pod được tạo thực tế và không dùng LimitRange để bypass hạn chế Autopilot.

### 15.2. ResourceQuota: ngân sách cấp namespace

~~~yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: orders-quota
  namespace: orders-lab
spec:
  hard:
    requests.cpu: "8"
    requests.memory: "16Gi"
    limits.cpu: "16"
    limits.memory: "32Gi"
    pods: "30"
~~~

Quota giúp kiểm soát tổng requests/limits của namespace, giới hạn số Pods. Nó **không tạo thêm node**; khi vượt quota, API server có thể từ chối tạo Pod, khác với Pod đã tạo nhưng **Pending vì scheduler không tìm thấy node**.

Khi một namespace đang có ResourceQuota cho requests/limits, yêu cầu khai báo tài nguyên rõ ràng có thể được enforce thông qua quota/admission. Đặt quota theo dự kiến HPA maxReplicas và batch workload, tránh quota quá thấp khiến autoscaling dừng bất ngờ.

## 16. Diagnosing: từ Pending đến OOMKilled

### 16.1. Bộ lệnh quan sát trước khi thay đổi

~~~bash
# Kiểm tra workload và tình trạng placement.
kubectl get deployment -n orders-lab
kubectl get pods -n orders-lab -o wide

# Đọc chi tiết Pod và Events, đặc biệt FailedScheduling.
kubectl describe pod POD_NAME -n orders-lab

# Xem events theo thời điểm.
kubectl get events -n orders-lab --sort-by=.lastTimestamp

# Xem các node và requests đã được allocate.
kubectl get nodes -o wide
kubectl describe node NODE_NAME

# Xem actual CPU/memory usage nếu metrics pipeline hỗ trợ.
kubectl top pods -n orders-lab --containers
kubectl top nodes

# Xem tài nguyên cấu hình, quotas và limits.
kubectl get deployment orders-api -n orders-lab -o yaml
kubectl get resourcequota,limitrange -n orders-lab
~~~

**`kubectl top` cần metrics-server hoặc cơ chế metrics tương thích**. Nếu chưa có dữ liệu, dùng Cloud Monitoring/GKE Observability và kiểm tra metrics pipeline; không tự kết luận “CPU bằng 0” vì lệnh báo thiếu metrics.

### 16.2. Ma trận nguyên nhân và hành động

| Triệu chứng | Quan sát | Hướng xử lý |
|---|---|---|
| Pod `Pending`, `Insufficient cpu` | Requests vượt allocatable node phù hợp | Right-size request, kiểm tra node pools/autoscaler |
| Pod `Pending`, `Insufficient memory` | Tổng memory requests không fit | Giảm request khi có số liệu, dùng node có RAM phù hợp |
| Pod `Pending` dù CPU còn nhiều | Taint/affinity/topology/PVC/Pod slots | Đọc Events và tất cả constraints |
| Pod `Pending` nhiều phút sau HPA scale | Autoscaler bị max/quota/capacity hoặc delay | Xem autoscaler logs, quota, IP ranges |
| Pod tạo bị từ chối | ResourceQuota/LimitRange/Autopilot admission | Xem API error, không chỉ scheduler |
| Pod `Running` nhưng latency tăng | CPU throttling, GC, DB hoặc network | CPU usage/limit/throttle, tracing và p95/p99 |
| Container `OOMKilled` | Vượt memory limit, heap/native vượt dự kiến | Xem Last State, RAM, heap và memory limit |
| Pod `Evicted` | Node memory/disk/PID pressure hoặc ephemeral storage | Xem reason/event và node conditions |
| `ImagePullBackOff` | Image URI/registry IAM/network | Kiểm tra Artifact Registry pull permissions |
| Pod CrashLoopBackOff | App crash, config, probes, OOM | Container logs, last termination, probes |
| Node NotReady | Node/network/kubelet issue | Node status, events, GKE operations |
| HPA không tăng replicas | Metrics thiếu, requests CPU thiếu, maxReplicas/chính sách | `kubectl describe hpa`, metrics/requests |
| Chỉ một zone có Pods | Node availability/topology constraints | Kiểm tra node pool across zones và spread policy |
| Autopilot Pod dùng request khác YAML | Admission defaults/min/max/ratios | Đọc Pod sau mutation, kiểm tra ComputeClass |

### 16.3. OOMKilled và `137`

~~~bash
kubectl describe pod POD_NAME -n orders-lab
kubectl logs POD_NAME -n orders-lab --previous
kubectl get pod POD_NAME -n orders-lab -o yaml
~~~

Tìm:

- `Last State: Terminated`, `Reason: OOMKilled`, `Exit Code: 137`.
- Số lần restart tăng, thời điểm OOM trùng với traffic burst hay startup.
- Memory usage/working set, heap và direct buffers từ JVM telemetry.
- `emptyDir.medium: Memory` hoặc sidecar làm tăng memory footprint.
- LimitRange/Autopilot đã sửa resource values khi admission chưa.

Nếu Pod OOM do startup peak, điều chỉnh request/limit, heap configuration và ứng dụng. Nếu OOM vì memory leak, tăng RAM chỉ là giảm triệu chứng; cần profiler và fix nguyên nhân. Không tắt memory limit trên production mà không đánh giá an toàn multi-tenant.

### 16.4. CPU throttling không phải CPU OOM

CPU throttling thường biểu hiện **chậm hoặc timeout**, trong khi container vẫn `Running`. Nếu Kubernetes CPU utilization luôn gần limit và JVM GC/profiling cho thấy contention, cân nhắc:

- Tăng CPU limit nếu workload và policy cho phép.
- Tăng request để scheduler đảm bảo phần CPU tương xứng.
- Thử bỏ CPU limit trong GKE Standard khi có guardrails.
- Scale HPA theo metric phù hợp, hoặc tối ưu CPU-heavy path.
- Xem node CPU contention và cgroups metrics.

**Đừng sửa bằng cách tăng memory limit khi CPU mới là nút thắt**, và ngược lại.

## 17. Case study: Java Orders API trên regional GKE cluster

### 17.1. Bối cảnh và số liệu

Một doanh nghiệp giả định triển khai Java Orders API trên GKE Standard, dùng Cloud SQL PostgreSQL và Artifact Registry. API có nhiều replicas sau load balancer, yêu cầu:

- p95 latency dưới **200 ms** ở traffic đại diện.
- Không mất phục vụ toàn bộ khi một node hoặc một zone lỗi.
- Có thể tăng lên 12 Pods khi khuyến mãi.
- Không lưu đơn hàng vào local ephemeral storage của Pod.
- Dự toán chi phí CPU/RAM và node pools có thể quan sát.

Số liệu thử ban đầu:

| Chỉ số | Đo được (giả định) |
|---|---|
| Request rate trung bình / đỉnh | 250 / 700 RPS |
| CPU trung bình/đỉnh mỗi Pod | 280m / 650m |
| RSS JVM khi ổn định | 620–800 MiB |
| Memory peak warm-up | 1,1 GiB |
| p95 latency | 155 ms |
| CPU throttling | Tăng ở đỉnh nếu limit 500m |
| DB latency | Một phần request phụ thuộc Cloud SQL |

### 17.2. Chọn baseline thay vì đoán

Ứng viên request `500m`, memory `768Mi`, CPU limit `1000m`, memory limit `1536Mi` có thể là **baseline để benchmark**. Nhưng memory peak 1,1 GiB vượt request 768Mi nên khi node memory pressure có rủi ro eviction cao hơn; nếu workload quan trọng, cân nhắc nâng memory request tới giá trị sát usage có headroom và test.

Không đặt memory limit bằng `Xmx`; cần RAM ngoài heap. Với JVM có heap percentage, đo actual RSS và GC. Cân nhắc đặt request **1Gi** và limit **1536Mi** nếu kết quả load test chứng minh tính ổn định/chi phí phù hợp.

### 17.3. Vì sao request không phải con số “đẹp”?

Giả sử ba Pods, mỗi Pod request `1000m` dù thực tế CPU thường dùng 280m. Scheduler dự trù **3 CPU** cho workload, trong khi tổng CPU usage thường chỉ khoảng 0,84 CPU. HPA dùng mẫu số request cao có thể scale chậm hơn. Ngược lại, đặt request `100m` để tiết kiệm packing làm Pod dễ tranh chấp CPU và HPA có thể scale quá nhạy.

Quy trình đúng: thu metric qua **các chu kỳ traffic**, thử nhiều request values, xem sự khác biệt giữa latency, restart/eviction, packing và hóa đơn. Không chọn giá trị chỉ từ một biểu đồ trung bình.

### 17.4. Autoscaling theo ba lớp

1. **HPA** giữ 3–12 replicas dựa trên CPU/traffic, có stabilization và capacity dự kiến.
2. **Cluster Autoscaler** bổ sung nodes trong node pools Standard khi Pods mới không fit.
3. **Topology spread** ưu tiên phân tán Pods trên zones; PDB giảm rủi ro quá nhiều replica bị gián đoạn tự nguyện.
4. **VPA recommendations** dùng cho rà soát baseline theo thời gian, không tự thay requests cạnh tranh với CPU-based HPA.
5. **Cloud Monitoring** theo dõi p95 latency, CPU throttling, memory pressure, HPA desired/actual replicas, Pending Pods, node autoscaling và chi phí.

### 17.5. Từ Java image đến production

~~~mermaid
flowchart LR
    Code["Git Orders API"] --> Build["CI build + unit tests"]
    Build --> Artifact["Artifact Registry<br/>OCI image"]
    Artifact --> Deploy["GKE Deployment + HPA"]
    Deploy --> Pods["Pods ở nhiều zones"]
    Pods --> SQL["Cloud SQL"]
    Pods --> Storage["Cloud Storage"]
    Monitor["Cloud Monitoring + Logs"] -. "Telemetry" .-> Pods
~~~

Kiểm tra thêm:

- IAM/workload identity để truy cập Cloud SQL/Storage.
- Readiness/liveness/startup probes tương ứng trạng thái ứng dụng.
- Graceful shutdown, termination grace period, preStop nếu cần.
- Connection pooling; tăng replicas không làm tăng số connections DB vô hạn.
- Artifact image digest và rollout/rollback theo release.
- Network policy, ingress, HTTPS và lưu trữ dữ liệu không phụ thuộc Pod local disk.

## 18. Triển khai thay đổi requests/limits an toàn

### 18.1. Resource change cũng là một deployment change

Dù không đổi code, sửa `requests`/`limits` của Pod template có thể tạo ReplicaSet mới và rollout. Với GKE Standard, container resource updates trong một số phiên bản có khả năng resize in-place theo feature support, nhưng **đừng mặc định mọi loại workload/cluster đều resize không gián đoạn**. Hãy kiểm tra GKE version, policy và rollout thực tế.

Quy trình:

1. Thu trạng thái/metric trước thay đổi (requests, limits, usage, latency, restart, billing).
2. Phân tích capacity và quota nếu request lớn hơn.
3. Kiểm tra YAML, admission policy và Autopilot mutation nếu áp dụng.
4. Thử trên staging với traffic đại diện.
5. Dùng rolling update/canary, xem Pod mới Pending hoặc OOM hay không.
6. Đọc HPA/VPA/Cluster Autoscaler sau deploy.
7. Theo dõi p95/p99, error rate, CPU throttling, memory pressure và chi phí.
8. Có sẵn manifest/version cũ để rollback nếu SLO xấu hơn.

### 18.2. PodDisruptionBudget không thể thay requests

Ví dụ tối thiểu:

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: orders-api-pdb
  namespace: orders-lab
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: orders-api
~~~

PDB kiểm soát **một số voluntary disruptions** thông qua eviction API, giúp tránh thu hồi quá nhiều Pods cùng lúc trong những trường hợp được hỗ trợ. Nó **không ngăn tất cả lỗi node, OOMKilled, outage** và không bảo đảm rollout phù hợp nếu có quá ít capacity. Phải kết hợp **replica count, topology, requests và capacity**.

### 18.3. Chi phí và khả năng đáp ứng

| Quyết định | Lợi ích | Rủi ro |
|---|---|---|
| Requests sát usage có headroom | Packing tốt hơn, giảm cấp phát thừa | Nếu quá thấp, contention/eviction |
| Limits CPU cao hơn request | Cho phép burst trong môi trường hỗ trợ | CPU spike của một Pod ảnh hưởng neighbor nếu quản lý kém |
| Requests = limits | Dễ dự đoán QoS/resource, có thể Guaranteed | Ít cơ hội dùng idle headroom, CPU throttling nếu limit thấp |
| Memory limit rộng | Giảm OOM trong peak | Dễ tạo pressure nếu request thấp |
| HPA max cao | Đáp ứng traffic spike | Có thể vượt quota, DB capacity và budget |
| Topology anti-affinity cứng | Tách fault domains tốt hơn | Có thể làm Pending khi node/capacity thiếu |
| Node pool lớn hơn | Fit các Pods lớn | Cost tăng khi utilization thấp |
| Autopilot | Giảm quản trị node | Tối ưu request và tính năng/giá theo ComputeClass vẫn cần thiết |

**Không tối ưu bằng một metric duy nhất**. CPU cost thấp nhưng p99 latency quá cao sẽ không đáp ứng mục tiêu doanh nghiệp.

## 19. Bài tập thực hành và tự đánh giá

### Bài 1 — Tính tổng requests

Một Pod có container Java request `500m CPU, 768Mi memory` và sidecar request `100m CPU, 128Mi memory`. Bỏ qua init containers và Pod overhead.

**Câu hỏi:** tổng CPU/memory requests là bao nhiêu? Ba replicas cần tối thiểu tổng resources được khai báo bao nhiêu?

**Gợi ý:** Một Pod = 600m CPU, 896Mi memory; ba Pods = 1800m CPU, 2688Mi memory, chưa tính các resource/system overhead khác.

### Bài 2 — Node còn CPU thực nhưng Pod Pending

Node có allocatable 3500m CPU; những Pods đang chạy request tổng 3000m. Pod mới request 750m. Dashboard cho thấy CPU usage 10%.

**Câu hỏi:** scheduler có thể đặt Pod mới vào node không? Vì sao Cluster Autoscaler có thể cần bổ sung node dù CPU usage thấp?

**Gợi ý:** Chỉ còn 500m allocatable chưa request nên 750m không fit.

### Bài 3 — CPU throttling

Java API có request 250m, CPU limit 500m, usage liên tục muốn vượt 500m và p99 tăng; container không bị restart.

**Câu hỏi:** đây có phải OOM không? Nên xem những metric nào và lựa chọn nào có thể giảm throttling?

**Gợi ý:** CPU limit gây throttling, không phải memory OOM; xem throttled time, CPU utilization, thread/GC và latency.

### Bài 4 — OOMKilled

Container có memory limit 1024Mi và `-Xmx1024m`, đồng thời sử dụng direct buffers, metaspace, thread stacks. Pod restart với `OOMKilled`.

**Câu hỏi:** tại sao heap không thể ăn toàn bộ memory limit? Những bước nào nên làm trước khi tăng giới hạn?

**Gợi ý:** memory limit gồm toàn bộ footprint; đo RSS/heap/native memory, điều chỉnh heap headroom và load test.

### Bài 5 — Lập lịch theo nhãn

Pod có `nodeSelector: kubernetes.io/arch: amd64`, nhưng toàn cluster chỉ có Arm64 nodes.

**Câu hỏi:** tăng CPU của node hiện tại có sửa được không? Giải pháp đúng là gì?

**Gợi ý:** không; cần node có architecture phù hợp hoặc build image multi-arch và sửa constraint có kiểm soát.

### Bài 6 — Taints và tolerations

Node pool batch có taint `dedicated=batch:NoSchedule`. Một Pod có toleration cho taint này nhưng không có nodeSelector.

**Câu hỏi:** Pod có bắt buộc chạy trên batch nodes không? Nếu muốn **chỉ** chạy ở batch nodes, cần thêm gì?

**Gợi ý:** toleration chỉ cho phép schedule; dùng node affinity/nodeSelector đúng label của node pool.

### Bài 7 — HPA tính CPU utilization

CPU request = 500m, usage = 400m, CPU limit = 1000m, HPA target 60%.

**Câu hỏi:** HPA nhìn thấy utilization bao nhiêu? Nếu chỉ tăng request lên 1000m mà usage không đổi thì tỷ lệ thành bao nhiêu?

**Gợi ý:** 80%; sau tăng request, 40%. HPA tính với **request**, không phải limit.

### Bài 8 — Autopilot tự điều chỉnh

Một Pod Autopilot Scale-Out request `1 vCPU` và `16Gi memory`, vượt ratio cho phép.

**Câu hỏi:** Có thể GKE thay đổi request nào và tại sao phải xem Pod sau admission? Vì sao thay đổi đó ảnh hưởng chi phí?

**Gợi ý:** có thể tăng CPU lên 4 vCPU để đạt ratio 1:4, theo khả năng/giới hạn ComputeClass; billable requests có thể thay đổi.

### Bài 9 — Nhiều replicas nhưng một zone

Deployment `replicas: 3` có topology spread mềm, nhưng cluster chỉ cung cấp nodes tại zone A.

**Câu hỏi:** ba replicas có bảo đảm chịu lỗi zone không? Phải thay đổi những gì ở cluster topology và scheduling?

**Gợi ý:** không; cần nodes/capacity ở nhiều zones và kiểm tra spread placement thực tế.

### Bài 10 — VPA và HPA cùng điều chỉnh

Nhóm bật HPA CPU utilization và VPA tự động thay CPU request của cùng Deployment.

**Câu hỏi:** vòng phản hồi nào có thể xảy ra? Có cách dùng VPA an toàn hơn trong giai đoạn đầu không?

**Gợi ý:** request là mẫu số của HPA, VPA đổi request khiến quyết định HPA đổi; dùng VPA `Off` để lấy recommendation trước.

### Bài 11 — Quota vs scheduling

Namespace có ResourceQuota `requests.cpu=2`. Deployment muốn tạo bốn Pods mỗi Pod request `750m`.

**Câu hỏi:** tổng request là bao nhiêu? Nếu vượt quota, đây là lỗi scheduler không tìm được node hay API từ chối tạo Pod?

**Gợi ý:** tổng 3 CPU; quota có thể từ chối admission/tạo Pod, không đơn thuần Pending vì node thiếu capacity.

### Bài 12 — Thiết kế Java Orders API

Một ứng dụng Java nhận traffic tăng gấp bốn vào cuối tuần, phụ thuộc Cloud SQL và cần p95 dưới 200ms. Hãy đề xuất:

- Baseline resource requests/limits dựa trên JVM RSS, CPU/GC và benchmark.
- HPA min/max và metric.
- Node autoscaling/Autopilot behavior.
- Spread across zones/anti-affinity, readiness, PDB.
- Observability, database connection pool, release rollback và budget.

**Gợi ý:** đo trên tải đại diện trước khi chốt con số; tránh tăng HPA max mà không tính Cloud SQL capacity.

## 20. Checklist áp dụng vào GKE thật

- [ ] Đã xác định cluster **Standard hay Autopilot**, Kubernetes/GKE version, ComputeClass và workload architecture.
- [ ] Đã phân biệt `requests` và `limits` cho CPU, memory và ephemeral storage.
- [ ] Đã hiểu đơn vị CPU `m` và memory `Mi`/`Gi`, tránh `memory: "400m"`.
- [ ] Đã cộng requests của toàn bộ containers, init-container effective requests và overhead phù hợp.
- [ ] Đã kiểm tra node **Allocatable** và phần requests đã phân bổ, không chỉ CPU usage.
- [ ] Đã xác nhận ResourceQuota/LimitRange/admission policy trong namespace.
- [ ] Đã kiểm tra event `FailedScheduling` trước khi tăng node count.
- [ ] Đã phân biệt nodeSelector, required/preferred affinity, taints/tolerations và topology spread.
- [ ] Đã kiểm tra zone topology và PVC/volume node affinity nếu ứng dụng stateful.
- [ ] Đã hiểu QoS Guaranteed/Burstable/BestEffort cùng điều kiện eviction thực tế.
- [ ] Đã kiểm tra CPU throttling, memory OOMKilled, ephemeral storage eviction và logs.
- [ ] Đã phân biệt HPA, VPA và Cluster Autoscaler; tránh vòng điều chỉnh requests gây phản ứng HPA sai.
- [ ] Trên Autopilot, đã đọc resource values **sau admission** và min/max/ratio/bursting rule hiện hành.
- [ ] Đã cấu hình readiness, liveness và startup probes phù hợp với JVM warm-up.
- [ ] Đã dùng Artifact Registry OCI image thật và đảm bảo IAM pull phù hợp.
- [ ] Đã đo SLO p95/p99, throughput, restart, availability, quota, cost theo peak traffic.
- [ ] Đã có chiến lược rollout/rollback, PDB và nhiều replicas/fault domains nếu cần HA.
- [ ] Đã xem security controls: IAM, Workload Identity Federation for GKE, network policy và secrets.
- [ ] Đã chốt owner, thay đổi có phê duyệt và dọn dẹp workloads sandbox nếu không còn dùng.

## 21. Tài liệu Google Cloud và Kubernetes chính thức

Các giá trị mặc định Autopilot, tính năng bursting, machine types, compute classes và feature gates có thể thay đổi theo phiên bản. Trước khi dùng trên môi trường production, kiểm tra tài liệu chính thức:

- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Kubernetes — Pod Quality of Service Classes](https://kubernetes.io/docs/concepts/workloads/pods/pod-qos/)
- [Kubernetes — Assign Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Kubernetes — Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)
- [Kubernetes — Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)
- [Kubernetes — Resource Quotas](https://kubernetes.io/docs/concepts/policy/resource-quotas/)
- [Kubernetes — Limit Ranges](https://kubernetes.io/docs/concepts/policy/limit-range/)
- [GKE — Resource requests in Autopilot](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-resource-requests)
- [GKE — Autopilot overview](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview)
- [GKE — About Cluster Autoscaler](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/cluster-autoscaler)
- [GKE — Configure Horizontal Pod Autoscaling](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/horizontal-pod-autoscaling)
- [GKE — Vertical Pod Autoscaling](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/verticalpodautoscaler)
- [GKE — Troubleshoot deployed workloads](https://docs.cloud.google.com/kubernetes-engine/docs/troubleshooting/deployed-workloads)
- [GKE — Pricing](https://cloud.google.com/kubernetes-engine/pricing)

**Điểm cần nhớ:** Trong GKE, **requests quyết định nơi Pod có thể được lập lịch và ảnh hưởng mức tài nguyên dự trù**, còn **limits giới hạn mức sử dụng của container lúc chạy**. **Scheduler** xem node allocatable và constraints; **HPA** thay số Pods, **VPA** hỗ trợ điều chỉnh kích thước Pods, còn **Cluster Autoscaler/Autopilot** cung cấp năng lực node. Để dịch vụ Java hoạt động an toàn, hãy kết hợp **sizing dựa trên số liệu, phân bố đa zone, probes, IAM, monitoring và kiểm soát chi phí**, sau đó xác minh bằng ứng dụng thật — không chỉ nhìn thấy Pod ở trạng thái `Running`.

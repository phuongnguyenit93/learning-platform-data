# Node, pod và phân chia trách nhiệm giữa control plane với worker

Kubernetes quản lý workload container bằng cách mô tả trạng thái mong muốn của ứng dụng rồi liên tục điều phối cluster để đạt trạng thái đó. Trong mô hình này, **control plane** ra quyết định và duy trì trạng thái điều khiển; **worker node** cung cấp CPU, bộ nhớ, mạng và storage để chạy workload; **Pod** là đơn vị triển khai nhỏ nhất mà Kubernetes schedule lên node.

Hiểu rõ ba khái niệm này giúp thiết kế compute capacity đúng cách. Một cluster có nhiều node chưa chắc chạy được nhiều workload nếu Pod yêu cầu tài nguyên vượt khả năng từng node, bị ràng buộc bởi topology hoặc thiếu network/storage. Tương tự, worker node có CPU và RAM còn trống nhưng ứng dụng vẫn có thể không được schedule nếu control plane không thể truy cập API, scheduler gặp lỗi hoặc policy không cho phép placement.

Trong module CLOUD_CORE_SERVICES_COMPUTE, bài học kết nối kiến thức máy ảo, CPU, bộ nhớ, mạng và lưu trữ với cách Kubernetes phân bổ compute. Bạn sẽ thấy control plane quyết định Pod chạy ở đâu, worker node biến quyết định đó thành container đang chạy như thế nào, và vì sao Pod có vòng đời khác với node.

Sau bài học, bạn có thể:

- Phân biệt cluster, control plane, worker node, Pod và container.
- Mô tả vai trò của API server, etcd, scheduler và controller manager.
- Giải thích kubelet, container runtime, CNI, kube-proxy và CSI trên worker node.
- Trình bày luồng từ khai báo Deployment đến khi Pod chạy và được phục vụ.
- Đọc Capacity/Allocatable của node và hiểu cách requests/limits ảnh hưởng scheduling.
- Nhận diện các trạng thái Pending, Running, Ready, Failed và các nguyên nhân Pod không schedule được.
- Chọn workload controller và cách phân bố Pod phù hợp với compute capacity và tính sẵn sàng.

## 1. Bức tranh tổng thể của Kubernetes cluster

Kubernetes cluster gồm một control plane và một tập hợp node. Trong cluster nhỏ, control plane và worker có thể cùng nằm trên một máy theo cấu hình phù hợp; trong production, control plane thường được tách biệt và có thể được nhà cung cấp quản lý.

- **Control plane:** cung cấp Kubernetes API, lưu trạng thái cluster, lập lịch Pod và điều khiển các controller.
- **Worker node:** máy tính toán thực thi Pod. Node có thể là VM hoặc máy vật lý, tùy cách triển khai cluster.
- **Pod:** đơn vị triển khai chứa một hoặc nhiều container cùng chia sẻ một số tài nguyên như network namespace và volume.
- **Container:** tiến trình ứng dụng được chạy bởi container runtime trên node.
- **Kubernetes API objects:** các đối tượng như Pod, Deployment, Service, Node, ConfigMap, Secret và PersistentVolume mô tả trạng thái mong muốn hoặc trạng thái quan sát được.

~~~mermaid
flowchart TB
    subgraph CP["Control plane"]
      API["kube-apiserver"]
      ETCD[("etcd")]
      SCH["kube-scheduler"]
      CM["kube-controller-manager"]
      CCM["cloud-controller-manager (nếu có)"]
      API <--> ETCD
      SCH --> API
      CM --> API
      CCM --> API
    end
    subgraph W1["Worker node A"]
      K1["kubelet"]
      CR1["Container runtime"]
      P1["Pod A"]
      K1 --> CR1 --> P1
    end
    subgraph W2["Worker node B"]
      K2["kubelet"]
      CR2["Container runtime"]
      P2["Pod B"]
      K2 --> CR2 --> P2
    end
    API <--> K1
    API <--> K2
    SCH -. bind Pod to node .-> API
~~~

Control plane và worker giao tiếp qua Kubernetes API và các giao thức liên quan. Scheduler không trực tiếp chạy container; nó chọn node rồi ghi quyết định vào API. Kubelet trên node quan sát Pod được giao cho mình và yêu cầu container runtime tạo container tương ứng.

### Cluster không đồng nghĩa với một máy lớn

Một cluster có thể gồm nhiều VM có kích thước khác nhau, nhiều nhóm node (node pool) và nhiều miền lỗi. Kubernetes nhìn các node như nguồn tài nguyên có thể được phân bổ, nhưng từng Pod vẫn phải phù hợp với năng lực và policy của node được chọn.

Ví dụ, tổng cluster có 64 vCPU nhưng một Pod yêu cầu 20 CPU. Nếu không node nào có đủ CPU allocatable còn lại để đáp ứng request đó, Pod có thể Pending dù tổng CPU còn trống cộng dồn trên các node lớn hơn 20. Scheduler không tự chia một Pod thành nhiều node.

## 2. Control plane làm nhiệm vụ gì?

Control plane duy trì trạng thái mong muốn và điều phối các thành phần trong cluster. Các thành phần lõi thường gồm:

| Thành phần | Trách nhiệm chính | Điều không trực tiếp làm |
|---|---|---|
| kube-apiserver | Cổng API; xác thực, phân quyền, admission và cung cấp giao diện cho client/component | Không tự chọn node cho Pod |
| etcd | Kho key-value nhất quán lưu trạng thái cluster và cấu hình quan trọng | Không chạy container ứng dụng |
| kube-scheduler | Chọn node phù hợp cho Pod chưa được gán node | Không tạo container trên node |
| kube-controller-manager | Chạy các controller để so sánh trạng thái thực với trạng thái mong muốn và thực hiện điều chỉnh | Không thay thế kubelet trong việc chạy container |
| cloud-controller-manager | Tích hợp với cloud provider cho một số chức năng như node, route và load balancer | Không bắt buộc ở mọi cluster hoặc mọi môi trường |

Một số cluster còn có thành phần bổ sung như API aggregation, admission webhook, scheduler profile hoặc controller do nhà cung cấp và ứng dụng cài đặt.

### kube-apiserver

Kubernetes API là điểm giao tiếp trung tâm. Người dùng, CI/CD, scheduler, controller và kubelet trao đổi thông tin thông qua API server.

Khi chạy lệnh kubectl apply, client gửi manifest đến API server. API server xác thực request, kiểm tra quyền, chạy admission chain và lưu object hợp lệ vào etcd. Các component khác watch hoặc đọc API để phản ứng với thay đổi.

API server có thể chạy nhiều replica phía sau load balancer. Trong cluster tự quản lý, cần bảo vệ endpoint, certificate, authentication, authorization và audit log. Trong managed Kubernetes, provider thường vận hành control plane nhưng khách hàng vẫn chịu trách nhiệm về quyền truy cập API và cấu hình workload.

### etcd

etcd lưu dữ liệu trạng thái của Kubernetes như object, metadata và cấu hình cluster. Nó là thành phần quan trọng của control plane.

Các nguyên tắc vận hành:

- Duy trì quorum theo thiết kế cluster; không tùy tiện giảm số thành viên.
- Bảo vệ dữ liệu bằng backup/snapshot và kiểm thử restore.
- Mã hóa dữ liệu nhạy cảm theo cấu hình phù hợp.
- Theo dõi latency, disk I/O, dung lượng và health của etcd.
- Không cho ứng dụng workload truy cập trực tiếp etcd.
- Tránh lưu dữ liệu ứng dụng nghiệp vụ vào etcd; dùng database hoặc storage phù hợp.

Mất quorum etcd có thể làm cluster không ghi được trạng thái mới, ảnh hưởng scheduling và controller. Các Pod đang chạy có thể tiếp tục xử lý trong một khoảng thời gian, nhưng việc tạo, cập nhật hoặc điều phối mới có thể bị ảnh hưởng.

### kube-scheduler

Scheduler theo dõi Pod chưa có nodeName và tìm node phù hợp. Quá trình khái quát gồm:

1. Lọc node không đáp ứng điều kiện (filtering).
2. Chấm điểm các node còn lại theo policy (scoring).
3. Chọn node có điểm phù hợp.
4. Ghi binding/assignment thông qua API.
5. Kubelet trên node nhận biết Pod được giao và bắt đầu triển khai.

Scheduler xét nhiều yếu tố: CPU/memory requests, node selector, node affinity, taints/tolerations, topology spread, volume constraints, pod affinity/anti-affinity và các policy/plugin đang bật.

Scheduler không đơn giản chọn node có CPU utilization thấp nhất. Nó chủ yếu dựa trên requests và điều kiện placement; actual usage, giới hạn tài nguyên, policy và scoring có thể được xử lý theo plugin/cấu hình cụ thể.

### kube-controller-manager

Controller là các vòng lặp reconciliation. Mỗi controller quan sát trạng thái hiện tại và điều chỉnh để gần với trạng thái mong muốn.

Ví dụ:

- Deployment controller quản lý ReplicaSet.
- ReplicaSet controller tạo hoặc xóa Pod để đạt số replica.
- Node controller theo dõi trạng thái node.
- Job controller điều phối Pod thực hiện công việc hữu hạn.
- EndpointSlice controller cập nhật backend endpoint cho Service.

Nếu khai báo Deployment có 3 replica nhưng chỉ có 2 Pod Ready, controller sẽ tiếp tục cố tạo hoặc khôi phục replica thứ ba khi điều kiện cho phép. Controller không bảo đảm ngay lập tức đạt trạng thái mong muốn nếu thiếu capacity hoặc policy ngăn placement.

## 3. Worker node cung cấp compute và chạy Pod

Worker node là máy tính toán thực tế. Nó có thể là VM cloud, bare-metal server hoặc node do dịch vụ Kubernetes quản lý. Node cần tài nguyên và các agent để tham gia cluster.

Các thành phần thường gặp:

- **kubelet:** agent trên node, đảm bảo Pod được giao cho node được chạy theo PodSpec.
- **Container runtime:** tải image và chạy container thông qua Container Runtime Interface (CRI), ví dụ containerd hoặc CRI-O.
- **CNI plugin:** cấu hình kết nối mạng cho Pod theo mô hình network của cluster.
- **kube-proxy hoặc dataplane thay thế:** triển khai một phần chức năng Service networking; một số cluster dùng eBPF hoặc giải pháp khác thay thế kube-proxy.
- **CSI node plugin:** tích hợp mount/attach volume cho workload khi dùng storage qua Container Storage Interface.
- **Node-level agents:** telemetry, log, security, device plugin hoặc agent do platform cài đặt.

Không phải mọi node đều có đúng cùng tập daemon. Cấu hình phụ thuộc Kubernetes distribution, cloud provider, CNI, CSI và chính sách vận hành.

### kubelet

Kubelet đăng ký/duy trì trạng thái node, theo dõi Pod được gán cho node và làm việc với container runtime. Nó:

- Đọc PodSpec được API server cung cấp.
- Yêu cầu runtime tạo sandbox và container.
- Mount volume theo cấu hình.
- Thực hiện startup, readiness và liveness probe.
- Gửi trạng thái Pod/node về API server.
- Phối hợp với cơ chế eviction khi node chịu áp lực tài nguyên.

Kubelet không phải scheduler. Nó không tự quyết định Pod nên chạy trên node nào; nó thực thi các Pod đã được gán cho node của mình.

### Container runtime và CRI

Container runtime chịu trách nhiệm pull image, tạo container và quản lý vòng đời tiến trình. Kubernetes giao tiếp với runtime qua CRI.

Image được lưu trong cache node có thể giúp khởi động nhanh hơn. Tuy nhiên, không nên dựa vào cache local như nguồn duy nhất; khi Pod chuyển sang node khác, node mới có thể phải pull image lại từ registry.

Cần chuẩn bị:

- Image registry truy cập được từ mọi node cần chạy workload.
- Image version/digest rõ ràng.
- Image pull secret hoặc workload identity phù hợp.
- Dung lượng disk cho image layer và writable layer.
- Runtime version tương thích với Kubernetes và node OS.

### CNI, kube-proxy và CSI

| Thành phần | Vai trò | Phạm vi |
|---|---|---|
| CNI | Cấp địa chỉ và kết nối mạng cho Pod; có thể áp dụng policy | Pod network |
| kube-proxy hoặc dataplane tương đương | Chuyển tiếp traffic đến endpoint của Service theo triển khai | Service networking |
| CSI | Tích hợp storage driver để attach/mount volume | Persistent/ephemeral volume |

CNI, kube-proxy và CSI không phải control plane core bắt buộc cùng một kiểu trên mọi cluster. Một số chức năng có thể do cloud provider hoặc dataplane khác cung cấp.

## 4. Node, Pod và container khác nhau như thế nào?

| Đối tượng | Là gì? | Vòng đời | Tài nguyên |
|---|---|---|---|
| Node | Máy tính toán tham gia cluster | Có thể được thêm, cordon, drain, upgrade hoặc xóa | CPU, RAM, disk, network, thiết bị |
| Pod | Đơn vị scheduling chứa một hoặc nhiều container | Thường ngắn hơn node; có thể bị tạo lại trên node khác | Tổng requests/limits của các container và overhead liên quan |
| Container | Tiến trình ứng dụng được runtime chạy | Có thể restart trong cùng Pod | Bị giới hạn bởi cấu hình tài nguyên của container/Pod và runtime |
| Deployment | Controller mô tả replica và rollout cho ứng dụng stateless | Quản lý qua nhiều Pod và revision | Không tự cung cấp CPU/RAM; Pod template mới khai báo resources |
| Service | Endpoint ổn định để truy cập nhóm Pod | Tồn tại độc lập với từng Pod IP | Không phải compute instance |

### Pod là đơn vị scheduling

Scheduler gán Pod lên một node. Các container trong cùng Pod luôn được đặt cùng node và chia sẻ một số namespace/tài nguyên.

Các container trong một Pod thường:

- Dùng chung network namespace và cùng một Pod IP.
- Có thể gọi nhau qua localhost nếu dùng port khác nhau.
- Có thể chia sẻ volume được khai báo ở Pod.
- Có thể dùng pattern sidecar, init container hoặc application container.
- Được quản lý như một đơn vị về placement và vòng đời Pod.

Không nên gom nhiều ứng dụng độc lập vào một Pod chỉ để tiết kiệm node. Khi cần scale hoặc release độc lập, nên tách thành các Pod riêng và kết nối qua Service.

### Pod không phải VM thu nhỏ

Pod không có kernel riêng như VM. Container trong Pod dùng kernel của node và được cô lập bằng các cơ chế OS như namespaces và cgroups. Vì vậy:

- Kernel/OS compatibility liên quan đến node.
- Một Pod bị lỗi không đồng nghĩa node bị lỗi.
- Node bị lỗi có thể ảnh hưởng nhiều Pod cùng lúc.
- Security boundary của container khác với VM boundary.
- Pod IP và container ID có thể thay đổi khi Pod được tạo lại.

### Pod IP và Service

Pod thường có địa chỉ IP riêng trong cluster network, nhưng Pod IP có thể thay đổi khi Pod được tạo lại. Client không nên hardcode Pod IP. Service cung cấp endpoint ổn định và phân phối traffic đến các Pod backend đủ điều kiện.

## 5. Luồng từ manifest đến Pod chạy trên worker node

Giả sử người dùng tạo Deployment có 3 replica:

1. kubectl apply gửi manifest đến API server.
2. API server xác thực, authorize, chạy admission và lưu Deployment vào etcd.
3. Deployment controller quan sát Deployment và tạo ReplicaSet.
4. ReplicaSet controller tạo 3 Pod object.
5. Scheduler phát hiện Pod chưa được gán node.
6. Scheduler lọc và chấm điểm node dựa trên resource requests và policy.
7. Scheduler ghi binding cho mỗi Pod.
8. Kubelet ở worker node tương ứng nhận PodSpec.
9. Kubelet gọi runtime qua CRI để tạo Pod sandbox và container.
10. CNI thiết lập network cho Pod.
11. CSI hoặc kubelet mount volume nếu Pod yêu cầu storage.
12. Container chạy; startup/readiness/liveness probe được thực hiện.
13. Pod chuyển sang Ready khi điều kiện readiness thành công.
14. Service/EndpointSlice đưa endpoint phù hợp vào đường traffic.

~~~mermaid
sequenceDiagram
    participant U as User/kubectl
    participant API as API server
    participant E as etcd
    participant C as Controllers
    participant S as Scheduler
    participant K as kubelet
    participant R as Runtime/CNI/CSI
    U->>API: Apply Deployment
    API->>E: Persist desired state
    API-->>U: Accepted
    C->>API: Watch Deployment
    C->>API: Create ReplicaSet and Pods
    S->>API: Watch unscheduled Pods
    S->>API: Bind Pod to selected Node
    K->>API: Observe assigned Pod
    K->>R: Create sandbox, containers and mounts
    R-->>K: Runtime/network/storage ready
    K->>API: Report Pod status and probes
~~~

Nếu Pod không chạy, hãy xác định nó đang dừng ở bước nào: chưa được schedule, image pull lỗi, volume mount lỗi, container crash hay readiness chưa đạt. Mỗi trạng thái cần hướng điều tra khác nhau.

## 6. Node Capacity và Allocatable

Node có tổng tài nguyên phần cứng (Capacity), nhưng không phải toàn bộ đều dành cho workload Pod.

- **Capacity:** tổng tài nguyên node công bố, ví dụ CPU, memory, ephemeral storage và số Pod tối đa.
- **Allocatable:** lượng tài nguyên node dành cho Pod sau khi trừ phần dành cho hệ điều hành, kubelet và các reservation theo cấu hình.
- **Requested:** tổng requests đã được scheduler tính cho các Pod đã gán node.
- **Actual usage:** lượng CPU/memory workload đang sử dụng thực tế tại thời điểm đo.

Ví dụ node có 8 vCPU và 32 GiB RAM. Nếu hệ điều hành và các system daemon được reserve 1 CPU và 3 GiB, allocatable có thể còn khoảng 7 CPU và 29 GiB. Đây chỉ là số minh họa; giá trị thật cần đọc từ Node object và cấu hình node.

~~~text
Node Capacity
  CPU:       8 vCPU
  Memory:    32 GiB
       |
       | trừ system/kube reservations
       v
Node Allocatable
  CPU:       7 vCPU
  Memory:    29 GiB
       |
       | trừ tổng Pod requests đã đặt
       v
Phần allocatable còn lại cho Pod mới
~~~

Scheduler chủ yếu dùng requests để đánh giá khả năng đặt Pod. Nếu tổng requests vượt allocatable, Pod mới có thể không được schedule dù actual usage hiện tại thấp. Đây là cơ chế bảo vệ capacity trước mức tiêu thụ đã cam kết của workload.

### Xem node capacity bằng kubectl

~~~bash
kubectl get nodes
kubectl describe node <node-name>
kubectl get nodes -o custom-columns=NAME:.metadata.name,CPU:.status.capacity.cpu,CPU_ALLOC:.status.allocatable.cpu,MEMORY:.status.capacity.memory,MEMORY_ALLOC:.status.allocatable.memory
~~~

Trong kubectl describe node, xem các phần Capacity, Allocatable, Conditions, Addresses, Taints và Non-terminated Pods. Các giá trị requests/limits của Pod được liệt kê giúp phát hiện node đã phân bổ bao nhiêu tài nguyên theo yêu cầu.

## 7. Requests và limits của Pod

Container có thể khai báo CPU/memory requests và limits. Đây là cơ chế quan trọng để scheduler placement và node quản lý tài nguyên.

- **Request:** lượng tài nguyên được dùng để lập lịch và làm cơ sở cho một số quyết định quản lý tài nguyên.
- **Limit:** giới hạn tài nguyên container được phép sử dụng theo semantics của resource.
- CPU limit thường được thực thi bằng throttling khi container vượt quota trong khoảng thời gian đo.
- Memory limit thường được thực thi bằng cơ chế OOM kill khi mức dùng vượt ngưỡng, tùy trạng thái node và kernel.

Ví dụ:

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: compute-example
spec:
  containers:
    - name: app
      image: registry.example/compute-app:1.0.0
      resources:
        requests:
          cpu: "500m"
          memory: "512Mi"
        limits:
          cpu: "1"
          memory: "1Gi"
~~~

Pod này yêu cầu scheduler dành 0,5 CPU và 512 MiB memory theo request. Container có thể dùng tối đa 1 CPU và 1 GiB memory theo limit. CPU 500m tương đương nửa CPU core theo đơn vị Kubernetes; 1 tương đương một CPU unit được Kubernetes định nghĩa.

### Tổng requests của Pod nhiều container

Pod có thể có nhiều application container, sidecar và init container. Scheduler tính resource request của Pod theo quy tắc tổng hợp của Kubernetes; init container có thể làm thay đổi request hiệu dụng của Pod so với việc chỉ cộng các container chạy đồng thời. Với Pod có sidecar injection hoặc init container, cần kiểm tra resource request thực tế sau admission.

### QoS classes

Kubernetes phân loại Pod thành các QoS class dựa trên requests/limits của container:

- **Guaranteed:** điều kiện requests và limits CPU/memory của mọi container phù hợp và bằng nhau theo quy tắc Kubernetes.
- **Burstable:** có ít nhất một request hoặc limit nhưng không đáp ứng điều kiện Guaranteed.
- **BestEffort:** không khai báo request/limit CPU và memory cho container.

QoS class ảnh hưởng đến thứ tự xử lý khi node thiếu tài nguyên, nhưng không phải cam kết tuyệt đối rằng Pod Guaranteed sẽ không bị ảnh hưởng. Node pressure, system failure và các điều kiện khác vẫn có thể làm Pod bị gián đoạn.

### Tránh khai báo tài nguyên tùy tiện

- Request quá thấp: scheduler có thể đặt quá nhiều Pod lên node, gây contention khi tải tăng.
- Request quá cao: capacity bị giữ trên giấy, Pod khó schedule và autoscaler có thể tạo thêm node không cần thiết.
- CPU limit quá thấp: throttling có thể làm tăng latency dù node còn CPU.
- Memory limit quá thấp: container có thể OOMKilled.
- Không khai báo request: scheduler khó dự đoán nhu cầu và QoS có thể là BestEffort.

Hãy đo tải đại diện, đặt request theo nhu cầu ổn định và limit theo chính sách bảo vệ phù hợp. Theo dõi actual usage và saturation để điều chỉnh.

## 8. Scheduler placement: vì sao Pod được đặt ở node này?

Scheduler chọn node dựa trên các ràng buộc và điểm số. Những yếu tố thường gặp:

- CPU/memory/ephemeral-storage requests còn đủ.
- nodeSelector hoặc node affinity.
- Taints của node và tolerations của Pod.
- Pod affinity/anti-affinity.
- Topology spread constraints.
- Volume zone/node constraints.
- Node condition và khả năng nhận Pod.
- Extended resources như GPU hoặc thiết bị do device plugin công bố.
- Policy/plugin scheduler được cluster cấu hình.

### Node selector

Dùng label để yêu cầu Pod chạy trên node có thuộc tính nhất định, ví dụ nhóm GPU hoặc kiến trúc CPU.

~~~yaml
spec:
  nodeSelector:
    kubernetes.io/arch: amd64
    workload-pool: batch
~~~

Nếu không node nào có đủ label, Pod sẽ Pending. Cần kiểm tra label thực tế và tránh hardcode label tự đặt mà không có quy trình quản lý.

### Taints và tolerations

Taint đánh dấu node để từ chối Pod không có toleration phù hợp. Toleration cho phép Pod được xem xét trên node có taint; nó không bảo đảm Pod sẽ được schedule lên node đó.

Ví dụ node GPU có taint dành cho workload cần GPU. Chỉ Pod có toleration phù hợp mới có thể chạy ở đó; Pod vẫn cần khai báo extended resource và các điều kiện placement khác.

### Affinity và topology spread

Pod anti-affinity hoặc topology spread có thể giúp replica phân bố qua node/zone để giảm correlated failure. Tuy nhiên, nếu cluster không đủ node hoặc topology domain, ràng buộc quá chặt có thể làm Pod Pending.

Cần cân bằng giữa tính sẵn sàng, utilization và khả năng schedule. Ví dụ, yêu cầu ba replica ở ba zone khác nhau cần ít nhất ba domain hợp lệ và capacity tương ứng.

## 9. Pod lifecycle và trạng thái

Pod là đối tượng có vòng đời ngắn. Khi Pod bị xóa hoặc node mất, Kubernetes có thể tạo Pod mới theo controller, nhưng Pod mới thường có UID và IP khác.

Một số phase thường gặp:

| Phase | Ý nghĩa | Điều cần kiểm tra |
|---|---|---|
| Pending | Được chấp nhận nhưng chưa hoàn tất setup, có thể đang chờ schedule hoặc chuẩn bị container | Events, scheduler, image pull, volume |
| Running | Pod đã được gán node và ít nhất một container đang chạy hoặc khởi động | Container state, logs, probes |
| Succeeded | Các container kết thúc thành công | Job completion và output |
| Failed | Các container kết thúc với lỗi hoặc Pod không thể hoàn tất | Exit code, logs, events |
| Unknown | Không thể xác định trạng thái, thường do node communication issue | Node health và kubelet connectivity |

Ready không phải Pod phase; đây là condition cho biết Pod có sẵn sàng nhận traffic theo readiness probe và điều kiện liên quan hay không.

### Probe

- **Startup probe:** cho phép ứng dụng có thời gian khởi động; liveness/readiness có thể được trì hoãn cho đến khi startup probe thành công.
- **Readiness probe:** quyết định Pod có nên nhận traffic qua Service hay không.
- **Liveness probe:** xác định container có cần được restart hay không.

Probe phải kiểm tra đúng điều kiện. Liveness probe quá nhạy có thể tạo restart loop khi dependency chậm; readiness probe quá rộng có thể loại toàn bộ Pod khỏi traffic vì một dependency phụ không thiết yếu.

### Pod restart và replacement

Container có thể restart bên trong cùng Pod; Pod object cũng có thể bị controller thay thế bằng Pod mới. Cần phân biệt restartCount, Pod UID và owner reference khi điều tra. Không dùng local filesystem của Pod làm nơi lưu dữ liệu duy nhất nếu Pod có thể được tạo lại.

## 10. Workload controllers và cách chúng dùng node

Các workload controller mô tả cách Pod được tạo và duy trì:

| Controller | Mục đích | Ví dụ |
|---|---|---|
| Deployment | Quản lý ứng dụng stateless, rollout và replica | API web, frontend |
| ReplicaSet | Duy trì số lượng Pod theo template | Thường được Deployment quản lý |
| StatefulSet | Workload cần identity/network/storage ổn định theo ordinal | Database hoặc hệ thống stateful phù hợp |
| DaemonSet | Chạy một Pod trên mỗi node hoặc tập node được chọn | Log agent, network/security agent |
| Job | Chạy công việc hữu hạn đến khi hoàn tất | Batch, migration job |
| CronJob | Tạo Job theo lịch | Báo cáo hàng đêm, cleanup |
| ReplicationController | Cơ chế cũ; hiện thường dùng Deployment/ReplicaSet | Workload legacy |

### Deployment ví dụ

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: compute-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: compute-api
  template:
    metadata:
      labels:
        app: compute-api
    spec:
      containers:
        - name: api
          image: registry.example/compute-api:1.4.2
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1"
              memory: "512Mi"
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
            periodSeconds: 10
~~~

Deployment yêu cầu ba replica. Controller tạo Pod và thay thế Pod khi cần đạt số lượng mong muốn. Scheduler quyết định node cho từng Pod; kubelet trên node thực thi container.

### DaemonSet và node-level compute

DaemonSet thường được dùng cho agent cần hiện diện trên mỗi node, ví dụ log collector hoặc security agent. Những Pod này cũng tiêu thụ CPU/RAM của node, vì vậy cần tính vào capacity. Nếu agent tăng memory usage, workload application có thể bị thiếu allocatable dù requests của ứng dụng không đổi.

## 11. Networking: Pod network và Service

Mỗi Pod thường có một địa chỉ IP riêng trong cluster network. Container trong cùng Pod chia sẻ network namespace, nên chúng có thể giao tiếp qua localhost. Pod khác giao tiếp qua Pod IP hoặc Service.

Các thành phần:

- CNI plugin tạo interface và kết nối Pod vào cluster network.
- Network policy plugin có thể kiểm soát traffic giữa Pod, namespace và endpoint.
- Service cung cấp địa chỉ/DNS ổn định cho nhóm Pod.
- EndpointSlice phản ánh các endpoint backend đủ điều kiện.
- Ingress hoặc Gateway API có thể quản lý traffic vào cluster ở tầng HTTP/TLS.
- kube-proxy hoặc dataplane thay thế xử lý Service routing theo triển khai.

### Pod IP không phải endpoint bền vững

Khi Pod bị thay thế, IP có thể đổi. Ứng dụng nên dùng DNS Service như compute-api.namespace.svc thay vì hardcode IP của Pod.

Ví dụ Service:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: compute-api
spec:
  selector:
    app: compute-api
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

Service chọn Pod có label phù hợp và đủ điều kiện endpoint. Nếu readiness probe thất bại, Pod thường không được đưa vào endpoint phục vụ thông thường. Cần kiểm tra selector, labels, ports và EndpointSlice khi Service không route được.

### Network performance

Với compute workload, network có thể trở thành giới hạn:

- Pod-to-Pod traffic qua node hoặc zone.
- Overlay/encapsulation overhead tùy CNI.
- Bandwidth/packet rate của VM node.
- MTU không tương thích.
- Network policy và dataplane processing.
- Egress/NAT hoặc cloud load balancer quota.

Theo dõi throughput, packet drops, retransmission, latency và connection count ở cả node lẫn ứng dụng.

## 12. Storage: ephemeral và persistent volume

Container filesystem thường có writable layer gắn với vòng đời container/Pod. Khi Pod bị tạo lại, dữ liệu trong layer có thể mất.

### Ephemeral storage

Node cung cấp ephemeral storage cho image layer, writable layer và một số volume tạm như emptyDir. Đây là tài nguyên hữu hạn; sử dụng quá mức có thể làm node disk pressure và dẫn đến eviction.

Có thể khai báo request/limit cho ephemeral storage để Kubernetes quản lý theo cấu hình:

~~~yaml
resources:
  requests:
    ephemeral-storage: "1Gi"
  limits:
    ephemeral-storage: "2Gi"
~~~

### Persistent volume

Với dữ liệu cần tồn tại qua Pod replacement, dùng PersistentVolumeClaim và storage provisioner/CSI phù hợp. Volume lifecycle có thể độc lập với Pod nhưng còn phụ thuộc access mode, storage class, zone và driver.

Không phải mọi volume đều có thể mount đồng thời trên nhiều node. Khi Pod được schedule sang zone khác, volume có thể không attach được nếu storage topology giới hạn. Scheduler và CSI topology cần phối hợp để đặt Pod ở nơi volume có thể sử dụng.

## 13. Node health, cordon, drain và thay thế node

Node có thể chuyển trạng thái NotReady khi kubelet mất kết nối, runtime lỗi, network không hoạt động hoặc host gặp sự cố. Kubernetes có thể đánh dấu node condition và xử lý Pod theo policy.

Các khái niệm vận hành:

- **cordon:** đánh dấu node không nhận Pod mới qua scheduler.
- **drain:** evict Pod phù hợp để chuẩn bị bảo trì/xóa node; kết quả phụ thuộc DaemonSet, PodDisruptionBudget và các tùy chọn lệnh.
- **uncordon:** cho phép scheduler xem xét node trở lại.
- **Node replacement:** tạo node mới, để workload được schedule lại, rồi loại node cũ.

Ví dụ:

~~~bash
kubectl cordon <node-name>
kubectl drain <node-name> --ignore-daemonsets
kubectl get pods -A -o wide
kubectl uncordon <node-name>
~~~

Lệnh drain có thể bị chặn bởi PodDisruptionBudget hoặc các Pod không được controller quản lý. Không dùng force hoặc delete-emptydir-data nếu chưa hiểu rõ tác động đến workload và dữ liệu.

### PodDisruptionBudget

PodDisruptionBudget (PDB) giới hạn mức gián đoạn tự nguyện đối với một nhóm Pod, ví dụ số Pod tối thiểu cần sẵn sàng trong quá trình drain. PDB không bảo vệ khỏi node crash, mất điện hoặc region outage; nó chủ yếu phối hợp với eviction do voluntary disruption.

Để drain an toàn, cần đủ replica, readiness đúng, capacity ở node khác và PDB phù hợp. PDB quá chặt có thể chặn bảo trì; PDB quá lỏng có thể làm giảm availability.

### Node pressure và eviction

Khi node thiếu memory, disk hoặc inode, kubelet có thể kích hoạt eviction theo threshold và priority. Pod BestEffort hoặc Pod có mức sử dụng vượt request có thể bị ảnh hưởng sớm hơn tùy điều kiện. Hãy theo dõi Node Conditions như MemoryPressure, DiskPressure và PIDPressure, cùng eviction events.

## 14. Compute capacity planning cho Kubernetes

Capacity planning phải tính cả workload và chi phí hệ thống trên node.

### Tính tổng request

Giả sử mỗi Pod API yêu cầu 500m CPU và 512Mi memory. Có 6 replica:

- CPU requests tổng: 6 × 0,5 = 3 CPU.
- Memory requests tổng: 6 × 512Mi = 3.072Mi (khoảng 3 GiB).

Nếu node allocatable còn 7 CPU và 29 GiB, về lý thuyết có thể chứa các Pod này cùng workload khác trong giới hạn request. Nhưng còn phải xét DaemonSet, Pod overhead, topology, anti-affinity, volume zone và headroom.

Không nên lập kế hoạch chỉ dựa trên tổng request. Cần quan sát actual usage, burst, node system overhead và khả năng chịu lỗi khi một node/zone mất.

### Headroom và N+1

Nếu workload cần tiếp tục phục vụ khi mất một node, cluster cần đủ capacity còn lại để chạy replica trên các node khác. Với N+1, tính toán capacity không chỉ cho trạng thái bình thường mà còn cho trạng thái sau một node hoặc miền lỗi bị loại.

### Node pools

Có thể tách node pool theo đặc tính workload:

- General-purpose cho API và service thông thường.
- Compute-optimized cho tác vụ CPU-bound.
- Memory-optimized cho cache hoặc workload cần RAM lớn.
- GPU/accelerator pool cho ML hoặc xử lý chuyên dụng.
- Spot/interruptible pool cho batch có thể retry.
- System pool dành cho các thành phần nền tảng.

Node pool tách biệt giúp quản lý instance family, autoscaling, taint/label và chi phí. Tuy nhiên, workload cần có toleration/affinity phù hợp và pool phải có capacity.

### Cluster autoscaler và workload autoscaler

- Horizontal Pod Autoscaler (HPA) điều chỉnh số replica dựa trên metric như CPU, memory hoặc custom metric.
- Vertical Pod Autoscaler (VPA) có thể đề xuất hoặc điều chỉnh requests theo chế độ/cấu hình.
- Cluster Autoscaler hoặc node autoscaler thêm/bớt node khi Pod không schedule được hoặc node dư capacity, tùy triển khai.

HPA có thể tăng replica nhưng nếu node pool hết capacity, Pod vẫn Pending. Node autoscaler có thể tạo node mới nhưng cần thời gian boot, pull image và readiness. Cần headroom và scale signal phù hợp.

## 15. Troubleshooting: từ Pod Pending đến node NotReady

Khi Pod không chạy, đừng bắt đầu bằng việc tăng số node một cách mù quáng. Xác định điểm thất bại trong chuỗi API → scheduler → kubelet → runtime/network/storage.

### Pod Pending

~~~bash
kubectl get pods -A
kubectl describe pod <pod-name> -n <namespace>
kubectl get events -n <namespace> --sort-by=.lastTimestamp
~~~

Các nguyên nhân thường gặp:

- Insufficient cpu hoặc Insufficient memory: requests không vừa allocatable node.
- node(s) didn't match Pod's node affinity/selector: label hoặc affinity không phù hợp.
- untolerated taint: Pod thiếu toleration.
- volume node affinity conflict: volume và node ở topology khác nhau.
- pod has unbound immediate PersistentVolumeClaims: PVC chưa bind.
- Topology spread/anti-affinity quá chặt.
- Không có node phù hợp với extended resource như GPU.

### ImagePullBackOff hoặc ErrImagePull

Kiểm tra image name/tag/digest, registry connectivity, credentials, image pull secret và architecture. Một image amd64 không chạy trực tiếp trên node arm64 nếu không có manifest multi-arch hoặc build phù hợp.

### CrashLoopBackOff

Kiểm tra logs trước/sau restart, exit code, command/args, config, secret, volume mount, OOMKilled và probe. CrashLoopBackOff là trạng thái backoff giữa các lần restart, không phải nguyên nhân gốc.

### Node NotReady

~~~bash
kubectl get nodes
kubectl describe node <node-name>
kubectl get pods -A -o wide
~~~

Kiểm tra kubelet heartbeat, container runtime, CNI, disk/memory pressure, node networking, certificate và cloud VM health. Trong managed Kubernetes, provider có thể cung cấp thêm node diagnostics; vẫn cần kiểm tra event và workload impact ở phía cluster.

### Service không có endpoint

~~~bash
kubectl get svc -n <namespace>
kubectl get endpointslices -n <namespace>
kubectl describe svc <service-name> -n <namespace>
~~~

Kiểm tra selector có khớp Pod labels không, Pod có Ready không, targetPort đúng không và network policy có chặn traffic không.

## 16. Bảo mật và phân chia trách nhiệm

Kubernetes không tự động bảo đảm mọi Pod an toàn chỉ vì chúng chạy trong cluster. Trách nhiệm được chia giữa cloud provider/platform team và application team.

### Control plane

- Bảo vệ API endpoint và certificate.
- Cấu hình authentication, RBAC và admission policy.
- Mã hóa secrets at rest theo khả năng nền tảng.
- Backup/restore etcd hoặc dùng dịch vụ control plane managed theo hướng dẫn provider.
- Audit API requests và hạn chế quyền cluster-admin.
- Cập nhật Kubernetes version và kiểm soát compatibility.

### Worker node

- Vá OS/kernel và container runtime.
- Giới hạn SSH/remote access; dùng identity và access gateway.
- Bảo vệ kubelet endpoint và node credentials.
- Cấu hình disk encryption và secure boot nếu có.
- Quản lý image provenance, vulnerability scan và registry access.
- Giám sát runtime, node agent và network policy.

### Pod/workload

- Chạy non-root khi có thể.
- Dùng securityContext, seccomp và capabilities tối thiểu.
- Không chạy privileged nếu không có lý do rõ ràng.
- Giới hạn service account token và dùng RBAC least privilege.
- Đặt CPU/memory/ephemeral-storage requests/limits.
- Dùng NetworkPolicy khi CNI hỗ trợ.
- Đưa secret vào qua secret manager/CSI hoặc Kubernetes Secret được bảo vệ.
- Không ghi credential vào image, manifest công khai hoặc log.

### Shared responsibility trong managed Kubernetes

Nhà cung cấp có thể vận hành control plane, etcd, API availability và một phần upgrade. Khách hàng thường vẫn chịu trách nhiệm về worker configuration, Pod security, RBAC, network policy, image, dữ liệu, workload availability và capacity. Ranh giới cụ thể tùy managed service.

## 17. Ví dụ thực tế: triển khai API trên ba worker node

Một ứng dụng API cần ba replica để phục vụ người dùng. Cluster có ba worker node, mỗi node có 4 vCPU và 16 GiB RAM. Sau khi trừ system reservation, giả sử allocatable mỗi node còn 3,5 CPU và 14 GiB.

Mỗi Pod API khai báo request 500m CPU và 512Mi memory. Ba Pod cần tổng cộng 1,5 CPU và 1,5 GiB theo requests. Scheduler có thể phân bố mỗi Pod trên một node nếu topology spread hoặc anti-affinity được cấu hình. Nếu không có ràng buộc, scheduler có thể đặt nhiều Pod trên cùng node theo scoring.

Khi node 2 bị NotReady:

1. Node controller phát hiện heartbeat không còn.
2. Các Pod trên node có thể chuyển trạng thái Unknown/Terminating theo timeout và policy.
3. Deployment/ReplicaSet tiếp tục duy trì số replica mong muốn.
4. Scheduler tìm node khác đủ capacity cho Pod thay thế.
5. Kubelet ở node mới pull image, tạo container và cấu hình network.
6. Readiness probe thành công, endpoint được cập nhật.
7. Service tiếp tục route traffic đến các Pod Ready còn lại.

Để chịu lỗi node mà không giảm quá mức capacity, cluster phải có đủ headroom trên node 1 và 3. Nếu hai node còn lại đã đầy requests, Pod thay thế có thể Pending. Ba replica trong manifest không tự tạo ra capacity vật lý.

### Lệnh quan sát ví dụ

~~~bash
kubectl get nodes -o wide
kubectl get pods -n production -o wide
kubectl top nodes
kubectl top pods -n production
kubectl describe node <node-name>
kubectl describe pod <pod-name> -n production
~~~

kubectl top cần Metrics Server hoặc nguồn metrics tương thích. Số liệu usage là ảnh chụp tại thời điểm truy vấn; dùng monitoring dài hạn để phân tích xu hướng và saturation.

## 18. Checklist thiết kế và vận hành Kubernetes compute

### Kiến trúc cluster

- [ ] Đã xác định control plane managed hay self-managed.
- [ ] API server, etcd, scheduler và controller có health/availability phù hợp.
- [ ] Worker node có OS/runtime/CNI/CSI tương thích.
- [ ] Có node pool phù hợp CPU, memory, GPU và workload class.
- [ ] Có capacity dự phòng cho node/zone failure.

### Pod và resource

- [ ] Pod được thiết kế với container boundary hợp lý.
- [ ] CPU/memory requests được đo và khai báo.
- [ ] Limits được đặt theo latency, stability và policy.
- [ ] Ephemeral storage được dự trù và giám sát.
- [ ] Readiness/liveness/startup probes phản ánh đúng trạng thái ứng dụng.
- [ ] Pod không giữ dữ liệu bền vững duy nhất trong writable layer.

### Scheduling và availability

- [ ] Node selector/affinity/taint/toleration có chủ đích.
- [ ] Topology spread/anti-affinity phù hợp miền lỗi và capacity.
- [ ] PodDisruptionBudget không chặn bảo trì ngoài ý muốn.
- [ ] Drain và node replacement đã được thử.
- [ ] HPA và node autoscaler có metric, headroom và giới hạn rõ.

### Network và storage

- [ ] CNI/Service dataplane hoạt động và có monitoring.
- [ ] Ứng dụng dùng Service DNS thay vì hardcode Pod IP.
- [ ] NetworkPolicy phù hợp luồng traffic.
- [ ] PVC/storage class có topology và access mode đúng.
- [ ] CSI attach/mount và restore đã được kiểm thử.

### Vận hành và bảo mật

- [ ] Có quy trình điều tra Pending, CrashLoopBackOff, OOMKilled và NotReady.
- [ ] Có log, metrics, events và tracing tập trung.
- [ ] RBAC, service account và workload identity theo least privilege.
- [ ] Image được version hóa và quét lỗ hổng.
- [ ] Node OS, runtime và Kubernetes được vá theo lịch.
- [ ] Backup control plane/data theo trách nhiệm và kiến trúc thực tế.

## 19. Tự kiểm tra

1. Node, Pod và container khác nhau như thế nào về vai trò và vòng đời?
2. Vì sao scheduler gán Pod vào node nhưng không trực tiếp tạo container?
3. kube-apiserver, etcd, scheduler và controller manager đảm nhiệm những phần việc nào?
4. kubelet phối hợp với container runtime như thế nào để chạy Pod?
5. CNI, kube-proxy/dataplane và CSI giải quyết những loại tài nguyên nào?
6. Vì sao một Pod yêu cầu 20 CPU có thể Pending dù tổng cluster còn hơn 20 CPU cộng dồn?
7. Phân biệt Capacity, Allocatable, Requests, Limits và Actual Usage.
8. CPU limit và memory limit có thể ảnh hưởng container theo cách nào?
9. Vì sao Pod IP không nên được dùng như endpoint bền vững?
10. Khi node bị NotReady, Deployment và scheduler phối hợp ra sao để tạo Pod thay thế?
11. PDB bảo vệ loại gián đoạn nào và không bảo vệ loại sự cố nào?
12. Hãy phân tích một Pod Pending do Insufficient memory và đề xuất cách xác minh trước khi tăng node pool.

Kubernetes tách quyết định điều phối khỏi nơi thực thi workload. Control plane lưu và điều khiển trạng thái mong muốn; scheduler chọn node; worker node cung cấp CPU, RAM, network và storage; kubelet cùng runtime biến PodSpec thành container đang chạy. Khi hiểu ranh giới này và đo đúng Capacity, Allocatable, requests, limits cùng trạng thái Pod/node, đội ngũ có thể lập kế hoạch compute, mở rộng và phục hồi workload có cơ sở hơn.

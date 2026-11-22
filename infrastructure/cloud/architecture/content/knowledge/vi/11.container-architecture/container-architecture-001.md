# Phân vai cụm, node, workload và dịch vụ trong nền tảng container

## 1. Nhìn nền tảng container như một hệ thống nhiều lớp

Container giúp đóng gói ứng dụng cùng các thành phần cần thiết để chạy trong môi trường nhất quán. Nhưng khi đưa ứng dụng lên cloud, việc chạy được một container mới chỉ là điểm đầu. Nền tảng còn phải quyết định container chạy trên máy nào, ai giám sát vòng đời của nó, workload tìm thấy nhau ra sao, dữ liệu tồn tại qua lần khởi động lại thế nào và hệ thống phục hồi khi node hoặc vùng sẵn sàng gặp sự cố ra sao.

Một nền tảng container thường có nhiều cấp trách nhiệm:

- **Cluster (cụm):** miền quản trị và lập lịch workload, cung cấp API và tài nguyên dùng chung.
- **Control plane:** điều khiển trạng thái mong muốn, lưu cấu hình và đưa ra quyết định lập lịch.
- **Node:** máy tính tham gia cluster, cung cấp CPU, RAM, lưu trữ và mạng để chạy workload.
- **Workload:** đơn vị ứng dụng được khai báo để nền tảng tạo, thay thế và duy trì, ví dụ Deployment, StatefulSet, Job hoặc DaemonSet trong Kubernetes.
- **Container / Pod:** môi trường thực thi; trong Kubernetes, Pod là đơn vị nhỏ nhất được scheduler đặt lên node.
- **Service:** abstraction cung cấp địa chỉ truy cập ổn định cho một nhóm backend hoặc công bố ứng dụng ra ngoài cluster.

Các thành phần trên có mối quan hệ nhưng không đồng nghĩa. **Cluster không phải một máy chủ lớn; node không phải một ứng dụng; Pod không phải Service; Service cũng không phải tiến trình chạy container.** Phân vai đúng giúp kiến trúc sư chọn compute, networking, storage, scaling và mô hình triển khai trên cloud với trách nhiệm rõ ràng.

Trong module **CLOUD_ARCHITECTURE**, mục tiêu là thiết kế ứng dụng cloud từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai. Khi chọn nền tảng container, cần cân bằng **độ tin cậy, bảo mật, khả năng mở rộng, chi phí và khả năng vận hành**, đồng thời đánh giá các đánh đổi theo tư duy Well-Architected.

Sau bài học, bạn có thể:

- Mô tả vai trò và ranh giới giữa cluster, control plane, node, workload, Pod, container và Service.
- Theo dõi đường đi từ khai báo workload đến lúc container được lập lịch và nhận traffic.
- Hiểu scheduler, kubelet, container runtime, service discovery, storage và network ở mức kiến trúc.
- Chọn loại workload phù hợp với ứng dụng stateless, stateful, batch hoặc tác vụ chạy trên mọi node.
- Thiết kế ranh giới bảo mật, quota, autoscaling, health check, triển khai và phục hồi.
- Xác định cách quan sát và kiểm tra nền tảng trong tình huống tải cao hoặc node lỗi.

## 2. Bản đồ thành phần và trách nhiệm

~~~mermaid
flowchart TB
    User["Người dùng / hệ thống gọi"] --> Entry["Ingress / Gateway / Load Balancer"]
    Entry --> Svc["Service: địa chỉ ổn định"]
    Svc --> Pods["Pods thuộc workload"]
    subgraph Cluster["Cluster container"]
        subgraph CP["Control plane"]
            API["API server"]
            Sched["Scheduler"]
            CM["Controllers"]
            Store[("State store")]
        end
        subgraph Nodes["Worker nodes"]
            N1["Node A: kubelet + runtime"]
            N2["Node B: kubelet + runtime"]
            N1 --> P1["Pod A"]
            N2 --> P2["Pod B"]
        end
        API <--> Store
        Sched --> API
        CM --> API
        API --> N1
        API --> N2
    end
    Pods --> P1
    Pods --> P2
~~~

Sơ đồ là mô hình khái niệm theo Kubernetes. Nền tảng container managed có thể ẩn hoặc thay thế một số thành phần control plane, state store và node management. Ranh giới logic vẫn hữu ích để biết ai chịu trách nhiệm khi triển khai, lập lịch, cấp mạng hoặc xử lý sự cố.

| Thành phần | Trách nhiệm chính | Câu hỏi kiến trúc |
| --- | --- | --- |
| Cluster | Miền quản trị workload, cấu hình và tài nguyên dùng chung | Một cluster phục vụ một môi trường hay nhiều nhóm ứng dụng? |
| Control plane | Điều phối trạng thái, API, scheduling và controller | Ai vận hành, sao lưu, nâng cấp và bảo vệ control plane? |
| Node | Cung cấp tài nguyên thực thi workload | Node pool nào phù hợp CPU, RAM, GPU và độ tin cậy? |
| Workload controller | Duy trì số lượng và trạng thái Pod theo khai báo | Ứng dụng cần rollout, scale, state hay chạy theo lịch? |
| Pod | Đơn vị scheduling gồm một hoặc nhiều container | Container nào cần chung network namespace, volume và vòng đời? |
| Container | Thực thi image ứng dụng hoặc helper | Image có an toàn, tái lập và được quét không? |
| Service | Cung cấp endpoint ổn định cho backend được chọn | Ai được gọi, qua port nào và traffic phân phối ra sao? |
| Namespace | Nhóm tài nguyên và phạm vi policy | Cần ownership, quota, RBAC và network policy thế nào? |
| Persistent Volume | Cấp lưu trữ bền vững cho workload | Dữ liệu tồn tại, backup, restore và di chuyển ra sao? |

## 3. Cluster: miền quản trị và lập lịch

**Cluster** là tập hợp control plane và các node được quản lý như một nền tảng thống nhất. Với Kubernetes, cluster cung cấp API để khai báo tài nguyên và duy trì trạng thái mong muốn. Ứng dụng thường không cần biết Pod nằm trên node nào; nó khai báo tài nguyên, policy và yêu cầu scheduling, sau đó nền tảng thực hiện.

### 3.1. Cluster chịu trách nhiệm điều gì?

- **API và trạng thái:** Deployment, Service, ConfigMap, Secret, policy và trạng thái.
- **Scheduling:** nơi workload có thể được đặt dựa trên tài nguyên và điều kiện node.
- **Networking:** địa chỉ Pod, Service discovery, network policy và kết nối ngoài.
- **Identity và policy:** danh tính người dùng, service account, RBAC, admission policy và quyền.
- **Capacity và isolation:** CPU/RAM, quota, node pool, giới hạn và mức chia sẻ.
- **Operations:** nâng cấp, backup dữ liệu cần thiết, giám sát và ứng phó sự cố.

Cluster không phải ranh giới bảo mật tuyệt đối. Namespace, RBAC và NetworkPolicy hỗ trợ phân chia quyền nhưng không thay thế isolation của cloud account/project, VPC/VNet, node, workload identity và runtime security.

### 3.2. Một cluster hay nhiều cluster?

Quyết định số cluster cần xét môi trường, mức độ tin cậy, yêu cầu tuân thủ, vùng triển khai, blast radius, quyền quản trị và năng lực vận hành.

| Mô hình | Lợi ích | Chi phí / rủi ro |
| --- | --- | --- |
| Một cluster dùng chung | Tận dụng compute, dùng chung platform tooling, giảm chi phí control plane | Tranh chấp tài nguyên, ảnh hưởng chéo, policy phức tạp, phạm vi lỗi lớn |
| Cluster riêng từng môi trường | Tách dev/staging/prod, quyền và thay đổi độc lập | Nhiều cluster cần nâng cấp, quan sát, cấu hình và capacity |
| Cluster riêng theo miền tin cậy | Giảm blast radius, tùy chỉnh policy và lịch vận hành | Tốn tài nguyên, tăng độ phức tạp quản trị và kết nối |
| Nhiều cluster theo region | Đáp ứng địa lý, độ trễ và DR | Đồng bộ config, failover, dữ liệu, DNS và diễn tập |

**Cluster là ranh giới quản trị hữu ích, không phải đơn vị chia nhỏ mặc định cho mọi microservice.** Một ứng dụng nhỏ không cần cluster riêng chỉ vì nó là một dịch vụ; workload có yêu cầu tuân thủ hoặc mức criticality khác biệt có thể cần ranh giới mạnh hơn namespace.

### 3.3. Namespace và ranh giới chia sẻ

Trong Kubernetes, namespace nhóm tài nguyên có tên như Deployment, Pod, Service, Secret và quota:

~~~text
cluster-prod
  namespace: commerce
    deployment: checkout
    service: checkout
    deployment: catalog
  namespace: platform
    deployment: metrics-agent
  namespace: batch
    job: nightly-reconciliation
~~~

Namespace hỗ trợ RBAC, ResourceQuota, LimitRange và một số policy theo phạm vi. Tuy nhiên, nó không tạo kernel riêng cho từng nhóm, không tự cô lập network traffic và không bảo đảm workload khác namespace không đọc được Secret. Cần kết hợp RBAC, Pod Security controls, NetworkPolicy, admission policy, node isolation khi cần, cloud IAM và encryption.

## 4. Control plane: bộ não điều phối

Trong Kubernetes, control plane cung cấp API và các thành phần điều khiển cluster. Ở nền tảng managed, nhà cung cấp thường vận hành phần lớn hoặc toàn bộ control plane; khách hàng vẫn quản lý nhiều khía cạnh của node, workload, identity, network, storage và cấu hình.

| Thành phần | Vai trò | Điều cần hiểu |
| --- | --- | --- |
| kube-apiserver | Cổng API; xác thực, authorization và xử lý request | Công cụ quản trị và controller tương tác qua API |
| etcd | Key-value store giữ trạng thái trong triển khai self-managed | Sẵn sàng, backup, encryption và restore quan trọng |
| kube-scheduler | Chọn node cho Pod chưa được gán | Xét resource requests, constraints, affinity, taints/tolerations |
| kube-controller-manager | Chạy controller đưa trạng thái thực tế về mong muốn | Controller liên tục quan sát và điều chỉnh |
| cloud-controller-manager | Tích hợp một số chức năng với cloud provider | Có thể quản lý node, route và load balancer tùy provider |

Managed Kubernetes có thể giấu etcd và controller bên trong dịch vụ; một số trách nhiệm được thực hiện bởi provider. Khi lập sơ đồ, vẫn nên thể hiện control plane là phần điều phối để phân biệt với năng lực chạy workload trên node.

### 4.1. Khi một khai báo được áp dụng

Giả sử nhóm khai báo Deployment có ba replica:

1. CI/CD gửi manifest tới API server.
2. API server xác thực danh tính, phân quyền, admission và kiểm tra đối tượng.
3. Trạng thái mong muốn được ghi vào state store.
4. Deployment controller tạo hoặc cập nhật ReplicaSet.
5. ReplicaSet controller tạo Pod cho đến khi đủ số lượng.
6. Scheduler tìm node phù hợp và gán Pod.
7. Kubelet nhận Pod specification, yêu cầu runtime tải image và chạy container.
8. Probe, trạng thái container, endpoint và controller cập nhật theo kết quả thực tế.

~~~mermaid
sequenceDiagram
    participant Dev as CI/CD
    participant API as API server
    participant State as State store
    participant Ctrl as Controllers
    participant Sch as Scheduler
    participant K as Kubelet
    participant CR as Container runtime
    Dev->>API: Apply Deployment replicas=3
    API->>State: Validate và lưu desired state
    Ctrl->>API: Tạo ReplicaSet và Pods
    Sch->>API: Chọn node cho Pod
    K->>API: Theo dõi Pod được gán
    K->>CR: Tạo sandbox và chạy container
    CR-->>K: Trạng thái container
    K-->>API: Cập nhật Pod status
~~~

Các controller làm việc theo vòng lặp quan sát và điều chỉnh (*reconciliation loop*). Vì vậy, khai báo thành công không có nghĩa ứng dụng đã sẵn sàng; cần quan sát Pending, ContainerCreating, Running, Ready và event liên quan.

### 4.2. Control plane có quản lý traffic?

Control plane điều phối đối tượng và trạng thái, trong khi traffic ứng dụng thường đi qua data plane: Pod network, Service dataplane, ingress/gateway, load balancer hoặc proxy. Mất quyền truy cập API server có thể ảnh hưởng việc thay đổi và điều phối mới, nhưng workload đang chạy có thể tiếp tục phục vụ tùy thiết kế. Không nên suy luận API server mất kết nối thì mọi container lập tức dừng.

## 5. Node: nơi workload thực sự chạy

**Node** là máy tính tham gia cluster. Trong cloud, node thường là VM hoặc máy vật lý do nhà cung cấp cung cấp; một số nền tảng dùng serverless/container instances để ẩn quản lý node. Node có đặc tính phần cứng: CPU architecture, RAM, disk, GPU, network bandwidth và local ephemeral storage.

| Thành phần trên node | Trách nhiệm |
| --- | --- |
| kubelet | Agent nhận Pod specification, điều phối runtime và báo trạng thái |
| Container runtime | Kéo image, tạo container, quản lý vòng đời; ví dụ containerd |
| CNI plugin | Cung cấp và quản lý mạng cho Pod |
| kube-proxy hoặc dataplane tương đương | Hỗ trợ Service networking; một số CNI thay thế vai trò này |
| CSI node plugin | Gắn, tháo và cung cấp volume cho Pod |
| Node OS / kernel | Cung cấp process isolation, network stack và filesystem |

Dataplane có thể dùng eBPF thay cho kube-proxy; CSI/CNI plugin được cài theo add-on hoặc managed service. Không nên giả định mọi cluster có cùng danh sách daemon.

### 5.1. Phân loại node pool

Node pool là tập node có cấu hình và chính sách mở rộng tương tự:

| Node pool | Workload phù hợp | Rủi ro cần kiểm soát |
| --- | --- | --- |
| General purpose | API, worker nhẹ, service stateless | Tài nguyên chia sẻ, noisy neighbor |
| Memory optimized | Cache, phân tích dữ liệu, ứng dụng giữ nhiều RAM | Chi phí RAM, giới hạn eviction |
| Compute optimized | Xử lý CPU nặng, mã hóa, render | CPU saturation và thời gian chạy |
| GPU / accelerator | ML inference, xử lý hình ảnh, tính toán chuyên dụng | Chi phí, quota, plugin và lịch GPU |
| System / platform | DNS, metrics, ingress, cluster add-on | Thiếu capacity hệ thống làm suy giảm nhiều chức năng |
| Spot / preemptible | Batch có thể retry và workload chịu gián đoạn | Node có thể bị thu hồi; không mặc định cho tác vụ critical |

Node pool không thay thế resource requests/limits, affinity, topology spread và taints/tolerations. Nó nhóm capacity; scheduler vẫn cần yêu cầu workload phù hợp để đặt đúng node.

### 5.2. Node không phải miền lỗi duy nhất

Nhiều node có thể cùng nằm trong một Availability Zone, phụ thuộc một storage backend hoặc một tuyến mạng. Nếu yêu cầu sẵn sàng cao, cần xem xét phân bố node qua zone, số replica, topology spread, PodDisruptionBudget, capacity dự phòng và khả năng ứng dụng chịu lỗi.

## 6. Container, Pod và workload

### 6.1. Container là đơn vị thực thi

Container image là gói bất biến mô tả filesystem và thông tin cần để chạy ứng dụng. Container phổ biến trên Linux chia sẻ kernel host, dùng namespace/cgroup hoặc cơ chế tương đương để cô lập process, mạng và tài nguyên. Container không phải VM đầy đủ với kernel riêng trong mọi trường hợp.

Image nên được build theo quy trình kiểm soát, quét lỗ hổng, pin digest khi cần, chạy bằng user không đặc quyền, hạn chế capability và tránh nhúng secret. Dữ liệu cần tồn tại không nên chỉ lưu trong writable layer của container.

### 6.2. Pod là đơn vị scheduling

Pod chứa một hoặc nhiều container được thiết kế để cùng tồn tại và phối hợp chặt chẽ. Các container trong Pod chia sẻ network namespace (cùng IP và port space) và có thể chia sẻ volume. Scheduler đặt **Pod**, không đặt từng container trong Pod lên node khác nhau.

Các container nên ở chung Pod khi cần lifecycle và locality gần như đồng nhất, ví dụ sidecar proxy, log/metrics helper hoặc init container chuẩn bị tài nguyên trước khi container chính chạy. Không gom nhiều ứng dụng độc lập vào một Pod chỉ để giảm số object vì chúng sẽ scale, rollout và chịu lỗi cùng nhau.

~~~mermaid
flowchart TB
    subgraph Pod["Một Pod: một network namespace"]
        App["Container ứng dụng"]
        Sidecar["Sidecar proxy"]
        Shared[("Shared volume nếu cần")]
        App --- Shared
        Sidecar --- Shared
        App <-->|"localhost"| Sidecar
    end
~~~

### 6.3. Chọn workload controller theo vòng đời

| Workload | Mục đích | Trường hợp điển hình |
| --- | --- | --- |
| Deployment | Duy trì replica Pod stateless, rollout/rollback | REST API, frontend, worker stateless |
| StatefulSet | Pod có identity ổn định và thường gắn persistent storage | Stateful application, database/operator-managed service |
| DaemonSet | Đảm bảo Pod trên mỗi node phù hợp | Log agent, network/security agent, node monitoring |
| Job | Chạy tác vụ đến khi hoàn thành | Batch import, migration một lần, báo cáo |
| CronJob | Tạo Job theo lịch | Tổng hợp báo cáo, cleanup, reconciliation định kỳ |
| ReplicaSet | Giữ số replica Pod; thường được Deployment quản lý | Thường không cần tạo trực tiếp |

StatefulSet không tự làm ứng dụng stateful có HA, backup hoặc consistency. Database trong StatefulSet vẫn cần replication, quorum, storage phù hợp, backup/restore và kế hoạch nâng cấp.

## 7. Service: địa chỉ ổn định cho backend thay đổi

Pod có vòng đời thay đổi: tạo mới, xóa, reschedule, scale và nhận IP khác. **Service** cung cấp abstraction ổn định để client truy cập nhóm backend phù hợp mà không theo dõi từng Pod IP.

| Service type | Cách tiếp cận | Dùng khi |
| --- | --- | --- |
| ClusterIP | Địa chỉ/virtual IP nội bộ cluster | Giao tiếp service-to-service |
| NodePort | Mở port trên địa chỉ node | Một số môi trường/lab hoặc làm thành phần đường load balancer |
| LoadBalancer | Yêu cầu tích hợp load balancer provider | Công bố dịch vụ qua load balancer public hoặc private |
| ExternalName | DNS CNAME đến hostname bên ngoài | Ánh xạ tên; không tạo proxy data path |

Ingress/gateway cung cấp routing L7 như host/path/TLS tùy implementation. **Service không tự cung cấp WAF, authentication hay API authorization** trừ khi có thành phần bổ sung.

### 7.1. Service discovery trong cluster

Client thường gọi DNS name của Service, ví dụ catalog.commerce.svc.cluster.local theo quy tắc DNS cluster mặc định. DNS service discovery trả tên/ClusterIP; dataplane chuyển tới endpoint backend đủ điều kiện.

~~~mermaid
flowchart LR
    Client["Pod checkout"] --> DNS["Cluster DNS"]
    DNS -->|"catalog.commerce.svc"| VIP["Service ClusterIP"]
    VIP --> DP["Service dataplane"]
    DP --> P1["Catalog Pod 1"]
    DP --> P2["Catalog Pod 2"]
    DP --> P3["Catalog Pod 3"]
~~~

Khi Pod chưa Ready, endpoint có thể không được đưa vào nhóm phục vụ tùy cấu hình. Nếu Service không có endpoint, kiểm tra selector, label, readiness và EndpointSlice.

## 8. Scheduling và quản lý tài nguyên

Scheduler chọn node dựa trên nhiều điều kiện. Ứng dụng cần khai báo tài nguyên thay vì để workload chạy không giới hạn và tranh chấp tài nguyên.

### 8.1. Requests và limits

- **CPU request:** lượng CPU scheduler dùng khi đánh giá khả năng đặt Pod và thường là cơ sở bảo đảm tương đối cho scheduling.
- **CPU limit:** giới hạn thời gian CPU container được phép tiêu thụ; vượt quá có thể bị throttling.
- **Memory request:** dùng để lập lịch và đánh giá khả năng cấp phát.
- **Memory limit:** vượt ngưỡng có thể khiến process/container bị OOM killed.

Requests không phải mức sử dụng thực tế và limits không phải năng lực dự phòng miễn phí. Khai báo quá thấp dẫn đến throttling, OOM hoặc node pressure; quá cao làm scheduler không tận dụng capacity và tăng chi phí.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: checkout
  namespace: commerce
spec:
  replicas: 3
  selector:
    matchLabels:
      app: checkout
  template:
    metadata:
      labels:
        app: checkout
    spec:
      containers:
        - name: app
          image: registry.example.com/checkout:1.4.2
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

Các giá trị trên là minh họa; cần đo heap, working set, CPU profile, peak load và startup time. Probe phải phản ánh đúng trạng thái ứng dụng; không gọi dependency chậm trong mọi lần liveness check rồi gây restart dây chuyền.

### 8.2. Scheduler xét điều kiện gì?

- Resource requests so với capacity khả dụng.
- Node selector, node affinity/anti-affinity.
- Taints trên node và tolerations của Pod.
- Topology spread constraints để phân tán replica theo zone/node hoặc miền lỗi.
- Volume topology, GPU hoặc thiết bị đặc thù.
- Policy và scoring khác tùy phiên bản/cluster.

Scheduler không tự hiểu ý nghĩa nghiệp vụ như “hai replica cùng tenant không được ở cùng vùng”. Kiến trúc sư phải diễn đạt ràng buộc thành label, affinity hoặc topology constraint.

### 8.3. Phân tán replica qua zone

Một Deployment có ba replica muốn tránh tập trung cả ba vào cùng zone. Có thể dùng topology spread constraints với label zone do node/provider cung cấp. Các tham số như maxSkew và whenUnsatisfiable phải được chọn cùng capacity thực tế; cấu hình quá chặt có thể làm Pod Pending khi một zone thiếu node.

## 9. Health check và vòng đời workload

Nền tảng cần biết khi nào container đã khởi động, khi nào có thể nhận traffic và khi nào cần được khởi động lại. Kubernetes cung cấp ba loại probe:

| Probe | Câu hỏi | Khi thất bại |
| --- | --- | --- |
| **Startup probe** | Ứng dụng đã hoàn tất khởi động chưa? | Kubelet tiếp tục thử trong ngưỡng cấu hình; vượt ngưỡng thì container bị restart |
| **Readiness probe** | Pod có thể nhận traffic lúc này không? | Pod bị đánh dấu chưa sẵn sàng và thường bị loại khỏi endpoint phục vụ |
| **Liveness probe** | Process còn ở trạng thái cần thiết để tiếp tục chạy không? | Kubelet restart container theo chính sách |

Readiness và liveness không thay thế nhau. Ứng dụng có thể chưa sẵn sàng do warm cache hoặc dependency tạm thời chưa sẵn, nhưng process vẫn hoạt động và không cần restart. Nếu process deadlock, liveness có thể giúp phát hiện và khôi phục.

### 9.1. Tránh health check gây lỗi dây chuyền

- Endpoint readiness nên đo khả năng nhận request theo tiêu chí ứng dụng, tránh gọi toàn bộ dependency đồng bộ mỗi vài giây.
- Liveness không nên phụ thuộc database, queue hoặc dịch vụ bên ngoài nếu outage của dependency có thể làm mọi replica tự restart.
- Với ứng dụng khởi động lâu, dùng startup probe để bảo vệ giai đoạn initialization.
- Chọn initial delay, period, timeout và failure threshold theo số liệu startup và khả năng phục hồi.
- Theo dõi restart count, probe failures và thời gian từ start đến Ready.

### 9.2. Rolling update và rollback

Deployment cho phép thay đổi phiên bản theo chiến lược rollout. Hai tham số quan trọng:

- **maxSurge:** số Pod bổ sung tối đa trong lúc cập nhật so với số replica mong muốn.
- **maxUnavailable:** số Pod có thể không sẵn sàng trong quá trình rollout.

Các giá trị phải phù hợp capacity, startup time và khả năng tương thích phiên bản. Nếu phiên bản mới cần schema database khác, rollback binary không tự rollback migration. Nên thiết kế migration theo kiểu expand-and-contract để phiên bản cũ và mới có thể cùng hoạt động trong giai đoạn chuyển đổi.

## 10. Storage: dữ liệu của workload sống ở đâu?

Container có vòng đời ngắn. Nếu dữ liệu quan trọng chỉ ghi vào writable layer của container, dữ liệu có thể mất khi Pod bị xóa hoặc tạo lại. Cần phân biệt:

- **Ephemeral storage:** dữ liệu tạm trên node/container, phù hợp cache tạm, scratch và file trung gian có thể tái tạo.
- **Persistent Volume (PV):** tài nguyên lưu trữ bền vững được cung cấp cho workload.
- **Persistent Volume Claim (PVC):** yêu cầu của workload về dung lượng và chế độ truy cập.
- **StorageClass:** mô tả loại storage và cách provision volume theo driver/chính sách.
- **CSI (Container Storage Interface):** giao diện tích hợp hệ thống lưu trữ vào cluster.

~~~mermaid
flowchart TB
    Pod["Pod / Stateful workload"] --> PVC["PersistentVolumeClaim"]
    PVC --> SC["StorageClass"]
    SC --> CSI["CSI provisioner / driver"]
    CSI --> PV["Persistent Volume"]
    PV --> Backend["Managed disk / file / block storage"]
~~~

PVC bound thành công không có nghĩa dữ liệu đã được backup hoặc phục hồi theo RPO. Cần kiểm tra performance class, IOPS/throughput, latency, encryption, snapshot, retention, zone affinity, access mode và restore test.

### 10.1. Access mode và topology

Một số storage cung cấp block volume chỉ có thể attach ở một node tại một thời điểm; một số file storage hỗ trợ chia sẻ đồng thời. Ý nghĩa của ReadWriteOnce, ReadOnlyMany, ReadWriteMany hoặc ReadWriteOncePod phụ thuộc khả năng driver và semantics nền tảng. **Không suy ra nhiều Pod đọc/ghi đồng thời an toàn chỉ từ việc khai báo PVC.**

Volume có thể bị ràng buộc vào một zone. Nếu Pod StatefulSet được reschedule sang node ở zone khác, volume attach có thể không thực hiện được hoặc cần cơ chế replication. Thiết kế storage phải xem xét cùng topology node và DR.

### 10.2. Stateless và stateful

| Đặc điểm | Stateless workload | Stateful workload |
| --- | --- | --- |
| Trạng thái | Nằm ngoài container hoặc có thể tái tạo | Duy trì dữ liệu/identity qua lần restart |
| Scaling | Thường có thể tăng replica độc lập | Phụ thuộc replication, partition, quorum và access pattern |
| Controller thường gặp | Deployment | StatefulSet hoặc operator chuyên dụng |
| Lưu trữ | Thường không cần volume bền vững tại Pod | PVC hoặc dịch vụ dữ liệu bên ngoài |
| Phục hồi | Tạo Pod mới từ image/config | Phải khôi phục dữ liệu và trạng thái nhất quán |

StatefulSet không tự biến database thành dịch vụ HA. Database trong container vẫn cần replication, backup, restore, failover, encryption và quản trị dữ liệu. Dùng managed database bên ngoài cluster giúp tách lifecycle compute khỏi dữ liệu, đổi lại cần tính latency, network, chi phí và dependency.

## 11. Networking: từ Pod tới dịch vụ

Khi chọn nền tảng container, cần xác định ba lớp giao tiếp:

1. **Pod-to-Pod:** workload trao đổi dữ liệu giữa Pod cùng node hoặc khác node.
2. **Pod-to-Service:** client gọi địa chỉ ổn định và dataplane phân phối tới endpoint.
3. **North-South traffic:** người dùng hoặc hệ thống ngoài cluster truy cập qua load balancer, ingress hoặc gateway.

### 11.1. CNI và mô hình mạng Pod

Container Network Interface (CNI) là giao diện/plugin tham gia cấu hình kết nối mạng cho workload. CNI có thể cấp IP cho Pod, tạo interface/route, áp dụng policy hoặc tích hợp SDN của cloud.

Một số nền tảng cấp IP Pod từ dải VPC/VNet; nền tảng khác dùng overlay network và encapsulation:

| Mô hình | Ưu điểm | Điểm cần kiểm tra |
| --- | --- | --- |
| Pod IP từ mạng cloud | Tích hợp route và policy VPC/VNet trực tiếp trong một số mô hình | Số IP subnet, giới hạn interface/secondary IP, mở rộng node |
| Overlay network | Tách dải Pod khỏi địa chỉ subnet vật lý, linh hoạt trong một số topology | Encapsulation, MTU, route, observability và hiệu năng |

Không giả định mọi Pod IP có thể truy cập từ on-prem hoặc Internet. Cần kiểm tra route, network policy, firewall, NAT, security group và load balancer.

### 11.2. Service, EndpointSlice và load balancing

Service dùng selector để chọn Pod theo label hoặc có thể dùng endpoint thủ công trong một số tình huống. Kubernetes duy trì EndpointSlice phản ánh backend và điều kiện sẵn sàng. Dataplane như kube-proxy hoặc eBPF-based implementation chuyển tiếp traffic phù hợp.

Nếu Service không nhận traffic, kiểm tra:

1. Selector Service có khớp label Pod không?
2. Pod có Ready không, readiness probe có thất bại không?
3. EndpointSlice có địa chỉ backend không?
4. TargetPort/port/protocol có đúng không?
5. NetworkPolicy, security group, CNI và dataplane có chặn traffic không?
6. Ứng dụng có lắng nghe đúng interface và port không?

### 11.3. North-South traffic

- **LoadBalancer Service:** cấp load balancer theo tích hợp cloud, có thể public hoặc internal tùy provider.
- **Ingress controller:** routing HTTP(S) theo host/path và TLS theo implementation.
- **Gateway API / API gateway:** routing và policy phong phú hơn theo controller/gateway được triển khai.
- **Service mesh:** có thể quản lý traffic east-west, identity service, mTLS và telemetry, nhưng tạo thêm control plane/data plane và chi phí vận hành.

Không phải cluster nào cũng cài Ingress controller mặc định; tài nguyên Ingress không tự tạo khả năng routing nếu không có controller tương ứng.

## 12. Bảo mật workload và ranh giới tenant

Nền tảng container chạy nhiều ứng dụng chung compute nên cần nhìn bảo mật từ image, identity, control plane, node đến network và dữ liệu.

### 12.1. Bảo vệ image và supply chain

- Chỉ dùng registry được quản lý; giới hạn ai được push/pull image.
- Quét lỗ hổng và malware theo quy trình CI/CD; định nghĩa chính sách xử lý finding nghiêm trọng.
- Pin image digest cho production khi cần bảo đảm bất biến; không dựa hoàn toàn vào tag mutable như latest.
- Tạo image tối thiểu, loại bỏ compiler và package không cần ở runtime.
- Ký image/attestation và kiểm tra provenance nếu mức rủi ro yêu cầu.
- Không đưa credential, token hoặc file bí mật vào image layer.

### 12.2. Identity và quyền

- Phân biệt quyền người thao tác cluster (human identity/RBAC) với quyền workload gọi cloud API (workload identity).
- Mỗi workload chỉ có quyền cần thiết; tránh gắn một cloud role rộng cho mọi Pod trên node.
- Dùng identity tích hợp của provider hoặc workload identity federation nếu phù hợp để tránh access key dài hạn.
- Quản lý Secret, mã hóa at rest, rotation và audit. Kubernetes Secret không tự động đồng nghĩa dữ liệu được mã hóa ở mọi lớp.
- Bảo vệ kubeconfig, API endpoint và CI/CD credential; kiểm soát quyền tạo privileged Pod hoặc truy cập host namespace.

### 12.3. Container security context

~~~yaml
apiVersion: v1
kind: Pod
metadata:
  name: secure-example
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 10001
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: app
      image: registry.example.com/app@sha256:REPLACE_WITH_DIGEST
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
~~~

Manifest minh họa nguyên tắc; UID phải phù hợp image, ứng dụng có thể cần thư mục ghi riêng được mount, và policy cluster phải cho phép cấu hình. Tránh privileged mode hoặc hostPath rộng nếu không có nhu cầu được phê duyệt.

### 12.4. Network policy và phân đoạn

Một số CNI cho phép Pod giao tiếp rộng nếu không có NetworkPolicy. Baseline nên xác định ingress/egress theo workload, chỉ cho checkout gọi catalog/payment adapter trên port cần thiết, giới hạn egress ra Internet hoặc metadata endpoint. Cần xác minh plugin thực thi policy; chỉ tạo object NetworkPolicy không bảo đảm mọi nền tảng áp dụng nếu CNI không hỗ trợ.

### 12.5. Isolation giữa tenant

Namespace là công cụ tổ chức, không phải sandbox mạnh cho workload không tin cậy. Với tenant khác nhau về mức độ tin cậy, cân nhắc dedicated node pool, taint/toleration, admission policy nghiêm ngặt, runtime sandbox hoặc cluster riêng. Đánh giá blast radius nếu tenant chiếm tài nguyên, khai thác kernel vulnerability hoặc lấy credential dùng chung.

## 13. Scaling và cân bằng capacity

### 13.1. Horizontal Pod Autoscaler

HPA điều chỉnh số replica của workload dựa trên metrics như CPU, memory hoặc custom/external metrics. Nếu scale theo CPU utilization, requests là một phần quan trọng để tính tỷ lệ sử dụng; thiếu requests khiến hành vi scaling thiếu cơ sở.

HPA chỉ tăng Pod, nhưng **node capacity** phải có khả năng tiếp nhận chúng. Nếu hết tài nguyên, Pod sẽ Pending; cluster autoscaler hoặc node autoscaling có thể bổ sung node nếu được cấu hình và còn quota/capacity cloud.

### 13.2. Ba lớp scaling khác nhau

| Lớp | Thay đổi gì? | Thành phần / cơ chế |
| --- | --- | --- |
| Application replica | Số Pod của workload | HPA hoặc KEDA/custom controller |
| Node capacity | Số lượng hoặc kích thước node | Cluster autoscaler / node pool autoscaling |
| Service/platform capacity | Throughput của database, queue, load balancer, DNS, control plane | Scaling dịch vụ managed, partition hoặc nâng cấp theo giới hạn |

HPA tăng từ 3 lên 30 Pod không có nghĩa hệ thống chịu được tải gấp 10 lần. Database connection pool, rate limit payment API, throughput queue và giới hạn network có thể trở thành bottleneck trước compute.

### 13.3. Scale to zero và workload gián đoạn

Scale to zero có thể tiết kiệm chi phí cho workload không cần phản hồi tức thời, nhưng tăng cold start và độ trễ. Spot/preemptible node có thể giảm giá cho batch nhưng ứng dụng phải xử lý eviction, checkpoint hoặc retry. Tác vụ thanh toán hoặc ghi dữ liệu quan trọng không nên dùng tài nguyên dễ bị thu hồi nếu chưa có cơ chế bảo đảm và phục hồi.

## 14. Triển khai, cập nhật và quản lý cấu hình

### 14.1. Image và configuration tách biệt

Image nên chứa chương trình và dependency đã đóng gói; cấu hình môi trường được truyền qua ConfigMap, Secret hoặc cơ chế phù hợp. Không build image riêng cho dev, staging và production chỉ vì endpoint database khác nhau.

Không đưa secret vào plain ConfigMap hay biến môi trường bị log vô tình. Với thông tin nhạy cảm, dùng Secret được bảo vệ hoặc external secret manager, có rotation và quyền truy cập rõ.

### 14.2. Declarative deployment và GitOps

Manifest khai báo trạng thái mong muốn, được review và áp dụng qua pipeline hoặc GitOps controller. Cách này cho phép xem diff, audit và tái lập môi trường. Tuy nhiên, cần quy định quyền sửa trực tiếp cluster; nếu người vận hành thay đổi thủ công, nguồn cấu hình có thể lệch khỏi Git và bị controller ghi đè.

### 14.3. Deployment strategy

| Chiến lược | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| Rolling update | Thay replica từng phần theo giới hạn surge/unavailable | Phiên bản tương thích đồng thời, triển khai thường xuyên |
| Blue/Green | Duy trì hai môi trường/nhóm phiên bản, chuyển traffic khi sẵn sàng | Cần chuyển tuyến nhanh và có capacity cho hai phiên bản |
| Canary | Phân một phần traffic tới bản mới và tăng dần theo kết quả | Có metrics, routing và rollback đủ tin cậy |
| Recreate | Dừng bản cũ trước khi chạy bản mới | Ứng dụng không hỗ trợ chạy song song hoặc có giới hạn dữ liệu |

Rollback phải tính cả database migration, message schema, external API side effects và dữ liệu đã ghi. Không chỉ nhìn vào việc quay image tag.

## 15. Vận hành, quan sát và phục hồi

### 15.1. Những lớp cần quan sát

| Lớp | Chỉ số và sự kiện quan trọng |
| --- | --- |
| Control plane | API availability/latency, lỗi admission, scheduler backlog, controller errors |
| Node | CPU/memory/disk pressure, inode, network errors, kubelet/runtime health |
| Pod/container | Pending, restart count, OOMKilled, probe failure, image pull error |
| Workload | Replica desired/available, rollout duration, queue depth, request rate và error rate |
| Service/network | EndpointSlice, DNS failures, connection resets, latency, dropped packets |
| Storage | Volume attach/mount errors, latency, IOPS, capacity, backup/restore status |
| Security | Image findings, policy violations, RBAC changes, privileged workload, secret access |

Metrics giúp nhìn xu hướng, logs cho biết sự kiện và traces nối các request qua nhiều service. Cần gắn nhãn và giữ log ở mức đủ điều tra mà không tạo cardinality quá cao hoặc lưu thông tin nhạy cảm không cần thiết.

### 15.2. Runbook cho các tình huống thường gặp

| Triệu chứng | Kiểm tra trước | Hướng điều tra |
| --- | --- | --- |
| Pod Pending | Events, requests, node capacity, taints, PVC | Scheduler constraints, quota, thiếu node hoặc storage topology |
| ImagePullBackOff | Image name/tag/digest, registry access | Secret pull, IAM, network, rate limit và registry availability |
| CrashLoopBackOff | Container logs, exit code, probes | Config/secret, startup, dependency, permission, memory |
| OOMKilled | Memory usage, limit, node pressure | Heap leak, request/limit, batch size, memory profile |
| Service không có backend | Selector, labels, EndpointSlice, readiness | Port mismatch, CNI, policy, ứng dụng không listen |
| Rollout bị treo | Replica availability, events, quota | Probe, image pull, PodDisruptionBudget, capacity hoặc migration |
| PVC Pending / attach lỗi | PVC, PV, StorageClass, CSI events | Quota, access mode, zone mismatch, driver, cloud volume API |
| Node NotReady | Node conditions, kubelet, runtime, network | Disk pressure, certificate, control plane connectivity, host failure |

Không nên xử lý mọi tình huống bằng cách xóa Pod. Controller có thể tạo lại Pod và lặp cùng lỗi, đồng thời xóa dấu hiệu điều tra. Thu thập events/logs và kiểm tra nguyên nhân trước thao tác gây thay đổi.

### 15.3. Nâng cấp cluster và node

Nâng cấp control plane, node OS, kubelet, runtime, CNI/CSI và add-on cần có compatibility matrix. Thực hiện theo cửa sổ thay đổi, kiểm tra API/deprecation, drain node phù hợp, bảo đảm đủ capacity cho workload di chuyển, và có kế hoạch phục hồi. Managed service giảm trách nhiệm vận hành phần control plane nhưng không tự giải quyết compatibility của ứng dụng hoặc add-on.

## 16. Well-Architected và các đánh đổi container

| Góc nhìn | Quyết định cần xem xét | Lợi ích / đánh đổi |
| --- | --- | --- |
| **Operational Excellence / Vận hành** | Managed cluster hay self-managed; GitOps; chuẩn hóa node pool và telemetry | Managed giảm gánh control plane nhưng vẫn cần quản lý workload, node, policy và add-on |
| **Security / Bảo mật** | Cluster isolation, RBAC, workload identity, image signing, network policy | Cô lập chặt hơn giảm blast radius nhưng tăng quy trình, policy và chi phí |
| **Reliability / Độ tin cậy** | Replica, zone spread, PDB, storage, probes và DR | Nhiều replica cần capacity, ứng dụng stateless và backend chịu lỗi |
| **Performance Efficiency / Hiệu quả hiệu năng** | Requests/limits, node family, CNI, sidecar, autoscaling | Tối ưu tài nguyên có thể giảm chi phí nhưng cấu hình sai gây throttling và latency |
| **Cost Optimization / Tối ưu chi phí** | Bin packing, spot node, scale-to-zero, right-sizing | Tiết kiệm compute nhưng tăng rủi ro gián đoạn hoặc cold start |
| **Sustainability / Bền vững** | Giảm tài nguyên nhàn rỗi, image và node pool phù hợp | Ít lãng phí nhưng vẫn phải giữ headroom và dự phòng |

### 16.1. Tư duy chọn managed hay tự vận hành

Managed Kubernetes phù hợp khi doanh nghiệp muốn dùng API và ecosystem Kubernetes nhưng không muốn tự vận hành toàn bộ control plane. Tuy nhiên, đội vẫn phải hiểu node pool, version skew, workload security, CNI/CSI, quota, networking, backup và DR. Serverless container platform có thể ẩn cả node management, nhưng giới hạn về runtime, networking, storage, startup hoặc workload duration cần được đối chiếu.

Self-managed cluster có thể cần khi có kiểm soát đặc thù hoặc môi trường riêng, nhưng đòi hỏi năng lực duy trì control plane, state store, certificate, upgrade, backup, patching và on-call. Chọn mô hình dựa trên tổng chi phí sở hữu và mức kiểm soát cần thiết, không chỉ giá compute.

### 16.2. Các chỉ số để ra quyết định

- **Utilization và saturation:** CPU/memory request so với usage, node pressure, throttling, OOM và queue.
- **Availability:** tỷ lệ Pod Ready, request success, thời gian phục hồi khi mất node/zone.
- **Delivery:** thời gian rollout, tỷ lệ rollout lỗi, thời gian rollback và deployment frequency.
- **Performance:** p95/p99 latency, throughput, network drops, storage latency.
- **Cost:** chi phí trên request/transaction thành công, utilization theo node pool, chi phí idle capacity và logging.
- **Security:** tỷ lệ image đã scan, lỗ hổng nghiêm trọng, workload chạy privileged, policy violation.

Các ngưỡng cần gắn với SLO và hành trình nghiệp vụ. Không tối ưu CPU utilization cao đến mức không còn headroom cho burst hoặc node failure.

## 17. Bài thực hành: thiết kế nền tảng container cho ứng dụng đặt hàng

Một doanh nghiệp triển khai ứng dụng đặt hàng trên cloud. Hệ thống có API checkout, catalog, worker xử lý đơn, batch đối soát mỗi đêm và agent thu thập metrics trên node. PostgreSQL managed nằm ngoài cluster; file hóa đơn nằm trong object storage. Đội có ba môi trường dev, staging, production và cần duy trì khả năng phục vụ khi một node lỗi.

**Yêu cầu bài làm:**

1. Vẽ sơ đồ cluster/control plane/node/workload/Pod/Service, chỉ ra thành phần nào do nhà cung cấp managed vận hành.
2. Chọn controller cho API stateless, worker, batch và node agent; giải thích khi nào dùng Deployment, Job/CronJob và DaemonSet.
3. Đề xuất namespace, RBAC, ResourceQuota, node pool và network policy cho các nhóm workload.
4. Viết manifest Deployment cho checkout gồm resource requests/limits, readiness/liveness hoặc startup probe, replica và Service.
5. Đề xuất topology spread/PDB phù hợp; giải thích cách hệ thống tiếp tục khi một node bị drain hoặc mất zone.
6. Chỉ rõ đường traffic từ Internet tới API, traffic nội bộ giữa checkout và catalog, đường kết nối tới PostgreSQL và object storage.
7. Đề xuất autoscaling cho Pod và node; xác định các bottleneck có thể nằm ở database, queue hoặc provider API.
8. Viết runbook ngắn cho Pod Pending, CrashLoopBackOff và Service không có endpoint.
9. Đưa ra ba chỉ số về reliability, performance và cost, kèm cách kiểm tra sau triển khai.

### Gợi ý đánh giá

Phương án tốt cần phân biệt **đơn vị quản trị** và **đơn vị chạy ứng dụng**, xác định đúng controller theo vòng đời workload, không lưu state quan trọng trong container ephemeral, có endpoint ổn định và kiểm soát tài nguyên. Nó cũng phải chỉ ra được giới hạn của namespace, ý nghĩa thực tế của probe, yêu cầu network/storage và trách nhiệm vận hành trên cloud.

Một lựa chọn khởi đầu có thể dùng cluster managed cho production, node pool riêng cho system và workload, Deployment cho API/worker stateless, CronJob cho batch và DaemonSet cho agent. Đây chỉ là phương án ứng viên; số cluster, zone, replica và policy phải được xác nhận từ SLO, chi phí và năng lực vận hành.

## 18. Checklist thiết kế và đưa workload container vào production

- [ ] Ranh giới cluster, môi trường, owner và trách nhiệm provider/customer đã rõ.
- [ ] Control plane/API endpoint và quyền quản trị được bảo vệ.
- [ ] Node pool phản ánh CPU, memory, GPU, network, storage và miền lỗi của workload.
- [ ] Chọn đúng workload controller; Pod chỉ ghép các container có lifecycle và locality phù hợp.
- [ ] Resource requests/limits được đo và kiểm tra dưới tải.
- [ ] Readiness, liveness và startup probe có mục đích tách biệt và không gây restart dây chuyền.
- [ ] Service selector, port, endpoint và đường công bố ứng dụng được kiểm tra.
- [ ] CNI, routing, DNS, network policy và firewall đáp ứng luồng traffic được phép.
- [ ] Dữ liệu bền vững dùng storage phù hợp; backup, restore, retention và RPO/RTO đã được diễn tập.
- [ ] Image được quản lý, quét, giới hạn quyền, không chứa secret và có quy trình cập nhật.
- [ ] RBAC, workload identity, Pod security, admission và tenant isolation được phê duyệt.
- [ ] HPA/node autoscaling có quota, headroom và chiến lược khi thiếu capacity.
- [ ] Rollout, rollback, database migration và tương thích message schema đã được tính đến.
- [ ] Logs, metrics, traces, alert và runbook bao phủ control plane, node, Pod, Service và storage.
- [ ] Nâng cấp cluster/node/add-on có kế hoạch, kiểm thử và điều kiện rollback.
- [ ] Chi phí control plane, node, storage, network, observability và nhân lực nằm trong tổng chi phí sở hữu.

**Ghi nhớ:** Cluster tạo miền quản trị; control plane điều phối trạng thái; node cung cấp compute; workload khai báo vòng đời; Pod gom container phối hợp chặt; Service tạo địa chỉ ổn định cho backend thay đổi. Khi các vai trò được phân định đúng, nhóm có thể thiết kế compute, networking, storage, scaling và bảo mật trên cloud có chủ đích, đồng thời đánh giá được tác động đến độ tin cậy, chi phí và vận hành theo Well-Architected.

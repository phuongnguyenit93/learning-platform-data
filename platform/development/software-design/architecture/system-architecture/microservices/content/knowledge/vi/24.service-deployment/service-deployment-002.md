# Nhiều thể hiện, nhiều vùng sẵn sàng và phân bố tải trong Microservices

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices → Triển khai dịch vụ.
>
> **Trọng tâm:** Cách dùng nhiều instance cùng phục vụ một API, phân tán chúng trên các Availability Zone (AZ), phân phối traffic tới những instance đủ khỏe và bảo toàn năng lực hoạt động khi Pod, node hoặc cả một AZ gặp sự cố.

## 1. Mục tiêu học tập

Sau khi học, bạn có thể:

1. Phân biệt instance, replica, Pod, node, cluster, AZ và Region; nêu rõ miền lỗi nào được bảo vệ.
2. Thiết kế một service nhiều replica trên nhiều node và nhiều AZ để tránh điểm lỗi đơn.
3. Hiểu đường đi qua DNS, regional load balancer, ingress/gateway, service discovery và cơ chế chọn backend.
4. Chọn giữa round-robin, weighted routing, least connections, least outstanding requests và session affinity theo đặc tính traffic.
5. Thiết kế readiness, liveness, startup probe, graceful shutdown và connection draining.
6. Tính công suất dự phòng theo kịch bản mất một AZ và phân biệt capacity lý thuyết với capacity đáp ứng SLO.
7. Minh họa Deployment, Service, topology spread, PodDisruptionBudget và HPA trong Kubernetes.
8. Nhận diện những điểm lỗi còn lại ở database, broker, cache, identity, config và mạng.
9. Thiết lập dashboard, cảnh báo, kiểm thử failover và runbook vận hành để chứng minh dịch vụ thực sự duy trì khả dụng.

Các con số và cấu hình trong bài là ví dụ. Chúng cần được kiểm nghiệm với tải, cấu trúc phụ thuộc, quota và khả năng của nền tảng thực tế.

## 2. Vì sao một instance không đủ?

Giả sử Order Service chỉ có một tiến trình JVM:

~~~text
Client → API Gateway → Order Service #1 → Order Database
                         │
                         └→ Inventory Service
~~~

Khi tiến trình này crash, bị OOM, restart vì deploy, hoặc máy chủ mất mạng, mọi request phụ thuộc vào nó đều có thể bị lỗi. Chuyển sang ba instance:

~~~text
Client → Load Balancer ─┬→ Order #1
                        ├→ Order #2
                        └→ Order #3
~~~

Nếu #1 ngừng hoạt động, LB có thể loại nó khỏi tập backend khỏe; #2 và #3 tiếp tục nhận request mới. Nhưng nếu cả ba vẫn nằm trên **cùng một node**, node chết có thể làm toàn bộ service ngừng hoạt động. Nếu ba node đều ở **cùng AZ**, mất AZ vẫn ảnh hưởng mọi instance.

Do đó cần phân biệt hai mục tiêu:

- **Scale-out:** tăng năng lực xử lý hoặc thông lượng bằng nhiều replica.
- **High availability:** tránh các replica bị mất cùng lúc và chuyển traffic tới replica còn khỏe khi xảy ra lỗi.

Tăng replica có thể giúp cả hai mục tiêu, nhưng chỉ khi đặt replica hợp lý, bảo vệ phụ thuộc và giữ đủ công suất dự phòng.

## 3. Thuật ngữ và miền lỗi

| Khái niệm | Ý nghĩa | Điều nó không tự bảo đảm |
| --- | --- | --- |
| **Instance** | Một tiến trình/bản chạy của service | Không nhất thiết nằm trên máy riêng |
| **Replica** | Bản sao phục vụ cùng contract, thường triển khai từ cùng image | Không chắc độc lập về node/AZ |
| **Container** | Đơn vị đóng gói và chạy phần mềm | Không đại diện cho một máy riêng |
| **Pod** | Đơn vị scheduling của Kubernetes, gồm một hoặc nhiều container | Có thể chia node với nhiều Pod khác |
| **Node** | VM/máy vật lý chạy workload | Có thể ở cùng AZ với node khác |
| **Availability Zone** | Miền hạ tầng trong một Region được thiết kế có mức cách ly lỗi | Không loại mọi lỗi chung trong region |
| **Region** | Khu vực triển khai rộng hơn, thường có nhiều AZ | Không mặc định có replication sang region khác |
| **Load Balancer** | Thành phần phân phối kết nối/request giữa backend | Không biết nghiệp vụ đã thành công nếu không được instrument |
| **Service discovery** | Cơ chế tìm endpoint hiện khả dụng | Không thay thế health/timeout của request thật |

Sơ đồ các miền lỗi:

~~~text
Region R
├── AZ-A
│   ├── Node A1 ── Order Pod 1
│   └── Node A2 ── Order Pod 2
├── AZ-B
│   ├── Node B1 ── Order Pod 3
│   └── Node B2 ── Order Pod 4
└── AZ-C
    ├── Node C1 ── Order Pod 5
    └── Node C2 ── Order Pod 6
~~~

Lỗi ở Pod 1 chỉ ảnh hưởng một Pod. Node A1 chết làm mất các Pod trên node đó. AZ-A gặp sự cố có thể làm mất toàn bộ node/Pod trong AZ-A. Nếu database hoặc identity provider dùng một endpoint phụ thuộc AZ-A, các Pod ở B/C vẫn có thể không phục vụ được nghiệp vụ.

**Multi-AZ là phương pháp giảm blast radius ở hạ tầng**, không phải lời cam kết mọi lỗi đều độc lập.

## 4. Kiến trúc tham chiếu: nhiều replica trên ba AZ

~~~text
                         Client / Mobile / Web
                                  │
                           DNS / Edge / WAF
                                  │
                          Regional L7 Load Balancer
                                  │
                   ┌──────────────┼──────────────┐
                   │              │              │
                 AZ-A           AZ-B           AZ-C
                   │              │              │
                 Ingress        Ingress        Ingress
                   │              │              │
               Order Pods      Order Pods     Order Pods
                 A1..A4         B1..B4         C1..C4
                   └──────────────┼──────────────┘
                                  │
                         Database / Broker
                         Multi-AZ topology
                                  │
                             Monitoring
~~~

Một request bình thường có thể đi qua các bước:

1. Client tra domain rồi kết nối tới endpoint của LB.
2. LB chấp nhận kết nối hoặc request và chọn upstream.
3. Ingress/Gateway xác thực và định tuyến đến Order.
4. Service discovery cung cấp danh sách Order Pods phù hợp.
5. LB nội bộ hoặc client chọn Pod Ready.
6. Pod thực thi nghiệp vụ, truy cập database và service khác.
7. Hệ thống ghi metric, log, trace ở các ranh giới cần thiết.

Trong trường hợp Pod A1 lỗi, danh sách endpoint được cập nhật và traffic mới có thể chuyển sang các Pod khác. Nếu AZ-A chết, đường vào cần còn backend ở B/C; các dependency có vai trò bắt buộc cũng phải tiếp tục hoặc failover trong ngân sách thời gian.

### 4.1. Cần có bao nhiêu AZ?

Hai AZ có thể phù hợp với một số bài toán và nền tảng, nhưng ba AZ thường thuận tiện để phân bổ công suất, duy trì quorum ở các thành phần nhất định và dự phòng một miền lỗi. Số AZ hợp lý phụ thuộc thiết kế database/broker, quy mô tải, giá và mục tiêu RTO/RPO.

Không được suy ra một cluster broker sẽ còn quorum chỉ vì "có ba AZ"; cần kiểm tra placement và replication thực tế.

## 5. Nhiều replica có thực sự stateless không?

Chạy cùng code trên nhiều instance dễ nhất khi mỗi instance có thể xử lý bất kỳ request hợp lệ nào mà không cần trạng thái chỉ tồn tại ở một tiến trình.

| Trạng thái | Rủi ro nếu chỉ lưu trong Pod | Giải pháp thường gặp |
| --- | --- | --- |
| HTTP session | Chuyển Pod gây logout hoặc mất trạng thái | Stateless token hoặc session store chung |
| Giỏ hàng | Pod chết làm mất giỏ | DB hoặc cache phân tán với TTL và consistency rõ |
| Idempotency key | Retry sang Pod khác tạo giao dịch trùng | Kho lưu bền vững có unique constraint |
| File upload đang dở | Pod bị thay làm mất file | Object storage và resumable upload |
| Job đang chạy | Pod chết khiến job mất hoặc chạy lại trùng | Queue, checkpoint, lease, idempotent job |
| Cron task | Mỗi replica chạy một lần → nhân side effect | Scheduler riêng, leader election hoặc job có khóa |
| Local cache | Pod mới chưa có dữ liệu, tải DB tăng | TTL, warm-up, cache stampede protection |

**Stateless ở tầng HTTP không có nghĩa toàn hệ thống không có state.** State được quản lý ở DB/cache/event store vẫn phải có chiến lược đa AZ và bảo vệ concurrency.

### 5.1. Session affinity không thay thế chia sẻ state

Sticky session đưa client quay lại cùng backend. Nó có thể tăng cache locality nhưng khiến một Pod nhận tải quá lớn và làm người dùng phụ thuộc vào Pod đó. Khi Pod/zone chết, client vẫn phải chuyển sang backend khác, nên trạng thái quan trọng phải có phương án khôi phục.

### 5.2. Không dùng Pod-local lock cho nghiệp vụ toàn hệ thống

Nếu mỗi replica có một biến `synchronized` hay mutex trong memory, chúng chỉ ngăn concurrency trong **một process**. Để tránh hai replica cùng tạo một payment hoặc cùng chạy job đặc quyền, cần constraint/transaction, distributed lease với fencing hoặc cơ chế tương đương.

## 6. Load balancing diễn ra ở nhiều tầng

### 6.1. DNS và global routing

DNS có thể định tuyến client tới một region hoặc endpoint; một số dịch vụ hỗ trợ weighted/failover/latency routing. Tuy nhiên DNS thường có cache ở resolver/client. **TTL không bảo đảm mọi client chuyển sang endpoint mới tức thời**; một số kết nối hiện hữu tiếp tục dùng địa chỉ cũ.

DNS thường giải quyết lựa chọn region/entry point. Health một Pod cụ thể thường được quản lý ở tầng LB/service discovery gần Pod hơn.

### 6.2. L4 Load Balancer

L4 xử lý luồng TCP/UDP theo thông tin kết nối. Nó thích hợp cho giao thức không yêu cầu proxy hiểu HTTP hoặc TLS pass-through. Một số L4 LB cân bằng theo **connection**, khiến ứng dụng có kết nối dài hạn hoặc HTTP/2/gRPC multiplexing phân bố request không đồng đều.

### 6.3. L7 Load Balancer

L7 hiểu request HTTP/gRPC đủ để định tuyến theo host, path, header, version, cân theo trọng số hoặc hỗ trợ canary. Nó có thể đo HTTP status/latency ở ranh giới ingress và quản lý các chính sách timeout/retry phù hợp.

Đổi lại, L7 có thêm chi phí xử lý, cấu hình TLS, security và yêu cầu riêng về tính sẵn sàng của proxy.

### 6.4. Load balancing nội bộ

Order gọi Inventory có thể đi qua Kubernetes Service IP/DNS, client-side balancer, sidecar proxy hoặc service mesh. Những tầng này khác nhau ở cách chọn endpoint, cache danh sách backend, reuse connection, timeout và retry.

~~~text
               ┌── Inventory Pod 1 / AZ-A
Order Pod ─────┼── Inventory Pod 2 / AZ-B
               └── Inventory Pod 3 / AZ-C
~~~

Phải hiểu request được cân bằng ở **tầng nào**. Có thể external traffic chia đều qua ba zone nhưng Order→Inventory vẫn dồn vào một zone vì client connections lâu dài.

## 7. Các thuật toán chọn backend

### 7.1. Round-robin

~~~text
Req 1 → Pod A
Req 2 → Pod B
Req 3 → Pod C
Req 4 → Pod A
~~~

Đơn giản khi các backend tương đương và công việc mỗi request gần nhau. Nhưng số request bằng nhau không có nghĩa CPU/DB cost bằng nhau.

### 7.2. Weighted routing

Ví dụ Canary V2 nhận 10% traffic; V1 nhận 90%. Hoặc một AZ có capacity lớn hơn được gắn trọng số cao hơn. Cần xác định trọng số áp dụng cho **nhóm backend** hay **mỗi endpoint**.

Không sử dụng weighted routing để ép AZ yếu nhận traffic vượt khả năng chỉ để "chia đều".

### 7.3. Least connections

Chọn backend có ít kết nối hiện hoạt. Phù hợp với một số loại long-lived connections; không phản ánh đúng tải nếu mỗi connection HTTP/2 mang số RPC khác nhau.

### 7.4. Least outstanding requests

Chọn backend có ít request đang thực thi. Hữu ích khi duration không đồng đều, nhưng cần proxy có dữ liệu chính xác và cấu hình tránh dao động.

### 7.5. Latency-aware / EWMA

Một số LB ưu tiên backend phản hồi nhanh hơn theo metric đã làm mượt. Cần kiểm tra tác động của outlier, cold cache, noisy neighbor và feedback loop: pod nhanh được gửi nhiều tải có thể trở nên chậm.

### 7.6. Consistent hash hoặc session affinity

Gắn một khóa ổn định vào backend để tăng cache hit/locality. Hữu ích với một số workload nhưng có thể tạo **hot key** hoặc làm mất cân đối. Khi backend chết hoặc danh sách endpoint thay đổi, khóa phải chuyển vị trí an toàn.

**Lựa chọn thực tế:** bắt đầu từ phân phối theo request/connection phù hợp giao thức và đo bằng RPS, in-flight, latency, CPU, pending connections; chỉ thêm affinity/weights khi có bằng chứng về nhu cầu.

## 8. HTTP/2, gRPC và WebSocket làm bài toán phức tạp hơn

Một gRPC client có thể giữ một TCP connection rất lâu, chứa hàng nghìn RPC. Nếu L4 chọn backend chỉ một lần cho connection, mọi RPC đó có thể dồn về cùng Pod.

~~~text
gRPC Client
    │ 1 HTTP/2 connection
    ▼
Inventory Pod A
    ├─ RPC 1
    ├─ RPC 2
    ├─ RPC 3
    └─ RPC 1000
~~~

Có thể cân bằng theo RPC ở L7 hoặc dùng chính sách gRPC client-side load balancing phù hợp. Đừng đánh giá công bằng bằng **số TCP connection** khi mục tiêu là chia đều số RPC hoặc độ nặng công việc.

WebSocket/streaming còn có vấn đề drain và reconnect: kết nối bị mất khi Pod chết không mặc định được chuyển tiếp trạng thái đến Pod khác. Ứng dụng cần protocol resume/reconnect, durable checkpoints hoặc state store khi yêu cầu trải nghiệm liền mạch.

## 9. Readiness, liveness và startup probe

Ba loại health check có ý nghĩa khác nhau:

| Kiểm tra | Câu hỏi | Tác động thường gặp |
| --- | --- | --- |
| Startup | Container đã qua giai đoạn khởi động cần thiết? | Cho phép app chậm startup trước khi liveness xử lý |
| Readiness | Instance có nên nhận request mới? | Không đưa Pod chưa Ready vào tập endpoint phù hợp |
| Liveness | Process đã kẹt ở mức cần restart? | Kubelet có thể restart container |

**Sai lầm nguy hiểm:** liveness kiểm tra toàn bộ dependencies bên ngoài. Khi DB chung outage, tất cả Pod có thể thất bại liveness và restart liên tục, tăng tải lúc hệ thống cần phục hồi.

Readiness có thể phụ thuộc một số điều kiện thiết yếu, nhưng cần phân biệt **dependency bắt buộc** với **tính năng phụ có fallback**. Một cache tham khảo ngừng hoạt động không nhất thiết khiến toàn service NotReady nếu ứng dụng vẫn xử lý đúng contract.

### 9.1. Actuator trong Spring Boot

Với Spring Boot Actuator, endpoint phổ biến là:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Chúng cần được bật và kiểm tra theo phiên bản/config thật. Nếu management server ở port khác HTTP server, endpoint probe còn khỏe chưa chắc đường phục vụ người dùng đã hoạt động. Health check không thay thế request error ratio hoặc user-facing SLO.

### 9.2. Health propagation không tức thời

Pod chuyển NotReady, sau đó controller cập nhật endpoint; kube-proxy, ingress hoặc service mesh tiếp tục đồng bộ. Trong khoảng ngắn, client hoặc kết nối đã tồn tại vẫn có thể gửi request tới Pod. Vì vậy graceful shutdown và timeout/retry có kiểm soát vẫn cần thiết.

## 10. Graceful shutdown và connection draining

Trong rolling update hoặc node drain, Pod đang xử lý request cần thời gian kết thúc:

~~~text
SIGTERM / bắt đầu terminate
      ↓
Đánh dấu không nhận công việc mới
      ↓
Readiness và endpoint list cập nhật
      ↓
LB ngừng điều phối request mới
      ↓
Hoàn tất hoặc chuyển tiếp in-flight work
      ↓
Đóng kết nối/flush state, process thoát
~~~

Các bước có thể xảy ra chồng lấn, tùy controller, LB, app và kết nối hiện hữu. Không coi một lệnh sleep cố định là bằng chứng kết nối đã được drain.

Cần đặt:

- `terminationGracePeriodSeconds` theo thời gian request/job thực tế.
- HTTP server graceful shutdown được cấu hình đúng.
- Cơ chế dừng consumer nhận job mới, ack/nack/requeue theo contract.
- LB draining/connection timeout phù hợp.
- Trạng thái job và idempotency bền vững qua Pod.
- Metric 5xx/connection reset, in-flight requests trong rollout.

**Nếu request có side effect:** process chết sau DB commit nhưng trước response có thể khiến client retry; phải bảo vệ bằng idempotency thay vì giả định request chưa thực thi.

## 11. Tính toán số replica chịu mất một AZ

Giả sử ba AZ và peak demand 1.500 requests/second. Load test cho thấy **một Order Pod xử lý được 300 RPS** ở ngưỡng bắt đầu không còn nhiều headroom. Chính sách vận hành chỉ muốn dùng 70% công suất này sau failover.

### 11.1. Phân bổ 3 Pod mỗi AZ

~~~text
AZ-A: 3 pods
AZ-B: 3 pods
AZ-C: 3 pods
Tổng: 9 pods
Mất AZ-A còn 6 pods
Safe throughput = 6 × 300 × 0,70 = 1.260 RPS
~~~

1.260 RPS nhỏ hơn peak 1.500 RPS. Cấu hình này **thiếu capacity** trong kịch bản AZ failure, nếu không có cơ chế giảm tải hoặc scale đủ nhanh.

### 11.2. Phân bổ 4 Pod mỗi AZ

~~~text
AZ-A: 4 pods
AZ-B: 4 pods
AZ-C: 4 pods
Tổng: 12 pods
Mất AZ-A còn 8 pods
Safe throughput = 8 × 300 × 0,70 = 1.680 RPS
~~~

Theo giả định về tầng ứng dụng, có 180 RPS headroom sau khi một AZ mất. Nhưng nếu DB chỉ phục vụ được 1.100 transactions/second thì hệ thống không thể đảm bảo 1.500 checkout RPS chỉ bằng cách tăng Pod.

### 11.3. Công thức sơ bộ

Với số replica N phân bố tương đối đều trong ba AZ:

~~~text
remaining_replicas ≈ N - ceil(N/3)
safe_capacity ≈ remaining_replicas × capacity_per_replica × target_utilization
~~~

Nếu replica phân bổ **không đều**, phải trừ capacity của AZ lớn nhất thay vì ceil(N/3) theo giả định lý tưởng.

Ví dụ 10 Pod chia A=6, B=2, C=2. Mất A chỉ còn 4 Pod, không thể lấy 10−ceil(10/3)=6 làm năng lực còn lại.

### 11.4. Đơn vị failure cần ghi rõ

“N+1” có thể được dùng với nhiều ý nghĩa. Hãy nói chính xác mục tiêu:

- Chịu mất **một Pod**.
- Chịu mất **một Node**.
- Chịu mất **một AZ**.
- Chịu lỗi **database leader**.
- Chịu mất **một Region**.

Dự phòng một Pod không bằng dự phòng một AZ chứa nhiều Pod và có thể chứa dependency quan trọng.

## 12. Kubernetes: bố trí replica trên nhiều AZ

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 12
  selector:
    matchLabels:
      app: order-service
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 2
      maxUnavailable: 1
  template:
    metadata:
      labels:
        app: order-service
    spec:
      terminationGracePeriodSeconds: 40
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: order-service
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: order-service
      containers:
        - name: order-service
          image: registry.example.org/order-service:1.4.2
          ports:
            - name: http
              containerPort: 8080
          resources:
            requests:
              cpu: "300m"
              memory: "512Mi"
            limits:
              memory: "1Gi"
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            failureThreshold: 24
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
~~~

Điểm cần chú ý:

1. `replicas: 12` là desired count; Pod có thể Pending, NotReady hoặc đang terminate.
2. `topologySpreadConstraints` theo AZ giúp giới hạn chênh lệch khi scheduler có các lựa chọn hợp lệ.
3. `maxSkew: 1` có ý nghĩa theo logic của scheduler; phải có worker nodes với label `topology.kubernetes.io/zone`.
4. `DoNotSchedule` giữ yêu cầu cứng nhưng có thể khiến Pod mới Pending khi một AZ unavailable.
5. `ScheduleAnyway` theo hostname ưu tiên trải đều node mà không chặn scheduling trong nhiều tình huống thiếu chỗ.
6. CPU/memory requests và giới hạn phải dựa trên profile thực; memory limit thấp có thể gây OOM.
7. Đường health phụ thuộc Actuator/config thật, không mặc định tồn tại trên mọi app.
8. Không suy diễn từ yaml rằng chắc chắn luôn có 4 Pod Ready ở mỗi AZ; còn phụ thuộc node capacity, taints, quotas, affinity khác và lỗi hạ tầng.

### 12.1. Tác dụng phụ của hard topology constraint

Khi AZ-A chết, scheduler có thể không được phép đặt Pod thay thế vào AZ-B/C do ràng buộc cân bằng chặt. Hệ thống còn 8 Pod Ready nhưng 4 Pod thay thế cứ Pending. Đây không nhất thiết là lỗi Kubernetes; có thể là hệ quả đúng của chính sách mà bạn chọn.

Cần quyết định trước:

- Cho phép temporary imbalance trong incident?
- Duy trì hard spread và dự trữ capacity đủ để phục vụ bằng các replica còn lại?
- Có cơ chế nới constraints qua quy trình vận hành có kiểm soát?
- Khi AZ quay lại, có tái cân bằng mà không làm gián đoạn dịch vụ không?

Một cấu hình bảo vệ phân tán rất chặt có thể gây khó cho tự động hồi phục trong sự cố thiếu AZ.

### 12.2. Kubernetes Service

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: order-service
spec:
  type: ClusterIP
  selector:
    app: order-service
  ports:
    - name: http
      port: 80
      targetPort: http
~~~

Service cung cấp endpoint nội bộ để client gọi Order; danh sách endpoint chịu ảnh hưởng từ labels và readiness. Nó không tự bảo đảm global routing, TLS policy, hay transaction nghiệp vụ thành công.

### 12.3. PodDisruptionBudget

~~~yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: order-service-pdb
spec:
  minAvailable: 8
  selector:
    matchLabels:
      app: order-service
~~~

PDB kiểm soát **voluntary disruptions** thông qua eviction API trong những tình huống được hỗ trợ, ví dụ maintenance/node drain. Nó không thể chặn AZ failure, node crash, kill cưỡng bức hoặc lỗi application. PDB quá chặt còn có thể làm bảo trì cluster không thể tiến hành.

### 12.4. Rolling update

`maxSurge: 2` cho phép thêm một số Pod mới trong khi rollout; `maxUnavailable: 1` giới hạn số Pod không khả dụng theo ngữ nghĩa Deployment. Phải có node headroom cho surge, và readiness phải thực sự phản ánh app đã sẵn sàng trước khi thay Pod cũ.

## 13. Autoscaling và headroom

Horizontal Pod Autoscaler (HPA) điều chỉnh số replica theo CPU/custom metrics. Ví dụ:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: order-service-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: order-service
  minReplicas: 12
  maxReplicas: 36
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
~~~

Đây là cấu hình minh họa. HPA CPU dựa trên usage liên quan resource requests, vì thế requests đặt sai dẫn đến quyết định scale sai. Một service chỉ chờ database có CPU thấp nhưng throughput đã bão hòa; CPU HPA không giải quyết được bottleneck đó.

### 13.1. Scale Pod khác với scale Node

Khi HPA tăng desired replicas từ 12 lên 24:

- Cần worker nodes đủ CPU/memory.
- Cần địa chỉ IP và quota cho Pod.
- Cần registry/image pull và thời gian boot.
- Cần topology constraints có thể thỏa.
- Cần Pod mới Ready trước khi nhận traffic.

Nếu node pool không đủ, Pod Pending và thực tế capacity không tăng. Cluster Autoscaler hoặc node provisioner có thể thêm node nhưng mất thời gian; không nên dựa vào nó như cơ chế duy nhất để bảo vệ peak traffic ngay khi một AZ chết.

### 13.2. Autoscaling theo queue

Với worker bất đồng bộ, có thể scale theo queue depth/lag/oldest message age bằng custom metrics hoặc KEDA. Nhưng nếu downstream DB chỉ cho phép 100 connections, tăng worker từ 10 lên 1000 có thể làm tình hình tệ hơn.

Nên ghép scale với concurrency limit, dependency capacity, DLQ và deadline của công việc.

### 13.3. Dự phòng nóng và dự phòng có thể scale

Có hai cách suy nghĩ:

- **Provisioned headroom:** đủ replica và hạ tầng chạy sẵn để chịu sự cố ngay.
- **Elastic recovery:** dựa vào autoscaler và bổ sung node sau khi lỗi xảy ra.

Thiết kế cần nêu thời gian chờ có thể chấp nhận. Với API thanh toán cần latency chặt, dự phòng nóng thường quan trọng hơn. Với batch không cần hoàn thành tức thì, chờ scale có thể chấp nhận được.

## 14. Dữ liệu và dependency có thể là điểm lỗi chung

Một triển khai Order ba AZ vẫn phụ thuộc:

~~~text
Order replicas in AZ-A/B/C
        │
        ├─ Order Database
        ├─ Inventory Service / Inventory DB
        ├─ Payment Provider
        ├─ Cache / Session Store
        ├─ Message Broker
        ├─ Identity Provider / JWKS
        └─ DNS / Secrets / Config
~~~

### 14.1. Database primary

Nhiều database có một writer chính và standby ở AZ khác. Khi AZ chứa writer chết, hệ thống phải phát hiện lỗi, bầu/chuyển writer, cập nhật đường kết nối và xử lý transaction dang dở.

Cần xác định:

- RTO dự kiến khi writer failover.
- Replication đồng bộ/bất đồng bộ.
- RPO, khả năng mất các write gần nhất.
- Cách tránh split-brain hoặc hai writer cùng chấp nhận ghi.
- Connection pool có reconnect/re-resolve endpoint không.
- Retry thao tác ghi có idempotent không.
- Read replicas có replication lag bao nhiêu.

**Multi-AZ database không đồng nghĩa zero downtime hay RPO=0** trong mọi cấu hình.

### 14.2. Message broker

Broker Kafka/RabbitMQ hay hệ tương đương cần replica/partition/quorum phân bố phù hợp. Nếu tất cả replicas của một partition nằm cùng AZ, mất AZ có thể khiến dữ liệu hoặc availability của partition bị ảnh hưởng dù cluster có nhiều node.

Kiểm tra producer ack, consumer offset, retry, leader election, rebalance, lag, duplicate delivery và DLQ. Một consumer chết sau xử lý nhưng trước ack có thể làm event được phát lại, nên downstream handler cần idempotency.

### 14.3. Cache và session

Khi một AZ mất, cache trong AZ đó có thể biến mất. Những request quay sang B/C làm cache miss tăng và dồn truy vấn xuống DB.

Cần rate limit, cache warming, chống cache stampede, TTL/invalidation và thiết kế state không lệ thuộc vào một Pod.

### 14.4. Secrets, IAM, certificate và config

Tất cả Pod cùng dùng một signing key, JWKS endpoint, cloud IAM policy hoặc config release. Credential hết hạn hoặc cấu hình sai có thể khiến toàn bộ zone lỗi cùng lúc. Đó là **correlated failure** chứ không phải lỗi AZ độc lập.

Cơ chế key rotation, workload identity, config rollout và security verification phải xét đủ các replica và zone.

## 15. Zone-local routing và cross-zone load balancing

Một số hạ tầng ưu tiên gọi nội bộ trong cùng AZ để giảm latency và chi phí truyền dữ liệu giữa AZ.

~~~text
Order AZ-A → Inventory AZ-A (ưu tiên)
    │
    └── Inventory AZ-A không khỏe → Inventory AZ-B/C (fallback)
~~~

**Ưu điểm của locality:** ít network hop, có thể tiết kiệm data transfer và giảm p95 trong điều kiện thường.

**Rủi ro:** nếu bắt buộc local endpoint mà không có fallback, mất Inventory AZ-A làm Order AZ-A thất bại dù Inventory B/C còn khỏe.

Cross-zone LB cho phép sử dụng capacity ở các AZ khác, nhưng cần kiểm tra chi phí, latency, policy của nhà cung cấp và tác động lên downstream. Không mặc định tính năng được bật hay miễn phí.

### 15.1. Đo phân bố thật

Hãy theo dõi RPS, outstanding requests, latency và utilization theo **Pod và zone**. Nếu ba AZ đều có bốn Pod mà AZ-A nhận 80% RPS, có thể do session affinity, clients lâu dài, routing policy hoặc backend eligibility khác nhau.

### 15.2. Quay lại zone sau outage

Khi AZ phục hồi, các Pod có thể khởi động cùng lúc, cold cache và đồng loạt mở DB connections. Không nhất thiết chuyển toàn bộ traffic trở lại ngay. Có thể ramp up từng bước theo readiness, observed latency, error ratio và capacity của DB/broker.

## 16. Retry storm và cascading failure khi AZ mất

Giả sử 1.000 RPS đang được chia đều cho ba AZ. Một AZ chết, các request được đưa tới hai AZ còn lại. Đồng thời, upstream tự retry hai lần các request timeout. Khi đó lưu lượng downstream có thể **tăng đáng kể** đúng lúc capacity ít đi.

Các cơ chế bảo vệ:

1. **Timeout:** giới hạn thời gian chờ connect và response theo user deadline.
2. **Retry có giới hạn:** chỉ cho lỗi có thể thoáng qua và thao tác an toàn/idempotent.
3. **Exponential backoff với jitter:** tránh tất cả client retry cùng lúc.
4. **Retry budget:** giới hạn tỷ lệ retry so với requests gốc.
5. **Circuit Breaker:** từ chối nhanh dependency suy giảm và kiểm tra hồi phục có giới hạn.
6. **Bulkhead:** giới hạn concurrency/pool theo dependency.
7. **Rate limit và load shedding:** từ chối có kiểm soát khi quá tải, thay vì làm toàn hệ thống timeout.
8. **Backpressure:** phát tín hiệu để upstream giảm tốc hoặc đợi, nếu giao thức cho phép.
9. **Idempotency key:** tránh tạo giao dịch trùng khi client chuyển từ Pod A sang Pod B.

**Không retry vô hạn** các request 429/503 hoặc lệnh có side effect chưa được idempotent. Một HTTP timeout không chứng minh phía server chưa thực hiện giao dịch.

### 16.1. Circuit Breaker theo instance

Mỗi Pod có thể có breaker state riêng. Khi một AZ phục hồi, nhiều Pod có thể cùng chuyển từ OPEN sang HALF_OPEN, tổng số probe tới dependency lớn hơn dự kiến. Cần giới hạn concurrency ở nhiều tầng hoặc điều phối phục hồi để tránh thundering herd.

## 17. Rolling deployment, canary và blue-green qua nhiều AZ

### 17.1. Rolling update

Quy trình:

~~~text
V1 chạy ở ba AZ
    ↓
Tạo một số Pod V2
    ↓
V2 qua startup/readiness
    ↓
Đưa V2 vào endpoint set
    ↓
Drain và thay Pod V1
    ↓
Lặp lại cho đến khi V2 đủ replica
~~~

Trong lúc deploy, cần giữ đủ capacity và quan sát:

- Available replicas, NotReady/Pending pods.
- 5xx, latency p95/p99.
- Retry/connection resets trong thời gian drain.
- V1 và V2 có tương thích API/event/schema database không.
- DB/broker có chịu được số connection tạm tăng khi maxSurge không.

### 17.2. Canary

Route phần nhỏ traffic tới V2 để so sánh error/latency với V1, sau đó tăng dần hoặc rollback theo tiêu chí được xác định. Canary chỉ thử trên một AZ có thể bỏ sót lỗi cấu hình/endpoint ở AZ khác; cần cân nhắc độ đại diện và số mẫu.

### 17.3. Blue-green

Chạy hai tập backend, chuyển traffic theo kế hoạch. Nó giúp rollback routing tương đối nhanh nhưng rollback application **không nhất thiết khôi phục được dữ liệu** nếu migration hoặc side effect của V2 không tương thích.

### 17.4. Tương thích phiên bản đồng thời

Trong rolling/canary, có thể tồn tại request:

~~~text
Gateway V2 → Order V1 → Inventory V2
Gateway V1 → Order V2 → Inventory V1
~~~

Vì vậy contract API, event schema, token và database migration nên hỗ trợ giai đoạn mixed versions. Chỉ thử happy path trên phiên bản mới riêng lẻ là chưa đủ.

## 18. Dashboard đa AZ cần quan sát những gì?

Nhóm metric đề xuất:

| Nhóm | Metric | Mục đích |
| --- | --- | --- |
| Traffic | RPS theo AZ/Pod/route | Biết backend đang nhận bao nhiêu tải |
| Errors | 5xx, timeout, rejected, business failure | Đo tác động đến client |
| Latency | p50/p95/p99 ở edge và service | Nhìn tail tăng khi failover |
| Saturation | CPU throttling, active threads, DB pool pending | Biết còn headroom không |
| Placement | Desired/Ready/Available, Pods per AZ/node | Nhận diện phân bố không đúng |
| Routing | Healthy endpoints, connection counts, cross-zone traffic | Biết LB có chuyển request đúng |
| Scaling | HPA desired/current, Pending reason, node provisioning | Biết recovery bị chặn ở đâu |
| Data | DB writer availability, replication lag | Theo dõi dữ liệu và failover |
| Event | Broker quorum, consumer lag, DLQ | Theo dõi xử lý bất đồng bộ |
| Resilience | Retry attempts, circuit state, fallback count | Nhìn request amplification và suy giảm |

### 18.1. Query PromQL minh họa

Nếu Micrometer/Prometheus xuất `http_server_requests_seconds_count` và pipeline đã thêm label `availability_zone`:

~~~promql
sum by (availability_zone) (
  rate(http_server_requests_seconds_count{
    job="order-service"
  }[5m])
)
~~~

Tỷ lệ HTTP 5xx theo zone:

~~~promql
sum by (availability_zone) (
  rate(http_server_requests_seconds_count{
    job="order-service",
    status=~"5.."
  }[5m])
)
/
clamp_min(
  sum by (availability_zone) (
    rate(http_server_requests_seconds_count{
      job="order-service"
    }[5m])
  ),
  1e-9
)
~~~

Truy vấn theo Pod:

~~~promql
sum by (pod) (
  rate(http_server_requests_seconds_count{
    job="order-service"
  }[5m])
)
~~~

Tên metric/labels thực tế thay đổi theo stack. Nếu không có `availability_zone`, cần enrich từ Pod→Node→Zone metadata thay vì đoán. Đừng dùng user ID, request ID, session hoặc URL có dữ liệu cá nhân làm metric label.

### 18.2. Nhìn SLI phía người dùng

Bốn Pod Ready ở hai zone không chứng minh checkout thành công. Cần SLI, ví dụ:

> Tỷ lệ checkout requests hợp lệ được xác nhận đúng nghiệp vụ trong 2 giây, đo tại edge hoặc business boundary.

Theo dõi error-budget burn, không chỉ process uptime. Một readiness endpoint xanh trong lúc Payment unavailable có thể vẫn đi kèm nhiều checkout thất bại.

### 18.3. Cảnh báo

- Một AZ không còn Pod Ready hoặc không có request thành công.
- Available capacity thấp hơn ngưỡng chịu một AZ failure.
- Pod Pending vì topology/resource/quota, autoscaler không scale được.
- 5xx và p99 tăng sau deployment hoặc zone failure.
- DB writer failover quá chậm, replication lag vượt chính sách.
- Retry attempts/fallback tăng bất thường.
- Queue age/DLQ tăng dù HTTP vẫn trả 202.
- Cross-zone latency/cost vượt mục tiêu.
- Một zone tiếp nhận phần lớn request dù capacity tương đương.

Alert tốt có owner, độ ảnh hưởng, điều kiện kích hoạt và link runbook.

## 19. RTO, RPO và multi-AZ khác multi-region

- **RTO:** thời gian mục tiêu để khôi phục chức năng.
- **RPO:** mức độ mất dữ liệu theo thời gian chấp nhận được.

Nếu database writer ở AZ-A mất, 10 giây failover có thể ảnh hưởng RTO. Nếu standby bất đồng bộ chưa nhận những giao dịch cuối, có thể ảnh hưởng RPO. Các Pod ứng dụng còn chạy không giải quyết được hai vấn đề này.

**Multi-AZ** giảm rủi ro lỗi ở một AZ. **Multi-region** đòi hỏi thêm global routing, replication liên region, conflict resolution, data residency, IAM, certificate và failback. Không quảng bá ba AZ trong một Region là chống được mọi outage cấp Region.

Ngay cả khi nhiều AZ được coi có phần lớn lỗi hạ tầng độc lập, **configuration bug** hoặc database corruption có thể lan cùng lúc. Không nhân các tỷ lệ availability của AZ một cách máy móc để suy ra uptime tổng.

## 20. Runbook: một Pod lỗi

Khi một Pod Order mất readiness hoặc crash:

1. Kiểm tra Pod/Node status, reason như OOMKilled, CrashLoopBackOff, failure probe.
2. Quan sát số backend Ready và metric user-facing.
3. Xác nhận LB không tiếp tục route request mới tới Pod hỏng sau propagation.
4. Kiểm tra Pod thay thế có được schedule và Ready không.
5. Kiểm tra in-flight request/job có side effect bị mất, retry hoặc xử lý trùng.
6. Xem CPU/memory/GC, exception và recent deploy để tìm root cause.
7. Sau thay đổi, theo dõi error ratio/p95 và thời gian ổn định, không chỉ số Pod Running.

Đừng tăng replica như biện pháp duy nhất khi mọi Pod chết vì chung một bug hoặc secret hết hạn.

## 21. Runbook: một AZ ngừng hoạt động

### 21.1. Xác nhận sự cố

Những tín hiệu thường xuất hiện:

- Nhiều node cùng AZ chuyển NotReady.
- Endpoint count hoặc Ready Pods của zone giảm.
- Request/connection reset, timeout tăng.
- Hai zone còn lại nhận nhiều traffic.
- HPA/cluster autoscaler tăng desired nhưng Pod có thể Pending.
- Database/broker phải chuyển primary/leader hoặc xảy ra lag.

### 21.2. Các bước hành động

**Bước 1 — Đo user impact:** request success ratio, p95/p99, số request lỗi, queue age và thời điểm bắt đầu.

**Bước 2 — Kiểm tra ingress/LB:** có backend khỏe ở zone khác không? Target health, route weights, kết nối còn cũ và drain behavior.

**Bước 3 — Kiểm tra công suất:** Pod Ready × năng lực đạt SLO; CPU/threads/DB pool/queue. Có phải load shedding để bảo vệ phần còn lại?

**Bước 4 — Kiểm tra stateful services:** DB writer, replication, broker quorum, cache/session, secrets/identity. Không ép ghi nếu có nguy cơ split-brain.

**Bước 5 — Hạn chế amplification:** quan sát retry count, in-flight, circuit-open, 429/503. Điều chỉnh retry/rate limit/concurrency theo runbook đã xác định.

**Bước 6 — Khôi phục capacity:** scale lên ở zone còn khỏe nếu quota/node/constraints cho phép; không chỉ tăng desired replica.

**Bước 7 — Kiểm tra hoạt động:** end-to-end checkout, idempotency, job backlog, DB lag, error budget.

**Bước 8 — Khi AZ trở lại:** nạp dần traffic, cho cache ấm, tránh đồng loạt reconnect DB và rebalance broker không kiểm soát.

**Bước 9 — Ghi nhận sự cố:** timeline, RTO/RPO thực tế, mất năng lực bao nhiêu, quy trình nào hoạt động/chưa hoạt động.

### 21.3. Không tự sửa constraint một cách mù quáng

Nếu `DoNotSchedule` chặn Pod mới do AZ không còn, phải biết quy trình có cho phép nới policy trong sự cố hay không. Nới constraint có thể tập trung mọi Pod vào một node hoặc gây thiếu IP/CPU. Đó là quyết định vận hành cần dựa trên capacity, không là sửa cấu hình mặc định.

## 22. Kiểm thử khả năng chịu lỗi và phân bố tải

Một thiết kế HA cần bằng chứng từ test có kiểm soát, không chỉ sơ đồ ba AZ.

| Ca thử | Kích thích | Điều cần chứng minh |
| --- | --- | --- |
| Pod crash | Kill một Pod có traffic | Endpoint được loại, Pod khác phục vụ |
| Node drain | Drain node qua eviction | PDB và graceful shutdown giữ đủ khả dụng |
| Readiness fail | Làm một Pod NotReady | Request mới không tiếp tục dồn vào backend lỗi sau propagation |
| Rolling update | Deploy V2 khi đang tải | Không cắt giảm capacity quá mức, mixed version tương thích |
| Traffic burst | Tăng RPS đến peak | p95/5xx và saturation vẫn đạt mục tiêu |
| AZ failure | Cô lập AZ-A trong môi trường test | AZ-B/C có đủ capacity và routing |
| DB failover | Làm writer primary unavailable | RTO/RPO và application reconnect đúng |
| Broker failure | Làm một node/leader lỗi | Quorum/consumer có behavior theo contract |
| Long-lived stream | Dừng Pod có gRPC/WebSocket | Client reconnect/resume đúng |
| Cross-zone loss | Chặn kết nối nội bộ cùng AZ hoặc liên AZ | Fallback routing không làm lan lỗi |
| Retry amplification | Downstream trả 503/timeout | Retry có giới hạn và không vượt capacity |
| Zone recovery | Cho AZ-A quay lại | Traffic tăng dần, không tạo thundering herd |

### 22.1. Kịch bản đo bằng load test

Ví dụ với peak 1.500 RPS và 12 Pod qua ba AZ:

1. Duy trì 1.500 RPS trong một khoảng đủ để ổn định; ghi RPS, 5xx, p95/p99, CPU/pool.
2. Cô lập AZ-A theo cơ chế thử nghiệm an toàn.
3. Đo thời gian endpoint AZ-A bị loại khỏi LB và số request mất trong giai đoạn đó.
4. Theo dõi tám Pod còn lại có xử lý 1.500 RPS trong SLO không.
5. Kiểm tra DB/broker/cache dưới tải chuyển vùng.
6. Phục hồi AZ-A và theo dõi cache warm-up, số connection và việc tái phân bố.
7. So sánh với mục tiêu error budget và RTO/RPO, ghi lại chênh lệch.

Không tuyên bố đạt "chịu được mất AZ" chỉ từ vài request thành công hoặc một lần kiểm tra health xanh.

### 22.2. Tránh test làm ảnh hưởng môi trường khác

Fault injection nên chạy ở môi trường đã được cho phép, có giới hạn blast radius, khả năng dừng và giám sát. Không kill node hoặc cô lập network ngoài phạm vi test. Trong CI có thể dùng các nhóm backend giả lập AZ; thử nghiệm hạ tầng thật cần quy trình vận hành riêng.

## 23. Bài tập suy luận

### Bài A — Tính thiếu công suất

9 Pod chia đều ba AZ. Mỗi Pod có năng lực an toàn 200 RPS. Peak demand 1.000 RPS.

**Hỏi:** mất một AZ còn phục vụ bao nhiêu?  
**Đáp án:** 6 Pod × 200 = **1.200 RPS**. Theo giả định vẫn đủ tầng ứng dụng, nhưng cần kiểm chứng DB/ingress và latency khi failover.

### Bài B — Lệch phân bố

10 Pod phân bố A=6, B=2, C=2; mỗi Pod phục vụ an toàn 200 RPS. Peak 1.000 RPS.

**Hỏi:** mất AZ-A còn bao nhiêu?  
**Đáp án:** 4 Pod × 200 = **800 RPS**; thiếu 200 RPS. Vì vậy tổng 10 Pod không đủ thông tin nếu không biết placement.

### Bài C — HPA tăng nhưng không có Pod Ready

HPA muốn 20 replicas; chỉ 12 Pod Ready, số còn lại Pending với lý do topology constraint không thỏa.

**Hỏi:** tăng maxReplicas lên 40 có giải quyết không?  
**Đáp án:** không. Cần kiểm tra node capacity, zone availability, spread constraint, taints, quota và node autoscaling.

### Bài D — L4 và gRPC

Một L4 LB giữ 10 connections trên mỗi backend, nhưng một backend nhận 75% RPC.

**Hỏi:** tại sao?  
**Đáp án:** RPC multiplex trên connection HTTP/2. Số connection bằng nhau chưa là số request bằng nhau; xem L7/gRPC balancing và đo in-flight RPC.

### Bài E — Sticky session

Giỏ hàng lưu trong memory của Pod A. Khi AZ-A chết, user được route sang Pod B và mất giỏ.

**Hỏi:** cần sửa ở đâu?  
**Đáp án:** state quan trọng phải được lưu/reconstruct ở kho dùng chung có durability phù hợp, hoặc thiết kế stateless; session affinity không thay thế failover.

### Bài F — Retry trùng giao dịch

Client gửi POST /orders; Pod A commit DB nhưng mất kết nối trước response. Client retry qua Pod B.

**Hỏi:** cần kiểm thử gì?  
**Đáp án:** idempotency key được lưu chung, unique/transaction constraint và response nhất quán khi retry; cần kiểm tra concurrent requests và trạng thái chưa xác định.

### Bài G — Multi-AZ app nhưng database fail

Order có Pod ở ba AZ; DB primary chỉ ở AZ-A và failover mất 40 giây.

**Hỏi:** sự cố này cho thấy điều gì?  
**Đáp án:** app replicas có thể còn khỏe, nhưng data plane chưa thể ghi. Phải đặt RTO/RPO, kiểm tra DB failover và connection recovery; tăng Pod không sửa được database writer.

### Bài H — AZ trở lại gây lỗi lần hai

Các Pod AZ-A cùng Ready; hệ thống route 40% traffic về đó. Cache cold khiến DB connection pool bão hòa.

**Hỏi:** nên thay đổi gì?  
**Đáp án:** readiness phù hợp warm-up, ramp-up traffic, chống cache stampede, giới hạn concurrency và quan sát DB/latency trong giai đoạn quay lại.

## 24. Checklist trước production

### Phân bố và năng lực

- [ ] Xác định miền lỗi cần chịu: Pod, node, AZ hay region.
- [ ] Worker nodes/replicas thực sự phân bố trên các AZ đã chọn.
- [ ] Không để phần lớn Pod cùng node hoặc cùng một AZ ngoài ý muốn.
- [ ] Tính capacity sau khi mất AZ có nhiều Pod/capacity nhất.
- [ ] Có headroom và cơ chế giảm tải nếu scale chưa kịp.
- [ ] Quota IP/CPU/memory/node và registry đủ cho rollout/failover.
- [ ] LB có health, routing và draining phù hợp protocol.
- [ ] Kiểm tra cross-zone routing/fallback và chi phí/latency.

### Ứng dụng

- [ ] Mỗi replica có thể xử lý request mà không phụ thuộc state memory của replica khác.
- [ ] Idempotency/transaction ngăn side effect trùng khi chuyển Pod.
- [ ] Readiness, liveness, startup có mục đích và cấu hình đúng.
- [ ] Graceful shutdown hoàn tất/requeue công việc đang xử lý.
- [ ] Rolling/canary deployment có rollback theo SLI.
- [ ] HTTP/2/gRPC/WebSocket có load balancing/reconnect phù hợp.
- [ ] Retry/timeout/Circuit Breaker/Bulkhead không tạo tải lan truyền.

### Dependency

- [ ] Database có topology, writer failover và RTO/RPO đã thử nghiệm.
- [ ] Broker có replication/quorum, consumer retry và idempotency.
- [ ] Cache/session có phương án khi mất zone/cold start.
- [ ] IAM/secrets/DNS/config không tạo single point of failure chưa được nhận diện.
- [ ] Downstream quota/capacity chịu được lưu lượng sau failover.

### Quan sát và chứng minh

- [ ] Dashboard Traffic/Errors/Latency/Saturation theo Pod và zone.
- [ ] Có Ready/Available, pending reason, endpoint count và autoscaling metrics.
- [ ] Theo dõi DB writer, lag, queue age, retry amplification và connection drain.
- [ ] SLI từ request nghiệp vụ, không chỉ từ health endpoint.
- [ ] Đã kiểm thử mất Pod, drain node, mất AZ, DB/broker failover.
- [ ] Đã xác minh dữ liệu không mất/trùng ngoài contract khi retry.
- [ ] Có runbook cho sự cố và quay lại AZ, có owner và tiêu chí hoàn tất.

## 25. Kết luận

Triển khai **nhiều thể hiện** giúp service mở rộng và bớt phụ thuộc vào một process. Phân bố trên **nhiều Availability Zone** giảm rủi ro hỏng đồng thời do node/zone, còn **load balancing** đưa request tới backend hiện khả dụng. Những thành phần này phải đi cùng nhau: **placement đúng, readiness/draining đúng, trạng thái được quản lý bền vững, dependency có khả năng failover và đủ capacity sau khi mất miền lỗi lớn nhất**.

Một hệ thống chỉ thật sự được xem là có khả năng chịu mất AZ khi đã thử trong tải đại diện, đo thời gian chuyển tuyến, tỷ lệ request nghiệp vụ thành công, latency đuôi, bão hòa tài nguyên và tính nhất quán của các thao tác ghi. Số Pod Running hay sơ đồ ba AZ chỉ là điều kiện thiết kế ban đầu; **kết quả vận hành và bằng chứng kiểm thử** mới xác nhận mục tiêu sẵn sàng.

# Định danh dịch vụ logic và xác định địa chỉ thể hiện chạy trong Microservices

## Mục tiêu học tập

Trong Microservices, một ứng dụng không nên phụ thuộc cứng vào địa chỉ IP hay hostname của từng tiến trình đang chạy. Service Inventory có thể được chạy thành 3 replica hôm nay, 8 replica vào giờ cao điểm, bị tái khởi động khi gặp lỗi và được triển khai qua nhiều phiên bản. Order vẫn cần gọi đúng **năng lực Inventory** mà không phải sửa code hoặc cấu hình mỗi khi một instance xuất hiện, biến mất hoặc đổi địa chỉ.

Bài học trả lời hai câu hỏi khác nhau:

1. **Định danh dịch vụ logic:** Khi nói “Inventory”, “Payment” hoặc “Catalog”, client đang tham chiếu tới **dịch vụ/năng lực nào** bằng một tên ổn định?
2. **Xác định địa chỉ thể hiện chạy (instance endpoint resolution):** Ở thời điểm gửi request, làm sao ánh xạ tên ổn định đó thành một **địa chỉ/đường kết nối cụ thể** của tiến trình, Pod, VM hoặc proxy hiện đang phục vụ?

Hai khái niệm liên quan nhưng không thay thế nhau. **Tên logic** biểu đạt *ai được gọi*; **địa chỉ thể hiện chạy** biểu đạt *kết nối tới đâu ở thời điểm này*. Một dịch vụ logic có thể có nhiều instance; một instance có thể biến mất bất cứ lúc nào. Hệ thống khám phá dịch vụ (service discovery) và định tuyến (routing) đóng vai trò liên kết hai lớp này.

Sau bài học, người học có thể:

- Phân biệt **service name/service ID**, **instance ID**, **endpoint**, **IP:port**, **DNS name**, **API route** và **workload identity**.
- Giải thích lý do không hard-code địa chỉ instance trong mã nguồn hoặc giữa các microservice.
- Mô tả **client-side discovery**, **server-side discovery**, **DNS-based discovery**, **registry-based discovery**, **orchestrator discovery** và **service mesh**.
- Giải thích quá trình **register → health/readiness → publish endpoints → resolve → load balance → deregister**.
- Thiết kế gọi service trong Kubernetes bằng Service DNS, ClusterIP, EndpointSlice và readiness mà không nhầm Service với Pod.
- Nhận diện các tình huống khó: stale DNS, registry lỗi, instance không còn ready, connection pool giữ kết nối cũ, rollout, autoscaling, multi-zone, multi-cluster và route sai phiên bản.
- Phân biệt **khám phá địa chỉ** với **xác thực danh tính service**: có địa chỉ không đồng nghĩa endpoint đáng tin.
- Áp dụng timeout, retry, circuit breaker, outlier detection, observability và kiểm thử khả năng phục hồi khi danh sách endpoint thay đổi.

**Bối cảnh:** Nội dung thuộc nhóm **Khám phá và định tuyến** trong kiến trúc Software Design / System Architecture / Microservices. Ví dụ tập trung vào Order gọi Inventory và Payment. Mọi địa chỉ và domain minh họa đều phục vụ giải thích, không phải hệ thống thực tế.

## 1. Vấn đề gốc: một dịch vụ logic, nhiều instance đang chạy

Giả sử Order cần kiểm tra tình trạng tồn kho:

~~~text
Order Service  ── gọi ──>  Inventory Service
~~~

Trong giai đoạn phát triển ban đầu, lập trình viên có thể cấu hình:

~~~text
inventory.url = http://10.20.1.14:8080
~~~

Nhưng địa chỉ 10.20.1.14:8080 có thể là IP của **một tiến trình cụ thể**, chứ không phải định danh ổn định của Inventory. Các sự kiện thường gặp:

- Pod Inventory-1 bị thay bằng Pod Inventory-4 với IP mới.
- Một Auto Scaling Group tạo thêm VM.
- Deployment rolling update chạy đồng thời phiên bản cũ và mới.
- Scheduler chuyển Pod sang node khác.
- Instance không còn healthy; load balancer phải bỏ khỏi danh sách.
- Network topology thay đổi khi chuyển môi trường staging → production.
- Inventory được chạy tại hai vùng khả dụng hoặc hai cluster.
- Ứng dụng mở một kết nối TCP dài tới một instance, trong khi DNS đã cập nhật địa chỉ khác.

Nếu Order biết trực tiếp IP của từng instance, mỗi biến động hạ tầng có thể buộc cập nhật cấu hình, restart client hoặc gây lỗi kết nối. Đó là **coupling với vị trí triển khai**.

Thiết kế phù hợp hơn:

~~~mermaid
flowchart LR
    O["Order Service"] -->|"Tên logic: inventory"| D["Discovery / Service DNS"]
    D --> S["Endpoint set: Inventory"]
    S --> I1["Instance 1\n10.20.1.14:8080"]
    S --> I2["Instance 2\n10.20.1.27:8080"]
    S --> I3["Instance 3\n10.20.1.39:8080"]
~~~

Order dựa vào hợp đồng của Inventory. Cơ chế discovery/routing quyết định instance cụ thể nào phục vụ tại thời điểm request.

**Không có nghĩa Order luôn phải tự truy vấn cả danh sách endpoint.** Với server-side discovery, Order chỉ kết nối một virtual service address hoặc proxy; proxy thực hiện việc chọn backend.

## 2. Từ vựng quan trọng: tên logic, instance, endpoint, route và identity

| Thuật ngữ | Ý nghĩa | Ví dụ minh họa |
|---|---|---|
| **Service logic** | Năng lực/đơn vị có hợp đồng ổn định | inventory |
| **Service name** | Tên client dùng để tìm dịch vụ | inventory.commerce.svc.cluster.local |
| **Instance ID** | Định danh một thể hiện chạy cụ thể trong một vòng đời | inventory-pod-7d9c |
| **Endpoint** | Địa chỉ có thể kết nối, gồm scheme/host/port hoặc thông tin giao thức khác | http://10.20.1.27:8080 |
| **Pod/VM/process** | Môi trường thực thi hiện tại | Pod trên một Kubernetes node |
| **Virtual IP (VIP)** | Địa chỉ ổn định đại diện cho một tập backend | ClusterIP của Kubernetes Service |
| **DNS record** | Bản ghi ánh xạ tên sang địa chỉ hoặc mục tiêu khác | A/AAAA/SRV |
| **API route** | Quy tắc chọn upstream theo host/path/header | /api/inventory → inventory |
| **Registry** | Nguồn dữ liệu hiện thời về instance/endpoint | Eureka/Consul hoặc control plane |
| **Load balancer** | Bộ chọn backend từ một tập hợp endpoint | L4/L7 proxy, client LB |
| **Workload identity** | Danh tính để xác thực/ủy quyền một workload | Chứng thư mTLS gắn tên service |
| **Service account** | Danh tính quyền hạn trong một nền tảng | K8s ServiceAccount |
| **Namespace/environment** | Ngữ cảnh phân biệt tên và policy | commerce/prod |
| **Health/readiness** | Tín hiệu instance có nên nhận traffic không | ready=true, unhealthy=false |

Một service name **không nhất thiết** là tên của một tiến trình, và một URL **không nhất thiết** là danh tính bảo mật. DNS đưa request tới một địa chỉ, nhưng không chứng minh bên ở địa chỉ đó có đúng quyền nhận dữ liệu.

### 2.1. Logical identity khác instance identity

**Logical service identity:** Đơn vị ổn định mà consumer muốn làm việc. Ví dụ “Payment Service” chịu trách nhiệm xử lý giao dịch. Nó có thể tồn tại qua nhiều thế hệ deployment.

**Instance identity:** Một bản sao thực thi cụ thể. Instance có thể có ID, IP và cổng riêng. Khi pod bị hủy rồi tạo lại, instance mới có thể thay ID và IP trong khi service logic vẫn là Payment.

**Version/variant identity:** Một service có thể chạy đồng thời v1 và v2, canary, blue/green hoặc tenant-specific variant. Đó là thuộc tính định tuyến/triển khai, không nhất thiết tạo một bounded context hoàn toàn khác.

### 2.2. Tên logic không nên phụ thuộc location

Tên logic thường hữu ích khi có thể trả lời “đây là dịch vụ gì?” mà không cần biết “đang chạy ở máy nào?”. Ví dụ:

~~~text
inventory
inventory.commerce.svc.cluster.local
payment.internal.example
~~~

Một địa chỉ thể hiện chạy:

~~~text
10.20.1.27:8080
inventory-abc123.specific-node.internal:8080
[2001:db8::27]:8443
~~~

Các tên DNS trên có mức độ ổn định khác nhau tùy hệ thống; chỉ vì một chuỗi là hostname không có nghĩa nó luôn đại diện cho service logic. Có hostname chỉ định đúng một instance.

### 2.3. API name, business capability và network name không phải một

Business capability là “quản lý tồn kho”. Service contract có thể gồm ReserveInventory, ReleaseReservation, GetAvailability. Network name như inventory.commerce.svc.cluster.local chỉ là một cách gọi tới runtime.

Thiết kế boundary nghiệp vụ đúng phải có ownership và contract rõ, kể cả khi network identity ổn định. Ngược lại, DNS service discovery tốt không sửa được việc Order đọc trực tiếp bảng Inventory hoặc cả hai chia sẻ rule nghiệp vụ không rõ chủ.

## 3. Vì sao phải tách service identity khỏi runtime address?

### 3.1. Độ đàn hồi (elasticity)

Khi Inventory scale từ 2 lên 10 replica, Order không nên biết chính xác 8 địa chỉ mới. Discovery phải đưa những endpoint mới **đủ điều kiện nhận traffic** vào tập hợp lựa chọn.

### 3.2. Self-healing

Một instance crash; orchestrator tạo bản sao mới. Discovery/routing cần ngừng chọn instance không khả dụng và cập nhật danh sách. Nếu client giữ địa chỉ cũ trong cache quá lâu, lỗi vẫn xảy ra dù hệ thống đã tạo instance mới.

### 3.3. Rolling deployment

Khi Inventory chuyển từ v1 sang v2, sẽ có giai đoạn nhiều phiên bản cùng tồn tại. Route có thể giữ traffic cho phiên bản đang ready, gửi một phần cho canary hoặc ngừng gửi tới instance đang draining.

### 3.4. Đa môi trường và đa vùng

Tên logic “inventory” có thể cùng ý nghĩa trong dev, staging và production, nhưng endpoint thực khác nhau. Cần scope name bằng environment/namespace/cluster khi cần để tránh kết nối nhầm.

### 3.5. Chính sách định tuyến có thể thay đổi độc lập

Hệ thống có thể chuyển từ round-robin sang least-request, locality-aware, weighted canary hoặc failover. Client không cần thay đổi code nghiệp vụ nếu hợp đồng discovery/routing giữ nguyên.

**Kết luận:** Service identity ổn định giúp giảm coupling với topology. Tuy nhiên nó không loại bỏ network failure, contract coupling hoặc yêu cầu timeout, retry và idempotency.

## 4. Service discovery là quá trình gì?

Một vòng đời đơn giản:

~~~mermaid
sequenceDiagram
    participant I as Inventory Instance
    participant R as Registry / Control plane
    participant O as Order Client
    participant LB as Load Balancer
    I->>R: Register instance + metadata
    I->>R: Health/readiness update
    O->>R: Resolve inventory
    R-->>O: Endpoint set / service address
    O->>LB: Request Inventory operation
    LB->>I: Chọn ready instance
    I-->>LB: Result
    LB-->>O: Result
    Note over R,I: Khi instance dừng: deregister/expire
~~~

Sơ đồ chỉ minh họa trách nhiệm tổng quát. Trong client-side load balancing, Order có thể chọn instance trực tiếp và không có LB trung gian. Trong Kubernetes Service phổ biến, client resolve một tên DNS sang **Service VIP**, còn tầng dataplane chọn Pod backend. Trong service mesh, sidecar/gateway có thể nhận endpoint set từ control plane.

### 4.1. Những thông tin một registry có thể lưu

- Service name, namespace, environment, version;
- Instance ID, IP/hostname, port, protocol;
- Health/readiness/registration state;
- Zone/region/node/cluster;
- Metadata định tuyến như canary tag hoặc capacity class;
- TTL/lease và thời điểm cập nhật;
- Thuộc tính bảo mật/trust domain theo nền tảng.

Không nên dùng registry như một shared business database. Nó mô tả **nơi và cách kết nối**, không có quyền tự quyết quy tắc Order hay Payment.

### 4.2. Register, deregister, lease và heartbeat

Instance có thể đăng ký lúc start, cập nhật heartbeat, sau đó deregister khi shutdown. Khi process crash không kịp deregister, lease/TTL hoặc health check giúp hệ thống phát hiện endpoint không còn hợp lệ.

**Heartbeat còn không đồng nghĩa instance xử lý được request.** Process có thể còn sống nhưng DB connection pool đã đầy. Readiness/serving health cần phản ánh liệu instance nên được đưa traffic mới vào hay không. Sự cân bằng giữa kiểm tra quá nghiêm và quá dễ có ảnh hưởng thực tế tới availability.

### 4.3. Chuyển từ “đã đăng ký” sang “được nhận traffic”

Đúng hơn là:

~~~text
STARTING
  -> RUNNING nhưng chưa READY
  -> READY + được publish như endpoint phục vụ
  -> DRAINING / UNREADY
  -> DEREGISTERED
  -> STOPPED
~~~

Dịch vụ không nên nhận traffic trước khi cần thiết lập các dependency tối thiểu và hoàn tất initialization. Khi shutdown, cần ngừng nhận request mới và có một khoảng grace phù hợp cho in-flight requests. Cơ chế draining không bảo đảm mọi request đã hoàn thành; caller vẫn cần xử lý lỗi.

## 5. Hai kiến trúc phổ biến: client-side và server-side discovery

### 5.1. Client-side discovery

Client chủ động hỏi registry/DNS/endpoint provider, nhận danh sách instance, rồi chọn một endpoint:

~~~mermaid
flowchart LR
    O["Order Client + LB"] -->|"Resolve inventory"| R[("Service Registry")]
    R -->|"I-1, I-2, I-3"| O
    O -->|"Chọn I-2"| I2["Inventory Instance 2"]
~~~

**Ưu điểm:**

- Client có thể chọn backend dựa trên locality, load, circuit state.
- Giảm một tầng proxy trên data path nếu kết nối trực tiếp.
- Có thể tận dụng thông tin động về health và phiên bản endpoint.

**Hạn chế:**

- Mỗi client language/runtime cần discovery và load-balancing logic.
- Client có thể giữ endpoint cache stale.
- Cấu hình, retry, timeout, auth và policy dễ khác nhau giữa SDK.
- Nếu registry lỗi hoặc update đến chậm, client phải có chiến lược last-known-good, expiry và fallback.

Ví dụ về ý tưởng: client SDK lấy endpoint từ registry rồi chọn instance bằng round-robin. Không có nghĩa mọi ứng dụng cần tự viết load balancer.

### 5.2. Server-side discovery

Client gọi một **địa chỉ ổn định của proxy/load balancer/virtual service**. Thành phần trung gian lấy và duy trì danh sách backend, sau đó chọn instance:

~~~mermaid
flowchart LR
    O["Order"] -->|"inventory.service:80"| LB["Service VIP / L4-L7 Proxy"]
    R[("Registry / Endpoints")] --> LB
    LB --> I1["Inventory Pod 1"]
    LB --> I2["Inventory Pod 2"]
    LB --> I3["Inventory Pod 3"]
~~~

**Ưu điểm:**

- Client chỉ cần biết một endpoint logic, code đơn giản.
- Policy chọn backend tập trung hơn.
- Dễ áp dụng TLS termination, observability, rate limiting hoặc routing nhất quán theo nền tảng.

**Hạn chế:**

- Thêm tầng data path hoặc dependency mạng.
- Proxy/LB cần được vận hành, scale và làm HA.
- Chính sách có thể không tận dụng được ngữ cảnh mà chỉ client biết.
- Khi config control plane cập nhật chậm, proxy có thể tiếp tục route tới endpoint không còn phù hợp.

### 5.3. Không có lựa chọn tuyệt đối tốt hơn

| Tiêu chí | Client-side | Server-side |
|---|---|---|
| Ai chọn instance | SDK/client | Proxy, LB hoặc platform dataplane |
| Trách nhiệm của app | Cao hơn | Thường thấp hơn |
| Centralized traffic policy | Cần phối hợp thư viện/cấu hình | Dễ áp dụng ở proxy/platform |
| Extra network hop | Có thể không | Có thể có, tùy tầng |
| Endpoint cache | Client quản lý | Dataplane quản lý |
| Đa ngôn ngữ | Nhiều SDK | Client tương đối đơn giản |
| Kiểm soát health/locality | Client cần tự hiểu | LB hoặc mesh có thể quản lý |
| Ví dụ | SDK gRPC với resolver thích hợp | Kubernetes Service, ingress/gateway |

**Chọn theo hệ sinh thái có sẵn**, yêu cầu SLO, security, mức vận hành và khả năng nhất quán policy. Có thể kết hợp cả hai: client resolve một DNS service rồi một proxy downstream chọn Pod.

## 6. Khám phá bằng DNS

DNS là một trong những cơ chế phổ biến nhất để tách tên khỏi địa chỉ.

### 6.1. Phân biệt DNS record và service contract

Một DNS name có thể trỏ tới IP của một virtual service hoặc nhiều IP cụ thể. DNS không biết contract ReserveInventory, không bảo đảm backend healthy và không thực thi business authorization. Nó chỉ cung cấp bản ghi cần thiết cho bước kết nối.

Các dạng bản ghi:

- **A:** Tên → địa chỉ IPv4.
- **AAAA:** Tên → địa chỉ IPv6.
- **CNAME:** Alias tới tên DNS khác (sau đó tiếp tục resolve).
- **SRV:** Có thể biểu diễn service/port/priority/weight theo quy tắc DNS.
- **TXT:** Metadata văn bản; không mặc nhiên là nguồn endpoint hợp lệ cho client.

### 6.2. Vòng đời DNS resolution

~~~text
Order muốn gọi http://inventory.commerce.svc.cluster.local
   ↓
Resolver tra bản ghi DNS
   ↓
Nhận một địa chỉ VIP hoặc một tập IP
   ↓
Client mở kết nối tới địa chỉ đã chọn
   ↓
Dataplane hoặc client quyết định backend
   ↓
Inventory instance xử lý request
~~~

Tùy môi trường, DNS name có thể được cache trong OS, process, DNS proxy hoặc thư viện HTTP. **Cập nhật DNS không tự động đổi một TCP connection đang mở**. Connection pool có thể giữ kết nối tới endpoint cũ cho đến khi connection bị đóng/timeout/recycled.

### 6.3. TTL và địa chỉ stale

DNS TTL định hướng thời gian cache của bản ghi, nhưng hành vi thực có thể khác theo resolver, runtime và chính sách cache. TTL quá dài làm chậm cập nhật khi instance thay đổi; TTL quá ngắn tăng số truy vấn và tải vào DNS, không bảo đảm client lập tức dùng endpoint mới.

Khi thiết kế:

1. Xác định tầng nào cache DNS và thời gian cache thực tế.
2. Theo dõi **stale address** khi rollout, scale-down và failover.
3. Cấu hình connection pooling và lifetime phù hợp.
4. Retry qua một endpoint khác khi hợp đồng cho phép.
5. Không tin rằng “đổi DNS là mọi connection chuyển ngay”.
6. Đảm bảo việc resolve thất bại có timeout và error handling rõ.

### 6.4. DNS round-robin không phải load balancing hoàn chỉnh

Một tên DNS trả nhiều A records có thể giúp phân tán kết nối. Tuy nhiên DNS resolution và thứ tự record không bảo đảm fairness, kiểm soát load, readiness tức thời hay failover nhanh. Một số client có thể chọn IP đầu tiên, cache lâu hoặc tái sử dụng một connection.

Nếu cần traffic policy nâng cao, có thể dùng client LB, reverse proxy hoặc service mesh. Khi dùng DNS nhiều IP, cần hiểu hành vi client SDK thực tế.

## 7. Kubernetes: Service là lớp logic, Pod là các thể hiện chạy

Một ví dụ rất điển hình: Inventory chạy trong namespace commerce, Deployment tạo một nhóm Pods.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory
  namespace: commerce
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inventory
  template:
    metadata:
      labels:
        app: inventory
    spec:
      containers:
        - name: inventory
          image: example.registry/inventory:v1
          ports:
            - containerPort: 8080
          readinessProbe:
            httpGet:
              path: /health/ready
              port: 8080
            initialDelaySeconds: 2
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: inventory
  namespace: commerce
spec:
  selector:
    app: inventory
  ports:
    - name: http
      port: 80
      targetPort: 8080
  type: ClusterIP
~~~

Đây là cấu hình minh họa. Thực tế có thể cần resource requests/limits, security context, termination behavior và nhiều cấu hình khác.

### 7.1. Tên logic và đường DNS

Service name: **inventory**. Trong namespace commerce, tên đầy đủ theo cấu trúc DNS thường là:

~~~text
inventory.commerce.svc.cluster.local
~~~

Hậu tố cluster domain có thể được tùy biến; cluster.local chỉ là ví dụ phổ biến.

Từ Pod Order trong cùng namespace, client có thể dùng:

~~~text
http://inventory:80
~~~

Từ namespace khác, có thể dùng tên rõ namespace như:

~~~text
http://inventory.commerce.svc.cluster.local:80
~~~

Không nên hard-code Pod IP hoặc giả định mọi môi trường dùng cùng cluster domain. Giá trị runtime có thể được đưa vào configuration, còn service contract giữ ổn định.

### 7.2. Service, ClusterIP và endpoint pods

**Kubernetes Service** là một tài nguyên API mô tả cách truy cập nhóm backend phù hợp selector và cấu hình. Với Service type ClusterIP thông thường, hệ thống cung cấp một virtual IP để client gọi; dataplane (ví dụ kube-proxy hoặc cơ chế thay thế) chuyển traffic tới những endpoints đủ điều kiện.

**Pod IP** là địa chỉ cụ thể của Pod hiện tại. Pod có thể được thay khi deployment, restart, scale hoặc node failure. Không nên cho Order nhớ lâu Pod IP cụ thể.

**EndpointSlice** là tài nguyên mô tả endpoints liên quan đến Service, bao gồm địa chỉ và điều kiện phục vụ. Endpoint availability gắn với readiness và trạng thái terminating theo quy tắc của Kubernetes/platform. Cơ chế cụ thể của dataplane có thể khác nhau theo cluster, nên không suy ra một thuật toán LB duy nhất từ loại Service.

~~~mermaid
flowchart TD
    O["Order Pod"] -->|"DNS: inventory.commerce.svc.cluster.local"| DNS["Cluster DNS"]
    DNS -->|"Service VIP"| VIP["Inventory Service / ClusterIP"]
    VIP --> DP["Cluster Data Plane"]
    EP["EndpointSlice / ready endpoints"] -.-> DP
    DP --> P1["Inventory Pod A"]
    DP --> P2["Inventory Pod B"]
    DP --> P3["Inventory Pod C"]
~~~

### 7.3. Readiness và liveness không giống nhau

**Readiness:** Pod đã sẵn sàng nhận traffic mới hay chưa. Khi readiness fail, Pod thường bị loại khỏi tập endpoint phục vụ mới của Service theo cơ chế tương ứng.

**Liveness:** Container cần được restart khi không còn tiến triển? Probe quá nhạy có thể gây vòng restart và làm availability tệ hơn.

**Startup probe:** Có thể bảo vệ giai đoạn khởi động dài để liveness/readiness không phản ứng sai khi app chưa startup xong.

Tránh readiness phụ thuộc quá chặt vào mọi downstream service: khi database hoặc dependency chung lỗi, tất cả Pod cùng unready có thể khiến Service không còn endpoint để phục vụ cả các chức năng vốn vẫn xử lý được. Readiness nên phản ánh **khả năng phục vụ traffic theo contract**, không phải chỉ sự tồn tại của process hay một bài kiểm tra tổng hợp quá rộng.

### 7.4. Headless Service khác ClusterIP

Một Service cấu hình:

~~~yaml
spec:
  clusterIP: None
~~~

là **headless Service**. Với các cấu hình thích hợp, DNS có thể trả trực tiếp địa chỉ Pod/endpoints thay vì một ClusterIP VIP. Cách dùng thường gặp là các hệ thống cần tự quản lý peer discovery hoặc client-side LB. Hành vi DNS và record cụ thể phụ thuộc Service/Pod/EndpointSlice và cấu hình.

**Headless không có nghĩa không có discovery**; nó chuyển một phần trách nhiệm chọn endpoint sang client hoặc giao thức ứng dụng.

### 7.5. Kubernetes Service không tự quản lý contract API

Service name và selector không thay thế versioning, idempotency, auth hoặc business boundary. Nếu v1 và v2 cùng nằm sau một Service, contract của hai phiên bản cần tương thích với client được route tới, hoặc phải có routing policy rõ.

Tách Service name inventory-v1 và inventory-v2 có thể hữu ích khi cần kiểm soát phiên bản cụ thể, nhưng không nên biến tên version thành lý do buộc mọi consumer cập nhật cùng lúc trong từng deployment.

## 8. Service registry chuyên dụng

Ngoài Kubernetes DNS, hệ thống chạy trên VM, nhiều datacenter hoặc môi trường hỗn hợp có thể sử dụng registry như Consul, Eureka hay một control plane khác. Chức năng thường gặp:

- Dịch vụ đăng ký một hoặc nhiều endpoint;
- Client hoặc LB truy vấn danh sách;
- Health check/heartbeat duy trì thông tin về instance;
- Lease expiry/deregister loại instance không còn hợp lệ;
- Metadata như zone, version, protocol hỗ trợ routing;
- Watch/long poll/notification giúp cập nhật endpoint set theo thời gian.

### 8.1. Self-registration

Mỗi instance tự đăng ký địa chỉ và metadata lúc start:

~~~mermaid
sequenceDiagram
    participant I as Inventory instance
    participant R as Registry
    I->>R: Register(name, instanceId, host, port, zone)
    loop Heartbeat / lease
        I->>R: Renew lease / health
    end
    I->>R: Deregister khi graceful shutdown
~~~

**Ưu:** Instance chủ động cung cấp thông tin chính xác về cổng và metadata.  
**Rủi ro:** Nếu process crash không deregister, phải có lease hoặc health detection. Nếu address được đăng ký nhầm (localhost, IP không route được, NAT sai), client có thể nhận endpoint không kết nối được.

### 8.2. Third-party registration

Orchestrator/platform agent quan sát những instance đang chạy rồi cập nhật registry thay chúng. Application không cần biết registry protocol.

**Ưu:** Giảm thư viện discovery trong app, hợp lý với nền tảng có orchestration.  
**Rủi ro:** Agent/controller có thể cập nhật chậm hoặc có sai lệch giữa trạng thái mong muốn và thực tế. Cần monitoring và reconciliation.

### 8.3. Registry outage

Registry là một **control-plane dependency**, nhưng không phải mọi request đang chạy phải gọi registry trực tiếp. Client/proxy có thể tiếp tục dùng **last-known-good endpoints** trong một thời gian có giới hạn.

Cần định nghĩa:

- Khi registry unreachable, client có dùng cache không và cache được giữ trong bao lâu?
- Khi mọi cached endpoints đều lỗi, có fail fast không?
- Khi registry trả danh sách rỗng, có phân biệt “không có instance” với “truy vấn thất bại” không?
- Khi registry hồi phục, cập nhật endpoint set bằng cách nào?
- Khi registry cung cấp endpoint cũ đã chết, client phát hiện và loại thế nào?
- Làm sao tránh “split brain” thông tin endpoint qua vùng/cluster?

Không nên coi registry là nguồn chân lý tuyệt đối về health thực tế tại thời điểm từng packet đi qua. State của registry, trạng thái dataplane và thực tế process có thể lệch nhau trong một khoảng thời gian.

## 9. Discovery kết hợp load balancing

Discovery trả lời **những endpoint có thể được dùng**. Load balancing trả lời **chọn endpoint nào cho request/connection hiện tại**. Hai bước có thể nằm trong cùng thư viện hoặc khác thành phần.

### Một số chính sách chọn backend

| Chính sách | Ý tưởng | Khi cân nhắc |
|---|---|---|
| Round-robin | Luân phiên backend | Backend tương đương về capacity, request cost |
| Random | Chọn ngẫu nhiên | Đơn giản, có thể phân phối tương đối tốt khi đủ nhiều request |
| Least-connections/least-requests | Ưu tiên backend đang ít request | Request duration biến động; cần metric/ước lượng có ích |
| Weighted | Backend nhận lưu lượng theo trọng số | Canary, máy có capacity khác |
| Locality-aware | Ưu tiên endpoint gần cùng zone/region | Giảm latency và cross-zone traffic, cần failover |
| Consistent hashing | Cố giữ cùng key vào tập endpoint tương đối ổn định | Cache affinity, lưu ý khi membership đổi |
| Priority/failover | Dùng nhóm chính, chuyển sang nhóm dự phòng | Multi-zone/region, kiểm soát rủi ro chuyển vùng |
| Outlier-aware | Tạm loại backend liên tục lỗi | Giảm tác động của instance hỏng, tránh eject quá nhiều |

**Sticky session** đôi khi cần với hệ thống có state cục bộ, nhưng với microservices nên cân nhắc giữ state ở nơi thích hợp thay vì phụ thuộc một process sống mãi. Consistent hashing cũng không thay thế dữ liệu bền vững khi instance thay đổi.

### Cẩn thận với load balancing theo connection

Load balancing tại tầng TCP có thể phân phối **kết nối** chứ không phải từng HTTP request. Một HTTP/2 connection dài có thể mang rất nhiều request và gây phân phối lệch dù có nhiều backend. Khi phân tích throughput, cần biết LB thực sự quyết định ở L4, L7 hay phía client.

## 10. Vòng đời instance: từ startup đến shutdown

### 10.1. Startup

Một tiến trình Inventory startup thường cần:

1. Nạp cấu hình và secret hợp lệ;
2. Mở các listener/network port;
3. Khởi tạo những dependency cần thiết cho traffic cốt lõi;
4. Kiểm tra trạng thái readiness;
5. Được registry/orchestrator đưa vào endpoint set;
6. Bắt đầu nhận traffic.

Không nên chỉ dựa vào “process chạy” hoặc “port 8080 đã mở” nếu application chưa thể xử lý request đúng.

### 10.2. Scale-out

Orchestrator tạo instance mới. Trước khi ready, instance có thể cần warm caches, hoàn thành migration phù hợp hoặc tải model. Sau khi ready, endpoint xuất hiện. LB bắt đầu đưa traffic đến mà không cần Order redeploy.

### 10.3. Scale-in và graceful shutdown

Một kế hoạch giảm replica thường cần:

1. Đánh dấu instance **unready/draining**;
2. Cho control plane/dataplane thời gian cập nhật endpoint set;
3. Ngừng nhận công việc mới khi có thể;
4. Hoàn tất hoặc chuyển giao in-flight requests/jobs theo chính sách;
5. Đóng kết nối và deregister;
6. Cho process kết thúc.

Có thể có một khoảng race: proxy/client đã chọn endpoint trước khi readiness thay đổi, hoặc vẫn giữ connection cũ. Vì vậy cần retry an toàn ở caller và idempotency đối với side effect quan trọng.

### 10.4. Rolling deployment

Trong rollout, v1 và v2 có thể cùng xuất hiện sau một tên logic:

~~~mermaid
sequenceDiagram
    participant O as Order
    participant D as Discovery/Dataplane
    participant V1 as Inventory v1
    participant V2 as Inventory v2
    Note over D,V1: Đầu rollout: v1 ready
    O->>D: ReserveInventory
    D->>V1: Route theo endpoint set
    V1-->>O: Result
    Note over D,V2: v2 startup rồi ready
    O->>D: ReserveInventory
    D->>V2: Chọn v2 khi đủ điều kiện
    V2-->>O: Result
    Note over D,V1: v1 draining/removed
~~~

**Điều kiện quan trọng:** v1/v2 phải đáp ứng những phiên bản contract mà client có thể gọi, hoặc có quy tắc route tách biệt. Discovery chỉ quyết định nơi gửi; nó không khiến hai phiên bản API không tương thích trở nên tương thích.

## 11. Kết hợp tên logic với version và traffic routing

Một service logic có thể có các deployment:

~~~text
inventory-v1
inventory-v2-canary
inventory-v2-stable
~~~

Tùy hệ thống, đây là tên deployment/label hoặc tên upstream route, không nhất thiết là ba service nghiệp vụ độc lập.

Những cách route phổ biến:

- **Weighted canary:** 5% traffic tới v2, còn lại v1;
- **Header-based:** Gửi request gắn một header thử nghiệm tới canary;
- **User/tenant cohort:** Một nhóm người dùng được chỉ định trải nghiệm phiên bản mới;
- **Blue/green:** Chuyển lưu lượng giữa hai nhóm backend theo kế hoạch;
- **Shadow/mirror:** Gửi bản sao request để quan sát, phải tuyệt đối kiểm soát side effect.

### Những giới hạn cần nêu rõ

- Weighted route thường áp dụng theo request hoặc connection tùy proxy/LB; không bảo đảm 5% chính xác trong mẫu rất nhỏ.
- Sticky session có thể làm tỷ trọng quan sát khác tỷ trọng đặt.
- Shadow một lệnh thanh toán có thể nguy hiểm nếu phía nhận thực hiện side effect; chỉ mirror traffic có cơ chế an toàn.
- Endpoint v2 ready chưa có nghĩa đáp ứng business contract mới; cần compatibility tests.
- Rollback code không tự rollback database schema hoặc side effect đã xảy ra.

Không đưa logic “nếu IP 10.20.1.27 thì đó là v2” vào Order. Routing theo version/cohort phải dựa trên metadata và policy được quản lý.

## 12. Service mesh: tách routing policy khỏi ứng dụng

Trong môi trường dùng service mesh, ứng dụng có thể gửi request tới một tên logic, còn **sidecar hoặc node-level proxy/dataplane** đảm nhiệm discovery, mTLS, retry policy, traffic splitting, metrics và một phần fault isolation.

~~~mermaid
flowchart LR
    O["Order App"] --> OP["Outbound Proxy"]
    CP[("Mesh Control Plane")] -. "endpoint discovery + routing policy" .-> OP
    CP -. "policy" .-> IP
    OP --> IP["Inbound Proxy"]
    IP --> I["Inventory App"]
~~~

### Lợi ích có thể có

- Chính sách traffic/security nhất quán giữa nhiều ngôn ngữ.
- Ứng dụng bớt phải tự viết code discovery và load balancing.
- Có điểm đo latency/errors, certificate identity và routing.
- Canary/failover có thể điều chỉnh qua cấu hình nền tảng.

### Chi phí và giới hạn

- Thêm dataplane proxy/resource và độ phức tạp vận hành.
- Policy sai có thể ảnh hưởng diện rộng.
- Retry ở mesh không mặc nhiên an toàn với command có side effect.
- Không phải mesh nào cũng dùng sidecar; có thể dùng ambient/node-level dataplane hoặc gateway.
- Mesh không thay thế trách nhiệm của application về idempotency, consistency và business state.

### Control plane và data plane

**Control plane:** Phân phối service endpoints, policy và configuration.  
**Data plane:** Thực sự chuyển tiếp traffic và chọn backend.

Khi control plane tạm lỗi, dataplane có thể tiếp tục phục vụ với configuration đã nhận, tùy implementation và lifecycle. Nhưng khi cấu hình quá cũ hoặc backend biến động mạnh, stale endpoints vẫn gây lỗi. Không nên khẳng định “mesh không có single point of failure” chỉ vì proxy phân tán; cần đánh giá cả control plane, CA, DNS và gateway.

## 13. Định danh logic cho người dùng và ingress khác service-to-service

Một client ngoài internet thường không gọi Pod IP hoặc inventory.commerce.svc.cluster.local. Thay vào đó:

~~~text
https://api.example.test/orders
           ↓
API Gateway / Ingress
           ↓
Order Service
           ↓
Inventory Service (internal discovery)
~~~

Phân biệt:

- **Public route:** Tên miền và đường dẫn công khai cho client, ví dụ api.example.test/orders.
- **API gateway/ingress:** Điểm vào quản lý auth, routing, rate limits và public contract.
- **Internal service name:** Địa chỉ logic Order dùng để gọi Inventory.
- **Runtime endpoint:** Pod/VM cụ thể đang xử lý.

Một URL public không nhất thiết ánh xạ 1:1 với một microservice. Gateway có thể phục vụ một API tổng hợp từ nhiều backend; nhiều URL có thể route tới cùng một service.

### Không nhầm host/path routing với discovery

Ingress rule “/inventory → Inventory Service” là **quy tắc định tuyến**. Discovery cần cung cấp endpoint phía sau Inventory để route thực sự hoạt động. Hai lớp có thể nằm trong cùng controller nhưng giải quyết bài toán khác nhau.

## 14. Tên dịch vụ và danh tính bảo mật không đồng nghĩa

Một client resolve tên “payment” sang địa chỉ 10.20.1.9. Điều đó **không chứng minh** process ở 10.20.1.9 đúng là Payment được phép nhận thông tin nhạy cảm.

Cần tách:

1. **Naming:** Client muốn gọi service logic nào?
2. **Resolution:** Tên đó được ánh xạ thành endpoint nào?
3. **Authentication:** Endpoint có thể chứng minh danh tính tin cậy không?
4. **Authorization:** Bên gọi có quyền thực hiện operation không?
5. **Policy:** Traffic phải đi qua đâu, được mã hóa và audit thế nào?

### 14.1. DNS không phải là xác thực danh tính

DNS cung cấp ánh xạ tên–địa chỉ; rủi ro gồm cấu hình sai, cache sai, routing giả mạo hoặc DNS/network bị kiểm soát. Cần TLS/mTLS với certificate validation và trust policy phù hợp, nhất là với dữ liệu nhạy cảm.

### 14.2. Workload identity và mTLS

Một mô hình phổ biến là gán identity cho workload, ví dụ một service account hoặc identity được chứng thực. Với mTLS, hai bên có thể xác thực lẫn nhau dựa trên certificate/SAN và trust domain, sau đó chính sách authorization xác định Order có được gọi ReserveInventory hay không.

Ví dụ identity minh họa:

~~~text
spiffe://example.test/ns/commerce/sa/inventory
spiffe://example.test/ns/commerce/sa/order
~~~

Đây là **định danh workload** trong trust domain, khác với network name inventory.commerce.svc.cluster.local. Một workload có thể di chuyển giữa node/IP mà vẫn giữ identity policy; việc cấp/rotation certificate và enforcement phải đúng.

**Cần tránh:** Chỉ kiểm tra “hostname/IP nằm trong private subnet” rồi coi đó là đủ quyền truy cập. Mạng riêng không thay thế xác thực và ủy quyền.

### 14.3. DNS rebinding, SSRF và untrusted destinations

Nếu ứng dụng cho người dùng nhập URL tùy ý rồi server tự resolve và gọi, đó là bề mặt rủi ro **Server-Side Request Forgery (SSRF)**. Nên có allowlist hostname/service identity, kiểm tra scheme/port, kiểm soát redirect, policy egress và đảm bảo địa chỉ sau resolve không vượt phạm vi cho phép.

Không xây dynamic discovery bằng cách tin một chuỗi service name do người dùng gửi trực tiếp khi nó cho phép truy cập service nội bộ không thuộc quyền của họ.

## 15. Multi-zone và multi-region: service logic có thể có nhiều tập endpoints

Trong một vùng, một service có thể chạy nhiều availability zones. Cần cân bằng giữa latency, chi phí cross-zone, vùng lỗi và capacity.

Ví dụ:

~~~text
Inventory logical service
   ├── Region A
   │    ├── Zone A1: 3 instances
   │    └── Zone A2: 2 instances
   └── Region B
        ├── Zone B1: 4 instances
        └── Zone B2: 2 instances
~~~

### 15.1. Locality-aware routing

Ưu tiên endpoint trong zone gần caller có thể giảm latency và chi phí egress. Tuy nhiên nếu zone đó lỗi, routing phải có chính sách chuyển sang zone/region khác khi được cho phép.

### 15.2. Failover không chỉ là chọn IP khác

Khi chuyển Payment sang region khác:

- Dữ liệu giao dịch có sẵn ở nơi dự phòng chưa?
- Có replication lag, conflict hoặc idempotency key dùng chung không?
- Một operation đã commit ở Region A nhưng response bị mất; Region B có biết không?
- Certificate/trust và authorization có tương thích không?
- Có giới hạn pháp lý/vị trí dữ liệu hoặc residency không?

**Discovery cho phép tìm endpoint, không giải quyết nhất quán dữ liệu đa vùng.** Tự động failover một operation có side effect khi chưa đối soát có thể tạo giao dịch trùng.

### 15.3. Multi-cluster

Tên inventory trong Cluster X không mặc nhiên resolve được inventory trong Cluster Y. Cần mô hình federation, cross-cluster DNS, gateways, service mesh đa cluster hoặc một cơ chế định tuyến được thiết kế rõ. Phải quyết định scope service identity theo cluster/region/environment để tránh nhầm môi trường.

## 16. Xử lý lỗi khi endpoint thay đổi

### 16.1. Endpoint cũ đã biến mất

Client có thể gọi IP cũ vì DNS cache hoặc endpoint cache chưa cập nhật. Kết quả có thể là connection refused, timeout hoặc reset. Cần:

- Timeout kết nối và request tổng;
- Refresh/re-resolve endpoints khi có tín hiệu hợp lệ;
- Retry sang endpoint khác với **budget** giới hạn;
- Chỉ retry operation có semantics/idempotency an toàn;
- Không lặp vô hạn trên cùng IP lỗi.

### 16.2. Instance còn sống nhưng không ready

Health registry có thể mới cập nhật, trong khi client vẫn có connection tới instance cũ. App cần xử lý lỗi hợp đồng hoặc tình trạng draining, không cho rằng discovery loại được 100% request lỗi.

### 16.3. Tập endpoints rỗng

Một service logic có thể tạm không có backend healthy. Client nên phản hồi lỗi dependency unavailable hoặc degrade theo contract, thay vì gửi sang một endpoint tùy ý. Nếu có fallback, phải định nghĩa dữ liệu nào được dùng và độ cũ có thể chấp nhận.

### 16.4. Registry/DNS lỗi

Phân biệt:

- Lỗi **resolve**: không thể lấy địa chỉ;
- Lỗi **connect**: có địa chỉ nhưng không kết nối;
- Lỗi **application**: backend nhận và xử lý nhưng trả lỗi;
- Lỗi **ambiguous outcome**: có thể đã commit, response không tới.

Mỗi loại có biện pháp khác nhau. Retry một POST thanh toán không thể được quyết định chỉ từ việc “timeout”. Cần idempotency key và API kiểm tra trạng thái hoặc reconciliation.

### 16.5. Connection pool và long-lived streams

Một HTTP/2 hoặc gRPC connection lâu dài có thể tiếp tục gửi nhiều request tới một backend khi endpoint set đã thay đổi. Các kỹ thuật như max connection lifetime, graceful GOAWAY/draining, pool rotation và load balancing phù hợp có thể giúp chuyển traffic. Đừng chỉ điều chỉnh DNS TTL rồi kỳ vọng tất cả streams tự động đổi backend.

## 17. Timeout, retry và load balancing phải phối hợp

Sự cố một endpoint thường dẫn đến retry. Nhưng retry nhiều tầng có thể biến một lỗi nhỏ thành bão lưu lượng:

~~~text
Client 3 attempts
  × Gateway 3 attempts
  × Service SDK 3 attempts
  = tối đa 27 attempts cho một logical request
~~~

Không nên cho mọi tầng retry độc lập với budget riêng không liên kết. Một phương án tốt cần:

- Overall deadline được truyền và trừ theo thời gian đã qua;
- Retry chỉ khi lỗi thuộc loại transient và operation lặp an toàn;
- Exponential backoff + jitter, số lần và tổng thời gian có giới hạn;
- Chọn endpoint khác sau network failure khi có cơ sở;
- Circuit breaker/outlier detection tránh backend liên tục lỗi;
- Không eject toàn bộ endpoints chỉ vì một shared dependency đang lỗi;
- Quan sát tỷ lệ retries, refused/timeout/reset theo backend và version.

### Retry khác load balancing

Load balancer chọn backend cho **mỗi attempt/request**. Retry tạo **attempt mới** sau thất bại. Hai hành vi có thể kết hợp nhưng không đồng nhất.

### Hedged requests

Một số hệ thống phát thêm request song song nếu attempt đầu chậm, rồi dùng kết quả đến trước. Điều này có thể cải thiện tail latency đối với **query idempotent**, nhưng tăng tải và nguy cơ tạo side effect trùng. Không tự áp dụng hedging cho AuthorizePayment hay ReserveInventory nếu chưa có semantic đặc biệt bảo đảm an toàn.

## 18. Readiness, health và outlier detection

Ba khái niệm khác nhau:

**Liveness:** Process đang sống/tiến triển đủ để không phải restart?

**Readiness:** Instance hiện có đủ điều kiện nhận traffic mới theo contract?

**Outlier detection:** Proxy/client nhận thấy một backend có lỗi hoặc latency bất thường và tạm giảm/chặn traffic tới backend đó.

Có thể có nhiều nguồn tín hiệu. Registry/control plane cung cấp danh sách endpoint; dataplane vẫn có thể dùng local observations để tránh instance đang lỗi mà registry chưa cập nhật.

### Tránh thảm họa eject toàn bộ

Nếu mọi instance Inventory đều trả 503 vì cùng DB đang outage, policy quá nhạy có thể tạm loại hết backends. Điều này không giải quyết gốc vấn đề và có thể làm hồi phục khó hơn. Cần giới hạn tỷ lệ eject, cảnh báo, fallback hợp lý và phân biệt lỗi application 4xx với hỏng backend.

### Health check có cần gọi database?

Một health probe có thể kiểm tra dependency thiết yếu, nhưng nếu mọi Pod đều fail readiness khi DB tạm chậm, service có thể mất toàn bộ endpoints. Có trường hợp đó là hành vi đúng vì không Pod nào phục vụ được; có trường hợp cần **degradation** cho read-only/cached operations. Quyết định phải dựa trên contract và phạm vi request, không dùng một probe chung cho mọi nhu cầu không tương thích.

## 19. Ví dụ Java: gọi service logic thay vì instance IP

### 19.1. HTTP client với base URI ổn định

Ví dụ ứng dụng Java dùng một service DNS name do môi trường cung cấp:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public final class InventoryClient {
    private final URI baseUri;
    private final HttpClient client;

    public InventoryClient(String serviceBaseUrl) {
        this.baseUri = URI.create(serviceBaseUrl);
        this.client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(1))
                .build();
    }

    public String getAvailability(String sku) throws Exception {
        URI target = baseUri.resolve("/inventory/availability?sku=" +
                java.net.URLEncoder.encode(
                        sku, java.nio.charset.StandardCharsets.UTF_8));

        HttpRequest request = HttpRequest.newBuilder(target)
                .GET()
                .timeout(Duration.ofSeconds(2))
                .build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IllegalStateException(
                    "Inventory HTTP status " + response.statusCode());
        }
        return response.body();
    }
}
~~~

Cấu hình khi chạy trong namespace commerce:

~~~text
INVENTORY_BASE_URL=http://inventory.commerce.svc.cluster.local:80
~~~

**Ý chính:** Client không cần biết Pod nào phục vụ. Dịch vụ logic và contract được cấu hình ổn định; tầng DNS/Service/dataplane thực hiện phần ánh xạ đến runtime endpoints.

**Giới hạn của ví dụ:** Đây là minh họa tối thiểu, chưa có structured error handling, auth, tracing, JSON mapping, overall deadline propagation hoặc retry policy. Nếu dùng HTTPS/mTLS cần quản lý certificate/trust và hostname identity đúng. Đừng sao chép vào production mà thiếu các yếu tố này.

### 19.2. Không tạo client mới cho mọi request nếu không cần

Connection pooling và reuse thường giúp giảm latency, TLS handshake và resource cost. Tuy nhiên pool cần có giới hạn, xử lý stale connections và lifecycle phù hợp để rollout không giữ traffic vô thời hạn vào instance đã draining.

### 19.3. Service base URL là cấu hình, không phải hard-coded IP

Một ứng dụng có thể dùng environment config hoặc service catalog:

~~~text
inventory.baseUrl = http://inventory.commerce.svc.cluster.local
payment.baseUrl   = http://payment.commerce.svc.cluster.local
~~~

Khi chuyển từ Kubernetes sang VM hoặc multi-cluster, endpoint logic trong cấu hình có thể thay, trong khi code nghiệp vụ gọi interface InventoryPort/PaymentPort vẫn giữ nguyên.

### 19.4. Port/adapter giúp giấu transport

~~~java
public interface InventoryPort {
    ReservationResult reserve(
            String orderId,
            String sku,
            int quantity,
            String idempotencyKey);
}
~~~

Application service phụ thuộc interface này thay vì một URL instance cụ thể. HTTP/gRPC adapter implement interface và dùng discovery ở tầng vận chuyển. Cách thiết kế hỗ trợ test và giảm coupling transport, nhưng vẫn phải giữ business contract nhất quán.

## 20. Ví dụ ứng dụng có client-side discovery

Giả sử registry trả:

~~~json
{
  "service": "inventory",
  "version": "v2",
  "endpoints": [
    {"instanceId": "inv-a", "host": "10.20.1.11", "port": 8080, "zone": "a", "ready": true},
    {"instanceId": "inv-b", "host": "10.20.1.12", "port": 8080, "zone": "b", "ready": true}
  ]
}
~~~

Một resolver client có thể dùng endpoint set này để chọn backend. Pseudocode:

~~~text
resolve(serviceName):
    endpoints = endpointCache.get(serviceName)
    if endpoints stale:
        endpoints = registry.refresh(serviceName)
    return endpoints filtered by readiness and routing policy

invoke(serviceName, request, deadline):
    candidates = resolve(serviceName)
    selected = loadBalancer.choose(candidates)
    response = transport.call(selected, request, remainingDeadline)
    if transient failure and retry budget remains and operation is safe:
        maybe refresh endpoints
        choose an appropriate next candidate
        retry with same logical operation ID
    return result or documented failure
~~~

Cần tránh những sai lầm:

- Dùng trạng thái ready từ registry như bảo đảm tuyệt đối endpoint đang khỏe.
- Refresh registry trên **mọi request** nếu không có lý do, gây phụ thuộc control plane theo data path.
- Retry với idempotency key mới cho cùng command.
- Cache endpoints vĩnh viễn.
- Tự động gửi lệnh nhạy cảm sang zone/region khác mà chưa xét dữ liệu và policy.
- Tin mọi endpoint được một registry không đáng tin cậy trả về mà không kiểm tra identity.

## 21. Sơ đồ tổng hợp Order gọi Inventory khi scale và rollout

~~~mermaid
sequenceDiagram
    participant O as Order
    participant D as Service DNS
    participant LB as Inventory Service / Proxy
    participant I1 as Inventory v1
    participant I2 as Inventory v2
    participant CP as Orchestrator / Discovery
    CP->>CP: Tạo Inventory v2
    CP->>I2: Readiness probe
    I2-->>CP: READY
    CP->>LB: Endpoint set thêm v2
    O->>D: Resolve inventory
    D-->>O: Service address
    O->>LB: ReserveInventory(orderId)
    LB->>I2: Route request
    I2-->>LB: Reservation result
    LB-->>O: Result
    CP->>I1: Draining
    CP->>LB: Loại I1 khỏi ready endpoints
    Note over O,LB: Client vẫn gọi cùng tên logic
~~~

Bài học:

1. Tên logic inventory không đổi.
2. Instance IDs, IPs và version có thể đổi.
3. Orchestrator/registry cập nhật membership.
4. DNS và dataplane có thể có cơ chế cache/propagation khác nhau.
5. Client cần đối phó lỗi tại thời điểm endpoint biến động.
6. Khi v1/v2 cùng tồn tại, contract compatibility là yêu cầu riêng của discovery.

## 22. Quan sát và chẩn đoán discovery/routing

Nếu Order gọi Inventory thất bại, cần biết vấn đề thuộc lớp nào:

| Lớp | Metric/log gợi ý | Câu hỏi chẩn đoán |
|---|---|---|
| DNS | Resolve success/failure, query latency, TTL/cache behavior | Tên có resolve được không? |
| Registry/control plane | Registered instances, watch lag, lease expiries | Endpoint set có cập nhật kịp không? |
| Service/EndpointSlice | Ready endpoints, endpoint churn | Service có backend ready không? |
| Dataplane/LB | Upstream resets, no healthy upstream, selection distribution | Request có được route tới đúng backend? |
| Network | TCP connect, TLS handshake, packet loss | Đường kết nối có hoạt động không? |
| Application | HTTP/gRPC codes, latency, exceptions | Backend nhận request nhưng xử lý lỗi gì? |
| Version routing | Traffic split, canary errors, contract mismatch | Có route sai phiên bản hoặc cohort? |
| Connection pooling | Active connections, long-lived sessions, stale hosts | Client đang giữ connection cũ? |
| Authorization | mTLS identity, 401/403, policy deny | Có đúng identity và quyền không? |
| Reliability | Retry attempts, circuit state, timeout budget | Chính sách phục hồi có làm tình hình xấu đi? |

### Structured logs minh họa

~~~text
traceId=abc123
callerService=order
targetLogicalService=inventory
resolvedName=inventory.commerce.svc.cluster.local
selectedEndpoint=10.20.1.27:8080
instanceId=inv-b
zone=b
attempt=1
connectLatencyMs=15
httpStatus=503
errorClass=UPSTREAM_UNAVAILABLE
~~~

Trong production, phải giới hạn thông tin nhạy cảm/PII trong logs; endpoint IP và danh tính workload có thể cần chính sách truy cập. Trace service-to-service nên liên kết các span và cho biết tuyến được chọn, nhưng không làm metrics có cardinality quá cao vì gắn instanceId/userId cho mọi time series.

### Hai góc nhìn cần tách

- **Service-level SLO:** Người dùng Order gọi Inventory thành công bao nhiêu phần trăm?
- **Instance-level diagnostics:** Pod nào lỗi và có phải một zone/version cụ thể?

Một service có SLO tốt vẫn có một instance lỗi nhưng đã được failover; một service có mọi Pod chạy vẫn có thể lỗi do DNS/proxy/auth.

## 23. Những anti-pattern thường gặp

**1. Hard-code IP:port của một instance.** Khi scale/restart, client stale. Dùng service name + discovery.

**2. Đồng nhất DNS name với workload identity đáng tin.** DNS trả địa chỉ, không cấp quyền. Dùng TLS/mTLS và authz phù hợp.

**3. Dùng Pod IP hoặc container name ngoài phạm vi lifecycle của nó.** Pod có thể bị thay. Service/VIP/registry là lớp ổn định hơn cho caller.

**4. Giả định DNS TTL thay đổi thì mọi TCP connection chuyển ngay.** Pool/HTTP2/gRPC có thể giữ connection dài; cần quản lý lifecycle và draining.

**5. Trả mọi instance đang running mà không xét readiness.** Có thể route vào instance startup chưa xong hoặc đang drain.

**6. Readiness quá gắn mọi dependency phụ.** Có thể loại hết backend chỉ vì lỗi của tính năng phụ không cần thiết cho tất cả requests.

**7. Chọn endpoint bằng một cache không có expiry.** Registry thay đổi nhưng client vẫn gọi IP chết. Cần refresh, failure detection và giới hạn stale.

**8. Cho client truy vấn registry trực tiếp trên mọi request.** Tăng dependency control-plane và latency; cần cache/watch strategy thích hợp.

**9. Coi registry là bằng chứng instance xử lý request được 100%.** Health signal có race và propagation delay.

**10. Retry mọi request khi một instance lỗi.** Gây side effect trùng cho POST/Payment nếu không có idempotency; đặt budget.

**11. Tăng replicas mà không tăng backend capacity.** Discovery có thêm endpoints nhưng tất cả cùng tranh DB hoặc external quota.

**12. Dùng một service name xuyên staging/prod không có scope.** Có nguy cơ gọi nhầm môi trường, phá isolation và dữ liệu.

**13. Đưa routing theo version vào code nghiệp vụ bằng IP hoặc hostname instance.** Sử dụng metadata/traffic policy và contract version.

**14. Quên graceful shutdown.** Endpoint bị hủy trong khi còn nhiều in-flight operations; cần draining, timeout và retry an toàn.

**15. Route tự động qua region mà không xem xét state.** Failover network không đồng nghĩa dữ liệu/payment đã nhất quán.

**16. Chỉ quan sát 5xx mà không có endpoint-level context.** Không biết lỗi DNS, no healthy upstream, TLS hay application.

**17. Đặt proxy LB nhưng bỏ hết error handling trong app.** Proxy không loại bỏ timeout, ambiguous commit, idempotency và business compensation.

**18. Coi Service là bounded context.** Một Kubernetes Service là đối tượng networking, không tự chứng minh domain ownership.

## 24. Cây quyết định chọn discovery/routing

~~~mermaid
flowchart TD
    A["Client cần gọi một service logic"] --> B{"Hệ thống chạy trên orchestrator có Service DNS/LB?"}
    B -- "Có" --> C["Ưu tiên service name ổn định và native service routing"]
    B -- "Không" --> D{"Có registry / platform discovery?"}
    D -- "Có" --> E["Client-side hoặc proxy-side resolver"]
    D -- "Không" --> F["Định nghĩa discovery phù hợp hoặc dùng LB/DNS được quản lý"]
    C --> G{"Cần canary, locality, mTLS, policy nâng cao?"}
    E --> G
    F --> G
    G -- "Có" --> H["Gateway / mesh / LB policy phù hợp"]
    G -- "Chưa cần" --> I["Giữ giải pháp đơn giản, đo SLO"]
    H --> J["Readiness, endpoint lifecycle, retry, auth, metrics"]
    I --> J
~~~

Không nhất thiết cần service mesh khi Kubernetes Service đáp ứng mọi nhu cầu. Không nhất thiết cần registry riêng khi nền tảng đã quản lý endpoints. Ưu tiên **một đường discovery rõ, ít lớp chồng lấn và có khả năng debug**.

### Mẫu ADR ngắn

~~~text
Context:
- Số service/replica và môi trường chạy:
- Hệ thống orchestrator hiện có:
- Cần scale, rollout, multi-zone không:
- Network/auth/trust requirements:

Options:
A. Native Service DNS + ClusterIP
B. Registry + client-side load balancing
C. Proxy/gateway/service mesh routing

Decision:
- Logical service name:
- Scope (namespace/environment/region):
- Endpoint owner/discovery source:
- Load balancing policy:
- Readiness/draining:
- Authentication/authorization:
- Timeout/retry/idempotency:
- Observability:
- Failure fallback:
- Điều kiện đánh giá lại:
~~~

## 25. Bài tập thực hành 1: phát hiện hard-coded instance

**Bối cảnh:** Một Order service gọi Inventory ở http://10.20.1.14:8080. Inventory có 3 replicas, thường rolling deploy và scale vào cuối tuần.

**Yêu cầu:**

1. Giải thích tại sao IP cứng gây lỗi khi Pod bị thay.
2. Xác định service name hợp lý và phạm vi namespace/environment.
3. Vẽ service discovery path từ Order tới Inventory.
4. Thiết kế readiness cho Inventory.
5. Nêu thay đổi cần có trong app configuration, HTTP client và test.
6. Giải thích điều gì sẽ xảy ra với connection đang mở khi Pod bị terminate.
7. Thiết kế một phép thử rollout không thay đổi code Order.

**Kết quả mong đợi:** Order gọi tên logic ổn định; deployment có thể thay instance; các request mới được route tới endpoints phù hợp; caller vẫn xử lý lỗi mạng có kiểm soát.

## 26. Bài tập thực hành 2: cấu hình Kubernetes Service

Cho Deployment Inventory 3 replicas ở namespace commerce trên port 8080.

**Thực hiện:**

1. Viết manifest Service type ClusterIP, port 80 và targetPort 8080.
2. Chọn selector app=inventory khớp Pod labels.
3. Thêm readinessProbe phù hợp với endpoint /health/ready.
4. Từ một Pod Order trong namespace commerce, mô tả cách gọi http://inventory.
5. Từ namespace billing, mô tả tên đầy đủ hơn.
6. Khi một Inventory Pod chưa ready, giải thích Service endpoint membership thay đổi ra sao.
7. Khi Pod bị tạo lại với IP mới, giải thích tại sao Order không cần sửa URL.
8. Khi DNS vẫn resolve được Service nhưng không có ready endpoint, mô tả lỗi khả dĩ và cách caller xử lý.

**Lưu ý:** Không cần triển khai thực tế nếu không có cluster. Có thể chứng minh bằng sơ đồ và kiểm thử giả lập lifecycle.

## 27. Bài tập thực hành 3: registry và client-side LB

Giả sử registry trả:

~~~text
inventory:
  - 10.0.0.11:8080, zone-a, ready
  - 10.0.0.12:8080, zone-a, ready
  - 10.0.1.11:8080, zone-b, ready
~~~

Hãy thiết kế một resolver/client LB:

- Lấy endpoint set theo logical service name;
- Cache với thời hạn và refresh thích hợp;
- Chọn ưu tiên zone-a khi Order chạy ở zone-a;
- Failover sang zone-b khi hai endpoints zone-a lỗi;
- Không retry command không idempotent một cách mù quáng;
- Đo selected backend, lỗi kết nối, retry và thời gian resolve;
- Xử lý trường hợp registry timeout nhưng cached endpoints còn dùng được;
- Xử lý khi tất cả endpoints trả lỗi;
- Bảo đảm endpoint được xác thực đúng identity khi dùng TLS/mTLS.

Vẽ sequence diagram cho một request đầu thành công và một request phải failover.

## 28. Bài tập thực hành 4: rollout và client cache stale

**Kịch bản:** Inventory v1 có Pod IP 10.1.0.5; client gRPC giữ một connection lâu dài. Deployment thay v1 bằng v2 ở 10.1.0.9. DNS/Service đã cập nhật nhưng client vẫn gặp reset trên connection cũ.

**Phân tích:**

1. Tại sao DNS update không nhất thiết chuyển connection hiện có?
2. Kể tên nơi có thể cache endpoint: OS, runtime, client SDK, proxy.
3. Phân biệt lỗi kết nối và lỗi backend đã commit nhưng response mất.
4. Đề xuất connection draining, max age, retry budget và idempotency.
5. Dùng metric nào chứng minh traffic đã dịch chuyển sang v2?
6. Kiểm tra contract compatibility v1/v2 như thế nào?
7. Khi v2 bị rollback, những request đang xử lý có thể ra sao?

**Đầu ra:** Runbook ngắn có điều kiện phát hiện, giảm tác động và xác nhận phục hồi.

## 29. Bài tập thực hành 5: tách discovery và authorization

**Kịch bản:** Order resolve tên payment thành một endpoint trong private subnet. Một service khác cũng có thể truy cập subnet đó nhưng không có quyền tạo charge.

Hãy giải thích:

1. Vì sao “ở trong mạng nội bộ” chưa đủ?
2. Làm sao xác thực Payment đúng workload identity?
3. Làm sao Payment xác thực caller là Order và có quyền AuthorizePayment?
4. Cần làm gì với certificate rotation, trust domain và policy deny?
5. Nếu service name resolve nhầm endpoint, TLS/mTLS có thể phát hiện sai identity thế nào?
6. Làm sao tránh một endpoint nội bộ tùy ý do user cung cấp trở thành SSRF?

**Đầu ra:** Sơ đồ phân tách naming, resolution, authentication, authorization và policy enforcement.

## 30. Bộ câu hỏi ôn tập

1. Service logic khác instance ID và endpoint ở điểm nào?
2. Vì sao một service có thể có nhiều Pod IP nhưng chỉ có một tên logic?
3. Service discovery giải quyết bài toán gì mà API contract không tự giải quyết?
4. Client-side discovery và server-side discovery khác nhau ở chỗ ai chọn backend?
5. DNS A/AAAA, CNAME và SRV có thể tham gia resolution như thế nào?
6. Vì sao DNS TTL không đủ để đảm bảo request lập tức chuyển sang Pod mới?
7. Trong Kubernetes, ClusterIP Service khác Pod IP ra sao?
8. EndpointSlice và readiness liên quan thế nào tới tập backend được phục vụ?
9. Headless Service chuyển thêm trách nhiệm gì cho client?
10. Vì sao Pod đang Running nhưng không Ready có thể không nhận traffic?
11. Liveness probe và readiness probe có mục tiêu khác nhau ra sao?
12. Registry self-registration cần lease/heartbeat khi instance crash vì sao?
13. Registry outage có luôn làm mọi request hiện tại thất bại không? Vì sao?
14. Khi cache endpoints stale, client nên làm gì ngoài retry vô hạn?
15. Một endpoint trả 503 vì shared DB outage khác một Pod bị crash ở chỗ nào?
16. Load balancing theo request và theo connection có tác động gì tới HTTP/2 streams?
17. Khi dùng canary 5%, điều gì khiến tỷ trọng quan sát không đúng chính xác 5%?
18. Vì sao service discovery không tự giải quyết schema compatibility giữa v1 và v2?
19. Khi scale từ 3 lên 10 replicas, Order cần thay đổi code/config endpoint không?
20. Khi scale-in, vì sao cần unready/draining trước shutdown?
21. Tên service logic có đồng nghĩa identity bảo mật đã xác thực không?
22. mTLS giúp giải quyết chuyện gì mà DNS/registry không giải quyết?
23. Multi-zone routing phải xử lý trường hợp local zone lỗi như thế nào?
24. Multi-region failover có thể nguy hiểm với payment side effect vì sao?
25. Khi Order gọi Payment timeout, tại sao không thể đổi endpoint và retry với payment ID mới ngay?
26. Service mesh có thể mang lại những policy nào và vì sao nó không thay business error handling?
27. Phân biệt control plane và data plane trong một service mesh hoặc routing system.
28. Nếu Service DNS resolve đúng nhưng “no healthy upstream”, cần xem những thành phần nào?
29. Nếu backend selection phân phối lệch, những metric và đặc điểm connection nào cần kiểm tra?
30. Nếu tất cả Pods healthy nhưng caller nhận 403, đây có thể là discovery error hay authorization/policy error?
31. Vì sao hard-code tên version trong client đôi khi làm tăng release coupling?
32. Khi nào dùng native Kubernetes Service là đủ, khi nào mới cân nhắc registry/mesh riêng?
33. Một gateway công khai khác gì internal service DNS?
34. Làm sao kiểm tra một client không vô tình gọi staging khi đang ở production?
35. Những kiểm thử nào chứng minh address resolution chịu được instance churn?

## 31. Checklist khi thiết kế discovery và routing

- [ ] Tên service logic diễn đạt capability/contract, không phải IP hoặc tên của một instance.
- [ ] Service name có scope theo environment/namespace/cluster/region cần thiết.
- [ ] Mỗi instance có runtime endpoint riêng và lifecycle rõ.
- [ ] Application không hard-code danh sách Pod/VM IP dễ biến động.
- [ ] Có một nguồn discovery rõ (DNS, registry, orchestrator/control plane).
- [ ] Client-side hay server-side resolution được chọn có lý do và ownership.
- [ ] Readiness và deregistration phản ánh khả năng nhận traffic mới.
- [ ] Có graceful shutdown/draining để giảm lỗi khi scale-in/rollout.
- [ ] Client hiểu DNS/registry cache, TTL và connection pooling.
- [ ] Không mặc định DNS thay đổi sẽ đóng mọi connection cũ.
- [ ] Có giới hạn timeout, retry budget và xử lý kết quả mơ hồ.
- [ ] Command có side effect dùng idempotency và reconciliation khi cần.
- [ ] Load balancing policy phù hợp request cost, locality và capacity.
- [ ] Routing version/canary được áp dụng mà không phá contract.
- [ ] Có observability ở DNS, registry, LB/proxy, network và application.
- [ ] Có cách phát hiện endpoint set rỗng và stale cache.
- [ ] Multi-zone/region failover cân nhắc consistency và security.
- [ ] Service name không được coi là xác thực; authn/authz được thực thi riêng.
- [ ] Có policy ngăn request tới endpoint nội bộ không được phép.
- [ ] Đã thử Pod crash, rollout, scale, registry/DNS outage, long-lived connections.
- [ ] Có ADR cho lựa chọn discovery và điều kiện đánh giá lại.

**Kết luận:** Định danh dịch vụ logic là cách giữ ổn định **đối tượng mà client muốn gọi** bất chấp hạ tầng biến động. Xác định địa chỉ thể hiện chạy là cách ánh xạ tên đó sang **tập endpoints đủ điều kiện** rồi chọn một backend cho request. DNS, registry, Kubernetes Service, load balancer và service mesh cung cấp những biến thể của cơ chế này; chúng giảm coupling vị trí và hỗ trợ scale/rollout/failover, nhưng không thay thế contract tương thích, xác thực danh tính, timeout, idempotency hoặc việc xử lý lỗi phân tán.
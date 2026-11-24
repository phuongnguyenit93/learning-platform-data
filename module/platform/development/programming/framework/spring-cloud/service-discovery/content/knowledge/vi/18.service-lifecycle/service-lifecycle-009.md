# Mở rộng hoặc thu hẹp số bản sao và xác minh quá trình hội tụ

Trong microservice, tăng hoặc giảm số instance không kết thúc ở thao tác đổi số replica. Sau khi scale, nền tảng triển khai phải tạo hoặc dừng tiến trình; instance phải đi qua readiness; registry phải nhận registration hoặc deregistration; dữ liệu phải lan đến discovery client; LoadBalancer phải cập nhật danh sách ứng viên; traffic cuối cùng mới chuyển sang tập instance mới.

Các bước này diễn ra bất đồng bộ và có thể có độ trễ khác nhau. Vì vậy, cần phân biệt:

- **Desired replicas:** số bản sao mà người vận hành hoặc autoscaler yêu cầu.
- **Running replicas:** số tiến trình/Pod đang chạy.
- **Ready replicas:** số instance đã sẵn sàng nhận request.
- **Registered instances:** số instance có registration trong registry.
- **Healthy instances:** số instance vượt qua health check theo chính sách.
- **Discoverable instances:** số instance mà consumer đã nhìn thấy.
- **Serving instances:** số instance thực sự nhận và xử lý traffic.

Một hệ thống chỉ được xem là hội tụ khi các lớp liên quan đã phản ánh cùng một trạng thái mong muốn trong giới hạn thời gian chấp nhận được. Bài này hướng dẫn scale-out, scale-in, phối hợp Kubernetes với Spring Cloud Discovery, xử lý Eureka/Consul và đo thời gian hội tụ từ control plane đến request thực tế.

## 1. Mô hình vòng đời khi thay đổi số replica

Giả sử `inventory-service` đang có 3 instance và cần tăng lên 5. Orchestrator nhận desired replicas bằng 5, tạo thêm workload, chờ ứng dụng sẵn sàng, sau đó instance đăng ký với registry. Consumer phải nhận được danh sách mới trước khi LoadBalancer có thể chọn hai instance bổ sung.

Khi giảm từ 5 xuống 3, hai instance cần được rút khỏi traffic, hoàn tất request đang chạy, deregister khỏi registry và dừng tiến trình. Nếu dừng process trước khi consumer ngừng chọn instance, request có thể đi vào endpoint đã chết.

~~~mermaid
flowchart TD
    DESIRED["Desired replicas thay đổi"] --> ORCH["Orchestrator / Deployment controller"]
    ORCH --> START["Tạo hoặc dừng process / Pod"]
    START --> READY["Readiness và application health"]
    READY --> REG["Register / deregister trong registry"]
    REG --> REPL["Registry replication / health evaluation"]
    REPL --> DISC["DiscoveryClient cập nhật snapshot"]
    DISC --> LB["LoadBalancer cập nhật candidates"]
    LB --> TRAFFIC["Traffic đi tới tập instance mới"]
    TRAFFIC --> VERIFY["Xác minh số lượng và request thực tế"]
~~~

Mỗi lớp có thể hội tụ ở một thời điểm khác nhau. Chẳng hạn Kubernetes đã có đủ Pod Ready nhưng Eureka Client chưa fetch registry mới; hoặc Consul đã đánh dấu service passing nhưng LoadBalancer cache vẫn giữ danh sách cũ.

### 1.1. Các trạng thái không thể thay thế cho nhau

| Trạng thái | Câu hỏi | Nguồn thường dùng |
|---|---|---|
| Desired | Đã yêu cầu bao nhiêu bản sao? | Deployment, StatefulSet, HPA hoặc cấu hình runtime |
| Running | Có bao nhiêu process/Pod đang chạy? | Orchestrator hoặc process supervisor |
| Ready | Có bao nhiêu instance sẵn sàng nhận traffic? | Readiness probe, Actuator readiness |
| Registered | Registry đang lưu bao nhiêu registration? | Eureka registry hoặc Consul Catalog |
| Healthy | Có bao nhiêu instance qua health check? | Eureka status hoặc Consul Health API |
| Discoverable | Consumer đã thấy bao nhiêu instance? | DiscoveryClient |
| Eligible | LoadBalancer có thể chọn bao nhiêu instance? | ServiceInstanceListSupplier sau filter |
| Serving | Instance nào đang thực sự nhận request? | Access log, request metric, tracing |

Không dùng số Pod Running thay cho số instance Healthy. Một process có thể chạy nhưng chưa mở cổng HTTP, chưa kết nối database hoặc chưa hoàn tất khởi tạo. Tương tự, registry có thể còn registration của process đã chết cho đến khi nhận deregistration hoặc hết lease.

## 2. Scale-out: tăng số bản sao

Scale-out thường gồm các bước sau:

1. Người vận hành hoặc autoscaler tăng desired replicas.
2. Orchestrator tạo Pod/VM/process mới.
3. Ứng dụng khởi động và hoàn thành các tác vụ initialization.
4. Readiness chuyển thành đạt yêu cầu.
5. Instance đăng ký với Eureka hoặc Consul.
6. Registry cập nhật trạng thái và phân phối thay đổi.
7. Consumer nhận danh sách instance mới.
8. LoadBalancer bắt đầu chọn instance mới.
9. Metric request xác nhận instance thực sự nhận traffic.

~~~mermaid
sequenceDiagram
    participant H as HPA / Operator
    participant K as Kubernetes
    participant A as New Spring Boot instance
    participant R as Eureka / Consul
    participant C as Consumer
    participant L as LoadBalancer

    H->>K: Set replicas = 5
    K->>A: Schedule and start Pod
    A->>A: Initialize application
    A->>A: Readiness becomes UP
    A->>R: Register service instance
    R-->>C: Registry data becomes available
    C->>R: Fetch / refresh registry
    C-->>L: Updated ServiceInstance list
    L->>A: Select new instance for request
    A-->>L: Successful response
~~~

### 2.1. Readiness phải phản ánh khả năng phục vụ

Readiness là tín hiệu cho biết instance có thể nhận request hay chưa. Không nên đánh dấu Ready ngay khi JVM vừa mở cổng nếu ứng dụng còn đang:

- Chạy database migration hoặc warm-up cache.
- Tải model hoặc dữ liệu cần thiết.
- Thiết lập kết nối đến broker hoặc dependency bắt buộc.
- Khởi tạo client và cấu hình bảo mật.
- Phục hồi trạng thái cần thiết trước khi xử lý request.

Với Spring Boot Actuator, có thể dùng readiness health group. Ví dụ:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
~~~

Đây là ví dụ minh họa; chỉ đưa dependency vào readiness nếu service thực sự không thể phục vụ khi dependency đó lỗi. Nếu đưa mọi dependency tùy chọn vào readiness, một sự cố phụ trợ có thể làm toàn bộ instance bị rút khỏi traffic và tạo cascading failure.

Kubernetes readiness probe có thể gọi endpoint Actuator:

~~~yaml
readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
~~~

Kubernetes loại Pod không Ready khỏi EndpointSlice dùng cho Service traffic. Nếu ứng dụng cũng đăng ký độc lập vào Eureka hoặc Consul, cần bảo đảm trạng thái registry được đồng bộ theo cùng readiness policy; Kubernetes readiness không tự động cập nhật Eureka registration. Trình tự “Ready rồi register” trong sơ đồ là mục tiêu vận hành cần đạt, không phải thứ tự tự động được bảo đảm bởi mọi integration. Nếu registry đăng ký instance trước khi readiness đạt, hãy giữ instance ở trạng thái không phục vụ hoặc để health check loại nó khỏi candidate list cho đến khi sẵn sàng.

### 2.2. Startup probe và liveness không phải readiness

Ba loại probe có vai trò khác nhau:

| Probe | Câu hỏi | Khi thất bại |
|---|---|---|
| Startup | Ứng dụng đã khởi động xong chưa? | Kubernetes tiếp tục thử startup probe; sau ngưỡng mới restart |
| Liveness | Process có còn sống và có thể tiếp tục chạy không? | Kubernetes restart container |
| Readiness | Instance có thể nhận request ngay lúc này không? | Kubernetes loại instance khỏi Service endpoints |

Liveness không nên kiểm tra mọi dependency bên ngoài. Nếu database tạm thời mất kết nối mà liveness fail, Kubernetes có thể restart hàng loạt instance, làm tải lên database và các instance còn lại tăng thêm.

## 3. Scale-in: giảm số bản sao an toàn

Scale-in khó hơn scale-out vì cần ngừng gửi request mới đến instance sắp dừng trong khi vẫn hoàn tất request đang chạy.

Luồng tổng quát:

1. Giảm desired replicas.
2. Orchestrator chọn instance cần terminate.
3. Instance chuyển sang trạng thái terminating hoặc not-ready.
4. Endpoint routing và registry ngừng đưa instance vào danh sách mới.
5. Consumer cập nhật DiscoveryClient và LoadBalancer cache.
6. Ứng dụng ngừng nhận request mới.
7. Request đang xử lý được hoàn tất trong thời gian drain.
8. Instance deregister và process kết thúc.

~~~mermaid
sequenceDiagram
    participant K as Orchestrator
    participant A as Instance to remove
    participant R as Registry
    participant C as Consumer
    participant L as LoadBalancer

    K->>A: Begin termination
    K->>A: Mark endpoint terminating / not-ready
    A->>R: Deregister or publish OUT_OF_SERVICE
    R-->>C: Updated registry state
    C->>C: Refresh discovery snapshot
    C-->>L: Remove instance from candidates
    Note over A,L: Wait for propagation and drain
    A->>A: Finish in-flight requests
    K->>A: Send TERM / close process
~~~

### 3.1. Rút instance khỏi traffic trước khi dừng process

Nếu chỉ gửi SIGTERM và chờ ứng dụng tự tắt, một số consumer vẫn có thể giữ instance trong cache và chọn nó cho request mới. Trước khi dừng, cần có cơ chế báo instance không còn đủ điều kiện nhận traffic:

- Kubernetes: Pod chuyển Terminating, readiness/EndpointSlice phản ánh endpoint không còn Ready.
- Eureka: cập nhật status hoặc deregister theo lifecycle.
- Consul: deregister service hoặc làm health check chuyển critical theo quy trình được thiết kế.
- Gateway hoặc load balancer ngoài: loại endpoint khỏi backend pool.

Một instance bị rút khỏi discovery không đồng nghĩa mọi request đang chạy đã kết thúc. Cần có giai đoạn drain và thời hạn shutdown phù hợp.

### 3.2. Graceful shutdown của Spring Boot

Spring Boot hỗ trợ graceful shutdown trên embedded Tomcat, Jetty và Reactor Netty. Khi application context đóng, web server ngừng nhận request mới theo cơ chế của server và cho request đang chạy thời gian hoàn tất.

Có thể cấu hình rõ:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Thời hạn 30 giây chỉ là ví dụ. Cần chọn dựa trên p95/p99 thời gian request, công việc nền và thời hạn termination của orchestrator. Nếu request có thể chạy 60 giây nhưng shutdown timeout chỉ 10 giây, request vẫn có thể bị ngắt.

Graceful shutdown chỉ xử lý phần web server và lifecycle của ứng dụng. Nó không tự đảm bảo mọi registry, consumer cache và gateway đã cập nhật trước khi process kết thúc. Cần phối hợp deregistration, readiness và drain.

### 3.3. Kubernetes termination và preStop

Khi Pod bị xóa, Kubernetes đặt deletion timestamp, đánh dấu Pod Terminating và bắt đầu quá trình shutdown. Control plane cập nhật EndpointSlice trong khi kubelet bắt đầu lifecycle shutdown trên node; hai việc này diễn ra song song, không có bảo đảm hook đã đợi mọi proxy cập nhật xong. Nếu có `preStop`, kubelet chạy hook này trước khi gửi TERM; thời gian hook nằm trong `terminationGracePeriodSeconds`.

Ví dụ:

~~~yaml
spec:
  terminationGracePeriodSeconds: 60
  containers:
    - name: inventory
      image: example/inventory-service:1.0
      lifecycle:
        preStop:
          httpGet:
            path: /internal/drain
            port: 8080
            scheme: HTTP
~~~

Endpoint `/internal/drain` ở đây là endpoint ứng dụng tự triển khai để chuyển readiness hoặc trạng thái registry. Nó không tồn tại sẵn trong Spring Boot. Endpoint phải được bảo vệ, chỉ cho phép kubelet/sidecar hoặc cơ chế nội bộ gọi. Hook HTTP cần trả kết quả thành công sau khi đã ghi nhận yêu cầu drain; không giữ request mở trong suốt thời gian drain.

Không nên thêm một lệnh `sleep` cố định mà không đo thời gian hội tụ. Nếu cần một khoảng chờ cho proxy hoặc registry propagation, hãy xác định bằng thử nghiệm và đặt nó trong ngân sách termination. Tổng thời gian `preStop`, graceful shutdown và drain phải nhỏ hơn grace period; nếu vượt, kubelet có thể buộc dừng process.

### 3.4. Không nhầm readiness với deregistration

Kubernetes readiness failure loại Pod khỏi EndpointSlice cho Service traffic, nhưng không tự xóa registration của ứng dụng khỏi Eureka hoặc Consul. Nếu ứng dụng đăng ký song song vào hai hệ thống, phải có lifecycle riêng cho registry đó.

Với Eureka, client có thể explicit unregister khi shutdown. Với Consul, Spring Cloud Consul có lifecycle đăng ký và deregistration; nếu dùng TTL heartbeat, cần xử lý việc ngừng heartbeat và chính sách re-registration. Đừng dựa hoàn toàn vào lease/session timeout nếu cần scale-in có kiểm soát.

## 4. Scale trong Kubernetes

Kubernetes Deployment quản lý desired replicas thông qua `.spec.replicas`. Có thể scale thủ công:

~~~bash
kubectl scale deployment inventory-service --replicas=5
~~~

Kiểm tra trạng thái:

~~~bash
kubectl get deployment inventory-service
kubectl get replicasets -l app=inventory-service
kubectl get pods -l app=inventory-service
~~~

Các trường thường quan sát:

- `spec.replicas`: desired replicas.
- `status.replicas`: số Pod được Deployment quản lý.
- `status.readyReplicas`: số Pod Ready.
- `status.availableReplicas`: số Pod được xem là available theo minReadySeconds.

Ví dụ Deployment:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inventory-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: inventory-service
  template:
    metadata:
      labels:
        app: inventory-service
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: inventory
          image: example/inventory-service:1.0
          ports:
            - name: http
              containerPort: 8080
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            failureThreshold: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
~~~

`maxSurge` cho phép tạo thêm Pod tạm thời vượt desired replicas trong rolling update. `maxUnavailable` giới hạn số Pod có thể unavailable trong quá trình cập nhật. Chúng điều khiển rollout, không phải autoscaling policy và không thay thế readiness.

### 4.1. Xác minh EndpointSlice

Với Kubernetes Service, EndpointSlice phản ánh endpoint được chọn bởi selector. Kiểm tra:

~~~bash
kubectl get endpointslice -l kubernetes.io/service-name=inventory-service
kubectl get endpointslice -l kubernetes.io/service-name=inventory-service -o yaml
~~~

Quan sát các condition:

- `ready`: endpoint có được dùng cho traffic thông thường hay không.
- `serving`: endpoint có đang phục vụ request hay không.
- `terminating`: endpoint đang trong quá trình kết thúc hay không.

Endpoint đang terminating thường có `ready=false`. Trong một số tình huống tất cả endpoint đều terminating, proxy có thể vẫn sử dụng endpoint `serving` để tránh mất toàn bộ traffic. Vì vậy, khi drain cần xem đủ ba condition, không chỉ `ready`.

### 4.2. Autoscaling với HPA

Horizontal Pod Autoscaler điều chỉnh desired replicas dựa trên metric như CPU, memory hoặc custom/external metric. Ví dụ:

~~~yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: inventory-service
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: inventory-service
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 65
~~~

HPA thay đổi desired replicas; Deployment controller mới tạo hoặc xóa Pod. Việc HPA báo desired replicas đã tăng không có nghĩa instance đã Ready hoặc đã xuất hiện trong service registry.

Scale-in có thể có stabilization window để tránh dao động khi metric giảm trong thời gian ngắn. Nên chọn min/max replicas, scale policies và stabilization theo tải, thời gian khởi động và chi phí của service.

## 5. Scale-out và scale-in với Eureka

Eureka client đăng ký metadata và gửi heartbeat định kỳ. Theo cấu hình Spring Cloud Netflix hiện hành, các giá trị mặc định thường gặp là:

| Property | Default | Ý nghĩa |
|---|---:|---|
| `eureka.instance.lease-renewal-interval-in-seconds` | 30s | Chu kỳ client gửi heartbeat |
| `eureka.instance.lease-expiration-duration-in-seconds` | 90s | Thời gian server chờ heartbeat trước khi xem lease hết hạn |
| `eureka.client.registry-fetch-interval-seconds` | 30s | Chu kỳ client fetch registry |
| `eureka.client.should-unregister-on-shutdown` | true | Client explicit unregister khi shutdown |

Giá trị phụ thuộc release và cấu hình. Không nên giảm heartbeat/lease quá thấp trong production chỉ để rút ngắn thời gian hội tụ; network jitter có thể khiến instance khỏe bị xem là mất.

### 5.1. Scale-out với Eureka

Khi instance mới start:

1. Eureka client tạo registration và gửi lên server.
2. Server lưu instance metadata và trạng thái ban đầu.
3. Client tiếp tục gửi heartbeat.
4. Peer server có thể cần thời gian replication.
5. Consumer fetch registry và cập nhật local cache.
6. LoadBalancer sử dụng danh sách mới.

Tài liệu Spring Cloud Netflix lưu ý một instance có thể chưa discoverable cho đến khi instance, server và client có metadata đồng bộ trong cache; với heartbeat mặc định, quá trình có thể mất tới khoảng ba chu kỳ heartbeat. Đây là mô tả hành vi hội tụ, không phải SLA cố định cho mọi topology.

### 5.2. Scale-in với Eureka

Khi Spring Boot client shutdown bình thường, property `should-unregister-on-shutdown` mặc định true giúp client yêu cầu server hủy registration. Với abrupt crash hoặc mất mạng, server có thể chỉ xóa registration khi lease hết hạn và eviction diễn ra.

Eureka server có self-preservation để tránh xóa hàng loạt instance khi server nhận ít heartbeat bất thường, vì điều đó có thể do network partition thay vì mọi service cùng chết. Khi self-preservation hoạt động, stale registration có thể tồn tại lâu hơn dự kiến. Không tắt self-preservation chỉ để ép registry xóa nhanh; trước tiên phải kiểm tra renewal rate, network, peer replication và trạng thái instance.

Cấu hình minh họa:

~~~yaml
eureka:
  client:
    should-unregister-on-shutdown: true
    registry-fetch-interval-seconds: 30
  instance:
    lease-renewal-interval-in-seconds: 30
    lease-expiration-duration-in-seconds: 90
~~~

Khi dùng Eureka cùng Spring Cloud LoadBalancer, nhớ rằng Eureka client đã có local registry cache. LoadBalancer cache có thể tạo thêm một lớp trễ; nếu DiscoveryClient đã cache, tài liệu LoadBalancer khuyến nghị cân nhắc tắt cache LoadBalancer để tránh double caching.

## 6. Scale-out và scale-in với Consul

Spring Cloud Consul đăng ký service cùng host, port, ID và metadata. Theo mặc định, integration tạo HTTP health check tới `/actuator/health` và Consul Agent kiểm tra định kỳ. Nếu check thất bại, instance được đánh dấu critical.

Ví dụ cấu hình:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        register: true
        health-check-path: /actuator/health
        health-check-interval: 10s
        register-health-check: true
~~~

Khi scale-out, registration mới có thể xuất hiện trong Catalog trước khi health check chuyển passing. Vì vậy cần phân biệt Catalog count với passing count. Consumer dùng Health API và filter passing nếu muốn chỉ nhận instance khỏe.

### 6.1. HTTP health check và TTL heartbeat

Consul có hai mô hình phổ biến:

- **HTTP check:** Agent chủ động gọi endpoint của ứng dụng theo chu kỳ.
- **TTL check:** ứng dụng chủ động gửi heartbeat đến Consul Agent để gia hạn TTL.

TTL heartbeat không tự động đồng nghĩa ứng dụng Ready. Ứng dụng phải gửi heartbeat chỉ khi điều kiện health/readiness phù hợp. Nếu process vẫn gửi heartbeat dù request handler không phục vụ được, Consul sẽ giữ trạng thái khỏe sai.

Trong Spring Cloud Consul, TTL heartbeat có thể bật bằng cấu hình:

~~~yaml
spring:
  cloud:
    consul:
      discovery:
        heartbeat:
          enabled: true
          ttl: 10s
~~~

Tài liệu Spring Cloud Consul hiện hành mô tả chu kỳ heartbeat mặc định là 30 giây nếu không cấu hình riêng. Tính năng tự đăng ký lại service khi heartbeat thất bại mặc định tắt; nếu bật, cần hiểu điều kiện re-register và tránh tạo registration lặp ngoài ý muốn.

### 6.2. Scale-in với Consul

Với shutdown bình thường, integration có thể deregister service trong lifecycle. Với crash hoặc mất heartbeat, check có thể chuyển critical; registration không nhất thiết biến mất ngay lập tức. Có thể cấu hình thời gian critical trước khi deregister nếu phiên bản Consul hỗ trợ và policy yêu cầu.

Không dùng `?passing` để đếm tổng registration. Query đó chỉ trả các node có mọi check passing. Khi scale-in, kiểm tra cả Catalog và Health API để biết instance đã bị xóa hay chỉ đang critical.

## 7. Tương tác giữa registry và Spring Cloud LoadBalancer

Ngay cả khi registry đã cập nhật, consumer có thể chưa chọn đúng tập instance mới vì DiscoveryClient và LoadBalancer có cache riêng.

Spring Cloud LoadBalancer dùng `ServiceInstanceListSupplier` để lấy danh sách instance. Cache mặc định có TTL 35 giây và capacity 256 trong tài liệu hiện hành. Nếu DiscoveryClient như Eureka đã cache, nên cân nhắc tắt LoadBalancer cache để tránh double caching.

Cấu hình ví dụ khi registry client đã cache:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Nếu DiscoveryClient không cache, có thể giữ cache LoadBalancer và chọn TTL theo mục tiêu hội tụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 10s
        capacity: 256
~~~

TTL 10 giây chỉ là ví dụ, không phải khuyến nghị chung. Giảm TTL làm danh sách mới được nhìn thấy nhanh hơn nhưng có thể tăng số lần gọi discovery. Đối chiếu cả chu kỳ refresh của registry client, cache supplier và policy filter.

### 7.1. Consumer không nhất thiết thấy tất cả instance

LoadBalancer có thể lọc instance theo zone, hint, health hoặc metadata. Vì vậy:

- Registry có 5 instance.
- DiscoveryClient có 5 instance.
- Supplier áp dụng zone preference còn 3.
- Health filter còn 2.
- LoadBalancer chỉ chọn trong 2 instance.

Đây không nhất thiết là lỗi hội tụ. Khi xác minh, cần so sánh đúng tập dữ liệu ở từng lớp.

## 8. Xác định thời gian hội tụ

Không dùng một khái niệm “scale xong” duy nhất. Hãy định nghĩa mốc thời gian cho scale-out và scale-in.

### 8.1. Scale-out convergence time

Đặt:

- `t0`: thời điểm gửi yêu cầu tăng desired replicas.
- `t1`: thời điểm tất cả replica mới ở trạng thái Ready.
- `t2`: thời điểm tất cả replica mới được đăng ký và healthy trong registry.
- `t3`: thời điểm consumer mục tiêu nhìn thấy các instance mới.
- `t4`: thời điểm LoadBalancer có thể chọn các instance mới.
- `t5`: thời điểm quan sát thấy request thành công đến instance mới.

Khi đó:

~~~text
T_ready       = t1 - t0
T_registered  = t2 - t0
T_discovered  = t3 - t0
T_eligible    = t4 - t0
T_serving     = t5 - t0
~~~

Mục tiêu vận hành thường quan tâm `T_serving`, vì instance mới chỉ hữu ích khi thực sự nhận và xử lý traffic. Tuy nhiên, đo từng mốc giúp xác định lớp nào gây chậm.

### 8.2. Scale-in convergence time

Đặt:

- `s0`: thời điểm gửi yêu cầu giảm desired replicas.
- `s1`: thời điểm endpoint bị đánh dấu terminating/not-ready.
- `s2`: thời điểm registry không còn coi instance là healthy hoặc registration bị xóa.
- `s3`: thời điểm consumer ngừng đưa instance vào candidate list.
- `s4`: thời điểm không còn request mới được gửi đến instance.
- `s5`: thời điểm request đang chạy hoàn tất và process dừng.

~~~text
T_removed_from_candidates = s3 - s0
T_no_new_traffic           = s4 - s0
T_drain_complete           = s5 - s0
~~~

Scale-in chỉ an toàn khi không còn request mới được gửi đến instance đã rút, và request đang chạy có đủ thời gian hoàn tất trước khi process bị dừng.

### 8.3. Đặt SLO hội tụ

Ví dụ SLO nội bộ:

- 95% lần scale-out nhỏ hơn hoặc bằng 90 giây để instance mới nhận request thành công.
- 99% lần scale-in nhỏ hơn hoặc bằng 60 giây để consumer ngừng gửi request mới tới instance được rút.
- 99% request đang chạy hoàn tất trong termination grace period.

Các con số chỉ là ví dụ. Chọn ngưỡng theo thời gian startup, registry topology, cache TTL, health-check interval, request duration và mức tải thực tế. Đo p50/p95/p99 qua nhiều lần scale, không dựa vào một lần thử.

## 9. Metric để xác minh hội tụ

Có thể tạo bộ metric custom hoặc tổng hợp từ orchestrator, registry và consumer:

| Metric | Type | Ý nghĩa |
|---|---|---|
| `service_replicas_desired` | Gauge | Desired replicas |
| `service_replicas_running` | Gauge | Process/Pod đang chạy |
| `service_replicas_ready` | Gauge | Replica Ready |
| `service_registry_instances` | Gauge | Registration theo service/status |
| `service_discovery_instances` | Gauge | Instance consumer nhìn thấy |
| `service_loadbalancer_candidates` | Gauge | Candidate sau filter |
| `service_scale_operations_total` | Counter | Số lần scale-out/scale-in |
| `service_scale_convergence_seconds` | Histogram | Thời gian từ scale request đến mốc hội tụ |
| `service_instance_drain_duration_seconds` | Histogram | Thời gian drain instance |
| `service_registry_snapshot_timestamp_seconds` | Gauge | Thời điểm snapshot registry gần nhất |

Không nên gắn Pod UID hoặc instance ID vào mọi metric tổng hợp vì cardinality cao. Dùng log/event hoặc tracing để điều tra một lần scale cụ thể.

### 9.1. PromQL so sánh desired và ready

~~~promql
service_replicas_desired - service_replicas_ready
~~~

Giá trị dương cho biết còn thiếu replica Ready so với desired. Metric cần có cùng label service/cluster để phép trừ ghép đúng series.

### 9.2. Chênh lệch giữa Ready và Healthy registration

~~~promql
service_replicas_ready
-
sum by (service, cluster) (
  service_registry_instances{status=~"UP|passing"}
)
~~~

Truy vấn này chỉ đúng nếu hai metric cùng scope, cùng label và cùng quy ước instance. Nếu registry gauge được scrape nhiều lần từ nhiều peer hoặc nhiều datacenter, cần loại trùng hoặc group đúng trước khi so sánh.

### 9.3. Thời gian hội tụ

Với histogram custom:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service) (
    rate(service_scale_convergence_seconds_bucket[30m])
  )
)
~~~

Định nghĩa histogram observation nhất quán: ví dụ scale-out ghi observation khi instance mới đã nhận traffic, scale-in ghi observation khi consumer không còn chọn instance cũ. Nếu gộp hai loại, thêm label operation với tập giá trị hữu hạn.

## 10. Quy trình xác minh sau mỗi lần scale

Dùng một quy trình cố định để không dừng ở trạng thái orchestrator báo thành công.

### 10.1. Kiểm tra desired và actual

Với Kubernetes:

~~~bash
kubectl get deployment inventory-service
kubectl get pods -l app=inventory-service -o wide
kubectl rollout status deployment/inventory-service
~~~

Xác minh `desired`, `readyReplicas` và `availableReplicas`. Nếu Pod không Ready, xem `kubectl describe pod` và log container trước khi điều tra registry.

### 10.2. Kiểm tra Service endpoints

~~~bash
kubectl get endpointslice -l kubernetes.io/service-name=inventory-service -o yaml
~~~

Xác minh Pod mới có endpoint Ready. Khi scale-in, xác minh Pod bị rút đã có condition terminating/not-ready và không còn được dùng cho traffic thông thường.

### 10.3. Kiểm tra registry

Eureka:

- Tìm service application và instance ID.
- Xem host, port và status.
- Xác minh registration mới xuất hiện hoặc registration cũ biến mất.
- Kiểm tra server peer replication và client fetch interval nếu các peer/consumer lệch nhau.

Consul:

- Truy vấn Catalog để xem registration còn tồn tại hay không.
- Truy vấn Health API để xem passing, warning hoặc critical.
- Dùng `?passing` để kiểm tra tập instance vượt qua mọi health check.
- Xác minh datacenter, namespace, partition và ACL giống nhau giữa các lần query.

### 10.4. Kiểm tra từ consumer

Gọi `DiscoveryClient.getInstances("inventory-service")` từ chính consumer hoặc expose một diagnostic endpoint nội bộ có bảo vệ. Sau đó quan sát danh sách candidate của LoadBalancer và instance ID được chọn.

Không chỉ kiểm tra từ một máy quản trị. DNS, ACL, cache, zone và network policy có thể khiến consumer khác nhìn thấy tập instance khác nhau.

### 10.5. Kiểm tra traffic thực tế

Gắn instance ID vào response header nội bộ hoặc log/trace, ví dụ:

~~~http
X-Served-By: inventory-7f8d9c
~~~

Sau scale-out, gửi đủ request để quan sát các instance mới có nhận traffic hay không. Sau scale-in, xác minh không còn request mới đến instance đã rút. Không dùng một request đơn lẻ để kết luận round-robin đã phân phối đều; thuật toán, connection reuse và số request đều ảnh hưởng quan sát.

## 11. Bảng chẩn đoán khi hội tụ không hoàn tất

| Hiện tượng | Lớp cần kiểm tra | Nguyên nhân thường gặp |
|---|---|---|
| Desired tăng nhưng Running không tăng | Orchestrator/scheduler | Thiếu tài nguyên, quota, image pull, scheduling constraint |
| Running tăng nhưng Ready không tăng | Ứng dụng/readiness | Startup chậm, dependency lỗi, probe path sai |
| Ready tăng nhưng registry không tăng | Registration lifecycle | Auto-registration tắt, ACL, sai hostname/port, lỗi kết nối registry |
| Registry có registration nhưng health không passing | Health check | Endpoint sai, network không tới được, app chưa sẵn sàng |
| Registry healthy nhưng consumer không thấy instance | DiscoveryClient | Cache chưa refresh, datacenter/namespace sai, ACL hoặc peer lag |
| DiscoveryClient thấy instance nhưng LoadBalancer không chọn | Supplier/filter | Cache cũ, zone/hint/health filter, candidate list rỗng |
| Consumer chọn instance mới nhưng request lỗi | Network/application | Advertised address sai, port chưa mở, TLS hoặc dependency lỗi |
| Scale-in xong nhưng consumer vẫn chọn instance cũ | Deregistration/cache | Registry chưa xóa, discovery snapshot cũ, LoadBalancer cache |
| Process dừng nhưng registration còn | Registry cleanup | Shutdown không graceful, lease chưa hết hạn, Consul critical entry chưa deregister |
| Request bị reset trong lúc scale-in | Drain/shutdown | TERM quá sớm, grace period ngắn, connection bị đóng khi request còn chạy |
| Replica dao động liên tục | Autoscaler | Metric nhiễu, thiếu stabilization, min/max hoặc scale policy chưa phù hợp |

## 12. Những sai lầm cần tránh

### 12.1. Chỉ kiểm tra Pod Running

Running không đồng nghĩa Ready, Healthy hoặc Discoverable. Chờ đủ điều kiện readiness trước khi xem scale-out hoàn tất.

### 12.2. Chỉ đợi registration xuất hiện

Registration có thể xuất hiện trước health check passing. Consumer có thể chọn instance quá sớm nếu filter không phù hợp. Kiểm tra cả status và traffic thành công.

### 12.3. Dùng lease timeout làm cơ chế scale-in chính

Lease timeout được thiết kế để xử lý instance mất heartbeat, không phải drain có chủ đích. Shutdown bình thường nên deregister hoặc chuyển trạng thái trước khi process kết thúc.

### 12.4. Giảm mọi interval để hội tụ nhanh

Giảm heartbeat, health-check interval, registry fetch interval và cache TTL cùng lúc có thể tăng tải, tạo false positive và làm khó chẩn đoán. Thay đổi từng lớp dựa trên số đo và thử nghiệm.

### 12.5. Quên cache phía consumer

Registry đã đúng nhưng DiscoveryClient hoặc LoadBalancer cache có thể còn dữ liệu cũ. Kiểm tra từng lớp và chọn TTL phù hợp; tránh double caching khi registry client đã có cache.

### 12.6. Dùng `sleep` thay cho xác minh

Một khoảng chờ cố định không chứng minh mọi consumer đã cập nhật. Hãy kiểm tra endpoint, candidate list và request metric; chỉ dùng delay như một phần của shutdown budget sau khi đã đo.

## 13. Kịch bản kiểm thử scale

Trước production, nên kiểm thử các tình huống sau:

| Kịch bản | Điều cần xác minh |
|---|---|
| Scale 3 → 5 | Hai instance mới Ready, registered, healthy, discoverable và nhận request |
| Scale 5 → 3 | Hai instance bị rút khỏi candidate list, không nhận request mới, drain xong |
| Pod startup chậm | Instance chưa Ready không nhận traffic |
| Readiness chuyển DOWN tạm thời | Endpoint bị loại khỏi traffic theo policy và được thêm lại khi Ready |
| Graceful shutdown | Registration/endpoint được rút trước khi process dừng |
| Abrupt kill | Lease/health check dọn stale instance theo timeout |
| Registry mất kết nối | Consumer xử lý snapshot cũ và recovery theo policy |
| Eureka peer chậm replication | Peer và consumer cuối cùng có cùng registry view |
| Consul check chậm hoặc critical | Catalog và Health API phản ánh đúng khác biệt |
| LoadBalancer cache còn entry cũ | Consumer ngừng chọn instance sau refresh/expiry |
| Autoscaler scale up/down liên tục | Stabilization hạn chế replica flapping |
| Request dài khi scale-in | Request hoàn tất trong termination grace period |

Ghi lại timestamp cho từng mốc. Không chỉ lưu kết quả PASS/FAIL; cần biết mất bao lâu từ desired change đến Ready, registry healthy, consumer discoverable và traffic thực tế.

## 14. Checklist vận hành

**Scale-out**

1. Kiểm tra quota và tài nguyên trước khi tăng desired replicas.
2. Xác nhận startup probe, readiness probe và Actuator readiness.
3. Đảm bảo registration chỉ được xem là đủ điều kiện khi instance thực sự phục vụ được.
4. Kiểm tra registry health và replication.
5. Kiểm tra DiscoveryClient và LoadBalancer candidate list.
6. Xác minh request thành công tới instance mới.

**Scale-in**

1. Chọn số replica cần giảm và xác định instance bị rút.
2. Đánh dấu instance terminating/not-ready hoặc OUT_OF_SERVICE.
3. Ngừng chọn instance cho request mới.
4. Chờ discovery và load balancer hội tụ.
5. Drain request đang chạy.
6. Deregister và dừng process theo graceful shutdown.
7. Xác minh registry không còn stale registration.

**Đo hội tụ**

1. Ghi thời điểm thay đổi desired replicas.
2. Ghi thời điểm replica Ready.
3. Ghi thời điểm registry healthy/removed.
4. Ghi thời điểm consumer thấy hoặc ngừng thấy instance.
5. Ghi thời điểm request đầu tiên thành công hoặc request cuối cùng hoàn tất.
6. Tính p50/p95/p99 và đặt SLO phù hợp.

## 15. Ghi nhớ

- Scale là thay đổi desired replicas; registry chỉ phản ánh instance được đăng ký, không trực tiếp tạo thêm process.
- Scale-out cần đi qua startup, readiness, registration, registry propagation, discovery refresh và LoadBalancer selection.
- Scale-in cần rút instance khỏi traffic, deregister, drain request đang chạy rồi mới dừng process.
- Kubernetes readiness điều khiển EndpointSlice nhưng không tự đồng bộ Eureka hoặc Consul registration.
- Spring Boot graceful shutdown cần có timeout phù hợp với request duration và termination grace period.
- Eureka heartbeat/lease, Consul health check/TTL và LoadBalancer cache tạo ra các mốc hội tụ khác nhau.
- Đừng dùng lease expiration thay cho graceful deregistration.
- Desired, Running, Ready, Registered, Healthy, Discoverable, Eligible và Serving là các con số khác nhau.
- Đo `T_serving` khi scale-out và `T_no_new_traffic`/`T_drain_complete` khi scale-in.
- Chỉ kết luận scale hoàn tất khi số lượng và traffic ở các lớp đã hội tụ theo SLO.

Mở rộng hoặc thu hẹp replica là một quy trình phối hợp giữa orchestrator, ứng dụng, registry, discovery client và data plane. Khi mỗi lớp có tín hiệu readiness, deregistration và thời hạn riêng, đồng thời được kiểm tra bằng timestamp và traffic thực tế, hệ thống có thể scale mà không gửi request đến instance chưa sẵn sàng hoặc đã dừng.

## Tài liệu tham khảo

- [Kubernetes — Deployments and Rolling Updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/workloads/pods/probes/)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes — EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Cloud Netflix — Eureka Client Registration and Discovery](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Netflix — Configuration Properties](https://docs.spring.io/spring-cloud-netflix/reference/configprops.html)
- [Spring Cloud Consul — Service Discovery and Health Checks](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Commons — LoadBalancer Caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)

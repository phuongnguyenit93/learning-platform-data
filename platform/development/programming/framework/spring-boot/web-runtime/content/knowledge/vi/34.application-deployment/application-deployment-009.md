# Thời hạn dừng tiến trình và thời gian rút lưu lượng khỏi cân bằng tải trong Spring Boot

Khi triển khai Spring Boot bằng rolling update, một Pod cũ có thể ngừng nhận kết nối quá sớm trong khi Ingress hoặc external load balancer vẫn định tuyến request đến nó. Kết quả là người dùng thấy **502, 503, 504, connection refused hoặc connection reset** ngay cả khi ứng dụng hoạt động bình thường trước và sau khi deploy. Ngược lại, giữ tiến trình sống quá lâu có thể trì hoãn rollout hoặc buộc Kubernetes dùng SIGKILL khi hết thời hạn. Cần phân biệt hai nhóm thời gian không do cùng một hệ thống kiểm soát:

- **Thời hạn dừng tiến trình:** từ khi bắt đầu chấm dứt Pod/container/process tới khi JVM thoát. Trong Kubernetes, thời hạn này chịu giới hạn bởi **terminationGracePeriodSeconds**, gồm thời gian **preStop**, xử lý **SIGTERM**, **graceful HTTP shutdown**, dọn tài nguyên và mọi overhead.
- **Thời gian rút lưu lượng:** khoảng các thành phần **EndpointSlice, Service, kube-proxy, Ingress, service mesh, cloud load balancer và clients** cập nhật trạng thái backend, ngừng gửi request mới và cho request/kết nối cũ kết thúc. Mỗi tầng có **propagation delay** và có thể có **deregistration delay/connection draining** riêng.

Bài thuộc **Spring Boot - web-runtime → Triển khai ứng dụng**, với chủ đề trực tiếp **Thời hạn dừng tiến trình và thời gian rút lưu lượng khỏi cân bằng tải**. Ví dụ dùng **Java 17, Spring Boot 3.3.13, Spring MVC, embedded Tomcat, Spring Boot Actuator, Maven và Kubernetes**. Các phần về AWS ALB, HTTP/2, gRPC và WebSocket có phạm vi rõ, không giả định mọi triển khai dùng cùng load balancer. Các thời hạn ví dụ là số minh họa, **không phải giá trị tối ưu chung**.

## 1. Mục tiêu học tập

Sau bài này bạn có thể:

1. Mô tả vòng đời **Pod termination**, preStop, SIGTERM, SIGKILL và process exit.
2. Phân biệt **ReadinessState, HTTP /readyz, Pod Ready, EndpointSlice ready/serving/terminating, LB target draining**.
3. Hiểu vì sao **preStop sử dụng một phần terminationGracePeriodSeconds**, không kéo dài deadline thêm.
4. Giải thích Boot **server.shutdown=graceful** và **spring.lifecycle.timeout-per-shutdown-phase**; biết thời gian của Boot không thay thế hard deadline ở Kubernetes.
5. Lập bảng những **clock/timeout riêng**: client timeout, proxy timeout, LB deregistration, web request drain, background work và container termination.
6. Xác định khoảng đợi **traffic withdrawal** bằng đo thực tế thay vì lấy một sleep ngẫu nhiên.
7. Thiết kế rollout cho **REST ngắn, long requests, HTTP/1.1 keep-alive, HTTP/2, SSE, WebSocket và gRPC**.
8. Cấu hình Actuator health probes **/livez và /readyz trên main web server port**.
9. Chạy project Java 17/Spring Boot và test HTTP thật với **@SpringBootTest(RANDOM_PORT)**.
10. Thử **SIGTERM có request đang chạy**, xem in-flight completion và process exit.
11. Hiểu tác động của **Deployment RollingUpdate, maxSurge, maxUnavailable, minReadySeconds, capacity và PodDisruptionBudget**.
12. Thu thập timeline từ app, Kubernetes, Ingress và external load balancer để giải thích 5xx trong rollout.

Nền tảng cần biết: HTTP status, Java, Spring Boot, Servlet/Tomcat, Kubernetes Pod/Service/Deployment và cách đọc application logs.

## 2. Định nghĩa các thời gian hay bị nhầm

### 2.1. Thời gian rút backend khỏi routing

**Traffic withdrawal delay** là khoảng từ lúc có sự kiện yêu cầu loại instance khỏi tuyến thông thường đến lúc các route-making components **thực sự ngừng chọn** instance đó cho request mới. Nó có thể gồm Kubernetes API event propagation, EndpointSlice watchers, proxy worker updates, cloud target registration controller và connection reuse.

Một proxy đã cập nhật endpoint list vẫn có thể xử lý **request đang in-flight** trên backend cũ; việc kết nối cũ còn sống không nhất thiết có nghĩa proxy vẫn chọn backend cho request mới. Hãy phân biệt:
- **Không tạo routing mới** đến backend.
- **Cho request đã gửi tiếp tục hoàn tất**.
- **Cho TCP/HTTP keep-alive connection cũ tồn tại**.
- **Đóng/force terminate connection** khi hết drain deadline.

### 2.2. Thời gian dừng process

**Process termination duration** gồm những việc trong JVM/container:
- nhận SIGTERM;
- Spring Boot đóng ApplicationContext;
- web server ngừng nhận request mới;
- chờ request đang chạy theo thời gian cho phép;
- dừng background producers/executors;
- đóng DB/HTTP pools và files;
- process thoát.

Kubernetes đặt một **Pod-level limit** cho toàn bộ quá trình gồm cả preStop. Nếu quá hạn, có thể **SIGKILL**. JVM không tự thương lượng thêm thời gian với kubelet chỉ vì đang có request chưa xong.

### 2.3. Những “đồng hồ” độc lập

| Đồng hồ | Ai quyết định | Ý nghĩa |
| --- | --- | --- |
| terminationGracePeriodSeconds | Kubernetes Pod spec/kubelet | Hard shutdown budget của Pod. |
| preStop duration | Pod lifecycle hook | Khoảng chạy hook, nằm **trong** Pod grace period. |
| Boot graceful timeout | Spring lifecycle | Thời gian chờ của từng SmartLifecycle shutdown phase. |
| Application cleanup duration | Spring beans và libraries | Đóng pools/executors/files; có thể có deadlines riêng. |
| EndpointSlice update latency | Kubernetes controllers/watchers | Đưa endpoint state vào Kubernetes API và consumers. |
| Ingress/LB routing propagation | Ingress/mesh/cloud LB | Thời gian chuyển request mới khỏi old backend. |
| LB deregistration delay | External LB/provider target group | Thời gian draining targets/connections; độc lập Pod deadline. |
| Client/request timeout | Client/gateway/proxy/server | Khi caller thôi chờ response. |
| Stream/session lifetime | HTTP/2, WebSocket, gRPC, SSE | Có thể dài hơn nhiều so với Pod grace. |

Không cộng tất cả vào một phép tính thô vì có những việc chạy **song song** và có những deadline nằm ở hệ thống độc lập. Nhưng nếu hai timeout có thể cắt lẫn nhau, phải xác định **timeout nào sẽ hết trước trong đường request thực tế**.

## 3. Timeline: Kubernetes Pod termination và load balancer

~~~text
t0: Pod có deletionTimestamp, bắt đầu grace period
 |
 +-- EndpointSlice controllers/watchers nhận cập nhật
 |      +-- ready=false / terminating=true
 |      +-- kube-proxy, ingress, mesh, LB cập nhật route
 |
 +-- preStop hook (nếu khai báo)
 |      +-- JVM thường vẫn đang nhận request
 |      +-- hook này tiêu thời gian trong grace budget
 |
 +-- kubelet yêu cầu runtime gửi SIGTERM
 |      +-- Spring ApplicationContext bắt đầu close
 |      +-- Boot graceful web server stop
 |      +-- chờ in-flight requests
 |      +-- resource cleanup
 |
 +-- JVM exits
 |
t0 + terminationGracePeriodSeconds:
 nếu còn process, kubelet có thể yêu cầu SIGKILL
~~~

Đây là một sơ đồ tổng quát. **EndpointSlice propagation và preStop không bắt buộc tuần tự.** Đường Ingress có thể còn stale khi SIGTERM tới; vì thế trong rollout nhạy cảm, có lý do dành một **preStop buffer** hoặc phối hợp với LB controller. Nhưng preStop cố định không tự bảo đảm tất cả backends ở mọi vùng/mọi proxies đều cập nhật.

### 3.1. Bắt đầu countdown trước preStop

Nếu terminationGracePeriodSeconds=45 và preStop=10 giây, Java **không có thêm 45 giây sau preStop**. Trong giả định không có overhead, chỉ còn 35 giây. Kubelet có một số hành vi gia hạn ngắn nếu preStop vẫn chạy khi grace period hết trong một số trường hợp, nhưng **không dùng phần gia hạn làm cơ sở thiết kế**.

Đừng đặt preStop sleep=30 và terminationGracePeriodSeconds=30 rồi mong Boot có 20 giây graceful. Thời gian thực có thể hết trước khi process nhận SIGTERM.

### 3.2. SIGTERM và SIGKILL

- **SIGTERM** yêu cầu process dừng bình thường; Java/Spring có cơ hội chạy shutdown hooks và bean destroy.
- **SIGKILL** dừng cưỡng bức: không @PreDestroy, không hoàn tất transaction/file flush theo ý muốn.
- **Exit 143** thường gắn signal 15 theo Unix conventions, **exit 137** thường gắn signal 9; nhưng cần xem Pod status và reason, đặc biệt OOMKilled, để biết nguyên nhân thực.
- **Readiness probe fail** chỉ làm Pod unready theo cơ chế routing thông thường, **không tự kích hoạt restart** như liveness/startup probe fail.

### 3.3. PID 1 phải nhận đúng signal

Dockerfile nên dùng exec-form:

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/traffic-drain-demo-0.0.1-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Nếu dùng shell-form ENTRYPOINT chạy qua shell không forward SIGTERM, Java có thể không nhận cơ hội graceful shutdown. Nếu cần wrapper, dùng **exec java -jar /app/app.jar** để tiến trình Java thay shell. Kubernetes, container runtime và shell behavior phải được kiểm tra trên image thật.

## 4. EndpointSlice ready, serving và terminating

### 4.1. Readiness của Pod không đồng nghĩa Pod đã biến mất

Kubernetes EndpointSlice có các điều kiện quan trọng:
- **ready**: endpoint sẵn sàng cho routing thông thường.
- **terminating**: endpoint thuộc Pod đang chấm dứt.
- **serving**: trạng thái phục vụ có thể được dùng để quyết định việc drain trên endpoint terminating.

Với Kubernetes hiện đại, endpoint của Pod đang terminating có **ready=false** để tương thích với consumers cũ, trong khi **serving có thể còn true**. Đây không phải mâu thuẫn: Service không dùng nó cho regular new traffic, nhưng consumer hiểu draining có thể dùng serving để biết endpoint đang xử lý kết nối cũ.

~~~json
{
  "addresses": ["10.0.0.42"],
  "conditions": {
    "ready": false,
    "serving": true,
    "terminating": true
  }
}
~~~

Đây chỉ là JSON rút gọn minh họa một endpoint. **Ngoại lệ:** Service cấu hình **publishNotReadyAddresses=true** có semantics đặc biệt của ready; không áp dụng suy luận luôn false cho trường hợp này.

### 4.2. Đừng đợi readinessProbe kỳ sau mới thấy terminating

Kubernetes có thể cập nhật EndpointSlice khi Pod deletion được ghi nhận **mà không chờ** readinessProbe fail. Vì vậy nói “periodSeconds=5, failureThreshold=3 nên mất tối thiểu 15 giây để loại Pod” là sai khi xét con đường **Pod termination**. Readiness probe sampling đặc biệt quan trọng cho trạng thái không ready lúc application đang hoạt động, còn Pod deletion có endpoint termination flow riêng.

### 4.3. Rút backend không xảy ra đồng thời mọi nơi

Các consumers của EndpointSlice (kube-proxy, Ingress, controllers) nhận thông tin và cập nhật data plane với độ trễ thực tế. Client còn có thể giữ HTTP/2 hoặc keep-alive connection. **Không thể chứng minh backend hết nhận request chỉ bằng nhìn EndpointSlice ready=false tại một thời điểm**.

### 4.4. Quan sát bằng kubectl

~~~bash
kubectl get endpointslices \
  -l kubernetes.io/service-name=traffic-drain-demo \
  -o yaml

kubectl get pods -l app=traffic-drain-demo -w
kubectl describe pod POD_NAME
~~~

Thay POD_NAME bằng tên thực tế. Dùng timestamped logs/API watches để xây timeline giữa ready/serving/terminating và request cuối được Ingress gửi tới Pod cũ. Pod đã xóa có thể không còn xem được bằng kubectl; cần tập trung log và lưu sự kiện trước rollout.

## 5. Các tầng load balancer có thể nằm trên đường request

~~~text
Browser/client
       |
       v
Cloud external LB / CDN
       |
       v
Ingress Controller / API Gateway / Service Mesh
       |
       v
Kubernetes Service / kube-proxy or eBPF data plane
       |
       v
PodIP:8080 -> Spring Boot Tomcat
~~~

Một số kiến trúc dùng external LB trực tiếp tới Pod IP, một số có NodePort, một số có Envoy sidecar, một số không có Ingress. Do vậy **không áp dụng một drain timeout cho mọi hệ thống**.

### 5.1. Kubernetes Service và data plane

Service selector chọn Pods qua EndpointSlices. Khi ready=false, regular traffic nên được loại khỏi backends. Nhưng data plane cần nhận và áp dụng cập nhật. Một số in-flight requests vẫn đang chạy trên backend đã bị loại khỏi lựa chọn cho request mới. Đo **routing propagation delay**, không chỉ check readiness endpoint.

### 5.2. Ingress và service mesh

Ingress có thể duy trì upstream connection pool và cache route config. Trong khi thay đổi backends:
- có thể ngừng chọn backend cũ;
- có thể giữ in-flight requests;
- có thể đóng connections cũ hoặc chờ timeout;
- có thể retry GET nếu upstream reset;
- có thể sinh 502/503 khi backend mất và không còn endpoint khác.

Với POST có side effect, **retry tự động không có idempotency key** có thể gây duplicate order/payment. Không tăng retry count theo phản xạ chỉ vì rollout có connection resets.

### 5.3. AWS Application Load Balancer

AWS ALB target group có **deregistration delay**; tài liệu AWS ghi **mặc định 300 giây** trong trường hợp chưa thay đổi thuộc tính target group. Khi target deregister, state có thể là **draining**, rồi unused khi hoàn tất.

**300 giây của ALB không kéo dài 45 giây terminationGracePeriodSeconds của Pod.** Nếu kubelet SIGKILL ở giây 45, LB không thể giữ một JVM đã chết tiếp tục trả response. Đồng thời, một target hết in-flight requests có thể hoàn tất draining sớm, không nhất thiết chờ đủ toàn bộ 300 giây.

Deregistration delay của AWS ALB **khác** AWS Network Load Balancer; NLB còn có chính sách xử lý existing TCP connections và connection termination riêng. Xác minh đúng LB type/provider và version trước khi áp dụng setting cụ thể.

### 5.4. Tại sao LB vẫn có thể gửi request sau EndpointSlice update?

Có thể do:
- controller chưa xử lý Kubernetes event;
- external LB API target update còn pending;
- ingress workers chưa nhận config;
- connection reuse/HTTP/2 streams tiếp tục;
- client đang gọi direct Pod IP hoặc node endpoint;
- mạng/proxy có propagation delays.

Không nhầm “request vẫn hoàn tất trên backend cũ” với “LB vẫn chọn backend cũ cho request mới”: để phân biệt, cần log route-selection hoặc target state ở proxy layer.

## 6. Spring Boot 3.3 graceful shutdown

### 6.1. Cấu hình rõ ràng

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Với Boot 3.3, graceful shutdown hỗ trợ **Tomcat, Jetty, Reactor Netty và Undertow**. Nó xảy ra khi ApplicationContext đóng, ở phase sớm của **SmartLifecycle** stop. Tomcat, Jetty và Reactor Netty thường ngừng tiếp nhận requests mới ở network layer; Undertow có thể trả 503 ngay cho request mới.

**Không suy ra toàn bộ process chắc chắn exit trong 20 giây.** Timeout-per-shutdown-phase đặt giới hạn chờ từng SmartLifecycle phase, nhưng có thể còn phases khác và cleanup từ @PreDestroy, close DB pools, executors, client resources. Trong deployment phải đo **SIGTERM → process exit** thực tế.

### 6.2. Nếu load balancer chưa kịp rút Pod

Khi JVM nhận SIGTERM, Tomcat bắt đầu graceful shutdown và có thể không nhận request mới. Nếu Ingress vẫn route new request tới Pod đó, người dùng có thể gặp connection refused/502 dù in-flight requests cũ vẫn được xử lý. Vì vậy **thời gian rút traffic** cần xảy ra kịp **trước** thời điểm backend ngừng tiếp nhận kết nối mới với mức tin cậy phù hợp SLO.

### 6.3. Readiness và ApplicationAvailability

Spring Boot có:
- **LivenessState.CORRECT/BROKEN**.
- **ReadinessState.ACCEPTING_TRAFFIC/REFUSING_TRAFFIC**.
- **ApplicationAvailability** để đọc state.
- **AvailabilityChangeEvent.publish** để thông báo đổi state khi cần.

Trong shutdown, Boot có thể chuyển readiness sang REFUSING_TRAFFIC. Nhưng **đổi readiness chỉ là tín hiệu**: nó không tự đóng socket, không buộc Ingress đã cập nhật, và không chặn direct Pod IP requests. HTTP request mới bị ngừng bởi **web server graceful shutdown** hoặc network/proxy decision, chứ không phải chỉ bởi enum.

### 6.4. Actuator /livez và /readyz trên main port

Cấu hình:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
~~~

Boot 3.3 expose:
- /actuator/health/liveness
- /actuator/health/readiness
- **/livez** trên main server port
- **/readyz** trên main server port

Nếu management.server.port khác server.port, health endpoint ở management connector có thể vẫn UP khi main HTTP connector hỏng. Vì vậy dùng additional paths trên main port là cách kiểm tra sát đường web traffic hơn. Không đưa shared DB/external dependency vào liveness vì restart nhiều Pods thường không khắc phục upstream outage.

## 7. Tính ngân sách thời gian

### 7.1. Ký hiệu

| Ký hiệu | Đại lượng |
| --- | --- |
| G | terminationGracePeriodSeconds của Pod. |
| P | preStop hook duration. |
| L | routing propagation từ Pod termination/EndpointSlice tới khi proxy ngừng chọn backend. |
| R | thời gian còn lại để request HTTP in-flight hoàn tất sau SIGTERM. |
| A | background work drain, bean destruction, pool/file cleanup. |
| M | margin dự phòng scheduling, GC, network jitter, sidecars. |
| D | LB deregistration/connection draining timeout độc lập, nếu có. |

Một **ngân sách bảo thủ** có thể dùng:

~~~text
G > P + R + A + M

Nếu sử dụng preStop để chờ propagation:
P nên đủ cho L ở mức percentile phù hợp + buffer.

L và P có thể song song.
D là timeout phía LB, không tự gia hạn G.
~~~

Các đại lượng cần đo bằng timestamps. Nếu có nhiều SmartLifecycle phases, hoặc preStop/sidecar teardown khác, chúng cũng chiếm thời gian và phải được cộng vào budget. Không có phép tính một dòng đảm bảo 0 lỗi ở mọi hệ thống.

### 7.2. Ví dụ số

Giả sử staging đo:
- L_p99 khoảng 7 giây.
- P = 10 giây, để che propagation với buffer.
- Request drain budget R = 18 giây.
- Cleanup A = 4 giây.
- Margin M = 8 giây.

~~~text
P + R + A + M
= 10 + 18 + 4 + 8
= 40 giây

Có thể thử G = 45 giây trong lab.
Boot graceful phase timeout = 20s.
~~~

**Không chọn G=45 chỉ vì công thức mẫu.** Nếu request dài 35 giây, external proxy rút backend p99 20 giây hoặc @PreDestroy block thêm 15 giây, G có thể không đủ. Nếu client timeout 3 giây, tăng G lên 60 cũng không cứu client đang chờ 30 giây.

### 7.3. Timeline ví dụ

~~~text
t= 0s Pod terminating, grace countdown G=45s
t= 0s EndpointSlice/Ingress/LB đồng thời cập nhật
t= 0..10s preStop; JVM còn phục vụ request trong buffer
t=10s SIGTERM tới Java
t=10..28s Boot chờ in-flight HTTP requests
t=28..32s app cleanup
t=32s JVM exit
t=45s hard deadline nếu JVM còn sống
~~~

Không coi timestamps này là một behavior guarantee; các bước có thể ngắn hơn, dài hơn hoặc overlap. Nó chỉ minh họa vì sao **preStop không phải thời gian cộng thêm sau G**, và vì sao phải dành budget cho shutdown sau SIGTERM.

### 7.4. preStop sleep: lợi ích và giới hạn

preStop sleep có thể giúp data plane hoàn thành update trước khi Tomcat đóng connector, nhưng:
- không xác nhận LB đã loại backend;
- không đảm bảo không còn traffic;
- không hủy/hoàn thành WebSocket, gRPC streams;
- tiêu thụ trực tiếp Pod grace budget;
- có thể không chạy nếu image thiếu shell/sleep;
- không hoạt động như service deregistration cho mọi cloud target controller.

Tốt hơn là dùng cơ chế drain/ack của ingress/LB khi có, hoặc đo propagation đủ nhiều lần rồi chọn **một buffer có căn cứ**. Không dùng một sleep số đẹp cho toàn bộ tổ chức nếu các apps có traffic và LB path khác nhau.

## 8. Những loại HTTP request cần xử lý khác nhau

### 8.1. REST request ngắn

Với REST GET/POST trả nhanh, web graceful shutdown có thể chờ các request đã được Tomcat nhận. Cần đặt client/proxy/server timeouts khớp với request duration hợp lệ. Trong lúc server đã ngừng accept nhưng proxy còn stale, request mới có thể lỗi; đó là khoảng preStop/LB withdrawal cần tối ưu.

### 8.2. HTTP/1.1 keep-alive

Client hoặc proxy có thể tái sử dụng TCP connection. Không nên nghĩ mỗi request tạo connection mới. Khi backend draining, proxy behavior với keep-alive cũ có thể khác việc chọn backend cho connection mới. Hãy test connection reuse, không chỉ curl mỗi request một kết nối.

### 8.3. HTTP/2 và gRPC

HTTP/2 multiplex nhiều streams trên một connection; gRPC unary calls và long-lived streaming RPC có deadline/cancellation khác nhau. GOAWAY/drain semantics tùy server/proxy implementation, không được khẳng định mọi runtime luôn có cùng GOAWAY behavior. Cần test real client, gateway, library versions và deadline/reconnect.

### 8.4. SSE và WebSocket

SSE/WebSocket có thể mở trong hàng giờ. Không có terminationGracePeriodSeconds hợp lý nào chờ mọi session đóng tự nhiên. Cần:
- thông báo server sắp drain;
- ngừng chấp nhận session mới;
- close kết nối và cho client reconnect;
- resume token/last event ID nếu cần;
- đảm bảo trạng thái được persist trước shutdown;
- giới hạn thời gian close handshake.

### 8.5. HTTP 202 detached jobs

Nếu REST endpoint trả 202 và executor vẫn xử lý một tác vụ dài, web graceful shutdown không tự theo dõi tác vụ đó vì HTTP request đã hoàn tất. Phải có durable queue/job state, stop intake, checkpoint, retry idempotency hoặc worker handoff. Không dùng G vô hạn để thay job orchestration.

## 9. Demo runnable: Spring Boot 3.3 Java 17

Demo cung cấp:
- **GET /demo/work?delayMs=1000**: xử lý HTTP request có delay giới hạn.
- **GET /demo/state**: ApplicationAvailability và số request demo đang in-flight.
- **/livez và /readyz** trên main Tomcat port qua Actuator.
- **ContextClosedEvent log** và @PreDestroy log để quan sát lifecycle.
- **JUnit HTTP tests** cho 200, 400, readiness 503 và liveness 200.
- Shell script process-level để SIGTERM trong lúc request còn xử lý.

### 9.1. Cây thư mục

~~~text
traffic-drain-demo/
  pom.xml
  Dockerfile
  src/main/java/com/example/drain/
    DrainApplication.java
    WorkController.java
    ShutdownTimeline.java
  src/main/resources/application.yml
  src/test/java/com/example/drain/
    DrainHttpIntegrationTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>traffic-drain-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.3.13 là phiên bản mốc trong lab, không phải đảm bảo đây là bản còn được bảo trì khi triển khai production. Với dự án mới, chọn Spring Boot release được hỗ trợ và bảo mật cập nhật.

### 9.3. DrainApplication.java

~~~java
package com.example.drain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DrainApplication {
    public static void main(String[] args) {
        SpringApplication.run(DrainApplication.class, args);
    }
}
~~~

### 9.4. WorkController.java

~~~java
package com.example.drain;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.availability.ApplicationAvailability;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
public class WorkController {

    private static final Logger log =
            LoggerFactory.getLogger(WorkController.class);

    private final AtomicInteger inFlight = new AtomicInteger();
    private final ApplicationAvailability availability;

    public WorkController(ApplicationAvailability availability) {
        this.availability = availability;
    }

    @GetMapping("/demo/work")
    public Map<String, Object> work(
            @RequestParam(defaultValue = "1200") long delayMs)
            throws InterruptedException {

        if (delayMs < 0 || delayMs > 15000) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "delayMs must be 0..15000");
        }

        int active = inFlight.incrementAndGet();
        long start = System.nanoTime();
        log.info("request-start active={} delayMs={}",
                active, delayMs);

        try {
            // Chỉ mô phỏng request chậm, không benchmark.
            Thread.sleep(delayMs);
            long elapsed =
                    (System.nanoTime() - start) / 1_000_000;

            return Map.of(
                    "status", "completed",
                    "delayMs", delayMs,
                    "elapsedMs", elapsed);
        }
        finally {
            int remaining = inFlight.decrementAndGet();
            log.info("request-end remaining={}", remaining);
        }
    }

    @GetMapping("/demo/state")
    public Map<String, Object> state() {
        return Map.of(
                "readiness",
                availability.getReadinessState().name(),
                "liveness",
                availability.getLivenessState().name(),
                "inFlightDemoRequests",
                inFlight.get());
    }
}
~~~

**Giải thích:**
- AtomicInteger chỉ đo endpoint demo, không phải toàn bộ Tomcat active requests.
- delayMs có upper bound 15 giây; tránh tạo endpoint ngủ vô hạn trong lab.
- Sleep dùng blocking style của Servlet worker, chỉ để giữ request in-flight khi nhận SIGTERM.
- finally giảm bộ đếm ngay cả khi bị InterruptedException; không tự hứa request sẽ thành công khi force kill.
- ReadinessState ở /demo/state là tín hiệu routing. Trạng thái REFUSING_TRAFFIC không tự làm method trả 503 nếu gọi trực tiếp trước khi connector dừng.
- **Không expose demo delay endpoint trên public production ingress**; nó có thể bị lạm dụng gây cạn request threads.

### 9.5. ShutdownTimeline.java

~~~java
package com.example.drain;

import jakarta.annotation.PreDestroy;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class ShutdownTimeline {

    private static final Logger log =
            LoggerFactory.getLogger(ShutdownTimeline.class);

    @EventListener
    public void contextClosing(ContextClosedEvent event) {
        log.info("event=context-close-requested");
    }

    @PreDestroy
    public void destroyed() {
        log.info("event=timeline-bean-destroyed");
    }
}
~~~

ContextClosedEvent xảy ra khi context bắt đầu đóng, không bảo đảm mọi HTTP request đã hoàn tất lúc log đầu tiên xuất hiện. @PreDestroy chỉ là một bean callback. Hai markers này giúp so timestamps, **không chứng minh external LB đã hoàn tất drain**.

### 9.6. application.yml

~~~yaml
spring:
  application:
    name: traffic-drain-demo
  lifecycle:
    timeout-per-shutdown-phase: 20s

server:
  port: 8080
  shutdown: graceful

management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
        add-additional-paths: true
~~~

Actuator /livez và /readyz nằm trên main web port. Nếu cấu hình management.server.port riêng sau này, cần kiểm tra health groups và main-port additional paths riêng. Không expose toàn bộ Actuator endpoints qua public network.

### 9.7. Dockerfile

~~~dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/traffic-drain-demo-0.0.1-SNAPSHOT.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Exec-form ENTRYPOINT giúp Java nhận signal của container runtime. Nếu lifecycle preStop dùng sh -c sleep, kiểm tra image thực tế có shell/sleep: nhiều distroless images không hỗ trợ. Không tự chuyển sang shell-form ENTRYPOINT chỉ để thêm sleep.

### 9.8. Build và chạy

Linux/macOS:

~~~bash
mvn clean package
java -jar target/traffic-drain-demo-0.0.1-SNAPSHOT.jar
~~~

Windows:

~~~text
mvn.cmd clean package
java -jar target/traffic-drain-demo-0.0.1-SNAPSHOT.jar
~~~

Terminal khác:

~~~bash
curl -i http://localhost:8080/demo/state
curl -i "http://localhost:8080/demo/work?delayMs=100"
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/livez
~~~

Khi app đã ready, /demo/state có cấu trúc:

~~~json
{
  "readiness": "ACCEPTING_TRAFFIC",
  "liveness": "CORRECT",
  "inFlightDemoRequests": 0
}
~~~

/readyz và /livez thường trả **HTTP 200**, JSON **{"status":"UP"}**. Gửi delayMs=20000 sẽ trả **400**. JSON property order hoặc HTTP Date/Server headers có thể khác giữa runs.

## 10. Test qua HTTP thật bằng RANDOM_PORT

Test MockMvc không thực sự mở Tomcat network connector nên không chứng minh behavior server thread/port hoặc SIGTERM. Test dưới đây dùng **@SpringBootTest(RANDOM_PORT)**, rồi một test quy trình process riêng cho shutdown.

### 10.1. DrainHttpIntegrationTest.java

~~~java
package com.example.drain;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.availability.AvailabilityChangeEvent;
import org.springframework.boot.availability.ReadinessState;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.context.ApplicationEventPublisher;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class DrainHttpIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    @Autowired
    ApplicationEventPublisher events;

    private String url(String path) {
        return "http://localhost:" + port + path;
    }

    private int status(String path) {
        return http.getForEntity(
                url(path), String.class)
                .getStatusCode().value();
    }

    @Test
    void readinessAndWorkUseRealHttp() {
        assertThat(status("/livez")).isEqualTo(200);
        assertThat(status("/readyz")).isEqualTo(200);
        assertThat(status("/demo/work?delayMs=30"))
                .isEqualTo(200);
        assertThat(status("/demo/work?delayMs=20000"))
                .isEqualTo(400);
    }

    @Test
    void refusingTrafficDoesNotBreakLiveness() {
        try {
            AvailabilityChangeEvent.publish(
                    events, this,
                    ReadinessState.REFUSING_TRAFFIC);

            assertThat(status("/readyz")).isEqualTo(503);
            assertThat(status("/livez")).isEqualTo(200);
            assertThat(http.getForObject(
                    url("/demo/state"), String.class))
                    .contains("REFUSING_TRAFFIC");
        }
        finally {
            AvailabilityChangeEvent.publish(
                    events, this,
                    ReadinessState.ACCEPTING_TRAFFIC);
        }
    }
}
~~~

**Test notes:**
- TestRestTemplate có thể trả status 503 để assert thay vì ném exception do error handler.
- AvailabilityChangeEvent.publish chuyển **readiness health group** sang OUT_OF_SERVICE/503, trong khi liveness vẫn CORRECT/200.
- Direct HTTP /demo/state còn hoạt động khi application chưa đóng connector, minh họa readiness chỉ là signal.
- Test dùng shared context với mutable availability; khi suite bật parallel test execution phải tách context hoặc đồng bộ để tránh race.
- Không dùng public /drain hoặc /control toggle endpoint chỉ để thao tác readiness production.
- Test này **không** kiểm tra LB propagation, preStop, SIGTERM hay process exit. Cần deployment test riêng.

Chạy:

~~~bash
mvn test
~~~

## 11. Thử SIGTERM khi request còn in-flight

Chạy tại Linux/macOS lab hoặc staging, **không chạy trên production**. Đảm bảo cổng 8080 rảnh:

~~~bash
java -jar target/traffic-drain-demo-0.0.1-SNAPSHOT.jar \
  > server.log 2>&1 &
APP_PID=$!

# Cần đợi /readyz 200 trước khi gửi request.
curl -fsS http://localhost:8080/readyz

# Request chậm được gửi trước SIGTERM.
curl -sS -o long-response.json \
  -w "HTTP=%{http_code} total=%{time_total}\n" \
  "http://localhost:8080/demo/work?delayMs=7000" &
REQ_PID=$!

sleep 1
kill -TERM "$APP_PID"

wait "$REQ_PID"
wait "$APP_PID"
~~~

**Điều quan sát cần ghi:**
1. Nếu request vào Tomcat trước SIGTERM và kết thúc trong graceful window, nó thường có cơ hội trả **HTTP 200**.
2. Request mới gửi **sau** khi connector bắt đầu đóng có thể gặp lỗi kết nối, tùy server/connection reuse.
3. Xem server.log các mốc context-close-requested, Tomcat graceful logs và timeline-bean-destroyed.
4. Đo thời gian từ SIGTERM đến process exit, không mặc định luôn bằng 20s.
5. Nếu request dài hơn graceful deadline hoặc process bị SIGKILL, có thể mất response.
6. Script giả định app đã ready; trong automated test phải retry /readyz có timeout thay vì gọi đúng một lần.
7. Windows Stop-Process không luôn tương đương SIGTERM theo POSIX; dùng Linux container phù hợp production để test signal semantics.

**Không tự kill -9 để “giúp” script kết thúc** nếu muốn đo graceful shutdown. Đối với hard-kill recovery, chạy một test riêng và ghi rõ đây là forced failure scenario.

## 12. Kubernetes Deployment và Service

### 12.1. Deployment mẫu

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: traffic-drain-demo
spec:
  replicas: 3
  minReadySeconds: 5
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: traffic-drain-demo
  template:
    metadata:
      labels:
        app: traffic-drain-demo
    spec:
      terminationGracePeriodSeconds: 45
      containers:
        - name: web
          image: registry.example.invalid/traffic-drain-demo:1.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 24
          livenessProbe:
            httpGet:
              path: /livez
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /readyz
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
            successThreshold: 1
          lifecycle:
            preStop:
              exec:
                command: ["sh", "-c", "sleep 10"]
~~~

**Đây là manifest minh họa.** Image ở registry.example.invalid không tồn tại; phải thay bằng registry và image thực tế. Image thực phải có sh và sleep để preStop thành công, hoặc dùng một hook mechanism thích hợp khác. Bổ sung resource requests/limits, securityContext, ServiceAccount, RBAC và network policies theo cluster.

**Tại sao chọn như vậy:**
- 3 replicas có khả năng duy trì capacity khi một Pod rời vòng phục vụ, nếu các replicas khác khỏe và đủ tải.
- **maxSurge: 1**, **maxUnavailable: 0** hướng rollout có Pod mới trước khi giảm Available replicas. Không tự đảm bảo zero downtime.
- **minReadySeconds: 5** yêu cầu Pod Ready liên tục trước khi coi là Available, nhưng không kiểm tra business SLO.
- **startupProbe** cho phép startup cần thời gian mà liveness không restart sớm.
- **readinessProbe** quyết định routing; liveness thất bại theo ngưỡng mới quyết định restart.
- **preStop sleep 10s** là buffer minh họa trước SIGTERM, không phải default đúng mọi hệ.
- **terminationGracePeriodSeconds: 45** gồm cả 10s preStop và phần shutdown/cleanup sau đó.
- Kubernetes có thể cập nhật terminating EndpointSlice không cần chờ readiness probe fail 2 lần; không suy luận withdrawal latency từ failureThreshold đơn lẻ.

### 12.2. Service

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: traffic-drain-demo
spec:
  selector:
    app: traffic-drain-demo
  ports:
    - name: http
      port: 80
      targetPort: http
  type: ClusterIP
~~~

Build image:

~~~bash
mvn clean package
docker build -t traffic-drain-demo:1.0 .
~~~

Image local tag không tự tồn tại ở registry.example.invalid; cần tag/push image thật trước khi deploy. Không triển khai YAML mẫu khi các giá trị image/namespace/quotas chưa được thay và kiểm chứng.

### 12.3. RollingUpdate không đảm bảo không lỗi

Ngay cả maxUnavailable=0 cũng không ngăn:
- Pod mới Ready quá sớm, cache chưa warm;
- LB vẫn route tới Pod cũ sau SIGTERM;
- cluster không đủ CPU/memory cho surge Pod;
- direct connections còn mở tới old Pod;
- network timeouts, DB bottlenecks;
- WebSocket/gRPC streaming vượt grace period.

**PodDisruptionBudget** áp dụng cho những voluntary disruptions theo eviction workflows, không phải một cơ chế thay thế hay tự bảo đảm behavior của mỗi Deployment rollout. Xác minh controller/version và capacity.

## 13. Đo rollout trên staging

### 13.1. Theo dõi resources

~~~bash
kubectl get deployments
kubectl get pods -l app=traffic-drain-demo -w
kubectl rollout status deployment/traffic-drain-demo
kubectl describe deployment traffic-drain-demo
kubectl get endpointslices \
  -l kubernetes.io/service-name=traffic-drain-demo \
  -o yaml
~~~

Xem Pod terminating và EndpointSlice conditions.ready/serving/terminating, kết hợp proxy logs. Không kết luận từ một lần kubectl get rằng ngay thời điểm đó LB đã đồng bộ.

### 13.2. Quan sát process exit và events

~~~bash
kubectl describe pod POD_NAME
kubectl logs POD_NAME -c web --timestamps
kubectl get pod POD_NAME -o yaml
~~~

POD_NAME cần được thay. Pod cũ có thể biến mất trước khi bạn truy vấn; nên dùng centralized logs và event capture trong staging. Xem terminated.reason, exitCode và OOMKilled, không suy luận mọi code 137 là grace timeout.

### 13.3. Lập bảng mốc thời gian

| Mốc | Định nghĩa | Nguồn quan sát |
| --- | --- | --- |
| t0 | Pod deletionTimestamp | K8s API/event. |
| t1 | EndpointSlice ready chuyển false | API watch. |
| t2 | Ingress/LB nhận backend update | Proxy/controller logs hoặc target state. |
| t3 | Last new request routed tới old Pod | Proxy route-selection/access logs. |
| t4 | preStop kết thúc và JVM nhận SIGTERM | Kubelet/runtime/application logs. |
| t5 | Spring web graceful phase kết thúc | Application logs/active requests. |
| t6 | Resource cleanup hoàn tất | App lifecycle logs. |
| t7 | Container process exited | Pod containerStatuses/runtime. |

Từ đó đo t1-t0, t2-t0, t4-t0, t5-t4 và t7-t0. **Last request timestamp t3** chỉ cho một ước lượng nếu có traffic được gửi đủ đều; nếu không có request mới, absence of logs **không chứng minh** LB ngừng routing đúng thời điểm.

### 13.4. Đo tail latency của withdrawal

Một rollout không lỗi chưa đủ để đặt sleep cố định. Lặp nhiều lần dưới tải có kiểm soát:
- nhiều đồng thời requests;
- HTTP keep-alive reuse;
- long requests;
- HTTP/2/gRPC nếu có;
- Pod CPU throttling hoặc GC pauses;
- Ingress reload;
- node drain;
- nhiều Pods cùng terminating.

Thu **p50/p95/p99 routing propagation**, 5xx và process exit time. Chọn ngân sách dựa trên percentile phù hợp SLO và thêm margin, không dựa vào average.

## 14. Readiness chủ động trước shutdown

### 14.1. ApplicationAvailability

Nếu bảo trì một instance trước khi Kubernetes xóa Pod, có thể phát trạng thái:

~~~java
AvailabilityChangeEvent.publish(
        eventPublisher,
        this,
        ReadinessState.REFUSING_TRAFFIC);
~~~

Đây là snippet cần ApplicationEventPublisher và imports Spring Boot availability. Khi readiness group thành OUT_OF_SERVICE, /readyz thường trả **503** nhưng /livez vẫn **200**. Tuy nhiên controller /demo/work vẫn có thể chạy khi gọi direct Pod IP trước khi connector bị đóng.

### 14.2. Không mở endpoint tự loại Pod khỏi traffic

Nếu expose public POST /drain mà không auth, bên ngoài có thể loại toàn bộ replicas khỏi Service bằng requests đơn giản. Nếu cần planned drain control plane, bảo vệ bằng mTLS/admin permissions/network policies/audit và tránh gọi hàng loạt lên mọi replica. Cần biết khi nào publish availability rồi chờ xác nhận route withdrawal trước SIGTERM.

### 14.3. Readiness không được dùng như liveness

Không đặt shared database hoặc remote API health vào liveness chỉ để Kubernetes restart cả fleet khi upstream gặp lỗi. Liveness là khả năng process tự hồi phục; readiness là khả năng instance nhận traffic ngay lúc đó. Tách chúng để tránh cascading restart.

## 15. Timeout qua nhiều lớp

### 15.1. Client và proxy deadline

Một request có thể bị cắt bởi:
- browser/HTTP client timeout;
- LB idle timeout;
- Ingress upstream read/connect timeout;
- service mesh drain timeout;
- Spring MVC async request timeout;
- transaction/DB timeout;
- Spring graceful shutdown phase;
- Kubernetes forced termination.

Tăng Pod grace period không tự sửa client timeout. Nếu proxy timeout 5 giây còn app work 15 giây, người dùng vẫn có thể nhận 504 dù JVM sống đủ 45 giây. Lập bảng per-hop timeout theo HTTP contract.

### 15.2. Retries an toàn

Nếu connection reset trong rollout, GET idempotent có thể retry trong budget phù hợp. Với POST tạo thanh toán/đơn hàng, server cũ có thể đã commit nhưng client mất response; retry mù quáng gây duplicate. Dùng **idempotency key, deduplication, transactional outbox hoặc reconciliation**.

### 15.3. Không dùng vô hạn timeout

Long-running requests cần upper bound và cancellation. Với SSE/WebSocket/gRPC, chọn drain/reconnect/resume thay vì đợi vô hạn. Background jobs kéo dài nên được persist và handoff, không kéo Kubernetes G vô hạn.

## 16. Troubleshooting lỗi deployment

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| 502 ngay lúc SIGTERM | Ingress còn route Pod cũ khi Tomcat ngừng accept | EndpointSlice, LB update latency, preStop buffer. |
| 504 khi request dài | Proxy/client timeout trước khi app xong | Per-hop timeout matrix và request duration. |
| Pod exit 137 | SIGKILL do grace hết hoặc OOMKilled | Pod reason/events, log thời gian. |
| Boot 20s nhưng Pod G 10s | Kubernetes hard deadline sớm hơn Boot phase | Tăng G có căn cứ/giảm drain. |
| preStop sleep 30s, G=30s | Không còn budget cho SIGTERM cleanup | Rút ngắn preStop hoặc tăng G. |
| /readyz 503 nhưng direct Pod IP vẫn 200 | Readiness chỉ là signal | Kiểm tra Service routing, không coi là firewall. |
| EndpointSlice ready=false nhưng ingress còn gửi | Data plane propagation/chưa đồng bộ | Controller logs, route-selection timestamps. |
| ALB vẫn draining khi Pod đã chết | LB delay không kéo dài Kubernetes Pod grace | Đồng bộ deadlines/target lifecycle. |
| WebSocket mất kết nối khi rollout | Stream không có drain/reconnect policy | Design reconnect/resume. |
| POST bị trùng sau proxy retries | Không có idempotency | Idempotency keys/dedup. |
| New Pod Ready nhưng user 5xx | Warmup không nằm trong readiness | Startup/ramp-up checks. |
| Surge Pod Pending | Cluster thiếu capacity | Resource quotas/autoscaler/placement. |
| Probe bị 401/403 | Spring Security/network chặn kubelet | Auth rules cho /livez,/readyz. |
| /livez 404 local | Actuator probes disabled | Probes.enabled và additional-paths. |
| preStop exec fail | Image thiếu sh/sleep hoặc command lỗi | Events/hook logs/image contents. |
| SIGTERM không tới JVM | PID1 shell không forward signal | Exec-form Dockerfile hoặc exec wrapper. |
| Graceful không chạy trong IDE | IDE gửi hard kill | Thử Linux process/container SIGTERM. |
| Failed rollout chỉ xảy ra đôi khi | Tail propagation/GC/jitter | Lặp staging với p99 metrics. |
| API response mất sau HTTP 202 | Detached job chưa persist | Durable queue/job ledger. |

## 17. Runbook xử lý rollout 5xx

1. Ghi thời gian rollout, first/last 5xx, request IDs, old/new Pod IDs và LB target states.
2. Phân biệt lỗi do **proxy** sinh hay do **application** trả; 502/503/504 có thể đến từ nhiều tầng.
3. Xem Ready/Available replicas và capacity; kiểm tra maxSurge/maxUnavailable.
4. Xem Pod deletionTimestamp, preStop duration, SIGTERM, Spring graceful logs, exit code.
5. Xem EndpointSlice ready/serving/terminating và thời gian controllers/data plane cập nhật.
6. Xem Ingress/LB access logs: request cuối được chọn tới backend cũ, active connections.
7. So sánh **P, L, R, A, G, D**, tìm sự kiện đến muộn hoặc deadline ngắn.
8. Kiểm tra long-lived HTTP/2/gRPC/WS/SSE connections và client retry.
9. Kiểm tra @Async/background jobs tách khỏi in-flight HTTP.
10. Thay một tham số theo dữ liệu đo, chạy lại staging rollout, so 5xx/p95/p99.
11. Nếu dữ liệu nhạy cảm/POST side effects, kiểm tra idempotency trước khi tăng retry.
12. Nếu incident nghiêm trọng, rollback để giữ capacity, không tắt readiness/liveness bừa bãi.

## 18. Bài tập

### Bài 1 — Hai đồng hồ
Vẽ timeline riêng cho Pod termination G và LB route withdrawal L. Dùng G=45s, P=10s, R=18s, A=4s, M=8s; tính margin và nêu vì sao D của AWS ALB không tự cộng vào G.

### Bài 2 — Readiness signal
Chạy HTTP tests, đổi readiness sang REFUSING_TRAFFIC, quan sát /readyz=503, /livez=200. Giải thích vì sao /demo/state vẫn có thể trả JSON qua direct HTTP.

### Bài 3 — SIGTERM khi có request
Gọi /demo/work?delayMs=7000, gửi SIGTERM sau 1 giây; quan sát response/client time, Tomcat logs, process exit. Thử lần khác với hard kill trong lab, so kết quả.

### Bài 4 — EndpointSlice
Quan sát ready/serving/terminating trong rolling update. Ghi timestamps EndpointSlice và Ingress last request to old Pod. Phân biệt endpoint API update và proxy data plane propagation.

### Bài 5 — preStop có giá trị không?
Ở staging, thử preStop=0,5,10 với G đủ lớn, ghi 502/503, p99 route latency và hard kills. Không kết luận từ một lần test.

### Bài 6 — AWS ALB
Xem deregistration delay thực của target group. Giải thích vì sao 300 giây LB default không làm Pod G=45 tự sống thêm. Thiết kế per-hop timeout matrix.

### Bài 7 — Streaming
Thêm SSE hoặc WebSocket, tạo stream dài hơn G. Thiết kế signal close, reconnection và resume token; không cố đợi kết thúc tự nhiên.

### Bài 8 — Rollout capacity
Với 3 replicas, maxSurge=1, maxUnavailable=0, giả sử Pod mới cần warmup 15 giây, Ingress propagation p99=8 giây, request p99=6 giây. Lập budget và kiểm tra có đủ cluster capacity tạo thêm replica.

## 19. Checklist vận hành

- [ ] Traffic path Client → LB → Ingress → Service → Pod đã được vẽ và xác minh.
- [ ] terminationGracePeriodSeconds gồm cả preStop, Boot drain, cleanup và margin.
- [ ] JVM PID1 nhận SIGTERM qua exec-form ENTRYPOINT hoặc signal forwarding chuẩn.
- [ ] server.shutdown=graceful khai báo tường minh cho Boot version.
- [ ] timeout-per-shutdown-phase không bị nhầm là hard total process limit.
- [ ] Health /livez và /readyz đo main port phù hợp, security không chặn kubelet.
- [ ] EndpointSlice ready/serving/terminating semantics được hiểu theo version.
- [ ] Ingress và external LB route withdrawal/deregistration đã đo ở staging.
- [ ] preStop buffer dựa trên observed propagation, không sleep tùy tiện.
- [ ] HTTP request duration/client/proxy timeouts không mâu thuẫn.
- [ ] HTTP/2, WebSocket, SSE, gRPC có drain/reconnect khi dùng.
- [ ] Background 202 jobs không dựa chỉ vào HTTP graceful.
- [ ] RollingUpdate có capacity và readiness warmup phù hợp.
- [ ] Không khai báo external dependency chung trong liveness gây restart storm.
- [ ] Không expose endpoint drain thủ công cho người dùng bên ngoài.
- [ ] Quan sát p95/p99 routing propagation, active requests, 5xx, exits.
- [ ] Đã test SIGTERM khi request còn chạy và full staging rollout.
- [ ] Có idempotency/retry policy cho non-idempotent calls.
- [ ] Có rollback/runbook khi hard kills hoặc 5xx tăng.

## 20. Câu hỏi tự kiểm tra

**1. Thời gian terminationGracePeriodSeconds bắt đầu trước hay sau preStop?** Trước; preStop tiêu thụ một phần budget.

**2. preStop sleep 10 giây có đảm bảo ingress hết route Pod cũ?** Không. Phụ thuộc propagation và controller/provider.

**3. EndpointSlice ready=false có nghĩa xóa ngay endpoint khỏi API?** Không; endpoint terminating có thể vẫn còn với serving=true để hỗ trợ drain.

**4. ReadinessState.REFUSING_TRAFFIC có chặn direct Pod IP?** Không. Nó là health/routing signal.

**5. server.shutdown=graceful có đảm bảo mọi request thành công?** Không; request timeout, client/proxy timeout và SIGKILL vẫn có thể xảy ra.

**6. Boot timeout-per-shutdown-phase=20s và G=15s, ai có thể kill tiến trình trước?** Kubelet khi G hết.

**7. AWS ALB deregistration delay=300s có kéo dài Pod grace từ 45 lên 300s?** Không.

**8. ReadinessProbe fail tự restart container?** Không, chỉ ảnh hưởng Ready/Service routing. Liveness/startup có semantics restart khác.

**9. maxUnavailable=0 có nghĩa tuyệt đối zero downtime?** Không, còn networking, readiness, capacity và long connections.

**10. Vì sao test MockMvc không đủ?** Không chạy Tomcat connector hay Pod termination, cần real HTTP/process/deployment tests.

**11. Làm sao đo chính xác việc LB ngừng chọn backend?** Kết hợp LB/proxy access logs, target state, EndpointSlice updates và controlled traffic, không chỉ xem app logs.

**12. Khi nào cần durable queue cho shutdown?** Khi HTTP 202 job phải tồn tại sau process exit/SIGKILL hoặc dài hơn grace window.

## 21. Tài liệu chính thức

1. [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): server.shutdown, SmartLifecycle stop phase và web server semantics.
2. [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): health, Kubernetes probes, additional paths và management port.
3. [Spring Boot 3.3 — SpringApplication Availability](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): liveness/readiness và AvailabilityChangeEvent.
4. [Kubernetes — Pod Lifecycle/Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#termination-of-pods): Pod grace, preStop, SIGTERM/SIGKILL.
5. [Kubernetes — Pods and Endpoints Termination Flow](https://kubernetes.io/docs/tutorials/services/pods-and-endpoint-termination-flow/): EndpointSlice ready/serving/terminating conditions.
6. [Kubernetes — Configure Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): liveness/readiness/startup probes.
7. [Kubernetes — Deployment Rolling Update](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-update-deployment): maxSurge, maxUnavailable, minReadySeconds.
8. [Kubernetes — EndpointSlices](https://kubernetes.io/docs/concepts/services-networking/endpoint-slices/): routing endpoint state.
9. [AWS ALB — Target Group Attributes](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-target-group-attributes.html): deregistration delay and draining.
10. [AWS ALB — Register/Deregister Targets](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/target-group-register-targets.html): connection draining.
11. [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @SpringBootTest RANDOM_PORT.

**Kết luận:** Triển khai Spring Boot an toàn đòi hỏi quản lý **hai đồng hồ độc lập nhưng liên quan**: thời hạn kubelet cho JVM thoát và thời gian các lớp load balancing ngừng gửi traffic đến instance cũ. Dùng **Actuator readiness**, **Spring Boot graceful shutdown**, **Kubernetes EndpointSlice termination signals**, preStop buffer khi có số đo, và một terminationGracePeriodSeconds đủ cho preStop + HTTP drain + cleanup. Sau đó kiểm chứng bằng **HTTP thật, SIGTERM thật và rolling updates ở staging** với keep-alive/streaming, đo p95/p99 thay vì đoán một con số sleep chung.
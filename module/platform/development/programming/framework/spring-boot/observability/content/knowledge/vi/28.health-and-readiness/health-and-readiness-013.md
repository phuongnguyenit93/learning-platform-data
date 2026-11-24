# Kubernetes probe trong Spring Boot

Kubernetes probe là cơ chế kubelet kiểm tra trạng thái container để quyết định khi nào ứng dụng đã khởi động, có cần restart hay có thể nhận traffic. Với Spring Boot, probe thường gọi các health groups của Actuator. Cấu hình sai có thể tạo restart loop, đưa pod chưa warm-up vào service endpoints hoặc giữ instance lỗi trong traffic quá lâu. Vì vậy cần chọn đúng loại probe, endpoint và ngưỡng thời gian theo lifecycle thực tế của ứng dụng.

Trong module **SPRING_BOOT_OBSERVABILITY**, Kubernetes probe thuộc chương **Health và readiness**, kết nối Actuator health, startup state, liveness/readiness, metrics, logs và tracing. Bài tập trung vào cách thiết kế startupProbe, livenessProbe và readinessProbe cho Spring Boot; chọn HTTP/TCP/exec/gRPC probe; cấu hình Actuator path/port/security; tính timeout và failure thresholds; phối hợp rollout, draining, kiểm thử và troubleshooting.

## Mục tiêu học tập

1. Phân biệt startupProbe, livenessProbe và readinessProbe.
2. Chọn probe mechanism phù hợp cho Spring Boot.
3. Cấu hình Actuator health groups và Kubernetes manifest.
4. Tính toán period, timeout, failure threshold và startup budget.
5. Tránh restart storm khi dependency bên ngoài gặp sự cố.
6. Xử lý management port riêng, security và network policy.
7. Phối hợp readiness với rolling update và graceful shutdown.
8. Kiểm thử probe behavior và điều tra trạng thái pod.

## 1. Kubernetes probe là gì?

Kubelet chạy probe định kỳ trên container. Kết quả probe ảnh hưởng tới trạng thái container và việc pod được đưa vào endpoints phục vụ traffic.

| Probe | Câu hỏi | Khi thất bại |
| --- | --- | --- |
| startupProbe | Ứng dụng đã hoàn tất giai đoạn khởi động chưa? | Sau ngưỡng thất bại, container bị restart |
| livenessProbe | Ứng dụng còn hoạt động và có thể tiếp tục không? | Container bị restart |
| readinessProbe | Instance có sẵn sàng nhận traffic không? | Pod bị đánh dấu not ready, không nhận traffic qua Service |

Không dùng ba probe thay thế lẫn nhau. Startup probe bảo vệ giai đoạn khởi động dài; liveness quyết định restart; readiness điều khiển traffic.

### 1.1. Quan hệ giữa probes

Khi startupProbe được cấu hình, Kubernetes chưa chạy liveness và readiness probes cho tới khi startup probe thành công. Sau đó liveness/readiness bắt đầu theo cấu hình riêng.

~~~mermaid
flowchart TD
    Start["Container starts"] --> Startup["startupProbe"]
    Startup -->|failure within budget| Startup
    Startup -->|success| Active["Normal probe phase"]
    Active --> Live["livenessProbe"]
    Active --> Ready["readinessProbe"]
    Live -->|failure threshold reached| Restart["Restart container"]
    Live -->|success| Running["Container continues"]
    Ready -->|success| Traffic["Pod can receive traffic"]
    Ready -->|failure| NoTraffic["Pod removed from ready endpoints"]
~~~

Readiness failure không tự restart container. Liveness failure mới kích hoạt restart. Startup probe failure sau budget cũng có thể dẫn tới restart.

### 1.2. Process running không đồng nghĩa ready

JVM có thể chạy, port đã listen và container state là Running, nhưng Spring context chưa hoàn tất, cache chưa warm hoặc dependency thiết yếu chưa sẵn sàng. Probe phải phản ánh trạng thái ứng dụng cần cho hành động tương ứng, không chỉ kiểm tra process tồn tại.

## 2. Spring Boot Actuator health groups

Thêm Actuator:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Bật Kubernetes probes cho health endpoint:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Spring Boot cung cấp các health groups với path phổ biến:

~~~text
/actuator/health/liveness
/actuator/health/readiness
~~~

Xác minh behavior theo Spring Boot version. Nếu dùng custom management base path hoặc port riêng, manifest phải khớp đường dẫn và port thực tế.

### 2.1. Liveness group

Liveness group nên phản ánh khả năng process/application tiếp tục hoạt động. Tránh đưa database, broker hoặc remote API vào liveness group nếu restart ứng dụng không thể khắc phục lỗi dependency. Một database outage chung có thể làm tất cả pods restart đồng thời và tăng áp lực reconnect.

### 2.2. Readiness group

Readiness group phản ánh instance có thể phục vụ traffic hay không. Có thể bao gồm dependency bắt buộc cho use case chính, startup readiness state hoặc custom indicator. Phân loại dependency optional/fallback trước khi đưa vào group; dependency phụ không nên làm toàn service ngừng nhận traffic nếu ứng dụng vẫn có degraded mode.

### 2.3. Startup state

Spring Boot application availability có LivenessState và ReadinessState. Trong startup, readiness thường ở REFUSING_TRAFFIC cho tới khi application ready. Nếu có warm-up bất đồng bộ sau lifecycle event, ứng dụng cần giữ readiness refusing tới khi critical warm-up hoàn tất.

Kubernetes startupProbe bổ sung thời gian cho process khởi động; nó không tự biết business warm-up đã xong nếu endpoint startup không phản ánh trạng thái đó.

## 3. Các loại probe mechanism

Kubernetes hỗ trợ nhiều cách kiểm tra:

| Mechanism | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| HTTP GET | Gửi HTTP request và đánh giá status code | Spring Boot Actuator health endpoint |
| TCP Socket | Kiểm tra port có accept connection | Chỉ cần biết socket mở |
| Exec | Chạy command bên trong container | Có check local chuyên biệt |
| gRPC | Gọi gRPC health checking protocol | Ứng dụng expose gRPC health service |

### 3.1. HTTP GET

Đây thường là lựa chọn phù hợp cho Spring Boot vì Actuator trả health status có semantics rõ. HTTP probe xem response code; 200–399 được xem là thành công, các response khác là thất bại. Đảm bảo DOWN/OUT_OF_SERVICE được ánh xạ thành response code phù hợp.

### 3.2. TCP socket

TCP probe chỉ chứng minh port có thể accept connection. Nó không chứng minh Spring context đã sẵn sàng, database hoạt động hay request handler có thể phục vụ. TCP probe có thể phù hợp cho startup sơ bộ hoặc service không có HTTP health endpoint, nhưng quá nông để thay thế readiness semantics của ứng dụng.

### 3.3. Exec probe

Exec probe chạy command trong container. Command có thể kiểm tra file/socket/local process, nhưng tạo process phụ và có thể tốn tài nguyên nếu chạy thường xuyên. Tránh dùng shell script nặng hoặc command phụ thuộc tools không có trong minimal container image.

### 3.4. gRPC probe

Nếu ứng dụng cung cấp gRPC health checking protocol, Kubernetes có thể dùng grpc probe. Cần bảo đảm health service phản ánh readiness/liveness semantics mong muốn. Actuator HTTP endpoint không tự động cung cấp gRPC health protocol.

## 4. Cấu hình probe trong Deployment

Ví dụ Deployment cho Spring Boot chạy HTTP port 8080:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 2
~~~

Đây là cấu hình minh họa. Startup probe cho tối đa khoảng 150 giây theo period/failure threshold trong ví dụ, nhưng thời điểm thực tế còn phụ thuộc scheduling và probe execution. Chọn thông số theo startup duration đo được và budget rollout.

### 4.1. initialDelaySeconds và startupProbe

Khi có startupProbe, thường không cần dùng initialDelaySeconds dài cho liveness/readiness để che startup chậm; startupProbe đã bảo vệ giai đoạn đó. Có thể dùng initialDelaySeconds khi cần delay riêng, nhưng tránh cấu hình chồng lấn khó hiểu.

### 4.2. timeoutSeconds

timeoutSeconds là giới hạn thời gian một lần probe. Health indicator phải hoàn tất nhanh hơn timeout. Nếu indicator gọi database hoặc remote API, đặt timeout client nhỏ hơn tổng probe timeout để Actuator có thể trả kết quả có kiểm soát.

### 4.3. periodSeconds

periodSeconds là khoảng cách giữa các lần probe. Probe quá thường xuyên có thể tạo tải phụ, nhất là khi mỗi lần gọi nhiều external dependencies. Probe quá thưa làm phát hiện failure chậm. Cân đối theo failure detection budget và chi phí health check.

### 4.4. failureThreshold và successThreshold

failureThreshold là số lần thất bại liên tiếp trước khi probe được xem là failed. successThreshold quy định số lần thành công liên tiếp để chuyển lại success; readiness probe có thể dùng để giảm flapping, trong khi startup/liveness có giới hạn semantics riêng của Kubernetes. Kiểm tra Kubernetes version và loại probe khi cấu hình.

## 5. Tính startup budget và failure detection

Startup budget cần bao phủ startup time bình thường cộng warm-up cần thiết và biến động hợp lý. Với startup probe periodSeconds = 5 và failureThreshold = 30, budget danh nghĩa xấp xỉ 150 giây.

Ví dụ ứng dụng có startup p99 35 giây, cache warm-up p99 40 giây, dependency initialization 15 giây và safety margin 30 giây. Startup budget đề xuất ban đầu khoảng 120 giây. Đo lại bằng startup metrics trong môi trường gần production; không dùng số ước lượng này làm cấu hình cố định.

### 5.1. Failure detection budget

Với probe period P, timeout T và failure threshold F, thời gian phát hiện failure thường xấp xỉ theo chu kỳ P nhân F, nhưng thời gian thực tế còn phụ thuộc lần probe đầu, thời gian request và scheduling. Không diễn giải công thức đơn giản như deadline chính xác.

### 5.2. Liveness threshold

Liveness failure dẫn tới restart. Đặt threshold đủ chịu được pause ngắn như CPU throttling, GC pause hoặc tải tạm thời. Threshold quá nhạy có thể restart loop; threshold quá lỏng có thể giữ process bị deadlock lâu.

### 5.3. Readiness threshold

Readiness có thể cần phục hồi nhanh để pod trở lại traffic, nhưng cần tránh flapping khi dependency chập chờn. Dùng successThreshold, caching/hysteresis trong ứng dụng nếu phù hợp và circuit breaker cho lời gọi nghiệp vụ.

## 6. Management port riêng và network

Spring Boot có thể chạy Actuator trên management port riêng:

~~~yaml
management:
  server:
    port: 8081
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health
  endpoint:
    health:
      probes:
        enabled: true
~~~

Khi đó probe cần dùng port 8081 và path đúng theo base path/health group. Nếu base path là /manage, xác minh endpoint group thực tế là /manage/health/liveness và /manage/health/readiness.

### 6.1. Management port không phải security boundary

Port riêng không tự động được bảo vệ. Pod network, NetworkPolicy, service mapping và security chain vẫn quyết định ai truy cập được. Không expose management port qua public Service nếu không cần.

### 6.2. Management context và application context

Nếu management server chạy port riêng, nó có thể có web server/context riêng. Health endpoint vẫn cần truy cập được từ kubelet. Kiểm thử từ góc nhìn pod/container và xác minh liveness endpoint không phụ thuộc route của business server.

### 6.3. NetworkPolicy

Nếu áp dụng NetworkPolicy, cho phép kubelet/node probe path theo mô hình network của cluster. Một policy chặn probe có thể khiến pod bị restart hoặc not ready dù application khỏe. Kiểm tra events và network reachability trước khi sửa health code.

## 7. Security và health details

Kubernetes probe thường cần đọc status mà không cần component details. Cấu hình Actuator có thể ẩn details:

~~~yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
~~~

Nếu security chain yêu cầu authentication cho health endpoint, kubelet HTTP probe tiêu chuẩn không tự gửi bearer token như HTTP client tùy chỉnh. Có thể dùng port/path/network riêng, permit đúng health paths trong security chain hoặc chọn cơ chế phù hợp cluster policy. Chỉ permit endpoint status tối thiểu; giữ management endpoints khác được bảo vệ.

### 7.1. HTTP status mapping

Probe HTTP đánh giá status code. Nếu health status DOWN được trả 503, probe thất bại như mong muốn. Nếu custom status mapping luôn trả 200, kubelet có thể đánh giá success dù body báo DOWN. Kiểm thử response code thực tế, không chỉ đọc JSON body.

### 7.2. Không để details tiết lộ topology

Health response công khai không nên chứa database hostname, credentials, internal IP, stack trace hoặc connection URL. Dùng logs/metrics có kiểm soát để điều tra chi tiết.

## 8. Dependency checks và cascade failure

Readiness có thể kiểm tra dependency bắt buộc, nhưng liveness không nên phụ thuộc external systems nếu restart không thể sửa sự cố đó.

| Dependency | Liveness | Readiness |
| --- | --- | --- |
| JVM/process state | Có | Có thể gián tiếp |
| Critical database | Không | Có thể, nếu mọi request chính cần |
| Optional search service | Không | Thường không nếu có fallback |
| Analytics broker | Không | Thường không nếu xử lý async |
| Payment provider | Không | Cân nhắc theo traffic/use case |
| Cache có fallback | Không | Thường không |

Nếu database shared bị lỗi và readiness của mọi pod chuyển false, service có thể không còn endpoint nào. Điều đó có thể đúng nếu không thể phục vụ request chính, nhưng cần đánh giá degraded mode, fallback và khả năng xử lý traffic còn lại.

### 8.1. Không probe bằng query nặng

Health check nên nhẹ và có timeout. Tránh full scan, count bảng lớn hoặc transaction nghiệp vụ. Probe frequency cao nhân chi phí check trên mọi pod.

### 8.2. Circuit breaker và probe khác nhau

Circuit breaker điều khiển lời gọi nghiệp vụ dựa trên failures/slow calls. Probe báo trạng thái instance cho orchestrator. Không dùng probe thay circuit breaker hoặc retry policy. Kết hợp timeout, bulkhead, fallback và readiness policy.

## 9. Rolling update và readiness

Trong rolling update, Kubernetes tạo pod mới, chờ pod đủ điều kiện Ready rồi mới tiếp tục rollout theo strategy. Readiness probe quyết định pod có thể tham gia Service endpoints. Nếu readiness quá dễ thành công, traffic có thể tới instance chưa warm-up; nếu quá khó, rollout có thể bị kẹt.

### 9.1. minReadySeconds và rollout strategy

minReadySeconds cho phép Deployment chờ pod ở trạng thái Ready trong một khoảng trước khi coi là available cho rollout. Nó không thay readiness probe; nó bổ sung độ ổn định sau khi pod ready.

maxUnavailable và maxSurge kiểm soát số pod có thể unavailable hoặc tạo thêm trong rollout. Chọn theo capacity, startup time và khả năng chịu tải dependency.

### 9.2. Startup chậm và rollout timeout

Nếu startup budget dài hơn progress deadline của Deployment, rollout có thể bị đánh dấu thất bại trước khi pod sẵn sàng. Căn chỉnh startupProbe budget, progressDeadlineSeconds, rollout strategy và thời gian image pull/scheduling.

## 10. Graceful shutdown và termination

Khi pod bị terminate, Kubernetes gửi SIGTERM và bắt đầu termination grace period. Spring Boot graceful shutdown có thể ngừng nhận request mới và chờ request đang chạy hoàn tất.

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Readiness cần chuyển sang REFUSING_TRAFFIC khi shutdown bắt đầu để pod được rút khỏi routing. Việc cập nhật endpoints/load balancer cần thời gian. Phối hợp termination grace period, preStop/drain behavior và server shutdown timeout.

### 10.1. Không chỉ dựa vào sleep

Một preStop sleep cố định có thể tạo khoảng đệm nhưng không chứng minh traffic đã drain. Thiết kế dựa trên readiness transition, load balancer propagation, in-flight request duration và grace period thực tế. Đừng để grace period ngắn hơn thời gian request hợp lệ cần hoàn tất.

## 11. Kiểm thử Kubernetes probe

Test health code trong JVM chưa đủ để chứng minh kubelet có thể truy cập endpoint trong cluster. Nên kiểm tra nhiều lớp:

| Test | Xác minh |
| --- | --- |
| HealthIndicator unit test | Contributor logic và timeout |
| MockMvc/integration test | Actuator path, status code, security |
| Container smoke test | Port/path trong image runtime |
| Manifest validation | YAML schema và probe fields |
| Kind/minikube test | Kubelet probe behavior trong cluster test |
| Rollout test | Pod chỉ Ready sau warm-up |
| Termination test | Readiness false và graceful drain |

### 11.1. Test endpoint response

Gửi request tới đúng path và xác minh HTTP status, không chỉ JSON body. Kiểm tra cả anonymous probe caller và caller được cấp quyền nếu policy có phân biệt.

### 11.2. Test startup delay

Tạo fixture warm-up có delay có kiểm soát. Xác minh startupProbe không đánh container fail trước budget, readiness chưa thành công trước warm-up completion và sau đó pod được Ready.

### 11.3. Test liveness failure

Trong môi trường test, mô phỏng ứng dụng không thể tiếp tục hoạt động theo policy. Xác minh liveness failure dẫn tới restart. Không cố ý tạo deadlock hoặc kill production process để thử probe.

### 11.4. Test readiness flapping

Mô phỏng dependency chập chờn và kiểm tra pod readiness transitions. Đánh giá tác động tới endpoints, traffic distribution và rollout. Kiểm tra thresholds/hysteresis có giảm flapping mà vẫn phát hiện outage trong budget.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Pod restart loop | Liveness/startup probe thất bại | Xem pod events, container logs và probe path |
| Pod Running nhưng NotReady | Readiness group DOWN hoặc path sai | Gọi endpoint từ trong pod và kiểm tra contributors |
| Probe connection refused | Sai port hoặc server chưa listen | Xác minh containerPort/management port |
| Probe HTTP 404 | Sai base path hoặc group path | Kiểm tra Actuator exposure/path |
| Probe HTTP 401/403 | Security chain chặn kubelet | Permit đúng health path hoặc policy phù hợp |
| Probe timeout | Indicator block hoặc timeout quá thấp | Giảm check cost và đặt dependency timeout |
| Startup probe fail sau deploy | Startup budget nhỏ hơn startup thực | Đo startup duration, tăng budget hợp lý |
| Tất cả pod restart khi DB lỗi | Liveness phụ thuộc database | Tách dependency khỏi liveness |
| Rollout bị kẹt | Readiness không đạt hoặc progress deadline ngắn | Kiểm tra warm-up và rollout settings |
| Pod ready trước cache warm-up | Readiness transition quá sớm | Giữ REFUSING_TRAFFIC tới completion |
| Probe bị network timeout | NetworkPolicy/node routing | Kiểm tra reachability và policy |
| Health body DOWN nhưng probe pass | HTTP status mapping trả success | Kiểm tra status code thực |
| Shutdown mất request | Drain/grace period không đủ | Căn chỉnh readiness, server timeout và termination grace |

### 12.1. Quy trình điều tra pod không Ready

1. Đọc pod description và events để xem probe type/path/response.
2. Xem container logs quanh startup và health indicator failures.
3. Exec vào container hoặc dùng port-forward để gọi đúng Actuator path.
4. Kiểm tra HTTP status, management port, base path và security.
5. Xem readiness group contributors và ApplicationAvailability state.
6. Đo warm-up duration và dependency timeouts.
7. Kiểm tra NetworkPolicy và kubelet reachability.
8. Đối chiếu Deployment rollout strategy và progress deadline.

## 13. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Startup probe có budget thực tế | Đo startup p95/p99 và warm-up |
| Liveness chỉ kiểm tra khả năng tiếp tục | Không phụ thuộc dependency ngoài |
| Readiness phản ánh traffic policy | Dependency mandatory/optional phân loại |
| Actuator groups đúng | Liveness/readiness paths đã test |
| HTTP status mapping đúng | DOWN trả response code thất bại |
| Port/base path chính xác | Manifest khớp runtime |
| Security phù hợp kubelet | Chỉ health path tối thiểu được phép |
| Timeout/frequency hợp lý | Không gây tải hoặc timeout giả |
| Threshold chống flapping | Failure/success thresholds có căn cứ |
| Rolling update đồng bộ | maxSurge/maxUnavailable/progress deadline |
| Graceful shutdown/drain | Readiness refusing và grace period đủ |
| Observability có lịch sử | Probe failures, startup duration và restart metrics |
| Manifest được validate | CI kiểm tra YAML/schema và deploy test |

## 14. Bài thực hành: triển khai probes cho order-service

**Bối cảnh:** order-service chạy ba replicas trên Kubernetes, dùng Spring Boot Actuator. Cache cần warm-up trước khi nhận traffic; PostgreSQL có thể gián đoạn ngắn. Hiện pod restart khi database lỗi và đôi khi nhận traffic trước khi cache sẵn sàng.

**Nhiệm vụ:**
1. Bật Actuator health probes.
2. Xác minh liveness và readiness health paths.
3. Đặt liveness group không phụ thuộc PostgreSQL.
4. Đưa PostgreSQL vào readiness chỉ khi use case chính không thể phục vụ khi DB unavailable.
5. Giữ readiness REFUSING_TRAFFIC trong warm-up.
6. Cấu hình startupProbe có budget theo startup/warm-up p99.
7. Cấu hình liveness/readiness period, timeout và thresholds theo failure budget.
8. Kiểm tra management port riêng, base path và security.
9. Thử dependency outage và xác minh không có liveness restart storm.
10. Thực hiện rolling update và xác minh pod mới chỉ nhận traffic sau khi ready.
11. Terminate pod trong lúc có request; xác minh graceful shutdown và draining.
12. Viết runbook cho restart loop, NotReady, timeout và rollout stalled.

**Kết quả mong đợi:** Kubernetes Deployment manifest, Actuator health groups, test probe behavior, rollout/shutdown evidence và runbook.

## 15. Ghi nhớ

Kubernetes probes điều khiển ba hành động khác nhau: startupProbe bảo vệ giai đoạn khởi động, livenessProbe quyết định restart và readinessProbe quyết định pod có nhận traffic. Spring Boot Actuator cung cấp health groups phù hợp để biểu diễn liveness/readiness; path, port, security và HTTP status mapping phải khớp manifest.

Đặt startup budget theo thời gian khởi động và warm-up đo được. Liveness không nên phụ thuộc database/broker nếu restart không thể sửa outage. Readiness cần phản ánh dependency thực sự bắt buộc và degraded mode. Căn chỉnh probe timeout/threshold với failure budget, rollout strategy và graceful shutdown. Kiểm thử trong môi trường Kubernetes tương tự production; dùng logs, metrics và events để điều tra probe failures thay vì chỉ nhìn trạng thái Running/NotReady.

**Tài liệu tham khảo:**
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)
- [Kubernetes — Configure Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)
- [Kubernetes — Deployments and Rolling Updates](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Spring Boot — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Boot — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)


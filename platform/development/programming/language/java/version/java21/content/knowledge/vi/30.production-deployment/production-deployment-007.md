# Thiết lập health check và cảnh báo lỗi tài nguyên

## Mục tiêu

Một dịch vụ Java 21 chạy production cần cho hệ thống điều phối biết khi nào tiến trình đã khởi động, khi nào có thể nhận traffic và khi nào cần được khởi động lại. Đồng thời, đội vận hành cần phát hiện sớm tình trạng cạn heap, vượt giới hạn bộ nhớ container, CPU throttling, GC pressure, thread/task tăng bất thường hoặc connection pool bị bão hòa.

Health check và resource alert có mục đích khác nhau. Health check trả lời câu hỏi một instance có thể tiếp tục chạy hoặc nhận traffic hay không. Metrics và alert giúp phát hiện xu hướng suy giảm, xác định nguyên nhân và yêu cầu hành động vận hành. Bài học này trình bày mô hình liveness/readiness/startup, ví dụ với Spring Boot Actuator, cấu hình Kubernetes probe và cách thiết kế cảnh báo có thể hành động được cho ứng dụng Java 21.

## 1. Phân biệt health check với monitoring và alert

Các cơ chế này bổ sung cho nhau:

| Cơ chế | Câu hỏi | Hành động thường gặp |
|---|---|---|
| Startup probe | Ứng dụng đã hoàn tất khởi tạo chưa? | Tạm hoãn liveness/readiness cho đến khi startup thành công |
| Liveness check | Process còn sống và có thể tiếp tục hoạt động không? | Restart instance nếu thất bại liên tục |
| Readiness check | Instance hiện có thể nhận request mới không? | Tạm ngừng gửi traffic đến instance |
| Metrics | Tài nguyên và hiệu năng đang thay đổi thế nào? | Dashboard, phân tích xu hướng và điều tra |
| Alert | Có điều kiện cần người hoặc hệ thống phản ứng không? | Gửi thông báo, tạo incident hoặc kích hoạt runbook |

Java SE không định nghĩa sẵn một HTTP health endpoint cho mọi ứng dụng. Framework hoặc nền tảng triển khai thường cung cấp endpoint và cơ chế probe. Metrics có thể được xuất bằng Micrometer/Prometheus, JMX hoặc hệ thống telemetry mà tổ chức đang sử dụng.

Không nên dùng một endpoint `/health` duy nhất cho tất cả mục đích nếu hệ thống điều phối cần phân biệt restart với ngừng nhận traffic. Một dependency tạm thời lỗi có thể khiến instance không sẵn sàng nhận request, nhưng restart liên tục mọi instance vì dependency chung đang lỗi có thể làm sự cố nghiêm trọng hơn.

## 2. Liveness: process có còn tiến triển được không?

Liveness kiểm tra ứng dụng có ở trạng thái cần restart hay không. Một liveness check nên tập trung vào trạng thái nội bộ của process, ví dụ:

- Application context đã được khởi tạo và main service loop còn hoạt động.
- Thành phần cốt lõi không ở trạng thái deadlock hoặc không thể phục hồi.
- Ứng dụng chưa đi vào trạng thái shutdown.

Không nên đưa database, message broker hoặc API bên ngoài vào liveness check một cách mặc định. Nếu database dùng chung tạm thời mất kết nối, tất cả instance có thể cùng fail liveness và bị restart đồng loạt. Việc này không khôi phục database, đồng thời tạo thêm áp lực lên dependency khi nó vừa phục hồi.

Liveness nên rẻ, nhanh, có timeout ngắn và không thực hiện truy vấn sâu. Nếu endpoint liveness không trả lời vì process bị treo hoặc không thể xử lý request, nền tảng có thể restart instance sau số lần thất bại đã cấu hình.

## 3. Readiness: instance có thể nhận traffic không?

Readiness phản ánh khả năng phục vụ request tại thời điểm hiện tại. Một instance có thể còn sống nhưng chưa sẵn sàng nhận traffic, ví dụ:

- Ứng dụng đang nạp cache hoặc hoàn tất warm-up cần thiết.
- Connection pool chưa sẵn sàng.
- Một dependency bắt buộc để xử lý request đang không khả dụng.
- Instance đang drain traffic để shutdown có trật tự.
- Hệ thống đã đạt giới hạn admission và cần tạm ngừng nhận thêm công việc.

Khi readiness fail, orchestrator hoặc load balancer nên ngừng gửi request mới đến instance. Readiness fail không đồng nghĩa cần restart process.

Chỉ đưa dependency thực sự cần cho request vào readiness. Nếu một tính năng tùy chọn hoặc một integration không liên quan đến phần lớn traffic bị lỗi, không nhất thiết phải đánh dấu toàn bộ instance unready. Có thể theo dõi dependency đó bằng metric và alert riêng, hoặc dùng readiness theo nhóm endpoint nếu kiến trúc cho phép.

## 4. Startup probe: phân biệt khởi động chậm với process bị treo

Một số ứng dụng Java cần thời gian để khởi động JVM, nạp Spring context, thực hiện migration hoặc warm-up. Nếu liveness bắt đầu quá sớm, orchestrator có thể restart process trước khi ứng dụng có cơ hội hoàn tất startup.

Startup probe dành cho giai đoạn này. Khi startup probe chưa thành công, Kubernetes chưa chạy liveness và readiness probe. Khi startup probe thành công, các probe còn lại bắt đầu hoạt động theo cấu hình.

Startup probe cần có ngân sách thời gian phù hợp với startup p99 hoặc thời gian khởi động đã quan sát trong production. Không nên đặt giá trị quá dài chỉ để che giấu startup bị treo; hãy theo dõi startup duration và đặt ngưỡng theo SLO triển khai.

## 5. Ví dụ với Spring Boot Actuator

Spring Boot Actuator cung cấp health endpoint và các health indicator. Trong ứng dụng Java 21, dùng release Spring Boot còn được hỗ trợ và tương thích với Java 21; Java 21 được hỗ trợ từ Spring Boot 3.2 trong dòng 3.x. Khi tạo hệ thống mới, chọn release còn được bảo trì thay vì ghim một bản cũ chỉ vì ví dụ này dùng cùng API. Cần có Actuator dependency; nếu muốn expose Prometheus scrape endpoint, thêm Micrometer Prometheus Registry:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
```

Phiên bản dependency nên được quản lý bằng Spring Boot dependency management/BOM của dự án. Sau đó, có thể bật health probes và tách nhóm liveness/readiness trong `application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db,partner
```

Trong cấu hình này:

- `/actuator/health/liveness` phục vụ liveness group.
- `/actuator/health/readiness` phục vụ readiness group.
- `readiness` bao gồm trạng thái ứng dụng, database health indicator và health indicator `partner` nếu ứng dụng đã đăng ký.
- `show-details: never` tránh công khai thông tin chi tiết về dependency và cấu hình nội bộ qua endpoint health.
- `prometheus` chỉ nên expose nếu ứng dụng có dependency Micrometer Prometheus Registry và endpoint được bảo vệ phù hợp.

Mặc định, Spring Boot ánh xạ trạng thái `DOWN` và `OUT_OF_SERVICE` thành HTTP 503; `UP` và `UNKNOWN` thường thành HTTP 200. Nếu tùy chỉnh status mapping, xác minh lại hành vi mà Kubernetes probe sẽ nhận được.

Tên health indicator `db` thường được Spring Boot auto-configure khi có datasource phù hợp. `partner` là indicator tùy chỉnh trong ví dụ; nếu chưa đăng ký indicator này, hãy bỏ nó khỏi group hoặc triển khai indicator tương ứng. Không copy nguyên cấu hình mà không kiểm tra các indicator thực sự có trong ứng dụng.

Với Kubernetes, có thể bật thêm đường dẫn probe trên main application port bằng cấu hình Actuator phù hợp với phiên bản Spring Boot đang dùng, chẳng hạn `management.endpoint.health.probes.add-additional-paths=true`. Khi bật, Spring Boot cung cấp các đường dẫn `/livez` và `/readyz` trên server port chính, giúp probe kiểm tra cả web server phục vụ ứng dụng. Hãy xác minh endpoint thực tế trong phiên bản framework đã ghim.

## 6. Viết health indicator có timeout và giới hạn phạm vi

Health indicator tùy chỉnh nên thực hiện một thao tác nhỏ, có timeout và không trả dữ liệu nhạy cảm. Ví dụ sau minh họa kiểm tra khả năng gọi một dependency bắt buộc:

```java
import java.time.Duration;

import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("partner")
class PartnerHealthIndicator implements HealthIndicator {
    private final PartnerClient client;

    PartnerHealthIndicator(PartnerClient client) {
        this.client = client;
    }

    @Override
    public Health health() {
        try {
            boolean available = client.ping(Duration.ofMillis(300));
            if (available) {
                return Health.up().build();
            }
            return Health.down().withDetail("dependency", "partner").build();
        } catch (Exception e) {
            // Không đưa exception message, URL, credential hoặc payload vào health response.
            return Health.down().withDetail("dependency", "partner").build();
        }
    }
}
```

`PartnerClient` là abstraction do ứng dụng định nghĩa; method `ping(Duration)` phải thực sự áp dụng timeout ở HTTP client hoặc SDK bên dưới. Chỉ đặt timeout ở phía caller mà không hủy hoặc giới hạn I/O thực tế có thể khiến probe vẫn giữ thread và connection trong thời gian dài.

Không nên gọi một API nghiệp vụ có side effect trong health check. Tránh kiểm tra bằng thao tác tạo đơn hàng, gửi message hoặc cập nhật dữ liệu. Health check nên dùng endpoint health/read-only hoặc một thao tác kiểm tra nhẹ đã được dependency hỗ trợ.

Nếu dependency chậm, có thể cache kết quả health trong một khoảng ngắn và cập nhật bằng background check, nhưng phải giới hạn tuổi dữ liệu và thể hiện rõ stale status. Không tạo một thread mới cho mỗi lần probe và không để nhiều probe đồng thời gây thêm tải lên dependency đang gặp sự cố.

## 7. Cấu hình Kubernetes probes

Ví dụ Deployment sau dùng ba probe riêng. Thay port và image bằng cấu hình của ứng dụng:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: java-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: java-service
  template:
    metadata:
      labels:
        app: java-service
    spec:
      containers:
        - name: app
          image: registry.example.com/java-service:1.0.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
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
            failureThreshold: 3
```

Các giá trị là ví dụ ban đầu, không phải ngưỡng phù hợp cho mọi service. `failureThreshold` kết hợp `periodSeconds` quyết định khoảng thời gian lỗi liên tục trước khi probe được xem là thất bại. Hãy đặt timeout lớn hơn thời gian phản hồi bình thường nhưng đủ ngắn để phát hiện instance không còn tiến triển.

Với startup probe ở ví dụ, liveness/readiness chưa được thực thi cho đến khi startup thành công. Điều này cho phép startup kéo dài trong một khoảng phù hợp với cấu hình probe mà không bị liveness restart sớm.

Nếu dùng management port riêng, cân nhắc probe trên main server port hoặc cấu hình thêm đường dẫn probe trên port chính. Một management server riêng có thể vẫn trả health response trong khi web server chính không phục vụ được traffic; probe cần kiểm tra đúng đường đi mà client sử dụng.

## 8. Giám sát heap và bộ nhớ process/container

Không nên chỉ theo dõi heap usage. Container memory còn gồm nhiều vùng ngoài Java heap:

- Metaspace và compressed class space.
- JIT code cache.
- Direct buffers và native allocation.
- Thread stack và bộ nhớ native của JVM.
- Thư viện JNI/JNA và các tiến trình phụ trong cùng container nếu có.

Một JVM có heap còn thấp vẫn có thể bị container OOM kill nếu tổng memory vượt limit. Ngược lại, heap usage cao trong thời gian ngắn chưa chắc là sự cố nếu GC hoạt động bình thường và không ảnh hưởng SLO.

Nên theo dõi đồng thời:

| Metric | Ý nghĩa |
|---|---|
| Heap used/max | Mức sử dụng Java heap so với giới hạn heap |
| Non-heap used | Metaspace, code cache và các vùng non-heap được JVM báo cáo |
| Process/container working set | Bộ nhớ thực tế container đang sử dụng |
| Container memory limit | Giới hạn bộ nhớ do nền tảng áp dụng |
| OOMKilled/restart count | Dấu hiệu container đã bị hệ thống dừng do memory pressure |
| Direct buffer usage | Mức sử dụng direct buffer nếu ứng dụng dùng NIO/Netty |

Với Micrometer/JVM metrics, metric heap thường có dạng `jvm_memory_used_bytes` và `jvm_memory_max_bytes`, có nhãn `area="heap"`. Tên metric container phụ thuộc exporter và nền tảng, ví dụ cAdvisor hoặc Kubernetes metrics pipeline.

## 9. Cảnh báo heap và container memory

Ví dụ PromQL dưới đây minh họa cách tính tỷ lệ heap đang dùng và container working set. Tên metric/label có thể khác tùy phiên bản Micrometer, Prometheus exporter và cAdvisor; cần kiểm tra metric thực tế trước khi đưa rule vào production.

```promql
sum by (application, instance) (
  jvm_memory_used_bytes{area="heap"}
)
/
sum by (application, instance) (
  jvm_memory_max_bytes{area="heap"} > 0
) > 0.85
```

Đây là cảnh báo tham khảo khi heap usage duy trì trên 85%. Nên thêm điều kiện thời gian như `for: 10m`, kết hợp xu hướng sau GC và allocation rate. Một spike ngắn trước GC không nhất thiết cần page người trực.

Với container, ví dụ metric cAdvisor:

```promql
container_memory_working_set_bytes{container!="", image!=""}
/
container_spec_memory_limit_bytes{container!="", image!=""} > 0.90
```

Nếu nền tảng không xuất `container_spec_memory_limit_bytes` hoặc dùng tên metric khác, thay bằng metric limit tương ứng. Loại bỏ series không có memory limit hợp lệ để tránh phép chia sai hoặc cảnh báo nhiễu.

Nên tạo cảnh báo riêng cho:

- Heap usage cao kéo dài sau nhiều chu kỳ GC.
- Container memory tiến sát limit.
- OOMKilled hoặc restart do memory pressure.
- Direct memory hoặc native memory tăng bất thường nếu ứng dụng có sử dụng.

Heap và container memory cần hai ngưỡng riêng. Không cộng heap và non-heap một cách máy móc rồi so với container limit; hãy dùng metric process/container thực tế để phát hiện native memory và overhead khác.

## 10. Cảnh báo CPU và CPU throttling

CPU cao có thể do business workload, GC concurrent work, serialization, logging, retry storm hoặc busy loop. Chỉ số CPU utilization đơn lẻ không cho biết nguyên nhân.

Trong container, CPU throttling có thể khiến JVM không nhận đủ thời gian CPU dù host còn nhiều core. Với cAdvisor, có thể quan sát tỷ lệ chu kỳ CPU bị throttle:

```promql
rate(container_cpu_cfs_throttled_periods_total[5m])
/
rate(container_cpu_cfs_periods_total[5m]) > 0.20
```

Tên metric có thể thay đổi theo runtime/cAdvisor và cgroup version. Một tỷ lệ trên 20% trong vài phút là ví dụ để bắt đầu điều tra, không phải ngưỡng production chung. Đối chiếu với CPU usage, request latency, throughput và CPU quota.

Nếu CPU cao nhưng throughput không tăng, hãy điều tra CPU profile, GC activity, lock contention và dependency wait. Nếu CPU throttling tăng đồng thời với latency, xem lại CPU limit/request hoặc tải đang nhận. Đừng tăng concurrency vô hạn khi CPU đã bão hòa.

## 11. Cảnh báo GC và allocation pressure

GC metrics giúp phát hiện khi ứng dụng dành nhiều thời gian hoặc CPU cho quản lý bộ nhớ. Có thể theo dõi:

- GC pause duration và tần suất pause.
- GC CPU/time nếu runtime hoặc exporter cung cấp.
- Allocation rate và heap occupancy.
- Allocation stall hoặc các sự kiện GC đặc thù trong log/JFR khi dùng ZGC.
- Thay đổi latency p95/p99 cùng thời điểm GC pressure tăng.

Không phải mọi collector đều xuất cùng metric hoặc event. Nếu chạy Generational ZGC trên Java 21, dùng GC log và JFR để điều tra allocation stall, concurrent cycle và pause; đừng giả định một metric generic của Micrometer thể hiện đầy đủ mọi hiện tượng ZGC.

Alert nên dựa trên tác động: GC pause vượt SLO, allocation stall xuất hiện kéo dài, heap không có headroom hoặc throughput giảm. Một chu kỳ GC diễn ra thường xuyên không tự nó là lỗi; GC là hoạt động bình thường của JVM.

## 12. Cảnh báo thread, virtual task và scheduler

Với ứng dụng Java 21 dùng virtual threads, số platform thread không đại diện cho số virtual thread hoặc task đang sống. `ThreadMXBean` đo platform thread; task metrics cần được instrument ở tầng ứng dụng hoặc quan sát bằng JFR.

Các metric hữu ích gồm:

- Platform thread live/peak để phát hiện thread pool hoặc thread leak.
- Application task active, started, completed và failed nếu ứng dụng tạo virtual thread task.
- Task duration, queue/wait time và số task đang chờ semaphore/dependency.
- JFR `jdk.VirtualThreadPinned` để điều tra pinning trên Java 21.
- CPU, scheduler pressure và lỗi submit task nếu runtime ghi nhận.

Không đặt alert chỉ vì số virtual thread cao. Một workload I/O-bound có thể có nhiều virtual thread đang chờ là bình thường. Cần kết hợp active task với task duration, request latency, dependency saturation, heap và CPU.

## 13. Cảnh báo connection pool và queue

Connection pool và queue thường là nơi thể hiện sớm tình trạng dependency bão hòa:

| Metric | Dấu hiệu cần theo dõi |
|---|---|
| Connections active/max | Pool thường xuyên đạt gần maximum |
| Pending/waiting borrowers | Task phải chờ connection tăng kéo dài |
| Connection acquisition timeout | Request không lấy được connection trong deadline |
| Queue depth | Công việc tích tụ nhanh hơn tốc độ xử lý |
| Queue wait time | Task chờ quá lâu trước khi được xử lý |
| Rejected task/request | Admission control đang từ chối công việc |
| Retry count | Retry có thể khuếch đại tải lên dependency |

Khi pool đạt maximum, không nhất thiết phải tăng pool size. Database có giới hạn connection và năng lực xử lý riêng; tăng pool có thể làm database quá tải hơn. Hãy kiểm tra query latency, transaction duration, số connection tổng từ mọi instance và cấu hình database.

Queue không giới hạn có thể che giấu quá tải bằng cách chuyển lỗi thành thời gian chờ và tiêu thụ bộ nhớ. Ưu tiên queue hữu hạn, timeout, backpressure và từ chối sớm theo hợp đồng service.

## 14. Ví dụ Prometheus alert rule

Một nhóm rule minh họa cho heap, container memory, CPU throttling và HTTP error ratio:

```yaml
groups:
  - name: java-service-resources
    rules:
      - alert: JavaHeapUsageHigh
        expr: |
          sum by (application, instance) (jvm_memory_used_bytes{area="heap"})
          /
          sum by (application, instance) (jvm_memory_max_bytes{area="heap"} > 0) > 0.85
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Java heap usage is high"
          description: "Heap usage has remained above 85% for 10 minutes."

      - alert: ContainerMemoryNearLimit
        expr: |
          container_memory_working_set_bytes{container!="", image!=""}
          /
          container_spec_memory_limit_bytes{container!="", image!=""} > 0.90
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Container memory is near its limit"
          description: "Check heap, native memory, direct buffers and container limit."

      - alert: ContainerCpuThrottlingHigh
        expr: |
          rate(container_cpu_cfs_throttled_periods_total[5m])
          /
          rate(container_cpu_cfs_periods_total[5m]) > 0.20
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Container CPU throttling is elevated"
          description: "Correlate throttling with latency, throughput and CPU quota."
```

Các biểu thức là ví dụ; phải xác minh metric name, label và cách aggregate trên hệ thống thực tế. Với container không có memory limit, rule cần lọc series tương ứng. Nên thêm `job`, namespace, cluster hoặc workload labels theo mô hình giám sát của tổ chức để tránh gộp các instance không liên quan.

Alert HTTP error ratio nên dùng metric request count do instrumentation của ứng dụng cung cấp. Ví dụ với metric Micrometer phổ biến:

```promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m])) > 0.02
```

Ngưỡng 2% chỉ là ví dụ. Service ít traffic có thể cần điều kiện minimum request count hoặc multi-window burn-rate alert để tránh cảnh báo do một request lỗi. Với service có SLO, ưu tiên alert theo error budget burn rate thay vì một tỷ lệ cố định không xét lưu lượng.

## 15. Thiết kế alert có thể hành động được

Một alert tốt nên cho biết:

- Tài nguyên hoặc SLO nào đang bị ảnh hưởng.
- Phạm vi instance/service/cluster.
- Mức độ nghiêm trọng và thời gian duy trì.
- Metric và dashboard liên quan.
- Hành động đầu tiên hoặc runbook cần mở.

Phân cấp gợi ý:

| Mức | Ví dụ | Hành động |
|---|---|---|
| Info | Heap tăng theo burst nhưng hồi phục sau GC | Theo dõi dashboard, không page |
| Warning | CPU throttling hoặc pool wait tăng kéo dài | Điều tra trong giờ làm việc, kiểm tra capacity |
| Critical | Container memory sát limit, OOMKilled tăng hoặc SLO burn nhanh | Gọi người trực và thực hiện runbook |

Không alert theo một sample đơn lẻ. Dùng `for`, moving window hoặc burn-rate logic để loại nhiễu, nhưng không đặt thời gian chờ dài đến mức bỏ lỡ sự cố thật. Alert phải có owner và hành động tiếp theo; nếu không ai cần làm gì khi nó bật, có thể chỉ cần metric/dashboard.

## 16. Bảo vệ health endpoint và metrics endpoint

Health và metrics có thể tiết lộ tên dependency, trạng thái database, phiên bản, cấu hình nội bộ hoặc thông tin hạ tầng. Trong production:

- Chỉ expose các endpoint thực sự cần thiết.
- Không trả exception message, connection string, hostname nội bộ hoặc credential trong health details.
- Giới hạn truy cập management endpoint bằng network policy, private interface, authentication hoặc gateway phù hợp.
- Không public Prometheus scrape endpoint ra Internet nếu không có yêu cầu và biện pháp bảo vệ tương ứng.
- Tách quyền đọc metrics khỏi quyền truy cập API nghiệp vụ nếu nền tảng hỗ trợ.
- Giữ health response nhỏ và nhanh để probe không trở thành nguồn tải bổ sung.

Nếu dùng management port riêng, cần xác nhận probe vẫn kiểm tra đúng trạng thái server chính. Một management endpoint khỏe không nhất thiết chứng minh listener phục vụ người dùng còn hoạt động.

## 17. Kiểm thử health check và alert trước khi triển khai

Không chỉ kiểm tra endpoint trả HTTP 200 khi ứng dụng bình thường. Cần xác minh các trạng thái chuyển đổi:

1. Startup chưa xong: startup probe chưa thành công và liveness/readiness chưa restart instance sớm.
2. Startup hoàn tất: liveness và readiness trả trạng thái UP.
3. Dependency bắt buộc bị ngắt: readiness chuyển DOWN, liveness vẫn UP nếu process còn khỏe.
4. Dependency tùy chọn bị ngắt: readiness không nhất thiết fail toàn instance; alert dependency riêng vẫn hoạt động.
5. Ứng dụng bắt đầu shutdown: readiness chuyển DOWN để ngừng nhận traffic trước khi process kết thúc.
6. Heap/container memory tăng: metric và alert kích hoạt theo ngưỡng/thời gian đã định.
7. CPU throttling hoặc pool saturation: dashboard cho thấy metric liên quan và alert chỉ rõ phạm vi.
8. Health endpoint bị treo: probe timeout và hành vi restart/readiness phù hợp với cấu hình.

Test alert bằng dữ liệu mô phỏng hoặc rule test trong pipeline monitoring. Kiểm tra cả firing và resolution để tránh alert bị kẹt sau khi hệ thống phục hồi.

## 18. Checklist production

Trước khi phát hành, hãy xác nhận:

1. Startup, liveness và readiness có mục đích riêng và endpoint riêng chưa?
2. Liveness có tránh phụ thuộc vào database hoặc service bên ngoài không?
3. Readiness chỉ bao gồm dependency bắt buộc để nhận traffic không?
4. Health indicator có timeout, không có side effect và không làm tăng tải dependency không?
5. Probe timeout/failure threshold có dựa trên thời gian khởi động và latency thực tế không?
6. Health/metrics endpoint có được bảo vệ và không lộ dữ liệu nhạy cảm không?
7. Heap và container memory có được giám sát riêng không?
8. CPU usage, throttling, GC pressure và request latency có được đối chiếu không?
9. Virtual task metrics có scope rõ ràng và không bị nhầm với platform thread count không?
10. Connection pool, queue depth, wait time và rejection có alert phù hợp không?
11. Alert có owner, severity, thời gian duy trì và runbook không?
12. Các trạng thái lỗi và phục hồi đã được kiểm thử trên môi trường gần production chưa?

## Kết luận

Health check phải phân biệt startup, liveness và readiness để nền tảng biết khi nào chờ khởi động, khi nào restart và khi nào chỉ cần ngừng gửi traffic. Liveness nên tập trung vào khả năng tiến triển của process; readiness mới đánh giá dependency bắt buộc và khả năng nhận request. Metrics và alert cần theo dõi heap cùng container memory, CPU throttling, GC, thread/task, connection pool và queue. Đặt timeout, ngưỡng và thời gian duy trì dựa trên SLO và dữ liệu thực tế; bảo vệ endpoint quản trị, kiểm thử cả trạng thái lỗi lẫn phục hồi và gắn mỗi alert với hành động vận hành cụ thể.

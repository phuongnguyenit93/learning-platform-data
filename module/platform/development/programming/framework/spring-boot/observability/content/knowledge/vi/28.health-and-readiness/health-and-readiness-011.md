# Readiness khi dependency lỗi trong Spring Boot

**Readiness khi dependency lỗi** là cách ứng dụng Spring Boot quyết định một instance còn đủ điều kiện nhận request mới hay không khi database, message broker hoặc dịch vụ phụ trợ gặp sự cố. Readiness phản ánh khả năng phục vụ traffic tại thời điểm hiện tại; liveness phản ánh process có còn hoạt động và có thể tiếp tục chạy hay cần được khởi động lại. Phân biệt hai tín hiệu này giúp hệ thống tránh restart hàng loạt khi một dependency dùng chung bị gián đoạn.

Trong module **SPRING_BOOT_OBSERVABILITY**, health indicators và Actuator cung cấp dữ liệu cho orchestration, load balancer và operator. Bài thuộc chương **Health và readiness**, tập trung vào semantics readiness khi dependency lỗi, phân loại dependency bắt buộc/tùy chọn, fail-open/fail-closed, health groups, Kubernetes probes, timeout/circuit breaker, kiểm thử và quy trình phục hồi.

## 1. Readiness trả lời câu hỏi nào?

Readiness trả lời: **instance này có nên nhận thêm traffic mới ngay lúc này không?**

Một instance có thể:
- Đang chạy bình thường nhưng database chính không truy cập được.
- Vẫn phục vụ endpoint read-only dù message broker đang lỗi.
- Đã khởi động nhưng chưa hoàn tất warm-up hoặc tải cấu hình.
- Đang drain để triển khai hoặc shutdown.
- Bị quá tải và tạm thời không nên nhận request mới.

Readiness không phải điểm số sức khỏe tổng quát. Nó là quyết định định tuyến traffic dựa trên khả năng phục vụ của instance và yêu cầu workload.

### 1.1. Phân biệt liveness, readiness và startup

| Probe | Câu hỏi | Khi thất bại |
| --- | --- | --- |
| Liveness | Process có còn hoạt động và tiến triển được không? | Orchestrator có thể restart container |
| Readiness | Instance có thể nhận traffic không? | Loại instance khỏi endpoints/load balancing |
| Startup | Ứng dụng đã hoàn tất khởi động chưa? | Tạm hoãn liveness/readiness cho tới khi startup thành công |

Dependency outage thường nên ảnh hưởng readiness khi dependency thiết yếu cho request cần phục vụ. Nó không nên tự động làm liveness fail, bởi restart application không sửa được database hoặc broker dùng chung đang outage.

### 1.2. Ví dụ tình huống

Một order service phụ thuộc database chính và gửi event tới Kafka:
- Database chính down: nếu mọi request nghiệp vụ cần database, instance có thể not ready.
- Kafka down: nếu request vẫn lưu order thành công và event được ghi vào outbox để publish sau, service có thể tiếp tục ready.
- Cache down: nếu có fallback database và latency vẫn nằm trong SLO, service có thể tiếp tục ready.
- Analytics API tùy chọn down: không nhất thiết ảnh hưởng readiness.

Quyết định cần dựa trên khả năng phục vụ thực tế và business contract, không chỉ dựa trên việc dependency trả health DOWN.

## 2. Phân loại dependency trước khi đưa vào readiness

Không nên đưa tất cả dependencies vào một health aggregate rồi dùng aggregate đó làm readiness. Trước hết, phân loại theo vai trò.

| Loại dependency | Ví dụ | Ảnh hưởng readiness |
| --- | --- | --- |
| Critical synchronous | Database cần cho hầu hết request | Thường ảnh hưởng |
| Critical authentication | Identity provider nếu mọi request cần xác thực trực tiếp | Tùy token validation/cache/fallback |
| Deferred/asynchronous | Broker khi dùng transactional outbox | Có thể không ảnh hưởng |
| Optional enhancement | Cache có fallback | Thường không ảnh hưởng nếu fallback đạt SLO |
| Analytics/telemetry | Analytics sink, tracing backend | Thường không ảnh hưởng |
| External feature-specific | Payment provider chỉ dùng cho một route | Có thể ảnh hưởng riêng route/traffic class |

Readiness thường là tín hiệu cấp instance, trong khi dependency có thể chỉ ảnh hưởng một nhóm chức năng. Nếu một dependency chỉ phục vụ một endpoint hiếm dùng, loại toàn bộ instance khỏi load balancer có thể làm giảm availability của endpoint vẫn hoạt động.

### 2.1. Criticality dựa trên request path

Hãy lập bản đồ:
1. Request types mà service phục vụ.
2. Dependency nào nằm trên synchronous path của từng request.
3. Có cache/fallback/outbox/local queue hay không.
4. Thời gian fallback còn đáp ứng SLO không.
5. Khi dependency lỗi, có thể trả response có ý nghĩa không.

Readiness nên phản ánh những request quan trọng mà instance cam kết phục vụ. Không nên đánh đồng mọi dependency trong application context với dependency bắt buộc.

## 3. Fail-closed và fail-open

Khi không kiểm tra được dependency, ứng dụng cần policy rõ ràng.

- **Fail-closed:** coi dependency không xác định/không khỏe là không ready.
- **Fail-open:** tiếp tục ready nếu ứng dụng có fallback hoặc vẫn phục vụ được chức năng cốt lõi.

| Tình huống | Policy có thể phù hợp | Lý do |
| --- | --- | --- |
| Database chính không thể thực hiện request nghiệp vụ | Fail-closed | Instance không thể hoàn thành công việc cốt lõi |
| Cache không truy cập được nhưng DB fallback ổn định | Fail-open | Service vẫn có thể phục vụ |
| Broker lỗi nhưng outbox nhận event bền vững | Fail-open | Publish có thể xử lý sau |
| Tracing backend lỗi | Fail-open | Telemetry outage không nên dừng business traffic |
| Dependency tùy chọn của một feature | Tùy feature | Có thể giữ instance ready cho route khác |

Fail-open không có nghĩa bỏ qua lỗi. Cần metrics, alerts và fallback behavior để operator biết chức năng nào bị suy giảm.

Fail-closed cũng không phải luôn an toàn. Nếu tất cả instances cùng kiểm tra một database đang outage và đồng loạt not ready, load balancer có thể không còn backend nào. Điều này có thể đúng nếu không thể phục vụ request nào, nhưng cần hiểu tác động và tránh restart loop.

## 4. Cấu hình health groups trong Spring Boot

Spring Boot Actuator hỗ trợ health groups để tạo các view sức khỏe riêng, ví dụ readiness và liveness. Tùy version và cấu hình, các probe groups có thể được tạo tự động trong Kubernetes hoặc được cấu hình rõ ràng.

Ví dụ expose health:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
  endpoint:
    health:
      probes:
        enabled: true
      show-details: never
```

Các path thường gặp:
- /actuator/health/liveness
- /actuator/health/readiness

Kiểm tra path thực tế nếu đã đổi management base path hoặc management port. Không giả định endpoint path mặc định luôn tồn tại trong mọi version/configuration.

### 4.1. Nhóm readiness tùy chỉnh

Có thể định nghĩa readiness group và chọn health contributors phù hợp:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include:
            - readinessState
            - db
        liveness:
          include:
            - livenessState
```

Tên contributor như db phụ thuộc auto-configuration và ứng dụng có health indicator tương ứng. Với R2DBC, messaging hoặc custom dependency, contributor ID có thể khác. Kiểm tra endpoint health thực tế thay vì sao chép ID không tồn tại.

Readiness group ví dụ trên coi database là dependency bắt buộc. Nếu database outage thì readiness có thể DOWN. Không đưa broker/cache/telemetry vào group chỉ vì chúng có health indicator.

## 5. ReadinessState và ApplicationAvailability

Spring Boot cung cấp ApplicationAvailability và AvailabilityState để mô tả trạng thái availability của ứng dụng. Hai trạng thái thường quan trọng:
- LivenessState: CORRECT hoặc BROKEN.
- ReadinessState: ACCEPTING_TRAFFIC hoặc REFUSING_TRAFFIC.

Ứng dụng có thể chuyển readiness state khi bắt đầu drain hoặc khi điều kiện vận hành khiến instance không nên nhận traffic.

Ví dụ công bố trạng thái readiness:

```java
@Component
class TrafficAvailability {

    private final ApplicationEventPublisher events;

    TrafficAvailability(ApplicationEventPublisher events) {
        this.events = events;
    }

    void stopAcceptingTraffic() {
        events.publishEvent(
                new AvailabilityChangeEvent<>(
                        this,
                        ReadinessState.REFUSING_TRAFFIC));
    }

    void acceptTraffic() {
        events.publishEvent(
                new AvailabilityChangeEvent<>(
                        this,
                        ReadinessState.ACCEPTING_TRAFFIC));
    }
}
```

Đây là ví dụ minh họa API availability của Spring Boot. Cần import AvailabilityChangeEvent và ReadinessState từ package tương ứng với version đang dùng. Không thay đổi liveness state chỉ vì dependency từ xa bị lỗi.

## 6. HealthIndicator cho dependency bắt buộc

Spring Boot Actuator có thể tổng hợp health contributors. Với dependency riêng, có thể triển khai HealthIndicator hoặc ReactiveHealthIndicator tùy ứng dụng.

Ví dụ health indicator đồng bộ:

```java
@Component
class CriticalCatalogHealthIndicator implements HealthIndicator {

    private final CatalogClient catalogClient;

    CriticalCatalogHealthIndicator(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    @Override
    public Health health() {
        try {
            catalogClient.checkAvailability();
            return Health.up().build();
        }
        catch (Exception ex) {
            return Health.down()
                    .withDetail("dependency", "catalog")
                    .withDetail("reason", "unavailable")
                    .build();
        }
    }
}
```

Không đưa exception message, URL có credentials hoặc payload vào health details. Ví dụ chỉ kiểm tra một dependency có chủ đích; không gọi nhiều API chậm trong mỗi probe.

Với reactive application, dùng ReactiveHealthIndicator và reactive client để tránh block event-loop. Không gọi block() trong WebFlux health indicator.

### 6.1. Timeout cho health check

Health check cần timeout ngắn và hữu hạn. Nếu probe chờ dependency vô thời hạn, Kubernetes có thể liên tục timeout và không nhận được tín hiệu readiness.

Timeout cần nhỏ hơn ngân sách thời gian probe và đủ ngắn để không tạo tải lớn lên dependency đang outage. Dùng client timeout/circuit breaker phù hợp; không tạo một health request mới không giới hạn cho mỗi lần kubelet poll.

## 7. Dependency lỗi không nên làm liveness thất bại

Liveness thường nên dựa trên trạng thái nội bộ của process: application context có hoạt động không, event loop/thread có tiến triển không, ứng dụng có bị deadlock nghiêm trọng không theo cơ chế được chọn.

Nếu database down:
- Readiness có thể DOWN nếu database cần cho request cốt lõi.
- Liveness vẫn UP nếu process hoạt động bình thường.
- Orchestrator ngừng gửi traffic mới tới instance.
- Khi database hồi phục, readiness có thể UP trở lại mà không cần restart application.

Nếu gắn database health vào liveness, mọi pod có thể restart cùng lúc trong lúc database vẫn down. Sau khi database hồi phục, restart storm có thể làm connection surge và kéo dài outage.

Không dùng liveness như cách buộc application tự restart khi dependency từ xa không khỏe.

## 8. Dependency tùy chọn và degraded readiness

Một service có thể phục vụ một phần chức năng khi dependency lỗi. Một số chiến lược:

1. **Giữ ready:** nếu fallback đáp ứng contract và SLO.
2. **Not ready toàn instance:** nếu phần lớn request quan trọng không thể phục vụ.
3. **Tách workload:** triển khai endpoint/worker có dependency profile khác nhau thành workload riêng.
4. **Readiness theo traffic class:** dùng routing architecture hỗ trợ tách loại traffic, thay vì nhồi mọi điều kiện vào boolean instance-level.

Kubernetes readiness cơ bản là tín hiệu cấp pod/container. Nó không tự định tuyến riêng từng route theo dependency. Nếu chỉ payment route không hoạt động nhưng order lookup vẫn tốt, mark toàn pod not ready có thể loại cả hai loại traffic.

### 8.1. Degraded không phải trạng thái probe chuẩn

Ứng dụng có thể có trạng thái nội bộ DEGRADED, nhưng probe thường cần trả kết quả pass/fail theo contract orchestrator. Có thể expose chi tiết degraded riêng cho operator qua health group hoặc metric, còn readiness quyết định theo policy rõ ràng.

## 9. Broker lỗi, outbox và asynchronous dependencies

Message broker thường không nằm trên synchronous response path nếu ứng dụng dùng transactional outbox hoặc lưu công việc vào database trước khi publish.

Ví dụ:
1. Request tạo order và ghi order + outbox record trong cùng transaction.
2. HTTP response thành công sau commit.
3. Background publisher gửi outbox event tới broker.
4. Broker tạm thời unavailable; outbox giữ event để retry.
5. Service vẫn có thể nhận order requests nếu database còn hoạt động và outbox capacity đủ.

Trong kiến trúc này, broker outage có thể không làm readiness fail ngay. Thay vào đó theo dõi:
- Outbox backlog.
- Tuổi của message cũ nhất.
- Publish failure/retry rate.
- DLQ count.
- Thời gian dự kiến backlog drain.

Nếu broker là đường xử lý bắt buộc và không có durable fallback, readiness policy có thể khác. Quyết định theo semantics ứng dụng.

## 10. Cache, identity provider và external APIs

Không phải dependency nào cũng nên đưa vào readiness.

**Cache:** nếu cache down nhưng database fallback vẫn đáp ứng latency/throughput, giữ readiness và phát cảnh báo cache degradation.

**Identity provider:** nếu token được xác thực offline bằng public key cache, outage của identity provider có thể không ảnh hưởng request hiện tại. Nếu mọi request cần introspection trực tiếp, dependency này có thể là critical.

**External API:** nếu chỉ một chức năng phụ thuộc API, không nhất thiết mark toàn service not ready. Dùng circuit breaker, fallback và metrics theo feature.

Readiness nên thể hiện khả năng phục vụ theo contract, không phải tổng hợp trạng thái của mọi hệ thống mà service kết nối.

## 11. Circuit breaker và health check

Circuit breaker bảo vệ ứng dụng khỏi gọi dependency đang lỗi liên tục. Tuy nhiên, circuit breaker open không tự động có nghĩa instance phải not ready.

Nếu fallback hoạt động, readiness có thể tiếp tục UP. Nếu operation cốt lõi không có fallback và mọi request đều thất bại, readiness có thể DOWN.

Tránh để health check gọi qua circuit breaker theo cách khiến probe tự thay đổi breaker state hoặc tạo thêm request khi dependency đang outage. Health check nên phản ánh trạng thái cần thiết bằng thao tác nhẹ, có timeout và không gây side effect.

## 12. Kubernetes probe configuration

Ví dụ Pod spec:

```yaml
containers:
  - name: app
    image: example/order-service:1.0
    ports:
      - name: http
        containerPort: 8080
    livenessProbe:
      httpGet:
        path: /actuator/health/liveness
        port: 8080
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /actuator/health/readiness
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2
    startupProbe:
      httpGet:
        path: /actuator/health
        port: 8080
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 30
```

Các giá trị chỉ là ví dụ. Startup probe path phải phù hợp health group và app startup behavior. Khi management port riêng, probe phải truy cập đúng port/path; không để management server chỉ bind localhost nếu kubelet cần truy cập qua pod network.

### 12.1. Readiness failure ảnh hưởng traffic thế nào?

Khi readiness probe thất bại, Kubernetes đánh dấu Pod not ready và thường loại Pod khỏi endpoints dùng để route Service traffic. Container vẫn tiếp tục chạy; kubelet không restart container chỉ vì readiness thất bại.

Khi readiness phục hồi, Pod có thể được đưa trở lại endpoints. Propagation tới load balancer/service mesh có thể mất thời gian; ứng dụng vẫn cần xử lý graceful drain và connection đang mở.

### 12.2. Startup probe

Startup probe giúp ứng dụng có thời gian khởi động lâu mà không bị liveness probe restart quá sớm. Nó không thay thế readiness; sau startup thành công, readiness tiếp tục quyết định instance đã sẵn sàng nhận traffic chưa.

## 13. Tránh health check gây tải lên dependency

Kubernetes có thể gọi probe nhiều lần trên mỗi pod. Nếu mỗi lần probe tạo nhiều kết nối/query hoặc gọi một loạt external APIs, health checking có thể làm nặng thêm dependency đang outage.

Nguyên tắc:
- Dùng probe nhẹ và timeout ngắn.
- Chỉ kiểm tra dependency thực sự critical.
- Tránh query nặng hoặc scan dữ liệu.
- Không tạo retry loop dài bên trong health check.
- Cân nhắc cache kết quả trong thời gian ngắn nếu semantics cho phép.
- Giới hạn concurrency của dependency checks.
- Không gọi health check theo từng request người dùng.

Cache health result phải có TTL và trạng thái stale được hiểu rõ. Nếu cache kết quả UP quá lâu, readiness có thể tiếp tục báo healthy dù dependency đã down; nếu TTL quá ngắn, probe có thể tạo tải lớn. Chọn TTL theo failure detection objective.

## 14. Readiness, autoscaling và cascading failure

Khi dependency dùng chung bị outage, nếu tất cả application pods đồng loạt not ready:
- Service có thể không còn endpoint nào.
- Autoscaler có thể tăng số pod vì backlog/CPU, làm thêm connection tới dependency khi nó hồi phục.
- Liveness cấu hình sai có thể restart tất cả pods.
- Retry traffic có thể dồn vào instances còn lại và làm chúng quá tải.

Cần phối hợp readiness với circuit breaker, bounded retries, connection pool limits, rate limiting/load shedding, autoscaling signals, backpressure và recovery ramp-up.

Readiness không phải cơ chế duy nhất để bảo vệ hệ thống. Nó kiểm soát định tuyến traffic tới instance; dependency protection cần nhiều lớp.

## 15. Kiểm thử readiness khi dependency lỗi

Kiểm thử cần xác minh hành vi readiness và liveness khi dependency thực sự lỗi, không chỉ test HealthIndicator đơn lẻ.

### 15.1. Test health indicator

Mock dependency trả success/failure/timeout. Xác nhận health result và details đã được sanitize.

### 15.2. Integration test với Spring Boot

Dùng Spring context và Actuator endpoint để xác minh:
- Readiness group có chứa contributor dự kiến.
- Dependency critical DOWN làm readiness DOWN.
- Dependency optional DOWN không làm readiness DOWN.
- Liveness vẫn UP khi dependency remote lỗi.
- Health details không lộ credentials hoặc exception message.

### 15.3. Test outage và recovery

Dùng Testcontainers hoặc dependency giả lập có thể stop/start:
1. Khởi động application và dependency.
2. Xác nhận readiness UP.
3. Dừng dependency critical.
4. Xác nhận readiness DOWN trong thời gian phát hiện dự kiến.
5. Xác nhận liveness vẫn UP và process không restart.
6. Khởi động dependency lại.
7. Xác nhận readiness phục hồi UP.

Với dependency optional, xác nhận readiness vẫn UP nhưng degradation metric/log được ghi nhận.

## 16. Troubleshooting readiness khi dependency lỗi

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Pod restart liên tục khi DB outage | DB health bị đưa vào liveness | Tách liveness khỏi dependency remote |
| Pod vẫn nhận traffic dù DB critical down | Readiness group không chứa DB indicator | Kiểm tra group include và contributor ID |
| Pod not ready khi cache down dù có fallback | Cache bị coi là critical | Xem lại dependency classification |
| Tất cả pods not ready cùng lúc | Dependency dùng chung outage hoặc probe quá nghiêm | Kiểm tra policy và fallback |
| Readiness probe timeout | Health check gọi dependency chậm hoặc không timeout | Giới hạn timeout và số checks |
| Readiness chập chờn | Dependency health dao động hoặc TTL không phù hợp | Kiểm tra latency và cache policy |
| Readiness UP nhưng request vẫn lỗi | Probe chỉ kiểm tra process hoặc dependency khác | So sánh request path với readiness policy |
| Readiness DOWN lâu sau DB recovery | Cached state, pool chưa phục hồi hoặc indicator lỗi | Kiểm tra TTL, pool và health logs |
| Health check làm DB quá tải | Query nặng hoặc probe quá thường xuyên | Dùng check nhẹ, giảm tần suất/concurrency |
| Broker outage làm service not ready | Broker được đưa vào aggregate dù có outbox | Kiểm tra async fallback và backlog |
| Management endpoint không reachable | Port/path/bind address sai | Kiểm tra probe port và base path |
| Health details lộ dữ liệu | show-details quá rộng | Sanitize và giới hạn authorization |

### Quy trình điều tra

1. Kiểm tra Pod events và trạng thái từng probe.
2. Xác nhận probe gọi đúng management port/path.
3. Đọc readiness và liveness riêng biệt.
4. Xác định health contributor nào làm readiness DOWN.
5. Đối chiếu dependency đó với request path và fallback.
6. Kiểm tra timeout, latency, pool saturation và circuit breaker.
7. Xác nhận liveness không phụ thuộc dependency remote.
8. Kiểm tra autoscaling, retries và traffic distribution trong outage.
9. Khi dependency hồi phục, theo dõi readiness, pool và error rate.
10. Điều chỉnh policy rồi kiểm thử lại cả outage lẫn recovery.

## 17. Bài thực hành: mô phỏng database outage

Mục tiêu là chứng minh database outage làm readiness thay đổi nhưng không khiến liveness restart application.

### Chuẩn bị

- Spring Boot Actuator application.
- Database lab có thể stop/start.
- Readiness/liveness groups.
- Kubernetes hoặc môi trường mô phỏng probe.
- Metrics/logs để quan sát health transitions.

### Bước 1 — Cấu hình health probes

Bật Actuator probes và expose health endpoint. Xác nhận liveness/readiness paths hoạt động.

### Bước 2 — Đưa database vào readiness

Thêm database contributor vào readiness group nếu database là dependency bắt buộc của request path.

### Bước 3 — Giữ liveness độc lập

Đảm bảo liveness group chỉ chứa liveness state và kiểm tra process-local thực sự cần thiết.

### Bước 4 — Xác minh trạng thái ban đầu

Khởi động app/database. Gọi hai health paths và xác nhận cả hai UP.

### Bước 5 — Tạo outage

Dừng database lab hoặc chặn kết nối có kiểm soát. Xác nhận readiness chuyển DOWN trong timeout budget.

### Bước 6 — Kiểm tra process

Xác nhận liveness vẫn UP và container không restart chỉ vì database outage.

### Bước 7 — Kiểm tra traffic

Xác nhận instance not ready bị loại khỏi service endpoints, trong khi process tiếp tục chạy để phục hồi.

### Bước 8 — Phục hồi database

Khởi động database lại. Theo dõi connection pool, readiness và request success rate.

### Bước 9 — Thử dependency optional

Mô phỏng cache/broker tùy chọn outage. Xác nhận readiness giữ UP nếu fallback/outbox vẫn đáp ứng contract.

### Bước 10 — Nghiệm thu

Ghi lại thời gian phát hiện outage, readiness transition, liveness state, thời gian phục hồi và tác động traffic.

### Checklist nghiệm thu

| Điều cần chứng minh | Kết quả mong đợi |
| --- | --- |
| Probe semantics | Phân biệt startup, liveness, readiness |
| Dependency classification | Critical và optional được phân loại |
| Readiness | Critical outage làm not ready theo policy |
| Liveness | Dependency remote outage không restart process |
| Fallback | Optional outage vẫn phục vụ chức năng cốt lõi |
| Timeout | Health check có deadline hữu hạn |
| Traffic routing | Not-ready instance bị loại khỏi endpoints |
| Recovery | Readiness trở lại UP sau phục hồi |
| Security | Health details không lộ secrets |
| Load | Probe không gây tải lớn lên dependency |
| Operations | Có metrics/logs cho degraded state |
| Testing | Có kiểm thử outage và recovery |

## 18. Những nguyên tắc cần ghi nhớ

1. **Readiness quyết định nhận traffic; liveness quyết định process có cần restart.** Không dùng dependency outage làm liveness failure máy móc.
2. **Chỉ đưa dependency critical vào readiness.** Optional dependency có fallback không nên loại cả instance khỏi traffic.
3. **Phân loại theo request path và business contract.** Một dependency có thể critical cho một feature nhưng optional với phần còn lại.
4. **Fail-open/fail-closed phải có chủ đích.** Xem xét fallback, SLO và tác động khi toàn bộ replicas cùng not ready.
5. **Health check phải nhẹ và có timeout.** Probe không được làm dependency outage nặng hơn.
6. **Broker outage có thể không ảnh hưởng readiness nếu có durable outbox.** Theo dõi backlog và publish delay riêng.
7. **Tách health groups.** Liveness phản ánh process; readiness phản ánh khả năng phục vụ traffic.
8. **Readiness không phải cơ chế bảo vệ duy nhất.** Kết hợp circuit breaker, bounded retry, rate limit và backpressure.
9. **Kiểm thử cả outage lẫn recovery.** Đảm bảo readiness phục hồi mà không cần restart không cần thiết.
10. **Theo dõi degraded state riêng.** Instance vẫn ready có thể đang suy giảm một chức năng; metrics và alerts phải thể hiện điều đó.

Readiness khi dependency lỗi cần phản ánh khả năng phục vụ request thực tế của instance. Khi phân loại dependency theo request path, giữ liveness độc lập với hệ thống từ xa, đặt timeout cho health checks và kiểm thử outage/recovery, Spring Boot có thể phối hợp với Kubernetes để ngừng gửi traffic tới instance không phục vụ được mà vẫn cho process cơ hội phục hồi khi dependency hoạt động trở lại.

# Health indicator trong Spring Boot Actuator

> **Chương:** Health và readiness  
> **Bài:** Health indicator  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Health indicator là gì?

Health indicator là thành phần báo cáo tình trạng của một tài nguyên hoặc capability mà ứng dụng phụ thuộc vào. Spring Boot Actuator tổng hợp kết quả thành health endpoint để hệ thống vận hành biết ứng dụng có hoạt động bình thường, sẵn sàng nhận traffic hoặc có dependency nào đang gặp vấn đề.

Một service có thể cần database, message broker, filesystem, external API hoặc worker nội bộ. Health indicator nên trả lời một câu hỏi vận hành cụ thể, chẳng hạn database có thực hiện được một kiểm tra nhẹ hay không. Nó không nên chạy toàn bộ business workflow hoặc tạo tải lớn mỗi lần endpoint health được gọi.

~~~mermaid
flowchart TD
  A["GET /actuator/health"] --> B["HealthEndpoint"]
  B --> C["HealthContributorRegistry"]
  C --> D["DatabaseHealthIndicator"]
  C --> E["BrokerHealthIndicator"]
  C --> F["DiskSpaceHealthIndicator"]
  D --> G["Health status + details"]
  E --> G
  F --> G
  G --> H["Aggregate health response"]
~~~

Health indicator là một phần của health reporting. Nó không thay thế metrics, tracing, alerting hay synthetic tests. Health cho biết trạng thái tại thời điểm kiểm tra; metrics và traces giúp hiểu xu hướng, nguyên nhân và tác động.

## 2. HealthIndicator và HealthContributor

Spring Boot Actuator cung cấp abstraction cho các health contributors. HealthIndicator đồng bộ thực hiện kiểm tra và trả Health. ReactiveHealthIndicator cung cấp health result bất đồng bộ cho ứng dụng reactive.

~~~java
public interface HealthIndicator {
    Health health();
}
~~~

Custom indicator thường implement HealthIndicator và được đăng ký thành Spring bean. Actuator phát hiện contributor trong application context và đưa vào registry.

HealthContributor là abstraction rộng hơn, có thể là indicator đơn lẻ hoặc nhóm contributors. CompositeHealthContributor gom nhiều contributors thành cấu trúc phân cấp.

| Thành phần | Vai trò |
| --- | --- |
| HealthIndicator | Kiểm tra đồng bộ, trả Health |
| ReactiveHealthIndicator | Kiểm tra reactive, trả Publisher/Mono Health |
| HealthContributor | Abstraction chung cho health contribution |
| CompositeHealthContributor | Nhóm nhiều contributors con |
| Health | Status và details của một lần kiểm tra |
| Status | Kết quả chuẩn hóa như UP, DOWN, OUT_OF_SERVICE, UNKNOWN |

Chọn contributor theo dependency/capability có ý nghĩa với vận hành, không tạo một indicator riêng cho mọi class hoặc method.

## 3. Cấu trúc Health response

Một health result có status và có thể có details. Response minh họa:

~~~json
{
  "status": "UP",
  "components": {
    "db": { "status": "UP" },
    "diskSpace": { "status": "UP" }
  }
}
~~~

Response thực tế phụ thuộc endpoint access, show-details policy, health groups và Spring Boot version. Khi details không được phép hiển thị, caller có thể chỉ nhận status tổng hợp.

Các status phổ biến:
- UP: contributor đang hoạt động bình thường.
- DOWN: contributor không hoạt động theo kiểm tra.
- OUT_OF_SERVICE: contributor tạm thời không phục vụ.
- UNKNOWN: không xác định được trạng thái.

Status là dữ liệu vận hành, không phải exception message. Details không được lộ credential, SQL, connection string hoặc dữ liệu cá nhân.

## 4. Viết custom HealthIndicator

Ví dụ indicator kiểm tra capability lưu trữ file:

~~~java
@Component
public class ArchiveStorageHealthIndicator implements HealthIndicator {

    private final ArchiveStorageClient storageClient;

    public ArchiveStorageHealthIndicator(ArchiveStorageClient storageClient) {
        this.storageClient = storageClient;
    }

    @Override
    public Health health() {
        try {
            boolean available = storageClient.isAvailable();
            if (available) {
                return Health.up()
                        .withDetail("storage", "reachable")
                        .build();
            }
            return Health.down()
                    .withDetail("storage", "unavailable")
                    .build();
        } catch (Exception ex) {
            return Health.down(ex)
                    .withDetail("storage", "health check failed")
                    .build();
        }
    }
}
~~~

Ví dụ giả định ArchiveStorageClient có phương thức isAvailable() nhanh, an toàn và không side effect. Nếu phương thức gọi mạng, cần timeout ngắn, tránh retry dài và bảo đảm health check không làm cạn connection pool.

Không trả UP chỉ vì client object đã được tạo. Indicator cần kiểm tra đúng capability ứng dụng cần trong giới hạn thời gian/chi phí phù hợp.

### 4.1. Trả status và details có chủ đích

Details nên dùng field ổn định như dependency name, check type hoặc trạng thái đơn giản. Không chứa secret, token, password, raw exception message, query parameters hoặc payload. Không đưa stack trace vào health details; stack trace thuộc log/tracing với access và retention riêng.

## 5. ReactiveHealthIndicator

Trong ứng dụng reactive, health check có thể gọi dependency qua reactive client. Implement ReactiveHealthIndicator để không block event-loop thread.

~~~java
@Component
public class SearchServiceHealthIndicator
        implements ReactiveHealthIndicator {

    private final WebClient webClient;

    public SearchServiceHealthIndicator(WebClient.Builder builder) {
        this.webClient = builder
                .baseUrl("http://search-service")
                .build();
    }

    @Override
    public Mono<Health> health() {
        return webClient.get()
                .uri("/internal/health")
                .retrieve()
                .toBodilessEntity()
                .timeout(Duration.ofSeconds(2))
                .map(response -> Health.up()
                        .withDetail("search-service",
                                response.getStatusCode().value())
                        .build())
                .onErrorResume(ex -> Mono.just(
                        Health.down()
                                .withDetail("search-service", "unavailable")
                                .build()));
    }
}
~~~

Đây là ví dụ minh họa; cần import Reactor, WebClient và Health API phù hợp. Endpoint downstream phải là health contract nhẹ, được bảo vệ và có timeout. Không gọi business endpoint tốn kém để kiểm tra sức khỏe.

Nếu reactive indicator gọi block(), nó có thể chiếm event-loop thread và làm chính ứng dụng chậm đi. Dùng reactive API xuyên suốt và giới hạn timeout.

## 6. Status aggregation

Health endpoint tổng hợp status từ nhiều contributors. Nếu một contributor DOWN, status tổng thay đổi theo status aggregator và order cấu hình.

Ví dụ: DB UP, broker UP, disk UP thì tổng UP; DB DOWN có thể làm tổng DOWN; OUT_OF_SERVICE có mức ưu tiên theo policy.

Có thể cấu hình status order:

~~~yaml
management:
  endpoint:
    health:
      status:
        order: DOWN, OUT_OF_SERVICE, UP, UNKNOWN
~~~

Property chi tiết cần khớp Spring Boot version. Khi tùy biến status, kiểm tra cả aggregation và HTTP status mapping; tránh tạo trạng thái tùy chỉnh mà platform/probe không hiểu.

UNKNOWN không nên tự động được hiểu là UP. Nếu không thể kiểm tra, chọn semantics rõ ràng theo policy và hiển thị lý do an toàn.

## 7. HTTP status mapping cho health

Health endpoint thường map trạng thái tổng hợp thành HTTP response status. UP thường trả 200; DOWN hoặc OUT_OF_SERVICE thường map thành status lỗi service theo mapping mặc định. UNKNOWN và custom statuses cần kiểm tra cấu hình cụ thể.

Kubernetes HTTP probe thường chỉ cần phân biệt response thành công hay thất bại. Monitoring system có thể đọc JSON status và component details nếu được cấp quyền.

Đừng giả định mọi health status đều ánh xạ giống nhau giữa các version hoặc custom mapping. Kiểm tra response thật của endpoint trong profile đang chạy.

## 8. Health groups: liveness và readiness

Health groups cho phép chọn tập contributors riêng cho mục đích kiểm tra:
- Liveness: process có cần được restart hay không?
- Readiness: instance có sẵn sàng nhận traffic hay không?

Ví dụ cấu hình:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
      group:
        readiness:
          include: readinessState,db
        liveness:
          include: livenessState
~~~

Ví dụ minh họa việc include contributors. Cân nhắc kỹ có nên đưa database vào readiness: nếu API không thể phục vụ request khi DB down, readiness có thể phản ánh dependency đó; nếu chỉ một phần API cần DB hoặc dependency lỗi diện rộng, đưa DB vào readiness của mọi pod có thể loại tất cả replicas khỏi traffic.

Không đưa database/broker/network dependency thông thường vào liveness. Dependency tạm thời lỗi không có nghĩa process cần restart. Restart đồng loạt có thể làm sự cố nặng hơn.

## 9. Chọn dependency nào cho health indicator?

| Dependency/capability | Có nên có indicator? | Cân nhắc |
| --- | --- | --- |
| Primary database | Thường có | Kiểm tra nhẹ, timeout ngắn; phân biệt readiness/liveness |
| Message broker | Tùy vai trò | Nếu không thể nhận việc khi broker down, readiness có thể cần phản ánh |
| Optional recommendation API | Thường không đưa vào readiness tổng | API chính có thể vẫn hoạt động |
| Disk chứa dữ liệu bắt buộc | Có thể cần | Disk space indicator và ngưỡng hợp lý |
| External payment provider | Tùy contract | Không tạo giao dịch để kiểm tra |
| Cache | Tùy cache có bắt buộc không | Cache down có thể chỉ làm latency tăng |
| Scheduler | Có thể có capability indicator | Kiểm tra worker tiến triển, không chỉ thread còn sống |

Health policy cần gắn với khả năng phục vụ request và SLA. Optional dependency DOWN có thể chỉ cần warning/metric thay vì đánh toàn bộ service DOWN.

## 10. Không tạo health check gây tải hoặc side effect

Health check được gọi định kỳ bởi kubelet, load balancer, monitoring agent và operator. Nếu mỗi lần check chạy query nặng hoặc gọi hàng loạt dependency, health endpoint có thể trở thành nguồn tải mới.

Thiết kế tốt:
- Timeout ngắn và bounded.
- Không retry dài.
- Dùng query nhẹ hoặc native ping nếu phù hợp.
- Cache kết quả trong khoảng ngắn nếu semantics cho phép.
- Giới hạn concurrency.
- Không tạo transaction hoặc ghi dữ liệu nghiệp vụ.
- Không gọi API tạo giao dịch.
- Không làm lộ exception message.

Health endpoint phải ổn định khi dependency lỗi. Nếu indicator chờ vô hạn, probe timeout có thể tạo thêm tải và gây restart.

## 11. Health indicator và metrics/tracing

Health indicator là snapshot status. Metrics và tracing cung cấp dữ liệu theo thời gian và theo operation.

Ví dụ:
- Health: database DOWN tại thời điểm check.
- Metrics: connection pool pending tăng trong 10 phút.
- Traces: query spans chậm do lock wait.
- Logs: database connection acquisition timeout.

Không thay health check bằng một metric threshold duy nhất. Cũng không tạo health indicator cho mọi metric. Health status cần semantics rõ và phục vụ quyết định readiness/liveness.

Nếu health indicator gọi dependency qua WebClient/JDBC, call đó có thể tạo telemetry riêng. Cân nhắc tránh tạo trace/log quá nhiều do health polling nhưng vẫn giữ dữ liệu chẩn đoán cần thiết.

## 12. Health contributor dạng composite

Khi subsystem gồm nhiều thành phần, CompositeHealthContributor biểu diễn cây health.

~~~text
storage
  primary
  replica
~~~

Response có thể hiển thị status từng contributor con nếu caller có quyền xem details. Composite giúp xác định component nào lỗi mà không tạo một indicator khổng lồ.

Tên contributor nên ổn định và dễ hiểu. Tránh dùng ID instance động hoặc tenant ID làm contributor name nếu chúng tạo số lượng không giới hạn.

## 13. Health status tùy chỉnh

Ứng dụng có thể định nghĩa Status tùy chỉnh, ví dụ DEGRADED, khi dependency vẫn hoạt động nhưng capability bị suy giảm. Nếu dùng custom status:
- Xác định thứ tự ưu tiên trong StatusAggregator.
- Cấu hình HTTP mapping nếu cần.
- Xác định readiness có coi DEGRADED là sẵn sàng không.
- Đảm bảo probe/monitoring hiểu status.
- Document semantics và alert policy.

Không tạo hàng chục status tùy chỉnh cho các lỗi nhỏ. Status nên là taxonomy nhỏ và ổn định; chi tiết nằm trong health details, metrics và logs.

## 14. Bảo mật health endpoint

Health response có thể tiết lộ tên database, broker, internal service, hostname, disk path hoặc dependency topology. Chỉ expose details cho caller có quyền.

~~~yaml
management:
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
~~~

Các giá trị được hỗ trợ phụ thuộc version. Cấu hình security role phù hợp để operator đọc details, trong khi public caller chỉ thấy status tổng quát nếu policy yêu cầu.

Không đưa credential, connection URL có password, SQL statement, stack trace hoặc raw exception message vào details. Health endpoint không phải debug dump.

## 15. Kiểm thử custom health indicator

Test indicator trực tiếp với dependency mock:

~~~java
class ArchiveStorageHealthIndicatorTest {

    @Test
    void reportsDownWhenStorageIsUnavailable() {
        ArchiveStorageClient client = mock(ArchiveStorageClient.class);
        when(client.isAvailable()).thenReturn(false);

        ArchiveStorageHealthIndicator indicator =
                new ArchiveStorageHealthIndicator(client);

        Health health = indicator.health();

        assertThat(health.getStatus()).isEqualTo(Status.DOWN);
    }
}
~~~

Ngoài unit test, cần integration test endpoint:
- Contributor được đăng ký trong Spring context.
- Endpoint trả status tổng đúng.
- Readiness/liveness groups gồm đúng contributors.
- HTTP mapping khớp platform probe.
- Details bị ẩn với caller không đủ quyền.
- Timeout dependency không treo endpoint.
- Reactive indicator không block event-loop.

Không chỉ test happy path. Giả lập timeout, exception, unknown result và nhiều contributors có status khác nhau.

## 16. Troubleshooting health indicators

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Health DOWN dù API vẫn trả request | Indicator kiểm tra optional dependency | Điều chỉnh readiness membership/semantics |
| Health UP nhưng business request thất bại | Check quá nông | Kiểm tra endpoint/check contract |
| Probe timeout | Indicator block hoặc dependency không timeout | Bounded timeout, reactive/non-blocking |
| Liveness restart liên tục | Đưa dependency ngoài vào liveness | Chỉ dùng process-local liveness signals |
| Readiness tất cả replicas DOWN | Shared dependency lỗi và policy loại toàn bộ | Xem failure domain/fallback |
| Component không xuất hiện | Bean chưa đăng ký hoặc registry | Kiểm tra Spring context |
| Details không hiện | show-details/security policy | Kiểm tra role và endpoint access |
| Custom status trả HTTP không mong muốn | StatusAggregator/HttpCodeStatusMapper | Kiểm tra order và mapping |
| Reactive indicator gây thread starvation | Blocking trên event loop | Dùng reactive client và timeout |
| Health endpoint tạo nhiều load | Poll quá thường xuyên/check nặng | Làm nhẹ, cache có giới hạn |
| Health response lộ topology | show-details quá rộng | Hạn chế access và sanitize |

### Quy trình điều tra

1. Xác định endpoint/group mà probe đang gọi.
2. Kiểm tra contributors thuộc group đó.
3. Đọc status/details theo quyền được cấp.
4. Xác định check nào chậm hoặc lỗi.
5. Đối chiếu metrics, traces và dependency health.
6. Kiểm tra timeout, retry và blocking behavior.
7. Xem HTTP status mapping và probe thresholds.
8. Điều chỉnh semantics liveness/readiness thay vì chỉ nới timeout.

## 17. Tình huống thực tế: database lỗi nhưng process vẫn sống

**Bối cảnh:** order-service chạy nhiều replicas. Database có sự cố ngắn hạn. Health tổng hợp chuyển DOWN và Kubernetes liveness probe bắt đầu restart pods.

### Bước 1 — xác định indicator gây DOWN

Health response cho thấy contributor db DOWN. Process và management endpoint vẫn trả lời, nhưng database connection check thất bại.

### Bước 2 — xem probe đang dùng group nào

Nếu liveness group include db, mọi pod có thể fail liveness và restart. Restart không khôi phục database và làm mất worker capacity.

### Bước 3 — tách liveness và readiness

Liveness chỉ phản ánh process-local condition phù hợp. Readiness có thể include db nếu service không thể xử lý request nghiệp vụ khi DB unavailable.

### Bước 4 — cân nhắc failure domain

Nếu database lỗi toàn vùng, tất cả replicas có thể cùng not-ready. Đây có thể là trạng thái đúng nếu không có fallback. Nếu service có endpoint read-only hoặc cache fallback, readiness policy cần phản ánh capability thực tế.

### Bước 5 — xác minh

Mô phỏng DB outage trong môi trường test. Xác nhận:
- Liveness vẫn UP khi process bình thường.
- Readiness DOWN nếu request không thể phục vụ.
- Pod không restart loop.
- Health endpoint có timeout hữu hạn.
- Khi DB hồi phục, readiness tự trở lại UP.
- Metrics/traces/logs cung cấp nguyên nhân chi tiết.

**Kết quả mong muốn:** platform chỉ restart process khi process cần restart; traffic được điều phối dựa trên readiness semantics.

## 18. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — custom synchronous indicator

Viết HealthIndicator kiểm tra storage client. Test UP, DOWN và exception. Đảm bảo details không chứa secret hoặc raw exception message.

### Bài tập B — reactive indicator

Viết ReactiveHealthIndicator gọi mock WebClient endpoint. Kiểm tra success, HTTP error, timeout và cancellation. Xác minh không dùng block() trên event-loop.

### Bài tập C — health groups

Cấu hình liveness/readiness groups. Đặt DB chỉ trong readiness, không trong liveness. Mô phỏng DB outage và kiểm tra probe response.

### Bài tập D — aggregation và mapping

Tạo hai contributors với UP/DOWN/OUT_OF_SERVICE. Quan sát aggregate status và HTTP response. Thử status order và custom mapping trong test profile.

### Bài tập E — bảo mật

Cấu hình show-details when-authorized. Kiểm tra caller không xác thực, role OPS và probe account. Xác nhận không có credential/connection string trong response.

### Bài tập F — dependency outage

Giả lập broker/database unavailable. Đo thời gian health endpoint, pool usage và probe failures. Đảm bảo health check không tạo tải đáng kể hoặc retry storm.

### Câu hỏi tự kiểm tra

1. HealthIndicator và ReactiveHealthIndicator khác nhau thế nào?
2. HealthContributor và CompositeHealthContributor dùng khi nào?
3. UP/DOWN/OUT_OF_SERVICE/UNKNOWN biểu thị điều gì?
4. Health aggregation hoạt động thế nào khi có nhiều contributors?
5. Vì sao health details cần access control?
6. Liveness khác readiness ở quyết định vận hành nào?
7. Vì sao không nên đưa database/broker vào liveness mặc định?
8. Một health check có thể làm hệ thống quá tải như thế nào?
9. Vì sao reactive health check không nên block event-loop?
10. Health snapshot khác metrics/tracing ra sao?
11. Khi nào optional dependency không nên làm service DOWN?
12. Custom status cần cấu hình aggregation và HTTP mapping thế nào?
13. Làm sao kiểm tra indicator timeout và exception?
14. Vì sao health UP không bảo đảm mọi business request thành công?
15. Làm thế nào điều tra readiness DOWN mà không tạo restart loop?

**Tiêu chí hoàn thành:** tạo custom sync/reactive health indicator; hiểu contributor/composite và aggregation; cấu hình health groups; phân biệt liveness/readiness; giới hạn timeout/side effects; bảo vệ details; kiểm thử status mapping và outage behavior; liên kết health với metrics/traces/logs.

## 19. Ghi nhớ

- Health indicator báo trạng thái một dependency hoặc capability tại thời điểm check.
- HealthIndicator là synchronous; ReactiveHealthIndicator phù hợp reactive checks và không nên block event-loop.
- HealthContributor/CompositeHealthContributor tổ chức indicators theo subsystem.
- UP/DOWN/OUT_OF_SERVICE/UNKNOWN là status phổ biến; aggregate result phụ thuộc StatusAggregator và cấu hình.
- Liveness quyết định process có cần restart; readiness quyết định instance có nhận traffic.
- Dependency tạm thời lỗi thường nên ảnh hưởng readiness theo contract, không tự động làm liveness fail.
- Health checks phải nhẹ, bounded, timeout hữu hạn và không tạo side effect nghiệp vụ.
- Details có thể lộ topology/secrets; áp dụng show-details và authorization phù hợp.
- Health snapshot bổ sung cho metrics, traces và logs; không thay thế chúng.
- Test success, failure, timeout, status mapping, security và dependency outage trước khi dùng probes production.

## Tài liệu tham khảo

- [Spring Boot Reference — Actuator Health](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health)
- [Spring Boot Reference — Health Groups](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.health.groups)
- [Spring Boot Reference — Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)
- [Spring Boot API — HealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/HealthIndicator.html)
- [Spring Boot API — ReactiveHealthIndicator](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/ReactiveHealthIndicator.html)
- [Spring Boot API — CompositeHealthContributor](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/actuate/health/CompositeHealthContributor.html)
- [Kubernetes — Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/)


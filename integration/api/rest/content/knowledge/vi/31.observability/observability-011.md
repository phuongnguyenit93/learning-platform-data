# Dashboard, cảnh báo và liên kết tới runbook

Lúc 09:15, tỷ lệ lỗi **POST /v1/orders** tăng sau một lần triển khai. Dashboard hiển thị CPU vẫn thấp; nhân viên trực vận hành nhận 50 thông báo “5xx > 1%” từ từng pod nhưng không biết khách hàng bị ảnh hưởng đến đâu, nguyên nhân nằm ở API hay database, và phải làm gì trước. Một dashboard nhiều biểu đồ nhưng **không dẫn đến quyết định** chưa phải hệ thống quan sát hữu ích. Ngược lại, cảnh báo có **mức độ ảnh hưởng, người phụ trách, bằng chứng và liên kết runbook** giúp nhóm xác nhận sự cố, giảm thiệt hại và kiểm tra phục hồi.

Bài thuộc chương **Quan sát hệ thống** của module **INTEGRATION_API_REST**: REST API theo resource/URI, HTTP method và status rõ ràng, kết hợp phân trang, cache, idempotency, xác thực, phân quyền, lỗi và kiểm thử với Java/Spring. Chúng ta thiết kế dashboard theo hành trình một yêu cầu REST, đặt alert theo **SLI/SLO**, liên kết từ cảnh báo đến **runbook có thể thực thi**, đồng thời bảo vệ telemetry khỏi lộ thông tin nhạy cảm.

## 1. Mục tiêu và các thành phần cần phân biệt

Sau bài này, bạn có thể:

1. Chọn **SLI** đo trải nghiệm người dùng và **SLO** phù hợp với API, tránh chỉ dựa vào CPU hoặc số lượng request.
2. Thiết kế dashboard có tầng **tổng quan → route/dependency → bằng chứng trace/log → runbook**, kiểm soát time range và label cardinality.
3. Viết truy vấn PromQL cho **RPS, tỷ lệ 5xx, p95/p99 latency, 429, queue và connection pool**, biết rủi ro khi thiếu traffic.
4. Tính **error budget** và cấu hình alert **multi-window burn rate**, phân biệt cảnh báo cần đánh thức trực với thông báo cần điều tra giờ làm.
5. Thêm instrumentation bằng **Spring Boot Actuator/Micrometer** và liên kết metric với trace/span/log an toàn.
6. Tạo runbook cho sự cố API: bước xác nhận, phân luồng, giảm tác động, khôi phục và đóng sự cố.
7. Kiểm thử metric, HTTP status, Prometheus rule, đường link runbook và diễn tập sự cố; đảm bảo quyền truy cập và dữ liệu cá nhân.

| Thuật ngữ | Ý nghĩa | Ví dụ với API đặt hàng |
|---|---|---|
| **Metric** | Chuỗi thời gian số đo tổng hợp | Số request, histogram duration, pool pending |
| **Log** | Bản ghi sự kiện cụ thể | Operation ID bị trùng, lỗi kết nối DB |
| **Trace** | Hành trình các span qua service | Gateway → Orders API → DB → Payment |
| **SLI** | Tỷ lệ/độ trễ phản ánh mức dịch vụ | 99,95% request hợp lệ không gặp 5xx |
| **SLO** | Mục tiêu chất lượng trên khoảng thời gian | ≥ 99,9% request hợp lệ thành công trong 30 ngày |
| **Error budget** | Phần sai số còn được chấp nhận theo SLO | 0,1% request đủ điều kiện trong cửa sổ |
| **Alert** | Điều kiện cần con người hoặc hệ thống phản ứng | Budget bị tiêu quá nhanh trong hai cửa sổ |
| **Runbook** | Quy trình vận hành gắn với điều kiện cảnh báo | Xác định lỗi, rollback/giảm tải, xác nhận ổn định |

**Dashboard không phải nguồn sự thật của nghiệp vụ**: một request trả 202 là đã tiếp nhận xử lý, không bảo đảm job hoàn tất; 201 có thể phản ánh resource đã commit nhưng email/thanh toán sau đó còn chờ. Vì vậy cần theo dõi **cả HTTP request lẫn outcome của workflow** thay vì suy success kinh doanh từ mọi status 2xx.

## 2. Bắt đầu từ hành trình người dùng và ranh giới quan sát

Xét **POST /v1/orders** tạo đơn rồi kích hoạt payment bất đồng bộ. Người dùng quan tâm: **có tạo được đơn không?**, **mất bao lâu?**, **có bị tạo trùng khi retry?**. Operator quan tâm: **đâu là tầng đầu tiên khác thường?**, **thay đổi gần nhất là gì?**, **khả năng khôi phục ra sao?**

~~~mermaid
flowchart LR
    C["Client / SDK"] --> G["Ingress / API Gateway"]
    G --> A["Orders API"]
    A --> DB["Primary DB + Outbox"]
    A --> Q["Queue / Dispatcher"]
    Q --> P["Payment dependency"]
    A --> M["Metrics: status / latency / RPS"]
    DB --> N["Business metrics: commit / outbox lag"]
    P --> N
    G --> T["Trace context"]
    A --> T
    P --> T
    M --> D["Dashboard + SLO"]
    N --> D
    D --> E["Alert → Runbook → Owner"]
~~~

Một **request ID** giúp hỗ trợ tra cứu một HTTP request; **trace ID** nối các span được instrument; **operation ID/idempotency key** xác định *logical operation* qua nhiều lần retry. Chúng phục vụ các mục đích khác nhau. Không dùng raw idempotency key, JWT hoặc user ID làm metric label; khi cần liên kết dữ liệu, dùng ID ngẫu nhiên trong log có giới hạn truy cập và retention.

### 2.1. Chọn điểm đo theo nhóm

| Cấp quan sát | Tín hiệu tối thiểu | Câu hỏi |
|---|---|---|
| **Người dùng/API** | RPS, 5xx, p95/p99, timeouts, 429, synthetic probes | Người dùng thật có gọi API thành công không? |
| **Nghiệp vụ** | Orders committed, failed, idempotency replay, payment pending, outbox age | HTTP 2xx có dẫn đến kết quả như mong đợi không? |
| **Dependency** | DB pool active/pending, query errors, broker backlog, external API errors | Nút thắt nằm ở đâu? |
| **Tài nguyên (USE)** | Utilization, saturation, errors: CPU, heap, threads, connection/queue | Hết capacity, nghẽn hay lỗi phần cứng/hạ tầng? |
| **Thay đổi** | Release version, rollout/canary, config/feature flag, deploy timestamp | Bất thường có trùng với thay đổi nào? |

Hai bộ khung bổ sung cho nhau: **RED** (Rate, Errors, Duration) tập trung service HTTP; **USE** (Utilization, Saturation, Errors) tập trung tài nguyên. Chỉ đo RPS và CPU sẽ bỏ lỡ các tình huống **DB lock, connection pool chờ, idempotency backlog hoặc lỗi thu hồi quyền**.

### 2.2. Gắn tín hiệu quan sát với HTTP contract

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: order-operation-31
Content-Type: application/json

{"cartId":"cart-19"}
~~~

Khi downstream đang quá tải, một response có thể là:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 10
Cache-Control: no-store
Content-Type: application/problem+json

{"type":"about:blank","title":"Service unavailable","status":503}
~~~

Metrics HTTP ghi một **attempt có status 503**, còn trace/log cho biết đang chờ pool, dependency hay lỗi deploy. Nhưng nếu DB đã commit trước khi response thất lạc, **503/timeout không chứng minh operation thất bại**: monitoring phải liên kết được **operation record/idempotency replay** thay vì đếm một HTTP attempt thành một đơn bị mất. **401/403** là tín hiệu xác thực/phân quyền và có thể là lỗi cấu hình IdP; **429** do quota hợp lệ khác **503** do hệ thống quá tải. Mỗi loại cần dashboard và runbook phù hợp.

## 3. Định nghĩa SLI/SLO trước khi viết biểu đồ

Một SLI về **availability của API** cần có tử số và mẫu số minh bạch. Ví dụ với nhóm route đặt hàng, xét các request hợp lệ nhận **2xx/3xx/5xx** và coi **5xx là lỗi dịch vụ**:

\[
\mathrm{errorRate} = \frac{\text{số request 5xx đủ điều kiện}}{\text{số request 2xx + 3xx + 5xx đủ điều kiện}}
\]

SLO availability **99,9% trên 30 ngày** tương đương error budget **0,1% số request đủ điều kiện**, không mặc nhiên tương đương đúng 43 phút downtime nếu traffic không đều. **401/403/400/404 do client** có thể loại khỏi SLI availability này, nhưng vẫn phải quan sát riêng. **429** cần có chính sách: rate limit hợp lệ do user vượt quota có thể không là lỗi service; 429 do hệ thống áp limit quá chặt khiến khách hợp lệ không mua được thì là tín hiệu tổn hại khách hàng, không được lờ đi.

**Không tính cả metrics scraping, health probe hoặc route nội bộ** vào mẫu số của SLO người dùng, và tránh đưa response 202 vào “payment successful” nếu payment là công việc sau. Một **client timeout** có thể xảy ra dù API cuối cùng trả 200; cần cả tín hiệu client/gateway hoặc synthetic SLI, không coi metric chỉ có 5xx phía server là toàn bộ trải nghiệm.

### 3.1. Availability, latency và kết quả nghiệp vụ

| SLI | Ví dụ định nghĩa | Tránh nhầm |
|---|---|---|
| **Request availability** | 1 − (5xx / eligible requests), trong 30 ngày | 4xx bị loại phải có lý do |
| **Latency** | Tỷ lệ POST đủ điều kiện hoàn thành trong 500 ms | p95 không nói gì về mọi request |
| **Checkout correctness** | Đơn committed không duplicate / tổng logical order được xác nhận | Một POST retry có thể nhiều HTTP request |
| **Async completion** | Job được xử lý thành công trong 2 phút / job đã nhận hợp lệ | 202 không phải completed |
| **Data freshness** | P99 outbox age hoặc replica lag theo giới hạn | Trễ không nhất thiết là HTTP 5xx |

Với histograms, tỷ lệ latency dưới ngưỡng có thể tính từ **bucket <= 500 ms** chia tổng count. Đừng lấy trung bình của p95 từ từng pod để tạo “p95 toàn service”: **percentile không cộng/trung bình được như counter**. Cần gộp **bucket counters** rồi tính histogram_quantile, hoặc dùng một phương pháp sketch/distribution phù hợp để tổng hợp đúng.

### 3.2. Error budget và burn rate

Cho SLO 99,9%, phần lỗi cho phép **e = 1 − 0,999 = 0,001**. Nếu error rate trong cửa sổ là **1,44%**, tốc độ tiêu budget (burn rate) bằng **0,0144 / 0,001 = 14,4 lần**. Với lượng request đủ lớn và phân bố đủ đại diện, mức 14,4 trong một giờ xấp xỉ tiêu **2% budget của cửa sổ 30 ngày** nếu xét theo thời gian với lưu lượng tương đương. Khi traffic biến động, hãy kiểm tra cả **tỷ lệ lỗi và số request đủ điều kiện**.

**Alert theo burn rate** tốt hơn một ngưỡng 5xx cố định cho mọi route: nó phản ánh mức đe dọa đối với SLO. Tuy nhiên burn rate không tự xác định nguyên nhân; một alert tốt còn cần route/service/region liên quan, dashboard, trace và runbook.

## 4. Thiết kế dashboard: từ triệu chứng đến hành động

Dashboard tốt cần một **độc giả và một quyết định**. Dashboard trực vận hành trả lời “Có đang ảnh hưởng khách không, ở đâu, cần làm gì?”; dashboard nhóm phát triển trả lời “Thành phần nào đang chậm/lỗi?”; dashboard sản phẩm trả lời “Bao nhiêu logical order hoàn tất?”. Đừng ghép 100 biểu đồ không có phân cấp vào một trang.

### 4.1. Tầng 1: Service overview dành cho người trực

| Vị trí | Panel | Cách đọc/điều hướng |
|---|---|---|
| Trên cùng | **SLO 30 ngày, budget còn, trạng thái alert đang mở** | Tác động hiện tại và mức ưu tiên |
| Hàng 1 | **Request rate; tỷ lệ lỗi 5xx; p50/p95/p99 latency** | So sánh cùng time range, xem deployment annotations |
| Hàng 2 | **Error rate theo URI template và method; 429/503** | Xác định nhóm route bị ảnh hưởng, drill down |
| Hàng 3 | **DB pool pending, outbox age, queue backlog, external service latency** | Tìm nguyên nhân trước mắt |
| Hàng 4 | **Committed orders, duplicate suppressed, payment pending/failed** | Tách lỗi HTTP khỏi kết quả nghiệp vụ |
| Cạnh panel | **Owner/on-call, liên kết runbook, thời gian deploy gần nhất** | Operator không phải đi tìm tài liệu |

Trên từng panel, thống nhất **UTC hoặc timezone được hiển thị rõ, độ dài cửa sổ, đơn vị** (request/s, ms/s, %, byte, count) và nhãn **service, environment, region, route template**. Cho phép lọc bằng biến chọn tenant/region **chỉ khi quyền truy cập và cardinality cho phép**. Panel overview nên ưu tiên **tổng hợp theo service/region**, không hiện từng user, UUID resource, path thô hoặc token.

### 4.2. Tầng 2: Drill-down từ route đến bằng chứng

Khi dashboard cho thấy POST /v1/orders có p99 cao, click đến trang chi tiết của route với: **latency histogram**, số request theo status, deployment version, pool chờ, DB slow query, downstream timeout, retry, idempotency replay và tỷ lệ commit. Tiếp tục từ metric **exemplar (nếu exporter/tracing hỗ trợ)** tới một trace, rồi từ trace ID tới log đã được lọc.

**Link phải giữ time range, service, region và route** khi điều hướng. Nếu alert phát hiện sự cố lúc 09:15 mà dashboard mở “Last 5 minutes” vào 10:00, người nhận sẽ không thấy vấn đề ban đầu. Alert payload nên mang **startsAt, labels có cardinality thấp và deep link đã dùng time range phù hợp**; một runbook không nên bắt người trực nhập lại tất cả thông tin.

### 4.3. Ba anti-pattern thường gặp

1. **Dashboard theo pod nhưng không có view toàn service:** pod bị restart làm counter reset và tổng số liệu sai; người trực không thấy tác động chung.
2. **Biểu đồ “API latency trung bình” duy nhất:** tail latency có thể gấp hàng chục lần p50; p99 và bucket distribution giúp phát hiện nhóm bị kẹt.
3. **Đồ thị error rate không có request volume:** 1 lỗi/1 request có thể tạo 100% error rate lúc traffic cực nhỏ, cần hiển thị numerator/denominator và kết hợp chính sách alert ít traffic.

## 5. Truy vấn PromQL cho REST API

Ví dụ giả định metric **http.server.requests** do Micrometer xuất sang Prometheus thành **http_server_requests_seconds_count**, **_sum** và (khi bật histogram phù hợp) **_bucket**. Các label thường có **application, uri, method, status, outcome** nhưng có thể khác giữa version/registry/filter và cấu hình. **Phải kiểm tra tên và label thực tế ở endpoint metrics** thay vì copy query và mặc định nó sẽ có dữ liệu.

### 5.1. Request rate và lỗi HTTP

~~~promql
# Tổng request/giây cho orders API, bỏ qua health/metrics.
sum(rate(http_server_requests_seconds_count{
  application="orders-api",uri=~"/v1/orders.*"
}[5m]))

# 5xx request/giây theo route template.
sum by (uri,method) (
  rate(http_server_requests_seconds_count{
    application="orders-api",uri=~"/v1/orders.*",status=~"5.."
  }[5m])
)

# 429 request/giây; xem riêng để phân biệt quota với service overload.
sum by (uri) (
  rate(http_server_requests_seconds_count{
    application="orders-api",status="429"
  }[5m])
)
~~~

Một SLI availability theo định nghĩa ở mục 3:

~~~promql
sum(rate(http_server_requests_seconds_count{
  application="orders-api",uri=~"/v1/orders.*",status=~"5.."
}[5m]))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    application="orders-api",uri=~"/v1/orders.*",
    status=~"2..|3..|5.."
  }[5m])),
  0.000001
)
~~~

Đây là **tỷ lệ lỗi**, không phải availability; availability = **1 − tỷ lệ đó**. **clamp_min** chỉ chống chia cho 0, không biến cửa sổ không có request thành bằng chứng hệ thống khỏe. Với no traffic, cần panel/tín hiệu **no-data** riêng, probe hoặc điều kiện request volume. Không loại **5xx** khỏi mẫu số và không chỉ dùng **200** cho mẫu số nếu API có 201/202/204 thành công.

### 5.2. Latency toàn service và theo route

~~~promql
# p95 latency tính từ histogram bucket đã gộp qua replica.
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{
      application="orders-api",uri=~"/v1/orders.*"
    }[5m])
  )
)

# p99 cho một route cụ thể.
histogram_quantile(
  0.99,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      application="orders-api",uri="/v1/orders",
      method="POST"
    }[5m])
  )
)
~~~

Đơn vị ở đây là **giây**, giao diện có thể chuyển sang ms. Query histogram_quantile yêu cầu histogram buckets thực sự được phát; nếu chỉ có **count/sum**, không thể tính p95/p99 chính xác từ trung bình. Histograms có sai số xấp xỉ tùy ranh giới bucket. Chọn bucket quanh mục tiêu SLO (ví dụ **100 ms, 300 ms, 500 ms, 1 s, 2 s**) thay vì giả định các bucket mặc định đủ chi tiết.

Nếu cần SLI “tỷ lệ request dưới 500 ms”, dùng bucket **le="0.5"** khi tồn tại và so với tổng count của đúng cùng tập route/status. Các metric client-side/gateway cũng cần so với latency server-side để tìm khoảng thời gian mất ở mạng, TLS, queue hoặc proxy.

### 5.3. Cách chọn label, rate và phép tổng hợp

- Counter phải dùng **rate()/increase()**, không lấy counter tăng mãi làm “RPS”. Rate của từng series nên được tính **trước khi sum**, để xử lý reset khi pod restart.
- **uri** phải là **route template** như /v1/orders/{id}; không dùng path thực /v1/orders/8bf... làm label, gây cardinality cao.
- Khi tính tổng toàn service, không bình quân tỷ lệ 5xx của các pod: dùng **tổng số 5xx / tổng eligible requests** để cân đúng traffic.
- Không trộn staging và production; chọn **application, environment, cluster/region** rõ ràng.
- Khi có **scrape gaps**, backend metric và dashboard phải có alert về thiếu telemetry; không coi chuỗi bằng 0 là tình trạng khỏe.

Các counter như **orders committed, idempotency replay, outbox pending** nên đặt tên rõ nghĩa với unit, có owner và nguồn commit. Đừng tăng counter “committed” ngay khi DTO qua validation hay JPA save: metric business phải khớp **mốc transaction commit**.

## 6. Instrumentation với Java, Spring Boot và Micrometer

**Spring Boot 3 / Spring Framework 6** hỗ trợ Micrometer Observation và Actuator cho HTTP server observations; exporter Prometheus cần dependency tương ứng. Ví dụ Maven/Gradle project có **spring-boot-starter-web, spring-boot-starter-actuator, micrometer-registry-prometheus** (và Spring Security nếu là API được bảo vệ). Nếu dùng trace xuất ra OTLP, bổ sung Micrometer Tracing bridge và exporter tương thích với phiên bản Spring Boot.

### 6.1. Cấu hình endpoint và histogram

~~~properties
spring.application.name=orders-api
management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.health.probes.enabled=true
management.metrics.tags.application=orders-api
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=100ms,300ms,500ms,1s,2s
~~~

**Endpoint /actuator/prometheus phải được bảo vệ**: dùng listener/network nội bộ, mTLS hoặc cơ chế xác thực scraper, network policy và rule Spring Security phù hợp; **không xuất public internet** chỉ vì cần Grafana. Kiểm tra endpoint thực tế sau startup vì port/base path có thể được cấu hình khác. Bật histogram gây tăng số series/bucket; giữ những SLI quan trọng, đo chi phí Prometheus trước khi bật mọi metric.

Đối với API JWT, **SecurityFilterChain** phải xác thực token và kiểm tra issuer/audience/scope; metrics không thể thay xác thực/phân quyền. Nếu ứng dụng có liveness/readiness, test chính sách expose của actuator riêng, không cho endpoint quản trị nhạy cảm truy cập chung với route khách hàng.

### 6.2. Đo kết quả nghiệp vụ sau ranh giới commit

HTTP auto-instrumentation ghi nhận thời gian và status, nhưng **không biết transaction business nào đã commit**. Một lớp facade bên ngoài transactional service có thể đếm kết quả sau khi service proxy đã trả về:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

record OrderReceipt(String id, String status) {}
record VerifiedActor(String tenantId, String userId) {}
record CreateOrderRequest(String cartId) {}

interface TransactionalOrderService {
    // Bean thực thi @Transactional qua Spring proxy; chỉ trả sau commit.
    OrderReceipt create(VerifiedActor actor, CreateOrderRequest request);
}

@Component
class OrderCreationTelemetry {
    private final TransactionalOrderService orderService;
    private final MeterRegistry metrics;

    OrderCreationTelemetry(
            TransactionalOrderService orderService,
            MeterRegistry metrics) {
        this.orderService = orderService;
        this.metrics = metrics;
    }

    OrderReceipt create(VerifiedActor actor, CreateOrderRequest request) {
        Timer.Sample duration = Timer.start(metrics);
        try {
            OrderReceipt receipt = orderService.create(actor, request);
            metrics.counter("orders.create.transaction",
                    "result", "returned_after_commit").increment();
            return receipt;
        } catch (RuntimeException error) {
            metrics.counter("orders.create.transaction",
                    "result", "exception").increment();
            throw error;
        } finally {
            duration.stop(metrics.timer("orders.create.duration",
                    "operation", "create"));
        }
    }
}
~~~

**Điều kiện quan trọng:** interface được implement bằng một **Spring-managed @Transactional bean** và gọi qua proxy; nếu là self-invocation không qua proxy, giả định “trả về sau commit” có thể sai. **returned_after_commit** chỉ nghĩa local service method đã trả sau commit được xác nhận, **không** có nghĩa HTTP response đã tới client hoặc payment đã hoàn thành. **exception** cũng không chứng minh rollback, vì có thể mất kết nối khi commit hoặc lỗi ở callback sau commit; muốn kết luận bền vững cần **operation ID và database reconciliation**.

Không đặt **tenantId, userId, cartId, raw URI hoặc token** làm tag cho counter/timer: số series sẽ tăng theo số khách hàng, đồng thời tạo rủi ro rò thông tin. Thay bằng các giá trị **operation, outcome, service, region** thuộc tập hữu hạn. Với metrics nghiệp vụ quan trọng, xác định rõ ai tăng counter sau replay idempotent: một lần **logical commit** nên có cách đếm riêng với nhiều **HTTP attempts**.

### 6.3. Tracing và logs tương quan đúng cách

**W3C Trace Context** dùng header **traceparent** để kết nối trace qua gateway và Java HTTP client khi instrumentation được bật. Một trace có thể chỉ ra span DB chậm, queue delay hoặc upstream 503; logging có thể tra theo trace ID/span ID nếu cấu hình correlation. Ví dụ log an toàn:

~~~json
{
  "timestamp": "2026-11-18T09:15:21Z",
  "level": "WARN",
  "service": "orders-api",
  "traceId": "81bf2f4b7e1f46b38b63128a9f6c2385",
  "spanId": "7a0823d41c752e93",
  "route": "POST /v1/orders",
  "operationType": "create-order",
  "errorCode": "DB_POOL_EXHAUSTED",
  "durationMs": 1900
}
~~~

Đây là ví dụ schema log, **không** tự sinh ra từ ứng dụng nếu chưa cấu hình structured logging và tracing exporter. Không log JSON body chứa thông tin giao hàng/thẻ, mật khẩu, Authorization, Cookie, API key hoặc idempotency key thô. Một **X-Request-Id từ client** có thể giả mạo; nếu dùng, kiểm soát độ dài/ký tự và không coi nó là danh tính đáng tin. Sampling tracing cần có chính sách: request hiếm, lỗi quan trọng và tỷ lệ traffic cao có thể cần chiến lược khác nhau, nhưng **không xem trace sampled là số liệu thống kê đầy đủ** thay metric counter.

## 7. Thiết kế cảnh báo: tín hiệu hành động, không phải “biểu đồ đỏ”

Một cảnh báo phục vụ **người trực** phải thỏa ba điều kiện: có tác động đủ nghiêm trọng để cần hành động **ngay**, có **hướng chẩn đoán/giảm ảnh hưởng** và có **owner chịu trách nhiệm**. Nếu chỉ là dấu hiệu nên điều tra khi rảnh, tạo ticket hoặc ghi dashboard, không đánh thức cả đội lúc nửa đêm.

### 7.1. Phân loại cảnh báo và mức ưu tiên

| Điều kiện | Mức phù hợp | Hành động |
|---|---|---|
| Multi-window SLO burn rate rất cao, traffic đủ | **Page** | Xác nhận impact, kích hoạt runbook, giảm ảnh hưởng |
| Burn rate tăng vừa phải trong nhiều giờ | **Ticket/working hours** hoặc page theo policy | Điều tra dependency/capacity trước khi budget cạn |
| Synthetic checkout fail ở nhiều vùng | **Page** nếu user journey quan trọng | Kiểm tra gateway, auth, DNS/TLS và backend |
| p99 tăng trên một route nhưng không vượt SLO | Warning/quan sát | Đo tail latency, tối ưu trước khi ảnh hưởng lớn |
| Redis/DB pool saturation gần ngưỡng | Warning hoặc page khi có user impact | Admission/retry/capacity; tránh alert flood |
| Một pod restart đơn lẻ | Thường **không page** nếu HA ổn | Theo dõi, xử lý khi replica mất HA/impact |
| Quota 429 tăng do chiến dịch hợp lệ | Business/security review | Phân biệt limit policy với capacity overload |

**Pager fatigue** là lỗi thiết kế: một incident làm 100 pod cùng phát alert không thêm 100 nguyên nhân. Nên **group by service, region, alertname**, deduplicate và route đến owner chính; pod/instance là thông tin chẩn đoán, không nên làm mỗi instance thành một page độc lập. Có policy maintenance/silence có thời hạn và audit, không để silence vô hạn che sự cố thật.

### 7.2. Multi-window, multi-burn-rate theo SLO

Với SLO 99,9% trên 30 ngày, một cách thiết kế cảnh báo phổ biến là đồng thời nhìn **1 giờ và 5 phút** với burn rate **14,4** để page khi lỗi kéo dài đủ, và **6 giờ + 30 phút** với burn **6** cho tình huống nghiêm trọng nhưng chậm hơn. Các cửa sổ/threshold này là **mẫu khởi đầu cần hiệu chỉnh** theo lưu lượng, tính mùa vụ và chính sách trực, không thay đo tác động thật.

Ví dụ quy tắc recording và alert trong Prometheus. Chọn cùng nhóm route và status như SLI mục 3; ở production nên quản lý các biểu thức dài bằng rule templates và kiểm tra label consistency:

~~~yaml
groups:
  - name: orders-slo
    interval: 30s
    rules:
      - record: orders:eligible_requests:rate5m
        expr: sum(rate(http_server_requests_seconds_count{application="orders-api",uri=~"/v1/orders.*",status=~"2..|3..|5.."}[5m]))
      - record: orders:server_errors:rate5m
        expr: sum(rate(http_server_requests_seconds_count{application="orders-api",uri=~"/v1/orders.*",status=~"5.."}[5m])) or vector(0)
      - record: orders:error_ratio:rate5m
        expr: orders:server_errors:rate5m / clamp_min(orders:eligible_requests:rate5m, 0.000001)
      - record: orders:eligible_requests:rate1h
        expr: sum(rate(http_server_requests_seconds_count{application="orders-api",uri=~"/v1/orders.*",status=~"2..|3..|5.."}[1h]))
      - record: orders:server_errors:rate1h
        expr: sum(rate(http_server_requests_seconds_count{application="orders-api",uri=~"/v1/orders.*",status=~"5.."}[1h])) or vector(0)
      - record: orders:error_ratio:rate1h
        expr: orders:server_errors:rate1h / clamp_min(orders:eligible_requests:rate1h, 0.000001)
      - alert: OrdersHighErrorBudgetBurn
        expr: |
          (orders:error_ratio:rate1h > 0.0144)
          and (orders:error_ratio:rate5m > 0.0144)
          and (orders:eligible_requests:rate1h > 0.1)
        for: 2m
        labels:
          severity: page
          team: orders
          service: orders-api
        annotations:
          summary: "Orders API consuming error budget rapidly"
          description: "Verify 5xx numerator, request volume and recent deploys."
          runbook_url: "https://runbooks.example.test/orders/availability"
          dashboard_url: "https://observability.example.test/d/orders-overview"
~~~

**0,0144 = 14,4 × 0,001**, tức ngưỡng error rate **1,44%** theo SLO 99,9%. Điều kiện **0,1 request/s trên cửa sổ 1 giờ** minh họa cổng volume, không phải giá trị mặc định đúng cho mọi hệ thống; nếu traffic thấp nhưng API critical, thêm **synthetic check** và alert no-data thay vì che lỗi. Rule này chỉ tạo **một alert tổng orders-api**; muốn phân theo region, thay tổng hợp thành **sum by(region)** nhất quán cho tất cả recording rule và alert, rồi test hoạt động ghép nhãn.

**Vấn đề kỹ thuật cần nhớ:** nếu service chưa có 5xx, series chọn status=5xx có thể chưa tồn tại. Quy tắc minh họa dùng **or vector(0)** cho **numerator tổng không có nhãn**, nhưng denominator vẫn cần eligible traffic. Với rule phân nhóm theo region/route, phải tạo zero theo cùng tập nhãn; đồng thời kiểm tra **scrape gaps/no traffic** riêng. **Không gán mọi scrape gap thành healthy**. Bổ sung selector environment/cluster để không trộn staging vào production.

### 7.3. Alert payload và Alertmanager routing

Alert phải có **severity, owner/team, service, region khi cần, SLO/threshold, thời điểm bắt đầu**, và các annotation **summary, dashboard_url, runbook_url**. Công cụ quản lý sự cố cần có người trực dự phòng/escalation. Cấu hình Alertmanager nên **group, deduplicate, inhibit warning khi critical cùng nguyên nhân và đặt repeat interval hợp lý**; đồng thời không đè mute cho sự cố độc lập. Nếu phân quyền dashboard/runbook yêu cầu SSO, thử liên kết bằng **tài khoản trực thật**, không chỉ trên máy người tạo dashboard.

Không nhét **trace ID của một khách hàng, JWT, email hoặc raw URL có token** vào alert gửi qua các hệ thống chat/pager có retention khác nhau. Đặt các link tới trang nội bộ truy cập theo least privilege; mọi link trong ví dụ trên dùng domain **example.test để minh họa**, không phải hệ thống đang được triển khai.

## 8. Runbook liên kết từ cảnh báo: người trực làm gì?

**Runbook khác tài liệu kiến trúc**: kiến trúc giải thích hệ thống hoạt động thế nào; runbook phải trả lời **khi nào dùng, xác nhận bằng gì, làm gì an toàn và khi nào dừng/escalate**. Nội dung phải tồn tại ở nơi người trực có quyền truy cập ngay khi xảy ra sự cố; liên kết hỏng, trang yêu cầu VPN không dùng được hoặc nội dung chỉ gồm “check logs” làm mất ý nghĩa của alert.

### 8.1. Mẫu runbook cho OrdersHighErrorBudgetBurn

Tên: **RB-ORDERS-AVAILABILITY** (bản 1.0, owner: đội Orders Platform).

Kích hoạt: alert **OrdersHighErrorBudgetBurn** hoặc synthetic order journey thất bại; vùng ảnh hưởng có trong alert. Mục tiêu: **giảm ngay lỗi đối với người dùng, bảo toàn đơn hàng/tiền và kiểm chứng phục hồi**. Liên kết: orders overview dashboard, route drill-down, trace search, deployment history và on-call escalation (được cấu hình trong hệ thống thực, ví dụ domain example.test ở trên).

**Bước 1 — Xác minh trong vài phút đầu**

- Mở dashboard đúng **time range từ startsAt**, kiểm tra request eligible, số lỗi 5xx, p95/p99 và synthetic probe. Nếu không có traffic hoặc metrics missing, phân biệt **no-data** với outage thật.
- Xác định **route, region, phiên bản deploy và nhóm khách hàng** bị ảnh hưởng; kiểm tra 401/403, 429 và 503 riêng để tránh gộp chính sách xác thực/limit vào lỗi DB.
- Lấy **một vài trace mẫu** có quyền truy cập phù hợp; nối với log bằng trace ID, không chụp token hoặc payload khách hàng vào incident channel.

**Bước 2 — Chọn nhánh điều tra theo bằng chứng**

| Bằng chứng | Nhánh kiểm tra |
|---|---|
| 5xx tăng ngay sau deploy | So canary/previous release, config/feature flag, migration compatibility |
| DB pool pending tăng, query latency cao | Connection saturation, lock contention, slow query, DB health |
| Upstream payment 5xx/timeout tăng | Circuit breaker, retry storm, dependency SLA, outbox state |
| Queue/outbox age tăng nhưng HTTP POST vẫn 201/202 | Job/workflow chưa hoàn tất, consumer lag, poison messages |
| 429 tăng chỉ ở tenant/route cụ thể | Rate-limit policy, traffic thực, abuse, false positive |
| Chỉ một region lỗi | Ingress, DNS/TLS, regional dependency, traffic routing |

**Bước 3 — Giảm tác động có kiểm soát**

- Nếu rollout mới là thủ phạm, **rollback hoặc tắt feature flag** theo quy trình đã được phê duyệt và kiểm tra tương thích schema/traffic; rollback code khi migration không tương thích có thể làm sự cố nặng hơn.
- Khi downstream quá tải, cân nhắc **admission control, giới hạn retries, bulkhead/circuit breaker** hoặc tạm giảm workload nền; theo dõi độ đầy queue và tránh nhân đôi request tài chính.
- Nếu thiếu capacity, tăng replica/connections **chỉ sau khi xác định bottleneck thật**; tăng replica API không giúp khi DB đã cạn connection.
- **Không tắt authorization, idempotency, audit hoặc xóa queue/DB để “xanh biểu đồ”**. Với payment outcome chưa rõ, giữ trạng thái PENDING/UNKNOWN và đối soát thay vì retry cùng lệnh với operation key mới.

**Bước 4 — Xác nhận phục hồi và đóng incident**

- Quan sát tỷ lệ lỗi, p95/p99, synthetic probe và số request đủ điều kiện **trong nhiều cửa sổ**, không đóng ngay sau một phút 0 lỗi.
- Kiểm tra **orders committed, idempotency replay, payment pending và outbox backlog** đã về mức chấp nhận được; có thể HTTP khỏe lại trong khi backlog đang mất dữ liệu.
- Ghi timeline, tác động khách hàng, mitigation, liên kết trace/dashboard và follow-up owner; **postmortem** phải cập nhật alert/runbook khi phát hiện thiếu bước.

Nội dung trên là **mẫu**: khi triển khai thật, cần người trực cụ thể, môi trường, quyền truy cập, dashboard ID và **lệnh rollback được kiểm chứng, có điều kiện an toàn**. Không đưa shell command mang tính phá hủy vào runbook chung nếu chưa có cơ chế review/approval; mọi thao tác thay đổi dữ liệu production phải đi theo runbook chuyên biệt được phê duyệt.

### 8.2. Các runbook cần thiết khác cho REST API

| Alert | Runbook nên giải thích | Tại sao không thể dùng chung một kịch bản |
|---|---|---|
| **OrdersAvailabilityBurn** | 5xx, dependency, rollback, khách bị ảnh hưởng | Ưu tiên HTTP success và correctness |
| **OrdersLatencyBurn** | Tail latency, DB/pool, queue, SLO threshold | Có thể chậm nhưng vẫn 200; cần phân tích p99 |
| **OrdersHigh429** | Rate policy, retry storm, fair tenant handling | 429 có thể là giới hạn hợp lệ, không phải lỗi server |
| **OrdersOutboxLagHigh** | Dispatcher/consumer, DLQ, operation reconciliation | 201/202 không chứng minh completion |
| **OrdersNoTelemetry** | Scrape target, exporter, network policy, missing metrics | Không có metric không có nghĩa không có lỗi |
| **OrdersAuthAnomaly** | 401/403 bất thường, IdP/JWKS, abuse và rotation | Không được tắt xác thực để thử sửa latency |

Runbook cho **429** cần nêu cách nhận biết user thực bị chặn nhầm, xác minh quota theo actor/tenant và điều kiện Retry-After; không tự tăng limit toàn cục vì một đối tác gây traffic lớn. Runbook cho **idempotency replay hoặc payment** cần luôn tách **HTTP attempts** khỏi **logical operation**, và không biến việc giảm error-rate thành double charge.

### 8.3. Phiên bản và vòng đời runbook

Mỗi runbook có **owner, ngày review, trigger/alert name, phạm vi service, prerequisite, rollback/fallback, escalation, tiêu chí đóng, link dashboard/query**. Khi đổi route, PromQL metric name, deployment hoặc đội trực, cập nhật **dashboard, alert và runbook trong cùng quy trình thay đổi**. Link nên là đường dẫn ổn định có thể redirect khi đổi cấu trúc tài liệu. Kiểm thử quyền truy cập, link nội bộ và tính đúng của panel bằng tài khoản có quyền giống người trực.

## 9. An toàn, bảo mật và tính đúng của telemetry

**Observability pipeline là hệ thống chứa dữ liệu vận hành nhạy cảm**. Mặc dù log/trace không phải response API, chúng có thể để lộ địa chỉ, access token, tài khoản, query parameter, header và thông tin đối tác. Bảo vệ gồm:

- **Least privilege và retention:** phân quyền theo team/region/tenant, audit truy cập, mã hóa truyền/lưu, TTL và quy trình xóa phù hợp chính sách.
- **Redaction theo allowlist:** chỉ ghi route template, mã lỗi, duration, trace ID; không log **Authorization, Cookie, Set-Cookie, mật khẩu, PII, signed URL hoặc nội dung body** mặc định.
- **Cardinality/cost budget:** tránh label theo orderId, tenantId thô, email, requestId, traceId; các giá trị này làm bùng số series, tốn bộ nhớ và có rủi ro rò thông tin.
- **Trace propagation tin cậy:** không nhận baggage của client làm tenant/role đã xác thực; không gửi trace headers/baggage nhạy cảm sang host không tin cậy.
- **Telemetry failure:** collector chậm hoặc backend gián đoạn không được chặn luồng checkout do ghi log đồng bộ vô hạn; dùng buffer có giới hạn, backpressure hoặc dropping có đo đếm riêng.
- **Monitoring authentication:** chênh lệch 401/403 theo release có thể báo bug hoặc tấn công; quan sát tập trung và hạn chế dữ liệu để không xây lại bảng theo dõi người dùng từ telemetry.

**Một alert sai cũng tạo rủi ro vận hành:** dashboard quá đẹp nhưng dữ liệu thiếu exporter, query gộp staging vào production, hay tỷ lệ lỗi bị kéo xuống do scrape health check có thể dẫn tới quyết định “hệ thống ổn” sai. Cần test tính toàn vẹn của **định nghĩa SLI**, kiểm tra no-data và đối chiếu với synthetic probes, không chỉ test rằng Prometheus trả HTTP 200.

## 10. Kiểm thử metrics, alerts và runbook

Dashboard/alert cũng là **phần mềm có hợp đồng** và cần test. Không nên đợi outage production đầu tiên mới phát hiện quy tắc PromQL chọn nhầm label, burn threshold sai, đường dẫn runbook lỗi hoặc người trực không có quyền đọc log.

### 10.1. Test metric ở ranh giới Java/Spring

Ví dụ JUnit 5 + **SimpleMeterRegistry** kiểm tra facade ở mục 6 phát bộ đếm đúng khi service trả về. Test dùng fake synchronous service, không cần database:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class OrderCreationTelemetryTest {
    @Test
    void countsSuccessfulReturn() {
        var registry = new SimpleMeterRegistry();
        TransactionalOrderService fake = (actor, request) ->
                new OrderReceipt("o-test", "PENDING");
        var telemetry = new OrderCreationTelemetry(fake, registry);

        telemetry.create(new VerifiedActor("tenant-test", "user-test"),
                new CreateOrderRequest("cart-test"));

        double count = registry
                .get("orders.create.transaction")
                .tag("result", "returned_after_commit")
                .counter().count();
        assertEquals(1.0, count);
        assertNotNull(registry.find("orders.create.duration")
                .tag("operation", "create").timer());
    }
}
~~~

**Giới hạn test này:** fake không thật sự commit, nên nó chỉ chứng minh **cách tăng metric khi service trả bình thường**. Test tích hợp cần một **Spring proxied @Transactional service + PostgreSQL/Testcontainers**: ghi thành công thì metric commit tăng sau khi transaction hoàn tất; cố tình làm unique constraint fail ở commit thì không tăng metric đó. Kiểm tra lỗi trong lúc commit bất định không bị gắn nhầm **rollback chắc chắn**; có operation record/reconciliation riêng. Test HTTP với **MockMvc** kiểm tra GET/POST/401/403/409/429/500 thực tế, và scraper lấy được metric có đúng route template/status.

### 10.2. Test Prometheus rule và điều kiện không có dữ liệu

Đặt Prometheus alerting/recording rules trong version control cùng dashboard/runbook; dùng **promtool check rules** để bắt syntax/schema và **promtool test rules** với synthetic time series để kiểm tra logic. Cần bao phủ:

| Dữ liệu giả lập | Mong đợi |
|---|---|
| Lưu lượng ổn định, 5xx thấp hơn SLO | Không page |
| 5xx cao liên tục quá 1 giờ và 5 phút | Alert burn rate được kích hoạt theo evaluation/for |
| Một spike 30 giây rồi hồi phục | Không page do đã áp cửa sổ/for |
| 1 request và 1 lỗi trong 1 giờ | Không bắn page do cổng volume; probe bảo vệ low traffic |
| 429 tăng nhưng 5xx không tăng | Alert **rate limiting riêng**, không page availability một cách sai |
| Không có 5xx series nhưng 2xx vẫn đều | Error-rate panel phải hiển thị 0 hoặc trạng thái được định nghĩa, không mất một cách khó hiểu |
| Scrape target biến mất | Alert **missing telemetry/no-data**, không báo healthy giả |
| Pod restart / counter reset | Rate không có spike giả do trừ counter thủ công |
| Nhiều region có traffic khác nhau | Tỷ lệ tổng hợp tính từ sum counters, không bình quân tỷ lệ |
| Có lỗi sau deploy, link mở sai time range | Test deep link, time range và rollout annotation |

Để xử lý trường hợp **5xx counter hoàn toàn chưa tồn tại**, recording rule có thể dùng biểu thức numerator tạo zero-valued series khi thiếu, với điều kiện vẫn yêu cầu **eligible traffic denominator hiện hữu**. Ví dụ với **một series tổng hợp không có labels**:

~~~promql
(sum(rate(http_server_requests_seconds_count{
  application="orders-api",uri=~"/v1/orders.*",status=~"5.."
}[5m])) or vector(0))
/
clamp_min(
  sum(rate(http_server_requests_seconds_count{
    application="orders-api",uri=~"/v1/orders.*",status=~"2..|3..|5.."
  }[5m])),
  0.000001
)
~~~

**or vector(0)** ở đây chỉ phù hợp cho aggregate toàn service không có labels. Khi group theo region/route, phải tạo zero series với **nhãn giống denominator** (thay vì vector không nhãn); đồng thời có alert về target down để tránh che thiếu dữ liệu thật. Tránh viết một PromQL “có số 0” rồi cho rằng toàn hệ thống chắc chắn khỏe khi exporter mất.

### 10.3. Drill game day và xác minh runbook_url

Trong môi trường test/staging, thử **inject 5xx hoặc latency có kiểm soát**, tăng DB pool wait qua mock dependency và ngừng exporter. Quy trình:

1. Ghi thời gian bắt đầu fault, lượng traffic test và phiên bản deploy.
2. Xác nhận alert đúng severity/owner, grouping và thời gian kỳ vọng; **không gửi page production** từ thử nghiệm staging.
3. Mở runbook từ **runbook_url trong alert thực tế** bằng tài khoản có quyền giống on-call; kiểm tra dashboard đúng thời gian/route.
4. Theo các bước runbook, chọn nhánh từ metric tới trace/log, xác nhận mitigation có thể thực hiện và có cơ chế rollback/reversal.
5. Gỡ fault, đo alert resolve, SLO phục hồi, backlog được xử lý và ghi lại runbook gaps.

**Synthetic probe** phải có dữ liệu test riêng, tài khoản ít quyền, request có idempotency/cleanup và chi phí giới hạn. Không tạo đơn mua hàng/thanh toán thật theo chu kỳ chỉ để lấy synthetic success. Nếu job/report được dùng làm probe, kiểm tra **cả create + poll completion**, thay vì coi 202 là thành công cuối cùng.

## 11. Bài tập: dashboard và cảnh báo cho API đặt hàng

Một hệ thống có **Orders API** chạy bốn replica, PostgreSQL, Redis và Payment API. SLO request availability **99,9% trong 30 ngày**, SLO latency là **95% request POST /v1/orders dưới 500 ms**, và outbox event phải được dispatch trong **2 phút**. Tại thời điểm triển khai mới, tỷ lệ 5xx của POST tăng, đồng thời job payment bắt đầu chậm dù GET /v1/orders vẫn hoạt động.

Hãy xây dựng một thiết kế có thể review được:

1. **Định nghĩa SLI**: numerator/denominator cho availability, latency và async completion; xử lý 401/403/429 và low traffic.
2. **Dashboard 2 tầng**: chọn ít nhất sáu panel overview và bốn panel drill-down, ghi unit, window, route/status dimensions, owner và deep link.
3. **PromQL**: RPS theo route, 5xx ratio, p95 từ histogram, 429 riêng, pool pending và backlog/oldest outbox age theo metric có sẵn trong hệ thống.
4. **Alert**: multi-window burn rate dựa trên 99,9% SLO, no-telemetry và outbox lag; chỉ rõ severity, grouping và cách tránh page storm.
5. **Runbook**: trigger, xác minh ảnh hưởng, kiểm tra thay đổi gần nhất, hướng mitigation an toàn, tiêu chí đóng và escalation.
6. **Java/Spring**: chỉ rõ vị trí tăng metric order commit và trạng thái payment, không log credential/PII hoặc dùng orderId làm metric label.
7. **Test**: rule testing, HTTP integration, một game day 5xx, một lần scrape outage, cùng test mở dashboard/runbook bằng vai trò trực.

**Gợi ý:** một HTTP **201** chỉ xác nhận resource order được tạo theo contract, không có nghĩa payment hoàn tất. Alert về outbox lag phải phân biệt với API 5xx. Nếu tỷ lệ lỗi cao trong 5 phút nhưng 1 giờ chưa đủ burn, cảnh báo multi-window có thể chưa page; synthetic check cho checkout critical có thể phát hiện sớm tình huống traffic thấp. Mọi mitigation cần giữ idempotency, quyền truy cập và khả năng đối soát payment.

## 12. Checklist và tham khảo

- [ ] Mỗi SLI có **numerator/denominator/window**, loại trừ status có lý do và owner rõ ràng.
- [ ] Dashboard cho thấy **traffic, 5xx, latency, budget, 429, business outcome và dependency saturation**.
- [ ] Metric dùng **route template**, label cardinality có hạn; histogram bucket đủ cho latency SLO.
- [ ] PromQL dùng rate trước sum, gộp bucket đúng, không bình quân per-pod p95/tỷ lệ lỗi.
- [ ] Alert có **severity, owner, low-volume/no-data policy, grouping, runbook_url, dashboard_url**.
- [ ] Runbook có trigger, kiểm chứng, nhánh nguyên nhân, mitigation an toàn, điều kiện đóng/escalate.
- [ ] Trace/log liên kết được nhưng **không lộ JWT, Cookie, PII hoặc idempotency key**.
- [ ] Scrape endpoint bảo mật, telemetry có retention, least privilege và cost/cardinality budget.
- [ ] Có rule tests, HTTP/DB integration tests, game day và định kỳ kiểm tra deep link/quyền người trực.

Tham khảo: **Spring Boot Actuator và Metrics**, https://docs.spring.io/spring-boot/reference/actuator/metrics.html; **Spring Boot Tracing**, https://docs.spring.io/spring-boot/reference/actuator/tracing.html; **Micrometer**, https://docs.micrometer.io/micrometer/reference/; **Prometheus Querying**, https://prometheus.io/docs/prometheus/latest/querying/basics/; **Prometheus Alerting Rules**, https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/; **Prometheus promtool**, https://prometheus.io/docs/prometheus/latest/command-line/promtool/; **Google SRE Workbook – Alerting on SLOs**, https://sre.google/workbook/alerting-on-slos/; **OpenTelemetry Trace Context**, https://www.w3.org/TR/trace-context/; **RFC 9457 Problem Details**, https://www.rfc-editor.org/rfc/rfc9457.html.

**Kết luận:** Một hệ quan sát REST API hiệu quả nối chuỗi **tác động người dùng → SLI/SLO → dashboard → alert đúng mức → runbook → bằng chứng phục hồi**. Dashboard chỉ có giá trị khi giúp đưa ra quyết định; alert chỉ đáng đánh thức người trực khi có việc họ có thể làm. Metrics, logs và traces cần phản ánh đúng **HTTP semantics, trạng thái commit, tác động nghiệp vụ và quyền riêng tư**, đồng thời phải được kiểm thử như chính API.

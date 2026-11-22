# Metrics theo route template thay vì URI chứa ID

> **Module:** `INTEGRATION_API_REST` — chương **Quan sát hệ thống**. Bài học xây dựng HTTP metrics có độ phân giải hữu ích nhưng **cardinality hữu hạn** cho REST API: phân biệt URI thực với **route template**, dùng Spring Boot 3 / Micrometer / Actuator, tránh lộ ID và thông tin nhạy cảm, kiểm soát nhãn, phân tích latency/error rate, và kiểm thử bằng Java/Spring. Các nguyên tắc áp dụng cho API resource/URI, mã trạng thái HTTP, xác thực/phân quyền, cache, idempotency và các thao tác bất đồng bộ.

## 1. Một route, hàng triệu time series?

Ứng dụng quản lý đơn hàng có endpoint:

~~~http
GET /v1/orders/ord_7849?include=items HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

Framework thực sự định tuyến request này tới:

~~~java
@GetMapping("/v1/orders/{orderId}")
public OrderView getOrder(@PathVariable String orderId) {
    // authorization + query + DTO mapping ...
}
~~~

Nếu ghi HTTP metric với nhãn `uri="/v1/orders/ord_7849"`, mỗi ID đơn mới tạo một giá trị nhãn mới. Khi đường dẫn còn chứa UUID, user ID, session ID hoặc số ngẫu nhiên, số lượng time series có thể tăng mãi. Dashboard chậm, storage tốn kém, scrape quá tải và cảnh báo mất độ tin cậy.

**Nhãn nên là route template ổn định:** `uri="/v1/orders/{orderId}"`, kết hợp các chiều **hữu hạn** như method, status và một tên service đã được kiểm soát.

~~~text
SAI:  api_requests_total{method="GET", uri="/v1/orders/ord_7849", status="200"}
SAI:  api_requests_total{method="GET", uri="/v1/orders/ord_7850", status="200"}

ĐÚNG: api_requests_total{method="GET", uri="/v1/orders/{orderId}", status="200"}
      [counter tăng thêm 2 cho cùng một series]
~~~

Mục tiêu không phải mất khả năng điều tra từng request: **metrics trả lời “route nào đang chậm hoặc lỗi?”; traces/logs có kiểm soát giúp điều tra một request cụ thể** bằng trace ID/correlation ID. Đừng ép metric labels làm chức năng của hệ thống search log.

**Sau bài học**, bạn có thể:

- Giải thích cardinality và chi phí khi gắn URI/ID vào label.
- Dùng route template do router xác định, không tự thay ID bằng regex ngẫu hứng.
- Cấu hình Spring Boot/Micrometer và bảo vệ endpoint metrics.
- Chọn tag hữu hạn cho method, route, status, outcome; tránh ID/tenant/user/token.
- Xây bảng điều khiển request rate, 5xx ratio, p95 latency không làm nổ time series.
- Viết integration test bảo đảm nhiều URI khác nhau cùng vào một label route, kể cả lỗi 404/401 và lỗi trước routing.

## 2. Ba tên rất giống nhau nhưng khác nhau

| Khái niệm | Ví dụ | Đưa vào HTTP metric label? |
|---|---|---|
| **Raw request target** | `/v1/orders/ord_7849?include=items` | **Không**: có ID/query |
| **Path đã parse** | `/v1/orders/ord_7849` | **Không**: vẫn có ID |
| **Route template** / matched pattern | `/v1/orders/{orderId}` | **Có**, sau khi xác minh từ router |
| **Route không khớp** | `/v1/this-does-not-exist` | Label cố định như `NOT_FOUND` |
| **Request ID / Trace ID** | `52ab...` | **Không** là label; dùng trong trace/log |
| **URI của resource mới** trong `Location` | `/v1/orders/ord_7850` | **Không** là label |

Với Spring MVC, route template được biết khi `HandlerMapping` tìm được handler, còn trong Spring WebFlux có matching mechanism tương ứng. Đừng gọi `request.getRequestURI()` rồi gửi trực tiếp vào `Timer.builder(...).tag("uri", ...)`.

### 2.1. Metric label là một phần của hợp đồng vận hành

Không chỉ giá trị nhãn mà **tên route** cũng cần ổn định. Ví dụ nhóm API sử dụng nhất quán:

~~~text
GET    /v1/orders/{orderId}
PATCH  /v1/orders/{orderId}
POST   /v1/orders
GET    /v1/orders/{orderId}/items
~~~

Nếu controller thay `{orderId}` thành `{id}`, URI public vẫn tương đương nhưng chuỗi template label thay, khiến dashboard/alerts có thể trông như “route cũ biến mất, route mới xuất hiện”. Cần review những thay đổi route-template tags như một **thay đổi metric contract** và cập nhật dashboard/recording rules tương ứng.

### 2.2. Hai cách đếm một request là hai vấn đề khác nhau

Một API request có thể có:

1. **HTTP server metric:** đo mọi request, kết quả route/status và tổng latency.
2. **Business metric:** ví dụ `orders.created` hoặc `payment.approved`, chỉ tăng **khi thao tác nghiệp vụ thực sự thành công**.

Đừng đếm “đã tạo đơn” bằng số response `POST /orders 2xx` nếu có async `202`, retry idempotent, cancel hoặc response mất sau commit. Đồng thời đừng tự đếm HTTP request lần thứ hai bằng interceptor nếu Actuator đã có auto-instrumentation, trừ khi có nhu cầu metric khác được định nghĩa rõ.

## 3. Cardinality: vì sao một nhãn xấu có thể lấn át hệ thống

Một time series được phân biệt bởi **tên metric + toàn bộ tập label và giá trị của chúng**. Nếu cùng metric có:

- 40 route templates,
- 5 HTTP methods,
- 6 status được quan sát,
- 20 ứng dụng/instance,
- và 15 histogram buckets (nếu bật histogram),

thì cỡ lý thuyết có thể tăng theo tích `40 × 5 × 6 × 20 × 15 = 360.000` series/bucket combinations trước khi tính thêm chiều khác. Đây chỉ là **ví dụ minh họa phép nhân**, không dự báo chính xác mọi runtime vì histogram còn có `_sum`/`_count`, bucket boundaries, missing combinations, các label hệ thống và scrape topology.

Nếu thay 40 route bằng **hàng triệu ID**, số series còn lớn hơn nhiều. **Hash ID không giải quyết cardinality**: ID được hash vẫn thường tạo một label value riêng, đồng thời có thể trở thành định danh truy vết người dùng.

### 3.1. Phân loại nhãn cho metric HTTP

| Tag/label | Cardinality | Khuyến nghị |
|---|---|---|
| `method` | Thấp, nếu giới hạn các method chuẩn | Dùng `GET/POST/PATCH/...`; fallback `OTHER` |
| `route` hoặc Micrometer `uri` | Thấp, nếu là matched template | **Ưu tiên** |
| `status` | Hữu hạn (HTTP status code) | Dùng cho error rate |
| `outcome` (2xx/4xx/5xx) | Rất thấp | Phù hợp báo cáo tổng hợp |
| `service`, `environment` | Hữu hạn khi do deploy config đặt | Được, có governance |
| `tenantId`, `userId`, `orderId` | Cao/nhạy cảm | **Không** là tag HTTP |
| `requestId`, `traceId` | Gần như duy nhất mỗi request | **Không** là tag |
| `path`, query string, header/`Location` | Không giới hạn + có thể chứa secret | **Không** |
| `exceptionMessage`, `email`, `token` | Không giới hạn/nhạy cảm | **Tuyệt đối tránh** |

Ngay cả label `clientType` từ header cũng có thể bị client giả mạo bằng chuỗi không giới hạn. Chỉ dùng nếu server chuẩn hóa vào một **allowlist nhỏ** (ví dụ `web`, `mobile`, `batch`, `other`), không phản chiếu nguyên header.

### 3.2. Sơ đồ luồng đúng

~~~mermaid
flowchart TD
    A["HTTP /v1/orders/ord_7849?include=items"] --> B["Spring routing / HandlerMapping"]
    B --> C{"Matched handler?"}
    C -- "Có" --> D["Template /v1/orders/{orderId}"]
    C -- "Không" --> E["Bounded fallback NOT_FOUND"]
    D --> F["Low-cardinality labels"]
    E --> F
    F --> G["Micrometer / Prometheus time series"]
    B --> H["Trace ID + sanitized detailed logs"]
    H --> I["Truy vết từng request khi cần"]
    G --> J["RPS / 5xx / p95 theo route"]
~~~

Lưu ý: route label là một **phân loại nhóm**. Bản thân metric không chứa order ID, nhưng người vận hành vẫn có thể liên hệ các request cụ thể qua trace ID đặt trong log/traces có phân quyền và retention phù hợp.

## 4. Route template đến từ router, không phải từ suy đoán

Làm thế nào có được chuỗi `/v1/orders/{orderId}`? Cách tốt nhất là **lấy matched route từ HTTP framework**, vì framework biết quy tắc ưu tiên, biến path, regex constraint và mapping nào thật sự xử lý request.

### 4.1. Những trường hợp routing đặc biệt

| Request | Kết quả có thể xảy ra | Tag metric an toàn |
|---|---|---|
| `GET /v1/orders/ord_42` | Matched GET route, 200 | `/v1/orders/{orderId}` |
| `GET /v1/orders/missing` | Route matched nhưng service trả 404 | Vẫn có thể là `/v1/orders/{orderId}` |
| `GET /v1/unknown/x/y` | Không tìm thấy route, 404 | `NOT_FOUND` hoặc `UNMATCHED` cố định |
| `POST /v1/orders/ord_42` | Không có handler POST tương ứng, 405 | Label fallback hữu hạn; không raw path |
| `GET /v1/orders/ord_42` với token thiếu | Security filter trả 401 **trước router** | `UNMATCHED`/`UNKNOWN` hữu hạn, không path thực |
| GET có `If-None-Match` khớp | `304 Not Modified` | Route template và status 304 |
| `PATCH /v1/orders/ord_42` bị `If-Match` stale | `412 Precondition Failed` | Matched PATCH route, status 412 |
| API gateway chặn body quá lớn | `413` có thể xảy ra trước Spring | Metric do gateway sở hữu, dùng route/fallback riêng |

**Đừng ép mọi 404 vào cùng một loại:** một handler đã match nhưng domain resource không tồn tại khác với một URI chưa match handler nào. Spring/agent có thể gắn tag fallback khác nhau theo phiên bản/runtime; hãy xem **scrape thật** và thiết kế dashboard chấp nhận fallback ổn định. Không cố gắn raw URI của 404 chưa matched để “giữ thông tin” — attacker có thể gửi vô hạn path ngẫu nhiên và phá metrics.

### 4.2. Vì sao regex “thay chuỗi số bằng {id}” không đủ?

Các API có thể có:

~~~text
/v1/users/42/orders/5501
/v1/orders/01HXR7...        (ULID)
/v1/products/abc-123-summer   (slug)
/v1/files/report.2026-11.pdf  (filename)
/v1/search?q=secret
~~~

Một regex chỉ nhận `\d+` bỏ sót UUID/ULID/slug, có thể thay nhầm segment cố định hoặc nhầm nhiều route. Query string vẫn mang giá trị tùy ý. Nếu không truy được matched pattern, dùng **fallback cố định** (`UNKNOWN`/`NOT_FOUND`) hoặc mapping thủ công **allowlist** đã xác minh, thay vì tự phân tích user input để sinh label.

### 4.3. Không làm sai status khi báo cáo

Một request thất bại vì validation có `400`, thiếu quyền có `403`, precondition không còn khớp có `412`, bị rate limit có `429`, server không sẵn sàng có `503`. Route, method và status là ba chiều khác nhau: **status 412 không phải 5xx**, cũng không chứng minh SLO bị vi phạm theo định nghĩa nghiệp vụ của bạn.

Nếu đo tỷ lệ lỗi, cần chính sách: 5xx thường phản ánh sự cố server; 4xx có thể là client misuse, thử quyền, rate limiting hoặc business conflict. Đừng gộp mọi 4xx vào “server error rate”, nhưng cũng đừng bỏ qua một đợt tăng đột biến 401/403/429. Đối với cache, 304 là **thành công của conditional GET theo hợp đồng** dù thuộc nhóm 3xx; không nên coi đó là redirect error.

## 5. Spring Boot/Micrometer: tận dụng instrumentation có sẵn

Với Spring Boot 3.x có Spring MVC/WebFlux, **Actuator + Micrometer Observation** có thể instrument HTTP server requests tự động khi tích hợp được cấu hình. Trong nhiều cấu hình Micrometer, meter logic có tên `http.server.requests` và tag `uri` được lấy từ **matched route template** chứ không phải raw path. Khi xuất Prometheus, một dạng metric thường thấy là `http_server_requests_seconds_count` / `_sum`, nhưng **tên metric và bộ label thực tế tùy phiên bản Micrometer/registry và cấu hình observation conventions**. Hãy kiểm tra endpoint scrape trên hệ thống của bạn.

Các dependency thường dùng:

~~~xml
<!-- Trong build Maven của ứng dụng Spring Boot -->
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
  <groupId>io.micrometer</groupId>
  <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Với Gradle, dùng dependency tương đương. Ở nhiều dự án Spring Boot, Prometheus endpoint cần được cho phép trong cấu hình management, còn backend Prometheus phải được cấu hình scrape phù hợp:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health, metrics, prometheus
  metrics:
    tags:
      application: orders-api
~~~

**Quan trọng:** cấu hình trên chỉ là mẫu demo. Không công khai `/actuator/prometheus` ra Internet. Bảo vệ endpoint bằng network policy, firewall, reverse proxy hoặc xác thực phù hợp; cân nhắc management port riêng, kiểm IP scraper và hạn chế truy cập metadata. `management.endpoints.web.exposure.include` không phải là cơ chế authentication.

### 5.1. Controller Spring MVC và tên route

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/v1/orders")
class OrderResource {
    private final OrderService orders;

    OrderResource(OrderService orders) {
        this.orders = orders;
    }

    @GetMapping("/{orderId}")
    ResponseEntity<OrderView> get(@PathVariable String orderId) {
        return ResponseEntity.ok(orders.readAuthorized(orderId));
    }

    @PostMapping
    ResponseEntity<OrderView> create(@RequestBody CreateOrder input) {
        OrderView created = orders.createAuthorized(input);
        return ResponseEntity.status(201).body(created);
    }
}

interface OrderService {
    OrderView readAuthorized(String orderId);
    OrderView createAuthorized(CreateOrder input);
}
record OrderView(String id, String status) {}
record CreateOrder(String productId, int quantity) {}
~~~

Lớp controller là ví dụ về routing, **chưa phải giải pháp auth production**. `readAuthorized`/`createAuthorized` phải xác minh principal/tenant/owner, kiểm input và trả các lỗi HTTP thích hợp. Với Security Filter Chain và Actuator hoạt động, request `GET /v1/orders/ord_42` được route tới pattern `/v1/orders/{orderId}`; không tự thêm một label `orderId=ord_42` vào HTTP Timer.

### 5.2. Đọc meter mà không nhầm labels

Lúc test hoặc debug, có thể duyệt meter registry:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.List;

List<Meter> httpMeters = registry.getMeters().stream()
    .filter(m -> m.getId().getName().equals("http.server.requests"))
    .toList();

httpMeters.forEach(m -> {
    String route = m.getId().getTag("uri");
    String method = m.getId().getTag("method");
    String status = m.getId().getTag("status");
    // Không đọc raw request URI để thay route.
});
~~~

Đoạn code dùng `registry` đã inject và chỉ minh họa API `MeterRegistry`. Với Micrometer Observation conventions mới hoặc tùy biến, tên tag có thể là `uri` trong meter Prometheus, trong khi OpenTelemetry sử dụng semantic convention như `http.route`. Kiểm định cấu hình thực thay vì coi một label name là bất biến giữa mọi backend.

**Không ghi manual Timer/Counters cho mỗi request chỉ để bắt chước `http.server.requests` nếu auto-instrumentation đã hoạt động.** Kết quả sẽ dễ bị double-count khi một dashboard cộng cả hai. Custom business meters nên có tên, ý nghĩa và thời điểm tăng khác với HTTP meters.

## 6. Nếu buộc phải tự instrument: chỉ nhận matched pattern đã kiểm soát

Ở Spring MVC, `HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE` có thể cung cấp matched pattern sau khi router chọn handler. Helper dưới đây **không bao giờ dùng raw URI làm metric label** và chỉ công nhận những route đã được duyệt trong contract:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.servlet.HandlerMapping;
import java.util.Set;

final class RouteLabels {
    private static final Set<String> ALLOWED = Set.of(
        "/v1/orders", "/v1/orders/{orderId}"
    );

    private RouteLabels() {}

    static String from(HttpServletRequest request) {
        Object matched = request.getAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        if (matched == null) return "UNMATCHED";
        String template = matched.toString();
        return ALLOWED.contains(template) ? template : "OTHER";
    }

    static String method(String method) {
        return switch (method) {
            case "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"
                -> method;
            default -> "OTHER";
        };
    }
}
~~~

Điểm quan trọng: `getRequestURI()`, `getQueryString()`, giá trị `@PathVariable` và `X-Request-Id` **không** xuất hiện trong logic tạo label. `OTHER` và `UNMATCHED` là các giá trị hữu hạn. Nếu triển khai thêm route, cập nhật allowlist và test tương ứng. Không dùng `template.toString()` không có allowlist nếu matched route có thể được tạo động bởi plugin hoặc phần mềm bên thứ ba.

Ví dụ một **metric demo riêng** (không thay auto-observation) đếm request **đã match MVC handler**:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
class MatchedRouteProbe implements HandlerInterceptor {
    private final MeterRegistry metrics;

    MatchedRouteProbe(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler, Exception error) {
        String route = RouteLabels.from(request);
        String statusClass = response.getStatus() / 100 + "xx";
        metrics.counter("demo.mvc.matched.requests",
            "route", route,
            "method", RouteLabels.method(request.getMethod()),
            "status_class", statusClass).increment();
    }
}
~~~

Để hoạt động, interceptor cần đăng ký qua `WebMvcConfigurer.addInterceptors(...)`. **Đây không phải thay thế đầy đủ cho HTTP server instrumentation**: `afterCompletion` chỉ chạy khi request đi qua MVC interceptor; preflight/security rejection và 404 trước routing có thể **không** gọi nó. Dùng built-in HTTP observations cho số lượng request tổng; demo này chỉ cho thấy cách tạo label an toàn cho metric riêng.

Spring WebFlux không dùng `jakarta.servlet.http.HttpServletRequest` hay `HandlerInterceptor`. Trong reactive stack, lấy matched route/context từ cơ chế WebFlux observation/filter tương ứng; vẫn theo nguyên tắc **template hữu hạn, không raw URI**. Với API gateway, dùng route ID/template do gateway quản lý, không copy toàn `:path` làm label.

## 7. Guardrails: giảm cardinality trước khi dữ liệu rời ứng dụng

Kiểm tra cardinality phải diễn ra **trước khi register meter**, chứ không chỉ dựa vào việc biểu đồ tình cờ chưa quá lớn.

### 7.1. `MeterFilter` là hàng rào cuối cùng

Micrometer cho phép giới hạn số **giá trị nhãn khác nhau** trên một nhóm meter. Ví dụ `uri` bị gắn quá nhiều route:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class MetricSafetyConfiguration {
    @Bean
    MeterFilter limitHttpUriTags() {
        return MeterFilter.maximumAllowableTags(
            "http.server.requests", "uri", 100,
            MeterFilter.deny());
    }
}
~~~

Mẫu này áp dụng khi meter thực tên `http.server.requests` và tag key `uri`. **Nó chặn việc đăng ký thêm meter vượt ngưỡng, không tự nhóm các giá trị mới vào `OTHER`**; do đó có thể mất telemetry cho route mới sau khi chạm giới hạn. Hãy phát cảnh báo về số lượng tag values, sửa nguyên nhân từ nguồn và test cập nhật route. Giới hạn 100 chỉ là ví dụ, phải tính theo số route thật và chính sách của hệ thống.

Nếu muốn **gom nhóm** các route không được nhận diện, hãy áp một chính sách thay tag sang `OTHER`/`UNMATCHED` **trước khi meter được tạo**, dựa vào matched route và allowlist. Đừng lấy vài giá trị ID đầu tiên làm nhãn rồi để `MeterFilter.deny()` bỏ hết request tiếp theo — dashboard lúc đó không còn đại diện cho traffic thực.

### 7.2. Governance cho thêm nhãn

Một đề xuất thêm `customerId`, `clientIp`, `userAgent` hoặc `errorDescription` vào metric phải trả lời:
 
- Nhãn có tối đa bao nhiêu giá trị ở tải cao, trong tháng và trong một năm?
- Giá trị có được user hoặc HTTP client tự đặt không?
- Có thể chứa PII, token, internal ID hoặc dữ liệu bị luật/chính sách hạn chế không?
- Nhãn có cần thiết cho alert/SLO không, hay truy vết bằng trace ID là đủ?
- Có allowlist, TTL/retention, regression test và owner chịu trách nhiệm không?

Nếu vẫn cần phân tích usage theo khách hàng, hãy dùng **analytics pipeline có kiểm soát truy cập và aggregation** hoặc log/traces đã lọc thay vì biến `tenantId` thành label của mọi HTTP request. Ngay cả 200 tenants × 50 routes × 6 status × 10 instances cũng tạo phép nhân đáng kể.

### 7.3. Histogram và percentiles cũng tiêu thụ series

Để tính latency p95 theo nhiều instances trong Prometheus, thường cần **histogram buckets** hoặc native histograms tương thích; client-side percentile summaries không phải lúc nào cũng tổng hợp xuyên instances đúng cách. Ví dụ bật histogram cho meter được chọn:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
~~~

Tính năng/tên property còn phụ thuộc phiên bản Spring Boot/Micrometer. Kiểm tra thực tế có `_bucket` và nhãn `le` trước khi dùng `histogram_quantile`; bật histogram cho mọi route/method/status có thể tăng storage. Cân nhắc SLO buckets hoặc metrics aggregation theo route group, giữ giới hạn label budget.

## 8. Dashboard Prometheus theo route template

Các truy vấn sau giả định exporter phát metric `http_server_requests_seconds_count`, `http_server_requests_seconds_bucket`, label `uri`, `method`, `status` và `application="orders-api"`. Đây là hình dạng thường gặp với Micrometer Prometheus; **hãy xác minh metric và label trên `/actuator/prometheus` của phiên bản thực tế** trước khi sao chép. Một số stack OpenTelemetry dùng tên/label khác.

### 8.1. Request rate (RPS) theo route và method

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{application="orders-api"}[5m])
)
~~~

Vì `uri` ở đây là route template, tất cả GET cho `/v1/orders/{orderId}` cùng đóng góp vào một nhóm. Nếu dashboard hiển thị hàng chục nghìn giá trị dạng `/v1/orders/ord_*`, bạn đã phát hiện **label leak**, không phải API thực sự có hàng chục nghìn routes.

### 8.2. Tỷ lệ 5xx theo route

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count{
    application="orders-api",status=~"5.."
  }[5m])
)
/
clamp_min(
  sum by (uri, method) (
    rate(http_server_requests_seconds_count{
      application="orders-api"
    }[5m])
  ),
  0.001
)
~~~

`clamp_min` ở ví dụ này chỉ tránh chia cho 0 trong dashboard; nó có thể làm méo tỷ lệ khi traffic rất thấp. Trong dashboard production, cân nhắc **chỉ hiện tỷ lệ cho route đủ mẫu** và cảnh báo theo error budget. Không trộn 412 (precondition stale) với 5xx; nếu 412 tăng mạnh, theo dõi như **xung đột đồng thời của nghiệp vụ** bằng biểu đồ riêng.

### 8.3. p95 latency từ histogram buckets

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri, method) (
    rate(http_server_requests_seconds_bucket{
      application="orders-api"
    }[5m])
  )
)
~~~

Truy vấn chỉ hoạt động theo mô hình **classic histograms** khi exporter có bucket và `le`. Nếu dùng native histograms hoặc metric conventions khác, phải đổi cách truy vấn. Histogram p95 có thể bị sai khi rất ít request hoặc bucket bố trí thô. Đừng gắn `orderId` vào histogram để “xem request chậm nhất”: dùng trace exemplar, span và logs cho request cụ thể.

### 8.4. Tách status bất thường và noise có chủ đích

Có thể xây biểu đồ số 401/403/404/409/412/429 theo route hoặc nhóm status. Nhưng cần giải thích:
 
- `401/403` tăng có thể là expired tokens hoặc traffic tấn công; nếu xảy ra **trước routing**, route label fallback như `UNKNOWN` vẫn là đúng.
- `404 NOT_FOUND` từ scanning tự động phải được nhóm, không tạo từng time series cho path ngẫu nhiên.
- `304` nhiều có thể là cache revalidation lành mạnh, không phải lỗi redirect.
- `409` có thể là state conflict; `412` là stale `If-Match`, hai loại giúp điều tra khác nhau.
- `429` do rate limiting làm giảm tải server, nên alert gắn với client UX và quota policy, không đánh đồng 429 với 500.

Khi có nhiều instances, hãy **sum các counter/rate qua instance** trước khi tính tỷ lệ. Không tính trung bình đơn giản các p95 của từng instance để ra p95 toàn service. Histogram có thể hợp nhất theo bucket nếu cùng chuẩn bucket/tên metric.

## 9. Trace và log chi tiết mà không làm metric mất kiểm soát

Một request `GET /v1/orders/ord_42` có thể tạo dữ liệu quan sát ở ba tầng:

| Hình thức | Mục đích | Dữ liệu nên có |
|---|---|---|
| **Metric** | Báo động nhanh và tổng hợp theo route | method, route template, status, duration |
| **Trace** | Xem dependency/critical path của request | span name như `GET /v1/orders/{orderId}`, trace ID, service span |
| **Structured log** | Điều tra event cụ thể, với quyền truy cập phù hợp | timestamp, traceId, route, error code, sanitized context |

Ví dụ log theo cấu trúc:

~~~json
{
  "timestamp": "2026-11-18T12:00:00Z",
  "level": "WARN",
  "traceId": "77a516a84d8a...",
  "route": "/v1/orders/{orderId}",
  "method": "PATCH",
  "status": 412,
  "errorCode": "STALE_VERSION",
  "durationMs": 38
}
~~~

Không có token, email, nội dung request body hay raw `Location` trong ví dụ. Nếu thật sự phải điều tra order ID, đưa vào **audit/trace có chính sách thu thập riêng**, masking, retention ngắn và quyền đọc hạn chế; **không** thêm vào mọi metric label.

### 9.1. Tracing cũng cần span name có cardinality hữu hạn

Với hệ thống dùng OpenTelemetry, một convention phổ biến đặt HTTP server span name dựa trên method + route template, còn attribute `http.route` biểu diễn template. Thuộc tính raw URL/path nếu được thu thập phải được xử lý riêng vì nguy cơ PII. Không đặt span name thành `GET /v1/orders/ord_42` cho mỗi request nếu mục tiêu là tổng hợp latency theo operation: backend tracing cũng bị phân mảnh grouping.

Có thể gắn **exemplar** trỏ từ một sample histogram/counter sang trace ID nếu instrumentation và storage hỗ trợ. Exemplar **khác với Prometheus label** của time series; trace ID không trở thành nhãn mới cho mọi request. Cần test mức độ hỗ trợ ở SDK, collector và query backend thật.

### 9.2. Metrics cho nghiệp vụ cần ranh giới commit

Trong API có idempotency, một POST thanh toán có thể nhận retry cùng `Idempotency-Key`. HTTP metric phải đếm **mỗi attempt**; business metric `payments.created` chỉ đếm **mỗi payment logic đã commit**. Với `202 Accepted` cho job bất đồng bộ, HTTP request duration không phải job processing duration: nên có metric `jobs.completed` và `job.duration` gắn nhãn job **type/status hữu hạn**, không gắn job ID.

Tương tự `ETag`, `If-None-Match` và `If-Match` ảnh hưởng status (`304/412`), nhưng không nên ghi **giá trị ETag** vào metric tag. Nếu cần điều tra vì sao precondition thất bại, dùng trace/log có kiểm soát và một metric tổng `precondition.failures` theo route/status.

## 10. Bảo mật: telemetry cũng là một bề mặt dữ liệu

Khi API có JWT Bearer, cookie, nhiều tenant và dữ liệu cá nhân, metrics phải tuân thủ ranh giới bảo mật như chính REST API:

- **Không lộ token/API key/cookie:** không đưa `Authorization`, `Cookie`, `Set-Cookie`, URL có chữ ký, query string, raw path chứa secret vào label, log hoặc exemplar.
- **Không biến tenant/user ID thành label:** số tenants thay đổi liên tục, còn user ID là dữ liệu định danh. Nếu cần báo cáo theo tenant, thiết kế analytics/audit có quyền riêng; cân nhắc mức gộp được cho phép.
- **Không công khai Actuator:** `/actuator/prometheus` có thể cho biết routes, traffic, instance, error pattern và một phần topology. Dùng quản lý mạng và authentication phù hợp.
- **Không dựa vào CORS để bảo vệ endpoint metrics:** curl/server-side HTTP clients không bị ràng buộc bởi browser CORS. Dùng security/network controls thật.
- **Không tin `X-Forwarded-*`/`X-Request-Id` vô điều kiện:** proxy trusted mới được viết các header, normalize/limit giá trị nếu đưa vào logs; không dùng raw header làm metric label.
- **Tránh leak 404/403 qua detail metrics:** không tạo nhãn `isForeignTenant=true` nếu nhãn đó có thể tiết lộ dữ liệu cá nhân hoặc tạo bề mặt suy đoán. Chỉ công khai status/route summary cho người có quyền đọc telemetry.
- **Rate limit và metric DoS:** một attacker có thể gửi hàng nghìn URI lạ, HTTP methods lạ hoặc User-Agent ngẫu nhiên; label budget và low-card fallback phải chịu được tình huống ấy.

**Quan sát được một lỗi không có nghĩa được phép lưu mọi dữ liệu của request.** Thiết kế metric với quyền truy cập, thời hạn lưu, cảnh báo và compliance giống dữ liệu vận hành khác.

## 11. Kiểm thử cardinality: nhiều ID vẫn là một route label

**Đừng chỉ test metric tồn tại.** Phải chứng minh rằng thay đổi `orderId` **không tạo thêm series riêng** và request không match route không làm số giá trị `uri` tăng vô hạn.

### 11.1. Unit test helper không dùng raw path

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.web.servlet.HandlerMapping;
import static org.junit.jupiter.api.Assertions.*;

class RouteLabelsTest {
    @Test
    void rawIdsCannotBecomeMetricTags() {
        var a = new MockHttpServletRequest(
            "GET", "/v1/orders/ord_1");
        var b = new MockHttpServletRequest(
            "GET", "/v1/orders/ord_998877");

        a.setAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE,
            "/v1/orders/{orderId}");
        b.setAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE,
            "/v1/orders/{orderId}");

        assertEquals("/v1/orders/{orderId}", RouteLabels.from(a));
        assertEquals(RouteLabels.from(a), RouteLabels.from(b));

        // Chưa có matched handler: không dùng request URI làm fallback.
        b.removeAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        assertEquals("UNMATCHED", RouteLabels.from(b));

        // Pattern chưa được duyệt: gom vào một giá trị hữu hạn.
        a.setAttribute(
            HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE,
            "/internal/{secretKey}");
        assertEquals("OTHER", RouteLabels.from(a));
        assertEquals("OTHER", RouteLabels.method("CUSTOM_METHOD"));
    }
}
~~~

Đây là test cho **helper minh họa** ở mục 6. Nó không chứng minh Spring Actuator tạo tag đúng, vì chưa có HTTP request thật và chưa chạy observation filters.

### 11.2. Integration test với server thật và `MeterRegistry`

Đối với auto-observation, ưu tiên `@SpringBootTest(webEnvironment = RANDOM_PORT)` để gọi HTTP thật. `MockMvc` là công cụ rất tốt cho contract REST, nhưng một số phiên bản/cấu hình chưa đi qua toàn bộ instrumentation HTTP network giống server thật. Ví dụ khung test:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.*;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RouteCardinalityIT {
    @LocalServerPort int port;
    @Autowired TestRestTemplate http;
    @Autowired MeterRegistry metrics;

    @Test
    void thirtyOrderIdsStillShareOneRouteTemplate() {
        // Fixture: tạo sẵn 30 order của cùng tenant test.
        // Thay bằng JWT do test issuer phát hành.
        HttpHeaders headers = new HttpHeaders();
        headers.setBearerAuth(validTestJwt());
        HttpEntity<Void> request = new HttpEntity<>(headers);

        for (int i = 0; i < 30; i++) {
            http.exchange(
                "http://localhost:" + port
                    + "/v1/orders/ord_" + i,
                HttpMethod.GET, request, String.class);
        }

        List<Meter> serverMeters = metrics.getMeters().stream()
            .filter(m -> m.getId().getName()
                .equals("http.server.requests"))
            .toList();

        assertTrue(serverMeters.stream().anyMatch(m ->
            "/v1/orders/{orderId}".equals(
                m.getId().getTag("uri"))));

        // Không một meter nào chứa ID từng request.
        assertTrue(serverMeters.stream().noneMatch(m -> {
            String uriTag = m.getId().getTag("uri");
            return uriTag != null && uriTag.contains("/ord_");
        }));
    }

    private String validTestJwt() {
        // Fixture/helper cấp token hợp lệ cho tenant test.
        throw new UnsupportedOperationException(
            "Implement with test issuer");
    }
}
~~~

**Đây là skeleton kiểm thử**, chưa chạy được nếu chưa seed 30 orders và thay `validTestJwt()` bằng token test hợp lệ với Resource Server. Với API công khai cho test, có thể dùng một route test-only thay vì JWT, nhưng **không vô hiệu bảo mật production** để làm metric test. Chạy bằng DB/test profile tương đương môi trường thực và có Actuator/Micrometer được khởi tạo. Nếu tên meter/tag thay theo phiên bản, chỉnh assertion theo **contract telemetry đã công bố**, không âm thầm hạ yêu cầu “không có ID”.

Cũng nên đo số lượng distinct route-tag values **trước và sau** 30 requests. Nó phải không tăng theo số ID. Với status có thể khác nhau (200/404), số series được phép tăng bởi status, **không bởi path values**. Muốn test metric đếm đủ 30 requests, đợi observation hoàn tất và assert timer count phù hợp, tránh race với background exporter.

### 11.3. Test lỗi trước routing và adversarial paths

Dùng 100 đường dẫn ngẫu nhiên như `/not-a-route/a_1` tới `/not-a-route/a_100`. Nếu API không match handler nào, metric labels phải gom thành số nhỏ các giá trị cố định (`NOT_FOUND`/`UNKNOWN` tùy framework), **không chứa các suffix ngẫu nhiên**.

Gửi thêm:
 
- Request không Bearer token → 401 tại filter; label vẫn hữu hạn.
- Request có route matched nhưng domain ID không tồn tại → 404; có thể mang matched template.
- `GET` với `If-None-Match` khớp → 304; route/template không đổi.
- `PATCH` với `If-Match` stale → 412; metric status riêng, route không đổi.
- Lỗi bất ngờ dẫn tới 500, timeout upstream, rate limit 429 → không dùng exception message, client IP hay retry token làm tag.
- Method không hỗ trợ và request path chứa UTF-8/percent-encoding → label không chứa raw encoding/ID.

Với hệ thống có gateway, tạo test ở **cả gateway và app**: một lỗi 413 hoặc 401 trước khi chạm app sẽ không xuất hiện trong `http.server.requests` của app nhưng vẫn phải được tính trong metric gateway. Nếu dashboard dùng cả hai nguồn, xác định rõ request đi qua đâu để tránh đếm hai lần.

### 11.4. Hàng rào build/CI

Một test CI hoặc validation cấu hình có thể thất bại nếu:

1. Có tag key `userId`, `tenantId`, `orderId`, `traceId`, `requestPath` ở HTTP meters.
2. Có raw URI như `/v1/orders/ord_*` trong các giá trị `uri`.
3. Số distinct `uri` values sau một nhóm random-ID requests tăng theo số request.
4. `MeterFilter` chạm trần mà không có alert và không xác định được nguyên nhân.
5. Đổi tên route template làm recording rules/alerts trống mà không được review.

Những kiểm tra này bổ sung cho kiểm thử REST thông thường: status, body/Problem Details, phân trang, `ETag` và object-level authorization vẫn phải đúng.

## 12. Bài thực hành: dashboard cho Orders API đa tenant

**Bối cảnh:** hệ thống nhận `GET /v1/orders/{orderId}`, `PATCH /v1/orders/{orderId}`, `POST /v1/orders` và `GET /v1/orders` (phân trang). Người dùng có thể gửi hàng nghìn ID hợp lệ hoặc không tồn tại; API dùng JWT, tenant isolation, conditional requests và retry. Prometheus đang thấy hàng trăm nghìn series với label `uri` chứa ID.

**Yêu cầu:**

1. Chỉ rõ nguyên nhân cardinality; ước tính số series theo route/method/status/instance/buckets và so sánh với cách gắn ID.
2. Chuyển HTTP instrumentation sang matched route template, quy ước fallback `NOT_FOUND`/`UNKNOWN`; không dùng regex thay số thay router.
3. Cấu hình Spring Boot Actuator/Micrometer và bảo vệ `/actuator/prometheus`.
4. Đưa ra ngân sách nhãn và `MeterFilter` để ngăn regression; giải thích vì sao `MeterFilter.deny()` không thay phép normalize từ đầu.
5. Viết PromQL request rate, 5xx ratio và p95 latency theo route; tách 304, 412 và 429 khỏi server-error SLO.
6. Viết unit test `RouteLabels` và integration test 100 order IDs cùng URI template; test 100 unmapped random paths.
7. Thử token thiếu, cross-tenant, error 404/409/412/429/500 và khẳng định labels không chứa ID hay token.
8. Đề xuất cách truy vấn một request cụ thể theo trace ID và logs đã lọc, không đặt trace ID thành metric label.
9. Mô tả khi `POST /orders` được retry với cùng idempotency key: HTTP attempt counter tăng nhiều lần nhưng business `orders.created` chỉ tăng khi có một đơn mới.
10. Đối chiếu route templates giữa Spring controllers, OpenAPI `/v1/orders/{orderId}` và dashboard queries; xác định quy trình review khi đổi tên biến path.

**Tiêu chí đạt:** số `uri` tag values tỷ lệ với **số route template đã triển khai**, không tỷ lệ với số order/users/requests; không có dữ liệu nhạy cảm trong labels; dashboard có thể phân biệt latency, 5xx và 4xx nghiệp vụ; test có thể phát hiện lại lỗi raw-path labels sau một refactor.

## 13. Tổng kết

**Route template là đơn vị nhóm phù hợp cho HTTP metrics của REST API.** Raw URI chứa ID, query, token hoặc tên file làm tăng cardinality, có thể rò dữ liệu và khiến hệ thống observability khó vận hành. Với Spring Boot/Micrometer, ưu tiên instrumentation có sẵn lấy matched pattern từ router, rồi đặt guardrails bằng allowlist/budget và regression tests.

Giữ các nhãn **method + route template + status** và một số chiều thấp khác đủ để đo RPS, error rate, latency. Dùng **trace ID và logs/traces có kiểm soát** để điều tra request cụ thể; đừng làm metric labels trở thành kho chứa định danh. Quan sát tốt là đo **đúng mức độ tổng hợp**, bảo toàn chính sách bảo mật và kiểm chứng bằng request HTTP thật.

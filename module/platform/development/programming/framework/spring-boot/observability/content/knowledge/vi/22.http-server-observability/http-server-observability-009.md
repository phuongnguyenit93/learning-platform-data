# Servlet instrumentation trong Spring Boot

Trong ứng dụng Spring Boot dùng Servlet stack, mỗi HTTP request đi qua container, filter chain, Spring Security, DispatcherServlet, controller và các tầng nghiệp vụ. Để biết request nào chậm, trả lỗi ở đâu hoặc gọi dependency nào, ta cần quan sát request ở ranh giới HTTP server. **Servlet instrumentation** tạo context quan sát cho vòng đời request/response, ghi nhận các đặc điểm HTTP cần thiết và liên kết spans/logs với phần xử lý bên trong ứng dụng.

Trong module **SPRING_BOOT_OBSERVABILITY**, Servlet instrumentation là một phần của HTTP server observability cùng Micrometer Observation, metrics, logs và distributed tracing. Bài thuộc chương **HTTP server observability**, tập trung vào **Servlet instrumentation**: cách Spring Boot tự động quan sát request, vai trò của Servlet Filter và Observation convention, cách bổ sung metadata nghiệp vụ an toàn, xử lý async/error dispatch, kiểm soát cardinality, kiểm thử và điều tra khi dữ liệu HTTP server không chính xác.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vòng đời HTTP request trong Servlet container và vị trí instrumentation.
2. Giải thích quan hệ giữa Servlet Filter, Micrometer Observation, metrics và tracing.
3. Nhận biết auto-instrumentation do Spring Boot cung cấp và tránh tạo instrumentation trùng.
4. Đọc HTTP server metrics phổ biến như request count và duration theo route/status.
5. Hiểu cách trace server span liên kết với trace context từ client.
6. Bổ sung custom Observation hoặc filter metadata mà không thay đổi semantics HTTP.
7. Xử lý async dispatch, error dispatch, security chain và context cleanup.
8. Kiểm soát route cardinality, dữ liệu nhạy cảm và log correlation.
9. Viết test ở cả tầng Observation, MockMvc và embedded servlet container.

## 1. Servlet instrumentation là gì?

Servlet instrumentation là việc gắn khả năng đo lường và tracing vào vòng đời request của Servlet API. Instrumentation có thể được thực hiện bởi filter, interceptor hoặc integration chuyên biệt của framework/container. Với Spring Boot, HTTP server instrumentation thường được cấu hình tự động khi ứng dụng dùng Spring MVC/Servlet stack và các dependency observability phù hợp.

Một HTTP server observation thường bắt đầu khi request đi vào server boundary và kết thúc khi response hoàn tất. Trong khoảng đó, hệ thống có thể ghi nhận HTTP method, route template, response status, thời gian xử lý, exception/error, trace context và Resource identity.

### 1.1. Vị trí trong Servlet request lifecycle

~~~mermaid
flowchart TD
    Client["HTTP client"] --> Container["Servlet container"]
    Container --> Filters["Servlet Filter chain"]
    Filters --> Security["Spring Security filters"]
    Security --> Dispatcher["DispatcherServlet"]
    Dispatcher --> Handler["HandlerMapping / Controller"]
    Handler --> Service["Application service"]
    Service --> Response["Build response"]
    Response --> Dispatcher
    Dispatcher --> Security
    Security --> Filters
    Filters --> Container
    Container --> Client
    Filters -. "Observation / server span" .-> Telemetry["Metrics / traces / logs"]
~~~

Vị trí cụ thể của tracing filter và security filters phụ thuộc auto-configuration và thứ tự filter. Khi cần quan sát toàn bộ request, cần bảo đảm instrumentation nằm ở ranh giới phù hợp và không bị đăng ký hai lần.

### 1.2. Filter, HandlerInterceptor và Observation

| Cơ chế | Phạm vi | Dùng khi nào |
| --- | --- | --- |
| Servlet Filter | Servlet request/response và filter chain | Cross-cutting concern ở server boundary |
| Spring MVC HandlerInterceptor | Trước/sau controller handler | Metadata gắn với handler đã được định tuyến |
| Micrometer Observation | Mô hình quan sát thống nhất | Lifecycle, context và handlers cho metrics/tracing |
| Container instrumentation | Tích hợp sát container/runtime | Quan sát ở tầng container nếu nền tảng cung cấp |

Filter nhìn thấy request trước khi handler được chọn. HandlerInterceptor có thể đọc handler/route đã map nhưng chỉ áp dụng trong Spring MVC. Observation là abstraction cho lifecycle và handlers; nó không đồng nghĩa với một loại filter cụ thể.

## 2. Spring Boot tự động instrument HTTP server

Trong ứng dụng Spring Boot Servlet, các dependency observability và tracing phù hợp giúp auto-configuration gắn instrumentation vào request lifecycle. Khi bật Actuator/Micrometer Observation, Spring MVC server requests có thể được quan sát và tạo metrics; khi thêm Micrometer Tracing bridge, observations phù hợp có thể tạo spans.

Dependency minh họa cho Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Giữ versions theo Spring Boot BOM. Không thêm version Micrometer/OpenTelemetry riêng lẻ nếu BOM đã quản lý; kiểm tra compatibility trước khi nâng cấp.

### 2.1. Observation và tracing bridge

Micrometer Observation cung cấp API biểu diễn một operation được quan sát. Observation có lifecycle bắt đầu/kết thúc, context mang metadata và handlers có thể chuyển observation thành metrics hoặc tracing.

Với HTTP server request:

1. Instrumentation phát hiện request bắt đầu.
2. Tạo Observation/context tương ứng.
3. Ghi nhận method và metadata ban đầu.
4. Khi route được xác định, convention có thể bổ sung route template.
5. Khi response kết thúc, instrumentation ghi status, outcome và duration.
6. Observation handlers cập nhật meter và/hoặc tracing span theo cấu hình.

Một Observation không tự bảo đảm có cả metrics lẫn trace. Kết quả phụ thuộc handlers, registry, tracing bridge, sampler và exporter.

### 2.2. Metrics và tracing có lifecycle khác nhau

- HTTP server metrics tổng hợp nhiều requests thành counters/timers/histograms.
- Server span đại diện một request hoặc một đoạn xử lý trong trace.
- Log events được ghi trong quá trình xử lý có thể mang traceId/spanId qua MDC.
- Exporter đưa spans ra Collector/backend; registry hoặc exporter riêng đưa metrics tới nơi lưu.

Không dùng số lượng spans đã sampling để thay thế request count từ metrics.

### 2.3. Resource identity của server

Mỗi instance Spring Boot cần Resource identity ổn định như service.name, service.version, environment và instance ID. Resource trả lời service nào phát telemetry; route/method/status là thuộc tính request. Không đưa request ID, user ID hoặc URL raw vào Resource.

## 3. HTTP server metrics: request count và duration

Spring Boot/Micrometer có thể phát các HTTP server measurements. Tên meter và tags cụ thể phụ thuộc Spring Boot/Micrometer version và registry. Với các phiên bản Spring Boot phổ biến, meter HTTP server thường có tên dạng http.server.requests; hãy kiểm tra meter thật qua Actuator hoặc registry thay vì giả định schema cố định.

Các dimension thường có ích:

| Dimension | Ví dụ | Cardinality |
| --- | --- | --- |
| method | GET, POST | Thấp |
| uri/route | /orders/{orderId} | Nên là route template |
| status | 200, 404, 500 | Thấp |
| outcome | SUCCESS, CLIENT_ERROR, SERVER_ERROR | Thấp |
| exception | Tên exception hoặc NONE | Cần kiểm soát |
| application/service | order-service | Tập service hữu hạn |

### 3.1. Route template thay vì raw URI

Không ghi metric tag theo raw path như:

~~~text
/orders/10001
/orders/10002
/orders/10003
~~~

Nếu mỗi order ID trở thành một giá trị tag, mỗi request có thể tạo một time series mới. Dùng route template ổn định:

~~~text
/orders/{orderId}
~~~

Route template thể hiện endpoint logic và giữ cardinality có thể kiểm soát. Trước khi route được xác định, instrumentation có thể dùng placeholder hoặc route value khác; kiểm tra output ở đúng framework/version.

### 3.2. Ví dụ truy vấn Prometheus

Request rate từ histogram/count series, tùy tên metric được expose:

~~~promql
sum by (uri, method) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Tỷ lệ HTTP 5xx:

~~~promql
sum(rate(http_server_requests_seconds_count{status=~"5.."}[5m]))
/
sum(rate(http_server_requests_seconds_count[5m]))
~~~

p95 latency với classic histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Các ví dụ giả định registry expose histogram metric với tên/labels tương ứng. Tên uri, status, method, suffix _seconds và bucket availability có thể khác theo phiên bản hoặc cấu hình. Xem output scrape thực tế và điều chỉnh query.

### 3.3. Histogram và percentile

Nếu cần p95/p99 trên Prometheus, histogram phải được bật/cấu hình phù hợp. Timer có thể export count/sum; percentile histogram hoặc SLO boundaries cần bật theo meter distribution configuration. Client-side percentile không giống server-side histogram quantile: kiểm tra backend và cách tổng hợp giữa nhiều instances.

## 4. Tracing server span và trace context

Khi request đi vào Spring Boot, server instrumentation có thể extract context từ incoming headers như W3C traceparent, tiếp tục trace hiện hữu nếu context hợp lệ, tạo trace mới nếu không có remote parent, tạo server span bao quanh request handling, đặt span active trong execution scope và kết thúc span khi request hoàn thành.

Ví dụ header W3C:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

traceparent mang Trace ID, Parent ID và trace flags. Baggage là header khác, mang các cặp metadata được kiểm soát; không dùng baggage thay cho authentication hoặc authorization.

### 4.1. Server span và downstream client span

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Collector
    Client->>Order: POST /orders + traceparent
    Note over Order: SERVER span A
    Order->>Inventory: HTTP request + child context
    Note over Inventory: SERVER span C
    Inventory-->>Order: Response
    Order-->>Client: HTTP 201
    Order->>Collector: Export order spans
    Inventory->>Collector: Export inventory spans
~~~

Trace ID được dùng chung xuyên service. Mỗi service phát spans với Resource identity riêng. HTTP client instrumentation ở order-service tạo client span; server instrumentation ở inventory-service tạo server span có quan hệ parent phù hợp.

### 4.2. Sampling

Head-based sampler quyết định sớm trace có được recording/export hay không. Nếu trace bị drop ngay khi bắt đầu, lỗi xảy ra ở cuối request không thể tự khiến SDK gửi lại spans đã bị loại. Tail sampling tại Collector có thể ưu tiên lỗi hoặc latency cao nếu SDK gửi đủ dữ liệu tới Collector và routing theo trace ID được bảo đảm.

Metrics HTTP vẫn cần ghi nhận toàn request theo instrumentation ngay cả khi traces được sampling. Dùng metrics cho request rate, error ratio và SLO; dùng trace samples để điều tra.

## 5. Bổ sung metadata bằng ObservationConvention

Khi mặc định instrumentation chưa cung cấp metadata nghiệp vụ cần thiết, có thể dùng ObservationConvention hoặc custom Observation. Ưu tiên convention có sẵn và extension point của Spring Boot/Micrometer trước khi tự viết filter tạo span.

Ví dụ custom business Observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final ObservationRegistry observationRegistry;

    public OrderService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public void createOrder() {
        Observation.createNotStarted("orders.create", observationRegistry)
                .lowCardinalityKeyValue("orders.channel", "web")
                .observe(() -> {
                    reserveInventory();
                    authorizePayment();
                });
    }

    private void reserveInventory() {
        // Call inventory dependency.
    }

    private void authorizePayment() {
        // Call payment dependency.
    }
}
~~~

Đây là custom business observation bên trong HTTP server request. Nó không thay thế server instrumentation và không nên tạo thêm server span trùng. Chỉ thêm low-cardinality keys có tập giá trị nhỏ; không đưa order ID, email hoặc raw URL thành low-cardinality tags.

### 5.1. Low-cardinality và high-cardinality

Micrometer Observation phân biệt low-cardinality key-values (có thể được dùng cho metrics và tracing handlers) với high-cardinality key-values (phù hợp hơn cho span metadata nếu cần, không nên trở thành metric labels). Dù high-cardinality key không thành metric label, nó vẫn có thể tăng chi phí indexing hoặc tiết lộ dữ liệu. Cần privacy review và giới hạn kích thước.

### 5.2. Đặt tên operation có ý nghĩa

Observation name nên ổn định và mô tả thao tác, ví dụ orders.create hoặc inventory.reserve. Không gắn ID vào observation name như orders.create.10001. Dùng route template/operation name để tổng hợp và tìm kiếm.

## 6. Khi nào cần tự viết Servlet Filter?

Spring Boot thường đã cung cấp HTTP server instrumentation khi dependencies/configuration phù hợp. Tự viết filter chỉ để tạo thêm server span thường gây hai spans bao quanh cùng request, metrics request count bị đếm hai lần, route/status/duration không thống nhất, duplicate trace correlation và sai thứ tự security/async handling.

Trước khi viết filter, xác định yêu cầu có thể giải quyết bằng:
1. ObservationConvention hoặc extension point hiện hữu.
2. Custom business Observation.
3. HandlerInterceptor nếu cần metadata sau khi MVC đã chọn handler.
4. Filter riêng cho metadata/cross-cutting behavior thực sự không có extension point phù hợp.

### 6.1. Ví dụ filter cho metadata không nhạy cảm

Nếu cần ghi nhận channel header đã được xác thực, filter có thể đặt business context field riêng. Ví dụ minh họa:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Locale;
import java.util.Set;

@Component
public class OrderChannelLoggingFilter extends OncePerRequestFilter {
    private static final Set<String> ALLOWED =
            Set.of("web", "partner", "batch");

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {

        String candidate = request.getHeader("X-Order-Channel");
        String channel = candidate == null
                ? "unknown"
                : candidate.trim().toLowerCase(Locale.ROOT);

        if (!ALLOWED.contains(channel)) {
            channel = "unknown";
        }

        String previous = MDC.get("orders.channel");
        try {
            MDC.put("orders.channel", channel);
            filterChain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.remove("orders.channel");
            } else {
                MDC.put("orders.channel", previous);
            }
        }
    }
}
~~~

Ví dụ minh họa allowlist hữu hạn và cleanup. Trong production, channel phải đến từ nguồn đáng tin đã xác minh; nếu caller có thể tự đặt header, không dùng nó làm bằng chứng về loại đối tác hoặc quyền. Nếu metadata đã được thiết lập trong scope khác, lưu/restore giá trị trước đó thay vì luôn remove.

### 6.2. OncePerRequestFilter và dispatcher types

Servlet có dispatcher types REQUEST, ASYNC, ERROR, FORWARD và INCLUDE. OncePerRequestFilter có các hook để quyết định skip async/error dispatch; default behavior và cách registration cần được hiểu theo phiên bản Spring. Filter custom có thể chạy ở request dispatch nhưng không chạy ở async dispatch hoặc error dispatch tùy cấu hình.

Không dùng filter custom để mô phỏng toàn bộ span lifecycle nếu chưa xử lý dispatcher types và async completion đúng cách.

## 7. Async servlet request và request lifecycle

Servlet async cho phép container giải phóng request thread ban đầu trong khi response vẫn đang được xử lý. Request lifecycle có thể kéo dài qua nhiều thread và dispatch. Nếu instrumentation chỉ kết thúc span khi thread ban đầu thoát khỏi filter chain, duration có thể sai hoặc context bị đóng quá sớm.

~~~mermaid
sequenceDiagram
    participant Container
    participant Filter
    participant Controller
    participant Worker
    participant Client
    Container->>Filter: REQUEST dispatch
    Filter->>Controller: doFilter
    Controller->>Container: startAsync()
    Container-->>Filter: Initial thread returns
    Container->>Worker: Execute async work
    Worker->>Container: Complete / dispatch
    Container->>Filter: ASYNC dispatch or completion callback
    Filter-->>Container: Finish lifecycle
    Container-->>Client: Response completed
~~~

Instrumentation cần tương thích Servlet async lifecycle để server span bao phủ đúng thời gian request/response. Không giữ MDC/ThreadLocal trong thread cũ rồi giả định async worker nhìn thấy. Cần context propagation phù hợp và test với embedded container.

### 7.1. Error dispatch

Khi controller ném exception, Spring exception resolver hoặc container error dispatch có thể xử lý response. Instrumentation cần phân biệt exception đã được xử lý với lỗi thực sự của request và status cuối. Không tạo thêm server span ở ERROR dispatch nếu request đã có span chính, trừ khi behavior đó có chủ đích.

### 7.2. Timeout và cancellation

Request timeout/cancel có thể kết thúc theo lifecycle khác với response thành công. Quan sát status, exception và duration từ request thật. Kiểm thử timeout server, client disconnect và async operation bị hủy nếu ứng dụng có các trường hợp này.

## 8. Thứ tự Filter, Spring Security và route mapping

Thứ tự filter ảnh hưởng tới những gì instrumentation nhìn thấy:

- Filter trước security có thể quan sát cả request bị authentication/authorization từ chối.
- Filter sau security có thể chỉ thấy request đã qua một số bước security.
- Filter gần DispatcherServlet có thể dễ đọc route/handler hơn nhưng không bao phủ mọi request ngoài MVC.
- Error/async dispatch cần filter registration phù hợp.

Không thay đổi thứ tự filter chỉ để thêm correlation nếu chưa hiểu behavior security. Tracing instrumentation không được làm lộ token, session cookie hoặc principal details trong span/log attributes.

### 8.1. Không log Authorization hoặc cookies

Request headers thường chứa credential. Không copy toàn bộ headers vào Observation, span attributes hoặc MDC. Nếu cần ghi nhận authentication outcome, dùng category hữu hạn như authenticated, anonymous, rejected; không ghi raw identity/token.

### 8.2. Route template và exception mapping

Route tag nên là route template như /orders/{orderId}, không phải raw path. Exception tag cần được kiểm soát; class name có thể hữu ích nhưng message thường chứa dữ liệu nhạy cảm hoặc giá trị động. Status cuối cần khớp response thật sau exception handling.

## 9. Cardinality và dữ liệu trong HTTP server telemetry

| Giá trị | Nên dùng làm metric tag? | Lý do |
| --- | --- | --- |
| HTTP method | Có | Tập nhỏ |
| Route template | Có, nếu chuẩn hóa | Endpoint hữu hạn |
| Status code/outcome | Có | Tập giá trị hữu hạn |
| Service name | Có theo mô hình metric | Ổn định |
| Raw URL/query string | Không | Biến thiên và có thể chứa PII |
| Request ID/Trace ID | Không | Gần như duy nhất mỗi request |
| User/customer ID | Không | Cardinality cao và nhạy cảm |
| Exception message | Không | Tự do, dễ chứa dữ liệu |
| Remote IP | Không mặc định | Cardinality/privacy/security |
| User agent raw | Không mặc định | Đa dạng và dài |

Span attributes vẫn có thể làm payload OTLP phình lớn nếu lưu header, query string hoặc body. Chỉ ghi field cần thiết, đặt giới hạn kích thước và redact dữ liệu. Không nhầm không phải metric label với không tốn chi phí.

### 9.1. Correlation IDs trong logs

Trace ID/span ID có thể được gắn vào MDC khi server span active. Logging pattern/structured encoder phải xuất đúng key. MDC không thay thế server instrumentation, và log có trace ID không chứng minh trace đã được sampling/export thành công.

## 10. Kiểm thử Servlet instrumentation

Nên test cả metrics/Observation behavior và trace propagation. Mỗi tầng chứng minh một điều khác nhau.

| Loại test | Dùng để xác minh | Giới hạn |
| --- | --- | --- |
| Observation unit test | Custom Observation name, tags và lifecycle | Không chạy servlet container |
| MockMvc test | MVC routing, filter/interceptor và response | Không mô phỏng đầy đủ embedded container/async |
| Embedded server integration test | Servlet filters, status, async dispatch và instrumentation thật | Tốn thời gian hơn |
| Tracing exporter test | Span IDs, parent relationship, Resource | Không nhất thiết kiểm tra toàn network |
| OTLP smoke test | Export đến Collector/backend | Cần Collector test hoặc receiver giả |

### 10.1. Test custom Observation

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class OrderObservationTest {
    @Test
    void recordsOrderOperation() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted("orders.create", registry)
                .lowCardinalityKeyValue("orders.channel", "web")
                .observe(() -> { });

        assertThat(registry.getCompletedObservationContexts()).hasSize(1);
    }
}
~~~

Đây là ví dụ kiểm tra lifecycle cơ bản; API assertion cụ thể có thể thay đổi theo Micrometer version. Nó không chứng minh HTTP server filter hay OTLP exporter hoạt động.

### 10.2. MockMvc và embedded server

MockMvc có thể xác minh controller response, status và route, nhưng không đi qua cùng embedded Tomcat/Jetty/Undertow lifecycle như request qua socket. Nếu mục tiêu là Servlet container instrumentation, dùng integration test với embedded server.

Một test với SpringBootTest và RANDOM_PORT có thể:
1. Gửi HTTP request tới embedded server.
2. Thu HTTP server meters từ MeterRegistry.
3. Kiểm tra meter count tăng.
4. Gửi request có incoming traceparent.
5. Kiểm tra server span giữ Trace ID và parent relationship đúng.
6. Gửi request lỗi và xác minh status/exception semantics.
7. Gửi async request nếu ứng dụng dùng Servlet async; kiểm tra span chỉ kết thúc khi response hoàn tất.
8. Xác minh MDC correlation trong log event nếu logging test appender được cấu hình.

Không hard-code IDs vì chúng được tạo động. Assert quan hệ và sự hiện diện.

### 10.3. Test cardinality regression

Gửi nhiều requests với order IDs khác nhau tới cùng route. Xác minh meter vẫn dùng route template /orders/{orderId} thay vì tạo tag value cho mỗi raw path. Test này ngăn thay đổi filter/convention làm tăng time series.

## 11. Troubleshooting Servlet instrumentation

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không có HTTP server meter | Thiếu Actuator/Observation handler hoặc instrumentation bị tắt | Kiểm tra dependency, MeterRegistry và meter thật |
| Meter có nhưng URI là UNKNOWN | Route chưa được xác định hoặc request ngoài MVC mapping | Kiểm tra route mapping và convention |
| Mỗi order ID tạo một series | Raw URI dùng làm tag | Dùng route template, bỏ dynamic path |
| HTTP metrics đếm gấp đôi | Custom filter/Observation trùng auto-instrumentation | Kiểm tra filter beans và handler registration |
| Không có server span | Tracing bridge/sampler/instrumentation chưa hoạt động | Kiểm tra active tracer và sampling |
| Trace ID không nối từ client | Propagator/header/context extraction sai | Kiểm tra traceparent |
| Span kết thúc quá sớm ở async | Filter lifecycle không theo async completion | Test embedded container và async dispatch |
| Error response không có status mong đợi | Exception resolver/container error dispatch thay đổi response | Kiểm tra final status và error handling |
| Log thiếu traceId/spanId | MDC integration/pattern không hoạt động | Kiểm tra MDC và encoder |
| MDC rò rỉ qua request | Custom filter không restore/clear context | finally và test thread reuse |
| Collector không nhận trace | Exporter endpoint/network/auth sai | Kiểm tra OTLP và receiver |
| Filter không chạy trên ERROR dispatch | Dispatcher type/OncePerRequestFilter hook | Xem filter registration và skip logic |
| Request 401 không có trace | Filter order/instrumentation đặt sau security | Kiểm tra filter chain và security order |

### 11.1. Quy trình điều tra

1. Xác minh request thực sự vào embedded servlet container.
2. Kiểm tra Actuator, ObservationRegistry và MeterRegistry được cấu hình.
3. Xem HTTP server meter thật và tag values.
4. Kiểm tra tracing bridge, active span và sampling decision.
5. Đối chiếu server span với incoming traceparent.
6. Kiểm tra filter order, async/error dispatch và exception handling.
7. Xác minh exporter/Collector nếu span được tạo nhưng backend không có trace.
8. Kiểm tra logs sau encoder/appender để xác định MDC fields có thực sự được xuất.

Không thêm filter tạo server span thứ hai trước khi xác định auto-configuration hiện tại đang làm gì.

## 12. Production checklist

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Servlet stack được nhận diện | Spring MVC và embedded container được cấu hình |
| HTTP server Observation hoạt động | Request lifecycle được ghi nhận một lần |
| Metrics tags có cardinality thấp | Route template, method, status/outcome chuẩn hóa |
| Server span được tạo đúng | Trace ID, span kind và status hợp lý |
| Propagation được kiểm thử | Incoming traceparent nối đúng |
| Resource identity đúng | service.name/version/environment cho instance |
| Async/error dispatch được xác minh | Span kết thúc theo response lifecycle |
| Filter order có chủ đích | Security và instrumentation không che nhau |
| Không có duplicate instrumentation | Meter/span count không bị nhân đôi |
| Không xuất dữ liệu nhạy cảm | Headers/body/token/PII được lọc |
| MDC được cleanup | Không có context từ request trước |
| Export pipeline được giám sát | Queue, exporter errors, Collector drops |
| Metrics SLI độc lập với sampling | Request count/error rate không lấy từ traces |
| Regression tests đủ tầng | Observation, MVC, embedded server và cardinality |

## 13. Bài thực hành: instrument order-service Servlet stack

**Bối cảnh:** order-service dùng Spring MVC trên Servlet container, có endpoint POST /orders/{orderId} và gọi inventory-service. Đội vận hành cần HTTP metrics, server spans và logs có trace/span IDs. Một custom filter hiện đang thêm request metadata.

**Nhiệm vụ:**

1. Bật Actuator và Micrometer Tracing bridge phù hợp Spring Boot BOM.
2. Xác minh HTTP server instrumentation tạo Observation/metrics và server span.
3. Gửi nhiều requests với order IDs khác nhau; chứng minh meter chỉ dùng route template, không raw URI.
4. Gửi request có traceparent từ test client; kiểm tra Trace ID/Parent ID và server span.
5. Tạo business Observation orders.create với low-cardinality tag orders.channel.
6. Kiểm tra custom filter: chỉ giữ metadata đã xác thực, không tạo span/metric duplicate, restore MDC trong finally.
7. Gửi request qua Spring Security; kiểm tra 200 và 401/403 theo filter order.
8. Tạo async endpoint/Servlet operation nếu ứng dụng sử dụng; xác minh server span kết thúc sau response hoàn tất.
9. Tạo lỗi 4xx và 5xx; xác minh final status, span status và metrics outcome.
10. Capture logs và xác minh traceId/spanId đúng trong controller/service/client span.
11. Chạy test cardinality với nhiều order IDs và thread reuse để phát hiện context leak.
12. Viết runbook cho trường hợp metrics có nhưng trace thiếu, meter đếm đôi hoặc URI tag tăng bất thường.

**Kết quả mong đợi:** cấu hình dependencies, bằng chứng HTTP server Observation/metrics/traces, custom convention/filter có kiểm soát, test ở MVC và embedded server, cùng runbook vận hành.

## 14. Ghi nhớ

**Servlet instrumentation** quan sát HTTP request ở ranh giới Servlet server và liên kết lifecycle đó với metrics/tracing. Spring Boot/Micrometer có thể tự động cung cấp HTTP server Observation khi dependencies và cấu hình phù hợp; custom Filter chỉ nên bổ sung behavior còn thiếu và phải tránh đếm hoặc tạo spans trùng.

Route template, method và status là các dimension hữu ích cho HTTP metrics; raw URL, request ID, user ID và exception message không phù hợp làm metric tags. Incoming traceparent nối server span với trace bên ngoài; Resource xác định service phát telemetry; MDC giúp log event mang traceId/spanId. Async/error dispatch, filter order, context cleanup, privacy và cardinality phải được kiểm thử bằng embedded servlet container. Dùng metrics làm nguồn SLI, traces để điều tra và logs để xem sự kiện theo context.

**Tài liệu tham khảo:**
- [Spring Boot — HTTP Server Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Jakarta Servlet Specification](https://jakarta.ee/specifications/servlet/)
- [OpenTelemetry — HTTP Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/http/)


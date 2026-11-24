# Tracing phân tán và truyền trace context xuống dịch vụ

## 1. Vì sao API Gateway cần distributed tracing?

Trong kiến trúc microservices, **Spring Cloud Gateway** là nơi tiếp nhận request, chọn route bằng predicate, thực thi filter chain, biến đổi path/header và chuyển tiếp đến backend qua URL cố định hoặc service discovery/load balancing. Trên cùng đường đi đó, Gateway có thể thực hiện xác thực, giới hạn lưu lượng, circuit breaker, retry, TLS và ghi nhận thông tin quan sát hệ thống.

Hãy xét yêu cầu:

~~~text
GET /api/orders/42
  -> API Gateway
  -> order-service
  -> inventory-service
  -> database
~~~

Khi client thấy `504 Gateway Timeout`, chỉ một dòng access log của Gateway thường không đủ để trả lời:

- Gateway đã chọn **route nào**, gọi instance nào?
- Lỗi xảy ra trước khi kết nối upstream hay sau khi backend đã bắt đầu xử lý?
- `order-service` chờ `inventory-service` bao lâu?
- Retry đã tạo thêm bao nhiêu lần gọi và tăng latency như thế nào?
- Các log ở Gateway và hai service có thực sự thuộc **cùng một request logic**?

**Distributed tracing** giải quyết bài toán liên kết những phần xử lý nằm trên nhiều tiến trình, thread và dịch vụ. Mỗi phần việc được biểu diễn bằng một **span**, còn toàn bộ đường đi thuộc một **trace** có định danh chung.

Bài học **“Tracing phân tán và truyền trace context xuống dịch vụ”** thuộc chương **Quan sát hệ thống** của module **SPRING_CLOUD_GATEWAY**. Mục tiêu là hiểu **cơ chế truyền context qua HTTP**, cấu hình Micrometer Tracing/OpenTelemetry, kiểm chứng Gateway và backend nằm trong cùng trace, đồng thời giữ tracing an toàn và có chi phí hợp lý khi vận hành.

Sau bài này, bạn có thể:

1. Phân biệt `traceId`, `spanId`, `parentSpanId`, sampling, baggage và request ID.
2. Đọc header W3C `traceparent`, `tracestate`, `baggage`.
3. Cấu hình trace export cho Gateway Server WebFlux và backend Spring Boot với phân biệt **Boot 3.5 / Boot 4.x**.
4. Kiểm tra trace context được **extract từ inbound request** và **inject vào outbound request** gửi đến service.
5. Hiểu vì sao Reactor Context/Micrometer Context Propagation quan trọng khi luồng reactive đổi scheduler.
6. Test qua mock upstream, trace backend và logs mà không phụ thuộc chỉ vào HTTP 200.
7. Nhận diện trace đứt đoạn do custom HTTP client, sampling, proxy xóa header, retry hoặc thiếu instrumentation.
8. Hạn chế rủi ro dữ liệu nhạy cảm, header giả mạo, metric cardinality và chi phí lưu trữ spans.

> **Phạm vi:** trọng tâm là **Spring Cloud Gateway Server WebFlux** trên Spring Boot hiện đại. Gateway Server Web MVC và Proxy Exchange MVC có threading/filter API khác; các nguyên lý W3C propagation vẫn dùng được nhưng ví dụ WebFlux không thể chép nguyên sang Servlet. Những cấu hình phụ thuộc phiên bản được ghi rõ; hãy kiểm tra effective configuration của release train đang triển khai.

## 2. Trace là một cây công việc, không chỉ là một request ID

### 2.1. Trace, span và quan hệ cha-con

Các khái niệm cơ bản:

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Trace** | Toàn bộ chuỗi xử lý một request logic đi qua các hệ thống | Request xem đơn hàng |
| **Trace ID** | Mã chung liên kết những spans cùng trace | 32 chữ số hex (128 bit trong W3C) |
| **Span** | Một đơn vị công việc có bắt đầu, kết thúc và attributes | Gateway nhận HTTP; Gateway gọi order-service |
| **Span ID** | Mã riêng của một span | 16 chữ số hex (64 bit trong W3C) |
| **Parent span ID** | Liên kết span con với phần việc gọi nó | Gateway outbound span là cha của service inbound span |
| **Span kind** | Vai trò SERVER, CLIENT, INTERNAL, PRODUCER, CONSUMER | HTTP server/client |
| **Attributes** | Metadata mô tả span | HTTP method, route ID, status |
| **Events** | Những mốc xảy ra trong span | Timeout, exception được ghi nhận |
| **Status** | Kết quả theo ngữ nghĩa tracing | OK/ERROR/UNSET tùy implementation |
| **Sampling** | Quyết định có ghi/xuất dữ liệu trace hay không | 10% hoặc chính sách theo parent |

Một đường đi được instrument đầy đủ **thường** có dạng:

~~~mermaid
flowchart TD
    R["Trace ID = T"] --> G1["Gateway SERVER span<br/>GET /api/orders/{id}"]
    G1 --> G2["Gateway CLIENT span<br/>HTTP tới ORDER-SERVICE"]
    G2 --> O1["order-service SERVER span"]
    O1 --> O2["order-service CLIENT span<br/>gọi inventory"]
    O2 --> I1["inventory-service SERVER span"]
    O1 --> DB["DB span nếu driver được instrument"]
~~~

Những spans trong sơ đồ chia sẻ **một trace ID** nhưng có **span IDs khác nhau**. Số lượng/nesting chính xác còn phụ thuộc các thư viện được instrument: một Gateway version có thể tạo Gateway outbound observation, Netty client span hoặc thêm span nội bộ khác. Không bắt integration test phải có đúng năm spans bất kể stack.

### 2.2. Trace ID không phải user ID hay khóa nghiệp vụ

`traceId` chủ yếu để **liên kết quan sát**. Nó không chứng minh request đã được xác thực, không thay `orderId`, không phải idempotency key và không phải credential.

Một user có thể gửi nhiều requests thuộc **những traces khác nhau**. Một trace cũng có thể đi qua nhiều services và chứa nhiều spans. Hệ thống log có thể sử dụng thêm `X-Request-Id` hoặc một operation ID để đối chiếu nghiệp vụ, nhưng **không được tự coi chúng là trace ID**.

### 2.3. Trace phân tán khác metrics và logs

| Tín hiệu | Câu hỏi phù hợp | Ví dụ |
| --- | --- | --- |
| **Metrics** | Bao nhiêu request thất bại, latency p95 ra sao? | `http.server.requests`, Gateway request timer |
| **Logs** | Đã xảy ra sự kiện cụ thể nào? | `traceId`, `spanId`, route ID, error code |
| **Traces** | Một request đi qua những thành phần nào, chậm tại đâu? | Chuỗi spans Gateway → order → inventory |

Ba tín hiệu **bổ sung**, không thay thế nhau. Tracing hữu ích cho điều tra request cụ thể nhưng không nên là công cụ duy nhất để tính SLO/SLI theo tổng số request: do **sampling**, chỉ một phần traffic có thể xuất hiện trong trace backend.

## 3. Truyền trace context qua HTTP bằng W3C Trace Context

Một span ở Gateway không thể tự trở thành parent của span ở backend nếu hai process **không có cách trao đổi context**. Với HTTP, cách phổ biến là dùng chuẩn **W3C Trace Context**.

### 3.1. Cấu trúc header traceparent

Ví dụ hợp lệ:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Dạng tổng quát:

~~~text
traceparent: version-trace-id-parent-id-trace-flags
             00      32 hex   16 hex    2 hex
~~~

| Trường | Ý nghĩa | Trong ví dụ |
| --- | --- | --- |
| `version` | Phiên bản định dạng traceparent | `00` |
| `trace-id` | Mã của toàn trace (128 bit) | `4bf92f3577b34da6a3ce929d0e0e4736` |
| `parent-id` | Span ID của bên gửi header | `00f067aa0ba902b7` |
| `trace-flags` | Bit flags; bit thấp nhất thể hiện sampled hint | `01` |

Đối với version 00, **trace ID và parent ID không được toàn số 0** và phải đúng độ dài/định dạng theo chuẩn. `01` thể hiện bit sampled được bật; `00` có sampled bit tắt. Đây **không phải cách đảm bảo mọi downstream tracer bắt buộc export**: quyết định thực tế còn chịu ảnh hưởng của sampler/tracing SDK và chính sách backend.

### 3.2. Điều gì thay đổi ở Gateway và backend?

Giả sử request từ một client đã có `traceparent`. Hệ thống instrumented có thể xử lý như sau:

~~~text
Client header:
  trace-id = T
  parent-id = C

Gateway nhận request:
  SERVER span id = G1
  trace-id = T
  parent = C

Gateway gửi request đến order-service:
  CLIENT span id = G2
  trace-id = T
  header parent-id thường là G2

order-service nhận request:
  SERVER span id = O1
  trace-id = T
  parent = G2
~~~

**Tính liên tục cần kiểm tra là trace ID và quan hệ span hợp lý**, không phải `spanId` của Gateway và order-service phải bằng nhau. Nếu bạn assert “mọi service có cùng spanId” thì đang nhầm span với trace.

Trường `traceparent` của outbound có thể mang parent ID khác inbound vì Gateway tạo span mới. Không nên **copy nguyên giá trị inbound `traceparent` qua outbound bằng tay** nếu tracing đã được instrument: làm vậy có thể làm mất quan hệ cha-con chính xác.

### 3.3. Tracestate

Một request có thể kèm:

~~~http
tracestate: vendor1=opaque-value
~~~

`tracestate` cho phép các tracing vendors truyền trạng thái bổ sung theo hợp đồng W3C. Đây không phải nơi nhét arbitrary JSON, bearer token hay thông tin nhận dạng khách hàng.

Không tự parse/ghi đè `tracestate` để “ép” sampled hoặc priority nếu bạn không triển khai propagator đúng chuẩn. Tracer/propagator nên quản lý việc extract/inject và giới hạn header.

### 3.4. Baggage: dữ liệu đi cùng trace nhưng không phải trace identity

W3C Baggage là cơ chế khác:

~~~http
baggage: locale=vi,feature-flag=beta
~~~

Dữ liệu baggage có thể được đưa qua nhiều hops nếu propagator được bật và network policy cho phép. Nhưng:

- Baggage **không** phải một phần của ID trace.
- Baggage **không** mặc nhiên xuất hiện thành span attribute hoặc log MDC.
- Baggage có thể đi xa hơn dự đoán, sang các services của đối tác.
- Baggage do client gửi **không đáng tin** để quyết định authentication, tenant hay rate limit.
- Không truyền password, access token, email, số điện thoại, số thẻ, user ID nhạy cảm.
- Cần giới hạn số key/chiều dài giá trị và kiểm soát propagation ở trust boundary.

`tracestate` và `baggage` **không đồng nghĩa**: một bên là thông tin của tracing system, bên kia là key-value context được ứng dụng/tracing libraries chia sẻ.

## 4. Luồng truyền context từ Gateway đến microservice

### 4.1. Một chuỗi HTTP điển hình

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Spring Cloud Gateway
    participant O as order-service
    participant I as inventory-service
    participant T as OTel Collector / Trace Backend
    C->>G: GET /api/orders/42 + traceparent(T,C)
    G->>G: Extract context, tạo SERVER span G1
    G->>O: GET /orders/42 + traceparent(T,G2)
    O->>O: Extract context, tạo SERVER span O1
    O->>I: HTTP + traceparent(T,O2)
    I->>I: Extract context, tạo SERVER span I1
    I-->>O: Response
    O-->>G: Response
    G-->>C: Response
    G-->>T: Export sampled spans
    O-->>T: Export sampled spans
    I-->>T: Export sampled spans
~~~

Sơ đồ không vẽ mọi span nội bộ. Bước export thường **bất đồng bộ và có batch**; việc client nhận HTTP 200 không có nghĩa Collector đã nhận toàn bộ trace ngay tại thời điểm đó.

### 4.2. Instrumentation của cả hai đầu là điều kiện cần

Để có một trace nối liền:

1. **Gateway inbound server** phải extract HTTP trace context hoặc khởi tạo root context.
2. **Gateway outbound HTTP client** phải inject context hiện hành vào request đi tới upstream.
3. **Backend inbound server** phải extract header và tạo span trong cùng trace.
4. Những HTTP calls tiếp theo của backend cũng cần **instrumented clients**.
5. Traces phải được sample/export tới một collector/backend được truy vấn đúng service/trace ID.

Chỉ có `spring-boot-starter-actuator` nhưng không có tracer/exporter phù hợp có thể cho metrics/observations mà **không thấy distributed traces trong UI**. Ngược lại, một `traceparent` được forward thành công cũng không tự chứng minh span của backend đã được export.

### 4.3. Gateway routes không phải trace configuration

Một route WebFlux như:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
~~~

chỉ định cách nhận `/api/orders/**` và chuyển đến `http://localhost:8081/orders/**`. Tracing được bổ sung bởi **Micrometer Observation/Tracing và HTTP server/client instrumentation**, không phải tự được bật chỉ vì có `Path` hay `StripPrefix`.

Trên **Gateway Server WebFlux 4.x** phổ biến, route property tương ứng là `spring.cloud.gateway.routes`. Ở **Server WebFlux 5.x**, tài liệu dùng `spring.cloud.gateway.server.webflux.routes`. Chỉ dùng đúng một namespace theo release, không đặt cả hai cấu hình vào một app.

## 5. Micrometer Observation, Micrometer Tracing và OpenTelemetry khác gì nhau?

| Thành phần | Vai trò | Cần hiểu |
| --- | --- | --- |
| **Micrometer Observation** | Mô tả một hoạt động có thể sinh metrics/tracing | `ObservationRegistry`, conventions, key-values |
| **Micrometer Tracing** | Facade span/trace/baggage cho Java | `Tracer`, `Span`, `Baggage` |
| **OpenTelemetry SDK** | Triển khai tracing và propagators/exporters | Context, span processor, OTLP |
| **OTLP** | Protocol chuyển telemetry từ ứng dụng tới Collector/backend | Không phải trace ID format |
| **OpenTelemetry Collector** | Nhận/xử lý/chuyển tiếp spans | Có thể lọc, batch, export đến Jaeger/Tempo/nhà cung cấp |
| **Jaeger, Tempo, Zipkin** | Backend xem/search traces | Hành vi query/retention tùy sản phẩm |
| **W3C Trace Context** | Định dạng headers qua HTTP | `traceparent`, `tracestate` |
| **W3C Baggage** | Định dạng key-value context qua HTTP | `baggage` |

Khi một Observation được cấu hình với tracing handler, nó có thể tạo span. Nhưng **không phải mọi Observation luôn tạo một span được export**: sampler, handler/tracer implementation, context và exporter quyết định kết quả.

Tài liệu Gateway còn định nghĩa outbound **Gateway HTTP Client Observation**, thường có tên `http.client.requests`. Bảng observability metadata của dự án liệt kê những thuộc tính như HTTP method, status, route ID và route URI. Đó là cơ sở để xem Gateway outbound request trong trace; không nên giả định mỗi filter trong route chain tự có một span.

## 6. Cấu hình mẫu: Gateway WebFlux với Spring Boot 3.5 và OTLP

Đây là biến thể **Spring Boot 3.5 + Spring Cloud Gateway Server WebFlux 4.x tương thích**, dùng **Micrometer Tracing bridge OpenTelemetry** và **OTLP HTTP exporter**.

### 6.1. Dependencies Maven

Giả định `pom.xml` đã dùng Spring Boot parent/BOM và Spring Cloud BOM đúng release train:

~~~xml
<!-- Gateway Server WebFlux starter theo release train 4.x -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway</artifactId>
</dependency>

<!-- Actuator và Micrometer Observation -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<!-- Cầu nối Observation/Tracing sang OpenTelemetry -->
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>

<!-- HTTP/gRPC OTLP exporter do OTel SDK hỗ trợ -->
<dependency>
    <groupId>io.opentelemetry</groupId>
    <artifactId>opentelemetry-exporter-otlp</artifactId>
</dependency>
~~~

**Không ghi version độc lập** của các thư viện trong ví dụ khi project đã có BOM. Nếu Gateway phiên bản bạn dùng đổi tên starter, cần chọn đúng artifact được tài liệu của release đó công bố; snippet trên là **một cấu hình theo dòng 4.x**, không phải template áp dụng cho mọi năm.

Không cần thêm đồng thời Brave, OpenTelemetry bridge và Java agent tùy ý rồi mong hệ thống tự quyết định tracer; **chọn một chiến lược instrumentation/export** và kiểm chứng các spans không bị tạo trùng.

### 6.2. application.yml của Gateway trong lab

~~~yaml
spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: http://localhost:8081
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
      observability:
        enabled: true

server:
  port: 8080

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Điểm quan trọng:

- `spring.application.name` giúp nhận diện service trong telemetry resources/logging.
- `spring.cloud.gateway.observability.enabled` là lựa chọn thuộc **namespace Gateway WebFlux 4.x**, không phải tên property của Spring Boot tracing. Với những release tương ứng, observability thường bật khi dependency cần thiết có mặt; ghi tường minh ở lab để nhấn mạnh cách kiểm tra.
- `management.tracing.sampling.probability: 1.0` phù hợp **lab/staging ngắn hạn**, giúp dễ nhìn thấy trace. **Production không nên để 100% mặc định** nếu chưa có capacity/cost assessment.
- `management.otlp.tracing.endpoint` của **Boot 3.5** là endpoint **HTTP OTLP traces**; ở đây giả định một Collector/receiver nhận `POST /v1/traces` tại port 4318.
- Đoạn cấu hình **không tạo Collector**. Nếu chưa chạy Collector hoặc backend, Gateway có thể vẫn phục vụ request nhưng exporter báo kết nối thất bại, không có trace để xem.
- `exposure: health,info` cố ý **không public management endpoints nhạy cảm**; xem traces ở backend riêng, không phải tại `/actuator/traces` mặc định.

### 6.3. Cấu hình backend order-service tương ứng

Ở `order-service` **Spring Boot 3.5** (có thể dùng Spring MVC) cần Actuator + Micrometer bridge + OTLP exporter tương thích, tương tự ba dependencies tracing ở trên, cộng starter web của service.

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8081

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Đừng chỉ cấu hình Gateway rồi mong backend tự tạo `SERVER span`. Nếu service không có inbound instrumentation/tracer hoặc không export, có thể Gateway vẫn gửi `traceparent` nhưng backend **không có span để kết nối**.

**Không cần cùng service name**: Gateway và order-service **phải có tên khác nhau** để trace UI thể hiện đúng hop giữa các process.

## 7. Biến thể Spring Boot 4.x / Gateway Server WebFlux 5.x

Spring Boot **4.x** thay đổi hướng đóng gói tracing. Tài liệu hiện hành giới thiệu dedicated starter **`spring-boot-starter-opentelemetry`** và nhóm property OTLP dưới `management.opentelemetry.*`.

### 7.1. Dependencies chính

~~~xml
<!-- App Gateway WebFlux theo Spring Cloud release train mới -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
</dependency>

<!-- OpenTelemetry tracing integration và exporter theo Boot 4.x -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
~~~

Các release/tổ hợp starter có thể thêm hoặc quản lý Actuator theo cách khác nhau; hãy đối chiếu dependency tree/auto-configuration thực tế và thêm `spring-boot-starter-actuator` nếu project cần các actuator endpoints/được tài liệu hướng dẫn. Không chép artifact `spring-boot-starter-opentelemetry` vào **Boot 3.5** mà không xác nhận vì đây là dependency dành cho Boot 4.x.

### 7.2. application.yml cho tuyến và OTLP

~~~yaml
spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
          observability:
            enabled: true

server:
  port: 8080

management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    otlp:
      endpoint: http://localhost:4318
~~~

Đây là **biến thể theo Boot 4.x**, không phải block thay thế từng dòng trong Boot 3.5. Tài liệu Boot 4.x nêu nhóm property `management.opentelemetry.otlp.*` có thể chỉ định endpoint chung; khi xuất **traces qua OTLP HTTP** và dùng common endpoint, exporter sẽ thêm đường dẫn signal `/v1/traces` phù hợp.

Nếu muốn cấu hình endpoint riêng cho traces, kiểm tra `management.opentelemetry.tracing.export.otlp.endpoint` theo release; đừng nhầm `management.otlp.tracing.endpoint` của Boot 3.5 với các property mới.

### 7.3. Bảng đối chiếu không nên bỏ qua

| Vấn đề | Boot 3.5 / Gateway 4.x | Boot 4.x / Gateway 5.x |
| --- | --- | --- |
| Gateway route namespace | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.routes` |
| Gateway observability setting | `spring.cloud.gateway.observability.enabled` | `spring.cloud.gateway.server.webflux.observability.enabled` |
| OpenTelemetry dependencies mẫu | Actuator + `micrometer-tracing-bridge-otel` + `opentelemetry-exporter-otlp` | `spring-boot-starter-opentelemetry` theo docs Boot 4 |
| OTLP HTTP traces setting mẫu | `management.otlp.tracing.endpoint` | `management.opentelemetry.otlp.endpoint` hoặc trace-specific property |
| Sampling | `management.tracing.sampling.probability` | `management.tracing.sampling.probability` |
| Truyền context | W3C propagator/instrumented clients | W3C propagator/instrumented clients |

Đây là **các tổ hợp minh họa**, không khẳng định cứ Gateway 4.x là Boot 3.5 duy nhất hoặc mọi minor release có cùng property. Nếu app không hiện trace, bước đầu là **đối chiếu dependency/namespace của đúng version**, không đoán lỗi trên network.

## 8. Backend demo: kiểm chứng trace ID được nhận đúng

Một backend **Spring MVC** là cách đơn giản để nhìn `Tracer.currentSpan()` trong request thread có instrumentation. Đoạn sau chỉ dành cho **mock/staging**, không tạo public endpoint tiết lộ trace metadata trong production.

~~~java
package example.orders;

import java.util.LinkedHashMap;
import java.util.Map;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersTraceDebugController {
    private final Tracer tracer;

    public OrdersTraceDebugController(Tracer tracer) {
        this.tracer = tracer;
    }

    @GetMapping("/orders/{id}")
    public Map<String, String> getOrder(
            @PathVariable("id") String id,
            @RequestHeader HttpHeaders headers) {

        Span current = tracer.currentSpan();
        Map<String, String> result = new LinkedHashMap<>();

        result.put("id", id);
        result.put("traceId",
                current != null ? current.context().traceId() : "none");
        result.put("spanId",
                current != null ? current.context().spanId() : "none");
        result.put("traceparentHeader",
                headers.getFirst("traceparent") != null ? "present" : "absent");
        return result;
    }
}
~~~

**Cách hiểu kết quả:**

- `traceId` trong response là **ID của active span ở service**; nếu có inbound parent, nó được kỳ vọng thuộc cùng trace.
- `spanId` của service thường **khác** Gateway span ID.
- Trường `traceparentHeader: present` chỉ chứng minh service thấy header; để xác nhận parent-child, cần kiểm tra **cấu trúc trace ở tracing backend**.
- `currentSpan() == null` có thể xảy ra khi tracing chưa bật, request ngoài observation scope hoặc context propagation không đúng; code kiểm tra null thay vì ném lỗi.
- Ở backend **reactive WebFlux**, current span có thể phụ thuộc Reactor Context/scope. Không copy một cách máy móc việc đọc `Tracer.currentSpan()` trong mọi callback bất đồng bộ; dùng API/hook propagation được framework hỗ trợ.

**Tuyệt đối không dùng header do client gửi để cấp quyền** chỉ vì nó mang trace ID hợp lệ. Những trường JSON trên phải được bỏ hoặc bảo vệ trong production, nhất là khi kết hợp với internal topology.

## 9. Kiểm thử HTTP propagation bằng curl

### 9.1. Không gửi traceparent: Gateway khởi tạo trace mới

Giả sử Gateway ở port 8080, order-service ở 8081, Collector ở 4318.

~~~bash
curl -i "http://localhost:8080/api/orders/42"
~~~

Một pipeline tracing đã cấu hình thường sinh root/new trace khi inbound không có context hợp lệ. Backend demo trả `traceId` và `traceparentHeader: present` nếu Gateway thực sự inject header.

Chỉ nhìn `HTTP 200` **không chứng minh tracing đang hoạt động**. Cần đọc response backend mock, header outbound do backend thấy và trace UI.

### 9.2. Gửi một W3C traceparent có kiểm soát

~~~bash
curl -i \
  -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  "http://localhost:8080/api/orders/42"
~~~

Với propagator W3C chấp nhận inbound context và sampling đã bật, trace trong backend **được kỳ vọng** dùng `traceId = 4bf92f3577b34da6a3ce929d0e0e4736`.

**Không yêu cầu outbound traceparent phải bằng chuỗi inbound**. Span ID trong outbound header cần phản ánh span cha thích hợp của backend; quan hệ parent-child nên được xác minh ở trace UI.

Các tình huống đặc biệt:

- Một hệ thống ở **trust boundary** có thể cố ý khởi tạo trace mới để không tiếp nhận context từ client không đáng tin.
- Một header malformed có thể bị bỏ qua và một trace mới được tạo.
- Một client gửi sampled bit `00` có thể không làm trace xuất hiện trong backend do sampling policy.
- Một reverse proxy/ingress có thể thay đổi hoặc loại bỏ header.
- Middleware/custom filter có thể vô tình ghi đè context trước khi Gateway routing.

### 9.3. Kiểm thử tracestate và baggage

~~~bash
curl -i \
  -H "traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01" \
  -H "tracestate: testvendor=demo" \
  -H "baggage: locale=vi" \
  "http://localhost:8080/api/orders/42"
~~~

Chỉ dùng **giá trị demo** và một environment cô lập. `baggage` có được truyền hay không phụ thuộc propagator/SDK/framework và policy. Không assert `tracestate` hoặc `baggage` phải được giữ nguyên byte-by-byte: propagators có quyền chuẩn hóa, bỏ trường không hợp lệ hoặc thay đổi vendor state.

Đừng copy token, session cookie, email/phone hay danh tính nhạy cảm vào lệnh test rồi lưu vào shell history.

### 9.4. Nếu không có Collector, vẫn test header được

Sử dụng mock HTTP upstream (WireMock, MockWebServer, một mock MVC) để ghi:

~~~text
Incoming path to mock:
  GET /orders/42

Incoming headers:
  traceparent: 00-<trace-id>-<parent-span-id>-01
~~~

Sau đó assert:

1. Gateway chọn route `orders-api`.
2. Backend nhận `traceparent` **đúng định dạng**.
3. Với client inbound W3C context hợp lệ, trace ID giữa inbound/outbound được giữ theo policy.
4. Hai request độc lập không có inbound context thường có hai trace IDs khác nhau.
5. Gateway không copy raw sensitive headers ra log khi kiểm thử.

Test header là **một lớp chứng minh propagation**; muốn thấy spans thực tế và cây latency phải kiểm tra tracer/exporter/backend.

## 10. Không tự copy traceparent bằng AddRequestHeader hoặc SetRequestHeader

Một cách cấu hình dễ sai:

~~~yaml
# PHẢN VÍ DỤ: chỉ minh họa ý tưởng sai, không đưa vào production.
filters:
  - SetRequestHeader=traceparent, 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Hậu quả:

- Tất cả requests dùng cùng trace ID/span ID giả tạo.
- Quan hệ cha-con bị sai, trace UI ghép các requests độc lập thành cùng cây.
- Sampling flags không phản ánh policy tracer.
- Một service có thể coi header là malformed hoặc tạo span không có parent chính xác.
- Security/incident investigation bị nhiễu do correlation sai.

Tương tự, việc đơn giản **sao chép nguyên `traceparent` inbound** thành outbound bỏ qua client span mới của Gateway. Tracer/HTTP instrumentation phải chịu trách nhiệm **extract → create child span → inject current context**.

### 10.1. X-Request-Id là chuyện khác

Bạn có thể có:

~~~http
X-Request-Id: req-7c6a
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

`X-Request-Id` do hệ thống định nghĩa (thường một identifier riêng), còn `traceparent` theo W3C và được tracing library quản lý. Đừng thiết kế `X-Request-Id` làm `spanId` hoặc lấy một giá trị từ HTTP header chưa xác thực rồi giả làm principal.

Nếu dùng `X-Request-Id` cho đối soát log, cần giới hạn độ dài/format, chuẩn hóa nguồn tin cậy và không coi nó là authorization.

## 11. Custom HTTP client: điểm đứt trace thường gặp nhất

### 11.1. HTTP proxy mặc định và lời gọi do code tự tạo là hai đường khác nhau

Trong Gateway, `NettyRoutingFilter`/HTTP routing infrastructure dùng HTTP client nội bộ để gửi upstream request. Gateway WebFlux có observability riêng cho HTTP client routing; cần kiểm tra nó đang bật và tạo/inject spans như mong muốn.

Nếu bạn tự viết `GlobalFilter` hoặc một bean service gọi **một HTTP endpoint phụ**, lời gọi đó là **outbound HTTP client riêng**. Đừng cho rằng vì Gateway chính có trace nên mọi `new WebClient` hoặc raw Reactor Netty client tự propagate.

### 11.2. Dùng builder được Spring Boot cấu hình

Spring Boot tài liệu tracing khuyến nghị dùng `RestClient.Builder` hoặc `WebClient.Builder` **được auto-configure** để tự động gắn observation/trace propagation.

Ví dụ một bean tạo `WebClient` phục vụ tác vụ bổ sung:

~~~java
package example.gateway.trace;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class InventoryStatusClient {
    private final WebClient client;

    public InventoryStatusClient(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("http://localhost:8082")
                .build();
    }

    public Mono<String> getAvailability(String sku) {
        return client.get()
                .uri(uriBuilder -> uriBuilder
                        .path("/inventory/{sku}")
                        .build(sku))
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

**Điểm chính:** inject builder từ Boot thay vì `WebClient.create(...)` hoặc tự dựng `WebClient.builder()` rồi bỏ qua ObservationRegistry. Với Boot version phù hợp và context đang active, outbound call qua builder được cấu hình có thể inject tracing headers.

Nhưng code này **không phải lệnh thay thế NettyRoutingFilter của Gateway**. Nó là ví dụ cho **custom outbound call**; nếu gọi nó từ filter, cần compose `Mono` trong cùng request chain, xử lý timeout/error và không tạo side effect không cần thiết.

Không dùng:

~~~java
// PHẢN VÍ DỤ: subscribe rời có thể mất lifecycle/context/error propagation.
client.get()
      .uri("/inventory/sku-42")
      .retrieve()
      .bodyToMono(String.class)
      .subscribe();
~~~

Một subscription rời có thể mất quan hệ trace context, cancellation, backpressure và error handling. Trong reactive application, hãy **return/compose publisher** qua `flatMap`, `then`, `defer` hoặc operator phù hợp.

### 11.3. Nếu dùng raw HttpClient hoặc SDK riêng

Các thư viện HTTP tự tạo, gRPC, OkHttp, Kafka producer hoặc vendor SDK **không tự được Micrometer Tracing instrument chỉ vì project có starter**. Cần:

- Integration/agent instrumentation tương ứng.
- Propagator tương thích và injection đúng protocol.
- Context scope được bảo toàn khi gọi SDK.
- Test trong đúng version/client implementation.
- Không inject trùng header khi library đã làm tự động.

**Không chỉ kiểm tra service có cùng trace ID trong response demo**; đồng thời xem HTTP client spans và parent-child ở backend tracing để phát hiện context bị reuse sai.

## 12. Reactor Context, thread switching và MDC

### 12.1. Vì sao `ThreadLocal` là bẫy trong Gateway WebFlux?

Server WebFlux dùng non-blocking Reactor pipeline. Một request có thể chuyển qua nhiều threads do `publishOn`, `subscribeOn`, callback network hoặc thư viện bên thứ ba. `ThreadLocal` gắn với một thread, còn trace context gắn với **logical execution scope/subscription**.

Vì vậy, đoạn:

~~~java
MDC.put("traceId", someId);
return chain.filter(exchange);
~~~

**không bảo đảm** mọi log của pipeline về sau luôn có cùng `traceId`. Ngoài nguy cơ mất context khi thread đổi, `MDC.put` không có scope/cleanup đúng còn có thể làm nhiễm dữ liệu giữa những requests dùng chung worker thread.

### 12.2. Reactor Context không phải HTTP header

`Reactor Context` là vùng key-value theo subscriber. Có thể dùng:

~~~java
Mono<String> readContext = Mono.deferContextual(ctx ->
        Mono.just(ctx.getOrDefault("example.routeLabel", "unknown")));

Mono<String> result = readContext
        .contextWrite(ctx -> ctx.put("example.routeLabel", "orders-api"));
~~~

Nhưng key `example.routeLabel` này **không phải W3C traceparent**, và `contextWrite` **không gửi header ra mạng**. Tracing libraries dùng integration/phạm vi context riêng để span được propagate qua reactive operators và được inject khi HTTP client gửi request.

**Không tự đọc một key có tên `traceId` trong Reactor Context rồi ghép chuỗi traceparent**. Phải dùng tracer/propagator đúng chuẩn. Khi cần route metadata cho log, có thể dùng exchange attributes, Observation conventions hoặc method arguments tường minh.

### 12.3. Micrometer Context Propagation và Reactor

Micrometer Context Propagation hỗ trợ bridge giữa **ThreadLocal-based scopes** (ví dụ tracing/MDC khi được đăng ký) và Reactor Context. Các nhánh Reactor mới có automatic context propagation support; Spring Boot/framework có thể quản lý hooks/registry theo version.

Không tự làm những việc sau mà chưa hiểu stack:

- Bật `Hooks.enableAutomaticContextPropagation()` nhiều lần ở custom filters để “sửa trace”.
- Gọi `tracer.currentSpan()` từ callback trên thread khác rồi giả định luôn có giá trị.
- Gọi `subscribe()` riêng trong `GlobalFilter` và mong tự kế thừa Context.
- `block()` trên Reactor Netty event loop để chờ span hoặc collector.
- Tạo spans mới ở mỗi retry mà không kết thúc/đóng scope đúng.
- Đặt một `Span` hoặc `ServerWebExchange` vào field singleton/static để chia sẻ cho requests khác.

Nếu log correlation mất sau scheduler hop, hãy xem **context propagation integration** và tracing bridge của Boot, không lấy một `ThreadLocal` thủ công làm giải pháp tổng quát.

### 12.4. Đọc current span để debug phải có fallback

Một hook thực thi **trong request scope được instrument** có thể thử:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;

// Đoạn code minh họa bên trong một callback có tracing scope hợp lệ.
Span current = tracer.currentSpan();
if (current != null) {
    String traceId = current.context().traceId();
    String spanId = current.context().spanId();
    // Chỉ ghi metadata cần thiết đã redact.
}
~~~

`currentSpan()` trả `null` **không đồng nghĩa chắc chắn request không được instrument**; cũng có thể code đang chạy **ngoài scope** hoặc context bridge không hoạt động tại vị trí đó.

Ở Gateway WebFlux, nên ưu tiên instrumented Observations và framework tracing thay vì mọi filter tự tạo span/viết header.

## 13. Baggage và log correlation nên được dùng thế nào?

### 13.1. Log có traceId/spanId, không dump mọi header

Ví dụ log đã làm sạch:

~~~text
2026-11-24T05:00:00Z INFO  service=edge-gateway
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=66b4a0e9139d401a routeId=orders-api
status=200 durationMs=87
~~~

Ở cùng trace, `order-service` có thể ghi:

~~~text
2026-11-24T05:00:00Z INFO  service=order-service
traceId=4bf92f3577b34da6a3ce929d0e0e4736
spanId=8f7c9b1a02f4d125 orderId=ord-42
status=200
~~~

Đây là **log format minh họa**, không phải output đã chạy. Trace ID giống nhau giúp nối log theo request, span ID khác nhau giúp phân biệt phần xử lý.

Với Spring Boot, correlation ID thường được thêm qua tích hợp Micrometer Tracing/MDC khi scope hợp lệ. Nếu tự cấu hình log pattern, cần biết tên MDC keys của version và tránh cấu hình xóa mất correlation data.

### 13.2. Baggage không tự là log field

Ví dụ cấu hình **Boot 3.5** cho một trường baggage đã review:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - locale
      correlation:
        fields:
          - locale
~~~

Đây chỉ là ví dụ. **Mỗi thuộc tính có semantics khác nhau**:

- `remote-fields` điều khiển việc truyền những baggage fields theo cơ chế mà tracer hỗ trợ; với W3C, baggage propagation có thể đã hoạt động tự động theo implementation.
- `correlation.fields` cho phép đưa các trường được chọn vào logging context khi tracing scope hiện hành.
- Không phải mọi tracer/backend có cùng cách phát baggage headers cho từng propagation format như B3 hay W3C.
- `locale` ở đây chỉ có thể là một **hint đã validate**, không phải credential hoặc security role.

**Không dùng baggage nhận từ Internet để quyết định tenant authorization hoặc rate-limit key.** Dù value nằm trong Reactor Context hay MDC, nguồn của nó vẫn có thể là header do client tự đặt.

### 13.3. Tracestate, baggage và custom span tags có phạm vi khác nhau

| Cơ chế | Phạm vi | Có thể có trong HTTP header? | Có tự vào trace backend làm tag? |
| --- | --- | --- | --- |
| `traceparent` | Identity/parent/sampling của trace | Có | ID/quan hệ span là thành phần trace |
| `tracestate` | Vendor trace propagation state | Có | Không phải arbitrary application tag |
| `baggage` | Context fields muốn propagate | Có | **Không mặc nhiên** |
| Span attribute | Metadata thuộc **một span** | Không mặc nhiên | Có nếu span được export và policy không lọc |
| MDC field | Logging scope/thread context | Không | Không, trừ khi được gắn riêng |
| HTTP `X-Request-Id` | Correlation theo API contract | Có | Không nếu không instrument riêng |

Đây là lý do không nên giải quyết “trace không có tenant” bằng cách copy mọi thông tin user từ header vào baggage hoặc span attributes.

## 14. Sampling: có propagation không có nghĩa có trace trong UI

### 14.1. Tỷ lệ sampling

Với Spring Boot, `management.tracing.sampling.probability` là tỷ lệ sampling ở root/decision tùy sampler:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
~~~

Giá trị `0.1` nghĩa là mục tiêu lấy mẫu khoảng **10%** theo policy sampler, **không phải luôn đúng một request trong từng nhóm mười requests**.

Để debug lab:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Dùng 100% sampling chỉ khi traffic nhỏ/được kiểm soát, vì:

- Số spans và dữ liệu exported tăng.
- Collector/backend tốn CPU, network, storage.
- Trace có thể chứa metadata nhạy cảm nếu không redact.
- Một trace gồm nhiều hops/retries có thể tạo nhiều spans hơn số requests client.

### 14.2. Parent-based sampling

Khi client gửi sampled flag `00`, một **parent-based sampler** có thể không export spans dù app sampling probability đang đặt cao. Ngược lại, một trace có sampled parent có thể được tiếp tục lấy mẫu tại downstream.

Do đó không suy từ “Gateway trả HTTP 200 nhưng trace UI trống” thành “traceparent không được truyền”. Nên kiểm tra:

1. Outbound `traceparent` có không?
2. Gateway/backend có tracer/extractor không?
3. Sampler/propagation type có tương thích không?
4. Exporter có hoạt động và backend index/query đúng không?

### 14.3. Quyết định sampling phải phù hợp SLO

Gợi ý vận hành:

- Traffic thấp ở staging: tạm thời 1.0 để integration test.
- Production: bắt đầu với tỷ lệ nhỏ và đo chi phí thực.
- Lỗi hiếm/latency cao: cân nhắc chính sách tail sampling ở Collector/backend nếu kiến trúc hỗ trợ.
- Trace bị drop không nên làm **request nghiệp vụ** thất bại. Giám sát dropped spans/export failures riêng.
- Nếu dùng tail sampling, Collector phải nhận đủ spans liên quan trong cùng trace; cấu hình collector fan-out cần cân nhắc routing theo trace ID.

**Không coi trace sampling là rate limiting request nghiệp vụ.** Hai cơ chế giải quyết mục tiêu khác nhau.

## 15. B3 và W3C: không phải mọi service cùng một định dạng

Một hệ thống cũ dùng **B3** có thể gửi `b3` hoặc `X-B3-TraceId`, `X-B3-SpanId`. Hệ thống mới thường dùng **W3C `traceparent`/`tracestate`**.

Tài liệu Spring Boot 3.x hỗ trợ cấu hình propagation format (ví dụ `management.tracing.propagation.type` hoặc `consume`/`produce` tùy release):

~~~yaml
# Ví dụ chủ đích chọn W3C khi tất cả dịch vụ đã tương thích.
management:
  tracing:
    propagation:
      type: w3c
~~~

**Không bật nhiều formats rồi cho rằng mọi client/backend tự xử lý như nhau.** Một service chỉ nhận B3 và Gateway chỉ phát W3C có thể tạo **trace mới** ở downstream dù HTTP request vẫn thành công.

Với migration từ B3 sang W3C:

1. Kiểm kê format từng service/SDK/sidecar.
2. Nếu cần chuyển tiếp tạm thời, cấu hình **consume/produce** được version hỗ trợ.
3. Kiểm thử đúng `traceId` và parent relationships ở từng hop.
4. Tránh các headers B3 và W3C **mâu thuẫn** trong cùng request không có policy ưu tiên.
5. Không tự ghép header ID giữa hai formats bằng custom regex.
6. Khi đã hội tụ, thu hẹp format để giảm ambiguity và chi phí xử lý.

Nếu dùng B3, chính sách baggage có thể khác W3C; không mặc định một header `baggage` sẽ được backend B3 đọc.

## 16. Tracing trong retry, circuit breaker, load balancer và lỗi mạng

### 16.1. Retry có thể tạo nhiều upstream attempts trong một trace

~~~mermaid
flowchart TD
    C["Client GET"] --> G["Gateway inbound span"]
    G --> R["Retry policy"]
    R --> A1["Attempt 1 → order-1 → 503"]
    R --> A2["Attempt 2 → order-2 → 200"]
    A1 --> T["Trace backend"]
    A2 --> T
    G --> T
~~~

Một request client có thể đi qua hai HTTP attempts. **Cách tracer thể hiện spans có thể khác theo placement của Retry filter và HTTP client observation**: có release tạo một client span cho từng attempt, có cấu hình không cho bạn nhìn được mọi attempt từ default spans.

Vì vậy, kết hợp:

- Trace quan hệ Gateway → backend.
- Metric **upstream attempts** theo route/exception.
- Log route ID, retry count, selected instance nếu được hỗ trợ.
- Request latency và backoff time.
- Không dùng chỉ số spans để suy chính xác số retries trong mọi implementation.

**Không tự retry thao tác ghi như POST thanh toán chỉ vì tracing cho thấy 503/504**. Timeout không chứng minh backend chưa commit; cần idempotency key/dedup và recovery.

### 16.2. Circuit breaker và fallback

Nếu circuit breaker trả fallback tại Gateway, client có thể thấy 200/503 mà **không có upstream order-service span** trong lần request đó. Đây có thể là hành vi đúng.

Khi điều tra, kiểm tra cả breaker state, fallback handler và route filters; đừng quy mọi thiếu downstream span cho propagation lỗi.

### 16.3. Load balancer và service discovery

Route `lb://ORDER-SERVICE` chọn instance theo discovery/load balancer khi có cấu hình. Trace thường cho thấy một client span ở Gateway và server span tại instance nhận request. **Trace context không chọn instance** và cũng không thay service discovery.

Nếu chọn instance lỗi, trace giúp thấy kết nối/response, còn metrics/logs/tracing metadata phải được dùng cùng nhau để tìm nguyên nhân.

### 16.4. 502/503/504 có thể xuất hiện trước khi tạo backend span

Một số trường hợp:

| Lỗi | Span có thể quan sát | Lưu ý |
| --- | --- | --- |
| Không khớp route | Gateway inbound span, không có downstream client span | Có thể là Gateway 404 |
| DNS/connect refused | Gateway HTTP client observation/error; không có backend server span | Request có thể chưa đến service |
| TLS handshake fail | Gateway/client error, backend app chưa nhận HTTP | Kiểm tra truststore/certificate |
| Timeout sau backend commit | Gateway/client timeout, backend có thể vẫn ghi và có span | Không tự phát lại POST |
| Circuit breaker short-circuit | Gateway span/fallback, không có backend attempt | Cần xem breaker metrics |
| Backend trả 503 | Gateway outbound + backend server spans nếu đã instrument | Có thể bị retry |
| Sampling drop | Headers có thể vẫn hiện, spans không vào UI | Không kết luận request chưa tới backend |

## 17. HTTP headers và trust boundary: phải kiểm soát dữ liệu tracing

### 17.1. Traceparent là dữ liệu do người gửi cung cấp

Client hoặc đối tác ngoài Internet có thể tự đặt:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Header đúng cú pháp **không chứng minh danh tính** và không bảo đảm client có quyền truy cập một order. Kẻ tấn công cũng có thể cố tạo trace ID trùng/giống định dạng để nhiễu log hoặc tăng số lượng contexts.

Ở ranh giới public API, cân nhắc:

- Dùng propagator chuẩn để validate/normalize; bỏ context malformed.
- Có policy rõ **tin/không tin inbound trace context** từ nguồn ngoài.
- Khi cần tách miền tin cậy, có thể **tạo trace mới** hoặc link sang incoming context thay vì coi nó là parent hợp lệ.
- Không dùng sampled bit từ client làm quyền override ngân sách tracing một cách vô hạn.
- Giới hạn kích thước header/tracestate/baggage, chống request header abuse.
- Không chuyển baggage untrusted sang các đối tác nếu không có hợp đồng.

### 17.2. Header propagation không được vô tình làm lộ secret

Không tạo span attributes hoặc log chứa:

- `Authorization: Bearer <token>`, `Cookie`, `Set-Cookie`.
- Password, private key, API keys, refresh token.
- Số thẻ/thông tin thanh toán, PII, raw request body.
- Query string có token hoặc email chưa được redact.
- Baggage chứa user identity nhạy cảm.
- Raw URI dynamic có dữ liệu khách hàng.

Một trace backend thường có quyền truy vấn rộng và retention khác database nghiệp vụ. Dữ liệu nhạy cảm vô tình đưa vào span có thể được nhân bản sang exporter, Collector, storage và UI.

### 17.3. Route ID là nhãn hợp lý, raw path có thể không

Ví dụ route cố định `orders-api` thường có cardinality thấp. Nhưng gắn raw path `/api/orders/42`, `/api/orders/43`, ... hoặc trace ID vào metric labels tạo số series tăng gần bằng traffic.

Theo hướng dẫn Gateway metrics, path tag thường **không được bật mặc định** để hạn chế cardinality. Với span tags, raw URI vẫn có thể là high-cardinality metadata; áp dụng filtering/redaction theo chính sách. Khi đặt tags, ưu tiên route template `/api/orders/{id}` thay vì raw ID nếu instrumentation hỗ trợ.

### 17.4. Observability không thay thế security

Dù Gateway và order-service có cùng `traceId`, backend vẫn cần xác thực principal, kiểm tra tenant/ownership và authorization cho resource. Không tin baggage `tenant=acme` hoặc `role=admin` do client gửi, kể cả khi nó xuất hiện ở Reactor Context của Gateway.

## 18. Observability của Gateway: metrics và traces phải được phân biệt

Spring Cloud Gateway Server WebFlux có các observation/metrics cụ thể:

| Loại | Ví dụ tên | Mục đích |
| --- | --- | --- |
| HTTP server observation | `http.server.requests` khi tích hợp Spring Boot phù hợp | Latency/status inbound Gateway |
| Gateway HTTP client observation | `http.client.requests` theo metadata Gateway | Thời gian outbound HTTP routing |
| Gateway request metrics filter | `spring.cloud.gateway.requests` trong tài liệu nhánh mới | Route-level timer theo status, outcome, route ID |
| Custom retry/route metrics | Tên do project tự định nghĩa | Upstream attempts, breaker, fallback |
| Distributed tracing spans | SERVER/CLIENT spans | Cây xử lý liên dịch vụ |

**Không đánh đồng “có Prometheus metrics” với “có trace”.** `micrometer-registry-prometheus` xuất metrics, còn traces cần tracing bridge/tracer và exporter/backend.

Một ví dụ dành cho nhánh Gateway WebFlux mới:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          observability:
            enabled: true
          metrics:
            enabled: true
            path-tags:
              enabled: false
~~~

Đây là cấu hình **về observability/metrics**. Nó không tự cấu hình OTLP span exporter, không phải cách tạo W3C traceparent một cách thủ công, và tên properties khác nhau ở nhánh Gateway 4.x.

### 18.1. Vì sao không xem metric route ID là span ID?

`routeId=orders-api` là nhãn ổn định của route, xuất hiện trên nhiều requests. `spanId` là định danh **một đơn vị xử lý** của một trace. Nếu dùng route ID thay span ID, mọi request qua cùng route bị nhập nhằng.

### 18.2. Trace UI có thể đến muộn

Collector thường batch/export. Sau `curl`, bạn có thể cần đợi backend index/truy vấn cập nhật, nhưng **không dùng một khoảng đợi cố định như bằng chứng hệ thống luôn có latency đó**. Trong test có thể dùng polling có timeout rõ và assert trace eventually appears, không chạy polling vô hạn.

## 19. Kiểm thử tích hợp ba process: client, Gateway, backend

### 19.1. Chuẩn bị lab

Giả định:

- **Gateway WebFlux**: `localhost:8080`, route `orders-api`.
- **order-service**: `localhost:8081`, có tracing deps và controller demo.
- **OTLP Collector**: nhận HTTP ở `localhost:4318/v1/traces`.
- **Trace backend**: Jaeger/Tempo/Zipkin qua exporter/Collector tương ứng, có UI hoặc query API.
- Sampling đặt `1.0` trên môi trường lab khi muốn xem tất cả requests, trừ khi kiểm thử parent-based sampling riêng.
- Có thể sử dụng mock HTTP server thay order-service ở ca chỉ kiểm header.

Lưu ý **cùng endpoint OTLP không đồng nghĩa cùng service**: `spring.application.name` phải được đặt khác nhau trên Gateway/backend.

### 19.2. Các assertion quan trọng

1. Client gửi GET `/api/orders/42`.
2. Gateway chọn đúng route và StripPrefix khiến backend nhận `/orders/42`.
3. Backend nhận **`traceparent` có cấu trúc W3C hợp lệ**.
4. Backend có `traceId` thuộc cùng trace mà Gateway export.
5. Gateway và backend có **span IDs khác nhau** và quan hệ parent-child hợp lý.
6. Trace UI hiển thị service names đúng, timing spans và HTTP status.
7. Request không có incoming `traceparent` vẫn tạo trace mới theo policy.
8. Request có traceparent hợp lệ được join/carry cùng trace ID nếu policy cho phép.
9. Nếu bật sampling thấp, không dùng sự vắng mặt ở UI để khẳng định header bị mất.
10. 401/403/404 có thể bị chặn **trước khi route Gateway chạy**; không luôn mong có outbound client span.

### 19.3. Pseudocode kiểm thử header ở mock upstream

~~~text
Given:
  Gateway has tracing enabled and W3C propagation.
  Mock upstream records HTTP headers.

When:
  GET /api/orders/42
  traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

Then:
  mock receives GET /orders/42
  mock has traceparent header
  outbound trace-id equals 4bf92f3577b34da6a3ce929d0e0e4736
  outbound parent-id is valid and not all zeros
  gateway response follows mock contract
~~~

Đây là **pseudocode**, chưa phải test class chạy độc lập. Nếu không có W3C extraction do misconfiguration, expected trace ID continuity phải fail để phát hiện lỗi. Nếu production cố tình tái tạo trace tại public boundary, sửa acceptance criteria theo policy đó.

### 19.4. Tracing trong @SpringBootTest cần cấu hình rõ

Tài liệu Spring Boot lưu ý **các tracing reporting components có thể không được auto-configure trong `@SpringBootTest` theo mặc định**, để tránh test vô tình gửi spans ra backend. Vì vậy:

- Unit test mapping/filter có thể chạy **không exporter**.
- Integration test propagation thật cần bật đúng auto-configuration/test observation/tracing theo version, hoặc chạy app qua embedded server/full integration environment.
- MockMvc test của backend và HTTP integration test của Gateway không luôn tạo cùng loại spans; giải thích expected context.
- Không dựa vào `@SpringBootTest` có status 200 để kết luận OTLP exporter đã làm việc.
- Không đặt token của observability backend vào test source control.

## 20. Ma trận tình huống phải thử

| Ca | Thao tác | Kết quả cần kiểm chứng |
| --- | --- | --- |
| T1 | Client GET không traceparent | Gateway tạo trace theo policy, backend nhận context nếu instrumentation bật |
| T2 | Client GET có W3C traceparent hợp lệ | Trace ID tiếp nối qua Gateway/backend khi trust policy cho phép |
| T3 | Inbound traceparent malformed | Không crash; tạo context khác hoặc reject theo chính sách |
| T4 | Inbound sampled bit `00` | Hành vi sampling và propagation đúng, không nhầm missing UI |
| T5 | Backend không có tracing dependencies | Header có thể đến nhưng không có backend server span được export |
| T6 | Gateway không có OTLP exporter | Client routing vẫn chạy; Collector không có Gateway spans |
| T7 | Collector offline | Gateway không được phụ thuộc availability collector để trả 200 nghiệp vụ |
| T8 | Custom WebClient xây ngoài Boot builder | Test phát hiện context propagation thiếu |
| T9 | Custom WebClient dùng Boot-injected builder | Header propagation hoạt động trong reactive context phù hợp |
| T10 | Gateway filter gọi `subscribe()` rời | Phát hiện trace bị tách/lỗi lifecycle |
| T11 | `publishOn` thay scheduler | Trace scope/MDC còn đúng khi context propagation được cấu hình |
| T12 | Proxy/ingress xóa `traceparent` | Backend mở trace mới; phát hiện qua header/trace tree |
| T13 | W3C phía Gateway, backend chỉ B3 | Trace ID có thể bị đứt; cần format migration |
| T14 | Retry GET 503 rồi 200 | Trace và attempt metrics thể hiện được hai lần gọi theo policy |
| T15 | Circuit breaker short-circuit | Không bắt buộc xuất hiện upstream server span |
| T16 | Rate limiter trả 429 trước routing | Không bắt buộc có downstream span |
| T17 | Gateway route `lb://` không có instance | Có Gateway error, không có backend server span |
| T18 | Baggage chứa giá trị user tự đặt | Không được dùng như authentication/tenant permission |
| T19 | Một request chứa nhiều span events | Không log raw token, query chứa PII |
| T20 | Enable raw path metric tags | Cardinality được phát hiện/giới hạn |
| T21 | Backend service name trùng Gateway | UI khó phân biệt; sửa resource/service name |
| T22 | HTTP 200 nhưng trace UI trống | Kiểm sampling/exporter/Collector và backend query |

## 21. Chẩn đoán lỗi khi trace bị đứt

| Hiện tượng | Nguyên nhân thường gặp | Hướng khắc phục |
| --- | --- | --- |
| Không có trace nào trong UI | Thiếu exporter, Collector sai endpoint, sampling thấp | Kiểm dependencies, OTLP URL, exporter logs, sampler |
| Chỉ có span của Gateway | Backend chưa instrument hoặc không export | Kiểm backend Actuator/tracing deps |
| Backend có trace ID khác Gateway | Header không được inject/extract; propagation format khác | Kiểm outbound traceparent, W3C/B3 compatibility |
| Có header traceparent nhưng backend không có span | Thiếu server instrumentation hoặc backend sampling/export lỗi | Kiểm inbound tracing và Collector |
| Traceparent outbound y hệt inbound mọi request | Filter copy thủ công thay propagator | Bỏ SetRequestHeader/copy tay, bật instrumentation |
| Trace ID trong log mất sau async boundary | Context propagation/MDC bridge thiếu | Dùng framework integration, tránh ThreadLocal thủ công |
| Trace ID xuất hiện ở request khác | Tracer/span giữ trong singleton/static/threadlocal không cleanup | Sửa scope, không chia sẻ request state |
| W3C ở Gateway nhưng B3 ở service cũ | Không cùng propagation format | Cấu hình consume/produce theo version |
| Trace không xuất hiện sau test với sampled=00 | Parent sampler giữ unsampled | Test sampled=01 và lab sampler 1.0 |
| Retry tăng latency nhưng trace chỉ có một upstream span | Placement/observation không quan sát từng attempt | Đo retry attempts qua metrics/logs riêng |
| 429 không có downstream span | Rate limiter chặn trước HTTP routing | Xem Gateway policy trước |
| 504 mà backend trace có status thành công | Timeout sau backend đã commit | Không tự retry write, dùng idempotency/reconciliation |
| Collector báo 404 | Nhầm `/v1/traces` hoặc port OTLP HTTP/gRPC | Kiểm exporter protocol và endpoint |
| Boot 4 config OTLP theo Boot 3.5 bị bỏ qua | Property namespace thay đổi | Dùng nhóm `management.opentelemetry.*` phù hợp |
| Route WebFlux 5.x không load | Dùng `spring.cloud.gateway.routes` sai version | Kiểm prefix và effective routes |
| Tracing được bật nhưng metrics không có | Registry/export khác nhau | Kiểm Micrometer metrics dependency/exposure |
| Log quá nhiều thông tin | Dump headers/baggage/raw URL | Redact và giới hạn attribute |
| Trace spans không có route ID | Observation convention/route match khác | Kiểm Gateway outbound observation/version |

### Quy trình debug có thứ tự

1. **Route đúng chưa?** Path/Method/StripPrefix, URI, service discovery và response status.
2. **Gateway có instrumentation chưa?** Actuator/tracer/observation và đúng properties theo phiên bản.
3. **Outbound có traceparent chưa?** Bắt header bằng mock upstream, tránh log vào production.
4. **Backend có đọc/tiếp nối trace không?** Xác minh trace ID/scope và backend tracing deps.
5. **Sampling có làm mất spans?** Kiểm sampled flag và sampler policy.
6. **Exporter/Collector hoạt động không?** OTLP protocol, host, path, TLS/auth, queue/drops.
7. **Có Reactor Context/thread hop bị mất?** Custom client/filter, `subscribe()` độc lập, MDC bridge.
8. **Có proxy/mesh sửa header không?** Ingress, firewall, sidecar, HTTP/2 gateway.
9. **Trace backend đang query đúng service/interval chưa?** Batching, retention, clock skew.
10. **Dữ liệu có an toàn không?** Kiểm baggage/attributes/URL/log PII trước khi mở rộng sampling.

## 22. Bài thực hành tổng hợp: theo dấu request từ Gateway đến order-service

**Bối cảnh:** Một Gateway nhận `GET /api/orders/42`, sau đó proxy đến `order-service`. Order service có thể gọi thêm một `inventory-service`.

### Yêu cầu

1. Chọn **một** tổ hợp phiên bản được hỗ trợ: Boot 3.5 + Gateway WebFlux 4.x hoặc Boot 4.x + Gateway WebFlux 5.x.
2. Cấu hình `spring.application.name=edge-gateway` và `order-service` khác tên.
3. Bật Actuator, Micrometer Tracing và exporter OTLP bằng dependency/property **đúng version**.
4. Khởi động một OTLP Collector/trace backend có thể nhận spans; xác minh endpoint HTTP 4318 nếu sử dụng OTLP HTTP.
5. Tạo route `orders-api`, `Path=/api/orders/**`, `StripPrefix=1`.
6. Tạo backend mock hoặc controller demo trả ID và `traceId`.
7. Đặt sampling 1.0 **trong môi trường test**.
8. Gửi curl không có `traceparent`, xác nhận backend thấy header outbound và có trace ID.
9. Gửi curl có W3C `traceparent` hợp lệ, xác nhận trace ID được giữ theo trust policy.
10. Truy vấn trace UI, xác nhận Gateway và backend spans nằm trong cùng cây với service names đúng.
11. Thêm một outbound `WebClient` call bằng injected `WebClient.Builder`; test span/context được propagate.
12. Thử tắt tracing ở backend và quan sát trace bị đứt.
13. Thử một request bị 401/429 ở Gateway; giải thích vì sao không có backend span.
14. Thử retry GET và so sánh số upstream attempts với số client requests.
15. Bật sampling thấp rồi chỉ ra rằng một request thành công có thể không xuất hiện trong trace UI.
16. Dùng một `baggage: locale=vi` đã validate, kiểm tra policy truyền context, không dùng baggage làm quyền.
17. Kiểm tra log correlation, không lộ `Authorization`, cookie, ID cá nhân hoặc request body.
18. Viết báo cáo một request: route ID, trace ID, spans ở từng service, thời gian chậm nhất, status và cách tái hiện.

### Tiêu chí hoàn thành

~~~text
[PASS] Gateway route khớp và upstream nhận đúng path
[PASS] W3C traceparent outbound hiện diện khi instrumentation bật
[PASS] Trace ID được nối liền theo chính sách propagate đã chọn
[PASS] Gateway và order-service có span IDs riêng
[PASS] Trace backend hiển thị cấu trúc parent-child có ý nghĩa
[PASS] Log có correlation IDs khi scope hợp lệ, không lộ dữ liệu nhạy cảm
[PASS] Lỗi exporter/sampling được phân biệt với lỗi routing
[PASS] Retry/fallback được phân biệt trong tracing và request metrics
[PASS] Không copy thủ công traceparent bằng SetRequestHeader
[PASS] Test ngăn baggage bị dùng như credential/authorization
~~~

Đây là **tiêu chí dự kiến**, không phải kết quả đã chạy một môi trường thật.

## 23. Checklist production

- [ ] Gateway/backend đều có tracer/instrumentation hợp lệ, không chỉ Actuator metrics.
- [ ] Đã chọn đúng tổ hợp Spring Boot, Spring Cloud Gateway và exporter dependencies.
- [ ] `spring.application.name`/service identity phân biệt mỗi process/service.
- [ ] Gateway routing WebFlux và HTTP outbound client có observation/trace propagation.
- [ ] Các custom `WebClient`/`RestClient` được dựng từ auto-configured builders hoặc instrumented đúng.
- [ ] Các HTTP SDK/gRPC/message broker có propagation riêng nếu dùng.
- [ ] W3C/B3 formats và consume/produce policy tương thích qua toàn đường đi.
- [ ] Không tự `SetRequestHeader`/copy raw `traceparent` khi instrumentation đã quản lý.
- [ ] Gateway giữ context hợp lệ qua Reactor asynchronous chain và scheduler hops.
- [ ] Không `block()` trong Netty event loop, không `subscribe()` rời trong filter.
- [ ] Không lưu span/trace context theo request vào biến singleton/static/ThreadLocal không cleanup.
- [ ] Trace context từ client không được dùng làm authentication hoặc tenant authorization.
- [ ] Baggage/tracestate có chính sách allowlist, size limit, redaction và trust boundary.
- [ ] Sampling/budget ở production theo traffic và chi phí; không giữ 1.0 vô hạn.
- [ ] Collector/exporter có TLS/auth, timeout, queue/drop monitoring, HA và retention.
- [ ] Lỗi Collector không làm request nghiệp vụ fail theo cách không chủ đích.
- [ ] Log correlation có traceId/spanId khi phù hợp; không dump raw token/cookie/PII.
- [ ] Span attributes/metrics không chứa raw user IDs, dynamic paths hoặc query secrets.
- [ ] Route ID và service name ổn định, tránh metric label cardinality cao.
- [ ] Quan sát retry attempts, circuit breaker, rate limiting và timeout cùng traces.
- [ ] Integration test qua từng Gateway replica và backend instrumented có parent-child đúng.
- [ ] Có kế hoạch migration W3C/B3 và kiểm thử khi nâng Spring Boot/Cloud.
- [ ] Đã phân biệt tracing với metrics/health và kiểm chứng backend UI không chỉ HTTP status.

## 24. Tổng kết và tài liệu tham khảo

**Distributed tracing** giúp nhìn thấy một request đi qua Gateway, microservices và những cuộc gọi tiếp theo. **Trace ID** liên kết toàn bộ trace; **span ID** phân biệt từng phần việc. Khi request đi qua HTTP, propagator dùng **W3C `traceparent`/`tracestate`** để truyền trace context; **baggage** là luồng key-value riêng, không phải bằng chứng xác thực.

Với **Spring Cloud Gateway Server WebFlux**, tracing tốt cần:

1. Micrometer Observation/Tracing cùng tracer/exporter tương thích.
2. Inbound HTTP server và outbound Gateway HTTP client có instrumentation.
3. Backend cũng extract header, tạo spans và export khi được sample.
4. Reactor Context/context propagation được bảo toàn qua pipeline không chặn.
5. OTLP Collector/trace backend vận hành đúng protocol, endpoint, retention.
6. Sampling, log correlation và security/redaction có chủ đích.

**Không tự thêm/copy `traceparent` như một header cố định** và không xem HTTP 200 hay `traceparent` hiện diện là đủ: hãy kiểm tra **trace ID continuity, parent-child spans, backend logs và exporter**. Kết hợp metrics, logs và traces sẽ giúp phân biệt route lỗi, upstream timeout, retries, circuit breaker và những thay đổi gây suy giảm hiệu năng mà không đánh đổi tính an toàn của dữ liệu.

### Tài liệu tham khảo chính thức

- [W3C Trace Context — traceparent và tracestate](https://www.w3.org/TR/trace-context/).
- [W3C Baggage](https://www.w3.org/TR/baggage/).
- [Spring Boot 3.5 — Tracing và OTLP](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html).
- [Spring Boot hiện hành — Tracing, OpenTelemetry starter và Propagating Traces](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot hiện hành — Observability và OTLP configuration](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [Spring Cloud Gateway Server WebFlux — Global Filters và Gateway Metrics Filter](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/global-filters.html).
- [Spring Cloud Gateway — Configuration Properties và observability settings](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html).
- [Spring Cloud Gateway — Observability metadata của Gateway HTTP Client Observation](https://docs.spring.io/spring-cloud-gateway/reference/appendix.html).
- [Micrometer Tracing — Context Propagation](https://docs.micrometer.io/tracing/reference/configuring.html).
- [Project Reactor — Context và Context Propagation](https://projectreactor.io/docs/core/release/reference/advanced-contextPropagation.html).

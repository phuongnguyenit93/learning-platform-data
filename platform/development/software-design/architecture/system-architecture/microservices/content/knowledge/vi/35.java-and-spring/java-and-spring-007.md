# Truyền ngữ cảnh quan sát và đo chỉ số theo dịch vụ

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Java và Spring. Tài liệu hướng dẫn truyền ngữ cảnh quan sát (observability context) xuyên suốt một request hoặc message qua nhiều microservice Java/Spring, liên kết trace, log và metric, đồng thời thiết kế chỉ số theo từng service để đo độ tin cậy, hiệu năng và tác động tới người dùng. Trọng tâm là W3C Trace Context, OpenTelemetry, Micrometer Observation/Tracing, MDC, HTTP, Kafka/RabbitMQ, asynchronous execution, metric cardinality, histogram, SLI/SLO, bảo mật và kiểm thử propagation.

## 1. Vì sao cần truyền ngữ cảnh quan sát?

Một thao tác người dùng thường đi qua nhiều tiến trình:

~~~text
Browser
   |
   v
API Gateway
   |
   v
Order Service
   |             \
   v              v
Inventory       Pricing
   |              |
   +-------> Order DB
                  |
                  v
              Outbox
                  |
                  v
                Kafka
                  |
             +----+----+
             v         v
        Notification  Fulfillment
~~~

Khi người dùng báo “đặt hàng chậm”, mỗi service có thể có log và dashboard riêng. Nếu không có cách liên kết các hoạt động, kỹ sư phải tìm theo timestamp, endpoint và message text; đồng hồ giữa máy có thể lệch, nhiều request xảy ra đồng thời và cùng một lỗi có thể sinh hàng trăm log giống nhau.

**Observability context** là tập thông tin giúp nối các hoạt động có liên quan thành một câu chuyện có thể truy vết. Các trường quan trọng thường gồm:

- `trace_id`: định danh một trace xuyên qua các service.
- `span_id`: định danh một hoạt động cụ thể trong trace.
- `parent_span_id`: quan hệ cha của span, nếu có.
- `trace_flags` và `tracestate`: thông tin điều khiển/nhà cung cấp theo chuẩn trace context.
- `baggage`: các thuộc tính được truyền theo context khi có nhu cầu rõ ràng.
- `correlation_id` hoặc `request_id`: mã tương quan nghiệp vụ/ứng dụng theo contract riêng.
- `service.name`, `service.version`, `deployment.environment`: danh tính runtime.
- `tenant`, `region`, `route`, `operation`: các chiều phân tích có kiểm soát.

Ngữ cảnh giúp trả lời ba câu hỏi:

1. **Request này đã đi qua đâu?** Trace và span cho thấy quan hệ giữa gateway, service, database và message.
2. **Điều gì đã xảy ra tại mỗi bước?** Log chứa trace/span identifiers và event có ý nghĩa.
3. **Vấn đề có phổ biến không?** Metrics tổng hợp theo service, route, outcome và dependency cho biết tần suất, độ trễ, saturation và SLO.

Không đưa mọi dữ liệu vào một loại telemetry. Trace cho biết đường đi của một request; log ghi sự kiện cụ thể; metric cho biết xu hướng tổng thể và là nguồn tốt cho alert. Chúng bổ trợ nhau.

## 2. Phân biệt trace context, correlation ID và business context

Các khái niệm thường bị dùng lẫn:

| Loại | Mục đích | Ví dụ | Vòng đời |
| --- | --- | --- | --- |
| Trace context | Nối các span của một execution path | trace ID, span ID, trace flags | Một trace hoặc nhánh công việc |
| Correlation ID | Liên kết các request/event cùng một workflow theo quy ước ứng dụng | `checkout-flow-123` | Có thể kéo dài qua nhiều trace |
| Request ID | Nhận diện một request cụ thể ở một boundary | `req-789` | Một request |
| Business ID | Tham chiếu đối tượng nghiệp vụ | `order-456` | Theo vòng đời order |
| Baggage | Truyền thuộc tính context giữa các process | `tenant-tier=gold` | Theo propagation policy |
| User/session context | Thông tin chủ thể của request | user/session reference | Theo security/session policy |

Một workflow kéo dài nhiều phút hoặc nhiều giờ có thể tạo nhiều trace riêng: request tạo đơn, event xử lý thanh toán, callback provider và reconciliation. Khi đó `correlation_id` hoặc `order_id` có thể liên kết các trace trong phạm vi được phép; không cần giữ một trace mở suốt toàn bộ workflow.

**Không dùng trace ID làm business ID.** Trace có thể bị sampling, thay đổi khi tạo một async root trace mới hoặc không tồn tại ở mọi hệ thống. Business ID có semantics nghiệp vụ và chính sách truy cập riêng.

**Không dùng correlation ID làm bằng chứng xác thực.** Người gửi có thể tự cung cấp một giá trị correlation; nó chỉ dùng để nối hoạt động, không cấp quyền đọc dữ liệu.

## 3. Mô hình trace: trace, span, parent và link

Một trace là đồ thị các span mô tả những hoạt động có liên quan. Với request đồng bộ, quan hệ thường là cây cha-con:

~~~text
Trace: 4bf92f...
|
+-- SERVER span: API Gateway
    |
    +-- CLIENT span: Order HTTP call
        |
        +-- SERVER span: Order Service
            |
            +-- CLIENT span: Inventory
            |    +-- SERVER span: Inventory
            |
            +-- CLIENT span: Pricing
            |    +-- SERVER span: Pricing
            |
            +-- CLIENT span: PostgreSQL query
~~~

Một span nên có:
- Tên mô tả operation, không chứa ID động.
- Start/end timestamp.
- Span kind: INTERNAL, SERVER, CLIENT, PRODUCER hoặc CONSUMER.
- Parent hoặc span links khi phù hợp.
- Attributes có cardinality và privacy được kiểm soát.
- Events cho mốc quan trọng.
- Status/error information phù hợp.

Không tạo một span cho mọi dòng code hoặc getter. Span quá nhỏ làm trace nặng, query khó đọc và tốn storage. Instrument các boundary có ý nghĩa: inbound/outbound HTTP, database, broker, scheduled job, business operation quan trọng.

### 3.1. Parent-child và span links

HTTP call đồng bộ thường tạo span client làm cha của server span phía nhận thông qua propagated context. Message processing có thể xảy ra sau khi producer đã kết thúc; tùy semantics, consumer có thể tiếp tục parent context hoặc dùng **span link** để thể hiện quan hệ tới một hay nhiều message/trace trước đó.

Span link hữu ích khi:
- Một batch consumer xử lý nhiều message từ nhiều trace.
- Một job gom dữ liệu từ nhiều workflow.
- Một async operation được kích hoạt bởi nhiều nguyên nhân.
- Consumer xử lý lại message sau thời gian dài hoặc từ DLQ.

Không ép mọi hoạt động bất đồng bộ thành một cây cha-con giả tạo. Quan hệ cần phản ánh causality thực.

## 4. W3C Trace Context: traceparent và tracestate

W3C Trace Context chuẩn hóa cách truyền context qua HTTP và các hệ thống tương thích.

Header `traceparent` có dạng khái quát:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Các thành phần:
- Version: `00` trong ví dụ.
- Trace ID: 32 ký tự hex, không phải toàn số 0.
- Parent ID: 16 ký tự hex, không phải toàn số 0.
- Trace flags: byte thể hiện các cờ, ví dụ sampled bit.

`tracestate` có thể mang state riêng của tracing vendor theo format chuẩn:

~~~http
tracestate: vendor1=value1,vendor2=value2
~~~

Quy tắc quan trọng:
- Dùng instrumentation/library chuẩn để inject và extract; không tự parse/ghép header bằng string thủ công.
- Validate context đầu vào và tuân theo version/format của chuẩn.
- Không tin trace context từ client như một danh tính hoặc quyền.
- Không để header do người dùng kiểm soát làm tăng không giới hạn kích thước hoặc cardinality.
- Xem xét trust boundary: có thể tiếp tục trace nội bộ nhưng cần quyết định có chấp nhận parent context từ public internet hay tạo trace mới và link lại.
- Giữ propagation nhất quán qua proxy/gateway và các service.

Trace flags là thông tin kỹ thuật, không phải SLO hoặc mức độ tin cậy của request. Sampling decision có thể được điều chỉnh bởi policy nội bộ; đừng coi `sampled=1` là bảo đảm trace chắc chắn được lưu ở mọi backend.

## 5. Baggage: truyền ít, có chủ đích

Baggage là các key/value được truyền cùng context giữa các service. Ví dụ:

~~~http
baggage: tenant-tier=gold,region=ap-southeast
~~~

Baggage có thể hỗ trợ:
- Phân biệt tenant tier để phân tích latency.
- Gắn experiment cohort đã được phép.
- Chuyển một mã workflow không nhạy cảm.
- Truyền một số thuộc tính routing/diagnostic có giới hạn.

Nhưng baggage có thể bị sao chép qua nhiều boundary, log hoặc trace. Do đó:

- Không truyền access token, cookie, email, số điện thoại, số thẻ, password hoặc PII.
- Không đưa payload lớn, danh sách ID hay dữ liệu tùy ý vào baggage.
- Đặt allowlist key, giới hạn kích thước và TTL/lifecycle.
- Xác minh nguồn và loại bỏ key không được phép tại ingress.
- Không dùng baggage thay cho auth claims hoặc tenant authorization.
- Tránh đưa giá trị high-cardinality vào metric labels dù chúng có mặt trong context.
- Chỉ propagate tới downstream cần thông tin đó; không phát tán mọi thuộc tính tới mọi vendor.

Nếu cần phân tích tenant, cân nhắc dùng tier/segment đã giới hạn số giá trị thay vì tenant ID cụ thể. Nếu cần điều tra một tenant, dùng log/trace có access control hoặc truy vấn chuyên biệt.

## 6. OpenTelemetry và Micrometer trong hệ Java/Spring

Có hai hệ sinh thái thường gặp:

- **OpenTelemetry (OTel):** API/SDK và semantic conventions độc lập vendor để tạo, propagate và export traces/metrics/logs.
- **Micrometer:** facade/observation và metrics ecosystem phổ biến trong Spring; Micrometer Observation có thể tạo observation, metrics và tracing bridge tùy cấu hình.

Trong Spring Boot, có thể chọn:
1. Spring Boot Actuator + Micrometer Observation/Tracing.
2. OpenTelemetry Java Agent để instrument tự động nhiều thư viện.
3. OTel SDK/manual instrumentation cho logic riêng.
4. Kết hợp agent và instrumentation thủ công khi biết rõ phạm vi, tránh duplicate spans.

**Chọn một đường instrumentation nhất quán cho từng thư viện.** Nếu agent và thư viện tự instrument cùng một HTTP client mà không phối hợp, trace có thể xuất hiện span lồng lặp hoặc duplicate metrics.

### 6.1. Các khái niệm cấu hình Spring Boot

Một cấu hình minh họa:

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 0.10
  metrics:
    tags:
      application: order-service
~~~

Đây là ví dụ khái niệm; property names, exporter và dependency modules phụ thuộc phiên bản Spring Boot/Micrometer đang dùng. Cần thêm Actuator, registry/exporter tương ứng và cấu hình endpoint exposure theo chính sách bảo mật. Không expose tất cả management endpoints công khai.

`probability: 0.10` là tỷ lệ sampling minh họa cho trace thông thường. Với hệ thống có yêu cầu điều tra, có thể cấu hình collector tail sampling để ưu tiên trace lỗi/chậm, nhưng cần tính buffer và resource budget. Không giả định sampling 10% nghĩa là mọi trace lỗi đều được giữ.

### 6.2. Service identity và resource attributes

Mỗi process cần danh tính ổn định:

- `service.name`: tên service, ví dụ `order-service`.
- `service.version`: version hoặc release identifier.
- `deployment.environment.name`: môi trường.
- `service.namespace`: nhóm/domain nếu có.
- `cloud.region`, `k8s.namespace.name`, `k8s.pod.name`: resource context theo quy ước instrumentation.
- `host.name` hoặc container attributes nếu cần điều tra.

Không gắn `service.name` bằng URL, request ID hoặc giá trị thay đổi theo request. Resource attributes mô tả process/deployment; span attributes mô tả operation cụ thể.

Ví dụ environment variables cho OpenTelemetry SDK/Agent:

~~~text
OTEL_SERVICE_NAME=order-service
OTEL_RESOURCE_ATTRIBUTES=service.version=1.8.0,deployment.environment.name=production
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.observability:4317
OTEL_PROPAGATORS=tracecontext,baggage
~~~

Endpoint và protocol cần khớp collector. Không đưa credential exporter vào manifest plain text; dùng workload identity/secret manager phù hợp.

## 7. Truyền context qua HTTP trong Spring

Với HTTP đồng bộ, client instrumentation thường:
1. Lấy current context từ execution đang xử lý.
2. Tạo client span.
3. Inject `traceparent`/`tracestate` vào outbound request.
4. Server extract context, tạo server span.
5. Khi response hoàn tất, kết thúc span và ghi status/latency.

Dùng HTTP client có observation/tracing instrumentation được cấu hình đúng. Ví dụ về mục tiêu behavior:

~~~text
Incoming request
  trace_id = abc
  server span = s1
      |
      +-- outbound Inventory request
             trace_id = abc
             client span = s2
             traceparent parent-id = s2
                    |
                    v
             Inventory server span = s3
             parent span = s2
~~~

### 7.1. Spring RestClient

Spring Framework có `RestClient` cho HTTP đồng bộ. Tùy phiên bản Spring Boot và client builder, observation có thể được tự động cấu hình hoặc cần builder được quản lý bởi application context. Ví dụ minh họa:

~~~java
@Configuration
class HttpClientConfiguration {
    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
            .baseUrl("http://inventory-service")
            .build();
    }
}
~~~

Khi dùng Spring Boot auto-configured `RestClient.Builder`, các customizers/observations có thể được áp dụng theo phiên bản và dependency. Nếu tự `new RestClient.Builder()` hoặc tự tạo client ngoài container, có thể bỏ qua instrumentation và propagation đã cấu hình.

Không tự set `traceparent` bằng cách đọc MDC rồi gắn header; MDC chỉ là bản trình bày log và có thể không chứa đầy đủ context. Hãy dùng tracing propagation của client/framework.

### 7.2. Spring WebClient và Reactor

`WebClient` thường được dùng với Reactor. Context của Reactor khác với `ThreadLocal` đơn giản:
- Một pipeline có thể đổi thread qua scheduler.
- Callback có thể chạy trên thread khác.
- MDC không tự động đúng nếu context propagation không được tích hợp.
- Cần dùng instrumentation và context propagation hỗ trợ reactive stack.

Ví dụ bean:

~~~java
@Configuration
class WebClientConfiguration {
    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("http://inventory-service")
            .build();
    }
}
~~~

Dùng builder được Spring Boot quản lý để nhận customizers/observations. Với Reactor, tránh lấy `MDC.get("traceId")` trong một callback rồi giả định giá trị đó luôn thuộc request hiện tại. Context có thể được phục hồi bằng Micrometer Context Propagation/Reactor integration theo phiên bản.

### 7.3. Gateway và proxy

Gateway cần:
- Giữ/propagate context theo trust policy.
- Không tạo một trace hoàn toàn mới cho mọi hop nếu muốn giữ distributed trace.
- Không làm mất header do allowlist/strip rules.
- Không forward baggage nhạy cảm hoặc header không được tin cậy.
- Có span riêng cho auth, routing hoặc policy khi có giá trị chẩn đoán.
- Tránh ghi toàn bộ headers chứa token vào logs.

Nếu gateway terminate và khởi tạo trace mới vì boundary bảo mật, cần quy ước link/correlation để đội vận hành vẫn nối được workflow mà không tin parent từ nguồn ngoài.

## 8. Truyền context qua Kafka và message broker

HTTP context propagation không tự động áp dụng cho mọi broker. Message producer cần inject context vào headers; consumer extract context và tạo consumer span theo instrumentation hoặc propagation convention.

~~~text
Order Service
  SERVER span
      |
      +-- PRODUCER span
             |
             +-- Kafka headers:
                    traceparent
                    tracestate
                    baggage (nếu allowlist)
                         |
                         v
                      Topic
                         |
                         v
                  Consumer Service
                    CONSUMER span
                         |
                         +-- DB transaction
                         +-- business effect
~~~

Các yêu cầu:
- Header names/encoding tuân theo convention thống nhất.
- Producer và consumer cùng dùng propagator compatible.
- Không serialize `ThreadLocal` hay Java object context vào message.
- Consumer tạo context mới nếu message thiếu hoặc context không hợp lệ.
- Với batch, một consumer span có thể cần link tới nhiều producer contexts.
- DLQ/retry topic phải giữ metadata cần thiết nhưng không kéo baggage nhạy cảm.
- Replay sau nhiều ngày có thể bắt đầu trace mới và link tới message/source trace thay vì tiếp tục trace cũ đã hết lifecycle.

### 8.1. Kafka headers

Một message có thể mang:

~~~text
headers:
  traceparent: 00-<trace-id>-<span-id>-01
  tracestate: <vendor-state>
  correlation-id: checkout-flow-123
  event-id: evt-456
~~~

Tên `correlation-id` và `event-id` là ví dụ contract ứng dụng. Dùng `traceparent`/`tracestate` theo W3C. Không đưa raw user data vào headers chỉ để thuận tiện tìm kiếm.

Khi dùng Spring Kafka, tracing có thể được hỗ trợ bởi Micrometer Observation hoặc OTel instrumentation tùy version/config. Bật observation cho template/listener khi framework hỗ trợ và kiểm tra trace thực tế; không giả định mọi `KafkaTemplate` tự tạo đều được instrument như bean auto-configured.

### 8.2. RabbitMQ và message metadata

Với RabbitMQ, propagation thường đi trong message headers/properties. Cần quy ước cho producer/consumer và bảo đảm retry/dead-letter giữ lại context phù hợp. Với message được republish, tạo span mới và link/propagate context theo semantics thay vì copy nguyên một span ID cũ.

**Không dùng message body làm nơi chứa tracing metadata** nếu broker header/property đã đáp ứng. Body là business contract; observability metadata nên có vòng đời và khả năng thay đổi riêng.

## 9. Context propagation qua thread pool và async execution

Một lỗi thường gặp trong Java:

~~~java
executor.submit(() -> {
    log.info("Processing order");
});
~~~

Nếu task chạy trên thread pool khác, `ThreadLocal` của request thread có thể không có mặt. Kết quả:
- Log thiếu trace/span IDs.
- Span con trở thành root ngoài ý muốn.
- Context của task trước bị sót nếu cleanup sai.
- MDC của một request có thể rò sang request khác khi tái sử dụng worker thread.

Cách giải quyết:
- Dùng executor được instrument hoặc context-aware wrapper.
- Dùng Micrometer Context Propagation hoặc OpenTelemetry Context API.
- Capture context lúc submit và restore trong phạm vi task.
- Luôn khôi phục/clear context sau task.
- Với CompletableFuture/Reactor, kiểm tra propagation qua từng executor/scheduler.
- Không tự sao chép toàn bộ ThreadLocal của request vào thread khác.

Ví dụ mục tiêu với Spring-managed executor:

~~~java
@Bean
ThreadPoolTaskExecutor applicationExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(8);
    executor.setMaxPoolSize(32);
    executor.setQueueCapacity(200);
    executor.setThreadNamePrefix("app-");
    executor.initialize();
    return executor;
}
~~~

Bean trên chỉ tạo executor; **nó không tự chứng minh context được truyền**. Cần cấu hình task decorator/context propagation theo phiên bản Spring/Micrometer đang dùng và test trace IDs ở task chạy thread khác. Tránh tự viết decorator chỉ copy MDC mà bỏ qua OpenTelemetry Context.

### 9.1. Scheduled jobs

Một scheduled job thường không có parent request hiện hành. Nên tạo một root span cho lần chạy, thêm attributes như job name, schedule type và execution ID có giới hạn. Nếu job được kích hoạt bởi event, có thể link với trace/message context ban đầu theo semantics.

Không giữ một trace context cũ trong singleton field rồi tái sử dụng cho lần chạy sau. Mỗi execution cần context riêng và kết thúc span trong `finally`/scope phù hợp.

## 10. MDC: nối log với trace

Mapped Diagnostic Context (MDC) cho phép logging framework thêm trường như `trace_id`, `span_id` vào mỗi log record. Một log có thể hiển thị:

~~~json
{
  "timestamp": "2026-11-12T03:15:00Z",
  "level": "INFO",
  "service": "order-service",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "message": "Order validation completed",
  "order_state": "PENDING"
}
~~~

Cách triển khai thường:
- Dùng Micrometer Tracing bridge hoặc OTel instrumentation tích hợp với logging.
- Cấu hình pattern/JSON encoder để xuất trace/span IDs.
- Đảm bảo MDC được set/restore đúng ở thread boundary.
- Giữ field name thống nhất giữa service và log backend.
- Redact thông tin nhạy cảm trước khi export.

Ví dụ Logback pattern minh họa:

~~~xml
<pattern>%d{ISO8601} %-5level [%thread] trace=%X{traceId:-} span=%X{spanId:-} %logger - %msg%n</pattern>
~~~

Tên MDC keys phụ thuộc bridge/instrumentation và cấu hình. Hãy kiểm tra output thực tế; không mặc định mọi stack đều dùng `traceId` và `spanId` giống nhau.

### 10.1. MDC không phải context propagation API

MDC là lớp hiển thị log, thường dựa trên thread-local. Nó không phải nguồn sự thật cho tracing context. Khi cần tạo child span hoặc inject header, dùng current context của tracing library. Copy MDC string qua thread có thể làm log trông liên kết nhưng trace graph vẫn bị đứt.

### 10.2. Không ghi business identifiers bừa bãi

Có thể thêm `order_id` vào log/traces nếu policy cho phép và access control phù hợp; không thêm vào metric labels. Với PII hoặc tenant ID, ưu tiên tokenized/pseudonymous value và hạn chế retention. Trace backend cũng có thể chứa dữ liệu nhạy cảm nếu span attributes được thêm tùy tiện.

## 11. Đo chỉ số theo từng service: RED và USE

Một bộ metric cơ bản cho service HTTP:

**RED**
- **Rate:** số request/operation mỗi giây.
- **Errors:** số và tỷ lệ lỗi theo định nghĩa.
- **Duration:** latency distribution, đặc biệt p50/p95/p99.

**USE**
- **Utilization:** mức sử dụng CPU, memory, connection pool, worker threads.
- **Saturation:** queue depth, pending requests, pool wait, throttling.
- **Errors:** lỗi của tài nguyên hoặc subsystem.

RED thường hữu ích cho request-driven services; USE giúp hiểu tài nguyên đang bão hòa ở đâu. Worker/message consumers cần thêm throughput, oldest message age, lag, retry, DLQ và processing duration.

| Nhóm metric | Ví dụ | Dùng để |
| --- | --- | --- |
| Request rate | `http.server.requests` | Lưu lượng theo service/route |
| Error rate | `http.server.requests` với outcome/status | SLI và alert |
| Duration | Histogram HTTP duration | p95/p99, latency budget |
| Dependency | Client request duration/errors | Tìm downstream bottleneck |
| JVM | Heap, GC pause, threads | Runtime health |
| Pool | Active/idle/pending DB connections | Queueing và saturation |
| Messaging | Records received/processed, lag, DLQ | Consumer health |
| Cache | Hit/miss/eviction/load duration | Cache effectiveness |
| Business | Orders accepted, payment outcomes | Business SLI |
| Runtime | CPU throttling, restarts, readiness | Platform interaction |

Tên metric phụ thuộc Micrometer registry và instrumentation version. Không coi tên minh họa là contract bất biến; chuẩn hóa tên và unit trong observability conventions của tổ chức.

## 12. Metric dimensions: service, route, outcome và dependency

Metrics phải cho phép so sánh mà không tạo số lượng series không kiểm soát. Các dimension thường hữu ích:

- `service`: tên service ổn định.
- `environment`: production/staging/dev.
- `region`: vùng triển khai.
- `route`: route template như `/orders/{id}`.
- `method`: HTTP method.
- `status` hoặc `outcome`: success/client_error/server_error.
- `dependency`: tên dependency có giới hạn.
- `operation`: tên operation đã chuẩn hóa.
- `version`: có thể dùng trong rollout analysis nhưng phải quản lý số version active.

Tránh:
- Raw URL chứa order ID.
- `user_id`, `session_id`, `trace_id`, `span_id`.
- Exception message hoặc SQL query làm label.
- Tenant ID không giới hạn.
- Dynamic hostnames, random pod IDs hoặc request payload values làm dimension nếu cardinality quá lớn.

Ví dụ một route `/orders/123456` nên được chuẩn hóa thành `/orders/{id}`. Nếu metric label giữ từng order ID, mỗi order có thể tạo một time series riêng, làm backend tốn memory và query chậm.

**Giữ high-cardinality context trong traces/logs có kiểm soát; giữ metric labels hữu hạn.**

## 13. Counter, gauge, timer và histogram

### Counter

Đếm sự kiện tăng dần: số request, số message xử lý, số retry. Không giảm counter khi process sống; hệ thống metrics xử lý reset khi process restart theo semantics của counter.

### Gauge

Giá trị tức thời: queue depth, active connections, in-flight requests, cache entries. Gauge có thể tăng/giảm.

### Timer/histogram

Đo duration distribution; dùng để tính percentile từ histogram hoặc backend hỗ trợ. Không chỉ xuất average nếu SLO dựa trên tail latency.

### Distribution summary

Đo phân bố một giá trị như payload size, batch size hoặc số items. Chọn unit và bucket phù hợp để tránh đo sai.

Ví dụ Micrometer:

~~~java
@Component
class OrderMetrics {
    private final Counter acceptedOrders;
    private final Timer validationTimer;

    OrderMetrics(MeterRegistry registry) {
        this.acceptedOrders = Counter.builder("orders.accepted")
            .description("Number of accepted orders")
            .register(registry);

        this.validationTimer = Timer.builder("orders.validation")
            .description("Order validation duration")
            .publishPercentileHistogram()
            .register(registry);
    }

    void recordAccepted() {
        acceptedOrders.increment();
    }

    <T> T measureValidation(Supplier<T> operation) {
        return validationTimer.record(operation);
    }
}
~~~

Ví dụ minh họa; cần import `MeterRegistry`, `Counter`, `Timer`, `Supplier`, chọn bucket/percentile theo registry và tránh đăng ký meter lặp cho mỗi request. Không thêm dynamic tags theo order ID.

**Histogram thường phù hợp để tổng hợp latency qua nhiều replica** hơn client-side percentile độc lập, vì bucket counts có thể được gộp trước khi ước lượng quantile. Client-side percentile không nhất thiết merge được chính xác giữa các instance.

## 14. Đo HTTP server và client theo service

Một service nên đo cả inbound và outbound:

**Inbound/server**
- Request count và duration.
- Status/outcome.
- Active/in-flight requests.
- Payload size khi có giá trị.
- Route template.
- Authentication/authorization outcome theo dimension giới hạn.

**Outbound/client**
- Request count/duration theo dependency.
- Timeout/cancel/error.
- Retry attempts.
- Connection pool wait.
- Circuit breaker state.
- Response code class.
- Deadline remaining khi cần chẩn đoán.

Ví dụ bảng dashboard:

| Service | Inbound p95 | 5xx rate | Outbound dependency | Dependency p95 | Retry rate |
| --- | ---: | ---: | --- | ---: | ---: |
| order-service | 240 ms | 0,2% | inventory-service | 110 ms | 0,1% |
| order-service | 240 ms | 0,2% | pricing-service | 180 ms | 0,4% |
| payment-service | 390 ms | 0,5% | payment-provider | 310 ms | 1,2% |

Các số chỉ minh họa. Không kết luận p95 của Order bằng tổng các p95 dependency; trace critical path và end-to-end SLI mới cho biết tác động thực.

### 14.1. Service-level vs journey-level SLI

Service-level SLI đo khả năng của một thành phần. Journey-level SLI đo outcome người dùng qua nhiều thành phần.

Ví dụ:
- Order API success rate có thể 99,95%.
- Payment API success rate có thể 99,9%.
- Nhưng checkout success có thể thấp hơn do Inventory, client validation, duplicate request hoặc trạng thái bất đồng bộ.

Một nhóm sở hữu service chịu trách nhiệm service SLO của mình và phối hợp với journey owner để hiểu tác động. Không tuyên bố checkout đạt SLO chỉ vì từng API trả nhiều HTTP 200.

## 15. Histogram bucket và percentile

Với latency SLO, bucket nên có boundary quanh ngưỡng mục tiêu. Ví dụ mục tiêu 300 ms:

~~~text
0.005s, 0.01s, 0.025s, 0.05s,
0.1s, 0.15s, 0.2s, 0.25s, 0.3s,
0.4s, 0.5s, 0.75s, 1s, +Inf
~~~

Chọn bucket theo phân bố thực và đơn vị nhất quán. Bucket quá rộng gần ngưỡng SLO làm khó ước lượng tỷ lệ đạt; quá nhiều bucket làm tăng series/storage. Không copy một bộ bucket chung mà không xem latency profile.

PromQL minh họa:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, route) (
    rate(http_server_request_duration_seconds_bucket[5m])
  )
)
~~~

Tên metric có thể khác theo registry/exporter. Với native histogram, query có thể khác. `histogram_quantile` ước lượng quantile từ bucket; kết quả có sai số do bucket boundaries và phân bố.

Tỷ lệ request hoàn tất trong 300 ms có thể dùng bucket `le="0.3"` nếu histogram có boundary chính xác và population/filters đúng. Đừng tính p95 bằng cách lấy trung bình p95 của từng Pod.

## 16. Exemplars: nối metric sample với trace

Exemplar có thể gắn một trace ID vào một observation trong histogram để từ spike metric mở được trace đại diện. Điều này hữu ích khi:
- p99 tăng nhưng cần biết request nào chậm.
- Error rate tăng theo route.
- Muốn chuyển từ dashboard tổng hợp sang trace cụ thể.
- Không muốn đưa trace ID vào metric label.

Exemplar thường cần:
- Registry/backend hỗ trợ.
- Trace context hiện hành và sampling phù hợp.
- Collector/exporter cấu hình đúng.
- Grafana/metrics UI hoặc backend có khả năng mở trace từ exemplar.
- Trace retention đủ lâu so với metric window.

Exemplar không phải nơi lưu tất cả trace IDs; nó là một mẫu liên kết. Không đưa trace ID thành label metric vì điều đó gây cardinality explosion.

## 17. Log, metric và trace phải dùng chung semantics

Nếu service A ghi `dependency=inventory`, service B ghi `target=stock`, còn dashboard dùng `remote_service=inventory-service`, correlation trở nên khó khăn.

Nên chuẩn hóa:
- `service.name` và `service.version`.
- `deployment.environment.name`.
- HTTP route/method/status conventions.
- Error code taxonomy.
- Dependency/service names.
- Operation names.
- Trace/span identifiers trong logs.
- Units và metric naming.
- Tenant classification và data redaction.
- Business event/correlation identifiers.

Tên metric có thể khác giữa Micrometer và OTel semantic conventions, nhưng phải có mapping/documentation. Không tạo nhiều metric chỉ khác tên cho cùng một điều đo lường.

Một quy ước chung cho lỗi:
- `error.type`: loại lỗi có giới hạn.
- `error.code`: mã nội bộ được chuẩn hóa.
- `outcome`: success/failure/timeout/cancelled.
- `exception.type`: class name khi phù hợp.
- Stack trace: log có access control, không phải metric label.

## 18. Sampling và tail sampling

Sampling giảm chi phí nhưng ảnh hưởng khả năng quan sát.

### Head sampling

Quyết định tại đầu trace, trước khi biết kết quả cuối. Ưu điểm là ít tài nguyên và nhất quán; nhược điểm là có thể bỏ sót một request hiếm nhưng rất chậm/lỗi.

### Tail sampling

Collector giữ trace tạm thời, chờ các span đến rồi chọn theo:
- Có error.
- Duration vượt threshold.
- Route critical.
- Retry nhiều.
- Tenant tier hoặc operation được phép.
- Tỷ lệ success ngẫu nhiên để baseline.

Tail sampling cần memory, buffering và timeout; trace đến muộn hoặc collector restart có thể làm trace không đầy đủ. Phải sizing collector theo throughput, spans/trace, decision wait và number of workers.

Không bật tail sampling mà không hiểu trace routing: các span của cùng trace cần đến cùng decision point hoặc có cơ chế phân phối phù hợp. Nếu split trace qua nhiều collector không đồng bộ, sampling có thể giữ một phần và bỏ phần còn lại.

### 18.1. Sampling và SLO

Sampling trace không được làm thay đổi số đếm metric hoặc SLI. Metrics cần được ghi trên toàn bộ traffic theo semantics; traces có thể sample. Nếu chỉ tính error rate từ sampled traces, SLO sẽ sai trừ khi có phương pháp thống kê phù hợp đã được thiết kế.

## 19. Truyền context qua nhiều boundary và trust zones

Một request có thể đi từ internet vào gateway, qua service nội bộ, tới provider bên ngoài. Không phải boundary nào cũng nên forward mọi context.

| Boundary | Trace context | Baggage | Correlation/business ID |
| --- | --- | --- | --- |
| Browser → public gateway | Theo policy; validate hoặc tạo trace mới | Thường lọc chặt | Request ID do server kiểm soát; business ID theo contract |
| Gateway → internal service | Propagate W3C context | Allowlist | Giữ correlation nếu hợp lệ |
| Service → trusted internal API | Propagate | Chỉ key cần thiết | Theo workflow |
| Service → external provider | Chỉ khi provider được phép nhận | Thường không gửi | Provider reference theo contract |
| Producer → broker | Inject headers | Allowlist nhỏ | Event/workflow IDs |
| Broker → consumer | Extract/validate | Filter | Giữ event/correlation IDs |
| DLQ/replay | Có thể tạo trace mới/link cũ | Loại dữ liệu không còn cần | Giữ event ID và replay ID |

Nếu public client gửi một `traceparent`, hệ thống có thể chọn tiếp tục trace hoặc khởi tạo trace mới theo trust policy. Điều quan trọng là không cho client kiểm soát sampling, baggage hoặc service identity ngoài giới hạn.

External provider có thể echo header hoặc ghi lại chúng. Chỉ truyền context nếu hợp đồng và privacy/security review cho phép.

## 20. Đo metrics cho message consumers và workers

HTTP metrics không phản ánh đủ một worker. Những chỉ số nên cân nhắc:

- `messages_received_total`
- `messages_processed_total`
- `messages_failed_total`
- `messages_retried_total`
- `messages_dead_lettered_total`
- Processing duration histogram.
- Consumer lag hoặc oldest message age.
- In-flight messages.
- Batch size.
- Commit/ack latency.
- Rebalance count/duration.
- Handler concurrency và queue depth.

Dùng dimensions có giới hạn: service, topic/queue, consumer group, outcome, event type đã kiểm soát. Không đưa message ID hoặc customer ID vào metric labels.

**Lag bằng 0 chưa chắc consumer khỏe:** consumer có thể không nhận message vì producer không gửi, hoặc offset đã reset bỏ qua dữ liệu. Kết hợp throughput, oldest age, business completion và synthetic event.

### 20.1. Context cho message processing

Consumer log nên có:
- trace ID hiện hành.
- span ID consumer.
- event ID/correlation ID theo contract.
- topic/partition/offset hoặc queue name trong phạm vi cardinality.
- processing outcome và duration.
- retry attempt có giới hạn.
- schema version.

Không log full message body. Với batch, ghi batch ID/count và lỗi theo record có chọn lọc, bảo vệ PII.

## 21. Business metrics: đo kết quả, không chỉ HTTP

Các service nghiệp vụ nên bổ sung metrics có ý nghĩa:
- Orders accepted/rejected.
- Payment authorization/capture outcomes.
- Inventory reservations accepted/released.
- Outbox publish success/pending.
- Reconciliation pending/failed.
- Workflow completion duration.
- Saga compensation count.
- Idempotency duplicate detections.

Ví dụ metric `orders.accepted` cần định nghĩa chính xác: đơn đã được ghi bền vững hay chỉ request được validation? Đặt tên và mô tả tránh gây hiểu lầm.

Không dùng order ID làm tag. Nếu cần phân tích một đơn cụ thể, truy vấn trace/log có quyền truy cập qua order reference. Business metric phải có owner, unit, outcome semantics và cách xử lý duplicate/replay.

## 22. Java/Spring: custom Observation cho business operation

Micrometer Observation có thể tạo một observation vừa liên kết metric và tracing handler tùy cấu hình. Ví dụ khái niệm:

~~~java
@Service
class OrderApplicationService {
    private final ObservationRegistry observationRegistry;
    private final OrderRepository repository;

    OrderApplicationService(
        ObservationRegistry observationRegistry,
        OrderRepository repository
    ) {
        this.observationRegistry = observationRegistry;
        this.repository = repository;
    }

    Order create(CreateOrder command) {
        return Observation.createNotStarted(
                "order.create",
                observationRegistry
            )
            .lowCardinalityKeyValue("operation", "create")
            .observe(() -> repository.save(command.toOrder()));
    }
}
~~~

Ví dụ cần import đúng package và cấu hình ObservationRegistry/handlers theo Spring Boot version. Tên operation ổn định; tag `operation=create` có cardinality thấp. Không thêm `orderId` làm low-cardinality key. Nếu cần order ID trong trace, dùng attribute/log có privacy review và giới hạn retention.

Observation có thể tạo metric và span thông qua handlers đã đăng ký. Nếu chỉ có metrics handler mà không có tracing handler, không mặc định sẽ có span. Kiểm tra cấu hình export và sampling.

### 22.1. Low-cardinality và high-cardinality values

Micrometer Observation phân biệt low-cardinality key-values dùng được cho metrics với high-cardinality values thường chỉ phù hợp tracing. Dùng đúng API theo semantics của version:
- `lowCardinalityKeyValue`: service operation, bounded outcome, dependency class.
- `highCardinalityKeyValue`: identifier phục vụ trace, nếu policy cho phép.

Không gắn giá trị động vào low-cardinality tags. Cũng không mặc định high-cardinality luôn an toàn: traces/logs vẫn có cost, privacy và access concerns.

## 23. Context propagation với CompletableFuture

Khi tạo async task, capture context tại điểm submit và truyền qua executor có context propagation. Với Micrometer Context Propagation, Spring hỗ trợ các cơ chế như `ContextSnapshot`/task decorators tùy phiên bản và cấu hình. Pseudocode về semantics:

~~~text
Request thread:
  current trace context = T
  submit task with captured context T
       |
       v
Worker thread:
  restore context T
  create child span
  execute operation
  close scope and restore previous context
~~~

Không giữ scope mở qua nhiều thread hoặc đóng scope trên thread khác nếu API không hỗ trợ. Không tự viết code copy `ThreadLocal` toàn cục. Dùng integration chính thức của framework và kiểm tra context ở executor thực tế.

Test cần xác minh:
- Task log có đúng trace ID.
- Span task là child/link phù hợp.
- Sau task, worker thread không giữ context cũ.
- Khi task fail/cancel, scope vẫn được đóng.
- Hai request chạy song song không lẫn MDC/context.

## 24. Context propagation trong Reactor

Reactor dùng `Context` gắn với subscription; execution có thể đổi thread. Micrometer Context Propagation và Reactor integration có thể bridge context với ThreadLocal/MDC khi được cấu hình. Tùy Spring Boot/Reactor version, cơ chế tự động propagation có thể khác.

Các nguyên tắc:
- Dùng instrumentation được Spring Boot quản lý.
- Không tự đọc MDC để truyền trace.
- Cẩn thận `publishOn`, `subscribeOn`, callbacks và custom schedulers.
- Đóng span khi terminal signal success/error/cancel.
- Không lưu `ContextView` hoặc trace scope trong singleton field.
- Kiểm tra context ở reactive chain sau thread switch.
- Kiểm tra cancellation để không để span mở hoặc công việc tiếp tục vô hạn.

Một test nên đặt `publishOn(Schedulers.parallel())`, log/observe ở trước và sau boundary, rồi xác minh trace vẫn liên tục và không lẫn giữa hai subscription.

## 25. Truyền context qua Spring Kafka

Nếu dùng Spring Kafka, quan sát producer/consumer cần được cấu hình nhất quán. Một cấu hình khái niệm:

~~~yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092

management:
  observations:
    annotations:
      enabled: true
~~~

Property này không phải công tắc chung bảo đảm mọi producer/listener được trace; việc bật observation cho `KafkaTemplate` và listener containers phụ thuộc Spring Kafka/Spring Boot version và bean wiring. Cần tham khảo version đang dùng, cấu hình `setObservationEnabled` khi API hỗ trợ và xác minh header propagation thực tế.

Một producer/consumer test cần kiểm tra:
1. Producer trong trace có tạo producer span.
2. Message header chứa trace context theo propagator.
3. Consumer extract được context và tạo consumer span/link.
4. Message retry/DLQ giữ event/correlation ID phù hợp.
5. Consumer processing duration và outcome được đo.
6. Duplicate delivery không làm metrics business bị đếm sai nếu metric định nghĩa theo unique business effect.
7. Context không bị rò qua listener threads.

Không hard-code header theo một vendor khi chuẩn W3C đã được dùng chung; nếu có custom header, tài liệu hóa compatibility và lý do.

## 26. Naming conventions cho span và metric

Tên operation nên ổn định, có ý nghĩa và ít giá trị động:

| Không nên | Nên dùng |
| --- | --- |
| `GET /orders/12345` | `GET /orders/{id}` |
| `load-user-9988` | `user.profile.load` |
| `kafka-record-evt-abc` | `kafka.process` |
| `sql-select-order-123` | `db.query` hoặc semantic convention phù hợp |
| `payment-provider-host-17` | `payment.authorize` |
| `order.create.customer-42` | `order.create` |

Span names mô tả operation; attributes mô tả dimension cụ thể có giới hạn. Không đưa raw SQL, URL chứa query parameters hoặc exception message vào tên span.

Metric names cần:
- Có unit rõ (seconds, bytes, items).
- Có type semantics (counter, gauge, histogram).
- Có description.
- Không trùng tên nhưng khác meaning.
- Có owner và dashboard/alert consumers.
- Có quy tắc deprecation/versioning.

Nếu đổi metric name hoặc labels, dashboard và alert có thể hỏng; thay đổi observability schema cũng cần review như API contract.

## 27. Error recording và exception semantics

Không phải mọi exception đều là lỗi hệ thống:
- Validation failure do input sai có thể là client error.
- Business rejection như out of stock là outcome nghiệp vụ hợp lệ.
- Dependency timeout là technical failure.
- Cancellation do client disconnect có thể không phải server defect.
- Retry thành công có thể vẫn là tín hiệu degraded dependency.

Trace status và metric outcome phải phản ánh semantics:
- `success`
- `client_error`
- `business_rejected`
- `server_error`
- `timeout`
- `cancelled`
- `retry_exhausted`

Không ghi mọi exception thành span status ERROR nếu đó là business outcome được thiết kế. Ngược lại, không nuốt exception rồi đánh dấu success chỉ để giảm error rate.

Stack trace nên có trong log khi cần, không nên là metric label. Error type/code phải có cardinality được kiểm soát.

## 28. SLI/SLO và dashboard theo service

Một service có thể định nghĩa SLI:

- Request success rate theo route/outcome.
- Latency distribution theo endpoint.
- Dependency availability/latency.
- Message processing success và oldest age.
- Data correctness/business invariants.
- Saturation: thread pool, DB pool, queue, CPU throttling.

Ví dụ:
- Order API: 99,9% request hợp lệ được xử lý theo contract trong cửa sổ 28 ngày.
- 95% create-order acknowledgement dưới 300 ms.
- 99% critical events được xử lý trong 2 phút.
- Không có duplicate payment effect trong tập giao dịch được đối soát.

Các con số chỉ minh họa. SLO phải có population, event definition, window và owner rõ. Không gộp HTTP acknowledgement với business completion nếu workflow async.

Dashboard service nên gồm:
1. RED inbound.
2. Outbound dependency latency/error.
3. JVM/resource/pool/queue saturation.
4. Trace examples/exemplars.
5. Business metrics.
6. SLO/error budget.
7. Release/version and region.
8. Alert state và runbook links.

## 29. Alert dựa trên tác động và khả năng hành động

Alert nên phát page khi người trực có hành động cần làm:
- SLO burn rate của user journey tăng nhanh.
- Service error rate/latency vượt guardrail có ảnh hưởng.
- Consumer oldest message age đe dọa business deadline.
- DB pool pending/lock wait gây request failure.
- Telemetry pipeline drop dữ liệu critical.
- Cardinality/ingestion anomaly có nguy cơ làm backend observability ngừng hoạt động.

Không page cho mọi trace error hoặc mọi Pod restart. Dùng ticket/dashboard cho tín hiệu chưa cần can thiệp ngay. Alert cần link dashboard, trace/log query, service owner, runbook và environment.

Nếu metrics pipeline hỏng, cần một tín hiệu độc lập báo telemetry gap. Không để “không có dữ liệu” bị hiểu thành “không có lỗi”.

## 30. Security và privacy của observability context

Trace/log/metric có thể chứa dữ liệu nhạy cảm. Cần:
- Không ghi token, password, cookie, payment card data hoặc secret.
- Không truyền PII trong baggage.
- Hạn chế business IDs trong trace/log theo access policy.
- Redact trước khi export khỏi process/trust zone.
- Access control theo team/tenant/environment.
- Retention và deletion policy rõ.
- Audit ai truy vấn telemetry nhạy cảm.
- Không expose Actuator/Prometheus endpoints ra public ingress.
- Giới hạn kích thước header và baggage.
- Chống header injection/forged context.
- Không dùng trace ID hoặc correlation ID để authorize request.
- Đảm bảo sampling không vô tình bỏ audit events bắt buộc.

Metrics thường dễ chia sẻ rộng hơn traces/logs vì ít dữ liệu chi tiết; nhưng label values vẫn có thể tiết lộ tenant hoặc deployment nội bộ. Phân loại dữ liệu trước khi mở dashboard cho người dùng rộng.

## 31. Kiểm soát chi phí và cardinality

Chi phí telemetry tăng theo:
- Request rate × spans/request × sampling.
- Logs/request × bytes × retention.
- Active metric series × scrape rate × retention.
- Baggage/span attributes và index.
- Collector buffering/tail sampling.
- Cross-region export và query usage.

Các biện pháp:
1. Dùng metric labels bounded.
2. Dùng route template.
3. Giữ trace bình thường theo sample policy, ưu tiên error/slow.
4. Giảm duplicate spans/instrumentation.
5. Dùng logs structured, tránh stack trace lặp vô hạn.
6. Chọn retention theo mục tiêu.
7. Batch/compress OTLP export.
8. Đặt collector queue/CPU/memory limits.
9. Có quota và anomaly alert.
10. Đo dropped telemetry, không chỉ ingestion cost.

**Không giảm telemetry đến mức mù sự cố.** Giữ SLO metrics và error counters đầy đủ; trace sampling là trade-off riêng. Khi incident, có thể bật detail theo service/route và timebox, rồi tự quay về policy sau đó.

## 32. OpenTelemetry Collector: xử lý và export

Một pipeline collector có thể gồm:

~~~text
OTel SDK / Java Agent
        |
        | OTLP
        v
OpenTelemetry Collector
        |
        +--> memory limiter
        +--> attributes/redaction processor
        +--> batch processor
        +--> tail sampling (nếu dùng)
        |
        +--> trace backend
        +--> metrics backend
        +--> log backend
~~~

Các processor/exporter thực tế phụ thuộc collector distribution và backend. Cần:
- Memory limiter để tránh collector OOM.
- Bounded queues và retry policy.
- Batch để giảm network overhead.
- Redaction/drop processors cho thuộc tính nhạy cảm.
- Sampling theo policy.
- Health/telemetry của collector.
- Exporter timeout và backpressure.
- HA/scaling theo trace affinity nếu tail sampling.

Collector outage không nên block request nghiệp vụ. SDK/exporter cần timeout và bounded queue/drop behavior; metric về dropped spans/logs phải được theo dõi.

## 33. Kiểm thử context propagation

Propagation là hành vi tích hợp, cần test ở boundary thực.

### HTTP test

- Gửi request có `traceparent` hợp lệ vào service.
- Xác minh server span có trace ID mong đợi.
- Xác minh outbound request tới stub có cùng trace ID và parent span đúng.
- Test header thiếu/sai format; service tạo context mới theo policy.
- Test baggage allowlist và kích thước.
- Test client timeout/cancel, span kết thúc đúng.

### Async test

- Submit task qua executor và xác minh trace/MDC.
- Chạy hai request song song để phát hiện context leak.
- Test exception/cancellation và cleanup.
- Với Reactor, test qua `publishOn`/`subscribeOn`.
- Với scheduled job, xác minh root span mới.

### Messaging test

- Producer inject headers.
- Consumer extract context.
- Retry/DLQ giữ event ID/correlation theo contract.
- Batch link nhiều parent contexts đúng semantics.
- Replay tạo trace mới/link cũ nếu cần.
- Không có duplicate business effect.

### Metrics test

- Meter có tên, unit và description đúng.
- Tags chỉ chứa bounded values.
- Counter tăng đúng theo business semantics.
- Timer/histogram ghi duration ở success và failure theo policy.
- Không đăng ký meter động mỗi request.
- Không tạo metric series theo trace/order/user IDs.

Một unit test chỉ assert MDC string không đủ chứng minh distributed trace được nối; cần test outbound headers hoặc exported spans.

## 34. Ví dụ kiểm tra trace bằng test exporter

Có thể dùng OTel SDK test exporter hoặc in-memory span exporter trong integration test để thu spans. Ý tưởng:

~~~text
Arrange:
  - OTel test SDK + in-memory exporter
  - HTTP server/service thật hoặc test slice
  - Downstream stub
Act:
  - Gửi inbound request có trace context
  - Service gọi downstream
Assert:
  - Có server span và client span
  - trace_id nhất quán
  - parent relationship đúng
  - status/error attributes phù hợp
  - span đã ended
Cleanup:
  - shutdown SDK/exporter
  - reset stub và context
~~~

API cụ thể của exporter phụ thuộc OTel SDK version. Nếu dùng Spring Boot/Micrometer bridge, chọn test configuration tương ứng; tránh khởi tạo hai SDK global providers trong cùng JVM. Đảm bảo test đóng provider sau khi chạy để không rò thread/export queue.

## 35. Prometheus và Micrometer: truy vấn chỉ số

Ví dụ tính request rate:

~~~promql
sum by (service, route) (
  rate(http_server_requests_seconds_count[5m])
)
~~~

Ví dụ error ratio:

~~~promql
sum by (service, route) (
  rate(http_server_requests_seconds_count{status=~"5.."}[5m])
)
/
clamp_min(
  sum by (service, route) (
    rate(http_server_requests_seconds_count[5m])
  ),
  1
)
~~~

Ví dụ p95 histogram:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, service, route) (
    rate(http_server_requests_seconds_bucket[5m])
  )
)
~~~

Tên metric/labels có thể khác theo Micrometer registry, exporter và version. Kiểm tra `/actuator/prometheus` trong môi trường được bảo vệ để xác định tên thật. Nếu metric count đã được đổi sang OpenTelemetry naming hoặc histogram format khác, điều chỉnh query theo backend.

Không dùng `avg(p95_per_pod)` làm p95 toàn service. Với classic histogram, gộp bucket counts rồi mới tính quantile. Error ratio cần thống nhất denominator và loại trừ/bao gồm các outcome theo SLI.

## 36. Troubleshooting: trace bị đứt giữa các service

Triệu chứng: Gateway có trace nhưng Order hoặc Inventory tạo trace mới.

Kiểm tra:
1. Gateway có inject `traceparent` vào outbound không?
2. Service nhận có extract đúng propagator không?
3. Header có bị ingress/proxy strip hoặc rename?
4. HTTP client có được instrument không, hay tự tạo client ngoài Spring context?
5. Context có mất ở executor/reactive boundary không?
6. Agent và manual SDK có xung đột hoặc duplicate instrumentation?
7. Sampling có làm một số span bị bỏ, tạo cảm giác trace bị đứt?
8. Collector có nhận đủ span và đồng bộ trace ID?
9. External boundary có policy chủ động tạo root trace mới?
10. Message broker headers có được inject/restore không?

Phân biệt **context propagation failure** với **sampling/export loss**: nếu outbound header đúng nhưng span không xuất hiện, lỗi có thể nằm ở instrumentation/exporter/backend.

## 37. Troubleshooting: log không có trace ID hoặc MDC bị lẫn

Nguyên nhân thường gặp:
- Logging pattern không in MDC keys đúng.
- Bridge/instrumentation chưa cấu hình.
- Async task không propagate context.
- ThreadLocal không được cleanup.
- Reactor thread switch không có context bridge.
- Log appender được tạo trước khi logging context sẵn sàng.
- Có nhiều tracing providers hoặc bridge xung đột.
- Service tự xóa MDC trong filter nhưng không khôi phục giá trị trước đó.

Cách kiểm tra:
- Gửi hai request song song có trace IDs khác nhau.
- Ghi log ở đầu request, sau outbound call, trong executor và khi kết thúc.
- Xác minh mỗi dòng log gắn đúng trace.
- Sau khi task kết thúc, chạy một task không có context và xác minh không còn ID cũ.
- So sánh log fields với exported spans.

Không sửa bằng cách thêm `MDC.put("traceId", ...)` ở nhiều controller; điều đó dễ tạo trạng thái lệch. Dùng bridge có lifecycle rõ và test.

## 38. Troubleshooting: metric cardinality tăng bất thường

Dấu hiệu:
- Active series tăng nhanh sau release.
- Prometheus memory/query latency tăng.
- Metrics backend từ chối sample hoặc vượt quota.
- Dashboard có nhiều series gần như giống nhau.

Điều tra:
- Liệt kê labels mới.
- Tìm raw path, user/tenant/order IDs, exception messages hoặc dynamic values.
- Kiểm tra tag provider/custom Observation convention.
- Kiểm tra route normalization.
- So sánh service version trước/sau.
- Xác định metric nào tạo nhiều series nhất.
- Đánh giá dashboard/query đang dùng label nào.

Khắc phục:
- Bỏ dynamic label và thay bằng bounded classification.
- Chuyển identifier sang log/trace có access control.
- Giới hạn error code taxonomy.
- Dùng route template.
- Thiết lập cardinality budget và alert.
- Thêm test bảo vệ metric tags trong CI.

Không chỉ xóa series ở backend rồi để instrumentation sai tiếp tục phát sinh.

## 39. Troubleshooting: trace có quá nhiều span hoặc duplicate span

Nguyên nhân:
- Java Agent và manual instrumentation cùng bọc HTTP client.
- Spring Observation và custom aspect tạo span cho cùng operation.
- Retry tạo nhiều span nhưng tên không thể phân biệt attempt.
- Logging/SQL instrumentation quá chi tiết.
- Một business method bị instrument ở cả controller, service và repository không có giá trị.

Khắc phục:
- Xác định instrumentation owner theo library.
- Chỉ tạo custom span ở business boundary thực sự cần.
- Ghi retry attempt bằng bounded attribute/event.
- Không instrument getter/utility.
- Tắt một instrumentation duplicate theo config chính xác.
- Test trace topology sau khi thay đổi.

Duplicate spans không chỉ tốn tiền; chúng có thể làm người điều tra hiểu sai thời gian và dependency graph.

## 40. Versioning và semantic conventions

OpenTelemetry semantic conventions có thể thay đổi theo version; Spring Boot, Micrometer, OTel Agent và exporter cũng có chu kỳ nâng cấp riêng.

Quản lý:
- Pin version agent/SDK/bridge/exporter.
- Đọc release notes và migration guides khi nâng cấp.
- Tránh thay tên span/metric tùy tiện trong một release.
- Có dashboard/alert migration plan.
- Dùng resource attributes ổn định.
- Ghi instrumentation version khi cần điều tra.
- Test context propagation và metric names trước rollout.
- Cho phép tương thích tạm thời khi nhiều version chạy song song.

Metric name hoặc label change có thể phá SLO query. Treat observability schema như một interface vận hành cần compatibility.

## 41. Observability cho multi-region và multi-tenant

Trong môi trường nhiều region:
- Propagate trace context qua region boundary khi được phép.
- Ghi region của service dưới dạng resource attribute.
- Đo network latency và cross-region calls.
- Theo dõi clock skew và exporter delay.
- Phân biệt service version/region trong rollout.
- Kiểm soát egress và data residency của telemetry.

Với multi-tenant:
- Không đưa tenant ID thô vào metric label nếu cardinality lớn.
- Có thể dùng tenant tier/plan với số giá trị giới hạn.
- Traces/logs theo tenant cần access control.
- Không cho baggage quyết định quyền truy cập tenant.
- Đo fairness và noisy-neighbor bằng metrics tổng hợp.
- Sampling policy có thể ưu tiên cohort/tier theo policy nhưng không bỏ qua privacy.

Một trace đi qua hai region không có nghĩa dữ liệu trace được phép export ra một backend ở region thứ ba. Residency và retention áp dụng cho telemetry như dữ liệu vận hành khác.

## 42. Context cho request retries và hedged requests

Một request retry có thể tạo nhiều attempt:
- Mỗi outbound attempt nên có span riêng hoặc event rõ.
- Giữ trace context của workflow.
- Ghi retry attempt bằng attribute có cardinality thấp.
- Ghi error type và backoff duration.
- Không tạo trace mới cho mỗi attempt trừ khi semantics yêu cầu.
- Không retry vượt deadline hoặc retry budget.
- Với hedged requests, link các attempts và ghi rõ attempt winner/cancelled.

Metrics cần phân biệt logical request với physical attempts. Nếu đếm mọi attempt như một user request, request rate và error ratio có thể bị hiểu sai. Có thể có `requests` ở boundary và `client_attempts` cho outbound riêng.

## 43. Context và sampling trong hệ thống có volume lớn

Một chiến lược có thể là:
- 100% metrics cốt lõi theo service/route/outcome.
- Structured logs cho lỗi và business transitions quan trọng.
- Sampling trace bình thường theo tỷ lệ.
- Tail sampling ưu tiên lỗi, slow spans và critical journeys.
- Audit/security events có pipeline và retention riêng.
- Temporary diagnostic sampling theo service/timebox khi incident.

Đây là ví dụ, không phải tỷ lệ bắt buộc. Đánh giá dựa trên volume, chi phí, nhu cầu điều tra, quy định và khả năng collector.

Khi có một trace sampled out, metric vẫn phải ghi nhận request/error/duration. Không phụ thuộc vào việc có trace mới biết SLO đang vi phạm.

## 44. Observability readiness khi đưa service mới vào production

Trước khi service được coi là production-ready:
- Service name/version/environment resource attributes đúng.
- Inbound/outbound HTTP spans hoạt động.
- Messaging producer/consumer context được kiểm tra nếu có.
- Async executor/reactive context propagation được test.
- Logs có trace/span IDs và không lộ secret.
- Metrics RED/USE/business được định nghĩa.
- Metric labels bounded, route normalized.
- Histogram phù hợp latency SLO.
- Dashboard và alert có owner/runbook.
- Collector/exporter endpoint, TLS/identity và retry/queue đã cấu hình.
- Sampling và retention policy rõ.
- Health/metrics endpoints được bảo vệ.
- Synthetic journey và test exporter có bằng chứng.
- Có dashboard để phát hiện telemetry drop/cardinality spike.
- Version upgrade/rollback của instrumentation được quản lý.

Observability không nên là phần việc “sau khi lên production mới thêm”. Instrumentation phải có trong service template và được kiểm tra trong CI.

## 45. Ví dụ checklist review một trace thực tế

Khi review một trace của `POST /orders`, hỏi:

1. Có server span ở gateway và Order không?
2. Outbound Inventory/Pricing spans có đúng parent không?
3. Span duration có gồm queue/pool wait hay chỉ service execution?
4. Database span có tên/attributes an toàn, không chứa raw SQL/PII?
5. Có event cho retry/timeout/circuit breaker khi cần?
6. Trace có bị duplicate bởi nhiều instrumentation?
7. Span status phản ánh business rejection và technical failure đúng không?
8. Consumer span sau Kafka có quan hệ parent/link phù hợp?
9. Logs có trace ID để mở đúng trace?
10. Metric exemplar có thể dẫn tới trace sample?
11. Sampling có giữ được error/slow path?
12. Baggage chỉ có allowlisted attributes?

Mục tiêu là trace kể được câu chuyện của operation mà không chứa quá nhiều chi tiết không cần thiết.

## 46. Checklist thiết kế và triển khai

- [ ] Phân biệt trace context, correlation ID, request ID và business identifiers.
- [ ] Dùng W3C Trace Context hoặc propagator chuẩn tương thích.
- [ ] Chọn trust policy cho context đến từ public boundary.
- [ ] Baggage có allowlist, size limit và không chứa secret/PII.
- [ ] Service resource attributes có tên/version/environment ổn định.
- [ ] HTTP server/client instrumentation không bị duplicate.
- [ ] RestClient/WebClient dùng builder/integration được quản lý phù hợp.
- [ ] Kafka/RabbitMQ producer inject và consumer extract context.
- [ ] Batch/replay/DLQ dùng parent/link semantics phù hợp.
- [ ] Executor, CompletableFuture và Reactor truyền context qua thread boundary.
- [ ] MDC chỉ phục vụ log; không thay tracing context API.
- [ ] Logs structured có trace/span IDs và redaction.
- [ ] Metrics RED/USE và business metrics có semantics rõ.
- [ ] Labels bounded; không có request/user/order/trace IDs.
- [ ] Histogram buckets bao phủ SLO threshold.
- [ ] Exemplars liên kết metric với trace khi backend hỗ trợ.
- [ ] Sampling không làm sai SLI/SLO.
- [ ] Collector có memory limits, queue/backpressure và dropped telemetry metrics.
- [ ] Dashboard theo service, dependency và user journey.
- [ ] Alert actionable, có owner/runbook.
- [ ] Context propagation, metric cardinality và privacy được test trong CI.
- [ ] Instrumentation version/semantic conventions có kế hoạch nâng cấp.

## 47. Câu hỏi thường gặp

**Trace ID có cần giống nhau trên mọi service không?**

Trong một distributed trace được propagate đúng, trace ID thường giữ nguyên qua các span liên quan. Span ID thay đổi theo operation. Một workflow dài hoặc replay có thể tạo trace mới và dùng correlation ID/span link để liên hệ.

**Có nên tự truyền trace ID bằng HTTP header riêng?**

Ưu tiên W3C `traceparent`/`tracestate` và instrumentation chuẩn. Header riêng có thể phục vụ correlation nghiệp vụ nhưng không thay distributed tracing protocol.

**MDC có đủ để propagate trace qua CompletableFuture không?**

Không. MDC chủ yếu là context cho logging và thường gắn với thread. Dùng Micrometer/OTel context propagation để giữ trace context; kiểm tra MDC bridge để log không bị thiếu hoặc lẫn.

**Có nên thêm order ID vào metric tag?**

Không. Giá trị này tạo high cardinality. Dùng trace/log có access control để điều tra một order; metrics dùng route, service, outcome và dimensions có giới hạn.

**Bật sampling 10% có làm mất 90% request khỏi SLO?**

Không nếu metrics được ghi độc lập cho toàn bộ traffic. Sampling chỉ áp dụng cho traces; không dùng sampled traces làm mẫu duy nhất để tính request success/latency SLO nếu không có phương pháp thống kê phù hợp.

**Một trace qua Kafka có phải giữ cùng parent span mãi mãi?**

Không bắt buộc. Consumer có thể tiếp tục context hoặc dùng span link, đặc biệt với batch, replay và workflow bất đồng bộ kéo dài. Chọn theo causality và lifecycle thực.

**Vì sao log có trace ID nhưng trace backend không thấy span?**

Có thể span bị sampling out, exporter lỗi, collector drop, backend retention/query filter hoặc log MDC được set thủ công mà không có span thật. Kiểm tra propagation, sampled flag, exporter và collector metrics.

**Vì sao có nhiều trace cho một request?**

Có thể header bị mất, client instrumentation không hoạt động, service tạo root span mới hoặc trust policy chủ động cắt trace. Cũng có thể retry/async workflow tạo trace mới có chủ ý. Kiểm tra outbound headers và parent relationships.

**Metric p95 của service có bằng p95 của journey không?**

Không. Journey có thể đi qua nhiều service, nhánh song song, network, queue và UI. Đo end-to-end SLI riêng, dùng trace critical path để phân tích nguyên nhân.

**Có cần instrument mọi method Java không?**

Không. Instrument boundary và business operation có giá trị. Quá nhiều span tạo noise và cost, khiến critical path khó hiểu.

**OpenTelemetry Agent hay manual instrumentation tốt hơn?**

Agent giảm công sức cho thư viện phổ biến; manual instrumentation hữu ích cho business operations và các boundary chưa được hỗ trợ. Có thể kết hợp nhưng phải tránh duplicate và pin version.

**Có thể gửi baggage chứa tenant ID để mọi service filter không?**

Chỉ khi có lý do, policy và kiểm soát cardinality/privacy. Baggage không phải cơ chế authorization. Thường nên truyền tenant context đã xác thực qua security/application contract và chỉ expose dạng đã giảm định danh cho observability.

**Khi nào cần tạo trace mới cho async job?**

Khi workflow tách rời về thời gian, replay hoặc được kích hoạt từ nhiều nguồn. Dùng correlation ID/business event ID và span links để nối causal history thay vì giữ một trace mở quá lâu.

---

**Nguyên lý ghi nhớ:** *Truyền observability context bằng chuẩn và instrumentation nhất quán qua HTTP, broker và async boundaries; dùng trace để hiểu một execution, log để ghi sự kiện có ngữ cảnh, metric để đo phân bố và SLO theo service. Giữ metric dimensions hữu hạn, baggage an toàn, MDC đúng lifecycle và kiểm thử propagation ở boundary thật để trace không đứt, log không lẫn và dashboard không bị cardinality bùng nổ.*
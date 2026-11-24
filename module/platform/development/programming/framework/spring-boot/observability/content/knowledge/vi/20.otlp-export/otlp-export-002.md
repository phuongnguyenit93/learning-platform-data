# OTLP traces: xuất distributed traces từ Spring Boot

Một ứng dụng Spring Boot có thể tạo Observation và span cho HTTP request, nhưng đội vận hành vẫn không tìm thấy trace trong backend. Khoảng cách nằm giữa **tạo span** và **xuất span**: tracing SDK phải ghi nhận span, xử lý sampling, gom batch, gửi qua OTLP, Collector phải nhận và chuyển tiếp, cuối cùng backend mới lưu và cho phép truy vấn.

**OTLP (OpenTelemetry Protocol)** là giao thức truyền telemetry của OpenTelemetry. **OTLP traces** là signal dùng để chuyển dữ liệu trace gồm Resource, instrumentation scope và spans. Với Spring Boot, Micrometer Observation và Micrometer Tracing có thể tạo span; OpenTelemetry bridge/SDK và OTLP exporter đảm nhiệm phần export theo cấu hình.

Bài thuộc chương **OTLP export** của module **SPRING_BOOT_OBSERVABILITY**: thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing, bao gồm propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng thực tế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả cấu trúc trace data và đường đi từ Observation tới OTLP receiver/backend.
2. Phân biệt OTLP/HTTP với OTLP/gRPC, endpoint và port thường dùng.
3. Cấu hình Spring Boot/Micrometer Tracing để xuất spans bằng OpenTelemetry OTLP exporter.
4. Dựng OpenTelemetry Collector nhận trace data, batch và chuyển tiếp tới backend.
5. Hiểu SpanProcessor, batch queue, timeout, retry, graceful shutdown và rủi ro mất spans.
6. Phân biệt export với trace context propagation, sampling và metric/log exporters.
7. Kiểm thử Resource, span hierarchy và OTLP transport theo từng tầng.
8. Bảo vệ telemetry, kiểm soát cardinality và vận hành pipeline traces trong production.

## 1. OTLP traces là gì?

Một **trace** biểu diễn đường đi của request hoặc công việc qua một hay nhiều thành phần. Trace chứa một hoặc nhiều **spans**; mỗi span mô tả một thao tác với thời điểm bắt đầu/kết thúc, span context, parent relationship, attributes, events và status. Khi export, spans được đóng gói cùng **Resource** và **Instrumentation Scope** trong OTLP trace signal.

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Trace ID | Định danh chung của trace | Một request tạo đơn |
| Span ID | Định danh một thao tác | HTTP server span |
| Parent Span ID | Span cha trực tiếp | HTTP client span gọi downstream |
| Span name/kind | Tên và vai trò thao tác | POST /orders, SERVER |
| Attributes | Metadata của thao tác | http.request.method=POST |
| Events | Mốc sự kiện trong span | Exception event |
| Status | Kết quả span | OK, ERROR hoặc UNSET |
| Resource | Nguồn phát telemetry | service.name=order-service |
| Instrumentation Scope | Thư viện tạo telemetry | Spring Web instrumentation |

Một trace nhiều service có thể chứa spans có Resource khác nhau: order-service phát spans của mình, inventory-service phát spans của mình. Trace ID và parent relationship liên kết chúng; Resource xác định nguồn tạo từng span.

### 1.1. Kiến trúc OTLP export

~~~mermaid
flowchart LR
    App["Spring Boot application"] --> Obs["Micrometer Observation"]
    Obs --> Bridge["Micrometer Tracing bridge"]
    Bridge --> SDK["OpenTelemetry SDK / TracerProvider"]
    SDK --> Processor["SpanProcessor / batch queue"]
    Processor --> Exporter["OTLP traces exporter"]
    Exporter --> Receiver["OTel Collector receiver"]
    Receiver --> Pipeline["Collector processors"]
    Pipeline --> BackendExporter["Collector exporter"]
    BackendExporter --> Backend["Trace backend"]
    Obs --> Metrics["Metrics handler"]
    Metrics --> MetricsBackend["Metrics registry/backend"]
    App --> Logs["Application logs"]
    Logs --> LogBackend["Log backend"]
~~~

**Có span trong code không đồng nghĩa có trace trong backend.** Từng chặng cần được cấu hình và xác minh độc lập.

OTLP có thể vận chuyển traces, metrics và logs; mỗi signal có data model, exporter và endpoint riêng. OTLP trace exporter không tự xuất Prometheus metrics hoặc Logback events. Dù cùng đến Collector, ba pipeline vẫn cần receivers/processors/exporters phù hợp.

## 2. OTLP trace data và cấu trúc export

Trong OpenTelemetry Protocol, trace data thường được biểu diễn qua cấu trúc:

~~~text
ExportTraceServiceRequest
└─ ResourceSpans
   ├─ Resource
   │  ├─ service.name
   │  ├─ service.version
   │  └─ deployment.environment.name
   └─ ScopeSpans
      ├─ InstrumentationScope
      │  ├─ name
      │  └─ version
      └─ Spans
         ├─ trace_id
         ├─ span_id
         ├─ parent_span_id
         ├─ name / kind
         ├─ start_time / end_time
         ├─ attributes
         ├─ events
         └─ status
~~~

Đây là cấu trúc khái niệm; wire format thực tế được định nghĩa bằng Protocol Buffers. OTLP receiver giải mã request theo protocol, không đọc một JSON tùy ý với các field tương tự.

- **ResourceSpans** nhóm các spans theo Resource tạo ra chúng.
- **Resource** chứa service.name, service.version, environment và metadata runtime.
- **ScopeSpans** nhóm spans theo instrumentation scope.
- **Span** mang trace/span IDs, parent, thời gian, attributes, events và status.

Resource cho biết nguồn phát telemetry; instrumentation scope cho biết thư viện tạo telemetry. Một process order-service có thể phát spans từ Spring Web instrumentation và một thư viện nội bộ: scope khác nhau nhưng Resource có thể chung.

Không đưa password, token, cookie, email, request body hoặc dữ liệu thanh toán vào span attributes. High-cardinality attributes làm tăng kích thước traces và chi phí indexing; không copy mọi baggage fields vào mọi span.

## 3. OTLP/HTTP và OTLP/gRPC

OTLP hỗ trợ truyền qua HTTP và gRPC. Các port mặc định thông dụng của OpenTelemetry Collector:

| Thuộc tính | OTLP/HTTP | OTLP/gRPC |
| --- | --- | --- |
| Port mặc định | 4318 | 4317 |
| Transport | HTTP | gRPC trên HTTP/2 |
| Trace endpoint | /v1/traces | gRPC service/method |
| Payload phổ biến | Protobuf (application/x-protobuf) | Protobuf |
| Metrics endpoint | /v1/metrics | gRPC service/method |
| Logs endpoint | /v1/logs | gRPC service/method |

### 3.1. OTLP/HTTP

Endpoint traces mặc định theo giao thức thường là:

~~~text
http://collector:4318/v1/traces
~~~

Exporter gửi HTTP POST chứa protobuf payload. Request minh họa:

~~~http
POST /v1/traces HTTP/1.1
Host: collector:4318
Content-Type: application/x-protobuf

<binary ExportTraceServiceRequest>
~~~

Đây là minh họa giao thức, không phải request copy-paste chạy được bằng curl. Body phải là protobuf hợp lệ hoặc định dạng khác được receiver hỗ trợ theo OTLP specification.

### 3.2. OTLP/gRPC

Với OTLP/gRPC, exporter gọi gRPC service trên HTTP/2, thường tới port 4317. Không nối /v1/traces vào URL gRPC như một HTTP path. Client và receiver phải tương thích gRPC/HTTP2, TLS và proxy.

Chọn HTTP hay gRPC dựa trên hạ tầng: proxy/load balancer, service mesh, xác thực, TLS và khả năng quan sát của tổ chức. Không giả định port mặc định luôn mở; deployment có thể thay đổi.

## 4. Cấu hình Spring Boot gửi OTLP traces

Ví dụ phụ thuộc Gradle cho Spring Boot 3.x với Micrometer Tracing bridge OpenTelemetry:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Vai trò:
- Actuator cung cấp tích hợp observability của Spring Boot.
- Micrometer Tracing bridge kết nối Micrometer với OpenTelemetry.
- OTLP exporter cung cấp cơ chế gửi telemetry.
- Prometheus registry (nếu dùng) phục vụ metrics, không thay tracing exporter.

Giữ versions theo Spring Boot BOM. Không cố định độc lập các phiên bản Micrometer, OpenTelemetry API/SDK/exporter nếu chưa kiểm tra tương thích.

### 4.1. Cấu hình endpoint OTLP/HTTP

Ví dụ application.yml trên cấu hình Spring Boot 3.x hỗ trợ OTLP tracing auto-configuration:

~~~yaml
spring:
  application:
    name: order-service
management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Xác nhận property endpoint theo version thực tế. probability là sampling head-based của cấu hình tích hợp, không phải tail sampling ở Collector.

### 4.2. Cấu hình theo môi trường

Không hard-code localhost khi triển khai với container riêng. Dùng biến môi trường:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT:http://localhost:4318/v1/traces}
~~~

Ví dụ DNS Service của Collector trên Kubernetes:

~~~text
OTLP_TRACES_ENDPOINT=http://otel-collector.observability.svc.cluster.local:4318/v1/traces
~~~

Tên Service chỉ minh họa. Phải dùng host, namespace, port và scheme thực tế. Từ góc nhìn container ứng dụng, localhost chỉ trỏ về chính container/network namespace đó.

### 4.3. Resource identity

Có thể dùng biến môi trường chuẩn OpenTelemetry SDK Autoconfigure khi tracing stack hỗ trợ:

~~~text
OTEL_SERVICE_NAME=order-service
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,service.version=2.4.1,deployment.environment.name=staging
~~~

Các biến này cấu hình Resource identity, không phải span attributes. Xác minh SDK/auto-configuration mà Spring Boot thực sự sử dụng có đọc các biến chuẩn đó không; không phải mọi cơ chế cấu hình provider đều tự dùng SDK Autoconfigure.

### 4.4. Headers và TLS

Khi Collector hoặc gateway yêu cầu xác thực, exporter cần gửi headers và kết nối TLS phù hợp. Cách cấu hình headers phụ thuộc Spring Boot/OpenTelemetry version và exporter implementation. Ví dụ định hướng cho phiên bản có hỗ trợ property headers:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT}
      headers:
        Authorization: ${OTLP_AUTH_HEADER}
~~~

Kiểm tra property binding của đúng version trước khi dùng production. Credentials phải lấy từ secret manager hoặc môi trường được bảo vệ; không commit token vào YAML. Dùng HTTPS/TLS, CA đúng và hostname verification.

## 5. OpenTelemetry Collector: nhận và chuyển tiếp traces

Collector là trung gian giữa ứng dụng và backend. Nó có thể nhận OTLP, batch, lọc theo policy và export sang nơi lưu traces.

### 5.1. Cấu hình Collector thử nghiệm

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318
processors:
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
  batch:
    timeout: 5s
exporters:
  debug:
    verbosity: basic
service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [debug]
~~~

Collector có hỗ trợ components này sẽ nhận OTLP HTTP trên 4318 và log dữ liệu qua debug exporter. Đây là cấu hình học tập; không dùng debug detailed trên production vì spans có thể chứa dữ liệu nhạy cảm và gây log volume lớn.

### 5.2. Cấu hình pipeline backend

Khi chuyển production, dùng exporter thực tế tới trace backend, đồng thời thiết lập auth, TLS, queue/retry và policy. Fragment minh họa Collector version hỗ trợ otlphttp exporter và env expansion:

~~~yaml
exporters:
  otlphttp/backend:
    endpoint: https://trace-backend.example.internal
    headers:
      Authorization: ${env:TRACE_BACKEND_TOKEN}
~~~

Trong cấu hình hoàn chỉnh, cần khai báo receiver/processor tại phần tương ứng, nối exporter trong service.pipelines.traces và kiểm tra exporter options của Collector distribution. Hostname trên chỉ là ví dụ.

### 5.3. Receiver phải được nối vào pipeline

Chỉ khai báo receivers.otlp chưa đủ. service.pipelines.traces phải tham chiếu receiver, processors và exporters. Nếu pipeline không được nối, cổng có thể mở nhưng trace data không tới đích mong muốn.

Trong Docker/Kubernetes, receiver phải listen trên interface có thể truy cập; container networking, port mapping, DNS, network policy và firewall phải đúng. Không dùng localhost cho Collector ở container khác. Kiểm tra readiness, health và tài nguyên Collector.

## 6. SpanProcessor, batching và lifecycle export

Span kết thúc không nhất thiết được gửi ngay. **SpanProcessor** nhận callback lifecycle span và điều phối cách xử lý:

- **SimpleSpanProcessor:** gửi span trực tiếp khi kết thúc; hữu ích cho test/ít traffic nhưng có overhead đồng bộ.
- **BatchSpanProcessor:** gom spans vào queue/batch và export bất đồng bộ; thường phù hợp hơn cho production.

~~~mermaid
flowchart TD
    Span["Span ends"] --> Processor["SpanProcessor"]
    Processor --> Queue["Batch queue"]
    Queue --> Ready{"Batch size / timer / shutdown"}
    Ready --> Export["OTLP exporter"]
    Export --> Receiver["Collector"]
    Receiver --> Result{"Accepted?"}
    Result -- "Yes" --> Done["Batch completed"]
    Result -- "Transient error" --> Retry["Retry theo policy"]
    Retry --> Export
    Result -- "Queue full / permanent error" --> Drop["Có thể drop spans"]
~~~

| Tham số | Tác động | Trade-off |
| --- | --- | --- |
| Queue capacity | Số spans chờ export | Cao hơn dùng thêm RAM; thấp dễ drop khi nghẽn |
| Max export batch size | Số spans trong một batch | Batch lớn giảm request count nhưng tăng payload |
| Schedule delay | Thời gian chờ flush | Ngắn giảm latency, tăng overhead |
| Export timeout | Giới hạn thời gian exporter chờ | Quá ngắn có thể fail khi mạng chậm |
| Retry/backoff | Thử lại lỗi tạm thời | Có thể tăng tải, không bảo đảm giao hàng |
| Collector batch timeout/size | Gom dữ liệu trước backend | Tăng throughput, thêm độ trễ |
| Shutdown timeout | Thời gian flush khi dừng | Dài hơn giúp flush nhưng kéo dài shutdown |

Tên property và cách cấu hình BatchSpanProcessor phụ thuộc OpenTelemetry SDK/version và Spring Boot auto-configuration. Không tự đặt property không được hỗ trợ.

### 6.1. Graceful shutdown

Khi ứng dụng dừng, spans trong queue có thể mất nếu process bị force-kill hoặc thời gian shutdown không đủ. Cho ứng dụng thời gian graceful shutdown, để SDK/span processor flush trong timeout hỗ trợ, kiểm tra exporter errors trong rolling update và hiểu rằng queue trong RAM không phải durable storage.

Không gọi flush đồng bộ trong mọi request để “bảo đảm” trace đã lưu; việc đó có thể làm latency người dùng phụ thuộc Collector/backend.

## 7. Sampling và trace completeness

Sampling chọn trace nào được ghi nhận/export. Spring Boot có thể cấu hình xác suất head sampling:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.10
~~~

Với head-based sampling, quyết định thường được đưa ra sớm khi trace bắt đầu. Nếu request phát sinh lỗi sau vài giây nhưng đã bị drop từ đầu, OTLP exporter không có trace hoàn chỉnh để gửi chỉ vì response cuối cùng là 500.

**Parent-based sampling** sử dụng sampling decision từ parent/remote parent làm cơ sở cho child, giúp các service duy trì tính nhất quán. W3C traceparent mang Trace ID, Parent ID và trace flags. Sampling không giống baggage.

**Tail sampling** có thể chờ spans tới Collector rồi giữ trace dựa trên status ERROR, latency cao hoặc policy khác. Nó cần SDK gửi đủ spans, routing các spans cùng trace tới cùng decision point, Collector buffer/memory phù hợp và attributes/status được instrumentation ghi đúng. Nếu SDK đã drop trace, Collector không thể phục hồi spans chưa export.

Tập traces đã sampling, đặc biệt tail sampling ưu tiên lỗi, không phải mẫu số mặc định để tính error rate. Dùng HTTP metrics/counters/histograms cho request rate, error ratio, p95/p99 và SLO; dùng traces đã sampling để điều tra request cụ thể.

## 8. Export và propagation giữa các service

Export OTLP là gửi span data ra Collector. **Propagation** là truyền trace context trong request để service downstream tiếp tục cùng trace. Hai hoạt động phải được cấu hình riêng.

~~~mermaid
sequenceDiagram
    participant Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Collector
    participant Backend
    Client->>Order: POST /orders
    Note over Order: Server span A
    Order->>Inventory: HTTP + traceparent
    Note over Inventory: Server span B, child of HTTP client span
    Inventory-->>Order: Response
    Order-->>Client: Response
    Order->>Collector: OTLP export spans của order
    Inventory->>Collector: OTLP export spans của inventory
    Collector->>Backend: Chuyển tiếp trace data
~~~

Một traceparent W3C minh họa:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Service nhận dùng propagator để extract context. Nếu HTTP client/server được instrument phù hợp, CLIENT span và SERVER span có thể cùng Trace ID, Parent Span ID đúng. Backend nối spans từ dữ liệu export của mỗi service.

Khi chuyển thread qua @Async/Executor hoặc đi qua Reactor, context cần được capture/restore. Với Kafka/RabbitMQ, producer/consumer instrumentation cần inject/extract context trong headers. OTLP exporter không tự nối parent-child nếu context đã bị mất; nó chỉ xuất những span được tạo ra.

Trace context được chia sẻ nhưng Resource không sao chép từ upstream. Span do inventory-service tạo phải gắn Resource của inventory-service, ví dụ service.name=inventory-service.

## 9. Kiểm thử OTLP traces

Nên kiểm thử từng tầng để tránh nhầm “Observation đã chạy” với “trace đã tới backend”.

| Tầng | Cách kiểm tra | Bằng chứng |
| --- | --- | --- |
| Observation | TestObservationRegistry | Tên, tags, lifecycle, lỗi |
| Tracing SDK | In-memory span exporter/test handler | Trace ID, span ID, parent ID |
| OTLP transport | Receiver test hiểu OTLP protobuf | HTTP/gRPC request và payload hợp lệ |
| Collector | OTLP receiver + debug exporter | Collector đã nhận spans |
| Backend | Truy vấn trace theo ID/service | Dữ liệu đã ingest và tìm được |
| Cross-service | Hai service có instrumentation | Quan hệ parent-child và Resource riêng |

### 9.1. Observation unit test không chứng minh export

Test dùng TestObservationRegistry có thể chứng minh Observation được tạo, có tên/tag và dừng đúng. Nó không gửi request OTLP. Test tạo Resource object không chứng minh Spring Boot provider đã dùng Resource đó.

### 9.2. Kiểm thử span hierarchy trong bộ nhớ

Với OpenTelemetry SDK test setup và in-memory exporter:

1. Cấu hình sampler giữ span trong test.
2. Tạo parent span và child span trong scope của parent.
3. Kết thúc cả hai spans.
4. Thu spans qua in-memory exporter.
5. Assert cùng Trace ID, khác Span ID và child.parentSpanId == parent.spanId.
6. Kiểm tra tên, Resource, attributes và error status.

Đây là tracing SDK test, chưa xác minh OTLP network transport.

### 9.3. OTLP HTTP smoke test

1. Khởi động Collector với OTLP HTTP receiver port 4318 và debug exporter.
2. Cấu hình endpoint ứng dụng tới /v1/traces.
3. Khởi động Spring Boot có tracing bridge/exporter và sampling phù hợp test.
4. Gửi request HTTP tạo spans.
5. Đợi batch processor flush.
6. Kiểm tra Collector logs/resource/spans.
7. Nếu có backend test, truy vấn Trace ID và xác nhận spans.

Không dùng GET /v1/traces hoặc JSON tùy ý để kết luận exporter hoạt động. Receiver cần request và payload đúng theo OTLP.

### 9.4. Kiểm thử lỗi export

Trong môi trường test, dừng Collector để tạo connection failure; khởi động lại và quan sát retry/queue behavior theo SDK version; gửi payload sai qua receiver giả lập để kiểm tra lỗi protocol; kiểm tra graceful shutdown khi còn batch đang chờ. Không khẳng định không mất spans chỉ dựa trên một lần Collector hoạt động lại.

## 10. Bảo mật và vận hành pipeline

Trace data có thể chứa URL, dependency information, exception message, SQL metadata và business attributes. Khi export, dữ liệu đi qua network và nhiều hệ thống lưu trữ.

| Rủi ro | Kiểm soát |
| --- | --- |
| Token/PII trong span attributes | Allowlist attributes, redaction, test payload |
| Collector receiver bị truy cập công khai | Private network, firewall, auth |
| OTLP traffic không mã hóa | TLS/HTTPS hoặc transport bảo vệ tương đương |
| Backend token bị lộ | Secret manager, rotate khi cần, không log |
| High-cardinality attributes | Hạn chế ID động, kích thước và indexing |
| Collector quá tải | Memory limiter, batch sizing, queue/scale |
| Trace data lưu quá lâu | Retention, access control, data governance |
| Debug exporter log quá nhiều | Chỉ dùng trong môi trường thử nghiệm |

Giữ Resource ổn định: service.name, service.version, environment và instance identity cần có ý nghĩa. Span attributes nên mô tả thao tác; không đưa email, password, access token, request body hoặc dữ liệu thanh toán vào traces. Không copy toàn bộ baggage thành span attributes mà chưa review.

Trace IDs có cardinality gần như một giá trị mỗi trace. Dùng chúng làm metric labels sẽ tạo rất nhiều time series. Nếu backend hỗ trợ exemplars, dùng exemplar để liên kết metric sample với trace mà không tạo nhãn trace ID cho mọi series.

Theo dõi export requests/errors, retry, timeout, dropped spans, queue occupancy, batch latency, Collector accepted/refused spans, exporter failure từ Collector tới backend và backend ingestion latency. Tên metrics cụ thể phụ thuộc SDK/Collector version.

## 11. Troubleshooting OTLP traces

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không có trace ở backend | Tracing bridge/SDK chưa tạo spans hoặc sampler drop | Kiểm tra Observation, tracer và sampling |
| Connection refused port 4318 | Collector không listen hoặc sai địa chỉ container | Kiểm tra endpoint từ process ứng dụng và receiver |
| HTTP 404 | Sai path hoặc request tới nhầm server | Kiểm tra /v1/traces, proxy routing |
| HTTP 400 | Payload/content type/protocol không hợp lệ | Xem OTLP exporter, receiver logs |
| HTTP 401/403 | Auth/tenant policy sai | Kiểm tra header/secret/quyền |
| HTTP 429 | Quota hoặc receiver quá tải | Giảm traffic/sampling, tăng capacity theo policy |
| HTTP 5xx | Collector/proxy/backend lỗi | Kiểm tra pipeline health, resource và retry |
| TLS handshake lỗi | Certificate/CA/hostname/scheme không đúng | Kiểm tra TLS trust chain và endpoint |
| Collector nhận spans nhưng backend trống | Thiếu pipeline exporter hoặc export downstream fail | Kiểm tra service.pipelines.traces |
| Trace bị tách giữa services | Propagation mất hoặc protocol/header không khớp | Kiểm tra traceparent, client/server instrumentation |
| Trace chỉ có một nhánh | Một service chưa export hoặc bị sampling/drop | So sánh Resource service.name ở Collector |
| Trace xuất hiện trễ | Batch schedule hoặc Collector processor wait | Kiểm tra batch/decision window |
| Một số spans mất khi shutdown | Queue chưa flush hoặc process bị force-kill | Kiểm tra graceful shutdown và drop metrics |
| unknown_service | Resource service.name thiếu | Kiểm tra SDK Resource configuration |

### 11.1. Trình tự điều tra

1. **Instrumentation:** request có thực sự tạo Observation/span không?
2. **Sampling:** span có được recording theo sampler không?
3. **SpanProcessor:** batch queue có nhận span và có bị đầy không?
4. **Exporter:** endpoint, protocol, path, TLS và authentication có đúng không?
5. **Collector:** receiver nhận request? traces pipeline có nối processor/exporter?
6. **Backend:** ingest, tenant, indexing, retention và query có đúng không?
7. **Propagation:** nếu trace không liền mạch, kiểm tra context riêng, không đổ lỗi cho exporter.

OTLP receiver trả 503 là lỗi telemetry pipeline; inventory-service trả 503 là lỗi dependency nghiệp vụ. Không tính lỗi export vào error rate của người dùng nếu nó không làm request nghiệp vụ thất bại. Tuy nhiên, exporter lỗi liên tục vẫn là vấn đề vận hành cần cảnh báo.

## 12. Production checklist

| Tiêu chí | Bằng chứng |
| --- | --- |
| Dependency tương thích | Spring Boot BOM, Micrometer Tracing bridge và OTel exporter |
| Đúng transport | OTLP/HTTP hoặc OTLP/gRPC được thống nhất |
| Endpoint hợp lệ | Host/port/path theo receiver thật |
| Resource đúng | service.name/version/environment/instance |
| Collector pipeline hoạt động | Receiver, processors, exporter được nối |
| TLS/auth bảo vệ | Credentials và trust chain an toàn |
| Sampling phù hợp | Có ngân sách và hiểu head/tail behavior |
| Batch/queue sizing | Kiểm thử peak, timeout và shutdown |
| Propagation được test | Spans giữa service cùng trace ID/parent relationship |
| Attribute an toàn | Không PII/secrets, cardinality được kiểm soát |
| Exporter health được giám sát | Errors, retries, drops, queue, ingest |
| Backend giữ và tìm được trace | Truy vấn staging/production phù hợp quyền |
| Metrics và logs liên kết đúng | SLI lấy từ metrics; trace ID correlation |
| Graceful shutdown | Có cơ hội flush theo timeout |
| Upgrade có regression tests | Kiểm tra property/protocol/semantic conventions |

## 13. Bài thực hành: xuất trace end-to-end

**Bối cảnh:** hệ thống có order-service gọi inventory-service. Cả hai chạy Spring Boot và cần gửi traces qua một OpenTelemetry Collector tới trace backend.

**Nhiệm vụ:**

1. Thêm Actuator, micrometer-tracing-bridge-otel và OTLP exporter theo BOM của dự án.
2. Cấu hình service.name, service.version, environment và endpoint OTLP đúng transport.
3. Chạy Collector OTLP receiver trên HTTP 4318 hoặc gRPC 4317 và khai báo service.pipelines.traces.
4. Bật sampling 100% trong môi trường thử nghiệm, gọi endpoint tạo đơn vài lần.
5. Tạo custom Observation cho thao tác nghiệp vụ; dùng HTTP client được instrument tới inventory-service.
6. Kiểm tra Collector nhận spans từ cả hai Resource service riêng và trace ID/parent relationship phù hợp.
7. Chuyển debug exporter sang backend test, xác minh có thể tìm trace bằng Trace ID.
8. Cố tình đổi HTTP endpoint sang port gRPC, sau đó sửa và ghi nhận dấu hiệu lỗi transport.
9. Dừng Collector khi ứng dụng đang có traffic, quan sát exporter errors/queue/retry và phục hồi.
10. Giảm sampling xuống 10%, so sánh số traces với metrics request/error vẫn đo theo instrumentation.
11. Thêm test Observation, tracing SDK và smoke test Collector; nêu rõ mỗi test chứng minh tầng nào.
12. Viết runbook cho trường hợp metrics/logs có dữ liệu nhưng traces không xuất hiện.

**Kết quả mong đợi:** cấu hình Spring Boot, Collector pipeline, trace có spans từ hai service, bằng chứng Resource/parent-child, test theo tầng và runbook về endpoint, sampling, queue, exporter errors và backend ingest.

## 14. Ghi nhớ

**OTLP traces** là cách chuyển trace data của OpenTelemetry từ ứng dụng tới Collector hoặc backend. Trong Spring Boot, Micrometer Observation và Tracing bridge tạo/quản lý spans; OpenTelemetry SDK và SpanProcessor xử lý sampling/batching; OTLP exporter gửi dữ liệu theo HTTP hoặc gRPC; Collector nhận, xử lý và chuyển tiếp tới trace storage.

Export khác propagation: traceparent nối context khi request đi qua services, còn OTLP chuyển spans ra khỏi process. Muốn trace đầy đủ, cần đúng Resource, span hierarchy, sampling, transport, endpoint, Collector pipeline và backend ingestion. Dùng metrics cho xu hướng/SLO, logs cho sự kiện và trace samples cho điều tra; bảo vệ attributes và giám sát chính pipeline telemetry.

**Tài liệu tham khảo:**

- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/)
- [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/)
- [OpenTelemetry — SDK Trace](https://opentelemetry.io/docs/specs/otel/trace/sdk/)
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)


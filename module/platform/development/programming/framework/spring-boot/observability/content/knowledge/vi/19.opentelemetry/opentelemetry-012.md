# Micrometer và OpenTelemetry: kết hợp instrumentation trong Spring Boot

> **Chương:** OpenTelemetry  
> **Bài:** Micrometer và OpenTelemetry  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Hai dự án giải quyết những phần nào của observability?

Trong một ứng dụng Spring Boot, nhóm phát triển cần đo thời gian xử lý HTTP, đếm số đơn hàng, theo dõi lời gọi database và kết nối trace qua nhiều dịch vụ. Micrometer và OpenTelemetry thường xuất hiện trong cùng một kiến trúc, nhưng không phải hai tên gọi cho cùng một thư viện.

**Micrometer** cung cấp instrumentation facade cho Java, các API metrics và Observation, cùng hệ sinh thái registry để xuất metrics đến nhiều backend. **OpenTelemetry (OTel)** định nghĩa chuẩn và cung cấp API/SDK để tạo, xử lý và xuất telemetry như traces, metrics và logs. Hai hệ sinh thái có thể tích hợp với nhau qua bridge và exporter.

Trong Spring Boot, cách nghĩ hữu ích là:

- Micrometer Observation cung cấp một abstraction để mô tả một hoạt động được quan sát.
- Observation handlers có thể chuyển một Observation thành một hoặc nhiều signal, ví dụ meter và span.
- Micrometer Tracing cung cấp API tracing thống nhất, có thể nối với implementation như Brave hoặc OpenTelemetry.
- OpenTelemetry API/SDK cung cấp mô hình tracing/metrics/logging theo chuẩn OTel và các processor/exporter tương ứng.
- Exporter và registry quyết định dữ liệu được vận chuyển tới backend nào.

~~~mermaid
flowchart TD
  A["Spring Boot application"] --> B["Micrometer Observation"]
  B --> C["Observation handlers"]
  C --> D["Micrometer meters / MeterRegistry"]
  C --> E["Micrometer Tracing API"]
  E --> F["Brave bridge hoặc OpenTelemetry bridge"]
  F --> G["Tracer / Span processor"]
  G --> H["OTLP hoặc Zipkin exporter"]
  D --> I["Prometheus / OTLP / vendor metrics"]
  H --> J["Collector / tracing backend"]
  I --> K["Metrics backend"]
  J --> L["Trace backend"]
  K --> M["Dashboard và alert"]
  L --> M
~~~

Sơ đồ khái quát nhiều khả năng tích hợp. Một ứng dụng không nhất thiết phải cài cùng lúc mọi thành phần. Chọn stack dựa trên backend, instrumentation, yêu cầu chuẩn hóa và chính sách vận hành.

## 2. Micrometer là gì?

Micrometer là một instrumentation library cho JVM, thường được mô tả như facade metrics. Ứng dụng dùng API ổn định để khai báo Counter, Timer, Gauge, DistributionSummary và các loại meter khác; registry cụ thể chuyển số liệu tới backend tương ứng.

Ví dụ:

~~~java
Counter counter = registry.counter(
        "orders.created",
        "channel", "web");
counter.increment();

Timer timer = registry.timer("orders.processing.duration");
timer.record(() -> processOrder());
~~~

Code nghiệp vụ không phải tự tạo request HTTP gửi metrics đến backend. MeterRegistry nhận các phép đo, còn registry/exporter đảm nhận việc đọc/tổng hợp/đẩy số liệu theo semantics của implementation.

Micrometer còn cung cấp **Observation API**. Observation biểu diễn một hoạt động có vòng đời: tạo, start, mở scope, cập nhật context, báo lỗi và stop. Observation handlers có thể chuyển context chung đó thành metrics hoặc tracing.

### 2.1. Meter và Observation khác nhau thế nào?

| Khái niệm | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Meter | Ghi một phép đo hoặc thống kê | Counter số đơn tạo |
| Timer | Đo số lần và thời lượng | Thời gian xử lý thanh toán |
| Observation | Mô tả lifecycle của một hoạt động | Gọi dịch vụ inventory |
| ObservationHandler | Chuyển Observation context thành signal | Metrics handler, tracing handler |
| MeterRegistry | Quản lý và xuất meters | PrometheusMeterRegistry |
| Tracer | Quản lý spans và trace context | Tracer từ Brave/OTel bridge |

Không phải mọi meter đều phải có một span, và không phải mọi span đều tự động tạo một metric theo ý muốn nghiệp vụ. Observation là điểm tích hợp có thể dùng handlers để tạo nhiều signal từ cùng một thao tác.

## 3. OpenTelemetry là gì?

OpenTelemetry là bộ tiêu chuẩn, API, SDK và công cụ cho việc tạo, xử lý, thu thập và export telemetry. Nó định nghĩa các data model và giao thức để instrument ứng dụng đa ngôn ngữ, đưa dữ liệu về một pipeline chung.

Các phần quan trọng:

- **OTel API:** interface dùng trong code để tạo spans, metrics instruments, context và các thành phần tương ứng.
- **OTel SDK:** implementation thực thi recording, sampling, resource, processors và exporters.
- **Instrumentation libraries:** thư viện tự tạo spans/metrics cho framework hoặc client.
- **OTLP:** giao thức truyền telemetry tới Collector hoặc backend hỗ trợ.
- **Collector:** thành phần nhận, xử lý và chuyển tiếp telemetry.
- **Semantic conventions:** quy ước tên attribute và ý nghĩa để dữ liệu thống nhất giữa thư viện/ngôn ngữ.

Ví dụ dùng OpenTelemetry API trực tiếp:

~~~java
Span span = tracer.spanBuilder("orders.create").startSpan();
try (Scope scope = span.makeCurrent()) {
    processOrder();
} catch (RuntimeException ex) {
    span.recordException(ex);
    span.setStatus(StatusCode.ERROR, "order processing failed");
    throw ex;
} finally {
    span.end();
}
~~~

API trên tạo và kết thúc một span. Nếu muốn xuất span ra backend, ứng dụng còn cần SDK/provider, sampler, processor và exporter được cấu hình. Có API trên classpath không đồng nghĩa dữ liệu tự động được ghi và gửi đi.

## 4. So sánh Micrometer và OpenTelemetry

| Tiêu chí | Micrometer | OpenTelemetry |
| --- | --- | --- |
| Trọng tâm ban đầu | Instrumentation metrics và Observation trong JVM | Chuẩn hóa telemetry đa signal và đa ngôn ngữ |
| Abstraction metrics | Counter, Timer, Gauge, MeterRegistry | API Metrics, MeterProvider, Meter, instruments |
| Abstraction lifecycle | Observation và ObservationRegistry | Tracing API/Span, context và instrumentation APIs |
| Tracing trong Spring | Micrometer Tracing facade và bridge | Trace API/SDK, Span, propagator, processor |
| Export | Registry theo backend, OTLP registry và bridge tương ứng | Exporter/OTLP SDK, Collector |
| Resource identity | Registry/bridge mapping tùy integration | Resource model và semantic attributes |
| Tích hợp Spring Boot | Actuator, Observation, Micrometer registries/handlers | Có thể qua Micrometer OTel bridge, OTel agent hoặc SDK |
| Dùng đa ngôn ngữ | API instrumentation Micrometer chủ yếu trong JVM | Chuẩn chung cho nhiều ngôn ngữ và nền tảng |

**Không cần chọn một bên rồi bỏ bên còn lại trong mọi trường hợp.** Trong Spring Boot, Micrometer thường là API instrumentation thuận tiện và tích hợp sâu với framework; OpenTelemetry có thể là chuẩn telemetry và transport thống nhất cho hệ thống lớn hơn.

Tuy nhiên, cần quyết định rõ thành phần nào sở hữu từng ranh giới instrument. Nếu Micrometer Observation và OTel Java Agent cùng tạo span cho một HTTP request, trace có thể xuất hiện các span trùng hoặc waterfall khó hiểu.

## 5. Observation là cầu nối quan trọng trong Spring Boot

Spring Boot Actuator và Micrometer Observation cung cấp một cách mô tả hoạt động chung. Ví dụ một service gọi inventory có thể tạo Observation:

~~~java
Observation.createNotStarted("inventory.reserve", registry)
    .lowCardinalityKeyValue("channel", "web")
    .observe(() -> inventoryClient.reserve());
~~~

Vòng đời observation có thể được mô tả:

~~~mermaid
sequenceDiagram
  participant App as Application
  participant Obs as Observation
  participant MH as Metrics handler
  participant TH as Tracing handler
  App->>Obs: createNotStarted
  App->>Obs: start
  Obs->>MH: onStart
  Obs->>TH: onStart
  App->>Obs: openScope / execute
  Note over App: Business operation
  App->>Obs: error(ex), nếu có
  App->>Obs: stop
  Obs->>MH: onStop
  Obs->>TH: onStop
~~~

Khi handlers tương ứng đã được đăng ký:

- Metrics handler có thể tạo meter hoặc ghi dữ liệu đo từ Observation.
- Tracing handler có thể tạo span, thiết lập current span, thêm attributes và kết thúc span.
- Error callback giúp handler biết operation thất bại.
- Scope cho phép context hiện hành được truy cập trong phạm vi thực thi.

Không tự giả định mỗi Observation đều tạo cả metrics lẫn tracing. Kết quả phụ thuộc handler được đăng ký, predicate/filter, cấu hình và loại context được hỗ trợ.

### 5.1. Low-cardinality và high-cardinality metadata

Observation cho phép gắn metadata theo mục đích:

~~~java
Observation.createNotStarted("orders.create", registry)
    .lowCardinalityKeyValue("channel", "web")
    .highCardinalityKeyValue("order.reference", reference)
    .observe(this::createOrder);
~~~

Low-cardinality values phù hợp với các chiều metrics có tập giá trị hữu hạn. High-cardinality values có thể hữu ích trên trace để tìm một lần thực thi cụ thể, nhưng cần cân nhắc indexing, retention và dữ liệu nhạy cảm.

Không đưa order ID, user ID, email hoặc request ID thành metric label. Gắn high-cardinality metadata vào Observation không có nghĩa mọi handler/backend sẽ xử lý giống nhau; hãy kiểm tra mapping và policy thực tế.

## 6. Micrometer Tracing bridge tới OpenTelemetry

Micrometer Tracing là facade tracing của hệ sinh thái Micrometer. Bridge kết nối facade đó với tracer implementation.

Một lựa chọn trong Spring Boot là OpenTelemetry bridge, thường thông qua dependency:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-otel</artifactId>
</dependency>
~~~

Một lựa chọn khác là Brave bridge:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-brave</artifactId>
</dependency>
~~~

Đây là các lựa chọn thay thế cho tracing implementation trong kiến trúc thông thường. Không thêm cả hai như thể chúng là hai exporter cần thiết để gửi cùng một span.

Với OpenTelemetry bridge, Micrometer Tracing API được nối với OTel tracer. Spring Boot có thể cấu hình tracing integration để Observation tạo spans. Exporter tới Zipkin/OTLP và provider/resource setup phụ thuộc stack cụ thể.

### 6.1. Bridge không đồng nghĩa OTel Java Agent

Bridge là adapter giữa hai API/tracing abstractions. Java agent là cơ chế instrumentation/auto-configuration ở cấp JVM, có thể tự instrument các thư viện được hỗ trợ.

| Thành phần | Vai trò |
| --- | --- |
| Micrometer OTel bridge | Kết nối Micrometer Tracing với OTel tracing implementation |
| OTel Java Agent | Instrumentation và autoconfiguration ở cấp JVM |
| OTel SDK | Tạo provider, sampler, processor và exporter |
| OTLP exporter | Gửi spans/metrics/logs qua OTLP |
| OTel Collector | Nhận, xử lý, route và export telemetry |

Một hệ thống có thể dùng bridge mà không dùng Java agent, hoặc dùng agent mà không thêm Micrometer bridge cho những instrumentation agent đã bao phủ. Cần tránh hai hệ instrumentation cùng bao bọc một operation.

## 7. Các mô hình tích hợp thường gặp

### Mô hình A — Spring Boot và Micrometer, metrics registry

~~~text
Spring Boot
  -> Micrometer MeterRegistry
  -> Prometheus registry
  -> Prometheus scrape
  -> Metrics backend / dashboard
~~~

Phù hợp khi nhu cầu chính là metrics qua Actuator/Prometheus và chưa cần một pipeline OTel thống nhất cho traces/logs.

### Mô hình B — Micrometer Observation/Tracing qua OTel bridge

~~~text
Spring Boot Observation
  -> Micrometer Observation handlers
  -> Micrometer Tracing
  -> OTel bridge
  -> OTel SDK / span processor
  -> OTLP exporter
  -> OTel Collector
  -> Trace backend
~~~

Phù hợp khi ứng dụng muốn dùng Observation API của Spring nhưng xuất tracing theo OpenTelemetry pipeline.

### Mô hình C — OpenTelemetry Java Agent (OTel Java Agent)

~~~text
JVM + OTel Java Agent
  -> supported library instrumentation
  -> OTel SDK
  -> OTLP exporter
  -> OTel Collector
~~~

Phù hợp khi cần auto-instrumentation nhanh cho các thư viện được agent hỗ trợ, nhất là khi không muốn thêm instrumentation thủ công cho mọi client.

### Mô hình D — Kết hợp có chủ đích

Một ứng dụng có thể dùng Micrometer cho metrics và Observation nghiệp vụ, cùng OTel bridge/SDK làm tracing backend. Một số tổ chức cũng dùng agent cho các thư viện chưa có custom instrumentation.

Điều kiện là phải phân công ownership rõ: HTTP server span do framework hay agent tạo? HTTP client span do builder hay agent tạo? Observation nghiệp vụ nào do code tạo? Có exporter nào chịu trách nhiệm xuất? Kiểm tra trace thực tế để loại bỏ duplication.

## 8. Cấu hình Spring Boot với Micrometer và OpenTelemetry

Một ví dụ Maven tối giản cho Spring Boot 3.x dùng Actuator và Micrometer OTel bridge:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-tracing-bridge-otel</artifactId>
    </dependency>
    <dependency>
        <groupId>io.opentelemetry</groupId>
        <artifactId>opentelemetry-exporter-otlp</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ cấu hình:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Đây là ví dụ phụ thuộc Spring Boot 3.x và dependency management tương ứng. Hãy xác minh property names/auto-configuration trên phiên bản thực tế. Các minor versions và lựa chọn exporter có thể khác nhau.

Giải thích:

- Actuator tích hợp management và Observation trong Spring Boot.
- OTel bridge nối Micrometer Tracing với OpenTelemetry tracer.
- OTLP exporter chuyển spans đến endpoint đã cấu hình.
- Sampling probability chọn một phần trace theo policy.
- Service name được quản lý từ Spring/Resource configuration; không giả định exporter tự suy ra chính xác trong mọi cách tích hợp.

Trong môi trường container, localhost có thể không trỏ tới Collector. Sử dụng DNS service đúng network, ví dụ collector:4318.

## 9. Khi nào dùng OTel API trực tiếp?

Không nhất thiết mọi code đều phải dùng OTel API trực tiếp nếu ứng dụng Spring Boot đã chuẩn hóa trên Micrometer Observation. API trực tiếp hữu ích khi:

- Một thư viện nội bộ được thiết kế độc lập với Spring/Micrometer và cần instrumentation OTel.
- Ứng dụng đa ngôn ngữ hoặc cần dùng API chuẩn OTel xuyên nhiều module.
- Một tính năng OTel cụ thể chưa có abstraction tương ứng ở Micrometer.
- Tổ chức đã chọn OTel API làm contract instrumentation cho thư viện dùng chung.

Ví dụ OTel API:

~~~java
Span span = tracer.spanBuilder("inventory.reserve").startSpan();
try (Scope scope = span.makeCurrent()) {
    return reserveInventory();
} catch (RuntimeException ex) {
    span.recordException(ex);
    span.setStatus(StatusCode.ERROR, "inventory reservation failed");
    throw ex;
} finally {
    span.end();
}
~~~

Nếu ứng dụng đang dùng Micrometer Observation cho cùng ranh giới, gọi OTel API trực tiếp để tạo span thứ hai có thể làm trace bị lặp. Chọn một API sở hữu operation đó, hoặc thiết kế bridge/handler rõ ràng để không tạo hai lần instrument.

Đừng trộn ví dụ OTel API trực tiếp với code Brave-specific, vì các lớp và lifecycle khác nhau. Dùng interface tương ứng với implementation thực tế.

## 10. Context propagation giữa Micrometer và OpenTelemetry

Một trace xuyên service yêu cầu trace context được giữ khi thực thi và được inject/extract ở ranh giới transport.

Micrometer Observation/Tracing và OpenTelemetry đều có mô hình context, nhưng bridge chịu trách nhiệm liên kết context theo integration. Không tự quản lý một ThreadLocal riêng để thay thế context propagation của framework.

~~~mermaid
sequenceDiagram
  participant A as order-service
  participant M as Micrometer Observation
  participant B as OTel bridge / context
  participant N as inventory-service
  A->>M: start observation
  M->>B: tạo/current span
  A->>N: HTTP call qua instrumented client
  Note over A,N: Inject trace context headers
  N->>B: Extract context
  B-->>N: server span với parent context
  N-->>A: Response
  A->>M: stop observation
~~~

Khi dùng HTTP client được instrument, outgoing request có thể mang W3C Trace Context hoặc B3 theo propagator. Server nhận phải hỗ trợ extract định dạng tương ứng. Nếu context bị mất khi chuyển thread, child span có thể trở thành root span hoặc bị tách trace.

### 10.1. Async và reactive execution

Context của thread không tự động truyền sang mọi executor. Với CompletableFuture, executor tùy chỉnh hoặc Reactor, dùng cơ chế context propagation được hỗ trợ bởi Spring/Micrometer/OTel integration.

Đảm bảo:

- Context được capture tại nơi submit tác vụ.
- Context được restore trong callback/worker.
- Scope được đóng đúng thread và đúng lifecycle.
- Observation/span chỉ stop khi công việc thực sự hoàn tất.
- Không mở một scope trên thread A rồi đóng trên thread B.

Kiểm tra bằng trace ID, parent span ID và thời lượng. Một log có trace ID không tự chứng minh downstream HTTP request đã propagate đúng.

## 11. Resource và service identity

OpenTelemetry Resource mô tả thực thể tạo telemetry. Một resource thường có attributes như:

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = production
service.instance.id = pod-7f9c
~~~

Micrometer và Spring Boot có thể cung cấp service identity cho các instrumentation/exporter theo cấu hình của integration. Khi sử dụng OTel SDK hoặc bridge, cần xác định resource được tạo ở đâu và có merge đúng với environment configuration hay không.

Không nhầm:

- Resource attribute: service.name, service.version.
- Span attribute: http.request.method, db.system.
- Observation key-value: metadata gắn vào operation; handler quyết định mapping.
- Metric attributes/tags: dimensions tạo series.
- Baggage: metadata được propagate theo trace context nếu cấu hình.
- MDC: context phục vụ logging trong tiến trình.

Một tên service đúng trên traces không tự chứng minh metrics Prometheus có label giống hệt; mỗi pipeline có thể xây resource/labels riêng. Hãy xác minh từng signal.

## 12. Exporter, registry và Collector

Micrometer registry và OpenTelemetry exporter không giống nhau:

| Thành phần | Dữ liệu | Mô hình |
| --- | --- | --- |
| PrometheusMeterRegistry | Micrometer meters | Expose endpoint để Prometheus scrape |
| OTLP MeterRegistry | Metrics | Push OTLP theo cấu hình registry |
| OTel span exporter | Spans | SDK processor chuyển spans tới exporter |
| OTel log exporter | Logs | SDK/log bridge chuyển log records |
| OpenTelemetry Collector | Một hoặc nhiều signals | Receive, process, batch, filter, route, export |

Một kiến trúc có thể dùng Micrometer Prometheus registry cho metrics và OTel OTLP exporter cho traces. Điều đó không có nghĩa cùng một exporter xuất cả hai.

Collector có thể gom, lọc hoặc chuyển đổi dữ liệu. Nó không thay thế instrumentation trong ứng dụng và không thể tạo span nghiệp vụ mà ứng dụng chưa instrument.

### 12.1. Push OTLP và pull Prometheus

- Prometheus pull: Prometheus chủ động scrape endpoint metrics của ứng dụng.
- OTLP push: ứng dụng/exporter gửi telemetry tới Collector hoặc backend.
- Zipkin reporter: gửi spans theo giao thức Zipkin.
- Collector export: Collector chuyển tiếp telemetry theo pipeline đã cấu hình.

Không dùng cấu hình sampling traces để điều khiển metrics scrape interval. Không dùng OTLP endpoint làm Prometheus scrape endpoint.

## 13. Tránh double instrumentation và duplicate spans

Một lỗi thường gặp là cùng một hoạt động được instrument bởi hai nguồn.

Ví dụ HTTP request có thể được tạo span bởi:
- Spring Boot server instrumentation.
- OTel Java Agent.
- Custom OTel filter.
- Custom Micrometer Observation bao bọc cùng boundary.

Nếu tất cả cùng hoạt động, trace có thể có nhiều span gần giống nhau hoặc quan hệ cha–con không như mong đợi.

### Cách kiểm soát

1. Liệt kê các instrumentation tự động đang bật trong agent/framework.
2. Xác định boundary nào đã được server/client library instrument.
3. Chỉ thêm Observation thủ công cho hoạt động nghiệp vụ chưa được đo.
4. Nếu cần custom attributes, ưu tiên bổ sung vào Observation/span hiện có thay vì tạo span lồng thứ hai cùng ý nghĩa.
5. Chạy một request test và xem waterfall theo tên, kind, parent ID và duration.
6. Tắt từng instrumentation trùng trong môi trường test để xác nhận nguồn tạo span.

Không xóa instrumentation chỉ dựa trên số lượng span mà chưa hiểu semantics; một HTTP client span và server span là hai phía của cùng một request và thường đều có ích.

## 14. Sampling và signal consistency

Sampling traces có thể làm một số request không có trace trên backend trong khi metrics vẫn ghi đầy đủ. Đây là điều bình thường.

Micrometer metrics không tự giảm theo tracing sampling probability. OTel span sampler và metrics recording policy là các thành phần riêng. Logs cũng có chính sách filter/retention riêng.

Nếu backend thấy error Counter tăng nhưng ít trace lỗi:

- Head-based sampler có thể đã bỏ trace ngay từ đầu.
- Exporter/Collector có thể drop spans.
- Observation chưa báo lỗi cho tracing handler.
- Sampling decision từ parent có thể khiến child không được record.
- Trace có thể tồn tại nhưng query/service name/time range sai.

Metrics dùng để phát hiện và định lượng xu hướng; traces giúp tìm đường đi của một số lần thực thi; logs mô tả sự kiện. Không suy error rate từ số span ERROR nếu sampling không được hiệu chỉnh.

## 15. Quy trình chọn stack cho dự án Spring Boot

Hãy quyết định theo nhu cầu và năng lực vận hành:

| Nhu cầu | Lựa chọn thường gặp |
| --- | --- |
| Metrics JVM/application với Actuator | Micrometer MeterRegistry |
| Prometheus scrape | Micrometer Prometheus registry |
| Observation chung cho metrics và tracing | Micrometer Observation + handlers |
| Tracing thống nhất với OTel ecosystem | Micrometer OTel bridge hoặc OTel API/SDK |
| Instrumentation thư viện rộng mà ít sửa code | OTel Java Agent, nếu thư viện được hỗ trợ |
| Export tập trung, nhiều backend | OTLP và OpenTelemetry Collector |
| Một thư viện muốn độc lập framework | API instrumentation được tổ chức chuẩn hóa, có thể là OTel API |

### 15.1. Checklist kiến trúc

- Có một lựa chọn rõ ràng cho tracing implementation.
- Resource service.name/service.version nhất quán.
- Mỗi HTTP/database/message boundary có owner instrumentation.
- Observation nghiệp vụ có tên ổn định và low-cardinality values.
- Propagation format thống nhất giữa services.
- Sampling phù hợp traffic và ngân sách.
- Exporter/Collector có queue, timeout, retry và self-monitoring phù hợp.
- Metrics labels không chứa IDs riêng.
- Logs có trace/span correlation mà không tiết lộ dữ liệu nhạy cảm.
- Không có duplicate spans từ agent, framework và custom instrumentation.

## 16. Tình huống thực tế: chuẩn hóa observability cho order-service

**Bối cảnh:** nhóm có Spring Boot order-service. Actuator đang xuất metrics qua Prometheus. Một số spans được tạo bằng OTel Java Agent; nhóm muốn thêm Observation cho bước tạo đơn và gửi traces đến OTel Collector.

### Bước 1 — kiểm kê instrumentation hiện tại

Xác định server span, HTTP client spans, JDBC spans nào agent đã tạo. Kiểm tra dependencies và cấu hình đang bật. Không thêm custom span trùng vào controller hoặc HTTP client.

### Bước 2 — thêm Observation cho nghiệp vụ

~~~java
@Service
public class OrderService {
    private final ObservationRegistry registry;

    public OrderService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public String create(String channel) {
        return Observation.createNotStarted("orders.create", registry)
            .lowCardinalityKeyValue("channel", normalize(channel))
            .observe(() -> {
                reserveInventory();
                return "created";
            });
    }

    private void reserveInventory() {
        // Business operation.
    }

    private String normalize(String value) {
        return "web".equals(value) || "mobile".equals(value)
                ? value : "other";
    }
}
~~~

Observation nghiệp vụ mô tả bước create order. Khi tracing handler được kết nối phù hợp, nó có thể tạo span. Metrics handler có thể ghi phép đo theo cấu hình. Không cần tạo OTel span thứ hai chỉ để làm cùng boundary.

### Bước 3 — giữ metrics pipeline hiện tại

Prometheus tiếp tục scrape endpoint metrics. Traces được gửi qua OTel exporter/Collector. Hai pipeline có thể dùng resource/service identity nhất quán nhưng lịch thu thập riêng.

### Bước 4 — kiểm tra trace waterfall

Gửi một request test. Trace dự kiến có server span, span orders.create và các client spans nếu có lời gọi đã instrument. Xác nhận parent-child, trace ID, duration, attributes và không có duplicate spans.

### Bước 5 — kiểm tra signal correlation

Metrics xác nhận request count/latency; trace chỉ ra các bước xử lý; logs được tìm theo trace ID nếu logging correlation đã bật. Kiểm tra service.name nhất quán và không có order ID làm metric tag.

**Kết quả mong muốn:** instrumentation nghiệp vụ do Observation quản lý, các library spans được tạo bởi integration phù hợp, metrics và traces được chuyển qua pipeline riêng nhưng có resource identity nhất quán.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — so sánh API

Viết hai cách đo cùng một thao tác:
- Micrometer Timer/MeterRegistry.
- Micrometer Observation có metrics handler.

So sánh code, lifecycle và thông tin mà tracing handler có thể bổ sung. Giải thích vì sao một meter đơn lẻ không tự tạo trace đầy đủ.

### Bài tập B — cấu hình OTel bridge

Tạo ứng dụng Spring Boot 3.x với Actuator và Micrometer OTel bridge. Cấu hình exporter/endpoint phù hợp, tạo một Observation nghiệp vụ và xác minh span trong backend. Ghi lại resource và propagation context.

### Bài tập C — nhận diện double instrumentation

Bật OTel Java Agent và thêm custom Observation quanh một HTTP endpoint đã được auto-instrument. Xem waterfall, xác định span nào trùng boundary và sửa ownership. Giữ lại các span client/server có semantics khác nhau.

### Bài tập D — tách pipeline metrics/traces

Xuất metrics qua Prometheus registry, traces qua OTLP. Thay đổi trace sampling probability và quan sát:
- Counter request có giảm không?
- Số trace trong backend có đổi không?
- Prometheus scrape interval có đổi không?
- Logs có tuân theo tracing sampling không?

Giải thích vì sao mỗi signal có policy riêng.

### Bài tập E — review kiến trúc

Với một service có HTTP, JDBC và message consumer, lập bảng instrumentation owner cho từng boundary. Chỉ ra API nào được dùng, bridge nào hoạt động, exporter nào chịu trách nhiệm, resource attributes và cách truyền context.

### Câu hỏi tự kiểm tra

1. Micrometer và OpenTelemetry giải quyết các phần nào của observability?
2. Meter khác Observation như thế nào?
3. OpenTelemetry API có tự xuất telemetry nếu thiếu SDK/exporter không?
4. Observation handler chuyển lifecycle thành signal ra sao?
5. Micrometer Tracing bridge có vai trò gì?
6. Brave bridge và OTel bridge có nên cùng hoạt động cho cùng tracer không?
7. OTel Java Agent khác bridge ở điểm nào?
8. Khi nào nên dùng OTel API trực tiếp trong ứng dụng Spring Boot?
9. Resource attribute khác span attribute và metric label thế nào?
10. Vì sao Micrometer metrics và OTel traces có thể dùng exporter khác nhau?
11. Context propagation bị mất ảnh hưởng trace waterfall ra sao?
12. Làm thế nào phát hiện duplicate spans từ agent và custom instrumentation?
13. Trace sampling có làm Counter Micrometer giảm không?
14. OpenTelemetry Collector có thay thế instrumentation trong ứng dụng không?
15. Cần kiểm tra gì để bảo đảm metrics, traces và logs có service identity nhất quán?

**Tiêu chí hoàn thành:** phân biệt Micrometer metrics/Observation với OTel API/SDK; giải thích bridge, handler, exporter và Collector; cấu hình được một stack Spring Boot; chọn instrumentation owner; hiểu resource và propagation; tránh duplicate spans; phân biệt sampling traces với metrics/logs.

## 18. Ghi nhớ

- Micrometer cung cấp metrics và Observation APIs tích hợp Spring Boot; OpenTelemetry cung cấp chuẩn, API/SDK và pipeline telemetry đa ngôn ngữ.
- Observation mô tả lifecycle hoạt động; handlers có thể chuyển nó thành metrics và spans nếu được cấu hình.
- Micrometer Tracing bridge nối facade tracing Micrometer với implementation như Brave hoặc OpenTelemetry.
- OTel Java Agent là cơ chế auto-instrumentation/autoconfiguration, không phải bridge. Tránh instrument cùng boundary hai lần.
- Resource mô tả service/process tạo telemetry; span attributes mô tả hoạt động; metric tags tạo dimensions; baggage được propagate theo context.
- Micrometer registry và OTel exporter có thể xuất các signals khác nhau. Prometheus pull không giống OTLP push.
- Context propagation và sampling phải được phối hợp giữa các service; metrics/logs có policy riêng.
- Chọn stack theo nhu cầu, quản lý ownership, kiểm tra waterfall và resource thực tế; không kết luận chỉ từ danh sách dependency.

## Tài liệu tham khảo

- [Micrometer Reference — Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Reference — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [OpenTelemetry — Concepts](https://opentelemetry.io/docs/concepts/)
- [OpenTelemetry — Java instrumentation](https://opentelemetry.io/docs/languages/java/)
- [OpenTelemetry — OTLP](https://opentelemetry.io/docs/specs/otlp/)


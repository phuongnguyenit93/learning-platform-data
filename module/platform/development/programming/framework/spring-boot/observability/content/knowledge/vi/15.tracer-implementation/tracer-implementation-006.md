# OTLP HTTP exporter trong Spring Boot: đưa distributed traces đến Collector

Ứng dụng Spring Boot đã có `Observation` quanh nghiệp vụ và logs hiển thị `traceId`, nhưng khi mở giao diện truy vết đội vận hành vẫn không tìm thấy trace. Không nhất thiết code chưa tạo span: dữ liệu còn phải đi qua **sampling, span processor, exporter, Collector và trace backend**. Chỉ một chặng không hoạt động cũng khiến trace biến mất khỏi hệ thống giám sát.

**OTLP** (*OpenTelemetry Protocol*) là giao thức truyền dữ liệu observability. **OTLP HTTP exporter** là thành phần gửi spans qua HTTP đến một OTLP receiver, thường là OpenTelemetry Collector hoặc backend có khả năng nhận OTLP. Trên đường truyền phổ biến, nó sử dụng **Protocol Buffers** (`application/x-protobuf`) và endpoint `/v1/traces`.

Bài thuộc chương **Tracer implementation** của module **SPRING_BOOT_OBSERVABILITY**: thiết lập observability cho Spring Boot với Micrometer Observation, metrics, logs và distributed tracing. Nội dung cũng phân biệt propagation, tag/cardinality, sampling, exporter và cách phối hợp metrics–logs–traces để điều tra lỗi, độ trễ và hành vi ứng dụng thực tế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của OTLP HTTP exporter trong chuỗi **Observation → tracing SDK → Collector → backend**.
2. Phân biệt **OTLP/HTTP** với **OTLP/gRPC** về transport, port và endpoint.
3. Cấu hình Spring Boot 3.x gửi spans tới Collector bằng Micrometer Tracing và OpenTelemetry.
4. Dựng một pipeline Collector thử nghiệm có OTLP HTTP receiver và debug exporter.
5. Hiểu sampling, batching, queue, retries, timeout, dữ liệu có thể mất và giới hạn độ trễ xuất.
6. Bảo vệ telemetry bằng TLS, authentication và chính sách span attributes an toàn.
7. Kiểm thử từng tầng và chẩn đoán khi metrics/logs có dữ liệu nhưng traces thiếu hoặc đứt giữa các service.

## 1. Exporter nằm ở đâu trong kiến trúc?

Một `Observation` mô tả vòng đời một thao tác. Khi ứng dụng cấu hình handler/tracing bridge phù hợp, thao tác đó có thể trở thành một span được ghi nhận bởi tracer. Exporter nhận dữ liệu spans từ tracing SDK/span processor, mã hóa và gửi ra ngoài.

~~~mermaid
flowchart LR
    App["Spring Boot HTTP / Business code"] --> Obs["Micrometer Observation"]
    Obs --> Bridge["Micrometer Tracing / OTel bridge"]
    Bridge --> SDK["OpenTelemetry SDK / SpanProcessor"]
    SDK --> Export["OTLP HTTP exporter"]
    Export -- "POST /v1/traces" --> Receive["Collector OTLP receiver"]
    Receive --> Process["Processors / exporters"]
    Process --> Store["Trace backend"]
    Obs --> Handler["Metrics handler"]
    Handler --> Meter["MeterRegistry / metrics backend"]
    App --> Log["Application logs<br/>traceId, spanId khi có"]
~~~

| Thành phần | Chức năng | Điều không tự bảo đảm |
| --- | --- | --- |
| `ObservationRegistry` | Quản lý Observation, scope, convention và handlers | Không tự gửi HTTP đến trace backend |
| Micrometer Tracing bridge | Kết nối Micrometer với tracer/SDK | Không bảo đảm mọi trace được lấy mẫu |
| OpenTelemetry SDK / SpanProcessor | Quản lý recording, batching và vòng đời spans | Không có khả năng lưu spans bền vững mặc định |
| **OTLP HTTP exporter** | Mã hóa và gửi span batches qua HTTP | Không bảo đảm Collector/backend đã ghi nhận hoàn toàn |
| Collector OTLP receiver | Nhận dữ liệu OTLP | Không phải trace storage bền vững mặc định |
| Collector processors/exporters | Xử lý và chuyển tiếp telemetry | Không tự có pipeline nếu chưa cấu hình |
| Trace backend | Lưu và cho phép truy vấn spans/traces | Không thể khôi phục span chưa từng được export |

Mô hình thường dùng cho microservices: **mỗi service tự xuất spans**, có thể tới cùng một Collector hoặc các Collector agents/gateway khác nhau. Backend ghép các spans theo trace ID và parent/span IDs, không phải Collector “chạy lại request” để tạo traces.

### 1.1. Export khác propagation

Có hai luồng độc lập:

- **Propagation:** `order-service` gửi `traceparent` khi gọi `inventory-service` để tạo quan hệ parent-child giữa spans hai process.
- **Export:** `order-service` và `inventory-service` gửi dữ liệu spans của mình tới Collector bằng OTLP HTTP.

Nếu **propagation lỗi**, hai service có thể xuất thành công nhưng backend sẽ thấy **hai traces rời nhau**. Nếu **export lỗi ở một service**, backend có thể thấy trace bị thiếu một nhánh dù propagation đang hoạt động. Không nhầm việc logs có trace ID với việc Collector đã nhận span đó.

## 2. OTLP/HTTP gửi gì? Dùng cổng và đường dẫn nào?

OTLP định nghĩa cách truyền **traces, metrics và logs**. Bài này chỉ tập trung vào **span data**; các exporter metrics và logs là những pipeline khác.

| Signal | Endpoint OTLP/HTTP thông dụng | Vai trò |
| --- | --- | --- |
| Traces | `http://collector:4318/v1/traces` | Gửi các spans |
| Metrics | `http://collector:4318/v1/metrics` | Gửi metrics qua OTLP |
| Logs | `http://collector:4318/v1/logs` | Gửi log records qua OTLP |

Không thể thay `/v1/traces` bằng `/v1/metrics` rồi kỳ vọng span exporter biến thành metrics exporter. Mỗi loại dữ liệu cần serializer, receiver pipeline và cấu hình phù hợp.

### 2.1. OTLP/HTTP khác OTLP/gRPC

| Thuộc tính | OTLP/HTTP | OTLP/gRPC |
| --- | --- | --- |
| Transport | HTTP, thường dùng protobuf | gRPC trên HTTP/2 |
| Port mặc định thường gặp | **4318** | **4317** |
| Đích nhận traces | **`/v1/traces`** | gRPC service/method |
| Content type thông dụng | `application/x-protobuf` | Protocol Buffers theo gRPC |
| Phản hồi lỗi | HTTP status và thông tin lỗi của receiver | gRPC status và thông tin lỗi |
| Load balancer/proxy | Phải chuyển tiếp HTTP request/path đúng | Phải hỗ trợ gRPC/HTTP2 đúng |

Một lỗi phổ biến là đặt `http://localhost:4317/v1/traces` cho **HTTP exporter**. Cổng 4317 thường là gRPC receiver nên HTTP request theo path `/v1/traces` có thể không được xử lý như dự kiến. Với OTLP HTTP/protobuf, địa chỉ local thường là:

~~~text
http://localhost:4318/v1/traces
~~~

**`localhost` luôn được hiểu từ tiến trình/container gửi**, không tự trỏ đến Collector chạy ở một container khác hoặc máy khác.

### 2.2. Hình dạng HTTP request

Exporter thường gửi một batch đã mã hóa:

~~~http
POST /v1/traces HTTP/1.1
Host: collector:4318
Content-Type: application/x-protobuf
Authorization: Bearer TOKEN_PLACEHOLDER

<binary OTLP ExportTraceServiceRequest>
~~~

Đoạn này mô tả giao thức, **không phải request copy-paste chạy được bằng curl**. Body là protobuf nhị phân. Header `Authorization` chỉ xuất hiện khi có xác thực và phải dùng credential thật từ secret store/biến môi trường, không ghi token vào tài liệu, repo hoặc logs.

Một response HTTP thành công cho biết receiver đã xử lý request theo giao thức; **chưa chứng minh** dữ liệu đã đến trace storage: còn batching, policy lọc, Collector exporter, ingest backend và retention. Một số phản hồi OTLP có thể mô tả **partial success/rejected spans**; khi kiểm tra mất dữ liệu cần xem thông tin receiver/Collector chứ không chỉ mã HTTP.

## 3. Cấu hình dependency Spring Boot

Ví dụ Gradle cho **Spring Boot 3.x** sử dụng Micrometer Tracing với OpenTelemetry bridge:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Dùng OpenTelemetry làm tracing implementation của Micrometer.
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'

    // Export spans bằng OTLP.
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    // Tùy chọn: metrics Prometheus độc lập với traces exporter.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Những phụ thuộc trên giải quyết các nhiệm vụ riêng:

1. **Actuator:** cung cấp phần tích hợp observability với Spring Boot.
2. **Micrometer Tracing bridge:** kết nối Observation/Tracing API với OpenTelemetry.
3. **OTLP exporter:** đảm nhiệm việc gửi dữ liệu spans ra khỏi ứng dụng.
4. **Prometheus registry (nếu cần):** phục vụ metrics, không thay thế tracing exporter.

**Không cố định tùy tiện phiên bản Micrometer, OpenTelemetry và Spring Boot**; sử dụng BOM/dependency management của dự án và xác minh tài liệu phiên bản. Khác biệt giữa các dòng Spring Boot có thể ảnh hưởng property names, auto-configuration và cách chọn HTTP/gRPC transport.

### 3.1. Ví dụ application.yml cho OTLP/HTTP

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 1.0  # Chỉ nên dùng khi thực hành với traffic nhỏ.
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

`management.otlp.tracing.endpoint` là property được dùng trong các dòng Spring Boot 3.x hỗ trợ OTLP tracing auto-configuration. Cần đối chiếu với **version thực tế** của dự án; ở phiên bản khác, cấu hình exporter có thể thay đổi.

`probability: 1.0` tạo điều kiện dễ nhìn trace trong môi trường test, nhưng không nên triển khai cho mọi hệ thống production vì lưu lượng cao làm tăng số spans, CPU, bộ nhớ, network và chi phí ingest.

### 3.2. Dùng biến môi trường khi triển khai

~~~yaml
management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT:http://localhost:4318/v1/traces}
~~~

Ví dụ một endpoint của Collector Service trong Kubernetes:

~~~text
OTLP_TRACES_ENDPOINT=http://otel-collector.observability.svc.cluster.local:4318/v1/traces
~~~

Đây là **tên DNS minh họa**, không phải tên service chắc chắn đã có. Phải xác định địa chỉ, namespace, cổng, DNS và network policy theo môi trường được triển khai.

### 3.3. Service name và resource attributes

`spring.application.name` thường được Spring Boot sử dụng làm ngữ cảnh cho tên ứng dụng/tracing service, nhưng khi backend hiển thị `unknown_service` cần kiểm tra **resource attributes thực sự được SDK/exporter đưa vào OTLP**.

| Resource attribute | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `service.name` | `order-service` | Phân biệt các service trong backend |
| `service.version` | `1.8.2` | Đối chiếu với release |
| `deployment.environment` | `staging` | Lọc theo môi trường |
| `service.instance.id` | Mã instance có giới hạn | Điều tra khác biệt giữa instances |

Không dùng access token, user ID hoặc dữ liệu cá nhân làm resource attributes. Tên cấu hình để bổ sung resource attributes phụ thuộc version Spring Boot/OpenTelemetry đang dùng.

### 3.4. Authentication và TLS

Khi Collector/backend yêu cầu xác thực, có thể có cơ chế thiết lập headers cho OTLP tracing. Ví dụ định hướng cho phiên bản Spring Boot hỗ trợ `management.otlp.tracing.headers`:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT}
      headers:
        Authorization: ${OTLP_AUTH_HEADER}
~~~

Giá trị `OTLP_AUTH_HEADER` nên được cấp qua hệ thống quản lý bí mật. Kiểm tra property binding của phiên bản thực tế: không phải mọi dòng Spring Boot hoặc exporter đều nhận headers từ cùng một namespace property.

Production cần sử dụng **HTTPS/TLS**, certificate/CA đúng, quyền truy cập receiver rõ ràng và network policy phù hợp. Nếu có proxy hoặc mTLS, cấu hình exporter/Collector tương ứng; **không bỏ xác minh TLS** như một cách sửa lỗi lâu dài.

## 4. Dựng OpenTelemetry Collector để nhận OTLP/HTTP

Collector giúp tách việc tiếp nhận telemetry khỏi ứng dụng: nó có thể nhận spans, batch, lọc theo policy, thêm resource attributes, chuyển tiếp và quan sát trạng thái pipeline.

Một cấu hình thử nghiệm:

~~~yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:
    timeout: 5s

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
~~~

Với Collector có hỗ trợ `debug` exporter, log Collector sẽ hiển thị những spans được nhận sau khi batch được xử lý. Đây là **cấu hình học tập**: không dùng debug detailed trên production vì log có thể chứa span attributes nhạy cảm và lượng dữ liệu lớn.

~~~mermaid
flowchart LR
    A["Spring Boot<br/>OTLP HTTP exporter"] -- "POST :4318/v1/traces" --> B["Collector<br/>OTLP HTTP receiver"]
    B --> C["Batch processor"]
    C --> D["Debug exporter (test)"]
    C -. "Production: backend exporter" .-> E["Trace storage / backend"]
~~~

### 4.1. Collector phải có service pipeline

Khai báo `receivers.otlp` riêng lẻ chưa đủ. `service.pipelines.traces` phải kết nối receiver, processors và exporters. Nếu chỉ dùng debug exporter, Collector có thể **nhận và log spans** mà không có trace lưu lâu dài để tìm kiếm trong giao diện.

Ở môi trường production, cấu hình exporter đích phù hợp (OTLP/HTTP, OTLP/gRPC hoặc giao thức backend hỗ trợ), cùng authentication, TLS, retry, memory limiter và batching theo nhu cầu triển khai. Receiver dùng HTTP **không bắt buộc** exporter tiếp theo cũng dùng HTTP.

### 4.2. Chạy trong container và Kubernetes

- Receiver cần listen trên interface phù hợp với luồng mạng mong muốn. `0.0.0.0:4318` cho phép nhận từ interface mạng container, nhưng cần firewall/network policy để bảo vệ.
- Nếu Spring Boot và Collector ở **hai container**, `localhost:4318` bên Spring Boot không phải Collector.
- Nếu Collector triển khai như Kubernetes Service, sử dụng DNS/port Service được cấp; kiểm tra namespace.
- Collector image/version phải có các component `otlp`, `batch` và `debug`. Các bản cũ có thể dùng tên exporter khác.
- Nếu cấu hình pipeline sai hoặc chỉ có receiver nhưng không có exporter, việc mở được cổng không có nghĩa spans được lưu.

### 4.3. Kiểm tra trạng thái receiver

Một phép kiểm tra TCP tới cổng 4318 cho biết khả năng kết nối mạng, **không chứng minh payload OTLP hợp lệ**. Gửi `GET /v1/traces` bằng curl có thể nhận 404/405 vì receiver chờ POST/protobuf; không nên dùng kết quả GET đơn lẻ để kết luận endpoint export hỏng.

Bằng chứng tốt hơn: Spring Boot gửi batch thật, Collector nhận và log span/resource information, hoặc một test receiver giải mã được `ExportTraceServiceRequest` của OTLP.

## 5. Instrument nghiệp vụ bằng Micrometer Observation

Không cần tự xây HTTP request OTLP cho từng thao tác. Ứng dụng nên dùng `Observation`; tracing SDK/handler/exporter xử lý phần telemetry.

~~~java
package com.example.orders.tracing;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class InventoryReservationService {
    private final ObservationRegistry registry;
    private final InventoryGateway inventory;

    public InventoryReservationService(
            ObservationRegistry registry, InventoryGateway inventory) {
        this.registry = registry;
        this.inventory = inventory;
    }

    public void reserve(String sku, int quantity) {
        String attemptId = UUID.randomUUID().toString();

        Observation.createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("dependency.name", "inventory")
                .lowCardinalityKeyValue("inventory.operation", "reserve")
                .highCardinalityKeyValue("inventory.attempt.id", attemptId)
                .observe(() -> inventory.reserve(sku, quantity));
    }
}

interface InventoryGateway {
    void reserve(String sku, int quantity);
}
~~~

Trong ví dụ:

1. `inventory.reserve` là tên ổn định, không chứa ID động.
2. Low-cardinality tags biểu diễn loại thao tác và dependency, thích hợp để nhóm metrics.
3. `inventory.attempt.id` là high-cardinality metadata; tracing handler có thể đưa vào span attributes khi được cấu hình. UUID giả danh giúp tìm lần thử mà không cần đưa dữ liệu người dùng vào trace.
4. `observe(...)` quản lý lifecycle và scope, ghi nhận exception theo hành vi API.
5. Span có thể được xuất **sau khi Observation dừng**, vì SDK có thể batch trước khi gửi HTTP.

Nếu Spring MVC/HTTP client đã được instrument, tránh thêm một custom Observation khác chỉ để sao chép span HTTP sẵn có. Nên instrument các **ranh giới nghiệp vụ có ý nghĩa** như checkout, reserve inventory, validate payment.

### 5.1. Không tự gọi exporter bên trong request handler

Không đặt logic kiểu “mỗi request tạo span rồi gọi HTTP `/v1/traces` bằng tay” trong business service. Nó làm coupling ứng dụng với telemetry, gây khó kiểm soát batching/retry, và có thể biến sự cố Collector thành sự cố độ trễ của người dùng.

Nếu cần xem trace gần thời gian thực, điều chỉnh SDK/Collector trong ngân sách phù hợp; không ép flush đồng bộ ở mọi request.

## 6. Propagation bằng traceparent khác với OTLP export

Giả sử `order-service` gọi `inventory-service`. Muốn có cây span xuyên service, HTTP client/server instrumentation phải **truyền và nhận trace context**, thông thường theo W3C Trace Context:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

| Thành phần | Ý nghĩa |
| --- | --- |
| `00` | Phiên bản của header |
| 32 ký tự hex | Trace ID |
| 16 ký tự hex | Span ID của phía gửi, dùng làm remote parent |
| `01` | Trace flags; bit sampled được bật trong ví dụ |

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Order as order-service
    participant Inv as inventory-service
    participant Collector as OTel Collector
    Client->>Order: POST /orders
    Note over Order: HTTP SERVER span A
    Order->>Order: inventory.reserve span B
    Order->>Inv: HTTP + traceparent, CLIENT span C
    Note over Inv: HTTP SERVER span D, parent C
    Inv-->>Order: HTTP response
    Order-->>Client: Response
    Order->>Collector: OTLP HTTP gửi spans A,B,C
    Inv->>Collector: OTLP HTTP gửi span D
~~~

- Span con có **trace ID chung** với parent, nhưng có **span ID mới** và `parentSpanId` tham chiếu đúng span cha.
- Hai service **xuất dữ liệu riêng**; backend dựng cây từ định danh trong spans.
- Nếu một service không export, backend có thể thiếu nhánh dù trace context đã truyền đúng.
- Nếu propagation lỗi, backend có thể có hai trace rời nhau dù exporter của cả hai vẫn thành công.

### 6.1. Async, Reactor và messaging

`@Async`, `Executor`, Reactor, messaging hoặc batch processing có thể đổi execution context. Nếu active trace context không được capture/restore, span mới có thể trở thành root khác.

Với Spring Framework 6.1+ và Micrometer Context Propagation, `ContextPropagatingTaskDecorator` có thể giúp truyền context cho executor phù hợp khi các accessors được cấu hình. Reactor cần cơ chế context riêng; messaging cần propagator/header đúng. **Sửa URL OTLP không thể tự nối lại parent–child sau khi context đã mất.**

### 6.2. High-cardinality metadata không tự là baggage

`Observation.highCardinalityKeyValue(...)` tạo metadata cho Observation/span; nó **không mặc nhiên được truyền sang service khác** qua `traceparent`. Nếu thật sự cần propagate một giá trị nghiệp vụ, thiết kế header hoặc baggage được kiểm soát riêng, hạn chế kích thước và dữ liệu nhạy cảm.

## 7. Sampling: span nào được xuất?

**Sampling** quyết định những spans/traces nào được ghi nhận để có khả năng export. OTLP HTTP exporter không tự khôi phục những span mà sampler đã bỏ.

~~~mermaid
flowchart TD
    A["Observation được tạo"] --> B{"Tracing SDK ghi span theo sampling?"}
    B -- "Không" --> C["Không có recorded span để export"]
    B -- "Có" --> D["Span kết thúc"]
    D --> E["SpanProcessor queue / batching"]
    E --> F["OTLP HTTP POST"]
    F --> G{"Receiver chấp nhận?"}
    G -- "Có" --> H["Collector pipeline → backend"]
    G -- "Lỗi tạm thời" --> I["Retry nếu policy hỗ trợ"]
    I --> F
    G -- "Không phục hồi / hết budget" --> J["Span có thể bị mất"]
~~~

### 7.1. Head-based sampling và tail-based sampling

**Head-based sampling** thường đưa ra quyết định sớm, chẳng hạn xác suất 10%, và sampling flag có thể được propagate. Nó giảm overhead nhưng có thể bỏ mất trace của lỗi hiếm.

**Tail-based sampling** thường đặt ở Collector/hạ tầng nhận spans để ưu tiên trace chậm hoặc lỗi sau khi quan sát một phần hoặc toàn bộ trace. Nó cần queue, bộ nhớ và cấu hình chính sách phù hợp. Nếu SDK đã bỏ span trước export bằng head sampling thì Collector **không thể phục hồi span chưa từng đến**.

**Sampling 10% không có nghĩa 10% HTTP requests được xử lý**; ứng dụng vẫn xử lý request bình thường, metrics có thể tiếp tục đo tất cả các request đã được instrument.

### 7.2. Sampling và parent–child spans

Một root span không được ghi có thể dẫn đến không có trace ở backend. Nếu policy ở các service khác nhau không tương thích hoặc một service áp dụng sampling độc lập, trace có thể không đầy đủ. Do đó, ngoài cấu hình sampling xác suất, cần kiểm tra **remote sampling state** và sự kế thừa trace context giữa các service.

Không dùng số traces lưu được làm mẫu số trực tiếp để tính error rate toàn hệ thống trừ khi thiết kế thống kê sampling thật sự cho phép suy luận đó. Với SLI/SLO người dùng, ưu tiên HTTP metrics tổng hợp có phạm vi rõ ràng.

## 8. Batching, retries, queue và mất dữ liệu

Exporter thường hoạt động cùng **BatchSpanProcessor**, gom spans hoàn tất thành các batch rồi gửi qua HTTP theo kích thước/lịch định trước. Vì thế một span có thể không xuất hiện ngay lập tức tại backend.

| Tùy chọn/cơ chế | Ảnh hưởng | Rủi ro |
| --- | --- | --- |
| Batch size | Số span gom vào mỗi đợt gửi | Quá lớn tăng bộ nhớ; quá nhỏ tăng HTTP overhead |
| Export interval | Độ thường xuyên flush theo lịch | Quá dài làm trace xuất hiện muộn |
| Queue capacity | Số spans tạm giữ khi chờ export | Queue đầy có thể làm drop |
| HTTP timeout | Giới hạn thời gian chờ receiver | Quá ngắn gây lỗi giả khi mạng chậm |
| Retry/backoff | Phục hồi sau lỗi tạm thời | Không bảo đảm giao hàng nếu hết budget |
| Collector batch processor | Gom dữ liệu trước khi xuất tới backend | Tăng thông lượng nhưng thêm độ trễ/bộ nhớ |
| Collector memory limiter | Giữ Collector khỏi OOM | Có thể từ chối hoặc làm mất dữ liệu khi áp lực |

Không phải tùy chọn nào cũng nằm dưới `management.otlp.tracing.*` trong mọi phiên bản Spring Boot. Một số được cấu hình ở OpenTelemetry SDK/span processor, số khác ở Collector. Tra tài liệu cho **đúng version**, tránh thêm property không tồn tại rồi tưởng đã điều chỉnh thành công.

### 8.1. Exporter có giữ span khi Collector lỗi?

Một số implementation có retry cho lỗi tạm thời, nhưng **không có bảo đảm mặc định rằng toàn bộ spans sẽ được lưu bền vững**. Nếu ứng dụng bị kill khi batch đang ở RAM, dữ liệu có thể mất. Nếu Collector quá tải, exporter hoặc Collector có thể drop/reject spans sau khi vượt giới hạn.

Vì vậy:

1. Theo dõi error rate, queue occupancy, dropped spans nếu telemetry của SDK/Collector cung cấp.
2. Dùng graceful shutdown để SDK có cơ hội flush trong phạm vi timeout.
3. Không dùng trace làm nhật ký nghiệp vụ bền vững hoặc nguồn chứng từ giao dịch.
4. Không ép export đồng bộ từng span vì có thể làm chậm đường request.
5. Có ngân sách sampling và retention phù hợp với lưu lượng, peak và chi phí.

### 8.2. Retry không tự sửa lỗi cấu hình

Retry có thể có ích khi receiver tạm thời quá tải hoặc network gián đoạn. Với token sai, endpoint path sai hoặc transport không tương thích, tăng retry chỉ thêm tải và trì hoãn phát hiện lỗi. Trước khi đổi retry policy, xác định loại lỗi là tạm thời hay cấu hình cố định.

## 9. Bảo mật telemetry và dữ liệu nhạy cảm

Spans có thể đi qua nhiều hệ thống và được lưu hàng ngày hoặc hàng tuần. Một span attribute hữu ích khi debug chưa chắc được phép đưa ra ngoài hạ tầng ứng dụng.

| Dữ liệu | Có nên export? | Cách xử lý |
| --- | --- | --- |
| `service.name`, `service.version` | Có | Hợp đồng resource attributes rõ ràng |
| Loại operation, dependency | Có | Tên ổn định, giá trị hữu hạn |
| `http.route=/orders/{id}` | Thường có | Route template thay URL thô |
| Mã lần thử giả danh nội bộ | Cân nhắc | High cardinality có giới hạn, không suy ra người dùng |
| Email, số điện thoại, địa chỉ | Không mặc định | Dữ liệu cá nhân |
| Password, token, cookie | **Không** | Bí mật xác thực |
| Body request/response | Tránh mặc định | Có thể chứa dữ liệu nhạy cảm và rất lớn |
| Exception message tự do | Kiểm soát | Có thể lộ SQL, URL, payload |

**Nguyên tắc production:**

- Chỉ gắn metadata thực sự cần cho câu hỏi điều tra; đặt giới hạn độ dài và số lượng attributes.
- Không đưa user ID, trace ID, order ID vào **low-cardinality metric labels**: chúng tạo nhiều time series.
- Cẩn trọng với **high-cardinality span attributes**; dù không làm nổ metric series, chúng vẫn tăng chi phí traces, indexing và rủi ro bảo mật.
- Bảo vệ traffic tới Collector bằng TLS, network policy và authentication phù hợp.
- Giữ credential trong secret store; không đặt token trực tiếp trong application.yml ở source control.
- Đặt retention và phân quyền truy cập traces/logs rõ ràng; giới hạn người xem spans nhạy cảm.
- Không chạy `debug` exporter ở verbosity detailed trên production trừ khi có nhu cầu kiểm soát chặt chẽ.

### 9.1. Resource attributes khác span attributes

**Resource attributes** như `service.name` mô tả nguồn tạo telemetry, còn **span attributes** như `dependency.name` mô tả một thao tác cụ thể. Cả hai có thể đi trong dữ liệu OTLP, nhưng backend có thể hiển thị/index khác nhau. Không nên kết luận exporter làm mất attribute chỉ vì bộ lọc UI không hỗ trợ tìm kiếm theo attribute đó.

## 10. Kiểm thử OTLP HTTP exporter theo từng tầng

Không có một test đơn lẻ nào chứng minh hoàn toàn end-to-end tracing. Nên kiểm tra từ instrumentation tới transport và backend.

| Tầng | Công cụ/cách thực hiện | Bằng chứng |
| --- | --- | --- |
| Unit test Observation | `TestObservationRegistry` | Observation có tên/tags/lifecycle đúng |
| Tracing SDK test | In-memory exporter hoặc test span handler | Spans và parentSpanId đúng |
| HTTP transport test | OTLP receiver giả lập hiểu protobuf | Request POST và payload đúng |
| Collector smoke test | OTLP HTTP receiver + debug exporter | Collector nhận resource/spans |
| Backend integration | Trace backend staging | Tra được trace theo ID/service |
| Cross-service test | Hai service với W3C propagation | Parent–child liền mạch qua HTTP |

### 10.1. Unit test Micrometer Observation

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.Test;

class InventoryObservationTest {
    @Test
    void recordsOperationMetadata() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("dependency.name", "inventory")
                .highCardinalityKeyValue(
                        "inventory.attempt.id", "attempt-test-001")
                .observe(() -> { /* mô phỏng nghiệp vụ thành công */ });

        TestObservationRegistryAssert.assertThat(registry)
                .hasSingleObservationThat()
                .hasBeenStopped()
                .hasNameEqualTo("inventory.reserve")
                .hasLowCardinalityKeyValue("dependency.name", "inventory")
                .hasHighCardinalityKeyValue(
                        "inventory.attempt.id", "attempt-test-001")
                .doesNotHaveError();
    }
}
~~~

Test này chứng minh Observation runtime, **không tạo request OTLP HTTP**. Để chứng minh exporter và Collector hoạt động, cần test ở tầng dưới.

### 10.2. Test span IDs bằng in-memory exporter

Với OpenTelemetry SDK test infrastructure và sampler ghi spans:

1. Tạo parent Observation trong active scope.
2. Tạo child Observation bên trong scope parent.
3. Hoàn tất child và parent.
4. Thu span data bằng in-memory exporter.
5. Kiểm tra parent và child có **cùng trace ID**.
6. Kiểm tra child có **span ID riêng** và `child.parentSpanId == parent.spanId`.
7. Kiểm tra span name, attributes và lỗi/status theo chính sách.

Test này xác minh tracing SDK/instrumentation; **không xác minh HTTP transport hoặc Collector**.

### 10.3. Smoke test Collector thực tế

Các bước:

1. Chạy Collector với `otlp` HTTP receiver và `debug` exporter của cấu hình học tập.
2. Cấu hình cả Spring Boot và Collector cùng endpoint/port thực tế.
3. Trong môi trường thử nghiệm, đặt sampling `1.0` và gửi vài request có Observation.
4. Đợi qua khoảng batching rồi xem Collector logs để tìm `service.name`, `traceId` và span names.
5. Nếu Collector xuất tiếp vào backend staging, tra trace ID và kiểm tra cây parent–child.
6. Ngắt Collector tạm thời để quan sát lỗi exporter/retry; khôi phục rồi đo lại trong giới hạn queue.

**Không gửi một chuỗi JSON tự tạo tới `/v1/traces` rồi coi HTTP 200/400 là bằng chứng đầy đủ của exporter.** Một transport test thực phải dùng payload OTLP hợp lệ và đúng content type.

### 10.4. Phân biệt unit test và end-to-end

`TestObservationRegistry` giúp bắt lỗi tên/tag/lifecycle rất nhanh. In-memory exporter chứng minh span recording. Collector debug chứng minh receiver đã chấp nhận payload. Backend query chứng minh dữ liệu đã lưu và truy vấn được. **Chỉ có kết quả của một tầng không nên suy rộng cho tất cả tầng còn lại.**

## 11. Chẩn đoán lỗi export qua HTTP

| Dấu hiệu | Nguyên nhân thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| `Connection refused` trên `localhost:4318` | Collector không chạy, sai container namespace, receiver không listen | IP/DNS từ process ứng dụng, port bindings, receiver config |
| DNS timeout / network timeout | Service DNS, network policy, firewall, proxy | Reachability, route, proxy/TLS |
| HTTP **404** | Sai path `/v1/traces` hoặc request tới server khác | Endpoint thực và reverse proxy |
| HTTP **400** | Payload/protocol không hợp lệ | OTLP/HTTP protobuf, content type, Collector logs |
| HTTP **401/403** | Thiếu/sai auth hoặc tenant permissions | Headers, secret, gateway policy |
| HTTP **429** | Quota hoặc quá tải receiver/backend | Sampling, lưu lượng, retry/backoff, queue |
| HTTP **5xx** | Receiver/proxy/backend lỗi tạm thời | Health pipeline, resource pressure, retry policy |
| TLS handshake failed | CA/certificate/hostname không đúng | Endpoint scheme, trust store, TLS config |
| Collector thấy spans nhưng backend không có | Thiếu exporter đích, lỗi auth, sai pipeline | Collector service pipelines và exporter logs |
| Backend thấy một service nhưng thiếu service khác | Exporter của service đó sai hoặc sampling | So sánh service resource/Collector receiver |
| Trace bị tách đôi | `traceparent` không được inject/extract | HTTP client/server instrumentation và propagation |
| Log có traceId nhưng trace UI trống | Sampler bỏ hoặc exporter/Collector/backend thiếu | Kiểm tra từ tracing SDK tới backend |
| Span xuất chậm | Batch schedule, Collector queue | Quan sát latency của pipeline |
| `unknown_service` | Resource `service.name` không đúng | Resource attributes và service naming |

### 11.1. Kiểm tra từ gần tới xa

1. **Code/Observation:** nghiệp vụ có thực sự chạy dưới Observation không? Unit test tên/tags pass?
2. **Tracing SDK:** có recording span không? Sampler có giữ chúng? Processor có được cấu hình?
3. **Exporter:** HTTP/Protobuf và URL `:4318/v1/traces` có đúng? Kết nối, TLS và auth có hoạt động?
4. **Collector:** receiver có listen? `service.pipelines.traces` đã nối tới exporter? Có từ chối spans?
5. **Backend:** đã nhận, lưu và hiển thị theo tenant/time range/service đúng?
6. **Propagation:** nếu thấy spans nhưng cây đứt, kiểm tra header `traceparent` và context qua thread.

Đừng sửa Prometheus scrape interval để chữa lỗi export traces. Metrics và tracing là hai pipeline khác nhau.

### 11.2. Không trộn lỗi telemetry với lỗi nghiệp vụ

HTTP **503 từ OTLP receiver** biểu thị **telemetry pipeline** gặp lỗi; HTTP **503 từ `inventory-service`** là lỗi dependency nghiệp vụ. Cần log/monitor phân loại riêng. Hệ thống thường không nên làm giao dịch người dùng thất bại chỉ vì trace exporter không thể kết nối, nhưng vẫn phải theo dõi mất dữ liệu telemetry như một sự cố vận hành.

## 12. Giám sát chính tracing pipeline

Tracing thường được dùng để điều tra sự cố, nhưng pipeline tracing cũng có thể hỏng đúng lúc cần nó nhất. Cần có dashboard/alerts về:

| Tín hiệu | Câu hỏi vận hành |
| --- | --- |
| Exporter requests/errors | Gửi tới receiver có thành công không? |
| Exporter queue / dropped spans | SDK đang giữ quá nhiều hay bỏ dữ liệu? |
| Export latency/retry | Mạng/receiver có bị nghẽn? |
| Collector accepted/refused spans | Receiver chấp nhận bao nhiêu dữ liệu? |
| Collector exporter send failures | Collector nhận nhưng không gửi được backend? |
| Batch processor latency | Dữ liệu được hiển thị chậm vì đâu? |
| Backend ingest/retention | Dữ liệu đã được lưu và còn truy vấn được không? |

Tên metric cụ thể phụ thuộc phiên bản OpenTelemetry SDK và Collector; kiểm tra tín hiệu thực mà bản triển khai expose trước khi tạo recording rules/alerts. Không nên đặt alert chỉ dựa vào “số spans thấp” vì sampling và traffic cũng ảnh hưởng số spans.

### 12.1. Graceful shutdown

Ứng dụng dừng ngay khi còn spans trong memory queue có thể làm mất dữ liệu. Với rolling deployment:

- Cấp thời gian graceful shutdown hợp lý.
- Đảm bảo tracing SDK/span processor có cơ hội flush trong timeout cho phép.
- Theo dõi exporter failures trong giai đoạn triển khai.
- Không dựa vào traces làm chứng từ nghiệp vụ phải lưu tuyệt đối.

### 12.2. Phân biệt SLO người dùng và telemetry SLO

SLO người dùng có thể là “99% POST /orders dưới 500 ms”. SLO pipeline quan sát có thể liên quan tới khả năng nhận telemetry, tỷ lệ export lỗi hoặc dropped spans so với policy. Không dùng trực tiếp **số traces đã lưu / tổng HTTP requests** làm tỷ lệ thành công nếu tracing được sampling và một request có nhiều spans.

## 13. Tình huống: p95 tăng nhưng thiếu nhánh inventory-service

**Giả định:** sau triển khai, p95 của `POST /orders` tăng từ 350 ms lên 2,5 giây. Metrics HTTP và logs đều hiện lỗi `inventory_timeout`, nhưng trace backend chỉ thấy spans của `order-service`.

~~~text
Trace dự kiến:
POST /orders                       order-service
└─ orders.checkout                 order-service
   └─ inventory.reserve            order-service
      └─ HTTP POST inventory       order-service
         └─ POST /reserve          inventory-service
            └─ DB stock lookup     inventory-service

Trace thực tế:
POST /orders                       order-service
└─ orders.checkout                 order-service
   └─ inventory.reserve            order-service
      └─ HTTP POST inventory       order-service
      (không thấy spans phía inventory-service)
~~~

Quy trình điều tra:

1. **Metrics xác định phạm vi:** request rate, lỗi HTTP 5xx, p95/p99, retry rate và latency inventory có thay đổi không?
2. **Trace còn lại xác định chặng:** HTTP CLIENT span của order-service có đang chờ lâu?
3. **Propagation:** `traceparent` có được gửi tới inventory? SERVER span phía inventory có trace ID chung?
4. **SDK phía inventory:** tracing bridge, sampler và instrumentation có hoạt động?
5. **OTLP exporter:** cấu hình `localhost:4318` bên container inventory có trỏ nhầm chính nó thay vì Collector Service? Logs có connection refused, 401 hoặc 404?
6. **Collector:** receiver có nhìn thấy `service.name=inventory-service` không? Traces pipeline có chuyển tiếp?
7. **Khắc phục:** sửa endpoint/network/auth/propagation theo lỗi đã xác minh và đo lại.
8. **Điều tra nghiệp vụ tiếp:** phục hồi exporter chỉ khôi phục **khả năng quan sát**. Vẫn phải tìm nguyên nhân gây 2,5 giây (DB pool, timeout, saturation, retry...).

**Không suy luận mọi request đều chậm chỉ từ một trace**; dùng metrics để định lượng phạm vi, traces để hiểu đường đi của request cụ thể và logs để tìm sự kiện lỗi.

## 14. Checklist production

| Tiêu chí | Bằng chứng cần có |
| --- | --- |
| Dependency và phiên bản tương thích | Boot BOM, Micrometer Tracing OTel bridge, OTLP exporter |
| Đúng giao thức | OTLP/HTTP với receiver hỗ trợ, không nhầm gRPC |
| Đúng endpoint | `/v1/traces`, cổng và DNS từ góc nhìn ứng dụng |
| Cấu hình theo môi trường | Endpoint qua config/secret, không hard-code localhost production |
| Service name/resource đúng | Backend phân biệt service, version, environment |
| TLS/auth đã xác minh | Receiver bảo vệ, headers/CA/policy phù hợp |
| Collector có traces pipeline | Receiver, processors và exporter đích được nối |
| Sampling được kiểm soát | Dev có thể bật cao, production có budget |
| Queue/retry/timeout hợp lý | Có metrics lỗi export và dấu hiệu dropped spans |
| Graceful shutdown | Có cơ hội flush khi scale down/rolling update |
| Propagation HTTP/async được kiểm tra | Same trace ID, parentSpanId đúng |
| Span attributes an toàn | Không có token, email, raw body, dữ liệu nhạy cảm |
| Metrics và logs vẫn có correlation | Request rate, p95, error rate và trace ID trong logs khi có scope |
| Backend thực sự lưu trace | Tra được trace theo ID, service, khoảng thời gian |

## 15. Bài thực hành: từ Observation tới OTLP HTTP Collector

**Bối cảnh:** hai Spring Boot services, `order-service` và `inventory-service`, chạy cùng OpenTelemetry Collector trong môi trường phát triển. Mục tiêu là thấy một trace từ HTTP entrypoint tới thao tác giữ hàng, đồng thời phát hiện lỗi exporter một cách có hệ thống.

**Nhiệm vụ:**

1. Thêm Actuator, `micrometer-tracing-bridge-otel` và `opentelemetry-exporter-otlp` cho cả hai service.
2. Cấu hình `management.otlp.tracing.endpoint` tới Collector OTLP/HTTP `/v1/traces`; xác minh port 4318 và DNS thực tế.
3. Chạy Collector với OTLP HTTP receiver và debug exporter trong môi trường test.
4. Tạo custom `Observation` `inventory.reserve` trong order-service. Dùng HTTP client có instrumentation tới inventory-service.
5. Bật sampling `1.0` để quan sát; tạo 5 request thành công và 2 request timeout.
6. Trong Collector logs, xác minh có resource `service.name` của cả hai services, spans và trace IDs.
7. Trong backend staging (nếu có), kiểm tra cây spans cùng trace ID, quan hệ HTTP CLIENT → SERVER đúng.
8. Dùng `TestObservationRegistry` kiểm tra tên/tag/lifecycle, sau đó giải thích vì sao test đó không chứng minh exporter gửi HTTP.
9. Cố tình đổi endpoint HTTP sang cổng gRPC `4317`; quan sát lỗi, sửa lại URL và xác minh phục hồi.
10. Ngắt Collector tạm thời, tạo traffic, kiểm tra exporter retry/queue/drop trong giới hạn cấu hình và phục hồi.
11. Giảm sampling từ 100% xuống 10% trong test, so sánh traces có mặt với số request/metrics HTTP.
12. Lập một báo cáo ngắn: khi p95 tăng nhưng trace thiếu, bạn kiểm tra những chặng nào trước?

**Kết quả mong đợi:** cấu hình ứng dụng và Collector, ít nhất một trace được nhận (nếu pipeline hoạt động), bằng chứng path/protocol đúng, bảng troubleshooting khi exporter lỗi, cùng chính sách sampling, authentication, cardinality và bảo vệ dữ liệu.

## 16. Ghi nhớ

**OTLP HTTP exporter** vận chuyển **traces đã được ghi nhận** từ OpenTelemetry SDK qua **HTTP/protobuf**, thường tới `http://collector:4318/v1/traces`. Nó không tự tạo parent–child spans, không thay thế Micrometer Observation, không quyết định mọi chính sách sampling và không đảm bảo trace đã được lưu ở backend.

Để vận hành đáng tin cậy, kiểm tra chuỗi **Observation → tracing bridge/SDK → sampling/span processor → exporter → Collector → backend**. Trace context `traceparent` giúp nối spans qua service; metrics cho biết xu hướng lỗi/độ trễ, còn logs và traces giải thích trường hợp cụ thể. Thành công phụ thuộc cấu hình mạng/TLS/auth, capacity/retry, sampling, tag/cardinality, retention và tương quan đa tín hiệu.

**Tài liệu tham khảo:**

- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/)
- [OpenTelemetry — SDK Trace](https://opentelemetry.io/docs/specs/otel/trace/sdk/)
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)

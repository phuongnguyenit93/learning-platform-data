# Cấu hình resource attributes cho OTLP trong Spring Boot

> **Chương:** OTLP export  
> **Bài:** Cấu hình resource attributes  
> **Module:** SPRING_BOOT_OBSERVABILITY — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Vì sao OTLP cần resource attributes?

Một ứng dụng Spring Boot có thể xuất traces, metrics và logs qua OpenTelemetry Protocol (OTLP). Khi telemetry tới Collector hoặc backend, dữ liệu cần trả lời câu hỏi: **ai đã tạo ra những dữ liệu này?** Một span có tên operation và attributes riêng, nhưng vẫn cần biết nó thuộc service, phiên bản và môi trường nào.

OpenTelemetry biểu diễn thông tin về thực thể tạo telemetry bằng **Resource**. Resource là tập thuộc tính được gắn với các signal do cùng một thực thể tạo ra, ví dụ một service process hoặc workload.

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = production
service.instance.id = order-service-pod-a7d2
~~~

Khi exporter chuyển telemetry qua OTLP, resource đi cùng dữ liệu theo cấu trúc OTLP. Collector và backend dùng resource attributes để nhóm, lọc, định tuyến, lập chỉ mục hoặc phân biệt các service.

Nếu resource không được cấu hình đúng, nhiều dịch vụ có thể xuất hiện dưới tên mặc định như unknown service, hoặc mỗi replica bị coi là một service riêng. Dashboard, service map, alert và truy vấn khi đó trở nên khó sử dụng.

## 2. Resource khác span attributes như thế nào?

Resource mô tả **thực thể tạo telemetry**. Span attributes mô tả **một hoạt động cụ thể**. Cả hai đều là key-value, nhưng phạm vi và vòng đời khác nhau.

| Loại dữ liệu | Phạm vi | Ví dụ |
| --- | --- | --- |
| Resource attribute | Service/process tạo telemetry | service.name=order-service |
| Span attribute | Một span | http.request.method=POST |
| Span event attribute | Một sự kiện trong span | exception.type=TimeoutException |
| Metric attribute | Một chiều phân nhóm phép đo | outcome=success |
| Log attribute | Một log record | event.action=order-created |
| Baggage | Metadata được propagate theo context | region=ap-south |

~~~mermaid
flowchart TD
  A["Resource: order-service"] --> B["Trace signal"]
  A --> C["Metrics signal"]
  A --> D["Logs signal"]
  B --> E["Span: orders.create"]
  E --> F["Span attributes: channel, result"]
  C --> G["Metric: orders.duration"]
  G --> H["Metric attributes: channel, outcome"]
  D --> I["Log record: order accepted"]
~~~

Không chép service.name vào từng span thủ công nếu SDK đã gắn Resource. Không dùng span attribute như thể nó sẽ tự trở thành Resource attribute. Nếu service identity nằm sai cấp, backend có thể không nhóm telemetry theo service như mong muốn.

## 3. Những resource attributes quan trọng

Một số thuộc tính thường dùng để mô tả service:

| Attribute | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| service.name | Tên logic ổn định của service | order-service |
| service.namespace | Nhóm hoặc miền chứa service | commerce |
| service.version | Phiên bản ứng dụng | 2.4.1 |
| service.instance.id | Định danh instance cụ thể | pod name hoặc instance ID |
| deployment.environment.name | Môi trường triển khai | production |
| service.role | Không phải thuộc tính service chuẩn chung; chỉ dùng nếu quy ước riêng được định nghĩa | api |

Ưu tiên semantic conventions OpenTelemetry hiện hành cho tên và ý nghĩa thuộc tính. Ví dụ môi trường thường được mô tả bằng deployment.environment.name trong semantic conventions mới; hệ thống cũ có thể gặp deployment.environment. Khi migration, xác minh backend và convention version để tránh tạo hai key cho cùng một ý nghĩa.

### 3.1. service.name phải ổn định

Các replicas của cùng service logic dùng cùng service.name. Không gắn pod ID, hostname, request ID hoặc giá trị thay đổi theo mỗi lần deploy vào tên service.

~~~text
service.name = order-service
service.instance.id = order-service-7dd7-pq8m
service.version = 2.4.1
~~~

Ba replicas có thể cùng service.name nhưng khác service.instance.id. Điều này cho phép backend nhóm service và vẫn drill down tới từng instance.

### 3.2. Namespace và environment là những chiều riêng

service.namespace nhóm service theo miền hệ thống; deployment.environment.name mô tả môi trường. Ví dụ:

~~~text
service.namespace = commerce
service.name = order-service
deployment.environment.name = staging
~~~

Tránh đổi tên thành order-service-staging nếu môi trường có thể được biểu diễn riêng. Tách các chiều giúp so sánh cùng service giữa staging và production.

## 4. OTEL_SERVICE_NAME và OTEL_RESOURCE_ATTRIBUTES

OpenTelemetry SDK environment configuration định nghĩa các biến môi trường dùng để cấu hình Resource:

- OTEL_SERVICE_NAME đặt giá trị chuyên biệt cho service.name.
- OTEL_RESOURCE_ATTRIBUTES đặt một tập resource attributes theo chuỗi key-value.
- OTEL_RESOURCE_ATTRIBUTES thường dùng cho namespace, version, environment và các metadata resource khác.

Bash:

~~~bash
export OTEL_SERVICE_NAME=order-service
export OTEL_RESOURCE_ATTRIBUTES="service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production"
java -javaagent:/opt/otel/opentelemetry-javaagent.jar -jar app.jar
~~~

PowerShell:

~~~powershell
$env:OTEL_SERVICE_NAME = "order-service"
$env:OTEL_RESOURCE_ATTRIBUTES = "service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production"
java -javaagent:C:\otel\opentelemetry-javaagent.jar -jar .\app.jar
~~~

Resource mong muốn:

~~~text
service.name = order-service
service.namespace = commerce
service.version = 2.4.1
deployment.environment.name = production
~~~

Theo quy tắc SDK environment variables, OTEL_SERVICE_NAME là cách chuyên biệt để đặt service.name và có ưu tiên khi service.name đồng thời xuất hiện trong OTEL_RESOURCE_ATTRIBUTES. Tránh khai báo hai giá trị khác nhau; một nguồn có thẩm quyền rõ ràng dễ vận hành hơn.

Cú pháp OTEL_RESOURCE_ATTRIBUTES có quy tắc escaping. Không tự nối các giá trị tùy ý từ request vào biến này. Chỉ đặt metadata cấu hình ổn định, không chứa bí mật.

## 5. Cấu hình resource trong Spring Boot

Spring Boot và Micrometer có các lớp cấu hình riêng. Tên ứng dụng Spring thường khai báo:

~~~yaml
spring:
  application:
    name: order-service
~~~

Tên này có thể được dùng trong một số integration như service identity hoặc tracing metadata. Tuy nhiên, không mặc định rằng spring.application.name và OTEL_SERVICE_NAME luôn tự đồng bộ trong mọi stack.

Khi dùng OpenTelemetry Java agent hoặc SDK autoconfiguration, các OTEL_* environment variables được đọc bởi thành phần OpenTelemetry tương ứng. Khi dùng Micrometer Tracing bridge, cần xác minh SDK/resource được khởi tạo thế nào và property nào thực sự tác động tới Resource.

Ví dụ cấu hình OTLP tracing của Spring Boot 3.x (tùy minor version và exporter):

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

Đoạn cấu hình trên minh họa tên Spring, sampling và endpoint trace. Nó không tự khai báo đầy đủ mọi resource attributes như namespace, version hay instance ID. Resource phải đến từ SDK, agent, bridge hoặc resource customization được cấu hình.

**Nguyên tắc:** xác định một nguồn cấu hình service.name có thẩm quyền và xác minh kết quả ở OTLP telemetry. Đừng giả định chỉ cần đặt spring.application.name là mọi exporter/SDK đều tạo resource giống nhau.

## 6. Resource với Micrometer Observation và Micrometer Tracing

Micrometer Observation là abstraction mô tả một hoạt động được quan sát. Observation handlers có thể chuyển context sang metrics và tracing. Resource identity thuộc cấu hình của registry/tracing implementation, không phải một low-cardinality key-value riêng trên mọi Observation.

Ví dụ Observation nghiệp vụ:

~~~java
Observation.createNotStarted("orders.create", observationRegistry)
    .lowCardinalityKeyValue("channel", "web")
    .observe(() -> orderService.create());
~~~

Trong ví dụ:

- orders.create là tên observation.
- channel=web mô tả operation và có thể được đưa vào metrics/spans tùy handler.
- service.name mô tả service tạo telemetry, không nên gắn lặp thủ công vào từng Observation.
- Resource được cung cấp bởi tracing SDK, bridge hoặc registry/exporter tương ứng.

Nếu cùng một ứng dụng dùng PrometheusMeterRegistry cho metrics và OTel bridge cho traces, cách gắn service identity có thể khác nhau. Phải kiểm tra hai pipeline riêng và chuẩn hóa naming convention.

## 7. OTLP truyền Resource trong data model

OTLP là giao thức vận chuyển telemetry. Resource được biểu diễn trong các cấu trúc ResourceSpans, ResourceMetrics và ResourceLogs, tương ứng với traces, metrics và logs.

~~~text
ExportTraceServiceRequest
  resource_spans[]
    resource
      attributes[]
        service.name = order-service
        service.namespace = commerce
    scope_spans[]
      spans[]
        name = orders.create
        trace_id = ...
~~~

Với metrics và logs, cấu trúc tương tự:

~~~text
ResourceMetrics
  resource
  scope_metrics
    metrics

ResourceLogs
  resource
  scope_logs
    log_records
~~~

Điều này giúp nhiều spans hoặc metric/log records cùng resource được nhóm trong payload. Exporter có thể batch dữ liệu theo resource và instrumentation scope. Đừng nhầm Resource với instrumentation scope: scope mô tả thư viện/instrumentation đã tạo telemetry, ví dụ tên và version của instrumentation library.

## 8. Ví dụ đọc Resource trong Collector

OpenTelemetry Collector có thể nhận OTLP và hiển thị hoặc xử lý Resource attributes. Một pipeline tối giản minh họa:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

exporters:
  debug:
    verbosity: detailed

service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      exporters: [debug]
    logs:
      receivers: [otlp]
      exporters: [debug]
~~~

Cấu hình minh họa cho Collector phiên bản hỗ trợ exporter debug theo schema tương ứng. Trong môi trường thực tế, thay debug bằng exporter đích phù hợp và bảo vệ endpoint nhận OTLP.

Khi gửi telemetry, log debug có thể cho thấy Resource attributes trước khi Collector export tiếp. Đây là cách kiểm tra hữu ích để phân biệt:
- Ứng dụng không tạo attribute.
- Exporter không đưa attribute vào payload.
- Collector processor sửa hoặc xóa attribute.
- Backend map hoặc hiển thị attribute theo cách riêng.

Collector có thể transform Resource, nhưng cần cấu hình processor rõ ràng và kiểm thử. Không để nhiều processor cùng ghi đè service.name mà không có quy tắc.

## 9. Thêm hoặc chuẩn hóa Resource bằng Collector processor

Trong một số kiến trúc, Collector được dùng để thêm metadata triển khai hoặc chuẩn hóa Resource. Ví dụ khái niệm dùng resource processor:

~~~yaml
processors:
  resource:
    attributes:
      - key: deployment.environment.name
        value: production
        action: upsert
      - key: service.namespace
        value: commerce
        action: upsert

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [resource]
      exporters: [otlp]
~~~

Processor resource có thể insert, update, upsert, delete hoặc hash attributes theo hành động mà phiên bản hỗ trợ. Xác minh schema processor và action với bản Collector đang dùng.

### 9.1. Nơi nào nên tạo resource attribute?

Có ba lựa chọn chính:

| Vị trí | Khi phù hợp | Rủi ro |
| --- | --- | --- |
| Ứng dụng/SDK | Service biết name, version và metadata build | Cấu hình có thể không đồng bộ giữa replicas |
| Java agent/autoconfiguration | Muốn chuẩn hóa environment configuration | Cần biết agent đang đọc biến và merge resource ra sao |
| Collector | Muốn bổ sung cluster/environment metadata tập trung | Có thể ghi đè giá trị sai hoặc che mất nguồn gốc ban đầu |

Ưu tiên tạo identity cốt lõi service.name ở nguồn có thẩm quyền gần ứng dụng. Collector có thể bổ sung thông tin hạ tầng đáng tin cậy, nhưng phải giữ nguyên semantics. Nếu Collector ép mọi telemetry thành cùng service.name, dashboard có thể mất khả năng phân biệt service.

## 10. Precedence và xung đột Resource

Resource có thể được tạo từ nhiều nguồn: SDK defaults, environment variables, agent configuration, code, Spring Boot integration và Collector processors.

Ví dụ xung đột:

~~~text
OTEL_SERVICE_NAME=order-service
OTEL_RESOURCE_ATTRIBUTES="service.name=orders,service.version=2.4.1"
spring.application.name=order-api
Collector upsert service.name=commerce-api
~~~

Kết quả cuối không nên được đoán từ danh sách nguồn. Cần kiểm tra quy tắc merge của SDK/agent, mapping của Spring integration và processor chạy sau exporter.

Thứ tự điều tra:

1. Environment của process thực tế.
2. SDK/agent/autoconfiguration có đọc environment không.
3. Resource builder trong code hoặc framework.
4. Bridge/exporter đưa resource nào vào OTLP.
5. Collector processor có thay đổi attributes không.
6. Backend có mapping hoặc transformation riêng không.

Theo SDK environment configuration, OTEL_SERVICE_NAME là biến chuyên biệt cho service.name và được ưu tiên hơn giá trị cùng key trong OTEL_RESOURCE_ATTRIBUTES. Các nguồn khác có quy tắc riêng; không khái quát precedence này thành quy tắc chung cho Spring Boot, Collector và backend.

## 11. Resource identity trên traces, metrics và logs

OpenTelemetry áp dụng Resource model cho nhiều signal, nhưng không có nghĩa mọi pipeline của ứng dụng đều dùng cùng một Resource object.

| Signal | Nguồn có thể gắn resource | Cách xác minh |
| --- | --- | --- |
| OTLP traces | OTel SDK / tracing bridge | Mở ResourceSpans |
| OTLP metrics | OTel MeterProvider hoặc registry exporter | Mở ResourceMetrics |
| OTLP logs | OTel Logs SDK/bridge | Mở ResourceLogs |
| Prometheus scrape | Target labels và registry conventions | Kiểm tra labels tại scrape endpoint |
| Application logs thường | Logging framework/agent | Kiểm tra log attributes và correlation |

Một ứng dụng có thể xuất trace qua OTLP nhưng metrics qua Prometheus scrape. Khi đó Prometheus labels được tạo từ registry, target config và relabeling; đừng giả định chúng giống hệt OTLP Resource attributes.

Muốn thống nhất, xác định tên logic của service, namespace, version và environment; cấu hình cho từng pipeline và xác minh bằng dữ liệu thực tế. Resource nhất quán là nền tảng để correlate dashboard, trace search và logs, nhưng traceId/spanId vẫn cần thiết để liên kết một request cụ thể.

## 12. Kubernetes: service identity và instance metadata

Trong Kubernetes, Deployment thường có nhiều replicas. Cách đặt resource nên phân biệt service logic với pod instance.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: example/order-service:2.4.1
          env:
            - name: OTEL_SERVICE_NAME
              value: order-service
            - name: OTEL_RESOURCE_ATTRIBUTES
              value: service.namespace=commerce,service.version=2.4.1,deployment.environment.name=production
            - name: POD_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
~~~

POD_NAME ở đây chỉ cung cấp dữ liệu environment; nó chưa tự động trở thành service.instance.id. Cần cấu hình SDK/agent hoặc resource customization để map nó vào đúng attribute nếu muốn dùng. Không nối POD_NAME vào OTEL_SERVICE_NAME.

Mỗi pod nên có instance identity khác nhau nhưng chung service name. Điều này giúp phân tích lỗi theo replica mà vẫn thống kê ở cấp service.

## 13. Cardinality, chi phí và bảo vệ dữ liệu

Resource attributes thường có cardinality thấp hơn các giá trị per-request, nhưng một số thuộc tính như service.instance.id có thể khác nhau theo mỗi pod/rollout. Cần cân nhắc cách backend index và lưu resource identity.

Không đưa vào Resource:

- Access token, password, secret hoặc cookie.
- User ID, email, số điện thoại hoặc dữ liệu cá nhân.
- Request ID hoặc order ID thay đổi mỗi lần thực thi.
- Nội dung request/response.
- Exception message tự do.

Resource được chia sẻ trên nhiều records nên lỗi gắn dữ liệu nhạy cảm có thể lan rộng trong telemetry. Chỉ đưa metadata ổn định, hữu ích cho vận hành và được chính sách bảo mật cho phép.

### 13.1. Resource cardinality khác metric cardinality

Một resource với service.instance.id mới có thể tạo thêm nhóm dữ liệu hoặc series phụ thuộc cách backend chuyển resource thành labels. Trong Prometheus, target instance labels cũng có thể làm tăng series. Không nhân thêm các thuộc tính không cần thiết vào mọi metric.

Các trường như service.name, service.namespace, service.version và environment thường hữu ích cho phân nhóm. Dùng instance ID chỉ khi cần phân biệt replica và backend có khả năng xử lý lượng instance metadata đó.

## 14. Kiểm tra Resource sau khi export OTLP

Không dừng ở việc xác nhận environment variable. Cần kiểm tra payload qua từng chặng.

### Bước 1 — kiểm tra environment của process

Linux:

~~~bash
printenv OTEL_SERVICE_NAME
printenv OTEL_RESOURCE_ATTRIBUTES
~~~

PowerShell:

~~~powershell
$env:OTEL_SERVICE_NAME
$env:OTEL_RESOURCE_ATTRIBUTES
~~~

Kiểm tra này chứng minh process environment có biến. Nó chưa chứng minh SDK đã đọc hoặc exporter đã gửi.

### Bước 2 — tạo telemetry test

Gửi một request tạo span và metric đã được instrument. Dùng một operation ổn định như orders.create để tìm trên backend.

### Bước 3 — kiểm tra Collector receive

Dùng debug exporter ở môi trường test hoặc metrics/telemetry của Collector để xác minh Resource attributes lúc nhận. Nếu attribute đã mất ở đây, kiểm tra application SDK/exporter.

### Bước 4 — kiểm tra sau processor

Nếu pipeline có resource/transform processor, quan sát telemetry sau processor. So sánh trước và sau để xác nhận không có ghi đè ngoài dự kiến.

### Bước 5 — kiểm tra backend

Mở trace hoặc metric và xác nhận service.name, namespace, version, environment và instance ID. Backend có thể đổi cách hiển thị hoặc chuẩn hóa key; đối chiếu payload OTLP và quy tắc mapping.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Backend hiện unknown_service | SDK không nhận service name hoặc không tạo resource | Kiểm tra SDK/agent configuration |
| Mỗi pod thành một service riêng | Pod name được dùng làm service.name | Dùng tên logic chung, instance ID riêng |
| OTEL_SERVICE_NAME có trong shell nhưng resource sai | Process service không nhận env hoặc SDK không đọc env | Kiểm tra environment bên trong process/container |
| Trace đúng tên, metrics sai tên | Hai pipeline có resource config khác nhau | Chuẩn hóa resource ở từng pipeline |
| Collector nhận đúng nhưng backend sai | Processor/export mapping sau đó ghi đè | Kiểm tra pipeline và backend transformation |
| service.name có hai giá trị | Environment, code hoặc Collector xung đột | Chọn source of truth và xử lý precedence |
| Environment hiển thị thành một phần của service name | Ghép environment vào service.name | Dùng deployment.environment.name |
| Version thay đổi làm nhiều service bị phân mảnh | Ghép version vào service.name | Dùng service.version riêng |
| Span có service.name thủ công nhưng resource thiếu | Gắn attribute sai cấp | Sửa Resource configuration |
| Instance ID bị thiếu | Chưa map pod/process identity | Cấu hình service.instance.id theo runtime |
| Payload OTLP lớn bất thường | Nhiều resource attributes hoặc value dài | Giảm field và giới hạn kích thước |
| Có dữ liệu bí mật trong resource | Đưa credential hoặc PII vào environment attributes | Loại bỏ, xoay secret nếu cần và kiểm tra retention |

### Quy trình chẩn đoán nhanh

1. Xác định signal đang thiếu hoặc sai Resource.
2. Kiểm tra process environment và SDK/agent.
3. Kiểm tra Resource tại exporter/Collector receiver.
4. Kiểm tra processors thay đổi attributes.
5. Kiểm tra backend mapping và query filters.
6. So sánh traces, metrics, logs theo từng pipeline.
7. Chỉ sửa nguồn tạo ra sai lệch, rồi gửi một request test để xác nhận.

## 16. Tình huống thực tế: resource identity không nhất quán

**Bối cảnh:** order-service chạy bốn replicas. Traces qua OTLP có service.name là order-service; metrics Prometheus gắn job là order-api; logs lại ghi service=orders. Dashboard hiển thị ba nhóm tên cho cùng một ứng dụng.

### Bước 1 — lập bản đồ identity

Ghi nhận nguồn tạo từng tên:
- Traces: OTel resource từ tracing SDK/agent.
- Metrics: Micrometer registry và Prometheus scrape config.
- Logs: logging pattern hoặc log agent enrichment.

### Bước 2 — chọn naming convention

Chốt service.name logic là order-service; namespace là commerce; version là image/app version; environment là production. Quy ước này dùng cho các pipeline có thể hỗ trợ.

### Bước 3 — sửa từng nguồn

- Cấu hình tracing Resource để service.name là order-service.
- Chuẩn hóa Prometheus job/relabeling để nhãn service tương ứng không mâu thuẫn.
- Cấu hình logging enrichment dùng cùng tên logic.
- Giữ pod identity ở instance label/resource riêng.

### Bước 4 — xác minh dữ liệu

Gửi request vào từng replica. Kiểm tra ResourceSpans, ResourceMetrics hoặc Prometheus labels, và log attributes. Xác nhận service name thống nhất, instance phân biệt được và không có ID per-request làm metric label.

**Kết quả mong muốn:** dashboard nhóm cùng một service; người vận hành vẫn lọc được từng version/instance và tìm trace/log theo request context.

## 17. Bài thực hành và câu hỏi tự kiểm tra

### Bài tập A — cấu hình resource từ environment

Khởi chạy một ứng dụng dùng OpenTelemetry Java Agent hoặc SDK autoconfiguration. Đặt:
- OTEL_SERVICE_NAME=order-service
- OTEL_RESOURCE_ATTRIBUTES có service.namespace, service.version và deployment.environment.name.

Gửi request, mở trace backend và xác minh Resource attributes. Bỏ biến trong môi trường test để quan sát default của SDK cụ thể.

### Bài tập B — kiểm tra precedence

Trong môi trường cô lập, đặt service.name khác nhau ở OTEL_SERVICE_NAME, OTEL_RESOURCE_ATTRIBUTES và Spring application name. Xác minh nguồn nào thực sự tác động lên resource trong stack đang dùng. Không giả định Spring property và OTel environment variables có một precedence chung.

### Bài tập C — Collector processor

Nhận OTLP trong Collector, xuất debug payload. Thêm resource processor để upsert deployment environment. So sánh Resource trước/sau processor và giải thích vì sao Collector có thể làm thay đổi dữ liệu ứng dụng gửi.

### Bài tập D — multi-replica

Chạy ba replicas cùng service.name và instance IDs khác nhau. Xác nhận backend nhóm một service nhưng drill down được từng pod.

### Bài tập E — nhiều signal

Kiểm tra traces, OTLP metrics/logs nếu ứng dụng export các signal đó; đồng thời kiểm tra Prometheus scrape labels. Xác định pipeline nào đang tạo resource/labels và liệu quy ước tên có thống nhất.

### Câu hỏi tự kiểm tra

1. Resource mô tả điều gì trong OpenTelemetry?
2. Resource attribute khác span attribute ở phạm vi nào?
3. OTEL_SERVICE_NAME và OTEL_RESOURCE_ATTRIBUTES khác nhau ra sao?
4. Vì sao không dùng pod ID làm service.name?
5. spring.application.name có luôn đồng bộ với OTel Resource không?
6. OTLP biểu diễn Resource ở những cấu trúc nào?
7. Instrumentation scope khác Resource thế nào?
8. Collector resource processor có thể làm gì với attributes?
9. Vì sao Prometheus target labels có thể khác OTLP Resource?
10. Khi trace đúng tên nhưng metrics sai, cần kiểm tra pipeline nào?
11. Resource attributes nào có thể làm tăng cardinality?
12. Tại sao không đưa secret, PII hoặc request ID vào Resource?
13. Làm sao xác định resource bị sai ở SDK, Collector hay backend?
14. service.version và deployment.environment.name có nên ghép vào service.name không?
15. Làm sao giữ service identity nhất quán giữa traces, metrics và logs?

**Tiêu chí hoàn thành:** giải thích Resource và OTLP data model; cấu hình service.name, namespace, version, environment và instance; phân biệt OTEL_SERVICE_NAME với Spring application name; hiểu precedence và Collector processor; kiểm tra resource trên từng signal; kiểm soát cardinality và dữ liệu nhạy cảm.

## 18. Ghi nhớ

- Resource mô tả service/process tạo telemetry và được gắn vào OTLP traces, metrics hoặc logs theo cấu trúc signal tương ứng.
- service.name là định danh logic ổn định của service; replicas cùng service dùng chung tên.
- service.namespace, service.version, deployment.environment.name và service.instance.id là các chiều riêng.
- OTEL_SERVICE_NAME đặt service.name trong OpenTelemetry SDK environment configuration; OTEL_RESOURCE_ATTRIBUTES đặt thêm resource attributes. Xác minh SDK/agent thực sự đọc các biến.
- spring.application.name thuộc Spring Boot; mapping sang OTel Resource phụ thuộc integration và không nên giả định tự động.
- Resource khác span attributes, metric attributes, instrumentation scope, baggage và MDC.
- Collector processor có thể bổ sung hoặc thay đổi resource; quản lý source of truth và kiểm tra trước/sau processor.
- Prometheus scrape labels không nhất thiết giống OTLP Resource. Xác minh từng pipeline.
- Chỉ đưa metadata vận hành ổn định và được phép vào Resource; tránh secret, PII và ID per-request.

## Tài liệu tham khảo

- [OpenTelemetry — Resources](https://opentelemetry.io/docs/concepts/resources/)
- [OpenTelemetry Specification — Resource SDK](https://opentelemetry.io/docs/specs/otel/resource/sdk/)
- [OpenTelemetry Specification — SDK Environment Variables](https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/)
- [OpenTelemetry Protocol — OTLP](https://opentelemetry.io/docs/specs/otlp/)
- [OpenTelemetry Collector — Resource Processor](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/processor/resourceprocessor)
- [OpenTelemetry Semantic Conventions — Service](https://opentelemetry.io/docs/specs/semconv/resource/service/)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Reference — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)


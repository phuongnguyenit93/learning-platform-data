# Endpoint fallback khi cấu hình OTLP trong Spring Boot

## 1. Mục tiêu học tập

Một ứng dụng Spring Boot có thể xuất ba loại telemetry qua OpenTelemetry Protocol (OTLP): **traces**, **logs** và **metrics**. Chúng thường được gửi tới cùng một OpenTelemetry Collector nhưng đi vào những route khác nhau. Nếu phải lặp lại địa chỉ, headers và compression cho từng signal, cấu hình dễ lệch nhau giữa các môi trường.

**Endpoint fallback** cho phép khai báo một endpoint OTLP chung làm mặc định, rồi ghi đè bằng endpoint riêng cho traces, logs hoặc metrics khi cần. Spring Boot dùng endpoint chung khi signal chưa có endpoint riêng; khi xuất qua HTTP, Boot tự thêm path chuẩn của signal. Bài thuộc chương **OTLP export** của module **SPRING_BOOT_OBSERVABILITY**, hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs, distributed tracing, context propagation, cardinality, exporter và sampling.

Sau bài học, bạn có thể xác định thứ tự ưu tiên endpoint; hiểu path được thêm khi fallback qua HTTP; cấu hình common headers và signal-specific headers; giải thích environment variables OTLP; phân biệt Spring Boot 4.x với 3.5.x; kiểm tra endpoint hiệu lực và chẩn đoán lỗi exporter.

**Phạm vi phiên bản:** phần endpoint fallback tập trung vào **Spring Boot 4.0.x**. Spring Boot 3.5.x dùng cấu hình OTLP theo signal và chưa có cùng common endpoint property để fallback như Boot 4. Không sao chép property giữa hai dòng mà không đối chiếu tài liệu.

## 2. Các OTLP signals

| Signal | Nội dung | Đường dẫn OTLP/HTTP chuẩn |
| --- | --- | --- |
| Traces | Span records và quan hệ trace | /v1/traces |
| Logs | Log records có cấu trúc | /v1/logs |
| Metrics | Metric data points | /v1/metrics |

Một Collector có thể nhận cả ba signals trên cùng host/cổng HTTP, nhưng mỗi signal dùng route riêng.

```mermaid
flowchart TD
    APP["Spring Boot application"]
    COMMON["Common endpoint<br/>https://collector.example:4318"]
    T["Traces exporter"]
    L["Logs exporter"]
    M["Metrics exporter"]
    TR["/v1/traces"]
    LR["/v1/logs"]
    MR["/v1/metrics"]
    COL["OpenTelemetry Collector"]
    APP --> T
    APP --> L
    APP --> M
    COMMON -. fallback .-> T
    COMMON -. fallback .-> L
    COMMON -. fallback .-> M
    T --> TR
    L --> LR
    M --> MR
    TR --> COL
    LR --> COL
    MR --> COL
```

Endpoint chung cung cấp **base URL** khi signal chưa có endpoint riêng. Nó không làm các signal dùng chung một request path.

## 3. Endpoint chung và endpoint theo signal

Spring Boot 4.x hỗ trợ common OTLP configuration dưới prefix **management.opentelemetry.otlp.**. Endpoint chung là **management.opentelemetry.otlp.endpoint**.

| Signal | Property endpoint riêng |
| --- | --- |
| Traces | management.opentelemetry.tracing.export.otlp.endpoint |
| Logs | management.opentelemetry.logging.export.otlp.endpoint |
| Metrics | management.otlp.metrics.export.url |

### 3.1. Quy tắc ưu tiên

**Nếu có endpoint riêng:** exporter dùng endpoint riêng nguyên dạng; Spring Boot không tự nối path signal vào URL đó. Common endpoint tiếp tục làm fallback cho những signal khác chưa có endpoint riêng.

**Nếu không có endpoint riêng:** exporter dùng common endpoint. Khi signal xuất qua HTTP, Boot thêm path chuẩn:

| Signal | Common endpoint | URL hiệu lực |
| --- | --- | --- |
| Traces | https://collector.example:4318 | https://collector.example:4318/v1/traces |
| Logs | https://collector.example:4318 | https://collector.example:4318/v1/logs |
| Metrics | https://collector.example:4318 | https://collector.example:4318/v1/metrics |

Đừng thêm signal path vào common base URL rồi lại mong Boot tự nối path lần nữa.

### 3.2. Ví dụ endpoint riêng ghi đè common

Common endpoint là https://collector.example:4318. Traces endpoint riêng là https://trace-gateway.example/tenant-a/v1/traces.

Kết quả:
- Traces gửi tới endpoint riêng nguyên dạng.
- Logs fallback tới https://collector.example:4318/v1/logs.
- Metrics fallback tới https://collector.example:4318/v1/metrics.

Cách này hữu ích khi traces cần gateway/tenant riêng, còn logs và metrics dùng Collector chung.

## 4. Cấu hình common endpoint trong Spring Boot 4

Ví dụ application.yml:

```yaml
spring:
  application:
    name: checkout-service

management:
  opentelemetry:
    otlp:
      endpoint: https://otel-collector.observability.svc:4318
      compression: gzip
      headers:
        Authorization: Bearer OTLP_AUTH_TOKEN_FROM_SECRET
    resource-attributes:
      deployment.environment: production
  tracing:
    sampling:
      probability: 0.1
```

Ý nghĩa:
- management.opentelemetry.otlp.endpoint là base endpoint chung.
- compression và headers áp dụng cho export dùng cấu hình chung khi signal không ghi đè.
- resource-attributes mô tả service/environment phát telemetry; nó không phải endpoint.
- Sampling probability ảnh hưởng traces được giữ, không đổi endpoint và không bật/tắt metrics/logs exporter.

OTLP_AUTH_TOKEN_FROM_SECRET là placeholder. Inject secret từ secret store hoặc môi trường triển khai; không commit token thật hoặc log Authorization header.

### 4.1. Override một signal

Ví dụ traces cần gửi qua gateway riêng, logs và metrics vẫn dùng Collector chung:

```yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://collector.example:4318
      headers:
        Authorization: Bearer OTLP_COMMON_TOKEN_FROM_SECRET
      compression: gzip
    tracing:
      export:
        otlp:
          endpoint: https://trace-gateway.example/tenant-a/v1/traces
          headers:
            X-Tenant: tenant-a
```

Endpoint hiệu lực:

| Signal | Endpoint |
| --- | --- |
| Traces | https://trace-gateway.example/tenant-a/v1/traces |
| Logs | https://collector.example:4318/v1/logs |
| Metrics | https://collector.example:4318/v1/metrics |

Traces không dùng common endpoint vì đã có endpoint riêng. Logs và metrics vẫn fallback.

## 5. Common headers và signal-specific headers

Spring Boot hợp nhất common headers với headers riêng theo signal. Nếu cùng một key xuất hiện ở hai nơi, **giá trị signal-specific thắng**.

```yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://collector.example:4318
      headers:
        Authorization: Bearer OTLP_COMMON_TOKEN
        X-Environment: production
    tracing:
      export:
        otlp:
          headers:
            Authorization: Bearer OTLP_TRACE_TOKEN
            X-Tenant: trace-team
```

Headers hiệu lực cho traces:
- Authorization dùng OTLP_TRACE_TOKEN vì key trùng nên signal-specific ghi đè.
- X-Environment vẫn là production vì chỉ có ở common.
- X-Tenant là trace-team vì chỉ có ở tracing-specific.

Logs và metrics vẫn dùng common Authorization và X-Environment nếu không có cấu hình riêng. Header merge là cơ chế cấu hình; credentials và quyền ingest vẫn cần giới hạn theo trust boundary.

## 6. Environment variable fallback

Spring Boot hỗ trợ mapping một tập environment variables của OpenTelemetry SDK sang configuration properties.

| Environment variable | Phạm vi |
| --- | --- |
| OTEL_EXPORTER_OTLP_ENDPOINT | Common endpoint |
| OTEL_EXPORTER_OTLP_TRACES_ENDPOINT | Endpoint riêng cho traces |
| OTEL_EXPORTER_OTLP_LOGS_ENDPOINT | Endpoint riêng cho logs |
| OTEL_EXPORTER_OTLP_METRICS_ENDPOINT | Endpoint riêng cho metrics |

Nếu tồn tại cả biến signal-specific và biến chung:
- Biến signal-specific được ưu tiên và dùng nguyên URL.
- Biến chung chỉ là fallback khi không có biến theo signal.
- Khi common endpoint được dùng fallback qua HTTP, Boot thêm path signal tương ứng.

Ví dụ:

```text
OTEL_EXPORTER_OTLP_ENDPOINT=https://collector.example:4318
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://traces.example/otlp/v1/traces
```

Kết quả:
- Traces dùng URL riêng nguyên dạng.
- Logs fallback tới https://collector.example:4318/v1/logs.
- Metrics fallback tới https://collector.example:4318/v1/metrics.

Nếu chỉ đặt common endpoint:

```text
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
```

thì traces qua HTTP dùng http://localhost:4318/v1/traces; logs dùng /v1/logs và metrics dùng /v1/metrics.

Mapping environment variables có thể tắt bằng:

```yaml
management:
  opentelemetry:
    map-environment-variables: false
```

Khi tắt mapping, không dựa vào OTEL_EXPORTER_OTLP_* để mong Boot bind tự động thành Spring properties; dùng application properties hoặc cơ chế cấu hình khác.

### 6.1. Property sources và cấu hình hiệu lực

Giá trị có thể đến từ application YAML, profile, environment variables của container, ConfigMap/secret store, command-line arguments hoặc external config source. Spring Boot có quy tắc precedence giữa property sources; không giải quyết xung đột bằng cách đoán.

Kiểm tra cấu hình hiệu lực qua deployment, ConfigProps nếu được expose an toàn hoặc test binding. Không dump secrets ra log. Nhớ rằng signal-specific OTLP environment variable là URL hoàn chỉnh; common endpoint là base URL và được nối signal path khi fallback HTTP.

## 7. OTLP/HTTP và OTLP/gRPC

Endpoint fallback nối path signal cho **HTTP**. Cần xác định exporter đang dùng transport nào.

| Transport | Kết nối thường gặp | Định tuyến |
| --- | --- | --- |
| OTLP/HTTP | HTTP(S), thường cổng 4318 | Dùng /v1/traces, /v1/logs, /v1/metrics |
| OTLP/gRPC | gRPC, thường cổng 4317 | Dùng RPC service/method; không ghép HTTP path vào URL |

Không copy URL HTTP có suffix /v1/traces sang exporter gRPC. Xem property transport của exporter và tài liệu Spring Boot đúng phiên bản. Không suy luận gRPC xử lý base URL giống HTTP.

Nếu receiver chỉ bật OTLP/HTTP nhưng ứng dụng dùng gRPC, lỗi kết nối có thể xuất hiện dù host đúng. Gửi HTTP tới cổng gRPC cũng có thể tạo lỗi giao thức.

## 8. Phân biệt Spring Boot 3.5 và 4.x

### 8.1. Spring Boot 4.x

Boot 4 có common endpoint property **management.opentelemetry.otlp.endpoint**. Các endpoint riêng là:
- Traces: management.opentelemetry.tracing.export.otlp.endpoint
- Logs: management.opentelemetry.logging.export.otlp.endpoint
- Metrics: management.otlp.metrics.export.url

Common endpoint làm fallback cho signal chưa đặt endpoint riêng. Khi fallback qua HTTP, Boot nối path tương ứng.

### 8.2. Spring Boot 3.5.x

Boot 3.5 dùng property riêng cho tracing OTLP:

```yaml
management:
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
      transport: http
      export:
        enabled: true
  tracing:
    sampling:
      probability: 0.1
```

Metrics OTLP dùng nhóm khác:

```yaml
management:
  otlp:
    metrics:
      export:
        url: http://localhost:4318/v1/metrics
        step: 1m
```

Spring Boot 3.5 chưa có cùng common endpoint property management.opentelemetry.otlp.endpoint để fallback chung như Boot 4. Không dùng ví dụ Boot 4 cho dự án Boot 3.5 rồi kết luận exporter đã được cấu hình.

| Chủ đề | Spring Boot 3.5.x | Spring Boot 4.x |
| --- | --- | --- |
| Common OTLP endpoint fallback | Không có cùng property common | management.opentelemetry.otlp.endpoint |
| Traces endpoint | management.otlp.tracing.endpoint | management.opentelemetry.tracing.export.otlp.endpoint |
| Metrics endpoint | management.otlp.metrics.export.url | management.otlp.metrics.export.url |
| Logs OTLP | Không cùng mô hình common logs exporter | Có logging OTLP properties |
| Common headers/compression | Cấu hình riêng theo exporter | Có common OTLP properties và signal override |

Luôn kiểm tra version thật từ Spring Boot BOM/runtime. Không suy version chỉ từ dependency Micrometer hoặc tên module.

## 9. Ví dụ Docker/Kubernetes

Trong container, localhost trỏ tới network namespace của container ứng dụng, không nhất thiết là Collector. Dùng service DNS truy cập được từ pod:

```yaml
management:
  opentelemetry:
    otlp:
      endpoint: http://otel-collector.observability.svc.cluster.local:4318
      headers:
        Authorization: Bearer OTLP_TOKEN_FROM_SECRET
      compression: gzip
```

Khi không khai báo endpoint riêng, traces, logs và metrics fallback tới cùng host/cổng với path tương ứng.

Nếu traces và logs có gateway riêng:

```yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://otel-gateway.internal:4318
    tracing:
      export:
        otlp:
          endpoint: https://trace-gateway.internal/team-a/v1/traces
    logging:
      export:
        otlp:
          endpoint: https://log-gateway.internal/team-a/v1/logs
```

Metrics không có endpoint riêng nên fallback về Collector chung. Traces và logs dùng gateway riêng; mỗi URL riêng là URL hoàn chỉnh có path.

## 10. Kiểm chứng endpoint hiệu lực

Không chỉ nhìn YAML rồi kết luận exporter đang gửi đúng. Kiểm tra theo thứ tự:

1. Xác nhận version Spring Boot thực tế từ dependency management/build metadata.
2. Xem endpoint chung, endpoint riêng và environment variables nào được thiết lập.
3. Kiểm tra endpoint riêng có ghi đè common endpoint không.
4. Tính URL cuối: endpoint riêng dùng nguyên URL; common fallback + signal path nếu HTTP.
5. Xác nhận transport exporter khớp receiver.
6. Kiểm tra common headers và signal-specific headers đã merge đúng.
7. Gửi một trace, log record và metric sample trong môi trường thử nghiệm.
8. Kiểm tra Collector access logs để thấy request tới đúng signal path.
9. Kiểm tra Collector pipeline và backend ingest; Collector nhận được không có nghĩa backend đã lưu.
10. Bỏ endpoint riêng trong test profile để xác nhận common fallback hoạt động.

| Common endpoint | Endpoint riêng | Kết quả |
| --- | --- | --- |
| https://collector:4318 | Không có, traces HTTP | https://collector:4318/v1/traces |
| https://collector:4318 | Không có, logs HTTP | https://collector:4318/v1/logs |
| https://collector:4318 | Không có, metrics HTTP | https://collector:4318/v1/metrics |
| https://collector:4318 | https://trace.example/custom | https://trace.example/custom |

## 11. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Traces tới đúng Collector, metrics không tới | Metrics exporter chưa bật hoặc URL riêng ghi đè | Kiểm tra management.otlp.metrics.export.enabled/url |
| Logs thiếu dù traces có | Logging exporter hoặc Collector logs pipeline chưa bật | Kiểm tra logging OTLP exporter và receiver |
| Request tới /v1/traces/v1/traces | Common endpoint đã chứa suffix và fallback nối thêm | Bỏ signal path khỏi common base URL |
| Request tới / thay vì /v1/metrics | Signal endpoint riêng dùng nguyên dạng nhưng thiếu path | Đặt endpoint riêng đầy đủ /v1/metrics |
| HTTP 404 | Sai route hoặc gateway chưa route signal path | Kiểm tra path và receiver |
| HTTP 415 | Sai content type/protocol hoặc nhầm HTTP/gRPC port | Khớp transport và receiver |
| HTTP 401/403 | Token/headers sai hoặc thiếu quyền ingest | Kiểm tra secret và header precedence |
| Common endpoint không có hiệu lực | Signal-specific property hoặc env var override | Kiểm tra endpoint riêng và property sources |
| Common header biến mất | Signal-specific header trùng key ghi đè | Kiểm tra merge rules |
| Common URL đúng nhưng timeout | DNS, network policy, TLS, receiver hoặc port | Kiểm tra từ đúng container/pod |
| Boot 3.5 không nhận common endpoint | Dùng property Boot 4 trong dự án 3.5 | Dùng property riêng theo signal của 3.5 |
| Collector nhận nhưng backend trống | Collector exporter/backend ingest lỗi | Kiểm tra pipeline và backend logs |

### 11.1. Vì sao common endpoint không nên chứa signal path?

Giả sử common endpoint là:

```yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://collector.example/otlp/v1/traces
```

Khi dùng làm common fallback cho cả traces, logs và metrics qua HTTP, Boot thêm path signal vào base URL. Với logs, URL có thể thành dạng:

https://collector.example/otlp/v1/traces/v1/logs

Đây thường không phải route logs mà gateway mong đợi.

Cách sửa:
- Common endpoint chỉ chứa scheme, host, port và base path chung mà Collector/gateway hỗ trợ.
- Nếu gateway cần path riêng theo signal, cấu hình endpoint riêng cho từng signal.
- Không đoán path gateway; kiểm tra route thực trong môi trường triển khai.

## 12. Bảo mật và vận hành

- Lưu token trong secret store hoặc environment secret; không commit token.
- Dùng TLS khi gửi qua network không tin cậy và xác minh certificate.
- Giới hạn quyền nhận OTLP theo service/environment/tenant.
- Dùng common headers cho thông tin thực sự chung; dùng credentials riêng nếu quyền ingest khác nhau.
- Không log Authorization headers hoặc payload telemetry đầy đủ ở production.
- Cấu hình timeout, batch, queue, retry và compression theo năng lực Collector/backend.
- Theo dõi exporter failures, dropped spans/logs/metrics và Collector queue saturation.
- Kiểm thử signal-specific path khi dùng gateway/reverse proxy.
- Không để endpoint mặc định localhost tồn tại ngoài môi trường mà nó thực sự trỏ tới Collector.
- Đảm bảo Collector có pipeline nhận và export cho từng signal.

## 13. Câu hỏi tự luyện

1. Common endpoint và signal-specific endpoint có quan hệ ưu tiên như thế nào?
2. Với common endpoint https://collector.example:4318, traces/logs/metrics dùng các URL HTTP nào?
3. Vì sao endpoint riêng https://trace.example/custom được dùng nguyên URL, không tự nối path?
4. Khi common headers có Authorization A và tracing-specific headers có Authorization B, traces gửi token nào?
5. OTEL_EXPORTER_OTLP_ENDPOINT khác OTEL_EXPORTER_OTLP_TRACES_ENDPOINT ra sao?
6. Vì sao common endpoint fallback qua HTTP cần thêm signal path?
7. Nếu common endpoint đã chứa /v1/traces, điều gì có thể xảy ra với logs và metrics?
8. Vì sao không copy management.opentelemetry.otlp.endpoint của Boot 4 vào dự án Boot 3.5?
9. Khi exporter gửi tới cổng 4317 nhưng dùng HTTP transport, lỗi có thể biểu hiện thế nào?
10. Collector nhận spans nhưng backend không có trace; cần kiểm tra pipeline nào?
11. Khi nào nên dùng common endpoint, khi nào override một signal?
12. Làm thế nào kiểm thử endpoint fallback trong môi trường container?

## Tài liệu tham khảo

- [Spring Boot 4.0 — Observability and Common OTLP Configuration](https://docs.spring.io/spring-boot/4.0/reference/actuator/observability.html)
- [Spring Boot 4.0 — Common Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/index.html)
- [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html)
- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/)
- [OpenTelemetry — OTLP Exporter Configuration](https://opentelemetry.io/docs/languages/sdk-configuration/otlp-exporter/)


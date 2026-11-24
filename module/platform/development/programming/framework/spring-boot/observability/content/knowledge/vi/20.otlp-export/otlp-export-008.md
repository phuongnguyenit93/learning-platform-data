# management.opentelemetry

Trong mô-đun **SPRING_BOOT_OBSERVABILITY**, Spring Boot kết hợp Micrometer Observation, metrics, logs và distributed tracing để giúp đội phát triển quan sát hành vi ứng dụng. Namespace cấu hình **management.opentelemetry** là một phần tích hợp OpenTelemetry trong Spring Boot Actuator. Nó điều khiển một số hành vi OpenTelemetry do Boot quản lý, trong đó có bật/tắt hỗ trợ, resource attributes, ánh xạ một tập environment variables và cấu hình OTLP dùng chung ở các phiên bản hỗ trợ.

Điểm quan trọng là namespace này **không phải công tắc chung tự động xuất mọi telemetry**. Traces, logs và metrics vẫn có pipeline, dependency và mức auto-configuration riêng. Spring Boot dùng Micrometer cho metrics và Observation/Tracing cho traces; OpenTelemetry Logs SDK có cấu hình riêng; việc chuyển log events từ SLF4J/Logback sang OpenTelemetry cũng là một ranh giới tích hợp khác. Bài này giải thích cách đọc và dùng management.opentelemetry chính xác, tránh cấu hình endpoint sai hoặc kỳ vọng một tín hiệu được xuất chỉ vì tín hiệu khác đang hoạt động.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Xác định vai trò của namespace management.opentelemetry trong Spring Boot Actuator.
2. Phân biệt hỗ trợ OpenTelemetry cơ bản, Micrometer Tracing, OpenTelemetry Logs SDK và Micrometer metrics.
3. Cấu hình resource attributes như service.name, service.version và deployment.environment.
4. Thiết lập OTLP endpoint, headers, compression ở cấp dùng chung và cấp tín hiệu.
5. Hiểu thứ tự ưu tiên giữa common properties, signal-specific properties và environment variables.
6. Phân biệt OTLP/HTTP với OTLP/gRPC và hiểu cách hình thành signal path.
7. Biết khi nào Boot tự cấu hình xuất traces, khi nào cần cấu hình riêng cho logs/metrics.
8. Kiểm tra tác động của enabled, custom Resource bean và map-environment-variables.
9. Bảo vệ credentials, giới hạn payload và theo dõi tình trạng export.
10. Chẩn đoán trường hợp có traces nhưng không có logs/metrics hoặc service identity sai.

## 2. Namespace management.opentelemetry đứng ở đâu?

Spring Boot Actuator cung cấp hỗ trợ OpenTelemetry ở mức tích hợp với application context. Ở các phiên bản có hỗ trợ tương ứng, Boot có thể tạo OpenTelemetry bean và Resource bean; các SDK providers như SdkTracerProvider, SdkLoggerProvider, ContextPropagators hoặc SdkMeterProvider nếu được đăng ký trong application context có thể được gắn vào OpenTelemetry instance do Boot quản lý.

Các nhóm property chính:

| Nhóm property | Vai trò |
| --- | --- |
| management.opentelemetry.enabled | Bật/tắt hỗ trợ OpenTelemetry của Spring Boot. |
| management.opentelemetry.resource-attributes | Khai báo resource attributes cho telemetry. |
| management.opentelemetry.map-environment-variables | Điều khiển ánh xạ một tập OpenTelemetry SDK environment variables sang Spring Boot properties. |
| management.opentelemetry.otlp | Cấu hình OTLP chung như endpoint, headers và compression ở phiên bản hỗ trợ. |
| management.opentelemetry.tracing | Cấu hình sampler, export và giới hạn liên quan tới traces. |
| management.opentelemetry.logging | Cấu hình export và giới hạn của OpenTelemetry logs ở phiên bản hỗ trợ. |

~~~mermaid
flowchart TB
    Config["application.yml / environment"]
    Config --> Manage["Spring Boot Actuator"]
    Manage --> OTEL["OpenTelemetry bean"]
    Manage --> Resource["Resource attributes"]
    OTEL --> Trace["SdkTracerProvider / Micrometer Tracing"]
    OTEL --> Logs["SdkLoggerProvider / OTel Logs"]
    OTEL --> Metrics["SdkMeterProvider nếu ứng dụng tự dùng"]
    Trace --> TraceExport["OTLP traces exporter"]
    Logs --> LogExport["OTLP logs exporter"]
    Metrics --> MetricExport["OTLP metrics exporter"]
    TraceExport --> Collector["OTLP Collector"]
    LogExport --> Collector
    MetricExport --> Collector
~~~

Sơ đồ biểu diễn các thành phần có thể tham gia cùng OpenTelemetry instance. Nó không có nghĩa Spring Boot luôn tự tạo cả ba SDK providers hoặc tự xuất ba tín hiệu. Cần đọc đúng phiên bản và cấu hình auto-configuration thực tế.

## 3. Kiểm tra phiên bản trước khi dùng property

Namespace và phạm vi auto-configuration khác biệt giữa các dòng Spring Boot. Tài liệu Spring Boot 4.2 mô tả cấu hình OTLP chung dưới management.opentelemetry.otlp, signal-specific properties cho tracing/logging và auto-configuration logging qua OTLP. Tài liệu Spring Boot 3.5 mô tả hỗ trợ OpenTelemetry cơ bản và resource attributes, nhưng không trình bày cùng bộ common OTLP properties và logging auto-configuration như tài liệu 4.2.

Vì vậy:

- Đừng giả định mọi property trong bài đều có mặt ở Spring Boot 3.x.
- Với Boot 3.5, kiểm tra Appendix Application Properties và reference đúng minor version; một số tính năng OpenTelemetry có phạm vi hẹp hơn.
- Với Boot 4.x, đối chiếu documentation đúng minor release vì property names/defaults có thể thay đổi.
- Nếu property không được bind, kiểm tra configuration metadata và startup logs thay vì suy đoán.
- Không thêm exporter/dependency chỉ vì thấy property trong tài liệu của phiên bản khác.

Tài liệu chính thức cần đối chiếu:
- Spring Boot Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- Spring Boot 3.5 Observability: https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html
- Spring Boot Application Properties: https://docs.spring.io/spring-boot/appendix/application-properties/

## 4. Bật/tắt hỗ trợ OpenTelemetry

Ở các phiên bản hỗ trợ, property enabled điều khiển tích hợp OpenTelemetry của Boot:

~~~yaml
management:
  opentelemetry:
    enabled: true
~~~

Có thể tắt:

~~~yaml
management:
  opentelemetry:
    enabled: false
~~~

Khi đặt false, các thành phần OpenTelemetry liên quan có thể dùng no-op implementations theo mô tả của phiên bản Boot; context propagators có thể vẫn tiếp tục hoạt động. Điều này **không đồng nghĩa tất cả metrics của ứng dụng đều tắt**, vì Spring Boot dùng Micrometer làm lựa chọn metrics chính. Micrometer registry vẫn có thể thu thập/xuất metrics qua pipeline riêng.

Đừng dùng enabled=false như cách thay thế cho việc tắt riêng OTLP logs hoặc traces. Nếu chỉ muốn ngừng gửi một tín hiệu, cấu hình export của đúng tín hiệu đó. Sau khi thay đổi, xác minh metrics endpoint, traces và logs riêng rẽ.

## 5. Cấu hình Resource attributes

Resource mô tả nguồn phát telemetry, chẳng hạn service name, version, môi trường và namespace. Nó được dùng để nhóm logs/traces/metrics theo service hoặc deployment context.

~~~yaml
spring:
  application:
    name: order-api

management:
  opentelemetry:
    resource-attributes:
      service.name: order-api
      service.version: "2.3.1"
      deployment.environment: production
      service.namespace: commerce
~~~

Đây là ví dụ. Trong hệ thống thật, service name/version/environment nên đến từ cấu hình deployment hoặc build metadata.

Nguyên tắc:
- service.name phải ổn định và giống nhau giữa signals của cùng service.
- service.version hữu ích khi so sánh trước/sau release.
- deployment.environment hoặc namespace giúp tách production, staging và development.
- Không đặt request ID, order ID, email hoặc user ID vào Resource; các giá trị đó thay đổi theo từng request và làm nổ số resource groups.
- Resource attributes mô tả process/service; span/log attributes mô tả một hoạt động hay sự kiện.

### Ưu tiên giữa property và environment

Tài liệu Spring Boot mô tả Resource auto-configured được hợp nhất với OTEL_RESOURCE_ATTRIBUTES và OTEL_SERVICE_NAME; các thuộc tính cấu hình qua management.opentelemetry.resource-attributes có độ ưu tiên cao hơn các environment variables đó.

Ví dụ environment:

~~~text
OTEL_SERVICE_NAME=order-api-default
OTEL_RESOURCE_ATTRIBUTES=service.version=2.3.0,deployment.environment=staging
~~~

Nếu cấu hình file:

~~~yaml
management:
  opentelemetry:
    resource-attributes:
      service.version: "2.3.1"
      deployment.environment: production
~~~

Các giá trị khai báo trong Spring Boot property thắng khi có xung đột theo quy tắc merge. Kiểm tra Resource thực tế trong exporter/backend vì việc merge này áp dụng cho Resource auto-configured của Boot.

**Nếu ứng dụng tự khai báo Resource bean**, quy trình auto-configured merge nói trên sẽ không còn áp dụng như cũ. Khi tạo Resource bean tùy chỉnh, ứng dụng phải tự chịu trách nhiệm hợp nhất các thuộc tính cần thiết, gồm service identity và environment metadata.

## 6. Cấu hình OTLP dùng chung

Ở các phiên bản Spring Boot có common OTLP configuration, có thể khai báo một endpoint, headers và compression dùng chung cho các tín hiệu:

~~~yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://otlp.example.com:4318
      compression: gzip
      headers:
        Authorization: Bearer REPLACE_WITH_SECRET
~~~

Ý nghĩa:
- endpoint là base endpoint chung của OTLP exporter.
- compression cấu hình phương thức nén payload nếu exporter/tín hiệu hỗ trợ.
- headers mang thông tin cần thiết để exporter xác thực hoặc định tuyến.
- credentials lấy từ secret manager/environment injection; không commit token thật trong repository.

Exporter của từng signal có thể cần endpoint riêng, transport riêng hoặc credentials riêng.

### Common và signal-specific properties

Các property riêng theo tín hiệu có độ ưu tiên cao hơn common values khi được đặt:

| Tín hiệu | Endpoint riêng minh họa |
| --- | --- |
| Traces | management.opentelemetry.tracing.export.otlp.endpoint |
| Logs | management.opentelemetry.logging.export.otlp.endpoint |
| Metrics | management.otlp.metrics.export.url |

Đối với headers, headers của từng signal được merge với common headers; giá trị signal-specific thắng khi trùng key.

~~~yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://collector.example.com:4318
      compression: gzip
      headers:
        Authorization: Bearer COMMON_SECRET
    tracing:
      export:
        otlp:
          endpoint: https://trace-gateway.example.com:4318
    logging:
      export:
        otlp:
          endpoint: https://logs-gateway.example.com:4318
~~~

Trong ví dụ, traces và logs đi tới gateway riêng; endpoint chung dùng làm fallback cho tín hiệu chưa có endpoint cụ thể. Không dùng ví dụ này nếu Spring Boot minor version không có logging export namespace tương ứng.

## 7. Endpoint chung, signal path và OTLP transport

Khi endpoint chung được dùng làm fallback và signal export qua HTTP, Spring Boot thêm signal-specific path:

| Signal | HTTP path |
| --- | --- |
| Traces | /v1/traces |
| Logs | /v1/logs |
| Metrics | /v1/metrics |

Ví dụ endpoint chung là https://collector.example.com:4318, các URL HTTP cuối có thể là:
- https://collector.example.com:4318/v1/traces
- https://collector.example.com:4318/v1/logs
- https://collector.example.com:4318/v1/metrics

Khi signal-specific endpoint được đặt, nó được dùng theo quy tắc riêng của property đó; không giả định common path được nối vào mọi endpoint đã chỉ định.

### HTTP và gRPC khác nhau

| Thuộc tính | OTLP/HTTP | OTLP/gRPC |
| --- | --- | --- |
| Cổng thường dùng | 4318 | 4317 |
| Signal path | /v1/traces, /v1/logs, /v1/metrics | RPC services, không dùng URL path HTTP signal như trên |
| Protocol | HTTP/protobuf | gRPC |
| Kiểm thử | HTTP status/receiver logs | gRPC status/connectivity/receiver logs |

Các cổng là mặc định thường gặp, có thể được thay trong Collector. Phải bảo đảm exporter transport khớp receiver. Không đổi 4318 thành 4317 trong endpoint HTTP rồi kỳ vọng client tự chuyển sang gRPC.

## 8. Environment variables và map-environment-variables

Spring Boot hỗ trợ ánh xạ một tập con OpenTelemetry SDK environment variables sang configuration properties khi khởi động. Property map-environment-variables điều khiển hành vi này ở các phiên bản hỗ trợ:

~~~yaml
management:
  opentelemetry:
    map-environment-variables: true
~~~

Có thể tắt mapping:

~~~yaml
management:
  opentelemetry:
    map-environment-variables: false
~~~

Khi dùng mapping, signal-specific environment variable được ưu tiên so với biến tổng quát. Nếu dùng general endpoint làm fallback, Spring Boot nối signal path khi export HTTP. Environment variable không được hỗ trợ sẽ không tự động có tác dụng chỉ vì bắt đầu bằng OTEL_.

Ví dụ:

~~~text
OTEL_EXPORTER_OTLP_ENDPOINT=https://collector.example.com:4318
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://trace-gateway.example.com:4318/custom-traces
OTEL_SERVICE_NAME=order-api
OTEL_RESOURCE_ATTRIBUTES=service.version=2.3.1,deployment.environment=production
~~~

Với một biến thuộc tập hỗ trợ, Spring Boot map nó sang property khi khởi động. General endpoint làm fallback cho traces có thể tạo URL /v1/traces; signal-specific endpoint được sử dụng theo giá trị riêng đã đặt.

### Không phải mọi OpenTelemetry SDK environment variables đều được hỗ trợ

Tài liệu Spring Boot liệt kê rõ chỉ hỗ trợ một subset. Nếu cần mọi biến môi trường mà OpenTelemetry SDK hiểu, tài liệu chỉ ra có thể cung cấp OpenTelemetry bean riêng bằng SDK autoconfigure; nhưng làm vậy sẽ chuyển quyền sở hữu OpenTelemetry auto-configuration ra khỏi Spring Boot và có thể làm hỏng các tích hợp observability built-in.

Vì vậy:
1. Kiểm tra danh sách mapping trong tài liệu đúng version.
2. Chỉ bật mapping khi muốn Spring Boot áp dụng tập variables được hỗ trợ.
3. Nếu một biến không được hỗ trợ, không giả định Boot sẽ đọc nó.
4. Chỉ thay thế Boot auto-configuration bằng OpenTelemetry SDK autoconfigure khi có yêu cầu rõ ràng và đã kiểm tra các tính năng bị ảnh hưởng.

## 9. Traces: relationship với Micrometer Tracing

Spring Boot tích hợp OpenTelemetry tracing thông qua Micrometer Tracing. Khi có Micrometer Tracing và dependencies/configuration tương ứng, Boot có thể cấu hình SdkTracerProvider và xuất traces qua OTLP. Các property thường dùng nằm dưới tracing export namespace trong management.opentelemetry ở những phiên bản hỗ trợ.

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.1
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: https://collector.example.com:4318
          transport: http
          timeout: 10s
          compression: gzip
          headers:
            Authorization: Bearer TRACE_SECRET
~~~

Cần kiểm tra tên property, đơn vị timeout và giá trị transport hợp lệ theo version. Đừng ghép cấu hình này với exporter bean tự tạo và agent cùng lúc nếu không có chủ đích; nhiều SDK/exporter có thể gây duplicate spans hoặc pipeline tách rời.

Một số export settings có liên quan:
- schedule delay/batch size/queue size kiểm soát batching và áp lực bộ nhớ.
- export timeout giới hạn thời gian exporter chờ.
- attribute/event/link limits giới hạn kích thước span.
- SSL bundle hoặc trust/client certificate thiết lập TLS/mTLS theo cách ứng dụng quản lý.

Sampling probability không phải endpoint configuration. Thay đổi sampling và export transport giải quyết hai vấn đề khác nhau.

## 10. Logs: không đồng nghĩa với trace export

OpenTelemetry Logs SDK có SdkLoggerProvider và OTLP logs exporter. Trong các phiên bản Spring Boot hỗ trợ logging auto-configuration, Boot có thể cấu hình SdkLoggerProvider và OTLP logging exporter qua logging export properties.

~~~yaml
management:
  opentelemetry:
    logging:
      export:
        otlp:
          endpoint: https://logs.example.com:4318
          transport: http
          compression: gzip
          timeout: 10s
~~~

Tuy nhiên, **có SdkLoggerProvider không tự động có nghĩa log statements của SLF4J/Logback đã được bridge vào provider**. Spring Boot không tự cung cấp bridge đó out of the box theo tài liệu hiện tại. Cần một logging bridge/appender tương thích hoặc code phát log qua OpenTelemetry Logs API.

Cần phân biệt:
- Trace correlation đưa trace ID/span ID vào log context giúp tìm logs liên quan tới trace.
- OTLP logs export chuyển log records tới Collector.
- Pipeline có correlation chưa chắc có OTLP logs export.
- Pipeline có OTLP log exporter chưa chắc đang nhận SLF4J events.

Không dùng property tracing endpoint để suy ra logs endpoint đã được cấu hình.

## 11. Metrics: Spring Boot chọn Micrometer

Trong Spring Boot, metrics chủ yếu đi qua Micrometer, không phải OpenTelemetry SdkMeterProvider. Vì vậy cấu hình dưới management.opentelemetry không thay thế cấu hình Micrometer registry.

Ví dụ dùng OTLP MeterRegistry:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: https://collector.example.com:4318/v1/metrics
        step: 30s
        enabled: true
        compression: gzip
~~~

Property cụ thể cần khớp registry/dependency và phiên bản Boot. Đây là pipeline Micrometer metrics. Nếu một dependency tự dùng OpenTelemetry MeterProvider, cần cấu hình SDK/exporter tương ứng và wire MeterProvider vào dependency đó; không mặc định metric từ OTel MeterProvider được xuất cùng Micrometer registry.

Resource attributes cấu hình trong Boot có thể được dùng bởi một số tích hợp OTLP metrics, nhưng Micrometer OTLP registry có các quy tắc riêng. Kiểm tra payload thực tế để xác nhận service identity và dimensions.

## 12. Cấu hình mẫu theo ba tín hiệu

Ví dụ dưới đây thể hiện cách tổ chức cấu hình cho phiên bản Spring Boot có hỗ trợ common OTLP endpoint và signal-specific logging/tracing properties. Cần thêm dependencies phù hợp cho mỗi pipeline.

~~~yaml
spring:
  application:
    name: order-api

management:
  opentelemetry:
    enabled: true
    resource-attributes:
      service.name: order-api
      service.version: "2.3.1"
      deployment.environment: production
      service.namespace: commerce
    otlp:
      endpoint: https://collector.example.com:4318
      compression: gzip
      headers:
        Authorization: Bearer OTLP_SECRET
    tracing:
      export:
        otlp:
          transport: http
          timeout: 10s
    logging:
      export:
        otlp:
          transport: http
          timeout: 10s
  tracing:
    sampling:
      probability: 0.1
  otlp:
    metrics:
      export:
        url: https://collector.example.com:4318/v1/metrics
        step: 30s
        enabled: true
~~~

Cấu hình thể hiện:
- Resource metadata dùng chung để nhận diện service.
- Common OTLP endpoint/headers/compression cho signal exporters hỗ trợ common properties.
- Traces có sampling riêng và Micrometer Tracing integration.
- Logs có logging pipeline riêng; cần đường chuyển log events phù hợp.
- Metrics xuất qua Micrometer OTLP registry với cấu hình của registry.

Không copy nguyên YAML vào mọi phiên bản Spring Boot. So sánh property metadata của dự án với version docs, kiểm tra dependencies và xác nhận exporter bean thực tế được tạo.

## 13. Bảo mật endpoint và headers

OTLP exporter thường gửi telemetry qua network. Những cấu hình cần được xử lý:

- Dùng HTTPS/TLS khi export qua network không tin cậy.
- Dùng mTLS nếu nền tảng yêu cầu client certificate.
- Lưu token/API key trong secret manager hoặc environment injection, không commit giá trị thật.
- Giới hạn quyền ghi/đọc telemetry ở Collector và backend.
- Không log headers chứa Authorization khi debug exporter.
- Dùng endpoint nội bộ và network policy khi Collector chỉ dành cho cluster.
- Xoay vòng credentials và kiểm tra exporter có reload secret/certificate hay không.

Ví dụ dùng placeholder:

~~~yaml
management:
  opentelemetry:
    otlp:
      endpoint: https://otlp.internal.example
      headers:
        Authorization: Bearer REPLACE_WITH_SECRET
~~~

Không đưa bearer token vào URL, span attributes, baggage hoặc log message. Không bật plaintext chỉ để tạm thời vượt lỗi certificate mà không hiểu trust boundary.

### Headers chung và headers riêng

Common headers có thể dùng cho nhiều signal. Signal-specific headers có thể bổ sung hoặc ghi đè một key trùng tên. Điều này hữu ích khi traces và logs đi qua các gateway có credentials khác nhau, nhưng cũng tạo rủi ro nếu một token vô tình được gửi tới endpoint khác.

Khi tách endpoints, rà soát header Authorization nào được gửi tới từng đích, TLS certificate/hostname, proxy/gateway forwarding và việc log header values.

## 14. Troubleshooting: property được khai báo nhưng exporter không gửi

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| management.opentelemetry không có tác dụng | Spring Boot version không hỗ trợ property đó hoặc YAML indentation sai. | Kiểm tra version reference/configuration metadata và startup logs. |
| Resource service.name không đúng | Environment variable merge hoặc custom Resource bean thay auto-configured Resource. | Kiểm tra Resource bean/payload và precedence. |
| Có traces nhưng logs trống | Chưa cấu hình OTel logs pipeline, thiếu bridge/appender hoặc Collector chưa nhận logs. | Kiểm tra logging exporter, appender/bridge và logs receiver. |
| Có metrics nhưng không có traces | Micrometer registry hoạt động nhưng thiếu Micrometer Tracing bridge/exporter hoặc sampler bỏ trace. | Kiểm tra tracing dependencies, sampling và trace pipeline. |
| Có traces nhưng không có metrics | Không có Micrometer registry exporter hoặc registry chưa enabled. | Kiểm tra dependency và metrics export property. |
| HTTP endpoint trả 404/415 | Sai path hoặc content type/transport. | Kiểm tra OTLP HTTP /v1/{signal} và receiver protocol. |
| Lỗi kết nối cổng 4317/4318 | Transport và listener không khớp, DNS/host sai. | Kiểm tra OTLP/gRPC so với OTLP/HTTP, listener và network. |
| Common endpoint không tạo path mong muốn | Đã đặt signal-specific endpoint hoặc transport không phải HTTP. | Kiểm tra precedence và endpoint thực tế từng exporter. |
| Environment variable không được áp dụng | Biến không thuộc subset Boot map hoặc mapping đã tắt. | Kiểm tra map-environment-variables và danh sách hỗ trợ đúng version. |
| Export 401/403 | Token sai/hết hạn, header key sai hoặc quyền ingest thiếu. | Kiểm tra credential qua secret store và gateway policy. |
| Export timeout/queue đầy | Collector/backend chậm hoặc exporter batch/timeout không phù hợp. | Đo exporter errors, queue, backend capacity và batch settings. |
| Backend chia một service thành nhiều nhóm | service.name/version/environment không nhất quán. | Chuẩn hóa Resource attributes giữa replicas/releases. |

Một cấu hình được bind thành công cũng chưa chứng minh Collector nhận dữ liệu. Hãy quan sát từng ranh giới: application provider → processor/exporter → network → Collector receiver → pipeline processor → backend ingestion/index.

## 15. Runbook xác minh management.opentelemetry

1. **Xác nhận phiên bản:** lấy Spring Boot version thực tế từ build/dependency report; mở reference docs đúng minor version.
2. **Kiểm tra property binding:** xem cảnh báo unknown/unbound properties và xác nhận YAML indentation.
3. **Kiểm tra bean:** xác định OpenTelemetry, Resource, SdkTracerProvider, SdkLoggerProvider và exporter/registry nào thực sự tồn tại.
4. **Kiểm tra resource:** xem service.name, service.version, environment trong payload/backend.
5. **Kiểm tra endpoint cuối:** xác định common endpoint hay signal-specific endpoint đang được dùng; với HTTP kiểm tra path cuối.
6. **Kiểm tra transport:** xác nhận exporter HTTP tới HTTP receiver hoặc gRPC tới gRPC receiver.
7. **Kiểm tra từng signal:** trace, log và metric có pipeline riêng; tạo mẫu rõ ràng cho mỗi loại.
8. **Kiểm tra Collector:** receivers, pipelines, exporters, authentication và dropped/refused counters.
9. **Kiểm tra backend:** ingestion/index latency, retention, tenant routing và query time range.
10. **Kiểm tra bảo mật:** credentials được lấy từ secret store và không xuất hiện trong logs/traces.

Khi chỉ một signal gặp lỗi, sửa cấu hình của đúng signal đó. Không tăng sampling hoặc tạo SDK thứ hai chỉ để giải quyết lỗi endpoint.

## 16. Bài tập tự kiểm tra

### Bài 1 — Common endpoint

Bạn cấu hình common OTLP endpoint là https://collector.example.com:4318 và exporter dùng HTTP. Traces không có signal-specific endpoint. Path được dùng sẽ như thế nào?

**Đáp án:** Với common endpoint fallback qua HTTP, Spring Boot nối path của signal; traces dùng /v1/traces. Logs và metrics dùng path tương ứng nếu pipeline/exporter của các signal đó được bật.

### Bài 2 — Endpoint riêng có ưu tiên không?

Common endpoint được khai báo, đồng thời tracing.export.otlp.endpoint cũng được đặt. Exporter traces dùng địa chỉ nào?

**Đáp án:** Signal-specific endpoint được ưu tiên khi đã đặt. Common endpoint làm fallback cho signal chưa có endpoint riêng.

### Bài 3 — Có traces nhưng không có logs

Ứng dụng gửi traces thành công tới Collector nhưng logs không xuất hiện. Có thể chỉ thêm trace exporter dependency không?

**Đáp án:** Không. Logs cần OpenTelemetry Logs SDK/exporter hoặc logging pipeline tương ứng, Collector logs receiver và đường tích hợp log events từ logging framework nếu nguồn log là SLF4J/Logback.

### Bài 4 — Metrics của Micrometer

Ứng dụng có Micrometer MeterRegistry. Tắt OpenTelemetry support có chắc chắn làm metrics ngừng thu thập không?

**Đáp án:** Không. Spring Boot dùng Micrometer cho metrics; metrics có thể tiếp tục hoạt động qua registry riêng kể cả khi OpenTelemetry SDK support bị tắt.

### Bài 5 — Resource bean tùy chỉnh

Sau khi thêm Resource bean riêng, service.name không còn được merge như trước. Nguyên nhân có thể là gì?

**Đáp án:** Việc tự định nghĩa Resource bean làm thay đổi cơ chế auto-configured Resource merge của Spring Boot. Ứng dụng cần tự hợp nhất các resource attributes muốn giữ.

### Bài 6 — Environment variable không hiệu lực

Bạn đặt một OTEL_* environment variable nhưng property không đổi. Lý do nào cần kiểm tra trước?

**Đáp án:** Spring Boot chỉ map một subset environment variables; kiểm tra danh sách hỗ trợ theo phiên bản và map-environment-variables. Không phải mọi biến của OpenTelemetry SDK đều tự động được ánh xạ.

## 17. Checklist triển khai

- [ ] Đã xác định Spring Boot version và kiểm tra tài liệu đúng minor release.
- [ ] Hiểu management.opentelemetry là cấu hình tích hợp OpenTelemetry, không phải công tắc tự xuất mọi signal.
- [ ] enabled được đặt theo mục tiêu; không dùng nó thay export property của riêng signal.
- [ ] Resource attributes có service.name/version/environment nhất quán.
- [ ] Không đưa request/user/customer IDs vào Resource.
- [ ] Biết custom Resource bean làm thay đổi cơ chế merge mặc định.
- [ ] Common OTLP endpoint/headers/compression được dùng có chủ đích.
- [ ] Signal-specific endpoint/headers được kiểm tra precedence.
- [ ] HTTP paths /v1/traces, /v1/logs, /v1/metrics và OTLP/gRPC transport không bị nhầm.
- [ ] Environment variables chỉ được dựa vào khi nằm trong subset Boot hỗ trợ.
- [ ] Micrometer Tracing được cấu hình cho trace export.
- [ ] Logs có SDK/exporter và logging bridge/appender phù hợp khi cần.
- [ ] Metrics được xuất qua Micrometer registry hoặc SDK pipeline được wire rõ ràng.
- [ ] TLS/auth và secrets được quản lý qua nền tảng phù hợp.
- [ ] Collector có receiver/pipeline/exporter cho từng signal.
- [ ] Có bằng chứng backend ingest và truy vấn được logs/traces/metrics.
- [ ] Có theo dõi timeout, queue, retry, dropped records và backend capacity.

**Ghi nhớ:** management.opentelemetry giúp Spring Boot cấu hình phần tích hợp OpenTelemetry như resource, common OTLP settings và thuộc tính theo tín hiệu trong các phiên bản hỗ trợ. Luôn xác nhận version, precedence và pipeline riêng của traces, logs, metrics. Micrometer Tracing tích hợp tracing; Micrometer là đường metrics chính của Spring Boot; logs cần OpenTelemetry Logs pipeline và bridge phù hợp. Kiểm tra dữ liệu từ application tới Collector/backend mới chứng minh export đã hoạt động.

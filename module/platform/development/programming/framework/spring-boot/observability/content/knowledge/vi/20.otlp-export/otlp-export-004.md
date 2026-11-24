# OTLP HTTP endpoint trong Spring Boot Observability

Trong chương **OTLP export** của module **SPRING_BOOT_OBSERVABILITY**, OTLP HTTP endpoint là địa chỉ HTTP mà OpenTelemetry exporter dùng để gửi telemetry tới OpenTelemetry Collector hoặc backend tương thích. Khi ứng dụng Spring Boot ghi nhận metrics, logs và distributed traces, endpoint, protocol, đường dẫn, encoding và cấu hình mạng phải khớp với receiver phía đích. Một endpoint sai có thể khiến code vẫn tạo span hoặc measurement bình thường nhưng backend không nhận được dữ liệu.

OTLP là **OpenTelemetry Protocol**. Protocol định nghĩa cách truyền traces, metrics và logs; nó có thể chạy trên gRPC hoặc HTTP/protobuf. Bài này tập trung vào **OTLP over HTTP**, các đường dẫn chuẩn, cách cấu hình Spring Boot/Micrometer và OpenTelemetry SDK, vai trò của Collector, xác thực/TLS, batching/retry, cùng cách kiểm chứng end-to-end.

Module **SPRING_BOOT_OBSERVABILITY** hướng tới Micrometer Observation, metrics, logs và distributed tracing, bao gồm propagation ngữ cảnh, tag/cardinality, exporter và sampling. OTLP export là một mắt xích của luồng quan sát: instrumentation tạo telemetry; exporter gửi dữ liệu; collector tiếp nhận và xử lý; backend lưu trữ và truy vấn. **Đặt URL endpoint không tự tạo instrumentation, không tự bật sampling và không biến endpoint thành nơi lưu lịch sử.**

## 1. OTLP HTTP nằm ở đâu trong kiến trúc?

Một triển khai phổ biến có ứng dụng Spring Boot gửi OTLP tới Collector nội bộ, rồi Collector định tuyến tới một hay nhiều backend:

```text
Spring Boot service
    |
    +-- Micrometer Observation / MeterRegistry --> metrics
    |
    +-- Micrometer Tracing / OpenTelemetry SDK --> traces
    |
    +-- Logging bridge / OTel Logs SDK ---------> logs
                 |
                 v
          OTLP HTTP exporter
            HTTP POST + protobuf
                 |
                 v
        OpenTelemetry Collector
          receivers / processors / exporters
                 |
        +--------+---------+
        |        |         |
        v        v         v
     Metrics   Traces     Logs
      backend  backend   backend
```

| Thành phần | Trách nhiệm |
| --- | --- |
| Instrumentation | Tạo observations, measurements, spans hoặc log records |
| SDK/provider | Quản lý lifecycle, sampling, aggregation và xử lý dữ liệu theo signal |
| OTLP exporter | Serialize và gửi telemetry qua OTLP |
| OTLP HTTP receiver | Nhận HTTP request theo đúng path/content type/protocol |
| Collector processor | Batch, filter, redact, sample hoặc transform theo cấu hình |
| Backend exporter | Chuyển dữ liệu tới hệ lưu trữ/quan sát đích |
| Observability backend | Lưu, truy vấn, dashboard và alert |

Collector thường đặt gần ứng dụng để tập trung quản lý network, authentication, routing, buffering và xử lý telemetry. Cũng có thể export trực tiếp tới backend hỗ trợ OTLP; quyết định tùy yêu cầu vận hành và bảo mật.

## 2. Ba signal và endpoint path chuẩn

OTLP HTTP dùng request riêng cho từng signal:

| Signal | HTTP path chuẩn | Payload |
| --- | --- | --- |
| Traces | `/v1/traces` | OTLP Trace request |
| Metrics | `/v1/metrics` | OTLP Metrics request |
| Logs | `/v1/logs` | OTLP Logs request |

Ví dụ Collector nhận OTLP/HTTP tại host `otel-collector` và port `4318`:

```text
http://otel-collector:4318/v1/traces
http://otel-collector:4318/v1/metrics
http://otel-collector:4318/v1/logs
```

Đây là các đường dẫn phổ biến theo OTLP/HTTP. Receiver có thể được cấu hình base path hoặc proxy prefix khác; cần xác nhận cấu hình Collector. Không nhầm port `4318` thường dùng cho OTLP/HTTP với port `4317` thường dùng cho OTLP/gRPC.

**OTLP HTTP không có nghĩa là gửi JSON tùy ý tới một REST API.** Mặc định, OTLP/HTTP truyền protobuf payload; JSON encoding là lựa chọn protocol hỗ trợ nhưng exporter và receiver phải cùng hỗ trợ/được cấu hình tương ứng. Một endpoint nhận JSON nghiệp vụ thông thường không đương nhiên là OTLP receiver.

## 3. Protobuf, JSON và HTTP headers

Với OTLP/HTTP, header request thường gặp:

```http
POST /v1/traces HTTP/1.1
Host: otel-collector:4318
Content-Type: application/x-protobuf
Content-Encoding: gzip
Authorization: Bearer <token>
```

- `Content-Type: application/x-protobuf`: payload OTLP protobuf. Với JSON encoding, media type là `application/json` nếu exporter/receiver hỗ trợ.
- `Content-Encoding: gzip`: chỉ dùng khi client thực sự nén payload và receiver hỗ trợ giải nén. Nếu không nén, có thể bỏ header.
- `Authorization`: chỉ dùng khi receiver/proxy được cấu hình cơ chế xác thực tương ứng. Không ghi token trực tiếp vào source code hoặc log.

OTLP/HTTP có semantics response được định nghĩa theo protocol. Exporter cần đọc status và thông tin lỗi để xử lý retry hoặc partial success. Collector có thể trả thành công ở lớp nhận nhưng dữ liệu vẫn bị processor/exporter phía sau loại hoặc thất bại; cần theo dõi telemetry của Collector để xác nhận toàn pipeline.

Không tự tạo JSON schema rồi POST tới endpoint chỉ vì URL kết thúc bằng `/v1/traces`. Nếu tự viết client, phải serialize đúng OTLP request envelope/protobuf hoặc JSON mapping được định nghĩa và xử lý response theo chuẩn.

## 4. Endpoint cụ thể và endpoint base

Exporter có thể dùng URL signal-specific đầy đủ hoặc endpoint gốc tùy API và biến môi trường:

| Cách cấu hình | Ví dụ | Lưu ý |
| --- | --- | --- |
| Signal-specific traces URL | `http://otel-collector:4318/v1/traces` | Địa chỉ hoàn chỉnh cho trace exporter |
| Base endpoint | `http://otel-collector:4318` | SDK thường tự nối path theo signal khi dùng endpoint chung |
| Signal-specific variable | `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Thường là URL đầy đủ cho traces |
| Generic variable | `OTEL_EXPORTER_OTLP_ENDPOINT` | Thường là base endpoint, SDK nối signal path theo quy ước |

Với OTLP/HTTP, generic `OTEL_EXPORTER_OTLP_ENDPOINT` thường là base URL; biến signal-specific như `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` và `OTEL_EXPORTER_OTLP_LOGS_ENDPOINT` chỉ định endpoint riêng cho signal. Không nối thêm `/v1/traces` lần thứ hai vào signal-specific URL.

Ví dụ:

```bash
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_SERVICE_NAME=orders-service
```

Hoặc chỉ định riêng traces:

```bash
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces
```

Tên biến, precedence và hỗ trợ của từng SDK/autoconfigure cần được kiểm tra theo phiên bản. Không giả định một property Spring Boot tự động đọc mọi biến môi trường của OpenTelemetry SDK nếu exporter được cấu hình bằng cơ chế khác.

## 5. Cấu hình Spring Boot/Micrometer Tracing

Với ứng dụng Spring Boot dùng Actuator và Micrometer Tracing, cấu hình tham khảo cho OTLP trace export có thể như sau (áp dụng cho các phiên bản hỗ trợ property tương ứng):

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
```

Giải thích:

- `spring.application.name` là tên ứng dụng; resource thực tế phải được xác minh trong backend.
- `management.tracing.sampling.probability` điều khiển sampling traces theo auto-configuration của phiên bản Spring Boot tương ứng; đây không phải cấu hình export metrics/logs.
- `management.otlp.tracing.endpoint` được một số phiên bản Spring Boot hỗ trợ cho OTLP tracing. Cần kiểm tra metadata của đúng version và exporter được auto-configure.
- Path trên là URL traces signal-specific cho OTLP/HTTP. Nếu property hoặc exporter mong base endpoint, dùng đúng semantics thay vì lặp path.

Ví dụ dependency khi dùng Micrometer Tracing với OpenTelemetry bridge và OTLP exporter:

```xml
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
</dependencies>
```

Phiên bản dependency nên được Spring Boot BOM quản lý. Không trộn tùy ý Brave bridge với OpenTelemetry bridge hoặc tạo SDK thứ hai cạnh auto-configuration. **Chỉ khai báo dependency chưa chứng minh export đã hoạt động**: phải kiểm tra provider, exporter, endpoint và Collector receiver.

## 6. Cấu hình OTLP HTTP cho metrics

Spring Boot Actuator/Micrometer có thể export metrics bằng registry tương ứng; không phải mọi ứng dụng mặc định dùng OTLP metric exporter. Nếu chọn OpenTelemetry Metrics SDK, một cấu hình tham khảo độc lập có thể tạo MeterProvider, periodic reader và OTLP HTTP exporter:

```java
import io.opentelemetry.exporter.otlp.http.metrics.OtlpHttpMetricExporter;
import io.opentelemetry.sdk.metrics.SdkMeterProvider;
import io.opentelemetry.sdk.metrics.export.PeriodicMetricReader;
import java.time.Duration;

var exporter = OtlpHttpMetricExporter.builder()
        .setEndpoint("http://otel-collector:4318/v1/metrics")
        .build();

var reader = PeriodicMetricReader.builder(exporter)
        .setInterval(Duration.ofSeconds(30))
        .build();

SdkMeterProvider meterProvider = SdkMeterProvider.builder()
        .registerMetricReader(reader)
        .build();
```

Đoạn code minh họa OTLP/HTTP metric exporter trong OpenTelemetry SDK; cần dependency/version tương thích. Resource, Views, attributes và lifecycle được lược bớt để tập trung endpoint. Provider phải sống cùng ứng dụng và đóng khi shutdown; không tạo provider mới mỗi request.

Nếu ứng dụng dùng Micrometer MeterRegistry, hãy cấu hình registry/exporter Micrometer phù hợp backend đã chọn. Không mặc định một OpenTelemetry SdkMeterProvider độc lập tự thu gom toàn bộ Micrometer meters.

## 7. OTLP HTTP logs không tự xuất hiện khi đã bật tracing

Logs là signal độc lập. Cấu hình OTLP trace exporter không có nghĩa logs sẽ được chuyển tới `/v1/logs`. Để export logs qua OTLP cần logging bridge/appender hoặc OpenTelemetry Logs SDK phù hợp, cấu hình resource và exporter, rồi xác minh log records thực sự được gửi.

```text
SLF4J / Logback
       |
       +--> console/file appender (nếu vẫn cần)
       |
       +--> OTel appender/bridge (nếu cấu hình)
                 |
                 v
            OTel LogRecord
                 |
                 v
           OTLP HTTP exporter
                 |
                 v
              /v1/logs
                 |
                 v
          Collector -> log backend
```

Không cài bridge/appender trùng chức năng hoặc forward cùng log event nhiều lần. Giữ correlation fields như Trace ID/Span ID khi context tồn tại, nhưng không đưa credentials, cookie, request body hay dữ liệu cá nhân vào log record. Áp dụng filtering/redaction trước khi export.

## 8. OTLP HTTP receiver trên OpenTelemetry Collector

Một Collector cần bật receiver OTLP HTTP. Cấu hình tối giản về mặt khái niệm (schema cụ thể phụ thuộc bản Collector/contrib distribution):

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch:

exporters:
  debug:
    verbosity: basic

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
    logs:
      receivers: [otlp]
      processors: [batch]
      exporters: [debug]
```

Đây là ví dụ kiểm tra receiver với debug exporter trong môi trường phát triển. `debug` chỉ giúp quan sát dữ liệu Collector nhận; production cần exporter đích, TLS/auth khi phù hợp, processors có chủ đích và giới hạn tài nguyên. Một pipeline chỉ hoạt động khi signal tương ứng có receiver, processor và exporter được khai báo trong service pipeline.

Nếu chỉ khai báo traces pipeline, metrics và logs gửi tới `/v1/metrics` hoặc `/v1/logs` có thể không có pipeline xử lý. Nếu Collector chỉ bật grpc protocol mà ứng dụng gửi HTTP, request không được nhận trên HTTP receiver; ngược lại cũng vậy.

Khi Collector nằm trong container, bind `0.0.0.0:4318` cho phép nhận trên interface của container nhưng cần expose port/network policy thích hợp. Không mở cổng OTLP công khai không xác thực ra Internet.

## 9. TLS, authentication và network

Endpoint production thường cần HTTPS hoặc mTLS và xác thực theo chính sách hạ tầng.

**TLS:** dùng hostname khớp certificate SAN, kiểm tra CA chain và expiry. Không tắt certificate verification để “chạy cho qua”. Nếu dùng private CA, cấu hình trust store cho exporter/runtime.

**mTLS:** Collector/proxy có thể yêu cầu client certificate. Exporter cần cung cấp certificate/key và trust bundle phù hợp; cách cấu hình phụ thuộc SDK/exporter.

**Authentication:** OTLP receiver có thể được bảo vệ bởi auth extension, gateway hoặc service mesh. Đặt token/password qua secret management hoặc environment được quản lý; không commit vào repository và không in vào logs.

**Network:** từ container ứng dụng, `localhost` là container/pod hiện tại. Dùng DNS/service name trong network của deployment. Kiểm tra egress policy, firewall, proxy, DNS và port mapping.

**Multi-tenancy:** nếu backend dùng tenant headers hoặc routing keys, chỉ gửi headers theo hợp đồng được bảo vệ. Không lấy tenant header tùy ý từ request người dùng để định tuyến exporter.

Endpoint đúng nhưng TLS handshake hoặc auth thất bại vẫn không gửi được telemetry. Hãy phân loại lỗi DNS/connect, TLS, HTTP status, OTLP response và Collector downstream export.

## 10. Batching, timeout, retry và partial success

OTLP exporters thường đi cùng batching và timeout để tránh gửi từng span/measurement riêng lẻ.

| Tham số | Tác dụng | Rủi ro nếu đặt không phù hợp |
| --- | --- | --- |
| Batch size | Số records gom mỗi lần export | Quá nhỏ tăng request overhead; quá lớn tăng memory/latency |
| Schedule/delay | Chu kỳ gửi batch | Quá dài làm telemetry trễ |
| Export timeout | Thời gian chờ request | Quá thấp gây timeout giả; quá cao giữ tài nguyên lâu |
| Retry/backoff | Thử lại khi lỗi tạm thời | Retry không giới hạn có thể tạo storm |
| Queue capacity | Số records chờ gửi | Quá nhỏ drop sớm; quá lớn tăng memory |

Không phải mọi lỗi đều retry giống nhau. Lỗi kết nối, timeout hoặc response retryable có thể được thử lại theo exporter policy; lỗi dữ liệu/định dạng hoặc authentication thường cần sửa cấu hình, không nên retry vô hạn. OTLP có semantics partial success cho một số signal/version: HTTP request có thể được chấp nhận một phần và response mang thông tin records bị reject. Exporter/SDK phải xử lý response theo protocol.

Batching tạo độ trễ trước khi telemetry xuất hiện ở backend. Khi test, chờ đủ chu kỳ export hoặc dùng force-flush/shutdown đúng cách trong demo. Trong production, không force-flush trên mọi request vì sẽ phá batching và tăng overhead.

## 11. Spring Boot service với nhiều signal

Một ứng dụng có thể dùng các pipeline khác nhau:

| Signal | API/instrumentation | Export path ví dụ |
| --- | --- | --- |
| Traces | Micrometer Tracing bridge hoặc OTel Tracer | OTLP traces endpoint |
| Metrics | Micrometer MeterRegistry hoặc OTel MeterProvider | OTLP metrics endpoint hoặc Prometheus scrape |
| Logs | SLF4J/Logback và OTel bridge/appender | OTLP logs endpoint hoặc log agent |

Không nhất thiết cả ba signals phải dùng OTLP. Ví dụ hệ thống có thể scrape Prometheus metrics, gửi traces qua OTLP HTTP và dùng log agent thu thập stdout. Điều quan trọng là:

- Biết signal nào đi qua pipeline nào.
- Service identity/resource attributes nhất quán.
- Traces được propagation và sampling đúng.
- Metrics giữ cardinality thấp và đủ coverage.
- Logs có trace/span correlation khi context có sẵn.
- Không ghi trùng cùng event qua hai exporters rồi cộng hai lần ở backend.

## 12. Chẩn đoán lỗi OTLP HTTP endpoint

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Connection refused | Collector chưa chạy, sai port hoặc bind | Kiểm tra receiver, container port và network |
| DNS resolution failure | Sai service name/namespace | Kiểm tra DNS và deployment network |
| 404 Not Found | Sai path, sai base-vs-signal endpoint hoặc receiver chưa bật | Kiểm tra các signal paths và proxy prefix |
| 415 Unsupported Media Type | Content-Type/encoding không được receiver hỗ trợ | Kiểm tra protobuf vs JSON và exporter protocol |
| 401/403 | Token, auth policy hoặc quyền | Kiểm tra secret, proxy/Collector auth |
| TLS handshake/certificate error | CA, hostname, certificate/key hoặc TLS version | Kiểm tra trust chain và SAN |
| HTTP 200 nhưng backend trống | Collector nhận request nhưng pipeline/exporter đích lỗi hoặc query sai | Xem Collector exporter errors, pipeline và backend labels |
| Chỉ traces có dữ liệu | Chưa cấu hình metrics/log exporter hoặc pipeline tương ứng | Kiểm tra ba signal riêng |
| Dữ liệu xuất trễ | Batch interval hoặc queue | Kiểm tra periodic reader, batch và timeout |
| Spans bị thiếu | Sampling, queue overflow, partial success hoặc exporter drops | Kiểm tra sampled ratio, SDK/Collector dropped counters |
| Metrics có series trùng | Hai pipeline ghi cùng event hoặc scrape duplicate | Kiểm tra registry/exporter và target discovery |

### Kiểm tra bằng HTTP client

Có thể kiểm tra TCP/HTTP reachability tới endpoint, nhưng request rỗng không phải payload OTLP hợp lệ:

```bash
curl -i http://otel-collector:4318/
```

Lệnh trên chỉ hỗ trợ kiểm tra kết nối/phản hồi ở root path, không chứng minh `/v1/traces` đã nhận đúng OTLP data. Không dùng curl POST JSON ngẫu nhiên để kết luận exporter hoạt động. Cách xác minh đáng tin cậy là gửi telemetry từ exporter thật hoặc OTLP client đúng chuẩn, rồi quan sát Collector receiver/pipeline/exporter.

## 13. Quy trình kiểm chứng end-to-end

1. **Xác nhận receiver:** Collector bật đúng OTLP HTTP protocol và port, bind đúng interface.
2. **Kiểm tra path:** traces, metrics, logs dùng path đúng hoặc signal-specific endpoint mà SDK nhận.
3. **Kiểm tra protocol:** exporter chọn HTTP/protobuf hoặc JSON theo capability tương ứng; không nhầm gRPC với HTTP.
4. **Kiểm tra network/TLS/auth:** DNS, routing, certificate, bearer/mTLS và secret injection.
5. **Tạo một request có trace:** gọi HTTP endpoint Spring Boot và xác minh server/client/business spans theo sampling policy.
6. **Ghi metrics có giá trị biết trước:** increment counter/record histogram; kiểm tra reader/exporter hoạt động.
7. **Ghi log có cấu trúc:** xác minh appender/bridge gửi log record và correlation fields đúng nếu đã bật.
8. **Quan sát Collector:** receiver nhận records, processors chạy và exporter đích không reject/drop.
9. **Kiểm tra backend:** đúng service/resource, signal, unit, labels và thời điểm ingest.
10. **Kiểm tra shutdown/batch:** bảo đảm data cuối được flush khi test process kết thúc; production quản lý lifecycle đúng.

### Ma trận kiểm thử

| Thử nghiệm | Kết quả mong đợi |
| --- | --- |
| Gửi trace qua exporter thật | Collector nhận trace request đúng path |
| Gửi metrics qua metrics exporter | Collector có metrics pipeline nhận record |
| Gửi logs qua logging bridge | Collector có logs pipeline nhận record |
| Dùng sai path | Nhận lỗi phù hợp, không nhầm với lỗi instrumentation |
| Dùng HTTP khi receiver chỉ bật gRPC | Không kết nối đúng; sửa protocol/receiver |
| Dùng signal endpoint đầy đủ rồi nối path lần nữa | Path sai; sửa semantics base vs signal URL |
| Token không hợp lệ | Auth trả lỗi; secret không bị log |
| Collector nhận được nhưng exporter backend fail | Receiver metrics vẫn có thể tăng; kiểm tra downstream exporter errors |
| Head sampling loại trace | Metrics có thể vẫn hiện dù trace thiếu |
| Đóng ứng dụng demo | Flush/close theo lifecycle để không mất batch cuối |

## 14. Bài tập tình huống

Một nhóm triển khai Spring Boot với endpoint:

```yaml
management:
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
```

Logs ứng dụng cho thấy request được xử lý thành công. Collector ghi nhận traces nhưng metrics và logs không xuất hiện ở backend. Nhóm thử thay endpoint thành một URL ghép thêm `/v1/metrics` vào sau đường dẫn traces và không cải thiện.

**Câu hỏi:**

1. Vì sao endpoint traces không tự cấu hình metrics và logs?
2. Đường dẫn mới có hợp lý không?
3. Cần kiểm tra những thành phần nào để đưa metrics và logs đi OTLP HTTP?
4. Nếu Collector nhận traces nhưng backend không có dữ liệu, cần phân biệt các lớp nào?

**Gợi ý phân tích:**

- Property trong ví dụ chỉ cấu hình tracing exporter; metrics cần registry/OTel MetricReader và exporter riêng, logs cần OTel logging bridge/appender hoặc SDK pipeline riêng.
- Path ghép thêm signal path vào URL traces là sai. Metrics endpoint chuẩn có path riêng `/v1/metrics` và logs là `/v1/logs`.
- Xác định pipeline thực tế: Micrometer registry hay OTel SdkMeterProvider; SLF4J/Logback có bridge/appender chưa; Collector có metrics/logs pipelines và downstream exporters chưa.
- Tách kiểm tra exporter từ ứng dụng, OTLP receiver, Collector processor/exporter và backend ingest/query. HTTP receiver nhận trace không bảo đảm downstream exporter đã thành công.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| OTLP over HTTP | Phân biệt với OTLP/gRPC |
| Signal paths | Nhớ traces, metrics, logs có endpoint riêng |
| Base vs full endpoint | Không nối path trùng |
| Encoding/headers | Hiểu protobuf, JSON, Content-Type, Content-Encoding |
| Spring Boot trace export | Kiểm tra property/dependency đúng version |
| Metrics export | Xác định Micrometer registry hoặc OTel MetricReader |
| Logs export | Xác định appender/bridge/SDK |
| Collector receiver/pipelines | Bật đúng protocol và signal |
| TLS/auth/network | Không mở OTLP receiver công khai không bảo vệ |
| Batch/retry/partial success | Phân biệt exporter errors với downstream rejection |
| End-to-end verification | Xác minh receiver, processor, exporter và backend |

**Ghi nhớ:** OTLP HTTP là transport chuẩn để gửi traces, metrics và logs qua các endpoint signal-specific như `/v1/traces`, `/v1/metrics` và `/v1/logs`. Cần khớp endpoint, base-vs-full URL, protocol, encoding, TLS/auth và Collector pipeline. Spring Boot tracing export không tự bật metrics/logs export; mỗi signal cần instrumentation và exporter phù hợp. Hãy xác minh từ ứng dụng qua receiver, processor, exporter tới backend, đồng thời theo dõi batching, retry, partial success và dropped telemetry để bảo đảm observability hoạt động thật trên môi trường production.

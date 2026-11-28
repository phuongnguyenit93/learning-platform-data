# Cấu hình exporter cho OTLP

Trong một ứng dụng Spring Boot dùng **Spring Modulith**, các điểm quan sát có thể ghi nhận HTTP request, lời gọi qua ranh giới application module và thao tác nghiệp vụ được instrument. Để xem các dấu vết ấy trong Jaeger, Tempo hoặc một nền tảng observability hỗ trợ OpenTelemetry, ứng dụng cần **xuất span ra khỏi tiến trình**. OTLP (OpenTelemetry Protocol) là giao thức phổ biến cho bước vận chuyển này.

Một cấu hình hoàn chỉnh nối các thành phần: **Micrometer Observation/Tracing → OpenTelemetry tracer → OTLP exporter → receiver (thường là OpenTelemetry Collector) → tracing backend**. Chỉ thêm dependency exporter chưa đủ nếu thiếu endpoint nhận dữ liệu, sai transport hoặc sampling loại bỏ trace. Bài học này trình bày cách cấu hình exporter OTLP trong Spring Boot, dựng Collector tối thiểu để kiểm tra và xác minh module spans đã đến backend.

Bài thuộc chương **Export traces** của module `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Mục tiêu chung của module là sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong Spring Boot qua module graph, Actuator, event metrics, tracing và context propagation. Riêng bài này tập trung vào **xuất traces**, phân biệt rõ với xuất metrics hoặc logs.

> **Phạm vi phiên bản:** Ví dụ cấu hình chính dùng **Spring Boot 3.5.x** với Micrometer Tracing và OpenTelemetry OTLP. Phần riêng bên dưới nêu khác biệt của **Spring Boot 4.2.x**, nơi starter và prefix cấu hình đã thay đổi. Hãy chọn đúng một bộ dependency/property theo BOM dự án, không trộn hai dòng phiên bản.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của Micrometer Tracing, OpenTelemetry bridge, OTLP exporter, Collector và tracing backend.
2. Chọn dependency cho Spring Boot 3.5.x và cấu hình endpoint OTLP.
3. Phân biệt OTLP/gRPC với OTLP/HTTP protobuf và cấu hình endpoint tương ứng.
4. Thiết lập OpenTelemetry Collector receiver và trace pipeline để nhận span.
5. Cấu hình service identity, sampling, timeout, compression và headers.
6. Xác minh HTTP span hoặc module span đi từ ứng dụng đến backend.
7. Chẩn đoán sai endpoint, sai protocol, container network, sampling và exporter không hoạt động.
8. Nhận biết khác biệt cấu hình giữa Spring Boot 3.5.x và 4.2.x.

## 2. OTLP exporter nằm ở đâu trong đường đi của trace?

Khi request đi vào ứng dụng, Spring Boot và các instrumentation tương ứng có thể tạo observation. Micrometer Tracing kết nối observation với tracer OpenTelemetry. Span sau đó được exporter gửi tới receiver theo OTLP:

~~~mermaid
flowchart LR
    Request["HTTP / module interaction"] --> Obs["Micrometer Observation"]
    Obs --> Tracer["Micrometer Tracing"]
    Tracer --> Span["OpenTelemetry Span"]
    Span --> Exporter["OTLP Span Exporter"]
    Exporter --> Receiver["OTLP Receiver / Collector"]
    Receiver --> Pipeline["Processors"]
    Pipeline --> Backend["Trace backend"]
    Backend --> UI["Trace search / waterfall"]
~~~

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Spring Modulith instrumentation** | Instrument tương tác module thuộc phạm vi hỗ trợ | Lời gọi qua API của `order` và `inventory` |
| **Micrometer Observation** | Mô tả thao tác, context, thời điểm và kết quả | HTTP observation, business observation |
| **Micrometer Tracing bridge** | Chuyển abstraction sang tracer cụ thể | `micrometer-tracing-bridge-otel` |
| **OpenTelemetry SDK/exporter** | Tạo và xuất span theo OTLP | HTTP protobuf hoặc gRPC |
| **OpenTelemetry Collector** | Nhận, xử lý, định tuyến và chuyển tiếp telemetry | OTLP receiver + batch processor |
| **Tracing backend** | Lưu và truy vấn trace/span | Jaeger, Tempo hoặc backend tương thích |

Không phải mọi lời gọi Java đều tự động sinh module span. Cần bật phần tích hợp Spring Modulith phù hợp, có module graph đúng và thực thi lời gọi nằm trong phạm vi instrumentation. Exporter chỉ vận chuyển những span đã được tạo và được sampling giữ lại.

## 3. Phân biệt OTLP/HTTP và OTLP/gRPC

Hai transport thường gặp:

| Đặc điểm | OTLP/HTTP protobuf | OTLP/gRPC |
| --- | --- | --- |
| Giao thức | HTTP với payload protobuf | gRPC với protobuf |
| Cổng Collector thường gặp | `4318` | `4317` |
| Endpoint traces thường gặp | `http://collector:4318/v1/traces` | `http://collector:4317` |
| Path tín hiệu | Có `/v1/traces` trong HTTP endpoint | Không thêm path HTTP như ví dụ |
| Spring Boot 3.5 | `transport: http` | `transport: grpc` |

Các cổng `4317` và `4318` là quy ước phổ biến, **không phải cổng bắt buộc**. Collector có thể được cấu hình cổng khác; ứng dụng phải khớp địa chỉ receiver thật.

Với OTLP/HTTP, URL traces thường kết thúc bằng `/v1/traces`. Với OTLP/gRPC, endpoint thường là địa chỉ server, không có path HTTP này. Nếu backend/gateway chỉ hỗ trợ một transport, ứng dụng phải dùng cùng giao thức.

## 4. Dependency cho Spring Boot 3.5.x

Spring Boot 3.5.x dùng Actuator để quản lý Micrometer Tracing và auto-configuration. Để xuất traces bằng OpenTelemetry/OTLP, cần ba dependency chính:

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
</dependencies>
~~~

Vai trò:

- `spring-boot-starter-actuator` cung cấp nền tảng observability và auto-configuration.
- `micrometer-tracing-bridge-otel` kết nối Micrometer Observation/Tracing với OpenTelemetry.
- `opentelemetry-exporter-otlp` cung cấp exporter gửi span tới OTLP receiver.

Với ứng dụng cần quan sát tương tác application module, có thể thêm phần tích hợp Spring Modulith Insight tương thích:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
</dependency>
~~~

Insight phục vụ instrumentation liên quan module; nó **không thay thế** tracing bridge hoặc OTLP exporter. Phiên bản Spring Modulith phải tương thích với Spring Boot/BOM dự án. Không khai báo version tùy tiện cho từng artifact nếu dự án đã quản lý bằng dependency management.

Kiểm tra dependency tree để xác nhận bridge và exporter đúng version, đồng thời tránh có nhiều tracing implementations xung đột:

~~~bash
mvn dependency:tree
~~~

Nếu dự án dùng Gradle, dùng lệnh dependency report tương ứng của Gradle.

## 5. Cấu hình OTLP/HTTP trong Spring Boot 3.5.x

Với HTTP protobuf, `application.yml` có thể như sau:

~~~yaml
spring:
  application:
    name: shop-application

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
      transport: http
      timeout: 10s
      connect-timeout: 5s
      compression: gzip
~~~

| Property | Ý nghĩa |
| --- | --- |
| `spring.application.name` | Tên ứng dụng; thường được dùng làm cơ sở cho resource identity như `service.name` |
| `management.tracing.sampling.probability` | Tỷ lệ trace được lấy mẫu; `1.0` nghĩa là lấy mẫu 100% |
| `management.otlp.tracing.endpoint` | URL HTTP API của Collector, gồm path `/v1/traces` |
| `management.otlp.tracing.transport` | Chọn transport; `http` cho OTLP/HTTP protobuf |
| `management.otlp.tracing.timeout` | Thời gian tối đa cho thao tác export |
| `management.otlp.tracing.connect-timeout` | Thời gian chờ kết nối |
| `management.otlp.tracing.compression` | Nén payload, ví dụ `gzip` nếu receiver hỗ trợ |

Spring Boot mặc định chỉ lấy mẫu một phần request (thường 10%) để tránh gửi quá nhiều dữ liệu. `probability: 1.0` hữu ích khi thử nghiệm local vì giúp dễ thấy trace, nhưng **không nên mặc định dùng cho production** nếu chưa tính tải, chi phí lưu trữ và chính sách sampling.

Endpoint trên giả định Collector có HTTP receiver lắng nghe tại máy cục bộ cổng `4318`. Nếu ứng dụng chạy trong container, `localhost` chỉ chính container ứng dụng; cần thay bằng hostname/service name có thể truy cập trong network.

## 6. Cấu hình OTLP/gRPC trong Spring Boot 3.5.x

Nếu Collector nhận OTLP/gRPC, thay transport và endpoint:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4317
      transport: grpc
      timeout: 10s
      connect-timeout: 5s
~~~

Trong Spring Boot 3.5.x, OTLP tracing auto-configuration hỗ trợ HTTP/protobuf và gRPC; mặc định là HTTP/protobuf. Đặt `management.otlp.tracing.transport: grpc` để dùng gRPC. Không dùng URL `/v1/traces` kiểu HTTP khi cấu hình endpoint gRPC.

## 7. Khác biệt cấu hình ở Spring Boot 4.2.x

Spring Boot 4.x đã thay đổi cách đóng gói và prefix cấu hình OpenTelemetry. Với Spring Boot 4.2.x, tài liệu hiện hành sử dụng starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-opentelemetry</artifactId>
</dependency>
~~~

Thay vì ghép thủ công bridge và OTLP exporter như cấu hình 3.5, starter này cung cấp tích hợp OpenTelemetry theo cách Spring Boot 4.x quản lý. Cấu hình traces dùng prefix mới:

~~~yaml
spring:
  application:
    name: shop-application

management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces
          transport: http
          timeout: 10s
~~~

Ở Spring Boot 4.x, cấu hình export traces nằm dưới `management.opentelemetry.tracing.export.otlp.*`. Các property chung cho OTLP (endpoint, headers, compression) cũng có thể khai báo dưới `management.opentelemetry.otlp.*`; property riêng cho traces có độ ưu tiên cao hơn khi cùng được đặt.

**Không copy nguyên cấu hình 3.5 vào 4.2 hoặc ngược lại.** Dùng đúng starter, property prefix và tài liệu tương ứng với BOM. Nếu dự án dùng một bản 4.x khác, hãy kiểm tra application properties appendix của đúng minor version.

## 8. Dựng OpenTelemetry Collector để nhận traces

Collector thường nằm giữa ứng dụng và backend. Nó có thể nhận OTLP, batch dữ liệu rồi chuyển tiếp tới tracing backend. Để kiểm tra exporter trước, có thể dùng `debug` exporter để Collector ghi thông tin span nhận được vào log.

Ví dụ cấu hình `otel-collector.yaml` tối thiểu cho local:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 127.0.0.1:4317
      http:
        endpoint: 127.0.0.1:4318

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
~~~

Pipeline này có ba phần:

1. **Receiver:** nhận cả OTLP/gRPC và OTLP/HTTP.
2. **Processor:** `batch` gom span trước khi chuyển tiếp.
3. **Exporter:** `debug` in thông tin telemetry để kiểm tra; nó không phải nơi lưu trace để truy vấn dài hạn.

Collector chỉ kích hoạt những component được khai báo trong pipeline thuộc phần `service`. Việc định nghĩa receiver hoặc exporter ở đầu file **chưa tự bật** component nếu pipeline không tham chiếu tới nó.

Chạy và kiểm tra cấu hình bằng lệnh của bản Collector đã cài:

~~~bash
otelcol validate --config=otel-collector.yaml
otelcol --config=otel-collector.yaml
~~~

Tên executable có thể là `otelcol-contrib` hoặc tên khác tùy distribution. Dùng đúng binary được cài. Nếu ứng dụng và Collector chạy trên cùng máy, bind `127.0.0.1` phù hợp cho local. Nếu chạy trong container khác nhau, cần bind vào interface mạng mà ứng dụng truy cập được và giới hạn truy cập bằng network policy/firewall. Không mở receiver không xác thực ra Internet.

### Chuyển tiếp tới backend thực tế

Khi muốn lưu trace vào backend, thay `debug` exporter bằng exporter tương ứng. Ví dụ nếu backend nhận OTLP/gRPC tại service `trace-backend:4317`:

~~~yaml
exporters:
  otlp/trace-backend:
    endpoint: trace-backend:4317
    tls:
      insecure: true

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/trace-backend]
~~~

Đây là **mảnh cấu hình thay thế exporter** cho môi trường nội bộ thử nghiệm, không phải file Collector đầy đủ độc lập. `tls.insecure: true` chỉ minh họa kết nối không mã hóa trong mạng local/dev được kiểm soát; production nên cấu hình TLS và xác thực theo backend. Nếu backend nhận OTLP/HTTP thay vì gRPC, dùng exporter và endpoint/transport tương ứng.

## 9. Đặt service identity và resource attributes

Một trace cần cho biết **dịch vụ/tiến trình nào phát ra span**. Trong modular monolith, các module `order`, `inventory` và `billing` thường chạy cùng ứng dụng nên có thể dùng chung `service.name=shop-application`.

| Thuộc tính | Ví dụ | Mục đích |
| --- | --- | --- |
| `service.name` | `shop-application` | Nhận diện dịch vụ/tiến trình |
| `service.version` | `2.4.0` | Phân biệt phiên bản deploy |
| `deployment.environment.name` | `staging` | Nhận diện môi trường |
| `module.identifier` | `inventory` | Phân biệt application module nếu instrumentation cung cấp |
| `traceId` | ID của một trace | Liên kết các span trong một trace |
| `spanId` | ID của một span | Định danh một thao tác |

Không đặt mỗi application module thành một `service.name` khác nhau nếu chúng vẫn cùng ứng dụng/process. Làm vậy sẽ khiến người xem hiểu nhầm modular monolith thành nhiều service độc lập. Thông tin module nên được thể hiện qua span name/attributes mà instrumentation hỗ trợ.

Ví dụ tên ứng dụng:

~~~yaml
spring:
  application:
    name: shop-application
~~~

Khi backend nhận trace, kiểm tra resource attributes để xác nhận `service.name` đúng. Nếu cần thêm môi trường hoặc version, cấu hình resource attributes theo property của Spring Boot đang dùng hoặc qua biến môi trường/OTel resource configuration tương ứng. Tránh đặt giá trị động như order ID hoặc request ID vào resource: resource mô tả nguồn phát telemetry, không mô tả từng request.

## 10. Sampling và batch export

### Sampling

Sampling quyết định trace nào được giữ để xuất. Nếu xác suất là 10%, một số request sẽ không có trace trong backend dù ứng dụng vẫn xử lý thành công.

| Môi trường | Hướng cấu hình thường dùng |
| --- | --- |
| Local/dev | Có thể dùng `1.0` để thấy mọi trace trong bài thực hành |
| Test/integration | Chọn tỷ lệ đủ cao để kiểm tra luồng; chú ý chi phí và tính lặp lại |
| Staging | Gần chính sách production để thử tải và xác minh pipeline |
| Production | Chọn theo traffic, SLO, chi phí và yêu cầu điều tra; không mặc định 100% |

Khi có parent trace, sampler kiểu parent-based có thể giữ tính nhất quán giữa span cha/con. Cấu hình sampler cụ thể phụ thuộc Spring Boot và tracer implementation.

### Batch export

Exporter thường gom span rồi gửi theo batch thay vì gửi một HTTP request riêng cho mỗi span. Cách này giảm overhead network, nhưng tạo độ trễ nhỏ giữa lúc request hoàn tất và lúc trace xuất hiện trong backend.

Các yếu tố cần điều chỉnh:

- **Batch schedule delay:** khoảng chờ trước khi exporter gửi batch.
- **Maximum batch size:** số span tối đa trong một lần gửi.
- **Queue capacity:** số span chờ gửi khi backend tạm chậm.
- **Export timeout:** thời gian tối đa cho một lần export.
- **Retry/backoff:** cách xử lý lỗi tạm thời, nếu exporter/SDK hỗ trợ.

Spring Boot 3.5 có property timeout, connect timeout, compression và headers cho OTLP tracing. Các tham số batching chi tiết có thể được điều khiển ở OpenTelemetry SDK hoặc builder customizer tùy version; không giả định mọi property của OpenTelemetry Java Agent đều có tên tương ứng trong Spring Boot.

## 11. Headers, authentication và TLS

Collector hoặc backend từ xa có thể yêu cầu header xác thực. Với Spring Boot 3.5:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: https://otel-gateway.example.internal/v1/traces
      transport: http
      headers:
        Authorization: "Bearer <token-from-secret-store>"
      timeout: 10s
      connect-timeout: 5s
~~~

Trong deployment thật, token phải được lấy từ secret manager hoặc biến môi trường được bảo vệ. Không commit token thật vào Git, không in header ra log và không chia sẻ cấu hình chứa credential trong ticket.

Khi dùng HTTPS/gRPC TLS:

- Cấu hình chứng thư CA đáng tin cậy trong runtime.
- Dùng mTLS nếu backend yêu cầu client certificate.
- Kiểm tra hostname/SAN của certificate khớp endpoint.
- Không tắt xác minh chứng thư trong production để “sửa nhanh” lỗi kết nối.
- Nếu Collector là gateway nội bộ, giới hạn nguồn có thể kết nối tới receiver.

Spring Boot 3.5 cung cấp `OtlpHttpSpanExporterBuilderCustomizer` và `OtlpGrpcSpanExporterBuilderCustomizer` để tùy biến builder khi property thông thường không đủ. Chỉ thêm customizer khi có yêu cầu cụ thể như TLS/client authentication đặc biệt; ưu tiên cấu hình chuẩn trước.

## 12. Kiểm chứng exporter đầu-cuối

Quy trình xác minh nên theo đúng thứ tự dữ liệu:

~~~mermaid
flowchart TD
    A["Ứng dụng khởi động với tracing bridge + exporter"] --> B["Gửi request có thể lặp lại"]
    B --> C{"Observation/span được tạo?"}
    C -->|"Không"| D["Kiểm tra instrumentation và sampling"]
    C -->|"Có"| E{"Exporter gửi tới receiver?"}
    E -->|"Không"| F["Kiểm tra endpoint, transport, auth, TLS, timeout"]
    E -->|"Có"| G{"Collector nhận trace?"}
    G -->|"Không"| H["Kiểm tra receiver và network"]
    G -->|"Có"| I{"Backend truy vấn được?"}
    I -->|"Không"| J["Kiểm tra Collector pipeline/exporter/backend"]
    I -->|"Có"| K["Đối chiếu traceId, service.name và module spans"]
~~~

### Bước 1 — Kiểm tra cấu hình và startup

Đảm bảo:

- Dependency bridge và exporter đúng version.
- Property prefix đúng dòng Spring Boot.
- Endpoint/transport khớp receiver.
- Có Collector hoặc backend đang chạy.
- Sampling không loại bỏ toàn bộ trace.

### Bước 2 — Tạo một thao tác có span

Gửi request HTTP vào ứng dụng. Nếu muốn xác minh module spans, gọi qua API module đã được Spring Modulith Insight instrument. Nếu cần kiểm tra tracing độc lập, có thể tạo observation nghiệp vụ:

~~~java
package com.example.shop.order;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class OrderDiagnostics {

    private final ObservationRegistry observations;

    OrderDiagnostics(ObservationRegistry observations) {
        this.observations = observations;
    }

    void inspectOrder() {
        Observation.createNotStarted("shop.order.inspect", observations)
                .lowCardinalityKeyValue("application.module", "order")
                .observe(() -> {
                    // Thao tác kiểm tra trong môi trường thử nghiệm.
                });
    }
}
~~~

Observation này có thể được chuyển thành span khi tracing handler được đăng ký. Nhãn `application.module` là do ví dụ tự đặt; nó không thay thế instrumentation module của Spring Modulith.

### Bước 3 — Kiểm tra Collector

Với `debug` exporter, xem log của Collector. Nếu Collector nhận spans, thông tin span sẽ được ghi ra log theo mức verbosity đã cấu hình. Nếu không có dữ liệu, kiểm tra ứng dụng có gửi đúng protocol/port và Collector có bật traces pipeline hay không.

### Bước 4 — Kiểm tra backend

Trong Jaeger/Tempo hoặc giao diện backend:

1. Chọn đúng `service.name`, ví dụ `shop-application`.
2. Chọn khoảng thời gian có request thử nghiệm; tính đến độ trễ batch/export.
3. Tìm trace và mở waterfall để xem span.
4. Đối chiếu `traceId`, span name, duration và resource attributes.
5. Nếu có Spring Modulith instrumentation, tìm module-related spans/attributes; tên thực tế tùy version.

### Bước 5 — So sánh với logs

Spring Boot cùng Micrometer Tracing có thể thêm correlation ID chứa `traceId` và `spanId` vào log thông qua MDC. Dùng cùng ID để nối log với trace. Việc export traces qua OTLP **không tự động export application logs** đến cùng backend; log pipeline có thể cần agent/collector riêng.

## 13. Kiểm tra trong test và môi trường container

### Lưu ý với `@SpringBootTest`

Một test context có thể không auto-configure các thành phần tracing có nhiệm vụ **report dữ liệu ra ngoài** giống ứng dụng đang chạy bình thường. Vì vậy:

- Test bean/observation có thể xác nhận instrumentation tạo dữ liệu.
- Test exporter có thể cần cấu hình riêng hoặc test double/collector test.
- Kiểm tra end-to-end cuối cùng nên chạy ứng dụng trong profile/môi trường gần deployment thật.

Không kết luận exporter production hỏng chỉ vì test context không gửi trace ra backend.

### Docker/Kubernetes network

Nếu ứng dụng và Collector ở hai container, cấu hình:

~~~yaml
management:
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
      transport: http
~~~

Tên `otel-collector` phải là hostname/service name phân giải được trong network của ứng dụng. `localhost` trong container ứng dụng không trỏ đến container Collector. Nếu Collector ở Kubernetes, dùng service DNS và port được khai báo trong cluster.

Nếu Collector bind receiver chỉ vào `127.0.0.1` trong container của nó, container ứng dụng khác sẽ không truy cập được. Khi cần bind ra interface mạng, giới hạn network và bảo vệ receiver bằng chính sách phù hợp; không mở cổng nhận telemetry ra public network.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Kiểm tra |
| --- | --- | --- |
| Ứng dụng chạy nhưng backend không có trace | Chưa có bridge/exporter hoặc chưa có observation được instrument | Dependency tree, tracing handler, request thực tế |
| Collector báo connection refused | Sai host/port hoặc receiver chưa chạy | Endpoint ứng dụng, Collector startup và network |
| HTTP exporter trả 404 | Sai path `/v1/traces` hoặc receiver không dùng OTLP/HTTP | Transport, URL, cấu hình receiver |
| gRPC exporter lỗi protocol | Ứng dụng dùng gRPC nhưng receiver chỉ mở HTTP, hoặc ngược lại | Cặp `transport` và receiver protocol |
| Backend chỉ thấy một phần request | Sampling mặc định hoặc parent trace không được sample | Sampling probability và sampler |
| Trace xuất hiện trễ | Batch, queue hoặc backend ingest delay | Chờ chu kỳ export, kiểm tra Collector/SDK logs |
| Collector nhận trace nhưng backend trống | Exporter pipeline chưa được tham chiếu trong `service.pipelines.traces` hoặc exporter backend lỗi | Collector config, exporter logs, auth/TLS |
| Backend không tìm thấy service | Resource `service.name` khác bộ lọc | Resource attributes và `spring.application.name` |
| Chỉ có HTTP span, thiếu module span | Insight chưa bật, module detection sai hoặc lời gọi ngoài phạm vi instrument | Spring Modulith dependency, module graph, điểm gọi |
| Trace bị tách ở listener async | Context propagation qua executor/broker chưa hoạt động | Executor, task decorator, messaging headers |
| Export lỗi do TLS | CA, hostname hoặc client certificate không khớp | Certificate chain, endpoint DNS, mTLS config |
| Request chậm khi bật tracing | Sampling quá cao, exporter/network chậm hoặc queue nghẽn | So latency, exporter timeout, Collector throughput |

Khi xử lý, phân biệt **không tạo span**, **không gửi span**, **Collector không nhận**, và **backend không hiển thị**. Bốn tình huống này nằm ở các chặng khác nhau và cần bằng chứng khác nhau.

## 15. Lưu ý bảo mật và vận hành

Trace có thể chứa route, method, exception, module name, database attributes và metadata nghiệp vụ. Trước khi gửi tới backend:

1. Không gắn mật khẩu, access token, session cookie hoặc thông tin thanh toán vào span attributes.
2. Không đưa tenant ID, email, order ID hoặc dữ liệu cá nhân vào span nếu không có nhu cầu điều tra và chính sách bảo vệ rõ ràng.
3. Giới hạn sampling theo tải và mục tiêu SLO; theo dõi queue/drop/export failures.
4. Dùng TLS và xác thực khi truyền qua network không tin cậy.
5. Giới hạn quyền truy cập tracing backend vì trace có thể tiết lộ cấu trúc nội bộ.
6. Đặt thời gian lưu trữ và chính sách xóa phù hợp.
7. Tránh expose Collector receiver công khai mà không có authentication/network controls.
8. Theo dõi chính Collector: receiver accepted/refused spans, exporter sent/failed, queue size và memory pressure theo khả năng của distribution.

**OTLP không phải hệ thống lưu trữ.** Nó chỉ là giao thức truyền dữ liệu; retention, indexing, query, phân quyền và chi phí lưu trữ thuộc trách nhiệm của backend.

## 16. Bài thực hành: xuất module spans qua OTLP

Chuẩn bị ứng dụng Spring Boot có hai application module `order` và `inventory`, phần tích hợp Spring Modulith Insight tương thích, Micrometer Tracing bridge và OTLP exporter. Dùng một OpenTelemetry Collector local với `debug` exporter.

1. **Xác nhận phiên bản:** ghi Spring Boot/Spring Modulith, chọn đúng dependency và property prefix.
2. **Bật instrumentation:** cấu hình Actuator, Insight và tracing bridge; xác nhận module graph nhận diện đúng hai module.
3. **Cấu hình HTTP protobuf:** đặt endpoint `http://localhost:4318/v1/traces`, transport `http` và sampling 100% trong local.
4. **Khởi động Collector:** bật receiver OTLP/HTTP và traces pipeline với batch processor + debug exporter.
5. **Gửi request:** gọi endpoint trong `order` có tương tác qua API `inventory`.
6. **Xem Collector logs:** xác nhận có span được nhận; nếu không, kiểm tra exporter endpoint, protocol và network.
7. **Chuyển sang backend:** thay debug exporter bằng exporter tới backend tracing thử nghiệm, cấu hình TLS/auth theo môi trường.
8. **Truy vấn trace:** tìm theo `service.name`, kiểm tra HTTP span và module spans nếu instrumentation hỗ trợ.
9. **Thử gRPC:** bật Collector gRPC receiver, đổi ứng dụng sang `transport: grpc` và endpoint cổng `4317`; xác nhận trace vẫn đến backend.
10. **Thử sampling thấp:** giảm xác suất, gửi nhiều request và giải thích vì sao không phải request nào cũng xuất hiện.
11. **Thử lỗi có kiểm soát:** đổi sai port hoặc dừng receiver trong local; nhận diện lỗi ở chặng export, sau đó khôi phục.
12. **Ghi nhận vận hành:** nêu service identity, sampling policy, transport, endpoint, timeout, bảo mật và bằng chứng đã xác minh.

Mẫu ghi kết quả:

| Kiểm tra | Kết quả mong đợi | Bằng chứng |
| --- | --- | --- |
| Dependency | Bridge và OTLP exporter đúng version | Dependency tree |
| Instrumentation | Có span cho thao tác đã gọi | Collector/backend |
| HTTP/gRPC | Transport khớp receiver | Collector log |
| Resource | `service.name` đúng ứng dụng | Trace resource attributes |
| Module | Có module span nếu điểm gọi được instrument | Span attributes/name thực tế |
| Sampling | Tỷ lệ trace phù hợp cấu hình | So request với trace nhận được |
| Export | Không có lỗi gửi/receiver | Exporter/Collector logs |
| Backend | Tìm được trace theo service và thời gian | Trace UI/query |

### Câu hỏi tự kiểm tra

1. Vì sao `micrometer-tracing-bridge-otel` không tự gửi span nếu thiếu OTLP exporter?
2. Khác biệt giữa OTLP/HTTP protobuf và OTLP/gRPC nằm ở transport và endpoint như thế nào?
3. Vì sao endpoint HTTP traces thường có path `/v1/traces` nhưng endpoint gRPC không dùng cùng path đó?
4. Một Collector có receiver nhưng không khai báo receiver trong `service.pipelines.traces` thì chuyện gì xảy ra?
5. Vì sao Collector nhận span chưa đủ chứng minh backend đã lưu trace?
6. Vì sao `spring.application.name`/`service.name` không nên đặt theo từng module trong modular monolith?
7. Sampling 10% có thể làm bạn hiểu nhầm điều gì khi kiểm tra một request duy nhất?
8. Vì sao `localhost` trong container ứng dụng không phải lúc nào cũng là Collector?
9. Nếu thấy HTTP span nhưng thiếu module span, những thành phần nào cần kiểm tra trước khi kết luận exporter hỏng?
10. Vì sao không nên đưa tenant ID hoặc order ID vào span attributes nếu không có nhu cầu và chính sách dữ liệu rõ ràng?

## 17. Tổng kết

Để xuất traces bằng OTLP, ứng dụng Spring Boot cần **Micrometer Tracing bridge**, **OpenTelemetry OTLP exporter** và một **receiver** đang hoạt động. Với Spring Boot 3.5.x, cấu hình chính dùng `management.otlp.tracing.*` và các dependency `micrometer-tracing-bridge-otel` cùng `opentelemetry-exporter-otlp`. Với Spring Boot 4.2.x, starter và prefix đã chuyển sang `spring-boot-starter-opentelemetry` và `management.opentelemetry.tracing.export.otlp.*`.

OTLP/HTTP protobuf và OTLP/gRPC cần endpoint/transport khớp với Collector. Collector phải bật receiver trong traces pipeline, có processor/exporter phù hợp và chuyển tiếp đến backend. Sampling, batch, timeout, service identity, TLS và xác thực quyết định chất lượng vận hành của pipeline. Khi kiểm tra, hãy theo bằng chứng từ **span được tạo → exporter gửi → Collector nhận → backend lưu và truy vấn**; chỉ khi cả chuỗi hoạt động, module spans của Spring Modulith mới trở thành dữ liệu hữu ích để kiểm chứng tương tác trong kiến trúc mô-đun.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Tracing và OpenTelemetry với OTLP](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html).
- [Spring Boot 3.5 — OtlpTracingProperties API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/tracing/otlp/OtlpTracingProperties.html).
- [Spring Boot 4.2 — Tracing và OpenTelemetry với OTLP](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
- [Spring Boot — Observability và OpenTelemetry](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
- [OpenTelemetry Collector — Configuration](https://opentelemetry.io/docs/collector/configuration/).
- [OpenTelemetry — OTLP Specification](https://opentelemetry.io/docs/specs/otlp/).
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/).

# Phối hợp với Zipkin, OTLP và nền tảng quan sát

Khi một ứng dụng Spring Boot được phân chia thành các application module bằng **Spring Modulith**, sơ đồ module và các quy tắc phụ thuộc cho biết **kiến trúc được thiết kế như thế nào**. Tuy nhiên, khi chạy thật, kỹ sư còn cần biết yêu cầu đã đi qua module nào, sự kiện nào được công bố, listener nào mất nhiều thời gian, và chỗ nào xuất hiện lỗi. Để trả lời, ứng dụng phải tạo **telemetry**, xuất dữ liệu đó đến một công cụ thu thập và phân tích, rồi đối chiếu kết quả với ranh giới module.

Bài thuộc chương **Insight starter** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, với trọng tâm **phối hợp Spring Modulith, Zipkin, OTLP và nền tảng quan sát**. Mục tiêu là hiểu đường đi của trace, biết cấu hình exporter theo phiên bản Spring Boot, kết nối module spans với metrics/logs và xử lý tình huống trace bị đứt qua luồng bất đồng bộ.

Sau khi học, bạn cần có thể:

- Phân biệt **Zipkin**, **OpenTelemetry**, **OTLP**, **OpenTelemetry Collector** và **tracing backend**.
- Thêm instrumentation Spring Modulith vào ứng dụng Spring Boot có Micrometer Tracing.
- Cấu hình đường xuất dữ liệu trực tiếp tới Zipkin hoặc qua OTLP tới Collector/backend tương thích.
- Kết hợp **Actuator module graph**, spans, event publication metrics và log correlation để quan sát một luồng nghiệp vụ.
- Phát hiện lỗi exporter, sai endpoint/protocol, sampling và mất context tại ranh giới async.

## 1. Hiểu đúng các thành phần của hệ quan sát

Đầu tiên cần tách **dữ liệu quan sát**, **cách truyền dữ liệu**, **bộ thu thập** và **nơi lưu trữ/hiển thị**:

| Thành phần | Vai trò | Có phải nơi xem trace không? |
| --- | --- | --- |
| **Micrometer Observation** | API ghi nhận observation về hoạt động của ứng dụng; tích hợp metrics và tracing. | Không. |
| **Micrometer Tracing** | Cầu nối đến tracer như OpenTelemetry hoặc Brave; tạo/quản lý spans và trace context. | Không. |
| **Spring Modulith observability** | Tạo observation/spans cho tương tác qua API module, kèm thông tin module; ghi nhận metric công bố domain event. | Không. |
| **OpenTelemetry (OTel)** | Hệ sinh thái chuẩn hóa API, SDK, ngữ nghĩa và truyền telemetry. | Không tự là giao diện phân tích. |
| **OTLP** | **OpenTelemetry Protocol**, dùng chuyển telemetry qua HTTP hoặc gRPC. | Không: đó là giao thức, không phải sản phẩm UI. |
| **OpenTelemetry Collector** | Nhận, xử lý, gom lô, lọc và chuyển telemetry đến các backend. | Thông thường không: Collector làm nhiệm vụ pipeline. |
| **Zipkin** | Hệ thống nhận, lưu và truy vấn **distributed traces**, có giao diện xem trace. | Có. |
| **Jaeger / Grafana Tempo / dịch vụ APM** | Ví dụ các backend khác nhau để lưu, tìm và phân tích trace theo cách từng sản phẩm hỗ trợ. | Thường có giao diện trực tiếp hoặc qua công cụ khác. |
| **Prometheus / Grafana** | Prometheus thu thập/lưu time series metrics; Grafana hiển thị dashboard và kết hợp nguồn dữ liệu. | Grafana có thể xem traces khi kết nối trace datasource phù hợp. |

**Ba tín hiệu chủ yếu** cần phân biệt:

- **Trace** cho biết đường đi của một yêu cầu hoặc công việc xuyên qua các span; có **traceId**, **spanId**, quan hệ cha-con hoặc span link, thời gian và thuộc tính.
- **Metric** tổng hợp các phép đo như số request, thời gian xử lý, sự kiện công bố, số lỗi; dữ liệu phù hợp cho xu hướng và cảnh báo.
- **Log** mô tả chi tiết một sự kiện tại thời điểm cụ thể; muốn tìm cùng một yêu cầu nên có **traceId** hoặc mã tương quan nghiệp vụ.

Không phải cứ bật OTLP là cả ba tín hiệu đều tự xuất. **Traces, metrics và logs có exporter, dependency, cấu hình và pipeline riêng**. Spring Modulith chủ yếu bổ sung thông tin module vào telemetry do hệ sinh thái Spring Boot/Micrometer thu thập.

## 2. Hai đường đưa module spans đến hệ quan sát

~~~mermaid
flowchart LR
    Client["HTTP Client"] --> App["Spring Boot + Spring Modulith"]
    App --> Obs["Micrometer Observation"]
    Obs --> Trace["Micrometer Tracing / OTel hoặc Brave"]
    Trace -->|"Zipkin exporter"| Zipkin["Zipkin API và UI"]
    Trace -->|"OTLP HTTP/gRPC"| Collector["OpenTelemetry Collector"]
    Collector --> Processor["Lọc / gom lô / định tuyến"]
    Processor --> Backend["Trace backend: Tempo, Jaeger, APM..."]
    App --> Metrics["Micrometer MeterRegistry"]
    Metrics --> MBack["Metrics backend"]
    App --> Logs["Structured logs"]
    Logs --> LBack["Log backend"]
~~~

Đây là **hai lối xuất trace thay thế**, không nhất thiết phải đồng thời cấu hình trên một ứng dụng. Khi dùng cả hai exporter, cần hiểu mục đích nhân bản và tác động tới chi phí, đường xử lý lỗi, sampling để tránh tưởng hai bản ghi là hai lần thực thi nghiệp vụ.

### Đường A — gửi trực tiếp tới Zipkin

~~~text
Spring Modulith module span
  -> Micrometer Tracing
  -> Zipkin exporter
  -> Zipkin HTTP API (thường là /api/v2/spans ở cổng 9411)
  -> Zipkin UI (thường http://localhost:9411)
~~~

Đường này phù hợp khi học tracing tại máy hoặc hệ thống có Zipkin sẵn. Zipkin vừa có API nhận span vừa có giao diện tìm kiếm. **Zipkin API không đồng nghĩa OTLP receiver**; không gửi OTLP vào cổng Zipkin HTTP rồi mặc định mong hệ thống hiểu giao thức đó.

### Đường B — gửi OTLP vào Collector

~~~text
Spring Modulith module span
  -> Micrometer Tracing + OpenTelemetry
  -> OTLP exporter
  -> Collector receiver (OTLP/HTTP hoặc OTLP/gRPC)
  -> processors
  -> exporter tương thích với backend
  -> trace backend và giao diện truy vấn
~~~

Đường này thuận tiện để thêm bước xử lý tập trung: gán tài nguyên, batch, giới hạn dữ liệu, lọc thuộc tính và chuyển đến nhiều hệ thống. Nó cũng tránh buộc từng ứng dụng phải biết chi tiết của backend phía sau Collector. Tuy nhiên, Collector phải có **receiver + service pipeline + exporter** đúng loại; chỉ mở cổng mà không nối pipeline đến exporter sẽ không tạo dữ liệu quan sát ở backend.

## 3. Spring Modulith bổ sung gì cho tracing?

Trong chế độ production, **Spring Modulith Insight starter** cung cấp tích hợp Actuator và observability. Nếu không dùng starter tổng hợp, có thể chọn các dependency riêng như **spring-modulith-actuator** và **spring-modulith-observability-core**, kết hợp với Spring Boot Actuator và tracer tương ứng.

Khi instrumentation hoạt động, các lời gọi qua **API của application module** có thể được chặn để tạo module entry spans, cho thấy tương tác giữa các module. Những thuộc tính module được tài liệu hóa gồm:

| Span attribute | Ý nghĩa |
| --- | --- |
| **module.identifier** | Mã định danh module. |
| **module.name** | Tên module. |
| **module.method** | Phương thức module được gọi. |
| **module.invocation-type** | Kiểu gọi, ví dụ bean invocation hoặc event listener. |

Chúng hữu ích khi lọc trace theo module hoặc tìm đoạn tương tác tốn nhiều thời gian. Dù vậy, **không phải mọi private method hay mọi câu SQL đều tự có một module span riêng**. Muốn thấy chi tiết sâu hơn có thể cần instrumentation HTTP client, database hoặc custom Observation.

Spring Modulith còn có các metric công bố sự kiện miền, đáng chú ý là:

- **module.events.published**: counter tổng hợp số sự kiện miền được công bố.
- **module.events.published.$moduleIdentifier.$simpleEventTypeName**: counter theo module và kiểu sự kiện, có thể mở rộng bằng customizer của Spring Modulith.

Các tên trên là metric do tài liệu Spring Modulith công bố; chúng khác với những metric nghiệp vụ tự thiết kế như **event_listener_failed_total** hay **event_publication_pending**. **Metric số lần phát sự kiện không chứng minh listener đã xử lý thành công**.

Spring Modulith cũng cung cấp endpoint mô tả cấu trúc module ở **/actuator/modulith** khi thêm dependency và expose endpoint phù hợp. Endpoint này có thể mô tả module, package và quan hệ phụ thuộc, kể cả loại **EVENT_LISTENER**. Đây là **góc nhìn kiến trúc**, không phải trang hiển thị runtime trace.

## 4. Thiết lập dependency theo dòng Spring Boot

Tên starter và cấu hình xuất trace thay đổi giữa các dòng Spring Boot. Khi sao chép ví dụ, **phải kiểm tra dòng phiên bản trong dự án**. Các ví dụ Gradle bên dưới giả định ứng dụng đã quản lý version tương thích qua Spring Boot/Spring Modulith BOM; vì thế không ghim số version riêng cho từng thư viện.

### 4.1. Spring Boot 3.x — OpenTelemetry và OTLP

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Các tương tác giữa application modules.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Quan sát Spring -> OpenTelemetry -> OTLP.
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

~~~yaml
# application.yml — minh họa cho Spring Boot 3.x
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 1.0  # Chỉ dùng trong lab để thấy nhiều trace.
  otlp:
    tracing:
      transport: http
      endpoint: http://localhost:4318/v1/traces
  endpoints:
    web:
      exposure:
        include: health,info,metrics,modulith
~~~

**management.otlp.tracing.endpoint** là nhóm property dành cho OTLP tracing trên Spring Boot 3.x. Ví dụ sử dụng **OTLP/HTTP** và đường dẫn **/v1/traces**. Nếu chuyển sang OTLP/gRPC, phải cấu hình transport và địa chỉ phù hợp với collector; không dùng đường dẫn HTTP trên kết nối gRPC.

**management.tracing.sampling.probability: 1.0** chỉ nên dùng khi demo hoặc trong bài kiểm thử nhỏ. Ở môi trường sản xuất, tỉ lệ lấy mẫu phải cân bằng nhu cầu điều tra với lưu lượng, chi phí lưu trữ và chính sách bảo mật.

### 4.2. Spring Boot 3.x — gửi trực tiếp Zipkin

Nếu chọn Zipkin thay vì OTLP, dùng bộ dependency exporter phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-zipkin'
}
~~~

~~~yaml
# application.yml — Spring Boot 3.x + Zipkin
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
  endpoints:
    web:
      exposure:
        include: health,info,metrics,modulith
~~~

Ở cấu hình này, **Zipkin exporter** gửi span đến Zipkin API. Đường dẫn **/api/v2/spans** là endpoint nhận dữ liệu, còn trang web Zipkin thường nằm ở gốc **http://localhost:9411**. Nếu lựa chọn tracer **Brave** thay vì OpenTelemetry, dependency bridge và reporter cũng phải đổi tương ứng; không tự trộn nhiều tracer bridge khi chưa xác định cơ chế auto-configuration.

### 4.3. Spring Boot 4.x — dùng starter và namespace mới

Trên Spring Boot 4.x, tài liệu chính thức đưa ra starter **spring-boot-starter-opentelemetry** cho OpenTelemetry/OTLP và **spring-boot-starter-zipkin** cho Brave/Zipkin. Nhóm property tracing exporter cũng khác dòng 3.x:

~~~groovy
// Chọn đường OTLP cho ứng dụng Spring Boot 4.x.
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

~~~yaml
# application.yml — Spring Boot 4.x + OTLP/HTTP
spring:
  application:
    name: shop-modulith

management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://localhost:4318/v1/traces
  endpoints:
    web:
      exposure:
        include: health,info,metrics,modulith
~~~

Nếu ứng dụng Boot 4.x cần Zipkin thay vì OTLP, thay starter OpenTelemetry bằng **org.springframework.boot:spring-boot-starter-zipkin** và đặt endpoint tại **management.tracing.export.zipkin.endpoint**.

> **Lưu ý về tương thích:** Các đoạn cấu hình trên minh họa hai dòng Spring Boot. Khi triển khai thực tế, kiểm tra tài liệu Spring Boot và Spring Modulith đúng phiên bản đang dùng, nhất là BOM, starter, tên property và các module tự động cấu hình. Tránh trộn property của Boot 3.x vào 4.x vì có thể dẫn đến exporter không dùng endpoint đã khai báo.

## 5. Thiết lập OpenTelemetry Collector cho đường OTLP

Collector có cấu trúc phổ biến **receivers → processors → exporters**. Phần **service.pipelines** mới thực sự nối các thành phần thành đường đi có hiệu lực.

Một cấu hình **minh họa tối thiểu** có thể nhận OTLP/HTTP và OTLP/gRPC, gom lô rồi in dữ liệu ra log Collector để kiểm tra pipeline:

~~~yaml
# otelcol-config.yaml — môi trường lab
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  batch: {}

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

Ở ví dụ này, span xuất hiện trong **log Collector**, chưa được lưu vào Zipkin/Tempo/Jaeger. Để tìm trace trên giao diện, phải thêm **exporter tương thích với backend thật** và cấu hình pipeline trỏ đến exporter đó. Tên exporter cụ thể, khả năng hỗ trợ và cấu hình xác thực phụ thuộc phiên bản/phân phối Collector.

### Cổng và đường dẫn thường gặp

| Đích | Giao thức | Ví dụ địa chỉ | Cần nhớ |
| --- | --- | --- | --- |
| Zipkin API | Zipkin v2 qua HTTP | **http://localhost:9411/api/v2/spans** | Không phải endpoint OTLP. |
| Collector OTLP/HTTP traces | HTTP/protobuf | **http://localhost:4318/v1/traces** | Có đường dẫn **/v1/traces**. |
| Collector OTLP/gRPC | gRPC | **localhost:4317** | Không gắn đường dẫn **/v1/traces**. |
| Collector OTLP/HTTP metrics | HTTP/protobuf | **http://localhost:4318/v1/metrics** | Cần metrics exporter và pipeline metrics riêng. |
| Collector OTLP/HTTP logs | HTTP/protobuf | **http://localhost:4318/v1/logs** | Cần log exporter và pipeline logs riêng. |

**localhost** luôn được hiểu từ góc nhìn tiến trình phát kết nối. Nếu ứng dụng chạy trong container còn Collector chạy container khác, **localhost:4318** trong ứng dụng trỏ tới chính container ứng dụng. Hãy dùng hostname/service name trên network chung hoặc cấu hình địa chỉ phù hợp với hệ triển khai. Khi debug lỗi xuất trace, đây là nguyên nhân cần kiểm tra đầu tiên.

### Collector không tự thay thế backend

Collector có thể tiếp nhận span thành công nhưng trace vẫn không hiện trên UI khi pipeline chỉ xuất sang **debug exporter** hoặc backend không nhận dữ liệu. Phải kiểm tra cả hai chặng:

1. **Ứng dụng → Collector:** endpoint đúng, receiver đang lắng nghe, request thành công, có batch nhận vào.
2. **Collector → backend:** exporter có hoạt động, quyền truy cập hợp lệ, lỗi gửi/queue/drop, backend có lưu span và UI đang truy vấn đúng service/time range.

Với môi trường sản xuất, cần thêm chính sách queue, retry, processor phù hợp, thông số memory và kiểm soát quyền truy cập. Không coi cấu hình demo mở cổng **0.0.0.0** là cấu hình an toàn mặc định cho môi trường công khai.

## 6. Đọc trace theo ranh giới application module

Giả sử ứng dụng có ba module: **order**, **payment** và **notification**. Một yêu cầu đặt hàng tạo giao dịch nghiệp vụ và sau đó phát sự kiện để gửi email:

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Người dùng
    participant W as HTTP Controller
    participant O as Order module
    participant P as Payment module
    participant N as Notification module
    participant B as Trace backend
    U->>W: POST /orders
    W->>O: placeOrder()
    O->>P: reservePayment()
    P-->>O: payment reserved
    O->>O: publish OrderPlaced
    O-->>W: transaction commit
    W-->>U: HTTP 201
    Note over O,N: Listener có thể chạy sau commit trên luồng khác
    O-->>N: OrderPlaced event
    N->>N: sendConfirmation()
    O-->>B: export spans (batch)
    P-->>B: export spans (batch)
    N-->>B: export spans (batch)
~~~

Các mũi tên xuất span chỉ minh họa logic; exporter thường **gom batch và gửi trễ**, không nhất thiết gửi ngay sau từng phương thức. Việc client nhận HTTP 201 cũng **không chứng minh listener bất đồng bộ đã hoàn tất**.

Trong trace mong đợi, kỹ sư muốn thấy:

- Span HTTP nhận yêu cầu, với route đã chuẩn hóa.
- Span khi đi qua API **order** và khi gọi **payment**, kèm thông tin module.
- Listener xử lý **OrderPlaced**, thời lượng thực thi và trạng thái lỗi nếu có.
- Trace ID để lọc các spans thuộc cùng ngữ cảnh quan sát; **eventId** hoặc **orderId** trong log để truy vết nghiệp vụ khi async tạo trace mới.

**Quan sát một trace không chứng minh toàn bộ kiến trúc đúng:** nó chỉ thể hiện những tương tác đã được instrument và sampled trong một lần thực thi. Để đối chiếu cấu trúc module, dùng module graph và endpoint **/actuator/modulith**; để xác nhận quy tắc phụ thuộc, dùng kiểm thử kiến trúc; để tìm chậm/lỗi runtime, dùng traces, metrics, logs.

### Trace IDs và module attributes

Một minh họa các span được ghi nhận:

~~~text
traceId = 4bf92f3577b34da6a3ce929d0e0e4736

HTTP POST /orders                          340 ms
  module=order    OrderService.placeOrder    300 ms
    module=payment PaymentService.reserve   110 ms
~~~

Listener có thể xuất hiện như span liên kết trong cùng trace **nếu context được truyền phù hợp**, hoặc trong một trace khác khi ranh giới async không giữ context. Dù trong cùng hay khác trace, hãy ghi **eventId** ở cả publisher và consumer. Không thêm **orderId**/**eventId** vào metric tag: các giá trị này có cardinality cao.

## 7. Context propagation qua HTTP và luồng bất đồng bộ

**Trace context propagation** mang các thông tin cần thiết để nối span khi chuyển giữa thành phần hoặc giữa luồng. Hai loại ranh giới thường gặp:

**Qua HTTP.** Nếu module gọi một service khác bằng **RestClient.Builder** hoặc **WebClient.Builder** được Spring Boot tự cấu hình, tracing có thể tạo và truyền header tiêu chuẩn, thường là W3C **traceparent** (và **tracestate** khi phù hợp). Nếu tự khởi tạo client không qua builder đã được instrument, header có thể không được gắn. Bên nhận cũng cần tracer/instrumentation và cấu hình propagation tương thích.

**Qua executor/async listener.** Khi chuyển sang thread pool, ngữ cảnh theo luồng như current observation, MDC hay security context không tự nhiên được bảo đảm chuyển theo. Tùy phiên bản Spring Framework/Micrometer và executor, cần cấu hình context propagation hoặc **TaskDecorator**; phải kiểm tra đúng executor thực sự được **@Async** hoặc **@ApplicationModuleListener** sử dụng.

Ví dụ Java minh họa cách bổ sung decorator cho **ThreadPoolTaskExecutor** mà ứng dụng tự quản lý:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
class TaskExecutionConfig {

    @Bean
    ThreadPoolTaskExecutor observationTaskExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("observed-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Đoạn mã chỉ tạo **một executor được trang bị decorator**. Nó **không tự chứng minh mọi listener đang dùng executor này**. Trong ứng dụng thực tế, phải nối executor đúng với cơ chế async, kiểm tra cấu hình context-propagation tương ứng và test trace thực tế. Đây cũng không phải lý do để gắn một traceId vào payload chỉ nhằm ép trace liên tục.

**Ngữ cảnh tracing không đồng nghĩa ngữ cảnh giao dịch.** Chuyển trace context qua thread có thể giữ thông tin quan sát nhưng không mang một JDBC transaction của luồng publisher sang listener. Listener bất đồng bộ cần transaction và chính sách xử lý lỗi riêng.

### Correlation ID trong log

Khi Micrometer Tracing hoạt động, Spring Boot có thể thêm **traceId/spanId** vào MDC và định dạng log correlation. Ví dụ:

~~~text
INFO  traceId=4bf92f3577b34da6a3ce929d0e0e4736
      module=order action=order_placed eventId=e-102

INFO  traceId=4bf92f3577b34da6a3ce929d0e0e4736
      module=notification action=listener_started eventId=e-102
~~~

Nếu dòng log notification không có traceId hoặc dùng traceId khác, trước tiên kiểm tra context propagation. **eventId** vẫn cho phép đối chiếu nghiệp vụ dù trace sampling thấp hoặc trace được khởi tạo lại; mã này nên hiện trong structured logs khi phù hợp với chính sách dữ liệu.

Không đưa email, token, session ID, số thẻ, payload yêu cầu hoặc dữ liệu định danh nhạy cảm vào span attributes/baggage. Với baggage truyền qua mạng, cần thiết kế danh sách trường được phép và giới hạn kích thước; có thể xuất hiện cả trong HTTP headers.

## 8. Kết hợp Actuator, metrics, traces và logs

Mỗi loại tín hiệu trả lời một phần câu hỏi:

| Câu hỏi vận hành | Điểm kiểm tra phù hợp |
| --- | --- |
| Ứng dụng hiện có những module nào? | **GET /actuator/modulith** khi đã expose. |
| Module nào phụ thuộc module nào, theo hình thức nào? | JSON modulith Actuator, kiểm tra kiến trúc và module graph. |
| Tần suất domain event tăng hay giảm? | Metric **module.events.published** và các metric event cụ thể. |
| Một request bị chậm ở module nào? | Trace có module spans, xem duration và mối quan hệ span. |
| Lỗi có tập trung ở một event listener? | Log lỗi, metric lỗi listener tùy instrumentation và trace có exception/status. |
| Bao nhiêu publication đang chờ hoàn tất? | Event Publication Registry hoặc custom gauge; không suy ra từ event-published counter. |
| Có liên hệ được một lỗi với yêu cầu ban đầu? | traceId/spanId nếu được propagate; eventId/correlation ID cho async. |
| Collector có nhận telemetry không? | Collector diagnostics, logs, receiver/exporter metrics, backend ingestion. |

### Metrics: Prometheus và OTLP là hai cách xuất khác nhau

Nếu dùng Prometheus, ứng dụng thường cần **micrometer-registry-prometheus**, bật và expose **/actuator/prometheus** để Prometheus scrape định kỳ. Nếu dùng **OTLP metrics**, cần **micrometer-registry-otlp** và cấu hình URL/pipeline metrics. Đừng coi việc gửi trace qua OTLP là tự động chuyển cả metrics của Micrometer qua cùng endpoint.

~~~groovy
// Ví dụ chọn xuất metrics cho Prometheus:
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
~~~

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,modulith
~~~

**/actuator/metrics** giúp kiểm tra meter trong tiến trình ứng dụng; **/actuator/prometheus** có nội dung scrape khác và yêu cầu registry tương ứng. Không expose mọi Actuator endpoint công khai: thiết lập network/authentication/authorization theo yêu cầu môi trường.

Đối với Spring Modulith, metric event publication có thể có tag **module.identifier**, **module.name** và **module.event.type**. Đây là những nhãn cardinality thấp nếu tập module/event type có giới hạn. Với metric nghiệp vụ tự instrument thêm, ưu tiên nhãn **module**, **eventType**, **listener**, **outcome**; không dùng **eventId** hay **orderId** làm label.

### Ba dashboard hữu ích

| Dashboard | Chỉ số / nguồn | Khi nào cần |
| --- | --- | --- |
| **Dòng sự kiện mô-đun** | Event-published rate theo module/type; pending và tuổi pending nếu có registry; error rate listener tự instrument. | Phát hiện phát nhiều nhưng không xử lý kịp. |
| **Độ trễ luồng nghiệp vụ** | p95/p99 request, module spans, duration API downstream, tỷ lệ lỗi. | Tìm module gây trễ và dependency đang nghẽn. |
| **Sức khỏe telemetry pipeline** | Collector received/sent/dropped, exporter error, độ trễ backend ingestion, trace search có dữ liệu. | Phân biệt ứng dụng không tạo spans với exporter/backend làm mất spans. |

Thông số thực tế của Collector thay đổi theo phiên bản; dashboard phải dựa trên metric name xuất hiện trong hệ thống đang chạy, không giả định một danh sách tên cố định cho mọi bản phân phối.

## 9. Cách kiểm tra end-to-end trong môi trường học

Một bài thực hành nhỏ có thể dùng ứng dụng Spring Boot có các module **order** và **notification**. Luồng **POST /orders** lưu đơn và công bố **OrderPlaced**; module notification lắng nghe sau commit.

**Bước 1 — Chọn một đường xuất trace.** Với Zipkin, khởi chạy Zipkin và dùng exporter Zipkin đúng dòng Spring Boot. Với OTLP, khởi chạy Collector có receiver **4318 HTTP** và pipeline **traces**; ban đầu dùng debug exporter để xác nhận dữ liệu đến, rồi nối backend truy vấn.

**Bước 2 — Bật instrumentation.** Thêm **spring-modulith-starter-insight**, Spring Boot Actuator và đúng tracer/exporter. Đảm bảo version được quản lý tương thích; đặt **spring.application.name** có ý nghĩa để backend dễ tìm service.

**Bước 3 — Bật sampling 100% tạm thời.** Trong lab, dùng **management.tracing.sampling.probability: 1.0** và tạo vài request. Nếu test chỉ tạo một request mà sampling là 10%, không thấy trace chưa đủ để kết luận exporter lỗi.

**Bước 4 — Quan sát module graph.** Truy cập **/actuator/modulith** từ môi trường cho phép và kiểm tra có module dự kiến, quan hệ phụ thuộc **EVENT_LISTENER** khi được nhận diện. Nếu trả 404/không có endpoint, kiểm tra dependency, exposure và bảo mật Actuator.

**Bước 5 — Quan sát spans.** Trong Zipkin hoặc trace backend khác, tìm service **shop-modulith** trong khung thời gian vừa thử. Mở trace, xác nhận các module spans và xem attributes **module.identifier**, **module.method** ở những span được tạo. Nếu async listener tạo trace riêng, dùng eventId trong logs để đối chiếu.

**Bước 6 — Quan sát metrics.** Kiểm tra **/actuator/metrics**, tìm **module.events.published** nếu instrumentation đã hoạt động, rồi phát thêm sự kiện để kiểm tra counter tăng. Nếu xuất Prometheus, xác nhận endpoint **/actuator/prometheus** có dữ liệu scrape. Không lấy việc metric tăng làm bằng chứng listener đã thành công.

**Bước 7 — Gây lỗi có kiểm soát.** Làm notification listener thất bại trong môi trường test; tìm exception ở logs/traces, đối chiếu trạng thái publication nếu bật registry, xác nhận giao dịch order đã commit độc lập. Sau đó sửa lỗi và thử cơ chế phát lại theo cấu hình, kết hợp idempotency để ngăn tạo tác vụ trùng.

### Bằng chứng nên lưu từ bài lab

| Bằng chứng | Tiêu chí đạt |
| --- | --- |
| Cấu hình ứng dụng | Tracer và exporter chỉ rõ một đường xuất trace chính, dùng property đúng Boot version. |
| Actuator modulith | Có danh sách module và quan hệ phụ thuộc hợp lý. |
| Trace UI | Tìm được ít nhất một trace có module span và thuộc tính module. |
| Event metrics | Counter publication tăng khi phát event thử nghiệm. |
| Logs | Có mã tương quan giúp nối request, publisher và listener. |
| Collector hoặc Zipkin ingress | Xác nhận nhận được spans, không có lỗi giao thức/endpoint. |
| Xử lý async | Biết listener hoàn tất hay lỗi độc lập với HTTP response. |

## 10. Chẩn đoán khi không thấy trace hoặc thiếu span

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra và xử lý |
| --- | --- | --- |
| Zipkin UI không có service | Sai endpoint, Zipkin chưa chạy, exporter chưa có, sampling thấp | Kiểm tra dependency, logs exporter, **/api/v2/spans**, thử 100% sampling trong lab. |
| OTLP exporter báo lỗi kết nối | Sai hostname/cổng, Docker localhost, firewall, receiver chưa bật | Kiểm tra từ **đúng runtime của ứng dụng** tới collector, port binding và receiver config. |
| Lỗi gRPC/HTTP hoặc 404 ở Collector | Dùng gRPC trên cổng HTTP, thiếu **/v1/traces** hoặc sai transport | Đối chiếu **4317/gRPC** với **4318/HTTP** và endpoint của exporter. |
| Collector nhận span nhưng backend trống | Pipeline chưa có exporter backend, exporter lỗi hoặc backend không ingest | Xem service.pipelines, log/meter của exporter, quyền truy cập và giao diện backend. |
| Có trace HTTP nhưng không thấy module span | Thiếu Spring Modulith observability hoặc lời gọi không đi qua API được instrument | Kiểm tra **spring-modulith-starter-insight**, API module, phiên bản và điều kiện instrumentation. |
| Không thấy listener span trong cùng trace | Async context không được truyền hoặc listener chạy ở thời điểm khác | Kiểm tra executor/TaskDecorator, correlation ID và eventId; tìm trace liên quan. |
| Một số request không có trace | Sampling hoặc filter cấu hình thấp | Kiểm tra xác suất sampling và chính sách head/tail sampling ở exporter/collector/backend. |
| Metric có nhưng trace không có | Registry metric hoạt động độc lập; tracer/exporter chưa sẵn sàng | Kiểm tra Micrometer Tracing, exporter và backend trace. |
| Log có traceId nhưng Zipkin không có trace | Span chưa được sampled, export bị lỗi/drop hoặc tra sai thời gian/service | Kiểm tra sampling, queue exporter, clock/timezone và độ trễ batch. |
| Trace có rất nhiều nhãn hoặc chứa dữ liệu nhạy cảm | Tùy chỉnh span/metric dùng định danh cá nhân hoặc payload | Xóa thuộc tính không cần thiết; dùng nhãn cardinality thấp và chính sách dữ liệu. |

### Thứ tự chẩn đoán giúp tránh nhầm tầng

~~~mermaid
flowchart TD
    A["Không tìm thấy trace"] --> B{"Ứng dụng có tracer và exporter?"}
    B -->|Không| C["Sửa dependency và auto-configuration"]
    B -->|Có| D{"Sampling có giữ trace thử nghiệm?"}
    D -->|Không| E["Tăng sampling tạm thời trong lab"]
    D -->|Có| F{"Receiver có nhận spans?"}
    F -->|Không| G["Kiểm tra hostname, cổng, HTTP/gRPC, TLS"]
    F -->|Có| H{"Backend có ingest và lưu?"}
    H -->|Không| I["Kiểm tra pipeline/exporter và backend"]
    H -->|Có| J["Kiểm tra service name, time range và UI filter"]
~~~

Nếu trace **thiếu một đoạn module**, cần một nhánh chẩn đoán khác: kiểm tra instrumentation của Spring Modulith và việc truyền context. Exporter thành công không có nghĩa mọi phương thức trong ứng dụng đều được instrument.

## 11. Lưu ý khi thiết kế hệ quan sát thực tế

**Đặt tên tài nguyên thống nhất.** **spring.application.name** và resource attributes nên phân biệt dịch vụ, môi trường, phiên bản triển khai để lọc dữ liệu; tránh tạo một tên service khác nhau cho mỗi instance ngẫu nhiên.

**Chọn sampling có chủ đích.** Sampling giúp kiểm soát chi phí tracing, nhưng làm trace không đầy đủ cho mọi request. Metrics và logs là nguồn bổ sung quan trọng khi điều tra một trường hợp không được lấy mẫu. Nếu có nhiều tầng sampling, hãy ghi rõ tầng nào quyết định.

**Đừng dùng trace để quyết định nghiệp vụ.** Tracing là công cụ chẩn đoán. Độ tin cậy của tác vụ async dựa vào transaction boundary, Event Publication Registry (nếu có), chính sách retry và listener idempotent, chứ không dựa vào việc một span đã được xuất.

**Bảo vệ telemetry.** Span names, attributes, log fields, baggage và exporter headers có thể chứa thông tin nhạy cảm. Cần kiểm soát truy cập Actuator, truyền dữ liệu bằng TLS ở môi trường thực tế, giữ token trong secret manager và thiết lập retention phù hợp.

**Quan sát chính pipeline quan sát.** Collector, exporter và backend cũng có thể quá tải. Đo tỷ lệ nhận/gửi/drop, kích thước queue, lỗi xác thực và độ trễ ingest; nếu telemetry bị mất, trước hết cần biết mất ở ứng dụng hay ở đường xuất.

**Giữ tài liệu kiến trúc và runtime liên hệ được.** Mỗi module nên có tên/identifier ổn định; các event type quan trọng nên có hợp đồng rõ ràng. Dashboard có thể lọc theo module để đối chiếu với module graph, nhưng trace chỉ là bằng chứng của những lần chạy đã quan sát được.

## 12. Nguồn tham khảo và hướng tự học

Tài liệu chính thức nên ưu tiên khi cấu hình hoặc nâng phiên bản:

- **Spring Modulith — Production-ready Features:** https://docs.spring.io/spring-modulith/reference/production-ready.html — starter insight, endpoint **/actuator/modulith**, module spans và event publication metrics.
- **Spring Boot 3.5 — Tracing:** https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html — bridge OpenTelemetry/Brave, exporter Zipkin và OTLP, property của dòng 3.x.
- **Spring Boot 4.x — Tracing:** https://docs.spring.io/spring-boot/reference/actuator/tracing.html — starter OpenTelemetry/Zipkin, namespace property exporter của dòng 4.x, log correlation và sampling.
- **Spring Boot — Metrics:** https://docs.spring.io/spring-boot/reference/actuator/metrics.html — Micrometer registries, Actuator metrics, Prometheus và OTLP metrics.
- **OpenTelemetry Collector — Configuration:** https://opentelemetry.io/docs/collector/configuration/ — cấu trúc receiver/processor/exporter/service pipeline, protocol và extension.

## 13. Kết luận

Trong Spring Modulith, **module graph** mô tả kiến trúc, còn **Micrometer Observation/Tracing** giúp thấy một phần các tương tác module diễn ra khi chạy. **Zipkin** là hệ thống tìm và hiển thị trace; **OTLP** là giao thức chuyển telemetry; **Collector** nối instrumentation với các backend quan sát. Việc chọn đường đi phải nhất quán với dependency, phiên bản Spring Boot, cổng/giao thức và cách backend nhận dữ liệu.

Một ứng dụng được quan sát tốt không chỉ có giao diện hiển thị trace. Nó còn có metric số sự kiện công bố, dữ liệu tình trạng listener, structured log nối bằng traceId hoặc eventId, dashboard theo module và quy trình chẩn đoán khi telemetry bị mất. Kết hợp các bằng chứng đó mới giúp trả lời: **tương tác xuyên module nào thực sự đã xảy ra, mất bao lâu, thất bại ở đâu và có thể kiểm chứng sau khi triển khai hay không?**

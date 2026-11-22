# Truyền trace context và xuất telemetry từ ứng dụng Java

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt traces, metrics và logs; biết cách ba tín hiệu bổ sung cho nhau khi điều tra sự cố.
- Giải thích trace, span, parent-child relationship, span link, trace ID, span ID, sampling và baggage.
- Mô tả W3C Trace Context (`traceparent`, `tracestate`, `baggage`), B3 và AWS X-Ray header (`X-Amzn-Trace-Id`).
- Truyền trace context qua HTTP, Spring MVC/WebFlux, `@Async`, executor, Reactor và message queues.
- Dùng Spring Boot Actuator, Micrometer Observation/Tracing và OpenTelemetry để instrument ứng dụng.
- Chọn chiến lược Spring Boot Micrometer, ADOT Java agent hoặc OpenTelemetry API thủ công mà không tạo spans trùng lặp.
- Tạo custom observations/spans, gắn attributes có kiểm soát và đưa trace ID/span ID vào log MDC.
- Instrument AWS SDK for Java 2.x, S3/SQS và hiểu propagation qua message attributes/system attributes.
- Cấu hình OTLP exporter và Collector, gửi traces tới AWS X-Ray/CloudWatch Transaction Search, metrics tới CloudWatch và logs tới CloudWatch Logs.
- Thiết lập sampling, resource attributes, batch/retry, IAM, network và bảo vệ telemetry.
- Kiểm thử propagation, xác minh telemetry và chẩn đoán lỗi mất context, duplicate spans, exporter timeout hoặc AccessDenied.
- Hiểu lộ trình chuyển từ AWS X-Ray SDK/Daemon sang OpenTelemetry.

**Bối cảnh module:** Bài thuộc chương **Ứng dụng Java và Spring Boot** trong `CLOUD_PROVIDERS_AWS`. Một request AWS có thể đi qua API Gateway/ALB, Spring Boot service, SQS/SNS, worker, database và S3. Trace context nối các bước này thành một hành trình có thể điều tra; metrics cho biết xu hướng sức khỏe; logs ghi chi tiết sự kiện.

> **Phạm vi:** Ví dụ sử dụng Spring Boot 3.5.x/4.x, Micrometer, OpenTelemetry, AWS Distro for OpenTelemetry (ADOT), AWS SDK for Java 2.x, Amazon CloudWatch và AWS X-Ray. Dependencies/properties thay đổi theo release; luôn dùng BOM và reference docs của đúng phiên bản. Tên service, Region, queue, account và endpoint trong ví dụ là dữ liệu minh họa.

## 1. Bài toán: vì sao API thành công nhưng worker vẫn xử lý lỗi?

Một khách hàng tạo đơn hàng. Orders API nhận request, lưu dữ liệu, gửi event vào SQS. Một worker đọc message, gọi dịch vụ thanh toán và lưu hóa đơn lên S3.

API trả HTTP 202, nhưng vài phút sau worker gặp timeout. Log chỉ ghi `Payment gateway timeout`; không có thông tin để biết request ban đầu, message nào, worker instance nào hoặc lần retry nào liên quan.

~~~mermaid
flowchart LR
    Client[Mobile / Web] --> API[Orders API]
    API --> DB[(Orders DB)]
    API --> Q[(SQS orders-events)]
    Q --> Worker[Payment worker]
    Worker --> Pay[Payment provider]
    Worker --> S3[(S3 invoices)]
    API -. logs .-> Logs[CloudWatch Logs]
    Worker -. logs .-> Logs
~~~

Nếu mỗi thành phần tự tạo request ID riêng hoặc không truyền trace context, operator chỉ thấy những mảnh log rời rạc. Khi propagation và instrumentation đúng, cùng một trace có thể chứa HTTP server span, database/client spans, SQS producer/consumer spans, payment HTTP span và S3 client span.

~~~mermaid
flowchart TD
    Root[Trace: create-order] --> HTTP[HTTP server span]
    HTTP --> Save[Save order span]
    HTTP --> Publish[SQS producer span]
    Publish --> Consume[SQS consumer span]
    Consume --> Payment[Payment HTTP client span]
    Consume --> Invoice[S3 PutObject span]
    Payment --> Error[Timeout event / error status]
~~~

**Điểm cốt lõi:** tracing chỉ hữu ích khi context đi qua ranh giới process/thread/message và các thành phần tạo spans dùng chung một trace context.

## 2. Ba tín hiệu observability

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Traces** | Một request đi qua những bước nào? Bước nào chậm/lỗi? | Trace ID, span duration, parent span |
| **Metrics** | Hệ thống hoạt động thế nào theo thời gian? | Request rate, error rate, p95 latency, queue depth |
| **Logs** | Tại một thời điểm đã xảy ra điều gì? | Exception, business event, validation failure |

Ví dụ điều tra:

| Dữ liệu | Kết quả |
| --- | --- |
| Metric | p95 POST /orders tăng từ 120 ms lên 2,4 s |
| Trace | 1,9 s nằm trong span SQS Send do throttling |
| Log | AWS SDK báo ThrottlingException, có request ID và trace ID |
| Kết luận | API chậm do publish message retry, không phải database |

~~~mermaid
flowchart LR
    App[Java / Spring Boot] --> SDK[Micrometer / OpenTelemetry]
    SDK --> OTLP[OTLP]
    OTLP --> Collector[ADOT / CloudWatch Agent]
    Collector --> XRay[AWS X-Ray / Trace Search]
    Collector --> CWMetric[CloudWatch Metrics]
    Collector --> CWLogs[CloudWatch Logs]
~~~

Telemetry là dữ liệu quan sát được ứng dụng phát ra. Exporter gửi telemetry tới endpoint; Collector/Agent nhận, xử lý, batch, lọc, sampling và chuyển tiếp tới backend.

## 3. Trace, span, trace ID và span ID

**Trace** biểu diễn hành trình của một operation qua nhiều thành phần. Trace gồm nhiều **spans**. Một span có tên operation, Trace ID, Span ID, Parent Span ID (nếu có), start/end timestamps, span kind, attributes, events, status và links.

~~~text
Trace ID: 4efaaf4d1e8720b39541901950019ee5

Span A: POST /orders                 SERVER
  Span B: orders.validate            INTERNAL
  Span C: INSERT orders              CLIENT
  Span D: SQS SendMessage             PRODUCER

Span E: orders-events receive        CONSUMER
  Span F: payment.authorize           CLIENT
  Span G: S3 PutObject                CLIENT
~~~

- **Child span:** operation được gọi trong context của parent; thường dùng cho HTTP client, DB call hoặc method con.
- **Span link:** liên kết span với một hoặc nhiều span context khác mà không ép thành quan hệ cha-con; hữu ích với batch consumer hoặc fan-in.
- **New root trace:** dùng khi operation độc lập hoặc policy yêu cầu tách trace.

Một message consumer có thể tiếp tục trace producer hoặc dùng link tùy semantics, framework và batch behavior. Không ép mọi message trong một batch vào một parent nếu chúng đến từ nhiều traces.

## 4. Trace context và W3C Trace Context

Trace context là metadata giúp service nhận biết request thuộc trace nào và span cha nào. Với W3C Trace Context, header phổ biến là:

~~~http
traceparent: 00-4efaaf4d1e8720b39541901950019ee5-00f067aa0ba902b7-01
tracestate: vendor=value
baggage: tenant-tier=gold,workflow=checkout
~~~

Cấu trúc `traceparent`:

~~~text
00 - 4efaaf4d1e8720b39541901950019ee5 - 00f067aa0ba902b7 - 01
|    |                                  |                  |
|    |                                  |                  +-- trace flags
|    |                                  +-- parent span ID
|    +-- trace ID (32 hex chars)
+-- version
~~~

- `trace-id`: định danh trace, không được toàn số 0.
- `parent-id`: Span ID của operation trước đó, không được toàn số 0.
- `trace-flags`: bit flags, trong đó sampled biểu thị quyết định sampling.
- `tracestate`: vendor-specific state, tùy chọn.
- `baggage`: cặp key/value truyền xuyên service, độc lập với traceparent.

### Correlation ID không phải trace context

Một `X-Correlation-ID` tự tạo có thể giúp tìm log, nhưng không mang parent/sampling metadata để dựng distributed trace. Trace ID cũng không phải authentication token, session ID hay authorization claim.

## 5. W3C, B3 và AWS X-Ray propagation

| Format | Header | Môi trường |
| --- | --- | --- |
| W3C Trace Context | `traceparent`, `tracestate`, `baggage` | Chuẩn phổ biến |
| B3 single | `b3` | Zipkin/Brave và hệ thống cũ |
| B3 multi | `X-B3-TraceId`, `X-B3-SpanId`, `X-B3-Sampled` | Hệ thống cũ |
| AWS X-Ray | `X-Amzn-Trace-Id` | AWS services tích hợp X-Ray |

Ví dụ X-Ray header:

~~~http
X-Amzn-Trace-Id: Root=1-5759e988-bd862e3fe1be46a994272793;Parent=53995c3f42cd8ad8;Sampled=1
~~~

- `Root`: X-Ray trace ID;
- `Parent`: segment/subsegment ID cha;
- `Sampled`: sampling decision.

AWS X-Ray hỗ trợ trace ID được tạo theo W3C, nhưng exporter phải chuyển ID sang format X-Ray tương ứng khi gửi trace document. X-Ray exporter/Collector cũ có thể kiểm tra timestamp trong trace ID và từ chối W3C IDs. Dùng ADOT/Collector release được hỗ trợ.

ADOT Java auto-instrumentation agent hỗ trợ W3C, B3 và `X-Amzn-Trace-Id` out of the box. Nếu cùng request mang nhiều header với trace IDs khác nhau, các service có thể chọn format khác nhau và trace bị chia. Chọn format production/consume theo kiến trúc và xác minh hai phía.

## 6. Propagation qua HTTP

Khi API nhận request, instrumentation extract context từ inbound headers, tạo server span, đưa span context vào execution context; khi gọi service tiếp theo, HTTP client inject context vào outbound headers. Service đích extract context và tạo span mới.

~~~mermaid
sequenceDiagram
    participant Client
    participant A as Orders API
    participant B as Inventory API
    Client->>A: POST /orders + traceparent
    A->>A: Extract parent context
    A->>A: Create SERVER span
    A->>B: GET /stock + new traceparent
    B->>B: Extract parent context
    B->>B: Create SERVER span
    B-->>A: Response
    A-->>Client: Response
~~~

### Dùng HTTP client builder của Spring Boot

Spring Boot auto-configures builders để trace context được inject. Ví dụ RestClient:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration
class HttpClientConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
            .baseUrl("https://inventory.internal")
            .build();
    }
}
~~~

`RestClient.Builder` được Spring Boot auto-configure. Không tự tạo `RestClient.builder()` rồi kỳ vọng tracing instrumentation được gắn như builder của Spring.

Với WebFlux:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ReactiveHttpConfiguration {

    @Bean
    WebClient paymentWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("https://payments.internal")
            .build();
    }
}
~~~

Nếu dùng RestTemplate, hãy dùng `RestTemplateBuilder` auto-configured. Nếu dùng Apache HttpClient/OkHttp/Feign/custom transport, kiểm tra instrumentation module của đúng stack.

## 7. Propagation qua message queue

Message queue tạo ranh giới thời gian: producer kết thúc trước khi consumer chạy. Producer phải inject trace context vào message metadata; consumer extract metadata để tạo span liên quan.

~~~mermaid
sequenceDiagram
    participant API as Orders API
    participant SQS
    participant W as Payment worker
    API->>SQS: SendMessage + trace metadata
    SQS-->>W: Deliver message + trace metadata
    W->>W: Extract context / create CONSUMER span
    W->>W: Process payment
    W-->>SQS: DeleteMessage / acknowledge
~~~

- SNS fan-out tới nhiều SQS queues có thể tạo nhiều consumer branches.
- Batch consumer có thể nhận messages từ nhiều traces; dùng links khi phù hợp.
- Retry/DLQ nên giữ event ID và metadata cần thiết để điều tra.
- Delay queue/scheduled job có thể cần trace mới kèm link tới trace ban đầu.

Trace context không thay idempotency key, message group ID hoặc business transaction ID.

## 8. AWS X-Ray trace header và SQS system attribute

AWS SDK for Java 2.x instrumentation có thể inject context vào outbound AWS API request dưới dạng `X-Amzn-Trace-Id`. Đây là header AWS managed services có thể nhận diện.

Với SQS `SendMessageBatch`, khi X-Ray propagation được bật, instrumentation có thể gắn context từng message vào `AWSTraceHeader` system attribute của entry. Carrier này độc lập với HTTP request header và không dùng một trong tối đa 10 user message attributes.

Điều này quan trọng vì HTTP request header chỉ đại diện API call tới SQS, còn message system attribute mang context gắn với từng message. Hành vi cụ thể phụ thuộc AWS SDK version, OTel AWS SDK instrumentation version và cấu hình X-Ray propagation. Kiểm tra support matrix khi dùng SendMessage, SendMessageBatch, SNS hoặc SDK clients được tạo thủ công.

## 9. Spring Boot Observability: Micrometer Observation và Tracing

Spring Boot dùng **Micrometer Observation** làm API thống nhất cho metrics và traces. Observation là operation có tên, context và key-values. Handler có thể biến observation thành metric, span và logging/correlation metadata.

| Thành phần | Vai trò |
| --- | --- |
| `ObservationRegistry` | Registry cho observations |
| `Observation` | Operation được đo/trace |
| Micrometer Tracing | API tracer độc lập implementation |
| `micrometer-tracing-bridge-otel` | Nối Micrometer với OpenTelemetry |
| OpenTelemetry SDK | Quản lý spans, context, sampler và exporters |
| OTLP exporter | Gửi telemetry tới Collector/backend |

Spring Boot auto-instrumentation có thể tạo observations cho HTTP server/client và một số tích hợp. Không phải mọi method hoặc AWS SDK call đều tự sinh span; cần kiểm tra instrumentation coverage.

## 10. Chọn chiến lược instrumentation

| Chiến lược | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| Spring Boot + Micrometer Tracing | Actuator auto-configuration, Observation API và tracer bridge | Ứng dụng Spring Boot cần Spring conventions, metrics và traces |
| OpenTelemetry/ADOT Java agent | `-javaagent` instrument bytecode của framework/client được hỗ trợ | Muốn auto-instrument nhiều libraries, gồm AWS SDK khi hỗ trợ |
| OpenTelemetry API thủ công | Tạo spans/attributes cho business operations đặc thù | Cần trace logic nghiệp vụ mà auto instrumentation không hiểu |

### Tránh duplicate instrumentation

Không bật đồng thời hai hệ thống auto-instrumentation tạo cùng một server/client span. Spring Boot Micrometer Tracing và OTel Java agent có thể cùng instrument HTTP server/client tùy version/configuration.

- **Spring-first:** Actuator + Micrometer Tracing + OTel exporter; thêm instrumentation cho AWS SDK nếu cần.
- **Agent-first:** ADOT Java agent instrument HTTP/JDBC/AWS SDK; chỉ thêm OTel API khi cần manual spans.
- **Hybrid có kiểm soát:** Spring Micrometer cho metrics/observations và agent cho library chưa được instrument; kiểm tra spans không bị lặp.

Nếu agent đã cung cấp OpenTelemetry instance, manual instrumentation nên dùng global instance theo hướng dẫn agent. Không khởi tạo OTel SDK global thứ hai.

## 11. Dependencies cho Spring Boot 3.5.x

Spring Boot 3.5 dùng Actuator và Micrometer bridge. Ví dụ Maven:

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
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Để Spring Boot BOM chọn versions phù hợp. Nếu không dùng Micrometer OTLP registry, bỏ dependency đó và cấu hình metrics exporter theo backend đang dùng. Không khai báo version riêng cho từng Micrometer/OpenTelemetry module nếu BOM đã quản lý.

## 12. Dependencies cho Spring Boot 4.x

Spring Boot 4.x có starter OpenTelemetry riêng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-opentelemetry</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-otlp</artifactId>
    </dependency>
</dependencies>
~~~

Spring Boot 4.x quản lý OpenTelemetry tracing integration và OTLP trace exporter qua auto-configuration. Metrics trong Spring portfolio vẫn được thu thập bằng Micrometer; `micrometer-registry-otlp` gửi metrics của Micrometer qua OTLP.

| Nhu cầu | Spring Boot 3.5 | Spring Boot 4.2 |
| --- | --- | --- |
| Tracing OTLP endpoint | `management.otlp.tracing.endpoint` | `management.opentelemetry.tracing.export.otlp.endpoint` |
| Sampling probability | `management.tracing.sampling.probability` | `management.tracing.sampling.probability` |
| Metrics OTLP URL | `management.otlp.metrics.export.url` | `management.otlp.metrics.export.url` |
| Resource attributes | `management.opentelemetry.resource-attributes.*` | `management.opentelemetry.resource-attributes.*` |

Không copy nguyên application.yml giữa Boot 3.5 và Boot 4.x mà không đối chiếu configuration metadata.

## 13. Resource attributes: định danh service và môi trường

Resource attributes mô tả nguồn phát telemetry, không mô tả một request cụ thể.

Các attributes thường dùng: `service.name`, `service.namespace`, `service.version`, `deployment.environment`, `cloud.provider`, `cloud.region` và `service.instance.id`.

~~~bash
OTEL_SERVICE_NAME=orders-api
OTEL_RESOURCE_ATTRIBUTES=service.namespace=commerce,deployment.environment=staging,cloud.provider=aws,cloud.region=ap-southeast-1
~~~

Hoặc cấu hình Spring Boot:

~~~yaml
management:
  opentelemetry:
    resource-attributes:
      service.name: orders-api
      service.namespace: commerce
      service.version: 1.8.0
      deployment.environment: staging
      cloud.provider: aws
      cloud.region: ap-southeast-1
~~~

Giữ `service.name` ổn định qua replicas của cùng một service. Không dùng pod ID, request ID hoặc user ID làm service.name vì làm vỡ grouping và tăng số service entities.

## 14. Cấu hình tracing cho Spring Boot 3.5

Ví dụ gửi spans tới Collector OTLP HTTP cổng 4318:

~~~yaml
spring:
  application:
    name: orders-api

management:
  tracing:
    sampling:
      probability: 0.10
  otlp:
    tracing:
      endpoint: http://otel-collector:4318/v1/traces
      transport: http
  observations:
    key-values:
      cloud.region: ap-southeast-1
      deployment.environment: staging
~~~

Spring Boot 3.5 mặc định sample 10% requests. Đặt probability 1.0 trong test để nhìn thấy mọi trace, nhưng không mặc định dùng 100% trong production.

Có thể cấu hình propagation consume W3C/B3 và produce W3C. Với AWS X-Ray propagation, dùng ADOT/X-Ray propagator hoặc instrumentation hỗ trợ AWS header.

## 15. Cấu hình tracing cho Spring Boot 4.x

Với Spring Boot 4.2, cấu hình OTLP theo namespace OpenTelemetry:

~~~yaml
spring:
  application:
    name: orders-api

management:
  tracing:
    sampling:
      probability: 0.10
  opentelemetry:
    tracing:
      sampler: parent-based-trace-id-ratio
      export:
        otlp:
          endpoint: http://otel-collector:4318/v1/traces
          transport: http
          compression: gzip
    resource-attributes:
      service.name: orders-api
      service.namespace: commerce
      deployment.environment: staging
      cloud.provider: aws
      cloud.region: ap-southeast-1
~~~

Có thể đặt endpoint chung `management.opentelemetry.otlp.endpoint` rồi để Boot thêm signal path khi dùng HTTP. Endpoint riêng cho traces sẽ được ưu tiên nếu khai báo.

## 16. Tạo custom observation bằng Micrometer

Spring Boot khuyến nghị dùng `ObservationRegistry` cho business operations cần cả metric và trace.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    private final ObservationRegistry observations;
    private final PaymentGateway paymentGateway;

    public PaymentService(ObservationRegistry observations,
                          PaymentGateway paymentGateway) {
        this.observations = observations;
        this.paymentGateway = paymentGateway;
    }

    public PaymentResult authorize(String orderId, long amount) {
        return Observation.createNotStarted("payment.authorize", observations)
            .lowCardinalityKeyValue("payment.provider", "primary")
            .lowCardinalityKeyValue("payment.operation", "authorize")
            .highCardinalityKeyValue("order.id", orderId)
            .observe(() -> paymentGateway.authorize(orderId, amount));
    }
}
~~~

- `payment.authorize` là tên observation.
- `payment.provider` và `payment.operation` có ít giá trị, phù hợp metric tags.
- `order.id` có nhiều giá trị; chỉ đưa vào trace khi thực sự cần và không chứa dữ liệu nhạy cảm.

Low-cardinality values được thêm vào metrics và traces; high-cardinality values chỉ nên thêm vào traces. Không đưa email, customer ID, request UUID, URL chứa query params hoặc raw SQL vào metric labels.

## 17. Tạo span thủ công cho business operation đặc thù

Ví dụ một bước nghiệp vụ không được framework tự instrument:

~~~java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Component;

@Component
public class FraudDecision {

    private final Tracer tracer;

    public FraudDecision(Tracer tracer) {
        this.tracer = tracer;
    }

    public boolean evaluate(String orderId) {
        Span span = tracer.nextSpan()
            .name("fraud.evaluate")
            .tag("fraud.engine", "rules-v2")
            .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            boolean approved = runRules(orderId);
            span.tag("fraud.result", approved ? "approved" : "rejected");
            return approved;
        } catch (RuntimeException ex) {
            span.error(ex);
            throw ex;
        } finally {
            span.end();
        }
    }

    private boolean runRules(String orderId) {
        return true;
    }
}
~~~

Đóng span trong finally để exporter nhận đủ duration/status. Không bắt exception rồi bỏ qua; hãy ghi error và giữ semantics của business operation. Một span nên đại diện operation có ý nghĩa, không phải từng getter/setter.

## 18. Context propagation qua @Async và thread pools

Trong code đồng bộ, context thường nằm trong scope hiện tại. Khi chuyển sang thread khác, ThreadLocal của thread gốc không tự xuất hiện trên worker thread.

Spring Boot Context Propagation hỗ trợ:
- Với auto-configured AsyncTaskExecutor, có thể bật `spring.task.execution.propagate-context=true` ở release hỗ trợ property này.
- Với executor tự cấu hình, gắn `ContextPropagatingTaskDecorator`.
- Với Reactor, bật `spring.reactor.context-propagation=auto` nếu cần restore ThreadLocal trong reactive operators.

Ví dụ custom executor:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
class AsyncConfiguration {

    @Bean("applicationTaskExecutor")
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(8);
        executor.setMaxPoolSize(32);
        executor.setQueueCapacity(500);
        executor.setThreadNamePrefix("orders-worker-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

Nếu context bị mất, kiểm tra executor thực tế mà @Async sử dụng, task decorator, custom CompletableFuture executor, Reactor chain và agent instrumentation. Không tự copy trace ID vào static ThreadLocal vì có thể rò context giữa requests.

## 19. Context propagation trong Reactor/WebFlux

Reactive execution có thể chuyển giữa nhiều threads. ThreadLocal không phải nguồn context đáng tin cậy trong mọi operator.

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Khi bật automatic propagation, Spring Context Propagation hỗ trợ chuyển observation context giữa Reactor Context và ThreadLocal theo lifecycle được quản lý. Nếu custom Reactor operators, dùng Context/Observation APIs và test nhiều requests đồng thời để phát hiện context leakage.

## 20. Log correlation bằng traceId và spanId

Spring Boot với Micrometer Tracing đưa `traceId` và `spanId` vào MDC trong scope đang hoạt động. Log pattern có thể hiển thị correlation ID:

~~~yaml
logging:
  pattern:
    correlation: "[orders-api,%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
~~~

Ví dụ log:

~~~text
[orders-api,4efaaf4d1e8720b39541901950019ee5,00f067aa0ba902b7] INFO PaymentService - authorization started
~~~

MDC chỉ là context cho logging trong process. Để trace đi qua network, cần propagation headers/message metadata riêng.

## 21. Baggage: truyền metadata xuyên service

Baggage là metadata key/value gắn với trace context và có thể được truyền tới downstream services.

~~~http
baggage: workflow=checkout,tenant-tier=gold
~~~

Micrometer Tracing có thể tạo baggage:

~~~java
import io.micrometer.tracing.BaggageInScope;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Component;

@Component
class WorkflowContext {

    private final Tracer tracer;

    WorkflowContext(Tracer tracer) {
        this.tracer = tracer;
    }

    void execute() {
        try (BaggageInScope ignored =
                 tracer.createBaggageInScope("workflow", "checkout")) {
            performWork();
        }
    }

    private void performWork() {
        // Work performed while baggage is in scope.
    }
}
~~~

Baggage được truyền tự động khi propagation format hỗ trợ. W3C biểu diễn baggage qua header `baggage`. Không đưa password, access token, email, địa chỉ hoặc dữ liệu cá nhân vào baggage. Chỉ cho phép keys/values có kiểm soát và giới hạn kích thước.

## 22. Instrument AWS SDK for Java 2.x

AWS SDK calls thường là một phần quan trọng của trace: S3 Get/PutObject, SQS Send/Receive, DynamoDB Get/Put, STS AssumeRole và SNS Publish.

ADOT/OpenTelemetry Java agent có thể tự động instrument AWS SDK v2 clients được hỗ trợ. Nếu không dùng agent, có thể dùng OpenTelemetry AWS SDK v2 instrumentation library.

Ví dụ instrument DynamoDB client cụ thể:

~~~java
import io.opentelemetry.instrumentation.awssdk.v2_2.AwsSdkTelemetry;
import software.amazon.awssdk.core.client.config.ClientOverrideConfiguration;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

AwsSdkTelemetry telemetry =
    AwsSdkTelemetry.create(openTelemetry).build();

DynamoDbClient dynamoDb = DynamoDbClient.builder()
    .overrideConfiguration(
        ClientOverrideConfiguration.builder()
            .addExecutionInterceptor(
                telemetry.createExecutionInterceptor())
            .build())
    .build();
~~~

Với SQS, instrumentation có thể cần wrapper bổ sung cho synchronous/async clients theo tài liệu instrumentation:

~~~java
SqsClient sqs = telemetry.instrument(
    SqsClient.builder().build()
);

SqsAsyncClient sqsAsync = telemetry.instrument(
    SqsAsyncClient.builder().build()
);
~~~

Nếu dùng Spring Cloud AWS auto-configured clients, không tạo client thứ hai chỉ để gắn interceptor. Dùng agent hoặc customizer/bean configuration để instrumentation áp dụng vào đúng client Spring inject.

## 23. SQS/SNS: propagation theo message

Khi gửi SQS message, cần liên kết consumer processing với producer operation. HTTP request tới SQS và message delivery là hai ranh giới khác nhau.

Kiểm tra:
- Producer instrumentation inject context vào message system attributes/message attributes;
- Consumer instrumentation extract đúng carrier;
- SendMessageBatch có context riêng cho từng entry;
- SNS-to-SQS subscription giữ metadata theo flow;
- DLQ/redrive giữ event ID và metadata cần thiết;
- Batch listener dùng span links khi xử lý nhiều messages từ nhiều traces.

Với AWS SDK v2 OTel instrumentation, khi X-Ray propagation bật, SendMessageBatch có thể gắn context từng message vào `AWSTraceHeader` system attribute. Nếu custom integration chưa hỗ trợ, có thể truyền W3C traceparent/tracestate trong message attributes theo messaging instrumentation convention.

Dùng event ID riêng cho idempotency, trace context cho correlation và message group ID cho FIFO ordering. Không dùng trace ID làm deduplication ID.

## 24. Sampling: chọn traces nào được lưu?

| Sampling | Cách hoạt động | Dùng khi |
| --- | --- | --- |
| Always on | Giữ mọi trace | Local test, workload nhỏ |
| Always off | Bỏ mọi trace | Tắt tracing có chủ đích |
| Trace ID ratio | Chọn tỷ lệ dựa trên trace ID | Giảm volume/cost |
| Parent-based ratio | Child tuân theo parent; root chọn theo ratio | Distributed services |
| Tail sampling | Collector quyết định sau khi thấy trace | Giữ errors/slow traces theo policy |

Spring Boot Micrometer Tracing mặc định sample 10% requests. Ví dụ:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Parent-based sampling giúp downstream services không tự chọn tỷ lệ khác khiến trace bị đứt.

ADOT Java agent direct export tới CloudWatch có thể sample 100% nếu không cấu hình sampler. Ví dụ cấu hình 5%:

~~~bash
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.05
~~~

Tail sampling cần Collector nhận đủ spans của cùng trace. Khi chạy nhiều Collector replicas, cần routing theo trace ID để spans không bị chia.

## 25. Metrics với Micrometer

Spring Boot dùng Micrometer làm metrics API. Metric thường có ích gồm HTTP request/duration, JVM memory/GC/threads, DB connection pool, SQS queue age/listener errors và business counters.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

@Component
class OrderMetrics {

    private final Counter created;

    OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("orders.created")
            .description("Number of orders created")
            .tag("channel", "web")
            .register(registry);
    }

    void orderCreated() {
        created.increment();
    }
}
~~~

Chỉ dùng tags có tập giá trị hữu hạn như channel=web/mobile/partner. Không dùng orderId, userId, requestId, raw URL hoặc exception message làm metric labels.

### Metrics exemplars

Exemplar có thể gắn một metric sample với trace context đã được sample. Operator nhìn histogram/latency metric rồi mở trace liên quan để điều tra outlier. Backend phải hỗ trợ exemplars.

## 26. Export metrics OTLP từ Spring Boot

Ví dụ Micrometer OTLP registry gửi metrics tới Collector:

~~~yaml
management:
  otlp:
    metrics:
      export:
        url: http://otel-collector:4318/v1/metrics
        step: 30s
        enabled: true
~~~

Metric export theo chu kỳ, khác với trace span được export sau khi kết thúc. Chọn step theo nhu cầu quan sát và ingestion volume.

Nếu muốn Collector ký request bằng SigV4 tới CloudWatch, application chỉ gửi OTLP nội bộ tới Collector. Không cấu hình exporter không hỗ trợ SigV4 gửi trực tiếp tới AWS OTLP endpoint.

## 27. Logs: structured logging và trace correlation

Log records nên mang trace_id, span_id, service.name, deployment.environment, level, timestamp, logger và event/request ID đã được kiểm soát.

~~~json
{
  "timestamp": "2026-11-20T10:15:30.120Z",
  "level": "ERROR",
  "service": "orders-api",
  "trace_id": "4efaaf4d1e8720b39541901950019ee5",
  "span_id": "00f067aa0ba902b7",
  "message": "Payment authorization failed",
  "error.type": "TimeoutException"
}
~~~

Spring Boot Micrometer Tracing có thể đưa trace/span IDs vào MDC để logger pattern hiển thị correlation ID. Nếu muốn gửi LogRecord qua OpenTelemetry Logs API, cần logging bridge/appender hoặc ADOT agent log instrumentation tương ứng.

Không giả định Spring Boot tự động bridge mọi Logback/Log4j log event sang OpenTelemetry LoggerProvider. Tracing correlation trong MDC và export log records bằng OTLP là hai cấu hình khác nhau.

## 28. OTLP và Collector

OTLP là giao thức truyền traces, metrics và logs giữa SDK/agent, Collector và backend.

| Transport | Endpoint | Port |
| --- | --- | --- |
| OTLP/gRPC | http://otel-collector:4317 | 4317 |
| OTLP/HTTP protobuf | http://otel-collector:4318 | 4318 |
| Traces path | /v1/traces | HTTP |
| Metrics path | /v1/metrics | HTTP |
| Logs path | /v1/logs | HTTP |

Collector có thể chạy dạng sidecar trong ECS task, daemonset/deployment trong EKS hoặc agent trên EC2. Với CloudWatch, Collector xử lý SigV4, batch, retry và export tới từng OTLP endpoint.

## 29. Collector config: gửi cả ba tín hiệu tới CloudWatch OTLP

Ví dụ Collector nhận OTLP từ Java app và export metrics, logs, traces tới CloudWatch. Thay Region, log group và stream theo môi trường:

~~~yaml
extensions:
  sigv4auth/metrics:
    service: monitoring
    region: ap-southeast-1
  sigv4auth/logs:
    service: logs
    region: ap-southeast-1
  sigv4auth/traces:
    service: xray
    region: ap-southeast-1

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
      http:
        endpoint: 0.0.0.0:4318

processors:
  memory_limiter:
    check_interval: 1s
    limit_percentage: 80
    spike_limit_percentage: 20
  batch:
    send_batch_size: 200
    send_batch_max_size: 1000
    timeout: 10s

exporters:
  otlphttp/metrics:
    metrics_endpoint: https://monitoring.ap-southeast-1.amazonaws.com/v1/metrics
    compression: gzip
    auth:
      authenticator: sigv4auth/metrics

  otlphttp/logs:
    logs_endpoint: https://logs.ap-southeast-1.amazonaws.com/v1/logs
    compression: gzip
    headers:
      x-aws-log-group: /apps/orders
      x-aws-log-stream: default
    auth:
      authenticator: sigv4auth/logs

  otlphttp/traces:
    traces_endpoint: https://xray.ap-southeast-1.amazonaws.com/v1/traces
    compression: gzip
    auth:
      authenticator: sigv4auth/traces

service:
  extensions: [sigv4auth/metrics, sigv4auth/logs, sigv4auth/traces]
  pipelines:
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp/metrics]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp/logs]
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [otlphttp/traces]
~~~

Trước khi chạy:
- Tạo CloudWatch Log Group `/apps/orders` và Log Stream `default`;
- Gán IAM role cho Collector để ký SigV4;
- Bật CloudWatch Transaction Search nếu dùng X-Ray OTLP endpoint;
- Mở network path tới CloudWatch endpoints;
- Pin Collector image/version trong production, không dùng latest;
- Bảo vệ receiver 4317/4318 bằng private network, Security Group hoặc inbound auth nếu cần.

CloudWatch OTLP endpoints chỉ hỗ trợ HTTP, không hỗ trợ gRPC ở phía AWS endpoint. Collector có thể nhận gRPC từ application rồi export bằng OTLP/HTTP.
## 30. ADOT Java agent: tự động instrument Spring Boot

ADOT Java agent là zero-code instrumentation. Agent instrument libraries/frameworks được hỗ trợ bằng bytecode instrumentation lúc JVM startup.

~~~bash
OTEL_RESOURCE_ATTRIBUTES=service.name=orders-api,service.namespace=commerce,deployment.environment=staging \
java -javaagent:/opt/aws-opentelemetry-agent.jar -jar orders-api.jar
~~~

Với Docker:

~~~dockerfile
COPY aws-opentelemetry-agent.jar /opt/aws-opentelemetry-agent.jar
ENV JAVA_TOOL_OPTIONS="-javaagent:/opt/aws-opentelemetry-agent.jar"
~~~

Pin agent version, kiểm tra release notes và supported libraries. Agent không tự instrument mọi thư viện có mặt trong classpath.

ADOT Java agent mặc định dùng OTLP exporter và thường gửi đến Collector/CloudWatch Agent ở localhost port 4317. Có thể thay bằng `OTEL_EXPORTER_OTLP_*` environment variables.

## 31. ADOT direct export tới CloudWatch: traces và logs

ADOT Java agent từ version 2.11.2 trở lên hỗ trợ gửi traces và logs trực tiếp tới CloudWatch OTLP endpoints mà không cần Collector riêng. Ví dụ:

~~~bash
export JAVA_TOOL_OPTIONS="-javaagent:/opt/aws-opentelemetry-agent.jar"

export OTEL_RESOURCE_ATTRIBUTES="service.name=orders-api,deployment.environment=prod"
export OTEL_TRACES_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://xray.ap-southeast-1.amazonaws.com/v1/traces

export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_LOGS_PROTOCOL=http/protobuf
export OTEL_EXPORTER_OTLP_LOGS_ENDPOINT=https://logs.ap-southeast-1.amazonaws.com/v1/logs
export OTEL_EXPORTER_OTLP_LOGS_HEADERS=x-aws-log-group=/apps/orders,x-aws-log-stream=default
~~~

Log Group và Log Stream phải tồn tại trước khi export. ADOT sử dụng AWS credentials provider để xác thực; trên ECS/EC2/EKS, ưu tiên IAM task/instance/pod role.

Nếu cần metric/log correlation trong CloudWatch, có thể thêm `aws.log.group.names=/apps/orders` vào `OTEL_RESOURCE_ATTRIBUTES`. Để trace/log correlation hoạt động, logger của ứng dụng cũng cần ghi trace ID/span ID theo hướng dẫn CloudWatch.

Theo hướng dẫn ADOT Java agent hiện hành, traces và logs có thể export trực tiếp, còn metrics cần CloudWatch Agent hoặc Collector. Nếu chỉ muốn traces/logs từ agent, đặt `OTEL_METRICS_EXPORTER=none`; metrics Spring Boot có thể gửi bằng Micrometer OTLP registry tới Collector.

Direct export traces có thể mặc định sample 100%. Cấu hình ratio sampler phù hợp production và kiểm soát chi phí.

## 32. CloudWatch Application Signals và X-Ray

CloudWatch Application Signals cung cấp góc nhìn application-centric về service health, dependencies và SLOs. ADOT Java auto-instrumentation có thể tạo telemetry để Application Signals quan sát HTTP services và downstream dependencies.

| Thành phần | Vai trò |
| --- | --- |
| ADOT Java agent | Instrument Java application |
| CloudWatch Agent / ADOT Collector | Nhận, xử lý và export telemetry |
| CloudWatch Application Signals | Health, dependency map, SLO-oriented view |
| X-Ray / Trace Search | Tìm kiếm và xem distributed traces |
| CloudWatch Metrics | Metrics và alarms |
| CloudWatch Logs | Log records và query |

Không nhầm bật Application Signals với việc mọi telemetry tự động xuất hiện mà không cần IAM/network/agent config. Kiểm tra agent injection, role permissions, resource attributes và Transaction Search setup.

## 33. IAM permissions, network và endpoint

Collector/agent cần identity có quyền ghi telemetry:

| Signal | Quyền tiêu biểu |
| --- | --- |
| Traces | `xray:PutTraceSegments`, `xray:PutTelemetryRecords` hoặc policy `AWSXrayWriteOnlyPolicy` |
| Metrics | `cloudwatch:PutMetricData` |
| Logs | `logs:PutLogEvents`, `logs:DescribeLogGroups`, `logs:DescribeLogStreams` |

Dùng policy tối thiểu theo Region/resource và kiểm tra managed policy version trước khi attach. Không cấp AdministratorAccess chỉ để làm telemetry export hoạt động.

Network cần:
- Application → Collector: 4317/4318 trong private network;
- Collector → X-Ray OTLP endpoint: HTTPS 443;
- Collector → CloudWatch metrics endpoint: HTTPS 443;
- Collector → CloudWatch Logs endpoint: HTTPS 443;
- Private subnet: NAT hoặc VPC endpoints phù hợp;
- Kiểm tra DNS, TLS certificate, proxy, Security Groups, NACL và endpoint policies.

CloudWatch OTLP endpoints dùng SigV4 với short-term credentials là phương án khuyến nghị cho workload trên AWS. Bearer token/API key là phương án riêng cho môi trường ngoài AWS và phải được quản lý/rotate như secret.

## 34. Sampling, cardinality, performance và chi phí

Telemetry có chi phí ingestion, storage, query và network. Thiết kế không kiểm soát có thể tăng chi phí hoặc ảnh hưởng latency ứng dụng.

### Kiểm soát trace volume
- Dùng parent-based sampling;
- Sample 100% trong local/test khi cần;
- Chọn ratio phù hợp traffic production;
- Dùng tail sampling nếu cần giữ lỗi/slow traces;
- Tránh tạo spans quá chi tiết;
- Dùng batch exporter và Collector;
- Theo dõi dropped spans, queue size và export failures.

### Kiểm soát metric cardinality

Tránh metric labels như user.id, order.id, request.id, raw URL path chứa ID, exception message hoặc SQL query đầy đủ. Dùng route template `/orders/{id}`, status class và operation name đã chuẩn hóa.

### Kiểm soát payload/logs

Không ghi request/response body nhạy cảm, access tokens, authorization headers, password, SQS payload đầy đủ hoặc presigned URL vào spans/logs. Dùng allowlist attributes và giới hạn kích thước spans.

## 35. Kiểm thử trace propagation và telemetry export

Gửi một `traceparent` hợp lệ vào API:

~~~bash
curl -H "traceparent: 00-4efaaf4d1e8720b39541901950019ee5-00f067aa0ba902b7-01" \
  http://localhost:8080/orders
~~~

Nếu API và downstream client được instrument đúng, trace phải giữ cùng trace ID và tạo span IDs mới cho từng operation.

### Test các trường hợp
- HTTP server span được tạo;
- Outbound RestClient/WebClient gửi trace context;
- Custom executor giữ context;
- Reactor pipeline giữ context;
- AWS SDK S3/SQS call có spans;
- SQS consumer liên kết message với producer;
- Logs chứa traceId/spanId;
- Metrics có tên/tags/cardinality phù hợp;
- Collector nhận OTLP và export thành công;
- CloudWatch/X-Ray hiển thị service/resource attributes.

Dùng in-memory exporter hoặc test exporter cho manual OTel SDK; mock HTTP server để xác minh headers; Collector debug exporter trong local để xem telemetry. LocalStack không thay thế mọi test propagation/instrumentation trên AWS thật.

## 36. Troubleshooting: trace bị mất hoặc telemetry không xuất hiện

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Mỗi service có trace ID khác | Inbound context không extract hoặc outbound context không inject | Kiểm tra traceparent, propagation format, HTTP client builder |
| Có server span nhưng thiếu client span | Tạo client thủ công, thiếu instrumentation | Dùng auto-configured builder hoặc agent/library |
| Context mất trong @Async | Executor không propagate context | Bật context propagation/task decorator |
| Trace mất trong Reactor | ThreadLocal không restore vào reactive pipeline | Bật spring.reactor.context-propagation=auto |
| Log không có traceId/spanId | MDC integration/logger pattern chưa đúng | Kiểm tra Micrometer Tracing và MDC |
| Span xuất hiện hai lần | Spring Boot và Java agent cùng instrument | Tắt một instrumentation path |
| SQS consumer không nối producer | Message carrier không inject/extract hoặc version chưa hỗ trợ | Kiểm tra AWSTraceHeader/message attributes |
| Trace không xuất hiện ở X-Ray | Transaction Search chưa bật, sai endpoint/Region | Kiểm tra CloudWatch setup và Collector logs |
| OTLP trả 404 | Sai path hoặc nhầm HTTP/gRPC | Kiểm tra /v1/traces, /v1/metrics, /v1/logs |
| OTLP trả 403 | SigV4 service/Region sai hoặc IAM thiếu quyền | Kiểm tra sigv4auth và Collector role |
| Logs bị reject | Log Group/Stream chưa tồn tại hoặc thiếu headers | Tạo group/stream và set x-aws-log-group/x-aws-log-stream |
| Metrics bị throttle | Quá nhiều series/TPS/batch lớn | Giảm cardinality, batch size, step |
| Trace thiếu service name | Thiếu service.name resource attribute | Set OTEL_SERVICE_NAME/OTEL_RESOURCE_ATTRIBUTES |
| Spans bị drop | Export queue đầy, timeout hoặc throttling | Kiểm tra Collector queue, retry và memory limiter |
| Trace duration bất thường | Đồng hồ host/container lệch | Đồng bộ NTP |
| Agent làm app startup lỗi | Agent/library version conflict | Kiểm tra logs, pin version và disable instrumentation lỗi |
| Logs có trace ID sai giữa requests | MDC/context không restore đúng | Kiểm tra thread reuse và custom ThreadLocal |

### Quy trình điều tra

~~~text
1. Xác định instrumentation strategy: Spring Boot, ADOT agent hay manual SDK.
2. Kiểm tra service.name, environment, Region và agent/dependency versions.
3. Xác minh inbound trace context được extract.
4. Kiểm tra HTTP client, executor, Reactor và message propagation.
5. Xem spans trong Collector debug exporter.
6. Kiểm tra OTLP endpoint, protocol, path và network.
7. Kiểm tra SigV4, IAM role, Region và CloudWatch Transaction Search.
8. Kiểm tra exporter queue, batch, retry và dropped telemetry.
9. Kiểm tra sampling/cardinality/size limits.
10. Xác minh bằng request có traceparent cố định trong môi trường test.
~~~

Không bật debug logs có thể ghi Authorization headers, AWS credentials, secret payload hoặc dữ liệu khách hàng.

## 37. Bảo mật trace context, baggage và telemetry

Trace context là metadata tương quan, không phải proof of identity. Client bên ngoài có thể gửi header nếu ingress không lọc.

- Không dùng trace ID để xác thực hoặc cấp quyền;
- Không tin sampling flag từ client như security policy;
- Cân nhắc loại bỏ/khởi tạo lại context tại trust boundary không tin cậy;
- Allowlist baggage keys và giới hạn size;
- Không đưa secrets, PII, payment data hoặc raw user input vào attributes;
- Giới hạn CloudWatch Log Groups access;
- Không mở OTLP receiver công khai mà không có network/auth controls;
- Dùng TLS và IAM role short-term credentials;
- Đặt retention/access policy cho traces/logs phù hợp.

AWS X-Ray tracing header có thể xuất phát từ client request. Nếu không muốn client tự đặt trace root/sampling state, xử lý header tại edge theo policy và AWS guidance.

## 38. Migration từ AWS X-Ray SDK sang OpenTelemetry

AWS thông báo AWS X-Ray SDKs/Daemon vào maintenance mode từ **25/02/2026**, chỉ nhận release giới hạn để xử lý security issues. Với ứng dụng mới hoặc đang phát triển, nên đánh giá chuyển sang OpenTelemetry/ADOT.

| X-Ray SDK concept | OpenTelemetry |
| --- | --- |
| Segment | Server span |
| Subsegment | Client/internal span |
| Annotation | Span attribute được ánh xạ phù hợp sang searchable annotation |
| Metadata | Span attributes/structured events |
| X-Ray recorder | Tracer/TracerProvider |
| X-Ray SDK instrumentation | OTel instrumentation libraries/Java agent |
| X-Ray Daemon | ADOT Collector hoặc CloudWatch Agent |
| X-Ray sampling rules | OTel sampler/ADOT X-Ray remote sampling khi hỗ trợ |

### Lộ trình migration
1. Inventory X-Ray SDK modules, recorder config, plugins và interceptors.
2. Kiểm tra agent/OTel instrumentation coverage cho Spring, HTTP, JDBC và AWS SDK v2.
3. Chọn ADOT Java agent hoặc Micrometer/OTel SDK approach.
4. Cấu hình W3C/X-Ray propagation phù hợp upstream/downstream.
5. Thay segment/subsegment code bằng Observation hoặc spans.
6. Ánh xạ annotation/metadata sang span attributes có cardinality/privacy phù hợp.
7. Chuyển exporter/daemon sang ADOT Collector hoặc CloudWatch OTLP endpoints.
8. Test traces qua ALB/API Gateway, SQS/SNS, AWS SDK và worker.
9. Chạy song song có kiểm soát ở staging; tránh gửi duplicate spans vào production.
10. Rollout từng service và loại bỏ X-Ray SDK/Daemon khi không còn dependency.

## 39. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Trace bị chia giữa hai service

Orders API nhận W3C traceparent nhưng Inventory API tạo trace ID mới.

**Yêu cầu:** Kiểm tra inbound extraction, auto-configured RestClient/WebClient builder, propagation formats và việc tạo HTTP client thủ công. Vẽ parent-child spans.

### Bài tập 2 — Context mất khi chạy @Async

Log trong request thread có trace ID, log trong worker thread không có.

**Yêu cầu:** Giải thích ThreadLocal/context propagation; cấu hình ContextPropagatingTaskDecorator hoặc property phù hợp; test hai requests đồng thời để phát hiện context leakage.

### Bài tập 3 — SQS message không nối với producer

API gửi SQS message nhưng worker tạo trace mới hoàn toàn.

**Yêu cầu:** Phân biệt HTTP API header và message carrier; kiểm tra AWSTraceHeader, instrumentation AWS SDK v2 và consumer extraction. Giải thích khi nào dùng span link cho batch.

### Bài tập 4 — Chọn instrumentation strategy

Một Spring Boot service có MVC, JDBC, S3, SQS và custom thread pool. Team bật Micrometer Tracing và ADOT Java agent cùng lúc.

**Yêu cầu:** Xác định spans trùng, chọn Spring-first hoặc agent-first, mô tả cách instrument AWS SDK còn thiếu và xác minh trace không duplicate.

### Bài tập 5 — Sampling và chi phí

Một API có 10.000 requests/giây. ADOT direct export đang sample 100%.

**Yêu cầu:** Đề xuất parent-based ratio sampling, so sánh volume khi giảm xuống 5%, xác định traces nào nên giữ 100% (nếu có) và tránh đứt trace giữa services.

### Bài tập 6 — Export CloudWatch OTLP bị 403

Collector nhận traces/metrics/logs nhưng CloudWatch trả 403.

**Yêu cầu:** Kiểm tra SigV4 service name (xray, monitoring, logs), Region, IAM permissions, workload role và Transaction Search setup.

### Bài tập 7 — Cardinality

Metric orders.duration có labels orderId, customerId, requestId.

**Yêu cầu:** Giải thích time-series explosion; chuyển IDs sang trace attributes có kiểm soát và giữ metric labels low-cardinality.

### Bài tập 8 — Migration X-Ray SDK

Ứng dụng dùng X-Ray recorder và daemon; cần chuyển sang ADOT.

**Yêu cầu:** Mapping segment/subsegment/annotation/metadata sang spans/attributes; chọn agent/SDK, Collector và kế hoạch rollout.

### Câu hỏi ngắn

1. **Trace gồm gì?** Nhiều spans liên kết bằng trace context.
2. **Span ID khác trace ID thế nào?** Trace ID định danh toàn hành trình; Span ID định danh một operation.
3. **traceparent có mấy phần chính?** Version, trace ID, parent span ID và flags.
4. **tracestate dùng làm gì?** Vendor-specific trace state.
5. **Baggage có phải authorization token không?** Không.
6. **Correlation ID có thay trace context không?** Không.
7. **Spring Boot dùng API nào cho observations?** Micrometer Observation/ObservationRegistry.
8. **Micrometer Tracing bridge OTel có vai trò gì?** Chuyển Observation/Tracing API sang OpenTelemetry.
9. **ADOT Java agent làm gì?** Auto-instrument framework/libraries được hỗ trợ.
10. **Có nên bật hai auto-instrumentation duplicate không?** Không.
11. **Vì sao dùng RestClient.Builder auto-configured?** Để gắn observation/trace propagation cho outbound requests.
12. **Vì sao @Async có thể mất trace context?** Context không tự chuyển qua thread nếu executor không propagate.
13. **MDC có thay propagation header không?** Không.
14. **SQS cần truyền context ở đâu?** Message attributes/system attributes hoặc instrumentation hỗ trợ.
15. **AWSTraceHeader là gì?** SQS system attribute mang X-Ray trace context.
16. **Low-cardinality tags nên chứa gì?** Giá trị hữu hạn như operation, channel, region.
17. **High-cardinality attributes nên đặt ở đâu?** Trace khi cần, tránh metric labels.
18. **OTLP receiver thường dùng port nào?** 4317 gRPC và 4318 HTTP.
19. **CloudWatch OTLP endpoints hỗ trợ HTTP hay gRPC?** HTTP.
20. **Trace endpoint CloudWatch dùng SigV4 service nào?** xray.
21. **Metrics endpoint dùng service nào?** monitoring.
22. **Logs endpoint dùng service nào?** logs.
23. **Vì sao cần Transaction Search cho X-Ray OTLP traces?** Đây là prerequisite của CloudWatch trace ingestion path.
24. **ADOT direct export metrics có giống traces/logs không?** Không; Java agent direct path hiện hành cần Collector/CloudWatch Agent cho metrics.
25. **X-Ray SDK/Daemon vào maintenance mode khi nào?** 25/02/2026.

## 40. Checklist trước production

- [ ] Đã chọn instrumentation strategy: Spring Boot Micrometer, ADOT Java agent hoặc manual OTel.
- [ ] Không có duplicate server/client spans.
- [ ] service.name, namespace, version, environment và Region ổn định.
- [ ] Inbound W3C/B3/X-Ray context được extract theo policy.
- [ ] Outbound RestClient/WebClient dùng auto-configured builder hoặc instrumentation tương ứng.
- [ ] Context propagate qua @Async, custom executors và Reactor.
- [ ] SQS/SNS producer/consumer context được kiểm tra ở message carrier, batch và retry.
- [ ] AWS SDK v2 clients được instrument đúng version.
- [ ] Logs có traceId/spanId correlation và không chứa secrets/PII.
- [ ] Metrics labels có cardinality thấp; IDs chỉ nằm trong traces khi cần.
- [ ] Baggage keys được allowlist và giới hạn size.
- [ ] Sampling parent-based phù hợp; không vô tình export 100% production traces.
- [ ] OTLP exporter có batch, timeout, retry và queue limits.
- [ ] Collector có memory limiter, private receiver và health monitoring.
- [ ] CloudWatch Transaction Search bật nếu dùng X-Ray OTLP traces.
- [ ] CloudWatch Log Group/Stream tồn tại trước khi export logs.
- [ ] Collector role có IAM permissions tối thiểu.
- [ ] VPC endpoints, DNS, TLS, Region và network được kiểm tra.
- [ ] Agent/Collector versions được pin và theo dõi release notes.
- [ ] Test profile không export telemetry vào production account.
- [ ] Có dashboard/alert cho error rate, latency, queue age, exporter failures và dropped spans.
- [ ] Có runbook điều tra context loss, AccessDenied, 429 và exporter timeout.
- [ ] X-Ray SDK/Daemon migration plan được đánh giá theo maintenance mode.
- [ ] Chi phí ingestion, retention, query và cardinality được theo dõi.

## 41. Tổng kết

Distributed tracing cần **context propagation** để nhiều process/thread/message hiểu cùng một trace. W3C Trace Context là format phổ biến; AWS X-Ray sử dụng `X-Amzn-Trace-Id` và hỗ trợ interoperability với W3C khi exporter/Collector phù hợp.

Trong Spring Boot, Micrometer Observation/Tracing cung cấp API tạo observations, spans, metrics và log correlation. Dùng auto-configured HTTP builders; cấu hình Context Propagation cho executor/Reactor; instrument AWS SDK v2 và message queues để trace không đứt tại ranh giới AWS.

Telemetry gồm traces, metrics và logs. OTLP là giao thức truyền; ADOT Java agent tự động instrument Java; Collector/CloudWatch Agent xử lý batch, SigV4, retry và export tới CloudWatch/X-Ray. Sampling, cardinality, baggage, IAM, network và log hygiene quyết định độ tin cậy, chi phí và bảo mật.

Những điểm cần nhớ:

1. Trace ID định danh hành trình; span ID định danh operation; traceparent mang parent context qua HTTP.
2. Baggage là metadata propagation, không phải nơi chứa secret hoặc PII.
3. MDC nối log với trace trong process; không thay network/message propagation.
4. Dùng Spring Boot auto-configured builders và Context Propagation để giữ context qua HTTP, async và Reactor.
5. Dùng ADOT/OTel instrumentation cho AWS SDK v2 và kiểm tra message carrier của SQS/SNS.
6. Dùng Micrometer cho Spring metrics, OpenTelemetry/ADOT cho traces và Collector cho telemetry pipeline.
7. CloudWatch OTLP endpoints dùng SigV4, HTTP và đúng service/Region; bật Transaction Search khi gửi traces.
8. Kiểm soát sampling, cardinality, retention, baggage và exporter queue.
9. AWS X-Ray SDK/Daemon vào maintenance mode từ 25/02/2026; nên đánh giá lộ trình OpenTelemetry.

### Tài liệu chính thức

- [Spring Boot 3.5 — Tracing](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html)
- [Spring Boot 4.x — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability and Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — Metrics and OTLP](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [OpenTelemetry Java instrumentation ecosystem](https://opentelemetry.io/docs/languages/java/instrumentation/)
- [OpenTelemetry Java agent](https://github.com/open-telemetry/opentelemetry-java-instrumentation)
- [OpenTelemetry AWS SDK v2 instrumentation](https://github.com/open-telemetry/opentelemetry-java-instrumentation/tree/main/instrumentation/aws-sdk/aws-sdk-2.2)
- [ADOT Java auto-instrumentation](https://aws-otel.github.io/docs/getting-started/java-sdk/auto-instr/)
- [ADOT Java manual instrumentation](https://aws-otel.github.io/docs/getting-started/java-sdk/manual-instr/)
- [ADOT Collector — Getting started](https://aws-otel.github.io/docs/getting-started/collector/)
- [AWS X-Ray concepts and trace headers](https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html)
- [AWS X-Ray — Migrating to OpenTelemetry Java](https://docs.aws.amazon.com/xray/latest/devguide/xray-migration-opentelemetry.html)
- [AWS X-Ray SDK and Daemon Support timeline](https://docs.aws.amazon.com/xray/latest/devguide/xray-sdk-daemon-timeline.html)
- [CloudWatch OTLP endpoints](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLPEndpoint.html)
- [CloudWatch — Export telemetry directly with ADOT](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-OTLP-UsingADOT.html)
- [CloudWatch — Send metrics, logs and traces with Collector](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/GettingSetup.html)
- [CloudWatch Application Signals](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Signals.html)

**Lưu ý:** Spring Boot 3.5 và 4.x có property/dependency khác nhau; AWS SDK/ADOT/Collector instrumentation phát hành độc lập. Hãy pin phiên bản đã kiểm thử, đối chiếu support matrix, test trace propagation qua mọi boundary và xác minh Collector export trong non-production account trước khi rollout.

# OpenTelemetry Tracer Provider trong Spring Boot

Trong chương **Tracer implementation** của module **SPRING_BOOT_OBSERVABILITY**, câu hỏi quan trọng không chỉ là “làm thế nào tạo một span?” mà còn là **ai cấp Tracer, ai quyết định sampling, ai xử lý span và ai gửi dữ liệu tới tracing backend?** Với OpenTelemetry, các trách nhiệm này được tổ chức quanh **TracerProvider**. Hiểu đúng cơ chế giúp cấu hình Micrometer Observation, metrics, logs và distributed tracing trong Spring Boot nhất quán, tránh tạo nhiều tracer độc lập hoặc tưởng rằng tạo span là đã xuất được trace.

Bài này giải thích **OpenTelemetry TracerProvider** (đặc biệt là `SdkTracerProvider`), mối quan hệ với `Tracer` và `OpenTelemetrySdk`, cách cấu hình trong Spring Boot qua **Micrometer Tracing bridge**, cách viết ví dụ SDK thủ công khi thật sự cần, cùng các lưu ý về context propagation, sampler, exporter, cardinality và liên kết metrics–logs–traces.

## 1. Vì sao cần TracerProvider?

Trong một hệ thống đặt hàng, cùng một request có thể tạo HTTP server span, span nghiệp vụ `order.confirm`, HTTP client span tới payment service và database span. Nếu mỗi thư viện tự tạo một bộ tracing riêng, các span có thể không cùng Trace ID, không dùng cùng resource metadata hoặc đi tới những exporter khác nhau. Một **TracerProvider được cấu hình nhất quán** cung cấp các tracer dùng chung hạ tầng và chính sách tracing trong một tiến trình.

```text
Spring Boot service
    |
    +-- HTTP instrumentation ---------+
    +-- Micrometer Observation -------+----> OpenTelemetry Tracer
    +-- Custom instrumentation -------+             |
                                                   v
                                           TracerProvider
                                                   |
                                        (SdkTracerProvider)
                                      /         |          \
                               Resource      Sampler     SpanProcessor
                                                           |
                                                    SpanExporter
                                                           |
                                                    OTLP / Collector
                                                           |
                                                   Tracing backend

W3C propagators: truyền trace context qua ranh giới HTTP/message
Metrics handlers và log correlation: các đường tín hiệu có cấu hình riêng
```

**Điểm phân biệt:** `TracerProvider` không phải một tracing backend và không phải kho lưu trữ lịch sử. Nó cung cấp `Tracer`; SDK implementation quản lý sampling, xử lý span và exporter. Dữ liệu chỉ xem được trong backend khi các bước tạo span, lấy mẫu, export và ingest đều hoạt động.

## 2. Các đối tượng chính và trách nhiệm

| Đối tượng | Vai trò | Lỗi nhận thức thường gặp |
| --- | --- | --- |
| `TracerProvider` | API cung cấp các `Tracer` theo instrumentation scope | Tưởng nó là collector hoặc backend |
| `Tracer` | API khởi tạo spans cho một thư viện/thành phần | Tạo một tracer mới là tạo một trace độc lập |
| `SdkTracerProvider` | SDK implementation quản lý tracer, resource, sampler, span processors | Tự tạo nhiều instance SDK trong cùng app mà không kiểm soát |
| `SpanBuilder` / `Span` | Tạo một thao tác, gắn attributes/events/status và quản lý vòng đời | Quên đóng span hoặc scope |
| `Resource` | Metadata về nguồn sinh telemetry: service name, môi trường, instance... | Gắn request ID/user ID vào resource |
| `Sampler` | Quyết định sampling tại thời điểm tạo span theo context/policy | Đồng nhất sampling với xóa metric hoặc lỗi exporter |
| `SpanProcessor` | Nhận lifecycle events của các recording spans, chuẩn bị xuất | Nhầm processor với propagator |
| `SpanExporter` | Gửi span data ra ngoài (ví dụ OTLP) | Nghĩ exporter tự instrument HTTP/JDBC |
| `ContextPropagators` | Định nghĩa cách inject/extract context qua transport | Tưởng đặt exporter là Trace ID tự đi qua service |
| `OpenTelemetrySdk` | Tập hợp SDK providers và propagators để instrumentation dùng | Nghĩ đây chỉ là alias của `SdkTracerProvider` |

Một `Tracer` thường được lấy từ provider bằng **instrumentation scope name** như `orders-business`, có thể kèm phiên bản. Tên scope cho biết thư viện/thành phần nào sinh telemetry; **không phải service name**, cũng không phải Trace ID. Service name nằm trong `Resource` và nên ổn định theo dịch vụ.

### API khác SDK implementation

OpenTelemetry chia **API** và **SDK**:

- **API** cho phép ứng dụng/thư viện dùng `Tracer` và truyền context mà không bắt buộc chọn exporter cụ thể.
- **SDK** thực thi sampling, span processing, resource và export. `SdkTracerProvider` là implementation của API `TracerProvider`.
- Trong môi trường không cài SDK/tracing bridge phù hợp, API có thể hoạt động theo dạng **no-op/non-recording**, không xuất dữ liệu. Không thể kết luận tracing hoạt động chỉ vì code biên dịch và gọi `spanBuilder()` thành công.

Các ví dụ trong bài mô tả một đường triển khai phổ biến. Tên dependency và thuộc tính auto-configuration có thể khác theo phiên bản Spring Boot/Micrometer/OpenTelemetry đang chạy; cần kiểm tra thực tế.

## 3. Vòng đời một span qua TracerProvider

Giả sử code tạo span cho thao tác `inventory.reserve`:

1. Instrumentation lấy `Tracer` từ provider.
2. `Tracer.spanBuilder("inventory.reserve")` tạo builder.
3. Khi `startSpan()` được gọi, provider tạo span context, sử dụng parent context hiện hành và **Sampler** để quyết định có record/export hay không.
4. Nếu span đang ghi nhận, code có thể thêm attributes, events, exception và status.
5. Scope làm span trở thành **current span** cho các lời gọi đồng bộ ở execution context phù hợp.
6. `span.end()` kết thúc thao tác; processor xử lý span đã hoàn tất và exporter có thể gửi dữ liệu đi.

```text
TracerProvider
   |
   +--> Tracer
         |
         +--> SpanBuilder
                |
                +--> startSpan() -- Sampler decision
                       |
                       +--> makeCurrent() / Scope
                       |        |
                       |        +--> calls bên trong dùng parent context
                       |
                       +--> add attributes / recordException
                       |
                       +--> end()
                              |
                              +--> SpanProcessor
                                       |
                                       +--> Exporter --> Collector/backend
```

**Scope và span khác nhau:** đóng `Scope` khôi phục context đang hoạt động trước đó; `span.end()` kết thúc span. Đóng scope **không tự kết thúc** span, và kết thúc span **không phải thao tác khôi phục** context. Phải quản lý cả hai đúng thứ tự.

Một span có thể giữ Trace ID hợp lệ trong context nhưng **không recording** do sampling; vì thế không phải mọi lệnh tạo span đều dẫn tới một bản ghi trên backend.

## 4. Spring Boot và Micrometer Tracing tích hợp thế nào?

Trong phần lớn ứng dụng Spring Boot sử dụng Actuator và **Micrometer Observation**, ưu tiên để **Spring Boot auto-configuration quản lý** tracing infrastructure. Mã nghiệp vụ tạo observation qua `ObservationRegistry` hoặc đọc current span qua `io.micrometer.tracing.Tracer`; bridge OpenTelemetry chuyển các sự kiện observation/tracing sang OpenTelemetry phù hợp.

```text
Spring Boot instrumentation / custom Observation
                  |
                  v
        Micrometer ObservationRegistry
                  |
                  v
      ObservationHandler / Micrometer Tracing
                  |
                  v
        micrometer-tracing-bridge-otel
                  |
                  v
            OpenTelemetry SDK
        (SdkTracerProvider / propagators)
                  |
                  +--> OTLP exporter --> collector/backend
                  |
                  +--> trace context --> HTTP/message downstream
```

**Không nhầm API:** `io.micrometer.tracing.Tracer` là abstraction của Micrometer Tracing; `io.opentelemetry.api.trace.Tracer` là API OpenTelemetry. Cả hai đều có thể tham gia cùng pipeline khi bridge được thiết lập, nhưng cách dùng khác nhau. Tránh import nhầm rồi coi hai kiểu là hoán đổi trực tiếp.

### Ví dụ dependency

Một tổ hợp tham khảo cho các phiên bản Spring Boot có hỗ trợ **Micrometer Tracing + OpenTelemetry bridge + OTLP exporter**:

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

Ví dụ giả định dùng Spring Boot parent/BOM để quản lý phiên bản tương thích. Với các thế hệ Spring Boot có starter và cấu hình tracing mới, phải đối chiếu dependency thực tế; không ghép tùy ý hai bridge khác nhau hoặc tạo nhiều SDK chỉ để “chắc chắn có trace”.

### Ví dụ cấu hình ứng dụng

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 0.1
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
```

Trong stack Spring Boot hỗ trợ các thuộc tính trên, cấu hình này yêu cầu sampling xác suất khoảng 10% ở đầu luồng theo chính sách tracer và endpoint OTLP/HTTP của collector. Đây là **ví dụ**, không phải mức sampling tối ưu hay bảo đảm số trace thực tế đúng 10%.

- `spring.application.name` thường là nguồn đặt service name trong các cấu hình auto-config, nhưng phải **xác minh resource attributes thực tế** ở tracing backend.
- `management.otlp.tracing.endpoint` chỉ có ý nghĩa khi dependency, exporter, protocol và auto-configuration tương ứng đang hoạt động.
- Cổng 4318 và `/v1/traces` thường dùng cho OTLP/HTTP; cấu hình OTLP/gRPC thường dùng endpoint/protocol khác.
- Trong container, `localhost` chỉ tới network namespace đang chạy, không tự động tới collector ở container/pod khác.
- Việc nhận span còn phụ thuộc pipeline collector/backend, bảo mật mạng, retention và sampling.

**Khuyến nghị thiết kế:** nếu để Spring Boot quản lý SDK/provider, **không đồng thời tự gọi** `OpenTelemetrySdk.builder()`, `GlobalOpenTelemetry.set(...)` hoặc dựng một `SdkTracerProvider` thứ hai để gắn vào cùng các HTTP/Observation handlers. Việc này dễ tạo resource, sampler, propagator và exporter không nhất quán.

## 5. Ví dụ custom Observation trong Spring Boot

Một bước nghiệp vụ `order.confirm` nên được instrument với Micrometer Observation để kết hợp metrics và tracing (khi handlers tương ứng được cấu hình):

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderConfirmationService {
    private final ObservationRegistry registry;
    private final OrderGateway gateway;

    public OrderConfirmationService(
            ObservationRegistry registry,
            OrderGateway gateway) {
        this.registry = registry;
        this.gateway = gateway;
    }

    public void confirm(OrderCommand command) {
        Observation.createNotStarted("order.confirm", registry)
                .lowCardinalityKeyValue("channel", command.channel())
                .observe(() -> gateway.confirm(command));
    }
}
```

`OrderGateway` và `OrderCommand` là các kiểu domain do ứng dụng định nghĩa, không thuộc Micrometer. `channel` cần được chuẩn hóa theo tập giá trị hữu hạn như `web/pos/partner` trước khi dùng làm low-cardinality tag; không lấy trực tiếp một header do client cung cấp.

Khi ObservationRegistry có tracing handler thông qua Micrometer Tracing và OpenTelemetry bridge, observation này **có thể sinh span nghiệp vụ** dưới HTTP server span hiện hành. Khi metric handler có mặt, nó cũng có thể sinh thời lượng/số lần thao tác. Nếu chỉ có registry rỗng và không có handlers, code vẫn chạy nhưng không tự tạo dữ liệu tracing/backend.

Ở tầng domain, không cần biết `SdkTracerProvider` đã dựng bằng constructor nào. Tầng cấu hình sở hữu provider, resource, sampler và exporter; domain code sở hữu **ranh giới và ngữ nghĩa** observation.

## 6. Dựng SdkTracerProvider thủ công khi thật sự cần

Có trường hợp ứng dụng độc lập, công cụ kiểm thử hoặc thư viện bootstrap **chủ động sở hữu** toàn bộ OpenTelemetry SDK, không dựa vào Spring Boot auto-configuration. Khi đó có thể dựng provider thủ công. Đoạn sau minh họa luồng **độc lập**, không đặt nguyên xi cạnh cấu hình Spring Boot ở mục 4.

Để biên dịch cần các module OpenTelemetry API/SDK, OTLP exporter tương thích cùng phiên bản; các dependency sẽ do BOM của stack quản lý. Đường class/import có thể thay đổi theo phiên bản.

```java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.api.common.AttributeKey;
import io.opentelemetry.api.common.Attributes;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.ContextPropagators;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.api.baggage.propagation.W3CBaggagePropagator;
import io.opentelemetry.context.propagation.TextMapPropagator;
import io.opentelemetry.exporter.otlp.http.trace.OtlpHttpSpanExporter;
import io.opentelemetry.sdk.OpenTelemetrySdk;
import io.opentelemetry.sdk.resources.Resource;
import io.opentelemetry.sdk.trace.SdkTracerProvider;
import io.opentelemetry.sdk.trace.samplers.Sampler;
import io.opentelemetry.sdk.trace.export.BatchSpanProcessor;
import java.util.concurrent.TimeUnit;

public final class StandaloneTracingExample {
    public static void main(String[] args) {
        var exporter = OtlpHttpSpanExporter.builder()
                .setEndpoint("http://localhost:4318/v1/traces")
                .build();

        var serviceResource = Resource.getDefault().merge(
                Resource.create(Attributes.of(
                        AttributeKey.stringKey("service.name"),
                        "standalone-orders")));

        SdkTracerProvider provider = SdkTracerProvider.builder()
                .setResource(serviceResource)
                .setSampler(Sampler.parentBased(
                        Sampler.traceIdRatioBased(0.1)))
                .addSpanProcessor(
                        BatchSpanProcessor.builder(exporter).build())
                .build();

        OpenTelemetry otel = OpenTelemetrySdk.builder()
                .setTracerProvider(provider)
                .setPropagators(ContextPropagators.create(
                        TextMapPropagator.composite(
                                W3CTraceContextPropagator.getInstance(),
                                W3CBaggagePropagator.getInstance())))
                .build();

        try {
            Tracer tracer = otel.getTracer("orders-instrumentation", "1.0");
            Span span = tracer.spanBuilder("inventory.reserve").startSpan();
            try (Scope ignored = span.makeCurrent()) {
                // Thực hiện công việc cần đo ở đây.
                span.setAttribute("inventory.operation", "reserve");
            } catch (RuntimeException ex) {
                span.recordException(ex);
                span.setStatus(StatusCode.ERROR, "reserve failed");
                throw ex;
            } finally {
                span.end();
            }
        } finally {
            // Khi ứng dụng do chính mình sở hữu SDK kết thúc:
            provider.shutdown().join(10, TimeUnit.SECONDS);
        }
    }
}
```

### Phân tích các quyết định trong ví dụ

**Resource:** `service.name=standalone-orders` mô tả dịch vụ **sinh ra** span. `Resource.getDefault()` giữ các attributes mặc định khi ghép thêm service name. Không đưa `orderId`, Trace ID hoặc user ID vào resource: resource dùng chung cho nhiều spans và cần ổn định.

**Sampler:** `Sampler.parentBased(Sampler.traceIdRatioBased(0.1))` vừa xem xét quyết định parent đã có, vừa dùng tỷ lệ sampling cho trace khởi tạo mới theo nhánh tương ứng. Cơ chế sampling chính xác ở backend còn phụ thuộc sampled flag, remote parent và các sampler/collector khác.

**SpanProcessor:** `BatchSpanProcessor` gom và gửi span theo lô để giảm overhead trên đường request. Nó có queue, lịch flush và cơ chế xử lý khi nghẽn; **không bảo đảm** mọi span đều được xuất khi process crash hoặc collector lỗi. `SimpleSpanProcessor` thường dễ dùng khi kiểm thử nhỏ nhưng đồng bộ hóa công việc export theo mỗi span có thể gây overhead lớn nếu dùng bừa trong production.

**Exporter:** `OtlpHttpSpanExporter` gửi dữ liệu tới receiver OTLP/HTTP. Nếu endpoint không tồn tại hoặc không thể kết nối, span có thể được tạo nhưng không thấy ở backend. Đây là **lỗi đường xuất**, không chứng minh Trace ID hay SpanBuilder sai.

**Propagators:** `W3CTraceContextPropagator` và `W3CBaggagePropagator` xác định định dạng đưa context vào/ra transport. Chúng **không tự gửi HTTP headers**; HTTP client/server instrumentation cần gọi inject/extract vào request/message thực tế.

**Lifecycle:** giữ provider sống cùng vòng đời ứng dụng; shutdown khi tiến trình được đóng có kiểm soát để giải phóng processor/exporter và cố gắng flush. Trong Spring Boot, nên để Spring quản lý lifecycle thay vì tự gọi shutdown cho bean provider mà framework còn dùng.

**Phạm vi ví dụ:** code tạo một span để minh họa. Trong thực tế, phần công việc nằm bên trong scope có thể ném exception; cần ghi exception/status phù hợp, xử lý lỗi theo business contract và luôn đóng scope/span. Không kết luận tracer hoạt động chỉ bằng việc thấy một Trace ID trong log.

## 7. Resource, service.name và instrumentation scope

Trong một tracing backend, các spans được nhóm theo dịch vụ và nguồn instrumentation. Nếu cấu hình resource sai, rất khó tìm trace theo service mặc dù spans đã đến backend.

| Metadata | Cấp độ | Ví dụ | Chính sách |
| --- | --- | --- | --- |
| `service.name` | Resource | `orders-service` | Ổn định theo dịch vụ |
| `deployment.environment.name` | Resource | `staging`, `production` | Tập giá trị có kiểm soát |
| `service.version` | Resource | `2026.11.22` | Giá trị theo phiên bản phát hành |
| Instrumentation scope | Tracer/instrumentation | `orders-business` | Xác định thành phần sinh spans |
| Span name | Một operation | `order.confirm` | Ổn định, không chứa ID động |
| Span attributes | Một lần chạy | `payment.provider=bank_a` | Cân nhắc cardinality, bảo mật và giới hạn SDK |
| Trace ID / Span ID | Trace/span context | Chuỗi hex theo propagator | Không dùng làm metric labels |

**Resource không phải baggage.** Resource mô tả nguồn phát telemetry. Baggage, khi được bật theo propagation, có thể đi qua nhiều service và phải được giới hạn dung lượng, key/value và độ nhạy cảm. Không nhầm `service.name` của process với thông tin về client hay người dùng đang gọi.

Khi có nhiều instance, backend có thể dùng thêm instance/pod/node metadata. Những nhãn hạ tầng cần được quản lý để dashboard truy vấn đúng theo service và môi trường, không làm nổ cardinality metrics.

## 8. Sampling không phải exporter, và propagation không phải sampling

Đây là ba quyết định dễ bị trộn:

1. **Sampling:** quyết định trace/span nào được ghi nhận hoặc xuất theo chính sách. Một trace không được sampled vẫn có thể có trace context để truyền downstream, tùy implementation.
2. **Propagation:** truyền Trace ID, Span ID của parent và flags qua HTTP/message/async context để downstream tiếp tục cùng trace.
3. **Exporting:** gửi span data đã ghi nhận tới collector/backend; có thể thất bại hoặc trễ vì mạng, queue, cấu hình hay backend.

```text
Một request vào service
        |
        +--> Propagator extract traceparent
        |
        +--> TracerProvider tạo span và Sampler quyết định
        |         |
        |         +--> recording span --> processor --> exporter --> backend
        |         |
        |         +--> non-recording span/context (theo SDK)
        |
        +--> HTTP client inject context --> downstream
```

Nếu `Sampler.parentBased(...)` tuân theo parent không sampled, downstream có thể không xuất span dù Trace ID được truyền hợp lệ. Nếu exporter lỗi, các span đã recording cũng có thể biến mất khỏi trace viewer. Nếu propagation đứt, downstream có thể tạo **Trace ID mới**, ngay cả khi cả hai service đều có provider và exporter hoạt động.

Các quyết định này cũng giải thích vì sao **trace không xuất hiện nhưng metrics vẫn có**: metric ObservationHandler/MeterRegistry có thể hoạt động độc lập với tracer sampling.

## 9. Propagation qua HTTP, thread và messaging

### HTTP giữa các service

Với W3C Trace Context, header `traceparent` thông thường có cấu trúc:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             vv ----------------trace-id-------- --------span-id--- flags
```

Đây là một ví dụ hợp lệ về hình dạng header: `trace-id` có 32 hex, `parent-id` có 16 hex, flag được diễn giải theo W3C. Định danh toàn số 0 là không hợp lệ. HTTP instrumentation cần inject/extract qua propagators tương thích để service B nhận trace context của service A.

Một `TracerProvider` được cấu hình đúng **không tự bảo đảm** headers luôn được truyền. Ví dụ HTTP client được tạo theo cách bỏ qua auto-instrumentation, proxy xóa header hoặc server không extract context, đều có thể khiến trace bị tách.

### Worker thread và asynchronous execution

Scope của span thường gắn với **execution context** hiện hành. Tạo task trên executor khác mà không có context propagation có thể làm `Span.current()` hoặc Micrometer `Tracer.currentSpan()` không còn là span của request cha.

Đối với Spring Framework có `ContextPropagatingTaskDecorator`, có thể cấu hình executor để khôi phục context khi chạy tác vụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class TracingExecutorConfig {

    @Bean
    ThreadPoolTaskExecutor tracingExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

Ví dụ phụ thuộc phiên bản Spring Framework có class này và cấu hình Micrometer Context Propagation tương ứng. Task thực tế **phải được submit vào đúng executor**; `CompletableFuture.runAsync(...)` không chỉ định executor có thể chạy ở common pool và không dùng decorator vừa cấu hình.

### Messaging và workflow dài

Với message producer/consumer, cần instrumentation inject/extract vào message headers; nhiều giờ sau có thể chủ động tạo trace mới và dùng span links hoặc business correlation thay vì kéo dài một trace vô hạn. Không đưa toàn bộ payload, token hoặc thông tin cá nhân vào baggage để “giữ context”.

## 10. Trace ID, logs và metrics: liên kết tín hiệu đúng cách

Giả sử request `POST /checkout` chậm vì payment provider:

```text
Metrics:
  http.server.requests{uri="/checkout",status="500"} tăng
  payment.authorize{provider="bank_a",outcome="error"} tăng

Trace (nếu sampled/export thành công):
  traceId=T
    POST /checkout                 spanId=A
      order.confirm               spanId=B
        payment.authorize         spanId=C
          HTTP POST provider      spanId=D (chậm)

Logs (nếu MDC correlation được bật):
  orders-service  traceId=T spanId=B "checkout failed"
  payment-service traceId=T spanId=C "provider timeout"
```

**Metrics** cho biết tỷ lệ lỗi và xu hướng độ trễ trên toàn hệ thống. **Traces** cho biết đường đi của một số request được ghi nhận, và **logs** giải thích loại lỗi/điều kiện nghiệp vụ trong các bước. Tracing provider chỉ phụ trách một phần luồng này; muốn tương quan được cần propagation và logging integration.

Không đưa `traceId`, `spanId`, order ID, raw URL, email hoặc exception message vào **low-cardinality metric tags**. Các giá trị ấy có cardinality cực cao, có thể tạo hàng triệu series và chi phí lưu trữ lớn. Với trace/log attributes cũng phải tránh secrets, quản lý quyền truy cập và giới hạn metadata.

Trace ID không phải một mã xác thực và không nên dùng để cấp quyền đọc trace/log. Có Trace ID trong log **không chứng minh** backend chứa trace đó: có thể do sampling, exporter, collector hoặc retention.

## 11. Những lỗi thường gặp với TracerProvider

| Hiện tượng | Nguyên nhân cần xem | Cách kiểm tra |
| --- | --- | --- |
| Có log hoạt động nhưng không thấy span trên backend | Chưa có SDK/handler, sampler loại, exporter không chạy, collector lỗi | Kiểm tra bridge, sampling, processor/exporter và backend |
| Spans xuất dưới `unknown_service` hoặc tên bất thường | Resource `service.name` chưa được đặt/override sai | Xem resource attributes thực tế ở backend |
| Service A và B có Trace ID khác nhau cho cùng giao dịch | HTTP/message propagation thiếu, proxy rewrite, task mất context | So W3C headers, client instrumentation và executor |
| Một request có hai bộ spans gần giống | Trùng instrumentation hoặc nhiều provider/agents | Kiểm kê auto-instrumentation, Micrometer bridge và OTel Java agent |
| Có HTTP spans nhưng không có custom business spans | Observation chưa được tạo, tracing handler/predicate thiếu hoặc scope sai | Xem registry, tên observation và tracing bridge |
| Mỗi span gọi exporter gây overhead lớn | Chọn processor không phù hợp, backend chậm | Ưu tiên batch processor, đo queue/drop/latency |
| Trace có spans nhưng logs thiếu trace ID | MDC không được xuất, log nằm ngoài scope | Kiểm tra logging pattern/encoder và context propagation |
| Span có Trace ID nhưng recording=false | Sampler quyết định không thu thập | Kiểm tra sampling policy/parent sampling, không coi là exporter lỗi |
| Chạy Spring Boot nhưng tự tạo thêm `SdkTracerProvider` | Hai nguồn cấu hình không đồng nhất | Chọn một nơi sở hữu tracing pipeline và lifecycle |

Đặc biệt với **OpenTelemetry Java agent**: agent có thể instrument tự động nhiều thư viện. Nếu đồng thời bật instrumentation của framework và thư viện khác theo cách chồng chéo, có thể có span trùng hoặc context không nhất quán. Không tắt/đổi agent tùy ý; xác định chủ sở hữu instrumentation cho từng ranh giới, kiểm tra kết quả trace thực tế và chọn chiến lược tương thích.

### Vì sao không nên dùng `GlobalOpenTelemetry` tùy tiện?

Một số thư viện thuần OpenTelemetry có thể dùng global instance. Trong Spring Boot được auto-config, tự thay global instance sau khi instrumentation đã khởi tạo có thể khiến các thành phần dùng những provider khác nhau hoặc hành vi phụ thuộc thứ tự bootstrap. Ưu tiên DI/tracing infrastructure của Spring Boot; nếu chủ động làm SDK manual thì tạo một pipeline nhất quán và xác định lifecycle ngay từ lúc bootstrap.

## 12. Quy trình kiểm chứng từ service đến backend

Một pipeline tracing đúng cần được kiểm tra ở nhiều lớp, không chỉ ở mã Java:

1. **Xác nhận dependency và version:** Spring Boot Actuator, Micrometer Tracing bridge, OpenTelemetry API/SDK/exporter nhất quán; không vô tình có hai providers.
2. **Xác nhận resource:** service name, environment/version và instrumentation scope đúng trong backend; không có metadata nhạy cảm.
3. **Kiểm tra sampling:** môi trường thử nghiệm có thể chọn xác suất cao để dễ nhìn thấy trace; với production cần chính sách chi phí và khả năng chẩn đoán.
4. **Tạo một thao tác đơn giản:** gọi HTTP endpoint có business Observation và xác minh span start/end, parent-child, thời lượng.
5. **Kiểm tra propagation:** gọi service downstream qua client có instrumentation; Trace ID nhất quán trong các service, Span ID và parent hợp lý.
6. **Kiểm tra async:** thực thi qua executor/message consumer có context propagation; kiểm tra log correlation và trace links/parent nếu cần.
7. **Kiểm tra exporter/collector:** OTLP endpoint, protocol, TLS/auth, queue, dropped spans, retry và ingest status.
8. **Đối chiếu metrics và logs:** metrics báo lỗi/latency ở khoảng thời gian nào, có log với trace ID và tracing backend có tìm được request đã sampled?
9. **Kiểm tra chi phí:** giới hạn span attributes/events, sampling, batch processor, cardinality metrics và không đưa secrets vào telemetry.

### Ma trận chẩn đoán tối thiểu

| Thử nghiệm | Kết quả mong đợi |
| --- | --- |
| Gọi `TracerProvider.get(...)` hoặc `OpenTelemetry.getTracer(...)` | Nhận Tracer phục vụ instrumentation, chưa đủ chứng minh exporter hoạt động |
| Tạo span có scope và gọi `end()` | Có recording span để processor xử lý nếu được sampled và SDK phù hợp |
| Collector không có kết nối | App vẫn có thể chạy; exporter báo lỗi/drop hoặc retry, trace backend thiếu |
| Sampling xác suất thấp | Ít spans được xuất; metrics có thể vẫn có theo handler riêng |
| HTTP client/server cùng propagator | Trace ID giữ qua service, tạo Span ID mới và parent phù hợp |
| Worker executor thiếu context propagation | Có thể mất current span/trace hoặc sinh trace mới |
| Có custom Observation nhưng không có tracing bridge | Observation có thể còn tác dụng metrics, không tự sinh OTel spans |
| Tên service không đúng | Trace tồn tại nhưng lọc theo service name dự kiến không ra |
| Hai instrumentation cùng bọc một DB call | Có thể xuất nhiều spans trùng nghĩa, cần phân tích lại |

## 13. Bài tập tình huống

Một nhóm phát hành `orders-service` (Spring Boot) và `payment-service`. Họ thêm `micrometer-tracing-bridge-otel`, khai báo OTLP exporter, rồi lại viết một configuration tạo `SdkTracerProvider` mới với `service.name=local-test` và `Sampler.alwaysOn()`. Khi kiểm tra:

```text
orders-service log: traceId=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
payment-service log: traceId=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb

Backend A:
  service.name=orders-service
  thấy một vài HTTP spans

Backend B:
  service.name=local-test
  thấy spans tạo bằng OTel API manual

Metrics:
  http.server.requests vẫn xuất đều
```

**Câu hỏi:** Có thể khẳng định lỗi do sampling hay do backend không? Cần xử lý theo trình tự nào?

**Gợi ý phân tích:**

1. **Chưa đủ bằng chứng** để quy tất cả lỗi cho sampling: hai provider/exporters có thể đã tạo hai pipeline độc lập, service name khác nhau và HTTP propagation giữa hai service cũng có thể bị mất.
2. Xác định **một nơi sở hữu** provider cho ứng dụng Spring Boot. Nếu dùng Micrometer bridge/auto-configuration, bỏ pipeline SDK manual không cần thiết và dùng cấu hình được framework hỗ trợ.
3. Kiểm tra service resource name, sampling policy, processor/exporter và OTLP endpoint/protocol của pipeline được giữ.
4. Kiểm tra `traceparent` qua HTTP client và server, đặc biệt khi code dùng client tự tạo hoặc proxy thay đổi header.
5. Kiểm tra logs có active span context/Trace ID từ pipeline đó. Một log có ID không đồng nghĩa tất cả spans được export.
6. Dùng metrics low-cardinality (provider/outcome, HTTP latency/error rate) xác định mức độ ảnh hưởng, không gắn Trace ID vào metric labels để “sửa” correlation.

**Kết luận:** **OpenTelemetry TracerProvider là gốc cấu hình của các Tracer trong một tiến trình**, còn `SdkTracerProvider` triển khai resource, sampling và span processors để xuất trace. Trong Spring Boot, nên để Micrometer Tracing bridge và framework quản lý provider nếu đã dùng auto-configuration; chỉ tự dựng SDK khi chủ động sở hữu toàn bộ pipeline. Propagation, exporter, logs và metrics là các phần phối hợp riêng: cấu hình nhất quán và kiểm chứng end-to-end quan trọng hơn việc chỉ tạo được một span trong code.

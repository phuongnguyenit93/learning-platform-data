# Dùng builder auto-configured để giữ context propagation trong Spring Boot

Trong chương **Context propagation** của module **SPRING_BOOT_OBSERVABILITY**, một nguyên nhân phổ biến làm trace bị đứt giữa các service là ứng dụng tự tạo HTTP client bằng constructor hoặc builder thuần, bỏ qua các customizer mà Spring Boot đã cấu hình. Khi đó request outbound có thể không được instrument, không tạo client span và không inject W3C trace context vào header.

Spring Boot cung cấp các **builder đã được auto-configure** như `RestClient.Builder`, `RestTemplateBuilder` và `WebClient.Builder`. Dùng chúng từ Spring Application Context giúp client nhận các thiết lập chung của ứng dụng, trong đó có observation/tracing instrumentation khi dependencies và cấu hình tương ứng đã bật. Đối với tác vụ bất đồng bộ, builder của task executor kết hợp `ContextPropagatingTaskDecorator` có thể giúp capture/restore context giữa thread.

Mục tiêu không chỉ là tạo một HTTP client chạy được. Mục tiêu là giữ được **Trace ID, parent-child span relationship và log correlation** qua những ranh giới mà ứng dụng kiểm soát, đồng thời tránh tự sao chép header hoặc vô tình tạo hai lớp instrumentation đo cùng một lời gọi.

## 1. Builder auto-configured giữ lại những gì?

Khi ứng dụng dùng Spring Boot Actuator và Micrometer Tracing bridge phù hợp, auto-configuration có thể chuẩn bị `ObservationRegistry`, convention và customizer cho những thành phần được hỗ trợ. Builder được Spring quản lý nhận các cấu hình này trước khi tạo client.

```text
Spring Application Context
    |
    +--> ObservationRegistry
    |       |
    |       +--> Observation handlers / tracing bridge
    |
    +--> RestClient.Builder / RestTemplateBuilder
    |       |
    |       +--> observation instrumentation
    |       +--> client observation convention/customizers
    |
    +--> WebClient.Builder
    |       |
    |       +--> observation instrumentation
    |       +--> reactive observation support
    |
    +--> ThreadPoolTaskExecutorBuilder
            |
            +--> TaskDecorator (khi được cấu hình)

Khi client gửi request trong một context đang hoạt động:
current span --> client observation/span --> inject traceparent
                                            |
                                            v
                                      downstream service
```

Builder không phải tracer hay propagator. Nó là **điểm lắp ráp client**; các customizer/observation registry/tracing bridge mới cung cấp phần instrumentation. Nếu ứng dụng không có tracing SDK/bridge/exporter, hoặc sampler không ghi nhận trace, sử dụng builder auto-configured vẫn không bảo đảm nhìn thấy span trong backend.

| Thành phần | Trách nhiệm |
| --- | --- |
| Auto-configured builder | Giữ các customizer và thiết lập Spring Boot đã áp dụng |
| `ObservationRegistry` | Nhận observation và chuyển tới handlers đã đăng ký |
| Micrometer Tracing bridge | Kết nối observation/span với tracer implementation |
| Propagator | Inject/extract context, ví dụ W3C `traceparent` |
| Exporter/collector | Gửi và tiếp nhận span đã được ghi nhận |
| Backend tracing | Lưu, tìm kiếm và hiển thị trace theo khả năng của hệ thống |

## 2. Dependency và cấu hình nền

Ví dụ dưới đây giả định ứng dụng Spring Boot sử dụng Actuator và Micrometer Tracing với OpenTelemetry bridge cùng OTLP exporter; version cần được quản lý đồng bộ bằng Spring Boot BOM phù hợp.

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
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

Nếu ứng dụng dùng reactive stack, cần thêm WebFlux starter phù hợp. Ví dụ cấu hình:

```yaml
spring:
  application:
    name: orders-service

management:
  tracing:
    sampling:
      probability: 1.0
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
```

`probability: 1.0` chỉ dùng để kiểm tra trong môi trường phát triển, nhằm dễ quan sát các trace. Production cần chọn sampling policy theo tải, yêu cầu điều tra và chi phí. Endpoint OTLP/HTTP và cổng `4318` chỉ là ví dụ; trong container/Kubernetes, `localhost` thường không trỏ tới collector ở container khác. Phải kiểm tra đúng protocol, DNS, TLS/auth và collector receiver.

Không cần tự tạo `ObservationRegistry` hoặc `SdkTracerProvider` thứ hai nếu Spring Boot đã auto-configure pipeline. Một nguồn cấu hình duy nhất giúp HTTP clients, server instrumentation và custom observations dùng cùng resource, sampler, propagator và exporter.

## 3. Dùng `RestClient.Builder` do Spring Boot cung cấp

Với Spring Framework hiện đại, `RestClient` là API HTTP đồng bộ. Spring Boot auto-configure một `RestClient.Builder` để ứng dụng inject và tùy chỉnh trước khi build.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class InventoryClientConfiguration {

    @Bean
    RestClient inventoryRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
```

Service sử dụng client đã được lắp ráp:

```java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class InventoryGateway {
    private final RestClient client;

    InventoryGateway(RestClient inventoryRestClient) {
        this.client = inventoryRestClient;
    }

    InventoryResponse reserve(ReserveRequest request) {
        return client.post()
                .uri("/api/inventory/reservations")
                .body(request)
                .retrieve()
                .body(InventoryResponse.class);
    }
}
```

`ReserveRequest` và `InventoryResponse` là kiểu domain/DTO do ứng dụng định nghĩa. Khi lời gọi `reserve(...)` diễn ra trong một trace context đang hoạt động và client observation/tracing đã bật, auto-configured client có thể:

1. Tạo client observation/span cho HTTP request.
2. Dùng context hiện tại làm parent.
3. Inject trace context qua propagator đã cấu hình, thường là W3C `traceparent`.
4. Ghi nhận duration/status và kết thúc observation/span.

Không cần tự đọc `Tracer.currentSpan()` rồi tự nối chuỗi `traceparent` vào header. Client instrumentation chịu trách nhiệm tạo span và inject đúng context.

## 4. Dùng `RestTemplateBuilder` để giữ cấu hình observation

Với codebase vẫn dùng `RestTemplate`, hãy inject `RestTemplateBuilder` từ Spring context:

```java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class LegacyInventoryClientConfiguration {

    @Bean
    RestTemplate inventoryRestTemplate(RestTemplateBuilder builder) {
        return builder
                .rootUri("http://inventory-service")
                .build();
    }
}
```

`RestTemplateBuilder` có thể mang các customizer do Boot đăng ký, trong đó có cấu hình observation tùy version và dependency. Tránh `new RestTemplate()` nếu mục tiêu là tái sử dụng auto-configuration của ứng dụng.

Lưu ý không gắn thêm một interceptor tự tạo để ghi đúng cùng HTTP metric/span nếu builder đã cấu hình client observation. Làm vậy có thể tạo spans trùng hoặc đo duration hai lần. Nếu cần interceptor cho xác thực, correlation nghiệp vụ hoặc header không nhạy cảm khác, giữ nhiệm vụ riêng biệt và không ghi đè trace headers do propagator quản lý.

## 5. Dùng `WebClient.Builder` trong ứng dụng reactive

Với WebFlux, inject `WebClient.Builder` auto-configured:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class PaymentClientConfiguration {

    @Bean
    WebClient paymentWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://payment-service")
                .build();
    }
}
```

Gọi downstream qua client này:

```java
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
class PaymentGateway {
    private final WebClient client;

    PaymentGateway(WebClient paymentWebClient) {
        this.client = paymentWebClient;
    }

    Mono<PaymentResponse> authorize(PaymentRequest request) {
        return client.post()
                .uri("/api/payments/authorize")
                .bodyValue(request)
                .retrieve()
                .bodyToMono(PaymentResponse.class);
    }
}
```

`PaymentRequest` và `PaymentResponse` là các DTO của ứng dụng. Trong reactive pipeline, context không nên được hiểu như ThreadLocal cố định trên một thread. Reactor có cơ chế context riêng; instrumentation tương ứng cần tích hợp context propagation để trace context đi theo subscription và các operator. Dùng `WebClient.Builder` auto-configured giúp giữ observation integration, nhưng code vẫn cần duy trì reactive chain, tránh tự tách công việc ra executor không tương thích hoặc gọi `.block()` tùy tiện trong reactive flow.

Nếu có nhiều WebClient khác nhau, có thể tạo nhiều bean dựa trên builder auto-configured với base URL/customizer khác nhau. Không tạo raw `WebClient.builder()` ở nơi cần Spring Boot customizers nếu mục tiêu là giữ cấu hình observation/tracing.

## 6. Điều gì xảy ra khi tự tạo raw builder?

Ví dụ dễ bỏ sót auto-configuration:

```java
// Không dùng cách này khi cần giữ customizers của Spring Boot.
RestClient client = RestClient.builder()
        .baseUrl("http://inventory-service")
        .build();

WebClient webClient = WebClient.builder()
        .baseUrl("http://payment-service")
        .build();
```

Các API builder tĩnh có thể tạo client hợp lệ về mặt HTTP, nhưng không tự đảm bảo chúng nhận các `RestClientCustomizer`, `RestTemplateCustomizer` hay `WebClientCustomizer` mà Spring Boot đăng ký. Kết quả có thể là:

- Không có observation cho lời gọi HTTP.
- Không có client span hoặc trace headers outbound.
- Metrics HTTP client không xuất hiện, dù server metrics vẫn có.
- Log phía downstream không liên kết được Trace ID với upstream.
- Dashboard cho thấy HTTP request chậm nhưng trace không có span outbound để khoanh vùng dependency.

Điều này không có nghĩa raw builder luôn không thể instrument. Có thể cấu hình thủ công observation registry/customizer/interceptor phù hợp. Nhưng nếu đã dùng Spring Boot auto-configuration, inject builder là con đường rõ ràng để kế thừa thiết lập tập trung.

## 7. Dùng builder đúng cách khi có nhiều client

Không nên thay đổi một builder dùng chung ở nhiều nơi sau khi đã tạo client, vì thay đổi cấu hình có thể gây bất ngờ cho bean khác. Một số builder của Spring Boot được cung cấp theo phạm vi prototype hoặc có cơ chế clone để tạo cấu hình độc lập; hãy dùng cách phù hợp với builder/version đang chạy.

Ví dụ tạo hai client có base URL khác nhau:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class DownstreamClients {

    @Bean
    RestClient inventoryClient(RestClient.Builder builder) {
        return builder.clone()
                .baseUrl("http://inventory-service")
                .build();
    }

    @Bean
    RestClient paymentClient(RestClient.Builder builder) {
        return builder.clone()
                .baseUrl("http://payment-service")
                .build();
    }
}
```

Nếu builder được Spring cung cấp như prototype, mỗi injection point có thể đã nhận instance riêng; clone vẫn giúp thể hiện ý định tạo cấu hình tách biệt. Cần xác minh API `clone()` của client builder ở phiên bản Spring Framework tương ứng. Không giữ một builder mutable trong static field hoặc chỉnh sửa tùy tiện sau khi nhiều bean đã sử dụng.

## 8. Giữ context khi chuyển sang executor

HTTP client builder giúp giữ instrumentation trên lời gọi HTTP. Nhưng khi request thread giao công việc sang thread pool, **context propagation giữa thread là một vấn đề riêng**. Chỉ inject `RestClient.Builder` hoặc `WebClient.Builder` không tự copy context sang executor.

Spring Framework cung cấp `ContextPropagatingTaskDecorator` ở các phiên bản hỗ trợ Micrometer Context Propagation. Có thể kết hợp với `ThreadPoolTaskExecutorBuilder` của Spring Boot:

```java
import org.springframework.boot.task.ThreadPoolTaskExecutorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class BackgroundTaskConfiguration {

    @Bean
    ThreadPoolTaskExecutor orderExecutor(
            ThreadPoolTaskExecutorBuilder builder) {
        return builder
                .corePoolSize(4)
                .maxPoolSize(8)
                .queueCapacity(100)
                .taskDecorator(new ContextPropagatingTaskDecorator())
                .build();
    }
}
```

Builder auto-configured giữ các cấu hình pool/customizer do Boot quản lý; việc truyền context được bổ sung rõ ràng bằng task decorator. Task phải thật sự được submit vào bean `orderExecutor`:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
class OrderAsyncService {
    private final Executor orderExecutor;

    OrderAsyncService(@Qualifier("orderExecutor") Executor orderExecutor) {
        this.orderExecutor = orderExecutor;
    }

    CompletableFuture<Void> persistAsync() {
        return CompletableFuture.runAsync(
                this::persistOrder,
                orderExecutor);
    }

    private void persistOrder() {
        // Context is restored if the matching accessors/integrations are registered.
    }
}
```

Nếu trong ứng dụng có nhiều `Executor` bean, cần dùng `@Qualifier("orderExecutor")` ở injection point để chắc chắn chọn đúng bean; hoặc inject đúng kiểu `ThreadPoolTaskExecutor` với tên bean tương ứng. Đoạn code rút gọn giả định chỉ có một executor phù hợp.

`ContextPropagatingTaskDecorator` không tạo trace mới, không tự gửi header và không kéo dài lifecycle của span vô hạn. Nó capture/restore các context accessor đã đăng ký khi task được submit/run. Với công việc nền bắt đầu sau khi request kết thúc, cần đánh giá semantics: tạo trace/job span riêng và liên kết với workflow trước bằng correlation/links có thể phù hợp hơn việc dùng parent span đã end.

## 9. Vì sao không tự copy `traceparent` bằng tay?

Một cách làm dễ gặp là đọc Trace ID từ `Tracer`, nối thành header rồi thêm vào mỗi HTTP request. Cách này không đầy đủ vì:

- Header W3C có **Trace ID, parent Span ID và trace flags**; mỗi lời gọi client cần span ID mới phù hợp, không chỉ copy Trace ID.
- Sampling decision và parent relationship phải nhất quán.
- Có thể có `tracestate`, baggage và propagator khác theo stack.
- Header từ client bên ngoài cần được validate theo chuẩn và trust boundary.
- Retry/redirect/async có lifecycle khác nhau; tự copy header có thể giữ sai parent span.

Với HTTP clients đã được instrument, để propagator inject/extract. Một `traceparent` minh họa:

```text
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ^^ -------------------------------- ---------------- ^^
             |          trace-id (32 hex)       parent-id (16 hex) flags
             version
```

Khi service downstream nhận request, nó tạo span mới có cùng Trace ID nếu context được chấp nhận và tiếp tục cùng trace; parent ID trong header là Span ID phía client. Không hardcode header trên vào application code.

## 10. Kiểm chứng propagation end-to-end

Để chứng minh builder auto-configured đang giữ tracing, không chỉ kiểm tra bean khởi tạo thành công. Hãy chạy một kịch bản có hai service trong môi trường test:

```text
Client
  |
  v
orders-service
  HTTP server span (Trace ID = T)
    |
    +-- order.confirm
          |
          +-- RestClient inventory call
                 HTTP client span (Trace ID = T, Span ID = C)
                      |
                      v
               inventory-service
                 HTTP server span
                 (Trace ID = T, Parent Span ID = C)
```

Các bước xác minh:

1. **Kiểm tra dependency/bridge:** Actuator, Micrometer Tracing bridge, SDK/exporter và collector tương thích version.
2. **Kiểm tra builder được inject:** client bean được tạo từ `RestClient.Builder`, `RestTemplateBuilder` hoặc `WebClient.Builder` trong Spring context.
3. **Tạo request trong trace context:** gọi endpoint của orders-service để server span có current context.
4. **Gọi downstream:** dùng client bean đã build, không tự tạo client mới ngoài Spring context.
5. **Xem trace backend:** kiểm tra có client span và server span downstream, cùng Trace ID, parent-child phù hợp.
6. **Kiểm tra logs:** nếu MDC correlation được cấu hình, log của hai service có thể mang Trace ID và Span ID tương ứng.
7. **Thử lỗi downstream:** xác minh status/error, thời lượng span và log có giúp tìm đúng dependency không.
8. **Thử async riêng:** submit task qua executor có decorator, xác minh context trong worker và gọi HTTP client từ worker nếu có.

Nếu không thấy trace, kiểm tra theo thứ tự:

| Hiện tượng | Khả năng | Cần kiểm tra |
| --- | --- | --- |
| Server span có nhưng không có client span | Client raw builder hoặc instrumentation bị thiếu | Builder được inject? Observation registry có gắn client không? |
| Client span có nhưng downstream mang Trace ID mới | Header không được inject/extract hoặc proxy sửa header | Propagator, HTTP client/server instrumentation, gateway |
| Client span không được export | Sampling, processor/exporter, collector lỗi | SDK, sampled decision, OTLP receiver/queue |
| Trace có nhưng logs thiếu Trace ID | MDC/logging correlation chưa cấu hình | Encoder/pattern và current scope |
| Request đồng bộ có context, worker thread không có | Executor thiếu context propagation | TaskDecorator, context accessor, đúng executor bean |
| Metrics có mà traces vắng | Metric handler chạy độc lập, tracing bridge/sampling lỗi | Tracing pipeline, không kết luận từ metric endpoint |

Một trace không xuất hiện do sampling không chứng minh builder không được auto-configure. Để test propagation, dùng môi trường thử nghiệm với sampling policy phù hợp và xác minh cả client/server spans.

## 11. Tránh duplicate instrumentation và cardinality cao

Builder auto-configured có thể đã gắn observation instrumentation cho HTTP client. Nếu lại thêm interceptor hoặc filter tạo span cho cùng một lời gọi, trace có thể chứa hai span đo trùng phạm vi. Trước khi instrument thủ công, hãy kiểm kê:

- HTTP client nào do Spring Boot tạo và được customizer áp dụng?
- Thư viện nào đang được OpenTelemetry Java agent tự động instrument?
- Có custom `Observation` bao quanh **nghiệp vụ** hay chỉ đo lặp lại toàn bộ HTTP call?
- Có interceptor nào tạo thêm span nhưng không có ý nghĩa riêng?

Custom observation vẫn có ích khi biểu diễn ranh giới như `inventory.reserve` hoặc `payment.authorize`, còn client span đo lời gọi mạng thực tế. Hai lớp có thể bổ trợ nhau vì chúng trả lời câu hỏi khác nhau.

Tag/attributes cần được kiểm soát. Nên dùng low-cardinality values như `provider=bank_a/bank_b`, `outcome=success/error`; tránh `traceId`, `orderId`, email, raw URL hoặc exception message làm metric labels. Trace ID có cardinality rất cao; log/tracing backend là nơi phù hợp hơn để tra cứu một request cụ thể với quyền truy cập phù hợp.

Propagation không có nghĩa đưa toàn bộ payload vào baggage. Chỉ truyền metadata nhỏ được allowlist, không truyền token, cookie, dữ liệu khách hàng hoặc request body. Header quá lớn có thể bị proxy/gateway từ chối.

## 12. Bài tập tình huống

Một `orders-service` dùng Spring Boot có tracing bridge. Controller có server span và log chứa Trace ID. Ứng dụng gọi `inventory-service` bằng hai client khác nhau:

```java
@Bean
RestClient inventoryClient(RestClient.Builder builder) {
    return builder.baseUrl("http://inventory-service").build();
}

// Ở một service cũ:
private final RestClient rawClient =
        RestClient.builder()
                .baseUrl("http://inventory-service")
                .build();
```

Nhóm quan sát thấy lời gọi từ bean `inventoryClient` có client span và downstream cùng Trace ID, còn lời gọi từ `rawClient` không có client span và log phía inventory dùng Trace ID mới.

**Câu hỏi:** Vì sao hai lời gọi có hành vi khác nhau? Có nên tự thêm header `traceparent` vào `rawClient` để sửa nhanh không?

**Gợi ý phân tích:**

1. Bean `inventoryClient` được build từ builder do Spring inject, nên có thể kế thừa customizers và observation instrumentation của Boot.
2. `rawClient` dùng static builder, bỏ qua customizers đã gắn với Spring context; nó có thể không tạo client observation/span hoặc không inject trace context.
3. Không nên tự copy `traceparent`: cần client span mới, parent ID đúng, flags/tracestate và propagator tương thích.
4. Sửa bằng cách tạo client qua builder auto-configured, kiểm tra bridge/registry và xác minh trace end-to-end.
5. Nếu raw client phải được tạo ngoài Spring, chủ sở hữu cần cấu hình observation/tracing instrumentation rõ ràng cho client đó và kiểm tra propagation.

### Checklist hoàn thành

| Thử nghiệm | Kết quả mong đợi |
| --- | --- |
| Inject auto-configured `RestClient.Builder` | Client bean kế thừa customizers của Spring Boot |
| Inject `RestTemplateBuilder` | RestTemplate nhận cấu hình của builder đã được Boot quản lý |
| Inject `WebClient.Builder` trong WebFlux | Client giữ observation integration/reactive context phù hợp |
| Dùng raw builder không cấu hình | Không mặc định có customizers/propagation |
| Gọi downstream trong current span | Client span dùng trace context cha nếu được instrument |
| Downstream nhận `traceparent` hợp lệ | Server span có cùng Trace ID và parent phù hợp |
| Chuyển công việc qua executor | Context giữ được khi task dùng executor có decorator và accessor tương ứng |
| Sampling không giữ trace | Không nhầm với lỗi builder hoặc lỗi propagation |
| Có HTTP agent instrumentation đồng thời | Không sinh span trùng cho cùng một ranh giới ngoài ý muốn |
| Metrics/logs/traces được kiểm tra | Tags hữu hạn, logs correlate, trace xuất khi được sampled/export thành công |

**Ghi nhớ:** Khi Spring Boot đã cấu hình observability, hãy **inject builder auto-configured từ Application Context** để tạo `RestClient`, `RestTemplate` hoặc `WebClient`. Cách này giúp giữ observation/tracing customizers và để propagator xử lý trace headers. Với công việc chuyển thread, cần executor có context propagation riêng; builder HTTP không thay thế task decorator. Kiểm chứng client/server spans, Trace ID, logs và exporter end-to-end để bảo đảm trace không bị đứt giữa các service.

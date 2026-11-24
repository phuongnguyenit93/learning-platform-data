# Micrometer, metric và tracing trong native executable

Một ứng dụng Spring Boot chạy dưới JVM hay dưới GraalVM Native Image đều cần trả lời các câu hỏi vận hành giống nhau: request mất bao lâu, tỷ lệ lỗi tăng ở đâu, service nào đang chậm và một request đi qua những thành phần nào. Micrometer cung cấp API đo lường thống nhất; Spring Boot Actuator tự cấu hình nhiều meter và Observation; Micrometer Tracing kết nối observation với distributed trace.

Khi build native, các API này vẫn có thể hoạt động vì instrumentation được biên dịch cùng ứng dụng. Điểm cần chú ý là native executable không phải một JVM đầy đủ: không có JIT compiler hay cơ chế nạp Java agent theo cách HotSpot thường dùng, một số metric JVM có thể khác hoặc không tồn tại, và mọi thư viện exporter/custom instrumentation phải tương thích với closed-world analysis.

Bài này xây dựng cấu hình quan sát cho dịch vụ Spring Boot native bằng Actuator, Micrometer Metrics, Micrometer Observation, OpenTelemetry và OTLP. Các ví dụ dùng Spring Boot 4.x; nếu dự án đang ở Boot 3.x, hãy dùng dependency và property reference của đúng minor version thay vì trộn cấu hình giữa các major version.

## 1. Ba tín hiệu quan sát và vai trò của Micrometer

Observability thường được tổ chức thành ba tín hiệu bổ sung nhau:

| Tín hiệu | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| Logs | Sự kiện nào đã xảy ra và chi tiết gì đi kèm? | Exception, trạng thái xử lý, log có trace ID |
| Metrics | Hệ thống đang hoạt động ra sao theo thời gian? | Request rate, latency, error count, memory |
| Traces | Một request đã đi qua những service/span nào? | HTTP server → service → database → HTTP client |

Metrics tổng hợp hoạt động thành chuỗi thời gian. Tracing giữ quan hệ cha-con của các thao tác trong một request. Logs lưu sự kiện chi tiết. Khi cả ba tín hiệu dùng chung context, có thể tìm một trace rồi mở log liên quan hoặc xem metric tại thời điểm trace chậm.

Spring Boot sử dụng Micrometer cho metrics và tracing:

- `MeterRegistry` nhận các meter như `Counter`, `Timer`, `Gauge` và `DistributionSummary`.
- `ObservationRegistry` điều phối một observation và các handler xử lý lifecycle của nó.
- `Micrometer Tracing` cung cấp API tracer độc lập với backend.
- Registry/exporter chuyển dữ liệu tới Prometheus, OTLP, Zipkin hoặc hệ thống giám sát khác.

`Observation` là lớp API thuận tiện khi một thao tác cần đồng thời tạo metric và span. Khi chỉ cần một số đo đơn giản, có thể dùng `MeterRegistry` trực tiếp.

## 2. Điều gì thay đổi khi ứng dụng chạy dưới Native Image?

Native Image được phân tích và biên dịch trước khi chạy. Executable chứa phần code có thể reach được từ entry point và các metadata mà build đã nhận diện. Không có JVM được đóng gói bên trong để nạp class và chạy JIT như ứng dụng `java -jar`.

Với observability, cần phân biệt:

1. **Instrumentation trong code:** lời gọi `Counter.increment()`, `Timer.record()` hoặc `Observation.observe()` được biên dịch vào executable. Đây là cách dùng Micrometer phù hợp với native.
2. **Auto-configuration của Spring:** Actuator và các integration mà Spring Boot hỗ trợ được xử lý qua AOT; framework đóng góp code và hints cần thiết.
3. **Exporter và thư viện bên thứ ba:** phải có mặt trên classpath khi build và tương thích Native Image. Nếu thư viện dùng reflection, resource hoặc proxy theo cách static analysis không suy ra được, có thể cần reachability metadata.
4. **Java agent lúc runtime:** agent dựa trên `java.lang.instrument`, `ClassFileTransformer` hoặc JVMTI không phải cơ chế instrumentation của native executable. Không lấy lệnh `-javaagent` của JVM làm cách cấu hình Micrometer cho native.

Một điểm rất dễ nhầm: **Micrometer Tracing là thư viện quan sát được biên dịch cùng ứng dụng; GraalVM Native Image Tracing Agent là công cụ chạy trên JVM để thu thập metadata cho native build.** Hai thứ có chữ “Tracing Agent” trong tên nhưng phục vụ hai mục đích khác nhau.

### Sơ đồ dữ liệu

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring MVC / WebFlux"]
    B --> C["Micrometer Observation"]
    C --> D["Meter handler"]
    C --> E["Tracing handler"]
    D --> F["MeterRegistry"]
    E --> G["Tracer / Span"]
    F --> H["Prometheus hoặc OTLP metrics"]
    G --> I["OTLP hoặc Zipkin traces"]
    B --> J["Application logs"]
    G --> K["Trace ID / Span ID trong MDC"]
    K --> J
~~~

## 3. Thêm dependency cho Actuator, metrics và tracing

Spring Boot quản lý phiên bản các dependency tương thích qua dependency management/BOM. Không tự thêm version riêng cho Micrometer nếu không có yêu cầu nâng cấp có chủ đích.

### Maven với OTLP

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

`spring-boot-starter-actuator` cung cấp endpoint và auto-configuration cho Micrometer. `spring-boot-starter-opentelemetry` cung cấp tích hợp Micrometer Tracing với OpenTelemetry trong Spring Boot 4.x. `micrometer-registry-otlp` đăng ký metrics exporter theo OTLP.

### Gradle với OTLP

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springframework.boot:spring-boot-starter-opentelemetry")
    implementation("io.micrometer:micrometer-registry-otlp")
}
~~~

### Nếu dùng Prometheus

Có thể thay registry OTLP metrics bằng Prometheus registry:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

~~~groovy
dependencies {
    implementation("io.micrometer:micrometer-registry-prometheus")
}
~~~

Có thể cấu hình nhiều registry cùng lúc nếu muốn gửi cùng meter đến nhiều backend. Khi làm vậy, cần chủ động kiểm tra chi phí export, số lượng time series và dữ liệu bị gửi trùng. Chọn một đường export chính trong môi trường thử nghiệm để xác minh trước.

## 4. Cấu hình Actuator endpoint và exporter

Ví dụ cấu hình `application.yml` cho OTLP:

~~~yaml
spring:
  application:
    name: orders-api

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics

  endpoint:
    health:
      probes:
        enabled: true

  metrics:
    tags:
      application: orders-api
      environment: staging

  otlp:
    metrics:
      export:
        url: http://otel-collector:4318/v1/metrics
        step: 30s

  opentelemetry:
    resource-attributes:
      service.name: orders-api
      deployment.environment: staging
    tracing:
      export:
        otlp:
          endpoint: http://otel-collector:4318/v1/traces

  tracing:
    sampling:
      probability: 0.1
~~~

Ý nghĩa:

- `management.endpoints.web.exposure.include` quyết định endpoint nào được mở qua HTTP.
- `/actuator/metrics` cho phép kiểm tra meter đã được đăng ký.
- `/actuator/health` và health probes phục vụ kiểm tra trạng thái ứng dụng.
- `management.metrics.tags` thêm tag có cardinality thấp cho các meter.
- `management.otlp.metrics.export.url` là endpoint nhận metrics OTLP.
- `management.opentelemetry.tracing.export.otlp.endpoint` là endpoint nhận trace OTLP.
- `service.name` và `deployment.environment` giúp phân biệt service và môi trường ở backend.
- `management.tracing.sampling.probability` điều khiển tỷ lệ request được lấy mẫu trace.

Nếu dùng OTLP endpoint chung, Spring Boot có property `management.opentelemetry.otlp.endpoint`; endpoint riêng theo từng signal sẽ được ưu tiên khi được cấu hình. Metrics exporter vẫn có property signal-specific `management.otlp.metrics.export.url`.

### Cấu hình endpoint Prometheus

Nếu dùng Prometheus, thêm `prometheus` vào danh sách endpoint exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Endpoint `/actuator/prometheus` trả dữ liệu theo định dạng scrape của Prometheus. Một cấu hình scrape tối thiểu:

~~~yaml
scrape_configs:
  - job_name: orders-api
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - orders-api:8080
~~~

Prometheus chủ động scrape từng instance. OTLP registry thường push dữ liệu theo chu kỳ. Chọn mô hình phù hợp với hệ thống giám sát và cách triển khai service.

### Không mở toàn bộ Actuator ra mạng công khai

Các endpoint metrics có thể tiết lộ thông tin về tài nguyên, throughput, dependency và trạng thái nội bộ. Chỉ expose endpoint thực sự cần, giới hạn mạng truy cập bằng network policy/security, và bảo vệ endpoint bằng Spring Security hoặc management interface riêng. Không dùng `include: "*"` như cấu hình production mặc định.

## 5. Tạo metric nghiệp vụ bằng MeterRegistry

Spring Boot tự đăng ký nhiều meter cho HTTP server/client, JVM, system, datasource, task executor và các integration được hỗ trợ. Ứng dụng vẫn nên tạo metric riêng cho những hành vi có ý nghĩa với nghiệp vụ.

Ví dụ một component ghi nhận số đơn hàng được tạo và thời gian xác thực thanh toán:

~~~java
package com.example.orders.observability;

import java.util.function.Supplier;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import org.springframework.stereotype.Component;

@Component
public class OrderMetrics {

    private final MeterRegistry registry;
    private final Counter createdOrders;
    private final Timer paymentAuthorization;

    public OrderMetrics(MeterRegistry registry) {
        this.registry = registry;

        this.createdOrders = Counter.builder("orders.created")
                .description("Number of orders created")
                .register(registry);

        this.paymentAuthorization = Timer.builder("payment.authorization")
                .description("Time spent authorizing a payment")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void orderCreated() {
        this.createdOrders.increment();
    }

    public <T> T measurePaymentAuthorization(Supplier<T> operation) {
        Timer.Sample sample = Timer.start(this.registry);
        try {
            return operation.get();
        }
        finally {
            sample.stop(this.paymentAuthorization);
        }
    }
}
~~~

Dùng component trong service:

~~~java
@Service
public class OrderService {

    private final OrderMetrics metrics;
    private final PaymentGateway paymentGateway;
    private final OrderRepository orderRepository;

    public OrderService(
            OrderMetrics metrics,
            PaymentGateway paymentGateway,
            OrderRepository orderRepository) {
        this.metrics = metrics;
        this.paymentGateway = paymentGateway;
        this.orderRepository = orderRepository;
    }

    public Order createOrder(CreateOrderCommand command) {
        PaymentResult result = this.metrics.measurePaymentAuthorization(
                () -> this.paymentGateway.authorize(command)
        );

        Order saved = this.orderRepository.save(Order.from(command, result));
        this.metrics.orderCreated();
        return saved;
    }
}
~~~

Ví dụ minh họa điểm đặt instrumentation; trong ứng dụng thật, chỉ tăng `orders.created` sau khi đơn hàng đã được lưu thành công. Không đặt counter trước một thao tác có thể rollback rồi vẫn ghi nhận thành công.

### Chọn meter đúng với câu hỏi

| Meter | Dùng khi | Ví dụ |
| --- | --- | --- |
| Counter | Cần đếm sự kiện tăng dần | Số đơn được tạo, số lần thanh toán bị từ chối |
| Timer | Cần đo thời lượng và số lần thực hiện | Thời gian gọi payment gateway |
| Gauge | Cần đọc giá trị hiện tại | Số message đang chờ trong queue |
| DistributionSummary | Cần phân phối của một giá trị số | Kích thước payload, số item trong batch |
| LongTaskTimer | Cần theo dõi thao tác còn đang chạy | Báo cáo hoặc batch dài |

Không tạo một meter mới cho từng request. Hãy đăng ký meter một lần, sau đó cập nhật giá trị qua reference đã lưu.

## 6. Dùng Observation để tạo metrics và traces cùng một thao tác

`ObservationRegistry` cho phép ứng dụng mô tả một thao tác theo lifecycle thống nhất. Khi Spring Boot đăng ký `DefaultMeterObservationHandler`, observation đã hoàn tất có thể tạo timer/counter. Khi Micrometer Tracing được cấu hình, tracing handler cũng có thể tạo span tương ứng.

Ví dụ quan sát bước xác thực thanh toán:

~~~java
package com.example.orders.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.stereotype.Component;

@Component
public class PaymentObservation {

    private final ObservationRegistry registry;

    public PaymentObservation(ObservationRegistry registry) {
        this.registry = registry;
    }

    public <T> T observeAuthorization(
            String paymentMethod,
            String orderId,
            java.util.function.Supplier<T> operation) {

        return Observation.createNotStarted(
                        "payment.authorization",
                        this.registry
                )
                .lowCardinalityKeyValue("payment.method", paymentMethod)
                .highCardinalityKeyValue("order.id", orderId)
                .observe(operation);
    }
}
~~~

Hai loại key-value có vai trò khác nhau:

- `lowCardinalityKeyValue` được dùng cho metrics và traces. Giá trị nên thuộc một tập hữu hạn như `card`, `bank-transfer`, `success`, `failed`.
- `highCardinalityKeyValue` chỉ dành cho trace hoặc signal có thể chịu được cardinality lớn. Ví dụ `order.id`, `user.id` hoặc request identifier.

Micrometer không đưa high-cardinality key-value vào meter tags vì mỗi giá trị duy nhất có thể tạo một time series mới. Nếu gắn `order.id` vào metric, số lượng meter có thể tăng theo số đơn hàng và làm tăng memory cũng như chi phí backend.

### Không tạo observation trùng lặp

Spring Boot đã instrument nhiều thành phần như HTTP server, HTTP client và repository. Nếu thêm `@Observed` hoặc tạo observation thủ công quanh chính thành phần đã được tự động instrument, backend có thể nhận hai observation cho cùng một thao tác.

Chỉ thêm observation cho ranh giới nghiệp vụ chưa được quan sát. Nếu cần dùng annotation `@Observed`, `@Timed`, `@Counted`, `@MeterTag` hoặc `@NewSpan`, bật `management.observations.annotations.enabled=true` và thêm AspectJ Weaver phù hợp. Annotation-based instrumentation cần AOP support; hãy xác minh cả proxy behavior lẫn native compatibility.

## 7. Cấu hình tracing với OpenTelemetry và OTLP

Spring Boot hỗ trợ Micrometer Tracing với OpenTelemetry/OTLP và OpenZipkin Brave/Zipkin. Ví dụ ở bài này chọn OpenTelemetry và OTLP.

Trong môi trường container, có thể cấu hình collector bằng environment variables:

~~~bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces
OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=http://otel-collector:4318/v1/metrics
OTEL_SERVICE_NAME=orders-api
OTEL_RESOURCE_ATTRIBUTES=deployment.environment=staging
~~~

Spring Boot ánh xạ một số OpenTelemetry environment variables sang configuration properties. Endpoint riêng của traces/metrics có ưu tiên hơn endpoint chung. Nếu dùng HTTP và chỉ cung cấp endpoint chung, Spring Boot bổ sung path theo signal như `/v1/traces` hoặc `/v1/metrics`.

Có thể cấu hình trực tiếp trong `application.yml` như mục trước. Với production, hãy lấy endpoint, headers và token từ secret/configuration management của môi trường. Không commit access token hoặc API key vào source control.

### Sampling

Spring Boot mặc định lấy mẫu 10% request để tránh gửi quá nhiều trace. Có thể thay đổi bằng:

~~~yaml
management:
  tracing:
    sampling:
      probability: 0.05
~~~

Không nên bật `1.0` cho mọi request trong production có lưu lượng lớn nếu chưa đánh giá chi phí. Có thể tăng tỷ lệ ở staging để debug và giảm tỷ lệ ở production. Khi dùng OpenTelemetry, sampler còn hỗ trợ chế độ parent-based để trace con tôn trọng quyết định lấy mẫu của trace cha.

### Giới hạn span

Span có thể chứa attributes, events, links và giá trị string. Giới hạn chúng để tránh payload quá lớn:

~~~yaml
management:
  opentelemetry:
    tracing:
      limits:
        max-attributes: 64
        max-attribute-value-length: 256
~~~

Nếu backend có giới hạn riêng, cấu hình tương thích với giới hạn đó. Không ghi request body, access token, mật khẩu hoặc dữ liệu cá nhân vào span attributes.

## 8. Truyền trace qua HTTP client, async và reactive pipeline

Một trace chỉ hữu ích khi quan hệ giữa các thao tác được truyền đúng qua ranh giới thread và service.

### Dùng builder do Spring Boot cấu hình

Để tự động truyền trace context qua HTTP, tạo `RestClient` hoặc `WebClient` bằng builder được Spring Boot auto-configure:

~~~java
@Configuration(proxyBeanMethods = false)
public class PartnerClientConfiguration {

    @Bean
    RestClient partnerRestClient(RestClient.Builder builder) {
        return builder
                .baseUrl("http://partner-service")
                .build();
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
public class ReactivePartnerClientConfiguration {

    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://partner-service")
                .build();
    }
}
~~~

Nếu tự tạo client bằng constructor hoặc builder không được Spring quản lý, instrumentation và trace propagation tự động có thể không được gắn vào. Khi đó cần áp dụng customizer tương ứng hoặc dùng builder đã auto-configure.

### Context propagation với reactive

Trong reactive pipeline, `ThreadLocal` không tự động được khôi phục ở mọi operator. Có thể bật automatic context propagation:

~~~yaml
spring:
  reactor:
    context-propagation: auto
~~~

Điều này giúp observation/tracing context được truyền qua reactive operators theo cơ chế Context Propagation.

### Context propagation với @Async

Với `AsyncTaskExecutor` do Spring Boot auto-configure, bật:

~~~yaml
spring:
  task:
    execution:
      propagate-context: true
~~~

Nếu tự cấu hình executor, đăng ký `ContextPropagatingTaskDecorator`:

~~~java
@Configuration(proxyBeanMethods = false)
public class AsyncConfiguration {

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

Nếu thiếu context propagation, trace có thể bị đứt ở thread mới: log không có trace ID hoặc span con không nằm trong trace cha.

## 9. Liên kết trace ID với logs

Khi Micrometer Tracing được cấu hình, Spring Boot bổ sung trace ID và span ID vào MDC để log có thể được liên kết với trace. Log pattern mặc định có correlation ID từ hai giá trị này.

Có thể tùy chỉnh format, ví dụ:

~~~yaml
logging:
  pattern:
    correlation: "[orders-api,%X{traceId:-},%X{spanId:-}] "
  include-application-name: false
~~~

Một dòng log sau đó có thể chứa service name, trace ID và span ID. Khi tìm lỗi trong backend tracing, có thể lấy trace ID để lọc log tương ứng.

Baggage có thể mang thêm context qua service boundary. Chỉ truyền những trường thật sự cần, có giới hạn kích thước và không chứa secret/PII không cần thiết. Baggage cũng có thể được đưa vào MDC hoặc span tags nếu cấu hình, vì vậy hãy kiểm soát rõ trường nào được propagate.

## 10. Kiểm tra metric endpoint và exporter

Actuator cung cấp hai endpoint hữu ích:

- `/actuator/metrics`: liệt kê meter và xem một meter theo tên.
- `/actuator/prometheus`: xuất dữ liệu theo format Prometheus khi registry và endpoint đã được cấu hình.

Ví dụ xem meter:

~~~bash
curl http://localhost:8080/actuator/metrics/orders.created
~~~

Xem timer:

~~~bash
curl http://localhost:8080/actuator/metrics/payment.authorization
~~~

Xem một meter theo tag:

~~~bash
curl "http://localhost:8080/actuator/metrics/http.server.requests?tag=method:POST"
~~~

Tên meter trong metrics endpoint là tên Micrometer đăng ký trong code. Backend Prometheus có thể chuẩn hóa tên thành snake case; đừng dùng tên đã normalize để truy vấn endpoint Actuator.

Với Prometheus:

~~~bash
curl http://localhost:8080/actuator/prometheus
~~~

Với OTLP, metrics registry gửi batch theo chu kỳ cấu hình. Kiểm tra log exporter, endpoint collector và dữ liệu tại backend. Việc endpoint `/actuator/metrics` trả về meter chỉ chứng minh meter đã được ghi nhận trong process; nó chưa chứng minh exporter gửi thành công tới backend.

## 11. Những khác biệt cần kiểm tra giữa JVM và native executable

Native executable không phải một JVM chạy nhanh hơn. Vì vậy, không nên so sánh một cách máy móc mọi meter JVM giữa hai loại binary.

| Nhóm metric | JVM executable | Native executable |
| --- | --- | --- |
| Metric nghiệp vụ tự tạo | Có nếu code được chạy | Có nếu code được reach và chạy |
| HTTP server/client metrics | Có khi integration được cấu hình | Có khi server/client integration tương thích và được đưa vào image |
| Database/connection pool metrics | Theo driver/pool integration | Theo driver/pool integration và reachability support |
| Process/system metrics | Phụ thuộc OS và Micrometer binder | Phụ thuộc OS, native runtime và binder được hỗ trợ |
| JVM memory/GC metrics | Theo MXBean của JVM | Có thể khác hoặc thiếu; native runtime không phải HotSpot heap |
| Class loading/JIT metrics | Có các metric liên quan class loader/JIT | Không có JIT compilation ở runtime; không kỳ vọng cùng bộ metric |
| Application startup/ready time | Có | Có thể dùng để đo startup/ready của ứng dụng native |

Khi benchmark observability cho native, nên ghi lại:

- `application.started.time` và `application.ready.time`.
- Process CPU, memory và số thread nếu binder/OS cung cấp.
- Request rate, error rate và latency.
- Exporter queue, export duration và lỗi gửi telemetry.
- Số meter, số series và số span được tạo.
- Tỷ lệ sampling và kích thước span.

Đừng dùng JIT compilation time để đánh giá native executable vì native code đã được biên dịch trước. Với memory, phân biệt heap/process RSS/container memory và cách backend thu thập từng giá trị; chúng không nhất thiết có cùng ý nghĩa giữa JVM và native.

## 12. Kiểm thử observability trong JVM và native

Nên chia test thành ba lớp.

### Unit test cho instrumentation

Dùng `SimpleMeterRegistry` để xác minh Counter/Timer được cập nhật đúng mà không cần kết nối backend. Với Observation, dùng `TestObservationRegistry` để xác minh observation name, lifecycle và key-value.

Những test này kiểm tra code instrumentation, không kiểm tra exporter hoặc native image.

### Integration test trên JVM

Kiểm tra:

- Actuator endpoint đã expose đúng.
- Registry được auto-configure khi dependency có trong runtime classpath.
- Metrics endpoint có meter nghiệp vụ.
- Traces được export tới collector/backend thử nghiệm.
- `RestClient`/`WebClient` truyền trace context.
- Context propagation hoạt động qua `@Async` hoặc Reactor.
- Log có correlation ID khi trace được lấy mẫu.

Lưu ý: Spring Boot không auto-configure các tracing components có reporting khi dùng `@SpringBootTest` theo cấu hình test mặc định. Nếu test cần kiểm tra exporter, hãy cấu hình tracing test một cách tường minh hoặc dùng một integration test chạy ứng dụng với collector thử nghiệm. Không suy luận exporter production bị hỏng chỉ vì test context không khởi tạo reporting components.

### Native smoke/integration test

Sau khi build executable:

~~~bash
# Maven project đã cấu hình native profile.
./mvnw -Pnative native:compile

# Gradle project đã cấu hình Native Build Tools.
./gradlew nativeCompile
~~~

Chạy native executable trong môi trường có collector/backend thử nghiệm. Gửi request tạo đơn, request lỗi và request gọi sang service khác. Xác minh:

1. Actuator health endpoint trả trạng thái phù hợp.
2. Metrics endpoint liệt kê meter ứng dụng.
3. Prometheus scrape hoặc OTLP collector nhận metrics.
4. Collector nhận trace với service name và resource attributes đúng.
5. Trace con được nối với trace cha qua HTTP.
6. Logs chứa correlation ID tương ứng.
7. Không có missing class, resource hoặc exporter initialization error trong native runtime.

Không dừng ở việc binary khởi động thành công. Cần thực hiện request để kích hoạt instrumentation và exporter.

## 13. Reachability, AOT và thư viện observability bên thứ ba

Các integration Actuator/Micrometer được Spring Boot hỗ trợ thường có auto-configuration và AOT contributions phù hợp. Tuy vậy, không thể suy ra rằng mọi registry, exporter hoặc instrumentation agent của bên thứ ba đều hoạt động trong native.

Nếu một custom exporter dùng reflection, `ServiceLoader`, resource hoặc dynamic proxy:

1. Kiểm tra thư viện có tài liệu GraalVM Native Image support hay reachability metadata không.
2. Xác minh implementation được đưa vào runtime classpath lúc build.
3. Kiểm tra Spring AOT có nhận diện bean và auto-configuration không.
4. Nếu thiếu metadata, chạy ứng dụng trên JVM với GraalVM Tracing Agent và thực hiện luồng export.
5. Review metadata được sinh ra, sau đó build lại native.
6. Chạy native integration test để xác nhận exporter hoạt động.

Không nhầm GraalVM Tracing Agent với Micrometer Tracing. Tracing Agent chỉ giúp thu metadata reflection/resource/proxy trên JVM; nó không xuất metric hoặc trace nghiệp vụ tới backend.

Nếu một sản phẩm APM yêu cầu `-javaagent` hoặc JVMTI để instrument bytecode lúc runtime, hãy xác nhận khả năng hỗ trợ native riêng từ nhà cung cấp. Native executable không có cơ chế Java Instrumentation giống HotSpot; chọn SDK hoặc integration được thiết kế cho native nếu có.

## 14. Bảo vệ chi phí và chất lượng telemetry

Một hệ thống observability có thể làm tăng CPU, memory, network và chi phí lưu trữ nếu cấu hình không hợp lý.

### Giữ cardinality của metric ở mức thấp

Không gắn các giá trị không giới hạn vào metric tags:

| Không nên dùng làm metric tag | Nên dùng |
| --- | --- |
| `order.id` | `payment.method` |
| `user.email` | `customer.tier` |
| `request.id` | `http.method` |
| Full URL có ID | URI template như `/orders/{id}` |
| Timestamp | `region`, `environment` |

ID của request có thể hữu ích trong trace hoặc log nhưng không nên tạo một time series mới cho mỗi request.

### Kiểm soát sampling và span size

- Chọn sampling phù hợp lưu lượng.
- Giới hạn attributes/events/links trên span.
- Tránh ghi payload hoặc object lớn vào span.
- Không gửi cùng một observation hai lần.
- Dùng `ObservationPredicate` nếu cần loại một nhóm observation khỏi báo cáo.
- Kiểm tra exporter timeout, queue và batch size để tránh backlog khi collector mất kết nối.

### Xử lý ứng dụng ngắn hạn

Prometheus scrape từng instance nên có thể bỏ lỡ batch job hoặc process kết thúc trước lần scrape tiếp theo. Với tác vụ ngắn hạn, cân nhắc OTLP push hoặc Prometheus Pushgateway theo mô hình vận hành phù hợp. Không dùng Pushgateway thay cho scrape thông thường của service dài hạn nếu không có nhu cầu rõ ràng.

## 15. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `/actuator/metrics` trả 404 | Endpoint chưa expose hoặc Actuator chưa có trong classpath | Kiểm tra dependency và `management.endpoints.web.exposure.include` |
| Có meter nhưng Prometheus không scrape được | Thiếu Prometheus registry hoặc endpoint chưa expose | Kiểm tra registry dependency và `/actuator/prometheus` |
| Metrics endpoint có dữ liệu nhưng OTLP backend trống | Exporter chưa được auto-configure, endpoint sai hoặc network bị chặn | Kiểm tra dependency, property URL, log exporter và collector |
| JVM có metric nhưng native không có một số `jvm.*` | Native runtime không cung cấp cùng MXBean/JIT metric | Đối chiếu metric cụ thể; dùng process/container metric phù hợp |
| Trace không xuất hiện | Tracing exporter không được cấu hình, sampling bỏ trace hoặc collector không nhận | Kiểm tra starter, sampling, endpoint và collector |
| Trace bị đứt khi gọi service khác | Client được tạo không dùng builder auto-configure hoặc context không được propagate | Dùng `RestClient.Builder`/`WebClient.Builder` của Spring và kiểm tra propagation |
| Log không có trace ID | Trace không được lấy mẫu, MDC/correlation hoặc context propagation bị tắt | Kiểm tra tracing config và logging pattern |
| `@Async` mất trace context | Executor không propagate context | Bật property hoặc dùng `ContextPropagatingTaskDecorator` |
| Native build thiếu class/resource của exporter | Thư viện dùng dynamic access chưa có metadata | Kiểm tra reachability metadata và Tracing Agent output |
| Telemetry bị mất ở ứng dụng ngắn hạn | Export interval lớn hơn thời gian process hoặc shutdown đột ngột | Dùng exporter phù hợp batch job và xác minh graceful shutdown |
| Số lượng time series tăng liên tục | Metric tag có cardinality cao hoặc tên meter chứa giá trị động | Bỏ ID/request/full URL khỏi metric tags |
| Có hai timer/span cho một thao tác | Auto instrumentation và custom observation bị trùng | Gỡ annotation hoặc tắt observation tự động tương ứng |

## 16. Bài thực hành: quan sát dịch vụ Order API chạy native

Tạo một Spring Boot REST API có endpoint `POST /orders`, một service xử lý đơn hàng và một `PaymentGateway` gọi sang service đối tác.

Thực hiện:

1. Thêm Actuator, OpenTelemetry starter và OTLP metrics registry.
2. Cấu hình resource attributes gồm `service.name`, `deployment.environment` và version ứng dụng.
3. Expose `health`, `info` và `metrics`; chỉ expose `prometheus` nếu đã thêm Prometheus registry.
4. Tạo Counter `orders.created` và Timer `payment.authorization`.
5. Tạo Observation `payment.authorization` với `payment.method` là low-cardinality và `order.id` là high-cardinality.
6. Tạo `RestClient` bằng builder auto-configure để truyền trace context tới payment service.
7. Cấu hình sampling và OTLP collector endpoint.
8. Chạy JVM, gửi request thành công và request lỗi; kiểm tra metrics, traces và log correlation.
9. Build native executable và gửi lại cùng request.
10. So sánh các meter xuất hiện trên JVM/native; ghi lại metric nào khác vì runtime không phải HotSpot.
11. Kiểm tra exporter, collector và context propagation khi chạy native.
12. Tăng tải thử nghiệm và quan sát cardinality, sampling, export queue và memory overhead.

### Câu hỏi tự kiểm tra

1. Metrics, traces và logs trả lời những câu hỏi khác nhau nào?
2. `MeterRegistry` khác `ObservationRegistry` ở vai trò nào?
3. Vì sao `Observation` có thể tạo cả timer và span?
4. Khi nào nên dùng Counter, Timer và Gauge?
5. Vì sao `order.id` nên là high-cardinality trace attribute thay vì metric tag?
6. Vì sao Spring Boot native vẫn có thể dùng Micrometer mà không cần Java agent?
7. GraalVM Native Image Tracing Agent khác Micrometer Tracing như thế nào?
8. Vì sao không nên kỳ vọng JIT compilation metric trên native executable?
9. Vì sao phải dùng builder auto-configure khi tạo `RestClient` hoặc `WebClient`?
10. Cần kiểm tra những gì khi metrics xuất hiện trên Actuator nhưng OTLP backend không nhận dữ liệu?
11. Vì sao test `@SpringBootTest` có thể không tự export tracing data?
12. Những trường hợp nào cần bổ sung reachability metadata cho exporter bên thứ ba?

**Tiêu chí đạt:** cấu hình được Actuator và một metrics registry; tạo được metric nghiệp vụ bằng Micrometer; dùng Observation để kết hợp metrics và tracing; cấu hình OTLP sampling/resource attributes; truyền trace qua HTTP client và async/reactive context; phân biệt metric JVM với native; cuối cùng xác minh metrics, traces và log correlation trên native executable mà không phụ thuộc Java agent runtime.

## Tài liệu chính thức

- Spring Boot — Observability: https://docs.spring.io/spring-boot/reference/actuator/observability.html
- Spring Boot — Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Boot — Tracing: https://docs.spring.io/spring-boot/reference/actuator/tracing.html
- Spring Boot — Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Boot — Introducing GraalVM Native Images: https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html
- Micrometer — Observation Introduction: https://docs.micrometer.io/micrometer/reference/observation/introduction.html
- Micrometer — Observation Components: https://docs.micrometer.io/micrometer/reference/observation/components.html
- Micrometer — OTLP Registry: https://docs.micrometer.io/micrometer/reference/implementations/otlp.html
- Micrometer — High Cardinality Tags Detector: https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html

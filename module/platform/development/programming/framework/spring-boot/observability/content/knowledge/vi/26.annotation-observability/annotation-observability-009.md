# Annotation trên service method trong Spring Boot

Trong ứng dụng Spring Boot, service method thường đại diện cho một thao tác nghiệp vụ như tạo đơn hàng, tính phí vận chuyển hoặc xác nhận thanh toán. Khi method chạy chậm hoặc phát sinh lỗi, chỉ có HTTP server metrics thường chưa đủ để biết phần nghiệp vụ nào chiếm thời gian. Annotation observability cho phép gắn metadata và lifecycle đo lường vào method, giúp theo dõi thời lượng, kết quả, metrics và distributed traces mà không phải tự viết boilerplate quanh mọi lời gọi.

Trong module SPRING_BOOT_OBSERVABILITY, annotation observability kết nối Micrometer Observation, metrics, logs và distributed tracing. Bài thuộc chương Annotation observability, tập trung vào annotation trên service method: cách dùng @Observed, điều kiện auto-configuration/AOP, cách annotation tạo Observation, naming và cardinality, self-invocation, async/reactive boundaries, kiểm thử và troubleshooting.

## Mục tiêu học tập

1. Giải thích vai trò của annotation trên service method trong observability.
2. Phân biệt @Observed với @Transactional, @Async và các annotation điều khiển nghiệp vụ.
3. Cấu hình Spring Boot/Micrometer để annotation tạo Observation.
4. Hiểu AOP proxy, method visibility và self-invocation.
5. Chọn observation name, low-cardinality và high-cardinality key-values an toàn.
6. Liên kết service Observation với HTTP/JDBC/client spans.
7. Hiểu annotation behavior trong async, reactive và exception paths.
8. Kiểm thử metrics, tracing, tags và proxy behavior.

## 1. Vì sao instrument service method?

HTTP request thường đi qua controller, service và repository. Server span cho biết tổng thời gian xử lý request, nhưng không nhất thiết chỉ ra service operation nào chiếm phần lớn thời gian. Observation trên service method giúp đặt ranh giới nghiệp vụ có ý nghĩa trong trace.

~~~text
HTTP server span: POST /orders
  └─ Observation: orders.create
       ├─ Observation: pricing.calculate
       ├─ HTTP client span: inventory.reserve
       └─ JDBC span: INSERT orders
~~~

Ví dụ service method có thể đại diện một use case ổn định. Trace viewer sẽ hiển thị operation name, thời gian, lỗi và các child spans được tạo trong quá trình method chạy.

### 1.1. Annotation không tự động có nghĩa là tracing

Một annotation chỉ tạo telemetry khi runtime có cơ chế xử lý annotation, thường là Spring AOP interceptor/aspect và Observation infrastructure. Nếu thiếu dependency, auto-configuration hoặc proxy không áp dụng, method vẫn chạy nhưng không có Observation.

Cần kiểm tra cả:
- annotation có mặt trên method;
- AOP/Observation integration có được cấu hình;
- ObservationRegistry và handlers có trong application context;
- tracing bridge/sampler/exporter nếu muốn spans;
- MeterRegistry nếu muốn metrics.

### 1.2. Observation là abstraction

Micrometer Observation cung cấp lifecycle và context cho operation. Observation handlers có thể xuất ra metrics và tracing. Annotation giúp khai báo điểm bắt đầu/kết thúc; nó không thay thế registry, handler, tracer, meter registry hoặc exporter.

## 2. @Observed trên service method

Micrometer cung cấp annotation @Observed để đánh dấu method hoặc type cần được quan sát. Ví dụ:

~~~java
import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    @Observed(name = "orders.create")
    public OrderResult createOrder(CreateOrderCommand command) {
        validate(command);
        reserveInventory(command);
        return persist(command);
    }

    private void validate(CreateOrderCommand command) {
        // Validate business rules.
    }

    private void reserveInventory(CreateOrderCommand command) {
        // Call inventory service.
    }

    private OrderResult persist(CreateOrderCommand command) {
        // Persist order.
        return new OrderResult("accepted");
    }
}
~~~

Khi method được gọi qua Spring proxy và annotation infrastructure đã bật, Observation có tên orders.create bao quanh method invocation. Tùy handlers, operation có thể tạo timer/metrics và span.

### 2.1. Cấu hình annotation support

Với Spring Boot, cần dùng dependency và auto-configuration tương ứng phiên bản. Ví dụ dependency nền:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-observation'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Trong ứng dụng Boot, một số dependency Micrometer được kéo vào qua Actuator/BOM. Không thêm version riêng nếu Boot BOM đã quản lý. Annotation support cần module AOP tương ứng, thường là spring-boot-starter-aop trong các cấu hình dùng proxy.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
~~~

Kiểm tra version Spring Boot/Micrometer cụ thể: tên property bật annotation và auto-configuration có thể khác giữa các release. Không suy đoán property; xác minh với tài liệu của version đang dùng và test một method thật.

### 2.2. Bật observed aspect

Micrometer/Spring Boot cung cấp cấu hình để bật aspect xử lý @Observed. Trong những phiên bản Spring Boot có property tương ứng, cấu hình thường được đặt dưới management.observations.annotations. Ví dụ minh họa:

~~~yaml
management:
  observations:
    annotations:
      enabled: true
~~~

Property này phụ thuộc phiên bản Boot. Kiểm tra configuration metadata/reference đúng version trước khi áp dụng. Nếu ứng dụng tự cấu hình ObservationAspect, tránh đăng ký đồng thời auto-configured aspect và custom aspect.

### 2.3. Tên Observation ổn định

Tên observation nên phản ánh use case hoặc operation:
- orders.create
- payment.authorize
- inventory.reserve
- pricing.calculate

Không gắn dữ liệu động vào tên như orders.create.12345 hoặc payment.authorize.customer-9. Tên động gây cardinality cao và làm dashboard/trace search khó tổng hợp.

## 3. Annotation tạo Observation như thế nào?

~~~mermaid
sequenceDiagram
    participant Caller
    participant Proxy as Spring AOP proxy
    participant Aspect as Observed aspect
    participant Method as Service method
    participant Handler as Observation handlers
    Caller->>Proxy: createOrder(command)
    Proxy->>Aspect: Intercept invocation
    Aspect->>Handler: Start Observation
    Aspect->>Method: Invoke target method
    Method-->>Aspect: Result or exception
    Aspect->>Handler: Stop Observation / record error
    Aspect-->>Caller: Return result or rethrow
~~~

Luồng tổng quát:
1. Caller gọi bean qua Spring proxy.
2. Aspect nhận diện annotation và tạo Observation.
3. Observation bắt đầu trước khi target method chạy.
4. Method thực thi trong scope Observation.
5. Kết quả hoặc exception được ghi nhận.
6. Observation dừng sau invocation.
7. Handlers cập nhật metrics/tracing theo cấu hình.

Tên và key-values cụ thể do annotation, convention và implementation quyết định. Hãy quan sát telemetry thực tế thay vì giả định mọi version phát cùng bộ tags.

## 4. AOP proxy và những giới hạn quan trọng

Annotation dựa trên proxy chỉ hoạt động khi lời gọi đi qua proxy. Đây là điều kiện dễ bị bỏ qua.

### 4.1. Self-invocation

~~~java
@Service
public class InvoiceService {

    public void closePeriod() {
        calculateTotals(); // Gọi nội bộ trên this, bỏ qua proxy.
    }

    @Observed(name = "invoice.calculate-totals")
    public void calculateTotals() {
        // Business calculation.
    }
}
~~~

Trong proxy-based AOP, lời gọi calculateTotals từ closePeriod đi trực tiếp trên target object và không qua proxy. Aspect có thể không được kích hoạt. Cách khắc phục thường là chuyển method được instrument sang một Spring bean khác và gọi qua bean boundary. Tránh inject chính bean vào chính nó chỉ để vượt qua self-invocation vì dễ tạo dependency cycle và làm thiết kế khó hiểu.

### 4.2. Method visibility và proxy type

Khả năng intercept method phụ thuộc Spring AOP proxy strategy, interface/class proxy, final class/method và version framework. Với class-based proxy, final method không thể override để intercept; private method không phải điểm join point thông thường của Spring proxy AOP.

Đặt annotation trên public service methods được gọi từ bean khác là cách dễ dự đoán nhất. Kiểm tra cấu hình proxy và method thực tế khi annotation không phát telemetry.

### 4.3. Bean phải do Spring quản lý

Nếu tạo service bằng new OrderService() thay vì inject bean từ ApplicationContext, Spring proxy/aspect không bao quanh instance đó. Annotation không được xử lý. Các service cần instrumentation phải được tạo và quản lý qua Spring container.

## 5. Observation metadata và cardinality

Observation có thể mang low-cardinality và high-cardinality key-values. Hai nhóm phục vụ các handlers khác nhau.

| Loại | Mục đích | Ví dụ |
| --- | --- | --- |
| Low-cardinality | Metrics và tracing | channel=web, operation=checkout |
| High-cardinality | Trace metadata chi tiết | order.reference đã được duyệt |
| Không nên thu thập | Secret/PII hoặc giá trị động không cần thiết | token, email, raw payload |

Annotation có thể hỗ trợ khai báo metadata theo các thuộc tính mà version cung cấp; cú pháp chính xác cần kiểm tra theo Micrometer version. Không tự giả định mọi annotation version có cùng attributes.

### 5.1. Low-cardinality

Các tag low-cardinality phải có tập giá trị nhỏ và hữu hạn:
- payment.method: card, bank-transfer, wallet;
- order.channel: web, mobile, partner;
- operation.result: accepted, rejected.

Không dùng customer ID, order ID, request ID, email hoặc raw URL làm metric tag. Số giá trị tăng theo traffic sẽ làm time series bùng nổ.

### 5.2. High-cardinality

High-cardinality metadata có thể hữu ích trong trace để điều tra một operation cụ thể, nhưng vẫn làm tăng payload/indexing cost và có thể lộ thông tin. Chỉ thêm field thực sự cần, giới hạn độ dài và được privacy review. Không đưa toàn bộ method arguments vào Observation context.

### 5.3. Đừng ghi payload tự động

Method arguments có thể chứa request body, payment details hoặc personal data. Tránh annotation/aspect tự serialize mọi argument/result vào tags. Chọn vài metadata đã chuẩn hóa và được phép.

## 6. Metrics và tracing từ cùng một annotation

Khi Observation có cả meter và tracing handlers:
- metrics có thể tổng hợp count/duration theo operation và low-cardinality tags;
- tracing handler có thể tạo span cho từng invocation được recording;
- exception/outcome có thể được ghi nhận theo convention;
- trace context hiện hành có thể làm parent cho service span.

Sampling áp dụng cho traces, không nên được dùng để quyết định request metrics có được ghi nhận hay không. Một method có thể được đo trong metrics dù trace của request bị sampler drop.

### 6.1. Ví dụ truy vấn metrics

Tên meter thực tế phụ thuộc Observation convention và registry. Nếu timer của application observation được export với tên application.task hoặc orders.create theo naming policy, hãy kiểm tra /actuator/metrics để lấy meter name thật trước khi tạo dashboard.

Ví dụ PromQL tổng quát cho timer đã được export thành histogram:

~~~promql
sum by (operation) (
  rate(application_observation_seconds_count[5m])
)
~~~

p95 latency nếu histogram và label tương ứng được bật:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, operation) (
    rate(application_observation_seconds_bucket[5m])
  )
)
~~~

Đây là query minh họa; không giả định meter name hoặc label operation mặc định của mọi version. Xem scrape output và điều chỉnh.

### 6.2. Không nhân đôi metrics bằng annotation lồng nhau

Nếu service method A gọi service method B và cả hai đều được instrument, metrics ghi nhận hai operations. Đây có thể là chủ đích để phân rã thời gian. Tuy nhiên, không thêm cùng một Observation ở aspect, wrapper và method body nếu chúng mô tả cùng boundary.

## 7. Exception và outcome

Observation thường dừng khi method kết thúc, dù kết quả thành công hay ném exception. Exception có thể được ghi nhận vào Observation và tracing span theo handler. Cần xác minh semantics:
- exception được ném ra khỏi method;
- exception được catch và chuyển thành business result;
- validation failure có phải error telemetry hay outcome nghiệp vụ;
- exception xảy ra ở child operation nhưng được xử lý ở parent.

Nếu method catch exception rồi trả fallback, aspect có thể chỉ thấy method kết thúc bình thường. Khi cần phản ánh failure, record outcome rõ ràng bằng convention/custom Observation thay vì mong aspect suy ra exception đã bị xử lý.

~~~java
@Observed(name = "payment.authorize")
public PaymentResult authorize(PaymentCommand command) {
    try {
        return gateway.authorize(command);
    } catch (GatewayUnavailableException ex) {
        log.warn("Payment gateway unavailable");
        throw ex;
    }
}
~~~

Không ghi exception message chứa token, account details hoặc dữ liệu nhạy cảm vào tags.

## 8. Kết hợp @Observed với @Transactional và @Async

Các annotation có mục đích khác nhau:
- @Observed: tạo Observation cho method invocation.
- @Transactional: quản lý transaction boundary.
- @Async: chuyển invocation sang executor.

Có thể kết hợp chúng, nhưng thứ tự advisor/interceptor ảnh hưởng scope. Ví dụ Observation bên ngoài transaction có thể bao gồm thời gian bắt đầu/commit transaction; Observation bên trong có thể chỉ đo phần method body tùy advisor ordering.

~~~java
@Service
public class SettlementService {

    @Observed(name = "settlement.execute")
    @Transactional
    public void settle(SettlementCommand command) {
        // Update ledger and settlement state.
    }
}
~~~

Không mặc định suy ra transaction duration từ method Observation nếu chưa xác định advisor order và transaction completion behavior. Nếu commit xảy ra khi transaction interceptor hoàn tất sau method body, observation boundary tùy thứ tự advisor có thể bao gồm hoặc không bao gồm commit.

### 8.1. @Async

~~~java
@Async("applicationTaskExecutor")
@Observed(name = "report.generate")
public CompletableFuture<Report> generateReport() {
    return CompletableFuture.completedFuture(buildReport());
}
~~~

Việc kết hợp phụ thuộc proxy chain và cách framework instrument asynchronous return values. Kiểm tra span có bao trùm phần thực thi thực tế hay chỉ thời gian method tạo Future. Dùng executor context propagation để giữ tracing/MDC đúng ở worker.

### 8.2. Reactive return types

Với Mono/Flux, method có thể trả publisher trước khi pipeline thực sự chạy. Nếu Observation aspect chỉ bao quanh thời gian tạo publisher, duration có thể không phản ánh thời gian subscription/terminal signal. Dùng reactive instrumentation/context propagation phù hợp và kiểm tra lifecycle tới complete/error/cancel. Không áp dụng giả định synchronous method cho reactive pipeline.

## 9. Annotation và custom Observation

@Observed phù hợp khi cần đánh dấu operation ổn định. Nếu cần metadata động có kiểm soát, business-specific event hoặc lifecycle phức tạp, custom Observation API có thể rõ ràng hơn.

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PricingService {
    private final ObservationRegistry registry;

    public PricingService(ObservationRegistry registry) {
        this.registry = registry;
    }

    public Price calculate(PriceRequest request) {
        return Observation.createNotStarted("pricing.calculate", registry)
                .lowCardinalityKeyValue("pricing.channel", request.channel())
                .observe(() -> calculateInternal(request));
    }

    private Price calculateInternal(PriceRequest request) {
        // Calculate price.
        return new Price(100);
    }
}
~~~

Ví dụ giả định channel được validate thành tập hữu hạn trước khi đưa vào low-cardinality tag. Nếu channel đến trực tiếp từ caller, chuẩn hóa/allowlist trước.

### 9.1. Custom aspect

Chỉ viết aspect riêng khi cần behavior mà @Observed/Observation API không đáp ứng. Custom aspect phải:
- xác định rõ method pointcut;
- tránh intercept cùng method hai lần với ObservedAspect;
- giữ nguyên return value/exception;
- đóng Observation trong mọi nhánh;
- xử lý checked exceptions;
- không serialize arguments/results mặc định;
- kiểm thử proxy order và async behavior.

Nếu chỉ cần một Observation quanh method, ưu tiên annotation/aspect có sẵn thay vì tạo framework riêng.

## 10. Kiểm thử annotation observability

Cần test riêng annotation activation, AOP proxy, Observation lifecycle, metrics/tracing handlers và exception behavior.

### 10.1. Test ObservationRegistry

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ServiceObservationTest {
    @Test
    void recordsObservationLifecycle() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted("orders.create", registry)
                .lowCardinalityKeyValue("order.channel", "web")
                .observe(() -> { });

        assertThat(registry.getCompletedObservationContexts()).hasSize(1);
    }
}
~~~

Test này kiểm tra Observation API trực tiếp, không chứng minh annotation AOP được bật.

### 10.2. Integration test qua Spring proxy

Tạo SpringBootTest với service bean được inject qua ApplicationContext, gọi method annotated và dùng test Observation handler/registry để xác minh observation bắt đầu và kết thúc. Gọi method qua bean proxy, không new instance thủ công.

Test thêm self-invocation: một public method gọi method annotated nội bộ. Xác minh behavior đúng với proxy strategy đang dùng; chuyển method sang bean riêng nếu cần interception.

### 10.3. Test exception

Cho method ném exception có kiểm soát. Assert exception vẫn được propagate theo contract và Observation được dừng, error được ghi nhận theo handler. Sau exception, gọi method khác và xác minh current observation/span context đã được restore.

### 10.4. Test metrics và tracing riêng

- MeterRegistry: xác minh timer/count và low-cardinality tags.
- Tracing test exporter: xác minh span name, parent relationship và error status.
- Log appender: xác minh traceId/spanId trong MDC nếu logging correlation được bật.
- Sampling test: không dùng việc thiếu span làm bằng chứng annotation không chạy; metrics/Observation có thể vẫn hoạt động.

## 11. Troubleshooting annotation trên service method

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| @Observed không tạo telemetry | Aspect/annotation support chưa bật | Kiểm tra dependency, property và auto-configuration version |
| Chỉ metrics có, không có span | Tracing handler/bridge/sampler/exporter thiếu | Kiểm tra tracing pipeline |
| Method nội bộ không được instrument | Self-invocation bỏ qua proxy | Chuyển method sang bean riêng |
| Bean tự tạo bằng new không có Observation | Không đi qua Spring proxy | Inject bean từ ApplicationContext |
| Final/private method không intercept | Proxy strategy/visibility limitation | Dùng public non-final method qua proxy |
| Observation name không như mong đợi | Convention/name config khác | Kiểm tra annotation và completed context |
| Tag xuất hiện trong metrics dù không muốn | Key-value được khai báo low-cardinality | Chuyển/loại bỏ metadata, review convention |
| Cardinality tăng theo request | Tag/name chứa ID hoặc URL động | Dùng tên ổn định và allowlist |
| Exception không được ghi nhận | Method catch rồi trả fallback | Record outcome/error rõ ràng |
| @Async span quá ngắn | Chỉ đo method tạo Future | Kiểm tra async instrumentation/lifecycle |
| Mono/Flux duration quá ngắn | Đo publisher assembly thay vì subscription | Dùng reactive observation integration |
| Có hai spans giống nhau | Aspect custom và ObservedAspect cùng intercept | Chọn một instrumentation owner |
| Context sai sau method | Scope không được đóng/restored | Kiểm tra finally và handler lifecycle |

### 11.1. Quy trình điều tra

1. Xác minh service là Spring bean.
2. Kiểm tra caller gọi qua proxy hay self-invocation.
3. Kiểm tra annotation support và ObservationRegistry.
4. Quan sát completed Observation context.
5. Kiểm tra MeterRegistry và Tracing handlers độc lập.
6. Kiểm tra sampler/exporter nếu span đã tạo nhưng không thấy ở backend.
7. Kiểm tra tags, naming và cardinality.
8. Test exception, async/reactive completion và context restoration.

## 12. Production checklist

| Tiêu chí | Bằng chứng |
| --- | --- |
| Annotation support được bật | Version/property/AOP config đã xác minh |
| Service bean qua proxy | Integration test gọi qua Spring context |
| Operation name ổn định | Không chứa ID động |
| Metrics low-cardinality | Tags là tập giá trị hữu hạn |
| Tracing bridge hoạt động | Span xuất hiện khi sampled |
| Parent context đúng | Service span là child/link phù hợp |
| Exception semantics rõ | Error/outcome được ghi nhận |
| Self-invocation được xử lý | Method boundary nằm ở bean phù hợp |
| Async/reactive được kiểm thử | Duration bao phủ execution lifecycle |
| Không duplicate instrumentation | Một aspect cho một method boundary |
| Privacy được kiểm soát | Không serialize arguments/secrets |
| Scope được restore | Không rò rỉ context sau invocation |

## 13. Bài thực hành: instrument service method trong order-service

**Bối cảnh:** order-service có service methods createOrder, calculatePricing và reserveInventory. Đội vận hành cần biết operation nào chậm, metrics nhóm theo operation và traces liên kết với HTTP request.

**Nhiệm vụ:**

1. Bật Actuator, AOP/Observed annotation support theo Spring Boot version.
2. Đánh dấu createOrder bằng @Observed với tên ổn định.
3. Gọi service qua Spring bean proxy và xác minh Observation được tạo.
4. Tạo nested operation calculatePricing và kiểm tra span hierarchy.
5. Bổ sung low-cardinality tag channel với allowlist.
6. Không đưa orderId/customerId/request body vào metric tags.
7. Tạo exception path và xác minh error được ghi nhận, exception vẫn propagate.
8. Kết hợp @Transactional và xác định Observation có bao gồm transaction completion theo advisor order.
9. Kết hợp @Async hoặc reactive return type nếu ứng dụng dùng; kiểm tra duration tới task completion/terminal signal.
10. Thử self-invocation và chuyển boundary sang bean riêng để xác minh proxy behavior.
11. Kiểm tra không có duplicate spans khi custom aspect và @Observed cùng tồn tại.
12. Viết runbook cho missing observation, missing span, cardinality tăng và async span duration sai.

**Kết quả mong đợi:** service methods có Observation/traces rõ ràng, metrics với tags an toàn, test proxy/exception/async và hướng dẫn troubleshooting.

## 14. Ghi nhớ

Annotation trên service method giúp khai báo ranh giới nghiệp vụ cần quan sát. @Observed có thể tạo Micrometer Observation khi annotation support và Spring AOP proxy được cấu hình đúng. Observation handlers quyết định metrics/tracing được xuất; tracing bridge/exporter không tự thay thế annotation aspect.

Gọi method qua Spring bean proxy, tránh self-invocation và instance tự tạo. Dùng operation name ổn định, low-cardinality tags có tập giá trị hữu hạn và không ghi arguments/secrets vào telemetry. Với @Transactional, @Async và reactive return types, xác minh interceptor ordering và lifecycle thực tế. Kiểm thử cả proxy behavior, Observation context, metrics, spans, exceptions và context restoration. Metrics cho xu hướng, spans cho quan hệ giữa operations, logs cho sự kiện gắn correlation IDs.

**Tài liệu tham khảo:**
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot — AOP](https://docs.spring.io/spring-boot/reference/features/aop.html)
- [Micrometer Observation — Annotations](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [Micrometer Observation — Reference](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Tracing — Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Framework — AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)


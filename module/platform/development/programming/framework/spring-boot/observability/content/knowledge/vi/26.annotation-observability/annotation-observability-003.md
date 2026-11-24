# @Counted trong Spring Boot

Spring Boot applications thường cần biết một operation được gọi bao nhiêu lần. Metrics như request rate, số lần chạy job hoặc số lần gọi service method giúp theo dõi tải và phát hiện hành vi bất thường. Micrometer cung cấp annotation `@Counted` để đếm số lần một method được thực thi thông qua AOP instrumentation.

`@Counted` tạo Counter cho method invocation. Mỗi lần method được intercept, counter tăng; nếu method ném exception, invocation vẫn đã xảy ra và thường vẫn được tính. Annotation không tự định nghĩa business event thành công, không đo thời gian thực thi và không thay thế HTTP request metrics hoặc tracing spans.

Bài **“@Counted”** thuộc chương **Annotation observability** của module **SPRING_BOOT_OBSERVABILITY**. Module hướng dẫn thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. @Counted là gì?

`@Counted` là annotation của Micrometer dùng để đếm số lần method được gọi. Aspect tương ứng intercept method invocation và cập nhật Counter trong MeterRegistry.

```java
import io.micrometer.core.annotation.Counted;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    @Counted(value = "invoice.generate.calls",
             description = "Number of invoice generation method calls")
    public Invoice generate(String orderId) {
        // Generate invoice
        return new Invoice(orderId);
    }
}
```

Tên metric là `invoice.generate.calls` trong ví dụ. Registry có thể chuẩn hóa tên theo naming convention của backend. Mỗi lần invocation được intercept, Counter tăng một đơn vị.

Counter phù hợp để trả lời method được gọi bao nhiêu lần, tần suất operation tăng hay giảm, hoặc một scheduled task có đang chạy như dự kiến không. Counter là giá trị tích lũy, thường dùng rate/increase trong query để quan sát số lần gọi theo cửa sổ thời gian.

## 2. Dependency và bật counted aspect

`@Counted` không hoạt động chỉ vì annotation xuất hiện trong source. Cần có Micrometer annotation support và aspect được đăng ký trong application context.

Gradle ví dụ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
    implementation 'io.micrometer:micrometer-core'
}
```

Nếu BOM/starter đã cung cấp dependency, tránh khai báo trùng hoặc override version. Kiểm tra dependency tree để biết phiên bản Micrometer được quản lý.

Đăng ký aspect:

```java
import io.micrometer.core.aop.CountedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CountedConfiguration {

    @Bean
    CountedAspect countedAspect(MeterRegistry registry) {
        return new CountedAspect(registry);
    }
}
```

Khi aspect có mặt, Spring AOP có thể intercept các method được đánh dấu. Xác minh loại proxy và method visibility theo AOP configuration của ứng dụng. Không giả định Spring Boot tự đăng ký CountedAspect trong mọi cấu hình.

## 3. Annotation hoạt động qua AOP proxy

Spring annotation-based AOP thường dựa trên proxy. Lời gọi từ bean khác đi qua proxy có thể được intercept; lời gọi nội bộ từ method này sang method khác trong cùng object thường không đi qua proxy.

```java
@Service
public class ReportService {

    public void runDailyReport() {
        calculateTotals(); // Self-invocation: may bypass the proxy
    }

    @Counted("report.calculate.calls")
    public void calculateTotals() {
        // Calculate report totals
    }
}
```

Nếu `runDailyReport()` gọi `calculateTotals()` trực tiếp trên cùng instance, invocation có thể không được aspect intercept. Cách tổ chức dễ kiểm soát hơn là đưa operation được đếm sang một Spring bean riêng rồi gọi qua injected dependency.

```java
@Service
public class ReportCalculationService {

    @Counted("report.calculate.calls")
    public void calculateTotals() {
        // Calculate report totals
    }
}

@Service
public class ReportService {

    private final ReportCalculationService calculationService;

    public ReportService(ReportCalculationService calculationService) {
        this.calculationService = calculationService;
    }

    public void runDailyReport() {
        calculationService.calculateTotals();
    }
}
```

Không gọi method qua `this` để mong đi qua proxy. Cũng không tự inject bean vào chính nó chỉ để vượt qua self-invocation nếu có thể tách trách nhiệm rõ ràng.

## 4. @Counted đếm invocation, không phải kết quả nghiệp vụ

Giả sử `chargeCard()` được gọi 100 lần: 92 lần thành công, 5 lần bị từ chối do insufficient funds và 3 lần timeout. Counter `payment.charge.calls` có thể ghi nhận 100 invocations; nó không tự cho biết 92 lần thành công.

| Metric | Ý nghĩa |
| --- | --- |
| `payment.charge.calls` | Số lần method được gọi |
| `payment.charge.success` | Số operation thành công, nếu ứng dụng ghi riêng |
| `payment.charge.failure` | Số operation thất bại, nếu ứng dụng ghi riêng |
| `payment.charge.duration` | Thời gian thực thi, thường dùng Timer |

Đừng đặt tên invocation counter là `payment.success` nếu nó tăng cả khi method ném exception. Tên metric phải mô tả đúng semantics.

Nếu cần đếm business outcome, ghi Counter tại điểm outcome đã được xác định:

```java
@Service
public class PaymentService {

    private final Counter successfulPayments;

    public PaymentService(MeterRegistry registry) {
        this.successfulPayments = Counter.builder("payment.operations")
                .tag("outcome", "success")
                .register(registry);
    }

    public Receipt charge(Command command) {
        Receipt receipt = performCharge(command);
        successfulPayments.increment();
        return receipt;
    }
}
```

Đây là cách ghi business outcome tường minh. Với outcome khác, dùng tập tag values hữu hạn như success, declined, error; không dùng exception message hay customer ID làm tag.

## 5. Đếm exception và failure

Một invocation có thể hoàn tất bình thường hoặc ném exception. `@Counted` đếm method call theo semantics của aspect; không tự phân loại exception thành các loại failure business.

Nếu cần tách số invocation và số lỗi, có thể kết hợp `@Counted` để đếm tổng method calls, Counter riêng tại exception/error handling boundary để đếm failure, Timer để đo thời gian, trace span để xem nguyên nhân và logs có trace/span correlation để đọc exception details.

Ví dụ:

```java
@Service
public class ShippingService {

    private final Counter failures;

    public ShippingService(MeterRegistry registry) {
        this.failures = Counter.builder("shipping.create.failures")
                .register(registry);
    }

    public Shipment create(CreateShipmentCommand command) {
        try {
            return callCarrier(command);
        }
        catch (CarrierException ex) {
            failures.increment();
            throw ex;
        }
    }
}
```

Đặt counter tại boundary có thể xác định failure chính xác. Nếu exception bị catch và retry ở nhiều lớp, cần quyết định đếm mỗi attempt hay chỉ final failure; nếu không, metric có thể bị hiểu sai.

## 6. Tags và cardinality

`@Counted` hỗ trợ cấu hình tags qua annotation attributes tùy phiên bản Micrometer. Chỉ dùng tags có tập giá trị hữu hạn, ổn định.

```java
@Counted(
    value = "catalog.lookup.calls",
    extraTags = {"operation", "lookup", "channel", "web"}
)
public Product lookup(String productCode) {
    // Lookup product
}
```

Tags operation=lookup và channel=web là giá trị tĩnh. Không đưa tham số method như productCode vào tag. Mỗi product code có thể tạo một time series riêng, khiến cardinality tăng theo số sản phẩm.

| Tag phù hợp | Tag không phù hợp |
| --- | --- |
| operation=lookup | product.id=SKU-123 |
| channel=web/mobile | user.id |
| result=success/failure | request.id |
| region=ap-southeast-1 | raw URL/query |
| payment.type=card/bank | exception.message |

Nếu cần phân tích theo identifier, cân nhắc logs/traces với redaction và access control. Không biến metric registry thành kho lưu dữ liệu theo từng entity.

## 7. @Counted và @Timed khác nhau thế nào?

`@Counted` đếm số invocation. `@Timed` đo thời gian và cũng cung cấp count của các timing samples. Hai annotation có thể bổ sung nhau nhưng không nên gắn tùy tiện lên cùng method mà chưa hiểu cách aspects và registry tạo meters.

| Tiêu chí | @Counted | @Timed |
| --- | --- | --- |
| Mục tiêu chính | Đếm invocation | Đo duration và phân phối thời gian |
| Count | Có | Có, số timing samples |
| Total time | Không | Có |
| Histogram/percentiles | Không phải mục tiêu chính | Có thể cấu hình |
| Phân tích latency | Không | Có |
| Đếm method calls đơn giản | Phù hợp | Có thể dùng nếu cũng cần duration |

Nếu chỉ cần số lần gọi, dùng `@Counted`. Nếu cần latency, dùng `@Timed` hoặc Observation/Timer phù hợp. Tránh tạo hai counters có cùng ý nghĩa dẫn tới double-count trong dashboard.

## 8. @Counted và Observation

Micrometer Observation cung cấp mô hình chung cho metrics và tracing. `@Counted` là instrumentation chuyên biệt cho method invocation; nó không tự tạo distributed span hay propagate trace context.

Có thể kết hợp `@Counted` cho số lần gọi method, `@Observed` hoặc Observation API cho operation cần metrics và tracing, `@Timed` cho latency, và logs trong active trace context cho chi tiết sự kiện.

Không gắn mọi annotation lên mọi method. Chọn đúng signal và boundary để tránh duplicate metrics, span lồng nhau không cần thiết và overhead.

## 9. Counter lifecycle và registry

`CountedAspect` sử dụng `MeterRegistry` để đăng ký/cập nhật Counter. Trong Spring Boot, ưu tiên MeterRegistry do Boot auto-configure để meters đi theo registry/exporter đã cấu hình.

Nếu tạo MeterRegistry riêng không được kết nối với exporter, counter có thể tăng trong registry đó nhưng không xuất hiện ở backend đang xem.

- Dùng tên meter nhất quán theo domain/operation.
- Giữ tag keys ổn định.
- Không đăng ký lại cùng meter với metadata mâu thuẫn.
- Không tạo registry mới cho mỗi request.
- Kiểm tra filters có loại meter này không.
- Kiểm tra exporter/Actuator endpoint riêng nếu meter không xuất hiện.

## 10. Kiểm tra metric qua Actuator

Nếu Actuator metrics endpoint được expose và có quyền truy cập, có thể kiểm tra meter:

```text
GET /actuator/metrics
GET /actuator/metrics/invoice.generate.calls
```

Endpoint có thể chuẩn hóa dấu chấm hoặc tên metric theo naming convention. Cấu hình exposure và security phải phù hợp môi trường; không mở rộng management endpoints công khai chỉ để debug.

Response của metrics endpoint có thể cho thấy meter name, measurements và available tag keys/values. Dùng nó để xác minh counter được đăng ký và tăng sau invocation.

## 11. Kiểm thử @Counted

Integration test nên xác minh aspect thực sự intercept method qua Spring bean proxy.

```java
@SpringBootTest
class InvoiceServiceTests {

    @Autowired
    InvoiceService invoiceService;

    @Autowired
    MeterRegistry registry;

    @Test
    void countsInvocations() {
        Counter counter = registry.find("invoice.generate.calls")
                .counter();

        double before = counter == null ? 0 : counter.count();

        invoiceService.generate("order-1");
        invoiceService.generate("order-2");

        double after = registry.get("invoice.generate.calls")
                .counter()
                .count();

        assertThat(after - before).isEqualTo(2.0);
    }
}
```

Đây là ví dụ cấu trúc test; cần bổ sung imports, fixture và cấu hình ứng dụng tương ứng. Nếu counter chưa tồn tại trước invocation, lấy baseline bằng 0; khi test chạy song song, dùng meter name/tag riêng hoặc registry test cô lập để tránh nhiễu.

Các trường hợp nên test: method được gọi qua Spring bean proxy; nhiều invocation; exception; self-invocation; tags; aspect không đăng ký hai lần; meter xuất hiện trong đúng registry. Với async/reactive method, xác minh semantics annotation trong version cụ thể; không giả định method return là task completion.

## 12. Những giới hạn thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Annotation không tăng counter | Thiếu CountedAspect hoặc AOP proxy | Đăng ký aspect và kiểm tra proxy |
| Một số call không được đếm | Self-invocation hoặc object ngoài Spring | Gọi qua Spring bean proxy |
| Counter tăng gấp đôi | Aspect/bean/interceptor trùng | Kiểm tra cấu hình AOP |
| Counter không có ở backend | Dùng registry khác hoặc exporter/filter | Kiểm tra MeterRegistry và filters |
| Cardinality tăng mạnh | Tag chứa method argument/dynamic value | Chuyển sang allowlist/static tags |
| Success count sai | Dùng invocation counter làm business success | Đếm tại outcome boundary |
| Không có latency | Chỉ dùng @Counted | Dùng @Timed hoặc Observation |
| Async task đo sai boundary | Method return trước khi task hoàn tất | Tạo Observation/Timer cho task execution |

## 13. Bài thực hành: đếm method calls

Thực hiện trong local/test:

1. Tạo Spring Boot service có Actuator, AOP và Micrometer.
2. Đăng ký CountedAspect với MeterRegistry.
3. Đánh dấu method generate invoice bằng `@Counted`.
4. Gọi method qua bean được inject từ Spring context.
5. Kiểm tra counter tăng đúng số invocation.
6. Tạo invocation ném exception và xác minh count theo semantics của aspect.
7. Thêm static tags như operation và channel.
8. Thử self-invocation để nhận diện giới hạn proxy.
9. So sánh `@Counted` với `@Timed` khi cần latency.
10. Xác minh metric có trong Actuator và exporter backend.
11. Kiểm tra không có ID động hoặc dữ liệu nhạy cảm trong tags.

Kết quả mong đợi: method invocation được đếm đúng, metric name/tags ổn định, business success/failure được biểu diễn bằng metrics riêng nếu cần và không có duplicate counters.

## 14. Câu hỏi tự kiểm tra

1. `@Counted` đo method invocation hay business success?
2. Thành phần nào intercept method có annotation?
3. Vì sao annotation không hoạt động chỉ bằng cách thêm vào source?
4. Self-invocation ảnh hưởng Spring AOP proxy thế nào?
5. Một method ném exception có phải là invocation không?
6. Khi nào nên ghi business success counter riêng?
7. Vì sao không đưa method arguments vào extra tags?
8. `@Counted` khác `@Timed` thế nào?
9. `@Counted` có tự tạo distributed span không?
10. Vì sao nên dùng MeterRegistry do Spring Boot quản lý?
11. Làm sao xác minh counter qua Actuator?
12. Test nào chứng minh aspect thực sự intercept bean call?
13. Vì sao đếm mỗi retry attempt khác đếm final business outcome?
14. Async method có thể có boundary đo khác với task completion thế nào?

## Tài liệu tham khảo

- [Micrometer — @Counted annotation](https://docs.micrometer.io/micrometer/reference/concepts/counters.html): Counter semantics và annotation-based counting.
- [Micrometer — CountedAspect Javadoc](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/aop/CountedAspect.html): AOP aspect cho @Counted.
- [Spring Boot — AOP](https://docs.spring.io/spring-boot/reference/features/aop.html): AOP auto-configuration và proxy behavior.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistry, Actuator metrics và registry integration.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer semantics và khác biệt với Counter.
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html): Observation API cho metrics/tracing correlation.

## Kết luận

**`@Counted` là cách đơn giản để đếm số lần một Spring bean method được gọi qua AOP instrumentation.** Cần đăng ký `CountedAspect`, dùng MeterRegistry do ứng dụng quản lý và bảo đảm lời gọi đi qua proxy. Counter phản ánh invocation; nó không tự phân biệt business success/failure và không đo latency.

Đặt tên metric đúng semantics, chỉ dùng tags cardinality thấp và ghi business outcomes tại boundary phù hợp. Khi cần duration hoặc distributed tracing, kết hợp Timer/Observation thay vì kỳ vọng `@Counted` cung cấp tất cả signals. Kiểm thử proxy, exception, self-invocation và exporter để đảm bảo số liệu phản ánh đúng hoạt động của ứng dụng.


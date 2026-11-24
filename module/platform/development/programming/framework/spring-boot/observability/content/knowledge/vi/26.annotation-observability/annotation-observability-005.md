# @NewSpan trong Spring Boot observability

Trong chương **Annotation observability** của module **SPRING_BOOT_OBSERVABILITY**, @NewSpan là annotation của Micrometer Tracing dùng để đánh dấu một method cần tạo span mới khi method được gọi qua tracing/AOP integration đã cấu hình. Span biểu diễn một operation có thời gian bắt đầu/kết thúc, tên, context và các thuộc tính; khi có active trace, span mới thường được tạo trong trace hiện tại để bổ sung chi tiết cho distributed trace.

@NewSpan hữu ích khi instrumentation tự động của HTTP, database hoặc messaging chưa mô tả đủ một bước nghiệp vụ. Ví dụ, một method tính phí, kiểm tra hạn mức hoặc xác minh chính sách có thể cần span riêng để quan sát latency và lỗi. Annotation không tự gửi trace tới backend: ứng dụng vẫn cần Micrometer Tracing bridge, tracer implementation, sampling policy và exporter phù hợp.

Trong module **SPRING_BOOT_OBSERVABILITY**, annotation-based tracing là một cách bổ sung cho Micrometer Observation API. Chọn span boundary có chủ đích: span nên mô tả operation có ý nghĩa, không phải mọi method nhỏ. Quá nhiều span làm trace khó đọc, tăng chi phí và có thể để lộ dữ liệu nếu attributes không được kiểm soát.

## 1. Span là gì và @NewSpan làm gì?

Một distributed trace thường gồm nhiều spans liên kết theo quan hệ parent-child hoặc span links. Mỗi span mô tả một operation, có start/end time và context như Trace ID, Span ID, parent context, attributes và status.

```text
HTTP server span: POST /orders
    |
    +--> order.validate
    |
    +--> order.calculate-price
    |       |
    |       +--> HTTP client span: pricing-service
    |
    +--> database span: INSERT order
```

Spring/Micrometer có thể tự tạo spans cho một số điểm tích hợp như HTTP server/client hoặc database tùy dependency/version. @NewSpan cho phép đánh dấu thêm một method nghiệp vụ để tạo span tại boundary đó.

Điều annotation không làm:

- Không tự bật distributed tracing nếu ứng dụng chưa cấu hình tracing.
- Không tự tạo exporter hoặc endpoint OTLP.
- Không bảo đảm mọi lần gọi method đều tạo span nếu lời gọi không đi qua AOP proxy hoặc integration cần thiết.
- Không thay thế propagation context qua HTTP/JMS/executor.
- Không biến method thành transaction hoặc retry boundary.
- Không bảo đảm span được lưu nếu sampling loại trace hoặc export thất bại.

## 2. Dependency và phiên bản

Trong Spring Boot, Micrometer Tracing có thể được cấu hình bằng bridge tương ứng, ví dụ OpenTelemetry hoặc Brave, cùng exporter tương ứng. Spring Boot BOM nên quản lý các phiên bản tương thích.

Ví dụ dependency cho ứng dụng dùng Actuator, Micrometer Tracing với OpenTelemetry bridge và OTLP exporter:

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

Đây là ví dụ dependency set; cấu hình auto-configuration cụ thể thay đổi theo Spring Boot version. Không trộn Brave bridge và OpenTelemetry bridge trong cùng tracing setup nếu không có kiến trúc tích hợp rõ ràng. Kiểm tra documentation/metadata của version đang dùng trước khi chọn import hoặc annotation package.

@NewSpan thường được dùng từ package io.micrometer.tracing.annotation.NewSpan trong Micrometer Tracing. Hãy xác minh package/API theo dependency thực tế, vì annotation và khả năng intercept có thể khác giữa các thế hệ Spring Cloud Sleuth và Micrometer Tracing.

## 3. Cấu hình annotation interception

Annotation chỉ có tác dụng khi có thành phần đọc annotation và intercept method invocation. Trong một số cấu hình Spring Boot/Micrometer Tracing, annotation support được auto-configure khi các dependency và AOP infrastructure phù hợp hiện diện; ở cấu hình khác, cần bật annotation handler/AOP integration theo hướng dẫn của version.

Một cấu hình minh họa với Spring AOP:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy
class TracingAopConfiguration {
}
```

Chỉ bật @EnableAspectJAutoProxy không tự cung cấp Micrometer span aspect nếu thư viện/integration tương ứng chưa có. Cần xác minh annotation aspect/handler đã được đăng ký. Không tự tạo aspect thứ hai cùng intercept @NewSpan khi auto-configuration đã đăng ký, nếu không có thể sinh span lồng nhau ngoài ý muốn.

Nếu method được gọi nội bộ từ method khác trong cùng bean (self-invocation), lời gọi có thể bỏ qua Spring proxy và annotation không được intercept. Đưa operation sang một Spring bean khác hoặc gọi qua proxy theo thiết kế rõ ràng nếu cần AOP interception.

## 4. Dùng @NewSpan trên method nghiệp vụ

Ví dụ đánh dấu bước tính giá trong service:

```java
import io.micrometer.tracing.annotation.NewSpan;
import org.springframework.stereotype.Service;

@Service
class PricingService {

    @NewSpan("order.calculate-price")
    Price calculate(Order order) {
        return pricingEngine.calculate(order);
    }
}
```

Tên span nên mô tả operation ngắn gọn, ổn định và có ý nghĩa. Tránh tạo tên span từ order ID, username, URL đầy đủ hoặc input tự do; span name có thể được dùng trong query/indexing và cần giữ cardinality thấp.

Nếu annotation không nhận tham số name trong phiên bản cụ thể, dùng đúng API được hỗ trợ hoặc default name convention. Không copy ví dụ giữa các version mà không kiểm tra compile-time API.

### Span name và operation boundary

Một span nên bao trùm một operation đủ đáng kể để đo latency hoặc hiểu quan hệ trong trace. Ví dụ:

- order.validate — kiểm tra quy tắc đơn hàng.
- order.calculate-price — tính giá.
- payment.authorize — gọi nghiệp vụ ủy quyền thanh toán.
- inventory.reserve — giữ tồn kho.
- invoice.render — tạo tài liệu hóa đơn.

Không cần tạo span riêng cho getter, setter, mapping đơn giản hoặc mọi private helper. Span quá nhỏ làm tăng overhead và khiến trace bị phân mảnh.

## 5. Tạo span từ method và đặt attributes

@NewSpan có thể hỗ trợ khai báo tên span và các tham số được đưa vào span theo annotation/API của version. Tuy nhiên, không nên mặc định mọi method parameter đều an toàn để export. Với identifiers hoặc dữ liệu nhạy cảm, ưu tiên attributes được allowlist rõ ràng hoặc dùng Observation API để kiểm soát key-value.

Ví dụ dùng Observation API khi cần kiểm soát metadata rõ hơn:

```java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class OrderPolicyService {
    private final ObservationRegistry registry;

    OrderPolicyService(ObservationRegistry registry) {
        this.registry = registry;
    }

    PolicyResult evaluate(Order order, String channel) {
        return Observation.createNotStarted("order.policy.evaluate", registry)
                .lowCardinalityKeyValue("channel", normalize(channel))
                .observe(() -> policyEngine.evaluate(order));
    }

    private String normalize(String channel) {
        if ("mobile".equals(channel)) return "mobile";
        if ("partner".equals(channel)) return "partner";
        return "web";
    }
}
```

Observation phù hợp khi muốn cùng một instrumentation tạo metrics và tracing handlers theo convention. lowCardinalityKeyValue dành cho dimension có tập giá trị hữu hạn. Nếu cần một giá trị định danh chi tiết cho trace, phải đánh giá privacy, sampling và retention; không biến nó thành metric label.

## 6. Parent span và active trace context

Khi một HTTP server request đã mở trace context và method được gọi trong cùng execution context, span do @NewSpan tạo thường được liên kết với active span theo tracing integration. Trace có thể trông như sau:

```text
Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736
  Span: HTTP POST /orders
    Span: order.validate
    Span: order.calculate-price
      Span: HTTP GET pricing-service
    Span: database INSERT order
```

Nếu method được gọi khi không có active span, integration có thể tạo root span mới hoặc hành xử theo configuration. Không giả định span luôn có parent. Để liên kết qua service boundary, tracing propagator phải inject/extract context trong protocol tương ứng.

Một span annotation không tự truyền context sang thread pool, CompletableFuture, Reactor scheduler hoặc message broker. Các ranh giới bất đồng bộ cần context propagation riêng; nếu không, span có thể mất parent hoặc log thiếu Trace ID.

## 7. Exception và span status

Khi method được intercept ném exception, tracing integration có thể ghi exception event và đánh dấu span error tùy handler/convention. Exception vẫn phải được xử lý theo semantics ứng dụng; annotation không tự retry, swallow exception hoặc thay đổi business result.

Ví dụ:

```java
@NewSpan("payment.authorize")
PaymentResult authorize(PaymentCommand command) {
    return paymentGateway.authorize(command);
}
```

Nếu paymentGateway ném exception, span có thể kết thúc với error status và exception event. Kiểm tra trace backend để xác nhận instrumentation/version thực sự ghi error. Không thêm exception message nguyên văn vào span name hoặc metric tag; message có thể chứa URL, dữ liệu người dùng hoặc token.

Nếu code bắt exception và trả fallback result, span có thể được đánh dấu thành công nếu instrumentation chỉ dựa trên exception thoát khỏi method. Nếu fallback là kết quả nghiệp vụ cần quan sát riêng, thêm outcome có cardinality thấp hoặc tạo Observation/business metric thể hiện fallback.

## 8. Async method và context propagation

Với @Async, executor hoặc CompletableFuture, method có thể chạy trên thread khác. ThreadLocal-based tracing context không tự động đi theo mọi executor. Cần dùng context propagation integration phù hợp với Spring/Micrometer và bảo đảm task decorator/accessor đã được cấu hình.

Ví dụ cấu hình executor có context-propagating task decorator trong Spring Framework version hỗ trợ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
class AsyncTracingConfiguration {

    @Bean(name = "applicationExecutor")
    ThreadPoolTaskExecutor applicationExecutor() {
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

Task phải thực sự được submit qua executor đã cấu hình. ContextPropagatingTaskDecorator chỉ capture/restore context mà accessor tương ứng đã đăng ký; không giả định nó tự truyền mọi ThreadLocal tùy ý. Kiểm tra Trace ID/Span ID trong logs và parent/link trong trace ở worker thread.

Với reactive code, Reactor Context và Micrometer context-propagation integration cần được cấu hình đúng. Không giữ span mở trong một thread rồi kỳ vọng callback chạy ở scheduler khác tự kế thừa context.

## 9. Sampling và chi phí span

@NewSpan tạo thêm span khi method được intercept, nhưng span có được export hay không còn phụ thuộc sampling và exporter pipeline. Head sampling có thể quyết định giữ hoặc loại trace từ đầu; tail sampling có thể được thực hiện ở collector/backend pipeline nếu kiến trúc hỗ trợ.

Một method được gọi rất thường xuyên có thể tạo lượng spans lớn. Trước khi gắn annotation, cân nhắc:

- Operation có đủ ý nghĩa để xuất hiện trong trace không?
- Span duration có giúp giải thích latency không?
- Đã có span tự động bao phủ cùng operation chưa?
- Attributes có cardinality và sensitivity phù hợp không?
- Sampling/export capacity có đáp ứng volume không?

Không dùng @NewSpan để thay thế metrics cho counter/rate. Span mô tả từng operation được chọn; metrics tổng hợp workload với chi phí thấp hơn cho dashboard dài hạn.

## 10. Khi nào dùng @NewSpan, @Observed hay Observation API?

| Cơ chế | Mục đích | Khi phù hợp |
| --- | --- | --- |
| @NewSpan | Tạo span mới quanh method qua tracing annotation integration | Muốn thêm một span cụ thể trong trace hiện tại |
| @Observed | Tạo Observation quanh method theo Micrometer observation aspect/convention | Muốn observation có thể phát sinh metrics và tracing handlers |
| Observation API | Tạo observation bằng code với lifecycle và metadata rõ ràng | Cần kiểm soát động, low/high-cardinality values hoặc scope |
| Tracer API | Tạo span trực tiếp theo tracing implementation | Cần thao tác span/context ở mức thấp và cụ thể |

Không bật nhiều cơ chế cùng bao quanh một method mà không có chủ ý. Ví dụ @NewSpan và @Observed cùng được intercept có thể tạo hai spans/observations lồng nhau, làm trace dài và metrics bị đếm khác mong đợi.

@Observed cũng cần observation annotation aspect được cấu hình; chỉ thêm annotation vào method không đảm bảo hoạt động ở mọi project. Kiểm tra AOP/proxy support và convention của version.

## 11. Những giới hạn AOP cần nhớ

Annotation-based instrumentation thường phụ thuộc proxy/interception. Các trường hợp dễ làm span không xuất hiện:

- Method được gọi nội bộ trong cùng bean (self-invocation).
- Object được tạo bằng new thay vì Spring container quản lý.
- Method hoặc class không thể được proxy theo cơ chế AOP đang dùng.
- Annotation aspect/handler chưa được đăng ký.
- Method chạy ở thread khác mà context không được truyền.
- Tracing chưa được cấu hình hoặc trace bị sampling loại.

Khi span thiếu, kiểm tra theo thứ tự: bean có do Spring quản lý không; call có đi qua proxy không; annotation integration có được bật không; active context có tồn tại không; sampling có giữ trace không; exporter/collector/backend có nhận dữ liệu không.

## 12. Kiểm thử @NewSpan

Một test nên xác minh span thực sự được tạo khi method được gọi qua Spring proxy, thay vì chỉ kiểm tra annotation tồn tại trên class.

Quy trình gợi ý:

1. Khởi tạo Spring application context với tracing test setup và in-memory/test span exporter phù hợp version.
2. Lấy service bean từ ApplicationContext thay vì tạo bằng new.
3. Gọi method qua bean proxy trong một active parent span nếu cần kiểm tra quan hệ parent-child.
4. Xác minh span name, parent context và start/end lifecycle.
5. Gọi method ném exception; kiểm tra error status/event theo convention.
6. Kiểm tra không có span duplicate khi nhiều annotation/aspect cùng được bật.
7. Với async, submit task qua executor đã cấu hình và xác minh context trong worker.
8. Không phụ thuộc vào việc trace được backend production lưu trong test; dùng test exporter hoặc observation handler có thể quan sát.

Các API của test span exporter thay đổi theo OpenTelemetry/Micrometer version. Chọn exporter/testing utility tương thích BOM, không sao chép import của version khác.

### Ma trận kiểm thử

| Kịch bản | Kết quả cần xác minh |
| --- | --- |
| Gọi Spring bean qua proxy | Span mới được tạo nếu integration bật |
| Gọi method nội bộ cùng bean | Xác nhận self-invocation có bỏ qua aspect không |
| Không có active span | Root/new span theo semantics cấu hình |
| Có active parent span | Child/link relationship đúng convention |
| Method ném exception | Span ghi error theo handler |
| Method chạy async | Context được capture/restore hoặc span link rõ ràng |
| Sampling loại trace | Không kết luận annotation hỏng chỉ vì backend không có span |
| Hai aspect cùng intercept | Không sinh duplicate spans ngoài ý muốn |
| Attribute chứa ID nhạy cảm | Không được export nếu không được policy cho phép |

## 13. Bài tập tình huống

Một developer thêm @NewSpan("order.calculate-price") vào method của OrderService. Khi chạy local, không thấy span mới. Method được gọi từ một method khác trong cùng class. Ứng dụng có Micrometer Tracing dependency và HTTP server spans vẫn xuất hiện bình thường.

**Câu hỏi:**

1. Vì sao có HTTP server span nhưng không có span từ @NewSpan?
2. Self-invocation ảnh hưởng thế nào tới Spring AOP proxy?
3. Nên xác minh annotation aspect/handler và bean lifecycle ra sao?
4. Nếu method được chuyển sang executor, cần kiểm tra thêm điều gì?
5. Có phải cứ thêm @NewSpan là span chắc chắn xuất hiện trong backend không?

**Gợi ý phân tích:**

- HTTP instrumentation có thể hoạt động độc lập với annotation interception. Dependency tracing không tự chứng minh @NewSpan aspect đã được đăng ký.
- Lời gọi nội bộ cùng bean có thể không đi qua Spring proxy, do đó aspect không chạy.
- Lấy bean từ ApplicationContext, gọi qua proxy, xác minh annotation integration/auto-configuration và kiểm tra version/package annotation.
- Async cần context propagation qua executor; nếu thiếu context, span có thể không có parent hoặc logs không có trace IDs.
- Sampling có thể loại trace và exporter/backend có thể lỗi. Dùng test exporter để tách lỗi annotation interception khỏi lỗi export.

### Checklist hoàn thành

| Nội dung | Có thể giải thích/kiểm tra |
| --- | --- |
| Vai trò @NewSpan | Tạo span quanh method khi annotation integration intercept |
| Micrometer Tracing | Có bridge, tracer và exporter phù hợp |
| AOP/proxy | Hiểu self-invocation và Spring-managed bean |
| Span naming | Tên ổn định, không chứa request/business IDs |
| Parent context | Span liên kết với active trace theo convention |
| Error handling | Biết exception ảnh hưởng span status như thế nào |
| Async/reactive | Có context propagation qua thread/scheduler |
| Sampling/export | Phân biệt span không được tạo, bị sampled out và export lỗi |
| Cardinality/privacy | Không đưa dữ liệu nhạy cảm vào attributes/tags |
| Alternative APIs | Biết khi nào dùng @Observed, Observation API hoặc Tracer |
| Testing | Kiểm tra span qua proxy và test exporter |

**Ghi nhớ:** @NewSpan giúp bổ sung một span quanh method nghiệp vụ khi Micrometer Tracing annotation integration và AOP interception đã được cấu hình. Annotation không tự bật tracing, exporter hoặc context propagation. Đặt span boundary có ý nghĩa, tên ổn định và attributes được kiểm soát; lưu ý self-invocation, Spring proxy, async/reactive context và sampling. Dùng Observation API hoặc @Observed khi cần lifecycle và metrics/tracing handlers có kiểm soát hơn, đồng thời kiểm thử bằng Spring bean proxy và test exporter để xác nhận span thực sự được tạo.

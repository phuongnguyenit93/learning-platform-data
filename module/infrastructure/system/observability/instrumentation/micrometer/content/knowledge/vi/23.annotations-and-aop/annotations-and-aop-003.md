# @Counted và cấu hình CountedAspect cho số lần thực thi

`@Counted` cho phép ghi nhận số lần một phương thức được gọi mà không phải tự viết `Counter.increment()` trong thân phương thức. Micrometer cung cấp `CountedAspect` để chặn lời gọi được đánh dấu, chạy logic nghiệp vụ rồi tăng counter tương ứng khi phương thức hoàn tất hoặc ném exception.

Annotation chỉ khai báo ý định đo lường; nó không tự hoạt động nếu không có AOP aspect xử lý. Trong ứng dụng Spring, cần thêm hỗ trợ Spring AOP, khai báo bean `CountedAspect` và bảo đảm lời gọi đi qua proxy của Spring. Khi cấu hình đúng, một counter có thể phân biệt lần gọi thành công và thất bại bằng các tag `result` và `exception`.

Trong module `OBSERVABILITY_INSTRUMENTATION_MICROMETER`, `@Counted` phù hợp để đếm số lần thực thi nghiệp vụ như kiểm tra đơn hàng, xử lý thanh toán hoặc nhận thông điệp. Nó chỉ đo số lần gọi; nếu cần đo thời lượng, hãy dùng `@Timed`, `Timer` hoặc Observation.

## 1. @Counted giải quyết vấn đề gì?

Nếu ghi counter thủ công, mỗi phương thức cần tự gọi `increment()` ở đúng vị trí. Khi có nhiều nhánh return hoặc exception, code dễ quên ghi nhận một số trường hợp:

```java
public void validateOrder(Order order) {
    validationCounter.increment();
    // Kiểm tra dữ liệu và có thể ném exception.
}
```

Nếu cần phân biệt thành công và thất bại, code thủ công còn phải quản lý thêm tag và đảm bảo không ghi hai lần. `@Counted` chuyển phần việc này cho aspect:

```java
@Counted("orders.validation.calls")
public void validateOrder(Order order) {
    // Logic nghiệp vụ.
}
```

`CountedAspect` tạo counter cho lời gọi được intercept. Theo mặc định, cả lần gọi thành công và thất bại đều được ghi nhận. Nếu phương thức ném exception, aspect ghi nhận trạng thái thất bại rồi ném lại exception để hành vi nghiệp vụ vẫn được giữ nguyên.

## 2. Thêm Spring AOP và đăng ký CountedAspect

`@Counted` và `CountedAspect` nằm trong module `micrometer-core`. Spring Boot Actuator thường đã đưa Micrometer Core vào dependency graph. Để Spring AOP nhận diện và áp dụng aspect, thêm starter AOP:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-aop'
}
```

Với Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

`spring-boot-starter-aop` cung cấp Spring AOP và AspectJ Weaver cần thiết để xử lý aspect. Khi dùng Spring Boot, auto-configuration AOP sẽ bật proxy khi các dependency phù hợp có mặt. Nếu dùng Spring Framework độc lập, cần cấu hình AOP bằng `@EnableAspectJAutoProxy` hoặc XML tương ứng và bảo đảm AspectJ Weaver nằm trên classpath.

Khai báo `CountedAspect` thành bean và inject `MeterRegistry`:

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

Đây là bước bắt buộc để `@Counted` được xử lý bởi Spring AOP. Chỉ thêm annotation vào method mà không đăng ký aspect sẽ không tạo counter. Hãy dùng `MeterRegistry` do Spring Boot quản lý để counter đi vào cùng registry với các metrics khác.

## 3. Đánh dấu method bằng @Counted

Ví dụ một service đếm số lần kiểm tra đơn hàng:

```java
import io.micrometer.core.annotation.Counted;
import org.springframework.stereotype.Service;

@Service
public class OrderValidationService {
    @Counted(
            value = "orders.validation.calls",
            description = "Number of order validation attempts",
            extraTags = {"operation", "validate"})
    public void validate(Order order) {
        if (order.items().isEmpty()) {
            throw new IllegalArgumentException("Order must contain an item");
        }
        // Các bước kiểm tra khác.
    }
}
```

Các thuộc tính chính của `@Counted`:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `value` | Tên counter; mặc định là `method.counted` |
| `description` | Mô tả ý nghĩa của counter |
| `extraTags` | Mảng key/value bổ sung, các phần tử phải đi theo cặp |
| `recordFailuresOnly` | Nếu `true`, chỉ ghi nhận lời gọi thất bại |

Nên đặt `value` tường minh để tên metric mô tả nghiệp vụ. Nếu nhiều method cùng dùng tên mặc định `method.counted`, chúng có thể được phân biệt bằng tag class/method mặc định, nhưng dashboard khó hiểu hơn và dễ tạo schema không mong muốn.

`extraTags` là các cặp chuỗi cố định trong annotation. Ví dụ `{"operation", "validate"}` thêm tag `operation=validate` cho mọi lần gọi method đó. Không đặt dữ liệu request, user ID hoặc order ID vào `extraTags`; annotation không phải nơi tạo tag động theo từng request.

## 4. Counter được gắn tag như thế nào?

`CountedAspect` tự thêm các tag mô tả kết quả thực thi:

| Tag | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `result` | `success` | Phương thức hoàn tất bình thường |
| `result` | `failure` | Phương thức ném exception hoặc hoàn tất bất đồng bộ với lỗi |
| `exception` | `none` | Lần gọi thành công, không có exception |
| `exception` | Tên class exception đơn giản | Loại exception gây thất bại |

Với constructor `new CountedAspect(registry)` thông dụng, aspect còn thêm tag `class` và `method` để phân biệt nơi gọi. Các `extraTags` trong annotation được ghép cùng các tag này.

Ví dụ metric logic có thể được biểu diễn trong Prometheus gần như sau:

```text
orders_validation_calls_total{
  class="com.example.OrderValidationService",
  method="validate",
  operation="validate",
  exception="none",
  result="success"
} 12

orders_validation_calls_total{
  class="com.example.OrderValidationService",
  method="validate",
  operation="validate",
  exception="IllegalArgumentException",
  result="failure"
} 2
```

Đây là dạng minh họa; tên export và hậu tố phụ thuộc registry cùng naming convention. Hai series có cùng metric name nhưng khác giá trị tag `result` và `exception`.

Khi phương thức ném exception, aspect ghi nhận `result=failure` và exception class đơn giản, sau đó ném lại exception. Nếu code bên trong tự bắt exception và trả về bình thường, aspect xem đó là thành công vì nó chỉ quan sát kết quả của lời gọi bên ngoài.

## 5. Ghi tất cả lần gọi hay chỉ ghi lần thất bại?

Mặc định, `recordFailuresOnly` là `false`; aspect ghi nhận cả success và failure. Đây thường là lựa chọn phù hợp khi muốn tính tổng số lần gọi và tỷ lệ lỗi:

```java
@Counted(
        value = "payment.authorization.calls",
        extraTags = {"operation", "authorize"})
public AuthorizationResult authorize(Payment payment) {
    // Xử lý ủy quyền thanh toán.
    return gateway.authorize(payment);
}
```

Nếu chỉ quan tâm lỗi và không cần counter cho thành công, có thể đặt `recordFailuresOnly = true`:

```java
@Counted(
        value = "payment.authorization.failures",
        recordFailuresOnly = true,
        extraTags = {"operation", "authorize"})
public AuthorizationResult authorize(Payment payment) {
    return gateway.authorize(payment);
}
```

Trong chế độ này, lời gọi thành công không tạo lần tăng counter; lời gọi thất bại vẫn được ghi nhận với `result=failure` và tag `exception` tương ứng. Nếu cần tỷ lệ lỗi, hãy giữ counter tổng có cả success/failure hoặc dùng một mẫu số độc lập. Không thể tính chính xác tỷ lệ lỗi chỉ từ counter `recordFailuresOnly=true` vì nó không chứa số lần thành công.

## 6. @Counted ở cấp class

`@Counted` có thể đặt trên class để áp dụng cho các method trong class:

```java
import io.micrometer.core.annotation.Counted;
import org.springframework.stereotype.Service;

@Service
@Counted(
        value = "inventory.service.calls",
        extraTags = {"component", "inventory"})
public class InventoryService {
    public void reserve(String sku) {
        // Giữ hàng.
    }

    public void release(String sku) {
        // Hoàn trả hàng.
    }
}
```

Các method được aspect intercept sẽ dùng counter theo tên đã khai báo và được phân biệt bằng tag `method` mặc định. Nếu method cần tên hoặc tag riêng, có thể đặt `@Counted` trực tiếp trên method đó. Pointcut của aspect tránh áp dụng advice class-level lần nữa cho method đã có annotation `@Counted`, nhằm tránh đếm hai lần.

Class-level annotation tiện khi mọi method trong class đều cần đếm. Nếu chỉ một số method có ý nghĩa vận hành, đặt annotation trực tiếp lên từng method giúp tránh tạo metrics cho các hàm phụ trợ hoặc getter không cần thiết.

## 7. AOP proxy ảnh hưởng đến vị trí đặt annotation

Spring AOP hoạt động thông qua proxy. Lời gọi từ bean khác đi vào bean Spring qua proxy sẽ được aspect intercept. Lời gọi nội bộ trong cùng object không đi qua proxy nên không kích hoạt `CountedAspect`.

Ví dụ dễ gây nhầm:

```java
@Service
public class InvoiceService {
    public void createInvoice() {
        validateInvoice(); // Self-invocation: không đi qua proxy.
    }

    @Counted("invoice.validation.calls")
    public void validateInvoice() {
        // Kiểm tra hóa đơn.
    }
}
```

Nếu `createInvoice()` gọi `validateInvoice()` bằng `this` ngầm định, lời gọi đó không được Spring AOP intercept. Có thể tách phần validate thành bean riêng rồi inject vào `InvoiceService`, hoặc tổ chức luồng gọi qua proxy một cách rõ ràng.

Các lưu ý khác:

- Đặt annotation trên method của Spring-managed bean; đối tượng được tạo bằng `new` bên ngoài container không có proxy.
- Với JDK dynamic proxy, lời gọi cần đi qua method được khai báo trên interface proxy.
- Private method không được Spring AOP proxy intercept; final method hoặc final class cũng không thể được CGLIB subclass proxy ghi đè.
- Dùng public method qua bean proxy là cách dễ dự đoán nhất giữa các kiểu proxy.
- Không đặt `@Counted` lên method static hoặc constructor và kỳ vọng Spring AOP xử lý như method instance thông thường.

Nếu metric không xuất hiện, hãy xác nhận method được gọi qua bean proxy trước khi kiểm tra registry hoặc backend.

## 8. Xử lý method trả về CompletionStage

`CountedAspect` hỗ trợ method trả về `CompletionStage` như `CompletableFuture`. Với loại return này, counter chỉ được tăng khi stage hoàn tất:

```java
import io.micrometer.core.annotation.Counted;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.util.concurrent.CompletableFuture;

@Service
public class ReportService {
    @Async
    @Counted("reports.generate.calls")
    public CompletableFuture<Report> generate(String reportType) {
        return CompletableFuture.supplyAsync(() -> buildReport(reportType));
    }
}
```

Nếu stage hoàn tất bình thường, aspect ghi `result=success` (trừ khi `recordFailuresOnly=true`). Nếu stage hoàn tất exceptional, aspect ghi `result=failure` và exception class rồi giữ nguyên trạng thái exceptional của stage. Điều này giúp counter phản ánh kết quả cuối cùng thay vì chỉ phản ánh thời điểm method trả về future.

Hỗ trợ này dành cho `CompletionStage`. Không giả định `Mono`, `Flux`, `Publisher` hoặc mọi kiểu asynchronous khác cũng được đếm tại thời điểm hoàn tất. Với reactive pipeline, hãy dùng Observation/reactive instrumentation hoặc đặt phép đo ở operator hoàn tất phù hợp.

## 9. Thêm tag từ tham số với @MeterTag

`extraTags` phù hợp với tag cố định. Nếu cần lấy tag từ tham số hoặc giá trị trả về, Micrometer có `@MeterTag`, nhưng cần cấu hình `CountedMeterTagAnnotationHandler` trên `CountedAspect` cùng resolver tương ứng.

Ví dụ annotation trên tham số:

```java
import io.micrometer.core.annotation.Counted;
import io.micrometer.core.aop.MeterTag;

@Counted("catalog.lookup.calls")
public Product findProduct(@MeterTag("category") String category) {
    return catalog.find(category);
}
```

Để hỗ trợ `@MeterTag`, cần gọi `countedAspect.setMeterTagAnnotationHandler(...)` khi cấu hình aspect. Handler nhận các `ValueResolver` hoặc `ValueExpressionResolver` do ứng dụng cung cấp để chuyển tham số thành tag value. Micrometer không tự bật xử lý này chỉ vì annotation xuất hiện.

Chỉ chuyển giá trị đã chuẩn hóa về tập hữu hạn thành tag. Ví dụ `category=book` hoặc `category=electronics` có thể phù hợp nếu danh mục được kiểm soát. Không đưa email, user ID, SKU tùy ý, query string hoặc dữ liệu tự do vào metric tag. Tag động có cardinality cao sẽ tạo nhiều time series và tăng chi phí lưu trữ.

Nếu chưa có nhu cầu cụ thể, hãy dùng `extraTags` cố định để cấu hình đơn giản và dễ kiểm soát.

## 10. Kiểm tra metric trong Prometheus

Với Prometheus registry, counter thường được công bố dưới dạng tên metric có hậu tố `_total`. Có thể tính tốc độ gọi thành công và thất bại theo cửa sổ 5 phút:

```promql
sum by (result) (
  rate(orders_validation_calls_total[5m])
)
```

Tỷ lệ thất bại trong cùng metric family:

```promql
sum(rate(orders_validation_calls_total{result="failure"}[5m]))
/
sum(rate(orders_validation_calls_total[5m]))
```

Nếu mẫu số không có dữ liệu hoặc bằng 0, biểu thức không tạo ra tỷ lệ hữu ích; dashboard cần xử lý trạng thái no-data. Với counter `recordFailuresOnly=true`, không dùng chính counter đó làm mẫu số vì nó chỉ đếm thất bại.

Không nhất thiết phải tạo thêm một `Counter` riêng chỉ để đếm số lần của một method đã được `@Counted`. Tuy nhiên, nếu cần một chỉ số nghiệp vụ khác với ý nghĩa lời gọi method, hãy tạo meter riêng với tên và semantics rõ ràng.

## 11. Kiểm thử CountedAspect bằng Spring context

Kiểm thử nên xác minh cả lời gọi thành công, lời gọi thất bại và việc exception vẫn được ném lại. Ví dụ dưới đây giả định ứng dụng test đã cấu hình bean `CountedAspect` như phần trước và dùng `SimpleMeterRegistry`:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderValidationCountedTest {
    @Autowired
    OrderValidationService service;

    @Autowired
    MeterRegistry registry;

    @Test
    void countsSuccessfulAndFailedCalls() {
        service.validate(new Order(List.of(new OrderItem("sku-1"))));

        assertThat(registry.get("orders.validation.calls")
                .tag("class", OrderValidationService.class.getName())
                .tag("method", "validate")
                .tag("operation", "validate")
                .tag("exception", "none")
                .tag("result", "success")
                .counter()
                .count()).isEqualTo(1.0);

        assertThatThrownBy(() -> service.validate(new Order(List.of())))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(registry.get("orders.validation.calls")
                .tag("class", OrderValidationService.class.getName())
                .tag("method", "validate")
                .tag("operation", "validate")
                .tag("exception", "IllegalArgumentException")
                .tag("result", "failure")
                .counter()
                .count()).isEqualTo(1.0);
    }
}
```

`Order`, `OrderItem` và `OrderValidationService` là kiểu miền nghiệp vụ minh họa; thay bằng kiểu của ứng dụng. Test phải gọi service được Spring inject, không tự tạo service bằng `new`, nếu không AOP proxy sẽ không chạy. Nếu dùng `SimpleMeterRegistry` trong test, có thể cung cấp registry đó qua test configuration để kiểm tra mà không cần backend ngoài.

Các kiểm tra nên bổ sung:

- Method không có `@Counted` không tạo counter ngoài ý muốn.
- `recordFailuresOnly=true` không tăng counter khi thành công nhưng có tăng khi thất bại.
- Lời gọi nội bộ trong cùng bean không được giả định là đã intercept.
- Với `CompletableFuture`, counter chỉ tăng sau khi stage hoàn tất.
- Tập tag key luôn nhất quán và giá trị tag không làm cardinality tăng ngoài dự kiến.

## 12. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Thêm `@Counted` nhưng không thấy counter | Chưa đăng ký `CountedAspect` hoặc thiếu AOP proxy | Thêm starter AOP và khai báo bean aspect |
| Tạo aspect nhưng annotation vẫn không chạy | Method không được gọi qua Spring proxy | Gọi qua bean được inject hoặc tách service |
| Counter chỉ ghi thành công | Code bắt exception bên trong và không ném ra ngoài | Đặt ranh giới đếm ở method phản ánh đúng kết quả cần đo |
| Chỉ thấy failure, không có success | `recordFailuresOnly=true` | Đổi về `false` nếu cần tổng số lần gọi và tỷ lệ lỗi |
| Đếm một lần nhưng tăng hai counter | Aspect được đăng ký trùng hoặc nhiều tầng proxy cùng xử lý | Kiểm tra cấu hình bean và AOP advisor |
| Không có tag theo tham số | Chưa cấu hình `CountedMeterTagAnnotationHandler` | Cấu hình handler và resolver cho `@MeterTag` |
| Metric tạo quá nhiều series | Dùng giá trị tự do làm tag | Chuẩn hóa tag value về vocabulary hữu hạn |
| Kỳ vọng đếm khi CompletableFuture được tạo | Nhầm thời điểm trả future với thời điểm hoàn tất | Để aspect xử lý CompletionStage hoặc đo reactive bằng công cụ tương ứng |
| Dùng `@Counted` để đo latency | Counter chỉ đếm số lần thực thi | Dùng `@Timed` hoặc Observation cho thời lượng |
| Dùng meta-annotation chứa `@Counted` | `CountedAspect` không hỗ trợ meta-annotation | Đặt `@Counted` trực tiếp hoặc tự triển khai aspect riêng |

## 13. Quy trình áp dụng

Khi thêm `@Counted` vào một service, hãy thực hiện theo trình tự:

1. Xác định method hoặc class có ý nghĩa cần đếm.
2. Thêm `spring-boot-starter-aop` và kiểm tra `micrometer-core` có trong runtime classpath.
3. Đăng ký một bean `CountedAspect` nhận `MeterRegistry` do Spring quản lý.
4. Đặt `@Counted` trực tiếp trên method hoặc class; khai báo tên metric rõ ràng.
5. Chọn `recordFailuresOnly` theo mục tiêu dashboard và alert.
6. Chỉ dùng `extraTags` hoặc `@MeterTag` với vocabulary có cardinality thấp.
7. Bảo đảm lời gọi đi qua Spring proxy; tránh self-invocation và object tự tạo.
8. Kiểm thử success, failure, async completion và schema tag.
9. Kiểm tra endpoint metrics hoặc backend để xác nhận counter được export và truy vấn đúng.

`@Counted` giúp tách việc đếm lời gọi khỏi code nghiệp vụ, còn `CountedAspect` kết nối annotation với `MeterRegistry` thông qua AOP. Khi aspect được cấu hình đúng, method được gọi qua proxy và tag được kiểm soát, ứng dụng có thể theo dõi số lần thành công/thất bại một cách nhất quán. Hãy dùng `Timer` hoặc Observation khi mục tiêu là đo thời gian, vì counter không chứa thông tin độ trễ.

## Tài liệu tham khảo

- [Micrometer 1.18: Counters và @Counted](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Counted Javadoc](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/annotation/Counted.html)
- [CountedAspect Javadoc](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/aop/CountedAspect.html)
- [Spring Boot: AOP auto-configuration](https://docs.spring.io/spring-boot/reference/features/aop.html)

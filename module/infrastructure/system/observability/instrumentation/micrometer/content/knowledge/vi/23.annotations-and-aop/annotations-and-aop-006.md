# Tag từ đối số bằng @MeterTag và cơ chế phân giải được hỗ trợ

`@MeterTag` cho phép lấy tag value từ đối số của một phương thức được instrument bằng annotation như `@Timed` hoặc `@Counted`. Thay vì gắn một tag value cố định, aspect đọc tham số lúc phương thức được gọi, chuyển tham số thành chuỗi qua cơ chế phân giải đã cấu hình rồi thêm cặp key-value đó vào meter.

Để cơ chế này hoạt động, annotation cần được xử lý bởi aspect tương ứng và aspect phải được đăng ký trong Spring context. `@MeterTag` tự nó không tạo meter và cũng không tự kích hoạt AOP. Khi dùng tag động, hãy ánh xạ đối số về một tập giá trị nhỏ, ổn định; không đưa ID người dùng, email, request ID hoặc dữ liệu tự do vào tag vì cardinality có thể tăng theo từng lần gọi.

## 1. @MeterTag giải quyết nhu cầu nào?

Một metric có thể cần phân loại theo một thuộc tính của tham số đầu vào. Ví dụ, phương thức tra cứu khách hàng nhận một đối tượng `Customer`; ta muốn đo thời gian xử lý riêng theo loại khách hàng như `retail`, `business` hoặc `partner`.

Nếu dùng `@Timed` với tag cố định, mọi lần gọi cùng phương thức sẽ mang cùng tag. `@MeterTag` cho phép lấy giá trị từ tham số:

```java
import io.micrometer.core.annotation.MeterTag;
import io.micrometer.core.annotation.Timed;
import org.springframework.stereotype.Service;

@Service
public class CustomerService {
    @Timed(value = "shop.customer.lookup", description = "Customer lookup duration")
    public Customer findCustomer(
            @MeterTag("customerType") Customer customer) {
        // Thực hiện tra cứu theo thông tin khách hàng.
        return customer;
    }
}
```

Trong ví dụ, `customerType` là tag key. Giá trị của tag được lấy từ tham số `customer` qua resolver đang áp dụng. Với resolver mặc định, giá trị thường được chuyển từ đối tượng tham số thành chuỗi; nếu đối tượng có `toString()` chứa dữ liệu không phù hợp hoặc quá chi tiết, hãy cung cấp resolver riêng.

## 2. @MeterTag cần aspect xử lý annotation

Micrometer cung cấp các aspect để xử lý annotation ở tầng method:

- `TimedAspect` xử lý `@Timed` và tạo timer cho lần thực thi phương thức.
- `CountedAspect` xử lý `@Counted` và tạo counter cho số lần gọi.
- `MeterTagAnnotationHandler` đọc `@MeterTag` trên tham số và phân giải tag value.

Trong Spring Boot, cần có AOP support và đăng ký aspect bean. Ví dụ với `@Timed`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

```java
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsAopConfiguration {
    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
```

Nếu dùng `@Counted`, đăng ký `CountedAspect` tương ứng:

```java
import io.micrometer.core.aop.CountedAspect;

@Bean
CountedAspect countedAspect(MeterRegistry registry) {
    return new CountedAspect(registry);
}
```

Tên package và API aspect cần khớp phiên bản Micrometer đang được Spring Boot quản lý. Chỉ thêm `spring-boot-starter-actuator` không có nghĩa mọi method gắn `@Timed` hoặc `@Counted` đều tự động được aspect xử lý; hãy xác minh aspect bean và AOP proxy thực sự được tạo.

## 3. @MeterTag hoạt động theo tham số được đánh dấu

`@MeterTag` đặt trên tham số mà bạn muốn chuyển thành tag. Ví dụ:

```java
@Timed("shop.payment.authorize")
public PaymentResult authorize(
        PaymentCommand command,
        @MeterTag("paymentChannel") PaymentChannel channel) {
    // Gọi cổng thanh toán.
    return paymentGateway.authorize(command, channel);
}
```

Chỉ tham số có `@MeterTag` được xử lý thành tag động. Các tham số khác vẫn được truyền cho phương thức bình thường và không tự động trở thành tag.

Khi phương thức có nhiều tham số được đánh dấu, mỗi tham số có thể tạo một tag riêng. Hãy giới hạn số tham số được dùng làm tag và bảo đảm các key khác nhau, có ý nghĩa rõ ràng.

Ví dụ:

```java
@Timed("shop.payment.authorize")
public PaymentResult authorize(
        @MeterTag("channel") PaymentChannel channel,
        @MeterTag("region") Region region) {
    return paymentGateway.authorize(channel, region);
}
```

Meter có thể được phân loại theo `channel` và `region`. Nếu mỗi tag có 3 và 5 giá trị hợp lệ, tổ hợp tối đa là 3 × 5 = 15 series cho metric này, chưa tính các tag khác do aspect hoặc registry bổ sung.

## 4. Resolver mặc định và giới hạn của toString()

Resolver là thành phần chuyển một đối tượng tham số thành tag value dạng chuỗi. Cơ chế mặc định có thể dựa trên biểu diễn chuỗi của tham số. Điều này tiện cho kiểu đơn giản như enum hoặc chuỗi đã chuẩn hóa, nhưng không phù hợp với mọi object.

Không nên để `toString()` của một domain object trả về toàn bộ nội dung đối tượng rồi dùng kết quả đó làm tag. Ví dụ `Customer.toString()` có thể chứa tên, email hoặc ID. Ngoài nguy cơ lộ dữ liệu, mỗi khách hàng có thể tạo một tag value mới.

Với kiểu dữ liệu có tập giá trị hữu hạn như enum, giá trị chuỗi có thể ổn định:

```java
public enum PaymentChannel {
    CARD,
    BANK_TRANSFER,
    WALLET
}
```

Nếu cần chuyển object thành nhóm nghiệp vụ, hãy dùng `ValueResolver` để chỉ trả về thuộc tính được phép và đã chuẩn hóa.

## 5. Viết ValueResolver để ánh xạ đối tượng thành tag value

`ValueResolver` là extension point để định nghĩa cách chuyển đối số thành chuỗi. Ví dụ sau chỉ lấy loại khách hàng và ánh xạ về một tập value cố định:

```java
import io.micrometer.core.aop.ValueResolver;
import java.util.Locale;

public final class CustomerTypeTagResolver implements ValueResolver {
    @Override
    public String resolve(Object parameter) {
        if (!(parameter instanceof Customer)) {
            return "unknown";
        }

        Customer customer = (Customer) parameter;
        if (customer.getType() == null) {
            return "unknown";
        }

        return customer.getType().name().toLowerCase(Locale.ROOT);
    }
}
```

Gắn resolver vào tham số:

```java
@Timed("shop.customer.lookup")
public Customer findCustomer(
        @MeterTag(value = "customerType", resolver = CustomerTypeTagResolver.class)
        Customer customer) {
    return customer;
}
```

Resolver có thể được dùng lại ở nhiều method. Hãy giữ nó stateless, nhanh và không thực hiện I/O. Không truy vấn database hoặc gọi dịch vụ bên ngoài trong quá trình phân giải tag vì resolver chạy trên đường gọi method và có thể làm tăng latency của chính thao tác được đo.

### 5.1. Resolver cần có đầu ra ổn định

Một resolver tốt có các đặc điểm:

- Trả về chuỗi không null theo quy ước rõ ràng.
- Ánh xạ input không hợp lệ về giá trị dự phòng như `unknown` hoặc `other`.
- Không trả về ID hoặc dữ liệu cá nhân.
- Không tạo giá trị ngẫu nhiên hoặc chứa timestamp.
- Không phụ thuộc trạng thái thay đổi ngoài ý nghĩa của tham số.
- Có chi phí tính toán thấp và không có tác dụng phụ.

Nếu resolver trả về `null`, chuỗi rỗng hoặc giá trị không nhất quán, kết quả meter có thể khó phân tích và tạo thêm series ngoài dự kiến. Hãy quy định rõ cách xử lý null và dữ liệu không nhận diện được.

## 6. ValueExpressionResolver và phân giải theo biểu thức

Ngoài resolver ánh xạ trực tiếp object, Micrometer hỗ trợ extension point `ValueExpressionResolver` để tính tag value từ biểu thức được cấu hình. Cơ chế này hữu ích khi muốn lấy một thuộc tính lồng nhau hoặc kết hợp một số trường của tham số mà không phải viết một resolver riêng cho từng kiểu.

`MeterTagAnnotationHandler` là thành phần kết nối annotation với cơ chế phân giải. Handler có thể được cấu hình với resolver thông thường và expression resolver; aspect dùng handler đó khi xử lý các tham số được đánh dấu. Cú pháp biểu thức, cách truy cập tham số và cách khởi tạo resolver phụ thuộc implementation mà ứng dụng cấu hình, ví dụ bộ phân giải dựa trên SpEL hoặc một expression engine nội bộ.

Khi dùng biểu thức, cần lưu ý:

- Biểu thức phải do đội phát triển kiểm soát, không lấy từ request hoặc người dùng.
- Chỉ truy cập thuộc tính cần thiết để tạo tag.
- Không thực thi lời gọi method có I/O hoặc logic nghiệp vụ nặng.
- Chuẩn hóa kết quả về tập value hữu hạn.
- Kiểm thử trường hợp null, object thiếu trường và biểu thức không hợp lệ.

Không có một expression language duy nhất bắt buộc cho mọi ứng dụng Micrometer. Nếu chọn expression resolver, hãy cấu hình rõ handler mà `TimedAspect` hoặc `CountedAspect` sử dụng và kiểm tra cú pháp theo implementation được tích hợp. Khi logic chỉ là ánh xạ một enum hoặc một trường đơn giản, `ValueResolver` thường dễ đọc và dễ kiểm soát hơn.

## 7. Cấu hình MeterTagAnnotationHandler cho aspect

`MeterTagAnnotationHandler` là điểm cấu hình tập trung cho việc phân giải các annotation trên tham số. Khi cần cơ chế phân giải tùy chỉnh cho nhiều loại annotation hoặc expression, hãy tạo handler phù hợp rồi truyền handler đó vào aspect theo constructor/API của phiên bản Micrometer đang dùng.

Về mặt trách nhiệm, cấu hình gồm ba phần:

1. **Annotation metadata**: xác định tag key và loại resolver cần áp dụng.
2. **ValueResolver**: chuyển đối tượng tham số thành chuỗi tag value.
3. **ValueExpressionResolver**: đánh giá biểu thức để tạo tag value khi cách phân giải dựa trên biểu thức được chọn.

Sau đó aspect gọi handler khi method được thực thi và gắn các tag đã phân giải vào meter. Không nên tự tạo meter trong resolver; resolver chỉ trả về giá trị tag.

Nếu dự án dùng cấu hình mặc định, hãy xác minh default handler có đáp ứng kiểu tham số đang dùng hay không. Nếu dùng resolver tùy chỉnh, hãy xác minh aspect thực sự nhận handler đó; tạo một bean handler riêng nhưng không nối nó vào aspect sẽ không thay đổi hành vi.

## 8. Kết hợp @MeterTag với @Counted

`@MeterTag` cũng có thể được dùng với phương thức được đếm bằng `@Counted`, nếu aspect hỗ trợ parameter tag trong phiên bản đang sử dụng:

```java
import io.micrometer.core.annotation.Counted;
import io.micrometer.core.annotation.MeterTag;
import org.springframework.stereotype.Service;

@Service
public class MessageHandler {
    @Counted(value = "shop.messages.processed")
    public void process(
            @MeterTag("messageType") MessageType messageType) {
        // Xử lý message.
    }
}
```

Mỗi lần method được aspect intercept, counter tương ứng với tag value được tăng. `@Counted` đo số lần method được gọi theo semantics của aspect; nó không tự động cho biết số message xử lý thành công nếu method có thể thất bại.

Nếu cần đếm riêng success và failure, hãy chọn điểm instrument phù hợp hoặc dùng các counter tường minh với tag `result` có giá trị hữu hạn. Đừng gắn nhãn `success` cho toàn bộ method chỉ vì nó có `@Counted`.

## 9. AOP proxy và những lời gọi không được intercept

Annotation-based metrics dựa trên AOP aspect. Với Spring proxy-based AOP, method phải được gọi qua proxy do Spring quản lý. Một lời gọi nội bộ từ method này sang method khác trong cùng object (self-invocation) thường không đi qua proxy, nên aspect không chạy.

Ví dụ:

```java
@Service
public class ReportService {
    public void generate() {
        measuredOperation("daily"); // self-invocation: thường không qua proxy.
    }

    @Timed("shop.report.operation")
    public void measuredOperation(
            @MeterTag("reportType") String reportType) {
        // Tạo báo cáo.
    }
}
```

Nếu `generate()` gọi trực tiếp `measuredOperation()` trên cùng instance, Spring AOP proxy thường không intercept lời gọi nội bộ đó. Có thể tách method được instrument sang một bean khác và inject bean đó, hoặc gọi method qua proxy theo thiết kế rõ ràng.

Ngoài ra, hãy kiểm tra giới hạn proxy và method của framework/phiên bản đang dùng. Method private, final hoặc class final có thể không được proxy theo cơ chế CGLIB/JDK tương ứng. Không nên kết luận annotation không hoạt động trước khi xác minh method có được intercept hay không.

## 10. Kiểm soát cardinality và bảo vệ dữ liệu

Tag từ tham số là tag động. Mỗi giá trị khác nhau có thể tạo một meter identity riêng. Nếu method nhận `customerId` và đưa thẳng vào `@MeterTag`, số series có thể tăng theo số khách hàng từng được gọi.

Không dùng trực tiếp các giá trị sau làm tag:

- User ID, customer ID, order ID hoặc session ID.
- Email, số điện thoại, địa chỉ hoặc tên người dùng.
- Request ID, trace ID hoặc correlation ID.
- URL đầy đủ, query string hoặc nội dung tự do.
- Exception message hoặc dữ liệu do bên ngoài gửi tùy ý.

Hãy ánh xạ về nhóm hữu hạn:

| Giá trị đầu vào | Tag value nên dùng |
| --- | --- |
| Customer có ID bất kỳ, loại `RETAIL` | `customerType=retail` |
| Customer có ID bất kỳ, loại `BUSINESS` | `customerType=business` |
| Channel không nhận diện được | `channel=other` |
| Region thuộc danh sách hỗ trợ | `region=apac`, `region=emea` hoặc giá trị hợp lệ khác |

Giới hạn cardinality trước khi đăng ký meter tốt hơn việc dựa vào backend để loại bỏ series sau khi chúng đã được tạo. Resolver nên là nơi chuẩn hóa dữ liệu theo domain nhưng không được biến thành nơi chứa logic nghiệp vụ phức tạp.

## 11. Kiểm thử @MeterTag

Nên kiểm tra ba phần riêng biệt:

1. Resolver ánh xạ đúng object sang tag value.
2. Aspect intercept method và tạo meter có tag mong đợi.
3. Meter được cập nhật đúng khi method thành công hoặc phát sinh exception theo semantics của annotation.

Có thể kiểm thử resolver như một unit test đơn giản:

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class CustomerTypeTagResolverTest {
    private final CustomerTypeTagResolver resolver =
            new CustomerTypeTagResolver();

    @Test
    void resolvesCustomerTypeToBoundedValue() {
        Customer customer = new Customer(CustomerType.BUSINESS);

        assertThat(resolver.resolve(customer)).isEqualTo("business");
        assertThat(resolver.resolve(null)).isEqualTo("unknown");
    }
}
```

Với integration test, tạo Spring context có `MeterRegistry`, `TimedAspect` và bean service được proxy. Gọi method qua bean inject từ context, sau đó tìm timer với tag đã phân giải:

```java
Timer timer = registry.find("shop.customer.lookup")
        .tag("customerType", "business")
        .timer();

assertThat(timer).isNotNull();
assertThat(timer.count()).isEqualTo(1);
```

Đây là đoạn assertion minh họa; cần bảo đảm method đã được gọi qua proxy và timer name đúng với annotation. Không khởi tạo service bằng `new` trong test nếu mục tiêu là kiểm tra AOP, vì object đó không được Spring proxy.

## 12. Những nguyên nhân khiến tag không xuất hiện

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Method chạy nhưng không có timer | `TimedAspect` chưa được đăng ký hoặc AOP chưa hoạt động | Kiểm tra aspect bean và dependency AOP. |
| Có timer nhưng thiếu tag | Tham số chưa có `@MeterTag` hoặc handler không được nối vào aspect | Kiểm tra annotation và `MeterTagAnnotationHandler`. |
| Tag value không đúng | Resolver mặc định không phù hợp với domain object | Viết `ValueResolver` và kiểm thử mapping. |
| Self-invocation không tạo meter | Lời gọi nội bộ không đi qua Spring proxy | Tách method sang bean khác hoặc gọi qua proxy. |
| Meter name khác dự kiến | `@Timed`/`@Counted` dùng tên khác hoặc naming convention export thay đổi | Kiểm tra `/actuator/metrics` và registry output. |
| Cardinality tăng nhanh | Resolver trả ID hoặc chuỗi động | Chuẩn hóa về enum/nhóm hữu hạn. |
| Expression không được áp dụng | Chưa cấu hình `ValueExpressionResolver` trong handler | Kiểm tra handler mà aspect đang sử dụng. |
| Tag bị từ chối | `MeterFilter` hoặc quy tắc registry loại bỏ meter/tag | Kiểm tra filter và log cấu hình. |

## 13. Checklist thiết kế @MeterTag

- [ ] Dùng `@MeterTag` trên đúng tham số của method được `@Timed` hoặc `@Counted` xử lý.
- [ ] Đăng ký aspect bean và bật AOP support.
- [ ] Gọi method qua Spring proxy, tránh self-invocation nếu cần intercept.
- [ ] Dùng resolver mặc định chỉ khi biểu diễn chuỗi của tham số đã an toàn và ổn định.
- [ ] Dùng `ValueResolver` để ánh xạ domain object về tag value có ý nghĩa.
- [ ] Dùng `ValueExpressionResolver` khi thực sự cần phân giải theo biểu thức và đã cấu hình handler tương ứng.
- [ ] Giữ resolver stateless, nhanh và không có I/O.
- [ ] Chuẩn hóa null và giá trị không hợp lệ về nhóm dự phòng.
- [ ] Không đưa ID, thông tin cá nhân hoặc dữ liệu tự do vào tag.
- [ ] Tính trước cardinality của các tag động và tổ hợp tag.
- [ ] Unit test resolver và integration test aspect cùng meter registry.
- [ ] Kiểm tra tag thực tế qua `/actuator/metrics` hoặc backend export.

`@MeterTag` giúp gắn chiều phân loại lấy từ đối số method vào metric được tạo bởi aspect. Để số liệu đáng tin cậy, hãy bảo đảm aspect thực sự intercept method, chọn đúng resolver cho kiểu tham số và giới hạn kết quả về một tập tag value ổn định. Resolver chỉ nên chuyển đổi dữ liệu đã có; việc kiểm soát cardinality và bảo vệ thông tin phải được thực hiện ngay tại ranh giới instrumentation.

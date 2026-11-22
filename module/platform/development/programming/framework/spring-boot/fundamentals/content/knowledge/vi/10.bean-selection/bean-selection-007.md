# `Ordered`, `@Order` và thứ tự các bean trong collection

Trong một ứng dụng Spring Boot, có lúc bạn cần inject **nhiều bean cùng implement một interface** vào một service. Ví dụ, một đơn hàng có thể được xử lý qua nhiều quy tắc giảm giá; một request có thể đi qua nhiều bộ lọc nghiệp vụ; hoặc ứng dụng cần chạy nhiều `CommandLineRunner` sau khi khởi động.

Khi đó, việc có đủ bean trong container chưa phải là tất cả. **Thứ tự thực hiện** cũng có thể ảnh hưởng trực tiếp đến kết quả. Spring cung cấp `Ordered` và `@Order` để biểu đạt thứ tự ưu tiên cho những điểm mở rộng có hỗ trợ cơ chế sắp xếp.

Điều cần nhớ ngay từ đầu:

- Số order **càng nhỏ thì mức ưu tiên càng cao**, tức được xếp trước.
- `Ordered` là interface cho phép bean tự trả về giá trị order.
- `@Order` là annotation khai báo giá trị order trên class hoặc phương thức cấu hình.
- Khi inject một `List<T>` hoặc array chứa nhiều bean phù hợp, Spring có thể sắp xếp các phần tử theo order.
- `@Order` **không quyết định thứ tự khởi tạo singleton** và không thay thế `@Primary` hoặc `@Qualifier` khi cần chọn một bean duy nhất.

## 1. Vì sao cần sắp xếp bean?

Giả sử ứng dụng bán hàng có nhiều quy tắc tính giá:

```text
Giá ban đầu
    |
    v
Giảm giá thành viên
    |
    v
Giảm giá chiến dịch
    |
    v
Điều chỉnh giá theo đối tác
    |
    v
Giá cuối cùng
```

Mỗi quy tắc được triển khai bởi một bean riêng. Nếu service nhận một collection các quy tắc, ứng dụng cần một thứ tự nhất quán để áp dụng chúng.

Không có thứ tự rõ ràng, kết quả có thể phụ thuộc vào thứ tự bean được tìm thấy hoặc cách collection được tạo. Điều đó khiến code khó đọc và dễ phát sinh lỗi khi thêm implementation mới.

Spring hỗ trợ metadata về thứ tự để container và những thành phần framework có sử dụng order comparator có thể sắp xếp các bean.

## 2. `Ordered` là gì?

`Ordered` là interface trong `org.springframework.core`. Bean implement interface này phải cung cấp phương thức `getOrder()`:

```java
public interface Ordered {
    int getOrder();
}
```

Giá trị trả về là một số nguyên. **Giá trị càng nhỏ, thứ tự càng cao.**

Ví dụ:

```java
import org.springframework.core.Ordered;
import org.springframework.stereotype.Component;

@Component
public class UrgentTaskHandler implements Ordered {

    @Override
    public int getOrder() {
        return 1;
    }
}
```

Bean `UrgentTaskHandler` cung cấp order bằng code. Cách này phù hợp khi thứ tự cần được quyết định bằng logic của bean, hoặc khi một implementation đã có thể triển khai `Ordered`.

### 2.1. Hai hằng số thường dùng

Spring định nghĩa hai hằng số tiện dụng:

| Hằng số | Giá trị/ý nghĩa | Vị trí |
| --- | --- | --- |
| `Ordered.HIGHEST_PRECEDENCE` | `Integer.MIN_VALUE` | Mức ưu tiên cao nhất theo quy ước order |
| `Ordered.LOWEST_PRECEDENCE` | `Integer.MAX_VALUE` | Mức ưu tiên thấp nhất theo quy ước order |

Ví dụ:

```java
import org.springframework.core.Ordered;

public class SecurityCheck implements Ordered {
    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }
}
```

Nếu không có giá trị order cụ thể, Spring thường xem phần tử không khai báo order như có mức ưu tiên thấp nhất (`LOWEST_PRECEDENCE`) trong những cơ chế sử dụng `OrderComparator`.

### 2.2. Có thể dùng số âm và số dương

Order không phải số thứ tự bắt đầu từ 1. Bạn có thể dùng số âm, số 0 hoặc số dương:

```java
public int getOrder() {
    return -10;
}
```

Ví dụ thứ tự tăng dần:

| Bean | Order | Vị trí |
| --- | ---: | ---: |
| `EmergencyHandler` | `-100` | 1 |
| `AuthenticationHandler` | `0` | 2 |
| `BusinessHandler` | `10` | 3 |
| `LoggingHandler` | `50` | 4 |

Nên dành khoảng cách giữa các giá trị, chẳng hạn 10, 20, 30, để có thể chèn thêm handler ở giữa mà không phải đổi toàn bộ thứ tự.

## 3. `@Order` là gì?

`@Order` là annotation của Spring Core, nằm trong package `org.springframework.core.annotation`. Annotation này cho phép khai báo order trực tiếp mà không cần class implement `Ordered`.

Ví dụ:

```java
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class MemberDiscountRule {
}
```

Một class khác:

```java
@Component
@Order(20)
public class CampaignDiscountRule {
}
```

Khi hai bean này được đưa vào một collection mà Spring sắp xếp theo order, `MemberDiscountRule` đứng trước `CampaignDiscountRule` vì 10 nhỏ hơn 20.

### 3.1. Giá trị mặc định

Nếu không chỉ định giá trị, `@Order` mặc định tương đương `Ordered.LOWEST_PRECEDENCE`:

```java
@Component
@Order
public class DefaultPriorityHandler {
}
```

Trong thực tế, nếu nhiều bean không khai báo order, đừng dựa vào thứ tự ngẫu nhiên hoặc thứ tự đăng ký để xây dựng logic nghiệp vụ. Nếu thứ tự có ý nghĩa, hãy khai báo rõ và ưu tiên giá trị order riêng biệt.

### 3.2. Đặt `@Order` trên phương thức `@Bean`

Không chỉ class component, bạn còn có thể đặt `@Order` trên phương thức factory `@Bean`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class HandlerConfiguration {

    @Bean
    @Order(1)
    public TaskHandler validationHandler() {
        return new ValidationHandler();
    }

    @Bean
    @Order(2)
    public TaskHandler auditHandler() {
        return new AuditHandler();
    }
}
```

Spring có thể sử dụng metadata trên factory method để xác định order của bean được tạo từ phương thức đó. Cách này hữu ích khi bạn không sở hữu class triển khai, chẳng hạn class đến từ thư viện bên ngoài.

**Chọn một nơi khai báo order rõ ràng:** nếu class và factory method cùng mang metadata order, hãy kiểm tra quy tắc tìm metadata của phiên bản Spring đang dùng; không nên đặt hai giá trị khác nhau rồi mong người đọc tự đoán giá trị nào có hiệu lực.

## 4. Inject nhiều bean vào `List<T>`

Đây là trường hợp sử dụng thường gặp nhất. Giả sử ứng dụng có interface:

```java
package com.example.shop.discount;

import java.math.BigDecimal;

public interface DiscountRule {
    BigDecimal apply(BigDecimal price);
}
```

Hai implementation:

```java
package com.example.shop.discount;

import java.math.BigDecimal;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public class MemberDiscountRule implements DiscountRule {
    @Override
    public BigDecimal apply(BigDecimal price) {
        return price.multiply(new BigDecimal("0.90"));
    }
}
```

```java
package com.example.shop.discount;

import java.math.BigDecimal;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public class CampaignDiscountRule implements DiscountRule {
    @Override
    public BigDecimal apply(BigDecimal price) {
        return price.subtract(new BigDecimal("5.00"));
    }
}
```

Service nhận tất cả bean có kiểu phù hợp:

```java
package com.example.shop.discount;

import java.math.BigDecimal;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class PricingService {

    private final List<DiscountRule> rules;

    public PricingService(List<DiscountRule> rules) {
        this.rules = rules;
    }

    public BigDecimal calculate(BigDecimal originalPrice) {
        BigDecimal result = originalPrice;

        for (DiscountRule rule : rules) {
            result = rule.apply(result);
        }

        return result;
    }
}
```

Spring tìm các bean ứng viên có kiểu `DiscountRule`, rồi trong cơ chế autowiring collection tiêu chuẩn, sắp xếp `List` theo order comparator. Với hai bean ở trên, danh sách được đưa vào constructor theo thứ tự:

```text
1. MemberDiscountRule   @Order(10)
2. CampaignDiscountRule @Order(20)
```

Với giá ban đầu 100:

```text
100.00
  -> giảm 10% thành viên = 90.00
  -> trừ 5.00 chiến dịch = 85.00
```

Thứ tự có thể làm thay đổi kết quả:

```text
100.00
  -> trừ 5.00 chiến dịch = 95.00
  -> giảm 10% thành viên = 85.50
```

Vì vậy, với pipeline nghiệp vụ có tính tuần tự, order cần được xem như một phần của thiết kế và cần được ghi rõ trong code.

## 5. Inject array và các kiểu collection khác

### 5.1. Array

Spring cũng hỗ trợ inject mảng bean cùng kiểu:

```java
@Service
public class PricingService {
    private final DiscountRule[] rules;

    public PricingService(DiscountRule[] rules) {
        this.rules = rules;
    }
}
```

Trong cơ chế autowiring array tiêu chuẩn, các bean ứng viên được sắp xếp theo order comparator trước khi được đưa vào mảng. Quy tắc giá trị nhỏ đứng trước vẫn được áp dụng.

### 5.2. `List` là lựa chọn phù hợp khi thứ tự quan trọng

Nếu logic của ứng dụng cần duyệt các bean theo một trình tự, `List<T>` biểu đạt ý định rõ ràng và Spring hỗ trợ sắp xếp collection này theo order.

Bạn có thể dùng:

```java
private final List<DiscountRule> rules;
```

để thể hiện một pipeline có thứ tự.

### 5.3. `Set` không phải hợp đồng thứ tự

`Set` được thiết kế để biểu diễn tập phần tử không trùng lặp. Tùy implementation và cách resolve, thứ tự iteration của Set không phải lúc nào cũng là một hợp đồng mà ứng dụng nên dựa vào.

```java
public PricingService(Set<DiscountRule> rules) {
    // Không nên giả định iteration order chính là @Order.
}
```

Nếu thứ tự thực thi quan trọng, hãy inject `List<DiscountRule>` hoặc chủ động chuyển và sắp xếp dữ liệu thành một list có quy tắc rõ ràng.

### 5.4. `Map<String, T>` hữu ích để tra cứu theo tên bean

Bạn có thể inject map:

```java
public NotificationService(Map<String, NotificationChannel> channels) {
    // key thường là bean name, value là bean tương ứng
}
```

Map thuận tiện khi cần chọn bean bằng tên như `emailChannel`, `smsChannel`. Tuy nhiên, mục đích chính của map injection là ánh xạ **bean name → bean instance**; không nên coi thứ tự iteration của map là hợp đồng `@Order`. Nếu cần duyệt theo thứ tự, hãy lấy các value và sắp xếp rõ ràng.

### 5.5. So sánh

| Kiểu injection | Công dụng | Có nên dựa vào `@Order` để duyệt? |
| --- | --- | --- |
| `List<T>` | Nhiều bean có trình tự | Có, với autowiring collection tiêu chuẩn của Spring |
| `T[]` | Nhiều bean trong mảng | Có, với cơ chế autowiring array tiêu chuẩn |
| `Set<T>` | Tập bean không trùng lặp | Không nên dựa vào iteration order |
| `Map<String, T>` | Tra cứu bean bằng tên | Không nên dựa vào thứ tự iteration |
| `ObjectProvider<T>.orderedStream()` | Lấy các bean theo thứ tự | Có, stream được yêu cầu sắp xếp |

## 6. `Ordered` và `@Order` khác nhau thế nào?

Cả hai đều biểu đạt order, nhưng cách khai báo và mức độ linh hoạt khác nhau.

| Tiêu chí | `Ordered` | `@Order` |
| --- | --- | --- |
| Loại | Interface | Annotation |
| Khai báo | Implement `getOrder()` | Gắn annotation với giá trị số |
| Giá trị | Có thể tính trong method | Giá trị metadata cố định |
| Phù hợp | Bean có logic tự cung cấp order | Component hoặc `@Bean` method cần khai báo order |
| Có thể dùng cùng nhau? | Có thể, nhưng cần hiểu quy tắc ưu tiên | Có thể, nhưng `Ordered` được ưu tiên khi object implement interface |

### 6.1. Nếu class vừa implement `Ordered` vừa có `@Order`?

Ví dụ:

```java
@Component
@Order(100)
public class SpecialHandler implements Ordered {

    @Override
    public int getOrder() {
        return 5;
    }
}
```

Khi Spring dùng `OrderComparator` để xét **instance**, giá trị từ interface `Ordered` được ưu tiên hơn metadata `@Order` trên class. Trong ví dụ này, order được sử dụng là 5.

Không nên khai báo hai giá trị mâu thuẫn nếu không có lý do đặc biệt. Chọn một cơ chế là đủ để người đọc dễ hiểu.

### 6.2. Ví dụ order được tính động

Một bean có thể trả về order từ thuộc tính đã được cấu hình:

```java
@Component
public class ConfigurableHandler implements Ordered {

    private final int order;

    public ConfigurableHandler(
            @Value("${handler.order:50}") int order) {
        this.order = order;
    }

    @Override
    public int getOrder() {
        return order;
    }
}
```

Trong ví dụ này, `@Value` lấy giá trị cấu hình `handler.order`, mặc định 50. Khi bean được sắp xếp, `getOrder()` trả về giá trị đã được inject. Cần import `org.springframework.beans.factory.annotation.Value`.

## 7. `PriorityOrdered` là gì?

`PriorityOrdered` là interface mở rộng `Ordered`:

```java
public interface PriorityOrdered extends Ordered {
}
```

Nó biểu thị một nhóm có mức ưu tiên cao hơn các đối tượng chỉ implement `Ordered` trong những cơ chế sử dụng `OrderComparator`.

Ví dụ:

```java
@Component
public class InfrastructureHandler implements PriorityOrdered {
    @Override
    public int getOrder() {
        return 100;
    }
}
```

và:

```java
@Component
public class ApplicationHandler implements Ordered {
    @Override
    public int getOrder() {
        return -100;
    }
}
```

Trong một điểm mở rộng có áp dụng quy tắc phân nhóm `PriorityOrdered`, `InfrastructureHandler` có thể được xếp trước nhóm `Ordered` thông thường dù số order của nó lớn hơn. Vì vậy không nên suy luận rằng chỉ so sánh số nguyên là đủ khi một cơ chế cụ thể có xét cả marker interface `PriorityOrdered`.

`PriorityOrdered` thường hữu ích trong hạ tầng mở rộng Spring, ví dụ một số loại post-processor. Với collection nghiệp vụ thông thường, `Ordered` hoặc `@Order` thường đã đủ; không cần dùng `PriorityOrdered` chỉ để tạo cảm giác ưu tiên cao hơn.

## 8. `@Order` không điều khiển thứ tự khởi tạo bean

Đây là nhầm lẫn rất phổ biến.

```java
@Component
@Order(1)
public class FirstService {
    public FirstService() {
        System.out.println("FirstService constructor");
    }
}

@Component
@Order(2)
public class SecondService {
    public SecondService() {
        System.out.println("SecondService constructor");
    }
}
```

Không nên coi hai annotation trên là cam kết rằng constructor của `FirstService` luôn được gọi trước constructor của `SecondService`.

`@Order` chủ yếu ảnh hưởng thứ tự khi các bean được **thu thập và sắp xếp** tại những điểm hỗ trợ order. Thứ tự khởi tạo bean còn phụ thuộc vào:

- Dependency giữa các bean.
- Scope và lazy initialization.
- Cách container đăng ký và tạo singleton.
- Các callback và post-processor.
- Cơ chế lifecycle của framework cụ thể.

Nếu bean B bắt buộc cần bean A được khởi tạo trước do có quan hệ phụ thuộc, hãy biểu đạt dependency qua constructor injection. Nếu chỉ cần kiểm soát khởi tạo trước mà không có dependency trực tiếp, có thể cân nhắc `@DependsOn`.

Ví dụ:

```java
@Component
@DependsOn("databaseInitializer")
public class SearchIndexService {
}
```

`@DependsOn` yêu cầu bean được chỉ định khởi tạo trước bean mang annotation trong trường hợp áp dụng phù hợp. Đây là một cơ chế khác với sắp xếp collection bằng `@Order`.

### 8.1. `@Order` và `@DependsOn`

| Annotation | Trả lời câu hỏi | Tác động chính |
| --- | --- | --- |
| `@Order(10)` | Phần tử này nên đứng ở vị trí nào khi sắp xếp? | Order trong collection/extension point có hỗ trợ |
| `@DependsOn("dataSourceInitializer")` | Bean nào cần được khởi tạo trước? | Quan hệ thứ tự khởi tạo giữa các bean |

Nếu `ReportService` inject `DataSource`, constructor dependency đã thể hiện quan hệ phụ thuộc. Không cần thêm `@DependsOn` chỉ để đảm bảo DataSource có trước ReportService trong tình huống đó.

## 9. `@Order` không thay thế `@Primary` và `@Qualifier`

Ba annotation có mục tiêu khác nhau:

```text
Nhiều bean cùng kiểu
        |
        +--> Cần chọn một bean để inject?
        |       @Primary / @Qualifier
        |
        +--> Cần tất cả bean theo trình tự?
                @Order / Ordered
```

### 9.1. `@Primary`: chọn ứng viên mặc định

```java
@Component
@Primary
public class EmailNotificationChannel implements NotificationChannel {
}

@Component
public class SmsNotificationChannel implements NotificationChannel {
}
```

Nếu một bean cần inject một `NotificationChannel`, `EmailNotificationChannel` là ứng viên primary khi không có qualifier hoặc quy tắc lựa chọn khác cụ thể hơn.

### 9.2. `@Qualifier`: chọn theo tên/nhãn

```java
@Service
public class AlertService {

    private final NotificationChannel channel;

    public AlertService(
            @Qualifier("smsNotificationChannel")
            NotificationChannel channel) {
        this.channel = channel;
    }
}
```

Qualifier giúp chỉ rõ implementation cần dùng.

### 9.3. `@Order`: lấy nhiều bean và sắp xếp

```java
@Service
public class NotificationPipeline {

    private final List<NotificationChannel> channels;

    public NotificationPipeline(List<NotificationChannel> channels) {
        this.channels = channels;
    }
}
```

Ở đây service nhận collection gồm nhiều channel phù hợp. `@Order` quyết định thứ tự các phần tử khi Spring sắp xếp list.

### 9.4. Bảng tổng hợp

| Công cụ | Khi nào dùng? | Ví dụ |
| --- | --- | --- |
| `@Primary` | Có nhiều bean cùng kiểu, muốn một bean làm mặc định | Email là channel mặc định |
| `@Qualifier` | Muốn chỉ định chính xác bean | Service gửi SMS |
| `@Order` / `Ordered` | Muốn nhiều bean được xử lý theo trình tự | Pipeline quy tắc giảm giá |
| `@DependsOn` | Cần bean khác được khởi tạo trước | Initializer trước service cần side effect |

## 10. `ObjectProvider.orderedStream()` để lấy bean theo thứ tự

Không phải lúc nào cũng muốn inject toàn bộ list ngay trong constructor. `ObjectProvider<T>` cho phép truy xuất các bean theo nhu cầu:

```java
import java.util.List;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class RuleExecutor {
    private final ObjectProvider<DiscountRule> rules;

    public RuleExecutor(ObjectProvider<DiscountRule> rules) {
        this.rules = rules;
    }

    public List<DiscountRule> orderedRules() {
        return rules.orderedStream().toList();
    }
}
```

`orderedStream()` yêu cầu Spring cung cấp các bean theo order comparator. Phương thức `stream()` thông thường không nên được coi là đã sắp xếp theo `@Order`; nếu thứ tự quan trọng, hãy gọi `orderedStream()` hoặc tự sắp xếp bằng comparator thích hợp.

Một ví dụ sử dụng ngay:

```java
rules.orderedStream().forEach(rule -> {
    // Thực thi từng rule theo thứ tự
});
```

API này hữu ích khi:

- Muốn trì hoãn việc resolve bean đến lúc cần.
- Muốn lấy một tập bean từ provider và sắp xếp theo order.
- Muốn sử dụng nhiều implementation mà không inject trực tiếp một `List` cố định.

## 11. Sắp xếp collection bằng comparator khi cần

Ngoài autowiring, bạn có thể chủ động sắp xếp collection trong Java.

Spring cung cấp `OrderComparator` và `AnnotationAwareOrderComparator`:

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.core.annotation.AnnotationAwareOrderComparator;

List<DiscountRule> ordered = new ArrayList<>(rules);
AnnotationAwareOrderComparator.sort(ordered);
```

`AnnotationAwareOrderComparator` hiểu metadata `@Order` và các nguồn order mà comparator hỗ trợ. `OrderComparator` cơ bản làm việc với `Ordered`; khi cần đọc annotation, hãy chọn comparator có khả năng nhận biết annotation.

Nếu muốn tự kiểm soát hoàn toàn:

```java
ordered.sort(
    Comparator.comparingInt(DiscountRule::customPriority)
);
```

Trong ví dụ này, `customPriority()` là phương thức do interface `DiscountRule` định nghĩa. Đây là quy tắc riêng của ứng dụng; nó không tự động dùng `@Order`.

Không nên vừa dùng `@Order`, vừa tự sort theo một thuộc tính khác mà không ghi rõ thứ tự nào là nguồn quyết định cuối cùng.

## 12. Một số điểm mở rộng: `@Order` trong Spring Boot

`@Order` không chỉ dùng cho list bean nghiệp vụ. Một số extension point của Spring và Spring Boot cũng sử dụng order comparator để xác định thứ tự thực thi.

### 12.1. `CommandLineRunner` và `ApplicationRunner`

Spring Boot gọi các bean `CommandLineRunner` và `ApplicationRunner` sau khi application context được khởi động. Có thể dùng `@Order` để xác định thứ tự gọi các runner:

```java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration(proxyBeanMethods = false)
public class StartupTasks {

    @Bean
    @Order(1)
    CommandLineRunner loadReferenceData() {
        return args -> System.out.println("1. Load reference data");
    }

    @Bean
    @Order(2)
    CommandLineRunner verifyConfiguration() {
        return args -> System.out.println("2. Verify configuration");
    }
}
```

Trong cấu hình này, runner có order 1 được gọi trước runner có order 2. Đây là **thứ tự gọi runner sau khi context đã khởi động**, không phải thứ tự khởi tạo object của hai runner.

Nếu runner thứ hai cần dữ liệu do runner thứ nhất tạo, hãy cân nhắc thiết kế dependency hoặc một quy trình khởi tạo chuyên biệt để quan hệ đó rõ ràng. Chỉ sắp xếp runner có thể không đủ để biểu đạt mọi điều kiện vận hành.

### 12.2. Spring AOP aspects

Nếu ứng dụng có nhiều aspect áp dụng lên cùng một join point, `@Order` có thể giúp xác định thứ tự ưu tiên giữa các aspect:

```java
@Aspect
@Component
@Order(1)
public class SecurityAspect {
    // Advice kiểm tra bảo mật
}
```

```java
@Aspect
@Component
@Order(2)
public class LoggingAspect {
    // Advice ghi log
}
```

Thứ tự thực thi cụ thể của before/after/around advice có quy tắc lồng nhau: aspect có precedence cao hơn có thể bao quanh aspect có precedence thấp hơn. Đừng diễn giải đơn giản rằng mọi dòng log đều chạy theo thứ tự tăng dần; cần xét loại advice và vị trí trong call stack.

### 12.3. Một số extension point hạ tầng

Spring có nhiều giao diện và callback dùng thứ tự, chẳng hạn một số loại `BeanFactoryPostProcessor`, `BeanPostProcessor`, event listener hoặc strategy. Mỗi extension point có thể có quy tắc thu thập và sắp xếp riêng. Hãy kiểm tra tài liệu/API của extension point đó để biết nó có tôn trọng `Ordered` hay `@Order` không.

**Không phải mọi danh sách trong Spring đều tự động sắp xếp theo `@Order`.** Annotation chỉ có tác dụng ở nơi cơ chế tương ứng đọc và sử dụng metadata order.

## 13. Thứ tự bằng nhau và giá trị mặc định

Ví dụ:

```java
@Component
@Order(10)
public class FirstRule implements DiscountRule {
}

@Component
@Order(10)
public class SecondRule implements DiscountRule {
}
```

Hai bean có cùng order. Comparator không có thông tin nghiệp vụ để quyết định bean nào cần chạy trước. Trong một số trường hợp, sort ổn định có thể giữ thứ tự đầu vào, nhưng thứ tự đầu vào có thể phụ thuộc cách đăng ký hoặc cơ chế tìm bean.

Nếu thứ tự giữa hai rule có ý nghĩa, hãy gán order khác nhau:

```java
@Order(10)
class FirstRule { }

@Order(20)
class SecondRule { }
```

Nếu hai rule độc lập và không cần quan hệ trước/sau, cùng order có thể chấp nhận được. Nhưng không nên kiểm thử hoặc xây dựng nghiệp vụ dựa vào thứ tự ngẫu nhiên giữa những phần tử cùng mức.

## 14. Cách kiểm tra thứ tự bean trong ứng dụng

### 14.1. In danh sách từ constructor

Trong service nhận list:

```java
public PricingService(List<DiscountRule> rules) {
    this.rules = rules;

    rules.forEach(rule ->
        System.out.println(rule.getClass().getSimpleName())
    );
}
```

Đây là cách đơn giản để quan sát các implementation được inject và thứ tự hiện tại. Nếu bean được bọc proxy, `getSimpleName()` có thể hiển thị tên lớp proxy; khi cần xác định target class, sử dụng API AOP phù hợp.

### 14.2. Dùng test để kiểm tra thứ tự có ý nghĩa nghiệp vụ

Ví dụ với Spring Boot Test:

```java
@SpringBootTest
class PricingServiceTest {

    @Autowired
    private List<DiscountRule> rules;

    @Test
    void rulesAreOrdered() {
        assertThat(rules)
            .extracting(rule -> rule.getClass())
            .containsSubsequence(
                MemberDiscountRule.class,
                CampaignDiscountRule.class
            );
    }
}
```

Đoạn test minh họa ý tưởng; nếu bean được proxy, nên kiểm tra target class bằng công cụ phù hợp hoặc kiểm tra **hành vi thực thi** thay vì so sánh runtime class trực tiếp. Cũng có thể dùng các rule giả ghi lại thứ tự gọi để kiểm tra pipeline.

Một cách kiểm tra hành vi ít phụ thuộc loại proxy hơn:

```java
@Test
void appliesRulesInConfiguredOrder() {
    BigDecimal result = pricingService.calculate(new BigDecimal("100.00"));

    assertThat(result).isEqualByComparingTo("85.00");
}
```

Test kết quả này chỉ phù hợp nếu các quy tắc giảm giá của ví dụ có đúng phép tính đã nêu và không có quy tắc khác trong context.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Order 100 chạy trước order 1.” | Số nhỏ hơn được ưu tiên trước; 1 đứng trước 100. |
| “`@Order(1)` làm bean khởi tạo đầu tiên.” | Nó sắp xếp bean ở những extension point có hỗ trợ; không điều khiển chung thứ tự khởi tạo singleton. |
| “`@Order` chọn bean mặc định để inject một interface.” | Dùng `@Primary` hoặc `@Qualifier` cho lựa chọn một bean; `@Order` phục vụ sắp xếp nhiều bean. |
| “Mọi `Set` và `Map` đều giữ order annotation.” | Không nên dựa vào iteration order của Set/Map; dùng List hoặc `orderedStream()` khi cần trình tự. |
| “Chỉ class mới có thể khai báo order.” | Có thể đặt `@Order` trên class và phương thức `@Bean` phù hợp. |
| “`Ordered` và `@Order` luôn được đọc ngang nhau.” | Khi instance implement `Ordered`, giá trị `getOrder()` được ưu tiên hơn annotation trong comparator tiêu chuẩn. |
| “Mọi danh sách trong Spring đều tự sắp xếp.” | Chỉ những cơ chế có sử dụng order comparator mới áp dụng metadata order. |
| “Hai bean cùng order chắc chắn có thứ tự nghiệp vụ xác định.” | Nếu thứ tự có ý nghĩa, hãy dùng giá trị riêng biệt hoặc một quy tắc tie-breaker rõ ràng. |

## 16. Bài thực hành

### Bài 1 — Tạo ba implementation

Tạo interface:

```java
public interface MessageHandler {
    void handle(String message);
}
```

Tạo ba bean `EmailHandler`, `SmsHandler` và `LogHandler` có `@Component` và order lần lượt là 20, 10, 30. Inject `List<MessageHandler>` vào `MessageDispatcher` và in tên các handler.

**Yêu cầu:** dự đoán thứ tự trước khi chạy, sau đó so sánh kết quả thực tế.

### Bài 2 — Thử `Ordered`

Thay một implementation bằng class implement `Ordered`, trả về `getOrder() = 5`. Đồng thời gắn `@Order(100)` lên class.

**Câu hỏi:** comparator sẽ sử dụng giá trị nào? Vì sao?

### Bài 3 — So sánh List, Set và Map

Inject cùng tập `MessageHandler` vào:

```java
List<MessageHandler>
Set<MessageHandler>
Map<String, MessageHandler>
```

Quan sát iteration order. Giải thích vì sao List là lựa chọn phù hợp hơn khi thứ tự xử lý là yêu cầu bắt buộc, còn Map hữu ích để tra cứu theo tên bean.

### Bài 4 — Phân biệt order và startup sequence

Tạo hai component có constructor in log và gắn `@Order(1)`, `@Order(2)`. Quan sát log khởi tạo. Sau đó inject cả hai vào `List` và in danh sách.

**Câu hỏi:** tại sao thứ tự log constructor không phải là bằng chứng về thứ tự của list?

### Bài 5 — Sắp xếp startup runners

Khai báo ba `CommandLineRunner` bằng `@Bean` với order 30, 10 và 20. Ghi log khi từng runner được gọi.

**Yêu cầu:** xác định thứ tự thực thi và giải thích vì sao `@Order` ở đây có hiệu lực.

### Bài 6 — Chọn một bean hay nhiều bean?

Cho hai implementation `PaymentGateway`: `CardGateway` và `BankGateway`.

- Một `PaymentService` chỉ được dùng một gateway theo cấu hình: hãy chọn `@Qualifier` hoặc `@Primary`.
- Một `PaymentAuditPipeline` cần gọi cả hai gateway theo trình tự: inject `List<PaymentGateway>` và dùng `@Order`.

Giải thích vì sao hai yêu cầu cần hai cơ chế khác nhau.

## 17. Ghi nhớ khi xây dựng pipeline bean

`Ordered` và `@Order` cho Spring biết **mức ưu tiên của một bean khi cơ chế tương ứng cần sắp xếp nhiều bean**. Giá trị nhỏ hơn đứng trước; nếu không khai báo, order mặc định có mức ưu tiên thấp nhất. Với collection injection, `List<T>` và array là những lựa chọn phù hợp khi trình tự có ý nghĩa; với `ObjectProvider`, dùng `orderedStream()` khi cần stream đã sắp xếp.

Hãy chọn đúng công cụ cho đúng câu hỏi: `@Order` để sắp xếp nhiều bean, `@Primary`/`@Qualifier` để chọn bean cần inject, và `@DependsOn` hoặc dependency injection để biểu đạt quan hệ khởi tạo. Khi thứ tự ảnh hưởng kết quả nghiệp vụ, đặt order rõ ràng và kiểm thử hành vi thực tế của pipeline.

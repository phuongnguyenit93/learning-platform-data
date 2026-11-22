# @Autowired và trường hợp constructor không cần annotation

Dependency Injection (DI) là cơ chế để một đối tượng nhận các thành phần mà nó cần từ bên ngoài thay vì tự tạo chúng. Trong Spring, `ApplicationContext` quản lý các bean và kết nối dependency theo các bean definition đã đăng ký. Annotation `@Autowired` là một cách yêu cầu Spring tự động giải quyết dependency tại một điểm injection.

Khi học Spring Boot, bạn thường thấy constructor có `@Autowired` trong ví dụ cũ, nhưng nhiều ứng dụng hiện đại lại không có annotation này trên constructor. Cả hai cách đều có thể đúng. Từ Spring Framework 4.3, nếu một bean class chỉ khai báo **một constructor duy nhất**, Spring tự sử dụng constructor đó để inject dependency mà không yêu cầu `@Autowired`.

Cần phân biệt ba câu hỏi:

- Bean nào đã được đăng ký trong context?
- Constructor hoặc điểm injection nào Spring sẽ sử dụng?
- Nếu có nhiều bean cùng kiểu, Spring chọn bean nào?

Bài học giải thích cách `@Autowired` hoạt động, vì sao constructor đơn không cần annotation, cách xử lý nhiều constructor và dependency tùy chọn, cùng các lỗi phổ biến khi wiring bean.

## 1. Dependency Injection và `@Autowired`

Giả sử một dịch vụ tạo đơn hàng cần một kho lưu trữ. Nếu service tự khởi tạo kho lưu trữ, nó phải biết implementation cụ thể:

```java
public class OrderService {
    private final JdbcOrderRepository repository =
            new JdbcOrderRepository();

    public void create(String id) {
        repository.save(id);
    }
}
```

Cách viết này ghép chặt nghiệp vụ với công nghệ lưu trữ. Khi muốn chuyển sang JPA, gọi API hoặc dùng fake repository trong test, phải sửa service.

Với DI, service khai báo dependency qua constructor:

```java
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public void create(String id) {
        repository.save(id);
    }
}
```

Service chỉ yêu cầu hợp đồng `OrderRepository`. Spring có thể tạo implementation và truyền vào khi khởi tạo bean.

Trong Spring, `@Autowired` đánh dấu một constructor, field hoặc method mà container cần xử lý để inject dependency. Annotation thuộc package:

```java
import org.springframework.beans.factory.annotation.Autowired;
```

Ví dụ constructor injection có annotation:

```java
@Service
public class OrderService {
    private final OrderRepository repository;

    @Autowired
    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
```

Nếu `OrderService` chỉ có constructor này, có thể bỏ `@Autowired` mà Spring vẫn inject đúng dependency.

## 2. Vì sao constructor duy nhất không cần `@Autowired`?

Từ Spring Framework 4.3, một bean class chỉ có **một constructor được khai báo** thì constructor đó được xem là constructor cần dùng để autowire, kể cả khi không gắn `@Autowired`.

Ví dụ:

```java
package com.example.orders.application;

import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final OrderRepository repository;
    private final OrderNotifier notifier;

    public OrderService(
            OrderRepository repository,
            OrderNotifier notifier) {
        this.repository = repository;
        this.notifier = notifier;
    }

    public void create(String orderId) {
        repository.save(orderId);
        notifier.orderCreated(orderId);
    }
}
```

Không có `@Autowired` trên constructor, nhưng Spring hiểu rằng khi tạo `OrderService`, nó phải tìm bean phù hợp cho `OrderRepository` và `OrderNotifier`.

Quy tắc này giúp mã nguồn gọn hơn vì constructor đơn đã diễn đạt rõ cách khởi tạo bean. Nó cũng làm cho dependency bắt buộc hiển thị ở API khởi tạo, cho phép dùng field `final` và giúp unit test tạo instance trực tiếp bằng `new OrderService(fakeRepository, fakeNotifier)`.

### 2.1. Bỏ annotation không có nghĩa dependency tự xuất hiện

Spring vẫn cần bean tương ứng trong context. Ví dụ:

```java
@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
```

Nếu không có bean nào tương thích với `OrderRepository`, ứng dụng vẫn không khởi động được. Lỗi thường xuất hiện qua `UnsatisfiedDependencyException`, với nguyên nhân sâu hơn là không tìm thấy bean phù hợp.

Vì vậy:

- Không cần `@Autowired` trên constructor đơn.
- Vẫn cần dependency được đăng ký trong Spring context.
- `@Autowired` không thay thế component scanning, `@Bean`, `@Import` hoặc auto-configuration.

### 2.2. Constructor mặc định do Java tạo

Nếu class không khai báo constructor nào, Java tự tạo constructor mặc định không tham số:

```java
@Component
public class ApplicationMarker {
    // Java tự cung cấp constructor không tham số.
}
```

Khi cần dependency, hãy khai báo constructor rõ ràng:

```java
@Component
public class ApplicationMarker {
    private final Environment environment;

    public ApplicationMarker(Environment environment) {
        this.environment = environment;
    }
}
```

Khi đã tự khai báo constructor có tham số, Java không còn tự sinh constructor mặc định không tham số. Trong ví dụ này, Spring dùng constructor một tham số dù không có `@Autowired`.

### 2.3. Quy tắc constructor đơn không áp dụng khi có nhiều constructor

Quy tắc không cần annotation nói về trường hợp bean class có một constructor duy nhất. Nếu class khai báo nhiều constructor, Spring cần biết constructor nào là ứng viên injection hoặc áp dụng quy tắc lựa chọn constructor phù hợp. Khi có nhiều lựa chọn, hãy làm rõ constructor dùng để khởi tạo bean.

## 3. Các vị trí có thể dùng `@Autowired`

Spring hỗ trợ autowiring qua constructor, field và method. Các cách này có đặc điểm khác nhau.

### 3.1. Constructor injection

```java
@Service
public class InvoiceService {
    private final InvoiceRepository repository;
    private final Clock clock;

    public InvoiceService(
            InvoiceRepository repository,
            Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }
}
```

Dependency được cung cấp ngay khi object được tạo. Khi constructor kết thúc, các field bắt buộc đã có giá trị. Đây thường là lựa chọn ưu tiên cho dependency bắt buộc.

Ưu điểm:

- Có thể khai báo field `final`.
- Không thể tạo object qua constructor này nếu thiếu dependency.
- Dependency hiển thị rõ ràng ở API khởi tạo.
- Unit test dễ tạo instance mà không cần Spring.
- Dễ nhận ra dependency vòng vì các bean phải chờ nhau trong quá trình khởi tạo.

### 3.2. Field injection

```java
@Service
public class InvoiceService {
    @Autowired
    private InvoiceRepository repository;
}
```

Spring tạo object trước, sau đó mới inject vào field. Vì dependency chưa được gán trong lúc constructor chạy, field injection có một số hạn chế:

- Không thể khai báo field được inject là `final`.
- Tạo instance trực tiếp bằng `new InvoiceService()` sẽ không có repository.
- Dependency không thể hiện trong constructor.
- Unit test thường cần Spring context hoặc cơ chế reflection để gán field.
- Một object có thể tồn tại sau khi constructor hoàn tất nhưng chưa có đủ dependency.

Field injection ngắn nhưng thường làm class khó kiểm thử và khó hiểu hơn. Với dependency bắt buộc, constructor injection rõ ràng hơn.

### 3.3. Setter injection

```java
@Component
public class ReportExporter {
    private ReportFormatter formatter;

    @Autowired
    public void setFormatter(ReportFormatter formatter) {
        this.formatter = formatter;
    }
}
```

Spring gọi setter để inject dependency sau khi tạo object. Setter injection phù hợp hơn với dependency thực sự tùy chọn hoặc có thể cấu hình lại sau khởi tạo, nếu thiết kế ứng dụng cần khả năng đó.

Nếu `ReportFormatter` bắt buộc để exporter hoạt động, constructor injection vẫn tốt hơn vì object không xuất hiện trong trạng thái thiếu formatter.

### 3.4. Method injection

`@Autowired` cũng có thể đánh dấu một phương thức có nhiều tham số:

```java
@Component
public class NotificationCoordinator {
    private EmailSender emailSender;
    private SmsSender smsSender;

    @Autowired
    public void configure(
            EmailSender emailSender,
            SmsSender smsSender) {
        this.emailSender = emailSender;
        this.smsSender = smsSender;
    }
}
```

Spring giải quyết từng tham số và gọi phương thức. Đây là method injection; nó không nhất thiết phải là JavaBean setter một tham số.

Trong thiết kế mới, nếu hai dependency đều bắt buộc, đưa chúng vào constructor thường làm hợp đồng của class rõ hơn.

### 3.5. So sánh nhanh

| Cách injection | Thời điểm gán dependency | Dùng `final` cho field | Phù hợp |
| --- | --- | --- | --- |
| Constructor | Khi tạo object | Có | Dependency bắt buộc |
| Field | Sau khi object được tạo | Không | Code legacy hoặc trường hợp framework đặc thù |
| Setter/method | Sau khi object được tạo | Không | Dependency tùy chọn hoặc cấu hình qua method |
| `@Bean` method parameter | Khi Spring gọi factory method | Không áp dụng trực tiếp | Lắp ghép bean trong Java configuration |

Spring hỗ trợ nhiều kiểu injection, nhưng khả năng sử dụng không có nghĩa chúng có chất lượng thiết kế ngang nhau trong mọi trường hợp.

## 4. Khi nào constructor cần `@Autowired`?

Nếu bean class có nhiều constructor, annotation có thể giúp Spring chọn constructor injection mong muốn.

```java
@Service
public class ShippingService {
    private final ShippingRepository repository;
    private final ShippingClient client;

    public ShippingService() {
        this(new InMemoryShippingRepository(), new DefaultShippingClient());
    }

    @Autowired
    public ShippingService(
            ShippingRepository repository,
            ShippingClient client) {
        this.repository = repository;
        this.client = client;
    }
}
```

Ở ví dụ này, constructor có `@Autowired` được chỉ định làm constructor injection. Constructor không tham số có thể hữu ích trong một số mục đích tạo object khác, nhưng tự tạo dependency hạ tầng bằng `new` thường không phải thiết kế tốt cho bean Spring. Đoạn mã chỉ minh họa cơ chế chọn constructor.

Một thiết kế rõ ràng hơn là giữ một constructor duy nhất:

```java
@Service
public class ShippingService {
    private final ShippingRepository repository;
    private final ShippingClient client;

    public ShippingService(
            ShippingRepository repository,
            ShippingClient client) {
        this.repository = repository;
        this.client = client;
    }
}
```

### 4.1. Một constructor bắt buộc được đánh dấu `@Autowired`

Khi có nhiều constructor, có thể đánh dấu constructor muốn Spring sử dụng. Thuộc tính `required` của `@Autowired` mặc định là `true`. Một constructor được đánh dấu `@Autowired` với `required = true` là constructor bắt buộc được chọn.

Ví dụ trên có một constructor được đánh dấu rõ ràng. Tuy nhiên, nếu không có yêu cầu đặc biệt cho nhiều cách khởi tạo, nên bỏ overload và giữ một constructor duy nhất.

### 4.2. Nhiều constructor có `@Autowired(required = false)`

Spring cho phép một số constructor được đánh dấu `required = false`. Khi không có constructor bắt buộc, Spring có thể xét các ứng viên và chọn constructor có số dependency lớn nhất mà nó có thể đáp ứng. Nếu không có constructor ứng viên phù hợp, constructor mặc định không tham số có thể được dùng khi có.

Đây là cơ chế linh hoạt nhưng có thể khiến cách khởi tạo khó đọc và phụ thuộc vào những bean đang có trong context. Với phần lớn service ứng dụng, tránh thiết kế nhiều constructor autowire tùy chọn. Dùng một constructor bắt buộc và biểu diễn dependency tùy chọn bằng kiểu phù hợp sẽ dễ hiểu hơn.

### 4.3. Không thể có nhiều constructor đều là constructor bắt buộc

Một class không thể yêu cầu Spring dùng đồng thời nhiều constructor làm constructor bắt buộc. Nếu nhiều constructor đều có `@Autowired` với `required = true`, cấu hình không hợp lệ và Spring sẽ báo lỗi.

Khi có nhiều constructor và cần injection, hãy chọn một constructor chính. Nếu có constructor phụ phục vụ test hoặc factory khác, đảm bảo nó không làm mơ hồ quá trình tạo bean.

## 5. `@Autowired` giải quyết dependency như thế nào?

Mặc định, `@Autowired` giải quyết dependency chủ yếu theo **kiểu (type)**. Spring tìm bean có kiểu tương thích với kiểu tham số hoặc field cần inject.

```java
public interface PaymentGateway {
    void charge(String paymentId);
}

@Component
public class BankPaymentGateway implements PaymentGateway {
    @Override
    public void charge(String paymentId) {
        // Gọi adapter ngân hàng.
    }
}

@Service
public class PaymentService {
    private final PaymentGateway gateway;

    public PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Nếu chỉ có một bean phù hợp với `PaymentGateway`, Spring có thể inject bean đó.

Nếu có nhiều implementation, Spring không biết cần chọn bean nào nếu không có thông tin ưu tiên hoặc qualifier. Lúc này có thể xuất hiện `NoUniqueBeanDefinitionException` hoặc `UnsatisfiedDependencyException` chứa nguyên nhân đó.

### 5.1. Dùng `@Qualifier` để chỉ rõ bean

`@Qualifier` thu hẹp tập bean ứng viên:

```java
@Component("bankGateway")
class BankPaymentGateway implements PaymentGateway {
    // ...
}

@Component("walletGateway")
class WalletPaymentGateway implements PaymentGateway {
    // ...
}

@Service
class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(@Qualifier("bankGateway") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Khi cần, có thể định nghĩa qualifier tùy biến bằng annotation riêng để mô tả ngữ nghĩa thay vì phụ thuộc vào tên bean.

### 5.2. Dùng `@Primary` cho implementation mặc định

Nếu một implementation nên được chọn khi không chỉ định qualifier, có thể đánh dấu nó bằng `@Primary`:

```java
@Component
@Primary
class BankPaymentGateway implements PaymentGateway {
    // ...
}
```

Khi inject `PaymentGateway` không có qualifier, bean primary được ưu tiên. `@Qualifier` tại điểm injection có thể chỉ rõ bean khác khi cần.

`@Primary` không làm các bean khác biến mất khỏi context. Nó chỉ cung cấp ưu tiên trong việc giải quyết dependency dạng đơn.

### 5.3. Inject tất cả implementation

Đôi khi ứng dụng muốn chạy qua tất cả plugin hoặc adapter. Spring có thể inject collection:

```java
@Service
public class PaymentGatewayRegistry {
    private final List<PaymentGateway> gateways;

    public PaymentGatewayRegistry(List<PaymentGateway> gateways) {
        this.gateways = List.copyOf(gateways);
    }

    public List<PaymentGateway> all() {
        return gateways;
    }
}
```

Các dạng phổ biến:

- `List<PaymentGateway>`: danh sách bean tương thích.
- `Set<PaymentGateway>`: tập bean.
- `Map<String, PaymentGateway>`: map từ bean name tới bean.
- `PaymentGateway[]`: mảng các bean phù hợp.

Nếu thứ tự xử lý có ý nghĩa, có thể dùng `@Order` hoặc `Ordered` theo cơ chế sắp xếp phù hợp. Không nên dựa vào thứ tự tình cờ của classpath hoặc tên file.

## 6. Dependency tùy chọn

Không phải mọi dependency đều bắt buộc. Nếu một thành phần thật sự tùy chọn, cần biểu diễn điều đó trong hợp đồng thay vì giả định bean luôn có.

### 6.1. Dùng `Optional<T>`

```java
@Service
public class WelcomeService {
    private final Optional<WelcomeMessageCustomizer> customizer;

    public WelcomeService(
            Optional<WelcomeMessageCustomizer> customizer) {
        this.customizer = customizer;
    }

    public String message(String name) {
        String result = "Welcome, " + name;
        return customizer
                .map(bean -> bean.customize(result))
                .orElse(result);
    }
}
```

Spring có thể inject `Optional.empty()` nếu không tìm thấy bean phù hợp, hoặc `Optional.of(bean)` nếu có. Đây là cách diễn đạt rõ ràng rằng dependency có thể không tồn tại.

### 6.2. Dùng `@Nullable`

```java
import org.springframework.lang.Nullable;

@Service
public class WelcomeService {
    private final WelcomeMessageCustomizer customizer;

    public WelcomeService(
            @Nullable WelcomeMessageCustomizer customizer) {
        this.customizer = customizer;
    }
}
```

Khi dependency không có, Spring có thể truyền `null`. Cần kiểm tra null trước khi sử dụng. Trong dự án dùng annotation nullability khác, hãy thống nhất một bộ annotation với compiler và công cụ phân tích mã.

### 6.3. Dùng `ObjectProvider<T>`

`ObjectProvider` hữu ích khi cần tra cứu bean muộn, lấy bean tùy chọn hoặc xử lý nhiều ứng viên:

```java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class OptionalReportService {
    private final ObjectProvider<ReportExporter> exporters;

    public OptionalReportService(ObjectProvider<ReportExporter> exporters) {
        this.exporters = exporters;
    }

    public void export(String reportId) {
        ReportExporter exporter = exporters.getIfAvailable();
        if (exporter != null) {
            exporter.export(reportId);
        }
    }
}
```

`getIfAvailable()` trả về bean nếu có, hoặc null nếu không có ứng viên; nếu có nhiều ứng viên mà không thể phân giải, lỗi ambiguity vẫn có thể xảy ra. Các phương thức như `getObject()`, `getIfAvailable()`, `getIfUnique()` và `orderedStream()` có ngữ nghĩa khác nhau, hãy chọn theo yêu cầu.

Không nên dùng `ObjectProvider` cho dependency luôn bắt buộc chỉ để tránh khai báo constructor. Điều đó làm dependency trở nên gián tiếp và che khuất hợp đồng của class.

## 7. `@Autowired(required = false)` có ý nghĩa gì?

Thuộc tính `required` mặc định là `true`. Với field hoặc method injection, `@Autowired(required = false)` cho phép bỏ qua điểm injection khi dependency không thỏa mãn điều kiện bắt buộc.

```java
@Component
public class DiagnosticReporter {
    private DiagnosticSink sink;

    @Autowired(required = false)
    public void setSink(DiagnosticSink sink) {
        this.sink = sink;
    }

    public void report(String message) {
        if (sink != null) {
            sink.write(message);
        }
    }
}
```

Nếu không có bean `DiagnosticSink`, setter có thể không được gọi và field giữ null. Class phải tự xử lý trường hợp đó.

Với constructor injection, `required = false` trên constructor có nhiều tham số có thể tạo ra lựa chọn constructor phức tạp hơn. Nếu chỉ muốn một tham số tùy chọn, thường nên dùng `Optional<T>`, `@Nullable` hoặc `ObjectProvider<T>` để thể hiện rõ ý định.

Đừng đánh dấu dependency bắt buộc là optional chỉ để ứng dụng khởi động qua lỗi thiếu bean. Nếu tính năng cần dependency đó mới hoạt động đúng, bỏ qua injection chỉ chuyển lỗi sang thời điểm chạy.

## 8. Injection trong `@Configuration` và `@Bean`

Không phải mọi dependency đều được inject qua class có stereotype. Trong Java configuration, Spring gọi phương thức `@Bean` và giải quyết tham số của phương thức như dependency.

```java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new BankPaymentGateway();
    }

    @Bean
    PaymentService paymentService(PaymentGateway paymentGateway) {
        return new PaymentService(paymentGateway);
    }
}
```

Không cần thêm `@Autowired` lên tham số `PaymentGateway` của bean method. Spring tự resolve tham số khi gọi factory method.

Với `proxyBeanMethods = false`, không nên gọi trực tiếp một bean method khác như một lời gọi Java để mong Spring thay thế bằng bean đã quản lý. Dùng tham số method injection như ví dụ trên để dependency rõ ràng.

Cũng có thể dùng component scan:

```java
@Component
class BankPaymentGateway implements PaymentGateway {}

@Service
class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
```

Hai cách đều có thể tạo bean graph. Hãy chọn cơ chế nhất quán và dễ kiểm soát trong module.

## 9. Lombok và constructor không cần `@Autowired`

Nhiều dự án dùng Lombok để giảm mã constructor:

```java
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
public class CustomerService {
    private final CustomerRepository repository;
    private final CustomerNotifier notifier;

    public void register(String customerId) {
        repository.save(customerId);
        notifier.registered(customerId);
    }
}
```

`@RequiredArgsConstructor` sinh constructor cho các field `final` chưa được khởi tạo và một số field `@NonNull` theo quy tắc Lombok. Class sau khi biên dịch có một constructor duy nhất; Spring Framework 4.3+ có thể tự dùng constructor đó mà không cần `@Autowired`.

Điều này phụ thuộc vào việc Lombok annotation processing đã được cấu hình trong build/IDE. Khi xem source, bạn có thể không thấy constructor tường minh, nhưng bytecode sau biên dịch có constructor do Lombok tạo.

Nếu class có thêm constructor do lập trình viên viết, cần kiểm tra số constructor thực tế sau khi Lombok sinh mã. Khi có nhiều constructor, quy tắc constructor đơn không còn áp dụng như trước. Đừng kết hợp nhiều annotation sinh constructor mà không hiểu kết quả biên dịch.

## 10. Vì sao constructor injection thường được khuyến nghị?

Constructor injection không chỉ là cách viết ngắn hơn field injection. Nó làm cho trạng thái cần thiết của object trở nên rõ ràng ngay tại thời điểm khởi tạo.

### 10.1. Bắt buộc dependency ngay khi tạo object

```java
@Service
public class TransferService {
    private final AccountRepository repository;
    private final FraudChecker fraudChecker;

    public TransferService(
            AccountRepository repository,
            FraudChecker fraudChecker) {
        this.repository = repository;
        this.fraudChecker = fraudChecker;
    }
}
```

Không thể tạo object qua constructor này mà không cung cấp hai dependency. Nếu bean graph thiếu một bean, lỗi xuất hiện khi Spring khởi tạo context, gần thời điểm cấu hình sai nhất.

### 10.2. Cho phép dùng `final`

Field `final` không thể bị gán lại sau khi constructor kết thúc. Nó không làm object trở thành immutable hoàn toàn, nhưng giữ tham chiếu dependency ổn định và giúp code dễ suy luận.

### 10.3. Unit test không phụ thuộc container

```java
@Test
void blocksTransferWhenFraudCheckFails() {
    AccountRepository repository = new InMemoryAccountRepository();
    FraudChecker checker = transfer -> true;

    TransferService service = new TransferService(repository, checker);

    assertThrows(
            FraudDetectedException.class,
            () -> service.transfer(new Transfer("A-1", "A-2", 100))
    );
}
```

Các kiểu `AccountRepository`, `FraudChecker`, `Transfer` và `FraudDetectedException` là các hợp đồng/domain type minh họa cần được định nghĩa trong ứng dụng. Điểm chính là test có thể tự tạo service với fake dependency mà không cần Spring.

### 10.4. Hạn chế dependency vòng

Giả sử `OrderService` cần `PaymentService`, còn `PaymentService` lại cần `OrderService`. Constructor injection tạo ra vòng phụ thuộc không thể khởi tạo theo thứ tự thông thường. Spring sẽ phát hiện và báo lỗi thay vì tạo hai object thiếu dependency.

Đây thường là tín hiệu cần xem lại thiết kế. Có thể trích xuất một dịch vụ điều phối, dùng domain event hoặc đảo hướng dependency qua interface phù hợp. Dùng `@Lazy` để trì hoãn một phía có thể giải quyết một số trường hợp kỹ thuật, nhưng không nên là cách mặc định để che giấu vòng phụ thuộc trong nghiệp vụ.

### 10.5. Constructor dài có thể là tín hiệu thiết kế

Nếu một service cần hàng chục dependency, đừng chuyển sang field injection chỉ để làm constructor ngắn lại. Hãy xem liệu lớp có đang gánh nhiều use case hoặc trách nhiệm không liên quan hay không. Có thể tách service theo use case hoặc tạo abstraction có ý nghĩa cho nhóm collaborator thực sự liên quan.

## 11. Lỗi thường gặp và cách xử lý

| Lỗi/triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Không có bean tương thích trong context | Kiểm tra đăng ký bean, component scan, import và profile |
| `NoUniqueBeanDefinitionException` | Nhiều bean cùng kiểu | Dùng `@Qualifier`, `@Primary` hoặc giới hạn implementation |
| `UnsatisfiedDependencyException` | Một dependency trong chuỗi bean graph không resolve được | Đọc nguyên nhân sâu nhất và lần theo constructor |
| `BeanCurrentlyInCreationException` | Có thể có dependency vòng | Xem lại hướng phụ thuộc và tách trách nhiệm |
| Field được inject vẫn null trong test | Test tự gọi `new`, không có container inject field | Dùng constructor injection hoặc Spring test khi cần kiểm tra wiring |
| Không inject được field `final` | Field injection không phù hợp với final field | Chuyển dependency sang constructor |
| Thêm `@Autowired` nhưng vẫn thiếu bean | Annotation không tạo implementation còn thiếu | Đăng ký implementation bằng component/configuration |
| Constructor được chọn không như mong đợi | Class có nhiều constructor | Đánh dấu constructor phù hợp hoặc giữ một constructor duy nhất |
| Ứng dụng chỉ lỗi khi gọi tính năng optional | Bỏ qua injection nhưng code không xử lý null | Dùng Optional/Provider hoặc cung cấp default bean |

Khi đọc stack trace, đừng dừng ở dòng `UnsatisfiedDependencyException` đầu tiên. Hãy đọc chuỗi `Caused by` để xác định bean hoặc kiểu dependency thực sự bị thiếu hoặc mơ hồ.

## 12. Một ví dụ hoàn chỉnh về constructor injection không có `@Autowired`

Ví dụ dưới đây kết nối REST controller với service và repository. Mỗi bean có một constructor, nên không cần `@Autowired` trên constructor.

### 12.1. Domain model

```java
package com.example.tasks.domain;

public record Task(String id, String title) {
    public Task {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
    }
}
```

### 12.2. Repository contract

```java
package com.example.tasks.domain;

import java.util.Optional;

public interface TaskRepository {
    void save(Task task);
    Optional<Task> findById(String id);
}
```

### 12.3. Repository implementation

```java
package com.example.tasks.persistence;

import com.example.tasks.domain.Task;
import com.example.tasks.domain.TaskRepository;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Repository;

@Repository
public class InMemoryTaskRepository implements TaskRepository {
    private final ConcurrentHashMap<String, Task> data = new ConcurrentHashMap<>();

    @Override
    public void save(Task task) {
        data.put(task.id(), task);
    }

    @Override
    public Optional<Task> findById(String id) {
        return Optional.ofNullable(data.get(id));
    }
}
```

### 12.4. Service

```java
package com.example.tasks.application;

import com.example.tasks.domain.Task;
import com.example.tasks.domain.TaskRepository;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class TaskService {
    private final TaskRepository repository;

    public TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    public Task create(String id, String title) {
        Task task = new Task(id, title);
        repository.save(task);
        return task;
    }

    public Optional<Task> find(String id) {
        return repository.findById(id);
    }
}
```

Constructor duy nhất của `TaskService` nhận `TaskRepository`. Spring tự inject `InMemoryTaskRepository` vì nó là bean implement interface đó và không có implementation cạnh tranh.

### 12.5. REST controller

```java
package com.example.tasks.web;

import com.example.tasks.application.TaskService;
import com.example.tasks.domain.Task;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/tasks")
public class TaskController {
    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @PostMapping("/{id}")
    public ResponseEntity<Task> create(
            @PathVariable String id,
            @RequestParam String title) {
        return ResponseEntity.ok(service.create(id, title));
    }

    @GetMapping("/{id}")
    public ResponseEntity<Task> find(@PathVariable String id) {
        return service.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```

### 12.6. Application entry point

```java
package com.example.tasks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TasksApplication {
    public static void main(String[] args) {
        SpringApplication.run(TasksApplication.class, args);
    }
}
```

Các package `web`, `application`, `persistence` là package con của `com.example.tasks`, nên component scan mặc định có thể tìm các stereotype trên. Nếu di chuyển một package ra ngoài phạm vi này, cần cấu hình scan hoặc đăng ký bean theo cách khác.

## 13. Phân biệt `@Autowired` với các annotation injection khác

Spring hỗ trợ một số annotation injection khác, đặc biệt khi làm việc với chuẩn Jakarta hoặc code cũ.

| Annotation | Nguồn | Ý nghĩa khái quát |
| --- | --- | --- |
| `@Autowired` | Spring Framework | Injection theo kiểu và quy tắc resolve của Spring |
| `@Inject` | Jakarta Dependency Injection | Annotation injection theo chuẩn Jakarta |
| `@Resource` | Jakarta Annotations | Thường resolve theo tên trước, sau đó theo kiểu theo quy tắc của nó |
| `@Qualifier` | Spring Framework | Thu hẹp/chỉ định bean ứng viên |
| `@Primary` | Spring Framework | Đánh dấu bean ưu tiên khi có nhiều ứng viên |

Trong ứng dụng Spring Boot, `@Autowired` phổ biến và tích hợp trực tiếp với Spring. Nếu dự án cần giảm phụ thuộc annotation Spring ở một số module, `@Inject` có thể là lựa chọn theo chuẩn, nhưng vẫn cần dependency API phù hợp và quy tắc container hỗ trợ. Không trộn các annotation tùy tiện khi chưa rõ thứ tự và semantics resolve.

`@Resource` thường phù hợp khi hợp đồng injection theo tên là điều mong muốn. Với constructor injection, `@Autowired` hoặc `@Inject` thường diễn đạt tự nhiên hơn; `@Resource` chủ yếu được dùng trên field hoặc setter trong nhiều ứng dụng.

## 14. Checklist suy nghĩ khi viết constructor cho Spring bean

Trước khi thêm `@Autowired`, hãy trả lời:

1. Class này có phải Spring bean không, hay chỉ là object Java/domain value?
2. Dependency nào là bắt buộc để object hoạt động đúng?
3. Class đã có đúng một constructor chưa?
4. Nếu chỉ có một constructor, có thể bỏ `@Autowired` không? Với Spring Framework 4.3+, câu trả lời là có.
5. Nếu có nhiều constructor, constructor nào Spring phải dùng? Có cần đánh dấu rõ bằng `@Autowired` không?
6. Nếu dependency tùy chọn, có thể biểu diễn bằng `Optional`, `@Nullable`, `ObjectProvider` hoặc default bean không?
7. Nếu có nhiều bean cùng kiểu, đã chọn bằng qualifier/primary hay chưa?
8. Unit test có thể tạo class bằng `new` với fake dependency không?
9. Nếu Spring không tìm thấy bean, implementation có thực sự được đăng ký và package có nằm trong vùng scan không?
10. Có dependency vòng cho thấy các trách nhiệm đang phụ thuộc lẫn nhau không?

Không cần thêm `@Autowired` chỉ vì thấy nó trong một đoạn code mẫu. Hãy dùng annotation khi nó cung cấp thông tin cần thiết cho quy tắc lựa chọn injection, và để constructor đơn tự nói lên hợp đồng dependency khi không có sự mơ hồ.

## 15. Ghi nhớ

`@Autowired` là công cụ yêu cầu Spring giải quyết dependency tại constructor, field hoặc method. Với **một constructor duy nhất**, Spring Framework 4.3 trở lên tự dùng constructor đó, nên annotation không bắt buộc. Đây là lý do nhiều service/controller hiện đại chỉ khai báo constructor nhận dependency mà không gắn annotation.

Trong thiết kế ứng dụng, ưu tiên constructor injection cho dependency bắt buộc: nó thể hiện rõ hợp đồng, hỗ trợ field `final`, phát hiện thiếu dependency sớm và giúp unit test không cần khởi động container. Dùng setter hoặc các kiểu optional khi dependency thực sự không bắt buộc. Nếu có nhiều bean cùng kiểu, giải quyết lựa chọn bằng `@Qualifier`, `@Primary` hoặc cấu hình phù hợp; nếu có nhiều constructor, làm rõ constructor được Spring sử dụng.

Cuối cùng, `@Autowired` không tự tạo bean. Bean vẫn cần được đăng ký trong `ApplicationContext` qua component scanning, `@Bean`, `@Import`, auto-configuration hoặc cơ chế phù hợp khác. Hiểu rõ sự khác nhau giữa đăng ký bean và inject dependency là nền tảng để đọc, viết và chẩn đoán ứng dụng Spring Boot.

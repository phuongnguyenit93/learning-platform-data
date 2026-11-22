# `@TestBean` và phương thức tạo đối tượng thay thế

Trong kiểm thử Spring, đôi khi ta cần thay một bean thật bằng một implementation do test cung cấp. Ví dụ, `OrderService` dùng `PaymentGateway` để gửi yêu cầu thanh toán; integration test muốn giữ nguyên `OrderService` và cấu hình Spring nhưng thay gateway thật bằng một fake có thể trả kết quả thành công hoặc thất bại theo kịch bản. Spring Framework 6.2 cung cấp `@TestBean` để đăng ký một instance thay thế được tạo từ factory method của test.

`@TestBean` đánh dấu một field trong test class. Spring tìm bean cần thay theo kiểu của field, qualifier hoặc tên bean; sau đó gọi một phương thức factory `static`, không có tham số, để tạo instance thay thế. Instance đó được đưa vào `ApplicationContext` và cũng được inject vào field của test. Nhờ vậy, các bean khác trong context sử dụng implementation thay thế thông qua dependency injection như bình thường.

## 1. `@TestBean` giải quyết vấn đề gì?

Một integration test thường cần giữ nhiều phần của ứng dụng hoạt động thật, nhưng một dependency cụ thể lại cần được điều khiển. Có thể đó là cổng thanh toán, dịch vụ vận chuyển, hệ thống gửi email hoặc một client gọi API bên ngoài.

Ví dụ, cấu hình production đăng ký gateway:

```java
@Configuration
class PaymentConfiguration {
    @Bean
    PaymentGateway paymentGateway(PaymentHttpClient client) {
        return new RemotePaymentGateway(client);
    }
}
```

`OrderService` nhận gateway qua constructor:

```java
@Service
class OrderService {
    private final PaymentGateway paymentGateway;

    OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    PaymentResult checkout(Order order) {
        return paymentGateway.charge(
                new PaymentRequest(order.id(), order.total()));
    }
}
```

Trong test, ta muốn dùng `OrderService` thật nhưng kiểm soát kết quả từ gateway. Có thể viết một fake:

```java
final class FakePaymentGateway implements PaymentGateway {
    private PaymentResult nextResult = PaymentResult.approved("test-payment-1");

    void setNextResult(PaymentResult result) {
        this.nextResult = result;
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        return nextResult;
    }
}
```

`@TestBean` cho phép đăng ký fake này để thay bean gateway trong test context. Test không phải tự tạo toàn bộ `OrderService` hoặc dựng một `ApplicationContext` riêng chỉ để thay một dependency.

## 2. Cú pháp cơ bản

`@TestBean` thuộc package:

```java
import org.springframework.test.context.bean.override.convention.TestBean;
```

Annotation được dùng trên field không `static` trong test class. Nếu không chỉ định tên phương thức factory, Spring tìm một static method không tham số có tên trùng với tên field hoặc tên bean được chỉ định.

```java
@SpringBootTest
class OrderServiceIntegrationTest {
    @TestBean
    private PaymentGateway paymentGateway;

    @Autowired
    private OrderService orderService;

    static PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }

    @Test
    void completesCheckoutWithFakeGateway() {
        PaymentResult result = orderService.checkout(
                new Order("order-42", new BigDecimal("30.00")));

        assertThat(result.approved()).isTrue();
        assertThat(paymentGateway).isInstanceOf(FakePaymentGateway.class);
    }
}
```

Trong ví dụ, field `paymentGateway` yêu cầu Spring thay bean phù hợp bằng instance do `paymentGateway()` tạo ra. Phương thức factory phải `static`, không nhận tham số và trả về kiểu tương thích với `PaymentGateway`.

Việc thay thế diễn ra trong bean factory của context. Các injection point khác đang yêu cầu bean đó, chẳng hạn constructor của `OrderService`, cũng nhận instance thay thế. Field được đánh dấu `@TestBean` trong test class cũng được inject instance tương ứng để test có thể cấu hình fake hoặc quan sát nó.

`@TestBean` được giới thiệu trong Spring Framework 6.2. Nếu dự án dùng Spring Framework cũ hơn, annotation này sẽ không có trong classpath. Với Spring Boot, cần dùng phiên bản Boot quản lý Spring Framework 6.2 trở lên; không nâng riêng `spring-test` một cách tùy tiện để tạo lệch phiên bản giữa các module Spring.

## 3. Quy tắc đặt tên factory method

Factory method là một phần quan trọng của `@TestBean`. Theo mặc định, Spring suy ra tên method từ field được đánh dấu hoặc tên bean được chỉ định.

Ví dụ đơn giản:

```java
@TestBean
private CustomerRepository customerRepository;

static CustomerRepository customerRepository() {
    return new InMemoryCustomerRepository();
}
```

Tên field là `customerRepository`, nên factory method mặc định là `customerRepository()`. Phương thức phải là static và có đúng một kết quả trả về tương thích với kiểu field.

Nếu annotation chỉ định tên bean:

```java
@TestBean(name = "primaryPaymentGateway")
private PaymentGateway gateway;

static PaymentGateway primaryPaymentGateway() {
    return new FakePaymentGateway();
}
```

Khi `name` được chỉ định và `methodName` bỏ trống, tên bean được dùng để suy ra tên factory method. Trong ví dụ, Spring tìm `primaryPaymentGateway()`.

### 3.1. Chỉ định `methodName`

Để tách tên field khỏi tên factory method hoặc làm ý định rõ ràng hơn, dùng thuộc tính `methodName`:

```java
@TestBean(methodName = "createFakePaymentGateway")
private PaymentGateway paymentGateway;

static PaymentGateway createFakePaymentGateway() {
    return new FakePaymentGateway();
}
```

`methodName` chỉ định tên phương thức static mà Spring cần tìm. Phương thức vẫn phải không có tham số và trả về kiểu tương thích với field.

Có thể kết hợp `name` và `methodName`:

```java
@TestBean(
        name = "paymentGateway",
        methodName = "createSandboxGateway",
        enforceOverride = true)
private PaymentGateway gateway;

static PaymentGateway createSandboxGateway() {
    return new SandboxPaymentGateway();
}
```

Ở đây, `paymentGateway` là bean được thay; `createSandboxGateway()` là factory method. Tên field `gateway` không còn được dùng để chọn bean vì `name` đã chỉ định rõ bean cần thay.

### 3.2. Factory method ở class khác

Factory method có thể được đặt trong test class, superclass, interface mà test class triển khai hoặc enclosing class hierarchy đối với nested test. Nếu muốn dùng một utility class bên ngoài, có thể chỉ định tên đầy đủ theo cú pháp `fully.qualified.ClassName#methodName`:

```java
@TestBean(methodName = "com.example.test.TestBeanFactories#createPaymentGateway")
private PaymentGateway paymentGateway;
```

Class tiện ích:

```java
package com.example.test;

public final class TestBeanFactories {
    private TestBeanFactories() {
    }

    public static PaymentGateway createPaymentGateway() {
        return new FakePaymentGateway();
    }
}
```

Cách này hữu ích khi nhiều test class dùng chung một factory phức tạp hoặc khi muốn giữ test class tập trung vào kịch bản. Factory bên ngoài vẫn phải là static method, không tham số và trả về kiểu tương thích.

### 3.3. Phạm vi tìm kiếm và visibility

Spring tìm factory method trong class khai báo field `@TestBean`, các superclass và interface được triển khai. Nếu field nằm trong nested test class, Spring còn tìm trong enclosing class hierarchy. Điều này cho phép đặt factory dùng chung ở base test class hoặc enclosing class khi cấu trúc test phù hợp.

Field và factory method không bắt buộc phải `public`. Chúng có thể là `private`, package-private, `protected` hoặc `public`, tùy quy ước dự án. Dù vậy, giữ factory ở phạm vi dễ đọc và đặt tên rõ ràng giúp người bảo trì nhận ra ngay cách tạo bean thay thế.

Nếu Spring không tìm thấy factory method, có nhiều method trùng tên phù hợp hoặc method không đáp ứng chữ ký yêu cầu, context sẽ không khởi tạo được. Hãy kiểm tra tên, `static`, số tham số và kiểu trả về trước khi điều chỉnh cấu hình bean.

## 4. Chọn bean cần thay theo kiểu hoặc tên

Mặc định, Spring dùng kiểu của field `@TestBean` để tìm bean definition phù hợp trong context. Nếu chỉ có một bean cùng kiểu, việc chọn thường trực tiếp. Nếu có nhiều bean, cần thu hẹp lựa chọn bằng qualifier hoặc tên bean.

### 4.1. Thay theo kiểu

```java
@TestBean
private PaymentGateway paymentGateway;

static PaymentGateway paymentGateway() {
    return new FakePaymentGateway();
}
```

Spring tìm bean có kiểu phù hợp với `PaymentGateway`. Nếu context chỉ có một ứng viên, bean đó được thay.

### 4.2. Dùng `@Qualifier` khi có nhiều bean cùng kiểu

Giả sử ứng dụng có hai gateway:

```java
@Bean
@Qualifier("primary")
PaymentGateway primaryGateway() {
    return new RemotePaymentGateway(primaryClient);
}

@Bean
@Qualifier("backup")
PaymentGateway backupGateway() {
    return new RemotePaymentGateway(backupClient);
}
```

Test có thể chỉ rõ bean cần thay bằng qualifier:

```java
@TestBean
@Qualifier("primary")
private PaymentGateway paymentGateway;

static PaymentGateway paymentGateway() {
    return new FakePaymentGateway();
}
```

Nếu không có qualifier, tên field được dùng làm qualifier dự phòng khi cần phân biệt các candidate. Điều đó có nghĩa field name có thể ảnh hưởng đến bean được chọn. Hãy dùng tên field thể hiện rõ bean mục tiêu và tránh đổi tên tùy tiện nếu việc chọn bean dựa vào tên.

### 4.3. Thay theo tên với `name` hoặc `value`

Khi biết chính xác bean name, có thể dùng `name`:

```java
@TestBean(name = "backupGateway")
private PaymentGateway gateway;

static PaymentGateway backupGateway() {
    return new FakePaymentGateway();
}
```

`value` là alias của `name`, nên có thể viết ngắn:

```java
@TestBean("backupGateway")
private PaymentGateway gateway;
```

Khi dùng dạng ngắn `value`, factory method mặc định được suy ra từ tên bean nếu không chỉ định `methodName`. Việc chọn theo tên đặc biệt hữu ích khi có nhiều bean cùng interface và test cần thay đúng một bean.

## 5. `enforceOverride`: bắt buộc bean phải tồn tại

Theo mặc định, `@TestBean` dùng chiến lược thay thế hoặc tạo mới. Nếu không tìm thấy bean tương ứng trong context, Spring có thể đăng ký bean được tạo từ factory method như một bean mới.

Điều này tiện lợi khi test configuration không có bean production tương ứng, nhưng có thể che giấu lỗi cấu hình. Ví dụ, test dự định thay `PaymentGateway` đang tồn tại; nếu bean production bị loại khỏi context do profile hoặc component scan sai, test vẫn có thể chạy với một bean mới và không chứng minh được việc override đã diễn ra.

Khi muốn test thất bại nếu không có bean để thay, đặt `enforceOverride = true`:

```java
@TestBean(enforceOverride = true)
private PaymentGateway paymentGateway;

static PaymentGateway paymentGateway() {
    return new FakePaymentGateway();
}
```

Với cấu hình này, Spring yêu cầu bean mục tiêu đã tồn tại. Nếu không tìm thấy bean phù hợp, quá trình tạo context thất bại. Đây là lựa chọn rõ ràng khi mục tiêu của test là thay một bean production đã đăng ký.

| Cấu hình | Khi bean mục tiêu tồn tại | Khi bean mục tiêu không tồn tại |
|---|---|---|
| `@TestBean` | Thay bean bằng instance factory | Tạo bean mới từ factory |
| `@TestBean(enforceOverride = true)` | Thay bean bằng instance factory | Báo lỗi khi khởi tạo context |

Hãy chọn theo ý định của test. Nếu test cần cung cấp một collaborator test-only mà context không có sẵn, mặc định tạo mới có thể phù hợp. Nếu test phải chứng minh một bean cụ thể được thay, `enforceOverride = true` giúp phát hiện cấu hình thiếu.

## 6. Factory method nên tạo loại đối tượng nào?

Factory method có thể trả về một fake, stub hoặc implementation test chuyên biệt. Nó không cần là Mockito mock. Đây là điểm khác biệt hữu ích: `@TestBean` tập trung vào việc tạo instance thay thế bằng một phương thức Java thông thường.

### 6.1. Fake có hành vi đơn giản

```java
final class InMemoryCustomerRepository implements CustomerRepository {
    private final Map<Long, Customer> customers = new HashMap<>();

    @Override
    public Optional<Customer> findById(Long id) {
        return Optional.ofNullable(customers.get(id));
    }

    @Override
    public Customer save(Customer customer) {
        customers.put(customer.id(), customer);
        return customer;
    }
}
```

Test có thể thay repository bằng fake:

```java
@SpringBootTest
class CustomerServiceIntegrationTest {
    @TestBean
    private CustomerRepository customerRepository;

    @Autowired
    private CustomerService customerService;

    static CustomerRepository customerRepository() {
        return new InMemoryCustomerRepository();
    }
}
```

Fake thực hiện một phần hợp đồng repository bằng bộ nhớ. Nó giúp kiểm tra service và wiring Spring nhưng không xác nhận SQL, mapping hoặc transaction của database thật. Nếu mục tiêu là kiểm tra persistence, hãy dùng repository integration test với database phù hợp.

### 6.2. Stub trả kết quả theo kịch bản

```java
final class StubInventoryClient implements InventoryClient {
    private InventoryStatus nextStatus = InventoryStatus.AVAILABLE;

    void returnStatus(InventoryStatus status) {
        this.nextStatus = status;
    }

    @Override
    public InventoryStatus check(String sku) {
        return nextStatus;
    }
}
```

Factory method tạo stub:

```java
@TestBean
private InventoryClient inventoryClient;

static InventoryClient inventoryClient() {
    return new StubInventoryClient();
}
```

Test có thể ép kết quả bằng cách truy cập field được inject. Vì bean thuộc context singleton, hãy chú ý trạng thái stub có thể được chia sẻ nếu context được cache hoặc tái sử dụng.

### 6.3. Factory method có thể dùng builder

Khi fake cần nhiều cấu hình, builder giúp thể hiện dữ liệu mặc định:

```java
static PaymentGateway paymentGateway() {
    return FakePaymentGateway.builder()
            .defaultResult(PaymentResult.approved("test-payment"))
            .supportsRefunds(true)
            .build();
}
```

Factory method nên tập trung tạo instance với cấu hình test. Nếu việc tạo fake cần nhiều bước hoặc dữ liệu phụ thuộc vào test method, hãy giữ factory đơn giản và cấu hình fake trong từng test qua API tường minh.

## 7. Vòng đời của bean thay thế

`@TestBean` tạo bean trong `ApplicationContext`, không tạo một đối tượng mới mỗi lần test method chạy. Bean được quản lý theo vòng đời của context và thường là singleton. Spring thay bean definition trong bean factory; các injection point sử dụng bean đó sẽ nhận instance thay thế.

Điều này có nghĩa:

- Factory method được dùng khi context được tạo và bean override được đăng ký.
- Field `@TestBean` trong test nhận instance thay thế.
- Các service khác trong context cũng nhận instance đó qua dependency injection.
- Nếu context được Spring Test cache và tái sử dụng, bean thay thế có thể tồn tại qua nhiều test method hoặc test class tương thích.
- Thay đổi mutable state trong fake có thể ảnh hưởng test chạy sau nếu không reset.

Không đặt dữ liệu riêng của từng test method trong một fake singleton mà không có cơ chế reset. Có thể tạo API `reset()` và gọi trong `@BeforeEach`, hoặc thiết kế fake stateless với hành vi cố định. Nếu fake có state lớn và không thể khôi phục an toàn, hãy cân nhắc phạm vi context phù hợp.

Ví dụ reset fake:

```java
@SpringBootTest
class NotificationServiceIntegrationTest {
    @TestBean
    private NotificationGateway notificationGateway;

    @Autowired
    private NotificationService notificationService;

    private static RecordingNotificationGateway notificationGateway() {
        return new RecordingNotificationGateway();
    }

    @BeforeEach
    void resetGateway() {
        ((RecordingNotificationGateway) notificationGateway).reset();
    }
}
```

Ở ví dụ này, factory trả về implementation cụ thể nhưng field có kiểu interface. Việc ép kiểu trong setup cho thấy test đang phụ thuộc vào fake implementation. Nếu phải ép kiểu ở nhiều nơi, có thể khai báo field với kiểu fake cụ thể nếu kiểu đó tương thích và việc chọn bean theo type vẫn rõ ràng, hoặc giữ một helper method trả về fake được cast một lần.

## 8. `@TestBean` trong context hierarchy

Một số ứng dụng dùng `@ContextHierarchy` để tạo parent context và child context. Theo mặc định, bean override được áp dụng cho các context trong hierarchy. Điều này có thể không phù hợp nếu bean chỉ tồn tại ở một cấp hoặc cùng kiểu bean xuất hiện ở nhiều cấp.

Spring Framework 6.2.6 bổ sung thuộc tính `contextName` cho `@TestBean`, cho phép giới hạn override vào một context hierarchy level có tên tương ứng:

```java
@ContextHierarchy({
        @ContextConfiguration(name = "root", classes = RootConfig.class),
        @ContextConfiguration(name = "web", classes = WebConfig.class)
})
class WebIntegrationTest {
    @TestBean(contextName = "root")
    private PaymentGateway paymentGateway;

    static PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

`contextName` phải khớp với `name` trên `@ContextConfiguration` của cấp cần thay. Nếu dự án dùng Spring Framework 6.2.0 đến 6.2.5, thuộc tính này chưa có; hãy kiểm tra phiên bản trước khi sử dụng.

Không dùng `contextName` khi test chỉ có một context. Với cấu hình đơn giản, để trống thuộc tính này giúp annotation gọn hơn.

## 9. `@TestBean` và các annotation thay bean khác

Spring Framework 6.2 chuẩn hóa cơ chế bean overriding trong Spring Test. `@TestBean`, `@MockitoBean` và `@MockitoSpyBean` đều có thể thay bean trong test context nhưng tạo instance theo cách khác nhau.

| Annotation | Instance thay thế | Mục đích thường gặp |
|---|---|---|
| `@TestBean` | Factory method static do test cung cấp | Fake hoặc implementation tùy chỉnh |
| `@MockitoBean` | Mockito mock | Stub response và verify tương tác |
| `@MockitoSpyBean` | Spy bọc bean thật | Giữ hành vi thật nhưng quan sát hoặc thay một phần hành vi |

Ví dụ `@MockitoBean`:

```java
@SpringBootTest
class OrderServiceMockBeanTest {
    @MockitoBean
    private PaymentGateway paymentGateway;

    @Autowired
    private OrderService orderService;

    @Test
    void usesConfiguredGatewayResponse() {
        when(paymentGateway.charge(any(PaymentRequest.class)))
                .thenReturn(PaymentResult.approved("mock-payment"));

        PaymentResult result = orderService.checkout(order());

        assertThat(result.approved()).isTrue();
        verify(paymentGateway).charge(any(PaymentRequest.class));
    }
}
```

Ví dụ này dùng Mockito mock vì test cần stub và verify. Nếu cần một fake có thuật toán hoặc dữ liệu trong bộ nhớ, `@TestBean` thường tự nhiên hơn. Nếu muốn quan sát một bean thật, `@MockitoSpyBean` có thể phù hợp.

Không cần thay mọi collaborator bằng `@TestBean`. Một fake tự viết có giá trị khi nó mô phỏng một hợp đồng có ý nghĩa; nếu test chỉ cần một phản hồi đơn giản và xác nhận lời gọi, `@MockitoBean` có thể ngắn hơn.

## 10. So sánh với `@TestConfiguration` và `@Import`

`@TestConfiguration` khai báo cấu hình bổ sung cho test; `@TestBean` trực tiếp đánh dấu field cần thay và factory method tạo instance. Hai cách có thể đạt kết quả tương tự nhưng cách tổ chức khác nhau.

Với `@TestConfiguration`:

```java
@TestConfiguration
class PaymentTestConfiguration {
    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}

@SpringBootTest
@Import(PaymentTestConfiguration.class)
class PaymentIntegrationTest {
    @Autowired
    private OrderService orderService;
}
```

Với `@TestBean`:

```java
@SpringBootTest
class PaymentIntegrationTest {
    @TestBean
    private PaymentGateway paymentGateway;

    static PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }

    @Autowired
    private OrderService orderService;
}
```

`@TestConfiguration` phù hợp khi muốn gom nhiều bean, cấu hình property, factory hoặc infrastructure test vào một lớp cấu hình. `@TestBean` phù hợp khi mục tiêu là thay một bean cụ thể và muốn đặt factory ngay cạnh test sử dụng nó.

Nếu có nhiều test cùng dùng một fake configuration phức tạp, top-level `@TestConfiguration` kết hợp `@Import` có thể dễ tái sử dụng hơn. Nếu chỉ thay một collaborator, `@TestBean` làm ý định ngắn gọn và trực tiếp.

## 11. Context caching và tên field `@TestBean`

Spring TestContext Framework cache `ApplicationContext` dựa trên cấu hình đã hợp nhất. Các bean override là một phần của cấu hình test và metadata của field, bao gồm qualifier/name, có thể ảnh hưởng đến việc xác định context cache key.

Nếu nhiều test class cùng thay một bean theo cùng cách, hãy giữ tên field và qualifier nhất quán. Ví dụ, cùng thay bean `paymentGateway` thì nên dùng field `paymentGateway` ở các class liên quan, thay vì class này đặt `gateway`, class khác đặt `fakeGateway` trong khi không có lý do về cấu hình.

Việc đổi tên field có thể làm cách Spring suy ra candidate khác đi hoặc tạo cấu hình override khác, dẫn đến context cache miss và khởi động context mới. Đừng đổi tên field một cách tùy tiện nếu nó đang tham gia chọn bean.

Context cache cũng có nghĩa fake singleton có thể được chia sẻ. Hãy giữ fake không chứa state mutable theo test method hoặc reset state trong `@BeforeEach`. Nếu cần một context riêng vì test thay đổi trạng thái context không thể khôi phục, có thể dùng `@DirtiesContext` với phạm vi phù hợp. Không dùng annotation này chỉ để xóa dữ liệu database hoặc file.

## 12. Những bean nào có thể được thay?

`@TestBean` thay bean singleton. Nếu bean mục tiêu có scope không phải singleton, việc override sẽ gây lỗi. Điều này phù hợp với mô hình test context: một instance thay thế được đăng ký trong bean factory và chia sẻ qua các injection point.

Nếu ứng dụng có prototype hoặc request-scoped bean, hãy cân nhắc cách test đúng với scope đó:

- Với prototype, tạo factory/provider phù hợp hoặc kiểm tra logic ở cấp component mà không thay bean bằng singleton `@TestBean`.
- Với request/session scope, dùng web test context và cơ chế scope tương ứng; `@TestBean` không biến bean request thành một bean singleton hợp lệ để thay tùy tiện.
- Với `FactoryBean`, khi override bean do `FactoryBean` tạo, Spring thay `FactoryBean` bằng singleton bean tương ứng với giá trị factory method trả về.

Trước khi dùng `@TestBean`, hãy xác định bean cần thay là singleton và biết rõ bean name/type mà context đang đăng ký.

## 13. Lỗi thường gặp và cách xử lý

### Không tìm thấy factory method

Kiểm tra tên method mặc định có trùng field name hoặc bean name không. Nếu dùng tên khác, khai báo `methodName`. Xác nhận method là `static`, không có tham số và nằm trong class hierarchy mà Spring tìm kiếm được; nếu ở class khác, dùng cú pháp đầy đủ `ClassName#methodName`.

### Factory method không tương thích kiểu

Kiểu trả về phải tương thích với kiểu field được đánh dấu. Nếu field là `PaymentGateway`, factory có thể trả `FakePaymentGateway` vì fake implement interface đó. Một kiểu không liên quan sẽ làm context không khởi tạo được.

### Có nhiều bean cùng kiểu

Dùng `@Qualifier` hoặc `name` để chỉ rõ candidate. Nếu không, Spring có thể không xác định được bean cần thay hoặc dùng field name làm qualifier dự phòng.

### Test vẫn chạy dù bean production bị thiếu

Mặc định, `@TestBean` có thể tạo bean mới nếu không tìm thấy bean tương ứng. Nếu test phải thay bean có sẵn, dùng `enforceOverride = true` để biến trường hợp thiếu bean thành lỗi cấu hình.

### Bean fake giữ state giữa các test

Bean thay thế thuộc context và có thể được cache. Reset fake trong `@BeforeEach`, tạo fake stateless hoặc tách context khi có lý do thực sự.

### Dùng annotation trên field `static`

`@TestBean` được đặt trên field instance không `static`. Factory method mới là phương thức `static`. Hãy phân biệt hai yêu cầu này.

### Dùng `@TestBean` với bean prototype

Chỉ singleton bean có thể được override. Kiểm tra scope của bean mục tiêu và chọn cách test phù hợp nếu bean có scope khác.

### Dùng nhầm `@TestBean` thay cho mock

`@TestBean` không tự cung cấp API `when`, `verify` của Mockito. Nếu cần stub/verify tương tác bằng Mockito, dùng `@MockitoBean`; nếu cần fake có hành vi riêng, dùng `@TestBean`.

### Override sai cấp trong context hierarchy

Nếu cùng kiểu bean xuất hiện ở nhiều cấp, dùng `contextName` trên Spring Framework 6.2.6 trở lên để giới hạn override vào đúng level có tên tương ứng.

## 14. Quy trình sử dụng `@TestBean`

Khi cần thay một bean trong Spring integration test, hãy thực hiện theo trình tự:

1. Xác định bean production cần thay và kiểm tra kiểu, bean name, qualifier cùng scope.
2. Khai báo field instance `@TestBean` với kiểu phù hợp.
3. Chọn bean theo type mặc định, qualifier hoặc `name` nếu context có nhiều candidate.
4. Viết factory method `static`, không tham số, trả về fake/stub có kiểu tương thích.
5. Để Spring suy ra method từ field/bean name hoặc chỉ định rõ `methodName`.
6. Dùng `enforceOverride = true` nếu test cần bảo đảm bean production thực sự tồn tại trước khi thay.
7. Chạy kịch bản qua bean thật đang được autowire và xác nhận hành vi ở ranh giới nghiệp vụ.
8. Nếu fake có state, reset giữa các test method vì context có thể được cache.
9. Nếu dùng context hierarchy, xác định level cần override và dùng `contextName` khi phiên bản Spring hỗ trợ.

Factory method nên dễ đọc và có trách nhiệm tạo đúng một instance thay thế. Hãy giữ fake nhỏ, mô phỏng đúng hợp đồng mà service cần và tránh đưa logic nghiệp vụ phức tạp vào test factory.

## 15. Ví dụ tổng hợp: thay gateway và kiểm tra cả thành công lẫn từ chối

Giả sử `PaymentService` gọi một `PaymentGateway`. Test muốn giữ service, repository và cấu hình Spring thật, nhưng điều khiển phản hồi gateway.

```java
final class ConfigurablePaymentGateway implements PaymentGateway {
    private PaymentResult nextResult;
    private final List<PaymentRequest> requests = new ArrayList<>();

    ConfigurablePaymentGateway() {
        this.nextResult = PaymentResult.approved("test-payment");
    }

    void returnResult(PaymentResult result) {
        this.nextResult = result;
    }

    List<PaymentRequest> requests() {
        return List.copyOf(requests);
    }

    void reset() {
        requests.clear();
        nextResult = PaymentResult.approved("test-payment");
    }

    @Override
    public PaymentResult charge(PaymentRequest request) {
        requests.add(request);
        return nextResult;
    }
}
```

Test class:

```java
@SpringBootTest
class PaymentServiceIntegrationTest {
    @TestBean(enforceOverride = true)
    private PaymentGateway paymentGateway;

    @Autowired
    private PaymentService paymentService;

    private ConfigurablePaymentGateway fakeGateway() {
        return (ConfigurablePaymentGateway) paymentGateway;
    }

    static PaymentGateway paymentGateway() {
        return new ConfigurablePaymentGateway();
    }

    @BeforeEach
    void resetGateway() {
        fakeGateway().reset();
    }

    @Test
    void completesPaymentWhenGatewayApproves() {
        fakeGateway().returnResult(
                PaymentResult.approved("payment-42"));

        PaymentResult result = paymentService.pay(
                new PaymentRequest("order-42", new BigDecimal("30.00")));

        assertThat(result.approved()).isTrue();
        assertThat(fakeGateway().requests()).hasSize(1);
        assertThat(fakeGateway().requests().get(0).orderId())
                .isEqualTo("order-42");
    }

    @Test
    void returnsDeclinedResultWhenGatewayRejects() {
        fakeGateway().returnResult(PaymentResult.declined("insufficient-funds"));

        PaymentResult result = paymentService.pay(
                new PaymentRequest("order-43", new BigDecimal("90.00")));

        assertThat(result.approved()).isFalse();
        assertThat(result.reason()).isEqualTo("insufficient-funds");
    }
}
```

Trong ví dụ, factory method là static và trả về một `ConfigurablePaymentGateway`. Field được khai báo theo interface `PaymentGateway` để Spring chọn bean theo kiểu và để service tiếp tục phụ thuộc vào abstraction. Helper `fakeGateway()` chỉ ép kiểu tại một nơi để test điều khiển fake. `@BeforeEach` reset state vì bean thay thế có vòng đời theo context và có thể được dùng lại giữa các test method.

Nếu muốn tránh ép kiểu, có thể khai báo field với kiểu cụ thể `ConfigurablePaymentGateway` và dùng `@Qualifier` hoặc `name` để xác định bean interface cần thay. Khi đó cần bảo đảm kiểu field vẫn tương thích với bean mục tiêu và không tạo ra lựa chọn mơ hồ trong context.

## 16. Nguyên tắc cần nhớ

- `@TestBean` thuộc Spring Framework 6.2 và dùng trên field instance trong test class.
- Spring tạo bean thay thế từ một factory method `static`, không tham số, có kiểu trả về tương thích với field.
- Mặc định, tên factory method được suy ra từ field name hoặc bean name; dùng `methodName` khi cần tên khác.
- Bean được chọn theo kiểu, qualifier hoặc tên được chỉ định qua `name`/`value`.
- `enforceOverride = true` buộc bean mục tiêu phải tồn tại; mặc định Spring có thể tạo bean mới nếu không tìm thấy candidate.
- Factory method có thể nằm trong test class, superclass, interface, enclosing hierarchy hoặc class bên ngoài được tham chiếu bằng `ClassName#methodName`.
- Bean thay thế được đưa vào `ApplicationContext`, nên các injection point khác cũng nhận instance đó.
- Chỉ singleton bean có thể được thay; fake có state cần được reset khi context được tái sử dụng.
- Dùng `@TestBean` cho fake/custom implementation; dùng `@MockitoBean` khi cần Mockito stubbing/verification và `@MockitoSpyBean` khi cần spy bean thật.
- Với context hierarchy, dùng `contextName` từ Spring Framework 6.2.6 khi cần giới hạn override vào một cấp.

`@TestBean` giúp thay một collaborator bằng instance được tạo theo factory method của test mà vẫn giữ phần còn lại của Spring context hoạt động. Khi chọn đúng bean, đặt tên factory rõ ràng và quản lý state của fake theo vòng đời context, integration test có thể kiểm soát dependency bên ngoài mà vẫn kiểm tra wiring và hành vi của các service thật.

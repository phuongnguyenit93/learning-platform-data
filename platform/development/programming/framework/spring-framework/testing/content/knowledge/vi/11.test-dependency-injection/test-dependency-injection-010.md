# Nhận biết lỗi thiếu bean khác với lỗi assertion

Khi một bài kiểm thử Spring thất bại, cần xác định nó thất bại ở giai đoạn nào. Một lỗi thiếu bean thường xảy ra khi Spring tạo `ApplicationContext` hoặc inject dependency cho test và bean đang được yêu cầu không thể được tìm thấy. Lỗi assertion xảy ra sau khi test method đã chạy đến câu lệnh kiểm tra nhưng giá trị thực tế không khớp với kết quả mong đợi.

Hai loại lỗi có thể xuất hiện trong cùng một dự án, thậm chí cùng một test class, nhưng nguyên nhân và cách xử lý khác nhau. Nếu nhầm lỗi khởi tạo context thành lỗi nghiệp vụ, ta có thể sửa assertion trong khi test chưa từng chạy. Ngược lại, nếu coi mọi test thất bại là lỗi cấu hình bean, ta có thể bỏ qua một lỗi thực sự trong hành vi ứng dụng.

## 1. Nhìn theo vòng đời của một Spring test

Một test tích hợp Spring thường đi qua các giai đoạn sau:

```text
Build và discovery test
          |
          v
Tạo / lấy ApplicationContext từ cache
          |
          v
Tạo test instance và inject dependency
          |
          v
Chạy lifecycle callbacks (@BeforeEach, ...)
          |
          v
Chạy test method
          |
          v
Thực hiện assertion
          |
          v
Callbacks kết thúc và dọn dẹp
```

Lỗi thiếu bean thường nằm ở giai đoạn tạo context hoặc inject dependency, tức là trước khi phần thân test method thực hiện assertion. Lỗi assertion nằm ở giai đoạn kiểm tra kết quả sau khi hành động được gọi.

Không phải mọi lỗi trước assertion đều là lỗi thiếu bean. Ví dụ, test không được tìm thấy, thiếu extension của JUnit, lỗi trong `@BeforeEach`, lỗi kết nối database hoặc lỗi tạo test fixture cũng có thể làm test thất bại. Vì vậy, cần đọc loại exception và vị trí xảy ra lỗi thay vì chỉ dựa vào dòng tổng kết `Tests failed`.

## 2. Lỗi thiếu bean là gì?

Trong Spring, dependency injection cần tìm một bean phù hợp với kiểu và qualifier được yêu cầu. Nếu không có bean đáp ứng điều kiện, Spring không thể hoàn thành việc tạo đối tượng hoặc cấu hình bean phụ thuộc.

Ví dụ service cần một repository:

```java
@Service
public class AccountService {

    private final AccountRepository repository;

    public AccountService(AccountRepository repository) {
        this.repository = repository;
    }
}
```

Nếu ApplicationContext không có bean `AccountRepository`, Spring không thể tạo `AccountService`. Test có thể nhận một lỗi bao ngoài như `UnsatisfiedDependencyException` hoặc `BeanCreationException`, còn nguyên nhân sâu hơn là `NoSuchBeanDefinitionException`.

### 2.1. Những exception thường gặp

| Exception / thông báo | Ý nghĩa thường gặp | Hướng kiểm tra |
|---|---|---|
| `NoSuchBeanDefinitionException` | Không tìm thấy bean phù hợp với kiểu hoặc tên được yêu cầu | Component scan, configuration, profile, import và test slice |
| `UnsatisfiedDependencyException` | Spring không thể cung cấp một dependency khi tạo bean | Đọc `Caused by` để tìm bean hoặc tham số constructor bị thiếu |
| `BeanCreationException` | Bean không thể được tạo | Kiểm tra nguyên nhân sâu hơn; có thể do dependency thiếu, cấu hình sai hoặc lỗi khởi tạo |
| `NoUniqueBeanDefinitionException` | Có nhiều bean cùng phù hợp trong khi Spring cần một bean duy nhất | Dùng `@Qualifier`, `@Primary` hoặc inject collection/provider |
| `BeanDefinitionOverrideException` | Có bean definition trùng tên và việc ghi đè không được cho phép | Kiểm tra cấu hình đăng ký bean và tên bean |
| `ApplicationContextException` | Một vấn đề trong quá trình khởi tạo hoặc vận hành context | Đọc nguyên nhân lồng bên trong, không kết luận ngay là thiếu bean |

Thông báo thường thấy khi thiếu bean là:

```text
No qualifying bean of type 'com.example.AccountRepository' available
```

Hoặc trong log có thể xuất hiện chuỗi nguyên nhân:

```text
Failed to load ApplicationContext
  Caused by: UnsatisfiedDependencyException
    Caused by: NoSuchBeanDefinitionException
      No qualifying bean of type 'com.example.AccountRepository' available
```

Lỗi bao ngoài cho biết Spring không thể tạo context hoặc bean. Exception sâu nhất thường cho biết dependency cụ thể nào không được tìm thấy. Khi chẩn đoán, hãy đọc toàn bộ chuỗi `Caused by`, bắt đầu từ nguyên nhân sâu nhất có ý nghĩa.

### 2.2. Không tìm thấy bean và có nhiều bean là hai tình huống khác nhau

Giả sử có hai implementation:

```java
@Component
class SmtpNotificationSender implements NotificationSender {
}

@Component
class InMemoryNotificationSender implements NotificationSender {
}
```

Nếu một service inject `NotificationSender` mà không có quy tắc chọn, Spring có thể phát sinh `NoUniqueBeanDefinitionException`. Đây không phải lỗi thiếu bean; có nhiều ứng viên hơn mức cần thiết.

Có thể giải quyết bằng `@Qualifier`:

```java
@Service
class NotificationService {

    private final NotificationSender sender;

    NotificationService(
            @Qualifier("inMemoryNotificationSender") NotificationSender sender) {
        this.sender = sender;
    }
}
```

Hoặc đánh dấu một bean mặc định bằng `@Primary` nếu đó là lựa chọn phù hợp với ứng dụng. Khi test cần một implementation cụ thể, hãy khai báo rõ bean mong muốn trong test configuration hoặc sử dụng qualifier tương ứng.

## 3. Lỗi thiếu bean xuất hiện ở đâu trong test?

### 3.1. Thiếu bean khi tạo ApplicationContext

Với `@SpringJUnitConfig`, `@ContextConfiguration` hoặc `@SpringBootTest`, Spring cần tạo ApplicationContext trước khi test method chạy. Nếu một bean bắt buộc không thể được tạo, test thường dừng ở bước chuẩn bị context.

Ví dụ:

```java
@SpringJUnitConfig(AccountService.class)
class AccountServiceTest {

    @Autowired
    private AccountService accountService;

    @Test
    void loadsService() {
        assertNotNull(accountService);
    }
}
```

Đoạn này chỉ đăng ký `AccountService` làm cấu hình nguồn component. Nếu `AccountService` cần `AccountRepository` nhưng không có cấu hình hoặc component scan nào cung cấp repository, context có thể không khởi tạo được. Câu lệnh `assertNotNull` chưa được thực thi.

### 3.2. Thiếu bean trong test slice

Các test slice cố ý chỉ nạp một phần ứng dụng. Ví dụ `@WebMvcTest(OrderController.class)` tập trung vào tầng MVC, nên service nghiệp vụ không nhất thiết được quét và đăng ký như khi chạy toàn bộ ứng dụng.

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private OrderService orderService;
}
```

Nếu `OrderService` không thuộc slice được nạp, việc inject field có thể làm context thất bại. Với controller test, thông thường nên cung cấp mock bean cho dependency nghiệp vụ:

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;
}
```

`@MockitoBean` là annotation của Spring Framework từ phiên bản 6.2, dùng để tạo hoặc thay thế bean trong test context bằng Mockito mock. Với Spring Boot cũ hơn, dự án có thể đang sử dụng `@MockBean` của Spring Boot Test; `@MockBean` đã được đánh dấu deprecated từ Spring Boot 3.4 để chuyển sang các annotation bean override của Spring Framework. Hãy dùng annotation có sẵn và tương thích với phiên bản dự án.

Nếu test cần kiểm tra chính service thật, hãy chọn phạm vi context phù hợp, ví dụ `@SpringBootTest` hoặc cấu hình test import service cùng các dependency cần thiết. Không nên đưa service thật vào một MVC slice chỉ để làm cho field inject được nếu mục tiêu của test chỉ là hành vi controller.

### 3.3. Thiếu bean do cấu hình không được nạp

Một bean có thể tồn tại trong mã nguồn nhưng không xuất hiện trong context của test. Các nguyên nhân thường gặp:

- Lớp chưa được component scan bao phủ.
- Configuration class chứa `@Bean` chưa được import hoặc khai báo trong `@ContextConfiguration`.
- Bean chỉ được tạo khi một profile hoạt động, nhưng test chưa bật profile đó.
- Điều kiện `@Conditional`, `@ConditionalOnProperty` hoặc điều kiện môi trường không thỏa.
- Test slice loại cấu hình hoặc component khỏi phạm vi quét.
- Bean bị giới hạn theo module, package hoặc classpath nhưng dependency cần thiết chưa có.
- Test dùng nhầm configuration class hoặc nhầm application context hierarchy.

Ví dụ một bean chỉ hoạt động khi profile `test` được bật:

```java
@Configuration
@Profile("test")
class TestGatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
```

Test cần kích hoạt profile và nạp cấu hình tương ứng:

```java
@SpringJUnitConfig(TestGatewayConfiguration.class)
@ActiveProfiles("test")
class PaymentServiceTest {

    @Autowired
    private PaymentGateway paymentGateway;
}
```

Nếu `@ActiveProfiles` bị thiếu hoặc profile bị ghi đè theo cấu hình test, bean có thể không được đăng ký. Khi chẩn đoán, hãy kiểm tra active profiles thực tế của Environment và điều kiện tạo bean.

## 4. Lỗi assertion là gì?

Assertion kiểm tra kết quả thực tế có khớp với hợp đồng mà test mô tả hay không. Với JUnit Jupiter, các phương thức như `assertEquals`, `assertTrue`, `assertNotNull`, `assertThrows` và `assertAll` sẽ báo lỗi khi điều kiện mong đợi không được đáp ứng.

Ví dụ:

```java
@Test
void calculatesDiscount() {
    PriceCalculator calculator = new PriceCalculator();

    int actual = calculator.discount(100, 10);

    assertEquals(90, actual);
}
```

Nếu phương thức trả về `95`, test thất bại với `AssertionFailedError` hoặc kiểu lỗi assertion tương ứng của JUnit. Điều này cho biết test method đã chạy, lời gọi được thực hiện và kết quả không khớp mong đợi.

Một báo cáo có thể hiển thị:

```text
org.opentest4j.AssertionFailedError:
Expected :90
Actual   :95
    at PriceCalculatorTest.calculatesDiscount(PriceCalculatorTest.java:12)
```

Ở đây, cần kiểm tra công thức giảm giá, dữ liệu đầu vào và expected value. Việc thêm bean vào ApplicationContext không giải quyết được sai lệch kết quả của phép tính thuần Java.

## 5. Phân biệt lỗi thiếu bean và lỗi assertion qua dấu hiệu

| Dấu hiệu | Lỗi thiếu bean / context | Lỗi assertion |
|---|---|---|
| Thời điểm | Thường trước test method | Trong test method hoặc assertion ở lifecycle callback |
| Exception thường thấy | `NoSuchBeanDefinitionException`, `UnsatisfiedDependencyException`, `BeanCreationException` | `AssertionFailedError`, `AssertionError` hoặc lỗi assertion của thư viện |
| Thông báo | `No qualifying bean`, `Failed to load ApplicationContext` | `expected ... but was ...`, `expected true but was false` |
| Stack trace | Đi qua Spring bean factory, dependency resolution, context loader | Trỏ đến dòng assertion trong test hoặc assertion helper |
| Test method đã chạy? | Thường chưa | Có; ít nhất đã đến câu assertion gây lỗi |
| Cần kiểm tra | Bean definition, profile, scan, qualifier, test slice, context config | Expected/actual, logic, fixture, mock stubbing và hợp đồng chức năng |

Hãy lưu ý rằng một assertion trong `@BeforeEach` hoặc một test helper cũng có thể thất bại trước khi test method chính được gọi. Vì thế, stack trace và exception type vẫn quan trọng hơn việc chỉ nhìn thời điểm tổng thể.

## 6. Không nhầm @Mock của Mockito với bean của Spring

Đây là nguyên nhân phổ biến khiến test có vẻ đã tạo mock nhưng Spring vẫn báo thiếu bean.

`@Mock` tạo một Mockito mock object. Nó không tự động đăng ký object đó vào ApplicationContext. `@InjectMocks` yêu cầu Mockito tạo đối tượng được kiểm thử và inject các mock theo quy tắc của Mockito; đối tượng này cũng không mặc nhiên trở thành Spring bean.

Ví dụ unit test thuần:

```java
@ExtendWith(MockitoExtension.class)
class AccountServiceUnitTest {

    @Mock
    private AccountRepository repository;

    @InjectMocks
    private AccountService service;

    @Test
    void returnsAccountWhenRepositoryFindsIt() {
        when(repository.findById(42L))
                .thenReturn(Optional.of(new Account(42L)));

        assertEquals(42L, service.findById(42L).id());
    }
}
```

Test này không cần Spring ApplicationContext. Mockito tự tạo mock repository và inject vào service.

Ngược lại, nếu test có `@Autowired AccountService` và dùng SpringExtension, Spring sẽ tìm bean `AccountService` trong context. Một field `@Mock AccountRepository` không đáp ứng yêu cầu tạo bean `AccountRepository` cho context đó.

Khi cần mock dependency bên trong Spring context, hãy dùng `@MockitoBean` (Spring Framework 6.2 trở lên) hoặc annotation tương thích của Spring Boot ở phiên bản cũ:

```java
@SpringJUnitConfig(AccountTestConfiguration.class)
class AccountServiceSpringTest {

    @Autowired
    private AccountService service;

    @MockitoBean
    private AccountRepository repository;

    @Test
    void delegatesLookupToRepository() {
        when(repository.findById(42L))
                .thenReturn(Optional.of(new Account(42L)));

        assertEquals(42L, service.findById(42L).id());
    }
}
```

Ví dụ giả định `AccountTestConfiguration` đăng ký `AccountService` và các bean cần thiết khác. `@MockitoBean` cung cấp mock trong context để Spring có thể inject vào service. Nếu cấu hình vẫn không có `AccountService`, mock repository không thể tự tạo ra service bean.

## 7. Lỗi thiếu bean và lỗi inject test instance

Không phải mọi vấn đề liên quan `@Autowired` đều là `NoSuchBeanDefinitionException`.

### 7.1. SpringExtension chưa được đăng ký

Trong test JUnit Jupiter thuần, annotation `@Autowired` không tự được JUnit xử lý. Muốn Spring thực hiện dependency injection cho test instance, cần đăng ký `SpringExtension`, thường qua `@ExtendWith(SpringExtension.class)` hoặc annotation kết hợp như `@SpringJUnitConfig`.

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class SpringManagedTest {

    @Autowired
    private AccountService service;
}
```

Nếu thiếu extension, test method vẫn có thể được JUnit chạy như một test bình thường, nhưng field `service` không được Spring inject. Khi code truy cập field, kết quả có thể là `NullPointerException` hoặc assertion `assertNotNull` thất bại. Đây là lỗi tích hợp test framework, không nhất thiết là Spring đã tìm kiếm bean rồi không tìm thấy.

### 7.2. SpringExtension có nhưng dependency không tồn tại

Nếu extension đã hoạt động và Spring chuẩn bị test instance nhưng không có bean phù hợp, quá trình injection có thể thất bại với lỗi dependency resolution. Khi đó, cần kiểm tra context configuration và bean definition.

### 7.3. Test constructor hoặc method parameter không được resolver hỗ trợ

JUnit Jupiter dùng `ParameterResolver` để cung cấp tham số cho test constructor và method. Nếu một tham số không được resolver nào hỗ trợ, JUnit có thể báo `ParameterResolutionException`.

Ví dụ:

```java
@Test
void testWithUnresolvedParameter(AccountService service) {
    // Nếu không có ParameterResolver hỗ trợ tham số này,
    // JUnit không thể gọi method.
}
```

Không nên giả định rằng khai báo một tham số kiểu bean là đủ để Spring tự inject. Hãy đăng ký SpringExtension và dùng cơ chế injection mà Spring Test hỗ trợ, chẳng hạn annotation phù hợp trên tham số hoặc test constructor theo cấu hình hiện hành. Nếu lỗi là `ParameterResolutionException`, hãy kiểm tra resolver và annotation trên tham số trước khi kết luận bean bị thiếu.

## 8. Các trường hợp dependency là tùy chọn

Một dependency không tồn tại không phải lúc nào cũng là lỗi. Nếu ứng dụng định nghĩa nó là tùy chọn, Spring có thể inject theo cách cho phép absence.

Ví dụ:

```java
@Component
class OptionalAuditService {

    private final ObjectProvider<AuditClient> auditClientProvider;

    OptionalAuditService(ObjectProvider<AuditClient> auditClientProvider) {
        this.auditClientProvider = auditClientProvider;
    }

    void audit(String event) {
        AuditClient client = auditClientProvider.getIfAvailable();
        if (client != null) {
            client.send(event);
        }
    }
}
```

`ObjectProvider#getIfAvailable()` cho phép bean tiếp tục hoạt động khi không có `AuditClient`. Tương tự, `Optional<T>` hoặc injection có `@Autowired(required = false)` có thể biểu đạt dependency không bắt buộc theo đúng API và vị trí sử dụng.

Nếu dependency được khai báo bắt buộc qua constructor, Spring phải tìm được bean phù hợp. Đừng làm dependency bắt buộc trở thành tùy chọn chỉ để test khởi tạo được; hãy xác định rõ hợp đồng của ứng dụng và cấu hình test tương ứng.

## 9. Đọc stack trace theo đúng thứ tự

Khi test thất bại, hãy bắt đầu từ phần summary để biết test nào và exception nào thất bại. Sau đó tìm dòng assertion hoặc chuỗi nguyên nhân của Spring.

Ví dụ lỗi context:

```text
AccountServiceTest > loadsService FAILED
    java.lang.IllegalStateException: Failed to load ApplicationContext
        Caused by: UnsatisfiedDependencyException:
            Error creating bean with name 'accountService'
        Caused by: NoSuchBeanDefinitionException:
            No qualifying bean of type 'AccountRepository' available
```

Cách đọc:

1. `Failed to load ApplicationContext` cho biết test không có context sẵn sàng.
2. `UnsatisfiedDependencyException` cho biết Spring đang tạo `accountService` nhưng không thỏa dependency.
3. `NoSuchBeanDefinitionException` chỉ ra kiểu bean không được tìm thấy.
4. Kiểm tra configuration class, scan path, profile, test slice và cách mock repository.

Ví dụ lỗi assertion:

```text
AccountServiceTest > returnsAccountWhenRepositoryFindsIt FAILED
    org.opentest4j.AssertionFailedError:
    Expected: 42
    Actual:   0
        at AccountServiceTest.returnsAccountWhenRepositoryFindsIt(AccountServiceTest.java:28)
```

Cách đọc:

1. Context đã được tạo đủ để test method chạy.
2. Stack trace trỏ tới câu assertion trong test method.
3. Xem fixture và mock stubbing có trả dữ liệu đúng không.
4. Nếu dữ liệu đầu vào đúng, kiểm tra logic service và expected value.

Đừng chỉ tìm từ khóa `FAILED`. Cùng một dòng summary có thể đại diện cho lỗi context, lỗi setup, lỗi assertion hoặc exception bất ngờ trong code.

## 10. Kiểm tra context độc lập khi nghi thiếu bean

Khi nghi ngờ cấu hình Spring, có thể viết một test nhỏ chỉ xác nhận context khởi tạo và bean cần thiết tồn tại.

```java
@SpringJUnitConfig(AccountTestConfiguration.class)
class AccountContextTest {

    @Autowired
    private ApplicationContext context;

    @Test
    void registersAccountService() {
        assertTrue(context.containsBean("accountService"));
        assertNotNull(context.getBean(AccountService.class));
    }
}
```

Test này giúp phân biệt cấu hình context với logic nghiệp vụ. Nếu context không thể khởi tạo, lỗi xảy ra trước assertion. Nếu context khởi tạo thành công nhưng bean không có, assertion hoặc `getBean` sẽ chỉ ra cấu hình thiếu theo cách trực tiếp hơn.

Có thể truy vấn bean theo kiểu:

```java
Map<String, AccountService> beans =
        context.getBeansOfType(AccountService.class);

assertEquals(1, beans.size());
```

Nếu ứng dụng có nhiều implementation hợp lệ, đừng assertion số lượng bằng 1 khi hợp đồng không yêu cầu như vậy. Hãy kiểm tra qualifier hoặc bean cụ thể cần dùng.

## 11. Kiểm tra cấu hình test slice và cấu hình đầy đủ

Chọn phạm vi context đúng giúp tránh nhiều lỗi thiếu bean.

| Annotation / cách dựng | Phạm vi chính | Điều cần chú ý |
|---|---|---|
| Unit test với Mockito | Không có Spring context | Dùng `@Mock`, `@InjectMocks` và MockitoExtension |
| `@SpringJUnitConfig` | Spring TestContext với cấu hình được chỉ định | Phải cung cấp configuration và bean cần thiết |
| `@ContextConfiguration` | Nạp các nguồn cấu hình Spring cho test | Kiểm tra classes, locations và context hierarchy |
| `@WebMvcTest` | MVC slice trong Spring Boot | Mock hoặc import service/dependency không thuộc slice |
| `@WebFluxTest` | WebFlux slice trong Spring Boot | Cung cấp mock bean cho service và dependency ngoài slice |
| `@DataJpaTest` | Persistence slice của Spring Boot | Không mặc định nạp toàn bộ service/web layer |
| `@SpringBootTest` | Context ứng dụng Spring Boot rộng hơn | Có thể cần cấu hình hạ tầng, property và dependency ngoài |

Các annotation có hậu tố `Test` trong bảng như `@WebMvcTest`, `@WebFluxTest`, `@DataJpaTest` và `@SpringBootTest` là tính năng Spring Boot Test. Spring Framework thuần cung cấp TestContext Framework và các cách dựng context tương ứng.

Nếu một test cần controller thật và service thật nhưng mock repository, hãy cấu hình phạm vi context đủ để tạo controller/service rồi thay repository bằng test bean hoặc mock bean. Nếu test chỉ kiểm tra HTTP mapping và response của controller, dùng MVC/WebFlux slice cùng mock service sẽ nhanh và rõ ràng hơn.

## 12. Phân biệt lỗi thiếu bean với lỗi trong mock setup

Mock có thể tồn tại nhưng được cấu hình sai. Trường hợp này context vẫn khởi tạo, test method chạy, nhưng kết quả assertion thất bại hoặc phát sinh exception trong lúc gọi mock.

Ví dụ:

```java
@Test
void returnsAccount() {
    when(repository.findById(42L))
            .thenReturn(Optional.of(new Account(42L)));

    Account result = service.findById(7L);

    assertNotNull(result);
}
```

Mock được cấu hình cho `42L` nhưng test gọi `7L`. Mockito trả về giá trị mặc định nếu không có stub khớp; service có thể trả `null` hoặc đi vào nhánh khác. Đây là lỗi test setup hoặc logic, không phải lỗi thiếu bean.

Khi assertion thất bại với test dùng mock, kiểm tra:

- Stub có dùng đúng tham số thực tế không?
- Mock có được inject vào đúng đối tượng đang kiểm thử không?
- Có gọi nhầm một instance service khác với instance đã được `@InjectMocks` tạo không?
- Mock có bị reset giữa các method bởi extension hoặc cấu hình test không?
- Có exception được ném từ stub hoặc answer không?
- Test có kiểm tra đúng kết quả của hợp đồng không?

## 13. Xử lý lỗi theo nguyên nhân

Khi gặp thông báo thiếu bean, hãy xử lý theo loại vấn đề:

| Nguyên nhân | Cách xử lý phù hợp |
|---|---|
| Bean chưa được component scan | Điều chỉnh package scan hoặc khai báo cấu hình bean đúng phạm vi |
| `@Bean` configuration chưa được nạp | Thêm configuration vào `@ContextConfiguration`, `@Import` hoặc cấu hình Boot phù hợp |
| Profile không hoạt động | Khai báo `@ActiveProfiles` hoặc thiết lập profile đúng cho test |
| Dependency ngoài không cần chạy thật | Đăng ký test bean hoặc `@MockitoBean`/cơ chế mock bean tương thích |
| Test slice loại dependency | Dùng mock bean, `@Import` hoặc chọn phạm vi test đúng mục tiêu |
| Có nhiều bean cùng kiểu | Chọn `@Qualifier`, `@Primary` hoặc inject nhiều bean theo hợp đồng |
| JUnit không thực hiện Spring injection | Đăng ký `SpringExtension` hoặc dùng annotation tích hợp như `@SpringJUnitConfig` |
| Test parameter không có resolver | Cấu hình `ParameterResolver` hoặc cách inject tham số được Spring hỗ trợ |
| Assertion expected/actual sai khác | Kiểm tra fixture, stub, đầu vào, logic và hợp đồng mong đợi |

Không nên thêm bean giả một cách máy móc cho mọi lỗi. Nếu bean là thành phần cần kiểm tra, phải cung cấp implementation thật trong context. Nếu bean là dependency ngoài phạm vi test, mock là lựa chọn hợp lý. Nếu dependency vốn tùy chọn, hãy kiểm tra cách ứng dụng biểu đạt tính tùy chọn.

## 14. Một quy trình chẩn đoán ngắn gọn

Khi test Spring thất bại, có thể đi theo trình tự:

1. Xác định test có được discovery và bắt đầu thực thi hay không.
2. Nếu thấy `Failed to load ApplicationContext`, đọc các exception `Caused by` để tìm bean hoặc cấu hình gốc.
3. Nếu thấy `NoSuchBeanDefinitionException`, kiểm tra kiểu bean, component scan, `@Bean`, profile, condition và test slice.
4. Nếu thấy `NoUniqueBeanDefinitionException`, kiểm tra các implementation và qualifier.
5. Nếu field `@Autowired` là `null` nhưng không có lỗi Spring context, kiểm tra `SpringExtension` và cách tạo test instance.
6. Nếu thấy `ParameterResolutionException`, kiểm tra resolver và annotation trên tham số.
7. Nếu thấy `AssertionFailedError` hoặc `AssertionError`, xem expected/actual và dòng assertion.
8. Nếu mock đã được inject nhưng kết quả sai, kiểm tra stubbing, tham số gọi và instance được test.
9. Nếu context lỗi lặp lại sau lần đầu, đọc thông báo context failure threshold để tìm lỗi gốc ở lần load đầu tiên.

Spring TestContext có cơ chế cache context. Từ Spring Framework 6.1, cơ chế failure threshold mặc định có thể ngăn việc thử tải lại cùng một context nhiều lần sau khi lần đầu thất bại. Khi thấy thông báo kiểu “ApplicationContext failure threshold exceeded”, đó thường là hậu quả của một lần khởi tạo context thất bại trước đó. Hãy tìm log đầu tiên của cùng context để xác định nguyên nhân thực, thay vì xử lý thông báo threshold như một lỗi bean độc lập.

## 15. Nguyên tắc thiết kế test để dễ chẩn đoán

- Đặt tên test thể hiện điều kiện và kết quả, ví dụ `loadsContext_whenRepositoryBeanIsConfigured` hoặc `returnsNotFound_whenAccountDoesNotExist`.
- Giữ một test tập trung vào một hành vi chính; tránh gộp quá nhiều cấu hình và assertion không liên quan.
- Dùng unit test thuần khi không cần Spring container.
- Dùng Spring context test khi cần xác minh bean wiring, profile, property hoặc lifecycle.
- Với test slice, khai báo rõ dependency được mock và dependency thật thuộc phạm vi slice.
- Kiểm tra cả loại exception và nguyên nhân sâu khi kiểm thử trường hợp context phải thất bại.
- Dùng assertion có thông tin expected/actual và message mô tả điều kiện khi điều đó giúp chẩn đoán.
- Không biến lỗi cấu hình thành test bị bỏ qua hoặc assertion lỏng lẻo chỉ để suite chuyển sang màu xanh.

Khi đọc đúng giai đoạn thất bại, exception và stack trace, ta có thể phân biệt một bean chưa được Spring tạo hoặc inject với một hành vi đã chạy nhưng cho kết quả sai. Lỗi thiếu bean cần xử lý ở cấu hình context và dependency injection; lỗi assertion cần kiểm tra dữ liệu, mock setup và logic được kiểm thử. Phân biệt rõ hai loại này giúp sửa đúng nguyên nhân và giữ cho bộ kiểm thử Spring phản ánh chính xác trạng thái của ứng dụng.

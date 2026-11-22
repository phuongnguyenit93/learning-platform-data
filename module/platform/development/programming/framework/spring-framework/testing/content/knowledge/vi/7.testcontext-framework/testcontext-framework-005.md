# SpringExtension với JUnit Jupiter

SpringExtension là cầu nối giữa **JUnit Jupiter** và **Spring TestContext Framework**. Khi một test cần Spring quản lý ApplicationContext, inject dependency vào test instance, áp dụng transaction test hoặc thực hiện các callback của TestContext, SpringExtension giúp những khả năng đó tham gia vào vòng đời test của JUnit Jupiter.

JUnit Jupiter cung cấp mô hình extension thay cho mô hình runner của JUnit 4. Vì vậy, cách tích hợp Spring cũng thay đổi:

- Với JUnit 4, thường dùng @RunWith(SpringRunner.class).
- Với JUnit Jupiter (JUnit 5), dùng @ExtendWith(SpringExtension.class), hoặc một annotation tổng hợp đã đăng ký extension này như @SpringJUnitConfig hay các annotation test của Spring Boot.

SpringExtension không phải là Spring container và cũng không tự biến mọi test thành một bài kiểm thử tích hợp. Nó kết nối các extension point của JUnit với TestContextManager. Test vẫn cần khai báo cách tạo ApplicationContext và chọn đúng phạm vi kiểm thử.

## 1. JUnit Jupiter và mô hình extension

JUnit Jupiter là programming model của JUnit 5. Một test class sử dụng các annotation như:

- @Test để khai báo test method.
- @BeforeEach và @AfterEach để thiết lập, dọn dẹp quanh từng test.
- @BeforeAll và @AfterAll để chạy tác vụ trước/sau toàn bộ test class.
- @Nested để nhóm các test liên quan.
- @ParameterizedTest để chạy cùng một test với nhiều bộ dữ liệu.
- @Tag để phân nhóm test.

JUnit Jupiter mở rộng vòng đời test bằng cơ chế **Extension**. Extension có thể tham gia vào các thời điểm như tạo test instance, trước/sau mỗi test, trước/sau test class, xử lý exception hoặc giải quyết tham số của method.

SpringExtension triển khai các extension point phù hợp để Spring TestContext Framework có thể phối hợp với JUnit Jupiter. Nhờ vậy, test có thể dùng các khả năng của Spring Test mà không cần một JUnit 4 Runner.

Ví dụ tối giản:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class MySpringTest {

    @Autowired
    private MyService myService;

    @Test
    void performsExpectedBehavior() {
        assertNotNull(myService);
    }
}
~~~

Hai annotation có trách nhiệm khác nhau:

- @ExtendWith(SpringExtension.class) đăng ký SpringExtension với JUnit Jupiter.
- @ContextConfiguration khai báo cấu hình dùng để tạo ApplicationContext cho test.

Chỉ đăng ký extension mà không có cấu hình context phù hợp thì chưa xác định được các bean mà test cần. Spring Test có cơ chế tìm cấu hình mặc định trong một số trường hợp, nhưng test rõ ràng nên khai báo cấu hình hoặc dùng annotation tổng hợp tương ứng.

## 2. SpringExtension kết nối với TestContext Framework như thế nào?

SpringExtension không tự viết lại vòng đời JUnit. Nó nhận các callback từ JUnit Jupiter và chuyển tiếp chúng tới **TestContextManager**.

TestContextManager quản lý TestContext cho test class. TestContext giữ thông tin về test, ApplicationContext và các listener tham gia vào quá trình thực thi. Các TestExecutionListener cung cấp những hành vi như inject dependency vào test instance, quản lý transaction test, xử lý @DirtiesContext và thực thi SQL script theo cấu hình.

Có thể hình dung mối liên hệ như sau:

~~~mermaid
flowchart TD
    J["JUnit Jupiter Engine"] --> E["SpringExtension"]
    E --> M["TestContextManager"]
    M --> T["TestContext"]
    T --> C["ApplicationContext"]
    M --> L["TestExecutionListeners"]
    L --> DI["Dependency injection"]
    L --> TX["Test-managed transactions"]
    L --> SQL["SQL scripts / lifecycle support"]
    C --> B["Spring beans"]
~~~

Các callback chính được chuyển tiếp theo vòng đời:

| JUnit Jupiter extension point | Hoạt động Spring TestContext |
|---|---|
| BeforeAllCallback | beforeTestClass |
| TestInstancePostProcessor | prepareTestInstance |
| BeforeEachCallback | beforeTestMethod |
| BeforeTestExecutionCallback | beforeTestExecution |
| AfterTestExecutionCallback | afterTestExecution |
| AfterEachCallback | afterTestMethod |
| AfterAllCallback | afterTestClass |
| ParameterResolver | Giải quyết tham số từ ApplicationContext khi tham số thuộc phạm vi Spring hỗ trợ |

Sự phân chia này giúp hiểu vì sao một số hành vi xảy ra trước @BeforeEach, trong khi hành vi khác xảy ra sát thời điểm gọi test method.

### Trình tự quanh một test method

Với test class dùng SpringExtension, trình tự khái quát là:

1. JUnit tạo test instance theo lifecycle đã cấu hình.
2. SpringExtension nhận instance qua TestInstancePostProcessor và yêu cầu TestContext chuẩn bị instance, bao gồm dependency injection.
3. Các callback trước test method được thực hiện.
4. JUnit chạy @BeforeEach.
5. SpringExtension nhận callback beforeTestExecution.
6. JUnit thực thi test method.
7. SpringExtension nhận callback afterTestExecution.
8. JUnit chạy @AfterEach.
9. SpringExtension nhận callback afterEach để hoàn tất xử lý test method trong TestContext.

Ở cấp test class, các callback beforeAll/afterAll tương ứng với beforeTestClass/afterTestClass của TestContext.

Thứ tự này giải thích một điểm quan trọng: dependency injection vào field của test instance được thực hiện trước khi @BeforeEach chạy, nên test có thể sử dụng bean đã inject trong setup method.

Đây là mô tả khái quát của lifecycle. Khi nhiều extension cùng tham gia, thứ tự callback còn phụ thuộc cách JUnit đăng ký extension và quy tắc của từng extension.

## 3. Đăng ký SpringExtension trực tiếp

Cách tường minh nhất là kết hợp @ExtendWith và @ContextConfiguration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = GreetingTestConfig.class)
class GreetingServiceTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void createsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
~~~

Cấu hình test có thể là một Java configuration nhỏ:

~~~java
@Configuration
class GreetingTestConfig {

    @Bean
    GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

Và thành phần cần kiểm tra:

~~~java
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + name;
    }
}
~~~

Khi test chạy:

- JUnit Jupiter phát hiện test class và đăng ký SpringExtension.
- Spring TestContext sử dụng GreetingTestConfig để tạo ApplicationContext.
- SpringExtension yêu cầu TestContext chuẩn bị test instance.
- Bean GreetingService được inject vào field.
- Test method gọi bean và kiểm tra kết quả.

Ví dụ này minh họa cách tích hợp extension và dependency injection. Nếu chỉ kiểm tra phép ghép chuỗi trong GreetingService, có thể tạo object trực tiếp mà không cần Spring. Dùng context ở đây để minh họa cơ chế wiring; trong ứng dụng thực tế, hãy chọn context khi cấu hình hoặc hành vi Spring là một phần của điều cần xác nhận.

## 4. Dùng @SpringJUnitConfig để viết ngắn gọn

Spring cung cấp annotation tổng hợp **@SpringJUnitConfig** cho JUnit Jupiter. Annotation này kết hợp:

- @ExtendWith(SpringExtension.class)
- @ContextConfiguration

Vì vậy, thay vì viết hai annotation riêng, có thể khai báo:

~~~java
@SpringJUnitConfig(GreetingTestConfig.class)
class GreetingServiceTest {

    @Autowired
    private GreetingService greetingService;

    @Test
    void createsGreeting() {
        assertEquals("Hello, Lan", greetingService.greet("Lan"));
    }
}
~~~

@SpringJUnitConfig có thể nhận classes hoặc locations tương tự cấu hình context. Khi cần chỉ định thêm initializer hoặc loader, có thể dùng các thuộc tính tương ứng của @ContextConfiguration thông qua annotation tổng hợp.

Bảng so sánh:

| Cách khai báo | Vai trò |
|---|---|
| @ExtendWith(SpringExtension.class) + @ContextConfiguration | Đăng ký extension và khai báo context riêng rẽ |
| @SpringJUnitConfig | Cách viết tổng hợp cho hai annotation trên |
| @SpringJUnitWebConfig | Cách viết tổng hợp dành cho context có cấu hình web |
| @SpringBootTest | Khởi tạo Spring Boot test context; annotation này đã tích hợp SpringExtension |

Nếu test cần kiểm tra Spring Framework context thông thường, @SpringJUnitConfig là lựa chọn dễ đọc. Nếu test cần bootstrapping theo Spring Boot, hãy dùng annotation Boot phù hợp.

## 5. Dependency injection vào test class

SpringExtension phối hợp với TestContext để chuẩn bị test instance. Nhờ đó, test có thể nhận bean qua field, setter hoặc các cách injection mà Spring Test hỗ trợ.

### Field injection

~~~java
@SpringJUnitConfig(TestConfig.class)
class AccountServiceTest {

    @Autowired
    private AccountService accountService;

    @Test
    void loadsAccount() {
        Account account = accountService.find("ACC-01");

        assertEquals("ACC-01", account.id());
    }
}
~~~

Field injection thường ngắn gọn và quen thuộc trong test. Tuy nhiên, field không được khởi tạo cho đến khi Spring chuẩn bị test instance. Không truy cập field đó trong một biểu thức khởi tạo field khác của test class.

### Setter hoặc method injection

Spring Test cũng hỗ trợ injection vào các method được đánh dấu @Autowired. Cách này hữu ích khi test cần chuẩn bị một số dependency theo method, nhưng nên giữ setup đơn giản để không làm test khó theo dõi.

~~~java
@SpringJUnitConfig(TestConfig.class)
class ReportServiceTest {

    private ReportService reportService;

    @Autowired
    void setReportService(ReportService reportService) {
        this.reportService = reportService;
    }

    @Test
    void generatesReport() {
        assertNotNull(reportService.generate());
    }
}
~~~

Trong đa số trường hợp, field injection hoặc constructor injection đủ rõ ràng. Không cần trộn nhiều kiểu injection trong cùng một test class nếu không có lý do cụ thể.

### Constructor injection cho test instance

JUnit Jupiter cho phép test class có constructor tùy chỉnh. Spring Test cung cấp @TestConstructor để xác định rằng tham số constructor được autowire từ ApplicationContext.

~~~java
@SpringJUnitConfig(TestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class AccountServiceConstructorTest {

    private final AccountService accountService;

    AccountServiceConstructorTest(AccountService accountService) {
        this.accountService = accountService;
    }

    @Test
    void loadsAccount() {
        assertNotNull(accountService);
    }
}
~~~

Có thể cấu hình chế độ autowire constructor mặc định trên toàn bộ test suite bằng thuộc tính:

~~~properties
spring.test.constructor.autowire.mode=all
~~~

Cấu hình toàn cục này thay đổi cách Spring xử lý constructor của test class. Chỉ bật khi đội phát triển muốn áp dụng nhất quán và đã hiểu tác động tới các test có constructor parameter dành cho JUnit extension khác.

Constructor injection làm dependency của test hiện rõ ngay tại khai báo class. Đổi lại, test class cần cấu hình autowire constructor phù hợp. Nếu không muốn thay đổi chế độ constructor, field injection hoặc setter injection có thể đơn giản hơn.

## 6. Inject bean vào tham số test method

SpringExtension còn triển khai ParameterResolver. Nhờ đó, JUnit Jupiter có thể yêu cầu extension cung cấp tham số mà Spring quản lý.

Ví dụ:

~~~java
@SpringJUnitConfig(TestConfig.class)
class AccountServiceParameterTest {

    @Test
    void loadsAccount(AccountService accountService) {
        Account account = accountService.find("ACC-01");

        assertEquals("ACC-01", account.id());
    }
}
~~~

SpringExtension phân giải tham số từ ApplicationContext khi tham số thuộc phạm vi nó hỗ trợ. Cách này giúp method chỉ khai báo dependency cần dùng mà không phải lưu chúng thành field.

Cũng có thể dùng tham số trong các lifecycle method của JUnit Jupiter khi extension hỗ trợ và tham số được phân giải phù hợp:

~~~java
@BeforeEach
void prepareTestData(AccountRepository repository) {
    repository.deleteAll();
}
~~~

Hãy lưu ý rằng việc xóa dữ liệu qua repository là side effect thật trong context đang chạy. Chỉ dùng setup như vậy khi test cần database và có chiến lược cô lập dữ liệu phù hợp.

### Khi nhiều ParameterResolver cùng tham gia

JUnit Jupiter có thể đăng ký nhiều extension cùng triển khai ParameterResolver. Ví dụ, MockitoExtension có thể cung cấp tham số @Mock, còn SpringExtension có thể cung cấp bean từ ApplicationContext.

Nếu nhiều resolver cùng nhận một tham số, JUnit có thể báo lỗi do không xác định được resolver phù hợp. Hãy dùng annotation và kiểu tham số rõ ràng, tránh khai báo cùng một dependency theo hai cơ chế giải quyết cạnh tranh.

Với mock cần thay thế bean trong Spring context, nên chọn cơ chế bean override tương thích với phiên bản Spring đang dùng. Với mock chỉ phục vụ một unit test thuần, có thể dùng MockitoExtension mà không cần SpringExtension.

## 7. Kết hợp SpringExtension với Spring Boot Test

Trong ứng dụng Spring Boot, các annotation test chuyên biệt thường đã đăng ký SpringExtension thông qua metadata của chúng. Ví dụ:

- @SpringBootTest
- @WebMvcTest
- @DataJpaTest
- @JsonTest
- Các test slice khác của Spring Boot

Do đó, không cần thêm @ExtendWith(SpringExtension.class) một lần nữa khi đã dùng annotation Boot tương ứng.

Ví dụ kiểm tra context ứng dụng:

~~~java
@SpringBootTest
class ApplicationContextTest {

    @Autowired
    private ApplicationService applicationService;

    @Test
    void loadsApplicationService() {
        assertNotNull(applicationService);
    }
}
~~~

Ví dụ kiểm tra MVC slice:

~~~java
@WebMvcTest(AccountController.class)
class AccountControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsAccountEndpointResponse() throws Exception {
        mockMvc.perform(get("/accounts/ACC-01"))
                .andExpect(status().isOk());
    }
}
~~~

Trong test MVC thực tế, controller thường cần service dependency. Test phải cung cấp mock hoặc bean thay thế phù hợp để context slice có thể khởi tạo. Ví dụ trên tập trung vào việc đăng ký SpringExtension qua test annotation và sử dụng MockMvc; nó chưa thể hiện cấu hình đầy đủ cho mọi controller.

Nếu dùng @SpringBootTest, context có thể rộng hơn và khởi tạo nhiều auto-configuration. Hãy chọn @WebMvcTest, @DataJpaTest hoặc slice khác khi chỉ cần kiểm tra một phần hệ thống. SpringExtension hỗ trợ lifecycle cho các loại context đó; annotation bootstrapper quyết định context nào được tạo.

## 8. Cấu hình profile và property cho test context

SpringExtension làm việc với TestContext đã được bootstrap. Test có thể khai báo profile hoặc property để cấu hình context trước khi bean được tạo.

Ví dụ dùng profile:

~~~java
@SpringJUnitConfig(TestConfig.class)
@ActiveProfiles("test")
class ProfileAwareServiceTest {

    @Autowired
    private StorageService storageService;

    @Test
    void usesTestStorageImplementation() {
        assertEquals("in-memory", storageService.type());
    }
}
~~~

Ví dụ cung cấp property inline:

~~~java
@SpringJUnitConfig(TestConfig.class)
@TestPropertySource(properties = {
        "feature.checkout.enabled=true",
        "service.region=test-region"
})
class CheckoutConfigurationTest {

    @Autowired
    private CheckoutFeature checkoutFeature;

    @Test
    void enablesCheckout() {
        assertTrue(checkoutFeature.isEnabled());
    }
}
~~~

Các annotation này ảnh hưởng đến việc tạo context. Đây là khác biệt với MockEnvironment được truyền trực tiếp vào object: trong context test, property tham gia vào quá trình cấu hình Spring và có thể ảnh hưởng tới @Value, @Profile, @Conditional và các bean khác.

Nếu cần property động được cấp sau khi khởi tạo tài nguyên test, Spring hỗ trợ @DynamicPropertySource với một static method đăng ký property thông qua DynamicPropertyRegistry. Cách này thường gặp khi dùng Testcontainers để lấy host/port được cấp lúc runtime. Khi cần kiểm tra hành vi đó, test phải sử dụng context test phù hợp.

## 9. TestContext listeners và các tiện ích kiểm thử của Spring

SpringExtension là điểm tích hợp với JUnit Jupiter; nhiều hành vi kiểm thử của Spring được thực hiện bởi TestExecutionListener trong TestContext Framework.

Một số ví dụ:

### Dependency injection

DependencyInjectionTestExecutionListener chuẩn bị test instance và inject các dependency được Spring quản lý. Nhờ đó, field @Autowired trong test được cung cấp trước khi test method chạy.

### Transaction test

TransactionalTestExecutionListener phối hợp với annotation @Transactional để tạo test-managed transaction khi cấu hình hỗ trợ. Với mặc định phổ biến, transaction được rollback sau test để dữ liệu không tồn tại lâu dài.

~~~java
@SpringJUnitConfig(PersistenceTestConfig.class)
@Transactional
class AccountRepositoryTest {

    @Autowired
    private AccountRepository repository;

    @Test
    void savesAccount() {
        repository.save(new Account("ACC-01"));

        assertTrue(repository.findById("ACC-01").isPresent());
    }
}
~~~

Rollback không có nghĩa mọi side effect đều được hoàn tác. Message đã gửi tới broker, HTTP request đã gửi hoặc email đã phát không tự được thu hồi chỉ vì database transaction rollback. Cần cô lập hoặc thay thế các dependency ngoài khi test.

### SQL script

Với cấu hình phù hợp, @Sql có thể chạy script trước hoặc sau test method để chuẩn bị dữ liệu hoặc dọn dữ liệu:

~~~java
@Test
@Sql("/sql/accounts-test-data.sql")
void findsAccountFromScript() {
    assertTrue(repository.findById("ACC-01").isPresent());
}
~~~

Script cần nằm trong test classpath và phù hợp với database đang sử dụng. Đây là tiện ích cho test có persistence, không phải yêu cầu của unit test thuần.

### Làm mới ApplicationContext

@DirtiesContext đánh dấu context đã bị thay đổi hoặc không còn an toàn để tái sử dụng. TestContext sẽ loại context đó khỏi cache và đóng context tương ứng theo lifecycle.

Không nên gắn @DirtiesContext cho mọi test. Việc làm mới context có thể tốn thời gian đáng kể. Chỉ sử dụng khi test thực sự làm thay đổi trạng thái context theo cách ảnh hưởng tới các test khác.

Các listener có thể được mở rộng hoặc tùy chỉnh. Tuy nhiên, trước khi thêm listener riêng, hãy xác định callback nào đang thiếu và liệu extension point hiện có của Spring Test đã đáp ứng yêu cầu chưa.

## 10. Vòng đời test instance và cache ApplicationContext

JUnit Jupiter mặc định tạo test instance mới cho mỗi test method (PER_METHOD). SpringExtension chuẩn bị từng instance đó, nhưng ApplicationContext có thể được dùng lại giữa nhiều test class có cùng cấu hình tương thích.

Điều này có nghĩa:

- Test instance thường độc lập giữa các method theo lifecycle mặc định.
- ApplicationContext không nhất thiết được tạo lại cho từng method.
- Bean singleton trong context có thể được dùng chung giữa nhiều test.
- Thay đổi trạng thái mutable trong bean singleton có thể ảnh hưởng test chạy sau.
- @DirtiesContext có thể làm context bị loại khỏi cache khi test đã làm thay đổi trạng thái context.

Vì vậy, không nên giả định mỗi test method có một bộ bean singleton mới. Nếu một bean giữ trạng thái, test cần reset trạng thái hoặc dùng fixture/cấu hình phù hợp. Dữ liệu database cũng cần được cô lập bằng transaction, cleanup hoặc namespace riêng.

Spring TestContext Framework có cache ApplicationContext để giảm thời gian khởi tạo. Cache dựa trên cấu hình context; các test dùng cùng cấu hình có thể chia sẻ context. Việc thay đổi profile, property, initializer hoặc cấu hình bean có thể làm test cần một cache entry khác.

Tối ưu cache không nên trở thành lý do để test phụ thuộc thứ tự. Test phải có thể chạy riêng và theo thứ tự khác mà vẫn cho kết quả đáng tin cậy.

## 11. Phối hợp với các JUnit extension khác

JUnit Jupiter cho phép đăng ký nhiều extension. SpringExtension có thể cùng tồn tại với extension khác như MockitoExtension, extension quản lý dữ liệu hoặc extension do dự án tự viết.

Ví dụ đăng ký hai extension:

~~~java
@ExtendWith({
        SpringExtension.class,
        MockitoExtension.class
})
@ContextConfiguration(classes = TestConfig.class)
class CombinedExtensionTest {

    @Mock
    private PaymentGateway paymentGateway;

    @Autowired
    private PaymentService paymentService;

    @Test
    void handlesGatewayResult() {
        when(paymentGateway.charge(any()))
                .thenReturn(PaymentResult.approved());

        PaymentResult result =
                paymentService.pay(new PaymentCommand("ORDER-01"));

        assertTrue(result.approved());
    }
}
~~~

Ví dụ chỉ minh họa cách đăng ký extension và sử dụng mock. Trong một Spring context thực tế, PaymentService thường đã được tạo với một bean PaymentGateway. Mock field do MockitoExtension tạo không tự động thay thế bean đó trong ApplicationContext. Muốn service trong context sử dụng mock, cần đăng ký bean mock/override bằng cơ chế phù hợp của phiên bản Spring hoặc cấu hình test.

Đây là lỗi thường gặp: có một field @Mock trong test class, nhưng bean được inject vào service vẫn là implementation thật. Hai đối tượng thuộc hai cơ chế quản lý khác nhau.

Khi kết hợp extension, cần phân biệt:

- Mock object được MockitoExtension tạo cho test instance.
- Bean được Spring ApplicationContext quản lý.
- Bean override được đăng ký trong context.
- Dependency được JUnit ParameterResolver cung cấp cho method parameter.

Không nên cho rằng một mock field sẽ tự động thay thế bean trong Spring. Nếu chỉ kiểm tra service thuần, tạo service trực tiếp với mock là đơn giản nhất. Nếu cần kiểm tra wiring trong context với một bean thay thế, hãy dùng bean override hoặc test configuration.

## 12. SpringExtension không phải SpringRunner

Tên hai lớp dễ gây nhầm:

| Thành phần | Framework | Cách đăng ký |
|---|---|---|
| SpringRunner | JUnit 4 | @RunWith(SpringRunner.class) |
| SpringExtension | JUnit Jupiter | @ExtendWith(SpringExtension.class) |

JUnit 4 Runner là cơ chế mở rộng vòng đời theo mô hình runner. JUnit Jupiter sử dụng extension model, cho phép nhiều extension cùng tham gia một test class.

Không dùng @RunWith(SpringRunner.class) cho test class được chạy bằng Jupiter Engine. Nếu dự án còn test JUnit 4, chúng cần JUnit Vintage Engine và cấu hình tương ứng; test Jupiter nên dùng SpringExtension.

Trong một dự án đang chuyển từ JUnit 4 sang JUnit Jupiter, hãy kiểm tra import annotation. @Test của org.junit.jupiter.api.Test khác với org.junit.Test. Một test class dùng annotation của engine không tương thích có thể không được phát hiện hoặc chạy theo cách mong đợi.

## 13. Các lỗi thường gặp và cách xử lý

### Không có ApplicationContext hoặc không tìm thấy bean

Nguyên nhân thường là test chưa khai báo cấu hình context, cấu hình chưa component scan/đăng ký bean, hoặc đang dùng sai annotation bootstrapper.

Kiểm tra @ContextConfiguration, @SpringJUnitConfig, @SpringBootTest hay test slice đang dùng. Đọc lỗi khởi tạo context và xác nhận bean cần thiết có trong cấu hình.

### Dùng @ExtendWith nhưng quên cấu hình context

SpringExtension đăng ký integration point, nhưng test vẫn cần nguồn cấu hình. Hãy thêm @ContextConfiguration hoặc dùng @SpringJUnitConfig. Với Spring Boot, chọn annotation Boot phù hợp.

### Dùng annotation JUnit 4 trong test Jupiter

Kiểm tra import của @Test, @RunWith và @ExtendWith. JUnit 4 runner không thay thế JUnit Jupiter extension. Chọn đúng engine và annotation cho test class.

### Constructor test không được autowire

Nếu constructor có tham số bean nhưng Spring chưa được cấu hình autowire constructor, JUnit có thể không tìm thấy ParameterResolver phù hợp. Dùng @TestConstructor(autowireMode = ALL) hoặc cấu hình thuộc tính spring.test.constructor.autowire.mode=all theo chính sách của test suite.

### ParameterResolutionException

Lỗi này có thể xảy ra khi không có resolver hỗ trợ tham số hoặc nhiều resolver cùng nhận một tham số. Kiểm tra kiểu và annotation trên parameter, extension đã đăng ký và cấu hình constructor. Với tham số mock, bảo đảm MockitoExtension hoặc cơ chế mock phù hợp được đăng ký.

### Mock trong test không được service dùng

Một field @Mock không tự thay bean trong ApplicationContext. Hãy tạo service trực tiếp với mock cho unit test, hoặc đăng ký bean override trong context test.

### Test phụ thuộc thứ tự hoặc trạng thái singleton

Context có thể được cache và bean singleton có thể sống qua nhiều test. Reset trạng thái, tạo dữ liệu độc lập hoặc dùng @DirtiesContext khi thực sự cần loại context khỏi cache.

### Test chậm vì khởi động context quá rộng

Nếu chỉ cần một controller, repository hoặc converter, cân nhắc test slice tương ứng. Nếu chỉ kiểm tra logic nghiệp vụ, không cần Spring context. Chọn phạm vi context nhỏ giúp giảm chi phí và làm lỗi dễ khoanh vùng.

## 14. Quy trình chọn cách tích hợp Spring với JUnit Jupiter

Trước khi viết test, hãy xác định điều gì cần được Spring chứng minh:

1. Nếu test chỉ kiểm tra logic Java và dependency có thể truyền trực tiếp, dùng JUnit Jupiter thuần.
2. Nếu cần inject bean hoặc kiểm tra cấu hình Spring Framework, dùng @SpringJUnitConfig hoặc @ExtendWith(SpringExtension.class) kết hợp @ContextConfiguration.
3. Nếu cần kiểm tra Spring Boot auto-configuration hoặc application context, dùng @SpringBootTest hoặc ApplicationContextRunner tùy phạm vi.
4. Nếu chỉ cần một lát cắt như MVC, JPA hoặc JSON, dùng annotation test slice tương ứng.
5. Nếu cần transaction test, SQL setup hoặc context lifecycle, tận dụng TestContext listener và annotation Spring phù hợp.
6. Nếu cần mock một bean trong context, đăng ký bean override rõ ràng; không giả định field @Mock tự thay bean.
7. Nếu nhiều extension cùng giải quyết parameter, kiểm tra annotation và khả năng hỗ trợ tham số để tránh xung đột.

SpringExtension cho phép JUnit Jupiter sử dụng đầy đủ tích hợp Spring TestContext: chuẩn bị test instance, dependency injection, callback lifecycle, parameter resolution và các listener hỗ trợ kiểm thử. Khi kết hợp đúng annotation bootstrapper và phạm vi context, test có thể xác nhận hành vi do Spring quản lý mà vẫn giữ được cấu trúc rõ ràng của JUnit Jupiter.

Hãy xem SpringExtension là cầu nối lifecycle giữa hai framework. JUnit Jupiter điều khiển test và extension points; Spring TestContext quản lý context cùng các listener; Spring ApplicationContext cung cấp bean. Hiểu rõ vai trò từng phần giúp chọn đúng annotation, tránh khởi động context không cần thiết và biết chính xác một test đang chứng minh điều gì.


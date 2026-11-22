# Tránh lớp cha kiểm thử lớn che giấu nhiều phụ thuộc

Trong dự án Spring, việc dùng lại cấu hình và fixture giúp giảm lặp lại giữa các test. Tuy nhiên, một lớp cha kiểm thử có thể lớn dần theo thời gian: chứa nhiều field được inject, nhiều annotation cấp lớp, nhiều phương thức setup và helper cho các tình huống khác nhau. Các test con chỉ cần một phần nhỏ nhưng vẫn thừa hưởng toàn bộ cấu hình và phụ thuộc đó.

Khi điều này xảy ra, tên test không còn cho biết đầy đủ những gì cần để chạy nó. Một test nhìn như kiểm thử service đơn giản có thể thực tế khởi động cả ứng dụng, kết nối database, bật security filter, tạo mock cho nhiều bean và chạy nhiều bước chuẩn bị ẩn trong lớp cha.

**Lớp cha kiểm thử chỉ nên chứa những quy tắc và tài nguyên thực sự chung cho mọi lớp con.** Với phần cấu hình có thể tái sử dụng, annotation tổng hợp có phạm vi rõ ràng, test configuration nhỏ và fixture factory thường làm ý định của test dễ nhìn thấy hơn. Mục tiêu là để người đọc nhận ra test đang dùng loại context nào, cần dependency nào và đang kiểm chứng hành vi gì ngay từ lớp test.

## 1. Vì sao lớp cha kiểm thử lớn trở thành vấn đề?

Hãy hình dung một lớp cha được tạo ra để tránh lặp lại cấu hình Spring:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
abstract class AbstractIntegrationTest {

    @Autowired
    protected MockMvc mockMvc;

    @Autowired
    protected OrderService orderService;

    @Autowired
    protected CustomerService customerService;

    @Autowired
    protected PaymentService paymentService;

    @Autowired
    protected OrderRepository orderRepository;

    @Autowired
    protected CustomerRepository customerRepository;

    @Autowired
    protected PaymentRepository paymentRepository;

    @Autowired
    protected TestDataCleaner testDataCleaner;

    @BeforeEach
    void cleanDatabase() {
        testDataCleaner.cleanAll();
    }

    protected Customer createCustomer() {
        // Tạo khách hàng mặc định.
    }

    protected Order createOrder() {
        // Tạo đơn hàng mặc định.
    }

    protected Payment createPayment() {
        // Tạo thanh toán mặc định.
    }
}
~~~

Một lớp con có thể chỉ cần kiểm tra một quy tắc nhỏ:

~~~java
class OrderNumberFormatterTest extends AbstractIntegrationTest {

    @Test
    void formatsOrderNumber() {
        // Kiểm tra định dạng mã đơn hàng.
    }
}
~~~

Nhưng test này vẫn thừa hưởng:

- Full Spring Boot ApplicationContext.
- MockMvc và cấu hình web.
- Profile test.
- Transaction cho test method.
- Nhiều service và repository không liên quan.
- Logic xóa dữ liệu trước mỗi test.
- Mọi lifecycle callback được khai báo trong lớp cha.

Nếu mục tiêu chỉ là kiểm tra định dạng chuỗi, phần lớn context và fixture đó không đóng góp bằng chứng nào cho hành vi đang kiểm tra. Test có thể chậm, phụ thuộc vào database hoặc thất bại do một bean không liên quan.

### Các dấu hiệu lớp cha đã quá lớn

Một số dấu hiệu thường gặp:

- Lớp con kế thừa chỉ để lấy một field hoặc một helper.
- Lớp cha inject nhiều bean nhưng mỗi lớp con chỉ dùng một vài bean.
- Một thay đổi cấu hình ở lớp cha làm nhiều test không liên quan cùng thất bại.
- Lớp con phải override phương thức setup để tắt một phần logic của lớp cha.
- Có nhiều cờ boolean hoặc hook method để bật/tắt từng phần fixture.
- Test phải đọc cả lớp cha mới hiểu database, profile, transaction hoặc security đang được cấu hình ra sao.
- Một test unit vô tình kế thừa full context chỉ vì cần một helper tạo dữ liệu.
- Lớp cha chứa nhiều phương thức tiện ích thuộc các domain khác nhau.

Vấn đề cốt lõi là quan hệ phụ thuộc đã bị che khuất. Người đọc nhìn vào lớp con không biết nó thực sự cần gì và đang chạy trong môi trường nào.

## 2. Phân biệt tái sử dụng cấu hình với tái sử dụng hành vi

Có hai nhu cầu thường bị gộp vào một lớp cha:

**Tái sử dụng cấu hình:** nhiều test cần cùng một cách khởi động context, cùng profile, cùng tập auto-configuration hoặc cùng một nhóm bean.

**Tái sử dụng hành vi chuẩn bị:** nhiều test cần tạo khách hàng, đơn hàng, tài khoản hoặc dữ liệu kiểm thử theo một quy tắc chung.

Hai nhu cầu này có thể được giải quyết riêng:

| Nhu cầu | Cơ chế thường phù hợp |
|---|---|
| Dùng lại một test slice cho một nhóm controller | Composed annotation dựa trên @WebMvcTest |
| Dùng lại profile và cấu hình cho một nhóm integration test | Annotation tổng hợp hoặc test configuration |
| Đăng ký một số bean hỗ trợ test | @TestConfiguration và @Import |
| Tạo entity hoặc DTO mẫu | Fixture factory hoặc builder |
| Tái sử dụng hành vi setup/cleanup đặc biệt | JUnit Extension hoặc helper có phạm vi rõ |
| Chia sẻ một luồng test có cấu trúc cố định | Abstract base class nhỏ, có hợp đồng rõ ràng |

Không cần gom tất cả vào một superclass. Cấu hình Spring, fixture dữ liệu và hành vi lifecycle là các mối quan tâm khác nhau; giữ chúng riêng giúp test chỉ nhận phần nó cần.

## 3. Annotation tổng hợp giúp tái sử dụng ý định cấu hình

Spring hỗ trợ sử dụng annotation khác làm meta-annotation. Nhờ đó, có thể tạo annotation tổng hợp để nhóm một cấu hình test thường dùng.

Ví dụ, nhiều controller test cùng cần:

- @WebMvcTest.
- Một cấu hình MVC dùng chung.
- Một profile chuyên cho test web.

Có thể định nghĩa annotation riêng:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@WebMvcTest
@ActiveProfiles("web-test")
@Import(WebTestConfiguration.class)
public @interface WebLayerTest {
}
~~~

Lớp test chỉ ra ý định rõ ràng:

~~~java
@WebLayerTest
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private CustomerService customerService;

    @Test
    void returnsCustomerDetails() throws Exception {
        // Gửi request và xác nhận HTTP response.
    }
}
~~~

Người đọc biết đây là test ở tầng web, có profile web-test và cấu hình hỗ trợ MVC. Không cần tìm một lớp cha để hiểu vì sao context có cấu hình đó.

### Cho phép annotation tổng hợp nhận tham số

Nếu annotation tổng hợp cần áp dụng cho nhiều controller khác nhau, có thể chuyển thuộc tính bằng @AliasFor:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@WebMvcTest
@ActiveProfiles("web-test")
@Import(WebTestConfiguration.class)
public @interface WebLayerTest {

    @AliasFor(
            annotation = WebMvcTest.class,
            attribute = "controllers")
    Class<?>[] controllers() default {};
}
~~~

Sử dụng:

~~~java
@WebLayerTest(controllers = CustomerController.class)
class CustomerControllerTest {
    // ...
}
~~~

@AliasFor khai báo thuộc tính của annotation tổng hợp tương ứng với thuộc tính của meta-annotation. Việc đặt alias cần tuân thủ quy tắc của Spring: kiểu dữ liệu và giá trị mặc định phải tương thích với thuộc tính được ánh xạ.

Không tạo một annotation có hàng chục thuộc tính để thay thế một lớp cha khổng lồ. Annotation tổng hợp nên biểu đạt một cấu hình có ý nghĩa và có phạm vi ổn định.

## 4. Tạo các annotation theo từng loại rủi ro

Một dự án có thể có nhiều nhóm test với yêu cầu khác nhau. Hãy đặt tên annotation theo phạm vi hoặc mục đích để người đọc nhận ra test đang kiểm chứng phần nào.

Ví dụ:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@WebMvcTest
@Import(ApiWebTestConfiguration.class)
public @interface ApiControllerTest {
}
~~~

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@DataJpaTest
public @interface JpaRepositoryTest {
}
~~~

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest
@ActiveProfiles("integration")
public @interface ApplicationIntegrationTest {
}
~~~

Cách dùng:

~~~java
@ApiControllerTest
class OrderControllerTest {
    // Chỉ kiểm tra MVC boundary.
}

@JpaRepositoryTest
class OrderRepositoryTest {
    // Kiểm tra mapping và query.
}

@ApplicationIntegrationTest
class OrderWorkflowIntegrationTest {
    // Kiểm tra luồng phối hợp nhiều tầng.
}
~~~

Các annotation này biểu đạt ba phạm vi khác nhau. Test controller không vô tình thừa hưởng database và toàn bộ service như một lớp con của integration base class. Repository test cũng không cần khởi động web server nếu không có rủi ro liên quan đến web.

Tên annotation cần phản ánh đúng cấu hình thật. Nếu @ApplicationIntegrationTest chỉ nạp một context rất nhỏ, tên đó có thể gây hiểu nhầm. Hãy chọn tên mô tả phạm vi và cam kết mà nhóm thống nhất.

### Tránh ghép các cấu hình xung đột

Không nên tạo một annotation tổng hợp đồng thời mang cả @WebMvcTest và @SpringBootTest. Hai annotation này dùng các cơ chế bootstrap và phạm vi context khác nhau. Kết hợp chúng có thể tạo cấu hình khó hiểu hoặc không hợp lệ.

Một annotation tổng hợp nên đại diện cho một cách bootstrap test nhất quán. Nếu một test cần full context và MockMvc, hãy dùng @SpringBootTest kết hợp @AutoConfigureMockMvc trong annotation integration tương ứng.

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("integration")
public @interface MvcIntegrationTest {
}
~~~

Dùng:

~~~java
@MvcIntegrationTest
class OrderWorkflowMvcIntegrationTest {
    // Request đi qua full application context.
}
~~~

Đây là phạm vi khác với @WebMvcTest: full context được khởi động, còn MockMvc gửi request qua Spring MVC test infrastructure.

## 5. Dùng @Import và @TestConfiguration thay cho field ẩn trong lớp cha

Một lớp cha thường chứa nhiều bean chỉ để phục vụ test. Có thể chuyển các bean đó vào một cấu hình test riêng và import có chủ đích.

~~~java
@TestConfiguration(proxyBeanMethods = false)
class OrderTestSupportConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC);
    }

    @Bean
    OrderNumberGenerator orderNumberGenerator() {
        return new SequentialOrderNumberGenerator();
    }
}
~~~

Lớp test chỉ nạp cấu hình khi thực sự cần:

~~~java
@SpringBootTest
@Import(OrderTestSupportConfiguration.class)
class OrderIntegrationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private Clock clock;

    @Test
    void createsOrderUsingConfiguredClock() {
        // Kiểm tra hành vi có phụ thuộc thời gian.
    }
}
~~~

Cấu hình được đặt tên theo vai trò và chỉ được import ở những test cần nó. Người đọc có thể truy ra dependency mà không phải lần theo một cây kế thừa.

### Tách cấu hình hỗ trợ thành các nhóm nhỏ

Nếu có nhiều loại tài nguyên test, có thể tách theo trách nhiệm:

- WebTestConfiguration: converter, formatter, controller advice hoặc thành phần web hỗ trợ.
- PersistenceTestConfiguration: database helper hoặc bean hỗ trợ persistence.
- ClockTestConfiguration: clock cố định để kiểm thử thời gian.
- MessagingTestConfiguration: publisher hoặc listener test double.
- SecurityTestConfiguration: user, authentication hoặc security policy dành cho test.

Không nhất thiết tạo một configuration class cho từng bean. Chỉ tách khi nhóm bean có một mục đích rõ và được nhiều test sử dụng.

## 6. Fixture factory giúp test thể hiện dữ liệu cần thiết

Một lý do phổ biến khiến lớp cha phình to là nó chứa nhiều phương thức tạo dữ liệu:

~~~java
protected Customer createCustomer() { ... }
protected Order createOrder() { ... }
protected Payment createPayment() { ... }
protected Product createProduct() { ... }
protected Invoice createInvoice() { ... }
~~~

Nếu một test chỉ cần một khách hàng, kế thừa cả superclass có thể kéo theo hàng loạt dependency và setup khác. Một fixture factory độc lập có thể cung cấp đúng dữ liệu cần dùng.

~~~java
public final class CustomerFixtures {

    private CustomerFixtures() {
    }

    public static Customer activeCustomer() {
        return new Customer(
                "customer-42",
                "Linh",
                "linh@example.com",
                CustomerStatus.ACTIVE);
    }

    public static Customer customerWithEmail(String email) {
        return new Customer(
                "customer-42",
                "Linh",
                email,
                CustomerStatus.ACTIVE);
    }
}
~~~

Test sử dụng trực tiếp:

~~~java
@Test
void acceptsActiveCustomer() {
    Customer customer = CustomerFixtures.activeCustomer();

    CustomerResult result = customerPolicy.evaluate(customer);

    assertEquals(CustomerStatus.ACTIVE, result.status());
}
~~~

Fixture factory không cần khởi động Spring và không inject repository nếu chỉ tạo object miền nghiệp vụ.

### Phân biệt fixture thuần với fixture cần persistence

Nếu cần lưu dữ liệu vào database, có thể tạo một helper nhận repository rõ ràng:

~~~java
public class CustomerRepositoryFixtures {

    private final CustomerRepository repository;

    public CustomerRepositoryFixtures(
            CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer createActiveCustomer() {
        return repository.save(
                CustomerFixtures.activeCustomer());
    }
}
~~~

Trong test:

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;

    private CustomerRepositoryFixtures fixtures;

    @BeforeEach
    void setUp() {
        fixtures = new CustomerRepositoryFixtures(customerRepository);
    }

    @Test
    void findsActiveCustomer() {
        Customer customer = fixtures.createActiveCustomer();

        // Truy vấn và xác nhận kết quả.
    }
}
~~~

Dependency của fixture được thể hiện ngay tại nơi khởi tạo. Test không cần kế thừa một base class chỉ để lấy repository và một loạt helper không liên quan.

### Builder khi dữ liệu có nhiều biến thể

Nếu entity có nhiều trường và mỗi test cần một biến thể khác nhau, builder có thể giúp dữ liệu rõ ràng:

~~~java
Customer customer = CustomerBuilder.aCustomer()
        .withId("customer-42")
        .withName("Linh")
        .withStatus(CustomerStatus.ACTIVE)
        .withEmail("linh@example.com")
        .build();
~~~

Builder nên có giá trị mặc định hợp lệ và cho phép test ghi đè những trường có ý nghĩa với tình huống. Tránh builder quá thông minh khiến người đọc không biết trường nào được tạo ngầm.

## 7. JUnit Extension phù hợp cho hành vi lifecycle dùng chung

Một lớp cha thường có @BeforeEach hoặc @AfterEach để chuẩn bị và dọn dẹp tài nguyên. Nếu hành vi này là một tiện ích test độc lập, JUnit Jupiter Extension có thể biểu đạt nó rõ hơn.

Ví dụ, một extension ghi nhận thời gian chạy của test:

~~~java
public class ExecutionTimeExtension
        implements BeforeTestExecutionCallback,
                   AfterTestExecutionCallback {

    private static final ExtensionContext.Namespace NAMESPACE =
            ExtensionContext.Namespace.create(
                    ExecutionTimeExtension.class);

    @Override
    public void beforeTestExecution(
            ExtensionContext context) {
        context.getStore(NAMESPACE).put(
                "startedAt", System.nanoTime());
    }

    @Override
    public void afterTestExecution(
            ExtensionContext context) {
        long startedAt = context.getStore(NAMESPACE)
                .get("startedAt", Long.class);

        long elapsed = System.nanoTime() - startedAt;

        System.out.printf(
                "%s took %d ms%n",
                context.getDisplayName(),
                elapsed / 1_000_000);
    }
}
~~~

Có thể đăng ký trên test class:

~~~java
@ExtendWith(ExecutionTimeExtension.class)
class CustomerServiceTest {
    // ...
}
~~~

Extension tách hành vi lifecycle khỏi cây kế thừa. Nhiều test có thể dùng lại nó mà không cần kế thừa một base class chứa thêm dependency.

### Khi nào dùng Extension?

Extension phù hợp khi hành vi có vòng đời riêng, ví dụ:

- Khởi tạo và đóng một tài nguyên ngoài.
- Đăng ký hoặc giải phóng một test listener.
- Cung cấp parameter cho test method.
- Theo dõi lifecycle hoặc metadata của test.
- Quản lý một tài nguyên theo test class hoặc test method.

Nếu hành vi chỉ là tạo một object nhỏ hoặc chuẩn bị một giá trị, helper thông thường thường đơn giản hơn extension. Không cần biến mọi thao tác setup thành extension.

### Extension không phải nơi giấu dependency tùy tiện

Một extension có thể tạo thêm sự phụ thuộc nếu nó tự mở database, kết nối broker, nạp profile hoặc inject nhiều service mà lớp test không thể nhìn thấy. Hãy đặt tên extension theo trách nhiệm, giữ cấu hình tối thiểu và làm rõ điều kiện sử dụng.

## 8. Hiểu đúng kế thừa annotation và kế thừa test class

Java và JUnit/Spring có các quy tắc kế thừa khác nhau. Không nên giả định rằng mọi annotation trên lớp cha đều tự động có hiệu lực ở lớp con.

### @Inherited của Java

Annotation được đánh dấu @Inherited có thể được kế thừa qua superclass khi tra cứu annotation trên class con. Cơ chế này:

- Chỉ áp dụng cho annotation đặt trên class.
- Chỉ áp dụng qua chuỗi superclass.
- Không kế thừa annotation từ interface.
- Không làm annotation trên method tự động được kế thừa theo cùng cơ chế.
- Không áp dụng nếu annotation không được khai báo @Inherited.

Ví dụ annotation tùy chỉnh:

~~~java
@Inherited
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface IntegrationEnvironment {
}
~~~

Nếu lớp cha có @IntegrationEnvironment, lớp con có thể nhìn thấy annotation này thông qua cơ chế tra cứu annotation kế thừa của Java.

### Spring có cơ chế tìm meta-annotation và annotation kế thừa

Spring Test sử dụng cơ chế tìm annotation riêng để hỗ trợ composed annotations, meta-annotations và một số quy tắc kế thừa của các annotation kiểm thử.

Ví dụ, các annotation như @SpringBootTest, @ContextConfiguration và @ActiveProfiles được thiết kế để dùng trong cấu hình test và có thể tham gia cơ chế kế thừa theo quy tắc tương ứng của Spring.

Tuy nhiên, thuộc tính kế thừa có thể có cờ riêng. Ví dụ:

- @ContextConfiguration có các thuộc tính kiểm soát kế thừa locations và classes.
- @ActiveProfiles có thuộc tính inheritProfiles.
- @TestPropertySource có thuộc tính kiểm soát kế thừa locations và properties.
- @NestedTestConfiguration điều khiển việc lớp nested kế thừa cấu hình test từ lớp bao quanh.

Khi dùng annotation tổng hợp, hãy đọc tài liệu của annotation gốc và xác định thuộc tính nào có thể được alias, thuộc tính nào được kế thừa và cách Spring tìm annotation trên superclass.

### @Inherited không giải quyết vấn đề thiết kế lớp cha

Ngay cả khi annotation tổng hợp được kế thừa đúng, việc đặt annotation đó lên một superclass lớn vẫn có thể che giấu phạm vi test. Annotation kế thừa chỉ là cơ chế áp dụng cấu hình; nó không làm cấu hình trở nên phù hợp với mọi lớp con.

Một lớp con nên khai báo trực tiếp annotation phản ánh mục tiêu test khi việc đó làm phạm vi rõ hơn. Chỉ dựa vào superclass khi mọi lớp con thực sự chia sẻ cùng một ý định và cùng hợp đồng cấu hình.

## 9. Lifecycle trong superclass cũng được kế thừa

JUnit Jupiter có thể phát hiện các test method và lifecycle method được kế thừa từ superclass theo quy tắc của JUnit. Do đó, lớp cha không chỉ truyền annotation cấp lớp mà còn có thể thêm setup và cleanup vào mỗi test con.

Ví dụ:

~~~java
abstract class BaseTest {

    @BeforeEach
    void prepareBaseState() {
        // Setup dùng chung.
    }

    @AfterEach
    void cleanBaseState() {
        // Cleanup dùng chung.
    }
}

class CustomerServiceTest extends BaseTest {

    @BeforeEach
    void prepareCustomer() {
        // Setup riêng cho customer.
    }

    @Test
    void createsCustomer() {
        // ...
    }
}
~~~

Trong JUnit Jupiter, setup từ superclass chạy trước setup của subclass; cleanup từ subclass chạy trước cleanup của superclass. Nếu lớp cha có nhiều callback hoặc nhiều lớp kế thừa trung gian, thứ tự thực thi có thể khó nhìn thấy từ test class cuối cùng.

Một base class nhỏ với một callback thật sự chung có thể hữu ích. Nhưng nếu mỗi lớp con phải override hook, đặt cờ hoặc dựa vào một chuỗi callback nhiều tầng, hãy chuyển hành vi sang extension hoặc helper có thể gọi rõ ràng.

## 10. Những dependency thường bị che trong lớp cha

### Full ApplicationContext

Một base class có @SpringBootTest khiến mọi lớp con khởi động full context. Test con có thể không cần web server, database hoặc messaging nhưng vẫn phải chịu chi phí và phụ thuộc đó.

Giải pháp: dùng annotation theo slice hoặc context cấu hình nhỏ cho từng nhóm test.

### Field @Autowired không được khai báo ở test class

Lớp con có thể gọi helper sử dụng service hoặc repository được inject trong superclass. Khi đọc lớp con, dependency không xuất hiện trong phần khai báo field.

Giải pháp: đưa dependency cần thiết thành field rõ ràng trong test class hoặc đưa nó vào một helper được tạo với constructor tham số.

### Setup dữ liệu toàn cục

Một @BeforeEach trong base class có thể xóa toàn bộ database, tạo tài khoản mặc định, khởi động mock server và nạp dữ liệu tham chiếu. Một test nhỏ chỉ cần một record nhưng phải chạy tất cả bước đó.

Giải pháp: chia fixture theo domain và để test gọi đúng factory cần dùng.

### Profile và property ẩn

Superclass có thể kích hoạt profile test, thay property, bật feature flag hoặc đăng ký test initializer. Lớp con nhìn thấy annotation test nhưng không biết bean nào được chọn.

Giải pháp: dùng composed annotation có tên rõ hoặc khai báo profile/property ngay tại test class khi chúng là phần quan trọng của tình huống.

### Transaction và context reset

@Transactional hoặc @DirtiesContext đặt ở superclass có thể ảnh hưởng đến mọi lớp con. Điều này có thể làm test con tưởng rằng dữ liệu luôn rollback hoặc context luôn được khởi động lại.

Giải pháp: đặt transaction scope và context lifecycle ở đúng test class cần chúng. Không dùng annotation cleanup ở base class như biện pháp chữa mọi lỗi state leak.

### Mock được đăng ký từ lớp cha

Một base class có thể khai báo nhiều @MockitoBean hoặc @MockBean. Các lớp con đều nhận các mock đó, kể cả khi không sử dụng. Bean override còn có thể ảnh hưởng tới context caching.

Giải pháp: đặt mock ở test class hoặc annotation/configuration dành riêng cho nhóm test có cùng dependency.

## 11. Một ví dụ chuyển từ base class lớn sang cấu hình rõ ràng

Giả sử ban đầu có:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
abstract class AbstractApplicationTest {

    @Autowired
    protected MockMvc mockMvc;

    @Autowired
    protected CustomerService customerService;

    @Autowired
    protected CustomerRepository customerRepository;

    @Autowired
    protected PaymentService paymentService;

    @Autowired
    protected PaymentRepository paymentRepository;

    @Autowired
    protected TestDataCleaner cleaner;

    @BeforeEach
    void resetAllData() {
        cleaner.cleanAll();
    }
}
~~~

Các lớp con:

~~~java
class CustomerControllerTest extends AbstractApplicationTest {
    // Chỉ dùng mockMvc.
}

class CustomerRepositoryTest extends AbstractApplicationTest {
    // Chỉ dùng customerRepository.
}

class PaymentServiceTest extends AbstractApplicationTest {
    // Chỉ dùng paymentService.
}
~~~

Ba test có ba rủi ro khác nhau nhưng đang dùng cùng một cấu hình. Có thể tách thành:

~~~java
@WebMvcTest(CustomerController.class)
class CustomerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private CustomerService customerService;
}
~~~

~~~java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository customerRepository;
}
~~~

~~~java
@ExtendWith(MockitoExtension.class)
class PaymentServiceTest {

    @Mock
    private PaymentGateway paymentGateway;

    @Mock
    private PaymentRepository paymentRepository;

    @InjectMocks
    private PaymentService paymentService;
}
~~~

Nếu có một nhóm integration test thật sự cần full context, tạo annotation riêng:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest
@ActiveProfiles("integration")
@Transactional
public @interface ApplicationIntegrationTest {
}
~~~

Và lớp cần kiểm tra luồng rộng khai báo:

~~~java
@ApplicationIntegrationTest
class CustomerRegistrationIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private CustomerRepository customerRepository;
}
~~~

Sau khi tách, mỗi lớp test cho thấy dependency và phạm vi cần thiết. Test controller dùng service mock, repository test dùng JPA slice, service test dùng Mockito, còn integration test mới nạp ứng dụng rộng.

## 12. Khi nào abstract base test class vẫn hợp lý?

Không cần loại bỏ mọi lớp cha. Một base class có thể phù hợp khi tất cả lớp con đều chia sẻ một hợp đồng rõ ràng và cùng cần một phần setup ổn định.

Ví dụ, nhiều test cho các implementation của cùng interface có thể kế thừa một bộ contract test:

~~~java
abstract class CustomerStoreContractTest {

    protected abstract CustomerStore customerStore();

    @Test
    void savesAndFindsCustomer() {
        Customer customer = CustomerFixtures.activeCustomer();

        customerStore().save(customer);

        assertEquals(
                customer,
                customerStore().findById(customer.id()).orElseThrow());
    }
}
~~~

Các lớp con cung cấp implementation:

~~~java
class InMemoryCustomerStoreTest
        extends CustomerStoreContractTest {

    private final CustomerStore store =
            new InMemoryCustomerStore();

    @Override
    protected CustomerStore customerStore() {
        return store;
    }
}
~~~

~~~java
@DataJpaTest
class JpaCustomerStoreTest extends CustomerStoreContractTest {

    @Autowired
    private JpaCustomerStore store;

    @Override
    protected CustomerStore customerStore() {
        return store;
    }
}
~~~

Đây là dạng kế thừa có mục đích: superclass chứa cùng một bộ hành vi cần kiểm tra cho mọi implementation. Lớp con chỉ cung cấp đối tượng đang được kiểm tra.

Base class hợp lý thường có các đặc điểm:

- Có một trách nhiệm duy nhất, được mô tả bằng tên.
- Các lớp con thực sự cần hầu hết setup và lifecycle của nó.
- Không chứa dependency của những domain không liên quan.
- Không cần nhiều cờ để tắt từng phần chức năng.
- Không yêu cầu lớp con override nhiều phương thức để sửa hành vi mặc định.
- Có thể hiểu được phạm vi context từ annotation trên lớp cha hoặc annotation tổng hợp được đặt tên rõ.

### Base class có thể chứa test contract

Một bộ contract test cho repository, serializer hoặc adapter có thể là ứng dụng tốt của kế thừa. Các test method dùng chung xác nhận cùng một hợp đồng; mỗi lớp con chỉ cung cấp implementation hoặc fixture cần thiết.

Không nên dùng cùng mô hình cho một lớp cha chỉ nhằm gom mọi bean tiện dụng của ứng dụng.

## 13. Cách thiết kế composed annotation có thể bảo trì

Một annotation tổng hợp tốt nên trả lời ba câu hỏi:

1. Test thuộc phạm vi nào?
2. Cấu hình nào luôn cần cho phạm vi đó?
3. Người dùng annotation có cần tùy chỉnh tham số nào không?

Ví dụ annotation cho test controller:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@WebMvcTest
@Import({
        ApiExceptionHandler.class,
        ApiWebTestConfiguration.class
})
@ActiveProfiles("web-test")
public @interface ApiControllerTest {

    @AliasFor(
            annotation = WebMvcTest.class,
            attribute = "controllers")
    Class<?>[] controllers() default {};
}
~~~

Annotation này có một phạm vi: MVC controller. Các bean hỗ trợ là exception handler và cấu hình web test. Người dùng có thể chỉ định controller qua alias.

Một annotation khác có thể đại diện cho integration test:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("integration")
public @interface FullApplicationMvcTest {
}
~~~

Không đưa mọi profile, mock, repository, service và helper vào một annotation duy nhất. Khi một test cần thêm dependency riêng, khai báo @MockitoBean hoặc @Import tại lớp đó để sự khác biệt được nhìn thấy.

### Có nên đánh dấu annotation tổng hợp là @Inherited?

Chỉ thêm @Inherited khi muốn lớp con tự động nhận annotation từ superclass và điều đó đúng với mọi trường hợp kế thừa dự kiến.

Nếu annotation dùng trực tiếp trên từng test class, không cần @Inherited. Nếu có một base class contract test và mọi subclass phải dùng cùng test environment, có thể cân nhắc. Hãy nhớ @Inherited của Java chỉ áp dụng qua superclass, không qua interface và không điều khiển annotation method.

Đối với Spring test annotations, còn phải xét cơ chế tìm annotation và các thuộc tính kế thừa của Spring. Đừng thêm @Inherited một cách máy móc để làm mọi cấu hình lan xuống lớp con.

## 14. Giữ dependency rõ ràng trong test class

Một test class dễ đọc nên cho thấy những dependency chính mà nó sử dụng.

Ví dụ:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void returnsOrderWhenFound() throws Exception {
        // ...
    }
}
~~~

Chỉ nhìn phần khai báo đã biết test cần MockMvc và thay OrderService bằng mock. Nếu dependency nằm trong một lớp cha sâu, người đọc phải mở thêm file để hiểu test.

Với helper, có thể khởi tạo trực tiếp:

~~~java
private final OrderRequestFactory requestFactory =
        new OrderRequestFactory();
~~~

Nếu helper cần dependency:

~~~java
private OrderRepositoryFixtures fixtures;

@BeforeEach
void setUp() {
    fixtures = new OrderRepositoryFixtures(orderRepository);
}
~~~

Hoặc dùng một bean fixture nếu nó cần được quản lý bởi Spring. Dù chọn cách nào, dependency nên xuất hiện tại điểm sử dụng hoặc trong cấu hình được đặt tên rõ ràng.

### Không lạm dụng constructor của test class

JUnit Jupiter có thể hỗ trợ constructor injection thông qua ParameterResolver, còn SpringExtension có thể cung cấp dependency cho test constructor theo cấu hình phù hợp. Tuy nhiên, việc đưa quá nhiều tham số vào constructor test class có thể làm danh sách phụ thuộc khó đọc.

Hãy dùng constructor hoặc method parameter injection khi nó làm dependency rõ ràng và phù hợp với JUnit/Spring setup của dự án. Field injection trong test cũng có thể chấp nhận được; điều cần tránh là giấu dependency trong superclass không có lý do.

## 15. Tránh setup có điều kiện và nhiều hook trong base class

Một dấu hiệu lớp cha đã gánh quá nhiều trách nhiệm là có các cờ như:

~~~java
abstract class AbstractTest {

    protected boolean cleanDatabase = true;
    protected boolean startMockServer = true;
    protected boolean createDefaultCustomer = true;
    protected boolean enableSecurity = true;

    @BeforeEach
    void setUp() {
        if (cleanDatabase) {
            // ...
        }
        if (startMockServer) {
            // ...
        }
        if (createDefaultCustomer) {
            // ...
        }
        if (enableSecurity) {
            // ...
        }
    }
}
~~~

Mỗi lớp con phải biết những cờ nào cần tắt. Một thay đổi mặc định có thể làm nhiều test thay đổi hành vi mà không có dấu hiệu trong test method.

Thay vì cờ, hãy chia cấu hình theo mục tiêu:

- Test cần database cleanup thì dùng fixture hoặc extension database riêng.
- Test cần mock server thì đăng ký extension hoặc cấu hình mock server rõ ràng.
- Test cần security thì dùng security test configuration.
- Test cần customer mặc định thì gọi CustomerFixtures.
- Test không cần thành phần nào thì không nạp nó.

Nếu nhiều hành vi thực sự luôn đi cùng nhau, có thể nhóm chúng trong một composed annotation hoặc một extension có tên thể hiện đầy đủ trách nhiệm.

## 16. Context caching và tác động của cấu hình dùng chung

Spring TestContext Framework có thể tái sử dụng ApplicationContext khi các test có cấu hình tương đương. Việc dùng annotation tổng hợp giúp nhóm test dùng cùng một cấu hình ổn định, từ đó hỗ trợ context cache.

Tuy nhiên, một base class lớn có thể thêm nhiều khác biệt cấu hình:

- Nhiều profile.
- Nhiều property source.
- Nhiều initializer.
- Nhiều bean override.
- Nhiều cấu hình import.
- Nhiều context hierarchy.

Các test không cần cùng một phạm vi vẫn có thể bị buộc dùng chung cấu hình lớn, hoặc cấu hình của từng lớp con làm context cache phân mảnh.

Hãy giữ cấu hình chung ổn định trong một nhóm test có cùng mục tiêu. Nếu hai nhóm test cần context khác nhau, dùng hai annotation tổng hợp hoặc hai cấu hình test riêng. Không ép chúng vào một base class chỉ để giảm số dòng annotation.

### @DirtiesContext không phải cách thay thế thiết kế fixture

Nếu một lớp cha dùng @DirtiesContext để giải quyết state leak, hãy xác định state đó thuộc đâu:

- Mutable singleton bean: có thể cần reset hoặc context riêng.
- Database row: transaction rollback hoặc cleanup dữ liệu.
- File tạm: xóa file theo lifecycle.
- Mock server: đóng server hoặc reset expectation.
- System property: lưu và khôi phục giá trị.
- Static field: tránh state dùng chung hoặc khôi phục rõ ràng.

@DirtiesContext loại context khỏi cache theo chế độ chỉ định. Nó không tự dọn database, file hoặc dịch vụ ngoài. Đặt annotation này ở superclass có thể làm tất cả lớp con tốn chi phí khởi động lại context.

## 17. Quy trình thu gọn một lớp cha kiểm thử đang lớn

Khi một base class đã có nhiều field và annotation, hãy chuyển dần theo từng nhóm test.

### Bước 1: Liệt kê lớp con và phần chúng thực sự dùng

Với mỗi subclass, ghi nhận:

- Annotation cấp lớp đang được thừa hưởng.
- Bean được inject và field nào được dùng.
- Lifecycle callback nào chạy.
- Helper nào được gọi.
- External resource nào được mở.
- Transaction hoặc profile nào đang có hiệu lực.

Mục đích là thấy rõ phần chung thực sự và phần chỉ phục vụ một vài lớp con.

### Bước 2: Phân nhóm theo rủi ro

Ví dụ:

- Controller tests cần MVC slice.
- Repository tests cần JPA slice.
- Service tests cần unit test với Mockito.
- Integration tests cần full context.
- Test cấu hình cần một context nhỏ với bean thật.

Không phân nhóm theo tên package hoặc theo việc các test tình cờ cùng dùng một repository.

### Bước 3: Chuyển cấu hình chung thành annotation tổng hợp

Tạo annotation cho mỗi nhóm có cùng cách bootstrap và profile. Dùng @AliasFor nếu người dùng annotation cần truyền controller hoặc tham số tương ứng.

### Bước 4: Chuyển fixture thành factory hoặc builder

Đưa việc tạo DTO/entity thuần Java ra khỏi superclass. Tách fixture cần database thành helper nhận repository rõ ràng.

### Bước 5: Chuyển lifecycle behavior thành extension khi phù hợp

Nếu cleanup hoặc setup là một tiện ích độc lập, tạo JUnit Extension. Nếu chỉ có một vài dòng setup, giữ trong test class.

### Bước 6: Làm dependency hiển thị ở lớp test

Khai báo @Autowired, @MockitoBean, @Import hoặc fixture factory tại lớp test. Chỉ giữ superclass cho hợp đồng test thực sự chung.

### Bước 7: Loại bỏ hook và cờ không còn cần

Sau khi lớp con đã tự khai báo cấu hình và fixture, xóa phương thức override, cờ boolean và helper không còn dùng khỏi base class. Đảm bảo không còn test nào phụ thuộc ngầm vào callback cũ trước khi bỏ nó.

### Bước 8: Xác nhận từng phạm vi test riêng

Chạy nhóm test tương ứng sau khi thay đổi. Một MVC slice cần kiểm tra request mapping; JPA slice cần truy vấn thật; unit test cần xác nhận hành vi service; integration test cần xác nhận wiring và hạ tầng. Kết quả của nhóm này không thay thế cho nhóm khác.

## 18. Những lỗi thường gặp khi tái sử dụng annotation và base class

### Một annotation tổng hợp có quá nhiều mục đích

Annotation tên @CommonTest có thể gom profile, database, web, security, mock, transaction và cleanup. Người đọc không biết nó đang tạo ra môi trường nào.

Hãy đặt tên theo một phạm vi cụ thể như @ApiControllerTest hoặc @JpaRepositoryTest.

### Lớp cha chỉ tồn tại để cung cấp một field

Nếu subclass kế thừa chỉ để lấy MockMvc hoặc một fixture, hãy cân nhắc khai báo dependency trực tiếp hoặc tạo helper nhỏ. Không cần một cây kế thừa cho một dependency.

### Lớp cha chứa nhiều bean không liên quan

Mỗi test con nhận thêm phụ thuộc và có thể thất bại vì bean ngoài phạm vi. Chuyển sang slice hoặc cấu hình nhỏ.

### Override setup để tắt hành vi của lớp cha

Nếu nhiều subclass phải override phương thức setup, superclass đang áp đặt một hành vi không thực sự chung. Chia setup thành extension hoặc fixture được gọi rõ ràng.

### Dùng @Inherited mà không hiểu phạm vi

@Inherited chỉ tác động đến annotation cấp class qua superclass. Nó không làm annotation trên interface hoặc method tự động được kế thừa. Spring còn có cơ chế tìm meta-annotation và thuộc tính inheritance riêng.

### Composed annotation che mất cấu hình quá nhiều

Annotation tổng hợp giúp giảm lặp lại, nhưng nếu nó bao gồm quá nhiều cấu hình và mock, người đọc vẫn không biết test thực sự phụ thuộc gì. Giữ annotation nhỏ, đặt tên theo phạm vi và để dependency đặc thù ở lớp test.

### Trộn @WebMvcTest với @SpringBootTest

Hai annotation có cách bootstrap khác nhau. Chọn một phạm vi rõ ràng: MVC slice hoặc full context với @AutoConfigureMockMvc.

### Dùng base class để tái sử dụng dữ liệu

Fixture dữ liệu thường không cần kế thừa. Dùng factory, builder hoặc object mẹ có giá trị mặc định hợp lệ.

### Cho rằng cùng một annotation nghĩa là cùng một hành vi

Một annotation tổng hợp có thể có thuộc tính alias hoặc cấu hình được ghi đè. Hai lớp dùng cùng annotation nhưng cung cấp property, profile hoặc bean override khác nhau có thể tạo context khác nhau. Hãy đọc cấu hình thực tế khi test phụ thuộc vào lựa chọn bean.

## 19. Bảng chọn cơ chế tái sử dụng

| Tình huống | Cơ chế nên cân nhắc | Lý do |
|---|---|---|
| Nhiều controller test có cùng MVC configuration | Composed annotation | Ghi rõ test slice và cấu hình web |
| Nhiều repository test dùng JPA slice | Composed annotation hoặc annotation chuẩn trực tiếp | Giữ context ở persistence boundary |
| Nhiều test cần một bean hỗ trợ giống nhau | @TestConfiguration + @Import | Dependency được nạp có chủ đích |
| Nhiều test tạo cùng một object mẫu | Fixture factory/builder | Không cần Spring hoặc kế thừa |
| Nhiều test cần cùng cleanup lifecycle | JUnit Extension | Tách hành vi lifecycle khỏi superclass |
| Nhiều implementation phải tuân cùng một hợp đồng | Abstract contract test | Chia sẻ test method có ý nghĩa |
| Một nhóm integration test có cấu hình hoàn toàn giống nhau | Composed integration annotation | Tái sử dụng cấu hình full context rõ ràng |
| Các test chỉ tình cờ dùng chung một vài dependency | Khai báo dependency tại từng test | Tránh phụ thuộc ẩn và context quá rộng |

## 20. Checklist thiết kế annotation dùng lại

Khi tạo annotation tổng hợp hoặc lớp cha, hãy tự hỏi:

1. Annotation này đại diện cho một phạm vi kiểm thử cụ thể không?
2. Mọi test sử dụng nó có thực sự cần cùng cấu hình không?
3. Có bean hoặc filter nào được nạp nhưng không liên quan đến mục tiêu?
4. Lớp con có phải override hook hoặc tắt cờ để tránh setup không cần thiết?
5. Dependency chính có thể nhìn thấy từ test class không?
6. Annotation có đang ghép các cơ chế bootstrap xung đột không?
7. @AliasFor có được dùng đúng với thuộc tính của meta-annotation không?
8. @Inherited có thực sự cần thiết không?
9. Test có thể chạy độc lập mà không cần đọc nhiều tầng superclass không?
10. Người bảo trì có thể biết test đang kiểm chứng rủi ro nào chỉ từ annotation, fixture và assertion không?

Một thiết kế tốt làm rõ ý định của test. Nếu người đọc phải lần theo nhiều lớp cha để tìm ra context, bean override và cleanup, phần tái sử dụng đang che khuất cấu hình.

## 21. Ví dụ cấu trúc thư mục test dễ hiểu

Một cấu trúc có thể tách annotation, configuration và fixture như sau:

~~~text
src/test/java/
  com/example/testing/
    annotations/
      ApiControllerTest.java
      JpaRepositoryTest.java
      MvcIntegrationTest.java
    config/
      ApiWebTestConfiguration.java
      PersistenceTestConfiguration.java
      FixedClockTestConfiguration.java
    fixtures/
      CustomerFixtures.java
      OrderFixtures.java
      CustomerRepositoryFixtures.java
    extensions/
      ExecutionTimeExtension.java

  com/example/customer/
    CustomerControllerTest.java
    CustomerRepositoryTest.java
    CustomerServiceTest.java

  com/example/order/
    OrderControllerTest.java
    OrderRepositoryTest.java
    OrderWorkflowIntegrationTest.java
~~~

Cấu trúc cụ thể phụ thuộc quy mô dự án. Một module nhỏ có thể đặt annotation và fixture gần package test sử dụng chúng. Điều quan trọng là tên và vị trí giúp người đọc tìm được cấu hình mà test đang dùng.

## Tài liệu tham khảo

- [JUnit 5 User Guide: Test Classes and Methods](https://junit.org/junit5/docs/current/user-guide/)
- [JUnit 5 User Guide: Extensions](https://junit.org/junit5/docs/current/user-guide/#extensions)
- [Spring Framework Reference: TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [Spring Framework Reference: TestContext Framework — Annotation Support](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/annotation.html)
- [Spring Framework API: AliasFor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/annotation/AliasFor.html)

## Kết luận

Lớp cha kiểm thử lớn có thể làm dependency, context và lifecycle trở nên khó nhìn thấy ở từng test. Hãy giữ superclass cho bộ contract test hoặc hành vi thật sự chung; dùng composed annotation để tái sử dụng một phạm vi cấu hình rõ ràng, @TestConfiguration và @Import cho bean hỗ trợ, fixture factory cho dữ liệu, và JUnit Extension cho lifecycle behavior. Khi dependency và phạm vi được thể hiện ngay tại lớp test, người đọc dễ hiểu test đang chạy trong môi trường nào và bằng chứng của nó có ý nghĩa gì.

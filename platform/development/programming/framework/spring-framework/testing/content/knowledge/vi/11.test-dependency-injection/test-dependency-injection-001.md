# @Autowired cho field, setter và constructor của test

Trong Spring Test, test class cũng có thể nhận bean từ ApplicationContext thông qua dependency injection. Annotation `@Autowired` có thể được đặt trên field, setter method hoặc constructor để Spring cung cấp dependency cho test instance.

Ba cách này phục vụ cùng mục đích nhưng khác nhau về thời điểm injection, cách thể hiện dependency và khả năng giữ trạng thái bất biến. Field injection ngắn gọn, setter injection cho phép gán dependency qua một phương thức, còn constructor injection làm rõ các dependency cần có ngay khi tạo test instance.

Để injection hoạt động, test phải được kết nối với Spring TestContext Framework, thường qua `@SpringJUnitConfig` hoặc cặp `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`. Chỉ thêm `@Autowired` vào một class JUnit thuần không tự tạo ApplicationContext.

## Spring inject vào test instance như thế nào?

Test class do JUnit tạo và quản lý vòng đời. Spring TestContext Framework chuẩn bị test instance bằng cách lấy bean từ ApplicationContext và inject vào những điểm được đánh dấu. Test class không cần được khai báo thành bean bằng `@Component`; Spring Test xử lý riêng đối tượng test trong quá trình chạy test.

Với JUnit Jupiter, `SpringExtension` kết nối lifecycle của JUnit với `TestContextManager`. Các thành phần chính tham gia như sau:

~~~mermaid
sequenceDiagram
    participant J as JUnit Jupiter
    participant S as SpringExtension
    participant T as TestContextManager
    participant C as ApplicationContext
    J->>S: Tạo test instance
    S->>T: Chuẩn bị TestContext
    T->>C: Lấy bean cần inject
    C-->>T: Trả về dependency
    T-->>J: Test instance đã được chuẩn bị
    J->>J: Chạy @BeforeEach và @Test
~~~

Có hai thời điểm cần phân biệt:

- **Constructor injection:** SpringExtension tham gia phân giải tham số constructor trong lúc JUnit tạo test instance. Dependency được truyền vào constructor để đối tượng được tạo hoàn chỉnh.
- **Field và setter injection:** test instance được tạo trước, sau đó Spring Test thực hiện dependency injection trong bước chuẩn bị test instance, trước khi các phương thức `@BeforeEach` và test method chạy.

Trong Spring TestContext Framework, `DependencyInjectionTestExecutionListener` thực hiện việc inject field và phương thức được đánh dấu `@Autowired` vào test instance. SpringExtension hỗ trợ constructor injection cho JUnit Jupiter thông qua cơ chế `ParameterResolver`.

## Điều kiện để @Autowired hoạt động trong test

Cách khai báo thường dùng nhất là `@SpringJUnitConfig`, annotation kết hợp tích hợp JUnit Jupiter với cấu hình ApplicationContext:

~~~java
@SpringJUnitConfig(TestConfig.class)
class CustomerServiceTest {
    // Các dependency được lấy từ ApplicationContext của TestConfig.
}
~~~

Có thể viết tường minh bằng hai annotation:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class CustomerServiceTest {
    // ...
}
~~~

`SpringExtension` kết nối JUnit với Spring TestContext Framework. `@ContextConfiguration` chỉ định nguồn cấu hình dùng để tạo ApplicationContext. Nếu không có extension hoặc cơ chế tích hợp phù hợp, JUnit không biết cách phân giải bean Spring cho test.

Ví dụ cấu hình tối giản:

~~~java
@Configuration
class TestConfig {

    @Bean
    CustomerRepository customerRepository() {
        return new InMemoryCustomerRepository();
    }

    @Bean
    CustomerService customerService(CustomerRepository repository) {
        return new CustomerService(repository);
    }
}
~~~

Các ví dụ tiếp theo giả định `TestConfig` cung cấp bean cần thiết. Trong ứng dụng thực tế, cấu hình có thể là class cấu hình, XML resource, cấu hình Spring Boot hoặc cấu hình test được import.

## Field injection: inject trực tiếp vào thuộc tính

Field injection đặt `@Autowired` trên thuộc tính của test class. Spring gán bean tương ứng vào field trong bước chuẩn bị test instance.

~~~java
@SpringJUnitConfig(TestConfig.class)
class CustomerServiceFieldTest {

    @Autowired
    private CustomerService customerService;

    @Test
    void findsCustomer() {
        var customer = customerService.findById("C-100");

        assertThat(customer).isPresent();
    }
}
~~~

Cách này dễ đọc và ngắn gọn, đặc biệt với test có một vài dependency. Field có thể là `private`; Spring sử dụng cơ chế reflection để thực hiện injection.

Các điểm cần nhớ:

- Field phải là instance field, không dùng `static` cho dependency cần inject theo test instance.
- Dependency chỉ sẵn sàng sau bước Spring chuẩn bị test instance; không truy cập field trong constructor.
- Các phương thức `@BeforeEach` và test method có thể sử dụng dependency sau khi injection hoàn tất.
- Nếu có nhiều bean cùng kiểu, cần chỉ rõ bean bằng `@Qualifier` hoặc thiết lập một bean `@Primary` phù hợp.

Ví dụ khi có hai implementation:

~~~java
@Autowired
@Qualifier("cachedCustomerService")
private CustomerService customerService;
~~~

Field injection phù hợp khi ưu tiên sự ngắn gọn và test không cần thể hiện dependency qua constructor. Tuy nhiên, danh sách dependency bị phân tán trong class, field có thể chưa được khởi tạo ngay sau constructor và khó giữ bất biến bằng `final`.

## Setter injection: inject qua phương thức

Setter injection đặt `@Autowired` trên một phương thức instance. Spring gọi phương thức đó và truyền bean vào tham số.

~~~java
@SpringJUnitConfig(TestConfig.class)
class CustomerServiceSetterTest {

    private CustomerService customerService;

    @Autowired
    void setCustomerService(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Test
    void findsCustomer() {
        var customer = customerService.findById("C-100");

        assertThat(customer).isPresent();
    }
}
~~~

Setter injection làm cho điểm nhận dependency hiển thị thành một phương thức. Nó có thể hữu ích khi cần logic gán hoặc chuẩn hóa trạng thái lúc nhận dependency, dù phần lớn setter injection trong test chỉ cần phép gán đơn giản.

Có thể dùng `@Qualifier` ở tham số setter khi có nhiều bean cùng kiểu:

~~~java
@Autowired
void setCustomerService(
        @Qualifier("cachedCustomerService")
        CustomerService customerService) {
    this.customerService = customerService;
}
~~~

Một số lưu ý:

- Phương thức injection thường nhận một hoặc nhiều tham số mà Spring có thể phân giải.
- Không gọi setter thủ công trước khi Spring chuẩn bị test instance nếu phương thức cần bean từ context.
- Nếu setter có logic phụ, giữ logic đó nhỏ và dễ hiểu để việc chuẩn bị test không tạo thêm side effect.
- Setter cho phép dependency có thể được thay đổi sau khi object được tạo; do đó test cần quản lý rõ trạng thái nếu setter còn được gọi trong các phương thức khác.

Setter injection phù hợp khi dependency có tính tùy chọn hoặc khi cần phương thức thiết lập rõ ràng. Với dependency bắt buộc của test, constructor injection thường diễn đạt yêu cầu đó tốt hơn.

## Constructor injection: nhận dependency khi tạo test instance

Constructor injection truyền dependency vào constructor. Với JUnit Jupiter, Spring có thể phân giải tham số constructor thông qua `SpringExtension`.

Một cách rõ ràng là dùng `@TestConstructor` để yêu cầu Spring tự động autowire tất cả tham số constructor:

~~~java
@SpringJUnitConfig(TestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class CustomerServiceConstructorTest {

    private final CustomerService customerService;

    CustomerServiceConstructorTest(CustomerService customerService) {
        this.customerService = customerService;
    }

    @Test
    void findsCustomer() {
        var customer = customerService.findById("C-100");

        assertThat(customer).isPresent();
    }
}
~~~

Trong chế độ `ALL`, Spring phân giải tất cả tham số constructor từ ApplicationContext. Test instance chỉ được tạo khi các dependency cần thiết đã được cung cấp. Dùng field `final` giúp dependency không bị thay đổi sau khi constructor hoàn tất.

Có thể đặt `@Autowired` trực tiếp trên constructor để yêu cầu autowiring constructor đó:

~~~java
@SpringJUnitConfig(TestConfig.class)
class CustomerServiceAutowiredConstructorTest {

    private final CustomerService customerService;

    @Autowired
    CustomerServiceAutowiredConstructorTest(CustomerService customerService) {
        this.customerService = customerService;
    }
}
~~~

`@TestConstructor` hữu ích khi muốn cấu hình rõ chế độ constructor injection cho test class hoặc một nhóm test thông qua meta-annotation. Thuộc tính `autowireMode` có các lựa chọn:

| Chế độ | Ý nghĩa |
|---|---|
| `ALL` | Tự động autowire tất cả tham số constructor |
| `ANNOTATED` | Chỉ autowire tham số được đánh dấu phù hợp, chẳng hạn `@Autowired`, `@Qualifier` hoặc `@Value` |

Nếu muốn đặt chế độ mặc định cho toàn bộ test suite, có thể cấu hình property `spring.test.constructor.autowire.mode`, ví dụ trong `junit-platform.properties`:

~~~properties
spring.test.constructor.autowire.mode=all
~~~

Khi cấu hình mặc định là `all`, các constructor của test class có thể nhận dependency từ Spring mà không cần lặp lại `@TestConstructor` trên từng class. Cấu hình này nên được ghi nhận rõ trong dự án vì nó ảnh hưởng đến cách JUnit tạo test instance.

Constructor injection phù hợp khi dependency là bắt buộc và muốn thể hiện rõ chúng ngay ở chữ ký constructor. Nó cũng giúp test dùng field `final` và giảm khả năng vô tình sử dụng dependency chưa được inject.

## So sánh ba cách injection

| Tiêu chí | Field | Setter | Constructor |
|---|---|---|---|
| Điểm nhận dependency | Thuộc tính | Phương thức | Tham số constructor |
| Thời điểm | Sau khi tạo instance, trong bước chuẩn bị test | Sau khi tạo instance, trong bước chuẩn bị test | Trong lúc tạo instance |
| Thể hiện dependency bắt buộc | Ít rõ ràng hơn | Khá rõ qua setter | Rõ qua chữ ký constructor |
| Có thể dùng field `final` | Không | Không với phép gán sau khởi tạo | Có |
| Phù hợp với dependency tùy chọn | Có thể, nhưng cần cấu hình rõ | Có | Có thể, nhưng constructor cần quy tắc phù hợp |
| Cấu trúc mã | Ngắn gọn | Có phương thức thiết lập | Rõ ràng, nhiều mã khai báo hơn |

Không có một cách injection phù hợp cho mọi test. Với test có ít dependency và cần sự ngắn gọn, field injection thường dễ dùng. Với dependency có tính tùy chọn hoặc cần một điểm thiết lập riêng, setter injection có thể phù hợp. Với dependency bắt buộc, constructor injection giúp test thể hiện đầy đủ điều kiện để tạo instance.

## Thứ tự lifecycle và thời điểm sử dụng dependency

Với field và setter injection, thứ tự khái quát của JUnit Jupiter và Spring Test là:

1. JUnit tạo test instance bằng constructor.
2. Spring Test chuẩn bị test instance và inject field/setter.
3. JUnit gọi các phương thức `@BeforeEach`.
4. JUnit chạy test method.
5. JUnit gọi các phương thức `@AfterEach`.

Với constructor injection, dependency được phân giải ở bước đầu tiên, trong lúc tạo test instance. Các bước chuẩn bị tiếp theo vẫn diễn ra như bình thường.

Ví dụ:

~~~java
@SpringJUnitConfig(TestConfig.class)
class LifecycleInjectionTest {

    private final CustomerService constructorService;

    @Autowired
    private CustomerRepository fieldRepository;

    LifecycleInjectionTest(CustomerService constructorService) {
        this.constructorService = constructorService;
    }

    @BeforeEach
    void setUp() {
        // Constructor dependency và field dependency đều sẵn sàng tại đây.
        assertThat(constructorService).isNotNull();
        assertThat(fieldRepository).isNotNull();
    }

    @Test
    void executesWithInjectedDependencies() {
        // ...
    }
}
~~~

Để ví dụ này dùng constructor injection theo mặc định một cách rõ ràng, có thể thêm `@Autowired` vào constructor hoặc khai báo `@TestConstructor(autowireMode = ALL)`. Field được Spring inject sau khi constructor hoàn tất và trước `@BeforeEach`.

Không truy cập field được inject trong constructor: lúc đó Spring chưa chạy bước field injection. Nếu constructor cần dependency, hãy nhận nó qua tham số constructor.

Với lifecycle mặc định của JUnit Jupiter là `PER_METHOD`, mỗi test method có test instance riêng. Spring chuẩn bị và inject instance đó. Nếu dùng `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, một instance được dùng cho nhiều test method; field và setter injection được thực hiện khi instance được chuẩn bị, nên không nên thay đổi dependency hoặc giữ trạng thái mutable dùng chung giữa các test method.

## Kết hợp @Autowired với qualifier và value

Cơ chế injection trong test hỗ trợ các annotation chỉ định bean hoặc giá trị cần nhận:

- `@Qualifier` chọn bean cụ thể khi có nhiều bean cùng kiểu.
- `@Value` nhận property hoặc biểu thức được Spring phân giải.
- `@Primary` trên bean cấu hình đánh dấu lựa chọn ưu tiên khi phân giải theo kiểu.

Ví dụ field nhận property:

~~~java
@SpringJUnitConfig(TestConfig.class)
class EndpointConfigurationTest {

    @Value("${service.base-url}")
    private String baseUrl;

    @Test
    void usesConfiguredEndpoint() {
        assertThat(baseUrl).startsWith("http");
    }
}
~~~

Ví dụ constructor nhận bean được chỉ định:

~~~java
@SpringJUnitConfig(TestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class RepositorySelectionTest {

    private final CustomerRepository repository;

    RepositorySelectionTest(
            @Qualifier("jdbcCustomerRepository")
            CustomerRepository repository) {
        this.repository = repository;
    }
}
~~~

Nếu có nhiều bean cùng kiểu và không có qualifier hoặc primary phù hợp, Spring có thể báo lỗi không xác định được bean. Đây là lỗi phân giải dependency trong lúc chuẩn bị test context hoặc test instance; hãy kiểm tra bean definition và qualifier trước khi sửa assertion.

## Constructor injection và tham số của test method

Constructor injection cho test class khác với việc Spring phân giải tham số cho từng test method.

JUnit Jupiter có cơ chế `ParameterResolver`. `SpringExtension` có thể cung cấp dependency cho constructor và các phương thức test/lifecycle theo quy tắc hỗ trợ tham số của Spring. Ví dụ, một test method có thể nhận bean qua tham số được đánh dấu:

~~~java
@Test
void findsCustomer(@Autowired CustomerService customerService) {
    assertThat(customerService.findById("C-100")).isPresent();
}
~~~

Cách truyền dependency qua tham số method hữu ích khi chỉ một test method cần một bean. Nó không biến bean thành field của test class và không thay đổi cách các test method khác nhận dependency.

Không nên nhầm parameter resolution với field/setter injection của `DependencyInjectionTestExecutionListener`. Constructor và method parameters được SpringExtension xử lý thông qua cơ chế mở rộng tham số của JUnit Jupiter; field và setter được xử lý trong bước dependency injection của TestContext Framework.

Khi một test method có nhiều extension cùng muốn phân giải một tham số, cần bảo đảm các resolver không tranh chấp. Với dependency Spring thông thường, đánh dấu `@Autowired` giúp ý định phân giải rõ ràng.

## JUnit 4 và JUnit Jupiter

Constructor injection cho test class gắn với cơ chế tạo instance của test engine. JUnit Jupiter có `ParameterResolver`, nên SpringExtension có thể cung cấp tham số constructor. JUnit 4 truyền thống thường yêu cầu test class có constructor không tham số và không có cơ chế ParameterResolver tương đương; vì vậy field hoặc setter injection thường được sử dụng với SpringRunner.

Nếu dự án chuyển từ JUnit 4 sang JUnit Jupiter, có thể chuyển dần sang constructor injection cho các test cần thể hiện dependency bắt buộc. Cần dùng đúng extension và annotation của phiên bản JUnit đang chạy, không trộn `@RunWith(SpringRunner.class)` của JUnit 4 với `@ExtendWith(SpringExtension.class)` của JUnit Jupiter trong cùng một test class.

## Các lỗi thường gặp

**Quên đăng ký SpringExtension.** `@Autowired` không tự hoạt động trong JUnit thuần. Hãy dùng `@SpringJUnitConfig` hoặc đăng ký `SpringExtension` và cấu hình context.

**Đọc field trước khi Spring inject.** Field injection diễn ra sau constructor. Không truy cập field đó trong constructor; hãy dùng tham số constructor nếu cần ngay lúc tạo instance.

**Constructor có tham số nhưng không được cấu hình autowire.** Kiểm tra `@Autowired`, `@TestConstructor` hoặc property `spring.test.constructor.autowire.mode`. JUnit phải có SpringExtension để phân giải dependency.

**Có nhiều bean cùng kiểu.** Dùng `@Qualifier` hoặc `@Primary`, và kiểm tra profile đang hoạt động.

**Dùng field injection rồi giả định field là immutable.** Field được inject có thể bị thay đổi trong test. Nếu dependency bắt buộc và cần ổn định, constructor injection cùng field `final` rõ ràng hơn.

**Đặt logic nghiệp vụ trong setter injection.** Setter được gọi khi Spring chuẩn bị test instance. Giữ phương thức này tập trung vào việc nhận dependency; fixture và setup của từng kịch bản nên đặt ở lifecycle method hoặc test method phù hợp.

**Dùng constructor injection nhưng constructor làm quá nhiều việc.** Constructor test nên nhận và lưu dependency. Việc tạo dữ liệu, gọi service hoặc thay đổi trạng thái hệ thống nên diễn ra trong setup/test method để lifecycle dễ hiểu.

**Dùng chung test instance và mutable state.** Với `PER_CLASS`, nhiều test method dùng cùng instance. Reset dữ liệu của test trong `@BeforeEach` và tránh thay đổi dependency được inject.

## Chọn cách injection cho test class

Hãy bắt đầu từ vai trò của dependency:

- Dependency bắt buộc cho hầu hết hành vi trong class: ưu tiên constructor injection, đặc biệt khi dùng JUnit Jupiter.
- Dependency đơn giản và test class cần ít mã khai báo: field injection là cách ngắn gọn.
- Dependency chỉ cần trong một số trường hợp hoặc cần một phương thức thiết lập riêng: cân nhắc setter injection.
- Chỉ một test method cần bean: có thể dùng tham số method được SpringExtension phân giải.
- Có nhiều bean cùng kiểu: chỉ định bằng qualifier hoặc primary.
- Cần cấu hình constructor injection nhất quán cho cả nhóm test: dùng `@TestConstructor` hoặc property mặc định của JUnit Platform.

Dù chọn cách nào, hãy bảo đảm Spring Test đã tạo ApplicationContext phù hợp và dependency được inject trước khi test sử dụng. Field và setter injection diễn ra trong bước chuẩn bị test instance; constructor injection diễn ra khi tạo instance qua SpringExtension. Nắm được khác biệt này giúp tránh lỗi null, hiểu rõ lifecycle và thể hiện đúng các dependency mà test cần.

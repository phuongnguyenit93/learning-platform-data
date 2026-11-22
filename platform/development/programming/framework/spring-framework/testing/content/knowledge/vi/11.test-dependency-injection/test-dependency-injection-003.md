# Tiêm tham số phương thức bằng SpringExtension

JUnit Jupiter cho phép một test method hoặc lifecycle method khai báo tham số. Thay vì phải lấy dependency từ field đã được inject, test có thể nhận trực tiếp bean cần dùng trong danh sách tham số của phương thức. **SpringExtension** thực hiện việc phân giải những tham số được đánh dấu để Spring cung cấp bean từ ApplicationContext.

Cách viết này hữu ích khi một test chỉ cần một hoặc hai dependency, khi một lifecycle method cần repository để chuẩn bị dữ liệu, hoặc khi một bài kiểm thử tham số cần kết hợp dữ liệu do JUnit cung cấp với service do Spring cung cấp. Nó cũng giúp người đọc thấy ngay mỗi phương thức phụ thuộc vào thành phần nào.

Để sử dụng, test cần được tích hợp với Spring TestContext Framework, thường thông qua **@SpringJUnitConfig** hoặc cặp **@ExtendWith(SpringExtension.class)** và **@ContextConfiguration**. Tham số cần lấy từ Spring được đánh dấu bằng **@Autowired**; khi có nhiều bean cùng kiểu, có thể dùng thêm **@Qualifier** để chọn đúng bean.

## 1. SpringExtension tham gia phân giải tham số như thế nào?

JUnit Jupiter có cơ chế **ParameterResolver**. Extension triển khai interface này có thể cho JUnit biết nó hỗ trợ loại tham số nào và cung cấp giá trị tương ứng khi test được gọi.

**SpringExtension** triển khai ParameterResolver và kết nối cơ chế này với Spring TestContext Framework. Khi SpringExtension nhận diện một tham số có thể autowire, nó lấy dependency từ ApplicationContext của test.

Ví dụ đơn giản:

~~~java
@Configuration
class GreetingTestConfig {

    @Bean
    GreetingService greetingService() {
        return new GreetingService("Xin chào");
    }
}
~~~

~~~java
@SpringJUnitConfig(GreetingTestConfig.class)
class GreetingServiceTest {

    @Test
    void returnsConfiguredGreeting(
            @Autowired GreetingService greetingService) {

        assertEquals("Xin chào", greetingService.greet());
    }
}
~~~

Khi chạy test:

1. JUnit Jupiter phát hiện test class và extension do **@SpringJUnitConfig** đăng ký.
2. Spring TestContext tạo hoặc lấy lại ApplicationContext theo cấu hình.
3. SpringExtension tham gia quá trình gọi test method.
4. Với tham số được đánh dấu **@Autowired**, SpringExtension phân giải bean phù hợp từ context.
5. JUnit gọi test method với giá trị đã được cung cấp.

Trong ví dụ, test method nhận GreetingService trực tiếp. Không cần khai báo field **@Autowired** trong test class.

**@SpringJUnitConfig** kết hợp **SpringExtension** và **@ContextConfiguration**. Nếu không dùng annotation kết hợp này, có thể khai báo tường minh:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = GreetingTestConfig.class)
class GreetingServiceTest {
}
~~~

Hai cách trên đều tích hợp Spring TestContext với JUnit Jupiter và nạp cấu hình đã chỉ định.

## 2. Đánh dấu tham số bằng @Autowired

Đối với tham số của test method, cách rõ ràng nhất là đặt **@Autowired** ngay trên tham số cần Spring phân giải:

~~~java
@Test
void findsOrder(
        @Autowired OrderService orderService,
        @Autowired OrderRepository orderRepository) {

    Order order = orderService.findById("order-17");

    assertTrue(orderRepository.existsById(order.id()));
}
~~~

Spring tìm bean theo kiểu tham số và áp dụng các quy tắc autowiring thông thường. Nếu chỉ có một bean phù hợp, dependency đó được truyền vào method.

Có thể trộn tham số Spring với các giá trị cục bộ thông thường nếu phương thức tự tạo chúng:

~~~java
@Test
void createsOrder(@Autowired OrderService orderService) {
    String customerId = "customer-test-7";

    Order order = orderService.create(customerId);

    assertEquals(customerId, order.customerId());
}
~~~

Tham số của method không cần phải là một Spring bean trong mọi trường hợp. Spring chỉ phân giải những tham số được đánh dấu hoặc được nhận diện là autowirable theo quy tắc của Spring TestContext. Các giá trị nghiệp vụ đơn giản như chuỗi, số hoặc expected value thường có thể khai báo trực tiếp trong test hoặc được cung cấp bởi JUnit parameterized test.

Không nên mong Spring tự tạo một giá trị tùy ý cho mọi tham số chưa được đánh dấu. Nếu một tham số không được SpringExtension hoặc một JUnit extension khác hỗ trợ, JUnit sẽ báo lỗi phân giải tham số.

## 3. Tiêm tham số vào lifecycle method

Ngoài **@Test**, SpringExtension có thể cung cấp dependency cho các phương thức vòng đời của JUnit Jupiter, chẳng hạn:

- **@BeforeEach**: chạy trước từng test method.
- **@AfterEach**: chạy sau từng test method.
- **@BeforeAll**: chạy một lần trước tất cả test method trong class.
- **@AfterAll**: chạy một lần sau tất cả test method trong class.

Điều này hữu ích khi việc chuẩn bị hoặc dọn dữ liệu cần dùng một bean Spring.

Ví dụ, repository được inject trực tiếp vào **@BeforeEach**:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderRepositoryTest {

    @BeforeEach
    void prepareData(@Autowired OrderRepository repository) {
        repository.deleteAll();
        repository.save(new Order("order-17", "customer-7"));
    }

    @Test
    void findsPreparedOrder(@Autowired OrderRepository repository) {
        Optional<Order> order = repository.findById("order-17");

        assertTrue(order.isPresent());
        assertEquals("customer-7", order.get().customerId());
    }
}
~~~

Mỗi test method có thể nhận repository trong chính chữ ký của nó. Phương thức chuẩn bị dữ liệu cũng khai báo dependency riêng, nên người đọc biết chính xác nó cần thành phần nào.

### Tiêm tham số vào @AfterEach

Nếu test cần dọn dữ liệu sau mỗi phương thức:

~~~java
@AfterEach
void cleanUp(@Autowired OrderRepository repository) {
    repository.deleteAll();
}
~~~

Chỉ dùng cách dọn này khi repository và thao tác cleanup phù hợp với transaction của test. Nếu dữ liệu đã được commit ở transaction khác hoặc có side effect ngoài database, cần chiến lược dọn riêng.

### Tiêm tham số vào @BeforeAll và @AfterAll

JUnit Jupiter mặc định yêu cầu **@BeforeAll** và **@AfterAll** là static. SpringExtension có thể tham gia phân giải tham số của các lifecycle method này:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderSuiteTest {

    @BeforeAll
    static void verifyTestInfrastructure(
            @Autowired OrderRepository repository) {
        assertNotNull(repository);
    }

    @Test
    void testOne() {
        // Test body
    }

    @AfterAll
    static void reportCompletion(
            @Autowired ApplicationContext context) {
        assertNotNull(context);
    }
}
~~~

Nếu muốn **@BeforeAll** và **@AfterAll** là instance method, có thể dùng:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
~~~

Với lifecycle PER_CLASS, JUnit dùng một test instance cho cả class và cho phép các lifecycle method này không cần static. Việc tiêm tham số vẫn do SpringExtension xử lý theo cơ chế của Spring TestContext.

Không nên dùng **@BeforeAll** để thay đổi dữ liệu dùng chung nếu test method chạy song song hoặc phụ thuộc trạng thái mutable của singleton bean. Hãy thiết kế dữ liệu độc lập và xác định rõ lifecycle của tài nguyên.

## 4. Tiêm dependency khi có nhiều bean cùng kiểu

Một ApplicationContext có thể chứa nhiều bean cùng kiểu. Ví dụ ứng dụng có hai Clock: một clock dùng cho nghiệp vụ và một clock dùng để ghi nhận thời gian hệ thống.

Nếu chỉ khai báo tham số kiểu Clock, Spring có thể không biết cần chọn bean nào. Hãy dùng **@Qualifier**:

~~~java
@Configuration
class ClockTestConfig {

    @Bean
    @Qualifier("businessClock")
    Clock businessClock() {
        return Clock.fixed(
                Instant.parse("2026-08-10T09:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    @Qualifier("auditClock")
    Clock auditClock() {
        return Clock.fixed(
                Instant.parse("2026-08-10T10:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Test chọn bean cụ thể:

~~~java
@SpringJUnitConfig(ClockTestConfig.class)
class ClockInjectionTest {

    @Test
    void receivesBusinessClock(
            @Autowired @Qualifier("businessClock") Clock clock) {

        assertEquals(
                Instant.parse("2026-08-10T09:00:00Z"),
                clock.instant()
        );
    }
}
~~~

**@Qualifier** thu hẹp lựa chọn bean theo qualifier đã khai báo. Spring vẫn áp dụng các quy tắc phân giải dependency của container, bao gồm type, qualifier và primary khi phù hợp.

Nếu một bean được đánh dấu **@Primary**, Spring có thể chọn bean đó khi có nhiều candidate cùng kiểu và không có qualifier cụ thể. Tuy nhiên, trong test cần xác nhận một bean chuyên biệt, **@Qualifier** thường làm ý định rõ ràng hơn.

Không nên đổi tên tham số Java rồi cho rằng tên đó luôn là cách chọn bean ổn định. Hãy khai báo qualifier rõ ràng khi có nhiều bean cùng kiểu.

## 5. Kết hợp tham số Spring với @ParameterizedTest

Một trường hợp hữu ích là test cần nhiều bộ dữ liệu đầu vào do JUnit cung cấp, đồng thời cần service được tạo trong Spring context.

JUnit Jupiter hỗ trợ **@ParameterizedTest** cùng các nguồn dữ liệu như **@ValueSource**, **@CsvSource**, **@MethodSource** và **@ArgumentsSource**. SpringExtension có thể cung cấp thêm tham số dependency được đánh dấu **@Autowired**.

Ví dụ:

~~~java
@Configuration
class DiscountTestConfig {

    @Bean
    DiscountService discountService() {
        return new DiscountService();
    }
}
~~~

~~~java
@SpringJUnitConfig(DiscountTestConfig.class)
class DiscountServiceTest {

    @ParameterizedTest
    @CsvSource({
        "100, 10",
        "200, 20",
        "350, 35"
    })
    void calculatesTenPercentDiscount(
            int subtotal,
            int expectedDiscount,
            @Autowired DiscountService discountService) {

        int actual = discountService.calculateDiscount(subtotal);

        assertEquals(expectedDiscount, actual);
    }
}
~~~

JUnit lấy **subtotal** và **expectedDiscount** từ từng dòng của **@CsvSource**. SpringExtension cung cấp DiscountService cho tham số được đánh dấu **@Autowired**.

Với parameterized test, các tham số do argument source cung cấp phải đứng trước các tham số do ParameterResolver cung cấp. Vì vậy, đặt dependency Spring ở cuối danh sách tham số:

~~~java
void test(
        String valueFromSource,
        int numberFromSource,
        @Autowired SomeService service)
~~~

Nếu đặt tham số được phân giải bởi extension trước các tham số của argument source, JUnit có thể báo lỗi vì không thể ánh xạ các đối số theo thứ tự mong đợi.

### Kết hợp @MethodSource và bean Spring

Nguồn dữ liệu của JUnit có thể là method trả về stream hoặc collection. Method nguồn và tham số dependency là hai cơ chế riêng:

~~~java
@ParameterizedTest
@MethodSource("validOrderCases")
void acceptsValidOrder(
        String orderId,
        int quantity,
        @Autowired OrderValidator validator) {

    assertTrue(validator.isValid(orderId, quantity));
}

static Stream<Arguments> validOrderCases() {
    return Stream.of(
            Arguments.of("order-17", 1),
            Arguments.of("order-18", 3),
            Arguments.of("order-19", 5)
    );
}
~~~

Trong ví dụ, **validOrderCases** tạo dữ liệu kiểm thử theo quy tắc của JUnit. OrderValidator được Spring phân giải riêng. Không cần đưa Spring bean vào **@MethodSource** chỉ để truyền dependency cho test method.

Nếu nguồn dữ liệu cần phụ thuộc vào trạng thái ApplicationContext, hãy cân nhắc thiết kế test khác hoặc dùng một cơ chế tạo dữ liệu rõ ràng. Method source thường là static trong cách sử dụng mặc định và không tự động nhận bean từ Spring như một test method.

## 6. Kết hợp tham số JUnit có sẵn với dependency Spring

JUnit Jupiter có các tham số do extension tích hợp cung cấp, chẳng hạn:

- **TestInfo**: thông tin về test hiện tại.
- **TestReporter**: ghi thông tin báo cáo cho test.
- **RepetitionInfo**: thông tin lần lặp trong **@RepeatedTest**.

SpringExtension có thể cùng tham gia phân giải tham số trong một method:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderRepeatedTest {

    @RepeatedTest(3)
    void checksServiceOnEachInvocation(
            RepetitionInfo repetitionInfo,
            @Autowired OrderService orderService) {

        assertTrue(repetitionInfo.getCurrentRepetition() >= 1);
        assertNotNull(orderService);
    }
}
~~~

RepetitionInfo được JUnit cung cấp cho repeated test; OrderService được Spring cung cấp. Mỗi resolver chỉ nên nhận trách nhiệm với tham số mà nó hỗ trợ.

Nếu có nhiều extension cùng tuyên bố hỗ trợ một tham số, JUnit có thể báo lỗi do nhiều resolver cùng phù hợp. Hãy dùng annotation và kiểu tham số rõ ràng để tránh xung đột.

## 7. Tiêm tham số và tiêm field khác nhau thế nào?

Cả hai cách đều lấy bean từ ApplicationContext, nhưng cách thể hiện dependency khác nhau.

### Field injection

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderFieldInjectionTest {

    @Autowired
    private OrderService orderService;

    @Test
    void createsOrder() {
        assertNotNull(orderService);
    }
}
~~~

Field injection phù hợp khi nhiều test method trong class đều dùng cùng một dependency. Tuy nhiên, dependency của từng method không hiện trong chữ ký phương thức.

### Method parameter injection

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
class OrderMethodInjectionTest {

    @Test
    void createsOrder(@Autowired OrderService orderService) {
        assertNotNull(orderService);
    }

    @Test
    void queriesOrder(@Autowired OrderRepository repository) {
        assertNotNull(repository);
    }
}
~~~

Method parameter injection thể hiện dependency ngay tại nơi sử dụng. Nó hữu ích khi mỗi test cần một tập dependency khác nhau hoặc lifecycle method cần bean riêng.

### So sánh

| Tiêu chí | Field injection | Method parameter injection |
|---|---|---|
| Khai báo | Field của test class | Tham số của method |
| Phạm vi thể hiện dependency | Có thể dùng chung trong class | Rõ ở từng method |
| Phù hợp | Nhiều method dùng cùng bean | Dependency khác nhau theo method |
| Hỗ trợ lifecycle method | Field được inject vào test instance | Có thể nhận bean qua tham số |
| Kết hợp dữ liệu JUnit | Dùng field riêng | Có thể kết hợp tham số source và dependency |
| Tái sử dụng | Thuận tiện cho dependency dùng chung | Tốt khi muốn method tự mô tả nhu cầu |

Không có quy tắc bắt buộc mọi test phải dùng một kiểu. Hãy chọn cách giúp dependency dễ nhìn và test dễ đọc. Có thể kết hợp hai cách trong cùng test class nếu mỗi cách có mục đích rõ ràng, nhưng tránh khai báo cùng một dependency ở nhiều nơi khi không cần thiết.

## 8. Khác biệt với constructor injection của test class

SpringExtension cũng hỗ trợ constructor injection cho test class, nhưng cơ chế chọn constructor có quy tắc riêng.

Ví dụ:

~~~java
@SpringJUnitConfig(OrderTestConfig.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class OrderConstructorInjectionTest {

    private final OrderService orderService;

    OrderConstructorInjectionTest(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void usesInjectedService() {
        assertNotNull(orderService);
    }
}
~~~

**@TestConstructor** điều khiển việc Spring autowire tham số constructor của test class. Có thể cấu hình chế độ mặc định qua thuộc tính hệ thống **spring.test.constructor.autowire.mode** theo phiên bản và cấu hình Spring TestContext của dự án.

Method parameter injection là một cơ chế riêng. Với test method hoặc lifecycle method, có thể đánh dấu trực tiếp dependency bằng **@Autowired**:

~~~java
@Test
void usesInjectedService(@Autowired OrderService orderService) {
    assertNotNull(orderService);
}
~~~

Vì vậy, không cần bật chế độ constructor autowire chỉ để dùng **@Autowired** trên tham số test method.

## 9. Phân biệt tham số Spring và tham số thông thường

Không phải mọi tham số của test method đều đến từ Spring. Một method có thể nhận dữ liệu từ nhiều nguồn:

| Nguồn | Ví dụ | Cơ chế |
|---|---|---|
| Spring ApplicationContext | OrderService, Repository, Clock | SpringExtension và @Autowired |
| JUnit argument source | Giá trị CSV, MethodSource, ValueSource | @ParameterizedTest |
| JUnit extension tích hợp | TestInfo, TestReporter, RepetitionInfo | ParameterResolver của JUnit |
| Giá trị do test tự tạo | Chuỗi, số, object cục bộ | Khai báo trong method hoặc helper |

Mỗi tham số cần có một nguồn phân giải rõ ràng. Ví dụ trong một **@ParameterizedTest**, các giá trị CSV được cung cấp bởi JUnit, còn service được Spring cung cấp. Không cần đăng ký dữ liệu CSV thành Spring bean.

Nếu một tham số không được bất kỳ resolver nào hỗ trợ, JUnit sẽ không thể gọi method và thường báo **ParameterResolutionException**. Nếu nhiều resolver cùng hỗ trợ một tham số, JUnit có thể báo lỗi do nhiều resolver phù hợp.

## 10. Bean được tiêm có vòng đời như thế nào?

Method parameter injection lấy bean từ ApplicationContext mà Spring TestContext quản lý. Nó không tự tạo một bản sao bean mới cho mỗi lần gọi test method.

Với bean singleton (mặc định), nhiều test method dùng cùng context có thể nhận cùng instance. Điều này có nghĩa:

- Trạng thái mutable của singleton có thể tồn tại giữa các test.
- Test không nên phụ thuộc thứ tự chạy.
- Dữ liệu test cần được reset hoặc cô lập.
- Context cache có thể giúp tái sử dụng bean giữa các test class có cấu hình tương thích.

Ví dụ, nếu test method nhận một fake repository singleton và thêm dữ liệu vào đó, test method sau có thể nhìn thấy dữ liệu cũ. Có thể dọn dữ liệu ở **@BeforeEach** hoặc **@AfterEach**, dùng transaction phù hợp hoặc tạo bean có scope thích hợp.

Việc dependency được truyền qua tham số không làm thay đổi scope của bean. Spring vẫn áp dụng vòng đời và scope đã cấu hình trong container.

## 11. Những lỗi thường gặp khi tiêm tham số

### Không có SpringExtension

Nếu test chỉ dùng **@Test** mà không tích hợp Spring TestContext, Spring không tham gia phân giải dependency. Hãy dùng **@SpringJUnitConfig** hoặc khai báo **@ExtendWith(SpringExtension.class)** cùng cấu hình context.

### Quên @Autowired trên tham số

Nếu tham số không được SpringExtension hoặc resolver khác hỗ trợ, JUnit sẽ báo **ParameterResolutionException**. Hãy đánh dấu tham số cần Spring phân giải bằng **@Autowired**.

### Không có bean phù hợp

Nếu ApplicationContext không có bean theo kiểu hoặc qualifier yêu cầu, Spring không thể cung cấp tham số. Hãy đăng ký bean bằng **@Bean**, **@Import**, component scan phù hợp hoặc cấu hình test.

### Có nhiều bean cùng kiểu

Nếu có nhiều candidate và không có lựa chọn rõ ràng, Spring có thể báo lỗi không xác định được dependency. Hãy dùng **@Qualifier** hoặc cấu hình **@Primary** khi đó là lựa chọn mặc định có ý nghĩa.

### Trộn sai thứ tự tham số trong parameterized test

Các tham số từ argument source phải đứng trước tham số được phân giải bởi ParameterResolver. Đặt dependency Spring ở cuối danh sách tham số của **@ParameterizedTest**.

### Dùng dữ liệu JUnit như một Spring bean

Một giá trị từ **@CsvSource** hoặc **@MethodSource** do JUnit cung cấp. Spring không cần và không nên đăng ký từng giá trị đó thành bean chỉ để test method nhận được nó.

### Dùng bean mutable mà không dọn trạng thái

Bean singleton có thể được dùng lại qua nhiều lần chạy. Hãy dọn dữ liệu hoặc thiết kế dependency stateless khi phù hợp.

### Nhầm method parameter injection với constructor autowiring

**@TestConstructor** điều khiển constructor của test class. Nó không phải điều kiện bắt buộc cho tham số của test method đã được đánh dấu **@Autowired**.

### Đưa tham số không rõ nguồn vào method

Mỗi tham số nên có nguồn phân giải rõ ràng: Spring bean, JUnit argument source hoặc resolver tích hợp. Một tham số tùy ý không có nguồn cung cấp sẽ khiến JUnit không thể gọi method.

## 12. Cách chẩn đoán ParameterResolutionException

Khi JUnit báo lỗi không thể resolve parameter, hãy đọc thông tin method và vị trí tham số trong exception. Sau đó xác định nguồn mà tham số dự kiến nhận:

| Tham số cần nhận | Nguồn phân giải | Điều cần kiểm tra |
|---|---|---|
| Service hoặc repository | SpringExtension | Context đã được nạp và bean đã đăng ký chưa? |
| Bean cụ thể trong nhiều candidate | SpringExtension | Có qualifier hoặc primary phù hợp không? |
| Giá trị CSV | JUnit argument source | Số cột, kiểu dữ liệu và thứ tự tham số có đúng không? |
| TestInfo hoặc RepetitionInfo | JUnit extension tích hợp | Method có đúng loại test/lifecycle không? |

Có thể kiểm tra nhanh:

1. Test class có **@SpringJUnitConfig** hoặc SpringExtension và context configuration không?
2. Tham số Spring có **@Autowired** hoặc qualifier phù hợp không?
3. Context có bean đúng kiểu không?
4. Có nhiều bean cùng kiểu cần qualifier không?
5. Với parameterized test, tham số source có đứng trước tham số resolver không?
6. Có extension khác cùng hỗ trợ một tham số gây xung đột không?
7. Mỗi tham số có một nguồn cung cấp rõ ràng không?

Không nên giải quyết lỗi bằng cách thêm **@Autowired** vào mọi tham số. Trước tiên hãy xác định tham số thuộc về Spring hay JUnit và chọn resolver phù hợp.

## 13. Ví dụ tổng hợp: service, lifecycle method và parameterized test

Ví dụ sau kết hợp một bean Spring, tham số lifecycle và dữ liệu từ JUnit:

~~~java
@Configuration
class PriceTestConfig {

    @Bean
    PriceService priceService() {
        return new PriceService();
    }

    @Bean
    PriceRepository priceRepository() {
        return new InMemoryPriceRepository();
    }
}
~~~

~~~java
@SpringJUnitConfig(PriceTestConfig.class)
class PriceServiceTest {

    @BeforeEach
    void reset(@Autowired PriceRepository repository) {
        repository.deleteAll();
    }

    @ParameterizedTest
    @CsvSource({
        "100, 110",
        "200, 220",
        "350, 385"
    })
    void addsTenPercentTax(
            int netPrice,
            int expectedGrossPrice,
            @Autowired PriceService priceService) {

        assertEquals(
                expectedGrossPrice,
                priceService.grossPrice(netPrice)
        );
    }
}
~~~

Trong mỗi invocation:

- JUnit lấy **netPrice** và **expectedGrossPrice** từ dòng CSV.
- SpringExtension cung cấp PriceService cho tham số được đánh dấu **@Autowired**.
- **@BeforeEach** nhận PriceRepository từ Spring và chuẩn bị trạng thái trước mỗi invocation.
- Test xác nhận kết quả của service bằng expected đã khai báo trong dữ liệu.

Ví dụ giả định PriceService tính thuế 10% theo quy tắc làm tròn phù hợp với các giá trị nguyên đã chọn. Trong dự án thực tế, model tiền tệ nên dùng kiểu số phù hợp như BigDecimal và test cần thể hiện rõ quy tắc scale/làm tròn.

## 14. Khi nào nên dùng method parameter injection?

Phương pháp này phù hợp khi:

- Một test method chỉ cần một vài bean.
- Mỗi test trong class cần các dependency khác nhau.
- Lifecycle method cần repository hoặc service để chuẩn bị, kiểm tra hay dọn dữ liệu.
- Parameterized test cần kết hợp dữ liệu do JUnit cung cấp với bean Spring.
- Muốn làm dependency hiện rõ trong chữ ký method.
- Cần inject qualifier vào một phương thức cụ thể.

Field injection vẫn có thể phù hợp khi nhiều test method dùng cùng dependency. Constructor injection của test class phù hợp khi muốn khai báo dependency chung ở cấp class và cấu hình chế độ autowire rõ ràng.

Hãy giữ method signature dễ đọc. Nếu một test method cần quá nhiều bean, đó có thể là dấu hiệu test đang bao phủ quá nhiều trách nhiệm hoặc cần một fixture/helper rõ ràng hơn. Không cần đưa mọi dependency của context vào chữ ký chỉ vì Spring có thể cung cấp chúng.

## 15. Checklist sử dụng SpringExtension để tiêm tham số

Trước khi hoàn tất test class, hãy xác nhận:

- Test đã tích hợp **SpringExtension** thông qua **@SpringJUnitConfig** hoặc cấu hình tương đương.
- ApplicationContext có các bean mà test cần.
- Tham số Spring được đánh dấu bằng **@Autowired** hoặc metadata injection thích hợp.
- Tham số có nhiều bean candidate dùng **@Qualifier** hoặc cơ chế chọn bean phù hợp.
- Lifecycle method nhận đúng dependency và không làm rò trạng thái sang test khác.
- Với **@ParameterizedTest**, tham số từ nguồn dữ liệu đứng trước tham số do resolver cung cấp.
- Tham số của JUnit như TestInfo và RepetitionInfo được phân giải bởi extension phù hợp.
- Test không nhầm method parameter injection với constructor autowiring.
- Bean singleton và context cache được tính đến khi chuẩn bị dữ liệu.
- Mỗi tham số có một nguồn phân giải rõ ràng.

**SpringExtension** cho phép JUnit Jupiter nhận dependency từ ApplicationContext ngay trong tham số của test method và lifecycle method. Khi kết hợp **@SpringJUnitConfig**, **@Autowired**, **@Qualifier** và các argument source của JUnit, test có thể thể hiện rõ những gì mỗi phương thức cần, đồng thời giữ nguyên cơ chế quản lý bean của Spring TestContext Framework.


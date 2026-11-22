# @TestConstructor và chế độ tự tiêm constructor

Trong JUnit Jupiter, test class cũng là một đối tượng Java cần được khởi tạo trước khi các test method chạy. Nếu test dùng Spring TestContext Framework, Spring có thể cung cấp bean từ ApplicationContext cho constructor của test class. Cách này được gọi là **constructor injection cho test class**.

Spring cung cấp annotation **@TestConstructor** để chọn chế độ tự động tiêm constructor. Annotation này đặc biệt hữu ích khi test có nhiều dependency bắt buộc, muốn khai báo chúng qua constructor và lưu trong các field final. Thay vì để Spring âm thầm gán field sau khi tạo object, danh sách dependency được thể hiện ngay tại điểm khởi tạo test.

Bài học này trình bày cách hoạt động của @TestConstructor, hai chế độ autowire, cấu hình mặc định ở cấp dự án, cách kết hợp với SpringExtension và Spring Boot, cũng như cách phân biệt constructor injection với việc inject tham số cho test method.

## 1. Constructor injection trong test class là gì?

Một test class thường cần một số dependency để kiểm tra hành vi của ứng dụng:

- Service cần được kiểm tra.
- Repository hoặc client phục vụ việc chuẩn bị dữ liệu.
- Clock cố định để kiểm soát thời gian.
- Một bean cấu hình hoặc component hỗ trợ test.

Có thể inject dependency bằng field:

~~~java
@SpringBootTest
class OrderServiceTest {

    @Autowired
    private OrderService orderService;

    @Test
    void shouldCreateOrder() {
        assertNotNull(orderService);
    }
}
~~~

Hoặc inject qua constructor:

~~~java
@SpringBootTest
class OrderServiceTest {

    private final OrderService orderService;

    @Autowired
    OrderServiceTest(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void shouldCreateOrder() {
        assertNotNull(orderService);
    }
}
~~~

Ở cách thứ hai, Spring cung cấp OrderService khi JUnit yêu cầu tạo test instance. Sau khi constructor hoàn tất, field final đã có giá trị và test class ở trạng thái sẵn sàng sử dụng.

**Constructor injection** có một số đặc điểm:

- Dependency bắt buộc được khai báo tường minh trong constructor.
- Có thể lưu dependency vào field final.
- Object không thể được tạo nếu thiếu dependency bắt buộc.
- Test class không cần field injection hoặc setter injection.
- Người đọc dễ thấy test phụ thuộc vào bean nào ngay từ phần khai báo constructor.

Constructor injection cho test class chỉ hoạt động khi SpringExtension tham gia vòng đời JUnit. Nếu test chạy thuần với JUnit và không đăng ký SpringExtension, JUnit không tự biết cách lấy bean từ ApplicationContext.

## 2. SpringExtension tham gia tạo test instance

Spring TestContext Framework tích hợp với JUnit Jupiter thông qua **SpringExtension**. Extension này thực hiện các callback của JUnit và cung cấp khả năng giải quyết tham số từ Spring ApplicationContext.

Có thể đăng ký extension tường minh:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfiguration.class)
class CatalogServiceTest {
}
~~~

Hoặc dùng annotation kết hợp:

~~~java
@SpringJUnitConfig(TestConfiguration.class)
class CatalogServiceTest {
}
~~~

Với Spring Boot, @SpringBootTest đã tích hợp SpringExtension:

~~~java
@SpringBootTest
class CatalogServiceTest {
}
~~~

Vì vậy, khi dùng @SpringBootTest, thông thường không cần thêm @ExtendWith(SpringExtension.class).

Quá trình tạo test instance có thể hình dung như sau:

~~~text
JUnit Jupiter phát hiện test class
        |
        v
JUnit chuẩn bị tạo test instance
        |
        v
SpringExtension tham gia xử lý constructor
        |
        v
Spring lấy bean phù hợp từ ApplicationContext
        |
        v
Spring cung cấp dependency cho constructor
        |
        v
Constructor hoàn tất, test instance được tạo
        |
        v
Các callback setup và test method được thực thi
~~~

Điểm quan trọng: constructor được gọi để tạo test instance, vì vậy dependency phải được giải quyết trước khi object hoàn tất. Đây là lý do constructor injection khác với field injection, vốn được thực hiện sau khi object đã được tạo.

## 3. @TestConstructor dùng để làm gì?

**@TestConstructor** là annotation của Spring TestContext dành cho test class chạy với JUnit Jupiter. Nó xác định Spring có tự động autowire constructor của test class hay không.

Ví dụ:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class OrderServiceTest {

    private final OrderService orderService;
    private final Clock clock;

    OrderServiceTest(
            OrderService orderService,
            Clock clock
    ) {
        this.orderService = orderService;
        this.clock = clock;
    }

    @Test
    void shouldUseConfiguredDependencies() {
        assertNotNull(orderService);
        assertNotNull(clock);
    }
}
~~~

Trong ví dụ này:

- @TestConstructor chọn chế độ tự động autowire toàn bộ constructor.
- OrderService và Clock được lấy từ ApplicationContext.
- Không cần đặt @Autowired trên constructor.
- Các dependency được lưu vào field final.

Annotation có thuộc tính chính là **autowireMode**. Thuộc tính này nhận giá trị từ enum **TestConstructor.AutowireMode**.

Hai chế độ cần hiểu là:

- **ANNOTATED**: chỉ tự động autowire constructor khi constructor test được đánh dấu @Autowired.
- **ALL**: tự động autowire constructor của test class mà không cần đánh dấu @Autowired.

Tên ANNOTATED dễ gây nhầm: chế độ này nói đến việc constructor có được đánh dấu @Autowired hay không. Nó không có nghĩa Spring chỉ inject những tham số riêng lẻ mang annotation @Autowired.

## 4. Chế độ ANNOTATED

ANNOTATED là chế độ mặc định nếu không có cấu hình khác. Trong chế độ này, constructor của test class cần được đánh dấu @Autowired để Spring tự động cung cấp các tham số constructor.

Ví dụ:

~~~java
@SpringJUnitConfig(CatalogTestConfiguration.class)
class CatalogServiceTest {

    private final CatalogService catalogService;

    @Autowired
    CatalogServiceTest(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @Test
    void shouldLoadCatalog() {
        assertNotNull(catalogService);
    }
}
~~~

Spring thấy constructor được đánh dấu @Autowired nên sẽ giải quyết tham số từ ApplicationContext.

Nếu bỏ @Autowired trong khi vẫn dùng chế độ ANNOTATED, constructor không được tự động autowire theo cơ chế này. JUnit sẽ cố giải quyết constructor theo các parameter resolver đang đăng ký; nếu không có resolver phù hợp, test có thể thất bại khi tạo instance.

Chế độ ANNOTATED phù hợp khi:

- Chỉ một số test class cần constructor injection.
- Phần lớn test hiện tại vẫn dùng field hoặc setter injection.
- Muốn quyết định rõ tại từng class có sử dụng constructor injection hay không.
- Không muốn thay đổi hành vi tạo instance của toàn bộ test suite.

Với một dự án đang có nhiều test class cũ, ANNOTATED giúp áp dụng constructor injection từng bước mà không làm thay đổi mặc định của các class khác.

## 5. Chế độ ALL

ALL yêu cầu Spring tự động autowire constructor của test class. Không cần đặt @Autowired trên constructor.

~~~java
@SpringJUnitConfig(CatalogTestConfiguration.class)
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class CatalogServiceTest {

    private final CatalogService catalogService;
    private final Clock clock;

    CatalogServiceTest(
            CatalogService catalogService,
            Clock clock
    ) {
        this.catalogService = catalogService;
        this.clock = clock;
    }

    @Test
    void shouldUseFixedClock() {
        assertNotNull(catalogService);
        assertEquals(ZoneOffset.UTC, clock.getZone());
    }
}
~~~

Trong chế độ này, Spring xem các tham số constructor là dependency cần được giải quyết từ context. Nếu có nhiều bean cùng kiểu, có thể dùng @Qualifier hoặc @Primary để chọn đúng bean.

ALL phù hợp khi:

- Dự án thống nhất sử dụng constructor injection cho test class.
- Hầu hết dependency của test class đều là bean Spring.
- Muốn bỏ lặp annotation @Autowired trên từng constructor.
- Muốn các dependency bắt buộc được thể hiện bằng constructor ở mọi test class thuộc phạm vi cấu hình.

Tuy nhiên, không nên bật ALL một cách tùy tiện cho toàn bộ dự án nếu nhiều test class có constructor phục vụ mục đích khác, chẳng hạn constructor nhận dữ liệu tự tạo hoặc test fixture không phải bean. Trong chế độ ALL, Spring sẽ cố giải quyết tất cả tham số constructor theo cơ chế autowire.

## 6. So sánh ANNOTATED và ALL

| Tiêu chí | ANNOTATED | ALL |
|---|---|---|
| Có phải chế độ mặc định? | Có, nếu không có cấu hình khác | Không |
| Constructor cần @Autowired? | Có | Không |
| Phạm vi áp dụng | Chỉ constructor được đánh dấu | Constructor test class |
| Phù hợp khi | Chỉ một số test dùng constructor injection | Dự án muốn áp dụng nhất quán |
| Khả năng ảnh hưởng test cũ | Thấp hơn | Cao hơn nếu bật toàn cục |
| Rủi ro với tham số không phải bean | Chỉ xuất hiện khi constructor được autowire | Mọi tham số constructor đều cần được Spring giải quyết |

Ví dụ cùng một test class:

~~~java
@SpringBootTest
class PaymentServiceTest {

    private final PaymentService paymentService;

    @Autowired
    PaymentServiceTest(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
~~~

Đây là cách dùng theo ANNOTATED.

Nếu đổi sang ALL:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class PaymentServiceTest {

    private final PaymentService paymentService;

    PaymentServiceTest(PaymentService paymentService) {
        this.paymentService = paymentService;
    }
}
~~~

Hai cách có cùng kết quả về dependency được inject. Khác biệt nằm ở cách kích hoạt cơ chế autowire constructor.

## 7. Cấu hình mặc định toàn cục bằng spring.test.constructor.autowire.mode

Nếu muốn áp dụng cùng một chế độ cho nhiều test class, Spring TestContext hỗ trợ property:

~~~properties
spring.test.constructor.autowire.mode=all
~~~

Có thể đặt property trong file **spring.properties** trên test classpath, ví dụ:

~~~text
src/test/resources/spring.properties
~~~

Nội dung:

~~~properties
spring.test.constructor.autowire.mode=all
~~~

Khi Spring TestContext đọc cấu hình này, các test class không khai báo @TestConstructor sẽ sử dụng chế độ ALL.

Cũng có thể đặt qua JVM system property:

~~~text
-Dspring.test.constructor.autowire.mode=all
~~~

Giá trị có thể dùng:

| Giá trị | Ý nghĩa |
|---|---|
| all | Tự động autowire constructor của test class |
| annotated | Chỉ autowire constructor được đánh dấu @Autowired |

Nếu không thiết lập property toàn cục, Spring dùng chế độ ANNOTATED.

Property toàn cục này thuộc cơ chế cấu hình của Spring Framework, được đọc thông qua SpringProperties. Vì vậy, hãy đặt trong spring.properties hoặc JVM system property theo cơ chế tương ứng. Không nên giả định rằng chỉ thêm nó vào application.yml là đủ để thay đổi chế độ của Spring TestContext.

### Khi nào nên bật ALL toàn cục?

Có thể cân nhắc ALL khi:

- Dự án mới có quy ước constructor injection cho test class.
- Các test class đều dùng constructor để nhận bean.
- Nhóm phát triển kiểm soát được các test có constructor đặc biệt.
- CI và môi trường developer dùng cùng cấu hình test.

Nếu dự án có nhiều module hoặc nhiều nhóm test với cách tổ chức khác nhau, nên cân nhắc cấu hình theo từng test class bằng @TestConstructor để tránh ảnh hưởng ngoài phạm vi.

## 8. Thứ tự ưu tiên giữa @TestConstructor và cấu hình toàn cục

Cấu hình tại test class có thể ghi đè chế độ mặc định toàn cục.

Ví dụ, dự án đặt trong spring.properties:

~~~properties
spring.test.constructor.autowire.mode=all
~~~

Một test class có thể chọn lại ANNOTATED:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ANNOTATED
)
class LegacyRepositoryTest {

    private final RepositoryService repositoryService;

    @Autowired
    LegacyRepositoryTest(RepositoryService repositoryService) {
        this.repositoryService = repositoryService;
    }
}
~~~

Trong trường hợp này, annotation trên class xác định chế độ cho class đó. Các test class khác không khai báo @TestConstructor vẫn dùng giá trị toàn cục.

Có thể ghi nhớ thứ tự quyết định như sau:

~~~text
@TestConstructor trên test class
        |
        | Có khai báo?
        +---- Có ----> Dùng autowireMode của annotation
        |
        +---- Không
                |
                v
spring.test.constructor.autowire.mode
        |
        | Có cấu hình?
        +---- Có ----> Dùng chế độ toàn cục
        |
        +---- Không
                |
                v
        ANNOTATED (mặc định)
~~~

Cách tổ chức này cho phép dự án có một mặc định chung nhưng vẫn giữ ngoại lệ rõ ràng ở những test class cần hành vi khác.

## 9. Dùng @Qualifier và @Value trong constructor test

Constructor injection tuân theo cơ chế giải quyết dependency của Spring. Nếu có nhiều bean cùng kiểu, dùng @Qualifier để chỉ rõ bean cần inject.

Ví dụ có hai Clock:

~~~java
@Configuration(proxyBeanMethods = false)
class ClockTestConfiguration {

    @Bean
    @Qualifier("utcClock")
    Clock utcClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    @Qualifier("localClock")
    Clock localClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T08:00:00Z"),
                ZoneId.of("Asia/Ho_Chi_Minh")
        );
    }
}
~~~

Test có thể chọn bean cụ thể:

~~~java
@SpringJUnitConfig(ClockTestConfiguration.class)
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class ClockConfigurationTest {

    private final Clock clock;

    ClockConfigurationTest(
            @Qualifier("utcClock") Clock clock
    ) {
        this.clock = clock;
    }

    @Test
    void shouldUseUtcClock() {
        assertEquals(ZoneOffset.UTC, clock.getZone());
    }
}
~~~

Nếu cần property thay vì bean, có thể dùng @Value:

~~~java
@SpringBootTest(properties = "app.region=ap-southeast-1")
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class RegionConfigurationTest {

    private final String region;

    RegionConfigurationTest(
            @Value("${app.region}") String region
    ) {
        this.region = region;
    }

    @Test
    void shouldUseConfiguredRegion() {
        assertEquals("ap-southeast-1", region);
    }
}
~~~

Ở đây Spring giải quyết tham số region thông qua property placeholder. @Qualifier giúp chọn bean, còn @Value lấy giá trị từ Environment. Cần phân biệt hai cách này với việc yêu cầu JUnit truyền dữ liệu cho một test invocation.

## 10. Kết hợp constructor injection với @SpringBootTest

Với ứng dụng Spring Boot, có thể inject trực tiếp service và các dependency hỗ trợ từ ApplicationContext.

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class InvoiceServiceTest {

    private final InvoiceService invoiceService;
    private final Clock clock;

    InvoiceServiceTest(
            InvoiceService invoiceService,
            Clock clock
    ) {
        this.invoiceService = invoiceService;
        this.clock = clock;
    }

    @Test
    void shouldCreateInvoice() {
        var invoice = invoiceService.create(sampleOrder());

        assertNotNull(invoice);
        assertNotNull(clock);
    }
}
~~~

@SpringBootTest khởi tạo ApplicationContext theo cấu hình Spring Boot. SpringExtension được tích hợp sẵn nên constructor được giải quyết theo chế độ đã chọn.

Nếu cần một bean chỉ dành cho test, có thể khai báo @TestConfiguration và import:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class InvoiceTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

~~~java
@SpringBootTest
@Import(InvoiceTestConfiguration.class)
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class InvoiceServiceTest {

    private final InvoiceService invoiceService;
    private final Clock clock;

    InvoiceServiceTest(
            InvoiceService invoiceService,
            Clock clock
    ) {
        this.invoiceService = invoiceService;
        this.clock = clock;
    }

    @Test
    void shouldUseTestClock() {
        assertEquals(ZoneOffset.UTC, clock.getZone());
    }
}
~~~

Ví dụ giả định ứng dụng có InvoiceService và không có một Clock bean khác gây xung đột. Nếu có nhiều bean cùng kiểu, hãy dùng @Qualifier hoặc cấu hình @Primary phù hợp.

Không cần thêm @ExtendWith(SpringExtension.class) khi đã dùng @SpringBootTest. Spring Boot đã tích hợp extension này vào annotation kiểm thử.

## 11. Kết hợp với @SpringJUnitConfig và cấu hình tối giản

Không phải test nào cũng cần toàn bộ Spring Boot ApplicationContext. Có thể dùng @SpringJUnitConfig để nạp một cấu hình nhỏ:

~~~java
@Configuration(proxyBeanMethods = false)
class GreetingTestConfiguration {

    @Bean
    Clock clock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }

    @Bean
    GreetingService greetingService(Clock clock) {
        return new GreetingService(clock);
    }
}
~~~

Test class:

~~~java
@SpringJUnitConfig(GreetingTestConfiguration.class)
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class GreetingServiceTest {

    private final GreetingService greetingService;

    GreetingServiceTest(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @Test
    void shouldGenerateGreetingAtFixedTime() {
        var greeting = greetingService.greet("Lan");

        assertEquals(
                "Hello Lan at 2026-01-01T00:00:00Z",
                greeting
        );
    }
}
~~~

Cấu hình nhỏ giúp test chỉ khởi tạo những bean cần thiết. Constructor injection vẫn hoạt động như khi dùng @SpringBootTest vì @SpringJUnitConfig cũng đăng ký SpringExtension.

Cách này phù hợp khi mục tiêu là kiểm tra một nhóm bean và cấu hình cụ thể, không cần các auto-configuration khác của ứng dụng.

## 12. Phân biệt constructor injection với tham số của test method

Một điểm quan trọng là **@TestConstructor chỉ điều khiển việc autowire constructor của test class**. Nó không quyết định cách JUnit truyền tham số cho từng test method.

Ví dụ, một test class có thể constructor-inject service, nhưng test method nhận dữ liệu từ @ParameterizedTest:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class DiscountServiceTest {

    private final DiscountService discountService;

    DiscountServiceTest(DiscountService discountService) {
        this.discountService = discountService;
    }

    @ParameterizedTest
    @CsvSource({
            "100000, 0",
            "200000, 10000",
            "500000, 50000"
    })
    void shouldCalculateDiscount(
            BigDecimal amount,
            BigDecimal expectedDiscount
    ) {
        var result = discountService.calculate(amount);

        assertEquals(expectedDiscount, result);
    }
}
~~~

Trong ví dụ:

- DiscountService được inject khi tạo test instance.
- amount và expectedDiscount được JUnit cung cấp cho từng invocation từ @CsvSource.
- @TestConstructor không làm các giá trị CSV trở thành bean Spring.

Không nên đưa dữ liệu riêng của từng test case vào constructor test class. Constructor được dùng để nhận dependency ổn định từ context; dữ liệu thay đổi theo từng tình huống nên được truyền vào test method, parameterized test hoặc fixture setup.

SpringExtension cũng có thể giải quyết tham số cho test method và lifecycle method trong các trường hợp được hỗ trợ, ví dụ tham số được đánh dấu @Autowired, @Qualifier hoặc @Value. Đây là cơ chế parameter resolution riêng, không phải tác dụng của @TestConstructor.

## 13. Constructor injection và test lifecycle

Constructor của test class được gọi khi JUnit tạo test instance. Vì vậy, chế độ test instance lifecycle ảnh hưởng đến số lần constructor được thực thi.

Với PER_METHOD mặc định:

- JUnit tạo một test instance cho mỗi test method.
- Constructor injection được thực hiện mỗi lần tạo instance.
- Spring ApplicationContext thường được tái sử dụng qua context cache.
- Các singleton bean trong cùng context có thể vẫn là cùng một object giữa các test instance.

Với PER_CLASS:

- JUnit tạo một test instance dùng chung cho cả class.
- Constructor injection chỉ diễn ra khi instance đó được tạo.
- Các field của test instance được giữ lại giữa các test method.
- Cần quản lý state mutable cẩn thận.

Ví dụ:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class CatalogLifecycleTest {

    private final CatalogService catalogService;
    private int invocationCount;

    CatalogLifecycleTest(CatalogService catalogService) {
        this.catalogService = catalogService;
    }

    @BeforeEach
    void setUp() {
        invocationCount = 0;
    }

    @Test
    void shouldLoadCatalog() {
        invocationCount++;
        assertNotNull(catalogService);
    }
}
~~~

PER_CLASS không thay đổi quy tắc giải quyết dependency của @TestConstructor. Nó chỉ thay đổi thời điểm và số lần JUnit tạo test instance.

Không nên dựa vào việc constructor được gọi nhiều lần để reset singleton bean trong Spring. Test instance và ApplicationContext có vòng đời độc lập.

## 14. Những trường hợp không nên dùng ALL

ALL thuận tiện khi mọi tham số constructor đều là dependency có thể được Spring giải quyết. Nhưng chế độ này có thể không phù hợp nếu constructor chứa dữ liệu không phải bean.

Ví dụ:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class ReportServiceTest {

    ReportServiceTest(
            ReportService reportService,
            String reportName
    ) {
        // ...
    }
}
~~~

Nếu String reportName không được cung cấp bằng một cơ chế injection phù hợp như @Value, Spring không thể tự suy ra giá trị cần truyền. Test có thể thất bại khi tạo instance.

Hãy dùng constructor cho dependency ổn định:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class ReportServiceTest {

    private final ReportService reportService;

    ReportServiceTest(ReportService reportService) {
        this.reportService = reportService;
    }

    @Test
    void shouldGenerateSummary() {
        var reportName = "monthly-sales";

        var report = reportService.generate(reportName);

        assertNotNull(report);
    }
}
~~~

Nếu một tham số thực sự là property cấu hình, dùng @Value hoặc inject một lớp @ConfigurationProperties. Nếu đó là dữ liệu riêng của một test case, tạo trong test method hoặc truyền qua parameterized test.

Cũng nên tránh ALL toàn cục khi:

- Có test class kế thừa với constructor không tương thích.
- Có constructor test nhận dữ liệu do framework khác cung cấp.
- Nhiều module dùng JUnit extension khác nhau.
- Một số test class không cần Spring nhưng nằm trong suite có cấu hình global property.
- Việc bật ALL làm thay đổi cách JUnit và Spring giải quyết tham số trong các test hiện hữu.

Trong các tình huống đó, giữ ANNOTATED và bật ALL trên đúng class cần constructor injection sẽ dễ kiểm soát hơn.

## 15. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Constructor không nhận được bean | SpringExtension chưa được đăng ký | Dùng @SpringJUnitConfig hoặc @SpringBootTest |
| Constructor không được autowire | Đang ở chế độ ANNOTATED nhưng thiếu @Autowired | Đánh dấu constructor hoặc chọn ALL |
| Không tìm thấy bean theo kiểu | Bean chưa được đăng ký hoặc context thiếu configuration | Kiểm tra @ContextConfiguration, component scan và cấu hình bean |
| Có nhiều bean cùng kiểu | Spring không xác định được ứng viên | Dùng @Qualifier hoặc @Primary |
| Không inject được tham số String/Integer | Không có bean hoặc nguồn @Value phù hợp | Dùng @Value, configuration properties hoặc tạo dữ liệu trong test method |
| Test cũ đột nhiên lỗi sau khi bật ALL toàn cục | Constructor của test class có tham số không phải bean | Thu hẹp phạm vi ALL hoặc sửa cấu trúc constructor |
| Tham số @ParameterizedTest bị hiểu nhầm là dependency | Nhầm constructor injection với method parameter resolution | Giữ test data ở tham số method |
| Dependency field null | Dùng field trước khi Spring chuẩn bị test instance hoặc không có SpringExtension | Kiểm tra annotation và lifecycle |
| Test instance mới nhưng bean vẫn giữ state | ApplicationContext cache tái sử dụng singleton | Reset state hoặc thiết kế bean stateless |

Khi chẩn đoán lỗi, hãy kiểm tra lần lượt:

1. Test có chạy với SpringExtension không?
2. Test class đang dùng ANNOTATED hay ALL?
3. Constructor có được đánh dấu @Autowired khi cần không?
4. Mỗi tham số có thể được Spring giải quyết từ bean, qualifier hoặc property không?
5. ApplicationContext có đăng ký bean tương ứng không?
6. Có nhiều bean cùng kiểu hoặc cấu hình profile làm bean bị loại bỏ không?
7. Cấu hình global có vô tình thay đổi test class khác không?

## 16. So sánh constructor injection, field injection và method parameter injection

| Cách tiêm phụ thuộc | Thời điểm | Điểm mạnh | Điểm cần lưu ý |
|---|---|---|---|
| Constructor injection | Khi tạo test instance | Dependency bắt buộc rõ ràng; có thể dùng field final | Cần constructor và chế độ autowire phù hợp |
| Field injection | Sau khi tạo test instance | Khai báo ngắn, quen thuộc với nhiều test cũ | Field không final; dependency ít tường minh hơn |
| Setter/method injection | Sau khi tạo instance hoặc qua lifecycle callback | Có thể dùng cho dependency tùy chọn hoặc setup | Dễ tạo trạng thái object chưa hoàn chỉnh |
| Test method parameter | Khi từng test method được gọi | Phù hợp với dependency theo method và dữ liệu test | Cần SpringExtension hoặc parameter resolver phù hợp |
| Parameterized test argument | Mỗi invocation | Thích hợp cho dữ liệu đầu vào thay đổi theo trường hợp | Đây là dữ liệu test do JUnit cung cấp, không phải bean injection |

Constructor injection thường phù hợp với dependency bắt buộc và ổn định trong cả test class. Field injection có thể vẫn hợp lý trong các test đơn giản hoặc codebase hiện hữu. Method parameter phù hợp khi chỉ một test cần một dependency hoặc khi dữ liệu thay đổi theo từng invocation.

Không cần chuyển toàn bộ test suite sang constructor injection chỉ vì @TestConstructor tồn tại. Hãy dùng nó khi việc khai báo dependency tại constructor làm test rõ ràng và dễ bảo trì hơn.

## 17. Quy trình áp dụng @TestConstructor trong dự án

Khi đưa constructor injection vào một dự án Spring hiện có, có thể thực hiện theo các bước:

1. Chọn một test class có các dependency bắt buộc, ổn định.
2. Xác minh test class đang chạy với SpringExtension thông qua @SpringJUnitConfig hoặc @SpringBootTest.
3. Chọn ANNOTATED để áp dụng cục bộ, hoặc ALL nếu dự án đã thống nhất quy ước.
4. Khai báo constructor nhận các bean cần thiết.
5. Lưu dependency vào field final.
6. Dùng @Qualifier hoặc @Value nếu cần phân biệt bean hoặc lấy property.
7. Chạy test class và xác minh lỗi tạo context, lỗi thiếu bean hoặc lỗi tham số.
8. Nếu muốn bật ALL toàn cục, kiểm tra các test class có constructor đặc biệt trước khi thay đổi cấu hình.
9. Giữ dữ liệu riêng từng test method trong test method hoặc parameterized test.
10. Theo dõi trạng thái mutable của test instance và singleton bean khi chạy cả suite hoặc chạy song song.

Ví dụ, một nhóm test mới có thể thống nhất:

~~~java
@SpringBootTest
@TestConstructor(
        autowireMode = TestConstructor.AutowireMode.ALL
)
class CustomerServiceTest {

    private final CustomerService customerService;
    private final Clock clock;

    CustomerServiceTest(
            CustomerService customerService,
            Clock clock
    ) {
        this.customerService = customerService;
        this.clock = clock;
    }
}
~~~

Trong khi các test class cũ vẫn dùng ANNOTATED hoặc field injection. Cách chuyển đổi theo từng nhóm giúp tránh thay đổi hành vi của toàn bộ suite cùng lúc.

## 18. Kết luận

@TestConstructor giúp cấu hình cách Spring tự động inject dependency vào constructor của test class khi chạy với JUnit Jupiter và SpringExtension.

Hai chế độ cần nhớ:

- **ANNOTATED**: chỉ autowire constructor test được đánh dấu @Autowired. Đây là mặc định khi không có cấu hình khác.
- **ALL**: tự động autowire constructor của test class mà không cần @Autowired.

Có thể chọn chế độ trên từng class bằng @TestConstructor hoặc đặt mặc định cho dự án bằng spring.test.constructor.autowire.mode trong spring.properties hay JVM system property. Annotation tại class cho phép một test chọn chế độ riêng.

Hãy dùng constructor injection cho các dependency bắt buộc, ổn định và có thể lấy từ ApplicationContext. Dùng @Qualifier khi có nhiều bean cùng kiểu, @Value cho property, và tham số test method cho dữ liệu thay đổi theo từng tình huống. Khi phân biệt rõ dependency của test class với dữ liệu của từng test invocation, @TestConstructor giúp test dễ đọc, ít trạng thái trung gian và dễ bảo trì hơn.


# Vòng đời lớp, test instance và phương thức kiểm thử

Một bài test trong Spring chịu tác động của hai vòng đời phối hợp với nhau: vòng đời của JUnit Jupiter và vòng đời quản lý test của Spring TestContext Framework. JUnit tạo test instance, gọi các phương thức chuẩn bị và dọn dẹp, rồi thực thi phương thức kiểm thử. Spring tích hợp vào các mốc đó để nạp ApplicationContext, inject dependency, quản lý transaction, chạy SQL test và xử lý những trạng thái dùng chung.

Hiểu đúng các mốc này giúp trả lời những câu hỏi thường gặp: Vì sao field được @Autowired trước khi @BeforeEach chạy? Vì sao mỗi test method có một test instance mới nhưng bean Spring vẫn giữ trạng thái? Vì sao dữ liệu database có thể được rollback sau test? Khi nào nên dùng @TestInstance(PER_CLASS), và khi nào cần @DirtiesContext?

Bài học tập trung vào quan hệ giữa **vòng đời lớp test**, **vòng đời test instance** và **vòng đời từng phương thức kiểm thử** trong Spring Framework Testing.

## 1. Hai vòng đời cùng tham gia một bài test

JUnit Jupiter quản lý cách test class và test method được thực thi. Spring TestContext Framework bổ sung khả năng chuẩn bị môi trường Spring và cung cấp các callback cho từng giai đoạn của test.

Có thể hình dung trách nhiệm như sau:

~~~text
JUnit Jupiter
    |
    +-- Tạo test instance
    +-- @BeforeAll / @AfterAll
    +-- @BeforeEach / @AfterEach
    +-- @Test và các test invocation
    +-- Quản lý extension callbacks
            |
            v
SpringExtension
    |
    v
TestContextManager
    |
    +-- Chuẩn bị test instance và inject dependency
    +-- Gọi TestExecutionListener trước/sau từng method
    +-- Quản lý transaction test
    +-- Chạy SQL test
    +-- Quản lý trạng thái ApplicationContext
~~~

**JUnit** quyết định khi nào một phương thức kiểm thử được chạy và một test instance tồn tại trong bao lâu. **Spring** cung cấp context, bean và các hành vi hỗ trợ tại những điểm mở rộng do JUnit cung cấp.

Trong JUnit Jupiter, Spring thường được tích hợp bằng một trong các annotation sau:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfiguration.class)
class PricingServiceTest {
}
~~~

Hoặc dùng annotation kết hợp:

~~~java
@SpringJUnitConfig(TestConfiguration.class)
class PricingServiceTest {
}
~~~

Với Spring Boot, @SpringBootTest đã tích hợp SpringExtension:

~~~java
@SpringBootTest
class ApplicationServiceTest {
}
~~~

Vì vậy, khi dùng @SpringBootTest hoặc @SpringJUnitConfig, thông thường không cần khai báo thêm @ExtendWith(SpringExtension.class).

## 2. Vòng đời của một test class trong JUnit Jupiter

JUnit Jupiter cung cấp các annotation chính để đánh dấu những giai đoạn của test:

| Annotation | Thời điểm | Mục đích |
|---|---|---|
| @BeforeAll | Một lần trước các test method trong class | Chuẩn bị tài nguyên dùng chung ở cấp class |
| @BeforeEach | Trước mỗi lần thực thi test method | Chuẩn bị dữ liệu và trạng thái riêng cho test |
| @Test | Phần thực thi chính | Kiểm tra một hành vi |
| @AfterEach | Sau mỗi lần thực thi test method | Dọn trạng thái của lần test vừa chạy |
| @AfterAll | Một lần sau các test method trong class | Giải phóng tài nguyên cấp class |

Ví dụ đơn giản:

~~~java
class CalculatorTest {

    @BeforeAll
    static void beforeAll() {
        System.out.println("Prepare test class");
    }

    @BeforeEach
    void beforeEach() {
        System.out.println("Prepare test method");
    }

    @Test
    void shouldAddNumbers() {
        assertEquals(5, 2 + 3);
    }

    @Test
    void shouldMultiplyNumbers() {
        assertEquals(6, 2 * 3);
    }

    @AfterEach
    void afterEach() {
        System.out.println("Clean test method");
    }

    @AfterAll
    static void afterAll() {
        System.out.println("Release test class");
    }
}
~~~

Với cấu hình mặc định của JUnit Jupiter, một test instance mới được tạo cho mỗi test method. Vì vậy, @BeforeAll và @AfterAll là static trong chế độ mặc định: chúng chạy ở cấp class, không phụ thuộc một instance cụ thể.

Trình tự khái quát:

~~~text
@BeforeAll
    |
    +-- Tạo test instance cho method thứ nhất
    |       |
    |       +-- @BeforeEach
    |       +-- @Test
    |       +-- @AfterEach
    |
    +-- Tạo test instance cho method thứ hai
    |       |
    |       +-- @BeforeEach
    |       +-- @Test
    |       +-- @AfterEach
    |
@AfterAll
~~~

Thứ tự giữa các test method không nên được dùng làm cơ chế chia sẻ trạng thái. Nếu test B chỉ chạy đúng sau test A, bộ test có thể thất bại khi JUnit thay đổi thứ tự hoặc chạy song song.

## 3. Test instance lifecycle: PER_METHOD và PER_CLASS

JUnit Jupiter cung cấp hai chế độ quản lý test instance.

### 3.1. PER_METHOD — chế độ mặc định

Trong chế độ PER_METHOD, JUnit tạo một instance mới cho mỗi test method.

~~~java
class ShoppingServiceTest {

    private int callCount = 0;

    @Test
    void firstTest() {
        callCount++;
        assertEquals(1, callCount);
    }

    @Test
    void secondTest() {
        callCount++;
        assertEquals(1, callCount);
    }
}
~~~

Hai test method có hai instance khác nhau. Do đó, field callCount được khởi tạo lại từ đầu ở mỗi instance.

Ưu điểm:

- Trạng thái instance được cô lập giữa các test method.
- Ít nguy cơ một test làm thay đổi field khiến test khác thất bại.
- Dễ viết setup riêng cho từng test.
- Phù hợp với đa số unit test và integration test.

Đây là chế độ nên giữ làm mặc định nếu không có lý do rõ ràng để chia sẻ test instance.

### 3.2. PER_CLASS — một instance dùng chung cho cả class

Có thể yêu cầu JUnit chỉ tạo một test instance cho toàn bộ class bằng @TestInstance:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ShoppingServiceTest {

    private int callCount = 0;

    @BeforeAll
    void beforeAll() {
        callCount = 0;
    }

    @Test
    void firstTest() {
        callCount++;
        assertEquals(1, callCount);
    }

    @Test
    void secondTest() {
        callCount++;
        assertEquals(2, callCount);
    }
}
~~~

Trong ví dụ này, hai test method dùng cùng một object nên field callCount được giữ lại giữa các method. @BeforeAll và @AfterAll có thể là instance method, không cần static.

PER_CLASS hữu ích khi:

- Cần tạo một tài nguyên đắt đỏ một lần cho cả class.
- Có setup cấp class cần truy cập field hoặc dependency đã được inject.
- Test cần một object cấu hình dùng chung và có cách bảo đảm trạng thái ổn định.
- Muốn giảm chi phí tạo test instance khi class có nhiều test method.

Tuy nhiên, trạng thái mutable trong test instance có thể rò rỉ giữa các method. Nếu một test thay đổi danh sách, mock, object fixture hoặc biến thành viên, test tiếp theo có thể nhận dữ liệu đã bị sửa.

Ví dụ dễ gây lỗi:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CartTest {

    private final List<String> items = new ArrayList<>();

    @Test
    void shouldAddFirstItem() {
        items.add("BOOK");
        assertEquals(1, items.size());
    }

    @Test
    void shouldStartWithEmptyCart() {
        assertTrue(items.isEmpty());
    }
}
~~~

Test thứ hai phụ thuộc vào việc test thứ nhất đã chạy hay chưa. Nếu chạy riêng, nó có thể xanh; khi chạy cả class, nó có thể đỏ.

Nếu dùng PER_CLASS, hãy chủ động reset state trong @BeforeEach hoặc tạo fixture mới cho từng test method:

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CartTest {

    private List<String> items;

    @BeforeEach
    void setUp() {
        items = new ArrayList<>();
    }

    @Test
    void shouldAddItem() {
        items.add("BOOK");
        assertEquals(1, items.size());
    }

    @Test
    void shouldStartWithEmptyCart() {
        assertTrue(items.isEmpty());
    }
}
~~~

### 3.3. Cấu hình PER_CLASS ở cấp dự án

JUnit cho phép đặt mặc định test instance lifecycle bằng cấu hình:

~~~properties
junit.jupiter.testinstance.lifecycle.default = per_class
~~~

Có thể đặt trong file junit-platform.properties trên test classpath.

Cấu hình này tác động đến các test class không khai báo lifecycle riêng. Khi thay đổi mặc định ở cấp dự án, cần xem xét tất cả test có mutable state vì các test trước đây dựa vào instance mới có thể bắt đầu chia sẻ state.

Trong một dự án Spring lớn, nên chọn chế độ rõ ràng và nhất quán. Nếu dùng PER_CLASS toàn cục, cần kiểm soát setup và cleanup chặt hơn.

## 4. SpringExtension kết nối vào vòng đời JUnit như thế nào?

SpringExtension là JUnit Jupiter extension tích hợp Spring TestContext Framework. Extension này chuyển các callback của JUnit thành lời gọi đến TestContextManager.

Các callback quan trọng gồm:

| Callback của SpringExtension | Công việc trong TestContext |
|---|---|
| BeforeAllCallback | beforeTestClass |
| TestInstancePostProcessor | prepareTestInstance |
| BeforeEachCallback | beforeTestMethod |
| BeforeTestExecutionCallback | beforeTestExecution |
| AfterTestExecutionCallback | afterTestExecution |
| AfterEachCallback | afterTestMethod |
| AfterAllCallback | afterTestClass |

Tên callback giúp phân biệt hai mốc thường bị nhầm:

- **beforeTestMethod** xảy ra trước các phương thức @BeforeEach của JUnit.
- **beforeTestExecution** xảy ra ngay trước phần thân test method, sau giai đoạn setup @BeforeEach.
- **afterTestExecution** xảy ra ngay sau phần thân test method, trước giai đoạn @AfterEach.
- **afterTestMethod** xảy ra sau các phương thức @AfterEach.

Trình tự khái quát khi chạy một test method:

~~~text
Spring: beforeTestClass (một lần cho class)
        |
JUnit tạo test instance
        |
Spring: prepareTestInstance
        |-- Dependency injection
        |-- Chuẩn bị test instance
        |
Spring: beforeTestMethod
        |-- TestExecutionListener trước method
        |
JUnit: @BeforeEach
        |
Spring: beforeTestExecution
        |-- Listener ngay trước test body
        |
JUnit: @Test
        |
Spring: afterTestExecution
        |-- Listener ngay sau test body
        |
JUnit: @AfterEach
        |
Spring: afterTestMethod
        |-- Listener sau method
        |
Spring: afterTestClass (một lần sau class)
~~~

Đây là trình tự khái quát để hiểu trách nhiệm của từng giai đoạn. Các extension khác, nested test, test template hoặc cấu hình listener có thể bổ sung callback riêng.

Điểm quan trọng là Spring không tự gọi tất cả annotation JUnit. JUnit điều khiển vòng đời test; SpringExtension tham gia qua extension API để thực hiện công việc của TestContext Framework.

## 5. TestContextManager và TestExecutionListener

TestContextManager là đối tượng điều phối quá trình kiểm thử tích hợp với Spring. Nó giữ TestContext cho class đang kiểm thử và thông báo các sự kiện vòng đời cho các TestExecutionListener.

Một TestExecutionListener có thể thực hiện công việc ở một hoặc nhiều mốc:

- Trước khi test class chạy.
- Khi chuẩn bị test instance.
- Trước test method.
- Ngay trước và sau test body.
- Sau test method.
- Sau khi test class kết thúc.

Một số listener thường gặp trong Spring TestContext:

| Listener | Trách nhiệm chính |
|---|---|
| DependencyInjectionTestExecutionListener | Inject dependency vào test instance |
| DirtiesContextTestExecutionListener | Xử lý context được đánh dấu dirty |
| TransactionalTestExecutionListener | Quản lý transaction cho test có @Transactional |
| SqlScriptsTestExecutionListener | Thực thi SQL được khai báo bằng @Sql |
| EventPublishingTestExecutionListener | Phát các sự kiện test lifecycle của Spring |

Các listener mặc định được Spring đăng ký theo cơ chế của TestContext Framework. Một số annotation như @Transactional, @Sql hoặc @DirtiesContext dựa vào các listener tương ứng để thực hiện công việc.

Khi tùy chỉnh @TestExecutionListeners, cần chú ý chế độ hợp nhất listener mặc định. Nếu vô tình thay thế danh sách mặc định mà không giữ các listener cần thiết, dependency injection, transaction hoặc SQL test có thể không còn hoạt động như mong đợi.

## 6. Dependency injection diễn ra ở thời điểm nào?

Trong JUnit Jupiter, SpringExtension triển khai TestInstancePostProcessor. Sau khi JUnit tạo test instance, extension gọi TestContextManager để chuẩn bị instance đó.

Spring có thể inject dependency vào field:

~~~java
@SpringBootTest
class CatalogServiceTest {

    @Autowired
    private CatalogService catalogService;

    @Test
    void shouldFindCatalogItem() {
        assertNotNull(catalogService);
    }
}
~~~

Với cách khai báo này, field được inject trong giai đoạn prepareTestInstance, trước khi @BeforeEach và test method chạy.

Do đó, có thể sử dụng dependency đã inject trong @BeforeEach:

~~~java
@BeforeEach
void setUp() {
    catalogService.resetTestData();
}
~~~

Hãy cẩn thận với các phương thức static. Một @BeforeAll static method trong chế độ PER_METHOD không thể truy cập field instance đã được inject. Nếu cần dùng dependency Spring trong setup cấp class, có thể cân nhắc PER_CLASS để dùng @BeforeAll instance method, hoặc thiết kế setup bằng cơ chế khác phù hợp.

SpringExtension cũng hỗ trợ parameter resolution cho constructor, test method và lifecycle method trong các trường hợp Spring có thể giải quyết tham số. Ví dụ, một test method có thể nhận bean qua tham số được đánh dấu @Autowired:

~~~java
@Test
void shouldUseConfiguredCatalog(@Autowired CatalogService catalogService) {
    assertNotNull(catalogService);
}
~~~

Với constructor injection cho test class, có thể dùng @TestConstructor(autowireMode = ALL) hoặc cấu hình chế độ autowire constructor của Spring TestContext. Hãy kiểm tra cấu hình phiên bản Spring đang dùng nếu chọn cách này.

## 7. Vòng đời test instance khác vòng đời Spring bean

Một điểm rất dễ nhầm là test instance và Spring bean có vòng đời độc lập.

Mặc định, JUnit tạo test instance mới cho mỗi test method. Nhưng Spring ApplicationContext thường được tái sử dụng từ context cache. Bean singleton trong context có thể được dùng chung giữa nhiều test method và thậm chí nhiều test class có cùng cấu hình context.

Ví dụ:

~~~text
ApplicationContext được cache
    |
    +-- CatalogService (singleton)
    +-- CatalogRepository
    +-- Clock
    |
    +-- Test class A
    |      +-- Test instance A1
    |      +-- Test instance A2
    |
    +-- Test class B
           +-- Test instance B1
           +-- Test instance B2
~~~

Các test instance có thể mới, nhưng CatalogService singleton trong cùng ApplicationContext vẫn là cùng một bean.

Điều này dẫn đến hai dạng trạng thái khác nhau:

**Trạng thái của test instance**

- Field trong test class.
- Danh sách fixture được tạo trong @BeforeEach.
- Biến tạm và mock được khai báo trong test instance.
- Đối tượng test helper được giữ trong field.

**Trạng thái của Spring ApplicationContext và bean**

- Singleton bean có field mutable.
- Cache trong ứng dụng.
- Listener hoặc scheduler được đăng ký trong context.
- Mock bean được dùng chung trong context.
- Các singleton lưu dữ liệu trong bộ nhớ.

PER_METHOD chỉ cô lập test instance. Nó không tự động reset singleton bean hoặc dữ liệu trong database.

Nếu một singleton bean có state mutable, test này có thể ảnh hưởng test khác ngay cả khi mỗi method dùng một test instance riêng. Nên thiết kế service stateless khi phù hợp, hoặc cung cấp cách reset state rõ ràng cho môi trường test.

## 8. Context caching và ảnh hưởng đến nhiều test class

Spring TestContext Framework lưu ApplicationContext vào cache để tránh khởi động lại cùng một cấu hình cho từng test class.

Context được nhận diện dựa trên các thông tin cấu hình như:

- Context loader.
- Các lớp cấu hình.
- Initializer.
- Context customizer và các cấu hình mock bean.
- Active profiles.
- Property sources.
- Parent context và các thông tin liên quan.

Nếu nhiều test class có cấu hình tương đương, Spring có thể tái sử dụng cùng ApplicationContext. Điều này làm bộ test nhanh hơn, nhưng cũng có nghĩa trạng thái singleton có thể tồn tại xuyên qua nhiều class.

Ví dụ:

~~~java
@SpringBootTest
class CatalogServiceTest {
    // Sử dụng ApplicationContext của cấu hình này.
}
~~~

~~~java
@SpringBootTest
class CatalogControllerTest {
    // Có thể dùng lại context tương đương từ cache.
}
~~~

Nếu hai class có cấu hình khác nhau, chẳng hạn active profile hoặc property khác nhau, Spring có thể cần một context khác.

Không nên giả định mỗi test class luôn có một ApplicationContext mới. Cũng không nên dựa vào việc context tình cờ được tạo mới để xóa state mà test đã thay đổi.

### Khi nào dùng @DirtiesContext?

@DirtiesContext đánh dấu ApplicationContext đã bị thay đổi và cần được loại khỏi cache. Spring sẽ tạo context mới khi một test sau đó cần cấu hình tương ứng.

Có thể dùng ở cấp method:

~~~java
@Test
@DirtiesContext
void shouldRebuildContextAfterChangingSingletonState() {
    // Thực hiện thay đổi không thể khôi phục an toàn
    // đối với trạng thái của ApplicationContext.
}
~~~

Hoặc cấp class:

~~~java
@SpringBootTest
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LegacyContextMutationTest {
}
~~~

Một số class mode phổ biến:

- BEFORE_CLASS: đánh dấu context dirty trước khi class chạy.
- AFTER_CLASS: đánh dấu dirty sau khi class kết thúc.
- BEFORE_EACH_TEST_METHOD: làm mới context trước từng method.
- AFTER_EACH_TEST_METHOD: làm mới context sau từng method.

Các mode theo method có thể làm test rất chậm vì phải dựng lại context nhiều lần. Chỉ dùng @DirtiesContext khi test thực sự làm thay đổi cấu trúc hoặc trạng thái context đến mức không thể khôi phục an toàn bằng cleanup thông thường.

@DirtiesContext chỉ xử lý cache ApplicationContext. Nó không tự xóa dữ liệu đã ghi vào database bên ngoài, không dọn file test và không hoàn tác một HTTP request đã gửi đến hệ thống khác. Những tài nguyên đó cần cơ chế cleanup riêng.

## 9. Transaction và thứ tự cleanup trong test method

Spring TestContext có thể quản lý transaction cho test method khi dùng @Transactional.

~~~java
@SpringBootTest
@Transactional
class OrderRepositoryTest {

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldPersistOrderInsideTestTransaction() {
        orderRepository.save(new Order("customer-1", new BigDecimal("250000")));

        assertEquals(1, orderRepository.count());
    }
}
~~~

Với cấu hình transaction test mặc định, transaction được bắt đầu cho test method và rollback sau khi test kết thúc. Điều này giúp dữ liệu trong database được cô lập giữa các test.

TransactionalTestExecutionListener tham gia vào lifecycle thông qua các callback trước và sau test method. Có thể sử dụng các hook chuyên biệt:

- @BeforeTransaction: chạy trước khi transaction test bắt đầu.
- @AfterTransaction: chạy sau khi transaction test kết thúc.
- @Commit: yêu cầu commit thay vì rollback mặc định.
- @Rollback: điều khiển rollback hoặc commit theo cấu hình.
- TestTransaction: điều khiển transaction test trong một số tình huống nâng cao.

### Cleanup trong @AfterEach có thể vẫn nằm trong transaction

Vì transaction test được mở trước các phương thức @BeforeEach và kết thúc sau giai đoạn @AfterEach, thao tác cleanup trong @AfterEach thường chạy trong cùng transaction của test method.

Nếu test dùng rollback mặc định, thao tác cleanup trong database có thể không cần thiết vì toàn bộ transaction sẽ rollback. Tuy nhiên, cleanup vẫn cần thiết cho tài nguyên ngoài transaction như file tạm, mock server, cache ngoài hoặc dữ liệu đã ghi qua kết nối khác.

### Cẩn thận với server chạy trên thread khác

Một tình huống quan trọng:

~~~java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@Transactional
class OrderApiTest {

    @Autowired
    private TestRestTemplate http;

    @Test
    void shouldCreateOrder() {
        http.postForEntity(
                "/api/orders",
                request(),
                OrderResponse.class
        );
    }
}
~~~

Transaction do test quản lý chạy trên thread của test. HTTP request được xử lý trên thread của server. Transaction phía server không tự động tham gia transaction test của thread gửi request.

Vì vậy, rollback transaction test không đảm bảo dữ liệu được tạo bởi request HTTP thật sẽ bị rollback. Test API dùng RANDOM_PORT cần dọn dữ liệu theo cách phù hợp, chẳng hạn xóa bản ghi theo test id hoặc dùng database/container riêng cho vòng đời test.

Đây là lý do cần phân biệt test dùng MockMvc trong cùng tiến trình với test gửi request qua HTTP server thật khi thiết kế dữ liệu và cleanup.

## 10. Lifecycle của test method và các loại test invocation

JUnit Jupiter có nhiều loại test method ngoài @Test:

- @ParameterizedTest: chạy cùng một test logic với nhiều bộ tham số.
- @RepeatedTest: lặp lại một test nhiều lần.
- @TestFactory: tạo dynamic tests.
- @TestTemplate: cung cấp khuôn thực thi cho extension hoặc test framework.

Với các test template như parameterized test và repeated test, các callback trước/sau từng invocation giúp mỗi lần thực thi có thể được setup và cleanup riêng. SpringExtension tiếp tục phối hợp với TestContext trong các giai đoạn tương ứng.

Ví dụ parameterized test:

~~~java
@SpringJUnitConfig(PricingTestConfiguration.class)
class DiscountCalculatorTest {

    @Autowired
    private DiscountCalculator calculator;

    @ParameterizedTest
    @CsvSource({
            "100000, 0.00",
            "200000, 0.05",
            "500000, 0.10"
    })
    void shouldCalculateDiscount(
            BigDecimal amount,
            BigDecimal expectedRate
    ) {
        assertEquals(expectedRate, calculator.discountRate(amount));
    }
}
~~~

Mỗi bộ tham số tạo một lần thực thi test. Nếu có dữ liệu mutable, hãy chuẩn bị lại theo từng invocation và tránh phụ thuộc thứ tự các bộ tham số.

Dynamic tests từ @TestFactory có quy tắc lifecycle riêng: các callback của method factory không đơn giản lặp lại toàn bộ @BeforeEach và @AfterEach cho từng DynamicTest. Nếu cần setup/cleanup riêng cho từng trường hợp động, hãy thiết kế dynamic test executable tự quản lý phần đó hoặc dùng parameterized test khi phù hợp.

## 11. Test lifecycle khi chạy song song

JUnit Jupiter có thể chạy test song song khi bật cấu hình tương ứng. Điều này có thể giảm thời gian chạy, nhưng làm lộ các phụ thuộc trạng thái vốn bị che khuất khi chạy tuần tự.

Rủi ro thường gặp:

- Hai test cùng ghi một bản ghi database.
- Nhiều method dùng chung PER_CLASS instance và sửa cùng field.
- Hai test cùng thay đổi singleton bean trong ApplicationContext.
- Mock bean dùng chung bị reset hoặc cấu hình đồng thời.
- Test cùng dùng một file hoặc một cổng cố định.
- Một test xóa dữ liệu mà test khác đang sử dụng.

Nếu test class dùng PER_CLASS, cần đặc biệt chú ý vì các method chia sẻ một instance. Khi chạy song song, các field mutable có thể bị truy cập đồng thời.

Có thể dùng @Execution(ExecutionMode.SAME_THREAD) cho class hoặc method cần chạy tuần tự, nhưng đây chỉ là biện pháp kiểm soát thực thi. Cách tốt hơn là cô lập dữ liệu và tránh state dùng chung có thể thay đổi.

Ví dụ cấu hình JUnit Platform:

~~~properties
junit.jupiter.execution.parallel.enabled = true
junit.jupiter.execution.parallel.mode.default = concurrent
junit.jupiter.execution.parallel.mode.classes.default = concurrent
~~~

Chỉ bật chạy song song khi các test đã có chiến lược cô lập dữ liệu, tài nguyên và context rõ ràng. Một bộ test chạy nhanh nhưng không ổn định sẽ khó dùng làm tín hiệu tin cậy cho CI.

## 12. Ví dụ tổng hợp: theo dõi lifecycle trong Spring test

Ví dụ dưới đây cho thấy cách JUnit và Spring cùng tham gia:

~~~java
@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class CatalogLifecycleTest {

    @Autowired
    private CatalogService catalogService;

    private String testId;

    @BeforeAll
    void beforeAll() {
        // Instance method vì class dùng PER_CLASS.
        // SpringExtension đã chuẩn bị test instance.
        assertNotNull(catalogService);
    }

    @BeforeEach
    void beforeEach() {
        // Dependency đã được inject.
        testId = UUID.randomUUID().toString();
    }

    @Test
    void shouldFindCatalog() {
        var result = catalogService.findCatalog(testId);

        assertNotNull(result);
    }

    @AfterEach
    void afterEach() {
        // Dọn trạng thái riêng của lần test.
        testId = null;
    }

    @AfterAll
    void afterAll() {
        // Giải phóng tài nguyên cấp class nếu có.
    }
}
~~~

Ví dụ này tập trung vào lifecycle; CatalogService và dữ liệu test cần được cung cấp theo cấu hình của dự án. Nếu test tạo dữ liệu database, hãy bổ sung cleanup phù hợp hoặc dùng transaction test khi ranh giới thực thi cho phép rollback.

Một cách khác là giữ PER_METHOD và dùng @BeforeAll static:

~~~java
@SpringBootTest
class CatalogLifecyclePerMethodTest {

    @Autowired
    private CatalogService catalogService;

    @BeforeAll
    static void beforeAll() {
        // Setup cấp class không truy cập field instance.
    }

    @BeforeEach
    void beforeEach() {
        // catalogService đã được inject vào instance.
        assertNotNull(catalogService);
    }
}
~~~

Cả hai cách đều hợp lệ. Chọn theo nhu cầu chia sẻ trạng thái của test instance, không chỉ vì muốn bỏ từ khóa static.

## 13. Những lỗi lifecycle thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| @Autowired field null trong @BeforeAll static | Static method không truy cập test instance | Dùng PER_CLASS với instance @BeforeAll hoặc chuyển việc dùng bean sang @BeforeEach |
| Test chạy riêng xanh nhưng chạy cả class lại đỏ | Mutable state bị giữ lại giữa method hoặc dữ liệu dùng chung | Reset trong @BeforeEach, tạo fixture mới, cô lập database |
| Test class sau bị ảnh hưởng bởi class trước | ApplicationContext cache và singleton bean dùng chung | Reset bean state, cleanup tài nguyên hoặc dùng @DirtiesContext khi thực sự cần |
| @BeforeEach không thấy bean | SpringExtension chưa được đăng ký hoặc context không chuẩn bị đúng | Dùng @SpringBootTest, @SpringJUnitConfig hoặc @ExtendWith(SpringExtension.class) |
| Dữ liệu vẫn còn sau test có @Transactional | Ghi dữ liệu qua thread hoặc transaction khác, chẳng hạn HTTP server thật | Dọn dữ liệu riêng hoặc dùng môi trường database cô lập |
| Test PER_CLASS thất bại khi chạy song song | Nhiều method cùng sửa state trên một instance | Tách state, chạy tuần tự hoặc thiết kế test thread-safe |
| Context khởi động lại quá nhiều lần | Cấu hình context khác nhau hoặc dùng @DirtiesContext thường xuyên | Chuẩn hóa cấu hình test và chỉ dirty context khi cần |
| @AfterEach không dọn được dữ liệu ngoài database | Cleanup chỉ tác động transaction test | Dùng API cleanup riêng cho file, cache hoặc dịch vụ ngoài |

Khi một test thất bại, hãy xác định state nằm ở đâu trước khi thêm cleanup: test instance, singleton bean, ApplicationContext, transaction database hay tài nguyên bên ngoài. Mỗi loại có vòng đời và cơ chế khôi phục khác nhau.

## 14. Cách thiết kế lifecycle phù hợp cho từng loại test

Với **unit test thuần**, giữ PER_METHOD mặc định, tạo fixture mới cho mỗi method và không cần SpringExtension nếu không kiểm tra hành vi Spring.

Với **Spring slice test**, để SpringExtension quản lý injection và context. Dùng @BeforeEach để chuẩn bị dữ liệu riêng; tránh giữ mutable state trong bean singleton.

Với **Spring integration test**, hiểu rõ context cache và transaction test. Nếu dùng @Transactional, xác minh thao tác đang chạy trong cùng thread/transaction hay qua server thật. Nếu context được tái sử dụng, đảm bảo test không để lại state trong singleton bean.

Với **test có tài nguyên cấp class**, PER_CLASS có thể giảm chi phí tạo tài nguyên, nhưng cần reset dữ liệu và kiểm soát việc chạy song song. Nếu chỉ cần một setup static không dùng field instance, giữ PER_METHOD và @BeforeAll static sẽ đơn giản hơn.

Với **test thay đổi ApplicationContext**, dùng @DirtiesContext ở phạm vi hẹp và xác định rõ thời điểm dirty. Đừng dùng nó thay cho việc xóa dữ liệu database hoặc dọn file.

## 15. Kết luận

Vòng đời kiểm thử trong Spring được hình thành từ JUnit Jupiter và Spring TestContext Framework. JUnit quản lý test class, test instance và test invocation; SpringExtension chuyển các callback của JUnit thành hoạt động chuẩn bị context, inject dependency và thông báo cho TestExecutionListener.

Hãy ghi nhớ các mối quan hệ chính:

- PER_METHOD tạo test instance riêng cho mỗi test method; đây là mặc định của JUnit Jupiter.
- PER_CLASS dùng một test instance chung và cho phép @BeforeAll/@AfterAll là instance method; cần quản lý state cẩn thận.
- SpringExtension chuẩn bị test instance và điều phối TestContext callbacks quanh từng method.
- Test instance mới không có nghĩa ApplicationContext hoặc singleton bean mới; Spring có thể tái sử dụng context qua cache.
- @Transactional thường rollback transaction test sau method, nhưng request qua HTTP server thật chạy trên thread khác có transaction riêng.
- @DirtiesContext loại context khỏi cache khi trạng thái context đã bị thay đổi và không thể khôi phục bằng cleanup thông thường.

Khi xác định được state và tài nguyên thuộc vòng đời nào, ta có thể đặt setup và cleanup đúng thời điểm, giảm phụ thuộc giữa các test method và giữ bộ kiểm thử Spring ổn định khi chạy riêng, chạy cả class hoặc chạy trong CI.


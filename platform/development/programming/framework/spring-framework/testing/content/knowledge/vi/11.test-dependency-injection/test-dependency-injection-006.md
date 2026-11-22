# Kết hợp tham số Spring với ParameterResolver khác

JUnit Jupiter cho phép extension cung cấp đối số cho test constructor và test method thông qua ParameterResolver. Spring TestContext tham gia cơ chế này bằng SpringExtension, giúp test nhận bean từ ApplicationContext. Mockito, các resolver tích hợp của JUnit và extension do dự án tự viết cũng có thể cung cấp tham số trong cùng một test.

Việc kết hợp nhiều nguồn tham số giúp chữ ký test thể hiện rõ dependency và dữ liệu cần thiết. Mỗi tham số cần có một resolver chịu trách nhiệm rõ ràng. Nếu nhiều resolver cùng tuyên bố hỗ trợ một tham số, JUnit báo lỗi vì không thể chọn một resolver duy nhất.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của JUnit Jupiter ParameterResolver.
- Dùng SpringExtension để inject bean vào tham số test method.
- Kết hợp tham số Spring với Mockito, TestInfo, TestReporter và resolver tùy chỉnh.
- Phân biệt đối số từ @ParameterizedTest với tham số do extension cung cấp.
- Hiểu constructor injection cho test class.
- Nhận biết lỗi khi nhiều resolver cùng hỗ trợ một tham số.
- Thiết kế custom resolver có điều kiện rõ ràng để tránh xung đột.
- Chẩn đoán ParameterResolutionException và tổ chức extension dễ bảo trì.

## 1. ParameterResolver trong JUnit Jupiter là gì?

JUnit Jupiter cho phép extension tham gia vào quá trình chuẩn bị và thực thi test. Một extension triển khai ParameterResolver có thể cung cấp giá trị cho tham số của test constructor hoặc test method.

Interface có hai phương thức chính:

~~~java
public interface ParameterResolver extends Extension {

    boolean supportsParameter(
        ParameterContext parameterContext,
        ExtensionContext extensionContext
    ) throws ParameterResolutionException;

    Object resolveParameter(
        ParameterContext parameterContext,
        ExtensionContext extensionContext
    ) throws ParameterResolutionException;
}
~~~

supportsParameter trả lời câu hỏi resolver có chịu trách nhiệm cho tham số đang xét hay không. Nếu trả về true, JUnit gọi resolveParameter để lấy giá trị truyền vào test.

~~~mermaid
flowchart TD
    A["JUnit chuẩn bị test method"] --> B["Đọc từng tham số"]
    B --> C["Hỏi các ParameterResolver"]
    C --> D{"Có đúng một resolver hỗ trợ?"}
    D -->|Có| E["Gọi resolveParameter"]
    E --> F["Truyền giá trị vào test"]
    D -->|Không có| G["ParameterResolutionException"]
    D -->|Nhiều resolver| H["Lỗi resolver cạnh tranh"]
~~~

Một tham số có thể được cung cấp bởi Spring, Mockito, JUnit hoặc một extension riêng. JUnit cần xác định được một resolver phù hợp cho mỗi tham số được extension phân giải.

## 2. SpringExtension cung cấp tham số Spring như thế nào?

SpringExtension kết nối JUnit Jupiter với Spring TestContext Framework. Ngoài việc quản lý ApplicationContext và các callback kiểm thử, extension này triển khai ParameterResolver để lấy dependency từ Spring.

Trong test method, Spring có thể cung cấp tham số được đánh dấu bằng các annotation phù hợp như:

- @Autowired: yêu cầu Spring inject dependency.
- @Qualifier: chỉ định bean phù hợp khi có nhiều bean cùng kiểu.
- @Value: lấy giá trị từ property hoặc biểu thức Spring.

Ví dụ:

~~~java
@SpringJUnitConfig(ReportConfiguration.class)
class ReportServiceTest {

    @Test
    void generatesReport(
            @Autowired ReportService reportService) {

        Report report = reportService.generate();

        assertNotNull(report);
    }
}
~~~

@SpringJUnitConfig kết hợp cấu hình test context với SpringExtension. Khi JUnit chuẩn bị gọi test method, SpringExtension nhận ra tham số @Autowired, yêu cầu Spring giải quyết dependency rồi truyền bean vào method.

Có thể dùng qualifier:

~~~java
@Test
void usesTheBusinessClock(
        @Autowired @Qualifier("businessClock") Clock clock) {

    assertNotNull(clock);
}
~~~

Nếu cần property, có thể dùng @Value:

~~~java
@Test
void receivesConfiguredCurrency(
        @Value("${app.currency}") String currency) {

    assertEquals("VND", currency);
}
~~~

Tham số không có annotation Spring phù hợp thường không được SpringExtension nhận là dependency. Điều này cho phép resolver khác cung cấp các tham số còn lại.

SpringExtension không biến mọi tham số của test method thành bean lookup. Việc đánh dấu tham số giúp xác định rõ tham số nào thuộc Spring.

## 3. Đăng ký SpringExtension cùng extension khác

Có thể kết hợp Spring với extension khác bằng @ExtendWith. Ví dụ, MockitoExtension hỗ trợ các tham số được đánh dấu @Mock.

~~~java
@SpringJUnitConfig(PricingConfiguration.class)
@ExtendWith(MockitoExtension.class)
class PricingTest {

    @Test
    void calculatesPrice(
            @Autowired TaxPolicy taxPolicy,
            @Mock DiscountGateway discountGateway,
            TestInfo testInfo) {

        when(discountGateway.discountFor("BOOK-1"))
            .thenReturn(BigDecimal.valueOf(10));

        PriceCalculator calculator =
            new PriceCalculator(taxPolicy, discountGateway);

        BigDecimal result = calculator.calculate("BOOK-1");

        assertEquals(BigDecimal.valueOf(90), result);
        assertTrue(testInfo.getDisplayName().contains("calculatesPrice"));
    }
}
~~~

Trong ví dụ này có ba nguồn tham số:

| Tham số | Nguồn cung cấp |
|---|---|
| taxPolicy | SpringExtension qua @Autowired |
| discountGateway | MockitoExtension qua @Mock |
| testInfo | JUnit Jupiter tích hợp sẵn |

Test lấy TaxPolicy thật từ Spring, nhận một mock DiscountGateway từ Mockito rồi tự tạo PriceCalculator để kiểm tra. Cách này phù hợp khi muốn kết hợp cấu hình Spring với một collaborator giả lập trong unit test.

Một lưu ý quan trọng: tham số @Mock do Mockito tạo chỉ là đối tượng mock được truyền vào test method. Nó không tự động thay thế một bean đang có trong ApplicationContext. Nếu PriceCalculator đã được Spring tạo sẵn và cần dùng mock thay thế một dependency bên trong context, hãy dùng cơ chế bean override phù hợp với phiên bản Spring đang dùng, chẳng hạn @MockitoBean ở các phiên bản Spring Framework hỗ trợ. Đừng giả định mock parameter sẽ tự được inject vào singleton bean.

@SpringJUnitConfig đã đăng ký SpringExtension thông qua meta-annotation. Vì vậy, không cần thêm @ExtendWith(SpringExtension.class) lần nữa khi đã dùng annotation kết hợp này.

Nếu dùng @ContextConfiguration thay cho @SpringJUnitConfig, hãy đăng ký SpringExtension rõ ràng:

~~~java
@ExtendWith({
    SpringExtension.class,
    MockitoExtension.class
})
@ContextConfiguration(classes = PricingConfiguration.class)
class PricingTest {
}
~~~

Các extension có thể cùng tham gia vào một test class. Điều quan trọng là từng resolver chỉ nhận những tham số thuộc trách nhiệm của nó.

## 4. Kết hợp tham số Spring với các resolver tích hợp của JUnit

JUnit Jupiter có các resolver tích hợp để cung cấp thông tin về lần chạy test. Các kiểu thường gặp gồm:

- TestInfo: thông tin về test hoặc container hiện tại.
- TestReporter: gửi dữ liệu báo cáo trong quá trình chạy test.
- RepetitionInfo: thông tin lần lặp trong @RepeatedTest.

Spring có thể inject bean vào cùng method mà JUnit cung cấp các tham số này:

~~~java
@SpringJUnitConfig(AuditConfiguration.class)
class AuditServiceTest {

    @Test
    void recordsAnEvent(
            @Autowired AuditService auditService,
            TestInfo testInfo,
            TestReporter reporter) {

        auditService.record("test-started");

        reporter.publishEntry(
            "test", testInfo.getDisplayName()
        );
    }
}
~~~

SpringExtension nhận tham số auditService vì nó có @Autowired. JUnit cung cấp TestInfo và TestReporter bằng resolver tích hợp của mình.

Với test lặp:

~~~java
@SpringJUnitConfig(CounterConfiguration.class)
class RepeatedCounterTest {

    @RepeatedTest(3)
    void incrementsCounter(
            @Autowired CounterService counterService,
            RepetitionInfo repetitionInfo) {

        assertTrue(repetitionInfo.getCurrentRepetition() >= 1);
        assertEquals(3, repetitionInfo.getTotalRepetitions());

        counterService.increment();
    }
}
~~~

RepetitionInfo chỉ có ý nghĩa trong ngữ cảnh repeated test. Không nên khai báo nó trong một @Test thông thường rồi mong JUnit cung cấp giá trị.

Một tham số do resolver tích hợp của JUnit cung cấp không cần @Autowired. Hãy giữ annotation Spring trên đúng những tham số cần lấy từ container.

## 5. Kết hợp Spring với @ParameterizedTest

@ParameterizedTest nhận dữ liệu từ một nguồn như @ValueSource, @CsvSource, @MethodSource hoặc @ArgumentsSource. Ngoài các đối số từ nguồn dữ liệu, JUnit cho phép các tham số ở cuối danh sách được cung cấp bởi ParameterResolver.

Quy tắc thực hành là đặt các tham số do nguồn dữ liệu cung cấp trước, sau đó đặt các tham số do extension phân giải ở cuối.

Ví dụ dùng @CsvSource cùng bean Spring:

~~~java
@SpringJUnitConfig(CalculatorConfiguration.class)
class CalculatorParameterizedTest {

    @ParameterizedTest
    @CsvSource({
        "2, 4",
        "3, 9",
        "5, 25"
    })
    void calculatesSquare(
            int input,
            int expected,
            @Autowired SquareService squareService) {

        assertEquals(expected, squareService.square(input));
    }
}
~~~

Hai tham số đầu input và expected đến từ từng dòng @CsvSource. Tham số cuối squareService được SpringExtension inject từ context.

Nếu đặt tham số @Autowired ở giữa các tham số nguồn, việc ánh xạ đối số của parameterized test có thể không đúng với quy tắc phân giải. Hãy giữ nhóm tham số nguồn ở đầu và nhóm tham số do resolver cung cấp ở cuối method parameter list.

Với @MethodSource, nguồn dữ liệu có thể trả về Stream<Arguments>:

~~~java
@SpringJUnitConfig(CalculatorConfiguration.class)
class CalculatorMethodSourceTest {

    static Stream<Arguments> squareCases() {
        return Stream.of(
            Arguments.of(2, 4),
            Arguments.of(4, 16),
            Arguments.of(6, 36)
        );
    }

    @ParameterizedTest
    @MethodSource("squareCases")
    void calculatesSquare(
            int input,
            int expected,
            @Autowired SquareService squareService) {

        assertEquals(expected, squareService.square(input));
    }
}
~~~

MethodSource chỉ cung cấp dữ liệu nghiệp vụ cho từng lần chạy. Bean Spring vẫn được cung cấp bởi SpringExtension.

Với @MethodSource trong trường hợp mặc định, factory method thường là static. Nếu test class dùng @TestInstance(TestInstance.Lifecycle.PER_CLASS), có thể dùng factory method instance theo quy tắc của JUnit. Việc thay đổi test instance lifecycle không làm thay đổi nguồn cung cấp bean Spring.

## 6. Kết hợp tham số constructor và tham số method

JUnit cũng có thể phân giải tham số constructor của test class. Spring TestContext hỗ trợ constructor injection cho test class theo chế độ được cấu hình.

Có thể yêu cầu Spring tự động inject tất cả tham số constructor bằng @TestConstructor:

~~~java
@SpringJUnitConfig(OrderConfiguration.class)
@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)
class OrderServiceSpringTest {

    private final OrderService orderService;

    OrderServiceSpringTest(OrderService orderService) {
        this.orderService = orderService;
    }

    @Test
    void createsOrder() {
        Order order = orderService.create("ORD-1");

        assertEquals("ORD-1", order.getNumber());
    }
}
~~~

@TestConstructor(autowireMode = ALL) yêu cầu Spring giải quyết toàn bộ tham số constructor của test class từ ApplicationContext. Có thể đặt chế độ mặc định cho test suite qua thuộc tính spring.test.constructor.autowire.mode nếu dự án cần chính sách thống nhất.

Nếu constructor autowiring không được bật, hãy dùng field injection hoặc method parameter injection theo cấu hình test. Không nên giả định Spring sẽ tự giải quyết mọi tham số constructor chỉ vì class có @SpringJUnitConfig.

Khi cần phối hợp nhiều resolver khác nhau, test method thường là nơi dễ phân chia trách nhiệm nhất: Spring nhận tham số có @Autowired, Mockito nhận tham số có @Mock, còn JUnit nhận các kiểu thông tin tích hợp. Với constructor ALL, Spring được yêu cầu xử lý tất cả tham số constructor, nên không phù hợp để trộn tùy ý tham số dành cho resolver khác vào cùng constructor.

## 7. Viết custom ParameterResolver

Một extension riêng có thể cung cấp đối tượng theo annotation do dự án định nghĩa. Ví dụ, nhiều test cần một tenant mặc định. Ta có thể tạo annotation @CurrentTenant và resolver tương ứng.

Annotation:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface CurrentTenant {
}
~~~

Kiểu dữ liệu:

~~~java
public record Tenant(String id) {
}
~~~

Resolver:

~~~java
import org.junit.jupiter.api.extension.ExtensionContext;
import org.junit.jupiter.api.extension.ParameterContext;
import org.junit.jupiter.api.extension.ParameterResolutionException;
import org.junit.jupiter.api.extension.ParameterResolver;

public class CurrentTenantResolver implements ParameterResolver {

    @Override
    public boolean supportsParameter(
            ParameterContext parameterContext,
            ExtensionContext extensionContext) {

        return parameterContext.isAnnotated(CurrentTenant.class)
            && parameterContext.getParameter().getType().equals(Tenant.class);
    }

    @Override
    public Object resolveParameter(
            ParameterContext parameterContext,
            ExtensionContext extensionContext) {

        return new Tenant("tenant-test");
    }
}
~~~

Đăng ký resolver cùng Spring:

~~~java
@SpringJUnitConfig(TenantConfiguration.class)
@ExtendWith(CurrentTenantResolver.class)
class TenantServiceTest {

    @Test
    void processesCurrentTenant(
            @CurrentTenant Tenant tenant,
            @Autowired TenantService tenantService) {

        assertEquals("tenant-test", tenant.id());
        assertTrue(tenantService.isEnabledFor(tenant));
    }
}
~~~

Resolver chỉ nhận tham số có cả annotation @CurrentTenant và kiểu Tenant. SpringExtension nhận tham số tenantService vì nó được đánh dấu @Autowired. Hai resolver có phạm vi rõ nên có thể cùng tồn tại.

### Thiết kế supportsParameter hẹp và có chủ đích

Một lỗi thường gặp là viết resolver chỉ kiểm tra kiểu:

~~~java
return parameterContext.getParameter().getType().equals(String.class);
~~~

Nếu Spring cũng có thể nhận một tham số String được đánh dấu @Value, hoặc resolver khác cũng cung cấp String, JUnit có thể phát hiện nhiều resolver cùng hỗ trợ một tham số.

Tốt hơn là kiểm tra cả annotation riêng và kiểu:

~~~java
return parameterContext.isAnnotated(CurrentTenant.class)
    && parameterContext.getParameter().getType().equals(Tenant.class);
~~~

supportsParameter nên chỉ quyết định resolver có phù hợp hay không. Không nên tạo tài nguyên, mở kết nối hoặc thay đổi trạng thái trong phương thức này vì JUnit có thể gọi nó nhiều lần trong quá trình chuẩn bị test.

resolveParameter mới thực hiện việc tạo hoặc lấy giá trị. Nếu không thể cung cấp tham số, hãy ném ParameterResolutionException với thông báo đủ rõ để người đọc biết annotation, kiểu hoặc điều kiện nào bị thiếu.

## 8. Điều gì xảy ra khi nhiều resolver cùng hỗ trợ một tham số?

JUnit Jupiter không dùng thứ tự đăng ký extension như một cơ chế ưu tiên resolver. Nếu nhiều ParameterResolver cùng trả về true cho một tham số, JUnit không tự chọn resolver đầu tiên. Test sẽ thất bại với lỗi ParameterResolutionException báo có nhiều resolver cạnh tranh.

Ví dụ resolver riêng nhận mọi String:

~~~java
@Override
public boolean supportsParameter(
        ParameterContext parameterContext,
        ExtensionContext extensionContext) {

    return parameterContext.getParameter().getType().equals(String.class);
}
~~~

Nếu test method có tham số:

~~~java
@Test
void readsCurrency(
        @Value("${app.currency}") String currency) {
}
~~~

SpringExtension có thể nhận tham số vì @Value yêu cầu Spring phân giải giá trị. Resolver riêng cũng nhận tham số vì nó nhận mọi String. Kết quả là hai resolver cùng cạnh tranh.

Cách xử lý:

- Thu hẹp supportsParameter bằng annotation riêng.
- Tránh dùng kiểu phổ biến như String, Integer hoặc Object làm điều kiện duy nhất.
- Xóa resolver bị đăng ký trùng hoặc bỏ annotation khiến resolver khác nhận cùng tham số.
- Chọn một nguồn duy nhất cho mỗi tham số.
- Nếu hai giá trị có cùng kiểu nhưng ý nghĩa khác nhau, dùng qualifier hoặc annotation riêng để phân biệt.

Ví dụ sửa resolver:

~~~java
return parameterContext.isAnnotated(CurrentTenant.class)
    && parameterContext.getParameter().getType().equals(String.class);
~~~

Khi đó, resolver chỉ nhận String có @CurrentTenant. Tuy nhiên, annotation riêng nên biểu đạt đúng ý nghĩa dữ liệu; nếu tham số là tenant, dùng kiểu Tenant thường rõ hơn String.

## 9. Phân biệt tham số do nguồn dữ liệu và tham số do resolver

Trong @ParameterizedTest, không phải mọi tham số đều do ParameterResolver cung cấp. JUnit có cơ chế riêng để lấy đối số từ ArgumentsProvider hoặc nguồn dữ liệu.

Ví dụ:

~~~java
@ParameterizedTest
@CsvSource({
    "VND, 100",
    "USD, 10"
})
void convertsAmount(
        String currency,
        int amount,
        @Autowired ExchangeService exchangeService,
        TestInfo testInfo) {

    // currency và amount đến từ CsvSource.
    // exchangeService đến từ Spring.
    // testInfo đến từ JUnit.
}
~~~

Có ba nhóm:

| Nhóm tham số | Nguồn | Ví dụ |
|---|---|---|
| Đối số theo từng lần chạy | @CsvSource, @MethodSource, @ValueSource | currency, amount |
| Tham số Spring | SpringExtension | @Autowired ExchangeService |
| Tham số extension khác | Mockito, JUnit hoặc custom resolver | @Mock, TestInfo, @CurrentTenant |

Nguồn dữ liệu của parameterized test cung cấp các đối số theo vị trí. Các tham số cần resolver nên được đặt sau nhóm đối số nguồn. Cách sắp xếp này giúp JUnit xác định rõ dữ liệu nào thuộc mỗi invocation và dữ liệu nào cần extension phân giải.

## 10. Kết hợp với @TempDir và các extension khác

JUnit có extension tích hợp hỗ trợ tham số như @TempDir để cung cấp thư mục tạm. Test có thể nhận đồng thời bean Spring, thư mục tạm và TestInfo:

~~~java
@SpringJUnitConfig(FileServiceConfiguration.class)
class FileServiceTest {

    @Test
    void writesReport(
            @Autowired FileReportService reportService,
            @TempDir Path temporaryDirectory,
            TestInfo testInfo) throws IOException {

        Path report = temporaryDirectory.resolve("report.txt");

        reportService.write(report, "test report");

        assertTrue(Files.exists(report));
        assertTrue(Files.size(report) > 0);
    }
}
~~~

Ở đây:

- FileReportService đến từ Spring.
- temporaryDirectory được JUnit cung cấp qua hỗ trợ @TempDir.
- TestInfo đến từ resolver tích hợp của JUnit.

Mỗi tham số có một nguồn rõ ràng. Test không cần tự khởi tạo thư mục tạm hoặc truy cập ApplicationContext bằng tay.

Các extension khác cũng có thể cung cấp tham số theo cách tương tự. Khi thêm extension vào test class, hãy xem annotation hoặc điều kiện mà extension dùng trong supportsParameter, rồi kiểm tra xem điều kiện đó có chồng lấn với Spring hay resolver hiện tại không.

## 11. Phân biệt Spring parameter injection với bean lookup thủ công

Một số test lấy bean trực tiếp qua ApplicationContext:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void getsServiceManually() {
    ReportService service =
        applicationContext.getBean(ReportService.class);

    assertNotNull(service);
}
~~~

Cách này hợp lệ, nhưng nếu test chỉ cần một dependency thì có thể inject thẳng vào tham số:

~~~java
@Test
void usesReportService(
        @Autowired ReportService reportService) {

    assertNotNull(reportService);
}
~~~

Parameter injection có một số lợi ích:

- Dependency được thể hiện ngay trong chữ ký method.
- Test method chỉ nhận các bean nó thực sự cần.
- Không cần giữ field injection cho những dependency chỉ dùng trong một method.
- Có thể kết hợp rõ ràng với tham số từ resolver khác.

Tuy nhiên, field injection vẫn hữu ích khi nhiều method trong cùng class dùng chung một bean. Hãy chọn cách thể hiện dependency dễ đọc nhất cho test class.

## 12. Chẩn đoán ParameterResolutionException

Khi JUnit không thể cung cấp tham số, thông báo thường chứa ParameterResolutionException. Hãy đọc thông báo để xác định tình huống.

### Không có resolver nào hỗ trợ tham số

Nguyên nhân thường gặp:

- Tham số không có annotation mà resolver yêu cầu.
- Extension chưa được đăng ký.
- Tham số có kiểu không được resolver hỗ trợ.
- Test đang dùng annotation Spring nhưng SpringExtension chưa được kích hoạt.

Ví dụ một tham số ReportService không có @Autowired trong test dùng Spring có thể không được SpringExtension nhận là dependency.

Cách sửa: đánh dấu tham số bằng annotation Spring phù hợp hoặc đăng ký resolver có trách nhiệm cung cấp nó.

### Có nhiều resolver cùng hỗ trợ tham số

Nguyên nhân thường gặp:

- Custom resolver nhận mọi tham số cùng kiểu.
- Hai extension cùng nhận một annotation hoặc kiểu.
- Một tham số mang nhiều annotation làm nhiều resolver cùng nhận.
- Extension bị đăng ký trùng qua cả meta-annotation và @ExtendWith.

Cách sửa: thu hẹp supportsParameter, bỏ đăng ký trùng và chỉ định rõ một nguồn cho tham số.

### Resolver hỗ trợ nhưng resolve thất bại

Nếu supportsParameter trả về true nhưng resolveParameter không thể tạo giá trị, kiểm tra điều kiện khởi tạo và dependency của resolver. Thông báo lỗi nên chỉ rõ kiểu tham số, annotation và nguyên nhân.

Không nên trả null để che giấu việc resolver không thể tạo giá trị, trừ khi null thực sự là một giá trị hợp lệ theo hợp đồng của tham số.

### Spring không tải được context

Đôi khi lỗi được nhìn thấy trong lúc phân giải tham số nhưng nguyên nhân nằm ở việc ApplicationContext không khởi tạo được. Khi đó, hãy tìm exception gốc liên quan đến bean creation, configuration hoặc datasource. Việc thay đổi ParameterResolver không sửa được một context tải thất bại.

## 13. Những lỗi thường gặp khi kết hợp resolver

- **Cho rằng resolver đầu tiên được ưu tiên:** JUnit báo lỗi nếu nhiều resolver cùng hỗ trợ một tham số.
- **Custom resolver nhận mọi String:** điều kiện quá rộng dễ xung đột với @Value hoặc resolver khác.
- **Quên đăng ký extension:** resolver riêng không được gọi nếu extension chưa được đăng ký bằng @ExtendWith hoặc cơ chế tương đương.
- **Đăng ký SpringExtension hai lần:** @SpringJUnitConfig đã bao gồm SpringExtension; không cần khai báo lại.
- **Đưa tham số Spring vào trước đối số @CsvSource:** hãy đặt đối số nguồn trước và tham số extension ở cuối method parameter list.
- **Nghĩ @Mock parameter thay thế bean Spring:** mock do Mockito tạo không tự động trở thành bean trong context.
- **Dùng @TestConstructor(ALL) rồi mong resolver khác xử lý một phần constructor:** chế độ này yêu cầu Spring giải quyết tất cả tham số constructor.
- **Dùng TestInfo ngoài ngữ cảnh JUnit hỗ trợ:** tham số phải được đặt trong lifecycle mà resolver tích hợp có thể cung cấp.
- **Thực hiện công việc trong supportsParameter:** phương thức này nên chỉ kiểm tra điều kiện, không tạo side effect.
- **Nuốt lỗi trong resolveParameter:** ném ParameterResolutionException với nguyên nhân rõ ràng để việc chẩn đoán dễ dàng.

## 14. Quy trình thiết kế test có nhiều nguồn tham số

Khi một test method cần tham số từ Spring và extension khác, hãy làm theo trình tự:

1. Liệt kê các giá trị test cần nhận và nguồn tạo ra từng giá trị.
2. Đánh dấu dependency Spring bằng @Autowired, @Qualifier hoặc @Value khi phù hợp.
3. Đánh dấu mock hoặc dữ liệu đặc biệt bằng annotation mà extension tương ứng hỗ trợ.
4. Đăng ký các extension cần thiết; dùng @SpringJUnitConfig nếu test cần Spring TestContext.
5. Đặt tham số do nguồn @ParameterizedTest cung cấp ở đầu danh sách.
6. Đặt tham số do ParameterResolver cung cấp ở cuối danh sách.
7. Kiểm tra supportsParameter của custom resolver để điều kiện đủ hẹp.
8. Chạy test và xử lý mọi ParameterResolutionException dựa trên resolver đang nhận tham số.
9. Nếu cần mock thay thế bean trong context, dùng cơ chế bean override phù hợp thay vì chỉ nhận một mock parameter.
10. Giữ mỗi test method chỉ nhận các tham số thực sự cần cho hành vi đang kiểm tra.

## Kết luận

SpringExtension cho phép Spring TestContext cung cấp bean vào tham số test method và constructor theo các quy tắc autowiring. JUnit Jupiter cũng có các ParameterResolver tích hợp, còn Mockito và extension riêng có thể cung cấp mock hoặc dữ liệu chuyên biệt. Những nguồn này có thể cùng xuất hiện trong một test class nếu mỗi tham số có một resolver chịu trách nhiệm rõ ràng.

Khi kết hợp với @ParameterizedTest, hãy đặt đối số từ nguồn dữ liệu trước và tham số do extension phân giải ở cuối. Với custom resolver, hãy giới hạn supportsParameter bằng annotation và kiểu cụ thể. Nếu nhiều resolver cùng nhận một tham số, JUnit sẽ báo lỗi cạnh tranh; hãy làm rõ nguồn cung cấp thay vì dựa vào thứ tự đăng ký extension.


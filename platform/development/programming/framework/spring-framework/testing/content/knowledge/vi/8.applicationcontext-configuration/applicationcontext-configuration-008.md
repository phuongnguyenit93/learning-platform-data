# ContextInitializer để chuẩn bị trước khi refresh

Spring tạo và cấu hình ApplicationContext theo nhiều giai đoạn. Trong giai đoạn chuẩn bị, context đã được tạo nhưng chưa refresh: bean chưa được khởi tạo hoàn chỉnh, các singleton chưa được tạo hàng loạt và ứng dụng chưa sẵn sàng phục vụ request. Đây là thời điểm thích hợp để thay đổi Environment, thêm property source, chọn profile hoặc đăng ký một số cấu hình cần có trước khi Spring xử lý bean definitions.

Spring cung cấp interface **ApplicationContextInitializer** cho mục đích này. Trong Spring TestContext Framework, một initializer có thể được khai báo qua thuộc tính initializers của @ContextConfiguration. Spring sẽ gọi initializer sau khi tạo context và trước khi refresh context.

Bài học này giải thích vị trí của ContextInitializer trong vòng đời ApplicationContext, cách triển khai và đăng ký initializer, những việc phù hợp để làm ở giai đoạn trước refresh, cách kiểm thử và những lỗi thường gặp khi sử dụng.

## 1. ApplicationContext có giai đoạn chuẩn bị trước khi refresh

ApplicationContext không xuất hiện ngay ở trạng thái sẵn sàng. Spring cần tạo context, thiết lập Environment, nạp cấu hình và bean definitions, rồi refresh để hoàn tất việc khởi tạo container.

Có thể mô tả luồng khái quát như sau:

~~~text
Tạo ApplicationContext
        |
        v
Chuẩn bị context
- Gắn parent context nếu có
- Chuẩn bị Environment và property sources
- Thiết lập cấu hình theo context loader
        |
        v
ApplicationContextInitializer.initialize(context)
        |
        v
Nạp hoặc hoàn thiện bean definitions
        |
        v
ApplicationContext.refresh()
- Đăng ký và chạy BeanFactoryPostProcessor
- Đăng ký BeanPostProcessor
- Khởi tạo các singleton eager
- Hoàn tất các cơ chế quản lý context
        |
        v
Context sẵn sàng sử dụng
~~~

Chi tiết các bước có thể khác nhau theo cách khởi tạo context, ContextLoader hoặc Spring Boot. Điểm quan trọng của hợp đồng initializer là nó được gọi khi context đã tồn tại và còn trước lần refresh tương ứng.

Trước refresh, initializer có thể chuẩn bị những thông tin mà Spring cần khi đọc bean definitions hoặc tạo bean, ví dụ:

- Thêm property source vào Environment.
- Bổ sung hoặc điều chỉnh active profiles.
- Đặt một số thông tin cấu hình cho context.
- Đăng ký bean definitions hoặc singleton phục vụ môi trường đặc biệt, nếu loại context hỗ trợ.
- Thiết lập parent context hoặc những tùy chỉnh container phù hợp với loại context đang dùng.

Sau khi refresh, nhiều quyết định đã được thực hiện: cấu hình điều kiện đã được đánh giá, bean definitions đã được xử lý và singleton eager có thể đã được tạo. Thay đổi Environment ở thời điểm đó thường không làm các bean đã khởi tạo tự động đọc lại cấu hình. Vì vậy, nếu một property phải ảnh hưởng đến quá trình bind hoặc điều kiện đăng ký bean, cần cung cấp nó trước refresh.

## 2. ApplicationContextInitializer là gì?

Interface ApplicationContextInitializer có một phương thức initialize nhận context cần chuẩn bị:

~~~java
public interface ApplicationContextInitializer<
        C extends ConfigurableApplicationContext> {

    void initialize(C applicationContext);
}
~~~

Tham số kiểu C cho phép initializer giới hạn loại context mà nó hỗ trợ. Ví dụ, initializer có thể nhận ConfigurableApplicationContext nói chung, hoặc chỉ nhận một loại context cụ thể khi cấu hình cần các API đặc thù.

Một initializer thường là một class độc lập:

~~~java
public class TestEnvironmentInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        // Chuẩn bị context trước refresh.
    }
}
~~~

Spring tạo và gọi initializer trong quá trình chuẩn bị context. Đây không phải một bean thông thường được lấy từ ApplicationContext đang được khởi tạo, vì context đó chưa refresh và chưa sẵn sàng cung cấp các bean theo cách thông thường.

Do đó, hãy thiết kế initializer như một thành phần cấu hình độc lập:

- Có thể được tạo bằng constructor mặc định khi dùng cơ chế khai báo initializer theo class.
- Không phụ thuộc vào việc @Autowired các bean từ chính context đang chuẩn bị.
- Nhận context qua tham số initialize.
- Nên tránh giữ state mutable dùng chung giữa nhiều lần khởi tạo.
- Chỉ thực hiện công việc chuẩn bị cần thiết, có thể lặp lại và dễ kiểm soát.

Nếu initializer cần dữ liệu đầu vào, hãy đưa dữ liệu đó qua property, constructor được hỗ trợ bởi cơ chế khởi tạo riêng, hoặc một đối tượng cấu hình độc lập. Với initializer khai báo bằng class trong @ContextConfiguration, cách đơn giản và dễ tương thích nhất thường là class không cần dependency injection.

## 3. Ví dụ: thêm property source trước khi refresh

Giả sử ứng dụng có cấu hình vận chuyển:

~~~yaml
app:
  shipping:
    free-shipping-threshold: 500000
    currency: VND
~~~

Ứng dụng bind cấu hình vào một record:

~~~java
@ConfigurationProperties(prefix = "app.shipping")
public record ShippingProperties(
        BigDecimal freeShippingThreshold,
        String currency
) {
}
~~~

Một configuration đăng ký properties:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ShippingProperties.class)
public class ShippingConfiguration {
}
~~~

Trong một số test hoặc môi trường đặc biệt, ta muốn bổ sung property trước khi Spring tạo ShippingProperties. Có thể dùng MapPropertySource:

~~~java
public class ShippingTestInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        Map<String, Object> values = Map.of(
                "app.shipping.free-shipping-threshold", "750000",
                "app.shipping.currency", "VND"
        );

        var propertySource =
                new MapPropertySource("shippingTestOverrides", values);

        context.getEnvironment()
                .getPropertySources()
                .addFirst(propertySource);
    }
}
~~~

Giải thích:

- ConfigurableApplicationContext cung cấp Environment có thể cấu hình.
- MapPropertySource đóng gói các cặp tên property và giá trị.
- addFirst đặt property source ở vị trí ưu tiên cao trong danh sách.
- Khi Spring đọc property, các giá trị trong shippingTestOverrides được ưu tiên trước những property source nằm sau nó.

Dùng addFirst có chủ đích: nó có thể ghi đè giá trị từ application.yml hoặc các nguồn cấu hình có thứ tự thấp hơn. Nếu muốn property mới có độ ưu tiên thấp hơn một số nguồn hiện có, hãy chọn addLast hoặc addBefore/addAfter theo tên property source phù hợp.

Có thể kiểm tra initializer bằng Spring TestContext:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = ShippingConfiguration.class,
        initializers = ShippingTestInitializer.class
)
class ShippingConfigurationTest {

    @Autowired
    private ShippingProperties properties;

    @Test
    void shouldUsePropertiesAddedBeforeRefresh() {
        assertEquals(
                new BigDecimal("750000"),
                properties.freeShippingThreshold()
        );
        assertEquals("VND", properties.currency());
    }
}
~~~

Test này không tự tạo ShippingProperties. Spring tạo context, gọi initializer, nạp configuration và bind properties trong quá trình khởi tạo bean. Assertion xác minh giá trị thực tế được inject vào test.

Nếu bỏ initializer nhưng vẫn giữ cấu hình gốc, test sẽ nhận giá trị từ nguồn cấu hình khác hoặc thất bại nếu property bắt buộc không có. Sự khác biệt nằm ở thời điểm và nguồn property được đưa vào Environment.

## 4. Thiết lập active profile trước refresh

Profile có thể quyết định configuration class hoặc bean nào được đăng ký. Nếu initializer cần bổ sung profile cho context, có thể thao tác trên ConfigurableEnvironment.

~~~java
public class TestProfileInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        context.getEnvironment().addActiveProfile("integration-test");
    }
}
~~~

Sau khi profile được thêm, các cấu hình như sau có thể được áp dụng khi Spring xử lý context:

~~~java
@Configuration
@Profile("integration-test")
class IntegrationTestConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

Trong test:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = IntegrationTestConfiguration.class,
        initializers = TestProfileInitializer.class
)
class PaymentConfigurationTest {

    @Autowired
    private PaymentGateway paymentGateway;

    @Test
    void shouldLoadTestPaymentGateway() {
        assertThat(paymentGateway)
                .isInstanceOf(FakePaymentGateway.class);
    }
}
~~~

Có hai thao tác dễ nhầm:

- addActiveProfile thêm một profile vào tập active profiles hiện tại.
- setActiveProfiles đặt lại danh sách active profiles theo các giá trị truyền vào.

Nếu context đã có profile do môi trường hoặc cấu hình khác thiết lập, setActiveProfiles có thể thay thế danh sách đó. Hãy chọn phương thức theo ý định: bổ sung profile hay thay toàn bộ profile.

Không nên dùng initializer để bật profile production trong test nếu điều đó có thể làm test kết nối đến database, cổng thanh toán hoặc dịch vụ thật. Hãy dùng profile dành riêng cho test và kiểm soát rõ các dependency bên ngoài.

## 5. Đăng ký initializer trong Spring TestContext Framework

Với JUnit Jupiter, initializer có thể được khai báo trong @ContextConfiguration:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = TestApplicationConfiguration.class,
        initializers = TestEnvironmentInitializer.class
)
class ApplicationContextTest {
}
~~~

Spring TestContext Framework sử dụng initializer trong lúc tạo context cho test class. Cấu hình trên có ba thành phần:

- @ExtendWith(SpringExtension.class) kết nối JUnit Jupiter với Spring TestContext.
- classes chỉ định cấu hình dùng để tạo context.
- initializers chỉ định các class cần được gọi trước refresh.

Có thể viết ngắn hơn bằng @SpringJUnitConfig nếu muốn kết hợp SpringExtension và @ContextConfiguration:

~~~java
@SpringJUnitConfig(
        classes = TestApplicationConfiguration.class,
        initializers = TestEnvironmentInitializer.class
)
class ApplicationContextTest {
}
~~~

Trong trường hợp sử dụng annotation kết hợp hoặc cấu hình @ContextConfiguration lặp, cần bảo đảm các metadata được hợp nhất theo đúng cấu hình mong muốn. Cách khai báo tường minh trong một @ContextConfiguration thường dễ đọc nhất khi chỉ có một nhóm cấu hình.

### Nhiều initializer

Một test có thể cần nhiều initializer, ví dụ một initializer thêm property và một initializer thiết lập một cấu hình context khác:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(
        classes = TestApplicationConfiguration.class,
        initializers = {
                TestEnvironmentInitializer.class,
                TestProfileInitializer.class
        }
)
class ApplicationContextTest {
}
~~~

Khi thứ tự có ý nghĩa, hãy khai báo và sắp xếp initializer một cách rõ ràng. Spring TestContext hỗ trợ thứ tự thông qua cơ chế ordering của initializer, chẳng hạn Ordered hoặc @Order trong những trường hợp tương ứng. Đừng để initializer sau âm thầm ghi đè kết quả mà initializer trước đã chuẩn bị.

Ví dụ, nếu initializer A thêm property source và initializer B đọc property đó để quyết định cấu hình, B phải chạy sau A. Nếu cả hai cùng sửa active profiles hoặc cùng thay đổi property source, hãy xác định rõ quy tắc ưu tiên.

Một initializer nên thay đổi một nhóm cấu hình có trách nhiệm rõ ràng. Nếu có nhiều initializer phụ thuộc lẫn nhau, cân nhắc gộp phần chuẩn bị liên quan vào một initializer để giảm độ phức tạp thứ tự.

## 6. Dùng initializer với Spring Boot

Spring Boot dựa trên Spring ApplicationContext nên cũng hỗ trợ ApplicationContextInitializer.

Có thể đăng ký initializer trực tiếp với SpringApplication:

~~~java
public class Application {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addInitializers(
                new TestEnvironmentInitializer()
        );

        application.run(args);
    }
}
~~~

Hoặc với SpringApplicationBuilder:

~~~java
new SpringApplicationBuilder(Application.class)
        .initializers(new TestEnvironmentInitializer())
        .run(args);
~~~

Trong ứng dụng thực tế, initializer thường được đăng ký bằng cơ chế cấu hình phù hợp của môi trường chạy. Ví dụ trên chỉ minh họa API đăng ký, không có nghĩa ứng dụng production nên luôn dùng initializer mang tên TestEnvironmentInitializer.

Trong Spring Boot test, có thể khai báo initializer qua @ContextConfiguration cùng @SpringBootTest khi cần kết hợp với cấu hình Boot:

~~~java
@SpringBootTest
@ContextConfiguration(initializers = ShippingTestInitializer.class)
class ShippingApplicationTest {

    @Autowired
    private ShippingProperties properties;

    @Test
    void shouldReadInitializerProperties() {
        assertEquals(
                new BigDecimal("750000"),
                properties.freeShippingThreshold()
        );
    }
}
~~~

@SpringBootTest tạo context theo cơ chế của Spring Boot. @ContextConfiguration bổ sung initializer để chuẩn bị context trước refresh.

Cần tránh đăng ký cùng một initializer nhiều lần qua các cơ chế khác nhau nếu không có chủ đích. Việc chạy lặp initializer có thể gây trùng bean definition, thêm property source nhiều lần hoặc tạo side effect khó hiểu.

## 7. Đăng ký bean definition từ initializer

Initializer không chỉ có thể thay đổi Environment. Với loại context hỗ trợ, nó còn có thể đăng ký cấu hình hoặc bean definitions trước refresh.

Ví dụ, nếu context cụ thể là GenericApplicationContext, có thể đăng ký một bean test:

~~~java
public class FixedClockInitializer
        implements ApplicationContextInitializer<GenericApplicationContext> {

    @Override
    public void initialize(GenericApplicationContext context) {
        Clock fixedClock = Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );

        context.registerBean(
                Clock.class,
                () -> fixedClock
        );
    }
}
~~~

Sau khi refresh, bean Clock có thể được inject vào service:

~~~java
@Service
public class ExpirationService {

    private final Clock clock;

    public ExpirationService(Clock clock) {
        this.clock = clock;
    }

    public Instant expiresAt(Duration duration) {
        return clock.instant().plus(duration);
    }
}
~~~

Trong test:

~~~java
@SpringBootTest
@ContextConfiguration(initializers = FixedClockInitializer.class)
class ExpirationServiceTest {

    @Autowired
    private ExpirationService expirationService;

    @Test
    void shouldUseFixedClock() {
        assertEquals(
                Instant.parse("2026-01-01T01:00:00Z"),
                expirationService.expiresAt(Duration.ofHours(1))
        );
    }
}
~~~

Ví dụ này cần loại context hỗ trợ GenericApplicationContext và chỉ nên dùng khi cấu hình test thực sự cần đăng ký bean theo cách đó. Với một bean đơn giản, @TestConfiguration và @Bean thường rõ ràng hơn:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class FixedClockTestConfiguration {

    @Bean
    Clock fixedClock() {
        return Clock.fixed(
                Instant.parse("2026-01-01T00:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Có thể import test configuration bằng @Import hoặc khai báo trong cấu hình test. Đây thường là cách dễ đọc hơn nếu mục tiêu chỉ là thay một dependency trong test.

Khi đăng ký bean bằng API của GenericApplicationContext, initializer phải nhận đúng loại context. Không nên giả định mọi ConfigurableApplicationContext đều có phương thức registerBean như GenericApplicationContext. Nếu initializer cần hoạt động với nhiều loại context, hãy dùng API chung phù hợp hoặc tách cấu hình theo loại context.

## 8. ContextInitializer khác các extension point khác của Spring như thế nào?

Spring có nhiều điểm mở rộng trong vòng đời container. Chúng có thời điểm và mục đích khác nhau.

| Cơ chế | Thời điểm chính | Dùng để làm gì? |
|---|---|---|
| ApplicationContextInitializer | Sau khi tạo context, trước refresh | Chuẩn bị Environment và context |
| BeanDefinitionRegistryPostProcessor | Trong refresh, ở giai đoạn xử lý bean definitions | Đăng ký hoặc thay đổi bean definitions |
| BeanFactoryPostProcessor | Trong refresh, sau khi bean definitions được nạp và trước khi khởi tạo singleton thông thường | Điều chỉnh metadata của bean factory |
| BeanPostProcessor | Trong quá trình tạo từng bean | Tùy chỉnh bean trước/sau initialization |
| ApplicationRunner / CommandLineRunner | Sau khi Spring Boot hoàn tất khởi tạo context | Chạy công việc sau khi ứng dụng khởi động |

### Khi nào chọn ApplicationContextInitializer?

Chọn initializer khi cần chuẩn bị context trước refresh, đặc biệt khi thay đổi phải có hiệu lực trước khi Spring xử lý cấu hình hoặc tạo bean.

Ví dụ:

- Bổ sung property source.
- Thêm active profile.
- Chuẩn bị Environment cho configuration properties.
- Đặt cấu hình ban đầu cho context.
- Đăng ký một số bean definitions trong context phù hợp.

### Khi nào chọn BeanFactoryPostProcessor?

Nếu cần đọc hoặc thay đổi bean definitions sau khi chúng đã được nạp, BeanFactoryPostProcessor hoặc BeanDefinitionRegistryPostProcessor thường phù hợp hơn.

Ví dụ, một thư viện cần kiểm tra metadata của bean definitions hoặc đăng ký definition dựa trên những definition đã có. Đây là trách nhiệm ở giai đoạn bean factory, không phải chuẩn bị Environment ban đầu.

### Khi nào chọn BeanPostProcessor?

Nếu cần can thiệp vào object trong lúc Spring tạo bean, chẳng hạn bọc proxy hoặc tùy chỉnh bean trước/sau initialization, BeanPostProcessor là điểm mở rộng phù hợp.

### Khi nào chọn ApplicationRunner?

Nếu công việc cần chạy sau khi ứng dụng đã khởi động và các bean đã sẵn sàng, ApplicationRunner hoặc CommandLineRunner phù hợp hơn. Không nên dùng runner để thêm property cần thiết cho quá trình bind bean, vì thời điểm đó đã quá muộn.

## 9. ContextInitializer và các cách cung cấp property trong test

Initializer không phải cách duy nhất để đưa property vào context. Hãy chọn công cụ theo loại dữ liệu và độ phức tạp.

| Cách cấu hình | Phù hợp khi | Đặc điểm |
|---|---|---|
| application.yml / application.properties | Cấu hình mặc định của ứng dụng | Nguồn cấu hình tiêu chuẩn |
| @TestPropertySource | Test cần một tập property cố định | Khai báo trực tiếp hoặc dùng file property |
| @SpringBootTest(properties = ...) | Test Boot cần vài giá trị override đơn giản | Gọn và dễ đọc ngay tại test |
| @DynamicPropertySource | Property có giá trị được xác định động, ví dụ URL container | Đăng ký supplier cho giá trị runtime |
| ApplicationContextInitializer | Cần chuẩn bị Environment/context qua một bước có logic hoặc nhiều thao tác | Linh hoạt nhưng cần quản lý lifecycle và thứ tự |

### @TestPropertySource cho property cố định

~~~java
@SpringJUnitConfig(TestApplicationConfiguration.class)
@TestPropertySource(properties = {
        "app.shipping.free-shipping-threshold=750000",
        "app.shipping.currency=VND"
})
class ShippingPropertiesTest {
}
~~~

Nếu chỉ cần override một vài property cố định, cách này thường dễ đọc hơn việc tạo một initializer riêng.

### @DynamicPropertySource cho giá trị runtime

Khi test dùng Testcontainers, URL và thông tin kết nối chỉ có sau khi container khởi chạy. @DynamicPropertySource cho phép đăng ký supplier:

~~~java
@Testcontainers
@SpringBootTest
class DatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Đây là lựa chọn chuyên biệt, thuận tiện cho property được cung cấp bởi tài nguyên test. Nếu chỉ cần đưa các giá trị này vào Environment, không nhất thiết phải tự viết initializer.

### Khi nào initializer có lợi thế?

Initializer phù hợp khi cần một bước chuẩn bị tổng hợp, ví dụ:

- Bổ sung property source và active profile theo cùng một quy tắc.
- Tích hợp một framework kiểm thử cần cấu hình context trước refresh.
- Đăng ký bean hoặc context metadata dựa trên thông tin runtime mà annotation tĩnh khó biểu đạt.
- Dùng chung một quy trình chuẩn bị cho nhiều test class hoặc nhiều context.

Nếu logic chỉ là khai báo một property, hãy cân nhắc @TestPropertySource hoặc thuộc tính properties của @SpringBootTest trước.

## 10. Kiểm thử chính initializer

Có thể chia việc kiểm thử thành hai lớp:

1. Kiểm tra logic thuần của initializer nếu có quy tắc tính toán hoặc chọn property.
2. Kiểm tra tác động thực tế lên ApplicationContext trước refresh.

Đối với tác động lên context, ApplicationContextRunner rất phù hợp vì cho phép đăng ký initializer rồi quan sát context sau khi runner hoàn tất refresh.

Ví dụ:

~~~java
class ShippingInitializerTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withInitializer(new ShippingTestInitializer())
                    .withUserConfiguration(ShippingConfiguration.class);

    @Test
    void shouldExposeShippingOverridesToTheContext() {
        contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(ShippingProperties.class);

            var properties = context.getBean(ShippingProperties.class);

            assertEquals(
                    new BigDecimal("750000"),
                    properties.freeShippingThreshold()
            );
        });
    }
}
~~~

ApplicationContextRunner gọi initializer trong quá trình tạo context, sau đó refresh và cung cấp context đã sẵn sàng cho callback test. Vì vậy, assertion đọc được bean đã được tạo bằng property do initializer bổ sung.

Có thể kiểm tra cả trường hợp profile hoặc property source được thiết lập:

~~~java
@Test
void shouldActivateIntegrationProfile() {
    new ApplicationContextRunner()
            .withInitializer(new TestProfileInitializer())
            .withUserConfiguration(IntegrationTestConfiguration.class)
            .run(context -> {
                assertThat(context.getEnvironment().getActiveProfiles())
                        .contains("integration-test");
                assertThat(context)
                        .hasSingleBean(PaymentGateway.class);
            });
}
~~~

Trong ví dụ thực tế, có thể kiểm tra active profiles trực tiếp từ Environment và xác minh loại bean cụ thể được đăng ký. Assertion nên phản ánh hợp đồng cấu hình của initializer.

Nếu initializer chỉ thêm property source, không cần kiểm tra mọi chi tiết nội bộ của MapPropertySource. Hãy kiểm tra giá trị mà Spring thực sự sử dụng.

## 11. Những lỗi thường gặp khi dùng ContextInitializer

### 11.1. Thay đổi Environment sau refresh

Một lỗi phổ biến là cố thêm property sau khi context đã refresh:

~~~java
context.refresh();

// Thay đổi property sau khi bean đã được tạo.
context.getEnvironment()
        .getPropertySources()
        .addFirst(propertySource);
~~~

Nếu bean đã bind properties hoặc điều kiện cấu hình đã được đánh giá, việc thêm property sau đó không tự động tạo lại bean hay đánh giá lại toàn bộ configuration.

Hãy thêm property trong initializer hoặc một cơ chế cấu hình được thực hiện trước refresh.

### 11.2. Nhầm initializer với bean được inject

Initializer được tạo trước khi context hoàn chỉnh. Không nên kỳ vọng có thể @Autowired một service từ chính context đang được chuẩn bị.

Nếu initializer cần một giá trị, hãy lấy từ Environment, tham số cấu hình hoặc một nguồn độc lập được phép sử dụng. Nếu công việc cần một bean đã được khởi tạo, đó có thể là công việc của một extension point muộn hơn.

### 11.3. Dùng sai loại context

Một initializer nhận GenericApplicationContext chỉ có thể làm việc với context tương thích. Nếu được dùng với loại context khác, có thể xảy ra lỗi ép kiểu hoặc không thể gọi API đặc thù.

Nếu chỉ cần thay đổi Environment, nhận ConfigurableApplicationContext thường linh hoạt hơn.

### 11.4. Property source có độ ưu tiên không như mong đợi

addFirst và addLast tạo vị trí ưu tiên khác nhau. Nếu property vẫn nhận giá trị cũ, hãy kiểm tra thứ tự property sources và nguồn nào đang cung cấp giá trị cuối cùng.

Không nên thêm nhiều property source cùng tên hoặc lặp initializer mà không kiểm soát.

### 11.5. Ghi đè active profiles ngoài ý muốn

setActiveProfiles thay danh sách profile hiện tại. Nếu mục tiêu chỉ là bổ sung profile, dùng addActiveProfile.

Hãy kiểm tra tập profile cuối cùng khi test có nhiều nguồn cấu hình.

### 11.6. Khởi tạo side effect khó lặp lại

Initializer có thể chạy khi Spring tạo context. Nếu nó gọi API thật, tạo dữ liệu production, mở tài nguyên không được đóng hoặc sửa file dùng chung, test sẽ khó ổn định.

Nên giữ initializer nhẹ, xác định rõ tài nguyên và có thể chạy lặp lại. Các thao tác có side effect lớn cần cơ chế lifecycle và cleanup phù hợp.

### 11.7. Dùng initializer cho việc vốn thuộc cơ chế khác

Nếu chỉ cần mock một bean, @TestConfiguration, @Import hoặc cơ chế mock bean của Spring Boot có thể rõ ràng hơn. Nếu cần chạy một tác vụ sau khi ứng dụng khởi động, dùng ApplicationRunner. Nếu cần sửa bean definitions sau khi nạp, xem xét BeanFactoryPostProcessor hoặc BeanDefinitionRegistryPostProcessor.

Chọn extension point theo thời điểm cần tác động.

## 12. Thứ tự của nhiều initializer và tính độc lập

Khi có nhiều initializer, hãy xác định rõ initializer nào cung cấp dữ liệu và initializer nào tiêu thụ dữ liệu đó.

Ví dụ:

~~~text
EnvironmentInitializer
    |
    +-- Thêm property source
    +-- Bổ sung active profile
            |
            v
ConditionalConfigurationInitializer
    |
    +-- Đọc giá trị đã chuẩn bị
    +-- Chuẩn bị cấu hình phụ thuộc
            |
            v
ApplicationContext.refresh()
~~~

Nếu thứ tự initializer không được xác định rõ, test có thể hoạt động khác nhau khi cấu hình thay đổi hoặc khi initializer được dùng ở context khác.

Một số nguyên tắc:

- Mỗi initializer nên có trách nhiệm hẹp.
- Tránh phụ thuộc vào side effect ngầm của initializer khác.
- Dùng ordering khi thứ tự là một phần của thiết kế.
- Không dùng static mutable state để truyền dữ liệu giữa các lần khởi tạo.
- Không giữ tham chiếu đến context sau khi initializer hoàn tất nếu không cần thiết.
- Nếu hai bước luôn phải chạy cùng nhau, cân nhắc gộp chúng để làm rõ hợp đồng.

Initializer cần an toàn khi được áp dụng cho các context phù hợp và không nên giả định nó chỉ chạy một lần duy nhất trong toàn bộ tiến trình. Spring có thể tạo nhiều context cho các test class hoặc cấu hình khác nhau.

## 13. Quy trình chọn và triển khai initializer

Khi cần chuẩn bị một ApplicationContext, có thể đi theo các bước sau:

1. Xác định chính xác dữ liệu hoặc cấu hình phải tồn tại trước refresh.
2. Kiểm tra liệu @TestPropertySource, @SpringBootTest(properties), @DynamicPropertySource hoặc @TestConfiguration đã giải quyết được nhu cầu chưa.
3. Nếu cần logic chuẩn bị tổng hợp, tạo class triển khai ApplicationContextInitializer với kiểu context phù hợp.
4. Thay đổi Environment hoặc context qua API được hỗ trợ trước refresh.
5. Đăng ký initializer bằng @ContextConfiguration hoặc cơ chế Spring Boot tương ứng.
6. Nếu có nhiều initializer, xác định thứ tự và tránh ghi đè ngoài ý muốn.
7. Viết context test để xác minh giá trị, profile hoặc bean sau khi context đã refresh.
8. Đảm bảo initializer không để lại side effect ngoài phạm vi test và có thể chạy lặp lại.

Ví dụ, nếu mục tiêu chỉ là đổi một property cố định, không cần tạo initializer. Nếu mục tiêu là tích hợp nhiều bước chuẩn bị mà các annotation tĩnh không thể biểu đạt rõ, initializer là một extension point phù hợp.

## 14. Kết luận

ApplicationContextInitializer là điểm mở rộng để chuẩn bị một ConfigurableApplicationContext sau khi context được tạo và trước khi refresh. Nó cho phép bổ sung property source, active profile và một số cấu hình hoặc bean definitions cần thiết trước khi Spring xử lý và khởi tạo bean.

Hãy nhớ các điểm chính:

- Initializer chạy trước refresh; thay đổi phải có hiệu lực trước khi bean được tạo hoặc điều kiện cấu hình được đánh giá.
- Trong Spring TestContext, đăng ký initializer qua thuộc tính initializers của @ContextConfiguration.
- Với Spring Boot, có thể đăng ký qua SpringApplication hoặc kết hợp @SpringBootTest với @ContextConfiguration.
- Initializer không phải bean thông thường của chính context đang được chuẩn bị, vì vậy không dựa vào dependency injection từ context đó.
- addFirst, addLast, addActiveProfile và setActiveProfiles có ý nghĩa khác nhau; cần hiểu thứ tự ưu tiên và tác động lên cấu hình hiện có.
- Dùng ApplicationContextRunner hoặc context test để xác minh kết quả sau refresh.
- Chọn initializer khi thực sự cần logic chuẩn bị trước refresh; dùng các annotation property hoặc test configuration đơn giản hơn khi chúng đã đủ.

Khi đặt thao tác cấu hình đúng vào giai đoạn trước refresh, Spring sẽ đọc được Environment và metadata cần thiết ngay từ lúc xây dựng container. Điều đó giúp test tái hiện cấu hình một cách có kiểm soát và phát hiện lỗi khởi tạo sớm hơn.


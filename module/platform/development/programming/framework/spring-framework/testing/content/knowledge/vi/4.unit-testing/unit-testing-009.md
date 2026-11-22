# Khi kiểm thử đơn vị không đủ để xác nhận cấu hình Spring

Kiểm thử đơn vị giúp xác minh logic của một lớp trong điều kiện được kiểm soát. Tuy nhiên, một ứng dụng Spring không chỉ gồm các đối tượng Java được gọi trực tiếp. Spring còn tạo đối tượng, tìm bean, inject dependency, đọc cấu hình, chọn profile, áp dụng điều kiện đăng ký bean và tạo proxy để cung cấp các hành vi như transaction, cache, security hoặc xử lý bất đồng bộ.

Khi một bài test tự khởi tạo lớp bằng constructor và thay dependency bằng mock, bài test đó có thể chứng minh logic của lớp hoạt động đúng, nhưng không chứng minh Spring có thể lắp ráp và vận hành lớp đó theo cấu hình của ứng dụng. Đây là ranh giới quan trọng giữa **unit test thuần Java** và **kiểm thử có Spring ApplicationContext**.

Bài học này giải thích khi nào unit test không đủ, những lỗi cấu hình mà unit test không thể phát hiện, cách chọn phạm vi kiểm thử Spring phù hợp và cách giữ bộ test nhanh mà vẫn có bằng chứng đáng tin cậy về cấu hình ứng dụng.

## 1. Một lớp chạy đúng chưa có nghĩa ứng dụng Spring được cấu hình đúng

Giả sử ứng dụng có service tính phí:

~~~java
@Service
public class ShippingService {

    private final ShippingPolicy policy;
    private final ShippingProperties properties;

    public ShippingService(
            ShippingPolicy policy,
            ShippingProperties properties
    ) {
        this.policy = policy;
        this.properties = properties;
    }

    public BigDecimal calculate(Order order) {
        if (order.total().compareTo(properties.freeShippingThreshold()) >= 0) {
            return BigDecimal.ZERO;
        }

        return policy.calculate(order);
    }
}
~~~

Một unit test có thể tạo service trực tiếp:

~~~java
class ShippingServiceTest {

    private final ShippingPolicy policy = mock(ShippingPolicy.class);

    private final ShippingProperties properties =
            new ShippingProperties(new BigDecimal("500000"));

    private final ShippingService shippingService =
            new ShippingService(policy, properties);

    @Test
    void shouldUseFreeShippingAboveThreshold() {
        var order = new Order(new BigDecimal("600000"));

        var fee = shippingService.calculate(order);

        assertEquals(BigDecimal.ZERO, fee);
        verifyNoInteractions(policy);
    }
}
~~~

Bài test trên có thể xác minh quy tắc miễn phí vận chuyển. Nhưng nó không đi qua cơ chế khởi tạo của Spring. Nó không cho biết:

- Spring có quét và đăng ký được ShippingService hay không.
- Spring có tìm thấy đúng ShippingPolicy để inject hay không.
- Có nhiều bean cùng kiểu khiến ứng dụng không khởi động được hay không.
- ShippingProperties có được bind từ application.yml hay không.
- Giá trị cấu hình có được chuyển đổi đúng kiểu hay không.
- Bean có được đăng ký trong profile đang chạy hay không.
- Một cấu hình có điều kiện có vô tình bỏ qua bean cần thiết hay không.
- Service có được bọc bằng proxy để áp dụng transaction, cache hoặc security hay không.

Lý do rất đơn giản: unit test đã tự cung cấp mọi thứ mà service cần. Khi test tạo object bằng constructor, nó bỏ qua quá trình Spring tạo và quản lý object.

Vì vậy, một unit test xanh chỉ là bằng chứng cho hành vi của đơn vị trong môi trường test đã thiết lập. Nó không tự động chứng minh cấu hình ứng dụng đúng.

## 2. Những phần cấu hình Spring mà unit test thuần Java không kiểm tra

### 2.1. Component scan và đăng ký bean

Spring Boot thường tìm các component từ package của lớp ứng dụng chính và các package con. Những lớp mang annotation như @Component, @Service, @Repository hoặc @Controller có thể được phát hiện trong phạm vi component scan.

Nếu lớp nằm ngoài phạm vi scan, thiếu annotation phù hợp hoặc cấu hình scan bị giới hạn, bean có thể không xuất hiện trong ApplicationContext.

Một unit test tạo trực tiếp service vẫn chạy bình thường:

~~~java
var service = new ShippingService(policy, properties);
~~~

Nhưng khi Spring khởi động, một controller cần ShippingService có thể gặp lỗi không tìm thấy bean.

Unit test không kiểm tra được lỗi này vì nó không yêu cầu Spring tìm bean. Khi thay đổi package, cấu hình scan hoặc cấu trúc module, nên có một context test xác minh các bean quan trọng thực sự được đăng ký.

### 2.2. Dependency injection, qualifier và bean bị trùng

Spring phải chọn đúng bean để inject. Khi có nhiều implementation cùng một interface, ứng dụng có thể cần @Primary hoặc @Qualifier.

Ví dụ:

~~~java
public interface ShippingPolicy {
    BigDecimal calculate(Order order);
}

@Component("standardShippingPolicy")
class StandardShippingPolicy implements ShippingPolicy {
    // ...
}

@Component("expressShippingPolicy")
class ExpressShippingPolicy implements ShippingPolicy {
    // ...
}
~~~

Nếu một service yêu cầu ShippingPolicy mà không có quy tắc chọn bean, Spring có thể báo lỗi do có nhiều ứng viên.

Một unit test tự truyền StandardShippingPolicy vào constructor không phát hiện được lỗi chọn bean của Spring. Một context test mới có thể xác minh cấu hình injection thực tế.

Ví dụ, service cần chính sách giao hàng nhanh:

~~~java
@Service
public class ExpressShippingService {

    private final ShippingPolicy policy;

    public ExpressShippingService(
            @Qualifier("expressShippingPolicy") ShippingPolicy policy
    ) {
        this.policy = policy;
    }
}
~~~

Bài test có thể kiểm tra bean được quản lý và dependency đã được inject:

~~~java
@SpringBootTest
class ShippingWiringTest {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private ExpressShippingService shippingService;

    @Test
    void shouldRegisterExpressShippingService() {
        assertNotNull(shippingService);
        assertThat(context)
                .hasBean("expressShippingPolicy");
    }
}
~~~

Các import và package trong ví dụ được lược bỏ để tập trung vào cách kiểm tra. Context test sẽ phát hiện lỗi wiring ngay trong quá trình tạo ApplicationContext.

### 2.3. Đọc và bind cấu hình

Một service có thể chạy đúng với giá trị được truyền trực tiếp trong unit test nhưng ứng dụng lại đọc sai application.yml.

Ví dụ cấu hình:

~~~yaml
app:
  shipping:
    free-shipping-threshold: 500000
    currency: VND
~~~

Lớp properties:

~~~java
@ConfigurationProperties(prefix = "app.shipping")
@Validated
public record ShippingProperties(
        @NotNull BigDecimal freeShippingThreshold,
        @NotBlank String currency
) {
}
~~~

Cấu hình Spring đăng ký properties:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ShippingProperties.class)
public class ShippingConfiguration {
}
~~~

Unit test có thể tạo ShippingProperties với một giá trị hợp lệ bất kỳ. Nó không xác minh rằng Spring đã đăng ký configuration properties, đọc đúng prefix, bind đúng tên trường, chuyển đổi kiểu dữ liệu hoặc kích hoạt validation.

Một test có Spring Context có thể kiểm tra các giá trị được bind:

~~~java
@SpringBootTest(properties = {
        "app.shipping.free-shipping-threshold=500000",
        "app.shipping.currency=VND"
})
class ShippingPropertiesTest {

    @Autowired
    private ShippingProperties properties;

    @Test
    void shouldBindShippingProperties() {
        assertEquals(
                new BigDecimal("500000"),
                properties.freeShippingThreshold()
        );
        assertEquals("VND", properties.currency());
    }
}
~~~

Bài test này xác minh đường đi từ Environment của Spring đến object properties. Nó có thể phát hiện lỗi đăng ký properties hoặc lỗi bind mà unit test thuần Java không thể nhìn thấy.

Nếu cấu hình dùng @Validated cùng các constraint như @NotNull hoặc @NotBlank, có thể thêm test khởi tạo context với giá trị thiếu hoặc sai định dạng để xác nhận ứng dụng thất bại khi cấu hình không hợp lệ.

### 2.4. Profile và cấu hình theo môi trường

Một ứng dụng thường có cấu hình khác nhau cho local, test, staging và production. Spring có thể bật bean hoặc nạp cấu hình theo profile:

~~~java
@Configuration
@Profile("production")
class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new ProductionPaymentGateway();
    }
}
~~~

~~~java
@Configuration
@Profile("test")
class TestPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new FakePaymentGateway();
    }
}
~~~

Một unit test có thể tự tạo FakePaymentGateway và chạy xanh. Nhưng nó không chứng minh profile test thực sự được kích hoạt hoặc profile production đăng ký đúng bean.

Có thể kiểm tra profile bằng:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentProfileTest {

    @Autowired
    private PaymentGateway paymentGateway;

    @Test
    void shouldUseTestPaymentGateway() {
        assertThat(paymentGateway)
                .isInstanceOf(FakePaymentGateway.class);
    }
}
~~~

Test này xác minh bean được chọn trong ApplicationContext khi profile test hoạt động.

Cần lưu ý rằng @ActiveProfiles đặt profile cho test context. Nó không chứng minh cấu hình triển khai production được nạp đúng trên máy chủ thật. Nếu cần kiểm tra cấu hình production, hãy dùng một context test riêng với profile hoặc property tương ứng và tránh kết nối đến hệ thống thật ngoài ý muốn.

### 2.5. Bean có điều kiện và auto-configuration

Spring Boot và các thư viện có thể đăng ký bean dựa trên điều kiện:

- @ConditionalOnProperty: phụ thuộc giá trị property.
- @ConditionalOnClass: phụ thuộc class có trên classpath.
- @ConditionalOnMissingBean: chỉ tạo bean khi chưa có bean phù hợp.
- @ConditionalOnBean: chỉ tạo bean khi một bean khác tồn tại.
- @Profile: phụ thuộc profile đang hoạt động.

Một unit test có thể kiểm tra logic của một class điều kiện hoặc tự tạo implementation cần thiết, nhưng không xác minh điều kiện đăng ký bean đã được đánh giá đúng trong ApplicationContext.

Ví dụ cấu hình tính phí chỉ được bật khi property cho phép:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ShippingProperties.class)
public class ShippingAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.shipping",
            name = "enabled",
            havingValue = "true"
    )
    ShippingService shippingService(ShippingProperties properties) {
        return new ShippingService(
                new StandardShippingPolicy(),
                properties
        );
    }
}
~~~

Khi property app.shipping.enabled không bật, bean ShippingService không nên được đăng ký bởi cấu hình này. Khi bật, bean cần xuất hiện.

Đây là hành vi của container và điều kiện cấu hình, vì vậy nên kiểm tra bằng ApplicationContextRunner hoặc một Spring context test phù hợp.

## 3. Khi nào cần kiểm thử với Spring ApplicationContext?

Không phải cứ dùng Spring là mọi unit test đều phải khởi động Spring. Hãy dùng unit test thuần Java khi câu hỏi cần trả lời chỉ liên quan đến logic của object.

Nên bổ sung context test khi câu hỏi liên quan đến một trong các nội dung sau:

| Câu hỏi cần xác minh | Unit test thuần Java | Kiểm thử Spring Context |
|---|---|---|
| Phương thức tính toán có đúng không? | Phù hợp | Thường không cần |
| Constructor và logic xử lý có đúng không? | Phù hợp | Không bắt buộc |
| Spring có phát hiện và đăng ký component không? | Không xác minh | Cần |
| Dependency injection có chọn đúng bean không? | Không xác minh | Cần |
| @Qualifier hoặc @Primary có hoạt động đúng không? | Không xác minh | Cần |
| application.yml có bind đúng vào properties không? | Không xác minh | Cần |
| Profile có chọn đúng cấu hình không? | Không xác minh | Cần |
| @ConditionalOnProperty có đăng ký bean đúng điều kiện không? | Không xác minh | Cần |
| Auto-configuration có hoạt động với classpath và bean hiện tại không? | Không xác minh | Cần |
| @Transactional có tạo hành vi rollback đúng không? | Không xác minh nếu gọi object trực tiếp | Cần gọi bean được Spring quản lý |
| Security filter hoặc MVC configuration có hoạt động không? | Không xác minh | Cần web slice hoặc context phù hợp |

Một context test không nhất thiết phải khởi động toàn bộ ứng dụng. Chọn loại context nhỏ nhất có thể chứng minh điều đang cần kiểm tra.

## 4. Các lựa chọn kiểm thử cấu hình Spring

### 4.1. ApplicationContextRunner cho cấu hình và auto-configuration

Spring Boot Test cung cấp ApplicationContextRunner để khởi tạo một context nhỏ theo từng lần chạy test. Công cụ này đặc biệt hữu ích khi kiểm tra cấu hình tự động hoặc các bean có điều kiện.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.discount")
public record DiscountProperties(
        BigDecimal rate
) {
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(DiscountProperties.class)
public class DiscountConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.discount",
            name = "enabled",
            havingValue = "true"
    )
    DiscountService discountService(DiscountProperties properties) {
        return new DiscountService(properties.rate());
    }
}
~~~

Test kiểm tra trường hợp được bật:

~~~java
class DiscountConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(DiscountConfiguration.class)
                    .withPropertyValues(
                            "app.discount.enabled=true",
                            "app.discount.rate=0.10"
                    );

    @Test
    void shouldRegisterDiscountServiceWhenEnabled() {
        contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(DiscountService.class);

            var properties =
                    context.getBean(DiscountProperties.class);

            assertEquals(
                    new BigDecimal("0.10"),
                    properties.rate()
            );
        });
    }
}
~~~

Test kiểm tra trường hợp bị tắt:

~~~java
@Test
void shouldNotRegisterDiscountServiceWhenDisabled() {
    new ApplicationContextRunner()
            .withUserConfiguration(DiscountConfiguration.class)
            .withPropertyValues(
                    "app.discount.enabled=false",
                    "app.discount.rate=0.10"
            )
            .run(context -> {
                assertThat(context)
                        .doesNotHaveBean(DiscountService.class);
            });
}
~~~

Các ví dụ cần dependency spring-boot-test và những lớp nghiệp vụ tương ứng trong dự án. Phần quan trọng là test không tự tạo DiscountService bằng constructor. Nó yêu cầu Spring xử lý cấu hình, bind properties và đánh giá điều kiện đăng ký bean.

Ưu điểm của ApplicationContextRunner:

- Chỉ nạp cấu hình được chỉ định.
- Dễ thay đổi property giữa các tình huống.
- Dễ kiểm tra bean có hoặc không có.
- Mỗi lần chạy có context riêng, giúp kiểm tra các tổ hợp cấu hình độc lập.
- Không cần khởi động web server hoặc toàn bộ ứng dụng.

Khi viết thư viện hoặc auto-configuration, có thể dùng WebApplicationContextRunner hoặc ReactiveWebApplicationContextRunner nếu cấu hình cần môi trường web tương ứng.

### 4.2. @SpringJUnitConfig và @ContextConfiguration

Nếu cần kiểm tra một nhóm cấu hình Spring cụ thể, có thể dùng @SpringJUnitConfig để kết hợp hỗ trợ JUnit Jupiter và Spring TestContext.

~~~java
@Configuration
class PricingTestConfiguration {

    @Bean
    PricingPolicy pricingPolicy() {
        return new StandardPricingPolicy();
    }

    @Bean
    PricingService pricingService(PricingPolicy policy) {
        return new PricingService(policy);
    }
}
~~~

~~~java
@SpringJUnitConfig(PricingTestConfiguration.class)
class PricingSpringConfigurationTest {

    @Autowired
    private PricingService pricingService;

    @Autowired
    private ApplicationContext context;

    @Test
    void shouldCreatePricingServiceWithConfiguredPolicy() {
        assertNotNull(pricingService);
        assertThat(context)
                .hasSingleBean(PricingPolicy.class);
    }
}
~~~

Cách này phù hợp khi muốn kiểm tra cấu hình Java cụ thể mà không cần tải toàn bộ cấu hình Spring Boot của ứng dụng.

Có thể dùng @ContextConfiguration để chỉ rõ nguồn cấu hình context. Khi bài test cần tích hợp với các cơ chế của Spring TestContext, các annotation như @SpringJUnitConfig giúp khai báo gọn hơn.

### 4.3. @SpringBootTest cho cấu hình ứng dụng ở phạm vi rộng

Khi cần xác minh nhiều phần của ứng dụng cùng được lắp ráp, @SpringBootTest có thể khởi động ApplicationContext theo cấu hình Spring Boot.

~~~java
@SpringBootTest
class ApplicationConfigurationTest {

    @Autowired
    private ApplicationContext context;

    @Autowired
    private ShippingService shippingService;

    @Test
    void shouldLoadRequiredApplicationBeans() {
        assertNotNull(shippingService);
        assertThat(context)
                .hasSingleBean(ShippingPolicy.class);
    }
}
~~~

Mặc định, @SpringBootTest không nhất thiết mở HTTP server thật. Nó thường tạo context với môi trường web mock nếu ứng dụng có web environment. Nếu chỉ kiểm tra bean wiring, không cần thiết phải mở server.

Có thể truyền property riêng cho test:

~~~java
@SpringBootTest(properties = {
        "app.shipping.enabled=true",
        "app.shipping.currency=VND"
})
class ShippingApplicationConfigurationTest {
    // Inject bean và xác minh cấu hình đã được nạp.
}
~~~

Nếu muốn dùng một file cấu hình riêng, có thể kết hợp @TestPropertySource hoặc cơ chế cấu hình test phù hợp. Cần nhớ rằng property truyền trực tiếp cho test có thể ghi đè giá trị trong application.yml; do đó bài test chứng minh cấu hình với bộ property đã thiết lập, không tự động chứng minh mọi môi trường triển khai đều đúng.

### 4.4. Slice test khi chỉ cần xác minh một phần Spring

Một số annotation của Spring Boot tạo ApplicationContext giới hạn theo từng lớp chức năng:

- @WebMvcTest: tập trung vào MVC, controller, converter, validation và các thành phần web liên quan.
- @DataJpaTest: tập trung vào entity, repository và hạ tầng JPA.
- @JsonTest: tập trung vào serialization/deserialization JSON.
- @RestClientTest: tập trung vào client HTTP và cấu hình chuyển đổi request/response.
- @JdbcTest: tập trung vào JDBC và thao tác với database.

Ví dụ, nếu thay đổi cấu hình Jackson khiến API trả JSON sai định dạng, một bài test kiểm tra object Java trực tiếp không đủ. Có thể dùng @JsonTest để xác minh cấu hình JSON trong Spring Boot.

Nếu thay đổi security filter chain hoặc cấu hình MVC, @WebMvcTest có thể giúp kiểm tra request, response và các filter trong phạm vi web test. Nếu cần xác minh cả luồng backend và database, hãy chọn context rộng hơn.

Slice test có chủ đích không tải mọi bean. Nếu một controller phụ thuộc service không thuộc slice, test có thể cần mock bean hoặc import cấu hình test cần thiết. Điều đó không phải lỗi của slice; đó là ranh giới mà slice được thiết kế để giữ.

## 5. Khi annotation tạo proxy, unit test gọi trực tiếp object sẽ bỏ qua hành vi Spring

Một nhóm lỗi cấu hình quan trọng liên quan đến proxy và AOP.

Spring có thể tạo proxy quanh bean để áp dụng các hành vi như:

- @Transactional: quản lý transaction.
- @Cacheable: đọc/ghi cache.
- @Async: thực thi bất đồng bộ.
- @PreAuthorize hoặc các annotation method security: kiểm tra quyền truy cập.
- Một số cơ chế retry, tracing hoặc interceptor khác.

Ví dụ:

~~~java
@Service
public class TransferService {

    private final AccountRepository accountRepository;

    public TransferService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional
    public void transfer(Account source, Account target, BigDecimal amount) {
        source.withdraw(amount);
        accountRepository.save(source);

        target.deposit(amount);
        accountRepository.save(target);
    }
}
~~~

Nếu unit test tạo service trực tiếp:

~~~java
var service = new TransferService(repository);
service.transfer(source, target, amount);
~~~

thì phương thức được gọi trên object thường không đi qua transaction proxy do Spring quản lý. Test vẫn có thể xác minh logic trừ tiền và cộng tiền, nhưng không xác minh transaction được mở, commit hoặc rollback đúng cách.

Để kiểm tra transaction, cần lấy bean từ ApplicationContext và gọi qua bean đó:

~~~java
@SpringBootTest
class TransferTransactionTest {

    @Autowired
    private TransferService transferService;

    @Autowired
    private AccountRepository accountRepository;

    @Test
    void shouldRollbackTransferWhenOperationFails() {
        // Chuẩn bị hai tài khoản trong database test.

        assertThatThrownBy(() ->
                transferService.transfer(
                        sourceAccount(),
                        targetAccount(),
                        new BigDecimal("100")
                )
        ).isInstanceOf(IllegalStateException.class);

        // Đọc lại dữ liệu và xác minh transaction đã rollback.
    }
}
~~~

Đây là khung minh họa. Trong bài test thực tế, cần lưu dữ liệu trước khi gọi service, dùng id hoặc dữ liệu test xác định, rồi đọc lại từ repository để xác minh cả hai tài khoản giữ nguyên số dư khi giao dịch thất bại.

Một số lưu ý quan trọng:

- Transaction mặc định rollback với RuntimeException và Error; checked exception có quy tắc khác trừ khi cấu hình rollbackFor.
- Test không nên tự chạy trong transaction ngoài nếu mục tiêu là quan sát commit/rollback của transaction service, vì transaction test có thể làm thay đổi cách các transaction tham gia.
- Gọi một method được đánh dấu @Transactional từ method khác trong cùng object thường là self-invocation và không đi qua proxy trong chế độ proxy mặc định.
- Nếu method không được proxy hỗ trợ do visibility, kiểu proxy hoặc cấu trúc bean, annotation có thể không tạo ra hành vi mong đợi.

Cùng nguyên tắc này áp dụng cho @Cacheable, @Async và method security: nếu cần xác minh hành vi do Spring interceptor cung cấp, hãy gọi bean đã được Spring quản lý qua đúng context.

## 6. Các dấu hiệu cho thấy cần bổ sung context test

Trong quá trình phát triển, hãy xem xét thêm một bài test có Spring Context khi xuất hiện các thay đổi hoặc lỗi sau:

**Thay đổi cấu trúc package hoặc module**

- Chuyển lớp sang package khác.
- Tách module hoặc đổi package của application class.
- Sửa @ComponentScan, @Import hoặc cấu hình đăng ký bean.

Những thay đổi này có thể làm component không được tìm thấy dù unit test của lớp vẫn chạy.

**Thay đổi dependency injection**

- Thêm implementation mới cho một interface.
- Thêm @Qualifier hoặc @Primary.
- Thay đổi constructor của bean.
- Đổi bean theo profile hoặc điều kiện.

Cần xác minh Spring chọn đúng bean và context khởi tạo thành công.

**Thay đổi cấu hình**

- Đổi tên property hoặc prefix.
- Thay đổi kiểu dữ liệu trong @ConfigurationProperties.
- Thêm validation cho property.
- Sửa profile hoặc biến môi trường.
- Thay đổi thứ tự ưu tiên giữa các nguồn cấu hình.

Cần xác minh giá trị cuối cùng mà bean nhận được.

**Thay đổi auto-configuration**

- Thêm hoặc sửa @ConditionalOnProperty.
- Thay đổi @ConditionalOnMissingBean.
- Nâng phiên bản starter hoặc thư viện.
- Thay đổi dependency làm một class xuất hiện hoặc biến mất khỏi classpath.

Cần kiểm tra điều kiện đăng ký bean trong các trường hợp bật, tắt và thiếu cấu hình.

**Thay đổi hành vi do proxy**

- Thêm @Transactional.
- Thêm @Cacheable hoặc @CacheEvict.
- Bật @Async.
- Bật method security.
- Thay đổi cấu hình AOP hoặc transaction manager.

Cần gọi bean qua Spring và xác minh tác động thực tế của interceptor.

**Thay đổi cấu hình web hoặc persistence**

- Sửa SecurityFilterChain.
- Thay đổi converter, formatter, Jackson module hoặc validator.
- Đổi DataSource, JPA dialect, transaction manager.
- Thay đổi migration hoặc cấu hình repository.

Cần dùng slice test hoặc integration test tương ứng.

## 7. Chọn loại context test phù hợp với câu hỏi

Không nên mặc định dùng @SpringBootTest cho mọi kiểm tra cấu hình. Khởi động toàn bộ ứng dụng làm test chậm hơn và có thể kéo theo nhiều dependency không liên quan.

| Mục tiêu | Công cụ phù hợp | Phạm vi |
|---|---|---|
| Kiểm tra logic một class | JUnit + Mockito | Không cần Spring Context |
| Kiểm tra một @Configuration đơn giản | @SpringJUnitConfig | Chỉ context và cấu hình được chọn |
| Kiểm tra auto-configuration, conditional bean, properties | ApplicationContextRunner | Context nhỏ, dễ thay đổi property |
| Kiểm tra cấu hình ứng dụng Boot tổng thể | @SpringBootTest | ApplicationContext của ứng dụng |
| Kiểm tra controller, filter, validation, JSON HTTP | @WebMvcTest | Web slice |
| Kiểm tra repository và mapping JPA | @DataJpaTest | JPA slice |
| Kiểm tra serialization JSON | @JsonTest | JSON slice |
| Kiểm tra HTTP client | @RestClientTest | REST client slice |
| Kiểm tra request qua server thật | @SpringBootTest với RANDOM_PORT | Ứng dụng và HTTP server thật |

Có thể dùng quy tắc lựa chọn sau:

1. Nếu câu hỏi chỉ là logic của object, dùng unit test.
2. Nếu câu hỏi là Spring có tạo đúng một bean từ một cấu hình cụ thể không, dùng context runner hoặc @SpringJUnitConfig.
3. Nếu câu hỏi là nhiều bean trong ứng dụng có được lắp ráp đúng không, dùng @SpringBootTest.
4. Nếu câu hỏi chỉ liên quan đến MVC, JPA, JSON hoặc REST client, dùng slice test phù hợp.
5. Nếu câu hỏi liên quan đến giao tiếp mạng thực tế hoặc toàn bộ hành trình, mở rộng đến server thật hoặc system/E2E test.

## 8. Tổ chức bộ test để vừa nhanh vừa kiểm tra được cấu hình

Một bộ test tốt thường chia trách nhiệm rõ ràng:

~~~text
ShippingServiceTest
    |
    +-- Kiểm tra quy tắc tính phí
    +-- Mock ShippingPolicy
    +-- Không khởi động Spring

ShippingConfigurationTest
    |
    +-- Kiểm tra bean registration
    +-- Kiểm tra property binding
    +-- Kiểm tra conditional configuration
    +-- Dùng ApplicationContextRunner

ShippingApplicationIntegrationTest
    |
    +-- Kiểm tra wiring giữa các bean
    +-- Kiểm tra cấu hình ứng dụng rộng hơn
    +-- Dùng @SpringBootTest khi cần

ShippingApiTest
    |
    +-- Kiểm tra HTTP contract
    +-- Kiểm tra filter và validation
    +-- Dùng @WebMvcTest hoặc server thật tùy mục tiêu
~~~

Mỗi nhóm test tạo ra một loại bằng chứng riêng:

- Unit test chứng minh logic của object với dependency đã kiểm soát.
- Configuration test chứng minh Spring đăng ký và cấu hình bean theo điều kiện đã thiết lập.
- Integration test chứng minh các thành phần thật phối hợp qua ranh giới cần kiểm tra.
- System test chứng minh hành vi của ứng dụng từ điểm vào bên ngoài.

Một số nguyên tắc giúp các test này ổn định:

**Chỉ nạp context cần thiết**

Dùng ApplicationContextRunner hoặc slice test nếu chỉ cần xác minh một phần cấu hình. Không khởi động toàn bộ ứng dụng chỉ để kiểm tra một property đơn giản.

**Tách dữ liệu test khỏi cấu hình production**

Dùng property hoặc profile dành riêng cho test. Không để context test vô tình gọi cổng thanh toán thật, gửi email thật hoặc ghi dữ liệu vào hệ thống production.

**Kiểm tra cả trường hợp bật và tắt**

Với bean có điều kiện, chỉ kiểm tra trường hợp property bật là chưa đủ. Hãy kiểm tra trường hợp tắt, thiếu property hoặc có bean thay thế nếu các trường hợp đó thuộc hợp đồng cấu hình.

**Kiểm tra lỗi cấu hình một cách có chủ đích**

Với properties bắt buộc, có thể kiểm tra context thất bại khi thiếu hoặc sai giá trị. Điều này giúp lỗi xuất hiện ngay khi khởi động thay vì chờ đến lúc một request hiếm gặp.

**Không lặp lại toàn bộ logic nghiệp vụ trong context test**

Context test nên xác minh bean graph, property, profile, proxy hoặc tích hợp. Các nhánh nghiệp vụ chi tiết vẫn thuộc unit test. Điều này giúp giảm số lượng test chậm và tránh hai loại test cùng kiểm tra một điều.

**Quan sát hành vi thay vì chỉ kiểm tra context khởi động**

Context khởi động thành công là điều kiện cần, nhưng chưa đủ để xác minh mọi cấu hình. Ví dụ, bean có thể tồn tại nhưng property bind sai; proxy có thể được tạo nhưng transaction không rollback như mong đợi. Hãy kiểm tra giá trị, loại bean hoặc tác động runtime tương ứng.

## 9. Cách đọc kết quả test mà không kết luận quá mức

Khi một unit test xanh, có thể kết luận logic được kiểm tra hoạt động với dữ liệu và dependency giả lập của test. Không thể suy ra rằng ứng dụng Spring khởi động thành công.

Khi một ApplicationContextRunner test xanh, có thể kết luận cấu hình được nạp trong context nhỏ với classpath và property đã cung cấp. Không thể suy ra toàn bộ ứng dụng production đã cấu hình đúng.

Khi một @SpringBootTest xanh, có thể kết luận ApplicationContext được dựng thành công với cấu hình test đã chọn và các assertion của test đều đạt. Không thể suy ra các profile khác, môi trường triển khai khác hoặc mọi dịch vụ bên ngoài đều hoạt động.

Khi một @WebMvcTest xanh, có thể kết luận hành vi web thuộc slice đã kiểm tra hoạt động trong context test. Không thể suy ra database hoặc toàn bộ service layer hoạt động đúng nếu chúng đã được thay bằng mock.

Khi một system/E2E test xanh, có thể kết luận hành trình đã chạy thành công trong môi trường và dữ liệu của lần test đó. Không thể suy ra mọi nhánh nghiệp vụ hoặc mọi tình huống lỗi đều đã được bao phủ.

Luôn gắn kết luận với ranh giới, cấu hình và dependency thực tế của bài test. Điều đó giúp báo cáo kiểm thử có ý nghĩa kỹ thuật và tránh tạo cảm giác an toàn giả.

## 10. Kết luận

Unit test vẫn là lựa chọn phù hợp nhất để kiểm tra logic nhỏ, nhanh và có khả năng khoanh vùng lỗi tốt. Nhưng khi câu hỏi chuyển sang việc Spring có tạo bean, inject dependency, bind properties, chọn profile, đánh giá điều kiện hoặc áp dụng proxy đúng cách hay không, cần có test chạy qua Spring ApplicationContext.

Hãy chọn phạm vi nhỏ nhất có thể trả lời câu hỏi:

- Dùng JUnit và Mockito để kiểm tra logic object.
- Dùng ApplicationContextRunner để kiểm tra cấu hình và auto-configuration theo từng bộ property.
- Dùng @SpringJUnitConfig khi cần một context Spring giới hạn.
- Dùng slice test khi chỉ cần xác minh MVC, JPA, JSON hoặc REST client.
- Dùng @SpringBootTest khi cần xác minh cấu hình ứng dụng và sự phối hợp của nhiều bean.
- Gọi bean được Spring quản lý khi cần kiểm tra transaction, cache, async hoặc các hành vi proxy.

Khi tách rõ logic nghiệp vụ và cấu hình framework, bộ test vừa giữ được tốc độ phản hồi nhanh, vừa có bằng chứng trực tiếp cho những phần mà unit test thuần Java không thể xác nhận.


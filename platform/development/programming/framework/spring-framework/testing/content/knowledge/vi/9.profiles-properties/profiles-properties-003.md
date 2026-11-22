# @TestPropertySource với tệp hoặc thuộc tính trực tiếp

Trong Spring TestContext Framework, annotation **@TestPropertySource** cho phép khai báo các nguồn thuộc tính chỉ áp dụng cho một test ApplicationContext. Ta có thể nạp cấu hình từ một hoặc nhiều file, khai báo trực tiếp các cặp key-value ngay trên test class, hoặc kết hợp cả hai cách. Những giá trị này được đưa vào Environment của Spring trước khi bean được tạo, nhờ đó test có thể điều khiển cấu hình mà không phải sửa file cấu hình chính của ứng dụng.

Ví dụ, service dùng thuộc tính checkout.enabled để bật hoặc tắt chức năng thanh toán. Trong production, giá trị có thể đến từ application.properties hoặc biến môi trường. Test có thể cung cấp giá trị riêng:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(properties = "checkout.enabled=false")
class CheckoutServiceTest {

    @Autowired
    private CheckoutService checkoutService;

    @Test
    void rejectsCheckoutWhenFeatureIsDisabled() {
        // Kiểm tra hành vi khi checkout.enabled=false.
    }
}
~~~

@TestPropertySource hữu ích khi cần kiểm thử một bean với cấu hình xác định, tái sử dụng một bộ cấu hình trong file fixture hoặc ghi đè một vài giá trị cho từng test class. Nó thuộc Spring TestContext Framework nên dùng được với Spring Framework thuần, Spring MVC test và Spring Boot test.

## 1. Vai trò của thuộc tính trong Spring Environment

Spring Environment cung cấp mô hình thống nhất để đọc property và xác định profile đang hoạt động. Bean có thể truy cập thuộc tính qua Environment, dùng @Value hoặc nhận dữ liệu qua @ConfigurationProperties.

~~~java
@Component
class CheckoutService {

    private final boolean enabled;

    CheckoutService(@Value("${checkout.enabled:true}") boolean enabled) {
        this.enabled = enabled;
    }

    boolean isEnabled() {
        return enabled;
    }
}
~~~

Giá trị checkout.enabled có thể đến từ nhiều PropertySource khác nhau, ví dụ:

- Thuộc tính trong file cấu hình ứng dụng.
- Java system properties.
- Environment variables của hệ điều hành.
- PropertySource được đăng ký bởi cấu hình Spring.
- Thuộc tính dành riêng cho test.

Spring tìm giá trị theo thứ tự ưu tiên của các PropertySource trong Environment. Khi test cần kiểm soát một giá trị cụ thể, @TestPropertySource thêm nguồn thuộc tính dành riêng cho test vào Environment của context.

Điểm quan trọng là annotation này không sửa file application.properties, không thay đổi biến môi trường của máy và cũng không ghi đè cấu hình toàn cục trong hệ điều hành. Nó cung cấp giá trị cho context được tạo để chạy test.

## 2. Khai báo thuộc tính trực tiếp bằng properties

Thuộc tính có thể được khai báo ngay trên annotation thông qua thuộc tính properties:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(properties = {
    "checkout.enabled=false",
    "checkout.timeout=5s",
    "checkout.currency=VND"
})
class CheckoutConfigurationTest {

    @Autowired
    private Environment environment;

    @Test
    void exposesInlineTestProperties() {
        assertEquals(
            "false",
            environment.getProperty("checkout.enabled")
        );
        assertEquals(
            "5s",
            environment.getProperty("checkout.timeout")
        );
        assertEquals(
            "VND",
            environment.getProperty("checkout.currency")
        );
    }
}
~~~

Mỗi phần tử trong mảng properties là một chuỗi biểu diễn thuộc tính. Có thể dùng cú pháp key=value hoặc key:value. Khoảng trắng quanh dấu phân cách được xử lý theo quy tắc phân tích thuộc tính của Java Properties.

~~~java
@TestPropertySource(properties = {
    "feature.search.enabled = true",
    "feature.search.page-size: 25"
})
~~~

Thuộc tính properties phù hợp với:

- Giá trị nhỏ chỉ dùng trong một test class.
- Ghi đè một vài thuộc tính mặc định.
- Cấu hình biến thể test mà không cần tạo thêm file.
- Làm rõ điều kiện test ngay tại nơi khai báo.

Không nên đặt một danh sách rất dài thuộc tính trực tiếp trong annotation nếu nó khiến test class khó đọc. Khi có nhiều cấu hình liên quan hoặc nhiều test dùng chung, chuyển chúng vào file properties có thể giúp tổ chức tốt hơn.

### 2.1. Đọc thuộc tính bằng Environment

Environment cho phép truy cập property theo tên và chuyển đổi kiểu dữ liệu:

~~~java
@Autowired
private Environment environment;

@Test
void readsConfiguredValues() {
    assertEquals("VND", environment.getProperty("checkout.currency"));
    assertFalse(environment.getProperty(
        "checkout.enabled",
        Boolean.class,
        true
    ));
}
~~~

Khi cần giá trị mặc định, có thể dùng overload nhận default value. Nếu thuộc tính bắt buộc phải có, nên dùng cách đọc khiến test thất bại rõ ràng khi thiếu cấu hình, thay vì âm thầm nhận một giá trị mặc định không phù hợp.

### 2.2. Dùng @Value

Bean có thể nhận thuộc tính bằng @Value:

~~~java
@Component
class SearchSettings {

    private final int pageSize;

    SearchSettings(@Value("${feature.search.page-size}") int pageSize) {
        this.pageSize = pageSize;
    }

    int pageSize() {
        return pageSize;
    }
}
~~~

Test khai báo giá trị:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(properties = "feature.search.page-size=25")
class SearchSettingsTest {

    @Autowired
    private SearchSettings settings;

    @Test
    void injectsPageSizeFromTestPropertySource() {
        assertEquals(25, settings.pageSize());
    }
}
~~~

Property phải có mặt trong Environment trước khi bean được khởi tạo và xử lý placeholder. Vì vậy, @TestPropertySource được khai báo trên test class, không phải một thao tác thay đổi giá trị sau khi context đã tạo bean.

### 2.3. Dùng @ConfigurationProperties

Với nhóm cấu hình có cấu trúc, @ConfigurationProperties thường dễ quản lý hơn nhiều @Value rời rạc:

~~~java
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    private boolean enabled;
    private Duration timeout = Duration.ofSeconds(10);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Test có thể cung cấp:

~~~java
@SpringJUnitConfig(CheckoutTestConfig.class)
@TestPropertySource(properties = {
    "checkout.enabled=true",
    "checkout.timeout=3s"
})
class CheckoutPropertiesTest {

    @Autowired
    private CheckoutProperties properties;

    @Test
    void bindsInlineProperties() {
        assertTrue(properties.isEnabled());
        assertEquals(Duration.ofSeconds(3), properties.getTimeout());
    }
}
~~~

Trong ví dụ, CheckoutTestConfig cần đăng ký CheckoutProperties bằng @EnableConfigurationProperties hoặc cơ chế đăng ký phù hợp của ứng dụng. Với Spring Boot, có thể dùng @EnableConfigurationProperties, @ConfigurationPropertiesScan hoặc cấu hình ứng dụng đã có. @TestPropertySource chỉ cung cấp giá trị; nó không tự đăng ký bean cấu hình.

## 3. Nạp thuộc tính từ file

Khi cấu hình có nhiều giá trị, được dùng lại trong nhiều test hoặc cần được xem như một fixture riêng, khai báo file trong locations:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(locations = "classpath:/test-config/checkout.properties")
class CheckoutServiceIntegrationTest {

    @Autowired
    private CheckoutService checkoutService;

    @Test
    void usesCheckoutTestConfiguration() {
        // ...
    }
}
~~~

Tạo file trong src/test/resources:

~~~properties
checkout.enabled=true
checkout.timeout=3s
checkout.currency=VND
payment.gateway.url=https://gateway.example.test
~~~

Vì src/test/resources nằm trên test classpath, Spring có thể tìm file bằng ClassPathResource. Prefix classpath: giúp thể hiện rõ nguồn tài nguyên và tránh phụ thuộc vào working directory.

### 3.1. Các dạng location

Thuộc tính locations nhận một hoặc nhiều resource location. Các dạng thường dùng:

| Dạng location | Ý nghĩa | Ví dụ |
|---|---|---|
| classpath: | Tìm tài nguyên trên classpath | classpath:/test-config/app.properties |
| file: | Đọc file từ filesystem | file:./config/test.properties |
| URL có scheme | Đọc resource từ URL được hỗ trợ | https://example.test/config.properties |
| Đường dẫn không có prefix | Mặc định được hiểu là classpath resource | test-config/app.properties |

Trong test tự động, file fixture trong classpath thường ổn định nhất. Đường dẫn file tương đối phụ thuộc thư mục làm việc, còn URL bên ngoài khiến test phụ thuộc mạng và hệ thống khác. Chỉ dùng các nguồn này khi đó là điều test cần kiểm tra.

Có thể khai báo nhiều file:

~~~java
@TestPropertySource(locations = {
    "classpath:/test-config/common.properties",
    "classpath:/test-config/checkout.properties"
})
~~~

Spring nạp các resource được khai báo và đưa các thuộc tính vào Environment. Khi có cùng một key ở nhiều nguồn, thứ tự và mức ưu tiên của PropertySource quyết định giá trị cuối cùng; hãy khai báo rõ ràng nguồn nào được dùng để ghi đè.

### 3.2. Đường dẫn mặc định khi không khai báo locations

Nếu @TestPropertySource không khai báo locations và cũng không khai báo properties, Spring có thể tìm file properties mặc định dựa trên tên đầy đủ của test class. Ví dụ, test class com.example.CheckoutServiceTest tương ứng với resource:

~~~text
classpath:com/example/CheckoutServiceTest.properties
~~~

Nếu file mặc định không tồn tại, Spring báo lỗi khi chuẩn bị test context. Cơ chế này có thể hữu ích khi mỗi test class có một file cấu hình riêng theo quy ước tên. Trong dự án có nhiều fixture, khai báo locations tường minh thường dễ đọc và dễ tìm hơn.

### 3.3. Đọc XML properties

DefaultPropertySourceFactory của Spring Test hỗ trợ resource properties theo định dạng properties và XML properties của Java. XML properties phải tuân theo định dạng mà java.util.Properties.loadFromXML hỗ trợ, không phải một file XML tùy ý.

Ví dụ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
<properties>
    <entry key="checkout.enabled">true</entry>
    <entry key="checkout.timeout">3s</entry>
</properties>
~~~

File có thể được tham chiếu bằng locations tương tự file properties. Nếu ứng dụng dùng một định dạng khác như YAML, cần cấu hình PropertySourceFactory phù hợp hoặc sử dụng cơ chế cấu hình của Spring Boot. Không nên đổi đuôi file thành .properties rồi mong Spring tự hiểu cú pháp YAML.

### 3.4. Encoding của file

Thuộc tính encoding cho phép chỉ định charset khi đọc file nguồn:

~~~java
@TestPropertySource(
    locations = "classpath:/test-config/messages.properties",
    encoding = "UTF-8"
)
~~~

Nếu file chứa ký tự tiếng Việt hoặc nội dung ngoài ASCII, hãy thống nhất encoding khi lưu file và khi nạp file. Không dựa vào charset mặc định của hệ điều hành vì máy phát triển và CI có thể khác nhau.

## 4. Kết hợp file và thuộc tính trực tiếp

Có thể dùng cả locations và properties trên cùng annotation:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(
    locations = "classpath:/test-config/checkout.properties",
    properties = {
        "checkout.enabled=false",
        "checkout.timeout=1s"
    }
)
class CheckoutOverrideTest {
    // ...
}
~~~

Đây là cách phù hợp khi file chứa bộ cấu hình nền, còn test class chỉ thay đổi một số giá trị để tạo tình huống riêng.

Khi cùng một key xuất hiện trong file và inline properties, inline properties có độ ưu tiên cao hơn thuộc tính nạp từ locations. Trong ví dụ trên, nếu file khai báo checkout.enabled=true thì giá trị trực tiếp false sẽ được dùng cho test context này.

Quy tắc này giúp tạo cấu hình theo lớp:

1. File properties lưu các giá trị nền được chia sẻ.
2. Inline properties mô tả khác biệt của một test class.
3. Test method kiểm tra hành vi của bean trong điều kiện đó.

Không nên khai báo cùng một key nhiều lần nếu không có chủ đích ghi đè. Nếu có override, hãy giữ tên thuộc tính và giá trị inline gần test đang kiểm tra để người đọc hiểu được lý do.

## 5. Thứ tự ưu tiên của test property sources

Spring Environment có thể chứa nhiều PropertySource. Các nguồn được thêm cho test có ưu tiên cao để test có thể ghi đè cấu hình ứng dụng. Với @TestPropertySource, các quy tắc quan trọng là:

- Thuộc tính trực tiếp trong properties có ưu tiên cao hơn thuộc tính được nạp từ locations.
- Test property sources có thể ghi đè các nguồn cấu hình thông thường như application-level @PropertySource, system properties và environment variables.
- Thuộc tính được đăng ký bằng @DynamicPropertySource có độ ưu tiên cao hơn @TestPropertySource.
- Các cơ chế cấu hình khác của framework hoặc Spring Boot có thể có quy tắc riêng; cần xem xét toàn bộ nguồn thuộc tính khi giá trị cuối cùng không như dự kiến.

Ví dụ, file cấu hình:

~~~properties
feature.mode=standard
feature.timeout=10s
~~~

Test class:

~~~java
@TestPropertySource(
    locations = "classpath:/test-config/feature.properties",
    properties = "feature.mode=isolated"
)
~~~

Trong test context, feature.mode nhận giá trị isolated; feature.timeout vẫn nhận 10s từ file.

Nếu giá trị bị ghi đè ngoài dự kiến, có thể kiểm tra nguồn bằng cách truy cập PropertySources của ConfigurableEnvironment:

~~~java
@Autowired
private Environment environment;

@Test
void inspectsPropertySources() {
    ConfigurableEnvironment configurable =
        (ConfigurableEnvironment) environment;

    configurable.getPropertySources().forEach(source ->
        System.out.println(source.getName())
    );
}
~~~

Ví dụ này dùng để điều tra thứ tự nguồn thuộc tính. Không nên để log debug hoặc assertion dựa trên tên nội bộ của PropertySource nếu tên đó không thuộc contract ổn định của ứng dụng.

## 6. Kế thừa cấu hình giữa test class

Khi test class kế thừa từ một lớp cơ sở, Spring TestContext có thể kế thừa các location và inline properties được khai báo ở lớp cha.

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(
    locations = "classpath:/test-config/integration.properties"
)
abstract class BaseIntegrationTest {
}

@TestPropertySource(properties = "payment.mode=stub")
class PaymentServiceTest extends BaseIntegrationTest {
    // ...
}
~~~

Mặc định, Spring kế thừa location và properties từ lớp bao quanh hoặc lớp cha theo mô hình test class tương ứng. Giá trị tại lớp con được kết hợp với giá trị kế thừa. Hai thuộc tính điều khiển hành vi này là:

- inheritLocations: mặc định true; quyết định có kế thừa danh sách resource locations hay không.
- inheritProperties: mặc định true; quyết định có kế thừa các inline properties hay không.

Có thể tắt riêng việc kế thừa:

~~~java
@TestPropertySource(
    locations = "classpath:/test-config/payment-isolated.properties",
    inheritLocations = false,
    inheritProperties = false
)
class IsolatedPaymentTest extends BaseIntegrationTest {
    // Chỉ dùng cấu hình khai báo trực tiếp ở lớp này.
}
~~~

Khi tắt kế thừa, test class con chỉ dùng nhóm cấu hình mà nó khai báo theo chính sách đó. Hãy dùng tùy chọn này khi nhóm test cần một môi trường thực sự khác; không nên tắt kế thừa chỉ để tránh hiểu thứ tự property source.

### 6.1. Kết hợp nhiều lớp cấu hình

Có thể tạo một lớp cơ sở cho cấu hình chung, rồi thêm properties riêng ở lớp con:

~~~java
@TestPropertySource(
    locations = "classpath:/test-config/application-test.properties"
)
abstract class BaseServiceTest {
}

@TestPropertySource(properties = {
    "notification.enabled=false",
    "notification.sender=test@example.test"
})
class NotificationServiceTest extends BaseServiceTest {
}
~~~

Cách này giảm lặp khi nhiều test dùng cùng bộ cấu hình nền. Tuy nhiên, lớp cơ sở nên chứa cấu hình thật sự chung. Nếu mỗi test class có một danh sách ghi đè dài và khác nhau, việc gom vào base class có thể làm nguồn giá trị khó theo dõi.

## 7. Kết hợp @TestPropertySource với @ActiveProfiles

@TestPropertySource và @ActiveProfiles giải quyết hai nhu cầu khác nhau:

- @ActiveProfiles chọn profile Spring cần kích hoạt, ví dụ test hoặc integration.
- @TestPropertySource cung cấp các giá trị thuộc tính bổ sung hoặc ghi đè cho test context.

Ví dụ:

~~~java
@SpringJUnitConfig(AppConfig.class)
@ActiveProfiles("test")
@TestPropertySource(properties = {
    "payment.gateway.url=https://gateway.example.test",
    "payment.retry.enabled=false"
})
class PaymentServiceTest {
    // ...
}
~~~

Profile test có thể làm Spring chọn các bean được đánh dấu @Profile("test") hoặc nạp cấu hình profile tương ứng. Inline properties cung cấp giá trị riêng cho kịch bản test. Nếu mục tiêu là chọn bean theo profile, hãy khai báo @ActiveProfiles để ý định rõ ràng; không dùng một property tùy tiện thay cho cơ chế profile.

Khi file cấu hình có nhiều profile, cần hiểu rõ profile nào được kích hoạt và nguồn thuộc tính nào đang được nạp. Một property tồn tại trong file không đồng nghĩa profile chứa bean tương ứng đã hoạt động.

## 8. Dùng @TestPropertySource trong Spring Boot test

@TestPropertySource không chỉ dành cho @SpringJUnitConfig. Có thể dùng với @SpringBootTest hoặc test slice của Spring Boot:

~~~java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/test-config/order-service.properties"
)
class OrderServiceApplicationTest {

    @Autowired
    private OrderService orderService;

    @Test
    void startsWithTestConfiguration() {
        // ...
    }
}
~~~

Spring Boot cũng cung cấp thuộc tính properties trên @SpringBootTest để khai báo giá trị trực tiếp:

~~~java
@SpringBootTest(properties = {
    "order.processing.enabled=false",
    "order.processing.batch-size=10"
})
class OrderProcessingTest {
}
~~~

Hai cách có mục đích gần nhau nhưng không hoàn toàn đồng nhất về vị trí khai báo và cách tổ chức:

| Cách | Khi nên dùng |
|---|---|
| @TestPropertySource(properties = ...) | Muốn dùng cơ chế Spring TestContext và có thể kết hợp file resource |
| @TestPropertySource(locations = ...) | Muốn nạp bộ thuộc tính từ fixture riêng |
| @SpringBootTest(properties = ...) | Test dùng Spring Boot và muốn khai báo nhanh các giá trị inline tại annotation bootstrap |
| @DynamicPropertySource | Giá trị được cung cấp động trong lúc test, ví dụ URL/port của container hoặc dịch vụ khởi chạy |

Chọn một nơi khai báo rõ ràng cho mỗi nhóm cấu hình. Khi kết hợp nhiều cơ chế, cần nhớ thứ tự ưu tiên của chúng để tránh test nhận giá trị khác với dự kiến.

## 9. Khi nào nên dùng @DynamicPropertySource?

@TestPropertySource phù hợp với giá trị tĩnh đã biết trước khi context khởi tạo. Nếu giá trị chỉ có sau khi một tài nguyên thử nghiệm được khởi chạy, chẳng hạn cổng ngẫu nhiên của database container, @DynamicPropertySource phù hợp hơn.

~~~java
@SpringBootTest
class DatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", database::getJdbcUrl);
        registry.add("spring.datasource.username", database::getUsername);
        registry.add("spring.datasource.password", database::getPassword);
    }
}
~~~

Ví dụ cần Testcontainers và cấu hình vòng đời container phù hợp với dự án. DynamicPropertyRegistry nhận Supplier để lấy giá trị tại thời điểm Spring cần thuộc tính. Đây là lựa chọn tốt hơn việc cố ghi một port ngẫu nhiên vào file properties trước khi container chạy.

Có thể phối hợp @DynamicPropertySource với @TestPropertySource: file cung cấp cấu hình tĩnh, còn dynamic source cung cấp giá trị kết nối được sinh ra khi chạy test. Khi cùng key xuất hiện ở cả hai nguồn, dynamic property source có ưu tiên cao hơn.

## 10. Tùy chỉnh PropertySourceFactory

Mặc định, @TestPropertySource dùng factory của Spring để nạp file properties. Khi cần một định dạng khác hoặc cách tạo PropertySource riêng, có thể cung cấp PropertySourceFactory tùy chỉnh qua thuộc tính factory.

Ví dụ cấu trúc khai báo:

~~~java
@TestPropertySource(
    locations = "classpath:/test-config/application-test.yml",
    factory = YamlPropertySourceFactory.class
)
class YamlBackedTest {
}
~~~

YamlPropertySourceFactory ở đây là class do ứng dụng hoặc thư viện cung cấp; Spring Test không mặc định biến mọi file YAML thành property source chỉ vì phần mở rộng là .yml. Factory cần đọc Resource, phân tích nội dung và trả về PropertySource phù hợp.

Khi triển khai factory riêng, cần xử lý rõ:

- Resource không tồn tại hoặc không đọc được.
- Nội dung sai cú pháp.
- Encoding của file.
- Cấu trúc YAML lồng nhau và quy tắc ánh xạ key.
- Tên PropertySource và cách xử lý nhiều resource.

Thuộc tính factory có trong các phiên bản Spring Framework hỗ trợ API này; cần đối chiếu phiên bản framework của dự án trước khi dùng. Nếu chỉ cần vài thuộc tính cho test, inline properties thường đơn giản hơn việc tạo một factory.

## 11. Property source và Spring TestContext cache

Spring TestContext Framework có thể cache ApplicationContext giữa các test có cấu hình tương đương. Cấu hình nguồn thuộc tính là một phần của metadata dùng để xác định context có thể tái sử dụng hay không.

Điều này có một số hệ quả:

- Nhiều test class dùng cùng cấu hình locations và properties có thể tái sử dụng context.
- Mỗi test class khai báo một tập inline properties khác nhau có thể cần một context riêng.
- Thay đổi thứ tự hoặc nội dung nguồn thuộc tính có thể làm cấu hình context khác đi.
- Dùng quá nhiều biến thể property source làm tăng số context cần khởi tạo và thời gian chạy suite.

Ví dụ, nếu mười test class cùng cần checkout.enabled=true và checkout.timeout=3s, có thể dùng một file fixture chung hoặc một cấu hình cơ sở thống nhất. Chỉ tạo biến thể riêng khi test thực sự cần điều kiện khác.

Không nên gom mọi test vào cùng một context chỉ để tăng cache hit nếu việc đó làm trạng thái giữa các test bị chia sẻ không an toàn. Tính độc lập và độ tin cậy của test vẫn quan trọng hơn việc tối ưu thời gian khởi tạo context.

## 12. Các lỗi thường gặp

### 12.1. Sai đường dẫn resource

Một location không tìm thấy sẽ khiến quá trình nạp test property source thất bại khi chuẩn bị context. Đặt file trong src/test/resources, kiểm tra đúng chữ hoa/thường của tên file và dùng prefix classpath: rõ ràng.

### 12.2. Nhầm tên thuộc tính

Environment không tự đoán key gần giống. checkout.enable và checkout.enabled là hai thuộc tính khác nhau. Dùng một hằng số hoặc quy ước tên thống nhất nếu cùng key được dùng ở nhiều nơi.

### 12.3. Nghĩ rằng inline properties ghi ngược vào file

@TestPropertySource chỉ bổ sung PropertySource cho test context. Nó không chỉnh sửa application.properties hay file fixture. Nếu cần thay nội dung file, đó là một thao tác khác và không nên thực hiện như tác dụng phụ của test.

### 12.4. Không hiểu thứ tự ưu tiên

Nếu file có checkout.enabled=true nhưng inline property khai báo false, giá trị inline sẽ được ưu tiên. Khi kết quả không như mong đợi, kiểm tra mọi PropertySource liên quan, bao gồm dynamic property source và cấu hình ứng dụng.

### 12.5. Dùng @TestPropertySource để thay profile

Profile quyết định nhóm cấu hình hoặc bean nào được kích hoạt. Dùng @ActiveProfiles để mô tả profile của test; dùng @TestPropertySource để cung cấp giá trị thuộc tính.

### 12.6. Đọc thuộc tính quá sớm

Nếu một lớp tự đọc System.getProperty trong static initializer hoặc constructor được gọi trước khi Spring chuẩn bị context, nó có thể không thấy giá trị trong test PropertySource. Hãy để cấu hình đi qua Spring Environment, @Value hoặc ConfigurationProperties nếu thành phần thuộc Spring container.

### 12.7. Dùng file cấu hình quá lớn

Một file test chứa nhiều giá trị không liên quan khiến test khó hiểu và dễ bị ảnh hưởng bởi thay đổi khác. Chia fixture theo nhóm chức năng hoặc chỉ khai báo inline những giá trị cần thiết.

### 12.8. Dùng file YAML mà không có factory

Default property source factory không tự phân tích YAML như cấu hình Spring Boot. Nếu dùng YAML, hãy chọn factory hỗ trợ định dạng đó hoặc cơ chế cấu hình phù hợp; nếu không, dùng file .properties.

### 12.9. Thay đổi thuộc tính sau khi context đã tạo

TestPropertySource được áp dụng khi chuẩn bị context. Nếu thay đổi một thuộc tính sau khi bean đã được tạo, field đã inject bằng @Value hoặc ConfigurationProperties không tự động cập nhật. Với giá trị cần thay đổi theo thời gian trong cùng một test, thiết kế một abstraction có thể điều khiển được hoặc tạo context mới theo nhu cầu.

## 13. Mẫu tổ chức test theo cấu hình

Một test dùng file làm nền và inline properties để ghi đè có thể được viết như sau:

~~~java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(
    locations = "classpath:/test-config/checkout.properties",
    properties = {
        "checkout.enabled=false",
        "checkout.timeout=1s"
    }
)
class CheckoutDisabledTest {

    @Autowired
    private CheckoutService checkoutService;

    @Test
    void rejectsCheckoutWhenDisabled() {
        assertThrows(
            CheckoutDisabledException.class,
            () -> checkoutService.checkout(validCommand())
        );
    }
}
~~~

File checkout.properties có thể giữ các giá trị nền:

~~~properties
checkout.enabled=true
checkout.timeout=10s
checkout.currency=VND
checkout.max-items=20
~~~

Trong test context này, checkout.enabled và checkout.timeout được ghi đè bằng giá trị inline; currency và max-items vẫn lấy từ file. Điều này tạo ra một cấu hình dễ đọc và chỉ rõ những điểm khác biệt của kịch bản.

Khi thiết kế test dựa trên thuộc tính, hãy xác định:

- Giá trị nào là cấu hình nền được chia sẻ?
- Giá trị nào là điều kiện riêng của test?
- Nên khai báo file fixture hay inline properties?
- Có nguồn thuộc tính nào có ưu tiên cao hơn đang ghi đè không?
- Test có cần profile cụ thể hay chỉ cần một vài property?
- Giá trị có tĩnh hay phải lấy động từ tài nguyên thử nghiệm?
- Cấu hình có thể được chia sẻ để tái sử dụng context hay cần một context riêng?

## Kết luận

@TestPropertySource giúp Spring TestContext nạp cấu hình riêng cho test từ file hoặc các cặp thuộc tính khai báo trực tiếp. File phù hợp với bộ cấu hình nền được chia sẻ; inline properties phù hợp với các giá trị ngắn cần làm rõ ngay trong test class. Có thể kết hợp hai cách, kế thừa hoặc tắt kế thừa cấu hình, phối hợp với @ActiveProfiles và @DynamicPropertySource khi cần. Hiểu thứ tự ưu tiên và thời điểm tạo ApplicationContext giúp test nhận đúng cấu hình, ổn định và dễ duy trì.

# Thuộc tính, profile, bean override và việc phân mảnh cache

Spring TestContext Framework lưu cache các ApplicationContext đã khởi tạo để nhiều test có cùng cấu hình có thể dùng lại context. Cơ chế này giúp giảm thời gian chạy suite, đặc biệt khi một context phải khởi tạo nhiều bean, kết nối database hoặc dựng hạ tầng kiểm thử.

Cache chỉ dùng lại context khi cấu hình đã hợp nhất của các test tương đương. Thuộc tính kiểm thử, active profiles và khai báo thay thế bean đều có thể làm cấu hình khác nhau. Nếu mỗi test class tạo một biến thể cấu hình riêng, suite có thể khởi tạo nhiều context gần giống nhau. Hiện tượng đó thường được gọi là **phân mảnh cache**.

Hiểu những thành phần tham gia vào cache key giúp tổ chức test sao cho các context được tái sử dụng khi cấu hình thực sự giống nhau, đồng thời vẫn giữ các môi trường kiểm thử khác nhau khi rủi ro cần kiểm chứng khác nhau.

## 1. Spring TestContext cache hoạt động như thế nào?

Khi một test cần Spring ApplicationContext, TestContext Framework tạo hoặc tìm một context dựa trên cấu hình đã hợp nhất của test. Cấu hình này được biểu diễn bằng MergedContextConfiguration.

Luồng khái quát:

~~~text
Test class A                 Test class B
     |                            |
     v                            v
MergedContextConfiguration   MergedContextConfiguration
     |                            |
     +-------------+--------------+
                   |
                   v
              Cache lookup
                   |
          +--------+--------+
          |                 |
       Cache hit         Cache miss
          |                 |
          v                 v
    Reuse context       Create context
          |                 |
          +--------+--------+
                   |
                   v
              Run test
~~~

Hai test class có thể dùng chung ApplicationContext dù tên class và test method khác nhau, miễn là cấu hình đã hợp nhất tạo ra cùng cache key.

Ngược lại, hai class kiểm tra cùng một controller nhưng khai báo profile, property hoặc bean override khác nhau có thể cần hai context riêng. Điều này là cần thiết nếu chúng đại diện cho hai cấu hình ứng dụng khác nhau.

### Cache lưu gì?

Cache lưu ApplicationContext đã khởi tạo cùng thông tin cấu hình dùng để tìm lại context đó. Cache không lưu kết quả assertion, dữ liệu test của từng method hoặc trạng thái stubbing như một phần của cấu hình context.

Ví dụ:

- Hai test class cùng dùng một cấu hình MVC, cùng profile, cùng property và cùng bean override có thể dùng chung context.
- Hai test class chỉ khác tên nhưng có cấu hình tương đương vẫn có thể dùng chung context.
- Hai test class dùng profile test và profile integration khác nhau thường có cache key khác nhau.
- Một test class khai báo thêm mock bean hoặc thay implementation khác có thể tạo cache key riêng.

Điều cần ghi nhớ là **tên test class không phải yếu tố duy nhất quyết định cache hit**. Spring so sánh cấu hình đã hợp nhất.

## 2. Những thành phần tạo nên cache key

Spring TestContext Framework xây dựng cache key từ các phần của MergedContextConfiguration. Những thuộc tính chính gồm:

| Thành phần | Ý nghĩa | Ví dụ |
|---|---|---|
| locations | Đường dẫn XML hoặc resource cấu hình context | classpath:/test-context.xml |
| classes | Các lớp cấu hình hoặc component được nạp | TestConfig.class |
| contextInitializerClasses | Các initializer được đăng ký | DatabaseInitializer.class |
| contextCustomizers | Các tùy chỉnh context được phát hiện qua annotation hoặc factory | @DynamicPropertySource, bean override |
| contextLoader | Bộ nạp ApplicationContext | Loader của Spring Test hoặc Spring Boot |
| parent | Cấu hình context cha trong hierarchy | Parent context dùng chung |
| activeProfiles | Các profile được kích hoạt | test, integration |
| propertySourceDescriptors | Mô tả các nguồn property được khai báo | File trong @TestPropertySource |
| propertySourceProperties | Các property inline được khai báo | feature.payment.stub=true |
| resourceBasePath | Đường dẫn gốc tài nguyên web nếu có | Cấu hình @WebAppConfiguration |

Các annotation và extension có thể đóng góp metadata vào những phần này. Ví dụ, @DynamicPropertySource và các khai báo bean override được đưa vào context customizers.

Không phải mọi thay đổi trong test đều tạo cache key mới. Việc đổi dữ liệu đầu vào trong một test method, thay đổi Mockito stubbing trong lúc test chạy hoặc đổi tên method thường không làm cấu hình context thay đổi.

## 3. Property source và tác động tới cache

Test có thể cung cấp property bằng nhiều cách:

- @TestPropertySource
- Thuộc tính properties của @SpringBootTest
- @DynamicPropertySource
- File cấu hình theo profile như application-test.yml
- Property được khai báo trong configuration class hoặc Environment

Các nguồn property được dùng để tạo Environment khi context khởi động. Nếu khai báo test khác nhau, Spring có thể cần tạo context khác nhau để bảo đảm mỗi test nhận đúng giá trị cấu hình.

### Inline properties trong @TestPropertySource

Ví dụ:

~~~java
@SpringJUnitConfig(PaymentConfiguration.class)
@TestPropertySource(properties = {
        "payment.mode=stub",
        "payment.timeout=2s"
})
class StubPaymentConfigurationTest {
}
~~~

Một class khác khai báo:

~~~java
@SpringJUnitConfig(PaymentConfiguration.class)
@TestPropertySource(properties = {
        "payment.mode=sandbox",
        "payment.timeout=2s"
})
class SandboxPaymentConfigurationTest {
}
~~~

Hai test có cùng lớp cấu hình nhưng property inline khác nhau. Kết quả cấu hình đã hợp nhất khác nhau nên chúng có thể tạo hai cache entry riêng.

Điều này hợp lý nếu hai class cần xác nhận hai implementation hoặc hai chế độ hoạt động khác nhau. Nếu nhiều class chỉ cần cùng một bộ property, hãy dùng chung một annotation cấu hình hoặc một lớp test base để các khai báo nhất quán.

### Properties trong @SpringBootTest

Spring Boot cho phép khai báo property trực tiếp:

~~~java
@SpringBootTest(properties = {
        "feature.invoice.enabled=true",
        "payment.mode=stub"
})
class InvoiceFeatureTest {
}
~~~

Các giá trị này là một phần của cấu hình test. Nếu một test class khác dùng payment.mode=sandbox hoặc thay đổi feature.invoice.enabled, nó có thể cần context riêng.

Hãy tránh khai báo cùng một bộ property bằng nhiều cách khác nhau giữa các class. Ví dụ, một class dùng @SpringBootTest(properties=...), class khác dùng file property riêng dù nội dung tương đương. Các metadata nguồn có thể khác nhau và làm giảm khả năng tái sử dụng cache.

### File trong @TestPropertySource

Có thể tải property từ file:

~~~java
@SpringJUnitConfig(ReportConfiguration.class)
@TestPropertySource(locations = "classpath:/report-test.properties")
class ReportServiceTest {
}
~~~

Nếu nhiều class cùng sử dụng file này và các cấu hình khác tương đương, chúng có cơ hội dùng chung context.

Nếu mỗi class trỏ tới một file khác nhau, cache key có thể khác ngay cả khi hai file hiện có nội dung giống nhau. Vì vậy, gom các property dùng chung vào một nguồn có ý nghĩa và chỉ tạo file riêng khi test thật sự cần cấu hình riêng.

### Thứ tự ưu tiên property

Property test có thể ghi đè cấu hình ứng dụng. Trong Spring Test, inline properties của @TestPropertySource có độ ưu tiên cao hơn property lấy từ resource locations của chính annotation. Các test property sources cũng được ưu tiên hơn một số nguồn môi trường và cấu hình ứng dụng thông thường.

@DynamicPropertySource có độ ưu tiên cao hơn @TestPropertySource, system properties, environment variables và các nguồn @PropertySource thông thường theo cơ chế của Spring.

Khi cùng một key xuất hiện ở nhiều nguồn, hãy xác định nguồn nào đang thắng trước khi kết luận vì sao bean được tạo với giá trị không mong đợi. Có thể kiểm tra Environment trực tiếp trong test nếu cần xác nhận cấu hình đã được nạp.

Không nên khai báo cùng một key ở quá nhiều nơi. Một property có một nguồn sở hữu rõ ràng sẽ giúp test dễ hiểu và tránh tạo ra những biến thể cấu hình không cần thiết.

## 4. Active profiles và việc tạo context riêng

Profile quyết định nhóm bean hoặc cấu hình nào được kích hoạt. @ActiveProfiles khai báo profile mà Spring TestContext sử dụng khi tạo context cho test.

Ví dụ:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class CustomerServiceTest {
}
~~~

Một test khác:

~~~java
@SpringBootTest
@ActiveProfiles("integration")
class CustomerIntegrationTest {
}
~~~

Hai test dùng profile khác nhau nên có thể tạo hai context riêng. Điều này thường cần thiết vì profile có thể chọn datasource, message broker, payment gateway hoặc implementation khác.

### Nhiều profile

Có thể khai báo nhiều profile:

~~~java
@SpringBootTest
@ActiveProfiles({"test", "stub-payment"})
class PaymentServiceTest {
}
~~~

Spring kích hoạt các profile được khai báo. Các profile này ảnh hưởng đến bean có @Profile, property file tương ứng và các điều kiện cấu hình khác.

Nếu nhiều test cần cùng một tập profile, hãy dùng một cấu hình chung để tránh những khác biệt nhỏ do khai báo không thống nhất.

### Kế thừa profile

@ActiveProfiles có thể được kế thừa từ lớp cha. Theo mặc định, profile của lớp con được hợp nhất với profile được khai báo ở lớp cha.

~~~java
@SpringBootTest
@ActiveProfiles("test")
abstract class BaseIntegrationTest {
}

@ActiveProfiles("stub-payment")
class PaymentServiceTest extends BaseIntegrationTest {
}
~~~

Lớp con có thể chạy với cả test và stub-payment.

Nếu muốn lớp con thay thế hoàn toàn profile của lớp cha, dùng inheritProfiles = false:

~~~java
@ActiveProfiles(
        profiles = "integration",
        inheritProfiles = false
)
class RealPaymentIntegrationTest extends BaseIntegrationTest {
}
~~~

Kết quả profile đã hợp nhất ảnh hưởng đến cache key. Vì vậy, hai lớp con kế thừa cùng base class nhưng chủ động chọn profile khác nhau có thể tạo hai context.

Hãy dùng profile để mô tả môi trường hoặc nhóm bean cần bật. Tránh tạo một profile riêng cho từng test method nếu các method chỉ khác dữ liệu đầu vào; dữ liệu nghiệp vụ nên được chuẩn bị trong test thay vì biến thành một cấu hình ApplicationContext mới.

### Profile mặc định và hệ thống

Khi test không khai báo @ActiveProfiles, Spring có thể dùng profile mặc định của Environment. Khi dùng @ActiveProfiles, Spring Test quản lý danh sách profile được chỉ định theo annotation hoặc resolver.

Nếu một dự án dựa vào spring.profiles.active từ JVM hoặc môi trường chạy, hãy xác định rõ cơ chế đó có được test loader sử dụng như mong muốn không. Để test tái lập được, khai báo profile cần thiết ngay trong test hoặc cấu hình chung thay vì phụ thuộc ngầm vào máy chạy.

## 5. Bean override và tác động tới cache

Trong nhiều test, một bean được thay bằng mock, spy hoặc implementation dành riêng cho test. Spring Test gọi những khai báo đó là bean overrides.

Với Spring Framework 6.2 trở lên, có thể sử dụng:

- @MockitoBean để thay một bean bằng Mockito mock.
- @MockitoSpyBean để bọc bean hiện có bằng Mockito spy.
- @TestBean để thay bean bằng một instance do phương thức factory tĩnh cung cấp.

Các khai báo override được xử lý trong quá trình xây dựng context và tham gia vào context customizers. Vì vậy, hai test class có tập bean override khác nhau có thể cần các cache key khác nhau.

### @MockitoBean

Ví dụ:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;
}
~~~

Spring tạo mock cho bean OrderService trong context test và inject mock đó vào controller.

Một class khác có thể dùng cùng controller slice và cùng override:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;
}
~~~

Nếu cấu hình đã hợp nhất tương đương, hai class có thể tái sử dụng cùng context. Các hành vi mock được cấu hình trong từng test method có thể được reset theo chính sách của annotation và không tự tạo một context mới.

### Override khác nhau có thể tạo cache entry khác

Ví dụ, một test thay OrderService, trong khi test khác thay cả OrderService và InventoryService:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @MockitoBean
    OrderService orderService;
}
~~~

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerWithInventoryTest {
    @MockitoBean
    OrderService orderService;

    @MockitoBean
    InventoryService inventoryService;
}
~~~

Hai tập override khác nhau nên context customizer có thể khác và cache key không giống nhau.

Nếu nhiều class cần cùng tập override, hãy dùng một annotation tổng hợp hoặc cấu hình test chung để giữ metadata nhất quán. Nếu test cần các bean thật để kiểm tra wiring hoặc profile selection, không override bean đang là đối tượng cần kiểm chứng.

### Tên bean, qualifier và lựa chọn theo kiểu

Khi có nhiều bean cùng kiểu, Spring cần xác định bean nào sẽ được thay. Có thể dùng tên hoặc qualifier:

~~~java
@MockitoBean(name = "primaryOrderService")
private OrderService orderService;
~~~

Hoặc:

~~~java
@MockitoBean
@Qualifier("primaryOrderService")
private OrderService orderService;
~~~

Tên field có thể được dùng như fallback qualifier trong một số trường hợp. Vì thế, thay đổi tên field có thể ảnh hưởng đến bean được chọn khi có nhiều candidate. Hãy khai báo qualifier rõ ràng khi ý định cần ổn định.

Các thuộc tính như bean type, tên, qualifier và chiến lược override là một phần của metadata dùng để tạo override. Nếu chúng khác nhau giữa các test, cấu hình context có thể khác.

### Chiến lược override

@MockitoBean hỗ trợ các chiến lược thay thế bean, tùy phiên bản Spring Framework:

- REPLACE_OR_CREATE: thay bean nếu có, hoặc tạo mock bean mới nếu chưa có.
- REPLACE: yêu cầu bean hiện có phải được thay.
- WRAP: bọc bean hiện có bằng spy.

Nếu test cần chứng minh production bean thật đã được cấu hình, dùng override có thể che mất chính rủi ro đó. Chọn chiến lược phù hợp với mục tiêu và tránh khai báo override rộng hơn cần thiết.

### @MockitoSpyBean

Spy bọc một bean thật để có thể quan sát hoặc stub một số phương thức trong khi giữ phần triển khai còn lại:

~~~java
@SpringBootTest
class PricingIntegrationTest {

    @MockitoSpyBean
    private PricingPolicy pricingPolicy;

    @Test
    void usesConfiguredPricingPolicy() {
        // Gọi service thật và quan sát policy được Spring quản lý.
    }
}
~~~

Spy bọc một bean hiện có phù hợp. Vì nó thay đổi cấu hình bean trong context, khai báo spy cũng có thể ảnh hưởng đến cache identity. Không nên thay cùng một bean bằng mock ở một nhóm test và spy ở nhóm khác nếu mục tiêu có thể đạt bằng một cấu hình dùng chung.

### @TestBean

@TestBean cho phép thay bean bằng một instance được tạo từ factory method tĩnh:

~~~java
@SpringBootTest
class ShippingServiceTest {

    @TestBean
    ShippingGateway shippingGateway;

    static ShippingGateway shippingGatewayTestOverride() {
        return new StubShippingGateway();
    }
}
~~~

Cách khai báo cụ thể phụ thuộc phiên bản Spring Framework và quy tắc đặt tên factory method. Khai báo bean override vẫn tham gia vào cấu hình context. Nếu nhiều test cần cùng một implementation thay thế, hãy đặt override trong cấu hình test dùng chung hoặc annotation tổng hợp.

### Khác biệt giữa khai báo mock và stubbing

Hai việc sau có tác động khác nhau:

- Khai báo @MockitoBean thay đổi cấu hình ApplicationContext và có thể tạo cache key khác.
- Gọi when(mock.method()).thenReturn(...) trong test method chỉ cấu hình hành vi mock đang có; bản thân stubbing không làm Spring tạo context mới.

Mockito mock thường được reset sau mỗi test theo chính sách mặc định của bean override. Điều này giúp context có thể được tái sử dụng mà trạng thái stubbing của test trước không rò rỉ sang test sau.

## 6. @DynamicPropertySource và giá trị động

@DynamicPropertySource đăng ký property có giá trị được cung cấp khi test cần, thường dùng với Testcontainers hoặc dịch vụ kiểm thử có cổng động.

~~~java
@SpringBootTest
@Testcontainers
class DatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
                postgres::getUsername);
        registry.add("spring.datasource.password",
                postgres::getPassword);
    }
}
~~~

Dynamic property source method được phát hiện và đưa vào context customizer. Vì vậy, sự khác biệt về phương thức khai báo có thể tạo cấu hình context khác nhau.

Một tình huống cần chú ý là lớp cha khai báo một @DynamicPropertySource dùng chung, còn các lớp con cung cấp container hoặc giá trị động khác nhau. Nếu các lớp con dùng cùng metadata method nhưng giá trị trả về thay đổi theo lớp con, cache có thể tái sử dụng context đã được khởi tạo với giá trị cũ.

Khi dynamic values thực sự khác nhau giữa các subclass, hãy tổ chức context để mỗi giá trị cần thiết có cấu hình riêng. Có thể dùng các method hoặc cấu hình riêng để tạo cache key khác nhau, hoặc dùng @DirtiesContext khi cần loại context cũ khỏi cache sau mỗi lớp. Chỉ dùng @DirtiesContext khi giá trị động thay đổi khiến context đã cache không còn phù hợp.

Không giả định giá trị được supplier trả về luôn được so sánh như một property literal trong cache key. Context customizer và metadata của phương thức dynamic property mới là phần quan trọng trong quá trình nhận diện cấu hình. Hãy đặc biệt chú ý khi một phương thức kế thừa có thể trả về các giá trị khác nhau giữa các lớp con.

## 7. Kế thừa metadata và cách hợp nhất cấu hình

Test class có thể kế thừa từ base class để dùng chung cấu hình. Spring TestContext hỗ trợ kế thừa và hợp nhất nhiều annotation.

Ví dụ:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "feature.audit.enabled=true",
        "payment.mode=stub"
})
abstract class BaseApplicationTest {
}
~~~

Các lớp con dùng chung cấu hình:

~~~java
class AuditServiceTest extends BaseApplicationTest {
}

class PaymentServiceTest extends BaseApplicationTest {
}
~~~

Nếu không thêm cấu hình khác, hai class có thể sử dụng cùng cache entry.

Lớp con có thể thêm property:

~~~java
@TestPropertySource(properties = "feature.audit.verbose=true")
class VerboseAuditServiceTest extends BaseApplicationTest {
}
~~~

Khi property được kế thừa và hợp nhất, lớp con có cấu hình đã hợp nhất khác với base class, nên có thể tạo context riêng.

### Tắt kế thừa property locations hoặc properties

@TestPropertySource hỗ trợ:

- inheritLocations: có kế thừa resource locations từ lớp cha không.
- inheritProperties: có kế thừa inline properties từ lớp cha không.

Ví dụ:

~~~java
@TestPropertySource(
        properties = "payment.mode=sandbox",
        inheritProperties = false
)
class SandboxPaymentTest extends BaseApplicationTest {
}
~~~

Khi inheritProperties = false, inline properties của lớp cha không được hợp nhất vào lớp con. Điều này thay đổi cấu hình đã hợp nhất và có thể làm cache key khác.

Tương tự, inheritLocations = false có thể được dùng khi lớp con cần thay thế danh sách file property được kế thừa.

### Profile inheritance

@ActiveProfiles có thuộc tính inheritProfiles. Mặc định là kế thừa và hợp nhất profile từ superclass. Khi đặt false, lớp con dùng profile được khai báo riêng.

~~~java
@ActiveProfiles(
        profiles = "production-like",
        inheritProfiles = false
)
class ProductionLikeTest extends BaseApplicationTest {
}
~~~

Profile khác nhau có thể kích hoạt bean và property source khác nhau, vì vậy thường cần context riêng.

### Tránh base class quá nhiều biến thể

Một base class với nhiều subclass, mỗi lớp con thay profile, property, import và bean override theo cách khác nhau có thể tạo nhiều cache entry. Base class nên chứa phần cấu hình thật sự dùng chung. Các biến thể cần thiết nên được đặt rõ trong annotation hoặc cấu hình riêng để người đọc hiểu vì sao context phải khác.

## 8. Vì sao cache bị phân mảnh?

Cache bị phân mảnh khi suite có nhiều cấu hình context gần giống nhau nhưng khác ở một hoặc nhiều thành phần của cache key.

Ví dụ:

| Test class | Profile | Property | Bean override | Khả năng cache |
|---|---|---|---|---|
| OrderMvcTest | test | payment.mode=stub | OrderService mock | Context A |
| OrderMvcValidationTest | test | payment.mode=stub | OrderService mock | Có thể dùng Context A |
| OrderMvcSandboxTest | test | payment.mode=sandbox | OrderService mock | Context khác |
| OrderMvcWithInventoryTest | test | payment.mode=stub | OrderService và Inventory mock | Context khác |
| OrderIntegrationTest | integration | database thật | Không override repository | Context khác |

Không phải mọi context riêng đều là lãng phí. Nếu profile hoặc bean override phản ánh một môi trường thực sự khác, context riêng là cần thiết. Vấn đề xuất hiện khi test vô tình tạo ra nhiều cấu hình tương đương về ý nghĩa nhưng khác metadata.

### Những nguyên nhân phổ biến

**Property inline khác nhau:** một class đặt timeout 2 giây, class khác đặt 2000ms dù cấu hình thực tế tương đương. Khai báo khác nhau có thể tạo cache key khác.

**Nhiều file property:** mỗi class có một file test riêng chứa cùng bộ giá trị, khiến location metadata khác nhau.

**Profile không thống nhất:** một số class dùng test, class khác dùng test-local dù chúng không cần môi trường khác nhau.

**Bean override khác nhau:** các class mock những tập bean khác nhau hoặc dùng qualifier/bean name khác nhau.

**Import configuration không đồng nhất:** cùng mục tiêu test nhưng một số class import thêm cấu hình không cần thiết.

**Dynamic property source:** các method khai báo hoặc giá trị động thay đổi giữa các lớp con có thể làm context không còn phù hợp để tái sử dụng.

**@DirtiesContext quá thường xuyên:** context bị loại khỏi cache sau test hoặc class dù cấu hình có thể dùng lại.

**Quá nhiều cấu hình độc lập:** test suite tạo nhiều biến thể profile/property chỉ để thay dữ liệu cho từng scenario.

### Cache key không dựa trên tên test class

Hai test class khác tên vẫn có thể dùng chung context. Đây là lý do việc gom cấu hình chung vào base class hoặc annotation tổng hợp có thể cải thiện cache reuse.

Ngược lại, cùng một class test có thể tạo nhiều context trong các lần chạy khác nhau nếu cấu hình, profile hoặc property được thay đổi theo môi trường chạy. Việc đổi tên class thường không giải quyết được phân mảnh; cần xem metadata cấu hình thực tế.

## 9. @DirtiesContext và vòng đời cache

@DirtiesContext đánh dấu ApplicationContext là không còn phù hợp để dùng lại. Spring đóng context và loại nó khỏi cache theo chế độ được khai báo.

Ví dụ:

~~~java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ModifiesSharedBeanStateTest {
}
~~~

Một số chế độ thường gặp:

| Chế độ | Thời điểm loại context |
|---|---|
| ClassMode.BEFORE_CLASS | Trước khi test class chạy |
| ClassMode.AFTER_CLASS | Sau khi test class hoàn tất |
| MethodMode.BEFORE_METHOD | Trước mỗi test method |
| MethodMode.AFTER_METHOD | Sau mỗi test method |

ClassMode và MethodMode là hai enum riêng của annotation. Hãy dùng đúng loại mode tương ứng với phạm vi muốn làm mới.

@DirtiesContext không phải thành phần tạo cache key. Nó là chỉ thị quản lý vòng đời, khiến một cache entry bị loại bỏ và context có thể phải tạo lại.

Nếu một test chỉ thay đổi dữ liệu database, hãy ưu tiên transaction rollback hoặc cleanup dữ liệu. Nếu test chỉ thay đổi stubbing của @MockitoBean, cơ chế reset mock thường đã xử lý việc đó. Chỉ dùng @DirtiesContext khi trạng thái hoặc cấu trúc context thực sự bị thay đổi và không thể khôi phục an toàn.

## 10. Kích thước cache, LRU và phạm vi JVM

Spring TestContext cache là cache tĩnh trong tiến trình JVM. Các test chạy trong cùng JVM có thể dùng chung context cache. Nếu build tool chia test sang nhiều fork JVM, mỗi tiến trình có cache riêng; context đã tạo ở fork này không tự động được dùng ở fork khác.

Mặc định, cache có kích thước tối đa 32 context. Khi vượt giới hạn, Spring sử dụng chính sách LRU (Least Recently Used) để loại context ít được dùng gần đây nhất.

Có thể thay đổi giới hạn bằng system property:

~~~text
spring.test.context.cache.maxSize=64
~~~

Tăng kích thước cache có thể giảm số lần tạo lại context nếu suite có nhiều cấu hình thực sự cần dùng. Tuy nhiên, mỗi context có thể giữ nhiều bean, connection pool và tài nguyên, nên tăng quá cao có thể làm tăng mức sử dụng bộ nhớ.

Hãy giải quyết các cấu hình trùng lặp trước khi chỉ tăng maxSize. Một suite có nhiều biến thể không cần thiết vẫn tiêu tốn thời gian và bộ nhớ dù cache lớn hơn.

### Fork JVM và cache reuse

Nếu Gradle hoặc Maven chạy test trong nhiều fork, mỗi fork có cache riêng. Ví dụ, hai test class có cùng cấu hình nhưng chạy ở hai JVM khác nhau sẽ khởi tạo context riêng trong mỗi JVM.

Điều này có thể làm thời gian chạy tăng dù cache key giống nhau. Khi tối ưu suite, cần xem cả số context khác nhau lẫn cách build tool phân phối test.

Không nhất thiết phải tắt fork để đạt cache reuse. Việc chọn số fork là quyết định cân bằng giữa song song, thời gian chạy, bộ nhớ và khả năng cô lập.

## 11. Quan sát cache hit và cache miss

Spring TestContext Framework có thể ghi thống kê cache. Bật log DEBUG cho logger:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Trong log, có thể quan sát các thông tin như:

- Số lần cache hit.
- Số lần cache miss.
- Kích thước cache hiện tại.
- Số context đang được giữ.
- Thống kê eviction.

Nếu số lần miss tăng nhanh trong khi nhiều test có vẻ dùng cùng cấu hình, hãy tìm các annotation hoặc metadata khác nhau giữa chúng.

Có thể bật log trong cấu hình test:

~~~java
@SpringBootTest(properties = {
        "logging.level.org.springframework.test.context.cache=DEBUG"
})
class ContextCacheDiagnosticsTest {
}
~~~

Nếu thêm property logging vào một số test class mà không thống nhất, chính property đó cũng có thể tạo cấu hình khác và ảnh hưởng cache. Trong một lần chẩn đoán suite, ưu tiên cấu hình logging chung cho tiến trình test hoặc thiết lập logging từ build tool.

### Đọc thống kê theo cách thực tế

- **Cache hit tăng:** context được tái sử dụng; đây là dấu hiệu tốt khi test thực sự dùng chung cấu hình.
- **Cache miss tăng:** Spring phải tạo context mới; kiểm tra xem đó có phải cấu hình khác cần thiết hay do khai báo không thống nhất.
- **Cache size chạm giới hạn:** có thể có eviction khi số cấu hình khác nhau vượt maxSize.
- **Miss sau eviction:** context có thể đã bị loại khỏi cache vì LRU và phải tạo lại.
- **Miss sau @DirtiesContext:** có thể là hành vi dự kiến do test yêu cầu đóng context.

Không nên chỉ tối ưu tỷ lệ hit. Nếu test cần hai profile hoặc hai tập bean override khác nhau để kiểm chứng hai cấu hình, hai context riêng là bằng chứng đúng.

## 12. Cách giảm phân mảnh cache

### Dùng chung cấu hình property thật sự giống nhau

Nếu nhiều test cần cùng profile và property, gom chúng vào một base class hoặc composed annotation.

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "payment.mode=stub",
        "feature.audit.enabled=true"
})
abstract class BaseServiceIntegrationTest {
}
~~~

Các lớp con chỉ thêm cấu hình riêng khi rủi ro thực sự khác.

### Tạo composed annotation cho nhóm test

Có thể định nghĩa annotation dùng chung:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "payment.mode=stub"
})
@interface StubPaymentIntegrationTest {
}
~~~

Sau đó:

~~~java
@StubPaymentIntegrationTest
class OrderPaymentTest {
}

@StubPaymentIntegrationTest
class RefundPaymentTest {
}
~~~

Việc này làm metadata dễ nhất quán và giảm lỗi một class quên khai báo property hoặc profile chung.

### Dùng bean override giống nhau giữa các class

Nếu nhiều test cần mock cùng bean, khai báo override theo cùng kiểu, tên và qualifier. Có thể dùng annotation tổng hợp cho nhóm controller test:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@WebMvcTest
@MockitoBean(types = {
        OrderService.class,
        CustomerService.class
})
@interface OrderMvcTest {
}
~~~

Cú pháp thuộc tính type-level của @MockitoBean phụ thuộc Spring Framework version. Hãy kiểm tra Javadoc phiên bản dự án trước khi dùng annotation tổng hợp. Nếu phiên bản không hỗ trợ hình thức đó, đặt các khai báo override trong một cấu trúc dùng chung phù hợp.

### Không tạo profile cho từng scenario

Nếu test chỉ cần kiểm tra một đầu vào khác nhau, hãy truyền dữ liệu vào method hoặc cấu hình mock. Không tạo profile mới chỉ để bật một giá trị cho một test case.

Profile nên mô tả môi trường hoặc tập bean có ý nghĩa, chẳng hạn test, integration, stub-payment. Dữ liệu cụ thể như customer ID, giá tiền hoặc quantity nên nằm trong fixture.

### Giữ property source ổn định

Dùng chung file property khi nội dung thực sự giống nhau. Tránh tạo nhiều file riêng chỉ vì tên test khác nhau. Với property inline, giữ cách biểu diễn thống nhất để tránh các cấu hình gần tương đương nhưng metadata khác.

### Hạn chế @DirtiesContext

Trước khi đánh dấu context dirty, xem có thể reset state bằng @AfterEach, transaction rollback hoặc cơ chế reset mock hay không. Context chỉ nên bị loại khi nó thực sự không còn an toàn để tái sử dụng.

### Không override bean đang cần kiểm chứng

Nếu test muốn xác nhận profile chọn đúng PaymentGateway, hãy để Spring tạo PaymentGateway thật. Dùng mock ở test khác khi cần cô lập service. Việc mock bean đang kiểm tra có thể khiến test xanh mà không chứng minh được cấu hình.

## 13. Ví dụ: phân tích hai test class dùng chung context

Giả sử hai class sau cùng kiểm tra service trong môi trường test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "payment.mode=stub")
class OrderServiceIntegrationTest {
}
~~~

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "payment.mode=stub")
class RefundServiceIntegrationTest {
}
~~~

Nếu các cấu hình khác như classes, initializer, dynamic property methods và bean overrides cũng tương đương, hai class có thể dùng chung ApplicationContext.

Giờ class thứ hai được thay đổi:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = "payment.mode=sandbox")
class RefundServiceIntegrationTest {
}
~~~

Property đã khác. Spring cần context với Environment phù hợp cho sandbox mode. Một cache entry riêng là hợp lý.

Nếu class thứ hai chỉ cần kiểm tra một dữ liệu refund khác nhưng vẫn dùng stub payment, hãy giữ property chung và chuẩn bị dữ liệu trong test. Khi đó, context có thể được tái sử dụng.

### Ví dụ: khác biệt bean override

~~~java
@SpringBootTest
class OrderServiceTest {
    @MockitoBean
    PaymentGateway paymentGateway;
}
~~~

~~~java
@SpringBootTest
class RefundServiceTest {
    @MockitoBean
    PaymentGateway paymentGateway;

    @MockitoBean
    NotificationClient notificationClient;
}
~~~

Class thứ hai có thêm override. Context customizer phản ánh tập bean override khác nên cache key có thể khác.

Nếu cả hai class đều cần mock hai bean, hãy khai báo cùng tập override. Nếu OrderServiceTest không dùng NotificationClient và bean thật của nó có thể khởi tạo an toàn, không cần thêm mock chỉ để hai class giống nhau. Mục tiêu là giữ cấu hình đúng với test và chia sẻ khi thực sự tương đương.

## 14. Một số lưu ý khi chạy song song

Spring context cache được chia sẻ trong JVM, vì vậy nhiều test có thể dùng chung context khi chạy song song. Việc tái sử dụng context không có nghĩa mọi bean bên trong đều an toàn khi nhiều test thao tác đồng thời.

Hãy chú ý:

- Bean singleton có mutable state có thể bị test khác thay đổi.
- Mock bean được chia sẻ trong context cần reset đúng và không nên bị nhiều test cấu hình đồng thời theo cách xung đột.
- Database và external resources phải có dữ liệu cô lập theo test.
- Một test dùng @DirtiesContext có thể đóng context đang được test khác sử dụng nếu việc chạy song song không được tổ chức phù hợp.
- Container hoặc dynamic resource dùng chung cần có lifecycle và property ổn định.

Nếu suite bật parallel execution, tránh thiết kế test dựa vào một bean mutable dùng chung. Cân nhắc tắt song song cho nhóm test có tài nguyên dùng chung không thể cô lập, hoặc dùng context/resource riêng khi rủi ro yêu cầu.

## 15. Quy trình điều tra một suite có nhiều context

Khi thời gian chạy test tăng do nhiều lần khởi tạo ApplicationContext, có thể làm theo trình tự:

1. Bật DEBUG logging cho org.springframework.test.context.cache.
2. Xác định thời điểm cache size tăng và số lần miss tăng.
3. Nhóm các test class theo loại context: MVC, JPA, Boot integration hoặc context tùy chỉnh.
4. So sánh @ActiveProfiles giữa các class.
5. So sánh @TestPropertySource locations và inline properties.
6. So sánh @SpringBootTest(properties=...) và các property source khác.
7. So sánh @MockitoBean, @MockitoSpyBean, @TestBean, bean name và qualifier.
8. Kiểm tra @DynamicPropertySource và các subclass có giá trị động khác nhau.
9. Tìm các khai báo @DirtiesContext và lý do chúng cần thiết.
10. Kiểm tra build tool có chia test sang nhiều JVM fork hay không.
11. Gom cấu hình thật sự giống nhau vào annotation hoặc base class dùng chung.
12. Chạy lại suite và quan sát cache hit/miss để xác nhận thay đổi có tác dụng.

Khi điều tra, không nên xóa mọi bean override hoặc profile chỉ để tăng hit count. Trước hết hãy xác định chúng có đại diện cho một rủi ro cấu hình riêng hay không.

## 16. Checklist thiết kế property, profile và bean override

Trước khi thêm cấu hình cho một test class, hãy xác định:

- Property này có thực sự khác với cấu hình chung không?
- Profile này mô tả một môi trường hoặc nhóm bean riêng không?
- Bean đang bị override có nằm ngoài rủi ro cần kiểm chứng không?
- Các test khác có thể dùng cùng tập bean override không?
- File property riêng có cần thiết không?
- Dynamic property có thể thay đổi giữa các lớp con trong khi context được cache không?
- Có thể reset state mà không phải đóng ApplicationContext không?
- Nếu context khác nhau, sự khác biệt đó có chủ đích và có thể giải thích không?

Một cấu hình riêng là hợp lý khi nó kiểm chứng một biến thể ứng dụng có ý nghĩa. Phân mảnh cache cần xử lý khi các biến thể chỉ xuất hiện do khai báo không thống nhất hoặc dữ liệu test bị đưa nhầm vào cấu hình context.

## Kết luận

Spring TestContext tái sử dụng ApplicationContext dựa trên cache key được tạo từ cấu hình đã hợp nhất. Property sources, active profiles, dynamic property methods và bean overrides đều có thể làm cache key khác nhau. Khi nhiều test class dùng cùng cấu hình, hãy chuẩn hóa annotation, profile, property và tập override để tận dụng cache. Khi test cần một môi trường hoặc tập bean khác, context riêng là cần thiết. Theo dõi cache hit/miss, hiểu tác động của @DirtiesContext và cách build tool chia JVM sẽ giúp tìm đúng nguyên nhân khiến suite khởi tạo quá nhiều context.

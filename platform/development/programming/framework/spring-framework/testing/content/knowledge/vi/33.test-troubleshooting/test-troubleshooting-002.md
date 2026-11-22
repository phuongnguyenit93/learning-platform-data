# Thiếu bean, trùng bean hoặc thiếu dependency kiểm thử

## Ba nhóm lỗi thường bị nhầm lẫn

Khi Spring tạo ApplicationContext cho một bài kiểm thử, framework phải tìm các bean cần thiết, chọn đúng bean để inject và khởi tạo được toàn bộ dependency của chúng. Một test có thể thất bại ngay khi context khởi động dù method kiểm thử chưa chạy.

Những thông báo như NoSuchBeanDefinitionException, NoUniqueBeanDefinitionException, UnsatisfiedDependencyException hoặc BeanDefinitionOverrideException thường được gom chung thành lỗi cấu hình Spring. Tuy nhiên, chúng mô tả những vấn đề khác nhau:

| Nhóm lỗi | Ý nghĩa | Dấu hiệu thường gặp |
| --- | --- | --- |
| Thiếu bean | Không có bean phù hợp với dependency cần inject | NoSuchBeanDefinitionException |
| Trùng bean theo kiểu | Có nhiều bean phù hợp nhưng Spring không biết chọn bean nào | NoUniqueBeanDefinitionException |
| Trùng tên bean | Hai định nghĩa cùng đăng ký một bean name trong context | BeanDefinitionOverrideException hoặc lỗi đăng ký definition |
| Thiếu dependency của bean | Bean đã được tìm thấy nhưng một dependency bên trong nó không thể được tạo | UnsatisfiedDependencyException, thường có root cause khác |
| Thiếu thư viện kiểm thử | Class hoặc API cần cho test không có trên test runtime classpath, hoặc version không tương thích | ClassNotFoundException, NoClassDefFoundError, NoSuchMethodError |

Việc xác định đúng nhóm lỗi giúp chọn cách sửa phù hợp. Thêm một mock bean có thể giải quyết dependency của controller trong MVC slice, nhưng không sửa được lỗi thiếu thư viện trên classpath. Thêm @Primary có thể giải quyết lựa chọn giữa hai bean cùng kiểu, nhưng không xử lý hai definition trùng tên.

## Hiểu chuỗi tạo ApplicationContext

Khi test dùng Spring TestContext hoặc Spring Boot test support, framework tạo ApplicationContext từ các cấu hình và customizer được khai báo. Quá trình này gồm các bước chính:

1. Tìm cấu hình gốc và cấu hình test được chỉ định.
2. Đọc component scan, @Import, auto-configuration, profile và điều kiện cấu hình.
3. Đăng ký bean definitions từ configuration class, component và factory method.
4. Áp dụng các bean override hoặc mock bean được khai báo cho test.
5. Khởi tạo các singleton và resolve constructor, field hoặc method dependencies.
6. Hoàn tất context rồi mới chạy test method.

Lỗi ở các bước đầu thường là vấn đề cấu hình hoặc phạm vi component scan. Lỗi khi resolve dependency thường là thiếu bean hoặc nhiều bean cùng phù hợp. Lỗi trong quá trình khởi tạo một bean có thể đến từ dependency sâu hơn, cấu hình sai hoặc code khởi tạo của chính bean đó.

Một test slice như @WebMvcTest cố ý chỉ nạp một phần ApplicationContext. Việc một service không xuất hiện trong slice có thể là hành vi đúng theo thiết kế của slice, không phải lỗi component scan của toàn ứng dụng.

## Chẩn đoán bean bị thiếu

### NoSuchBeanDefinitionException

Thông báo này có nghĩa Spring cần một bean theo type hoặc qualifier cụ thể nhưng không tìm được definition phù hợp trong context hiện tại.

Ví dụ controller cần một service:

~~~java
@RestController
class OrderController {

    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }
}
~~~

Nếu test dùng @WebMvcTest(OrderController.class), Spring dựng MVC slice và đưa controller vào context. Service nghiệp vụ thường không được tạo như trong full application context, vì slice tập trung vào web layer. Kết quả có thể là lỗi không tìm thấy OrderService.

Nếu mục tiêu là kiểm thử HTTP contract của controller và cô lập service, cung cấp một mock bean:

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;
}
~~~

@MockitoBean là annotation bean override của Spring Framework 6.2 trở lên. Với phiên bản Spring Boot cũ hơn, dự án có thể đang dùng @MockBean từ spring-boot-test. Hãy chọn API tương thích với phiên bản Spring Framework và Spring Boot thực tế của dự án.

Nếu mục tiêu là kiểm tra service thật cùng các dependency của nó, không nên mock OrderService. Hãy dùng test configuration phù hợp hoặc một integration test với context chứa service và những dependency cần thiết.

### Kiểm tra component scan và package cấu hình

Một bean có thể bị thiếu vì lớp cấu hình gốc không scan tới package chứa component. Spring Boot thường tìm lớp cấu hình chính có @SpringBootApplication từ package của lớp đó xuống các package con.

Ví dụ cấu trúc:

~~~text
com.example
  Application.java
  orders
    OrderService.java
  testsupport
    TestConfiguration.java
~~~

Nếu Application nằm trong package con như com.example.bootstrap còn OrderService nằm ngoài nhánh package được scan, component có thể không được phát hiện. Khi đó cần đặt lớp cấu hình gốc ở package cha hợp lý hoặc khai báo scanBasePackages có chủ đích.

Không nên thêm component scan rộng tùy tiện trong test để chữa mọi lỗi thiếu bean. Scan rộng có thể kéo thêm adapter, client hoặc cấu hình production không thuộc phạm vi bài test, khiến context khó kiểm soát và test trở nên phụ thuộc nhiều hơn.

### Kiểm tra profile và điều kiện cấu hình

Bean có thể chỉ được đăng ký khi profile hoặc property phù hợp:

~~~java
@Configuration
@Profile("integration")
class IntegrationClientConfiguration {

    @Bean
    ExternalCatalogClient externalCatalogClient() {
        return new ExternalCatalogClient();
    }
}
~~~

Nếu test không bật profile integration, bean trên không xuất hiện. Có thể bật profile trong test:

~~~java
@ActiveProfiles("integration")
@SpringBootTest
class CatalogIntegrationTests {
}
~~~

Tương tự, @ConditionalOnProperty, @ConditionalOnClass, @ConditionalOnMissingBean và các điều kiện auto-configuration có thể khiến bean không được đăng ký. Khi đó hãy kiểm tra property, classpath và điều kiện thực tế. Đừng tạo thêm một bean cùng chức năng trước khi hiểu tại sao cấu hình gốc không kích hoạt.

### Dùng @Import khi cần thêm cấu hình rõ ràng

Nếu test cần một configuration class hoặc component cụ thể, @Import giúp đưa nó vào context mà không cần mở rộng component scan toàn cục:

~~~java
@SpringBootTest
@Import(PartnerClientTestConfiguration.class)
class PartnerIntegrationTests {
}
~~~

Đây là cách phù hợp khi một nhóm test cần thêm bean hỗ trợ hoặc adapter cụ thể. Hãy đảm bảo configuration được import không vô tình kéo theo cấu hình production cần credential hoặc hệ thống bên ngoài không có trong môi trường test.

## Chẩn đoán nhiều bean cùng kiểu

### NoUniqueBeanDefinitionException

Lỗi này xuất hiện khi một dependency yêu cầu một type nhưng có nhiều bean cùng assignable với type đó. Ví dụ ứng dụng có hai PaymentGateway:

~~~java
interface PaymentGateway {
    PaymentResult charge(PaymentRequest request);
}

@Component
class CardPaymentGateway implements PaymentGateway {
    // ...
}

@Component
class BankTransferGateway implements PaymentGateway {
    // ...
}
~~~

Nếu service inject theo interface:

~~~java
class PaymentService {

    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Spring không có đủ thông tin để chọn CardPaymentGateway hay BankTransferGateway. Có ba cách phổ biến để giải quyết, tùy ý nghĩa của dependency.

### Dùng @Qualifier khi consumer cần một implementation cụ thể

Đặt qualifier tại bean definition:

~~~java
@Component
@Qualifier("card")
class CardPaymentGateway implements PaymentGateway {
    // ...
}
~~~

Consumer khai báo rõ lựa chọn:

~~~java
class PaymentService {

    private final PaymentGateway gateway;

    PaymentService(@Qualifier("card") PaymentGateway gateway) {
        this.gateway = gateway;
    }
}
~~~

Qualifier thích hợp khi tên hoặc vai trò của implementation là một phần của cấu hình. Có thể dùng qualifier tự định nghĩa thay vì string nếu muốn type-safe hơn.

### Dùng @Primary khi có một implementation mặc định

Nếu một bean nên được chọn khi consumer không chỉ định qualifier, đánh dấu bean đó là primary:

~~~java
@Component
@Primary
class CardPaymentGateway implements PaymentGateway {
    // ...
}
~~~

@Primary giúp Spring ưu tiên bean này trong các injection theo type khi không có qualifier cụ thể. Nó không xóa các bean còn lại và không sửa lỗi hai bean definition trùng cùng một tên.

Không dùng @Primary chỉ để làm test khởi động được nếu production thực sự cần lựa chọn theo profile hoặc cấu hình. Một primary tùy tiện có thể khiến ứng dụng chạy nhưng gọi nhầm implementation.

### Inject tất cả implementation khi nghiệp vụ cần chúng

Nếu consumer cần làm việc với nhiều gateway, khai báo collection:

~~~java
class PaymentGatewayRegistry {

    private final Map<String, PaymentGateway> gateways;

    PaymentGatewayRegistry(Map<String, PaymentGateway> gateways) {
        this.gateways = gateways;
    }

    PaymentGateway get(String name) {
        return gateways.get(name);
    }
}
~~~

Spring có thể inject List, Set hoặc Map các bean phù hợp. Với Map, key thường là bean name. Consumer chịu trách nhiệm chọn implementation theo business rule và cần xử lý trường hợp key không tồn tại.

## Chẩn đoán bean bị đăng ký trùng tên

### BeanDefinitionOverrideException

Đây là trường hợp hai bean definition cùng dùng một bean name. Ví dụ:

~~~java
@Configuration
class ProductionConfiguration {

    @Bean
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}

@TestConfiguration
class TestConfiguration {

    @Bean
    ExternalClient externalClient() {
        return new StubExternalClient();
    }
}
~~~

Cả hai factory method mặc định có bean name externalClient. Nếu cùng được import vào một context và bean overriding không được cho phép, Spring báo lỗi definition trùng tên.

Không nhầm trường hợp này với hai bean khác tên nhưng cùng type. Hai bean khác tên thường dẫn tới NoUniqueBeanDefinitionException khi inject theo type; hai definition cùng tên dẫn tới xung đột đăng ký.

### Đặt tên riêng khi thật sự cần cả hai bean

Nếu test cần cả implementation thật và stub, đặt tên rõ ràng:

~~~java
@TestConfiguration
class TestClientConfiguration {

    @Bean("stubExternalClient")
    ExternalClient stubExternalClient() {
        return new StubExternalClient();
    }
}
~~~

Sau đó inject bằng qualifier. Nếu test chỉ cần thay thế bean production, dùng cơ chế bean override của Spring Test hoặc cấu hình test có chủ đích thay vì đăng ký thêm bean trùng tên.

### Không bật bean overriding toàn cục như cách chữa mặc định

Spring Boot có property điều khiển bean definition overriding. Bật nó có thể khiến definition đăng ký sau thay thế definition trước, nhưng kết quả phụ thuộc thứ tự đăng ký và có thể che giấu xung đột cấu hình.

Chỉ bật overriding khi có lý do rõ ràng và đã xác định definition nào phải thắng. Với test, ưu tiên @MockitoBean, @TestBean, @Import hoặc cấu hình test tường minh phù hợp với phiên bản framework.

## Chọn đúng cách cung cấp test bean

Có nhiều cách thêm hoặc thay bean trong context kiểm thử. Chúng có phạm vi và mục đích khác nhau.

| Cách | Mục đích | Khi phù hợp |
| --- | --- | --- |
| @MockitoBean | Thay thế hoặc tạo bean bằng Mockito mock trong test context | Cô lập dependency của web slice hoặc integration test |
| @MockitoSpyBean | Bọc bean hiện có bằng Mockito spy | Muốn quan sát lời gọi nhưng vẫn dùng hành vi thật |
| @TestConfiguration + @Bean | Khai báo implementation hỗ trợ dành riêng cho test | Fake client, clock, adapter hoặc fixture tùy chỉnh |
| @Import | Đưa configuration hoặc component cụ thể vào context | Thêm một nhóm bean có ranh giới rõ |
| @ActiveProfiles | Bật nhóm cấu hình theo profile | Bean phụ thuộc profile |
| @SpringBootTest | Nạp application context theo cấu hình Boot | Cần kiểm tra tích hợp rộng hơn |
| @ContextConfiguration | Chỉ định cấu hình Spring TestContext | Test dùng context tối giản hoặc cấu hình Spring cụ thể |

### @TestConfiguration cho bean hỗ trợ

Ví dụ cung cấp một Clock cố định cho test:

~~~java
@TestConfiguration
class FixedTimeTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
                Instant.parse("2026-04-15T10:00:00Z"),
                ZoneOffset.UTC
        );
    }
}
~~~

Có thể import configuration này vào test:

~~~java
@SpringBootTest
@Import(FixedTimeTestConfiguration.class)
class ReservationIntegrationTests {
}
~~~

Nếu context đã có một Clock bean khác, test có thể gặp nhiều bean cùng type. Khi đó quyết định rõ test muốn thay thế bean hiện tại hay muốn giữ cả hai và inject theo qualifier. Không tạo thêm Clock rồi mong Spring tự chọn bean mới.

### Bean override theo phiên bản Spring

Trong Spring Framework 6.2 trở lên, @MockitoBean và @MockitoSpyBean là cơ chế bean override được cung cấp bởi Spring TestContext. Chúng hỗ trợ khai báo mock/spy trực tiếp trên test field hoặc type và được áp dụng trong context kiểm thử.

Các dự án Spring Boot cũ có thể đang dùng @MockBean và @SpyBean từ Spring Boot Test. Trong Spring Boot 3.4, các annotation cũ này đã được đánh dấu deprecated để chuyển dần sang API bean override của Spring Framework. Không trộn annotation từ hai thế hệ API nếu chưa kiểm tra version compatibility.

Ví dụ dùng API mới:

~~~java
@SpringBootTest
class BillingServiceTests {

    @MockitoBean
    PaymentGateway paymentGateway;
}
~~~

Nếu cần mock theo qualifier khi có nhiều bean cùng type, khai báo qualifier trên field hoặc dùng thuộc tính phù hợp của annotation ở phiên bản đang dùng. Hãy kiểm tra chính xác API có sẵn trong dependency trước khi sao chép ví dụ từ tài liệu của phiên bản mới hơn.

## Test slice không chứa toàn bộ bean của ứng dụng

Một nguồn gây hiểu nhầm phổ biến là kỳ vọng test slice có đầy đủ bean như @SpringBootTest.

### @WebMvcTest

@WebMvcTest tập trung vào Spring MVC layer: controller được chọn, MVC infrastructure, converters, validation và các thành phần web liên quan. Service, repository và client nghiệp vụ thường được mock hoặc import rõ ràng.

~~~java
@WebMvcTest(OrderController.class)
class OrderControllerTests {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    OrderService orderService;
}
~~~

Nếu controller inject thêm một collaborator không thuộc web slice, cần mock hoặc import collaborator đó. Đừng chuyển ngay sang @SpringBootTest nếu mục tiêu chỉ là kiểm tra mapping, validation và HTTP response của controller.

### @DataJpaTest

@DataJpaTest tập trung vào JPA repositories, entity mapping và database test infrastructure. Các service hoặc web controller không tự động được đưa vào context.

Nếu repository phụ thuộc custom converter, auditing configuration hoặc entity listener riêng, import cấu hình cần thiết một cách rõ ràng. Nếu test cần kiểm tra service orchestration cùng repository, dùng context phù hợp hơn thay vì giả định slice đã nạp service.

### @SpringBootTest

@SpringBootTest nạp application context theo cấu hình Spring Boot. Phạm vi rộng hơn nhưng vẫn phụ thuộc component scan, profile, condition, auto-configuration exclusions và properties của test.

Nếu một bean vẫn thiếu trong @SpringBootTest, hãy kiểm tra cấu hình gốc, package scan, profile và điều kiện tạo bean. Annotation này không bảo đảm mọi class trong repository đều được đăng ký.

### @ContextConfiguration

@ContextConfiguration cho phép chỉ định cấu hình tạo context của Spring TestContext. Nếu chỉ khai báo một cấu hình tối giản, context chỉ có những bean được cấu hình hoặc import từ đó. Đừng kỳ vọng component scan và auto-configuration của Spring Boot nếu test không bootstrap chúng.

## Thiếu dependency kiểm thử trên classpath

Không phải mọi lỗi có chữ “missing” đều là thiếu Spring bean. Nếu JVM không tìm thấy class hoặc method mà test cần, vấn đề có thể nằm ở dependency của Gradle/Maven hoặc version mismatch.

### Phân biệt lỗi classpath với lỗi ApplicationContext

| Exception hoặc dấu hiệu | Hướng kiểm tra đầu tiên |
| --- | --- |
| NoSuchBeanDefinitionException | Bean có nằm trong context và đúng type/qualifier không? |
| NoUniqueBeanDefinitionException | Có bao nhiêu bean phù hợp với type? |
| UnsatisfiedDependencyException | Đọc nested cause để tìm dependency đầu tiên không resolve được |
| BeanDefinitionOverrideException | Có hai definition cùng bean name không? |
| ClassNotFoundException | Class có trong runtime classpath không? |
| NoClassDefFoundError | Dependency có bị thiếu lúc chạy hoặc class initialization thất bại không? |
| NoSuchMethodError | Các module có dùng version không tương thích không? |
| NoSuchBeanDefinitionException cho một test extension | Test support hoặc auto-configuration có được nạp không? |

Trong Gradle, thư viện chỉ cần khi compile/run test thường phải nằm trong testImplementation hoặc testRuntimeOnly, tùy cách sử dụng. Spring Boot project thường dùng starter-test:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Nếu test dùng Testcontainers, thêm module tương ứng trong test scope:

~~~groovy
dependencies {
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
}
~~~

Version cần được quản lý đồng bộ bằng Spring Boot dependency management hoặc version catalog của dự án. Tránh tự thêm một version Spring Test khác với Spring Framework đang được Boot quản lý.

### Kiểm tra dependency tree và source set

Nếu class có trong IDE nhưng Gradle test không tìm thấy, kiểm tra dependency thuộc đúng source set và task:

~~~powershell
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Với một module cụ thể, chạy task từ module đó hoặc chỉ định project path tương ứng. Kiểm tra dependency bị exclude, version conflict và cấu hình test runtime. Không thêm thư viện vào implementation chỉ để làm test compile nếu nó chỉ cần trong test source set.

## Đọc stack trace từ ngoài vào trong

Spring thường bọc lỗi khởi tạo bean trong một exception tổng quát. Dòng đầu tiên có thể chỉ nói ApplicationContext failed to load hoặc Error creating bean, nhưng nguyên nhân thực tế thường nằm sâu hơn trong nested cause.

Ví dụ:

~~~text
Failed to load ApplicationContext
  UnsatisfiedDependencyException:
    Error creating bean with name 'orderController'
      UnsatisfiedDependencyException:
        Error creating bean with name 'orderService'
          NoSuchBeanDefinitionException:
            No qualifying bean of type 'PaymentGateway' available
~~~

Trong chuỗi này, OrderController và OrderService chỉ là những bean bị ảnh hưởng. Dependency đầu tiên không resolve được là PaymentGateway. Hãy sửa tại điểm đó thay vì thêm mock cho OrderController hoặc vô hiệu hóa toàn bộ auto-configuration.

Khi có nhiều nested exception, xác định exception sâu nhất có ý nghĩa đầu tiên, sau đó lần ngược bean đang yêu cầu dependency đó. Đọc thêm condition evaluation report nếu lỗi liên quan auto-configuration hoặc @ConditionalOn... của Spring Boot.

## Một quy trình chẩn đoán thực tế

1. Đọc exception đầu tiên và các nested cause. Phân biệt lỗi bean definition, lỗi injection, lỗi khởi tạo bean và lỗi classpath.
2. Xác định test đang dùng @WebMvcTest, @DataJpaTest, @SpringBootTest hay @ContextConfiguration. Viết ra những bean mà phạm vi đó dự kiến nạp.
3. Với bean thiếu, kiểm tra component scan, @Import, profile, conditional property và auto-configuration.
4. Với nhiều bean cùng type, kiểm tra qualifier, primary và việc consumer có cần một hay nhiều implementation.
5. Với bean name trùng, tìm các @Bean method hoặc component có cùng tên; chọn bean override hoặc tên riêng có chủ đích.
6. Với UnsatisfiedDependencyException, lần theo dependency graph tới bean hoặc class đầu tiên không tạo được.
7. Với ClassNotFoundException, NoClassDefFoundError hoặc NoSuchMethodError, kiểm tra testRuntimeClasspath và version alignment.
8. Chọn cách sửa theo mục tiêu test: mock dependency ngoài phạm vi, import test configuration, bật profile cần thiết hoặc mở rộng test context khi thật sự cần.
9. Chạy lại đúng test class hoặc method để xác nhận lỗi context đã được xử lý và assertion nghiệp vụ vẫn có ý nghĩa.

## Những cách sửa dễ che giấu nguyên nhân

### Chuyển tất cả test slice thành @SpringBootTest

Điều này có thể làm lỗi thiếu bean biến mất vì context rộng hơn, nhưng cũng khởi động nhiều thành phần không liên quan, tăng thời gian và làm test phụ thuộc hạ tầng. Giữ slice khi mục tiêu là kiểm tra một layer; chỉ dùng full context khi cần xác nhận tích hợp rộng.

### Mock mọi dependency mà không phân biệt ranh giới

Mock bean giúp cô lập một collaborator, nhưng nếu mock cả bean đang được kiểm thử hoặc các thành phần cần xác nhận cùng nhau, test chỉ chứng minh mock hoạt động. Chọn dependency ngoài phạm vi test để thay thế.

### Bật bean overriding toàn cục

Việc này có thể khiến một definition bị ghi đè theo thứ tự đăng ký, che giấu cấu hình trùng. Hãy chỉ định bean test thay thế một cách tường minh.

### Thêm component scan rộng

Scan toàn bộ package gốc có thể kéo vào các adapter và integration configuration không cần thiết. Import đúng component/configuration mà test cần thường rõ ràng hơn.

### Thêm dependency production để sửa lỗi test classpath

Nếu thư viện chỉ được dùng trong test, thêm nó vào testImplementation hoặc testRuntimeOnly. Giữ test dependency trong runtime production làm tăng classpath ứng dụng và có thể gây xung đột version.

## Kết luận về cách đọc lỗi

Thiếu bean, nhiều bean cùng type, trùng bean name và thiếu thư viện kiểm thử là những vấn đề ở các lớp khác nhau. NoSuchBeanDefinition hướng tới phạm vi context hoặc điều kiện đăng ký; NoUniqueBeanDefinition hướng tới lựa chọn giữa các candidate; BeanDefinitionOverrideException hướng tới xung đột tên; UnsatisfiedDependency yêu cầu lần theo dependency graph; còn lỗi classpath cần kiểm tra dependency và version.

Khi chẩn đoán bắt đầu từ exception gốc và ranh giới thực tế của test context, cách sửa sẽ nhỏ và đúng mục tiêu hơn: cung cấp mock cho dependency ngoài phạm vi, import cấu hình cần thiết, chọn bean bằng qualifier/primary, đổi tên definition bị xung đột hoặc bổ sung dependency đúng test scope.

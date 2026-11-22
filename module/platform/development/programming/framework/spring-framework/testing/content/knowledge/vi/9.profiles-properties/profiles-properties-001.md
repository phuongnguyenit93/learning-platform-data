# @ActiveProfiles và lựa chọn bean theo môi trường kiểm thử

Một ứng dụng Spring thường cần cấu hình khác nhau khi chạy trên máy lập trình, trong môi trường kiểm thử và khi triển khai production. Repository có thể được thay bằng fake trong test, mail client có thể ghi vào hộp thư giả lập, còn production dùng adapter kết nối dịch vụ thật. Spring Profiles cung cấp cơ chế chọn cấu hình và bean dựa trên môi trường đang hoạt động.

Trong Spring TestContext, annotation `@ActiveProfiles` khai báo profile cần kích hoạt khi tải `ApplicationContext` cho test. Annotation `@Profile` trên component, configuration class hoặc phương thức `@Bean` quyết định thành phần nào được đăng ký khi profile tương ứng đang hoạt động. Kết hợp hai annotation này, test có thể yêu cầu Spring lắp ghép đúng nhóm bean dành cho môi trường kiểm thử.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vai trò của Spring Profile và `Environment`.
- Kích hoạt profile cho test bằng `@ActiveProfiles`.
- Chọn implementation bằng `@Profile` trên component và bean factory method.
- Dùng profile expression để kết hợp điều kiện môi trường.
- Hiểu profile inheritance khi test class kế thừa test base class.
- Dùng custom `ActiveProfilesResolver` khi profile cần được xác định động.
- Phân biệt profile với property và các cơ chế conditional khác.
- Tổ chức cấu hình kiểm thử sao cho test độc lập với môi trường máy chạy.

## 1. Spring Profile giải quyết vấn đề gì?

Hãy xem một ứng dụng gửi thông báo. Khi chạy production, nó cần gửi email qua SMTP. Trong test, ta không muốn gửi email thật; thay vào đó, có thể dùng một implementation chỉ ghi nhận thông báo trong bộ nhớ.

Nếu chọn implementation bằng các câu điều kiện rải rác trong service, code nghiệp vụ sẽ phải biết ứng dụng đang chạy ở môi trường nào. Spring Profile cho phép đặt lựa chọn đó ở tầng cấu hình và dependency injection.

~~~mermaid
flowchart TD
    A["Test khởi tạo Spring TestContext"] --> B["@ActiveProfiles(test)"]
    B --> C["Environment có active profile test"]
    C --> D["Spring đánh giá @Profile trên bean"]
    D --> E["FakeEmailSender được đăng ký"]
    E --> F["Test inject EmailSender"]
    G["Production khởi động"] --> H["Profile production"]
    H --> I["SmtpEmailSender được đăng ký"]
    I --> J["Ứng dụng inject EmailSender"]
~~~

Một profile là một tên được quản lý bởi `Environment`. Ví dụ:

- `test`: cấu hình và adapter dành cho kiểm thử.
- `development`: cấu hình dùng khi lập trình.
- `staging`: cấu hình cho môi trường tiền production.
- `production`: cấu hình triển khai thật.

Tên profile do ứng dụng và đội phát triển quy ước. Spring không bắt buộc phải dùng các tên này. Quan trọng là profile phải được kích hoạt một cách có chủ đích và bean có điều kiện phải phản ánh đúng ý nghĩa của nó.

Profile thường được dùng để chọn:

- Implementation của interface, ví dụ fake repository so với repository kết nối database.
- Bean cấu hình HTTP client, mail sender hoặc message publisher.
- Configuration class cung cấp datasource hay integration adapter.
- Property file và cấu hình riêng cho môi trường.

Profile không phải một cơ chế phân quyền hay một ranh giới bảo mật. Không nên dựa vào tên profile để bảo vệ secret hoặc ngăn ứng dụng truy cập production. Credential và endpoint cần được quản lý bằng cấu hình an toàn riêng.

## 2. Kích hoạt profile cho test bằng @ActiveProfiles

`@ActiveProfiles` là annotation của Spring TestContext. Nó khai báo profile cần được kích hoạt khi framework tải `ApplicationContext` cho test class.

Ví dụ:

~~~java
@SpringJUnitConfig(ApplicationConfiguration.class)
@ActiveProfiles("test")
class NotificationServiceTest {

    @Autowired
    NotificationService notificationService;

    @Test
    void sendsNotificationUsingTestConfiguration() {
        // Kiểm tra hành vi với các bean của profile test.
    }
}
~~~

Trong ví dụ này, Spring tạo `Environment` cho context và kích hoạt profile `test`. Những bean có điều kiện `@Profile("test")` có thể được đăng ký. Các bean chỉ dành cho profile khác sẽ không được chọn.

Nếu không có active profile nào được khai báo, Spring dùng default profile. Tên mặc định ban đầu là `default`, nhưng ứng dụng có thể đổi bằng cấu hình `spring.profiles.default`. Khi test kích hoạt `test`, profile `default` không tự động được cộng thêm; chỉ những profile đang hoạt động mới quyết định các điều kiện `@Profile` tương ứng.

Có thể khai báo nhiều profile:

~~~java
@ActiveProfiles({"test", "local"})
class LocalIntegrationTest {
}
~~~

Các profile trong mảng được kích hoạt đồng thời. Nếu một bean cần một trong các profile đó, có thể dùng mảng profile trên `@Profile` hoặc expression tương ứng.

Ví dụ:

~~~java
@Component
@Profile({"test", "local"})
class LocalEmailSender implements EmailSender {
    // Implementation dùng trong test hoặc local.
}
~~~

Khi một test class có `@ActiveProfiles`, Spring TestContext sử dụng danh sách profile được khai báo để thiết lập active profiles cho context. Vì vậy, kết quả của test không nên phụ thuộc vào việc người chạy đã đặt `spring.profiles.active` trong biến môi trường hay chưa.

Nếu muốn xác định profile theo môi trường chạy thực tế, hãy dùng `ActiveProfilesResolver` hoặc cấu hình test không khai báo `@ActiveProfiles` và để môi trường cung cấp profile. Với unit và integration test cần tái lập, khai báo profile tường minh thường dễ hiểu hơn.

## 3. Chọn bean bằng @Profile

`@Profile` đặt điều kiện để Spring đăng ký một thành phần. Annotation có thể dùng trên:

- Class được phát hiện qua component scan, ví dụ `@Component`, `@Service` hoặc `@Repository`.
- Configuration class được đánh dấu `@Configuration`.
- Phương thức `@Bean` bên trong configuration class.

### Chọn implementation trên component

Giả sử ứng dụng có một interface:

~~~java
public interface EmailSender {
    void send(String recipient, String message);
}
~~~

Implementation cho test:

~~~java
@Component
@Profile("test")
public class InMemoryEmailSender implements EmailSender {

    private final List<String> sentMessages = new ArrayList<>();

    @Override
    public void send(String recipient, String message) {
        sentMessages.add(recipient + ": " + message);
    }

    public List<String> sentMessages() {
        return List.copyOf(sentMessages);
    }
}
~~~

Implementation cho production:

~~~java
@Component
@Profile("production")
public class SmtpEmailSender implements EmailSender {

    @Override
    public void send(String recipient, String message) {
        // Gửi qua SMTP client được cấu hình cho production.
    }
}
~~~

Service chỉ phụ thuộc vào interface:

~~~java
@Service
public class NotificationService {

    private final EmailSender emailSender;

    public NotificationService(EmailSender emailSender) {
        this.emailSender = emailSender;
    }

    public void notifyCustomer(String email, String message) {
        emailSender.send(email, message);
    }
}
~~~

Khi test kích hoạt profile `test`, Spring đăng ký `InMemoryEmailSender`. Khi ứng dụng chạy với profile `production`, Spring đăng ký `SmtpEmailSender`. Service không cần biết implementation cụ thể nào được chọn.

### Chọn bean qua @Bean method

Nếu muốn đặt implementation trong configuration class, có thể viết:

~~~java
@Configuration
public class EmailConfiguration {

    @Bean
    @Profile("test")
    EmailSender testEmailSender() {
        return new InMemoryEmailSender();
    }

    @Bean
    @Profile("production")
    EmailSender productionEmailSender() {
        return new SmtpEmailSender();
    }
}
~~~

Tên phương thức bean khác nhau giúp cấu hình rõ ràng. Khi mỗi lần chỉ một profile phù hợp được kích hoạt, context sẽ có một bean `EmailSender` tương ứng để inject.

Nếu hai implementation cùng được đăng ký trong một context và đều có cùng kiểu, Spring có thể báo lỗi không xác định được bean khi inject theo kiểu. Hãy thiết kế profile sao cho tập bean phù hợp là duy nhất, hoặc dùng `@Qualifier`/`@Primary` khi nhiều bean cùng tồn tại là chủ đích.

## 4. Viết test xác nhận implementation được chọn

Ta có thể kiểm tra trực tiếp loại bean Spring cung cấp. Ví dụ dùng configuration class:

~~~java
@Configuration
class EmailConfiguration {

    @Bean
    @Profile("test")
    EmailSender testEmailSender() {
        return new InMemoryEmailSender();
    }

    @Bean
    @Profile("production")
    EmailSender productionEmailSender() {
        return new SmtpEmailSender();
    }
}
~~~

Test:

~~~java
@SpringJUnitConfig(EmailConfiguration.class)
@ActiveProfiles("test")
class EmailProfileSelectionTest {

    @Autowired
    EmailSender emailSender;

    @Test
    void selectsInMemorySenderForTestProfile() {
        assertInstanceOf(InMemoryEmailSender.class, emailSender);
    }
}
~~~

Test này khởi tạo context thật nhưng chỉ với cấu hình nhỏ cần kiểm tra. `@ActiveProfiles("test")` làm điều kiện profile phù hợp; `@Profile("test")` cho phép factory method đăng ký bean. Assertion xác nhận bean được inject đúng implementation.

Có thể kiểm tra hành vi thay vì chỉ kiểm tra class:

~~~java
@Test
void recordsMessagesWithoutSendingExternalEmail() {
    assertInstanceOf(InMemoryEmailSender.class, emailSender);

    emailSender.send("ada@example.com", "Order accepted");
    InMemoryEmailSender inMemory =
        (InMemoryEmailSender) emailSender;

    assertEquals(
        List.of("ada@example.com: Order accepted"),
        inMemory.sentMessages()
    );
}
~~~

## 5. @Profile hỗ trợ biểu thức điều kiện

`@Profile` có thể nhận một hoặc nhiều tên profile. Khi truyền mảng tên profile, bean được đăng ký nếu ít nhất một profile phù hợp đang hoạt động.

Ví dụ:

~~~java
@Configuration
@Profile({"test", "development"})
class NonProductionConfiguration {
}
~~~

Cấu hình này được kích hoạt khi profile `test` hoặc `development` hoạt động.

Ngoài danh sách, Spring hỗ trợ profile expression với toán tử:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `&` | AND | `test & cloud` |
| `|` | OR | `test | local` |
| `!` | NOT | `!production` |

Ví dụ:

~~~java
@Configuration
@Profile("test & !production")
class IsolatedTestConfiguration {
}
~~~

Cấu hình chỉ phù hợp khi `test` đang hoạt động và `production` không hoạt động.

Có thể dùng expression để chọn bean cho nhiều tổ hợp môi trường:

~~~java
@Bean
@Profile("development | test")
EmailSender localEmailSender() {
    return new InMemoryEmailSender();
}
~~~

~~~java
@Bean
@Profile("production & cloud")
EmailSender cloudEmailSender() {
    return new CloudEmailSender();
}
~~~

Các expression phức tạp nên được dùng có chừng mực. Nếu điều kiện khó đọc, hãy chia cấu hình thành các nhóm rõ ràng hoặc dùng custom condition phù hợp.

## 6. Profile inheritance trong test class

Test class có thể kế thừa một base class chứa cấu hình kiểm thử chung. Mặc định, `@ActiveProfiles` có thể được kế thừa từ superclass.

Ví dụ:

~~~java
@SpringJUnitConfig(TestConfiguration.class)
@ActiveProfiles("test")
abstract class BaseSpringIntegrationTest {
}
~~~

~~~java
class OrderServiceIntegrationTest extends BaseSpringIntegrationTest {

    @Test
    void createsOrder() {
        // Context dùng profile test kế thừa.
    }
}
~~~

Nếu subclass bổ sung profile:

~~~java
@ActiveProfiles("database")
class DatabaseBackedOrderTest extends BaseSpringIntegrationTest {
}
~~~

Theo mặc định `inheritProfiles` là true, vì vậy profile từ superclass và subclass được kết hợp. Trong ví dụ này, context được yêu cầu có cả `test` và `database`.

Nếu subclass cần thay thế danh sách profile được kế thừa, hãy đặt `inheritProfiles = false`:

~~~java
@ActiveProfiles(
    profiles = "postgres",
    inheritProfiles = false
)
class PostgreSqlIntegrationTest extends BaseSpringIntegrationTest {
}
~~~

Lúc này, profile từ base class không được kế thừa cho test class này. Hãy chọn giữa kế thừa và thay thế một cách có chủ đích; nếu profile base class chứa các điều kiện thiết yếu như `test`, việc thay thế có thể khiến bean kiểm thử không còn được đăng ký.

Khi test suite có nhiều tầng kế thừa, hãy ghi rõ profile nào đến từ base class và profile nào do subclass bổ sung. Điều này giúp tránh một test bất ngờ chạy với tập bean khác mong đợi.

## 7. Dùng ActiveProfilesResolver khi profile cần xác định động

Thông thường, test nên khai báo profile cố định bằng `@ActiveProfiles("test")`. Trong một số dự án, profile cần được chọn theo một quy tắc riêng, ví dụ hệ điều hành, một system property hoặc loại test.

Spring TestContext cho phép triển khai `ActiveProfilesResolver`:

~~~java
public class TestProfileResolver implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String selected = System.getProperty(
            "test.profile",
            "test"
        );

        return new String[] { selected };
    }
}
~~~

Gắn resolver vào test:

~~~java
@SpringJUnitConfig(ApplicationConfiguration.class)
@ActiveProfiles(resolver = TestProfileResolver.class)
class EnvironmentAwareTest {
}
~~~

Resolver nhận test class và trả về mảng profile cần kích hoạt. Khi khai báo resolver, danh sách profile tĩnh trong thuộc tính `profiles` của annotation không còn là nguồn lựa chọn chính; resolver chịu trách nhiệm trả về danh sách cuối cùng.

Custom resolver hữu ích khi có quy tắc chung cho một nhóm test. Tuy nhiên, nếu resolver phụ thuộc biến môi trường của từng máy, test có thể khó tái lập và context cache có thể tạo ra nhiều cấu hình khác nhau. Hãy ưu tiên profile tường minh cho test thông thường và chỉ dùng resolver khi có nhu cầu thực tế.

## 8. Profile và profile-specific configuration trong Spring Boot

Spring Boot có thể nạp file cấu hình riêng theo profile. Ví dụ:

~~~text
src/main/resources/
  application.yml
  application-test.yml
  application-development.yml
  application-production.yml
~~~

File mặc định chứa cấu hình chung:

~~~yaml
spring:
  application:
    name: order-service

logging:
  level:
    root: INFO
~~~

File `application-test.yml` chứa cấu hình cho test:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:orders-test
    username: sa
    password:

app:
  notifications:
    enabled: false
~~~

Khi profile `test` hoạt động, Spring Boot nạp cấu hình mặc định cùng các cấu hình dành cho profile đó theo quy tắc Config Data. Test có thể kích hoạt profile bằng:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderApplicationTest {
}
~~~

Không cần đặt lại `spring.profiles.active` bên trong file `application-test.yml` để kích hoạt chính profile đó. Hãy kích hoạt profile từ môi trường khởi chạy, annotation test hoặc cơ chế activation phù hợp. Các thuộc tính điều khiển profile như `spring.profiles.active` và `spring.profiles.default` không được khai báo trong tài liệu cấu hình chỉ được kích hoạt khi một profile khác đang hoạt động.

Spring Boot cũng hỗ trợ profile group. Một profile tổng hợp có thể kích hoạt nhiều profile nhỏ:

~~~yaml
spring:
  profiles:
    group:
      integration:
        - test
        - postgres
        - messaging
~~~

Khi kích hoạt `integration`, các profile thành viên cũng được kích hoạt. Cách này hữu ích khi một nhóm integration test luôn cần cùng một tập cấu hình database và messaging.

Profile group là tính năng của Spring Boot. Với Spring Framework thuần, `Environment` và `@Profile` vẫn hoạt động, nhưng cách nạp file và các tiện ích như profile group thuộc lớp cấu hình của Boot.

## 9. Phân biệt profile với property và conditional bean

Profile là một điều kiện theo nhóm môi trường. Property là giá trị cấu hình cụ thể. Hai cơ chế có thể phối hợp nhưng không thay thế nhau.

Ví dụ profile:

~~~java
@Bean
@Profile("test")
PaymentGateway fakePaymentGateway() {
    return new FakePaymentGateway();
}
~~~

Ví dụ property trong Spring Boot:

~~~java
@Bean
@ConditionalOnProperty(
    name = "payment.gateway.enabled",
    havingValue = "true"
)
PaymentGateway paymentGateway() {
    return new HttpPaymentGateway();
}
~~~

`@ConditionalOnProperty` kiểm tra giá trị property; nó không phải annotation của Spring Framework core mà là tiện ích conditional của Spring Boot.

Một số cách chọn cấu hình:

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Chọn nhóm bean cho test hoặc production | `@Profile` |
| Bật/tắt một tính năng theo property | `@ConditionalOnProperty` |
| Chọn bean theo kiểu và qualifier | `@Qualifier`, `@Primary` |
| Điều kiện tùy biến dựa trên Environment hoặc classpath | Custom `Condition` |
| Cấu hình profile-specific trong Boot | `application-{profile}.yml` |

Không nên tạo profile mới cho từng flag nhỏ nếu đó chỉ là một property. Profile nên biểu đạt một môi trường hoặc một tập cấu hình có ý nghĩa, còn feature flag nên dùng property hoặc cơ chế quản lý tính năng.

## 10. Chọn bean duy nhất và tránh xung đột

Khi inject theo interface, Spring cần xác định bean phù hợp. Nếu profile kích hoạt nhiều implementation cùng kiểu, việc inject có thể mơ hồ.

Ví dụ hai bean cùng hoạt động:

~~~java
@Component
@Profile("test")
class FakePaymentGateway implements PaymentGateway {
}

@Component
@Profile("local")
class LocalPaymentGateway implements PaymentGateway {
}
~~~

Nếu test kích hoạt cả `test` và `local`, hai bean đều có thể được đăng ký. Khi service yêu cầu một `PaymentGateway` mà không có quy tắc ưu tiên, Spring có thể báo lỗi do có nhiều candidate.

Có một số lựa chọn:

- Thiết kế profile sao cho chỉ một implementation cho mỗi boundary được đăng ký.
- Dùng `@Primary` cho bean mặc định khi nhiều candidate là hợp lệ.
- Dùng `@Qualifier` khi consumer cần một implementation cụ thể.
- Dùng bean name rõ ràng trong cấu hình và injection point.
- Tách configuration class để mỗi môi trường có tập bean phù hợp.

Ví dụ qualifier:

~~~java
@Configuration
class GatewayConfiguration {

    @Bean
    @Profile("test")
    @Qualifier("testGateway")
    PaymentGateway testGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("production")
    @Qualifier("productionGateway")
    PaymentGateway productionGateway() {
        return new HttpPaymentGateway();
    }
}
~~~

Trong trường hợp mỗi môi trường chỉ có một bean phù hợp, qualifier thường không cần thiết. Hãy tránh thêm qualifier hoặc primary chỉ để che giấu việc nhiều profile bị kích hoạt ngoài dự kiến.

## 11. Cấu trúc test profile để không phụ thuộc máy phát triển

Một test ổn định cần tự khai báo môi trường của nó. Nếu test chỉ chạy đúng khi máy lập trình đã đặt một biến môi trường đặc biệt, kết quả có thể khác nhau trên CI hoặc máy của thành viên khác.

Một cấu trúc phổ biến:

~~~text
src/test/java/
  com/example/
    BaseIntegrationTest.java
    OrderServiceIntegrationTest.java

src/test/resources/
  application-test.yml
~~~

Base test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
abstract class BaseIntegrationTest {
}
~~~

Test kế thừa:

~~~java
class OrderServiceIntegrationTest extends BaseIntegrationTest {

    @Autowired
    OrderService orderService;

    @Test
    void placesOrder() {
        // Test dùng profile test được khai báo ở base class.
    }
}
~~~

Một số nguyên tắc hữu ích:

- Khai báo profile kiểm thử trong test class hoặc base class có phạm vi rõ.
- Đặt property kiểm thử trong `src/test/resources` khi phù hợp.
- Không để endpoint, password hoặc secret production lọt vào test config.
- Dùng database riêng, database nhúng hoặc Testcontainers tùy ranh giới cần kiểm tra.
- Không phụ thuộc profile đang được đặt trong shell của người chạy.
- Khi cần kiểm tra profile khác nhau, tạo test class riêng với cấu hình rõ ràng.
- Không dùng chung profile test cho mọi mục tiêu nếu unit test và integration test có nhu cầu tài nguyên khác nhau.

Nếu một test cần xác nhận cấu hình production, hãy kiểm tra điều kiện bean hoặc cấu hình bằng một context test cô lập. Không khởi động ứng dụng với credential production chỉ để chứng minh profile production chọn đúng implementation.

## 12. Quan sát profile và bean đang hoạt động

Khi không chắc profile nào được kích hoạt, có thể kiểm tra `Environment` trong test:

~~~java
@SpringBootTest
@ActiveProfiles({"test", "integration"})
class ActiveProfileInspectionTest {

    @Autowired
    Environment environment;

    @Test
    void activatesExpectedProfiles() {
        assertArrayEquals(
            new String[] {"test", "integration"},
            environment.getActiveProfiles()
        );
    }
}
~~~

Có thể kiểm tra bean được chọn:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void registersTheExpectedGateway() {
    assertTrue(
        applicationContext.containsBean("testPaymentGateway")
    );
    assertFalse(
        applicationContext.containsBean("productionPaymentGateway")
    );
}
~~~

Tên bean mặc định từ `@Bean` thường là tên phương thức factory. Nếu dùng component, bean name mặc định thường dựa trên tên class với quy tắc đặt tên bean của Spring. Khi cần kiểm tra bean cụ thể, hãy đặt tên tường minh trong cấu hình để test không phụ thuộc vào suy đoán.

Khi debug context, có thể log active profiles:

~~~java
System.out.println(
    Arrays.toString(environment.getActiveProfiles())
);
~~~

Trong Spring Boot, Actuator có endpoint environment và beans hỗ trợ chẩn đoán khi được cấu hình an toàn, nhưng không nên mở thông tin cấu hình nhạy cảm ra môi trường công khai.

## 13. Profile ảnh hưởng tới ApplicationContext cache

Spring TestContext cache context dựa trên metadata cấu hình. Danh sách active profiles là một phần của cấu hình context và ảnh hưởng đến cache key.

Ví dụ:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class TestProfileContextTest {
}
~~~

~~~java
@SpringBootTest
@ActiveProfiles("integration")
class IntegrationProfileContextTest {
}
~~~

Hai test class này có active profiles khác nhau nên thông thường cần hai context khác nhau. Điều này là cần thiết vì tập bean và property có thể khác nhau.

Nếu suite khai báo nhiều tổ hợp profile riêng biệt, Spring phải tải nhiều context và thời gian chạy có thể tăng. Hãy thống nhất cấu hình test class khi chúng thực sự cần cùng một môi trường. Không gộp profile chỉ để tăng cache hit nếu điều đó làm test dùng sai bean hoặc sai tài nguyên.

Profile resolver động cũng có thể làm context key thay đổi tùy kết quả trả về. Nếu resolver đọc system property, hãy bảo đảm test không thay đổi giá trị đó giữa lúc các context được tạo theo cách gây khó hiểu.

## 14. Những lỗi thường gặp

- **Quên `@ActiveProfiles("test")`:** test có thể dùng profile mặc định hoặc profile từ môi trường máy chạy, khiến bean test không được đăng ký.
- **Cho rằng `@Profile` tự kích hoạt profile:** annotation này chỉ đặt điều kiện đăng ký bean; test hoặc môi trường khởi chạy phải kích hoạt profile.
- **Kích hoạt đồng thời nhiều implementation:** Spring có thể tìm thấy nhiều bean cùng kiểu và không biết inject bean nào.
- **Đặt `spring.profiles.active` trong file profile-specific:** cấu hình kích hoạt profile cần được đặt ở nguồn cấu hình phù hợp, không phải tài liệu chỉ được nạp sau khi profile đã hoạt động.
- **Kế thừa profile ngoài ý muốn:** `inheritProfiles` mặc định là true; subclass có thể nhận thêm profile từ base class.
- **Dùng resolver phụ thuộc máy cá nhân:** test có thể cho kết quả khác nhau giữa local và CI.
- **Dùng profile thay cho mọi feature flag:** profile nên đại diện cho nhóm môi trường; property phù hợp hơn cho một tính năng bật/tắt riêng.
- **Cho rằng profile là cơ chế bảo mật:** profile chỉ chọn cấu hình và bean, không bảo vệ secret hay endpoint.
- **Dùng `@Primary` để che xung đột profile:** hãy hiểu vì sao nhiều bean cùng được đăng ký trước khi đặt thứ tự ưu tiên.
- **Khởi động production integration trong test:** chỉ kiểm tra cấu hình production bằng context cô lập, không cần kết nối tài nguyên production thật.

## 15. Quy trình chọn bean theo môi trường kiểm thử

Khi cần một implementation riêng cho test, hãy đi theo trình tự:

1. Xác định interface hoặc boundary mà ứng dụng cần thay thế theo môi trường.
2. Viết implementation dành cho test và implementation dành cho môi trường chạy thật.
3. Đặt điều kiện `@Profile` lên component hoặc bean factory method tương ứng.
4. Kích hoạt profile kiểm thử bằng `@ActiveProfiles` trên test class hoặc base class.
5. Nếu có nhiều profile, xác định rõ chúng được kết hợp hay thay thế qua `inheritProfiles`.
6. Khởi tạo context nhỏ hoặc test context ứng dụng theo phạm vi cần thiết.
7. Inject qua interface và xác nhận bean được chọn hoặc hành vi quan sát được.
8. Kiểm tra active profiles khi cần chẩn đoán cấu hình.
9. Bảo đảm test không phụ thuộc biến môi trường hoặc secret của máy cá nhân.
10. Chỉ thêm resolver động hoặc profile group khi cấu trúc môi trường thực sự cần chúng.

## Kết luận

`@ActiveProfiles` cho Spring TestContext biết profile nào cần kích hoạt khi tải context cho test. `@Profile` dùng điều kiện đó để quyết định component, configuration class hoặc bean factory method nào được đăng ký. Nhờ vậy, cùng một service có thể nhận fake adapter trong test và implementation kết nối hệ thống thật ở môi trường triển khai.

Hãy khai báo profile kiểm thử tường minh, giữ tập bean phù hợp không mơ hồ và phân biệt profile với property. Khi hiểu profile inheritance và context caching, bạn có thể tổ chức test theo môi trường một cách tái lập, dễ chẩn đoán và không phụ thuộc cấu hình máy chạy.



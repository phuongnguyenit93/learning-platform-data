# Profile và property không đúng thứ tự ưu tiên

## 1. Phân biệt active profile và property precedence

Khi một bài kiểm thử Spring dùng nhầm cấu hình, nguyên nhân thường nằm ở một trong hai cơ chế khác nhau:

- **Active profile** quyết định những bean hoặc cấu hình được đánh dấu `@Profile` nào được đưa vào `ApplicationContext`, đồng thời quyết định các file cấu hình theo profile nào được nạp.
- **Property precedence** quyết định giá trị nào thắng khi cùng một key xuất hiện trong nhiều `PropertySource` của `Environment`.

Hai cơ chế có liên quan nhưng không thay thế nhau. `@ActiveProfiles("test")` yêu cầu Spring TestContext kích hoạt profile `test`; nó không có nghĩa mọi property trong `application-test.yml` luôn thắng mọi nguồn cấu hình khác. Một biến môi trường, JVM system property hoặc test property source có thể ghi đè giá trị trong file profile.

Ví dụ, ứng dụng có các cấu hình:

```yaml
# application.yml
payment:
  api-base-url: https://payments.example.com
  timeout: 5s
```

```yaml
# application-test.yml
payment:
  api-base-url: http://localhost:9091
  timeout: 2s
```

Nếu profile `test` được kích hoạt, Boot nạp cấu hình profile tương ứng. Tuy nhiên, nếu môi trường chạy test còn có `PAYMENT_TIMEOUT=10s`, giá trị từ environment variable có thể ghi đè giá trị trong file cấu hình. Vì vậy, khi thấy một bean dùng sai URL hoặc timeout, cần xác định riêng profile nào đang active và property cuối cùng được lấy từ nguồn nào.

## 2. Profile được kích hoạt như thế nào?

Spring `Environment` có danh sách active profiles và default profiles. Nếu không có profile nào được kích hoạt rõ ràng, Spring dùng default profile, thường có tên `default`.

Trong ứng dụng thông thường, profile có thể được kích hoạt bằng property `spring.profiles.active`, ví dụ:

```bash
java -jar app.jar --spring.profiles.active=dev
```

Hoặc bằng biến môi trường:

```text
SPRING_PROFILES_ACTIVE=dev
```

Với integration test dùng Spring TestContext Framework, cách khai báo rõ ràng thường là `@ActiveProfiles`:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderIntegrationTests {
}
```

Khi `@ActiveProfiles` có mặt, TestContext Framework dùng profile được khai báo trong annotation để xác định active profiles. Theo mặc định, `spring.profiles.active` đặt trong JVM system property hoặc environment variable không được dùng để thay thế danh sách đó. Đây là nguồn nhầm lẫn phổ biến khi chạy test trong IDE và CI với các biến môi trường khác nhau.

Nếu test cần cho phép profile bên ngoài ghi đè profile trong annotation, có thể triển khai `ActiveProfilesResolver` riêng. Không nên mong đợi `@ActiveProfiles("test")` và `SPRING_PROFILES_ACTIVE=staging` tự động được hợp nhất theo property precedence thông thường.

### Kế thừa active profiles

`@ActiveProfiles` mặc định cho phép kế thừa profile từ lớp cha và lớp bao ngoài. Ví dụ:

```java
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("integration")
abstract class BaseIntegrationTest {
}

class OrderRepositoryTest extends BaseIntegrationTest {
    // Profile integration được kế thừa.
}
```

Nếu lớp con cần một bộ profile riêng, đặt `inheritProfiles = false`:

```java
@ActiveProfiles(profiles = "repository-test", inheritProfiles = false)
class IsolatedRepositoryTest extends BaseIntegrationTest {
}
```

Lúc này lớp con không kế thừa `integration` từ lớp cha. Thuộc tính `inheritProfiles` điều khiển việc kế thừa profile; nó không điều khiển kế thừa các property trong `@TestPropertySource`.

### ActiveProfilesResolver

Khi profile cần phụ thuộc môi trường chạy, có thể dùng resolver:

```java
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.ActiveProfilesResolver;
import org.springframework.test.context.support.DefaultActiveProfilesResolver;

public class CiAwareProfilesResolver implements ActiveProfilesResolver {

    private final DefaultActiveProfilesResolver fallback =
            new DefaultActiveProfilesResolver();

    @Override
    public String[] resolve(Class<?> testClass) {
        String ciProfile = System.getenv("TEST_PROFILE");
        if (ciProfile != null && !ciProfile.isBlank()) {
            return ciProfile.split(",");
        }
        return fallback.resolve(testClass);
    }
}
```

Đăng ký resolver trên test class:

```java
@ActiveProfiles(resolver = CiAwareProfilesResolver.class)
class EnvironmentAwareIntegrationTest {
}
```

Resolver trên kiểm tra biến `TEST_PROFILE` trước, nếu không có thì dùng hành vi mặc định của Spring. Đây là chính sách do ứng dụng test lựa chọn; hãy giới hạn các profile được phép và tránh dùng giá trị tùy ý từ môi trường không tin cậy.

## 3. File cấu hình theo profile được nạp ra sao?

Trong Spring Boot, các file thường gặp gồm:

```text
src/main/resources/
  application.yml
  application-test.yml
  application-ci.yml
```

`application.yml` chứa cấu hình chung. `application-test.yml` chỉ được áp dụng khi profile `test` active; `application-ci.yml` chỉ được áp dụng khi profile `ci` active.

Ví dụ:

```yaml
# application.yml
server:
  port: 8080
payment:
  timeout: 5s
```

```yaml
# application-test.yml
server:
  port: 0
payment:
  timeout: 1s
```

Khi chạy với profile `test`, giá trị `server.port` được đặt thành `0` để server chọn port ngẫu nhiên, còn timeout được đặt thành một giây. Các key không được khai báo trong file profile vẫn lấy từ cấu hình chung hoặc nguồn khác.

Spring Boot xử lý config data theo vị trí và profile. Ở mức tổng quát, file cấu hình bên ngoài packaged application có thể ghi đè file trong classpath; file profile-specific có thể ghi đè file chung ở cùng nhóm vị trí. Các location được khai báo sau thường có độ ưu tiên cao hơn các location trước. Nếu cấu hình `spring.config.location` hoặc `spring.config.additional-location`, cần tính cả thứ tự location đó khi chẩn đoán.

Một số khác biệt quan trọng:

- `spring.config.location` thay thế các vị trí tìm kiếm mặc định.
- `spring.config.additional-location` bổ sung vị trí cấu hình và có thể ghi đè cấu hình mặc định.
- Các location được xử lý theo thứ tự khai báo; location phía sau có thể ghi đè key trùng ở location trước.
- File `.properties` và YAML cùng vị trí có quy tắc ưu tiên riêng; Boot khuyến nghị thống nhất một định dạng trong toàn ứng dụng.
- Với nhiều profile active, các tài liệu cấu hình tương ứng được xét theo thứ tự profile và nguồn; khi có nhiều giá trị trùng, nguồn có ưu tiên cao hơn thắng.

Đừng suy luận rằng `application-test.yml` luôn thắng mọi file hoặc mọi nguồn. Nó chỉ là một phần trong hệ thống `PropertySource` của Boot.

## 4. Thứ tự ưu tiên property trong Spring Boot

Spring Boot định nghĩa thứ tự các nguồn cấu hình để giá trị ở nguồn có độ ưu tiên cao hơn ghi đè nguồn thấp hơn. Theo tài liệu Externalized Configuration hiện hành, thứ tự từ thấp lên cao được mô tả như sau:

| Thứ tự | Property source | Ghi chú |
|---:|---|---|
| 1 | Default properties từ `SpringApplication.setDefaultProperties(...)` | Giá trị dự phòng thấp nhất. |
| 2 | `@PropertySource` trên class `@Configuration` | Được thêm khi context refresh; quá muộn cho một số property đọc trước refresh như `logging.*` và `spring.main.*`. |
| 3 | Config data | Bao gồm `application.yml`, `application-{profile}.yml` và các location được import. |
| 4 | `RandomValuePropertySource` | Cung cấp key thuộc nhóm `random.*`. |
| 5 | OS environment variables | Ví dụ `PAYMENT_TIMEOUT`. |
| 6 | Java system properties | Ví dụ `-Dpayment.timeout=8s`. |
| 7 | JNDI attributes | Khi ứng dụng chạy trong môi trường hỗ trợ JNDI. |
| 8 | `ServletContext` init parameters | Dành cho ứng dụng Servlet. |
| 9 | `ServletConfig` init parameters | Dành cho Servlet được cấu hình tương ứng. |
| 10 | `SPRING_APPLICATION_JSON` | Property được truyền dưới dạng JSON trong environment hoặc system property. |
| 11 | Command-line arguments | Ví dụ `--payment.timeout=3s`. |
| 12 | `properties` trên `@SpringBootTest` và test slice annotations | Inline test properties của Spring Boot. |
| 13 | `@DynamicPropertySource` | Thường dùng để cung cấp URL/port động từ Testcontainers hoặc server giả. |
| 14 | `@TestPropertySource` | Property nguồn dành riêng cho test. |
| 15 | Devtools global settings | Chỉ liên quan khi Devtools active. |

Bảng trên mô tả thứ tự theo Spring Boot reference; khi dùng Spring Framework TestContext thuần hoặc phiên bản Boot khác, hãy đối chiếu tài liệu đúng phiên bản và xác nhận trực tiếp `Environment` trong context đang chạy.

Spring Framework TestContext mô tả riêng rằng dynamic properties có độ ưu tiên cao hơn `@TestPropertySource`, system properties, environment variables và property sources của ứng dụng. Tài liệu Spring Boot lại đưa thứ tự test sources trong bảng externalized configuration của Boot. Vì vậy, khi một test Boot kết hợp nhiều loại test property source, không nên dựa vào trí nhớ hoặc áp một bảng chung cho mọi bootstrapper; hãy dùng thứ tự được tài liệu đúng phiên bản quy định và kiểm tra property source thực tế.

## 5. @TestPropertySource: file và inline properties

`@TestPropertySource` cho phép khai báo file properties và key-value inline cho một test class:

```java
import org.springframework.test.context.TestPropertySource;

@TestPropertySource(
        locations = "classpath:/order-test.properties",
        properties = {
                "payment.timeout=750ms",
                "feature.audit.enabled=false"
        }
)
class OrderServiceTests {
}
```

Ví dụ file `order-test.properties`:

```properties
payment.timeout=2s
payment.retry-count=1
```

Khi cùng một key xuất hiện trong file và trong thuộc tính `properties` inline, inline property có độ ưu tiên cao hơn file location. Vì vậy `payment.timeout` nhận `750ms`, còn `payment.retry-count` nhận `1`.

`@TestPropertySource` có một số quy tắc đáng chú ý:

- Có thể khai báo nhiều lần trên một class; các khai báo sau ghi đè các khai báo trước cho key trùng.
- Annotation khai báo trực tiếp trên test class có độ ưu tiên cao hơn annotation xuất hiện thông qua meta-annotation.
- `inheritLocations` và `inheritProperties` mặc định cho phép kế thừa cấu hình test property từ lớp cha.
- Đặt `inheritLocations = false` hoặc `inheritProperties = false` để thay thế phần kế thừa tương ứng.
- Nếu dùng `@TestPropertySource` rỗng, Spring tìm file mặc định có tên tương ứng với test class, ví dụ `OrderServiceTests.properties`; nếu không tìm thấy, test có thể lỗi khi nạp context.

Mặc định, `@TestPropertySource` hỗ trợ Java properties và XML properties. Từ Spring Framework 6.1, có thể dùng `PropertySourceFactory` tùy chỉnh để nạp định dạng khác như YAML hoặc JSON. Không nên giả định `@TestPropertySource("classpath:application-test.yml")` tự đọc YAML nếu chưa cấu hình factory phù hợp.

## 6. @DynamicPropertySource cho giá trị được tạo lúc chạy

`@DynamicPropertySource` phù hợp khi giá trị chỉ biết sau khi tài nguyên test được khởi động, chẳng hạn port ngẫu nhiên của Testcontainers, WireMock hoặc một local server.

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class RepositoryIntegrationTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Method được đánh dấu `@DynamicPropertySource` phải là `static` và nhận một `DynamicPropertyRegistry`. Giá trị được cung cấp qua `Supplier`, nên chỉ được lấy khi property được resolve. Đây là lý do nên truyền method reference như `postgres::getJdbcUrl` thay vì đọc port quá sớm trước khi container được khởi động.

Dynamic properties thường dùng cho endpoint động. Không dùng chúng để giấu một cấu hình test sai hoặc để override mọi property một cách thiếu chủ đích. Hãy giới hạn vào các giá trị thực sự phụ thuộc vòng đời tài nguyên test.

Nếu một base test class khai báo `@DynamicPropertySource` nhưng giá trị động khác nhau giữa các lớp con, Spring Test có thể tái sử dụng application context từ context cache. Khi context cũ chứa property của tài nguyên trước đó, cần tách cấu hình context hoặc dùng `@DirtiesContext` phù hợp để mỗi lớp có context với giá trị đúng.

## 7. @SpringBootTest(properties) và test slice properties

Spring Boot cho phép khai báo inline properties ngay trên annotation kiểm thử:

```java
@SpringBootTest(properties = {
        "payment.timeout=500ms",
        "feature.audit.enabled=false"
})
class PaymentIntegrationTests {
}
```

Các thuộc tính này hữu ích cho một test class cần override một vài giá trị mà không cần tạo file properties riêng. Các annotation test slice như `@WebMvcTest` cũng hỗ trợ thuộc tính tương tự.

Đừng nhầm `@SpringBootTest(properties=...)` với `@TestPropertySource`. Chúng là các cơ chế khác nhau và được đặt ở những vị trí khác nhau trong thứ tự property source của Spring Boot. Nếu cùng một key được khai báo trong nhiều nguồn, hãy kiểm tra precedence theo tài liệu phiên bản Boot đang dùng.

Đối với các giá trị dùng chung cho nhiều test, một file `application-test.yml` hoặc test configuration có thể dễ quản lý hơn. Đối với một ngoại lệ chỉ dành cho một test class, inline properties thường rõ ràng hơn.

## 8. Không dùng property precedence để thay thế profile activation

Một lỗi thường gặp là đặt `spring.profiles.active` trong test property source:

```java
@TestPropertySource(properties = "spring.profiles.active=test")
class OrderServiceTests {
}
```

Đây không phải cách tốt để yêu cầu Boot nạp `application-test.yml`. Test property sources được thêm vào context trong quá trình chuẩn bị test; chúng không phải lúc nào cũng có mặt ở thời điểm Config Data đã quyết định profile nào cần dùng để nạp file. Khi đó property có thể xuất hiện trong `Environment`, nhưng file profile-specific đã không được nạp như mong muốn.

Hãy kích hoạt profile bằng cơ chế profile của test:

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceTests {
}
```

Hoặc cung cấp `spring.profiles.active` từ nguồn bootstrap sớm như JVM system property, environment variable hoặc command line khi không có `@ActiveProfiles` ghi đè cách xác định profile của TestContext.

Nếu muốn một test chỉ override một property, hãy khai báo property đó trực tiếp:

```java
@SpringBootTest(properties = "payment.timeout=500ms")
class FastPaymentTests {
}
```

Không dùng `spring.profiles.active` như một key cấu hình thông thường khi mục tiêu thực sự chỉ là thay một giá trị.

## 9. Các quy tắc profile-specific cần nhớ

Spring Boot có một số giới hạn để profile activation được xử lý nhất quán:

- `spring.profiles.active` và `spring.profiles.default` chỉ được khai báo trong tài liệu cấu hình không phụ thuộc profile.
- Không đặt hai key này trong `application-test.yml` hoặc một document đã được kích hoạt bằng `spring.config.activate.on-profile`.
- Có thể dùng `spring.profiles.include` để thêm profile và `spring.profiles.group` để nhóm nhiều profile dưới một tên logic.
- Dùng `spring.config.activate.on-profile` để kích hoạt một document cụ thể trong file cấu hình nhiều document.
- Profile `default` chỉ được dùng khi không có active profile nào khác.

Ví dụ profile group:

```yaml
spring:
  profiles:
    group:
      integration:
        - test
        - database-test
        - messaging-test
```

Khi kích hoạt `integration`, các profile thành viên cũng được đưa vào active profiles. Cách này hữu ích khi nhiều test cần cùng một tổ hợp cấu hình. Tránh khai báo profile group hoặc include ở nhiều nguồn khác nhau nếu chưa xác định rõ thứ tự và tổ hợp profile cuối cùng.

Ví dụ document activation:

```yaml
app:
  banner: default
---
spring:
  config:
    activate:
      on-profile: test
app:
  banner: test-mode
```

Document thứ hai chỉ được áp dụng khi profile `test` active. Việc kích hoạt profile và việc chọn property source vẫn là hai bước liên quan nhưng khác nhau.

## 10. Chẩn đoán property đang lấy từ đâu

Khi một bean nhận giá trị không như mong đợi, trước hết hãy đọc giá trị cuối cùng qua `Environment` và kiểm tra danh sách `PropertySource`. `MutablePropertySources` được duyệt theo thứ tự ưu tiên; property source đầu tiên chứa key là nguồn được dùng.

```java
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;

void diagnose(ConfigurableApplicationContext context) {
    ConfigurableEnvironment environment = context.getEnvironment();

    System.out.println("Active profiles: "
            + String.join(", ", environment.getActiveProfiles()));
    System.out.println("Default profiles: "
            + String.join(", ", environment.getDefaultProfiles()));

    String key = "payment.timeout";
    System.out.println("Resolved value: " + environment.getProperty(key));

    for (PropertySource<?> source : environment.getPropertySources()) {
        if (source.containsProperty(key)) {
            System.out.println("First matching source: " + source.getName());
            break;
        }
    }
}
```

Đoạn code này minh họa cách tìm nguồn đầu tiên chứa property. Trong ứng dụng thật, tránh ghi giá trị nhạy cảm như password, token hoặc connection string ra log. Có thể chỉ ghi tên nguồn, hoặc mask giá trị trước khi hiển thị.

Một cách kiểm tra nhanh ngay trong test:

```java
@Autowired
Environment environment;

@Test
void printsTestConfiguration() {
    System.out.println(Arrays.toString(environment.getActiveProfiles()));
    System.out.println(environment.getProperty("payment.api-base-url"));
}
```

Nếu dùng Spring Boot Actuator, endpoint `env` giúp xem property sources và origin của giá trị; `configprops` giúp kiểm tra giá trị đã bind vào `@ConfigurationProperties`. Chỉ bật và expose các endpoint này trong môi trường phù hợp, đồng thời bảo vệ thông tin nhạy cảm theo chính sách bảo mật.

## 11. Chẩn đoán binding với @ConfigurationProperties

Đôi khi `Environment.getProperty("payment.timeout")` cho đúng giá trị nhưng bean `@ConfigurationProperties` lại có giá trị khác. Khi đó cần kiểm tra prefix, tên key, kiểu dữ liệu, validation và cách binder xử lý cấu trúc phức tạp.

Ví dụ:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        String apiBaseUrl,
        Duration timeout,
        int retryCount) {
}
```

Key dạng kebab-case được khuyến nghị trong file cấu hình:

```yaml
payment:
  api-base-url: http://localhost:9091
  timeout: 2s
  retry-count: 1
```

Các nguồn như environment variables có quy tắc relaxed binding riêng. Ví dụ `PAYMENT_API_BASE_URL` có thể map đến `payment.api-base-url`. Khi tên biến có dấu gạch dưới, dấu chấm hoặc chỉ số list, cần tuân theo quy tắc binding của Spring Boot thay vì suy luận bằng cách thay ký tự tùy ý.

Đặc biệt, khi cùng một cấu trúc được khai báo ở nhiều nguồn:

- Với scalar property, giá trị từ nguồn ưu tiên cao hơn được dùng.
- Với list, nguồn ưu tiên cao hơn thường thay thế toàn bộ list; các phần tử từ nguồn thấp hơn không tự động được nối vào.
- Với map, các entry có thể được hợp nhất theo key, nhưng cùng một key vẫn lấy giá trị từ nguồn ưu tiên cao hơn.

Vì vậy, một danh sách cấu hình bị mất phần tử sau khi thêm profile hoặc environment variable có thể là hành vi override của list, không phải lỗi đọc sai file.

## 12. Context cache có thể khiến cấu hình cũ xuất hiện

Spring TestContext Framework cache `ApplicationContext` để giảm thời gian chạy suite. Các thuộc tính cấu hình như active profiles, context customizers và test property sources tham gia vào việc xác định context cache key.

Nếu hai test class có cấu hình giống nhau, chúng có thể dùng lại cùng context. Điều này thường có lợi, nhưng cần chú ý khi:

- Một `@DynamicPropertySource` trong base class trả về giá trị thay đổi giữa các subclass.
- Một static container hoặc mock server được khởi động lại nhưng context vẫn giữ endpoint cũ.
- Test thay đổi trạng thái singleton bean hoặc property source sau khi context đã được tạo.
- Một test dùng `@DirtiesContext` làm context bị loại khỏi cache và test tiếp theo phải tạo context mới.

Nếu giá trị động khác nhau giữa các subclass, hãy bảo đảm mỗi subclass có context đúng với tài nguyên của nó. Có thể dùng `@DirtiesContext` ở phạm vi phù hợp hoặc tách test configuration để context cache key khác nhau. Không nên thay đổi `Environment` tùy tiện sau khi bean đã được khởi tạo và mong `@Value` tự cập nhật; phần lớn giá trị inject vào bean được resolve trong lúc tạo bean.

## 13. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `application-test.yml` không được nạp | Profile `test` chưa active hoặc test khai báo `@ActiveProfiles` khác. | In `Environment.getActiveProfiles()` và kiểm tra annotation/resolver. |
| `SPRING_PROFILES_ACTIVE` không thay đổi profile của test | Test class khai báo `@ActiveProfiles`, nên TestContext không dùng biến môi trường để thay thế. | Bỏ annotation nếu muốn dùng external profile, hoặc triển khai `ActiveProfilesResolver`. |
| Profile đúng nhưng URL/timeout vẫn sai | Environment variable, JVM property, command line hoặc test property source có ưu tiên cao hơn file. | Tìm property source đầu tiên chứa key và kiểm tra nguồn ghi đè. |
| `@TestPropertySource` không đọc YAML | Factory mặc định không hỗ trợ YAML. | Dùng `.properties` hoặc cấu hình `PropertySourceFactory` tùy chỉnh từ Spring Framework 6.1. |
| `@TestPropertySource` rỗng làm context load thất bại | Spring không tìm thấy file properties mặc định có tên tương ứng test class. | Khai báo `locations` rõ ràng hoặc bỏ annotation rỗng. |
| `@DynamicPropertySource` không có giá trị đúng | Supplier đọc tài nguyên trước khi sẵn sàng, hoặc context cache giữ giá trị từ test khác. | Dùng method reference, khởi động tài nguyên đúng vòng đời và tách/làm mới context khi cần. |
| `@PropertySource` không thay đổi `logging.*` | Property source được thêm quá muộn trong vòng đời Boot. | Đặt property ở config data hoặc nguồn bootstrap sớm. |
| List trong `@ConfigurationProperties` mất phần tử | List ở nguồn ưu tiên cao hơn thay thế toàn bộ list. | Khai báo list đầy đủ ở nguồn override hoặc chuyển sang map nếu mô hình phù hợp. |
| `@ActiveProfiles` lớp con vẫn nhận profile lớp cha | `inheritProfiles` mặc định là `true`. | Đặt `inheritProfiles = false` khi muốn thay thế danh sách kế thừa. |
| Bean vẫn giữ giá trị cũ sau khi đổi property | Bean đã được tạo và inject giá trị trước khi property thay đổi. | Tạo context mới hoặc thiết kế cấu hình động có cơ chế refresh rõ ràng. |

## 14. Quy trình xử lý khi test nhận sai cấu hình

Khi test dùng nhầm profile hoặc property, hãy chẩn đoán theo thứ tự:

1. In active profiles và default profiles từ `Environment`.
2. Kiểm tra test class, base class, enclosing class và `ActiveProfilesResolver` để biết profile đến từ đâu.
3. Xác nhận file profile-specific có đúng tên và nằm trong config location được Boot tìm kiếm.
4. Kiểm tra `spring.config.location`, `spring.config.additional-location`, config imports và file ngoài classpath.
5. Tìm tất cả nơi khai báo key cần kiểm tra: YAML, properties, environment variable, JVM `-D`, command line, `@SpringBootTest(properties)`, `@DynamicPropertySource`, `@TestPropertySource` và `@PropertySource`.
6. Duyệt `Environment.getPropertySources()` để xác định nguồn đầu tiên chứa key.
7. Nếu dùng `@ConfigurationProperties`, kiểm tra prefix, relaxed binding, kiểu dữ liệu, list/map merge và validation.
8. Nếu test chạy theo suite nhưng giá trị thay đổi giữa lớp, kiểm tra context cache và vòng đời tài nguyên động.
9. Chỉ thay đổi nguồn cấu hình có chủ đích; tránh thêm một override mới mà không loại bỏ nguyên nhân cũ.

## 15. Nguyên tắc tổ chức cấu hình test

- Dùng `@ActiveProfiles("test")` để chọn profile rõ ràng cho test context.
- Dùng `application-test.yml` cho cấu hình chung của môi trường test.
- Dùng `@TestPropertySource` hoặc `@SpringBootTest(properties=...)` cho override cụ thể của test class.
- Dùng `@DynamicPropertySource` cho URL, port và thông tin chỉ có sau khi tài nguyên test được khởi động.
- Tránh khai báo cùng một key ở quá nhiều nơi; nếu cần override, ghi rõ lý do trong test.
- Không đặt `spring.profiles.active` trong một file profile-specific hoặc dùng test property source muộn để thay thế profile activation.
- Không để endpoint hoặc credential production làm fallback trong test profile.
- Khi kế thừa test configuration, xác định riêng quy tắc kế thừa profile và property source.
- Kiểm tra property source thực tế khi precedence phức tạp, đặc biệt giữa Spring Framework thuần và Spring Boot test bootstrapper.
- Bảo vệ log và endpoint chẩn đoán để không làm lộ secret.

## 16. Kết luận

Profile activation và property precedence là hai cơ chế khác nhau. `@ActiveProfiles` chọn profile cho Spring TestContext; `PropertySource` quyết định giá trị cuối cùng của từng key. File `application-{profile}.yml` chỉ là một nguồn trong nhiều nguồn cấu hình, còn test property sources, environment variables, JVM properties và command line có thể ghi đè nó theo thứ tự của phiên bản Spring đang dùng. Khi gặp cấu hình sai, hãy xác nhận active profiles trước, sau đó tìm property source đầu tiên chứa key trong `Environment`. Cách kiểm tra này giúp xác định chính xác nguyên nhân thay vì tiếp tục thêm các override mới.

## Tài liệu tham khảo

- [Spring Framework Reference — Context Configuration with Environment Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html)
- [Spring Framework Reference — Context Configuration with Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html)
- [Spring Framework Reference — Context Configuration with Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)

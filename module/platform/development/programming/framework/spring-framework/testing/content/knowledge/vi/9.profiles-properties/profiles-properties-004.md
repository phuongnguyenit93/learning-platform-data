# Thứ tự ưu tiên của các nguồn cấu hình

Trong ứng dụng Spring, một thuộc tính có thể được khai báo ở nhiều nơi: file cấu hình, biến môi trường, system property của JVM, cấu hình dành riêng cho test hoặc giá trị được cung cấp động từ một tài nguyên bên ngoài. Khi nhiều nguồn cùng khai báo một khóa, Spring cần một quy tắc xác định nguồn nào được dùng.

Quy tắc đó được thể hiện qua **thứ tự của các `PropertySource` trong `Environment`**. Spring duyệt các nguồn theo thứ tự ưu tiên; nguồn đầu tiên chứa khóa sẽ cung cấp giá trị. Vì vậy, việc hiểu thứ tự này rất quan trọng khi cấu hình profile, viết test với `@TestPropertySource`, cấp dữ liệu cho Testcontainers bằng `@DynamicPropertySource` hoặc chẩn đoán vì sao `@Value` nhận một giá trị khác dự kiến.

## 1. Environment và PropertySource

`Environment` là abstraction của Spring để truy cập hai nhóm thông tin:

- **Profiles:** các profile đang hoạt động hoặc profile mặc định, được dùng để quyết định bean và cấu hình nào được áp dụng.
- **Properties:** các cặp khóa/giá trị lấy từ một hoặc nhiều nguồn cấu hình.

Trong cấu hình Spring, `ConfigurableEnvironment` cho phép đọc và thay đổi danh sách nguồn thuộc tính. Mỗi nguồn được biểu diễn bởi `PropertySource<?>`, thường là một tập hợp khóa/giá trị có tên.

Một số loại nguồn phổ biến:

| Nguồn | Ví dụ | Mục đích |
|---|---|---|
| `MapPropertySource` | Map do ứng dụng hoặc test tạo | Cung cấp thuộc tính từ dữ liệu trong bộ nhớ |
| `PropertiesPropertySource` | Đối tượng `java.util.Properties` | Đưa tập thuộc tính Java vào Environment |
| `ResourcePropertySource` | File `.properties` hoặc resource tương ứng | Đọc cấu hình từ resource |
| `System.getProperties()` | `-Dapp.timeout=30` | Cấu hình qua system property của JVM |
| System environment | `APP_TIMEOUT=30` | Cấu hình qua biến môi trường của hệ điều hành |
| Test property source | `@TestPropertySource` | Ghi đè cấu hình dành riêng cho test |
| Dynamic test property source | `@DynamicPropertySource` | Cung cấp giá trị được tính hoặc lấy từ tài nguyên bên ngoài lúc chạy test |

`Environment.getProperty("app.timeout")` tìm khóa trong các nguồn đã đăng ký. Nếu khóa xuất hiện ở nhiều nguồn, giá trị ở nguồn có độ ưu tiên cao hơn sẽ được trả về. Đây là cơ chế phân giải thuộc tính theo thứ tự, không phải quy tắc “giá trị mới nhất theo thời gian luôn thắng”.

### 1.1. Thứ tự trong MutablePropertySources

`ConfigurableEnvironment#getPropertySources()` trả về `MutablePropertySources`. Danh sách này duy trì thứ tự tìm kiếm và cung cấp các thao tác:

- `addFirst(propertySource)`: đặt nguồn lên đầu danh sách, có độ ưu tiên cao nhất trong các nguồn hiện có.
- `addLast(propertySource)`: thêm nguồn vào cuối, có độ ưu tiên thấp hơn các nguồn đứng trước.
- `addBefore(name, propertySource)` và `addAfter(name, propertySource)`: đặt nguồn trước hoặc sau một nguồn đã có tên.
- `replace(name, propertySource)`: thay nguồn có tên bằng nguồn mới.
- `remove(name)`: loại bỏ nguồn theo tên.

Ví dụ:

```java
ConfigurableEnvironment environment = new StandardEnvironment();

Map<String, Object> overrides = Map.of(
        "app.timeout", "15",
        "app.feature.enabled", "true");

environment.getPropertySources().addFirst(
        new MapPropertySource("local-test-overrides", overrides));

assertEquals("15", environment.getProperty("app.timeout"));
assertEquals(Boolean.TRUE,
        environment.getProperty("app.feature.enabled", Boolean.class));
```

`addFirst` làm nguồn mới được xét trước các nguồn mặc định như system properties và system environment. Trong ứng dụng thực tế, chỉ nên thay đổi thứ tự khi có yêu cầu cấu hình rõ ràng; một nguồn ghi đè ở đầu danh sách có thể che khuất giá trị từ mọi nguồn đứng sau.

### 1.2. Quy tắc first match wins

Giả sử danh sách nguồn có thứ tự như sau:

```text
1. test-overrides
2. systemProperties
3. systemEnvironment
4. application-properties
5. defaultProperties
```

Nếu `app.timeout` tồn tại ở `test-overrides`, Spring trả về giá trị ở nguồn này và không cần lấy giá trị ở các nguồn thấp hơn. Nếu khóa không có ở nguồn thứ nhất, Spring tiếp tục tìm ở nguồn thứ hai và cứ thế cho đến khi tìm thấy hoặc hết danh sách.

Đây là lý do một property có thể xuất hiện trong nhiều file nhưng ứng dụng chỉ nhìn thấy một giá trị tại một thời điểm. Các nguồn thấp hơn vẫn tồn tại trong Environment; chúng chỉ không được chọn cho khóa đã được nguồn cao hơn cung cấp.

## 2. Các nguồn thuộc tính mặc định của Spring

Với `StandardEnvironment`, Spring đăng ký hai nguồn quan trọng:

1. `systemProperties`: các thuộc tính từ `System.getProperties()` của JVM.
2. `systemEnvironment`: các biến môi trường của hệ điều hành.

System properties đứng trước system environment trong `StandardEnvironment`. Nếu cả hai cùng khai báo một khóa tương ứng, system property được ưu tiên.

Ví dụ chạy JVM:

```bash
java -Dapp.region=from-jvm -jar application.jar
```

Hoặc khai báo biến môi trường:

```bash
APP_REGION=from-environment java -jar application.jar
```

Trên Windows PowerShell:

```powershell
$env:APP_REGION = "from-environment"
java -Dapp.region=from-jvm -jar application.jar
```

Trong `StandardEnvironment`, `Environment#getProperty("app.region")` trả về `from-jvm` khi cả hai cách cấu hình cùng cung cấp giá trị tương ứng. Cách ánh xạ tên biến môi trường có thể phụ thuộc `SystemEnvironmentPropertySource`; khi làm việc với biến môi trường, cần tuân theo quy tắc tên mà môi trường và framework đang sử dụng hỗ trợ.

Với ứng dụng web dựa trên Servlet, `StandardServletEnvironment` bổ sung các nguồn liên quan như servlet config, servlet context và JNDI. Các nguồn này được đặt theo thứ tự do implementation của Spring quy định; không nên giả định mọi loại `Environment` đều có chính xác hai nguồn giống `StandardEnvironment`.

## 3. Nguồn cấu hình được khai báo bằng @PropertySource

`@PropertySource` đưa một resource vào Environment khi Spring xử lý cấu hình Java.

```java
@Configuration
@PropertySource("classpath:/config/application-defaults.properties")
public class ApplicationConfiguration {
}
```

Ví dụ nội dung `application-defaults.properties`:

```properties
app.region=ap-southeast
app.timeout=10
app.feature.enabled=false
```

Sau khi configuration class được xử lý, các giá trị này có thể được đọc qua `Environment` hoặc placeholder resolution.

```java
@Component
public class ApplicationSettings {

    private final Environment environment;

    public ApplicationSettings(Environment environment) {
        this.environment = environment;
    }

    public String region() {
        return environment.getProperty("app.region");
    }
}
```

Với `StandardEnvironment`, các nguồn system properties và system environment đã được đăng ký trước. Nguồn được thêm bởi `@PropertySource` thường được đặt sau các nguồn mặc định này, vì vậy system property hoặc biến môi trường tương ứng có thể ghi đè giá trị trong file.

Khi có nhiều `@PropertySource`, thứ tự xử lý các configuration class có thể ảnh hưởng đến nguồn nào được thêm trước hoặc sau. Nếu thứ tự ghi đè giữa nhiều file là một yêu cầu quan trọng, hãy cấu hình thứ tự một cách tường minh hoặc sử dụng cách đăng ký `PropertySource` có kiểm soát thay vì dựa vào thứ tự quét component không xác định.

`@PropertySource` thuộc Spring Framework. Việc Spring Boot tự động nạp `application.properties`, `application.yml` và các file theo profile là cơ chế Config Data của Spring Boot, có quy tắc riêng và nhiều nguồn hơn. Không nên lấy thứ tự của Spring Boot Config Data rồi áp dụng nguyên xi cho một ứng dụng Spring Framework thuần.

## 4. Thứ tự ưu tiên của nguồn thuộc tính trong Spring TestContext

Spring TestContext cung cấp các annotation để thêm cấu hình dành riêng cho test. Các nguồn này được đặt với độ ưu tiên cao để test có thể thay thế cấu hình ứng dụng mà không cần sửa file cấu hình production.

Trong phạm vi các nguồn thường gặp của Spring TestContext, thứ tự ưu tiên từ cao xuống thấp là:

| Ưu tiên | Nguồn | Cách khai báo | Ý nghĩa |
|---:|---|---|---|
| 1 | Dynamic test properties | `@DynamicPropertySource` | Giá trị động, thường lấy từ container hoặc tài nguyên được khởi tạo trong test |
| 2 | Inline test properties | `@TestPropertySource(properties = ...)` | Cặp khóa/giá trị viết trực tiếp trên test class |
| 3 | Test property resources | `@TestPropertySource(locations = ...)` | File cấu hình được chỉ định riêng cho test |
| 4 | JVM system properties | `-Dkey=value` hoặc `System.setProperty` | Cấu hình của tiến trình JVM |
| 5 | System environment | Biến môi trường | Cấu hình từ hệ điều hành |
| 6 | Application `@PropertySource` | `@PropertySource` trên configuration class | Cấu hình resource do ứng dụng khai báo |
| 7 | Default properties | `MutablePropertySources` được cấu hình ở cuối | Giá trị dự phòng khi không nguồn nào cung cấp khóa |

Bảng trên mô tả thứ tự thường gặp khi sử dụng Spring TestContext cùng `StandardEnvironment` và các nguồn được liệt kê. Nếu ứng dụng hoặc test tự thêm, thay thế hoặc sắp xếp lại `PropertySource`, thứ tự thực tế sẽ phụ thuộc cấu hình đó. Với Spring Boot, các nguồn Config Data và thuộc tính do Boot test cung cấp cũng cần được tính đến theo phiên bản Boot đang sử dụng.

### 4.1. @TestPropertySource với resource file

`@TestPropertySource(locations = ...)` nạp một hoặc nhiều file chỉ dành cho test:

```java
@SpringJUnitConfig(TestConfiguration.class)
@TestPropertySource(locations = "classpath:/config/test-defaults.properties")
class AccountServiceTest {
    // test methods
}
```

Ví dụ `test-defaults.properties`:

```properties
app.region=test-region
app.timeout=20
app.feature.enabled=true
```

Các thuộc tính trong test property resource có độ ưu tiên cao hơn system properties, system environment và các nguồn cấu hình ứng dụng được khai báo bằng `@PropertySource` theo quy tắc của TestContext.

Nếu không chỉ định `locations`, Spring có thể tìm resource mặc định tương ứng với tên test class theo quy ước của `@TestPropertySource`. Để tránh test phụ thuộc vào một file ngầm định khó nhận biết, nên chỉ rõ `locations` khi muốn sử dụng một resource cụ thể.

### 4.2. Inline properties có độ ưu tiên cao hơn file test

Có thể khai báo giá trị ngay trên annotation:

```java
@TestPropertySource(
        locations = "classpath:/config/test-defaults.properties",
        properties = {
                "app.timeout=30",
                "app.feature.enabled=false"
        })
class AccountServiceTest {
}
```

Nếu file `test-defaults.properties` đặt `app.timeout=20`, giá trị `30` trong `properties` sẽ được ưu tiên. Đây là cách thuận tiện để mỗi test class ghi đè một vài giá trị mà không phải tạo thêm file cấu hình riêng.

Inline properties có thể dùng dạng `key=value` hoặc `key:value`. Hãy giữ tên khóa nhất quán với cấu hình ứng dụng và tránh đưa bí mật thật vào source code hoặc file test được commit.

### 4.3. @DynamicPropertySource có độ ưu tiên cao nhất trong nhóm test sources

`@DynamicPropertySource` cho phép đăng ký thuộc tính có giá trị được cung cấp bởi một `Supplier`. Cơ chế này đặc biệt hữu ích khi test cần địa chỉ, port hoặc credential tạm thời của một tài nguyên bên ngoài, chẳng hạn Testcontainers.

```java
@SpringJUnitConfig(ExternalServiceTestConfiguration.class)
class ExternalServiceIntegrationTest {

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("service.base-url", () -> "http://localhost:18080");
        registry.add("service.timeout", () -> "5s");
    }
}
```

Spring gọi supplier khi giá trị property được phân giải, thay vì bắt buộc phải tính tất cả giá trị ngay lúc đăng ký. Vì vậy, supplier có thể đọc port được cấp động sau khi container đã khởi động.

Ví dụ minh họa với Testcontainers:

```java
@Testcontainers
@SpringBootTest
class DatabaseIntegrationTest {

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

Ví dụ dùng API của Spring TestContext kết hợp Testcontainers; dự án cần khai báo dependency và cấu hình lifecycle Testcontainers tương ứng. `@DynamicPropertySource` có độ ưu tiên cao hơn `@TestPropertySource`, system properties, system environment và nguồn `@PropertySource` của ứng dụng. Do đó, URL do container cung cấp có thể ghi đè URL cố định trong file cấu hình.

Các phương thức được đánh dấu `@DynamicPropertySource` phải là `static`, nhận một `DynamicPropertyRegistry` và đăng ký khóa bằng `registry.add(name, supplier)`. Tên khóa phải trùng với khóa mà ứng dụng đang đọc.

### 4.4. Ví dụ tổng hợp nhiều nguồn cùng khai báo một khóa

Giả sử ứng dụng có file `application-defaults.properties`:

```properties
app.mode=application
app.timeout=5
app.region=ap-southeast
```

File dành riêng cho test `test-defaults.properties`:

```properties
app.mode=file
app.timeout=10
```

Test class khai báo inline properties và dynamic property:

```java
@SpringJUnitConfig(PropertyPrecedenceTest.TestConfiguration.class)
@TestPropertySource(
        locations = "classpath:/config/test-defaults.properties",
        properties = {
                "app.mode=inline",
                "app.timeout=20"
        })
class PropertyPrecedenceTest {

    @Configuration
    @PropertySource("classpath:/config/application-defaults.properties")
    static class TestConfiguration {
    }

    @Autowired
    private Environment environment;

    @DynamicPropertySource
    static void dynamicProperties(DynamicPropertyRegistry registry) {
        registry.add("app.mode", () -> "dynamic");
    }

    @Test
    void usesHighestPriorityValueForEachProperty() {
        assertEquals("dynamic", environment.getProperty("app.mode"));
        assertEquals("20", environment.getProperty("app.timeout"));
        assertEquals("ap-southeast", environment.getProperty("app.region"));
    }
}
```

Kết quả được giải thích như sau:

| Khóa | Giá trị trong application file | Giá trị trong test file | Inline test value | Dynamic value | Giá trị được đọc |
|---|---|---|---|---|---|
| `app.mode` | `application` | `file` | `inline` | `dynamic` | `dynamic` |
| `app.timeout` | `5` | `10` | `20` | Không khai báo | `20` |
| `app.region` | `ap-southeast` | Không khai báo | Không khai báo | Không khai báo | `ap-southeast` |

Ví dụ cho thấy độ ưu tiên được xét riêng cho từng khóa. `app.mode` lấy giá trị dynamic, trong khi `app.timeout` lấy inline test value và `app.region` vẫn lấy từ cấu hình ứng dụng vì không có nguồn cao hơn ghi đè.

## 5. Profile và property source là hai khái niệm khác nhau

Profile quyết định cấu hình hoặc bean nào được kích hoạt. Property source quyết định giá trị nào được dùng khi nhiều nguồn cùng cung cấp một khóa. Hai cơ chế có thể phối hợp nhưng không thay thế nhau.

Ví dụ:

```java
@Configuration
@Profile("test")
public class TestMailConfiguration {

    @Bean
    MailGateway mailGateway() {
        return new InMemoryMailGateway();
    }
}
```

Khi profile `test` hoạt động, Spring có thể đăng ký `InMemoryMailGateway`. Profile không tự động làm mọi property trong một file mang tên `test` có độ ưu tiên cao hơn. Việc nạp file theo profile phụ thuộc cách cấu hình ứng dụng; trong Spring Boot, cơ chế `application-test.properties` thuộc Config Data.

### 5.1. Kích hoạt profile cho test bằng @ActiveProfiles

Spring TestContext cung cấp `@ActiveProfiles` để khai báo profile dùng khi tạo ApplicationContext cho test:

```java
@SpringJUnitConfig(TestConfiguration.class)
@ActiveProfiles("test")
class AccountServiceTest {
}
```

Có thể khai báo nhiều profile:

```java
@ActiveProfiles({"test", "stub-mail"})
class AccountServiceTest {
}
```

Các profile này được dùng để đánh giá điều kiện `@Profile` và cấu hình bean. Nếu `@ActiveProfiles` được khai báo, Spring TestContext dùng các profile đã khai báo (và các profile được kế thừa theo quy tắc) thay cho việc tự động lấy `spring.profiles.active` từ system property hoặc biến môi trường. Nếu cần logic chọn profile tùy chỉnh, có thể triển khai `ActiveProfilesResolver` và khai báo qua thuộc tính `resolver` của `@ActiveProfiles`.

Nếu không khai báo `@ActiveProfiles`, môi trường có thể lấy active profile từ cấu hình `Environment`, chẳng hạn system property `spring.profiles.active`, hoặc sử dụng default profile khi không có profile nào được kích hoạt.

### 5.2. Kế thừa profile trong test class hierarchy

`@ActiveProfiles` mặc định kế thừa profile từ lớp cha. Có thể bổ sung profile ở lớp con:

```java
@ActiveProfiles("test")
abstract class BaseIntegrationTest {
}

@ActiveProfiles("stub-mail")
class MailIntegrationTest extends BaseIntegrationTest {
}
```

Với cấu hình kế thừa mặc định, lớp con có thể dùng cả `test` và `stub-mail`. Nếu đặt `inheritProfiles = false`, profile khai báo ở lớp cha không được kế thừa. Cần hiểu rõ lựa chọn này để tránh một test vô tình chạy với bean production hoặc thiếu bean giả lập cần thiết.

### 5.3. Kế thừa @TestPropertySource

`@TestPropertySource` cũng hỗ trợ kế thừa từ lớp cha. Mặc định, locations và inline properties được kế thừa; các giá trị ở lớp con có thể bổ sung hoặc ghi đè theo thứ tự nguồn được xây dựng.

Có thể tắt kế thừa độc lập cho resource và inline properties:

```java
@TestPropertySource(
        locations = "classpath:/config/base-test.properties",
        properties = "app.region=base")
abstract class BaseServiceTest {
}

@TestPropertySource(
        locations = "classpath:/config/special-test.properties",
        inheritLocations = false,
        properties = "app.region=special",
        inheritProperties = false)
class SpecialServiceTest extends BaseServiceTest {
}
```

Trong ví dụ, lớp con không nhận các resource locations và inline properties từ lớp cha. Chỉ dùng `inheritLocations = false` hoặc `inheritProperties = false` khi muốn thay thế nhóm cấu hình tương ứng; nếu không, mặc định kế thừa thường thuận tiện hơn cho test hierarchy.

## 6. Đọc thuộc tính bằng Environment, @Value và cấu hình bean

Sau khi Environment được tạo và các property source được đăng ký, ứng dụng có thể truy cập giá trị bằng nhiều API.

### 6.1. Environment#getProperty

```java
@Component
public class FeatureSettings {

    private final Environment environment;

    public FeatureSettings(Environment environment) {
        this.environment = environment;
    }

    public boolean isFeatureEnabled() {
        return environment.getProperty(
                "app.feature.enabled", Boolean.class, false);
    }
}
```

Overload có kiểu đích cho phép Spring chuyển đổi chuỗi property sang kiểu Java. Có thể truyền giá trị mặc định nếu khóa không tồn tại. Cần phân biệt trường hợp khóa không tồn tại với trường hợp khóa tồn tại nhưng giá trị rỗng hoặc không chuyển đổi được.

### 6.2. @Value và placeholder

```java
@Component
public class RetrySettings {

    private final int maxAttempts;

    public RetrySettings(@Value("${app.retry.max-attempts:3}") int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
```

Placeholder `${app.retry.max-attempts:3}` dùng giá trị của khóa nếu tìm thấy; nếu không có, phần sau dấu `:` là giá trị mặc định. Khi có nhiều nguồn khai báo cùng khóa, placeholder resolution sử dụng giá trị thắng theo thứ tự của Environment.

Trong Spring Framework, khả năng phân giải placeholder phụ thuộc bean factory/configuration được thiết lập đúng, thường qua `PropertySourcesPlaceholderConfigurer` hoặc cơ chế cấu hình tương ứng. Spring Boot tự cấu hình nhiều phần này cho ứng dụng Boot.

### 6.3. @ConfigurationProperties trong Spring Boot

Spring Boot cung cấp `@ConfigurationProperties` để bind một nhóm thuộc tính thành object có kiểu:

```java
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(int maxAttempts, Duration delay) {
}
```

Binder của Spring Boot hỗ trợ relaxed binding và chuyển đổi kiểu theo quy tắc của Boot. Giá trị cuối cùng vẫn chịu ảnh hưởng từ các nguồn trong Environment và thứ tự ưu tiên của Config Data/test sources. `@ConfigurationProperties` là tính năng Spring Boot, không phải API cốt lõi của Spring Framework.

## 7. Thứ tự nguồn cấu hình trong Spring Boot

Khi kiểm thử ứng dụng Spring Boot, cần phân biệt quy tắc chung của `Environment` với hệ thống externalized configuration của Boot. Boot bổ sung các nguồn như Config Data, file profile-specific, command-line arguments, test annotation properties và các nguồn khác. Thứ tự chính xác được định nghĩa bởi phiên bản Spring Boot đang dùng.

Một số nguồn Boot thường gặp gồm:

- Default properties được khai báo trong `SpringApplication`.
- `@PropertySource` trên configuration class.
- Config Data từ `application.properties` hoặc `application.yml` và các file theo profile.
- Random value property source.
- System properties và system environment.
- JNDI hoặc servlet context parameters trong môi trường tương ứng.
- Command-line arguments.
- Các test property sources như `@SpringBootTest(properties = ...)`, `@TestPropertySource` và `@DynamicPropertySource`.

Đây là các nhóm nguồn để nhận diện, không phải bảng thứ tự đầy đủ. Boot có các quy tắc bổ sung như file bên ngoài ghi đè file trong classpath, file profile-specific ghi đè file không theo profile, và các nguồn test có ưu tiên cao. Khi một test phụ thuộc chính xác vào precedence của Boot, hãy đối chiếu tài liệu externalized configuration của đúng phiên bản Boot và kiểm tra danh sách `Environment#getPropertySources()` tại runtime.

Không nên suy ra rằng `application-test.properties` luôn được Spring Framework thuần tự động nạp chỉ vì `@ActiveProfiles("test")` được dùng. Việc tự động nạp file theo profile là hành vi của Spring Boot Config Data hoặc phải được cấu hình riêng trong Spring Framework.

## 8. Kiểm tra thứ tự ưu tiên trong test

Khi viết test về cấu hình, nên kiểm tra giá trị cuối cùng mà bean hoặc component nhận được. Nếu mục tiêu là kiểm tra riêng thứ tự property source, có thể đọc danh sách nguồn trong Environment.

### 8.1. Kiểm tra giá trị hiệu lực

```java
@SpringJUnitConfig(PropertyTestConfiguration.class)
@TestPropertySource(properties = "app.mode=test")
class EnvironmentPropertyTest {

    @Autowired
    private Environment environment;

    @Test
    void testPropertyOverridesApplicationDefault() {
        assertEquals("test", environment.getProperty("app.mode"));
    }
}
```

Test này kiểm tra hợp đồng quan sát được: giá trị mà component đọc từ Environment. Nó ít phụ thuộc vào tên nội bộ của property source hơn so với việc assertion trực tiếp vị trí của một source trong danh sách.

### 8.2. Quan sát nguồn nào cung cấp một khóa

Khi chẩn đoán, có thể duyệt các nguồn theo đúng thứ tự:

```java
ConfigurableEnvironment environment =
        (ConfigurableEnvironment) applicationContext.getEnvironment();

for (PropertySource<?> source : environment.getPropertySources()) {
    if (source.containsProperty("app.mode")) {
        System.out.println(source.getName() + " contains app.mode");
    }
}
```

Nguồn đầu tiên chứa khóa là nguồn được resolver ưu tiên. Đoạn mã chỉ in tên nguồn, không in giá trị. Trong log production, không nên ghi giá trị của mọi property vì chúng có thể chứa mật khẩu, token, connection string hoặc thông tin nhạy cảm.

Nếu cần xem giá trị, hãy chỉ thực hiện trong test với khóa không nhạy cảm. Một số môi trường Spring Boot còn cung cấp endpoint chẩn đoán cấu hình, nhưng cần giới hạn quyền truy cập và tuân theo chính sách bảo mật của ứng dụng.

### 8.3. Kiểm tra conversion và giá trị mặc định

Một property có thể được tìm thấy nhưng không chuyển đổi được sang kiểu mong muốn. Test nên phân biệt lỗi không tìm thấy khóa với lỗi conversion:

```java
@Test
void convertsPropertyToInteger() {
    assertEquals(30, environment.getProperty("app.timeout", Integer.class));
}

@Test
void usesDefaultWhenPropertyIsMissing() {
    assertEquals(5, environment.getProperty(
            "app.retry.max-attempts", Integer.class, 5));
}
```

Nếu property chứa chuỗi không hợp lệ như `app.timeout=fast`, việc đọc dưới dạng `Integer` có thể phát sinh lỗi chuyển đổi. Đừng kiểm tra trường hợp đó như thể khóa không tồn tại; hai tình huống có ý nghĩa cấu hình khác nhau.

## 9. Context caching và dynamic properties

Spring TestContext có cơ chế cache ApplicationContext để giảm thời gian khởi tạo giữa các test có cùng cấu hình. Các property source và profile là một phần của cấu hình dùng để xác định context phù hợp.

`@DynamicPropertySource` thường được khai báo trong lớp cha để nhiều test class dùng chung tài nguyên, chẳng hạn một container. Tuy nhiên, nếu các lớp con kế thừa cùng một phương thức dynamic nhưng supplier trả về giá trị khác nhau theo lớp con, context cache có thể khiến một context được tái sử dụng với giá trị không như mong muốn.

Trong tình huống các dynamic properties thực sự khác nhau và làm thay đổi cấu hình context, có thể cần `@DirtiesContext` để yêu cầu TestContext loại context khỏi cache sau test phù hợp. Không nên thêm annotation này vào mọi test; nó làm giảm lợi ích cache và chỉ nên dùng khi test đã làm thay đổi context hoặc cần tách context theo dữ liệu động.

Với Testcontainers, cần đảm bảo container đã sẵn sàng trước khi supplier được dùng để tạo kết nối. Quản lý lifecycle container phải nhất quán với thời điểm Spring tạo bean datasource hoặc client. Nếu container dừng trong khi context vẫn được cache và tái sử dụng, các test sau có thể thất bại dù property source vẫn chứa URL cũ.

## 10. Những lỗi thường gặp khi cấu hình nhiều nguồn

**Giả định file test luôn thắng mọi nguồn.** `@DynamicPropertySource` có ưu tiên cao hơn `@TestPropertySource`; inline properties cũng cao hơn resource locations. Hãy xác định đúng loại nguồn đang ghi đè.

**Nhầm profile với thứ tự property source.** `@ActiveProfiles("test")` chọn cấu hình theo profile; nó không tự nâng mọi property của một file lên đầu danh sách. Cần xác định file được nạp bởi cơ chế nào và nguồn đó được đặt ở đâu.

**Nhầm Spring Framework với Spring Boot Config Data.** `@PropertySource` và `Environment` thuộc Spring Framework; việc tự động nạp `application-test.properties` theo profile là hành vi Spring Boot hoặc cần cấu hình riêng. Hãy dùng đúng tài liệu cho stack đang kiểm thử.

**Dùng `System.setProperty` nhưng quên khôi phục.** System properties là trạng thái toàn JVM và có thể ảnh hưởng các test khác. Lưu giá trị cũ, đặt giá trị test và khôi phục trong `finally` hoặc extension quản lý trạng thái.

**Kỳ vọng thứ tự component scan ổn định.** Nhiều configuration class cùng khai báo `@PropertySource` có thể được xử lý theo thứ tự không phù hợp với giả định của test. Nếu thứ tự quan trọng, cấu hình tường minh.

**Khai báo cùng khóa ở nhiều nơi nhưng không biết nguồn thắng.** Hãy kiểm tra `Environment#getProperty` và tên nguồn chứa khóa theo thứ tự. Tránh suy đoán dựa trên tên file hoặc thời điểm file được tạo.

**Không kiểm tra giá trị cuối cùng mà bean nhận.** Test chỉ xác minh property source tồn tại chưa chứng minh placeholder, binder hoặc bean được cấu hình đúng. Hãy assertion giá trị tại điểm sử dụng.

**Supplier dynamic phụ thuộc tài nguyên chưa sẵn sàng.** Nếu supplier lấy port hoặc credential của container, bảo đảm tài nguyên được khởi động trước lúc bean cần property được tạo.

**Đưa bí mật vào inline test properties hoặc log.** Dùng dữ liệu giả trong test và không in token, password hoặc URL có credential trong log.

## 11. Quy trình xác định nguồn thắng

Khi một thuộc tính có giá trị không như dự kiến, có thể lần theo quy trình sau:

1. Xác định chính xác khóa được đọc, ví dụ `app.datasource.url`; không nhầm với một khóa tương tự.
2. Xác định cách đọc: `Environment`, `@Value`, `@ConfigurationProperties` hay API riêng của ứng dụng.
3. Xác định loại môi trường: Spring Framework thuần hay Spring Boot; MVC hay WebFlux không làm thay đổi nguyên tắc first match wins nhưng có thể thay đổi tập nguồn được đăng ký.
4. Kiểm tra profile đang hoạt động và configuration class/bean nào được chọn.
5. Liệt kê các `PropertySource` theo thứ tự hiện tại và xác định nguồn đầu tiên chứa khóa.
6. Kiểm tra `@DynamicPropertySource`, inline `@TestPropertySource`, resource test, system properties, environment variables và `@PropertySource` có cùng khai báo khóa hay không.
7. Kiểm tra conversion, placeholder default và kiểu dữ liệu tại điểm sử dụng.
8. Nếu context được cache, xác định test có đang dùng lại context với dynamic properties hoặc trạng thái toàn cục từ test trước hay không.
9. Viết test thể hiện giá trị hiệu lực mà ứng dụng phải nhận, đồng thời cô lập system property hoặc tài nguyên ngoài khi cần.

## 12. Nguyên tắc thiết kế cấu hình test

Để cấu hình dễ hiểu và ít gây ảnh hưởng giữa các test:

- Dùng file test riêng cho một nhóm giá trị có liên quan và đặt tên rõ mục đích.
- Dùng inline `@TestPropertySource` cho một vài giá trị ghi đè cục bộ.
- Dùng `@DynamicPropertySource` cho địa chỉ hoặc thông tin chỉ có sau khi tài nguyên test được khởi động.
- Dùng `@ActiveProfiles` để chọn bean/configuration phù hợp cho test.
- Hạn chế sửa system properties và environment toàn cục; nếu bắt buộc, luôn khôi phục trạng thái.
- Không đưa bí mật production vào file cấu hình test.
- Kiểm tra giá trị cuối cùng tại bean hoặc service cần cấu hình.
- Chỉ dùng `@DirtiesContext` khi thực sự cần loại context khỏi cache.

Khi hiểu rõ `Environment`, `PropertySource` và quy tắc ưu tiên của Spring TestContext, ta có thể dự đoán giá trị nào sẽ được chọn khi nhiều nguồn cùng khai báo một khóa. Profile giúp chọn cấu hình phù hợp với ngữ cảnh chạy; property source quyết định giá trị hiệu lực; còn test nên xác minh giá trị mà thành phần thực sự nhận được. Đây là nền tảng để cấu hình Spring test ổn định, tái lập được và dễ chẩn đoán khi local, CI hoặc môi trường triển khai cung cấp các nguồn cấu hình khác nhau.

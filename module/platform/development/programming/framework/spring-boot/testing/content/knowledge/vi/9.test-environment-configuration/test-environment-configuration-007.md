# Spring Boot Testing: Thứ tự ưu tiên cấu hình và cách xác minh giá trị thực sự được dùng

## 1. Vì sao cùng một key lại có nhiều giá trị?

Trong dự án Spring Boot, cùng một thuộc tính có thể được khai báo tại nhiều nơi: `application.properties`, `application-test.yml`, biến môi trường, JVM `-D...`, command-line, `@SpringBootTest(properties = ...)`, `@TestPropertySource` hoặc một `@DynamicPropertySource` trả giá trị lúc chạy Testcontainers.

Ví dụ, `demo.checkout.retries` có thể bằng 2 trong file chung, 7 trong file profile `test` và 12 trong biến môi trường CI. Vậy **giá trị nào service thực sự nhận**?

Cần tách ba câu hỏi thường bị nhập làm một:

1. **Giá trị nào đã được khai báo?** Mỗi file hoặc nguồn chỉ cho biết một *ứng viên*.
2. **Giá trị nào thắng trong `Environment`?** Spring duyệt các `PropertySource` theo thứ tự ưu tiên; nguồn có giá trị phù hợp xuất hiện trước thường thắng.
3. **Giá trị nào đã được bean sử dụng?** Bean có thể nhận qua `@Value`, `@ConfigurationProperties`, constructor, connection-details, giá trị tính sẵn, hoặc caching. Kết quả trong `Environment` không phải lúc nào cũng chứng minh một client đang dùng đúng cấu hình đó.

Bài học tập trung vào **cấu hình môi trường test**, không chỉ ghi nhớ một bảng ưu tiên. Mục tiêu là dự đoán được giá trị phổ biến, xác minh giá trị thực bằng một bài test, tìm đúng nguồn đã cấp giá trị, và nhận ra trường hợp kiểm `Environment` chưa đủ.

### Kết quả học tập

- Hiểu `PropertySource`, thứ tự override, cách hoạt động của config data và active profile.
- Phân biệt nguồn giá trị chung với các override riêng cho kiểm thử: `@SpringBootTest(properties)`, `@TestPropertySource` và `@DynamicPropertySource`.
- Viết integration test Java 17+ kiểm đồng thời `Environment`, `@Value`, `@ConfigurationProperties` và active profiles.
- Tìm nguồn thắng bằng `ConfigurableEnvironment.getPropertySources()`, thông tin origin và Actuator `env`/`configprops`.
- Xử lý lỗi do cấu hình CI, profile, test context cache, biến môi trường, thứ tự YAML/properties và Testcontainers.
- Không tiết lộ secret khi chẩn đoán; không thay global system properties bừa bãi trong parallel tests.

## 2. Mô hình đúng: PropertySource và cách chọn giá trị

Spring cung cấp một `Environment` chứa nhiều `PropertySource`. Một `PropertySource` có tên và khả năng trả một giá trị cho key. Với `ConfigurableEnvironment`, ta có thể duyệt chúng qua `getPropertySources()` **theo thứ tự ưu tiên từ cao xuống thấp**.

Hình dung:

~~~text
ConfigurableEnvironment
  |
  +-- Nguồn ưu tiên cao: demo.checkout.mode = "test-inline"
  |
  +-- Nguồn kế tiếp:   demo.checkout.mode = "boot-inline"
  |
  +-- Một nguồn khác:  không có demo.checkout.mode
  |
  +-- Config data:     demo.checkout.mode = "profile"
  |
  +-- Config data:     demo.checkout.mode = "default"
  |
  +-- Các nguồn ưu tiên thấp hơn
             |
             v
   getProperty("demo.checkout.mode")
   -> "test-inline"  (nguồn phù hợp đầu tiên)
~~~

Trong một ví dụ đơn giản, **một key không được ghép chuỗi từ nhiều nguồn**; nguồn ưu tiên cao có giá trị hợp lệ sẽ che giá trị cùng key ở nguồn thấp hơn. Tuy nhiên, **binding một object phức tạp** không luôn tương đương từng lời gọi `getProperty(key)`:

- Với các **thuộc tính đơn** như `demo.checkout.retries`, phép override thường rất dễ hiểu.
- Với `@ConfigurationProperties`, cơ chế *relaxed binding*, chuyển kiểu và merge/replace collection có quy tắc riêng. Trong Spring Boot, **list từ nguồn ưu tiên cao thường thay thế list**, không nối các phần tử list từ nhiều file; map có thể có quy tắc kết hợp giá trị theo key.
- Với placeholder `${...}`, giá trị được tham chiếu được resolve từ `Environment`; tham chiếu lồng nhau có thể làm nguồn cuối cùng không hiển nhiên.
- Với bean đã khởi tạo, thay đổi `System.setProperty` hoặc biến môi trường sau đó không tự làm mọi bean bind lại.

Do đó phải kiểm **cùng key, cùng profile, cùng giai đoạn của vòng đời ứng dụng, cùng phiên bản Spring Boot** và cuối cùng kiểm giá trị của bean/client nếu đó là thứ nghiệp vụ sử dụng.

## 3. Thứ tự ưu tiên phổ biến trong Spring Boot

Spring Boot 3.5 và 4.x mô tả các nguồn cấu hình trong một thứ tự; **nguồn ở phần sau có thể override nguồn ở phần trước**. Đối với dự án test thông thường, bức tranh tổng quát từ mức ưu tiên thấp đến cao là:

| Tầng | Nguồn | Ví dụ | Ý nghĩa |
| --- | --- | --- | --- |
| 1 | Default properties do ứng dụng đặt | `SpringApplication.setDefaultProperties(...)` | Giá trị dự phòng |
| 2 | `@PropertySource` trên `@Configuration` | File custom properties | Có thể được nạp muộn; không phù hợp cho một số cấu hình bootstrap |
| 3 | Config data | `application.properties`, `application-test.yml`, file ngoài jar | Các default thường dùng cho ứng dụng và profile |
| 4 | `RandomValuePropertySource` | `random.uuid`, `random.int` | Chỉ cung cấp nhóm key `random.*` |
| 5 | OS environment variables | `DEMO_CHECKOUT_RETRIES` | Override file thông thường |
| 6 | JVM system properties | `-Ddemo.checkout.retries=12` | Thường thắng OS environment trên cùng key |
| 7 | JNDI / ServletContext / ServletConfig | Một số môi trường servlet hoặc application server | Chỉ xuất hiện khi hạ tầng đó cung cấp |
| 8 | `SPRING_APPLICATION_JSON` | JSON đưa qua env hoặc system property | Override nhiều nguồn truyền thống |
| 9 | Command-line args | `--demo.checkout.retries=15` | Thắng file, env và JVM property trong cơ chế thông thường |
| 10 | Test properties của Boot | `@SpringBootTest(properties = "...")` | Override riêng trong test context |
| 11 | Test property sources / dynamic properties | `@TestPropertySource`, `@DynamicPropertySource` | Các cơ chế có ưu tiên cao trong test; xem phân biệt bên dưới |
| 12 | Devtools global settings khi bật | Cấu hình devtools người dùng | Có thể đứng rất cao, thường không nên dựa vào trong CI |

**Lưu ý quan trọng về tầng 11:** tài liệu Spring Framework TestContext quy định rõ `@DynamicPropertySource` có ưu tiên cao hơn các giá trị đến từ `@TestPropertySource`, còn bảng tổng quan ở một số tài liệu Spring Boot liệt kê hai mục trong thứ tự có thể gây cách hiểu ngược. Đừng tạo một test phụ thuộc vào xung đột giữa **cùng một key** được khai báo bởi cả hai cơ chế nếu không xác minh trên đúng phiên bản/dàn test của dự án. Chọn một nơi override có chủ đích và dùng phương pháp dò nguồn thắng tại mục 7 để chứng minh thực tế.

Mục 1–9 là **sơ đồ khái quát**, không phải lời hứa mọi `ApplicationContext` luôn có đủ các tầng. Test không khởi động servlet không có servlet config; test được chạy trực tiếp qua IDE có thể không có command-line property như `java -jar`; devtools thường không phải thành phần của test runner.

**Các bất biến thực hành đáng ghi nhớ:**

- Giá trị trong `application-test.properties` **không mặc nhiên** thắng `-Ddemo.checkout.retries=12`; JVM system property là nguồn ưu tiên cao hơn config data.
- `@ActiveProfiles("test")` chọn profile test, nhưng **không biến** tất cả giá trị từ `application-test.properties` thành nguồn ưu tiên cao nhất.
- Override test inline có thể thắng cả cấu hình máy chạy/CI; hãy sử dụng nó có mục đích để cô lập test.
- Giá trị `null` trong `SPRING_APPLICATION_JSON` được xử lý như thiếu property khi lookup; không dùng nó để xóa giá trị từ nguồn thấp hơn.
- `@PropertySource` được thêm khi context refresh; nó có thể **quá muộn** để đổi vài thuộc tính được Spring Boot đọc sớm, ví dụ `logging.*` hay `spring.main.*`.

## 4. Thứ tự nằm bên trong tầng Config Data

Một nguồn thường bị hiểu nhầm: **“File tên application-test thì luôn thắng mọi file application”**. Sự thật phụ thuộc **vị trí file, profile active, kiểu tài liệu và cách import**.

Ở cấu hình mặc định, các nhóm config data quan trọng đi từ ưu tiên thấp đến cao:

1. `application.properties` / YAML **bên trong classpath/jar**.
2. `application-{profile}.properties` / YAML **bên trong classpath/jar** cho profile đang active.
3. `application.properties` / YAML **bên ngoài jar** tại vị trí cấu hình được nạp.
4. `application-{profile}.properties` / YAML **bên ngoài jar** tại vị trí cấu hình được nạp.

Đây là cách nhìn theo **nhóm file**, không phải danh sách đầy đủ của tất cả cơ chế location/import. Trong từng nhóm, thứ tự vị trí cụ thể, document trong một file, `spring.config.import` và profile hoạt động có thể tiếp tục ảnh hưởng giá trị cuối.

### 4.1 Cấu hình chung và profile-specific

Ví dụ:

File `src/test/resources/application.properties`:

~~~properties
demo.checkout.mode=base
demo.checkout.retries=2
~~~

File `src/test/resources/application-test.properties`:

~~~properties
demo.checkout.mode=profile-test
~~~

Khi test context khởi động với `@ActiveProfiles("test")`, kết quả thông thường là:

~~~text
demo.checkout.mode    = profile-test
demo.checkout.retries = 2
~~~

`mode` được ghi đè trong file profile, nhưng `retries` không khai báo ở profile nên kế thừa từ config data chung. **Không phải profile đã xóa toàn bộ những key của file nền.**

Nếu cùng một key có trong nhiều profile-specific files và nhiều profiles active, **thứ tự profile cuối có thể thắng** theo quy tắc của Spring Boot; không nên dựa vào việc trùng key giữa quá nhiều profiles. Với `spring.profiles.include` và profile groups, những profile phụ cũng tham gia; hãy xác nhận danh sách thực tế bằng `Environment.getActiveProfiles()`.

### 4.2 .properties so với YAML

Khi file `application.properties` và `application.yml` cùng một location, Spring Boot ưu tiên `.properties`. Dùng nhất quán **một định dạng chính** cho từng nhóm cấu hình; tránh đặt cùng key ở cả hai file rồi phải giải đoán precedence.

File YAML trong `src/test/resources/application-test.yml` là **config data** hợp lệ. Nhưng `@TestPropertySource(locations = "classpath:/overrides.yml")` không mặc định hỗ trợ YAML giống properties file trong mọi phiên bản/configuration: Spring Framework hỗ trợ properties/XML theo mặc định; dùng custom `PropertySourceFactory` khi cần format khác, hoặc chọn một file `.properties` cho `@TestPropertySource`.

### 4.3 Config location, additional location và import

- `spring.config.location` **thay thế** các vị trí tìm mặc định.
- `spring.config.additional-location` **bổ sung** vị trí, thường cho phép giá trị bổ sung ghi đè default.
- `spring.config.import` có thể nạp config từ file, config tree hoặc nguồn khác; tài liệu Spring Boot quy định thứ tự import riêng, không thể chỉ đoán theo tên file.
- `optional:` cho phép thiếu một location không làm ứng dụng fail; nếu typo path mà lại dùng `optional:`, file có thể âm thầm không được nạp.
- `spring.config.name`, `spring.config.location` và `spring.config.additional-location` được xử lý **rất sớm**. Đặt chúng tại env/system property/command-line hoặc nơi được xử lý đủ sớm, thay vì chỉ cố cấu hình qua bean `@PropertySource` được tạo sau.

Nếu một dự án đa module có cả `src/main/resources/application.properties` và `src/test/resources/application.properties`, test runtime classpath có thể chứa hai tài nguyên cùng tên. Kết quả phụ thuộc cách build tạo classpath và cơ chế nạp; thiết kế test nên tránh dựa vào “định nghĩa trùng ở cùng classpath path sẽ tự hợp nhất theo suy đoán”. Dùng cấu hình profile, test properties hoặc location minh bạch.

## 5. Các override dành riêng cho test context

### 5.1 @ActiveProfiles: chọn tập cấu hình, không trực tiếp là giá trị cho mọi key

~~~java
@ActiveProfiles("test")
@SpringBootTest
class CheckoutIntegrationTest {
    // Test context nạp profile "test".
}
~~~

Đoạn này chỉ minh họa annotation trong dự án Spring Boot có application class; **không phải file test độc lập**. `@ActiveProfiles` khai báo profile dùng bởi Spring TestContext. Để biết đúng tập đang active:

~~~java
@Autowired Environment environment;

// Bên trong một phương thức @Test:
assertTrue(Arrays.asList(environment.getActiveProfiles()).contains("test"));
~~~

Cần import `java.util.Arrays`, `org.springframework.core.env.Environment`, `Autowired` và assertion JUnit; đoạn này cũng **không độc lập**.

**Đừng chỉ đọc `environment.getProperty("spring.profiles.active")` để kết luận có hay không một `@ActiveProfiles`.** Một profile được kích hoạt qua TestContext không bắt buộc biểu hiện như một literal `spring.profiles.active` trong cùng nguồn bạn đang kiểm.

### 5.2 @SpringBootTest(properties = ...): override theo test class

~~~java
@SpringBootTest(properties = {
    "demo.checkout.retries=3",
    "demo.checkout.mode=from-test-annotation"
})
class CheckoutServiceIntegrationTest {
    // ...
}
~~~

`properties` tại `@SpringBootTest` và các test slices tương ứng đưa key-value vào test `Environment` với mức ưu tiên cao hơn config data, env và JVM/CLI thông thường của ứng dụng. Đây là lựa chọn rõ ràng cho **một số key có giá trị cố định riêng bài test**.

Nhưng nếu sau đó dùng một cơ chế test override khác cho **chính key đó**, kết quả cần dựa vào precedence thực, không chỉ dựa vào việc annotation nào viết gần lớp hơn.

### 5.3 @TestPropertySource: file và inline, hai mức trong cùng cơ chế

~~~java
@TestPropertySource(
    locations = "classpath:/checkout-test.properties",
    properties = {
        "demo.checkout.mode=from-test-inline"
    }
)
class CheckoutServiceIntegrationTest {
    // ...
}
~~~

Trong một `@TestPropertySource`, **giá trị `properties` inline thắng giá trị cùng key từ `locations`**. `@TestPropertySource` có mức ưu tiên cao so với app config, OS env và JVM system properties.

Đường dẫn tương đối và `classpath:/...` có nghĩa khác nhau; `classpath:/checkout-test.properties` chỉ tới tài nguyên ở classpath root. Một annotation `@TestPropertySource` trống có thể khiến framework thử tìm file mặc định theo tên class rồi thất bại nếu thiếu; hãy chỉ rõ locations hoặc properties khi có chủ đích.

Với test class kế thừa hoặc nested tests, `@TestPropertySource` có cơ chế inherit locations/properties. Nếu một test bất ngờ nhận giá trị khác, kiểm cả annotation trên **lớp cha, meta-annotation và test configuration**; không chỉ xem class hiện tại.

### 5.4 @DynamicPropertySource: giá trị do supplier cấp lúc runtime

Khi port của Testcontainers, stub server hay service ngoài thay đổi sau khi khởi tạo, khó lưu giá trị cuối trong file properties. `@DynamicPropertySource` cho phép đăng ký supplier:

~~~java
@DynamicPropertySource
static void externalProperties(DynamicPropertyRegistry registry) {
    registry.add("demo.remote.url", () -> "http://127.0.0.1:19090");
}
~~~

Method phải **static**, nhận đúng một `DynamicPropertyRegistry`, trả `void`. Giá trị được cấp bằng supplier khi cần resolve; trong ví dụ đây là chuỗi cố định để bài test không cần khởi động container, nhưng ngoài thực tế có thể là `container::getJdbcUrl` hoặc `stubServer::baseUrl`.

Spring Framework TestContext mô tả dynamic property có ưu tiên cao hơn `@TestPropertySource`. Tuy vậy, thực hành tốt vẫn là **không cố ý cung cấp cùng key ở nhiều cơ chế test override nếu không cần**, và tự quan sát nguồn thắng bằng test trong dự án cụ thể. Với superclass chia sẻ `@DynamicPropertySource` nhưng subclass dùng tài nguyên khác nhau, context cache có thể gây reuse sai; cần thiết kế context identity hoặc dùng `@DirtiesContext` có chọn lọc.

### 5.5 @ServiceConnection và ConnectionDetails không luôn tương đương một property

Trong Spring Boot hỗ trợ Testcontainers service connections, `@ServiceConnection` có thể tạo các bean **`ConnectionDetails`** để Spring auto-configuration tạo datasource/client. Khi đó, một `DataSource` thực tế có thể sử dụng endpoint từ connection details thay vì một `spring.datasource.url` có sẵn trong `Environment`.

Do đó, để kiểm **database nào thực sự đang được kết nối**:

1. Xác minh active profile và các property có liên quan.
2. Xem bean `DataSource` / `JdbcConnectionDetails` hoặc configuration đã bind.
3. Nếu test có DB, kiểm JDBC metadata từ **connection thật**; không suy đoán chỉ từ `Environment.getProperty("spring.datasource.url")`.

Đoạn minh họa trong một integration test đã được cấu hình datasource và có kết nối khả dụng:

~~~java
@Autowired DataSource dataSource;

@Test
void connectsToExpectedDatabase() throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        String url = connection.getMetaData().getURL();
        assertTrue(url.startsWith("jdbc:postgresql:"));
    }
}
~~~

Đây **không phải file test độc lập**; cần import `javax.sql.DataSource`, `java.sql.Connection`, `java.sql.SQLException`, `@Autowired`, `@Test` và `assertTrue`. Nó chỉ kiểm JDBC URL loại PostgreSQL, không chứng minh production DB không bị chọn nhầm; có thể cần bổ sung assertion dựa vào tên DB, schema hoặc connection details của **môi trường kiểm thử**. Tránh in mật khẩu hoặc full URL có credentials.

## 6. Ví dụ hoàn chỉnh Java 17+: tái hiện precedence và kiểm giá trị cuối

Đây là một ví dụ **chạy được trong module Spring Boot 3.x có Java 17+**, không yêu cầu database, Docker, HTTP server hoặc ứng dụng production riêng. Ta sẽ cố tình đặt cùng key ở bốn nơi để quan sát override:

- File config data chung.
- File config data theo profile `test`.
- File test-only `@TestPropertySource(locations = ...)`.
- Inline test annotation `@SpringBootTest(properties = ...)` và `@TestPropertySource(properties = ...)`.

Một key khác được `@DynamicPropertySource` cấp, nhưng **không đụng cùng key** với inline test override, để ví dụ không phụ thuộc việc phân giải thứ tự giữa hai cơ chế ưu tiên cao.

### 6.1 Thư mục và file

~~~text
src/
  test/
    java/
      example/
        PropertyPrecedenceTest.java
    resources/
      application.properties
      application-test.properties
      priority-test.properties
~~~

Trong dự án Spring Boot chuẩn có Gradle hoặc Maven, `src/test/resources` xuất hiện trên runtime test classpath. Không cần khai báo Spring `@SpringBootApplication` production vì test sẽ chứa cấu hình tối thiểu riêng.

### 6.2 File src/test/resources/application.properties

~~~properties
demo.checkout.mode=base
demo.checkout.retries=2
demo.checkout.region=base-region
demo.checkout.endpoint=http://base.invalid
~~~

### 6.3 File src/test/resources/application-test.properties

~~~properties
demo.checkout.mode=profile-test
demo.checkout.retries=7
demo.checkout.region=profile-region
demo.checkout.endpoint=http://profile.invalid
~~~

`@ActiveProfiles("test")` trong test sẽ làm file profile này tham gia. `retries=7` chỉ có ở config data; các test override tiếp theo không đụng key này để chứng minh **file profile thắng file chung**.

### 6.4 File src/test/resources/priority-test.properties

~~~properties
demo.checkout.mode=test-file
demo.checkout.region=test-file-region
~~~

File này **không tự động được nạp chỉ vì tên có chữ test**. Nó được yêu cầu tường minh trong `@TestPropertySource(locations = "classpath:/priority-test.properties")`.

### 6.5 File src/test/java/example/PropertyPrecedenceTest.java

~~~java
package example;

import java.net.URI;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.Environment;
import org.springframework.core.env.PropertySource;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@ActiveProfiles("test")
@SpringBootTest(
        classes = PropertyPrecedenceTest.TestApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "demo.checkout.mode=boot-test")
@TestPropertySource(
        locations = "classpath:/priority-test.properties",
        properties = {
                "demo.checkout.mode=test-inline",
                "demo.checkout.region=inline-region"
        })
@DisplayName("Spring Boot property precedence")
class PropertyPrecedenceTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @EnableConfigurationProperties(CheckoutSettings.class)
    static class TestApplication {
    }

    @ConfigurationProperties(prefix = "demo.checkout")
    public record CheckoutSettings(
            String mode,
            int retries,
            String region,
            URI endpoint) {
    }

    @DynamicPropertySource
    static void provideDynamicEndpoint(DynamicPropertyRegistry registry) {
        // Mô phỏng endpoint được biết tại runtime, không cần server thật.
        registry.add(
                "demo.checkout.endpoint",
                () -> "http://127.0.0.1:19090");
    }

    @Autowired
    Environment environment;

    @Autowired
    ConfigurableEnvironment configurableEnvironment;

    @Autowired
    CheckoutSettings settings;

    @Value("${demo.checkout.mode}")
    String injectedMode;

    @Test
    @DisplayName("Inline TestPropertySource ghi đè file và Boot test properties")
    void inlineTestPropertyWinsForMode() {
        assertAll(
                () -> assertEquals("test-inline",
                        environment.getRequiredProperty("demo.checkout.mode")),
                () -> assertEquals("test-inline", injectedMode),
                () -> assertEquals("test-inline", settings.mode()));
    }

    @Test
    @DisplayName("Profile test cấp key không bị override ở test")
    void activeProfileSuppliesRetries() {
        assertAll(
                () -> assertEquals(7,
                        environment.getRequiredProperty(
                                "demo.checkout.retries", Integer.class)),
                () -> assertEquals(7, settings.retries()),
                () -> assertTrue(Arrays.asList(
                        environment.getActiveProfiles()).contains("test")));
    }

    @Test
    @DisplayName("Inline properties thắng location của TestPropertySource")
    void inlineOverridesTestResource() {
        assertAll(
                () -> assertEquals("inline-region",
                        environment.getRequiredProperty("demo.checkout.region")),
                () -> assertEquals("inline-region", settings.region()));
    }

    @Test
    @DisplayName("DynamicPropertySource cấp endpoint cuối được bind")
    void dynamicEndpointIsUsed() {
        URI expected = URI.create("http://127.0.0.1:19090");

        assertAll(
                () -> assertEquals(expected.toString(),
                        environment.getRequiredProperty(
                                "demo.checkout.endpoint")),
                () -> assertEquals(expected, settings.endpoint()));
    }

    @Test
    @DisplayName("Liệt kê các nguồn có cùng key mà không đoán tên source")
    void canInspectCompetingSources() {
        List<String> candidates = sourcesContaining(
                "demo.checkout.mode");

        assertFalse(candidates.isEmpty());
        assertEquals("test-inline",
                environment.getRequiredProperty("demo.checkout.mode"));

        // Khi debug, có thể đặt breakpoint và xem candidates.
        // Không assert tên PropertySource vì nó phụ thuộc phiên bản.
    }

    private List<String> sourcesContaining(String key) {
        List<String> names = new ArrayList<>();

        // Thứ tự duyệt: ưu tiên cao đến thấp.
        for (PropertySource<?> source :
                configurableEnvironment.getPropertySources()) {
            if (source.getProperty(key) != null) {
                names.add(source.getName());
            }
        }

        return names;
    }
}
~~~

**Bài test trên độc lập về cấu hình Spring**: `@SpringBootConfiguration`, `@EnableAutoConfiguration` và `@EnableConfigurationProperties` tạo context tối thiểu để bind record `CheckoutSettings`. Không yêu cầu bean ứng dụng khác, network hay Docker. Các test sử dụng JUnit Jupiter từ Spring Boot starter test. `webEnvironment = NONE` tránh khởi tạo web server.

**Điểm thiết kế đáng chú ý:** tất cả năm phương thức kiểm thử dùng cùng một Spring test context; không sửa global properties giữa các test. Giá trị `demo.checkout.endpoint` được cấp qua supplier tĩnh. `CheckoutSettings` là record configuration properties được Spring Boot bind bằng constructor; đối tượng thật phải nhận `URI` cuối từ source thắng.

### 6.6 Vì sao kết quả được dự đoán như sau?

| Key | File chung | File profile test | Test resource | @SpringBootTest inline | @TestPropertySource inline | Dynamic | Kết quả |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `demo.checkout.mode` | `base` | `profile-test` | `test-file` | `boot-test` | `test-inline` | — | **`test-inline`** |
| `demo.checkout.retries` | `2` | `7` | — | — | — | — | **`7`** |
| `demo.checkout.region` | `base-region` | `profile-region` | `test-file-region` | — | `inline-region` | — | **`inline-region`** |
| `demo.checkout.endpoint` | `http://base.invalid` | `http://profile.invalid` | — | — | — | `http://127.0.0.1:19090` | **`http://127.0.0.1:19090`** |

Mỗi giá trị được xác minh theo hai góc nhìn:

1. `environment.getRequiredProperty(...)`: giá trị hiệu lực trong environment, có chuyển kiểu cho `Integer.class`.
2. `settings...()` hoặc `@Value`: giá trị mà bean/test field **thực sự nhận** từ Spring, không chỉ giá trị có trong file.

Với `mode`, cả ba phép đọc đều phải là `test-inline`. Với `endpoint`, không có server chạy thật, nhưng việc bind `URI` chứng minh giá trị được chuyển kiểu đúng; **không chứng minh kết nối mạng thành công**.

Nếu thông báo FAIL chỉ vì môi trường CI tiêm một key khác từ nơi có ưu tiên cao hơn, bài test sẽ chỉ ra **giá trị thực tế đã khác**. Sau đó phải điều tra source gốc, không sửa assertion thành giá trị ngẫu nhiên của máy đang chạy.

### 6.7 Cấu hình Gradle và lệnh chạy

Trong `build.gradle` của **dự án Spring Boot đã có plugin/dependency management**, những dependency cơ bản sau phải hiện diện:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây chỉ là **đoạn bổ sung**, không phải file `build.gradle` hoàn chỉnh. Java toolchain nên là Java 17 hoặc cao hơn. Với Gradle wrapper của dự án:

~~~bash
./gradlew test --tests example.PropertyPrecedenceTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.PropertyPrecedenceTest
~~~

**Kết quả dự kiến:** JUnit Jupiter phát hiện **5 test methods** và cả năm PASS trên dự án được cấu hình đúng. Test không tự in stdout; mức chi tiết Gradle/IDE thay đổi nên không có chuỗi stdout cố định. Nếu Gradle kết thúc thành công, sẽ có thông báo kiểu `BUILD SUCCESSFUL` khi các tác vụ liên quan cũng thành công.

**Lưu ý về phiên bản:** ví dụ dùng Spring Boot 3.x với constructor-bound record configuration properties và JUnit Jupiter. Với Spring Boot 4.x, kiểm migration guide của dự án và những module dependency hiện có; nguyên tắc `Environment`/TestContext vẫn liên quan, nhưng không nên sao chép mù quáng cấu hình Gradle của phiên bản khác.

## 7. Làm sao tìm chính xác nguồn đã thắng?

Giả sử test nhận `demo.checkout.mode=unexpected`. Việc tìm kiếm toàn repo bằng tên key có thể chỉ ra nhiều file, không chỉ ra file nào **thật sự được nạp và thắng**. Thay vì đoán, hãy đọc `ConfigurableEnvironment` tại runtime.

### 7.1 Duyệt PropertySource theo thứ tự

Trong test Spring Boot đã được inject `ConfigurableEnvironment`, có thể thêm phương thức trợ giúp:

~~~java
static void diagnose(ConfigurableEnvironment env, String key) {
    System.out.println("Effective: " + env.getProperty(key));
    for (PropertySource<?> source : env.getPropertySources()) {
        Object candidate = source.getProperty(key);
        if (candidate != null) {
            System.out.println(source.getName() + " -> " + candidate);
        }
    }
}
~~~

**Đây là đoạn minh họa** trong code có các import `ConfigurableEnvironment` và `PropertySource`, không phải file độc lập. Chỉ chạy với **key không nhạy cảm** như `demo.checkout.mode`, tuyệt đối không dùng để in password, private key, token hay toàn bộ biến môi trường.

Danh sách được duyệt từ ưu tiên cao xuống thấp; nguồn đầu tiên khớp theo tên key trực tiếp thường quyết định giá trị. Tuy nhiên:

- Một `PropertySource` có thể chuyển đổi tên key (đặc biệt các biến môi trường hoặc wrapper cho configuration binding).
- Giá trị effective qua `Environment` có thể được resolve placeholder và chuyển kiểu, khác dạng raw trong property source.
- `@ConfigurationProperties` có relaxed binding, nên kiểm bean đã bind là bước quan trọng bổ sung.
- Nếu application thêm custom `PropertySource`, thứ tự có thể khác sơ đồ mặc định.
- Một giá trị có thể bị wrapper/proxy/connection-details điều chỉnh ngoài Environment.

Đừng viết assertion đòi tên source phải đúng `"Inlined Test Properties"` hay tên class cụ thể; format/naming của source có thể khác giữa các version. **Assert giá trị cuối** và dùng tên source làm chẩn đoán.

### 7.2 Đọc origin (file, dòng, vị trí) khi Spring Boot cung cấp

Spring Boot hỗ trợ tracking origin cho nhiều config data sources. Có thể mở rộng đoạn helper:

~~~java
import org.springframework.boot.origin.Origin;
import org.springframework.boot.origin.OriginLookup;

static void diagnoseOrigin(ConfigurableEnvironment env, String key) {
    for (PropertySource<?> source : env.getPropertySources()) {
        Object value = source.getProperty(key);
        if (value == null) {
            continue;
        }

        Origin origin = OriginLookup.getOrigin(source, key);
        System.out.println("source=" + source.getName()
                + ", origin=" + (origin == null
                ? "not available" : origin));
    }
}
~~~

Đây là **mã minh họa cần đặt trong class/helper có import Spring**, không phải chương trình `main`. `OriginLookup.getOrigin(...)` có thể trả `null` đối với nguồn không hỗ trợ origin. Với file application properties/yaml có origin tracking, thông tin thường giúp biết **resource và vị trí tương ứng**. Với system property hoặc inline test override, có thể chỉ thấy tên source thay vì đường dẫn/dòng.

Không assert file line number trong CI: thay đổi bình luận hoặc thứ tự dòng sẽ phá test mà không ảnh hưởng behavior. Origin là **công cụ điều tra**, không phải một phần hợp đồng nghiệp vụ.

### 7.3 Phân biệt Environment với @ConfigurationProperties đã bind

Nếu `environment.getProperty("demo.checkout.retries")` trả `7` nhưng service lại sử dụng `10`, có thể do:

- Bean đã được tạo trước một lần đổi property source.
- Service tự áp dụng default/clamp/transform (ví dụ `Math.max(10, retries)`).
- Một `@Bean` khác dựng client từ `ConnectionDetails`.
- Giá trị được bind dưới tên relaxed/alias hoặc prefix khác.
- Tồn tại nhiều bean `@ConfigurationProperties` và service inject nhầm bean.
- Giá trị được cache, refresh hoặc override bởi code runtime.

Cách xác minh hiệu lực thật:

1. `Environment`: assert source resolution.
2. **Bean cấu hình**: assert `@ConfigurationProperties` hoặc `@Value` thực tế.
3. **Bean/client tiêu thụ**: assert field/getter/metadata quan sát được hoặc hành vi tạo kết nối.
4. Với database, HTTP, Kafka: test tương tác/connection thực tế nếu đó là yêu cầu, không chỉ đọc property text.

Chỉ khi bước 3 hoặc 4 phản ánh đúng mới có bằng chứng đủ mạnh rằng **runtime đang sử dụng cấu hình mong muốn**.

## 8. Actuator env và configprops: chẩn đoán ngoài test runner

Nếu ứng dụng có `spring-boot-starter-actuator`, các endpoint:

- `/actuator/env`: liệt kê property sources, active/default profiles và các property có thể nhìn thấy qua environment.
- `/actuator/env/{property.name}`: tập trung vào một key và nguồn thắng/các nguồn ứng viên.
- `/actuator/configprops`: xem các bean `@ConfigurationProperties` và dữ liệu binding, giúp phát hiện khác biệt giữa file cấu hình với object cuối.

Ví dụ **chỉ dành cho môi trường phát triển/test có quyền truy cập kiểm soát**:

~~~properties
management.endpoints.web.exposure.include=health,env,configprops
~~~

Sau khi ứng dụng **có Actuator, web server và được khởi động**, có thể dùng:

~~~bash
curl http://localhost:8080/actuator/env/demo.checkout.mode
~~~

Không giả định lệnh này chạy được trong ví dụ mục 6 vì ví dụ chọn `webEnvironment = NONE` và không bật Actuator. Endpoint cũng có thể bị đổi prefix, port, hoặc từ chối bởi Spring Security.

**Cảnh báo bảo mật:** `env` và `configprops` có thể chứa dữ liệu nhạy cảm. Spring Boot mặc định sanitizes values theo cấu hình Actuator. Đừng bật `management.endpoint.env.show-values=always` trên môi trường không bảo vệ, đừng tắt sanitization cho secret và đừng công khai endpoint chỉ để debug. Trong unit/integration test, dùng assertions cho key **không bí mật** sẽ an toàn và ổn định hơn.

## 9. Các trường hợp dễ khiến thứ tự ưu tiên bị hiểu nhầm

### 9.1 @ActiveProfiles không phải “ghi đè toàn bộ Environment”

`@ActiveProfiles("test")` chỉ chọn profile active. Các config sources khác như environment variables, JVM `-D`, test annotations có thể thắng key của profile file. Để test không bị CI phụ thuộc host, override các key quan trọng trong test context ở nơi có chủ đích.

### 9.2 JVM system properties, môi trường IDE và Gradle

Một lệnh:

~~~bash
java -Ddemo.checkout.retries=12 -jar my-app.jar
~~~

là ví dụ **JVM system property cho ứng dụng đóng gói**. Nhưng khi chạy JUnit bằng Gradle, JVM dành cho test có thể là một **forked process**; system properties của Gradle daemon, IDE và test JVM không mặc nhiên giống nhau. Nếu cần truyền property cho Gradle test task, cấu hình rõ `systemProperty` hoặc runtime test flags thay vì giả định `-D` luôn tới đúng JVM.

Ví dụ minh họa trong `build.gradle` đang tồn tại:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()
    systemProperty 'demo.checkout.retries', '12'
}
~~~

Khi áp dụng đoạn này, ngưỡng test có thể bị tác động nếu **không có nguồn test override cao hơn**. Đoạn ví dụ mục 6 vẫn sẽ thấy `retries` từ system property là `12`, không phải `7`, vì bài ví dụ **không override key retries** bằng test annotation. Đây là một thay đổi có chủ ý dùng để chứng minh mức ưu tiên; **không thêm cấu hình này vào lúc chạy bộ ví dụ 5 PASS của mục 6**.

### 9.3 OS environment variables và relaxed binding

Trong shell, `DEMO_CHECKOUT_RETRIES=12` thường tương ứng với `demo.checkout.retries` cho binding của Spring Boot. Nên dùng tên canonical kebab-case trong `@Value` và cấu trúc rõ trong `@ConfigurationProperties`. Quy tắc chuyển tên cho env phức tạp hơn thay dấu chấm bằng gạch dưới: index list và map key có hướng dẫn riêng.

Một kiểm tra `System.getenv("DEMO_CHECKOUT_RETRIES")` chỉ chứng minh shell cung cấp biến; không chứng minh `Environment` đã chọn nó. Hãy xác minh cả property thắng và bean bind.

### 9.4 YAML profile document với spring.config.activate.on-profile

Trong `application.yml`, có thể dùng nhiều YAML documents và `spring.config.activate.on-profile` để chỉ nạp một document cho profile cụ thể. Nhưng `spring.profiles.active` và `spring.profiles.default` phải nằm trong **tài liệu không profile-specific**, không được đặt trong document chỉ active trên một profile rồi kỳ vọng kích hoạt thêm profile khác.

`spring.profiles.include` và `spring.profiles.group.*` cũng có quy tắc khai báo ở non-profile-specific documents. Nếu vi phạm, Spring Boot có thể báo lỗi cấu hình hoặc môi trường profile không như dự kiến.

### 9.5 @TestPropertySource YAML và duplicate resource name

`@TestPropertySource` thường nhận properties/XML mặc định, không tự đọc YAML như Spring Boot config data. Nếu muốn dùng YAML test profile, đặt ở `application-test.yml` và kích hoạt profile; nếu cần custom location YAML trong `@TestPropertySource`, dùng factory tương ứng của Spring Framework version được hỗ trợ.

Khi hai file cùng tên xuất hiện ở nhiều module/classpath location, **không đoán cơ chế hợp nhất**. Ghi đường dẫn `classpath:/...` rõ ràng và theo dõi origin.

### 9.6 Test context caching

Spring TestContext **cache ApplicationContext** giữa các lớp test có cấu hình context tương đương. Nếu test A thay `System.setProperty("demo.checkout.retries", "99")` giữa suite rồi test B tái sử dụng context hoặc bean đã bind, kết quả dễ khó hiểu. Đặt configuration ở **test annotation/fixture** thay vì đổi process-global state.

Nếu dynamic properties khác nhau theo subclass nhưng chia sẻ cấu hình base class, có thể cần tách context cấu hình hoặc dùng `@DirtiesContext` có chọn lọc. Tuy nhiên `@DirtiesContext` tốn chi phí khởi động lại, không nên dùng cho mọi test chỉ để chữa tình trạng cấu hình thiếu minh bạch.

### 9.7 Thứ tự khai báo trong code không phải thứ tự precedence

Việc đặt `@TestPropertySource` trước `@SpringBootTest` trong source code, hay đặt hai dòng trong annotation theo thứ tự khác, không xác định ưu tiên. Cơ chế của Spring Boot và Spring TestContext quyết định. Đừng dựa vào số thứ tự annotation khi code review.

### 9.8 ConnectionDetails có thể vượt khỏi “giá trị key”

Trong Spring Boot với service connections, giá trị `spring.datasource.url` đọc được không chứng minh JDBC connection cuối dùng URL đó. Test cần xem `DataSource` thật hoặc connection metadata và đảm bảo không kết nối nhầm production database. Đây là lý do một bài học về **“giá trị thực sự được dùng”** không dừng ở việc đọc property source.

## 10. Chiến lược test để chống lỗi cấu hình theo môi trường

Bảng lựa chọn kiểm thử:

| Điều bạn muốn chắc chắn | Kiểu kiểm tra | Ví dụ assertion |
| --- | --- | --- |
| Test dùng profile nào | `Environment.getActiveProfiles()` | Có `test` trong tập active |
| Config data profile override key chung | Spring context test | `retries == 7` |
| Inline test override thắng file | `@TestPropertySource` + env | `mode == "test-inline"` |
| Bean nhận giá trị đã bind | `@ConfigurationProperties` / `@Value` | `settings.mode()` đúng |
| API endpoint động đã được đăng ký | `@DynamicPropertySource` | `settings.endpoint()` đúng |
| Nguồn nào cấp property | `ConfigurableEnvironment.getPropertySources()`, origin | Tên source đầu tiên có key |
| Hệ thống kết nối DB nào | Integration test với `DataSource` thật | JDBC URL/schema/metadata hợp lệ |
| Biến môi trường CI có bị chặn bởi test override | Test chạy trên CI với input được kiểm soát | Kết quả cuối như đã định |
| Secret không bị lộ khi debug | Security review, Actuator sanitization | Không log plain-text credentials |

Không phải tất cả bài test đều cần `@SpringBootTest`. Với một class dùng `@ConfigurationProperties` và validation, có thể test binding bằng `ApplicationContextRunner` hoặc test slice phù hợp để tránh khởi động toàn ứng dụng; nhưng khi muốn xác nhận **config data/profile/test annotation của đúng Spring Boot context**, một integration test có cấu hình như mục 6 thường dễ giải thích hơn.

### Không nên tự sửa assertion để “theo môi trường”

Nếu `retries` chạy trên CI bằng 12 thay vì 7, đừng chỉ sửa `assertEquals(7, ...)` thành 12 mà chưa hiểu nguồn. Hãy xác định CI có một `-D` hoặc env variable không, property được truyền tới test JVM ra sao, và test có cần override cố định để độc lập hay thực sự muốn thử tương tác với host environment.

Test đúng mục tiêu phải mô tả **giá trị được kỳ vọng theo hợp đồng**; mục tiêu đó quyết định có cho phép giá trị host override hay không.

## 11. Quy trình điều tra một giá trị cấu hình bất ngờ

Giả sử Spring service có request timeout 30 giây trong dev nhưng CI trả 5 giây:

1. **Chỉ ra key chính xác** bean sử dụng, ví dụ `demo.http.request-timeout`, tránh đọc nhầm `server.tomcat.connection-timeout` là một thuộc tính khác.
2. **Xác định context và phase:** test được chạy qua `@SpringBootTest`, `@WebMvcTest` hay không có Spring context? Bean đã bind lúc khởi động hay tính mỗi request?
3. **Đọc profile thực tế:** `getActiveProfiles()`, kiểm profile group/include, không chỉ nhìn tên file.
4. **Đọc effective property:** `environment.getProperty(key)`, kèm kiểu khi có thể.
5. **Duyệt các sources theo precedence:** tìm nơi đầu tiên có giá trị cùng key, xem các ứng viên sau bị che.
6. **Đọc origin khi có:** file, dòng, resource, system/environment/test inline source.
7. **Đọc bean thật:** `@ConfigurationProperties`, `@Value`, client settings, timeout builder hoặc connection details, tùy cách ứng dụng tiêu thụ.
8. **Kiểm đầu vào runtime:** IDE run config, Gradle test JVM, CI secrets/env, Maven Surefire system properties, command-line args.
9. **Quyết định sửa tại đúng tầng:** đổi config data/profile, thêm test override, sửa tên key, sửa bean binding, hay sửa wiring của container/connection details.
10. **Khóa lại bằng regression test:** assert giá trị dự kiến và bean tiêu thụ, không hardcode tên source dễ thay đổi.

Ví dụ test cụ thể về bean `CheckoutSettings` ở mục 6 là một **regression test**: nếu đổi thứ tự cấu hình hoặc vô tình bỏ `@ActiveProfiles("test")`, ít nhất các assertions về retries/profile sẽ báo lỗi.

## 12. Các sai lầm thường gặp

**Sai lầm 1 — “application-test.properties luôn có ưu tiên cao nhất.”**  
Không đúng. File profile là config data; environment vars, JVM system properties, một số command-line và test overrides có thể thắng. Giải pháp: kiểm `Environment` và bean.

**Sai lầm 2 — “Đã ghi @ActiveProfiles nên Environment chắc chắn có spring.profiles.active=test.”**  
`@ActiveProfiles` tác động vào TestContext; nguồn property literal có thể khác. Dùng `getActiveProfiles()` làm bằng chứng.

**Sai lầm 3 — “Tên file priority-test.properties có test nên tự nạp.”**  
Không đúng. Một file tùy ý cần được tham chiếu bởi `@TestPropertySource`, `spring.config.import` hoặc cách nạp minh bạch khác.

**Sai lầm 4 — “Cứ chuyển YAML vào @TestPropertySource(locations=...) là hoạt động như application.yml.”**  
Spring TestContext không mặc định hỗ trợ mọi format tại locations. Với YAML, dùng config data hoặc factory phù hợp.

**Sai lầm 5 — “Thêm @PropertySource là có thể override mọi cấu hình startup.”**  
Nhiều thuộc tính logging/main được đọc sớm hơn thời điểm source được thêm lúc refresh. Dùng nguồn externalized configuration đúng giai đoạn.

**Sai lầm 6 — “@SpringBootTest(properties) và @TestPropertySource giống nhau hoàn toàn.”**  
Chúng là các đường khai báo khác nhau và có quan hệ precedence cần hiểu. Đừng dùng cùng key ở nhiều nơi nếu không chủ đích kiểm override.

**Sai lầm 7 — “DynamicPropertySource luôn được gọi một lần tại thời điểm method đăng ký.”**  
Registry nhận supplier; giá trị được cung cấp khi resolve, không phải nhất thiết tại dòng đăng ký. Nếu supplier có side effect hoặc đọc state thay đổi theo thời gian, test có thể không ổn định.

**Sai lầm 8 — “Đọc Environment là đủ chứng minh JDBC client đang dùng đúng URL.”**  
Không đúng khi connection details, client builder hoặc cache khác tác động. Kiểm bean/client thật và connection khi cần.

**Sai lầm 9 — “Đổi System.setProperty trong @BeforeEach sẽ cô lập từng test.”**  
System properties là trạng thái toàn JVM và ảnh hưởng song song/context caching. Ưu tiên test annotations; nếu buộc đổi, quản lý khôi phục và cô lập nghiêm ngặt.

**Sai lầm 10 — “Source đầu tiên có tên giống kỳ vọng đồng nghĩa giá trị được bind đúng.”**  
Tên source chỉ là metadata; binder có thể có relaxed binding và conversion. Assert cả bean thật.

**Sai lầm 11 — “Env var dùng dấu gạch dưới được phép suy luận tùy ý.”**  
Quy tắc relaxed binding của Spring Boot có hướng dẫn cụ thể (case, dấu gạch nối, chỉ số list). Kiểm tên canonical và kết quả bind thực tế.

**Sai lầm 12 — “Mọi key nằm trong ứng dụng đều có thể log để debug.”**  
Không được log secret, password, token, key hoặc toàn bộ `Environment`/Actuator values. Chỉ truy vấn key an toàn, phân quyền endpoint và tôn trọng sanitization.

**Sai lầm 13 — “Không cần biết phiên bản vì mọi tài liệu precedence giống hệt.”**  
Spring Boot, Spring Framework, test runner và các cơ chế bổ sung có thể thay đổi. Khi hai trang tài liệu mô tả xung đột giữa các test-specific sources theo cách không thống nhất, phép đo trong context đang chạy là cách chốt chính xác. Tránh thiết kế test dùng cùng key ở nhiều cơ chế ưu tiên cao không cần thiết.

**Sai lầm 14 — “Danh sách trong config luôn được cộng dồn từ profile và file chung.”**  
Với `@ConfigurationProperties`, binding list thường bị thay thế bởi giá trị ở nguồn ưu tiên cao hơn. Kiểm object sau bind thay vì tự ghép theo giả định.

## 13. Thực hành nâng cao: kiểm chính bean tiêu thụ thay vì chỉ kiểm key

Có những cấu hình ảnh hưởng hành vi theo cách không thể kiểm bằng `getProperty` đơn thuần.

### Timeout của HTTP client

Bean xây ở `@Configuration` có thể đọc `demo.http.timeout` rồi nhân/chuyển sang `Duration`. Test nên kiểm chính cấu hình timeout trong client builder nếu API cho phép, hoặc kiểm hành vi với stub server điều khiển được. Không assert một số raw `5000` rồi mặc định nghĩ client đang dùng 5 giây.

### Kết nối database Testcontainers

Nếu dùng `@DynamicPropertySource`, có thể supply `spring.datasource.url` từ `container::getJdbcUrl`; nếu dùng `@ServiceConnection`, auto-configuration có thể nhận `ConnectionDetails`. Hai thiết kế khác nhau; đừng vô tình cấu hình hai nguồn cạnh tranh rồi đoán thứ tự. Test integration nên kiểm connection metadata/schema hoặc chạy một truy vấn thực sự trên database container.

### Mapping @ConfigurationProperties có default

Record hoặc bean có giá trị mặc định có thể không nhận trực tiếp source property nếu source thiếu, hoặc validation có thể từ chối một giá trị không hợp lệ. Test phải khẳng định **giá trị cuối ở bean** và case thiếu/invalid, không chỉ nguồn gốc raw. Đặc biệt chú ý đơn vị `Duration`, `DataSize` và enum case-insensitivity nếu code dựa vào chuyển kiểu.

### Hệ thống có refresh hoặc dynamic configuration

Một số ứng dụng dùng config server, refresh scopes, `EnvironmentChangeEvent` hoặc code tự cập nhật runtime. Khi đó cần định nghĩa “thực sự được dùng” tại **thời điểm nào**. Unit test binding lúc startup và integration test refresh có thể phải tách riêng; đừng mặc định mọi bean tự cập nhật khi property source thay đổi.

## 14. Checklist trước khi chốt cấu hình test

- [ ] Biết rõ **key canonical** và **bean/client tiêu thụ** thuộc tính ấy.
- [ ] Phân biệt file chung, file profile, external config, OS env, JVM system props, command-line và các test annotations.
- [ ] `@ActiveProfiles` được kiểm bằng `getActiveProfiles()`; không suy đoán từ filename.
- [ ] Nếu có `@TestPropertySource`, xác định `locations` và `properties` inline; inline có thể ghi đè file.
- [ ] Với `@DynamicPropertySource`, method static, nhận `DynamicPropertyRegistry` và supplier không phụ thuộc state chập chờn.
- [ ] Tránh dùng cùng một key ở nhiều test-specific high-precedence sources trừ khi chính precedence là nội dung test.
- [ ] Đã xác minh effective value bằng `Environment` và **bean đã bind** (`@Value`/`@ConfigurationProperties`) khi phù hợp.
- [ ] Khi cần tìm nguyên nhân, duyệt `ConfigurableEnvironment.getPropertySources()` theo thứ tự và đọc origin nếu có.
- [ ] Nếu dùng `@ServiceConnection`/`ConnectionDetails`, kiểm client/connection thật thay vì chỉ đọc `spring.datasource.url`.
- [ ] Không dùng `System.setProperty` không kiểm soát giữa các test hoặc làm bẩn context cache.
- [ ] Biến môi trường CI/test JVM được chủ động cấu hình, không phụ thuộc thiết lập riêng của máy người phát triển.
- [ ] Không ghi secret vào log, không công khai Actuator `env`/`configprops` hoặc tắt sanitization để tiện debug.
- [ ] Phép đo precedence được thực hiện trên **đúng Spring Boot/Framework version** và đúng kiểu test context.
- [ ] Regression test tập trung vào hợp đồng: cấu hình được chọn và tác động thật lên bean/đầu ra.

**Kết luận:** thứ tự ưu tiên cấu hình chỉ là **bản đồ**. Nguồn sự thật khi chạy test là `Environment` và những bean/client đã được tạo từ nó. Khi hai nơi cùng khai báo một key, đừng sửa cấu hình bằng trực giác: hãy xác minh profile active, nguồn thắng và giá trị đã bind, sau đó đặt override test ở một nơi rõ ràng và khóa hành vi bằng assertion.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): property source order, config data locations, profile-specific files và các test overrides.
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): `spring.profiles.active`, `spring.profiles.include`, profile groups và thứ tự.
- [Spring Framework — Context Configuration with Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): `@TestPropertySource`, inline/file precedence và inheritance.
- [Spring Framework — Context Configuration with Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): `@DynamicPropertySource`, dynamic supplier, relative precedence và context cache.
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): `Environment`, `ConfigurableEnvironment` và `PropertySource`.
- [Spring Boot — Actuator Environment Endpoint](https://docs.spring.io/spring-boot/api/rest/actuator/env.html): xem property sources, origin và property effective ở runtime.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): `env`/`configprops` và sanitization.
- [Spring Boot — OriginLookup API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/origin/OriginLookup.html): đọc origin khi property source hỗ trợ.

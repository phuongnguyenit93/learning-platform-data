# Kích hoạt profile kiểm thử bằng @ActiveProfiles trong Spring Boot

Trong Spring Boot, **profile** cho phép ứng dụng thay đổi cấu hình và bean theo môi trường: `dev`, `test`, `staging`, `prod` hoặc các tên theo nghiệp vụ. Khi chạy kiểm thử tích hợp, chúng ta thường muốn một `ApplicationContext` khác với ứng dụng thực tế: dùng cấu hình ít rủi ro, mock/fake adapter, database test và timeout ngắn; đồng thời vẫn giữ phần lớn wiring Spring để kiểm chứng hành vi thực.

Annotation **`@ActiveProfiles`** của Spring TestContext Framework giải quyết nhu cầu này: nó khai báo những **bean definition profiles** cần được kích hoạt khi Spring tải `ApplicationContext` cho một test class.

Ví dụ đơn giản:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderApplicationTest {

    @Test
    void contextLoads() {
        // Spring khởi tạo context với profile "test".
    }
}
~~~

Khi cấu hình Spring Boot thông thường được nạp, profile `test` còn khiến file **`application-test.yml`** hoặc **`application-test.properties`** thích hợp được xét trong hệ thống Config Data. Điều này giúp các test dùng giá trị cấu hình riêng mà không cần sửa `application.yml` dành cho ứng dụng.

Bài học dùng **Spring Boot 3.3.x, Spring Framework 6.1.x, JUnit Jupiter và Java 21**. Nội dung phân biệt profile của test với property override, trình bày ví dụ hoàn chỉnh, cách kế thừa profile, profile resolver, interaction với TestContext cache, các test slice và những lỗi thường gặp.

## 1. @ActiveProfiles giải quyết vấn đề gì?

Giả sử ứng dụng bán hàng có hai adapter gửi thông báo:

- `SmtpNotificationSender`: gửi SMTP thật trong một số môi trường.
- `FakeNotificationSender`: lưu sự kiện trong bộ nhớ, không gửi email ra bên ngoài.

Ngoài ra, cấu hình sản xuất có thể sử dụng hệ thống thanh toán thật hoặc queue bên ngoài. Nếu test khởi động với profile không đúng, nó có nguy cơ kết nối nhầm hệ thống thật, đòi hỏi credential production hoặc gửi dữ liệu ngoài ý muốn.

Với `@ActiveProfiles("test")`, test có thể lựa chọn bean dành riêng cho profile test và nhận các property dành cho môi trường kiểm thử.

~~~text
Test class
  |
  +-- @SpringBootTest
  |
  +-- @ActiveProfiles("test")
              |
              v
     Spring TestContext Framework
              |
              v
       ApplicationContext
              |
              +-- @Profile("test") bean
              +-- @Profile("!test") bean bị loại
              +-- application.yml
              +-- application-test.yml
              |
              v
       Test assertions
~~~

**Phân biệt:** `@ActiveProfiles` chỉ khai báo profile cho **context do Spring TestContext tải**. Một unit test thuần chỉ chạy Java objects do `new` tạo ra, không dựng Spring context, sẽ không có tác dụng gì khi thêm annotation này.

## 2. Package, dependency và phạm vi áp dụng

Import đúng:

~~~java
import org.springframework.test.context.ActiveProfiles;
~~~

Đây là annotation thuộc module **spring-test**, được `spring-boot-starter-test` cung cấp trong các ứng dụng Spring Boot thông thường.

### Maven

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

### Gradle Groovy DSL

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### Gradle Kotlin DSL

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Trong dự án Spring Boot 3.3, Spring TestContext được tích hợp với JUnit Jupiter qua extension phù hợp. `@SpringBootTest` của Spring Boot đã khai báo cách tích hợp cần thiết để chạy test với Spring; không cần thêm `@ExtendWith(SpringExtension.class)` một lần nữa chỉ cho ví dụ này.

Annotation `@ActiveProfiles` được sử dụng ở **cấp class**. Nó có thể áp dụng trên test class hoặc meta-annotation và được kế thừa theo quy tắc của TestContext. Không gắn nó lên một test method rồi giả định rằng mỗi method trong cùng class được tạo context với một profile khác nhau.

## 3. Ví dụ tối thiểu với @SpringBootTest

Ứng dụng chính:

~~~java
package com.example.profiledemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ProfileDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProfileDemoApplication.class, args);
    }
}
~~~

File `src/main/resources/application.yml`:

~~~yaml
app:
  greeting:
    message: "Hello from default configuration"
    max-retries: 3
~~~

File `src/test/resources/application-test.yml`:

~~~yaml
app:
  greeting:
    message: "Hello from test configuration"
    max-retries: 1
~~~

Class cấu hình:

~~~java
package com.example.profiledemo.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.greeting")
public record GreetingProperties(
        String message,
        int maxRetries) {
}
~~~

Đăng ký class này bằng `@ConfigurationPropertiesScan` trên `ProfileDemoApplication`, ví dụ:

~~~java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ProfileDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProfileDemoApplication.class, args);
    }
}
~~~

Các import tương ứng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
~~~

Test:

~~~java
package com.example.profiledemo;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.profiledemo.config.GreetingProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class GreetingPropertiesTest {

    @Autowired
    GreetingProperties greeting;

    @Test
    void usesTestProfileConfiguration() {
        assertThat(greeting.message())
                .isEqualTo("Hello from test configuration");
        assertThat(greeting.maxRetries()).isEqualTo(1);
    }
}
~~~

**Điều xảy ra:**

1. JUnit phát hiện test.
2. Spring TestContext tạo merged test context configuration.
3. `@ActiveProfiles("test")` khai báo `test` là profile hoạt động cho context đó.
4. Spring Boot nạp Config Data và áp dụng các document phù hợp với profile test.
5. `GreetingProperties` được bind từ giá trị hiệu lực.
6. Assertions kiểm tra đúng dữ liệu dành cho test.

Nếu không có nguồn override ưu tiên cao hơn, `application-test.yml` sẽ ghi đè những key cùng tên từ `application.yml`.

### Vị trí file quan trọng

~~~text
src/
├── main/
│   ├── java/com/example/profiledemo/
│   │   ├── ProfileDemoApplication.java
│   │   └── config/GreetingProperties.java
│   └── resources/
│       └── application.yml
└── test/
    ├── java/com/example/profiledemo/
    │   └── GreetingPropertiesTest.java
    └── resources/
        └── application-test.yml
~~~

`src/test/resources` nằm trên classpath của test, nhưng thông thường không được đóng gói vào production JAR từ `src/main`. Đây là cách hữu ích để cô lập cấu hình kiểm thử.

## 4. @ActiveProfiles và @Profile hoạt động cùng nhau

`@Profile` dùng để điều kiện hóa việc đăng ký bean. `@ActiveProfiles` chọn profile cho context của test, từ đó quyết định bean nào thỏa điều kiện.

Định nghĩa interface:

~~~java
package com.example.profiledemo.notification;

public interface NotificationSender {
    void send(String recipient, String message);
    String kind();
}
~~~

Bean thật:

~~~java
package com.example.profiledemo.notification;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("!test")
public class ConsoleNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        System.out.println("Send to " + recipient + ": " + message);
    }

    @Override
    public String kind() {
        return "console";
    }
}
~~~

Bean test:

~~~java
package com.example.profiledemo.notification;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("test")
public class FakeNotificationSender implements NotificationSender {

    @Override
    public void send(String recipient, String message) {
        // Không phát sinh kết nối SMTP hoặc HTTP.
    }

    @Override
    public String kind() {
        return "fake";
    }
}
~~~

Test:

~~~java
package com.example.profiledemo;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.profiledemo.notification.NotificationSender;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class NotificationProfileTest {

    @Autowired
    NotificationSender sender;

    @Test
    void selectsFakeSender() {
        assertThat(sender.kind()).isEqualTo("fake");
    }
}
~~~

Với profile `test`, bean `FakeNotificationSender` phù hợp còn bean `ConsoleNotificationSender` với `@Profile("!test")` không phù hợp.

**Lưu ý thiết kế:** đặt `@Profile("!test")` trên bean thật nghĩa là nó được bật trong tất cả môi trường **không có test**, không riêng production. Nếu chỉ cho phép gửi thật ở profile xác định, có thể thay bằng `@Profile("prod")` hoặc cấu hình feature flags rõ ràng hơn. Không nên coi mọi môi trường không phải test đều an toàn.

## 5. Cú pháp @ActiveProfiles

Các hình thức tương đương về giá trị cơ bản:

~~~java
@ActiveProfiles("test")
~~~

~~~java
@ActiveProfiles({"test", "integration"})
~~~

~~~java
@ActiveProfiles(profiles = {"test", "integration"})
~~~

Thuộc tính `value` là alias cho `profiles`:

~~~java
@ActiveProfiles(value = "test")
~~~

Không dùng cả `value` và `profiles` với các giá trị khác nhau trong cùng annotation vì hai thuộc tính là alias của nhau.

Cú pháp:

~~~java
@ActiveProfiles(profiles = "test", inheritProfiles = false)
~~~

được dùng khi cần ngăn nhận thêm các profile từ lớp cha hoặc lớp test bao ngoài. Mặc định `inheritProfiles = true`.

Có thể chọn resolver:

~~~java
@ActiveProfiles(resolver = CiProfileResolver.class)
~~~

để tính profile theo logic cụ thể. Cơ chế resolver được trình bày ở phần sau.

### Không có cú pháp @ActiveProfiles ở cấp phương thức

Một class như:

~~~java
@SpringBootTest
class CheckoutTest {

    @Test
    @ActiveProfiles("test")
    void localTest() {
    }
}
~~~

không phải cách dùng hợp lệ của annotation vì target của `@ActiveProfiles` là `TYPE`. Nếu cần nhiều cấu hình profile khác nhau, thường tạo **nhiều test class**, mỗi class khai báo profile và sử dụng context tương ứng.

## 6. Profile và Config Data: application-test.yml

Spring Boot thường xét cả file chung `application.yml` và biến thể tương ứng profile, ví dụ:

~~~text
application.yml
application-test.yml
application-integration.yml
application-prod.yml
~~~

Khi `test` hoạt động, file `application-test.yml` được xét và có thể ghi đè các key trùng từ file chung.

Ví dụ:

`src/main/resources/application.yml`:

~~~yaml
app:
  client:
    endpoint: https://api.example.org
    timeout: 20s
    retries: 4

logging:
  level:
    com.example.profiledemo: INFO
~~~

`src/test/resources/application-test.yml`:

~~~yaml
app:
  client:
    endpoint: http://127.0.0.1:18080
    timeout: 500ms
    retries: 1

logging:
  level:
    com.example.profiledemo: DEBUG
~~~

`@ActiveProfiles("test")` khiến profile test có hiệu lực khi context được tải, và các property này có thể được bind thành:

~~~text
endpoint = http://127.0.0.1:18080
timeout  = PT0.5S
retries  = 1
~~~

Chúng vẫn có thể bị ghi đè nếu test khai báo property có mức ưu tiên cao hơn qua `@TestPropertySource`, `@SpringBootTest(properties=...)` hoặc `@DynamicPropertySource`.

### application-test.yml không tự được kích hoạt vì đang chạy JUnit

Đặt một file tên `application-test.yml` trong `src/test/resources` **chưa đủ** để đảm bảo Spring Boot chọn profile `test`. Phải có một cơ chế kích hoạt profile thích hợp, ví dụ `@ActiveProfiles("test")` trong test tích hợp.

Một ứng dụng chạy bình thường không tự dùng profile `test` chỉ vì tên file có chữ test.

### Không tự đổi profile bằng spring.profiles.active trong file profile-specific

Tránh:

~~~yaml
# application-test.yml — không nên viết
spring:
  profiles:
    active: prod
~~~

Trong hệ thống Config Data của Spring Boot, `spring.profiles.active` và `spring.profiles.default` có ràng buộc: không được dùng trong profile-specific documents hoặc tài liệu được kích hoạt bằng `spring.config.activate.on-profile`. Nếu cần bật profile cho test, đặt `@ActiveProfiles` trên test class.

## 7. Sử dụng @SpringBootTest với nhiều profile

Khi một kịch bản cần đồng thời hai nhóm cấu hình:

~~~java
@SpringBootTest
@ActiveProfiles({"test", "integration"})
class IntegrationMessagingTest {
    // ...
}
~~~

Những profile hoạt động có thể là `test` và `integration`. Vì vậy:

- Bean có `@Profile("test")` được xét.
- Bean có `@Profile("integration")` được xét.
- Bean có `@Profile({"test", "integration"})` phù hợp nếu ít nhất một tên được chọn.
- Bean có `@Profile("!prod")` phù hợp nếu `prod` không hoạt động.
- Các tài liệu cấu hình theo những profile này có thể tham gia Config Data.

**Không nhầm `@Profile({"test","integration"})` với yêu cầu hai profile phải cùng hoạt động**. Trong annotation đó, các chuỗi riêng là điều kiện OR. Muốn diễn đạt điều kiện đồng thời, Spring hỗ trợ profile expression như `@Profile("test & integration")`.

### Thứ tự profile có ảnh hưởng cấu hình không?

Có thể có. Khi nhiều file cấu hình theo profile cung cấp cùng một key, Spring Boot áp dụng quy tắc ưu tiên theo thứ tự profile được khai báo và vị trí Config Data; trong những ví dụ thông thường, profile được xét sau có thể ghi đè giá trị từ profile trước.

Ví dụ:

~~~text
application-test.yml:
  app.feature.limit = 10

application-integration.yml:
  app.feature.limit = 30
~~~

Với `@ActiveProfiles({"test", "integration"})`, kết quả thông thường là 30 khi không có nguồn khác mạnh hơn. Tuy nhiên, imported Config Data, location groups và property sources tùy chỉnh cũng có thể ảnh hưởng. Với những test yêu cầu giá trị xác định, hãy assert giá trị hiệu lực trong `Environment` thay vì suy đoán chỉ từ tên file.

### Không dùng profile prod trong test một cách vô ý

~~~java
@ActiveProfiles({"test", "prod"})
~~~

không có nghĩa `prod` sẽ bị vô hiệu bởi `test`. Bean `@Profile("prod")` cũng có thể được tạo, dẫn đến kết nối production hoặc tác vụ ngoài ý muốn. Khi mục tiêu là cách ly, ưu tiên profile kiểm thử rõ ràng và dùng fake/test configuration có ranh giới an toàn.

## 8. Kiểm tra active profile trong test

Để chắc chắn profile được kích hoạt, inject `Environment`:

~~~java
package com.example.profiledemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class ActiveProfileEnvironmentTest {

    @Autowired
    Environment environment;

    @Test
    void testProfileIsActive() {
        assertThat(environment.getActiveProfiles())
                .contains("test");
    }
}
~~~

Nếu có nhiều profile, `getActiveProfiles()` trả mảng String. Với kịch bản cần chính xác tập profile, hãy kiểm tra đầy đủ giá trị thay vì chỉ `contains("test")`.

Có thể dùng:

~~~java
import org.springframework.core.env.Profiles;

assertThat(environment.acceptsProfiles(
        Profiles.of("test"))).isTrue();
~~~

API `Profiles.of("test")` là cách hiện đại để kiểm tra biểu thức profile theo Spring Framework.

### active và default profiles khác nhau

`environment.getActiveProfiles()` là danh sách profile được kích hoạt. `environment.getDefaultProfiles()` là danh sách default profiles được dùng khi **không có active profile**.

Không nên viết test chỉ kiểm tra default profiles rồi kết luận `@ActiveProfiles("test")` không hoạt động. Hai danh sách có vai trò khác nhau.

### Thuộc tính spring.profiles.active có nhất thiết chứa test?

Không nên coi `environment.getProperty("spring.profiles.active")` là cách duy nhất để xác nhận `@ActiveProfiles`. TestContext có thể áp dụng profile lên Environment trực tiếp; property string không phải nguồn sự thật duy nhất cho danh sách active. Dùng `getActiveProfiles()` hoặc `acceptsProfiles(...)`.

## 9. @ActiveProfiles khác @TestPropertySource như thế nào?

Hai annotation có trách nhiệm riêng:

`@ActiveProfiles`:

~~~java
@ActiveProfiles("test")
~~~

chọn profile cho context. Nó ảnh hưởng các điều kiện `@Profile` và nguồn Config Data theo profile.

`@TestPropertySource`:

~~~java
@TestPropertySource(properties = {
        "app.client.timeout=100ms",
        "app.client.retries=0"
})
~~~

đưa các property trực tiếp vào môi trường của test, thường có độ ưu tiên cao hơn file `application.yml`/`application-test.yml`.

Có thể kết hợp:

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
        "app.client.timeout=100ms"
})
class TimeoutOverrideTest {
    // ...
}
~~~

Trong trường hợp đó, profile test vẫn hoạt động, nhưng property `app.client.timeout` được ghi đè ngay tại test class.

### Khi nào chọn cách nào?

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Chọn fake bean thay cho real bean | `@ActiveProfiles("test")` với `@Profile` |
| Nạp một tập cấu hình của môi trường test | `@ActiveProfiles("test")` + `application-test.yml` |
| Đổi một giá trị duy nhất cho một kịch bản | `@TestPropertySource(properties=...)` |
| Đổi một vài giá trị trong @SpringBootTest | `@SpringBootTest(properties=...)` |
| Cấp địa chỉ container được tạo động | `@DynamicPropertySource` |
| Unit test một object Java không có context | Constructor + fake hoặc mock trực tiếp |

### @TestPropertySource không phải bộ đọc YAML tổng quát

Cần tránh giả định:

~~~java
@TestPropertySource(
        locations = "classpath:application-test.yml")
~~~

sẽ luôn đọc YAML như Spring Boot Config Data. `@TestPropertySource` có cách xử lý định dạng resource riêng; với Spring Boot test, hãy để `application-test.yml` được nạp theo **profile-specific Config Data**. Khi cần custom factory cho `@TestPropertySource` trong phiên bản hỗ trợ, đó là thiết kế khác.

## 10. @SpringBootTest(properties=...) và profile test

Spring Boot cho phép khai báo property ngay tại test:

~~~java
@SpringBootTest(properties = {
        "app.client.timeout=200ms",
        "app.client.retries=1"
})
@ActiveProfiles("test")
class ClientTest {
}
~~~

Ở đây `@ActiveProfiles` vẫn kiểm soát profile; `properties` là những giá trị override phục vụ context được tạo bởi test.

Nếu `application-test.yml` có:

~~~yaml
app:
  client:
    timeout: 1s
    retries: 3
~~~

thì các giá trị inline do `@SpringBootTest(properties=...)` cung cấp có thể thắng cấu hình thông thường, cho `timeout=200ms` và `retries=1`.

Cần tránh vừa đặt hàng chục thuộc tính trong `application-test.yml`, vừa viết lại chúng trong `@SpringBootTest(properties)` mà không có lý do. Sự trùng lặp làm test khó hiểu: người đọc không biết nên sửa nơi nào khi default thay đổi.

## 11. @DynamicPropertySource và profile test

Khi dùng Testcontainers hoặc một resource cấp phát cổng động, giá trị cần cấu hình chỉ được biết sau khi container khởi động.

`@DynamicPropertySource` cho phép đưa giá trị từ phương thức supplier vào Environment cho Spring TestContext:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@SpringBootTest
@ActiveProfiles("test")
class ExternalServiceIntegrationTest {

    // Giả sử test có một đối tượng server/container được tạo theo
    // cơ chế riêng của dự án, cung cấp một endpoint động.
    static final String TEST_ENDPOINT = "http://127.0.0.1:18080";

    @DynamicPropertySource
    static void dynamicProperties(DynamicPropertyRegistry registry) {
        registry.add("app.client.endpoint", () -> TEST_ENDPOINT);
    }
}
~~~

Đây là ví dụ cơ chế property supplier; trong Testcontainers thật, supplier có thể lấy từ container đang chạy. Không tự suy ra port 18080 luôn mở nếu không có server thực sự.

Property từ `@DynamicPropertySource` thường có **độ ưu tiên cao** hơn những giá trị từ `@TestPropertySource`, environment/system properties và file cấu hình thông thường. Vì vậy, dù `application-test.yml` có một endpoint khác, giá trị dynamic có thể được dùng.

`@DynamicPropertySource` không tự tạo active profile. Khi cần cả fake beans và dynamic endpoint, kết hợp với `@ActiveProfiles("test")`.

### Cache và resource động

Nếu mỗi subclass dùng cùng một test context cấu hình nhưng container có endpoint khác nhau, việc cache context có thể làm test nhận dữ liệu động không mong muốn. Spring TestContext có hướng dẫn cân nhắc `@DirtiesContext` trong các trường hợp dynamic properties thay đổi giữa các subclass. Không lạm dụng `@DirtiesContext` cho mọi test vì nó làm giảm hiệu năng.

## 12. @ActiveProfiles với @DataJpaTest và test slices

Spring Boot hỗ trợ các test slices chỉ tải một phần context, ví dụ `@DataJpaTest`, `@WebMvcTest`, `@JsonTest`. Chúng vẫn sử dụng Spring TestContext khi chạy theo cách thông thường, nên `@ActiveProfiles` có thể áp dụng.

Ví dụ:

~~~java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.ActiveProfiles;

@DataJpaTest
@ActiveProfiles("test")
class CustomerRepositoryTest {
    // Có thể @Autowired repository và test database.
}
~~~

File `application-test.yml` có thể cung cấp:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: create-drop
  datasource:
    url: jdbc:h2:mem:customer-test
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
~~~

**Điều kiện:** thêm driver H2 và các dependency JPA cần thiết. `@ActiveProfiles("test")` **không tự cài driver, tạo database hoặc khởi động container**.

### @DataJpaTest có hành vi database riêng

`@DataJpaTest` thường áp dụng auto-configuration dành cho test database, có thể thay datasource bằng embedded database khi điều kiện được thỏa. Nếu muốn test một database thật hoặc container, có thể cần `@AutoConfigureTestDatabase(replace = ...)` và cấu hình phù hợp.

Vì vậy, không nên nghĩ rằng cứ khai báo `spring.datasource.url` trong `application-test.yml` thì database test luôn sử dụng chính URL đó dưới mọi cấu hình `@DataJpaTest`.

### @WebMvcTest

~~~java
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.ActiveProfiles;

@WebMvcTest(controllers = GreetingController.class)
@ActiveProfiles("test")
class GreetingControllerTest {
    // Có thể test controller bằng MockMvc.
}
~~~

`GreetingController` là class controller thuộc dự án; tùy dependency của controller, test slice có thể cần cung cấp fake/mock bean. `@ActiveProfiles` chọn profile nhưng không làm `@WebMvcTest` tự nạp toàn bộ service của ứng dụng.

## 13. Kế thừa @ActiveProfiles từ lớp cha

Theo Spring TestContext, mặc định `inheritProfiles = true`.

Ví dụ:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
abstract class BaseIntegrationTest {
}
~~~

Subclass:

~~~java
class PaymentServiceTest extends BaseIntegrationTest {
    // Kế thừa cấu hình test và profile "test".
}
~~~

Không cần lặp `@ActiveProfiles("test")` trên mọi subclass. Đây là cách tổ chức hữu ích cho một nhóm integration tests dùng chung môi trường.

### Subclass bổ sung profile

~~~java
@ActiveProfiles("slow")
class SlowPaymentServiceTest extends BaseIntegrationTest {
}
~~~

Theo quy tắc mặc định, các profile của subclass được thêm vào danh sách profile kế thừa từ superclass. Context có thể nhận cả `test` và `slow`.

### Subclass thay thế danh sách profile

~~~java
@ActiveProfiles(
        profiles = "isolated",
        inheritProfiles = false)
class IsolatedPaymentServiceTest extends BaseIntegrationTest {
}
~~~

Khi `inheritProfiles = false`, test class không kế thừa các profile từ superclass (hoặc enclosing class theo quy tắc liên quan), thay vào đó áp dụng danh sách đã khai báo.

Hãy rất cẩn thận khi đặt `inheritProfiles=false`: nó có thể bỏ mất profile `test` chung, khiến bean thật được kích hoạt hoặc file `application-test.yml` không còn được chọn.

## 14. @Nested tests và kế thừa profile

JUnit Jupiter có `@Nested` để tổ chức test class bên trong test class khác.

~~~java
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderFlowTest {

    @Test
    void outerCase() {
    }

    @Nested
    class ErrorCases {

        @Test
        void missingCustomer() {
        }
    }
}
~~~

Trong Spring Framework 6.1, `@ActiveProfiles` được **kế thừa từ enclosing test class theo mặc định**, phù hợp với cơ chế TestContext hỗ trợ nested classes.

Tuy nhiên, cấu hình inheritance của nested tests còn chịu ảnh hưởng các tùy chọn TestContext như `@NestedTestConfiguration`. Nếu dự án thay đổi cách kế thừa test configuration, hãy kiểm tra context thực tế của nested test thay vì mặc định mọi annotation đều được áp dụng giống nhau.

Nếu một nested class cần profile riêng, có thể khai báo `@ActiveProfiles` ở nested class và cân nhắc `inheritProfiles`. Không nên dùng chung context giữa các nested tests có cấu hình profile khác nhau mà không hiểu rõ test context cache.

## 15. Tạo composed annotation cho cả nhóm kiểm thử

Khi nhiều test dùng cùng cấu hình, có thể tạo một annotation tùy chỉnh kết hợp `@SpringBootTest` và `@ActiveProfiles`:

~~~java
package com.example.profiledemo.testing;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest
@ActiveProfiles("test")
public @interface IntegrationTest {
}
~~~

Sử dụng:

~~~java
@IntegrationTest
class CustomerFlowTest {
    // ...
}
~~~

Lợi ích:

- Không lặp hai annotation trên hàng trăm test.
- Dễ định nghĩa một quy ước chung cho integration tests.
- Khi thay đổi profile hoặc cấu hình test chung, có thể cập nhật một vị trí.

Không nên lồng quá nhiều composed annotation khó truy tìm; với nhóm test nhỏ, dùng trực tiếp `@SpringBootTest` và `@ActiveProfiles` có thể rõ ràng hơn.

### Meta-annotation vẫn không tạo bảo đảm an toàn tuyệt đối

Nếu ai đó thêm `@ActiveProfiles("prod")` trên subclass hoặc tùy biến `inheritProfiles`, tập profile có thể thay đổi. Những hệ thống có rủi ro truy cập production cần thêm biện pháp an toàn như endpoint giả, credential riêng cho test và chính sách mạng.

## 16. Chọn profile động bằng ActiveProfilesResolver

Có những trường hợp cần tính profile từ môi trường chạy test, ví dụ local CI hoặc một loại backend.

Spring TestContext cung cấp SPI:

~~~java
import org.springframework.test.context.ActiveProfilesResolver;
~~~

Tạo resolver:

~~~java
package com.example.profiledemo.testing;

import org.springframework.test.context.ActiveProfilesResolver;

public final class CiAwareProfilesResolver
        implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String ci = System.getenv("CI");

        if ("true".equalsIgnoreCase(ci)) {
            return new String[] {"test", "ci"};
        }

        return new String[] {"test"};
    }
}
~~~

Sử dụng:

~~~java
@SpringBootTest
@ActiveProfiles(resolver = CiAwareProfilesResolver.class)
class CustomerIntegrationTest {
}
~~~

Nếu biến môi trường `CI=true`, resolver chọn `test` và `ci`. Nếu không, chỉ chọn `test`.

Đây là **ví dụ minh họa** việc tính profile. Trong dự án thực, profile thay đổi theo môi trường có thể làm test khác kết quả giữa laptop và CI. Ưu tiên các profile **tất định** khi có thể; nếu cần biến thể, tài liệu và pipeline CI phải ghi rõ.

### Dùng resolver thay vì đọc spring.profiles.active một cách ngầm định

Theo Spring TestContext, khi `@ActiveProfiles` được khai báo, thuộc tính `spring.profiles.active` từ environment variable hoặc JVM system property **không tự được tính đến** để chọn danh sách profile của test theo cơ chế mặc định. Nếu muốn CLI/system property ghi đè profile đã khai báo, có thể viết một `ActiveProfilesResolver` tường minh.

Ví dụ ý tưởng:

~~~java
import org.springframework.core.env.AbstractEnvironment;
import org.springframework.test.context.support.DefaultActiveProfilesResolver;
import org.springframework.util.StringUtils;

public final class SystemPropertyProfilesResolver
        extends DefaultActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        String value = System.getProperty(
                AbstractEnvironment.ACTIVE_PROFILES_PROPERTY_NAME);

        if (StringUtils.hasText(value)) {
            return StringUtils.commaDelimitedListToStringArray(
                    StringUtils.trimAllWhitespace(value));
        }

        return super.resolve(testClass);
    }
}
~~~

Nếu đăng ký class này qua:

~~~java
@ActiveProfiles(
        profiles = "test",
        resolver = SystemPropertyProfilesResolver.class)
~~~

thì `-Dspring.profiles.active=ci` có thể khiến resolver trả `ci` thay vì `test`. Đoạn ví dụ dựa trên `DefaultActiveProfilesResolver` và cách lấy JVM property; không có cơ chế tương tự được tự động bật nếu bạn chỉ viết `@ActiveProfiles("test")`.

**Cảnh báo:** Cho phép override profile test từ bên ngoài có thể đưa test vào môi trường không an toàn. Chỉ dùng nếu đó là một yêu cầu vận hành thật sự.

## 17. @ActiveProfiles và spring.profiles.active: hiểu đúng thứ tự

Trong ứng dụng khởi động thông thường, property:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

có thể kích hoạt profile `prod` theo cơ chế Environment/Config Data.

Trong **Spring integration test**, nếu test class có:

~~~java
@ActiveProfiles("test")
~~~

thì Spring TestContext sử dụng annotation để xác định profile của context; không nên kỳ vọng một biến `SPRING_PROFILES_ACTIVE=prod` tự động thay `test` trong cơ chế TestContext mặc định.

Hai cách kích hoạt có điểm chung là ảnh hưởng Spring Environment, nhưng có đường thiết lập khác nhau:

| Ngữ cảnh | Cách thường dùng |
| --- | --- |
| Chạy production JAR | `spring.profiles.active` qua environment/CLI |
| TestContext integration test | `@ActiveProfiles` |
| Test cần profile tính toán | `ActiveProfilesResolver` |
| Unit test không dựng Spring context | Không dùng profile Spring |

Điểm cần nhớ: sử dụng `Environment.getActiveProfiles()` trong test để xác nhận kết quả, thay vì suy luận từ sự hiện diện của một chuỗi property ở system environment.

## 18. Profile group và test profile

Spring Boot có `spring.profiles.group` để định nghĩa một tên profile kích hoạt thêm các profile liên quan.

Ví dụ trong `application.yml`:

~~~yaml
spring:
  profiles:
    group:
      integration:
        - test
        - database
~~~

Nếu profile `integration` được kích hoạt trong một luồng Spring Boot Config Data hỗ trợ group expansion, các profile nhóm như `test` và `database` có thể cùng hoạt động.

Điều này hữu ích khi cần gom tập cấu hình, nhưng cũng làm danh sách profile thực tế dài hơn profile viết trong test annotation.

~~~java
@ActiveProfiles("integration")
~~~

Không nên chỉ dựa vào chuỗi này để kết luận duy nhất profile `integration` hoạt động trong mọi bước. Có thể kiểm tra `environment.getActiveProfiles()` ở runtime và test bean/profile-specific property tương ứng.

**Giới hạn Config Data:** `spring.profiles.group` là thuộc tính kích hoạt profile nên phải được khai báo ở vị trí hợp lệ, không đặt tùy tiện trong file profile-specific như `application-test.yml` hoặc document với `spring.config.activate.on-profile`.

Nếu mục tiêu chỉ cần hai profile cố định, `@ActiveProfiles({"test","database"})` đôi khi đơn giản hơn tạo một group.

## 19. Dùng multi-document YAML theo profile

Thay vì tách file `application-test.yml`, có thể khai báo nhiều document trong một `application.yml`:

~~~yaml
app:
  message: "default"

---
spring:
  config:
    activate:
      on-profile: test

app:
  message: "from test document"
~~~

Với `@ActiveProfiles("test")`, document thứ hai có thể được kích hoạt.

Lưu ý:

- `spring.config.activate.on-profile` là điều kiện chọn **document** trong Config Data.
- `@ActiveProfiles` là điều kiện chọn **profile** cho test context.
- `@Profile` là điều kiện chọn **bean definitions**.
- `spring.profiles.active` không được khai báo trong chính document đã có `spring.config.activate.on-profile` theo quy tắc Config Data.

Nếu dự án có nhiều cấu hình test, tách `src/test/resources/application-test.yml` thường dễ đọc hơn. Nếu chỉ có một vài giá trị nhỏ, multi-document YAML cũng là một lựa chọn.

## 20. Khi @ActiveProfiles không có tác dụng như kỳ vọng

### 20.1. Chỉ chạy JUnit thuần

~~~java
@ActiveProfiles("test")
class PureUnitTest {

    @Test
    void calculate() {
        var calculator = new Calculator();
        // Không có Spring ApplicationContext.
    }
}
~~~

`@ActiveProfiles` tự nó không dựng context. Nếu test không dùng Spring TestContext, annotation không làm gì. Hãy giữ unit test độc lập và inject fake/mock qua constructor thay vì khởi động Spring chỉ để sử dụng một profile.

### 20.2. Chưa bật Spring TestContext

Nếu không có `@SpringBootTest`, `@ContextConfiguration` hoặc một test slice/extension phù hợp, Spring không được yêu cầu nạp context. `@ActiveProfiles` không thay thế những annotation đó.

### 20.3. File application-test.yml nằm sai chỗ

Nếu file không nằm trên classpath test hoặc tên khác quy ước, Spring Boot có thể không nạp nó. Kiểm tra:

~~~text
src/test/resources/application-test.yml
~~~

và cấu hình build đã copy test resources.

### 20.4. Đặt @ActiveProfiles lên phương thức

`@ActiveProfiles` dành cho class. Hãy khai báo ở class hoặc meta-annotation thay vì từng method.

### 20.5. Prefix cấu hình không khớp

~~~yaml
app:
  notifications:
    enabled: false
~~~

khác với `@ConfigurationProperties(prefix="app.notification")`. Profile đã hoạt động nhưng tên key sai vẫn có thể làm Binder không nhận giá trị mong đợi.

### 20.6. Property được nguồn khác ghi đè

Nếu `@SpringBootTest(properties="app.message=inline")` hoặc `@DynamicPropertySource` đặt cùng key, giá trị đó có thể thắng `application-test.yml`. Đừng kết luận profile không hoạt động chỉ vì một assertion giá trị thất bại.

### 20.7. Bean có nhiều điều kiện

Một bean có `@Profile("test")` nhưng đồng thời có `@ConditionalOnProperty` hoặc các điều kiện auto-configuration khác. Profile phù hợp không đảm bảo tất cả điều kiện khác đều đúng.

### 20.8. Profile kế thừa từ lớp cha

Một lớp cha có `@ActiveProfiles("integration")` và subclass có `@ActiveProfiles("test")`. Vì `inheritProfiles=true`, context có thể nhận cả hai. Nếu muốn chỉ `test`, dùng `inheritProfiles=false`.

### 20.9. Test slice không tải bean mong đợi

`@WebMvcTest` không tự quét toàn bộ service/repository như `@SpringBootTest`. Profile test có thể đúng nhưng bean không nằm trong phạm vi của slice.

### 20.10. Context cache dùng lại context

Spring TestContext cache có thể tái sử dụng context khi merged configuration tương đương, trong đó các active profiles là một yếu tố quan trọng. Nếu test thay đổi các trạng thái singleton/static hoặc dữ liệu bên ngoài mà không dọn dẹp, kết quả có thể ảnh hưởng lẫn nhau dù profile đúng.

## 21. TestContext cache và hiệu năng

Khởi tạo `@SpringBootTest` thường tốn thời gian. Spring TestContext cache giúp tái sử dụng context cho những test có cấu hình tương đương.

Ví dụ:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class CheckoutTestA {
}
~~~

~~~java
@SpringBootTest
@ActiveProfiles("test")
class CheckoutTestB {
}
~~~

Nếu các yếu tố cấu hình khác của hai test tương đương, chúng **có thể** dùng chung cached ApplicationContext.

Nếu đổi sang:

~~~java
@SpringBootTest
@ActiveProfiles({"test", "integration"})
class CheckoutTestC {
}
~~~

cấu hình profile khác có thể tạo một cache key khác và làm khởi tạo context mới.

### Tránh quá nhiều profile biến thể không cần thiết

Nếu mỗi test class tự tạo một profile riêng với cấu hình rất giống nhau, số context khởi tạo tăng và suite chậm. Có thể thống nhất `test` làm nền, dùng vài `@TestPropertySource` override có mục đích, và dành profile riêng cho những thay đổi bean/config data lớn.

### Khi nào dùng @DirtiesContext?

`@DirtiesContext` yêu cầu framework đánh dấu context cần bỏ khỏi cache trong những tình huống cụ thể. Chỉ dùng khi test thực sự làm bẩn context theo cách không thể khôi phục bằng cleanup thông thường. Lạm dụng nó khiến test suite chậm đáng kể.

Chỉ thay đổi dữ liệu trong database test không nhất thiết phải phá context; các test transaction hoặc cleanup thích hợp thường đủ.

## 22. Viết một integration test có cấu hình thực

Giả sử một service dùng typed configuration:

~~~java
package com.example.profiledemo.config;

import java.time.Duration;
import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.payment")
public record PaymentProperties(
        URI endpoint,
        Duration timeout,
        boolean enabled) {
}
~~~

`src/main/resources/application.yml`:

~~~yaml
app:
  payment:
    endpoint: https://pay.example.org
    timeout: 10s
    enabled: true
~~~

`src/test/resources/application-test.yml`:

~~~yaml
app:
  payment:
    endpoint: http://127.0.0.1:9999
    timeout: 200ms
    enabled: false
~~~

Test:

~~~java
package com.example.profiledemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;

import com.example.profiledemo.config.PaymentProperties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class PaymentConfigurationTest {

    @Autowired
    PaymentProperties payment;

    @Autowired
    Environment environment;

    @Test
    void loadsTestPaymentConfiguration() {
        assertThat(environment.getActiveProfiles())
                .contains("test");

        assertThat(payment.enabled()).isFalse();
        assertThat(payment.timeout())
                .isEqualTo(Duration.ofMillis(200));
        assertThat(payment.endpoint())
                .isEqualTo(URI.create("http://127.0.0.1:9999"));
    }
}
~~~

Cần bảo đảm `PaymentProperties` được đăng ký bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

**Không kết nối endpoint 127.0.0.1:9999 nếu không có test server.** Ví dụ chỉ kiểm tra binding và chọn profile. Nếu có bean startup chủ động gọi remote API, phải thay bằng fake adapter hoặc dựng server giả cho test.

## 23. Kiểm tra một bean chỉ được bật trong profile test

Tạo một bean bên trong configuration:

~~~java
package com.example.profiledemo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
public class TestMarkerConfiguration {

    public interface ProfileMarker {
        String name();
    }

    @Bean
    @Profile("test")
    ProfileMarker testProfileMarker() {
        return () -> "test";
    }

    @Bean
    @Profile("!test")
    ProfileMarker defaultProfileMarker() {
        return () -> "default";
    }
}
~~~

Test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class ProfileMarkerTest {

    @Autowired
    TestMarkerConfiguration.ProfileMarker marker;

    @Test
    void selectsMarkerForTest() {
        assertThat(marker.name()).isEqualTo("test");
    }
}
~~~

Ví dụ yêu cầu class `TestMarkerConfiguration` được component scan trong ứng dụng. Trong một ứng dụng thực, adapter phân vùng theo profile có thể là payment gateway, email sender hoặc storage client.

Nếu dùng `@Profile("!test")` trên default bean, cần hiểu nó được kích hoạt trong mọi context không có `test`, không riêng production.

## 24. Đừng dùng profile test thay cho mock đúng phạm vi

Một số test chỉ muốn mock một dependency để kiểm tra logic controller/service mà không có nhu cầu thay cả cấu hình môi trường.

Nếu tạo một `@Profile("test")` fake bean toàn cục cho mọi test, những integration test khác có thể vô tình dùng fake và bỏ sót lỗi kết nối thật.

Lựa chọn:

- **Test unit:** tạo class bằng constructor và truyền fake/mock.
- **Test slice:** cung cấp mock/fake phù hợp với phạm vi slice.
- **Integration test với test profile:** `@ActiveProfiles("test")` khi muốn thay cả nhóm property và bean.
- **Integration test với hạ tầng thực:** dùng Testcontainers/embedded service cùng dynamic properties và profile được đặt có chủ đích.

Test profile là một kỹ thuật cấu hình; nó không tự đảm bảo mức độ tích hợp hoặc tính cô lập.

## 25. Điều gì xảy ra nếu không có @ActiveProfiles?

Nếu test chỉ viết:

~~~java
@SpringBootTest
class ContextLoadsTest {

    @Test
    void contextLoads() {
    }
}
~~~

thì Spring TestContext không áp đặt profile `test` từ annotation. Các profile có thể đến từ môi trường, cấu hình hoặc cơ chế khởi động khác; nếu không có active profiles, Spring dùng default profile theo quy tắc Environment.

Không nên kết luận `@SpringBootTest` luôn tự bật `test`. Đây là một giả định sai khá phổ biến.

Nếu ứng dụng đang có các bean chỉ hoạt động với `@Profile("prod")`, test không có profile phù hợp sẽ không tự tạo chúng chỉ vì đang chạy trên máy build.

## 26. Chạy test trong Maven và Gradle

Ví dụ Maven:

~~~bash
./mvnw test
~~~

Chạy một class với Maven Surefire khi cấu hình dự án hỗ trợ:

~~~bash
./mvnw -Dtest=GreetingPropertiesTest test
~~~

Gradle:

~~~bash
./gradlew test
~~~

Hoặc chọn một class:

~~~bash
./gradlew test --tests "com.example.profiledemo.GreetingPropertiesTest"
~~~

Trên Windows dùng wrapper `mvnw.cmd` hoặc `gradlew.bat` tương ứng.

`@ActiveProfiles("test")` đã khai báo trong test class nên không cần bắt buộc truyền `-Dspring.profiles.active=test` chỉ để test nhận profile.

Nếu muốn xem profile thực sự được sử dụng, thêm assertion `environment.getActiveProfiles()` hoặc quan sát log startup của context.

## 27. Những bẫy bảo mật và vận hành

### Test profile không cho phép kết nối production một cách an toàn

Dù test có `@ActiveProfiles("test")`, một bean không có `@Profile`/conditional có thể vẫn chạy và gọi endpoint thật từ file chung. Vì vậy, profile test nên đi kèm:

- Endpoint chỉ dành cho test hoặc local fake server.
- Credential riêng có quyền hạn thấp.
- Vô hiệu hóa các tác vụ gửi email, thanh toán, webhook thật.
- Hạn chế egress ở CI nếu hệ thống nhạy cảm.
- Test rõ ràng rằng fake adapter được chọn.
- Không lưu secret thật trong `src/test/resources` rồi commit.

### Không dùng @ActiveProfiles("prod") để test production tùy tiện

Chọn `prod` có thể kích hoạt datasource, queue, schedule hoặc service client thật. Nếu cần kiểm thử cấu hình sản xuất, hãy tạo môi trường kiểm thử tách biệt, dùng dữ liệu giả và quyền truy cập riêng.

### Cẩn thận với @Scheduled và ApplicationRunner

`@SpringBootTest` khởi tạo ứng dụng tương đối đầy đủ. Những `ApplicationRunner`, `CommandLineRunner` hoặc scheduled jobs có thể chạy trong test context nếu được kích hoạt. Nếu chúng tạo tác dụng ngoài ý muốn, hãy kiểm soát bằng profile/conditional và test-specific config.

### Tránh profile “test” như công tắc bảo mật

Việc có hay không có `test` không phải là bằng chứng về danh tính hoặc quyền của người dùng. Không dùng `@Profile("test")` thay hệ thống phân quyền hoặc chính sách bảo vệ secret.

## 28. Mẫu tổ chức test cho dự án lớn

Một tổ chức tham khảo:

~~~text
src/test/java/com/example/profiledemo/
├── support/
│   ├── IntegrationTest.java
│   └── CiAwareProfilesResolver.java
├── unit/
│   └── PriceCalculatorTest.java
├── repository/
│   └── CustomerRepositoryTest.java
├── web/
│   └── GreetingControllerTest.java
└── integration/
    ├── PaymentFlowTest.java
    └── NotificationFlowTest.java

src/test/resources/
├── application-test.yml
└── data/
    └── test-customers.json
~~~

Đề xuất sử dụng:

- Unit tests trong `unit` không khởi tạo Spring context khi không cần.
- `@WebMvcTest`/`@DataJpaTest` cho những lát cắt kiểm thử phù hợp.
- `@IntegrationTest` (composed annotation) cho test cần context đầy đủ và profile test.
- Testcontainers/`@DynamicPropertySource` cho integration tests cần database hoặc service chạy thật nhưng cô lập.
- Cấu hình chung ít và ổn định trong `application-test.yml`.
- Override riêng của từng kịch bản bằng thuộc tính test thay vì tạo quá nhiều profile gần giống nhau.

Điểm cốt lõi là test phải đọc được và bảo trì được: người xem class có thể suy ra profile, phạm vi context và những ngoại lệ cấu hình quan trọng.

## 29. Bảng so sánh nhanh

| Công cụ/annotation | Có bật profile? | Có cấp property? | Có tạo context? |
| --- | --- | --- | --- |
| `@ActiveProfiles("test")` | Có, qua TestContext | Gián tiếp dẫn đến profile-specific Config Data | Không tự tạo context |
| `@Profile("test")` | Không | Không | Không; chỉ điều kiện đăng ký bean |
| `@SpringBootTest` | Không tự buộc profile test | Có thể qua `properties` | Có, context Spring Boot đầy đủ phù hợp |
| `@TestPropertySource` | Không tự chọn profile từ tên file | Có | Không tự tạo context |
| `@DynamicPropertySource` | Không tự chọn profile | Có, giá trị động | Không tự tạo context |
| `@DataJpaTest` | Không tự buộc test profile | Có thể qua `properties` | Có, test slice JPA |
| `spring.profiles.active` | Có trong bootstrap ứng dụng thông thường | Là property cấu hình | Không tự tạo test context |
| `ActiveProfilesResolver` | Có, khi gắn bằng `@ActiveProfiles` | Không trực tiếp | Không tự tạo context |

Nếu đang tìm cách đổi một giá trị timeout, `@ActiveProfiles` có thể là phương án quá lớn; nếu cần thay cả tập bean và nguồn config test, nó thường phù hợp.

## 30. Bài tập thực hành

### Bài 1 — Kích hoạt file cấu hình test

Tạo `src/main/resources/application.yml` chứa `app.message=default` và `src/test/resources/application-test.yml` chứa `app.message=from-test`. Viết `@SpringBootTest @ActiveProfiles("test")`, inject `Environment` và assert giá trị `from-test`.

### Bài 2 — Bean theo profile

Tạo hai bean cùng interface, một dùng `@Profile("test")` và một dùng `@Profile("!test")`. Viết test xác nhận bean test được chọn khi `@ActiveProfiles("test")`.

### Bài 3 — Multiple profiles

Tạo `application-test.yml` và `application-integration.yml` có cùng key nhưng giá trị khác nhau. Viết `@ActiveProfiles({"test","integration"})` và xác nhận property hiệu lực. Giải thích vì sao không nên tự suy luận thứ tự từ tên file.

### Bài 4 — Kế thừa test profile

Tạo abstract base class với `@ActiveProfiles("test")`. Viết subclass có `@ActiveProfiles("slow")`. Dự đoán profile hiệu lực khi `inheritProfiles` giữ mặc định.

**Đáp án:** các profile của base class được kế thừa, rồi profile của subclass được thêm vào.

### Bài 5 — Bỏ kế thừa

Trên subclass, đặt:

~~~java
@ActiveProfiles(profiles = "isolated", inheritProfiles = false)
~~~

Kiểm tra `Environment.getActiveProfiles()` và giải thích tại sao `test` từ base class không còn được thêm bởi cơ chế kế thừa annotation.

### Bài 6 — TestPropertySource

Tạo `application-test.yml` đặt `app.retry.count=2` và một test `@TestPropertySource(properties="app.retry.count=7")`. Assert kết quả là 7 khi không có nguồn ưu tiên cao hơn khác.

### Bài 7 — DynamicPropertySource

Tạo một local mock server cấp cổng ngẫu nhiên. Dùng `@DynamicPropertySource` để cung cấp URL của server, đồng thời bật `@ActiveProfiles("test")`. Kiểm tra URL hiệu lực, sau đó dọn dẹp server.

### Bài 8 — Test slice

Viết `@DataJpaTest @ActiveProfiles("test")` cho repository. Xác nhận dependency database phù hợp được cung cấp. Không giả định annotation tự tạo driver H2 hoặc container.

### Bài 9 — Profile resolver

Viết `ActiveProfilesResolver` trả `{"test","ci"}` khi `CI=true`, còn lại trả `{"test"}`. Kiểm tra tập profile trong hai môi trường và giải thích rủi ro các test chạy khác nhau giữa local và CI.

### Bài 10 — Chẩn đoán cấu hình sai

Test có `@ActiveProfiles("test")` nhưng bean vẫn đọc endpoint production. Hãy kiểm tra thứ tự:
1. File `application-test.yml` có nằm trên test classpath không?
2. Prefix property có viết đúng không?
3. Có property khác override không?
4. Bean đang dùng `@ConfigurationProperties` hay hard-coded endpoint?
5. `@Profile` của adapter có đúng điều kiện không?
6. Có test context khác đang được tạo không?

### Bài 11 — Unit test thuần

Một class `PriceCalculator` chỉ cần hai tham số constructor và không phụ thuộc Spring. Viết unit test bằng `new PriceCalculator(...)` thay vì `@SpringBootTest`. Giải thích tại sao không cần `@ActiveProfiles`.

### Bài 12 — Tránh tác dụng phụ

Một startup runner gửi email mỗi khi context được tạo. Thiết kế fake bean hoặc condition để integration test không gửi email thật khi `test` active. Kiểm tra rằng profile test thực sự chọn fake adapter.

## 31. Tổng kết

`@ActiveProfiles` thuộc **Spring TestContext Framework** và dùng để khai báo các profile hoạt động khi framework tải `ApplicationContext` cho integration test. Trong Spring Boot, profile này thường kéo theo việc nạp **`application-test.yml`** hoặc **`application-test.properties`** và việc chọn bean theo `@Profile`.

Cần ghi nhớ:

- Dùng `@SpringBootTest` hoặc test slice/ContextConfiguration phù hợp để thật sự tạo context; `@ActiveProfiles` đơn độc không làm việc này.
- Đặt `@ActiveProfiles("test")` ở cấp class, không phải method.
- Dùng `Environment.getActiveProfiles()` để kiểm tra, đừng chỉ nhìn property string `spring.profiles.active`.
- Default `inheritProfiles=true` khiến subclass/nested test có thể kế thừa profile của lớp cha hoặc lớp bao ngoài.
- Dùng `inheritProfiles=false` nếu thật sự cần thay danh sách profile kế thừa.
- `ActiveProfilesResolver` cho phép quyết định profile bằng code nhưng nên giữ test có tính tất định.
- `@TestPropertySource`, `@SpringBootTest(properties)` và `@DynamicPropertySource` dùng để override **property**, không phải thay vai trò của `@ActiveProfiles`.
- Profile test không tự cấp driver database, mock server, quyền truy cập hoặc bảo đảm không kết nối production.
- Để test nhanh, chọn đúng phạm vi context và tận dụng TestContext cache một cách có chủ đích.

## Tài liệu tham khảo

- [Spring Framework 6.1 — ActiveProfiles API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/test/context/ActiveProfiles.html)
- [Spring Framework — Context Configuration with Environment Profiles](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/env-profiles.html)
- [Spring Framework — @ActiveProfiles](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-activeprofiles.html)
- [Spring Framework — ActiveProfilesResolver API](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/test/context/ActiveProfilesResolver.html)
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)

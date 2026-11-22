# Cấp giá trị động bằng `@DynamicPropertySource` trong kiểm thử Spring Boot

## 1. Bài toán: cấu hình test không thể biết hết khi viết YAML

Spring Boot cho phép ứng dụng lấy cấu hình từ `application.yml`, `application.properties`, biến môi trường, Java system properties và nhiều `PropertySource` khác. Trong một integration test, giá trị cần đưa cho ứng dụng có thể **chỉ xuất hiện sau khi tài nguyên test khởi động**.

Ví dụ:

- PostgreSQL container mở cổng nội bộ `5432` nhưng Docker ánh xạ sang một cổng host ngẫu nhiên.
- Redis hoặc Kafka container được tạo riêng cho mỗi lần chạy CI.
- HTTP mock server khởi động trên một cổng rảnh do hệ điều hành chọn.
- Test cần đưa URL, host, port, credential hoặc tên tài nguyên được sinh trong quá trình khởi tạo fixture.
- Spring application context phải nhìn thấy các giá trị ấy **trước khi tạo bean phụ thuộc** như `DataSource` hoặc HTTP client.

Nếu cố định:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/testdb
~~~

thì test dễ lỗi khi container đang được ánh xạ sang port `51423` hoặc `49311`. Mã test có thể tìm được port thật từ Testcontainers, nhưng phải **truyền nó vào `Environment` của Spring** sao cho auto-configuration đọc đúng.

Spring TestContext Framework cung cấp `@DynamicPropertySource` để làm việc này.

> **Cốt lõi:** `@DynamicPropertySource` đánh dấu một phương thức `static` trong lớp integration test. Phương thức nhận `DynamicPropertyRegistry` và đăng ký các cặp **tên property + `Supplier` cung cấp giá trị khi cần**. Spring thêm chúng vào property sources của application context dành cho test.

Cơ chế này không phải hot-reload production. Nó chủ yếu phục vụ kiểm thử có tài nguyên ngoài được tạo động.

## 2. Các thành phần và package

Những import chính:

~~~java
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.DynamicPropertyRegistry;
~~~

Cả hai thuộc package `org.springframework.test.context` của Spring Framework. Để dùng cùng Spring Boot, thường có `spring-boot-starter-test` mang Spring Test và JUnit Jupiter.

Một sơ đồ khái niệm:

~~~text
JUnit / Spring TestContext
           |
           v
@DynamicPropertySource static method
           |
           v
DynamicPropertyRegistry.add(name, Supplier)
           |
           v
Dynamic PropertySource trong Environment
           |
           v
Spring Boot Binder / @Value / @ConfigurationProperties
           |
           v
Bean ứng dụng nhận URL, host, port ...
~~~

Vai trò được phân chia:

| Thành phần | Trách nhiệm |
| --- | --- |
| `@DynamicPropertySource` | Chỉ ra method đăng ký dynamic properties trên test class |
| `DynamicPropertyRegistry` | Nhận các tên property và value suppliers |
| `Supplier` | Trả giá trị khi framework resolve property |
| `Environment` | Kết hợp các nguồn cấu hình theo precedence |
| `@Value` | Inject một giá trị thuộc tính vào bean |
| `@ConfigurationProperties` | Bind nhóm cấu hình vào object Java có kiểu |
| `Testcontainers` | Quản lý container/test resource thực tế nếu test sử dụng |

`@DynamicPropertySource` không khởi động container giúp bạn, không tự tạo một HTTP server và cũng không biến các key tùy ý thành key mà Spring Boot auto-configuration hiểu.

## 3. Cú pháp chính xác của phương thức

Mẫu tối thiểu:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class EndpointIntegrationTest {

    @DynamicPropertySource
    static void register(DynamicPropertyRegistry registry) {
        registry.add("app.client.host", () -> "127.0.0.1");
        registry.add("app.client.port", () -> 50001);
        registry.add("app.client.timeout", () -> "3s");
    }
}
~~~

Với phương thức được đánh dấu `@DynamicPropertySource` trong integration test class:

1. Phải là **`static`**.
2. Phải nhận **một tham số duy nhất** kiểu `DynamicPropertyRegistry`.
3. Thông thường khai báo trả về **`void`**.
4. Đăng ký dữ liệu bằng `registry.add(propertyName, valueSupplier)`.
5. Lớp test phải được thực thi qua **Spring TestContext**, ví dụ `@SpringBootTest` hoặc `@SpringJUnitConfig`.

Một ví dụ **không hợp lệ** vì thiếu `static`:

~~~java
@DynamicPropertySource
void register(DynamicPropertyRegistry registry) {
    registry.add("app.client.port", () -> 50001);
}
~~~

Một ví dụ khác **không hợp lệ** vì không nhận registry:

~~~java
@DynamicPropertySource
static void register() {
}
~~~

Và không thể thêm một tham số `Environment` theo ý muốn:

~~~java
// Không đúng signature của @DynamicPropertySource.
@DynamicPropertySource
static void register(
        DynamicPropertyRegistry registry, Environment environment) {
}
~~~

Không gắn `@Bean` lên method này như một factory method thông thường. TestContext phát hiện và gọi method theo contract riêng của annotation.

## 4. `DynamicPropertyRegistry.add` và đặc tính lazy

API:

~~~java
registry.add("app.client.port", () -> 50001);
~~~

Tham số thứ hai là một `Supplier`, không phải giá trị đã tính sẵn.

Sai:

~~~java
registry.add("app.client.port", 50001);
~~~

Đúng:

~~~java
registry.add("app.client.port", () -> 50001);
~~~

Đúng với method reference:

~~~java
registry.add("app.client.port", mockServer::getPort);
~~~

Supplier được gọi **khi property được resolve**. Ví dụ:

~~~java
registry.add("app.client.port", () -> {
    System.out.println("Resolving app.client.port");
    return mockServer.getPort();
});
~~~

Lệnh `registry.add(...)` không bắt buộc gọi `mockServer.getPort()` ngay tại thời điểm đăng ký. Nếu không bean hay code nào hỏi property, supplier có thể không được gọi trong quá trình test.

Nhưng **lazy không đồng nghĩa “chỉ gọi một lần”**. Một property có thể được resolve ở nhiều thời điểm, và supplier có thể bị gọi lặp lại. Vì vậy nó nên:

- Trả giá trị nhanh và nhất quán.
- Chỉ đọc thông tin từ tài nguyên đã start.
- Không khởi động/dừng container hoặc server ở mỗi lần gọi.
- Không sửa trạng thái global.
- Không phát sinh số ngẫu nhiên mới cho mỗi lần lookup.

Ví dụ có rủi ro:

~~~java
registry.add("app.client.port", () ->
        java.util.concurrent.ThreadLocalRandom.current()
            .nextInt(20000, 60000));
~~~

Nếu hai bean resolve property ở hai thời điểm, chúng có thể nhận **hai cổng khác nhau** không gắn với server nào.

## 5. Test nhỏ chứng minh precedence

Trước tiên không cần Docker. Có thể viết test tự chứa:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = DynamicPortTest.TestApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = "app.client.port=12345")
class DynamicPortTest {

    @SpringBootApplication
    static class TestApp {
    }

    @DynamicPropertySource
    static void dynamicPort(DynamicPropertyRegistry registry) {
        registry.add("app.client.port", () -> 50001);
    }

    @Autowired
    Environment environment;

    @Test
    void choosesDynamicValue() {
        Integer port = environment.getProperty(
                "app.client.port", Integer.class);

        assertThat(port).isEqualTo(50001);
    }
}
~~~

Trong ví dụ:

- `@TestPropertySource` cấp giá trị tĩnh `12345`.
- `@DynamicPropertySource` cấp cùng key với supplier trả `50001`.
- Theo precedence của Spring TestContext, **dynamic property có ưu tiên cao hơn `@TestPropertySource`**.
- Kết quả từ `Environment` là `50001`.
- Test không cần web server vì `webEnvironment=NONE`.

Đây là cách xác minh cơ chế trước khi đưa một container/fixture phức tạp vào.

## 6. Dynamic value được bind vào `@ConfigurationProperties`

Giả sử ứng dụng có một cấu hình client:

~~~java
package com.example.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        String host,
        int port,
        Duration timeout) {
}
~~~

Class ứng dụng đăng ký properties:

~~~java
package com.example;

import com.example.config.ClientProperties;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(ClientProperties.class)
public class DemoApplication {
}
~~~

Test:

~~~java
package com.example;

import com.example.config.ClientProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ClientPropertiesTest {

    @DynamicPropertySource
    static void dynamicClientSettings(DynamicPropertyRegistry registry) {
        registry.add("app.client.host", () -> "127.0.0.1");
        registry.add("app.client.port", () -> 50001);
        registry.add("app.client.timeout", () -> "750ms");
    }

    @Autowired
    ClientProperties client;

    @Test
    void bindsTypedValues() {
        assertThat(client.host()).isEqualTo("127.0.0.1");
        assertThat(client.port()).isEqualTo(50001);
        assertThat(client.timeout())
                .isEqualTo(Duration.ofMillis(750));
    }
}
~~~

Cùng hệ thống Spring Boot binding được áp dụng như với YAML: `750ms` chuyển thành `Duration`, `port` thành số nguyên và các field được inject vào object.

`@DynamicPropertySource` không yêu cầu bạn tự parse từng key. Hãy đăng ký key **đúng với prefix và model** của component nhận dữ liệu.

## 7. Vì sao Testcontainers thường đi cùng `@DynamicPropertySource`?

Testcontainers chạy dịch vụ thực trong container. Dịch vụ có thể nghe một cổng cố định **bên trong container**, trong khi Docker chọn cổng khác ở phía host:

~~~text
Inside PostgreSQL container: port 5432
Run #1 host mapped port: 49321
Run #2 host mapped port: 51437

postgres.getJdbcUrl()
postgres.getUsername()
postgres.getPassword()
          |
          v
DynamicPropertyRegistry
          |
          v
spring.datasource.url
spring.datasource.username
spring.datasource.password
          |
          v
Spring Boot DataSource auto-configuration
~~~

Không nên mặc định container luôn có thể truy cập qua `localhost:5432`. Testcontainers cung cấp API để lấy JDBC URL đã chứa host, mapped port và database tương ứng.

Method references rất phù hợp:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
registry.add("spring.datasource.username", postgres::getUsername);
registry.add("spring.datasource.password", postgres::getPassword);
~~~

Ba key này là những property mà Spring Boot hiểu để cấu hình datasource trong trường hợp dùng auto-configuration chuẩn.

Nếu tự đặt key `test.postgres.jdbc-url` nhưng Spring Boot vẫn chờ `spring.datasource.url`, cơ chế auto-configuration không tự biết hai key là một.

## 8. Ví dụ hoàn chỉnh: PostgreSQL container trong integration test

### 8.1. Các dependencies

Với Maven, Spring Boot 3.x và project có Spring Boot BOM/dependency management:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>postgresql</artifactId>
    <scope>test</scope>
</dependency>
~~~

Các phiên bản Testcontainers cần tương thích với Spring Boot/Java và BOM của dự án. Testcontainers cũng cần Docker-compatible runtime hoạt động trong local/CI; thêm dependency thôi không đủ.

### 8.2. Code test

~~~java
package com.example;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class PostgreSqlIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("integration_db")
                .withUsername("integration_user")
                .withPassword("integration_password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    DataSource dataSource;

    @Test
    void canQueryDatabase() {
        Integer result = new JdbcTemplate(dataSource)
                .queryForObject("select 1", Integer.class);

        assertThat(result).isEqualTo(1);
    }
}
~~~

Giải thích:

1. `@Testcontainers` bật JUnit Jupiter extension của Testcontainers.
2. `@Container static` để extension quản lý container theo lifecycle phù hợp của test class.
3. Container dùng một PostgreSQL instance dành riêng cho test với database/user/password ví dụ.
4. `@DynamicPropertySource` cung cấp JDBC URL và credentials **đúng container đang chạy**.
5. Spring Boot bind `spring.datasource.*` để tạo `DataSource`.
6. `JdbcTemplate` xác minh đường kết nối có thể thực hiện một truy vấn đơn giản.

Password trong snippet chỉ dành cho container test cô lập, không phải credential để dùng trong production.

### 8.3. Cẩn thận context cache và lifetime

Một Spring context được cache có thể tồn tại **lâu hơn** static Testcontainers container do JUnit extension quản lý theo test class. Nếu container đã stop nhưng context vẫn được reuse, cached datasource có thể kết nối tới cổng không còn hoạt động.

Điều này không chứng minh dynamic property sai; nó thường là **resource lifecycle không đồng nhất với context caching**. Phần sau trình bày các cách tránh lỗi.

## 9. Redis container với mapped port

Một ví dụ khác:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(
        classes = DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class RedisIntegrationTest {

    @Container
    static GenericContainer<?> redis =
            new GenericContainer<>("redis:7-alpine")
                .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisSettings(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
    }

    @Autowired
    Environment environment;

    @Test
    void usesCorrectMappedPort() {
        Integer port = environment.getProperty(
                "spring.data.redis.port", Integer.class);

        assertThat(port).isEqualTo(redis.getMappedPort(6379));
    }
}
~~~

Trong Spring Boot 3.x, Redis connection properties có prefix `spring.data.redis`. Những ví dụ Boot cũ có thể sử dụng `spring.redis`, vì vậy phải đối chiếu version.

Test này chỉ xác minh **giá trị config được resolve**. Để xác minh Redis client có kết nối thực, cần tích hợp client/dependency tương ứng và thao tác đọc-ghi Redis trong test.

## 10. Precedence của dynamic properties

Theo tài liệu Spring Framework TestContext, dynamic properties có độ ưu tiên cao hơn những nguồn như:

- `@TestPropertySource` (cả file hoặc inline properties).
- Java system properties (ví dụ `-Dapp.key=value`).
- Biến môi trường hệ điều hành.
- Các property sources do `@PropertySource` của ứng dụng thêm vào.
- Các property sources ứng dụng thêm bằng lập trình theo cơ chế thông thường.

Ví dụ:

~~~yaml
# application.yml
app:
  client:
    port: 10000
~~~

~~~java
@SpringBootTest(properties = "app.client.port=20000")
@TestPropertySource(properties = "app.client.port=30000")
class ClientTest {

    @DynamicPropertySource
    static void dynamic(DynamicPropertyRegistry registry) {
        registry.add("app.client.port", () -> 40000);
    }
}
~~~

Giá trị `app.client.port` khi Spring resolve trong test context là **40000** theo precedence nêu trên.

Điều này cho phép container address ghi đè URL tĩnh được khai báo ở môi trường developer mà không phải sửa file cấu hình chính.

### 10.1. Chỉ những key được đăng ký mới được override trực tiếp

Giả sử YAML có:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/defaultdb
    username: default_user
    password: default_password
~~~

Dynamic registry chỉ ghi đè URL:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
~~~

Kết quả có thể là URL từ container nhưng username/password từ YAML. Đây là trạng thái **không nhất quán** và dễ gây authentication failure.

Hãy đăng ký đầy đủ bộ property cần thiết cho một external service:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
registry.add("spring.datasource.username", postgres::getUsername);
registry.add("spring.datasource.password", postgres::getPassword);
~~~

Dynamic source không tự xóa các key liên quan nhưng chưa được đăng ký.

## 11. Đối chiếu với `@TestPropertySource`

`@TestPropertySource` phù hợp cho cấu hình **biết trước**:

~~~java
@TestPropertySource(properties = {
    "app.feature.enabled=true",
    "app.client.timeout=2s"
})
~~~

Hoặc tải file:

~~~java
@TestPropertySource(locations = "classpath:/test-settings.properties")
~~~

Nó không có cách trực tiếp biết **port mà Docker sẽ gán vào lúc runtime** trước khi start container.

| Tiêu chí | `@TestPropertySource` | `@DynamicPropertySource` |
| --- | --- | --- |
| Điểm khai báo | Annotation trên test class | Annotation trên method `static` |
| Input | Key-value tĩnh hoặc file | Key + `Supplier` |
| Phù hợp với port do container chọn | Không trực tiếp | Có |
| Có thể dùng file properties | Có | Không phải mục đích của API |
| Độ ưu tiên khi cùng key | Thấp hơn dynamic source | Cao hơn test property sources |
| Cần quản lý lifecycle ngoài Spring | Không nếu chỉ dùng dữ liệu tĩnh | Có nếu supplier đọc từ container/server |
| Dùng trong test không có Spring context | Không tạo Environment tự động | Cũng không tạo Environment tự động |

Nếu chỉ muốn `app.feature.enabled=true`, `@TestPropertySource` hoặc `@SpringBootTest(properties=...)` thường đơn giản hơn, không cần dynamic supplier.

## 12. `@SpringBootTest(properties=...)` và giới hạn compile-time

Một giá trị tĩnh có thể viết:

~~~java
@SpringBootTest(properties = {
    "app.cache.enabled=false",
    "app.client.timeout=500ms"
})
~~~

Nhưng Java annotation attributes cần compile-time constant. Không thể đưa giá trị runtime của `testServer.getPort()` vào string attribute theo cách trực tiếp.

Trong khi đó:

~~~java
@DynamicPropertySource
static void dynamic(DynamicPropertyRegistry registry) {
    registry.add("app.client.port", testServer::getPort);
}
~~~

đăng ký method reference được đánh giá khi cần.

Phân biệt thêm `@SpringBootTest(webEnvironment = RANDOM_PORT)`: đây là cơ chế Spring Boot chọn port của chính **embedded web server ứng dụng**, có thể đọc với `@LocalServerPort`. `@DynamicPropertySource` thường giải quyết endpoint **phụ thuộc bên ngoài** như database container hoặc mock HTTP service.

Không cần dùng dynamic source chỉ để ép embedded web server của ứng dụng chọn port; `RANDOM_PORT` đã có contract riêng.

## 13. Phối hợp `@ActiveProfiles("test")`

Một test có thể dùng cả profile tĩnh và dynamic properties:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class RepositoryTest {

    @DynamicPropertySource
    static void register(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Cách phân chia:

- `@ActiveProfiles("test")`: chọn profile test và các file `application-test.yml`.
- `application-test.yml`: các giá trị ổn định như feature flags, timeout, mức logging.
- `@DynamicPropertySource`: host/port/URL/runtime credentials được fixture sinh ra.
- Testcontainers hoặc extension tương đương: tạo và quản lý resource thực tế.

Ví dụ YAML cho profile test:

~~~yaml
app:
  features:
    payments-enabled: false
  client:
    timeout: 3s
~~~

Phần tĩnh tiếp tục được dùng. Dynamic source chỉ cần đăng ký những property được xác định ở runtime.

## 14. Không nhầm dynamic property với refresh bean

Một ví dụ:

~~~java
static final AtomicReference<String> currentUrl =
        new AtomicReference<>("http://127.0.0.1:51001");

@DynamicPropertySource
static void dynamic(DynamicPropertyRegistry registry) {
    registry.add("app.api.url", currentUrl::get);
}
~~~

Sau khi context đã refresh:

~~~java
currentUrl.set("http://127.0.0.1:52002");
~~~

Lời gọi:

~~~java
environment.getProperty("app.api.url");
~~~

**có thể** đọc giá trị mới từ Supplier khi property được resolve. Nhưng bean đã inject:

~~~java
@Value("${app.api.url}")
private String apiUrl;
~~~

không tự động cập nhật field `apiUrl`.

Tương tự, record `@ConfigurationProperties` được bind ở startup có thể tiếp tục giữ URL cũ cho tới khi bean được tạo hoặc bind lại theo một cơ chế riêng.

**Hai khái niệm khác nhau:**

1. `Supplier` cấp value khi lookup.
2. Spring thực hiện bind/inject vào bean tại giai đoạn tạo bean.

`@DynamicPropertySource` không bảo đảm bước 2 chạy lại sau khi Supplier thay đổi. Nếu muốn test nhiều endpoint khác nhau, cân nhắc tạo context khác hoặc thiết kế lookup trực tiếp ở nơi cần động thực sự.

## 15. Spring TestContext caching và endpoint cũ

Spring TestContext Framework cache những application contexts có cấu hình tương đương để giảm chi phí startup. Điều này hữu ích, nhưng có thể làm lộ lỗi liên quan dynamic resources.

Ví dụ:

~~~text
Test A
  Container A: port 51001
  ApplicationContext X
  DataSource X → jdbc:...:51001

Test A kết thúc
  Container A bị stop
  ApplicationContext X vẫn có thể còn trong cache

Test B
  Container B: port 52002
  TestContext reuse ApplicationContext X
  DataSource X vẫn trỏ port 51001
  → Connection refused
~~~

**Không nên mặc định** rằng một supplier trả giá trị khác sẽ buộc Spring tạo lại context. Cache key không nhất thiết chứa value runtime đã được supplier tính.

Tài liệu Spring Framework khuyến nghị cân nhắc `@DirtiesContext` trên base class nếu các dynamic properties thay đổi giữa các subclasses và gây lỗi do context cache.

~~~java
import org.springframework.test.annotation.DirtiesContext;

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
abstract class BaseIntegrationTest {
    @DynamicPropertySource
    static void dynamic(DynamicPropertyRegistry registry) {
        // Thông tin từ fixture phù hợp từng test class.
    }
}
~~~

Cách trên yêu cầu Spring đánh dấu context bẩn sau class, nhờ đó không dùng lại context không còn phù hợp cho class kế tiếp.

**Trade-off:** tạo lại Spring context tốn thời gian. Nếu nhiều test có thể dùng **một container shared sống đủ lâu**, quản lý shared lifecycle đúng cách thường hiệu quả hơn đánh dấu context bẩn sau mọi class.

## 16. Kế thừa `@DynamicPropertySource`

Một phương thức `@DynamicPropertySource` có thể được kế thừa từ test superclass, từ interface được framework nhận diện và từ enclosing test class theo cơ chế cấu hình nested tests.

Ví dụ base class:

~~~java
public abstract class BaseDatabaseTest {

    protected static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("shared_test");

    static {
        postgres.start();
    }

    @DynamicPropertySource
    static void database(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
~~~

Các test con:

~~~java
@SpringBootTest
class OrderRepositoryTest extends BaseDatabaseTest {
}

@SpringBootTest
class CustomerRepositoryTest extends BaseDatabaseTest {
}
~~~

Ví dụ dùng một container static được start bằng static initializer như một phương án fixture shared. Cần có cơ chế cleanup/lifecycle phù hợp khi suite/JVM kết thúc và bảo đảm các test không can thiệp dữ liệu của nhau.

Nếu subclasses lại thay đổi container instance hoặc có dynamic properties khác nhau, cần đánh giá context caching như phần trước.

### 16.1. Có cần cùng database cho toàn suite không?

Chia sẻ container giảm thời gian startup nhưng có thể tạo rủi ro test A để lại dữ liệu cho test B. Có thể dùng:

- Transaction rollback cho test phù hợp.
- Cleanup dữ liệu rõ ràng.
- Schema/database riêng cho từng test group.
- Container/context độc lập nếu isolation quan trọng hơn tốc độ.

`@DynamicPropertySource` chỉ cấp thông tin kết nối; nó không tự cách ly dữ liệu.

## 17. Nguy cơ khi test chạy song song

Một số môi trường CI bật parallel test execution. Cần lưu ý:

- Static references được share giữa các tests cùng JVM.
- Container không được stop trong lúc một cached context còn cần dùng.
- Không thay đổi một static `postgres` field giữa hai test đang chạy song song.
- Không dùng `System.setProperty(...)` để thay endpoint theo từng test, vì đó là trạng thái toàn JVM.
- Đảm bảo Supplier không mutate state hoặc start một server nhiều lần.
- Nếu hai tests cùng sửa database, dùng transaction/isolation phù hợp.
- Các test contexts muốn kết nối vào resource khác nhau phải có cơ chế tách resource/context rõ ràng.

Ví dụ Supplier tốt:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
~~~

Ví dụ rủi ro:

~~~java
registry.add("app.api.url", () -> {
    server.startOnRandomPort();
    return server.baseUrl();
});
~~~

Supplier không nên start server mỗi lần property được đọc. Tài nguyên phải được chuẩn bị và bảo đảm tồn tại trước lúc lookup.

## 18. JUnit `@BeforeAll` có đủ sớm không?

Một cách khởi tạo mock server:

~~~java
static final MockServerFixture server = new MockServerFixture();

@BeforeAll
static void start() {
    server.startOnRandomPort();
}

@DynamicPropertySource
static void dynamic(DynamicPropertyRegistry registry) {
    registry.add("app.api.url", server::baseUrl);
}
~~~

Phải thận trọng: vòng đời Spring TestContext/extension và JUnit callbacks có thể khiến context cần property trước thời điểm bạn nghĩ `@BeforeAll` đã chạy. Vì thế không nên khẳng định mẫu này luôn an toàn trong mọi arrangement.

Các lựa chọn đáng cân nhắc:

- Dùng JUnit/Testcontainers extension có contract lifecycle phù hợp.
- Khởi động fixture trước khi context cần resolve property, ví dụ static initializer được kiểm soát.
- Dùng một base test fixture có lifecycle shared được xác định rõ.
- Để Supplier chỉ đọc URL/port sau khi server thực sự start.

Ví dụ minh họa một static fixture:

~~~java
static final MockServerFixture server =
        MockServerFixture.startOnRandomPort();

@DynamicPropertySource
static void dynamic(DynamicPropertyRegistry registry) {
    registry.add("app.api.url", server::baseUrl);
}
~~~

`MockServerFixture` là class mô phỏng, không phải API có sẵn của Spring. Nếu dùng WireMock, OkHttp MockWebServer hoặc một thư viện tương đương, hãy điều chỉnh theo lifecycle và API thực tế của thư viện đó.

## 19. `@ServiceConnection` của Spring Boot có thể thay thế khi phù hợp

Trong Spring Boot 3.1+, `@ServiceConnection` cùng `spring-boot-testcontainers` hỗ trợ tích hợp một số Testcontainers services vào Spring Boot auto-configuration bằng **ConnectionDetails**.

Ví dụ:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class DatabaseConnectionTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Test sử dụng auto-configured DataSource.
}
~~~

Khi Spring Boot nhận diện container và loại service được hỗ trợ, nó có thể cấp các connection details mà không cần method `@DynamicPropertySource` tự đăng ký `spring.datasource.url`, `username` và `password`.

### 19.1. So sánh

| `@DynamicPropertySource` | `@ServiceConnection` |
| --- | --- |
| Thuộc Spring TestContext | Thuộc tích hợp Spring Boot Testcontainers |
| Đăng ký property bằng key và supplier | Cấp ConnectionDetails cho các service được hỗ trợ |
| Dùng với Testcontainers hoặc resource tự quản lý | Hướng tới Testcontainers/service connection được Boot nhận diện |
| Cần biết tên property của consumer | Có thể không cần liệt kê URL/username/password keys |
| Phù hợp với custom SDK/HTTP client | Phù hợp với auto-configuration có ConnectionDetails |
| Giá trị hiện diện trong Environment theo key | Contract chính là connection abstraction, không phải mọi custom key |

Khi cần cấp `vendor.client.base-url` cho một SDK tự viết, `@DynamicPropertySource` vẫn hữu ích. Khi dùng PostgreSQL container với Boot DataSource auto-configuration, `@ServiceConnection` có thể giúp giảm boilerplate.

Không nên kết hợp cả hai để cấu hình **cùng một dependency** trừ khi hiểu rõ thứ tự ưu tiên giữa ConnectionDetails và environment properties của phiên bản Spring Boot đang chạy.

## 20. `DynamicPropertyRegistrar` là lựa chọn khác trong Spring Framework 6.2+

Spring Framework 6.2+ có `DynamicPropertyRegistrar`: một bean có thể đăng ký dynamic properties khi test ApplicationContext được khởi tạo.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.DynamicPropertyRegistrar;

@Configuration(proxyBeanMethods = false)
class TestServerConfig {

    @Bean
    TestApiServer apiServer() {
        return new TestApiServer();
    }

    @Bean
    DynamicPropertyRegistrar apiUrl(TestApiServer apiServer) {
        return registry -> registry.add(
                "app.api.base-url", apiServer::getBaseUrl);
    }
}
~~~

`TestApiServer` là class minh họa cần triển khai tương ứng; code này tập trung vào cách registrar nhận bean và method reference.

Khác biệt:

- `@DynamicPropertySource` là **static method trong test class**; rất hợp với tài nguyên do test tự tạo **bên ngoài** Spring context.
- `DynamicPropertyRegistrar` là **bean trong test context**; có thể inject một bean khác và đăng ký property lấy từ bean đó.

Registrar beans được framework phát hiện và khởi tạo sớm trước giai đoạn singleton pre-instantiation để có thể đăng ký properties. Khi registrar tham chiếu bean khác, các dependency ấy cũng có thể bị tạo sớm.

Không nên dùng registrar để phụ thuộc tùy tiện vào nhiều service phức tạp, vì lifecycle sẽ khó kiểm soát. Dự án dùng Spring Framework trước 6.2 không mặc định có API này; kiểm tra version qua dependency management.

## 21. Kiểu dữ liệu: không phải lúc nào Supplier cũng trả String

Các supplier có thể trả value kiểu nguyên thủy/wrapper hoặc object chuyển đổi được:

~~~java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("app.worker.count", () -> 4);
    registry.add("app.worker.enabled", () -> true);
    registry.add("app.worker.timeout", () -> "750ms");
    registry.add("app.worker.endpoint",
            () -> "http://127.0.0.1:50001");
}
~~~

Model:

~~~java
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        int count,
        boolean enabled,
        Duration timeout,
        URI endpoint) {
}
~~~

Spring Boot binder và conversion có thể chuyển các giá trị này sang type đích.

Cần nhớ:

- String `750ms` có thể được parse thành `Duration.ofMillis(750)`.
- Một URI hợp lệ về cú pháp không đảm bảo endpoint reachable hoặc an toàn.
- Supplier trả giá trị sai type có thể gây binding/conversion failure.
- Key thiếu vẫn có thể tạo null/default tùy model; không phải cứ dynamic property là automatically required.
- Validation nghiệp vụ vẫn cần `@Validated` và constraints/logic phù hợp.

## 22. Giá trị dynamic không nên là secret production

Cấp mật khẩu cho PostgreSQL test container:

~~~java
registry.add("spring.datasource.password", postgres::getPassword);
~~~

là bình thường khi test container cô lập. Nhưng registry không tự mã hóa hoặc làm an toàn mọi secret.

Thực hành nên tuân theo:

- Không log toàn bộ `Environment` hoặc properties object có credential.
- Không gửi token production vào test fixture chỉ để integration test “giống thật”.
- Không bật công khai Actuator endpoints như `/actuator/env` hoặc `/actuator/configprops`.
- Không đưa password vào assertion failure messages hoặc logs.
- Tránh tạo supplier làm lộ giá trị từ external account ngoài phạm vi test.
- Dùng test credentials riêng, quyền tối thiểu và dữ liệu giả.

Mức precedence cao không phải một cơ chế bảo mật; dynamic source chỉ là một cách cấp property value.

## 23. Một method đăng ký nhiều dynamic properties

Có thể đăng ký một bộ khóa trong cùng method:

~~~java
@DynamicPropertySource
static void allResources(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);

    registry.add("spring.data.redis.host", redis::getHost);
    registry.add("spring.data.redis.port",
            () -> redis.getMappedPort(6379));

    registry.add("app.partner.base-url", mockServer::baseUrl);
}
~~~

Không bắt buộc mỗi key có một method riêng.

Nhưng nếu một test chỉ kiểm tra repository, nó có thể chỉ cần PostgreSQL; việc khởi động Redis và HTTP mock server không có lợi nếu không được sử dụng. Tài nguyên càng nhiều, test càng dễ chậm hoặc thất bại vì dependency không liên quan.

Tổ chức setup theo mục tiêu của từng nhóm test. Nếu chia sẻ fixtures, xác định lifecycle và cách cô lập dữ liệu trước khi tối ưu context cache.

## 24. Khi nào không nên dùng `@DynamicPropertySource`?

Không nên dùng chỉ vì muốn truyền bất kỳ cấu hình nào.

| Tình huống | Lựa chọn đơn giản hơn/phù hợp hơn |
| --- | --- |
| Bật feature flag cố định | `@TestPropertySource` hoặc `@SpringBootTest(properties=...)` |
| Unit test thuần không có Spring context | Truyền tham số trực tiếp hoặc mock dependency |
| Cần profile test cụ thể | `@ActiveProfiles("test")` |
| Embedded web server ứng dụng chạy random port | `@SpringBootTest(webEnvironment=RANDOM_PORT)` + `@LocalServerPort` |
| ConnectionDetails từ Testcontainers đã được Boot hỗ trợ | Cân nhắc `@ServiceConnection` |
| Dynamic value đến từ bean trong context (Framework 6.2+) | `DynamicPropertyRegistrar` |
| Cập nhật cấu hình production đang chạy | Cơ chế externalized configuration/refresh production riêng |
| Test yêu cầu mỗi lần đọc trả random value khác | Thiết kế lại fixture; dynamic source không nên sinh ra endpoint không ổn định |

Với integration test dùng dynamic resources, `@DynamicPropertySource` thường là lựa chọn tự nhiên. Với unit test ngắn, nó chỉ tăng độ phức tạp.

## 25. Lỗi thường gặp và cách khắc phục

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Method không được Spring gọi | Test không chạy qua Spring TestContext hoặc thiếu annotation | Dùng `@SpringBootTest`/`@SpringJUnitConfig` và đúng annotation |
| Error về method signature | Không `static` hoặc sai số/kiểu tham số | Dùng `static void method(DynamicPropertyRegistry registry)` |
| Code không compile tại `registry.add` | Truyền value trực tiếp | Bọc bằng `() -> value` hoặc method reference |
| Mapped port getter lỗi | Container chưa start | Quản lý lifecycle trước khi resolve |
| Bean vẫn dùng production datasource | Dynamic key sai tên hoặc context đang dùng cấu hình khác | Kiểm tra `spring.datasource.*` và wiring |
| DataSource URL đúng, authentication fail | Thiếu dynamic username/password | Cấp cả bộ config từ container |
| Context test B dùng container A đã stop | Context caching và fixture lifetime lệch nhau | Điều chỉnh shared lifecycle hoặc `@DirtiesContext` |
| Value từ Environment đổi nhưng bean không đổi | Bean chỉ bind/inject lúc tạo | Tạo context/bean mới hoặc cơ chế refresh có chủ đích |
| CI không start container | Docker-compatible runtime không khả dụng/quyền hạn chế | Cấu hình Testcontainers CI đúng môi trường |
| Property từ `@TestPropertySource` không thắng | Dynamic source có precedence cao hơn | Chỉ đăng ký các key cần override |
| Supplier cho port khác mỗi lần | Có random/side effects khi lookup | Chốt endpoint khi fixture start |
| `@DynamicPropertySource` trong JUnit thuần không tác dụng | Không có Spring context | Bỏ annotation hoặc dùng Spring TestContext khi cần |
| `@ServiceConnection` không cấp custom URL key | Chưa có ConnectionDetails cho SDK đó | Dùng dynamic registry với custom property |
| Nested/inherited tests dùng value sai | Cache/lifecycle hoặc quy tắc inheritance | Kiểm tra `@NestedTestConfiguration` và context reuse |
| Lỗi ngẫu nhiên khi chạy parallel | Static fixture mutable, container bị stop sớm | Cách ly resources và giữ fixture ổn định |

Tách câu hỏi chẩn đoán thành các bước:

1. Test resource đã start thành công chưa?
2. Supplier đang đọc tài nguyên nào?
3. Supplier có trả giá trị hợp lệ và ổn định không?
4. Property name có đúng với bean/auto-configuration không?
5. Có một key khác hoặc cơ chế ConnectionDetails đang điều khiển kết nối không?
6. Context có đang được reuse từ test trước không?
7. Bean cần giá trị mới có được recreate/rebind không?

## 26. Bài tập 1: sửa phương thức không hợp lệ

Cho:

~~~java
@DynamicPropertySource
void configure(DynamicPropertyRegistry registry) {
    registry.add("app.client.port", 54321);
}
~~~

**Yêu cầu:** sửa để Spring TestContext có thể sử dụng.

**Đáp án:**

~~~java
@DynamicPropertySource
static void configure(DynamicPropertyRegistry registry) {
    registry.add("app.client.port", () -> 54321);
}
~~~

Có hai thay đổi:

- Thêm `static`.
- Thay giá trị trực tiếp bằng `Supplier`.

## 27. Bài tập 2: dynamic source ghi đè test YAML

YAML:

~~~yaml
# application-test.yml
app:
  catalog:
    port: 8080
~~~

Test:

~~~java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("app.catalog.port", () -> 55001);
}
~~~

**Câu hỏi:** `Environment.getProperty("app.catalog.port", Integer.class)` thường trả gì?

**Đáp án:** **55001**, vì dynamic source có precedence cao hơn các property thông thường trong test context.

**Câu hỏi mở rộng:** nếu dynamic source chỉ đăng ký `app.catalog.host`, `app.catalog.port` có bị xóa không?

**Đáp án:** Không. Key `port` không bị đăng ký/override bởi dynamic source, nên nó được xác định từ các property sources còn lại.

## 28. Bài tập 3: Testcontainers PostgreSQL

Giả sử có:

~~~java
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

**Yêu cầu:** điền dynamic properties đúng cho Spring Boot datasource.

**Đáp án:**

~~~java
@DynamicPropertySource
static void database(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Quan trọng: container phải được start/managed đúng lifecycle trước khi các getters được gọi. Không cố định `5432` làm host mapped port.

## 29. Bài tập 4: thay giá trị sau context startup

Test có:

~~~java
static final AtomicReference<String> url =
        new AtomicReference<>("http://localhost:50001");

@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("app.client.url", url::get);
}
~~~

Sau khi context refresh:

~~~java
url.set("http://localhost:50002");
~~~

**Câu hỏi:** bean đã inject `@Value("${app.client.url}")` có chắc tự đổi thành `50002` không?

**Đáp án:** Không. Environment có thể đọc giá trị mới khi được hỏi, nhưng field đã được inject không tự rebind. Muốn thay runtime behavior cần một thiết kế khác (lookup động, context mới, bean recreation hoặc refresh).

## 30. Bài tập 5: chọn công cụ đúng

| Nhu cầu | Lựa chọn |
| --- | --- |
| Chỉ bật `app.feature.enabled=true` trong test | `@TestPropertySource` hoặc `@SpringBootTest(properties=...)` |
| Redis container có random mapped port | `@DynamicPropertySource` |
| PostgreSQL container dùng Boot auto-configuration hỗ trợ ServiceConnection | `@ServiceConnection` nếu phiên bản và dependency phù hợp |
| Java unit test không dùng Spring | Truyền dependency/value trực tiếp |
| Giá trị động lấy từ bean trong test context, Framework 6.2+ | `DynamicPropertyRegistrar` |
| Một subclass dùng container mới nhưng context cache còn giữ container cũ | Sửa lifecycle/context caching, cân nhắc `@DirtiesContext` |

## 31. Checklist áp dụng trong dự án

1. Method có `@DynamicPropertySource`, `static`, trả `void` và nhận đúng một registry.
2. `registry.add(...)` nhận key chính xác và supplier, không phải value trực tiếp.
3. Test chạy qua Spring TestContext.
4. Resource được start trước khi supplier bị resolve.
5. Supplier không start/stop resource, không tạo số random mới, không có side effects.
6. Port/URL lấy từ fixture thật thay vì hard-code.
7. Với datasource, đăng ký URL, username và password nhất quán.
8. Nắm precedence: dynamic property thường thắng các cấu hình tĩnh của test.
9. Đừng giả định một DynamicPropertySource thay đổi thì mọi singleton tự refresh.
10. Rà soát TestContext caching khi fixtures khác nhau giữa test classes.
11. Nếu sử dụng `@DirtiesContext`, xác định chi phí tạo lại context.
12. Không truy cập global JVM properties nếu chỉ muốn cấu hình một test context.
13. Tránh log credentials, token và toàn bộ Environment.
14. Nếu chỉ cần giá trị tĩnh, dùng cơ chế khai báo test property đơn giản hơn.
15. Cân nhắc `@ServiceConnection` cho các service mà Spring Boot đã hỗ trợ.
16. Dùng `DynamicPropertyRegistrar` khi thật sự cần bean-based dynamic registration và version hỗ trợ.
17. Đảm bảo CI có container runtime tương thích, timeout và resource isolation.
18. Viết assertion kiểm tra **bean hay client thật sự sử dụng** endpoint động, không chỉ kiểm tra Supplier trả String đúng.

## 32. Ghi nhớ

- **`@DynamicPropertySource`** là cơ chế của Spring TestContext để đưa giá trị runtime của integration-test fixture vào `Environment`.
- **Method phải là `static`**, nhận đúng một `DynamicPropertyRegistry`.
- **`registry.add(name, supplier)`** đăng ký hàm cung cấp value; Supplier được gọi khi property được resolve.
- **Dynamic properties có precedence cao**, bao gồm cao hơn `@TestPropertySource`.
- **Testcontainers** là use case điển hình vì host/mapped port/JDBC URL chỉ biết ở runtime.
- **Dùng đúng key** mà Spring Boot auto-configuration hoặc `@ConfigurationProperties` đang đọc.
- **Quản lý lifecycle và TestContext cache** để tránh bean trỏ tới container đã stop.
- **Không có automatic rebinding** cho bean đã inject nếu Supplier đổi value sau startup.
- **`@ServiceConnection`** của Spring Boot có thể thay việc đăng ký datasource properties thủ công trong những tình huống hỗ trợ.
- **`DynamicPropertyRegistrar`** (Spring Framework 6.2+) dùng khi muốn đăng ký dynamic properties từ bean trong test context.

### Tài liệu tham khảo

- Spring Framework — Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Framework Javadoc — DynamicPropertySource: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/DynamicPropertySource.html
- Spring Framework Javadoc — DynamicPropertyRegistry: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/DynamicPropertyRegistry.html
- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework — Test Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Spring Boot — Testcontainers and Service Connections: https://docs.spring.io/spring-boot/reference/testing/testcontainers.html
- Testcontainers Java — JUnit Jupiter Extension: https://java.testcontainers.org/test_framework_integration/junit_5/

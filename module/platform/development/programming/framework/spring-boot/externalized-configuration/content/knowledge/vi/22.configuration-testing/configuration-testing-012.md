# Phân biệt @DynamicPropertySource với @ServiceConnection khi dùng Testcontainers

## 1. Bài toán: một container động phải được Spring Boot biết cách kết nối

Trong integration test, chúng ta thường muốn kiểm tra ứng dụng với **PostgreSQL, MySQL, MongoDB, Redis, RabbitMQ** hoặc một dịch vụ khác chạy trong container. Testcontainers giúp tạo môi trường thử nghiệm gần với hạ tầng thực mà không cần cài thủ công tất cả dịch vụ trên máy phát triển.

Ví dụ, một PostgreSQL container có thể được cấp:

~~~text
host: localhost hoặc host của container runtime
mapped port: 49xxx, thay đổi theo lượt chạy
database: integration_test
username: test_user
password: test_password
~~~

Không nên hard-code URL kết nối như:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/integration_test
~~~

vì Testcontainers thường ánh xạ cổng động và host có thể khác tùy môi trường.

Cần một cơ chế để **truyền thông tin kết nối của container** vào Spring Test ApplicationContext. Trong Spring Boot 3.3 có hai cách thông dụng:

1. **@DynamicPropertySource** — cung cấp **các property động** cho Spring Environment, như **spring.datasource.url**, **spring.datasource.username**, **spring.datasource.password**, hoặc **app.partner.base-url**.
2. **@ServiceConnection** — yêu cầu Spring Boot tạo **ConnectionDetails** từ container để những auto-configuration được hỗ trợ kết nối trực tiếp với dịch vụ, không cần tự khai báo từng property kết nối.

Cả hai đều phù hợp với Testcontainers, nhưng **chúng hoạt động ở hai lớp khác nhau**.

Bài này làm rõ API, luồng hoạt động, cách chọn, các ví dụ hoàn chỉnh bằng PostgreSQL, giới hạn với dịch vụ tùy biến, xử lý lifecycle và tình huống sử dụng kết hợp. Bối cảnh là **Spring Boot 3.3.x**, **Spring Framework 6.1**, **JUnit 5**, **Java 21**.

## 2. Kết quả học tập

Sau bài này, bạn sẽ có thể:

- Phân biệt cách **Spring Environment PropertySources** hoạt động với **ConnectionDetails**.
- Cấp một URL/port/password động từ Testcontainers bằng **@DynamicPropertySource**.
- Viết method **static** nhận **DynamicPropertyRegistry** và đăng ký **Supplier**.
- Sử dụng **@ServiceConnection** trên một container field hoặc bean.
- Biết dependency **spring-boot-testcontainers** cần thiết khi dùng ServiceConnection.
- Hiểu **JdbcConnectionDetails** được auto-configuration sử dụng như thế nào.
- Biết vì sao property **spring.datasource.url** trong Environment không nhất thiết bị thay đổi khi có ServiceConnection.
- Dùng **@ServiceConnection(name = "...")** khi cần định danh container có type chung.
- Kết hợp hai cơ chế khi test vừa có PostgreSQL vừa có property tùy chỉnh.
- Viết test chứng minh ứng dụng thực sự kết nối tới container.
- Nhận diện lỗi thường gặp về static, lifecycle, context caching, image matching, database replacement và Docker runtime.

**Tóm tắt ngắn:** **@DynamicPropertySource đăng ký property**; **@ServiceConnection đăng ký connection details cho auto-configuration**. Không nên coi chúng là hai cú pháp hoàn toàn tương đương của cùng một API.

## 3. Sơ đồ khác biệt về đường đi dữ liệu

### 3.1. @DynamicPropertySource

~~~text
Testcontainers PostgreSQL
  getJdbcUrl()
  getUsername()
  getPassword()
          |
          v
@DynamicPropertySource
DynamicPropertyRegistry.add(key, Supplier)
          |
          v
Spring Environment / PropertySource
  spring.datasource.url
  spring.datasource.username
  spring.datasource.password
          |
          v
Spring Boot DataSource auto-configuration
          |
          v
DataSource -> JDBC -> PostgreSQL container
~~~

Ở đây, test tự quyết định **tên key Spring Boot phải nhận** và lấy giá trị từ getter của container.

### 3.2. @ServiceConnection

~~~text
Testcontainers PostgreSQL
        |
        v
@ServiceConnection
        |
        v
ContainerConnectionDetailsFactory phù hợp
        |
        v
JdbcConnectionDetails
        |
        v
Spring Boot DataSource auto-configuration
        |
        v
DataSource -> JDBC -> PostgreSQL container
~~~

Ở đây, test không cần tự đăng ký **spring.datasource.url**, username và password. Spring Boot nhận diện container, tạo bean **ConnectionDetails** rồi các auto-configuration có hỗ trợ sẽ sử dụng nó.

### 3.3. Hệ quả quan trọng

- **@DynamicPropertySource** hoạt động theo **tên property** trong Environment.
- **@ServiceConnection** hoạt động theo **loại dịch vụ và kiểu ConnectionDetails** mà Spring Boot hỗ trợ.
- Với ServiceConnection, **connection details được ưu tiên hơn các connection-related configuration properties** khi auto-configuration tiêu thụ chúng.
- Điều này **không đồng nghĩa** ServiceConnection viết đè chuỗi **spring.datasource.url** trong Environment.
- Nếu code nghiệp vụ của bạn tự gọi **Environment.getProperty("spring.datasource.url")**, kết quả không nhất thiết mô tả kết nối đang được DataSource dùng dưới ServiceConnection.
- Nếu ứng dụng dùng key tùy chỉnh như **app.partner.base-url**, ServiceConnection chỉ giúp được khi có integration/ConnectionDetails phù hợp. **@DynamicPropertySource** thường đơn giản hơn.

## 4. Chuẩn bị dependencies

Một ví dụ đầy đủ sử dụng **PostgreSQL thật trong Testcontainers** và **JdbcTemplate** để gửi câu SQL **SELECT 1**.

### 4.1. Gradle

Giả sử project đã dùng Spring Boot 3.3.x và dependency management của Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Ý nghĩa:

- **spring-boot-starter-jdbc**: hỗ trợ JDBC, DataSource và JdbcTemplate.
- **org.postgresql:postgresql**: PostgreSQL JDBC driver.
- **spring-boot-starter-test**: Spring Boot Test, JUnit 5, AssertJ.
- **org.testcontainers:junit-jupiter**: tích hợp Testcontainers với JUnit Jupiter.
- **org.testcontainers:postgresql**: container chuyên dụng cho PostgreSQL.
- **spring-boot-testcontainers**: tích hợp Spring Boot **@ServiceConnection** và các connection details factories.

Nếu project có Spring Boot BOM/dependency management, thông thường không cần tự gán phiên bản cho từng dependency trên.

**Chỉ dùng @DynamicPropertySource** thì không bắt buộc thêm **spring-boot-testcontainers**. Annotation này thuộc Spring TestContext Framework. Nhưng để so sánh hai cách trong cùng project, ta thêm dependency này.

### 4.2. Maven

Ví dụ dependencies cho project đã dùng Spring Boot parent hoặc BOM:

~~~xml
<dependencies>
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
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-testcontainers</artifactId>
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
</dependencies>
~~~

Nếu dùng **@DataJpaTest** và JPA repository thay cho JdbcTemplate, bổ sung **spring-boot-starter-data-jpa** theo kiến trúc ứng dụng. Đừng thêm starter JPA nếu bài test chỉ cần JDBC.

### 4.3. Điều kiện chạy Testcontainers

Testcontainers cần một **container runtime** tương thích, thường là Docker. CI agent phải được cấp quyền truy cập runtime cần thiết.

Kiểm tra trước:

~~~bash
docker version
docker info
~~~

Nếu các lệnh không kết nối được Docker daemon, nhiều test Testcontainers sẽ không khởi động được container.

Với máy phát triển, Docker Desktop hoặc runtime tương thích phải đang chạy. Trong CI, cần cấu hình quyền và network phù hợp; không giả định mọi runner đều có Docker mặc định.

## 5. Ứng dụng thử nghiệm tối thiểu

Main class:

~~~java
package com.example.tc;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestcontainersDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                TestcontainersDemoApplication.class, args);
    }
}
~~~

Bài test dùng **JdbcTemplate**, đã được Spring Boot tự cấu hình nếu DataSource có thể khởi tạo.

Không cần tạo entity, bảng database hoặc một ứng dụng web server. Câu truy vấn:

~~~sql
SELECT 1
~~~

đủ để chứng minh JDBC connection thực sự được mở đến PostgreSQL container.

### 5.1. File cấu hình thông thường

Ví dụ **application.yml** cho môi trường local có thể có:

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://localhost:5432/localdb"
    username: local_user
    password: local_password
~~~

Trong integration test, ta không muốn vô tình sử dụng database local đó. Cả hai phương pháp trong bài đều có thể khiến DataSource của test trỏ vào container, nhưng theo **hai đường cấu hình khác nhau**.

**Không sử dụng mật khẩu production thật** trong các ví dụ test. Tài khoản/credential Testcontainers ở đây chỉ dành cho database tạm.

## 6. Cách 1 — @DynamicPropertySource với PostgreSQLContainer

**@DynamicPropertySource** được Spring Framework cung cấp trong:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
~~~

Nó cho phép một test đăng ký các property có giá trị động, rất phù hợp với container có host hoặc port được xác định sau khi start.

Ví dụ đầy đủ:

~~~java
package com.example.tc;

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
@SpringBootTest
class DynamicPostgresIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("integration_test")
                .withUsername("test_user")
                .withPassword("test_password");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {

        registry.add(
                "spring.datasource.url", postgres::getJdbcUrl);
        registry.add(
                "spring.datasource.username", postgres::getUsername);
        registry.add(
                "spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void connectsToContainer() {
        Integer result = jdbcTemplate.queryForObject(
                "SELECT 1", Integer.class);

        assertThat(result).isEqualTo(1);
    }
}
~~~

Giải thích từng phần:

1. **@Testcontainers** kích hoạt JUnit Jupiter extension quản lý Testcontainers.
2. **@Container** chỉ ra instance container do extension quản lý.
3. Field **static** tạo container được chia sẻ giữa các test methods trong class.
4. **PostgreSQLContainer** cung cấp URL JDBC, username và password thực sau khi container chạy.
5. **@DynamicPropertySource** đánh dấu method đăng ký các property động.
6. Method này **static** và nhận đúng một tham số **DynamicPropertyRegistry**.
7. **registry.add(key, Supplier)** đăng ký cách lấy giá trị; các method references như **postgres::getJdbcUrl** không cần gọi getter ngay lúc khai báo.
8. DataSource auto-configuration dùng các property **spring.datasource.*** và tạo JDBC DataSource.
9. **JdbcTemplate** thực thi query đến container, chứng minh kết nối thực.

### 6.1. Vì sao không hard-code localhost:5432?

Testcontainers có thể map cổng PostgreSQL bên trong container **5432** ra cổng host bất kỳ. **postgres.getJdbcUrl()** trả JDBC URL phù hợp với host/mapped port đang dùng.

Ví dụ một lượt chạy có thể nhận:

~~~text
jdbc:postgresql://localhost:49215/integration_test
~~~

Lượt chạy khác có thể dùng một cổng khác. Đây là giá trị ví dụ, **không phải port cố định cần cấu hình**.

### 6.2. Supplier quan trọng như thế nào?

Thay vì truyền giá trị được tính trước:

~~~java
registry.add(
        "spring.datasource.url", () -> postgres.getJdbcUrl());
~~~

ta có thể truyền method reference:

~~~java
registry.add(
        "spring.datasource.url", postgres::getJdbcUrl);
~~~

Hai cách đều thể hiện **Supplier**. Spring Test sẽ gọi Supplier khi property được giải quyết, thay vì bắt buộc lấy giá trị ngay khi đăng ký.

Phương thức **@DynamicPropertySource** không phải nơi nên thực hiện các network call nặng hoặc khởi tạo dịch vụ bất ngờ. Hãy để lifecycle container được quản lý rõ ràng.

## 7. API và quy tắc của @DynamicPropertySource

Một method hợp lệ có dạng:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add("app.external.host", server::getHost);
}
~~~

Những ràng buộc cơ bản:

- Annotation nằm trên **method**, không phải class hoặc field.
- Method phải là **static**.
- Method nhận một tham số duy nhất kiểu **DynamicPropertyRegistry**.
- **registry.add(name, supplier)** yêu cầu tên property và Supplier cung cấp giá trị.
- Có thể đăng ký nhiều key trong cùng method.
- Dynamic properties được đưa vào **Environment** dành cho Spring TestContext.

Không nhầm với:

~~~java
@TestPropertySource(properties = "spring.datasource.url=...")
~~~

**@TestPropertySource** hữu ích cho giá trị tĩnh. **@DynamicPropertySource** phù hợp khi giá trị đến từ một dịch vụ chỉ biết host/port khi runtime khởi động.

### 7.1. Độ ưu tiên của dynamic properties

Spring Framework mô tả rõ rằng dynamic properties có ưu tiên **cao hơn** các property từ **@TestPropertySource**, OS environment, Java system properties và các PropertySource thông thường.

Ví dụ test có:

~~~java
@TestPropertySource(properties = {
    "spring.datasource.url=jdbc:postgresql://wrong-host:5432/wrong"
})
~~~

nhưng method dynamic đăng ký:

~~~java
registry.add(
        "spring.datasource.url", postgres::getJdbcUrl);
~~~

thì khi resolution cùng key qua Environment, dynamic property thường được ưu tiên.

**Đừng xem đây là quyền ưu tiên tuyệt đối trong mọi cơ chế kết nối**, bởi **@ServiceConnection** không đơn thuần là một PropertySource khác. Cần phân biệt property precedence với ConnectionDetails precedence.

### 7.2. Kiểm tra giá trị thực được đưa vào Environment

Trong test DynamicPropertySource:

~~~java
@Autowired
Environment environment;

@Test
void publishesJdbcUrl() {
    assertThat(environment.getProperty(
                "spring.datasource.url"))
            .startsWith("jdbc:postgresql:");
}
~~~

Đoạn trên kiểm tra **property đã được đăng ký vào Environment**. Bài test kết nối **SELECT 1** ở mục 6 còn kiểm tra **DataSource thực sự hoạt động**. Cả hai assertion phục vụ mục đích khác nhau.

**Không log password** dù nó được đăng ký vào Environment.

## 8. Dùng @DynamicPropertySource cho custom application keys

Một ưu điểm lớn là **không phụ thuộc vào danh sách dịch vụ mà Spring Boot có ConnectionDetails factory**.

Ví dụ ứng dụng có:

~~~java
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        URI baseUrl,
        Duration requestTimeout) {
}
~~~

Và một HTTP test server/container được cấp cổng ngẫu nhiên. Ta có thể đăng ký:

~~~java
@DynamicPropertySource
static void partnerProperties(DynamicPropertyRegistry registry) {
    registry.add(
            "app.partner.base-url",
            () -> "http://" + partner.getHost()
                    + ":" + partner.getMappedPort(80));

    registry.add(
            "app.partner.request-timeout",
            () -> "2s");
}
~~~

Ví dụ này giả định class test đã định nghĩa và khởi động **partner** là một Testcontainers **GenericContainer** có exposed port **80**.

**app.partner.base-url** không phải key kết nối chuẩn của Spring Boot. Nhưng nó là property hợp lệ vì do application code của bạn định nghĩa.

Với **@ServiceConnection**, nếu không có ConnectionDetails factory và auto-configuration phù hợp cho loại partner service này, việc gắn annotation không tự biết phải cập nhật **app.partner.base-url**.

### 8.1. Cấu trúc sử dụng custom property

~~~text
Testcontainer HTTP mock
     |
     v
partner.getHost() + partner.getMappedPort(80)
     |
     v
DynamicPropertyRegistry
  app.partner.base-url
     |
     v
Environment
     |
     v
PartnerProperties.baseUrl
     |
     v
PartnerClient của ứng dụng
~~~

Đây là lý do không nên bỏ **@DynamicPropertySource** chỉ vì **@ServiceConnection** có cú pháp ngắn hơn cho PostgreSQL hoặc Redis.

## 9. Cách 2 — @ServiceConnection với PostgreSQLContainer

**@ServiceConnection** là tính năng tích hợp Testcontainers của **Spring Boot**. Nó cho phép auto-configuration suy ra thông tin kết nối từ container và sử dụng **ConnectionDetails**.

Import:

~~~java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
~~~

Dependency tương ứng:

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
~~~

Ví dụ hoàn chỉnh:

~~~java
package com.example.tc;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
class ServiceConnectionPostgresIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("integration_test")
                .withUsername("test_user")
                .withPassword("test_password");

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void connectsToContainer() {
        Integer result = jdbcTemplate.queryForObject(
                "SELECT 1", Integer.class);

        assertThat(result).isEqualTo(1);
    }
}
~~~

Điểm đáng chú ý: **không có @DynamicPropertySource** và **không có ba lời gọi registry.add(...)**.

Spring Boot sử dụng container được đánh dấu **@ServiceConnection** để tạo ConnectionDetails bean phù hợp. Đối với PostgreSQL JDBC, auto-configuration có thể sử dụng **JdbcConnectionDetails** để tạo DataSource.

### 9.1. Hai annotation có hai trách nhiệm khác nhau

Trong ví dụ:

~~~java
@Testcontainers
...
@Container
@ServiceConnection
static PostgreSQLContainer<?> postgres = ...;
~~~

- **@Testcontainers** và **@Container** là phần tích hợp JUnit/Testcontainers, quản lý container lifecycle.
- **@ServiceConnection** là phần tích hợp Spring Boot, giúp auto-configuration kết nối đến container.

**@ServiceConnection không tự thay thế @Container về mặt lifecycle** trong cách khai báo static field này. Ngược lại, **@Container** không tự tạo JdbcConnectionDetails cho Spring Boot.

### 9.2. @ServiceConnection làm việc qua ConnectionDetails

**ConnectionDetails** là abstraction chứa thông tin cần để kết nối một dịch vụ. Một loại thường gặp là **JdbcConnectionDetails**.

Thay vì Spring Boot phải dựa hoàn toàn vào:

~~~properties
spring.datasource.url=...
spring.datasource.username=...
spring.datasource.password=...
~~~

auto-configuration có thể lấy thông tin cần thiết từ JdbcConnectionDetails bean.

Đối với service connection được tạo từ Testcontainers, những connection details này được sử dụng ưu tiên hơn các connection-related configuration properties khi có auto-configuration thích hợp.

Đó là lý do một test không cần tự sao chép URL, username và password từ container vào Environment.

## 10. @ServiceConnection không đơn giản là viết vào Environment

Đây là khác biệt quan trọng dễ gây hiểu nhầm.

Giả sử **application.yml** có:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/localdb
~~~

và test có:

~~~java
@ServiceConnection
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

Khi auto-configuration được hỗ trợ sử dụng **JdbcConnectionDetails** từ container, DataSource có thể kết nối tới container **dù Environment vẫn có property spring.datasource.url mang URL local**.

Vì vậy:

~~~java
String url = environment.getProperty("spring.datasource.url");
~~~

**không nhất thiết là JDBC URL mà DataSource đang sử dụng** trong trường hợp ServiceConnection.

Muốn kiểm tra kết nối thực tế, sử dụng:

- Câu query đơn giản qua JdbcTemplate.
- Truy cập DataSource/Connection metadata trong phạm vi test.
- Quan sát JdbcConnectionDetails bean khi cần chẩn đoán chính xác.

**Không viết test chỉ assert Environment.getProperty("spring.datasource.url") bằng container.getJdbcUrl() rồi coi đó là điều kiện bắt buộc của @ServiceConnection.** Test đó đang kiểm tra một cơ chế không được ServiceConnection hứa sẽ thực hiện.

### 10.1. Ví dụ quan sát DataSource thực

~~~java
@Autowired
DataSource dataSource;

@Test
void usesContainerDatabase() throws Exception {
    try (Connection connection =
            dataSource.getConnection()) {

        String actualUrl =
                connection.getMetaData().getURL();

        assertThat(actualUrl)
                .contains("integration_test");
    }
}
~~~

Imports:

~~~java
import java.sql.Connection;
import javax.sql.DataSource;
~~~

Metadata của JDBC driver thường phản ánh URL thực của connection. Đây là assertion kiểm tra kết nối, không dựa vào cách Environment đang lưu property gốc.

Với hệ thống nhiều DataSource, cần xác định đúng DataSource bean đang được kiểm thử.

## 11. So sánh nhanh hai annotation

| Tiêu chí | @DynamicPropertySource | @ServiceConnection |
| --- | --- | --- |
| Nơi cung cấp | **Spring Framework TestContext** | **Spring Boot Testcontainers** |
| Annotation dùng trên | **static method** | **container field** hoặc **@Bean** container |
| API chính | **DynamicPropertyRegistry.add(key, Supplier)** | **ConnectionDetails factories** |
| Đơn vị dữ liệu | Property theo tên key trong Environment | ConnectionDetails bean cho dịch vụ |
| Cần biết tên key | Có, test tự chọn | Không cần với service được factory hỗ trợ |
| URL/username/password JDBC | Tự đăng ký các key | Tự suy ra từ PostgreSQLContainer |
| Property tùy biến app.* | Dùng trực tiếp | Không tự hỗ trợ nếu thiếu factory/consumer |
| Quy tắc ưu tiên | Dynamic property cao trong Environment | ConnectionDetails ưu tiên hơn connection properties ở consumer được hỗ trợ |
| Dependency riêng | Spring TestContext (qua starter-test) | **spring-boot-testcontainers** |
| Kiểm tra đúng | Environment key và hoạt động của client | ConnectionDetails/hoạt động của client |
| Phạm vi ứng dụng | Rộng: bất kỳ key nào | Chủ yếu dịch vụ có ConnectionDetails factory |
| Boilerplate cho JDBC | Đăng ký url, username, password | Gắn annotation, không đăng ký ba key |
| Có thể dùng cùng nhau | Có | Có |

**Quy tắc chọn:** Nếu một dịch vụ đã có ServiceConnection factory và application dùng auto-configuration hỗ trợ ConnectionDetails, **@ServiceConnection** thường ngắn gọn. Nếu cần truyền **tên property tùy chỉnh**, **@DynamicPropertySource** phù hợp hơn.

## 12. Những dịch vụ nào thường được @ServiceConnection nhận diện?

Spring Boot 3.3 cung cấp các **ContainerConnectionDetailsFactory** cho nhiều loại container và dịch vụ.

Ví dụ tiêu biểu:

- **PostgreSQLContainer**, **MySQLContainer** và những JDBC database containers phù hợp có thể cung cấp **JdbcConnectionDetails**.
- **MongoDBContainer** có thể cung cấp **MongoConnectionDetails**.
- **RabbitMQContainer** có thể cung cấp **RabbitConnectionDetails**.
- **Neo4jContainer** có thể cung cấp **Neo4jConnectionDetails**.
- Kafka/Redpanda containers có factory phù hợp với dòng thư viện được hỗ trợ.
- Container image có repository **redis** có thể được nhận diện để cung cấp **RedisConnectionDetails**.
- Các kết nối khác như Flyway, Liquibase, R2DBC có factory tương ứng tùy container.

**Không phải mọi GenericContainer đều tự nhận diện được.** Cơ chế factory có thể dựa trên:

1. **Container class** cụ thể, ví dụ PostgreSQLContainer.
2. **Docker image name**, ví dụ repository **redis**.
3. **@ServiceConnection(name = "...")** làm hint cho loại container/image, khi thích hợp.

Dùng đúng API và factory list của **Spring Boot version** đang triển khai. Không suy rằng annotation sẽ tạo ConnectionDetails cho bất kỳ image tự đặt nào.

### 12.1. PostgreSQL có thể liên quan nhiều kiểu connection details

Spring Boot 3.3 tài liệu hóa rằng một PostgreSQLContainer có thể phù hợp với cả **JdbcConnectionDetails** và **R2dbcConnectionDetails**.

Theo mặc định, các connection details phù hợp có thể được tạo cho container. Nhưng service connection nào thực sự được **tiêu thụ** còn phụ thuộc classpath và auto-configuration của ứng dụng.

Ví dụ:

- Dự án JDBC thường sử dụng JdbcConnectionDetails.
- Dự án reactive R2DBC có thể sử dụng R2dbcConnectionDetails.
- Dự án không dùng R2DBC không nên suy rằng chỉ vì một ConnectionDetails loại đó tồn tại mà một R2DBC client sẽ tự được tạo.

Khi cần hạn chế type, annotation **@ServiceConnection** hỗ trợ thuộc tính **type** để chỉ định nhóm connection details cần tạo.

### 12.2. @ServiceConnection(type = ...)

Ví dụ muốn chỉ khai báo JDBC:

~~~java
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

@ServiceConnection(type = JdbcConnectionDetails.class)
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

Chỉ dùng khi thực sự cần giới hạn factory result. Trong ví dụ JDBC đơn giản, **@ServiceConnection** không có thuộc tính thường đã đủ.

## 13. @ServiceConnection trên container @Bean

Ngoài static field trong JUnit test, Spring Boot còn hỗ trợ container được đăng ký thành Spring bean.

Ví dụ test configuration:

~~~java
package com.example.tc;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgreSqlTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
                .withDatabaseName("integration_test")
                .withUsername("test_user")
                .withPassword("test_password");
    }
}
~~~

Test import cấu hình:

~~~java
package com.example.tc;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Import(PostgreSqlTestConfiguration.class)
class SpringManagedContainerTest {

    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void canQueryDatabase() {
        Integer answer = jdbcTemplate.queryForObject(
                "SELECT 1", Integer.class);
        assertThat(answer).isEqualTo(1);
    }
}
~~~

Trong cách này, Spring Boot quản lý container **như một bean** trong test ApplicationContext. Container bean được tạo và start theo lifecycle mà Boot quản lý, và bị stop khi context đóng.

**Không bắt buộc thêm @Testcontainers / @Container** cho một container **@Bean** đã được Spring Boot quản lý theo cách này. Không trộn lẫn hai cơ chế lifecycle một cách không cần thiết.

### 13.1. Khi nào chọn container bean?

Phù hợp nếu:

- Nhiều test classes cần chia sẻ test configuration qua **@Import**.
- Muốn container lifecycle gắn với Spring ApplicationContext.
- Đang xây cấu hình test tái sử dụng ở một module.
- Muốn kết hợp container management với các bean phụ thuộc.

Nhưng cần hiểu **Spring TestContext caching**: container bean có thể sống cùng context được cache và dừng khi context đóng. Một số field-level containers do JUnit quản lý có lifecycle khác, dẫn tới nguy cơ context giữ bean kết nối sau khi container đã bị stop nếu tái sử dụng cache không phù hợp.

## 14. Vì sao @Bean GenericContainer có thể cần name

Đối với container cụ thể:

~~~java
@Bean
@ServiceConnection
PostgreSQLContainer<?> postgresContainer() {
    return new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Spring Boot biết return type là **PostgreSQLContainer**, nên có thể suy ra factory phù hợp.

Nhưng với một bean trả về:

~~~java
@Bean
@ServiceConnection
GenericContainer<?> redisContainer() {
    return new GenericContainer<>("redis:7");
}
~~~

Spring Boot không thể gọi bean method sớm chỉ để biết tên image, bởi điều đó có thể gây **eager initialization**. Type **GenericContainer** không đủ để khẳng định dịch vụ Redis.

Cách phù hợp:

~~~java
package com.example.tc;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.GenericContainer;

@TestConfiguration(proxyBeanMethods = false)
public class RedisTestConfiguration {

    @Bean
    @ServiceConnection(name = "redis")
    GenericContainer<?> redisContainer() {
        return new GenericContainer<>("redis:7")
                .withExposedPorts(6379);
    }
}
~~~

**name = "redis"** cung cấp hint cho factory. Để một RedisConnectionDetails thực sự được auto-configuration sử dụng, ứng dụng cần các dependencies/auto-configuration client Redis phù hợp; đoạn class chỉ minh họa registration.

### 14.1. Custom registry image/mirror

Ví dụ công ty dùng image:

~~~text
registry.company.invalid/mirror/redis-custom:7
~~~

Nếu factory không nhận diện repository image tùy biến, có thể dùng:

~~~java
@ServiceConnection(name = "redis")
~~~

để cho biết đây là dịch vụ tương thích Redis, với điều kiện image thực sự cung cấp giao thức Redis ở port thích hợp.

**Không dùng name tùy ý chỉ để ép factory chạy** nếu container không thực sự tương thích với dịch vụ đó.

## 15. Spring Boot ServiceConnection và @ConfigurationProperties

Giả sử một cấu hình có:

~~~java
@ConfigurationProperties(prefix = "app.partner")
public record PartnerProperties(
        URI baseUrl,
        String apiKey) {
}
~~~

Nếu test tạo một **GenericContainer** chạy dịch vụ partner mock, **@ServiceConnection** không tự tìm PartnerProperties rồi điền **baseUrl**. Annotation này không phải một phiên bản tổng quát của **@ConfigurationProperties binding**.

Ngược lại, **@DynamicPropertySource** có thể cung cấp giá trị cho model trên bằng key canonical:

~~~java
registry.add(
        "app.partner.base-url",
        () -> "http://" + partner.getHost()
                + ":" + partner.getMappedPort(80));
~~~

Spring Boot Binder tiếp tục bind vào PartnerProperties như các property khác.

**Phân biệt hai đường đi:**

~~~text
@DynamicPropertySource
    -> Environment key
    -> @ConfigurationProperties / @Value / DataSourceProperties

@ServiceConnection
    -> ConnectionDetails bean
    -> Auto-configuration biết dùng ConnectionDetails
~~~

Một hệ thống có thể cung cấp **custom ConnectionDetails** cho dịch vụ riêng, nhưng đó là một phần phát triển hạ tầng khác và không được thực hiện tự động chỉ bằng annotation trên bất kỳ container nào.

## 16. Dùng kết hợp hai cách trong cùng test

Tình huống thực tế: ứng dụng có **PostgreSQL** được Spring Boot quản lý qua DataSource auto-configuration, đồng thời có **một HTTP service giả lập** mà application code đọc base URL qua **app.partner.base-url**.

Lựa chọn:

- PostgreSQL → **@ServiceConnection**.
- HTTP mock → **@DynamicPropertySource**.

Ví dụ:

~~~java
package com.example.tc;

import org.junit.jupiter.api.Test;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class MixedConnectionsTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    static GenericContainer<?> partner =
            new GenericContainer<>("nginx:1.27-alpine")
                .withExposedPorts(80);

    @DynamicPropertySource
    static void partnerProperties(
            DynamicPropertyRegistry registry) {

        registry.add("app.partner.base-url", () ->
                "http://" + partner.getHost()
                        + ":" + partner.getMappedPort(80));
    }

    @Test
    void contextStarts() {
        // Trong ứng dụng thật:
        // assert PartnerProperties và truy vấn DB hoặc HTTP mock.
    }
}
~~~

Ví dụ dùng Nginx container chỉ để minh họa một HTTP endpoint có mapped port. Nếu ứng dụng thực sự cần API response cụ thể, hãy dùng **WireMock**, **MockServer** hoặc một container mock được cấu hình theo contract của API đó.

**Hai annotation không xung đột chỉ vì có cùng một test**. Chúng phục vụ hai nhu cầu: connection details chuẩn và property tùy biến.

### 16.1. Cẩn trọng không cung cấp hai cơ chế cho cùng JDBC connection khi không cần

Ví dụ có cả:

~~~java
@ServiceConnection
static PostgreSQLContainer<?> postgres = ...;
~~~

và:

~~~java
registry.add("spring.datasource.url", postgres::getJdbcUrl);
~~~

trong cùng một test.

Nó có thể vẫn hoạt động, nhưng tạo **hai đường cung cấp thông tin** cho cùng connection. Vì JdbcConnectionDetails có thể được ưu tiên, việc thêm property sẽ gây nhầm khi debug.

**Khuyến nghị:** chọn một đường làm chủ cho từng dịch vụ, trừ khi bạn có mục đích kiểm thử rõ ràng.

## 17. Dùng @DynamicPropertySource với container không được Boot hỗ trợ

Không phải mọi Testcontainers module đều có factory tương ứng trong Spring Boot 3.3.

Một dịch vụ tùy biến có thể chạy tại:

~~~text
http://<host>:<mapped-port>
~~~

và ứng dụng dùng:

~~~properties
app.search.endpoint=...
app.search.token=...
~~~

Một test có thể đăng ký:

~~~java
@DynamicPropertySource
static void dynamicSearchProperties(
        DynamicPropertyRegistry registry) {

    registry.add("app.search.endpoint", () ->
            "http://" + searchContainer.getHost()
                    + ":" + searchContainer.getMappedPort(8080));

    registry.add("app.search.token",
            () -> "test-only-token");
}
~~~

Đoạn minh họa giả định **searchContainer** đã được định nghĩa/start và expose port 8080.

Điểm mạnh là cơ chế property **không cần hiểu loại container**. Chỉ cần trả đúng giá trị mà ứng dụng mong đợi.

Nếu ứng dụng dùng:

~~~java
@ConfigurationProperties(prefix = "app.search")
public record SearchProperties(
        URI endpoint,
        String token) {
}
~~~

thì Binder sẽ chuyển property động thành object này khi bean được khởi tạo.

### 17.1. Test token không phải production secret

Sử dụng credential giả chỉ cho test container. Không copy API token production vào JUnit source hoặc CI variables không được bảo vệ. Không in token ra log ngay cả khi đang test.

## 18. Vấn đề precedence: property và connection details là hai trục

Điều này cần được kiểm tra riêng:

### 18.1. Dynamic properties có độ ưu tiên cao trong Environment

Giả sử:

~~~java
@TestPropertySource(properties = {
    "spring.datasource.url=jdbc:postgresql://wrong-host/db"
})
~~~

và:

~~~java
@DynamicPropertySource
static void postgresProps(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl);
}
~~~

Spring TestContext ưu tiên dynamic property khi giải quyết **spring.datasource.url**.

### 18.2. ServiceConnection dùng ConnectionDetails

Nếu thay method trên bằng:

~~~java
@ServiceConnection
static PostgreSQLContainer<?> postgres = ...;
~~~

auto-configuration có thể dùng **JdbcConnectionDetails** từ container. Đây không phải “property source có ưu tiên cao hơn” theo cùng ý nghĩa với DynamicPropertySource.

Vì vậy, hai câu hỏi khác nhau:

1. **Environment giải quyết spring.datasource.url thành chuỗi nào?**
2. **DataSource auto-configuration đang lấy JDBC connection details từ đâu?**

Để xác định DB thực, câu trả lời thứ hai hoặc một truy vấn SQL thực tế quan trọng hơn.

### 18.3. Ví dụ false-positive khi kiểm tra Environment

Một test dùng ServiceConnection có thể thấy:

~~~text
Environment:
  spring.datasource.url = giá trị local/default nào đó

DataSource:
  kết nối tới PostgreSQL Testcontainers
~~~

Hai trạng thái không nhất thiết mâu thuẫn. ConnectionDetails đã giúp auto-configuration chọn kết nối container dù property Environment còn giữ giá trị khác.

## 19. Lifecycle của container và test class

Khi dùng:

~~~java
@Testcontainers
class ExampleTest {
    @Container
    static PostgreSQLContainer<?> postgres = ...;
}
~~~

JUnit Testcontainers extension quản lý field static trong phạm vi test class:

- Container static được chia sẻ giữa các test methods của class.
- Thông thường container được start trước các test methods và stop khi class hoàn tất.
- Spring TestContext có thể **cache ApplicationContext** để tái sử dụng giữa các test classes.
- Lifecycle của static JUnit container và lifecycle của cached context **không nhất thiết trùng nhau**.

Nếu một cached context giữ DataSource trỏ tới container đã bị stop, các test sau có thể lỗi dù config ban đầu đúng.

### 19.1. Cách giảm rủi ro lifecycle

- Chọn rõ container lifecycle: JUnit field hay Spring-managed bean.
- Tránh chia sẻ ApplicationContext giữa test classes có những container khác nhau nhưng configuration metadata bị xem là tương đương.
- Với những test subclasses kế thừa **@DynamicPropertySource** nhưng giá trị động thay đổi, cân nhắc **@DirtiesContext** theo hướng dẫn Spring Framework.
- Khi dùng Spring-managed **@Bean** container, hiểu rằng container thường sống cùng test context và dừng khi context đóng.
- Không tự start/stop một container trong mỗi @Test nếu Spring context được tạo một lần và bean đã kết nối từ trước.
- Nếu test suite lớn, xác định rõ chính sách reuse, isolation và cleanup.

### 19.2. Khi nào không cần @DirtiesContext?

Không thêm **@DirtiesContext** cho mọi test một cách máy móc. Nó buộc Spring không tái sử dụng context, làm test chậm và có thể tăng số lần khởi tạo container.

Chỉ dùng khi có lý do rõ ràng về context state hoặc dynamic property values thay đổi giữa các test và cần context mới.

## 20. Kết hợp với @SpringBootTest

Hai ví dụ chính dùng:

~~~java
@SpringBootTest
@Testcontainers
~~~

**@SpringBootTest** tải Spring Boot application context, giúp test sử dụng DataSource và các auto-configuration thực tế.

**@Testcontainers** quản lý lifecycle của field-level containers.

**@DynamicPropertySource** hoặc **@ServiceConnection** cung cấp thông tin kết nối.

Nếu test cần thực sự chạy một REST server, có thể dùng:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
~~~

sau đó dùng các test utilities phù hợp cho HTTP assertions.

Không cần chạy embedded server nếu bài test chỉ cần JDBC query. Môi trường web của SpringBootTest nên được chọn theo mục đích để tránh chi phí không cần thiết.

### 20.1. @DynamicPropertySource không dành riêng cho SpringBootTest

Annotation này thuộc **Spring TestContext Framework**, nên có thể dùng trong nhiều kiểu Spring integration tests khác được TestContext hỗ trợ.

### 20.2. @ServiceConnection cũng không yêu cầu đúng một kiểu test class

Tính năng này có thể phối hợp với Spring Boot test slices, hoặc container beans trong test configuration, miễn là infrastructure và auto-configuration cần thiết được tạo.

Điều quan trọng là **test có thực sự tạo và sử dụng connection details hay không**.

## 21. @DataJpaTest và việc thay DataSource trong test slice

Nếu thay ví dụ JdbcTemplate bằng JPA repositories, bạn có thể sử dụng:

~~~java
@DataJpaTest
@Testcontainers
class RepositoryTest {
    ...
}
~~~

Tuy nhiên, **@DataJpaTest** là một test slice được thiết kế để cấu hình kiểm thử tầng persistence và có thể dùng embedded test database theo những quy tắc nhất định.

Khi muốn chắc chắn test sử dụng PostgreSQL Testcontainers thay vì một embedded database, có thể dùng:

~~~java
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
~~~

Ví dụ:

~~~java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class OrderRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired repository rồi kiểm tra hành vi persistence.
}
~~~

Imports:

~~~java
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
~~~

**Chú ý:** chi tiết tự thay thế DataSource và tích hợp ServiceConnection của các test slice phụ thuộc Spring Boot version và cấu hình cụ thể. Dùng **replace=NONE** khi muốn thể hiện rõ ý định không thay connection container bằng embedded database, rồi viết assertion kiểm tra DB thực tế.

### 21.1. Tại sao test PostgreSQL thật quan trọng?

Một số câu SQL, kiểu dữ liệu, index và transaction behavior khác giữa PostgreSQL với H2/HSQLDB. Test repository chạy qua embedded DB không luôn đại diện chính xác cho production PostgreSQL.

Testcontainers cung cấp backend thật trong môi trường được cô lập, giúp test migration/schema/queries đáng tin cậy hơn.

## 22. Kiểm tra DataSource thực thay vì chỉ kiểm tra context starts

Một test kém chứng minh:

~~~java
@Test
void contextLoads() {
}
~~~

Context có thể khởi tạo nhưng không hề chạy truy vấn trên backend mà bạn muốn.

Một test mạnh hơn:

~~~java
@Autowired
JdbcTemplate jdbc;

@Test
void runsQueryOnContainer() {
    Integer value = jdbc.queryForObject(
            "SELECT 1", Integer.class);

    assertThat(value).isEqualTo(1);
}
~~~

Hoặc:

~~~java
@Autowired
DataSource dataSource;

@Test
void connectsToExpectedDatabase() throws Exception {
    try (Connection connection =
            dataSource.getConnection()) {

        assertThat(connection.getMetaData()
                .getURL())
                .contains("integration_test");
    }
}
~~~

Các assertion này giúp phát hiện tình huống cấu hình bị override sai hoặc một DataSource khác được tạo.

**Không chỉ kiểm tra container.isRunning()**. Container chạy không chứng minh Spring bean đang kết nối tới nó.

## 23. Khi nào cần @ServiceConnection(name=...)?

Một ví dụ Redis:

~~~java
@Testcontainers
@SpringBootTest
class RedisIntegrationTest {

    @Container
    @ServiceConnection(name = "redis")
    static GenericContainer<?> redis =
            new GenericContainer<>("redis:7")
                .withExposedPorts(6379);

    // Autowire RedisTemplate khi có Redis starter phù hợp.
}
~~~

Ở một static field, Boot có thể xem image name và tìm factory theo repository. **name="redis"** giúp thể hiện rõ identity, đặc biệt khi dùng generic/custom image.

Ở một **@Bean method trả về GenericContainer**, name thường quan trọng hơn vì Spring Boot không gọi method sớm chỉ để khám phá image.

Nếu container cung cấp giao thức khác hoặc Redis không thực sự lắng nghe port 6379, chỉ gắn name sẽ không làm client kết nối thành công. ServiceConnection không thay thế thiết kế container đúng và network readiness.

## 24. Khi service có nhiều endpoint hoặc authentication đặc biệt

Một container tùy biến có thể cấp:

- HTTP host + port.
- gRPC port.
- Endpoint TLS.
- Username/password.
- API token.
- Một endpoint quản trị và một endpoint dữ liệu riêng.

Với **@DynamicPropertySource**, có thể đăng ký các key riêng:

~~~java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add(
            "app.service.http-url",
            () -> "http://" + service.getHost()
                    + ":" + service.getMappedPort(8080));
    registry.add(
            "app.service.grpc-port",
            () -> service.getMappedPort(9090));
    registry.add(
            "app.service.token",
            () -> "test-token");
}
~~~

Ví dụ giả định container đã expose cả hai port. Tên **app.service.*** là namespace tự định nghĩa.

Với **@ServiceConnection**, muốn đạt mức tích hợp tương tự thì cần ConnectionDetails abstraction và factory mà code auto-configuration thực sự tiêu thụ. Không nên kỳ vọng Boot tự phát hiện toàn bộ endpoint tùy ý của một GenericContainer.

## 25. Thử nghiệm một context có hai cơ chế override

Giả sử:

**application-test.yml**:

~~~yaml
spring:
  datasource:
    url: "jdbc:postgresql://localhost:5432/static_test_db"
    username: static_user
    password: static_password

app:
  partner:
    base-url: "http://localhost:9000"
~~~

Trong test:

- **@ServiceConnection** trỏ JDBC DataSource tới PostgreSQLContainer.
- **@DynamicPropertySource** override **app.partner.base-url** sang HTTP mock container.

Kết quả hợp lý:

~~~text
DataSource:
    dùng JdbcConnectionDetails của PostgreSQLContainer

PartnerProperties:
    baseUrl bind từ app.partner.base-url
    do DynamicPropertySource cung cấp

Environment.getProperty("spring.datasource.url"):
    có thể vẫn là URL tĩnh từ application-test.yml
~~~

Trạng thái này có thể hoàn toàn đúng, và cho thấy hai cách hợp tác chứ không loại trừ nhau.

### 25.1. Đừng dùng kết quả Environment để suy ra mọi connection

Một bean có thể dùng connection details từ một nguồn cao hơn property. Khi debug, xác định đúng consumer:

- DataSource.
- R2DBC ConnectionFactory.
- MongoClient.
- Rabbit connection factory.
- Redis client.
- Custom client của ứng dụng.

Sau đó xác định nó đọc Environment hay ConnectionDetails.

## 26. Lưu ý khi chạy trong CI

Testcontainers thường yêu cầu container runtime có thể khởi chạy image, publish/mapping port và truy cập network thích hợp.

Checklist CI:

1. Runner có Docker hoặc compatible runtime?
2. User chạy test có quyền truy cập daemon/socket theo chính sách bảo mật?
3. Image **postgres:16-alpine** có thể pull hoặc đã cache?
4. Registry có rate limit hoặc yêu cầu authentication?
5. Network policy có ngăn truy cập mapped ports?
6. Các dependencies Testcontainers có version phù hợp với Spring Boot BOM?
7. Container health/startup readiness có timeout hợp lý?
8. Parallel tests có tiêu thụ quá nhiều memory/CPU?
9. Database cleanup/isolation có rõ ràng giữa test methods?
10. Có đang vô tình dùng database production hay credential thật?
11. Logs có giữ thông tin hữu ích khi container không start?
12. Test suite có fail do context cache/container lifecycle không?

### 26.1. Đừng dùng cổng host cố định nếu không cần

Nếu mọi test cố bind host port 5432, parallel CI jobs có thể xung đột và những máy có PostgreSQL local sẽ gặp lỗi.

Ưu tiên để Testcontainers cấp mapped port động; lấy endpoint qua getter hoặc ServiceConnection.

### 26.2. Image version

Ví dụ dùng **postgres:16-alpine** để minh họa. Trong project thực tế, nên chọn version PostgreSQL gần với production, cập nhật có kiểm soát và theo chính sách reproducibility của nhóm.

Không dùng image **latest** một cách vô điều kiện nếu muốn test kết quả ổn định theo thời gian.

## 27. Xử lý lỗi: @DynamicPropertySource không được gọi

Dấu hiệu:

- DataSource vẫn dùng URL local.
- Context fail với lỗi không kết nối được localhost:5432.
- Không thấy property động được áp dụng.

Kiểm tra:

- Method có annotation **@DynamicPropertySource** đúng package Spring Test không?
- Method là **static** không?
- Method có đúng một tham số **DynamicPropertyRegistry** không?
- Test có chạy qua Spring TestContext, ví dụ **@SpringBootTest** không?
- Tên key có đúng **spring.datasource.url**, **username**, **password** không?
- Container field có được quản lý và start đúng lifecycle không?
- Có một custom DataSource bean bỏ qua những property này không?

Ví dụ sai:

~~~java
@DynamicPropertySource
void register(DynamicPropertyRegistry registry) {
    // Sai: method không static.
}
~~~

Ví dụ đúng:

~~~java
@DynamicPropertySource
static void register(DynamicPropertyRegistry registry) {
    // ...
}
~~~

## 28. Xử lý lỗi: @ServiceConnection không có tác dụng

Dấu hiệu:

- DataSource không trỏ vào container.
- Bean ConnectionDetails phù hợp không tồn tại.
- Spring Boot vẫn cần spring.datasource.url hoặc connection properties.
- Spring Boot không nhận diện GenericContainer.

Kiểm tra:

1. Có **spring-boot-testcontainers** trong **testImplementation/test scope** không?
2. Annotation import đúng **org.springframework.boot.testcontainers.service.connection.ServiceConnection** không?
3. Container được khai báo dưới dạng static field hoặc Spring bean được xử lý đúng không?
4. Container class có factory tương ứng trong Spring Boot version đó không?
5. Nếu dùng **GenericContainer @Bean**, có cần **name="redis"** hoặc tên image phù hợp không?
6. Có đúng auto-configuration/client dependencies không, ví dụ JDBC starter + PostgreSQL driver?
7. App có custom DataSource tự tạo mà bỏ qua ConnectionDetails không?
8. Container có thực sự khởi động và cung cấp protocol/port phù hợp không?
9. Có một test slice thay DataSource bằng embedded DB không?
10. Nếu dùng nhiều container cùng loại, auto-configuration có chọn đúng bean/service cần dùng không?

Đừng chỉ thêm nhiều annotation để thử vận may. Xác định xem thiếu ở **container lifecycle**, **factory matching**, **ConnectionDetails bean** hay **client auto-configuration**.

## 29. Lỗi thường gặp và cách tránh

### Lỗi 1: nghĩ @ServiceConnection luôn thiết lập spring.datasource.url

Sai tầng abstraction. Nó cung cấp **JdbcConnectionDetails** và các connection details khác khi được hỗ trợ. Environment có thể không thay đổi property URL.

### Lỗi 2: nghĩ @DynamicPropertySource chỉ dành cho database

Nó hỗ trợ bất kỳ key nào, kể cả **app.partner.base-url** hoặc **app.service.grpc-port**.

### Lỗi 3: bỏ dependency spring-boot-testcontainers

Dùng @ServiceConnection của Spring Boot cần module tích hợp tương ứng. **spring-boot-starter-test** một mình không thay thế dependency này.

### Lỗi 4: sử dụng GenericContainer nhưng không giúp factory nhận diện dịch vụ

Với @Bean method có return type GenericContainer, Boot không biết image trước khi bean khởi tạo. Dùng **@ServiceConnection(name = "redis")** khi phù hợp hoặc type container cụ thể.

### Lỗi 5: hard-code cổng host

Các container có mapped ports động. Dùng **getJdbcUrl()**, **getHost()**, **getMappedPort()** hoặc ConnectionDetails.

### Lỗi 6: method @DynamicPropertySource không static

Spring TestContext yêu cầu static method với một DynamicPropertyRegistry argument.

### Lỗi 7: đăng ký cả ConnectionDetails và property cho cùng dịch vụ mà không có mục đích

Hai đường cấu hình gây nhầm về precedence và khó biết giá trị nào thực sự được consumer sử dụng.

### Lỗi 8: test chỉ kiểm tra context loads

Nên chạy truy vấn JDBC hoặc kiểm tra client hoạt động để biết ứng dụng kết nối đúng container.

### Lỗi 9: làm mất cấu hình trong test context cache

Một context được cache có thể giữ DataSource trỏ container đã dừng. Kiểm soát lifecycle/test isolation, dùng @DirtiesContext khi thực sự cần.

### Lỗi 10: dùng @ServiceConnection để cấp app.custom.key

Nếu không có factory/consumer hỗ trợ, annotation không tự liên kết arbitrary key. Dùng @DynamicPropertySource cho key tùy chỉnh.

### Lỗi 11: thiếu test slice configuration

Với **@DataJpaTest**, xem xét **@AutoConfigureTestDatabase(replace = NONE)** nếu muốn bảo đảm không dùng embedded database thay Testcontainers.

### Lỗi 12: test container nhưng cấu hình vẫn trỏ production

Đây là rủi ro nghiêm trọng. Test phải được cô lập khỏi endpoint/credential production; không dựa vào defaults production để khởi tạo DataSource.

### Lỗi 13: tự start/stop container sai lúc

Nếu container stop trong khi Spring context còn giữ connection pool, có thể xuất hiện lỗi connection timeout. Chọn lifecycle rõ ràng và tránh stop container trong test method tùy tiện.

### Lỗi 14: không kiểm tra Docker runtime

Không có daemon/compatible runtime, Testcontainers không thể start service như mong đợi. Cần thiết kế CI execution environment phù hợp.

### Lỗi 15: cho rằng tất cả ConnectionDetails factories đã có ở mọi version

Spring Boot bổ sung factory theo từng phiên bản. Với dòng 3.3, dùng danh sách được tài liệu 3.3 công bố; không áp dụng vô điều kiện các ví dụ từ tài liệu phiên bản mới hơn.

### Lỗi 16: dùng Testcontainers credential như secret production

Container credentials trong test là dữ liệu giả, chỉ dùng cho test. Không phát tán password thật trong Java source hay CI logs.

## 30. Bài thực hành

### Bài A — cấu hình PostgreSQL bằng DynamicPropertySource

1. Thêm dependencies JDBC, PostgreSQL driver, Testcontainers và starter-test.
2. Tạo PostgreSQLContainer static.
3. Gắn **@Testcontainers**, **@Container**.
4. Viết **@DynamicPropertySource static**.
5. Đăng ký URL, username, password bằng **registry.add**.
6. Inject JdbcTemplate và chạy SELECT 1.
7. In **không nhạy cảm** JDBC URL hoặc database name trong test để xem mapped port động.

**Kết quả mong đợi:** DataSource kết nối container thật, không dùng database local.

### Bài B — chuyển sang ServiceConnection

1. Giữ PostgreSQLContainer static.
2. Xóa method **@DynamicPropertySource**.
3. Gắn **@ServiceConnection** lên field container.
4. Đảm bảo **spring-boot-testcontainers** có trong test classpath.
5. Chạy lại query SELECT 1.
6. So sánh số dòng code và cơ chế connection.

**Kết quả mong đợi:** auto-configuration dùng JdbcConnectionDetails của container.

### Bài C — so sánh property trong Environment

1. Trong application-test.yml đặt một JDBC URL giả.
2. Chạy test ServiceConnection và query tới PostgreSQL container.
3. Đọc **Environment.getProperty("spring.datasource.url")**.
4. So sánh với URL thực từ **DataSource.getConnection().getMetaData().getURL()**.

**Kết quả mong đợi:** thấy rõ Environment property không nhất thiết mô tả ConnectionDetails đang được sử dụng.

### Bài D — custom HTTP endpoint

1. Tạo một GenericContainer có exposed HTTP port.
2. Tạo **PartnerProperties(baseUrl)** dưới prefix **app.partner**.
3. Dùng DynamicPropertyRegistry cấp base URL theo getHost/getMappedPort.
4. Bind PartnerProperties.
5. Assert baseUrl khớp endpoint động.

**Kết quả mong đợi:** DynamicPropertySource phục vụ custom configuration mà không cần ServiceConnection factory.

### Bài E — Redis với GenericContainer

1. Thêm Redis starter/client dependencies phù hợp cho test.
2. Tạo GenericContainer Redis expose 6379.
3. Gắn **@ServiceConnection(name = "redis")** trên container hoặc @Bean.
4. Assert Redis client chạy được lệnh đơn giản qua container.
5. Bỏ name ở trường hợp @Bean GenericContainer và quan sát sự khác biệt nhận diện factory.

**Kết quả mong đợi:** hiểu cách ServiceConnection factory match theo class/image/name.

### Bài F — container như Spring bean

1. Tạo **@TestConfiguration** có **@Bean @ServiceConnection** trả PostgreSQLContainer.
2. **@Import** vào @SpringBootTest.
3. Không dùng JUnit @Container cho bean này.
4. Query SELECT 1.
5. Tìm hiểu lifecycle theo Spring TestContext caching.

**Kết quả mong đợi:** phân biệt JUnit-managed container với Spring-managed container.

### Bài G — kiểm thử lỗi của test slice

1. Tạo repository JPA với @DataJpaTest.
2. Gắn PostgreSQLContainer và ServiceConnection.
3. Bổ sung **@AutoConfigureTestDatabase(replace = NONE)** khi cần.
4. Chạy query đặc trưng của PostgreSQL.
5. Xác nhận test không bị chuyển sang embedded DB.

**Kết quả mong đợi:** test chạy trên backend thực tế gần với production.

### Bài H — kết hợp hai cơ chế

1. Dùng @ServiceConnection cho PostgreSQL.
2. Dùng @DynamicPropertySource cho một custom HTTP mock URL.
3. Assert cả JDBC query và PartnerProperties.
4. Không dùng registry.add cho các JDBC keys nếu ServiceConnection đã đảm trách.
5. Ghi rõ ranh giới ownership của từng container.

**Kết quả mong đợi:** hai annotation bổ sung nhau trong cùng test integration.

## 31. Checklist khi chọn phương án

Hãy trả lời những câu hỏi sau:

- Dịch vụ của bạn có Spring Boot ConnectionDetails factory không?
- Ứng dụng sử dụng auto-configuration có đọc ConnectionDetails không?
- Bạn cần cấp **spring.datasource.*** hay một **app.custom.*** key?
- Có muốn test chủ động quản lý từng property hay để Boot tự suy ra connection?
- Có nhiều container cùng loại không?
- Container là JUnit static field hay Spring @Bean?
- Nếu @Bean trả GenericContainer, có cần name hint không?
- Dependencies đã có **spring-boot-testcontainers** khi dùng ServiceConnection chưa?
- Nếu dùng @DynamicPropertySource, method có static và Supplier đúng không?
- Đã kiểm tra runtime Docker phù hợp trong CI chưa?
- Đã tránh fixed host port chưa?
- Có test query/IO thực để chứng minh kết nối đúng không?
- Có dùng context caching và lifecycle nhất quán không?
- Có một test slice vô tình tạo embedded database không?
- Có đang dựa vào Environment.getProperty để suy ra kết nối được tạo từ ConnectionDetails không?
- Có đưa credential thật vào test source/log không?
- Có thêm @DirtiesContext chỉ khi cần, tránh tăng thời gian chạy vô ích không?
- Có xem đúng phiên bản Spring Boot khi đọc danh sách factory không?

## 32. Tổng kết

- **@DynamicPropertySource** là API của **Spring Framework TestContext**, giúp thêm các property động vào Spring Environment qua **DynamicPropertyRegistry** và **Supplier**.
- **@ServiceConnection** là tích hợp của **Spring Boot Testcontainers**, tạo bean **ConnectionDetails** từ container để các auto-configuration phù hợp sử dụng.
- Với PostgreSQL JDBC, ServiceConnection có thể cung cấp **JdbcConnectionDetails** và giảm việc khai báo URL, username, password bằng tay.
- **ConnectionDetails ưu tiên hơn connection-related configuration properties** tại những consumer hỗ trợ nó; đây không phải thao tác ghi đè các key Environment.
- **@DynamicPropertySource** linh hoạt cho mọi key, nhất là **app.partner.base-url** hoặc những endpoint của dịch vụ tùy biến.
- **@ServiceConnection** cần module **spring-boot-testcontainers**; không phải mọi container/custom image đều có factory.
- Với **GenericContainer @Bean**, có thể cần **@ServiceConnection(name = "redis")** để Spring Boot nhận diện dịch vụ.
- **@Testcontainers** và **@Container** quản lý JUnit container lifecycle; không phải chức năng của @ServiceConnection.
- Container **@Bean** do Spring Boot quản lý có lifecycle theo test ApplicationContext.
- Hai cơ chế có thể được **kết hợp** trong một test khi mỗi cơ chế phụ trách một loại kết nối.
- Test nên kiểm tra **client thực sự sử dụng container**, không chỉ context starts hoặc một property string trong Environment.
- Context caching, test slices, mapped ports và Docker runtime là những yếu tố quyết định integration test có đáng tin cậy hay không.

## Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Testcontainers, *Service Connections*, *Dynamic Properties*, *Using Spring Beans*: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Spring Boot 3.3 — Spring Boot Testcontainers module và ServiceConnection API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/testcontainers/service/connection/ServiceConnection.html
- Spring Framework 6.1 — DynamicPropertySource API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/context/DynamicPropertySource.html
- Spring Framework — Context Configuration with Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Testcontainers Java — JUnit 5 Quickstart: https://java.testcontainers.org/quickstart/junit_5_quickstart/
- Testcontainers Java — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/

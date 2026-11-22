# @ServiceConnection và ConnectionDetails trong các phiên bản Spring Boot hỗ trợ Testcontainers

## 1. Vấn đề: container chạy ở cổng ngẫu nhiên, ứng dụng kết nối bằng cách nào?

Khi viết integration test cho Spring Boot, ta thường cần một dịch vụ thật chạy tạm thời như PostgreSQL, Redis, Kafka, MongoDB hoặc RabbitMQ. **Testcontainers** tạo Docker container và ánh xạ cổng nội bộ (ví dụ PostgreSQL 5432) ra một **host port có thể thay đổi ở mỗi lần chạy**. Spring Boot lại cần biết chính xác JDBC URL, username, password hoặc host/port để tự cấu hình các client.

Cách cũ là tự đăng ký các giá trị động qua `@DynamicPropertySource`. Từ **Spring Boot 3.1**, dự án có một cách tích hợp trực tiếp hơn: đánh dấu container bằng **`@ServiceConnection`**. Spring Boot dùng các `ContainerConnectionDetailsFactory` phù hợp để tạo **bean `ConnectionDetails`**, rồi auto-configuration tiêu thụ các bean đó thay cho việc phải tự ghép từng property kết nối.

Ví dụ cốt lõi với PostgreSQL:

~~~java
@Testcontainers
@SpringBootTest
class PostgreSqlIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // Có thể @Autowired JdbcTemplate, DataSource...
}
~~~

Đây là **snippet về cơ chế**; bản chạy đầy đủ có imports, Gradle và tests ở phần 6. Với `PostgreSQLContainer`, Boot có thể tạo `JdbcConnectionDetails` chứa URL/credentials thực của container. Như vậy ta không phải viết tay `spring.datasource.url`, `spring.datasource.username` và `spring.datasource.password` từ `postgres.getJdbcUrl()` cho từng test.

**Sau bài học, bạn có thể:**

1. Phân biệt nhiệm vụ của **Docker/Testcontainers**, **`@ServiceConnection`**, **`ConnectionDetails`** và **Spring Boot auto-configuration**.
2. Biết chính xác mức phiên bản nào có `@ServiceConnection`/`ConnectionDetails`, và tại sao không thể chép annotation vào Spring Boot 3.0.
3. Sử dụng **`spring-boot-testcontainers`**, Testcontainers JUnit Jupiter và module container tương ứng trong Gradle.
4. Viết `@SpringBootTest` Java 17 + Spring Boot **3.3.5** kiểm tra PostgreSQL thực, dùng `JdbcConnectionDetails`, `DataSource`, `JdbcTemplate` và schema initialization.
5. Hiểu **connection details thường ưu tiên hơn connection-related properties** của Spring Boot auto-configuration mà chúng phục vụ.
6. Phân biệt nhận diện container theo **typed container subclass** so với **Docker image name**; dùng `@ServiceConnection(name="redis")` với `GenericContainer` khi cần.
7. Dùng `@ServiceConnection(type=...)` khi muốn giới hạn loại connection details được tạo.
8. Phân biệt **JUnit-managed static @Container field**, **Spring-managed @Bean container**, `@ImportTestcontainers` và các ảnh hưởng đến **ApplicationContext cache**.
9. Sử dụng **`@DynamicPropertySource`** làm phương án tương thích hoặc fallback khi không có factory phù hợp.
10. Chẩn đoán lỗi Docker không hoạt động, thiếu starter/module, DataSource bị slice thay bằng embedded database, trùng cấu hình hoặc container đã dừng.
11. Không hard-code mapped host port, không đưa credentials/container test vào môi trường production ngoài chủ đích.
12. Tự thiết kế test cô lập dữ liệu, dọn các side effects và xác minh chính DB engine đang sử dụng.

**Phiên bản ví dụ:** Java 17, Spring Boot **3.3.5**, Spring Framework 6.1, Gradle, JUnit Jupiter và PostgreSQL 16 trong Testcontainers. Mọi code hoàn chỉnh ở mục 6 dùng API/package của **Spring Boot 3.3.x**. Những sản phẩm/phần mềm này còn phát triển; khi nâng lên 3.4/3.5/4.x, phải đọc tài liệu phiên bản đích trước khi sao chép imports hoặc dependency modules.

**Ngữ cảnh cha “Testcontainers”:** Bài tập trung vào *cách đưa thông tin kết nối từ container vào Spring Boot*. Nó không phải hướng dẫn điều hành Docker production, migration database, viết toàn bộ repository JPA hay phát triển service mới. Docker phải có sẵn khi thực sự chạy các integration tests.

## 2. Sơ đồ: ai tạo container, ai tạo thông tin kết nối?

~~~text
JUnit Jupiter                  Spring Boot TestContext
     |                                  |
     | @Testcontainers                  | @SpringBootTest
     | @Container static               | @ServiceConnection discovery
     v                                  v
Testcontainers                ContainerConnectionDetailsFactory
     |                                  |
     | start PostgreSQL container       | nhận diện PostgreSQLContainer
     | map 5432 -> host:randomPort      | tạo JdbcConnectionDetails
     | getJdbcUrl(), credentials        | (và loại khác nếu áp dụng)
     |                                  v
     +------------------------> Spring Boot auto-configuration
                                        |
                                        | DataSourceAutoConfiguration
                                        v
                                DataSource / JdbcTemplate
                                        |
                                        v
                              Kết nối tới PostgreSQL test
~~~

Một chuỗi trách nhiệm cần nhớ:

- **Testcontainers** tạo và quản lý dịch vụ thật trong Docker. `@Container` và `@Testcontainers` của thư viện JUnit Jupiter Testcontainers chịu trách nhiệm vòng đời container khi theo mô hình static field.
- **`@ServiceConnection`** thuộc **Spring Boot**, không thuộc JUnit hoặc Testcontainers. Nó đánh dấu nguồn cung cấp một service connection.
- **`ContainerConnectionDetailsFactory`** xác định có biết tạo connection details cho container này không. Việc nhận diện dựa trên **kiểu container** hoặc **tên image** tùy loại factory.
- **`ConnectionDetails`** là một abstraction chung mô tả cách kết nối đến dịch vụ; các interface cụ thể như `JdbcConnectionDetails`, `RedisConnectionDetails`, `KafkaConnectionDetails`, `MongoConnectionDetails` cung cấp dữ liệu phù hợp cho từng auto-configuration.
- **Spring Boot auto-configuration** dùng connection details khi thiết lập client hoặc pool. Tạo bean ConnectionDetails không có nghĩa Spring Boot tự khởi động tất cả dependency clients: phải có starter/library, auto-configuration và factory hỗ trợ.

Trong Boot 3.3, các package quan trọng:

~~~text
org.springframework.boot.testcontainers.service.connection.ServiceConnection
org.springframework.boot.autoconfigure.service.connection.ConnectionDetails
org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails
org.springframework.boot.autoconfigure.data.redis.RedisConnectionDetails
org.springframework.test.context.DynamicPropertySource
org.springframework.test.context.DynamicPropertyRegistry
org.testcontainers.junit.jupiter.Testcontainers
org.testcontainers.junit.jupiter.Container
org.testcontainers.containers.PostgreSQLContainer
org.testcontainers.containers.GenericContainer
~~~

Không nhầm `org.testcontainers.junit.jupiter.Container` (JUnit lifecycle) với `org.testcontainers.containers.Container` (Testcontainers API/interface), hoặc `@ServiceConnection` với một annotation thuộc package `org.springframework.boot.autoconfigure`.

### 2.1. `ConnectionDetails` không phải Environment property

Một `JdbcConnectionDetails` (Boot 3.3) có các method chính:

~~~java
public interface JdbcConnectionDetails extends ConnectionDetails {
    String getJdbcUrl();
    String getUsername();
    String getPassword();
    // getDriverClassName() và XA data source có default methods.
}
~~~

Đây là **chữ ký API giản lược** để học, không phải source file trong project. Bean `JdbcConnectionDetails` là một đối tượng có methods, **không phải** một property bag tự động ghi đè nội dung trong Spring `Environment`.

Khi DataSource auto-configuration được tích hợp với `JdbcConnectionDetails`, nó lấy URL, user, password từ bean details thay vì phải dựa duy nhất vào `spring.datasource.*`. Các properties vẫn có thể xuất hiện khi `environment.getProperty(...)` được gọi; sự tồn tại của property **không chứng minh** nó là thông tin cuối cùng mà DataSource đã sử dụng.

**Quy tắc ưu tiên:** Với Spring Boot auto-configuration **có hỗ trợ đúng loại `ConnectionDetails`**, connection details thường **được ưu tiên hơn các thuộc tính liên quan đến connection**. Không suy rộng thành “ConnectionDetails ưu tiên mọi property trong JVM”. Một DataSource được bạn tự `new`/customize thủ công và không tiêu thụ `JdbcConnectionDetails` có thể dùng đường kết nối khác.

### 2.2. `@ServiceConnection` không tự phát minh factory cho mọi image

Một annotation `@ServiceConnection` chỉ hữu ích khi Spring Boot có **factory tương thích** cho kiểu container hoặc tên image. Nó không biến mọi `GenericContainer` thành PostgreSQL/Redis/Kafka client được hỗ trợ. Nếu ứng dụng có một service tự viết với giao thức riêng, bạn có thể cần custom connection details/factory hoặc quay lại `@DynamicPropertySource` và cấu hình client thủ công.

## 3. Tương thích phiên bản: đâu là “các phiên bản hỗ trợ”?

| Dòng Spring Boot | `@ServiceConnection` / `ConnectionDetails` | Gợi ý |
|---|---|---|
| **2.x** | Không có API service connection Boot 3.1 | Testcontainers + properties / `@DynamicPropertySource` theo Spring Test version hỗ trợ; không import code Boot 3.x |
| **3.0.x** | Chưa có hai API này | Dùng `@DynamicPropertySource` hoặc cấu hình test JDBC URL; không thêm import `@ServiceConnection` |
| **3.1.x** | **Bắt đầu hỗ trợ** | Thêm `spring-boot-testcontainers`; factories/loại container theo release thực tế |
| **3.2.x** | Có | Có thể dùng service connections; kiểm bảng factory theo 3.2 |
| **3.3.x** | **Có — ví dụ của bài** | Package/API và Gradle bên dưới cho **3.3.5** |
| **3.4.x / 3.5.x** | Tiếp tục hỗ trợ | Kiểm release notes về Testcontainers, factories, @AutoConfigureTestDatabase và lifecycle |
| **4.x** | Khái niệm tiếp tục, nhưng hệ module/package auto-configuration đã thay đổi | Đối chiếu docs/API **4.x** cho imports/dependencies; không sao chép nguyên `JdbcConnectionDetails` Boot 3.3 |

**Mốc chính thức:** `@ServiceConnection`, `ConnectionDetails` và `JdbcConnectionDetails` được đánh dấu **Since: 3.1.0** trong Spring Boot API. Vì vậy bài cố định 3.3.5 để có bộ code tái lập, thay vì trộn annotation với ví dụ 3.0 hoặc thay imports từ Spring Boot 4.

**Điều cần phân biệt:** “Có annotation” không đồng nghĩa “mọi loại container/factory đều hỗ trợ”. Bảng service connections của Boot 3.1 có thể khác 3.3 và 3.5. Ví dụ Kafka, RabbitMQ, MongoDB, Redis, JDBC, Flyway, Liquibase, R2DBC có factories khác nhau; hãy đọc danh sách khớp **trong phiên bản đang dùng**.

**Với dự án cũ:** Hãy ưu tiên một cách test đã được Boot version hỗ trợ. Nếu dự án đang là Boot 3.0 và chưa thể nâng cấp, dùng `@DynamicPropertySource`. Không cố thêm `spring-boot-testcontainers:3.3.5` vào một ứng dụng Boot 3.0 rồi giả định Spring core/auto-configuration sẽ tương thích.

## 4. Các loại container và ConnectionDetails phổ biến

Bảng minh họa theo Spring Boot **3.3.x** (danh sách không phải toàn bộ factories):

| Dịch vụ/container | Đích `ConnectionDetails` | Cách nhận diện thường gặp |
|---|---|---|
| `PostgreSQLContainer` / `JdbcDatabaseContainer` | **JdbcConnectionDetails** | Typed container / JDBC database container |
| PostgreSQL JDBC với Flyway hoặc Liquibase | **FlywayConnectionDetails**, **LiquibaseConnectionDetails** | JdbcDatabaseContainer nếu dependency tương ứng |
| `PostgreSQLContainer` trong app reactive | **R2dbcConnectionDetails** | Typed PostgreSQL container, cần R2DBC dependencies |
| `MongoDBContainer` | **MongoConnectionDetails** | Typed container |
| `KafkaContainer` (hoặc loại tương thích theo version) | **KafkaConnectionDetails** | Typed container |
| `RabbitMQContainer` | **RabbitConnectionDetails** | Typed container |
| `Neo4jContainer` | **Neo4jConnectionDetails** | Typed container |
| `GenericContainer` với image Redis | **RedisConnectionDetails** | Image name `redis` hoặc hint `name="redis"` |
| `ElasticsearchContainer` | **ElasticsearchConnectionDetails** | Typed container |

Khi có `PostgreSQLContainer`, Spring Boot có thể tạo **nhiều loại details** cùng lúc, như JDBC và R2DBC; nếu có Flyway/Liquibase, connection details cho migration cũng có thể được đưa vào quá trình cấu hình. **Không phải mọi details được tạo đều đồng nghĩa mọi client đang chạy**: chỉ các auto-configurations có dependency và conditions phù hợp mới tiêu thụ chúng.

Nếu muốn chỉ tạo JDBC details, có thể dùng thuộc tính `type`:

~~~java
@Container
@ServiceConnection(type = JdbcConnectionDetails.class)
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

Đây là snippet đặt trong một test class. `type` **giới hạn các loại ConnectionDetails factory được phép tạo**, không thay đổi container image, không biến PostgreSQL thành một dịch vụ khác. Trong project chỉ dùng JDBC và không dùng Flyway/R2DBC, chọn `JdbcConnectionDetails` là cách làm rõ phạm vi.

**Cảnh báo khi thêm migration:** Nếu bạn dùng `type=JdbcConnectionDetails.class` trong app có Flyway, bạn đang hạn chế tạo `FlywayConnectionDetails`. Tùy cấu hình, Flyway có thể vẫn hoạt động thông qua cùng DataSource, nhưng không được tuyên bố mọi connection detail dành cho migration đã có. Khi cần chúng, bỏ giới hạn hoặc liệt kê đủ loại, kiểm trên version thực tế.

## 5. Điều kiện vận hành trước khi chạy ví dụ

Muốn chạy integration test Testcontainers, cần:

1. **Java 17** tương thích với Spring Boot 3.3.5.
2. **Gradle** tương thích (hoặc Gradle Wrapper của project).
3. **Docker daemon/container runtime tương thích Testcontainers**, đang chạy và được test process truy cập.
4. Môi trường có khả năng tải image `postgres:16-alpine` hoặc đã pre-pull image trong registry nội bộ.
5. Test runner/JUnit Jupiter nhận được Testcontainers extension.
6. Không có policy CI chặn Docker socket/containers/port mapping/Ryuk (tùy cấu hình môi trường).
7. Dùng **database riêng cho tests**, không dùng mật khẩu hoặc địa chỉ PostgreSQL production.

**Cổng container không cố định:** PostgreSQL trong container lắng nghe 5432, nhưng host port do Testcontainers map có thể khác mỗi lần. Không viết `jdbc:postgresql://localhost:5432/mydb` trong test rồi hy vọng trỏ đúng; lấy `postgres.getJdbcUrl()` hoặc để `@ServiceConnection` tạo details.

**CI:** Runner phải thực sự có Docker được hỗ trợ; việc chỉ thêm dependency Testcontainers không tự tạo daemon. Nếu CI không cấp quyền dùng Docker, test không chạy được, dù source Java biên dịch chính xác. Hãy chọn runner có container runtime phù hợp hoặc dùng integration-test stage riêng; đừng dùng H2 để giả vờ đã chạy PostgreSQL integration test.

## 6. Dự án chạy được: Spring Boot 3.3.5 + PostgreSQL Testcontainers

Project này dùng **một class integration test duy nhất** để vòng đời static `@Container` và Spring test context rõ ràng. Ta cố tình khai báo `spring.datasource.*` với giá trị **không hợp lệ** trong test annotation để chứng minh `JdbcConnectionDetails` được auto-configuration ưu tiên. Test khẳng định `Environment` vẫn giữ property sai trong khi DataSource thực sự kết nối container. Chỉ áp dụng cấu hình này cho bài thực hành, **không áp dụng dummy credentials lên cấu hình production**.

### 6.1. Cấu trúc file

~~~text
settings.gradle
build.gradle
src/main/java/demo/serviceconnection/ServiceConnectionApplication.java
src/test/resources/schema.sql
src/test/java/demo/serviceconnection/PostgresServiceConnectionTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'boot-service-connection-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Vì sao có từng dependency?**

- `spring-boot-starter-jdbc`: đưa `JdbcTemplate`, `DataSourceAutoConfiguration`, transaction manager và JDBC support vào ứng dụng.
- `org.postgresql:postgresql`: JDBC driver thật cho PostgreSQL; đặt runtimeOnly vì code production không trực tiếp import class driver.
- `spring-boot-starter-test`: JUnit Jupiter, Spring Test, assertions và Spring Boot testing.
- **`spring-boot-testcontainers`**: cơ chế Spring Boot tạo `ConnectionDetails` từ Testcontainers qua `@ServiceConnection`.
- **`org.testcontainers:junit-jupiter`**: extension nhận `@Testcontainers`, `@Container` và quản lý start/stop container.
- **`org.testcontainers:postgresql`**: typed `PostgreSQLContainer`.
- Spring Boot BOM quản lý phiên bản tương thích cho Testcontainers, PostgreSQL driver và Spring libraries; không tự ghép các version không cùng BOM.

Không cần khai báo thêm `spring.datasource.url` thực trỏ host port Testcontainers; chính `@ServiceConnection` đảm nhiệm. Không dùng Flyway/Liquibase trong ví dụ để tránh thêm một cơ chế schema initialization không liên quan.

### 6.2. Application class

**src/main/java/demo/serviceconnection/ServiceConnectionApplication.java**

~~~java
package demo.serviceconnection;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServiceConnectionApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServiceConnectionApplication.class, args);
    }
}
~~~

Không có HTTP server vì project không khai báo web starter. `@SpringBootTest` vẫn khởi tạo application context đầy đủ với JDBC DataSource. Spring Boot sẽ tìm main application trong package hierarchy của test `demo.serviceconnection`.

### 6.3. Schema SQL của integration test

**src/test/resources/schema.sql**

~~~sql
CREATE TABLE inventory_item (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    quantity INTEGER NOT NULL
);
~~~

**Vì sao schema.sql ở test resources?** Với PostgreSQL container, database này **không phải embedded database** theo cơ chế SQL initialization mặc định của Spring Boot. Vì vậy ở test class ta đặt **`spring.sql.init.mode=always`** để Boot chạy schema.sql khi DataSource/ApplicationContext khởi tạo. Nếu bỏ `always`, Boot có thể không chạy file trên PostgreSQL và test báo lỗi “relation inventory_item does not exist”.

Trong một dự án production sử dụng Flyway/Liquibase, hãy dùng migration thật để tạo schema và chỉ dùng `@Sql`/fixture cho data; không bật đồng thời nhiều cơ chế tạo cùng bảng. Bài này chủ động dùng schema.sql để có ví dụ tối thiểu và không cần migration library.

### 6.4. Test class hoàn chỉnh: 5 JUnit tests và hook kiểm rollback

**src/test/java/demo/serviceconnection/PostgresServiceConnectionTest.java**

~~~java
package demo.serviceconnection;

import java.sql.Connection;
import java.sql.SQLException;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.transaction.AfterTransaction;
import org.springframework.transaction.annotation.Transactional;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
@SpringBootTest(properties = {
        "spring.sql.init.mode=always",
        "spring.datasource.url=jdbc:postgresql://127.0.0.1:1/unused",
        "spring.datasource.username=unused",
        "spring.datasource.password=unused"
})
class PostgresServiceConnectionTest {

    @Container
    @ServiceConnection(type = JdbcConnectionDetails.class)
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("inventory_test")
                    .withUsername("test")
                    .withPassword("test");

    @Autowired
    JdbcConnectionDetails details;

    @Autowired
    DataSource dataSource;

    @Autowired
    JdbcTemplate jdbc;

    @Autowired
    Environment environment;

    private Long insertedId;

    private long countItem(long id) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM inventory_item WHERE id = ?",
                Long.class, id);
    }

    @Test
    void detailsDescribeTheRunningPostgresContainer() {
        assertTrue(postgres.isRunning());
        assertEquals(postgres.getJdbcUrl(), details.getJdbcUrl());
        assertEquals(postgres.getUsername(), details.getUsername());
        assertEquals(postgres.getPassword(), details.getPassword());
    }

    @Test
    void autoConfiguredDataSourceReallyConnectsToPostgres()
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());

            assertTrue(connection.getMetaData()
                    .getURL().startsWith("jdbc:postgresql:"));
        }
    }

    @Test
    void connectionDetailsOverrideExplicitFallbackProperties() {
        String fallback = environment.getProperty(
                "spring.datasource.url");

        assertEquals(
                "jdbc:postgresql://127.0.0.1:1/unused",
                fallback);

        assertNotEquals(fallback, details.getJdbcUrl());

        Integer answer = jdbc.queryForObject(
                "SELECT 2 + 3", Integer.class);

        assertEquals(Integer.valueOf(5), answer);
    }

    @Test
    void springBootInitializedSchemaOnContainerDatabase() {
        Long tableCount = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'inventory_item'
                """,
                Long.class);

        assertEquals(Long.valueOf(1L), tableCount);
        assertEquals(0L, countItem(1001L));
    }

    @Test
    @Transactional
    void writesUsingTheRealConnectionCanBeRolledBack() {
        insertedId = 1001L;

        int rows = jdbc.update(
                """
                INSERT INTO inventory_item(id, sku, quantity)
                VALUES (?, ?, ?)
                """,
                insertedId, "PEN-001", 7);

        assertEquals(1, rows);
        assertEquals(1L, countItem(insertedId));

        Integer quantity = jdbc.queryForObject(
                "SELECT quantity FROM inventory_item WHERE id = ?",
                Integer.class, insertedId);

        assertEquals(Integer.valueOf(7), quantity);
    }

    @AfterTransaction
    void verifyRollbackAfterTransactionalTest() {
        if (insertedId == null) {
            return;
        }

        // Hook chỉ chạy sau test-managed transaction.
        assertEquals(0L, countItem(insertedId));
    }
}
~~~

**Giải thích cách chạy/QA từng test:**

1. **detailsDescribeTheRunningPostgresContainer:** xác minh container đang chạy và `JdbcConnectionDetails` cung cấp đúng JDBC URL/username/password mà typed PostgreSQLContainer thực sự sử dụng. Nếu thiếu factory phù hợp hoặc module `spring-boot-testcontainers`, injection/cấu hình có thể thất bại.
2. **autoConfiguredDataSourceReallyConnectsToPostgres:** mở JDBC Connection từ `DataSource` mà Spring tạo và đọc DatabaseMetaData. Kết quả vendor phải là **PostgreSQL** và JDBC URL bắt đầu `jdbc:postgresql:`; đây là bằng chứng thực tế không dùng H2.
3. **connectionDetailsOverrideExplicitFallbackProperties:** chứng minh `Environment` vẫn có property URL cố ý không hợp lệ, nhưng `details.getJdbcUrl()` không bằng property đó và query `SELECT 2 + 3` vẫn trả **5** trên PostgreSQL container. Như vậy property không phải nguồn kết nối cuối cùng được DataSource auto-config sử dụng.
4. **springBootInitializedSchemaOnContainerDatabase:** kiểm bảng `public.inventory_item` có tồn tại. Đây là bằng chứng `spring.sql.init.mode=always` đã chạy `schema.sql` trên PostgreSQL thực.
5. **writesUsingTheRealConnectionCanBeRolledBack:** ghi một hàng trong test-managed transaction của Spring rồi đọc quantity=7. `@AfterTransaction` chạy **sau khi test kết thúc**, kiểm id 1001 không còn do rollback mặc định.

**Tổng: 5 phương thức `@Test`**, không có `@Disabled` trong file hoàn chỉnh. `@AfterTransaction` là **hook** và không được tính thành một test thứ sáu. H5 dùng `@Transactional` vì `@SpringBootTest` **không mặc định transactional** như `@JdbcTest`. Các test còn lại chỉ SELECT để không tạo dữ liệu committed. Dữ liệu test được giữ cô lập và việc rollback được kiểm đúng **sau transaction**, không chỉ khi transaction đang mở.

**Tại sao property URL cố ý sai vẫn an toàn trong ví dụ?** Nó chỉ tồn tại trong annotation của test, được dùng để chứng minh precedence, không được copy vào `application.properties` production. Nếu Boot không tạo được service connection như kỳ vọng, test sẽ **fail nhanh** thay vì âm thầm kết nối một database bên ngoài. Không thay dummy URL bằng thông tin production.

### 6.5. Lệnh chạy

Nếu project có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Trong Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Nếu chỉ chép files trong bài mà **chưa có Wrapper scripts/JAR**, `./gradlew` chưa tồn tại: dùng Gradle tương thích để tạo wrapper hoặc chạy `gradle test`.

Chạy riêng class:

~~~bash
./gradlew test --tests demo.serviceconnection.PostgresServiceConnectionTest
~~~

**Điều kiện:** Docker daemon khả dụng; image `postgres:16-alpine` tải được; đủ quyền tạo container và mạng. Testcontainers có thể khởi động container helper/Ryuk theo môi trường. Thời gian chờ tải image lần đầu phụ thuộc network; không giả định một số giây cố định.

**Kết quả kỳ vọng từ code:**

| Check | Expected |
|---|---|
| Container PostgreSQL | isRunning = true |
| JdbcConnectionDetails | URL/user/password trùng container |
| DataSource JDBC metadata | Database product = PostgreSQL |
| Config property cố ý sai | Vẫn hiện trong Environment |
| Query `SELECT 2 + 3` | **5** |
| Bảng `public.inventory_item` | Có **1** table metadata row |
| Insert test | **1** row thêm, quantity **7** |
| @AfterTransaction | Row id 1001 đếm được **0** |
| JUnit Jupiter methods | **5**, dự kiến PASS nếu Docker/env đáp ứng |

Đây là **expected behavior theo API và code mẫu**, không phải khẳng định đã chạy Docker/Gradle trong môi trường của người đọc. Báo cáo test Gradle thường nằm ở `build/reports/tests/test/index.html`.

### 6.6. Vì sao không hard-code port hoặc tự khai báo @DynamicPropertySource trong test này?

`PostgreSQLContainer` đã biết mapped JDBC URL thực. `@ServiceConnection` đưa connection details vào auto-configuration; nếu cùng test lại khai báo:

~~~java
@DynamicPropertySource
static void dataSourceProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

đây là snippet **phương án khác**, không phải phần cần thêm vào file đầy đủ phía trên. Nó làm test dư hai nguồn cấu hình và che việc bạn có thật sự kiểm chứng service connection hay không. Với dự án dùng Boot 3.3.5 và typed container được hỗ trợ, hãy chọn **một cách** làm chính. Với service chưa được supported factory nhận diện hoặc Boot trước 3.1, xem fallback mục 10.

## 7. Có thể dùng @ServiceConnection trong @JdbcTest không?

Có, nhưng cần hiểu **test database replacement** của JDBC slice. `@JdbcTest` tập trung vào JDBC layer và Spring Boot có `TestDatabaseAutoConfiguration` thường thay DataSource bằng một embedded database nếu classpath có H2. Để cố định rằng JDBC slice phải dùng PostgreSQL Testcontainers, với Spring Boot 3.3 hãy khai báo:

~~~java
@JdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class JdbcPostgresSliceTest {

    @Container
    @ServiceConnection(type = JdbcConnectionDetails.class)
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Đây là snippet để giải thích **annotation combination**; imports cần thêm:
- `org.springframework.boot.test.autoconfigure.jdbc.JdbcTest`
- `org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase`
- `org.springframework.boot.autoconfigure.jdbc.JdbcConnectionDetails`
- `org.springframework.boot.testcontainers.service.connection.ServiceConnection`
- `org.testcontainers.containers.PostgreSQLContainer`
- `org.testcontainers.junit.jupiter.Container`
- `org.testcontainers.junit.jupiter.Testcontainers`

Nếu bỏ `replace=NONE`, JDBC slice có thể dùng **H2 thay vì PostgreSQL** dù container vẫn chạy, làm test “xanh” với SQL dialect khác mục tiêu. Trong Spring Boot 3.4+, chính sách replacement có những cập nhật liên quan test database detection; không áp dụng suy đoán từ 3.3 sang 3.4 mà không đọc release docs.

**Với @DataJpaTest** cũng cần suy nghĩ về embedded database replacement, `EntityManager`, Flyway/Liquibase và schema migrations. Nếu mục tiêu là JPA, nên dùng type-specific slice cùng cấu hình PostgreSQL phù hợp; không sao chép `@JdbcTest` rồi kỳ vọng nó tự scan entities/repositories JPA.

**Lưu ý @JdbcTest không giống @SpringBootTest:** Nó không tự nạp mọi `@Service/@Repository`, không chạy toàn app và mặc định transactional/rollback; phải dùng `@Import` cho những collaborator cần có. Vì vậy bài mẫu runnable dùng @SpringBootTest để minh họa service connection độc lập với slice; snippet này để người học chuyển kiến thức đúng cách.

## 8. Typed container và GenericContainer: quy tắc nhận diện

### 8.1. Typed container: nhận diện theo class

Các container chuyên dụng như `PostgreSQLContainer`, `MongoDBContainer`, `RabbitMQContainer` cho Spring Boot biết dịch vụ cần kết nối thuộc loại nào. Factory có thể match theo container subclass mà không cần đọc image name, nên ví dụ PostgreSQL thường chỉ cần:

~~~java
@ServiceConnection
static PostgreSQLContainer<?> db =
        new PostgreSQLContainer<>("postgres:16-alpine");
~~~

Một `PostgreSQLContainer` phù hợp có method `getJdbcUrl`, `getUsername`, `getPassword`. Đây là lý do JDBC factory tạo được details. Không phải cứ image có chữ “postgres” nhưng được khai báo dưới `GenericContainer` là tự có đủ JDBC logic của `PostgreSQLContainer`. Factory match type JDBC database container không tự biến GenericContainer thành JdbcDatabaseContainer.

### 8.2. GenericContainer: có thể cần `name` cho image-based factory

Ví dụ Redis với một `@Bean` factory trả **GenericContainer<?>**:

~~~java
package demo.redis;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.GenericContainer;

@TestConfiguration(proxyBeanMethods = false)
public class RedisContainerTestConfig {

    @Bean
    @ServiceConnection(name = "redis")
    public GenericContainer<?> redisContainer() {
        return new GenericContainer<>("redis:7-alpine")
                .withExposedPorts(6379);
    }
}
~~~

Đây là **một file Java hoàn chỉnh nhưng là ví dụ phụ cho project Redis khác**. Để chạy, project đó cần `spring-boot-starter-data-redis`, `spring-boot-testcontainers`, Testcontainers và import `RedisContainerTestConfig` vào test/app context; **không** thêm file này vào project PostgreSQL tối thiểu ở mục 6 rồi mong có bean Redis client. Với bean Spring-managed, Boot/Testcontainers quản lý lifecycle phù hợp theo test context.

**Vì sao phải có name="redis"?** Khi `@ServiceConnection` nằm trên một method `@Bean`, Spring Boot **không gọi method sớm chỉ để đọc Docker image** (điều đó gây eager initialization). Nó có thể đọc **return type**; `GenericContainer<?>` không cho biết đó là Redis. Vì vậy `name="redis"` là hint để chọn factory match theo tên Redis.

Trái lại, với một **static field** container đã có instance, Boot có thể đọc image repository name. Tuy vậy, một `name` tường minh là hữu ích khi image được mirror/đổi tên. Ví dụ image từ private registry không có repository name `redis` thì:

~~~java
@ServiceConnection(name = "redis")
static GenericContainer<?> redis =
        new GenericContainer<>(
                "registry.example.internal/mirror/my-redis:7")
                .withExposedPorts(6379);
~~~

Đây là snippet về cấu hình, **không** bảo đảm image tùy ý thực sự chạy Redis. Muốn client kết nối được, image đó vẫn phải chạy đúng giao thức Redis và expose port đúng.

**Không áp dụng `name="postgres"` như một cách thay thế cho typed PostgreSQLContainer trong mọi tình huống.** JDBC connection factory trên Boot 3.3 nhận diện `JdbcDatabaseContainer` và cần các method JDBC tương ứng. Một GenericContainer mang tên image Postgres không tự có getJdbcUrl/username/password và không bảo đảm sinh `JdbcConnectionDetails` như typed container. Hãy chọn đúng container subclass.

### 8.3. Custom image cho typed PostgreSQLContainer

Trong môi trường doanh nghiệp, Docker image có thể được mirror. Testcontainers typed PostgreSQLContainer tự kiểm tra tính tương thích image với PostgreSQL. Nếu image là bản mirror hợp lệ nhưng tên repository khác `postgres`, có thể cần `DockerImageName.asCompatibleSubstituteFor("postgres")` theo API Testcontainers:

~~~java
DockerImageName postgresMirror =
        DockerImageName.parse(
                "registry.example.internal/mirror/postgres-custom:16")
                .asCompatibleSubstituteFor("postgres");

PostgreSQLContainer<?> pg =
        new PostgreSQLContainer<>(postgresMirror);
~~~

Đây là snippet, cần import `org.testcontainers.utility.DockerImageName` và `org.testcontainers.containers.PostgreSQLContainer`. Chỉ đánh dấu compatible khi image thật sự tương thích Postgres; không dùng để qua mặt validation với image khác giao thức. Sau khi có typed container, Boot vẫn có thể cung cấp JDBC details theo **container type**.

## 9. Static @Container, Spring bean và @ImportTestcontainers

### 9.1. Static field do JUnit extension quản lý

~~~java
@Testcontainers
class ExampleTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Với mô hình này, `@Testcontainers` extension **start/stop container theo vòng đời JUnit class**. Test class chạy xong container có thể dừng, trong khi **Spring TestContext ApplicationContext cache** còn tồn tại và có thể được tái sử dụng ở test class khác. Nếu context/client trong cache vẫn giữ kết nối tới container cũ đã dừng, class sau có thể lỗi ngẫu nhiên.

**Giải pháp tùy mục tiêu:**
- Khi chỉ có một integration test class như ví dụ chính, static field đơn giản và dễ hiểu.
- Khi nhiều class chia sẻ cùng service connection/context, dùng **Spring-managed container beans** hoặc **@ImportTestcontainers** cùng cấu hình lifecycle/test context thích hợp, thay vì mặc định static JUnit container và context cache có cùng vòng đời.
- Nếu cần độc lập tuyệt đối, mỗi suite/class có container/database riêng; quản lý chi phí startup và cleanup rõ ràng.
- Không vội dùng @DirtiesContext cho tất cả tests chỉ để khắc phục một sai lệch lifecycle mà chưa hiểu nguyên nhân.

### 9.2. @TestConfiguration và @Bean container

Spring Boot 3.3 có thể quản lý container được khai báo như một bean trong test configuration. Ví dụ PostgreSQL typed container:

~~~java
package demo.serviceconnection;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgreSqlContainerConfig {

    @Bean
    @ServiceConnection
    public PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
~~~

Đây là **một file cấu hình thay thế**, không nằm trong project runnable ở phần 6. Có thể import vào một test:

~~~java
@SpringBootTest
@Import(PostgreSqlContainerConfig.class)
class ImportContainerConfigTest {
    // Spring quản lý vòng đời của PostgreSQLContainer bean.
}
~~~

Snippet thứ hai cần imports Spring Boot/Spring Context tương ứng. Đối với **@Bean container**, Testcontainers/Spring Boot quản lý start/stop cùng **ApplicationContext lifecycle**, không cần thêm `@Container`/`@Testcontainers` cho bean ấy. Nếu đã chuyển sang bean-managed container, không đồng thời để JUnit extension cố start/stop cùng instance như một static field.

**Điểm quan trọng về factory matching:** Vì `@Bean` method chưa được gọi lúc Boot xét service connection, Spring suy ra loại details từ **return type**. Với `PostgreSQLContainer<?>`, điều đó đủ để match JDBC; với `GenericContainer<?>`, phải có name hint nếu factory match theo image/name.

### 9.3. @ImportTestcontainers cho khai báo containers dùng lại

`@ImportTestcontainers` hỗ trợ import container declarations từ một class cấu hình/test riêng, giúp làm việc với lifecycle và Spring TestContext cache phù hợp hơn trong các trường hợp chia sẻ. Ví dụ ý tưởng:

~~~java
@ImportTestcontainers(SharedPostgresContainers.class)
@SpringBootTest
class CustomerDatabaseTest {
    // Reuse container declarations trong shared config.
}
~~~

Đây là snippet kiến trúc, **không phải source chạy độc lập**: SharedPostgresContainers phải được định nghĩa bằng container fields phù hợp, và cần import annotation `org.springframework.boot.testcontainers.context.ImportTestcontainers` theo phiên bản Boot. Đọc tài liệu 3.3 cho lifecycle/field declarations khi áp dụng trong suite lớn.

**Phân biệt:**
- `@Import` Spring bean configuration: đưa một `@TestConfiguration` với `@Bean` container vào context.
- `@ImportTestcontainers`: đưa container declarations vào Spring TestContext theo hỗ trợ Boot/Testcontainers.
- `@Testcontainers/@Container`: JUnit Jupiter extension quản lý static/instance Testcontainers fields.
- Cả ba có thể hữu ích trong dự án nhưng không nên áp dụng trùng lặp lên cùng một container mà không hiểu ai sở hữu vòng đời.

## 10. Phương án cũ và fallback: @DynamicPropertySource

`@DynamicPropertySource` thuộc Spring Test, ra đời trước Spring Boot 3.1. Nó không cần Spring Boot hiểu service connection factory; thay vào đó bạn đưa vào `DynamicPropertyRegistry` các **supplier** trả property giá trị động của container.

Ví dụ thay thế cho test PostgreSQL:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
@SpringBootTest
class LegacyPostgresPropertiesTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.datasource.url",
                postgres::getJdbcUrl);
        registry.add(
                "spring.datasource.username",
                postgres::getUsername);
        registry.add(
                "spring.datasource.password",
                postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void runsAgainstPostgresWithDynamicProperties() {
        assertEquals(
                Integer.valueOf(5),
                jdbc.queryForObject(
                        "SELECT 2 + 3", Integer.class));
    }
}
~~~

Đây là **file class ví dụ phụ** cho dự án có starter-jdbc, PostgreSQL driver, Testcontainers postgres và Testcontainers JUnit dependency; không phải một phần bắt buộc của project 5 tests phía trên. `@DynamicPropertySource` method phải `static`, nhận `DynamicPropertyRegistry`. Các suppliers được đánh giá theo nhu cầu; không chèn host port cố định vào property string.

**Khi nào ưu tiên phương án nào?**

| Tình huống | Ưu tiên | Vì sao |
|---|---|---|
| Boot **3.1+**, typed container được factory nhận diện, auto-config có ConnectionDetails | **@ServiceConnection** | Ít boilerplate, tích hợp trực tiếp auto-configuration |
| Boot **3.0 trở xuống** | **@DynamicPropertySource** | Chưa có @ServiceConnection |
| Container/service chưa có factory hoặc client tự cấu hình | **@DynamicPropertySource** / custom bean | Phải cung cấp property hoặc client config thủ công |
| Cần đăng ký thêm non-connection properties động | Có thể dùng @DynamicPropertySource bên cạnh service connection cho **properties khác**, cẩn thận tránh trùng connection settings | Service connection không cung cấp mọi custom setting |
| Nhiều clients/containers khác nhau | Cấu hình từng loại ConnectionDetails/registry rõ ràng | Tránh trỏ hai clients vào nhầm service |

**Không cần trộn cả hai cách cho cùng một URL JDBC** nếu đang cố test `@ServiceConnection`. Nếu cả hai cùng có, service connection của auto-configuration được hỗ trợ thường ưu tiên hơn connection properties, và code trở nên khó xác minh nguồn cấu hình.

Một lựa chọn Testcontainers cũ khác là **JDBC URL `jdbc:tc:postgresql:...`** do Testcontainers JDBC driver cung cấp, nhưng nó có lifecycle và yêu cầu dependency khác. Nó không phải là `@ServiceConnection` và không nên lẫn vào ví dụ khi đang học Boot service connection.

## 11. Tự cung cấp ConnectionDetails khi không dùng container factory

`ConnectionDetails` là abstraction Spring Boot **auto-configuration tiêu thụ**, không bắt buộc chỉ được tạo từ Testcontainers. Về nguyên tắc, bạn có thể tự khai báo một bean triển khai `JdbcConnectionDetails` nếu ứng dụng có một cơ chế cung cấp JDBC endpoint khác.

Snippet minh họa trong test configuration:

~~~java
@Bean
JdbcConnectionDetails jdbcConnectionDetails() {
    return new JdbcConnectionDetails() {
        @Override
        public String getJdbcUrl() {
            return "jdbc:postgresql://127.0.0.1:5432/testdb";
        }

        @Override
        public String getUsername() {
            return "local_test";
        }

        @Override
        public String getPassword() {
            return "local_test";
        }
    };
}
~~~

Đây chỉ là **snippet mô tả interface**, không phải file runnable và **không** dùng trong project chính. Nó giả định có PostgreSQL local thực sự chạy ở endpoint được ghi. Trong hệ thống thật không hard-code credentials vào source; dùng secret management/config phù hợp. Nếu tự tạo ConnectionDetails mà không đúng interface khách hàng của auto-configuration (ví dụ trả RedisConnectionDetails cho JDBC client), nó sẽ không phục vụ mục tiêu.

**ConnectionDetails khác PropertySource:** Một DataSource tự viết trong `@Configuration` có thể bỏ qua bean này hoàn toàn, còn Spring Boot `DataSourceAutoConfiguration` biết dùng `JdbcConnectionDetails`. Khi debug “tại sao connection details không có tác dụng”, hãy kiểm xem ứng dụng đang dùng **auto-configured client** hay một client/data source do lập trình viên khởi tạo và bind props thủ công.

**Nhiều beans cùng loại:** Nếu hai containers cùng cung cấp `JdbcConnectionDetails` và một DataSource auto-configuration chỉ mong một bean, context có thể báo ambiguous dependency hoặc chọn sai theo điều kiện. Tách application contexts, khai báo rõ bean qualification hoặc thiết kế nhiều DataSources/clients có chủ đích; không đánh dấu tùy tiện mọi container thành service connection.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| IDE báo không tồn tại `@ServiceConnection` | Boot <3.1 hoặc thiếu `spring-boot-testcontainers` | Nâng Boot tương thích, thêm test dependency; nếu không thể nâng dùng @DynamicPropertySource |
| Không autowire được `JdbcConnectionDetails` | Không có compatible factory/container source hoặc cấu hình test không nhận @ServiceConnection | Kiểm typed container, annotation, module, context |
| PostgreSQL container chạy nhưng app dùng H2 | `@JdbcTest`/`@DataJpaTest` thay DataSource | `@AutoConfigureTestDatabase(replace=NONE)` với Boot 3.3 |
| Container không start | Docker daemon unavailable, image không tải được, permission/network | Kiểm Docker engine, registry, Testcontainers logs |
| DataSource cố kết nối localhost:5432 | Service connection không tạo được hoặc DataSource do bạn tự cấu hình | Kiểm ConnectionDetails bean và DataSource metadata |
| Runtime port thay đổi | Host port được map động | Không hard-code port; dùng container getJdbcUrl/service connection |
| GenericContainer Redis không được nhận diện | @Bean trả GenericContainer không có hint | `@ServiceConnection(name="redis")`, expose 6379, Redis starter |
| Custom mirrored image không được typed container chấp nhận | Image compatibility validation | `DockerImageName.asCompatibleSubstituteFor` chỉ cho image thực sự tương thích |
| Có details nhưng client vẫn không chạy | Thiếu starter/client hoặc auto-configuration không tiêu thụ details | Thêm đúng dependencies, kiểm auto-config conditions |
| `spring.datasource.url` vẫn là giá trị cũ trong Environment | ConnectionDetails không sửa property | So actual DataSource/JDBC metadata, không suy từ Environment |
| Query thấy “relation ... does not exist” | `schema.sql` không chạy với non-embedded Postgres | `spring.sql.init.mode=always` hoặc Flyway/Liquibase |
| Test pass trên H2 nhưng fail trên PostgreSQL | SQL dialect/driver khác | Bảo đảm test dùng đúng vendor, JDBC metadata |
| `@Container` bị stop khi context còn cache | JUnit lifecycle khác Spring context lifecycle | Spring-managed bean/@ImportTestcontainers, kiểm context sharing |
| Flyway tự trỏ sai DB | `type` filter chỉ tạo JDBC details, migration configs độc lập | Cho phép Flyway details hoặc dùng chung DataSource đúng |
| Hai PostgreSQL containers cung cấp hai JdbcConnectionDetails | Multiple candidates không có lựa chọn rõ | Tách contexts, qualifiers, DataSource configs |
| Test phụ thuộc thứ tự, DB còn data | Không rollback/cleanup hoặc shared persistent container | @Transactional test, fixtures riêng, teardown |
| CI không có Docker socket | Môi trường runner không có Testcontainers runtime | Dùng runner hỗ trợ Docker, tách integration stage |
| Testcontainers reuse làm data cũ tồn tại | Container tái sử dụng không dọn DB | Isolation/schema reset; không mặc định bật reuse |
| Có service connection nhưng URL tự cấu hình không đổi | Client custom không sử dụng ConnectionDetails | Wire client theo details hoặc dùng properties tương ứng |
| Boot 4 code không compile với import Boot 3.3 | Packages/modules reorganized | Đối chiếu Java API docs của đúng Boot 4.x |

### 12.1. Checklist debug có thứ tự

1. Xác định đúng **Spring Boot version**. Có phải 3.1+ không?
2. Xác định đã có `spring-boot-testcontainers`, `org.testcontainers:junit-jupiter`, module service-specific, starter client và JDBC driver khi dùng SQL.
3. Xem test có **`@Testcontainers` + static `@Container`** hay container bean quản lý bởi Spring không; tránh ownership chồng chéo.
4. Kiểm Docker daemon có chạy và image được tải không.
5. Xem container có **typed class** đúng và annotation `@ServiceConnection` đúng package không.
6. Nếu là `GenericContainer`, xem factory match image hay cần `name` tường minh.
7. Nếu dùng type filter, kiểm `JdbcConnectionDetails`/các loại khác có bị loại không.
8. Dùng `@Autowired JdbcConnectionDetails` hoặc connection details tương ứng để xác nhận bean.
9. Mở thật `DataSource.getConnection()`; xem `DatabaseMetaData.getDatabaseProductName()` và JDBC URL.
10. Nếu test slice, kiểm `@AutoConfigureTestDatabase(replace=NONE)` ở dòng Boot áp dụng.
11. Nếu schema trống, kiểm SQL init/migrations, `spring.sql.init.mode` và SQL errors.
12. Kiểm Spring TestContext caching và JUnit container lifecycle nếu chỉ fail khi chạy cả suite.
13. Không in password/full credentials ra CI logs; chỉ kiểm chúng bằng assertions trong test.
14. Nếu dùng custom client, kiểm code có thật sự consume ConnectionDetails không.
15. Nếu upgrade Boot, đọc changes của auto-config package/factory và chạy lại integration tests.

## 13. Thiết kế tests có thể tin cậy trong CI

**Một số nguyên tắc:**

- **Database test disposable:** `inventory_test` trong container riêng, không dùng production database hoặc tài khoản nhạy cảm.
- **Không hard-code mapped port:** hệ thống CI có thể đang chạy dịch vụ khác tại 5432; Testcontainers chọn host port phù hợp.
- **Không lấy Docker image mutable tag không kiểm soát:** ví dụ dùng `postgres:16-alpine` để dễ học; với CI cần reproducibility cao, pin image version/digest thích hợp và cập nhật định kỳ theo policy bảo mật.
- **Đảm bảo cleanup:** dùng `@Transactional` cho các test JDBC chạy trong cùng test thread khi rollback phù hợp, hoặc `@Sql`/fixture reset/Testcontainers database isolation nếu code chạy server thread khác.
- **Không đánh đồng rollback của JUnit và HTTP server writes:** @SpringBootTest(RANDOM_PORT) có server request ở thread khác, transaction test client không tự rollback dữ liệu do server commit.
- **Không lạm dụng `@DirtiesContext`:** context cache giúp suite nhanh; chỉ làm bẩn context khi thật sự thay đổi singleton beans/config cần reset.
- **Không bật `withReuse(true)` vô điều kiện:** reuse hỗ trợ phát triển nhanh hơn nhưng có thể làm dữ liệu còn qua lần chạy; hiểu Testcontainers reuse policy và cách reset DB.
- **Không vô hiệu hóa Ryuk hay kiểm soát Docker để “sửa” lỗi mà không hiểu runtime:** dùng cấu hình được tổ chức cho phép, tránh để rò resources.
- **Không giả định mọi test cần cùng container:** Nếu một slice chỉ kiểm Java logic không chạm PostgreSQL, unit test hoặc H2 test có thể đủ; chỉ dùng Testcontainers khi driver/dialect/transaction semantics thật là mục tiêu.
- **Không gắn preemptive timeout vào transaction test có DML rồi trông rollback:** test-managed transaction dựa trên thread, callback preemptive có thể chạy khác thread và commit độc lập.

### 13.1. Một chiến lược CI thực tế

~~~text
PR: unit tests (không Docker)
    |
    +-- slice tests chỉ dùng embedded H2 nếu phù hợp
    |
    +-- integration tests PostgreSQL Testcontainers
          Docker-capable runner
          -> pull pinned PostgreSQL image
          -> start container
          -> Boot @ServiceConnection
          -> run @SpringBootTest / @DataJpaTest
          -> verify schema/behavior/rollback
          -> stop container + cleanup
~~~

Việc tách stages không phải bắt buộc cho một project nhỏ, nhưng giúp dễ phân biệt lỗi **Docker runtime** với lỗi **mapping/application**. Một lỗi “Could not find a valid Docker environment” không thể được chữa bằng cách đổi `@ServiceConnection` thành `@DynamicPropertySource`; cả hai cách đều cần container chạy trước.

## 14. Câu hỏi tự luyện

1. **Version:** Tại sao `@ServiceConnection` không compile trên Spring Boot 3.0, nhưng `@DynamicPropertySource` có thể làm cùng nhiệm vụ đăng ký URL?
2. **Dependency:** Khi thêm Testcontainers PostgreSQL nhưng quên `spring-boot-testcontainers`, annotation nào bị thiếu và hạ tầng nào không tạo details?
3. **Precedence:** Trong project có `spring.datasource.url=jdbc:postgresql://localhost:1/unused` nhưng test vẫn query được DB container, giải thích khác biệt giữa Environment property và JdbcConnectionDetails.
4. **Typed container:** Tại sao `PostgreSQLContainer` tạo JDBC details dễ hơn `GenericContainer("postgres:16")`?
5. **Generic Redis:** Khi @Bean return type là GenericContainer, vì sao cần `@ServiceConnection(name="redis")`?
6. **Type filter:** `@ServiceConnection(type=JdbcConnectionDetails.class)` có tác dụng gì nếu app dùng R2DBC hoặc Flyway?
7. **Database slice:** Vì sao `@JdbcTest` đôi khi thay PostgreSQL bằng H2 và `@AutoConfigureTestDatabase(replace=NONE)` quan trọng?
8. **Context cache:** Static @Container dừng sau test class nhưng Spring context còn cache. Triệu chứng nào có thể xảy ra và có thể xử lý bằng Spring-managed bean ra sao?
9. **Migrations:** Khi thêm Flyway, nên bỏ schema.sql hoặc đổi SQL init config như thế nào để không tạo bảng hai lần?
10. **Docker:** Một test xanh trên máy local nhưng CI không có Docker daemon: nên sửa Java code hay cấu hình runner?
11. **Custom client:** Một @Bean DataSource viết tay đọc `spring.datasource.url` trực tiếp. Vì sao nó có thể không dùng JdbcConnectionDetails?
12. **Dynamic fallback:** Viết bản tương đương của test PostgreSQL với @DynamicPropertySource, không dùng @ServiceConnection; phương pháp này phù hợp phiên bản nào?
13. **Multiple services:** App có PostgreSQL + Redis; bạn cần những starters và ConnectionDetails types nào?
14. **Isolation:** Nếu test một HTTP request lưu dữ liệu xuống Postgres container, vì sao @Transactional trên client test method không đủ để rollback?
15. **Upgrade:** Khi chuyển Boot 3.3 lên Boot 4.x, tài liệu/API nào phải kiểm và vì sao import JdbcConnectionDetails có thể đổi?

## 15. Tài liệu chính thức

- [Spring Boot 3.3 — Testcontainers & Service Connections](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): @ServiceConnection, các `ContainerConnectionDetailsFactory`, image matching, type filter, Spring-managed containers và @DynamicPropertySource.
- [Spring Boot 3.3 — ServiceConnection API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/testcontainers/service/connection/ServiceConnection.html): annotation, `name`, `type`, since 3.1.0.
- [Spring Boot 3.3 — ConnectionDetails API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/service/connection/ConnectionDetails.html): interface gốc kết nối service.
- [Spring Boot 3.3 — JdbcConnectionDetails API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcConnectionDetails.html): URL, username, password, driver.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @SpringBootTest, @JdbcTest và DataSource replacement.
- [Spring Boot 3.3 — Database Initialization](https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html): `spring.sql.init.mode`, schema.sql và migrations.
- [Spring Framework — @DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): registration of dynamic property suppliers.
- [Testcontainers for Java — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): @Testcontainers, @Container, lifecycle.
- [Testcontainers for Java — PostgreSQL](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQLContainer, JDBC URL và container behavior.
- [Spring Boot 4 — API Overview](https://docs.spring.io/spring-boot/api/java/): kiểm lại các module/package khi nâng version.

**Ghi nhớ:** `@ServiceConnection` của **Spring Boot 3.1+** không tự kết nối client chỉ vì một container đang chạy; nó cho Boot nhận diện container và tạo bean `ConnectionDetails` phù hợp. Auto-configuration có hỗ trợ sẽ dùng details để kết nối, thường ưu tiên chúng hơn URL/host/port properties. Chọn **typed container** khi có thể, dùng **`name` hint** cho image-based factory với `GenericContainer`, **`type` filter** khi cần giới hạn loại details, và kiểm tra **vòng đời container/context** cùng **database replacement** trong test slices. Với Boot 3.0 hoặc container không được factory hỗ trợ, **`@DynamicPropertySource`** vẫn là lựa chọn có giá trị; luôn xác minh bằng kết nối thật, không chỉ bằng việc đọc Environment properties.

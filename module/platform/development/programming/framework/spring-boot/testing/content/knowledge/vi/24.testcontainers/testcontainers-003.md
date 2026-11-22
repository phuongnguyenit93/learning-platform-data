# @Testcontainers, @Container và vòng đời static hoặc instance

Trong nhóm **Testcontainers** thuộc module **Spring Boot - testing**, `@Testcontainers` và `@Container` là hai annotation của tích hợp Testcontainers với **JUnit Jupiter**. Chúng tự động quản lý thời điểm khởi động và dừng container chạy database, broker hoặc service phụ trợ. Cách khai báo field **static hay instance** xác định container sống theo **test class** hay **test method**, ảnh hưởng tốc độ, isolation, cleanup và khả năng Spring Boot dùng lại `ApplicationContext`.

**Kết luận quan trọng ngay từ đầu:**

- `@Testcontainers` đăng ký `TestcontainersExtension` với JUnit Jupiter.
- `@Container` đánh dấu field chứa Testcontainers container để extension quản lý.
- **`static @Container`**: container được start trước các phương thức test của class và stop sau class.
- **Instance `@Container`** (field không static): extension start trước **mỗi test method** và stop sau method.
- **Static không tự reset database giữa methods**; instance không tự viết assertions hoặc bảo vệ tài nguyên bên ngoài container.
- **`@ServiceConnection`**, `@DynamicPropertySource` và `@AutoConfigureTestDatabase` có vai trò nối container vào Spring, **không thay thế quy tắc owner/lifecycle** của JUnit extension.
- Khi Spring TestContext cache còn giữ datasource/driver mà JUnit đã dừng container, các class chạy riêng có thể xanh nhưng chạy cả suite thì lỗi. Có thể tránh bằng container bean do Spring context quản lý hoặc mô hình shared lifecycle rõ ràng.

Bài sử dụng **Java 17+, JUnit Jupiter, Testcontainers 1.x, Spring Boot 3.5.x, PostgreSQL 16 và Spring JDBC**. Các source files minh họa chạy được trong một project Gradle đã cấu hình tương thích; phần cuối có ví dụ Java SE độc lập (không cần Docker) và stdout xác định.

## 1. Testcontainers là gì và test kiểm chứng được điều gì?

Testcontainers chạy dependency thật bên trong Docker container và cho test Java kết nối đến nó. Ví dụ: thay vì mock repository và khẳng định câu SQL đúng trên PostgreSQL, bạn cho repository/JdbcTemplate thực thi trên một PostgreSQL container.

```text
JUnit Jupiter
    |
    +-- TestcontainersExtension
    |       |
    |       +-- Docker container PostgreSQL
    |                    |
    |                    +-- host/port động, JDBC URL
    |                    +-- database + constraints
    |
    +-- Test method
            |
            +-- JDBC/JPA/repository gọi database thật
            +-- assert data và exception
```

Nhờ đó có thể kiểm tra:

- JDBC driver kết nối được; schema/migrations phù hợp với database engine.
- SQL constraints, transactions, data mapping và query hoạt động trong môi trường gần production.
- Service thực như Redis/Kafka/Neo4j tương tác được, nếu test đã cấu hình đúng module và assertion.
- Hành vi với startup/readiness, URI, credentials và mapped ports.

Nhưng container **không tự chứng minh** authentication của production, network/cloud routing, database volume thật hoặc business assertions. Nó chỉ cung cấp hạ tầng để thực hiện test. Một test chỉ gọi `postgres.isRunning()` không chứng minh bảng đã được tạo hay repository chạy đúng.

**Hai khái niệm container khác nhau:** `PostgreSQLContainer` của Testcontainers là một Docker container; `ApplicationContext` của Spring là IoC container các beans. Chúng có thể không cùng tuổi thọ.

## 2. Tách vai trò @Testcontainers, @Container và vòng đời

Ví dụ đơn giản:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class DatabaseTest {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void databaseProcessIsRunning() {
        assertTrue(postgres.isRunning());
    }
}
```

Với project đã có JUnit Jupiter, driver Testcontainers PostgreSQL và Docker đang chạy, đây là một class test Java hoàn chỉnh. Lưu ý:

- `@Testcontainers` tương đương việc đăng ký Jupiter extension chuyên dụng để quản lý các `@Container` fields.
- `@Container` **không** tự động mở Docker nếu extension không được kích hoạt.
- Field `postgres` là static nên thuộc phạm vi **test class**.
- Không gọi `postgres.start()` trong `@BeforeEach` vì extension đã sở hữu start/stop.
- Container process đang chạy chưa đủ để kết luận database đã có data/schema mong muốn.

Nếu muốn đăng ký extension tường minh, có thể dùng `@ExtendWith(TestcontainersExtension.class)` thay cho `@Testcontainers`; không cần cả hai cho cùng mục đích.

## 3. Static @Container: shared trong một test class

Khai báo:

```java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");
```

Giả sử JUnit chạy ba method:

```text
TestcontainersExtension starts postgres
    |
    +-- @BeforeAll
    +-- @BeforeEach -> @Test A -> @AfterEach
    +-- @BeforeEach -> @Test B -> @AfterEach
    +-- @BeforeEach -> @Test C -> @AfterEach
    +-- @AfterAll
    |
TestcontainersExtension stops postgres
```

**Lợi thế:** một lần khởi động PostgreSQL cho nhiều methods giảm startup overhead. Test vẫn có JDBC connection và transactions riêng nếu được thiết kế tương ứng.

**Rủi ro:**

- Database state có thể còn giữa các methods: INSERT/UPDATE đã commit không tự biến mất chỉ vì có `static`.
- Các methods không được dựa vào thứ tự JUnit chạy.
- Một test xóa bảng, thay schema hoặc tạo dữ liệu không cleanup có thể phá test khác.
- Container chỉ được chia sẻ trong phạm vi class theo extension, không tự trở thành singleton cho toàn JVM.
- Test class A kết thúc thì extension dừng container, mặc dù một Spring context đã cache và còn datasource trỏ đến nó.

**Không nên** dùng global `DELETE FROM ...` trước mỗi test khi các test khác đang chia sẻ database/parallel suite mà không có isolation rõ.

## 4. Instance @Container: mỗi method có một vòng start/stop

Khai báo:

```java
@Testcontainers
class FreshDatabaseTest {
    @Container
    PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test void testA() {
        // postgres được start cho method này
    }

    @Test void testB() {
        // một vòng start/stop khác
    }
}
```

Đây là snippet chưa có imports/assertions, không phải file đầy đủ; mục 9 có class runnable. Lifecycle:

```text
Method A:
    start instance container -> test A -> stop

Method B:
    start instance container -> test B -> stop
```

**Lợi thế:** mỗi method có database mới trong mô hình container không dùng volume/shared state bên ngoài. Hữu ích cho kiểm tra migration, schema destructive, dữ liệu khó rollback hoặc môi trường cần isolation mạnh.

**Đánh đổi:** container PostgreSQL tốn thời gian start, download image lần đầu, tài nguyên Docker/CPU/memory; nhiều methods có thể khiến suite chậm đáng kể. Mỗi method vẫn phải seed schema/data. Method khác không thể dựa vào dữ liệu của method trước.

**Lưu ý JUnit `@TestInstance(PER_CLASS)`:** annotation này làm Jupiter tái sử dụng cùng **test class object**, nhưng **không đổi quy tắc Testcontainers extension**: field instance vẫn được start/stop trong lifecycle **mỗi method**. Không dùng PER_CLASS để “biến” instance container thành class-scoped.

## 5. Bảng so sánh nhanh

| Tiêu chí | Static field | Instance field |
| --- | --- | --- |
| Annotation | `static @Container` | `@Container` |
| Start | Trước test methods của class | Trước mỗi test |
| Stop | Sau toàn bộ class | Sau từng test |
| 5 test methods | Thường 1 vòng start/stop | Thường 5 vòng start/stop |
| Data đã commit giữa methods | Có thể tồn tại | Thường không, nếu fresh DB |
| Startup cost | Thường thấp | Thường cao hơn |
| Cần fixture/schema | Có | Có ở mỗi container |
| Phù hợp | Repository tests có rollback hoặc cleanup | Isolation method mạnh, destructive setup |
| Rủi ro với cached Spring context | Có nếu context sống lâu hơn container | Rất đáng chú ý khi context giữ config của container cũ |
| Đồng nghĩa thread-safe? | Không | Không tự động |

**Quy tắc chọn:** với Spring repository/JDBC tests, thường bắt đầu **static + transaction rollback + fixture độc lập**. Với test thuần JUnit cần DB sạch mỗi method, instance dễ hiểu. Khi nhiều Spring test classes cần chia sẻ cached context, xem xét container làm **Spring test bean** hoặc một lifecycle thực sự dài bằng context.

## 6. Gradle và yêu cầu môi trường

Ví dụ nhắm **Spring Boot 3.5 + Testcontainers 1.x**, Java 17. Trong project Gradle đã có Boot plugins/repositories/BOM/toolchain, phần dependency cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn bổ sung**, không phải toàn bộ `build.gradle`. Spring Boot BOM giúp chọn Testcontainers, JDBC driver, Spring Framework và JUnit versions tương thích. Với Spring Boot 4/Testcontainers 2.x, package/module một số thành phần khác; phải chỉnh imports và Gradle coordinates theo bộ version đang dùng, không trộn hai major versions.

Cần có:

- Docker Engine/Desktop hoặc container runtime được Testcontainers hỗ trợ và truy cập được từ test process.
- Quyền pull image `postgres:16-alpine`, đủ CPU/RAM/storage, network/registry nếu image chưa cache.
- Test source và migrations không trỏ tới database production.
- CI có Docker daemon hợp lệ; nếu Docker là requirement bắt buộc, thiếu Docker phải làm job integration fail.
- Host port không hardcode; Testcontainers tạo random mapped port để tránh tranh chấp 5432 giữa máy dev và CI.
- Không tắt resource reaper/cơ chế cleanup chỉ để né lỗi môi trường mà chưa hiểu hệ quả.

`@Testcontainers(disabledWithoutDocker = true)` có thể **skip** tests khi Docker không khả dụng. Chỉ dùng khi chức năng đó đúng chính sách: CI bắt buộc test database không nên “xanh giả” do skip.

## 7. Project mẫu và các file cần tạo

Cấu trúc:

```text
src/
├── main/java/example/testing/containers/
│   ├── ContainerLessonApplication.java
│   ├── LifecycleRules.java
│   └── LifecycleScopeDemo.java
└── test/
    ├── resources/schema.sql
    └── java/example/testing/containers/
        ├── StaticPostgresLifecycleTest.java
        ├── InstancePostgresLifecycleTest.java
        ├── SpringJdbcPostgresTest.java
        ├── ContextOwnedContainerConfig.java
        ├── ContextOwnedJdbcTest.java
        └── LifecycleRulesTest.java
```

Tất cả source files phía dưới dùng cùng package `example.testing.containers`.

### Spring Boot entry point

Tạo `src/main/java/example/testing/containers/ContainerLessonApplication.java`:

```java
package example.testing.containers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContainerLessonApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                ContainerLessonApplication.class, args);
    }
}
```

File này giúp các Spring test slices tìm được Boot configuration từ cùng package. Không cần gọi `main()` khi chạy JUnit. Nếu chạy ứng dụng ở ngoài test, phải có datasource thực và migration tương ứng; container chỉ khai báo trong `src/test` không tự xuất hiện ở production.

## 8. Ví dụ Java/JUnit hoàn chỉnh: static PostgreSQL

Tạo `src/test/java/example/testing/containers/StaticPostgresLifecycleTest.java`:

```java
package example.testing.containers;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.UUID;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class StaticPostgresLifecycleTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    private static String startedId;

    @BeforeAll
    static void rememberContainerIdentity() {
        assertTrue(postgres.isRunning());
        startedId = postgres.getContainerId();
        assertNotNull(startedId);
    }

    private static Connection connect() throws SQLException {
        return DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword());
    }

    @Test
    void jdbcUsesMappedPostgresAndClassContainerId()
            throws Exception {
        assertTrue(postgres.isRunning());
        assertEquals(startedId, postgres.getContainerId());
        assertTrue(postgres.getMappedPort(5432) > 0);

        try (Connection connection = connect();
             Statement statement = connection.createStatement();
             ResultSet rs = statement.executeQuery(
                     "SELECT current_database()")) {
            assertTrue(rs.next());
            assertEquals(
                    postgres.getDatabaseName(), rs.getString(1));
        }
    }

    @Test
    void writesAndCleansCommittedFixture() throws Exception {
        assertEquals(startedId, postgres.getContainerId());

        String key = "static-" + UUID.randomUUID();

        try (Connection connection = connect();
             Statement ddl = connection.createStatement()) {
            ddl.execute("""
                    CREATE TABLE IF NOT EXISTS lifecycle_events (
                        event_key VARCHAR(80) PRIMARY KEY,
                        payload VARCHAR(120) NOT NULL
                    )
                    """);

            try {
                try (PreparedStatement insert =
                        connection.prepareStatement("""
                        INSERT INTO lifecycle_events
                            (event_key, payload)
                        VALUES (?, ?)
                        """)) {
                    insert.setString(1, key);
                    insert.setString(2, "Xin chào 😀");
                    assertEquals(1, insert.executeUpdate());
                }

                try (PreparedStatement select =
                        connection.prepareStatement("""
                        SELECT payload FROM lifecycle_events
                        WHERE event_key = ?
                        """)) {
                    select.setString(1, key);
                    try (ResultSet rs = select.executeQuery()) {
                        assertTrue(rs.next());
                        assertEquals("Xin chào 😀",
                                rs.getString(1));
                    }
                }
            } finally {
                try (PreparedStatement delete =
                        connection.prepareStatement("""
                        DELETE FROM lifecycle_events
                        WHERE event_key = ?
                        """)) {
                    delete.setString(1, key);
                    delete.executeUpdate();
                }
            }
        }
    }

    @AfterAll
    static void stillAliveBeforeExtensionStopsClass() {
        assertTrue(postgres.isRunning());
        assertEquals(startedId, postgres.getContainerId());
    }
}
```

**Hai test methods** kiểm tra cùng một `containerId` trong một class, kết nối PostgreSQL qua mapped port/JDBC URL thật và insert/read-back chuỗi Unicode. Sau khi test hoàn tất, `finally` xóa đúng fixture key mà test sở hữu.

**Tại sao cleanup dù container sẽ stop sau class?** Vì cả hai test methods dùng **cùng database**. Một row đã commit có thể làm test khác bị ảnh hưởng trước khi class kết thúc; dọn theo key khiến test độc lập hơn. PostgreSQL connection dùng auto-commit theo mặc định trong ví dụ JDBC thuần, nên rollback của Spring Test không tham gia ở đây.

`@BeforeAll`/`@AfterAll` quan sát container đang chạy. Extension bắt đầu static container trước các callbacks của test class và dừng nó sau khi class kết thúc. **Không gọi thêm `postgres.stop()` trong `@AfterAll`**, vì extension đã sở hữu cleanup.

## 9. Ví dụ Java/JUnit hoàn chỉnh: instance PostgreSQL

Tạo `src/test/java/example/testing/containers/InstancePostgresLifecycleTest.java`:

```java
package example.testing.containers;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class InstancePostgresLifecycleTest {

    @Container
    final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @BeforeEach
    void startsBeforeEachMethod() {
        assertTrue(postgres.isRunning());
    }

    @Test
    void firstMethodHasFreshDatabase() throws Exception {
        assertFreshThenInsert();
    }

    @Test
    void secondMethodAlsoHasFreshDatabase() throws Exception {
        assertFreshThenInsert();
    }

    private void assertFreshThenInsert() throws Exception {
        try (Connection connection =
                    DriverManager.getConnection(
                            postgres.getJdbcUrl(),
                            postgres.getUsername(),
                            postgres.getPassword());
             Statement statement =
                    connection.createStatement()) {
            statement.execute("""
                    CREATE TABLE isolated_values (
                        value_text VARCHAR(120) NOT NULL
                    )
                    """);

            try (ResultSet rs = statement.executeQuery(
                    "SELECT COUNT(*) FROM isolated_values")) {
                assertTrue(rs.next());
                assertEquals(0, rs.getInt(1));
            }

            assertEquals(1, statement.executeUpdate("""
                    INSERT INTO isolated_values(value_text)
                    VALUES ('one row')
                    """));
        }
    }

    @AfterEach
    void stopOccursAfterMethodCallbacks() {
        assertTrue(postgres.isRunning());
    }
}
```

**Hai methods không dựa vào thứ tự chạy.** Mỗi method có một vòng startup/teardown của Docker container, nên tạo table `isolated_values` mà **không dùng `IF NOT EXISTS`** vẫn hợp lệ. Một container tái dùng với cùng committed schema sẽ gây lỗi `table already exists`; đây là cách test biểu diễn yêu cầu fresh database một cách quan sát được.

**Lưu ý:** nếu dùng external volume/reusable database config thì không được suy diễn data sạch chỉ từ cú pháp instance. Ví dụ này không khai báo volume dùng chung hoặc reusable container.

Thời điểm:

- `@BeforeEach`: instance container đã được extension start.
- `@Test`: container đang chạy.
- `@AfterEach`: container vẫn đang chạy.
- Sau `@AfterEach`: extension stop container của method.

## 10. Spring Boot @ServiceConnection cùng static @Container

Spring Boot 3.5 có annotation `@ServiceConnection` để tạo connection details từ Testcontainers, giúp Datasource lấy JDBC URL/username/password mà không hardcode port. Trong một **JDBC slice test** ta có thể dùng `@JdbcTest` với PostgreSQL.

### Test schema: schema.sql

Tạo `src/test/resources/schema.sql`:

```sql
CREATE TABLE IF NOT EXISTS app_events (
    event_key VARCHAR(80) PRIMARY KEY,
    description VARCHAR(200) NOT NULL
);
```

Vì PostgreSQL không phải embedded database theo SQL initialization của Boot, ta cấu hình `spring.sql.init.mode=always` cho test. Nếu ứng dụng dùng Flyway/Liquibase, nên chạy migrations phù hợp và tránh schema.sql tạo trùng bảng.

### SpringJdbcPostgresTest.java

Tạo `src/test/java/example/testing/containers/SpringJdbcPostgresTest.java`:

```java
package example.testing.containers;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.jdbc.core.JdbcTemplate;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@JdbcTest(properties = "spring.sql.init.mode=always")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class SpringJdbcPostgresTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void unicodeRoundTripWithRealPostgres() {
        assertTrue(postgres.isRunning());

        String key = "spring-" + UUID.randomUUID();
        String text = "Kiểm thử 😀";

        jdbc.update("""
                INSERT INTO app_events(event_key, description)
                VALUES (?, ?)
                """, key, text);

        String result = jdbc.queryForObject("""
                SELECT description FROM app_events
                WHERE event_key = ?
                """, String.class, key);

        assertEquals(text, result);
    }

    @Test
    void secondMethodUsesSameClassContainer() {
        assertTrue(postgres.isRunning());

        String key = "spring-" + UUID.randomUUID();
        jdbc.update("""
                INSERT INTO app_events(event_key, description)
                VALUES (?, ?)
                """, key, "isolated");

        Integer total = jdbc.queryForObject("""
                SELECT COUNT(*) FROM app_events
                WHERE event_key = ?
                """, Integer.class, key);

        assertEquals(Integer.valueOf(1), total);
    }
}
```

**Annotation này làm gì?**

- `@Testcontainers` + static `@Container`: JUnit extension **start/stop PostgreSQL theo test class**.
- `@ServiceConnection` trên field: Spring Boot tạo connection details cho DataSource từ running container.
- `@JdbcTest`: cấu hình context hẹp gồm DataSource/JdbcTemplate và transaction infrastructure; **không load full web/controller/services**.
- `@AutoConfigureTestDatabase(replace = NONE)`: ngăn việc thay PostgreSQL bằng embedded H2; tránh kiểm thử nhầm database.
- `spring.sql.init.mode=always`: chạy test schema trên PostgreSQL non-embedded.
- `@JdbcTest` mặc định tạo test-managed transaction và rollback DML của method, nên hai methods có thể dùng DB chung mà không làm bẩn state nếu SQL ở trong transaction đó.

**Quan trọng:** đọc lại bằng `JdbcTemplate` trong cùng transaction chứng minh SQL đã chạy và mapping hoạt động, **không chứng minh dữ liệu đã commit bền vững**. Khi mục tiêu là commit hoặc HTTP thật, cần kiểm tra từ transaction khác và cleanup độc lập.

**Rủi ro cần nhớ:** class kết thúc có thể stop static container nhưng Spring TestContext vẫn cache `ApplicationContext`. Xem mục 12 trước khi copy pattern này sang hàng chục Spring test classes có cùng context.

## 11. Container bean: lifecycle theo Spring ApplicationContext

Nếu các Spring test classes thực sự cần chia sẻ context, một cách tổ chức đáng cân nhắc là **đặt Testcontainers object thành Spring test bean**. Với Spring Boot 3.5, `@ServiceConnection` trên `@Bean` method giúp Boot nhận kiểu container, tạo details và quản lý startup/shutdown theo vòng đời context.

### ContextOwnedContainerConfig.java

Tạo `src/test/java/example/testing/containers/ContextOwnedContainerConfig.java`:

```java
package example.testing.containers;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class ContextOwnedContainerConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>(
                "postgres:16-alpine");
    }
}
```

Return type `PostgreSQLContainer<?>` rất quan trọng: khi dùng `@Bean`, Boot có thể nhận dạng service connection factory dựa trên **declared return type**. Nếu trả type chung `GenericContainer<?>` mà không có hint, Boot có thể không biết nó là PostgreSQL và sẽ không tạo đúng connection details.

### ContextOwnedJdbcTest.java

Tạo `src/test/java/example/testing/containers/ContextOwnedJdbcTest.java`:

```java
package example.testing.containers;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@JdbcTest(properties = "spring.sql.init.mode=always")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
@Import(ContextOwnedContainerConfig.class)
class ContextOwnedJdbcTest {

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void springManagedContainerHasWorkingDatasource() {
        String key = "bean-" + UUID.randomUUID();

        jdbc.update("""
                INSERT INTO app_events(event_key, description)
                VALUES (?, ?)
                """, key, "context-owned");

        String result = jdbc.queryForObject("""
                SELECT description FROM app_events
                WHERE event_key = ?
                """, String.class, key);

        assertEquals("context-owned", result);
    }
}
```

**Một JUnit test method** dùng PostgreSQL container **do Spring context quản lý**. Không cần `@Testcontainers` hoặc `@Container` trong class này, vì bean lifecycle của Boot mới là owner. Container sống cùng context, giúp tránh việc Jupiter extension dừng resource khi context còn được cache.

**Không đồng nghĩa một container cho toàn JVM.** Nếu Spring tạo context khác do profile/configuration khác, có thể có container bean riêng. Nếu context cache bị invalidated, container cũ được đóng theo lifecycle và context mới tạo container mới.

**Không gọi `postgresContainer().start()` bên trong bean method**, không gọi `stop()` trong `@AfterEach`. Boot chịu trách nhiệm lifecycle. Nếu dùng cùng object vừa là Spring bean vừa gắn `@Container` ở một JUnit field, sẽ có hai owner — nên tránh.

## 12. Spring TestContext cache và lỗi “chạy riêng xanh, chạy suite đỏ”

Spring TestContext framework cache `ApplicationContext` để tránh tạo lại context cho các test classes cấu hình tương tự. Nhưng Jupiter extension stop **static @Container** sau khi class kết thúc, kể cả khi context Spring còn được giữ lại.

```text
Class A
  static @Container postgresA started
  Spring context -> datasource -> postgresA
  tests pass
  Jupiter stops postgresA

Class B
  Spring reuses compatible cached context
  datasource still targets postgresA
  query -> Connection refused / stale pool
```

**Đây là failure mode có điều kiện**, không phải mọi bộ test đều sẽ gặp: context cache key của Spring xét configuration/customizers, nên hai test classes có thể tạo contexts riêng. Nhưng nếu context thực sự được reuse, **dependency của context phải còn sống**.

Các cách kiểm soát:

- Một test class đơn lẻ: static `@Container` thường đủ.
- Nhiều class dùng chung context: container bean theo context lifecycle có thể an toàn và rõ ràng hơn.
- Shared container cho toàn test suite: owner riêng phải start trước contexts và stop sau khi contexts không còn dùng; không nhầm với field static ở một class bất kỳ.
- `@DirtiesContext` có thể ép context đóng/rebuild để tránh reuse sai, nhưng **không phải chiến lược cleanup database** và làm test chậm. Dùng có chọn lọc.
- Không dùng instance `@Container` một cách máy móc trong Spring integration test có context cache: DataSource được cấu hình cho container của method đầu có thể còn giữ URL khi extension đã dừng container và khởi động container mới với port khác.

**Quy tắc ownership:** tài nguyên mà Spring bean giữ connection đến phải sống ít nhất đến khi bean/context không còn dùng nó. Cách viết `static` hay `@TestInstance(PER_CLASS)` không tự giải quyết điều này.

## 13. @DynamicPropertySource là lựa chọn khác @ServiceConnection

Khi chưa dùng `@ServiceConnection`, Spring có `@DynamicPropertySource` để đăng ký properties động từ container.

Snippet minh họa có thể đặt vào class test có các imports tương ứng:

```java
@Testcontainers
@JdbcTest(properties = "spring.sql.init.mode=always")
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE)
class JdbcDynamicPropertiesTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>(
                    "postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {
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
}
```

Đoạn này chỉ minh họa cấu hình, **chưa phải một test runnable** vì chưa có imports và method `@Test`. Ý nghĩa:

- `@DynamicPropertySource` method phải static, tham số `DynamicPropertyRegistry`.
- `registry.add(...)` nhận supplier, cho phép lấy host port/credentials sau startup.
- `@DynamicPropertySource` **không start/stop Docker**. Vòng đời vẫn do extension xử lý.
- Với PostgreSQL trong Boot 3.5, thường chọn một trong hai cách: `@ServiceConnection` hoặc dynamic datasource properties để giảm ambiguity/precedence.
- Cache context vẫn phải phù hợp với owner container. Supplier không tự kéo dài lifecycle.
- Không hardcode `jdbc:postgresql://localhost:5432/test` khi Testcontainers đã cấp mapped port.

Một bảng tách trách nhiệm:

| Thành phần | Quản lý lifecycle Docker? | Nhiệm vụ |
| --- | --- | --- |
| `@Testcontainers` / extension | Có, với `@Container` fields | Start/stop theo static/instance |
| `@ServiceConnection` trên static field | Không tự thay thế extension | Boot tạo connection details |
| `@Bean @ServiceConnection` | Boot quản lý bean container | Context-scoped lifecycle + details |
| `@DynamicPropertySource` | Không | Inject properties vào Spring Environment |
| `@AutoConfigureTestDatabase(Replace.NONE)` | Không | Không replace test datasource |
| `@DirtiesContext` | Không trực tiếp | Thay lifecycle của cached Spring context |

Không nhầm “kết nối đến container” với “sở hữu start/stop container”.

## 14. Dữ liệu trong static container: rollback, cleanup, schema

Một static PostgreSQL container dùng cho nhiều methods có thể tích lũy rows:

```text
Test A: INSERT key='same-key', COMMIT
Test B: INSERT key='same-key'
    -> duplicate primary key
```

Nếu test đã được Spring TestContext mở test-managed transaction (ví dụ `@JdbcTest` mặc định), DML tham gia transaction đó sẽ rollback cuối method. Nhưng rollback không bao phủ mọi side effect:

- JDBC connection tự mở qua `DriverManager` với auto-commit và không join Spring transaction.
- HTTP thật qua `@SpringBootTest(RANDOM_PORT)`: server thread có transaction độc lập.
- `@Async` hoặc `CompletableFuture` worker chạy ngoài test thread.
- `@Transactional(propagation = REQUIRES_NEW)` mở transaction riêng qua proxy.
- Kafka/Redis/network operation đã được thực thi, không nằm trong JDBC rollback.
- DDL/migrations/schema changes có lifecycle riêng, tùy database/transaction.

**Chiến lược tốt:**

1. Test tự tạo fixture nó cần; không phụ thuộc test khác.
2. Dùng khóa riêng (UUID) và chỉ xóa dữ liệu mà method sở hữu.
3. Với test transaction: hiểu dữ liệu nhìn thấy trong cùng transaction **chưa chứng minh commit**.
4. Với HTTP/@Async commit: chờ task hoàn tất, cleanup bằng transaction độc lập sau đó.
5. Với schema destructive: dùng per-method DB/container hoặc riêng schema.
6. Với database dùng chung: không chạy global `DELETE FROM table` khi các test khác có thể đang đọc/ghi.
7. Với Docker reusable container: thiết kế reset/cleanup mạnh hơn vì state có thể còn **giữa các lần chạy**.

**Đừng dùng `@DirtiesContext` chỉ để dọn committed DB rows**. Nó tác động cache Spring context; data đã commit có thể còn trên một external/shared database.

## 15. JUnit callbacks: container chạy lúc nào?

| Callback | Static container | Instance container |
| --- | --- | --- |
| `@BeforeAll` | Đã start | Chưa ở per-method lifecycle |
| `@BeforeEach` | Đang chạy | Đã start |
| `@Test` | Đang chạy | Đang chạy |
| `@AfterEach` | Đang chạy | Chưa bị stop |
| `@AfterAll` | Đang chạy trước cleanup extension | Per-method containers đã stop |
| Cleanup bởi extension | Sau class | Sau từng method |

**Tại sao bảng này có ích?**

- Có thể truy vấn static container trong `@BeforeAll`.
- Nếu đặt instance container vào một `@BeforeAll`, bạn đang dùng tài nguyên trước lúc per-method extension start nó.
- Với instance container, cleanup DB ngay trong `@AfterEach` xảy ra trước khi Docker stop; nếu nó còn đang chạy thì có thể dọn tài nguyên ngoài container.
- Nếu một method có @Async task đang chạy, không cho container stop khi task chưa hoàn tất và còn cần database.
- Spring `@AfterTransaction` có ý nghĩa khác JUnit `@AfterEach`: nó dùng để quan sát trạng thái **sau transaction test đã rollback/commit**.

Một lưu ý về `@TestInstance(PER_CLASS)`: JUnit có thể dùng cùng object ở nhiều test methods, nhưng extension vẫn kiểm soát instance `@Container` theo per-method lifecycle; các callback trên không tự biến thành class-scoped.

## 16. Readiness và mapped port: đừng nhầm process chạy với DB sẵn sàng

Docker process started không đồng nghĩa PostgreSQL/Kafka/HTTP service đã chấp nhận kết nối. Testcontainers modules có default wait strategy; với `GenericContainer` bạn có thể cấu hình riêng.

Ví dụ cấu hình HTTP health check (chỉ là snippet vì image riêng không có trong bài):

```java
GenericContainer<?> api =
        new GenericContainer<>(
                DockerImageName.parse("my-test-api:1.0"))
                .withExposedPorts(8080)
                .waitingFor(
                        Wait.forHttp("/health")
                                .forPort(8080)
                                .forStatusCode(200));
```

Mẫu này cần imports từ Testcontainers, image có endpoint `/health` thật và network phù hợp; không phải class runnable độc lập.

Với PostgreSQL:

```java
int hostPort = postgres.getMappedPort(5432);
String jdbcUrl = postgres.getJdbcUrl();
```

Cả hai chỉ hợp lệ **sau khi container đã start**. Không giả định hostPort == 5432: Testcontainers map container-internal 5432 sang host port động, kể cả chạy với remote Docker host. Dùng `getHost()` + `getMappedPort(...)` nếu phải dựng endpoint cho custom client, còn JDBC ưu tiên `getJdbcUrl()`/Spring Boot `@ServiceConnection`.

**Các timeout không giống nhau**: image pull/startup, readiness wait, JDBC query timeout, JUnit method timeout và CI job timeout là những tầng khác nhau. Khi báo lỗi, kiểm tra bước nào chưa hoàn tất trước khi tăng ngưỡng vô điều kiện.

## 17. Parallel execution và các test dùng chung database

Jupiter Testcontainers extension **không cung cấp cam kết an toàn mặc định cho test chạy song song**. Static container là shared mutable resource:

- Method A tạo row, method B truncate table.
- Test A migrate schema, test B đang query.
- Một class stop container trong khi worker/context ở class khác còn kết nối.
- Nhiều tests cùng dùng business key và va chạm UNIQUE.
- Database pool hết connections khi nhiều methods sử dụng cùng lúc.

Nếu cần parallel CI:

1. Cân nhắc tắt parallel execution đối với nhóm tests thao tác cùng DB/schema.
2. Dùng database/schema hoặc container riêng theo test group, không có shared global cleanup.
3. Dùng UUID fixture keys, tránh hardcoded IDs nếu chúng có thể trùng.
4. Chờ HTTP/@Async background operations hoàn tất trước khi teardown.
5. Nếu dùng `@ResourceLock` của JUnit, mọi test liên quan phải tuân thủ cùng lock; lock không bảo vệ process ngoài JUnit.
6. Không kỳ vọng static fields tự tạo thread-safety; chúng chỉ chia sẻ reference.

**Kiểm tra cả test chạy riêng lẻ và full suite.** Lỗi chỉ xuất hiện khi chạy full suite thường gợi ý shared state, context cache, lifecycle hoặc concurrency chứ không nhất thiết là logic SQL sai.

## 18. Reusable containers, singleton và manual lifecycle

**`static @Container` không đồng nghĩa reusable container giữa test runs.** Theo mặc định, Jupiter extension vẫn stop container sau class. Có các patterns nâng cao:

- **Singleton container** khởi động thủ công ở một base class/test suite owner; có thể tiết kiệm startup, nhưng phải phối hợp context lifetime, cleanup và shutdown.
- **Reusable containers** với `withReuse(true)` và cấu hình Testcontainers tương ứng dành cho môi trường phát triển; có thể giữ Docker container giữa các lần chạy. Hệ quả là data/configuration có thể tồn tại và gây test contamination.
- **Container Spring bean** gắn với ApplicationContext cache, thường phù hợp khi nhiều test classes share context.

Không bật reuse chỉ để làm CI nhanh hơn mà bỏ qua yêu cầu test sạch. Reusable containers có hạn chế, không nên là mặc định cho CI; đồng thời không nên trộn quy tắc JUnit extension stop với kỳ vọng container vẫn tồn tại sau test.

**Manual start/stop** chỉ hợp lý khi có owner rõ ràng. Ví dụ một suite bootstrapping hạ tầng ở trước toàn bộ tests và đóng sau khi không còn Spring context sử dụng. Không nên để mỗi test class tự gọi `start()` trên cùng một global resource rồi một class bất kỳ `stop()` nó.

## 19. Nhiều containers có dependency

Một integration suite có thể cần PostgreSQL và Redis:

```java
@Container
static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

@Container
static GenericContainer<?> redis =
        new GenericContainer<>(
                DockerImageName.parse("redis:7-alpine"))
                .withExposedPorts(6379);
```

Đây là snippet cần imports/Testcontainers class thích hợp. Nếu hai services độc lập, extension quản lý cả hai. Nhưng nếu service B cần A sẵn sàng trước khi boot, **đừng tin vào thứ tự khai báo Java fields** làm startup dependency contract. Hãy cấu hình dependency/readiness rõ bằng Testcontainers APIs, shared Docker network, health check và Spring configuration tương ứng.

**Rollback PostgreSQL không rollback Redis hoặc Kafka.** Khi test ghi nhiều hệ thống, mỗi hệ thống cần cleanup/transaction/outbox strategy phù hợp. Testcontainers chỉ quyết định hạ tầng sống lúc nào, không biến distributed transaction thành atomic.

## 20. Java 17 độc lập: mô hình hóa class-scope và method-scope

Một ví dụ nhỏ không cần Docker/Spring giúp nhớ callback scope mà không nhầm nó với kiểm thử integration thực.

### LifecycleRules.java

Tạo `src/main/java/example/testing/containers/LifecycleRules.java`:

```java
package example.testing.containers;

public final class LifecycleRules {
    private LifecycleRules() {
    }

    public enum Scope {
        CLASS, METHOD
    }

    public record Lifecycle(
            String startBefore,
            String stopAfter,
            int startsForThreeTests) {
    }

    public static Lifecycle describe(Scope scope) {
        return switch (scope) {
            case CLASS ->
                    new Lifecycle(
                            "before-all", "after-all", 1);
            case METHOD ->
                    new Lifecycle(
                            "before-each", "after-each", 3);
        };
    }
}
```

### LifecycleScopeDemo.java

Tạo `src/main/java/example/testing/containers/LifecycleScopeDemo.java`:

```java
package example.testing.containers;

public class LifecycleScopeDemo {
    public static void main(String[] args) {
        LifecycleRules.Lifecycle shared =
                LifecycleRules.describe(
                        LifecycleRules.Scope.CLASS);
        LifecycleRules.Lifecycle perMethod =
                LifecycleRules.describe(
                        LifecycleRules.Scope.METHOD);

        System.out.println(
                "static=" + shared.startBefore()
                        + "/" + shared.stopAfter());
        System.out.println(
                "instance=" + perMethod.startBefore()
                        + "/" + perMethod.stopAfter());
        System.out.println(
                "starts for 3 methods="
                        + shared.startsForThreeTests()
                        + "/" + perMethod.startsForThreeTests());
    }
}
```

Biên dịch và chạy từ root project với Java 17+:

```bash
javac -d out src/main/java/example/testing/containers/LifecycleRules.java src/main/java/example/testing/containers/LifecycleScopeDemo.java
java -cp out example.testing.containers.LifecycleScopeDemo
```

Stdout **chính xác**:

```text
static=before-all/after-all
instance=before-each/after-each
starts for 3 methods=1/3
```

**Đây chỉ là mô hình Java SE** minh họa quy tắc, không phải đoạn code khởi động Docker. Các integration test ở mục 8–11 mới dùng Testcontainers thật.

### LifecycleRulesTest.java

Tạo `src/test/java/example/testing/containers/LifecycleRulesTest.java`:

```java
package example.testing.containers;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LifecycleRulesTest {

    @Test
    void classScopeStartsOnce() {
        LifecycleRules.Lifecycle result =
                LifecycleRules.describe(
                        LifecycleRules.Scope.CLASS);

        assertEquals("before-all", result.startBefore());
        assertEquals("after-all", result.stopAfter());
        assertEquals(1, result.startsForThreeTests());
    }

    @Test
    void methodScopeStartsPerTest() {
        LifecycleRules.Lifecycle result =
                LifecycleRules.describe(
                        LifecycleRules.Scope.METHOD);

        assertEquals("before-each", result.startBefore());
        assertEquals("after-each", result.stopAfter());
        assertEquals(3, result.startsForThreeTests());
    }
}
```

Đây là **2 JUnit test methods không cần Docker**. Đừng dùng chúng như bằng chứng Testcontainers đã start/stop đúng: chúng chỉ xác nhận logic mô hình. Với actual Docker lifecycle phải chạy `StaticPostgresLifecycleTest` hoặc `InstancePostgresLifecycleTest`.

## 21. Chạy tất cả ví dụ

Linux/macOS (tại root project có Gradle wrapper):

```bash
./gradlew test --tests example.testing.containers.LifecycleRulesTest
./gradlew test --tests example.testing.containers.StaticPostgresLifecycleTest
./gradlew test --tests example.testing.containers.InstancePostgresLifecycleTest
./gradlew test --tests example.testing.containers.SpringJdbcPostgresTest
./gradlew test --tests example.testing.containers.ContextOwnedJdbcTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.containers.LifecycleRulesTest"
.\gradlew.bat test --tests "example.testing.containers.StaticPostgresLifecycleTest"
.\gradlew.bat test --tests "example.testing.containers.InstancePostgresLifecycleTest"
.\gradlew.bat test --tests "example.testing.containers.SpringJdbcPostgresTest"
.\gradlew.bat test --tests "example.testing.containers.ContextOwnedJdbcTest"
```

**Số test methods của bộ ví dụ:**

| Class | Methods | Docker? |
| --- | ---: | --- |
| `LifecycleRulesTest` | 2 | Không |
| `StaticPostgresLifecycleTest` | 2 | Có |
| `InstancePostgresLifecycleTest` | 2 | Có, container per method |
| `SpringJdbcPostgresTest` | 2 | Có |
| `ContextOwnedJdbcTest` | 1 | Có |
| **Tổng** | **9** | Các integration tests cần Docker |

**Đầu ra Gradle/JUnit không có một stdout chính xác duy nhất** vì phụ thuộc versions, image pull, logger và reporter. Kết quả kỳ vọng khi môi trường đúng là 9 test methods pass, nhưng đó **không phải tuyên bố chúng đã được thực thi trong hệ thống của người đọc**.

Lệnh compile demo Java SE đã ghi ở mục 20 có stdout cố định; đó là một quy tắc khác với Integration tests dùng Docker runtime.

## 22. Debug theo triệu chứng

**A. “Could not find a valid Docker environment”:** Docker daemon không chạy hoặc test process không truy cập được socket. Kiểm tra Docker service/context, quyền, CI sidecar/runtime. Không chỉnh SQL khi container chưa được start.

**B. Image pull/timeout:** kiểm tra registry/network/proxy, disk, memory, image tag. Phân biệt image pull failure với database readiness.

**C. “Connection refused” khi chạy cả suite:** kiểm tra static container đã stop trong khi cached Spring context/DataSource còn được reuse, hoặc pool giữ stale mapped URL.

**D. Test method thứ hai lỗi duplicate key:** static container giữ committed row từ method trước; xem rollback của test có áp dụng không, đã cleanup ngoài transaction chưa.

**E. Test instance container chậm:** per-method PostgreSQL startup; cân nhắc static container và transaction rollback nếu isolation vẫn đạt mục tiêu.

**F. Test pass trên H2 dù muốn Postgres:** xem `@AutoConfigureTestDatabase` đã replace datasource không; đặt `Replace.NONE` rõ.

**G. Bean không connect được:** kiểm tra `@ServiceConnection` và `spring-boot-testcontainers`, Boot BOM, Testcontainers module; nếu dùng properties, xem `@DynamicPropertySource` có static/suppliers đúng không.

**H. Schema missing:** container có DB trống; cung cấp migration hoặc `schema.sql` + init mode cho non-embedded DB. Container startup không tự sinh tables từ JDBC entities.

**I. Test bị treo ở startup:** kiểm tra wait strategy, service logs, Docker resources, readiness endpoint, startup timeout.

**J. Dữ liệu bị xóa bất ngờ ở parallel tests:** chung DB/schema nhưng có `DELETE/TRUNCATE`/migration/cleanup giao thoa; điều phối isolation hoặc sequential mode.

**K. Context bean tạo nhiều containers:** có thể có nhiều Spring contexts với cache keys khác nhau; bean-scoped không có nghĩa singleton toàn JVM. Đo context construction và gỡ những config differences không cần thiết.

**L. Test được skip khi Docker thiếu:** kiểm tra `disabledWithoutDocker=true` có bật ngoài ý định; CI phải báo rõ số integration tests đã chạy, không chỉ màu xanh của build.

## 23. Các lỗi phổ biến cần tránh

**1. Chỉ gắn `@Container` mà quên extension.** Không có automatic lifecycle nếu không bật `@Testcontainers` hoặc Jupiter extension tương ứng.

**2. Gọi `start()`/`stop()` thủ công trên container do extension quản lý.** Tạo hai owner và có thể stop sớm.

**3. Nghĩ static là một container cho cả JVM.** Nó class-scoped theo extension; những test classes khác không tự chia sẻ nó.

**4. Nghĩ static container reset DB mỗi method.** Không; transaction/fixture/cleanup cần thiết.

**5. Nghĩ instance container không phải trả startup overhead.** Mỗi test method có thể start một PostgreSQL mới.

**6. Dùng `@TestInstance(PER_CLASS)` để thay đổi scope @Container.** Không hiệu quả như vậy.

**7. Không xác nhận mapped port.** Testcontainers cấp host port động; đừng hardcode localhost:5432.

**8. Dùng `@ServiceConnection` nhưng thiếu Boot testcontainers dependency.** Connection details có thể không được cung cấp.

**9. `@ServiceConnection` bị datasource replacement che mất.** Dùng `@AutoConfigureTestDatabase(replace=NONE)` nếu test phải chạy trên PostgreSQL.

**10. Dùng @DynamicPropertySource instance method.** Phải static và đăng ký suppliers đúng.

**11. Container chạy nhưng test không có schema/migrations.** `isRunning()` không chứng minh DB contract.

**12. Mock `JdbcTemplate` trong test cần xác minh SQL.** Không còn thực thi DB và mất ý nghĩa Testcontainers.

**13. Static container bị stop khi Spring context vẫn cache.** Chạy cả suite để phát hiện; cân nhắc context-managed bean.

**14. Dùng instance container với Spring context cache không giải quyết URL/port đổi sau mỗi method.** Phải chọn lifecycle tương thích.

**15. Tin rằng rollback dọn mọi HTTP/@Async side effect.** Cross-thread/transaction riêng cần cleanup riêng.

**16. Chạy parallel trên shared mutable DB không điều phối.** Có thể phá data/DDL và gây flakiness.

**17. Dùng @DirtiesContext để xóa dữ liệu committed.** Nó quản lý context chứ không tự clear external DB.

**18. Bật reusable containers trên CI theo mặc định.** Có thể rò state giữa các runs.

**19. Lấy thứ tự khai báo hai @Container làm startup order contract.** Dependency phải cấu hình tường minh.

**20. Chỉ chạy Java demo rồi tuyên bố integration Docker đã pass.** Demo là mô phỏng scope; cần thực chạy JUnit/Docker.

## 24. Checklist QA trước khi kết luận

**Scope và ownership:**

- Có `@Testcontainers` hoặc `@ExtendWith(TestcontainersExtension.class)`?
- `@Container` field là static hay instance? Có đúng isolation/performance cần thiết?
- Có tránh manual start/stop nếu JUnit extension là owner?
- Lifecycle của container có dài đủ cho worker, Spring context và connection pool không?
- Các callbacks `@BeforeAll/@BeforeEach/@AfterEach/@AfterAll` có được gọi khi resource đang sống không?

**Spring Boot connection:**

- Đã chọn `@ServiceConnection` hoặc `@DynamicPropertySource` có chủ đích?
- Boot có `spring-boot-testcontainers` và Testcontainers module/driver đúng version?
- Khi test PostgreSQL, có `Replace.NONE` hoặc cấu hình ngăn embedded replacement?
- Non-embedded DB có schema.sql/init mode hoặc migration phù hợp?
- Với context cache, có nguy cơ container JUnit class bị stop trước cached context không?
- Container bean từ `@TestConfiguration` có được import và sống theo context khi cần?
- Test có assert JDBC query thật thay vì chỉ `isRunning()`?

**Dữ liệu/CI:**

- Mỗi method có fixture riêng, không phụ thuộc thứ tự chạy?
- Có biết writes nào rollback và writes nào commit?
- Có cleanup row sau commit, không xóa data của test khác?
- Docker host và mapped port được lấy từ APIs thay vì hardcode?
- Readiness, timeout, image version, Docker resources được kiểm soát?
- CI thiếu Docker fail hoặc skip theo chính sách, không gây xanh giả?
- Parallel execution/reusable container có nguy cơ contamination không?
- Đã chạy cả individual classes và full suite để phát hiện context/cache issues?

**Kết luận:** trong Testcontainers JUnit Jupiter, `@Testcontainers` bật extension và `@Container` đánh dấu tài nguyên Docker cần quản lý. **Static field → một vòng container cho class; instance field → một vòng cho method.** Đó là *vòng đời hạ tầng*, không phải transaction rollback, data cleanup hay quyền sở hữu Spring context. Trong Spring Boot, `@ServiceConnection` nối container với datasource; khi tái dùng context giữa nhiều classes, container bean theo context có thể tránh stale connections. Hãy chọn phạm vi container theo **isolation + tốc độ + context lifecycle + CI**, và chỉ kết luận các assertions thực sự được chạy.

## 25. Tài liệu tham khảo

- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container` và static/instance lifecycle.
- [Testcontainers Java — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): `PostgreSQLContainer`, JDBC URL và Docker image.
- [Testcontainers Java — Manual Lifecycle Control](https://java.testcontainers.org/test_framework_integration/manual_lifecycle_control/): singleton/manual start/stop patterns.
- [Testcontainers Java — Reusable Containers](https://java.testcontainers.org/features/reuse/): reuse và các hạn chế CI.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): service connections và container beans.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): JDBC test slice và database replacement.
- [Spring Framework 6.2 — Context Cache](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): cached contexts và vòng đời resource.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback boundaries và các side effects ngoài transaction.

# Chọn slice hoặc full context để kiểm chứng cấu hình DataSource thực tế

## Mục tiêu học tập

Trong một bài kiểm thử JDBC/Spring Boot, việc `DataSource` tồn tại và truy vấn `SELECT 1` chạy thành công **chưa đủ** để khẳng định ứng dụng kết nối đúng database và đúng connection pool. Đặc biệt, `@JdbcTest` và `@DataJpaTest` có cơ chế tạo hoặc thay thế DataSource để phục vụ test slice. Trong Spring Boot 3.3, cơ chế đó thường chọn embedded database, ngay cả khi test properties đang khai báo một JDBC URL khác.

Bài thuộc nhánh **JDBC và dữ liệu SQL** của module **Spring Boot – testing**, tập trung vào một quyết định thực tế: **khi nào chọn test slice, khi nào chọn full ApplicationContext và phải thu thập bằng chứng gì để xác minh DataSource đang được sử dụng thật**.

Sau bài này, bạn có thể:

- Phân biệt `@JdbcTest`, `@DataJpaTest`, `@DataJdbcTest` và `@SpringBootTest`.
- Giải thích lý do `@JdbcTest` có thể dùng H2 thay vì database được khai báo trong properties.
- Chọn chính sách `@AutoConfigureTestDatabase` với `Replace.ANY`, `AUTO_CONFIGURED`, `NONE` và hiểu sự khác biệt từ Spring Boot 3.4 với `NON_TEST`.
- Phân biệt ba lớp thông tin: **Environment property → DataSource bean → JDBC Connection runtime**.
- Kiểm metadata database thực tế bằng `Connection.getMetaData()`, loại DataSource và Hikari pool configuration.
- Viết project Java 17/Spring Boot 3.3.5/Gradle có ba nhóm test: slice thay DataSource, slice giữ DataSource và full context với HikariCP.
- Biết cách dùng Testcontainers/PostgreSQL khi câu hỏi liên quan database engine production, migration hoặc native SQL.
- Xử lý tình huống custom DataSource, nhiều DataSources, `@Primary`, routing, test profiles và cấu hình động.
- Tránh kết nối production, lộ secrets hoặc tạo dữ liệu khó dọn khi chạy test trên CI.

**Ý chính:** Nếu muốn chứng minh ứng dụng đang kết nối đến một DB nào đó, **đừng chỉ assert `spring.datasource.url`**. Hãy mở `Connection` từ **chính DataSource ứng dụng dùng**, xem JDBC metadata, và chạy SQL/schema check phù hợp.

## 1. DataSource thực sự là gì?

`javax.sql.DataSource` là interface dùng để cấp các kết nối JDBC. Trong ứng dụng Spring Boot, Bean DataSource có thể là:

- `HikariDataSource` do Boot tự cấu hình từ `spring.datasource.*` và `spring.datasource.hikari.*`.
- Embedded DataSource của H2, HSQLDB hoặc Derby.
- Một Bean tự viết bằng `@Bean DataSource`.
- `LazyConnectionDataSourceProxy` hay `TransactionAwareDataSourceProxy`.
- `AbstractRoutingDataSource` điều hướng theo tenant, vai trò read/write hoặc thread context.
- Nhiều DataSources: orders, audit, reporting, read replica.
- DataSource được tạo nhờ Testcontainers connection details hoặc một source secrets bên ngoài.

Một ví dụ properties:

~~~properties
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/shop
spring.datasource.username=shop_app
spring.datasource.password=...
spring.datasource.hikari.maximum-pool-size=12
~~~

**Đây là cấu hình minh họa, không phải cấu hình runnable của bài.** Không chép mật khẩu production vào test. Việc file này tồn tại hoặc `Environment` đọc được nó không bảo đảm DataSource được inject thực sự kết nối đến URL đó.

Luồng cấu hình:

~~~text
application.yml / application-test.yml / environment variables
             |
             v
 Spring Environment, configuration properties
             |
             v
 DataSourceAutoConfiguration / @Bean tự định nghĩa
             |
             +---- test database replacement (nếu được bật)
             |
             v
 DataSource bean: Hikari / embedded / custom / proxy
             |
             v
 dataSource.getConnection()
             |
             v
 JDBC Driver + Server/Database thực tế
             |
             +-- Connection.getMetaData().getURL()
             +-- Connection.getMetaData().getDatabaseProductName()
             +-- SQL kiểm schema / database-specific behavior
~~~

Ba tầng quan sát:

| Tầng | Cách kiểm | Điều nó chứng minh |
| --- | --- | --- |
| Giá trị khai báo | `environment.getProperty("spring.datasource.url")` | Giá trị property trong Environment |
| Bean được inject | `DataSource` type, Hikari pool properties, qualifiers | Wiring/loại pool nếu không có wrapper |
| Kết nối thật | `Connection.getMetaData()` và SQL thực thi | Engine/URL/schema/behavior tại lúc kết nối |

Nếu chỉ kiểm tầng đầu, bạn có thể bỏ sót **embedded replacement**. Nếu chỉ kiểm loại pool, bạn vẫn chưa biết nó kết nối đúng địa chỉ. Nếu chỉ kiểm `SELECT 1`, bạn chưa biết schema/migration hay tenant routing đã đúng.

## 2. Chọn test slice hay full context

Test slice cố ý bootstrap một phần nhỏ của ứng dụng để giảm startup cost và cô lập tầng đang kiểm. Full context nạp app configuration rộng hơn và có thể kéo theo integrations không liên quan.

| Annotation | Phạm vi chính | DataSource behavior |
| --- | --- | --- |
| `@JdbcTest` | JDBC infrastructure, `JdbcTemplate`, SQL | Có test database auto-configuration/replacement, thường dùng embedded DB |
| `@DataJpaTest` | Entity, Spring Data JPA repository, Hibernate, `TestEntityManager` | Thường dùng embedded DB; mặc định transactional/rollback |
| `@DataJdbcTest` | Spring Data JDBC repositories | Có cơ chế DB test tương tự |
| `@JooqTest` | jOOQ/`DSLContext` | Kiểm annotation và auto-config theo phiên bản thực |
| `@WebMvcTest` | MVC controller và request binding | Không dùng để chứng minh connection pool/JDBC |
| `@SpringBootTest` | Spring application configuration đầy đủ hơn | Không mặc định dùng replacement policy của JDBC/JPA slice |
| JUnit unit test thuần | Java logic | Không cần Spring context/DataSource |

### Khi dùng `@JdbcTest`

- Bạn muốn chứng minh một query qua `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` trả dữ liệu đúng.
- Bạn đang kiểm RowMapper, JDBC exception translation, SQL chuẩn.
- Không cần nạp toàn bộ web server, security, messaging, caches hoặc business services.
- Bạn chấp nhận embedded DB vì SQL/query behavior không phụ thuộc engine đặc thù, **hoặc** bạn chủ động giữ Testcontainers DataSource bằng `Replace.NONE`.

### Khi dùng `@DataJpaTest`

- Bạn muốn kiểm repository method, entity mapping, JPQL, transaction và Hibernate behavior.
- Bạn có entity fixture, cần `EntityManager` hoặc `TestEntityManager`.
- Bạn hiểu persistence context/flush/clear và rollback của test slice.
- Nếu SQL native/migrations dùng PostgreSQL, bạn có test trên đúng engine thay vì chỉ H2.

### Khi dùng `@SpringBootTest`

- Bạn cần biết application `@Configuration` thật có nạp custom DataSource không.
- Bạn muốn kiểm `@Primary`, `@Qualifier`, custom routing, connection pool properties hoặc transaction manager toàn ứng dụng.
- Bạn muốn bảo vệ việc kết hợp config/profile/connection details/migrations.
- Bạn cần kiểm một luồng tích hợp nhiều lớp, dù sẽ tốn thời gian khởi tạo hơn.

**Không cần mở HTTP port chỉ để kiểm DataSource.** `@SpringBootTest(webEnvironment = NONE)` vẫn tải full Spring ApplicationContext dạng non-web. Dùng `RANDOM_PORT` chỉ khi mục tiêu bao gồm HTTP server/network/transaction server-side.

## 3. Vì sao test slice có thể đổi database?

Trong Spring Boot 3.3, `@JdbcTest` và `@DataJpaTest` tích hợp `@AutoConfigureTestDatabase` để tránh dùng nhầm database ứng dụng khi chỉ cần kiểm thử data layer. Khi có driver H2/HSQLDB/Derby, Spring Boot có thể tạo embedded DB dùng cho test và thay DataSource vốn được cấu hình.

Ví dụ:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/order_test
~~~

~~~java
@JdbcTest
class OrderJdbcTest {
    // ...
}
~~~

Đây là hai đoạn minh họa, không phải project chạy độc lập. Với Boot 3.3 và embedded driver có sẵn, DataSource trong `OrderJdbcTest` **có thể là H2**, không phải PostgreSQL. Kết quả `Environment.getProperty(...)` vẫn có thể là PostgreSQL URL, trong khi JDBC metadata lấy từ connection lại ghi `H2`.

### Các chính sách `Replace` của Spring Boot 3.3

~~~java
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.ANY)
~~~

| Policy | Ý nghĩa |
| --- | --- |
| `ANY` | Cho phép thay DataSource bất kể nó auto-configured hay manually defined; **default của Boot 3.3** |
| `AUTO_CONFIGURED` | Chỉ thay DataSource do Spring Boot auto-configuration tạo |
| `NONE` | **Không thay** DataSource đã cấu hình |
| `NON_TEST` | **Không tồn tại ở Boot 3.3**; được bổ sung từ Boot 3.4 |

Từ **Spring Boot 3.4+**, `Replace.NON_TEST` được thêm và trở thành default mới, giúp giữ nhiều auto-configured DataSource mà Boot nhận diện được là **test DB** (ví dụ metadata Testcontainers, `@DynamicPropertySource`, `jdbc:tc` theo điều kiện của phiên bản). Không viết `Replace.NON_TEST` trong project dùng Boot 3.3 vì sẽ không compile.

Khi requirement là **“không đổi DataSource mà test đã chọn”**, `Replace.NONE` diễn đạt intent rõ ràng trong cả 3.3 và các bản mới hơn. Tuy nhiên nó **không** xác nhận DB an toàn: nếu URL hiện tại chỉ production, test có thể kết nối production thật.

### `connection = H2` khác `replace = NONE`

~~~java
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2)
~~~

- `replace` kiểm **có thay DataSource hay không**.
- `connection` kiểm **khi thay thì chọn embedded engine nào**.
- `EmbeddedDatabaseConnection.NONE` nghĩa không ép engine cụ thể, **không đồng nghĩa `Replace.NONE`**.
- Muốn dùng H2 khi replacement, phải có H2 JDBC driver trên test runtime classpath.
- Không có embedded driver mà vẫn yêu cầu embedded replacement có thể khiến context startup fail.

Trong môi trường nhiều DataSources, cơ chế test database replacement theo Javadoc Spring Boot 3.3 chỉ **xét `@Primary DataSource`**, không phải thay mọi datasource bean. Vậy một application có audit datasource riêng cần test và bảo vệ riêng, không dựa vào một slice test để khẳng định tất cả đều an toàn.

## 4. Thiết kế bằng chứng theo mục tiêu

Trước khi code, viết rõ câu hỏi muốn trả lời:

| Câu hỏi | Bằng chứng tối thiểu |
| --- | --- |
| DataSource có được tạo không? | `@Autowired DataSource` và mở connection |
| DB có phải H2/PostgreSQL? | `DatabaseMetaData.getDatabaseProductName()` |
| Đúng database name/URL? | `DatabaseMetaData.getURL()` sau khi sanitize |
| Test replacement đã thay URL? | So sánh configured URL và runtime URL |
| Hikari property đã bind? | Kiểm bean Hikari thật `getMaximumPoolSize()` |
| `JdbcTemplate` có dùng được connection? | SQL query có expected độc lập |
| Có đúng schema/migrations? | Query table/version migration/constraints thực sự |
| Custom service/config có được nạp? | Kiểm bean presence/config behavior trong full context |
| Có nhiều DataSources? | Inject từng bean qua `@Qualifier`, metadata từng connection |
| Test đang dùng đúng container DB? | Assert product name + runtime URL + vendor-specific behavior |

Một test chỉ `assertNotNull(dataSource)` hoặc `SELECT 1` có thể pass trong hầu hết DB. Nó là smoke check, **không thay** được validation cần thiết.

## 5. Project runnable Java 17 + Spring Boot 3.3.5

Ví dụ dùng H2 in-memory để chạy được **không cần Docker, database server hay dịch vụ bên ngoài**. Ta cố ý tạo ba context:

1. **JDBC slice thay DB:** cấu hình URL `configured_slice`, nhưng `Replace.ANY` buộc embedded replacement.
2. **JDBC slice giữ DB:** cấu hình URL `kept_slice` và `Replace.NONE`.
3. **Full context:** dùng URL `full_context_db`, Hikari pool size 3 và nạp `@Service` ứng dụng thật.

Sau đó so sánh JDBC metadata của từng context. **Cả ba database đều là H2**, giúp cô lập đúng cơ chế replacement và scope. Một phần tiếp theo mở rộng sang PostgreSQL Testcontainers để kiểm engine thật.

### 5.1. Cấu trúc file

~~~text
datasource-test-scope/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/datasource/
    │   ├── DataSourceApplication.java
    │   └── ApplicationMarker.java
    └── test/java/com/example/datasource/
        ├── JdbcSliceReplacementTest.java
        ├── JdbcSlicePreservationTest.java
        └── FullContextDataSourceTest.java
~~~

Gradle Wrapper là tập hợp scripts và một JAR nhị phân, cần được tạo từ Gradle phù hợp hoặc lấy từ repo. Đừng tự soạn `gradle-wrapper.jar` như file text.

**`settings.gradle`**

~~~groovy
rootProject.name = 'datasource-test-scope'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Giải thích:

- `spring-boot-starter-jdbc` mang JDBC infrastructure, `JdbcTemplate`, transaction hỗ trợ và HikariCP trong cấu hình mặc định.
- H2 nằm ở `testRuntimeOnly`; không đưa embedded driver vào production runtime module demo.
- `spring-boot-starter-test` mang JUnit Jupiter/Spring TestContext và test slices.
- Spring Boot BOM quản lý versions H2/JUnit/JDBC tương thích.
- `useJUnitPlatform()` giúp Gradle chạy JUnit Jupiter.

**`src/main/java/com/example/datasource/DataSourceApplication.java`**

~~~java
package com.example.datasource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DataSourceApplication {

    public static void main(String[] args) {
        SpringApplication.run(DataSourceApplication.class, args);
    }
}
~~~

Đây là root configuration của app. Project không có production DataSource URL/driver để chạy `bootRun` như một triển khai thật; **task được thiết kế để chạy là `test`** với H2 trên test classpath.

**`src/main/java/com/example/datasource/ApplicationMarker.java`**

~~~java
package com.example.datasource;

import org.springframework.stereotype.Service;

@Service
public class ApplicationMarker {

    public String identity() {
        return "full-application";
    }
}
~~~

`ApplicationMarker` là một service đơn giản, không chạm DB. Nó được dùng để chứng minh **component scan**: JDBC slice không nạp service thông thường, trong khi full application context có nó.

## 6. Test A — `@JdbcTest` thay DataSource

**`src/test/java/com/example/datasource/JdbcSliceReplacementTest.java`**

~~~java
package com.example.datasource;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
    "spring.datasource.url="
        + "jdbc:h2:mem:configured_slice;DB_CLOSE_DELAY=-1"
})
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2)
class JdbcSliceReplacementTest {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private Environment environment;

    @Autowired
    private ApplicationContext context;

    @Test
    void declaredUrlDiffersFromEffectiveConnection()
            throws SQLException {

        String declared = environment.getProperty(
                "spring.datasource.url");

        assertEquals(
                "jdbc:h2:mem:configured_slice;DB_CLOSE_DELAY=-1",
                declared);

        try (Connection connection = dataSource.getConnection()) {
            String actual = connection.getMetaData().getURL();

            assertTrue(actual.startsWith("jdbc:h2:mem:"), actual);
            assertFalse(actual.contains("configured_slice"), actual);
            assertEquals(
                    "H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void replacementDataSourceRunsSql() {
        Integer result = jdbcTemplate.queryForObject(
                "SELECT 2 + 3", Integer.class);

        assertNotNull(result);
        assertEquals(5, result.intValue());
    }

    @Test
    void unrelatedServiceIsExcludedFromJdbcSlice() {
        assertTrue(
                context.getBeansOfType(ApplicationMarker.class)
                        .isEmpty());
    }
}
~~~

**Điều test A chứng minh:**

1. `Environment` vẫn báo URL khai báo `configured_slice`.
2. JDBC metadata của **DataSource thực tế** bắt đầu bằng `jdbc:h2:mem:` nhưng **không chứa** `configured_slice`.
3. Engine của connection thực là H2.
4. `JdbcTemplate` chạy SQL trên connection đang được inject.
5. Service ứng dụng ngoài phạm vi JDBC slice không tự được scan.

Tên embedded DB được Spring tạo có thể thay đổi, nên **không hardcode** tên database generated. Assertion chỉ kiểm thuộc tính quan trọng: nó **không phải database được khai báo ban đầu**.

Nếu đổi `Replace.ANY` thành `Replace.NONE`, test đầu phải fail ở `assertFalse(actual.contains("configured_slice"))`, vì runtime sẽ giữ URL cấu hình. Đây là một phép mutation test có giá trị: chứng minh assertions thực sự phát hiện chính sách đổi DataSource.

## 7. Test B — `@JdbcTest` giữ DataSource

**`src/test/java/com/example/datasource/JdbcSlicePreservationTest.java`**

~~~java
package com.example.datasource;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JdbcTest(properties = {
    "spring.datasource.url="
        + "jdbc:h2:mem:kept_slice;DB_CLOSE_DELAY=-1"
})
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
class JdbcSlicePreservationTest {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void effectiveUrlMatchesConfiguredTestDatabase()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            String actual = connection.getMetaData().getURL();

            assertTrue(
                    actual.startsWith("jdbc:h2:mem:kept_slice"),
                    actual);
            assertEquals(
                    "H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void keptDataSourceStillExecutesSql() {
        Integer result = jdbcTemplate.queryForObject(
                "SELECT 4 + 5", Integer.class);

        assertNotNull(result);
        assertEquals(9, result.intValue());
    }
}
~~~

**Điểm khác biệt với test A:**

- `Replace.NONE` ngăn **test database replacement**, không biến H2 thành PostgreSQL.
- Test vẫn dùng H2 vì **chính properties đã khai báo H2**.
- URL JDBC runtime giữ tên `kept_slice`.
- Dù không replace, test vẫn là JDBC slice: các application services không tự xuất hiện vì `NONE` không thay component scan.

Bẫy thường gặp: Có người đọc “NONE” và hiểu “không dùng database nhúng”. Thực chất `NONE` chỉ quyết định **không thay DataSource**; nếu DataSource đã cấu hình là H2 thì kết quả vẫn là H2.

## 8. Test C — `@SpringBootTest` kiểm full application context

**`src/test/java/com/example/datasource/FullContextDataSourceTest.java`**

~~~java
package com.example.datasource;

import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = DataSourceApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.datasource.url="
            + "jdbc:h2:mem:full_context_db;DB_CLOSE_DELAY=-1",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.datasource.hikari.maximum-pool-size=3"
    })
class FullContextDataSourceTest {

    @Autowired
    private DataSource dataSource;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    private ApplicationMarker marker;

    @Test
    void effectiveUrlMatchesFullContextConfig()
            throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            String actual = connection.getMetaData().getURL();

            assertTrue(
                    actual.startsWith("jdbc:h2:mem:full_context_db"),
                    actual);
            assertEquals(
                    "H2",
                    connection.getMetaData().getDatabaseProductName());
        }
    }

    @Test
    void hikariPropertyIsAppliedToActualPoolBean() {
        HikariDataSource pool =
                assertInstanceOf(HikariDataSource.class, dataSource);

        assertEquals(3, pool.getMaximumPoolSize());
    }

    @Test
    void applicationServiceIsLoadedInFullContext() {
        assertEquals("full-application", marker.identity());
    }

    @Test
    void jdbcTemplateCanExecuteAgainstFullContextDataSource() {
        Integer result = jdbcTemplate.queryForObject(
                "SELECT 7 + 8", Integer.class);

        assertNotNull(result);
        assertEquals(15, result.intValue());
    }
}
~~~

**Điều test C chứng minh:**

- App `@SpringBootApplication` đã tải full non-web ApplicationContext.
- `DataSource` dùng chính URL H2 `full_context_db`.
- HikariCP là bean thật trong **project demo** (starter-jdbc và không có custom bean).
- Cấu hình `spring.datasource.hikari.maximum-pool-size=3` được áp dụng.
- `ApplicationMarker` được component scan vào full context.
- `JdbcTemplate` thực thi SQL được.

Không phải mọi ứng dụng dùng `@SpringBootTest` đều có `HikariDataSource` trực tiếp: custom DataSource, proxy, routing hoặc pool khác có thể khiến assertion `instanceof` không phù hợp. Ở đây ta dùng nó vì **mục tiêu bài là kiểm chính Hikari binding trong cấu hình mặc định của demo**.

### Vì sao dùng `webEnvironment = NONE`?

Ta không kiểm HTTP endpoint. `SpringBootTest.WebEnvironment.NONE` nạp các bean config của ứng dụng mà không chạy web server. Để kiểm HTTP + JDBC transaction commit sau POST/GET, dùng `RANDOM_PORT` và HTTP client, kèm cleanup rõ ràng vì server thread có transaction khác test thread.

## 9. Thực thi bộ test và kết quả mong đợi

| Class | Test methods | Mục tiêu |
| --- | ---: | --- |
| `JdbcSliceReplacementTest` | 3 | Property khác runtime DB, embedded SQL, slice scope |
| `JdbcSlicePreservationTest` | 2 | URL được giữ và JDBC query hoạt động |
| `FullContextDataSourceTest` | 4 | Full app wiring, URL thực, Hikari settings, service |
| **Tổng** | **9** | Ba context riêng |

Trong thư mục có Gradle Wrapper và JDK 17:

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy từng class:

~~~bash
./gradlew test --tests 'com.example.datasource.JdbcSliceReplacementTest'
./gradlew test --tests 'com.example.datasource.JdbcSlicePreservationTest'
./gradlew test --tests 'com.example.datasource.FullContextDataSourceTest'
~~~

**Kỳ vọng 9 lượt JUnit test pass** khi source và dependencies đúng. Đây là kết quả dự kiến từ mã, không phải kết quả đã chạy trên máy người học. Không có `System.out.println`, nên không có stdout nghiệp vụ cố định; Gradle có thể báo `BUILD SUCCESSFUL` hoặc dùng lại test task cache.

Nếu cần buộc chạy lại:

~~~bash
./gradlew test --rerun-tasks
~~~

Báo cáo JUnit thông thường:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.datasource.JdbcSliceReplacementTest.xml
    ├── TEST-com.example.datasource.JdbcSlicePreservationTest.xml
    └── TEST-com.example.datasource.FullContextDataSourceTest.xml
~~~

Khi chưa có Wrapper, một Gradle đã cài đặt và tương thích có thể tạo:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó commit `gradlew`, `gradlew.bat`, Wrapper properties và Wrapper JAR theo quy định. Với project hiện hữu, ưu tiên Gradle Wrapper của team, không tự đổi version theo bài học.

### Bảng tổng kết runtime dự kiến

~~~text
JdbcSliceReplacementTest
  Environment URL: jdbc:h2:mem:configured_slice;...
  Replace.ANY + EmbeddedDatabaseConnection.H2
  Runtime URL:     jdbc:h2:mem:<generated-name>...
  Runtime Engine:  H2
  ApplicationMarker bean: absent

JdbcSlicePreservationTest
  Environment URL: jdbc:h2:mem:kept_slice;...
  Replace.NONE
  Runtime URL:     jdbc:h2:mem:kept_slice;...
  Runtime Engine:  H2

FullContextDataSourceTest
  Environment URL: jdbc:h2:mem:full_context_db;...
  Full app context, no slice replacement
  Runtime URL:     jdbc:h2:mem:full_context_db;...
  Runtime Engine:  H2
  DataSource type: HikariDataSource (in this project)
  Hikari maxPool:  3
  ApplicationMarker bean: present
~~~

Tên `<generated-name>` là placeholder **giải thích mô hình output**, không phải tên database được hardcode trong test và không phải stdout cố định.

## 10. Tại sao chỉ đọc `Environment` dễ cho cảm giác đúng giả?

Trong thực tế, test properties có thể do nhiều nguồn cùng tác động:

- `application.yml` và `application-test.yml`.
- `@ActiveProfiles("test")`.
- Inline test properties trong `@SpringBootTest`/`@JdbcTest`.
- `@TestPropertySource`.
- Environment variables, system properties, command-line options.
- `@DynamicPropertySource` từ Testcontainers.
- `@ServiceConnection` connection details từ container.
- Custom bean sử dụng prefix khác `spring.datasource`.
- `@AutoConfigureTestDatabase` thay bean khi test bootstrap.

Ví dụ:

~~~java
@ActiveProfiles("test")
@SpringBootTest
class DatabaseSmokeTest {
    // ...
}
~~~

Đây là snippet minh họa. Profile `test` giúp nạp cấu hình test nhưng **không bảo đảm URL an toàn hoặc DataSource đang dùng đúng file**. Nếu custom DataSource lấy URL từ nguồn khác, hoặc slice replacement diễn ra, giá trị trong một file `application-test.yml` không đủ.

Một số test viết:

~~~java
assertEquals(
    "jdbc:postgresql://localhost:5432/shop_test",
    environment.getProperty("spring.datasource.url"));
~~~

Test có thể xanh ngay cả khi DataSource thực tế đã được thay sang H2. Cần kết hợp:

~~~java
try (Connection connection = dataSource.getConnection()) {
    assertEquals(
        "PostgreSQL",
        connection.getMetaData().getDatabaseProductName());
}
~~~

Đoạn này là snippet với `dataSource`/imports đã có, dùng trong context được cấu hình an toàn. Nếu contract còn yêu cầu schema cụ thể, kiểm thêm SQL thực tế trên schema ấy.

### `DataSourceProperties` cũng không phải bằng chứng cuối cùng

`DataSourceProperties` chứa thông tin binding/inference để tạo datasource, nhưng không phải mọi custom bean/wrapper đều bắt buộc dùng nó. Việc một property object có URL đúng **không chứng minh** connection của repository/JdbcTemplate đi tới URL đó.

Đường kiểm đáng tin là:

1. Xác định DataSource bean mà component cần kiểm sử dụng.
2. Mở connection từ chính bean đó.
3. Kiểm engine, URL/schema/catalog theo ràng buộc hợp đồng.
4. Thực thi SQL có ý nghĩa.
5. Đóng connection, không log secrets.

## 11. Kiểm connection metadata an toàn

Một helper dùng trong test có thể trông như sau:

~~~java
private void assertDatabaseEngine(
        DataSource dataSource, String expected)
        throws SQLException {

    try (Connection connection = dataSource.getConnection()) {
        assertEquals(
                expected,
                connection.getMetaData().getDatabaseProductName());
    }
}
~~~

Đây là snippet method trong test class, cần imports JUnit và JDBC. `getDatabaseProductName()` xác nhận engine mà JDBC driver báo. `getURL()` cho biết JDBC URL theo metadata; đôi khi có query parameters hoặc endpoint nội bộ nên cần **sanitization** trước khi log ra CI.

### Khi kiểm database/schema quan trọng hơn URL

Với PostgreSQL, trong một context test chuyên biệt:

~~~sql
SELECT current_database(), current_schema()
~~~

Với MySQL, có các function tương ứng theo dialect. Đây là SQL minh họa, **không chạy trong H2 project demo**. Chỉ dùng trong test biết rõ engine/driver. Một connection qua proxy/load balancer có thể trả URL tới proxy, không tiết lộ instance backend; database/schema result và bảng migrations có thể là bằng chứng hữu ích hơn.

### Phân biệt các thuộc tính pool với connection

- `HikariDataSource.getMaximumPoolSize()` kiểm pool setting của bean Hikari.
- `Connection.getMetaData()` kiểm metadata kết nối tới DB.
- `Connection.isReadOnly()` phản ánh trạng thái read-only của một connection, không tự bảo đảm database replica/transaction isolation.
- `DataSource.getLoginTimeout()` không chứng minh SQL query timeout hoặc network socket behavior.
- `JdbcTemplate.queryForObject(...)` kiểm query thực thi, không tự xác minh mọi bảng/migration.

Chọn assertion theo mục tiêu, tránh một bài test khổng lồ kiểm tất cả mà không biết lỗi thuộc tầng nào.

## 12. Testcontainers khi cần database engine thật

Demo H2 không kiểm native SQL hoặc driver behavior của PostgreSQL. Khi cần:

- `jsonb`, array, enum, UUID, `ILIKE`, `ON CONFLICT`, `RETURNING`.
- Transaction isolation/locking hoặc collation đặc thù.
- Flyway/Liquibase migrations của PostgreSQL/MySQL.
- Native SQL cùng index/constraint thật.
- Connection pool behavior với PostgreSQL JDBC driver.

hãy dùng **PostgreSQL Testcontainers** hoặc một DB test tương đương.

### Dependencies bổ sung trong Boot 3.3

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
~~~

Đây là **snippet thêm vào project đã có Spring Boot/JDBC**, không phải build độc lập. Cần Docker/container runtime tương thích và Postgres image được phép chạy trên CI.

### `@JdbcTest` với container: cần giữ DataSource trên Boot 3.3

~~~java
@JdbcTest
@Testcontainers
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE)
class PostgresJdbcSliceTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private DataSource dataSource;

    @Test
    void confirmsPostgresNotAccidentalH2() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            assertEquals(
                    "PostgreSQL",
                    connection.getMetaData().getDatabaseProductName());
        }
    }
}
~~~

**Snippet này không phải class độc lập để compile**: cần thêm imports Spring Boot/JUnit/Testcontainers, dependencies và schema/fixture khi query nghiệp vụ. Nó minh họa yêu cầu cốt lõi: container được start, `@ServiceConnection` cấp connection details và `Replace.NONE` ngăn test slice thay Postgres bằng H2.

Trong Boot **3.3**, `Replace.NONE` có ý nghĩa đặc biệt quan trọng vì mặc định slice có thể `Replace.ANY`. Boot 3.4+ có `NON_TEST` nhận diện nhiều test databases, nhưng khi mục tiêu là **chắc chắn giữ container** thì `NONE` vẫn rõ.

### `@DynamicPropertySource` là một lựa chọn khác

~~~java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Đây là snippet dùng biến `postgres` đã khai báo. Với Boot 3.3 và `@JdbcTest`, kể cả Environment có JDBC URL động chính xác, **embedded replacement vẫn có thể xảy ra** nếu không dùng policy phù hợp. Không tự đồng thời dùng cả `@ServiceConnection` và dynamic properties cùng mục đích khi không cần thiết.

### Với full context

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Testcontainers
class PostgresFullContextTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    // @Autowired DataSource...
    // Assert PostgreSQL metadata, schema and migration.
}
~~~

Đây là snippet kiến trúc, cần full test class/config. `@SpringBootTest` thường không bật embedded replacement như slice, nhưng vẫn phải **đọc runtime connection** — một container được tạo ra không chứng minh custom DataSource của app đã sử dụng nó.

### Khi có migration

Một test `SELECT 1` trên PostgreSQL chỉ chứng minh driver/connection chạy. Nếu mục tiêu là “migrations sản xuất được áp dụng”, hãy chạy schema migration thật trên DB test và assert bảng/cột/constraint/version. Test dùng Hibernate `ddl-auto=create-drop` có thể xanh **dù migration SQL production sai**, nên không coi đó là migration verification.

## 13. Custom DataSource và `@Configuration` ngoài slice

Ví dụ application có custom configuration:

~~~java
@Configuration
class DbConfig {

    @Bean
    DataSource customizedDataSource() {
        // Tạo custom pool từ config riêng.
    }
}
~~~

Đây là snippet minh họa, không biên dịch độc lập. Một `@JdbcTest` có thể không scan config/bean này nếu nằm ngoài phạm vi được nạp, và `Replace.NONE` **không tự thêm bean** bị thiếu. Hai cách hợp lý:

- Dùng `@Import(DbConfig.class)` vào targeted test slice khi chỉ muốn kiểm JDBC cùng config đó.
- Dùng `@SpringBootTest(NONE)` khi muốn bảo vệ **wiring của ứng dụng thật**.

Khi import vào slice, bạn đã cố ý mở rộng context. Kết quả đó bảo vệ **context có import**, chưa chắc giống mọi component của production. Không coi nó là full context chỉ vì đã thêm một `@Configuration`.

### Nhiều DataSources: `@Primary`, `@Qualifier` và routing

~~~java
@Configuration
class MultiDbConfig {

    @Bean
    @Primary
    DataSource ordersDataSource() {
        // ...
    }

    @Bean
    DataSource auditDataSource() {
        // ...
    }
}
~~~

Snippet kiến trúc; cần thân hàm và imports để chạy. Khi ứng dụng có nhiều DataSource, `@Primary` giúp chọn candidate mặc định, còn `@Qualifier("auditDataSource")` hướng tới bean khác.

Nếu chỉ autowire `DataSource` và kiểm một connection, bạn thường mới thấy **primary path**. Các `JdbcTemplate` hoặc Spring Data repositories khác có thể dùng audit/reporting datasource qua qualifier hay transaction manager riêng.

Một test robust cần:

- Inject đúng datasource bean theo tên/qualifier.
- Mở connection và kiểm metadata cho **từng nguồn thực sự**.
- Kiểm DataSource được repository/JdbcTemplate cụ thể sử dụng, không chỉ bean có mặt.
- Nếu dùng `AbstractRoutingDataSource`, thiết lập tenant/route context đúng trước khi mở connection; test nhiều routes.
- Không giả định test database replacement thay **mọi** DataSource trong context.

### Proxy DataSource và Hikari

`LazyConnectionDataSourceProxy`, `TransactionAwareDataSourceProxy` hoặc routing wrapper không nhất thiết là `HikariDataSource` khi inject, dù pool bên dưới là Hikari. Vì vậy:

- Nếu yêu cầu là **đích kết nối**, dùng JDBC metadata/SQL.
- Nếu yêu cầu là **cấu hình pool**, truy cập đúng Hikari bean/target hoặc cơ chế unwrap được hỗ trợ.
- Nếu mục tiêu là **app transaction/routing**, kiểm behavior trong context đúng.

Trong project runnable, không có custom wrapper nên assert Hikari type trực tiếp là hợp lý và có giá trị.

## 14. Transaction trong slice và full context

`@JdbcTest` thường được cấu hình transactional và rollback DML sau mỗi method. `@DataJpaTest` có JPA persistence context và rollback mặc định. `@SpringBootTest` không tự làm mọi test transactional, còn các HTTP calls tới server thật được xử lý trên thread/transaction phía server.

| Trường hợp | Điều cần nhớ |
| --- | --- |
| JDBC slice gọi `jdbcTemplate.update` trong test thread | Thường tham gia test transaction và rollback |
| JPA slice `repository.save` | Có thể cần `flush/clear` để kiểm DB round-trip |
| Full context test gọi JDBC trực tiếp không `@Transactional` | DML có thể commit tùy auto-commit/transaction scope |
| `@SpringBootTest(RANDOM_PORT)` gửi HTTP POST | Server transaction có thể commit riêng; test rollback không xóa |
| DataSource metadata test | Chỉ cần mở/đóng connection, không phải ghi dữ liệu |
| Testcontainers shared across methods | Container không tự reset DB state giữa mỗi method |

**Đừng gắn `@Transactional` lên mọi test chỉ để “an toàn”**. Với HTTP real server, transaction trên JUnit thread không rollback dữ liệu server đã commit. Khi cần cleanup, dùng test marker/ID, rollback được hiểu đúng, transaction cleanup độc lập hoặc schema/container riêng.

### Vì sao test chỉ kiểm metadata không cần fixture?

Trong project mẫu, mọi SQL query là `SELECT 2+3`, `SELECT 4+5`, `SELECT 7+8`. Chúng không tạo bảng, không insert, không delete. Nhờ đó bộ test tập trung vào **cấu hình DataSource** và không cần chiến lược cleanup phức tạp.

Nếu muốn kiểm repository/schema, bổ sung fixture có mục đích và chọn mức test phù hợp, tránh biến test cấu hình thành nơi kiểm quá nhiều business logic.

## 15. Đảm bảo an toàn với database thật

`Replace.NONE` không phải một security boundary. Cần các biện pháp độc lập:

1. Database/container **dành riêng test**, không dùng credentials production.
2. CI network không có đường tới production DB khi không được cấp phép.
3. User test có quyền tối thiểu, đặc biệt với DDL/DELETE/TRUNCATE.
4. Assert runtime engine và test database/schema marker trước thao tác destructive.
5. Không in username/password/token hoặc full URL có secrets ra logs.
6. Không xóa bảng chung trong cleanup để “cho test sạch”.
7. Dùng testRunId/tenant schema/resource IDs khi suite chạy song song.
8. Có TTL/container teardown khi tiến trình test chết trước `@AfterEach`.
9. Khi `@SpringBootTest` mở toàn context, kiểm các integrations (email, billing, queue) đều dùng sandbox/fake.
10. Dùng credentials/test profiles được quản lý bởi CI secrets, không commit vào repository.

**H2 in-memory không giống production engine.** Nó là lựa chọn hợp lý cho SQL cơ bản và bài học replacement, nhưng native SQL/locking/collation/migration có thể khác PostgreSQL/MySQL. Khi mục tiêu yêu cầu engine thật, test trên engine tương ứng.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `@JdbcTest` dùng H2 dù URL trỏ PostgreSQL | Boot 3.3 replacement mặc định `ANY` | `Replace.NONE` và kiểm runtime connection |
| `spring.datasource.url` đúng nhưng query đi DB khác | Test replacement, custom bean hoặc routing | Kiểm JDBC metadata của đúng bean |
| `Failed to replace DataSource with an embedded database` | Thiếu embedded JDBC driver | Thêm H2/HSQLDB/Derby test runtime hoặc đổi policy |
| `Cannot determine a suitable driver class` | Driver/URL/connection details không đầy đủ | Kiểm test dependencies/properties |
| Custom DataSource không có trong `@JdbcTest` | Slice không scan config đó | `@Import` hoặc full context |
| `Replace.NONE` nhưng startup fail | Không có usable DataSource/driver | Cấu hình DataSource test thật, không chỉ annotation |
| Hikari type assertion fail trong slice | Embedded replacement tạo pool khác | Kiểm engine/URL thay vì Hikari khi đó là mục tiêu |
| `HikariDataSource` cast fail với full context | Proxy/routing/custom DataSource | Lấy đúng target pool hoặc kiểm metadata |
| Hikari pool size không khớp | Custom bean không bind prefix `hikari` | Kiểm nguồn bean và configuration prefix |
| Container PostgreSQL chạy nhưng app dùng H2 | Test slice replacement | `Replace.NONE` với Boot 3.3; assert product |
| Test H2 pass nhưng native SQL Postgres fail | Khác dialect/schema | Testcontainers PostgreSQL |
| `@ActiveProfiles("test")` vẫn trỏ DB sai | Property source/connection details khác | Kiểm effective connection, safety allowlist |
| Full context test fail do external service | Nạp toàn bộ bean/integrations | Dùng test-specific stubs hoặc slice |
| Test pool cạn connection | Quên đóng `Connection` | Try-with-resources |
| Test SQL pass nhưng schema migration fail | Chỉ query `SELECT 1` | Test migration/schema riêng |
| Rollback JUnit không xóa server row | HTTP server transaction riêng | Cleanup server-side committed data |
| Multiple DataSources, audit vẫn trỏ prod | Chỉ primary được replace/test | Kiểm mọi qualified/routed DataSources |
| `Replace.NON_TEST` không compile | Spring Boot 3.3 chưa có giá trị này | Dùng `NONE`/`ANY` phù hợp phiên bản |

### Quy trình debug

1. Xác định version Spring Boot và đúng annotation test.
2. Phân biệt yêu cầu: **query correctness, bean wiring, connection destination hay pool config**.
3. Kiểm `@AutoConfigureTestDatabase` và policy replacement.
4. Kiểm test runtime classpath có driver phù hợp.
5. Kiểm test URL/credentials an toàn trước khi mở connection.
6. Kiểm Bean DataSource actual (custom/primary/proxy/routing).
7. Mở connection đúng bean, assert metadata và SQL có ý nghĩa.
8. Nếu cần migrations, query schema/version table thực tế.
9. Kiểm transaction/rollback và cleanup khi có ghi DB.
10. Đọc root cause thật, không chỉ exception bọc `Failed to load ApplicationContext`.

## 17. Bài tập

**Bài A — Chứng minh replacement:** Chạy `JdbcSliceReplacementTest`, sau đó đổi `Replace.ANY` thành `Replace.NONE`. Dự đoán assertion `assertFalse(actual.contains("configured_slice"))` fail và giải thích vì sao.

**Bài B — Giữ URL:** Trong `JdbcSlicePreservationTest`, đổi URL từ `kept_slice` thành `another_slice` mà không đổi expected. Test phải fail. Hoàn nguyên.

**Bài C — Hikari binding:** Trong `FullContextDataSourceTest`, thay max pool size 3 thành 5, giữ assertion 3. Test phải fail, chứng minh test bắt được thay đổi cấu hình.

**Bài D — Slice scan:** Dùng `ApplicationMarker` để kiểm service vắng ở `@JdbcTest` nhưng có ở full context. Thử `@Import(ApplicationMarker.class)` vào một class slice mới và phân tích vì sao đây là context mở rộng có chủ đích.

**Bài E — Profile:** Tạo `application-test.yml` với một H2 URL riêng, kích hoạt `@ActiveProfiles("test")`, kiểm `Environment` và runtime URL. Thêm inline test properties để quan sát override.

**Bài F — PostgreSQL:** Dùng Testcontainers, `@JdbcTest` + `Replace.NONE` trên Boot 3.3. Assert PostgreSQL engine và một query Postgres-specific. Không dùng production DB.

**Bài G — Migration:** Tạo bảng bằng Flyway/Liquibase test migration và query bảng thật. Giải thích vì sao `SELECT 1`/metadata không chứng minh migration thành công.

**Bài H — Nhiều DataSources:** Tạo orders và audit DataSource với URL H2 khác nhau. Inject qua qualifier, kiểm metadata của từng connection; không tự cho rằng replacement áp dụng mọi bean.

**Bài I — Transaction:** Tạo JDBC slice test ghi/đọc trong test transaction; so với HTTP integration có server commit riêng. Xây dựng cleanup theo test ID thay vì `deleteAll()` khi dùng DB chia sẻ.

**Bài J — Connection leak:** Mở connection rồi quên đóng trong test riêng với pool nhỏ, quan sát timeout. Sửa bằng try-with-resources. Không thực hiện thí nghiệm gây quá tải trên DB production.

## 18. Checklist trước khi merge test DataSource

- [ ] Tôi đã chọn slice hoặc full context theo **mục tiêu cụ thể**, không theo thói quen?
- [ ] Tôi biết Spring Boot version và default replacement của test annotation?
- [ ] Tôi phân biệt `Replace.ANY`, `Replace.NONE`, `AUTO_CONFIGURED`, và `NON_TEST` chỉ từ Boot 3.4?
- [ ] Tôi không suy ra runtime DataSource chỉ từ `spring.datasource.url` trong `Environment`?
- [ ] Tôi kiểm JDBC metadata từ đúng DataSource/qualifier/route?
- [ ] Tôi kiểm engine/URL/schema theo contract và tránh log secrets?
- [ ] Nếu kiểm Hikari, tôi lấy đúng pool và assert setting thực tế?
- [ ] Nếu dùng Testcontainers, tôi xác nhận **app dùng container**, không chỉ container đang chạy?
- [ ] Với SQL vendor-specific, tôi chạy trên đúng database engine?
- [ ] Với migration, tôi kiểm schema thực, không chỉ kết nối?
- [ ] Tôi biết `@JdbcTest`/`@DataJpaTest` có thể không nạp service/config ngoài slice?
- [ ] Tôi không dùng `@DirtiesContext` để thay database cleanup?
- [ ] Connection được đóng, test không để pool leak?
- [ ] Test profile/credentials/network không thể vô tình truy cập production?
- [ ] Tôi đã xử lý test data/transaction cleanup nếu test có ghi dữ liệu?
- [ ] Report Gradle/JUnit cho thấy test methods thực thi, không nhầm cached task với run mới?

## 19. Nguồn tham khảo chính thức

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): test slices và `@SpringBootTest`.
- [Spring Boot 3.3 — AutoConfigureTestDatabase API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html): replacement, embedded connection, primary DataSource.
- [Spring Boot 3.3 — Replace API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): `ANY`, `AUTO_CONFIGURED`, `NONE`.
- [Spring Boot 3.4 — Replace API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.Replace.html): `NON_TEST` và các trường hợp test database.
- [Spring Boot 3.3 — SQL Databases](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html): DataSource, JdbcTemplate, Hikari, auto-configuration.
- [Spring Boot 3.3 — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): `@ServiceConnection` và connection details.
- [Spring Framework — TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback của test-managed transactions.
- [HikariCP Documentation](https://github.com/brettwooldridge/HikariCP): connection pool configuration.

**Ghi nhớ:** `@JdbcTest` kiểm JDBC nhanh nhưng có thể **thay DataSource** trong test context. `@SpringBootTest` kiểm cấu hình ứng dụng đầy đủ hơn nhưng không mặc định an toàn với DB thật. Hãy kiểm đúng **runtime connection**, đúng **database engine/schema**, và đúng **pool bean** khi chúng là một phần của hợp đồng. Chọn test nhỏ nhất đủ bằng chứng, rồi bổ sung full-context/Testcontainers tests cho integration wiring quan trọng.

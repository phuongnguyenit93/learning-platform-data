# Khởi tạo cơ sở dữ liệu thực bằng Testcontainers khi cần

## 1. Khi nào một bài kiểm thử cần database thật?

Một repository có thể chạy tốt trên H2 nhưng thất bại khi deploy PostgreSQL hoặc MySQL. Nguyên nhân là **database không chỉ là nơi lưu vài hàng dữ liệu**. Mỗi hệ quản trị có SQL dialect, kiểu dữ liệu, cách so sánh, xử lý NULL, index, locking, transaction isolation, DDL và các tính năng riêng.

Ví dụ, ứng dụng dùng PostgreSQL partial unique index:

~~~sql
CREATE UNIQUE INDEX ux_users_active_email
ON users (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
~~~

Một test dùng H2 có thể không hỗ trợ đúng cú pháp hoặc semantics của index này. Nếu test chỉ dùng H2, nó không chứng minh được production PostgreSQL sẽ chặn hai tài khoản active trùng email.

**Testcontainers** cho phép khởi chạy database thật trong container Docker dùng cho test, kết nối ứng dụng qua JDBC như một database bình thường, sau đó dừng và dọn container theo lifecycle của test.

Bài học thuộc chương **Kiểm thử**, module *Data Persistence Relational Access ORM Hibernate*. Trọng tâm là biết **khi nào cần database thật**, cách khởi tạo và quản lý container, tích hợp với Spring/JPA/Hibernate, và giữ test đáng tin cậy.

### 1.1. Mục tiêu

Sau bài học, bạn có thể:

1. Chọn giữa mock, H2 và database thật theo mục tiêu test.
2. Khởi chạy PostgreSQL/MySQL bằng Testcontainers với JUnit Jupiter.
3. Kết nối Spring Boot datasource qua `@ServiceConnection` hoặc `@DynamicPropertySource`.
4. Chạy Flyway/Liquibase migrations và Hibernate schema validation trên database container.
5. Kiểm thử SQL dialect, unique constraints, partial indexes, locking, isolation và native queries.
6. Quản lý transaction/test data để không vô tình che lỗi commit hoặc concurrency.
7. Tránh các vấn đề container lifecycle, Spring context cache, parallel tests và CI.
8. Xây dựng integration tests có thể tái lập và không phụ thuộc database dùng chung của developer.

## 2. Test pyramid: không phải test nào cũng cần container

Database thật tạo độ tin cậy cao cho behavior phụ thuộc DB, nhưng có chi phí khởi động, tài nguyên và thời gian. Không cần biến mọi unit test thành integration test.

| Loại test | Dùng gì? | Câu hỏi được trả lời |
|---|---|---|
| Unit test domain logic | Không cần DB; mock dependencies nếu cần | Quy tắc Java/domain có đúng không? |
| Repository/service test đơn giản | H2 có thể đủ nếu SQL/mapping portable | JPQL, mapping cơ bản và wiring có hoạt động không? |
| ORM integration test | Database cùng engine/version production | Hibernate sinh SQL và quản lý transaction đúng không? |
| Migration/schema test | Database thật + migration tool | DDL/index/constraint có tạo được trên DB mục tiêu không? |
| Concurrency/locking test | Database thật, transactions/connections riêng | Unique, lock, isolation và optimistic/pessimistic behavior có đúng không? |
| End-to-end test | Stack gần production, có thể gồm DB container | Các thành phần tích hợp có hoạt động cùng nhau không? |

### 2.1. Khi nào H2 thường đủ?

H2 có thể phù hợp khi test:
- Một domain/service rule không phụ thuộc DB.
- CRUD JPA cơ bản, JPQL portable.
- Mapping entity và association thông thường.
- Một repository query đơn giản không dùng vendor-specific functions.
- Logic transaction ở mức ứng dụng mà không cần kiểm chứng locking/DB behavior riêng.

Nhưng H2 **không tự động tương đương** PostgreSQL/MySQL chỉ vì cả hai đều hỗ trợ SQL và JDBC.

### 2.2. Khi nào nên dùng database thật?

Dùng Testcontainers khi test phụ thuộc một hoặc nhiều điều sau:

- Partial/filtered unique indexes hoặc generated columns.
- JSON/JSONB, arrays, enums, UUID, spatial types, full-text search.
- Native SQL, stored procedures, functions hoặc dialect-specific syntax.
- Collation, case sensitivity, Unicode comparison và NULL semantics.
- Foreign keys, CHECK constraints, cascade và deferrable constraints.
- Locking, transaction isolation, deadlocks và concurrent writes.
- Optimistic/pessimistic locking và `@Version`.
- Migrations Flyway/Liquibase, extensions, triggers, generated columns.
- Hibernate SQL generation khác nhau theo dialect.
- Query plans, indexes và database-specific performance behavior.

Một nguyên tắc thực tế: **test điều gì có thể sai ở production database bằng chính loại database đó**.

### 2.3. Testcontainers không thay thế mọi test

Không nên khởi chạy container cho mọi phép kiểm tra đơn giản như:
- Một hàm normalize email.
- Một method tính thuế thuần Java.
- Một mapper DTO không truy cập DB.
- Một validation rule không phụ thuộc database.

Tách test nhanh khỏi test tích hợp giúp developer chạy feedback loop nhanh và CI phân loại failure rõ hơn.

## 3. Testcontainers hoạt động như thế nào?

Testcontainers là thư viện Java điều khiển container runtime (thường là Docker) để khởi chạy services phục vụ test. Test code tạo container object, cấu hình image/credentials/database, đợi service sẵn sàng, sau đó lấy JDBC URL/host/port được ánh xạ động.

~~~text
JUnit test starts
       |
       v
Testcontainers requests Docker
       |
       v
Start PostgreSQL container
       |
       +--> wait until database accepts connections
       |
       v
Expose mapped host/port + JDBC URL
       |
       v
Spring DataSource / Hibernate / JDBC
       |
       v
Run test + migrations + assertions
       |
       v
Stop container / cleanup resources
~~~

### 3.1. Vì sao port thường không cố định?

Container PostgreSQL có thể nghe cổng 5432 **bên trong container**, nhưng Testcontainers thường map sang một host port khả dụng. Không hard-code `localhost:5432` trong test; lấy connection details từ container hoặc Spring Boot service connection.

Điều này cho phép:
- Nhiều test suites chạy song song.
- Developer có PostgreSQL local ở port 5432 mà không xung đột.
- CI không cần một database service cố định được cấu hình trước.
- Test dùng credentials/database riêng biệt.

### 3.2. Những gì cần có trên máy/CI

- Java/JDK phù hợp project.
- Build tool (Gradle/Maven).
- Docker Engine hoặc Docker Desktop đang chạy, hoặc một compatible container runtime được Testcontainers hỗ trợ.
- Quyền truy cập Docker socket/daemon.
- Network và image registry access để pull database image lần đầu.
- Dung lượng disk/RAM phù hợp.

Nếu Docker daemon không chạy, Testcontainers không thể tự tạo database bằng Java. Lỗi thường nằm ở container runtime/permissions/image pull, không phải Hibernate.

### 3.3. Chọn image cụ thể, không dùng latest

Ví dụ:

~~~java
new PostgreSQLContainer<>("postgres:16.4-alpine");
~~~

Trong dự án thật, chọn version phù hợp với production, pin major/minor/patch hoặc image digest theo policy. Tránh `postgres:latest` vì một lần pull mới có thể thay đổi behavior và làm test khác nhau giữa developer/CI.

Database image version cần tương thích:
- Production engine/version.
- Migration scripts.
- Extensions.
- JDBC driver.
- SQL syntax được sử dụng.
- CI architecture.

## 4. Dependencies trong Gradle và Maven

Các ví dụ dưới đây minh họa Testcontainers API phổ biến thuộc dòng 1.x và Spring Boot 3.1+ integration. Hãy dùng BOM/version được project quản lý và imports tương ứng với major version Testcontainers đang cài; **không trộn modules từ các major versions khác nhau**.

### 4.1. Gradle Kotlin DSL

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")

    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
}
~~~

Nếu project không có dependency management quản lý Testcontainers version, import Testcontainers BOM cùng một version:

~~~kotlin
dependencies {
    testImplementation(platform("org.testcontainers:testcontainers-bom:$testcontainersVersion"))
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
}
~~~

`testcontainersVersion` là Gradle property/version do project quản lý, không phải dependency tự được khai báo ở đây. Nếu Spring Boot BOM đã quản lý version phù hợp, tránh khai báo hai BOM xung đột.

### 4.2. Gradle Groovy DSL

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

### 4.3. Maven

~~~xml
<dependencies>
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

Nếu Spring Boot dependency management chưa quản lý Testcontainers, import `org.testcontainers:testcontainers-bom` trong `dependencyManagement`. Đừng chọn version độc lập cho từng Testcontainers module.

### 4.4. Nếu dùng MySQL

Thay module PostgreSQL bằng module MySQL tương ứng:

~~~kotlin
testImplementation("org.testcontainers:mysql")
~~~

Container class thường dùng trong API 1.x:

~~~java
MySQLContainer<?> mysql =
    new MySQLContainer<>("mysql:8.4");
~~~

Chọn image cùng major/version/collation với môi trường mục tiêu. Nếu production dùng MariaDB, kiểm thử bằng MariaDB container thay vì suy luận MySQL tương đương.

### 4.5. JDBC driver vẫn cần có

Testcontainers module không nhất thiết thay thế JDBC driver do application dùng. Ví dụ PostgreSQL driver:

~~~kotlin
runtimeOnly("org.postgresql:postgresql")
~~~

Nếu Spring Boot cần driver trong test runtime, dependency scope phải bao gồm test runtime (ví dụ `runtimeOnly` trong source set main hoặc `testRuntimeOnly` theo cấu trúc project). MySQL dùng driver tương ứng.

## 5. Test database trực tiếp với JUnit Jupiter

Trước khi tích hợp Spring, có thể kiểm tra Testcontainers hoạt động bằng JDBC thuần.

### 5.1. PostgreSQLContainer cơ bản

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
class PostgreSqlContainerTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @Test
    void connectsToRealPostgres() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword());
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(
                "select current_database()")) {

            result.next();
            assertEquals("app_test", result.getString(1));
        }
    }
}
~~~

`@Testcontainers` đăng ký JUnit Jupiter extension; `@Container static` cho biết container được khởi động một lần cho class và dừng sau class theo lifecycle extension.

### 5.2. Lấy connection details từ container

| Method | Giá trị |
|---|---|
| `getJdbcUrl()` | JDBC URL với mapped host/port |
| `getUsername()` | Username cấu hình cho DB |
| `getPassword()` | Password cấu hình |
| `getHost()` | Host mà test process truy cập |
| `getMappedPort(5432)` | Host port map từ port bên trong container |

Không tạo JDBC URL bằng cách tự nối `localhost:5432`. Port có thể thay đổi theo mỗi lần chạy.

### 5.3. Chạy SQL init script

~~~java
static final PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16.4-alpine")
        .withDatabaseName("app_test")
        .withUsername("test")
        .withPassword("test")
        .withInitScript("db/container-init.sql");
~~~

`withInitScript` tìm script trong test classpath và chạy khi database container khởi tạo theo contract của module.

Dùng script này cho bootstrap đặc thù container, ví dụ tạo extension/role cần thiết. Nếu ứng dụng dùng Flyway/Liquibase, **để migration tool của ứng dụng tạo schema nghiệp vụ**, tránh có hai nguồn schema definitions dễ lệch nhau.

### 5.4. MySQL container trực tiếp

~~~java
import org.testcontainers.containers.MySQLContainer;

@Testcontainers
class MySqlContainerTest {

    @Container
    static final MySQLContainer<?> mysql =
        new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @Test
    void usesTargetDatabase() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                mysql.getJdbcUrl(),
                mysql.getUsername(),
                mysql.getPassword())) {

            assertTrue(connection.isValid(2));
        }
    }
}
~~~

Nếu kiểm thử collation, timezone hoặc SQL modes, hãy cấu hình chúng trong container/database đúng cách và assert bằng SQL. Một MySQL container “cùng engine” nhưng khác collation/SQL mode vẫn có thể không đại diện production.

## 6. Kết nối Spring Boot bằng @ServiceConnection

Spring Boot 3.1+ hỗ trợ service connection integration cho một số Testcontainers modules. Annotation `@ServiceConnection` cho phép Boot suy ra connection details từ container object.

### 6.1. Cách đơn giản trên test class

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class UserRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @Autowired
    UserRepository userRepository;

    @Test
    void loadsUsersFromPostgres() {
        // Thực hiện repository assertions.
    }
}
~~~

Cần dependency `spring-boot-testcontainers` trong test scope và Testcontainers module tương ứng. Boot nhận connection details từ container, nên thường không cần tự khai báo `spring.datasource.url`, username/password cho container này.

### 6.2. @DataJpaTest cần chú ý replace datasource

`@DataJpaTest` là slice test tập trung JPA. Theo cấu hình mặc định, Spring Boot có thể thay datasource bằng embedded database nếu có trên classpath.

Khi muốn dùng PostgreSQL container, khai báo:

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Testcontainers
class UserRepositoryJpaTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @Autowired
    UserRepository repository;

    @Test
    void savesAndFindsUser() {
        // Arrange/act/assert với DB container.
    }
}
~~~

`replace = NONE` yêu cầu Spring Boot giữ datasource đã được cấu hình thay vì tự thay bằng embedded DB. Xác nhận test thật sự kết nối container qua logs/connection metadata khi lần đầu thiết lập.

### 6.3. @ServiceConnection với @TestConfiguration

Khi nhiều test classes dùng chung một Spring context, có thể khai báo container như bean trong test configuration để lifecycle gắn với Spring context:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class DatabaseContainerConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");
    }
}
~~~

Import config vào test:

~~~java
@SpringBootTest
@Import(DatabaseContainerConfiguration.class)
class UserServiceIntegrationTest {
    // Tests...
}
~~~

Spring Boot có thể quản lý container bean lifecycle cùng ApplicationContext. Cách này hữu ích khi Spring TestContext cache context và nhiều test classes tái sử dụng cùng cấu hình.

**Kiểm tra đúng Spring Boot version**: package/behavior của service connections và container bean lifecycle phụ thuộc phiên bản. Nếu không có hỗ trợ tương ứng, dùng `@DynamicPropertySource`.

## 7. Kết nối thủ công với @DynamicPropertySource

Trước Spring Boot service connections, hoặc khi cần custom properties, dùng `@DynamicPropertySource`.

### 7.1. Ví dụ Spring Boot

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class UserRepositoryDynamicPropertyTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void datasourceProperties(
            DynamicPropertyRegistry registry) {

        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add(
            "spring.datasource.driver-class-name",
            postgres::getDriverClassName
        );
    }
}
~~~

`@DynamicPropertySource` là static method nhận `DynamicPropertyRegistry`; supplier được dùng để đăng ký property value động.

### 7.2. Custom datasource hoặc migration datasource

Nếu project cấu hình datasource bằng custom prefix, hãy đăng ký đúng keys mà configuration class đọc. Nếu Flyway dùng datasource riêng, cấu hình migration connection theo đúng kiến trúc; không mặc định chỉ set `spring.datasource.*` sẽ bao phủ mọi DataSource.

Không hard-code port/password của container vào `application-test.yml`. Container details phải được lấy từ object runtime.

### 7.3. Chọn cách kết nối

| Cách | Phù hợp khi |
|---|---|
| `@ServiceConnection` | Spring Boot version hỗ trợ và container module được nhận diện |
| `@DynamicPropertySource` | Cần tương thích rộng, custom property keys hoặc chưa dùng service connections |
| JDBC thủ công | Test JDBC độc lập hoặc framework không có integration tự động |
| Testcontainers JDBC URL | Muốn khởi tạo container từ datasource URL và use case phù hợp |

Không khai báo cả service connection và dynamic properties cho cùng datasource nếu không có lý do; ưu tiên một nguồn connection configuration rõ ràng.

## 8. Testcontainers JDBC URL

Testcontainers có module JDBC cho phép dùng URL dạng:

~~~properties
spring.datasource.url=jdbc:tc:postgresql:16.4:///app_test
spring.datasource.username=test
spring.datasource.password=test
~~~

Khi JDBC driver/module tương ứng được cấu hình, container có thể được tạo khi datasource được sử dụng. Cú pháp và options phụ thuộc Testcontainers version/module.

Ưu điểm:
- Có thể ít code container object trong test.
- Hợp với ứng dụng dùng datasource config chuẩn.
- Có thể tích hợp init scripts theo Testcontainers JDBC URL conventions.

Hạn chế:
- Lifecycle và startup timing ít tường minh hơn container field/bean.
- Không dễ truyền container object cho `@ServiceConnection`.
- Custom ports, network aliases, wait strategies và advanced configuration có thể khó biểu đạt.
- Cần module JDBC tương ứng và driver.
- Với Spring context caching, vẫn cần hiểu datasource/container lifecycle.

Nếu test cần điều khiển container nhiều, **container object + service connection/dynamic properties** thường dễ đọc và debug hơn.

## 9. Chạy Flyway/Liquibase trên database container

Một integration test có ý nghĩa cần kiểm chứng **schema thật của ứng dụng**, không chỉ một bảng test tự tạo thủ công.

### 9.1. Dùng Flyway migration như production

Ví dụ cấu trúc:

~~~text
src/
  main/
    resources/
      db/
        migration/
          V1__create_users.sql
          V2__active_email_unique_index.sql
  test/
    java/
      ...UserRepositoryIntegrationTest.java
~~~

Migration `V1__create_users.sql`:

~~~sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    normalized_email VARCHAR(320) NOT NULL,
    deleted_at TIMESTAMP NULL
);
~~~

Migration `V2__active_email_unique_index.sql` trên PostgreSQL:

~~~sql
CREATE UNIQUE INDEX ux_users_active_tenant_email
ON users (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
~~~

Khi Spring context khởi động, Flyway áp migrations lên container database. Test kiểm tra constraint đã được tạo đúng trên engine production.

### 9.2. Cấu hình Hibernate schema validation

Nếu Flyway/Liquibase là source of truth cho schema, cấu hình Hibernate chỉ validate:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
~~~

Điều này giúp Hibernate kiểm tra mapping/schema tương thích ở mức nó hỗ trợ. Nhưng Hibernate schema validation **không đảm bảo** partial-index predicate, trigger, collation, generated expression hay mọi database-specific DDL đều chính xác. Integration tests phải kiểm tra behavior/catalog của các objects đó.

Không dùng `ddl-auto=create-drop` trong test migration nếu mục tiêu là kiểm tra migration production; Hibernate có thể tạo schema riêng làm test vô tình bỏ qua lỗi migration.

### 9.3. Liquibase

Nếu ứng dụng dùng Liquibase, để Liquibase chạy changelog chính thức khi Spring context khởi động. Changesets có thể có preconditions hoặc database-specific SQL blocks theo DB support.

Không tạo schema test bằng một file SQL độc lập nếu production dùng Liquibase, vì hai schema có thể lệch nhau.

### 9.4. Container init script không phải migration tool

`withInitScript("db/container-init.sql")` chạy bootstrap script lúc database container khởi tạo. Có thể dùng cho:
- Tạo extension PostgreSQL cần trước migrations.
- Tạo role/permission đặc thù test.
- Thiết lập một database bootstrap nhỏ.

Tránh đặt toàn bộ bảng ứng dụng trong cả init script lẫn Flyway. Nếu có hai nguồn DDL, test có thể pass trong khi migration thật fail.

### 9.5. Kiểm tra migration trên database trống

Một test tốt nên tạo container/database mới hoặc schema sạch, sau đó:
1. Khởi động application context.
2. Để Flyway/Liquibase chạy từ đầu.
3. Kiểm tra migration version/history.
4. Thực hiện repository operation.
5. Assert constraint/index behavior.
6. Dừng/cleanup container.

Điều này phát hiện migrations chỉ hoạt động khi developer DB đã có objects từ trước.

## 10. Test dữ liệu và transaction một cách có chủ đích

### 10.1. @DataJpaTest thường rollback mỗi test

`@DataJpaTest` thường chạy test trong transaction và rollback khi test kết thúc. Điều này tiện cho isolation, nhưng có thể che một số lỗi:
- Commit-time constraint/deferred constraint.
- After-commit listeners.
- Transaction visibility với connection khác.
- Background worker cần đọc dữ liệu đã commit.
- Locking giữa hai transactions.

`entityManager.flush()` giúp phát SQL và kiểm tra nhiều constraints ngay trong test, nhưng **flush không phải commit**. Với deferred constraints, lỗi có thể chỉ xuất hiện lúc transaction commit.

### 10.2. Dùng TestEntityManager để kiểm tra persistence

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class UserPersistenceTest {

    @Autowired
    TestEntityManager entityManager;

    @Test
    void persistsAndReloads() {
        User user = new User("a@example.com");

        entityManager.persist(user);
        entityManager.flush();

        Long id = user.getId();
        entityManager.clear();

        User reloaded = entityManager.find(User.class, id);
        assertEquals("a@example.com", reloaded.getEmail());
    }
}
~~~

`clear()` detach các managed objects trong persistence context, giúp lần `find` sau đọc lại theo DB/cache semantics thay vì trả object đang managed. Nếu second-level cache được bật, có thể cần cache policy riêng để test DB round trip.

### 10.3. Không chỉ assert object state trước flush

~~~java
User user = new User("a@example.com");
repository.save(user);

assertNotNull(user.getId());
~~~

Điều này chưa chứng minh SQL đã thành công hoặc transaction đã commit. Với generator IDENTITY, INSERT có thể chạy sớm; generator khác có thể cấp ID trước. Nếu test muốn chứng minh DB constraint, hãy flush hoặc hoàn tất transaction rồi query lại từ context mới.

### 10.4. Kiểm tra commit thật khi cần

Có thể dùng `TransactionTemplate` hoặc Spring TestTransaction để kết thúc transaction có chủ đích:

~~~java
transactionTemplate.executeWithoutResult(status -> {
    repository.save(user);
    // TransactionTemplate commit khi callback kết thúc bình thường.
});
~~~

Sau đó đọc trong một transaction mới. Nếu test method tự được `@Transactional` bao ngoài, TransactionTemplate mặc định có thể join transaction hiện tại theo propagation; muốn independent commit phải cấu hình boundary phù hợp và hiểu rollback test semantics.

**Không thêm `@Commit` vào mọi test chỉ để “chắc đã ghi DB”**; điều đó có thể làm test data tồn tại qua các tests và phá isolation.

### 10.5. Seed data sau migration

Các lựa chọn:
- Builder/factory tạo entities qua JPA khi muốn test ORM lifecycle.
- `@Sql` chạy SQL fixture khi cần dữ liệu chính xác hoặc database-specific.
- Test data builder trong code.
- Dataset riêng theo test class.

Dù chọn cách nào, đảm bảo fixture không tạo state phụ thuộc thứ tự test và cleanup không xóa dữ liệu của test khác.

## 11. Test database-specific constraints với Testcontainers

### 11.1. Ví dụ PostgreSQL partial unique index

Giả sử migration đã tạo:

~~~sql
CREATE UNIQUE INDEX ux_users_active_tenant_email
ON users (tenant_id, normalized_email)
WHERE deleted_at IS NULL;
~~~

Test:

~~~java
@Test
void allowsManyDeletedRowsButOnlyOneActiveEmail() {
    repository.saveAndFlush(
        new User(7L, "a@example.com", Instant.parse("2025-01-01T00:00:00Z"))
    );
    repository.saveAndFlush(
        new User(7L, "a@example.com", Instant.parse("2025-02-01T00:00:00Z"))
    );

    repository.saveAndFlush(
        new User(7L, "a@example.com", null)
    );

    assertThrows(
        DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(
            new User(7L, "a@example.com", null)
        )
    );
}
~~~

Đây là ví dụ khái niệm; constructor/mapping repository cần tương ứng. Vì exception có thể đánh dấu transaction rollback-only, sau assertion fail không tiếp tục repository operations trong cùng transaction. Nếu test method mặc định transactional, test kết thúc và rollback transaction là phù hợp.

Test này phải chạy trên PostgreSQL container nếu muốn chứng minh PostgreSQL partial index; H2 compatibility mode không phải bằng chứng tương đương.

### 11.2. Kiểm tra generated columns trên MySQL

Với MySQL generated active key:
- Insert deleted rows có cùng email.
- Insert một active row.
- Thử insert active duplicate và assert unique violation.
- Soft-delete active row rồi insert active row mới.
- Restore row cũ khi row mới còn active và assert conflict.
- Kiểm tra generated column value trực tiếp bằng SQL.

Đây là DB behavior cụ thể, nên test bằng MySQL container đúng version/collation.

### 11.3. Kiểm tra collation và normalization

Nếu production dùng collation không phân biệt case hoặc index expression `lower(email)`:
- Insert `Alice@example.com`.
- Thử insert `alice@example.com`.
- Assert theo business policy.
- Test Unicode normalization nếu domain yêu cầu.
- Test trailing spaces và DB collation rules.
- Xác nhận application normalization và database equality không mâu thuẫn.

### 11.4. Native query và database functions

Nếu code dùng:
- `jsonb_path_query`.
- `ON CONFLICT ... WHERE`.
- PostgreSQL `RETURNING`.
- MySQL `JSON_EXTRACT`.
- SQL Server filtered indexes.
- Oracle analytic/function syntax.

hãy thực hiện query trên đúng DB engine. Mock chỉ xác nhận code đã gọi method; H2 có thể không hỗ trợ đúng syntax/function semantics.


## 12. Kiểm thử transaction, locking và concurrency

### 12.1. Tại sao cần hai connections/transactions?

Một test method chạy trong một transaction không kiểm chứng được hai clients cạnh tranh. Để test concurrency, cần:
- Hai threads riêng.
- Hai transaction độc lập.
- Mỗi thread có persistence context/EntityManager riêng.
- Một barrier/latch đồng bộ thời điểm.
- Database thật với isolation/config tương ứng production.

**Không chia sẻ cùng Hibernate Session/EntityManager giữa threads.**

### 12.2. Ví dụ kiểm tra unique constraint dưới concurrency

Giả sử Spring service/repository đã được inject và DB có unique index:

~~~java
@Test
void onlyOneConcurrentRegistrationCanCommit() throws Exception {
    CyclicBarrier barrier = new CyclicBarrier(2);

    Callable<Boolean> attempt = () -> {
        try {
            transactionTemplate.executeWithoutResult(status -> {
                boolean exists = repository
                    .existsByTenantIdAndEmail(7L, "race@example.com");

                await(barrier);

                if (exists) {
                    throw new DuplicateEmailException();
                }

                repository.saveAndFlush(
                    new User(7L, "race@example.com")
                );
            });
            return true;
        } catch (DataIntegrityViolationException ex) {
            return false;
        }
    };

    ExecutorService pool = Executors.newFixedThreadPool(2);
    try {
        Future<Boolean> first = pool.submit(attempt);
        Future<Boolean> second = pool.submit(attempt);

        int successes =
            (first.get() ? 1 : 0) + (second.get() ? 1 : 0);

        assertEquals(1, successes);
        assertEquals(
            1,
            repository.countByTenantIdAndEmail(
                7L, "race@example.com"
            )
        );
    } finally {
        pool.shutdownNow();
    }
}
~~~

Helper cho barrier:

~~~java
private static void await(CyclicBarrier barrier) {
    try {
        barrier.await(10, TimeUnit.SECONDS);
    } catch (Exception ex) {
        throw new IllegalStateException(ex);
    }
}
~~~

Đây là pattern minh họa, cần imports `java.util.concurrent.*` và test setup tương ứng. `TransactionTemplate` phải dùng transaction manager phù hợp; mỗi invocation từ worker thread sẽ mở transaction riêng nếu thread đó chưa có transaction.

Cả hai transactions có thể cùng thấy `exists=false`, rồi cùng INSERT. Unique index là cơ chế cuối cùng để chỉ một row có thể commit. DB/isolation cụ thể có thể ném unique violation, serialization failure hoặc deadlock; nếu muốn test đúng một loại exception, cấu hình isolation và DB version tương ứng.

**Không bắt mọi exception thành duplicate** trong code production. Test concurrency cần phân biệt conflict deterministic với lỗi hạ tầng/transient.

### 12.3. Cẩn thận với transaction của test method

Nếu test method được annotate `@Transactional`:
- Thread chính có transaction test.
- Worker threads không tự kế thừa transaction của thread chính.
- Fixture chưa commit có thể không visible cho worker connections.
- Cleanup rollback của test không nhất thiết rollback những transactions worker đã commit.
- Test có thể để lại dữ liệu nếu worker commit độc lập.

Vì vậy concurrency tests thường nên **không có test-level @Transactional**; tạo fixture đã commit trước, chạy workers, rồi cleanup bằng transaction riêng hoặc database/schema riêng.

### 12.4. Test optimistic locking với @Version

Để chứng minh optimistic conflict:
1. Hai EntityManagers/transactions cùng load một entity và version V.
2. T1 cập nhật và commit, version thành V+1.
3. T2 cập nhật entity với snapshot V rồi flush/commit.
4. T2 phải nhận optimistic locking failure theo provider/transaction integration.

Không dùng một EntityManager chung cho hai threads; một persistence context không phải công cụ mô phỏng hai users đồng thời.

### 12.5. Test pessimistic locking và deadlock

Với `LockModeType.PESSIMISTIC_WRITE` hoặc query lock:
- Dùng DB thật.
- Dùng transactions riêng và barriers.
- Thiết lập timeout rõ.
- Tránh test treo vô hạn.
- Assert lock contention/timeout theo semantics DB/driver.
- Cleanup connections/threads trong `finally`.

Deadlock behavior phụ thuộc execution plan, thứ tự lock và DB engine. Đừng viết test dựa trên thứ tự scheduling của JVM mà không có synchronization.

## 13. Container lifecycle và Spring TestContext cache

Đây là một trong những lỗi khó hiểu nhất khi dùng Testcontainers cùng Spring.

### 13.1. @Container static và lifecycle theo test class

~~~java
@Testcontainers
@SpringBootTest
class FirstIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16.4-alpine");
}
~~~

`static @Container` thường khởi động một lần cho class và dừng khi class hoàn thành. Nhưng Spring TestContext có thể cache ApplicationContext để tái sử dụng cho class test khác.

Kịch bản lỗi:
1. Class A khởi động container và Spring context kết nối nó.
2. Class A kết thúc, Testcontainers extension dừng container.
3. Spring vẫn giữ context đã cache.
4. Class B tái sử dụng context đó.
5. DataSource trong context trỏ tới host port/container đã dừng → connection failure.

Đây không phải lỗi Hibernate mapping; đây là **lifecycle không đồng bộ giữa JUnit extension và Spring context cache**.

### 13.2. Container bean gắn với Spring ApplicationContext

Với Spring Boot hỗ trợ service connections, khai báo container trong test configuration:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class SharedDatabaseTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");
    }
}
~~~

Import configuration vào các test classes dùng chung context:

~~~java
@SpringBootTest
@Import(SharedDatabaseTestConfiguration.class)
class OrderIntegrationTest {
}
~~~

Container lifecycle gắn với Spring context theo Spring Boot integration. Khi context được đóng, container được dọn theo lifecycle của bean.

Kiểm tra behavior của đúng Spring Boot/Testcontainers version. Nếu project dùng version cũ, có thể dùng singleton container pattern hoặc quản lý container suite-wide một cách tường minh.

### 13.3. Singleton container pattern

Với JUnit/test suite không dùng Spring-managed container bean, một singleton container được khởi chạy một lần và giữ tới khi JVM kết thúc có thể giảm startup time:

~~~java
abstract class AbstractPostgresIntegrationTest {

    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");

    static {
        POSTGRES.start();
    }
}
~~~

Các test classes kế thừa có thể dùng cùng container. Nhưng:
- Phải quản lý cleanup JVM/test suite.
- Dữ liệu giữa test classes phải được cô lập.
- Không để parallel tests dùng chung table rows/sequence state tùy tiện.
- Spring context phải được cấu hình connection details tương thích singleton.
- Nếu test suite chạy trong forked JVMs, mỗi fork có lifecycle/container riêng.

Singleton pattern giảm startup cost nhưng tăng yêu cầu về data isolation.

### 13.4. Instance @Container

~~~java
@Container
PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16.4-alpine");
~~~

Container được khởi động/dừng cho từng test method theo JUnit extension semantics. Điều này cô lập tốt nhưng startup rất tốn thời gian, đặc biệt khi có hàng trăm tests.

Dùng khi isolation container thực sự cần thiết, không mặc định cho mọi repository test.

### 13.5. Chọn lifecycle theo phạm vi

| Lifecycle | Chi phí | Phù hợp |
|---|---|---|
| Mỗi test method | Cao | Cần DB state hoàn toàn tách biệt/container config khác nhau |
| Mỗi test class | Trung bình | Một class test dùng DB chung, context không bị tái sử dụng sau khi container dừng |
| Một Spring ApplicationContext | Thường hiệu quả | Nhiều test classes dùng cùng Boot context/container bean |
| Suite/JVM singleton | Thấp hơn startup lặp | Suite lớn, có strategy reset data/schema nghiêm ngặt |

Đừng chọn singleton chỉ vì nó nhanh nếu test isolation bị phá.

## 14. Parallel tests và dữ liệu chia sẻ

### 14.1. Container chung không có nghĩa dữ liệu test chung an toàn

Nhiều tests có thể chạy trên một PostgreSQL container/database. Nếu hai tests cùng INSERT `test@example.com` vào unique index, một test có thể fail ngẫu nhiên dù code đúng.

Các biện pháp:
- Mỗi test dùng unique fixture key (UUID).
- Tạo schema/database riêng cho từng test worker nếu cần.
- Chia namespace tenant IDs.
- Dùng cleanup có kiểm soát.
- Tắt parallelism cho nhóm test dùng shared global state.
- Không giả định rollback transaction của test bao phủ mọi thread.

### 14.2. Truncate và cleanup

Ví dụ PostgreSQL:

~~~sql
TRUNCATE TABLE order_items, purchase_orders, customers
RESTART IDENTITY CASCADE;
~~~

Chỉ chạy khi test sở hữu database/schema đó. `TRUNCATE ... CASCADE` có thể xóa dữ liệu liên quan ngoài dự kiến nếu schema chia sẻ. Không chạy cleanup rộng trên một database dùng chung nhiều suites.

### 14.3. Dùng database/schema riêng theo worker

Một suite lớn có thể:
- Một container PostgreSQL.
- Mỗi worker một schema.
- Migrations chạy vào từng schema.
- Connection search_path/schema được đặt theo worker.
- Cleanup schema sau suite.

Cách này nhanh hơn một container per test nhưng đòi hỏi quản lý schema, migration metadata và connection settings rõ ràng.

### 14.4. Test order không được quyết định kết quả

Một test không được phụ thuộc “test A chạy trước để tạo user fixture”. Dùng test data builder/SQL fixture riêng, unique IDs và cleanup. Nếu test chỉ pass khi chạy cả class nhưng fail khi chạy độc lập, thường có shared state/lifecycle/data dependency.

## 15. CI: chạy Testcontainers trên pipeline

### 15.1. CI cần container runtime

Testcontainers cần Docker-compatible runtime. Nhiều CI hosted runners có Docker sẵn; self-hosted runner phải cài đặt và cấp quyền socket/daemon.

Pipeline cần:
- Checkout source.
- Cài JDK/build tool.
- Cung cấp Docker runtime.
- Pull database image (hoặc dùng image cache).
- Chạy test tasks.
- Lưu logs/reports khi fail.
- Dọn containers/volumes/networks sau job.

Không cấu hình CI trỏ vào một PostgreSQL production/shared database chỉ để tránh Docker. Mỗi job nên có DB ephemeral và dữ liệu test độc lập.

### 15.2. Khi container không khởi động

Kiểm tra:
- Docker daemon có đang chạy không?
- Runner có quyền Docker socket không?
- `DOCKER_HOST`/Docker context có trỏ đúng endpoint không?
- Registry pull có bị chặn/auth failure không?
- Image architecture có phù hợp runner không?
- Có đủ RAM/disk không?
- Port/network/firewall có cho phép không?
- Testcontainers Ryuk resource reaper có chạy được không?

Log container startup thường giúp phân biệt “database chưa ready” với “không kết nối được Docker”.

### 15.3. Ryuk và cleanup

Testcontainers thường dùng resource reaper (Ryuk) để dọn resources sau test process. Nếu CI environment chặn container này, có thể gặp leaked containers/volumes hoặc startup failure tùy config.

Không tắt Ryuk một cách tùy tiện. Nếu môi trường yêu cầu custom cleanup, phải có cơ chế dọn resources theo labels/run ID và quyền hạn tương ứng; nếu không, runner có thể tích lũy container rác.

### 15.4. Không skip test quan trọng một cách âm thầm

Một số cấu hình JUnit/Testcontainers có thể skip tests khi Docker không khả dụng, ví dụ tùy chọn `disabledWithoutDocker`. Điều này hữu ích trên laptop developer không cài Docker, nhưng trong CI của project thì integration suite quan trọng nên **fail fast nếu Docker runtime được kỳ vọng**.

Phân loại rõ:
- Local optional integration profile có thể skip với thông báo.
- CI release gate phải xác nhận database integration tests đã chạy.
- Không coi “0 tests executed vì Docker unavailable” là pass.

### 15.5. CI image caching

Database images lớn có thể làm pipeline chậm khi pull mỗi job. Caching image ở runner hoặc registry mirror có thể giúp, nhưng:
- Pin image version/digest.
- Không cache container state/database data như test fixture dùng chung.
- Bảo đảm image cache không âm thầm thay image version.
- Cleanup container/volume sau mỗi job.

## 16. Test dữ liệu khởi tạo và schema

### 16.1. Migration test và repository test là hai mục tiêu khác nhau

Migration test trả lời: **schema từ database trống có thể được tạo đúng không?**

Repository test trả lời: **application queries/mappings hoạt động trên schema đó không?**

Một test dùng schema Hibernate create tự động không chứng minh Flyway migration đúng. Một test chỉ kiểm tra Flyway history table không chứng minh repository query chạy.

### 16.2. Dùng migration production

Ví dụ Spring Boot properties:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.flyway.enabled=true
~~~

Với Liquibase:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.liquibase.enabled=true
~~~

Chỉ bật tool migration mà project thực sự sử dụng. Nếu application dùng profile/config khác cho test, xác nhận nó không vô tình disable migration hoặc trỏ vào schema sai.

### 16.3. Seed data: migration hay fixture?

- Migration chứa **schema evolution** và dữ liệu reference cần tồn tại trong mọi môi trường.
- Test fixture chứa **dữ liệu phục vụ một scenario test**.
- Không nhét một tập test users/orders ngẫu nhiên vào production migrations.
- Không dùng test fixture để âm thầm sửa schema thiếu.

### 16.4. @Sql và transaction

~~~java
@Sql(
    scripts = "/sql/users-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
@Test
void findsActiveUser() {
    // ...
}
~~~

`@Sql` chạy theo Spring TestContext; transaction behavior phụ thuộc `@SqlConfig`, test transaction và execution phase. Nếu script cần commit để thread khác nhìn thấy, phải thiết kế transaction mode/boundary rõ, không mặc định fixture đã commit.

### 16.5. Test schema theo migrations trên database trống

Một pipeline hữu ích:
- Khởi động DB container sạch.
- Chạy migrations từ version đầu tiên.
- Kiểm tra migration status.
- Chạy repository/integration tests.
- Nếu project hỗ trợ, kiểm tra rollback/forward migration hoặc upgrade từ snapshot/schema version trước.
- Dừng container.

Điều này phát hiện migration phụ thuộc local database state hoặc một DBA đã tạo object thủ công mà repository không quản lý.

## 17. Kiểm thử Hibernate behavior thực tế

### 17.1. Dirty checking và flush

Dùng DB container để chứng minh:
1. Load entity managed.
2. Đổi field.
3. Flush.
4. Clear persistence context.
5. Reload từ database.
6. Assert value/version.

~~~java
@Test
void dirtyCheckingUpdatesDatabase() {
    User user = entityManager.find(User.class, userId);

    user.rename("New name");
    entityManager.flush();
    entityManager.clear();

    User reloaded = entityManager.find(User.class, userId);
    assertEquals("New name", reloaded.getName());
}
~~~

Nếu test method có transaction và rollback cuối test, DB state được nhìn thấy trong transaction test. Nếu cần xác nhận commit với connection khác, test phải kết thúc transaction rồi query từ context mới.

### 17.2. Lazy loading và fetch plan

Trên DB thật:
- Tạo nhiều root entities và associations.
- Clear persistence context trước đoạn đo.
- Truy cập association.
- Đếm JDBC statements hoặc Hibernate fetch statistics.
- Thử fetch join/EntityGraph/DTO/batch fetch.
- Kiểm tra không có lazy SQL ngoài service boundary.

DB container không tự phát hiện N+1; **instrumentation/query budget vẫn cần**.

### 17.3. Unique constraint và soft delete

Với active-only uniqueness:
- Insert một active row.
- Soft-delete row đó.
- Insert active row mới cùng key.
- Thử restore row cũ và assert unique conflict.
- Tạo nhiều deleted rows cùng key.
- Chạy thêm một JDBC/native insert để xác nhận DB constraint bảo vệ cả đường không qua Hibernate.

Đây là trường hợp DB thật rất hữu ích vì semantics partial/generated index là database-specific.

### 17.4. Isolation và visibility

Một test có thể:
- T1 INSERT nhưng chưa commit.
- T2 SELECT cùng key.
- T1 commit.
- T2 đọc lại theo isolation semantics.

Không giả định mọi DB/isolation mode có cùng snapshot behavior. PostgreSQL READ COMMITTED, PostgreSQL REPEATABLE READ và MySQL InnoDB isolation có semantics khác nhau. Test phải nêu isolation mode và dùng transactions/connections riêng.

### 17.5. Native SQL và Hibernate persistence context

Khi chạy native UPDATE trong transaction:
- Hibernate không tự cập nhật mọi managed object field.
- Clear/refresh có thể cần thiết.
- Cache/query cache cần policy riêng.
- Constraint/trigger vẫn do database thực thi.

Testcontainers giúp xác nhận actual DB result, nhưng vẫn phải test L1/L2 state bằng Hibernate APIs riêng.

## 18. Khi nào nên dùng Testcontainers JDBC vs container bean trong Spring?

| Tiêu chí | JDBC URL | Container field/bean |
|---|---|---|
| Thiết lập cơ bản | Rất gọn | Rõ container object |
| Lấy mapped host/port | Ít tường minh | Trực tiếp từ container |
| Spring Boot service connection | Không phải đường chính | Hỗ trợ tốt với @ServiceConnection |
| Custom startup/wait/network | Hạn chế hơn | Linh hoạt |
| Lifecycle nhiều Spring contexts | Cần hiểu datasource lifecycle | Có thể gắn container với context |
| Truyền container cho tests khác | Khó hơn | Dễ hơn |
| Phù hợp | Test JDBC/datasource đơn giản | Spring integration/advanced config |

Nếu ứng dụng Spring Boot dùng Flyway, JPA và nhiều repository tests, container bean/service connection thường là lựa chọn rõ ràng. Nếu một test JDBC đơn giản chỉ cần database tạm, JDBC URL có thể đủ.

## 19. Các lỗi thường gặp khi thiết lập

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Docker environment không được phát hiện | Daemon/endpoint/permissions | Kiểm tra Docker context, socket, DOCKER_HOST |
| Container pull timeout | Registry/network/auth | Kiểm tra image registry và credentials |
| Connection refused lúc startup | Database chưa ready hoặc port tự đoán sai | Dùng mapped JDBC URL và wait strategy |
| Test dùng H2 thay vì PostgreSQL | @DataJpaTest replace datasource | Đặt `replace = NONE` và kiểm tra service connection |
| Spring Boot không nhận container | Thiếu spring-boot-testcontainers hoặc version không hỗ trợ | Kiểm tra dependencies/version |
| `@DynamicPropertySource` trả port cũ | Container lifecycle không đồng bộ Spring context | Gắn lifecycle với context/singleton đúng |
| Class A pass, class B connection refused | JUnit dừng container nhưng Spring context vẫn cache | Dùng container bean/context lifecycle hoặc singleton |
| Test chạy riêng pass, chạy suite fail | Shared state/order/cache/parallel race | Fixture riêng, isolation, cleanup |
| Migration không chạy | Test profile disable Flyway/Liquibase hoặc datasource sai | Kiểm tra config/property source |
| Hibernate tạo schema thay vì migration | ddl-auto create/create-drop | Dùng migration tool và validate khi mục tiêu là migration |
| Migration chạy trên H2 nhưng fail production | SQL dialect-specific | Test bằng DB production engine |
| Unique constraint test không fail | Embedded DB semantics khác/transaction chưa flush | Test trên DB thật và flush/commit đúng |
| Commit-time constraint không được test | @DataJpaTest rollback, chỉ flush | Hoàn tất transaction có chủ đích |
| Concurrency test không tái hiện race | Dùng chung EntityManager hoặc không đồng bộ threads | Hai transactions/contexts riêng và barrier |
| Worker không thấy fixture | Fixture chưa commit | Commit fixture trước transaction khác |
| Container per method làm suite chậm | Startup cost lặp | Container static/context/suite lifecycle |
| Container reuse làm test phụ thuộc nhau | Dữ liệu cũ tồn tại | Cleanup/namespace/schema isolation |
| Container rác sau CI | Cleanup/Ryuk bị chặn | Sửa runtime/permissions và cleanup policy |
| Test skip khi Docker không có nhưng CI vẫn xanh | disabledWithoutDocker/optional profile | CI release gate phải chạy suite thật |
| SQL log quá nhiều và lộ PII | Bind parameter TRACE | Tắt/mask sensitive parameters |
| Test pass nhưng DB plan chậm | Chỉ assert correctness | EXPLAIN/ANALYZE và performance test riêng |
| Version test khác production | Image tag latest | Pin DB image/version/digest |
| Test timezone không ổn định | Container timezone/session timezone khác | Set timezone rõ và assert DB/JVM behavior |

## 20. Một cấu hình tham khảo hoàn chỉnh cho Spring Boot + PostgreSQL

### 20.1. Test configuration

~~~java
@TestConfiguration(proxyBeanMethods = false)
class PostgreSqlTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16.4-alpine")
            .withDatabaseName("app_test")
            .withUsername("test")
            .withPassword("test");
    }
}
~~~

### 20.2. Repository integration test

~~~java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Import(PostgreSqlTestConfiguration.class)
class UserRepositoryIntegrationTest {

    @Autowired
    UserRepository repository;

    @Autowired
    TestEntityManager entityManager;

    @Test
    void storesAndReloadsUser() {
        User user = new User(
            7L,
            "alice@example.com",
            "Alice"
        );

        repository.save(user);
        entityManager.flush();
        entityManager.clear();

        User reloaded = repository
            .findByTenantIdAndEmail(7L, "alice@example.com")
            .orElseThrow();

        assertEquals("Alice", reloaded.getDisplayName());
    }
}
~~~

Giả định `User`, repository method và migration đã tồn tại. Test dùng `@DataJpaTest` transaction/rollback defaults, container bean và DB connection details do Spring Boot service connection cung cấp.

### 20.3. application-test.properties

~~~properties
spring.jpa.hibernate.ddl-auto=validate

spring.flyway.enabled=true

logging.level.org.hibernate.SQL=DEBUG
~~~

Chỉ bật SQL debug trong profile test/local cần quan sát. Không bật bind parameter TRACE nếu dữ liệu fixture có thông tin nhạy cảm.

### 20.4. Vì sao ví dụ không tự tạo bảng bằng Hibernate?

Mục tiêu của integration test là kiểm tra schema production migrations và Hibernate mappings có tương thích. Nếu Hibernate tự tạo schema từ annotations, test có thể pass dù Flyway migration đang thiếu partial index, trigger hoặc column.

## 21. Quyết định chi phí: khi nào không nên chạy container?

Testcontainers có startup cost và phụ thuộc Docker. Không cần chạy một DB container cho mọi test method nếu có thể tái sử dụng an toàn.

Một chiến lược cân bằng:

- Unit tests/domain: chạy nhanh, không DB.
- JPA mapping tests cơ bản: H2 nếu semantics portable và không cần kiểm chứng production DB.
- Repository integration: một container theo Spring context hoặc test suite.
- DB-specific tests: cùng engine/version production.
- Migration/locking/concurrency tests: container thật, transactions/fixtures riêng.
- Performance/load tests: môi trường benchmark gần production, không suy từ container nhỏ.

Container reuse chỉ tối ưu lifecycle; **nó không thay thế data isolation**. Nếu suite dùng một container lâu, test phải tự quản lý fixtures/schema/transactions nghiêm ngặt.

### 21.1. Testcontainers reusable mode

Một số cấu hình Testcontainers hỗ trợ reuse container giữa các lần chạy local khi bật opt-in ở môi trường developer. Đây không phải mặc định nên bật cho CI:
- State cũ có thể tồn tại.
- Version/image/config đổi có thể tạo mismatch.
- Resource cleanup không còn đơn giản như ephemeral containers.
- Test phụ thuộc data còn sót có thể pass/fail không ổn định.

Nếu dùng reusable mode, chỉ dùng cho local workflow có reset database/schema rõ ràng; CI nên dùng lifecycle ephemeral và cleanup xác định.

### 21.2. Chọn size phù hợp

Một PostgreSQL container đơn giản thường đủ cho repository tests. Nhưng performance benchmark không thể kết luận production capacity từ container với CPU/RAM/network khác production.

Đừng dùng Testcontainers như cách giả lập:
- Replication cluster.
- Failover.
- Production connection pool contention.
- Distributed database topology.
- Managed cloud database latency.

Những mục tiêu này cần environment/infrastructure test chuyên biệt.
+
## 22. Bài tập thực hành

### Bài 1 — H2 hay Testcontainers?

Một service chỉ tính tổng tiền từ các Java objects, không truy cập DB.

**Hỏi:** Có cần PostgreSQL container không?

**Đáp án:** Không. Unit test thuần Java là đủ.

### Bài 2 — Partial unique index

Ứng dụng dùng PostgreSQL `WHERE deleted_at IS NULL` trong unique index.

**Hỏi:** H2 test có chứng minh PostgreSQL constraint đúng không?

**Đáp án:** Không. Dùng PostgreSQL container đúng version và chạy migration thật.

### Bài 3 — Docker runtime

Test báo không tìm thấy Docker environment.

**Hỏi:** Có phải Hibernate mapping sai không?

**Đáp án:** Không nhất thiết. Kiểm tra Docker daemon, endpoint, socket/permissions, network và image pull trước.

### Bài 4 — Port

Developer đang chạy PostgreSQL local trên 5432, Testcontainers cũng chạy.

**Hỏi:** Có bắt buộc conflict không?

**Đáp án:** Không. Testcontainers thường map container port sang host port khả dụng; lấy URL từ container thay vì hard-code 5432.

### Bài 5 — Image tag

Test dùng `postgres:latest`.

**Hỏi:** Rủi ro?

**Đáp án:** Một lần pull có thể đổi engine version và semantics; pin version/digest tương thích production.

### Bài 6 — JUnit static container

`@Container static` trong class có ý nghĩa gì?

**Đáp án:** Container được tái sử dụng cho test methods của class và dừng sau class theo JUnit Testcontainers extension lifecycle.

### Bài 7 — Instance container

`@Container` field không static có lifecycle thế nào?

**Đáp án:** Thường start/stop mỗi test method; isolation cao hơn nhưng startup cost lớn.

### Bài 8 — Spring Boot service connection

**Hỏi:** Cần dependency nào ngoài Testcontainers module để dùng `@ServiceConnection`?

**Đáp án:** Với Spring Boot 3.1+ cần integration module `spring-boot-testcontainers` trong test scope, cùng Testcontainers module/driver phù hợp.

### Bài 9 — @DataJpaTest

Test vẫn dùng embedded H2 dù có PostgreSQL container.

**Hỏi:** Cần xem setting nào?

**Đáp án:** `@AutoConfigureTestDatabase(replace = Replace.NONE)` và kiểm tra service connection/datasource thực tế.

### Bài 10 — Dynamic properties

**Hỏi:** Vì sao dùng `postgres.getJdbcUrl()` thay cho `jdbc:postgresql://localhost:5432/app`?

**Đáp án:** Host port được map động; URL từ container phản ánh connection thực tế.

### Bài 11 — Flyway

Production dùng Flyway nhưng test chỉ dùng Hibernate `create-drop`.

**Hỏi:** Test đã kiểm chứng migrations chưa?

**Đáp án:** Chưa. Dùng container sạch và để Flyway chạy migrations production; Hibernate validate schema.

### Bài 12 — withInitScript

**Hỏi:** Có nên tạo toàn bộ application schema trong init script và Flyway cùng lúc?

**Đáp án:** Không. Dễ có hai nguồn schema lệch nhau. Dùng init script cho bootstrap đặc thù; migration tool tạo schema nghiệp vụ.

### Bài 13 — flush vs commit

Test gọi `entityManager.flush()` rồi assert constraint không lỗi.

**Hỏi:** Có chứng minh deferred constraint commit thành công không?

**Đáp án:** Không. Constraint deferred có thể chỉ kiểm tra khi transaction commit; cần test commit thật.

### Bài 14 — Test rollback

`@DataJpaTest` rollback sau mỗi method.

**Hỏi:** Có phù hợp để kiểm tra after-commit event không?

**Đáp án:** Không tự động. Cần transaction hoàn tất commit có chủ đích và kiểm tra event handler/outbox sau commit.

### Bài 15 — Concurrency

Hai threads dùng cùng một EntityManager injected vào test để insert đồng thời.

**Hỏi:** Có hợp lệ không?

**Đáp án:** Không. EntityManager/Session không thread-safe; mỗi thread phải dùng transaction và persistence context riêng.

### Bài 16 — Fixture visibility

Test setup insert user trong transaction chưa commit; worker transaction khác không thấy user.

**Hỏi:** Vì sao?

**Đáp án:** Transaction khác không mặc định thấy uncommitted data; commit fixture trước hoặc tạo fixture trong từng worker transaction theo scenario.

### Bài 17 — Spring context cache

Class A kết thúc và container dừng, Class B tái sử dụng Spring context cũ.

**Hỏi:** Lỗi nào có thể gặp?

**Đáp án:** DataSource trỏ vào container/port đã dừng. Gắn container lifecycle với Spring context bean hoặc dùng suite singleton phù hợp.

### Bài 18 — Parallel tests

Hai test cùng insert `test@example.com` trên một database container chung.

**Hỏi:** Vì sao đôi lúc một test fail?

**Đáp án:** Shared fixture key và parallel execution gây unique conflict. Dùng UUID/namespace/schema isolation hoặc tắt parallelism cho nhóm đó.

### Bài 19 — Ryuk

CI bị chặn resource reaper.

**Hỏi:** Hệ quả có thể là gì?

**Đáp án:** Container/network/volume có thể bị rò rỉ hoặc startup fail. Khắc phục runtime/permissions/cleanup policy; không tắt cleanup mà không có thay thế.

### Bài 20 — Reusable container

Developer bật reusable container và test pass ở lần hai dù lần đầu fail.

**Hỏi:** Cần nghi ngờ điều gì?

**Đáp án:** Database state cũ, schema/data không được reset hoặc test phụ thuộc thứ tự. Reuse không thay thế isolation.

### Bài 21 — Optimistic locking

Hai transactions cùng load version V, T1 commit update, T2 commit update.

**Hỏi:** Nên kiểm tra trên một DB container không?

**Đáp án:** Có, nếu muốn xác nhận behavior Hibernate/DB/driver thực tế; dùng EntityManagers riêng và transactions riêng.

### Bài 22 — Native SQL

Application chạy PostgreSQL `ON CONFLICT ... RETURNING`.

**Hỏi:** Có thể chỉ test bằng H2 không?

**Đáp án:** Không nếu muốn xác nhận PostgreSQL syntax/semantics. Dùng PostgreSQL container.

### Bài 23 — Test migration

Một migration tạo index thất bại khi container sạch nhưng local DB pass.

**Hỏi:** Điều đó gợi ý gì?

**Đáp án:** Local DB có thể đã có object/data state từ trước; container sạch giúp phát hiện migration không tự tái lập được.

### Bài 24 — Testcontainers và performance

Một query mất 20 ms trong container trên laptop.

**Hỏi:** Có thể kết luận production query dưới 20 ms không?

**Đáp án:** Không. Testcontainers chủ yếu xác nhận behavior/compatibility; performance cần environment, dataset, hardware, network và load phù hợp.

## 23. Checklist triển khai trong dự án

Trước khi thêm Testcontainers vào một module, xác định:

1. Test đang cần xác nhận behavior nào phụ thuộc database thật?
2. Engine/version production là gì?
3. Có cần extension, collation, timezone hoặc SQL mode đặc thù không?
4. Testcontainers/JUnit/Spring Boot versions có được quản lý bằng BOM không?
5. Docker runtime có sẵn ở local và CI không?
6. Container lifecycle gắn với test class hay Spring ApplicationContext?
7. Spring TestContext cache có thể reuse context sau khi container dừng không?
8. `@DataJpaTest` có vô tình thay datasource bằng embedded DB không?
9. Flyway/Liquibase migrations production có chạy trên DB trống không?
10. Hibernate `ddl-auto` có đang che migration failure không?
11. Fixtures có isolated và parallel-safe không?
12. Test có cần commit thật hoặc hai transactions độc lập không?
13. Database-specific assertions có chạy đúng engine/version không?
14. SQL/bind logs có vô tình lộ dữ liệu nhạy cảm không?
15. CI có thực sự chạy integration suite, hay skip khi Docker unavailable?
16. Cleanup container/volume/network có hoạt động không?
17. Container reuse có tạo stale state không?
18. Performance claims có được đo trong môi trường benchmark phù hợp không?

## 24. Tổng kết

### 24.1. Cách lựa chọn nhanh

| Nhu cầu | Lựa chọn |
|---|---|
| Kiểm thử domain Java thuần | Unit test, không DB |
| CRUD/JPQL portable cơ bản | H2 có thể đủ |
| PostgreSQL partial indexes/JSONB/ON CONFLICT | PostgreSQL Testcontainer |
| MySQL generated columns/collation | MySQL Testcontainer |
| Flyway/Liquibase migration | DB container sạch + migration thật |
| Locking/concurrency/transaction isolation | DB container + connections/transactions riêng |
| Spring Boot integration | Container bean + `@ServiceConnection` hoặc `@DynamicPropertySource` |
| Test suite lớn dùng Spring context chung | Container lifecycle theo context/suite |
| Performance/load production-like | Benchmark environment riêng, không suy từ container nhỏ |

### 24.2. Năm nguyên tắc

1. **Dùng DB thật khi behavior phụ thuộc DB thật.** H2 không thể chứng minh mọi semantics PostgreSQL/MySQL.
2. **Để migrations production tạo schema.** Không dùng Hibernate schema generation để vô tình bỏ qua lỗi DDL.
3. **Quản lý lifecycle cùng test context.** Container đã dừng nhưng Spring context còn cache là nguồn lỗi phổ biến.
4. **Tách transactions và persistence contexts trong concurrency tests.** Không chia sẻ EntityManager/Session giữa threads.
5. **Container reuse không đồng nghĩa data isolation.** Dùng fixtures, schema/tenant namespaces và cleanup rõ ràng.

### 24.3. Sơ đồ ghi nhớ

~~~text
Có cần DB thật không?
        |
        +-- Không: unit/H2 test phù hợp
        |
        +-- Có: chọn engine/version production
                    |
                    v
              Testcontainers
                    |
                    v
        Khởi động DB + wait strategy
                    |
                    v
          Spring DataSource connection
                    |
                    v
        Flyway/Liquibase migrations
                    |
                    v
        Hibernate validate + fixtures
                    |
                    v
       Test query/constraint/transaction
                    |
                    v
      Assertions + cleanup + CI reporting
~~~

Một câu hỏi chẩn đoán hữu ích:

> “Test này cần chứng minh điều gì mà mock hoặc H2 không thể chứng minh, và nó đang chạy trên database/version nào?”

## Tài liệu chính thức

- [Testcontainers for Java](https://java.testcontainers.org/) — hướng dẫn cài đặt, modules và lifecycle.
- [Testcontainers JUnit 5 Quickstart](https://java.testcontainers.org/test_framework_integration/junit_5/) — `@Testcontainers`, `@Container` và JUnit Jupiter.
- [Testcontainers PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/) — PostgreSQL container, JDBC URL và init script.
- [Testcontainers MySQL Module](https://java.testcontainers.org/modules/databases/mysql/) — MySQL container.
- [Testcontainers JDBC Support](https://java.testcontainers.org/modules/databases/jdbc/) — JDBC URL integration.
- [Testcontainers Lifecycle and Reusable Containers](https://java.testcontainers.org/features/reuse/) — resource lifecycle/reuse caveats.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html) — service connections và container integration.
- [Spring Boot — Data JPA](https://docs.spring.io/spring-boot/reference/data/sql.html#data.sql.jpa-and-spring-data) — JPA datasource/configuration.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/testing.html) — Spring TestContext, transactions và test utilities.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — repository testing/mapping behavior.
- [Flyway Documentation](https://documentation.red-gate.com/fd) — migrations và schema versioning.
- [Liquibase Documentation](https://docs.liquibase.com/) — changelogs và database migrations.
- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — dialect, schema validation, transactions và provider behavior.

> Các ví dụ sử dụng API phổ biến của Testcontainers/JUnit Jupiter và Spring Boot 3.1+; package names, service connection support, lifecycle integration và module coordinates có thể thay đổi theo major version. Hãy dùng dependency BOM nhất quán và xác nhận trên phiên bản trong dự án. Testcontainers tạo môi trường database thật phục vụ kiểm thử; nó không tự bảo đảm test isolation, migration correctness hoặc production performance nếu test không thiết kế các điều đó.


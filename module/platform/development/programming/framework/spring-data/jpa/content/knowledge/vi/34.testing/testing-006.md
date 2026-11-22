# Dùng Testcontainers với PostgreSQL hoặc MySQL

## 1. Testcontainers giải quyết vấn đề gì trong kiểm thử Spring Data JPA?

Một repository có thể chạy tốt với H2 nhưng gặp lỗi khi triển khai trên PostgreSQL hoặc MySQL. Hai database có thể khác nhau về cú pháp SQL, kiểu dữ liệu, collation, cách so sánh chuỗi, xử lý JSON, sequence/identity, locking, constraint và hành vi của dialect.

Ví dụ, một JPQL đơn giản có thể chạy trên nhiều database, nhưng native query dùng toán tử JSON của PostgreSQL sẽ không chạy trên H2. Migration có thể chứa kiểu dữ liệu hoặc cú pháp riêng của MySQL. Một test chỉ dùng database in-memory không chứng minh rằng ứng dụng hoạt động đúng với database production.

**Testcontainers** tạo và quản lý database tạm thời trong Docker container ngay trong lúc chạy test. Test có thể kết nối tới một PostgreSQL hoặc MySQL thật, với JDBC driver thật và SQL engine thật. Sau khi test hoàn tất, container được dừng và tài nguyên được dọn theo lifecycle đã cấu hình.

Với Spring Data JPA, Testcontainers thường được dùng để kiểm thử:

- Repository query, derived query, JPQL và native SQL.
- Entity mapping, enum, UUID, decimal, date/time và kiểu dữ liệu riêng của database.
- Unique constraint, foreign key, index và transaction.
- Pagination, sorting, locking và concurrency.
- Flyway/Liquibase migration.
- Fetch plan, lazy loading và các truy vấn phát sinh từ Hibernate.
- Hành vi khác biệt giữa database phát triển và database production.

Testcontainers không thay thế unit test. Unit test vẫn phù hợp để kiểm tra logic Java thuần. Testcontainers bổ sung integration test cho phần cần database thật.

## 2. Kiến trúc khi chạy Spring Data JPA trên container

Luồng cơ bản:

```text
JUnit test
   |
   v
Spring TestContext
   |
   +---- Spring Data JPA repository
   |
   +---- EntityManager / Hibernate
   |
   +---- DataSource / JDBC driver
                 |
                 v
          Testcontainers
                 |
                 v
       PostgreSQL hoặc MySQL
          trong Docker
```

Testcontainers chọn image database, khởi động container, chờ database sẵn sàng rồi cung cấp host, port, database name, username và password động. Spring Boot dùng các thông tin này để cấu hình DataSource.

Không nên hard-code `localhost:5432` hoặc `localhost:3306` trong test. Testcontainers có thể ánh xạ port ngẫu nhiên trên máy host; hãy lấy thông tin kết nối từ container hoặc để Spring Boot tự cấu hình bằng `@ServiceConnection`.

Database trong container là database thật. Hibernate vẫn dùng JDBC và dialect tương ứng; các câu SQL được thực thi bởi PostgreSQL/MySQL chứ không phải H2 giả lập.

## 3. Chuẩn bị môi trường

### 3.1. Yêu cầu

Trước khi chạy test, máy phát triển hoặc CI cần có:

- Java tương thích với Spring Boot của dự án (ví dụ Java 17+ cho nhiều dự án Boot 3).
- Maven hoặc Gradle.
- Docker Engine, Docker Desktop hoặc Docker environment được Testcontainers hỗ trợ.
- Quyền truy cập Docker daemon/socket.
- Kết nối tới registry để tải image database nếu image chưa có trong cache.

Không cần cài PostgreSQL/MySQL trực tiếp trên máy host. Docker phải hoạt động và test process phải truy cập được Docker daemon.

Kiểm tra Docker trước khi chạy:

```bash
docker version
docker info
```

Nếu hai lệnh này không chạy được, hãy xử lý Docker daemon/context/permission trước. Testcontainers không tự cài hoặc khởi động Docker Engine.

### 3.2. Chọn image database

Ví dụ image có tag cố định:

```text
postgres:16-alpine
mysql:8.4
```

Hãy chọn phiên bản tương ứng với database production. Không nên dùng tag `latest` trong test suite vì cùng một commit có thể chạy với engine khác nhau ở hai thời điểm.

Nếu production dùng extension PostgreSQL, collation đặc biệt, MySQL SQL mode hoặc timezone riêng, hãy cấu hình container test tương ứng. Một container database mặc định không tự tái tạo toàn bộ cấu hình production.

## 4. Thêm dependency

Testcontainers có các module riêng cho từng database và framework test. Các dependency chỉ cần ở test scope, ngoại trừ JDBC driver mà ứng dụng sử dụng ở runtime.

### 4.1. Maven với Spring Boot 3.x và Testcontainers 1.x

Ví dụ cấu hình cho Spring Boot 3.x, JUnit Jupiter và PostgreSQL:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
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
```

Spring Boot dependency management có thể quản lý phiên bản cho các dependency phù hợp. Nếu dự án không quản lý Testcontainers qua Spring Boot BOM, import `org.testcontainers:testcontainers-bom` và chọn một phiên bản 1.x thống nhất cho tất cả module Testcontainers.

Nếu dùng MySQL, thay driver PostgreSQL bằng MySQL Connector/J và thay module Testcontainers PostgreSQL bằng module MySQL:

```xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <scope>runtime</scope>
</dependency>

<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>mysql</artifactId>
    <scope>test</scope>
</dependency>
```

Không cần khai báo cả hai database driver nếu ứng dụng chỉ chạy với một database. Nếu test matrix kiểm thử cả PostgreSQL và MySQL, có thể để cả hai driver ở test/runtime classpath và chọn container cho từng test profile.

### 4.2. Gradle với Spring Boot 3.x và Testcontainers 1.x

Ví dụ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

Với MySQL:

```groovy
dependencies {
    runtimeOnly 'com.mysql:mysql-connector-j'
    testImplementation 'org.testcontainers:mysql'
}
```

Nếu dùng version catalog hoặc dependency management plugin, khai báo phiên bản tại một nơi duy nhất. Không để module `junit-jupiter`, `postgresql` và `mysql` dùng các phiên bản Testcontainers khác nhau.

### 4.3. Lưu ý Testcontainers 2.x và Spring Boot 4.x

Testcontainers 2.0 đổi artifact name và package của các container class. Không trộn dependency hoặc import của hai major version.

| Thành phần | Testcontainers 1.x | Testcontainers 2.x |
|---|---|---|
| JUnit Jupiter | `org.testcontainers:junit-jupiter` | `org.testcontainers:testcontainers-junit-jupiter` |
| PostgreSQL | `org.testcontainers:postgresql` | `org.testcontainers:testcontainers-postgresql` |
| MySQL | `org.testcontainers:mysql` | `org.testcontainers:testcontainers-mysql` |
| PostgreSQL class | `org.testcontainers.containers.PostgreSQLContainer` | `org.testcontainers.postgresql.PostgreSQLContainer` |
| MySQL class | `org.testcontainers.containers.MySQLContainer` | `org.testcontainers.mysql.MySQLContainer` |

Testcontainers 2.x dùng package module riêng, ví dụ `org.testcontainers.postgresql` và `org.testcontainers.mysql`. Spring Boot 4.x chuyển một số package test slice, chẳng hạn `DataJpaTest` sang `org.springframework.boot.data.jpa.test.autoconfigure`. Hãy dùng dependency và import phù hợp major version của Spring Boot/Testcontainers trong dự án; không sao chép import 1.x vào dự án 2.x.

Các ví dụ code tiếp theo dùng package Testcontainers 1.x để phù hợp với Spring Boot 3.x. Nếu dự án đã dùng Testcontainers 2.x, giữ nguyên logic và đổi dependency/import theo bảng trên.

## 5. Cách khuyến nghị: Spring Boot @ServiceConnection

### 5.1. @ServiceConnection là gì?

Từ Spring Boot 3.1, `@ServiceConnection` cho phép Spring Boot tự tạo connection details từ Testcontainers container. Với PostgreSQL/MySQL container có kiểu cụ thể, Spring Boot có thể suy ra JDBC URL, username và password mà không cần tự gán từng property.

Để dùng annotation này, thêm dependency test:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-testcontainers</artifactId>
    <scope>test</scope>
</dependency>
```

Service connection details được ưu tiên hơn các datasource connection properties thông thường. Container phải có kiểu cụ thể mà Spring Boot nhận diện được, chẳng hạn `PostgreSQLContainer` hoặc `MySQLContainer`.

### 5.2. Khai báo PostgreSQL container như Spring bean

Tạo file `src/test/java/com/example/test/PostgresTestConfiguration.java`:

```java
package com.example.test;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.PostgreSQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class PostgresTestConfiguration {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> postgresContainer() {
        return new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("jpa_test")
            .withUsername("test")
            .withPassword("test");
    }
}
```

Spring quản lý lifecycle của container bean:

1. Tạo và khởi động container trước các bean ứng dụng phụ thuộc database.
2. Tạo connection details từ container.
3. Cấu hình DataSource cho Hibernate và Spring Data JPA.
4. Dừng container khi ApplicationContext tương ứng bị đóng.

Đây là cách phù hợp khi nhiều test dùng chung một Spring context được cache. Container còn hoạt động trong suốt vòng đời context; datasource không bị trỏ tới một container đã dừng sau khi một test class kết thúc.

### 5.3. Dùng container cho @DataJpaTest

Ví dụ test slice:

```java
package com.example.customer;

import com.example.test.PostgresTestConfiguration;
import jakarta.persistence.EntityManager;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Import(PostgresTestConfiguration.class)
class CustomerRepositoryIntegrationTest {

    @Autowired
    private CustomerRepository repository;

    @Autowired
    private EntityManager entityManager;

    @Test
    void savesAndReadsCustomerFromPostgres() {
        Customer saved = repository.save(
            new Customer("customer@example.test")
        );

        repository.flush();
        Long id = saved.getId();

        entityManager.clear();

        Customer reloaded = repository.findById(id).orElseThrow();

        assertThat(reloaded.getEmail())
            .isEqualTo("customer@example.test");
    }
}
```

`@DataJpaTest` chỉ nạp các thành phần cần cho persistence layer như entity, repository, EntityManager và DataSource. Nó không tự nạp toàn bộ service/controller của ứng dụng.

`@AutoConfigureTestDatabase(replace = NONE)` rất quan trọng: `@DataJpaTest` mặc định có thể thay DataSource bằng database nhúng như H2 nếu có trên classpath. Đặt `replace = NONE` để test sử dụng DataSource từ Testcontainers.

Trong ví dụ, `repository.flush()` đẩy INSERT xuống database và `entityManager.clear()` loại entity đang managed khỏi persistence context. Lệnh `findById()` sau đó phải đọc lại dữ liệu thông qua database thay vì trả object đang nằm sẵn trong first-level cache.

Ví dụ giả định entity `Customer` có constructor nhận email, thuộc tính `email` và getter `getEmail()`; repository kế thừa `JpaRepository<Customer, Long>`. Đây là test tích hợp trong dự án Spring Boot, không phải chương trình Java độc lập có thể chạy chỉ bằng `javac`.

### 5.4. Dùng PostgreSQL cho @SpringBootTest

Nếu cần kiểm tra toàn bộ application context, service, controller và repository, có thể dùng cùng test configuration:

```java
@SpringBootTest
@Import(PostgresTestConfiguration.class)
class CustomerApplicationIntegrationTest {

    @Autowired
    private CustomerService customerService;

    @Test
    void loadsApplicationAgainstPostgres() {
        assertThat(customerService).isNotNull();
    }
}
```

`@SpringBootTest` khởi tạo ứng dụng đầy đủ nên thời gian chạy thường dài hơn `@DataJpaTest`. Chỉ dùng khi cần xác minh wiring hoặc luồng xuyên nhiều tầng. Test repository/query đơn lẻ nên ưu tiên slice test.

## 6. Dùng MySQL thay cho PostgreSQL

### 6.1. Tạo MySQL container

Nếu production dùng MySQL, hãy chạy test trên MySQL thật:

```java
package com.example.test;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.containers.MySQLContainer;

@TestConfiguration(proxyBeanMethods = false)
public class MySqlTestConfiguration {

    @Bean
    @ServiceConnection
    MySQLContainer<?> mysqlContainer() {
        return new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("jpa_test")
            .withUsername("test")
            .withPassword("test");
    }
}
```

Test sử dụng cấu hình này:

```java
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Import(MySqlTestConfiguration.class)
class CustomerRepositoryMySqlTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void persistsCustomerOnMysql() {
        Customer saved = repository.save(
            new Customer("mysql@example.test")
        );

        repository.flush();

        assertThat(saved.getId()).isNotNull();
    }
}
```

Cần có MySQL Connector/J ở runtime/test classpath và module Testcontainers MySQL ở test scope.

### 6.2. PostgreSQL và MySQL không thay thế lẫn nhau

Không nên chạy test PostgreSQL rồi kết luận ứng dụng chắc chắn chạy đúng trên MySQL, hoặc ngược lại. Hai database có khác biệt thực tế:

| Khía cạnh | PostgreSQL | MySQL |
|---|---|---|
| Kiểu dữ liệu | Có JSONB, UUID và nhiều kiểu chuyên biệt | Có JSON, binary và kiểu riêng |
| So sánh chuỗi | Phụ thuộc collation; thường phân biệt hoa/thường theo collation | Collation mặc định có thể không phân biệt hoa/thường |
| Generated ID | Identity/sequence tùy mapping | AUTO_INCREMENT thường gặp |
| SQL function | Có hàm/toán tử PostgreSQL-specific | Có hàm/toán tử MySQL-specific |
| Locking | Có semantics và loại lock riêng | InnoDB có locking behavior riêng |
| Migration | Có thể dùng cú pháp/extension PostgreSQL | Có thể dùng cú pháp và engine MySQL |

Nếu production dùng PostgreSQL, hãy kiểm thử bằng PostgreSQL. Nếu ứng dụng hỗ trợ cả hai engine, tạo hai test configuration hoặc hai CI job độc lập. Không nên dựa vào H2 mode để mô phỏng hoàn toàn hai database này.

## 7. Cách cũ: @Testcontainers, @Container và @DynamicPropertySource

Trước Spring Boot 3.1 hoặc khi không dùng service connection, có thể kết nối bằng cách đăng ký datasource properties thủ công.

Ví dụ PostgreSQL với Testcontainers 1.x:

```java
package com.example.customer;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@DataJpaTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class CustomerRepositoryDynamicPropertiesTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("jpa_test")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void datasourceProperties(
            DynamicPropertyRegistry registry) {

        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void containerIsRunning() {
        assertThat(postgres.isRunning()).isTrue();
    }
}
```

Các import AssertJ cần được thêm nếu dùng assertion như ví dụ; test này chỉ minh họa cách đăng ký properties. Không thêm `@ServiceConnection` cùng lúc với `@DynamicPropertySource` cho cùng một DataSource nếu không có lý do rõ ràng.

Cơ chế:

- `@Testcontainers` kích hoạt JUnit Jupiter extension của Testcontainers.
- `@Container` đánh dấu container để extension quản lý.
- Field static được khởi động một lần trước các test method trong class và dừng sau class.
- `@DynamicPropertySource` đưa JDBC URL, username và password thực tế vào Spring Environment.
- `@AutoConfigureTestDatabase(replace = NONE)` giữ lại DataSource trỏ tới container.

### 7.1. Cảnh báo về Spring context cache

JUnit extension dừng static container sau khi test class kết thúc. Trong khi đó, Spring TestContext Framework có thể giữ và tái sử dụng ApplicationContext cho test class khác. Nếu context cache giữ DataSource phụ thuộc container đã dừng, test tiếp theo có thể lỗi kết nối.

Khi nhiều test class dùng chung context, ưu tiên quản lý container như Spring bean bằng `@Bean` và `@ServiceConnection`, hoặc dùng cơ chế import container declaration được Spring quản lý. Cách JUnit extension đơn giản phù hợp với test class độc lập có lifecycle khớp với container.

Không khắc phục lỗi này bằng cách gọi `start()` ngẫu nhiên trong từng test method. Hãy thống nhất một cơ chế lifecycle và để Spring/Testcontainers quản lý container theo đúng phạm vi.

## 8. JDBC URL đặc biệt của Testcontainers

Testcontainers có thể tạo database từ JDBC URL mà không cần khai báo container field:

```properties
spring.test.database.replace=none
spring.datasource.url=jdbc:tc:postgresql:16-alpine:///jpa_test
```

Tiền tố `jdbc:tc:` báo cho Testcontainers tạo container database tương ứng. Testcontainers JDBC driver quản lý việc khởi động database khi ứng dụng mở kết nối.

Cách này ngắn gọn cho test đơn giản, nhưng ít linh hoạt hơn container object khi cần:
- Tùy chỉnh database name, username, password hoặc command.
- Copy file init vào container.
- Chờ readiness hoặc kiểm tra container.
- Kết hợp nhiều service.
- Dùng Spring Boot service connection.

Khi dùng JDBC URL mode, phải có module database, JDBC driver và Testcontainers JDBC driver tương ứng trên test runtime classpath. Không trộn URL `jdbc:tc:` với URL `jdbc:postgresql://` lấy từ container field trong cùng cấu hình DataSource.

## 9. Kiểm thử schema và migration

### 9.1. Dùng Flyway hoặc Liquibase

Nếu ứng dụng quản lý schema bằng Flyway/Liquibase, integration test nên chạy migration trên chính container database.

Ví dụ cấu trúc Flyway:

```text
src/main/resources/
└── db/
    └── migration/
        ├── V1__create_customer.sql
        └── V2__add_customer_status.sql
```

Khi Spring Boot khởi động DataSource từ Testcontainers, Flyway có thể chạy migration trên database đó nếu dependency và cấu hình migration đã được khai báo. Test khi đó kiểm tra cả:
- Migration có cú pháp hợp lệ trên database thực.
- Schema cuối cùng khớp entity mapping.
- Repository query chạy được với schema đã migrate.
- Constraint/index được tạo đúng.

Không nên để Hibernate tự tạo schema bằng `ddl-auto=create` trong khi mục tiêu test là xác minh migration. Với migration-based application, thường dùng `validate` hoặc `none` theo chiến lược của dự án và để Flyway/Liquibase quản lý DDL.

### 9.2. Phân biệt kiểm thử mapping và kiểm thử migration

`@DataJpaTest` có thể kiểm tra mapping và repository. Nhưng nếu cấu hình test dùng Hibernate tự tạo schema, migration production có thể chưa từng chạy.

Để kiểm tra migration:
1. Khởi động container rỗng.
2. Để Flyway/Liquibase chạy từ version đầu.
3. Kiểm tra schema hoặc thực hiện repository operation.
4. Kiểm tra dữ liệu/constraint được tạo đúng.
5. Chạy lại migration theo quy trình nâng cấp nếu dự án có nhiều version.

Không dùng một database container đã có schema từ lần chạy trước để kết luận migration từ đầu hoạt động. Mỗi lần test cần có trạng thái khởi tạo xác định.

### 9.3. Seed dữ liệu

Có thể tạo dữ liệu test bằng repository, EntityManager, `@Sql` hoặc script init. Với JPA repository test, tạo fixture trong từng test thường giúp dữ liệu và mục đích test rõ ràng.

Nếu dùng script SQL, hãy viết đúng dialect của database mục tiêu. Một script PostgreSQL có thể không chạy trên MySQL và ngược lại.

## 10. Transaction và tính cô lập giữa các test

### 10.1. @DataJpaTest mặc định rollback

`@DataJpaTest` thường chạy mỗi test method trong transaction và rollback khi kết thúc. Điều này giúp các test không để lại dữ liệu cho test kế tiếp.

Ví dụ:

```java
@Test
void findsCustomerByEmail() {
    repository.save(new Customer("one@example.test"));
    repository.flush();

    Optional<Customer> result =
        repository.findByEmail("one@example.test");

    assertThat(result).isPresent();
}
```

Dữ liệu được ghi trong transaction test và rollback sau method. Nếu test cần xác nhận SQL constraint hoặc lỗi xảy ra ở database, hãy gọi `flush()`; nhiều lỗi chỉ xuất hiện khi Hibernate gửi SQL xuống database, không phải ngay tại lệnh `save()`.

### 10.2. Rollback không thay thế mọi cleanup

Một số thao tác không được rollback giống INSERT/UPDATE thông thường, chẳng hạn sequence ở PostgreSQL có thể đã tăng dù transaction rollback. Không assert rằng ID tiếp theo luôn bắt đầu từ 1.

Nếu test dùng `@Commit`, `@Transactional(propagation = NOT_SUPPORTED)` hoặc thực thi thao tác qua HTTP server thread, dữ liệu có thể không nằm trong transaction test method. Khi đó cần cleanup rõ ràng bằng repository delete, truncate hoặc database/schema riêng.

### 10.3. Không phụ thuộc thứ tự test

Mỗi test nên tự tạo dữ liệu và không phụ thuộc test khác đã chạy trước. Tránh:
- Dùng chung email/unique key mà không dọn dữ liệu.
- Assert tổng số row trong bảng khi test khác có thể ghi thêm.
- Dựa vào ID tăng liên tục.
- Chia sẻ mutable static fixture.
- Dùng thứ tự test để chuẩn bị database.

Nếu nhiều test dùng cùng container, container có thể được giữ sống nhưng dữ liệu vẫn cần được cô lập.

### 10.4. Chạy song song

Một container PostgreSQL/MySQL dùng chung không tự động cô lập dữ liệu cho nhiều test chạy song song. Có thể gặp unique-key collision, test đọc dữ liệu của test khác hoặc truncate ảnh hưởng test đang chạy.

Nếu bật parallel test execution, hãy:
- Tạo dữ liệu có ID/unique key riêng.
- Dùng transaction và rollback khi phù hợp.
- Dùng schema/database riêng cho worker hoặc test class nếu cần.
- Tránh truncate bảng dùng chung trong khi test khác đang chạy.
- Đánh giá giới hạn connection pool và tài nguyên Docker.

JUnit Jupiter Testcontainers extension chủ yếu được thiết kế và kiểm thử với thực thi tuần tự; không bật parallel một cách mặc định khi các test chia sẻ container và database state.

## 11. Kiểm thử repository với dữ liệu thực

Một integration test tốt cần xác nhận hành vi của query, không chỉ xác nhận Spring context khởi động.

Ví dụ:

```java
@Test
void filtersAndSortsCustomers() {
    repository.saveAll(List.of(
        new Customer("zoe@example.test"),
        new Customer("anna@example.test"),
        new Customer("minh@example.test")
    ));
    repository.flush();

    List<Customer> result =
        repository.findAll(
            Sort.by(Sort.Direction.ASC, "email")
        );

    assertThat(result)
        .extracting(Customer::getEmail)
        .containsExactly(
            "anna@example.test",
            "minh@example.test",
            "zoe@example.test"
        );
}
```

Test này kiểm tra sắp xếp do database thực hiện. Dữ liệu fixture cần bảo đảm không có row khác ảnh hưởng kết quả; có thể dùng repository method lọc theo một nhóm test hoặc xóa dữ liệu trong transaction test trước khi tạo fixture.

Các tình huống đáng kiểm tra trên database thật:

- Query dùng native SQL hoặc function riêng database.
- Unique constraint và foreign key.
- Giá trị decimal và rounding.
- Timestamp, timezone và precision.
- Collation và so sánh không phân biệt hoa/thường.
- Pagination kết hợp JOIN.
- Locking với `@Lock`.
- JSON/array/enum hoặc kiểu dữ liệu chuyên biệt.
- Bulk update/delete và persistence context.
- Transaction isolation và concurrent update.

## 12. So sánh database thật với H2

H2 vẫn hữu ích cho test nhanh, nhưng không nên dùng làm bằng chứng cuối cùng khi production chạy PostgreSQL/MySQL.

| Tiêu chí | H2 in-memory | Testcontainers PostgreSQL/MySQL |
|---|---|---|
| Khởi động | Rất nhanh, không cần Docker | Cần Docker và khởi động container |
| SQL engine | H2 | Engine gần production |
| Dialect | H2 dialect | PostgreSQL/MySQL dialect |
| Native query vendor-specific | Có thể không tương thích | Kiểm tra đúng database |
| Migration | Có thể khác cú pháp | Chạy trên database mục tiêu |
| CI setup | Nhẹ | Cần Docker runtime |
| Mức độ production parity | Giới hạn | Cao hơn nếu khớp version/config |

Không cần thay toàn bộ unit test bằng Testcontainers. Có thể giữ test logic nhanh với H2 hoặc mock khi phù hợp, và dùng một nhóm integration test nhỏ hơn để xác minh query, mapping và migration trên database production.

## 13. Quản lý lifecycle và tái sử dụng container

### 13.1. Container static với JUnit extension

Khi dùng `@Container` static field, container được chia sẻ giữa các method của cùng test class. Khi dùng field không static, container được khởi động/dừng cho từng test method, tạo isolation cao hơn nhưng tốn thời gian và tài nguyên hơn.

### 13.2. Container bean do Spring quản lý

Với `@Bean` trong `@TestConfiguration`, container sống theo ApplicationContext. Spring khởi động container trước các bean cần database và dừng nó sau khi các bean phụ thuộc đã được đóng.

Đây là lựa chọn phù hợp khi TestContext cache tái sử dụng cùng context giữa nhiều test class. Có thể dùng một test configuration chung cho các repository integration test cùng database.

### 13.3. Không bật reuse một cách tùy tiện

Testcontainers có chế độ reuse container giữa nhiều lần chạy local nếu cấu hình riêng. Chế độ này có thể tăng tốc, nhưng không phù hợp mặc định cho CI hoặc test cần database sạch tuyệt đối.

Nếu reuse:
- Dữ liệu cũ có thể còn từ lần chạy trước.
- Schema có thể đã được migration từ version khác.
- Test có thể pass cục bộ nhưng fail trên CI sạch.
- Phải có chiến lược reset database rõ ràng.

Mặc định nên dùng container disposable và trạng thái database xác định. Chỉ bật reuse khi hiểu rõ ảnh hưởng và có cơ chế reset đáng tin cậy.

## 14. Chạy test trong CI

CI runner cần có Docker environment tương thích với Testcontainers. Không nên giả định mọi hosted runner hoặc containerized build đều truy cập được Docker daemon.

Một pipeline thông thường:

1. Checkout source và cài JDK.
2. Khởi tạo Docker service/daemon theo môi trường CI.
3. Chạy unit test.
4. Chạy integration test có Testcontainers.
5. Thu log test và báo cáo lỗi nếu container không khởi động.
6. Dọn tài nguyên sau khi job kết thúc.

Lệnh chạy:

```bash
./mvnw test
```

Hoặc Gradle:

```bash
./gradlew test
```

Testcontainers tự tải image nếu chưa có trong cache. CI có thể cache image hoặc dùng registry mirror để giảm thời gian, nhưng phải giữ tag image rõ ràng và có thể tái lập.

Không tắt kiểm tra Docker để làm test “pass giả”. Nếu môi trường CI không hỗ trợ Docker, hãy cấu hình runner phù hợp hoặc tách integration test thành job có Docker.

## 15. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy Docker environment | Docker daemon chưa chạy hoặc CI không cấp socket | Kiểm tra `docker info`, Docker context và quyền truy cập |
| Container khởi động nhưng Spring không kết nối được | DataSource vẫn trỏ tới localhost/port cố định | Dùng `@ServiceConnection` hoặc dynamic properties từ container |
| Test vẫn chạy trên H2 | `@DataJpaTest` thay DataSource bằng embedded DB | Đặt `@AutoConfigureTestDatabase(replace = NONE)` |
| Không tìm thấy PostgreSQLContainer | Thiếu module PostgreSQL hoặc import sai major version | Kiểm tra dependency và package 1.x/2.x |
| No suitable driver | Thiếu PostgreSQL/MySQL JDBC driver | Thêm đúng driver vào runtime/test classpath |
| Connection refused | Container chưa ready hoặc bị dừng quá sớm | Dùng lifecycle được quản lý và kiểm tra startup logs |
| Test class đầu pass, class sau lỗi connection | Spring context cache giữ DataSource nhưng JUnit đã dừng container | Quản lý container bằng Spring bean hoặc đồng bộ lifecycle |
| Migration fail trên CI | Script dùng cú pháp khác database/version | Chạy migration trên đúng image/version production |
| Test pass dù constraint không đúng | Hibernate chưa flush SQL | Gọi `flush()` trước assertion về constraint |
| Dữ liệu rò giữa test | Test không rollback hoặc chạy ngoài transaction | Dùng rollback, cleanup hoặc schema/database riêng |
| Test parallel flaky | Nhiều test chia sẻ cùng bảng/database | Cô lập dữ liệu, schema hoặc tắt parallel cho nhóm đó |
| Image pull chậm/thất bại | Registry unavailable, rate limit hoặc tag sai | Kiểm tra pull image độc lập và cấu hình mirror/cache |
| Không tương thích constructor/import | Đổi Testcontainers 1.x sang 2.x | Đồng bộ artifact name và package class |
| Container hết dung lượng hoặc chạy chậm | Nhiều container/volume/log còn tồn tại | Dọn tài nguyên, giới hạn số test song song và xem Docker disk usage |

## 16. Checklist thiết lập Testcontainers cho Spring Data JPA

- [ ] Đã xác định database và version giống production.
- [ ] Docker daemon có thể truy cập từ test process.
- [ ] JDBC driver đúng database có trong classpath.
- [ ] Testcontainers JUnit/database module có scope test.
- [ ] Tất cả module Testcontainers dùng cùng major/minor version.
- [ ] Spring Boot 3.1+ dùng `spring-boot-testcontainers` nếu cần `@ServiceConnection`.
- [ ] Container cung cấp JDBC connection details động.
- [ ] `@DataJpaTest` dùng `replace = NONE` khi cần giữ DataSource Testcontainers.
- [ ] Container lifecycle phù hợp với Spring context cache.
- [ ] Migration chạy trên database container khi dự án dùng Flyway/Liquibase.
- [ ] Test fixture độc lập và không phụ thuộc thứ tự chạy.
- [ ] Đã flush khi cần xác nhận SQL/constraint.
- [ ] Test song song có chiến lược cô lập dữ liệu.
- [ ] CI runner có Docker environment và quyền pull image.
- [ ] Test không dựa vào tag `latest` hoặc cấu hình database không xác định.

## 17. Khi nào nên chọn từng cách?

| Cách tích hợp | Phù hợp khi | Lưu ý |
|---|---|---|
| Spring bean + `@ServiceConnection` | Spring Boot 3.1+ và nhiều test dùng chung context | Khuyến nghị cho lifecycle theo ApplicationContext |
| `@Container` + `@DynamicPropertySource` | Dự án cũ hơn hoặc cần tự gán property | Cẩn thận Spring context cache và container shutdown |
| JDBC URL `jdbc:tc:` | Test đơn giản, không cần tùy biến container | Cần Testcontainers JDBC driver và cấu hình URL |
| Container riêng mỗi test method | Cần isolation mạnh | Khởi động chậm, tốn tài nguyên |
| Container dùng chung cho test suite | Nhiều test cần cùng database | Phải kiểm soát dữ liệu và transaction |

## 18. Tài liệu tham khảo chính thức

- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): service connections, Spring-managed container beans, JUnit extension, dynamic properties và lifecycle.
- [Testcontainers for Java — PostgreSQL module](https://java.testcontainers.org/modules/databases/postgres/): PostgreSQL container, JDBC URL và dependency.
- [Testcontainers for Java — MySQL module](https://java.testcontainers.org/modules/databases/mysql/): MySQL container, cấu hình và JDBC URL.
- [Testcontainers for Java — JUnit 5 integration](https://java.testcontainers.org/test_framework_integration/junit_5/): static/instance container lifecycle và giới hạn khi chạy song song.
- [Testcontainers for Java — JDBC support](https://java.testcontainers.org/modules/databases/jdbc/): special JDBC URL và database container lifecycle.

## 19. Kết luận

Testcontainers giúp kiểm thử Spring Data JPA với PostgreSQL hoặc MySQL thật trong Docker. Nhờ vậy, test có thể phát hiện lỗi SQL, dialect, mapping, migration, constraint và transaction mà H2 hoặc mock không thể đại diện đầy đủ.

Với Spring Boot 3.1 trở lên, `@ServiceConnection` giảm cấu hình datasource thủ công. Quản lý container dưới dạng Spring bean đặc biệt hữu ích khi TestContext cache dùng chung ApplicationContext. Với test slice `@DataJpaTest`, cần ngăn Spring thay DataSource bằng database nhúng bằng `@AutoConfigureTestDatabase(replace = NONE)`.

Hãy chọn đúng database/version production, dùng JDBC driver tương ứng, quản lý lifecycle rõ ràng và cô lập dữ liệu giữa test. Testcontainers nên bổ sung cho unit test và test nhanh, tập trung vào những hành vi cần xác minh với database engine thật.
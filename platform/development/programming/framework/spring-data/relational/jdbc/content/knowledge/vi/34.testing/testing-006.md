# @AutoConfigureTestDatabase và kiểm soát thay thế DataSource

Khi kiểm thử ứng dụng dùng **Spring Data Relational JDBC (Spring Data JDBC)**, lựa chọn database ảnh hưởng trực tiếp đến độ tin cậy của test. Một repository test có thể chạy nhanh trên H2 in-memory, trong khi integration test cần dùng đúng PostgreSQL hoặc MySQL như môi trường triển khai. Spring Boot cung cấp annotation **@AutoConfigureTestDatabase** để quyết định DataSource hiện có có được thay bằng embedded test database hay không.

Annotation này thường xuất hiện cùng **@DataJdbcTest**, nhưng cũng có thể dùng với **@SpringBootTest** hoặc test slice khác. Điều cần hiểu rõ là chính sách thay thế DataSource: `ANY`, `AUTO_CONFIGURED`, `NON_TEST` và `NONE` có ý nghĩa khác nhau. Chọn sai có thể khiến test âm thầm kết nối nhầm database hoặc khiến Spring cố tạo embedded database khi test cần database thật.

## 1. DataSource trong kiểm thử Spring Data JDBC

Spring Data JDBC thực hiện truy vấn qua JDBC `DataSource`. Trong test, Spring Boot có thể:

- Tạo một embedded database như H2 nếu dependency có trên test classpath.
- Dùng DataSource được cấu hình qua `spring.datasource.*`.
- Dùng DataSource do ứng dụng tự khai báo bằng `@Bean`.
- Dùng database trong Testcontainers thông qua `@ServiceConnection`, `@DynamicPropertySource` hoặc Testcontainers JDBC URL.

`@AutoConfigureTestDatabase` kiểm soát việc **thay thế DataSource hiện có bằng embedded test database**. Annotation không tự viết lại query, không chuyển đổi dialect và không làm schema production tự tương thích với H2.

~~~mermaid
flowchart TD
    Test["Spring Boot test"]
    Existing["DataSource hiện có<br/>auto-configured hoặc @Bean"]
    Policy["@AutoConfigureTestDatabase<br/>replace + connection"]
    Decision{"DataSource có thuộc<br/>phạm vi được thay thế?"}
    Embedded["Embedded DataSource<br/>H2 / HSQL / Derby"]
    Keep["Giữ DataSource hiện tại<br/>PostgreSQL / MySQL / Testcontainers"]
    JDBC["Spring Data JDBC<br/>Repository / JdbcTemplate"]
    DB[("Test database")]
    Test --> Existing --> Policy --> Decision
    Decision -->|Có| Embedded --> JDBC
    Decision -->|Không| Keep --> JDBC
    JDBC --> DB
~~~

## 2. @DataJdbcTest và @AutoConfigureTestDatabase

`@DataJdbcTest` là test slice dành cho Spring Data JDBC. Nó tập trung vào entity, repository và các thành phần cấu hình JDBC cần thiết, thay vì khởi tạo toàn bộ ứng dụng.

Trong Spring Boot hiện hành:

- `@DataJdbcTest` cấu hình Spring Data JDBC repositories và `JdbcTemplate`.
- Mặc định, test dùng embedded in-memory database nếu có trên classpath.
- Test được đánh dấu transactional và transaction thường rollback khi kết thúc mỗi test.
- Component scan bị giới hạn; các subclass của `AbstractJdbcConfiguration` được nhận diện, còn component thông thường và `@ConfigurationProperties` không tự động được scan.
- Có thể thêm `@EnableConfigurationProperties` hoặc import cấu hình test khi cần.

Ví dụ tối thiểu:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJdbcTest
class OrderRepositoryTests {

    @Autowired
    private OrderRepository orders;

    @Test
    void savesAndFindsOrder() {
        Order saved = orders.save(new Order(101L, "DRAFT"));

        assertThat(saved.getId()).isNotNull();
        assertThat(orders.findById(saved.getId()))
            .isPresent()
            .get()
            .extracting(Order::getStatus)
            .isEqualTo("DRAFT");
    }
}
~~~

Vì `@DataJdbcTest` đã bao gồm cấu hình test database, không cần thêm `@AutoConfigureTestDatabase` nếu muốn dùng hành vi mặc định. Thêm annotation khi muốn điều khiển chính sách thay thế, ví dụ buộc thay cả DataSource do ứng dụng tự khai báo hoặc giữ nguyên database kiểm thử bên ngoài.

### Phân biệt các loại test

| Annotation | Phạm vi | Khi phù hợp |
|---|---|---|
| `@JdbcTest` | JDBC infrastructure và `JdbcTemplate`, không tập trung vào Spring Data JDBC repositories | Test SQL/JdbcTemplate trực tiếp |
| `@DataJdbcTest` | Spring Data JDBC entities, repositories và JDBC infrastructure | Test repository và mapping aggregate |
| `@SpringBootTest` | Toàn bộ ApplicationContext của ứng dụng | Integration test cần service, controller, security hoặc cấu hình thực |
| `@SpringBootTest` + `@AutoConfigureTestDatabase` | Toàn bộ ApplicationContext nhưng có thể thay DataSource | Kiểm tra luồng ứng dụng với database test |

`@AutoConfigureTestDatabase` cũng có thể dùng cùng `@SpringBootTest` nếu muốn tải full application context nhưng dùng database test. Nó chỉ điều khiển DataSource; nó không biến `@SpringBootTest` thành test slice.

## 3. Cấu trúc và thuộc tính của @AutoConfigureTestDatabase

Annotation có thể đặt trên test class hoặc test method. Hai thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `replace` | Quyết định loại DataSource hiện có nào được phép thay thế |
| `connection` | Chọn loại embedded database được tạo khi cần thay thế |

Trong Spring Boot 3.5 và 4.1.2, giá trị mặc định của `replace` là `Replace.NON_TEST`. `connection` mặc định là `EmbeddedDatabaseConnection.NONE`, nghĩa là Spring Boot thử phát hiện embedded database phù hợp dựa trên classpath.

Ví dụ import và khai báo tường minh:

~~~java
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace;

@DataJdbcTest
@AutoConfigureTestDatabase(
    replace = Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2
)
class OrderRepositoryH2Tests {
}
~~~

`connection = H2` yêu cầu dùng H2 khi DataSource được thay thế. Nếu có nhiều embedded database trên classpath, chỉ định rõ loại database giúp test không phụ thuộc vào việc phát hiện theo classpath.

Để embedded database được tạo, driver/database tương ứng phải có trên test runtime classpath. Ví dụ với Gradle:

~~~groovy
dependencies {
    testRuntimeOnly("com.h2database:h2")
}
~~~

Nếu không có embedded database phù hợp, Spring Boot không thể tạo DataSource embedded theo yêu cầu. Hãy thêm dependency hoặc chọn chính sách giữ DataSource có sẵn.

## 4. Bốn chế độ Replace

`AutoConfigureTestDatabase.Replace` quyết định phạm vi DataSource mà annotation có thể thay:

| Giá trị | Hành vi | Trường hợp sử dụng |
|---|---|---|
| `ANY` | Thay DataSource dù được auto-configure hay khai báo thủ công | Muốn buộc test dùng embedded database, kể cả khi ứng dụng có `@Bean DataSource` |
| `AUTO_CONFIGURED` | Chỉ thay DataSource do Spring Boot auto-configure | Muốn thay DataSource mặc định của Boot nhưng giữ DataSource do test/ứng dụng tự khai báo |
| `NON_TEST` | Thay DataSource trừ trường hợp nó là DataSource auto-configured đang kết nối tới một test database được nhận diện | Lựa chọn mặc định hiện hành, hữu ích khi dùng Testcontainers hoặc dynamic test properties |
| `NONE` | Không thay DataSource mặc định của ứng dụng | Muốn giữ nguyên DataSource do ứng dụng/test cấu hình |

### ANY

`ANY` có phạm vi mạnh nhất:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(replace = Replace.ANY)
class OrderRepositoryTests {
}
~~~

Ngay cả khi ứng dụng có một bean `DataSource` được tạo thủ công, Spring Boot vẫn có thể thay DataSource đó bằng embedded database. Cách này hữu ích khi test cần cô lập hoàn toàn khỏi cấu hình database bên ngoài.

Tuy nhiên, nếu test có ý định kiểm tra cấu hình DataSource thủ công, connection pool, driver hoặc database thật, `ANY` có thể làm test không còn kiểm tra đúng thành phần đó.

### AUTO_CONFIGURED

`AUTO_CONFIGURED` chỉ thay DataSource do Spring Boot tạo tự động:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(replace = Replace.AUTO_CONFIGURED)
class OrderRepositoryTests {
}
~~~

Nếu test cung cấp một bean DataSource riêng, bean đó được giữ lại. Chế độ này hữu ích khi có cấu hình database riêng cho test nhưng vẫn muốn thay DataSource mặc định mà Boot tạo từ `spring.datasource.*`.

Đừng nhầm `AUTO_CONFIGURED` với `NON_TEST`: `AUTO_CONFIGURED` không phân loại xem database có phải test database hay không; nó chỉ xét nguồn gốc của DataSource.

### NON_TEST

`NON_TEST` là mặc định trong các API Spring Boot hiện hành. Nó thay DataSource trừ khi DataSource được auto-configure và Spring Boot nhận diện nó đang kết nối tới một test database.

Các loại connection được xem là test database bao gồm:

- Bean definition có `ContainerImageMetadata`, chẳng hạn database Testcontainers được đánh dấu `@ServiceConnection` hoặc database được tạo từ Docker Compose.
- `spring.datasource.url` được cung cấp qua `@DynamicPropertySource`.
- URL dùng cú pháp Testcontainers JDBC, ví dụ `jdbc:tc:postgresql:...`.

Nhờ đó, một DataSource được Boot tạo từ Testcontainers có thể được giữ lại mà không cần ghi `replace = Replace.NONE` cho mọi test.

Tuy nhiên, `NON_TEST` không đồng nghĩa “giữ mọi DataSource có chữ test trong URL”. Một DataSource bean tự tạo có thể không được Boot nhận diện như một auto-configured test connection. Nếu cần giữ chắc chắn bean thủ công, dùng `NONE`.

### NONE

`NONE` tắt việc thay thế:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(replace = Replace.NONE)
class OrderRepositoryPostgresTests {
}
~~~

Spring dùng DataSource do ứng dụng hoặc test cấu hình. Nếu không có DataSource hợp lệ, context sẽ không khởi động chỉ vì đã chọn `NONE`; chế độ này không tự tạo database.

Đây là lựa chọn rõ ràng khi:

- Test dùng một `DataSource` được khai báo thủ công.
- Muốn chạy trên database được cấp sẵn trong CI.
- Muốn kiểm tra đúng driver, connection pool hoặc cấu hình JDBC.
- Đang dùng một database test riêng và không muốn annotation thay nó.

## 5. Chọn Replace theo mục tiêu test

| Mục tiêu | Lựa chọn thường phù hợp |
|---|---|
| Test repository nhanh trên H2, kể cả khi ứng dụng có DataSource thủ công | `ANY` |
| Thay DataSource mặc định do Boot tạo, nhưng giữ bean DataSource riêng của test | `AUTO_CONFIGURED` |
| Dùng Testcontainers qua `@ServiceConnection` hoặc `@DynamicPropertySource` với auto-config | `NON_TEST` (mặc định hiện hành) |
| Giữ nguyên DataSource do test tự khai báo | `NONE` |
| Buộc thay cả DataSource của Testcontainers bằng H2 | `ANY` |
| Chạy full application context trên database đã cấu hình | `NONE` |

Hãy chọn dựa trên DataSource mà test thực sự cần sử dụng. Đừng chọn `ANY` chỉ vì muốn test “an toàn” nếu mục tiêu test là xác minh cấu hình kết nối PostgreSQL do ứng dụng khai báo.

## 6. Dùng embedded H2 cho repository test

H2 phù hợp cho test nhanh các thao tác CRUD và mapping cơ bản. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest;
import org.springframework.boot.jdbc.EmbeddedDatabaseConnection;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace;

import static org.assertj.core.api.Assertions.assertThat;

@DataJdbcTest
@AutoConfigureTestDatabase(
    replace = Replace.ANY,
    connection = EmbeddedDatabaseConnection.H2
)
class CustomerRepositoryTests {

    @Autowired
    private CustomerRepository customers;

    @Test
    void persistsCustomer() {
        Customer saved = customers.save(
            new Customer("Lan", "lan@example.test")
        );

        Customer loaded = customers.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getName()).isEqualTo("Lan");
        assertThat(loaded.getEmail()).isEqualTo("lan@example.test");
    }
}
~~~

Test trên yêu cầu H2 có trên test runtime classpath. `Replace.ANY` đảm bảo DataSource được thay kể cả khi có cấu hình thủ công.

### Hạn chế của embedded database

H2 không đảm bảo mô phỏng chính xác PostgreSQL, MySQL, MariaDB hoặc SQL Server. Khác biệt có thể xuất hiện ở:

- Kiểu dữ liệu riêng như `JSONB`, `UUID`, `INET`, `ENUM`.
- Cú pháp DDL, identity, sequence và generated key.
- CTE, window function, JSON operator và database-specific function.
- Collation, so sánh chuỗi, timezone và độ chính xác timestamp.
- Khóa, isolation level, deadlock và optimistic/pessimistic locking.
- Constraint, index, transaction và hành vi của JDBC driver.

H2 có compatibility mode cho một số database nhưng không biến nó thành database thật đó. Dùng H2 cho test logic nhanh; dùng Testcontainers hoặc database test tương ứng để kiểm tra SQL và hành vi phụ thuộc engine.

## 7. Giữ DataSource thủ công

Giả sử ứng dụng hoặc test có cấu hình:

~~~java
import javax.sql.DataSource;

import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
class TestDatabaseConfiguration {

    @Bean
    @Primary
    DataSource testDataSource() {
        return DataSourceBuilder.create()
            .url("jdbc:postgresql://localhost:5432/orders_test")
            .username("test_user")
            .password("test_password")
            .build();
    }
}
~~~

Có thể import cấu hình đó vào test slice và giữ DataSource:

~~~java
import org.springframework.context.annotation.Import;

@DataJdbcTest
@Import(TestDatabaseConfiguration.class)
@AutoConfigureTestDatabase(replace = Replace.NONE)
class OrderRepositoryTests {
}
~~~

Trong ví dụ này, `NONE` làm rõ ý định dùng chính bean DataSource do test cung cấp. Nếu dùng `AUTO_CONFIGURED`, bean thủ công cũng được giữ vì nó không phải DataSource do Boot auto-configure; tuy nhiên `NONE` diễn đạt rõ hơn rằng test không muốn replacement.

Nếu cấu hình nhiều bean DataSource, hãy đánh dấu bean được repository dùng làm `@Primary` khi phù hợp. `@AutoConfigureTestDatabase` chỉ xem xét DataSource `@Primary` trong trường hợp application context có nhiều DataSource.

## 8. Giữ database Testcontainers bằng @ServiceConnection

Testcontainers cho phép chạy database thật trong container, giúp test dùng đúng database engine và driver mà ứng dụng triển khai.

Với Spring Boot 4.1, ví dụ dùng PostgreSQL:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@DataJdbcTest
@Testcontainers
@AutoConfigureTestDatabase(replace = Replace.NON_TEST)
class OrderRepositoryPostgresTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:17-alpine");

    @Autowired
    private OrderRepository orders;

    @Test
    void savesOrderUsingPostgres() {
        Order saved = orders.save(new Order(101L, "DRAFT"));

        assertThat(orders.findById(saved.getId())).isPresent();
    }
}
~~~

`@ServiceConnection` cho phép Spring Boot tạo connection details cho PostgreSQL container. Với `Replace.NON_TEST`, DataSource auto-configured từ service connection được nhận diện là test database nên không bị thay bằng H2.

Nếu đặt `Replace.ANY`, DataSource có thể bị thay bằng embedded database và test sẽ không còn chạy trên PostgreSQL container như dự định. Nếu muốn bảo đảm không thay DataSource trong test này, `Replace.NONE` cũng là lựa chọn hợp lệ.

Các dependency test cần có theo phiên bản Spring Boot:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-data-jdbc-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("org.testcontainers:junit-jupiter")
    testRuntimeOnly("org.postgresql:postgresql")
}
~~~

Các version nên được quản lý bằng Spring Boot dependency management/BOM tương ứng. Với Spring Boot 3.x, tên module và package test annotation khác tùy phiên bản; không sao chép import Boot 4 vào dự án Boot 3 mà không kiểm tra dependency.

## 9. Giữ Testcontainers qua @DynamicPropertySource

Một cách khác là truyền JDBC URL và credentials vào Spring Environment bằng `@DynamicPropertySource`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@DataJdbcTest
@Testcontainers
@AutoConfigureTestDatabase(replace = Replace.NON_TEST)
class OrderRepositoryDynamicPostgresTests {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:17-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    private OrderRepository orders;

    @Test
    void repositoryUsesContainerDatabase() {
        Order saved = orders.save(new Order(101L, "DRAFT"));
        assertThat(orders.findById(saved.getId())).isPresent();
    }
}
~~~

Spring Boot hiện hành nhận diện `spring.datasource.url` được cấp qua `@DynamicPropertySource` như một test connection khi áp dụng `Replace.NON_TEST`. Vì vậy DataSource auto-configured từ các property này được giữ lại.

Nếu test dùng một bean DataSource thủ công thay vì DataSource auto-configured từ property, hãy dùng `Replace.NONE` để thể hiện rõ ý định giữ bean đó.

## 10. Testcontainers JDBC URL

Testcontainers cũng cung cấp JDBC driver wrapper có thể khởi động container từ URL:

~~~properties
spring.datasource.url=jdbc:tc:postgresql:17-alpine:///orders_test
spring.datasource.username=test
spring.datasource.password=test
~~~

URL có tiền tố `jdbc:tc:` cho phép Testcontainers JDBC driver tạo database container khi kết nối. Spring Boot hiện hành nhận dạng Testcontainers JDBC URL là một test connection trong chính sách `NON_TEST`.

Cần có Testcontainers JDBC module và JDBC driver tương ứng trên test classpath. Cú pháp URL, image tag và các tham số phụ thuộc database/container mà dự án dùng.

Nếu test có yêu cầu cấu hình lifecycle container rõ ràng, log, init script hoặc chia sẻ container giữa nhiều test class, `@Container`/`@ServiceConnection` thường dễ kiểm soát hơn JDBC URL.

## 11. Nhiều DataSource và @Primary

Một application context có thể có nhiều DataSource:

~~~java
@Bean
@Primary
DataSource ordersDataSource() {
    // DataSource chính cho Spring Data JDBC repositories.
}

@Bean
DataSource auditDataSource() {
    // DataSource phụ cho audit/log database.
}
~~~

Khi có nhiều bean DataSource, `@AutoConfigureTestDatabase` chỉ xét bean được đánh dấu `@Primary`. Vì vậy:

- Nếu primary DataSource bị thay, secondary DataSource vẫn có thể giữ nguyên.
- Nếu repository được cấu hình dùng secondary DataSource, thay primary không nhất thiết cô lập repository đó.
- Nếu không có primary rõ ràng, việc chọn DataSource có thể không đáp ứng ý định test và có thể gây lỗi wiring.

Với ứng dụng nhiều database, nên khai báo rõ `@Primary`, `@Qualifier`, repository package và transaction manager. Nếu cần thay nhiều DataSource, cấu hình từng bean bằng test configuration riêng thay vì giả định annotation sẽ thay tất cả.

Đặc biệt, không để một DataSource phụ trỏ tới database production trong test chỉ vì DataSource chính đã được thay bằng H2. Cần kiểm tra mọi connection mà test context có thể sử dụng.

## 12. Dùng @SpringBootTest cùng @AutoConfigureTestDatabase

`@DataJdbcTest` không tải toàn bộ service, controller, security hoặc component thông thường. Nếu cần kiểm tra luồng nghiệp vụ hoàn chỉnh nhưng vẫn muốn thay database:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase.Replace;

@SpringBootTest
@AutoConfigureTestDatabase(replace = Replace.ANY)
class OrderApplicationIntegrationTests {
    // Full application context với embedded test DataSource.
}
~~~

Chọn `ANY` nếu muốn buộc thay cả DataSource do ứng dụng tự khai báo. Nếu muốn dùng database do profile/test properties cấu hình, dùng `NONE`. Với Testcontainers được Boot nhận diện, `NON_TEST` giúp giữ container connection trong khi vẫn thay các DataSource không được xem là test database.

Khác với `@DataJdbcTest`, `@SpringBootTest` không tự động làm mọi test transactional. Nếu muốn rollback transaction của test method, cần đánh dấu `@Transactional` phù hợp. Với test chạy server thật bằng `RANDOM_PORT` hoặc `DEFINED_PORT`, request client và server chạy ở thread/transaction riêng; transaction của test thread không tự rollback các thao tác được thực hiện trong request phía server.

## 13. Cấu hình qua application properties

`@AutoConfigureTestDatabase` được ánh xạ với prefix:

~~~properties
spring.test.database
~~~

Có thể cấu hình chính sách thay thế bằng property:

~~~properties
spring.test.database.replace=none
~~~

Hoặc khai báo trực tiếp trên test:

~~~java
@AutoConfigureTestDatabase(replace = Replace.NONE)
~~~

Dùng annotation thường dễ thấy chính sách ngay tại test class. Property hữu ích khi nhiều test cùng chia sẻ một cấu hình hoặc khi cần bật/tắt theo profile test.

Không cấu hình property global `spring.test.database.replace=none` một cách vô thức cho toàn bộ test suite nếu một số test đang dựa vào embedded database mặc định. Chính sách toàn cục có thể khiến test cố kết nối tới DataSource ngoài ý muốn.

## 14. Schema và migration trong test database

Thay DataSource không tự đảm bảo schema đã sẵn sàng. Test database vẫn cần các bảng, index, constraint và dữ liệu ban đầu phù hợp với mapping.

Các cách chuẩn bị schema phổ biến:

- Flyway hoặc Liquibase chạy migration trên test database.
- `schema.sql` và `data.sql` nếu dự án dùng SQL initialization.
- `@Sql` để nạp schema/data riêng cho test.
- Test fixture tạo dữ liệu qua repository hoặc `JdbcTemplate`.

Ví dụ:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(replace = Replace.ANY)
@Sql("/sql/orders-test-data.sql")
class OrderRepositoryTests {
}
~~~

Hãy xác định thứ tự khởi tạo schema phù hợp với cấu hình Spring Boot và công cụ migration. Không để một cơ chế tự tạo schema cạnh tranh với Flyway/Liquibase trên cùng database.

Khi chạy H2, migration viết cho PostgreSQL có thể không chạy được do khác biệt DDL hoặc function. Có thể duy trì migration tương thích nhiều database nếu đó là yêu cầu thực, nhưng test với database thật vẫn cần thiết để xác minh migration production.

## 15. Transaction và rollback

`@DataJdbcTest` mặc định chạy test trong transaction và rollback khi test method kết thúc. Điều này giúp test độc lập hơn, nhưng có vài điểm cần lưu ý:

- Test không thấy dữ liệu từ một transaction chưa commit ở connection khác.
- Code mở transaction độc lập hoặc dùng propagation khác có thể không bị rollback cùng transaction test.
- Side effect ngoài database như message, file hoặc HTTP call không tự rollback.
- Với Testcontainers, container database vẫn tồn tại theo lifecycle của container; rollback chỉ tác động transaction, không xóa container.
- Nếu test cần xác minh dữ liệu đã commit hoặc hành vi nhiều transaction, có thể tắt transaction test bằng `Propagation.NOT_SUPPORTED` hoặc thiết kế transaction riêng có chủ đích.

Ví dụ tắt transaction test slice:

~~~java
@DataJdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class OrderCommitIntegrationTests {
}
~~~

Nếu dùng `@SpringBootTest`, thêm `@Transactional` khi cần rollback theo test method. Đừng suy luận rằng chọn `Replace.NONE` hay dùng Testcontainers sẽ tự thay đổi chính sách transaction.

## 16. Chẩn đoán khi DataSource bị thay ngoài ý muốn

Khi test kết nối sai database, kiểm tra theo thứ tự:

1. Test đang dùng `@DataJdbcTest`, `@JdbcTest` hay `@SpringBootTest`?
2. Annotation test slice có tự bao gồm `@AutoConfigureTestDatabase` không?
3. `replace` đang dùng giá trị nào? Có đang để mặc định `NON_TEST` không?
4. DataSource được auto-configure từ property hay khai báo thủ công bằng `@Bean`?
5. Test database có được Boot nhận diện qua `@ServiceConnection`, `@DynamicPropertySource` hoặc `jdbc:tc:` không?
6. Có nhiều DataSource không? Bean nào là `@Primary`?
7. Có property `spring.test.database.replace` trong profile hoặc test config đang ghi đè annotation không?
8. Driver và embedded database có nằm đúng test runtime classpath không?

Có thể kiểm tra DataSource đang được inject:

~~~java
@DataJdbcTest
class DataSourceSelectionTests {

    @Autowired
    DataSource dataSource;

    @Test
    void reportsDatabaseProduct() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData metadata = connection.getMetaData();
            System.out.println(metadata.getURL());
            System.out.println(metadata.getDatabaseProductName());
        }
    }
}
~~~

Chỉ log URL/metadata trong test cục bộ hoặc CI có kiểm soát; không log password hoặc connection string chứa secret.

### Một số lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Test dùng H2 dù đã cấu hình PostgreSQL | `@DataJdbcTest` thay DataSource theo chính sách test database | Dùng `Replace.NONE` hoặc Testcontainers được nhận diện với `NON_TEST` |
| DataSource `@Bean` bị thay | `ANY` hoặc `NON_TEST` đang cho phép thay bean thủ công | Dùng `NONE` nếu cần giữ bean, hoặc xem xét `AUTO_CONFIGURED` |
| DataSource Boot tạo không bị thay | Đang dùng `NONE` hoặc `NON_TEST` nhận diện connection là test database | Kiểm tra chính sách và ý định test |
| Testcontainers khởi động nhưng test lại kết nối H2 | `Replace.ANY` hoặc cấu hình replacement khác ghi đè service connection | Dùng `NON_TEST` hoặc `NONE` |
| `Replace.NON_TEST` không giữ custom DataSource | Bean thủ công không được nhận diện là auto-configured test connection | Dùng `NONE` |
| Secondary DataSource vẫn kết nối database cũ | Annotation chỉ xét `@Primary` DataSource | Cấu hình riêng tất cả DataSource test có thể truy cập |
| Không tạo được embedded database | Thiếu H2/HSQL/Derby trên test runtime classpath | Thêm dependency hoặc giữ DataSource hiện có |
| Test chạy trên H2 nhưng lỗi ở production | Khác biệt SQL, type, constraint hoặc driver | Thêm integration test trên database thật |
| Migration thất bại khi dùng H2 | DDL/function đặc thù database production | Dùng Testcontainers hoặc migration tương thích có chủ đích |
| Dữ liệu vẫn còn sau test | Transaction không bao trùm thao tác ghi hoặc code đã commit độc lập | Kiểm tra transaction boundary và cleanup fixture |

## 17. Khác biệt package giữa Spring Boot 3 và 4

Spring Boot 4 tách nhiều test module và package annotation theo chức năng. Vì vậy, import có thể khác giữa Boot 3 và Boot 4.

| Thành phần | Spring Boot 3.5 | Spring Boot 4.1 |
|---|---|---|
| `@DataJdbcTest` | `org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest` | `org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest` |
| `@AutoConfigureTestDatabase` | `org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase` | `org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase` |
| `@JdbcTest` | `org.springframework.boot.test.autoconfigure.jdbc.JdbcTest` | `org.springframework.boot.jdbc.test.autoconfigure.JdbcTest` |
| `EmbeddedDatabaseConnection` | `org.springframework.boot.jdbc.EmbeddedDatabaseConnection` | `org.springframework.boot.jdbc.EmbeddedDatabaseConnection` |

Trong các phiên bản Boot 3 cũ, enum `Replace` có thể chưa có `NON_TEST`; tập giá trị và default đã thay đổi theo phiên bản. Hãy kiểm tra API docs đúng với Spring Boot BOM mà dự án đang dùng trước khi sao chép ví dụ.

## 18. Checklist lựa chọn DataSource cho test

Trước khi hoàn thiện một test Spring Data JDBC, hãy xác định:

- Test chỉ kiểm tra repository hay cần toàn bộ application context?
- Test cần embedded database hay database engine thật?
- DataSource do Boot auto-configure, test tự khai báo hay đến từ Testcontainers?
- `Replace` có đúng với nguồn gốc và mục tiêu DataSource không?
- Có nhiều DataSource và bean `@Primary` chưa?
- Driver và database dependency có nằm trên test runtime classpath không?
- Schema được chuẩn bị bằng Flyway, Liquibase, SQL initialization hay fixture?
- Test có transaction rollback hay cần xác minh commit?
- Có khác biệt SQL/DDL/driver mà H2 không mô phỏng được không?

Một bộ test tốt thường kết hợp:

1. Repository tests nhanh trên embedded database cho CRUD và mapping cơ bản.
2. Integration tests trên Testcontainers để xác minh database engine, dialect, migration và JDBC driver thực tế.
3. Full application tests khi cần kiểm tra service, transaction boundary và cấu hình tích hợp.

## 19. Bài thực hành

1. Tạo `OrderRepository` và test bằng `@DataJdbcTest`; thêm H2 vào test runtime classpath.
2. Thử `Replace.ANY` và xác minh DataSource bị thay bằng embedded database.
3. Tạo một DataSource bean thủ công trong test configuration; so sánh kết quả của `ANY`, `AUTO_CONFIGURED` và `NONE`.
4. Dùng `@SpringBootTest` kết hợp `@AutoConfigureTestDatabase` để kiểm tra toàn bộ service layer.
5. Tạo PostgreSQL Testcontainer với `@ServiceConnection`; chạy repository test cùng `Replace.NON_TEST`.
6. Thay `@ServiceConnection` bằng `@DynamicPropertySource`; xác minh DataSource auto-configured vẫn dùng container.
7. Tạo hai DataSource, đánh dấu một bean `@Primary`; quan sát DataSource nào bị annotation thay.
8. Chạy cùng một repository test trên H2 và PostgreSQL, so sánh DDL, generated ID, timestamp và query.
9. Thêm Flyway migration vào test database và xác minh schema được khởi tạo trước test.
10. Tắt transaction test bằng `Propagation.NOT_SUPPORTED`; tự chuẩn bị cleanup và quan sát dữ liệu đã commit.
11. Đặt `spring.test.database.replace=none` trong test profile và so sánh với thuộc tính annotation.
12. Kiểm tra import/package của annotation theo phiên bản Spring Boot mà dự án đang dùng.

## 20. Ghi nhớ

`@AutoConfigureTestDatabase` kiểm soát việc Spring Boot có thay DataSource hiện tại bằng embedded test database hay không. `ANY` thay mọi DataSource được xét, `AUTO_CONFIGURED` chỉ thay DataSource do Boot tạo, `NON_TEST` giữ các test connection được nhận diện trong khi thay những DataSource còn lại, và `NONE` giữ nguyên DataSource của ứng dụng. Trong Spring Boot 3.5 và 4.1, `NON_TEST` là default; nếu có nhiều DataSource, annotation chỉ xét bean `@Primary`.

Với Spring Data JDBC, `@DataJdbcTest` mặc định dùng embedded database và rollback transaction khi test kết thúc. Dùng H2 cho kiểm thử repository nhanh; dùng `Replace.NONE` để giữ DataSource tự cấu hình; dùng `@ServiceConnection` hoặc `@DynamicPropertySource` cùng `NON_TEST` khi chạy Testcontainers. Cuối cùng, xác minh database thực tế mà test kết nối, schema/migration và transaction boundary; chỉ nhìn annotation không đủ để biết test đang chạy trên database nào.

## Tài liệu tham khảo

- [Spring Boot 4.1 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot 4.1 — AutoConfigureTestDatabase API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/jdbc/test/autoconfigure/AutoConfigureTestDatabase.html)
- [Spring Boot 4.1 — AutoConfigureTestDatabase.Replace API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/jdbc/test/autoconfigure/AutoConfigureTestDatabase.Replace.html)
- [Spring Boot 4.1 — DataJdbcTest API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/data/jdbc/test/autoconfigure/DataJdbcTest.html)
- [Spring Boot 4.1 — Testcontainers and Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — AutoConfigureTestDatabase API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/jdbc/AutoConfigureTestDatabase.html)

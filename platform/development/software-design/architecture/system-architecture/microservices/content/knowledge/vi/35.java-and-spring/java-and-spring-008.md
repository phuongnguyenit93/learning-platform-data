# Kiểm thử tích hợp bằng JUnit và Testcontainers

Trong một ứng dụng Java/Spring, unit test có thể chứng minh một hàm tính giá hoạt động đúng khi nhận dữ liệu đầu vào, nhưng chưa chắc ứng dụng thật có thể ghi dữ liệu vào PostgreSQL, chạy migration, serialize message, gọi HTTP dependency hoặc khởi động với cấu hình production-like. Những lỗi thường chỉ xuất hiện khi các thành phần kết nối với nhau: SQL khác biệt giữa H2 và PostgreSQL, transaction không commit như dự kiến, JSON field bị đổi tên, broker từ chối quyền publish, migration không chạy trên schema mới, hoặc Spring wiring nhầm implementation.

**Integration test** kiểm tra sự tương tác giữa nhiều thành phần qua ranh giới thực tế của chúng. **JUnit 5** cung cấp cách tổ chức và chạy test, lifecycle, assertions, parameterized tests và extension model. **Testcontainers** khởi tạo các dependency thực trong container tạm thời để test có thể sử dụng database, message broker, cache hoặc dịch vụ hỗ trợ gần với môi trường chạy thật. Kết hợp với Spring Boot, nhóm có thể kiểm tra repository, transaction, HTTP endpoint, messaging adapter, migration và cấu hình ứng dụng mà không phải dùng một hạ tầng dùng chung dễ gây nhiễu giữa các lần chạy.

Bài học này dùng ví dụ hệ thống thương mại điện tử với Order Service, PostgreSQL và message broker. Các đoạn code là mẫu minh họa cần điều chỉnh theo phiên bản Java, Spring Boot, JUnit, Testcontainers và thư viện đang dùng trong dự án. Mục tiêu là hiểu cách thiết kế test có tính lặp lại, cô lập dữ liệu và kiểm tra đúng contract của hệ thống.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt unit test, integration test, component test, contract test và end-to-end test.
- Giải thích vai trò của JUnit Jupiter và Testcontainers trong test suite Java.
- Khởi tạo PostgreSQL container cho JUnit 5 và kết nối Spring Boot bằng DynamicPropertySource.
- Dùng SpringBootTest để kiểm tra wiring, repository, transaction và service behavior với dependency thật.
- Kiểm tra Flyway/Liquibase migration trên database rỗng và database có dữ liệu phiên bản cũ.
- Kiểm thử HTTP API qua MockMvc hoặc WebTestClient khi cần kiểm tra Spring MVC/WebFlux stack.
- Kiểm tra message producer/consumer với broker container, xác nhận serialization, delivery và idempotency.
- Quản lý lifecycle container, dữ liệu test, parallel execution, timeout và cleanup.
- Tổ chức Testcontainers trong CI với Docker, image pinning, cache và diagnostics.
- Nhận biết các lỗi thường gặp như test phụ thuộc thứ tự, port cố định, dùng database H2 thay production, chờ async bằng sleep và test quá rộng.

## 2. Các lớp kiểm thử trong một ứng dụng Spring

Không phải mọi test đều cần container. Chọn đúng lớp kiểm thử giúp suite nhanh và vẫn bắt được lỗi có giá trị.

| Loại test | Phạm vi | Dependency | Ví dụ |
|---|---|---|---|
| Unit test | Một class/hàm và logic nội bộ | Fake/mock hoặc không có dependency | Tính tổng đơn hàng |
| Slice test | Một lát cắt Spring | Một phần ApplicationContext | @WebMvcTest, @DataJpaTest |
| Integration test | Tương tác giữa các thành phần | Database/broker thật hoặc dependency tương thích | Repository + PostgreSQL |
| Component test | Một service chạy như một thành phần có ranh giới | Dependency thật hoặc giả lập có chủ đích | Order API + DB + broker |
| Contract test | Tương thích giữa producer và consumer | Contract artifact/provider verification | Event schema, API response |
| End-to-end test | Hành trình qua nhiều service | Hệ thống tích hợp lớn | Checkout đến Order và Payment |

Một unit test của OrderCalculator nên chạy nhanh và không cần Docker. Một integration test cho OrderRepository nên dùng database cùng họ với production để phát hiện khác biệt SQL, index, constraint và transaction. Một end-to-end test không nên được dùng thay cho hàng trăm test nhỏ vì khó chẩn đoán và thường chậm.

### 2.1. Kim tự tháp kiểm thử

~~~text
             E2E / journey
           ít, chọn trọng điểm
        -------------------------
          Contract / component
        -------------------------
        Integration với dependency
        -------------------------
             Unit tests
          nhiều, chạy nhanh
~~~

Hình này là định hướng về phạm vi và số lượng tương đối, không phải tỷ lệ cứng. Hệ thống có nhiều workflow bất đồng bộ có thể cần nhiều integration/contract tests hơn một ứng dụng CRUD đơn giản.

### 2.2. Khi nào cần Testcontainers?

Dùng Testcontainers khi test cần hành vi của dependency thật hoặc tương thích cao với production:

- PostgreSQL/MySQL để kiểm tra SQL, migration, locking và transaction.
- Kafka/RabbitMQ để kiểm tra broker protocol, topic/queue và serialization.
- Redis để kiểm tra cache semantics, TTL hoặc script.
- LocalStack hoặc container tương thích để kiểm tra một số tích hợp cloud.
- Elasticsearch/OpenSearch để kiểm tra query/index mapping.
- WireMock container hoặc service giả lập có kiểm soát khi cần mô phỏng HTTP provider.

Không cần container cho phép tính thuần, mapping đơn giản hoặc validation có thể kiểm tra độc lập. Testcontainers không biến một test thành đúng tự động; nó chỉ cung cấp dependency gần thực tế hơn.

## 3. JUnit 5: nền tảng tổ chức test

JUnit 5 thường được gọi là JUnit Jupiter ở phần API và engine. Các annotation cơ bản:

| Annotation | Ý nghĩa |
|---|---|
| @Test | Một test case |
| @BeforeEach | Chạy trước mỗi test |
| @AfterEach | Chạy sau mỗi test |
| @BeforeAll | Chạy một lần trước toàn bộ test class |
| @AfterAll | Chạy một lần sau toàn bộ test class |
| @Nested | Nhóm test theo ngữ cảnh |
| @ParameterizedTest | Chạy một test với nhiều bộ dữ liệu |
| @MethodSource | Lấy dữ liệu từ method |
| @ValueSource | Dữ liệu đơn giản |
| @DisplayName | Tên test dễ đọc |
| @Tag | Phân loại test |
| @Disabled | Tạm bỏ qua test có lý do rõ |
| @ExtendWith | Đăng ký extension |

Ví dụ:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderTotalTest {

    private OrderTotalCalculator calculator;

    @BeforeEach
    void setUp() {
        calculator = new OrderTotalCalculator();
    }

    @Test
    @DisplayName("Tính tổng tiền gồm giá sản phẩm và phí vận chuyển")
    void calculatesTotal() {
        long total = calculator.calculate(200_000, 20_000);

        assertEquals(220_000, total);
    }
}
~~~

Đây là unit test. Không cần khởi tạo Spring context hay Docker vì test chỉ kiểm tra phép tính.

### 3.1. Assertion nên kiểm tra hành vi có ý nghĩa

JUnit có các assertion phổ biến:

~~~java
assertEquals(expected, actual);
assertTrue(condition);
assertFalse(condition);
assertNull(value);
assertNotNull(value);
assertNotEquals(unexpected, actual);
assertThrows(IllegalArgumentException.class, () -> service.execute());
assertAll(
    () -> assertEquals("O-100", order.id()),
    () -> assertEquals("CREATED", order.status())
);
~~~

Với exception, kiểm tra cả loại và thông tin quan trọng nếu đó là một phần contract:

~~~java
IllegalArgumentException error = assertThrows(
    IllegalArgumentException.class,
    () -> calculator.calculate(-1, 10)
);
assertEquals("amount must be non-negative", error.getMessage());
~~~

Không nên assert message nội bộ dễ thay đổi nếu message không phải API contract. Hãy ưu tiên kết quả nghiệp vụ, status, dữ liệu được ghi và side effect cần bảo vệ.

### 3.2. Parameterized test

Một rule có nhiều input nên dùng parameterized test:

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DiscountCalculatorTest {

    @ParameterizedTest
    @CsvSource({
        "100000, 10, 90000",
        "200000, 15, 170000",
        "50000, 0, 50000"
    })
    void calculatesDiscount(
            long price,
            int percent,
            long expected) {
        assertEquals(
            expected,
            DiscountCalculator.apply(price, percent)
        );
    }
}
~~~

Dữ liệu test nên thể hiện boundary, trường hợp bình thường và trường hợp lỗi. Với tiền tệ, dùng kiểu dữ liệu/rounding phù hợp domain; ví dụ long ở đây chỉ minh họa một đơn vị tiền nguyên.

## 4. Testcontainers hoạt động như thế nào?

Testcontainers sử dụng Docker-compatible runtime để khởi chạy dependency cho test. Một test thường thực hiện:

~~~text
JUnit bắt đầu test suite
        |
        v
Testcontainers khởi chạy container
        |
        v
Chờ dependency sẵn sàng
        |
        v
Test lấy host/port/credentials động
        |
        v
Ứng dụng kết nối dependency
        |
        v
JUnit chạy assertions
        |
        v
Container được dừng và dọn theo lifecycle
~~~

Container có thể là một PostgreSQL instance, broker hoặc dịch vụ khác. Test không nên giả định port host cố định vì Testcontainers thường ánh xạ port ngẫu nhiên để tránh xung đột.

### 4.1. Những khái niệm quan trọng

- **Image:** phiên bản phần mềm container được khởi chạy, ví dụ PostgreSQL 16.
- **Container:** instance thực tế được tạo từ image.
- **Mapped port:** port trên host được ánh xạ tới port trong container.
- **Wait strategy:** điều kiện xác định service đã sẵn sàng.
- **Reusable/static container:** container sống lâu hơn một test method hoặc class tùy cấu hình.
- **Lifecycle:** ai khởi tạo, dừng và dọn container.
- **Network:** cách các container giao tiếp với nhau khi test nhiều dependency.

Testcontainers cần Docker hoặc một môi trường tương thích được cấu hình đúng. Nếu Docker daemon không sẵn sàng, test có thể fail trước khi chạy test body; đây là lỗi môi trường test cần hiển thị rõ.

## 5. Thêm dependency cho JUnit và Testcontainers

Với Gradle Groovy DSL, một cấu hình minh họa:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot dependency management có thể quản lý version phù hợp cho một số dependency. Nếu dự án không dùng BOM/Dependency Management của Spring Boot, cần khai báo version Testcontainers nhất quán cho các module liên quan, tốt nhất thông qua BOM của Testcontainers.

Với Maven, cần các dependency tương đương trong test scope và cấu hình Surefire/Failsafe tương thích với JUnit Platform. Không nên trộn version ngẫu nhiên của Testcontainers core, JUnit module và database module.

### 5.1. Kiểm tra dependency tree

Nếu test không tìm thấy annotation @Testcontainers hoặc class PostgreSQLContainer, kiểm tra dependency đã vào test classpath chưa. Có thể dùng Gradle:

~~~bash
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Hoặc lọc dependency cụ thể:

~~~bash
./gradlew dependencyInsight --dependency testcontainers --configuration testRuntimeClasspath
~~~

Lệnh cụ thể có thể khác theo tên configuration của dự án. Tránh thêm cùng một thư viện ở nhiều version chỉ để làm IDE hết báo đỏ.

## 6. Integration test PostgreSQL với JUnit 5

Ví dụ đầu tiên dùng PostgreSQL container và JDBC để chứng minh test kết nối database thực. Đoạn code độc lập với Spring giúp hiểu lifecycle trước khi thêm ApplicationContext.

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Testcontainers
class PostgreSqlIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders")
            .withUsername("test")
            .withPassword("test");

    @Test
    void insertsAndReadsAnOrder() throws Exception {
        try (Connection connection = DriverManager.getConnection(
                postgres.getJdbcUrl(),
                postgres.getUsername(),
                postgres.getPassword())) {

            try (var statement = connection.createStatement()) {
                statement.execute("""
                    CREATE TABLE orders (
                        id VARCHAR(40) PRIMARY KEY,
                        status VARCHAR(30) NOT NULL
                    )
                    """);
            }

            try (PreparedStatement insert = connection.prepareStatement(
                    "INSERT INTO orders(id, status) VALUES (?, ?)")) {
                insert.setString(1, "O-100");
                insert.setString(2, "CREATED");
                assertEquals(1, insert.executeUpdate());
            }

            try (PreparedStatement query = connection.prepareStatement(
                    "SELECT status FROM orders WHERE id = ?")) {
                query.setString(1, "O-100");
                try (ResultSet result = query.executeQuery()) {
                    result.next();
                    assertEquals("CREATED", result.getString("status"));
                }
            }
        }
    }
}
~~~

Ở đây container là static nên được chia sẻ trong vòng đời class theo JUnit Testcontainers extension. Các test method trong class dùng cùng database instance; do đó cần quản lý dữ liệu test để không phụ thuộc thứ tự. Với container instance field, extension có thể khởi động/dừng theo từng test method, đổi lại thời gian chạy lớn hơn.

### 6.1. Vì sao không hardcode localhost:5432?

Testcontainers ánh xạ port động. Hãy lấy JDBC URL, username và password từ container:

~~~java
postgres.getJdbcUrl();
postgres.getUsername();
postgres.getPassword();
~~~

Không ghi cố định host port vì một developer có thể đã chạy PostgreSQL ở cổng 5432, CI có thể chạy nhiều job song song, và Docker Desktop có thể cấp port khác.

## 7. Spring Boot kết nối PostgreSQL container

Trong ứng dụng Spring, thường muốn test cả Spring wiring, repository, migration và transaction. JUnit 5 có thể quản lý container; Spring nhận thông tin kết nối thông qua DynamicPropertySource.

Ví dụ:

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

@SpringBootTest
@Testcontainers
class OrderDatabaseIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders")
            .withUsername("test")
            .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void applicationCanUseTheRealDatabase() {
        Integer result = jdbcTemplate.queryForObject(
            "SELECT 1",
            Integer.class
        );

        assertEquals(1, result);
    }
}
~~~

Spring Boot tạo DataSource từ các thuộc tính động. Test xác nhận ApplicationContext có thể kết nối database thật, thay vì chỉ kiểm tra một repository bằng mock.

### 7.1. @ServiceConnection

Với Spring Boot phiên bản hỗ trợ service connections (từ Spring Boot 3.1), có thể dùng @ServiceConnection để giảm cấu hình property thủ công cho các container được hỗ trợ:

~~~java
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;

@Container
@ServiceConnection
static final PostgreSQLContainer<?> postgres =
    new PostgreSQLContainer<>("postgres:16-alpine");
~~~

Cần thêm module Spring Boot Testcontainers tương ứng trong test scope. Cách này tiện khi auto-configuration nhận diện loại container; DynamicPropertySource vẫn hữu ích cho container tùy biến hoặc thuộc tính không được service connection tự cung cấp. Chọn một cơ chế cấu hình rõ ràng, tránh để cả hai cùng ghi đè một property mà không có lý do.

## 8. Test repository với database thật

Giả sử OrderRepository dùng Spring Data JPA. Một integration test có thể kiểm tra insert, query, unique constraint và mapping:

~~~java
@SpringBootTest
@Testcontainers
class OrderRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    OrderRepository repository;

    @Test
    void savesAndLoadsOrder() {
        Order order = new Order("O-200", OrderStatus.CREATED);

        repository.saveAndFlush(order);

        Order loaded = repository.findById("O-200").orElseThrow();

        assertEquals(OrderStatus.CREATED, loaded.getStatus());
    }
}
~~~

Order và OrderRepository là model/repository minh họa. Trong dự án thật, dùng factory hoặc builder test để tạo entity hợp lệ; tránh tạo object thiếu field bắt buộc rồi chỉ vì test không chạm đến invariant mà tưởng repository đúng.

### 8.1. Kiểm tra unique constraint

Ví dụ hai order không được có cùng external reference:

~~~java
@Test
void rejectsDuplicateExternalReference() {
    repository.saveAndFlush(order("O-1", "EXT-77"));

    assertThrows(
        DataIntegrityViolationException.class,
        () -> repository.saveAndFlush(order("O-2", "EXT-77"))
    );
}
~~~

Nếu exception được ném ra bởi database, cần bảo đảm test flush đúng thời điểm. JPA có thể trì hoãn SQL tới flush/commit, nên gọi save mà không flush có thể không làm lỗi xuất hiện ngay trong assertion.

## 9. Vì sao database cùng loại production quan trọng?

H2 hoặc một database in-memory có thể rất hữu ích cho một số test nhanh, nhưng không phải lúc nào cũng tương thích PostgreSQL/MySQL:

- SQL dialect và function khác nhau.
- Kiểu dữ liệu, JSON, UUID, timestamp và collation khác.
- Locking/isolation semantics khác.
- Unique constraint và null handling có khác biệt theo engine.
- Index, query planner và extension không giống.
- Migration có thể chạy ở H2 nhưng fail trên engine production.
- Transaction/sequence behavior có thể khác.

Nếu production dùng PostgreSQL, dùng PostgreSQL container để kiểm thử repository và migration quan trọng. Không cần bỏ mọi test in-memory; chỉ cần **không dựa vào H2 để chứng minh production database behavior**.

## 10. Kiểm thử Flyway migration

Migration là một phần của ứng dụng. Một repository test chạy được trên schema tự tạo bằng tay nhưng migration production lỗi vẫn có thể làm release thất bại.

Một chiến lược cơ bản:

1. Khởi tạo database rỗng.
2. Cho ứng dụng/Flyway chạy toàn bộ migration.
3. Kiểm tra bảng, index, constraint và dữ liệu seed cần thiết.
4. Chạy repository/service behavior.
5. Kiểm tra migration từ version cũ nếu có đường nâng cấp quan trọng.

Ví dụ test kiểm tra schema sau migration:

~~~java
@SpringBootTest
@Testcontainers
class DatabaseMigrationIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void flywayCreatesExpectedSchema() {
        Integer count = jdbcTemplate.queryForObject(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = 'orders'
            """,
            Integer.class
        );

        assertEquals(1, count);
    }
}
~~~

Ví dụ giả định Spring Boot tự cấu hình Flyway và migration nằm đúng thư mục cấu hình. Nếu dự án dùng Liquibase hoặc migration tool khác, kiểm tra theo công cụ đó.

### 10.1. Kiểm tra nâng cấp từ schema cũ

Một migration có thể chạy trên database rỗng nhưng fail khi bảng đã có hàng triệu record hoặc constraint cũ. Với migration quan trọng, tạo fixture từ schema/version trước, thêm dữ liệu đại diện, chạy migration rồi xác nhận:

- Dữ liệu cũ được giữ hoặc chuyển đổi đúng.
- Giá trị default không làm sai business meaning.
- Unique/index constraint không fail bất ngờ.
- Thời gian migration phù hợp cửa sổ triển khai.
- Ứng dụng cũ/mới có thể cùng chạy trong giai đoạn expand-contract.
- Rollback/forward-fix strategy đã được xác định.

Không nhất thiết mọi migration đều cần một full dataset production-size trong CI. Có thể dùng bộ dữ liệu kiểm thử đại diện, còn performance/locking migration cần một kiểm thử chuyên biệt gần quy mô thực tế.

## 11. Transaction và @Transactional trong integration test

Spring Test có thể rollback transaction của test method nếu test được cấu hình transactional. Điều này giúp dọn dữ liệu, nhưng cần hiểu ranh giới:

- Transaction trong thread test có thể rollback khi test kết thúc.
- HTTP request chạy ở server thread khác thường không nằm trong transaction của test client.
- Async worker hoặc message consumer dùng transaction riêng.
- External side effect như email/payment không rollback cùng DB.
- Test gọi commit rõ ràng hoặc chạy propagation khác có thể không được rollback như kỳ vọng.

Ví dụ:

~~~java
@SpringBootTest
@Transactional
class OrderServiceIntegrationTest {
    // DB work trong transaction test có thể rollback sau mỗi test.
}
~~~

Không dựa vào @Transactional để dọn mọi trạng thái nếu test có HTTP server, broker hoặc thread nền. Cần cleanup theo từng dependency và xác minh không còn dữ liệu rác.

### 11.1. Khi test transaction commit

Một số hành vi chỉ xuất hiện sau commit, ví dụ outbox publisher hoặc event listener. Có thể dùng test không rollback hoặc commit rõ theo thiết kế, rồi xóa dữ liệu bằng cleanup có kiểm soát. Test nên xác minh behavior production thực sự sử dụng, không ép mọi code chạy trong transaction giả của test.

## 12. Cô lập dữ liệu giữa các test

Test có thể chạy theo thứ tự khác nhau hoặc song song. Nếu cùng dùng một database/container, dữ liệu cần được cô lập.

Các cách phổ biến:

- Tạo unique ID cho từng test.
- Xóa dữ liệu theo test key sau khi chạy.
- Dùng schema/database riêng theo test suite hoặc worker.
- Dùng transaction rollback khi toàn bộ hoạt động nằm trong transaction test.
- Khởi tạo container theo class hoặc suite khi phù hợp.
- Dùng migration/reset strategy được kiểm soát.

Ví dụ unique ID:

~~~java
String orderId = "it-" + UUID.randomUUID();
~~~

Không dùng ID cố định nếu nhiều test có thể chạy song song trên cùng database. Nếu cần deterministic ID để dễ debug, thêm namespace theo test class/worker.

### 12.1. Tránh cleanup quá rộng

Một câu lệnh xóa toàn bộ bảng trong @AfterEach có thể xóa dữ liệu của test đang chạy song song. Nếu dùng truncate/cascade, chỉ dùng trên database/schema riêng mà test đó sở hữu. Tránh dùng shared development database làm Testcontainers substitute cho integration suite.

## 13. Lifecycle: static container hay instance container?

JUnit Testcontainers extension hỗ trợ hai kiểu thường gặp:

~~~java
@Testcontainers
class ExampleTest {

    @Container
    static final PostgreSQLContainer<?> shared =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    PostgreSQLContainer<?> perTest =
        new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

- **Static field:** container chạy một lần cho test class và dừng sau class. Các method chia sẻ dependency instance.
- **Instance field:** container có lifecycle theo test method, giúp cô lập mạnh hơn nhưng tốn thời gian khởi động.

Lựa chọn phụ thuộc chi phí khởi động, yêu cầu cô lập và trạng thái test. Với database lớn, thường chia sẻ static container trong class nhưng dùng dữ liệu riêng từng test. Với test kiểm tra trạng thái broker hoặc cấu hình có thể thay đổi mạnh, container riêng có thể an toàn hơn.

### 13.1. Không để container lifecycle xung đột Spring context cache

Spring Test cache ApplicationContext giữa các test class có cùng cấu hình. Nếu một class dừng container trong khi context vẫn giữ DataSource trỏ tới container đó, test class tiếp theo có thể gặp connection refused.

Các cách giảm rủi ro:

- Dùng cùng một cấu trúc container/lifecycle cho nhóm test chia sẻ context.
- Tạo một base class hoặc cấu hình test thống nhất nếu thật sự phù hợp.
- Tránh nhiều static container khác nhau nhưng Spring context được cache chung với dynamic properties không tương ứng.
- Chỉ dùng @DirtiesContext khi cần loại bỏ context cache; không dùng bừa bãi vì làm test suite chậm.
- Cân nhắc suite-level container hoặc service connection được quản lý tập trung nếu số lượng test lớn.

Phải xác định rõ ai sở hữu lifecycle container và context. Một cấu hình test chạy ổn riêng từng class nhưng fail khi chạy toàn suite thường có vấn đề ở đây.

## 14. Testcontainers với message broker

Một service có thể ghi Order vào PostgreSQL và phát OrderCreated qua Kafka. Unit test producer bằng mock chỉ chứng minh code gọi method; integration test với broker container kiểm tra kết nối, serialization, topic và consumer behavior gần thực tế.

Ví dụ khái niệm với Kafka container:

~~~java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
class KafkaContainerIntegrationTest {

    @Container
    static final KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse("apache/kafka-native:3.8.0")
        );

    @Test
    void brokerIsReachable() {
        String bootstrapServers = kafka.getBootstrapServers();

        assertNotNull(bootstrapServers);
        assertFalse(bootstrapServers.isBlank());
    }
}
~~~

API và package Kafka module phụ thuộc phiên bản Testcontainers. Một số dự án cũ dùng Kafka module/constructor khác; cần theo tài liệu version đã pin. Ví dụ trên chỉ minh họa cách lấy bootstrap servers từ container.

### 14.1. Cấu hình Spring Kafka

Có thể truyền bootstrap server động qua DynamicPropertySource:

~~~java
@DynamicPropertySource
static void kafkaProperties(DynamicPropertyRegistry registry) {
    registry.add(
        "spring.kafka.bootstrap-servers",
        kafka::getBootstrapServers
    );
}
~~~

Sau đó khởi tạo producer/consumer bean theo cấu hình ứng dụng. Cần bảo đảm topic được tạo đúng, serializer/deserializer tương thích và listener có đủ thời gian xử lý trước khi assertion.

### 14.2. Test publish và consume

Một test hữu ích nên kiểm tra:

1. Producer gửi event có key và schema đúng.
2. Broker nhận record.
3. Consumer đọc được payload.
4. Business handler tạo trạng thái đúng.
5. Duplicate event không tạo side effect lần hai.
6. Event sai schema/poison message được xử lý theo policy.
7. Retry/DLQ behavior được kiểm tra ở test chuyên biệt.

Không dùng sleep cố định để chờ consumer. Dùng Awaitility hoặc polling có timeout và điều kiện cụ thể; nếu không, test sẽ chậm và flaky.

Ví dụ polling đơn giản:

~~~java
await()
    .atMost(Duration.ofSeconds(10))
    .untilAsserted(() -> {
        assertEquals(
            OrderStatus.CREATED,
            orderRepository.findById(orderId).orElseThrow().getStatus()
        );
    });
~~~

Đoạn code cần dependency Awaitility và import tương ứng. Polling phải có timeout ngắn hợp lý và failure message đủ để debug.

## 15. Testcontainers với RabbitMQ, Redis và các dependency khác

Testcontainers có nhiều module tích hợp. Ví dụ khái niệm:

~~~java
// Redis: org.testcontainers:redis
GenericContainer<?> redis =
    new GenericContainer<>("redis:7-alpine")
        .withExposedPorts(6379);

// RabbitMQ: module RabbitMQ tương ứng
// Có thể dùng container chuyên biệt hoặc GenericContainer.
~~~

Lấy host/port qua container:

~~~java
String host = redis.getHost();
Integer port = redis.getMappedPort(6379);
~~~

Không assume service luôn ở localhost:6379 trên host. Trong một Docker network, container-to-container có thể dùng alias và internal port; test JVM chạy trên host thường dùng host/mapped port.

### 15.1. Chọn image có chủ đích

- Pin major/minor hoặc digest phù hợp mức tái lập.
- Chọn image được duy trì và có nguồn đáng tin.
- Cân nhắc kiến trúc CPU của developer/CI.
- Không dùng tag latest trong suite quan trọng vì nội dung image có thể đổi mà source không đổi.
- Nâng image có kế hoạch và chạy lại migration/compatibility tests.

Một image pin không đảm bảo tuyệt đối tái lập nếu registry thay đổi tag; digest là định danh mạnh hơn khi cần cố định artifact.

## 16. Kiểm thử HTTP API với Spring MVC

Có hai lựa chọn phổ biến:

- **MockMvc:** chạy Spring MVC stack trong test context mà không cần mở server port thật.
- **RANDOM_PORT/WebTestClient/HTTP client:** chạy server thật trên port ngẫu nhiên và gửi request qua HTTP.

MockMvc phù hợp để kiểm tra controller, filter, validation, serialization và service wiring. RANDOM_PORT phù hợp khi muốn kiểm tra network boundary, server configuration hoặc behavior phụ thuộc container thực.

Ví dụ MockMvc với SpringBootTest:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
class OrderApiIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void createsOrder() throws Exception {
        mockMvc.perform(
                post("/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {
                          "customerId": "C-10",
                          "currency": "VND"
                        }
                        """)
            )
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("CREATED"));
    }
}
~~~

Ví dụ cần import MockMvc, request builder, MediaType và jsonPath. Nó minh họa controller + Spring context; để kiểm tra DB thật, class cần cấu hình Testcontainers database như các phần trước.

### 16.1. Kiểm tra HTTP server thực

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderHttpIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void healthEndpointResponds() {
        // Gửi HTTP request tới localhost với port được cấp động.
    }
}
~~~

Không hardcode 8080 vì test song song và môi trường developer có thể đã dùng port này. Với HTTP integration, kiểm tra response body, headers, status và side effect nghiệp vụ khi phù hợp.

## 17. Test database + broker trong cùng một service

Một workflow thường có transactional outbox:

~~~text
HTTP POST /orders
       |
       v
OrderService
       |
       v
DB transaction:
  - insert order
  - insert outbox event
       |
       v
Commit
       |
       v
Outbox publisher -> Kafka
       |
       v
Consumer -> downstream state
~~~

Một component test có thể dựng PostgreSQL và Kafka containers cùng lúc để xác minh wiring và contract. Nhưng test phải có mục tiêu rõ:

- Sau khi tạo order, row Order được commit.
- Outbox row được ghi cùng transaction.
- Publisher phát event với stable eventId.
- Consumer xử lý event và tạo downstream state đúng.
- Nếu publisher gửi lại, consumer không tạo side effect trùng.

Không nhất thiết mỗi test repository đều khởi động cả PostgreSQL và Kafka. Tách test DB, broker và một số ít component flow giúp chẩn đoán nhanh hơn.

### 17.1. Kiểm tra atomicity của outbox

Test có thể mô phỏng transaction rollback:

- Gây lỗi trước commit và xác nhận cả Order lẫn Outbox đều không tồn tại.
- Commit thành công và xác nhận cả hai tồn tại.
- Publisher crash sau publish nhưng trước khi đánh dấu sent; event có thể được gửi lại.
- Consumer dedup theo eventId và không nhân đôi business effect.

Đây là behavior quan trọng của hệ thống phân tán; chỉ assert rằng publisher method được gọi một lần là chưa đủ.

## 18. Test dữ liệu bất đồng bộ đúng cách

Một consumer có thể xử lý event sau khi test method đã gửi message. Cách chờ nên dựa trên điều kiện cuối:

~~~java
await()
    .alias("Order should become confirmed")
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        Order order = repository.findById(orderId).orElseThrow();
        assertEquals(OrderStatus.CONFIRMED, order.getStatus());
    });
~~~

Tránh:

~~~java
Thread.sleep(5000);
~~~

Sleep cố định có hai vấn đề: nếu consumer nhanh, test lãng phí thời gian; nếu consumer chậm hơn, test vẫn fail. Polling có timeout mô tả điều kiện cần đạt và cho biết lỗi khi không đạt.

### 18.1. Timeout phải phản ánh hợp đồng

Một test chạy trong CI chậm hơn local. Timeout nên đủ cho môi trường CI nhưng không quá dài để che deadlock. Với mỗi async test:

- Đặt timeout có lý do.
- Poll trạng thái có ý nghĩa.
- Khi fail, in correlation ID, topic/partition/offset hoặc trạng thái hiện tại.
- Không retry test thất bại vô hạn để làm xanh pipeline.
- Dọn message/state của test.

## 19. Test contract và schema evolution

Testcontainers giúp chạy broker thật, nhưng không thay thế contract testing. Producer/consumer cần kiểm tra:

- Schema compatibility.
- Required/optional fields.
- Semantic meaning.
- Event identity và aggregate version.
- Ordering assumptions.
- Retry, duplicate và replay.
- Backward/forward compatibility theo policy.

Một producer có thể gửi JSON hợp lệ nhưng consumer vẫn hiểu sai semantics. Ví dụ field amount đổi từ “đơn vị đồng” sang “đơn vị xu” mà tên và kiểu vẫn giữ nguyên. Contract test schema không tự phát hiện thay đổi ý nghĩa; cần domain tests và review.

### 19.1. Kiểm tra compatibility qua nhiều phiên bản

Một test có thể deserialize fixture event của phiên bản cũ bằng consumer mới, hoặc xác minh producer mới vẫn tương thích với consumer cũ theo contract đã chọn. Giữ fixture có nguồn gốc/version rõ và tránh chỉ copy JSON tùy ý vào test.

## 20. Kiểm thử transaction, locking và concurrency

Database container cho phép test behavior gần production engine:

- Unique constraint khi hai request cùng ghi business key.
- Optimistic locking và version column.
- Pessimistic lock/row contention.
- Isolation level và lost update.
- Atomic conditional update.
- Transaction rollback.
- Deadlock handling/retry policy.

Một test concurrency cần đồng bộ worker có chủ đích, dùng dữ liệu riêng và timeout. Không nên dựa vào Thread.sleep để “tạo race condition”. Có thể dùng CountDownLatch, CyclicBarrier hoặc ExecutorService để điều khiển thời điểm hai transaction cùng thực hiện.

Ví dụ khái niệm:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch start = new CountDownLatch(1);

// Mỗi worker:
// 1. Mở transaction riêng
// 2. Đọc cùng trạng thái
// 3. ready.countDown()
// 4. start.await()
// 5. Thực hiện cập nhật
// 6. Ghi nhận kết quả
~~~

Sau test cần assert invariant cuối, ví dụ số reservation thành công không vượt lượng token. Đừng chỉ assert một thread nhận exception; hệ thống có thể vẫn ghi dữ liệu sai ở transaction còn lại.

### 20.1. Test thực tế với engine thật

Một concurrency test trên H2 có thể không tái hiện locking hoặc isolation của PostgreSQL. Dùng cùng engine production cho test có rủi ro dữ liệu, tài chính hoặc stock correctness.

## 21. Kiểm thử migration và rollback compatibility

Migration trong hệ thống triển khai rolling update có thể gặp ứng dụng version cũ và mới cùng chạy. Test nên mô phỏng:

1. Database schema version N.
2. Seed dữ liệu như production cũ.
3. Chạy migration lên N+1.
4. Chạy code mới.
5. Khi cần, xác minh code cũ vẫn đọc được trong cửa sổ tương thích.
6. Kiểm tra data backfill và invariant.
7. Xác định rollback chỉ đổi application hay cần forward fix/data repair.

Không giả định mọi DDL đều rollback dễ dàng hoặc migration destructive có thể đảo ngược. Với thay đổi lớn, dùng expand-contract: thêm cấu trúc mới, chuyển traffic, backfill/verify, rồi mới xóa cấu trúc cũ sau deprecation window.

## 22. Kiểm thử security integration ở mức phù hợp

Integration test cũng có thể xác minh:

- Spring Security filter chain hoạt động.
- Endpoint yêu cầu authentication.
- Role/scope được ánh xạ đúng.
- Service-to-service identity được kiểm tra.
- Database role chỉ có quyền cần thiết.
- TLS/certificate configuration nếu test environment hỗ trợ.
- Secret được inject qua property/reference và không log ra output.

Không đưa secret thật vào test source, fixture hoặc CI logs. Dùng credential dùng riêng cho container, biến môi trường test hoặc secret store được kiểm soát. Testcontainers database username/password đơn giản chỉ dành cho môi trường test cô lập.

## 23. Tổ chức test suite theo tag và nhóm chạy

Không phải integration test nào cũng cần chạy ở mỗi vòng feedback. Có thể dùng JUnit tags:

~~~java
@Tag("integration")
class OrderRepositoryIT {
}
~~~

Hoặc:

~~~java
@Tag("component")
class CheckoutComponentIT {
}
~~~

Một chiến lược CI minh họa:

| Nhóm | Khi chạy | Mục tiêu |
|---|---|---|
| Unit | Mọi commit/PR | Feedback nhanh |
| Slice | Mọi PR | Kiểm tra Spring layer |
| Integration | PR và main branch | DB/broker behavior thật |
| Contract | PR producer/consumer | Compatibility |
| Component | PR quan trọng hoặc nightly | Một service và dependencies |
| E2E | Nightly/release/canary | Hành trình trọng điểm |
| Migration/performance | Theo thay đổi và lịch riêng | Rủi ro dữ liệu/capacity |

Tên nhóm và cách chạy phụ thuộc build. Dùng JUnit tags, Gradle tasks hoặc Maven profiles nhưng phải bảo đảm test quan trọng không bị bỏ khỏi pipeline mặc định ngoài ý muốn.

## 24. CI với Docker và Testcontainers

CI runner cần môi trường Docker-compatible. Một pipeline thường:

~~~text
Checkout source
      |
      v
Resolve dependencies
      |
      v
Compile + unit tests
      |
      v
Start Testcontainers dependencies
      |
      v
Run integration tests
      |
      v
Collect test reports/container logs
      |
      v
Build artifact + publish only if checks pass
~~~

### 24.1. Những điều cần chuẩn bị

- Docker daemon hoặc Testcontainers Cloud/remote runtime được cấu hình phù hợp.
- Quyền truy cập image registry.
- Network/DNS đủ để pull image và test kết nối.
- CPU/RAM đủ cho database/broker.
- Timeout phù hợp với runner.
- Artifact lưu test report và log khi fail.
- Image version được pin.
- Không để container/test data tồn tại ngoài lifecycle ngoài ý muốn.

### 24.2. Không bỏ qua test khi Docker không có

Có thể dùng cấu hình disabledWithoutDocker cho một số test local tùy mục đích, nhưng trong CI bắt buộc kiểm thử integration thì Docker unavailable phải khiến pipeline báo lỗi rõ. Nếu mọi test tự động skip khi không có Docker, pipeline xanh nhưng không hề kiểm tra dependency thật.

Phân biệt **local developer convenience** với **CI acceptance policy**.

### 24.3. Build cache và image pull

Pull image có thể chiếm nhiều thời gian. Có thể cache layer/image ở runner theo policy, nhưng không dùng image cache cũ thiếu kiểm chứng hoặc chia sẻ mutable state giữa job không an toàn. Test vẫn phải chạy với image digest/version dự kiến.

## 25. Parallel execution và tài nguyên

JUnit có thể chạy test song song, nhưng container và database state cần được thiết kế cho điều đó.

Rủi ro:

- Hai test cùng dùng một ID.
- Hai class cùng migrate một database.
- Một test xóa bảng khi test khác đang chạy.
- Broker topic dùng chung và consumer nhận message của test khác.
- Container bị dừng trong khi Spring context khác vẫn sử dụng.
- Nhiều container cùng lúc làm CI hết RAM/CPU.
- Port cố định xung đột.

Cách xử lý:

- Namespace dữ liệu theo test/worker.
- Topic/schema riêng hoặc unique key.
- Không cleanup toàn cục trên shared database.
- Giới hạn parallelism theo tài nguyên.
- Dùng lifecycle container nhất quán.
- Cân nhắc tách test cần isolation cao sang process/task riêng.
- Thu log và thread dump khi test treo.

Chạy song song chỉ hữu ích nếu test độc lập và runner đủ tài nguyên. Tăng số thread có thể làm suite chậm hơn khi database hoặc Docker đã bão hòa.

## 26. Testcontainers và Spring context cache

Một lỗi thường gặp là mỗi test class tạo một container riêng nhưng Spring tái sử dụng context được cấu hình bởi container đã dừng. Kết quả là test đầu pass, test sau báo connection refused.

Cần thống nhất strategy:

- Một static container dùng chung cho một context/configuration.
- Một test base/configuration quản lý lifecycle chung nếu nhóm test cùng dependency.
- Container suite-level khi cần tối ưu startup và đã có cơ chế cleanup đáng tin.
- Context riêng khi endpoint/credentials/container thực sự khác nhau.
- Tránh @DirtiesContext hàng loạt chỉ để chữa triệu chứng lifecycle.

Không tạo static singleton container bằng utility tùy tiện nếu JUnit/Spring lifecycle không được hiểu rõ. Một singleton sai có thể sống qua test suite, giữ resource và khiến test phụ thuộc thứ tự.

## 27. Chờ readiness đúng cách

Container process chạy không đồng nghĩa database/broker đã nhận kết nối. Testcontainers module thường có wait strategy phù hợp, nhưng container tùy chỉnh có thể cần cấu hình:

- Log message readiness.
- HTTP health endpoint.
- TCP port open.
- Healthcheck.
- Custom wait strategy với timeout.

Ví dụ khái niệm:

~~~java
container.waitingFor(
    Wait.forHttp("/health")
        .forStatusCode(200)
        .withStartupTimeout(Duration.ofSeconds(60))
);
~~~

Chỉ dùng endpoint thật phản ánh dependency sẵn sàng cho test. Một TCP port mở nhưng schema migration chưa xong vẫn có thể làm test flaky.

## 28. Test data builder và fixture

Fixture tốt giúp test tập trung vào hành vi:

~~~java
final class OrderTestData {

    static Order validOrder(String id) {
        return new Order(
            id,
            "CUSTOMER-1",
            OrderStatus.CREATED
        );
    }
}
~~~

Builder/factory nên tạo object hợp lệ theo domain invariants, cho phép override field cần thiết và không giấu logic quan trọng. Tránh một ObjectMother khổng lồ với hàng trăm flag tùy chọn khiến test không rõ dữ liệu thực tế.

Với database, fixture cần phản ánh constraint thật và không dùng chung ID giữa test chạy song song. Dữ liệu nhạy cảm nên là synthetic, không sao chép customer production vào local container.

## 29. Kiểm tra cả dữ liệu và side effect

Một integration test không nên chỉ xác nhận method trả về một object. Tùy use case, cần kiểm tra:

- Database row/relationship đúng.
- Transaction commit/rollback.
- Event/outbox được ghi.
- Cache invalidation hoặc update.
- Audit record.
- HTTP status/body/headers.
- Duplicate request không nhân đôi effect.
- Error path không để lại trạng thái nửa vời.

Ví dụ create order:

~~~text
Gửi POST /orders
    |
    +--> HTTP 201 + orderId
    +--> Order row tồn tại
    +--> Outbox OrderCreated tồn tại
    +--> Tổng tiền và currency đúng
    +--> Không có payment charge ngoài ý muốn
~~~

Không phải test nào cũng phải kiểm tra tất cả. Chọn các assertion trực tiếp chứng minh contract quan trọng của test case.

## 30. Kiểm thử idempotency và retry

Trong hệ thống phân tán, request có thể được gửi lại sau timeout. Integration test nên xác minh cùng idempotency key không tạo hai order/payment effects:

~~~java
@Test
void repeatedRequestWithSameIdempotencyKeyDoesNotDuplicateOrder() {
    String key = "it-" + UUID.randomUUID();

    Order first = orderService.create(command(), key);
    Order second = orderService.create(command(), key);

    assertEquals(first.getId(), second.getId());
    assertEquals(1, orderRepository.countByIdempotencyKey(key));
}
~~~

Đây là ví dụ cần điều chỉnh theo API thật. Cần test thêm trường hợp cùng key nhưng payload khác; hệ thống thường phải trả conflict hoặc quy tắc đã định nghĩa thay vì âm thầm dùng kết quả cũ cho một yêu cầu khác.

Với payment provider, test sandbox/fake provider có contract riêng; PostgreSQL container không chứng minh provider thực xử lý idempotency đúng. Khi outcome timeout chưa rõ, kiểm tra lookup/reconciliation thay vì retry capture bằng key mới.

## 31. Kiểm tra consumer duplicate và out-of-order

Một consumer cần test:

- Event gửi hai lần chỉ tạo một business effect.
- Event version cũ vẫn được xử lý theo compatibility policy.
- Event đến sai thứ tự không làm state lùi.
- Missing sequence/gap được phát hiện.
- Poison message không chặn vô hạn partition.
- Retry/DLQ có observability và replay procedure.

Ví dụ logic version:

~~~java
if (event.version() <= aggregate.getVersion()) {
    return; // duplicate hoặc event cũ theo policy
}
if (event.version() != aggregate.getVersion() + 1) {
    throw new MissingSequenceException();
}
aggregate.apply(event);
~~~

Đây chỉ là mô hình cho aggregate có sequence liên tục. Không áp dụng kiểm tra version liên tiếp cho mọi loại event; semantics phải theo domain contract. Integration test cần chứng minh database state cuối, inbox/dedup record và offset/ACK behavior.

## 32. Kiểm thử external HTTP dependency

Không phải dependency nào cũng có thể hoặc nên chạy trong container. Với payment/email/provider API, có thể dùng WireMock hoặc service giả lập để điều khiển response:

- 2xx thành công.
- 4xx không retry.
- 5xx retry có giới hạn.
- Timeout sau khi provider đã xử lý.
- Connection reset.
- Response malformed.
- Rate limit/429 với Retry-After.
- TLS/authentication failure.

Mục tiêu là mô phỏng failure mode có chủ đích. Nhưng test với mock server không chứng minh integration thực tế với provider production; cần contract/sandbox tests hoặc kiểm thử định kỳ phù hợp.

### 32.1. Không giả lập mọi thứ

Nếu test cần xác minh serialization của Kafka, hãy dùng Kafka thật qua Testcontainers. Nếu test chỉ kiểm tra Checkout gọi Payment client với đúng idempotency key, một HTTP mock server có thể phù hợp và nhanh hơn. Chọn mức thật theo ranh giới đang kiểm tra.

## 33. Testcontainers với nhiều container và Docker network

Một component test có thể cần PostgreSQL và Kafka. Test JVM có thể kết nối tới cả hai qua mapped ports. Nếu một container cần gọi container khác, dùng Docker network và network alias:

~~~java
Network network = Network.newNetwork();

GenericContainer<?> serviceA =
    new GenericContainer<>("example/service-a:1.0")
        .withNetwork(network)
        .withNetworkAliases("service-a");

GenericContainer<?> serviceB =
    new GenericContainer<>("example/service-b:1.0")
        .withNetwork(network)
        .withNetworkAliases("service-b");
~~~

Cần quản lý lifecycle Network và container đúng cách, thường dùng try-with-resources hoặc container rules phù hợp. Không hardcode container IP vì Docker network có thể cấp địa chỉ khác giữa các lần chạy.

## 34. Testcontainers reuse và hiệu năng suite

Khởi động container mỗi test method có thể rất chậm. Một số chiến lược:

- Static container per class.
- Chia sẻ container theo test suite với lifecycle rõ.
- Dùng image/cache ở runner.
- Giảm số container trong test không cần chúng.
- Chạy test độc lập song song trong giới hạn tài nguyên.
- Dùng database/schema reset nhanh nhưng an toàn.
- Tách migration/performance tests khỏi mọi commit nếu chi phí lớn, vẫn chạy ở lịch/release phù hợp.

Testcontainers có tính năng reusable containers ở một số cấu hình, thường yêu cầu bật rõ ràng và có giới hạn. Reuse có thể giữ state giữa các lần chạy, làm test không còn sạch nếu reset không đúng. Không bật reuse trong CI một cách mặc định; ưu tiên lifecycle có thể tái lập.

## 35. Debug integration test thất bại

Khi test fail, thu thập:

- JUnit test report và stack trace đầy đủ.
- Container startup logs và exit code.
- Image/version/digest.
- Host và mapped port (không ghi secret).
- Spring property source đã áp dụng ở mức an toàn.
- Database logs, migration history và query failure.
- Broker topic/partition/consumer group/lag nếu liên quan.
- Thread dump khi treo hoặc timeout.
- CI runner resource pressure và Docker daemon status.

Một số lỗi thường gặp:

| Lỗi | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Could not find a valid Docker environment | Docker daemon/runtime chưa sẵn sàng | Kiểm tra Docker Desktop/CI socket |
| Connection refused | Container chưa ready hoặc lifecycle đã dừng | Wait strategy, Spring context cache |
| Port already allocated | Hardcode port hoặc cấu hình mapping sai | Dùng mapped port |
| Migration failed | SQL/schema/extension khác môi trường | Xem Flyway/Liquibase logs |
| Test pass riêng, fail cả suite | Shared state/lifecycle/order dependency | Chạy lặp, parallel và kiểm tra cleanup |
| Consumer timeout | Topic/ACL/serialization/async wait | Kiểm tra broker và consumer logs |
| Random constraint violation | Test data trùng hoặc test song song | Unique IDs, schema isolation |
| Context loads with wrong URL | Property precedence/cache | Dynamic properties/service connection |
| CI chậm bất thường | Image pull/resource contention | Image cache, parallelism, runner sizing |

Không chữa test flaky bằng cách tăng timeout vô hạn hoặc retry test tự động nhiều lần. Tìm nguyên nhân nondeterminism trước.

## 36. Test report và chẩn đoán khi CI fail

Gradle thường tạo JUnit XML và HTML reports dưới thư mục build/test-results và build/reports. CI nên lưu các report này cùng container logs khi failure.

Một task có thể được gọi riêng:

~~~bash
./gradlew test --tests '*OrderDatabaseIntegrationTest'
~~~

Hoặc theo tag/nhóm task tùy build configuration. Không nên chạy toàn suite mỗi khi sửa một test nhỏ, nhưng trước merge cần chạy tập kiểm tra mà repository yêu cầu.

### 36.1. Không che test failure

- Không dùng ignoreFailures cho pipeline acceptance.
- Không catch Throwable rồi log mà không fail test.
- Không biến Docker unavailable thành skipped trong CI bắt buộc.
- Không gắn @Disabled lâu dài mà không có issue/owner.
- Không retry tất cả test flaky để có build xanh.
- Giữ log đủ để tìm nguyên nhân nhưng loại bỏ credentials và dữ liệu nhạy cảm.

## 37. Tổ chức source và naming

Một cách tổ chức minh họa:

~~~text
src/
  main/
    java/...
    resources/
      db/migration/
  test/
    java/...
      unit/
      slice/
      integration/
      component/
    resources/
      application-test.yml
      fixtures/
        events/
        json/
~~~

Dự án có thể dùng source set riêng như integrationTest để chạy độc lập với unit tests. Nếu dùng Gradle custom source set, cần khai báo classpath, task, JUnit Platform và dependency configuration đầy đủ.

Naming có thể dùng hậu tố IT cho integration test nếu build tách test task. Nếu tất cả chạy trong test task mặc định, tên class không nhất thiết phải theo một quy ước cứng; điều quan trọng là dễ tìm, dễ chạy và phân loại được.

## 38. Một chiến lược integration test cho Order Service

Giả sử Order Service dùng Spring Boot, PostgreSQL, Kafka và external Payment API.

| Nhóm test | Dependency | Những gì kiểm tra |
|---|---|---|
| OrderRepositoryIT | PostgreSQL container | CRUD, query, constraints, locking |
| OrderMigrationIT | PostgreSQL container sạch/cũ | Flyway migrations, backfill, compatibility |
| OrderApiIT | Spring context + PostgreSQL | Validation, serialization, status, persistence |
| OrderOutboxIT | PostgreSQL + Kafka | Commit outbox, publish, duplicate handling |
| OrderConsumerIT | Kafka + PostgreSQL | Deserialize, idempotency, ordering |
| PaymentAdapterIT | HTTP mock/sandbox | Timeout, retry, idempotency, error mapping |
| OrderComponentIT | DB + broker + provider stub | Một luồng Order end-to-end trong phạm vi service |
| CheckoutE2E | Nhiều service | Hành trình người dùng trọng điểm |

Không cần chạy tất cả mọi tổ hợp dependency trong mỗi test. Tập trung vào boundary có rủi ro cao và các invariants quan trọng.

## 39. Ví dụ cấu hình Spring Boot test profile

Một file application-test.yml có thể giữ các cấu hình không nhạy cảm:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
  kafka:
    consumer:
      auto-offset-reset: earliest

logging:
  level:
    org.testcontainers: INFO
~~~

JDBC URL, username/password và broker address nên được cấp động bởi Testcontainers. Không ghi host/port production hoặc secret thật vào test profile. Nếu test cần tắt một scheduled job hoặc external integration, cấu hình rõ trong profile test và bảo đảm không vô tình làm thay đổi behavior đang cần kiểm tra.

### 39.1. Tránh ddl-auto=create-drop che migration

Nếu production dùng Flyway/Liquibase, integration test nên chạy migration thật và dùng validate phù hợp. Hibernate tự tạo schema có thể che lỗi migration, index hoặc constraint không đúng. Có thể dùng create-drop trong test chuyên biệt cho một số mục đích, nhưng không dùng nó làm bằng chứng migration production chạy được.

## 40. Kiểm thử Spring context và auto-configuration

Một integration test có thể xác nhận bean graph khởi tạo với dependency thật:

~~~java
@SpringBootTest
@Testcontainers
class ApplicationContextIntegrationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void loadsRequiredBeans() {
        assertNotNull(context.getBean(OrderService.class));
        assertNotNull(context.getBean(OrderRepository.class));
    }
}
~~~

Test context load hữu ích để phát hiện missing bean, profile sai hoặc configuration conflict. Nhưng không nên coi việc ApplicationContext khởi tạo thành công là đủ: cần test hành vi thực tế qua database/broker/API.

### 40.1. Context test quá rộng

@SpringBootTest có thể khởi động nhiều bean và dependency, làm test chậm. Dùng @DataJpaTest, @WebMvcTest hoặc test cấu hình hẹp hơn khi mục tiêu chỉ là một layer. Nếu test cần full wiring thì dùng SpringBootTest có chủ đích.

## 41. Testcontainers và phiên bản ứng dụng

Một test pass trên image PostgreSQL 16 không đảm bảo production PostgreSQL 15 tương thích hoàn toàn. Pin image gần production hoặc test ma trận version nếu tổ chức hỗ trợ nhiều phiên bản.

Cũng cần lưu ý:

- Java runtime/version.
- Spring Boot và Hibernate version.
- Database engine/extension.
- Kafka broker và client version.
- Serializer/schema registry.
- OS/architecture của runner.
- Timezone/locale và clock behavior.

Không phải lúc nào cũng cần test mọi tổ hợp. Chọn ma trận theo supported compatibility và thay đổi có rủi ro.

## 42. Test migration có dữ liệu lịch sử

Một migration có thể chạy nhanh trên database rỗng nhưng fail khi có dữ liệu cũ hoặc giá trị bất thường.

Một bộ test migration nên có fixture cho:

- Bản ghi có nullable field.
- Bản ghi duplicate theo dữ liệu lịch sử.
- Giá trị ở biên min/max.
- Encoding/timezone nếu liên quan.
- Foreign key/reference không còn hợp lệ.
- Bảng lớn cần backfill theo batch.
- Trạng thái đang chạy dở hoặc retry.

Nếu migration cần backfill dài, không chạy toàn bộ dữ liệu production trong mỗi PR. Có thể có test logic, test dữ liệu đại diện và performance rehearsal riêng. Mục tiêu là phát hiện rủi ro trước khi migration chạm production.

## 43. Test tính lặp lại và độc lập

Một test tốt phải có thể chạy:

- Một mình.
- Trong toàn suite.
- Nhiều lần liên tiếp.
- Theo thứ tự khác.
- Song song trong giới hạn hỗ trợ.
- Trên máy developer và CI.
- Với dữ liệu test mới, không phụ thuộc state cũ.

Có thể chạy lặp một test để tìm flaky behavior:

~~~bash
./gradlew test --tests '*OrderConsumerIT'
~~~

Lặp nhiều lần có thể thực hiện ở CI hoặc một script riêng; không cần nhét vòng lặp retry vào chính test. Nếu fail ngẫu nhiên, ghi lại seed, event ID, container logs và thời điểm để tái hiện.

## 44. Các lỗi thường gặp khi dùng Testcontainers

**Dùng H2 thay PostgreSQL rồi kết luận SQL production đúng.** Engine khác nhau có semantics khác nhau. Dùng container cùng họ với production cho test DB quan trọng.

**Dùng latest image.** Build có thể đổi behavior khi tag di chuyển. Pin version/digest theo policy.

**Hardcode port.** CI song song hoặc developer đã chiếm port. Lấy mapped port từ container.

**Dùng sleep cố định cho async consumer.** Test chậm và flaky. Poll điều kiện với timeout.

**Chia sẻ database nhưng dùng ID cố định.** Test va chạm dữ liệu. Tạo unique ID hoặc schema riêng.

**Dùng @Transactional để giả định mọi side effect rollback.** Thread khác, broker và provider không thuộc transaction test. Cleanup/dedup riêng.

**Dừng container quá sớm trong khi Spring context còn cache.** Test sau connection refused. Đồng bộ lifecycle container và context.

**Chỉ test container startup.** Dependency có thể mở port nhưng behavior chưa đúng. Test hành vi qua client thực.

**Bỏ qua migration.** Schema tự tạo che lỗi release. Chạy migration production-like.

**Mock tất cả dependency.** Không phát hiện serialization, SQL và protocol mismatch. Dùng Testcontainers ở boundary cần xác minh.

**Dùng container cho mọi unit test.** Suite chậm, debug khó. Giữ unit test nhẹ và chọn integration test theo rủi ro.

**Tăng timeout vô hạn để chữa flaky test.** Che race condition hoặc dependency treo. Điều tra readiness, data isolation và async behavior.

**Không thu log khi CI fail.** Khó phân biệt lỗi code, Docker, network hay image. Lưu report/container logs có kiểm soát.

**Tái sử dụng container có state cũ.** Test phụ thuộc lịch sử. Reset state hoặc dùng lifecycle sạch.

**Không kiểm tra duplicate/replay.** Message có thể được xử lý hai lần trong production. Test idempotency và side effects.

**Dùng test credentials thật.** Có thể lộ secret trong log/artifact. Dùng credential riêng, synthetic và quyền tối thiểu.

## 45. Quy trình thực hiện một integration test mới

Một quy trình thực dụng:

1. Viết rõ boundary cần kiểm tra: repository, HTTP, broker hay cả component.
2. Chọn dependency thật cần thiết; không khởi tạo container thừa.
3. Chọn image/version tương thích production.
4. Khai báo lifecycle và wait strategy.
5. Cấu hình Spring bằng service connection hoặc dynamic properties.
6. Chuẩn bị dữ liệu độc lập, có cleanup.
7. Thực hiện hành động qua public boundary mà test cần kiểm tra.
8. Assert cả response và side effect quan trọng.
9. Với async, chờ điều kiện bằng polling có timeout.
10. Thu diagnostics khi fail và chạy test độc lập/toàn suite.
11. Tích hợp vào đúng CI task/tag.
12. Ghi rõ test bảo vệ invariant hoặc regression nào.

Không viết một test quá rộng chỉ để chứng minh “mọi thứ chạy được”. Một test có mục tiêu hẹp thường cho failure message hữu ích hơn.

## 46. Ví dụ hoàn chỉnh theo luồng Order

Một component integration test có thể theo logic:

~~~text
Arrange:
  - PostgreSQL container sẵn sàng
  - Kafka container sẵn sàng
  - Spring ApplicationContext được cấu hình
  - Tạo customer/order input duy nhất

Act:
  - Gọi OrderService.createOrder(command)
  - Outbox publisher phát OrderCreated

Assert:
  - Order row tồn tại và status đúng
  - Outbox event có eventId/aggregateId
  - Kafka nhận event theo schema
  - Consumer tạo downstream state
  - Gửi lại cùng eventId không tạo side effect thứ hai

Cleanup:
  - Dữ liệu có namespace riêng
  - Container được dừng theo lifecycle
  - Không để message test ảnh hưởng test khác
~~~

Một số phần có thể được chia thành nhiều test để dễ chẩn đoán. Component test tổng hợp chỉ cần đủ để chứng minh đường tích hợp quan trọng; không cần lặp mọi assertion của repository test.

## 47. Checklist trước khi merge

- [ ] Test có kiểm tra một behavior/contract rõ ràng.
- [ ] Dependency được chọn phù hợp với boundary cần kiểm tra.
- [ ] Image/version được pin theo policy.
- [ ] Không hardcode port hoặc credential production.
- [ ] Container readiness được xác định đúng.
- [ ] Spring properties được cấp từ container động.
- [ ] Migration thật được chạy khi test cần database schema.
- [ ] Dữ liệu test không phụ thuộc thứ tự hoặc test khác.
- [ ] Transaction/async/external side effect được xử lý đúng.
- [ ] Không dùng Thread.sleep cố định cho consumer.
- [ ] Duplicate/retry/error path được kiểm tra khi có rủi ro.
- [ ] Test chạy được riêng và trong suite.
- [ ] Parallelism không làm va chạm state.
- [ ] CI có Docker-compatible runtime.
- [ ] CI không âm thầm skip integration tests bắt buộc.
- [ ] Test report và container logs có thể thu thập khi fail.
- [ ] Output không chứa secrets hoặc dữ liệu cá nhân.
- [ ] Test không quá rộng hoặc khởi tạo container không cần thiết.

## 48. Bài tập thực hành

### Bài A — Repository với PostgreSQL

Tạo OrderRepository dùng Spring Data JPA. Viết integration test dùng PostgreSQL container để lưu, đọc, cập nhật trạng thái và kiểm tra unique constraint. Chạy migration thay vì tạo schema thủ công.

### Bài B — Dynamic properties

Viết test SpringBootTest với PostgreSQL container. Cấu hình URL, username, password bằng DynamicPropertySource. Sau đó chuyển sang ServiceConnection nếu phiên bản Spring Boot hỗ trợ và so sánh độ rõ của cấu hình.

### Bài C — Migration từ phiên bản cũ

Tạo schema version N, seed dữ liệu cũ, chạy Flyway lên N+1. Kiểm tra dữ liệu, constraint và khả năng ứng dụng mới đọc. Mô phỏng trường hợp duplicate/null trong dữ liệu lịch sử.

### Bài D — Kafka producer/consumer

Dựng Kafka container, gửi OrderCreated event và xác nhận consumer cập nhật trạng thái. Gửi cùng eventId hai lần và chứng minh business effect chỉ xảy ra một lần.

### Bài E — Outbox atomicity

Tạo transaction ghi Order và Outbox. Test rollback trước commit, publisher crash sau publish và consumer redelivery. Xác nhận không mất event đã commit và không tạo effect trùng.

### Bài F — HTTP API

Dùng MockMvc hoặc RANDOM_PORT để gọi POST /orders. Kiểm tra status, response schema, database state và validation errors. Giải thích trường hợp nào cần HTTP server thực.

### Bài G — Async polling

Viết test chờ order chuyển từ CREATED sang CONFIRMED bằng Awaitility. Không dùng sleep. Đặt timeout, poll interval và message giúp xác định consumer lag hoặc lỗi xử lý.

### Bài H — Concurrency

Cho hai request cùng reserve một đơn vị inventory. Dùng PostgreSQL container và synchronization primitives để tạo cạnh tranh. Assert không oversell và kết quả transaction đúng.

### Bài I — Lifecycle và Spring context

Tạo hai test class dùng cùng Spring context nhưng container lifecycle khác nhau. Tái hiện lỗi connection refused, sau đó thiết kế lifecycle dùng chung hoặc context tách biệt.

### Bài J — CI integration tests

Cấu hình pipeline có Docker-compatible runner, chạy unit trước integration, lưu JUnit report và container logs khi fail. Chứng minh CI fail nếu Docker không sẵn sàng thay vì skip toàn bộ test bắt buộc.

### Bài K — Provider timeout

Dùng HTTP mock container để mô phỏng provider đã xử lý request nhưng response timeout. Test stable idempotency key, lookup trạng thái và reconciliation; không tạo payment attempt mới một cách mù.

### Bài L — Chạy song song

Bật parallel execution cho một nhóm integration tests. Dùng unique IDs/topic names, kiểm tra cleanup và chạy lặp để phát hiện flaky tests. Giới hạn concurrency theo tài nguyên CI.

## 49. Kết luận

JUnit 5 tổ chức test và assertions; Testcontainers cung cấp các dependency thật trong môi trường tạm thời; Spring Boot kết nối các thành phần qua cấu hình test có thể kiểm soát. Kết hợp đúng cách giúp phát hiện những lỗi mà mock hoặc database in-memory khó mô phỏng: SQL/migration khác engine, transaction boundary, serialization, broker protocol, Spring wiring và behavior khi retry/duplicate.

Một integration test có giá trị khi nó kiểm tra **một ranh giới có ý nghĩa và một hành vi có thể quan sát**, dữ liệu được cô lập, lifecycle rõ và kết quả lặp lại được trên developer machine lẫn CI. Không cần biến mọi test thành một hệ thống end-to-end nặng. Hãy giữ unit tests nhanh, dùng Testcontainers cho những dependency mà tính tương thích thực sự quan trọng, và bổ sung component/E2E tests cho các hành trình có rủi ro cao.

Khi test được thiết kế quanh contract và business invariant, nhóm có thể thay đổi service tự tin hơn: migration được kiểm tra trước release, message replay không nhân đôi side effect, transaction được xác minh trên database thật và lỗi môi trường được phân biệt với lỗi ứng dụng. Đó là cách đưa integration testing vào vòng đời phát triển Spring một cách bền vững.

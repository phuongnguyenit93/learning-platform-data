# Kiểm thử repository thật với SQL và ràng buộc dữ liệu

Repository là ranh giới giữa logic ứng dụng và database. Một unit test dùng mock repository có thể xác nhận service gọi đúng phương thức, nhưng không chứng minh câu SQL chạy đúng, mapping entity chính xác, transaction hoạt động hay database thực thi các ràng buộc dữ liệu.

Khi kiểm thử repository thật, test cần chạy với database engine và schema có hành vi gần với môi trường ứng dụng. Test thực hiện thao tác lưu, truy vấn, cập nhật và xóa thông qua repository thật; sau đó xác nhận kết quả đã được database xử lý. Với những yêu cầu phụ thuộc SQL hoặc dialect cụ thể, nên dùng cùng loại database với production, thường thông qua Testcontainers.

## 1. Repository thật khác gì repository mock?

Mock repository chỉ mô phỏng kết quả mà test đã khai báo. Nó không chạy SQL và không kiểm tra database:

```java
given(customerRepository.findByEmail("mai@example.test"))
    .willReturn(Optional.of(customer));
```

Đoạn test dùng mock có thể phù hợp khi kiểm tra service, nhưng nó không chứng minh:

- Derived query hoặc `@Query` tạo ra SQL đúng.
- Mapping giữa entity và cột database chính xác.
- Join, sort, pagination và native query hoạt động với dialect thật.
- Unique, foreign key, check constraint và `NOT NULL` được database thực thi.
- Transaction commit/rollback đúng như thiết kế.
- Migration tạo schema tương thích với code hiện tại.

Repository integration test dùng Spring context tối thiểu cần thiết cùng database thật. Nó kiểm tra hợp đồng giữa repository, ORM/JDBC layer, SQL và schema.

## 2. Chọn test slice phù hợp

Spring Boot cung cấp các test slice để chỉ nạp phần hạ tầng cần thiết:

| Annotation | Thành phần được cấu hình | Trường hợp sử dụng |
|---|---|---|
| `@DataJpaTest` | JPA repositories, entity scanning, `EntityManager` và hạ tầng JPA | Kiểm thử Spring Data JPA repository và mapping ORM |
| `@DataJdbcTest` | Spring Data JDBC repositories và JDBC hạ tầng liên quan | Kiểm thử repository dùng Spring Data JDBC |
| `@JdbcTest` | `DataSource`, `JdbcTemplate` và transaction support | Kiểm thử DAO/JDBC code hoặc câu SQL trực tiếp |
| `@SpringBootTest` | Application context rộng hơn, tùy cấu hình | Kiểm thử repository cùng service, transaction hoặc cấu hình ứng dụng tích hợp |

Các test slice thường chạy trong transaction và rollback sau mỗi test method. Đây là cách nhanh để giữ database sạch, nhưng vẫn phải chú ý những tác vụ commit độc lập hoặc truy cập từ thread khác.

Ví dụ repository JPA:

```java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
```

Với JDBC thuần, có thể inject `JdbcTemplate` vào DAO và dùng `@JdbcTest`. Nếu DAO là component do ứng dụng định nghĩa, dùng `@Import(CustomerJdbcRepository.class)` để đưa nó vào test slice.

## 3. Dùng database cùng loại với production

Một database nhúng như H2 có thể chạy nhanh, nhưng không bảo đảm tương thích hoàn toàn với PostgreSQL, MySQL, SQL Server hoặc Oracle. SQL syntax, kiểu dữ liệu, collation, sequence, JSON support, locking và hành vi constraint có thể khác nhau.

Nếu ứng dụng production chạy PostgreSQL, hãy ưu tiên chạy repository test trên PostgreSQL. Testcontainers khởi động database trong container và cung cấp kết nối cho Spring test context.

Với Spring Boot 3.1 trở lên, `@ServiceConnection` có thể tự cung cấp connection details từ container. Ví dụ Gradle dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    runtimeOnly 'org.postgresql:postgresql'
}
```

Để Boot quản lý các phiên bản đồng bộ, dùng Spring Boot dependency management hoặc BOM của dự án.

Ví dụ test slice JPA với PostgreSQL:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataJpaTest(properties = "spring.jpa.hibernate.ddl-auto=validate")
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class CustomerRepositoryTests {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private CustomerRepository customerRepository;
}
```

`@AutoConfigureTestDatabase(replace = NONE)` yêu cầu Spring Boot không thay database container bằng database nhúng. `@ServiceConnection` cung cấp JDBC connection details từ container. `@DataJpaTest` nạp repository và JPA infrastructure cần cho test.

Với Spring Boot cũ hơn 3.1, có thể dùng `@DynamicPropertySource` để đăng ký URL, username và password từ container:

```java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Khi dùng `@DynamicPropertySource`, nhớ import `DynamicPropertyRegistry` và `DynamicPropertySource` từ `org.springframework.test.context`. Container phải được khởi động trước khi Spring tạo datasource.

## 4. Kiểm thử schema được tạo bởi migration

Trong production, schema thường được quản lý bằng Flyway hoặc Liquibase. Nếu test chỉ để Hibernate tự tạo bảng từ entity, nó có thể bỏ qua lỗi migration hoặc khác biệt giữa schema test và schema production.

Một cách kiểm thử gần production là:

1. Khởi động database cùng engine với production.
2. Chạy migration thật của ứng dụng.
3. Đặt Hibernate ở chế độ `validate` để đối chiếu mapping với schema đã có.
4. Thực hiện repository operations và xác nhận kết quả.

Ví dụ Flyway migration tạo bảng khách hàng và đơn hàng:

```sql
CREATE TABLE customer (
    id BIGSERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    CONSTRAINT uk_customer_email UNIQUE (email),
    CONSTRAINT ck_customer_email_not_blank
        CHECK (length(trim(email)) > 0)
);

CREATE TABLE purchase_order (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    CONSTRAINT uk_purchase_order_number UNIQUE (order_number),
    CONSTRAINT ck_purchase_order_amount CHECK (amount >= 0),
    CONSTRAINT fk_purchase_order_customer
        FOREIGN KEY (customer_id) REFERENCES customer(id)
);
```

Đặt file migration theo convention của Flyway, ví dụ `src/main/resources/db/migration/V1__create_customer_and_order.sql`. Khi test context khởi động, Boot tự cấu hình Flyway nếu dependency và cấu hình migration có trong ứng dụng. `spring.jpa.hibernate.ddl-auto=validate` giúp phát hiện mapping không tương thích với schema đã migrate.

Không bật `ddl-auto=create` hoặc `create-drop` trong test migration nếu mục tiêu là kiểm chứng DDL production. Nếu Hibernate tự tạo lại bảng, test có thể không chạy trên schema do migration tạo ra.

## 5. Xác nhận thao tác ghi và đọc từ database

Một repository test cơ bản nên chứng minh dữ liệu đã được ghi xuống database và có thể được truy vấn lại. Với JPA, `save(...)` có thể chỉ đưa entity vào persistence context; SQL có thể chưa chạy ngay. `flush()` buộc Hibernate đồng bộ các thay đổi đang chờ xuống database.

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;

import static org.assertj.core.api.Assertions.assertThat;

@Autowired
private CustomerRepository customerRepository;

@Autowired
private TestEntityManager entityManager;

@Test
void savesAndReloadsCustomer() {
    String email = "customer-" + UUID.randomUUID() + "@example.test";

    Customer saved = customerRepository.save(new Customer(email, "Mai"));

    entityManager.flush();
    entityManager.clear();

    Customer reloaded = customerRepository.findById(saved.getId())
        .orElseThrow();

    assertThat(reloaded.getEmail()).isEqualTo(email);
    assertThat(reloaded.getDisplayName()).isEqualTo("Mai");
}
```

`flush()` buộc SQL insert/update được gửi tới database. `clear()` xóa entity khỏi persistence context; truy vấn tiếp theo phải đọc lại dữ liệu thay vì chỉ trả về object đang được quản lý. Cách này giúp test tránh trường hợp chỉ xác nhận state trong bộ nhớ.

Nếu dùng Spring Data JDBC hoặc JDBC thuần, thao tác repository thường thực thi SQL ngay trong lời gọi; không có JPA persistence context cần flush/clear. Hãy viết assertion theo semantics của công nghệ đang dùng.

## 6. Kiểm thử derived query, @Query và native SQL

Repository method có thể được Spring Data tạo query từ tên method hoặc khai báo bằng `@Query`. Test cần xác nhận điều kiện lọc và dữ liệu thực tế, đặc biệt với join, sorting, paging và biểu thức SQL phụ thuộc dialect.

Ví dụ derived query:

```java
Optional<Customer> findByEmail(String email);

List<Customer> findByDisplayNameContainingIgnoreCaseOrderByDisplayNameAsc(
    String keyword
);
```

Ví dụ JPQL và native query:

```java
@Query("select c from Customer c where lower(c.email) = lower(:email)")
Optional<Customer> findByEmailCaseInsensitive(String email);

@Query(value = "select count(*) from customer where email like :pattern",
       nativeQuery = true)
long countByEmailPattern(@Param("pattern") String pattern);
```

Test nên tạo dữ liệu có kết quả phân biệt rõ ràng:

```java
@Test
void findsCustomersByCaseInsensitiveEmail() {
    String email = "Mai-" + UUID.randomUUID() + "@example.test";
    customerRepository.saveAndFlush(new Customer(email, "Mai"));

    Customer found = customerRepository
        .findByEmailCaseInsensitive(email.toUpperCase(Locale.ROOT))
        .orElseThrow();

    assertThat(found.getEmail()).isEqualTo(email);
}
```

Với native SQL, chạy trên database engine thật giúp phát hiện cú pháp, tên bảng/cột, kiểu dữ liệu và function không tương thích. Khi query dùng pagination, hãy kiểm tra cả nội dung trang, tổng số bản ghi và thứ tự; dữ liệu test nên có nhiều bản ghi đủ để phân biệt các trang.

## 7. Kiểm thử unique constraint

Unique constraint phải được database thực thi. Nếu chỉ kiểm tra một validator ở tầng ứng dụng, test chưa chứng minh schema thật có constraint.

Giả sử `customer.email` có constraint `uk_customer_email`. Test có thể lưu bản ghi đầu tiên, sau đó thử lưu email trùng:

```java
import org.springframework.dao.DataIntegrityViolationException;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Test
void databaseRejectsDuplicateCustomerEmail() {
    String email = "unique-" + UUID.randomUUID() + "@example.test";

    customerRepository.saveAndFlush(new Customer(email, "First"));

    assertThatThrownBy(() ->
        customerRepository.saveAndFlush(new Customer(email, "Duplicate"))
    ).isInstanceOf(DataIntegrityViolationException.class);
}
```

`saveAndFlush(...)` buộc insert thứ hai chạy ngay, vì vậy test quan sát được lỗi constraint trong method. Nếu chỉ gọi `save(...)`, exception có thể chỉ xuất hiện lúc flush hoặc commit transaction và test có thể không bắt được tại vị trí assertion.

Với `@DataJpaTest`, mỗi test method thường chạy trong transaction được rollback khi kết thúc. Sau khi flush vi phạm constraint, transaction hiện tại có thể ở trạng thái rollback-only; không tiếp tục dùng transaction đó để kiểm tra thêm truy vấn khác. Hãy để test kết thúc và Spring rollback transaction.

## 8. Kiểm thử foreign key và check constraint

Foreign key bảo đảm bản ghi con tham chiếu tới bản ghi cha tồn tại. Check constraint bảo đảm giá trị thỏa một biểu thức SQL. Đây là quy tắc ở database layer, nên test nên xác nhận database từ chối dữ liệu không hợp lệ.

Ví dụ dùng `JdbcTemplate` để cố tình insert đơn hàng trỏ tới customer không tồn tại:

```java
import java.math.BigDecimal;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Autowired
private JdbcTemplate jdbcTemplate;

@Test
void databaseRejectsOrderWithMissingCustomer() {
    String orderNumber = "PO-" + UUID.randomUUID();

    assertThatThrownBy(() -> jdbcTemplate.update("""
        INSERT INTO purchase_order(customer_id, order_number, amount)
        VALUES (?, ?, ?)
        """, -999L, orderNumber, new BigDecimal("25.00")))
        .isInstanceOf(DataIntegrityViolationException.class);
}
```

Tương tự, test có thể thử insert `amount` âm để xác nhận `ck_purchase_order_amount` hoạt động. Dùng SQL trực tiếp ở đây giúp tách bạch lỗi database constraint khỏi validation hoặc kiểm tra trước khi lưu của entity.

Không phải lúc nào cũng cần test mọi constraint bằng JDBC trực tiếp. Với constraint được khai báo và kiểm tra thông qua repository save, hãy dùng repository nếu mục tiêu là xác nhận toàn bộ đường đi ứng dụng. Dùng JDBC trực tiếp khi muốn chứng minh chính database từ chối dữ liệu bất kể ORM hay validation layer.

## 9. SQL fixture bằng @Sql

Spring Test hỗ trợ `@Sql` để chạy script trước hoặc sau test method. Cách này hữu ích khi test cần một tập dữ liệu SQL rõ ràng hoặc cần kiểm tra truy vấn trên fixture có cấu trúc.

Ví dụ script `src/test/resources/sql/customer-fixture.sql`:

```sql
INSERT INTO customer (email, display_name)
VALUES ('fixture-398@example.test', 'Fixture Customer');
```

Đăng ký script:

```java
import org.springframework.test.context.jdbc.Sql;

@Test
@Sql("/sql/customer-fixture.sql")
void findsFixtureCustomer() {
    Customer found = customerRepository
        .findByEmail("fixture-398@example.test")
        .orElseThrow();

    assertThat(found.getDisplayName()).isEqualTo("Fixture Customer");
}
```

Với test transactional mặc định của `@DataJpaTest`, script `BEFORE_TEST_METHOD` thường chạy trong transaction test và dữ liệu được rollback sau method. Nếu test không chạy transaction hoặc script được cấu hình ở chế độ transaction độc lập, cần thiết kế cleanup tương ứng.

Có thể chỉ định rõ phase:

```java
@Sql(
    scripts = "/sql/customer-fixture.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD
)
```

Nếu dùng fixture có ID hoặc unique key cố định, không chạy cùng fixture đó đồng thời trên một database dùng chung nếu các transaction có thể nhìn thấy và xung đột dữ liệu. Với test song song, ưu tiên dữ liệu có định danh duy nhất hoặc database/schema riêng. Tránh script cleanup kiểu `DELETE FROM customer` trên database mà test khác đang sử dụng.

## 10. Transaction, flush và rollback trong repository test

`@DataJpaTest`, `@DataJdbcTest` và `@JdbcTest` thường được cấu hình để chạy mỗi test method trong transaction và rollback khi kết thúc. Điều này giúp test độc lập mà không phải cleanup thủ công mọi bản ghi.

Tuy nhiên, rollback không thay thế việc hiểu transaction boundary:

- JPA có thể trì hoãn SQL đến flush hoặc commit. Dùng `flush()` để phát hiện constraint và SQL lỗi trong test.
- Entity đã được quản lý có thể được trả về từ persistence context. Dùng `clear()` khi muốn xác nhận dữ liệu được đọc lại từ database.
- `REQUIRES_NEW` có thể commit transaction độc lập với transaction của test.
- Request gửi qua server `RANDOM_PORT` chạy trên thread server riêng, không nằm trong transaction của test method.
- Tác vụ `@Async`, scheduler hoặc message consumer cũng không tự tham gia transaction của test.
- Dữ liệu được ghi bởi external process không được rollback bởi transaction test.

Nếu test cần xác nhận dữ liệu đã commit và được một transaction khác nhìn thấy, hãy thiết kế test riêng cho transaction boundary đó. Có thể dùng `@Commit` hoặc `TestTransaction.flagForCommit()` khi thật sự cần commit, nhưng phải có cleanup tường minh và tránh dùng chung dữ liệu cố định.

## 11. Kiểm thử JDBC trực tiếp

Với repository sử dụng `JdbcTemplate`, `@JdbcTest` tạo slice gọn gồm `DataSource`, `JdbcTemplate` và transaction support. Có thể import DAO thật:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
@Import(CustomerJdbcRepository.class)
class CustomerJdbcRepositoryTests {

    @Autowired
    private CustomerJdbcRepository repository;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void queriesCustomerUsingSql() {
        jdbcTemplate.update("""
            INSERT INTO customer(email, display_name)
            VALUES (?, ?)
            """, "jdbc-398@example.test", "JDBC Customer");

        Customer customer = repository.findByEmail("jdbc-398@example.test");

        assertThat(customer.displayName()).isEqualTo("JDBC Customer");
    }
}
```

Nếu cần dùng database container thay vì database nhúng, kết hợp `@AutoConfigureTestDatabase(replace = NONE)` và connection details từ Testcontainers như ví dụ JPA. `@JdbcTest` kiểm tra SQL code thực thi qua JDBC; nó không tự động scan toàn bộ component như `@SpringBootTest`.

Với Spring Data JDBC repository, dùng `@DataJdbcTest` để nạp repository và mapping tương ứng. Nếu cần custom converter hoặc cấu hình bổ sung, đưa cấu hình đó vào test slice bằng `@Import`.

## 12. Kiểm thử truy vấn và ràng buộc phụ thuộc database

Một số hành vi không thể mô phỏng đáng tin cậy bằng database nhúng hoặc mock:

- JSON/JSONB operators và index trong PostgreSQL.
- Collation, case sensitivity và so sánh chuỗi theo database.
- `TIMESTAMP WITH TIME ZONE`, precision và cách làm tròn số.
- Sequence, identity generation và locking semantics.
- `ON DELETE CASCADE`, deferred constraint hoặc partial unique index.
- Native SQL, CTE, window function và function riêng của database.

Với các trường hợp này, hãy chạy test trên cùng loại database và phiên bản gần production. Hãy để migration thật tạo schema, rồi xác nhận kết quả qua repository hoặc JDBC. Không nên viết test mong một database khác có hành vi giống hoàn toàn chỉ vì cả hai đều hỗ trợ SQL.

## 13. Cô lập dữ liệu và chạy test song song

Khi nhiều repository test cùng dùng một database container, container riêng không tự động làm dữ liệu của từng test riêng biệt. Mỗi test vẫn cần dữ liệu độc lập:

- Dùng UUID hoặc test run ID cho email, mã đơn hàng và unique key.
- Chỉ xóa bản ghi thuộc test hiện tại.
- Tránh truncate bảng dùng chung khi test khác đang chạy.
- Dùng schema/database riêng nếu test cần reset hoặc migration phá hủy.
- Dùng fixture tĩnh chỉ khi database/schema được cô lập hoặc fixture không thể xung đột.
- Không chia sẻ mutable singleton state giữa các test chạy đồng thời.

Nếu build chạy nhiều JVM hoặc CI job cùng trỏ vào một database, UUID trong dữ liệu test giúp tránh trùng định danh nhưng không bảo vệ các thao tác reset toàn schema. Khi cần, tạo database hoặc schema riêng theo build/test run.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Test pass trên H2 nhưng fail trên production database | Dialect, kiểu dữ liệu, native SQL, collation hoặc constraint khác nhau |
| Unique constraint chỉ fail lúc test kết thúc | SQL chưa flush tại vị trí assertion; dùng `saveAndFlush()` hoặc `entityManager.flush()` |
| Test đọc dữ liệu cũ sau khi update | Entity còn trong persistence context; gọi `clear()` rồi đọc lại |
| Flyway/Liquibase migration không chạy | Thiếu dependency, sai migration location hoặc test slice không nạp migration config |
| Hibernate tự tạo bảng khiến migration lỗi không xuất hiện | Test đang dùng `ddl-auto=create/create-drop`; dùng migration thật và `validate` |
| Test container vẫn bị thay bằng database nhúng | Thiếu `@AutoConfigureTestDatabase(replace = NONE)` |
| Foreign key test thất bại ở tầng ORM trước database | Entity relationship hoặc cascade chặn trước khi SQL chạy; dùng JDBC để xác nhận constraint DB nếu đó là mục tiêu |
| Test song song xung đột unique key | Fixture hoặc mã định danh cố định được dùng chung |
| `@Transactional` không rollback dữ liệu từ API | Request chạy trên thread server riêng hoặc transaction được commit độc lập |
| SQL script cleanup xóa dữ liệu test khác | Script cleanup không giới hạn theo định danh hoặc namespace |

Khi debug, xác định lỗi phát sinh ở tầng nào: repository mapping, SQL execution, database constraint, migration, transaction hay test fixture. Bật log SQL hoặc log bind parameter trong thời gian điều tra có thể giúp hiểu câu lệnh thực tế; không nên để log nhạy cảm ở mức chi tiết trong môi trường dùng dữ liệu thật.

## 15. Quy trình xây dựng repository integration test

1. Chọn đúng slice: `@DataJpaTest`, `@DataJdbcTest`, `@JdbcTest` hoặc `@SpringBootTest`.
2. Dùng database cùng loại với production khi test phụ thuộc dialect hoặc constraint cụ thể.
3. Khởi động database bằng Testcontainers và ngăn Boot thay bằng embedded database.
4. Chạy migration thật và dùng Hibernate `validate` nếu ứng dụng dùng JPA.
5. Tạo dữ liệu riêng cho test hoặc dùng SQL fixture trong database/schema được cô lập.
6. Gọi repository thật để kiểm tra query, mapping và kết quả.
7. Dùng `flush()` để buộc SQL thực thi; dùng `clear()` khi cần đọc lại từ database.
8. Kiểm tra unique, foreign key, check và `NOT NULL` ở database layer.
9. Hiểu transaction rollback và cleanup cho các thao tác commit hoặc chạy trên thread/process khác.
10. Giữ test độc lập khi chạy song song và xác minh migration, SQL trên database production-like.

Repository test đáng tin cậy phải chứng minh được câu SQL và schema thật cùng thực hiện đúng hợp đồng dữ liệu. Dùng test slice để giữ context gọn, database cùng loại với production để kiểm tra dialect, migration thật để xác nhận schema và `flush()` để buộc các constraint được thực thi ngay tại vị trí cần kiểm tra. Nhờ vậy, test có thể phát hiện lỗi mà mock repository hoặc database nhúng không thể cho thấy.

# Phân biệt @DataJdbcTest, @JdbcTest và @SpringBootTest

Spring Boot cung cấp nhiều annotation kiểm thử để tạo Spring ApplicationContext với phạm vi khác nhau. Với ứng dụng dùng Spring Data JDBC, ba annotation thường được cân nhắc là `@DataJdbcTest`, `@JdbcTest` và `@SpringBootTest`.

- `@JdbcTest` tạo test slice cho tầng JDBC cơ bản: DataSource và JdbcTemplate. Nó phù hợp khi cần kiểm tra DAO hoặc SQL viết bằng JDBC.
- `@DataJdbcTest` tạo test slice dành cho Spring Data JDBC: ngoài hạ tầng JDBC, nó cấu hình các repository Spring Data JDBC và mapping aggregate.
- `@SpringBootTest` khởi tạo ApplicationContext của ứng dụng bằng SpringApplication. Nó phù hợp khi cần kiểm thử luồng nghiệp vụ qua nhiều bean hoặc cấu hình tích hợp của ứng dụng.

Điểm khác biệt chính là **phạm vi ApplicationContext và loại thành phần được tự động cấu hình**. Chọn annotation đúng giúp test nhanh hơn, ít phụ thuộc hơn và vẫn kiểm tra được lớp đang quan tâm.

Bài học giải thích từng annotation, các bean được nạp, transaction và rollback, database dùng trong test, cách thêm cấu hình riêng, ví dụ Java và cách chọn phạm vi test phù hợp.

## 1. Test slice và full application context

Spring Boot gọi những bài test chỉ nạp một phần cấu hình cần thiết là **test slice**. Slice giới hạn component scan và chỉ bật nhóm auto-configuration liên quan đến lớp cần kiểm thử.

`@JdbcTest` và `@DataJdbcTest` là hai test slice. Chúng thường không nạp toàn bộ service, controller, security và các bean nghiệp vụ khác của ứng dụng.

`@SpringBootTest` tạo ApplicationContext thông qua `SpringApplication` và sử dụng cấu hình chính của ứng dụng. Vì vậy, nó thường nạp nhiều bean hơn và có chi phí khởi tạo cao hơn.

Có thể hình dung phạm vi như sau:

~~~mermaid
flowchart TD
    A["@SpringBootTest"] --> B["Toàn bộ ApplicationContext"]
    B --> C["Service, repository, JDBC, cấu hình và các bean ứng dụng"]
    D["@DataJdbcTest"] --> E["Data JDBC test slice"]
    E --> F["Repository Spring Data JDBC + mapping + JDBC"]
    G["@JdbcTest"] --> H["JDBC test slice"]
    H --> I["DataSource + JdbcTemplate + JDBC infrastructure"]
~~~

Sơ đồ thể hiện phạm vi chính. Thành phần cụ thể còn phụ thuộc các auto-configuration có trên classpath và cấu hình test của dự án.

## 2. So sánh nhanh ba annotation

| Tiêu chí | `@JdbcTest` | `@DataJdbcTest` | `@SpringBootTest` |
| --- | --- | --- | --- |
| Phạm vi | JDBC slice | Spring Data JDBC slice | Full ApplicationContext |
| DataSource | Có | Có | Có nếu ứng dụng cấu hình |
| JdbcTemplate | Có | Có | Có nếu JDBC auto-configuration được bật |
| Spring Data JDBC repositories | Không phải mục tiêu của slice | Có | Có nếu ứng dụng cấu hình |
| Mapping aggregate | Không tự cấu hình Spring Data JDBC repository mapping | Có | Có nếu ứng dụng cấu hình |
| Service/controller thông thường | Không tự scan | Không tự scan | Được nạp theo cấu hình ứng dụng |
| Transaction test mặc định | Có, rollback sau mỗi test | Có, rollback sau mỗi test | Không tự thêm transaction cho test |
| Database mặc định | Embedded database nếu có | Embedded database nếu có | Theo cấu hình ứng dụng |
| Phù hợp nhất | DAO/JdbcTemplate/SQL thủ công | Repository, aggregate, converter, mapping | Use case nhiều tầng, wiring và tích hợp toàn ứng dụng |

Một điểm dễ nhầm: `@JdbcTest` không phải phiên bản rút gọn của `@DataJdbcTest` để kiểm thử repository. Spring Boot mô tả rõ `@JdbcTest` dành cho trường hợp chỉ cần DataSource và không dùng Spring Data JDBC; nếu test repository Spring Data JDBC, hãy dùng `@DataJdbcTest`.

## 3. @JdbcTest: kiểm thử JDBC cơ bản

`@JdbcTest` phù hợp khi code đang được kiểm thử thao tác trực tiếp với JDBC, ví dụ:

- DAO dùng `JdbcTemplate` hoặc `NamedParameterJdbcTemplate`.
- Repository tự viết bằng JDBC, không dùng Spring Data JDBC repository abstraction.
- Câu SQL thủ công, bind parameter, row mapping và transaction ở tầng JDBC.
- Một thành phần truy cập dữ liệu cần DataSource nhưng không cần mapping aggregate của Spring Data JDBC.

Theo cấu hình mặc định, slice này tạo một embedded database trong bộ nhớ nếu dependency database phù hợp có trên classpath và cấu hình test cho phép, đồng thời cấu hình `JdbcTemplate`.

Các bean `@Component` và `@ConfigurationProperties` thông thường không được scan. Nếu cần kiểm thử một DAO cụ thể, có thể thêm nó bằng `@Import`.

### Ví dụ với JdbcTemplate

DAO:

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class LedgerDao {

    private final JdbcTemplate jdbcTemplate;

    public LedgerDao(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int countEntries() {
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM ledger_entry",
            Integer.class
        );

        return count == null ? 0 : count;
    }
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.jdbc.test.autoconfigure.JdbcTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;

@JdbcTest
@Import(LedgerDao.class)
class LedgerDaoTest {

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Autowired
    LedgerDao ledgerDao;

    @Test
    void countsLedgerEntries() {
        jdbcTemplate.update(
            "INSERT INTO ledger_entry (description) VALUES (?)",
            "Opening balance"
        );

        assertThat(ledgerDao.countEntries()).isEqualTo(1);
    }
}
~~~

`@Import(LedgerDao.class)` đưa DAO vào context của test. Nếu không import, component scan bị giới hạn có thể không tạo bean `LedgerDao`.

Ví dụ giả định schema `ledger_entry` đã được tạo bởi schema SQL trong test hoặc migration được cấu hình cho test. Test không cần khởi tạo toàn bộ ứng dụng chỉ để kiểm tra câu SQL và cách DAO đọc kết quả.

## 4. @DataJdbcTest: kiểm thử Spring Data JDBC repository

`@DataJdbcTest` là lựa chọn phù hợp khi cần kiểm thử những thành phần thuộc Spring Data JDBC:

- Repository kế thừa `CrudRepository` hoặc repository interface tương ứng.
- Mapping aggregate root và entity con.
- `@MappedCollection`, `@Embedded`, `@Id` và `@Version`.
- Custom converter và JDBC mapping.
- Query method, derived query và thao tác lưu/đọc aggregate.
- Tương tác giữa repository Spring Data JDBC và `JdbcTemplate`.

Theo cấu hình mặc định, slice này tạo embedded database nếu có, cấu hình `JdbcTemplate` và Spring Data JDBC repositories. Nó cũng scan các class kế thừa `AbstractJdbcConfiguration` để nạp cấu hình JDBC chuyên biệt.

Các `@Component` và `@ConfigurationProperties` thông thường không được scan. Nếu cần một service hoặc bean hỗ trợ trong test, hãy import tường minh hoặc khai báo cấu hình test.

### Ví dụ kiểm thử repository

Giả sử có aggregate:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerRepository
        extends CrudRepository<Customer, Long> {
}
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest;

@DataJdbcTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void savesAndLoadsCustomer() {
        Customer saved = customers.save(
            new Customer("jens@example.com")
        );

        Customer loaded = customers.findById(saved.getId())
            .orElseThrow();

        assertThat(loaded.getEmail())
            .isEqualTo("jens@example.com");
    }
}
~~~

`@DataJdbcTest` tự cấu hình repository Spring Data JDBC. Không cần tự tạo `JdbcAggregateTemplate` hoặc `JdbcMappingContext` chỉ để chạy CRUD repository trong test slice.

## 5. @SpringBootTest: kiểm thử toàn bộ ứng dụng

`@SpringBootTest` tạo ApplicationContext bằng `SpringApplication` và sử dụng cấu hình chính của Spring Boot. Đây là lựa chọn phù hợp khi bài test cần nhiều thành phần phối hợp:

- Service gọi repository và các service khác.
- Transaction bao quanh toàn bộ use case.
- ApplicationEvent, EntityCallback hoặc các bean được cấu hình trong ứng dụng.
- Security, validation, configuration properties hoặc integration khác.
- Luồng HTTP qua controller và web server.

Khác với hai test slice, `@SpringBootTest` không giới hạn component scan vào một phần cụ thể của ứng dụng. Các auto-configuration và bean được cấu hình như khi chạy ứng dụng thật.

### Ví dụ kiểm thử service dùng repository

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Transactional
class CustomerApplicationServiceTest {

    @Autowired
    CustomerApplicationService service;

    @Test
    void registersCustomerThroughApplicationService() {
        Long customerId = service.register("jens@example.com");

        assertThat(customerId).isNotNull();
    }
}
~~~

`WebEnvironment.NONE` yêu cầu Spring Boot tạo ApplicationContext không có môi trường web. Test vẫn nạp các bean của ứng dụng, nhưng không khởi động embedded web server.

Trong ví dụ, `@Transactional` được thêm tường minh để test chạy trong transaction và rollback sau mỗi test theo cơ chế Spring Test. `@SpringBootTest` tự nó không mặc định thêm transaction cho test method.

### Các chế độ webEnvironment

`@SpringBootTest` hỗ trợ nhiều chế độ:

| Giá trị | Hành vi |
| --- | --- |
| `MOCK` | Mặc định; tạo web ApplicationContext với môi trường mock, không khởi động server |
| `RANDOM_PORT` | Khởi động web server thật trên cổng ngẫu nhiên |
| `DEFINED_PORT` | Khởi động web server thật trên cổng cấu hình |
| `NONE` | Tạo ApplicationContext không có web environment |

Dùng `MOCK` hoặc `NONE` cho test service/integration không cần HTTP server. Dùng `RANDOM_PORT` khi cần kiểm thử request qua server thật.

## 6. Transaction và rollback trong ba loại test

`@JdbcTest` và `@DataJdbcTest` mặc định chạy test trong transaction và rollback transaction khi test kết thúc. Vì vậy dữ liệu được insert trong test thường không còn sau khi test hoàn thành.

Ví dụ:

~~~java
@DataJdbcTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository customers;

    @Test
    void createsCustomer() {
        customers.save(new Customer("jens@example.com"));

        assertThat(customers.count()).isEqualTo(1);
    }
}
~~~

Sau test, transaction được rollback nên dữ liệu không được commit vào database test.

`@SpringBootTest` không tự động đặt test trong transaction. Nếu cần rollback, thêm `@Transactional` vào class hoặc method:

~~~java
@SpringBootTest
@Transactional
class CustomerServiceIntegrationTest {
    // test service; transaction của test được rollback sau mỗi method
}
~~~

### 6.1. Khi cần test commit thật

Nếu mục tiêu là kiểm tra dữ liệu sau commit, test có thể dùng `@Commit` hoặc `@Rollback(false)`, hoặc tắt transaction test bằng propagation phù hợp rồi tự quản lý transaction. Cần có bước dọn dữ liệu để các test không ảnh hưởng lẫn nhau.

Ví dụ tắt transaction do test framework tạo:

~~~java
@JdbcTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class LedgerDaoNonTransactionalTest {
}
~~~

Khi không có test transaction bao ngoài, DAO hoặc code ứng dụng sẽ dùng transaction riêng theo cấu hình của nó.

### 6.2. Lưu ý với RANDOM_PORT và DEFINED_PORT

Khi `@SpringBootTest` khởi động server thật, HTTP client và server xử lý trên các thread khác nhau. Transaction của test method chạy ở thread client không bao quanh transaction mà request xử lý ở server thread.

Vì vậy, nếu test được đánh dấu `@Transactional` nhưng gửi HTTP request tới server ở `RANDOM_PORT` hoặc `DEFINED_PORT`, transaction phía server không tự rollback theo transaction của test. Hãy dọn dữ liệu bằng API test, SQL cleanup hoặc chiến lược database isolation riêng.

## 7. Database nào được sử dụng trong test?

Với `@JdbcTest` và `@DataJdbcTest`, Spring Boot mặc định cấu hình embedded database trong bộ nhớ nếu có database embedded trên classpath. Cách này giúp test nhanh, không cần khởi chạy database riêng.

Tuy nhiên, embedded database có thể khác database production về:

- Cú pháp SQL và dialect.
- Kiểu dữ liệu, enum, JSON, array và sequence.
- Identifier quoting và quy tắc chữ hoa/chữ thường.
- Locking, isolation level và transaction semantics.
- Generated keys, batch insert và upsert.
- Constraint và hành vi migration.

Nếu cần test trên database đã cấu hình sẵn, dùng `@AutoConfigureTestDatabase(replace = Replace.NONE)` để Spring Boot không thay DataSource hiện có bằng embedded database.

Ví dụ:

~~~java
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.containers.PostgreSQLContainer;

@DataJdbcTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class PostgreSqlRepositoryTest {
}
~~~

Với database production như PostgreSQL, MySQL hoặc SQL Server, Testcontainers là lựa chọn phù hợp để chạy integration test trên đúng engine. Spring Boot hiện cũng hỗ trợ tích hợp container thông qua cơ chế service connection khi dùng phiên bản và module tương thích.

Không nên chỉ dựa vào H2 để kết luận câu SQL, khóa bi quan hoặc dialect-specific feature hoạt động giống production.

## 8. Thêm bean và cấu hình riêng vào test slice

Vì test slice giới hạn component scan, một service hoặc bean hỗ trợ có thể không xuất hiện trong ApplicationContext.

Có thể thêm bean bằng `@Import`:

~~~java
@DataJdbcTest
@Import(CustomerService.class)
class CustomerServiceSliceTest {
    // Repository và CustomerService được nạp cho test
}
~~~

Hoặc khai báo cấu hình chỉ dành cho test bằng `@TestConfiguration`:

~~~java
@TestConfiguration
class CustomerTestConfiguration {

    @Bean
    Clock testClock() {
        return Clock.fixed(
            Instant.parse("2026-01-01T00:00:00Z"),
            ZoneOffset.UTC
        );
    }
}
~~~

Sau đó import cấu hình:

~~~java
@DataJdbcTest
@Import(CustomerTestConfiguration.class)
class CustomerRepositoryTest {
}
~~~

`@TestConfiguration` được dùng bổ sung vào cấu hình chính của test. Nếu đặt bên trong test class, nó không thay thế cấu hình ứng dụng chính.

Với `@DataJdbcTest`, các class kế thừa `AbstractJdbcConfiguration` được scan để nạp cấu hình Spring Data JDBC. Điều này hữu ích nếu ứng dụng có custom conversions, naming strategy hoặc cấu hình JDBC chuyên biệt.

## 9. Khác biệt package và dependency giữa Spring Boot 3 và 4

Spring Boot 4 tách nhiều test slice thành các module riêng. Vì vậy, package của annotation test đã thay đổi so với Spring Boot 3.x.

| Annotation | Spring Boot 3.5 | Spring Boot 4.1 |
| --- | --- | --- |
| `@JdbcTest` | `org.springframework.boot.test.autoconfigure.jdbc.JdbcTest` | `org.springframework.boot.jdbc.test.autoconfigure.JdbcTest` |
| `@DataJdbcTest` | `org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest` | `org.springframework.boot.data.jdbc.test.autoconfigure.DataJdbcTest` |
| `@AutoConfigureTestDatabase` | `org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase` | `org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase` |
| `@SpringBootTest` | `org.springframework.boot.test.context.SpringBootTest` | `org.springframework.boot.test.context.SpringBootTest` |

Với Spring Boot 4, test slice tương ứng nằm trong các module:

- `spring-boot-jdbc-test` cung cấp `@JdbcTest`.
- `spring-boot-data-jdbc-test` cung cấp `@DataJdbcTest`.
- `spring-boot-test` cung cấp các thành phần kiểm thử cơ bản, bao gồm `@SpringBootTest`.

Với Gradle, các dependency test có thể được khai báo như sau khi dự án dùng Spring Boot 4:

~~~groovy
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-jdbc-test")
    testImplementation("org.springframework.boot:spring-boot-data-jdbc-test")
}
~~~

Các phiên bản dependency nên được quản lý bởi Spring Boot dependency management/BOM. Nếu chỉ dùng một trong hai slice, chỉ cần thêm module test tương ứng.

Hãy dùng phiên bản dependency theo Spring Boot BOM của dự án. Không copy import từ tài liệu Boot 4 vào dự án Boot 3 mà không kiểm tra package và dependency.

## 10. Chọn annotation theo mục tiêu kiểm thử

Có thể dùng bảng quyết định sau để chọn phạm vi phù hợp:

| Câu hỏi | Annotation nên chọn |
| --- | --- |
| Tôi chỉ cần kiểm tra SQL qua JdbcTemplate hoặc DAO JDBC? | `@JdbcTest` |
| Tôi cần kiểm tra CrudRepository, query method hoặc aggregate mapping của Spring Data JDBC? | `@DataJdbcTest` |
| Tôi cần kiểm tra service gọi repository, transaction và nhiều bean ứng dụng? | `@SpringBootTest` |
| Tôi cần kiểm tra controller hoặc request HTTP qua toàn bộ ứng dụng? | `@SpringBootTest` kết hợp cấu hình web phù hợp |
| Tôi cần kiểm tra SQL vendor-specific trên database production? | `@DataJdbcTest` hoặc `@JdbcTest` với database thật/Testcontainers |
| Tôi cần xác nhận cấu hình và wiring toàn ứng dụng? | `@SpringBootTest` |

### 10.1. Không ghép nhiều test slice vào cùng test class

Spring Boot không hỗ trợ kết hợp nhiều annotation slice như `@JdbcTest` và `@DataJdbcTest` trên cùng một test class. Mỗi slice có bộ lọc component scan và danh sách auto-configuration riêng.

Nếu cần một slice nhưng muốn thêm một số auto-configuration khác, hãy chọn một annotation test chính rồi thêm các annotation `@AutoConfigure…` phù hợp hoặc dùng `@ImportAutoConfiguration`.

Các annotation `@AutoConfigure…` cũng có thể được kết hợp với `@SpringBootTest` nếu cần một số test bean được cấu hình tự động mà vẫn muốn giữ full ApplicationContext.

### 10.2. Khi nào nên dùng @Import trong DataJdbcTest?

`@DataJdbcTest` phù hợp để kiểm thử repository, nhưng một service thông thường không tự động được scan. Nếu chỉ muốn kiểm tra service nhỏ phối hợp repository trong slice:

~~~java
@DataJdbcTest
@Import(CustomerApplicationService.class)
class CustomerApplicationServiceSliceTest {

    @Autowired
    CustomerApplicationService service;
}
~~~

Cách này chỉ thêm service được chỉ định và các dependency mà test cung cấp. Nếu service phụ thuộc nhiều bean, event listener, security hoặc cấu hình toàn ứng dụng, `@SpringBootTest` thường phản ánh hệ thống thực tế tốt hơn.

## 11. Ví dụ chọn đúng loại test cho cùng một chức năng

Giả sử ứng dụng có luồng đăng ký khách hàng:

~~~text
CustomerController
       |
       v
CustomerApplicationService
       |
       v
CustomerRepository
       |
       v
Spring Data JDBC / DataSource
~~~

Có thể chia test theo ranh giới:

- Test `CustomerRepository` bằng `@DataJdbcTest` để xác nhận mapping và SQL.
- Test DAO dùng `JdbcTemplate` bằng `@JdbcTest` nếu có truy vấn JDBC riêng.
- Test `CustomerApplicationService` bằng `@SpringBootTest` để xác nhận validation, transaction, callback và các bean được wiring.
- Test HTTP endpoint bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)` hoặc slice web phù hợp nếu chỉ cần kiểm tra controller.

Không cần chạy full ApplicationContext cho mọi test repository. Ngược lại, test một use case phụ thuộc nhiều bean không nên giả định một test slice tự nạp toàn bộ service graph.

## 12. Cấu hình database thật với Testcontainers

Embedded database hữu ích cho test nhanh, nhưng không thay thế integration test trên database production khi ứng dụng phụ thuộc vào dialect hoặc hành vi vendor-specific.

Ví dụ, nếu production dùng PostgreSQL, một test slice có thể dùng PostgreSQL container thay cho H2:

~~~java
@DataJdbcTest
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
@Testcontainers
class PostgreSqlCustomerRepositoryTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:17");

    // Cấu hình DataSource để kết nối container,
    // hoặc dùng Spring Boot service connection phù hợp phiên bản.
}
~~~

Đây là khung minh họa; cách cung cấp thông tin kết nối phụ thuộc phiên bản Spring Boot và Testcontainers. Với Spring Boot có hỗ trợ service connection, có thể đăng ký container bean với `@ServiceConnection` để Boot tự cấu hình các connection details tương ứng.

Điều quan trọng là test phải thực sự kết nối container và không bị thay bằng embedded database. `replace = Replace.NONE` giữ lại DataSource được cấu hình cho test.

Các tình huống nên kiểm tra trên database thật:

- Generated keys và sequence.
- Composite ID và composite foreign key.
- SQL do dialect sinh, identifier quoting và phân trang.
- Pessimistic locking, isolation level và deadlock.
- Kiểu dữ liệu JSON, array, UUID hoặc kiểu vendor-specific.
- Migration Flyway/Liquibase và constraint.
- Upsert hoặc các query sử dụng cú pháp riêng của database.

Không nên chỉ dựa vào H2 để kết luận câu SQL, khóa bi quan hoặc dialect-specific feature hoạt động giống production.

## 13. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không inject được repository trong `@JdbcTest` | Đây không phải Spring Data JDBC repository slice | Dùng `@DataJdbcTest` |
| Không inject được service trong `@DataJdbcTest` | Slice không scan component thông thường | Dùng `@Import` hoặc `@TestConfiguration` |
| Test pass trên H2 nhưng fail ở production | SQL, dialect, type hoặc locking khác nhau | Chạy test với database production qua Testcontainers |
| Dữ liệu test biến mất sau mỗi method | Slice mặc định rollback transaction | Đây là hành vi mặc định; dùng `@Commit` hoặc tắt transaction nếu cần |
| Test `@SpringBootTest` để lại dữ liệu | Không có test transaction mặc định | Thêm `@Transactional` hoặc dọn dữ liệu tường minh |
| Test HTTP với RANDOM_PORT không rollback dữ liệu | Request xử lý trên server thread/transaction riêng | Dọn dữ liệu qua API hoặc SQL cleanup |
| Custom converter không được nạp trong slice | Cấu hình JDBC không nằm trong slice context | Đăng ký qua `AbstractJdbcConfiguration`, `@Import` hoặc cấu hình test |
| Import annotation không tìm thấy | Package test annotation khác giữa Boot 3 và Boot 4 | Kiểm tra phiên bản Boot và module test tương ứng |
| Test context khởi động chậm | Dùng full context cho test chỉ cần repository | Chuyển sang `@DataJdbcTest` hoặc `@JdbcTest` |
| Nhiều test slice trên một class không hoạt động | Spring Boot không hỗ trợ ghép nhiều slice annotation | Chọn một slice và bổ sung auto-configuration cần thiết |

## 14. Quy trình tổ chức test cho Spring Data JDBC

Một cấu trúc test có thể chia theo trách nhiệm:

1. **DAO test:** dùng `@JdbcTest` cho SQL JDBC viết tay và JdbcTemplate.
2. **Repository test:** dùng `@DataJdbcTest` cho aggregate mapping, repository, query method, converter và callback.
3. **Service integration test:** dùng `@SpringBootTest` khi cần xác nhận nhiều bean và transaction phối hợp.
4. **Web integration test:** dùng `@SpringBootTest` với `MOCK`, `RANDOM_PORT` hoặc `DEFINED_PORT` theo yêu cầu.
5. **Database compatibility test:** chạy slice hoặc full context trên đúng database bằng Testcontainers.
6. **Transaction test:** xác định rõ test cần rollback mặc định, commit thật hay nhiều transaction cạnh tranh.
7. **Configuration test:** import đúng custom JDBC configuration hoặc dùng full context nếu cấu hình được lắp ghép từ nhiều module.

Tách test theo ranh giới giúp lỗi dễ định vị. Nếu test repository fail, có thể tập trung vào mapping, SQL và database. Nếu test service fail nhưng repository test pass, cần xem lại quy tắc nghiệp vụ hoặc wiring giữa các bean.

## 15. Bài tập tự thực hành

### Bài 1 — So sánh hai slice

Viết một test dùng `@JdbcTest` để insert và query bằng `JdbcTemplate`. Viết test thứ hai dùng `@DataJdbcTest` để lưu và đọc cùng bảng bằng repository. Quan sát các bean được inject ở mỗi context.

### Bài 2 — Test repository

Tạo `CustomerRepository` và kiểm thử save, findById, update và delete bằng `@DataJdbcTest`. Xác nhận dữ liệu rollback sau test.

### Bài 3 — Test custom DAO

Tạo DAO dùng `NamedParameterJdbcTemplate`. Dùng `@JdbcTest` và `@Import` để đưa DAO vào context, sau đó kiểm tra bind parameter và row mapping.

### Bài 4 — Test service

Tạo `CustomerApplicationService` gọi repository và một bean khác. Dùng `@SpringBootTest(webEnvironment = NONE)` để kiểm tra wiring và luồng nghiệp vụ.

### Bài 5 — Transaction rollback

So sánh test slice mặc định với `@SpringBootTest` có và không có `@Transactional`. Kiểm tra dữ liệu sau mỗi test.

### Bài 6 — Test database thật

Chuyển một test repository từ H2 sang PostgreSQL Testcontainers. Xác nhận migration, generated key và query hoạt động trên database mục tiêu.

### Bài 7 — Custom configuration

Đăng ký custom converter hoặc naming strategy trong cấu hình JDBC. Kiểm tra nó được nạp trong `@DataJdbcTest` và so sánh với `@SpringBootTest`.

### Bài 8 — HTTP transaction

Tạo một test `@SpringBootTest(webEnvironment = RANDOM_PORT)` gửi request tạo dữ liệu. Xác nhận transaction test không tự rollback transaction phía server và thiết kế bước cleanup phù hợp.

## 16. Tài liệu tham khảo chính thức

- [Spring Boot 4.1 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): test slice, `@JdbcTest`, `@DataJdbcTest`, transaction mặc định và `@SpringBootTest`.
- [Spring Boot 4.1 — Test Modules](https://docs.spring.io/spring-boot/reference/testing/test-modules.html): các module test riêng như `spring-boot-jdbc-test` và `spring-boot-data-jdbc-test`.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): package annotation và cách cấu hình test slice trong dòng Boot 3.5.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): ApplicationContext, test execution và quản lý transaction trong Spring Test.

`@JdbcTest` tập trung vào DataSource và JdbcTemplate cho JDBC thuần; `@DataJdbcTest` bổ sung repository và mapping của Spring Data JDBC; `@SpringBootTest` kiểm thử ứng dụng với ApplicationContext đầy đủ. Hãy chọn phạm vi nhỏ nhất vẫn bao phủ hành vi cần kiểm tra, đồng thời dùng đúng database khi test phụ thuộc dialect, locking hoặc kiểu dữ liệu của production.

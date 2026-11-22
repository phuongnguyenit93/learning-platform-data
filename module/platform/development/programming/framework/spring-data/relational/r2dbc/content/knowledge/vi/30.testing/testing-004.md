# Kiểm thử Repository bằng @DataR2dbcTest

Spring Data R2DBC repository trả về các kiểu reactive như Mono và Flux. Vì vậy, kiểm thử repository cần xác nhận cả câu lệnh database lẫn cách publisher phát dữ liệu, hoàn tất hoặc báo lỗi. Spring Boot cung cấp annotation @DataR2dbcTest để tạo một test slice tập trung vào các thành phần R2DBC mà không khởi tạo toàn bộ ứng dụng.

Test slice này phù hợp để kiểm tra repository, mapping entity, derived query, custom query, DatabaseClient và R2dbcEntityTemplate. Nó giúp bài test chạy nhanh hơn so với khởi động toàn bộ application context, đồng thời vẫn sử dụng infrastructure Spring Data R2DBC thực tế.

Một repository test tốt cần xác nhận hành vi trên database: insert và generated ID, truy vấn theo điều kiện, phân trang/sắp xếp, mapping kiểu dữ liệu, custom SQL, constraint và transaction khi phù hợp. StepVerifier điều khiển subscription và kiểm tra các tín hiệu reactive. Với các khác biệt phụ thuộc database hoặc driver, Testcontainers cho phép chạy cùng hệ quản trị thực tế trong môi trường kiểm thử.

## 1. @DataR2dbcTest dùng để làm gì?

@DataR2dbcTest là test slice của Spring Boot dành cho ứng dụng dùng Spring Data R2DBC. Nó chỉ nạp nhóm cấu hình liên quan đến R2DBC và repository thay vì khởi tạo toàn bộ thành phần web, security, messaging hoặc các service không cần cho bài test repository.

Một test slice thường cung cấp:

- Cấu hình R2DBC ConnectionFactory.
- Spring Data R2DBC repository infrastructure.
- Entity mapping và các thành phần persistence liên quan.
- Các bean như DatabaseClient hoặc R2dbcEntityTemplate khi được auto-configure.
- Cấu hình database test theo khả năng và dependency có trên classpath.

Các component ứng dụng thông thường không nhất thiết được quét như trong full application context. Nếu repository test cần custom converter, mapping configuration hoặc bean hỗ trợ riêng, hãy import rõ ràng bằng @Import hoặc nested @TestConfiguration.

### Phạm vi của test slice

| Thành phần | Có phù hợp trong @DataR2dbcTest? |
| --- | --- |
| ReactiveCrudRepository | Có, đây là mục tiêu chính. |
| Custom repository implementation | Có, nếu được phát hiện và cấu hình trong slice. |
| DatabaseClient/R2dbcEntityTemplate | Có, khi auto-configuration tương ứng được kích hoạt. |
| Entity mapping và custom converters | Có, nhưng cấu hình tùy chỉnh cần được import nếu không tự được phát hiện. |
| Application service thông thường | Thường không được component-scan như full app; import/mock khi thật sự cần. |
| WebFlux controller và HTTP routing | Không phải phạm vi của slice này. |
| Security filter chain, messaging, scheduler | Không tự động khởi tạo toàn bộ như ứng dụng hoàn chỉnh. |
| Flyway/Liquibase migration | Không nên giả định luôn được kích hoạt trong slice; cần cấu hình hoặc chạy riêng theo mục tiêu test. |

Nếu cần kiểm tra HTTP request, validation hoặc controller, dùng @WebFluxTest hoặc @SpringBootTest với WebTestClient. Nếu cần kiểm tra toàn bộ service orchestration cùng repository và cấu hình ứng dụng, dùng @SpringBootTest.

## 2. Tạo repository test đầu tiên

Giả sử ứng dụng có entity Person lưu trong bảng people:

~~~java
@Table("people")
public record Person(
    @Id Long id,
    @Column("first_name") String firstName,
    String email
) {}
~~~

Repository:

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    Flux<Person> findByFirstName(String firstName);

    Mono<Person> findByEmail(String email);

    Mono<Boolean> existsByEmail(String email);
}
~~~

Test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

@DataR2dbcTest
class PersonRepositoryTest {

    @Autowired
    PersonRepository repository;

    @Test
    void savesAndFindsPerson() {
        Person input = new Person(
            null,
            "Ada Lovelace",
            "ada-" + UUID.randomUUID() + "@example.test"
        );

        StepVerifier.create(
            repository.save(input)
                .flatMap(saved -> repository.findById(saved.id()))
        )
        .assertNext(found -> {
            assertNotNull(found.id());
            assertEquals("Ada Lovelace", found.firstName());
            assertTrue(found.email().startsWith("ada-"));
        })
        .verifyComplete();
    }
}
~~~

Ví dụ giả định schema đã được khởi tạo và database hỗ trợ generated identity cho cột id. ID để null khi insert; Spring Data/driver nhận ID được database sinh và trả entity đã lưu. Hãy xác minh hành vi này trên database mục tiêu vì chiến lược sinh ID phụ thuộc database, schema và mapping.

Điểm quan trọng:

1. @DataR2dbcTest tạo test context cho persistence.
2. Spring inject repository thật, không phải mock.
3. repository.save trả Mono nên chưa thực thi cho tới khi có subscription.
4. StepVerifier subscribe và kiểm tra phần tử được phát.
5. findById chạy sau khi save hoàn tất nhờ flatMap.
6. verifyComplete xác nhận publisher hoàn tất mà không phát thêm lỗi.

Không gọi subscribe thủ công trong test rồi kiểm tra biến dùng chung. StepVerifier giữ việc subscribe và assertion trong cùng một luồng kiểm thử.

## 3. StepVerifier và cách kiểm tra Mono/Flux

Reactor Test cung cấp StepVerifier để kiểm tra các tín hiệu onNext, onComplete và onError theo thứ tự. Đây là cách phù hợp để xác nhận hành vi reactive mà không cần block trong code production.

### Kiểm tra Mono có một phần tử

~~~java
StepVerifier.create(repository.findById(id))
    .assertNext(person -> {
        assertEquals(id, person.id());
        assertEquals("Ada Lovelace", person.firstName());
    })
    .verifyComplete();
~~~

Nếu repository không tìm thấy ID, Mono hoàn tất rỗng. Khi test kỳ vọng có phần tử, dùng expectNext hoặc assertNext để test thất bại nếu không có dữ liệu.

### Kiểm tra Mono rỗng

~~~java
StepVerifier.create(repository.findByEmail("missing@example.test"))
    .verifyComplete();
~~~

Với phương thức trả Mono<Person>, không tìm thấy thường biểu diễn bằng Mono.empty. Không nhầm trường hợp này với lỗi database.

### Kiểm tra Flux có nhiều phần tử

~~~java
StepVerifier.create(repository.findByFirstName("Ada"))
    .expectNextMatches(person ->
        person.firstName().equals("Ada")
    )
    .expectNextMatches(person ->
        person.firstName().equals("Ada")
    )
    .verifyComplete();
~~~

Test trên giả định đúng hai bản ghi khớp. Nếu thứ tự không được bảo đảm bởi query, không nên phụ thuộc thứ tự phát phần tử. Hãy thêm ORDER BY hoặc dùng collectList rồi kiểm tra tập giá trị nếu thứ tự không phải một phần hợp đồng repository.

### Kiểm tra số lượng phần tử

~~~java
StepVerifier.create(repository.findByFirstName("Ada"))
    .expectNextCount(2)
    .verifyComplete();
~~~

expectNextCount chỉ xác nhận số lượng, không kiểm tra nội dung. Dùng assertNext khi cần kiểm tra field.

### Kiểm tra lỗi

~~~java
StepVerifier.create(repository.save(personWithInvalidData))
    .expectError()
    .verify();
~~~

Nếu cần xác nhận loại lỗi, dùng expectError(Class) hoặc expectErrorMatches. Loại exception cụ thể có thể phụ thuộc Spring exception translation và R2DBC driver. Với lỗi constraint, hãy xác minh trên driver/database thực tế thay vì giả định mọi vendor trả cùng một class.

## 4. Khởi tạo schema cho repository test

Repository cần bảng và cột tương ứng với entity. Có vài cách khởi tạo schema:

- Dùng schema.sql trong test resources.
- Dùng migration Flyway/Liquibase.
- Dùng script riêng cho Testcontainers.
- Tạo schema trong test setup qua DatabaseClient khi cần kiểm soát trực tiếp.

Ví dụ schema.sql cho bảng people:

~~~sql
CREATE TABLE people (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    first_name VARCHAR(120) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE
);
~~~

Đặt file tại:

~~~text
src/test/resources/schema.sql
~~~

Spring Boot có cơ chế SQL initialization cho R2DBC. Có thể cấu hình test để chạy script:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:schema.sql
~~~

Tên property và thời điểm initialization phụ thuộc Spring Boot version và cách test slice được cấu hình. Với database embedded, chế độ mặc định có thể chỉ khởi tạo schema trong trường hợp phù hợp. Với database bên ngoài hoặc Testcontainers, cấu hình mode rõ ràng nếu muốn dùng schema.sql.

Nếu test suite chạy song song trên cùng database, tránh để nhiều test cùng DROP/CREATE bảng. Nên tạo schema một lần cho container/context và dùng dữ liệu test độc lập.

### Dữ liệu mẫu

Có thể dùng data.sql để nạp dữ liệu cố định:

~~~sql
INSERT INTO people (first_name, email)
VALUES ('Ada Lovelace', 'ada@example.test');

INSERT INTO people (first_name, email)
VALUES ('Grace Hopper', 'grace@example.test');
~~~

Dữ liệu cố định hữu ích cho test query có kết quả xác định. Với test có thể chạy nhiều lần hoặc song song, dùng email/id duy nhất để tránh va chạm dữ liệu giữa các lần chạy.

Không dựa vào thứ tự insert để suy ra thứ tự SELECT. Nếu test yêu cầu thứ tự, query phải có ORDER BY.

## 5. Embedded database và database thực tế

@DataR2dbcTest có thể dùng embedded R2DBC database nếu driver và dependency tương ứng có trên test classpath, hoặc dùng database được cấu hình trong môi trường test. Embedded database giúp chạy nhanh và dễ thiết lập.

Tuy nhiên, database khác nhau có khác biệt về:

- Cú pháp SQL và function.
- Kiểu dữ liệu UUID, JSON, enum và timestamp.
- Generated identity/sequence.
- Constraint và error code.
- Transaction isolation, locking và savepoint.
- Collation, case sensitivity và quy tắc so sánh chuỗi.
- Cách xử lý LIMIT/OFFSET, RETURNING và upsert.

Một query chạy trên H2 chưa chắc chạy giống PostgreSQL hoặc MySQL. Embedded database phù hợp cho test repository đơn giản, mapping cơ bản và query portable. Với SQL đặc thù vendor hoặc tính năng quan trọng của production, hãy test bằng cùng loại database với môi trường thật.

### Không thay database chỉ để test dễ hơn

Nếu production dùng PostgreSQL và repository có query dựa vào JSONB, array, RETURNING hoặc operator riêng của PostgreSQL, H2 không thể chứng minh query hoạt động đúng. Test bằng H2 có thể vẫn hữu ích cho logic chung, nhưng cần integration test PostgreSQL để xác nhận hành vi thật.

## 6. Dùng Testcontainers với PostgreSQL

Testcontainers khởi chạy database thật trong container trong thời gian test. Cách này giúp kiểm tra R2DBC driver, SQL dialect, kiểu dữ liệu và constraint giống môi trường mục tiêu.

Dependency minh họa với Gradle:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Dự án cần có R2DBC PostgreSQL driver ở runtime/test runtime theo cấu hình dependency hiện tại. Version Testcontainers nên được quản lý nhất quán qua BOM hoặc dependency management của dự án.

Test class:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.r2dbc.DataR2dbcTest;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@DataR2dbcTest
@Testcontainers
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class PersonRepositoryPostgresTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void r2dbcProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.r2dbc.url",
            () -> "r2dbc:postgresql://"
                + POSTGRES.getHost()
                + ":"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", POSTGRES::getUsername);
        registry.add("spring.r2dbc.password", POSTGRES::getPassword);
    }

    @Autowired
    PersonRepository repository;

    @Test
    void persistsPersonInPostgres() {
        String email = UUID.randomUUID() + "@example.test";
        Person input = new Person(null, "Grace Hopper", email);

        StepVerifier.create(repository.save(input))
            .assertNext(saved -> {
                assertNotNull(saved.id());
                assertEquals(email, saved.email());
            })
            .verifyComplete();
    }
}
~~~

Ví dụ dùng PostgreSQL 16 image làm minh họa. Chọn image tag tương thích với database production và chính sách test của dự án. Annotation AutoConfigureTestDatabase với Replace.NONE yêu cầu Spring Boot không thay connection cấu hình bằng embedded test database; kiểm tra package/API theo Spring Boot version đang dùng.

### Vì sao cần @DynamicPropertySource?

Port của container thường được ánh xạ động trên host. Không nên hard-code localhost:5432. DynamicPropertySource đăng ký URL, username và password sau khi container cung cấp endpoint thực tế.

R2DBC URL có dạng r2dbc:postgresql://host:port/database. PostgreSQLContainer thường cung cấp JDBC URL, nhưng test R2DBC cần URL theo scheme của R2DBC driver. Hai URL phải trỏ tới cùng container/database.

### Docker và môi trường CI

Testcontainers cần Docker daemon hoặc runtime tương thích. Nếu môi trường developer/CI không có Docker, test có thể không chạy. Có thể:

- Cấu hình CI runner hỗ trợ Docker.
- Chạy nhóm test container trong pipeline integration riêng.
- Dùng embedded database cho test nhanh và Testcontainers cho nhóm test cần vendor thật.
- Dùng @Testcontainers(disabledWithoutDocker = true) khi phiên bản Testcontainers hỗ trợ và dự án muốn bỏ qua test nếu không có Docker.

Không âm thầm bỏ qua toàn bộ integration test trong CI production. Pipeline cần thể hiện rõ test nào đã chạy và test nào bị skip.

## 7. Giữ test slice nhỏ và import cấu hình cần thiết

@DataR2dbcTest không khởi tạo toàn bộ component scan như @SpringBootTest. Đây là chủ ý để test tập trung và nhanh.

Nếu cần custom converter hoặc mapping configuration, import rõ ràng:

~~~java
@DataR2dbcTest
@Import(ProductR2dbcConfiguration.class)
class ProductRepositoryTest {
    // repository tests
}
~~~

Nếu cấu hình chỉ dùng trong test, có thể khai báo nested @TestConfiguration:

~~~java
@DataR2dbcTest
class ProductRepositoryTest {

    @TestConfiguration
    static class TestConfig {
        // Test-only beans
    }
}
~~~

Không đưa toàn bộ service, controller và các client bên ngoài vào slice nếu mục tiêu chỉ là repository. Nếu cần bean service để kiểm thử flow lớn, hãy cân nhắc @SpringBootTest hoặc import đúng collaborator cần thiết.

### Custom conversions

Nếu entity có kiểu riêng, enum mapping đặc biệt hoặc converter tùy chỉnh, repository test cần dùng cùng conversion configuration với ứng dụng. Nếu test context không tự quét configuration đó, dùng @Import.

Ví dụ kiểu dữ liệu domain:

~~~java
public record Money(BigDecimal amount, String currency) {}
~~~

Nếu Money được lưu trong một cột NUMERIC hoặc VARCHAR theo quy ước riêng, cần converter đọc và ghi. Test nên xác nhận cả hai chiều:

1. Lưu entity có Money.
2. Đọc lại entity.
3. So sánh amount và currency.
4. Kiểm tra giá trị database nếu converter có representation đặc thù.

Đừng chỉ kiểm tra converter bằng unit test; repository integration test mới xác nhận converter thực sự được đăng ký trong mapping infrastructure.

## 8. Kiểm thử derived query methods

Spring Data có thể tạo query từ tên method. Test repository nên xác nhận method truy vấn đúng tập dữ liệu:

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    Flux<Person> findByFirstName(String firstName);

    Mono<Person> findByEmail(String email);

    Flux<Person> findByFirstNameOrderByEmailAsc(String firstName);
}
~~~

Test:

~~~java
@Test
void findsPeopleByFirstName() {
    String first = "Ada-" + UUID.randomUUID();

    Person firstPerson = new Person(null, first, "a-" + UUID.randomUUID() + "@example.test");
    Person secondPerson = new Person(null, first, "b-" + UUID.randomUUID() + "@example.test");

    StepVerifier.create(
        repository.saveAll(List.of(firstPerson, secondPerson))
            .thenMany(repository.findByFirstNameOrderByEmailAsc(first))
    )
    .assertNext(person -> assertTrue(person.email().startsWith("a-")))
    .assertNext(person -> assertTrue(person.email().startsWith("b-")))
    .verifyComplete();
}
~~~

Dùng unique prefix giúp test không bị ảnh hưởng bởi dữ liệu từ test khác. Query có OrderBy trong tên method tạo thứ tự rõ ràng; nếu không có sort, không nên kiểm tra thứ tự phát.

Với repository trả Mono<Person> cho query có thể khớp nhiều hàng, cần hiểu semantics của query và unique constraint. Nếu nhiều hàng khớp, kết quả có thể phát lỗi do nhiều kết quả hơn mong đợi. Dùng Flux khi quan hệ kết quả là nhiều phần tử hoặc bảo đảm điều kiện unique trong database.

## 9. Kiểm thử custom query bằng @Query

Với query khai báo, test phải chạy trên database để xác nhận SQL hợp lệ và mapping đúng.

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long> {

    @Query("""
        SELECT id, first_name, email
        FROM people
        WHERE LOWER(first_name) = LOWER(:name)
        ORDER BY id
        """)
    Flux<Person> searchByNameIgnoreCase(String name);
}
~~~

Test:

~~~java
@Test
void executesCustomQueryAndMapsRows() {
    String name = "Ada-" + UUID.randomUUID();

    Person input = new Person(null, name, "ada-" + UUID.randomUUID() + "@example.test");

    StepVerifier.create(
        repository.save(input)
            .thenMany(repository.searchByNameIgnoreCase(name.toUpperCase(Locale.ROOT)))
    )
    .assertNext(found -> assertEquals(name, found.firstName()))
    .verifyComplete();
}
~~~

Test này xác nhận:

- Named parameter được bind.
- Function LOWER được database hỗ trợ.
- Tên cột và alias phù hợp entity.
- Row được map thành Person.
- Query phát đúng kết quả.

Cú pháp text block và named parameter được hỗ trợ theo phiên bản Spring Data R2DBC. Nếu SQL dùng function hoặc operator riêng vendor, chạy test bằng đúng database production.

### Test query chỉ trả projection

Nếu query chỉ chọn một số cột, dùng projection phù hợp thay vì map vào entity đầy đủ:

~~~java
public record PersonSummary(Long id, String firstName) {}
~~~

Query:

~~~java
@Query("""
    SELECT id, first_name
    FROM people
    WHERE id = :id
    """)
Mono<PersonSummary> findSummaryById(Long id);
~~~

Test cần xác nhận alias/cột được ánh xạ đúng. Đừng dựa vào SELECT * cho projection vì schema thay đổi có thể làm query và mapping không còn khớp.

## 10. Kiểm thử DatabaseClient và R2dbcEntityTemplate

Không phải mọi persistence code đều đi qua repository interface. Custom repository có thể dùng DatabaseClient hoặc R2dbcEntityTemplate.

Có thể inject các thành phần này trong @DataR2dbcTest:

~~~java
@DataR2dbcTest
class ProductTemplateTest {

    @Autowired
    R2dbcEntityTemplate template;

    @Test
    void insertsAndReadsProduct() {
        ProductEntity product = sampleProduct();

        StepVerifier.create(
            template.insert(ProductEntity.class)
                .using(product)
                .flatMap(saved ->
                    template.select(ProductEntity.class)
                        .matching(query(where("id").is(saved.id())))
                        .one()
                )
        )
        .assertNext(found -> assertEquals(product.name(), found.name()))
        .verifyComplete();
    }
}
~~~

Ví dụ minh họa API template; cần import Criteria/Query và điều chỉnh ID generation theo entity/schema cụ thể.

Với DatabaseClient:

~~~java
@Autowired
DatabaseClient databaseClient;

@Test
void executesParameterizedSql() {
    String email = UUID.randomUUID() + "@example.test";

    StepVerifier.create(
        databaseClient.sql("""
            SELECT COUNT(*)
            FROM people
            WHERE email = :email
            """)
            .bind("email", email)
            .map((row, metadata) -> row.get(0, Long.class))
            .one()
    )
    .expectNext(0L)
    .verifyComplete();
}
~~~

Mapping theo index có thể phụ thuộc driver và metadata; với query thực tế, ưu tiên alias rõ và đọc theo tên cột khi phù hợp. Test cũng cần xác nhận kiểu Java mà driver trả về; COUNT có thể map thành Long hoặc kiểu số khác tùy driver.

## 11. Kiểm thử sorting và pagination

Repository test nên xác nhận page boundary và sort nếu repository expose Pageable/Sort hoặc custom pagination.

Ví dụ:

~~~java
Flux<Person> findByFirstName(String firstName, Sort sort);
~~~

Gọi:

~~~java
repository.findByFirstName(
    "Ada",
    Sort.by(Sort.Direction.ASC, "email")
);
~~~

Nếu custom repository dùng Pageable, test cần xác nhận:

- Offset được tính đúng.
- Page size giới hạn số phần tử.
- Sort có tie-breaker ổn định khi giá trị chính trùng nhau.
- Count query (nếu có) đếm đúng tập kết quả.
- Trang cuối và trang vượt phạm vi được xử lý đúng.

Không chỉ kiểm tra số lượng. Tạo dữ liệu test có giá trị sắp xếp trùng nhau để xác nhận tie-breaker. Nếu database query không có ORDER BY ổn định, test có thể thất bại ngẫu nhiên dù dữ liệu không đổi.

## 12. Kiểm thử constraint và exception translation

Database test là nơi phù hợp để xác nhận UNIQUE, NOT NULL, FOREIGN KEY và CHECK được thực thi.

Ví dụ email có unique constraint:

~~~java
@Test
void rejectsDuplicateEmail() {
    String email = UUID.randomUUID() + "@example.test";

    Person first = new Person(null, "First", email);
    Person duplicate = new Person(null, "Second", email);

    StepVerifier.create(
        repository.save(first)
            .then(repository.save(duplicate))
    )
    .expectError()
    .verify();
}
~~~

Test này xác nhận thao tác thứ hai phát lỗi. Nếu muốn kiểm tra exception type, dùng exception được Spring/driver trả về trong phiên bản và database cụ thể. Có thể kiểm tra cause chain hoặc SQLSTATE để phân loại integrity violation.

Không giả định mọi database trả cùng exception class hoặc message. Assertion theo message text dễ vỡ khi nâng driver/database version.

### Transaction sau lỗi constraint

Một số database đánh dấu transaction không thể tiếp tục sau lỗi statement cho tới khi rollback. Vì vậy, nếu test chạy nhiều lệnh trong cùng transaction, thao tác sau lỗi có thể thất bại dù lỗi ban đầu đã được bắt.

Hãy kiểm tra transaction semantics của database. Với test constraint đơn giản, cô lập thao tác ghi lỗi trong một test/transaction riêng hoặc dùng cleanup phù hợp.

## 13. Quản lý dữ liệu giữa các test

Test repository có thể dùng chung database hoặc application context. Nếu dữ liệu không được cô lập, test sẽ phụ thuộc thứ tự chạy và có thể thất bại khi chạy song song.

Một số cách:

- Dùng UUID hoặc giá trị duy nhất cho email/code mỗi test.
- Tạo dữ liệu qua repository trong chính test.
- Dùng schema/database riêng cho từng suite hoặc worker khi cần parallel execution.
- Xóa dữ liệu bằng reactive DatabaseClient và đợi cleanup hoàn tất.
- Khởi tạo schema một lần thay vì DROP/CREATE trước từng method nếu không cần.
- Không phụ thuộc dữ liệu do test khác tạo.

Ví dụ cleanup reactive trong test:

~~~java
@AfterEach
void cleanUp() {
    StepVerifier.create(
        databaseClient.sql("DELETE FROM people")
            .fetch()
            .rowsUpdated()
    )
    .expectNextMatches(rowsUpdated -> rowsUpdated >= 0)
    .verifyComplete();
}
~~~

rowsUpdated phát giá trị số hàng bị ảnh hưởng; expectNextMatches kiểm tra giá trị đó, còn expectNextCount chỉ đếm số tín hiệu onNext. Trong suite chạy song song, DELETE toàn bảng có thể xóa dữ liệu của test khác. Khi đó dùng unique test key và xóa theo key.

### Không cleanup bất đồng bộ rồi kết thúc test

Không gọi subscribe trong @AfterEach rồi để test kết thúc ngay. Khi đó cleanup có thể chưa hoàn tất trước khi test tiếp theo chạy. Dùng StepVerifier hoặc một cách đồng bộ rõ ràng trong test lifecycle để đợi cleanup.

## 14. Transaction trong @DataR2dbcTest

Transaction trong R2DBC là reactive và gắn với subscription/ Reactor Context. Điều này khác với JDBC transaction gắn với thread-bound connection.

Khi dùng transaction trong repository test:

- Xác định test context có cấu hình ReactiveTransactionManager hay không.
- Kiểm tra phiên bản Spring Boot/Spring Test có hỗ trợ transactional test semantics cho R2DBC theo cách đang sử dụng không.
- Publisher cần được subscribe trong đúng transaction context nếu muốn tham gia cùng transaction.
- Một subscription tách rời có thể không tham gia transaction đang được quản lý.
- Không tự mở transaction và gọi subscribe độc lập trong test setup.

Không nên giả định annotation @Transactional trên test method luôn hoạt động giống test JDBC. Hãy xác nhận behavior của Spring Boot version và reactive transaction test support. Với test cần kiểm soát rõ commit/rollback, dùng TransactionalOperator trong test hoặc test service thực tế rồi kiểm tra trạng thái dữ liệu sau khi publisher hoàn tất.

Ví dụ dùng TransactionalOperator để kiểm tra rollback:

~~~java
@Test
void rollsBackRepositoryWriteWhenPublisherFails() {
    Person person = new Person(
        null,
        "Rollback",
        UUID.randomUUID() + "@example.test"
    );

    Mono<Person> work = repository.save(person)
        .flatMap(saved ->
            Mono.<Person>error(new IllegalStateException("force rollback"))
        );

    StepVerifier.create(transactionalOperator.transactional(work))
        .expectError(IllegalStateException.class)
        .verify();

    StepVerifier.create(repository.findByEmail(person.email()))
        .verifyComplete();
}
~~~

Ví dụ giả định transactionalOperator dùng cùng ConnectionFactory với repository và test database hỗ trợ transaction. Test thực hiện subscription của transaction và truy vấn kiểm tra sau khi transaction đã rollback.

Nếu transaction manager của slice không được inject tự động trong phiên bản cụ thể, import cấu hình R2dbcTransactionManager hoặc tạo TransactionalOperator trong test configuration.

## 15. Test custom repository fragment

Custom repository fragment thường chứa query phức tạp hoặc logic dùng DatabaseClient. Test slice vẫn có thể kiểm tra fragment thông qua repository bean nếu implementation được phát hiện đúng quy ước.

Ví dụ interface:

~~~java
public interface PersonSearchRepository {
    Flux<Person> searchByPrefix(String prefix);
}
~~~

Repository chính:

~~~java
public interface PersonRepository
        extends ReactiveCrudRepository<Person, Long>,
                PersonSearchRepository {
}
~~~

Implementation theo naming convention:

~~~java
public class PersonSearchRepositoryImpl
        implements PersonSearchRepository {

    private final DatabaseClient databaseClient;

    public PersonSearchRepositoryImpl(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Flux<Person> searchByPrefix(String prefix) {
        return databaseClient.sql("""
                SELECT id, first_name, email
                FROM people
                WHERE first_name LIKE :prefix
                ORDER BY id
                """)
            .bind("prefix", prefix + "%")
            .map((row, metadata) -> new Person(
                row.get("id", Long.class),
                row.get("first_name", String.class),
                row.get("email", String.class)
            ))
            .all();
    }
}
~~~

Test qua repository:

~~~java
StepVerifier.create(repository.searchByPrefix("Ada"))
    .expectNextMatches(person ->
        person.firstName().startsWith("Ada")
    )
    .verifyComplete();
~~~

Nếu fragment implementation cần bean cấu hình riêng không có trong slice, import configuration cần thiết. Không mở rộng component scan toàn bộ ứng dụng chỉ để tìm một implementation.

## 16. Kiểm thử optimistic locking và version field

Nếu entity dùng @Version để optimistic locking, repository test nên xác nhận version được tăng khi update và xung đột khi cập nhật bằng version cũ.

Entity minh họa:

~~~java
@Table("inventory")
public record InventoryItem(
    @Id Long id,
    String sku,
    Integer quantity,
    @Version Long version
) {}
~~~

Test có thể:

1. Insert entity và đọc version ban đầu.
2. Cập nhật entity với version hiện tại.
3. Xác nhận version tăng.
4. Thử cập nhật lại bằng object có version cũ.
5. Xác nhận Spring Data phát lỗi optimistic locking phù hợp.

Tên exception và chi tiết hành vi phụ thuộc Spring Data R2DBC version. Hãy xác nhận bằng test trên database thực tế và không chỉ kiểm tra field version trong object giả lập.

## 17. Kiểm thử custom converters và kiểu dữ liệu

Các kiểu như JSON, enum, UUID, Instant, OffsetDateTime hoặc value object có thể phụ thuộc driver và custom converter.

Test nên bao gồm round trip:

~~~text
Java value
   |
Write converter
   |
Database column
   |
Read converter
   |
Java value
~~~

Ví dụ với enum:

~~~java
public enum PersonStatus {
    ACTIVE,
    SUSPENDED
}
~~~

Kiểm tra:

- Giá trị enum được ghi theo đúng representation (name, code hoặc native enum).
- Giá trị đọc được chuyển về đúng enum.
- Giá trị legacy hoặc không còn trong enum được xử lý có chủ đích.
- Casing và null semantics nhất quán.

Với JSON column, test bằng database hỗ trợ JSON type nếu production dựa vào operator/index JSON. Một chuỗi JSON lưu trong VARCHAR ở H2 không chứng minh PostgreSQL JSONB mapping hoạt động.

## 18. @DataR2dbcTest hay @SpringBootTest?

Chọn annotation theo phạm vi cần kiểm tra:

| Nhu cầu | Annotation phù hợp |
| --- | --- |
| Repository, mapping, custom SQL | @DataR2dbcTest |
| R2dbcEntityTemplate/DatabaseClient | @DataR2dbcTest |
| Custom converter trong persistence slice | @DataR2dbcTest + @Import |
| Service phối hợp nhiều repository | @SpringBootTest hoặc test service với collaborator phù hợp |
| Controller WebFlux và HTTP serialization | @WebFluxTest |
| Toàn bộ application wiring, migration và R2DBC | @SpringBootTest |
| End-to-end với database thật | @SpringBootTest + Testcontainers |

@DataR2dbcTest giúp test nhanh, phạm vi hẹp và ít phụ thuộc. Nhưng nếu test cần kiểm tra auto-configuration của toàn ứng dụng, Flyway/Liquibase, security hoặc HTTP routing, slice test không đủ.

Không dùng @SpringBootTest cho mọi repository test nếu không cần toàn bộ context; thời gian khởi động và độ phức tạp sẽ tăng.

## 19. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy repository bean | Repository scan không được kích hoạt hoặc package nằm ngoài cấu hình. | Kiểm tra package và slice configuration. |
| Không có ConnectionFactory | Thiếu R2DBC driver hoặc URL/credentials sai. | Kiểm tra dependency và spring.r2dbc.*. |
| Test dùng nhầm embedded DB | Test database replacement đang bật. | Dùng Replace.NONE khi cần database đã cấu hình. |
| Bảng không tồn tại | Schema script/migration không chạy hoặc sai schema. | Cấu hình SQL init/migration và kiểm tra schema. |
| Query chạy trên H2 nhưng lỗi production | Khác dialect hoặc kiểu dữ liệu. | Bổ sung Testcontainers cho database production. |
| StepVerifier không phát dữ liệu | Dữ liệu chưa được insert hoặc query filter sai. | Nối save bằng then/flatMap và kiểm tra bind values. |
| Test phụ thuộc thứ tự | Dữ liệu dùng chung hoặc không có ORDER BY. | Dùng dữ liệu unique và sort rõ. |
| Test bị treo | Publisher không complete, timeout hoặc blocking trong reactive flow. | Kiểm tra query, subscription và dùng verify(Duration). |
| Constraint test nhận exception khác dự kiến | Driver/translator khác nhau. | Kiểm tra cause chain, SQLSTATE và vendor behavior. |
| Custom converter không chạy | Converter configuration không được import vào slice. | Dùng @Import hoặc test configuration. |
| Cleanup không hoàn tất | Subscribe rời rạc hoặc không đợi publisher. | Dùng StepVerifier trong lifecycle test. |
| Transaction test không rollback | Reactive context không được chia sẻ hoặc test transaction support khác version. | Dùng TransactionalOperator và xác minh sau completion. |

### Đặt timeout cho test reactive

Có thể đặt timeout ở verify:

~~~java
StepVerifier.create(repository.findAll())
    .expectNextCount(3)
    .verifyComplete(Duration.ofSeconds(5));
~~~

Timeout giúp test fail thay vì treo vô hạn. Không đặt timeout quá thấp khiến CI chậm hoặc database container khởi động chưa xong bị hiểu nhầm là lỗi query.

## 20. Thực hành tốt khi xây dựng repository test suite

- Dùng @DataR2dbcTest cho test tập trung vào persistence.
- Dùng repository thật thay vì mock khi cần xác nhận SQL và mapping.
- Dùng StepVerifier để kiểm tra tín hiệu Mono/Flux.
- Tạo schema rõ ràng và quản lý schema test nhất quán.
- Dùng embedded database cho query portable, Testcontainers cho hành vi vendor-specific.
- Dùng dữ liệu duy nhất để test có thể chạy lặp lại và song song.
- Không dựa vào thứ tự kết quả nếu query không ORDER BY.
- Import custom converter/configuration cần thiết thay vì khởi tạo toàn bộ app.
- Kiểm tra constraint, generated ID, version, pagination và kiểu dữ liệu.
- Không tự subscribe trong test setup/cleanup rồi kết thúc test trước publisher.
- Phân biệt repository slice với service, web và end-to-end test.
- Ghi nhận database vendor, driver và version trong CI để dễ tái hiện lỗi.

## 21. Quy trình viết một @DataR2dbcTest

Khi thêm test cho repository mới, có thể đi theo thứ tự:

1. **Xác định phạm vi:** test repository/query/mapping hay cần cả service/web?
2. **Chọn database:** embedded cho hành vi portable; Testcontainers cho database production.
3. **Khai báo slice:** dùng @DataR2dbcTest và cấu hình replacement nếu cần database thật.
4. **Chuẩn bị schema:** schema.sql, migration hoặc setup script phù hợp.
5. **Inject repository:** dùng bean Spring thật.
6. **Tạo dữ liệu test:** dùng ID/code/email riêng cho từng test.
7. **Subscribe và assert:** dùng StepVerifier cho Mono/Flux.
8. **Kiểm tra biên:** empty result, duplicate, null, generated ID và mapping.
9. **Quản lý transaction/cleanup:** xác nhận reactive context và chờ cleanup hoàn tất.
10. **Chạy trên CI:** đảm bảo Docker hoặc database test sẵn sàng nếu dùng Testcontainers.

@DataR2dbcTest giúp kiểm tra repository trong một Spring context nhỏ, tập trung vào persistence reactive. Kết hợp repository thật, schema được quản lý rõ, StepVerifier và database phù hợp sẽ phát hiện lỗi SQL, mapping, constraint và driver mà mock không thể chỉ ra. Dùng Testcontainers khi cần xác nhận hành vi của database production, đồng thời giữ test độc lập bằng dữ liệu riêng và quản lý subscription/cleanup đúng theo reactive lifecycle.

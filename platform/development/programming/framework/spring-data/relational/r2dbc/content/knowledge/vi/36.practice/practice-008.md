# Viết kiểm thử tích hợp bằng Testcontainers và StepVerifier

Kiểm thử repository R2DBC chỉ có ý nghĩa khi xác nhận được hành vi với database và driver thật. Mock repository có thể kiểm tra cách service gọi collaborator, nhưng không thể phát hiện SQL sai dialect, mapping UUID/JSON/timestamp không đúng, constraint không khớp schema hoặc transaction không rollback như mong đợi.

Testcontainers giúp khởi chạy database thật trong container cho thời gian kiểm thử. Spring Boot kết nối tới container bằng cấu hình động, còn StepVerifier điều khiển subscription và kiểm tra các tín hiệu reactive như onNext, onComplete và onError. Kết hợp hai công cụ này, test có thể xác nhận toàn bộ đường đi từ repository/service qua R2DBC driver tới database.

Bài học này dùng PostgreSQL làm ví dụ. Các nguyên tắc áp dụng tương tự cho database khác nếu có image và R2DBC driver tương ứng. Nội dung tập trung vào cấu hình container, Spring test context, schema/migration, kiểm tra Mono/Flux, transaction reactive, fixture và cleanup, concurrency, kiểm soát thời gian chạy và CI.

## 1. Vì sao cần integration test với database thật?

Unit test có thể xác nhận mapper hoặc logic domain thuần Java. Repository integration test cần xác nhận những thành phần mà mock không mô phỏng được:

- SQL do Spring Data tạo ra có chạy được trên database mục tiêu không?
- Tên bảng, cột, schema và kiểu dữ liệu có khớp entity mapping không?
- R2DBC driver có chuyển UUID, BigDecimal, enum, JSON và timestamp đúng không?
- Generated ID có được trả về đúng không?
- UNIQUE, FOREIGN KEY, NOT NULL và CHECK có thực thi như dự kiến không?
- Derived query, @Query, Criteria và DatabaseClient có hoạt động với dialect thật không?
- Transaction có commit/rollback qua reactive context không?
- Optimistic locking có phát hiện cập nhật đồng thời không?

Một test dùng H2 có thể hữu ích cho query portable, nhưng không chứng minh PostgreSQL JSONB, enum, array, sequence hoặc cú pháp đặc thù PostgreSQL hoạt động đúng. Nếu production dùng PostgreSQL, ít nhất một nhóm integration test quan trọng nên dùng PostgreSQL thật.

### Vai trò của từng công cụ

| Công cụ | Trách nhiệm |
| --- | --- |
| Testcontainers | Tạo và quản lý vòng đời database container. |
| JUnit 5 | Quản lý test lifecycle và assertions. |
| Spring Boot test | Tạo application context hoặc test slice. |
| R2DBC driver | Kết nối ứng dụng tới database theo reactive SPI. |
| StepVerifier | Subscribe và kiểm tra tín hiệu Mono/Flux. |
| Flyway/Liquibase hoặc schema.sql | Chuẩn bị schema kiểm thử. |

Testcontainers không thay thế Spring Data R2DBC và StepVerifier cũng không tự tạo database. Mỗi thành phần xử lý một phần riêng của integration test.

## 2. Dependency cần thiết

Ví dụ dependency Gradle cho Spring Boot, Reactor Test và Testcontainers:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")

    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
}
~~~

Spring Boot starter test cung cấp JUnit Jupiter, AssertJ và các thư viện kiểm thử Spring phổ biến. Reactor Test cung cấp StepVerifier. Testcontainers có module JUnit Jupiter và module PostgreSQL.

Nên quản lý version Testcontainers qua BOM hoặc dependency management của dự án thay vì khai báo version rời rạc cho từng module. Cần bảo đảm version tương thích với Java, Spring Boot và Gradle đang dùng.

Nếu test chạy Flyway qua JDBC, bổ sung Flyway và PostgreSQL JDBC driver cho test runtime. R2DBC driver và JDBC driver là hai dependency khác nhau:

- R2DBC driver phục vụ repository và DatabaseClient.
- JDBC driver phục vụ Flyway/Liquibase khi công cụ migration dùng JDBC.

Không thêm JDBC chỉ để Spring Data R2DBC có thể kết nối database.

## 3. Khởi chạy PostgreSQL bằng Testcontainers

Testcontainers cung cấp PostgreSQLContainer để khởi chạy PostgreSQL trong Docker:

~~~java
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class DatabaseContainerTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @Test
    void containerIsRunning() {
        assertTrue(POSTGRES.isRunning());
    }
}
~~~

Testcontainers sẽ pull image nếu máy chưa có, tạo container, đợi database sẵn sàng rồi mới chạy test. Khi class kết thúc, JUnit extension dừng và xóa container theo lifecycle đã cấu hình.

Dùng image tag cụ thể thay vì tag trôi như latest để test có thể tái lập. Chọn phiên bản PostgreSQL gần với production, nhất là khi ứng dụng phụ thuộc vào kiểu dữ liệu hoặc tính năng vendor-specific.

### Docker là điều kiện chạy test

Testcontainers cần Docker daemon hoặc runtime tương thích. Nếu Docker không chạy, container không thể khởi động. Đây là lỗi môi trường test, không phải lỗi repository.

Trên CI, runner cần được cấp Docker socket hoặc môi trường container phù hợp. Không nên bỏ qua integration test một cách âm thầm rồi báo build thành công như thể chúng đã chạy.

## 4. Cấu hình R2DBC bằng DynamicPropertySource

Host port của container thường được ánh xạ động. Không giả định PostgreSQL luôn chạy ở localhost:5432. Dùng @DynamicPropertySource để đăng ký cấu hình sau khi container cung cấp endpoint.

~~~java
@DataR2dbcTest
@Testcontainers
@AutoConfigureTestDatabase(
    replace = AutoConfigureTestDatabase.Replace.NONE
)
class PersonRepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void configureR2dbc(DynamicPropertyRegistry registry) {
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
}
~~~

Các điểm quan trọng:

- URL dùng scheme r2dbc:postgresql, không phải jdbc:postgresql.
- Host lấy từ POSTGRES.getHost().
- Port lấy từ getMappedPort(5432), không hard-code 5432.
- Database, username và password lấy từ container.
- Replace.NONE ngăn test database replacement thay connection đã cấu hình bằng embedded database.

Annotation và package cụ thể cần khớp Spring Boot version của dự án. Trong một số version, test slice hoặc auto-configuration có thể khác; hãy dùng API từ dependency đang quản lý.

### Vì sao không dùng JDBC URL?

PostgreSQLContainer cung cấp getJdbcUrl(), nhưng Spring Data R2DBC cần R2DBC URL. Hai URL có thể trỏ tới cùng container, nhưng chúng thuộc hai SPI và driver khác nhau.

## 5. Dùng @DataR2dbcTest hay @SpringBootTest?

Chọn test context theo mục tiêu.

| Annotation | Phạm vi |
| --- | --- |
| @DataR2dbcTest | Repository, mapping, DatabaseClient, R2dbcEntityTemplate và persistence slice. |
| @SpringBootTest | Toàn bộ application context, service wiring, transaction config, migration và các bean ứng dụng. |
| @WebFluxTest | Controller, routing và HTTP serialization; thường mock service. |
| Unit test thuần | Mapper, domain rules và logic không cần Spring/database. |

### Repository slice

@DataR2dbcTest khởi tạo phần persistence cần thiết và thường nhanh hơn full application context. Dùng nó để kiểm tra derived query, custom @Query, converter, generated ID và constraint.

### Full application context

@SpringBootTest phù hợp khi cần kiểm tra service điều phối nhiều repository, cấu hình transaction manager, migration tự động hoặc bean wiring thật. Nếu chỉ kiểm tra một repository, khởi tạo toàn bộ ứng dụng có thể làm test chậm và khó chẩn đoán.

### Ví dụ @SpringBootTest

~~~java
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class OrderServiceIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
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
    OrderService orderService;
}
~~~

Ví dụ trên dùng cùng một container nhưng khởi tạo full application context. Nếu ứng dụng có Flyway, cần cấu hình JDBC URL riêng như phần migration bên dưới.

## 6. Chuẩn bị schema bằng migration

Cách đáng tin cậy cho integration test là dùng chính migration của ứng dụng. Như vậy test xác nhận migration có thể tạo schema và code hiện tại làm việc với schema đó.

Nếu dùng Flyway qua JDBC, có thể cấu hình thêm JDBC URL từ cùng container:

~~~java
@DynamicPropertySource
static void configureDatabase(DynamicPropertyRegistry registry) {
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

    registry.add("spring.flyway.url", POSTGRES::getJdbcUrl);
    registry.add("spring.flyway.user", POSTGRES::getUsername);
    registry.add("spring.flyway.password", POSTGRES::getPassword);
}
~~~

Trong test runtime cần có Flyway và PostgreSQL JDBC driver. Spring Boot có thể chạy Flyway khi tạo application context, trước khi repository được sử dụng. Cách auto-configuration cụ thể phụ thuộc phiên bản Spring Boot và cấu hình datasource.

Nếu dùng Liquibase, cấu hình JDBC URL và credentials theo namespace Liquibase tương ứng.

### Vì sao dùng cùng container?

Flyway tạo schema qua JDBC, sau đó repository truy cập schema đó qua R2DBC. Hai kết nối phải trỏ tới cùng server, database và schema. Nếu migration chạy vào database A nhưng R2DBC kết nối database B, test sẽ báo thiếu bảng dù migration log ghi thành công.

### Không sửa migration chỉ để test pass

Integration test nên dùng migration thực tế. Nếu migration lỗi trên database sạch, sửa migration hoặc cấu hình migration đúng quy trình. Không tạo schema test khác biệt với production rồi coi kết quả là xác nhận migration.

## 7. Chuẩn bị schema bằng schema.sql khi không dùng migration

Với test nhỏ hoặc module chưa có migration, có thể đặt schema.sql trong src/test/resources:

~~~sql
CREATE TABLE people (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    first_name VARCHAR(120) NOT NULL,
    email VARCHAR(254) NOT NULL UNIQUE
);
~~~

Cấu hình SQL initialization:

~~~yaml
spring:
  sql:
    init:
      mode: always
      schema-locations: classpath:schema.sql
~~~

Với database container, cấu hình mode rõ ràng để Spring chạy script nếu cần. Việc SQL initialization có được kích hoạt trong test slice hay không còn phụ thuộc Spring Boot version và auto-configuration đang bật.

schema.sql phù hợp khi cần fixture schema nhỏ và ổn định. Nếu ứng dụng đã có Flyway/Liquibase, ưu tiên chạy migration thật để tránh drift giữa test schema và production schema.

## 8. Viết repository integration test đầu tiên

Giả sử có entity Person:

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

    Mono<Person> findByEmail(String email);

    Flux<Person> findByFirstName(String firstName);
}
~~~

Test lưu rồi đọc lại:

~~~java
@Test
void savesAndReadsPerson() {
    String email = UUID.randomUUID() + "@example.test";
    Person input = new Person(null, "Ada Lovelace", email);

    StepVerifier.create(
        repository.save(input)
            .flatMap(saved -> repository.findById(saved.id()))
    )
    .assertNext(found -> {
        assertNotNull(found.id());
        assertEquals("Ada Lovelace", found.firstName());
        assertEquals(email, found.email());
    })
    .verifyComplete();
}
~~~

Test này xác nhận một đường đi thực tế:

1. Spring Data mapping entity thành row.
2. R2DBC driver gửi INSERT tới PostgreSQL.
3. Database sinh ID.
4. Repository phát entity đã lưu.
5. findById thực hiện SELECT bằng ID.
6. Driver map row về entity.
7. StepVerifier kiểm tra dữ liệu và completion.

Không mock repository trong test này. Mục tiêu là kiểm tra database, mapping và driver thực sự phối hợp.

## 9. StepVerifier kiểm tra tín hiệu Mono

Mono có thể phát tối đa một phần tử, hoàn tất rỗng hoặc phát lỗi.

### Kỳ vọng có một phần tử

~~~java
StepVerifier.create(repository.findByEmail(email))
    .assertNext(person -> assertEquals(email, person.email()))
    .verifyComplete();
~~~

Nếu Mono rỗng, assertNext không được gọi và verifyComplete sẽ làm test thất bại vì test đang kỳ vọng một phần tử.

### Kỳ vọng rỗng

~~~java
StepVerifier.create(repository.findByEmail("missing@example.test"))
    .verifyComplete();
~~~

Đây là hành vi thường gặp của findById/findByEmail khi không có bản ghi. Mono.empty không phải exception.

### Kỳ vọng lỗi

~~~java
StepVerifier.create(service.createOrder(invalidCommand))
    .expectError(InvalidOrderException.class)
    .verify();
~~~

Dùng expectErrorMatches khi cần kiểm tra thêm error code hoặc cause. Không phụ thuộc quá mức vào message của driver vì message có thể thay đổi theo version.

### Kiểm tra giá trị rồi completion

~~~java
StepVerifier.create(repository.count())
    .expectNext(3L)
    .verifyComplete();
~~~

StepVerifier xác nhận cả phần tử và tín hiệu hoàn tất. Nếu publisher phát thêm giá trị hoặc lỗi sau đó, verifyComplete sẽ phát hiện.

## 10. StepVerifier kiểm tra Flux

Flux có thể phát nhiều phần tử. Test nên kiểm tra số lượng, nội dung và thứ tự chỉ khi thứ tự là một phần của query contract.

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

Test trên giả định có đúng hai hàng và query có thứ tự ổn định. Nếu không có ORDER BY, database không bảo đảm thứ tự trả về.

### Kiểm tra danh sách sau khi thu thập

~~~java
StepVerifier.create(repository.findByFirstName("Ada").collectList())
    .assertNext(people -> {
        assertEquals(2, people.size());
        assertTrue(people.stream()
            .allMatch(person -> person.firstName().equals("Ada")));
    })
    .verifyComplete();
~~~

collectList phù hợp khi tập kết quả test nhỏ và cần kiểm tra cả collection. Không dùng cách này cho stream production rất lớn nếu không có giới hạn memory.

### Kiểm tra thứ tự tường minh

Nếu repository method có ORDER BY:

~~~java
StepVerifier.create(repository.findByFirstNameOrderByEmailAsc("Ada"))
    .expectNextMatches(person -> person.email().startsWith("a-"))
    .expectNextMatches(person -> person.email().startsWith("b-"))
    .verifyComplete();
~~~

Dùng dữ liệu test có giá trị sort phân biệt để assertion rõ ràng.

## 11. Kiểm tra derived query và custom SQL

Integration test nên kiểm tra query chạy được trên đúng database vendor.

Derived query:

~~~java
Flux<Person> findByFirstNameOrderByEmailAsc(String firstName);
~~~

Custom query:

~~~java
@Query("""
    SELECT id, first_name, email
    FROM people
    WHERE LOWER(first_name) = LOWER(:name)
    ORDER BY id
    """)
Flux<Person> searchByNameIgnoreCase(String name);
~~~

Test nên xác nhận:

- Bind parameter được truyền đúng.
- Tên cột và alias khớp mapping.
- Function/operator được database hỗ trợ.
- Kết quả map đúng kiểu Java.
- Query rỗng và query có nhiều kết quả có semantics đúng.
- Sort có thứ tự xác định.

Với query PostgreSQL-specific như JSONB operator, array hoặc RETURNING, chạy test trên PostgreSQL container thay vì chỉ H2.

## 12. Kiểm tra constraint và lỗi database

Testcontainers cho phép xác nhận constraint thật của database.

Giả sử email có UNIQUE constraint. Test duplicate:

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

Test này xác nhận lần ghi thứ hai phát lỗi. Nếu cần assert exception cụ thể, hãy kiểm tra loại exception và SQLSTATE do Spring exception translation cùng driver version đang dùng trả về.

Các constraint nên có integration test tương ứng:

- UNIQUE: không cho trùng business key.
- NOT NULL: từ chối dữ liệu thiếu.
- FOREIGN KEY: ngăn tham chiếu không tồn tại.
- CHECK: giới hạn quantity, price hoặc trạng thái.
- PRIMARY KEY: bảo đảm identity.

Không giả định mọi database vendor trả cùng exception class hoặc message cho cùng constraint.

## 13. Kiểm tra generated ID và database defaults

Nếu ID do database sinh, test phải xác nhận entity trả về có ID hợp lệ:

~~~java
StepVerifier.create(repository.save(new Person(null, "Grace", email)))
    .assertNext(saved -> assertNotNull(saved.id()))
    .verifyComplete();
~~~

Nếu bảng có default timestamp hoặc trigger, đọc lại row để xác nhận database thực sự tạo giá trị đúng.

Không chỉ kiểm tra object input vì object đầu vào có thể vẫn giữ ID null hoặc timestamp null. Kiểm tra entity do save phát ra và/hoặc query readback theo semantics driver.

Generated values và RETURNING behavior phụ thuộc database/driver. Test bằng cùng hệ quản trị và version gần production.

## 14. Kiểm thử transaction rollback bằng TransactionalOperator

Reactive transaction gắn với Reactor Context và subscription. Không giả định transaction hoạt động như JDBC thread-bound transaction.

Có thể inject TransactionalOperator dùng cùng R2dbcTransactionManager với repository:

~~~java
@Test
void rollsBackWriteWhenPublisherFails() {
    String email = UUID.randomUUID() + "@example.test";
    Person person = new Person(null, "Rollback", email);

    Mono<Person> work = repository.save(person)
        .flatMap(saved ->
            Mono.<Person>error(new IllegalStateException("force rollback"))
        );

    StepVerifier.create(transactionalOperator.transactional(work))
        .expectError(IllegalStateException.class)
        .verify();

    StepVerifier.create(repository.findByEmail(email))
        .verifyComplete();
}
~~~

Test thực hiện một INSERT rồi phát lỗi trong cùng transaction. TransactionalOperator rollback; sau khi publisher kết thúc, query mới xác nhận bản ghi không tồn tại.

Điều kiện để test có ý nghĩa:

- TransactionalOperator dùng đúng ConnectionFactory của repository.
- Repository operation được subscribe bên trong publisher đã bọc transaction.
- Lỗi truyền ra ngoài transaction boundary để kích hoạt rollback.
- Database hỗ trợ transaction cho thao tác đang test.
- Query xác minh chạy sau khi transaction rollback hoàn tất.

### Không gọi subscribe bên trong transaction

Không viết:

~~~java
transactionalOperator.transactional(repository.save(person)).subscribe();
return Mono.empty();
~~~

Subscription tách rời có thể chạy ngoài lifecycle mà test đang kiểm soát. Hãy đưa publisher vào StepVerifier hoặc trả nó về caller.

### Thận trọng với @Transactional trên test method

Không mặc định annotation @Transactional trên test method có semantics giống JDBC test. Test-managed transaction support phụ thuộc Spring Test version và loại transaction manager. Với reactive flow, cách tường minh bằng TransactionalOperator giúp thấy rõ publisher nào nằm trong transaction.

## 15. Kiểm tra service use case có nhiều thao tác ghi

Integration test có thể kiểm tra service điều phối nhiều repository trong cùng transaction.

Ví dụ use case tạo order và order lines:

~~~java
@Test
void createsOrderAndLinesAtomically() {
    CreateOrderCommand command = sampleCommand();

    StepVerifier.create(orderService.create(command))
        .assertNext(order -> {
            assertNotNull(order.id());
            assertEquals(2, order.lines().size());
        })
        .verifyComplete();

    StepVerifier.create(orderRepository.findById(command.expectedId()))
        .expectNextCount(1)
        .verifyComplete();
}
~~~

Ví dụ minh họa cần điều chỉnh theo cách ID được sinh và response service thực tế. Test nên đọc lại bảng liên quan để xác nhận cả root và child đã được lưu.

Một test rollback khác có thể ép bước ghi payment thất bại sau khi order đã insert, rồi xác nhận cả order và payment đều không còn nếu chúng thuộc cùng transaction.

Không chỉ kiểm tra object trả về. Đọc lại database để xác nhận trạng thái commit.

## 16. Quản lý fixture và dữ liệu giữa các test

Test integration dùng chung container hoặc Spring context có thể nhìn thấy dữ liệu từ test trước. Nếu không cô lập, kết quả phụ thuộc thứ tự chạy và test có thể thất bại khi chạy song song.

Các nguyên tắc:

- Dùng UUID hoặc business key duy nhất cho từng test.
- Tạo fixture ngay trong test thay vì dựa vào dữ liệu test khác.
- Xóa dữ liệu theo khóa của test, không DELETE toàn bảng khi chạy song song.
- Xóa bảng con trước bảng cha nếu foreign key yêu cầu.
- Đợi publisher cleanup hoàn tất trước khi test kết thúc.
- Không dùng chung mutable fixture object giữa các test.
- Giữ thứ tự SELECT tường minh nếu assertion phụ thuộc thứ tự.

Ví dụ tạo email duy nhất:

~~~java
String email = "person-" + UUID.randomUUID() + "@example.test";
~~~

Cách này giảm va chạm khi test lặp lại hoặc chạy song song.

### Cleanup reactive

Có thể dùng DatabaseClient và StepVerifier trong @AfterEach:

~~~java
@AfterEach
void cleanUp() {
    StepVerifier.create(
        databaseClient.sql("DELETE FROM people")
            .fetch()
            .rowsUpdated()
    )
    .expectNextMatches(rows -> rows >= 0)
    .verifyComplete();
}
~~~

rowsUpdated phát số hàng bị ảnh hưởng; expectNextMatches kiểm tra giá trị đó. Không dùng expectNextCount để kiểm tra số hàng vì expectNextCount chỉ đếm số tín hiệu onNext.

Trong suite chạy song song, DELETE toàn bảng có thể xóa dữ liệu của test khác. Khi đó hãy xóa theo unique test key hoặc cấp schema/database riêng cho từng test worker.

### Cleanup theo foreign key

Nếu có bảng order_lines tham chiếu orders, xóa child trước root hoặc dùng truncate/cascade chỉ trong database test riêng. Không đưa lệnh cleanup phá hủy vào database dùng chung.

## 17. Vòng đời container và Spring context cache

Đây là điểm dễ gây lỗi khi dùng Testcontainers cùng Spring TestContext.

JUnit Testcontainers extension quản lý container được khai báo bằng @Container. Static container thường chạy trong phạm vi test class và dừng sau khi class kết thúc. Spring có thể cache application context giữa các test class. Nếu context được cache nhưng container đã dừng, test class sau có thể dùng ConnectionFactory trỏ tới container không còn tồn tại.

Có hai cách tổ chức phổ biến:

### Container theo class

~~~java
@Testcontainers
@SpringBootTest
class PersonRepositoryIT {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine");

    // DynamicPropertySource và tests
}
~~~

Cách này đơn giản khi một class sở hữu context riêng hoặc không tái sử dụng context sau khi container dừng. Nếu nhiều class dùng chung cached context, cần xem xét lifecycle.

### Singleton container dùng chung

Có thể tạo base class hoặc test support giữ container sống trong suốt test JVM:

~~~java
abstract class PostgresIntegrationTest {

    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("app_test")
            .withUsername("test_user")
            .withPassword("test_password");

    static {
        POSTGRES.start();
    }

    @DynamicPropertySource
    static void configureR2dbc(DynamicPropertyRegistry registry) {
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
}
~~~

Các test class kế thừa base class sẽ dùng cùng container. Container được khởi động tĩnh và Testcontainers cleanup strategy có thể dừng khi JVM kết thúc. Nếu chọn cách này, không đồng thời đánh dấu cùng container bằng @Container của JUnit extension.

### Chọn lifecycle theo suite

- Một class độc lập: static @Container thường dễ hiểu.
- Nhiều class dùng chung Spring context: singleton hoặc Spring-managed container giúp tránh context trỏ tới container đã dừng.
- Test chạy song song: cần kiểm soát dữ liệu và schema, không chỉ lifecycle container.
- CI chia nhiều process/fork: mỗi JVM có thể tạo container riêng; cân nhắc thời gian và tài nguyên.

Không để Spring context sống lâu hơn database mà nó kết nối tới.

## 18. Kiểm tra optimistic locking và concurrency

Database thật cần thiết để xác nhận hành vi khi hai thao tác cạnh tranh.

Với entity có @Version:

~~~java
@Table("inventory")
public record InventoryItem(
    @Id UUID id,
    String sku,
    Integer quantity,
    @Version Long version
) {}
~~~

Test có thể:

1. Insert inventory item.
2. Đọc entity với version hiện tại.
3. Cập nhật bằng version đó.
4. Thử lưu một bản sao cũ với version cũ.
5. Xác nhận thao tác stale phát lỗi optimistic locking.

Tên exception và chi tiết implementation phụ thuộc Spring Data version. Dùng test trên database mục tiêu để xác nhận.

### Hai update đồng thời

Có thể dùng Mono.when hoặc Flux.merge để kích hoạt hai thao tác cạnh tranh, nhưng cần thiết kế test sao cho kết quả không phụ thuộc scheduling ngẫu nhiên. Dùng barrier/latch hoặc service operation có điều phối rõ nếu cần tái hiện race condition.

Không khẳng định một thao tác cụ thể luôn thắng nếu database không bảo đảm thứ tự. Assertion nên tập trung vào invariant cuối cùng: không mất update ngoài chính sách, version tăng đúng và một thao tác stale bị từ chối.

## 19. Kiểm tra timeout và lỗi kết nối

Integration test có thể treo nếu query không hoàn tất hoặc container bị dừng. Đặt timeout cho StepVerifier:

~~~java
StepVerifier.create(repository.findAll())
    .expectNextCount(3)
    .expectComplete()
    .verify(Duration.ofSeconds(10));
~~~

Timeout cần đủ rộng cho CI và thời gian cold start container. Đặt quá thấp có thể tạo test flaky.

Nên phân biệt:

- Container không khởi động được.
- ConnectionFactory không kết nối.
- Query bị treo.
- Publisher phát lỗi SQL.
- Assertion thất bại do dữ liệu không đúng.

Các loại lỗi khác nhau cần chẩn đoán khác nhau. Log test nên giữ nguyên exception cause và SQLSTATE cần thiết, nhưng không in password hoặc URL chứa credentials.

## 20. Testcontainers và WebFlux end-to-end

Nếu cần kiểm tra HTTP endpoint cùng database thật, có thể dùng @SpringBootTest với webEnvironment RANDOM_PORT và WebTestClient:

~~~java
@Testcontainers
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ProductApiIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) {
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
    WebTestClient webTestClient;

    @Test
    void createsAndReadsProduct() {
        webTestClient.post()
            .uri("/api/products")
            .bodyValue(sampleRequest())
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.id").exists();
    }
}
~~~

WebTestClient kiểm tra HTTP boundary. StepVerifier phù hợp để kiểm tra publisher của service/repository trực tiếp. Không cần cố dùng StepVerifier cho mọi HTTP test; chọn công cụ theo boundary đang kiểm tra.

Nếu endpoint tạo dữ liệu rồi test đọc lại qua HTTP, đó là end-to-end integration test có phạm vi lớn hơn repository test. Giữ số lượng test loại này vừa phải vì chúng khởi động nhiều thành phần và chạy chậm hơn.

## 21. Kiểm thử custom converter và kiểu dữ liệu vendor-specific

Nếu entity có UUID, JSON, enum hoặc timestamp, test round trip trên database thật:

1. Tạo entity có giá trị đặc biệt.
2. Save qua repository.
3. Đọc lại bằng ID hoặc business key.
4. So sánh giá trị sau mapping.
5. Nếu cần, query trực tiếp cột để xác nhận representation.

Ví dụ với JSONB PostgreSQL, H2 không đủ để xác nhận operator và converter JSONB. Dùng PostgreSQL container để test cả lưu, đọc và query theo JSON field.

Với timestamp, kiểm tra Instant/OffsetDateTime và timezone semantics. Không chỉ so sánh chuỗi hiển thị vì driver có thể chuẩn hóa precision hoặc timezone theo database type.

Custom converters phải được import vào test slice nếu không được auto-configure:

~~~java
@DataR2dbcTest
@Import(ProductR2dbcConfiguration.class)
class ProductMappingIntegrationTest {
    // Tests
}
~~~

Test xác nhận converter thực sự được đăng ký trong mapping context, không chỉ gọi converter trực tiếp như unit test.

## 22. Chạy integration test trên CI

CI cần bảo đảm:

- Docker daemon hoặc runtime tương thích sẵn sàng.
- Runner có quyền pull image hoặc image đã được cache.
- Image tag được pin.
- Test timeout đủ cho cold start.
- Testcontainers cleanup không để lại container/rác tài nguyên.
- Database port được cấp động, không xung đột.
- Secrets không bị ghi vào log.
- Integration test được phân biệt rõ với unit test.
- Test song song không dùng chung dữ liệu không an toàn.

Có thể tách task integration test riêng trong Gradle nếu suite dài. Ví dụ cấu hình source set/task phụ thuộc cấu trúc build của dự án; không sao chép một task name tùy ý mà chưa xem build.gradle.

### Khi không có Docker

Có thể dùng profile để chạy unit test mà không cần Docker và chạy integration test ở job khác có Docker. Nếu dùng Testcontainers disabledWithoutDocker, phải theo dõi test bị skip rõ ràng. Build release nên có bước xác nhận integration suite đã chạy trên database mục tiêu.

Không thay test container bằng mock rồi coi coverage tương đương.

## 23. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Docker connection error | Docker daemon không chạy hoặc runner không có quyền. | Khởi động/cấp Docker runtime cho CI. |
| Connection refused | Container chưa sẵn sàng hoặc URL/port sai. | Dùng mapped port và readiness wait của Testcontainers. |
| Không tìm thấy bảng | Schema/migration chưa chạy hoặc sai database/schema. | Kiểm tra migration, SQL init và R2DBC URL. |
| Flyway chạy nhưng R2DBC báo thiếu bảng | JDBC và R2DBC trỏ khác database/schema. | Dùng endpoint của cùng container cho cả hai URL. |
| Test slice không có repository bean | Package scan hoặc cấu hình slice sai. | Kiểm tra package và repository configuration. |
| Dùng nhầm embedded database | Database replacement đang bật. | Cấu hình Replace.NONE khi cần container thật. |
| Test class sau không kết nối được | Spring context cache còn nhưng container theo class đã dừng. | Dùng lifecycle container dùng chung hoặc tách context. |
| Test thất bại ngẫu nhiên | Dữ liệu dùng chung hoặc thiếu ORDER BY. | Dùng fixture unique và sort xác định. |
| Rollback không hoạt động | Publisher không nằm trong reactive transaction context. | Dùng TransactionalOperator và subscribe qua StepVerifier. |
| Exception assertion sai | Driver/database trả exception khác dự kiến. | Kiểm tra cause, SQLSTATE và vendor behavior. |
| Test treo | Publisher không complete hoặc timeout thiếu. | Đặt verify(Duration) và kiểm tra connection/query. |
| Test song song xóa dữ liệu của nhau | Cleanup DELETE toàn bảng. | Cleanup theo key hoặc cô lập schema/database. |

## 24. Quy trình xây dựng integration test

Khi thêm integration test cho repository hoặc service R2DBC, thực hiện theo trình tự:

1. **Chọn phạm vi:** repository slice, full context hay HTTP end-to-end.
2. **Chọn database:** dùng cùng vendor/version gần production.
3. **Thêm dependency:** R2DBC driver, Reactor Test và Testcontainers modules.
4. **Khởi động container:** dùng image tag cố định và readiness check.
5. **Đăng ký property động:** cấu hình R2DBC URL, username/password bằng DynamicPropertySource.
6. **Chuẩn bị schema:** chạy migration thật hoặc schema script phù hợp.
7. **Tạo fixture độc lập:** dùng UUID/business key riêng cho mỗi test.
8. **Thực thi publisher:** dùng StepVerifier để kiểm tra onNext/onComplete/onError.
9. **Kiểm tra database:** readback dữ liệu, constraint, generated values và mapping.
10. **Kiểm tra transaction:** dùng TransactionalOperator cho rollback/reactive context.
11. **Quản lý lifecycle:** bảo đảm container không dừng trước Spring context đang dùng.
12. **Chạy CI:** xác nhận Docker, timeout, cleanup và test suite thực sự chạy.

Testcontainers cung cấp database thật có thể tái tạo; StepVerifier xác nhận đúng tín hiệu của publisher reactive. Khi cấu hình R2DBC tới endpoint động, chạy migration/schema giống ứng dụng và kiểm tra kết quả bằng repository thật, integration test có thể phát hiện lỗi dialect, mapping, constraint, transaction và concurrency mà mock không thấy. Giữ fixture độc lập, quản lý đúng vòng đời container/context và chạy suite trên CI có Docker để kết quả ổn định và đáng tin cậy.

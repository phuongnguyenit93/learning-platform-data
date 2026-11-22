# Phân biệt kiểm thử đơn vị với kiểm thử tích hợp truy cập dữ liệu

## 1. Hai loại kiểm thử trả lời hai câu hỏi khác nhau

Trong ứng dụng Spring Data Relational R2DBC, kiểm thử cần xác nhận cả logic nghiệp vụ lẫn cách ứng dụng giao tiếp với database. Hai mục tiêu này có liên quan nhưng không giống nhau:

- **Kiểm thử đơn vị (unit test)** xác nhận một phần logic nhỏ hoạt động đúng khi các dependency của nó được kiểm soát. Ví dụ, kiểm tra OrderService tính tổng tiền, từ chối đơn hàng không hợp lệ hoặc điều phối các lời gọi repository đúng thứ tự.
- **Kiểm thử tích hợp truy cập dữ liệu (data-access integration test)** xác nhận các thành phần persistence thực sự phối hợp được với nhau và với database. Ví dụ, kiểm tra repository tạo đúng SQL, entity được map đúng cột, converter hoạt động, constraint được thực thi và transaction rollback theo mong đợi.

Một unit test có thể dùng Mockito để giả lập repository. Test đó hữu ích cho service logic, nhưng không chứng minh câu SQL, mapping metadata hay R2DBC driver hoạt động đúng.

Một integration test cần đi qua đường truy cập dữ liệu thật: repository hoặc DatabaseClient, R2DBC ConnectionFactory, driver và database. Nó có thể phát hiện lỗi mà mock không thể nhìn thấy, nhưng thường chạy lâu hơn và cần quản lý dữ liệu test.

Không có loại nào thay thế loại kia. Một suite cân bằng dùng unit test để kiểm tra nhiều nhánh logic nhanh, và dùng integration test cho những hành vi phụ thuộc Spring Data, R2DBC driver hoặc hệ quản trị cơ sở dữ liệu.

## 2. Ranh giới kiểm thử trong một ứng dụng R2DBC

Có thể hình dung các lớp của ứng dụng:

~~~text
                 HTTP / Message entry point
                            |
                            v
                     Service / Use case
                    /                 \
                   v                   v
             Domain rules         Repository API
                                       |
                         +-------------+-------------+
                         |                           |
                         v                           v
                 Spring Data R2DBC             DatabaseClient
                 Repository / Template          SQL execution
                         |                           |
                         +-------------+-------------+
                                       |
                                       v
                              R2DBC ConnectionFactory
                                       |
                                       v
                                  R2DBC Driver
                                       |
                                       v
                                  Database
~~~

Unit test thường tập trung ở service/domain và thay thế repository bằng mock hoặc fake. Integration test truy cập dữ liệu đi qua repository/template/DatabaseClient và database thật.

| Thành phần cần xác nhận | Loại test phù hợp |
|---|---|
| Quy tắc tính toán thuần Java | Unit test |
| Validation và quyết định nghiệp vụ | Unit test |
| Service xử lý repository empty/error đúng cách | Unit test với mock publisher |
| Entity mapping và tên cột | Data-access integration test |
| Derived query hoặc query annotation | Data-access integration test |
| Criteria, Query và Update của template | Data-access integration test |
| SQL và bind parameter của DatabaseClient | Data-access integration test |
| Custom R2dbcConverter | Data-access integration test |
| Unique/foreign key/check constraint | Data-access integration test |
| Generated ID và version | Data-access integration test |
| Transaction rollback qua nhiều câu lệnh | Integration test với database |
| SQL dialect và hành vi driver production | Integration test trên đúng database |
| Query plan và hiệu năng | Performance test trên môi trường phù hợp |

Một test có khởi tạo Spring context chưa chắc là integration test truy cập dữ liệu. Nếu repository vẫn được mock và không có database, test đó vẫn chỉ xác nhận logic phối hợp giữa các bean. Ngược lại, một test không khởi động toàn bộ Spring Boot vẫn có thể là integration test nếu nó dùng R2DBC driver và database thật để thực thi câu lệnh.

## 3. Unit test là gì?

Unit test kiểm tra một đơn vị logic trong phạm vi hẹp. Đơn vị đó có thể là một class, một service method hoặc một hàm domain. Mục tiêu là kiểm tra hành vi của code đang sở hữu mà không phụ thuộc vào việc database, network hoặc hệ thống bên ngoài có sẵn hay không.

Ví dụ service:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> register(RegisterCustomer command) {
        if (command.email() == null || command.email().isBlank()) {
            return Mono.error(
                    new IllegalArgumentException("Email is required")
            );
        }

        Customer customer = new Customer(
                null,
                command.name().trim(),
                command.email().trim().toLowerCase(Locale.ROOT),
                "ACTIVE"
        );

        return repository.save(customer);
    }
}
~~~

Unit test có thể giả lập CustomerRepository để kiểm tra:

- Email rỗng bị từ chối.
- Tên được trim.
- Email được chuẩn hóa.
- Service gọi save với entity đúng.
- Kết quả từ repository được phát ra cho caller.
- Lỗi từ repository được truyền hoặc chuyển đổi theo hợp đồng.

Test không cần tạo H2 hoặc PostgreSQL vì mục tiêu là logic của CustomerService.

### 3.1. Unit test không kiểm tra repository thật

Khi repository được mock, lời gọi:

~~~java
when(repository.save(any(Customer.class)))
        .thenReturn(Mono.just(savedCustomer));
~~~

không chạy SQL. Mockito chỉ trả publisher mà test đã định nghĩa. Vì vậy test không thể phát hiện:

- Bảng hoặc cột bị khai báo sai.
- Query method tạo SQL không đúng.
- Database từ chối kiểu dữ liệu.
- Unique constraint không tồn tại.
- Converter không được đăng ký.
- R2DBC driver không hỗ trợ một kiểu Java.
- Transaction manager không tham gia thao tác.

Đây không phải nhược điểm của Mockito. Đó là ranh giới có chủ ý của unit test. Không nên kỳ vọng một mock chứng minh hành vi của database.

## 4. Viết unit test reactive với Mockito và StepVerifier

Trong code R2DBC, service thường trả về Mono hoặc Flux. Unit test nên tiêu thụ publisher và kiểm tra tín hiệu bằng Reactor Test, thường là StepVerifier.

Ví dụ:

~~~java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {

    @Mock
    CustomerRepository repository;

    @InjectMocks
    CustomerService service;

    @Test
    void shouldNormalizeEmailBeforeSaving() {
        RegisterCustomer command = new RegisterCustomer(
                "An Nguyen",
                "  AN@EXAMPLE.TEST "
        );

        Customer saved = new Customer(
                10L,
                "An Nguyen",
                "an@example.test",
                "ACTIVE"
        );

        when(repository.save(any(Customer.class)))
                .thenReturn(Mono.just(saved));

        StepVerifier.create(service.register(command))
                .expectNext(saved)
                .verifyComplete();

        ArgumentCaptor<Customer> captor =
                ArgumentCaptor.forClass(Customer.class);

        verify(repository).save(captor.capture());

        assertThat(captor.getValue().email())
                .isEqualTo("an@example.test");
        assertThat(captor.getValue().name())
                .isEqualTo("An Nguyen");
    }
}
~~~

Test này kiểm tra hành vi service và entity được truyền đến repository. Nó không kiểm tra cách entity được lưu xuống database.

Một số lưu ý:

- Cần subscribe publisher trong test, ví dụ bằng StepVerifier, để pipeline reactive được thực thi.
- Dùng ArgumentCaptor để kiểm tra dữ liệu được truyền đến dependency.
- Không cần gọi subscribe() riêng rồi kiểm tra assertion ngay sau đó.
- Tránh block() tùy tiện trong code production. Trong test, StepVerifier giúp giữ việc kiểm tra reactive rõ ràng và có timeout.
- Nếu service có nhiều publisher phụ thuộc nhau, kiểm tra thứ tự và tín hiệu bằng operator/publisher phù hợp.

### 4.1. Kiểm tra validation mà không gọi repository

~~~java
@Test
void shouldRejectBlankEmail() {
    RegisterCustomer command = new RegisterCustomer(
            "An Nguyen",
            " "
    );

    StepVerifier.create(service.register(command))
            .expectErrorMatches(error ->
                    error instanceof IllegalArgumentException
                    && error.getMessage().equals("Email is required"))
            .verify();

    verifyNoInteractions(repository);
}
~~~

Đây là unit test tốt vì nó xác nhận service từ chối request trước khi truy cập persistence.

### 4.2. Kiểm tra repository trả empty

~~~java
@Test
void shouldPreserveEmptyResult() {
    when(repository.findById(99L)).thenReturn(Mono.empty());

    StepVerifier.create(service.findById(99L))
            .verifyComplete();
}
~~~

Nếu service chuyển empty thành lỗi nghiệp vụ, hãy kiểm tra đúng exception đó. Mock publisher cho phép tạo nhanh các nhánh success, empty và error vốn khó tái hiện có kiểm soát bằng database.

### 4.3. Kiểm tra lỗi từ repository

~~~java
@Test
void shouldPropagateRepositoryFailure() {
    RuntimeException databaseFailure =
            new RuntimeException("database unavailable");

    when(repository.findById(10L))
            .thenReturn(Mono.error(databaseFailure));

    StepVerifier.create(service.findById(10L))
            .expectErrorMatches(error -> error == databaseFailure)
            .verify();
}
~~~

Nếu service có trách nhiệm chuyển lỗi kỹ thuật thành lỗi nghiệp vụ, unit test nên xác nhận mapping đó. Việc kiểm tra SQLState hoặc vendor error code thật thuộc integration test trên driver/database tương ứng.

## 5. Fake, stub và mock trong unit test

Các test double có thể thay thế dependency nhưng có mục đích khác nhau:

- **Stub:** trả dữ liệu đã định nghĩa trước để kiểm tra nhánh logic.
- **Mock:** vừa trả kết quả vừa cho phép xác minh lời gọi, tham số hoặc thứ tự tương tác.
- **Fake:** một implementation đơn giản có hành vi thực tế nhưng không dùng database production, ví dụ repository lưu trong Map.

Ví dụ fake repository:

~~~java
class InMemoryCustomerRepository
        implements CustomerRepository {

    private final Map<Long, Customer> customers = new HashMap<>();
    private final AtomicLong ids = new AtomicLong();

    // Các method cần thiết được triển khai bằng dữ liệu trong bộ nhớ.
}
~~~

Fake có thể hữu ích khi nhiều unit test cần một hành vi repository nhất quán. Tuy nhiên, fake phải tuân theo hợp đồng mà service sử dụng. Một fake đơn giản có thể không tái hiện constraint, concurrency hoặc semantics SQL.

Không nên xây một database giả quá phức tạp trong unit test. Nếu cần kiểm tra mapping, constraint hoặc query, hãy dùng integration test với database.

## 6. Khi nào không nên mock repository?

Không cần mock repository trong mọi test chỉ vì ứng dụng đang dùng R2DBC.

Nếu mục tiêu là kiểm tra repository method, query, mapping hoặc transaction, mock repository sẽ bỏ qua chính thành phần cần xác nhận.

Ví dụ test này không có giá trị để chứng minh query method đúng:

~~~java
when(repository.findByStatus("ACTIVE"))
        .thenReturn(Flux.just(customer));

StepVerifier.create(repository.findByStatus("ACTIVE"))
        .expectNext(customer)
        .verifyComplete();
~~~

Nó chỉ xác nhận mock trả đúng giá trị do test thiết lập. Không có SQL nào được thực thi.

Đối với repository test, hãy inject repository thật được Spring Data tạo và dùng database. Mock chỉ phù hợp khi repository là dependency của đơn vị logic đang kiểm thử.

## 7. Data-access integration test là gì?

Data-access integration test xác nhận nhiều thành phần persistence hoạt động cùng nhau. Một test điển hình có thể bao gồm:

1. Spring tạo repository hoặc R2dbcEntityTemplate.
2. ConnectionFactory tạo kết nối qua R2DBC driver.
3. Driver gửi SQL đến database.
4. Database thực thi query và constraint.
5. Spring Data ánh xạ row thành entity hoặc DTO.
6. Test kiểm tra kết quả và trạng thái dữ liệu.

Ví dụ cần kiểm tra:

- @Table và @Column ánh xạ đúng.
- @Id nhận generated value.
- Derived query trả đúng hàng.
- @Query dùng bind parameter chính xác.
- Criteria và Sort tạo điều kiện phù hợp.
- Custom conversion hoạt động hai chiều.
- Unique constraint từ chối duplicate.
- Transaction rollback nhiều thao tác.
- Database-specific SQL chạy trên đúng engine.

Integration test thường chậm hơn unit test vì có startup, connection acquisition, SQL execution và cleanup. Nhưng nó là bằng chứng cần thiết cho những hành vi phụ thuộc persistence.

## 8. Kiểm thử repository với @DataR2dbcTest

Spring Boot cung cấp @DataR2dbcTest để tạo test slice tập trung vào các thành phần R2DBC. Test slice thường giới hạn ApplicationContext vào cấu hình liên quan repository/persistence, giúp khởi động nhanh hơn full application context.

Ví dụ:

~~~java
@DataR2dbcTest
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void shouldPersistAndReadCustomer() {
        Customer input = new Customer(
                null,
                "An Nguyen",
                "an@example.test",
                "ACTIVE"
        );

        StepVerifier.create(
                repository.save(input)
                        .flatMap(saved ->
                                repository.findById(saved.id())
                        )
        )
        .assertNext(found -> {
            assertThat(found.id()).isNotNull();
            assertThat(found.name()).isEqualTo("An Nguyen");
            assertThat(found.email()).isEqualTo("an@example.test");
        })
        .verifyComplete();
    }
}
~~~

Đây là integration test vì repository thật thực hiện thao tác qua R2DBC. Cấu hình test phải cung cấp ConnectionFactory và schema phù hợp. Tùy Spring Boot version và dependency trên classpath, test slice có thể chọn embedded database hoặc cần cấu hình rõ URL/bean.

Không nên mặc định @DataR2dbcTest tự tạo schema đúng theo mọi entity. Schema có thể đến từ script initializer, migration tool hoặc cấu hình test riêng.

### 8.1. Khi cần thêm bean vào test slice

Test slice không tải toàn bộ bean của ứng dụng. Nếu repository cần custom converter, callback hoặc cấu hình riêng, hãy import cấu hình cần thiết:

~~~java
@DataR2dbcTest
@Import(CustomerR2dbcConfiguration.class)
class CustomerRepositoryIntegrationTest {
    // Repository thật và các bean persistence cần thiết.
}
~~~

Chỉ import những thành phần cần kiểm tra. Nếu mục tiêu là xác nhận wiring toàn ứng dụng, migration hoặc service transaction boundary, có thể dùng @SpringBootTest.

### 8.2. Kiểm thử repository không cần khởi động HTTP server

Một test truy cập repository thường không cần WebServer. @DataR2dbcTest giúp tránh khởi tạo controller, security filter, scheduler và các bean không liên quan. Nhờ vậy, test tập trung vào persistence và phản hồi nhanh hơn full context.

Nếu cần kiểm tra cả controller, serialization, security và repository trong cùng request, đó là integration test ở phạm vi ứng dụng rộng hơn.

## 9. Kiểm thử SQL và mapping qua DatabaseClient

Khi dùng DatabaseClient, integration test nên gửi SQL thật và kiểm tra row mapping:

~~~java
@DataR2dbcTest
class CustomerQueryIntegrationTest {

    @Autowired
    DatabaseClient databaseClient;

    @Test
    void shouldMapSummaryFromSql() {
        Flux<CustomerSummary> result =
                databaseClient.sql("""
                        SELECT id, name, status
                        FROM customers
                        WHERE status = :status
                        ORDER BY id
                        """)
                    .bind("status", "ACTIVE")
                    .map((row, metadata) -> new CustomerSummary(
                            row.get("id", Long.class),
                            row.get("name", String.class),
                            row.get("status", String.class)
                    ))
                    .all();

        StepVerifier.create(result)
                .expectNextMatches(summary ->
                        summary.name().equals("An Nguyen"))
                .verifyComplete();
    }
}
~~~

Test này xác nhận database hiểu SQL, named parameter được bind, cột được trả về và callback map tạo DTO đúng.

Đối với raw SQL, hãy dùng schema test tương ứng và bind tất cả giá trị dữ liệu. Không nối input trực tiếp vào câu SQL. Nếu query phụ thuộc dialect production như PostgreSQL ON CONFLICT, JSONB hoặc RETURNING, phải chạy test trên PostgreSQL thay vì thay câu lệnh bằng một cú pháp khác rồi xem là đã xác nhận cùng hành vi.

## 10. Kiểm thử entity mapping và converter

Mapping là trách nhiệm của Spring Data R2DBC và driver, vì vậy cần test integration.

Ví dụ entity:

~~~java
@Table("customers")
public record Customer(
        @Id Long id,
        @Column("display_name") String name,
        @Column("email_address") String email,
        String status
) {}
~~~

Schema:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL,
    email_address VARCHAR(320) NOT NULL,
    status VARCHAR(30) NOT NULL
);
~~~

Integration test insert rồi đọc lại có thể phát hiện mapping sai giữa property và cột.

Với custom value object, cần kiểm tra cả writing converter và reading converter:

~~~java
public record EmailAddress(String value) {}
~~~

~~~java
@WritingConverter
class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}
~~~

~~~java
@ReadingConverter
class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Unit test có thể gọi converter trực tiếp để kiểm tra phép biến đổi. Nhưng integration test mới xác nhận Spring Data đã đăng ký và sử dụng converter trong pipeline đọc/ghi.

Nếu production dùng kiểu native như UUID, JSONB hoặc enum, hãy chạy test với đúng database và driver production vì H2 có thể biểu diễn kiểu đó khác.

## 11. Kiểm thử constraint và lỗi database

Một unit test với mock có thể mô phỏng repository phát DuplicateKeyException, nhưng không chứng minh database thực sự có unique constraint.

Integration test nên tạo hai bản ghi trùng business key:

~~~java
@Test
void shouldRejectDuplicateEmail() {
    Customer first = new Customer(
            null, "An", "an@example.test", "ACTIVE"
    );

    Customer duplicate = new Customer(
            null, "Another", "an@example.test", "ACTIVE"
    );

    StepVerifier.create(
            repository.save(first)
                    .then(repository.save(duplicate))
    )
    .expectError()
    .verify();
}
~~~

Test cần có unique constraint trong schema. Nếu test chỉ kiểm tra exception chung, nó xác nhận thao tác thất bại nhưng chưa chắc đã xác nhận đúng nguyên nhân. Có thể kiểm tra exception chain, SQLState hoặc constraint name khi ứng dụng phụ thuộc vào cách phân loại lỗi đó. Vendor error code nên được kiểm tra trên database production.

Các constraint nên được kiểm thử riêng:

- Primary key.
- Unique constraint.
- Not-null.
- Check constraint.
- Foreign key.
- Delete/update referential behavior.

Không giả định H2 và production database xử lý NULL, collation hoặc deferred constraint giống nhau.

## 12. Kiểm thử transaction và rollback

Unit test có thể xác nhận service nối các publisher đúng cách, nhưng không chứng minh database rollback nhiều câu lệnh trong một transaction.

Integration test cần dùng transaction manager thật và thực thi ít nhất hai thao tác database trong cùng boundary. Ví dụ:

~~~java
@Transactional
public Mono<Order> createOrderThenFail(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(savedOrder ->
                    orderLineRepository.saveAll(toLines(savedOrder.id(), command))
                            .then(Mono.error(
                                    new IllegalStateException("force rollback")
                            ))
            );
}
~~~

Test có thể xác nhận publisher phát lỗi, sau đó đọc lại dữ liệu bằng một thao tác nằm ngoài transaction đã kết thúc để bảo đảm cả Order và OrderLine đã rollback.

Cần chú ý:

- Service method phải được gọi qua Spring proxy nếu dựa vào annotation.
- Toàn bộ publisher cần được trả về và subscribe.
- Repository phải dùng cùng ConnectionFactory/transaction manager.
- Không gọi subscribe() riêng trong service.
- Không nuốt lỗi trước khi transaction interceptor nhìn thấy lỗi.
- Test không nên vô tình mở transaction bao ngoài làm che kết quả commit/rollback.

Với H2, test rollback cơ bản có thể hữu ích. Với isolation, lock, deadlock, cancellation hoặc concurrent update, cần kiểm thử trên engine production.

## 13. Unit test service và integration test repository bổ trợ nhau

Một ví dụ nghiệp vụ đặt hàng có thể được kiểm tra theo hai tầng.

**Unit test OrderService:**

- Giá trị đầu vào sai bị từ chối.
- Service tạo Order với trạng thái ban đầu đúng.
- Service gọi repository để lưu Order.
- ID của Order được dùng khi tạo OrderLine.
- Lỗi từ OrderLine repository được truyền đúng.
- Kết quả cuối được ánh xạ thành OrderResponse.

Repository được mock, vì vậy test chạy nhanh và có thể kiểm tra nhiều nhánh lỗi.

**Integration test OrderRepository/OrderLineRepository:**

- Entity mapping đúng.
- Generated ID được trả lại.
- Foreign key OrderLine trỏ tới Order hợp lệ.
- Constraint quantity được thực thi.
- Query tìm đơn hàng theo customer trả đúng dữ liệu.
- Transaction lưu Order và OrderLine rollback cùng nhau.

Không cần lặp lại mọi nhánh nghiệp vụ ở integration test. Integration test nên tập trung vào hợp đồng persistence và một số luồng end-to-end quan trọng.

## 14. H2 và Testcontainers: chọn database cho integration test

Integration test cần database, nhưng không phải test nào cũng cần cùng loại database.

### 14.1. H2 cho kiểm thử relational phổ thông

H2 có thể phù hợp để kiểm tra nhanh:

- CRUD cơ bản.
- Mapping entity.
- Repository derived query phổ thông.
- SQL portable.
- Constraint đơn giản.
- Một số transaction flow cơ bản.

Ưu điểm là khởi động nhanh và không cần database server. Tuy nhiên, H2 có dialect, kiểu dữ liệu, collation, transaction, locking và query planner riêng.

Một test H2 pass không chứng minh PostgreSQL hoặc MySQL sẽ có cùng hành vi.

### 14.2. Testcontainers cho database production

Nếu production dùng PostgreSQL, hãy dùng PostgreSQL container cho những test cần xác nhận:

- SQL dialect.
- JSONB, array, enum và native type.
- ON CONFLICT và RETURNING.
- Migration.
- Generated value và sequence.
- Locking, isolation và concurrency.
- Constraint/error code.
- Hành vi của R2DBC driver production.

Ví dụ:

~~~java
@Testcontainers
@DataR2dbcTest
class CustomerPostgresRepositoryTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
                "r2dbc:postgresql://" +
                postgres.getHost() + ":" +
                postgres.getFirstMappedPort() + "/" +
                postgres.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }
}
~~~

Đây là ví dụ cấu hình khái quát; cần dependency Testcontainers, R2DBC PostgreSQL driver và schema setup tương ứng. Nếu test cần Flyway, cấu hình thêm JDBC URL/user/password trỏ cùng container và bảo đảm migration chạy trước test.

### 14.3. Không dùng H2 để benchmark production

Query plan và hiệu năng của H2 không đại diện cho database production. Benchmark cần engine, version, schema, index, dữ liệu và cấu hình gần production. H2 chủ yếu giúp kiểm tra logic chức năng nhanh.

## 15. Kiểm thử migration là một trách nhiệm riêng

Test repository với schema.sql không xác nhận migration production chạy đúng. Có thể schema.sql đã được viết khác với migration, hoặc migration có cú pháp đặc thù.

Migration integration test nên:

1. Khởi động database rỗng.
2. Chạy Flyway hoặc Liquibase bằng JDBC nếu công cụ dùng JDBC.
3. Xác nhận migration history.
4. Truy cập schema vừa tạo qua R2DBC.
5. Chạy một số thao tác repository quan trọng.
6. Kiểm tra upgrade từ schema phiên bản trước nếu cần.

Với ứng dụng R2DBC, việc Flyway dùng JDBC không có nghĩa repository test đang dùng JDBC. Migration và runtime là hai đường kết nối riêng. Test nên xác nhận chúng trỏ cùng database/schema.

Khi test chỉ kiểm tra CRUD với schema.sql, ghi rõ đó là persistence test trên schema fixture, không phải migration test.

## 16. @DataR2dbcTest hay @SpringBootTest?

| Tiêu chí | @DataR2dbcTest | @SpringBootTest |
|---|---|---|
| Phạm vi | Slice persistence | Application context rộng hoặc toàn bộ |
| Repository thật | Có | Có nếu cấu hình ứng dụng |
| Database thật | Có thể cấu hình | Có thể cấu hình |
| Controller/security | Thường không tải | Có thể tải |
| Service và wiring toàn ứng dụng | Chỉ khi import | Có |
| Migration | Phụ thuộc auto-configuration/import/cấu hình | Phù hợp để kiểm tra startup và migration toàn ứng dụng |
| Thời gian khởi động | Thường nhanh hơn | Thường lâu hơn |
| Use case | Repository, mapping, converter, query | Luồng tích hợp nhiều bean và startup/migration |

Không nên dùng @SpringBootTest cho mọi repository test nếu một slice nhỏ đã đủ. Nhưng cũng không nên ép test toàn ứng dụng vào @DataR2dbcTest khi mục tiêu bao gồm controller, security, migration ordering hoặc nhiều cấu hình.

Chọn annotation theo phạm vi behavior cần xác nhận, không theo thói quen.

## 17. Kiểm thử reactive không đồng nghĩa phải mock mọi publisher

StepVerifier dùng được với cả publisher từ mock và publisher từ database thật.

Với unit test, publisher thường được stub:

~~~java
when(repository.findById(10L))
        .thenReturn(Mono.just(customer));
~~~

Với integration test, publisher đến từ repository thật:

~~~java
StepVerifier.create(repository.findById(10L))
        .expectNextMatches(customer ->
                customer.id().equals(10L))
        .verifyComplete();
~~~

StepVerifier xác nhận các tín hiệu Reactive Streams như:

- onNext và giá trị được phát.
- complete.
- error và loại lỗi.
- Thứ tự phần tử.
- Số lượng phần tử.
- Timeout hoặc cancellation trong test có điều phối phù hợp.

StepVerifier không quyết định test là unit hay integration. Điều đó phụ thuộc nguồn publisher và các thành phần thực sự được đưa vào test.

## 18. Kiểm thử cancellation, backpressure và concurrency

Đây là những hành vi quan trọng của reactive pipeline nhưng không phải mọi ứng dụng đều cần test ở mọi lớp.

**Unit test** có thể xác nhận service nối publisher và xử lý cancellation/error theo contract của code. Có thể dùng TestPublisher hoặc PublisherProbe để điều khiển nguồn và kiểm tra subscription.

**Integration test** cần database thật khi muốn xác nhận cancellation có giải phóng result stream/connection đúng cách hoặc concurrency có tạo behavior database mong muốn.

Ví dụ các tình huống cần test trên production database:

- Nhiều request cập nhật cùng một hàng.
- Optimistic locking với @Version.
- Pessimistic lock hoặc SELECT FOR UPDATE.
- Deadlock và retry transaction.
- Transaction isolation.
- Hủy subscription khi Flux đang đọc nhiều hàng.
- Pool saturation khi nhiều stream đồng thời.

Không suy luận locking của PostgreSQL từ H2. Cần nhiều connection/transaction thực sự và dữ liệu test được điều phối để tái hiện race condition.

## 19. Test isolation và quản lý dữ liệu

Integration test có thể làm thay đổi database dùng chung. Nếu không cô lập dữ liệu, test phụ thuộc thứ tự chạy hoặc chạy song song có thể thất bại ngẫu nhiên.

Một số chiến lược:

- Database/schema riêng cho mỗi test suite.
- Container riêng cho nhóm test cần isolation mạnh.
- Tạo dữ liệu với key duy nhất cho từng test.
- Xóa fixture sau test bằng publisher được tiêu thụ đầy đủ.
- Reset schema khi test cần trạng thái ban đầu hoàn toàn.
- Tránh chạy song song trên cùng schema nếu test có thao tác cleanup toàn bảng.

Ví dụ chuẩn bị dữ liệu ngay trong pipeline:

~~~java
Mono<Void> arrange = repository.deleteAll()
        .then(repository.save(
                new Customer(null, "An", "an@example.test", "ACTIVE")
        ))
        .then();

StepVerifier.create(
        arrange.thenMany(repository.findByStatus("ACTIVE"))
)
.expectNextMatches(customer ->
        customer.email().equals("an@example.test"))
.verifyComplete();
~~~

Đoạn ví dụ đơn giản hóa fixture; nếu có nhiều hàng, có thể dùng saveAll. Điều quan trọng là setup phải hoàn tất trước assertion.

Tránh gọi subscribe() trong setup rồi lập tức chạy assertion vì thao tác ghi có thể chưa hoàn tất. Trong test reactive, hãy nối setup và action vào một publisher duy nhất hoặc dùng cơ chế setup được framework chờ đúng cách.

### 19.1. Transaction test và cleanup

Không giả định mọi test slice R2DBC tự động rollback dữ liệu sau mỗi test. Hãy kiểm tra semantics của Spring Boot/Spring Test version và cách transaction được cấu hình. Nếu không có rollback tự động, chủ động dọn dữ liệu hoặc dùng database cô lập.

Với reactive transaction, context được truyền qua Reactor Context. Không giả định một transaction test imperative gắn ThreadLocal sẽ tự bao quanh publisher reactive. Nếu cần transaction boundary, cấu hình ReactiveTransactionManager và kiểm tra rõ cách test được thực thi.

### 19.2. Không dùng một database in-memory chung thiếu kiểm soát

Nếu nhiều test context cùng dùng một tên H2 in-memory, chúng có thể chia sẻ database tùy URL và vòng đời connection. Khi chạy parallel, test này có thể xóa dữ liệu của test khác.

Đặt tên database rõ theo suite/context, dùng container riêng hoặc kiểm soát parallel execution. Không dựa vào thứ tự test để dữ liệu còn sót.

## 20. Kiểm tra lỗi ở đúng tầng

Lỗi có thể xuất hiện ở service, mapping, driver hoặc database. Nên kiểm tra ở tầng có trách nhiệm:

| Lỗi | Kiểm tra ở đâu? |
|---|---|
| Email rỗng bị chấp nhận | Unit test service/domain |
| Service không chuyển empty thành NotFound | Unit test service |
| Service gọi save với sai entity | Unit test với captor |
| @Column ánh xạ sai tên cột | Integration test repository |
| Query annotation sai cú pháp | Integration test với database |
| Bind null sai kiểu | Integration test với driver |
| Unique constraint không hoạt động | Integration test database |
| Converter không được đăng ký | Integration test Spring Data mapping |
| R2DBC driver trả kiểu khác kỳ vọng | Integration test production driver |
| Transaction không rollback | Integration test với transaction manager |
| SQLState/vendor error code sai | Integration test đúng database |
| Query chậm hoặc không dùng index | Performance test trên production-like database |

Unit test có thể tạo một exception giả để kiểm tra service mapping, nhưng không nên khẳng định exception giả phản ánh chính xác vendor exception. Integration test xác nhận lỗi thực tế do database/driver phát ra.

## 21. Tránh những anti-pattern phổ biến

- **Mock repository rồi gọi đó là repository integration test:** không có SQL nào được thực thi.
- **Dùng H2 để xác nhận PostgreSQL-specific SQL:** dialect và semantics không tương đương hoàn toàn.
- **Chỉ có integration test và bỏ qua unit test:** nhiều nhánh logic nhỏ sẽ chạy chậm và khó chẩn đoán.
- **Chỉ có unit test và không test database:** mapping, query và constraint có thể sai mà suite vẫn xanh.
- **Gọi subscribe() trong service hoặc test setup:** tạo luồng thực thi tách khỏi publisher đang được kiểm tra.
- **Dùng block() trong code reactive production:** có thể chặn event-loop và làm mất composition.
- **Chia sẻ database giữa test song song mà không isolation:** gây lỗi phụ thuộc thứ tự.
- **Dựa vào schema.sql nhưng không test migration:** migration production có thể thất bại.
- **Assert quá sâu vào SQL sinh ra khi chỉ cần kiểm tra kết quả:** test dễ vỡ khi implementation thay đổi mà behavior không đổi.
- **Không test database production cho native query:** lỗi chỉ xuất hiện khi triển khai thật.
- **Chạy Testcontainers cho mọi unit test:** làm mất lợi ích tốc độ và phạm vi hẹp của unit test.
- **Kiểm tra hiệu năng bằng H2 in-memory:** kết quả không đại diện engine production.

## 22. Cách tổ chức test suite theo tầng

Một cấu trúc thực tế có thể là:

~~~text
src/test/
├── java/
│   └── com/example/
│       ├── unit/
│       │   ├── CustomerServiceTest.java
│       │   └── OrderServiceTest.java
│       ├── r2dbc/
│       │   ├── CustomerRepositoryTest.java
│       │   └── CustomerMappingTest.java
│       └── postgres/
│           ├── CustomerPostgresQueryTest.java
│           ├── OrderTransactionTest.java
│           └── FlywayMigrationTest.java
└── resources/
    └── db/
        └── test-data.sql
~~~

Tên package chỉ là gợi ý. Có thể tổ chức theo module hoặc domain thay vì theo loại test.

Một chiến lược chạy CI:

1. Chạy unit test thường xuyên trong quá trình phát triển.
2. Chạy H2 R2DBC test cho repository/mapping phổ thông nếu dự án dùng H2.
3. Chạy Testcontainers test cho dialect, migration, type và transaction production-specific.
4. Chạy nhóm concurrency/performance riêng khi cần.
5. Không bỏ qua nhóm test database production trong pipeline phát hành.

Nếu thời gian CI là vấn đề, có thể phân loại test bằng JUnit tags hoặc Gradle test task. Nhưng việc phân nhóm phải minh bạch; test quan trọng không được vô tình loại khỏi release gate.

## 23. Ví dụ chiến lược kiểm thử cho một use case

Giả sử use case tạo customer gồm chuẩn hóa email, lưu customer và ghi audit.

### Unit test CustomerService

Mock repository và audit service để xác nhận:

- Email được chuẩn hóa.
- Email không hợp lệ bị từ chối.
- Repository được gọi đúng một lần.
- Audit service chỉ được gọi khi lưu thành công.
- Lỗi lưu được truyền đúng.
- Kết quả trả về chứa ID từ repository.

### Repository integration test

Dùng R2DBC database thật để xác nhận:

- Customer được insert.
- ID được sinh và trả về.
- Email được lưu đúng cột.
- Unique constraint từ chối email trùng.
- Query tìm customer theo email hoạt động.
- Converter được sử dụng.

### Transaction integration test

Nếu customer và audit row phải atomic:

- Gọi service transactional thật.
- Làm bước audit thất bại có kiểm soát.
- Xác nhận customer không được commit nếu yêu cầu rollback toàn bộ.
- Xác nhận lỗi được phát ra đúng.
- Kiểm tra bằng một truy vấn sau khi transaction đã kết thúc.

### Production database test

Nếu dùng PostgreSQL-specific SQL hoặc JSONB:

- Khởi chạy PostgreSQL bằng Testcontainers.
- Chạy migration thật.
- Thực thi câu SQL native.
- Kiểm tra mapping và constraint trên PostgreSQL.

Một use case có thể cần nhiều test nhỏ ở các tầng khác nhau. Mỗi test nên có một mục tiêu rõ, tránh một test lớn vừa kiểm tra validation, HTTP, SQL, transaction, message và response khiến lỗi khó định vị.

## 24. Đo tốc độ và độ tin cậy của test suite

Một test suite tốt cần đủ nhanh để được chạy thường xuyên và đủ thực tế để phát hiện lỗi quan trọng.

Theo dõi:

- Thời gian unit test.
- Thời gian khởi động Spring context.
- Thời gian khởi động database/container.
- Số test flaky.
- Tỷ lệ test cần retry.
- Thời gian cleanup.
- Số test dùng chung database.
- Mức độ bao phủ query/mapping/transaction quan trọng.

Nếu nhiều test dùng chung một @SpringBootTest, Spring Test context cache có thể giúp giảm startup cost. Tuy nhiên, không nên dùng chung context làm lý do chia sẻ state database giữa test.

Tối ưu suite bằng cách đặt đúng ranh giới, tái sử dụng container/context có kiểm soát và chỉ khởi động thành phần cần thiết. Không loại bỏ integration test quan trọng chỉ để rút ngắn CI.

## 25. Checklist lựa chọn loại test

Trước khi viết test, hãy xác định:

1. Test đang kiểm tra logic thuộc service/domain hay hành vi persistence?
2. Có cần thực thi SQL thật không?
3. Có cần xác nhận entity mapping hoặc converter không?
4. Có cần database thực thi constraint không?
5. Có phụ thuộc SQL dialect hoặc vendor type không?
6. Có cần xác nhận transaction/locking/concurrency không?
7. Repository nên là mock hay repository thật trong test này?
8. H2 có đủ cho query phổ thông hay cần Testcontainers production DB?
9. Schema đến từ fixture hay migration thật?
10. Test có cô lập dữ liệu và hỗ trợ chạy song song không?
11. Publisher có được tiêu thụ bằng StepVerifier hoặc cơ chế rõ ràng không?
12. Test có kiểm tra behavior quan sát được thay vì chi tiết implementation không?

Quy tắc thực hành:

- **Unit test:** mock/fake dependency; tập trung vào logic, input/output, lỗi và điều phối reactive.
- **Data-access integration test:** repository/template/DatabaseClient thật, R2DBC driver và database; tập trung vào SQL, mapping, constraint và transaction.
- **Production database integration test:** đúng engine/driver; tập trung vào dialect, migration, type, locking và concurrency.
- **Performance test:** môi trường gần production với dữ liệu và tải đại diện.

## 26. Kết luận

Unit test và data-access integration test có ranh giới khác nhau. Unit test cô lập logic của một đơn vị, thường thay repository bằng mock hoặc fake để kiểm tra nhanh các nhánh nghiệp vụ và cách service xử lý Mono/Flux. Nó không thực thi SQL và không chứng minh Spring Data mapping hoặc database behavior.

Data-access integration test đi qua repository, R2dbcEntityTemplate hoặc DatabaseClient, ConnectionFactory, R2DBC driver và database. Nó xác nhận query, entity mapping, converter, generated ID, constraint, transaction và những hành vi phụ thuộc hệ quản trị. @DataR2dbcTest phù hợp cho nhiều test slice persistence; @SpringBootTest phù hợp khi cần wiring toàn ứng dụng hoặc startup/migration. H2 có thể giúp kiểm tra relational behavior phổ thông, còn Testcontainers với đúng database production cần thiết cho SQL đặc thù, migration, type, locking và concurrency.

Một suite hiệu quả dùng unit test để kiểm tra nhiều nhánh logic với tốc độ cao và dùng integration test để xác nhận hợp đồng persistence thực tế. Hãy chọn test theo behavior cần chứng minh, tiêu thụ publisher rõ ràng, cô lập dữ liệu và giữ một nhóm test trên đúng database production trong pipeline phát hành.


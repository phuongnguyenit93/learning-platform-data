# Chọn tài nguyên thật, bản nhúng hoặc dịch vụ mô phỏng

Một bài kiểm thử Spring thường cần nhiều tài nguyên bên ngoài ứng dụng: cơ sở dữ liệu, HTTP API, message broker, hệ thống lưu trữ tệp, cache hoặc dịch vụ xác thực. Khi chạy test, ta phải quyết định sẽ kết nối tới dịch vụ thật, dùng một triển khai nhúng (embedded/in-memory), hay thay thế dependency bằng mock, stub hoặc fake.

Không có một lựa chọn đúng cho mọi test. Dịch vụ thật đem lại độ trung thực cao nhưng thường chậm, tốn chi phí và khó kiểm soát. Bản nhúng giúp test nhanh, tự chạy và dễ cô lập, nhưng có thể khác hành vi production. Mock và fake tạo điều kiện kiểm tra logic trong phạm vi hẹp, nhưng không chứng minh ứng dụng giao tiếp đúng với hệ thống bên ngoài.

Mục tiêu là chọn tài nguyên phù hợp với hành vi đang cần xác nhận, rồi quản lý vòng đời và dữ liệu test sao cho kết quả ổn định, lặp lại được.

## 1. Ba cách cung cấp tài nguyên cho test

### Dùng dịch vụ thật

Test kết nối tới một instance thật của dịch vụ mà ứng dụng sử dụng, ví dụ PostgreSQL, Kafka, Redis hoặc một HTTP API trong môi trường kiểm thử.

“Thật” có thể là dịch vụ production-compatible chạy cục bộ bằng container, một instance chuyên dụng trong CI, hoặc sandbox do nhà cung cấp dịch vụ cung cấp. Không nhất thiết phải gọi production. Với database hoặc broker, Testcontainers thường tạo instance thật trong container dùng riêng cho test.

Ưu điểm:

- Kiểm tra được giao thức, dialect, ràng buộc và hành vi thực tế của công nghệ.
- Phát hiện khác biệt giữa thư viện ứng dụng và hệ thống mà production sử dụng.
- Có thể kiểm tra migration, transaction, locking, broker acknowledgment hoặc các tính năng riêng của dịch vụ.

Đổi lại, test cần khởi động và dọn dẹp tài nguyên, có thể tốn thời gian, cần Docker hoặc môi trường CI phù hợp và có thể thất bại do yếu tố hạ tầng.

### Dùng triển khai nhúng hoặc in-memory

Triển khai nhúng cung cấp một phiên bản nhẹ chạy trong cùng tiến trình hoặc được khởi động tự động cùng test. Ví dụ thường gặp là H2 in-memory cho database, embedded Kafka cho kiểm thử messaging hoặc một server HTTP giả lập chạy trên loopback.

Ưu điểm:

- Test tự khởi động, không cần phụ thuộc vào instance dùng chung.
- Tốc độ thường nhanh và dữ liệu dễ làm sạch.
- Phù hợp với test tích hợp thường xuyên trong vòng lặp phát triển.

Nhược điểm là bản nhúng có thể không tái hiện đầy đủ dialect, concurrency, cấu hình bảo mật hoặc tính năng của dịch vụ production. Test xanh trên H2 không đảm bảo migration sẽ chạy đúng trên PostgreSQL nếu hai hệ quản trị có khác biệt liên quan.

### Dùng dịch vụ mô phỏng hoặc test double

Mock, stub hoặc fake thay thế dependency thật bằng một đối tượng kiểm soát được trong test. Ví dụ, mock một `PaymentGateway`, dùng fake repository lưu dữ liệu trong map, hoặc cấu hình `MockRestServiceServer` để trả response HTTP đã định trước.

Ưu điểm:

- Test nhanh, xác định và không phụ thuộc mạng hay dịch vụ ngoài.
- Dễ tạo tình huống hiếm gặp như timeout, lỗi xác thực, dữ liệu không hợp lệ hoặc phản hồi bất thường.
- Phù hợp để kiểm tra quy tắc nghiệp vụ và cách ứng dụng phản ứng với kết quả từ dependency.

Nhược điểm là test chỉ xác nhận hành vi của test double. Nếu mock quá sâu hoặc mô phỏng sai hợp đồng, test có thể xanh trong khi ứng dụng không hoạt động với dịch vụ thật.

## 2. Chọn theo câu hỏi mà test cần trả lời

Trước khi chọn tài nguyên, hãy xác định điều test đang muốn chứng minh:

| Câu hỏi cần trả lời | Lựa chọn thường phù hợp |
| --- | --- |
| Quy tắc nghiệp vụ xử lý dữ liệu và lỗi ra sao? | Mock hoặc fake ở ranh giới ứng dụng. |
| Repository có tạo đúng SQL, mapping, constraint và transaction không? | Database nhúng để chạy nhanh; database cùng loại production để xác nhận tính tương thích. |
| Migration có chạy trên đúng hệ quản trị production không? | Database thật cùng loại, thường dùng Testcontainers hoặc môi trường chuyên dụng. |
| HTTP adapter có gửi đúng method, URL, header và body không? | Mock HTTP server kết hợp HTTP client thật. |
| Ứng dụng có tương tác đúng với API đối tác trong môi trường sandbox không? | Sandbox hoặc môi trường tích hợp thật, thường dành cho một nhóm test có kiểm soát. |
| Consumer và producer có trao đổi message đúng với broker không? | Embedded broker cho test nhanh; broker thật trong container cho tính năng production-specific. |
| Tệp được tạo, đọc và xóa đúng trên filesystem không? | Thư mục tạm trên filesystem thật bằng `@TempDir`. |

Một hệ thống thường cần nhiều cấp test. Unit test dùng mock/fake để kiểm tra logic; test tích hợp dùng bản nhúng hoặc container để kiểm tra kết nối; một số test end-to-end dùng dịch vụ thật để xác nhận hợp đồng toàn hệ thống.

## 3. Cơ sở dữ liệu: H2, database thật và Testcontainers

Database là ví dụ điển hình cho sự khác biệt giữa bản nhúng và dịch vụ production. `@DataJpaTest` thường cấu hình test slice cho JPA và có thể tự thay datasource bằng embedded database nếu dependency phù hợp có trên classpath.

Ví dụ test với H2 in-memory:

```java
@DataJpaTest
class PersonRepositoryTest {

    @Autowired
    PersonRepository repository;

    @Test
    void shouldFindPersonByEmail() {
        repository.save(new Person("Lan", "lan@example.test"));

        assertThat(repository.findByEmail("lan@example.test"))
                .isPresent();
    }
}
```

Test này nhanh và độc lập. H2 phù hợp để kiểm tra nhiều thao tác repository thông thường, nhưng không nên mặc định nó tương đương PostgreSQL, MySQL hoặc SQL Server. Những khác biệt có thể xuất hiện ở:

- Cú pháp SQL, kiểu dữ liệu, sequence và cách sinh khóa.
- Collation, so sánh chuỗi, timezone và precision của timestamp.
- Constraint, index, locking và transaction isolation.
- Stored procedure, function, trigger hoặc extension riêng của hệ quản trị.
- Hành vi của migration tool khi chạy trên dialect cụ thể.

Nếu ứng dụng production dùng PostgreSQL và phụ thuộc vào đặc tính PostgreSQL, hãy chạy test tích hợp với PostgreSQL thật. Testcontainers có thể khởi động container PostgreSQL cho test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class PersonRepositoryPostgresTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("app_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    PersonRepository repository;

    @Test
    void shouldPersistPersonInPostgres() {
        Person saved = repository.saveAndFlush(
                new Person("Lan", "lan@example.test")
        );

        assertThat(repository.findById(saved.getId())).isPresent();
    }
}
```

`@Container` đánh dấu container do JUnit Jupiter extension quản lý. `@DynamicPropertySource` đăng ký các thuộc tính kết nối lấy từ container sau khi nó được khởi động. `SpringBootTest` nạp application context và dùng datasource được cấu hình từ các thuộc tính động.

Với Spring Boot phiên bản hỗ trợ Testcontainers service connections, có thể dùng `@ServiceConnection` để Boot suy ra các connection details từ container thay vì đăng ký từng thuộc tính bằng `@DynamicPropertySource`:

```java
@Testcontainers
@SpringBootTest
class PersonRepositoryPostgresTest {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

`@ServiceConnection` thuộc Spring Boot, không phải Spring Framework core. Cần dependency Testcontainers tương ứng và module service connection phù hợp với phiên bản Boot đang dùng. Nếu không có auto-configuration này, cách `@DynamicPropertySource` vẫn là lựa chọn tường minh.

### Khi nào giữ H2 và khi nào dùng database production-compatible?

| Loại test | Database gợi ý | Lý do |
| --- | --- | --- |
| Test repository CRUD đơn giản, chạy thường xuyên | H2 hoặc embedded DB | Tốc độ và khả năng cô lập. |
| Test custom SQL, native query hoặc migration | Database cùng loại production | Kiểm tra dialect và cú pháp thật. |
| Test locking, isolation, constraint phức tạp | Database cùng loại production | Hành vi transaction phụ thuộc engine. |
| Test mapping JPA thông thường | H2 cho vòng phản hồi nhanh, thêm test container định kỳ | Cân bằng tốc độ và độ trung thực. |

Không cần chạy toàn bộ test trên container nếu điều đó làm vòng lặp quá chậm. Có thể giữ suite nhanh với H2 và thêm một nhóm test tích hợp chạy trên database production-compatible trong CI.

## 4. HTTP API bên ngoài: mock server, sandbox hay dịch vụ thật

Khi ứng dụng gọi HTTP API, có ba mức kiểm thử thường gặp.

### Mock request/response ở tầng client

Với `RestClient` hoặc `RestTemplate`, Spring Test cung cấp `MockRestServiceServer`. Test dùng HTTP client thật của ứng dụng nhưng chặn request ở request factory, kiểm tra method/URL/header/body và trả response giả lập.

```java
RestClient.Builder builder = RestClient.builder()
        .baseUrl("https://inventory.example");

MockRestServiceServer server = MockRestServiceServer
        .bindTo(builder)
        .build();

InventoryHttpAdapter adapter = new InventoryHttpAdapter(builder.build());

server.expect(requestTo("https://inventory.example/api/items/SKU-1"))
        .andExpect(method(HttpMethod.GET))
        .andRespond(withSuccess(
                """
                {"sku":"SKU-1","quantity":12}
                """,
                MediaType.APPLICATION_JSON
        ));

assertThat(adapter.findBySku("SKU-1"))
        .isEqualTo(new InventoryItem("SKU-1", 12));
server.verify();
```

Đây là lựa chọn phù hợp để xác nhận adapter tạo request đúng và chuyển response đúng. Nó không gọi dịch vụ bên ngoài và không xác nhận server đối tác đang hoạt động.

Với `WebClient`, thường dùng MockWebServer hoặc WireMock để mở HTTP server cục bộ, sau đó cấu hình `WebClient` gọi đến địa chỉ đó. Cách này cho phép kiểm tra request qua HTTP connector thực tế.

### Dùng sandbox của nhà cung cấp

Sandbox là môi trường thử nghiệm do nhà cung cấp API vận hành. Nó phù hợp khi cần xác nhận hợp đồng thực tế, chữ ký request, OAuth, quy trình nhiều bước hoặc những hành vi mà mock server không mô phỏng đáng tin cậy.

Test sandbox cần quản lý credentials, dữ liệu, quota, thời gian phản hồi và khả năng gián đoạn của dịch vụ. Không nên chạy mọi unit test phụ thuộc sandbox vì suite sẽ chậm và dễ thất bại do môi trường ngoài ứng dụng. Thường chỉ một nhóm integration/contract test chạy theo lịch hoặc trong pipeline phù hợp.

### Gọi dịch vụ thật

Một số hệ thống cần kiểm tra với dịch vụ thật, ví dụ xác nhận tích hợp thanh toán trong môi trường staging. Chỉ dùng dữ liệu và tài khoản được cấp riêng cho kiểm thử, có quy trình cleanup và tránh tác động đến người dùng hoặc dữ liệu production. Test cần có timeout, retry hợp lý và log đủ để chẩn đoán lỗi môi trường.

## 5. Message broker: embedded broker và broker thật

Với ứng dụng dùng Kafka, RabbitMQ hoặc ActiveMQ, test cần xác nhận producer gửi đúng message và consumer xử lý đúng payload, header, key hoặc acknowledgment.

Một số dự án Spring Kafka dùng embedded Kafka broker cho test:

```java
@SpringBootTest
@EmbeddedKafka(
        topics = "orders-test",
        partitions = 1,
        bootstrapServersProperty = "spring.kafka.bootstrap-servers"
)
class OrderEventIntegrationTest {

    @Autowired
    KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    @Test
    void shouldPublishOrderCreatedEvent() {
        kafkaTemplate.send(
                "orders-test",
                "order-42",
                new OrderCreatedEvent(42L)
        );
        // Consumer/test listener xác nhận message đã được nhận.
    }
}
```

`@EmbeddedKafka` được cung cấp bởi Spring Kafka test support, không thuộc Spring Framework core. Nó khởi chạy broker nhúng phục vụ test. Cần thêm dependency `spring-kafka-test` tương thích với Spring Kafka đang dùng và cấu hình consumer/test listener để xác nhận message thực sự được xử lý.

Embedded broker hữu ích cho test nhanh về serialization, listener, routing và consumer group ở mức phù hợp. Khi ứng dụng phụ thuộc vào tính năng đặc thù của broker production, cấu hình bảo mật, transaction, replication hoặc phiên bản broker cụ thể, nên bổ sung test với broker thật trong container hoặc môi trường tích hợp.

Với RabbitMQ, có thể chạy RabbitMQ container bằng Testcontainers để xác nhận exchange, queue, binding, acknowledgment và dead-letter configuration trên broker thật. Một mock `RabbitTemplate` phù hợp để kiểm tra logic gọi publisher ở unit test, nhưng không xác nhận topology đã được broker tạo đúng.

## 6. Filesystem và tài nguyên cục bộ

Không phải mọi tài nguyên đều cần dịch vụ mạng. Với code đọc/ghi tệp, dùng thư mục tạm do JUnit quản lý thường tốt hơn mock mọi thao tác `Files`:

```java
class ReportWriterTest {

    @TempDir
    Path tempDirectory;

    @Test
    void shouldWriteReport() throws IOException {
        Path report = tempDirectory.resolve("report.txt");

        new ReportWriter().write(report, "Quarterly report");

        assertThat(Files.readString(report))
                .isEqualTo("Quarterly report");
    }
}
```

`@TempDir` cung cấp một thư mục tạm và JUnit dọn dẹp sau vòng đời test phù hợp. Test này dùng filesystem thật của máy chạy test nhưng dữ liệu được cô lập trong thư mục riêng. Nó kiểm tra hành vi tạo và đọc tệp thực tế tốt hơn việc mock sâu các static method của `Files`.

Nếu ứng dụng dùng S3, Azure Blob Storage hoặc một object storage khác, có thể dùng fake/local emulator như LocalStack hoặc MinIO trong test tích hợp, tùy dịch vụ cần kiểm tra. Mock interface storage phù hợp với unit test nghiệp vụ; emulator/container giúp kiểm tra request, metadata và API tương thích; tài khoản sandbox hoặc môi trường thật phù hợp cho một số test hợp đồng cuối cùng.

## 7. Fake, stub, mock và embedded service khác nhau thế nào?

Các từ này thường được dùng lẫn nhau, nhưng có ý nghĩa khác nhau:

| Loại test double | Đặc điểm | Ví dụ |
| --- | --- | --- |
| Dummy | Đối tượng được truyền vào chỉ để lấp vị trí tham số, không được sử dụng. | Một `Clock` hoặc collaborator không được gọi trong test cụ thể. |
| Stub | Trả về dữ liệu đã định trước để kiểm soát nhánh xử lý. | `when(gateway.find()).thenReturn(item)`. |
| Mock | Ghi nhận và xác nhận tương tác mong đợi. | `verify(gateway).publish(event)`. |
| Fake | Triển khai đơn giản nhưng có hành vi làm việc được. | Repository trong bộ nhớ dùng `Map` để lưu entity. |
| Embedded service | Một triển khai dịch vụ chạy thật nhưng gọn nhẹ trong môi trường test. | H2 hoặc embedded Kafka. |
| Mock server | Server mô phỏng giao thức để client gửi request thật vào. | MockRestServiceServer, MockWebServer, WireMock. |

Fake và embedded service không giống mock. Fake repository có thể thực hiện truy vấn trong bộ nhớ, còn embedded database thực thi SQL và transaction theo engine của nó. Mock server tiếp nhận HTTP request qua client thật nhưng response được test điều khiển.

Chọn loại thay thế theo hành vi cần xác nhận. Không dùng mock để thay cho kiểm thử persistence nếu mục tiêu là xác nhận SQL; không dùng database container cho một unit test chỉ cần kiểm tra một nhánh nghiệp vụ đơn giản.

## 8. Cấu hình tài nguyên bằng Spring Test

Spring Test cung cấp một số cơ chế giúp đưa endpoint, credentials và connection details vào application context của test.

### `@TestPropertySource`

Khai báo property riêng cho test:

```java
@SpringJUnitConfig(AppConfig.class)
@TestPropertySource(properties = {
        "inventory.base-url=http://localhost:9090",
        "feature.audit.enabled=false"
})
class InventoryAdapterTest {
}
```

Các property này được đưa vào `Environment` của test context. Có thể dùng file properties riêng bằng thuộc tính `locations`.

### `@DynamicPropertySource`

Khi địa chỉ tài nguyên chỉ có sau khi khởi động container, đăng ký property động:

```java
@DynamicPropertySource
static void properties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
```

Phương thức phải là `static` và nhận `DynamicPropertyRegistry`. Các supplier chỉ được lấy giá trị khi property cần được resolve. Cơ chế này phù hợp với URL/port ngẫu nhiên do container hoặc mock server cấp.

### `@TestConfiguration`

Có thể khai báo bean chỉ dành cho test bằng `@TestConfiguration`, ví dụ một fake adapter hoặc một bean thay thế. Cần bảo đảm cấu hình test được import hoặc được nạp theo cách phù hợp; không nên âm thầm thay thế dependency khiến test tưởng đang dùng service thật.

### Profiles

`@ActiveProfiles("test")` có thể chọn profile dành cho test. Profile giúp phân biệt cấu hình theo môi trường, nhưng không tự tạo database, broker hay HTTP service. Vẫn cần cung cấp tài nguyên tương ứng và xác định rõ test đang dùng implementation nào.

## 9. Quản lý vòng đời, dữ liệu và tính cô lập

Một test có thể đúng khi chạy riêng nhưng thất bại khi chạy cả suite nếu tài nguyên hoặc dữ liệu bị chia sẻ. Dù dùng dịch vụ thật, bản nhúng hay mock server, cần quản lý vòng đời rõ ràng.

### Khởi động và dừng tài nguyên

- Dùng JUnit lifecycle (`@BeforeAll`, `@BeforeEach`, `@AfterEach`, `@AfterAll`) hoặc extension chuyên dụng để tạo và dừng tài nguyên.
- Với Testcontainers, dùng JUnit Jupiter extension hoặc cơ chế lifecycle phù hợp với phiên bản.
- Với MockWebServer/WireMock, khởi động trước request và dừng sau test hoặc sau class.
- Tránh để server hoặc container sống sót ngoài vòng đời test nếu không có chủ đích chia sẻ.

### Cô lập dữ liệu

- Mỗi test dùng khóa, tên topic hoặc thư mục riêng khi có thể.
- Xóa dữ liệu sau test hoặc dùng database/container mới theo phạm vi phù hợp.
- Không để test phụ thuộc vào thứ tự chạy hoặc dữ liệu do test trước tạo.
- Khi chia sẻ container giữa nhiều test, vẫn phải cô lập schema, table, topic hoặc key.

### Transaction rollback

`@Transactional` trên test có thể rollback database sau test, nhưng không tự động rollback mọi side effect ngoài database. Message đã gửi tới broker, HTTP request tới dịch vụ ngoài hoặc tệp đã ghi có thể vẫn tồn tại. Cần cleanup riêng cho các tài nguyên đó.

### Timeout và retry

Test dùng dịch vụ thật cần timeout hữu hạn để tránh treo suite. Retry chỉ nên dùng khi lỗi có tính tạm thời và retry là hành vi thực tế của ứng dụng. Retry test bừa bãi có thể che giấu race condition hoặc lỗi cấu hình.

## 10. Tránh dùng tài nguyên production trong test thông thường

Kết nối test tới database, broker hoặc API production có thể làm thay đổi dữ liệu thật, tiêu thụ quota, gửi thông báo tới người dùng hoặc phát sinh chi phí. Test thông thường nên dùng tài khoản và tài nguyên dành riêng cho test.

Nếu bắt buộc kiểm tra trên hệ thống gần production, dùng môi trường staging/sandbox, credentials riêng, dữ liệu nhận diện được là dữ liệu test và quy trình cleanup. Tránh đưa secret vào source code hoặc log; lấy thông tin kết nối từ cấu hình môi trường/secret store được quản lý.

Không nên dùng một instance dùng chung mà mọi developer và pipeline đều ghi vào cùng bảng hoặc topic nếu không có cách cô lập. Những test chạy song song có thể đè dữ liệu hoặc tiêu thụ message của nhau.

## 11. Ma trận lựa chọn thực tế

| Tài nguyên | Test nhanh, cô lập | Test tích hợp có độ trung thực cao | Test hợp đồng/end-to-end |
| --- | --- | --- | --- |
| Database | H2 hoặc fake repository tùy mục tiêu | Testcontainers với DB cùng loại production | Staging hoặc DB chuyên dụng có cấu hình production-like |
| HTTP outbound | Mock interface nghiệp vụ | MockRestServiceServer, MockWebServer hoặc WireMock | Sandbox/instance dịch vụ thật |
| Kafka/RabbitMQ | Mock publisher hoặc fake event bus | Embedded broker hoặc broker container | Broker staging và các service liên quan |
| Filesystem | `@TempDir` trên filesystem thật | Filesystem/container mô phỏng môi trường đích | Storage integration environment |
| Object storage | Mock storage port | LocalStack/MinIO hoặc emulator phù hợp | Sandbox/tenant storage riêng |
| Identity/OAuth | Stub token provider hoặc mock port | Mock identity server hoặc container | Identity sandbox với flow thật |

Ma trận chỉ là điểm bắt đầu. Nếu một tính năng phụ thuộc vào behavior cụ thể của engine hoặc nhà cung cấp, hãy tăng độ trung thực của test ở đúng khu vực đó. Không cần dùng dịch vụ thật cho tất cả các test.

## 12. Một chiến lược nhiều tầng cho dự án Spring

Một dự án Spring có thể tổ chức test thành các nhóm sau:

```text
Unit tests
  - Mock/fake application ports
  - Kiểm tra quy tắc nghiệp vụ
  - Nhanh, chạy thường xuyên

Integration tests
  - Embedded services hoặc Testcontainers
  - Kiểm tra repository, HTTP adapter, messaging, serialization
  - Chạy trong CI

Contract / end-to-end tests
  - Sandbox hoặc dịch vụ thật trong môi trường chuyên dụng
  - Kiểm tra tương tác giữa các hệ thống
  - Chạy có kiểm soát, thường ít hơn
```

Ví dụ, với luồng tạo đơn hàng:

1. Unit test `OrderService` mock `InventoryGateway` để xác nhận quy tắc đủ tồn kho.
2. Test `InventoryHttpAdapter` dùng `MockRestServiceServer` để xác nhận URL, header, JSON và mapping lỗi.
3. Test repository dùng PostgreSQL container để xác nhận transaction và schema.
4. Test tích hợp cuối cùng gọi sandbox của hệ thống kho để xác nhận hợp đồng thực tế nếu rủi ro nghiệp vụ yêu cầu.

Mỗi nhóm trả lời một câu hỏi riêng. Việc phân tầng giúp suite có nhiều test nhanh và xác định, đồng thời vẫn có đủ bằng chứng về khả năng tích hợp với hạ tầng thật.

## 13. Những sai lầm thường gặp

**Dùng H2 rồi kết luận ứng dụng tương thích với PostgreSQL.**

H2 và PostgreSQL có thể khác nhau về SQL, kiểu dữ liệu, constraint và transaction. Chạy test bổ sung trên đúng hệ quản trị khi các đặc tính đó quan trọng.

**Mock repository trong test được gọi là integration test persistence.**

Mock repository không thực thi SQL hoặc transaction. Dùng database thật/nhúng khi mục tiêu là kiểm tra persistence.

**Gọi API đối tác thật trong mọi unit test.**

Điều này khiến suite chậm, dễ bị giới hạn quota và phụ thuộc mạng. Mock interface cho logic nghiệp vụ, dùng mock HTTP server cho adapter và dành sandbox cho test hợp đồng.

**Dùng embedded broker nhưng bỏ qua khác biệt với broker production.**

Embedded broker có thể không tái hiện cấu hình bảo mật, replication hoặc tính năng riêng. Thêm test với broker cùng loại production khi cần.

**Cho rằng rollback transaction sẽ dọn mọi side effect.**

Rollback database không thu hồi message đã publish, HTTP request đã gửi hoặc file đã tạo. Cần cleanup riêng.

**Chia sẻ dữ liệu và tài nguyên giữa test chạy song song.**

Các test có thể đè dữ liệu hoặc đọc nhầm message. Dùng resource namespace riêng, key riêng hoặc cơ chế isolation phù hợp.

**Dùng mock quá sâu vào API của framework.**

Mock chuỗi fluent thường khiến test phụ thuộc cách gọi method. Mock interface của ứng dụng hoặc dùng mock server tại ranh giới giao thức.

## 14. Quy trình quyết định và triển khai

Khi thêm một dependency ngoài vào test, có thể làm theo trình tự:

1. Xác định hành vi cần kiểm tra: logic nghiệp vụ, persistence, giao thức, cấu hình hay tích hợp end-to-end.
2. Xác định đặc tính của dịch vụ có ảnh hưởng đến hành vi đó: dialect, protocol, transaction, serialization, concurrency hoặc security.
3. Chọn mức trung thực tối thiểu đủ để kiểm tra hành vi: mock/fake, embedded, container hoặc dịch vụ sandbox/thật.
4. Cấu hình endpoint và credentials qua Spring Test properties hoặc dynamic properties; không hard-code secret.
5. Quản lý startup/shutdown và cleanup rõ ràng.
6. Cô lập dữ liệu để test chạy độc lập và có thể chạy song song.
7. Bổ sung test ở mức cao hơn khi mock/embedded không thể xác nhận đặc tính quan trọng.
8. Chạy nhóm test nhanh thường xuyên và nhóm test hạ tầng thật trong CI theo lịch hoặc stage phù hợp.

## Kết luận

Chọn dịch vụ thật, bản nhúng hay dịch vụ mô phỏng dựa trên hành vi mà bài test cần xác nhận. Mock và fake phù hợp với logic nghiệp vụ; embedded service giúp kiểm tra tích hợp nhanh; Testcontainers và mock HTTP server cho độ trung thực cao hơn ở ranh giới dữ liệu/giao thức; sandbox hoặc dịch vụ thật phù hợp với một số test hợp đồng và end-to-end.

Không có một loại tài nguyên duy nhất thay thế được các cấp test còn lại. Một chiến lược Spring Testing tốt kết hợp nhiều mức, quản lý vòng đời và dữ liệu rõ ràng, đồng thời dùng đúng hệ quản trị hoặc giao thức production khi những khác biệt đó có ý nghĩa đối với hành vi ứng dụng.

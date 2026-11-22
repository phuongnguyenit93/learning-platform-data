# Quản lý dữ liệu kiểm thử độc lập, tái lập và dọn sạch trong CI

## 1. Vấn đề: một test đúng không được phụ thuộc test chạy trước

Giả sử API Orders nhận lệnh tạo đơn, lưu PostgreSQL, dùng Idempotency-Key chống tạo trùng, ghi transactional outbox và trả HTTP 201. Khi một test kiểm tra POST thành công, nó tạo order, idempotency record và outbox event. Test tiếp theo kiểm tra POST cùng mã tham chiếu nhưng kỳ vọng dữ liệu rỗng. Nếu hai test dùng chung database mà không có vòng đời dữ liệu rõ ràng, test sau có thể nhận **409 Conflict**, dù code nghiệp vụ không sai.

Đây là **test pollution**: trạng thái do test A để lại làm test B thất bại hoặc, tệ hơn, **pass sai**. Trong CI, thứ tự chạy, tốc độ container, số worker, mốc thời gian và retry khác máy cá nhân nên vấn đề thường bộc lộ thành lỗi chập chờn (*flaky tests*).

Bài thuộc chương **Kiểm thử** của module **INTEGRATION_API_REST**. Mục tiêu là kiểm thử hợp đồng REST theo resource/URI, HTTP methods/status, validation, idempotency, cache, authentication, authorization và xử lý lỗi bằng **Java/Spring hoặc công nghệ tương đương**. Trọng tâm: **mỗi test biết chính xác dữ liệu đầu vào, trạng thái sau chạy và cách cô lập khỏi test khác**; CI phải có bằng chứng tái lập và cơ chế dọn sạch có giới hạn.

Sau bài, bạn sẽ:

1. Phân biệt isolation ở mức **test, method, class, suite, job, database và external service**.
2. Thiết kế fixture tối thiểu, rõ ràng, deterministic và có chủ sở hữu.
3. Chọn transaction rollback, cleanup SQL, database/schema riêng hay container dùng một lần đúng bối cảnh.
4. Dùng **JUnit 5, Spring Boot Test, Testcontainers, Flyway, MockMvc và HTTP thực**.
5. Ngăn rò dữ liệu qua **cache, Redis, message broker, file, clock và process async**.
6. Thiết kế CI song song không dùng chung dữ liệu, không xóa nhầm môi trường thật.
7. Đánh giá test qua trạng thái HTTP, database, idempotency, bảo mật đa tenant và khả năng chạy lại.

Ví dụ sử dụng **Java 17+, Spring Boot 3.x, JUnit Jupiter, PostgreSQL và Testcontainers**. Tên repository/entity/DTO trong mã là phần giả định của hệ thống Orders để người học triển khai. Không chạy lệnh dọn database mẫu trên môi trường chia sẻ hoặc production.

## 2. Ba bất biến của test data đáng tin

**Độc lập (isolation):** Tất cả input và trạng thái mà test T cần phải do T hoặc fixture được T sở hữu thiết lập. Không yêu cầu “hãy chạy test tạo khách hàng trước”.

**Tái lập (repeatability):** Cùng code, schema và seed cho cùng kết quả logic, không phụ thuộc thứ tự test hay giờ máy. Với tính năng có ngẫu nhiên/thời gian, dùng nguồn được kiểm soát và assert theo invariant chứ không đoán UUID.

**Dọn sạch (cleanup):** Sau khi test kết thúc, môi trường dùng lại không còn side effect vượt ngoài phạm vi được phép. Nếu dùng container/database hoàn toàn dùng một lần, **hủy nguyên môi trường** là cleanup hợp lệ. Nếu tái sử dụng, phải dọn cả DB lẫn cache, queue, object storage, filesystem và background workers liên quan.

Một test tốt có thể mô tả bằng:

~~~text
Given  schema_version + seed_minimal + controlled_clock
When   send HTTP request (authentication, headers, JSON)
Then   assert status, headers, body, committed state and events
Finally cleanup owned data or discard isolated environment
~~~

Không đánh đồng **idempotency** với khả năng dọn sạch: retry cùng key giúp một business operation không tạo trùng, nhưng các lần chạy test khác nhau vẫn cần namespace và lifecycle riêng.

### Ma trận nguồn gây nhiễm chéo

| Nguồn trạng thái | Triệu chứng | Ranh giới cô lập |
| --- | --- | --- |
| PostgreSQL rows/sequences | Unique conflict, count khác, ID bất ngờ | DB/schema hoặc cleanup transaction |
| Redis cache/rate limiter | GET cũ, HTTP 429 ngẫu nhiên | Key prefix riêng, flush scoped, container |
| Broker Kafka/RabbitMQ | Message cũ kích hoạt consumer | Topic/consumer group namespace, test broker |
| Object storage/file | Export nhìn thấy file test trước | Bucket/prefix/thư mục tạm riêng |
| Mock server | Stub từ test trước áp nhầm | Reset expectations mỗi test |
| App singleton/static state | Counter/token/feature flag còn lại | Reset hoặc tránh mutable global |
| Clock/timezone/randomness | Token hết hạn, ngày tháng đổi | Inject Clock/Random/ID generator |
| Background jobs | Cleanup xong job vẫn ghi lại row | Stop/quiesce worker, await bounded, discard DB |
| Search index/CDN | Eventual consistency, cache sai tenant | Test namespace và reconciliation |
| CI runners/jobs | Chạy song song cùng DB/key | Mỗi job có môi trường và credentials riêng |

## 3. Chọn chiến lược cô lập theo lớp kiểm thử

Không phải mọi test đều cần PostgreSQL thật. Đặt mức cô lập ở **tầng thấp nhất vẫn đủ chứng minh hành vi cần test**.

| Loại test | Dữ liệu và hạ tầng | Mức độ tin cậy đạt được |
| --- | --- | --- |
| **Unit** | Object factory trong RAM, fake clock, stub repository | Logic thuần, không xác minh SQL/HTTP |
| **MVC slice** (@WebMvcTest) | Mock service, Spring MVC/Security filters | Routing, validation, JSON, status/headers |
| **Repository slice** (@DataJpaTest) | DB thật hoặc test DB, transaction per test | Entity mapping, query, constraint; chú ý rollback |
| **Spring Boot integration** | App context + PostgreSQL Testcontainers | HTTP → service → transaction → DB |
| **Multi-service integration** | Broker/Redis/DB thật, namespace riêng | Async delivery, dedup, cache, retries |
| **End-to-end** | Hệ thống cô lập theo deployment/test run | Hành vi liên dịch vụ, khả năng phục hồi |
| **Contract test** | Mock provider hoặc real provider sandbox | Request/response schema, không cần dữ liệu production |

**Quy tắc:** Test ngoại lệ SQL unique constraint không thể được chứng minh chỉ bằng Mockito ném exception. Test optimistic locking/concurrent commit cần database với semantics gần production. Test chữ ký JWT không thể được chứng minh bằng Security Test **jwt()**, vì helper này tạo Authentication giả.

Một số điểm dễ nhầm:

- **@DataJpaTest** thường chạy rollback theo transaction test; điều đó phù hợp query test nhưng có thể giấu lỗi chỉ xuất hiện khi commit thật.
- **MockMvc** gọi vào Spring MVC **không cần socket HTTP**; với request đồng bộ, test transaction có thể nằm cùng thread và bị rollback bởi test context. Với server thật dùng **RANDOM_PORT/TestRestTemplate/WebTestClient**, server xử lý trên thread/transaction khác; rollback ở test thread **không xóa** thay đổi đã commit bên server.
- Với async listener, job scheduler và outbox relay, rollback test thread không bao trùm consumer transaction hoặc external side effects.
- **@DirtiesContext** xây lại Spring context, không phải lệnh reset PostgreSQL/Kafka/Redis dùng chung; lạm dụng làm CI chậm mà vẫn có thể nhiễm bẩn.
- Chạy một test **đơn lẻ**, chạy **cả class** và chạy **full suite không cố định thứ tự** đều là các kiểm chứng cần thiết.

## 4. Fixture là đặc tả nghiệp vụ tối thiểu, không phải bản dump production

Một fixture nên nói **vì sao dữ liệu tồn tại**, không lấp đầy mọi trường bằng giá trị tùy tiện. Ví dụ:

~~~text
tenant-a có user buyer-1 với scope orders:write
tenant-b có buyer-2 không được đọc order của tenant-a
cart-42 thuộc tenant-a, gồm một sản phẩm còn hàng
addr-8 thuộc buyer-1
order ord-501 đã COMMITTED, có một outbox OrderCreated
~~~

Tránh copy database production sang CI: có thể chứa **PII, token, mật khẩu, số thẻ, audit record** và số lượng dữ liệu quá lớn. Thay bằng dữ liệu **synthetic** như email ở domain example.invalid, ID không trùng với hệ thống thật, số tiền giả và access token test được ký bằng khóa riêng.

### Object Mother, builder và factory

Một test fixture factory minh họa:

~~~java
public final class OrderFixtures {
    private OrderFixtures() {}

    public static final UUID TENANT_A = UUID.fromString(
        "11111111-1111-4111-8111-111111111111");
    public static final UUID TENANT_B = UUID.fromString(
        "22222222-2222-4222-8222-222222222222");

    public static CreateOrderRequest validCreateOrder() {
        return new CreateOrderRequest("cart-42", "addr-8");
    }

    public static OrderEntity committedOrder(
            UUID id, UUID tenantId, String reference) {
        return OrderEntity.testCreated(
            id, tenantId, reference,
            "CREATED", 180000L, "VND");
    }
}
~~~

**OrderEntity.testCreated** là factory của domain/test code cần cài đặt, không phải Spring API. Với test cần thay một field, dùng builder có default **đủ nhưng tối thiểu**, ví dụ một cart thuộc tenant A. Không để fixture factory âm thầm tạo 20 bảng hoặc gọi external API, vì việc tái lập và cleanup sẽ khó kiểm soát.

**ID ổn định hay ngẫu nhiên?** Nếu test assert một ID cụ thể hoặc dựa vào FK giữa các fixture, dùng UUID cố định **trong database đã cô lập** để dễ đọc lỗi. Nếu nhiều job dùng chung sink và không thể cô lập, cần **namespace theo run ID** hoặc sinh ID duy nhất cho từng lần chạy, rồi assert theo ID đã nhận. Không dùng ID cố định như một cách thay thế isolation.

### Seed và migration có vai trò khác nhau

- **Migration** định nghĩa cấu trúc và invariants: tables, indexes, unique constraints, enum, FK.
- **Reference seed** định nghĩa dữ liệu cấu hình bất biến cần cho ứng dụng (ví dụ loại tiền tệ), có thể được version cùng migration.
- **Test fixture seed** tạo từng tenant, user, cart, order theo kịch bản; không nên nhúng toàn bộ fixture vào migration production.
- **Expected result/golden file** là kết quả để so contract, không được tự “update snapshot” khi code lỗi rồi coi là fix.

Mỗi test nên chỉ phụ thuộc schema **được migrate đúng phiên bản** và fixture đã khai báo; không chạy test trên một database dev đang tồn tại với schema sửa bằng tay.

## 5. Khởi tạo PostgreSQL dùng một lần bằng Testcontainers

Đối với REST API dùng Spring Data JPA, PostgreSQL thật trong container giúp kiểm thử **UNIQUE constraint, JSONB, locking, transaction isolation và SQL** mà H2 không luôn mô phỏng giống. Một container per class/suite có thể tái sử dụng **trong phạm vi test run**; không được để nhiều CI jobs cùng trỏ tới một database chia sẻ chỉ vì muốn nhanh.

Dependency theo Spring Boot 3.x/JUnit 5 điển hình gồm **spring-boot-starter-test**, **org.testcontainers:junit-jupiter**, **org.testcontainers:postgresql**, JDBC driver PostgreSQL và Flyway nếu dự án dùng migration. Cấu hình dưới đây dùng **@DynamicPropertySource**, không yêu cầu @ServiceConnection.

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
class OrdersPostgresIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("orders_it")
            .withUsername("orders_it")
            .withPassword("test-only-password");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url",
            postgres::getJdbcUrl);
        registry.add("spring.datasource.username",
            postgres::getUsername);
        registry.add("spring.datasource.password",
            postgres::getPassword);
    }

    @Test
    void databaseIsAvailable() {
        assertTrue(postgres.isRunning());
    }
}
~~~

Các imports đến từ Spring Test, JUnit Jupiter và Testcontainers. **Testcontainers cần Docker/container runtime trên CI runner**, quyền tải image và thời gian startup trong CI timeout; mật khẩu ví dụ chỉ dùng trên database test cô lập. Không dùng credential production.

Vì @Container là **static**, container sống theo vòng đời class do JUnit extension quản lý. Nếu các class chia sẻ Spring ApplicationContext cache, hãy kiểm soát lifecycle của datasource/container: đừng để context cache giữ JDBC URL của container đã dừng. Có thể dùng **container sống cùng suite/context** hoặc giới hạn context caching có chủ đích. Không bật **reusable containers** trên CI một cách mặc định: tái sử dụng qua lượt chạy sẽ phá giả định sạch nếu không reset chặt chẽ.

### Dùng Flyway/Liquibase để dựng schema

Test nên chạy **migration giống production (cùng version)**, thay vì Hibernate ddl-auto=create dựng schema rồi bỏ qua unique index/check constraint thực.

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
~~~

YAML này giả định ứng dụng dùng Flyway và JPA, không phải mọi dependency được tự cài. Hibernate validate giúp phát hiện mismatch entity/schema nhưng không thay migration test. **Reference data** có thể do migration chuẩn tạo; **fixture theo từng scenario** không nên nằm trong migration production.

### Tốc độ và phạm vi reuse

- **Per method container:** cô lập mạnh nhưng rất tốn startup, hợp lý khi test nâng cấp database.
- **Per class/container + cleanup:** cân bằng thời gian và isolation.
- **Per suite/container + schema/database riêng cho class:** nhanh hơn nhưng phức tạp quản lý pool/schema và parallel.
- **Per CI job container:** tránh cross-job pollution; hủy container/volume khi job kết thúc.

Đo cả thời gian chạy, tỷ lệ flaky, thời gian debug và mức tương đồng với production SQL.

## 6. Transaction rollback: mạnh nhưng không áp dụng mọi đường đi

Một @DataJpaTest có @Transactional thường rollback sau mỗi test, nên mọi thay đổi **trong đúng transaction do Spring Test quản lý** sẽ bị bỏ.

~~~java
@DataJpaTest
class OrderRepositoryTest {
    @Autowired OrderRepository orders;

    @Test
    void findOrderByTenantAndReference() {
        OrderEntity seeded = orders.save(
            OrderFixtures.committedOrder(
                UUID.fromString(
                    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
                OrderFixtures.TENANT_A, "fixture-order-1"));

        assertThat(orders.findByTenantIdAndExternalReference(
            OrderFixtures.TENANT_A, "fixture-order-1"))
            .contains(seeded);
        // Dữ liệu thuộc transaction test sẽ rollback.
    }
}
~~~

**Ngoại lệ quan trọng:**

1. **RANDOM_PORT + TestRestTemplate** gửi HTTP qua socket; server xử lý trên thread và transaction khác, vì vậy test thread rollback **không xóa** thay đổi đã commit phía server.
2. **@Async, scheduler, broker consumer và HTTP client bên ngoài** chạy transaction/tiến trình độc lập.
3. **REQUIRES_NEW** có thể commit transaction riêng ngoài vòng rollback test.
4. **Redis, cache, broker, file và object storage** không rollback theo JDBC.
5. Lỗi deferred constraint/commit-time trigger và event dispatch sau commit chỉ xuất hiện khi **commit thật**; rollback test có thể bỏ sót.

**Đừng gắn @Transactional cho toàn HTTP integration test chỉ để “tự dọn”.** Chọn cleanup ở boundary thực sự được kiểm thử.

## 7. Dọn dữ liệu bằng SQL có kiểm soát

Với database test được tái sử dụng giữa methods, chọn **reset-before** làm đảm bảo chính: test có trạng thái sạch ngay cả khi test trước không chạy teardown. **Reset-after** giúp bớt tồn dư cho test sau, nhưng sẽ không chạy nếu JVM/container bị kill. Có thể kết hợp cả hai nếu phù hợp.

Spring Test hỗ trợ @Sql:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Sql(
    scripts = "/sql/clean-owned-fixtures.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD,
    config = @SqlConfig(
        transactionMode = SqlConfig.TransactionMode.ISOLATED))
class OrdersHttpIT {
    // Đã reset database trước mỗi test.
}
~~~

File SQL trên là **tài nguyên test cần tự tạo trong dự án**, không phải tệp được bài này tạo ra. Với PostgreSQL **cô lập hoàn toàn**, một script minh họa:

~~~sql
-- CHỈ chạy trên container/database dành riêng cho test.
TRUNCATE TABLE
    order_items,
    outbox_events,
    idempotency_records,
    orders,
    carts,
    addresses
RESTART IDENTITY;
-- Giữ reference tables và Flyway schema history.
~~~

**Không thêm TRUNCATE ... CASCADE tùy tiện** để vượt lỗi FK: CASCADE có thể xóa bảng ngoài phạm vi như quyền người dùng hoặc reference data. Khi FK chặn, sửa thứ tự/scope cleanup hoặc tách DB chứ không mở rộng phạm vi xóa mù.

**Quy tắc an toàn:** chạy cleanup chỉ với test credentials trên DB được nhận diện rõ là test; kiểm tra endpoint/database name; không đụng staging/production; không xóa migration metadata. Nếu test chạy **song song cùng DB**, một cleanup có thể xóa fixture của test khác: dùng **schema/database riêng**, hoặc tắt parallel ở nhóm dùng cleanup toàn cục.

@Sql **ISOLATED transaction mode** cần transaction manager tương thích. Nếu một transaction test khác đang giữ lock, cleanup độc lập có thể bị chặn; nên chạy reset **trước khi transaction nghiệp vụ được mở**, không phải giữa một tác vụ async đang ghi.

Nếu không thể reset DB toàn cục, dùng **tracked cleanup**: mỗi fixture lưu row IDs hoặc test-run namespace, xóa từ bảng con đến cha, assert không còn row thuộc test. Kết hợp TTL và job dọn định kỳ cho artifacts ngoài DB; không phụ thuộc riêng @AfterEach khi process có thể crash.

## 8. Test HTTP phải xác nhận dữ liệu đã commit

Ví dụ gửi **POST /api/v1/orders** qua real HTTP rồi đọc state ở database:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderCreateHttpIT {
    @Autowired TestRestTemplate http;
    @Autowired OrderRepository orders;
    @Autowired OutboxRepository outbox;

    @Test
    void createPersistsOrderAndOutbox() {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setBearerAuth("signed-test-token");
        headers.set("Idempotency-Key", "order-create-it-1");

        HttpEntity<CreateOrderRequest> request =
            new HttpEntity<>(
                OrderFixtures.validCreateOrder(), headers);

        ResponseEntity<OrderResponse> reply =
            http.postForEntity(
                "/api/v1/orders", request, OrderResponse.class);

        assertThat(reply.getStatusCode())
            .isEqualTo(HttpStatus.CREATED);
        UUID id = reply.getBody().id();
        assertThat(reply.getHeaders().getLocation().getPath())
            .isEqualTo("/api/v1/orders/" + id);
        assertThat(orders.findById(id)).isPresent();
        assertThat(outbox.countByAggregateIdAndEventType(
            id, "OrderCreated")).isEqualTo(1L);
    }
}
~~~

Đây là **skeleton**: cần cart/address fixture, DTO/repositories, cleanup và issuer/key test. **Chuỗi "signed-test-token" không tự hợp lệ**; thay bằng token thực ký bởi test issuer hoặc cơ chế auth riêng cho test có giới hạn phạm vi. Đừng tắt SecurityFilterChain để test pass.

Với **MockMvc**, helper **jwt()** của spring-security-test cho phép test 201/401/403 mà không cần issuer thật, nhưng nó **không kiểm chứng signature/issuer/audience**. Cần test riêng qua Bearer token thật và mock JWKS/introspection nếu đây là yêu cầu bảo mật.

**Không dựa vào auto-increment IDs** để khẳng định sạch; assert theo business key/tenant, count liên quan và transaction commit thật. Đọc DB sau HTTP trong transaction mới, tránh persistence context cache của test làm kết quả sai.

## 9. Bộ fixture phải đại diện trạng thái HTTP

| Ca kiểm thử | Dữ liệu chuẩn bị | Kỳ vọng |
| --- | --- | --- |
| GET tồn tại | Order thuộc tenant A | 200 + DTO đúng contract |
| GET không tồn tại | ID chưa tạo | 404, không lộ dữ liệu |
| GET ngoài quyền | Order của tenant B | 403/404 theo policy |
| POST thiếu field | JSON không có shippingAddressId | 400 validation |
| POST trùng external reference | Một order đã commit cùng tenant/reference | 409, không tạo row/outbox |
| POST retry cùng key | Có idempotency result với cùng fingerprint | Replay cùng ID, không phát event mới |
| PATCH If-Match cũ | Order đã tăng version | 412, không ghi đè |
| GET If-None-Match đúng | ETag của representation hiện tại | 304, không có JSON body |
| Rate limiter | Bucket user A cạn, user B còn token | 429/200 không ảnh hưởng nhau |
| Async operation | Có job PENDING/result chưa sẵn sàng | 202/GET status theo contract |

Không seed tất cả scenario vào cùng database global. Mỗi test nên tạo fixture chuyên biệt, có chủ sở hữu và cleanup boundary rõ ràng.

Ví dụ hai tenant:

~~~text
tenant A: buyer-1, cart-42, addr-8, order ord-a
tenant B: buyer-2, cart-77, addr-9, order ord-b

caller A GET /orders/ord-a => 200
caller A GET /orders/ord-b => 404 (policy ẩn resource)
caller B GET /orders/ord-a => 404
~~~

Tenant IDs phải đến từ principal/membership đã xác minh; không tin field tenant trong JSON body. Nếu API công bố 403 thay 404 cho truy cập ngoài quyền, fixture/test phải theo hợp đồng đó, không áp kỳ vọng tùy tiện.

### Một HTTP contract có thể tái lập

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <signed-test-access-token>
Idempotency-Key: it-run42-create-1
Content-Type: application/json
Accept: application/json

{"cartId":"cart-42","shippingAddressId":"addr-8"}
~~~

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa
Content-Type: application/json

{"id":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","status":"CREATED"}
~~~

ID và token ở trên là **dữ liệu minh họa**, không phải ID mà server bắt buộc sinh. Test thực nên lấy ID từ phản hồi rồi so Location, JSON schema và bản ghi database. Lần gọi lại **cùng Idempotency-Key và cùng body** phải replay cùng resource; **cùng key nhưng body khác** nhận 409 theo contract và không tạo outbox mới. Đặt expectations vào tests, đồng thời có thể kiểm schema/status với **OpenAPI contract validator** trong CI; OpenAPI không tạo hoặc dọn fixture thay cho test.

## 10. ID, idempotency key và namespace trong test song song

Nếu suite chạy trên một resource dùng chung, các giá trị như orderRef, idempotencyKey, Redis key hoặc filename phải không trùng. Một **test run namespace** có thể là **it-run42-shard2**:

~~~text
orderRef     = testRun + ":checkout-create"
idempotency  = testRun + ":POST:/orders:case-1"
redisKey     = "it:" + testRun + ":tenant-a:orders-read"
objectPrefix = "it/" + testRun + "/exports/"
brokerGroup  = "it-" + testRun + "-inventory"
~~~

Đây là ý tưởng khóa, không phải cú pháp Spring tự hiểu. Validate ký tự/độ dài run ID; không ghép trực tiếp input không tin cậy thành path, SQL hoặc Redis key. **Unique ID tránh đụng nhau, không thay isolation và cleanup**: row cũ vẫn còn, broker vẫn chứa message cũ và Redis vẫn giữ key đến TTL.

Với **retry của chính một request**, giữ nguyên Idempotency-Key và payload; với **hai test độc lập**, dùng key khác hoặc database riêng. Không tạo key mới mỗi lần retry rồi kết luận API tạo trùng là lỗi.

### Clock, timezone và randomness

Một test token hết hạn hoặc ngày thanh toán có thể fail vì ngày/giờ máy CI khác. Inject clock và dùng giá trị cố định:

~~~java
@Configuration
class ClockConfiguration {
    @Bean
    Clock appClock() {
        return Clock.systemUTC();
    }
}

@TestConfiguration
class FixedClockTestConfiguration {
    @Bean
    @Primary
    Clock fixedClock() {
        return Clock.fixed(
            Instant.parse("2026-01-15T10:00:00Z"),
            ZoneOffset.UTC);
    }
}
~~~

Service dùng **Instant.now(clock)**; test phải import fixed clock có chủ đích, không cho @Primary fixed clock lọt production. JWT decoder có thể dùng validator/clock riêng, nên đóng băng domain Clock **không tự đảm bảo** JWT sẽ được coi là còn hạn. Ngoài ra kiểm soát **Locale, ZoneId, JSON format, sorting, pseudo-random seed**. Với rate limiting, dùng TimeSource monotonic cho elapsed time; không lấy wall clock làm System.nanoTime giả.

## 11. Redis, cache và limiter cũng là test data

Một test GET có thể đọc **cache từ test trước**, dù PostgreSQL đã truncate. Rate limiter của user có thể còn thiếu token khiến HTTP 429 xuất hiện ngẫu nhiên.

- Dùng **Redis container riêng theo CI job** hoặc prefix **it:<testRun>:** cho mỗi key; chỉ cleanup key thuộc prefix.
- Không dùng **FLUSHALL/FLUSHDB trên Redis dùng chung**. Ngay cả staging cũng không phải sandbox được phép xóa toàn bộ.
- TTL giúp dọn key cũ nhưng **không cô lập ngay lập tức**; test phải reset state hoặc dùng namespace riêng.
- Reset in-memory cache, circuit breaker, counters và mutable test singleton nếu chúng tham gia request.
- Với multi-tenant, assert cache/limiter key có scope đúng principal + tenant + route group; **không dùng raw Bearer token làm key**.

Cleanup theo prefix:

~~~text
prefix = "it:" + testRun + ":"
SCAN theo prefix + "*", xóa theo batch từng key đã xác minh
đảm bảo background writers không tiếp tục tạo key
không gọi KEYS * hoặc FLUSHALL trên shared Redis
~~~

SCAN không phải snapshot nguyên tử; khi worker vẫn chạy, key có thể được tạo trong lúc cleanup. Chặn writer hoặc hủy container riêng mới đảm bảo trạng thái cuối.

**Cache HTTP** còn có ETag, If-None-Match, Cache-Control, Vary: test 304 chỉ hợp lệ với representation/validator đúng của caller và tenant, không dùng dữ liệu cached của tenant B cho A.

## 12. Broker, outbox và tài nguyên ngoài database

Test transactional outbox có thể để lại **order row, outbox event, inbox record và message**. Sau khi test dọn DB, relay vẫn có thể publish tiếp làm consumer tạo dữ liệu mới. Vì vậy cần **quiesce → verify → cleanup**, hoặc dùng môi trường dùng một lần.

| Thành phần | Chiến lược |
| --- | --- |
| Broker Kafka/RabbitMQ | Instance dùng một lần hoặc topic/queue có prefix testRun |
| Consumer group | Group riêng per suite, không reuse offsets |
| EventId | Một ID cho một fact; **redelivery giữ nguyên ID** |
| Inbox dedup | Database riêng hoặc cleanup theo consumer/testRun |
| DLQ | Queue test, quyền và retention riêng |
| Scheduled relay | Dừng/await bounded trước khi dọn |
| Object storage | Bucket test hoặc prefix run ID, cleanup có xác minh |
| Mock HTTP server | Reset stubs/request journal sau mỗi test |

Không assert Kafka **offset cố định**, vì offset phụ thuộc lịch sử topic. Assert theo **eventId, aggregate ID/version và side effect cuối cùng**. Với async, dùng Awaitility thay Thread.sleep:

~~~java
await().atMost(Duration.ofSeconds(10))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> assertThat(inventoryRepository
        .countReservationsFor(orderId)).isEqualTo(1L));
~~~

Cần dependency Awaitility và consumer đang chạy. Khi timeout, in diagnostics **eventId, trạng thái outbox, attempts, consumer lag/error category**, không dump token/PII. Không tăng timeout vô hạn để che lỗi thiết kế.

### Test duplicate delivery

~~~text
1. Seed order + outbox event E đã commit.
2. Relay gửi E; consumer insert inbox(E) và reserve hàng.
3. Consumer DB commit nhưng ACK broker bị mất.
4. Gửi lại E; consumer nhìn inbox(E) và không reserve lần hai.
5. Assert inbox(E) = 1, reservation(order) = 1.
6. Cleanup DB và topic theo cùng test-run ID.
~~~

Nếu consumer gọi Payment API hoặc gửi email **ngoài** transaction của inbox, cần idempotency ở downstream hoặc outbox tiếp; marker inbox đơn thuần không đảm bảo side effect ngoài DB chỉ chạy một lần.

### Mock external services và file

- Dùng **WireMock/MockWebServer** cho 200/404/429/503, timeout, malformed JSON và retry; reset stubs và recorded requests.
- CI không nên gọi API thanh toán, SMS/email hoặc provider thật. Cho phép outbound test chỉ tới host allowlist và dùng credential sandbox.
- Với file, dùng JUnit **@TempDir** hoặc object prefix cô lập. Cleanup phải xác minh path thuộc test root; không xóa thư mục cha suy đoán từ input.
- Với API sandbox ngoài quyền kiểm soát, sinh external reference riêng, rate limit và dùng chính cleanup API của sandbox, không tạo tác dụng phụ trên người dùng.

## 13. Fixture bảo mật và phân quyền đa tenant

Dữ liệu cần có **ít nhất hai principals, hai tenants, scopes khác nhau, một resource ngoài quyền**. Chỉ test bằng admin mọi quyền sẽ bỏ lọt BOLA/IDOR và cache trộn tenant.

~~~java
@Test
void tenantCannotReadOtherTenantOrder() throws Exception {
    mockMvc.perform(get("/api/v1/orders/{id}", orderOfTenantB)
            .with(jwt()
                .jwt(j -> j.subject("buyer-a")
                    .claim("tenant_id", "tenant-a"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders:read"))))
        .andExpect(status().isNotFound());
}
~~~

**jwt() trong spring-security-test tạo Authentication giả**, không kiểm tra chữ ký, issuer, audience và expiry. Để test decoder, dùng Bearer token **được ký bằng test key**, mock JWKS/introspection server, assert 401 và WWW-Authenticate với token sai. Không tắt SecurityFilterChain để mọi test được 200.

Security fixture cũng phải có state cho CSRF/session khi dùng cookie; với Bearer-only API, cần test preflight OPTIONS không có token và POST thật thiếu token trả 401. Test hai caller xen kẽ để phát hiện token/tenant bị giữ sai trong singleton.

Không ghi access token hoặc data cá nhân vào HTTP snapshot/log CI; dùng mã lỗi ổn định, không so nguyên chuỗi lỗi có thể bản địa hóa.

## 14. Parallel CI: cô lập trước khi tăng concurrency

Nếu test A đang INSERT order trong cùng database mà test B chạy **TRUNCATE**, kết quả chập chờn là tất yếu. Phân chia:

| Phạm vi chạy | Ranh giới cần độc lập |
| --- | --- |
| CI jobs/shards | Database/container/queue namespace và credentials riêng |
| JVM forks | Schema/database/key prefix riêng, hoặc suite sequential |
| Classes dùng context cache | Không mutate global bean/test singleton |
| Parallel methods | Fixture per method, không cleanup toàn DB của nhau |
| Async worker | Correlation/operation scope, stop/await trước cleanup |

**Phương án thực dụng:** cho unit/slice tests chạy parallel; nhóm integration tests dùng cleanup toàn DB chạy sequential **bên trong mỗi job**, nhưng nhiều jobs có thể chạy song song nếu mỗi job có container riêng. Khi chứng minh được namespace/dedup và cleanup không đụng chéo mới tăng parallelism.

JUnit 5 **@ResourceLock** chỉ điều phối trong một JVM/JUnit engine, **không khóa được** database của hai CI runners độc lập. @DirtiesContext làm chậm context startup và **không reset broker/database dùng chung**. Tránh biến cả suite thành serial chỉ để che một shared fixture không có owner.

## 15. Thiết kế pipeline CI tái lập và an toàn

Một pipeline đáng tin phải khởi động từ **schema đúng version, test data đã được kiểm soát, môi trường độc lập và toolchain xác định**. Nó cần cho biết **thất bại nào thuộc code, dữ liệu, cơ sở hạ tầng hoặc timeout**, không chỉ hiện “test failed”.

Luồng đề xuất:

~~~mermaid
flowchart TD
    A[Checkout đúng commit] --> B[Khóa JDK, build tool, dependency versions]
    B --> C[Unit tests không cần DB]
    C --> D[Khởi động Testcontainers / mock servers]
    D --> E[Migration schema]
    E --> F[Seed fixture theo test]
    F --> G[HTTP, security, integration, concurrency tests]
    G --> H[Kiểm tra leak và assert cleanup]
    H --> I[Hủy container và test resources]
    I --> J[Archive reports và diagnostics đã redaction]
~~~

Một GitHub Actions workflow minh họa phần test nhanh (container runtime của runner vẫn phải được kiểm chứng):

~~~yaml
name: REST tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    timeout-minutes: 25
    env:
      SPRING_PROFILES_ACTIVE: test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle
      - name: Unit and standard integration tests
        run: ./gradlew --no-daemon test
~~~

**Lưu ý:** bài này **không chạy Gradle hay tạo workflow**. Nếu dự án tách task **integrationTest**, phải định nghĩa test suite/task trong build rồi thêm vào pipeline; không giả định task đó tự tồn tại. Đặt build timeout phù hợp, pin phiên bản dependencies/container images; nếu cần bảo đảm supply chain chặt hơn, dùng **action SHA pinning**, image digest và permission tối thiểu.

### Dữ liệu và secrets trong CI

- CI dùng **test-only credentials và isolated endpoints**, không dùng production secrets trong pull requests không tin cậy.
- Mỗi job/shard có database, Redis namespace, broker group và object prefix riêng. **Run ID không phải một secret**, nhưng cần được validate.
- Container startup phải có timeout rõ, không chuyển sang DB dùng chung khi Docker không hoạt động.
- Đảm bảo teardown ngay cả khi test fail, nhưng không kỳ vọng teardown chạy sau **runner kill**; dùng hạ tầng dùng một lần và TTL cleanup cho artifacts.
- Báo cáo test/log cần **redact Authorization, cookie, token, PII**, đồng thời hạn chế retention và quyền download.
- Không dump toàn bộ PostgreSQL tables hay raw broker payload vào public CI artifact để debug.
- Nếu dùng seed xuất phát từ môi trường thật, bắt buộc có chính sách **ẩn danh dữ liệu** và chấp thuận riêng; lựa chọn mặc định vẫn là synthetic fixtures.

### Bảo đảm tính tái lập ở máy cá nhân

Cùng test nên có cách chạy lại từ **cùng commit, cùng JDK/dependency và cùng container image**, với input fixture được version. Ghi CI run ID, test class/method, seed của random generator, database/schema version và broker topic **mà không ghi secret**. Một lỗi chỉ xuất hiện khi chạy full suite thường là dấu hiệu **shared state**; đừng sửa bằng cách thêm sleep hoặc chạy lại test ba lần.

## 16. Phân tích flaky test theo nguyên nhân

| Dấu hiệu | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Chạy một test pass, cả suite fail | Fixture shared, order dependency | Chạy đảo thứ tự, assert setup/cleanup |
| 409 ngẫu nhiên với POST | External reference/idempotency key trùng | Kiểm tra tenant/key, unique DB, test namespace |
| 429 khi chỉ test GET | Rate limiter cache chưa reset | Kiểm tra prefix/key/TTL và identity |
| 404 ngay sau tạo 201 | Async transaction/replica/cache | Đọc primary DB, await bounded, kiểm tra consistency |
| Duplicate outbox event | Retry/ack-loss, dedup sai | So eventId và business state, chạy fault injection |
| Invalid JWT bất chợt | Token hết hạn, key/time skew | Fixed clock/issuer, test JWKS rotation |
| CI fail nhưng local pass | PostgreSQL/locale/timezone/JDK khác | Pin versions, export safe metadata |
| Cleanup treo | Worker giữ DB lock, @Sql isolated conflict | Kiểm tra active transactions/locks, stop worker |
| Random port conflict | Dùng fixed port hoặc shared mock server | RANDOM_PORT, ephemeral ports, per-test server |
| Test leak file/cache | Cleanup chỉ dọn PostgreSQL | Inventory mọi external side effect |
| Rollback test pass, production fail | Lỗi ở commit hoặc HTTP server thread khác | Real HTTP + commit test + DB readback |

**Debug theo hướng invariant:** trước test assert fixture/row count dự kiến, sau test assert kết quả và không còn data của run cũ ở phạm vi test sở hữu. Giữ lại **diagnostics an toàn** trong một khoảng ngắn để phân tích, không sửa bằng cách vô điều kiện tăng timeout, thêm retry hay xóa bớt assertions.

Với lỗi tranh chấp, có thể chạy cùng suite nhiều lần hoặc đảo thứ tự **trong môi trường cô lập** để tái hiện; một lần pass không chứng minh hết flaky. Khi mô phỏng crash/failover, phân biệt “test đã chủ động gây lỗi” với “runtime bên ngoài thực sự mất ổn định” bằng logs có correlation ID.

## 17. Ma trận xác minh tính sạch và đúng của REST API

| Phép thử | Điều kiện dữ liệu đầu vào | Bằng chứng cần có |
| --- | --- | --- |
| GET 200 | Entity tenant A tồn tại | DTO/status, đúng tenant |
| GET 404 | ID không có, hoặc ngoài quyền | Không lộ owner/tài nguyên khác |
| POST 201 | Cart/addr hợp lệ | Một order + một outbox đã commit |
| POST 400 | Field JSON thiếu/sai | Không ghi business data |
| POST 401/403 | Thiếu auth/scope | Không ghi order/idempotency/outbox |
| POST 409 | Cùng key khác fingerprint | Không có event/row mới |
| Retry cùng key/payload | Có kết quả lưu trước | Replay cùng order, count outbox = 1 |
| PATCH 412 | ETag/revision stale | Không ghi đè |
| GET 304 | Validator đúng cho caller | Không body, cache theo hợp đồng |
| Rate 429 | Bucket của principal đã cạn | Retry-After hợp lệ, user khác không bị ảnh hưởng |
| Broker ACK mất | Event đã publish, producer chưa biết | Redelivery cùng eventId, side effect = 1 |
| Consumer lỗi trước commit | Inbox và change rollback | Retry xử lý lại được |
| Parallel CI shards | Mỗi job một namespace/database | Không phụ thuộc thứ tự, không truncate chéo |
| Redis broker unavailable | Failure policy rõ | Không infinite retries hoặc chuyển unlimited |
| Test bị kill giữa chừng | Run cũ có thể còn artifact | New run vẫn độc lập, TTL/reaper dọn về sau |
| Cleanup hoàn tất | Quiesced workers, owned data | Không còn fixture của test trong tài nguyên reused |

Không dựa hoàn toàn vào HTTP status để kết luận dữ liệu đã commit. Với transaction/async, luôn có **readback state** từ nguồn chân lý và test lỗi tại ranh giới. Bài yêu cầu kiểm tra cả **negative scenarios**, không chỉ happy path.

## 18. Bài tập: biến bộ kiểm thử Orders API thành hermetic CI

Giả sử bộ test cũ có các vấn đề: tất cả test dùng database **orders_dev**, user/cart ID cố định, toàn class dùng @Transactional, một test gửi HTTP qua RANDOM_PORT, Redis còn key cũ, một consumer Kafka chạy nền, và CI có 4 shards. Thỉnh thoảng POST tạo đơn trả 409 hoặc GET bị 429 khi chạy cả suite.

Thực hành:

1. Lập **inventory mọi state**: PostgreSQL tables/transactions, idempotency, outbox, inbox, Redis, Kafka, file, time, static variables và external APIs.
2. Chọn boundary cho **unit, MVC slice, repository, HTTP integration và async integration**. Nêu phần nào cần PostgreSQL thật và phần nào có thể dùng mock.
3. Dựng PostgreSQL Testcontainers, chạy migration giống production, tạo fixture **tenant A/B** và factory Order/Cart/Address tối thiểu.
4. Viết **reset-before** hoặc cách dùng database/schema dùng một lần; chứng minh cleanup chỉ tác động môi trường test và không phá test shard khác.
5. Dùng **Clock.fixed** để test ETag/cache expiry hoặc thời gian đơn; với JWT, có test decoder riêng và token test được ký.
6. Viết HTTP test 201 và readback database, rồi 400/401/403/404/409/412; chứng minh không có outbox event khi request bị từ chối.
7. Viết test retry Idempotency-Key và consumer redelivery, assert **business side effect = 1** dưới concurrency và broker ACK-loss.
8. Cho CI chạy 4 shards với namespace riêng; test kill/restart một shard, kiểm tra job còn lại không bị ảnh hưởng và artifacts cũ có TTL cleanup.
9. Lập dashboard report flaky/error/latency, ghi run ID và schema version nhưng **không ghi token/PII**.
10. So sánh thời gian CI và tỷ lệ flaky trước–sau: có thể nhanh hơn bằng context/container reuse **nếu vẫn chứng minh isolation**.

**Sản phẩm nộp:** test data plan, fixture factory, SQL/migration strategy, Spring/JUnit tests, test resource lifecycle, CI workflow và ma trận trước–sau chứng minh kết quả độc lập.

## 19. Checklist và kết luận

- **Dữ liệu đầu vào:** fixture ít, synthetic, rõ scenario, có ownership và không phụ thuộc test khác.
- **Schema:** dùng migration đúng version, không tự sửa database dev bằng tay.
- **Isolation:** chọn rõ rollback, scoped cleanup hoặc database/container dùng một lần.
- **Commit:** kiểm tra HTTP thực và async ở transaction boundary đúng; không tin test-level rollback có thể dọn tất cả.
- **Ngoài DB:** Redis, broker, cache, file, external mocks, worker đều có lifecycle riêng.
- **Thời gian/ID:** Clock/Random/namespace được kiểm soát, không assert auto-increment/offset ngẫu nhiên.
- **Bảo mật:** hai tenant, đúng quyền, JWT issuer/audience test; không dùng dữ liệu production hay lộ secrets trong CI.
- **Song song:** mỗi shard có tài nguyên độc lập; không truncate/FLUSHALL trên tài nguyên chia sẻ.
- **Dọn sạch:** reset-before, teardown/TTL, kiểm soát process bị kill và xác minh không còn fixture trong phạm vi sở hữu.
- **Tái lập:** cùng commit + toolchain + migration + seed đưa tới cùng invariant; failures có diagnostics an toàn.

**Kết luận:** Quản lý dữ liệu kiểm thử là một phần thiết kế hệ thống, không phải vài dòng xóa bảng sau @Test. Một bộ REST API tests đáng tin cần **fixture có mục đích, ranh giới isolation đúng transaction/hạ tầng, dọn sạch có chủ sở hữu, clock và namespace tái lập, cùng CI không chia sẻ state**. Khi các điều kiện đó được chứng minh, test mới có thể bảo vệ các hợp đồng HTTP, quyền truy cập và tính nhất quán nghiệp vụ mà không bị phụ thuộc thứ tự chạy.





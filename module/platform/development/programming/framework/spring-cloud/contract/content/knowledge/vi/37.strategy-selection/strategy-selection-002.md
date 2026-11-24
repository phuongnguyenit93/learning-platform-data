# Khi kiểm thử tích hợp hoặc end-to-end phù hợp hơn

## Mục tiêu học tập

**Spring Cloud Contract** giúp producer và consumer thống nhất hành vi HTTP hoặc messaging bằng **Groovy/YAML DSL**. Producer dùng contract để sinh test kiểm chứng implementation; consumer dùng stub artifact và **Stub Runner** để kiểm tra client/handler với hành vi provider đã công bố.

Tuy nhiên, contract test không chứng minh toàn bộ hệ thống hoạt động đúng khi database, broker, gateway, authentication, network và nhiều service cùng tham gia. Có những câu hỏi chỉ **integration test** hoặc **end-to-end (E2E) test** mới trả lời đáng tin cậy.

Bài thuộc chương **Lựa chọn chiến lược**, tập trung vào câu hỏi **khi nào kiểm thử tích hợp hoặc end-to-end phù hợp hơn**. Sau bài, bạn có thể:

- Phân biệt contract test, integration test và E2E test theo ranh giới mà mỗi loại kiểm chứng.
- Nhận biết khi nào generated producer tests và consumer stubs là đủ.
- Chọn integration test khi cần xác minh database, transaction, security filter, serialization, broker, retry, outbox hoặc nhiều component phối hợp.
- Chọn E2E khi cần xác minh workflow nghiệp vụ xuyên qua gateway và nhiều service trong môi trường gần production.
- Kết hợp Spring Cloud Contract với Spring Boot Test, Testcontainers và môi trường kiểm thử có kiểm soát.
- Tránh biến E2E thành suite duy nhất hoặc dùng stub để che lỗi ở hạ tầng thật.
- Thiết kế test strategy phù hợp với độ rủi ro, chi phí và thời gian phản hồi.

> **Nguyên tắc lựa chọn:** dùng tầng kiểm thử nhỏ nhất có thể chứng minh rủi ro đang quan tâm. Khi rủi ro nằm ở sự phối hợp giữa các thành phần thật, integration hoặc E2E phù hợp hơn việc chỉ kiểm tra một contract boundary bằng stub.

## 1. Tình huống: contract đã PASS nhưng đơn hàng vẫn không hoàn tất

Giả sử hệ thống thương mại điện tử có:

- **Checkout Service:** nhận yêu cầu đặt hàng.
- **Inventory Service:** giữ hàng.
- **Payment Service:** thu tiền.
- **Order Service:** ghi nhận trạng thái đơn.
- **Message broker:** phát sự kiện để các service phối hợp.
- **API Gateway:** định tuyến request và áp dụng authentication.

Contract giữa Checkout và Inventory mô tả:

~~~http
POST /api/inventory/reservations HTTP/1.1
Content-Type: application/json

{"sku":"SKU-101","quantity":2}
~~~

Inventory trả:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json

{"reservationId":"RSV-1001","status":"ACTIVE"}
~~~

Producer contract tests PASS. Consumer tests cũng PASS khi Checkout gọi stub do Stub Runner cung cấp.

Nhưng trong production-like environment, đơn hàng vẫn thất bại vì:

- Transaction ghi reservation đã commit nhưng message không được publish.
- Checkout và Inventory dùng sai broker topic.
- Database constraint từ chối SKU khi dữ liệu thực tế khác fixture.
- Gateway bỏ header authentication mà service yêu cầu.
- Payment timeout khiến workflow giữ hàng nhưng không giải phóng reservation.
- Order Service nhận event nhưng deserialize sai phiên bản schema.

**Contract tests có thể vẫn PASS** vì chúng chỉ chứng minh những tương tác đã được mô tả ở boundary. Chúng không tự động xác minh transaction, broker topology, gateway hay toàn bộ workflow.

Đây là lúc cần thêm **integration test** hoặc **E2E test**.

## 2. Ba loại kiểm thử trả lời ba câu hỏi khác nhau

| Loại kiểm thử | Câu hỏi chính | Ranh giới điển hình | Thành phần thật |
|---|---|---|---|
| **Contract test** | Hai service có tuân thủ giao diện đã thỏa thuận không? | Một provider-consumer boundary | Producer implementation hoặc consumer + stub |
| **Integration test** | Các component thực có phối hợp đúng không? | Một service và dependencies, hoặc nhóm component | DB, broker, web stack, adapter, service |
| **End-to-end test** | Người dùng/hệ thống có hoàn thành workflow qua các service không? | Từ entry point đến kết quả nghiệp vụ | Nhiều service và hạ tầng gần production |

### Contract test với Spring Cloud Contract

Có hai hướng chính:

1. **Producer verification:** contract DSL sinh test để gọi provider implementation và kiểm tra response/message theo kỳ vọng.
2. **Consumer-side stub test:** consumer dùng stub artifact qua Stub Runner để kiểm tra client/handler với hành vi provider đã công bố.

Contract test phát hiện **drift giữa producer và consumer** mà không phải khởi động toàn bộ hệ thống trong mỗi lần chạy.

### Integration test

Integration test đặt các thành phần thật vào cùng một scenario. Ví dụ:

- Spring controller thật → service thật → PostgreSQL thật trong Testcontainers.
- Application service → transactional outbox → Kafka broker thật.
- Consumer listener → message converter → database projection.
- Security filter chain → JWT decoder/test identity → endpoint.

Test có thể mock một dependency ngoài phạm vi, nhưng các ranh giới đang được xác minh phải được chạy thật.

### End-to-end test

E2E kiểm tra workflow qua nhiều service, thường bắt đầu ở public API/UI/gateway và kết thúc ở trạng thái nghiệp vụ có thể quan sát.

Ví dụ: gửi yêu cầu checkout, giữ hàng, thanh toán, nhận xác nhận đơn hàng và kiểm tra kết quả cuối cùng.

E2E không nhất thiết phải chạy toàn bộ production infrastructure, nhưng môi trường phải đủ gần để kiểm chứng các ranh giới mà test cam kết.

## 3. Contract test không phải integration test thu nhỏ

Một consumer test dùng Stub Runner có thể trông giống integration test:

~~~java
@SpringBootTest
@AutoConfigureStubRunner(
    ids = "com.example:inventory-producer:2.3.0:stubs:0",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class CheckoutInventoryClientContractTest {
    // Client của Checkout gọi HTTP stub.
}
~~~

Test có thể khởi tạo Spring context và client thật của Checkout. Nhưng Inventory vẫn được thay bằng **stub**, nên test không xác minh:

- Inventory controller đang deploy.
- Database Inventory và transaction của nó.
- Inventory security/filter chain.
- Broker hoặc downstream dependency của Inventory.
- Network, DNS, gateway và deployment routing giữa hai service.

Nó là consumer-side contract/stub test, không phải kiểm thử tích hợp thật giữa Checkout và Inventory.

Tương tự, producer generated test có thể chạy provider implementation trong MockMvc hoặc test mode khác, nhưng điều đó không mặc nhiên chứng minh database, broker và service phụ trợ đã được tích hợp.

**Tên annotation hoặc việc dùng `@SpringBootTest` không tự quyết định loại test.** Hãy nhìn dependency nào là thật, dependency nào là stub/mock, và assertion đang chứng minh ranh giới nào.

## 4. Quy tắc chọn tầng kiểm thử

Dùng các câu hỏi sau để chọn test:

1. **Rủi ro có nằm ở một HTTP/message boundary đã được contract mô tả?** Contract test thường là lựa chọn trực tiếp và nhanh.
2. **Kết quả phụ thuộc phối hợp nhiều component thật trong một service?** Chọn integration test.
3. **Lỗi chỉ xuất hiện khi nhiều service, gateway, broker và quy trình nghiệp vụ cùng hoạt động?** Cần E2E hoặc integration test ở cấp hệ thống.
4. **Cần xác minh transaction, isolation, commit/rollback hoặc constraint?** Dùng database integration test với DB thật phù hợp.
5. **Cần xác minh message được publish/consume, retry, ordering hoặc dead-letter?** Dùng messaging integration test với broker/binder phù hợp; nếu workflow xuyên service, bổ sung E2E.
6. **Chỉ cần bảo đảm consumer chấp nhận response đúng contract?** Stub Runner test thường đủ; không cần dựng provider thật chỉ để lặp lại assertion.
7. **Cần chứng minh một hành trình người dùng hoàn chỉnh?** Chọn một số E2E scenario quan trọng, không biến mọi case dữ liệu thành E2E.

### Ma trận quyết định nhanh

| Nhu cầu xác minh | Contract | Integration | E2E |
|---|---:|---:|---:|
| HTTP method/path/status/body | **Rất phù hợp** | Có thể | Có thể |
| Producer response đáp ứng DSL | **Rất phù hợp** | Có thể | Không phải lựa chọn đầu |
| Consumer xử lý stub response | **Rất phù hợp** | Có thể | Có thể |
| SQL constraint/transaction | Không đủ | **Rất phù hợp** | Có thể nhưng khó chẩn đoán |
| Spring security filter chain | Có thể kiểm một phần | **Rất phù hợp** | Có thể |
| Broker delivery/ack/retry | Message contract hỗ trợ một phần | **Rất phù hợp** | Khi cần workflow xuyên service |
| Gateway routing/DNS/TLS | Không đủ | Có thể ở gateway integration | **Rất phù hợp** |
| Nhiều service phối hợp workflow | Không đủ một mình | Có thể theo nhóm | **Rất phù hợp** |
| User journey quan trọng | Không đủ | Có thể | **Rất phù hợp** |

Đây là hướng dẫn lựa chọn, không phải ranh giới cứng. Một test có thể kết hợp nhiều kỹ thuật; điều quan trọng là ghi rõ nó xác minh điều gì.

## 5. Khi integration test phù hợp hơn: database và transaction

Contract mô tả request/response không tự chứng minh dữ liệu được ghi đúng vào database hoặc transaction được commit/rollback đúng.

Ví dụ reservation cần:

1. Đọc tồn kho.
2. Kiểm tra số lượng có thể bán.
3. Tạo reservation.
4. Cập nhật lượng đã giữ.
5. Ghi outbox event trong cùng transaction.

Contract test với response `201` có thể PASS trong khi bước 3 hoặc 5 bị lỗi nếu test base class mock service.

### Những câu hỏi cần database integration test trả lời

- Entity được persist với đúng relationship và column mapping không?
- Unique constraint ngăn duplicate reservation không?
- Transaction rollback khi một thao tác giữa chừng fail không?
- Isolation level có cho phép oversell khi hai request đồng thời không?
- Migration hiện tại có tương thích schema không?
- Optimistic/pessimistic locking có hành vi mong muốn không?
- Outbox row và business row có commit nguyên tử không?

### Ví dụ service có transaction

~~~java
@Service
public class ReservationService {

    private final InventoryRepository inventoryRepository;
    private final ReservationRepository reservationRepository;
    private final OutboxRepository outboxRepository;

    @Transactional
    public Reservation reserve(String sku, int quantity) {
        Inventory item = inventoryRepository.findBySkuForUpdate(sku)
            .orElseThrow(() -> new SkuNotFoundException(sku));

        if (item.availableToSell() < quantity) {
            throw new InsufficientStockException(sku);
        }

        item.reserve(quantity);

        Reservation reservation =
            reservationRepository.save(
                Reservation.create(sku, quantity)
            );

        outboxRepository.save(
            OutboxEvent.stockReserved(reservation)
        );

        return reservation;
    }
}
~~~

Đây là ví dụ minh họa; repository/entity/locking method cần được định nghĩa trong ứng dụng.

Contract test có thể xác minh endpoint trả `201` và schema response. Integration test cần xác minh **inventory update, reservation row và outbox row** được ghi đúng trong cùng transaction.

### Vì sao dùng DB thật trong test?

Mock repository có thể chứng minh service gọi `save()`, nhưng không chứng minh:

- SQL thực chạy được.
- Constraint có hiệu lực.
- Transaction boundary hoạt động.
- Locking/isolation được database thực thi.
- Migration tạo schema đúng.

Dùng Testcontainers với engine database tương thích production thường cho bằng chứng tốt hơn H2 khi behavior phụ thuộc PostgreSQL/MySQL-specific features.

## 6. Ví dụ database integration test với Testcontainers

Ví dụ giả định dự án dùng Spring Boot, Spring Data JPA, PostgreSQL và Testcontainers JUnit integration. Dependency/version cần được quản lý theo BOM tương thích.

~~~java
@Testcontainers
@SpringBootTest
class ReservationDatabaseIT {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    ReservationService reservationService;

    @Autowired
    InventoryRepository inventoryRepository;

    @Autowired
    ReservationRepository reservationRepository;

    @Autowired
    OutboxRepository outboxRepository;

    @Test
    void reservationAndOutboxArePersisted() {
        inventoryRepository.save(
            Inventory.withStock("SKU-101", 10, 2)
        );

        Reservation reservation =
            reservationService.reserve("SKU-101", 2);

        assertThat(reservation.getId()).isNotNull();
        assertThat(inventoryRepository.findBySku("SKU-101"))
            .get()
            .extracting(Inventory::availableToSell)
            .isEqualTo(6);
        assertThat(reservationRepository.findById(reservation.getId()))
            .isPresent();
        assertThat(outboxRepository.findByAggregateId(reservation.getId()))
            .isNotEmpty();
    }
}
~~~

Ví dụ dùng factory/repository method minh họa; điều chỉnh theo domain model thực tế. Test cần migration/schema initialization, cleanup và transaction setup rõ ràng.

### Assertions nên tập trung vào invariant

~~~text
availableToSell = stockOnHand - reserved
reservation.quantity = requested quantity
outbox.aggregateId = reservation.id
business row and outbox row commit together
~~~

Nếu yêu cầu là atomicity, thêm test ép một thao tác sau khi cập nhật inventory fail và xác minh transaction rollback cả business row lẫn outbox row.

**Không dùng mock outbox repository trong test được tuyên bố là xác minh transaction giữa business state và outbox.**

## 7. Khi transaction rollback là trọng tâm

Contract có thể mô tả status/error body khi request thất bại. Nhưng contract không xác minh trạng thái database sau lỗi.

Ví dụ khi outbox insert bị lỗi:

~~~text
Before:
  SKU-101 stockOnHand = 10
  reserved = 2

Attempt:
  reserve SKU-101 quantity = 3
  update inventory succeeds
  insert outbox fails

Expected after rollback:
  reserved = 2
  no reservation row
  no outbox row
~~~

Integration test cần:

1. Dùng database thật với transaction manager thật.
2. Seed baseline.
3. Tạo failure có kiểm soát ở bước outbox (ví dụ constraint/DB fault).
4. Gọi service transaction.
5. Xác minh exception được phát ra.
6. Đọc lại database trong transaction/session mới.
7. Xác minh mọi thay đổi được rollback.

Nếu chỉ kiểm tra exception từ mock, test không chứng minh rollback. Nếu đọc lại trong cùng persistence context/cache, có thể nhìn thấy entity state cũ; cần flush/clear hoặc transaction mới phù hợp.

## 8. Khi concurrency và locking là rủi ro

Một contract HTTP request đơn lẻ không thể chứng minh hệ thống không oversell khi hai request đến đồng thời.

~~~text
Initial available stock = 5

Request A reserves 4
Request B reserves 4

Expected:
  at most one reservation succeeds
  final reserved quantity <= 5
  no negative available stock
~~~

Integration test có thể dùng hai transaction/thread cùng chờ barrier rồi gọi service đồng thời. Sau đó kiểm tra database invariant.

Điều cần cẩn thận:

- Dùng database engine thực tương thích production.
- Đồng bộ thời điểm bắt đầu request thay vì dùng sleep.
- Không chia sẻ EntityManager/session giữa thread.
- Dùng timeout hữu hạn và dọn dữ liệu.
- Assert kết quả nghiệp vụ cuối cùng, không phụ thuộc request nào thắng.
- Lặp lại trong test chuyên biệt nếu race hiếm; không dựa vào một lần chạy.

Contract test vẫn hữu ích để xác minh response success/conflict đã thống nhất. Integration test kiểm tra locking/transaction thực.

## 9. Khi security filter chain và identity thật quan trọng

Contract có thể mô tả header/token assumptions hoặc response 401/403. Nhưng consumer stub không chứng minh authentication/authorization cấu hình đúng trong service.

Integration test phù hợp khi cần xác minh:

- JWT decoder kiểm tra signature/issuer/audience.
- Spring Security filter chain áp dụng đúng matcher.
- Role/scope được map đúng thành authority.
- Method security chặn thao tác trái phép.
- CSRF/CORS/session behavior đúng.
- Service-to-service authentication hoạt động với identity phù hợp.

### Ví dụ security integration test

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class InventorySecurityIT {

    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousRequestIsRejected() throws Exception {
        mockMvc.perform(get("/api/inventory/SKU-101"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void inventoryReaderCanReadStock() throws Exception {
        mockMvc.perform(
                get("/api/inventory/SKU-101")
                    .with(jwt().authorities(
                        new SimpleGrantedAuthority("SCOPE_inventory.read")
                    ))
            )
            .andExpect(status().isOk());
    }
}
~~~

Đây là ví dụ Spring Security test support. Nó xác minh filter chain/authorization behavior trong context test, nhưng `jwt()` thường tạo authentication bằng test support; **không nhất thiết kiểm chứng xác minh chữ ký JWT từ issuer thật**.

Nếu rủi ro nằm ở key rotation, JWKS endpoint, issuer/audience hoặc TLS giữa service và identity provider, cần integration test bổ sung với test issuer/JWKS hoặc môi trường xác minh được kiểm soát.

### Khi nào E2E cần thiết?

Nếu mục tiêu là xác minh người dùng đăng nhập qua API Gateway, token được truyền qua gateway và nhiều service, E2E qua gateway phù hợp hơn. Một test filter chain đơn lẻ không kiểm tra routing/forwarded headers của cả hệ thống.

## 10. Khi serialization và framework integration là trọng tâm

Contract kiểm tra schema và matcher ở boundary. Nhưng lỗi có thể xuất hiện khi framework components phối hợp:

- Jackson module/custom serializer không được đăng ký.
- Enum naming strategy khác giữa application và test.
- `JavaTimeModule` hoặc timezone config thiếu.
- Content negotiation chọn sai media type.
- Validation annotations không chạy qua đúng request pipeline.
- Global exception handler chuyển exception thành body/status sai.
- Multipart/binary body hoặc compression khác behavior.
- Message converter không đọc được payload/header.

Nếu producer generated test dùng test mode không khởi tạo đầy đủ web stack, integration test với Spring application context thật có thể cần thiết.

### Ví dụ kiểm tra JSON qua HTTP stack

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class InventoryHttpSerializationIT {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void returnsExpectedJsonTypes() {
        ResponseEntity<JsonNode> response =
            restTemplate.getForEntity(
                "/api/inventory/SKU-101",
                JsonNode.class
            );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody().path("sku").asText())
            .isEqualTo("SKU-101");
        assertThat(response.getBody().path("available").isBoolean())
            .isTrue();
        assertThat(response.getBody().path("quantity").isIntegralNumber())
            .isTrue();
    }
}
~~~

Test chạy HTTP server và serialization/deserialization stack trong Spring context. Nó không tự kiểm tra gateway hoặc deployment network bên ngoài process.

**Lựa chọn test mode:** dùng MockMvc/WebApplicationContext hoặc random-port HTTP tùy rủi ro. Không phải mọi contract đều cần mở TCP port; nhưng nếu bug nằm ở server connector, servlet filter, compression hoặc HTTP stack thật, test qua server phù hợp hơn.

## 11. Khi messaging delivery, retry và dead-letter là rủi ro

Message contract có thể xác minh payload, headers, destination/label và generated producer behavior trong test setup. Nhưng nó không tự bảo đảm broker vận hành đúng.

Integration test với broker thật hoặc broker test container phù hợp khi cần xác minh:

- Message thực được publish vào đúng topic/queue.
- Consumer group nhận đúng message.
- Acknowledgment/offset/ack mode đúng.
- Retry policy và backoff hoạt động.
- Dead-letter queue nhận message sau số lần retry.
- Ordering/partition key được bảo đảm trong phạm vi broker.
- Serialization/schema registry integration đúng.
- Transactional publishing/consumer acknowledgment.
- Redelivery không tạo duplicate side effects ngoài mong muốn.

### Ví dụ workflow message

~~~mermaid
sequenceDiagram
    participant API as Inventory API
    participant DB as PostgreSQL
    participant O as Outbox publisher
    participant K as Kafka
    participant C as Checkout consumer
    API->>DB: Update stock + insert outbox
    O->>DB: Read pending outbox
    O->>K: Publish StockChanged
    K->>C: Deliver event
    C->>DB: Update checkout projection
    C-->>K: Commit offset/ack
~~~

Contract test có thể xác minh shape của `StockChanged`. Integration test cần xác minh **publish/delivery/ack** qua broker và persistence thực.

### Khi E2E tốt hơn?

Nếu yêu cầu là khi một đơn hàng được checkout thì event StockChanged phải cập nhật projection trong Reporting Service, đó là workflow xuyên nhiều service. Có thể dùng integration tests riêng cho publisher và consumer, cộng một E2E scenario xác minh luồng nghiệp vụ trọng yếu.

Không nhất thiết mọi message schema đều cần E2E. Dùng contract test cho schema/boundary và integration test cho broker mechanics.

## 12. Khi retry, timeout và resilience behavior là trọng tâm

Stub có thể trả 500/timeout giả lập để kiểm tra consumer client xử lý lỗi. Nhưng stub response đơn giản không chứng minh toàn bộ resilience configuration trong runtime.

Integration test phù hợp để kiểm tra:

- HTTP client timeout thật được áp dụng.
- Retry có giới hạn và chỉ retry lỗi phù hợp.
- Circuit breaker chuyển trạng thái đúng.
- Bulkhead/connection pool có giới hạn.
- Fallback không che lỗi dữ liệu hoặc business rejection.
- Idempotency key ngăn side effect lặp.
- Cancellation/timeout không để transaction dang dở.

| Câu hỏi | Tầng phù hợp |
|---|---|
| Consumer xử lý response 503 theo contract ra sao? | Consumer contract/stub test |
| HTTP client thực có timeout/retry/circuit breaker đúng cấu hình không? | Integration test với controllable server |
| Khi Payment chậm, toàn bộ checkout workflow kết thúc/compensate đúng không? | E2E hoặc workflow integration test |

Có thể dùng WireMock làm controllable HTTP server trong integration test để tạo response delay/failure. Nếu cần xác minh behavior của actual downstream service, cần environment phù hợp.

## 13. Khi gateway, DNS, TLS và network topology là rủi ro

Contract test thường gọi trực tiếp producer hoặc local stub. Nó không tự xác minh:

- API Gateway route tới đúng service.
- Path rewrite/prefix strip đúng.
- TLS handshake, certificate chain và hostname verification.
- DNS/service discovery.
- Ingress/network policy.
- Reverse proxy headers và forwarded scheme/host.
- Load balancer/session behavior.
- Service-to-service mTLS.
- Rate limiting tại gateway.

Chọn tầng:

- **Gateway integration test:** gateway thật + upstream test service để kiểm tra route, filters, auth và header forwarding.
- **E2E:** gateway + các service cần thiết + hạ tầng gần production để xác minh workflow bên ngoài.
- **Contract test:** tiếp tục kiểm tra API boundary từng service, độc lập topology.

Không dùng E2E để kiểm tra mọi path rewrite permutation nếu có thể kiểm tra nhanh ở gateway integration suite. Giữ một số luồng đại diện xuyên gateway trong E2E.

## 14. Khi nhiều service phối hợp một workflow nghiệp vụ

E2E phù hợp hơn khi yêu cầu là **kết quả cuối cùng của một chuỗi service**, không chỉ một request/response.

Ví dụ checkout:

1. Client gửi POST checkout qua gateway.
2. Checkout tạo order pending.
3. Inventory giữ hàng.
4. Payment thu tiền.
5. Order chuyển sang confirmed.
6. Notification được phát.
7. Client tra cứu order và thấy trạng thái cuối.

Contract tests giữa Checkout–Inventory, Checkout–Payment và Checkout–Order vẫn cần thiết để phát hiện interface drift. Nhưng chúng không chứng minh orchestration tổng thể đúng.

Các lỗi chỉ lộ khi nhiều service cùng chạy:

- Saga không gọi compensation khi Payment thất bại.
- Inventory reservation hết hạn nhưng Order vẫn confirmed.
- Event đến trễ hoặc duplicate khiến trạng thái chuyển lùi.
- Correlation ID bị mất qua một service.
- Retry giữa các service tạo duplicate payment.
- Service publish event trước khi transaction commit.
- Timeout tổng thể vượt SLA dù từng call riêng đều PASS.
- Service discovery/gateway route nhầm instance hoặc version.

Một E2E test nên xác minh **business outcome và side effects quan trọng**, ví dụ order state, payment status, reservation state và event notification. Không nên assert mọi internal log hoặc thứ tự call không phải cam kết nghiệp vụ.
## 15. E2E nên kiểm tra workflow, không lặp lại mọi contract

Một lỗi phổ biến là viết E2E cho mọi biến thể request/response của từng service. Kết quả là:

- Suite chậm vì phải khởi động nhiều service.
- Một lỗi ở một service làm hàng trăm test fail cùng lúc.
- Khó biết service nào gây lỗi.
- Test phụ thuộc seed data và môi trường chung.
- Nhóm ngại chạy test thường xuyên vì thời gian phản hồi dài.

Thay vào đó, dùng contract tests để bao phủ nhiều biến thể giao diện ở từng boundary; integration tests kiểm tra cơ chế phối hợp trong service; E2E chỉ giữ **một số hành trình nghiệp vụ đại diện có rủi ro cao**.

Ví dụ Checkout:

| Tình huống | Tầng ưu tiên | Lý do |
|---|---|---|
| Inventory trả 404 với SKU không tồn tại | Contract | Một provider-consumer interaction rõ |
| Checkout parse response quantity sai kiểu | Consumer contract/stub | Kiểm tra client xử lý schema |
| Inventory reservation và outbox phải commit cùng nhau | Integration | Cần DB transaction thật |
| Kafka listener retry và dead-letter | Messaging integration | Cần broker semantics |
| Người dùng checkout thành công qua gateway, inventory, payment và order | E2E | Cần workflow xuyên service |
| Payment bị từ chối và reservation được giải phóng | Integration + một E2E quan trọng | Cần compensation thực, nhưng không phải mọi mã lỗi đều cần full E2E |

## 16. Khi E2E phù hợp hơn integration test đơn service

Integration test trong một service có thể xác minh nhiều component bên trong, nhưng không bao phủ toàn bộ topology triển khai.

E2E đáng dùng khi yêu cầu phụ thuộc vào:

- API Gateway hoặc ingress route thực.
- Service discovery/DNS và network policy.
- Authentication được truyền qua nhiều service.
- Nhiều service có version/configuration khác nhau.
- Saga/orchestration/compensation.
- Eventual consistency qua nhiều datastore.
- Hệ thống cần xác minh business SLA tổng thể.
- Một luồng người dùng trọng yếu cần kiểm tra trước release.

Ví dụ integration test của Checkout có thể dùng Payment stub và xác minh Checkout chuyển trạng thái khi Payment trả thành công. Nhưng chỉ E2E với Payment service thật trong test environment mới kiểm tra được các bước **Checkout gọi đúng endpoint, Payment ghi nhận giao dịch và Order cuối cùng chuyển trạng thái đúng**.

### Chọn E2E theo business risk

Không phải mọi workflow đều cần E2E. Ưu tiên:

1. Luồng tạo doanh thu hoặc xử lý giao dịch trọng yếu.
2. Luồng có nhiều service và compensation.
3. Luồng từng gây sự cố production.
4. Luồng có gateway/security/deployment routing phức tạp.
5. Luồng có data consistency/eventual consistency quan trọng.
6. Luồng cần kiểm tra một release candidate trước khi promote.

## 17. Thiết kế E2E theo trạng thái nghiệp vụ quan sát được

Một E2E tốt không cần biết mọi lời gọi nội bộ. Nó cần:

- Gửi input qua entry point được hỗ trợ.
- Nhận correlation/order ID.
- Chờ kết quả cuối bằng điều kiện có giới hạn thời gian.
- Đọc trạng thái qua public API hoặc một test observation interface được kiểm soát.
- Xác minh invariants nghiệp vụ.
- Dọn dữ liệu test sau khi chạy.

Ví dụ:

~~~text
Given:
  SKU-101 has available stock 8
  test payment account is authorized

When:
  client submits checkout for quantity 2

Then:
  order becomes CONFIRMED
  payment becomes CAPTURED
  reservation becomes ACTIVE
  available stock becomes 6
  orderId is returned and can be queried
~~~

Đây là **business-level scenario**. Nó không bắt buộc test phải assert Checkout gọi Inventory trước Payment theo đúng một thứ tự nội bộ, trừ khi thứ tự đó là một yêu cầu nghiệp vụ hoặc consistency guarantee.

### Assertions nên tránh

- Assert tên thread nội bộ.
- Assert thứ tự log.
- Assert số lần gọi một internal helper không phải contract.
- Assert ID tự tăng cụ thể như `orderId=1`.
- Assert một service nội bộ phải được gọi trước nếu orchestration không cam kết thứ tự đó.
- Assert database schema chi tiết trong E2E nếu integration tests đã kiểm tra schema.

Các assertions này làm E2E brittle và khiến refactor nội bộ trở thành breaking change giả.

## 18. Xử lý eventual consistency trong E2E

Nhiều workflow messaging không hoàn thành ngay khi HTTP request trả về. Checkout có thể trả `202 Accepted` hoặc trạng thái `PENDING` trước khi các consumer xử lý event.

Không nên viết:

~~~java
Thread.sleep(5000);
assertThat(orderClient.get(orderId).status())
    .isEqualTo("CONFIRMED");
~~~

Sleep cố định không bảo đảm hệ thống đã xử lý xong và kéo dài suite khi event đến sớm.

Dùng **condition-based wait** với deadline:

~~~java
await()
    .atMost(20, SECONDS)
    .untilAsserted(() -> {
        OrderView order = orderClient.getOrder(orderId);
        assertThat(order.status()).isEqualTo("CONFIRMED");
    });
~~~

Ví dụ cần dependency Awaitility và client được cấu hình. Deadline `20 seconds` chỉ là con số minh họa, cần chọn theo SLA test environment.

### Chọn điều kiện chờ đúng

- Chờ trạng thái nghiệp vụ cuối, không chờ một log message.
- Correlate theo order ID/test ID, không lấy “event gần nhất”.
- Chờ đúng điều kiện; tránh poll toàn bộ database nếu public API đủ.
- Dùng timeout hữu hạn và báo trạng thái cuối khi timeout.
- Không biến timeout dài thành cách che dead-letter hoặc consumer bị dừng.

### Khi nào cần kiểm tra event trực tiếp?

Nếu mục tiêu của test là broker delivery hoặc event contract, hãy viết messaging integration test chuyên biệt. E2E của user journey nên tập trung vào kết quả cuối mà người dùng/hệ thống quan sát được.

## 19. Dữ liệu test và isolation trong integration/E2E

Test có thể đúng khi chạy riêng nhưng fail trong suite vì chia sẻ database, broker topic hoặc account.

### Nguyên tắc dữ liệu

- Mỗi test có unique correlation/order ID.
- Dữ liệu seed có tên và nguồn rõ ràng.
- Không phụ thuộc vào record được tạo bởi test khác.
- Dùng account/SKU/test tenant riêng cho suite.
- Cleanup theo namespace hoặc test run ID.
- Không dùng dữ liệu production thật.
- Không để test suite xóa dữ liệu của môi trường dùng chung.

### Isolation cho database

- Testcontainers tạo DB riêng cho suite hoặc class phù hợp.
- Migrations chạy như ứng dụng thật.
- Test data builder tạo dữ liệu có ý nghĩa.
- Rollback chỉ khi request chạy trong cùng transaction context; HTTP server thread khác có thể commit độc lập.
- Test chạy song song cần schema/database riêng hoặc namespace/lock.

### Isolation cho broker

- Topic/queue hoặc consumer group riêng.
- Correlation ID cho từng test.
- Offset/ack reset có kiểm soát.
- Không nhận message của test khác.
- Dọn topic/namespace sau test theo policy.

### Isolation cho service environment

Nếu nhiều E2E chạy song song, dùng namespace hoặc deployment riêng. Một E2E test không được phụ thuộc vào một service chung bị test khác thay đổi state.

## 20. Testcontainers giúp integration test sát dependency thật

Testcontainers hữu ích khi cần chạy dependency thật mà không phải duy trì server dùng chung.

Ví dụ có thể khởi động:

- PostgreSQL/MySQL tương thích production.
- Kafka hoặc broker phù hợp.
- Redis.
- LocalStack hoặc service giả lập cloud dependency.
- WireMock container khi cần controllable HTTP dependency.

### Khi nào nên dùng Testcontainers?

| Nhu cầu | Testcontainers có ích? |
|---|---|
| SQL dialect/constraint/transaction | **Có** |
| Broker semantics/serialization | **Có** |
| Cache behavior phụ thuộc engine | **Có** |
| Test API client với response tùy chỉnh | WireMock/Test server có thể đủ |
| Full production cluster với nhiều service | Thường cần môi trường E2E riêng |
| Kiểm tra gateway/ingress/load balancer thật | Test environment triển khai gần production phù hợp hơn |

Không phải cứ dùng container là test đã là integration test tốt. Phải chạy đúng dependency và kiểm tra đúng invariant.

### Ví dụ Kafka container (minh họa)

~~~java
import org.testcontainers.kafka.KafkaContainer;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class InventoryMessagingIT {

    @Container
    static KafkaContainer kafka =
        new KafkaContainer(
            DockerImageName.parse("apache/kafka-native:3.8.0")
        );

    @DynamicPropertySource
    static void kafkaProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.kafka.bootstrap-servers",
            kafka::getBootstrapServers
        );
    }

    @Test
    void publishesStockChangedEvent() {
        // Seed inventory, invoke application service,
        // consume event from the test topic and assert payload/headers.
    }
}
~~~

Đây là khung minh họa. Container image/API và Kafka client version phải được chọn tương thích với Testcontainers version và môi trường dự án; test cần consumer/producer setup, topic, timeout, cleanup và assertions thực tế.

## 21. Tích hợp Spring Cloud Contract vào test strategy

Spring Cloud Contract tiếp tục giữ vai trò trung tâm ở service boundaries, ngay cả khi bổ sung integration/E2E.

~~~mermaid
flowchart TD
    A["Contract DSL"] --> B["Producer generated tests"]
    A --> C["Consumer Stub Runner tests"]
    B --> D["Producer boundary verified"]
    C --> E["Consumer boundary verified"]
    D --> F["Integration tests with real dependencies"]
    E --> F
    F --> G["E2E critical business journeys"]
    G --> H["Release confidence"]
~~~

### Contract test bảo vệ điều gì?

- HTTP method/path/status/headers/body.
- Message destination/label/headers/payload.
- Dynamic values qua matchers.
- Consumer assumptions về response/message.
- Producer compatibility với contract được công bố.

### Integration test bổ sung điều gì?

- Persistence/transaction.
- Spring application context, web stack và security.
- Broker, serialization, retry/ack.
- Adapter/client configuration.
- Component interaction trong service.

### E2E bổ sung điều gì?

- Gateway/network/service discovery.
- Nhiều service và workflow.
- Business outcome, compensation và eventual consistency.
- Runtime configuration trong môi trường gần production.

**Đừng xóa contract tests sau khi có integration/E2E.** Integration/E2E chậm và khó định vị lỗi hơn; contract tests vẫn là feedback nhanh cho interface drift.

## 22. Kết hợp generated producer tests và integration tests

Producer generated tests có thể dùng base class để chuẩn bị dependency/state. Chọn base class/test mode theo ranh giới muốn kiểm tra.

### Producer contract test tập trung boundary

Ví dụ producer generated test dùng MockMvc với service dependency được chuẩn bị để response có thể tái hiện. Cách này phù hợp kiểm tra contract ở controller/provider boundary.

### Producer integration test kiểm tra service thật

Thêm một test suite riêng dùng Spring context, DB thật và repository thật để xác minh transaction/persistence. Không cần biến mọi contract generated test thành một test nặng với container nếu phần lớn assertions chỉ cần HTTP boundary.

### Vì sao tách hai suite?

- Generated contract tests phản hồi nhanh và tập trung vào contract.
- Integration tests kiểm chứng infrastructure/component interaction.
- Khi integration fail, nhóm có thể khoanh vùng DB/broker/config.
- Khi contract fail, nhóm biết provider behavior đã lệch khỏi agreement.
- E2E chỉ kiểm tra số lượng nhỏ workflow quan trọng.

### Cấu trúc source set minh họa

~~~text
src/
  main/
  test/
    java/
      ... unit and fast tests
  contractTest/
    java/
      ... generated Spring Cloud Contract tests
  integrationTest/
    java/
      ... database, broker, security integration tests
  e2eTest/
    java/
      ... deployed workflow tests
~~~

Tên source set/task là convention của dự án, không phải Spring Cloud Contract tự tạo tất cả. Gradle/Maven cần cấu hình plugin/source sets/test lifecycle tương ứng.

## 23. Khi nào không cần E2E?

Không nên viết E2E chỉ vì một test nghe có vẻ “thực tế hơn”.

Contract hoặc integration test thường đủ khi:

- Chỉ cần xác minh schema/headers/status tại một boundary.
- Chỉ cần kiểm tra một service tính toán business rule.
- Lỗi có thể tái hiện bằng DB/broker test container trong phạm vi một service.
- Mỗi biến thể request có thể được kiểm tra độc lập bằng contract/stub.
- Không có rủi ro topology/deployment hoặc cross-service workflow liên quan.

Ví dụ, 30 trường hợp validation cho endpoint Inventory không cần 30 E2E tests. Dùng unit/contract/provider tests cho các trường hợp đầu vào; thêm một integration test cho persistence/validation pipeline; giữ một E2E happy path và một failure/compensation path quan trọng.

### Chi phí của E2E

- Setup môi trường lâu.
- Nhiều dependency và nhiều điểm fail.
- Test data phức tạp.
- Flakiness do network/timing.
- Khó phân biệt lỗi ứng dụng và hạ tầng.
- Thời gian debug và rerun lớn.
- Phụ thuộc deployment version/configuration.

E2E có giá trị khi rủi ro được kiểm chứng xứng đáng với chi phí đó.

## 24. Khi contract test vẫn là lựa chọn tốt nhất

Dùng contract test khi câu hỏi là:

- Producer có trả status/body/header theo DSL không?
- Consumer có xử lý response provider đã công bố không?
- Message payload có giữ field/type/headers quan trọng không?
- Producer change có phá consumer expectation không?
- Consumer có đang phụ thuộc vào một behavior chưa được thống nhất không?

Không cần khởi động cả hệ thống chỉ để kiểm tra một response JSON. Contract test giúp phát hiện breaking change sớm và cho phép producer/consumer phát triển độc lập.

### Ví dụ một lỗi contract nên bắt

Producer đổi:

~~~json
{"sku":"SKU-101","available":true,"quantity":8}
~~~

thành:

~~~json
{"sku":"SKU-101","availability":"IN_STOCK","units":8}
~~~

Nếu consumer cần `available`/`quantity`, consumer contract test phải fail với stub mới. Đây là tín hiệu interface drift; không cần E2E mới phát hiện được.

### Nhưng contract test không kiểm tra toàn bộ behavior

Nếu producer trả đúng JSON nhưng lưu quantity sai vào DB, contract có thể vẫn PASS. Đó là rủi ro integration; hãy kiểm tra persistence/invariant bằng integration test.

## 25. Khi integration test vẫn chưa đủ và cần E2E

Integration test trong một service hoặc một nhóm component không xác minh deployment topology và cross-service orchestration đầy đủ.

Chọn E2E khi:

- Gateway route, auth propagation hoặc service discovery là điều kiện bắt buộc.
- Nhiều service có thể deploy độc lập và version khác nhau.
- Eventual consistency xuyên nhiều datastore cần được kiểm tra.
- Saga/compensation trải qua nhiều service.
- User journey hoặc business SLA phải được xác nhận trước release.
- Một lỗi production trước đây chỉ xuất hiện trong environment tích hợp.

Ví dụ Payment integration test có thể chứng minh Payment service capture transaction thành công. Nó không chứng minh Checkout, Payment và Order phối hợp để một order chỉ được confirmed sau khi payment capture hoàn tất.

E2E kiểm tra kết quả xuyên chuỗi, còn contract tests bảo vệ từng API/message boundary và integration tests bảo vệ cơ chế bên trong từng service.

## 26. Thiết kế pipeline theo tầng

Một CI pipeline cân bằng có thể tổ chức:

~~~mermaid
flowchart TD
    A["Pull request"] --> B["Unit + static checks"]
    B --> C["Producer contract tests"]
    B --> D["Consumer Stub Runner tests"]
    C --> E["Integration tests"]
    D --> E
    E --> F{"Critical integration PASS?"}
    F -->|No| X["Block"]
    F -->|Yes| G["Build deployable candidate"]
    G --> H["Deploy isolated test environment"]
    H --> I["Critical E2E journeys"]
    I --> J{"E2E PASS?"}
    J -->|No| X
    J -->|Yes| K["Release candidate"]
~~~

### PR feedback

- Unit/fast tests.
- Generated producer contract tests.
- Consumer tests với stub artifact phù hợp.
- Integration tests chọn lọc cho code paths/rủi ro vừa thay đổi.

### Main branch/nightly

- Integration suite đầy đủ với DB/broker containers.
- Consumer compatibility với candidate stub mới.
- E2E critical journeys trong environment cô lập.
- Smoke checks cho gateway/network/deployment.

### Pre-release

- E2E critical business journeys.
- Contract compatibility với các consumer quan trọng.
- Migration/rollback tests nếu release có thay đổi persistence.
- Operational smoke tests, auth và network.
- Artifact/version/provenance checks.

Không phải mọi tổ chức cần đúng ba stage này; hãy điều chỉnh theo tốc độ release và chi phí môi trường.

## 27. Quản lý test flakiness và chẩn đoán lỗi theo tầng

Khi suite fail, tên test và log phải giúp xác định failure thuộc tầng nào.

| Failure | Dấu hiệu | Hướng điều tra |
|---|---|---|
| Contract producer test | Generated assertion không khớp | DSL, producer response, matcher |
| Consumer stub test | Unmatched stub/request hoặc client assertion | Stub version, mapping, consumer URL/body |
| DB integration | SQL/constraint/transaction failure | Migration, DB engine, transaction, seed |
| Messaging integration | Timeout/duplicate/ack fail | Broker, topic, consumer group, offset |
| Security integration | 401/403 ngoài mong đợi | Filter chain, test identity, JWT config |
| E2E | Workflow không đạt trạng thái cuối | Service logs, correlation ID, event flow, environment |
| Deployment smoke | Không connect/route/TLS | Gateway, DNS, certificate, network policy |

### Nguyên tắc giảm flakiness

- Dùng unique test data/correlation ID.
- Không dùng sleep cố định cho asynchronous workflows.
- Dùng bounded await với deadline.
- Không chia sẻ state giữa test song song.
- Không phụ thuộc thứ tự test.
- Pin container image và toolchain.
- Dùng environment riêng hoặc namespace.
- Giữ log, traces và IDs để tái hiện.
- Không retry đến khi xanh rồi bỏ qua failure đầu tiên.

**Không nới contract matcher để sửa lỗi integration/E2E.** Nếu business behavior cần đúng quantity/status, giữ assertion đó; tìm nguyên nhân state/broker/network thực.

## 28. Bài thực hành: chọn tầng kiểm thử phù hợp

### Case A — Producer đổi response field

Inventory đổi `quantity` từ number thành string.

**Lựa chọn:** contract test.

Lý do: đây là thay đổi schema ở provider-consumer boundary. Generated producer test và consumer Stub Runner test có thể phát hiện trực tiếp.

### Case B — Reservation ghi DB và outbox không nguyên tử

Khi outbox insert fail, reservation vẫn tồn tại.

**Lựa chọn:** database integration test.

Lý do: cần transaction manager, database và rollback thật. Contract response đơn lẻ không chứng minh atomicity.

### Case C — Hai request đồng thời oversell stock

**Lựa chọn:** concurrency integration test với DB tương thích production; bổ sung contract cho status/conflict response.

Lý do: cần kiểm tra locking/isolation thực và business invariant cuối.

### Case D — Gateway bỏ Authorization header

**Lựa chọn:** gateway integration test; E2E nếu cần xác minh luồng authentication qua nhiều service.

Lý do: test controller trực tiếp không đi qua gateway routing/header forwarding.

### Case E — Payment thất bại nhưng order vẫn confirmed

**Lựa chọn:** E2E critical workflow, cộng integration tests cho Payment/Order state transitions.

Lý do: lỗi nằm ở orchestration/compensation xuyên service.

### Case F — Consumer không parse được response stub

**Lựa chọn:** consumer contract test với Stub Runner.

Lý do: kiểm tra consumer xử lý schema/behavior provider đã công bố; không cần dựng tất cả service.

### Case G — Kafka consumer không ack và message bị redeliver

**Lựa chọn:** messaging integration test với broker phù hợp.

Lý do: cần xác minh broker delivery/ack semantics. Chỉ dùng E2E nếu redelivery gây sai business workflow xuyên service.

### Case H — Một checkout happy path cần kiểm tra trước release

**Lựa chọn:** E2E critical journey.

Lý do: cần chứng minh kết quả nghiệp vụ qua gateway, Checkout, Inventory, Payment và Order cùng hoạt động.

## 29. Checklist review chiến lược test

### Chọn đúng ranh giới

- [ ] Câu hỏi kiểm thử được viết rõ dưới dạng behavior/risk.
- [ ] Contract test được dùng cho API/message boundary đã thống nhất.
- [ ] Integration test được dùng khi cần component/dependency thật.
- [ ] E2E chỉ giữ cho workflow/topology/business risk quan trọng.
- [ ] Không dùng tên annotation để suy ra test level.
- [ ] Ghi rõ dependency thật, dependency mock/stub và phạm vi assertion.

### Integration test

- [ ] DB engine phù hợp behavior production cần kiểm chứng.
- [ ] Migration/schema được khởi tạo như ứng dụng.
- [ ] Transaction rollback/commit được đọc từ trạng thái bền vững.
- [ ] Broker/destination/consumer group được cô lập.
- [ ] Retry/ack/DLQ được kiểm tra nếu là yêu cầu.
- [ ] Security filter chain/serialization/client configuration chạy đúng stack.
- [ ] Dữ liệu test có seed/cleanup rõ.
- [ ] Test có thể chạy riêng và song song an toàn.

### E2E

- [ ] Bắt đầu từ entry point thực cần xác minh.
- [ ] Môi trường chứa đúng service/gateway/configuration cần.
- [ ] Test dùng unique ID/correlation.
- [ ] Chờ eventual consistency bằng condition có deadline.
- [ ] Assert business outcome, không assert internal implementation.
- [ ] Có timeout và diagnostics khi workflow không hoàn tất.
- [ ] Cleanup dữ liệu/environment an toàn.
- [ ] Chỉ chọn các journey quan trọng, không lặp hàng loạt contract cases.

### CI và bảo trì

- [ ] Contract tests chạy sớm để phát hiện drift.
- [ ] Integration tests chạy trên PR/main phù hợp rủi ro.
- [ ] E2E critical suite chạy trong environment cô lập.
- [ ] Toolchain, container images và stub artifacts được pin.
- [ ] Test report ghi rõ tầng failure.
- [ ] Logs/traces có correlation IDs.
- [ ] Flaky failures được điều tra, không che bằng retry.
- [ ] Release gate có bằng chứng contract + integration + E2E theo risk.

## 30. Ghi nhớ và tài liệu tham khảo

**Contract test, integration test và E2E test bổ sung cho nhau.**

Spring Cloud Contract là lựa chọn mạnh khi cần kiểm tra producer/consumer có tuân thủ HTTP/message agreement hay không. Integration test phù hợp hơn khi rủi ro nằm ở database, transaction, security filter, serialization, broker, retry hoặc phối hợp các component thật. E2E phù hợp khi cần xác minh gateway, network, nhiều service, saga/compensation, eventual consistency và business journey.

Không phải cứ test càng rộng càng tốt. Contract tests tạo feedback nhanh ở boundary; integration tests xác minh các cơ chế thực; E2E xác minh số lượng nhỏ workflow quan trọng trong môi trường gần production. Chọn tầng theo **rủi ro cần chứng minh**, rồi giữ assertions ổn định và có thể chẩn đoán.

### Tài liệu tham khảo

- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/): contract DSL, producer verification và Stub Runner.
- [Spring Cloud Contract — Gradle Project](https://docs.spring.io/spring-cloud-contract/reference/gradle-project.html): generated contract tests và stub generation.
- [Spring Cloud Contract — Stub Runner](https://docs.spring.io/spring-cloud-contract/reference/project-features-stubrunner/stub-runner-boot.html): consumer-side stubs.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): Spring Boot test support và application context.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): tích hợp Testcontainers.
- [Testcontainers for Java](https://java.testcontainers.org/): chạy database, broker và dependencies trong test.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): kiểm tra authentication/authorization trong test.
- [Awaitility](https://github.com/awaitility/awaitility): chờ điều kiện bất đồng bộ có giới hạn.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): mô phỏng HTTP dependency trong consumer/integration tests.

**Kết luận thực hành:** trước khi viết test, hãy hỏi **“lỗi nào mình cần bắt, và cần những thành phần thật nào để chứng minh?”** Nếu đó là interface drift, dùng contract test. Nếu đó là transaction, broker hoặc security integration, dùng integration test. Nếu đó là kết quả của một workflow qua nhiều service, chọn E2E cho hành trình trọng yếu.

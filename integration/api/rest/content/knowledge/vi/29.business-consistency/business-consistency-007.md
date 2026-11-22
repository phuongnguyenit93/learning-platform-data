# Transactional Outbox khi vừa cập nhật dữ liệu vừa phát sự kiện

## 1. Tình huống: một yêu cầu HTTP, hai hệ thống phải biết cùng sự thật

Một API nhận đơn hàng:

~~~http
POST /api/v1/orders HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: checkout-841
Accept: application/json

{
  "cartId": "cart-42",
  "shippingAddressId": "addr-8"
}
~~~

Order Service cần **lưu đơn vào PostgreSQL** và **phát OrderCreated lên message broker** để Inventory, Billing hoặc Notification xử lý. Nếu hai thao tác này nằm trên hai hệ thống độc lập, transaction database thông thường **không bảo đảm** message broker đã nhận event. Một câu lệnh Java gọi repository rồi producer không đủ để có tính nhất quán.

**Transactional Outbox** giải quyết bài toán bằng cách ghi **bản ghi nghiệp vụ và event dự định phát** vào **cùng một transaction database**, sau đó một relay độc lập chuyển event đã commit đến broker. Mẫu này kết hợp nhất quán cục bộ của cơ sở dữ liệu với giao tiếp bất đồng bộ, tránh phải dùng distributed transaction/two-phase commit cho hai tài nguyên không chung transaction manager.

Bài thuộc chương **Nhất quán nghiệp vụ**, module **INTEGRATION_API_REST**: thiết kế REST API theo resource, URI, method/status HTTP, hợp đồng dữ liệu, idempotency, OpenAPI, xác thực/phân quyền, xử lý lỗi và kiểm thử Java/Spring. Ví dụ tập trung **Java 17+, Spring Boot 3.x, Spring Data JPA, PostgreSQL**, một broker tương đương Kafka/RabbitMQ, và các giả định được ghi tường minh.

Học xong, bạn cần:

1. Giải thích **dual-write problem** và phân biệt *transaction commit* với *event delivery*.
2. Thiết kế bảng outbox, event envelope, transaction boundary và idempotency.
3. Cài **@Transactional** để lưu aggregate + outbox atomically trong Spring.
4. Triển khai **polling relay** hoặc **CDC** mà không mất event khi process/broker lỗi.
5. Chấp nhận **at-least-once delivery**, viết consumer idempotent và bảo toàn ordering khi cần.
6. Dùng HTTP 201/202/409/503 đúng ý nghĩa, phân quyền tenant, không làm lộ dữ liệu nhạy cảm.
7. Kiểm thử rollback, concurrent requests, broker outage, duplicate, replay và theo dõi độ trễ outbox.

## 2. Dual-write: vì sao các cách trực giác thất bại?

Giả sử service làm hai hành động:

~~~java
orderRepository.save(order);
eventProducer.publish(new OrderCreated(order.id()));
~~~

Có ít nhất bốn thời điểm hỏng:

| Trình tự | Sự cố | Trạng thái cuối | Hậu quả |
| --- | --- | --- | --- |
| DB commit rồi mới publish | Process crash giữa hai bước | **Có order, không có event** | Billing/Inventory không biết đơn |
| Publish trước DB commit | DB rollback sau publish | **Có event, không có order** | Consumer xử lý đơn không tồn tại |
| Publish trong @Transactional DB | Broker nhận, DB commit lỗi | **Event có, order không có** | @Transactional không bao trùm broker |
| DB commit và broker publish đều thành công, ACK mất | Producer retry | **Event có thể xuất hiện nhiều lần** | Consumer tạo tác dụng phụ trùng |

**Không thể sửa chỉ bằng đổi thứ tự hai lời gọi.** @Transactional chỉ bao trùm resource do transaction manager quản lý. HTTP client, Kafka producer, email sender hay message broker thường không tự gia nhập transaction JDBC/JPA.

### Vì sao afterCommit, @Async và event nội bộ chưa đủ?

~~~java
@Transactional
public Order create(CreateOrderRequest body) {
    Order order = orderRepository.save(map(body));
    applicationEventPublisher.publishEvent(
        new OrderCreated(order.id()));
    return order;
}
~~~

Đoạn này chưa nói event được ai xử lý và khi nào. Nếu handler gửi broker trực tiếp, vẫn có khoảng mất dữ liệu. Ngay cả **@TransactionalEventListener(phase = AFTER_COMMIT)** cũng có **khoảng crash sau commit nhưng trước khi callback hoàn tất**. Nếu @Async gửi broker, process có thể chết khi task còn trong RAM. Cả hai có thể hữu ích cho công việc *best-effort*, nhưng **không thay thế outbox durable** khi event là bắt buộc.

### Ranh giới bài toán

Outbox đảm bảo **bản ghi nghiệp vụ và một bản ghi dự định phát event cùng commit hoặc cùng rollback** khi chúng nằm trong **cùng database transaction ACID**. Nó **không** tự đảm bảo consumer đã xử lý, chỉ phát một lần, mạng không đứt, hay toàn hệ thống có ACID xuyên nhiều service.

## 3. Định nghĩa rõ các mức nhất quán

Một hệ thống dùng outbox thường đạt các bảo đảm khác nhau ở từng biên:

| Biên | Bảo đảm có thể thiết kế | Không nên hứa |
| --- | --- | --- |
| **Order + outbox trong PostgreSQL** | Atomic commit/rollback trong một transaction | Bao trùm cả Kafka/email/S3 |
| **Outbox → broker** | Phát lại đến khi được broker xác nhận (**at least once** nếu policy đủ bền vững) | Exactly-once end-to-end chỉ bằng một poller |
| **Broker → consumer** | Consumer xử lý lại an toàn, lưu dedup/offset theo contract | Không bao giờ gặp duplicate hoặc out-of-order |
| **Order Service → HTTP caller** | 201 sau khi order + outbox commit | 201 nghĩa mọi downstream đã xong |
| **Toàn bộ workflow** | **Eventual consistency** với timeout, monitoring, recovery | Strong consistency tức thời giữa mọi service |

Khi API trả 201, event có thể còn nằm trong outbox vài mili-giây hoặc nhiều giây. Inventory có thể chưa reserve xong. Nếu quy trình yêu cầu phân phối hoặc phê duyệt nhiều bước trước khi trả kết quả nghiệp vụ cuối, hãy mô hình hóa **operation resource/Saga** và trạng thái rõ ràng thay vì diễn đạt sai rằng “order đã hoàn tất hết mọi việc”.

**Tính đúng phụ thuộc giả định**: database không mất dữ liệu đã commit theo durability policy; ứng dụng không bỏ event trước khi publish thành công; relay được vận hành/retry; sink có cách xử lý duplicate; business idempotency được triển khai riêng.

## 4. Kiến trúc và luồng dữ liệu

~~~mermaid
flowchart TD
    A[HTTP POST /orders] --> B[Spring Security + validation]
    B --> C[OrderService @Transactional]
    C --> D[INSERT order + INSERT outbox]
    D --> E{DB commit?}
    E -->|Rollback| F[Không có order / event mới]
    E -->|Commit| G[201 Created + Location]
    E -->|Commit| H[(Outbox PENDING)]
    H --> I[Relay polling hoặc CDC]
    I --> J[Broker topic/queue]
    J --> K[Inventory/Billing/Notification]
    K --> L[Consumer dedup + business transaction]
~~~

**Hai dòng xuất phát từ commit** không có nghĩa event delivery phải xong trước HTTP response. Outbox PENDING chỉ là một bản ghi database đã được commit. Relay có thể chạy cùng ứng dụng trong một process hay thành worker độc lập; về vận hành, tách worker thường giúp kiểm soát throughput/retries dễ hơn.

Một state machine outbox tham khảo:

~~~text
PENDING
  -> IN_FLIGHT (worker lease)
  -> PUBLISHED (broker ACK)
  -> ARCHIVED/DELETED theo retention

IN_FLIGHT
  -> PENDING (gửi lỗi, backoff)
  -> IN_FLIGHT (lease hết hạn, worker khác claim)
  -> PUBLISHED (late ACK nếu vẫn sở hữu claim)

PENDING/IN_FLIGHT
  -> DEAD_LETTER (quá số lần/thời gian, cần điều tra/replay)
~~~

**DEAD_LETTER không nên là xóa event**. Nó là một trạng thái có quy trình cảnh báo, điều tra và replay được kiểm soát. Event bắt buộc mà dừng vĩnh viễn không có người xử lý vẫn có thể làm toàn workflow kẹt dù database transaction đã thành công.

## 5. Thiết kế event contract: domain fact, không phải Java object dump

Ví dụ OrderCreated đã commit:

~~~json
{
  "eventId": "2bcb49e5-38dc-4cab-9ff3-faf2b87b81d8",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "aggregateType": "Order",
  "aggregateId": "ord-501",
  "aggregateVersion": 1,
  "tenantId": "tenant-a",
  "occurredAt": "2026-11-18T09:30:00Z",
  "producer": "orders-service",
  "correlationId": "req-841",
  "operationId": "checkout-841",
  "payload": {
    "orderId": "ord-501",
    "totalMinor": 180000,
    "currency": "VND",
    "status": "CREATED"
  }
}
~~~

| Field | Vai trò | Bảo đảm cần kiểm tra |
| --- | --- | --- |
| **eventId** | Định danh duy nhất của event | Sinh một lần lúc tạo outbox; không sinh lại mỗi publish |
| **eventType/schemaVersion** | Reader định tuyến/di trú schema | Stable naming, có cơ chế nâng version |
| **aggregateId/version** | Phân biệt các thay đổi cùng resource | Giúp ordering, phát hiện gap/replay |
| **tenantId** | Phân vùng dữ liệu/quyền truy cập | Lấy từ context đã xác thực, không từ body |
| **occurredAt** | Thời điểm event được tạo khi xử lý transaction | Không đồng nghĩa lúc broker hoặc consumer nhận |
| **correlationId/operationId** | Truy vết HTTP, idempotency, async workflow | Được validate/generate ở trust boundary |
| **payload** | Dữ liệu consumer thật sự cần | Minimal, không chứa access token/PII thừa |

Sự kiện **OrderCreated** là một *fact*: order được commit, không phải “người dùng đã bấm nút gửi”. Nếu transaction rollback thì không được phát fact này. Nếu một request POST bị retry và server trả lại kết quả idempotent của lần trước, không tự tạo thêm event OrderCreated thứ hai.

**Không đưa password, API key, Authorization header, số thẻ hoặc toàn bộ JSON DTO** vào event. Outbox thường được sao chép sang nhiều broker, sink, data lake nên mức độ phơi bày dữ liệu có thể lớn hơn database nguồn. Mọi consumer phải biết schema và quyền sử dụng dữ liệu, không vì internal event mà được quyền bỏ qua tenant/privacy.

## 6. Schema PostgreSQL: order và outbox cùng database

Ví dụ schema tối giản phục vụ atomic write và relay:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    external_reference VARCHAR(120) NOT NULL,
    request_fingerprint CHAR(64) NOT NULL,
    status VARCHAR(30) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_orders_tenant_extref
        UNIQUE (tenant_id, external_reference)
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    tenant_id VARCHAR(80) NOT NULL,
    aggregate_type VARCHAR(60) NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    schema_version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner UUID,
    leased_until TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    last_error_code VARCHAR(80),
    CHECK (status IN (
        'PENDING', 'IN_FLIGHT', 'PUBLISHED', 'DEAD_LETTER'))
);

CREATE INDEX outbox_pending_idx
    ON outbox_events (status, next_attempt_at, occurred_at);

CREATE INDEX outbox_expired_lease_idx
    ON outbox_events (status, leased_until)
    WHERE status = 'IN_FLIGHT';

CREATE INDEX outbox_aggregate_idx
    ON outbox_events (
        tenant_id, aggregate_type, aggregate_id, aggregate_version);
~~~

**Schema là thiết kế tham khảo**, không tự có tính toàn vẹn nếu không có policy. Production nên có **unique constraint theo (tenant_id, aggregate_type, aggregate_id, aggregate_version, event_type)** khi mô hình xác định mỗi version chỉ có một event cùng type; nếu có nhiều event hợp lệ cho cùng version, phải chọn business event ID/invariant khác thay vì áp unique sai. DB constraints bảo vệ trạng thái, không thay validator của JSON schema.

Không đặt transaction của broker vào cùng câu lệnh SQL này. **Tất cả thay đổi order và outbox phải qua cùng DataSource/transaction manager**; nếu repo outbox kết nối database khác, **@Transactional** thông thường không bảo đảm atomicity.

**Đừng mặc định event cần FK trực tiếp đến orders**: event retention có thể dài hơn lifetime của order, và các entity có thể bị archive/xóa. Chọn referential integrity theo nghiệp vụ/retention, không để purge order phá audit/event history.

## 7. Java/Spring: ghi aggregate và outbox trong một @Transactional

DTO request nhận từ client **không** có tenantId, ownerId hoặc eventId; các thông tin đó do server kiểm soát:

~~~java
public record CreateOrderRequest(
    @NotBlank String cartId,
    @NotBlank String shippingAddressId
) {}

public record OrderResponse(UUID id, String status) {}

public record CreatedOrder(UUID id, String status) {}
~~~

Service tạo order và outbox trong cùng transaction:

~~~java
@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final OrderAuthorizationPolicy access;
    private final RequestFingerprint fingerprints;
    private final Clock clock;

    public OrderCommandService(
            OrderRepository orders,
            OutboxRepository outbox,
            OrderAuthorizationPolicy access,
            RequestFingerprint fingerprints,
            Clock clock) {
        this.orders = orders;
        this.outbox = outbox;
        this.access = access;
        this.fingerprints = fingerprints;
        this.clock = clock;
    }

    @Transactional
    @PreAuthorize("hasAuthority('SCOPE_orders:write')")
    public CreatedOrder createOnce(
            CreateOrderRequest request,
            String idempotencyKey,
            Authentication caller) {

        String tenantId = access.requireAuthorizedTenant(caller);
        access.requireCartOwnership(caller, request.cartId());
        access.requireAddressOwnership(
            caller, request.shippingAddressId());

        UUID orderId = UUID.randomUUID();
        String fingerprint = fingerprints.of(
            tenantId, request); // Canonical request digest.

        OrderEntity order = OrderEntity.newCreated(
            orderId, tenantId, idempotencyKey,
            fingerprint, request.cartId(),
            request.shippingAddressId());

        orders.save(order);

        OrderCreatedV1 event = new OrderCreatedV1(
            UUID.randomUUID(), orderId, tenantId,
            1L, Instant.now(clock),
            order.totalMinor(), order.currency(), "CREATED");

        outbox.save(OutboxEntity.pending(
            event, "OrderCreated", 1));

        return new CreatedOrder(orderId, "CREATED");
        // Transaction commit sau khi method hoàn tất qua proxy.
    }
}
~~~

**OrderEntity, OrderCreatedV1, OrderRepository, OutboxEntity, OutboxRepository, RequestFingerprint và OrderAuthorizationPolicy** là các thành phần ứng dụng cần cài đặt; ví dụ tập trung đúng boundary. **OrderCreatedV1** phải serialize thành event contract ở mục 5, bao gồm các field nghiệp vụ cần thiết nhưng không xuất toàn bộ entity. EventId được sinh **một lần** và lưu trong outbox.

Điều kiện để đoạn code đạt atomicity:

- Hai repository phải dùng **cùng DataSource và transaction manager**. Không cấu hình repository outbox sang một database khác rồi cho rằng một @Transactional vẫn bao trùm được cả hai.
- Method **createOnce** phải được gọi qua **Spring transaction proxy**, không gọi trực tiếp từ method khác trong cùng class (self-invocation) rồi bỏ qua interceptor.
- Dùng rollback theo exception policy phù hợp. Spring @Transactional mặc định rollback với RuntimeException/Error; nếu dùng checked exception riêng, cấu hình **rollbackFor** khi cần.
- **Flush khác commit**: JPA có thể trì hoãn SQL đến flush/commit. Không coi một lệnh save đã trả về là dữ liệu chắc chắn đã commit.
- Không gọi HTTP, broker hoặc email producer **bên trong transaction** này. Duy trì transaction ngắn, đặt lock/timeout phù hợp để tránh giữ DB connection quá lâu.
- Chỉ tạo event đã commit cho **state change có thật**. Nếu command không làm gì (ví dụ lặp yêu cầu), không tự tạo OrderCreated lần nữa.

Với entity dùng **@Version**, lấy giá trị version phù hợp mô hình. Ví dụ OrderCreated có aggregateVersion=1 do domain tự xác định; đừng áp giá trị đó lên field do JPA tự quản lý mà không kiểm thử flush/commit và mapping.

### Repository và sự kiện phải có scope tenant

Định nghĩa truy vấn theo **tenant + business reference**:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {

    Optional<OrderEntity>
        findByTenantIdAndExternalReference(
            String tenantId, String externalReference);
}
~~~

Tất cả các lần đọc/replay phải kiểm tra tenant theo principal đã xác thực; không lookup order bằng idempotency key toàn hệ thống nếu chưa giới hạn tenant. Unique constraint **(tenant_id, external_reference)** xử lý tranh chấp race mà thao tác “check rồi insert” ở Java không giải quyết được.

## 8. HTTP API: 201 sau commit, idempotency cho retry

Controller dùng một facade chịu trách nhiệm xử lý **tạo mới hoặc trả kết quả đã ghi trước đó**:

~~~java
@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {
    private final IdempotentOrderFacade facade;

    public OrderController(IdempotentOrderFacade facade) {
        this.facade = facade;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderResponse> create(
            @Valid @RequestBody CreateOrderRequest body,
            @RequestHeader("Idempotency-Key") String key,
            Authentication authentication) {

        CreatedOrder order =
            facade.createOrReplay(body, key, authentication);

        URI location =
            URI.create("/api/v1/orders/" + order.id());

        return ResponseEntity.created(location)
            .cacheControl(CacheControl.noStore())
            .body(new OrderResponse(
                order.id(), order.status()));
    }
}
~~~

**IdempotentOrderFacade** là abstraction cần hiện thực: cùng **tenant + key + fingerprint(payload)** phải trả cùng order/response theo contract; **cùng key nhưng payload khác** phải bị từ chối (thường **409 Conflict**); key rỗng/quá dài hoặc sai định dạng trả **400**. Định nghĩa TTL, scope key, canonical payload và xử lý request đồng thời. Không dùng body hash đơn thuần làm authentication hoặc key tenant.

Với schema ở mục 6, **external_reference** được dùng làm định danh bền vững tương ứng với **Idempotency-Key** cho ví dụ này, còn **request_fingerprint** là digest chuẩn hóa để phát hiện key reuse với payload khác. Trong thực tế có thể tách **idempotency_requests** thành bảng riêng nếu endpoint có nhiều loại response/stage hoặc muốn lưu nguyên response để replay. Một idempotency key có thể chứa dữ liệu định danh; đặt giới hạn độ dài/ký tự và bảo vệ giá trị khi ghi log.

### Race condition: phải giải quyết sau transaction thất bại

Thuật toán facade tham khảo:

~~~text
1. Validate key; xác định tenant/principal đáng tin.
2. Chuẩn hóa body, tính fingerprint.
3. Gọi orderCommandService.createOnce(...) qua Spring proxy;
   transaction gồm order + outbox, commit thành công thì trả 201.
4. Nếu có unique conflict trên (tenant_id, external_reference):
   - transaction tạo mới phải rollback xong;
   - mở read transaction MỚI để tìm order theo tenant + key;
   - fingerprint bằng nhau: replay kết quả đã lưu (không tạo event);
   - khác nhau: 409 IDEMPOTENCY_KEY_REUSED.
5. Nếu constraint khác hoặc lỗi DB/commit khác: KHÔNG giả là
   duplicate; phân loại 5xx/503 và đối soát kết quả chưa rõ.
~~~

**Không bắt DataIntegrityViolationException rồi query lại bằng EntityManager trong cùng transaction đã bị lỗi**: transaction có thể đang ở trạng thái rollback-only hoặc database transaction đã aborted. Ngoài ra unique violation có thể xảy ra **khi commit sau khi method return**; facade cần bắt exception **bên ngoài transaction boundary**. Dùng transaction riêng (hoặc retry bounded sau xung đột) để đọc trạng thái đã commit.

Nếu đồng thời hai POST dùng cùng key, database unique constraint chỉ cho một bản ghi thắng. Facade còn cần so fingerprint, tenant và kết quả; retry không được làm phát thêm OrderCreated. Nếu không chắc create đã commit vì kết nối đứt, query **operation/order status** theo business reference thay vì tự khởi tạo event mới.

### Wire-level contract minh họa

~~~http
HTTP/1.1 201 Created
Location: /api/v1/orders/4f226ceb-1246-4594-9e6a-777e59db7677
Content-Type: application/json
Cache-Control: no-store

{
  "id": "4f226ceb-1246-4594-9e6a-777e59db7677",
  "status": "CREATED"
}
~~~

Response **201** có nghĩa order và outbox đã commit, **không** có nghĩa Inventory/Billing đã nhận event. Facade ở trên chọn **replay lại phản hồi 201 gốc** cho cùng key/payload (không tạo resource mới); một API khác có thể công bố trả 200 kèm resource hiện có. Điều quan trọng là **nhất quán và được tài liệu hóa**, không trả 201 mới với ID khác.

Nếu thao tác thực tế chỉ nhận **lệnh xử lý bất đồng bộ** và chưa tạo được order, dùng **202 Accepted + Location của operation resource**, rồi chuyển trạng thái PENDING/RUNNING/SUCCEEDED/FAILED. Không dùng 202 thay cho bằng chứng database commit nếu lời gọi chưa được durable-enqueue.

### HTTP status và lỗi liên quan

| Tình huống | Status gợi ý | Ý nghĩa |
| --- | --- | --- |
| Order + outbox commit | **201 Created** | Có order mới và event chờ chuyển |
| Cùng key/payload được replay | **201 cũ** hoặc 200 theo contract | Không có state change/event mới |
| Key reuse, khác payload | **409 Conflict** | Không được xử lý như request mới |
| JSON/validation sai | **400 Bad Request** | Không ghi order/outbox |
| Chưa có auth/thiếu quyền | **401/403** | Không dùng tenant client tự khai |
| Resource trong body ngoài tenant | **404/403** theo chính sách | Không rò dữ liệu của tenant khác |
| DB không commit, phụ thuộc tạm lỗi | **503 hoặc 500** tùy bản chất | Không khẳng định request có thể retry vô điều kiện |
| Event còn pending, downstream chưa xong | **Không phải lỗi HTTP tạo order** | Trạng thái nghiệp vụ downstream theo operation/resource |

**Broker outage không nhất thiết biến 201 thành 503**: nếu database commit được outbox và backlog chưa vượt giới hạn vận hành, request tạo order có thể thành công và relay gửi sau. Nếu outbox/DB không thể ghi bền vững, **rollback** và không trả 201 giả.

## 9. Event body và độ bền của JSON serialization

Outbox **không lưu một Java object tham chiếu mutable**. Event payload phải được tạo từ snapshot trạng thái mới **trong transaction**, serialize nhất quán và lưu thành bytes/JSON theo schema đã phiên bản hóa.

Ví dụ:

~~~java
public record OrderCreatedV1(
    UUID eventId,
    UUID orderId,
    String tenantId,
    long aggregateVersion,
    Instant occurredAt,
    long totalMinor,
    String currency,
    String status
) {}
~~~

Một entity outbox có thể lưu **event_id, event_type, schema_version, payload JSONB, tenant, aggregate ID/version**; relay **không cần deserialize lại OrderEntity** để “lấy dữ liệu mới nhất”. Nếu relay đọc lại entity lúc publish, event có thể chứa trạng thái đã đổi thêm sau khi event được tạo, làm sai ý nghĩa OrderCreated.

Khi payload có field Instant, BigDecimal, enum hoặc nullable field, quy định **JSON schema, định dạng số, timezone, field name và evolution rules**. Consumer cũ phải có chiến lược với field mới; nếu có thay đổi breaking, tăng schemaVersion và kiểm thử consumer compatibility.

**EventId là identity nghiệp vụ của event**, dùng cho de-duplicate; **correlationId** chỉ giúp tracing, không thể thay eventId vì nhiều sự kiện có thể cùng correlation. **operationId** liên kết HTTP/idempotency với workflow, không nên dùng một UUID mới cho mỗi attempt của cùng command đã ghi.

## 10. Polling relay: claim, publish, ACK và retry

Relay thường chạy như scheduled worker. Một sai lầm là **SELECT hàng PENDING rồi publish mà không có cơ chế claim nguyên tử**: hai worker có thể cùng chọn hàng đó. Dùng row lock/lease, giao dịch ngắn và thời gian retry cụ thể.

### Claim một batch bằng PostgreSQL SKIP LOCKED

Ví dụ SQL thực hiện trong **một transaction ngắn**:

~~~sql
WITH candidates AS (
    SELECT event_id
    FROM outbox_events
    WHERE
       (status = 'PENDING' AND next_attempt_at <= now())
       OR
       (status = 'IN_FLIGHT' AND leased_until < now())
    ORDER BY occurred_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT :batch_size
)
UPDATE outbox_events AS o
SET status = 'IN_FLIGHT',
    lease_owner = :claim_token,
    leased_until = now() + interval '30 seconds',
    attempts = attempts + 1
FROM candidates AS c
WHERE o.event_id = c.event_id
RETURNING o.*;
~~~

**claim_token** là UUID ngẫu nhiên **mới mỗi lần claim**, không phải ID cố định của worker cho mọi lần chạy. Điều kiện UPDATE/ACK sau đó cần token này để một worker cũ không xác nhận nhầm record đã bị worker mới chiếm khi lease hết hạn.

**FOR UPDATE SKIP LOCKED** cho nhiều relay đọc các row khác nhau mà không chờ nhau quá lâu; nó **không tự bảo đảm event cùng aggregate được phát đúng thứ tự**, cũng không xóa khả năng duplicate khi lease hết hạn hoặc broker ACK bị mất. Chỉ chạy claim trong transaction ngắn rồi **commit trước khi gọi network**.

Sau khi broker trả **publish ACK đúng durability policy**, đánh dấu:

~~~sql
UPDATE outbox_events
SET status = 'PUBLISHED',
    published_at = now(),
    lease_owner = NULL,
    leased_until = NULL
WHERE event_id = :event_id
  AND status = 'IN_FLIGHT'
  AND lease_owner = :claim_token;
~~~

Kiểm tra **rows affected = 1**. Nếu = 0, claim không còn thuộc worker; không được tự tin rằng record đã PUBLISHED, cần đọc/truy vết trạng thái và dựa vào consumer idempotency. Nếu broker trả lỗi hoặc timeout, thực hiện một UPDATE riêng có điều kiện claim token để chuyển về PENDING và đặt **next_attempt_at = now() + backoff**. Nếu worker chết trước UPDATE, **leased_until** giúp worker khác claim lại.

**Lease phải lớn hơn thời gian publish bounded**, hoặc có cơ chế gia hạn lease; batch lớn cùng thời gian gửi dài có thể khiến những record cuối mất lease khi chưa tới lượt. Dùng batch nhỏ, concurrency được giới hạn và đo thời gian xử lý. Không giữ transaction hoặc row lock khi đang chờ broker.

### Pseudocode Java/Spring cho relay

~~~java
@Configuration
@EnableScheduling
class OutboxSchedulingConfiguration {}

@Component
public class OutboxRelay {
    private final OutboxClaims claims;
    private final BrokerPublisher broker;

    public OutboxRelay(OutboxClaims claims,
                       BrokerPublisher broker) {
        this.claims = claims;
        this.broker = broker;
    }

    @Scheduled(fixedDelay = 200)
    public void drain() {
        UUID claimToken = UUID.randomUUID();
        List<OutboxRecord> batch =
            claims.claimAvailable(50, claimToken);
        // claimAvailable chạy @Transactional trong Spring bean khác.
        // Transaction đã commit trước khi publish.

        for (OutboxRecord record : batch) {
            try {
                broker.publishAndAwaitAck(
                    record.eventId(),
                    record.aggregateKey(),
                    record.payload());

                claims.markPublished(
                    record.eventId(), claimToken);
            } catch (Exception ex) {
                claims.scheduleRetry(
                    record.eventId(), claimToken,
                    Backoff.forAttempt(record.attempts()));
            }
        }
    }
}
~~~

**OutboxClaims, BrokerPublisher, OutboxRecord, Backoff** là abstraction cần hiện thực; code là skeleton. Mỗi method update trạng thái outbox nên thực hiện trong transaction riêng. Cần cấu hình **publisher ACK có ý nghĩa bền vững** (ví dụ Kafka acks/all/replication theo broker policy), delivery timeout, giới hạn in-flight và retry. **ACK của broker không có nghĩa consumer đã xử lý.**

Không log exception body/credentials tùy ý từ broker; log **eventId, eventType, aggregateKey đã kiểm soát, attempts, error category, latency**. Với exception không thể xử lý (schema/serialization/invalid destination), chuyển record sang **DEAD_LETTER** có cảnh báo và khả năng replay đã kiểm toán, không retry vô tận ở tần số cao.

### Những giới hạn của polling

- **Độ trễ** phụ thuộc polling interval, batch size, load/DB và số relay.
- Scan outbox lớn có thể gây áp lực DB; cần index, partition/archival và TTL đúng.
- **SKIP LOCKED** không bảo đảm công bằng tuyệt đối khi record lỗi được claim liên tục hoặc backlog lớn.
- **Multiple instances** có thể chạy relay, nhưng phải test lease, claim token, crash/restart và chuyển node.
- **One row/one broker ACK** không phải transaction phân tán. Nếu broker nhận event nhưng ACK không về, record sẽ phát lại.

## 11. Consumer idempotency: xử lý duplicate mà không nhân đôi side effect

**At-least-once delivery** có nghĩa cùng eventId có thể đến **nhiều lần**. Ví dụ Inventory nhận OrderCreated và reserve hàng; nếu mỗi lần delivery lại trừ tồn kho, sai lệch không thể khắc phục chỉ bằng producer có outbox.

Một **inbox/dedup table** ở database consumer:

~~~sql
CREATE TABLE consumed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Trong một transaction consumer:

~~~text
BEGIN
  INSERT INTO consumed_events(consumer_name, event_id)
    VALUES('inventory-reserver', eventId)
    ON CONFLICT DO NOTHING
  if inserted_rows == 0:
    COMMIT; ACK message; return   # Đã xử lý event này.
  else:
    verify event schema, tenant, aggregate/version policy
    apply reservation business change
    COMMIT
ACK message sau DB commit
~~~

**Ghi dedup marker và business change trong cùng transaction database của consumer**. Nếu transaction rollback, marker cũng rollback để event có thể được xử lý lại. Nếu DB commit nhưng ACK broker/offset fail, broker gửi lại; marker khiến consumer bỏ duplicate an toàn.

### Java/Spring consumer skeleton

~~~java
@Service
public class InventoryOrderConsumer {
    private final ConsumedEventRepository inbox;
    private final InventoryReservationService inventory;

    public InventoryOrderConsumer(
            ConsumedEventRepository inbox,
            InventoryReservationService inventory) {
        this.inbox = inbox;
        this.inventory = inventory;
    }

    @Transactional
    public void process(OrderCreatedV1 event) {
        boolean firstTime = inbox.tryInsert(
            "inventory-reserver", event.eventId());

        if (!firstTime) return;

        inventory.reserveForOrder(
            event.tenantId(), event.orderId());
        // Cùng DB transaction với inbox marker.
    }
}
~~~

Nếu reserveInventory gọi **một service khác qua HTTP** hoặc gửi email ngoài database, marker và side effect ấy **không nằm trong cùng DB transaction**. Để tránh duplicate phải dùng **outbox tiếp ở consumer**, downstream **Idempotency-Key**, hoặc quy trình điều phối bù trừ. Không hứa “inbox là đủ” cho mọi side effect.

**Đừng dùng correlationId làm dedup key.** Một yêu cầu tạo order có thể sinh OrderCreated, PaymentRequested, InventoryReserved cùng correlation; chỉ **eventId + consumer identity** (hoặc một business operation ID đúng nghĩa) mới phân biệt xử lý.

### Ordering của nhiều event cho cùng aggregate

Giả sử cùng order có:

~~~text
OrderCreated  (aggregateVersion=1)
OrderPaid     (aggregateVersion=2)
OrderCancelled(aggregateVersion=3)
~~~

Nếu relay A phát version 2 trước relay B phát version 1, consumer có thể thấy OrderPaid trước OrderCreated. **ORDER BY occurred_at + SKIP LOCKED chưa bảo đảm thứ tự** khi có nhiều worker, lease/transaction và broker partitions.

Các phương án:

- Partition event theo **tenant + aggregateId** và sử dụng broker key ổn định để các event của aggregate vào cùng partition; vẫn phải bảo đảm **producer không publish ngược thứ tự**.
- Chỉ cho **một event in-flight trên mỗi aggregate** hoặc serialization per aggregate ở relay, có index và kiểm thử race.
- Dùng **CDC theo database commit log** khi cần thứ tự commit tương đối đáng tin, vẫn phải thiết kế aggregate version/partition và giải quyết nhiều transaction/channels.
- Consumer lưu **lastAppliedVersion**, từ chối/đợi event vượt version kế tiếp, bỏ duplicate version đã xử lý, và có quy trình replay/reconciliation khi thiếu event.

**Version liên tục chỉ hợp lý khi mô hình phát đúng một event cho mỗi state revision.** Nếu một transaction phát nhiều event hoặc bỏ qua version do thay đổi không phát event, không áp cứng “phải nhận +1” mà không mô tả sequence riêng cho event stream.

## 12. CDC thay polling: trade-off kiến trúc

**Change Data Capture (CDC)** đọc thay đổi từ transaction log của database (ví dụ PostgreSQL WAL với Debezium), chuyển record outbox sang broker. Đây là một cách hiện thực phần relay; **không thay thế bước ghi outbox trong transaction nghiệp vụ**.

~~~mermaid
flowchart LR
    A[OrderService @Transactional] --> B[(Orders + Outbox)]
    B --> C[PostgreSQL WAL]
    C --> D[CDC Connector]
    D --> E[Broker topic]
    E --> F[Consumer dedup]
~~~

| Tiêu chí | Polling relay | CDC từ transaction log |
| --- | --- | --- |
| Triển khai | Scheduled worker, SQL claim/lease | Connector/replication slot, log capture |
| Tải database | Polling/index/UPDATE trạng thái | WAL stream, phụ thuộc retention/slot |
| Độ trễ | Phụ thuộc interval/batch | Thường thấp khi connector khỏe |
| Ordering | Phải tự bảo vệ per aggregate | Theo commit-log trong phạm vi nguồn, vẫn cần partition/consumer policy |
| Vận hành | Retry, dead-letter, archive, claim | Lag, connector restart, WAL retention, snapshot, schema evolution |
| Duplicate | Có khi ACK/lease lỗi | Có thể khi connector restart/replay |
| Khi phù hợp | Đội muốn kiểm soát SQL/ít hạ tầng hơn | Đã có CDC platform hoặc yêu cầu latency/throughput cao |

CDC có thể dùng **outbox event router** để định tuyến eventType/aggregateKey vào topic, nhưng phải cấu hình eventId/schemaVersion/tenant và routing key nhất quán. **Đừng dùng trigger trực tiếp gọi network**, vì DB transaction sẽ phụ thuộc broker; trigger ghi outbox trong DB có thể phù hợp nếu schema và quyền được kiểm soát.

Nếu connector dừng lâu, PostgreSQL **replication slot có thể giữ WAL** và làm đầy disk. Theo dõi connector lag, WAL retention, replication slot, permissions và recovery. Snapshot/restart cần kế hoạch tránh phát sự kiện cũ ngoài dự kiến; consumer vẫn phải idempotent.

## 13. Failure matrix: dự đoán trước khi production

| Điểm lỗi | Điều gì xảy ra? | Cách phục hồi an toàn |
| --- | --- | --- |
| DB insert order lỗi trước commit | Không có event commit | Rollback cả order/outbox; response lỗi phù hợp |
| Outbox insert lỗi | Transaction phải rollback order | Không trả 201 giả, báo sự cố lưu trữ |
| Process crash ngay sau commit | Order + outbox vẫn tồn tại | Relay đọc lại PENDING sau restart |
| Broker unavailable | Outbox tồn tại, backlog tăng | Retry/backoff, cảnh báo, không xóa event |
| Broker nhận, ACK về producer bị mất | Publish kết quả không rõ | Retry cùng eventId, consumer dedup |
| Relay crash sau ACK trước PUBLISHED | Event có thể phát lại | Claim lease hết hạn, retry, dedup |
| Relay claim hết lease khi publish chậm | Worker khác phát lại | Bounded timeout/lease renewal, dedup |
| Broker phát cùng message hai lần | Consumer nhận duplicate | Inbox unique + transaction |
| Consumer DB commit nhưng offset ACK lỗi | Consumer nhận lại event | Inbox marker bỏ duplicate |
| Consumer DB rollback | Broker redelivery | Inbox rollback, retry theo policy |
| Event payload không tương thích | Consumer liên tục lỗi | Schema/version validation, DLQ/quarantine, manual replay |
| Event phát ngược thứ tự aggregate | State transition sai | Aggregate sequence, key partition, serialization/reorder |
| DB commit outcome không rõ do network | Caller có thể retry | Idempotency lookup, không tạo operation mới bừa |

Một vài chiến lược cần chọn theo nghiệp vụ:

- **Poison event**: không gửi lại vô hạn đến khi toàn bộ partition bị chặn; chuyển quarantine/DLQ có quan sát và cách sửa schema/consumer.
- **Backpressure**: khi outbox backlog tăng tới mức không thể phục hồi kịp, cần giới hạn admission, scale relay hoặc giảm lưu lượng theo policy. Bảo đảm storage của outbox không đầy làm sập cả nghiệp vụ.
- **Reconciliation**: định kỳ so aggregate đã commit với các event/outbox tương ứng, phát hiện gap, re-drive event có chủ đích; không tự sinh event trùng mà không kiểm tra nguồn gốc.
- **Replay**: giữ eventId ổn định nếu chỉ redeliver cùng fact; nếu tạo một event sửa lỗi mới, dùng eventId mới và liên kết causation/reference với event gốc.

## 14. Security: outbox không phải vùng miễn trừ quyền truy cập

Outbox chứa sự kiện có thể được sao chép sang broker, data platform hoặc nhiều consumer. Vì vậy, một record nội bộ có thể tạo bề mặt rủi ro **lớn hơn** entity nguồn nếu payload chứa credential hay dữ liệu cá nhân.

### Bảo vệ ranh giới REST và database

- **Inbound authentication:** Spring Security phải xác thực JWT/opaque access token, issuer, audience và scopes; không chỉ decode JWT rồi tin claims.
- **Object-level authorization:** tenant/user trong order phải bắt nguồn từ principal và domain membership đã xác minh, không lấy từ JSON, query hoặc X-Tenant-Id không đáng tin.
- **Đừng log raw Idempotency-Key** nếu nó chứa định danh nhạy cảm. Giới hạn ký tự/độ dài và dùng fingerprint của payload canonical; nếu body dễ đoán hoặc có PII, xem xét HMAC với khóa riêng thay hash không khóa.
- **DB quyền tối thiểu:** app chỉ ghi đúng bảng outbox cần thiết; relay chỉ đọc/cập nhật trạng thái event; người vận hành không có quyền sửa payload tùy tiện.
- **Broker:** TLS/mTLS hoặc xác thực theo nền tảng, topic ACL per producer/consumer, rotate secrets; không public topic chỉ vì event “nội bộ”.
- **Replay/DLQ:** là thao tác đặc quyền vì có thể kích hoạt side effects; cần phê duyệt, audit và per-tenant boundary.

Ví dụ Spring Security cho API tạo order:

~~~java
@Configuration
@EnableMethodSecurity
class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.POST, "/api/v1/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .sessionManagement(s -> s
                .sessionCreationPolicy(
                    SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .build();
    }
}
~~~

Đây là **mẫu cho Bearer-only API**, không phải cấu hình hoàn chỉnh của ứng dụng có cookie/session. Cần chain fallback bảo vệ các URI ngoài /api/**, validator issuer/audience và rule quyền đọc/sửa resource. **CSRF không nên disable mù** cho authentication dựa trên cookie. Scope chỉ là tầng đầu; service còn phải xác minh cartId/shippingAddressId thuộc caller.

### Tối thiểu hóa payload và bảo vệ riêng tư

Không ghi vào outbox: access/refresh token, password, API key, số thẻ/CVV, toàn bộ DTO, exception stack trace, raw request headers hoặc nội dung liên hệ cá nhân không cần thiết. Nếu Billing thực sự cần thông tin nhạy cảm, cân nhắc **fetch qua API có authorization** bằng orderId thay vì phát tán tới mọi subscriber.

Dùng event schema có version và field allowlist; mã hóa at rest/in transit; quy định retention cho outbox, broker, DLQ, archive và backup. **Immutable event không đồng nghĩa lưu mãi**, và dữ liệu pseudonymized vẫn có thể thuộc phạm vi chính sách bảo vệ dữ liệu.

## 15. Vận hành: backlog, retention và đối soát

| Metric | Câu hỏi |
| --- | --- |
| **outbox_pending_count** | Bao nhiêu event chưa publish? |
| **oldest_pending_age_seconds** | Event lâu nhất chờ bao lâu? |
| **publish_retry_total / errors** | Broker hoặc mapping đang lỗi? |
| **published_lag_seconds** | Event chờ từ occurredAt đến broker ACK bao lâu? |
| **consumer_processing_lag** | Sau khi broker nhận, bao lâu consumer áp trạng thái? |
| **dead_letter_count** | Bao nhiêu event cần con người can thiệp? |
| **duplicate_detected_total** | Bao nhiêu redelivery đã được chặn? |
| **outbox_storage / WAL_lag** | DB/CDC có nguy cơ đầy ổ đĩa? |

Dùng route group, event type, error category, broker và tenant tier làm metric label; **không dùng eventId, orderId, userId hoặc raw URL làm nhãn có cardinality cao**. Structured log có eventId/correlationId giúp tra cứu nhưng phải redaction payload/token.

### Dọn dữ liệu an toàn

- Với polling, chỉ purge hoặc archive **PUBLISHED** theo chính sách sau khi chắc chắn có broker ACK bền vững. Không xóa PENDING hoặc IN_FLIGHT để giảm backlog.
- Với CDC, cân nhắc **replication slot, WAL retention, connector offsets và snapshot behavior** trước khi đổi chiến lược cleanup.
- Partition/archival theo thời gian có thể cần khi lưu lượng cao; đừng drop cả partition còn event cần replay hoặc legal hold.
- Khi backlog vượt ngưỡng chịu đựng, scale relay, giới hạn admission/cost hoặc dùng degraded mode theo runbook; không để storage đầy mà không có cảnh báo.

**Failure policy:** Nếu transaction không thể lưu outbox, **rollback nghiệp vụ** và không trả 201. Nếu outbox đã commit, broker chỉ đang chậm và backlog còn trong mức an toàn, API vẫn có thể trả 201; nếu mất khả năng vận hành/khôi phục trong SLO, nên có policy kiểm soát nhận request mới. Không để trạng thái HTTP phụ thuộc ngẫu nhiên vào thời điểm broker timeout.

### Reconciliation

Định kỳ đối soát **committed aggregate changes với event/outbox records và downstream progress**, tìm gap, replay có chủ đích. Sự kiện gốc replay phải giữ **cùng eventId**; nếu cần một fact sửa sai mới, tạo **eventId khác**, liên kết causation với sự kiện cũ. Replay không được bỏ qua inbox/dedup hoặc quyền tenant.

## 16. OpenAPI 3.1: công bố 201 trước khi downstream hoàn tất

Một hợp đồng rút gọn cho Orders API:

~~~yaml
openapi: 3.1.0
info: { title: Orders API, version: 1.0.0 }
paths:
  /api/v1/orders:
    post:
      summary: Tạo order và ghi outbox trong cùng DB transaction
      description: >
        201 nghĩa order cùng outbox đã commit.
        Inventory/Billing xử lý bất đồng bộ.
        Retry cùng tenant, key, body trả lại kết quả gốc;
        key cũ với body khác nhận 409.
      security:
        - bearerAuth: []
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema: { type: string, minLength: 1, maxLength: 120 }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [cartId, shippingAddressId]
              additionalProperties: false
              properties:
                cartId: { type: string, minLength: 1 }
                shippingAddressId: { type: string, minLength: 1 }
      responses:
        '201':
          description: Order và event outbox đã commit
          headers:
            Location:
              required: true
              schema: { type: string, format: uri-reference }
          content:
            application/json:
              schema: { $ref: '#/components/schemas/OrderResponse' }
        '400':
          description: Request hoặc idempotency key không hợp lệ
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/ApiProblem' }
        '401':
          description: Thiếu token hoặc token không hợp lệ
          headers:
            WWW-Authenticate:
              schema: { type: string }
        '403': { description: Caller thiếu quyền }
        '404': { description: Cart hoặc địa chỉ ngoài phạm vi caller }
        '409':
          description: Idempotency-Key đã dùng với payload khác
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/ApiProblem' }
        '503':
          description: Không thể ghi bền vững hoặc đang quá tải
          content:
            application/problem+json:
              schema: { $ref: '#/components/schemas/ApiProblem' }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
  schemas:
    OrderResponse:
      type: object
      required: [id, status]
      properties:
        id: { type: string, format: uuid }
        status: { type: string, const: CREATED }
    ApiProblem:
      type: object
      properties:
        type: { type: string, format: uri-reference }
        title: { type: string }
        status: { type: integer }
        detail: { type: string }
        code: { type: string }
~~~

**OpenAPI không tự tạo transaction hay consumer idempotency**. Một service dùng API ở trên không được diễn giải 201 là hàng đã được reserve hoặc đã thanh toán. Nếu client cần biết trạng thái workflow dài, bổ sung GET order/fulfillment status, hoặc thiết kế riêng **202 Accepted + Location của operation resource** khi request chỉ mới được lưu để xử lý bất đồng bộ.

## 17. Kiểm thử: phải chứng minh commit, duplicate và phục hồi

Unit test gọi mock repository rồi assert verify(save) **không chứng minh database transaction atomic**. Cần kết hợp **MockMvc/security tests**, **PostgreSQL integration** (ví dụ Testcontainers), **broker/relay integration**, concurrency và fault injection. Nên thực hiện test trong môi trường giới hạn tài nguyên, không gửi message thật đến production topic.

### HTTP + database: happy path

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrderOutboxIntegrationTest {
    @Autowired MockMvc mockMvc;
    @Autowired OrderRepository orders;
    @Autowired OutboxRepository outbox;

    @Test
    void oneHttpCreateCommitsOrderAndOutbox()
            throws Exception {

        MvcResult result = mockMvc.perform(
                post("/api/v1/orders")
                    .with(jwt()
                        .jwt(j -> j.subject("buyer-1")
                            .claim("tenant_id", "tenant-a"))
                        .authorities(
                            new SimpleGrantedAuthority(
                                "SCOPE_orders:write")))
                    .header("Idempotency-Key", "checkout-841")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                      {"cartId":"cart-42",
                       "shippingAddressId":"addr-8"}
                      """))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andReturn();

        String location = result.getResponse()
            .getHeader("Location");
        UUID id = UUID.fromString(
            location.substring(location.lastIndexOf('/') + 1));

        assertThat(orders.findById(id)).isPresent();
        assertThat(outbox.countByAggregateIdAndEventType(
            id, "OrderCreated")).isEqualTo(1L);
    }
}
~~~

Test giả định có fixtures **cart-42, addr-8 thuộc buyer-1/tenant-a**, policy cho phép người dùng, mapper, schema và các repository methods tương ứng. Phải bật @EnableMethodSecurity. **jwt() trong spring-security-test tạo authentication giả, không kiểm tra JWT signature/issuer/audience**; tạo test khác với JWT ký bằng key test và mock JWKS/introspection nếu cần xác minh resource server thực.

**Tránh đặt @Transactional lên toàn test method** khi muốn kiểm tra commit của request: test-level transaction/rollback có thể che lỗi xuất hiện lúc transaction commit. Sau HTTP 201, đọc lại database ở một transaction riêng; dùng PostgreSQL thực hoặc Testcontainers tương đương production để kiểm tra unique constraint.

### Fault injection và concurrent requests

| Ca thử | Bất biến cần assert |
| --- | --- |
| Happy path | Một order + một outbox OrderCreated sau 201 |
| Outbox INSERT lỗi | **Order rollback**, không có state change không kèm event |
| Order INSERT/commit lỗi | **Outbox rollback**, không có event mồ côi |
| Hai POST đồng thời cùng tenant/key/payload | Một order/event, kết quả replay cùng resource |
| Hai POST cùng key khác payload | 409, không sửa order/event cũ |
| Hai tenant trùng key | Hai scope độc lập, không replay sai tenant |
| 401/403 hoặc cart/addr ngoài tenant | Không ghi order/outbox, không rò resource |
| Crash sau commit trước publish | Record PENDING còn, worker sau restart tiếp tục |
| Broker nhận event, ACK mất | Publish lại **cùng eventId**, consumer business effect đúng một lần |
| Crash sau ACK trước đánh dấu PUBLISHED | Duplicate delivery vẫn an toàn |
| Hai relay claim cùng thời điểm | Không cùng sở hữu một row khi lease hợp lệ |
| Lease hết hạn + late ACK | Claim token cũ không ghi đè kết quả claim mới |
| Consumer transaction rollback | Inbox dedup marker rollback, retry có thể xử lý |
| Event thiếu schema hoặc sai version | Quarantine/DLQ và alert, không mất âm thầm |
| Version 2 đến trước version 1 | Ordering/reconciliation policy đúng |
| Broker/CDC down lâu | Backlog/WAL metric cảnh báo, storage không cạn âm thầm |
| Outbox payload/log | Không chứa token, secrets hoặc PII không cần thiết |

**Inject lỗi đúng ranh giới:** để outbox repository ném exception lúc flush; kill relay sau broker ACK; mô phỏng producer timeout sau broker đã nhận; kill consumer sau DB commit trước offset ACK; ép lease expire. Với các lỗi này, chỉ mock method publish luôn trả success không đủ để chứng minh tính đúng.

### Test consumer dedup với database thật

~~~text
1. Gửi OrderCreated(eventId = E) lần thứ nhất.
2. Consumer bắt đầu transaction, insert inbox(E), reserve hàng.
3. Commit consumer DB, nhưng không ACK broker.
4. Gửi lại cùng eventId = E.
5. INSERT inbox(E) gặp duplicate, không reserve lần hai.
6. Assert: count(inbox E) = 1, inventory reservation = 1.
7. Gửi event hợp lệ mới E2 cho một order khác:
   hệ thống vẫn xử lý bình thường.
~~~

Nếu side effect là gửi email hoặc gọi Payment API, test **idempotency của downstream** riêng; inbox marker ở database consumer không đủ cho side effect nằm ngoài transaction đó.

## 18. Bài tập: đơn hàng, kho và thanh toán bất đồng bộ

Bạn triển khai **Orders API** với PostgreSQL, Kafka và hai consumer Inventory/Billing. Người dùng có thể bấm tạo đơn hai lần khi mạng chập chờn, Kafka có thể ngừng vài phút, và một consumer có thể crash sau khi ghi database nhưng trước khi ACK.

Yêu cầu:

1. Vẽ **dual-write timeline** cho ít nhất ba lỗi: DB commit trước publish, publish trước rollback, ACK mất rồi retry.
2. Thiết kế **orders / outbox_events / idempotency state** với unique constraint, status, lease, next_attempt_at, eventId và fingerprint.
3. Viết Java/Spring endpoint nhận **Idempotency-Key**; service @Transactional ghi order + outbox, kiểm tra tenant/scope, trả 201/409/503 đúng nghĩa.
4. Cài **polling relay** có SKIP LOCKED, claim token, lease, backoff và markPublished chỉ sau ACK. Giải thích lựa chọn khác là **CDC**.
5. Viết consumer Inventory với **inbox unique(consumer,eventId)** và transaction áp business state. Mô tả xử lý khi OrderPaid đến trước OrderCreated.
6. Thử **100 POST concurrent** từ hai API instance với cùng key: chỉ một order/event; với hai payload khác nhau, một kết quả hoặc 409 tùy thứ tự.
7. Viết tối thiểu **12 test** bao gồm rollback, broker outage, ack-loss, late ACK, duplicate, out-of-order, tenant isolation và token sai.
8. Đề xuất dashboard backlog, DLQ, replay runbook, retention/PII và lúc nào hệ thống phải từ chối request mới.

**Sản phẩm nộp:** hợp đồng HTTP/OpenAPI, schema SQL, code Spring, relay pseudocode, event JSON schema, bảng failure modes, kết quả test và một ADR nêu rõ bảo đảm đạt được/chưa đạt được.

### Câu hỏi mở rộng

- Nếu cần thanh toán xong *trước khi* thông báo “Đơn đã xác nhận”, chỉ có outbox là đủ chưa? Nên bổ sung **Saga/process manager** với trạng thái CREATED, PAYMENT_PENDING, PAID, FAILED và compensation như thế nào?
- Nếu giá/thông tin order có thể đổi trước khi relay phát, vì sao event phải chứa snapshot hoặc version lúc commit thay vì truy vấn lại state mới nhất?
- Nếu bắt buộc bảo toàn thứ tự theo aggregate qua ba relay worker, chọn serialize per-aggregate, partition key hay CDC theo commit-log? Bạn sẽ test trường hợp nào để chứng minh?

## 19. Checklist và kết luận

| Kiểm tra | Tiêu chí hoàn thành |
| --- | --- |
| Có đúng dual-write boundary? | Order và outbox **cùng một DB transaction**, không gửi broker ở giữa |
| Có event contract? | eventId, type/version, aggregateId/version, tenant, timestamp, payload tối thiểu |
| Có HTTP semantics? | 201 sau commit, 202 chỉ khi operation bền vững, 409 khi key reuse khác payload |
| Có idempotency? | Cùng tenant/key/body trả kết quả cũ, concurrent unique constraint |
| Relay atomic? | Claim/lease, retry/backoff, markPublished sau ACK và token chống stale worker |
| Chấp nhận duplicate? | At-least-once, consumer inbox trong transaction, idempotent downstream |
| Có yêu cầu ordering? | Key/sequence/per-aggregate serialization và gap detection khi cần |
| Có phục hồi? | Broker/CDC outage, crash windows, DLQ, replay, reconciliation |
| Có security? | Tenant authz, TLS/topic ACL, no secrets/PII thừa, quyền replay/retention |
| Có vận hành và test? | Lag/oldest pending, database/broker integration, concurrency/fault injection |

**Kết luận:** Transactional Outbox không biến nhiều service thành một transaction phân tán. Nó giải quyết ranh giới quan trọng nhất bằng cách **lưu thay đổi nghiệp vụ và ý định phát event cùng một commit**, rồi **chuyển bất đồng bộ có retry**. Kết hợp **consumer idempotency, ordering policy, kiểm soát tenant, HTTP contract và quan sát backlog** mới tạo thành một giải pháp nhất quán nghiệp vụ đáng tin trong hệ thống REST API phân tán.









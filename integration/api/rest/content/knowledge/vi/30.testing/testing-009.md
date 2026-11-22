# Kiểm thử chống trùng khi retry sau timeout

## 1. Timeout không trả lời câu hỏi “server đã ghi chưa?”

Một khách hàng gửi `POST /v1/orders` để đặt hàng. Primary database đã commit đơn `o-42`, nhưng kết nối mạng đứt **trước khi client nhận `201 Created`**. Client chỉ nhìn thấy timeout và gửi lại request. Nếu server chạy lệnh INSERT lần nữa, khách hàng có hai đơn dù chỉ muốn đặt một lần.

~~~mermaid
sequenceDiagram
    participant C as Java client
    participant A as REST API
    participant D as Primary DB
    C->>A: POST /v1/orders + Idempotency-Key K
    A->>D: INSERT order + ledger K (một transaction)
    D-->>A: COMMIT thành công
    Note over A,C: Response bị mất / client timeout
    C--xA: Không nhận được 201
    C->>A: Retry POST với cùng key K và payload
    A->>D: Tra ledger K theo actor/tenant/operation
    D-->>A: COMPLETED + outcome đã lưu
    A-->>C: Replay 201 + cùng Location/body
    Note over C,D: Chỉ một order được tạo
~~~

**Timeout là kết quả quan sát ở phía gọi, không phải kết quả transaction.** Nó có thể xảy ra trước khi request tới server, lúc đang xử lý, sau commit hoặc trong đường response trở về. Không được khẳng định “timeout nên chắc chắn rollback”, cũng không được retry bằng khóa mới cho cùng ý định nghiệp vụ.

Bài thuộc chương **Kiểm thử** của module **INTEGRATION_API_REST**: học REST resource, URI, HTTP methods/status, hợp đồng dữ liệu, phân trang/cache, idempotency, OpenAPI, xác thực, phân quyền, xử lý lỗi và kiểm thử Java/Spring. Trọng tâm ở đây là **cách chứng minh chống trùng dưới failure injection và concurrency**, không chỉ thêm header rồi gọi thử hai lần.

Sau bài học, bạn sẽ biết thiết kế test oracle về side effect, xây dữ liệu/transaction ledger, mô phỏng lỗi trước và sau commit, kiểm thử retry cùng key/khác payload, race condition, lỗi ở downstream, và đưa các tình huống này vào Spring Boot/JUnit/HTTP integration tests.

## 2. Định nghĩa chính xác bất biến và hợp đồng retry

Một test có ý nghĩa cần bắt đầu bằng **điều phải luôn đúng**:

> Trong phạm vi `(tenant, actor, operation, idempotency key)` và một ý định nghiệp vụ xác định, tối đa **một** side effect tạo đơn được commit; mọi retry hợp lệ có kết quả nhất quán, kể cả khi response đầu bị mất.

Ở đây “một lần” là **hiệu ứng nghiệp vụ**; server có thể nhận và xử lý nhiều HTTP request, nhiều lần đọc ledger, hoặc nhiều lần trả response. Không tuyên bố mạng phân tán có “exactly once delivery” chỉ vì dùng `Idempotency-Key`.

### 2.1. Một hợp đồng HTTP cụ thể để kiểm thử

Ví dụ API quy định header `Idempotency-Key` là **opaque key** do client tạo cho mỗi ý định tạo order, có thể theo cú pháp Structured Field String nếu API chọn theo đặc tả idempotency-key tương ứng:

~~~http
POST /v1/orders HTTP/1.1
Authorization: Bearer <redacted>
Content-Type: application/json
Idempotency-Key: "bc2197a0-10bd-40a7-9fe5-dc38c5692a03"

{"productId":"sku-7","quantity":2}

HTTP/1.1 201 Created
Location: /v1/orders/o-42
Content-Type: application/json
Cache-Control: no-store

{"id":"o-42","productId":"sku-7","quantity":2,"status":"CREATED"}
~~~

Khi request giống hệt ý định được gửi lại với **cùng key**, server trong ví dụ trả **201, cùng `Location` và body đã lưu**. Header phụ như `Idempotency-Replayed: true` có thể được thêm **nếu API tự định nghĩa**; không giả định header này được chuẩn hóa hoặc bắt buộc ở mọi server.

| Tình huống | Kết quả hợp đồng mẫu | Test cần chứng minh |
|---|---|---|
| Lần đầu, commit thành công | `201` + `Location`/JSON | Tạo đúng một order và một ledger completed |
| Retry cùng key, payload cùng ý định sau commit | Replay `201` + response cũ | Không thêm order/event/payment |
| Cùng key, payload khác | `422 Unprocessable Content` | Không thêm side effect, không thay outcome cũ |
| Cùng key trong lúc request đầu chưa kết thúc | `409 Conflict` + `Retry-After` **hoặc** chờ ngắn theo policy | Không có hai transaction cùng tạo đơn |
| Key mới cho **ý định mới** | `201` mới nếu nghiệp vụ cho phép | Không vô tình gộp hai đơn hợp lệ |
| Không gửi key ở operation bắt buộc | `400` theo hợp đồng | Từ chối trước khi ghi |
| Đã hết thời gian lưu key | Theo chính sách TTL/cửa sổ dedupe đã công bố | Không hứa replay vô hạn |

**201/409/422 là lựa chọn hợp đồng của ví dụ**, không có nghĩa mọi dịch vụ phải dùng cùng status/body; API có thể trả 200 khi replay, 202 trong lúc xử lý hoặc response bất đồng bộ. Test phải phản ánh **OpenAPI và chính sách đã công bố**. `Retry-After` có thể là giây hoặc HTTP-date, client phải giới hạn retry/deadline.

### 2.2. Scope: khóa không phải định danh toàn cục

Chỉ lưu key `K` rồi kiểm unique toàn hệ thống dễ tạo **cross-tenant collision/denial of service**: user A có thể chiếm key user B định sử dụng. Một scope phổ biến:

~~~text
tenantId  = lấy từ principal/tenant membership đã xác thực
actorId   = chủ ý định (subject hoặc client service identity đáng tin)
operation = "POST /v1/orders" (route template/canonical operation ID)
key       = opaque string client cung cấp, được validate giới hạn length/charset
hash      = fingerprint của method + operation + body canonical theo contract
~~~

Không dùng raw `Authorization`, email, tên user hay `jti` làm key chính: token refresh làm thay đổi dữ liệu, và log/storage key có thể lộ PII. Không tin `tenantId` hoặc `actorId` do client tự gửi trong body/header; **scope bắt nguồn từ security context được xác minh**.

### 2.3. Fingerprint phải gắn với ý định, không chỉ chuỗi JSON

Hai payload biểu diễn cùng nội dung có thể khác khoảng trắng hoặc thứ tự property; ngược lại, hai request có cùng body nhưng khác operation/tenant **không cùng ý định**. Server cần chính sách rõ:

- Với DTO có field cố định, tạo fingerprint từ **các field đã validate và chuẩn hóa** như `productId, quantity, currency, destination` theo thứ tự cố định.
- Nếu tính hash từ raw bytes, phải công bố rằng khác whitespace/field order cũng có thể được xem là payload khác.
- Không âm thầm bỏ field có ảnh hưởng nghiệp vụ (ví dụ địa chỉ giao hàng), nếu không retry cùng key nhưng thay address vẫn có thể nhận nhầm outcome.
- Dùng hash cryptographic phù hợp; không lưu raw body có PII chỉ để so sánh, không dùng log hash làm định danh người dùng lâu dài.

**Thử lại cùng key nhưng payload khác** phải cho lỗi rõ ràng, không tạo thêm đơn và không trả outcome cũ như thể request mới đã thành công.

## 3. Ledger và transaction là cơ sở để test chống trùng

Một `ConcurrentHashMap` trong Spring singleton có thể ngăn hai request trong **một JVM**, nhưng không bảo đảm khi có nhiều Pod, restart hoặc failover. Để test retry sau timeout một cách thực chất, trạng thái dedupe phải **bền vững và có ràng buộc duy nhất** ở nơi giữ bất biến nghiệp vụ.

### 3.1. PostgreSQL: unique constraint và outcome bền vững

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    customer_id UUID NOT NULL,
    product_id TEXT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    status TEXT NOT NULL
);

CREATE TABLE api_idempotency (
    id BIGSERIAL PRIMARY KEY,
    tenant_id UUID NOT NULL,
    actor_id UUID NOT NULL,
    operation TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('IN_PROGRESS','COMPLETED')),
    order_id UUID NULL,
    http_status INT NULL,
    location TEXT NULL,
    response_json TEXT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_idempotency_scope
      UNIQUE (tenant_id, actor_id, operation, idem_key)
);

CREATE INDEX idx_idempotency_expiry
    ON api_idempotency (expires_at);
~~~

Trong mẫu **tạo order và ledger cùng một database**, một transaction nên làm:

~~~text
BEGIN;
  INSERT ledger (K, requestHash, IN_PROGRESS)
    ON CONFLICT DO NOTHING
    -- unique constraint tranh chấp sẽ serialize competing inserts
  nếu claim thành công:
      INSERT orders
      UPDATE ledger -> COMPLETED + orderId + 201 + Location + body snapshot
  nếu claim thất bại:
      SELECT ledger sau khi winner commit
      kiểm requestHash, replay outcome hoặc trả mismatch
COMMIT;
~~~

**Bất biến commit:** không có trạng thái “ledger COMPLETED nhưng order chưa commit” hay “order đã commit nhưng ledger chưa ghi” nếu hai bảng cùng transaction và adapter không mở transaction khác. Thứ tự trong transaction có thể khác, nhưng **atomic commit** phải bao trọn cả hai. Với PostgreSQL, `INSERT ... ON CONFLICT DO NOTHING` có thể **chờ transaction đang giữ unique key** rồi xác định winner; một `SELECT` tiếp theo dưới `READ COMMITTED` sẽ thấy row mới commit. Nếu test dùng isolation/snapshot khác, phải kiểm tra hành vi DB đó thay vì suy từ mock.

**Snapshot outcome có chủ đích:** nếu retry đọc trực tiếp `orders` đã đổi từ `CREATED` sang `PAID`, response replay không còn giống request ban đầu. Lưu `http_status, location, response_json` (hoặc một outcome đủ tái tạo có version) để quyết định replay ổn định. Không lưu secret/JWT/headers nhạy cảm trong ledger. Không cache bất biến response chứa URL ký có TTL ngắn mà không thiết kế lại replay/renewal.

### 3.2. Vì sao test “2 POST, 1 row” vẫn có thể sai?

Một flow kém có thể chạy:

~~~text
T1: SELECT ledger(K) -> absent
T2: SELECT ledger(K) -> absent
T1: INSERT order o1
T2: INSERT order o2
T1: INSERT ledger K
T2: INSERT ledger K -> unique violation
~~~

Nếu T2 đã commit order o2 **trước** khi ghi ledger trong transaction độc lập, unique constraint ledger không cứu được side effect. Test phải **đếm order hoặc dòng nghiệp vụ thật**, không chỉ đếm ledger. Nếu side effect là gửi email, tạo payment ở provider hoặc phát event, kiểm tra các tác dụng ấy riêng.

### 3.3. Hai kiểu trạng thái IN_PROGRESS

| Thiết kế | Hành vi khi request thứ hai tới | Cách test |
|---|---|---|
| **Atomic synchronous transaction**: ledger IN_PROGRESS chưa commit, complete trong cùng transaction | Competing insert có thể chờ unique lock đến commit/rollback rồi replay/tự claim | Hai HTTP request đồng thời, DB row count và timeout DB |
| **Durable operation state**: ledger IN_PROGRESS đã commit, worker xử lý về sau | Server thấy state và có thể trả `409` hoặc `202`, rồi retry/poll | Test lease, crash/recovery, event outbox, completion và duplicate worker |

Không trộn hai kiểu rồi giả định `IN_PROGRESS` luôn phải trả HTTP 409: ở kiểu synchronous, transaction khác có thể **không nhìn thấy** row chưa commit; chỉ khi được xử lý theo policy mới trả 409. Nếu giữ database transaction mở trong lúc gọi payment gateway vài giây, hệ thống có thể lock dài và quá tải; đó là lý do dùng **durable operation + outbox + provider idempotency** cho side effect bên ngoài.

## 4. Ma trận lỗi theo điểm cắt: các test phải làm chủ thời điểm

Điểm quan trọng nhất là biết **fault xảy ra trước hay sau primary commit**:

| Điểm cắt | Ghi đã commit? | Lần retry được phép làm gì? | Test oracle |
|---|---|---|---|
| F1: client chưa gửi đủ request | Chưa chắc server nhận | Có thể gửi lại cùng K | ≤1 order, không assumption “server chưa nhận” |
| F2: server validate rồi crash trước DB transaction | Chưa | Retry có thể tạo order một lần | 1 order, ledger completed |
| F3: đã claim ledger **chưa commit**, crash/rollback | Chưa | Retry claim K rồi tạo một lần | Không có order/ledger mồ côi sau rollback |
| F4: order + ledger commit, **response bị mất** | **Rồi** | Replay outcome, không tạo mới | **1 order**, cùng Location/body |
| F5: hai request K đồng thời khi chưa commit | Một winner được commit | Loser chờ/replay/409 theo contract | Không duplicate, không deadlock kéo dài |
| F6: commit xong rồi process restart/failover | Rồi nếu storage bền vững | Replay sau restart | Ledger tồn tại, business count vẫn 1 |
| F7: cùng K, đổi quantity/product/address | Có thể đã có K | Từ chối payload mismatch | `422`, không sửa order/outcome đầu |
| F8: key mới cho cùng body | Hai ý định theo API contract | Có thể tạo mới (trừ business unique rule) | Không khẳng định dedupe mọi POST không có K |
| F9: key từ tenant B trùng key tenant A | Hai scope độc lập | Không lộ outcome A hoặc chặn B oan | Không cross-tenant replay |
| F10: key hết retention, retry đến muộn | Không còn dedupe record | Theo contract có thể tạo lại | Test expiry, client deadline, rủi ro duplicate |
| F11: payment provider timeout sau nhận tiền | Outcome ngoài DB chưa biết | Query/reconcile hoặc retry với **provider key cũ** | Không charge hai lần |
| F12: rate limiter/proxy từ chối trước app | Không có business side effect | `429`/`503` theo policy | Ledger không bị ghi vô cớ |

Test kiểu “gọi `Thread.sleep(1000)` rồi hy vọng trùng race” dễ flaky. Dùng **`CountDownLatch`/barrier, test hooks có kiểm soát, transaction blocking, network proxy/fault injection**, và luôn đặt timeout tối đa. Fault injection phải nằm ở **điểm cắt được quan sát**: ngắt socket trước khi server nhận không chứng minh tình huống **commit xong mới mất response**.

### 4.1. Ba mức kiểm thử khác nhau

~~~mermaid
flowchart TB
    U["Unit: decision/fingerprint/state machine"]
    I["Integration: Spring + Postgres + unique constraint"]
    E["End-to-end: HTTP client + proxy/drop response + server restart"]
    U --> I --> E
~~~

- **Unit:** kiểm canonical fingerprint, route scope, request mismatch, state transitions, backoff/deadline; nhanh nhưng không chứng minh DB atomicity.
- **HTTP/DB integration:** gọi Spring MVC bằng `MockMvc` hoặc HTTP test server, dùng PostgreSQL thật/test container; kiểm row count, saved outcome, transaction rollback và concurrency.
- **Network/failure end-to-end:** điều khiển client read timeout, proxy drop response sau khi server commit, kill/restart app, lỗi DB/network và downstream; phân biệt request thành công trên server với kết quả client nhìn thấy.

Đừng chỉ assert HTTP status: test phải xem **tác dụng phụ đã commit**. Đồng thời đừng dùng mọi test như một e2e chậm; chọn bộ deterministic ở tầng thấp và chỉ vài test fault thực ở tầng cao.

## 5. Java/Spring: mẫu service đủ rõ để kiểm thử transaction

Ví dụ sau dùng **Java 17+, Spring Boot 3.x, Spring MVC, Spring JDBC, PostgreSQL** và Spring Security Resource Server. Mục tiêu là nhìn thấy **ranh giới transaction**, không phải triển khai một thư viện idempotency hoàn chỉnh. Các lớp `Actor`, `PayloadMismatchException`, `KeyParser` và DTO là kiểu của ứng dụng.

### 5.1. DTO và kết quả đã lưu

~~~java
record Actor(UUID tenantId, UUID subjectId) {}

record CreateOrderRequest(String productId, int quantity) {}

record CreatedOrder(UUID id, String productId,
                    int quantity, String status) {}

record CreationOutcome(int httpStatus, String location,
                       String responseJson, boolean replay) {}

record StoredOutcome(String requestHash, String state,
                     int httpStatus, String location, String responseJson) {}
~~~

HTTP contract xác định **business intention** qua product/quantity (ứng dụng thực còn có shipping, currency, voucher…). `Actor` được rút ra từ JWT **đã xác minh** và membership; không tin tenant lấy từ JSON. Fingerprint hash phải dựa vào **cùng representation canonical mà server xử lý**, không bỏ các field có ảnh hưởng side effect.

### 5.2. Một transaction claim K, tạo đơn và đóng ledger

~~~java
@Service
class OrderCreationService {
    private final JdbcTemplate jdbc;     // Primary datasource
    private final ObjectMapper json;

    OrderCreationService(JdbcTemplate jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Transactional
    public CreationOutcome create(
            Actor actor, String key, CreateOrderRequest body) {
        if (body.productId() == null || body.productId().isBlank()
                || body.quantity() < 1 || body.quantity() > 100) {
            throw new IllegalArgumentException("Invalid order data");
        }
        if (key == null || key.length() < 8 || key.length() > 128) {
            throw new IllegalArgumentException("Invalid idempotency key");
        }
        // Ứng dụng phải parse/chuẩn hóa header theo contract trước khi gọi.
        String hash = fingerprint(body);

        List<Long> claimed = jdbc.query("""
            INSERT INTO api_idempotency (
              tenant_id, actor_id, operation, idem_key,
              request_hash, state, expires_at)
            VALUES (?, ?, 'orders.create', ?, ?, 'IN_PROGRESS',
                    now() + interval '24 hours')
            ON CONFLICT (tenant_id, actor_id, operation, idem_key)
            DO NOTHING RETURNING id
            """,
            (rs, i) -> rs.getLong("id"),
            actor.tenantId(), actor.subjectId(), key, hash);

        if (claimed.isEmpty()) {
            List<StoredOutcome> prior = jdbc.query("""
                SELECT request_hash, state, http_status, location,
                       response_json
                FROM api_idempotency
                WHERE tenant_id = ? AND actor_id = ?
                  AND operation = 'orders.create' AND idem_key = ?
                """,
                (rs, i) -> new StoredOutcome(
                    rs.getString(1), rs.getString(2), rs.getInt(3),
                    rs.getString(4), rs.getString(5)),
                actor.tenantId(), actor.subjectId(), key);

            if (prior.isEmpty()) {
                // Ví dụ có thể do cleanup/failover race;
                // cần policy bounded retry/reconciliation riêng.
                throw new RetryableLedgerRaceException();
            }
            StoredOutcome old = prior.get(0);
            if (!old.requestHash().equals(hash)) {
                throw new PayloadMismatchException();
            }
            if (!old.state().equals("COMPLETED")) {
                throw new RequestStillProcessingException();
            }
            return new CreationOutcome(
                old.httpStatus(), old.location(),
                old.responseJson(), true);
        }

        UUID orderId = UUID.randomUUID();
        jdbc.update("""
            INSERT INTO orders
              (id, tenant_id, customer_id, product_id, quantity, status)
            VALUES (?, ?, ?, ?, ?, 'CREATED')
            """,
            orderId, actor.tenantId(), actor.subjectId(),
            body.productId(), body.quantity());

        String location = "/v1/orders/" + orderId;
        String responseJson = serialize(new CreatedOrder(
            orderId, body.productId(), body.quantity(), "CREATED"));

        jdbc.update("""
            UPDATE api_idempotency SET state = 'COMPLETED',
              order_id = ?, http_status = 201,
              location = ?, response_json = ?
            WHERE id = ?
            """,
            orderId, location, responseJson, claimed.get(0));

        return new CreationOutcome(201, location, responseJson, false);
    }

    private String fingerprint(CreateOrderRequest input) {
        // Ví dụ canonical: validate trước, không bỏ field nghiệp vụ.
        String canonical = "POST|/v1/orders|"
            + input.productId() + "|" + input.quantity();
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                .digest(canonical.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private String serialize(CreatedOrder order) {
        try {
            return json.writeValueAsString(order);
        } catch (JsonProcessingException invalid) {
            // RuntimeException khiến transaction rollback cả order và K.
            throw new IllegalStateException("Cannot encode response", invalid);
        }
    }
}
~~~

Các exceptions chưa định nghĩa là **domain/test placeholders** và cần `@RestControllerAdvice` ánh xạ theo HTTP contract. Đây là lộ trình **single-database transaction**: `@Transactional` phải chạy qua Spring proxy và dùng **primary `JdbcTemplate` cùng transaction manager**; nếu mở connection riêng để ghi ledger, bảo đảm atomicity mất. Không bọc lời gọi provider bên ngoài trong transaction này.

**Chú ý race:** khi hai transactions cùng insert unique key, PostgreSQL có thể chờ winner. Sau khi winner commit, loser mới đi vào nhánh “không claim” và đọc stored outcome dưới `READ COMMITTED`. Một transaction `REPEATABLE READ` đã mở snapshot sớm có thể không thấy row vừa commit: cần handling serialization/retry nhất quán. Test với **PostgreSQL thực**, không suy ra tính đúng từ H2 hoặc một repository mock.

### 5.3. HTTP controller và error mapping

~~~java
@RestController
@RequestMapping("/v1/orders")
class OrderCreationController {
    private final OrderCreationService orders;
    private final ActorFactory actors;

    @PostMapping
    ResponseEntity<String> create(
            @AuthenticationPrincipal Jwt jwt,
            @RequestHeader("Idempotency-Key") String rawKey,
            @RequestBody CreateOrderRequest body) {
        Actor actor = actors.fromVerifiedJwt(jwt);
        String key = KeyParser.parseAndValidate(rawKey);
        CreationOutcome result = orders.create(actor, key, body);
        return ResponseEntity.status(result.httpStatus())
            .location(URI.create(result.location()))
            .contentType(MediaType.APPLICATION_JSON)
            .cacheControl(CacheControl.noStore())
            .header("Idempotency-Replayed",
                    Boolean.toString(result.replay()))
            .body(result.responseJson());
    }
}
~~~

Spring `ResponseEntity<String>` với `application/json` trong ví dụ ghi **JSON string đã serialize sẵn** vào response, không phải serialize String thành JSON string lần nữa; phải kiểm chính xác runtime/message converter trong integration test. `KeyParser` là adapter **giả định**, cần giới hạn length/charset, xử lý Structured Field String nếu là cú pháp công bố và từ chối header lỗi. `ActorFactory` chỉ dùng token đã verify, với `orders.write`/tenant permission được kiểm riêng.

~~~java
@RestControllerAdvice
class OrderApiErrors {
    @ExceptionHandler(PayloadMismatchException.class)
    ResponseEntity<ProblemDetail> mismatch() {
        ProblemDetail problem = ProblemDetail.forStatus(422);
        problem.setTitle("Idempotency key reused with another request");
        problem.setProperty("code", "IDEMPOTENCY_PAYLOAD_MISMATCH");
        return ResponseEntity.unprocessableEntity()
            .contentType(MediaType.parseMediaType("application/problem+json"))
            .body(problem);
    }
}
~~~

Tùy policy, `RequestStillProcessingException` trả `409` + `Retry-After` hoặc `202` với operation URI. Không để exception chứa SQL, token, tenant ID hoặc request body bị đưa thẳng vào `ProblemDetail.detail`. `401/403` do Spring Security filter phát sinh trước MVC cần entry point/access denied handler riêng nếu muốn Problem Details thống nhất.

**Ví dụ có giới hạn rõ:** chưa xử lý TTL cleanup, write failover, optimistic version, distributed trace, duplicate provider calls và request payload phức tạp; đây là những trường hợp cần thêm test và cơ chế tương ứng ở các mục sau. Mục tiêu của mã là **có chỗ kiểm đếm được order và ledger trong cùng transaction**, không phải mô phỏng “exactly once” mọi side effect.

## 6. HTTP integration test với PostgreSQL: replay và payload mismatch

Test cần dùng **database có cùng ngữ nghĩa unique/transaction như production**. PostgreSQL Testcontainers phù hợp để thử `ON CONFLICT`, lock, rollback và isolation; H2 hoặc mocks không thay được kiểm chứng race tại database.

### 6.1. Spring Boot + Testcontainers

~~~java
@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
class IdempotencyHttpIT {
    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired MockMvc mvc;
    @Autowired JdbcTemplate jdbc;

    static final UUID TENANT =
        UUID.fromString("13ec77f6-efc6-43c9-9522-d7a3e35b7d88");
    static final UUID ACTOR =
        UUID.fromString("3ab6c1bc-587c-4292-9928-0564f964dc2b");

    @BeforeEach
    void cleanup() {
        jdbc.update("DELETE FROM api_idempotency");
        jdbc.update("DELETE FROM orders");
    }

    MvcResult submit(String key, String body) throws Exception {
        return mvc.perform(post("/v1/orders")
            .with(jwt()
                .jwt(j -> j.subject(ACTOR.toString())
                    .claim("tenant_id", TENANT.toString()))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.write")))
            .header("Idempotency-Key", "\"" + key + "\"")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content(body))
            .andReturn();
    }

    long orderCount() {
        return jdbc.queryForObject("""
            SELECT count(*) FROM orders
            WHERE tenant_id = ? AND customer_id = ?
            """, Long.class, TENANT, ACTOR);
    }

    long completedLedgerCount() {
        return jdbc.queryForObject("""
            SELECT count(*) FROM api_idempotency
            WHERE tenant_id = ? AND actor_id = ?
              AND operation = 'orders.create'
              AND state = 'COMPLETED'
            """, Long.class, TENANT, ACTOR);
    }
}
~~~

Đây là **khung test có thể triển khai**: cần dependencies Spring Boot Test, Security Test, Testcontainers PostgreSQL/JUnit Jupiter và Flyway/Liquibase hoặc migration SQL Mục 3; import chuẩn của JUnit/Mockito/Spring được lược. `ActorFactory` thực của dự án phải map principal test thành đúng tenant/actor và resource server phải có filter bảo vệ `orders.write`. Test `jwt()` **mô phỏng một principal đã xác thực**, không chứng minh JWT signature/issuer/audience verification; test riêng ở security integration.

**Không đánh dấu `@Transactional` trên lớp test** khi kiểm atomicity qua HTTP/concurrency; test transaction bao bên ngoài có thể rollback dữ liệu hoặc khiến query quan sát những trạng thái khác production. Làm sạch fixture có chủ đích và chạy không song song trên cùng DB/schema khi dùng `DELETE` toàn bảng.

### 6.2. Retry sau khi server đã commit nhưng “client không nhận response”

~~~java
@Test
void replayAfterLostResponseCreatesOnlyOneOrder() throws Exception {
    String key = UUID.randomUUID().toString();
    String payload = """
        {"productId":"sku-7","quantity":2}
        """;

    MvcResult first = submit(key, payload);
    // Mô phỏng phía client KHÔNG dùng response lần đầu.
    // Server đã xử lý xong/commit khi request MockMvc hoàn tất.
    assertEquals(1L, orderCount());
    assertEquals(1L, completedLedgerCount());

    MvcResult retry = submit(key, payload);
    assertEquals(201, first.getResponse().getStatus());
    assertEquals(201, retry.getResponse().getStatus());
    assertEquals(first.getResponse().getHeader("Location"),
                 retry.getResponse().getHeader("Location"));
    assertEquals(first.getResponse().getContentAsString(),
                 retry.getResponse().getContentAsString());
    assertEquals("true",
                 retry.getResponse().getHeader("Idempotency-Replayed"));

    assertEquals(1L, orderCount());          // Bất biến nghiệp vụ
    assertEquals(1L, completedLedgerCount()); // Outcome bền vững
}
~~~

Test trên **chứng minh replay sau một request đã hoàn tất và commit**, tương đương client bỏ qua response. Nó **chưa tạo TCP timeout hoặc mất response thật** vì `MockMvc` không mở socket. Đặt tên/ghi chú chính xác, sau đó bổ sung e2e fault test ở Mục 8 để kiểm “commit xong nhưng response bị drop”.

### 6.3. Cùng key nhưng request khác phải từ chối

~~~java
@Test
void sameKeyDifferentPayloadIsRejectedWithoutSideEffect()
        throws Exception {
    String key = UUID.randomUUID().toString();
    submit(key, """
        {"productId":"sku-7","quantity":2}
        """);

    MvcResult mismatch = submit(key, """
        {"productId":"sku-7","quantity":99}
        """);

    assertEquals(422, mismatch.getResponse().getStatus());
    assertTrue(mismatch.getResponse().getContentAsString()
        .contains("IDEMPOTENCY_PAYLOAD_MISMATCH"));
    assertEquals(1L, orderCount());
    assertEquals(1L, completedLedgerCount());

    // Retry bản đầu sau mismatch vẫn lấy lại outcome ban đầu.
    MvcResult original = submit(key, """
        {"productId":"sku-7","quantity":2}
        """);
    assertEquals(201, original.getResponse().getStatus());
    assertEquals(1L, orderCount());
}
~~~

Không chỉ assert `422`: sau mismatch phải giữ outcome cũ và không thay quantity/order. Thêm biến thể test **thứ tự JSON property/whitespace** theo canonicalization policy; nếu server canonicalize payload, cùng dữ liệu nghiệp vụ nên tạo fingerprint giống nhau. Với nullable field/default, test cả omission vs explicit null theo ý nghĩa mà API đã công bố.

### 6.4. Cross-tenant và cross-actor không được replay nhầm

Lặp lại key của tenant A bằng principal tenant B không được đọc `Location`/body của A, dù key có thể đoán được. Nếu hai tenant tạo order hợp lệ với cùng key, mỗi scope có outcome riêng. Cũng kiểm user A1 và A2 trong cùng tenant nếu policy scope tới actor; nếu service quyết định scope theo tenant để cùng một job/organization intent, test phải phản ánh quyết định đó và phân quyền replay phù hợp.

**Không chỉ đổi `tenant_id` trong request body** để mô phỏng tenant khác: phải gửi principal khác đã xác thực. Test data isolation phải đọc trực tiếp DB hoặc qua adapter scoped, không suy từ khác `Location` khi ID ngẫu nhiên.

### 6.5. Test phản hồi khi thiếu hoặc sai Idempotency-Key

Nếu endpoint bắt buộc key, kiểm request không header, key rỗng, dài vượt ngưỡng, cú pháp không hợp lệ và nhiều header trùng lặp. Tất cả phải bị từ chối **trước side effect**, không rơi về một key mặc định `null` khiến mọi user chia chung quota. Với key quá dài, cần giới hạn input để tránh tấn công tăng cardinality/memory/DB row; lỗi nên là Problem Details an toàn, không echo key thô.

## 7. Kiểm thử tranh chấp đồng thời, rollback và restart

### 7.1. N request cùng key, một side effect

~~~java
@Test
void concurrentSameKeyRequestsCommitAtMostOneOrder()
        throws Exception {
    String key = UUID.randomUUID().toString();
    String payload = """
        {"productId":"sku-7","quantity":2}
        """;
    int workers = 12;
    ExecutorService pool = Executors.newFixedThreadPool(workers);
    CountDownLatch start = new CountDownLatch(1);

    try {
        List<Future<MvcResult>> results = new ArrayList<>();
        for (int i = 0; i < workers; i++) {
            results.add(pool.submit(() -> {
                if (!start.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Barrier timeout");
                }
                return submit(key, payload);
            }));
        }
        start.countDown();

        for (Future<MvcResult> future : results) {
            int status = future.get(20, TimeUnit.SECONDS)
                .getResponse().getStatus();
            // Synchronous-transaction strategy may replay 201;
            // explicit in-progress policy may respond 409.
            assertTrue(status == 201 || status == 409);
        }
    } finally {
        pool.shutdownNow();
    }

    assertEquals(1L, orderCount());
    assertEquals(1L, completedLedgerCount());
    assertEquals(201, submit(key, payload).getResponse().getStatus());
}
~~~

Phương thức này đặt **barrier lúc bắt đầu request**, tạo contention và kiểm bất biến. Nhưng CPU scheduling có thể khiến request đầu hoàn tất trước khi request khác tới unique index; vì vậy để **chứng minh chính xác case “concurrent while IN_PROGRESS”**, nên có test hook tại **sau khi claim key, trước commit**:

~~~text
Winner T1: claim K -> signal claimedLatch -> CHỜ releaseLatch
Loser  T2: gửi cùng K trong lúc T1 đang giữ unique lock
Assert    : không có hai order được commit, T2 không phá lock
Release   : cho T1 insert order, hoàn thành ledger và commit
T2        : chờ rồi replay hoặc trả 409 theo policy
Assert    : đúng một order/outbox event, không deadlock/500
~~~

Hook chỉ dành cho **test profile**, có deadline và bị vô hiệu ở production. Với PostgreSQL cần quan sát lock/transaction bằng instrumentation phù hợp, không ép test bằng `Thread.sleep` rồi mặc định race đã xảy ra.

### 7.2. Crash trước commit và rollback phải trả key về trạng thái dùng được

Nếu transaction đầu insert ledger, insert order rồi ném exception **trước commit**, cả hai insert phải rollback. Test có thể kích hoạt fault hook sau insert order:

~~~text
Given: chưa có key K và order
When : POST(K) -> server cố ý throw RuntimeException trước commit
Then : count(orders)=0, count(api_idempotency for K)=0
When : retry POST(K) không fault
Then : 201 + count(orders)=1, ledger COMPLETED=1
~~~

Nếu app tạo order trong transaction riêng, row order vẫn tồn tại sau rollback ledger: test này bắt được lỗi. Khi dùng outbox, row outbox cũng phải rollback nếu đi theo transaction order. Nếu email/push đã gửi ra ngoài trước commit, không thể rollback side effect ấy; cần chuyển phát qua outbox hoặc thiết kế chống trùng phía downstream.

### 7.3. Restart hoặc failover không được làm mất dedupe

Với Spring Boot chạy nhiều instances, phát POST(K) cho instance A, quan sát commit, **terminate/restart A**, retry qua instance B rồi assert vẫn một order. Đây là test quan trọng hơn mock cache: một `Map` trong JVM sẽ mất trạng thái khi restart. Cần xác minh database unique/ledger còn nguyên và không bị cleanup job xóa sớm.

Đối với DB failover, test thêm trường hợp primary đã ACK commit nhưng failover target **chưa nhận WAL**, vì kết quả còn phụ thuộc **durability/RPO/replication mode**. Không cam kết đúng một side effect xuyên mất commit nếu kiến trúc không cung cấp atomic durability tương ứng; cần thiết kế đối soát bằng business reference và kiểm thử theo RPO thực.

## 8. Timeout qua TCP thật: phải làm mất response sau commit

`MockMvc` có thể chứng minh retry/replay, nhưng không tạo socket timeout. Để tái hiện đúng sự cố:

1. Khởi chạy API trên cổng thật bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và database integration; đặt HTTP client qua proxy kiểm soát (ví dụ Toxiproxy hoặc một fault proxy của test harness).
2. Đưa **barrier sau transaction commit, trước khi response flush** vào test-only adapter/filter. Đợi `committedSignal` từ server thay vì giả định commit sau N mili giây.
3. Cho client gửi POST(K), quan sát server đã commit, sau đó proxy **drop/cut đường response** hoặc giữ response vượt client read deadline.
4. Client nhận `HttpTimeoutException`/connection reset; **không suy server rollback**. Kiểm DB bằng query độc lập: đúng một order, ledger K completed.
5. Client gửi lại cùng key/payload qua đường HTTP bình thường. Assert Location/body replay, không tạo order/charge/outbox thêm.

~~~text
POST K ─────▶ HTTP proxy ─────▶ Spring API ─────▶ Primary COMMIT
Client đợi...            server đã ghi order + ledger
       ╳  proxy DROP RESPONSE sau commit
Client timeout
POST K ─────▶ proxy (bình thường) ─────▶ ledger replay 201
COUNT(order)=1; COUNT(completed ledger K)=1
~~~

**Điểm đo “sau commit” phải thật:** callback trong method `@Transactional` **trước khi proxy commit** không chứng minh commit đã xong. Có thể dùng test hook tại layer **ngoài transaction proxy** sau khi service trả thành công, hoặc `TransactionSynchronization.afterCommit()` rồi phối hợp không ghi response trước khi fault được kích hoạt. Dùng signal/barrier thay vì `sleep(200)`.

Network fault test có thể tốn tài nguyên/flaky; giữ ít ca nhưng đáng tin, timeout có giới hạn và thu dọn proxy/session. Dùng real HTTP client vì `MockMvc.perform(...)` không mô phỏng lỗi TCP. Một response bị drop **trước commit** kiểm nhánh khác, không thay thế case F4.

### 8.1. Java HttpClient: retry cùng key, không tạo key mới

~~~java
String key = UUID.randomUUID().toString(); // Tạo một lần mỗi ý định
String body = """
    {"productId":"sku-7","quantity":2}
    """;
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

for (int attempt = 1; attempt <= 3; attempt++) {
    HttpRequest request = HttpRequest.newBuilder(
            URI.create("https://api.example.com/v1/orders"))
        .timeout(Duration.ofSeconds(5))
        .header("Authorization", "Bearer " + credentialProvider.token())
        .header("Idempotency-Key", "\"" + key + "\"")
        .header("Content-Type", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(body))
        .build();

    try {
        HttpResponse<String> response = client.send(
            request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() == 201) {
            // Parse/validate Location, body và finish.
            break;
        }
        if (response.statusCode() == 422) {
            throw new IllegalStateException("Key/payload mismatch");
        }
        // 409 in-progress/429/503 chỉ retry nếu contract và
        // Retry-After + budget còn cho phép; branch implementation omitted.
        break;
    } catch (HttpTimeoutException timeout) {
        if (attempt == 3) throw timeout;
        // Lên lịch retry có jitter/deadline; giữ nguyên key và payload.
    }
}
~~~

Đây là **khung nguyên tắc**: `credentialProvider` cần triển khai thực, client phải xử lý `InterruptedException` (restore interrupt khi thích hợp), network exceptions khác, HTTP 409/429/503 và scheduling delay có giới hạn. Trong Spring WebFlux dùng `WebClient` với policy retry có điều kiện, không `block()` trên event-loop hoặc retry mọi `onError` vô điều kiện. Token có thể refresh giữa lần gọi, nhưng **idempotency key của cùng ý định vẫn giữ nguyên**; server scope định danh actor ổn định thay vì chuỗi token.

**Không retry `401/403` như lỗi timeout**: đó là vấn đề credential/quyền. `409` chỉ retry nếu API cho biết request K đang xử lý; conflict trạng thái nghiệp vụ khác không được retry mù. Với `429/503`, `Retry-After` là gợi ý; client vẫn phải tôn trọng deadline, retry budget, jitter và hủy request khi người dùng không còn cần.

## 9. Side effect bên ngoài: không thể rollback một lần đã charge

Ví dụ checkout có bước ghi DB và gọi payment provider. Nếu thanh toán bị charge rồi response của provider timeout, server **không biết chắc payment thành công hay thất bại**. Một transaction PostgreSQL không thể rollback giao dịch mà provider đã xử lý.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Checkout API
    participant D as Database
    participant W as Outbox worker
    participant P as Payment provider
    C->>A: POST checkout + key K
    A->>D: TX: order + ledger + outbox event
    D-->>A: COMMIT
    A-->>C: 202 Accepted + operation URI
    W->>D: Lấy outbox event, có thể nhận lại
    W->>P: Charge + provider idempotency key P-K
    P-->>W: Response timeout dù charge đã xảy ra
    W->>P: Reconcile hoặc retry cùng P-K
    P-->>W: Trả lại outcome cũ
    W->>D: Mark payment/order done
~~~

Ở đây **API key K** bảo vệ việc nhận một yêu cầu checkout, còn **provider key P-K** bảo vệ side effect ở provider. Thường derivation là stable ID của logical payment attempt hoặc một key được lưu cùng operation; **không tạo P-K mới mỗi lần outbox worker retry**. Key không được log giá trị thô nếu nó là credential/bí mật.

### 9.1. Test outbox delivery lặp

1. Gửi một checkout K, assert **một order, một logical payment instruction, một outbox event** commit.
2. Worker nhận event lần đầu, provider mock ghi nhận charge nhưng cố ý trả timeout.
3. Cho worker nhận **chính event ấy** lần thứ hai, kiểm nó gửi **cùng provider key** hoặc reconcile payment theo business reference.
4. Provider mock có idempotency ledger trả outcome cũ, assert **một charge thật** và operation chuyển trạng thái đúng.
5. Nếu callback/webhook từ provider được gửi lặp, verify handler có inbox/dedup event ID hoặc state transition idempotent; không phát hai lần `ORDER_PAID`.

**Không chỉ dùng `verify(providerClient, times(1)).charge(...)`** nếu thiết kế cho phép nhiều HTTP retries nhưng provider dedupe chúng. Điều cần chứng minh là **số charge nghiệp vụ**, không phải tuyệt đối một lần gọi HTTP. Ngược lại, nếu nhà cung cấp **không hỗ trợ idempotency/reconciliation**, không được hứa at-most-once charge chỉ nhờ ledger API; phải có business-specific safeguard hoặc chấp nhận và vận hành xử lý trường hợp không thể phân giải.

### 9.2. Trạng thái IN_PROGRESS bền vững cần recovery

Khi operation worker có `IN_PROGRESS` đã commit, một worker có thể chết trước khi chuyển COMPLETED. Test cần kiểm:

- **Lease expiry:** một worker mới được claim sau lease timeout; tránh hai worker cùng sở hữu operation lâu dài.
- **Fencing/version:** worker cũ tỉnh lại sau pause không được ghi đè outcome của worker mới bằng state cũ.
- **Outbox at-least-once:** cùng event được deliver nhiều lần vẫn không nhân đôi charge/order/email.
- **Ambiguous downstream outcome:** timeout không tự chuyển thành FAILED rồi charge lại với key khác; phải query/reconcile.
- **Client replay:** GET operation hoặc POST(K) trong lúc xử lý trả `202`/`409` theo hợp đồng, không tạo operation thứ hai.

Các test recovery có thể dùng fake clock điều khiển lease, test DB locks và controlled fake provider. Đừng tự coi **exactly once event delivery** là điều kiện bắt buộc; thường cần thiết kế **at-least-once delivery + idempotent consumer**.

## 10. TTL, cache, key reuse và điều kiện biên

### 10.1. Khóa hết hạn không đồng nghĩa business action biến mất

Ledger `expires_at` chỉ định **retention của kết quả dedupe**, không phải thời gian sống của đơn. Sau khi cleanup xóa K, request với K cũ có thể tạo order mới nếu API không có business unique constraint riêng. Hãy công bố retention và thiết kế **client retry horizon nhỏ hơn thời gian giữ key**, đồng thời tính đến offline retries, queue delay và vận hành.

Test với **Clock được inject hoặc điều khiển job cleanup**, không dùng `Thread.sleep(24h)`:

~~~text
T0       : POST K -> order o1, ledger K COMPLETED
T0 + 1h  : retry K -> replay o1; count=1
T0 + TTL : cleanup chỉ xóa bản COMPLETED đã hết hạn
T0 + TTL+: retry K -> behavior theo contract (có thể tạo o2)
Assert   : không còn lời hứa "cùng K mãi mãi = cùng order"
~~~

Không xóa **IN_PROGRESS còn đang thực sự xử lý** chỉ vì wall-clock TTL; nếu worker treo, cần lease/recovery rõ ràng. Dùng timestamp trong DB/clock thống nhất để tránh các instance lệch giờ khiến key hết hạn sớm. Cleanup chạy đồng thời request phải có lock/transaction logic để không tạo khoảng trống dedupe ngay khi một attempt vẫn có tác dụng.

### 10.2. Reverse proxy/cache có thể làm test đánh lạc hướng

HTTP POST thường không được replay từ cache thông thường theo cách mặc định, nhưng gateway, app-layer caching hoặc SDK retry middleware có thể ảnh hưởng đường đi. Nếu thấy cùng body khi retry, chưa chứng minh ledger đúng: response có thể đến từ fake client, in-memory cache hoặc reverse proxy. Trong test:

- Ghi nhận **đã có HTTP request thứ hai tới server** (mà không log token/payload).
- Tắt hoặc kiểm soát cache trên test path; test server restart để loại cache RAM.
- Kiểm database/outbox/provider effect bằng **nguồn dữ liệu độc lập**, không chỉ body.
- Với nhiều app instances, retry đi qua instance khác để kiểm storage share.

### 10.3. Business uniqueness là lớp khác với request dedupe

Nếu nghiệp vụ không cho một giỏ hàng checkout hai lần, thêm constraint `UNIQUE(tenant_id, cart_id, logical_checkout_id)` hoặc state transition có điều kiện, **kể cả khi client gửi key mới do bug**. Nhưng đừng áp unique theo `productId+quantity` làm cấm người dùng cố ý mua hai đơn giống nhau. Test rõ “cùng ý định” khác với “hai ý định hợp lệ nhưng body giống nhau”.

## 11. Bảo mật, quan sát và tiêu chí qua cổng chất lượng

**Idempotency-Key không phải bearer token và không cấp quyền xem order.** Dù biết key K của tenant khác, attacker không được replay hoặc nhận `Location`/body của họ. Server phải xác thực actor và kiểm tenant/operation scope trước khi tra ledger hay trả outcome. Chỉ lưu **digest/fingerprint** của request có field nhạy cảm; cân nhắc HMAC hoặc cơ chế tokenization nếu hash của dữ liệu ít entropy có thể bị brute-force offline.

| Tín hiệu cần đo | Điều chứng minh / cảnh báo | Tránh làm |
|---|---|---|
| `idempotency_claimed_total` | Bao nhiêu ý định mới được nhận | Không dùng raw key/actor làm label |
| `idempotency_replayed_total` | Retry thành công từ ledger | Không log response chứa PII |
| `idempotency_mismatch_total` | Key reuse sai payload | Không log raw body để “debug” |
| `idempotency_in_progress_total` | Client va vào request đang xử lý | Không suy mọi 409 là abuse |
| `idempotency_lock_wait_duration` | Contention/DB lock kéo dài | Giới hạn đuôi p99, deadline |
| `order_duplicate_business_violation_total` | Bất biến bị phá, cần cảnh báo | Không dùng status 201 làm thay row count |
| `outbox_retries_total`/`provider_reconcile_total` | Tác dụng ngoài cần retry/đối soát | Không coi retry HTTP là duplicate charge |

Khi phát hiện mismatch hoặc lỗi unknown, response công khai có `type/title/code/status` trung tính theo RFC 9457; không đính kèm JWT, email, địa chỉ giao hàng, SQL, storage key hoặc payload hash. Dùng correlation ID do server tạo, log với retention/access control phù hợp. Rate limiting có thể tính cả retries, nhưng cần policy không khóa oan client đang phục hồi sau lỗi; không tự miễn quota mọi request có Idempotency-Key (attacker có thể spam key mới).

**Tiêu chí pass cho test chống trùng:**

1. Bất biến **business row/outbox/provider side effect** được kiểm đếm.
2. Có ca **commit rồi mất response** thật hoặc giả lập có tín hiệu commit rõ, không chỉ timeout trước request.
3. Có concurrency/rollback/restart/cross-tenant/mismatch test và tất cả đều bounded timeout.
4. Client **giữ nguyên key và payload cho cùng intent**, không che HTTP 401/403/422 thành retry vô hạn.
5. Hệ thống định nghĩa rõ TTL, in-progress, ambiguous downstream và recovery; test phù hợp.

## 12. Bài tập: checkout bị timeout và cách chấm

**Bối cảnh:** `POST /v1/checkouts` nhận `cartId` và idempotency key K. API commit order và outbox event, trả `202 Location: /v1/operations/p-19`. Payment provider có hỗ trợ idempotency key. Client timeout đúng lúc server đã commit, rồi retry hai lần: lần 1 cùng K, lần 2 do bug tạo K2.

**Yêu cầu thực hành:** thiết kế test tự động và nêu invariants đối với đơn, operation, event và charge; chỉ rõ 202/409/422/429/503 cần xử lý thế nào; mô tả cách xác minh fault sau commit không bị nhầm với lỗi trước commit.

**Gợi ý lời giải:**

- Với **hai POST dùng K**, chỉ một order/operation/outbox event được tạo; retry trả outcome đã lưu hoặc trạng thái đang xử lý theo hợp đồng, không lấy timeout làm bằng chứng rollback.
- Với **K2 cho cùng cart**, request-level idempotency không bảo vệ được; thêm business constraint/state transition một checkout trên một logical cart intent, hoặc quyết định rõ liệu một cart được phép checkout nhiều lần. Test K2 không tạo thêm charge khi nghiệp vụ cấm.
- Worker có thể gọi provider lại sau timeout nhưng **giữ cùng provider payment key**, assert provider tạo tối đa một charge; xử lý webhook lặp và reconciliation.
- `422` là key/payload mismatch, không tự retry; `409` chỉ có thể retry nếu subtype **in progress** theo hợp đồng; `429/503` theo `Retry-After` và deadline; `202` là job chưa hoàn tất, theo dõi operation URI. `401/403` không được retry mù.
- E2E test có barrier **sau DB commit, trước response flush**, proxy drop response và client timeout; kiểm row DB trước khi retry; unit test service đơn thuần không đủ chứng minh fault timing này.

**Checklist trước khi merge:**

- [ ] Khóa được scope theo **trusted tenant/actor/operation**, fingerprint gắn toàn bộ field ảnh hưởng nghiệp vụ.
- [ ] Schema có **unique constraint** và ledger + order commit atomically; response replay giữ nguyên semantics.
- [ ] Test replay `201`, mismatch `422`, in-progress `409/202` theo hợp đồng, thiếu/sai key trước ghi.
- [ ] Test **lost response after commit**, rollback before commit, concurrency, restart, TTL và actor/tenant khác.
- [ ] Đếm **orders, outbox records, provider charges**, không chỉ HTTP/ledger.
- [ ] Client giữ cùng key khi retry cùng intent, có timeout/deadline/jitter/budget; không retry vô hạn.
- [ ] External provider có idempotency/reconciliation; worker hỗ trợ at-least-once delivery, lease/fencing.
- [ ] Security, Problem Details và log không phản chiếu token/key/PII hoặc lộ outcome tenant khác.
- [ ] Test trên PostgreSQL/engine production tương đương; có ít nhất một test fault qua HTTP socket thật.

**Tham khảo:** [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110), [RFC 9457 — Problem Details](https://www.rfc-editor.org/rfc/rfc9457), [Spring Testing MVC](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html), [Spring Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html), [PostgreSQL — Unique Indexes](https://www.postgresql.org/docs/current/indexes-unique.html), [Testcontainers Java](https://java.testcontainers.org/).

**Kết luận:** Một test chống trùng tốt không dừng ở việc gọi lại POST với cùng header. Nó phải **đặt lỗi tại đúng thời điểm**, đặc biệt **commit xong nhưng response bị mất**, rồi chứng minh **không có side effect nghiệp vụ thứ hai** trong database và cả downstream. Unique constraint, transaction, ledger outcome, retry cùng ý định, fault injection có barrier và kiểm thử multi-tenant/concurrency tạo thành bằng chứng đáng tin cậy cho REST API Java/Spring.

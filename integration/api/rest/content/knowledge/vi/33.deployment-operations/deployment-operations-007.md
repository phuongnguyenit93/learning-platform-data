# Trạng thái cần lưu bền khi mở rộng nhiều tiến trình phục vụ

Một REST API chạy ổn trên một tiến trình Java có thể gặp lỗi khi tăng từ một lên nhiều replica. Request đầu tiên đi vào replica A, tạo đơn rồi trả phản hồi. Request kế tiếp đến replica B và không tìm thấy dữ liệu từng lưu trong `ConcurrentHashMap` của A. Nếu A bị restart ngay sau khi chấp nhận một job trong bộ nhớ, công việc đó có thể biến mất. Nếu client gửi lại `POST` sau khi mất kết nối, hai replica có thể cùng tạo hai đơn hàng.

Đây không đơn thuần là vấn đề “load balancer chọn sai server”. Câu hỏi quan trọng hơn là **trạng thái nào cần tồn tại qua restart, cần được chia sẻ giữa replica, và phải có tính nhất quán đủ mạnh để bảo vệ bất biến nghiệp vụ**.

Trong mô-đun **INTEGRATION_API_REST**, các hợp đồng resource, URI, phương thức, mã trạng thái HTTP, idempotency, cache, xác thực và phân quyền giúp client giao tiếp đúng với API. Bài thuộc chương **Triển khai và vận hành** và nối các hợp đồng đó với thực tế triển khai nhiều tiến trình bằng Java/Spring Boot, database, Redis, hàng chờ bền vững và cơ chế rollout.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **trạng thái cục bộ**, **trạng thái dùng chung nhưng tái tạo được**, **trạng thái bắt buộc lưu bền** và **trạng thái điều phối có thời hạn**.
2. Giải thích vì sao REST “stateless” ở tầng HTTP vẫn cần database, outbox, idempotency store hoặc shared session store.
3. Thiết kế thao tác tạo đơn, retry sau timeout, session và job bất đồng bộ chạy đúng khi request tới các replica khác nhau.
4. Sử dụng transaction, unique constraint, atomic update và outbox để bảo vệ dữ liệu khi nhiều tiến trình cùng ghi.
5. Chọn nơi lưu phù hợp: relational database, Redis, object storage, broker; nêu rõ độ bền, TTL, tính nhất quán và cách phục hồi.
6. Xây test nhiều replica, kill/restart trong lúc xử lý; chuẩn bị rollout, backup/restore, quan sát và bảo mật dữ liệu dùng chung.

**Nguyên tắc:** nếu một tiến trình bị hủy ngay sau một điểm thành công mà hệ thống đã công bố, mọi trạng thái cần thiết để giữ lời hứa đó phải còn tồn tại và truy cập được từ tiến trình thay thế.

## 2. Hai replica, một API, một hợp đồng

Giả sử có hai instance Spring Boot đứng sau gateway:

~~~mermaid
flowchart TB
    C["Java client / Browser"] --> G["Gateway / Load balancer"]
    G --> A["Orders API · Replica A"]
    G --> B["Orders API · Replica B"]
    A --> DB[("Shared relational database")]
    B --> DB
    A --> R[("Shared Redis nếu cần")]
    B --> R
    DB --> O[("Outbox / durable jobs")]
    O --> W["Worker replicas"]
    W --> X["Payment / Email provider"]
~~~

Chuỗi sự kiện dễ gây lỗi:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant A as Replica A
    participant B as Replica B
    participant D as Shared DB
    C->>G: POST /orders + Idempotency-Key: req-42
    G->>A: Request lần đầu
    A->>D: BEGIN; ghi order + key; COMMIT
    D-->>A: COMMIT thành công
    A--xC: Response 201 thất lạc / client timeout
    Note over A: Replica A có thể bị restart
    C->>G: Retry cùng key và payload
    G->>B: Chọn replica B
    B->>D: Đọc key/order đã commit
    D-->>B: Kết quả request đầu
    B-->>C: Trả kết quả tương ứng, không tạo đơn thứ hai
~~~

Nếu A chỉ ghi idempotency key vào một `HashMap` cục bộ, B không thể biết giao dịch đã hoàn tất. Nếu business operation và idempotency record được ghi **cùng transaction** vào database chia sẻ, B nhận biết kết quả sau commit ngay cả khi A biến mất.

Database chia sẻ giúp hai replica **thấy trạng thái đã commit**, nhưng không tự ngăn race condition. Nếu cả hai đọc tồn kho rồi update mà không khóa hoặc điều kiện atomic, cùng một database vẫn có thể bán quá số lượng. **Lưu chung**, **lưu bền** và **nhất quán dưới cạnh tranh** là ba yêu cầu khác nhau.

## 3. Bốn câu hỏi để phân loại trạng thái

Với mỗi biến, record, file hoặc message, hãy hỏi:

1. **Có mất được không?** Nếu tiến trình chết, có được phép tái tạo từ nguồn khác mà không vi phạm hợp đồng?
2. **Ai cần thấy?** Chỉ request hiện tại, một replica, mọi replica, worker nền hay một hệ thống ngoài?
3. **Phải đúng đến mức nào?** Chấp nhận đọc dữ liệu cũ vài giây hay cần uniqueness/atomicity ngay lập tức?
4. **Sống bao lâu?** Vài millisecond, suốt phiên, đến khi job hoàn tất hay theo hạn lưu trữ?

| Trạng thái | Thường có thể mất? | Cần chia sẻ? | Nơi lưu phù hợp | Điều phải thiết kế |
| --- | --- | --- | --- | --- |
| Biến tạm của một request | Có nếu request được retry an toàn | Không | Stack/heap request | Không giữ sau response |
| Jackson metadata, connection pool | Tái tạo được | Không | Memory mỗi replica | Giới hạn tài nguyên, warm-up |
| Cache sản phẩm công khai | Có nếu nguồn chính còn | Có thể | Cache local hoặc Redis | TTL, invalidation, stale data |
| Đơn hàng, số dư, tồn kho, quyền sở hữu | **Không** | **Có** | Transactional database | Constraint, transaction, backup |
| Idempotency record thao tác ghi | Không trong cửa sổ retry cam kết | Có | Database/durable atomic store | Unique key, fingerprint, result, TTL |
| Session xác thực dạng stateful | Tùy yêu cầu chính sách phiên | Có nếu request đi nhiều replica | Shared session store | TTL, revoke, HA, cookie |
| JWT access token tự chứa | Không lưu mỗi access token để verify | Mọi replica cần trust configuration | Token client; key/JWKS quản lý | Issuer, audience, expiry, rotation |
| Refresh token/revocation state | Thường cần lưu suốt thời hạn hiệu lực | Có | Database/store đủ bền | Rotation atomic, replay detection |
| Job đã nhận và hứa xử lý | **Không** | Worker nào cũng có thể nhận | DB job table / durable broker | Claim/lease, retry, idempotency |
| Event phải publish sau commit | **Không** | Có | Outbox trong DB transaction | Publish retry, consumer dedup |
| Kết nối WebSocket/TCP hiện tại | Không thể giữ socket qua restart | Không dưới dạng socket sống | Memory replica sở hữu kết nối | Reconnect, resubscribe, shared pub/sub |
| Tiến độ phải đọc sau restart | Không được mất nếu đã hứa bền | Có | Database/object storage | Version, status, quyền truy cập |
| Counter rate limit tạm thời | Tùy rủi ro/chính sách | Thường | Redis atomic + TTL/gateway quota | Mức chính xác, clock, TTL |
| Lock/lease điều phối | Có thể hết hạn và cấp lại | Có | DB/Redis/coordinator | Fencing, renew, failover |
| Metrics gauge, log buffer | Thường tái tạo hoặc xuất ngoài | Không | Per-replica collector | Không làm source of truth nghiệp vụ |

Không có đáp án “mọi thứ đưa vào Redis” hoặc “mọi thứ phải nằm trong SQL”. Hệ thống cần **source of truth** rõ ràng cho từng loại trạng thái và mức cam kết tương ứng.

## 4. REST stateless không có nghĩa không dùng state

**Stateless request** trong REST nghĩa là request chứa đủ ngữ cảnh để server hiểu và xử lý, thay vì dựa vào hội thoại không chuyển đi giữa request. Nó **không** cấm lưu resource trong database hoặc lưu state phục vụ bảo mật theo thiết kế.

~~~http
GET /api/v1/orders/8c9b4ca4-2211-4cd0-a949-d176bcb8e35f HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

Replica nào cũng xác minh token, kiểm tra quyền và đọc `order` từ database. Đơn hàng là **resource state lưu bền**, còn xác thực đi kèm mỗi request. Không cần object `CurrentConversation` riêng trên A để B biết người dùng đang làm gì.

Trong ứng dụng dùng session cookie, HTTP request mang session ID, còn thông tin phiên có thể nằm ở **server-side session store** dùng chung. Đây là lựa chọn kiến trúc hợp lệ, miễn là có session TTL, bảo mật cookie và khả năng truy cập từ nhiều replica. Không được suy luận rằng cứ gọi endpoint là “REST API” thì tắt CSRF an toàn nếu browser tự đính cookie xác thực.

### 4.1. Sticky session không phải tính bền vững

Load balancer có thể cố đưa client luôn đến replica A (session affinity). Điều đó chỉ **giảm tần suất** gặp request khác replica; không bảo vệ trước A crash/restart, rolling deployment, autoscaling scale-in, multi-zone failover hoặc client đổi network path. Sticky session có thể tối ưu locality nhưng **không biến biến Java, local disk hay session memory thành durable shared state**.

## 5. Những trạng thái nghiệp vụ bắt buộc lưu bền

### 5.1. Resource và constraint trong một database

Với `POST /api/v1/orders`, trạng thái lưu lâu dài thường gồm đơn hàng, item, tenant, customer, reservation tồn kho, record idempotency trong cửa sổ retry, outbox event khi cần và audit nghiệp vụ theo yêu cầu. Các record cần định danh ổn định, constraint và migration. `synchronized` trong một JVM không thay thế được unique constraint ở database.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE inventory (
    tenant_id VARCHAR(64) NOT NULL,
    sku_id UUID NOT NULL,
    available INTEGER NOT NULL CHECK (available >= 0),
    PRIMARY KEY (tenant_id, sku_id)
);

CREATE TABLE purchase_order (
    id UUID PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL,
    customer_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    sku_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE api_idempotency (
    tenant_id VARCHAR(64) NOT NULL,
    caller_id VARCHAR(128) NOT NULL,
    operation VARCHAR(128) NOT NULL,
    idem_key VARCHAR(200) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    state VARCHAR(32) NOT NULL,
    order_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, caller_id, operation, idem_key)
);
~~~

Đây là schema rút gọn; production cần khóa ngoại, index cho tra cứu/cleanup, constraint trạng thái và retention. `expires_at` **không tự xóa row** trong PostgreSQL; cần job cleanup an toàn. `request_hash` phải đại diện cho payload đã chuẩn hóa theo hợp đồng (đừng hash JSON raw mà quên key order/format); không lưu request body nhạy cảm chỉ để kiểm tra trùng nếu hash đáp ứng.

### 5.2. Nhiều replica cùng ghi phải dùng atomic update

Ví dụ tồn kho chỉ còn một sản phẩm; A và B đồng thời yêu cầu giữ một đơn vị. Đoạn code Java sau dễ gặp race:

~~~java
Inventory stock = repository.findBySkuId(skuId).orElseThrow();
if (stock.getAvailable() > 0) {
    stock.setAvailable(stock.getAvailable() - 1);
    repository.save(stock);
}
~~~

Cả hai transaction có thể đọc `available=1` trước khi một transaction ghi. Thay bằng atomic conditional update trong database:

~~~sql
UPDATE inventory
   SET available = available - :quantity
 WHERE tenant_id = :tenantId
   AND sku_id = :skuId
   AND available >= :quantity;
~~~

Phải kiểm tra **số row cập nhật**: một row nghĩa là giữ thành công; không row nào nghĩa là không tìm thấy, sai tenant hoặc không đủ hàng. Với số lượng dương, constraint và điều kiện atomic giúp không trừ âm ngay cả khi nhiều process tranh nhau. Chọn isolation/locking phù hợp database thật; các bất biến bao phủ nhiều row có thể cần `@Version`, row lock hoặc isolation cao hơn.

### 5.3. @Transactional không tạo transaction xuyên dịch vụ

Trong Spring Boot, `@Transactional` bao phủ thao tác tham gia cùng transaction manager/database. Nó không tự rollback email, HTTP charge hoặc message broker bên ngoài:

~~~java
@Transactional
public OrderReceipt placeOrder(CreateOrder command) {
    // Atomic update tồn kho trong database.
    // INSERT đơn hàng trong cùng transaction.
    // INSERT outbox event trong cùng transaction.
    // Return để Spring proxy commit trước khi controller trả HTTP.
}
~~~

Gọi method transactional qua Spring proxy, không dựa vào self-invocation; `save/flush` khác `commit`. Giữ transaction ngắn, không chờ provider chậm trong khi giữ connection/lock. Nếu nghiệp vụ đi qua nhiều dịch vụ, định nghĩa workflow bền vững với trạng thái trung gian và thao tác bù/idempotent.

## 6. Idempotency phải hoạt động giữa các replica

Một lỗi điển hình:

~~~java
// SAI: chỉ tồn tại trong một JVM và mất sau restart.
private final Set<String> seenKeys =
    ConcurrentHashMap.newKeySet();

boolean firstTime(String key) {
    return seenKeys.add(key);
}
~~~

Hai replica có hai set khác nhau. Ngay cả một JVM, `seenKeys.add` và ghi đơn hàng không atomic. Nếu thêm key xong process chết trước commit, retry bị chặn sai; nếu DB commit nhưng response mất, retry đến B tạo đơn thứ hai.

Một thiết kế đúng xác định:

1. **Namespace:** `tenantId + callerId + operation + Idempotency-Key`, không cho caller chiếm key của người khác.
2. **Fingerprint:** cùng key nhưng payload/action khác bị từ chối (thường `409 Conflict` theo contract).
3. **Atomic commit:** business resource và kết quả idempotency ghi cùng đơn vị commit, hoặc durable state machine có recovery.
4. **Concurrent duplicate:** chỉ một request thực thi nghiệp vụ, request khác chờ/đọc kết quả/từ chối có kiểm soát.
5. **Result replay:** trả kết quả tương ứng, không nhầm “thấy key” với “đã thành công”.
6. **TTL/retention:** giữ ít nhất bằng cửa sổ retry đã cam kết; xác định rõ hành vi khi key hết hạn.

### 6.1. Ví dụ transaction idempotent với PostgreSQL

Giả định `tenantId` và `callerId` đã được xác minh từ authentication, `quantity > 0` được validate, mọi thao tác ghi dùng **một PostgreSQL**. Helper `fingerprints.sha256Canonical(command)` tạo hash hex của payload canonical ổn định.

~~~java
@Service
public class CreateOrderService {
    private final JdbcTemplate jdbc;
    private final Fingerprints fingerprints;

    public CreateOrderService(JdbcTemplate jdbc, Fingerprints fingerprints) {
        this.jdbc = jdbc;
        this.fingerprints = fingerprints;
    }

    @Transactional
    public OrderResult create(
            String tenantId, String callerId, String key,
            CreateOrder command) {
        String operation = "POST:/api/v1/orders";
        String hash = fingerprints.sha256Canonical(command);

        int acquired = jdbc.update("""
            INSERT INTO api_idempotency
              (tenant_id, caller_id, operation, idem_key,
               request_hash, state, expires_at)
            VALUES (?, ?, ?, ?, ?, 'PROCESSING',
                    now() + interval '24 hours')
            ON CONFLICT
              (tenant_id, caller_id, operation, idem_key)
            DO NOTHING
            """,
            tenantId, callerId, operation, key, hash);

        if (acquired == 0) {
            ExistingResult old = jdbc.queryForObject("""
                SELECT request_hash, state, order_id
                  FROM api_idempotency
                 WHERE tenant_id = ? AND caller_id = ?
                   AND operation = ? AND idem_key = ?
                 FOR UPDATE
                """,
                (rs, row) -> new ExistingResult(
                    rs.getString("request_hash"),
                    rs.getString("state"),
                    (UUID) rs.getObject("order_id")),
                tenantId, callerId, operation, key);

            if (old == null || !old.requestHash().equals(hash)) {
                throw new IdempotencyConflictException();
            }
            if (!"SUCCEEDED".equals(old.state())) {
                throw new RequestStillProcessingException();
            }
            return new OrderResult(old.orderId(), true);
        }

        int reserved = jdbc.update("""
            UPDATE inventory
               SET available = available - ?
             WHERE tenant_id = ? AND sku_id = ?
               AND available >= ?
            """,
            command.quantity(), tenantId,
            command.skuId(), command.quantity());
        if (reserved != 1) {
            throw new InsufficientStockException();
        }

        UUID id = UUID.randomUUID();
        jdbc.update("""
            INSERT INTO purchase_order
              (id, tenant_id, customer_id, status, sku_id, quantity)
            VALUES (?, ?, ?, 'PENDING', ?, ?)
            """,
            id, tenantId, callerId,
            command.skuId(), command.quantity());
        jdbc.update("""
            UPDATE api_idempotency
               SET state = 'SUCCEEDED', order_id = ?
             WHERE tenant_id = ? AND caller_id = ?
               AND operation = ? AND idem_key = ?
            """,
            id, tenantId, callerId, operation, key);
        return new OrderResult(id, false);
    }
}

public record CreateOrder(UUID skuId, int quantity) {}
public record OrderResult(UUID orderId, boolean replayed) {}
public record ExistingResult(String requestHash,
                             String state, UUID orderId) {}
~~~

`Fingerprints` và các exception là thành phần giả định. Cần import `JdbcTemplate`, `@Transactional`, `UUID` cùng cấu hình Spring. Code minh họa **PostgreSQL-specific**, không áp dụng nguyên văn mọi database. Một transaction ghi `PROCESSING` rồi cập nhật `SUCCEEDED` **trước commit**, nên nếu process chết đang thực thi, toàn bộ reservation, order và idempotency row rollback. Request đồng thời cùng unique key có thể đợi transaction đầu commit/rollback ngay tại unique index; cần database/HTTP timeout và integration test concurrency.

Sau commit, retry đọc `SUCCEEDED` và dùng ID cũ. Nếu hợp đồng yêu cầu replay **chính xác HTTP status/header/body**, cần lưu hoặc dựng lại kết quả theo version tương ứng. Nếu request đầu commit rồi response serialize lỗi, client vẫn có thể retry an toàn.

**Giới hạn ví dụ:** chưa xử lý mọi lỗi/constraint, TTL cleanup, response snapshot, payment và outbox. Với workflow kéo dài qua **nhiều transaction**, một record `PROCESSING` đã commit có thể tồn tại lâu: cần lease/heartbeat/recovery và job state machine. Không thể chỉ trông vào transaction trong code trên.

### 6.2. Redis có thể dùng cho idempotency không?

Redis hỗ trợ thao tác atomic như `SET key value NX EX ...`, script và TTL, phù hợp cho lock ngắn hoặc cache kết quả có thời hạn. Nhưng nếu Redis cache evict hoặc mất dữ liệu **trong khi đơn đã commit ở SQL**, retry có thể tạo hiệu ứng trùng. Nếu API cam kết không trùng trong một cửa sổ, **độ bền và consistency của idempotency store phải đáp ứng cam kết ấy**.

Redis với AOF/RDB, replica và failover vẫn có cửa sổ mất dữ liệu phụ thuộc cấu hình, eviction và kiểu xác nhận. Redis cluster **không tạo transaction atomic tự động với PostgreSQL**. Nếu dùng Redis làm nơi ghi tạm, phải có business unique/dedup ở nguồn dữ liệu hoặc một quy trình recovery đã được kiểm thử.

## 7. Session, JWT và trạng thái xác thực

### 7.1. Session server-side cần chia sẻ khi request đến nhiều replica

Nếu session cookie `JSESSIONID` trỏ tới session nằm trong memory A, request tới B có thể bị coi là chưa đăng nhập. Các lựa chọn:

- **Spring Session** dùng Redis cho phép nhiều replica tra cứu cùng phiên, nhưng cần đánh giá TTL, HA/persistence, network và bảo vệ dữ liệu.
- JDBC-backed session nếu cần durability/consistency khác và chấp nhận chi phí truy vấn.
- JWT access token tự chứa khi phù hợp; replica nào cũng kiểm được chữ ký/issuer/audience/expiry, nhưng refresh/revocation vẫn có thể cần shared state.

Ví dụ khái niệm:

~~~yaml
# Các property/auto-configuration cụ thể tùy Spring Boot/Spring Session.
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
  session:
    timeout: 30m
~~~

Cần khai báo dependency Spring Session Data Redis tương ứng và **integration test hai process** với cùng store. Chỉ cấu hình kết nối Redis chưa bảo đảm Spring Session đã được bật. Bảo vệ connection/ACL/namespace, session TTL, rotation và cookie `Secure`, `HttpOnly`, `SameSite` phù hợp; API dùng cookie xác thực cho thao tác ghi vẫn cần CSRF protection.

### 7.2. JWT không loại bỏ mọi state

JWT có thể được verify ở mọi replica nếu các instance chia sẻ issuer/JWKS và trust policy. Logout tức thì, refresh-token rotation, phát hiện tái sử dụng token hoặc revoke tài khoản có thể cần state dùng chung. Có thể dùng access token ngắn hạn và revoke ở tầng refresh, hoặc shared revocation store. Đừng tạo secret ký JWT ngẫu nhiên mới trên mỗi replica rồi mong token luôn hợp lệ giữa các instance. Rotation cần kế hoạch chồng lấn khóa, `kid`, JWKS và rollback version cũ/mới.

## 8. Job bất đồng bộ, outbox và HTTP 202

Đoạn code dễ gây mất việc:

~~~java
@PostMapping("/api/v1/reports")
ResponseEntity<Void> generateReport(@RequestBody ReportRequest request) {
    executor.execute(() -> reportService.generate(request));
    return ResponseEntity.accepted().build();
}
~~~

Code chỉ đặt task vào executor cục bộ. Nếu A bị terminate sau khi trả `202 Accepted` nhưng trước khi task chạy, job biến mất; nếu process chết giữa tác vụ, kết quả dở dang. B không có record để tra cứu trạng thái.

### 8.1. 202 cần trạng thái job được ghi bền

Thiết kế tốt hơn:

~~~http
POST /api/v1/reports HTTP/1.1
Authorization: Bearer <access-token>
Idempotency-Key: "report-req-42"
Content-Type: application/json

{"period":"2026-10","format":"csv"}

HTTP/1.1 202 Accepted
Location: /api/v1/report-jobs/52a1e9d0-4397-4885-912f-6604c9ce01b2
Cache-Control: no-store

{"jobId":"52a1e9d0-4397-4885-912f-6604c9ce01b2","status":"QUEUED"}
~~~

Sau khi ghi job/transaction commit, bất kỳ replica nào cũng có thể phục vụ:

~~~http
GET /api/v1/report-jobs/52a1e9d0-4397-4885-912f-6604c9ce01b2 HTTP/1.1
Authorization: Bearer <access-token>

HTTP/1.1 200 OK
Content-Type: application/json

{"jobId":"52a1e9d0-4397-4885-912f-6604c9ce01b2","status":"RUNNING"}
~~~

Kiểm tra principal/tenant cho job và kết quả tải xuống. `202` nghĩa **đã chấp nhận xử lý**, không có nghĩa công việc hoàn tất. Nếu không commit được durable job thì trả lỗi, không báo `202` giả.

### 8.2. Claim/lease khi nhiều worker cùng đọc queue

Hai worker không được cùng `SELECT first READY job` rồi xử lý trước khi một worker update. Có thể dùng PostgreSQL `FOR UPDATE SKIP LOCKED` trong transaction ngắn để claim job, gắn `lease_until`/`owner` rồi commit. Phần xử lý lâu chạy ngoài transaction claim. Nếu worker chết, lease hết hạn và job được nhận lại.

**Lease không đồng nghĩa exactly-once**. Worker A bị pause, hết lease, B nhận lại và xử lý, sau đó A tiếp tục: cả hai có thể tác động lên output. Với side effect cần idempotency/dedup theo job ID hoặc **fencing token** tăng đơn điệu mà resource đích kiểm tra. Chỉ kiểm tra Redis lock ở thời điểm bắt đầu không đủ cho thao tác kéo dài.

### 8.3. Transactional outbox bảo vệ event sau commit

Tránh:

~~~java
orderRepository.save(order);
messageBroker.publish(new OrderCreated(order.id()));
// Một phía có thể thành công khi phía kia thất bại.
~~~

Thay bằng:

~~~mermaid
flowchart LR
    H["POST /orders"] --> T["Một DB transaction"]
    T --> A["INSERT order"]
    T --> B["INSERT outbox event"]
    A --> C["COMMIT"]
    B --> C
    C --> W["Publisher worker"]
    W --> Q[("Durable broker")]
    Q --> U["Idempotent consumer"]
~~~

Business row và outbox row cùng commit. Worker sau đó publish rồi mark sent. Nếu worker crash **sau broker nhận event nhưng trước khi mark sent**, có thể publish lại; consumer cần dedup. Outbox ngăn mất **ý định publish** khi DB đã commit, nhưng không tự bảo đảm exactly-once effect trên mọi hệ thống.

Với Kafka/RabbitMQ, phải hiểu broker ack, replication, retention, consumer offset và redelivery. “Queue durable” không tự bảo đảm mọi message được lưu nếu publisher không xác nhận hoặc failover theo cấu hình không đủ an toàn.

## 9. Upload, export và object storage

Không nên ghi file khách hàng vào `/tmp` trong container rồi trả URL `/files/123` và mong mọi replica đọc được. Local disk của Pod thường không có nghĩa là shared durable storage; restart/reschedule/đổi node có thể làm file biến mất.

Thiết kế upload:

1. Nhận `POST /api/v1/uploads` với xác thực, quyền, validation và giới hạn kích thước.
2. Ghi blob vào object storage hoặc kho bền phù hợp, xác minh hoàn tất và checksum nếu cần.
3. Ghi DB metadata (owner, tenant, object key, hash, size, scan status, retention).
4. Chỉ công bố `READY` khi object đã ghi xong và vượt kiểm tra cần thiết.
5. Khi client tải qua replica khác, kiểm tra quyền rồi stream/proxy hoặc cấp signed URL ngắn hạn.
6. Có cleanup object mồ côi và reconciliation metadata vì DB và object store thường **không có transaction atomic chung**.

Chọn DB cho metadata/trạng thái workflow; object store cho blob. Không đưa thông tin nhạy cảm vào object key dễ đoán; signed URL cũng là credential có thời hạn, cần HTTPS và tránh ghi nguyên URL vào log/Referer.

## 10. Cache, rate limit và lock dùng chung tạm thời

Không phải mọi state cần bền như đơn hàng. Ví dụ cache:

~~~java
@Cacheable(cacheNames = "catalog", key = "#skuId")
public CatalogItem findCatalogItem(UUID skuId) {
    return repository.findPublished(skuId);
}
~~~

Cache local trên A/B có thể chứa phiên bản hơi khác nhau; nếu độ cũ chấp nhận được, điều đó hợp lệ. Muốn cập nhật giá đồng thời, cần version/TTL/invalidation hoặc cache dùng chung được thiết kế đúng. Redis không xóa được mọi stale cache vì CDN, browser và cache client cũng có thể giữ response.

### 10.1. Cache key phải chứa ngữ cảnh bảo mật

Nếu `GET /api/v1/orders` thay đổi theo tenant, principal, scope, locale hoặc field permission, key chỉ là `"/api/v1/orders"` có thể lộ dữ liệu xuyên tenant. Key phải phụ thuộc **đầy đủ các input thay đổi representation**, có TTL/invalidation. Không cache raw response có `Authorization` như tài sản public nếu contract không cho phép; `Cache-Control`/`Vary` cần đúng.

### 10.2. Rate limit chia sẻ nhưng không là business ledger

Nếu mỗi replica giới hạn 100 request/phút riêng, với 3 replica user có thể được phục vụ khoảng 300 request/phút. Nếu quota toàn cụm, dùng token bucket/counter **atomic chung** ở gateway/Redis/dịch vụ quota, TTL theo cửa sổ và chính sách khi store lỗi.

Quota để giảm abuse có thể chấp nhận sai số khi failover; quota **tính tiền hoặc bảo đảm hợp đồng** cần record bền và reconciliation. Không coi Redis counter có TTL/eviction là sổ cái thanh toán.

### 10.3. Lock chỉ là điều phối

`synchronized`, `ReentrantLock` và `Semaphore` chỉ phối hợp trong một JVM. DB row lock, Redis lease hoặc coordinator giúp điều phối nhiều replica, nhưng cần namespace, TTL, renewal, recovery khi network partition, và **fencing/idempotency/constraint** nếu holder cũ có thể tiếp tục sau khi mất lease. Nếu một `UPDATE ... WHERE status='PENDING'` atomic là đủ, không nhất thiết phải xây distributed lock riêng.

## 11. WebSocket/SSE: kết nối sống không thể copy

WebSocket kết nối tới replica cụ thể; socket TCP và subscription in-memory không thể được “chuyển nguyên vẹn” sang B khi A chết. Hệ thống cần:

1. Client reconnect với backoff, xác thực lại và resubscribe.
2. Nếu cần không mất event, lưu **event history/cursor** bền vững và hỗ trợ resume.
3. Phát event đến replica sở hữu kết nối qua pub/sub hoặc event bus chung; không chỉ qua map sessions của A.
4. Phân biệt pub/sub ephemeral với durable message log; client offline có thể bỏ lỡ event.

SSE tương tự: `Last-Event-ID` ở client không có nghĩa server tự có event history. Nếu cần resume đúng, phải có event log, cursor và retention. Kiểm tra quyền tenant/room trên mọi subscription và event, kể cả khi qua bus.

## 12. Rolling update và scale-in an toàn

Khi thay đổi số replica, trạng thái phải chịu được:

- **Rolling update:** version N/N+1 cùng đọc ghi schema, session, job/event payload trong giai đoạn chuyển tiếp.
- **Crash/restart:** local cache, thread/task, socket biến mất; durable records có thể được xử lý tiếp.
- **Scale-in:** ngừng nhận request mới, kết thúc request đang chạy trong ngân sách, nhường lease job/cho retry.
- **Zone failure:** shared database, broker và session store cũng cần HA/failover chứ không chỉ API.
- **Network partition:** tránh nhiều worker đều tin mình là leader; invariants phải được bảo vệ tại source of truth.

### 12.1. Readiness, liveness, startup và graceful shutdown

- **Readiness:** Pod có thể nhận request mới không? Endpoint/proxy cập nhật theo thời gian, không tức thời tuyệt đối.
- **Liveness:** ứng dụng có cần restart không? Đừng dùng lỗi DB thoáng qua làm liveness fail gây restart hàng loạt.
- **Startup:** cho phép khởi động/warm-up đủ thời gian trước khi liveness can thiệp.
- **Graceful shutdown:** ngừng tiếp nhận việc mới và cho request có thời gian kết thúc, đồng thời xử lý lease job có chủ đích.

Ví dụ Spring Boot:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health
~~~

30 giây chỉ minh họa; cần phối hợp `terminationGracePeriodSeconds` của Kubernetes, gateway timeout, thời gian request và worker lease. **Graceful shutdown không làm task trong RAM thành durable**. Bảo vệ management endpoint bằng network/auth; readiness OK không chứng minh queue không backlog.

### 12.2. Schema migration tương thích khi hai phiên bản cùng chạy

Nếu N+1 đổi kiểu `status` và xóa cột cũ trước khi N dừng, N có thể lỗi. Dùng **expand-and-contract**:

1. Mở rộng schema mà version cũ vẫn đọc/ghi được.
2. Deploy code tương thích dữ liệu cũ/mới; nếu dual-write, xác định một nguồn sự thật.
3. Backfill có thể resume, idempotent và đo được tiến độ.
4. Chỉ drop cột cũ sau khi không còn replica/consumer cũ và đã xác minh dữ liệu.

Áp dụng cho **Redis session serialization**, outbox payload và broker message schema. Không lưu nguyên object Java serialized nhạy cảm với class version khi một schema versioned/DTO nhỏ có thể phù hợp hơn. Rollback cũng cần được thử, không chỉ upgrade một chiều.

## 13. Bảo mật, backup và retention của trạng thái chung

| Vấn đề | Câu hỏi vận hành |
| --- | --- |
| Confidentiality | DB/Redis/blob chứa session, token, PII, tài chính hay bí mật? Mã hóa khi lưu/truyền? |
| Access control | API/worker nào được đọc/ghi? Least privilege và tách credential theo dịch vụ? |
| Tenant isolation | Key, query, object/job lookup có lọc đúng tenant/principal không? |
| Retention/TTL | Idempotency, session, file, audit tồn tại bao lâu và ai dọn? |
| Backup/restore | RPO/RTO rõ ràng? Đã thử restore và recovery key mã hóa chưa? |
| Cross-store restore | DB có khớp object store/outbox/broker sau restore không? Cần reconciliation? |
| Data minimization | Cần lưu raw request/response nhạy cảm hay chỉ hash/resource pointer? |
| Incident response | Có revoke session/refresh token hoặc rotate secret trên toàn cụm? |

**Backup không thay thế HA.** Backup giúp phục hồi mất dữ liệu; HA giữ dịch vụ hoạt động qua node failure. **Replication không thay backup**: xóa nhầm hay dữ liệu sai có thể được replicate ngay. Redis nhiều replica nhưng persistence/eviction không đáp ứng yêu cầu cũng không phải store bền tương đương DB cho dữ liệu tài chính/idempotency bắt buộc.

Với trạng thái ghi quan trọng, nên **fail closed** khi store dùng để bảo vệ invariant không sẵn sàng, thay vì nhận request và để kết quả không thể khôi phục. Chính sách degraded mode chỉ phù hợp khi có cam kết rõ ràng và an toàn.

## 14. Observability cho nhiều replica

Mục tiêu không chỉ biết replica A đang chạy mà là lời hứa nghiệp vụ còn đúng khi A biến mất:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| HTTP request rate, p95/p99, 4xx/5xx theo route | Bất thường sau deploy/scale? |
| Idempotency new/replay/conflict/in-progress/DB lock timeout | Retry tạo trùng hoặc tranh khóa kéo dài? |
| Đơn tạo mới, tồn kho âm, unique violation | Business invariant có bị phá không? |
| Session lookup hit/miss/expiry/store error | Login/session có mất khi đổi replica không? |
| Job ready/in-flight/retry/dead/oldest age | Đã nhận 202 nhưng xử lý trễ/mất? |
| Outbox unpublished count/age/publish retries | DB commit nhưng downstream chưa có event? |
| Broker lag/redelivery/dedup | Side effect bị trùng hoặc chậm? |
| DB pool pending, SQL latency, transaction rollback | Shared storage thành bottleneck khi scale? |
| Redis eviction/failover/latency | Session/cache/quota có suy giảm? |
| Pod restarts/terminations/readiness | Rollout/scale-in có liên quan sự cố? |

Metric labels nên dùng route template, operation hữu hạn, status class, region/instance; **không dùng idempotency key, session ID, user ID, job ID hay order ID làm metric label**. ID có thể xuất hiện trong log/trace có kiểm soát, masking và quyền truy cập; trace liên kết HTTP/outbox/worker nhưng không đồng nghĩa một transaction phân tán.

### 14.1. SLO cho job và tính bền vững

Với `202`, SLO “99,9% request nhận trong 100 ms” không đo thời gian **hoàn tất job**. Cần time-to-completion, tỷ lệ job thành công trước deadline, backlog age, recovery time sau restart và khả năng tra cứu qua replica khác. Idempotency invariant có thể kiểm tra định kỳ bằng query kiểm toán trên database; không đưa mỗi key vào Prometheus.

## 15. Kiểm thử hai replica, crash và retry

Unit test một `ConcurrentHashMap` không chứng minh scale-out. Cần **ít nhất hai process/app instance độc lập** trỏ vào cùng store và chạy fault test trong môi trường cách ly.

| Tình huống | Cách thực hiện | Bằng chứng mong đợi |
| --- | --- | --- |
| Tạo ở A, đọc ở B | POST A, GET B | Cùng resource, đúng quyền/tenant |
| Same key ở A và B | Hai POST concurrent cùng key/payload | Một đơn, một lần giữ hàng, replay đúng |
| Same key khác payload | Key cũ, quantity khác | Từ chối, không ghi đơn mới |
| A chết trước commit | Kill A khi transaction mở | Không partial order/inventory/key; retry B an toàn |
| A commit nhưng response mất | Ngắt response sau commit, retry B | ID cũ, không có hiệu ứng thứ hai |
| Khác key tranh tồn cuối | Hai POST đồng thời | Tồn kho không âm, chỉ một đơn thành công |
| A trả 202 rồi chết | Dừng A sau khi job commit | B/worker tra cứu/hoàn tất job được |
| Worker chết giữa xử lý | Kill sau claim/before ack | Lease/retry và idempotent side effect |
| Session đổi replica | Login A, gọi B rồi logout | Session hoạt động theo thiết kế |
| Session store/broker mất | Ngắt store test | Fail closed/degraded policy đã định nghĩa |
| Rolling N/N+1 | Hai version dùng chung storage | Schema/session/message tương thích |
| Restore backup | Khôi phục môi trường cách ly | RPO/RTO, reconciliation được kiểm chứng |

### 15.1. Smoke test qua HTTP

Giả định hai URL riêng của replica:

~~~bash
curl -i -X POST "https://replica-a.test.example/api/v1/orders" \
  -H "Authorization: Bearer <test-token>" \
  -H 'Idempotency-Key: "order-retry-42"' \
  -H "Content-Type: application/json" \
  --data '{"skuId":"11111111-1111-4111-8111-111111111111","quantity":1}'

curl -i -X POST "https://replica-b.test.example/api/v1/orders" \
  -H "Authorization: Bearer <test-token>" \
  -H 'Idempotency-Key: "order-retry-42"' \
  -H "Content-Type: application/json" \
  --data '{"skuId":"11111111-1111-4111-8111-111111111111","quantity":1}'
~~~

Các hostname chỉ minh họa. Assertions quan trọng ngoài status: cùng order ID, đúng một business action, tồn kho chỉ giảm một lần và request không tạo side effect ngoài dự kiến. Trong test “commit rồi response mất”, cần **fault injection sau commit nhưng trước khi nhận body** (chẳng hạn proxy test cắt response), không kill process ngẫu nhiên rồi đoán transaction đã commit.

### 15.2. Test Java/Spring với database thật

Integration test dùng PostgreSQL Testcontainers và gọi application service qua Spring bean:

~~~java
@SpringBootTest
class DurableOrderStateIT {
    @Autowired CreateOrderService service;
    @Autowired JdbcTemplate jdbc;

    @Test
    void replayReturnsExistingOrderWithoutReservingAgain() {
        CreateOrder payload = new CreateOrder(
            UUID.fromString("11111111-1111-4111-8111-111111111111"), 1);
        // Fixture: tenant-a, alice, SKU có ít nhất 2 đơn vị.
        OrderResult first =
            service.create("tenant-a", "alice", "key-test-001", payload);
        OrderResult second =
            service.create("tenant-a", "alice", "key-test-001", payload);

        assertThat(first.replayed()).isFalse();
        assertThat(second.replayed()).isTrue();
        assertThat(second.orderId()).isEqualTo(first.orderId());
        // Assert DB: một order, tồn kho giảm đúng 1 đơn vị.
    }
}
~~~

Code là **khung test**, phụ thuộc fixture/schema và import JUnit/AssertJ/Spring. Không đặt `@Transactional` trên test khiến rollback cuối test che lỗi commit của ứng dụng; đọc dữ liệu sau commit từ transaction độc lập. Để chứng minh **giữa hai process**, phải chạy hai instance khác nhau trỏ cùng DB, không chỉ tạo hai object service trong một JVM.

### 15.3. Phân bố test theo rủi ro

- **Unit:** fingerprint canonical, rule TTL/retry và state machine job.
- **Controller:** HTTP `201`/`202`/`409`, `Location`, validation và Problem Details.
- **Integration:** DB transaction, unique constraint, concurrent row update, session Redis, worker lease.
- **E2E/chaos có kiểm soát:** hai replica qua gateway, rolling deploy, scale-in, response loss, security và observability.

Đánh giá bằng bất biến cuối: không có đơn trùng, tồn kho không âm, không mất job đã nhận, không lộ dữ liệu cross-tenant và trạng thái được đọc qua replica bất kỳ.

## 16. Runbook khi trạng thái “mất” sau scale

Khi người dùng báo “sau deploy bị logout”, “job không thấy nữa” hoặc “retry tạo hai đơn”:

1. **Phân loại:** local state, cache, session, database resource, durable job hay outbox?
2. **Tái hiện theo replica:** request đầu/sau đi đâu, route/trace ID/deployment version nào?
3. **Kiểm tra source of truth:** transaction đã commit hay log mới ghi “processing”?
4. **Kiểm tra uniqueness/lease:** idempotency namespace, DB lock waits, job claim, stale worker?
5. **Kiểm tra rollout:** schema/JWKS/session payload N/N+1 có tương thích?
6. **Kiểm tra store:** Redis evictions/TTL/persistence, broker ack, DB replica lag, object permission?
7. **Giảm tác động:** chặn ghi khi không bảo đảm invariant, giảm retry storm, khôi phục worker hoặc rollback phù hợp.
8. **Phục hồi và kiểm toán:** replay outbox/job có dedup, reconcile đơn/charge, kiểm tra tenant và SLO.

Đừng kết luận “load balancer làm mất đơn” chỉ vì request tới B. Nếu đơn commit trong DB dùng chung thì B phải đọc được theo consistency contract. Nếu B đọc từ read replica bị trễ, cần read-your-writes hoặc đọc primary cho truy vấn ngay sau ghi: đó là **độ nhất quán đọc**, không phải mất dữ liệu.

## 17. Bài tập thực hành

**Bài tập 1 — Phân loại trạng thái.** Spring Boot giữ session trong `HttpSession` local, idempotency key trong `ConcurrentHashMap`, đơn trong PostgreSQL, cache catalog trong Caffeine và export file ở `/tmp`. Khi scale 1→4 replica rồi scale-in, phân loại trạng thái nào có nguy cơ mất/không nhìn thấy, nơi lưu phù hợp và dữ liệu nào tái tạo được.

**Bài tập 2 — Idempotency nhiều replica.** Thiết kế `POST /api/v1/orders` qua load balancer khi client có thể timeout sau commit. Định nghĩa unique key tenant/caller/operation, fingerprint, result, TTL/cleanup, conflict cùng key khác payload. Viết test hai POST đồng thời tới hai instance và assert một lần giữ hàng.

**Bài tập 3 — 202 và job bền vững.** API `POST /api/v1/reports` đặt task vào `ThreadPoolTaskExecutor` rồi trả `202`. Chuyển sang DB job table/broker bền, thêm `GET /report-jobs/{id}`, ownership, claim/lease, retry/deadline và trạng thái `QUEUED`/`RUNNING`/`SUCCEEDED`/`FAILED`. Chứng minh job không mất sau khi dừng replica nhận request.

**Bài tập 4 — Session và bảo mật.** Frontend dùng cookie session trên A/B. Thiết kế Spring Session với shared store hoặc JWT + refresh token phù hợp. Thử login A, gọi B, logout B rồi gọi A. Giải thích SameSite/CSRF, key rotation, TTL và failover Redis.

**Bài tập 5 — Lỗi lease.** Hai worker dùng Redis lock TTL 30 giây xử lý báo cáo 60 giây. A bị pause, lease hết hạn, B nhận job, rồi A tiếp tục ghi kết quả. Đề xuất renew/fencing/idempotent output và test ngăn writer cũ ghi đè.

**Bài tập 6 — Rolling update.** Version N lưu session field thành Java enum, N+1 đổi tên enum khi triển khai rolling. Thiết kế schema/version tương thích, expand-and-contract, rollback và test N/N+1 đọc session/outbox/job.

**Bài tập 7 — Phục hồi nhiều store.** Tạo đơn, lưu attachment object store, ghi DB metadata rồi publish event. Phân tích điểm crash giữa bước, chọn outbox, cleanup object mồ côi, reconciliation, backup/restore và điều kiện commit trước `201`/`202`.

### Tiêu chí hoàn thành

Lời giải đạt yêu cầu nếu (1) phân biệt state local/shared/durable/lease; (2) chỉ rõ source of truth, retention và consistency; (3) dùng transaction/constraint chống race ở mọi replica; (4) không coi sticky session hay `@Async` local là bảo đảm bền; (5) có test restart/scale-in/retry/job recovery; và (6) có kế hoạch bảo mật, backup, rollout và giám sát.

## 18. Checklist trước khi mở rộng nhiều tiến trình

- [ ] Trạng thái cần sống qua commit/restart có source of truth chung, schema và mức bền rõ ràng.
- [ ] Resource/unique constraint/atomic update và concurrency control áp dụng toàn cụm, không dựa vào `synchronized` cục bộ.
- [ ] Idempotency key có namespace, fingerprint, kết quả/TTL; commit xong nhưng response mất có thể retry sang replica khác.
- [ ] Session/token/refresh/revocation dùng chung đúng thiết kế; sticky session không phải điều kiện để hệ thống đúng.
- [ ] API `202` chỉ phát khi job đã được ghi bền; worker có lease/retry/dedup và client tra cứu trạng thái.
- [ ] Event sau commit dùng outbox hoặc protocol tương đương; consumer có idempotency.
- [ ] File/blob không chỉ ở container filesystem; metadata/quyền/lifecycle lưu bền.
- [ ] Cache/rate limit có scope/TTL/consistency phù hợp; store tạm không bị coi là ledger.
- [ ] WebSocket/SSE có reconnect, pub/sub dùng chung và durable history/resume nếu cần.
- [ ] Rolling update tương thích N/N+1 ở DB schema, session payload, JWT keys, message format.
- [ ] Có readiness, graceful shutdown, handling scale-in, store failover, backup/restore và reconciliation.
- [ ] Test hai replica thực, concurrent request, crash trước/sau commit, retry, outbox/job recovery và cross-tenant.
- [ ] Log/trace/metric không chứa session ID, token, idempotency key và PII nhạy cảm ở nơi công khai.

**Kết luận:** mở rộng REST API bằng nhiều tiến trình không chỉ là nhân số instance. Sự đúng đắn đến từ việc **mỗi loại trạng thái có nơi lưu và vòng đời phù hợp**: dữ liệu nghiệp vụ và cam kết đã công bố phải bền vững; thao tác cạnh tranh cần atomic constraint; session/job phải đi qua store chung khi cần; cache và kết nối cục bộ phải tái tạo được. Khi replica thay đổi liên tục, hệ thống vẫn phải giữ đúng hợp đồng HTTP và bất biến nghiệp vụ.

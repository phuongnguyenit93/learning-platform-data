# Xử lý hai yêu cầu cùng khóa đến đồng thời

## 1. Bài toán: request trùng tới trước khi request đầu hoàn tất

Một ứng dụng bán hàng gọi **POST /api/orders** với header `Idempotency-Key: K-913`. Vì mạng chậm, người dùng nhấn nút lần nữa; SDK cũng có thể retry và load balancer chuyển hai yêu cầu đến **hai instance khác nhau**. Cả hai request tới khi server **chưa trả phản hồi cho request đầu**.

~~~text
                Cùng tenant, cùng operation, cùng key K-913
Client ──────── POST A ────────> API instance A ──┐
       └──────── POST B ────────> API instance B ──┼──> Database
                                                  └──> Downstream
~~~

Mục tiêu không phải “cả hai HTTP response giống nhau”. Mục tiêu là **hai request đại diện cho một ý định nghiệp vụ chỉ tạo một order intent**, không trừ hàng/tạo thanh toán hai lần, và client có cách biết trạng thái của ý định đó.

Trong chương **Lũy đẳng và thử lại** của module **INTEGRATION_API_REST**, nội dung này tập trung vào **race condition**, cách giành quyền xử lý nguyên tử, hợp đồng HTTP khi request đang chạy, transaction và kiểm thử cạnh tranh bằng Java/Spring. Kiến thức về resource, URI, HTTP methods/status, idempotency, OpenAPI, phân quyền và lỗi API đều được dùng trong một tình huống cụ thể.

**Sau bài học, bạn cần phân biệt được ba sự thật:**

1. **Cùng key** chưa chắc **cùng yêu cầu**; phải so sánh phạm vi và fingerprint.
2. **Một request đã giành được key** chưa chắc **nghiệp vụ đã hoàn tất**.
3. **Một bản ghi chống trùng ở API** chưa chắc đã ngăn trùng tại payment provider hoặc message consumer.

## 2. Race condition của cách làm “kiểm tra rồi thực hiện”

Một implementation dễ mắc lỗi:

~~~text
if not idempotencyStore.exists(key):
    result = createOrderAndChargePayment()
    idempotencyStore.save(key, result)
return result
~~~

Khi hai request đồng thời, thao tác **`exists` và `save` không nguyên tử**:

| Thời điểm | Instance A | Instance B |
|---|---|---|
| t1 | Kiểm tra K: chưa có | |
| t2 | | Kiểm tra K: chưa có |
| t3 | Tạo đơn O1, gửi charge P1 | |
| t4 | | Tạo đơn O2, gửi charge P2 |
| t5 | Lưu K → O1 | |
| t6 | | Lưu K → O2 hoặc gặp unique conflict |

Nếu **unique constraint chỉ được áp dụng ở t6**, giao dịch charge P2 đã có thể diễn ra. Unique constraint muộn **không hoàn tác được** tác động bên ngoài database.

### Bất biến cần giữ

Với một phạm vi `(tenant, operation, key)` còn hiệu lực:

- Chỉ **một bản ghi claim** được tạo thành công.
- Chỉ **một business operation** được tiếp nhận để thực thi.
- Request trùng có **cùng fingerprint** nhận trạng thái của **operation đó**, không tạo operation mới.
- Request trùng **khác fingerprint** bị từ chối mà không thay đổi ý định ban đầu.
- Khi kết quả nghiệp vụ không rõ, hệ thống **tra cứu/đối soát**, không tự mở một effect mới.

**Điểm tuyến tính hóa (linearization point)** tại tầng tiếp nhận là lúc claim được ghi nhận nguyên tử và commit bền vững, không phải lúc client nhận status 202 hay lúc bản ghi cache xuất hiện.

## 3. Hợp đồng HTTP khi một khóa đang được sử dụng

API cần công bố ít nhất bốn trường hợp: **khóa mới**, **khóa trùng đang xử lý**, **khóa trùng đã hoàn tất**, **khóa trùng nhưng dữ liệu khác**.

Ví dụ một request:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
Idempotency-Key: K-913
Content-Type: application/json

{"cartId":"cart-91","shippingAddressId":"addr-9"}
~~~

### Chính sách minh họa: tạo operation bất đồng bộ

**Lần đầu**, server ghi nhận bền vững một operation:

~~~http
HTTP/1.1 202 Accepted
Location: /api/operations/7e1a2f9b-654f-4e19-8b2c-c3e865b3fc14
Content-Type: application/json
Cache-Control: no-store

{"operationId":"7e1a2f9b-654f-4e19-8b2c-c3e865b3fc14","state":"PENDING"}
~~~

**Lần hai tới khi operation đang chạy**, cùng key và cùng fingerprint:

~~~http
HTTP/1.1 202 Accepted
Location: /api/operations/7e1a2f9b-654f-4e19-8b2c-c3e865b3fc14
Content-Type: application/json
Cache-Control: no-store

{"operationId":"7e1a2f9b-654f-4e19-8b2c-c3e865b3fc14","state":"PROCESSING"}
~~~

Hai response có thể **khác trường state**, nhưng **operationId phải là cùng một operation**. Không có đơn hàng thứ hai được tạo vì request B.

**Sau khi hoàn tất**, client có thể đọc `GET /api/operations/7e1a2f9b-654f-4e19-8b2c-c3e865b3fc14`; một request POST trùng key có thể nhận **200 OK với trạng thái cuối** hoặc **response đã lưu của lần đầu**, tùy contract. Không có quy tắc HTTP tổng quát bắt hai request trùng key phải dùng cùng status hay trả lại cùng byte response.

**Khóa trùng nhưng payload khác** phải bị từ chối:

~~~http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/idempotency-key-reused",
  "title": "Idempotency key reused with different request",
  "status": 422,
  "code": "IDEMPOTENCY_KEY_MISMATCH",
  "detail": "Khóa này đã được dùng cho một yêu cầu khác."
}
~~~

**422 là quyết định của hợp đồng minh họa**, không phải HTTP bắt buộc cho mọi ứng dụng idempotency. Với yêu cầu trùng **đang xử lý**, một API đồng bộ cũng có thể chọn **409 Conflict** kèm mã lỗi `IDEMPOTENCY_IN_PROGRESS` và hướng dẫn tra cứu/thử lại. Điều quan trọng là **không chạy lại cùng thao tác** và hành vi được mô tả rõ trong OpenAPI.

| Tình trạng khóa trong scope | Fingerprint | Phản hồi gợi ý | Tác động được phép |
|---|---|---|---|
| Chưa có | Mới | **202** + Location, tạo operation | **Một** claim và operation |
| `PENDING/PROCESSING` | Trùng | **202** + cùng Location; hoặc **409** theo policy | **Không** tạo thêm |
| `SUCCEEDED/FAILED_FINAL` | Trùng | Kết quả đã lưu hoặc trạng thái operation theo policy | **Không** chạy lại |
| Bất kỳ trạng thái còn hiệu lực | Khác | **422** hoặc **409** theo policy | **Không** đổi request cũ |
| Thiếu key trong endpoint yêu cầu | — | **400 Bad Request** | Chưa tiếp nhận |

**202 chỉ nghĩa là đã chấp nhận xử lý**, không phải đơn hàng/thu tiền đã thành công. Nếu server chọn replay response cũ, kết quả có thể phản ánh **thời điểm operation ban đầu**, không phải representation mới nhất của resource.

## 4. Phạm vi khóa và fingerprint: chống nhầm hai ý định

Không dùng một `Idempotency-Key` làm khóa Redis/DB toàn cục nếu nhiều tenant có thể tạo cùng chuỗi. Một composite key hợp lý:

~~~text
(authenticatedTenantId, operationKind, idempotencyKey)
~~~

- **Tenant/user/service identity** phải đến từ security context đã xác thực, không tin `X-Tenant-ID` tùy ý từ client.
- **Operation kind** phân biệt `CREATE_ORDER`, `REFUND_PAYMENT` và các thao tác khác; không để cùng key ở hai endpoint vô tình trả chéo kết quả.
- **Fingerprint** bảo vệ cùng key không bị dùng lại cho nội dung khác. Có thể tính SHA-256 từ `method + operationKind + canonical payload` theo quy tắc được công bố.
- **Một intent mới** phải dùng key mới, ngay cả khi payload giống intent cũ. Không dedupe chỉ bằng hash của payload vì người dùng có thể cố ý mua hai món giống nhau.

Ví dụ hai request có cùng key nhưng `shippingAddressId` khác nhau là **mismatch**, không phải “cập nhật payload đang chờ”. Một retry đúng cần **giữ nguyên intent**.

### Canonicalization và bí mật

JSON có thể giống nghĩa nhưng khác thứ tự trường hoặc khoảng trắng. Server phải chọn:

- Hash trên **raw bytes** và yêu cầu retry gửi body byte-identical; hoặc
- Hash trên **dữ liệu đã chuẩn hóa có kiểm soát**, quy định kiểu số, null, default values, Unicode và các trường nào tham gia.

Không hash dựa trên chuỗi tùy tiện của `Map.toString()`. Không log raw access token, key chứa thông tin nhạy cảm hoặc payload thanh toán; hạn chế dữ liệu trả cho một principal khác dù biết được khóa.

## 5. Claim nguyên tử bằng database và unique constraint

Với nhiều instance, một cơ sở dữ liệu quan hệ có transaction và unique constraint là nền tảng rõ ràng để **giành quyền tiếp nhận operation**. Ví dụ PostgreSQL:

~~~sql
CREATE TABLE idempotency_claims (
    tenant_id       text        NOT NULL,
    operation_kind  text        NOT NULL,
    idem_key        varchar(200) NOT NULL,
    request_hash    char(64)    NOT NULL,
    operation_id    uuid        NOT NULL UNIQUE,
    created_at      timestamptz NOT NULL DEFAULT now(),
    expires_at      timestamptz NOT NULL,
    PRIMARY KEY (tenant_id, operation_kind, idem_key)
);

CREATE TABLE order_operations (
    operation_id uuid PRIMARY KEY,
    tenant_id    text NOT NULL,
    state        text NOT NULL,
    request_json jsonb NOT NULL
);

CREATE TABLE outbox_events (
    event_id      uuid PRIMARY KEY,
    operation_id  uuid NOT NULL,
    event_type    text NOT NULL,
    payload       jsonb NOT NULL,
    published     boolean NOT NULL DEFAULT false
);
~~~

**Transaction tiếp nhận** thực hiện ba bước ngắn:

1. **Atomic insert claim** với khóa duy nhất; nếu conflict, không sinh operation mới.
2. Nếu claim mới: ghi **order operation** và **outbox event** trong **cùng database transaction**.
3. **Commit**; chỉ sau commit mới trả **202 Accepted**.

~~~sql
-- Thực thi trong transaction của request; không gọi dịch vụ mạng ở đây.
INSERT INTO idempotency_claims
    (tenant_id, operation_kind, idem_key, request_hash,
     operation_id, expires_at)
VALUES
    (:tenant, 'CREATE_ORDER', :key, :hash,
     :operationId, now() + interval '48 hours')
ON CONFLICT (tenant_id, operation_kind, idem_key)
DO NOTHING;
~~~

**Một hàng được thêm** nghĩa là request đã claim thành công. **Không có hàng được thêm** nghĩa là khóa đã tồn tại; request phải đọc record cũ, kiểm tra fingerprint và dùng **operationId cũ**.

Ở **PostgreSQL READ COMMITTED**, nếu request A chưa commit claim, request B có thể **chờ quyết định của unique constraint**. Sau khi câu `INSERT ... ON CONFLICT DO NOTHING` hoàn thành, một câu `SELECT` **mới** trong transaction của B có thể nhìn thấy record A vừa commit. Không được làm `SELECT` kiểm tra trước rồi mới coi đó là quyền thực thi; chỉ **insert atomic/unique constraint** quyết định ai thắng.

### Tại sao không dùng một database transaction kéo dài để gọi PSP?

Nếu giữ transaction mở trong lúc gọi payment provider mất vài giây, bạn có thể khóa row lâu, giữ connection pool và khiến request B chờ không cần thiết. Quan trọng hơn, **DB transaction không bao trùm side effect ở provider**. Mô hình an toàn hơn thường là:

**Claim + persist intent + outbox (transaction ngắn) → worker thực hiện → cập nhật trạng thái + đối soát**.

Khi request B tới trong lúc A còn chạy, nó được trả **cùng operationId** mà không cần chờ PSP hoàn tất.

## 6. Java/Spring Boot 3: triển khai claim hai request cạnh tranh

Ví dụ tập trung vào phần **giành key và ghi intent**. `JdbcTemplate` được dùng với PostgreSQL; code chưa bao gồm authentication, JSON canonicalizer, worker, error handler hay migration. Những phần này phải được cung cấp trong ứng dụng thật.

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

record ClaimResult(UUID operationId, String state, boolean created) {}
record ExistingClaim(UUID operationId, String hash, String state) {}

class IdempotencyKeyMismatch extends RuntimeException {}

@Service
public class OrderClaimService {
    private final JdbcTemplate jdbc;

    public OrderClaimService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public ClaimResult claim(
            String tenantId, String key,
            String requestHash, String canonicalJson) {

        UUID operationId = UUID.randomUUID();
        int inserted = jdbc.update("""
            INSERT INTO idempotency_claims
                (tenant_id, operation_kind, idem_key, request_hash,
                 operation_id, expires_at)
            VALUES (?, 'CREATE_ORDER', ?, ?, ?,
                    now() + interval '48 hours')
            ON CONFLICT (tenant_id, operation_kind, idem_key)
            DO NOTHING
            """, tenantId, key, requestHash, operationId);

        if (inserted == 1) {
            jdbc.update("""
                INSERT INTO order_operations
                    (operation_id, tenant_id, state, request_json)
                VALUES (?, ?, 'PENDING', CAST(? AS jsonb))
                """, operationId, tenantId, canonicalJson);

            jdbc.update("""
                INSERT INTO outbox_events
                    (event_id, operation_id, event_type, payload)
                VALUES (?, ?, 'OrderRequested', CAST(? AS jsonb))
                """, UUID.randomUUID(), operationId, canonicalJson);

            return new ClaimResult(operationId, "PENDING", true);
        }

        ExistingClaim old = jdbc.queryForObject("""
            SELECT c.operation_id, c.request_hash, o.state
            FROM idempotency_claims c
            JOIN order_operations o
              ON o.operation_id = c.operation_id
            WHERE c.tenant_id = ?
              AND c.operation_kind = 'CREATE_ORDER'
              AND c.idem_key = ?
            """, (rs, row) -> new ExistingClaim(
                    rs.getObject("operation_id", UUID.class),
                    rs.getString("request_hash"),
                    rs.getString("state")), tenantId, key);

        if (!old.hash().equals(requestHash)) {
            throw new IdempotencyKeyMismatch();
        }
        return new ClaimResult(
                old.operationId(), old.state(), false);
    }
}
~~~

### Những điều code thực sự bảo đảm

- **Unique constraint** trên `(tenant_id, operation_kind, idem_key)` phân định người thắng trên **mọi instance cùng dùng database**.
- Transaction lưu **claim, operation và outbox** cùng lúc; nếu một bước thất bại, toàn bộ thay đổi rollback.
- Request thua không tạo thêm operation/outbox; nó trả **operationId đã được claim trước đó** nếu fingerprint khớp.
- Trạng thái hiện hành được đọc từ **`order_operations.state`** (một nguồn duy nhất); không cần đồng bộ một bản sao `state` riêng trong bảng claim.
- `READ_COMMITTED` và hai câu lệnh `INSERT` rồi `SELECT` phù hợp ví dụ PostgreSQL. Khi chuyển database hoặc isolation level, cần kiểm tra lại hành vi visibility.

**Những điều code chưa bảo đảm:** việc worker chỉ gọi downstream một lần, khả năng phục hồi khi provider trả kết quả không rõ, bản ghi `PROCESSING` bị kẹt, việc dọn key hết hạn, phân quyền theo resource, hoặc response HTTP cuối. Đây là những ranh giới khác cần hợp đồng và kiểm thử riêng.

### Controller HTTP mỏng

~~~java
import java.net.URI;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

record CreateOrderRequest(String cartId, String shippingAddressId) {}
record OperationView(UUID operationId, String state) {}

@RestController
class OrderController {
    private final OrderClaimService claims;
    private final RequestFingerprint fingerprints; // service ứng dụng
    private final TenantIdentity identity;           // từ security context

    OrderController(OrderClaimService claims,
                    RequestFingerprint fingerprints,
                    TenantIdentity identity) {
        this.claims = claims;
        this.fingerprints = fingerprints;
        this.identity = identity;
    }

    @PostMapping("/api/orders")
    ResponseEntity<OperationView> create(
            @RequestHeader("Idempotency-Key") String key,
            @RequestBody CreateOrderRequest request) {

        String tenant = identity.authenticatedTenant();
        String canonicalJson = fingerprints.canonicalJson(request);
        String hash = fingerprints.hash("CREATE_ORDER", canonicalJson);
        ClaimResult result = claims.claim(
                tenant, key, hash, canonicalJson);
        URI statusUrl = URI.create(
                "/api/operations/" + result.operationId());

        if ("SUCCEEDED".equals(result.state())
                || "FAILED_FINAL".equals(result.state())) {
            return ResponseEntity.ok()
                    .location(statusUrl)
                    .body(new OperationView(
                            result.operationId(), result.state()));
        }
        return ResponseEntity.accepted()
                .location(statusUrl)
                .body(new OperationView(
                        result.operationId(), result.state()));
    }
}
~~~

`RequestFingerprint` và `TenantIdentity` là **hợp đồng của ứng dụng**, không phải class Spring có sẵn. Một HTTP 202 ở đây có nghĩa **operation đã được commit để xử lý bất đồng bộ**; worker và endpoint `GET /api/operations/{id}` phải được xây riêng. Với một API đồng bộ, có thể chọn response replay hoặc **409 in-progress**, nhưng cần công bố cách khác biệt đó.

**Tuyệt đối không dùng mã demo như hệ thống thanh toán production chưa qua thiết kế đầy đủ:** ngoài cơ chế claim còn cần validation, authorization, bảo vệ downstream, transaction isolation, TTL, outbox relay, worker ownership và recovery.

## 7. Giao message lặp, worker race và provider timeout

Giành key thành công ở API mới chặn **duplicate admission**. Nếu broker giao một event hai lần hoặc worker lease hết hạn, **hai worker vẫn có thể cùng cố thực hiện một operation**.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as API instance A
    participant B as API instance B
    participant D as DB + unique claim + outbox
    participant W as Worker
    participant P as Downstream
    par Hai request cùng key
        C->>A: POST K + payload X
        C->>B: POST K + payload X
    end
    A->>D: Atomic claim K
    B->>D: Atomic claim K
    D-->>A: Một claim được commit
    D-->>B: Claim đã tồn tại, cùng operationId
    A-->>C: 202 Location /operations/7e1a2f9b-654f-4e19-8b2c-c3e865b3fc14
    B-->>C: 202 Location /operations/7e1a2f9b-654f-4e19-8b2c-c3e865b3fc14
    D->>W: Outbox event (có thể redeliver)
    W->>P: Gọi với stable operation reference
    P-->>W: Kết quả hoặc timeout không rõ
    W->>D: Lưu/reconcile trạng thái cuối
~~~

### Ba tầng chống lặp cần phân biệt

| Tầng | Bảo vệ bằng gì? | Lỗ hổng nếu chỉ có tầng này |
|---|---|---|
| **API admission** | Atomic claim + unique key + fingerprint | Consumer/provider vẫn có thể thực thi lặp |
| **Worker processing** | Consumer dedupe theo `operationId`, lease/fencing, state transition nguyên tử | Provider đã thu tiền nhưng worker chưa ghi result |
| **External business effect** | Idempotency reference của provider, unique business reference, reconciliation | Nếu provider không hỗ trợ, không thể hứa exactly-once bằng lock nội bộ |

**Lease hết hạn không chứng minh worker cũ đã ngừng.** Nếu worker A bị pause rất lâu, worker B có thể takeover; sau đó worker A tỉnh lại và cùng gọi provider. Fencing/version guard giúp ngăn worker cũ **ghi trạng thái nội bộ**, nhưng **không tự ngăn một charge đã được gửi ra ngoài**. Phải dùng cùng **downstream idempotency reference**, hoặc tra cứu/đối soát trước khi phát sinh side effect mới.

Với payment provider không hỗ trợ idempotency hoặc status lookup đáng tin, hệ thống cần nhánh **UNKNOWN / REQUIRES_RECONCILIATION**, không liều thu lại chỉ vì HTTP call trước timeout.

### Crash ở bốn vị trí

| Vị trí crash | Điều kiện cần đúng khi phục hồi |
|---|---|
| Trước commit claim/operation/outbox | Transaction rollback; request khác có thể claim |
| Sau commit, trước 202 đến client | Retry cùng key tìm lại **operationId** cũ |
| Sau publish event, trước relay ACK | Event có thể giao trùng; consumer chịu được lặp |
| Sau provider success, trước lưu kết quả | Dùng stable reference để tra cứu/reconcile; không tạo effect mới |

Chính ở các điểm crash này, test chỉ so sánh HTTP 202 của hai request thường **không đủ** để chứng minh nghiệp vụ an toàn.

## 8. TTL, timeout và chính sách retry khi đang chạy

### Không dọn record đang xử lý chỉ vì TTL đã trôi

Nếu một order operation còn `PROCESSING` sau 48 giờ nhưng cleanup xóa idempotency claim, retry cùng key có thể tạo **operation thứ hai**. TTL của claim phải phù hợp với **vòng đời operation, thời hạn client retry và rủi ro side effect**.

Một chính sách cần xác định:

1. Retention **sau khi operation terminal**; không đơn giản xóa `PENDING/PROCESSING` quá hạn.
2. Nếu worker chết, dùng **recovery/lease** để xử lý operation đang kẹt.
3. Duy trì **business reference duy nhất** đủ lâu cho thanh toán, phát hành vé hoặc hoàn tiền ngay cả khi dữ liệu idempotency cache ngắn hạn hết hạn.
4. Không cho một key hết hạn **tái sử dụng âm thầm** nếu chưa có cách chứng minh an toàn.
5. Có `operationId` để client tra cứu sau khi deadline retry kết thúc.

### Client nên làm gì khi cùng key đang xử lý?

Với chính sách **202 + Location** của bài:

~~~text
POST cùng K → 202 PENDING/PROCESSING + /api/operations/7e1a2f9b-654f-4e19-8b2c-c3e865b3fc14
             → GET /api/operations/7e1a2f9b-654f-4e19-8b2c-c3e865b3fc14 theo nhịp hợp lý
             → SUCCEEDED | FAILED_FINAL | REQUIRES_RECONCILIATION
~~~

Client không phải tiếp tục gửi POST cùng key mỗi 100 ms. Nếu API chọn **409 in-progress**, body/header nên nói rõ cách tra cứu, mốc retry hợp lý hoặc liên kết operation. Đối với **429/503**, client tuân thủ `Retry-After` khi có, kết hợp **backoff + jitter + retry budget**; những cơ chế này kiểm soát tải, còn claim nguyên tử kiểm soát duplication.

**Không đổi key khi retry cùng intent.** Key mới báo với server đây là **ý định khác**, và có thể tạo operation/side effect khác.

## 9. OpenAPI mô tả cả trường hợp in-flight

Một hợp đồng tối giản theo **OpenAPI 3.1**, chọn **202** cho request mới và request trùng đang xử lý:

~~~yaml
openapi: 3.1.0
info:
  title: Orders API
  version: 1.0.0
paths:
  /api/orders:
    post:
      summary: Tiếp nhận một ý định tạo đơn hàng
      description: >
        Scope khóa gồm tenant đã xác thực, CREATE_ORDER và Idempotency-Key.
        Cùng khóa + cùng payload dùng lại một operationId.
        Cùng khóa + payload khác bị từ chối với 422.
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          schema:
            type: string
            minLength: 1
            maxLength: 200
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [cartId, shippingAddressId]
              properties:
                cartId:
                  type: string
                shippingAddressId:
                  type: string
      responses:
        '202':
          description: >
            Operation đã được tiếp nhận hoặc vẫn đang xử lý.
            Request trùng cùng key/payload dùng lại operationId cũ.
          headers:
            Location:
              description: URI theo dõi operation
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Operation'
        '200':
          description: Trạng thái cuối của operation đã có
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Operation'
        '400':
          description: Thiếu key hoặc request không hợp lệ
        '422':
          description: Key được dùng lại với request fingerprint khác
          content:
            application/problem+json:
              schema:
                type: object
        '429':
          description: Vượt hạn mức; không thay thế chống trùng
  /api/operations/{id}:
    get:
      summary: Tra cứu trạng thái operation
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Trạng thái hiện tại của operation được phép xem
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Operation'
components:
  schemas:
    Operation:
      type: object
      required: [operationId, state]
      properties:
        operationId:
          type: string
          format: uuid
        state:
          type: string
          enum: [PENDING, PROCESSING, SUCCEEDED, FAILED_FINAL]
~~~

**Thực tế cần bổ sung** error body, authentication/security scheme, thời hạn giữ key, giới hạn retry, mã lỗi riêng, CORS và trạng thái đối soát nếu dùng. OpenAPI chỉ mô tả contract; **không tự tạo unique constraint hay đảm bảo concurrency**.

## 10. Kiểm thử đồng thời: phải đếm business effect

### Bài test “hai request xuất phát cùng lúc”

Ý tưởng dùng hai thread gọi cùng service trên **hai transaction độc lập**. Ví dụ JUnit 5 với Spring:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class ConcurrentIdempotencyTest {
    @Autowired OrderClaimService service;
    @Autowired JdbcTemplate jdbc;

    @Test
    void concurrentSameKeyCreatesOnlyOneOperation() throws Exception {
        String key = UUID.randomUUID().toString();
        String json = """
            {"cartId":"cart-91","shippingAddressId":"addr-9"}
            """;
        String hash = "a".repeat(64); // Fixture: cùng fingerprint hợp lệ

        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);
        Callable<ClaimResult> call = () -> {
            start.await();
            return service.claim("tenant-27", key, hash, json);
        };

        try {
            Future<ClaimResult> a = pool.submit(call);
            Future<ClaimResult> b = pool.submit(call);
            start.countDown();

            ClaimResult r1 = a.get(10, TimeUnit.SECONDS);
            ClaimResult r2 = b.get(10, TimeUnit.SECONDS);
            assertEquals(r1.operationId(), r2.operationId());
            assertNotEquals(r1.created(), r2.created());

            Integer claims = jdbc.queryForObject("""
                SELECT COUNT(*) FROM idempotency_claims
                WHERE tenant_id = ? AND operation_kind = 'CREATE_ORDER'
                  AND idem_key = ?
                """, Integer.class, "tenant-27", key);
            assertEquals(1, claims);

            Integer outboxCount = jdbc.queryForObject("""
                SELECT COUNT(*) FROM outbox_events
                WHERE operation_id = ?
                """, Integer.class, r1.operationId());
            assertEquals(1, outboxCount);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Test giả định schema PostgreSQL đã được tạo và `@SpringBootTest` có `DataSource` phù hợp; **không** bọc toàn bộ test trong một transaction chưa commit. Fingerprint chuỗi `"a".repeat(64)` chỉ là dữ liệu kiểm thử, không phải SHA-256 thực tế. Test này chứng minh claim/operation/outbox **trong DB**, chưa chứng minh payment provider không charge hai lần.

### Bổ sung test tình huống khó

| Kịch bản | Điều cần assert |
|---|---|
| **Hai request cùng key, cùng body, hai pod** | Cùng operationId, đúng một claim/operation/outbox |
| **Hai request cùng key, body khác** | Một request bị từ chối mismatch, không có operation thứ hai |
| **Hai tenant cùng key** | Không rò kết quả, mỗi tenant có scope riêng |
| **Thua claim khi winner chưa commit** | Request B chờ/kết thúc hợp lệ; không tự claim thêm |
| **Winner rollback trước commit** | Request B có thể giành claim; chỉ một operation đã commit |
| **Crash sau commit, trước HTTP 202** | Retry tìm được operation cũ |
| **Outbox publish trùng** | Consumer dedupe, không làm side effect hai lần |
| **Hai worker tranh lease** | Không ghi trạng thái cũ; downstream idempotency/reconcile |
| **Provider success, response timeout** | Không charge lại bằng reference mới |
| **Record PROCESSING quá TTL** | Không bị xóa để tạo operation thứ hai |
| **Completed cùng key và payload** | Trả lại kết quả/trạng thái theo contract, không chạy lại |
| **Đồng thời 100 request** | Chỉ một intent; đo lock contention, latency và timeout |

**Test HTTP status thôi là không đủ.** Phải assert **database row count, eventId, operationId, số lần gọi provider, ledger entries hoặc hàng tồn kho**, tùy thao tác nghiệp vụ. Với lỗi mạng, dùng mock provider có thể **thực hiện charge rồi cố ý mất response** để chứng minh khả năng đối soát.

### Những số liệu nên giám sát

- **Claim-winner / duplicate-hit / fingerprint-mismatch rate** theo loại thao tác.
- **p95/p99 latency** của câu insert claim và thời gian chờ unique constraint.
- **Operation stuck age** ở `PENDING/PROCESSING`; số lần recovery/takeover.
- **Outbox lag, redelivery và DLQ depth**.
- **Duplicate business effect** (mục tiêu bằng 0) và PSP reconciliation lag.
- **Retry attempts per intent**, 409/422/429 và failure rate theo tenant/tier; tránh metric label chứa key thô.

## 11. Bài tập ngắn: ba request đến cùng lúc

Một API tạo phiếu hoàn tiền có scope `(tenant, REFUND, key)`. Trong cùng một thời điểm:

- **A:** tenant T1, key K7, payload `{"paymentId":"P1","amount":100000}`.
- **B:** tenant T1, key K7, **cùng payload A**.
- **C:** tenant T1, key K7, payload `{"paymentId":"P1","amount":200000}`.

Giả sử cả ba request đã được xác thực, và API chọn chính sách **202 + Location** cho request trùng đang xử lý, **422** khi fingerprint không khớp.

**Yêu cầu:** Hãy xác định số claim, số refund intent, status có thể trả, rủi ro khi chỉ khóa trong RAM và điều cần test khi payment provider trả timeout.

### Đáp án gợi ý

Vì **unique constraint chọn đúng một request thắng** và fingerprint của C khác A/B, có hai khả năng:

1. **A hoặc B thắng:** Một refund intent có amount=100000; request còn lại cùng payload nhận **202 cùng operationId**; **C nhận 422**.
2. **C thắng:** Một refund intent có amount=200000; **A và B đều nhận 422** vì dùng lại key với fingerprint khác.

**Không được khẳng định A chắc chắn thắng** chỉ vì được viết đầu tiên trong đề: khi thực thi đồng thời, winner phụ thuộc thứ tự transaction chiếm unique key. Trong mọi trường hợp, nếu contract chống trùng hoạt động, **chỉ có một claim và một refund intent được tiếp nhận**, không phải hai hoặc ba.

`synchronized` trong một JVM **không bảo vệ hai pod khác nhau**. Redis `SETNX` với TTL có thể hỗ trợ điều phối, nhưng nếu TTL hết khi một worker còn chạy, owner mới có thể xử lý lại; cần business uniqueness, fencing/recovery và provider idempotency. Khi PSP trả timeout, **tra cứu kết quả theo reference ổn định**, không gọi refund mới với ID mới chỉ vì thiếu response.

## 12. Checklist triển khai

- [ ] `Idempotency-Key` được ràng buộc với **tenant/principal, operation kind và fingerprint** đã chuẩn hóa.
- [ ] **Atomic claim** và unique constraint được thực hiện **trước side effect**.
- [ ] **Claim, business intent và outbox** cùng một transaction ngắn; không giữ DB transaction khi gọi PSP.
- [ ] Request trùng in-flight trả **cùng operationId** hoặc lỗi in-progress theo contract, không chạy thêm.
- [ ] Cùng key nhưng payload khác bị từ chối **trước khi tạo side effect**.
- [ ] Không nhầm **202 Accepted** với nghiệp vụ đã hoàn tất.
- [ ] Có `GET /operations/{id}` hoặc kênh tra cứu kết quả cho trường hợp response thất lạc.
- [ ] Worker/broker chịu được redelivery, lease takeover và event đến không đúng thứ tự.
- [ ] Downstream có stable idempotency reference hoặc quy trình reconciliation đáng tin.
- [ ] Không xóa claim `PROCESSING` chỉ vì TTL; retention phù hợp vòng đời và rủi ro nghiệp vụ.
- [ ] Kiểm thử cạnh tranh trên **nhiều transaction/instance**, crash trước/sau commit và timeout sau provider success.
- [ ] Quan sát được **duplicate business effects**, không chỉ số response 202 hoặc cache hit.

**Kết luận:** Hai request cùng khóa đến đồng thời là bài toán **quyền thực thi nguyên tử**, không phải bài toán “so hai response có giống nhau không”. Thiết kế hiệu quả là **claim bằng unique constraint**, ghi một **business intent bền vững**, trả lại cùng **operationId** cho request trùng, rồi bảo vệ các side effect ở worker và downstream bằng dedupe/đối soát. Nếu không xác định được kết quả cuối, trạng thái phải là **chưa rõ và có thể tra cứu**, không tự tạo một giao dịch khác.

### Tài liệu tham khảo

- **RFC 9110 — HTTP Semantics:** idempotent methods, 202 Accepted, 409 Conflict và semantics của retry.
- **RFC 9457 — Problem Details for HTTP APIs:** thông báo lỗi fingerprint mismatch có cấu trúc.
- **OpenAPI Specification 3.1:** header, response, trạng thái operation và các mã lỗi.
- **PostgreSQL Documentation — INSERT ... ON CONFLICT và Transaction Isolation:** atomic conflict resolution, READ COMMITTED.
- **Spring Framework — Transaction Management:** `@Transactional`, transaction boundaries và database isolation.

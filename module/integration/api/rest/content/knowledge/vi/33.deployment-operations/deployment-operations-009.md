# Migration dữ liệu theo thứ tự mở rộng rồi thu hẹp

## 1. Bối cảnh và mục tiêu

Trong module **INTEGRATION_API_REST**, một REST API phải duy trì tính đúng đắn của resource, URI, phương thức, status HTTP, hợp đồng dữ liệu, cache, idempotency và phân quyền **cả khi đang triển khai phiên bản mới**. Migration schema DB chạy thành công chưa đồng nghĩa các ứng dụng cũ, workers và clients cũ vẫn hoạt động.

Xét Order API viết bằng **Java 17+, Spring Boot 3 và PostgreSQL**, gồm **POST /api/v1/orders**, **GET /api/v1/orders/{id}**, **PATCH /api/v1/orders/{id}**, cùng các job/export và event consumers. Bảng orders đang có cột **total_vnd INTEGER NOT NULL** biểu diễn số tiền bằng VND. Thiết kế mới muốn dùng **amount_minor BIGINT** và **currency VARCHAR(3)** để chuẩn hóa money model.

Với các đơn VND cũ, dữ liệu có thể ánh xạ **amount_minor = total_vnd, currency = 'VND'** vì đồng VND có zero decimal places theo ISO 4217. Nhưng khi code cũ còn tồn tại, **không được bật ghi các currency khác VND**: code cũ không biết biểu diễn số tiền mới và rollback có thể làm sai nghiệp vụ.

Đổi tên cột ngay là sai trong rolling deployment:

~~~sql
-- KHÔNG AN TOÀN khi còn instance cũ.
ALTER TABLE orders RENAME COLUMN total_vnd TO amount_minor;
~~~

Các instances A0 cũ đang query **total_vnd** sẽ lỗi; một rollback chỉ đổi Docker image không thể khôi phục schema đã mất.

**Sau bài học, bạn có thể:**

1. Giải thích **Expand → Migrate → Contract** và đường đi của các phiên bản code/schema.
2. Chọn thay đổi DB và REST API tương thích với **old/new readers, writers và consumers**.
3. Viết dual-write, backfill theo batch, reconcile và read cutover không làm mất dữ liệu.
4. Dùng Spring/Java, PostgreSQL, migration tools và deployment flags đúng trách nhiệm.
5. Kiểm tiền, tenant/ACL, optimistic locking, ETag, idempotency và contract HTTP trong migration.
6. Lập rollback window, go/no-go, test matrix, observability và runbook vận hành.

**Nguyên tắc:** chỉ xóa cấu trúc cũ khi không còn actor nào phụ thuộc và bằng chứng dữ liệu đã đồng bộ đầy đủ; không nhầm **schema compatible** với **public API compatible**.

## 2. Ba pha Expand, Migrate, Contract

~~~mermaid
flowchart LR
 A[S0: total_vnd] --> B[EXPAND: thêm amount_minor và currency]
 B --> C[Code A1: đọc cũ, dual-write]
 C --> D[MIGRATE: backfill và reconcile]
 D --> E[Code A2: chuyển nguồn đọc có flag]
 E --> F[Retire old apps, workers, clients]
 F --> G[CONTRACT: constraints và bỏ total_vnd]
~~~

| Pha | Việc được phép | Việc chưa được làm |
| --- | --- | --- |
| **Expand** | Thêm cột nullable, index cần thiết, code tương thích | Không drop/rename cột cũ, không thêm constraint phá old writer |
| **Migrate** | Ghi đồng bộ, backfill lịch sử, kiểm tính khớp, switch readers | Không cho reader dùng new fields chưa đầy đủ/đồng bộ |
| **Contract** | Bỏ legacy code, siết constraints, xóa old column sau grace period | Không contract khi còn old worker, rollback image hoặc event consumer |

**Expand không tự zero-lock.** PostgreSQL có thể lấy table/metadata locks cho DDL. Mức ảnh hưởng phụ thuộc DB version, default, bảng, locks và workload. Test trên staging gần production, đặt lock timeout phù hợp và đo replication lag trước rollout.

**Contract là điểm rủi ro rollback lớn nhất.** Nếu đã drop cột cũ, rollback bằng binary A0 thường không còn khả thi. Phải ưu tiên forward-fix hoặc restore theo runbook được duyệt; **restore backup không phải rollback tức thời không mất dữ liệu**.

### 2.1. Ma trận tương thích binary × schema

| Binary | S0: chỉ cột cũ | S1: cả cũ+mới | S2: chỉ cột mới |
| --- | --- | --- | --- |
| **A0**: chỉ dùng total_vnd | Hoạt động | Hoạt động nếu nullable mới | Hỏng |
| **A1**: đọc cũ, ghi cũ+mới | Hỏng khi SQL cần cột mới | Hoạt động | Hỏng do còn đọc/ghi cũ |
| **A2**: đọc mới, vẫn dual-write để rollback | Hỏng | Hoạt động khi new data đầy đủ | Có thể hỏng nếu còn ghi cũ |
| **A3**: chỉ dùng cấu trúc mới | Hỏng | Chỉ ghi được trên S1 sau khi bỏ NOT NULL của total_vnd; mọi old reader đã ngừng | Hoạt động |

Do đó phải **expand S1 trước khi deploy A1**. Không đưa A2 vào đọc new fields trước khi đã xử lý mọi old writer. Trong rolling deployment, database, pods, queue workers, cron jobs, Kafka consumers và rollback image có thể cùng sử dụng schema.

### 2.2. DB, REST API và event schema là ba hợp đồng riêng

- DB có thể thêm cột mới mà **GET /orders/{id}** vẫn trả **totalVnd** cho client cũ.
- REST response có thể thêm object **amount: {minor, currency}** nhưng **không xóa totalVnd** cho đến khi xác minh client support.
- Event/outbox có thể thêm **amount**; consumer cũ vẫn cần **totalVnd** hoặc một event version cũ.
- Search index, CSV exports, BI reports, cache và webhook cũng là consumers cần được thống kê.

Một client strict JSON schema có thể bị phá bởi field mới **dù đây là additive change**. Dùng consumer contract tests/OpenAPI compatibility checks, không giả định mọi client đều bỏ qua unknown fields.

## 3. Chốt bất biến tiền và quyền trước khi chuyển dữ liệu

Bất biến cho giai đoạn VND-only:

- **total_vnd >= 0** và phù hợp range INTEGER cũ; **amount_minor** phải bằng total_vnd và **currency='VND'**.
- Giá/tiền đến từ pricing domain đáng tin; client không thể tự gửi một số tiền khác để tạo order.
- **tenant_id, owner_id, resource ACL** không đổi; không đọc/ghi order tenant khác trong migration.
- **Một Idempotency-Key** gắn tenant + actor + operation + fingerprint không tạo hai đơn hoặc charge hai lần khi retry.
- **Version/ETag** phản ánh business resource state; backfill cột nội bộ không tự làm mọi If-Match của client trở nên stale nếu public representation chưa đổi.
- Trong khi old code vẫn hoạt động, không ghi đa tiền tệ hoặc giá trị vượt range INTEGER; đó là **feature rollout khác** sau contract.
- Dữ liệu null/âm/outliers phải được điều tra; không mặc định chuyển null thành 0 hoặc đoán currency.

Ví dụ schema ban đầu:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    owner_id UUID NOT NULL,
    total_vnd INTEGER NOT NULL,
    status VARCHAR(24) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL
);
~~~

Response cũ:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v7"
Cache-Control: private, no-store

{"id":"11111111-1111-4111-8111-111111111111",
 "totalVnd":2590000,"status":"CREATED"}
~~~

Một migration đúng phải bảo vệ **cả giá trị DB và representation REST client đang phụ thuộc**.

## 4. Expand schema: thêm nhưng chưa ràng buộc quá sớm

~~~sql
-- Flyway V100__expand_order_money.sql
ALTER TABLE orders
    ADD COLUMN amount_minor BIGINT,
    ADD COLUMN currency VARCHAR(3);
~~~

**Chưa đặt NOT NULL** vì A0 vẫn INSERT chỉ cột cũ. Chưa drop/rename total_vnd. Tránh default giá 0 giả; nếu đặt default currency='VND' vẫn phải kiểm tất cả dữ liệu nghiệp vụ, không coi default thay logic migration.

Điều kiện vận hành:

1. Kiểm schema/data profiling, row count và những giá trị bất thường trước khi thao tác.
2. Dry-run trên staging có kích thước dữ liệu, index, write rate gần production; đo DDL lock.
3. Có lock timeout và retry **có giám sát**, không để process deploy chờ khóa vô hạn.
4. Chạy migration **trước** binary A1 và xác nhận mọi DB read replicas/CDC phù hợp.
5. Không chỉnh sửa file versioned Flyway đã apply vì sẽ gây checksum mismatch; tạo version migration kế tiếp khi sửa.
6. Chỉ tạo index nếu có truy vấn thực sự dùng; CREATE INDEX CONCURRENTLY của PostgreSQL **không chạy trong transaction block**.

~~~sql
-- Chỉ khi query theo currency/tenant thực sự có lợi từ index.
-- Với Flyway, cấu hình executeInTransaction=false cho lệnh này.
CREATE INDEX CONCURRENTLY idx_orders_tenant_currency
    ON orders (tenant_id, currency);
~~~

Index concurrently thất bại có thể để lại invalid index; cần runbook kiểm catalog index, cleanup/retry. Không dùng lệnh này vô điều kiện trên mọi DB vendor.

## 5. Deploy A1: đọc cũ, dual-write nguyên tử

Sau expand, **A1** vẫn đọc total_vnd như A0 nhưng ghi đồng thời ba cột. Điều này cho phép các old pods và new pods cùng hoạt động trong rollout.

~~~sql
INSERT INTO orders (
    id, tenant_id, owner_id,
    total_vnd, amount_minor, currency,
    status, version, created_at
) VALUES (
    :id, :trustedTenant, :trustedOwner,
    :amountVnd, CAST(:amountVnd AS BIGINT), 'VND',
    'CREATED', 0, now()
);
~~~

Khi cập nhật số tiền hợp lệ, dùng một UPDATE có transaction và optimistic lock:

~~~sql
UPDATE orders
   SET total_vnd = :amountVnd,
       amount_minor = CAST(:amountVnd AS BIGINT),
       currency = 'VND',
       version = version + 1
 WHERE id = :id
   AND tenant_id = :trustedTenant
   AND version = :expectedVersion
   -- Thêm owner/ACL/action/state checks của policy thực.
RETURNING id, version;
~~~

**Tenant predicate không thay object ACL.** Service phải kiểm authorization theo order và policy, trong khi UPDATE có điều kiện bảo vệ race/version. Nếu row count=0, phân loại 404/403/412 theo phạm vi caller được biết, không query toàn DB để lộ order khác tenant.

### 5.1. Ví dụ Spring transaction cho dual-write

~~~java
public record MoneyVnd(long amountMinor) {
    public MoneyVnd {
        if (amountMinor < 0 || amountMinor > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(
                "Outside legacy VND range");
        }
    }
}

@Service
public class OrderWriteService {
    private final NamedParameterJdbcTemplate jdbc;
    private final OrderPolicy policy;

    public OrderWriteService(
            NamedParameterJdbcTemplate jdbc, OrderPolicy policy) {
        this.jdbc = jdbc;
        this.policy = policy;
    }

    @Transactional
    public UUID create(Caller caller, CreateOrder command) {
        policy.requireCreate(caller, command);
        MoneyVnd price = policy.requireCurrentPrice(command);
        UUID id = UUID.randomUUID();
        var params = new MapSqlParameterSource()
            .addValue("id", id)
            .addValue("tenant", caller.tenantId())
            .addValue("owner", caller.userId())
            .addValue("legacy", Math.toIntExact(price.amountMinor()))
            .addValue("minor", price.amountMinor());
        jdbc.update("""
            INSERT INTO orders
              (id, tenant_id, owner_id, total_vnd,
               amount_minor, currency, status, version, created_at)
            VALUES
              (:id, :tenant, :owner, :legacy,
               :minor, 'VND', 'CREATED', 0, now())
            """, params);
        return id;
    }
}
~~~

**Caller/CreateOrder/OrderPolicy là domain abstractions cần triển khai.** Transaction này chỉ đồng bộ **các cột trong một DB**, không tự tạo distributed transaction giữa Inventory/Payment/DB. Việc POST retry vẫn cần idempotency store, một business operation ID và downstream dedup.

### 5.2. Điều gì xảy ra nếu A0 còn ghi?

A0 sẽ tạo/cập nhật row chỉ có **total_vnd**; new fields có thể null hoặc lệch. **Không chuyển new readers sang đọc amount_minor khi A0 còn ghi mà không có cơ chế đồng bộ bảo đảm.**

Các lựa chọn:

| Biện pháp | Lợi ích | Rủi ro |
| --- | --- | --- |
| Đợi A0 và toàn bộ old workers ngừng, sau đó backfill/reconcile | Đơn giản, dễ xác minh | Phải kiểm deployment, queue, cron, retry |
| Trigger DB tự đồng bộ old write | Bao phủ A0 trong transition | Logic ẩn, locking, overhead, recursion |
| CDC/outbox dual pipeline | Phù hợp khi thay bảng hoặc service khác | Lag, ordering, duplicate events |
| Dual-read fallback tạm thời | Giảm lỗi khi new fields chưa đủ | Có thể che dữ liệu lệch và kéo dài migration |

Với ví dụ một bảng, chọn **đợi A0 drain + A1 dual-write + reconciliation** là phương án dễ kiểm soát. Nếu vẫn cần A0 chạy lâu, phải đầu tư trigger/CDC có test nhất quán thay vì kỳ vọng một lần backfill chữa mọi write.

## 6. Backfill: theo batch, idempotent và không giữ lock dài

Một UPDATE duy nhất trên hàng triệu rows có thể tăng WAL, row locks, replication lag, bloat, vacuum pressure và thời gian phục hồi. Backfill nên có batch size, rate cap, transaction ngắn, checkpoint, pause/resume, retries và audit theo migration ID.

~~~sql
-- PostgreSQL: mỗi batch chạy trong một transaction riêng.
WITH target AS (
    SELECT id
      FROM orders
     WHERE amount_minor IS NULL OR currency IS NULL
     ORDER BY id
     LIMIT :batchSize
     FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
   SET amount_minor = CAST(o.total_vnd AS BIGINT),
       currency = 'VND'
  FROM target t
 WHERE o.id = t.id
RETURNING o.id;
~~~

**FOR UPDATE SKIP LOCKED** tránh chờ những rows đang bị khóa; một batch không đảm bảo đã thấy tất cả rows. Worker lặp đến khi số rows cần backfill bằng 0, có thể phân nhiều workers theo policy. Commit từng batch, không giữ transaction qua network calls.

Không dùng **OFFSET tăng dần** cho tập rows đang co lại sau UPDATE: có thể bỏ sót rows khi những rows đầu không còn thỏa WHERE. Dùng predicate **needs_backfill** + batch locking hoặc keyset checkpoint với reconciliation bổ sung.

SQL trên chỉ sửa null; **không sửa amount_minor đã có nhưng khác total_vnd** do A0 cập nhật sau batch trước. Do đó **count NULL = 0 chưa đủ để chuyển nguồn đọc**. Sau khi old writers thực sự ngừng, phải chạy reconciliation so giá trị, sửa dưới transaction có kiểm soát và xác nhận không còn divergence.

### 6.1. Backfill không được tăng business version tùy tiện

Nếu chỉ ghi thêm cột kỹ thuật mà REST representation chưa đổi, việc tự tăng version trên hàng triệu rows có thể khiến tất cả client gửi **If-Match** với ETag cũ nhận 412. Nên tách version nghiệp vụ và migration metadata; nếu trigger/@Version vẫn tăng version, cần thiết kế/test tác động lên optimistic locking và cache trước khi chạy.

### 6.2. Retry, audit và lỗi mapping

Nếu worker chết sau commit trước khi checkpoint được lưu, chạy lại phép gán **new=old** phải an toàn. Không nhân đôi amount hay tạo order mới. Đánh dấu lỗi dữ liệu bất thường để xử lý, không tự bỏ qua. Metrics gồm rows/sec, lag, mismatch, retries, lock wait, WAL/replication pressure và elapsed time; log không chứa PII/số thẻ/token. Actor cho thay đổi schema/internal fields là **system migration**, không giả user cuối.

## 7. Reconciliation: chứng minh dữ liệu mới khớp trước khi đọc

Backfill chạy hết các rows NULL chưa đủ nếu old writer có thể cập nhật **total_vnd** sau khi một row đã được backfill. Trước read cutover, xác minh mọi old-only writer đã drain, cả **web pods, scheduled workers, delayed jobs và CDC consumers**.

Các truy vấn PostgreSQL minh họa:

~~~sql
-- Rows còn thiếu trường mới.
SELECT count(*) AS incomplete_count
FROM orders
WHERE amount_minor IS NULL OR currency IS NULL;

-- Rows khác giá trị VND authoritative cũ.
SELECT count(*) AS mismatch_count
FROM orders
WHERE amount_minor IS DISTINCT FROM CAST(total_vnd AS BIGINT)
   OR currency IS DISTINCT FROM 'VND';

SELECT count(*) AS invalid_amount_count
FROM orders
WHERE total_vnd < 0 OR amount_minor < 0;
~~~

**IS DISTINCT FROM** khác toán tử không bằng thông thường ở chỗ xử lý đúng cả NULL. Với bảng lớn, full count/scan có thể tốn IO: chạy incremental reconciliation theo keyset, canary sampling để phát hiện sớm, rồi full verification ở cửa sổ kiểm soát. **Không báo 100% nếu chỉ kiểm sample.**

Nếu lệch và **total_vnd còn là nguồn sự thật**, có thể sửa theo batch, lock rows ngắn:

~~~sql
WITH target AS (
    SELECT id
    FROM orders
    WHERE amount_minor IS DISTINCT FROM CAST(total_vnd AS BIGINT)
       OR currency IS DISTINCT FROM 'VND'
    ORDER BY id
    LIMIT :batchSize
    FOR UPDATE SKIP LOCKED
)
UPDATE orders AS o
SET amount_minor = CAST(o.total_vnd AS BIGINT),
    currency = 'VND'
FROM target t
WHERE o.id = t.id
RETURNING o.id;
~~~

**Không chạy chiều old → new này sau khi amount_minor đã trở thành authoritative source**, vì có thể ghi đè tiền mới bằng giá trị cũ. Muốn backfill/reconcile, phải định nghĩa source of truth **theo từng pha** và xác minh không có writers cạnh tranh ngoài mô hình.

Gate để chuyển nguồn đọc: old-only writers và consumers bằng 0; backfill NULL bằng 0; mismatches bằng 0 trên population theo yêu cầu; new writes đồng bộ; replication lag/lock/error và latency trong ngưỡng; rollback path còn dùng được.

### 7.1. Shadow-read trước khi read-new

Ở A2 có thể đọc cả hai định dạng trong background và so sánh, nhưng **trả authoritative old value** cho client cho đến khi gate PASS. Ghi metric mismatch theo route/tenant group chứ không log tên khách hàng, giá tiền hay PII. Nếu có mismatch, giữ flag readNew OFF, phân tích điều kiện đua và reconcile; không tự đổi nguồn theo từng request để che lỗi.

Không làm lazy backfill ngay trong GET handler: GET được thiết kế safe; một read storm không được biến thành hàng nghìn UPDATE không kiểm soát. Migration dữ liệu nên do **job rate-limited, checkpointed và audit được** thực hiện.

## 8. Chuyển nguồn đọc theo feature flag

~~~mermaid
sequenceDiagram
  participant C as REST client
  participant A as Service A2
  participant D as Database
  participant M as Migration metrics
  C->>A: GET /orders/{id}
  A->>D: Read authorized row, old + new fields
  D-->>A: Data
  A->>M: Compare total_vnd and amount_minor
  A-->>C: Compatible response from old source
  Note over A: After reconciliation and rollout gates
  C->>A: GET /orders/{id}
  A->>D: Read authorized new money fields
  D-->>A: amount_minor + currency
  A-->>C: Contract-preserving response
~~~

Rollout đề xuất:

1. Deploy A2 với **readNew flag OFF**; dual-write vẫn hoạt động.
2. Chạy **shadow comparison** trên canary và thống kê mismatch/latency.
3. Khi có sign-off, bật readNew theo tenant/canary có kiểm soát.
4. Kiểm HTTP status, tiền/currency, authorization, cache, p95, ETag, Idempotency-Key.
5. Mở rộng traffic từ canary sang toàn bộ khi dữ liệu và SLO ổn định.
6. Duy trì dual-write trong **rollback window** trước khi bỏ legacy readers/writers.

Feature flag không thể khôi phục schema đã drop, không làm dữ liệu tự đồng bộ, và không biến client cũ thành client mới. Ghi owner, thời điểm bật, scope, kill switch và tiêu chí rollback.

## 9. REST contract: chuyển DB không đồng nghĩa thay JSON ngay

Trong pha quá độ, API v1 có thể tiếp tục trả **totalVnd** trong khi DB dùng new fields. Chỉ thêm **amount** nếu contract/consumer test cho phép:

~~~http
GET /api/v1/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-repr-v8"
Cache-Control: private, no-store

{
  "id":"11111111-1111-4111-8111-111111111111",
  "totalVnd":2590000,
  "amount":{"minor":2590000,"currency":"VND"},
  "status":"CREATED"
}
~~~

**Additive response chưa chắc backward-compatible** nếu old SDK/schema validator từ chối unknown properties. Nếu không chứng minh được client tolerate, giữ JSON v1 y nguyên và phát hành **/api/v2/orders/{id}** hoặc một media type version rõ. V1 có thể suy ra totalVnd từ amount_minor **chỉ khi currency là VND và value nằm trong range legacy**.

| HTTP operation | Bất biến trong migration |
| --- | --- |
| **POST /orders** | 201 + Location khi đã commit; retry cùng key không tạo duplicate |
| **GET /orders/{id}** | 200 với selected representation đúng; không lộ tenant khác |
| **PATCH /orders/{id}** | If-Match/CAS và 412 khi stale; validate tiền/currency |
| **GET collection** | limit/cursor/filter/sort đều tenant/ACL scoped |
| **Authn/authz** | 401/403/404 đúng policy; không fallback dữ liệu bị cấm |
| **ETag / If-None-Match** | 304 chỉ sau kiểm quyền và validator đúng representation |
| **Errors** | Problem Details RFC 9457, không lộ DB schema/host/stack |
| **Cache** | Không dùng cache JSON v1/v2/tenant này cho tenant khác |

**ETag** là validator của selected representation: thêm amount field có thể đổi bytes và strong ETag. Ngược lại, backfill hai cột nội bộ mà JSON không đổi không nhất thiết phải tăng business version và làm stale mọi If-Match. Phân biệt **migration metadata, business version và representation validator**.

**Idempotency:** nếu client cũ gửi totalVnd và client mới gửi amount, server phải có fingerprint policy rõ: cùng key + cùng ý nghĩa business replay ra cùng outcome; cùng key + nội dung business khác phải conflict. Fingerprint phải scoped theo tenant, actor, method/resource và TTL; không tạo order mới do chỉ thay tên trường. Không cho client tự gửi amount không qua pricing authorization.

### 9.1. Event contract và worker cũ

Một outbox event có thể được consumer cũ xử lý sau khi DB đã migrate. Trong giai đoạn đó, event có thể giữ **totalVnd** và thêm amount, hoặc phát event version rõ với consumer compatibility tests. Không xóa topic/field cũ khi DLQ/retries/outstanding messages vẫn phụ thuộc. Nếu consumer nhận sự kiện at-least-once, phải dedup và bảo toàn ordering theo aggregate/business key.

## 10. Contract: constraints và drop sau gate hoàn tất

Sau khi **backfill toàn bộ, old writers ngừng và không còn rows sai**, có thể tăng ràng buộc. Với PostgreSQL:

~~~sql
-- Lúc này mọi insert/update mới phải có fields hợp lệ.
ALTER TABLE orders
ADD CONSTRAINT orders_new_money_valid
CHECK (
    amount_minor IS NOT NULL
    AND currency IS NOT NULL
    AND amount_minor >= 0
) NOT VALID;
~~~

**NOT VALID** bỏ qua bước scan lịch sử lúc thêm constraint, **nhưng vẫn enforce trên rows được INSERT/UPDATE sau đó**. Nếu còn old writer hoặc rows lịch sử thiếu new fields được UPDATE, operations có thể thất bại. Không thêm constraint này quá sớm.

~~~sql
ALTER TABLE orders
    VALIDATE CONSTRAINT orders_new_money_valid;
~~~

Sau đó nếu cần, dùng **ALTER COLUMN SET NOT NULL** cho amount_minor và currency, cân nhắc phiên bản PostgreSQL, table locks, duration và replication. Test trên staging; không mặc định đây là metadata-only.

**Trước khi deploy A3 chỉ ghi cột mới trên schema S1**, phải xử lý ràng buộc legacy: cột **total_vnd INTEGER NOT NULL** ban đầu sẽ từ chối INSERT của A3 nếu A3 không ghi giá trị cũ. Sau khi **hết rollback window yêu cầu A0/A1/A2**, không còn old reader và đã xác nhận tất cả new writers hoạt động, có thể thực hiện migration trung gian:

~~~sql
-- Chỉ sau khi không còn old readers và được duyệt mất rollback cũ.
ALTER TABLE orders ALTER COLUMN total_vnd DROP NOT NULL;
~~~

Kể từ khi A3 ghi rows mới với **total_vnd = NULL**, rollback về A2 đọc cột cũ không còn an toàn chỉ bằng đổi image, dù chưa DROP COLUMN. Cần forward-fix hoặc kế hoạch reverse-backfill/compatibility được kiểm chứng nếu muốn quay lại. Trình tự khác cũng có thể giữ A3 dual-write đến tận lúc DROP, rồi mới phát hành binary new-only; không được tự ý bỏ qua ràng buộc NOT NULL.

Chỉ khi **code A3, workers, consumers, rollback plan** không dùng total_vnd, mới contract:

~~~sql
ALTER TABLE orders DROP COLUMN total_vnd;
~~~

Cần kiểm cả **views, materialized views, triggers, stored procedures, BI exports, CDC connectors, cached DTOs và jobs**. Từ thời điểm này, A0 không còn chạy được. Việc bật multi-currency thuộc release riêng sau khi legacy code đã hết; không nhồi thêm thay đổi nghiệp vụ vào cutover schema.

## 11. Flyway và Spring Boot: ai chạy migration?

| Giai đoạn | Mục đích |
| --- | --- |
| **V100 expand** | Add two nullable columns, giữ schema cũ |
| **Deploy A1** | Read-old/dual-write |
| **Backfill job** | Batch+checkpoint+reconciliation, old writer drained |
| **Deploy A2** | Shadow compare/readNew flag |
| **V101 validate constraints** | Sau dữ liệu sạch, writer đủ fields |
| **V101b legacy compatibility boundary** | Hết rollback window/old readers; bỏ NOT NULL ở total_vnd trước new-only writes |
| **Deploy A3** | New-only readers/writers, adapter v1 nếu cần; rollback A2 không còn đơn giản |
| **V102 contract** | Drop old column sau sign-off |

**Flyway versioned migrations** phù hợp với DDL được quản lý bằng commit/version. Đừng sửa migration đã apply; tạo migration mới để sửa. Backfill lớn thường nên là **job riêng có rate limit/pause/resume**, tránh giữ startup pod chờ một migration transaction nhiều giờ.

Nếu Flyway chạy khi app startup, bảo đảm DB migration **có một owner/lock đúng** và schema expand được apply trước khi A1 pods ready. Tránh để nhiều pods đồng thời chạy backfill lớn. PostgreSQL **CREATE INDEX CONCURRENTLY** phải thực hiện ngoài transaction block và có cấu hình migration tool phù hợp.

**Readiness:** A1 có thể ready với columns mới nullable; A2 chỉ route readNew khi data gate đạt; A3 không được chạy khi schema còn thiếu. Workers/cron cũng cần cùng compatibility management, không chỉ web pods.

## 12. Rollback theo giai đoạn và điểm không thể đảo ngược bằng code

| Điểm lỗi | Cách xử lý khả dĩ | Giới hạn |
| --- | --- | --- |
| DDL expand thất bại | Giữ A0, sửa DDL/retry an toàn | Không tự drop bảng/cột đã chứa writes |
| A1 dual-write lỗi | Rollback A0 khi S1 còn đủ | Không bật new currency |
| Backfill quá tải/sai | Pause, xác định authoritative old, reconcile | Không đảo tiền tùy ý |
| A2 read-new mismatch | Tắt readNew, quay read-old | Cần sửa nguồn lệch trước lần switch tiếp |
| Sau NOT NULL constraint | Rollback chỉ tới binary vẫn ghi đủ new fields | A0 thường không compatible |
| Sau khi bỏ legacy NOT NULL và A3 ghi new-only | Forward-fix hoặc reverse-backfill có kiểm chứng | Rows mới có total_vnd=NULL; không thể chỉ đổi image về A2 |
| Sau DROP total_vnd | Forward-fix hoặc restore có runbook | Chỉ rollback Docker image không đủ |

**Rollback window** nghĩa là giữ được **schema cũ, semantics VND-only, event/consumer compatibility, idempotency và dữ liệu legacy** trong khoảng thời gian được duyệt. Một Docker image cũ không phải rollback nếu cột đã mất.

**Backup/PITR** không phải nút undo tức thời: restore tới trước migration có thể làm mất orders vừa commit. Cần RPO/RTO, plan replay CDC/outbox và đối soát payment/charges. Với schema đã contract, **roll-forward fix** đôi khi an toàn hơn khôi phục cột cũ.

## 13. Runbook triển khai: rõ owner, gate và tín hiệu dừng

Một thay đổi schema có rollback khó cần **runbook có checkpoints**, không dựa vào trí nhớ người trực vận hành. Ví dụ lộ trình cho Order API:

| Mốc | Hành động | Gate để tiếp tục |
| --- | --- | --- |
| **T0 – Baseline** | Snapshot schema/metrics/backup readiness, kiểm tiền và row count | Không có dữ liệu nguồn vi phạm policy, đủ quyền vận hành |
| **T1 – Expand** | Apply V100 nullable columns; A0 vẫn chạy | DDL xong, app cũ không 5xx, DB lock/replication bình thường |
| **T2 – Compatible writers** | Deploy A1 canary rồi toàn traffic | Mọi new writes đồng bộ, không tăng conflict/latency |
| **T3 – Drain A0** | Loại old pods, cron, workers, in-flight jobs | Không còn old-only writer thực tế |
| **T4 – Backfill** | Batch copy, pause khi lag/lock vượt ngưỡng | Backlog về 0, reconciliation mismatch=0 |
| **T5 – Read switch** | A2 shadow compare, canary readNew rồi toàn phần | Money chính xác, REST response/ETag/ACL và SLO đúng |
| **T6 – Compatibility window** | Tiếp tục dual-write, theo dõi rollback readiness | Không còn downstream dùng legacy; hết rollback window |
| **T7 – Contract** | Constraint/validate; A3 new-only; drop cũ sau sign-off | Test A3 và toàn downstream; rollback dạng forward-fix sẵn |

Mốc trên là **thứ tự logic**, không phải thời lượng được đảm bảo. Một số hệ thống cần giữ dual-write nhiều ngày trước T7; nếu DB traffic quá cao, backfill phải chậm lại. **Không xóa schema cũ chỉ vì dashboard có một phút không lỗi.**

### 13.1. Abort conditions và canary

Một policy vận hành có thể đưa các ngưỡng **minh họa**:

- Bất kỳ sai lệch số tiền thực tế hoặc cross-tenant exposure → **dừng rollout ngay**, bảo toàn dữ liệu và điều tra.
- Mismatch >0 sau reconciliation toàn population của VND legacy → không bật readNew.
- Replication lag, DB lock wait, p95/p99 và 5xx vượt error budget → pause backfill/canary.
- Có old-only writer/consumer hoặc pending DLQ không tương thích → không contract.
- Flyway schema version thiếu/không đồng nhất giữa các DB target → không đẩy A2/A3.
- Không còn rollback/forward-fix plan phù hợp → không sign-off drop column.

Canary nên dùng dữ liệu nhiều tenant/role và cả orders cũ lẫn mới. Kiểm **không chỉ request GET 200** mà còn POST 201, PATCH 412, idempotency, cache, metrics và downstream consumers.

## 14. Observability và audit trong migration

| Thành phần | Metric / log cần có | Ý nghĩa |
| --- | --- | --- |
| **Schema state** | Flyway version, column/constraint/index readiness | Biết binary nào có thể chạy |
| **Writers** | A0/A1/A2/A3 pod/worker versions, old write count | Chứng minh old-only writers đã drain |
| **Backfill** | Rows remaining, rows/sec, batch duration, error/retry | Dự đoán progress, pause khi quá tải |
| **Consistency** | Missing/mismatch count, sampled shadow differences | Quyết định read switch |
| **Database** | Lock wait, deadlocks, WAL/replication lag, pool active | Không làm sập DB vì migrate |
| **HTTP API** | RPS, p95/p99, 4xx/5xx, ETag/412/429 | Hợp đồng REST không bị suy giảm |
| **Domain money** | Invalid currency, negative/overflow, mismatch per segment | Kiểm toàn vẹn tài chính |
| **Idempotency** | Duplicate prevented, key conflicts, pending operations | Không tạo đơn trùng |
| **Security** | Auth denies, tenant mismatch, field exposure incidents | Migration không mở quyền |
| **Downstream** | Event schema errors, DLQ, worker backlog, export mismatches | Consumer không bị bỏ quên |

Labels nên là **release, route template, phase, job ID, tenant cohort** có cardinality hạn chế, không dùng raw orderId hoặc toàn bộ tenant/user IDs làm metric labels. Log audit lưu operation ID, migration version, actor service, outcome và correlation ID nhưng không dump tên/địa chỉ/số thẻ/secret.

**Quan sát và quyết định rollback theo dữ liệu**, không chỉ mức sử dụng CPU hoặc việc container chuyển READY. DB migration có thể không gây 500 nhưng làm sai tiền trên export hoặc event; cần đối soát các đầu ra ấy.

## 15. Kiểm thử tương thích và toàn vẹn trước contract

Dùng **PostgreSQL Testcontainers** với dataset đại diện, Spring Security filter thật, các binary/version test jobs và API contract tests. Môi trường thử phải mô phỏng **mixed-version deployment**, không chỉ khởi động bản mới trên DB sạch.

### 15.1. Ma trận kiểm thử

| ID | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| M01 | A0 chạy trên S1 ngay sau expand | Đọc/ghi total_vnd bình thường |
| M02 | A1 trên S0 | Bị chặn bởi deployment gate, không cho production startup sai schema |
| M03 | A0/A1 đồng thời tạo đơn VND | Không 5xx, new fields nullable trong transition |
| M04 | A1 tạo order | Ba cột đúng, cùng một DB commit |
| M05 | A1 cập nhật amount với If-Match | CAS đúng, 412 khi stale |
| M06 | Old writer cập nhật order sau backfill | Reconciliation phát hiện lệch |
| M07 | Backfill chạy lại cùng batch | Không nhân tiền, không sinh order mới |
| M08 | Worker chết sau commit trước checkpoint | Rerun idempotent |
| M09 | Multiworker SKIP LOCKED | Không deadlock/lost rows; cuối cùng backlog=0 |
| M10 | Dữ liệu âm/null/overflow legacy | Quarantine/report, không tự convert 0 |
| M11 | Backfill và read traffic đồng thời | p95/lock/replica lag trong ngân sách |
| M12 | Shadow compare A2 | Phát hiện mọi mismatch ở fixture |
| M13 | Switch readNew rồi rollback flag | REST result theo business value đúng |
| M14 | POST retry Idempotency-Key | Chỉ một order/charge per operation |
| M15 | Tenant A đọc order tenant B | 403/404, không leak |
| M16 | GET v1 với strict client schema | JSON cũ vẫn hợp lệ hoặc version riêng |
| M17 | GET v2 money object | Currency/range/shape/ETag đúng |
| M18 | List/filter/sort và export CSV | Không thiếu data, không rò tenant |
| M19 | Job/event legacy message sau deploy | Consumer vẫn xử lý hoặc được drain/translate |
| M20 | CHECK NOT VALID khi old writer còn hoạt động | Test chứng minh có thể fail; gate chặn áp sớm |
| M21 | Constraint validation trên dữ liệu lịch sử | Chỉ PASS khi toàn population đúng |
| M22 | Rollback A2 sang A1 khi S1 còn nguyên | Chạy lại an toàn, không mất tiền |
| M23 | Rollback A0 sau DROP | Test chứng minh không compatible, yêu cầu forward-fix |
| M24 | Bật multi-currency trong rollback window | Bị feature gate ngăn |
| M25 | CDC/index/cache lag | Không đọc representation tiền không nhất quán |

**Kiểm riêng dữ liệu đã có và dữ liệu mới được tạo**. Đừng chỉ seed database ở schema S2 hoàn chỉnh rồi kết luận backward compatibility PASS. Test cần đưa **A0-generated rows còn NULL new fields**, chạy job backfill, rồi kiểm A1/A2 và REST clients.

### 15.2. JUnit với JDBC cho dual-write và reconciliation

~~~java
@Test
void compatibleWriteStoresSameVndInOldAndNewColumns() {
    UUID id = orderWriteService.create(
        tenantAReaderWithCreateScope, validOrderCommand());

    Map<String, Object> values = jdbc.queryForMap("""
        SELECT total_vnd, amount_minor, currency
          FROM orders
         WHERE id = ?
           AND tenant_id = ?
        """, id, tenantA);

    long legacy = ((Number) values.get("total_vnd")).longValue();
    long modern = ((Number) values.get("amount_minor")).longValue();
    assertEquals(legacy, modern);
    assertEquals("VND", values.get("currency"));
}
~~~

Đây là test skeleton: **Caller, validOrderCommand, fixtures, JDBC và token/tenant** cần khai báo từ test project. Kiểm HTTP auth/ACL bằng **REST Assured hoặc MockMvc** đi qua SecurityFilterChain, không chỉ gọi thẳng service như đoạn JDBC trên.

~~~java
@Test
void migrationDoesNotExposeOtherTenantOrder() {
    given()
        .spec(api())
        .auth().oauth2(tokenTenantA)
    .when()
        .get("/orders/{id}", orderTenantB)
    .then()
        .statusCode(404); // Chính sách che tồn tại.
}
~~~

**404** là ví dụ privacy policy, không phải bắt buộc mọi hệ thống; có nơi chọn 403 khi caller được biết tài nguyên tồn tại. Điều quan trọng là không lộ order/money hoặc side effect. Với rolling deployment, nên chạy smoke test **thông qua gateway**, vì route/binary cũ và mới có thể không phân bố đồng đều.

### 15.3. Kiểm thử race và rollback thật

- Cho A0 sửa total_vnd khi backfill đang chạy: chứng minh mismatch được phát hiện/reconcile sau khi A0 drain.
- Hai PATCH cùng ETag: chỉ một business mutation commit theo optimistic locking.
- POST timeout sau DB commit: replay cùng Idempotency-Key không tạo order trùng; không suy outcome từ HTTP exception.
- Toggle readNew OFF/ON khi A2 đang chạy: không chuyển tenant/row sang nguồn cũ thiếu đồng bộ.
- Bật constraint trên dữ liệu còn null trong staging: gate phải từ chối, không kéo lỗi này sang production.
- Restore/rollback drill có dataset thay đổi sau snapshot để đo RPO/RTO, tránh kết luận restore mất dữ liệu bằng 0 mà chưa đối soát.

## 16. OpenAPI và security tại thời điểm bỏ field cũ

**Không gỡ totalVnd khỏi schema v1 hoặc xóa route cũ chỉ vì DB đã drop cột.** Hai quyết định khác nhau:

1. **DB contract:** nguồn lưu là amount_minor/currency.
2. **Public API contract:** liệu khách hàng còn hợp đồng totalVnd? Nếu có, adapter v1 vẫn phải trả giá trị chính xác khi currency='VND'. Nếu multi-currency khiến không thể chuyển ngược, yêu cầu version/cutover client trước.

Ví dụ OpenAPI 3.1 cho API v2:

~~~yaml
openapi: 3.1.0
info:
  title: Order API v2
  version: 2.0.0
paths:
  /api/v2/orders/{id}:
    get:
      operationId: getOrderV2
      security: [{ bearerAuth: [] }]
      parameters:
        - name: id
          in: path
          required: true
          schema: { type: string, format: uuid }
      responses:
        '200':
          description: Order với money representation mới
          content:
            application/json:
              schema: { $ref: '#/components/schemas/OrderV2' }
        '401': { description: Chưa xác thực }
        '403': { description: Không có quyền }
        '404': { description: Order không được công bố }
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer }
  schemas:
    Money:
      type: object
      required: [minor, currency]
      properties:
        minor: { type: integer, format: int64, minimum: 0 }
        currency: { type: string, minLength: 3, maxLength: 3 }
    OrderV2:
      type: object
      required: [id, amount, status]
      properties:
        id: { type: string, format: uuid }
        amount: { $ref: '#/components/schemas/Money' }
        status: { type: string }
~~~

OpenAPI chỉ mô tả hợp đồng HTTP, không chứng minh DB copy đúng, resource ACL đúng hay old consumer đã được retire. Kèm test compatibility với real clients và policy deprecation/sunset riêng nếu API v1 thực sự ngừng hoạt động. **Không đột ngột trả 410/404 cho v1 trước khi khách hàng được chuyển đổi theo cam kết.**

## 17. Anti-pattern khi chuyển schema

| Sai lầm | Rủi ro | Cách khắc phục |
| --- | --- | --- |
| Rename/drop trước rolling deploy | A0 SQL hỏng | Expand add columns trước |
| Thêm NOT NULL khi old writers chưa dual-write | INSERT/UPDATE cũ fail | Nullable → backfill → validate → tighten |
| Backfill 1 transaction hàng triệu rows | Lock/WAL/replication lag | Batches có pause/rate limit |
| Dùng OFFSET trên rows cần migration đang co lại | Bỏ sót rows | Predicate batch/keyset + reconcile |
| Chỉ check NULL count | Bỏ sót giá trị lệch | Reconcile bằng equality/invariants |
| New readers trước old writer drain | Dữ liệu thiếu/không nhất quán | Shadow read, cutover gate |
| Read fallback mãi không đo mismatch | Che bug dữ liệu | Metrics và deadline loại fallback |
| Gộp đổi business semantics và schema | Rollback không biểu diễn được tiền | Tách multi-currency rollout |
| Bỏ permission khi backfill | Lộ dữ liệu tenant khác | Trusted tenant, ACL và data ownership |
| Chỉ rollback Docker image sau drop | Binary cũ không còn tương thích | Compatibility window, forward-fix |
| Chạy backfill từ mỗi pod startup | Tranh lock, tăng tải, duplicate work | Single owner/lease hoặc workers có idempotency |
| Tự coi client bỏ qua field mới | Strict SDK có thể fail | Contract test/versioning |
| Không kiểm jobs/events ngoài HTTP | Consumer cũ vẫn hỏng | Inventory dependencies, DLQ drain |
| Test DB S2 sạch thay vì S0→S1→S2 | Không phát hiện đường chuyển lỗi | Test mixed versions và dữ liệu lịch sử |

## 18. Bài tập thực hành: triển khai money migration không downtime

**Bối cảnh:** Order API có 2 triệu orders VND; PostgreSQL, Spring Boot, workers xử lý thanh toán và export, các pod A0 sẽ được rolling update. Hệ thống cần giữ REST v1 trong ít nhất một thời gian chuyển đổi, sau đó mở v2 money object. SLO đọc đơn không được giảm vượt budget đã công bố.

**Yêu cầu (100 điểm):**

1. **Phân tích – 20 điểm:** lập compatibility matrix A0/A1/A2/A3 với S0/S1/S2, xác định authoritative source và rollback window.
2. **SQL – 25 điểm:** viết V100 expand nullable, batch backfill với SKIP LOCKED, reconciliation bằng IS DISTINCT FROM, constraints NOT VALID/VALIDATE và contract drop.
3. **Java/Spring – 25 điểm:** viết dual-write @Transactional, caller/tenant ACL, idempotent POST và If-Match/CAS PATCH; dùng feature flag chuyển read source.
4. **HTTP/OpenAPI – 15 điểm:** đưa ví dụ GET v1 totalVnd, GET v2 amount object, status/error/ETag và giải thích client backward compatibility.
5. **Vận hành/kiểm thử – 15 điểm:** thiết kế cutover gates, metrics, kịch bản race với old writer, lỗi DB, rollback và test cross-tenant.

**Hướng giải:** mở schema trước; A1 đọc old/dual-write; drain A0; backfill từng batch rồi reconcile đến mismatch=0; A2 shadow compare/readNew có guard; giữ cột cũ tới khi rollback/consumers đã retire; mới siết constraints và drop. API v1 có thể được adapter từ new storage nếu VND-only; đừng bật multi-currency khi còn yêu cầu rollback sang legacy.

## 19. Checklist vận hành và tài liệu tham khảo

- [ ] Thống kê đủ app binaries, jobs, cron, event consumers, exports, BI và client contracts.
- [ ] DDL expand thêm nullable fields **trước** khi deploy binary cần field mới.
- [ ] Dual-write nguyên tử trong một DB transaction, nguồn authoritative rõ theo phase.
- [ ] Không bật new reader khi còn old-only writer không có đồng bộ đáng tin.
- [ ] Backfill batch nhỏ, idempotent, checkpoint, rate-limit và pause/resume.
- [ ] Reconcile NULL và mismatches, không chỉ dựa vào phần trăm progress.
- [ ] Siết constraints chỉ sau khi data sạch và old writers hết.
- [ ] Bảo vệ tenant/ACL, price invariants, If-Match, idempotency, JSON/ETag/cache.
- [ ] Có compatibility tests với A0/A1/A2/A3 và old/new REST clients.
- [ ] Có cutover sign-off, rollback window, backup/PITR/forward-fix plan.
- [ ] Contract drop khi không còn dependency cũ, không đồng nhất DB drop với API field removal.
- [ ] Theo dõi DB locks, replication, mismatch, HTTP SLO, event backlog và domain audit.

**Ghi nhớ:** an toàn trong migration không phải là một câu ALTER TABLE chạy thành công; đó là **chuỗi trạng thái trung gian có thể kiểm chứng**, cho phép old/new code đồng tồn tại, dữ liệu lịch sử được chuyển đúng và contract được thu hẹp **chỉ sau khi** không còn ai cần nó.

### Nguồn học tập

- **PostgreSQL Documentation**: ALTER TABLE, locking, CHECK NOT VALID/VALIDATE CONSTRAINT, CREATE INDEX CONCURRENTLY, transaction và FOR UPDATE SKIP LOCKED.
- **Flyway Documentation**: versioned migrations, checksums, transaction handling và deployment ordering.
- **Spring Boot/Spring Data/Spring Transactions**: JDBC, @Transactional, optimistic locking và application lifecycle.
- **RFC 9110 – HTTP Semantics**, **RFC 9457 – Problem Details**, **OpenAPI Specification 3.1**.
- **OWASP API Security Top 10**: BOLA/BOPLA, resource consumption và authentication; tài liệu vận hành về zero-downtime deploy, backfill và data integrity.

# Đồng bộ dữ liệu với cache, tìm kiếm và hệ thống ngoài

## 1. Một lệnh cập nhật, nhiều nơi phải nhìn thấy kết quả

Orders API cho phép nhân viên chuyển đơn hàng từ **CREATED** sang **PAID**. Dữ liệu chính lưu trong PostgreSQL; Redis cache tăng tốc GET; search index hỗ trợ tìm kiếm; một hệ thống hóa đơn bên ngoài cần biết đơn đã thanh toán. Nếu API ghi DB thành công nhưng cập nhật search thất bại, người dùng có thể **GET /orders/{id} thấy PAID** trong khi **GET /orders?status=PAID** chưa tìm thấy đơn. Nếu một notification được gửi hai lần, đối tác có thể tạo hai hóa đơn nếu thiếu kiểm soát trùng.

Đây là vấn đề **nhất quán giữa hệ thống (cross-system consistency)**, không chỉ là “cache cần làm mới”. Mỗi nơi có vòng đời và cơ chế thất bại khác nhau. Một transaction trong DB **không tự bao trùm** Redis, search engine, message broker hoặc HTTP API đối tác.

Bài thuộc chương **Nhất quán nghiệp vụ** của module **INTEGRATION_API_REST**: học thiết kế REST theo resource/URI, phương thức và status HTTP, hợp đồng dữ liệu rõ ràng, phân trang, cache, idempotency, OpenAPI, xác thực/phân quyền, xử lý lỗi và kiểm thử bằng Java/Spring. Trọng tâm ở đây là **đưa thay đổi đã commit tới các read models và hệ thống ngoài một cách phục hồi được**.

**Mục tiêu:** chọn nguồn sự thật, xác định mức độ chậm có thể chấp nhận, triển khai transactional outbox/CDC, consumer idempotent chống sự kiện trùng hoặc đảo thứ tự, thiết kế invalidation cache và indexing tìm kiếm, đối soát với đối tác, đồng thời viết HTTP contract và kiểm thử failure cases.

## 2. Phân biệt dữ liệu gốc, projection và yêu cầu về độ mới

~~~mermaid
flowchart LR
    C["REST client"] --> API["Orders REST API"]
    API --> DB[("Orders DB: nguồn sự thật")]
    DB --> OUT[("Outbox cùng transaction")]
    OUT --> PUB["Publisher / CDC"]
    PUB --> BUS[("Broker: at-least-once")]
    BUS --> CACHE["Cache invalidator"]
    BUS --> SEARCH["Search indexer"]
    BUS --> INT["External integration worker"]
    CACHE --> REDIS[("Redis cache")]
    SEARCH --> IDX[("Search index")]
    INT --> EXT["Hệ thống đối tác"]
~~~

**Nguồn sự thật (source of truth)** là nơi quyết định trạng thái nghiệp vụ đã được chấp nhận. Trong ví dụ: **Orders DB** là bản ghi chuẩn; cache, search và dữ liệu đối tác là các **bản chiếu (projection)/bản sao** phục vụ nhu cầu riêng. Một integration có thể có trạng thái riêng trong DB của đối tác; đừng nhầm “đối tác đã nhận” với “đối tác đã xử lý thành công”.

| Nơi lưu/đọc | Kỳ vọng điển hình | Có thể chậm? | Tác động nếu chậm |
| --- | --- | --- | --- |
| **Primary Orders DB** | Transaction commit, version/concurrency rõ. | Không nên trả thành công khi transaction chưa commit, trừ API async có contract riêng. | Quyết định nghiệp vụ sai. |
| **Redis cache** | Giảm latency, hỗ trợ GET phổ biến. | Có, nếu công bố độ mới phù hợp. | GET có thể trả dữ liệu cũ. |
| **Search index** | Tìm kiếm/filter/full-text nhanh. | Thường eventual consistency. | Kết quả tìm kiếm thiếu hoặc còn bản ghi đã xóa. |
| **External system** | Nhận thông tin, thực hiện quy trình riêng. | Thường bất đồng bộ/phụ thuộc mạng. | Trễ hóa đơn, notification, fulfillment. |

**Không có một mức consistency đúng cho mọi API.** Chọn mức độ từ yêu cầu:

- **Strong/read-your-write tại API cốt lõi:** sau POST/PATCH thành công, GET trực tiếp cùng resource phải thấy trạng thái đã commit hoặc có cơ chế read consistency rõ ràng. Nếu đọc từ replica/cache, phải thiết kế để không vi phạm cam kết.
- **Eventual consistency cho tìm kiếm:** cho phép kết quả trễ vài giây nếu UI công bố/thiết kế phù hợp; những thao tác quan trọng phải kiểm lại resource gốc.
- **External workflow:** chấp nhận xử lý kéo dài và retries; cần trạng thái tích hợp, deadline và đối soát.

Định nghĩa **SLO độ trễ projection** (ví dụ “99% events được phản ánh trong search trong 10 giây”) khác với bảo đảm “luôn đúng ngay”. SLO là mục tiêu quan sát vận hành, **không phải thuộc tính cơ chế Kafka/Redis**.

### 2.1. Phân biệt ba thời điểm

| Thời điểm | Sự kiện | Ý nghĩa |
| --- | --- | --- |
| **T1** | Transaction Orders DB commit. | Lệnh đã được hệ thống nguồn chấp nhận. |
| **T2** | Event được publisher chuyển đến broker và consumer bắt đầu xử lý. | Hệ thống phụ có cơ hội nhận thay đổi, chưa chắc apply. |
| **T3** | Search/cache/đối tác xác nhận cập nhật. | Projection hoặc tích hợp cụ thể đã được cập nhật. |

**T1 ≠ T2 ≠ T3.** Trả HTTP **200/201** cho lệnh sync DB có thể chính xác tại T1 dù search chưa kịp ở T3. **202 Accepted** chỉ phù hợp nếu bản thân thao tác nghiệp vụ **chưa hoàn thành** và có hợp đồng theo dõi, không dùng 202 chỉ vì mọi projection đang async.

## 3. Vì sao “ghi DB rồi gửi message” dễ mất nhất quán?

Xét code ngây thơ:

~~~java
ordersRepository.save(order);
messageBroker.publish(new OrderPaid(order.id()));
~~~

Hai thao tác không chung transaction:

1. **DB commit thành công, publish thất bại** (process chết, broker unreachable): không có message; search và đối tác có thể không biết đơn PAID.
2. **Publish thành công, DB rollback**: consumer thấy một trạng thái chưa từng được commit.
3. **Publish thành công nhưng ACK bị mất**: publisher retry, consumer có thể nhận **hai bản message**.
4. **Thứ tự đổi trạng thái bị đảo**: event version 9 đến trước version 8, hệ thống phụ có thể quay lùi nếu apply mù.

Không sửa bằng cách “đặt hai lời gọi trong **@Transactional**”: transaction manager của PostgreSQL không tự đưa broker/HTTP/Redis vào cùng atomic commit. Distributed transaction/2PC chỉ phù hợp một số môi trường có đầy đủ hỗ trợ và chi phí vận hành được chấp nhận; thường không phải lựa chọn mặc định cho REST API tích hợp bên ngoài.

### 3.1. Không nhầm thứ tự lệnh với atomicity

| Cách làm | Vấn đề tồn tại |
| --- | --- |
| Ghi DB → publish trực tiếp. | Mất event nếu chết sau DB commit. |
| Publish → ghi DB. | Event “ma” nếu DB rollback. |
| Ghi DB → xóa cache. | Có thể bỏ lỡ invalidation, hoặc refill stale bởi request đang chạy. |
| Ghi DB → gọi HTTP đối tác trong transaction. | Transaction giữ lock trong lúc chờ mạng; đối tác có thể thành công khi DB rollback. |
| Retry publish không có idempotency. | Duplicate side effect và sai thứ tự. |

**Nguyên tắc:** commit thay đổi nguồn và **ý định cần phát sự kiện** một cách bền vững trong **cùng DB transaction**. Sau đó một worker/CDC chuyển sự kiện đến các đích, có retry và idempotency.

## 4. Transactional outbox: commit dữ liệu cùng tín hiệu thay đổi

**Transactional outbox** có bảng sự kiện nằm trong cùng database với aggregate. Trong một transaction:

1. Khóa/kiểm version và business rules của order.
2. Cập nhật hàng order và tăng **aggregate version**.
3. Ghi một hàng **outbox event** chứa định danh ổn định, aggregateId, version, type và payload cần thiết.
4. Commit cả hai. Nếu transaction rollback, **không có order mới và không có event**.

~~~sql
-- PostgreSQL: giản lược để minh họa ý nghĩa.
CREATE TABLE orders (
  id uuid PRIMARY KEY,
  tenant_id uuid NOT NULL,
  status text NOT NULL,
  version bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE order_outbox (
  event_id uuid PRIMARY KEY,
  aggregate_id uuid NOT NULL,
  tenant_id uuid NOT NULL,
  aggregate_version bigint NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  published_at timestamptz,
  attempts integer NOT NULL DEFAULT 0,
  UNIQUE (aggregate_id, aggregate_version)
);
~~~

**UNIQUE (aggregate_id, aggregate_version)** minh họa quy tắc **mỗi thay đổi version chỉ có một event** khi hệ thống chọn một event/transition. Nếu transaction sinh nhiều domain events cho cùng version, cần thêm **sequence/event type** trong khóa; không áp constraint mẫu một cách máy móc. **event_id** phục vụ dedupe, còn **aggregate_version** giúp phát hiện thứ tự.

### 4.1. Java/Spring: cập nhật version và ghi outbox trong cùng transaction

~~~java
import java.util.UUID;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record StatusChangeResult(UUID id, String status, long version) {}
class VersionConflictException extends RuntimeException {}

@Service
class OrderStatusService {
    private final NamedParameterJdbcTemplate jdbc;
    private final OutboxRepository outbox;

    OrderStatusService(
            NamedParameterJdbcTemplate jdbc, OutboxRepository outbox) {
        this.jdbc = jdbc;
        this.outbox = outbox;
    }

    @Transactional
    public StatusChangeResult changeStatus(
            UUID tenant, UUID id, long expectedVersion, String newStatus) {
        // Trước đây service đã kiểm business transition và quyền tenant.
        var params = new MapSqlParameterSource()
                .addValue("tenant", tenant)
                .addValue("id", id)
                .addValue("expected", expectedVersion)
                .addValue("status", newStatus);

        int changed = jdbc.update("""
                UPDATE orders
                   SET status = :status,
                       version = version + 1,
                       updated_at = now()
                 WHERE id = :id
                   AND tenant_id = :tenant
                   AND version = :expected
                """, params);
        if (changed != 1) {
            throw new VersionConflictException();
        }

        long nextVersion = expectedVersion + 1;
        outbox.insert(new OrderStatusChanged(
                UUID.randomUUID(), id, tenant, nextVersion, newStatus));
        return new StatusChangeResult(id, newStatus, nextVersion);
    }
}

record OrderStatusChanged(
        UUID eventId, UUID orderId, UUID tenantId,
        long version, String status) {}

interface OutboxRepository {
    void insert(OrderStatusChanged event);
}
~~~

**Giả định:** OutboxRepository.insert thực hiện **SQL INSERT dùng cùng datasource/transaction manager**, không publish mạng ở đây; DB commit thành công mới coi cập nhật hoàn tất. @Transactional chỉ có hiệu lực qua Spring proxy phù hợp. **newStatus** phải qua enum/business validation, không cho caller tùy tiện đặt trạng thái; tenant lấy từ identity đáng tin và kiểm quyền từng order.

UPDATE với điều kiện version là **optimistic concurrency control**: hai request cùng đọc version 7 chỉ một request thành công. Khi không có hàng được cập nhật, có thể là **không tồn tại, khác tenant hoặc version conflict**; phân loại 404/412 theo security policy, không tự trả 500. Nếu dùng JPA @Version, cần test tương đương trong transaction.

### 4.2. Event envelope đủ thông tin để replay

~~~json
{
  "eventId": "c9c158a0-52b5-4e7b-9d17-4dfa8e80c644",
  "type": "OrderStatusChanged",
  "schemaVersion": 1,
  "aggregateId": "11111111-1111-4111-8111-111111111111",
  "tenantId": "22222222-2222-4222-8222-222222222222",
  "aggregateVersion": 8,
  "occurredAt": "2026-11-18T09:00:00Z",
  "data": { "status": "PAID" }
}
~~~

Envelope có identity, version, tenant và schema version để consumer **dedupe**, bỏ event cũ, truy vết và tiến hóa schema. **occurredAt** để đo độ trễ, **không dùng timestamp để quyết định thứ tự** khi đồng hồ lệch. Tránh PII/token/payment details không cần thiết trong event, broker hay log.

## 5. Outbox publisher/CDC: giao hàng được nhưng không hứa exactly-once toàn cục

Outbox **giải quyết atomicity giữa dữ liệu chính và việc ghi nhận sự kiện**; nó **không tự đưa message tới broker**. Có hai cách phổ biến:

- **Polling publisher:** worker đọc hàng chưa publish, claim trong thời gian ngắn, gửi message, chờ broker ACK rồi đánh dấu published.
- **Change Data Capture (CDC):** connector đọc commit log và chuyển hàng outbox đã commit thành event; vẫn phải quản lý offset, schema và duplicate deliveries.

Không nên giữ **DB transaction và row lock** trong cuộc gọi mạng. Với polling, có thể dùng **SELECT ... FOR UPDATE SKIP LOCKED** trong transaction ngắn để claim batch và ghi **lease/claimed_until**; sau commit mới publish. Bảng mẫu ở phần 4 cần thêm cột lease nếu dùng cách này; lease hết hạn cho phép worker khác nhận lại event.

### 5.1. Pseudocode Java/Spring cho dispatcher

~~~java
import java.util.List;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

record OutboxEvent(
        java.util.UUID eventId, java.util.UUID aggregateId,
        long version, String payload) {}

interface OutboxDispatchStore {
    // Claim bằng lease trong transaction ngắn.
    List<OutboxEvent> claimBatch(int limit);
    void markPublished(java.util.UUID eventId);
    void scheduleRetry(java.util.UUID eventId, String safeReason);
}

interface BrokerPublisher {
    // Chỉ return sau ACK thành công theo delivery policy.
    void publishAndAwaitAck(OutboxEvent event);
}

@Component
class OutboxDispatcher {
    private final OutboxDispatchStore store;
    private final BrokerPublisher broker;

    OutboxDispatcher(OutboxDispatchStore store, BrokerPublisher broker) {
        this.store = store;
        this.broker = broker;
    }

    @Scheduled(fixedDelay = 500)
    void dispatch() {
        for (OutboxEvent event : store.claimBatch(100)) {
            try {
                broker.publishAndAwaitAck(event);
                store.markPublished(event.eventId());
            } catch (Exception ex) {
                store.scheduleRetry(event.eventId(), "PUBLISH_FAILED");
            }
        }
    }
}
~~~

Mẫu trên **chưa hiện thực claim/retry**, và cần bật scheduling tại ứng dụng. Với broker client bất đồng bộ phải **đợi ACK thật**, không markPublished ngay sau khi gọi send(). Nếu broker ACK nhưng worker chết trước khi ghi published, event sẽ được phát **lại**. Consumer phải idempotent, kể cả broker có tính năng dedupe hoặc exactly-once trong phạm vi riêng. Hãy thiết kế lease timeout, retry/backoff/jitter, attempts, DLQ, retention, replay và cleanup mà không giữ transaction qua network.

### 5.2. Thứ tự theo aggregate, không theo thời điểm nhận

~~~text
Nguồn: v7 CREATED -> v8 PAID -> v9 FULFILLED
Consumer nhận: v9, v8, v8, v7
~~~

Nếu cứ áp message cuối cùng, search có thể quay ngược **FULFILLED → PAID → CREATED**. Nên:

1. Partition theo **aggregateId** khi broker hỗ trợ để giảm đảo thứ tự; retry/replay vẫn có thể làm trùng.
2. Lưu **lastAppliedVersion** cùng projection, chỉ áp version **lớn hơn** bằng một thao tác nguyên tử.
3. Với event chứa **full snapshot trạng thái**, có thể bỏ qua phiên bản trung gian khi nhảy v7 → v9; với **delta cần mọi bước**, phải phát hiện gap và replay theo thứ tự.
4. Không dùng **occurredAt**/đồng hồ làm bằng chứng về thứ tự commit giữa nhiều node.

### 5.3. Consumer idempotent tại DB projection

~~~sql
CREATE TABLE order_projection (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    status text NOT NULL,
    source_version bigint NOT NULL,
    deleted boolean NOT NULL DEFAULT false
);

INSERT INTO order_projection
        (id, tenant_id, status, source_version, deleted)
VALUES (:id, :tenant, :status, :version, false)
ON CONFLICT (id) DO UPDATE
   SET status = EXCLUDED.status,
       tenant_id = EXCLUDED.tenant_id,
       source_version = EXCLUDED.source_version,
       deleted = EXCLUDED.deleted
 WHERE order_projection.source_version < EXCLUDED.source_version;
~~~

PostgreSQL chỉ apply bản mới hơn ngay trong một statement nguyên tử. Nhận v9 trước v8 **không quay lùi dữ liệu**, nhận lại v9 không nhân đôi side effect. Đây là SQL minh họa dùng named parameters do client JDBC bind, giả định **order ID duy nhất toàn cục** và event mang **full snapshot của các field trong projection**. Delta như trừ tiền/tăng số lượng phải kiểm gap và không được áp vượt bước.

**Deletion/tombstone:** nếu consumer xóa hẳn row sau Deleted version 10, một Update version 9 đến muộn có thể **tạo lại bản ghi**. Giữ tombstone/high-watermark ít nhất đến khi hết khả năng replay, rồi mới cleanup theo policy. External search cũng cần version/tombstone tương tự.

### 5.4. Inbox dedupe và giới hạn ACK

Với side effect thực hiện **trong cùng local DB**, tạo **consumer_inbox(consumer_name, event_id)** unique, **INSERT inbox + update projection trong cùng transaction**. Event đã có thì bỏ qua/ACK; transaction rollback thì inbox rollback để retry.

Nếu side effect là **HTTP đối tác hoặc search engine ở hệ khác**, ghi inbox trước call có thể **mất việc** khi chết; ghi sau call có thể **làm hai lần**. Cần idempotency key/version ở destination, workflow state bền vững và đối soát. **Exactly-once end-to-end qua nhiều hệ độc lập không có chỉ nhờ một cờ của broker.**

## 6. Cache: invalidation là một phần consistency contract

### 6.1. Cache-aside và khoảng thời gian stale

~~~text
GET /api/orders/123
  1. Kiểm authentication/authorization của actor.
  2. Đọc cache key có tenant scope.
  3. Miss: đọc DB gốc rồi điền cache có TTL.

PATCH /api/orders/123
  1. DB commit trạng thái mới + outbox.
  2. Consumer nhận event rồi invalidate/refresh cache.
~~~

Ví dụ Redis key: **orders:{tenantId}:{orderId}**. Tenant phải từ identity đáng tin và kiểm membership; nếu response thay theo **vai trò, trường ẩn hoặc locale**, cache key/data phải phân biệt representation. Cache hit **không miễn kiểm authorization**: quyền có thể đổi độc lập với order.

Sau DB commit nhưng trước invalidation, Redis có thể còn v7 trong khi DB v8. Nếu invalidation mất, TTL có thể buộc miss về sau, nhưng **TTL không thay outbox/replay/monitoring**, và không nên công bố strong consistency khi cache có thể stale.

### 6.2. Race: stale refill sau invalidation

~~~text
R1: GET miss -> đọc DB v7 (chưa ghi cache)
W : PATCH DB commit v8
W : invalidate key
R1: ghi v7 vào cache
R2: GET hit v7, dù invalidation đã chạy
~~~

**Xóa key sau commit chưa đủ**. Chọn theo yêu cầu:

- **Value có sourceVersion + compare-and-set**: write v7 không ghi đè dữ liệu v8.
- **Versioned keys/generation**: lookup dựa trên version được xác minh, không dùng pointer stale.
- **TTL ngắn/revalidation**, chấp nhận stale trong giới hạn đã công bố.
- **Bypass cache hoặc đọc primary DB** cho endpoint/operation yêu cầu read-your-writes.

“Xóa hai lần sau một khoảng ngủ” chỉ giảm rủi ro ở một số workload, **không chứng minh correctness**. List/search result caches còn khó invalidate hơn per-order key, nên cần tag/generation hoặc TTL cho từng loại projection.

### 6.3. Redis cache khác HTTP cache

**ETag/If-None-Match** và **Cache-Control** là hợp đồng client/proxy; khác Redis nội bộ. Với response cá nhân, dùng **private/no-store hoặc revalidation** theo threat model. **304 Not Modified** phải dựa trên validator của đúng representation; đừng trả 304 từ Redis stale khi bản ghi nguồn đã đổi. Cache keys không được bỏ tenant/authorization scope chỉ để tăng cache-hit rate.

## 7. Search index: projection để tìm kiếm, không phải quyết định quyền cuối

Một document trong Elasticsearch/OpenSearch hoặc công cụ tương đương có thể trông như:

~~~json
{
  "orderId": "11111111-1111-4111-8111-111111111111",
  "tenantId": "22222222-2222-4222-8222-222222222222",
  "status": "PAID",
  "totalMinorUnit": 125000,
  "sourceVersion": 8,
  "updatedAt": "2026-11-18T09:00:00Z"
}
~~~

Chính sách indexing:

1. **Chỉ index thay đổi đã commit** qua outbox/CDC hay cơ chế tương đương.
2. Dùng **document ID ổn định** từ aggregate ID; nếu ID chỉ duy nhất trong tenant, kết hợp tenant vào key.
3. Áp **version ordering/external versioning/CAS** của search engine, không cho event v8 ghi đè document v9.
4. Xử lý **delete/tombstone**, kể cả khi event cũ đến sau khi xóa.
5. Retry 429/5xx có backoff, giám sát **indexing lag**, xử lý lỗi mapping/schema và hỗ trợ rebuild.

**Search không phải lớp authorization cuối.** Index có thể chưa nhận thay đổi quyền hoặc thông tin xóa; nên lọc tenant theo identity đáng tin và kiểm quyền khi người dùng đọc chi tiết resource gốc. Với kết quả chứa dữ liệu nhạy cảm ngay trong danh sách, phải áp privacy policy nghiêm hơn (ví dụ truy vấn DB kiểm lại trước khi trả), không chỉ trông vào index stale. Search result có thể tạm thời thiếu order vừa cập nhật; **GET /api/orders/{id}** từ primary là nguồn tra cứu cần ưu tiên cho hành động quan trọng.

### 7.1. Rebuild index không được bỏ thay đổi trong lúc backfill

~~~text
1. Tạo index mới có schema/mapping N+1, chưa phục vụ traffic.
2. Ghi checkpoint của source/CDC/outbox.
3. Backfill snapshot DB vào index mới, kèm sourceVersion.
4. Replay changes phát sinh trong lúc backfill, dùng version/tombstone.
5. So sánh số lượng, độ mới, quyền tenant, mapping và search quality.
6. Chuyển search alias theo cơ chế atomic alias của engine.
7. Duy trì catch-up/rollback plan rồi mới dọn index cũ.
~~~

Nếu chỉ scan DB rồi đổi alias, một order cập nhật trong lúc scan có thể **mất khỏi index hoặc quay về bản cũ**. Cần biết snapshot/CDC offset và đủ log retention để replay. **Đếm số document bằng nhau chưa chứng minh giá trị/index quyền bằng nhau**.

### 7.2. Hợp đồng REST cho tìm kiếm eventual

Không mặc định hứa **GET /api/orders?status=PAID** có snapshot giống ngay **GET /api/orders/{id}**. Nếu trải nghiệm cần read-your-writes, có thể điều hướng thẳng tới resource mới commit, đợi watermark/version của projection có giới hạn, hoặc thực hiện truy vấn DB cho tình huống đó. Metadata như **asOf** hay watermark có thể giúp UI hiển thị “đang đồng bộ” nếu được định nghĩa chính xác và không lộ thông tin tenant khác.

Cursor pagination trên index đang thay đổi có thể thấy trùng/thiếu document; nếu yêu cầu phân trang snapshot ổn định, dùng cơ chế snapshot/PIT/search_after hoặc hợp đồng tương đương, không chỉ OFFSET trên tập biến động.

## 8. Hệ thống ngoài: gửi yêu cầu và hoàn thành nghiệp vụ là hai trạng thái

Đối tác hóa đơn nhận **POST /invoices** khi đơn PAID. Phân biệt:

| Tình huống | Thực tế có thể xảy ra | Cách xử lý |
| --- | --- | --- |
| HTTP timeout, không nhận response. | Đối tác **có thể đã tạo hóa đơn**. | Giữ idempotency key, tra trạng thái; không thử lại bằng key mới mù quáng. |
| Đối tác trả **202 Accepted**. | Đã nhận yêu cầu nhưng chưa hoàn tất. | Theo job/monitor, callback hoặc polling theo contract. |
| Đối tác trả **201** nhưng ACK bị mất. | Remote side effect đã xảy ra. | Dedupe ổn định từ đối tác và reconciliation. |

Outbox chỉ giữ được **ý định gửi**, không chứng minh remote business result. Worker tích hợp nên có trạng thái bền vững như **PENDING, IN_FLIGHT, ACKNOWLEDGED, SUCCEEDED, FAILED_RETRYABLE, NEEDS_REVIEW**. Đối tác trả 202 có thể là ACKNOWLEDGED, nhưng **không được tự đánh dấu SUCCEEDED**.

### 8.1. Outbound POST có idempotency key ổn định

~~~http
POST /invoices HTTP/1.1
Host: billing.partner.example
Authorization: Bearer <partner-access-token>
Content-Type: application/json
Accept: application/json, application/problem+json
Idempotency-Key: order-11111111-paid-v8
X-Request-ID: c9c158a0-52b5-4e7b-9d17-4dfa8e80c644

{
  "orderId": "11111111-1111-4111-8111-111111111111",
  "amountMinorUnit": 125000
}
~~~

**Key ổn định cho cùng logical command** qua các lần retry, được namespace theo provider/tenant/operation nếu cần. Đối tác phải có contract thực thi key, retention và cùng key khác payload; chỉ gửi header **Idempotency-Key không bảo đảm** nếu họ bỏ qua. Không sinh key mới mỗi lần retry. Không gửi access token người dùng sang service đối tác có audience khác.

### 8.2. Webhook inbound: xác thực trước khi đưa vào inbox

Webhook phản hồi kết quả cần:

1. **TLS và signature/HMAC** bằng thuật toán/secret được thống nhất trên **raw body bytes** và timestamp/nonce. Không ký sau khi parse và serialize lại JSON.
2. Chống replay bằng **time window** và unique provider/event ID; chữ ký của event cũ có thể vẫn hợp lệ nếu không kiểm timestamp. Nếu tự so chữ ký, dùng constant-time compare.
3. **Lưu inbox/event bền vững trước khi ACK 2xx** nếu sẽ xử lý async; worker riêng cập nhật trạng thái tích hợp và order theo state machine/transaction.
4. Đối chiếu tenant/order/amount với integration request đã lưu, **không tin trực tiếp** các ID từ payload dù chữ ký hợp lệ.

**2xx của webhook thường chỉ xác nhận đã nhận**, không chứng minh mọi xử lý sau đó thành công. Signature sai → 401/403, payload sai → 400, lỗi hạ tầng tạm thời → 5xx để provider retry nếu họ có chính sách này. Cần kiểm provider thực sự retry status nào, cách ký và retention của event IDs.

### 8.3. Ranh giới credential và SSRF

Chỉ gọi **base URL đã allowlist**, HTTPS/TLS validation, giới hạn redirect và không forward bearer token của người dùng. Dùng service credential có audience/scope riêng, timeout/circuit breaker, rate limit và secret rotation. Không ghi payment details, token, raw webhook body nhạy cảm vào logs hoặc DLQ không được kiểm soát.

## 9. HTTP contract: commit của API khác độ mới của projection

Một client đọc order version 7 rồi muốn chuyển sang PAID. Dùng precondition để ngăn ghi đè khi có người cập nhật trước:

~~~http
PATCH /api/orders/11111111-1111-4111-8111-111111111111 HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json, application/problem+json
If-Match: "order-v7"

{"status":"PAID"}

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-v8"
Cache-Control: private, no-store

{
  "id":"11111111-1111-4111-8111-111111111111",
  "status":"PAID",
  "version":8
}
~~~

Đây là **request và response minh họa đặt liên tiếp**, không phải một HTTP message. API trả **200 sau transaction DB + outbox commit**, không đợi search/đối tác. Ví dụ ETag là dạng **strong validator do server kiểm soát**; trong production nó phải đại diện đúng phiên bản representation/biến thể, không chỉ tùy tiện đặt từ một cột nếu representation có thể đổi độc lập. Controller kiểm If-Match theo contract, map thành **expectedVersion** trước khi gọi service.

| Tình huống | Status/hành vi |
| --- | --- |
| PATCH hợp lệ, commit DB + outbox thành công | **200** với representation/ETag mới hoặc **204** không body theo contract. |
| If-Match không khớp version hiện tại | **412 Precondition Failed**; không ghi thay đổi/outbox. |
| API bắt buộc precondition nhưng thiếu If-Match | Có thể dùng **428 Precondition Required**. |
| Không tìm thấy order hoặc không được tiết lộ | **404** theo chính sách quyền; không để 412 làm lộ order thuộc tenant khác. |
| Không xác thực/không có quyền | **401/403**; kiểm quyền trước khi phản hồi nội dung riêng. |
| Business transition không hợp lệ | **409 Conflict** hoặc **422** theo hợp đồng nghiệp vụ. |
| DB commit thất bại | **5xx** phù hợp, không trả 200 vì đã gửi message trước đó. |
| Chỉ search hoặc đối tác đang chậm sau DB commit | Trạng thái order vẫn là **đã commit**; tracking projection tách riêng. |

**202 Accepted** phù hợp khi **chính command** mới được đưa vào hàng đợi và chưa được thực thi. Nếu chọn mô hình đó, dùng resource theo dõi:

~~~http
HTTP/1.1 202 Accepted
Location: /api/operations/op-7f3d
Retry-After: 3
Content-Type: application/json

{"operationId":"op-7f3d","status":"PENDING"}
~~~

Không lẫn **operation chưa commit** với **order đã commit nhưng search chưa index**. Một status endpoint có thể công bố trạng thái kết nối đối tác mà không làm thay đổi kết quả nghiệp vụ của GET order. Nếu API đòi read-your-writes, route GET sau PATCH tới primary hoặc một nguồn có watermark/version phù hợp, không mặc định đọc cache/replica có lag.

## 10. Reconciliation và replay: kế hoạch khi event bị mất hoặc projection lệch

Outbox, retry và consumer idempotent giúp giảm lỗi nhưng vẫn có thể xảy ra **schema mismatch, thao tác thủ công trên DB, bug consumer, retention quá ngắn hoặc đối tác xử lý khác dự kiến**. Cần **reconciliation** độc lập với việc message đã được ACK.

### 10.1. Đối soát nội bộ

Một job theo chu kỳ:

1. Chọn phạm vi theo tenant, aggregate/time window hoặc checkpoint; đọc **version/trạng thái DB chuẩn**.
2. So sánh với **lastAppliedVersion** ở search/projection, hoặc bản ghi trạng thái publish/integration.
3. Nếu projection chậm nhưng còn event, **replay có idempotency** từ checkpoint; nếu hết event hoặc schema bị sai, **rebuild snapshot + catch-up**.
4. Đối với deleted resources, kiểm **tombstone**; đừng để replay cũ khôi phục thông tin đã xóa.
5. Ghi kết quả đối soát, retry schedule, người xử lý và bằng chứng đã repair. Giới hạn rate để job không gây quá tải hệ chính.

**Không chỉ so số row.** Hai bên có thể cùng 1.000 order nhưng khác status/version/tenant. So checksum/schema hash có kiểm soát, lấy mẫu chi tiết và so aggregateVersion tùy chi phí. Với search eventual, đối soát chỉ nên báo drift sau **grace window** đã định nghĩa, tránh phát hiện giả mọi thay đổi đang chờ index.

### 10.2. Đối soát với đối tác

Khi gọi POST hóa đơn timeout, worker không biết remote đã tạo chưa. Tìm bằng **external request ID/idempotency key** hoặc API tra cứu của đối tác, cập nhật local integration state theo response có thể chứng minh, sau đó mới quyết định retry/compensation. Nếu remote không có cơ chế tra cứu/dedupe, cần chính sách xử lý thủ công, giới hạn attempt và tránh tự động tạo yêu cầu thứ hai gây mất tiền.

**Compensation** không nhất thiết là rollback kỹ thuật: hóa đơn đã phát hành có thể cần một **credit note** hoặc thao tác nghiệp vụ đảo tác động, chứ không xóa row DB. Đó là quy tắc domain và quy định đối tác, phải thiết kế riêng; outbox không tự thực hiện Saga.

### 10.3. DLQ không phải “thùng rác an toàn”

Một event bị schema mismatch hoặc input không hợp lệ không nên retry nóng mãi. Đưa vào **quarantine/DLQ** với lỗi đã redacted, lưu correlation, tenant scope và lý do. Có quy trình phân loại, sửa schema/bug, **replay** và xác nhận projection sau replay. Giới hạn quyền đọc DLQ vì payload có thể nhạy cảm, đặt retention tương ứng và tránh ghi secrets.

## 11. SLO, telemetry và an toàn vận hành

| Chỉ số | Cách đo / câu hỏi |
| --- | --- |
| **Outbox oldest unprocessed age** | Sự kiện lâu nhất chưa publish đã chờ bao lâu? |
| **Broker/consumer lag** | Consumer chậm bao nhiêu event/thời gian so với checkpoint? |
| **Projection apply latency p95/p99** | Từ DB commit đến search/cache apply mất bao lâu? |
| **Stale read rate** | Bao nhiêu request trả bản cũ hơn nguồn trong mẫu đối soát? |
| **Duplicate/stale event count** | Có nhiều retry/đảo thứ tự bất thường không? |
| **DLQ depth / retry exhaustion** | Event nào cần người can thiệp? |
| **External pending age / success rate** | Đối tác đã ACK nhưng chưa SUCCEEDED bao lâu? |
| **Reconciliation drift** | Có bao nhiêu order sai version/trạng thái quá grace window? |

Log/traces nên nối **request ID → transaction/orderId → outbox eventId → broker messageId → consumer action → partner request ID**. Không đặt **orderId, eventId, token, email** làm metric label có cardinality vô hạn; dùng trace/log có retention và kiểm quyền. Cấu hình alert theo SLO và backlog age, không chỉ tổng count message; có thể 0 failure nhưng hệ thống ngừng tiến nên độ trễ tăng mãi.

**Thứ tự xử lý sự cố đề xuất:** tạm dừng consumer lỗi gây side effect, bảo toàn outbox/offset, xác định mốc commit và version đúng, sửa root cause, replay theo idempotent/version guards, đối soát và ghi lại kết quả. Không reset offset và replay toàn bộ vào đối tác trước khi kiểm idempotency.

## 12. Kiểm thử đúng failure windows, không chỉ happy path

| ID | Kịch bản | Điều cần chứng minh |
| --- | --- | --- |
| T01 | Cập nhật order thành công | **Order + outbox commit cùng transaction**, version tăng đúng một lần. |
| T02 | Outbox INSERT thất bại sau UPDATE | **Rollback toàn transaction**; không có order changed mà thiếu outbox. |
| T03 | DB commit rồi publisher chết trước broker send | Outbox vẫn pending; worker mới gửi được. |
| T04 | Broker ACK rồi worker chết trước markPublished | Event phát lại nhưng consumer **không áp side effect hai lần**. |
| T05 | Consumer nhận v9, v8, v8, v7 | Projection không quay lùi khỏi v9. |
| T06 | Deleted v10 rồi Update v9 tới muộn | Tombstone/high-watermark chặn phục hồi dữ liệu. |
| T07 | Cache miss v7, commit v8 + invalidate, refill v7 | Chính sách CAS/version/TTL ngăn hoặc giới hạn stale đúng cam kết. |
| T08 | Search index down/429, broker vẫn nhận | Retry/backoff, DLQ, backfill; API cốt lõi không bị hỏng do search. |
| T09 | Reindex chạy khi có cập nhật | Snapshot + replay không bỏ hoặc ghi đè version mới. |
| T10 | Đối tác timeout sau khi đã commit hóa đơn | Retry cùng key hoặc reconcile; không tạo hai hóa đơn. |
| T11 | Webhook giả chữ ký/replay/cross-tenant | Bị từ chối/dedupe; không mutate order. |
| T12 | Người dùng POST với If-Match cũ | **412** và không phát outbox. |
| T13 | Cùng order, hai tenant/actor khác quyền | Cache/search/GET không lộ dữ liệu hoặc status nhạy cảm. |

### 12.1. Một integration test cho atomic update + outbox

Với **Spring Boot**, **JdbcTemplate** và DB test cô lập (ví dụ PostgreSQL qua Testcontainers), sau khi cấu hình repository thật:

~~~java
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class OrderOutboxIT {
    @Autowired JdbcTemplate jdbc;
    @Autowired OrderStatusService service;

    @Test
    void updateAndOutboxArePersistedTogether() {
        UUID id = UUID.randomUUID();
        UUID tenant = UUID.randomUUID();
        jdbc.update("""
            INSERT INTO orders(id, tenant_id, status, version)
            VALUES (?, ?, 'CREATED', 7)
            """, id, tenant);

        var result = service.changeStatus(tenant, id, 7, "PAID");
        Long version = jdbc.queryForObject(
                "SELECT version FROM orders WHERE id = ?",
                Long.class, id);
        Integer events = jdbc.queryForObject("""
                SELECT COUNT(*) FROM order_outbox
                 WHERE aggregate_id = ? AND aggregate_version = 8
                """, Integer.class, id);

        assertEquals(8L, result.version());
        assertEquals(8L, version.longValue());
        assertEquals(1, events.intValue());
    }
}
~~~

Đây là **test mẫu**: cần datasource/transaction manager, implementation OutboxRepository ghi cùng transaction, fixture database riêng và cleanup của test suite. Test này kiểm success path; **T02 phải chủ động gây lỗi INSERT outbox và xác nhận UPDATE rollback**, T04/T05 cần thử duplicate/out-of-order và các test đối tác cần fake server điều khiển ACK/timeout. Đừng bọc toàn bộ test bằng test-level transaction rollback nếu mục đích là chứng minh hành vi **commit thật và publish sau commit**.

### 12.2. Contract test HTTP và bảo mật

Với **MockMvc hoặc WebTestClient**, kiểm **PATCH + If-Match → 200/412**, response ETag, JSON/Problem Details, authorization theo tenant và service chỉ gọi khi được phép. Trên test tích hợp end-to-end, tách **GET trực tiếp** với **GET search** để kiểm đúng freshness contract. Dùng fake broker/partner có khả năng gửi duplicate, đảo thứ tự, delay và timeout; chỉ có unit test một hàm mapper **không đủ chứng minh eventual consistency**.

## 13. Bài tập: đơn PAID nhưng search vẫn CREATED

**Tình huống:** DB đã commit order v8 PAID lúc 10:00; outbox có event e8. Redis còn v7; search index hiện v7. Broker phân phối e8 hai lần, rồi nhận muộn e7. Một cuộc gọi tạo invoice tới đối tác timeout, nhưng dashboard đối tác báo đã có invoice với externalRequestId e8.

**Yêu cầu:** (1) Khi nào PATCH nên trả 200 hay 202? (2) Làm sao bảo đảm DB commit không mất e8? (3) Consumer/search xử lý chuỗi e8,e8,e7 thế nào? (4) Kể một race làm cache quay lại v7 sau khi invalidate và cách ngăn. (5) Có nên POST invoice lần nữa với key mới? (6) Đề xuất năm chỉ số giám sát và bốn test lỗi. (7) Khi nào nên sửa index bằng reindex + CDC replay thay vì sửa thủ công một document?

**Hướng giải:** PATCH trả **200/204 khi DB+outbox đã commit**; 202 nếu chỉ mới queue nghiệp vụ. Outbox trong cùng transaction và publisher retry sau commit. Search apply **v8**, bỏ duplicate e8 và e7 cũ, giữ tombstone/version cho delete. Cache-aside có thể refill v7 sau invalidation, xử lý bằng version/CAS, read-through có nguồn xác minh hoặc TTL theo freshness contract. **Không tạo invoice lần hai với key mới**; đối soát theo externalRequestId/idempotency key cũ và cập nhật trạng thái. Theo dõi outbox age, consumer lag, search apply latency, cache stale rate, integration pending age/DLQ. Reindex + replay khi drift hàng loạt hoặc mapping sai, tránh sửa lẻ thiếu lịch sử.

## 14. Checklist phát hành

- [ ] Có **source of truth** và freshness contract riêng cho GET trực tiếp, cache, search, hệ thống ngoài.
- [ ] Commit DB + outbox **cùng transaction**; không gọi broker/HTTP network trong DB transaction.
- [ ] Publisher có lease/ACK/retry/backoff/DLQ/retention; consumer chịu được duplicate.
- [ ] Event có **eventId, aggregateId, tenantId, aggregateVersion, schemaVersion** và chỉ dữ liệu cần thiết.
- [ ] Consumer áp monotonic version, hiểu snapshot/delta và **tombstone/deletion**.
- [ ] Cache keys/TTL/permissions an toàn, xử lý stale refill và HTTP validators đúng semantics.
- [ ] Search index có id ổn định, version ordering, rebuild snapshot + CDC replay và tenant controls.
- [ ] Đối tác có stable idempotency key, trạng thái tích hợp, webhook verification và reconciliation.
- [ ] PATCH/POST trả status theo **commit nghiệp vụ**, không đánh đồng với projection lag.
- [ ] Đo outbox age, projection lag, external pending age, drift; diễn tập crash/replay.
- [ ] Test duplicate, out-of-order, stale cache, delete, partner timeout, rollback và cross-tenant.

**Kết luận:** nhất quán nghiệp vụ khi đồng bộ cache, search và hệ thống ngoài không đến từ việc “gọi cập nhật ở cả bốn nơi”. Thiết kế bền vững bắt đầu bằng **nguồn sự thật và transaction rõ**, ghi outbox cùng commit, phát sự kiện có thể retry, consumer **idempotent và có version guard**, cache/search có chính sách độ mới phù hợp, đối tác có idempotency/reconciliation, và các tình huống lỗi đều được kiểm thử. REST API phải nói chính xác **điều gì đã commit** và **điều gì còn đang được đồng bộ**.

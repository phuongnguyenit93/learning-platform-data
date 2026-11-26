# LWT, batch và phạm vi nguyên tử trong chuỗi phản ứng với Spring Data Cassandra

## 1. Một chuỗi Mono có phải là một giao dịch không?

Một dịch vụ Spring Boot dùng **Spring Data Cassandra** nhận lệnh thanh toán đơn hàng. Lập trình viên viết một chuỗi phản ứng:

~~~java
return orderService.markPaid(orderId)
    .then(eventService.appendPaidEvent(orderId))
    .then(notificationService.notifyCustomer(orderId));
~~~

Ba thao tác được **xếp theo thứ tự trong một reactive chain**, nhưng điều đó **không** khiến Cassandra bảo đảm rằng cả ba bước cùng commit hoặc cùng rollback. Nếu bước đầu đã ghi thành công rồi bước hai thất bại, trạng thái đơn hàng có thể là `PAID` nhưng bảng sự kiện chưa có `OrderPaid`. Nếu người dùng đóng trình duyệt giữa chừng và subscription bị hủy, thao tác đã gửi trước đó cũng **không được tự động hoàn tác**.

Đây là ngộ nhận cần giải quyết ở chương **Truy cập phản ứng** của module **SPRING_DATA_CASSANDRA**: **Reactor điều phối luồng bất đồng bộ; CQL/LWT/batch quy định phạm vi bảo đảm dữ liệu tại Cassandra.** Một fluent chain không tự mở rộng bảo đảm nguyên tử của database.

Trong bài này, ta phân biệt:

- **`Mono`/`Flux` và subscription:** khi nào query được gửi, các bước được nối và xử lý lỗi ra sao.
- **Lightweight transaction (LWT):** một mutation có điều kiện theo trạng thái hiện tại, với kết quả `[applied]`.
- **CQL batch:** gộp nhiều mutation theo một ngữ nghĩa batch cụ thể; **không đồng nghĩa transaction ACID đa partition**.
- **Workflow nhiều bước:** nhiều câu CQL, nhiều bảng, event/notification — cần idempotency, retry và đối soát.
- **Atomicity, isolation, ordering, durability, consistency:** những thuộc tính riêng biệt không thể suy ra chỉ từ tên API reactive.

**Mục tiêu học tập:**

1. Viết reactive gateway kết nối Java driver Cassandra 4.x và Reactor mà không block thread xử lý I/O.
2. Đọc được `AsyncResultSet.wasApplied()` của LWT thay vì chỉ coi việc `Mono` complete là mutation thành công.
3. So sánh batch `LOGGED`, `UNLOGGED` và conditional batch về partition, atomicity, isolation và chi phí.
4. Biết vì sao `flatMap`, `then`, `concatMap`, `zip` hoặc `@Transactional` không tự biến nhiều request CQL thành một transaction Cassandra.
5. Xử lý đúng timeout, cancel, resubscribe, retry, command ID, bảng denormalized và tính nhất quán cuối cùng của projection.
6. Kiểm thử đồng thời hai writer, lỗi ở giữa chuỗi và hành vi cancellation trên môi trường Cassandra thật.

## 2. Trước hết: “nguyên tử” đang nói tới điều gì?

Các khái niệm sau thường bị dùng lẫn:

| Khái niệm | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Atomicity** | Tập mutation được xem như một đơn vị thành công/thất bại theo phạm vi nào? | Một batch đủ điều kiện được bảo đảm nguyên tử trong phạm vi Cassandra hỗ trợ |
| **Isolation** | Request khác có thể quan sát một phần quá trình không? | Batch đa partition không tự cung cấp isolation như transaction SQL |
| **Conditional atomicity/CAS** | Chỉ ghi nếu dữ liệu hiện tại thỏa điều kiện? | `UPDATE ... IF version = ?` |
| **Ordering** | Những bước nào được bắt đầu sau bước nào? | `then(...)` bắt đầu bước sau khi publisher trước hoàn tất |
| **Durability/acknowledgement** | Có bao nhiêu replica đã phản hồi theo mức yêu cầu? | Write `LOCAL_QUORUM` |
| **Eventual consistency** | Các bản sao hoặc bảng projection hội tụ dần sau khi ghi? | Bảng danh sách có thể cập nhật sau bảng trạng thái chính |

Một câu như “tôi dùng `concatMap` nên tất cả bước ghi là nguyên tử” nhầm **ordering ở Java** với **atomicity của database**. Tương tự, `LOGGED BATCH` giúp xử lý các mutation trong một batch theo quy tắc Cassandra, **không tự tạo khóa cô lập mọi truy vấn đọc của ứng dụng**.

### 2.1. Bốn phạm vi khác nhau

~~~mermaid
flowchart TB
    A[HTTP request / Reactive subscription] --> B[Mono hoặc Flux chain]
    B --> C[CQL statement 1]
    B --> D[CQL statement 2]
    C --> E[Partition / replicas tương ứng]
    D --> F[Partition / replicas tương ứng]
    G[LWT hoặc BATCH] -. Bảo đảm theo phạm vi CQL hợp lệ .-> E
    G -. Không tự mở rộng sang mọi side effect .-> F
~~~

Có thể có bốn ranh giới:

1. **Một CQL statement** được Cassandra thực hiện theo các bảo đảm của statement đó.
2. **Một conditional mutation/LWT** được quyết định với điều kiện trên khóa phù hợp.
3. **Một CQL batch** chứa một nhóm mutation mà Cassandra xử lý theo quy tắc logged/unlogged/conditional.
4. **Một reactive workflow** gồm nhiều statement, nhiều database hoặc API bên ngoài; không có transaction bao trùm chỉ nhờ Reactor.

Khi thiết kế, hãy viết rõ **bất biến nghiệp vụ nằm ở phạm vi nào** trước khi chọn LWT hay batch.

## 3. Schema: hai bảng và hai đường truy vấn

Giả sử dịch vụ có hai access pattern: tìm trạng thái đơn bằng ID và đọc lịch sử sự kiện của đơn:

~~~sql
-- Keyspace app_ks phải được tạo trước với replication phù hợp topology.
CREATE TABLE app_ks.orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    state text,
    version bigint,
    last_command_id uuid,
    updated_at timestamp
);

CREATE TABLE app_ks.order_events_by_order (
    order_id uuid,
    event_no bigint,
    event_id uuid,
    event_type text,
    occurred_at timestamp,
    payload text,
    PRIMARY KEY ((order_id), event_no)
) WITH CLUSTERING ORDER BY (event_no ASC);
~~~

| Bảng | Partition key | Clustering key | Đường đọc |
| --- | --- | --- | --- |
| `orders_by_id` | `order_id` | Không có | `SELECT ... WHERE order_id = ?` |
| `order_events_by_order` | `order_id` | `event_no` | `WHERE order_id = ? AND event_no >= ?` |

Hai bảng có thể cùng dùng giá trị `order_id` nhưng vẫn là **hai bảng với dữ liệu/partition và mutation riêng**. Đừng hiểu rằng chúng được tự động cập nhật cùng nhau chỉ vì partition key có cùng kiểu và giá trị.

Một query timeline đúng đường clustering:

~~~sql
SELECT event_no, event_id, event_type, occurred_at
FROM app_ks.order_events_by_order
WHERE order_id = ? AND event_no >= ?
LIMIT 100;
~~~

**Query-first design vẫn là nền tảng:** LWT, batch và Reactor không thể biến truy vấn thiếu partition key thành truy vấn hiệu quả hoặc cho phép `ORDER BY` tùy ý trên cột thường.

## 4. ReactiveCassandraRepository cho đường CRUD thông thường

Spring Data Cassandra có reactive repository cho những thao tác đọc/ghi phù hợp entity mapping. Ví dụ:

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_id")
public class OrderRow {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("state")
    private String state;

    @Column("version")
    private Long version;

    @Column("last_command_id")
    private UUID lastCommandId;

    @Column("updated_at")
    private Instant updatedAt;

    protected OrderRow() {}

    public UUID getOrderId() { return orderId; }
    public String getState() { return state; }
    public Long getVersion() { return version; }
    public UUID getLastCommandId() { return lastCommandId; }
    public Instant getUpdatedAt() { return updatedAt; }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.repository.ReactiveCassandraRepository;

public interface ReactiveOrderRepository
        extends ReactiveCassandraRepository<OrderRow, UUID> {
}
~~~

Với phiên bản phù hợp, repository có thể cung cấp `Mono<OrderRow> findById(UUID)`, `Mono<OrderRow> save(OrderRow)` và các thao tác reactive khác.

Nhưng cần phân biệt:

- `Mono<OrderRow>` **không có nghĩa** Cassandra đã kiểm tra điều kiện trên version.
- Một lệnh `save(...)` thông thường có thể là **upsert**.
- Một field có tên `version` **không mặc nhiên** bật LWT. Spring Data Cassandra ở một số phiên bản có hỗ trợ optimistic locking qua `@Version`, nhưng phải kiểm tra chính xác hợp đồng với entity mới/cũ, kiểu trả về và exception của phiên bản đang dùng.
- Repository reactive không tự ghép mọi lệnh `save`, `delete` và `findById` trong cùng một transaction phân tán.

Nếu nhu cầu chính là **kết quả CAS chính xác** hoặc **batch CQL có ngữ nghĩa rõ ràng**, có thể bổ sung gateway dựa trên Java driver bất đồng bộ, rồi bọc bằng Reactor.

## 5. Java driver 4.x + Reactor: dựng Mono thực sự thực thi theo subscription

Java driver Cassandra 4.x cung cấp `CqlSession.executeAsync(...)`, thường trả `CompletionStage<AsyncResultSet>`. Reactor có thể chuyển kết quả này thành `Mono` mà không cần gọi `get()` hoặc `join()`.

Ví dụ LWT tạo đơn nếu chưa có:

~~~sql
INSERT INTO app_ks.orders_by_id
    (order_id, customer_id, state, version, last_command_id, updated_at)
VALUES (?, ?, 'CREATED', 1, ?, ?)
IF NOT EXISTS;
~~~

Gateway:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;
import reactor.core.publisher.Mono;

public final class ReactiveOrderCasGateway {
    private final CqlSession session;
    private final PreparedStatement createIfAbsent;
    private final PreparedStatement payIfVersion;

    public ReactiveOrderCasGateway(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.createIfAbsent = session.prepare(
            "INSERT INTO app_ks.orders_by_id " +
            "(order_id, customer_id, state, version, " +
            "last_command_id, updated_at) " +
            "VALUES (?, ?, 'CREATED', 1, ?, ?) IF NOT EXISTS"
        );
        this.payIfVersion = session.prepare(
            "UPDATE app_ks.orders_by_id " +
            "SET state = 'PAID', version = ?, " +
            "last_command_id = ?, updated_at = ? " +
            "WHERE order_id = ? " +
            "IF version = ? AND state = 'CREATED'"
        );
    }

    public Mono<Boolean> createIfAbsent(
            UUID orderId, UUID customerId,
            UUID commandId, Instant now) {
        return Mono.defer(() -> {
            BoundStatement bound = createIfAbsent.bind(
                    orderId, customerId, commandId, now)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setSerialConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_SERIAL);

            return Mono.fromCompletionStage(
                    () -> session.executeAsync(bound))
                .map(AsyncResultSet::wasApplied);
        });
    }

    public Mono<Boolean> payIfUnchanged(
            UUID orderId, long expectedVersion,
            UUID commandId, Instant now) {
        return Mono.defer(() -> {
            if (expectedVersion == Long.MAX_VALUE) {
                return Mono.error(new IllegalArgumentException(
                    "Version overflow"));
            }
            BoundStatement bound = payIfVersion.bind(
                    expectedVersion + 1, commandId, now,
                    orderId, expectedVersion)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setSerialConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_SERIAL);

            return Mono.fromCompletionStage(
                    () -> session.executeAsync(bound))
                .map(AsyncResultSet::wasApplied);
        });
    }
}
~~~

**Giải thích chính xác:**

1. `CqlSession` và `PreparedStatement` có **vòng đời dài**, thường là bean Spring; không tạo/đóng session mỗi request.
2. `Mono.defer(...)` trì hoãn việc **tạo bound statement và gửi request** đến lúc có subscription.
3. `Mono.fromCompletionStage(...)` nhận kết quả bất đồng bộ mà không chặn thread bằng `Future.get()`.
4. `AsyncResultSet.wasApplied()` phân biệt **LWT được áp dụng** với **điều kiện không thỏa**.
5. `setConsistencyLevel(...)` và `setSerialConsistencyLevel(...)` thiết lập regular/serial CL cho statement; giá trị minh họa **phải được đánh giá theo topology**, đặc biệt multi-DC.
6. Nếu `executeAsync(...)` lỗi hoặc timeout, publisher phát **onError**, không tự trả `false`.

**Giả định:** mã dùng Reactor hỗ trợ `Mono.fromCompletionStage(Supplier)`, Java driver 4.x, schema đã có và cấu hình session/driver đúng. Khả năng API cụ thể cần đối chiếu đúng phiên bản Spring Boot, Spring Data Cassandra và Reactor của dự án.

### 5.1. Một subscription là một lần thực thi

~~~java
Mono<Boolean> operation =
    gateway.createIfAbsent(orderId, customerId, commandId, now);

// Mỗi subscribe mới có thể gửi một conditional write mới.
// Đây là ví dụ ý tưởng, không nên tự subscribe trong service:
~~~

`Mono` trong ví dụ là **cold publisher** do `defer`. Khi **retry**, **repeat**, hoặc có **hai subscriber độc lập**, logic có thể thực thi nhiều lần. Việc LWT thứ hai trả `false` không chứng minh lần thứ nhất đã thất bại; có thể lần đầu đã tạo hàng rồi response bị mất.

Không tự gọi `subscribe()` bên trong service để “chạy nền” rồi trả ngay một `Mono.just(success)`: điều đó làm mất đường truyền lỗi/cancellation và làm HTTP response không còn phản ánh kết quả Cassandra.

## 6. Kết quả LWT: true, false và onError là ba nhánh khác nhau

Với câu `INSERT ... IF NOT EXISTS`:

| Tín hiệu của publisher | Kết quả CQL | Ý nghĩa nghiệp vụ có thể dùng |
| --- | --- | --- |
| `onNext(true)` rồi `onComplete` | `[applied] = true` | Hàng được tạo mới |
| `onNext(false)` rồi `onComplete` | `[applied] = false` | Hàng đã tồn tại; có thể cần phân biệt conflict và idempotent replay |
| `onError(timeout)` | Không có cờ kết quả hợp lệ | Trạng thái ghi có thể chưa rõ |
| `onError(invalid query)` | Lỗi schema/CQL | Lỗi lập trình/triển khai, không phải tranh chấp |
| Subscription bị cancel | Consumer không còn đợi kết quả | Không chứng minh request chưa commit |

Nếu trả `Mono<Boolean>`, **`false` vẫn là một giá trị được emit**. Nó **không phải `Mono.empty()`**.

**Sai:**

~~~java
return gateway.createIfAbsent(orderId, customerId, commandId, now)
    .filter(Boolean::booleanValue)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Database returned no result")));
~~~

Đoạn này làm mất thông tin “điều kiện không thỏa” bằng cách biến `false` thành empty rồi đổi thành lỗi kỹ thuật giả.

**Đúng hướng hơn:**

~~~java
return gateway.createIfAbsent(orderId, customerId, commandId, now)
    .map(applied -> applied
        ? CreateOrderOutcome.CREATED
        : CreateOrderOutcome.ALREADY_EXISTS);
~~~

`CreateOrderOutcome` là enum nghiệp vụ do service định nghĩa. Nếu cần xử lý timeout, phải dùng một nhánh lỗi riêng và có chính sách đối soát; không dùng `onErrorReturn(false)`.

### 6.1. Không phụ thuộc vào số hàng/Row như một SELECT

Kết quả conditional mutation có cờ `[applied]`. Với Java driver 4.x, `AsyncResultSet.wasApplied()` là API trực tiếp thể hiện ngữ nghĩa này. Những cột bổ trợ khi điều kiện thất bại có thể khác nhau theo CQL/phiên bản; đừng dùng `currentPage().iterator().next()` như một entity luôn có đủ cột `version`, `state`, `customer_id`.

Khi muốn giải thích conflict cho client, có thể **đọc lại** hàng hiện tại bằng query theo partition key; lưu ý readback là một thao tác riêng có thể thấy trạng thái mới hơn do writer khác.

## 7. LWT không cần một chuỗi đọc–ghi ở client

Anti-pattern reactive:

~~~java
return repository.findById(orderId)
    .flatMap(order -> {
        if (!"CREATED".equals(order.getState())) {
            return Mono.error(new IllegalStateException("Not creatable"));
        }
        // Dù có điều kiện ở Java, save này vẫn có thể ghi đè
        // cập nhật vừa được một instance khác thực hiện.
        return repository.save(order);
    });
~~~

Vấn đề không nằm ở `flatMap`, mà ở **khoảng trống giữa lần đọc và lần ghi**. Request khác có thể thay đổi state sau khi service kiểm tra.

Một câu CQL thực hiện điều kiện tại Cassandra:

~~~sql
UPDATE app_ks.orders_by_id
SET state = 'PAID', version = ?, updated_at = ?
WHERE order_id = ?
IF version = ? AND state = 'CREATED';
~~~

Đây là **CAS/optimistic concurrency**. LWT có thêm chi phí Paxos nhưng bảo vệ quy tắc “chỉ trả tiền nếu trạng thái/phiên bản còn khớp” trên dữ liệu mục tiêu.

**Chú ý:** một số phiên bản Spring Data Cassandra hỗ trợ `@Version`/optimistic locking trên entity. Khi sử dụng, cần xác minh write path có thực hiện conditional write đúng, phát loại exception nào và reactive repository có hành vi gì. Không mặc định một field tên `version` hoặc một `Mono<OrderRow>` đã mang lại CAS.

## 8. Batch CQL là gì và khác LWT ở đâu?

CQL `BATCH` gom nhiều mutation vào một câu lệnh batch. Ví dụ hai sự kiện trong **cùng partition `order_id`**:

~~~sql
BEGIN BATCH
    INSERT INTO app_ks.order_events_by_order
        (order_id, event_no, event_id, event_type, occurred_at)
    VALUES (?, ?, ?, 'OrderCreated', ?);

    INSERT INTO app_ks.order_events_by_order
        (order_id, event_no, event_id, event_type, occurred_at)
    VALUES (?, ?, ?, 'PaymentRequested', ?);
APPLY BATCH;
~~~

Batch không tự có điều kiện “chỉ chèn nếu event chưa tồn tại”; các `INSERT` thường vẫn mang ngữ nghĩa **upsert** đối với khóa trùng. **LWT** đưa thêm một quyết định `IF` dựa trên dữ liệu hiện tại.

| Thuộc tính | Ghi thường | Batch không điều kiện | Conditional write/LWT |
| --- | --- | --- | --- |
| Kiểm tra `IF version = ?` tại commit | Không | Không tự có | **Có** |
| Gộp nhiều mutation một cách tường minh | Không | **Có** | Có thể dùng conditional batch theo giới hạn CQL |
| Dùng thêm Paxos vì CAS | Không | Không chỉ vì có batch | **Có** |
| Isolation ACID đa bảng/partition như RDBMS | Không | **Không** | **Không** |
| Có thể gặp timeout với outcome chưa rõ | Có | Có | Có |
| Tự đảm bảo side effect HTTP/email | Không | Không | Không |

**Không nên** dùng batch như công cụ tối ưu throughput tổng quát cho hàng nghìn mutation trên nhiều partition. Với Cassandra, các write không điều kiện phân tán thường xử lý tốt khi gửi riêng với concurrency có kiểm soát; batch nên xuất phát từ **một yêu cầu atomicity cụ thể**, đặc biệt trong một partition.

## 9. LOGGED, UNLOGGED và COUNTER batch

### 9.1. LOGGED batch

`BEGIN LOGGED BATCH` (hoặc batch logged theo cú pháp/default của phiên bản) dùng cơ chế **batchlog** khi cần đảm bảo các mutation của batch đa partition được áp dụng theo khả năng/điều kiện mà Cassandra hỗ trợ. Khi coordinator gặp sự cố giữa quá trình, batchlog có thể giúp các mutation còn lại được **replay**.

~~~sql
BEGIN LOGGED BATCH
    INSERT INTO app_ks.orders_by_id
        (order_id, state, version)
    VALUES (?, 'CREATED', 1);

    INSERT INTO app_ks.order_events_by_order
        (order_id, event_no, event_id, event_type)
    VALUES (?, 1, ?, 'OrderCreated');
APPLY BATCH;
~~~

Ví dụ trên đụng **hai bảng/partition**. Logged batch cung cấp semantics atomicity theo Cassandra, nhưng **không bảo đảm isolation**: một reader khác có thể quan sát mutation ở bảng này trước khi mutation ở bảng kia trở nên thấy được. Không có một transaction snapshot ngăn các request khác xen vào ở mọi bảng.

Điều phải hiểu:

- Batchlog là cơ chế **phục hồi các mutation của batch**, không phải một khóa transaction phân tán bao trùm tất cả bảng.
- “Atomic” không nên được diễn giải thành “mọi đọc ở mọi CL, mọi DC đều thấy tất cả mutation cùng đúng một thời điểm”.
- Khi client timeout, batch có thể vẫn đang được áp dụng hoặc sẽ được replay. **Không biết chắc đã commit hay chưa** chỉ từ timeout.
- Batch nhiều partition và batchlog có thể tốn chi phí network/CPU/latency; không nên dùng cho mọi bulk import.

### 9.2. UNLOGGED batch

`BEGIN UNLOGGED BATCH` không dùng batchlog cho khả năng khôi phục đa partition theo cách logged batch.

~~~sql
BEGIN UNLOGGED BATCH
    INSERT INTO app_ks.order_events_by_order
        (order_id, event_no, event_id, event_type)
    VALUES (?, 1, ?, 'OrderCreated');

    INSERT INTO app_ks.order_events_by_order
        (order_id, event_no, event_id, event_type)
    VALUES (?, 2, ?, 'PaymentRequested');
APPLY BATCH;
~~~

Hai mutation trên có cùng `order_id`, tức cùng **partition logic của cùng bảng**; đây là trường hợp batch một partition thích hợp để xem xét. Ngược lại, **UNLOGGED batch trên nhiều partition không có bảo đảm khôi phục all-or-none của logged batch**.

Trong một partition, Cassandra có quy tắc atomicity/visibility mạnh hơn đối với batch, nhưng vẫn không nên suy ra một transaction nhiều lần đọc và nhiều lần ghi với isolation/rollback như trong RDBMS.

### 9.3. COUNTER batch

Counter có cú pháp/batch type riêng:

~~~sql
BEGIN COUNTER BATCH
    UPDATE app_ks.counter_table
    SET total = total + 1
    WHERE id = ?;
APPLY BATCH;
~~~

Đây là **mẫu CQL khái niệm**; `counter_table` phải được định nghĩa phù hợp với CQL counter (không trộn các cột thường tùy ý). Không dùng counter batch để thay thế logged/unlogged batch của những cột không phải counter. Counter còn có đặc tính riêng về retry/idempotency và không thích hợp để suy ra “exactly once” khi client timeout.

## 10. Phạm vi partition là ranh giới thiết kế quan trọng

Một khái niệm rất dễ bị nhầm:

~~~text
orders_by_id:            partition key = order_id X
order_events_by_order:   partition key = order_id X
~~~

Hai giá trị khóa **bằng nhau** nhưng **hai bảng khác nhau**. Không nên dùng câu “cùng order ID nên mọi conditional batch trên hai bảng chắc chắn là single-partition LWT”. Conditional CQL có những giới hạn cụ thể theo **partition và statement** mà Cassandra kiểm tra.

Các nguyên tắc:

1. Một batch **tất cả mutation trong cùng partition của một bảng** thường là dạng dễ kiểm soát nhất.
2. Logged batch **nhiều partition** có atomicity phục hồi theo batchlog nhưng **không có isolation SQL** và có chi phí bổ sung.
3. Unlogged batch **nhiều partition** không cho atomicity phục hồi như logged batch.
4. **Conditional batch** phải tuân thủ các hạn chế CQL/LWT, đặc biệt yêu cầu điều kiện/mutation liên quan đến **cùng partition theo quy tắc của phiên bản Cassandra**; không dùng nó như transaction CAS tùy ý xuyên nhiều partition.
5. Những hiệu ứng **ngoài Cassandra** như HTTP request, message broker và email không thể đưa vào một CQL batch.

**Quy tắc học tập:** nếu thiết kế yêu cầu `IF` trên một hàng ở bảng A, đồng thời buộc bảng B, queue C và email D phải cùng atomic, hãy coi đó là **workflow phân tán**, không phải điều đã được giải quyết bằng batch.

## 11. Conditional batch: điều kiện quyết định nhóm mutation

Trong trường hợp hỗ trợ, conditional batch có thể dùng một hoặc nhiều điều kiện `IF` trên các mutation **cùng partition phù hợp**. Ví dụ minh họa hai bước của một workflow nằm trong **cùng bảng `order_steps_by_order`**, để thấy cách kiểm tra trạng thái trước khi thay đổi một nhóm row:

~~~sql
CREATE TABLE app_ks.order_steps_by_order (
    order_id uuid,
    step_no int,
    state text,
    version bigint,
    PRIMARY KEY ((order_id), step_no)
);
~~~

Một mẫu biểu đạt ý định:

~~~sql
BEGIN BATCH
    UPDATE app_ks.order_steps_by_order
    SET state = 'DONE', version = 2
    WHERE order_id = ? AND step_no = 1
    IF version = 1;

    UPDATE app_ks.order_steps_by_order
    SET state = 'READY', version = 2
    WHERE order_id = ? AND step_no = 2
    IF version = 1;
APPLY BATCH;
~~~

**Đây là ví dụ để thử trong môi trường Cassandra phù hợp.** Phải đảm bảo cả hai `order_id` được bind **cùng một giá trị** và hai hàng đã có `version = 1`. Kiểm tra cú pháp/hỗ trợ conditional statements trong batch theo **phiên bản Cassandra thực tế**; nếu server từ chối một tổ hợp CQL, không cố sửa bằng cách rải mutation sang nhiều partition hoặc bỏ điều kiện.

Mục tiêu của conditional batch hợp lệ là **đưa điều kiện và nhóm mutation vào cùng quyết định CQL**, không phải viết:

~~~java
// Không tương đương với atomic CAS:
return checkVersion(orderId)
    .flatMap(valid -> valid
        ? updateFirstStep(orderId).then(updateSecondStep(orderId))
        : Mono.empty());
~~~

Trong đoạn reactive trên, hai bước vẫn là **hai request độc lập**. Một writer khác có thể thay đổi state sau `checkVersion` hoặc giữa hai update.

### 11.1. [applied] của conditional batch

Với conditional batch hợp lệ, client cần kiểm tra **kết quả điều kiện của cả batch**; nếu một điều kiện không thỏa, conditional mutation group theo ngữ nghĩa Cassandra không được áp dụng như trường hợp thành công.

Sử dụng API `wasApplied()` khi driver trả kết quả LWT. Không lấy việc `Mono<Void>` hoàn tất hoặc không ném exception làm bằng chứng rằng điều kiện đã thỏa. Ngược lại, false là **conflict/kết quả điều kiện**, không phải timeout.

Phải xác minh cấu hình CQL, giới hạn partition, khả năng combine conditional/regular statements và metadata trả về đúng **phiên bản Cassandra**. Không trộn một ví dụ conditional batch của một version với giả định mọi version hỗ trợ giống nhau.

## 12. Batch qua Java driver rồi bọc thành Mono

Java driver 4.x hỗ trợ `BatchStatement` và các `BoundStatement` đã chuẩn bị. Ví dụ batch ghi **hai event trong một partition**:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import java.util.UUID;
import reactor.core.publisher.Mono;

public final class ReactiveEventBatchGateway {
    private final CqlSession session;
    private final PreparedStatement insertEvent;

    public ReactiveEventBatchGateway(CqlSession session) {
        this.session = session;
        this.insertEvent = session.prepare(
            "INSERT INTO app_ks.order_events_by_order " +
            "(order_id, event_no, event_id, event_type) " +
            "VALUES (?, ?, ?, ?)"
        );
    }

    public Mono<Void> appendInitialEvents(
            UUID orderId, UUID createdEventId,
            UUID requestedEventId) {
        return Mono.defer(() -> {
            BatchStatement batch = BatchStatement
                .builder(DefaultBatchType.UNLOGGED)
                .addStatement(insertEvent.bind(
                    orderId, 1L, createdEventId, "OrderCreated"))
                .addStatement(insertEvent.bind(
                    orderId, 2L, requestedEventId, "PaymentRequested"))
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .build();

            return Mono.fromCompletionStage(
                    () -> session.executeAsync(batch))
                .then();
        });
    }
}
~~~

Trong trường hợp này, **hai mutation thuộc cùng bảng và cùng partition `order_id`**. Batch không chứa `IF`, vì vậy ví dụ **không tự chống ghi lại event_no=1/2** nếu request bị retry hoặc một writer khác dùng cùng khóa.

**Điểm kỹ thuật:**

- `BatchStatement.builder(DefaultBatchType.UNLOGGED)` là API Java driver 4.x; đối chiếu phiên bản chính xác.
- `Mono.defer(...)` bảo đảm mỗi subscription xây batch riêng, không chia sẻ đối tượng bind chứa dữ liệu của request khác.
- `Mono.fromCompletionStage(() -> session.executeAsync(batch))` thực thi bất đồng bộ.
- `then()` bỏ payload kết quả và trả `Mono<Void>`, **phù hợp chỉ khi không cần một cờ `[applied]` nghiệp vụ**.
- Batch không điều kiện không có cờ CAS false cần phân nhánh; nếu đang dùng **conditional batch**, không được bỏ kết quả bằng `then()` mà không kiểm tra `wasApplied()`.
- Các event ID phải **ổn định cho một command** nếu cần retry idempotent; UUID sinh lại mỗi subscription có thể gây duplicate theo khóa khác.

**Lưu ý:** batch chỉ gửi một lệnh tổng hợp nhưng **không có nghĩa chạy nhanh hơn một nhóm async writes riêng** trong mọi workload. Đo latency và contention trước khi tối ưu.

## 13. Một Mono chứa hai bước không tương đương một CQL batch

So sánh ba cách:

~~~java
// A: Hai request độc lập, thực hiện theo thứ tự.
return gateway.updateOrder(orderId)
    .then(gateway.insertEvent(orderId));

// B: Hai request độc lập, có thể được khởi tạo cạnh nhau.
return Mono.when(
    gateway.updateOrder(orderId),
    gateway.insertEvent(orderId)
);

// C: Một request CQL batch đã được chuẩn bị/xây dựng.
return gateway.executeCqlBatch(orderId);
~~~

Đây là pseudocode diễn đạt cấu trúc; các method gateway giả định đã có. Sự khác biệt:

| Cách | Điều phối ở client | Bảo đảm dữ liệu |
| --- | --- | --- |
| A: `then` | Bước B được subscribe sau khi A hoàn tất | Không rollback A nếu B lỗi |
| B: `Mono.when` | Các nguồn có thể chạy đồng thời | Không atomic, nếu một nguồn lỗi nguồn kia có thể đã ghi |
| C: một CQL batch | Một batch được gửi đến Cassandra | Có semantics batch theo loại và phạm vi; không tự isolation đa partition |

**Nếu A trả onComplete:** thao tác đầu đã hoàn tất theo publisher, không phải một “giao dịch còn mở” cho bước B dùng chung. **Nếu B lỗi:** không có một reactive rollback tự động cho A.

### 13.1. zip không phải khóa giao dịch

~~~java
Mono.zip(
    orderRepository.findById(orderId),
    inventoryRepository.findById(itemId)
).flatMap(tuple -> validateAndWrite(tuple));
~~~

`Mono.zip` kết hợp hai kết quả bất đồng bộ, **không cung cấp snapshot isolation** giữa hai lần đọc. Hai record có thể bị writer khác thay đổi ngay sau đó. Nếu phải bảo vệ việc đặt hàng theo tồn kho, cần thiết kế bất biến theo khóa thích hợp, LWT ở nguồn sự thật hoặc workflow reservation, không dựa vào `zip`.

### 13.2. concatMap chỉ sắp thứ tự trong một subscription

~~~java
return Flux.fromIterable(commands)
    .concatMap(command -> gateway.handle(command))
    .then();
~~~

`concatMap` giữ thứ tự xử lý trong **Flux subscription này**, hữu ích để tránh chạy các command của cùng nguồn song song. Nhưng hai instance ứng dụng hoặc hai subscription khác **vẫn có thể ghi cạnh tranh** trên cùng partition.

Nếu cần thứ tự quyết định toàn cục theo từng order, phải dùng **một cơ chế phân phối single-writer theo aggregate** hoặc **CAS/version**, không xem `concatMap` là khóa toàn cluster.

## 14. Reactive transaction abstraction không tự tạo transaction Cassandra

Trong hệ sinh thái Spring, `@Transactional` và `TransactionalOperator` có ý nghĩa khi tồn tại **transaction manager phù hợp** và resource manager hỗ trợ transaction tương ứng. Cassandra không cung cấp giao dịch relational ACID đa bảng/partition thông thường.

Không được suy:

~~~java
@Transactional
public Mono<Void> pay(UUID orderId) {
    return updateOrder(orderId)
        .then(appendEvent(orderId))
        .then(sendEmail(orderId));
}
~~~

thì cả ba bước tự động rollback cùng nhau. Không có transaction manager nào biến email thành thao tác nằm trong Cassandra commit, và không phải Spring Data Cassandra reactive operation nào cũng tham gia một transaction Cassandra tổng quát.

**Cách đánh giá đúng:**

1. Thao tác nào có thể diễn đạt bằng **một conditional CQL statement** trên khóa thích hợp?
2. Những mutation nào thực sự thuộc **một batch CQL hợp lệ**, cần semantics nào?
3. Những bước nào nằm **ngoài ranh giới nguyên tử**? Thiết kế retry/idempotency và đối soát.
4. Tầng Spring có hỗ trợ rõ một cơ chế transaction phù hợp không? Nếu không, **đừng tuyên bố rollback đa bước** chỉ vì annotation.

## 15. Phân biệt “có kết quả lỗi” và “đã ghi một phần”

Reactive chain có thể phát lỗi từ nhiều điểm:

~~~text
payWithCas(...)
    |
    +-- applied = false  -> conflict nghiệp vụ
    |
    +-- applied = true   -> tiếp tục appendEvent(...)
                                 |
                                 +-- success -> hoàn thành workflow
                                 |
                                 +-- timeout/error -> trạng thái event chưa rõ,
                                                     CAS trước đã áp dụng
~~~

Đoạn này minh họa một workflow gồm **hai statement riêng**, không phải conditional batch.

Một implementation đơn giản:

~~~java
public Mono<PaymentOutcome> pay(
        UUID orderId, long expectedVersion,
        UUID commandId, Instant now) {
    return casGateway.payIfUnchanged(
            orderId, expectedVersion, commandId, now)
        .flatMap(applied -> {
            if (!applied) {
                return Mono.just(PaymentOutcome.CONFLICT);
            }
            return eventGateway.appendPaidEvent(
                    orderId, commandId, now)
                .thenReturn(PaymentOutcome.ACCEPTED);
        });
}
~~~

Ví dụ giả định `PaymentOutcome`, `casGateway` và `eventGateway` đã được định nghĩa; event ID/command ID phải ổn định. **Nếu bước append event lỗi**, method phát onError nhưng **state có thể đã là `PAID`**. Không nên đặt toàn bộ lỗi vào một enum `FAILED_NO_CHANGES`, vì không đúng sự thật.

**Đây chính là lý do cần phân biệt:**

- **Committed source-of-truth:** nơi quyết định nghiệp vụ thực sự xảy ra.
- **Downstream projection/event:** các bước cập nhật sau, có thể trễ hoặc lỗi.
- **Outcome trả về client:** không báo “chưa làm gì” chỉ vì bước cuối thất bại.

## 16. Thiết kế nguồn sự thật và quy trình phục hồi

### 16.1. Snapshot là nguồn sự thật

Nếu `orders_by_id` là nguồn sự thật:

1. LWT cập nhật version/state ở bảng chính.
2. Sau `[applied] = true`, tạo một **yêu cầu đồng bộ bền vững** cho bảng timeline hoặc hệ thống khác.
3. Nếu ghi bảng phụ thất bại, có **reconciliation worker** hoặc outbox/handoff được thiết kế để thử lại.
4. Mọi bước sau phải idempotent theo `commandId`/`eventId`.

Một `flatMap` nối hai lệnh không tự tạo **handoff bền vững**. Nếu process chết ngay sau LWT, code reactive chưa kịp phát lệnh thứ hai; cần một thiết kế có khả năng phát hiện và phục hồi trường hợp này.

### 16.2. Event stream là nguồn sự thật

Nếu theo event sourcing, có thể dùng một **event log có thứ tự và cơ chế append an toàn** làm nơi commit command. Snapshot và bảng tra cứu là projection được xây lại từ event.

~~~mermaid
flowchart LR
    A[Command có id ổn định] --> B[Validate state/version]
    B --> C[Commit event theo cơ chế CAS/sequence an toàn]
    C --> D[Event stream: nguồn sự thật]
    D --> E[Projector orders_by_id]
    D --> F[Projector timeline/search]
    E --> G[API đọc snapshot có thể trễ]
~~~

Tuy nhiên:

- Chỉ `INSERT` vào event table không tự bảo đảm **sequence** hay validation nghiệp vụ.
- Đọc `MAX(event_no) + 1` rồi ghi không điều kiện có race condition.
- `IF NOT EXISTS` trên `(order_id, event_no)` chỉ bảo vệ **vị trí khóa đó**, không đảm bảo event ID duy nhất ở mọi sequence.
- Một projector phải xử lý duplicate/replay và checkpoint đúng.
- Read-after-write vào projection có thể trễ, dù Cassandra read CL của bảng snapshot là `LOCAL_QUORUM`.

**Kết luận:** event sourcing là một kiến trúc với nguồn sự thật và giao thức commit, không phải cách đổi tên một bảng batch.

## 17. Timeout và retry: trạng thái có thể chưa xác định

Khi gọi:

~~~java
return Mono.fromCompletionStage(
    () -> session.executeAsync(conditionalStatement));
~~~

một timeout có thể xảy ra **sau khi request đã gửi đến Cassandra**, thậm chí sau khi một số bước đồng thuận/ghi đã xảy ra. Vì vậy:

~~~java
// SAI: mọi lỗi đều biến thành applied=false.
return gateway.payIfUnchanged(...)
    .onErrorReturn(false);
~~~

Đây là lỗi phân loại kết quả. `false` nghĩa là Cassandra **đã trả kết quả điều kiện không thỏa**, còn timeout không cho client bằng chứng tương ứng.

### 17.1. RetryWhen có thể thực thi mutation nhiều lần

~~~java
// Chỉ minh họa vấn đề; không sao chép nguyên xi để retry mọi ghi.
return gateway.createIfAbsent(orderId, customerId, commandId, now)
    .retryWhen(Retry.backoff(3, Duration.ofMillis(100)));
~~~

Vì source là cold publisher, `retryWhen` **resubscribe** và có thể gửi lại cùng mutation. Nếu lần đầu `INSERT IF NOT EXISTS` đã thành công nhưng response mất, lần sau có thể trả `[applied] = false`. Điều đó không có nghĩa command thất bại.

Đối với batch không điều kiện, retry có thể **lặp mutation** hoặc tương tác với timestamp/TTL/counter theo ngữ nghĩa phức tạp. Đối với event append, retry với event ID hoặc sequence mới có thể tạo **duplicate nghiệp vụ**.

**Policy an toàn hơn** phải xét:

1. Loại lỗi nào đáng retry (timeout, unavailable hay lỗi cấu hình)?
2. Mutation có **idempotent** khi thực thi nhiều lần không?
3. Một lần trước có thể đã áp dụng nhưng mất response không?
4. Có `commandId` và record bền vững để **đối chiếu** không?
5. Retry tối đa bao nhiêu lần, backoff và jitter ra sao, có làm hot partition tệ hơn không?

Không viết `retryWhen` vô hạn cho LWT hoặc batch quan trọng chỉ để “thấy thao tác thành công”.

## 18. Cancellation: hủy subscriber không phải rollback

Giả sử HTTP client ngắt kết nối, Reactor nhận `cancel`:

~~~text
T0: client subscribe /pay
T1: driver gửi UPDATE ... IF version = 7 đến Cassandra
T2: client đóng kết nối, subscription bị cancel
T3: Cassandra có thể vẫn đang thực hiện/đã commit LWT
T4: ứng dụng không còn consumer để nhận applied=true
~~~

Cancellation làm consumer ngừng yêu cầu kết quả, và một số API có thể cố hủy future/luồng xử lý. Nó **không bảo đảm Cassandra hủy được request đã đến coordinator** và **không tự rollback mutation đã commit**.

### 18.1. Hậu quả của doOnCancel sai

~~~java
// SAI nếu session là bean dùng chung của toàn ứng dụng.
return gateway.payIfUnchanged(...)
    .doOnCancel(() -> sharedCqlSession.close());
~~~

Một request bị hủy không được đóng tài nguyên dùng chung cho hàng nghìn request khác. `CqlSession` do Spring quản lý theo vòng đời ứng dụng, không theo vòng đời từng subscription.

Nếu workflow quan trọng phải **tiếp tục dù HTTP request đã mất**, cần chuyển nó sang **command/job có trạng thái bền vững** thay vì đơn thuần gọi `subscribe()` và hy vọng nó hoàn tất trong process hiện tại.

### 18.2. Cancellation giữa hai bước

Nếu LWT đã commit rồi subscription bị hủy **trước bước ghi event**, Reactor không tự bù trừ LWT. Một workflow có thể thiếu bước phụ ngay cả khi không có exception nào tới HTTP handler.

Do đó, với bất biến quan trọng, cần persist **ý định công việc tiếp theo** theo cơ chế phù hợp và có worker phục hồi; không để tính đúng đắn phụ thuộc vào việc HTTP client giữ kết nối đến hết mọi thao tác.

## 19. flatMap concurrency, backpressure và tranh chấp LWT

Một `Flux` xử lý nhiều command:

~~~java
return Flux.fromIterable(commands)
    .flatMap(command -> gateway.process(command))
    .then();
~~~

`flatMap` có thể cho phép **nhiều thao tác đang chạy đồng thời**. Nếu `commands` chứa nhiều cập nhật **cùng orderId**, các LWT có thể tranh chấp cùng partition và tạo nhiều `[applied] = false`, latency tăng hoặc timeout.

Một số lựa chọn:

~~~java
// Giữ thứ tự trong một Flux subscription.
return Flux.fromIterable(commands)
    .concatMap(command -> gateway.process(command))
    .then();
~~~

hoặc:

~~~java
// Giới hạn mức song song cho các command độc lập.
int maxConcurrency = 8;
return Flux.fromIterable(commands)
    .flatMap(command -> gateway.process(command),
             maxConcurrency)
    .then();
~~~

**Giới hạn quan trọng:** `concatMap` chỉ tuần tự hóa **một luồng**; nó không ngăn những instance/consumer khác sửa cùng partition. Nếu cần giữ thứ tự theo aggregate xuyên các instance, phải thiết kế key routing/single-writer, queue partitioning hoặc CAS/version.

Reactive **backpressure** giúp giới hạn demand và bộ nhớ ở phía consumer, nhưng không thay thế giới hạn số CQL request đang bay, mức tải cluster và chính sách retry. Đo p95/p99 latency, in-flight requests, CAS conflicts và tải partition để điều chỉnh concurrency.

## 20. Paging và LWT không thay thế nhau

Trong Cassandra, **LWT** là thao tác ghi có điều kiện; **paging** là kỹ thuật đọc dần nhiều hàng. Hai nhu cầu khác nhau:

~~~sql
SELECT event_no, event_id, event_type
FROM app_ks.order_events_by_order
WHERE order_id = ? AND event_no >= ?
LIMIT 100;
~~~

Một nguồn `Flux<OrderEvent>` được tạo từ reactive repository/driver có thể phát nhiều row, nhưng:

- `take(10)` dừng consumer sau 10 phần tử **không tự sửa** CQL thành `LIMIT 10`.
- Cassandra/driver có thể đã fetch trang đầu hoặc prefetch trước khi cancel.
- `page size` quy định kích thước từng lần fetch, **không phải tổng `LIMIT`**.
- `Paging state` phải gắn với cùng query shape, bind values và ngữ cảnh xác thực.
- Không đọc toàn bộ lịch sử vào `List` rồi cắt trang ở JVM.

Khi API biết trước số hàng cần trả, ưu tiên **projection và LIMIT trên server**, đọc đúng partition/clustering range. Khi xử lý stream lâu dài, kiểm soát demand, page fetch, cancellation và giới hạn số row scan.

## 21. Một reactive workflow có đối chiếu trạng thái

Xét một yêu cầu thanh toán có command ID cố định:

~~~text
requestId / commandId = C
orderId = X
expectedVersion = 7
~~~

Một thiết kế có thể dùng kiểu kết quả rõ ràng:

~~~java
public enum PaymentOutcome {
    APPLIED,
    REPLAYED,
    CONFLICT,
    PENDING_RECONCILIATION
}
~~~

**Ý định**:

~~~mermaid
flowchart TD
    A[Nhận command C cho order X] --> B[LWT IF version=7 AND state=CREATED]
    B --> C{Kết quả?}
    C -->|true| D[Đã commit quyết định ở nguồn sự thật]
    C -->|false| E[Đọc/đối chiếu command ID]
    C -->|timeout| F[Không khẳng định chưa commit]
    D --> G[Persist/đảm bảo handoff cho projection/event]
    E --> H{Cùng command đã xử lý?}
    H -->|Có| I[REPLAYED]
    H -->|Không| J[CONFLICT]
    F --> K[Đối soát bằng command ID/version]
    G --> L[Hoàn tất hoặc PENDING theo workflow]
~~~

**Không nên** cài đặt sơ đồ bằng cách “CAS true → gọi message broker” rồi tuyên bố nguyên tử. Handoff phải có cơ chế bền vững; nếu không có, báo cáo rõ eventual inconsistency/rủi ro mất sự kiện và thiết kế phục hồi.

### 21.1. last_command_id là một ví dụ hạn chế

Một cột `last_command_id` trên snapshot giúp đối chiếu một lệnh gần nhất, nhưng sau vài mutation khác nó có thể bị thay thế. Nếu cần deduplicate nhiều command trong thời gian dài, phải có **idempotency ledger/event log** lưu kết quả theo command ID cùng quy trình giữ/đọc dữ liệu.

Khi dùng nhiều bảng cho ledger và snapshot, lại xuất hiện bài toán nguyên tử/handoff. Đừng mặc định thêm một bảng ID là có transaction nhiều partition; phải xác định nguồn sự thật của việc chấp nhận command.

## 22. Kiểm thử bằng StepVerifier: đúng tín hiệu reactive

Ở tầng unit test, có thể kiểm tra service phân biệt kết quả:

~~~java
import static org.mockito.Mockito.*;
import java.time.Instant;
import java.util.UUID;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void createReturnsConflictWhenConditionNotApplied() {
    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    UUID commandId = UUID.randomUUID();
    Instant now = Instant.parse("2026-11-25T09:00:00Z");

    when(casGateway.createIfAbsent(
        orderId, customerId, commandId, now))
        .thenReturn(Mono.just(false));

    StepVerifier.create(service.create(
            orderId, customerId, commandId, now))
        .expectNext(CreateOrderOutcome.ALREADY_EXISTS)
        .verifyComplete();
}
~~~

Ví dụ giả định JUnit 5, Mockito, `service` và `casGateway` được tạo trong test fixture. Nó chứng minh **ánh xạ false → conflict ở tầng service**, không chứng minh Paxos và CQL query được Cassandra chấp nhận.

Test lỗi khác:

~~~java
@Test
void timeoutIsNotRewrittenAsConditionFalse() {
    Mono<Boolean> failed = Mono.error(
        new RuntimeException("Simulated driver timeout"));

    StepVerifier.create(failed)
        .expectErrorMatches(error ->
            error.getMessage().contains("timeout"))
        .verify();
}
~~~

Ở test thật, cần dùng một loại exception đại diện driver hoặc mock chuyên biệt; đừng bắt mọi RuntimeException rồi áp dụng chính sách “chưa ghi”.

### 22.1. Test cold publisher: subscribe mới thực thi

~~~java
@Test
void deferDoesNotExecuteUntilSubscription() {
    AtomicInteger calls = new AtomicInteger();

    Mono<String> lazy = Mono.defer(() -> {
        calls.incrementAndGet();
        return Mono.just("ok");
    });

    assertEquals(0, calls.get());

    StepVerifier.create(lazy)
        .expectNext("ok")
        .verifyComplete();

    assertEquals(1, calls.get());
}
~~~

Ví dụ cần import JUnit assertions, `AtomicInteger`, Reactor `Mono`/`StepVerifier`. Với driver thật, việc khởi tạo `PreparedStatement` trong constructor có thể thực hiện trước subscription, nhưng **request `executeAsync` trong `Mono.defer`** chỉ bắt đầu khi subscription diễn ra.

## 23. Integration test với Cassandra: chứng minh ranh giới thật

Một test tích hợp nên chạy trên Cassandra thử nghiệm với topology/schema phù hợp, chẳng hạn qua **Testcontainers** hoặc một cluster test được quản lý. Những trường hợp cần có:

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Hai reactive subscriber tạo cùng `order_id` bằng `IF NOT EXISTS` | Chỉ một nhận `wasApplied() = true` khi không có tác động ngoài |
| Hai writer cùng expected version | Chỉ conditional write được chấp nhận theo trạng thái được bảo vệ |
| Một `Mono.just(false)` | Service không biến false thành empty/timeout |
| LWT timeout | Không tự trả conflict; có chính sách trạng thái chưa xác định |
| Hai mutation trong cùng partition qua batch | Kết quả/bảo đảm theo loại batch được kiểm thử |
| Logged batch hai partition | Không mặc định có isolation; quan sát trạng thái và đo chi phí |
| Unlogged batch nhiều partition | Không được tuyên bố bảo đảm atomicity phục hồi như logged batch |
| Conditional batch cùng partition | Xác minh CQL hợp lệ, điều kiện và `wasApplied()` |
| Reactive chain hai câu độc lập | Có thể còn bước đầu sau khi bước hai lỗi |
| Cancel trước response | Không suy từ cancel rằng Cassandra đã rollback |
| Retry sau timeout | Command ID ổn định; không tạo duplicate nghiệp vụ |
| `flatMap` với nhiều command cùng key | Đo contention/latency và mức conflict |
| Hai DC với LOCAL_SERIAL | Kiểm tra phạm vi đồng thuận và read CL theo topology |
| Paging timeline | Đủ partition key, giới hạn số row và xử lý page đúng |

### 23.1. Cách kiểm thử lỗi giữa hai bước

1. Tạo hàng `orders_by_id` trạng thái `CREATED`, version 7.
2. Dùng LWT để chuyển thành `PAID`, version 8, nhận `[applied] = true`.
3. Trong test gateway, cố ý làm bước `appendPaidEvent` trả `Mono.error(...)` **trước khi gửi CQL**.
4. Xác nhận reactive workflow phát onError, **nhưng hàng orders_by_id vẫn `PAID`**.
5. Thử subscription lại với **command ID cố định**. Nếu CAS trả false, đối chiếu command ID và trạng thái thay vì tuyên bố payment thất bại.
6. Kích hoạt cơ chế reconciliation giả lập để ghi event nếu thiếu, tránh phát hai event nghiệp vụ.

Test này chứng minh rõ rằng **`then`/`flatMap` không cung cấp rollback toàn workflow**.

### 23.2. Cách kiểm thử conditional batch

1. Tạo hai hàng step 1 và 2 **trong cùng partition `order_id`** với version 1.
2. Thực thi conditional batch hợp lệ của phiên bản Cassandra trong lab.
3. Xác nhận `wasApplied() == true` khi mọi điều kiện thỏa.
4. Thay version của một hàng rồi thực thi lại; xác nhận `false` và trạng thái không bị thay như một lần conditional batch thành công.
5. Thử cố ý chia mutation sang partition khác trong môi trường test và ghi nhận lỗi/giới hạn CQL thực tế; **không “sửa” bằng cách bỏ IF**.

Test cần được viết theo **phiên bản Cassandra và protocol đang chạy**, bởi cú pháp/giới hạn của conditional batch có thể khác; không dựa vào mock để chứng minh atomicity.

### 23.3. Test retry và cancellation có giới hạn

- Dùng `StepVerifier.withVirtualTime(...)` cho logic delay/backoff khi phù hợp; nó không mô phỏng chính xác Paxos hoặc replica.
- Khi inject lỗi sau khi request đã gửi, chỉ làm trên cluster test và ghi rõ giai đoạn lỗi.
- Đừng dùng một test pass duy nhất để kết luận “không thể ghi một phần” trong mọi topology.
- Không chạy network partition/fault injection/stress trên production.
- Thu thập thông tin CL, serial CL, RF, số node, Cassandra/driver version và thời gian lỗi để diễn giải kết quả.

## 24. Vận hành: các chỉ số cần theo dõi

| Chỉ số | Câu hỏi |
| --- | --- |
| P50/P95/P99 latency của LWT | CAS có nằm trong SLA API không? |
| Tỷ lệ `[applied] = false` | Có nhiều command tranh chấp hoặc retry sai không? |
| Timeout/Unavailable | Replica/topology có đáp ứng CL và serial CL không? |
| Batch size (statements/bytes/partitions) | Có batch đa partition quá lớn không? |
| Batchlog/replay signals | Có lỗi node hoặc áp lực phục hồi logged batch không? |
| Concurrent requests / in-flight statements | Reactor có gửi quá nhiều mutation cùng lúc không? |
| Retry rate và command dedup | Một lỗi đang tạo thành bão retry/duplicate không? |
| Projection lag | Bảng phụ đã bắt kịp source-of-truth chưa? |
| Cancellation và disconnect | Client rời đi khi tác vụ nào còn đang chạy? |
| Hot partitions/tombstones | Dữ liệu có gây read/write amplification không? |
| Cross-DC latency/failover | LWT local có còn đúng với yêu cầu quan sát của business không? |

Những chỉ số này hữu ích hơn một khẳng định chung chung “Reactor nhanh nên batch cũng nhanh”. Với Cassandra, **mô hình partition và đường truy cập dữ liệu** vẫn là yếu tố quyết định phần lớn chi phí.

## 25. Những hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Nối ba `Mono` bằng `then` tạo một transaction.” | Chỉ tạo thứ tự subscription, **không rollback** bước trước |
| “`zip` đọc hai record trong một snapshot.” | Hai request riêng có thể quan sát trạng thái không đồng thời |
| “`concatMap` khóa mọi writer của cluster.” | Nó chỉ tuần tự trong một subscription; không khóa instance khác |
| “`@Transactional` tự rollback email và Cassandra.” | Phải có transaction manager/resource semantics phù hợp; không có ACID toàn workflow |
| “Logged batch giống SQL transaction đa bảng có isolation.” | Có batchlog/atomicity theo Cassandra, **không có isolation đa partition kiểu SQL** |
| “Unlogged batch đa partition cũng được batchlog bảo vệ.” | **Không** |
| “Batch luôn tăng throughput.” | Batch đa partition thường có overhead, không phải công cụ bulk-write chung |
| “Dùng `IF` trong batch là có thể kiểm tra hai partition tùy ý.” | Conditional batch chịu giới hạn partition/CQL/phiên bản |
| “`Mono<Void>` hoàn thành nghĩa CAS `[applied] = true`.” | Nếu đã bỏ result, mất cờ CAS; phải đọc `wasApplied()` |
| “`false` của LWT là exception.” | Đây là kết quả điều kiện hợp lệ |
| “Timeout nghĩa là chưa ghi.” | Mutation/batch có thể đã xảy ra hoặc đang được phục hồi |
| “`retryWhen` không có side effect vì reactive là lazy.” | Resubscribe có thể thực thi mutation lại |
| “Cancel HTTP request rollback lệnh đã gửi.” | Cancellation không phải rollback Cassandra |
| “Một order ID giống nhau ở hai bảng là cùng một partition atomic.” | Hai bảng vẫn có data/partition/mutation riêng |
| “LWT ở bảng chính tự đồng bộ bảng denormalized.” | Cần workflow/outbox/reconciliation |
| “Page size 100 đồng nghĩa LIMIT 100.” | Page size là kích thước đợt fetch; LIMIT giới hạn tổng hàng |

## 26. Bài thực hành tổng hợp

**Đề bài:** xây endpoint reactive `POST /orders/{orderId}/pay`. Hệ thống có nhiều instance Spring Boot, bảng `orders_by_id` là nguồn sự thật; bảng `order_events_by_order` phục vụ timeline.

**Yêu cầu triển khai:**

1. Tạo schema hai bảng theo partition key/query-first như phần 3.
2. Khởi tạo state `CREATED`, version 1; chọn command ID cố định của request.
3. Tạo `ReactiveOrderCasGateway` dùng `CqlSession.executeAsync(...)`, `Mono.defer(...)` và `AsyncResultSet.wasApplied()`.
4. Viết `payIfUnchanged` bằng `IF version = ? AND state = 'CREATED'`.
5. Phân biệt kết quả CAS true/false/onError ở tầng service.
6. Viết một `ReactiveEventBatchGateway` dùng batch trong **cùng partition** cho hai sự kiện thử nghiệm.
7. So sánh batch cùng partition với hai statement độc lập nối bằng `then`; giải thích khác biệt atomicity và thứ tự.
8. Thử một logged batch **đa partition** trong lab; diễn giải giới hạn isolation và chi phí batchlog, không gọi nó là transaction SQL.
9. Với các bước ở **hai bảng khác nhau**, thiết kế một nguồn sự thật và reconciliation worker khi bước phụ thất bại.
10. Tạo hai writer cạnh tranh cùng expected version; kiểm tra chỉ một CAS được áp dụng theo trạng thái ban đầu.
11. Giả lập timeout sau khi gửi lệnh; retry cùng command ID và đối chiếu kết quả, không tự biến `false` thành thất bại của command đầu.
12. Test cancellation từ HTTP; mô tả vì sao không tự rollback và khi nào phải persist background job.
13. Dùng `flatMap(..., concurrency)` để kiểm soát số statement đang chạy; so sánh với `concatMap` và sự cạnh tranh xuyên instance.
14. Kiểm tra các truy vấn đọc event có đủ partition key, clustering restriction, `LIMIT` và paging đúng.
15. Dùng `StepVerifier` cho service signals và integration test trên Cassandra thật cho LWT/batch.
16. Ghi lại latency, conflict rate, timeout, batch size, số partition và projection lag.

**Tiêu chí đạt:** người học mô tả được ranh giới chính xác giữa **Reactor chain**, **conditional CQL/LWT**, **CQL batch** và **workflow nhiều hệ thống**; không tuyên bố nguyên tử khi thiếu cơ sở, không che dấu onError, không retry mù và có đường phục hồi khi các bảng phụ bị trễ.

## 27. Câu hỏi tự kiểm tra

1. Vì sao `Mono.then(...)` không rollback bước trước khi bước sau lỗi?
2. Trong Java driver 4.x, phương thức nào cho biết LWT có được áp dụng khi dùng async result?
3. `onNext(false)` khác `Mono.empty()` và `onError(timeout)` thế nào?
4. Vì sao `Mono.defer(...)` hữu ích khi tạo request CQL cho mỗi subscription?
5. Điều gì có thể xảy ra khi cùng cold `Mono` được subscribe hai lần?
6. Khi nào `IF version = ?` cần thiết dù read/write dùng quorum?
7. Batch `LOGGED` khác `UNLOGGED` về cơ chế batchlog và phục hồi đa partition ra sao?
8. Logged batch đa partition có isolation như SQL transaction không?
9. Vì sao batch một partition thường phù hợp hơn batch hàng nghìn partition để tăng throughput?
10. Conditional batch phải tuân thủ những giới hạn nào về partition và cú pháp?
11. Hai bảng dùng cùng giá trị `order_id` có mặc nhiên được coi là một partition cho CAS xuyên bảng không?
12. `Mono.when(...)` có tự bảo vệ hai mutation chạy đồng thời khỏi ghi một phần không?
13. `Mono.zip(...)` có tạo snapshot nhất quán của hai lần đọc không?
14. `concatMap` có ngăn một service instance khác cập nhật cùng order không?
15. Tại sao không nên dùng `onErrorReturn(false)` cho LWT?
16. Nếu request đầu đã commit nhưng mất response, `retryWhen` có thể cho kết quả gì?
17. Idempotency key cần được cấp và giữ ổn định qua bao nhiêu lần thử?
18. Vì sao cancellation HTTP không phải rollback của Cassandra?
19. Nếu trạng thái chính đã `PAID` nhưng append event thất bại, hệ thống cần cơ chế gì?
20. Event sourcing khác snapshot làm nguồn sự thật ở đâu?
21. Tại sao `take(10)` trên Flux không đồng nghĩa Cassandra chỉ đọc đúng 10 row?
22. Khi nào nên dùng `@Transactional`, và vì sao không được giả định Cassandra reactive có transaction relational đa partition?
23. Unit test với `StepVerifier` chứng minh được gì và không chứng minh được gì về Paxos/batch?
24. Những metrics nào giúp phát hiện batch quá lớn hoặc LWT contention trên hot partition?
25. Một reactive workflow cần làm gì để vẫn hoàn thành được khi client rời đi ngay sau khi bước commit chính thành công?

**Ghi nhớ:** **Reactive chain quy định cách tổ chức bất đồng bộ và thứ tự tiêu thụ; nó không tự tạo giao dịch.** **LWT** giải quyết quyết định có điều kiện bằng CAS/Paxos và phải đọc rõ `[applied]`. **CQL batch** có ngữ nghĩa atomicity theo loại batch, partition và phiên bản Cassandra; logged batch nhiều partition **không cung cấp isolation SQL**, còn conditional batch bị giới hạn về khóa/partition. Khi workflow gồm nhiều statement, bảng hoặc hệ thống, hãy chọn **nguồn sự thật**, dùng **command ID/idempotency**, xác định **các outcome chưa rõ sau timeout/cancel**, và thiết kế **hệ thống phục hồi/đối soát**. Với Spring Data Cassandra, mọi lựa chọn vẫn phải dựa trên partition key, consistency, paging và giám sát hiệu năng phân tán.

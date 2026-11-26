# Timestamp của batch và thứ tự quan sát các thay đổi

Trong **Apache Cassandra**, một câu lệnh `BATCH` gom nhiều `INSERT`, `UPDATE` hoặc `DELETE` thành một request. Nó **không phải vòng lặp thực hiện lần lượt từng câu lệnh** và cũng **không phải transaction SQL có isolation toàn cục**. Hai điểm quan trọng nhất:

- Khi không đặt write timestamp riêng cho từng mutation, **mọi mutation trong một batch mặc định dùng chung một write timestamp**.
- Cassandra bảo đảm **isolation trong phạm vi một partition**, nhưng **logged batch qua nhiều partition không bảo đảm người đọc nhìn thấy mọi thay đổi cùng thời điểm**.

Hệ quả: hai câu `UPDATE` cùng ghi một cell trong một batch **không được ưu tiên theo vị trí của chúng trong văn bản CQL**. Cùng write timestamp sẽ dẫn tới cơ chế hòa giải *last-write-wins* (LWW) với quy tắc xử lý timestamp bằng nhau. Với nhiều partition, các thay đổi có thể được quan sát ở những thời điểm khác nhau, ngay cả khi logged batch cung cấp bảo đảm atomicity theo cơ chế batchlog.

Bài thuộc chương **Batch** của module **SPRING_DATA_CASSANDRA**: truy cập Apache Cassandra bằng entity mapping, repository, `CassandraTemplate`, `CqlTemplate` và truy vấn CQL. Chúng ta sẽ gắn chủ đề timestamp với partition key, consistency, paging, retry, idempotency và hiệu năng trong hệ dữ liệu phân tán.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **write timestamp của batch** (micro giây, metadata LWW) với **cột `timestamp` CQL** (mili giây, dữ liệu nghiệp vụ).
2. Giải thích chính xác vì sao thứ tự các statement trong `BEGIN BATCH` **không phải thứ tự thực thi/ghi đè được bảo đảm**.
3. Phân biệt **LOGGED**, **UNLOGGED**, **COUNTER** batch và giới hạn atomicity/isolation theo partition.
4. Sử dụng `USING TIMESTAMP`, `CassandraBatchOperations.withTimestamp(long)` và Java Driver `BatchStatement`.
5. Đọc `WRITETIME()` để kiểm tra metadata và thiết kế integration test không dựa vào những giả định sai.
6. Chọn mô hình lưu **lịch sử sự kiện theo clustering key** thay vì dùng batch như log có thứ tự.

> **Quy tắc:** CQL BATCH là cơ chế nhóm mutation với những bảo đảm cụ thể, không phải một workflow tuần tự có nhiều bước.

## 2. Thiết kế bảng trước khi viết batch

Xét ứng dụng bán hàng với một đơn gồm nhiều dòng. Bảng đọc theo đơn:

~~~sql
CREATE TABLE order_lines_by_order (
    tenant_id uuid,
    order_id uuid,
    line_id uuid,
    sku text,
    quantity int,
    note text,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, order_id), line_id)
);
~~~

| Cột | Vai trò | Ý nghĩa |
|---|---|---|
| `tenant_id` | Partition key 1 | Tenant |
| `order_id` | Partition key 2 | Đơn hàng |
| `line_id` | Clustering key | Dòng trong đơn |
| `sku`, `quantity`, `note` | Cột thường | Nội dung cần ghi |
| `updated_at` | Cột CQL `timestamp` | Thời điểm nghiệp vụ, **không phải metadata write timestamp** |

Hai dòng có cùng `tenant_id` và `order_id`, khác `line_id`, thuộc **một partition**. Hai `order_id` khác nhau là hai partition khác nhau dù cùng tenant.

~~~text
Partition P1 = (tenant A, order X)
    line L1
    line L2
    line L3

Partition P2 = (tenant A, order Y)
    line L4
    line L5
~~~

Đường đọc hợp lệ:

~~~sql
SELECT line_id, sku, quantity, note, updated_at
FROM order_lines_by_order
WHERE tenant_id = ? AND order_id = ?;
~~~

Một bảng khác để đọc trạng thái đơn:

~~~sql
CREATE TABLE orders_by_id (
    tenant_id uuid,
    order_id uuid,
    customer_id uuid,
    status text,
    updated_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

Bảng `orders_by_id` và `order_lines_by_order` có **đường lưu vật lý khác nhau**. Không vì khóa cùng chứa `tenant_id/order_id` mà suy ra một transaction nhiều bảng có isolation giống SQL.

## 3. Bốn khái niệm phải phân biệt

| Khái niệm | Câu hỏi | Trả lời trong Cassandra |
|---|---|---|
| Batch | Những mutation nào được gửi chung? | Một nhóm DML trong một request |
| Write timestamp | Phiên bản cell nào thắng? | So sánh metadata micro giây và quy tắc LWW |
| Atomicity | Logged batch có bảo đảm cuối cùng hoàn tất tập mutation không? | Có theo batchlog, trong phạm vi tính năng batch |
| Isolation | Reader có thể thấy một phần thay đổi không? | Một partition có isolation; nhiều partition **không có snapshot chung** |

**Atomicity và isolation không đồng nghĩa.** Logged batch nhiều partition có thể được bảo đảm hoàn tất nhờ batchlog, nhưng không có khoảnh khắc quan sát nguyên tử xuyên các partition. Trong một giai đoạn, người đọc có thể thấy partition thứ nhất đã thay đổi trong khi partition thứ hai chưa thấy thay đổi đó.

~~~mermaid
flowchart TD
    A[Client gửi LOGGED BATCH] --> B[Coordinator và batchlog]
    B --> C[Mutation partition P1]
    B --> D[Mutation partition P2]
    C --> E[Reader P1 có thể thấy mới]
    D --> F[Reader P2 có thể còn thấy cũ]
    E --> G[Mutations được hoàn tất và hội tụ]
    F --> G
~~~

Sơ đồ cho thấy **một tình huống có thể xảy ra**, không phải khẳng định mọi batch đều lộ trạng thái trung gian. Consistency, topology và thời điểm read ảnh hưởng việc quan sát thực tế.

### 3.1. Trong một partition

Khi các mutation thuộc **một partition**, Cassandra cung cấp atomicity và isolation ở phạm vi partition. Reader không nên nhận một ảnh chụp chỉ gồm một phần mutation của **cùng partition batch** đã được áp dụng.

### 3.2. Trong nhiều partition

Với logged batch nhiều partition, cơ chế batchlog giúp bảo đảm hoàn tất mutation nhưng **không** cung cấp isolation xuyên partition. Với unlogged batch nhiều partition, nếu có lỗi giữa chừng, một phần mutation có thể đã được áp dụng trong khi phần còn lại không được áp dụng.

## 4. Timestamp mặc định của các mutation trong BATCH

Theo tài liệu CQL của Apache Cassandra, nếu không đặt timestamp riêng trên từng operation, các operations trong một batch được áp dụng với **cùng một timestamp**. Timestamp này có thể được sinh theo chính sách driver/server hoặc được đặt tại cấp batch.

~~~sql
BEGIN BATCH
    UPDATE order_lines_by_order
    SET quantity = 2
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;

    UPDATE order_lines_by_order
    SET note = 'packed'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
APPLY BATCH;
~~~

Nếu hai update nhắm vào **cùng hàng, hai cột khác nhau**, không có writer cạnh tranh, chúng thường tạo các cell `quantity` và `note` có **cùng write timestamp**.

Cùng timestamp **không** có nghĩa `quantity` đã được áp dụng trước `note`, hoặc reader ở partition khác có thể quan sát đồng thời với chúng.

### 4.1. Cột kiểu timestamp khác write timestamp

~~~sql
BEGIN BATCH USING TIMESTAMP 1795597200123000
    UPDATE order_lines_by_order
    SET quantity = 2,
        updated_at = '2026-11-25T09:00:00.123+00:00'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
APPLY BATCH;
~~~

- `1795597200123000`: **write timestamp** của mutation, micro giây từ Unix epoch.
- `2026-11-25T09:00:00.123+00:00`: **giá trị cột `updated_at`**, mili giây khi lưu CQL `timestamp`.
- `WRITETIME(updated_at)`: metadata micro giây của cell `updated_at`, **không phải giá trị cột**.

Hai mốc có thể trùng nhau về instant nếu được chủ động chọn như vậy, nhưng Cassandra **không tự đọc `updated_at` để chọn write timestamp**.

### 4.2. Chuyển thời gian Java đúng đơn vị

~~~java
import java.time.Instant;

public final class WriteTimestamp {
    private WriteTimestamp() {}

    public static long toEpochMicros(Instant value) {
        if (value.getNano() % 1_000 != 0) {
            throw new IllegalArgumentException(
                    "Instant must have microsecond precision");
        }
        return Math.addExact(
                Math.multiplyExact(
                        value.getEpochSecond(), 1_000_000L),
                value.getNano() / 1_000L);
    }
}
~~~

~~~text
2026-11-25T09:00:00.123Z
= 1.795.597.200.123 mili giây
= 1.795.597.200.123.000 micro giây
~~~

**Không truyền thẳng `Instant.toEpochMilli()` vào `USING TIMESTAMP`**. Nếu truyền `1795597200123` thay vì `1795597200123000`, Cassandra hiểu đó là timestamp **rất cũ** và một mutation có vẻ mới có thể thua các bản ghi hiện có.

Tránh cho client không tin cậy cấp timestamp trong tương lai: write timestamp quá lớn có thể che khuất mutation hợp lệ sau đó trên cùng cell.

## 5. USING TIMESTAMP chung của batch

CQL cho phép chọn timestamp tại **`BEGIN BATCH`**:

~~~sql
BEGIN BATCH USING TIMESTAMP 1795597200123000
    UPDATE order_lines_by_order
    SET quantity = 2
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;

    UPDATE order_lines_by_order
    SET note = 'packed'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
APPLY BATCH;
~~~

Hai mutation dùng timestamp chung trong ví dụ. **Không đặt thêm timestamp riêng** cho các statement bên trong khi đã dùng batch-level `USING TIMESTAMP`.

~~~sql
-- VÍ DỤ KHÔNG ĐÚNG: không trộn hai cách cấp timestamp.
BEGIN BATCH USING TIMESTAMP 1795597200123000
    UPDATE order_lines_by_order
    USING TIMESTAMP 1795597200123001
    SET quantity = 2
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
APPLY BATCH;
~~~

Hãy chọn **một chính sách**: timestamp chung cho toàn batch, **hoặc** timestamps riêng trên những DML khi CQL/server hỗ trợ và bài toán cần đến chúng.

## 6. Hai UPDATE vào cùng cell: không có thứ tự “câu sau thắng”

Xét:
 
~~~sql
BEGIN BATCH
    UPDATE order_lines_by_order
    SET note = 'PACKED'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;

    UPDATE order_lines_by_order
    SET note = 'SHIPPED'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
APPLY BATCH;
~~~

Người đọc quen SQL có thể nghĩ câu thứ hai chắc chắn ghi đè câu thứ nhất. Nhưng trong Cassandra, nếu không chỉ định timestamp riêng, **cả hai mutation cùng dùng timestamp của batch**. Cùng một cell, cùng timestamp sẽ gây **timestamp tie**; Cassandra hòa giải theo quy tắc nội bộ, không dựa vào việc câu lệnh đứng ở dòng sau.

| Mutation A | Mutation B | Kết luận |
|---|---|---|
| `note='PACKED'`, t=100 | `note='SHIPPED'`, t=200 | Timestamp B lớn hơn, B có thể thắng |
| `note='PACKED'`, t=200 | `note='SHIPPED'`, t=100 | A có thể thắng dù lệnh B chạy/đến sau |
| `note='PACKED'`, t=200 | `note='SHIPPED'`, t=200 | Timestamp tie; **không ưu tiên theo vị trí trong batch** |
| Live cell t=200 | Tombstone t=200 | Quy tắc tie-break có ưu tiên dấu xóa khi cùng timestamp |

**Đừng xây business workflow dựa vào tie-break của các giá trị live**. Dù quy tắc hòa giải giúp các replica hội tụ, nó không có nghĩa “thứ tự nghiệp vụ do câu CQL mô tả”.

### 6.1. Nếu chỉ cần trạng thái cuối, dùng một mutation

~~~sql
UPDATE order_lines_by_order
SET quantity = 2, note = 'SHIPPED'
WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
~~~

Không cần batch hai lệnh cùng khóa/hàng khi có thể đặt cả hai giá trị trong một `UPDATE`.

### 6.2. Nếu cần lưu cả PACKED và SHIPPED, dùng event log

Lưu thành **hai hàng sự kiện khác nhau**, mỗi hàng có một `event_id` ổn định và một cột thời gian nghiệp vụ. Phải tránh dùng một cell `note` làm lịch sử thay đổi bằng cách viết nhiều lần trong batch.

## 7. Per-statement timestamps và ý nghĩa thực tế

Trong những phiên bản CQL hỗ trợ, có thể đặt **timestamps khác nhau trên từng mutation**, **không khai báo timestamp tại cấp batch**:

~~~sql
BEGIN BATCH
    UPDATE order_lines_by_order
    USING TIMESTAMP 1795597200123000
    SET note = 'PACKED'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;

    UPDATE order_lines_by_order
    USING TIMESTAMP 1795597200123001
    SET note = 'SHIPPED'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
APPLY BATCH;
~~~

Nếu hai mutation tác động cùng cell, timestamp `...3001` lớn hơn nên mutation tương ứng được ưu tiên theo LWW (giả sử không có phiên bản mới hơn khác). Nhưng **đó vẫn không phải hai bước được thực thi theo thứ tự có kiểm tra điều kiện**: batch không tạo ra điểm `SELECT` giữa hai mutation.

**Khuyến nghị:** chỉ dùng timestamp riêng khi có protocol rõ về thứ tự hòa giải. Để điều khiển state transition, dùng CAS/`IF` hoặc version nghiệp vụ, và đưa lịch sử thành các hàng append-only.

## 8. BATCH LOGGED: bảo đảm atomicity và giới hạn quan sát

`BEGIN BATCH` mặc định là **LOGGED**. Cassandra dùng **batchlog** để giúp những mutation thuộc batch được hoàn tất sau lỗi giữa chừng. Nó **không** là một commit log có thứ tự mà các consumer có thể đọc như queue.

~~~sql
BEGIN BATCH
    UPDATE orders_by_id
    SET status = 'PAID'
    WHERE tenant_id = ? AND order_id = ?;

    UPDATE order_lines_by_order
    SET note = 'paid'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
APPLY BATCH;
~~~

Hai bảng vật lý khác nhau có thể được đọc ở các thời điểm khác nhau. Reader thấy `orders_by_id.status='PAID'` không có nghĩa reader đồng thời thấy `order_lines_by_order.note='paid'`. Logged batch **không cung cấp cross-table snapshot/isolation**.

Một logged batch chỉ nhắm một partition có thể được Cassandra tối ưu như unlogged batch trong nội bộ vì cơ chế atomicity/isolation cùng-partition đã đủ. Đừng dùng loại LOGGED như một cách “ép thứ tự lệnh”.

### 8.1. Không nên lạm dụng multi-partition logged batch

Multi-partition logged batch chỉ hợp lý nếu thật sự cần bảo đảm atomicity cho **một số mutation nhỏ**. Nó có thể gây thêm chi phí batchlog, coordinator và network. Đối với bulk ingest hàng chục nghìn partition, **prepared/asynchronous writes có giới hạn concurrency** thường phù hợp hơn một batch khổng lồ.

## 9. BATCH UNLOGGED và partial writes

~~~sql
BEGIN UNLOGGED BATCH
    UPDATE orders_by_id SET status = 'PAID'
    WHERE tenant_id = ? AND order_id = ?;

    UPDATE orders_by_id SET status = 'PAID'
    WHERE tenant_id = ? AND order_id = ?;
APPLY BATCH;
~~~

Nếu hai cặp `(tenant_id, order_id)` khác nhau, batch chạm **hai partition**. Khi có lỗi, một unlogged batch nhiều partition **có thể chỉ ghi được một phần**.

| Loại batch | Atomicity | Isolation |
|---|---|---|
| LOGGED, một partition | Có | Có trong partition |
| UNLOGGED, một partition | Có theo cơ chế mutation cùng-partition | Có trong partition |
| LOGGED, nhiều partition | Có theo cơ chế batchlog | **Không có isolation xuyên partition** |
| UNLOGGED, nhiều partition | **Không bảo đảm atomicity xuyên partition** | Không có isolation xuyên partition |

Số lượng câu CQL không đồng nghĩa số partition. Một nghìn statement vào cùng `(tenant,order)` có thể là **một partition nhưng batch quá lớn**; ba statement vào ba order khác nhau có thể là **ba partition**. Cả kích thước payload lẫn ranh giới partition đều quan trọng.

## 10. COUNTER batch: cần tránh retry mù

Counter có semantics riêng:

~~~sql
CREATE TABLE order_metrics_by_day (
    tenant_id uuid,
    metric_day date,
    paid_orders counter,
    PRIMARY KEY ((tenant_id, metric_day))
);
~~~

~~~sql
BEGIN COUNTER BATCH
    UPDATE order_metrics_by_day
    SET paid_orders = paid_orders + 1
    WHERE tenant_id = ? AND metric_day = ?;
APPLY BATCH;
~~~

Counter update **không idempotent**: retry sau timeout khi request đầu đã được áp dụng có thể làm bộ đếm tăng thêm lần nữa. Không trộn counter mutation vào batch ghi dữ liệu thông thường; không dùng write timestamp tự chọn như cách CAS cho counter.

Nếu cần tổng số đơn đã thanh toán “đúng một lần”, hãy thiết kế event ID, deduplication và phép tổng hợp có thể đối soát, không suy từ `BEGIN COUNTER BATCH` rằng hệ thống có exactly-once delivery.

## 11. Java Driver 4: BatchStatement và setQueryTimestamp

Java Driver cung cấp `BatchStatement` để gom các bound statements. Ví dụ **hai dòng cùng partition**:

~~~java
package example.orders;

import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class OrderLineBatchDao {
    private final CqlSession session;
    private final PreparedStatement insert;

    public OrderLineBatchDao(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
                "INSERT INTO order_lines_by_order " +
                "(tenant_id, order_id, line_id, sku, quantity, note) " +
                "VALUES (?, ?, ?, ?, ?, ?)");
    }

    public void insertTwoLines(
            UUID tenantId, UUID orderId,
            UUID lineA, UUID lineB, long timestampMicros) {

        BoundStatement first = insert.bind(
                tenantId, orderId, lineA, "SKU-A", 2, "packed");
        BoundStatement second = insert.bind(
                tenantId, orderId, lineB, "SKU-B", 1, "packed");

        BatchStatement batch =
                BatchStatement.builder(DefaultBatchType.LOGGED)
                        .addStatement(first)
                        .addStatement(second)
                        .setQueryTimestamp(timestampMicros)
                        .build();

        session.execute(batch);
    }
}
~~~

Hai `BoundStatement` được áp dụng lên **hai hàng khác nhau**, nên không xảy ra vấn đề cùng-cell/timestamp tie giữa hai statement. `setQueryTimestamp(timestampMicros)` đặt **write timestamp chung ở cấp batch**, không gán giá trị cho cột `updated_at`.

Nếu không gọi `setQueryTimestamp`, timestamp hiệu lực được chọn theo cơ chế timestamp generator/driver/server của phiên bản và cấu hình. Không mặc định “luôn là clock coordinator” hay “luôn là `Instant.now()` của ứng dụng”.

Một `BatchStatement` chỉ nên chứa những statements thật sự cần gửi chung; đừng sử dụng batch để che lỗi thiết kế partition hoặc biến các thao tác nhiều bước có điều kiện thành một lời gọi.

## 12. Spring Data: CassandraBatchOperations.withTimestamp()

Spring Data Cassandra cung cấp `CassandraOperations.batchOps()` và `CassandraBatchOperations`. API `withTimestamp(long)` áp dụng **timestamp chung cho toàn batch**.

~~~java
package example.orders;

import org.springframework.data.cassandra.core.CassandraBatchOperations;
import org.springframework.data.cassandra.core.CassandraOperations;

public final class OrderLineBulkWriter {
    private final CassandraOperations operations;

    public OrderLineBulkWriter(CassandraOperations operations) {
        this.operations = operations;
    }

    public void write(OrderLine a, OrderLine b, long micros) {
        CassandraBatchOperations batch = operations.batchOps();

        batch.withTimestamp(micros)
                .insert(a, b)
                .execute();
    }
}
~~~

`CassandraBatchOperations` sử dụng logged batches mặc định trong các phiên bản hiện đại; một instance **không thể execute lại sau khi đã execute**. Timestamp được đặt ở cấp batch, và statement order không phải ordering guarantee.

### 12.1. @Version không tự bảo vệ batch

Nếu entity có `@Version`, **Spring Data Cassandra hỗ trợ optimistic locking qua LWT cho thao tác một entity**, **không hỗ trợ optimistic locking tự động trong `CassandraBatchOperations`**.

~~~java
// Thao tác đơn lẻ có thể được Spring Data bảo vệ bằng @Version.
repository.save(order);

// KHÔNG giả định hai entity trong batch sẽ có
// IF version = expectedVersion tự động.
operations.batchOps()
        .update(orderA, orderB)
        .execute();
~~~

Nếu cần CAS, dùng single-entity `save` ở đường được hỗ trợ hoặc tự viết CQL `IF version = ?` và kiểm tra kết quả. Đừng dùng batch thông thường như giao dịch có optimistic lock trên nhiều entity.

### 12.2. CqlTemplate/CqlOperations cho CQL trực tiếp

~~~java
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.CqlOperations;

public void updateNotes(
        CqlOperations cql, long timestampMicros,
        UUID tenantId, UUID orderId, UUID lineA, UUID lineB) {

    cql.execute(
            "BEGIN BATCH USING TIMESTAMP ? " +
            "UPDATE order_lines_by_order SET note = ? " +
            "WHERE tenant_id = ? AND order_id = ? AND line_id = ?; " +
            "UPDATE order_lines_by_order SET note = ? " +
            "WHERE tenant_id = ? AND order_id = ? AND line_id = ?; " +
            "APPLY BATCH;",
            timestampMicros,
            "packed", tenantId, orderId, lineA,
            "packed", tenantId, orderId, lineB);
}
~~~

CQL này có **chín bind markers**: một timestamp chung và **hai nhóm bốn giá trị** (note, tenant, order, line). `CqlTemplate` không đọc annotation `@Version` để tự sửa câu CQL trực tiếp, và không cung cấp isolation xuyên partition chỉ vì được gọi từ Spring.

## 13. Entity mapping để chạy Spring Data batch

Lớp khóa ghép:

~~~java
package example.orders;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class OrderLineKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "order_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID orderId;

    @PrimaryKeyColumn(name = "line_id", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED)
    private UUID lineId;

    public OrderLineKey() {}

    public OrderLineKey(UUID tenantId, UUID orderId, UUID lineId) {
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.lineId = lineId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public UUID getOrderId() { return orderId; }
    public void setOrderId(UUID value) { orderId = value; }
    public UUID getLineId() { return lineId; }
    public void setLineId(UUID value) { lineId = value; }

    @Override
    public boolean equals(Object candidate) {
        if (this == candidate) return true;
        if (!(candidate instanceof OrderLineKey)) return false;
        OrderLineKey other = (OrderLineKey) candidate;
        return Objects.equals(tenantId, other.tenantId)
                && Objects.equals(orderId, other.orderId)
                && Objects.equals(lineId, other.lineId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, orderId, lineId);
    }
}
~~~

`ordinal=0,1,2` được đánh **liên tục trên toàn bộ primary key**; `PrimaryKeyType` thuộc package `core.cql`.

Entity:

~~~java
package example.orders;

import java.time.Instant;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_lines_by_order")
public class OrderLine {
    @PrimaryKey
    private OrderLineKey id;

    @Column("sku")
    private String sku;

    @Column("quantity")
    private Integer quantity;

    @Column("note")
    private String note;

    @Column("updated_at")
    private Instant updatedAt;

    public OrderLine() {}

    public OrderLine(OrderLineKey id, String sku,
            Integer quantity, String note, Instant updatedAt) {
        this.id = id;
        this.sku = sku;
        this.quantity = quantity;
        this.note = note;
        this.updatedAt = updatedAt;
    }

    public OrderLineKey getId() { return id; }
    public void setId(OrderLineKey value) { id = value; }
    public String getSku() { return sku; }
    public void setSku(String value) { sku = value; }
    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer value) { quantity = value; }
    public String getNote() { return note; }
    public void setNote(String value) { note = value; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { updatedAt = value; }
}
~~~

Hai class `public` cần nằm trong **hai file Java riêng**. `Instant` ánh xạ cột CQL `timestamp` (mili giây); `withTimestamp(long)` nhận write timestamp **micro giây**. Không tự điền `updatedAt` bằng timestamp của batch trừ khi đó là yêu cầu nghiệp vụ có chủ đích.

Repository point read:

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderLineRepository
        extends CassandraRepository<OrderLine, OrderLineKey> {
}
~~~

Nếu cần đọc nhiều dòng của một đơn, dùng query với đủ partition key `tenant_id` và `order_id`. `@Version`, batch và paging không thay đổi yêu cầu mô hình khóa này.

## 14. WRITETIME(): kiểm tra đúng metadata đã ghi

Đọc những cell mới được batch cập nhật:

~~~sql
SELECT line_id, quantity, note, updated_at,
       WRITETIME(quantity) AS quantity_us,
       WRITETIME(note) AS note_us,
       WRITETIME(updated_at) AS updated_at_us
FROM order_lines_by_order
WHERE tenant_id = ? AND order_id = ?;
~~~

| Trường | Kiểu/ý nghĩa |
|---|---|
| `quantity` | Dữ liệu `int` |
| `quantity_us` | Metadata micro giây của cell `quantity` |
| `note` | Dữ liệu `text` |
| `note_us` | Metadata micro giây của cell `note` |
| `updated_at` | Dữ liệu CQL `timestamp`, đọc bằng Java `Instant` |
| `updated_at_us` | Metadata micro giây của cell `updated_at` |

Sau batch có timestamp `T`, nếu `quantity` và `note` đều được ghi và chưa có ghi đè, `WRITETIME(quantity)=WRITETIME(note)=T`. Nếu một writer khác cập nhật `note` ở timestamp `T+1`, cell `note` có thể có `WRITETIME=T+1` trong khi cell `quantity` vẫn là `T`.

**Giới hạn:** `WRITETIME` dành cho những cell CQL được hỗ trợ, không phải cách truy vấn arbitrary metadata của primary key/counter. Nó cũng không cung cấp lịch sử của mọi mutation đã bị overwrite.

### 14.1. Thí nghiệm so sánh có kiểm soát

1. Tạo một partition test hoàn toàn mới.
2. Ghi hai **cell khác nhau** trong một batch với `USING TIMESTAMP T`.
3. Đọc `WRITETIME()` của từng cell, so sánh với `T`.
4. Ghi thêm một cell ở `T+1` bằng một request khác.
5. Đọc lại: metadata của cell vừa sửa có thể đổi, cell còn lại không bị đổi chỉ vì cùng entity Java.
6. Không viết test khẳng định statement đứng sau trong cùng batch luôn thắng khi cùng timestamp.

## 15. Conditional batch và LWT là cơ chế khác

CQL có `IF` sử dụng **lightweight transaction (LWT)**. Ví dụ:

~~~sql
UPDATE orders_by_id
SET status = 'PAID'
WHERE tenant_id = ? AND order_id = ?
IF status = 'NEW';
~~~

Driver trả kết quả có cột `[applied]`; `false` là điều kiện không thỏa, trong khi timeout có thể xảy ra **sau khi mutation được áp dụng nhưng response thất lạc**, nên không được coi timeout là false.

Cassandra có hỗ trợ **conditional CQL batch** với các giới hạn nghiêm ngặt về table/partition và statement theo phiên bản server. Không suy từ khả năng đó rằng `CassandraBatchOperations` tự động xử lý optimistic locking `@Version`. Cũng **không kết hợp** write timestamp do client đặt tùy ý với LWT conditional statements.

Nếu nghiệp vụ là `NEW → PAID → SHIPPED`, đừng viết hai `UPDATE status` trong cùng batch rồi mong Cassandra kiểm tra bước `PAID` trước. Cần CAS/sequence hoặc workflow với acknowledgement; ghi các sự kiện riêng để có lịch sử.

## 16. Thứ tự sự kiện phải nằm trong khóa, không trong timestamp của batch

Nếu API cần “50 sự kiện mới nhất trong một đơn/ngày”, thiết kế bảng sự kiện:

~~~sql
CREATE TABLE order_events_by_day (
    tenant_id uuid,
    order_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY (
        (tenant_id, order_id, event_day),
        occurred_at, event_id
    )
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

~~~sql
SELECT occurred_at, event_id, event_type, payload
FROM order_events_by_day
WHERE tenant_id = ?
  AND order_id = ?
  AND event_day = ?
LIMIT 50;
~~~

Trong **mỗi partition**, kết quả được sắp theo **clustering `occurred_at DESC, event_id ASC`**, chứ không theo thứ tự `INSERT` của batch hay write timestamp của cell `event_type`.

`event_id` làm khóa phá hòa khi hai sự kiện có cùng thời điểm. Nếu muốn thứ tự nghiệp vụ tuyệt đối xuyên nhiều partition, phải xây logic sequence/điều phối riêng, không dùng write timestamp của batch làm global sequence.

### 16.1. Pagination không phụ thuộc thứ tự batch

Với Spring Data Cassandra, có thể đọc bằng `Slice<T>` và `CassandraPageRequest`:

~~~java
Slice<OrderEvent> first = repository.findInDay(
        tenantId, orderId, day,
        CassandraPageRequest.first(50));

if (first.hasNext()) {
    Slice<OrderEvent> second = repository.findInDay(
            tenantId, orderId, day,
            first.nextPageable());
}
~~~

Đây là **đoạn sử dụng API minh họa**: `OrderEvent` và phương thức repository phải được định nghĩa tương ứng với bảng sự kiện. Paging state là vị trí tiếp tục của **cùng query và bind values**, không phải một snapshot bất biến qua nhiều HTTP requests.

## 17. Consistency không tạo snapshot xuyên partition

`LOCAL_ONE`, `LOCAL_QUORUM` và các consistency levels yêu cầu số replica phản hồi theo replication của keyspace, **không biến logged batch nhiều partition thành một transaction có isolation toàn cục**.

- Reader A ở `LOCAL_ONE` và reader B ở `LOCAL_QUORUM` có thể quan sát dữ liệu vào các thời điểm khác nhau.
- `LOCAL_SERIAL`/`SERIAL` là serial consistency liên quan **LWT**, không phải cấu hình “ép thứ tự câu lệnh” cho batch thông thường.
- Batchlog giúp hoàn tất mutation của logged batch; nó không tạo distributed barrier khiến mọi reader nhìn thấy trạng thái mới cùng lúc.
- Dữ liệu giữa hai bảng projection có thể chậm đồng bộ hoặc được đọc ở các thời điểm khác nhau.

Nếu cần một nguồn sự thật đáng tin cậy, hãy bảo vệ aggregate bằng CAS/version, phát event có ID ổn định, cập nhật read models idempotent và có đối soát/projection-lag metrics.

## 18. TTL, tombstones và chi phí batch

Batch có thể chứa `DELETE`, hoặc `UPDATE` gán `null` lên cột thường; các thao tác này tạo **tombstone** với write timestamp metadata. Trong trường hợp cùng timestamp, tombstone được ưu tiên so với live cell theo quy tắc hòa giải tương ứng.

~~~sql
-- KHÔNG dùng như hai bước có thứ tự.
BEGIN BATCH USING TIMESTAMP 1795597200123000
    UPDATE order_lines_by_order
    SET note = 'packed'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;

    DELETE note FROM order_lines_by_order
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
APPLY BATCH;
~~~

Nếu chỉ muốn xóa `note`, viết **một câu `DELETE note`** thay vì cố “ghi rồi xóa” trong batch.

TTL cho dữ liệu hết hạn, không quyết định thứ tự giữa DML. Khi TTL hết hạn, tombstones và compaction có thể khiến truy vấn sau này tốn kém. Một batch xóa hàng nghìn hàng không bảo đảm thu hồi ổ đĩa tức thì.

Cần theo dõi p95/p99, partition size, tombstones scanned, compaction, repair và batch size. Batch quá lớn trên hot partition có thể làm tăng latency dù chỉ là một request.

## 19. Retry, timeout và idempotency

Khi `execute(batch)` timeout, không thể chắc chắn batch **chưa được áp dụng**. Có thể coordinator đã gửi mutation hoặc batchlog đang hoàn tất những mutation còn thiếu.

| Kiểu mutation | Retry có an toàn không? |
|---|---|
| `INSERT` cùng key và payload ổn định | Thường có thể thiết kế idempotent, cần xem concurrent writers |
| Mỗi retry sinh write timestamp mới | Có thể ghi đè mutation khác đã đến sau về nghiệp vụ |
| Counter increment | **Không idempotent**, có thể tăng hai lần |
| List append | Có thể thêm trùng |
| Insert event với ID mới mỗi lần | Có thể tạo hàng sự kiện trùng |
| LWT timeout | Không biết chắc điều kiện đã được áp dụng chưa |
| Unlogged multi-partition batch lỗi | Có thể cần đối soát partial writes |

Một chiến lược phù hợp dùng **command ID/event ID ổn định**, payload cố định, timestamp ổn định khi policy yêu cầu, retry/backoff có giới hạn và reconciliation theo khóa. Không đặt `setIdempotent(true)` cho mọi batch chỉ vì chúng gồm những `UPDATE` thông thường; cần đánh giá từng mutation.

## 20. Integration test chứng minh timestamp chung

Unit test mock `CassandraBatchOperations` chỉ chứng minh service gọi `withTimestamp`, không chứng minh Cassandra thực sự áp dụng cùng metadata. Dùng Cassandra test instance có schema được provision và fixture riêng.

### 20.1. JUnit/Java Driver kiểm tra hai dòng cùng partition

~~~java
package example.orders;

import static org.junit.jupiter.api.Assertions.*;

import java.util.List;
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class BatchTimestampIntegrationTest {
    @Autowired CqlSession session;

    @Test
    void sameBatchTimestampForTwoRows() {
        UUID tenant = UUID.randomUUID();
        UUID order = UUID.randomUUID();
        UUID line1 = UUID.randomUUID();
        UUID line2 = UUID.randomUUID();
        long micros = 1795597200123456L;

        PreparedStatement insert = session.prepare(
                "INSERT INTO order_lines_by_order " +
                "(tenant_id, order_id, line_id, sku, quantity, note) " +
                "VALUES (?, ?, ?, ?, ?, ?)");

        BatchStatement batch =
                BatchStatement.builder(DefaultBatchType.LOGGED)
                        .addStatement(insert.bind(
                                tenant, order, line1, "SKU-A", 2, "packed"))
                        .addStatement(insert.bind(
                                tenant, order, line2, "SKU-B", 1, "packed"))
                        .setQueryTimestamp(micros)
                        .build();
        session.execute(batch);

        PreparedStatement select = session.prepare(
                "SELECT line_id, quantity, note, " +
                "WRITETIME(quantity) AS quantity_us, " +
                "WRITETIME(note) AS note_us " +
                "FROM order_lines_by_order " +
                "WHERE tenant_id = ? AND order_id = ?");

        List<Row> rows =
                session.execute(select.bind(tenant, order)).all();
        assertEquals(2, rows.size());

        for (Row row : rows) {
            assertEquals(micros, row.getLong("quantity_us"));
            assertEquals(micros, row.getLong("note_us"));
            assertEquals("packed", row.getString("note"));
        }
    }
}
~~~

Test dùng **một partition** và hai dòng khác nhau, tránh cạnh tranh cùng cell. UUID ngẫu nhiên cô lập fixture. **Chưa thực thi test trong STEP 4**; dự án cần bổ sung Cassandra test environment, keyspace, schema và cấu hình consistency phù hợp.

### 20.2. Test write timestamp lớn hơn

~~~sql
UPDATE order_lines_by_order
USING TIMESTAMP 1795597200123000
SET quantity = 1
WHERE tenant_id = ? AND order_id = ? AND line_id = ?;

UPDATE order_lines_by_order
USING TIMESTAMP 1795597200123001
SET quantity = 2
WHERE tenant_id = ? AND order_id = ? AND line_id = ?;

SELECT quantity, WRITETIME(quantity)
FROM order_lines_by_order
WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
~~~

Với một fixture mới và không có writer cạnh tranh, kỳ vọng `quantity=2`, `WRITETIME(quantity)=1795597200123001`. Đây là **hai requests riêng**; không chứng minh thứ tự trong batch.

### 20.3. Không viết test sai về partial visibility

Với logged batch nhiều partition, tài liệu xác nhận **không có isolation xuyên partition**, nhưng một integration test nhỏ có thể *không bao giờ* nhìn thấy trạng thái trung gian vì test chạy quá nhanh. **Không quan sát được** không đồng nghĩa **được bảo đảm không tồn tại**.

Để kiểm chứng dưới sự cố, dùng fault injection/chaos testing có kiểm soát, giám sát mutation/ACK và thử đọc concurrent; không dùng production và không kết luận về isolation chỉ từ một lần chạy.

### 20.4. Danh mục test bổ sung

| Test | Điều cần xác minh |
|---|---|
| Cùng batch, hai cell khác nhau | Metadata timestamp được áp dụng như dự kiến |
| Cùng cell, timestamp bằng nhau | Không suy luận “câu sau thắng” |
| Per-statement timestamp khác nhau | Quy tắc LWW, không phải vị trí câu lệnh |
| Batch nhiều bảng | Không giả định snapshot xuyên bảng |
| Unlogged nhiều partition có sự cố | Có thể có partial writes |
| Counter batch retry | Không idempotent |
| Batch chứa DELETE/TTL | Tombstone scan/retention |
| `@Version` trong `batchOps()` | Không tự có optimistic locking |
| Batch rất lớn/hot partition | Batch warnings, p99, timeout |
| Cursor paging khi có writer | Không có snapshot cố định tự động |

## 21. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Nghĩ statement đứng sau trong batch sẽ thắng | Sai với timestamp tie | Ghi một lần/cell hoặc CAS/event log |
| Dùng `updated_at` làm thứ tự ghi | Nhầm dữ liệu với metadata | Dùng `WRITETIME` để quan sát, dùng version khi cần |
| Truyền `toEpochMilli()` vào `USING TIMESTAMP` | Sai đơn vị 1.000 lần | Chuyển sang micro giây |
| Trộn timestamp ở batch và statement | CQL không hợp lệ | Chọn một cách cấp timestamp |
| Nghĩ logged multi-partition có snapshot | Reader có thể thấy một phần trạng thái | Aggregate/source of truth và projection |
| Nghĩ unlogged multi-partition luôn atomic | Có thể có partial write | Không dùng nếu cần bảo đảm đó |
| Dùng counter batch như exactly-once | Retry đếm trùng | Deduplication/đối soát |
| Tạo batch hàng nghìn partition | Coordinator/batchlog quá tải | Ghi bất đồng bộ có giới hạn concurrency |
| Dùng `@Version` với batch và nghĩ có CAS | Stale updates không bị tự động chặn | Single-entity LWT hoặc conditional CQL |
| Dùng batch như log sự kiện | Mất thứ tự nghiệp vụ | Append-only rows theo clustering key |
| Tăng consistency để ép cùng nhìn thấy | Không tạo global transaction | Hiểu replication/isolation và thiết kế read model |
| Đọc `WRITETIME(primary key)` tùy ý | Không phải khả năng CQL phù hợp | Đọc metadata trên cột thường |
| Retry batch với timestamp mới tùy tiện | Có thể ghi đè dữ liệu mới | Idempotency key và retry policy |
| Đặt `LIMIT 50` rồi nghĩ chỉ quét 50 cell | Tombstones vẫn tốn chi phí | Giám sát storage và schema |

## 22. Bài tập thực hành

### Bài tập A — phân tích timestamp

~~~sql
BEGIN BATCH USING TIMESTAMP 1795597200123000
    UPDATE order_lines_by_order
    SET quantity = 3
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;

    UPDATE order_lines_by_order
    SET note = 'ready'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
APPLY BATCH;
~~~

Nếu hai lệnh nhắm cùng hàng nhưng hai cột khác nhau, `WRITETIME(quantity)` và `WRITETIME(note)` là bao nhiêu sau khi batch thành công, không có writer khác? Vì sao?

### Bài tập B — cùng cell, cùng timestamp

~~~sql
BEGIN BATCH
    UPDATE order_lines_by_order SET note = 'PACKED'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;

    UPDATE order_lines_by_order SET note = 'SHIPPED'
    WHERE tenant_id = ? AND order_id = ? AND line_id = ?;
APPLY BATCH;
~~~

Vì sao không được khẳng định `SHIPPED` chắc chắn thắng? Hãy đề xuất **một UPDATE cho trạng thái cuối** hoặc **hai hàng sự kiện** nếu cần lịch sử.

### Bài tập C — ranh giới partition

Cùng tenant, ba order `O1/O2/O3`. Nếu batch ghi cả ba đơn, đó là một hay ba partition? Logged và unlogged có bảo đảm gì? Reader có thể thấy O1 mới và O2 cũ cùng thời điểm không? Nếu lỗi giữa chừng, cần xử lý theo command ID thế nào?

### Bài tập D — Spring API

~~~java
long micros = WriteTimestamp.toEpochMicros(
        Instant.parse("2026-11-25T09:00:00.123Z"));

operations.batchOps()
        .withTimestamp(micros)
        .insert(firstLine, secondLine)
        .execute();
~~~

Giá trị `micros` là bao nhiêu? `updatedAt` có tự bằng mốc đó không? Tại sao `CassandraBatchOperations` không thể dùng lại sau `execute()`?

### Bài tập E — đúng thứ tự lịch sử

Thiết kế `order_events_by_day` chứa các sự kiện `PACKED`, `SHIPPED`, `DELIVERED`. Hãy sử dụng `(tenant_id,order_id,event_day)` làm partition key và `occurred_at`/`event_id` làm clustering. Viết truy vấn 50 sự kiện mới nhất và giải thích tại sao kết quả theo **clustering** chứ không theo write timestamp của batch.

### Câu hỏi tự kiểm tra

1. Khi không cấp timestamps riêng, các mutation trong cùng batch mang timestamp nào?
2. Cột CQL `timestamp` có phải metadata của mutation không?
3. Vì sao không được suy “UPDATE cuối trong batch thắng”?
4. `withTimestamp(long)` yêu cầu mili giây hay micro giây?
5. Có được đặt đồng thời batch-level và statement-level `USING TIMESTAMP` không?
6. Logged batch nhiều partition có isolation toàn cục không?
7. Unlogged batch nhiều partition gặp lỗi có thể xảy ra gì?
8. Counter batch có idempotent khi retry không?
9. `@Version` tự bảo vệ `CassandraBatchOperations.update(a,b)` không?
10. `LOCAL_QUORUM` có tạo snapshot xuyên bảng không?
11. Dùng `WRITETIME(note)` để đọc toàn bộ lịch sử thay đổi được không?
12. Vì sao lịch sử nên lưu theo khóa sự kiện, không theo thứ tự batch?

**Đáp án:** (1) cùng một timestamp; (2) không; (3) timestamp tie/LWW; (4) micro giây; (5) không; (6) không; (7) partial writes; (8) không; (9) không; (10) không; (11) không; (12) batch không bảo đảm thứ tự sự kiện.

## 23. Checklist trước khi release

- [ ] Biết **mỗi statement chạm partition nào** và có thật sự cần batch không.
- [ ] Phân biệt LOGGED, UNLOGGED, COUNTER và phạm vi atomicity/isolation.
- [ ] Không dùng thứ tự câu lệnh trong batch để quyết định giá trị cuối.
- [ ] Không viết hai payload trái ngược cho cùng cell/cùng timestamp.
- [ ] Nếu dùng batch-level `USING TIMESTAMP`, biết mọi mutation nhận cùng metadata.
- [ ] Không trộn batch timestamp với per-statement timestamps.
- [ ] Xác nhận đơn vị **micro giây** cho `withTimestamp(long)` và Java Driver.
- [ ] Tách cột `updated_at`/CQL `timestamp` khỏi write timestamp.
- [ ] Không cho client không tin cậy chọn write timestamp tương lai tùy ý.
- [ ] Không dùng logged multi-partition batch như SQL transaction có global isolation.
- [ ] Không dùng unlogged multi-partition batch khi cần atomicity xuyên partition.
- [ ] Không dùng counter batch cho exactly-once mà không có deduplication.
- [ ] Không suy `@Version` tự tạo optimistic locking trong `CassandraBatchOperations`.
- [ ] Dùng CAS/LWT nếu cần kiểm tra điều kiện nghiệp vụ.
- [ ] Có command/event ID ổn định, backoff và chính sách retry rõ.
- [ ] Không dùng batch khổng lồ cho bulk ingest hoặc cleanup.
- [ ] Với lịch sử sự kiện, partition/clustering key phản ánh thứ tự truy vấn mong muốn.
- [ ] Phân trang đúng `Slice`/`nextPageable` và không dùng cursor cho query khác.
- [ ] Đã đo batch size, p95/p99, hot partition, tombstone scan và compaction.
- [ ] Có integration test kiểm chứng `WRITETIME`, lỗi/timestamp và phạm vi partition.
- [ ] Các ví dụ bài viết cần vòng Content QA/CI riêng trước khi dùng production.

## 24. Tổng kết

**Timestamp của batch** phục vụ **hòa giải cell/tombstone**; **CQL `timestamp`** là dữ liệu về thời điểm. **Cùng timestamp không tạo thứ tự statement**. **Single-partition batch** có atomicity/isolation trong phạm vi partition; **logged multi-partition batch** có atomicity theo batchlog nhưng không có isolation xuyên partition. `CassandraBatchOperations.withTimestamp` không thay thế CAS, `@Version`, schema đúng, hay event log được thiết kế theo query.

## Tài liệu tham khảo

- [Apache Cassandra — CQL Data Manipulation và BATCH](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — CQL Language Specification](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/cql_singlefile.html).
- [Spring Data Cassandra — CassandraBatchOperations API](https://docs.spring.io/spring-data/cassandra/reference/4.5/api/java/org/springframework/data/cassandra/core/CassandraBatchOperations.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Data Cassandra — CQL Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra Java Driver 4 — Batch Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/batch/).
- [Apache Cassandra Java Driver 4 — Query Timestamps](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/query_timestamps/).

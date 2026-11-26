# Phạm vi @Version cho thao tác một entity và giới hạn với batch

Trong **Spring Data Cassandra**, annotation `@Version` giúp phát hiện xung đột khi **hai tiến trình cùng sửa một entity**. Thay vì ghi đè một cách mù quáng, Spring Data Cassandra sử dụng **lightweight transaction (LWT)** của Apache Cassandra để kiểm tra phiên bản đang lưu trước khi chấp nhận thay đổi. Nếu entity đã bị một writer khác sửa, thao tác lưu phiên bản cũ thất bại với `OptimisticLockingFailureException`.

Tuy nhiên, một giới hạn rất quan trọng là **optimistic locking bằng `@Version` chỉ được Spring Data Cassandra hỗ trợ cho thao tác một entity; không tự động áp dụng cho thao tác batch**. Một `CassandraBatchOperations.update(entityA, entityB)` không đồng nghĩa hai entity đều được kiểm tra `IF version = ...`, dù cả hai class có field `@Version`.

Bài học thuộc chương **LWT và khóa lạc quan** của module **SPRING_DATA_CASSANDRA**. Nội dung gắn với phạm vi module: truy cập Cassandra bằng **entity mapping, repository, CassandraTemplate và CQL**, đồng thời giải thích thiết kế partition key, consistency, paging, hiệu năng và ý nghĩa của tính nhất quán trong một hệ dữ liệu phân tán.

Sau bài này, bạn cần có thể:

1. Viết entity Cassandra có `@Version Long version` và hiểu vòng đời phiên bản khi insert/update/delete.
2. Phân biệt **LWT được Spring tự sinh cho một entity** với CQL `IF` viết thủ công.
3. Giải thích được vì sao **batch không được @Version bảo vệ tự động**, kể cả khi batch được gọi từ `CassandraTemplate`.
4. Thiết kế hướng xử lý đúng cho hai writer cạnh tranh, timeout, retry và các bảng projection khác nhau.
5. Viết integration test chứng minh stale update thất bại, đồng thời kiểm tra rủi ro khi trộn batch và đường ghi không kiểm tra version.

> **Kết luận chính:** `@Version` không phải khóa JVM, không phải global transaction và không phải thuộc tính của CQL `BATCH`. Nó là **quy ước entity-level do Spring Data thực thi bằng LWT** ở những thao tác đơn lẻ được hỗ trợ.

## 1. Vì sao last-write-wins không đủ cho nhiều nghiệp vụ?

Apache Cassandra thường hòa giải các mutation cạnh tranh trên cùng cell theo **write timestamp** (*last-write-wins*). Nếu hai request cùng đọc trạng thái `NEW`, sau đó một request chuyển sang `PAID` còn request khác chuyển sang `CANCELLED`, một lệnh `UPDATE` vô điều kiện có thể ghi đè kết quả của lệnh kia tùy timestamp và thứ tự thực thi.

~~~text
                  Cassandra: order 42, status = NEW
                              |
                 +------------+------------+
                 |                         |
           Writer A đọc NEW           Writer B đọc NEW
                 |                         |
          Muốn ghi PAID             Muốn ghi CANCELLED
                 |                         |
             UPDATE A                  UPDATE B
                 |                         |
                 +------------+------------+
                              |
                    Một giá trị thắng theo
                    timestamp của mutation.
~~~

Nếu hợp đồng nghiệp vụ là “sau khi thanh toán thành công, không được dùng dữ liệu cũ để hủy đơn”, cơ chế LWW theo write timestamp **không tự kiểm tra** điều kiện đó. Cột `updated_at timestamp` cũng không giúp ích nếu ứng dụng không thực hiện compare-and-set.

**Optimistic locking** giải quyết một lớp lỗi cụ thể:

1. Mỗi entity có **version** biểu thị phiên bản dữ liệu mà writer đã đọc.
2. Writer gửi cập nhật **chỉ khi version trong Cassandra còn bằng version đã đọc**.
3. Nếu cập nhật thành công, version được tăng.
4. Writer khác đang giữ phiên bản cũ sẽ nhận **xung đột**, thay vì âm thầm ghi đè.

Đây là cách kiểm tra **đồng thời trên cùng thực thể được định danh**, không phải cơ chế sắp xếp lịch sử nhiều partition hoặc bảo vệ tất cả read models trong một ứng dụng.

## 2. @Version là gì trong Spring Data Cassandra?

`@Version` là annotation thuộc **Spring Data Commons**:

~~~java
import org.springframework.data.annotation.Version;
~~~

Nó không phải `jakarta.persistence.Version` của JPA. Khi dùng với entity Spring Data Cassandra được mapping đúng, nó khai báo **một property phiên bản** để Spring Data kiểm tra khi thực hiện các thao tác ghi **một entity**.

Theo cơ chế optimistic locking của Spring Data Cassandra:

| Thao tác trên một entity | Cơ chế ý tưởng | Khi có xung đột |
|---|---|---|
| Tạo mới với version chưa khởi tạo | `INSERT ... IF NOT EXISTS` | Khóa hàng đã có → ghi bị từ chối |
| Cập nhật entity đã đọc | `UPDATE ... IF version = oldVersion`, tăng version | Version đang lưu khác → không cập nhật |
| Xóa entity có version | Conditional `DELETE` với version của entity | Version khác → không xóa |
| `CassandraBatchOperations` trên nhiều entity | **Không** tự thêm bảo vệ `@Version` | Không được giả định stale entity bị phát hiện |

Với đường optimistic locking được Spring Data hỗ trợ, khi điều kiện không thỏa framework ném **`org.springframework.dao.OptimisticLockingFailureException`** hoặc subtype liên quan, tùy thao tác/phiên bản. Trường hợp bị từ chối về mặt nghiệp vụ khác với các lỗi hạ tầng như timeout, unavailable, authentication hoặc schema không tồn tại.

### 2.1. Không nhầm @Version với write timestamp

| Thuộc tính | `@Version Long version` | Cassandra write timestamp |
|---|---|---|
| Giá trị | Số phiên bản entity, ví dụ 0, 1, 2 | Thời gian metadata của mutation, tính bằng micro giây |
| Nơi lưu | Một cột CQL, ví dụ `version bigint` | Metadata phục vụ reconciliation của cell/tombstone |
| Điều kiện cập nhật | Spring dùng `IF version = ...` trong LWT | Cassandra hòa giải dữ liệu theo write timestamp |
| Xem bằng CQL | `SELECT version` | `WRITETIME(status)` cho cột phù hợp |
| Có tự bảo đảm nhiều bảng? | Không | Không |

`version = 3` không có nghĩa mutation xảy ra lúc 3 micro giây sau epoch; cũng không có nghĩa bản ghi ở mọi bảng projection đều đang ở phiên bản thứ 3.

## 3. Thiết kế bảng point read theo primary key đầy đủ

Giả sử ứng dụng có API:

~~~text
GET   /tenants/{tenantId}/orders/{orderId}
PATCH /tenants/{tenantId}/orders/{orderId}/status
~~~

Một bảng theo ID:

~~~sql
CREATE TABLE order_state_by_id (
    tenant_id uuid,
    order_id uuid,
    status text,
    total_amount decimal,
    updated_at timestamp,
    version bigint,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

| Cột | Vai trò | Có tham gia so sánh optimistic locking? |
|---|---|---|
| `tenant_id` | Partition key, thành phần thứ nhất | Dùng định vị đúng entity |
| `order_id` | Partition key, thành phần thứ hai | Dùng định vị đúng entity |
| `status` | Cột thường | Trạng thái nghiệp vụ cần bảo vệ |
| `total_amount` | Cột thường | Giá trị nghiệp vụ |
| `updated_at` | Cột thường, CQL `timestamp` | Chỉ là thời gian nghiệp vụ |
| `version` | Cột thường, CQL `bigint` | **Có**, Spring so sánh và tăng |

**Đường đọc hợp lệ** phải có **đủ** `tenant_id` và `order_id`:

~~~sql
SELECT tenant_id, order_id, status, total_amount, updated_at, version
FROM order_state_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

Câu `WHERE status = 'NEW'` không tự trở thành truy vấn hiệu quả chỉ vì entity có `@Version`. LWT kiểm tra `status` hoặc `version` khi **đã xác định đúng khóa**, không cung cấp chỉ mục để tìm tất cả đơn ở một trạng thái.

## 4. Entity có khóa ghép và @Version Long

### 4.1. Khóa ghép ánh xạ hai thành phần partition

~~~java
package example.orders;

import java.io.Serializable;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class OrderStateKey implements Serializable {
    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "order_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID orderId;

    public OrderStateKey() {}

    public OrderStateKey(UUID tenantId, UUID orderId) {
        this.tenantId = tenantId;
        this.orderId = orderId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public UUID getOrderId() { return orderId; }
    public void setOrderId(UUID value) { orderId = value; }

    @Override
    public boolean equals(Object candidate) {
        if (this == candidate) return true;
        if (!(candidate instanceof OrderStateKey)) return false;
        OrderStateKey that = (OrderStateKey) candidate;
        return Objects.equals(tenantId, that.tenantId)
                && Objects.equals(orderId, that.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, orderId);
    }
}
~~~

**Hai thành phần đều là `PARTITIONED`**, không có clustering key trong bảng `order_state_by_id`. `ordinal` mô tả thứ tự của từng thành phần trong primary key. Nếu service chỉ có `orderId` mà không có tenant, nó **chưa có đủ đường khóa** cho point read này.

### 4.2. Entity có version được ánh xạ

~~~java
package example.orders;

import java.math.BigDecimal;
import java.time.Instant;

import org.springframework.data.annotation.Version;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_state_by_id")
public class OrderState {

    @PrimaryKey
    private OrderStateKey id;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    @Column("updated_at")
    private Instant updatedAt;

    @Version
    @Column("version")
    private Long version;

    public OrderState() {}

    public OrderState(OrderStateKey id, String status,
            BigDecimal totalAmount, Instant updatedAt) {
        this.id = id;
        this.status = status;
        this.totalAmount = totalAmount;
        this.updatedAt = updatedAt;
        // version không gán: null nghĩa là entity mới theo chiến lược mặc định.
    }

    public OrderStateKey getId() { return id; }
    public void setId(OrderStateKey value) { id = value; }
    public String getStatus() { return status; }
    public void setStatus(String value) { status = value; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public void setTotalAmount(BigDecimal value) { totalAmount = value; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant value) { updatedAt = value; }
    public Long getVersion() { return version; }
    public void setVersion(Long value) { version = value; }
}
~~~

Chọn **`Long` boxed** thay vì `long` để trạng thái **chưa có version (`null`)** được biểu diễn rõ. Trong Spring Data, khi entity có property `@Version`, giá trị `null` thường được dùng để nhận diện entity mới; primitive `0` còn có ý nghĩa nhận diện mới khác và dễ gây nhầm lẫn. Mẫu trên dùng `Long` xuyên suốt và để Spring quản lý chu kỳ phiên bản.

`updatedAt` là **giá trị nghiệp vụ** ánh xạ `timestamp` CQL, còn `version` ánh xạ `bigint`. Không đặt `@Version` lên `Instant updatedAt` hoặc một field trong object khóa ghép.

## 5. Tạo mới một entity: IF NOT EXISTS và version = 0

Repository đơn giản:

~~~java
package example.orders;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderStateRepository
        extends CassandraRepository<OrderState, OrderStateKey> {
}
~~~

Tạo entity mới:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

OrderStateKey key = new OrderStateKey(tenantId, orderId);
OrderState initial = new OrderState(
        key, "NEW", new BigDecimal("125000.00"), Instant.now());

// initial.getVersion() == null
OrderState saved = repository.save(initial);

// Với đường insert @Version được Spring quản lý,
// version được khởi tạo bằng 0.
Long persistedVersion = saved.getVersion();
~~~

Theo tài liệu Spring Data Cassandra, với một entity mới có `@Version`, Spring sử dụng **LWT `IF NOT EXISTS`**, không phải `INSERT` vô điều kiện. Ngữ nghĩa CQL tương đương:

~~~sql
INSERT INTO order_state_by_id (
    tenant_id, order_id, status, total_amount, updated_at, version
) VALUES (?, ?, ?, ?, ?, 0)
IF NOT EXISTS;
~~~

*Lưu ý:* Đây là **CQL mô tả ngữ nghĩa**, không phải cam kết chuỗi CQL được từng phiên bản Spring Data tạo ra giống hệt từng ký tự. Hãy kiểm chứng câu statement thực tế ở môi trường test nếu ứng dụng phụ thuộc chi tiết binding/DDL.

Nếu hai request cùng muốn tạo **một khóa**:

~~~text
Writer A: INSERT key K, version=0 IF NOT EXISTS
Writer B: INSERT key K, version=0 IF NOT EXISTS

Kết quả: chỉ mutation thỏa điều kiện được áp dụng.
Writer thua không được âm thầm ghi đè hàng đã có.
~~~

Với `@Version` do Spring Data quản lý, thao tác không được áp dụng vì entity đã tồn tại được xem là **optimistic locking failure**. Không coi ngoại lệ đó là một lỗi network để tự động thử lại vô hạn.

### 5.1. Trường hợp version = null nhưng hàng đã tồn tại

Giả sử service tự dựng một entity mới với cùng `tenantId/orderId`, không đọc bản đang có:

~~~java
OrderState duplicate = new OrderState(
        new OrderStateKey(tenantId, orderId),
        "PAID", new BigDecimal("125000.00"), Instant.now());

// duplicate.getVersion() == null
repository.save(duplicate);
~~~

Do version đang `null`, Spring có thể coi đây là **entity mới** và thực thi insert có điều kiện. Nó **không có nghĩa** “nếu hàng đã tồn tại thì cập nhật lên PAID”. Hãy đọc entity và lấy version hiện tại, hoặc thiết kế command/CQL điều kiện riêng thay vì tự gán version dựa trên suy đoán.

## 6. Cập nhật một entity: IF version = oldVersion

Hai writer cùng đọc một hàng `version=0`:

~~~text
             order_state_by_id
            status=NEW, version=0
                     |
              +------+------+
              |             |
         Writer A đọc   Writer B đọc
           version=0      version=0
              |             |
        A muốn PAID    B muốn CANCELLED
              |             |
     UPDATE ... IF 0   UPDATE ... IF 0
              |             |
      A được áp dụng   B bị từ chối vì
      version: 0 → 1   hiện tại version=1
~~~

Về ngữ nghĩa, Spring Data thực hiện điều kiện tương đương:

~~~sql
UPDATE order_state_by_id
SET status = ?, total_amount = ?,
    updated_at = ?, version = 1
WHERE tenant_id = ? AND order_id = ?
IF version = 0;
~~~

Ở lần ghi thành công tiếp theo, version `1` được kiểm tra và tăng thành `2`; ứng dụng **không tự sửa trực tiếp version** trước khi gọi `save` để qua mặt cơ chế này.

### 6.1. Code service: read → modify → save

~~~java
package example.orders;

import java.time.Clock;
import java.time.Instant;
import java.util.UUID;

import org.springframework.dao.OptimisticLockingFailureException;

public class OrderStateService {
    private final OrderStateRepository repository;
    private final Clock clock;

    public OrderStateService(OrderStateRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public OrderState markPaid(UUID tenantId, UUID orderId) {
        OrderStateKey key = new OrderStateKey(tenantId, orderId);

        OrderState current = repository.findById(key)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Order not found"));

        if (!"NEW".equals(current.getStatus())) {
            throw new IllegalStateException(
                    "Transition requires state NEW");
        }

        current.setStatus("PAID");
        current.setUpdatedAt(Instant.now(clock));

        // Nếu một writer khác đã thay đổi version,
        // Spring Data ném OptimisticLockingFailureException.
        return repository.save(current);
    }
}
~~~

Đây là ví dụ **synchronous repository**; cần có bean `Clock` (ví dụ `Clock.systemUTC()`) được cung cấp bởi application. `IllegalArgumentException`/ `IllegalStateException` chỉ là placeholder cho domain errors; API thực tế nên ánh xạ sang `404` hoặc `409` theo hợp đồng.

**Lưu ý quan trọng:** bước `if ("NEW".equals(...))` chạy trong JVM **không nguyên tử** với thao tác lưu. Chính **điều kiện `IF version = ...` trong LWT** mới phát hiện writer khác đã sửa entity ở giữa hai bước. Tuy nhiên điều đó chỉ hiệu quả nếu **mọi đường ghi liên quan đều tuân thủ việc thay đổi version** (xem phần 10).

### 6.2. Spring Data ném ngoại lệ khi version cũ

~~~java
import org.springframework.dao.OptimisticLockingFailureException;

try {
    OrderState saved = repository.save(current);
    // Chỉ xem thao tác thành công sau khi save thực sự hoàn tất.
} catch (OptimisticLockingFailureException conflict) {
    // Đã có writer khác tác động, hoặc entity được tạo/xóa khác kỳ vọng.
    // Phải nạp lại trạng thái và quyết định theo domain.
}
~~~

**Không** tự làm:

~~~java
// Sai ý định:
current.setVersion(current.getVersion() + 1);
repository.save(current);
~~~

`version` cần là giá trị **đã đọc**, không phải “version mà client đoán sẽ có”. Framework dùng nó làm điều kiện so sánh với dữ liệu thật.

## 7. Xóa một entity: version-aware delete khác delete theo ID

Với entity `current` đã đọc, Spring Data Cassandra có đường xóa một entity có khả năng áp dụng optimistic locking:

~~~java
import org.springframework.data.cassandra.core.CassandraOperations;

OrderState current = repository.findById(key).orElseThrow();

// Trên API Spring Data Cassandra hỗ trợ single-entity versioned delete:
operations.delete(current);
~~~

Về ngữ nghĩa, conditional delete phải kiểm tra version hiện tại trước khi xóa:

~~~sql
DELETE FROM order_state_by_id
WHERE tenant_id = ? AND order_id = ?
IF version = ?;
~~~

Nếu version đã thay đổi, thao tác không được coi là xóa thành công và đường optimistic locking báo xung đột. Sự khác biệt rất đáng chú ý:

| API/ý định | Có thông tin version đã đọc? | Giả định đúng |
|---|---|---|
| `operations.delete(entity)` với mapped `@Version` | **Có** | Đường single-entity có thể kiểm tra version |
| `repository.delete(entity)` | **Có** | Kiểm tra hành vi version-aware theo phiên bản repository |
| `repository.deleteById(key)` | **Không** | Không suy ra điều kiện `IF version = ...` |
| `DELETE FROM ... WHERE key` qua CQL trực tiếp | **Không**, trừ khi tự thêm `IF` | Là câu delete theo khóa, không tự kiểm tra version |

Nếu API cần “xóa **chỉ khi dữ liệu vẫn đúng phiên bản người dùng đã thấy**”, hãy dùng đường delete một entity được framework hỗ trợ hoặc CQL `DELETE ... IF version = ?` rõ ràng. Không dùng `deleteById` với kỳ vọng ngầm rằng Spring tự nhớ version của một object đã đọc ở request trước.

**Xóa hàng** có thể tạo tombstone và chịu quy tắc hòa giải write timestamp của Cassandra. `@Version` xác định điều kiện **có được phép xóa hay không**, không bảo đảm tombstone được thu hồi vật lý ngay lập tức.

## 8. LWT hoạt động ra sao?

**Lightweight transaction** dùng cơ chế đồng thuận có điều kiện (thuật ngữ thường gặp là **Paxos**) để kiểm tra điều kiện trên dữ liệu hiện có rồi quyết định có áp dụng mutation hay không.

~~~mermaid
flowchart TD
    A[Client đọc entity version=4] --> B[Chỉnh sửa giá trị]
    B --> C[UPDATE ... IF version=4]
    C --> D{LWT kiểm tra dữ liệu hiện tại}
    D -->|version=4| E[Applied=true, version=5]
    D -->|version khác| F[Applied=false, không ghi cập nhật]
    E --> G[Trả entity mới]
    F --> H[Spring báo OptimisticLockingFailureException]
~~~

`IF` không phải một phép `SELECT` Java rồi `UPDATE` độc lập. Nó được xử lý tại Cassandra trong một giao thức có điều kiện. Đó là lý do LWT giúp tránh kiểu lost update mà `read → validate → unconditional UPDATE` không tránh được.

### 8.1. Serial consistency và regular consistency

Trong Java Driver/Cassandra, cần phân biệt:

| Cấu hình | Công dụng |
|---|---|
| `LOCAL_SERIAL` hoặc `SERIAL` | Serial consistency của phần LWT/consensus |
| `LOCAL_QUORUM` và các mức thông thường | Consistency cho phần thao tác đọc/ghi theo replica |
| Request timeout | Giới hạn thời gian chờ của client, không làm LWT nhanh hơn |
| Retry/idempotency | Quyết định cách ứng dụng xử lý lỗi và kết quả chưa rõ |

Các lựa chọn phải phù hợp với **replication factor, datacenter, SLA và phiên bản Cassandra**. `LOCAL_QUORUM` **không tự biến** một câu `UPDATE` vô điều kiện thành LWT. Ngược lại, `@Version` không cho phép bỏ qua thiết kế đường khóa.

### 8.2. LWT đắt hơn ghi thông thường

LWT cần các bước trao đổi và kiểm tra điều kiện bổ sung nên thường tăng latency/tải so với mutation không điều kiện. Hệ quả:

- Tránh thêm `@Version` lên mọi entity chỉ theo thói quen, đặc biệt với dòng sự kiện append-only.
- Với một khóa cực nóng, các writer cạnh tranh có thể làm tăng contention, retry và p95/p99 latency.
- Không dùng LWT như phương án thay thế partitioning/indexing hoặc như một khóa phân tán vô hạn.
- Đo performance ở dữ liệu và concurrency đại diện; phân loại lỗi conflict khác với lỗi hạ tầng.

## 9. Giới hạn được công bố: @Version chỉ hỗ trợ single-entity operations

Tài liệu **Spring Data for Apache Cassandra — Optimistic Locking** nêu rõ: cơ chế optimistic locking được hỗ trợ **chỉ cho thao tác một entity**, **không hỗ trợ batch operations**.

Vì vậy phải phân biệt ba tình huống:

| Tình huống | Có @Version trên entity? | Có được kỳ vọng Spring tự tạo điều kiện CAS? |
|---|---|---|
| `repository.save(order)` | Có | **Có**, trên đường một entity được hỗ trợ |
| `cassandraTemplate.save(order)` | Có | **Có**, trên đường một entity được hỗ trợ |
| `operations.batchOps().update(orderA, orderB)` | Có cả hai | **Không**, batch không hỗ trợ optimistic locking tự động |
| `CqlSession.execute("UPDATE ...")` | Entity Java có annotation | **Không**, driver không đọc metadata entity |
| CQL `UPDATE ... IF version = ?` trực tiếp | Có hoặc không | **Có điều kiện CQL** vì tự viết `IF`, không phải do annotation |

Mọi kết luận ở trên áp dụng cho **cơ chế @Version do Spring Data Cassandra quản lý**. Đừng suy rộng thành “Cassandra không hề hỗ trợ conditional batch”: CQL có khả năng conditional batches trong những phạm vi bị ràng buộc (xem phần 12). Hai cơ chế khác nhau.

### 9.1. Vì sao batch không thể được hiểu như gọi save() tuần tự?

Giả sử:

~~~java
OrderState a = repository.findById(keyA).orElseThrow();
OrderState b = repository.findById(keyB).orElseThrow();

a.setStatus("PAID");
b.setStatus("CANCELLED");

operations.batchOps()
        .update(a, b)
        .execute();
~~~

Đoạn code sử dụng `CassandraBatchOperations` cho hai entity. **Nó không tương đương**:

~~~java
// Hai thao tác riêng lẻ; mỗi thao tác có thể được Spring Data
// bảo vệ bằng @Version, nhưng KHÔNG tạo atomicity giữa hai thao tác.
repository.save(a);
repository.save(b);
~~~

Với batch, không được giả định framework đã tạo `IF version = oldVersion` cho từng entity và đã tăng version theo cùng semantics như `save` đơn lẻ. Ngoài ra, hai lời gọi `save` tuần tự **không phải transaction hai entity**: nếu ghi A thành công nhưng B bị conflict, A vẫn có thể đã thay đổi.

**Khuyến nghị:** giữ đường entity-level optimistic locking đơn lẻ cho các cập nhật cần tránh lost update; nếu yêu cầu là một bất biến của nhiều bản ghi, cần mô hình hóa lại bất biến, đánh giá phạm vi của CQL conditional batch hoặc dùng workflow có idempotency/đối soát phù hợp.

## 10. Một đường ghi CQL không có IF có thể phá giả định @Version

Xét entity hiện có:

~~~text
key K: status=NEW, version=4
~~~

Service A đọc entity với `version=4`. Trong lúc đó, service B gửi CQL trực tiếp:

~~~sql
-- Không bảo vệ bằng version và cũng không tăng version!
UPDATE order_state_by_id
SET status = 'PAID'
WHERE tenant_id = ? AND order_id = ?;
~~~

Bây giờ dữ liệu có thể là:

~~~text
key K: status=PAID, version=4
~~~

Service A vẫn giữ `version=4` và gọi `repository.save(...)` với `status='CANCELLED'`. Điều kiện `IF version = 4` **vẫn có thể thỏa**, vì B đã thay status nhưng **không đổi version**.

Điều đó cho thấy:

1. `@Version` không phải một bộ giám sát mọi mutation trên bảng.
2. **Mọi writer** tác động vào những field cần bảo vệ phải tôn trọng cùng quy tắc version/CAS.
3. Các đường `@Query`, `CqlTemplate`, `CqlSession`, batch, job migration và service khác cần được rà soát.
4. Nếu bắt buộc có nhiều kiểu writer, hãy định nghĩa một protocol ghi có điều kiện chung và kiểm thử race condition.

Một `UPDATE ... SET version = version + 1` không phải lời giải phổ quát: Cassandra không cung cấp cơ chế tăng nguyên tử trực tiếp cho cột `bigint` thông thường giống counter. Với version nghiệp vụ, cần giá trị dự kiến mới và điều kiện `IF version = ?`, hoặc API Spring Data được hỗ trợ.

## 11. Viết conditional CQL thủ công khi cần kiểm soát rõ

Một câu CQL compare-and-set cho một hàng:

~~~sql
UPDATE order_state_by_id
SET status = ?,
    updated_at = ?,
    version = ?
WHERE tenant_id = ?
  AND order_id = ?
IF version = ?;
~~~

Trong một method, các tham số có ý nghĩa:

~~~text
?0: status mới
?1: updated_at mới
?2: version mới = expectedVersion + 1
?3: tenant_id
?4: order_id
?5: expectedVersion (giá trị đã đọc)
~~~

### 11.1. Dùng Java Driver và đọc [applied]

~~~java
package example.orders;

import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class OrderVersionCasDao {
    private final CqlSession session;
    private final PreparedStatement update;

    public OrderVersionCasDao(CqlSession session) {
        this.session = session;
        this.update = session.prepare(
                "UPDATE order_state_by_id " +
                "SET status = ?, updated_at = ?, version = ? " +
                "WHERE tenant_id = ? AND order_id = ? " +
                "IF version = ?");
    }

    public boolean changeStatus(
            UUID tenantId, UUID orderId, String status,
            Instant updatedAt, long expectedVersion) {

        long nextVersion = Math.addExact(expectedVersion, 1L);
        Row result = session.execute(update.bind(
                status, updatedAt, nextVersion,
                tenantId, orderId, expectedVersion)).one();

        if (result == null) {
            throw new IllegalStateException("Missing LWT result");
        }

        return result.getBoolean("[applied]");
    }
}
~~~

**`[applied]=true`** nghĩa là điều kiện được thỏa và mutation được áp dụng; **`[applied]=false`** nghĩa là không được áp dụng do điều kiện không thỏa. Nếu timeout/exception xảy ra, trạng thái **chưa xác định** — không thể tự coi như `false`.

Đoạn DAO này dùng **CAS tường minh**. Dù entity Java có `@Version` hay không, driver không tự quản lý exception/domain conflict. Caller phải chuyển kết quả `false` thành lỗi xung đột của nghiệp vụ hoặc thử nạp lại dữ liệu theo chính sách được thiết kế.

### 11.2. Vì sao không dùng SELECT rồi UPDATE?

~~~java
// Lập luận sai:
if (databaseVersion == expectedVersion) {
    unconditionalUpdate();
}
~~~

Giữa hai bước trên, một writer khác có thể thay dữ liệu. `IF version = ...` kiểm tra điều kiện trên server bằng LWT; đó là khác biệt cốt lõi giữa **optimistic locking thực sự** và phép kiểm tra giá trị trước khi ghi trong JVM.

### 11.3. CqlTemplate và CassandraTemplate

`CqlTemplate`/`CqlOperations` cho phép gửi CQL có bind parameters; tuy nhiên khi muốn đọc chính xác `[applied]` và metadata của kết quả LWT, dùng `CqlSession` hoặc API result-extractor phù hợp:

~~~java
// CQL được quản lý tường minh; không phải @Version tự sinh.
String conditionalCql =
        "UPDATE order_state_by_id " +
        "SET status = ?, version = ? " +
        "WHERE tenant_id = ? AND order_id = ? " +
        "IF version = ?";
~~~

`CassandraTemplate`/`CassandraOperations` phù hợp khi bạn muốn framework mapping một entity và sử dụng cơ chế `@Version` trên **lời gọi thao tác đơn lẻ**. Nếu cần một câu điều kiện CQL đặc thù không thuộc đường entity-save, hãy kiểm tra API version hiện tại và đừng giả định `@Version` tự gắn điều kiện vào mọi statement.

## 12. CassandraBatchOperations: batch là gì và không phải gì?

`CassandraOperations.batchOps()` tạo `CassandraBatchOperations`, dùng để nhóm các lệnh INSERT/UPDATE/DELETE. Trong các phiên bản Spring Data Cassandra hiện đại:

~~~java
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.CassandraBatchOperations;

CassandraBatchOperations batch = operations.batchOps();

batch.update(entityA, entityB);
batch.execute();
~~~

`batchOps()` mặc định tạo **logged batch**; có thể dùng overload nhận `BatchType` khi phiên bản hỗ trợ. Một object batch **chỉ được execute một lần**. Nhưng thao tác trên **nhiều entity** không được Spring Data nâng cấp thành “nhiều optimistic locks từ @Version”.

### 12.1. Phân biệt BATCH thông thường và LWT

| Cơ chế | Có điều kiện `IF`? | Đảm bảo/giới hạn cốt lõi |
|---|---|---|
| `repository.save(entity)` có `@Version` | Framework thêm cho một entity | CAS theo version của entity |
| `CassandraBatchOperations.update(entities)` | **Không được giả định** tự thêm từ `@Version` | Group mutations; không hỗ trợ optimistic locking entity-level tự động |
| CQL `BEGIN BATCH ... APPLY BATCH` không có `IF` | Không | Batch mutations, không kiểm tra giá trị hiện tại |
| CQL conditional batch với `IF` hợp lệ | Có thể | Chỉ trong phạm vi/ràng buộc backend hỗ trợ, thường **một partition/một table** |
| Nhiều `save(entity)` riêng lẻ | Mỗi entity có thể có CAS | Không nguyên tử xuyên nhiều entity |

**Không suy ra rằng batch là transaction ACID SQL.** Với logged batch trải trên nhiều partition, batchlog giúp Cassandra tiếp tục/phục hồi các mutation nhưng **không có isolation hay snapshot nguyên tử xuyên partition** như một giao dịch quan hệ. Có thể có khoảng thời gian một phần kết quả đã quan sát được trước phần còn lại. Chi phí coordinator và mạng cũng có thể tăng.

### 12.2. Giới hạn của conditional CQL batch

Cassandra có cú pháp **conditional batch**, nhưng phần LWT của batch bị ràng buộc bởi schema và version; thông thường các thao tác điều kiện phải ở **cùng một table và partition**. Cần kiểm tra tài liệu chính xác của phiên bản cluster đang dùng trước khi triển khai.

Ví dụ một bảng lưu nhiều dòng trong **cùng một partition**:

~~~sql
CREATE TABLE order_lines_by_order (
    tenant_id uuid,
    order_id uuid,
    line_id uuid,
    quantity int,
    version bigint,
    PRIMARY KEY ((tenant_id, order_id), line_id)
);
~~~

Một conditional batch trên hai dòng **của cùng partition** có thể được diễn đạt về ý tưởng bằng CQL:

~~~sql
-- Ví dụ cần kiểm chứng với đúng phiên bản Cassandra trước khi dùng.
BEGIN BATCH
  UPDATE order_lines_by_order
  SET quantity = ?, version = ?
  WHERE tenant_id = ? AND order_id = ? AND line_id = ?
  IF version = ?;

  UPDATE order_lines_by_order
  SET quantity = ?, version = ?
  WHERE tenant_id = ? AND order_id = ? AND line_id = ?
  IF version = ?;
APPLY BATCH;
~~~

Trong ví dụ, các giá trị `tenant_id` và `order_id` của cả hai mutation phải **giống nhau**, `line_id` xác định hai hàng khác nhau cùng partition. Cần đọc `[applied]` của kết quả batch và xử lý việc **toàn bộ điều kiện bị từ chối** nếu có điều kiện không thỏa.

**Quan trọng:** tự viết CQL conditional batch như trên **không phải** cách khiến `CassandraBatchOperations.update(entityA, entityB)` tự hiểu `@Version`; nó là một giao thức CAS do ứng dụng quản lý, có giới hạn của server và chi phí LWT. Không sử dụng conditional batch xuyên hai bảng hoặc hai partition rồi kỳ vọng nguyên tử.

### 12.3. Khi nào không nên dùng batch?

- Gộp hàng trăm mutation từ nhiều tenant/partition chỉ để giảm số lần gọi API.
- Muốn biến hai read models `orders_by_id` và `orders_by_customer_month` thành một transaction ACID tổng quát.
- Muốn bảo vệ nhiều `@Version` đồng thời mà không có điều kiện CQL thực sự.
- Dùng một batch quá lớn gây áp lực coordinator, batchlog, retry và p99.
- Cần read-before-write để kiểm tra logic phức tạp trên nhiều partition.

Trong các trường hợp này, thường phải **thiết kế lại aggregation boundary**, dùng ghi độc lập có idempotency và đối soát, hoặc đánh giá cơ chế giao dịch đặc thù mà **phiên bản Cassandra** hỗ trợ; không giả định Spring Data Cassandra `@Version` cung cấp khả năng đó.

## 13. Hai bảng projection: mỗi @Version chỉ bảo vệ entity của bảng đó

Giả sử ngoài `order_state_by_id`, hệ thống có bảng đọc lịch sử theo khách/tháng:

~~~sql
CREATE TABLE orders_by_customer_month (
    tenant_id uuid,
    customer_id uuid,
    month_bucket date,
    created_at timestamp,
    order_id uuid,
    status text,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        created_at, order_id
    )
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Một đơn có thể có:

~~~text
order_state_by_id
    key = (tenant, order)
    version = 7, status = PAID

orders_by_customer_month
    key = (tenant, customer, month, createdAt, order)
    status = NEW
~~~

`@Version` của `OrderState` **không tự cập nhật bảng projection** khi lưu bản ghi `order_state_by_id`. Nó cũng không tự kiểm tra rằng dòng lịch sử của đơn đang có cùng version, vì:

1. Hai bảng dùng **hai primary keys khác nhau**.
2. `@Version` kiểm soát một **entity row** của một mapping cụ thể.
3. Ghi sang hai bảng là **hai mutations** với nhiều khả năng thất bại/đến trễ.
4. Một batch không tự biến hai updates thành một optimistic lock nhiều entity.

Nếu tính nhất quán giữa các bảng là yêu cầu sản phẩm, hãy thiết kế:

- Một nguồn sự thật/aggregate state với CAS theo version.
- Event/outbox hoặc command log có **ID ổn định** để phát thay đổi đến projection.
- Upsert idempotent, có **version/sequence** trong projection để chặn event cũ ghi đè event mới.
- Đối soát định kỳ theo partition/key và xử lý replay khi có lỗi từng phần.
- SLA về projection lag và cơ chế hiển thị trạng thái chậm cập nhật cho người dùng.

Đây là vấn đề **thiết kế hệ phân tán**, không được giải bằng cách thêm `@Version` vào hai entity rồi gọi `batchOps()`.

## 14. @Version không tự bảo vệ PATCH, derived query hoặc raw CQL

Không phải thao tác nào nhắc tới entity cũng đi qua lifecycle optimistic locking:

~~~java
// API entity-level: có cơ chế @Version theo đường save được hỗ trợ.
repository.save(order);
~~~

Khác với:

~~~java
// Một @Query viết CQL trực tiếp: kiểm tra version là việc của chính CQL.
@Query("UPDATE order_state_by_id SET status = ?0 " +
       "WHERE tenant_id = ?1 AND order_id = ?2")
void updateStatusDirectly(
        String status, UUID tenantId, UUID orderId);
~~~

Đoạn `@Query` là ví dụ **một method nằm trong repository**; việc dùng `@Query` cho DML cần đối chiếu API và return type theo phiên bản Spring Data Cassandra, nhưng ý chính không đổi: **nếu CQL không có `IF version = ...` và không thay version**, `@Version` trên entity không làm statement này trở thành CAS.

Tương tự:

- `CassandraTemplate` với `Query/Criteria` xây một `UPDATE` theo điều kiện khóa có thể **không** tự dùng version nếu nó không đi qua thao tác version-aware trên một entity.
- `CqlTemplate` thực thi chuỗi CQL là tầng thấp, **không** tự đọc mapping `@Version` để thêm `IF`.
- `CqlSession` chỉ hiểu statement và bind values, **không** diễn giải annotation Java.
- Một job data migration hoặc consumer ghi bằng CQL trực tiếp phải tôn trọng protocol version của dữ liệu nếu không muốn phá invariant.

**Quy tắc kiểm tra:** xác định đường code cuối cùng gửi câu CQL nào; không kết luận có optimistic locking chỉ từ việc nhìn thấy `@Version` trong class.

## 15. Timeout, retry và kết quả LWT chưa xác định

LWT có thể **được áp dụng tại Cassandra** nhưng client **không nhận được phản hồi** vì timeout hoặc kết nối ngắt. Trong tình huống này:

~~~text
Client: UPDATE ... IF version=4
             |
             v
Cassandra: applied=true, version=5
             |
        Response thất lạc
             |
Client: timeout
~~~

Client **không được** diễn giải timeout là “chắc chắn chưa cập nhật”. Nếu retry cùng điều kiện `IF version=4`, kết quả có thể là `[applied]=false` vì request đầu đã thành công.

### 15.1. Phân loại kết quả và hành động

| Kết quả | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `save` trả entity thành công | Update được framework xác nhận | Trả trạng thái mới |
| `OptimisticLockingFailureException` | Version/điều kiện không thỏa | Nạp lại và xử lý domain conflict |
| Driver/CQL `[applied]=false` | LWT cụ thể không được áp dụng | So sánh trạng thái thật, trả conflict hoặc idempotent success theo contract |
| Timeout/transport exception | **Không rõ** mutation đã được áp dụng chưa | Tra cứu bằng khóa/command ID, retry có chính sách |
| InvalidQueryException | CQL/schema/điều kiện không hợp lệ | Sửa query hoặc migration |
| Unavailable/overloaded | Không đáp ứng điều kiện hạ tầng | Thực hiện backoff/circuit-breaker, không spin retry |

### 15.2. Không retry bằng cách nâng version tùy tiện

Một cách xử lý sai:

~~~java
// KHÔNG làm kiểu này sau conflict:
order.setVersion(order.getVersion() + 1);
repository.save(order);
~~~

Bạn vừa đổi **expectedVersion** theo giả định chưa được xác minh. Nếu có writer khác đã đổi trạng thái/giá trị nghiệp vụ, bạn có thể vô tình ép một mutation cũ qua bước kiểm tra.

Thay vào đó, đọc lại **entity hiện tại**, kiểm tra domain invariant và quyết định có phát **command mới** với version mới hay không. Với các command cần idempotency xuyên retry, dùng `commandId` ổn định; trong nhiều quy trình còn cần bảng/record deduplication hoặc event log riêng.

### 15.3. API HTTP nên tách 404, 409 và 503

- `404 Not Found`: khóa hàng không tồn tại theo hợp đồng và kiểm tra truy cập.
- `409 Conflict`: trạng thái/version đã thay đổi nên command không thể áp dụng như yêu cầu.
- `503 Service Unavailable` hoặc mã lỗi hạ tầng phù hợp: Cassandra tạm không thể phục vụ; không tuyên bố chắc chắn mutation chưa xảy ra.

Không nên trả thành công “đã cập nhật” khi chỉ thấy một request được gửi đi mà chưa xác nhận kết quả. Ngược lại, không đánh đồng mọi timeout với xung đột version.

## 16. Chi phí và năng lực vận hành

Khi cân nhắc `@Version`, hãy đo:

| Chỉ số | Vì sao quan trọng? |
|---|---|
| p50/p95/p99 latency của LWT | Consensus có thể tăng thời gian xử lý |
| Tỷ lệ conflict `OptimisticLockingFailureException` | Phát hiện tranh chấp nghiệp vụ hoặc client giữ version cũ |
| LWT timeout/unavailable | Tách lỗi hạ tầng khỏi conflict hợp lệ |
| Số mutation/giây trên một partition | Khóa nóng làm tăng contention |
| Retry rate và backoff | Tránh retry storm khi cluster bận |
| Replication factor/DC | Quyết định consistency/serial consistency khả dụng |
| Projection lag và lỗi ghi từng phần | `@Version` không bảo vệ bảng đọc khác |
| Tombstones/TTL | Delete và thời hạn dữ liệu có chi phí đọc/compaction |

Không có một cấu hình timeout hoặc serial consistency “đúng với mọi cluster”. Hãy chọn dựa trên phân phối dữ liệu, SLA, replication, lưu lượng và phiên bản Apache Cassandra đang vận hành.

`@Version` không thay thế **partition key**. Nếu dùng khóa `(tenant_id, order_id)`, mỗi update xác định một partition; muốn tìm danh sách đơn theo `status` hoặc theo khách/tháng, cần đường truy cập/bảng projection riêng thay vì kỳ vọng LWT giúp lọc.

## 17. Integration test: hai bản sao entity tranh chấp nhau

Một unit test mock repository chỉ kiểm tra code gọi `save`, **không chứng minh** Spring sinh `IF version = ...`, CQL chạy đúng hay Cassandra từ chối stale update. Cần một test Cassandra thật trong CI/Testcontainers hoặc cluster test được cô lập.

### 17.1. Test insert → update → stale save

~~~java
package example.orders;

import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.OptimisticLockingFailureException;

@SpringBootTest
class OrderStateOptimisticLockingIntegrationTest {

    @Autowired OrderStateRepository repository;

    @Test
    void staleWriterCannotOverwriteNewerVersion() {
        OrderStateKey key = new OrderStateKey(
                UUID.randomUUID(), UUID.randomUUID());

        OrderState created = repository.save(new OrderState(
                key, "NEW",
                new BigDecimal("100.00"),
                Instant.parse("2026-11-25T09:00:00Z")));

        assertEquals(0L, created.getVersion());

        OrderState writerA = repository.findById(key).orElseThrow();
        OrderState writerB = repository.findById(key).orElseThrow();

        assertEquals(0L, writerA.getVersion());
        assertEquals(0L, writerB.getVersion());

        writerA.setStatus("PAID");
        writerA.setUpdatedAt(
                Instant.parse("2026-11-25T09:01:00Z"));
        OrderState savedA = repository.save(writerA);
        assertEquals(1L, savedA.getVersion());

        writerB.setStatus("CANCELLED");
        assertThrows(
                OptimisticLockingFailureException.class,
                () -> repository.save(writerB));

        OrderState persisted = repository.findById(key).orElseThrow();
        assertEquals("PAID", persisted.getStatus());
        assertEquals(1L, persisted.getVersion());
    }
}
~~~

**Điều kiện chạy:** schema `order_state_by_id` đã được tạo, cấu hình cluster/test keyspace và dependency Spring Boot Test có sẵn. Đoạn code là ví dụ để đưa vào dự án và **chưa được chạy trong STEP 4**.

`UUID.randomUUID()` trong fixture dùng để cô lập mỗi lượt test; command nghiệp vụ thật phải dùng ID ổn định qua retry. Không kiểm thử race/delete trên dữ liệu production.

### 17.2. Test insert trùng khóa

~~~java
@Test
void newVersionedEntityDoesNotSilentlyUpsertExistingRow() {
    OrderStateKey key = new OrderStateKey(
            UUID.randomUUID(), UUID.randomUUID());

    OrderState first = new OrderState(
            key, "NEW", new BigDecimal("100.00"),
            Instant.parse("2026-11-25T09:00:00Z"));
    repository.save(first);

    // Một entity MỚI khác nhưng cùng primary key, version vẫn null.
    OrderState second = new OrderState(
            key, "PAID", new BigDecimal("100.00"),
            Instant.parse("2026-11-25T09:01:00Z"));

    assertThrows(OptimisticLockingFailureException.class,
            () -> repository.save(second));
}
~~~

Đây là **method bổ sung vào class integration test trên**. Nó xác minh `IF NOT EXISTS` của đường insert có `@Version`. Không suy rằng Cassandra `INSERT` thông thường đã có uniqueness check: điểm khác biệt xuất hiện vì Spring Data chọn LWT cho thao tác entity versioned.

### 17.3. Test bắt buộc cho batch

Vì tài liệu xác nhận batch **không được @Version bảo vệ tự động**, đừng chỉ kiểm tra rằng một batch “chạy thành công”. Hãy có test chứng minh giả định của chính hệ thống:

1. Tạo hai bản ghi có version bằng `repository.save`.
2. Đọc entity A/B, sau đó để writer khác cập nhật một bản bằng đường `save` hợp lệ.
3. Thử batch trên các bản A/B cũ **chỉ trong môi trường test**.
4. Quan sát CQL thực sự được gửi và version/data sau batch.
5. Xác nhận ứng dụng **không dựa vào** việc batch ném `OptimisticLockingFailureException` cho từng stale entity.
6. Nếu cần điều kiện trên nhiều bản ghi trong cùng partition, test conditional CQL batch **riêng** theo quy tắc server; không suy từ `@Version`.

Không có cơ chế “kiểm thử đúng” nào bằng cách giả lập rằng `batchOps().update()` là alias của hai lệnh `repository.save()`. Hai đường code có contracts khác nhau.

### 17.4. Các tình huống cạnh tranh cần kiểm thử thêm

| Test | Kỳ vọng |
|---|---|
| Hai writer cùng version 0 | Chỉ một writer có thể chuyển version 0 → 1 |
| Writer giữ version cũ lâu | Save thất bại, service xử lý conflict |
| Delete bằng version cũ | Không xóa khi entity đã thay đổi theo đường versioned delete |
| Delete theo ID | Không mặc định có version check |
| CQL raw UPDATE không tăng version | Phơi bày nguy cơ phá invariant `@Version` |
| Retry LWT sau timeout giả lập | Xử lý kết quả chưa xác định, không tự tăng version |
| Hai access tables | Phát hiện projection lag/ghi một phần |
| Batch với stale entity | Không dựa vào optimistic locking tự động |
| Conditional batch cùng partition | Kiểm tra `[applied]` và giới hạn server |
| Partition nóng/nhiều writer | Đo conflict, p99, timeout và retry amplification |

## 18. Các cách giải quyết khi cần thay đổi nhiều entity

Không phải lúc nào hệ thống cũng cần “một transaction chứa tất cả entity”. Hãy xác định **bất biến nghiệp vụ** trước:

### 18.1. Một aggregate root làm nguồn sự thật

Nếu trạng thái chính của đơn chỉ cần quyết định dựa trên một hàng `order_state_by_id`, hãy:

1. Dùng `@Version`/LWT bảo vệ **một hàng nguồn sự thật**.
2. Sau khi ghi thành công, phát command/event có ID và version ổn định.
3. Cập nhật projection khác bất đồng bộ có idempotency và kiểm tra sequence.
4. Đối soát khi cần, có metrics về projection lag.

Đây thường là một mô hình dễ hiểu hơn việc cố “khóa” đồng thời hàng ở nhiều bảng không cùng partition.

### 18.2. Conditional batch do ứng dụng điều khiển

Nếu bất biến thực sự nằm trên nhiều hàng **cùng table và partition**, hãy nghiên cứu CQL conditional batch hỗ trợ bởi **đúng phiên bản Cassandra**. Khi đó:

- Viết rõ `IF` cho điều kiện cần kiểm tra.
- Đảm bảo toàn bộ mutation nằm trong phạm vi hợp lệ.
- Đọc và xử lý `[applied]`.
- Đo chi phí LWT và khả năng contention.
- Không dùng `CassandraBatchOperations` như một cách ngầm bật `@Version`.

### 18.3. Giao dịch đa partition hoặc nhiều hệ thống

Nếu phải cập nhật nhiều partition/bảng với ràng buộc chặt, đánh giá tính năng giao dịch **thực sự có trên phiên bản backend**, hoặc một cơ chế workflow/saga có compensation và idempotency. Một số phiên bản Cassandra mới có hướng giao dịch nâng cao, nhưng **không được suy từ đó rằng Spring Data `@Version` đã hỗ trợ batch optimistic locking**.

Với write path cần tính chính xác cao, có thể tách command validation, conditional write cho aggregate, và các bước cập nhật read model được giám sát/đối soát riêng.

## 19. Lỗi thường gặp và cách khoanh vùng

| Triệu chứng hoặc hiểu lầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| `save` ném `OptimisticLockingFailureException` | Version đã thay đổi / insert có điều kiện thất bại | Đọc lại entity, xử lý conflict đúng domain |
| `save` trên entity version=null không cập nhật được hàng cũ | Spring coi đây là entity mới và dùng `IF NOT EXISTS` | Dùng entity/version đọc được hoặc CAS riêng |
| Dùng `long version` rồi gặp trạng thái mới khó hiểu | Primitive 0 có semantics state detection riêng | Dùng `Long` nullable, test vòng đời |
| Update raw CQL ghi đè giá trị mà `@Version` không biết | Không tăng version, không `IF version` | Thống nhất protocol ghi trên mọi writer |
| Batch `update(a,b)` không báo stale update như mong đợi | `@Version` không hỗ trợ batch | Không dựa vào annotation; chọn phương án multi-record đúng |
| Hai `save` riêng lẻ: A thành công, B conflict | Không có transaction xuyên hai call | Thiết kế compensation/idempotent projection |
| `deleteById` xóa dù entity đã thay đổi | Đường delete không có expected version | Dùng version-aware delete hoặc CQL `IF` |
| Timeout LWT sau khi Cassandra có thể đã ghi | Kết quả chưa xác định | Đối soát theo key/commandId, retry có kiểm soát |
| Conflict rate tăng cao | Nhiều writer cùng tranh một partition/entity | Giảm contention, tổ chức command theo aggregate |
| p99 tăng sau khi thêm @Version | LWT consensus tốn thêm round-trips | Benchmark và chỉ bảo vệ invariant cần thiết |
| Dùng `WRITETIME` thay version | Metadata LWW không phải CAS nghiệp vụ | Giữ cột `version` và điều kiện đúng |
| Truy vấn sai khóa nhưng có @Version | Optimistic locking không tạo index | Sửa partition key/read model, không tăng timeout |

Không đọc log chứa dữ liệu nhạy cảm chỉ để kiểm tra `IF version`. Trên môi trường test/staging, dùng request tracker/driver metrics có kiểm soát để quan sát CQL và `[applied]`, bảo vệ bind values/tenant IDs.

## 20. Bài tập thực hành

Hệ thống logistics quản lý trạng thái kiện hàng:

~~~sql
CREATE TABLE package_state_by_id (
    tenant_id uuid,
    package_id uuid,
    state text,
    last_scanned_at timestamp,
    version bigint,
    PRIMARY KEY ((tenant_id, package_id))
);
~~~

Yêu cầu:

~~~text
GET   /tenants/{tenantId}/packages/{packageId}
PATCH /tenants/{tenantId}/packages/{packageId}/state

Trạng thái: CREATED → AT_HUB → IN_TRANSIT → DELIVERED.
Không cho một command cũ đẩy ngược trạng thái về trước.
~~~

### Bài tập A — entity và repository

Tạo `PackageKey` gồm hai field partitioned với ordinal 0, 1. Tạo `PackageState` có:

~~~java
@Version
@Column("version")
private Long version;
~~~

Tạo `CassandraRepository<PackageState, PackageKey>`. Viết service đọc theo key, xác thực bước chuyển trạng thái, rồi `repository.save(entity)`; trình bày tình huống hai writer cùng giữ `version=2`.

### Bài tập B — câu CQL conditional tương đương

~~~sql
UPDATE package_state_by_id
SET state = ?, last_scanned_at = ?, version = ?
WHERE tenant_id = ? AND package_id = ?
IF version = ?;
~~~

Giả sử phiên bản hiện tại là 2:

- Nếu `[applied]=true`, version mới sẽ là 3 theo protocol của bạn.
- Nếu `[applied]=false`, không được coi mutation là đã ghi; kiểm tra trạng thái/version thực để quyết định.
- Nếu timeout, **không** suy ra false: kiểm tra khả năng request đã được áp dụng.

### Bài tập C — giới hạn của batch

Giả sử phải cập nhật `package_state_by_id` và một bảng `scans_by_package_day` có partition key `(tenant_id, package_id, scan_day)`. Hãy trả lời:

1. Hai bảng có cùng partition key không?
2. `@Version` trên entity trạng thái có bảo vệ dòng scan không?
3. `batchOps().update(packageState).insert(scan)` có tự kiểm tra version cả hai không?
4. Nếu mutation thứ nhất thành công nhưng bản ghi scan chưa hiển thị, người dùng phải nhận contract gì?
5. Đề xuất command ID, event log/projection, retry và đối soát phù hợp.

### Bài tập D — chọn chiến lược theo phạm vi

| Bài toán | Chiến lược đề xuất |
|---|---|
| Một entity trạng thái bị hai writer sửa | `@Version` trên thao tác đơn lẻ |
| Tạo mới nhưng không muốn trùng primary key | `INSERT IF NOT EXISTS` (do Spring tạo khi entity versioned mới) |
| Cập nhật một hàng bằng driver ngoài Spring | CQL `IF version = ?` và tăng version có kiểm soát |
| Hai dòng cùng table/partition cần cùng điều kiện | Đánh giá conditional CQL batch của server |
| Hai bảng khác partition cần nhất quán nghiệp vụ | Aggregate/source of truth + idempotent projection/đối soát |
| Danh sách theo thời gian của một package | Read model với partition/clustering key phù hợp, không do @Version tạo ra |

### Câu hỏi tự kiểm tra

1. `@Version` của Spring Data Cassandra nằm ở package nào?
2. Vì sao chọn `Long` nullable thay cho `long` trong ví dụ?
3. Với entity mới có version null, Spring Data dùng điều kiện CQL nào?
4. Writer A và B cùng đọc version 0, tại sao cả hai không thể cùng ghi thành công theo đường save version-aware?
5. Khi version không khớp, Spring ném ngoại lệ nào?
6. `repository.deleteById(key)` có tự biết version client đã thấy không?
7. `CassandraBatchOperations.update(a,b)` có tự thực hiện hai CAS theo `@Version` không?
8. Cassandra có hỗ trợ **conditional batch CQL** trong trường hợp hợp lệ không?
9. Raw CQL UPDATE chỉ thay status mà không tăng version gây rủi ro gì?
10. Một timeout LWT có chứng minh `[applied]=false` không?
11. Vì sao `LOCAL_QUORUM` không thay thế `IF version = ?`?
12. Vì sao hai bảng projection cùng có version vẫn không tự tạo transaction nhiều bảng?

**Gợi ý đáp án:** (1) `org.springframework.data.annotation.Version`; (2) null giúp xác định entity mới; (3) `IF NOT EXISTS`; (4) chỉ mutation có version hiện hành thỏa `IF`; (5) `OptimisticLockingFailureException`; (6) không; (7) không; (8) có, nhưng ràng buộc nghiêm ngặt về table/partition và version server; (9) writer dùng version cũ vẫn có thể ghi đè; (10) không; (11) consistency replica khác CAS nghiệp vụ; (12) mỗi entity/table là một write path riêng, không tự đồng bộ nguyên tử.

## 21. Checklist trước khi triển khai

- [ ] Xác định invariant cần bảo vệ: mất cập nhật ở **một entity**, không phải mọi dữ liệu của hệ thống.
- [ ] Có bảng với **primary key đầy đủ** và cột `version bigint` phù hợp mapping.
- [ ] Import đúng `org.springframework.data.annotation.Version`, không nhầm với JPA.
- [ ] Sử dụng `Long` nullable hoặc đã kiểm chứng kỹ semantics new detection của kiểu được chọn.
- [ ] Entity mới có version null; không tự tăng version trước khi save.
- [ ] Kiểm chứng đường single-entity insert có `IF NOT EXISTS`, update có `IF version`.
- [ ] Chỉ dùng version-aware delete khi cần kiểm tra phiên bản; không nhầm với `deleteById`.
- [ ] Catch và xử lý `OptimisticLockingFailureException` thành domain conflict, không retry mù.
- [ ] Phân biệt LWT conflict với timeout, unavailable, schema error và lỗi kết nối.
- [ ] Mọi writer dùng CqlTemplate/CqlSession/@Query/batch đều tôn trọng protocol version nếu cùng sửa dữ liệu.
- [ ] **Không** giả định `@Version` hoạt động tự động trong `CassandraBatchOperations`.
- [ ] Không dùng CQL BATCH nhiều partition như một SQL transaction toàn cục.
- [ ] Nếu dùng conditional CQL batch, đã kiểm tra ràng buộc **same partition/table** theo version.
- [ ] Có chiến lược idempotency, outbox/event và đối soát khi cập nhật nhiều bảng projection.
- [ ] Đã kiểm thử 2 writer, duplicate insert, stale update/delete và đường ghi bypass version.
- [ ] Đã đánh giá LWT contention, p95/p99, consistency/serial consistency, retry và tải.
- [ ] Không dùng `@Version` để thay cho query-driven design, paging, partitioning hay index.
- [ ] Bài đang ở bước viết Markdown; sẽ có vòng review/QA chuyên môn riêng trước khi xuất bản.

## Tài liệu tham khảo

- [Spring Data Cassandra — Persisting Entities: Optimistic Locking](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Data Cassandra — Repository Core Concepts và Entity State Detection](https://docs.spring.io/spring-data/cassandra/reference/repositories/core-concepts.html).
- [Spring Data Cassandra — Object Mapping và @Version](https://docs.spring.io/spring-data/cassandra/reference/object-mapping.html).
- [Spring Data Cassandra — CassandraBatchOperations Javadoc](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/CassandraBatchOperations.html).
- [Spring Data Cassandra — CassandraOperations Javadoc](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/CassandraOperations.html).
- [Apache Cassandra — CQL Data Manipulation, BATCH và IF](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra Java Driver 4 — Query Idempotence](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/idempotence/).

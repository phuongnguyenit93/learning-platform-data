# Repository fragment sử dụng Template hoặc Driver

Trong **Spring Data Cassandra**, `CassandraRepository` cung cấp các thao tác repository thông dụng như lưu, đọc theo khóa chính và xóa. Khi ứng dụng cần một truy vấn CQL đặc thù, cần kiểm soát các tùy chọn của driver hoặc cần gom logic truy cập dữ liệu thành một API có thể tái sử dụng, ta có thể mở rộng repository bằng **repository fragment**. Fragment là một giao diện nhỏ do ứng dụng định nghĩa, có lớp triển khai riêng, sau đó được ghép vào repository hiện có.

Bài này tập trung vào hai cách triển khai fragment:

- **`CassandraOperations` / `CassandraTemplate`**: sử dụng ánh xạ entity và API truy vấn của Spring Data Cassandra.
- **`CqlSession` của Java Driver**: thực thi CQL trực tiếp, chủ động chọn câu lệnh, tham số, consistency và xử lý `Row`.

Cả hai cách đều cần tuân thủ mô hình Cassandra: **thiết kế bảng theo truy vấn**, lọc đúng partition key, kiểm soát kích thước partition, giới hạn lượng dữ liệu đọc và sử dụng paging khi kết quả lớn.

## 1. Fragment giải quyết vấn đề gì?

Giả sử một hệ thống quản lý đơn hàng cần lấy tối đa 50 đơn gần đây của một khách thuê (tenant), trong một trạng thái xác định, kể từ một mốc thời gian. Các thao tác `save`, `findById`, `deleteById` vẫn thuộc `CassandraRepository`. Riêng thao tác `findRecentByTenantAndStatus(...)` cần được kiểm soát chặt về CQL và hiệu năng.

Có thể viết phương thức suy diễn từ tên, khai báo `@Query` hoặc tạo fragment. Fragment phù hợp hơn khi:

1. Truy vấn cần kết hợp nhiều điều kiện, ánh xạ kết quả hoặc quy tắc kiểm tra tham số.
2. Cần viết một triển khai bằng `CassandraTemplate` hay `CqlSession` thay vì phụ thuộc cách Spring Data suy diễn truy vấn.
3. Cần chia sẻ cùng một hành vi cho nhiều repository hoặc dễ thay đổi cách truy cập dữ liệu.
4. Cần kiểm tra độc lập logic truy vấn mà không mở rộng toàn bộ base repository.

Sơ đồ ghép thành phần:

```text
OrderService
    |
    v
OrderRepository
    |-- CassandraRepository<OrderByStatus, OrderKey>
    |       |-- save / findById / deleteById / ...
    |
    |-- OrderSearchFragment
            |
            v
      OrderSearchFragmentImpl
            |-- Cách A: CassandraOperations
            |-- Cách B: CqlSession (Java Driver)
```

**Một repository có thể ghép nhiều fragment.** Mỗi fragment nên biểu diễn một nhóm hành vi nhỏ, có tên rõ nghĩa. Lớp triển khai không cần kế thừa `SimpleCassandraRepository`.

## 2. Bắt đầu từ mô hình truy vấn Cassandra

Không nên thiết kế fragment trước rồi tìm cách ép Cassandra thực hiện truy vấn. Hãy xác định access pattern và bảng phục vụ truy vấn trước.

**Access pattern:** với `tenant_id` và `status` đã biết, lấy các đơn có `created_at >= since`, theo thời gian mới nhất, tối đa `limit` bản ghi.

Một bảng phù hợp là:

```sql
CREATE TABLE orders_by_tenant_status (
    tenant_id  uuid,
    status     text,
    created_at timestamp,
    order_id   uuid,
    amount     decimal,
    PRIMARY KEY ((tenant_id, status), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Ý nghĩa các thành phần:

| Thành phần | Vai trò |
| --- | --- |
| `(tenant_id, status)` | **Partition key tổng hợp**; cùng tenant và trạng thái được đặt vào cùng một logical partition. |
| `created_at` | Clustering column cho truy vấn theo khoảng thời gian và thứ tự giảm dần. |
| `order_id` | Clustering column bổ sung để phân biệt các đơn có cùng timestamp. |
| `amount` | Dữ liệu trả về, không tham gia điều kiện lọc. |

Truy vấn CQL dự kiến:

```sql
SELECT order_id, created_at, amount
FROM orders_by_tenant_status
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
LIMIT ?;
```

Tất cả thành phần partition key đều có điều kiện bằng; phạm vi trên clustering column phù hợp với thứ tự khóa. Không cần `ALLOW FILTERING`. Nếu yêu cầu mới chuyển thành “lọc mọi tenant theo status” thì đây là **access pattern khác** và thường cần một bảng đọc khác, không phải thêm `ALLOW FILTERING` vào truy vấn.

**Cảnh báo về partition lớn:** nếu một tenant có hàng triệu đơn trong cùng một trạng thái, partition `(tenant_id, status)` có thể tăng quá lớn. Khi đó nên xem xét thêm time bucket (ví dụ `yyyymm`) vào partition key và thay đổi logic truy vấn để đọc các bucket cần thiết. Việc chọn bucket phải dựa trên tốc độ ghi, thời gian giữ dữ liệu và truy vấn thực tế; không có kích thước partition tối ưu cố định cho mọi hệ thống.

## 3. Định nghĩa entity và khóa chính

Để sử dụng Template và `CassandraRepository`, entity phải ánh xạ đúng khóa trong bảng. Với khóa tổng hợp, có thể dùng `@PrimaryKeyClass` và `@PrimaryKey`.

Ví dụ rút gọn, giả sử dùng Java 17+, Spring Data Cassandra 4.x và đã cấu hình kết nối Cassandra:

```java
// OrderKey.java (lược bỏ import)
@PrimaryKeyClass
public class OrderKey implements java.io.Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "status", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private String status;

    @PrimaryKeyColumn(name = "created_at", ordinal = 0,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 1,
            type = PrimaryKeyType.CLUSTERED)
    private UUID orderId;

    public OrderKey() {}

    // Bổ sung constructor, getters/setters, equals và hashCode.
}
```

Các annotation trên đến từ `org.springframework.data.cassandra.core.mapping`; `Ordering` đến từ `org.springframework.data.cassandra.core.cql`. Trong mã sản xuất, **không bỏ qua** `equals`/`hashCode` của khóa và đảm bảo các getter/setter hoặc cơ chế ánh xạ tương ứng hoạt động đúng.

```java
// OrderByStatus.java (lược bỏ import)
@Table("orders_by_tenant_status")
public class OrderByStatus {

    @PrimaryKey
    private OrderKey key;

    @Column("amount")
    private BigDecimal amount;

    public OrderByStatus() {}

    public OrderKey getKey() { return key; }
    public void setKey(OrderKey key) { this.key = key; }

    public BigDecimal getAmount() { return amount; }
    public void setAmount(BigDecimal amount) { this.amount = amount; }
}
```

Nếu dữ liệu đến từ một bảng tối ưu cho màn hình đọc, có thể coi `OrderByStatus` là **read model**. Một đơn hàng có thể được ghi sang nhiều bảng theo các access pattern khác nhau; ứng dụng phải xác định rõ cách duy trì dữ liệu nhất quán giữa chúng.

## 4. Tạo contract của fragment và ghép vào repository

Fragment trả về DTO để phần service không phải biết chi tiết ánh xạ khóa Cassandra.

```java
// OrderSummary.java
public record OrderSummary(
        UUID orderId,
        Instant createdAt,
        BigDecimal amount
) {}
```

```java
// OrderSearchFragment.java
public interface OrderSearchFragment {

    List<OrderSummary> findRecent(
            UUID tenantId,
            String status,
            Instant since,
            int limit
    );
}
```

```java
// OrderRepository.java
public interface OrderRepository
        extends CassandraRepository<OrderByStatus, OrderKey>,
                OrderSearchFragment {
}
```

Khi Spring Data tạo `OrderRepository`, các phương thức thuộc `CassandraRepository` được cung cấp bởi phần base repository; phương thức `findRecent` được chuyển tới fragment implementation.

**Quy ước nhận diện:** interface tên `OrderSearchFragment` đi với lớp `OrderSearchFragmentImpl` (hậu tố `Impl` mặc định). Đặt implementation trong package được Spring Data repository scanning tìm thấy, thường cùng package hoặc package con phù hợp. Nếu tùy biến hậu tố triển khai trong cấu hình repository, cần áp dụng nhất quán. Chỉ sử dụng **một** trong hai implementation dưới đây tại một thời điểm.

## 5. Cách A — Fragment dùng CassandraOperations / CassandraTemplate

`CassandraTemplate` triển khai `CassandraOperations`. Tiêm `CassandraOperations` qua constructor giúp code dễ kiểm thử và giảm phụ thuộc vào lớp cụ thể.

```java
// OrderSearchFragmentImpl.java (lược bỏ import)
public class OrderSearchFragmentImpl implements OrderSearchFragment {

    private final CassandraOperations cassandra;

    public OrderSearchFragmentImpl(CassandraOperations cassandra) {
        this.cassandra = cassandra;
    }

    @Override
    public List<OrderSummary> findRecent(
            UUID tenantId, String status, Instant since, int limit) {

        validate(tenantId, status, since, limit);

        Query query = Query
                .query(Criteria.where("tenant_id").is(tenantId))
                .and(Criteria.where("status").is(status))
                .and(Criteria.where("created_at").gte(since))
                .limit(limit);

        return cassandra.select(query, OrderByStatus.class)
                .stream()
                .map(row -> new OrderSummary(
                        row.getKey().getOrderId(),
                        row.getKey().getCreatedAt(),
                        row.getAmount()))
                .toList();
    }

    private static void validate(
            UUID tenantId, String status, Instant since, int limit) {

        if (tenantId == null || since == null ||
                status == null || status.isBlank()) {
            throw new IllegalArgumentException("Thiếu tham số truy vấn");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit phải nằm trong [1, 100]");
        }
    }
}
```

Để đoạn ví dụ chạy được, cần thêm import Java/Spring phù hợp và các accessors trong `OrderKey`: `getOrderId()`, `getCreatedAt()`. `CassandraOperations.select(query, OrderByStatus.class)` dùng mapping metadata để chuyển kết quả thành entity; code không cần đọc `Row` bằng tay.

**Ưu điểm của Template:**

- Tận dụng mapping của `@Table`, `@PrimaryKey`, converter và các quy tắc ánh xạ kiểu dữ liệu.
- Query API dễ kết hợp cùng DTO/domain code và viết unit test qua mock `CassandraOperations`.
- Không phải viết toàn bộ CQL/row mapping cho truy vấn tương đối đơn giản.

**Giới hạn cần hiểu:** Query API không làm thay đổi cách Cassandra xử lý dữ liệu. Việc truy vấn được biểu diễn bằng `Criteria` không chứng minh rằng câu CQL phát ra là tối ưu. Cần kiểm tra CQL thực tế, partition key, kế hoạch paging và tải thử với dữ liệu đủ lớn. Cũng không nên coi Template là lựa chọn duy nhất cho các truy vấn đòi hỏi tùy chọn driver chuyên biệt.

## 6. Cách B — Fragment dùng trực tiếp CqlSession

Khi cần kiểm soát CQL và tùy chọn của từng câu lệnh, có thể thay nội dung lớp `OrderSearchFragmentImpl` ở phần trên bằng triển khai sử dụng DataStax Java Driver 4 (`com.datastax.oss.driver.api.core.CqlSession`).

```java
// OrderSearchFragmentImpl.java — phương án thay thế (lược bỏ import)
public class OrderSearchFragmentImpl implements OrderSearchFragment {

    private static final String FIND_RECENT_CQL = """
            SELECT order_id, created_at, amount
            FROM orders_by_tenant_status
            WHERE tenant_id = ?
              AND status = ?
              AND created_at >= ?
            LIMIT ?
            """;

    private final CqlSession session;
    private final PreparedStatement findRecentStatement;

    public OrderSearchFragmentImpl(CqlSession session) {
        this.session = session;
        this.findRecentStatement = session.prepare(FIND_RECENT_CQL);
    }

    @Override
    public List<OrderSummary> findRecent(
            UUID tenantId, String status, Instant since, int limit) {

        validate(tenantId, status, since, limit);

        BoundStatement bound = findRecentStatement
                .bind(tenantId, status, since, limit)
                .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM);

        ResultSet resultSet = session.execute(bound);
        List<OrderSummary> result = new ArrayList<>();

        for (Row row : resultSet) {
            result.add(new OrderSummary(
                    row.getUuid("order_id"),
                    row.getInstant("created_at"),
                    row.getBigDecimal("amount")));
        }
        return result;
    }

    private static void validate(
            UUID tenantId, String status, Instant since, int limit) {

        if (tenantId == null || since == null ||
                status == null || status.isBlank()) {
            throw new IllegalArgumentException("Thiếu tham số truy vấn");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit phải nằm trong [1, 100]");
        }
    }
}
```

Các lớp driver cần import gồm `CqlSession`, `PreparedStatement`, `BoundStatement`, `ResultSet`, `Row` và `DefaultConsistencyLevel` trong package `com.datastax.oss.driver.api.core` / `...cql`. Trong cấu hình Spring Boot phù hợp, `CqlSession` có thể được inject vào fragment.

Điểm cần chú ý:

- `session.prepare(...)` tạo **prepared statement** một lần lúc xây dựng fragment; giá trị lọc được truyền qua `bind(...)`, giúp tách tham số khỏi chuỗi CQL.
- `LOCAL_QUORUM` là **ví dụ về consistency cho một request**, không phải cấu hình mặc định nên áp dụng đại trà. Chọn mức consistency theo replication factor từng data center, yêu cầu độ mới của dữ liệu, độ trễ và khả năng sẵn sàng.
- `session.execute(...)` là API **blocking**. Nếu ứng dụng theo mô hình reactive, hãy dùng cơ chế truy cập bất đồng bộ/reactive tương ứng thay vì chặn event loop.
- Khi ánh xạ `Row` thủ công, người viết phải kiểm soát tên cột, kiểu dữ liệu, giá trị nullable và các thay đổi schema.

**Tránh CQL nối chuỗi** từ đầu vào, chẳng hạn `"WHERE status = '" + status + "'"`. Prepared statement + bind markers vừa rõ kiểu dữ liệu vừa tránh lỗi injection từ giá trị lọc. Tên bảng/tên cột không thể thay bằng bind marker thông thường; nếu thực sự cần identifier động thì phải kiểm soát bằng danh sách cho phép.

## 7. Chọn Template hay Driver?

| Tiêu chí | `CassandraOperations` / `CassandraTemplate` | `CqlSession` |
| --- | --- | --- |
| Ánh xạ dữ liệu | Dùng Spring Data entity mapping/converter. | Tự ánh xạ `Row` hoặc chủ động dùng converter phù hợp. |
| Biểu diễn truy vấn | `Query`, `Criteria` và API của Template. | CQL rõ ràng, toàn quyền biểu diễn câu lệnh được driver hỗ trợ. |
| Cấu hình riêng cho statement | Phụ thuộc API và cấu hình Spring Data đang dùng. | Trực tiếp đặt consistency, page size, timeout, idempotence… trên statement khi cần. |
| Bảo trì theo schema | Thuận tiện khi entity mapping đã đúng. | Cần cập nhật SQL, tên cột và mapping thủ công khi schema đổi. |
| Kiểm thử đơn vị | Mock `CassandraOperations` thuận tiện. | Có thể mock driver, nhưng integration test thường quan trọng hơn. |
| Trường hợp thường chọn | Truy vấn custom vẫn chủ yếu dựa vào entity. | Truy vấn CQL chuyên biệt, tùy chọn driver chi tiết hoặc ánh xạ DTO tối ưu. |

Hai cách không đối lập về mặt kiến trúc: fragment là **hợp đồng và điểm mở rộng**; Template/Driver là **cách hiện thực hợp đồng**. Cùng một repository có thể sở hữu nhiều fragment khác nhau, mỗi fragment chọn công cụ thích hợp.

## 8. Consistency, paging và hiệu năng trong fragment

### 8.1. Consistency không đồng nghĩa transaction quan hệ

Cassandra là hệ thống phân tán. Consistency level của từng read/write quyết định số replica cần phản hồi cho thao tác tương ứng. Chẳng hạn, `LOCAL_QUORUM` yêu cầu quorum trong local data center; chi phí độ trễ và tính sẵn sàng khác với `LOCAL_ONE`. Việc đọc được kết quả mới nhất còn phụ thuộc mức nhất quán của cả quá trình ghi/đọc, replication factor và các tình huống lỗi.

Không nên mặc định rằng toàn bộ logic nghiệp vụ trong một fragment được bao bọc bởi transaction ACID nhiều hàng. Với luồng cần điều kiện cập nhật, phải đánh giá riêng cơ chế lightweight transaction (`IF` / Paxos) và chi phí của nó; fragment không tự mang lại tính nguyên tử đó.

### 8.2. Phân biệt LIMIT và page size

- `LIMIT 50` (hoặc `Query.limit(50)`) giới hạn **số hàng tối đa** của kết quả CQL.
- Driver page size điều chỉnh **số hàng trả theo mỗi đợt mạng**, không có nghĩa toàn bộ truy vấn chỉ trả một trang. `ResultSet` đồng bộ có thể tự tải các trang tiếp theo khi duyệt hết dữ liệu.
- Với API “xem thêm”, hãy dùng paging state/cursor của Cassandra và buộc cursor vào cùng truy vấn + tham số. Không giả lập phân trang sâu bằng `OFFSET` kiểu SQL quan hệ; CQL không hỗ trợ offset phổ thông theo cách đó.
- Khi API dùng Spring Data, cân nhắc hỗ trợ `Slice`/paging theo cơ chế Cassandra thay cho `Page` nếu việc đếm tổng số hàng là tốn kém hoặc không cần thiết.

Ví dụ sử dụng driver để đọc theo từng đợt có thể gọi `bound.setPageSize(50)` và quản lý paging state. Đây là vấn đề khác với `LIMIT`; cần thiết kế rõ API trả dữ liệu và cursor trước khi triển khai. **Không truyền trực tiếp paging state của khách hàng khác** hoặc của query khác mà không kiểm tra.

### 8.3. Kiểm soát read path

- Điều kiện lọc phải gắn với khóa phân vùng; xác minh câu CQL không phát sinh `ALLOW FILTERING`.
- Đặt giới hạn đầu vào: `limit` hợp lý, thời gian truy vấn có biên, định dạng `status` hợp lệ.
- Theo dõi phân phối kích thước partition, tombstones, read latency và timeout dưới tải.
- Chuẩn bị phương án thay đổi bảng khi access pattern khác xuất hiện; Cassandra thường dùng denormalization.
- Chỉ sử dụng ordering mà khóa clustering hỗ trợ; không mong chờ sort tùy ý trên các partition.

## 9. Kiểm thử và gỡ lỗi

Một fragment cần được kiểm tra ở **hai tầng**:

**Unit test** tập trung vào logic của lớp triển khai: kiểm tra `limit`, tham số rỗng, DTO mapping và việc gọi đúng `CassandraOperations` hoặc driver. Ví dụ, mock `CassandraOperations.select(...)` để xác minh fragment trả `OrderSummary` theo dữ liệu entity giả lập.

**Integration test** chạy với Cassandra thực (có thể dùng Testcontainers), tạo đúng schema và dữ liệu đại diện. Ít nhất nên kiểm tra:

1. Hai tenant có cùng `status` không nhìn thấy dữ liệu của nhau.
2. Biên `created_at >= since` được hiểu đúng; kết quả tuân thủ clustering order.
3. `limit` cắt đúng số hàng; nhiều bản ghi cùng timestamp vẫn được phân biệt bằng `order_id`.
4. Câu CQL chạy mà không cần `ALLOW FILTERING` và không phát sinh lỗi key restriction.
5. Mức consistency đã chọn hoạt động với replication factor môi trường kiểm thử.
6. Nếu có paging, tiếp tục bằng cursor không gây mất/trùng bản ghi trong điều kiện dữ liệu kiểm thử ổn định. Với dữ liệu cập nhật đồng thời, cần làm rõ tính nhất quán mà API cam kết.

Lỗi thường gặp:

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `No property ... found` khi tạo repository | Spring Data cố suy diễn phương thức vì chưa phát hiện fragment implementation. | Kiểm tra repository có `extends OrderSearchFragment`, tên `OrderSearchFragmentImpl`, package scanning và bean registration. |
| Lỗi `InvalidQueryException` về partition/clustering key | Query chưa đủ partition key hoặc có điều kiện không phù hợp thứ tự clustering. | Đối chiếu CQL với DDL; thay bảng nếu access pattern khác. |
| Đọc được qua driver nhưng ánh xạ Template lỗi | Entity/key mapping sai tên, kiểu cột hoặc converter. | Kiểm tra `@Table`, `@PrimaryKeyClass`, `@PrimaryKeyColumn` và getters/constructor. |
| Latency cao, timeout dù có `LIMIT` | Partition lớn, nhiều tombstone, mức consistency không phù hợp hoặc paging/đọc nhiều trang. | Đo kích thước partition, trace/metrics, tối ưu data model và giới hạn phạm vi truy vấn. |
| Kết quả thiếu hoặc không như kỳ vọng | Sai timestamp boundary, write/read consistency hoặc dữ liệu tại bảng đọc chưa đồng bộ. | Kiểm tra đường ghi, quy tắc denormalization, timezone và consistency. |
| Trùng bean hoặc hành vi không xác định | Tồn tại đồng thời hai implementation của cùng fragment/method. | Chỉ giữ một `OrderSearchFragmentImpl` được chọn, cấu hình bean tường minh khi cần. |

## 10. Bài tập áp dụng

1. Triển khai phương thức `findRecent` bằng `CassandraOperations`, dùng bảng và entity của ví dụ. Thử dữ liệu từ nhiều tenant và nhiều trạng thái.
2. Thay implementation bằng `CqlSession` với prepared statement và so sánh CQL phát ra, số hàng, thứ tự, kết quả DTO.
3. Bổ sung `bucket_yyyymm` vào partition key để xử lý partition quá lớn. Mô tả cách API lấy các đơn gần đây qua nhiều bucket mà vẫn có giới hạn số request và số hàng.
4. Thiết kế endpoint trả 50 kết quả mỗi lần và một cursor cho lần gọi sau. Giải thích vì sao dùng paging state phù hợp hơn kiểu “trang 1000” với offset tùy ý.

## 11. Ghi nhớ

**Repository fragment** cho phép mở rộng `CassandraRepository` theo từng nhóm hành vi mà không làm phình interface repository hoặc trộn chi tiết CQL vào service. Chọn `CassandraOperations` khi muốn tận dụng entity mapping và Query API; chọn `CqlSession` khi cần quyền kiểm soát CQL/driver chi tiết. Dù dùng cách nào, hiệu năng và độ đúng của truy vấn trước hết được quyết định bởi **partition key, clustering key, consistency, paging và cách tổ chức dữ liệu theo truy vấn**.

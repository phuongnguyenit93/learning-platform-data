# Query, Criteria và dựng điều kiện theo khóa với CassandraTemplate

Trong **Spring Data Cassandra**, `CassandraTemplate` cung cấp API truy cập Apache Cassandra ở mức thấp hơn repository nhưng vẫn hỗ trợ ánh xạ entity và chuyển đổi kiểu. Hai đối tượng thường gặp nhất khi cần dựng truy vấn là **`Query`** và **`Criteria`**: `Criteria` mô tả điều kiện trên cột; `Query` tập hợp các điều kiện cùng giới hạn hoặc tùy chọn thực thi; `CassandraTemplate` gửi truy vấn và ánh xạ kết quả về Java.

Điểm quan trọng là **Query/Criteria không biến Cassandra thành cơ sở dữ liệu SQL cho phép lọc tùy ý**. Điều kiện dựng trong Java phải tuân theo cấu trúc **partition key**, **clustering columns**, quy tắc CQL và giới hạn thực tế của hệ phân tán. Nếu dựng đúng cú pháp API nhưng thiếu thành phần khóa, truy vấn vẫn có thể bị Cassandra từ chối hoặc có chi phí quá lớn.

Bài này thuộc chương **CassandraTemplate** của module **SPRING_DATA_CASSANDRA**. Chúng ta sẽ dùng một ví dụ xuyên suốt để học cách thiết kế bảng theo truy vấn, dựng điều kiện tĩnh và động, đọc một hàng hoặc nhiều hàng, xử lý thời gian, paging, tính nhất quán và kiểm soát hiệu năng.

## 1. Vai trò của Query, Criteria và CassandraTemplate

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| `Criteria` | Biểu diễn phép so sánh trên một cột | `Criteria.where("tenant_id").is(tenantId)` |
| `Query` | Gom điều kiện và giới hạn/trình bày truy vấn | `Query.query(criteria).limit(20)` |
| `CassandraOperations` | Giao diện các thao tác với entity và truy vấn | `operations.select(query, OrderRow.class)` |
| `CassandraTemplate` | Triển khai phổ biến của `CassandraOperations` | Bean được inject vào service |
| `CqlSession` | API Java Driver để chạy CQL trực tiếp | Prepared `SELECT ... WHERE ...` |

Luồng dữ liệu:

~~~text
HTTP / nghiệp vụ
    |
    v
Service xác định tenant, customer, month, giới hạn
    |
    v
Query + Criteria  ---> Spring Data Cassandra Mapping
    |                       |
    +-----------+-----------+
                v
         CassandraTemplate
                |
                v
          Java Driver / CQL
                |
                v
          Cassandra replicas
                |
                v
          Row -> entity Java
~~~

`CassandraTemplate` hữu ích khi một service cần điều kiện được xây dựng trong mã Java, thay vì khai báo một phương thức repository riêng cho từng tổ hợp bộ lọc. Tuy nhiên, **mọi tổ hợp điều kiện được phép** vẫn phải có đường truy cập hợp lý theo schema; không nên cho phép client gửi tên cột và toán tử tùy ý rồi đưa thẳng vào `Criteria`.

## 2. Bắt đầu bằng truy vấn nghiệp vụ và thiết kế bảng

Giả sử API cần:

~~~text
GET /tenants/{tenantId}/customers/{customerId}/orders
    ?month=2026-11
    &limit=20

Kết quả: các đơn hàng mới nhất của khách trong tháng.
~~~

Một bảng CQL đáp ứng trực tiếp:

~~~sql
CREATE TABLE orders_by_customer_month (
    tenant_id uuid,
    customer_id uuid,
    month_bucket date,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

`tenant_id`, `customer_id`, `month_bucket` là ba thành phần **composite partition key**. `created_at` và `order_id` là **clustering columns**, lần lượt giúp sắp xếp theo thời gian và phân biệt những đơn cùng thời điểm tạo.

| Thành phần khóa | Giá trị minh họa | Hệ quả |
|---|---|---|
| `tenant_id` | Tenant A | Không lẫn khách giữa các tenant |
| `customer_id` | Khách C1 | Phạm vi một khách hàng |
| `month_bucket` | Ngày đầu tháng 11/2026 | Giới hạn kích thước partition theo tháng |
| `created_at` | 2026-11-25T09:10:00Z | Đọc đơn mới hơn trước |
| `order_id` | UUID đơn hàng | Giúp định danh duy nhất một hàng khi cùng timestamp |

CQL tương ứng với hợp đồng API:

~~~sql
SELECT tenant_id, customer_id, month_bucket,
       created_at, order_id, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Truy vấn có **đủ partition key** để Cassandra định vị partition, rồi đọc các hàng đầu tiên theo clustering order. Nếu muốn lịch sử tháng 10 và tháng 11, phải xử lý **hai partition** (và việc ghép/trộn kết quả) thay vì tưởng rằng một paging state của tháng 11 dùng được cho tháng 10.

**Chọn khóa theo truy vấn trước, viết `Criteria` sau.** Đó là thứ tự làm việc giúp tránh thiết kế API linh hoạt trên giấy nhưng không phù hợp với Cassandra khi chạy thật.

## 3. Entity mapping cho bảng có khóa ghép

Để template chuyển một `Row` thành object, cần một entity có metadata đúng schema. Mô hình khóa ghép:

~~~java
package example.orders;

import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class CustomerMonthOrderKey implements Serializable {

    @PrimaryKeyColumn(name = "tenant_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(name = "customer_id", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(name = "month_bucket", ordinal = 2,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate monthBucket;

    @PrimaryKeyColumn(name = "created_at", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID orderId;

    public CustomerMonthOrderKey() {}

    // Bổ sung constructor, getters/setters, equals/hashCode trên cả năm field
    // trước khi đưa lớp khóa này vào ứng dụng thực tế.
}
~~~

Ở đây, các ordinal **0, 1, 2, 3, 4** mô tả thứ tự toàn bộ primary key. Giá trị `PrimaryKeyType.PARTITIONED` hoặc `CLUSTERED` cho biết từng cột thuộc phần nào của khóa. Kiểu `PrimaryKeyType` được import từ package `org.springframework.data.cassandra.core.cql`.

Entity:

~~~java
package example.orders;

import java.math.BigDecimal;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_month")
public class CustomerMonthOrder {

    @PrimaryKey
    private CustomerMonthOrderKey id;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    public CustomerMonthOrder() {}

    public CustomerMonthOrderKey getId() { return id; }
    public void setId(CustomerMonthOrderKey id) { this.id = id; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public BigDecimal getTotalAmount() { return totalAmount; }
    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }
}
~~~

Các đoạn mã ánh xạ trên trình bày cấu trúc thiết yếu; lớp khóa phải được hoàn thiện (accessors, equality, cách tạo ID ổn định) trước khi dùng trong ví dụ chạy thực. `Instant` tương ứng CQL `timestamp` với độ chính xác mili giây; nếu dùng giá trị có nano giây, cần chính sách chuẩn hóa/kiểm chứng rõ ràng.

`@Table` và `@PrimaryKeyClass` không tự bảo đảm schema đã tồn tại. Trong production, keyspace và bảng thường được tạo bằng migration CQL có kiểm soát; template chỉ dùng mapping để truy vấn và chuyển đổi dữ liệu.

## 4. Tiêm CassandraOperations vào service

Thông thường Spring Boot cấu hình `CqlSession`, các thành phần Spring Data Cassandra và bean template tương ứng khi có dependency/cấu hình phù hợp. Service nên phụ thuộc vào **giao diện `CassandraOperations`**:

~~~java
import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final CassandraOperations operations;

    public OrderQueryService(CassandraOperations operations) {
        this.operations = operations;
    }

    // Các phương thức Query/Criteria ở phần tiếp theo
    // được đặt trong service này.
}
~~~

`CassandraTemplate` là triển khai phổ biến của `CassandraOperations`. **Không cần tạo `CqlSession` mới cho mỗi HTTP request**: session quản lý metadata, kết nối và tài nguyên driver; hãy dùng bean được quản lý vòng đời.

Nếu ứng dụng có nhiều template/session cho nhiều keyspace, nên cấu hình bean rõ ràng và tránh inject nhầm template vào keyspace khác.

## 5. Tạo truy vấn theo toàn bộ partition key

Các import cần dùng:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;
~~~

Phương thức trong `OrderQueryService`:

~~~java
public List<CustomerMonthOrder> findRecent(
        UUID tenantId, UUID customerId, LocalDate monthBucket) {

    Query query = Query.query(Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("customer_id").is(customerId))
            .and(Criteria.where("month_bucket").is(monthBucket))
            .limit(20);

    return operations.select(query, CustomerMonthOrder.class);
}
~~~

Đối chiếu từng thành phần:

| Java API | Phần CQL tương ứng | Ý nghĩa |
|---|---|---|
| `Criteria.where("tenant_id").is(tenantId)` | `tenant_id = ?` | Thành phần 1 của partition key |
| `.and(Criteria.where("customer_id").is(customerId))` | `AND customer_id = ?` | Thành phần 2 |
| `.and(Criteria.where("month_bucket").is(monthBucket))` | `AND month_bucket = ?` | Thành phần 3 |
| `.limit(20)` | `LIMIT 20` | Giới hạn số hàng trong kết quả |
| `operations.select(...)` | Chạy truy vấn và ánh xạ các hàng | `List<CustomerMonthOrder>` |

`Criteria` chọn **tên cột CQL** đúng với schema/mapping; không tùy ý dùng tên Java `monthBucket` khi trong bảng tên thật là `month_bucket`. Nên tránh tạo tên cột từ chuỗi người dùng nhập.

Trong ví dụ này, `LocalDate.of(2026, 11, 1)` đại diện cho tháng 11. Cả writer và reader phải dùng cùng quy tắc bucket (ví dụ luôn ngày 1), không dùng ngày hiện tại ngẫu nhiên rồi mong truy vấn sẽ tìm được dữ liệu.

### 5.1. Truy vấn một hàng và nhiều hàng khác nhau thế nào?

`select(query, Entity.class)` trả danh sách hàng. `selectOne(query, Entity.class)` chỉ thích hợp khi **truy vấn được thiết kế để trả tối đa một hàng**. Chẳng hạn, nếu đã biết đầy đủ năm thành phần primary key:

~~~java
public CustomerMonthOrder findExact(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        Instant createdAt, UUID orderId) {

    Query query = Query.query(Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("customer_id").is(customerId))
            .and(Criteria.where("month_bucket").is(monthBucket))
            .and(Criteria.where("created_at").is(createdAt))
            .and(Criteria.where("order_id").is(orderId));

    return operations.selectOne(query, CustomerMonthOrder.class);
}
~~~

Cần import `java.time.Instant` cho ví dụ. Khi không có hàng, kết quả của `selectOne` có thể là `null`, vì vậy service nên chuyển sang `Optional` hoặc chính sách 404/not found ở tầng phù hợp, thay vì mặc định đối tượng luôn tồn tại.

**Sai lầm cần tránh:** không dùng `selectOne` chỉ vì UI “hiện một đơn” nhưng truy vấn thiếu clustering key. Nếu query có thể trả nhiều hàng, phải quyết định thứ tự, `LIMIT` và quy tắc chọn hàng trước.

## 6. Dựng điều kiện trên clustering columns

Vì `created_at` là clustering column đầu tiên, ứng dụng có thể lọc khoảng thời gian **bên trong một partition đã biết**. Ví dụ sản phẩm muốn lấy đơn từ 09:00 đến trước 12:00 UTC trong ngày 25/11:

~~~sql
SELECT *
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at >= '2026-11-25T09:00:00+00:00'
  AND created_at <  '2026-11-25T12:00:00+00:00'
LIMIT 100;
~~~

Sử dụng `gte` (*greater than or equal*) và `lt` (*less than*) trong API `Criteria`:

~~~java
public List<CustomerMonthOrder> findInWindow(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        Instant fromInclusive, Instant toExclusive) {

    if (fromInclusive == null || toExclusive == null
            || !fromInclusive.isBefore(toExclusive)) {
        throw new IllegalArgumentException("Invalid time window");
    }

    Query query = Query.query(Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("customer_id").is(customerId))
            .and(Criteria.where("month_bucket").is(monthBucket))
            .and(Criteria.where("created_at").gte(fromInclusive))
            .and(Criteria.where("created_at").lt(toExclusive))
            .limit(100);

    return operations.select(query, CustomerMonthOrder.class);
}
~~~

Đoạn code minh họa cú pháp `Query/Criteria` với hai điều kiện biên trên một cột. Khi triển khai thật, hãy kiểm tra hành vi tạo statement trong phiên bản Spring Data Cassandra đang sử dụng; có thể dùng CQL có tham số qua driver khi muốn kiểm soát chính xác cấu trúc câu lệnh.

Tại sao lại dùng **khoảng nửa mở** `[from, to)`? Vì hai khoảng liên tiếp như `[09:00, 10:00)` và `[10:00, 11:00)` không trùng ở mốc 10:00. Tuy nhiên, độ chính xác `timestamp` của Cassandra là mili giây; phải đồng nhất chính sách làm tròn/chuẩn hóa `Instant` khi ghi và lọc.

### 6.1. Điều kiện được phép theo thứ tự khóa

Với schema minh họa:

~~~text
Partition key:  tenant_id, customer_id, month_bucket
Clustering:     created_at, order_id
~~~

Các trường hợp tiêu biểu:

| Điều kiện `WHERE` | Có phù hợp với primary-key path không? | Giải thích |
|---|---|---|
| Ba thành phần partition key | **Có** | Định vị đúng partition |
| Partition key + `created_at >= ?` | **Có** | Range trên clustering column đầu |
| Partition key + `created_at = ? AND order_id = ?` | **Có** | Đủ khóa của một hàng |
| Chỉ `customer_id = ?` | **Không** | Thiếu `tenant_id` và `month_bucket` |
| Partition key + `order_id = ?`, bỏ `created_at` | **Không theo lối chuẩn** | Bỏ qua clustering column đứng trước |
| Partition key + `status = 'PAID'` | **Không theo lối chuẩn** | `status` là cột thường, chưa có index hỗ trợ |
| Partition key + `ORDER BY total_amount DESC` | **Không** | `total_amount` không phải clustering column |

Không phải mọi truy vấn không khớp primary-key path đều **bị từ chối trong mọi cấu hình**: index hoặc tính năng đặc thù phiên bản có thể mở rộng cách lọc. Nhưng nếu mục tiêu là truy vấn tải cao với độ trễ dễ dự đoán, hãy ưu tiên đường truy cập được thiết kế sẵn theo partition/clustering.

## 7. Điều kiện động: cái gì có thể tùy chọn, cái gì phải bắt buộc?

Một API có thể nhận khoảng thời gian tùy chọn nhưng **không được** cho phép thiếu một phần partition key một cách vô tình. Tách hai nhóm:

- **Bắt buộc:** `tenantId`, `customerId`, `monthBucket`; thiếu giá trị thì báo lỗi request trước khi tạo `Query`.
- **Tùy chọn có kiểm soát:** một mốc thời gian `created_at` để lấy đơn từ thời điểm đó trở đi; giá trị phải nằm trong tháng/bucket theo hợp đồng.

Ví dụ:

~~~java
import java.util.Objects;

public List<CustomerMonthOrder> search(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        Instant createdFrom, int requestedLimit) {

    Objects.requireNonNull(tenantId, "tenantId");
    Objects.requireNonNull(customerId, "customerId");
    Objects.requireNonNull(monthBucket, "monthBucket");

    int safeLimit = Math.max(1, Math.min(requestedLimit, 100));

    Query query = Query.query(Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("customer_id").is(customerId))
            .and(Criteria.where("month_bucket").is(monthBucket));

    if (createdFrom != null) {
        query.and(Criteria.where("created_at").gte(createdFrom));
    }

    query.limit(safeLimit);
    return operations.select(query, CustomerMonthOrder.class);
}
~~~

Đây là ví dụ **điều kiện động nhưng vẫn có đường đọc cố định**: luôn biết partition, chỉ thêm bộ lọc clustering hợp lệ. Việc clamp `limit` minh họa cách giới hạn số hàng; trong API thực tế có thể **từ chối** giá trị không hợp lệ thay vì tự sửa thầm, tùy hợp đồng của sản phẩm.

### 7.1. Khi client muốn thêm `status` thì sao?

Không nên tự động viết:

~~~java
// Cách dễ sai với schema hiện tại:
query.and(Criteria.where("status").is("PAID"));
~~~

`status` không thuộc primary key, chưa có index và không tạo đường đọc theo trạng thái. Với nhu cầu “20 đơn `PAID` mới nhất của một khách trong tháng” xuất hiện thường xuyên, một bảng truy cập phù hợp hơn:

~~~sql
CREATE TABLE orders_by_customer_status_month (
    tenant_id uuid,
    customer_id uuid,
    status text,
    month_bucket date,
    created_at timestamp,
    order_id uuid,
    total_amount decimal,
    PRIMARY KEY (
        (tenant_id, customer_id, status, month_bucket),
        created_at, order_id
    )
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Truy vấn:

~~~sql
SELECT * FROM orders_by_customer_status_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND status = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Trong thiết kế mới, `status` **là thành phần partition key**, nên phù hợp. Đánh đổi: đơn hàng đổi trạng thái phải được phản ánh vào bảng projection, có thể cần xóa hàng ở partition trạng thái cũ và ghi hàng ở partition mới. Cần idempotency, đối soát, quản lý tombstone và chính sách consistency; `Query` trong Java không tự đồng bộ dữ liệu giữa hai bảng.

Nếu nhu cầu theo trạng thái hiếm và dữ liệu giới hạn chặt trong một partition nhỏ, có thể đánh giá lọc ở tầng ứng dụng hoặc index tương thích, nhưng phải đo chi phí và bảo đảm kết quả đúng với `LIMIT`. **Không dùng `ALLOW FILTERING` như giải pháp mặc định** để vượt qua thiết kế khóa không phù hợp.

## 8. Template khác repository và CQL trực tiếp ra sao?

Cả ba cách đều truy cập cùng dữ liệu CQL, nhưng có điểm mạnh khác nhau:

| Cách viết | Phù hợp khi | Điểm cần kiểm soát |
|---|---|---|
| `CassandraRepository` | CRUD theo ID, phương thức truy vấn ổn định | Không viết method name tùy ý vượt khả năng của schema |
| `CassandraTemplate` + `Query/Criteria` | Dựng bộ lọc hợp lệ, ánh xạ nhiều entity, dùng DSL | Đảm bảo mọi nhánh động có đủ khóa và giới hạn |
| `CqlSession` + prepared CQL | Cần kiểm soát chính xác statement, driver options hoặc CQL đặc biệt | Bind đúng kiểu, mapping thủ công hoặc dùng converter |

Ví dụ repository tương đương câu truy vấn theo partition:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface CustomerMonthOrderRepository
        extends CassandraRepository<CustomerMonthOrder, CustomerMonthOrderKey> {

    @Query("SELECT * FROM orders_by_customer_month "
         + "WHERE tenant_id = ?0 AND customer_id = ?1 "
         + "AND month_bucket = ?2 LIMIT 20")
    List<CustomerMonthOrder> findRecent(
            UUID tenantId, UUID customerId, LocalDate monthBucket);
}
~~~

Nếu chỉ cần truy vấn trên, repository có thể là lựa chọn đơn giản nhất. Template có ích khi thêm **các bộ lọc clustering tùy chọn có kiểm soát** mà vẫn muốn mapping về entity.

Ví dụ CQL trực tiếp:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public ResultSet findRaw(
        CqlSession session, UUID tenantId, UUID customerId,
        LocalDate monthBucket) {

    PreparedStatement statement = session.prepare(
            "SELECT * FROM orders_by_customer_month "
          + "WHERE tenant_id = ? AND customer_id = ? "
          + "AND month_bucket = ? LIMIT 20");

    return session.execute(
            statement.bind(tenantId, customerId, monthBucket));
}
~~~

Đây là **minh họa phương thức**, không phải class Java độc lập. Trong production, prepared statement thường nên được chuẩn bị và tái sử dụng phù hợp với vòng đời session thay vì prepare lại trên mọi request. Driver giúp bind tham số kiểu UUID/date; đừng nối trực tiếp giá trị chưa tin cậy vào chuỗi CQL.

`ResultSet` ở API driver không tự chuyển thành `CustomerMonthOrder` như `CassandraTemplate`; nếu dùng CQL trực tiếp, ứng dụng phải xác định cách giải mã `Row` hoặc sử dụng mapping phù hợp.

## 9. Query/Criteria và paging: hai trách nhiệm khác nhau

Một truy vấn hợp lệ vẫn có thể trả về rất nhiều hàng trong cùng partition. Với Cassandra, phân trang đi theo **paging state** chứ không phải cơ chế `OFFSET` tùy ý. `LIMIT` hạn chế số hàng trả về của truy vấn, còn paging kiểm soát việc đọc kết quả theo từng trang.

Ví dụ dùng repository có thể trả `Slice<T>`:

~~~java
import java.time.LocalDate;
import java.util.UUID;

import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.cassandra.repository.Query;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

// Phương thức trong CustomerMonthOrderRepository:
@Query("SELECT * FROM orders_by_customer_month "
     + "WHERE tenant_id = ?0 AND customer_id = ?1 AND month_bucket = ?2")
Slice<CustomerMonthOrder> findInMonth(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        Pageable pageable);

// Đoạn gọi trong service:
Slice<CustomerMonthOrder> first =
        repository.findInMonth(
                tenantId, customerId, monthBucket,
                CassandraPageRequest.first(20));

if (first.hasNext()) {
    Slice<CustomerMonthOrder> second =
            repository.findInMonth(
                    tenantId, customerId, monthBucket,
                    first.nextPageable());
}
~~~

Ví dụ cố ý trình bày **chữ ký repository và lời gọi service cùng một khối** cho dễ theo dõi; khi triển khai hãy đặt chúng ở class phù hợp. API paging của template/repository cần đối chiếu với phiên bản Spring Data Cassandra đang dùng.

Một số nguyên tắc:

- **Paging state thuộc về truy vấn**, gồm keyspace, bảng, điều kiện, giá trị tham số và cách thực thi tương thích; không tái dùng cho customer hoặc tháng khác.
- Nếu dùng `Query/Criteria` với template, hãy chọn API paging phù hợp của phiên bản thư viện để lấy tiếp trang. **Không** lấy `select(...)` toàn bộ rồi `subList` để giả làm paging.
- Nếu cần liệt kê nhiều partition/tháng, ứng dụng phải quản lý trạng thái riêng và hợp nhất kết quả theo chính sách thứ tự; không có cursor toàn cục tự động.
- Page size không sửa được hot partition; cần đo kích thước partition, lượng dữ liệu trên mỗi truy vấn và số request song song.

## 10. Consistency, timeout và truy vấn phân tán

`CassandraTemplate` làm việc trên Java Driver nhưng không tự quyết định mức nhất quán nghiệp vụ. Các mức như `LOCAL_ONE` và `LOCAL_QUORUM` mô tả số phản hồi replica cần thiết theo chính sách read/write và replication factor của keyspace. Chúng độc lập với lựa chọn `Query`, `Criteria` hay repository.

Giả sử keyspace có replication factor 3 trong local DC. `LOCAL_QUORUM` thường cần **hai replica ở local DC** đáp ứng, đổi lại có thể tăng chi phí so với `LOCAL_ONE`. Đây chỉ là ví dụ: lựa chọn thực tế phải cân nhắc yêu cầu nhất quán, lỗi node và độ trễ.

Khi cần kiểm soát statement-specific consistency, timeout hoặc fetch size, hãy kiểm tra khả năng cấu hình tại tầng Spring Data đang dùng hoặc dùng Java Driver trực tiếp cho thao tác đặc biệt. Không nên gán tùy tiện consistency khác nhau cho hai phần của cùng một quy trình nghiệp vụ rồi giả định dữ liệu luôn nhìn thấy đồng thời giữa nhiều bảng.

### 10.1. Những chỉ số hiệu năng cần quan sát

- p50/p95/p99 latency khi đọc đúng một partition và khi đọc nhiều partition.
- Số request đang xử lý, timeout, retry và kết quả timeout chưa rõ đã thực thi hay chưa.
- Kích thước partition theo percentile, hot key/hot partition và tombstones.
- Số hàng trả về, số trang đọc, fetch size, payload/network traffic và heap/GC.
- Tần suất truy vấn sai đường khóa, truy vấn cần `ALLOW FILTERING` hoặc bộ lọc ứng dụng đọc quá nhiều hàng.
- Độ trễ cập nhật giữa các bảng projection, nếu một đơn được lưu dưới nhiều access pattern.

Không tăng timeout vô hạn hoặc tăng số luồng để che đi một truy vấn thiếu partition key. Cần đo dữ liệu và schema trước, sau đó tinh chỉnh concurrency/driver nếu cần.

## 11. Sai lầm thường gặp khi dựng Query và Criteria

| Sai lầm | Hiện tượng | Hướng sửa |
|---|---|---|
| Thiếu một thành phần composite partition key | Query không thực thi theo đường primary key | Validate đủ `tenantId/customerId/monthBucket` |
| Dùng field Java thay cho tên cột CQL | Cột không tồn tại hoặc mapping không như dự định | Dùng tên cột đúng schema; kiểm tra `@Column` |
| Xây `Criteria` theo filter tùy ý của client | Lọc trên cột thường, quét ngoài kiểm soát | Whitelist query pattern, thiết kế access table/index |
| Lọc `order_id` nhưng bỏ `created_at` | Không đi theo clustering order | Dùng toàn bộ khóa hoặc truy cập bảng theo ID |
| Dùng `ORDER BY total_amount` | CQL không hỗ trợ sort theo cột thường | Bảng đọc theo tổng tiền hoặc giải pháp phù hợp |
| `selectOne` trên query có thể trả nhiều hàng | Kết quả không phản ánh contract | Định nghĩa đầy đủ khóa hoặc thứ tự và giới hạn |
| Tin rằng `LIMIT 20` luôn làm máy chủ đọc 20 hàng | Lọc hậu kiểm có thể phải đọc nhiều hơn | Tránh lọc không theo khóa, đo số hàng quét |
| Dùng `ALLOW FILTERING` để sửa mọi lỗi | Độ trễ bất ổn, có thể đọc quá nhiều | Thiết kế bảng theo truy vấn hoặc index đã benchmark |
| Lấy `List` lớn rồi `subList` | Tốn bộ nhớ, không paging ở Cassandra | Dùng paging state / `Slice` |
| Tự tạo `CqlSession` trong mỗi lần gọi | Quá nhiều kết nối và tài nguyên | Dùng bean session/template chia sẻ |
| Retry thao tác ghi với ID được sinh mới | Tạo hàng trùng nghiệp vụ | Giữ ID và payload ổn định, cân nhắc idempotency |

### 11.1. Phân biệt lọc ở CQL với lọc ở Java

Giả sử ứng dụng viết:

~~~java
List<CustomerMonthOrder> orders = operations.select(query, CustomerMonthOrder.class);
List<CustomerMonthOrder> paid = orders.stream()
        .filter(order -> "PAID".equals(order.getStatus()))
        .toList();
~~~

Đây là **lọc ở Java** sau khi Cassandra đã trả dữ liệu. Nếu `query.limit(20)` thì `paid` có thể chứa 0–20 đơn `PAID`, **không phải 20 đơn `PAID` mới nhất** của tháng. Lọc ứng dụng chỉ phù hợp nếu toàn bộ tập đầu vào nhỏ, có giới hạn chặt và hợp đồng API chấp nhận kết quả ấy. Với yêu cầu lấy chính xác 20 đơn đã thanh toán gần nhất, cần access table theo trạng thái hoặc chiến lược đọc được chứng minh tương đương về mặt kết quả.

## 12. Kiểm thử truy vấn và kiểm tra CQL thật

Việc viết `Criteria` đúng về mặt Java chưa chứng minh Cassandra hỗ trợ truy vấn. Một quy trình kiểm thử nên bao gồm:

1. **Xác nhận schema**: bảng, keyspace, partition key và clustering order.
2. **Kiểm tra query contract**: các thành phần khóa bắt buộc luôn có mặt; limit được giới hạn.
3. **Thử dữ liệu thật**: có nhiều đơn trong cùng tháng, hai đơn cùng `created_at`, nhiều khách và nhiều tenant.
4. **So sánh kết quả template với CQL có tham số**: cùng tenant/customer/month cho cùng kết quả và thứ tự hợp lệ.
5. **Thử giá trị biên**: đầu/cuối tháng, `Instant` ở UTC, tháng không có dữ liệu, UUID không tồn tại.
6. **Đo tải**: p95/p99, paging, hot partition, timeout và số truy vấn song song.

Kiểm tra cấu trúc schema trong `cqlsh`:

~~~text
-- DESCRIBE là lệnh của cqlsh, không phải CQL prepared statement.
DESCRIBE TABLE orders_by_customer_month;
~~~

Hoặc đọc system schema:

~~~sql
SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'app_data'
  AND table_name = 'orders_by_customer_month';
~~~

Thay `app_data` bằng keyspace đang dùng. Kết quả phải cho thấy ba cột `partition_key` và hai cột `clustering` theo thứ tự được thiết kế. Việc dùng `@PrimaryKeyClass` trong Java không tự thay primary key của bảng Cassandra đã có dữ liệu.

### 12.1. Một khung integration test

Khi dự án có Cassandra test instance và schema fixture, có thể viết:

~~~java
@Test
void findRecentUsesTheExpectedPartitionAndOrder() {
    // Given: fixture đã ghi ba đơn cùng tenant/customer/month,
    // hai đơn ở tháng khác và một đơn thuộc tenant khác.
    List<CustomerMonthOrder> result =
            service.findRecent(tenantId, customerId, monthBucket);

    assertEquals(3, result.size());
    // Kiểm tra mọi result có cùng partition key.
    // Kiểm tra thứ tự created_at giảm dần,
    // và order_id làm khóa phá hòa theo CQL.
}
~~~

Ví dụ là **khung test**: cần tạo fixture, thực thi với Cassandra thật và bổ sung assertions cụ thể trong dự án, không được coi là test đã chạy. Unit test mock `CassandraOperations` giúp kiểm tra nhánh dựng query nhưng không thay thế integration test vì mock không xác minh quy tắc CQL.

## 13. Bài tập thực hành

Một hệ thống logistics có API:

~~~text
GET /packages/{packageId}/events?day=2026-11-25&limit=50
~~~

Schema:

~~~sql
CREATE TABLE package_events_by_day (
    package_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    hub_id uuid,
    event_type text,
    PRIMARY KEY ((package_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

**Yêu cầu:**

1. Viết `Query.query(Criteria.where("package_id").is(packageId))`, bổ sung điều kiện `event_day`, giới hạn 50 và gọi `operations.select(query, PackageEvent.class)`.
2. Bổ sung bộ lọc tùy chọn `occurred_at >= fromInclusive` nhưng vẫn luôn có **đầy đủ partition key**.
3. Giải thích vì sao truy vấn chỉ có `hub_id = ?` không phù hợp bảng này.
4. Thiết kế bảng `events_by_hub_day` nếu cần đọc 50 sự kiện mới nhất của một kho trong một ngày; cân nhắc bucket/shard khi một kho quá nóng.
5. Nêu cách phân trang 500 sự kiện, và vì sao không lấy 500 hàng rồi chia thành mười `List` ở service.

Một lời giải khung cho (1)–(2):

~~~java
Query query = Query.query(Criteria.where("package_id").is(packageId))
        .and(Criteria.where("event_day").is(day));

if (fromInclusive != null) {
    query.and(Criteria.where("occurred_at").gte(fromInclusive));
}

query.limit(50);
List<PackageEvent> events = operations.select(query, PackageEvent.class);
~~~

Với (3), `hub_id` chỉ là cột thường: không định vị được partition. Với (4), cần một đường đọc có `hub_id` và ngày/bucket trong partition key, cùng clustering theo thời điểm sự kiện. Với (5), paging phải diễn ra ở Cassandra thông qua paging state và truy vấn tương thích.

### Câu hỏi tự kiểm tra

1. `Criteria` và `Query` khác nhau ở vai trò nào?
2. Vì sao `Query.query(Criteria.where("customer_id").is(id))` không đủ với partition key `(tenant_id, customer_id, month_bucket)`?
3. Khi nào nên dùng `selectOne` thay vì `select`?
4. `created_at >= ?` có nên đặt trước khi xác định partition key không?
5. Tại sao một `Criteria` trên `status` không tự tạo index?
6. Vì sao `LIMIT 20` rồi lọc `status == PAID` ở Java không trả đúng 20 đơn `PAID` mới nhất?
7. Paging state có thể dùng lại cho customer hoặc tháng khác không?
8. Chuyển từ `CassandraTemplate` sang `ReactiveCassandraTemplate` có sửa được một query sai primary key không?

**Đáp án gợi ý:** (1) `Criteria` biểu diễn điều kiện, `Query` gom điều kiện và giới hạn; (2) thiếu các thành phần partition key; (3) khi truy vấn được thiết kế trả tối đa một hàng; (4) nên giới hạn một partition trước; (5) DSL không thay đổi schema; (6) điều kiện đã áp sau khi lấy 20 hàng không phù hợp; (7) không; (8) không, chỉ đổi mô hình xử lý I/O.

## 14. Checklist khi dựng Query theo khóa

- [ ] Xác định query contract trước khi xây `Criteria`.
- [ ] Hiểu đúng **toàn bộ partition key** và thứ tự clustering của bảng.
- [ ] Validate đủ thành phần partition key ở mọi nhánh query động.
- [ ] Dùng tên cột CQL/mapping chính xác; không lấy tên cột tùy ý từ client.
- [ ] Chỉ thêm range filter trên clustering column theo khả năng CQL của schema.
- [ ] Không dùng `status`, `total_amount` như cột lọc/sort nếu chưa có đường truy cập phù hợp.
- [ ] Áp giới hạn số hàng, kích thước partition, request concurrency và paging có chủ đích.
- [ ] Phân biệt `select` (nhiều hàng) với `selectOne` (tối đa một hàng).
- [ ] Khi yêu cầu mới không phù hợp bảng, đánh giá access table/index thay vì tự thêm `ALLOW FILTERING`.
- [ ] Kiểm tra readback bằng CQL/test instance, so sánh đúng thứ tự và dữ liệu biên.
- [ ] Đo p95/p99, timeout, tombstones, hot partitions và tác động consistency.
- [ ] Không coi status của một bài hay ví dụ là chứng nhận đã chạy QA/benchmark production.

## Tài liệu tham khảo

- [Spring Data Cassandra — Cassandra Template](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Data Cassandra — Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html).
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Spring Data Cassandra — Cassandra Configuration](https://docs.spring.io/spring-data/cassandra/reference/cassandra/configuration.html).
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).

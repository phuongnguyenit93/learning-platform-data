# Kiểm tra CQL thực tế và xử lý truy vấn không hợp lệ theo mô hình khóa

**Derived query** (truy vấn dẫn xuất) trong **Spring Data Cassandra** cho phép khai báo phương thức repository như `findByKeyTenantIdAndKeyCustomerIdAndKeyMonthBucket(...)` để Spring Data phân tích tên phương thức, ánh xạ property Java sang tên cột Cassandra và tạo truy vấn CQL. Cách viết này ngắn gọn, nhưng **một tên phương thức parse được không đồng nghĩa CQL được Cassandra chấp nhận**, càng không bảo đảm truy vấn đi theo đường đọc có hiệu năng tốt.

Bài học thuộc chương **Truy vấn dẫn xuất** của module **SPRING_DATA_CASSANDRA**. Trọng tâm là **kiểm chứng CQL thực tế và xử lý truy vấn không hợp lệ theo mô hình khóa**, với các mối liên hệ thiết yếu đến entity mapping, `CassandraRepository`, `CassandraTemplate`, CQL có tham số, partition key, clustering columns, consistency, paging và khả năng chịu tải phân tán.

Kết thúc bài, bạn cần làm được bốn việc:

1. Từ yêu cầu nghiệp vụ và schema, dự đoán các `WHERE` được phép trước khi viết repository method.
2. Phân biệt lỗi **phân tích tên property**, lỗi **ánh xạ entity**, lỗi **CQL bị Cassandra từ chối** và truy vấn **chạy được nhưng có chi phí xấu**.
3. Quan sát statement do ứng dụng thực sự gửi, đối chiếu với CQL tường minh và viết integration test trên Cassandra thật.
4. Sửa truy vấn bằng cách **hoàn thiện khóa**, dùng `@Query`/`CassandraTemplate` đúng cách hoặc **thiết kế bảng truy cập khác**, thay vì dùng `ALLOW FILTERING` theo phản xạ.

> **Thông điệp cốt lõi:** Repository method là giao diện Java. **Primary key, schema và quy tắc CQL** mới quyết định Cassandra có thể xử lý truy vấn nào. Tên phương thức không thay thế việc thiết kế bảng theo truy vấn.

## 1. Truy vấn dẫn xuất được hình thành thế nào?

Một repository có thể viết:

~~~java
public interface CustomerRepository
        extends CassandraRepository<Customer, UUID> {

    Optional<Customer> findByCustomerId(UUID customerId);
}
~~~

Nếu entity `Customer` ánh xạ thuộc tính `customerId` vào cột CQL `customer_id`, Spring Data có thể phân tích `findByCustomerId` thành điều kiện `customer_id = ?`. Nhưng có hai câu hỏi khác nhau:

- **Spring Data có hiểu tên property và dựng được CQL không?**
- **Cassandra có cho phép `WHERE customer_id = ?` trên bảng đang dùng không?**

Ví dụ này hợp lý nếu `customer_id` là partition key đơn hoặc có một đường truy cập được cấu hình tương thích; nếu `customer_id` chỉ là cột thường trong bảng khác thì tên phương thức vẫn có thể được phân tích nhưng truy vấn **không có đường đọc tự nhiên**.

~~~mermaid
flowchart TD
    A[Yêu cầu API] --> B[Thiết kế bảng theo truy vấn]
    B --> C[Entity mapping và primary key]
    C --> D[Tên phương thức repository]
    D --> E{Spring Data phân tích được property?}
    E -->|Không| F[Lỗi cấu hình/query creation]
    E -->|Có| G[Tạo CQL + bind parameters]
    G --> H{CQL hợp lệ với schema/index?}
    H -->|Không| I[Invalid query / query rejected]
    H -->|Có| J[Thực thi trên Cassandra]
    J --> K{Đáp ứng SLA và consistency?}
    K -->|Không| L[Tối ưu access table, paging, tải và retry]
    K -->|Có| M[Giữ integration test và giám sát]
~~~

Một số lỗi được phát hiện khi Spring tạo repository bean, nhưng một số chỉ xuất hiện **khi câu lệnh thật được gửi tới cluster**. Tùy phiên bản Spring Data Cassandra, chiến lược khởi tạo repository và loại query, không được mặc định rằng ứng dụng khởi động thành công nghĩa là mọi derived method đều hợp lệ.

## 2. Thiết kế bảng ví dụ và hợp đồng truy vấn

Ứng dụng quản lý đơn hàng cần **20 đơn mới nhất của một khách trong một tháng**, với các chiều tenant, customer và time bucket. Bảng:

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

| Cột | Nhóm khóa | Vị trí | Ý nghĩa |
|---|---|---:|---|
| `tenant_id` | Partition | 0 | Tách đường truy cập theo tenant |
| `customer_id` | Partition | 1 | Tập đơn của một khách |
| `month_bucket` | Partition | 2 | Giới hạn độ lớn partition theo tháng |
| `created_at` | Clustering | 0 | Đơn mới hơn đứng trước |
| `order_id` | Clustering | 1 | Phân biệt các đơn cùng timestamp |
| `status` | Cột thường | — | Trạng thái đơn |
| `total_amount` | Cột thường | — | Số tiền `decimal` |

**Cấu trúc kép cần nhớ:**

~~~text
Partition key = (tenant_id, customer_id, month_bucket)
Clustering    = (created_at DESC, order_id ASC)
Full row key  = (tenant_id, customer_id, month_bucket, created_at, order_id)
~~~

Câu truy vấn phù hợp:

~~~sql
SELECT *
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Câu truy vấn có **đầy đủ ba thành phần partition key**, nên Cassandra có thể định vị một partition. Phần `ORDER BY` không bắt buộc vì bảng đã khai báo clustering order. Nếu API cần lịch sử trên nhiều tháng, phải truy vấn **nhiều partition**, rồi hợp nhất và phân trang theo hợp đồng riêng.

### 2.1. Một bảng khác cho yêu cầu tra đúng order ID

API `GET /tenants/{tenantId}/orders/{orderId}` có đường đọc khác. Thiết kế:

~~~sql
CREATE TABLE orders_by_id (
    tenant_id uuid,
    order_id uuid,
    customer_id uuid,
    status text,
    total_amount decimal,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, order_id))
);
~~~

`(tenant_id, order_id)` là **composite partition key**, đồng thời là toàn bộ primary key của bảng này. Truy vấn hợp lệ:

~~~sql
SELECT *
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

**Không cố ép một bảng phục vụ mọi `findBy...`**. Cassandra thường dùng nhiều read models/bảng truy cập tương ứng với các truy vấn quan trọng; ứng dụng phải chịu trách nhiệm đồng bộ dữ liệu, idempotency và xử lý ghi thất bại giữa các bảng.

## 3. Mapping entity và lớp khóa ghép để hỗ trợ derived query

Giả sử entity `OrderByCustomerMonth` có field `key` kiểu `OrderMonthKey`. Chúng ta cố tình dùng tên field `key` để thấy rõ cách parser truy cập property lồng nhau.

### 3.1. Lớp khóa với @PrimaryKeyClass

~~~java
package example.orders;

import java.io.Serializable;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.cql.PrimaryKeyType;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;

@PrimaryKeyClass
public class OrderMonthKey implements Serializable {

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
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.ASCENDING)
    private UUID orderId;

    public OrderMonthKey() {}

    public OrderMonthKey(UUID tenantId, UUID customerId,
            LocalDate monthBucket, Instant createdAt, UUID orderId) {
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.monthBucket = monthBucket;
        this.createdAt = createdAt;
        this.orderId = orderId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID value) { tenantId = value; }
    public UUID getCustomerId() { return customerId; }
    public void setCustomerId(UUID value) { customerId = value; }
    public LocalDate getMonthBucket() { return monthBucket; }
    public void setMonthBucket(LocalDate value) { monthBucket = value; }
    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant value) { createdAt = value; }
    public UUID getOrderId() { return orderId; }
    public void setOrderId(UUID value) { orderId = value; }

    @Override
    public boolean equals(Object value) {
        if (this == value) return true;
        if (!(value instanceof OrderMonthKey)) return false;
        OrderMonthKey other = (OrderMonthKey) value;
        return Objects.equals(tenantId, other.tenantId)
                && Objects.equals(customerId, other.customerId)
                && Objects.equals(monthBucket, other.monthBucket)
                && Objects.equals(createdAt, other.createdAt)
                && Objects.equals(orderId, other.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(tenantId, customerId, monthBucket,
                createdAt, orderId);
    }
}
~~~

`ordinal` được đánh theo **toàn bộ primary key**: ba trường partition nhận 0–2, hai trường clustering nhận 3–4. `PrimaryKeyType` thuộc package `org.springframework.data.cassandra.core.cql`; không nhầm với package `core.mapping`.

Khi tạo khóa, sử dụng `LocalDate.of(year, month, 1)` làm `monthBucket` và giữ `createdAt` ở độ chính xác phù hợp CQL `timestamp` (mili giây). Cùng một command được retry cần giữ nguyên ID và khóa; thay `Instant.now()` hay UUID trong mỗi lần thử có thể tạo hàng mới.

### 3.2. Entity chính

~~~java
package example.orders;

import java.math.BigDecimal;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_month")
public class OrderByCustomerMonth {

    @PrimaryKey
    private OrderMonthKey key;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    public OrderByCustomerMonth() {}
    public OrderByCustomerMonth(OrderMonthKey key, String status,
            BigDecimal totalAmount) {
        this.key = key;
        this.status = status;
        this.totalAmount = totalAmount;
    }

    public OrderMonthKey getKey() { return key; }
    public void setKey(OrderMonthKey value) { key = value; }
    public String getStatus() { return status; }
    public void setStatus(String value) { status = value; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public void setTotalAmount(BigDecimal value) { totalAmount = value; }
}
~~~

Trong Java, đường property của `tenantId` là `key.tenantId`, của `monthBucket` là `key.monthBucket`. Trong CQL, các tên cột tương ứng lại là `tenant_id`, `month_bucket`. Repository derivation đi qua **metadata Java và mapping**; server Cassandra chỉ nhìn thấy tên **cột CQL**.

## 4. Khai báo derived query hợp lý và dự đoán CQL

Repository:

~~~java
package example.orders;

import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrderByCustomerMonthRepository
        extends CassandraRepository<OrderByCustomerMonth, OrderMonthKey> {

    List<OrderByCustomerMonth>
    findByKeyTenantIdAndKeyCustomerIdAndKeyMonthBucket(
            UUID tenantId, UUID customerId, LocalDate monthBucket);
}
~~~

`findByKeyTenantIdAndKeyCustomerIdAndKeyMonthBucket` mô tả ba đường property lồng nhau, tương đương `key.tenantId`, `key.customerId`, `key.monthBucket`. Tùy phiên bản Spring Data Cassandra và cách đặt tên property, cần xác minh parser nhận đúng đường lồng nhau. Nếu tên property dễ nhập nhằng, phương thức có thể cần biểu diễn đường lồng nhau bằng dấu gạch dưới như `findByKey_TenantIdAndKey_CustomerIdAndKey_MonthBucket`; dấu `_` là ký hiệu **phân tách đường property của Spring Data**, không phải dấu gạch dưới trong tên cột Cassandra.

**CQL kỳ vọng về ngữ nghĩa** (không cam kết từng byte của statement framework sinh):

~~~sql
SELECT *
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?;
~~~

Framework có thể khác về danh sách cột, quoting, thứ tự điều kiện hoặc chi tiết prepared statement theo phiên bản. Quan trọng là **các điều kiện khóa cuối cùng**: đủ ba thành phần partition key, đúng tên cột và đúng kiểu tham số.

### 4.1. Truy vấn theo toàn bộ primary key

Với một hàng cụ thể, kế thừa repository CRUD đã đủ:

~~~java
OrderMonthKey key = new OrderMonthKey(
        tenantId, customerId, monthBucket, createdAt, orderId);

Optional<OrderByCustomerMonth> order = repository.findById(key);
~~~

`findById` nhận **toàn bộ lớp khóa ghép**, không nhận riêng `orderId`. Đây là cách an toàn khi service đã có đủ năm thành phần và muốn lấy đúng một hàng. Không cố viết `findByKeyOrderId` trên bảng này và kỳ vọng Cassandra tự tìm partition.

### 4.2. Khi cần giới hạn số hàng

`List<T>` trên một partition có hàng nghìn đơn không mặc nhiên giới hạn kết quả. Nếu API chỉ cần **20 đơn mới nhất**, một phương thức `@Query` tường minh có thể thể hiện contract rõ ràng:

~~~java
import org.springframework.data.cassandra.repository.Query;

@Query("SELECT * FROM orders_by_customer_month " +
       "WHERE tenant_id = ?0 AND customer_id = ?1 " +
       "AND month_bucket = ?2 LIMIT 20")
List<OrderByCustomerMonth> findLatestTwenty(
        UUID tenantId, UUID customerId, LocalDate monthBucket);
~~~

Đoạn này là **phương thức cần đặt bên trong repository** đã khai báo, không phải Java file độc lập. `@Query` không miễn áp dụng quy tắc khóa: câu lệnh vẫn phải có đủ partition key và giới hạn theo đường đọc hợp lệ.

Với API có nhu cầu nhiều trang, nên dùng khả năng `Slice`/`CassandraPageRequest` phù hợp phiên bản Spring Data và paging state của Cassandra, thay vì tải toàn bộ `List` rồi gọi `subList`.

## 5. Một số phương thức parse được nhưng không có đường đọc hợp lệ

Giả sử vẫn dùng bảng `orders_by_customer_month`. Những ví dụ sau **không nên đưa vào repository production** chỉ để thử:

~~~java
// Ví dụ cố ý sai hoặc thiếu đường đọc theo schema hiện tại:
List<OrderByCustomerMonth> findByStatus(String status);

List<OrderByCustomerMonth> findByKeyCustomerId(UUID customerId);

List<OrderByCustomerMonth> findByKeyOrderId(UUID orderId);

List<OrderByCustomerMonth>
findByKeyTenantIdAndKeyCustomerIdAndKeyMonthBucketAndStatus(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        String status);
~~~

Vì sao?

| Tên truy vấn/điều kiện dự kiến | Vấn đề | Kết quả có thể gặp |
|---|---|---|
| `WHERE status = ?` | `status` là cột thường, chưa có index | Cassandra từ chối hoặc cần index/đường đọc khác |
| `WHERE customer_id = ?` | Thiếu `tenant_id` và `month_bucket` | Không định vị đầy đủ partition |
| `WHERE order_id = ?` | `order_id` là clustering column thứ hai, không phải partition key | Không có đường đọc theo ID riêng |
| `WHERE tenant_id=? AND customer_id=? AND month_bucket=? AND status=?` | Partition hợp lệ nhưng thêm filter trên cột thường | Có thể bị từ chối nếu không có index hỗ trợ |
| `ORDER BY total_amount DESC` | Sắp xếp theo cột thường | Không phải `ORDER BY` được hỗ trợ theo clustering key |

Phương thức Java **có thể hợp lệ về tên**, nhưng CQL có thể bị Cassandra kiểm tra và từ chối ở runtime. Nếu Spring Data phiên bản đang dùng kiểm tra thêm các hạn chế trong giai đoạn tạo repository, lỗi có thể xảy ra **ngay khi khởi tạo bean**. Do đó đừng phụ thuộc vào đúng một thời điểm phát sinh lỗi.

### 5.1. Dễ nhầm giữa lỗi property và lỗi primary key

Ví dụ khai báo `findByCustomerCode` nhưng entity không có property `customerCode`: đây là **lỗi phân tích property path**. Repository có thể không khởi tạo được, thường được bọc trong lỗi tạo bean hoặc lỗi tạo truy vấn; cần sửa tên property hoặc mapping.

Ngược lại, `findByStatus` tham chiếu một property Java **có tồn tại**, nên parser có thể tạo CQL. Nhưng `status` không nằm trong partition/clustering key: đây là **lỗi đường truy vấn theo schema** nếu không có index hỗ trợ. Đổi `Status` thành `STATUS` trong tên method không khắc phục được.

## 6. Quy tắc WHERE cần tự kiểm tra trước khi chạy

Với bảng:

~~~sql
PRIMARY KEY (
    (tenant_id, customer_id, month_bucket),
    created_at, order_id
)
~~~

Hãy kiểm tra theo thứ tự:

1. **Đã biết đầy đủ partition key chưa?** Đường đọc một partition thông thường dùng điều kiện bằng (`=`) trên cả `tenant_id`, `customer_id`, `month_bucket`.
2. **Điều kiện clustering có đi theo thứ tự khóa không?** Muốn lọc `order_id` trong đường chuẩn thường phải tuân thủ điều kiện trên `created_at` đứng trước nó.
3. **Có lọc/sort trên cột thường không?** `status`, `total_amount` không tự có đường truy cập chỉ vì entity có `@Column`.
4. **Có index hoặc access table thực sự hỗ trợ không?** Nếu có, vẫn phải benchmark độ chọn lọc, kích thước kết quả và chi phí phân tán.
5. **Có giới hạn số hàng và paging đúng không?** `LIMIT` khác page size và paging state.
6. **Có quyền tenant và consistency phù hợp không?** Đúng CQL không đồng nghĩa tự kiểm soát quyền truy cập hay nhất quán nghiệp vụ.

### 6.1. Truy vấn hợp lệ khi có điều kiện clustering đúng thứ tự

Đọc đơn trong một khoảng thời gian của một partition:

~~~sql
SELECT *
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at >= ?
  AND created_at < ?
LIMIT 100;
~~~

Đây là **khoảng nửa mở** `[fromInclusive, toExclusive)` trên clustering column đầu. Thay vì đoán việc parser có hỗ trợ mọi biến thể `Between`, `GreaterThanEqual`, `LessThan` cho đường nested key trên phiên bản đang dùng, có thể ghi CQL tường minh bằng `@Query`:

~~~java
import java.time.Instant;
import org.springframework.data.cassandra.repository.Query;

@Query("SELECT * FROM orders_by_customer_month " +
       "WHERE tenant_id = ?0 AND customer_id = ?1 " +
       "AND month_bucket = ?2 AND created_at >= ?3 " +
       "AND created_at < ?4 LIMIT 100")
List<OrderByCustomerMonth> findInWindow(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        Instant fromInclusive, Instant toExclusive);
~~~

Code trên cũng là **method nằm trong repository**. Service cần validate `fromInclusive < toExclusive` và chuẩn hóa precision của `Instant`: CQL `timestamp` là mili giây, không bảo toàn mọi nano giây của Java.

### 6.2. Sort theo clustering khác sort toàn bảng

`WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC)` sắp thứ tự **trong từng partition**. Không có một thứ tự toàn cục cho tất cả tenant/customer/month. Một lời gọi dùng `Sort.by("totalAmount").descending()` không biến `total_amount` thành clustering column; trong Cassandra, `ORDER BY` chỉ được hỗ trợ trên các cột clustering và theo các quy tắc CQL áp dụng.

Nếu sản phẩm cần “10 đơn có tổng tiền lớn nhất của mọi khách”, cần thiết kế đường đọc khác, index/search hoặc hệ phân tích phù hợp. Không nên lấy mọi hàng rồi sort trong JVM khi dữ liệu có thể không giới hạn.

## 7. Làm thế nào để thấy CQL thực sự được gửi?

**CQL trong tài liệu minh họa không được coi là bằng chứng statement do Spring Data sinh.** Việc quan sát cần được thực hiện trong một **test/staging environment có quyền truy cập hợp lệ**, không ghi dữ liệu khách hàng thật vào log.

### 7.1. Quan sát từ tầng Java Driver

Java Driver 4 cung cấp cơ chế **request tracking / request logging** có thể ghi statement và kết quả thực thi theo cấu hình. Tùy phiên bản driver, có thể cấu hình `RequestLogger` trong file `application.conf`:

~~~hocon
datastax-java-driver {
  advanced.request-tracker.classes = [RequestLogger]
  advanced.request-tracker.logs {
    success.enabled = true
    error.enabled = true
    slow.enabled = true
  }
}
~~~

**Cảnh báo:** đây là cấu hình gợi ý để kiểm thử; khóa cấu hình và khả năng hiển thị tham số/values phải được đối chiếu với phiên bản Java Driver thực tế. Chỉ bật mức log phù hợp ở môi trường test hoặc trong khoảng chẩn đoán có kiểm soát. Tránh ghi giá trị bind nhạy cảm, credentials, thông tin tenant/customer hay payload nghiệp vụ vào log; tắt diagnostic verbosity sau khi kiểm tra.

Có thể tăng log level có chọn lọc cho Spring Data Cassandra trong test:

~~~yaml
# application-test.yml — chỉ phục vụ chẩn đoán.
logging:
  level:
    org.springframework.data.cassandra: DEBUG
~~~

Log Spring Data có thể hữu ích để hiểu repository, mapping hoặc lifecycle, nhưng **không bảo đảm mỗi phiên bản sẽ in nguyên CQL đầy đủ**. Dữ liệu từ request tracker ở tầng driver và test đối chiếu bằng CQL là nguồn xác minh đáng tin hơn cho statement thực thi.

### 7.2. Những gì cần ghi nhận từ request

Với method `findByKeyTenantIdAndKeyCustomerIdAndKeyMonthBucket`, ghi lại trong môi trường test:

| Cần quan sát | Ví dụ kỳ vọng | Vì sao quan trọng |
|---|---|---|
| Keyspace và bảng | `orders_by_customer_month` | Tránh chạy nhầm schema hoặc tenant |
| Danh sách cột | `SELECT ...` | Mapper có nhận đủ các cột cần thiết không? |
| Điều kiện `WHERE` | Ba cột partition key | Có đúng query-driven design không? |
| Bind markers và kiểu | UUID, UUID, date | Không đảo thứ tự/đổi kiểu |
| `ORDER BY`, `LIMIT` | Theo clustering và giới hạn đã chọn | Kết quả đúng thứ tự và kích thước |
| Consistency/timeout | Theo statement/profile thực tế | Không nhầm lỗi availability với lỗi query |
| Kết quả/lỗi driver | Query thành công hoặc server từ chối | Xác định tầng gây lỗi |

Giá trị bind có thể được **ẩn** khi log; vẫn có thể kiểm tra số marker, kiểu dữ liệu, thứ tự khai báo trong code và kết quả integration test. Không bật log chứa giá trị nhạy cảm chỉ để nhìn UUID cụ thể.

### 7.3. Dùng CQL độc lập để đối chiếu hành vi

Trong test, thực thi câu CQL tương đương qua `CqlSession` hoặc `cqlsh` bằng **cùng dữ liệu fixture**:

~~~sql
SELECT created_at, order_id, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?;
~~~

Khi dùng `cqlsh`, phải thay bind markers bằng literal hợp lệ; khi dùng Java Driver, nên chuẩn bị statement và bind tham số. Đừng coi việc `cqlsh` chạy trên máy quản trị là bằng chứng ứng dụng ở container/Kubernetes có cùng network, keyspace, credentials hay consistency.

**Truy vấn tường minh chỉ đối chiếu ngữ nghĩa.** Nếu derived method thực sự gửi CQL khác, cần quay lại quan sát logs/tracker và kiểm tra parser/metadata, không mặc định rằng hai truy vấn giống nhau vì kết quả một bộ fixture tình cờ bằng nhau.

## 8. Kiểm tra schema thực tế trước khi đổ lỗi cho repository

Trong Cassandra, một schema có thể đã được thay đổi bằng migration, hoặc entity Java mới chưa khớp bảng vật lý. Kiểm tra bằng CQL:

~~~sql
SELECT table_name
FROM system_schema.tables
WHERE keyspace_name = 'app_data';

SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'app_data'
  AND table_name = 'orders_by_customer_month';
~~~

Đổi `app_data` thành keyspace của môi trường đang chạy. Với bảng ví dụ, cần xác nhận:

| `column_name` | `kind` | `position` | Kiểu |
|---|---|---:|---|
| `tenant_id` | `partition_key` | 0 | `uuid` |
| `customer_id` | `partition_key` | 1 | `uuid` |
| `month_bucket` | `partition_key` | 2 | `date` |
| `created_at` | `clustering` | 0 | `timestamp` |
| `order_id` | `clustering` | 1 | `uuid` |
| `status` | `regular` | — | `text` |
| `total_amount` | `regular` | — | `decimal` |

Có thể dùng `DESCRIBE TABLE orders_by_customer_month;` trong **cqlsh** để xem DDL thực tế; `DESCRIBE` là lệnh tiện ích của cqlsh chứ không phải prepared CQL thông thường gửi qua Java Driver.

`@Table`, `@PrimaryKeyClass` và `@PrimaryKeyColumn` mô tả **mapping Java**. Sửa annotation không tự sửa partition key của bảng đã có dữ liệu. `CREATE_IF_NOT_EXISTS` chỉ tạo bảng chưa có, **không phải schema migration**.

## 9. Phân loại lỗi để xử lý đúng nguyên nhân

| Giai đoạn | Dấu hiệu có thể gặp | Nguyên nhân điển hình | Cách kiểm tra |
|---|---|---|---|
| **Phân tích tên method** | Lỗi tạo repository/query, `PropertyReferenceException` | Method nhắc property không có hoặc nested path sai | Đối chiếu entity `key.customerId` và tên method |
| **Mapping** | Không nhận field hoặc lỗi chuyển đổi | `@Column` sai, kiểu Java không khớp CQL | Đọc metadata, schema và converter |
| **CQL gửi tới server** | Driver `InvalidQueryException` hoặc lỗi Spring chuyển đổi | Thiếu partition key, lọc cột thường, sort sai | Ghi CQL thật, chạy câu tương đương trong test |
| **Schema** | Bảng/cột/keyspace không tồn tại | Migration chưa chạy hoặc keyspace sai | `system_schema`, `DESCRIBE` |
| **Authorization** | `Unauthorized` | Role không có quyền đọc/ghi | Kiểm tra grants, không mở quyền bừa bãi |
| **Kết nối** | Không bootstrap/không tìm thấy node | Contact points, DC, TLS, DNS | Kiểm tra network và driver config |
| **Hiệu năng** | Query có kết quả nhưng p99 cao/timeout | Hot partition, tombstone, paging, query fan-out | Đo query/cluster, review access pattern |
| **Nhất quán nghiệp vụ** | Dữ liệu giữa các bảng khác nhau | Projection chậm, ghi một phần, retry | Xem mutation flow, idempotency, consistency |

Khi Spring chuyển ngoại lệ driver thành `DataAccessException`, cần đọc **cause gốc** để biết lỗi đến từ Cassandra hay từ parser/mapping. Không dựa duy nhất vào message bọc ngoài kiểu `BeanCreationException` hoặc `DataAccessException`.

### 9.1. Ví dụ: tìm theo status nhưng thiếu index

Giả sử developer viết:

~~~java
List<OrderByCustomerMonth> findByStatus(String status);
~~~

Nếu `status` chỉ là cột thường, câu truy vấn mong muốn:

~~~sql
SELECT * FROM orders_by_customer_month WHERE status = 'PAID';
~~~

không có đường truy cập theo partition key. Tùy CQL/index/configuration, Cassandra có thể từ chối hoặc không đáp ứng hiệu năng mong muốn. **Không sửa bằng cách tăng timeout, bật `ALLOW FILTERING` đại trà hay đổi tên phương thức.** Nếu sản phẩm cần tìm các đơn `PAID` theo khách/tháng thường xuyên, thiết kế bảng đọc riêng:

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

Truy vấn trên bảng mới:

~~~sql
SELECT *
FROM orders_by_customer_status_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND status = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Ở đây `status` là **thành phần partition key**, không còn là cột thường. Đánh đổi: khi một đơn đổi trạng thái, ứng dụng phải xử lý việc xóa/ghi projection tương ứng và kiểm tra dữ liệu giữa các bảng. **Consistency level cao hơn trên từng mutation không biến nhiều bảng thành một transaction ACID thống nhất.**

### 9.2. Ví dụ: chỉ có orderId

Nếu một API chỉ nhận `orderId`, không thể dùng repository của `orders_by_customer_month` như một lookup toàn cục. Có thể dùng `orders_by_id` với `tenant_id` từ ngữ cảnh xác thực và `order_id` từ request:

~~~sql
SELECT *
FROM orders_by_id
WHERE tenant_id = ? AND order_id = ?;
~~~

Thiết kế này vừa xác định đường truy cập theo partition key vừa có cơ hội kiểm soát quyền tenant. Không tin tưởng một `tenant_id` bất kỳ do client cung cấp nếu chưa kiểm tra authorization.

### 9.3. Khi nào dùng index?

Secondary index hoặc storage-attached indexing (SAI, tùy phiên bản Cassandra/nhà cung cấp) có thể hỗ trợ một số bộ lọc trên cột không thuộc primary key. Nhưng tính phù hợp phụ thuộc **độ chọn lọc, kích thước dữ liệu, tải, consistency và phiên bản cluster**. Không suy ra “chỉ cần thêm index” sẽ thay thế tất cả read model.

Nếu truy vấn quan trọng phải có latency ổn định ở quy mô lớn, hãy thử nghiệm index với dữ liệu thật, so sánh với access table chuyên dụng và xem xét chi phí vận hành, ghi bổ sung và phục hồi dữ liệu.

## 10. Sửa truy vấn bằng @Query hoặc CassandraTemplate đúng cách

Sửa derived method thành `@Query` hữu ích khi muốn **CQL rõ ràng và dự đoán được**, nhưng chỉ khi câu CQL đó **đúng schema**.

### 10.1. Dùng @Query có điều kiện khóa đầy đủ

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.cassandra.repository.Query;

// Đặt phương thức vào OrderByCustomerMonthRepository:
@Query("SELECT * FROM orders_by_customer_month " +
       "WHERE tenant_id = ?0 AND customer_id = ?1 " +
       "AND month_bucket = ?2 LIMIT 20")
List<OrderByCustomerMonth> findRecent(
        UUID tenantId, UUID customerId, LocalDate monthBucket);
~~~

Câu CQL được người viết kiểm soát, dễ đối chiếu với `system_schema`. Tuy vậy, **không đặt `WHERE status = ?` trái đường khóa** rồi kỳ vọng `@Query` bỏ qua hạn chế của Cassandra.

### 10.2. Dùng CassandraTemplate và Query/Criteria

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

// Phương thức trong service có CassandraOperations operations:
public List<OrderByCustomerMonth> findRecentViaTemplate(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        CassandraOperations operations) {

    Query query = Query.query(Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("customer_id").is(customerId))
            .and(Criteria.where("month_bucket").is(monthBucket))
            .limit(20);

    return operations.select(query, OrderByCustomerMonth.class);
}
~~~

`CassandraTemplate` cung cấp DSL diễn đạt điều kiện và ánh xạ entity; nó **vẫn tạo CQL chịu cùng quy tắc Cassandra**. Với một API cho phép tùy chọn khoảng thời gian, service có thể thêm `Criteria.where("created_at").gte(...)` khi đã có toàn bộ partition key và kiểm tra khoảng. Nhưng tùy chọn lọc theo `status` không hợp lệ trên bảng hiện tại vẫn cần index hoặc read model khác.

### 10.3. Trường hợp cần CQL trực tiếp

`CqlTemplate`/`CqlOperations` hoặc Java Driver `CqlSession` phù hợp khi muốn kiểm soát chính xác statement, bind values hoặc driver execution profile. Ví dụ Java Driver:

~~~java
import java.time.LocalDate;
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

public ResultSet selectPartition(
        CqlSession session, UUID tenantId, UUID customerId,
        LocalDate monthBucket) {

    PreparedStatement ps = session.prepare(
            "SELECT order_id, created_at, status, total_amount " +
            "FROM orders_by_customer_month " +
            "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ?");

    return session.execute(
            ps.bind(tenantId, customerId, monthBucket));
}
~~~

Đây là **phương thức minh họa**; ở DAO thực tế nên giữ `PreparedStatement` để tái sử dụng, không prepare lại trên mọi request. Dùng bind markers `?` thay vì ghép trực tiếp dữ liệu người dùng vào CQL.

## 11. Viết integration test kiểm chứng derived query và CQL

Một bài test hợp lệ cần kiểm chứng **hai điều riêng biệt**: repository trả đúng dữ liệu và Cassandra thực sự thực thi được truy vấn theo khóa. Có thể dùng Cassandra test instance được tạo riêng cho CI hoặc Testcontainers, với keyspace và bảng đã provision trước khi chạy. Không dùng production làm môi trường thử các truy vấn cố ý sai.

### 11.1. Fixture kiểm tra partition và thứ tự

Tạo tối thiểu các bản ghi:

| Bản ghi | Tenant | Customer | Bucket | Created at | Vai trò |
|---|---|---|---|---|---|
| A | T1 | C1 | 2026-11-01 | 2026-11-25 10:00Z | Đơn mới trong partition mục tiêu |
| B | T1 | C1 | 2026-11-01 | 2026-11-25 09:00Z | Đơn cũ hơn trong cùng partition |
| C | T1 | C1 | 2026-10-01 | 2026-10-30 20:00Z | Partition tháng khác |
| D | T1 | C2 | 2026-11-01 | 2026-11-25 11:00Z | Khách khác |
| E | T2 | C1 | 2026-11-01 | 2026-11-25 12:00Z | Tenant khác |

Với `tenantId=T1`, `customerId=C1`, `monthBucket=2026-11-01`, phương thức derived đúng phải trả **A và B**, theo thứ tự clustering mới trước cũ; C/D/E không được lọt vào kết quả.

### 11.2. So sánh với CQL có bind parameters

Một khung integration test khi đã có bean `CqlSession`, repository, schema và fixture:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DerivedQueryIntegrationTest {

    @Autowired OrderByCustomerMonthRepository repository;
    @Autowired CqlSession session;

    @Test
    void derivedQueryMatchesExplicitCqlForOnePartition() {
        UUID tenantId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        UUID otherTenant = UUID.randomUUID();
        UUID otherCustomer = UUID.randomUUID();
        LocalDate month = LocalDate.of(2026, 11, 1);
        LocalDate otherMonth = LocalDate.of(2026, 10, 1);
        Instant recent = Instant.parse("2026-11-25T10:00:00Z");
        Instant older = Instant.parse("2026-11-25T09:00:00Z");
        UUID a = UUID.randomUUID();
        UUID b = UUID.randomUUID();

        PreparedStatement insert = session.prepare(
                "INSERT INTO orders_by_customer_month " +
                "(tenant_id, customer_id, month_bucket, created_at, " +
                "order_id, status, total_amount) VALUES (?, ?, ?, ?, ?, ?, ?)");

        // Hai hàng trong partition mục tiêu; ba hàng ngoài partition.
        session.execute(insert.bind(
                tenantId, customerId, month, recent, a,
                "PAID", new BigDecimal("100.00")));
        session.execute(insert.bind(
                tenantId, customerId, month, older, b,
                "NEW", new BigDecimal("50.00")));
        session.execute(insert.bind(
                tenantId, customerId, otherMonth, older, UUID.randomUUID(),
                "PAID", new BigDecimal("20.00")));
        session.execute(insert.bind(
                tenantId, otherCustomer, month, recent, UUID.randomUUID(),
                "PAID", new BigDecimal("30.00")));
        session.execute(insert.bind(
                otherTenant, customerId, month, recent, UUID.randomUUID(),
                "PAID", new BigDecimal("40.00")));

        List<OrderByCustomerMonth> derived =
                repository.findByKeyTenantIdAndKeyCustomerIdAndKeyMonthBucket(
                        tenantId, customerId, month);

        PreparedStatement ps = session.prepare(
                "SELECT order_id FROM orders_by_customer_month " +
                "WHERE tenant_id = ? AND customer_id = ? " +
                "AND month_bucket = ?");

        List<UUID> explicitIds = session.execute(
                ps.bind(tenantId, customerId, month))
                .all().stream()
                .map(row -> row.getUuid("order_id"))
                .toList();

        List<UUID> derivedIds = derived.stream()
                .map(row -> row.getKey().getOrderId())
                .toList();

        assertEquals(List.of(a, b), derivedIds);
        assertEquals(explicitIds, derivedIds);
    }
}
~~~

**Lưu ý:** Đoạn test sử dụng schema đã được tạo trong một Cassandra test instance, có `CqlSession` và repository được Spring inject. Nó tạo UUID riêng cho từng lượt test để tránh va chạm dữ liệu; khi áp dụng thực tế cần có fixture migration, chính sách dọn dữ liệu và consistency/phối hợp test phù hợp. Ví dụ dùng `Stream.toList()` của Java 16+.

Mục đích của phép so sánh là **đường derived** và **đường CQL tường minh** có cùng kết quả trên partition đã biết. Nó không thay thế việc quan sát CQL được driver gửi (phần 7), bởi hai câu khác nhau đôi khi vẫn cho cùng kết quả trên fixture quá nhỏ.

### 11.3. Test âm tính cho truy vấn không đúng khóa

Có thể test **CQL cố ý thiếu partition key** trực tiếp bằng driver, trên một keyspace test **không có index hỗ trợ**:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;

@Test
void rejectsQueryWithoutPartitionKeyOrIndex() {
    UUID customerId = UUID.randomUUID();
    assertThrows(InvalidQueryException.class, () ->
            session.execute(SimpleStatement.newInstance(
                    "SELECT * FROM orders_by_customer_month " +
                    "WHERE customer_id = ?",
                    customerId)));
}
~~~

Đoạn code là **method minh họa cho class test có `session` đã được inject**. Việc Cassandra từ chối hay hỗ trợ bằng index phụ thuộc vào schema/version thực tế; test phải được chạy trên một schema mà ta đã xác nhận **không có đường truy cập phụ**. Không nên khai báo derived method cố ý sai trong một repository được Spring quét khi bootstrap, vì nó có thể khiến cả application context không khởi tạo được trước khi test đến bước assertion.

Trong môi trường có security policy, `InvalidQueryException` cũng có thể được bọc lại ở tầng Spring hoặc thay bằng lỗi khác nếu cấu hình/index khác. Hãy khẳng định **bất biến về đường khóa**, không chỉ so khớp chuỗi thông báo lỗi theo phiên bản.

## 12. Paging: tên method đúng vẫn có thể trả quá nhiều hàng

Một derived finder hợp lệ:

~~~java
List<OrderByCustomerMonth>
findByKeyTenantIdAndKeyCustomerIdAndKeyMonthBucket(
        UUID tenantId, UUID customerId, LocalDate monthBucket);
~~~

vẫn có thể trả hàng chục nghìn hàng trong một partition; `List` sẽ khiến ứng dụng materialize toàn bộ kết quả. Với API có nhiều trang, dùng `Slice` và `Pageable` theo khả năng Spring Data Cassandra của phiên bản đang dùng:

~~~java
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;

// Khai báo trong repository:
Slice<OrderByCustomerMonth>
findByKeyTenantIdAndKeyCustomerIdAndKeyMonthBucket(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        Pageable pageable);
~~~

Lời gọi minh họa:

~~~java
import org.springframework.data.cassandra.core.query.CassandraPageRequest;

Slice<OrderByCustomerMonth> first =
        repository.findByKeyTenantIdAndKeyCustomerIdAndKeyMonthBucket(
                tenantId, customerId, monthBucket,
                CassandraPageRequest.first(50));

if (first.hasNext()) {
    Slice<OrderByCustomerMonth> second =
            repository.findByKeyTenantIdAndKeyCustomerIdAndKeyMonthBucket(
                    tenantId, customerId, monthBucket,
                    first.nextPageable());
}
~~~

Hai phương thức ví dụ cùng tên khác tham số được trình bày như **lựa chọn thiết kế**; khi sử dụng, nên chỉ giữ overload thực sự cần trong repository và kiểm thử query được sinh. Pagination của Cassandra dựa trên **paging state**, không hỗ trợ `OFFSET` tùy ý giống nhiều hệ SQL.

**Page size không phải `LIMIT`.** Một `CassandraPageRequest.first(50)` phục vụ đọc theo trang; muốn API chỉ bao giờ trả tối đa 20 đơn mới nhất, nên biểu đạt giới hạn tổng/response trong contract và triển khai tương ứng.

Paging state gắn với **cùng CQL, bind values và cấu hình tương thích**. Không lấy state của `tenant T1/customer C1/month 11` rồi tái sử dụng cho `month 10`. Nếu cần ghép nhiều partition, ứng dụng phải điều phối cursor của từng truy vấn và trộn kết quả theo chính sách thứ tự đã xác định.

## 13. Consistency và retry không giải quyết truy vấn sai khóa

`LOCAL_ONE`, `LOCAL_QUORUM` và các consistency levels mô tả yêu cầu phản hồi replica của một thao tác trên keyspace có replication cụ thể. Với RF=3 ở local datacenter, `LOCAL_QUORUM` thường cần hai replica phản hồi. Nhưng:

- Chuyển từ `LOCAL_ONE` sang `LOCAL_QUORUM` **không** làm `WHERE status=?` trở thành đường đọc hợp lệ.
- Tăng timeout/retry **không** giảm số partition phải đọc nếu model sai.
- Với dữ liệu được denormalize qua `orders_by_id` và `orders_by_customer_month`, consistency của từng câu lệnh **không tạo** transaction nguyên tử giữa hai bảng.
- Một câu derived query đúng khóa vẫn có thể chậm khi partition nóng, tombstone nhiều hoặc số hàng quá lớn.

Để vận hành đúng trong hệ phân tán, nên đo:

| Chỉ số | Hỏi điều gì? |
|---|---|
| p50/p95/p99 latency | Truy vấn có đáp ứng SLO dưới tải thực không? |
| Timeout và retry | Có lỗi hạ tầng, truy vấn quá lớn hay bão retry không? |
| Partition size/hot key | Một customer/month có nhiều đơn bất thường không? |
| Tombstones | Có nhiều xóa/TTL hoặc chuyển trạng thái trong projection không? |
| Số trang và byte đọc | Một request có tiêu thụ quá nhiều dữ liệu không? |
| CQL và số partition liên quan | Mọi query có đúng đường khóa không? |
| Projection lag | Hai access tables có nhất quán theo yêu cầu nghiệp vụ không? |

Không có một ngưỡng page size hoặc partition size tuyệt đối cho mọi ứng dụng. Benchmark cần dùng dữ liệu có phân phối đại diện, concurrency và replication tương đương môi trường vận hành.

## 14. Quy trình xử lý khi một derived query bị từ chối

Ví dụ một developer thêm `findByStatus("PAID")` và nhận lỗi. Thực hiện theo trình tự:

1. **Ghi lại yêu cầu nghiệp vụ:** tìm theo trạng thái trên toàn hệ thống hay chỉ theo tenant/customer/month? Kết quả có sắp theo thời gian không, cần mấy hàng/trang?
2. **Kiểm tra entity và property path:** `status` có tồn tại không? Nếu method dùng nested key, tên `key.tenantId` đã được parser hiểu đúng chưa?
3. **Đọc schema vật lý:** xác nhận partition/clustering columns và index; đừng suy từ annotation đơn độc.
4. **Quan sát CQL thực tế trong test:** bảng nào, cột `WHERE` nào, thứ tự bind và `ORDER BY` gì?
5. **Đối chiếu quy tắc Cassandra:** có đầy đủ partition key, clustering đúng thứ tự, cột thường được index phù hợp không?
6. **Chọn hướng sửa:** hoàn thiện tham số khóa, viết `@Query`/template rõ ràng, hoặc thiết kế access table mới. Không chuyển lỗi schema thành `ALLOW FILTERING` không kiểm soát.
7. **Test kết quả và performance:** test nhiều tenant, nhiều partition, time bucket, paging và dữ liệu biên; đo latency/tải.
8. **Giám sát sau triển khai:** log truy vấn chọn lọc, bảo vệ PII, theo dõi retry/tombstone/projection và xác thực quyền.

~~~text
findByStatus("PAID")
    |
    +-- Property không tồn tại?
    |      → Sửa tên method / entity mapping.
    |
    +-- Property tồn tại, nhưng CQL sai đường khóa?
    |      → Bổ sung đầy đủ partition key
    |         hoặc thiết kế bảng orders_by_customer_status_month.
    |
    +-- Có index phù hợp và CQL chạy được?
    |      → Benchmark, kiểm tra độ chọn lọc và tính nhất quán.
    |
    +-- Query đúng nhưng timeout?
           → Kiểm tra partition size, hot key, tombstone,
              paging, concurrency và availability.
~~~

## 15. Bài tập thực hành

Hệ thống quản lý kiện hàng có schema:

~~~sql
CREATE TABLE scans_by_package_day (
    package_id uuid,
    scan_day date,
    scanned_at timestamp,
    scan_id uuid,
    hub_id uuid,
    result text,
    PRIMARY KEY ((package_id, scan_day), scanned_at, scan_id)
) WITH CLUSTERING ORDER BY (scanned_at DESC, scan_id ASC);
~~~

Yêu cầu API:

~~~text
GET /packages/{packageId}/scans?day=2026-11-25&limit=50
GET /hubs/{hubId}/scans?day=2026-11-25&limit=50
GET /scans/{scanId}
~~~

**Bài tập A — phân loại ba truy vấn**

| API | Có thể phục vụ trực tiếp từ `scans_by_package_day`? | Hướng giải |
|---|---|---|
| Lịch sử một package trong ngày | **Có** | `WHERE package_id=? AND scan_day=?` |
| Lịch sử của một hub trong ngày | **Không theo primary-key path** | Bảng `scans_by_hub_day` hoặc index được benchmark |
| Tra chỉ bằng scanId | **Không** | Bảng `scans_by_id` hoặc locator theo ID |

**Bài tập B — viết repository**

Tạo `@PrimaryKeyClass` gồm `package_id`, `scan_day` là partition, `scanned_at`, `scan_id` là clustering. Entity `PackageScan` có field `key`; khai báo derived finder theo đường `key.packageId` và `key.scanDay`. Dự đoán CQL, sau đó **kiểm tra CQL thực tế** trong integration test.

Một truy vấn tường minh để đối chiếu:

~~~sql
SELECT scanned_at, scan_id, hub_id, result
FROM scans_by_package_day
WHERE package_id = ? AND scan_day = ?
LIMIT 50;
~~~

**Bài tập C — cố ý tạo lỗi an toàn**

Trên **test cluster không có index theo hub_id**, chạy:

~~~sql
SELECT * FROM scans_by_package_day
WHERE hub_id = ?;
~~~

Ghi lại lỗi server, xác định vì sao `hub_id` không thuộc partition key. Không thêm `ALLOW FILTERING` như lời giải; hãy đề xuất schema của `scans_by_hub_day` với `(hub_id, scan_day)` làm partition key, đồng thời cân nhắc hub có thể trở thành hot partition. Nếu cần tra theo `scan_id`, thiết kế bảng `scans_by_id` và thảo luận cách giữ dữ liệu đồng bộ.

### Câu hỏi tự kiểm tra

1. Vì sao một derived repository method có tên đúng vẫn có thể bị Cassandra từ chối?
2. Sai property Java và thiếu partition key khác nhau ở bước phát hiện lỗi nào?
3. Với `PRIMARY KEY ((tenant_id, customer_id, month_bucket), created_at, order_id)`, `WHERE customer_id=?` có đủ đường truy vấn không?
4. `@Query` có thể biến một câu lọc trên cột thường thành truy vấn hiệu quả mà không đổi schema không?
5. Dùng `CassandraTemplate` có tránh được quy tắc `WHERE` của CQL không?
6. Vì sao cần so sánh derived query với CQL có bind parameters trên **nhiều partition** thay vì chỉ một hàng?
7. Có nên bật request logging chứa tham số nhạy cảm trên production để debug không?
8. `CassandraPageRequest.first(50)` có ý nghĩa như `LIMIT 50` tổng số hàng không?
9. Tăng consistency hoặc timeout có sửa được lỗi CQL thiếu partition key không?
10. Khi chuyển từ truy vấn theo ID sang truy vấn theo status, vì sao có thể cần bảng truy cập khác?

**Đáp án gợi ý:** (1) parser Java không kiểm chứng đầy đủ đường truy cập; (2) property path sai có thể lỗi khi tạo query, CQL sai khóa có thể bị từ chối khi thực thi; (3) không; (4) không; (5) không; (6) phát hiện dữ liệu bị lẫn tenant/month và thứ tự sai; (7) không; (8) không; (9) không; (10) status là chiều truy vấn khác, cần index hoặc partitioning phù hợp.

## 16. Checklist kiểm chứng trước khi release

- [ ] Đã xác định query contract và access pattern trước khi viết `findBy...`.
- [ ] Entity có metadata `@Table`, `@Column`, primary key đúng với schema vật lý.
- [ ] Nested property path trong tên method được kiểm chứng trên phiên bản Spring Data đang dùng.
- [ ] Đã đối chiếu toàn bộ partition key, thứ tự clustering và các điều kiện lọc/sort.
- [ ] Đã quan sát **CQL thật** từ Java Driver trong môi trường test/staging.
- [ ] Dữ liệu bind có kiểu và thứ tự khớp câu CQL; không ghép trực tiếp dữ liệu người dùng.
- [ ] Đã phân biệt lỗi parser/property, mapping, CQL server, schema, quyền và timeout.
- [ ] Không thêm `ALLOW FILTERING` tùy tiện để bỏ qua schema sai đường đọc.
- [ ] Khi dùng `@Query` hoặc `CassandraTemplate`, query vẫn tuân thủ primary key.
- [ ] Có integration test với nhiều tenant, customer, month, clustering order và trường hợp rỗng.
- [ ] Dùng `Slice`/paging state cho truy vấn nhiều hàng; không tải toàn bộ rồi chia trang.
- [ ] Đã kiểm tra consistency, retry, hot partition, tombstone và projection lag.
- [ ] Request logs không để lộ secrets/PII; chỉ bật chẩn đoán có kiểm soát.
- [ ] Schema migration/backfill được quản lý riêng; đổi method hoặc annotation không tự di chuyển dữ liệu.
- [ ] Có benchmark p95/p99 và kiểm tra hiệu năng với dữ liệu đại diện.

## Tài liệu tham khảo

- [Spring Data Cassandra — Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html).
- [Spring Data Cassandra — Defining Query Methods](https://docs.spring.io/spring-data/cassandra/reference/repositories/query-methods-details.html).
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra Java Driver — Request Tracking](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/request_tracker/).

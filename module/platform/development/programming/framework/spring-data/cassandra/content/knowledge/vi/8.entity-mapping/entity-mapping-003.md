# @PrimaryKeyClass và lớp khóa ghép trong Spring Data Cassandra

Trong **Spring Data Cassandra**, nhiều bảng cần hơn một cột để xác định vị trí và thứ tự dữ liệu. Khi đó, thay vì đánh dấu một trường `UUID` bằng `@PrimaryKey`, ta có thể tạo **lớp khóa ghép** dùng `@PrimaryKeyClass`, mô tả từng thành phần bằng `@PrimaryKeyColumn` rồi nhúng lớp khóa vào entity. Cách ánh xạ này cần phản ánh chính xác `PRIMARY KEY` đã thiết kế trong CQL.

Bài học thuộc chương **Ánh xạ entity** của module **SPRING_DATA_CASSANDRA**. Chủ đề tập trung vào cấu trúc khóa ghép, entity mapping, repository, `CassandraTemplate` và các truy vấn CQL. Đồng thời, chúng ta sẽ xem cách partition key, clustering key, tính nhất quán, paging và phân bố tải ảnh hưởng đến thiết kế dữ liệu phân tán.

Sau bài học, bạn có thể:

1. Phân biệt **partition key**, **clustering columns** và **toàn bộ primary key**.
2. Dùng `@PrimaryKeyClass` và `@PrimaryKeyColumn` ánh xạ một khóa CQL gồm nhiều thành phần.
3. Viết `equals()`/`hashCode()` đúng cho đối tượng khóa, tạo entity và repository sử dụng kiểu ID phù hợp.
4. Viết truy vấn theo partition key và giải thích vì sao một số truy vấn khác cần bảng truy cập riêng.
5. Nhận diện lỗi annotation, thay đổi khóa, paging và hot partition trước khi đưa ứng dụng vào production.

## 1. Cassandra hiểu khóa ghép như thế nào?

Xét yêu cầu sản phẩm: “Hiển thị 20 đơn hàng mới nhất của **một khách hàng** trong **một tháng**, trong phạm vi **một tenant**”. Bảng có thể được thiết kế như sau:

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

Trong CQL, phần bên trong cặp ngoặc kép `((tenant_id, customer_id, month_bucket))` là **composite partition key**. Hai cột `created_at` và `order_id` là **clustering columns**.

| Thành phần | Vai trò | Được dùng để làm gì? |
|---|---|---|
| `tenant_id` | Thành phần partition key, vị trí 0 | Phân biệt tenant |
| `customer_id` | Thành phần partition key, vị trí 1 | Chỉ định khách hàng trong tenant |
| `month_bucket` | Thành phần partition key, vị trí 2 | Giới hạn dữ liệu mỗi partition theo tháng |
| `created_at` | Clustering, vị trí 0 | Sắp xếp đơn theo thời gian giảm dần |
| `order_id` | Clustering, vị trí 1 | Phân biệt hai đơn có cùng thời điểm và tạo thứ tự xác định |
| `status`, `total_amount` | Cột thông thường | Lưu dữ liệu nghiệp vụ, không tham gia định tuyến theo primary key |

Với thiết kế này, Cassandra dùng **toàn bộ partition key** để tính token và tìm replica. Bên trong partition, các hàng được sắp xếp theo clustering columns. Toàn bộ năm cột khóa tạo nên **định danh một hàng** trong bảng.

~~~text
Partition (tenant=A, customer=C1, month=2026-11)
    created_at DESC              order_id       status
    2026-11-25T09:12:00Z         O-103          PAID
    2026-11-25T08:20:00Z         O-102          NEW
    2026-11-24T17:00:00Z         O-101          PAID

Partition (tenant=A, customer=C1, month=2026-10)
    ... các hàng trong tháng khác ...

Partition (tenant=A, customer=C2, month=2026-11)
    ... khách hàng khác ...
~~~

Sơ đồ trên dùng ID ngắn để dễ đọc; kiểu CQL thực tế của `order_id` là `uuid`.

**Phân biệt quan trọng:** “khóa ghép” có thể có nghĩa là nhiều cột **partition key**, nhiều cột **clustering**, hoặc kết hợp cả hai. Chỉ có tên `@PrimaryKeyClass` không cho biết một trường thuộc nhóm nào; cần khai báo rõ `PrimaryKeyType` cho từng trường.

## 2. Phân biệt các dạng PRIMARY KEY qua CQL

| Định nghĩa | Partition key | Clustering columns | Đường truy vấn phù hợp |
|---|---|---|---|
| `PRIMARY KEY (user_id)` | `user_id` | Không có | Tra một user theo ID |
| `PRIMARY KEY (customer_id, created_at)` | `customer_id` | `created_at` | Lịch sử theo customer |
| `PRIMARY KEY ((tenant_id, sku))` | Cặp `tenant_id, sku` | Không có | Tra một sản phẩm bằng hai mã |
| `PRIMARY KEY ((device_id, day_bucket), event_time, event_id)` | Cặp `device_id, day_bucket` | `event_time`, `event_id` | Sự kiện thiết bị theo ngày/thời gian |
| `PRIMARY KEY ((tenant_id, customer_id, month_bucket), created_at, order_id)` | Ba thành phần đầu | Hai thành phần sau | Đơn mới nhất của một khách theo tháng |

Hai ví dụ dễ nhầm:

~~~sql
-- customer_id là partition key; created_at là clustering.
PRIMARY KEY (customer_id, created_at)

-- Cả customer_id và created_at đều là thành phần partition key.
PRIMARY KEY ((customer_id, created_at))
~~~

Hai kiểu này có đường đọc **rất khác nhau**. Với kiểu đầu, có thể đọc lịch sử một khách theo thứ tự thời gian trong một partition. Với kiểu thứ hai, `created_at` tham gia định vị partition, nên truy vấn chỉ cung cấp `customer_id` thiếu thông tin partition key.

Trong bài này, chúng ta dùng ví dụ `orders_by_customer_month` vì nó buộc phải ánh xạ **cả partition key ghép và clustering columns**.

## 3. @PrimaryKeyClass định nghĩa đối tượng khóa như thế nào?

`@PrimaryKeyClass` đặt trên một **kiểu Java** biểu diễn các trường tham gia primary key. Các field của lớp được đánh dấu `@PrimaryKeyColumn`, trong đó:

- `name`: tên cột CQL tương ứng.
- `type = PrimaryKeyType.PARTITIONED`: field là một thành phần của partition key.
- `type = PrimaryKeyType.CLUSTERED`: field là clustering column.
- `ordinal`: vị trí của field **so với các cột primary key khác**; trong ví dụ này đánh số liên tiếp từ partition key đầu tiên đến clustering column cuối cùng.
- `ordering = Ordering.DESCENDING` hoặc `Ordering.ASCENDING`: thứ tự clustering khi mô tả schema.

Đối tượng khóa cho bảng đơn hàng:

~~~java
package example.orders.cassandra;

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
public class OrderByCustomerMonthKey implements Serializable {

    private static final long serialVersionUID = 1L;

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

    public OrderByCustomerMonthKey() {
    }

    public OrderByCustomerMonthKey(
            UUID tenantId, UUID customerId, LocalDate monthBucket,
            Instant createdAt, UUID orderId) {
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.monthBucket = monthBucket;
        this.createdAt = createdAt;
        this.orderId = orderId;
    }

    public UUID getTenantId() { return tenantId; }
    public void setTenantId(UUID tenantId) { this.tenantId = tenantId; }

    public UUID getCustomerId() { return customerId; }
    public void setCustomerId(UUID customerId) { this.customerId = customerId; }

    public LocalDate getMonthBucket() { return monthBucket; }
    public void setMonthBucket(LocalDate monthBucket) {
        this.monthBucket = monthBucket;
    }

    public Instant getCreatedAt() { return createdAt; }
    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public UUID getOrderId() { return orderId; }
    public void setOrderId(UUID orderId) { this.orderId = orderId; }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof OrderByCustomerMonthKey)) return false;
        OrderByCustomerMonthKey that = (OrderByCustomerMonthKey) other;
        return Objects.equals(tenantId, that.tenantId)
                && Objects.equals(customerId, that.customerId)
                && Objects.equals(monthBucket, that.monthBucket)
                && Objects.equals(createdAt, that.createdAt)
                && Objects.equals(orderId, that.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(
                tenantId, customerId, monthBucket, createdAt, orderId);
    }
}
~~~

Ở đây `ordinal` chạy **liên tục từ 0 đến 4 trên toàn bộ primary key**: ba thành phần `PARTITIONED` nhận 0, 1, 2; hai cột `CLUSTERED` nhận 3, 4. `PrimaryKeyType` phân biệt hai nhóm, còn `ordinal` mô tả vị trí tương đối giữa **mọi** cột khóa. Spring Data dùng metadata này để tạo thứ tự cột trong `PRIMARY KEY`; riêng clustering columns còn có `CLUSTERING ORDER BY`.

### 3.1. Vì sao cần constructor và equals/hashCode?

Lớp khóa là một **value object**: hai đối tượng với cùng năm thành phần phải được xem là cùng một khóa theo ngữ nghĩa Java. Override `equals()` và `hashCode()` giúp so sánh, lưu trong `Set` hoặc dùng làm khóa của `Map` đúng như kỳ vọng; một số cơ chế framework/cache cũng dựa vào ngữ nghĩa này.

Constructor không tham số và accessor thuận tiện cho quá trình materialization/binding của Spring Data, đặc biệt khi dùng mapping theo field/property thông thường. Có thể dùng constructor mapping hoặc những cấu trúc immutable được phiên bản Spring Data đang chạy hỗ trợ, nhưng cần xác minh thực tế. Đoạn mã trên ưu tiên cấu trúc dễ hiểu và tương thích.

Ngữ nghĩa so sánh khóa trong Java cũng phải tương thích với kiểu CQL. Chẳng hạn, Cassandra `timestamp` có độ chính xác **mili giây**; nếu nguồn `Instant` có nano giây, cần chuẩn hóa về mili giây trước khi tạo khóa để tránh các đối tượng Java được xem là khác nhau nhưng ghi vào cùng giá trị thời gian CQL.

**Không sửa khóa sau khi đưa vào `HashMap` hoặc `HashSet`**: thay giá trị một field ảnh hưởng đến `hashCode()` sẽ gây hành vi khó dự đoán. Với ứng dụng thực tế, lớp khóa immutable có thể là lựa chọn tốt nếu được ánh xạ đúng; một khi ghi hàng, thay primary key về mặt Cassandra là ghi hàng mới và xử lý hàng cũ.

### 3.2. Giá trị của khóa phải có ý nghĩa ổn định

Đối tượng `OrderByCustomerMonthKey` chứa `createdAt` và `orderId`. Nếu ứng dụng tạo `UUID.randomUUID()` mỗi lần retry hoặc đặt `createdAt = Instant.now()` trong từng lượt thử, **toàn bộ primary key thay đổi** và Cassandra có thể tạo thêm một hàng khác cho cùng một hành động nghiệp vụ.

Hãy tạo ID và thời điểm nghiệp vụ **một lần**, lưu cùng request/event hoặc tại nguồn dữ liệu chuẩn, rồi tái sử dụng trên các lần ghi lại. Mỗi field của primary key phải có giá trị hợp lệ, không `null` khi ghi.

## 4. Đặt lớp khóa vào entity bằng @PrimaryKey

`@PrimaryKeyClass` chỉ mô tả kiểu khóa. Để Spring Data biết một entity dùng kiểu khóa đó, đặt `@PrimaryKey` trên **một field của entity**:

~~~java
package example.orders.cassandra;

import java.math.BigDecimal;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_month")
public class OrderByCustomerMonth {

    @PrimaryKey
    private OrderByCustomerMonthKey id;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    public OrderByCustomerMonth() {
    }

    public OrderByCustomerMonth(
            OrderByCustomerMonthKey id,
            String status, BigDecimal totalAmount) {
        this.id = id;
        this.status = status;
        this.totalAmount = totalAmount;
    }

    public OrderByCustomerMonthKey getId() { return id; }
    public void setId(OrderByCustomerMonthKey id) { this.id = id; }

    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }

    public BigDecimal getTotalAmount() { return totalAmount; }
    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }
}
~~~

Với mapping này:

- `@Table("orders_by_customer_month")` gắn entity với bảng CQL.
- `@PrimaryKey` cho biết `id` là **đối tượng chứa toàn bộ primary key**; không cần thêm `@Column` trên `id`.
- `@PrimaryKeyColumn` ở lớp khóa quyết định các cột vật lý `tenant_id`, `customer_id`, `month_bucket`, `created_at`, `order_id`.
- `status`, `total_amount` là cột thông thường, có thể thay đổi mà không chuyển hàng sang khóa khác.

Các kiểu Java thường dùng ở đây ánh xạ tới Cassandra:

| Java | CQL | Vai trò |
|---|---|---|
| `UUID` | `uuid` | Định danh tenant, customer và đơn |
| `LocalDate` | `date` | Ngày đầu tháng, đại diện month bucket |
| `Instant` | `timestamp` | Thời gian tạo đơn |
| `String` | `text` | Trạng thái |
| `BigDecimal` | `decimal` | Giá trị tiền theo độ chính xác thập phân |

`monthBucket` dùng `LocalDate.of(year, month, 1)` để mọi yêu cầu trong cùng tháng tạo đúng **một giá trị bucket**. Thống nhất cách biểu diễn bucket ở cả writer, reader và truy vấn backfill. Dữ liệu thời gian của `Instant` cần được hiểu theo UTC khi lưu và hiển thị theo múi giờ nghiệp vụ phù hợp.

## 5. Ghi và đọc bằng CassandraRepository

Với entity có khóa ghép, tham số ID của repository phải là **kiểu khóa ghép**, không phải `UUID` đơn lẻ:

~~~java
package example.orders.cassandra;

import org.springframework.data.cassandra.repository.CassandraRepository;

public interface OrdersByCustomerMonthRepository
        extends CassandraRepository<
                OrderByCustomerMonth, OrderByCustomerMonthKey> {
}
~~~

Tạo một hàng đơn hàng:

~~~java
UUID tenantId = UUID.fromString(
        "82d9ca7e-6141-43e2-a3ad-0410427a5177");
UUID customerId = UUID.fromString(
        "b8e2ecf5-6844-4da7-bbf3-c5bb47ff8183");
UUID orderId = UUID.randomUUID();
Instant createdAt = Instant.parse("2026-11-25T09:00:00Z");

OrderByCustomerMonthKey key = new OrderByCustomerMonthKey(
        tenantId,
        customerId,
        LocalDate.of(2026, 11, 1),
        createdAt,
        orderId
);

OrderByCustomerMonth order = new OrderByCustomerMonth(
        key, "PAID", new BigDecimal("125000.00"));

repository.save(order);
~~~

Đây là ví dụ trong service có `OrdersByCustomerMonthRepository repository`; cần import `UUID`, `Instant`, `LocalDate`, `BigDecimal`. `save` dùng semantics upsert của Cassandra đối với cùng primary key. Đây không phải cơ chế mặc định đảm bảo duy nhất cho một mã đơn **nghiệp vụ** trên mọi bảng: nếu uniqueness là yêu cầu, phải thiết kế kiểm soát riêng, có thể dùng conditional write/LWT tại khóa phù hợp.

Đọc một hàng theo đầy đủ primary key:

~~~java
Optional<OrderByCustomerMonth> saved = repository.findById(key);
~~~

`findById(key)` có đủ cả partition key và clustering columns. Nếu **chỉ biết `orderId`**, bạn **chưa có đủ khóa** để dùng `findById` của bảng này. Thường cần một bảng tra cứu như `orders_by_id` với khóa phù hợp; không nên biến repository method thành truy vấn quét toàn bảng.

### 5.1. Tra danh sách theo partition key, không cần toàn bộ khóa hàng

Để đáp ứng API “20 đơn mới nhất của khách trong tháng”, câu CQL hợp lý là:

~~~sql
SELECT tenant_id, customer_id, month_bucket,
       created_at, order_id, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Đây là truy vấn **trên một partition**: chỉ cần biết đủ ba thành phần partition key. Không cần biết `created_at` và `order_id` vì ta muốn danh sách nhiều hàng, theo thứ tự clustering được thiết kế sẵn.

Repository hỗ trợ khai báo method riêng:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.cassandra.repository.Query;

public interface OrdersByCustomerMonthRepository
        extends CassandraRepository<
                OrderByCustomerMonth, OrderByCustomerMonthKey> {

    @Query("SELECT * FROM orders_by_customer_month "
         + "WHERE tenant_id = ?0 AND customer_id = ?1 "
         + "AND month_bucket = ?2 LIMIT 20")
    List<OrderByCustomerMonth> findRecent(
            UUID tenantId, UUID customerId, LocalDate monthBucket);
}
~~~

`LIMIT 20` là giới hạn minh họa. Trong hệ thống thực, API thường cần điều khiển page size trong phạm vi được phép và tiếp tục phân trang thay vì luôn tải một tập lớn.

## 6. Cùng truy vấn qua CassandraTemplate

`CassandraTemplate`/`CassandraOperations` giúp tạo truy vấn bằng các đối tượng `Query` và `Criteria`. Điều kiện vẫn phải tôn trọng cấu trúc partition key của Cassandra:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;

import org.springframework.data.cassandra.core.CassandraOperations;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

// Phương thức trong service; CassandraOperations được inject.
public List<OrderByCustomerMonth> findRecent(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        CassandraOperations operations) {
    Query query = Query.query(Criteria.where("tenant_id").is(tenantId))
            .and(Criteria.where("customer_id").is(customerId))
            .and(Criteria.where("month_bucket").is(monthBucket))
            .limit(20);

    return operations.select(query, OrderByCustomerMonth.class);
}
~~~

Trong ứng dụng thực, `tenantId` nên được lấy từ ngữ cảnh xác thực, còn `customerId` phải được kiểm tra quyền truy cập trước khi truy vấn. Đoạn mã trên minh họa phương thức đặt **bên trong service**, không phải một class độc lập.

Để đọc một hàng, có thể dùng:

~~~java
OrderByCustomerMonth row =
        operations.selectOneById(key, OrderByCustomerMonth.class);
// Không có hàng: có thể trả null.
~~~

Repository, template và CQL trực tiếp đều gửi truy vấn tới Cassandra thông qua driver. Không có abstraction nào tự sửa một điều kiện `WHERE` thiếu partition key. Khi cần thao tác sâu với statement, consistency hoặc paging, có thể dùng các API phù hợp ở tầng template/driver mà không đánh đổi thiết kế khóa.

## 7. Clustering columns, sort và truy vấn khoảng

Vì bảng dùng:

~~~sql
PRIMARY KEY (
    (tenant_id, customer_id, month_bucket),
    created_at,
    order_id
)
WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC)
~~~

nên có thể đọc các đơn trong tháng theo thời gian tạo. Một truy vấn khoảng thời gian dựa trên clustering column đầu tiên:

~~~sql
SELECT *
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at >= '2026-11-20T00:00:00+00:00'
  AND created_at <  '2026-11-26T00:00:00+00:00'
LIMIT 100;
~~~

Đây là ví dụ truy vấn trong **một partition**, với giới hạn trên clustering column đầu tiên. Với truy vấn khác, phải tuân theo quy tắc thứ tự các clustering columns và các điều kiện mà phiên bản CQL hỗ trợ. Không tùy ý lọc `order_id` trước khi ràng buộc các thành phần clustering đứng trước.

`ORDER BY` trong Cassandra không tương đương khả năng sắp xếp tùy ý mọi cột của SQL quan hệ:

- Không dùng `ORDER BY total_amount DESC` trên bảng này để sắp xếp theo giá; `total_amount` là cột thường.
- Không kỳ vọng một câu query tự sắp xếp toàn bộ đơn hàng qua **nhiều partition** theo thời gian.
- Có thể đảo chiều đọc clustering order theo những quy tắc CQL hỗ trợ, nhưng việc hỗ trợ kiểu sắp xếp cụ thể vẫn phụ thuộc định nghĩa khóa.
- Nếu sản phẩm cần “đơn giá trị lớn nhất trong tháng”, cân nhắc **bảng đọc riêng** có clustering theo giá trị và partitioning phù hợp, thay vì tải mọi đơn rồi sort trong JVM.

Nếu cần hỗ trợ nhiều truy vấn sản phẩm khác nhau, **một bảng cho mỗi đường đọc cần thiết** có thể phù hợp với mô hình Cassandra; khi đó ứng dụng phải tính chi phí ghi thêm và đồng bộ các projection.

## 8. Paging với khóa ghép

Phân trang Cassandra dùng **paging state** của truy vấn. Khi partition có hàng nghìn bản ghi, một `LIMIT` nhỏ chỉ phục vụ lần đọc đầu; nếu API cần trang tiếp theo, phải thiết kế cách truyền paging state (hoặc token phù hợp) gắn với **đúng truy vấn và tham số**.

Với Spring Data Cassandra, repository có thể trả `Slice<T>` cho query có `Pageable`; sử dụng `CassandraPageRequest` để đi tiếp theo paging state:

~~~java
import java.time.LocalDate;
import java.util.UUID;
import org.springframework.data.cassandra.core.query.CassandraPageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.cassandra.repository.Query;

// Khai báo trong OrdersByCustomerMonthRepository:
@Query("SELECT * FROM orders_by_customer_month "
     + "WHERE tenant_id = ?0 AND customer_id = ?1 "
     + "AND month_bucket = ?2")
Slice<OrderByCustomerMonth> findInMonth(
        UUID tenantId, UUID customerId,
        LocalDate monthBucket, Pageable pageable);

// Ví dụ trong service:
Slice<OrderByCustomerMonth> first =
        repository.findInMonth(
                tenantId, customerId, monthBucket,
                CassandraPageRequest.first(20));

if (first.hasNext()) {
    Slice<OrderByCustomerMonth> second =
            repository.findInMonth(
                    tenantId, customerId, monthBucket,
                    first.nextPageable());
}
~~~

Ví dụ kết hợp **chữ ký repository** và **đoạn gọi trong service** để trình bày flow; đặt chúng vào đúng class khi triển khai. Các phiên bản Spring Data Cassandra khác nhau có thể khác chi tiết API paging, nên kiểm tra với dependency dự án.

**Không dùng kiểu `OFFSET 10000`** để nhảy trực tiếp tới một vị trí tùy ý như nhiều cơ sở dữ liệu SQL. Paging state đại diện cho tiến độ của một truy vấn; không tái sử dụng nó khi thay `tenant_id`, `customer_id`, tháng hoặc câu query. Nếu API cần ghép danh sách nhiều tháng, ứng dụng phải quản lý paging **từng partition** và cách hợp nhất thứ tự.

## 9. Kiểm tra metadata của bảng và mapping

Sau khi kết nối Cassandra và tạo bảng theo quy trình quản lý schema, có thể dùng `cqlsh` để xem:

~~~text
-- Đây là câu lệnh tiện ích của cqlsh:
DESCRIBE TABLE orders_by_customer_month;
~~~

Hoặc đọc metadata CQL:

~~~sql
SELECT column_name, kind, position, type
FROM system_schema.columns
WHERE keyspace_name = 'learning_data'
  AND table_name = 'orders_by_customer_month';
~~~

Trong ví dụ trên, thay `learning_data` bằng keyspace thật đã được cấu hình. Kết quả mong đợi về cấu trúc:

| Cột | `kind` | `position` | CQL type |
|---|---|---:|---|
| `tenant_id` | `partition_key` | 0 | `uuid` |
| `customer_id` | `partition_key` | 1 | `uuid` |
| `month_bucket` | `partition_key` | 2 | `date` |
| `created_at` | `clustering` | 0 | `timestamp` |
| `order_id` | `clustering` | 1 | `uuid` |
| `status` | `regular` | — | `text` |
| `total_amount` | `regular` | — | `decimal` |

Kiểm tra thứ tự và kiểu này giúp phát hiện lỗi khi annotation `ordinal`, `type`, `@Column` khác schema thực tế. `@PrimaryKeyClass` mô tả **mapping Java**, còn bảng Cassandra là **schema vật lý** cần khớp với mapping.

### 9.1. `schema-action` không thay migration

Một dự án có thể dùng `spring.cassandra.schema-action: CREATE_IF_NOT_EXISTS` ở local/dev để thử tạo bảng từ metadata; production thường để `NONE` và dùng migration CQL có kiểm soát. Nếu bảng đã tồn tại:

- Thêm `@PrimaryKeyColumn` hay sửa `ordinal` **không biến** bảng cũ thành schema mới.
- Đổi `PrimaryKeyType.PARTITIONED` thành `CLUSTERED` làm thay đổi cách định vị partition; thường cần **bảng mới + backfill**.
- Đổi tên một field nằm trong primary key không có nghĩa Cassandra tự rename cột hay chuyển mọi dữ liệu.
- Việc tạo lại bảng có thể gây mất dữ liệu nếu dùng chế độ schema action phá hủy; không bật ngoài môi trường được phép.

Nếu cần sửa primary key production, quy trình thường gồm thiết kế bảng mới, triển khai ghi song song hoặc projection, backfill, đối soát, chuyển tuyến đọc và bỏ bảng cũ sau khi xác nhận an toàn.

## 10. Các lỗi thường gặp với @PrimaryKeyClass

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `findById` không nhận ID mong đợi | Repository khai báo ID là `UUID` thay vì lớp khóa | Dùng `CassandraRepository<Entity, CompositeKey>` |
| Truy vấn theo `customer_id` bị từ chối | Thiếu `tenant_id` và `month_bucket` thuộc partition key | Cung cấp đầy đủ partition key hoặc xây bảng đọc phù hợp |
| Các đơn ghi đè nhau | Thiếu clustering column phân biệt, hoặc dùng lại toàn bộ primary key | Thêm `order_id` vào khóa theo thiết kế và tạo ID ổn định |
| Thứ tự đọc khác mong đợi | `ordering` hoặc thứ tự clustering trong CQL không đúng | Đối chiếu `CLUSTERING ORDER BY` và annotation |
| Mất dữ liệu trong object khi đọc | Field Java khác tên hoặc kiểu CQL | Kiểm tra `@Column`, converter và metadata |
| Lỗi `null` ở khóa lúc ghi | Chưa gán đủ thành phần primary key | Validate tất cả field khóa trước `save` |
| `Map`/`Set` tìm key thất bại | Không có `equals/hashCode` đúng hoặc sửa key sau khi dùng | So sánh đủ các thành phần và không thay key sau khi sử dụng |
| Sửa annotation nhưng schema không đổi | Bảng tồn tại, không có migration | Cập nhật schema qua migration và backfill |
| Partition rất lớn/hot | Partition theo customer nhưng không chia bucket, hoặc một khách có tải bất thường | Thiết kế bucket/shard theo phân bố thật |
| `ALLOW FILTERING` làm truy vấn chậm | Lọc trên cột không thuộc đường truy cập chính | Xem xét read model/index phù hợp thay vì quét |

### 10.1. Key class không phải là logic kiểm soát quyền

Ví dụ `tenantId` là thành phần partition key, nhưng chỉ có field này trong Java **không tự kiểm tra quyền**. Endpoint vẫn phải xác nhận caller có quyền truy cập tenant tương ứng. Không nhận tenant ID từ client rồi tin tuyệt đối vào giá trị đó khi xây CQL.

### 10.2. Cập nhật một cột khóa là di chuyển hàng

Giả sử đơn hàng có `created_at` hoặc `month_bucket` cần sửa. Vì các giá trị đó nằm trong primary key, Cassandra không thay chúng tại chỗ theo một `UPDATE` thông thường. Cần ghi hàng ở khóa mới và xử lý hàng ở khóa cũ, cùng những projection liên quan. Tác vụ xóa tạo tombstone nên phải cân nhắc chi phí đọc và chính sách TTL.

Nếu thời gian tạo không nên thay đổi theo nghiệp vụ, giữ nó ổn định; nếu sản phẩm cần sắp xếp theo thời điểm cập nhật thường xuyên thay đổi, hãy thiết kế **bảng truy cập theo thời điểm cập nhật** thay vì sửa bất chấp khóa phân cụm của bảng hiện có.

## 11. Kết nối với consistency và hiệu năng Cassandra

`@PrimaryKeyClass` xác định **cách ánh xạ khóa**, không trực tiếp quyết định consistency level. Việc chọn `LOCAL_ONE`, `LOCAL_QUORUM` hoặc mức khác nằm ở cấu hình statement/driver/repository phù hợp, trong khi replication thuộc keyspace.

Một bảng đọc theo `orders_by_customer_month` có thể được chọn vì tốc độ đọc tốt, nhưng ứng dụng còn có bảng `orders_by_id` để tra một đơn theo ID. Ghi vào hai bảng là **hai mutation** và reader có thể tạm quan sát projection chưa đồng bộ. Lựa chọn consistency level cao hơn cho mỗi statement không biến hai bảng thành một transaction ACID thống nhất. Cần idempotency, xử lý lỗi từng bước và cơ chế đối soát.

Các chỉ số cần theo dõi sau khi triển khai:

- **Kích thước partition** và các khách hàng có khối lượng đơn vượt trội.
- **p50/p95/p99 latency** của truy vấn theo tháng; timeout, retry và số request đang bay.
- **Tombstones** do xóa/cập nhật khóa hoặc chính sách TTL.
- **Số trang và số hàng** được đọc, bộ nhớ khi ghép kết quả nhiều tháng.
- **Write amplification** khi một đơn được lưu ở nhiều bảng theo các query pattern.

Không có một kích thước partition hoặc page size lý tưởng cho mọi hệ thống. Cần đo trên dữ liệu đại diện và giới hạn API có thể thực thi, thay vì suy luận rằng cứ dùng UUID hoặc thêm month bucket là mọi hot partition sẽ biến mất.

## 12. Bài tập thực hành

Hệ thống logistics cần lưu nhật ký quét mã kiện hàng. API yêu cầu:

~~~text
GET /packages/{packageId}/scans?day=2026-11-25&limit=50
~~~

Trong một ngày, cần đọc 50 lần quét mới nhất của đúng một kiện hàng. Một bảng dự kiến:

~~~sql
CREATE TABLE package_scans_by_day (
    package_id uuid,
    scan_day date,
    scanned_at timestamp,
    scan_id uuid,
    hub_id uuid,
    scan_status text,
    PRIMARY KEY ((package_id, scan_day), scanned_at, scan_id)
) WITH CLUSTERING ORDER BY (scanned_at DESC, scan_id ASC);
~~~

**Yêu cầu thực hiện:**

1. Tạo lớp `PackageScanKey` dùng `@PrimaryKeyClass`.
2. Đánh dấu `package_id`, `scan_day` là `PARTITIONED` với ordinal 0 và 1.
3. Đánh dấu `scanned_at`, `scan_id` là `CLUSTERED` với ordinal 2 và 3; cột thời gian `DESCENDING`.
4. Tạo `PackageScan` với `@PrimaryKey PackageScanKey id`, `@Column("hub_id")` và `@Column("scan_status")`.
5. Tạo repository dùng `CassandraRepository<PackageScan, PackageScanKey>` và phương thức CQL lấy 50 hàng theo `package_id`/`scan_day`.
6. Xác định phải sửa gì nếu sản phẩm bổ sung “tìm mọi lần quét trong ngày tại một `hub_id`”.

Gợi ý khai báo khóa:

~~~java
@PrimaryKeyClass
public class PackageScanKey implements Serializable {
    @PrimaryKeyColumn(name = "package_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID packageId;

    @PrimaryKeyColumn(name = "scan_day", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private LocalDate scanDay;

    @PrimaryKeyColumn(name = "scanned_at", ordinal = 2,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.DESCENDING)
    private Instant scannedAt;

    @PrimaryKeyColumn(name = "scan_id", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED,
            ordering = Ordering.ASCENDING)
    private UUID scanId;

    // Constructor, getters/setters, equals/hashCode trên cả bốn field.
}
~~~

Đoạn trên là **phác thảo của lớp**, cần imports như ở ví dụ chính và hoàn thiện các phương thức trước khi biên dịch. Câu (6) có thể dẫn đến một bảng truy cập `package_scans_by_hub_day` với partition key theo `(hub_id, scan_day)`, clustering theo thời gian và `scan_id`, sau khi cân nhắc lưu lượng của hub lớn, time bucket hoặc shard. Không thể chỉ thêm `findByHubId` vào repository của bảng cũ rồi mặc định truy vấn hiệu quả.

### Câu hỏi tự kiểm tra

1. `@PrimaryKeyClass` được dùng trên entity hay trên kiểu chứa các thành phần khóa?
2. `@PrimaryKeyColumn(type = PARTITIONED)` khác `CLUSTERED` như thế nào?
3. Vì sao repository `findById` cần toàn bộ `OrderByCustomerMonthKey`, còn query danh sách theo tháng chỉ cần ba trường partition key?
4. Nếu có hai đơn cùng `created_at` trong một partition, thành phần nào giúp phân biệt?
5. Chỉnh `ordinal` của `created_at` trong Java có tự tổ chức lại bảng Cassandra đã có dữ liệu không?
6. Vì sao một paging state của tháng 11 không dùng lại cho truy vấn tháng 10?

**Đáp án ngắn:** (1) trên lớp khóa; (2) partition quyết định vị trí, clustering quyết định thứ tự hàng trong partition; (3) một hàng cần đủ primary key, còn một partition gồm nhiều hàng chỉ cần partition key; (4) `order_id`; (5) không, cần migration/bảng mới khi thay khóa; (6) paging state gắn với truy vấn và tham số của nó.

## 13. Checklist khi triển khai khóa ghép

- [ ] Có truy vấn nghiệp vụ cụ thể trước khi quyết định primary key.
- [ ] Phân biệt rõ **composite partition key**, **clustering columns** và **toàn bộ khóa hàng**.
- [ ] `@PrimaryKeyClass` chứa đúng các cột khóa, `@PrimaryKeyColumn` khai báo đúng `name/type/ordinal/ordering`.
- [ ] Entity sử dụng `@PrimaryKey` trên field có đúng kiểu lớp khóa.
- [ ] Repository khai báo kiểu ID là lớp khóa ghép, không khai báo một trường UUID riêng.
- [ ] Key class có constructor/accessor thích hợp, `equals/hashCode` dựa trên toàn bộ khóa.
- [ ] Mọi field khóa đều có giá trị hợp lệ; ID và thời gian nghiệp vụ được tái sử dụng khi retry.
- [ ] Đã đối chiếu schema thực tế, kiểu CQL, vị trí partition/clustering và thứ tự clustering.
- [ ] Các query CQL cung cấp đủ partition key; không dùng `ALLOW FILTERING` như lối đi mặc định.
- [ ] Dữ liệu một partition có giới hạn thực tế, API có paging và giới hạn đồng thời khi cần.
- [ ] Nếu đổi primary key, có kế hoạch bảng mới/migration/backfill và kiểm tra consistency.
- [ ] Đã đo p95/p99, hot partitions, tombstones và chi phí đọc/ghi với dữ liệu đại diện.

## Tài liệu tham khảo

- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Spring Data Cassandra — Repository Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Data Cassandra — Configuration](https://docs.spring.io/spring-data/cassandra/reference/cassandra/configuration.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra — CQL Data Definition](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/ddl.html).

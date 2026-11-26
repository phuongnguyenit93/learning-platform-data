# @PrimaryKeyColumn: loại khóa, thứ tự và hướng sắp xếp

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt **partition key**, **clustering column** và các thành phần còn lại của primary key trong Apache Cassandra.
- Sử dụng `@PrimaryKeyColumn` với `type = PrimaryKeyType.PARTITIONED` hoặc `PrimaryKeyType.CLUSTERED`, hiểu đúng `ordinal` và `ordering`.
- Ánh xạ khóa chính ghép bằng `@PrimaryKeyClass` và `@PrimaryKey` trong Spring Data Cassandra, đồng thời nhận biết cách khai báo `@PrimaryKeyColumn` trực tiếp trên entity.
- Đối chiếu Java mapping với CQL `PRIMARY KEY (...)` và `WITH CLUSTERING ORDER BY (...)` để tránh sai lệch schema.
- Viết truy vấn có partition key đầy đủ, đọc theo clustering order, xử lý trường hợp trùng mốc thời gian, phân trang và giới hạn kích thước partition.
- Phân tích các lỗi thực tế: đảo `ordinal`, gán nhầm loại khóa, tưởng `DESC` là sắp xếp toàn bảng, thay đổi giá trị primary key khi cập nhật entity.

Bài học nằm trong chương **Ánh xạ entity** của **SPRING_DATA_CASSANDRA**: sử dụng Spring Data Cassandra để truy cập Apache Cassandra bằng entity mapping, repository, `CassandraTemplate` và CQL. Mô hình dữ liệu Cassandra được thiết kế **theo truy vấn**; vì thế `@PrimaryKeyColumn` không chỉ giúp map thuộc tính Java thành cột. Các thành phần khóa quyết định **cách định tuyến partition**, **thứ tự dòng bên trong partition** và **những truy vấn được thực thi hiệu quả**.

## 1. Primary key của Cassandra không giống chỉ một ID trong JPA

Trong cơ sở dữ liệu quan hệ, một primary key thường chủ yếu xác định duy nhất bản ghi. Các truy vấn lọc và sắp xếp khác có thể được hỗ trợ bằng index và phép `JOIN`. Cassandra là cơ sở dữ liệu phân tán dạng wide-column, nên cấu trúc primary key còn quyết định đường truy cập dữ liệu.

Xét bảng lưu đơn hàng để đáp ứng yêu cầu:

> “Lấy 20 đơn gần nhất của một khách hàng trong một tháng.”

Nếu lưu mọi đơn theo `order_id` mà không có bảng phục vụ khách hàng, truy vấn lịch sử phải tìm trên rất nhiều partition. Thay vào đó, tạo bảng dành riêng cho đường đọc:

~~~sql
CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    order_id ASC
);
~~~

Khóa của bảng trên có hai nhóm:

~~~text
PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
             └───────────┬─────────────┘  └────────┬─────────┘
                  Partition key               Clustering columns
                  (2 thành phần)               (2 thành phần)

Partition: (customer_id, month_bucket)
  ├── Dòng created_at mới nhất, order_id thấp hơn nếu cùng timestamp
  ├── Dòng created_at tiếp theo
  └── ...
~~~

| Thành phần | Loại khóa | Vai trò |
| --- | --- | --- |
| `customer_id` | Partition key, phần 1 | Giới hạn lịch sử vào một khách hàng |
| `month_bucket` | Partition key, phần 2 | Chia lịch sử theo tháng để tránh một partition tăng vô hạn |
| `created_at` | Clustering column, vị trí 1 | Sắp xếp các đơn trong cùng partition theo thời gian giảm dần |
| `order_id` | Clustering column, vị trí 2 | Phân biệt các đơn có cùng thời điểm và tạo thứ tự phụ xác định |
| `status`, `total_amount` | Cột dữ liệu thường | Được đọc/ghi cùng row nhưng không tham gia định danh khóa |

Cassandra dùng **toàn bộ các thành phần partition key** làm đầu vào cho cơ chế phân phối token; các replica của partition được chọn theo token và chính sách replication của keyspace. Các clustering column xác định danh tính dòng **bên trong partition đó** và thứ tự lưu trữ logic. Hai đơn có cùng `customer_id`, `month_bucket`, `created_at` nhưng khác `order_id` là hai dòng khác nhau.

Đây là lý do cần phân biệt rõ hai loại `@PrimaryKeyColumn`.

## 2. Cú pháp và ý nghĩa của @PrimaryKeyColumn

Annotation `@PrimaryKeyColumn` thuộc package:

~~~java
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;
import org.springframework.data.cassandra.core.cql.Ordering;
~~~

Ví dụ minh họa:

~~~java
@PrimaryKeyColumn(
    name = "created_at",
    ordinal = 2,
    type = PrimaryKeyType.CLUSTERED,
    ordering = Ordering.DESCENDING
)
private Instant createdAt;
~~~

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Cách dùng |
| --- | --- | --- |
| `name` | Tên cột CQL được ánh xạ | Đặt tường minh nếu Java dùng `createdAt`, CQL dùng `created_at` |
| `ordinal` | Vị trí của thành phần trong thứ tự khóa mà Spring Data ánh xạ | Quy ước từ `0`, duy nhất và liên tục cho từng thành phần khóa |
| `type` | Phân biệt partition key và clustering column | `PrimaryKeyType.PARTITIONED` hoặc `PrimaryKeyType.CLUSTERED` |
| `ordering` | Hướng sắp xếp của clustering column | `Ordering.ASCENDING` hoặc `Ordering.DESCENDING`; chỉ có ý nghĩa sắp xếp với clustering column |

`@PrimaryKeyColumn` không phải annotation của JPA. Nó mô tả metadata khóa cho Spring Data Cassandra. Annotation **không tự thay đổi bảng Cassandra đang tồn tại**. Nếu schema được quản lý bằng migration/CQL và Spring Boot đặt `spring.cassandra.schema-action: none`, CQL thực tế vẫn là nguồn xác định cấu trúc bảng.

### 2.1. type = PARTITIONED

Dùng `PrimaryKeyType.PARTITIONED` cho mọi thành phần của partition key:

~~~java
@PrimaryKeyColumn(
    name = "customer_id",
    ordinal = 0,
    type = PrimaryKeyType.PARTITIONED
)
private UUID customerId;

@PrimaryKeyColumn(
    name = "month_bucket",
    ordinal = 1,
    type = PrimaryKeyType.PARTITIONED
)
private String monthBucket;
~~~

Hai annotation trên tương ứng với phần `(customer_id, month_bucket)` của CQL.

Điểm cần nhớ:

- **Cả hai cột cùng tạo một partition key ghép**, không phải hai partition key độc lập để tùy ý truy vấn từng cột.
- Để truy vấn chính xác một partition theo bảng này, thông thường phải cung cấp cả `customer_id` và `month_bucket`.
- Thứ tự các thành phần partition key là một phần của định nghĩa schema, nhưng **không tạo thứ tự sắp xếp giữa các partition**.
- `ordering = DESCENDING` không có tác dụng biến một partition key thành danh sách dữ liệu giảm dần. Sắp xếp nội bộ thuộc về clustering columns.

Ví dụ hai partition độc lập:

~~~text
(customer_id = A, month_bucket = "2026-10")
(customer_id = A, month_bucket = "2026-11")
~~~

Các đơn của cùng khách hàng nhưng ở hai tháng **không** nằm trong một chuỗi sắp xếp chung do Cassandra tự cung cấp. Ứng dụng phải biết cần đọc những bucket nào và tổ chức việc ghép kết quả nếu giao diện cần xem liên tục qua nhiều tháng.

### 2.2. type = CLUSTERED

Dùng `PrimaryKeyType.CLUSTERED` cho những cột xác định thứ tự/danh tính các dòng trong một partition:

~~~java
@PrimaryKeyColumn(
    name = "created_at",
    ordinal = 2,
    type = PrimaryKeyType.CLUSTERED,
    ordering = Ordering.DESCENDING
)
private Instant createdAt;

@PrimaryKeyColumn(
    name = "order_id",
    ordinal = 3,
    type = PrimaryKeyType.CLUSTERED,
    ordering = Ordering.ASCENDING
)
private UUID orderId;
~~~

`created_at` là clustering column đầu tiên nên quyết định thứ tự ưu tiên. `order_id` là clustering column thứ hai, chỉ phân biệt/sắp xếp các dòng khi giá trị `created_at` bằng nhau. Cấu trúc này phù hợp yêu cầu “đơn mới nhất trước, có quy tắc phân biệt khi cùng thời điểm”.

Nếu không đưa `order_id` vào khóa, hai đơn có cùng timestamp trong cùng partition sẽ có **cùng primary key**. Lệnh INSERT/UPDATE tiếp theo khi đó tác động vào cùng row, gây mất khả năng lưu riêng hai đơn. Vì timestamp có thể trùng, một thành phần khóa ổn định để phân biệt dòng là rất quan trọng.

### 2.3. ordinal là thứ tự trong metadata khóa, không phải thứ tự field Java

Hai class sau có thể khai báo field theo thứ tự nguồn Java khác nhau nhưng ánh xạ đúng nếu `ordinal` và `type` nhất quán. Java reflection và thứ tự khai báo field không nên được dùng làm nguồn suy đoán thứ tự primary key.

Với bảng ví dụ, quy ước rõ ràng là:

| `ordinal` | Cột | `type` | `ordering` |
| ---: | --- | --- | --- |
| 0 | `customer_id` | `PARTITIONED` | Không dùng để sắp xếp |
| 1 | `month_bucket` | `PARTITIONED` | Không dùng để sắp xếp |
| 2 | `created_at` | `CLUSTERED` | `DESCENDING` |
| 3 | `order_id` | `CLUSTERED` | `ASCENDING` |

Tránh dùng `ordinal` trùng lặp hoặc tạo ánh xạ mà một clustering column được đặt trước các thành phần partition key. Về mặt CQL, các thành phần partition key luôn thuộc phần ngoặc kép của `PRIMARY KEY` trước các clustering column.

Nếu đổi `ordinal` của `created_at` và `order_id`, ý nghĩa của khóa thay đổi: ưu tiên sắp xếp theo ID rồi mới theo thời gian, trái với truy vấn đơn mới nhất. Đổi annotation Java **không** chuyển đổi lại dữ liệu và schema CQL đã tồn tại.

## 3. Ví dụ hoàn chỉnh: khóa ghép với @PrimaryKeyClass

Spring Data Cassandra hỗ trợ khai báo một class chứa khóa chính ghép, sau đó nhúng khóa vào entity. Đây là cách dễ quản lý khi repository dùng khóa nhiều thành phần.

### 3.1. Tạo lớp khóa

File Java minh họa `OrderByCustomerMonthKey.java`:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class OrderByCustomerMonthKey implements Serializable {

    private static final long serialVersionUID = 1L;

    @PrimaryKeyColumn(
        name = "customer_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "month_bucket",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED
    )
    private String monthBucket;

    @PrimaryKeyColumn(
        name = "created_at",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id",
        ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING
    )
    private UUID orderId;

    public OrderByCustomerMonthKey() {
    }

    public OrderByCustomerMonthKey(
            UUID customerId,
            String monthBucket,
            Instant createdAt,
            UUID orderId) {
        this.customerId = customerId;
        this.monthBucket = monthBucket;
        this.createdAt = createdAt;
        this.orderId = orderId;
    }

    public UUID getCustomerId() {
        return customerId;
    }

    public void setCustomerId(UUID customerId) {
        this.customerId = customerId;
    }

    public String getMonthBucket() {
        return monthBucket;
    }

    public void setMonthBucket(String monthBucket) {
        this.monthBucket = monthBucket;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public UUID getOrderId() {
        return orderId;
    }

    public void setOrderId(UUID orderId) {
        this.orderId = orderId;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof OrderByCustomerMonthKey)) {
            return false;
        }
        OrderByCustomerMonthKey that = (OrderByCustomerMonthKey) other;
        return Objects.equals(customerId, that.customerId)
            && Objects.equals(monthBucket, that.monthBucket)
            && Objects.equals(createdAt, that.createdAt)
            && Objects.equals(orderId, that.orderId);
    }

    @Override
    public int hashCode() {
        return Objects.hash(customerId, monthBucket, createdAt, orderId);
    }
}
~~~

Những điểm cần kiểm chứng:

- `@PrimaryKeyClass` đánh dấu type chứa các thành phần khóa ghép.
- Mỗi field mang `@PrimaryKeyColumn` có tên cột và `ordinal` khớp với CQL ở phần 1.
- `customerId` và `monthBucket` là hai phần của partition key; `createdAt` và `orderId` thuộc clustering key.
- Các field khóa có giá trị **không null** trước khi insert/save; một thành phần primary key null không tạo ra row hợp lệ trong Cassandra.
- `equals()`/`hashCode()` dựa trên **tất cả thành phần khóa**, giúp so sánh các object khóa đúng nghĩa. Không lấy `status` hoặc `totalAmount` làm thành phần khóa.
- Sau khi dùng key để lưu một row, nên **coi giá trị khóa là bất biến về nghiệp vụ**. Nếu cần thay đổi khóa, đó là một row khác trong Cassandra, phải xử lý bản ghi cũ.

Trong ứng dụng Java hiện đại, có thể cân nhắc immutable mapping/constructor binding nếu phiên bản Spring Data Cassandra hỗ trợ đúng cách. Ví dụ trên dùng no-arg constructor và setter để việc ánh xạ dễ theo dõi, không yêu cầu Lombok.

### 3.2. Tạo entity sử dụng khóa ghép

File minh họa `OrderByCustomerMonth.java`:

~~~java
import java.math.BigDecimal;

import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_month")
public class OrderByCustomerMonth {

    @PrimaryKey
    private OrderByCustomerMonthKey key;

    @Column("status")
    private String status;

    @Column("total_amount")
    private BigDecimal totalAmount;

    public OrderByCustomerMonth() {
    }

    public OrderByCustomerMonth(
            OrderByCustomerMonthKey key,
            String status,
            BigDecimal totalAmount) {
        this.key = key;
        this.status = status;
        this.totalAmount = totalAmount;
    }

    public OrderByCustomerMonthKey getKey() {
        return key;
    }

    public void setKey(OrderByCustomerMonthKey key) {
        this.key = key;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }
}
~~~

Ở đây, `@PrimaryKey` trỏ đến **toàn bộ object khóa**, còn `@PrimaryKeyColumn` nằm trong class `OrderByCustomerMonthKey`. Không cần khai báo thêm một `@PrimaryKey` riêng cho `customerId` hay `orderId` trong entity này.

CQL `timestamp` phù hợp với `Instant`, `uuid` với `UUID` và `decimal` với `BigDecimal`. `month_bucket` dùng `text` như `"2026-11"` để dễ vận hành; ứng dụng phải bảo đảm tạo bucket theo múi giờ/quy tắc nghiệp vụ nhất quán.

### 3.3. Repository sử dụng type khóa ghép

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;
import java.util.List;
import java.util.UUID;

public interface OrderByCustomerMonthRepository
        extends CassandraRepository<
            OrderByCustomerMonth,
            OrderByCustomerMonthKey> {

    @Query(
        "SELECT * FROM orders_by_customer_month "
      + "WHERE customer_id = ?0 AND month_bucket = ?1 LIMIT 20"
    )
    List<OrderByCustomerMonth> findLatestTwenty(
        UUID customerId,
        String monthBucket);
}
~~~

Type thứ hai trong `CassandraRepository<Entity, ID>` phải là `OrderByCustomerMonthKey` chứ không phải `UUID`. Một ID xác định **một row** bao gồm tất cả phần partition và clustering, không chỉ `order_id`.

Ví dụ:

~~~java
OrderByCustomerMonthKey key = new OrderByCustomerMonthKey(
    customerId,
    "2026-11",
    createdAt,
    orderId
);

repository.findById(key)
    .ifPresent(row -> System.out.println(row.getStatus()));
~~~

`findById(key)` có đủ bốn thành phần khóa để tra cứu một row. Trái lại, `findLatestTwenty(customerId, "2026-11")` có đủ partition key để lấy **nhiều row trong cùng partition** và tận dụng thứ tự clustering giảm dần đã khai báo.

## 4. Có thể dùng @PrimaryKeyColumn trực tiếp trên entity không?

Có. Với khóa ngắn, có thể đánh dấu từng thành phần trực tiếp trên entity thay vì tạo `@PrimaryKeyClass` riêng.

Giả sử bảng CQL:

~~~sql
CREATE TABLE events_by_device (
    device_id uuid,
    event_at timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY ((device_id), event_at, event_id)
) WITH CLUSTERING ORDER BY (
    event_at DESC,
    event_id ASC
);
~~~

Ánh xạ:

~~~java
@Table("events_by_device")
public class EventByDevice {

    @PrimaryKeyColumn(
        name = "device_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID deviceId;

    @PrimaryKeyColumn(
        name = "event_at",
        ordinal = 1,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private Instant eventAt;

    @PrimaryKeyColumn(
        name = "event_id",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING
    )
    private UUID eventId;

    @Column("payload")
    private String payload;

    // Constructor, getter và setter...
}
~~~

Ví dụ này rút gọn các phần Java thông thường để tập trung vào mapping; cần import `@Table`, `@Column`, `@PrimaryKeyColumn`, `PrimaryKeyType`, `Ordering`, `UUID` và `Instant`.

Hai cách có cùng mục đích ánh xạ primary key, nhưng chọn cách nào cần nhất quán:

| Cách khai báo | Ưu điểm | Điều cần lưu ý |
| --- | --- | --- |
| `@PrimaryKeyClass` + entity có `@PrimaryKey` | ID là object có nghĩa rõ ràng; thuận tiện truyền/so sánh khóa ghép trong repository | Thêm class, cần `equals()`/`hashCode()` và constructors phù hợp |
| Nhiều `@PrimaryKeyColumn` trực tiếp trên entity | Đơn giản với bảng và khóa ngắn | Cần hiểu cách Spring Data biểu diễn ID ghép trong repository; không giả định ID là một field `UUID` |

Không trộn hai cách khai báo cho **cùng một khóa** theo cách tạo hai nguồn metadata mâu thuẫn. Đặc biệt, không đặt `@PrimaryKey` lên `orderId` nếu bảng có primary key ghép được mô tả bởi các `@PrimaryKeyColumn` khác.

## 5. Đối chiếu Java mapping và schema CQL

Hãy luôn kiểm tra ba nguồn thông tin sau **khớp nhau**:

1. CQL `CREATE TABLE` đang triển khai thực tế trên cluster.
2. Annotation Java `@PrimaryKeyColumn` (`name`, `ordinal`, `type`, `ordering`).
3. Đường truy vấn thật trong repository, `CassandraTemplate` hoặc CQL.

Bảng đối chiếu:

| CQL | Java mapping | Ý nghĩa |
| --- | --- | --- |
| `PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)` | `customerId: PARTITIONED 0`, `monthBucket: PARTITIONED 1`, `createdAt: CLUSTERED 2`, `orderId: CLUSTERED 3` | Định tuyến partition và thứ tự ưu tiên các thành phần khóa |
| `CLUSTERING ORDER BY (created_at DESC, order_id ASC)` | `createdAt: DESCENDING`, `orderId: ASCENDING` | Hướng clustering khai báo phải phù hợp |
| `created_at timestamp` | `Instant createdAt` | CQL timestamp và kiểu Java |
| `order_id uuid` | `UUID orderId` | CQL UUID và kiểu Java |
| `month_bucket text` | `String monthBucket` | Kiểu bucket nhất quán |

### 5.1. Annotation không tự sửa schema đã có

Nếu người phát triển đổi annotation:

~~~java
@PrimaryKeyColumn(
    name = "created_at",
    ordinal = 2,
    type = PrimaryKeyType.CLUSTERED,
    ordering = Ordering.ASCENDING  // Trước đó là DESCENDING
)
private Instant createdAt;
~~~

Trong khi CQL vẫn là:

~~~sql
WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC)
~~~

thì **không** được giả định Cassandra đã đổi thứ tự lưu trữ chỉ vì Java build thành công. Khi schema quản lý bằng migration hoặc `schema-action: none`, annotation chỉ là metadata trong ứng dụng. Cần giữ các định nghĩa nhất quán.

Thay đổi cấu trúc primary key của một bảng đã có dữ liệu thường không phải thao tác `ALTER TABLE` đơn giản. Phương án thực tế thường là tạo bảng mới phù hợp truy vấn, backfill/đồng bộ dữ liệu, xác minh và chuyển đường đọc có kiểm soát.

### 5.2. Xem schema thật trong cqlsh

~~~sql
-- Lệnh tiện ích của cqlsh, không phải truy vấn CQL thông thường:
DESCRIBE TABLE order_service.orders_by_customer_month;
~~~

Và truy vấn metadata hệ thống:

~~~sql
SELECT column_name, kind, position, clustering_order, type
FROM system_schema.columns
WHERE keyspace_name = 'order_service'
  AND table_name = 'orders_by_customer_month';
~~~

Cột `kind` có thể cho biết `partition_key`, `clustering` hoặc `regular`; `position` biểu diễn vị trí **trong từng nhóm khóa của schema Cassandra**, còn `clustering_order` cho biết hướng sắp xếp của clustering columns. Không so sánh máy móc `position` của `system_schema.columns` với toàn bộ dãy `ordinal` trong Java: `position` thường bắt đầu lại từ 0 cho nhóm partition key và cho nhóm clustering, trong khi ví dụ Java đánh số tuần tự từ 0 qua tất cả thành phần khóa.

Nếu metadata khác với lớp Java, cần rà soát migration và phương thức mapping trước khi vận hành. Không bật sinh schema tự động trên production để chữa lệch cấu trúc khóa khi chưa có kế hoạch chuyển đổi dữ liệu.

## 6. Query-driven design quyết định cách chọn khóa

Với bảng `orders_by_customer_month`, truy vấn chính cần có **đủ partition key**:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Do `created_at DESC` và `order_id ASC` được khai báo trong schema, truy vấn đọc từ đầu partition theo thứ tự clustering mặc định sẽ gặp những đơn mới trước.

Đối với một khoảng thời gian thuộc cùng bucket:

~~~sql
SELECT order_id, created_at, status
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
  AND created_at >= ?
  AND created_at < ?;
~~~

Cassandra có thể tìm phạm vi dựa trên clustering column đầu tiên sau khi đã xác định partition. Quy tắc dùng clustering column phụ thuộc thứ tự của nó trong primary key: muốn lọc trực tiếp theo clustering column đứng sau thường phải ràng buộc hợp lệ các cột đứng trước.

### 6.1. Những truy vấn không phù hợp

~~~sql
-- Thiếu month_bucket, không chỉ định đầy đủ partition key ghép:
SELECT * FROM orders_by_customer_month
WHERE customer_id = ?;

-- Không có partition key:
SELECT * FROM orders_by_customer_month
WHERE status = 'PAID';

-- Muốn ORDER BY trên toàn bộ khách hàng/tháng:
SELECT * FROM orders_by_customer_month
ORDER BY created_at DESC;
~~~

Các truy vấn này không khớp access pattern mà bảng được thiết kế để phục vụ. Tùy câu lệnh và chỉ mục hiện hữu, Cassandra có thể từ chối hoặc cần cơ chế lọc/tìm kiếm khác, nhưng **không** nên coi `ALLOW FILTERING` là cách sửa thông thường: nó có thể khiến truy vấn phải quét rất nhiều dữ liệu và độ trễ khó dự báo.

Giải pháp tùy nhu cầu:

- Nếu cần tra cứu chi tiết theo `order_id`, tạo bảng `orders_by_id` với partition key `order_id`.
- Nếu cần đơn theo trạng thái của một cửa hàng trong ngày, thiết kế thêm bảng theo `(store_id, status, day_bucket)`, sau đó chọn clustering phù hợp.
- Nếu cần lịch sử dài qua nhiều tháng, ứng dụng xác định các bucket cần đọc, giới hạn mức song song và ghép kết quả theo hợp đồng phân trang.
- Nếu thực sự cần tìm kiếm/lọc linh hoạt, cân nhắc cơ chế index/search phù hợp phiên bản Cassandra và workload, đo trước khi quyết định.

Cassandra cho phép **denormalization có chủ đích** để phục vụ nhiều cách đọc. Khi lưu một đơn ở nhiều bảng, ứng dụng phải đảm bảo việc cập nhật các bản sao nghiệp vụ; replication factor của keyspace không tự đồng bộ dữ liệu giữa các bảng này.

### 6.2. CassandraTemplate có thay đổi luật CQL không?

Không. `CassandraTemplate` hỗ trợ xây dựng query và ánh xạ kết quả:

~~~java
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

// cassandraTemplate được inject qua constructor.
Query query = Query.query(
        Criteria.where("customer_id").is(customerId))
    .and(Criteria.where("month_bucket").is("2026-11"))
    .limit(20);

List<OrderByCustomerMonth> latest =
    cassandraTemplate.select(query, OrderByCustomerMonth.class);
~~~

Query này sử dụng đủ partition key; trình ánh xạ sẽ dựng lại `OrderByCustomerMonthKey` từ các cột khóa. Không có tính năng nào ở repository hoặc template làm biến truy vấn bỏ `month_bucket` thành đường truy cập partition hiệu quả.

Cũng không cần tự đặt `ORDER BY` tùy ý trong Java nếu thứ tự lưu trữ mặc định của bảng đã phục vụ đúng danh sách “mới nhất trước”. Nếu muốn thứ tự ngược, hãy xem các quy tắc của CQL `ORDER BY` trên clustering columns; nó chỉ áp dụng trong phạm vi partition hợp lệ và không phải sắp xếp toàn cụm.

## 7. Hướng sắp xếp: ASCENDING, DESCENDING và các giới hạn

### 7.1. Hướng sắp xếp quyết định thứ tự trong *một partition*

Giả sử một khách hàng có ba đơn cùng tháng:

| `created_at` (UTC) | `order_id` rút gọn | `status` |
| --- | --- | --- |
| 2026-11-20 10:00:00 | A | PAID |
| 2026-11-20 10:00:00 | B | NEW |
| 2026-11-19 18:30:00 | C | SHIPPED |

Với `created_at DESC` và `order_id ASC`, Cassandra trả hai dòng ngày 20 trước dòng ngày 19; trong nhóm cùng thời gian, thứ tự theo **giá trị UUID thực** (được so sánh theo quy tắc kiểu UUID), không phải theo ký tự A/B đặt tên minh họa. Nếu cần thứ tự nghiệp vụ cụ thể khi trùng timestamp, phải chọn clustering column phù hợp với quy tắc đó.

> **Lưu ý:** `Ordering.DESCENDING` không tạo “bảng đã sắp xếp giảm dần theo thời gian trên toàn cluster”. Thứ tự chỉ có nghĩa **giữa các dòng thuộc cùng một partition**. Mọi truy vấn phân trang xuyên nhiều partition phải có cơ chế ghép/điều phối riêng.

### 7.2. ORDER BY trong CQL có quy tắc

Trên partition đã xác định, truy vấn có thể yêu cầu thứ tự clustering phù hợp:

~~~sql
SELECT order_id, created_at, status
FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
ORDER BY created_at DESC
LIMIT 20;
~~~

Tùy schema, Cassandra có thể đọc theo thứ tự khai báo hoặc theo hướng ngược tương ứng; không thể tùy ý đảo độc lập từng cột clustering theo mọi tổ hợp mà không xem quy tắc `ORDER BY` của CQL. Đặc biệt, không thể dùng `ORDER BY status` khi `status` chỉ là cột dữ liệu thường rồi mong Cassandra sắp xếp không giới hạn trên toàn bảng.

Thứ tự mặc định trong schema và kiểu query phải được chọn **trước** khi tạo bảng, dựa trên màn hình/luồng xử lý sử dụng thường xuyên nhất. Phép đọc ngược có thể được hỗ trợ, nhưng việc lựa chọn clustering order vẫn cần kiểm chứng về hiệu năng và giới hạn phiên bản Cassandra.

### 7.3. ordinals và hướng sort không thay thế thứ tự lọc

Với clustering key `(created_at, order_id)`, truy vấn theo:

~~~sql
WHERE customer_id = ?
  AND month_bucket = ?
  AND order_id = ?
~~~

không thể được coi là tra cứu trực tiếp tốt chỉ vì `order_id` là clustering column. Nó đứng **sau** `created_at`, nên việc bỏ điều kiện trên cột clustering trước có thể bị từ chối hoặc đòi hỏi cơ chế lọc khác. Muốn tra cứu theo `order_id`, dùng bảng `orders_by_id` hoặc đường dữ liệu thiết kế riêng.

## 8. Thêm bucket và chọn clustering để giữ partition có giới hạn

Tại sao ví dụ dùng `month_bucket` trong partition key, thay vì chỉ `customer_id`?

Nếu một khách hàng có rất nhiều đơn trong nhiều năm, partition `customer_id` có thể tăng đến mức đọc, compaction và repair tốn tài nguyên. Bucket theo tháng chia dữ liệu thành nhiều partition có giới hạn tương đối:

~~~text
(customer=A, month=2026-09) -> danh sách tháng 09
(customer=A, month=2026-10) -> danh sách tháng 10
(customer=A, month=2026-11) -> danh sách tháng 11
~~~

Lựa chọn bucket phải dựa trên tốc độ tăng dữ liệu và cách người dùng đọc:

| Bucket | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Theo tháng | Dễ vận hành cho lịch sử vừa phải | Khách hàng rất lớn vẫn có thể tạo partition nóng |
| Theo ngày | Giới hạn số dòng từng partition tốt hơn | Truy vấn dài ngày phải đọc nhiều partition |
| Theo tháng + shard | Phân tán tải cao trong tháng | Phức tạp hơn khi đọc/sắp xếp và phân trang xuyên shard |

Không có kích thước partition tối ưu cho mọi hệ thống. Cần đo partition size, độ trễ p95/p99, hot keys, lượng tombstone, compaction và mẫu truy vấn. Thêm shard có thể làm giảm hotspot nhưng tăng số partition mà API phải đọc, nên cần cân nhắc chi phí hai chiều.

### 8.1. Paging không phải OFFSET

Truy vấn:

~~~sql
SELECT * FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
LIMIT 100;
~~~

`LIMIT 100` giới hạn tổng số row trả về theo ngữ nghĩa CQL. Trong Java Driver, **page size** quy định số row mục tiêu cho một lần tải trang, còn **paging state** dùng để tiếp tục truy vấn. Không coi paging state là số thứ tự trang hay tùy ý sửa thành offset.

Khi danh sách trải qua nhiều bucket, ứng dụng cần hợp đồng cursor chứa đủ ngữ cảnh bucket/thứ tự và trạng thái đọc; không thể cộng các offset SQL rồi mong thứ tự toàn cụm ổn định. Nếu dữ liệu liên tục được thêm, cần xác định chính sách snapshot/thời điểm bắt đầu đọc, xử lý trùng/thiếu giữa các lần phân trang theo yêu cầu sản phẩm.

Hướng `DESCENDING` giúp lấy bản ghi mới nhất trong một partition mà không phải quét và đảo một danh sách lớn ở ứng dụng; đó là lợi ích trực tiếp của thiết kế clustering theo truy vấn.

## 9. Cập nhật entity: khóa là địa chỉ row

Trong Cassandra, primary key không đơn thuần là ID chỉ để tìm row; **nó xác định vị trí logic của row**. Hai key khác nhau là hai row khác nhau.

Giả sử đã lưu một đơn với khóa:

~~~text
customer_id = A
month_bucket = 2026-11
created_at = 2026-11-20T10:00:00Z
order_id = O
~~~

Sau đó sửa `createdAt` thành một ngày khác rồi gọi `save()`:

~~~java
OrderByCustomerMonth row = repository.findById(oldKey)
    .orElseThrow();

OrderByCustomerMonthKey newKey = new OrderByCustomerMonthKey(
    oldKey.getCustomerId(),
    oldKey.getMonthBucket(),
    correctedTimestamp,
    oldKey.getOrderId()
);

row.setKey(newKey);
repository.save(row);
~~~

Cassandra có thể tạo/ghi một row tại **khóa mới**. Row cũ **không tự bị xóa** vì Spring Data Cassandra không có persistence context/dirty checking và cơ chế di chuyển primary key như ta có thể tưởng tượng từ ORM quan hệ.

Nếu nghiệp vụ thật sự cần đổi khóa, phải có quy trình được thiết kế riêng, ví dụ:

1. Xác định khóa cũ và khóa mới; xem liệu trường hợp đổi khóa có thực sự cần thiết không.
2. Ghi hoặc xác nhận bản ghi ở khóa mới theo đúng quy tắc idempotency.
3. Xóa/đánh dấu hết hiệu lực row cũ có kiểm soát; tính đến tình huống thao tác trước thành công nhưng thao tác sau lỗi.
4. Đồng bộ các bảng đọc khác đang chứa đơn hàng và đối soát dữ liệu bị bỏ sót.
5. Theo dõi tombstone và chi phí compaction do xóa trong Cassandra.

Không giả định hai lệnh `save`/`delete` trên hai partition sẽ có giao dịch ACID đa bảng với rollback như JPA. Nếu cần bất biến nghiệp vụ mạnh, xem xét mô hình ghi phù hợp, LWT theo phạm vi được hỗ trợ và quy trình phục hồi thất bại từng phần.

Với cách làm thực tế, `created_at` nên bất biến sau lúc tạo đơn; `status` và `total_amount` là thuộc tính thay đổi, nên nằm ở cột dữ liệu thường. Nếu phải sắp xếp lại dữ liệu theo một trạng thái dễ đổi, cân nhắc bảng read model khác và quy trình di chuyển khóa có chủ đích.

## 10. Đối chiếu với JPA và tránh nhầm lẫn giữa annotation

| Vấn đề | Spring Data JPA/RDBMS | Spring Data Cassandra |
| --- | --- | --- |
| Khai báo key | `@Id`, `@EmbeddedId`, `@IdClass` | `@PrimaryKey`, `@PrimaryKeyClass`, `@PrimaryKeyColumn` |
| Nhiều thành phần khóa | Composite PK để định danh row | Composite PK còn xác định partition và clustering |
| Thứ tự truy vấn | SQL `ORDER BY`, index và execution plan | Thứ tự clustering trong từng partition, CQL có giới hạn truy cập |
| Quan hệ | Foreign key, `JOIN` và các quan hệ JPA | Không có foreign key/JOIN quan hệ kiểu JPA; thường denormalize |
| Cập nhật entity | Entity managed có thể được flush/dirty check | Gọi `save`/CQL tường minh, không có JPA persistence context |
| Đổi primary key | Phụ thuộc ORM/schema/transaction | Tạo địa chỉ row khác; phải xử lý row cũ và read models |
| Bảo đảm nhất quán | Giao dịch RDBMS tùy isolation | Consistency level cho replica, LWT khi cần; không thay thế ứng dụng đồng bộ nhiều bảng |

Một class Java được gọi là “entity” ở cả hai công nghệ không có nghĩa vòng đời và cơ chế quản lý trạng thái giống nhau. Đặc biệt, `@PrimaryKeyColumn(ordering = DESCENDING)` không tương đương “mọi `SELECT` trên bảng đều tự động `ORDER BY` toàn bộ dữ liệu”.

## 11. Các lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Truy vấn lịch sử theo khách bị từ chối khi chỉ có `customer_id` | Partition key gồm cả `month_bucket` | Truyền đầy đủ partition key hoặc thiết kế bảng khác cho đường truy vấn |
| Danh sách không có thứ tự mong đợi | Đảo `ordinal` clustering hoặc schema CQL không khớp `ordering` | Xem `DESCRIBE TABLE`, so sánh CQL và annotation; migration nếu cần |
| Hai đơn cùng timestamp ghi đè nhau | Clustering key thiếu thành phần định danh ổn định | Thêm `order_id`/key phù hợp ngay trong thiết kế bảng mới |
| `repository.findById(orderId)` không phù hợp | ID của entity là khóa ghép | Dùng object `OrderByCustomerMonthKey` hoặc bảng `orders_by_id` |
| Thay `ordering` trong Java nhưng kết quả không đổi | CQL schema đang tồn tại giữ nguyên clustering order | Đối chiếu schema, thực hiện thay đổi bảng/migration có kế hoạch |
| Đọc `WHERE status = ?` chậm hoặc thất bại | `status` không phải khóa truy cập của bảng | Thiết kế read model theo trạng thái hoặc index phù hợp workload |
| Có hai row khi sửa `created_at` | Primary key đã đổi; `save` ghi theo địa chỉ mới | Giữ khóa ổn định; nếu phải đổi, di chuyển và dọn row cũ |
| Tăng page size nhưng API vẫn chậm | Query chạm partition quá lớn, hotspot hoặc nhiều bucket | Đo số row/partition, latency, payload và thiết kế bucket |
| `ALLOW FILTERING` chạy thử được nhưng production timeout | Phải quét/lọc dữ liệu lớn, chi phí tăng theo dữ liệu | Bỏ đường quét; chuyển sang bảng phục vụ access pattern |
| Mã map được nhưng thứ tự clustering không đúng CQL | Metadata mapping không đồng nhất với schema thật | Kiểm tra `system_schema.columns` và CQL tạo bảng |

## 12. Bài thực hành: thiết kế khóa từ yêu cầu đọc

Một dịch vụ thông báo cần đáp ứng ba tình huống:

1. Hiển thị **30 thông báo mới nhất** của mỗi người dùng trong một ngày.
2. Xem chính xác một thông báo theo `notification_id`.
3. Đánh dấu một thông báo đã đọc mà không làm thay đổi thứ tự của danh sách.

### Bước 1. Xác định bảng theo danh sách

Đề xuất:

~~~sql
CREATE TABLE notifications_by_user_day (
    user_id uuid,
    day_bucket date,
    created_at timestamp,
    notification_id uuid,
    title text,
    is_read boolean,
    PRIMARY KEY ((user_id, day_bucket), created_at, notification_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC,
    notification_id ASC
);
~~~

Trong Spring Data Cassandra:

~~~java
@PrimaryKeyClass
public class NotificationByUserDayKey implements Serializable {

    @PrimaryKeyColumn(
        name = "user_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID userId;

    @PrimaryKeyColumn(
        name = "day_bucket",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private LocalDate dayBucket;

    @PrimaryKeyColumn(
        name = "created_at",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "notification_id",
        ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING)
    private UUID notificationId;

    // Constructor, getter, setter, equals() và hashCode()
    // dựa trên cả bốn trường khóa...
}
~~~

Đoạn Java lược bỏ boilerplate, cần import các kiểu Java/Spring tương ứng. `LocalDate` phù hợp với kiểu CQL `date`. Đảm bảo `day_bucket` tính từ `created_at` theo quy tắc múi giờ nhất quán.

### Bước 2. Tách tra cứu theo ID nếu cần

Truy vấn trực tiếp bằng `notification_id` không được phục vụ hiệu quả chỉ từ bảng `notifications_by_user_day`. Một bảng `notifications_by_id` có `notification_id` làm partition key có thể đáp ứng truy vấn chi tiết. Hệ thống phải có chiến lược đồng bộ khi `is_read` thay đổi; không có foreign key/cascade tự động giữa hai bảng.

### Bước 3. Kiểm soát cập nhật và thứ tự

`is_read` là cột dữ liệu thường; thay đổi nó không thay đổi clustering order. `created_at` và `notification_id` nên được giữ ổn định. Khi hiển thị nhiều ngày, API chọn day buckets cần đọc và điều phối thứ tự/next cursor.

### Bước 4. Xác minh trong CQL

~~~sql
SELECT notification_id, title, is_read, created_at
FROM notifications_by_user_day
WHERE user_id = ?
  AND day_bucket = ?
LIMIT 30;
~~~

Đây là query hợp với partition key ghép và nhận thứ tự theo clustering. Thử thêm nhiều thông báo có `created_at` giống nhau nhưng `notification_id` khác nhau để chắc chắn chúng vẫn là các dòng độc lập.

### Bước 5. Tự kiểm tra

**Câu 1.** Vì sao `day_bucket` nên đặt `PARTITIONED` thay vì `CLUSTERED` nếu muốn tránh partition theo user tăng vô hạn?

*Gợi ý:* Khi ở partition key, mỗi ngày của một user thuộc partition khác nhau; chỉ là clustering column thì mọi ngày vẫn có thể nằm trong một partition user.

**Câu 2.** Nếu đổi `notification_id` từ `CLUSTERED ordinal=3` thành `PARTITIONED ordinal=3` trong Java, schema CQL hiện tại có tự chuyển sang dạng phân vùng mới không?

*Gợi ý:* Không. Phải sửa thiết kế schema và di chuyển dữ liệu theo quy trình; annotation không tự đổi bảng hiện có.

**Câu 3.** `Ordering.DESCENDING` trên `created_at` bảo đảm sắp xếp gì?

*Gợi ý:* Sắp xếp các dòng **trong cùng partition**, không sắp xếp toàn cluster hay xuyên nhiều bucket.

**Câu 4.** Nếu không có `notification_id` làm clustering column, hai thông báo cùng `user_id`, `day_bucket` và `created_at` sẽ thế nào?

*Gợi ý:* Chúng có cùng primary key, nên không được lưu như hai row phân biệt.

**Câu 5.** Vì sao `findById(notificationId)` không phải lựa chọn ID phù hợp cho entity `NotificationByUserDay` với khóa ghép?

*Gợi ý:* Khóa một row bao gồm `user_id`, `day_bucket`, `created_at` và `notification_id`; ID chỉ có UUID không đủ xác định row của bảng này.

**Câu 6.** Khi thay đổi `is_read`, có cần cập nhật `created_at` để row “mới lên đầu” không?

*Gợi ý:* Không nếu yêu cầu sắp xếp theo thời gian tạo. Thay đổi `created_at` còn làm đổi khóa, có thể tạo row mới và để lại row cũ.

## 13. Checklist trước khi dùng @PrimaryKeyColumn trong production

- **Truy vấn rõ ràng:** Liệt kê query quan trọng và điều kiện `WHERE`/`ORDER BY` của từng bảng trước khi chọn khóa.
- **Partition key đầy đủ:** Tất cả thành phần `PARTITIONED` tạo được partition phân bố hợp lý và không phình vô hạn.
- **Thứ tự đúng nhu cầu:** `ordinal` của `CLUSTERED` bám theo thứ tự lọc/range/sort, `ordering` khớp CQL.
- **Khóa xác định duy nhất:** Các clustering column đủ để tránh ghi đè các sự kiện trùng timestamp.
- **Java và CQL khớp:** Tên cột, type, partition/clustering, thứ tự và hướng sort được đối chiếu với schema thật.
- **ID repository chính xác:** Nếu dùng `@PrimaryKeyClass`, repository khai báo đúng type khóa ghép và có `equals/hashCode`.
- **Giữ khóa ổn định:** Tránh đưa các thuộc tính nghiệp vụ thay đổi thường xuyên vào primary key.
- **Phân trang phù hợp:** Không giả định có OFFSET/global sort, kiểm soát paging state và nhiều bucket.
- **Theo dõi hiệu năng:** Kiểm tra partition size, hotspot, tombstone, timeout, consistency và tải thực tế.
- **Thay đổi schema có kế hoạch:** Không sửa annotation rồi mong các partition cũ tự di chuyển; dùng migration, backfill và đối soát khi cần.

## Kết luận

`@PrimaryKeyColumn` là annotation trung tâm khi ánh xạ **primary key ghép** của Cassandra trong Spring Data Cassandra. `type` xác định cột thuộc **partition key** hay **clustering key**, `ordinal` quy định vị trí thành phần khóa, còn `ordering` mô tả hướng sắp xếp của clustering column. Ba thuộc tính phải khớp với `PRIMARY KEY` và `CLUSTERING ORDER BY` trong CQL.

Trong một hệ thống phân tán, thiết kế khóa không tách rời đường truy vấn. Partition key quyết định nơi các dòng được nhóm và định tuyến; clustering columns cho phép đọc có thứ tự trong partition; repository và `CassandraTemplate` chỉ cung cấp lớp ánh xạ/thực thi trên cấu trúc đó. Hãy bắt đầu từ truy vấn cần phục vụ, kiểm soát kích thước partition, giữ các thành phần khóa ổn định, rồi xác minh schema thực tế trước khi đưa ứng dụng vào vận hành.

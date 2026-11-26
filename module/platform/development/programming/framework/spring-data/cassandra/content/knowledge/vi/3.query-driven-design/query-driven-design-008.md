# Truy vấn không phù hợp và thời điểm cần bảng truy cập khác

Trong **Spring Data Cassandra**, ứng dụng có thể truy cập Apache Cassandra bằng repository, `CassandraTemplate` hoặc CQL. Tuy nhiên, API Java không thay đổi cách Cassandra tổ chức dữ liệu: **partition key** quyết định nơi dữ liệu được lưu, **clustering columns** quyết định thứ tự dữ liệu trong partition. Một câu truy vấn hợp lý với cơ sở dữ liệu quan hệ có thể không thực thi được, hoặc thực thi rất tốn kém, trên Cassandra.

Bài học thuộc chương **Thiết kế theo truy vấn**. Trọng tâm là nhận diện truy vấn không tương thích với bảng hiện có, quyết định khi nào cần một **bảng truy cập khác** (access table/read model), và hiểu chi phí của việc lưu cùng một thực thể dưới nhiều cách tổ chức. Các quyết định này tác động trực tiếp tới tính nhất quán, paging và hiệu năng của ứng dụng phân tán.

Sau bài học, bạn có thể:

1. Phân biệt truy vấn bị Cassandra từ chối với truy vấn hợp lệ nhưng có chi phí quá lớn.
2. Nhận ra các dấu hiệu thiếu partition key, lọc trên cột không thuộc khóa, sắp xếp sai clustering order hoặc quét quá nhiều partition.
3. Thiết kế bảng bổ sung từ yêu cầu API cụ thể, cùng phương án cập nhật và phân trang.
4. So sánh bảng truy cập riêng với chỉ mục, lọc có giới hạn ở ứng dụng và hệ thống tìm kiếm/phân tích.

## 1. Tại sao một bảng không phục vụ tốt mọi truy vấn?

Trong Cassandra, câu hỏi cần trả lời thường được xác định **trước khi** định nghĩa bảng. Cấu trúc `PRIMARY KEY` có hai vai trò:

- **Partition key** xác định partition và nhóm replica lưu dữ liệu. Với khóa phân vùng ghép, các thành phần nằm trong cặp ngoặc kép `((...))` phải được xét như một khóa duy nhất.
- **Clustering columns** xác định cách các hàng được sắp xếp trong cùng partition. Các điều kiện lọc và `ORDER BY` được hỗ trợ phụ thuộc cấu trúc khóa và quy tắc của CQL.

Ví dụ:

~~~sql
CREATE TABLE orders_by_customer (
    customer_id uuid,
    bucket_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, bucket_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Bảng có hai thành phần partition key là `customer_id` và `bucket_month`. Trong một partition, dữ liệu được tổ chức theo `created_at` giảm dần, sau đó là `order_id`. `status` và `total_amount` chỉ là cột dữ liệu thường; chúng **không tạo đường truy cập** tương đương index B-tree trong cơ sở dữ liệu quan hệ.

Truy vấn được thiết kế cho bảng:

~~~sql
-- 20 đơn hàng mới nhất của một khách trong tháng 2026-11.
SELECT customer_id, bucket_month, created_at, order_id, status, total_amount
FROM orders_by_customer
WHERE customer_id = 818f7146-53cf-4a38-b0ad-0c99a71c8dd2
  AND bucket_month = '2026-11'
LIMIT 20;
~~~

Cassandra xác định partition từ đúng khóa `(customer_id, bucket_month)`, rồi lấy các hàng đầu tiên theo clustering order. Kết quả giới hạn ở **một partition** đã biết, nên đường đọc tương đối dễ dự đoán.

Để lấy hai tháng, ứng dụng thường thực hiện các truy vấn trên **hai partition riêng**, theo thứ tự tháng, rồi hợp nhất kết quả theo thời gian. Paging state của partition tháng này không tự động trở thành paging state cho partition tháng khác.

### 1.1. Một số điều kiện cần nhớ

| Yêu cầu đọc | Phụ thuộc vào điều gì? | Hệ quả thiết kế |
|---|---|---|
| Tìm chính xác theo mã | Partition key của bảng chứa mã đó | Cần bảng tra cứu theo mã nếu mã không nằm trong khóa đường đọc hiện có |
| Lấy lịch sử theo một chủ thể | Partition key là chủ thể, có thể kèm time bucket | Kiểm soát kích thước partition và giới hạn lịch sử |
| Lấy bản ghi mới nhất | Clustering order theo thời gian | Sắp xếp khi ghi, thay vì sort toàn bộ khi đọc |
| Lọc theo trạng thái của một chủ thể | Trạng thái cần nằm trong đường truy cập, hoặc được hỗ trợ bởi chỉ mục phù hợp | Có thể cần bảng có `status` trong partition key |
| Xếp hạng theo tiền hoặc điểm | Clustering order theo thuộc tính xếp hạng trong partition phù hợp | Một bảng tối ưu cho thời gian không tự tối ưu cho xếp hạng |
| Tìm kiếm tùy ý, nhiều thuộc tính | Không phải thế mạnh mặc định của một bảng Cassandra | Cân nhắc chỉ mục phù hợp hoặc hệ thống tìm kiếm/OLAP |

Lưu ý: các quy tắc CQL có ngoại lệ và khả năng bổ sung khi có chỉ mục. Bảng trên mô tả **đường truy cập chuẩn dựa vào primary key**, là điểm khởi đầu để thiết kế và đánh giá chi phí.

## 2. Khi nào truy vấn hiện tại không phù hợp?

Giả sử sản phẩm ban đầu chỉ cần API:

~~~text
GET /customers/{customerId}/orders?month=2026-11&limit=20
~~~

Bảng `orders_by_customer` đáp ứng tốt. Sau đó, sản phẩm bổ sung:

~~~text
GET /customers/{customerId}/orders?month=2026-11&status=PAID&limit=20
~~~

Một người quen SQL quan hệ có thể thử:

~~~sql
-- Không được bảng hiện tại hỗ trợ theo đường primary key.
SELECT *
FROM orders_by_customer
WHERE customer_id = ?
  AND bucket_month = ?
  AND status = 'PAID'
LIMIT 20;
~~~

`status` không phải thành phần của primary key và chưa có index hỗ trợ. Cassandra thường từ chối vì truy vấn phải lọc dữ liệu ngoài đường truy cập đã định nghĩa. Thêm `LIMIT 20` **không có nghĩa chỉ đọc 20 hàng**: để tìm đủ 20 hàng đạt điều kiện, hệ thống có thể phải xét nhiều hàng khác.

Một phương án dễ nghĩ tới là:

~~~sql
-- Cú pháp có thể cho phép thực thi trong một số cấu hình,
-- nhưng không bảo đảm chi phí đọc phù hợp với production.
SELECT *
FROM orders_by_customer
WHERE customer_id = ?
  AND bucket_month = ?
  AND status = 'PAID'
ALLOW FILTERING;
~~~

`ALLOW FILTERING` cho phép Cassandra cân nhắc một số truy vấn lọc ngoài đường primary-key. Nó **không tạo index**, không tự giới hạn số hàng phải duyệt và có thể cho độ trễ tăng rất mạnh khi dữ liệu lớn. Không dùng nó như cách mặc định để sửa truy vấn không tương thích.

### 2.1. Những truy vấn thường phát tín hiệu cảnh báo

| Dạng truy vấn | Tín hiệu | Câu hỏi cần đặt ra |
|---|---|---|
| `WHERE status = 'PAID'` nhưng khóa phân vùng theo khách hàng | Thiếu partition key đúng đường đọc | API muốn tìm theo trạng thái trên phạm vi nào? |
| `WHERE customer_id = ?` khi partition key là `(customer_id, bucket_month)` | Thiếu một thành phần partition key ghép | Có thể yêu cầu caller chỉ rõ tháng hoặc chọn bảng khác không? |
| `ORDER BY total_amount DESC` trên bảng clustering theo thời gian | Muốn một thứ tự khác | Có cần bảng xếp hạng riêng không? |
| `WHERE status IN (...)` rồi quét nhiều tháng | Fan-out nhiều partition | Bao nhiêu partition và bao nhiêu hàng có thể phải đọc? |
| `COUNT(*)` trên phạm vi rất lớn | Phải xét nhiều hàng; không có counter tổng quát miễn phí | Có cần bảng tổng hợp/counter được duy trì riêng không? |
| `SELECT *` trên bảng tăng trưởng liên tục | Payload và số hàng khó kiểm soát | Có thể giảm cột, giới hạn theo khóa và phân trang không? |
| Một `customer_id` có hàng triệu sự kiện trong cùng partition | Hot/large partition dù CQL hợp lệ | Có cần bucket theo thời gian hoặc shard không? |

**Truy vấn hợp lệ không đồng nghĩa hiệu quả.** Cassandra có thể nhận câu lệnh nhưng vẫn gặp độ trễ cao do partition quá lớn, tombstone, paging nhiều lượt, hot partition, điều kiện lọc kém chọn lọc hoặc số truy vấn fan-out quá lớn.

## 3. Đánh giá trước khi tạo bảng mới

Không phải mọi điều kiện đọc mới đều phải sinh thêm một bảng. Hãy ghi rõ **hợp đồng truy vấn (query contract)**:

- **Ai gọi?** API người dùng, báo cáo ban đêm, tác vụ quản trị hay trang điều hành?
- **Bộ lọc bắt buộc?** Khách hàng, mã đơn, trạng thái, thời gian, khu vực?
- **Thứ tự nào?** Mới nhất, giá cao nhất, hay thứ tự không quan trọng?
- **Số hàng cần đọc?** Một, 20, 100 hay toàn bộ lịch sử?
- **Tần suất và SLA?** Bao nhiêu request/giây, p95/p99 tối đa bao nhiêu?
- **Tính mới của dữ liệu?** Có chấp nhận vài giây đồng bộ chậm giữa các bảng không?
- **Độ lớn và phân bố?** Bao nhiêu bản ghi mỗi partition, có khóa nào quá nóng?
- **Chi phí ghi?** Mỗi trạng thái thay đổi bao nhiêu lần, có chấp nhận cập nhật nhiều bảng không?

Ví dụ hợp đồng truy vấn mới:

> Lấy 20 đơn hàng trạng thái `PAID` gần nhất của **một** khách hàng trong **một** tháng; tải cao trong giờ cao điểm, kết quả theo thời gian giảm dần; có thể chấp nhận độ trễ đồng bộ ngắn đã được sản phẩm xác định.

Hợp đồng này đủ cụ thể để thiết kế bảng mới, chọn partition key, clustering order, paging và quy trình cập nhật.

### 3.1. Cây quyết định

~~~mermaid
flowchart TD
    A[Truy vấn mới] --> B{Khớp partition key và clustering order?}
    B -->|Có| C[Đo kích thước partition, paging và p95/p99]
    C --> D{Đạt SLA khi dữ liệu tăng?}
    D -->|Có| E[Tiếp tục dùng bảng hiện tại]
    D -->|Không| F[Đổi bucket, key hoặc đường truy cập]
    B -->|Không| G{Truy vấn thường xuyên, có SLA chặt?}
    G -->|Có| H[Thiết kế access table riêng]
    G -->|Không| I[Đánh giá index, xử lý giới hạn hoặc tác vụ offline]
    I --> J{Cần tìm kiếm/aggregate tùy ý ở quy mô lớn?}
    J -->|Có| K[Cân nhắc search engine hoặc OLAP]
    J -->|Không| L[Benchmark lựa chọn đã khoanh vùng]
~~~

**Bảng truy cập riêng thường là lựa chọn tốt** khi truy vấn xuất hiện thường xuyên, đã có pattern ổn định, cần độ trễ dễ dự đoán và không thể thỏa mãn bằng primary key của bảng đang dùng. **Index** có thể hợp lý nếu hệ Cassandra đang vận hành hỗ trợ loại chỉ mục phù hợp, dữ liệu và mức chọn lọc đáp ứng yêu cầu; phải đo thực tế thay vì suy luận chỉ từ cú pháp. **Xử lý offline hoặc hệ phân tích** hợp lý hơn với tìm kiếm tùy ý, phép nối phức tạp và báo cáo quét dữ liệu quy mô lớn.

## 4. Thiết kế bảng đọc mới cho truy vấn theo trạng thái

Để phục vụ truy vấn `(customer_id, status, bucket_month) → mới nhất`, tạo projection:

~~~sql
CREATE TABLE orders_by_customer_status (
    customer_id uuid,
    status text,
    bucket_month text,
    created_at timestamp,
    order_id uuid,
    total_amount decimal,
    PRIMARY KEY (
        (customer_id, status, bucket_month),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Các cột `customer_id`, `status`, `bucket_month` cùng là **partition key ghép**. `created_at` và `order_id` là clustering columns. Có thể lưu thêm các thuộc tính mà giao diện cần để tránh thực hiện một lần đọc bảng khác cho từng đơn.

Truy vấn mới đi thẳng vào một partition:

~~~sql
SELECT customer_id, status, bucket_month,
       created_at, order_id, total_amount
FROM orders_by_customer_status
WHERE customer_id = ?
  AND status = 'PAID'
  AND bucket_month = '2026-11'
LIMIT 20;
~~~

Lợi ích là xác định đúng nhóm bản ghi và trả về thứ tự mong muốn ngay từ dữ liệu được ghi. Chi phí là **các trường của một đơn hàng được sao chép** sang một bảng khác và ứng dụng phải giữ projection nhất quán với dữ liệu nguồn theo chính sách của hệ thống.

### 4.1. Tại sao cần `bucket_month`?

Nếu bảng dùng partition key `(customer_id, status)`, một khách có thể tích lũy toàn bộ lịch sử đơn của một trạng thái trong một partition. Một số khách có thể phát sinh lưu lượng hoặc số hàng vượt xa khách bình thường.

Bucket theo tháng giúp giới hạn phạm vi dữ liệu được đọc và tránh partition tăng vô hạn. Nhưng bucket **không miễn phí**: muốn xem nhiều tháng, ứng dụng phải truy vấn nhiều partition và ghép kết quả. Chọn ngày, tuần, tháng hoặc kết hợp shard dựa vào phân bố thực tế, tốc độ tăng dữ liệu và truy vấn sản phẩm.

Không tạo partition key chỉ gồm `status` với vài giá trị như `NEW`, `PAID`, `CANCELLED`: các trạng thái phổ biến có thể tạo partition rất lớn và nóng. Nếu bài toán là xem đơn mới trên toàn hệ thống theo trạng thái/ngày, phải thiết kế riêng theo ngày và có thể chia shard:

~~~sql
-- Chỉ là ví dụ một access pattern khác, không phải bảng
-- dùng để truy vấn lịch sử theo khách hàng.
CREATE TABLE orders_by_status_day_shard (
    status text,
    day_bucket date,
    shard smallint,
    created_at timestamp,
    order_id uuid,
    customer_id uuid,
    PRIMARY KEY ((status, day_bucket, shard), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Ứng dụng cần quy tắc xác định shard ổn định khi ghi và cách fan-out/merge khi đọc. Nếu muốn xem toàn bộ shard, mỗi shard là một partition riêng và phải gộp các kết quả theo thời gian. Số shard cần đo bằng traffic và phân phối dữ liệu; tăng shard làm giảm tập trung tải ghi nhưng tăng số truy vấn đọc.

### 4.2. Mỗi truy vấn bổ sung có thể cần đường đọc khác

| Nhu cầu sản phẩm | Bảng truy cập có thể thiết kế | Khóa gợi ý | Rủi ro cần đo |
|---|---|---|---|
| 20 đơn gần nhất của khách trong tháng | `orders_by_customer` | `((customer_id, month), created_at, order_id)` | Lượng dữ liệu/tháng của khách lớn |
| 20 đơn `PAID` gần nhất của khách trong tháng | `orders_by_customer_status` | `((customer_id, status, month), created_at, order_id)` | Cập nhật khi trạng thái đổi |
| Tra đơn theo ID | `orders_by_id` | `(order_id)` | Dữ liệu sao chép và nhất quán |
| Đơn mới của toàn hệ thống theo trạng thái/ngày | `orders_by_status_day_shard` | `((status, day, shard), created_at, order_id)` | Hot partition, fan-out nhiều shard |
| Xếp hạng đơn theo số tiền | Bảng xếp hạng có partition phù hợp hoặc hệ phân tích | Clustering theo tiền, có khóa phụ phá hòa | Cập nhật xếp hạng, tính mới và chi phí ghi |

Đây là **các lựa chọn theo nhu cầu thực** chứ không phải yêu cầu tạo cả năm bảng cho mọi hệ thống.

## 5. Dùng Spring Data Cassandra với bảng truy cập mới

Spring Data Cassandra không tự sinh đường đọc khi developer viết một repository method. Cấu trúc bảng CQL vẫn quyết định truy vấn nào được hỗ trợ. Một cách ánh xạ composite key minh họa:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class CustomerStatusOrderKey implements Serializable {
    @PrimaryKeyColumn(name = "customer_id", ordinal = 0,
            type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(name = "status", ordinal = 1,
            type = PrimaryKeyType.PARTITIONED)
    private String status;

    @PrimaryKeyColumn(name = "bucket_month", ordinal = 2,
            type = PrimaryKeyType.PARTITIONED)
    private String bucketMonth;

    @PrimaryKeyColumn(name = "created_at", ordinal = 3,
            type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 4,
            type = PrimaryKeyType.CLUSTERED)
    private UUID orderId;

    // Bổ sung no-args constructor, getters/setters, equals và hashCode
    // dựa trên toàn bộ các thành phần khóa.
}
~~~

Trong một ứng dụng thực tế, cần hoàn thiện constructor, accessor và so sánh giá trị cho khóa trước khi dùng. `ordinal` mô tả thứ tự các cột trong khóa. Với bảng đã định nghĩa, entity đọc có thể được khai báo:

~~~java
import java.math.BigDecimal;
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("orders_by_customer_status")
public class OrderByCustomerStatus {
    @PrimaryKey
    private CustomerStatusOrderKey id;

    @Column("total_amount")
    private BigDecimal totalAmount;

    // Bổ sung constructor, getters và setters.
}
~~~

Với repository, khai báo rõ CQL cho đường đọc theo partition key:

~~~java
import java.util.List;
import java.util.UUID;
import org.springframework.data.cassandra.repository.CassandraRepository;
import org.springframework.data.cassandra.repository.Query;

public interface OrdersByCustomerStatusRepository
        extends CassandraRepository<OrderByCustomerStatus, CustomerStatusOrderKey> {

    @Query("SELECT * FROM orders_by_customer_status " +
           "WHERE customer_id = ?0 AND status = ?1 " +
           "AND bucket_month = ?2 LIMIT 20")
    List<OrderByCustomerStatus> findRecentInMonth(
            UUID customerId, String status, String bucketMonth);
}
~~~

`LIMIT 20` là chính sách của ví dụ, không nên gắn cố định nếu API cho phép chọn page size có kiểm soát. Đối với service cần truy vấn động, `CassandraTemplate` hỗ trợ cùng đường đọc:

~~~java
import org.springframework.data.cassandra.core.CassandraTemplate;
import org.springframework.data.cassandra.core.query.Criteria;
import org.springframework.data.cassandra.core.query.Query;

// Ví dụ trong service đã inject CassandraTemplate template:
Query query = Query.query(Criteria.where("customer_id").is(customerId))
        .and(Criteria.where("status").is("PAID"))
        .and(Criteria.where("bucket_month").is("2026-11"))
        .limit(20);

List<OrderByCustomerStatus> orders =
        template.select(query, OrderByCustomerStatus.class);
~~~

Dù dùng `@Query`, `Query/Criteria`, `CassandraTemplate` hay `CqlSession` trực tiếp, truy vấn vẫn cần cung cấp **đầy đủ ba thành phần partition key**. Đổi sang `ReactiveCassandraRepository` hoặc `ReactiveCassandraTemplate` chỉ đổi mô hình xử lý bất đồng bộ/phản ứng; **không làm truy vấn sai key trở nên tối ưu**.

### 5.1. Phân trang trên đường đọc đã định nghĩa

Với một partition có thể trả nhiều hàng, sử dụng cơ chế **paging state** của Cassandra. Các API phân trang của Spring Data Cassandra có thể trả `Slice<T>`; driver cũng hỗ trợ paging ở mức `Statement`. Paging state đại diện cho trạng thái của **một truy vấn cụ thể** và chỉ nên dùng lại với truy vấn và tham số tương thích.

Không áp dụng cơ học mô hình `OFFSET 100000` của SQL quan hệ lên Cassandra. Khi truy vấn nhiều tháng hoặc nhiều shard, ứng dụng phải tự quản lý kết quả, paging state **của từng partition** và cách nối hoặc trộn dữ liệu, thay vì giả định có một cursor toàn cục miễn phí.

## 6. Giữ dữ liệu nhất quán khi có nhiều bảng truy cập

Cassandra khuyến khích thiết kế dựa trên truy vấn nên **denormalization** và ghi cùng một dữ liệu vào nhiều bảng thường là lựa chọn có chủ đích. Ví dụ, một đơn mới được lưu ở `orders_by_id`, `orders_by_customer` và `orders_by_customer_status`.

~~~text
Nhận lệnh đặt hàng hoặc đổi trạng thái
        |
        v
Xác nhận thao tác nghiệp vụ và phiên bản dữ liệu
        |
        +----> orders_by_id
        +----> orders_by_customer
        +----> orders_by_customer_status
        |
        v
Theo dõi lỗi, retry an toàn và đối soát các projection
~~~

Các mũi tên ở đây chỉ **logic đồng bộ dữ liệu**, không tuyên bố ba lần ghi là một giao dịch ACID. Ghi qua nhiều partition/bảng không có ngữ nghĩa transaction và isolation giống một cơ sở dữ liệu quan hệ. Logged batch có thể giúp tổ chức độ bền của nhóm mutation trong điều kiện nhất định, nhưng **không biến cập nhật nhiều bảng thành giao dịch cô lập với mọi reader**.

### 6.1. Trạng thái thay đổi tạo vấn đề gì?

Giả sử đơn `O-123` đổi `NEW → PAID`. Partition key bảng `orders_by_customer_status` chứa `status`, vì vậy cần:

1. Xác định bản ghi cũ ở partition `(customer_id, 'NEW', month)`.
2. Xóa hàng ở vị trí cũ theo toàn bộ primary key.
3. Ghi hàng tại partition `(customer_id, 'PAID', month)`.
4. Cập nhật dữ liệu nguồn, đảm bảo event hoặc retry không ghi đè trạng thái mới hơn.
5. Có cơ chế phát hiện và khôi phục khi một bước cập nhật projection thất bại.

Trong lúc cập nhật, reader có thể tạm thấy bản ghi ở hai vị trí, không thấy ở vị trí cần đọc hoặc thấy trạng thái cũ, tùy thứ tự ghi và consistency level. Phải xác định **mức nhất quán mà sản phẩm chấp nhận**, rồi chọn cách cập nhật phù hợp.

Nếu nhu cầu chỉ là “đơn đã thanh toán”, một bảng chuyên `paid_orders_by_customer` được ghi khi đơn **lần đầu** chuyển sang `PAID` có thể giảm việc di chuyển qua các trạng thái, nhưng vẫn cần xử lý hoàn tiền, hủy, sửa và xóa theo định nghĩa nghiệp vụ.

### 6.2. Những nguyên tắc vận hành

- **Định nghĩa nguồn dữ liệu chuẩn**: dữ liệu nào được xem là sự thật khi hai projection khác nhau?
- **Idempotency**: cùng một event bị phát lại không tạo bản sao sai hoặc kéo lùi trạng thái. Có thể dùng event ID/version và logic cập nhật thích hợp; không đánh đồng retry với thao tác luôn an toàn.
- **Thứ tự sự kiện**: thao tác đến muộn phải được xử lý theo phiên bản và quy tắc nghiệp vụ, đặc biệt khi có nhiều writer.
- **Xóa, TTL, tombstone**: projection cần chính sách vòng đời phù hợp. Thay đổi khóa thường là xóa hàng cũ và thêm hàng mới; quá nhiều xóa có thể làm tăng tombstone và chi phí đọc.
- **Consistency level**: `LOCAL_ONE`, `LOCAL_QUORUM` hay cấu hình khác tác động đến phản hồi của từng thao tác; không mặc nhiên bảo đảm đồng bộ nhiều access table.
- **Đối soát**: có job/đường kiểm tra phát hiện thiếu, thừa hoặc sai projection; có thể sửa lại từ nguồn dữ liệu chuẩn.

Hai cách triển khai phổ biến là **ghi các bảng trong đường xử lý yêu cầu** (đơn giản hơn nhưng khó chịu lỗi từng phần) và **cập nhật projection qua event/outbox hoặc pipeline bất đồng bộ** (tách tải đọc/ghi, nhưng phải chấp nhận và đo độ trễ đồng bộ). Chọn theo cam kết tính nhất quán, khả năng vận hành và đặc tính hệ thống.

## 7. Khi nào dùng index, khi nào dùng bảng riêng?

Không nên đặt quy tắc “mọi truy vấn mới phải có bảng mới”. Cassandra có các khả năng index tùy phiên bản và bản phân phối, gồm secondary index hoặc các dạng **Storage-Attached Index (SAI)** ở môi trường hỗ trợ. Chúng có thể phù hợp với truy vấn lọc có chọn lọc trên tập dữ liệu thích hợp; cần kiểm tra cú pháp, giới hạn và hành vi của **phiên bản Cassandra đang chạy**.

| Phương án | Nên cân nhắc khi | Rủi ro/đánh đổi |
|---|---|---|
| Giữ bảng, lọc **ở ứng dụng** | Đã biết một partition nhỏ và giới hạn chặt số hàng đọc | Dữ liệu lớn lên khiến chi phí khó dự đoán; không lọc sau `LIMIT` rồi tin đó là 20 bản ghi phù hợp |
| Index phù hợp | Pattern lọc được index hỗ trợ, độ chọn lọc và benchmark đạt SLA | Overhead ghi/lưu trữ, giới hạn điều kiện, độ trễ và phân bố dữ liệu |
| **Access table riêng** | Pattern truy vấn ổn định, thường xuyên, cần lọc/sắp xếp theo khóa khác | Ghi khuếch đại, dữ liệu trùng, projection lag, migration |
| Hệ tìm kiếm/analytics | Tra cứu tự do, tìm văn bản, nhiều phép tổng hợp hoặc báo cáo rộng | Hạ tầng bổ sung, vận hành pipeline và tính nhất quán |

`ALLOW FILTERING` không nằm trong danh sách giải pháp thường dùng vì bản thân nó không đảm bảo một đường đọc có chi phí ổn định. Tuy nhiên, với tập dữ liệu **thật sự nhỏ và giới hạn**, truy vấn có lọc có thể được cân nhắc như một quyết định tạm thời đã đo, không phải mặc định cho API tải cao.

### 7.1. Quyết định dựa trên chi phí đọc và ghi

Giả sử mỗi đơn hàng được sao chép sang `N` access table khác nhau. Thêm bảng thường làm tăng:

* **Write amplification:** mỗi thao tác nghiệp vụ kéo theo nhiều mutation.
* **Storage amplification:** các cột cần phục vụ đọc xuất hiện ở nhiều bảng.
* **Độ phức tạp đồng bộ:** cần xử lý cập nhật, xóa, retry, event trễ và backfill.

Đổi lại, đọc theo đúng partition key có thể làm giảm đáng kể số hàng và partition bị truy cập, giúp độ trễ ổn định hơn khi dữ liệu tăng.

Không thể suy ra “thêm hai bảng nghĩa là hệ thống chậm gấp ba”: cần đo kích thước hàng, replication, compression, write path, cache, consistency và tải cụ thể. Nhưng **mỗi bảng bổ sung phải có một truy vấn sản phẩm đủ rõ ràng để biện minh**.

## 8. Thay đổi schema khi ứng dụng đang chạy

Với dữ liệu production đã tồn tại, thêm access table thường cần lộ trình chuyển đổi:

1. **Chốt hợp đồng truy vấn:** xác định partition key, clustering order, phạm vi bucket, giới hạn và consistency kỳ vọng.
2. **Tạo bảng mới:** xem xét tài nguyên lưu trữ, TTL, replication/keyspace và quyền truy cập. Không bật đọc từ bảng mới khi dữ liệu còn thiếu nếu API cần dữ liệu đầy đủ.
3. **Thiết lập luồng cập nhật mới:** bổ sung ghi projection hoặc event pipeline; xử lý duplicate và cập nhật đến trễ.
4. **Backfill dữ liệu cũ:** đi theo nguồn có thể kiểm chứng; chia khối và giới hạn tốc độ để tránh làm quá tải Cassandra. Không dùng `SELECT *` không kiểm soát trên bảng khổng lồ.
5. **Đối soát:** so sánh số lượng và mẫu dữ liệu theo khóa/bucket, kiểm tra trạng thái đổi, lỗi tombstone, độ trễ projection và truy vấn thực.
6. **Chạy shadow read và đo SLA:** thực hiện truy vấn ở bảng mới song song có kiểm soát, so sánh kết quả và p95/p99.
7. **Chuyển tuyến đọc:** triển khai theo nhóm nhỏ, theo dõi lỗi và duy trì phương án quay lại nếu cần.
8. **Dọn đường cũ:** chỉ loại bỏ lối đọc hoặc dữ liệu thừa sau khi xác nhận không còn consumer và đảm bảo chính sách lưu giữ.

Điểm dễ sót là **khoảng trống giữa backfill và dữ liệu mới**. Luồng đồng bộ phải đủ thông tin để bắt kịp các thay đổi xảy ra trong lúc sao chép dữ liệu lịch sử; nếu không, projection sẽ thiếu hoặc bị event cũ ghi đè.

## 9. Kiểm chứng chất lượng và hiệu năng của thiết kế mới

Trước khi coi một bảng truy cập mới là thành công, thử các tình huống đại diện:

| Bài đo | Cần quan sát |
|---|---|
| Một khách ít đơn, nhiều khách ít đơn | Chi phí truy vấn và phân bố partition thông thường |
| Một khách có số lượng đơn vượt trội | Hot partition, thời gian đọc và paging |
| Một trạng thái phổ biến bất thường | Có phân bố lại tải nhờ bucket/shard đủ tốt không |
| Nhiều truy vấn đồng thời | Throughput, in-flight requests, timeout, CPU/GC |
| Đọc qua nhiều tháng/shard | Fan-out, memory merge, số paging state |
| Cập nhật trạng thái liên tục | Write latency, tombstones, lỗi đồng bộ projection |
| Có node chậm/timeout | Retry, idempotency, dữ liệu tạm lệch và khả năng phục hồi |

Theo dõi **p50/p95/p99 latency**, số hàng trả về, số partition bị chạm, số trang đọc, kích thước partition, tombstone scan, timeout, read/write pressure và projection lag. Benchmark phải dựa trên phân phối dữ liệu thực tế, không chỉ một tập thử nhỏ với mọi khóa xuất hiện đều nhau.

**Dấu hiệu phải xem lại thiết kế** gồm: một truy vấn API cần quét bảng, ứng dụng tải toàn bộ rồi lọc; fan-out tăng theo tổng số khách hàng; một partition không còn giới hạn tăng trưởng; hoặc một loại truy vấn phụ khiến write amplification và độ trễ ghi tăng quá mức. Khi đó, giải pháp có thể là **đổi yêu cầu truy vấn**, điều chỉnh bucket, thêm read model hoặc chuyển bài toán sang hệ phù hợp hơn.

## 10. Bài tập thực hành

Hệ thống theo dõi giao hàng đang có bảng:

~~~sql
CREATE TABLE tracking_events_by_package (
    package_id uuid,
    day_bucket date,
    event_time timestamp,
    event_id uuid,
    hub_id uuid,
    event_type text,
    PRIMARY KEY ((package_id, day_bucket), event_time, event_id)
) WITH CLUSTERING ORDER BY (event_time DESC, event_id ASC);
~~~

Hãy đánh giá bốn yêu cầu:

1. Hiển thị 30 sự kiện mới nhất của một kiện hàng trong ngày.
2. Liệt kê tất cả kiện hàng vừa đến một kho `hub_id` trong 10 phút.
3. Đếm tổng sự kiện theo `event_type` trên toàn quốc trong một năm.
4. Hiển thị lịch sử của kiện hàng trong 90 ngày.

**Hướng phân tích:**

- **(1)** Phù hợp với primary key hiện có: truy vấn một `(package_id, day_bucket)`, lấy theo `event_time DESC`, `LIMIT 30`.
- **(2)** Không có đường đọc theo `hub_id`; cân nhắc bảng `events_by_hub_time_bucket` với partition key kết hợp `hub_id` và time bucket đủ nhỏ, clustering theo thời gian. Tính cả trường hợp kho rất đông và nhu cầu shard.
- **(3)** Không phù hợp với truy vấn giao dịch thông thường; cân nhắc pipeline tổng hợp/bảng chỉ số định kỳ hoặc hệ phân tích, thay vì `COUNT(*)` quét toàn bộ.
- **(4)** Dùng nhiều partition ngày đã biết; cần giới hạn số partition và kết quả, quản lý paging state từng ngày, ghép theo thời gian. Nếu API này quá thường xuyên và tốn kém, xem xét bucket khác hoặc read model phù hợp.

Trong cả bốn tình huống, việc sử dụng `ReactiveCassandraRepository` không tự sửa những vấn đề do partition key hoặc đường truy cập sai. **Mô hình dữ liệu quyết định nơi và thứ tự Cassandra đọc; mô hình Spring quyết định cách ứng dụng gọi và xử lý kết quả.**

## 11. Checklist trước khi chấp nhận một truy vấn mới

- [ ] Có hợp đồng truy vấn rõ ràng: filter, order, limit, SLA và phạm vi thời gian.
- [ ] Xác định đầy đủ partition key; không nhầm clustering column với partition key.
- [ ] Xem truy vấn có yêu cầu lọc trên cột thường hoặc sắp xếp ngoài clustering order không.
- [ ] Có giới hạn kích thước partition, fan-out, paging và số thao tác đồng thời.
- [ ] Nếu thêm access table, đã xác định nguồn dữ liệu chuẩn, cách cập nhật/xóa và xử lý event trễ.
- [ ] Nếu dùng index, đã xác minh tính năng theo phiên bản Cassandra và benchmark với phân bố thực.
- [ ] Đã đo p95/p99, timeout, tombstones, độ lệch projection và chi phí đọc/ghi.
- [ ] Kịch bản triển khai có backfill, đối soát, chuyển đọc và phương án quay lại.

## Tài liệu tham khảo

- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).
- [Apache Cassandra — CQL](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/index.html).
- [Spring Data Cassandra — Query Methods](https://docs.spring.io/spring-data/cassandra/reference/cassandra/repositories/query-methods.html).
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).

# Đồng bộ các bản sao dữ liệu ở nhiều bảng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao một thực thể nghiệp vụ thường được lưu ở nhiều bảng Cassandra khác nhau và phân biệt **bản sao phục vụ truy vấn** với **replica của cụm Cassandra**.
- Thiết kế đường ghi khi cùng dữ liệu xuất hiện trong nhiều bảng, xác định bảng nguồn sự thật và mức trễ đồng bộ có thể chấp nhận.
- Phân tích thất bại từng phần, ghi trùng, sự kiện đến sai thứ tự và cập nhật cạnh tranh; áp dụng **idempotency**, **revision** và ghi có điều kiện đúng phạm vi.
- Chọn giữa ghi đồng bộ, CQL batch và cập nhật bất đồng bộ bằng sự kiện; hiểu giới hạn của consistency level, lightweight transaction (LWT) và materialized view.
- Xây dựng cách đối soát, khôi phục, quan sát độ trễ đồng bộ và kiểm chứng dữ liệu khi thay đổi schema.

Bài học thuộc **SPRING_DATA_CASSANDRA**: sử dụng Spring Data Cassandra để truy cập Apache Cassandra qua entity mapping, repository, `CassandraTemplate` và CQL. Vì Cassandra là cơ sở dữ liệu phân tán được thiết kế theo đường truy vấn, việc duy trì nhiều biểu diễn của cùng một dữ liệu là trách nhiệm quan trọng ở tầng ứng dụng.

## 1. Vì sao có nhiều bản sao dữ liệu?

Giả sử ứng dụng bán hàng cần hai màn hình:

1. Xem chi tiết đơn hàng khi biết `order_id`.
2. Xem 20 đơn gần nhất của một khách hàng trong một tháng.

Trong cơ sở dữ liệu quan hệ, một bảng `orders` có thể hỗ trợ nhiều truy vấn thông qua chỉ mục và phép kết hợp bảng. Với Cassandra, một bảng nên được thiết kế cho một số **access pattern đã xác định**, đặc biệt là cách chọn partition key và thứ tự clustering. Hai yêu cầu trên thường dẫn đến hai bảng:

- `orders_by_id`: định vị một đơn bằng `order_id`.
- `orders_by_customer_month`: đọc danh sách theo `(customer_id, month_bucket)` và thứ tự tạo đơn.

Hai bảng chứa các trường như trạng thái và tổng tiền của **cùng một đơn hàng**. Khi trạng thái đơn thay đổi từ `NEW` thành `PAID`, cả hai đường đọc phải được cập nhật theo chính sách nghiệp vụ đã chọn.

### 1.1. Hai khái niệm rất dễ nhầm

| Khái niệm | Ai tạo và duy trì? | Mục đích | Ý nghĩa của consistency |
| --- | --- | --- | --- |
| **Replica của Cassandra** | Cassandra phân bố và sao chép dữ liệu theo replication factor | Chịu lỗi, phân tán lưu trữ, phục vụ đọc/ghi | Consistency level quy định số replica phải phản hồi cho một thao tác |
| **Bản sao logic ở nhiều bảng** | Người thiết kế schema và ứng dụng | Phục vụ các truy vấn khác nhau, thường bằng dữ liệu phi chuẩn hóa | Không tự nhất quán chỉ vì dùng `QUORUM` hay `LOCAL_QUORUM` |

Các cơ chế repair hoặc read repair trong Cassandra hướng đến tính nhất quán giữa replica của dữ liệu lưu trữ. Chúng **không** tự so khớp trường `status` giữa `orders_by_id` và `orders_by_customer_month`.

## 2. Thiết kế ví dụ: hai bảng và một nguồn sự thật

### 2.1. Schema CQL

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    month_bucket text,
    status text,
    amount decimal,
    revision bigint
);

CREATE TABLE orders_by_customer_month (
    customer_id uuid,
    month_bucket text,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    revision bigint,
    PRIMARY KEY ((customer_id, month_bucket), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

`orders_by_id` có partition key là `order_id`. Ở bảng thứ hai, partition key gồm `customer_id` và `month_bucket`; `created_at` cùng `order_id` là clustering columns. `month_bucket` có thể là chuỗi `2026-11` được tính thống nhất từ thời điểm tạo đơn theo UTC; tên và độ rộng bucket cần xác định bằng tải thực tế.

Truy vấn tương ứng:

~~~sql
SELECT order_id, customer_id, status, amount, revision
FROM orders_by_id
WHERE order_id = ?;

SELECT order_id, created_at, status, amount, revision
FROM orders_by_customer_month
WHERE customer_id = ? AND month_bucket = ?
LIMIT 20;
~~~

Thiết kế này giúp đọc đúng partition mà không cần `ALLOW FILTERING`. Nếu một khách có lượng đơn rất lớn trong một tháng, có thể cần bucket nhỏ hơn hoặc chia shard có kiểm soát. Danh sách vượt nhiều bucket phải được ứng dụng điều phối việc đọc và sắp xếp kết quả.

### 2.2. Xác định bất biến trước khi ghi

Trong ví dụ, chọn `orders_by_id` làm **nguồn sự thật (source of truth)** cho trạng thái đơn; `orders_by_customer_month` là **read model** được dựng từ dữ liệu đó.

| Quyết định | Quy ước của ví dụ |
| --- | --- |
| Định danh duy nhất | `order_id` không đổi sau khi tạo |
| Khóa của read model | `customer_id`, `month_bucket`, `created_at`, `order_id` không đổi trong vòng đời đơn |
| Dữ liệu có thể cập nhật | `status`, `amount`, `revision` |
| Nguồn sự thật | `orders_by_id` |
| Chính sách đọc danh sách | Có thể chấp nhận trễ ngắn và hiển thị `revision` để chẩn đoán khi cần |
| Thứ tự thay đổi | Mỗi đơn có `revision` tăng dần; sự kiện mới cần mang giá trị này |

Đây là **quy ước ứng dụng**, không phải tính năng đồng bộ bảng mặc định của Cassandra. Nếu nghiệp vụ bắt buộc hai màn hình phản ánh cùng trạng thái ngay lập tức, cần đánh giá lại hợp đồng nhất quán, đường đọc hoặc nền tảng lưu trữ; tăng consistency level không thể tự tạo giao dịch đa bảng.

## 3. Điều gì xảy ra khi ghi vào hai bảng?

Một cách triển khai ban đầu là gọi hai thao tác ghi liên tiếp:

~~~text
Nhận yêu cầu tạo/sửa đơn
  -> ghi orders_by_id
  -> ghi orders_by_customer_month
  -> trả kết quả
~~~

Thao tác này có thể hoạt động khi mọi thứ ổn định, nhưng hai lệnh ghi không mặc nhiên thuộc một giao dịch có rollback.

| Tình huống | Trạng thái có thể quan sát | Hành động cần thiết |
| --- | --- | --- |
| Cả hai lệnh thành công | Hai đường đọc đã được cập nhật | Ghi nhận kết quả và theo dõi độ trễ |
| Ghi bảng nguồn thành công, ghi read model thất bại | Chi tiết đơn mới, danh sách còn cũ | Có cơ chế retry bền vững và đối soát |
| Lệnh ghi timeout | Không chắc server đã áp dụng mutation hay chưa | Xem kết quả là **không xác định**, retry theo cách idempotent hoặc xác minh trạng thái |
| Client đã ghi xong nhưng mất phản hồi | Client có thể gửi lại cùng yêu cầu | Chống xử lý trùng bằng ID yêu cầu/revision |
| Sự kiện trạng thái cũ đến sau trạng thái mới | Read model có nguy cơ bị lùi trạng thái | So sánh revision trước khi chấp nhận cập nhật |
| Xóa/đổi khóa ở một bảng nhưng quên bảng kia | Dữ liệu cũ còn xuất hiện ở đường đọc khác | Xóa/di chuyển theo kế hoạch và đối soát |

Một retry đơn giản kiểu “ghi lại giá trị cũ sau vài giây” còn có thể **ghi đè dữ liệu mới hơn**. Cassandra giải quyết xung đột của cell dựa trên timestamp ghi, chứ không hiểu `status=PAID` phải mới hơn `status=NEW` theo nghiệp vụ. Vì vậy sự an toàn của retry cần được thiết kế rõ ràng.

## 4. Ba chiến lược đồng bộ thường gặp

### 4.1. Ghi đồng bộ cả hai bảng trong luồng yêu cầu

Ứng dụng thực thi các lệnh ghi trước khi trả kết quả cho người gọi:

~~~mermaid
flowchart TD
    A["API: tạo/cập nhật đơn"] --> B["Ghi orders_by_id"]
    B --> C["Ghi orders_by_customer_month"]
    C --> D["Trả kết quả"]
    B --> E["Lỗi hoặc timeout: ghi nhận và xử lý bất định"]
    C --> E
    E --> F["Retry idempotent và đối soát"]
~~~

**Ưu điểm:** đơn giản, dễ quan sát ở mức yêu cầu, không cần thêm hàng đợi khi quy mô nhỏ. **Giới hạn:** độ trễ API tăng theo số bảng, thất bại từng phần vẫn có thể xảy ra và process có thể chết trước khi lưu việc cần retry. Chỉ trả thành công khi cả hai lệnh có phản hồi thành công **không** giải quyết khoảng trống do sự cố trước đó hoặc timeout có kết quả không xác định.

Nếu chọn cách này, cần có **bản ghi công việc chờ đồng bộ được lưu bền vững** hoặc một lần quét đối soát đủ tin cậy. Retry bằng bộ nhớ trong tiến trình không bảo vệ được khi tiến trình bị khởi động lại.

### 4.2. CQL batch khi thật sự cần nhóm mutation

Ví dụ một logged batch ghi hai biểu diễn của đơn:

~~~sql
BEGIN LOGGED BATCH
    INSERT INTO orders_by_id
        (order_id, customer_id, created_at, month_bucket,
         status, amount, revision)
    VALUES (?, ?, ?, ?, ?, ?, ?);

    INSERT INTO orders_by_customer_month
        (customer_id, month_bucket, created_at, order_id,
         status, amount, revision)
    VALUES (?, ?, ?, ?, ?, ?, ?);
APPLY BATCH;
~~~

**Logged batch** sử dụng batchlog để giúp các mutation của batch được áp dụng cuối cùng dù có lỗi nút trong quá trình thực hiện. Tuy nhiên, các mutation ở nhiều partition/bảng **không được bảo đảm hiển thị đồng thời** cho mọi truy vấn. Batch không có rollback và isolation tổng quát như transaction ACID của RDBMS; timeout vẫn cần xử lý cẩn thận.

Không dùng batch như cách mặc định tăng tốc ghi số lượng lớn. Batch nhiều partition có overhead và có thể tạo tải tập trung ở coordinator. **Unlogged batch** cũng không phải giải pháp bảo đảm toàn bộ mutation đa partition; nó chủ yếu thích hợp khi các thao tác có cùng phạm vi partition phù hợp. Khi cần đồng bộ nghiệp vụ liên tục qua nhiều read model, batch không thay thế cho kiểm soát thứ tự, retry và đối soát.

### 4.3. Đồng bộ bất đồng bộ qua sự kiện

Với nhiều read model, có thể tách lệnh cập nhật nghiệp vụ và luồng dựng read model:

~~~mermaid
flowchart TD
    A["API / lệnh nghiệp vụ"] --> B["Ghi trạng thái chuẩn vào orders_by_id"]
    B --> C["Nguồn thay đổi bền vững: CDC / event log có bảo đảm"]
    C --> D["Consumer nhóm theo order_id"]
    D --> E{"Revision đã áp dụng?"}
    E -->|"Mới hơn"| F["Cập nhật read model có điều kiện"]
    E -->|"Đã có hoặc cũ"| G["Bỏ qua an toàn"]
    F --> H["Ghi nhận tiến độ"]
    F --> I["Lỗi: retry, DLQ, đối soát"]
    I --> D
~~~

Read model có thể trễ hơn nguồn sự thật trong một khoảng thời gian. Đổi lại, hệ thống có thể chủ động retry, xây dựng thêm bảng mới và mở rộng bộ xử lý theo khóa nghiệp vụ.

Điểm khó nhất là **đảm bảo không làm mất sự kiện giữa bước ghi nguồn và bước phát sự kiện**. Ghi Cassandra xong rồi gọi `publish()` trực tiếp tạo khoảng trống: process có thể chết trước khi publish. Cần chọn một nguồn thay đổi có khả năng phục hồi, ví dụ cơ chế CDC được triển khai và vận hành đúng, một event log bền vững làm nguồn sự thật, hoặc cơ chế ghi nhận công việc kèm đối soát. Mẫu *transactional outbox* cần xem xét bảo đảm thực tế của nơi lưu outbox: chỉ thêm một bảng `outbox` và gọi hai lần `save()` **không** tự có atomic commit giữa hai bảng Cassandra.

Consumer thường cần chịu được **at-least-once delivery**: cùng sự kiện có thể phát lại nhiều lần. Hàng đợi phân vùng theo `order_id` giúp giữ thứ tự đối với một khóa, nhưng vẫn phải xử lý retry, rebalance và sự kiện cũ đến trễ.

### 4.4. So sánh lựa chọn

| Phương án | Hợp với trường hợp | Đánh đổi chính |
| --- | --- | --- |
| Ghi trực tiếp hai bảng | Ít bảng, tải vừa, yêu cầu đọc gần tức thời và có đối soát | API phụ thuộc nhiều lệnh ghi; phải xử lý thất bại từng phần |
| Logged batch | Nhóm một số mutation có quan hệ logic và hiểu rõ chi phí | Có atomicity cuối cùng cho batch nhưng không có isolation/rollback kiểu SQL |
| Sự kiện/CDC và projector | Nhiều read model, cần khôi phục và mở rộng độc lập | Chấp nhận eventual consistency; vận hành event log, consumer, retry |
| Chỉ giữ nguồn sự thật, dựng dữ liệu khi đọc | Truy vấn hiếm, tránh duy trì thêm bảng | Phải trả chi phí nhiều lần đọc/ghép ở ứng dụng; không phải mọi truy vấn đều khả thi |

Quyết định nên dựa trên yêu cầu thực tế về độ trễ hiển thị, lưu lượng ghi, số read model, chi phí vận hành và cách giải quyết dữ liệu sai lệch.

## 5. Idempotency: ghi lại bao nhiêu lần vẫn có kết quả đúng

**Idempotency** nghĩa là xử lý lại cùng một thao tác không làm phát sinh hiệu ứng nghiệp vụ ngoài ý muốn. Điều này quan trọng khi client retry sau timeout hoặc consumer nhận lại sự kiện.

### 5.1. Dùng khóa và giá trị ổn định

Việc ghi lại một snapshot `(order_id, status, amount, revision)` với cùng khóa thường dễ làm idempotent hơn việc cập nhật cộng dồn. Ví dụ:

~~~sql
-- Mutation gán giá trị; phải bổ sung kiểm soát revision/thứ tự nếu có tranh chấp.
UPDATE orders_by_customer_month
SET status = ?, amount = ?, revision = ?
WHERE customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;
~~~

Ngược lại, các hành động như “cộng điểm thêm 10”, “gửi email” hoặc “trừ tồn kho” có thể gây tác dụng lặp lại. Chúng cần khóa idempotency riêng ở lớp nghiệp vụ và cơ chế deduplicate cho từng hiệu ứng. Không suy ra rằng một câu `UPDATE` bình thường tự chống được sự kiện đến sai thứ tự.

### 5.2. Ghi có điều kiện trên bảng nguồn

Nếu đơn chỉ được tạo một lần, LWT có thể ngăn hai request cùng chiếm một `order_id`:

~~~sql
INSERT INTO orders_by_id
    (order_id, customer_id, created_at, month_bucket,
     status, amount, revision)
VALUES (?, ?, ?, ?, 'NEW', ?, 1)
IF NOT EXISTS;
~~~

Khi chuyển trạng thái từ revision 1 sang 2:

~~~sql
UPDATE orders_by_id
SET status = 'PAID', revision = 2
WHERE order_id = ?
IF revision = 1;
~~~

Ứng dụng phải đọc cờ `[applied]` của kết quả CQL. Nếu `false`, thao tác có thể đã được xử lý trước đó hoặc đã thua một cập nhật cạnh tranh; cần đọc trạng thái hiện tại và quyết định phản hồi theo nghiệp vụ. LWT dùng đồng thuận, có chi phí cao hơn ghi thông thường và **chỉ bảo vệ điều kiện trên dữ liệu mà lệnh đó tác động**. LWT trên `orders_by_id` không tạo một transaction nguyên tử với read model.

Với hệ thống tạo `revision` theo mỗi biến động, cần đảm bảo việc tăng revision và cập nhật trạng thái ở nguồn được điều phối an toàn. Không thể dùng `revision = revision + 1` như một phép tăng nguyên tử chung cho cột thông thường trong mọi lệnh ghi; dùng CAS, điều phối tuần tự hoặc nguồn sự kiện có thứ tự.

### 5.3. Projector chống sự kiện trùng và sai thứ tự

Giả sử view đang ở `revision=4`:

- Nhận lại sự kiện `revision=4`: bỏ qua vì đã áp dụng.
- Nhận sự kiện `revision=3`: bỏ qua vì là trạng thái cũ.
- Nhận snapshot đầy đủ `revision=5`: áp dụng nếu điều kiện cập nhật vẫn khớp revision trước đó.
- Nhận sự kiện chỉ chứa thay đổi tăng dần của `revision=6` trước `revision=5`: **không** áp dụng ngay nếu thiếu biến đổi của revision 5; phải đợi hoặc phát lại đúng thứ tự.

Với snapshot đầy đủ, projector có thể dùng lần so sánh và ghi có điều kiện tại **một row của read model**:

~~~sql
UPDATE orders_by_customer_month
SET status = ?, amount = ?, revision = ?
WHERE customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?
IF revision = ?;
~~~

Tham số cuối là revision mà projector vừa quan sát được. Nếu điều kiện không được áp dụng, đọc lại row, so sánh revision rồi quyết định bỏ qua hoặc thử lại. Với row view **chưa tồn tại**, cần đường khởi tạo riêng bằng `INSERT ... IF NOT EXISTS` và xử lý kết quả tranh chấp. Không được giả định `UPDATE ... IF revision = ?` tự tạo row khi row chưa có.

Ví dụ dùng Java Driver cùng một ứng dụng Spring Data Cassandra, lược bỏ import và xử lý lỗi vận hành:

~~~java
@Component
public class OrderViewProjector {
    private final CqlSession session;
    private final PreparedStatement guardedUpdate;

    public OrderViewProjector(CqlSession session) {
        this.session = session;
        this.guardedUpdate = session.prepare(
            "UPDATE orders_by_customer_month " +
            "SET status = ?, amount = ?, revision = ? " +
            "WHERE customer_id = ? AND month_bucket = ? " +
            "AND created_at = ? AND order_id = ? " +
            "IF revision = ?"
        );
    }

    public boolean updateExistingView(
            UUID customerId,
            String monthBucket,
            Instant createdAt,
            UUID orderId,
            String status,
            BigDecimal amount,
            long nextRevision,
            long observedRevision) {

        BoundStatement statement = guardedUpdate.bind(
            status, amount, nextRevision,
            customerId, monthBucket, createdAt, orderId,
            observedRevision
        );
        Row result = session.execute(statement).one();
        return result != null && result.getBoolean("[applied]");
    }
}
~~~

Phương thức này minh họa **CAS cho một row đã tồn tại**. Một projector hoàn chỉnh còn phải phân biệt view chưa có, giá trị cũ hơn, timeout không rõ kết quả và retry có giới hạn. Nếu chọn xử lý một stream theo khóa để bảo toàn thứ tự, vẫn cần kiểm tra revision để đề phòng phát lại và thay đổi trong topology consumer.

> **Lưu ý:** Cassandra giải quyết xung đột ghi bằng timestamp ở mức cell. Chỉ lưu thêm cột `revision` nhưng vẫn dùng `save()` vô điều kiện không thể ngăn một retry cũ ghi đè dữ liệu mới. Bảo vệ bằng LWT, thiết kế writer đơn theo khóa có bảo đảm phù hợp hoặc cơ chế điều phối tương đương.

## 6. Entity mapping, repository và CassandraTemplate đóng vai trò gì?

Spring Data Cassandra làm việc với **từng biểu diễn vật lý** của dữ liệu. Nó không tự quản lý quan hệ giữa hai bảng như ORM có cascade của JPA.

### 6.1. Một entity cho một bảng

~~~java
@Table("orders_by_id")
public class OrderById {
    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("status")
    private String status;

    @Column("revision")
    private Long revision;

    // Các field còn lại, constructor, getter, setter...
}

@PrimaryKeyClass
public class OrderByCustomerMonthKey implements Serializable {
    @PrimaryKeyColumn(name = "customer_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(name = "month_bucket", ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private String monthBucket;

    @PrimaryKeyColumn(name = "created_at", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.DESCENDING)
    private Instant createdAt;

    @PrimaryKeyColumn(name = "order_id", ordinal = 3,
        type = PrimaryKeyType.CLUSTERED, ordering = Ordering.ASCENDING)
    private UUID orderId;

    // Constructor, getter, setter, equals(), hashCode()...
}

@Table("orders_by_customer_month")
public class OrderByCustomerMonth {
    @PrimaryKey
    private OrderByCustomerMonthKey key;

    @Column("status")
    private String status;

    @Column("amount")
    private BigDecimal amount;

    @Column("revision")
    private Long revision;

    // Constructor, getter, setter...
}
~~~

Các class rút gọn để tập trung vào mô hình; class khóa ghép phải có `equals()`/`hashCode()` đúng với các thành phần khóa. Entity và CQL schema cần được kiểm tra khớp nhau khi triển khai.

Repository cho từng bảng có thể khai báo:

~~~java
public interface OrderByIdRepository
        extends CassandraRepository<OrderById, UUID> {
}

public interface OrderByCustomerMonthRepository
        extends CassandraRepository<OrderByCustomerMonth,
                                    OrderByCustomerMonthKey> {
}
~~~

Ví dụ chọn read model bằng `CassandraTemplate`:

~~~java
Query query = Query.query(Criteria.where("customer_id").is(customerId))
    .and(Criteria.where("month_bucket").is(monthBucket))
    .limit(20);

List<OrderByCustomerMonth> recentOrders =
    cassandraTemplate.select(query, OrderByCustomerMonth.class);
~~~

Repository và template chịu trách nhiệm tạo/thực thi câu lệnh cho bảng được ánh xạ. Một lời gọi `orderByIdRepository.save(order)` **không** tự cập nhật `orders_by_customer_month`. Với logic CAS cần đọc `[applied]` như phần trên, có thể dùng Java Driver/CQL tường minh hoặc API phù hợp của Spring Data Cassandra, tùy phiên bản đang dùng.

## 7. Nhất quán của replica khác với đồng bộ read model

Trong một cụm có replication factor phù hợp, `LOCAL_QUORUM` cho phép một thao tác đọc/ghi yêu cầu phản hồi từ đa số replica trong data center. Điều này ảnh hưởng tính sẵn sàng, độ trễ và mức bảo đảm khi đọc **cùng một dữ liệu logic**, nhưng không buộc hai bảng ứng dụng được cập nhật cùng một thời điểm.

Ví dụ:

1. Ghi `status=PAID` vào `orders_by_id` tại `LOCAL_QUORUM`, nhận thành công.
2. Consumer chưa xử lý sự kiện chuyển trạng thái.
3. Đọc `orders_by_customer_month` tại `LOCAL_QUORUM`, vẫn thấy `NEW`.

Đây không nhất thiết là lỗi replica hay lỗi consistency level. View chưa nhận mutation tương ứng. Cần phân biệt:

- **Replica consistency:** các replica của cùng một bảng/partition được đọc/ghi với mức bảo đảm nào?
- **Projection consistency:** read model đã phản ánh sự kiện nghiệp vụ đến revision nào?
- **Business consistency:** hệ thống có cho phép đọc hai biểu diễn khác nhau trong một khoảng trễ nhất định không?

Nếu API cần “đọc ngay sau ghi” cho một thao tác quan trọng, có thể đọc trực tiếp từ bảng nguồn, trả snapshot mới từ command response, hoặc đặt một cơ chế chờ projection đạt revision yêu cầu với timeout rõ ràng. Chờ projection chỉ mang lại bảo đảm khi biết nó đã áp dụng revision và có cách xác minh kết quả; không nên giả định chỉ cần `Thread.sleep()` là đủ.

Materialized view của Cassandra (nếu được sử dụng trong phiên bản và môi trường cụ thể) cũng không phải phương án mặc định thay thế toàn bộ logic đồng bộ ứng dụng: cần xét điều kiện thiết kế khóa, giới hạn truy vấn, tính nhất quán, chi phí vận hành và hỗ trợ của hệ thống. Không mặc định rằng một materialized view giải quyết được mọi đường đọc hoặc bất biến nghiệp vụ.

## 8. Xóa, đổi khóa và hiệu ứng phát lại

### 8.1. Xóa phải có mặt trong hợp đồng đồng bộ

Ví dụ xóa đơn vật lý đòi hỏi xử lý cả hai địa chỉ:

~~~sql
DELETE FROM orders_by_id
WHERE order_id = ?;

DELETE FROM orders_by_customer_month
WHERE customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;
~~~

Nếu chỉ xóa bảng nguồn, dòng cũ còn trong danh sách. Nếu sự kiện tạo đơn cũ được phát lại sau khi xóa, projector có thể **tạo lại** view. Một chiến lược là dùng trạng thái logic `DELETED` với revision tăng dần và chỉ dọn vật lý sau khi đủ thời gian/điều kiện; consumer phải biết cách bỏ qua sự kiện revision cũ.

Trong Cassandra, xóa và TTL tạo tombstone. Xóa nhiều, TTL không đồng đều hoặc partition quá lớn có thể làm tăng chi phí đọc, compaction. Không nên coi “xóa rồi insert lại” là thao tác miễn phí; cần có chính sách lưu trữ, dọn dữ liệu và theo dõi tombstone.

### 8.2. Trường khóa cần ổn định

Nếu `customer_id`, `month_bucket` hoặc `created_at` thay đổi, row trong bảng read model sẽ nằm ở một **primary key khác**. Ghi row mới không tự xóa row cũ. Vì vậy:

1. Ưu tiên giữ các trường dùng trong khóa ổn định.
2. Nếu nghiệp vụ buộc di chuyển, phải biết **khóa cũ** để xóa/mức đánh dấu hết hiệu lực và **khóa mới** để ghi.
3. Thiết kế sự kiện di chuyển mang cả khóa cũ, khóa mới và revision.
4. Xử lý retry để không lặp lại tác dụng phụ và đối soát các row mồ côi.

## 9. Đối soát là một phần của thiết kế, không phải công việc chữa cháy

Dù đã có event log và retry, vẫn cần cơ chế phát hiện read model lệch với nguồn sự thật: lỗi phần mềm, sự kiện bị bỏ sót, khôi phục dữ liệu, backfill hoặc thao tác vận hành có thể tạo sai lệch.

### 9.1. Đối soát có phạm vi và giới hạn tải

Một quy trình có thể thực hiện:

1. Xác định tập `order_id` theo khoảng thời gian, bucket hoặc log sự kiện cần kiểm tra. Tránh quét toàn bảng trong giờ cao điểm.
2. Đọc snapshot nguồn và row read model bằng **khóa đầy đủ**; so sánh sự tồn tại, `revision`, `status`, `amount` và khóa phân vùng dự kiến.
3. Nếu view thiếu hoặc revision thấp hơn, tạo công việc rebuild từ snapshot nguồn mới nhất.
4. Nếu view chứa row không còn hợp lệ, áp dụng quy tắc xóa logic/dọn dữ liệu an toàn; không xóa mù khi nguồn đang chuyển trạng thái.
5. Ghi nhận số lượng lệch, số sửa thành công, số retry và các ngoại lệ cần điều tra.

Không dùng `COUNT(*)` toàn bảng như cách đối chiếu thường trực ở quy mô lớn. Cassandra không tối ưu cho quét/count phân tán tùy ý; tốt hơn là tổ chức checkpoint, danh sách khóa có thể quét theo phạm vi xác định và công việc nền được giới hạn tốc độ.

### 9.2. Những chỉ số nên quan sát

| Chỉ số | Ý nghĩa vận hành |
| --- | --- |
| Projection lag p95/p99 | Thời gian từ khi nguồn thay đổi đến khi read model áp dụng revision |
| Số sự kiện đang chờ và tuổi sự kiện cũ nhất | Xác định consumer bị kẹt, tích tụ hoặc mất khả năng bắt kịp |
| Retry, timeout và DLQ | Phân biệt lỗi tạm thời với lỗi dữ liệu/code cần xử lý |
| Revision mismatch, missing/orphan view | Mức sai lệch thực tế giữa các biểu diễn |
| LWT contention, latency | Chi phí và mức tranh chấp của cập nhật có điều kiện |
| Partition size, tombstone, read latency | Rủi ro hiệu năng của bảng theo truy vấn |

Nên đặt mục tiêu rõ ràng, chẳng hạn “99% read model cập nhật trong giới hạn trễ mà sản phẩm chấp nhận”, rồi cảnh báo theo mục tiêu đó thay vì chỉ đếm số lệnh ghi thành công.

## 10. Thay đổi schema và bổ sung read model mới

Giả sử muốn thêm màn hình “đơn theo trạng thái trong từng cửa hàng” và bảng `orders_by_store_status_day`. Không thể chỉ tạo bảng rồi chờ dữ liệu cũ tự xuất hiện.

Một quy trình triển khai an toàn gồm:

1. **Định nghĩa truy vấn và khóa** của bảng mới; ước tính số dòng mỗi partition và mức phân phối tải.
2. **Tạo schema** mới nhưng chưa đổi đường đọc chính.
3. **Thiết lập nguồn thay đổi cho dữ liệu mới**: projector hoặc đường ghi chịu trách nhiệm cập nhật bảng mới, có cơ chế replay và checkpoint.
4. **Backfill dữ liệu lịch sử** từ nguồn sự thật bằng luồng có giới hạn tốc độ. Phân biệt snapshot cũ và thay đổi đến trong khi backfill.
5. **Đối soát và bắt kịp revision**; không cho snapshot cũ ghi đè sự kiện mới.
6. **Chuyển dần đường đọc** khi đã đo được độ đầy đủ, độ trễ và tỷ lệ lỗi.
7. **Theo dõi và dọn đường cũ** sau thời gian chuyển đổi phù hợp.

Khi nhiều bảng cùng lặp trường `status`, thêm một giá trị enum hoặc thay quy tắc trạng thái cũng phải xét tất cả projector và client đọc chúng. Data contract và versioning của event là một phần của thay đổi schema.

## 11. Tình huống thực hành: lỗi ở giữa hai thao tác

Giả sử đơn `O-123` có snapshot ở cả hai bảng tại `revision=7, trạng thái `NEW`. Dịch vụ nhận lệnh chuyển `PAID` và cập nhật bảng nguồn lên `revision=8`, nhưng projector gặp timeout.

**Yêu cầu thiết kế:** màn hình chi tiết phải trả `PAID`; màn hình danh sách được phép hiển thị `NEW` trong một khoảng trễ có giới hạn, nhưng cuối cùng phải hiển thị `PAID` ở revision 8.

Luồng xử lý đề xuất:

1. Đường cập nhật nguồn đảm bảo lệnh chuyển trạng thái được chấp nhận đúng một lần về mặt nghiệp vụ; gắn `revision=8`.
2. Cơ chế thay đổi bền vững lưu hoặc tái dựng được snapshot revision 8. Nếu publish thất bại, nó vẫn có đường phát lại hoặc đối soát.
3. Consumer nhận snapshot revision 8. Nếu view hiện là revision 7, cập nhật có điều kiện lên 8; nếu timeout, kiểm tra lại trạng thái trước khi thử.
4. Khi cùng sự kiện revision 8 được gửi lại, consumer nhận thấy view đã ở revision 8 nên bỏ qua.
5. Nếu một sự kiện revision 6 đến muộn, consumer bỏ qua vì không được đưa trạng thái view lùi về 6.
6. Job đối soát phát hiện các đơn có view thiếu/lạc hậu và sửa từ snapshot nguồn nếu luồng sự kiện bỏ sót.

### Kiểm thử nên thực hiện

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Cùng lệnh được gửi hai lần | Không phát sinh hai lần hiệu ứng nghiệp vụ; revision cuối đúng |
| Ghi nguồn thành công, projector tạm ngừng | View trễ có kiểm soát, rồi bắt kịp khi projector hoạt động lại |
| Consumer nhận `8, 8, 7` | View vẫn ở revision 8 |
| Hai consumer cùng xử lý một revision | CAS hoặc điều phối theo khóa ngăn ghi sai; có cơ chế xử lý CAS thất bại |
| Timeout sau khi server đã áp dụng | Retry không đưa dữ liệu lùi và không tạo tác dụng phụ trùng |
| Xóa logic ở revision 9, rồi phát lại revision 8 | View không hồi sinh đơn |
| Backfill revision 5 trong khi view đã ở revision 9 | Snapshot lịch sử không ghi đè phiên bản mới |

## 12. Những sai lầm cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Cassandra đã có replication nên hai bảng sẽ tự đồng bộ.” | Replication giữa node khác với duy trì hai read model. |
| “`LOCAL_QUORUM` đảm bảo đọc mọi bảng đều cùng trạng thái.” | Nó áp dụng cho replica của từng dữ liệu được đọc/ghi; không bảo đảm đồng bộ liên bảng. |
| “Hai lần `repository.save()` trong `@Transactional` sẽ rollback cùng nhau.” | Spring Data Cassandra không biến chúng thành transaction ACID đa bảng kiểu JPA. |
| “Logged batch khiến mọi bảng đổi trạng thái cùng lúc.” | Logged batch giúp eventual atomic application nhưng không cấp isolation/rollback tổng quát. |
| “Retry đến khi thành công là đủ.” | Retry cũ có thể ghi đè mới; phải xét revision, idempotency và thứ tự. |
| “Thêm cột revision là tự hết race condition.” | Cần bảo đảm việc so sánh và ghi thực sự có điều kiện hoặc xử lý tuần tự đúng. |
| “Publish event sau khi save thì chắc chắn không mất event.” | Có khoảng trống khi process dừng giữa hai thao tác; cần cơ chế bền vững, replay và đối soát. |
| “`ALLOW FILTERING` thay được bảng theo truy vấn.” | Phải tối ưu đường truy cập bằng partition/clustering và đo hiệu năng. |
| “Xóa nguồn là các bản sao khác biến mất.” | Mỗi read model cần quy tắc xóa và chống phát lại dữ liệu cũ. |

## 13. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `orders_by_customer_month` vẫn có thể hiển thị `NEW` sau khi `orders_by_id` đã ghi `PAID` tại `LOCAL_QUORUM`?

*Gợi ý:* Hai bảng là hai biểu diễn logic khác nhau. Consistency level không vận hành projector thay ứng dụng.

**Câu 2.** Một client timeout sau lệnh tạo đơn. Khi retry, hệ thống có nguy cơ nào và phải bảo vệ bằng gì?

*Gợi ý:* Server có thể đã ghi xong. Dùng định danh yêu cầu, ghi có điều kiện và thao tác có thể phát lại an toàn.

**Câu 3.** Vì sao lưu `revision` mà luôn dùng `save()` vô điều kiện vẫn nguy hiểm?

*Gợi ý:* Cassandra không tự so sánh revision nghiệp vụ; mutation đến muộn có timestamp mới có thể ghi đè trạng thái mới hơn.

**Câu 4.** Có thể dùng `BEGIN LOGGED BATCH` để thay hoàn toàn event log và đối soát trong hệ thống nhiều read model không?

*Gợi ý:* Batch có phạm vi bảo đảm và chi phí riêng; không mang lại isolation đa bảng, thứ tự sự kiện hay quy trình phục hồi read model theo thời gian.

**Câu 5.** Khi đổi `month_bucket` của một đơn, tại sao chỉ lưu một row mới là sai?

*Gợi ý:* Đây là một thành phần primary key. Row cũ còn tồn tại tại khóa cũ, nên cần xử lý di chuyển/xóa hợp lệ và retry.

## Kết luận

Nhân bản dữ liệu giữa nhiều bảng là hệ quả trực tiếp của thiết kế Cassandra theo truy vấn. Spring Data Cassandra giúp ánh xạ entity, thực thi repository, `CassandraTemplate` và CQL, nhưng **ứng dụng vẫn phải thiết kế hợp đồng nhất quán giữa các read model**. Một giải pháp đáng tin cậy cần biết nguồn sự thật ở đâu, dùng khóa truy vấn ổn định, có cách phát hiện và phát lại thay đổi, bảo vệ trước retry/sai thứ tự bằng revision và thao tác có điều kiện, đồng thời liên tục đo độ trễ và đối soát dữ liệu. Những lựa chọn này quan trọng hơn việc chỉ cố gắng ghi vào tất cả các bảng trong cùng một phương thức Java.

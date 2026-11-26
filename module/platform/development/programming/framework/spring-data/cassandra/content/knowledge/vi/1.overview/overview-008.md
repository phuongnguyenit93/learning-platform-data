# Khác biệt với JPA về ánh xạ, quan hệ, vòng đời entity và giao dịch

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt tư duy **ánh xạ quan hệ và quản lý trạng thái đối tượng** của Spring Data JPA với tư duy **thiết kế bảng theo truy vấn** của Spring Data Cassandra.
- Biết cách chuyển từ entity JPA có quan hệ sang các bảng Cassandra có partition key, clustering column và dữ liệu được nhân bản có chủ đích.
- Giải thích vì sao việc sửa một đối tượng đã đọc từ Cassandra không tự động lưu thay đổi như cơ chế dirty checking của JPA.
- Chọn đúng giữa thao tác ghi thông thường, batch và lightweight transaction (LWT); nhận diện những bảo đảm mà Cassandra **không** cung cấp tương đương giao dịch ACID của cơ sở dữ liệu quan hệ.

Bài học nằm trong phạm vi **SPRING_DATA_CASSANDRA**: truy cập Apache Cassandra bằng Spring Data Cassandra thông qua entity mapping, repository, `CassandraTemplate` và CQL. Khi đối chiếu với JPA, cần luôn nhớ Cassandra là cơ sở dữ liệu phân tán dạng wide-column, được thiết kế để phục vụ các truy vấn đã biết và mở rộng theo nhiều nút.

## 1. Hai mô hình tư duy khác nhau

Với **Spring Data JPA**, mô hình ứng dụng thường bắt đầu từ các thực thể nghiệp vụ như `Customer`, `Order`, `OrderItem`. Các đối tượng được ánh xạ tới bảng quan hệ; ứng dụng dùng khóa ngoại, phép `JOIN` và giao dịch để kết hợp dữ liệu, cập nhật nhiều bảng nhất quán.

Với **Spring Data Cassandra**, mô hình thường bắt đầu từ các câu hỏi mà ứng dụng cần trả lời: “Tìm một đơn hàng theo mã”, “Lấy 20 đơn gần nhất của khách hàng”, “Liệt kê đơn theo trạng thái ở một chi nhánh”. Mỗi kiểu truy cập có thể cần một bảng riêng với khóa phân vùng phù hợp. Các bảng có thể lặp lại cùng dữ liệu; ứng dụng chịu trách nhiệm cập nhật những bản sao đó.

| Khía cạnh | Spring Data JPA / RDBMS | Spring Data Cassandra |
| --- | --- | --- |
| Điểm xuất phát khi thiết kế | Thực thể, chuẩn hóa, quan hệ và ràng buộc | Truy vấn cụ thể, phân bố dữ liệu và partition key |
| Ánh xạ | `@Entity`, `@Id`, `@JoinColumn`, `@ManyToOne`… | `@Table`, `@PrimaryKey`, `@PrimaryKeyClass`, `@PrimaryKeyColumn`… |
| Khóa | Primary key; thường có foreign key giữa các bảng | Partition key và clustering column; không có foreign key quan hệ |
| Kết hợp dữ liệu | `JOIN`, quan hệ ORM, lazy/eager loading | Đọc các bảng đã thiết kế cho truy vấn hoặc ghép dữ liệu ở ứng dụng |
| Quản lý đối tượng | Persistence context; trạng thái managed/detached, dirty checking | Ánh xạ kết quả CQL thành đối tượng; không có JPA persistence context |
| Ghi thay đổi | Có thể flush thay đổi của managed entity khi commit | Gọi `save`/`insert`/`update` hoặc thực thi CQL tường minh |
| Giao dịch | Giao dịch RDBMS có commit/rollback, mức isolation tùy DB | Không có giao dịch ACID đa câu lệnh, đa bảng tương đương JPA |
| Truy vấn và phân trang | JPQL/SQL, join, index, thường dùng offset/limit | CQL theo khóa truy cập; paging state, giới hạn theo partition |
| Nhất quán | Tùy transaction isolation và cơ sở dữ liệu | Consistency level có thể cấu hình; bản sao dữ liệu giữa bảng không tự đồng bộ |

> **Ghi nhớ:** Cả hai đều có class Java được gọi là “entity”, nhưng một entity Cassandra **không** mặc nhiên có toàn bộ ngữ nghĩa của một managed JPA entity.

## 2. Ánh xạ entity: từ định danh nghiệp vụ sang khóa truy vấn

### 2.1. Ví dụ JPA

Giả sử hệ thống bán hàng có khách hàng và đơn hàng. Trong mô hình quan hệ, đơn hàng có thể chứa tham chiếu đối tượng tới khách hàng:

~~~java
@Entity
@Table(name = "orders")
public class JpaOrder {

    @Id
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private JpaCustomer customer;

    private String status;
    private BigDecimal amount;

    // Constructor, getter, setter...
}
~~~

Ở đây:

- `@ManyToOne` diễn đạt quan hệ đối tượng. Cơ sở dữ liệu quan hệ có thể dùng foreign key `customer_id` để đảm bảo tính toàn vẹn, nếu schema được khai báo ràng buộc đó.
- JPA/Hibernate có thể tải `customer` qua quan hệ khi cần; ứng dụng có thể dùng `JOIN` trong truy vấn.
- `@Id` chủ yếu định danh một dòng; cách tổ chức khóa không nhất thiết quyết định toàn bộ khả năng truy vấn.

### 2.2. Cùng bài toán trong Cassandra

Giả sử có hai truy vấn quan trọng:

1. Tra cứu một đơn bằng `order_id`.
2. Xem **20 đơn mới nhất** của một `customer_id`.

Nếu chỉ tạo một bảng theo `order_id`, truy vấn thứ hai sẽ không hiệu quả vì Cassandra không thể tự do quét và sắp xếp dữ liệu toàn cụm như một RDBMS. Vì vậy, tạo hai bảng dành cho hai đường đọc:

~~~sql
CREATE TABLE orders_by_id (
    order_id uuid PRIMARY KEY,
    customer_id uuid,
    created_at timestamp,
    status text,
    amount decimal
);

CREATE TABLE orders_by_customer (
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    status text,
    amount decimal,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

~~~sql
-- Một partition/row theo ID đơn hàng
SELECT * FROM orders_by_id WHERE order_id = ?;

-- Đọc những đơn mới nhất trong partition của một khách hàng
SELECT * FROM orders_by_customer
WHERE customer_id = ?
LIMIT 20;
~~~

`orders_by_id` có partition key là `order_id`. Trong `orders_by_customer`, **partition key** là `customer_id`, còn `created_at` và `order_id` là **clustering columns**. Các dòng trong cùng partition được tổ chức theo thứ tự clustering đã định, giúp truy vấn “đơn mới nhất của khách” tận dụng cách lưu trữ.

Cùng một đơn xuất hiện ở hai bảng. Đây là **denormalization có mục đích**, khác với việc chuẩn hóa bảng và dùng `JOIN` trong JPA. Khi trạng thái của đơn thay đổi, chương trình phải xác định cách cập nhật cả hai nơi.

> **Lưu ý hiệu năng:** Partition theo một khách hàng có thể phình rất lớn nếu khách hàng tạo cực nhiều đơn. Khi đó có thể dùng khóa ghép như `(customer_id, month_bucket)` và cho ứng dụng đọc các bucket cần thiết. Bucket cần được chọn theo tải thực tế; không nên dùng một partition vô hạn.

### 2.3. Java entity và khóa ghép trong Spring Data Cassandra

Entity cho truy vấn theo ID có thể ánh xạ đơn giản:

~~~java
@Table("orders_by_id")
public class OrderById {

    @PrimaryKey("order_id")
    private UUID orderId;

    @Column("customer_id")
    private UUID customerId;

    @Column("created_at")
    private Instant createdAt;

    @Column("status")
    private String status;

    @Column("amount")
    private BigDecimal amount;

    // Constructor, getter, setter...
}
~~~

Với bảng theo khách hàng, entity có **khóa chính ghép**. Spring Data Cassandra dùng `@PrimaryKeyClass` và `@PrimaryKeyColumn` để thể hiện vai trò các thành phần khóa:

~~~java
@PrimaryKeyClass
public class OrderByCustomerKey implements Serializable {

    @PrimaryKeyColumn(
        name = "customer_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "created_at",
        ordinal = 1,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING
    )
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING
    )
    private UUID orderId;

    // No-arg constructor, getter, setter, equals() và hashCode()...
}

@Table("orders_by_customer")
public class OrderByCustomer {

    @PrimaryKey
    private OrderByCustomerKey key;

    @Column("status")
    private String status;

    @Column("amount")
    private BigDecimal amount;

    // Constructor, getter, setter...
}
~~~

*Ví dụ lược bỏ các dòng `import` và phương thức thông thường để tập trung vào ánh xạ.* Class khóa cần triển khai `equals()`/`hashCode()` nhất quán theo các thành phần khóa. Trong ứng dụng thực, nên xác nhận thứ tự clustering trong annotation khớp schema CQL đang triển khai.

Khác biệt quan trọng: trong Cassandra, **lựa chọn partition key ảnh hưởng trực tiếp đến việc dữ liệu nằm ở đâu và truy vấn nào được phục vụ hiệu quả**. Thêm annotation vào một class JPA hiện có không giải quyết được vấn đề thiết kế bảng.

### 2.4. Repository, CassandraTemplate và CQL

Một repository Cassandra vẫn có phương thức quen thuộc như `findById` và `save`:

~~~java
public interface OrderByIdRepository
        extends CassandraRepository<OrderById, UUID> {
}

public interface OrderByCustomerRepository
        extends CassandraRepository<OrderByCustomer, OrderByCustomerKey> {
}
~~~

Với truy vấn cần kiểm soát điều kiện và giới hạn, có thể dùng `CassandraTemplate`:

~~~java
// Biến cassandraTemplate được inject qua constructor.
Query query = Query.query(
    Criteria.where("customer_id").is(customerId)
).limit(20);

List<OrderByCustomer> orders =
    cassandraTemplate.select(query, OrderByCustomer.class);
~~~

Spring Data Cassandra giúp ánh xạ và xây dựng lệnh truy vấn, nhưng **không làm biến mất ràng buộc của CQL**: điều kiện truy cập phải phù hợp khóa và schema. Ví dụ, truy vấn `WHERE status = 'PAID'` trên toàn bộ `orders_by_customer` không tự trở nên hiệu quả nhờ repository; cần cân nhắc bảng khác theo access pattern, chỉ mục phù hợp hoặc điều chỉnh yêu cầu.

## 3. Quan hệ: không có JOIN và cascade kiểu JPA

### 3.1. Quan hệ đối tượng không tương đương với quan hệ dữ liệu

Trong JPA, một mô hình có thể khai báo:

~~~java
@OneToMany(mappedBy = "order", cascade = CascadeType.ALL)
private List<JpaOrderItem> items;
~~~

Khi gọi `save` hoặc xóa đơn hàng, hành vi cascade phụ thuộc mapping và trạng thái persistence context. Một câu truy vấn JPQL có thể dùng `JOIN FETCH` để lấy các bản ghi liên quan.

Cassandra **không có foreign key, JOIN quan hệ, lazy proxy association hoặc cascade xóa/lưu theo kiểu JPA**. Nếu một entity Cassandra chứa trường `customerId` thì đó chỉ là giá trị dữ liệu; Spring Data không tự theo ID để nạp `Customer` hoặc tự xóa các bản ghi ở bảng khác.

Ba cách phổ biến để biểu diễn nhu cầu “có liên quan”:

| Nhu cầu đọc | Thiết kế thường gặp | Đánh đổi cần kiểm soát |
| --- | --- | --- |
| Hiển thị vài thông tin khách cùng đơn | Lưu `customer_name`/thông tin cần hiển thị vào bảng theo đơn | Dữ liệu lặp; cần cập nhật hoặc chấp nhận độ trễ đồng bộ |
| Lấy nhiều món của một đơn | Bảng `items_by_order` với partition key `order_id` | Phải giới hạn kích thước partition; ghi/xóa ở bảng riêng |
| Tra cứu cả chiều khách → đơn và đơn → khách | Hai bảng theo hai khóa truy vấn | Ghi nhiều nơi, xử lý thất bại từng phần và đối soát |

Không nên mặc định đưa **toàn bộ** danh sách quan hệ vào một collection của một row Cassandra. Collection phù hợp dữ liệu nhỏ, có giới hạn rõ ràng; một quan hệ một-nhiều phát triển không giới hạn dễ tạo row/partition quá lớn và chi phí cập nhật cao.

### 3.2. Luồng ghi khi một đối tượng có nhiều biểu diễn

Ví dụ dịch vụ tạo đơn cần phục vụ cả hai truy vấn trên:

~~~mermaid
flowchart TD
    A["Nhận yêu cầu tạo đơn + orderId"] --> B["Kiểm tra nghiệp vụ và idempotency"]
    B --> C["Ghi orders_by_id"]
    C --> D["Ghi orders_by_customer"]
    D --> E["Xác nhận kết quả cho ứng dụng"]
    C --> F["Nếu một bước lỗi: ghi nhận để retry/đối soát"]
    D --> F
~~~

Sơ đồ diễn tả **hai thao tác ghi logic**, không phải một transaction ACID. Nếu ghi bảng đầu thành công và bảng thứ hai thất bại, dữ liệu có thể tạm thời khác nhau. Giải pháp cần chọn theo yêu cầu nghiệp vụ: ghi bù có retry và khóa idempotency, xử lý sự kiện, hàng đợi và cơ chế đối soát. Khi thiết kế luồng ghi, cần nêu rõ bảng nào là nguồn dữ liệu chính cho từng nghiệp vụ và người đọc chấp nhận trễ đồng bộ đến mức nào.

Trong trường hợp có thể tận dụng batch hoặc LWT, vẫn phải hiểu giới hạn ở phần giao dịch bên dưới.

## 4. Vòng đời entity: managed và detached khác hoàn toàn đối tượng Cassandra

### 4.1. JPA có persistence context và dirty checking

Một giao dịch JPA điển hình:

~~~java
@Transactional
public void markPaid(UUID orderId) {
    JpaOrder order = entityManager.find(JpaOrder.class, orderId);
    order.setStatus("PAID");
    // Đối tượng đang managed: JPA phát hiện thay đổi
    // và flush xuống DB khi phù hợp, thường trước/ở lúc commit.
}
~~~

Trong phạm vi persistence context, JPA theo dõi entity đã được quản lý. Entity có thể chuyển qua trạng thái transient, managed, detached, removed. Hibernate thường tạo SQL `UPDATE` khi flush nếu phát hiện field cần ghi, ngay cả khi không gọi `save()` thêm lần nữa.

Điều này phụ thuộc giao dịch và trạng thái entity: sửa đối tượng **detached** ở ngoài persistence context không đồng nghĩa tự cập nhật database.

### 4.2. Cassandra không có cơ chế dirty checking của JPA

Với repository Cassandra:

~~~java
public void markPaid(UUID orderId) {
    OrderById order = orderByIdRepository.findById(orderId)
        .orElseThrow();

    order.setStatus("PAID");

    // Bắt buộc phát lệnh ghi tường minh.
    orderByIdRepository.save(order);

    // Nếu hệ thống còn orders_by_customer:
    // phải cập nhật biểu diễn đó theo chiến lược đồng bộ đã thiết kế.
}
~~~

Thay đổi `order.setStatus(...)` chỉ đổi đối tượng trong bộ nhớ. Spring Data Cassandra **không giữ một persistence context để tự phát hiện và flush thay đổi** sau đó. Một lời gọi `save()` chủ động gửi thao tác ghi dựa trên mapping và khóa; nhiều thao tác Cassandra có ngữ nghĩa **upsert**. Không nên giả định `save()` luôn báo lỗi nếu dòng chưa tồn tại hoặc tự bảo vệ trước các ghi đồng thời.

Các điểm dễ nhầm khác:

- **Callback:** JPA có `@PrePersist`/`@PostLoad` và các sự kiện vòng đời. Spring Data Cassandra có cơ chế entity callback/event riêng, chẳng hạn `BeforeConvertCallback` và `BeforeSaveCallback`; không được mặc nhiên coi các callback này tương đương nhau.
- **Khóa chính:** Cassandra yêu cầu đủ thành phần khóa để thao tác đúng row. “Sửa” giá trị thuộc primary key thực chất chỉ định một địa chỉ row khác; nếu cần đổi khóa logic, phải thiết kế bước tạo row mới và xóa row cũ.
- **Lazy loading:** Truy xuất một entity Cassandra không tự kích hoạt proxy để lấy các entity liên quan. Ứng dụng phải truy vấn rõ ràng.
- **Auditing/version:** Các tính năng hỗ trợ metadata hoặc khóa lạc quan phải được cấu hình và hiểu theo semantics Cassandra; không có toàn bộ vòng đời JPA chỉ vì cùng dùng annotation của Spring Data.

### 4.3. Thao tác xóa cũng không tự lan sang bảng khác

Trong JPA, có thể khai báo `CascadeType.REMOVE` hoặc `orphanRemoval = true` cho quan hệ phù hợp. Cassandra không tự xóa bản sao dữ liệu trong `orders_by_customer` khi `orders_by_id` bị xóa. Từng bảng phải có chiến lược xóa/TTL riêng.

Xóa trong Cassandra còn tạo **tombstone** và được dọn theo cơ chế compaction. Xóa hàng loạt, dữ liệu TTL quá nhiều hoặc thường xuyên viết/xóa có thể gây áp lực đọc; vì vậy hành vi xóa không nên được sao chép máy móc từ thiết kế JPA.

## 5. Giao dịch: @Transactional, batch và LWT khác nhau ở đâu?

### 5.1. @Transactional không biến Cassandra thành RDBMS

Với JPA và một relational transaction manager, đoạn sau có thể chạy trong cùng giao dịch DB:

~~~java
@Transactional
public void payAndReserve(UUID orderId) {
    // UPDATE orders
    // UPDATE inventory
    // Nếu có lỗi phù hợp, transaction có thể rollback cả hai.
}
~~~

Với Cassandra, đặt `@Transactional` lên phương thức chứa hai lệnh `repository.save(...)` **không tự tạo** giao dịch ACID có thể rollback cả hai lệnh trên nhiều bảng/partition. Spring Data Cassandra không cung cấp persistence-context transaction giống JPA. Nếu ứng dụng còn có JPA transaction manager, annotation đó có thể điều phối phần RDBMS nhưng **không kéo các lệnh Cassandra vào cùng commit/rollback**.

Một khi lệnh ghi Cassandra đã được hệ thống chấp nhận, ném exception sau đó không có nghĩa Cassandra sẽ hoàn tác dữ liệu đã ghi.

### 5.2. Phân biệt các cơ chế ghi

| Cơ chế | Bảo đảm chính | Không được suy diễn |
| --- | --- | --- |
| Ghi một row bằng CQL | Mutation của một row có tính nguyên tử ở mức row | Không phải transaction giữa các row/bảng |
| Batch CQL cùng partition | Gom các mutation; thường hiệu quả cho dữ liệu cùng partition | Không có đầy đủ isolation/rollback kiểu RDBMS |
| Logged batch nhiều partition | Batchlog giúp bảo đảm các mutation của batch cuối cùng đều được áp dụng khi hệ thống phục hồi | Không bảo đảm mọi thay đổi hiện ra đồng thời với reader; có overhead, không là công cụ tăng tốc bulk write |
| Lightweight transaction (LWT) với `IF` | So sánh và ghi có điều kiện, giúp xử lý tranh chấp trên dữ liệu mục tiêu | Không thay thế giao dịch tổng quát trên nhiều bảng/partition |
| Consistency level như `LOCAL_QUORUM` | Quy định số bản sao cần phản hồi cho từng phép đọc/ghi | Không cấp thêm rollback, foreign key hay isolation liên bảng |

Cassandra có thể đảm bảo mức nguyên tử phù hợp cho những thao tác cụ thể, nhưng **không cung cấp mô hình “unit of work” với rollback toàn bộ như một transaction JPA**. Đặc biệt, logged batch giải quyết việc các mutation được áp dụng cuối cùng; nó không phải một chốt khóa ngăn người đọc nhìn thấy trạng thái trung gian.

### 5.3. Ví dụ LWT để tránh ghi đè vô điều kiện

Khi cần đảm bảo một `order_id` chỉ được tạo một lần, có thể dùng câu lệnh điều kiện:

~~~sql
INSERT INTO orders_by_id (
    order_id, customer_id, created_at, status, amount
) VALUES (?, ?, ?, 'NEW', ?)
IF NOT EXISTS;
~~~

Hoặc chuyển trạng thái nếu điều kiện còn đúng:

~~~sql
UPDATE orders_by_id
SET status = 'PAID'
WHERE order_id = ?
IF status = 'NEW';
~~~

Ứng dụng phải đọc kết quả điều kiện (chẳng hạn cờ `[applied]` ở mức CQL/driver) trước khi thông báo thành công. LWT dùng giao thức đồng thuận nên có chi phí latency/throughput cao hơn ghi thông thường; chỉ dùng khi thực sự cần phối hợp tranh chấp. Một LWT trên `orders_by_id` không mặc nhiên cập nhật nguyên tử `orders_by_customer`.

### 5.4. Nhất quán bản sao khác nhất quán nghiệp vụ

Trong Cassandra, **consistency level** quy định yêu cầu phản hồi từ các replica của một thao tác đọc/ghi. Chọn mức phù hợp, chẳng hạn `LOCAL_QUORUM` trong môi trường nhiều replica, có thể cải thiện độ tin cậy của dữ liệu đọc được và ảnh hưởng độ trễ/sẵn sàng. Nó **không** đồng bộ tự động hai bảng ứng dụng chứa cùng `order_id`.

Cần tách hai câu hỏi:

1. **Replica consistency:** Một thao tác đọc/ghi trên **một dữ liệu logic** chờ bao nhiêu replica?
2. **Business consistency:** Khi đơn chuyển từ `NEW` sang `PAID`, bao lâu hai bảng `orders_by_id` và `orders_by_customer` phản ánh cùng trạng thái?

Câu hỏi thứ hai cần thiết kế luồng ghi, retry, idempotency và đối soát ở tầng ứng dụng. Không thể giải chỉ bằng tăng consistency level.

## 6. Hệ quả đối với query, paging và hiệu năng

Trong JPA, ứng dụng quen với một repository có thể lọc theo nhiều field, thêm `JOIN` và sử dụng `PageRequest` theo kiểu offset. Với Cassandra, truy vấn chỉ hiệu quả khi điều kiện khớp mô hình khóa hoặc một cơ chế index được thiết kế, thử tải và chấp nhận chi phí.

Đối với ví dụ này:

- `WHERE order_id = ?` dùng `orders_by_id`.
- `WHERE customer_id = ? LIMIT 20` dùng `orders_by_customer`.
- `WHERE status = 'PAID'` trên toàn cụm chưa có đường truy cập tốt: cần định nghĩa phạm vi truy vấn thực tế (theo chi nhánh, ngày, trạng thái…), rồi thiết kế bảng theo partition key phù hợp.
- `ALLOW FILTERING` không phải cách sửa mặc định cho một schema không đáp ứng truy vấn; có thể gây quét dữ liệu tốn kém.
- Phân trang Cassandra dựa trên **paging state** do CQL/driver cung cấp; không mặc nhiên hỗ trợ nhảy đến trang sâu bằng `OFFSET` như SQL. Không nên suy diễn rằng `Page`, tổng số kết quả hay `COUNT(*)` toàn bảng luôn rẻ.

Một ứng dụng có danh sách đơn theo khách nên giới hạn kích thước trang và có chiến lược lưu/truyền paging state phù hợp API. Với danh sách rất dài, cần theo dõi kích thước partition, số tombstone, phân bố tải theo partition key, thời gian đọc và số lần retry.

## 7. Tình huống chuyển đổi: bỏ JPA không chỉ là đổi annotation

Giả sử ứng dụng hiện tại làm như sau:

~~~java
@Transactional
public void payOrder(UUID orderId) {
    JpaOrder order = jpaOrderRepository.findById(orderId)
        .orElseThrow();
    order.setStatus("PAID");
    order.getCustomer().increaseLoyaltyPoints(10);
    // JPA dirty checking + transaction database quan hệ.
}
~~~

Không thể chuyển máy móc sang Cassandra bằng cách thay `@Entity` thành `@Table` và thay `JpaRepository` thành `CassandraRepository`: hệ thống sẽ mất cơ chế tự tải quan hệ, dirty checking, cascade và atomic commit của transaction quan hệ.

Cách phân tích đúng bắt đầu từ nghiệp vụ:

1. **Liệt kê truy vấn cần hỗ trợ.** Ai đọc đơn theo ID, theo khách, theo ngày? Có cần truy vấn điểm thưởng khách theo ID không?
2. **Thiết kế bảng theo từng access pattern.** Quyết định partition key, clustering, giới hạn kích thước partition và dữ liệu nào phải nhân bản.
3. **Xác định bất biến nghiệp vụ.** Trạng thái đơn có bắt buộc chuyển theo thứ tự `NEW → PAID`? Hai lần yêu cầu thanh toán trùng nhau có được phép không?
4. **Chọn cơ chế điều phối.** Dùng LWT khi cần ghi có điều kiện trên row; dùng retry idempotent và đối soát cho nhiều bảng; nếu cần transaction ACID bao trùm cập nhật đơn và điểm thưởng, cân nhắc giữ phần đó trong hệ thống giao dịch phù hợp hoặc thiết kế lại quy trình với nhất quán cuối cùng.
5. **Đo và kiểm thử tải.** Xác minh truy vấn CQL đúng khóa, paging hoạt động, dữ liệu không tạo hotspot, và hành vi khi một trong các bước ghi thất bại.

Ví dụ, nếu một yêu cầu thanh toán cập nhật đơn và cộng điểm ở hai bảng Cassandra, cần có mã yêu cầu duy nhất và cách phát hiện “đã xử lý” để retry không cộng điểm hai lần. Việc thao tác `save` hai lần trong một method không cung cấp sự bảo đảm đó.

## 8. Các ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Entity Cassandra giống hệt JPA entity.” | Giống ở hình thức class ánh xạ; khác về khóa, quan hệ, trạng thái và lifecycle. |
| “Có `@ManyToOne` nên Cassandra tự JOIN.” | Cassandra không hỗ trợ quan hệ ORM kiểu đó; phải thiết kế đường đọc. |
| “Sửa object là tự flush.” | Cần chủ động phát lệnh ghi hoặc CQL. |
| “`save()` là update có kiểm tra dòng tồn tại.” | Nhiều thao tác Cassandra mang tính upsert; kiểm tra tồn tại/điều kiện cần xử lý riêng. |
| “`@Transactional` rollback được nhiều lệnh Cassandra.” | Không có ACID transaction Cassandra đa bảng tương đương JPA. |
| “Logged batch tương đương SQL transaction.” | Batch có mục đích và giới hạn riêng; không mang isolation/rollback RDBMS. |
| “Dùng `LOCAL_QUORUM` thì các bảng nhân bản luôn đồng bộ.” | Consistency level xử lý replica của từng thao tác, không đồng bộ mô hình dữ liệu ứng dụng. |
| “Thiếu index thì dùng `ALLOW FILTERING`.” | Phải xem lại access pattern và thiết kế partition trước tiên. |

## 9. Tự kiểm tra hiểu bài

**Câu 1.** Một trang cần lấy 20 đơn mới nhất theo khách hàng. Chỉ có bảng `orders_by_id` với `order_id` làm primary key. Có nên viết một repository method `findByCustomerId` và kỳ vọng Cassandra tự tối ưu không?

*Gợi ý:* Không. Cần bảng hoặc đường truy cập được thiết kế theo `customer_id`, có clustering để phục vụ thứ tự thời gian; kiểm soát kích thước partition.

**Câu 2.** Trong một method, chương trình tìm `OrderById`, gọi `setStatus("PAID")` rồi trả về mà không `save()`. Database có đổi không?

*Gợi ý:* Không có dirty checking kiểu JPA; thay đổi chỉ nằm trong đối tượng Java trừ khi có thao tác ghi tường minh ở nơi khác.

**Câu 3.** Sau khi ghi thành công `orders_by_id`, ghi `orders_by_customer` thất bại. Thêm `@Transactional` có giải quyết triệt để không?

*Gợi ý:* Không. Cần thiết kế retry idempotent, cơ chế đối soát và ngữ nghĩa nhất quán có thể chấp nhận được; cân nhắc ràng buộc giao dịch của nghiệp vụ.

**Câu 4.** Hai yêu cầu cùng cố đổi trạng thái `NEW` sang `PAID`. Làm sao tránh cả hai cùng coi thao tác là “lần chuyển thành công” trên một row?

*Gợi ý:* Có thể dùng CQL conditional update `IF status = 'NEW'` (LWT), kiểm tra `[applied]` và đánh giá chi phí tranh chấp.

**Câu 5.** Vì sao `SELECT ... WHERE customer_id = ? LIMIT 20` có thể hiệu quả trên `orders_by_customer`, nhưng `SELECT ... WHERE status = 'PAID'` chưa chắc hiệu quả?

*Gợi ý:* Truy vấn đầu xác định partition key và tận dụng clustering; truy vấn thứ hai không chỉ ra partition key tương ứng.

## Kết luận

Spring Data Cassandra vẫn hỗ trợ entity, repository và template giống phong cách Spring Data, nhưng **không kế thừa các bảo đảm của JPA**. Khi dùng Cassandra, câu hỏi ưu tiên là: “Ứng dụng sẽ truy vấn dữ liệu này bằng khóa nào, dữ liệu được phân bố ra sao, và những bản sao của cùng thông tin sẽ được đồng bộ thế nào?”. Trả lời được các câu hỏi đó trước khi viết annotation giúp tránh schema khó truy vấn, partition quá lớn, cập nhật thiếu nhất quán và các kỳ vọng sai về giao dịch.

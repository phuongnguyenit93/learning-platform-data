# Giả định ORM loại bỏ nhu cầu hiểu truy vấn và giao dịch

ORM (*Object–Relational Mapping*) giúp Java developer làm việc với dữ liệu quan hệ qua entity, repository và object graph. Với Spring Data JPA và Hibernate, một số thao tác rất ngắn: gọi `findById(...)` để tải một đối tượng, sửa thuộc tính rồi để cơ chế *dirty checking* đồng bộ thay đổi; hoặc gọi `saveAll(...)` để ghi danh sách entity. Sự tiện lợi đó dễ tạo ra giả định nguy hiểm: **“Đã dùng ORM thì không cần hiểu SQL, transaction, isolation hoặc cách database vận hành nữa.”**

Giả định này sai vì ORM **không thay thế cơ sở dữ liệu**. Nó chuyển các thao tác Java thành SQL và điều phối trạng thái entity; DBMS vẫn thực thi truy vấn, chọn execution plan, áp ràng buộc, cấp khóa, quản lý transaction log, cache và tính bền vững. Nếu không hiểu những lớp bên dưới, ứng dụng có thể đúng trong unit test nhưng bị N+1 queries, giữ transaction quá lâu, lost update, deadlock, tạo hàng trùng, gọi mạng trong transaction hoặc ghi dữ liệu sai mà không nhận exception.

Bài thuộc chương **Lỗi thiết kế** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Phạm vi liên quan trực tiếp tới ranh giới persistence trong Java: mô hình dữ liệu, lược đồ, truy vấn, chỉ mục, transaction/isolation, kiểm soát đồng thời, tài nguyên kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng.

Mục tiêu không phải phủ nhận ORM. ORM hữu ích với những nghiệp vụ phù hợp, nhưng **ORM nên là công cụ triển khai một thiết kế persistence đã hiểu rõ**, chứ không phải nguồn quyết định duy nhất về cấu trúc dữ liệu, transaction và hành vi SQL.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ORM chuyển đổi giữa object model và relational model, đồng thời chỉ rõ trách nhiệm vẫn thuộc DBMS.
2. Phân biệt `EntityManager.persist()`, `merge()`, `flush()`, `clear()`, `commit()` và thao tác thực sự trên connection.
3. Nhận biết N+1, eager fetching quá mức, cartesian explosion và các vấn đề phân trang.
4. Đọc SQL do ORM phát sinh, đánh giá index/selectivity/`EXPLAIN` và xác nhận số round-trip.
5. Xác định ranh giới transaction ở thao tác nghiệp vụ thay vì dựa vào từng repository method.
6. Hiểu các bẫy `@Transactional` trong Spring: proxy, self-invocation, exception rollback, propagation và `readOnly`.
7. Phân tích isolation, optimistic/pessimistic locking, lost update và các bất biến cần constraint ở DB.
8. Hiểu tại sao batch, bulk JPQL, ID generation và persistence context có ảnh hưởng đến hiệu năng và tính đúng.
9. Thiết kế retry/idempotency và xử lý tác dụng phụ ngoài database bằng transactional outbox khi phù hợp.
10. Viết integration tests trên DBMS thật để kiểm chứng SQL, transaction, ràng buộc và đồng thời, không chỉ mock repository.

## 2. ORM thực sự làm gì và không làm gì?

### 2.1. ORM là lớp ánh xạ và quản lý trạng thái

Một entity JPA minh họa:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private int stock;

    protected Product() {}

    public Product(Long id, String name, int stock) {
        this.id = id;
        this.name = name;
        this.stock = stock;
    }

    public Long getId() { return id; }
    public int getStock() { return stock; }
    public void setStock(int stock) { this.stock = stock; }
}
~~~

ORM biết quan hệ cơ bản giữa class `Product` và bảng `products`; nó có thể nạp object từ row, theo dõi thay đổi của managed entity, rồi sinh SQL tương ứng.

Đường đi điển hình:

~~~mermaid
flowchart TD
    A["Use case Java / application service"] --> B["Repository / EntityManager"]
    B --> C["JPA provider: mapping, persistence context, dirty checking"]
    C --> D["JDBC driver / DataSource / connection pool"]
    D --> E["DBMS SQL parser, optimizer và execution engine"]
    E --> F["Index / row locks / constraints / WAL / storage"]
    F --> E
    E --> D
    D --> C
    C --> A
~~~

Những thứ ORM thường hỗ trợ:

- Ánh xạ bảng/cột/khóa thành entity và quan hệ.
- Theo dõi trạng thái object trong persistence context.
- Sinh và bind SQL cho các thao tác CRUD.
- Hỗ trợ query qua JPQL/Criteria/repository conventions.
- Điều phối cascade, entity lifecycle, optimistic versioning theo cấu hình.
- Có thể hỗ trợ batching, fetch planning và một số cơ chế cache.

Những thứ ORM **không tự động giải quyết đúng cho mọi trường hợp**:

- Chọn đúng mô hình dữ liệu và bất biến nghiệp vụ.
- Biết một lần xử lý nghiệp vụ cần commit những bảng nào cùng nhau.
- Tự tạo index tối ưu cho workload thực.
- Ngăn mọi trường hợp lost update hoặc write skew.
- Bảo đảm event/HTTP/payment cùng rollback với database.
- Hiểu những dữ liệu lịch sử có format cũ hoặc schema migration dở dang.
- Tự phát hiện bản ghi duplicate do request retry sau commit không rõ kết quả.
- Quyết định transaction nào nên dùng `READ COMMITTED` hay `SERIALIZABLE`.
- Bảo vệ connection pool trước một giao dịch giữ connection quá lâu.

### 2.2. Entity là object, bảng là tập bản ghi quan hệ

Trong Java, truy cập `order.getCustomer().getName()` giống thao tác với object ở bộ nhớ. Nhưng `customer` có thể là lazy proxy và thao tác gọi getter sẽ kích hoạt câu `SELECT` thứ hai, phụ thuộc trạng thái session.

Ngược lại, một câu SQL:

~~~sql
SELECT o.id, c.display_name
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
WHERE o.status = 'PAID';
~~~

có thể lấy một projection cho hàng nghìn đơn trong một lượt đi database. Không có quy tắc “object access tự nhiên = truy cập dữ liệu hiệu quả”. Object graph và relational result set có hình thức tối ưu khác nhau.

### 2.3. Repository interface không thay đổi chi phí vật lý

Ví dụ Spring Data:

~~~java
public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    List<OrderEntity> findByStatus(String status);
}
~~~

Tên method rất ngắn, nhưng:

- Kết quả có thể gồm hàng trăm nghìn entity.
- Mỗi association bị truy cập có thể sinh SELECT bổ sung.
- Không có paging hoặc giới hạn tập trả về.
- Cột `status` có thể không có index phù hợp.
- ORM có thể giữ toàn bộ entity trong persistence context.
- Query có thể đụng tranh chấp tài nguyên với transaction khác.

Vì vậy câu hỏi đúng không phải “có dùng repository method tiện không?” mà là **“SQL nào được thực thi, trả về bao nhiêu row, giữ những tài nguyên nào, và bảo toàn invariant nào?”**

## 3. Sai lầm 1: Không đọc SQL vì ORM đã sinh hộ

### 3.1. Một lệnh Java có thể phát sinh nhiều SQL

Ví dụ lấy danh sách đơn rồi in tên khách hàng:

~~~java
List<OrderEntity> orders =
    orderRepository.findByStatus("PAID");

for (OrderEntity order : orders) {
    System.out.println(order.getCustomer().getDisplayName());
}
~~~

Nếu quan hệ `customer` được lazy load và mỗi order tham chiếu một khách chưa nạp, ORM có thể phát:

~~~sql
SELECT * FROM orders WHERE status = 'PAID';

SELECT * FROM customers WHERE id = ?;
SELECT * FROM customers WHERE id = ?;
SELECT * FROM customers WHERE id = ?;
-- ... lặp cho những customer khác chưa nạp.
~~~

Đây là vấn đề **N+1 query**: một query lấy danh sách, N query tiếp theo lấy association. Số query thực phụ thuộc số customer khác nhau, persistence context, cache, cấu hình fetch và truy cập của code.

Một quy trình có 10 đơn chạy ổn trong test; với 10.000 đơn có thể tạo hàng nghìn lượt đi-về mạng và tải connection/DB tăng đáng kể.

### 3.2. Cách sửa phụ thuộc use case

Nếu API chỉ cần `id` đơn và tên khách hàng, projection với JOIN thường phù hợp:

~~~java
public record OrderSummary(Long id, String customerName) {}

@Query("""
    select new com.example.OrderSummary(
        o.id, c.displayName
    )
    from OrderEntity o
    join o.customer c
    where o.status = :status
    """)
List<OrderSummary> findSummaries(@Param("status") String status);
~~~

Đây là đoạn minh họa trong một interface repository phù hợp; package `com.example.OrderSummary`, mapping `customer` và các import phải có trong dự án thật.

Nếu cần cả entity và association để chạy một use case, có thể xem xét:

- `JOIN FETCH` với quan hệ phù hợp.
- `@EntityGraph` cho fetch plan ở query cụ thể.
- Batch fetching của Hibernate.
- Một hoặc nhiều query theo tập ID, ghép dữ liệu ở application service.
- DTO projection thay vì materialize toàn bộ aggregate.

**Không có một cách luôn tốt nhất.** Với quan hệ collection, fetch join nhiều collection có thể nhân số hàng được trả về, tốn băng thông và memory hoặc gây rủi ro phân trang.

### 3.3. EAGER không phải “nút sửa N+1”

Giải pháp thiếu cân nhắc thường là đổi mọi quan hệ sang `FetchType.EAGER`. Điều này không nhất thiết loại N+1: provider có thể dùng nhiều SELECT để đáp ứng eager association, và query nào cũng tải dữ liệu dù endpoint không cần.

Một endpoint tìm danh sách đơn chỉ cần số tiền có thể kéo theo cả khách hàng, địa chỉ, lịch sử thanh toán và sản phẩm. Băng thông, memory và persistence context phình ra.

Nên thiết kế fetch plan **theo thao tác sử dụng dữ liệu**, không cố mô phỏng toàn bộ object graph bằng một câu SQL khổng lồ cho mọi request.

### 3.4. Query count là một tín hiệu, không phải chỉ số duy nhất

Hai query lớn làm JOIN sai có thể tệ hơn mười query nhỏ, tùy dữ liệu và index. Cần đo:

- Số SQL/round trips.
- Số row và byte được trả về.
- Thời gian thực thi, p95/p99.
- CPU, I/O, sort, temporary files.
- Lock wait và thời gian transaction.
- JVM heap/GC, số entity được materialize.

Mục tiêu là **đúng và hiệu quả trên workload**, không phải đạt một số query thấp nhất bằng mọi giá.

## 4. Sai lầm 2: Tin rằng query method tự chọn execution plan đúng

ORM phát SQL nhưng **DBMS optimizer** quyết định phần lớn cách thực thi. Hai câu JPQL trông giống nhau có thể tạo plan khác biệt do thống kê, index, dữ liệu skew và bind parameters.

### 4.1. Ví dụ tìm kiếm theo tenant

~~~sql
SELECT id, created_at, amount
FROM orders
WHERE tenant_id = ?
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

Để đánh giá truy vấn này cần hiểu:

- Có index hỗ trợ điều kiện lọc/`ORDER BY` không?
- Phân bố `tenant_id` và `status` ra sao?
- `LIMIT 50` có giảm công việc hay DB vẫn cần scan/sort lớn?
- Có truy vấn cần cả hàng sau khi tìm index không?
- Các row trả về có nhiều payload lớn không?
- Có khác biệt giữa tenant rất lớn và tenant nhỏ không?

Một index composite minh họa:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
~~~

Index này **có thể** phù hợp cho mẫu truy vấn trên nhưng không tự luôn tối ưu. Nó tốn chi phí insert/update/delete và dung lượng; hiệu quả phải được đo cùng các truy vấn thực khác.

### 4.2. Đọc plan thay vì đoán

PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
~~~

`EXPLAIN ANALYZE` **thực thi truy vấn** để lấy số đo, nên cần cảnh giác với DML hoặc query đắt trên production. Dùng môi trường/tập dữ liệu được phê duyệt và giới hạn thời gian/tài nguyên.

Đọc các tín hiệu:

- `Seq Scan`, `Index Scan`, `Bitmap Heap Scan` có phù hợp quy mô?
- Estimated rows và actual rows chênh lệch lớn không?
- Sort, hash join và temporary I/O tốn bao nhiêu?
- Buffer hits/reads và actual execution time?
- Lọc sau scan làm loại nhiều hàng không?
- Có index/partition đúng với phân bố và điều kiện không?

Không đưa một assertion cứng “query phải luôn dùng index scan” vào unit test. Query plan phụ thuộc dữ liệu, statistics và engine version. Nên quản lý SLO/chi phí và regression test tương ứng.

### 4.3. ORM không thay database schema migration

Cấu hình Hibernate auto-DDL có thể tạo hoặc cập nhật schema trong vài môi trường, nhưng nó không biết:

- Dữ liệu lịch sử có thỏa `NOT NULL` mới không.
- Một `ALTER COLUMN` có rewrite bảng lớn không.
- Có rolling deployment cần giữ cột cũ không.
- Một đổi kiểu tiền có mất precision không.
- DDL nào giữ lock làm gián đoạn API.
- Backfill nào cần batch, checkpoint và audit.

Production nên dùng migration versioned có review, rehearsal và kiểm chứng dữ liệu. ORM mapping và schema validation là hai lớp hỗ trợ, không thay chiến lược tiến hóa dữ liệu.

## 5. Sai lầm 3: Nhầm entity state với SQL và COMMIT

### 5.1. Persistence context và vòng đời entity

Trong JPA, entity có thể ở trạng thái:

- **New/transient:** object mới chưa được quản lý.
- **Managed:** gắn với một persistence context; provider có thể theo dõi biến đổi.
- **Detached:** không còn được context quản lý.
- **Removed:** được đánh dấu để xóa theo lifecycle.

Các lời gọi khác nhau có tác dụng khác nhau:

| Thao tác | Ý nghĩa chính | Không đồng nghĩa |
|---|---|---|
| `persist(entity)` | Đưa entity mới vào trạng thái managed và lên lịch INSERT | Đã commit vào DB |
| Thay đổi field managed | Dirty checking có thể sinh UPDATE khi flush | UPDATE xảy ra ngay tại setter |
| `merge(entity)` | Sao chép trạng thái detached vào managed instance | Detached object tự trở thành managed, hoặc không thể ghi đè dữ liệu mới |
| `flush()` | Đồng bộ thay đổi pending xuống DB trong transaction | `commit()` |
| `clear()` | Detach managed entities khỏi context | Rollback hoặc xóa dữ liệu |
| `remove(entity)` | Đánh dấu xóa managed entity | Dữ liệu đã mất bền vững ngay |
| Transaction `commit` | Kết thúc thành công transaction theo DBMS | Tất cả hệ bên ngoài cũng đã commit |

Một thao tác `repository.save(...)` có thể gọi `persist` hoặc `merge` tùy cách repository xác định entity mới/cũ. Nó không phải một primitive “upsert an toàn và atomic trên mọi DBMS”.

### 5.2. Flush có thể xảy ra sớm hơn dự đoán

Ví dụ:

~~~java
@Transactional
public void updateAndRead(long productId) {
    Product product = entityManager.find(Product.class, productId);
    product.setStock(product.getStock() - 1);

    // Tùy flush mode và provider, query sau có thể kích hoạt flush.
    long remaining = entityManager.createQuery(
        "select count(p) from Product p", Long.class
    ).getSingleResult();
}
~~~

Dù không gọi `save`, một managed entity bị sửa có thể được UPDATE khi flush. Provider có thể flush trước một query cần dữ liệu đồng bộ hoặc khi commit, tùy flush mode/JPQL/native query/provider.

Hệ quả:

- Lỗi constraint có thể xuất hiện tại `flush`, trước query hoặc lúc commit, không nhất thiết tại setter.
- SQL update có thể gửi trước cuối method nhưng chưa commit.
- Khi transaction rollback, những SQL đã flush vẫn phải bị đảo theo cơ chế DB.
- Test mock repository không quan sát đúng timing của flush/constraint.

### 5.3. `flush()` không phải bằng chứng dữ liệu đã bền vững

~~~text
BEGIN
  persist(order)
  flush()          -> INSERT được gửi; transaction chưa commit
  persist(outbox)
  flush()
  COMMIT           -> DB xác nhận transaction thành công
~~~

Nếu `COMMIT` không thành công, hai INSERT trước có thể rollback. Nếu mạng đứt quanh `COMMIT`, caller có thể không biết chắc nó đã commit hay chưa.

Cần log và thiết kế idempotency theo **kết quả nghiệp vụ đã xác nhận**, không mặc định thấy SQL trong log là dữ liệu đã bền vững.

### 5.4. `merge` và stale object

Một entity detached được tải từ phiên bản cũ có thể chứa state lỗi thời. Nếu gọi `merge` mà không có cơ chế kiểm soát version/điều kiện ghi, các thuộc tính cũ có thể ghi đè thay đổi mới.

Khi cần bảo vệ concurrent updates:

- Dùng `@Version` phù hợp.
- Xây patch/update tập field thực sự thay đổi.
- Tránh nhận nguyên một entity object từ API request như nguồn sự thật.
- Kiểm tra affected row count hoặc OptimisticLockException.
- Đọc lại trạng thái khi phát hiện xung đột; không tự ghi đè.

## 6. Sai lầm 4: Mở transaction ở từng repository thay vì thao tác nghiệp vụ

Một hành động nghiệp vụ có thể cập nhật nhiều bảng. Nếu mỗi repository tự commit, một bước lỗi sẽ làm hệ thống nửa thành công.

### 6.1. Ví dụ sai: tạo đơn rồi trừ tồn kho

~~~java
public void placeOrder(OrderCommand command) {
    // Nếu mỗi lời gọi mở/commit transaction riêng:
    orderRepository.save(toEntity(command));
    inventoryRepository.decreaseStock(command.sku(), command.quantity());
    paymentRepository.recordPending(command.paymentRef());
}
~~~

Nếu bước trừ tồn kho bị lỗi vì thiếu hàng, đơn có thể đã commit trước. Nếu bước payment record bị lỗi, hai bước trước có thể đã commit. ORM không suy ra rằng ba thao tác thuộc **một use case atomic**.

### 6.2. Đặt ranh giới ở application service

~~~java
@Service
public class OrderPlacementService {
    private final OrderRepository orders;
    private final InventoryRepository inventory;
    private final PaymentRecordRepository paymentRecords;

    public OrderPlacementService(
            OrderRepository orders,
            InventoryRepository inventory,
            PaymentRecordRepository paymentRecords) {
        this.orders = orders;
        this.inventory = inventory;
        this.paymentRecords = paymentRecords;
    }

    @Transactional
    public void placeOrder(OrderCommand command) {
        int changed = inventory.decreaseIfEnough(
            command.sku(), command.quantity()
        );

        if (changed != 1) {
            throw new InsufficientStockException(command.sku());
        }

        orders.save(OrderEntity.from(command));
        paymentRecords.save(PaymentRecord.pending(
            command.paymentRef()
        ));
    }
}
~~~

Đoạn trên là **khung kiến trúc**, cần định nghĩa các class/repository và cấu hình Spring đầy đủ. Nó giả định cả ba repository dùng cùng database/transaction manager; payment record là **ghi nội bộ**, không phải gọi thu tiền thật ở hệ thống bên ngoài.

Nếu toàn bộ thao tác cùng nằm trong một transaction DB hợp lệ, lỗi runtime có thể làm rollback các thay đổi theo rollback rules của framework. Tuy nhiên cũng cần xử lý lỗi ở commit, dữ liệu trùng và ranh giới tài nguyên ngoài DB.

### 6.3. SQL cập nhật tồn kho có điều kiện

Một cách diễn đạt invariant “không âm tồn kho” tại DB:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE sku = :sku
  AND available >= :quantity;
~~~

Ký hiệu `:quantity` và `:sku` dành cho framework hỗ trợ named parameters (ví dụ Spring/JPA); JDBC `PreparedStatement` thuần dùng `?`.

Nếu affected-row count = 1, hàng có tồn kho đủ tại thời điểm cập nhật theo cơ chế isolation/locking của DBMS. Nếu 0, sản phẩm không tồn tại hoặc tồn kho không đủ; ứng dụng phải trả lỗi đúng ngữ nghĩa. Database cũng nên có constraint bảo vệ:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT inventory_available_nonnegative
CHECK (available >= 0);
~~~

Không chỉ viết:

~~~java
Inventory inventory = repository.findBySku(sku);
if (inventory.getAvailable() >= quantity) {
    inventory.setAvailable(inventory.getAvailable() - quantity);
}
~~~

mà mặc định không có race khi hai transaction cùng đọc `available` cũ.

### 6.4. Một transaction cực dài cũng là lỗi

Không nên giữ transaction mở xuyên suốt một HTTP request dài hoặc vòng gọi dịch vụ bên ngoài:

~~~text
BEGIN
  SELECT và lock rows
  Gọi HTTP payment provider (có thể 5–30 giây)
  Gửi email
  UPDATE orders
COMMIT
~~~

Trong lúc chờ network, transaction có thể giữ row locks, connection và MVCC snapshot; timeout hoặc retry làm tải database tăng.

Nên định nghĩa transaction ngắn quanh thao tác cần atomic tại DB, tách side effect ngoài DB qua workflow/outbox/saga phù hợp.

## 7. Sai lầm 5: Tin `@Transactional` là “bùa an toàn”

`@Transactional` rất hữu ích, nhưng phải hiểu **transaction manager, proxy, thread, propagation, isolation và rollback rules**. Annotation không bảo đảm mọi lời gọi method trong Java đều tự động được bao bởi transaction.

### 7.1. Self-invocation có thể bỏ qua proxy

Ví dụ cơ bản trong mô hình Spring proxy:

~~~java
@Service
public class BatchService {
    public void run() {
        // Lời gọi qua this không đi qua transactional proxy.
        this.processChunk();
    }

    @Transactional
    public void processChunk() {
        // Có thể không mở transaction mới như tác giả kỳ vọng.
    }
}
~~~

Spring transaction interception ở chế độ proxy thông thường xảy ra khi lời gọi đi **qua proxy**. Lời gọi nội bộ qua `this` không được intercept, trừ khi dùng cơ chế khác được cấu hình có chủ đích.

Giải pháp điển hình:

- Tách `processChunk` sang một bean/service khác và gọi qua Spring bean.
- Dùng `TransactionTemplate` cho ranh giới được điều khiển bằng code.
- Hoặc thiết kế transaction boundary trên public method được gọi từ ngoài proxy.

Không lách bằng cách thêm annotation lên mọi private helper rồi mặc định nó hoạt động.

### 7.2. Checked exception và rollback

Trong Spring transaction mặc định phổ biến:

- `RuntimeException` và `Error` dẫn đến rollback.
- Checked exception thường **không tự động** làm rollback nếu không có cấu hình/rule bổ sung.

Ví dụ:

~~~java
@Transactional(rollbackFor = BusinessValidationException.class)
public void importOrder(OrderCommand command)
        throws BusinessValidationException {
    // ...
}
~~~

`BusinessValidationException` ở ví dụ phải là kiểu exception được định nghĩa phù hợp. Nếu service bắt exception rồi nuốt, transaction interceptor có thể thấy method kết thúc bình thường và commit, trừ khi transaction đã được đánh dấu rollback-only hoặc DB đã ở trạng thái lỗi.

Test không nên suy ra “đã ném bất kỳ exception nào cũng rollback”. Hãy kiểm tra dữ liệu thực sau lỗi.

### 7.3. `readOnly = true` không phải quyền bảo mật read-only

~~~java
@Transactional(readOnly = true)
public OrderDetail loadOrder(long id) {
    // ...
}
~~~

`readOnly=true` là một **hint/cấu hình transaction** mà framework/driver/provider có thể tối ưu theo cách riêng, chẳng hạn thay flush behavior. Nó không tự thay quyền SQL của DB user và không phải cơ chế bảo mật chắc chắn ngăn lệnh UPDATE trên mọi backend.

Nếu cần thật sự cấm ghi, dùng role database có quyền chỉ đọc hoặc enforcement của hạ tầng, kết hợp test trên DBMS thật.

### 7.4. Transaction thường gắn với thread/context hiện tại

Một lời gọi `@Async`, `CompletableFuture` hoặc thread mới **không mặc nhiên kế thừa transaction JPA/JDBC** của thread hiện tại. Các công nghệ reactive có cơ chế propagation khác, cần dùng transaction manager tương ứng.

Không bắt một thread chạy query lazy/ghi dữ liệu rồi kỳ vọng nó dùng cùng session và rollback với thread khác. Thiết kế mỗi tác vụ async có transaction riêng và cơ chế phối hợp rõ.

## 8. Hiểu transaction propagation trước khi tách service

Hai method cùng có `@Transactional` không có nghĩa chúng luôn có hai transaction độc lập. Trong Spring, propagation quyết định method được gọi sẽ tham gia transaction hiện có hay tạo scope khác.

### 8.1. Những propagation thường gặp

| Propagation | Ý nghĩa khái quát | Rủi ro khi hiểu sai |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện có; nếu không có thì tạo mới | Tưởng method con luôn commit riêng |
| `REQUIRES_NEW` | Tạm treo transaction hiện có và bắt đầu transaction độc lập | Ghi audit commit dù nghiệp vụ chính rollback; cần thêm connection |
| `NESTED` | Có thể dùng savepoint trong transaction hiện tại khi manager hỗ trợ | Tưởng là một transaction hoàn toàn độc lập |
| `SUPPORTS` | Tham gia nếu có, nếu không thì chạy không có transaction theo cách framework quản lý | Code có hành vi khác tùy caller |
| `MANDATORY` | Yêu cầu transaction hiện có | Gọi ngoài transaction sẽ thất bại |
| `NOT_SUPPORTED` | Chạy ngoài transaction, tạm treo nếu đang có | Đọc/ghi không nằm trong atomic boundary dự kiến |

Không giả định `NESTED` được mọi transaction manager, provider và DBMS hỗ trợ giống nhau. Đặc biệt, savepoint cho JDBC transaction không tự có nghĩa mọi trạng thái managed entity trong ORM được rollback về đúng snapshot trước savepoint.

### 8.2. Ví dụ `REQUIRES_NEW` có thể phá invariant

~~~java
@Service
public class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordOrderAttempt(long orderId) {
        auditRepository.save(new AuditEntry(orderId));
    }
}
~~~

Giả sử outer transaction bắt đầu tạo đơn rồi gọi audit. Nếu audit commit thành công nhưng outer transaction rollback, ta có audit record về đơn **chưa tồn tại**. Điều đó có thể hợp lệ nếu audit chỉ mang nghĩa “có lần thử tạo đơn”, nhưng sai nếu dữ liệu audit được diễn giải là “đơn đã được tạo thành công”.

Vì vậy cần định nghĩa ngữ nghĩa của mỗi bảng và transaction. Không dùng `REQUIRES_NEW` như mẹo “tránh lỗi rollback-only” khi chưa hiểu side effect.

Ngoài ra, một outer transaction đã giữ connection; tạo transaction mới có thể cần một connection khác. Nếu quá nhiều request đều dùng `REQUIRES_NEW` trong pool nhỏ, các thread có thể chờ connection và làm hệ thống nghẽn.

### 8.3. `UnexpectedRollbackException` không phải lỗi ngẫu nhiên

Một method con dùng propagation `REQUIRED` có thể đánh dấu transaction chung là rollback-only sau khi gặp lỗi. Nếu outer method bắt exception rồi tiếp tục và cố commit, framework có thể báo `UnexpectedRollbackException`.

Đây là tín hiệu **transaction đã bị đánh dấu không thể commit đúng**, không nên “fix” bằng cách nuốt exception ở nơi khác. Cần điều chỉnh ranh giới, rollback policy hoặc tách nghiệp vụ có lý do rõ.

### 8.4. Transaction boundary và phần mềm phân tán

~~~mermaid
flowchart LR
    A["HTTP request / use case"] --> B["Application service @Transactional"]
    B --> C["Order repository"]
    B --> D["Inventory repository"]
    B --> E["Outbox repository"]
    C --> F["Cùng DB transaction"]
    D --> F
    E --> F
    F --> G["Commit"]
    G --> H["Outbox publisher"]
    H --> I["Broker / external consumer"]
~~~

Ba thao tác ghi tại DB có thể commit nguyên tử khi dùng cùng transaction manager và nguồn kết nối phù hợp. Nhưng publisher và broker **không** được bao bởi DB transaction chỉ vì nằm trong cùng một method Java.

## 9. Sai lầm 6: Tưởng isolation tự ngăn mọi race

Transaction giúp gom thao tác atomic, nhưng isolation quyết định transaction được quan sát những thay đổi đồng thời như thế nào. ORM không tự chuyển toàn bộ hoạt động thành tuần tự hóa theo nghiệp vụ.

### 9.1. Lost update khi đọc–sửa–ghi

Giả sử tồn kho ban đầu 10:

~~~text
T1: SELECT available FROM inventory WHERE sku='A' -> 10
T2: SELECT available FROM inventory WHERE sku='A' -> 10
T1: available = 10 - 7 -> UPDATE available=3
T2: available = 10 - 6 -> UPDATE available=4

Kết quả cuối: 4, trong khi đã xử lý tổng 13 đơn vị.
~~~

Lịch chạy trên chỉ minh họa một trường hợp khi các transaction không có cơ chế chống xung đột phù hợp; với khóa/isolation/ORM version khác, transaction có thể chờ hoặc bị hủy.

Nếu ứng dụng chỉ làm `entity.setAvailable(entity.getAvailable() - quantity)`, ORM có thể sinh UPDATE với giá trị được tính từ snapshot cũ. Một transaction riêng cho từng request **không tự bảo đảm** logic tồn kho đúng.

### 9.2. Cập nhật có điều kiện tại database

~~~sql
UPDATE inventory
SET available = available - ?
WHERE sku = ?
  AND available >= ?;
~~~

Ở đây các placeholder được bind bằng JDBC. Nếu affected rows = 1, thao tác đã trừ khi đủ tại thời điểm thực hiện cập nhật theo cơ chế khóa/serialization của DB. Nếu = 0, không được tiếp tục tạo order như đã giữ hàng.

Kết hợp:

- Constraint `CHECK (available >= 0)`.
- Transaction chung cho trừ tồn kho và tạo order.
- Unique/idempotency key tránh request trùng.
- Locking/isolation và retry phù hợp cho logic nhiều hàng.

Một câu UPDATE có điều kiện không giải quyết tất cả bài toán reservation hoặc nhiều kho: cần thiết kế invariant thực và điều kiện khóa.

### 9.3. Optimistic locking qua `@Version`

~~~java
@Entity
@Table(name = "products")
public class ProductEntity {
    @Id
    private Long id;

    @Version
    private Long version;

    private String name;

    private int stock;

    protected ProductEntity() {}
}
~~~

Với optimistic locking của provider, câu UPDATE thường có điều kiện version tương đương:

~~~sql
UPDATE products
SET stock = ?, version = ?
WHERE id = ?
  AND version = ?;
~~~

Nếu một transaction khác đã cập nhật version, ảnh hưởng 0 hàng có thể dẫn đến `OptimisticLockException` hoặc exception tương ứng theo provider.

Nhưng cần biết:

- `@Version` chỉ hoạt động trên **đường cập nhật do ORM quản lý tương ứng**.
- Native SQL, JPQL bulk update hoặc script migration có thể không tự tăng/so version.
- Retry phải đọc lại trạng thái, chạy lại **toàn use case** và kiểm tra điều kiện nghiệp vụ, không đơn giản gọi lại setter với snapshot cũ.
- Versioning trên một entity không tự bảo vệ invariant liên quan nhiều row khác.

### 9.4. Pessimistic locking

Khi cần khóa một hàng trước khi ra quyết định, JPA có thể cung cấp lock mode như `PESSIMISTIC_WRITE`, thường ánh xạ đến cơ chế khóa DB tương ứng:

~~~java
ProductEntity product = entityManager.find(
    ProductEntity.class,
    productId,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Nhưng phải xác minh SQL và khả năng hỗ trợ của provider/DBMS; thời gian giữ khóa, deadlock, lock wait và transaction boundary vẫn rất quan trọng.

Đừng khóa trước một lời gọi HTTP kéo dài hoặc truy vấn liên quan nhiều dữ liệu không cần thiết. Một transaction giữ khóa lâu có thể chặn hàng loạt request khác.

### 9.5. Write skew và bất biến nhiều hàng

Giả sử hai bác sĩ trực; quy tắc: luôn phải còn ít nhất một người trực. T1 kiểm tra “còn 2 người” rồi cho A nghỉ; T2 cũng kiểm tra “còn 2 người” rồi cho B nghỉ. Hai transaction cập nhật **hai hàng khác nhau** nên optimistic version trên từng hàng có thể không phát hiện xung đột, cuối cùng không ai trực.

Đây là ví dụ kinh điển về **write skew** ở một số mức isolation và lịch chạy. Cần thiết kế bảo vệ invariant ở mức phù hợp:

- Transaction isolation mạnh hơn (ví dụ `SERIALIZABLE` với xử lý retry).
- Khóa một hàng tổng hợp/coordination row làm điểm đồng bộ khi hợp lý.
- Constraint/trình bày dữ liệu khác giúp DB trực tiếp bảo vệ quy tắc.
- Một workflow serialized theo khóa nghiệp vụ.

Không chỉ thêm `@Version` vào từng entity rồi kết luận mọi rule liên bảng đã được bảo vệ.

### 9.6. Isolation được cấu hình nhưng không có nghĩa giống nhau mọi nơi

Tên `READ_COMMITTED`, `REPEATABLE_READ` và `SERIALIZABLE` có quy tắc DBMS-specific. Ví dụ PostgreSQL sử dụng MVCC và có những bảo đảm/đặc tính riêng, trong khi MySQL/InnoDB có cơ chế gap/next-key locks và defaults khác.

`@Transactional(isolation = Isolation.SERIALIZABLE)` chỉ có ý nghĩa nếu transaction manager/driver/DBMS áp dụng thật. Cần test lịch chạy của các transaction có tranh chấp trên engine/phiên bản production và xử lý serialization failures bằng **retry transaction có kiểm soát**, không giả định mức cao luôn loại bỏ mọi lỗi hệ thống.

## 10. Sai lầm 7: Bỏ constraint vì đã validate bằng Java

### 10.1. Java validation không phải hàng rào duy nhất

Bean Validation và điều kiện trong service rất hữu ích cho phản hồi lỗi người dùng. Nhưng dữ liệu có thể đi vào DB qua:

- Batch import hoặc ETL.
- Admin SQL/maintenance job.
- Một microservice khác.
- Phiên bản ứng dụng cũ còn chạy.
- Retry/bug của worker.
- Một lỗi race vượt qua check–then–act.

Nếu quy tắc thực sự là bất biến dữ liệu có thể kiểm tra ở DB, nên dùng constraint thích hợp.

Ví dụ:

~~~sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES users(id),
    total_amount NUMERIC(14,2) NOT NULL CHECK (total_amount >= 0),
    currency VARCHAR(3) NOT NULL
);
~~~

Bảng này không giải quyết mọi rule nghiệp vụ, nhưng bảo vệ `NOT NULL`, `UNIQUE`, `FOREIGN KEY` và `CHECK` kể cả khi không đi qua Java.

### 10.2. Check–then–insert không thay unique

Cách dễ sai:

~~~java
if (!userRepository.existsByEmail(email)) {
    userRepository.save(new UserEntity(email));
}
~~~

Hai request có thể cùng thấy “chưa tồn tại”, rồi cùng INSERT. Nếu không có unique constraint, có thể tạo duplicate.

Giải pháp thường:

1. DB có unique key tương ứng với ngữ nghĩa email/domain/tenant.
2. Ứng dụng có thể check trước để báo lỗi thân thiện nhưng không dựa vào nó để bảo đảm unique.
3. Khi DB từ chối do unique violation, ánh xạ sang kết quả nghiệp vụ thích hợp.
4. Không tự retry cùng INSERT với cùng dữ liệu như một lỗi tạm thời.
5. Nếu dùng upsert, xác định xung đột cùng ID nhưng payload khác phải xử lý thế nào.

Với hệ nhiều tenant, unique trên `email` khác unique trên `(tenant_id, email)`; index/constraint phải khớp invariant thật. Nếu dùng case-insensitive comparison, cần định nghĩa normalization/collation thay vì mặc định JPA annotation đã xử lý mọi kiểu chữ.

### 10.3. Không biến tất cả validation thành constraint

Một số điều kiện phụ thuộc hệ ngoài, thời điểm hiện tại hoặc giao dịch đa tài nguyên. DB constraint không tự kiểm tra được mọi quyền/nhân quả nghiệp vụ. Có thể cần domain validation + transaction + constraint + outbox, mỗi lớp có trách nhiệm riêng.

Nguyên tắc là **phòng vệ nhiều lớp với ngữ nghĩa nhất quán**, không chuyển mọi quy tắc vào entity annotation hoặc cố nhét toàn bộ domain logic vào một trigger.

## 11. Sai lầm 8: Coi lazy loading là chi tiết nội bộ vô hại

### 11.1. LazyInitializationException không phải lỗi “thiếu annotation”

Khi entity được load trong transaction rồi trả ra controller, persistence context có thể đã đóng. Truy cập association lazy bên ngoài context có thể gây `LazyInitializationException` trong Hibernate.

Giải pháp thiếu kiểm soát thường là bật **Open Session in View (OSIV)** hoặc đổi quan hệ sang EAGER cho toàn bộ ứng dụng. OSIV có thể làm lazy queries chạy trong lúc rendering response và che giấu chỗ phát sinh SQL, tạo thêm round trips hoặc khiến dữ liệu được đọc ngoài ranh giới transaction nghiệp vụ dự kiến. Việc session còn mở không tự đồng nghĩa một transaction vẫn bao mọi thao tác.

Đường thiết kế tốt hơn:

- Service transaction nạp đủ dữ liệu cần cho use case.
- Trả DTO/projection được thiết kế cho API.
- Dùng `EntityGraph`/fetch join hoặc query riêng khi cần.
- Không serialize trực tiếp một object graph JPA không giới hạn.
- Kiểm tra SQL khi mapping DTO để tránh N+1.

### 11.2. Serialize entity trực tiếp có rủi ro bảo mật và hiệu năng

Ví dụ trả thẳng `OrderEntity` từ REST endpoint có thể làm serializer truy cập lazy associations, sinh query bổ sung hoặc lộ field nội bộ ngoài ý muốn.

Ngay cả khi dùng annotation loại trừ JSON field, cần quản lý hợp đồng API độc lập với entity persistence. DTO rõ ràng giúp giới hạn dữ liệu trả về, bảo vệ PII, tránh vòng tham chiếu và phân biệt dữ liệu read model với những field cần cho update.

### 11.3. Eager fetch nhiều collection có thể phình dữ liệu

Một order có 10 items và 8 audit events. Query join fetch cả hai collection có thể tạo tới **80 dòng kết quả** cho cùng một order trước khi ORM de-duplicate root entity. Với nhiều order, số row tăng rất lớn.

Ngoài overhead mạng/memory, các ORM có giới hạn hoặc cảnh báo khi fetch nhiều collection, đặc biệt kiểu bag. Đừng kết luận “chỉ một SQL là tối ưu” khi SQL đó sinh cartesian multiplication.

### 11.4. Phân trang không đơn giản khi join fetch collection

Nếu cần trang 20 order, JOIN với order_items có thể trả 200 dòng. Áp `LIMIT 20` ở DB trên tập row JOIN có thể cắt giữa một order hoặc cho số root order khác mong đợi. ORM có thể cần xử lý pagination trong memory hoặc cảnh báo/fail tùy cấu hình.

Một chiến lược an toàn hơn tùy use case:

1. Trang theo **ID của root order** với index/ORDER BY ổn định.
2. Truy vấn dữ liệu cần thiết cho tập ID ở trang đó.
3. Sắp kết quả theo thứ tự trang ban đầu.
4. Nếu cần count, thiết kế count query phù hợp.
5. Kiểm tra cả khi dữ liệu thay đổi đồng thời.

Khi tập dữ liệu lớn và biến động, **keyset pagination** có thể phù hợp hơn `OFFSET`, nhưng nó đòi hỏi thứ tự/khóa ổn định và hợp đồng API rõ.

## 12. Sai lầm 9: Dùng bulk update rồi mong persistence context tự biết

### 12.1. JPQL bulk bypasses managed-entity state

Ví dụ:

~~~java
int changed = entityManager.createQuery(
    """
    update ProductEntity p
    set p.archived = true
    where p.lastSeenAt < :cutoff
      and p.archived = false
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
~~~

Bulk update có thể giúp DB xử lý cả tập mà không load từng entity. Nhưng theo semantics JPA, thao tác bulk không đồng bộ các managed entity đã có trong persistence context theo cách thông thường, và có thể không kích hoạt đầy đủ entity lifecycle callbacks/optimistic checks như update mỗi object.

Lỗi dễ gặp:

~~~text
1. Entity product 42 đang managed với archived=false.
2. Bulk JPQL cập nhật DB archived=true.
3. Java đọc lại product 42 từ persistence context -> vẫn thấy false.
4. Logic phía sau tính toán với trạng thái cũ hoặc flush đè.
~~~

Cần thiết kế `flush` trước bulk operation khi cần, sau đó `clear` hoặc `refresh` theo phạm vi phù hợp; xem xét tác động tới các entity khác đang managed. Không tự gọi `clear()` rồi bỏ mất pending changes chưa flush.

### 12.2. Bulk update và `@Version`

Một JPQL bulk UPDATE có thể không tự kiểm tra/tăng `@Version` như ORM quản lý từng entity. Nếu business invariant phụ thuộc optimistic locking, cần điều kiện version hoặc chiến lược khác, kiểm tra affected rows và race với writer đồng thời.

Đừng dùng bulk SQL cho logic có callbacks, cascade và audit per-entity bắt buộc mà không thay thế những hành vi đó bằng một cơ chế có kiểm chứng.

### 12.3. Lệnh một dòng không có nghĩa một row

Trong Spring Data JPA, method như `deleteAll()` hoặc `deleteAllInBatch()` có semantics và chi phí khác nhau. Một phương thức có thể load entity rồi xóa từng object để thực thi lifecycle, trong khi bulk delete có thể bỏ qua những callback/cascade ở tầng ORM theo cách riêng.

Trước khi dùng một API thuận tiện trên bảng lớn:

- Kiểm tra provider SQL thực sự sinh ra.
- Ước lượng số hàng và thời gian khóa.
- Xác nhận cascade/foreign key đúng.
- Có `WHERE` giới hạn phạm vi nếu nghiệp vụ yêu cầu.
- Thử rollback và xử lý stale persistence context.

## 13. Sai lầm 10: `saveAll` đồng nghĩa batch insert hiệu quả

### 13.1. ORM batching phụ thuộc driver và ID strategy

~~~java
orderItemRepository.saveAll(items);
~~~

Tên `saveAll` không bảo đảm driver gửi một batch hay một câu SQL nhiều hàng. Hibernate có cấu hình ví dụ:

~~~properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
~~~

Nhưng khả năng batch phụ thuộc statement shape, version, JDBC driver, ID generator và cách lấy generated keys.

Khi dùng `GenerationType.IDENTITY`, Hibernate thường cần INSERT sớm để có ID từ database, và điều này có thể hạn chế hoặc làm mất cơ hội JDBC INSERT batching theo cách thông thường. Sequence với cấp phát theo block hoặc ID được sinh ở application có thể cải thiện khả năng batch trong một số hệ thống, nhưng đổi ID strategy trên production đòi hỏi migration/đánh giá index, FK, ordering và storage.

### 13.2. Flush/clear giải quyết memory chứ không tự commit chunk

Một đoạn minh họa:

~~~java
@Transactional
public void persistAll(List<ProductEntity> products) {
    int i = 0;

    for (ProductEntity product : products) {
        entityManager.persist(product);
        if (++i % 100 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }
    entityManager.flush();
    entityManager.clear();
}
~~~

Điều này có thể giới hạn số managed entities trong persistence context; nhưng:

- Toàn method vẫn là **một transaction**.
- `flush` không commit mỗi 100 row.
- `clear` detach toàn bộ entity managed, không chỉ những product mới.
- `List` vẫn có thể giữ toàn bộ data trong memory.
- Nếu cần commit chunk riêng, phải thiết kế service/transaction per chunk.
- Nếu từng row có business invariant liên quan row khác, chia chunk có thể thay đổi atomicity.

### 13.3. Multi-row SQL và `COPY` có thể phù hợp hơn

Với import hàng triệu row, PostgreSQL `COPY` và staging table có thể phù hợp hơn ORM entity persistence. SQL `INSERT ... SELECT`, `UPDATE ... FROM` hoặc batch JDBC cũng có thể hiệu quả hơn trong một số workload.

Nhưng nếu có JPA entity callbacks, audit/cascade/versioning quan trọng, bỏ qua ORM phải được **thiết kế thay thế có chủ đích**, không được đánh đổi tính đúng đắn chỉ vì tốc độ.

Chọn công nghệ theo nhiệm vụ:

| Nhu cầu | Phương án đáng xem xét |
|---|---|
| CRUD aggregate có lifecycle | ORM/JPA với transaction và fetch plan rõ |
| API list chỉ cần vài trường | DTO projection, JPQL/native query |
| Bulk update có quy tắc SQL rõ | Set-based SQL/JPQL bulk có kiểm soát |
| Import lớn từ file | Staging + bulk loader, validate, merge |
| Ghi nhiều hàng cùng template | JDBC batching/Hibernate batching khi khả thi |
| Báo cáo phân tích nặng | Read model hoặc kho phân tích, query tối ưu |

**Không cần ép mọi thao tác qua một repository/entity abstraction duy nhất.** Một hệ thống có thể dùng ORM cho phần domain và SQL-centric code cho báo cáo/import nếu giữ transaction, ownership và test nhất quán.

## 14. Sai lầm 11: Coi cache ORM là nguồn dữ liệu có thẩm quyền

### 14.1. Persistence context và shared cache khác nhau

JPA first-level cache thuộc persistence context, giúp giữ một entity managed với cùng identity trong phạm vi đó. Second-level cache (nếu cấu hình) có thể chia sẻ dữ liệu giữa sessions. Query cache, Redis cache và các cache ứng dụng lại là những lớp khác.

Một dòng bị cập nhật bằng raw SQL, job ETL hoặc service khác có thể khiến entity/cache giữ dữ liệu cũ tùy transaction/isolation và cách invalidation.

Không nên kết luận:

> Đã bật second-level cache thì mọi transaction luôn thấy dữ liệu mới nhất.

### 14.2. Cache không bảo đảm distributed consistency

Khi update database và sau đó invalidate Redis/cache, có thể có khoảng thời gian hai nguồn khác nhau. Nếu transaction rollback sau khi cache đã bị xóa, hiệu năng có thể bị ảnh hưởng; nếu cache được ghi trước commit mà transaction rollback, có nguy cơ cache chứa dữ liệu chưa commit.

Một số chiến lược như cache-aside, TTL, transactional invalidation, versioned keys hoặc event-driven refresh có đặc tính consistency khác nhau. Chọn theo use case và khả năng chấp nhận stale data.

Với tồn kho, số dư, quyền truy cập, không thể chỉ đọc một cache không có cơ chế consistency phù hợp rồi commit quyết định nghiệp vụ như thể nó là trạng thái đã được khóa tại database.

### 14.3. N+1 có thể bị che bởi cache trong test

Một endpoint chạy nhanh ở local vì data đã warm cache có thể sinh N+1 khi cache lạnh hoặc khi deploy instance mới. Benchmark nên có cả warm/cold cache, cùng số SQL thực, p95/p99 và tỷ lệ cache hit ở tải phù hợp.

## 15. Sai lầm 12: ORM tự làm retry và idempotency

### 15.1. Mất kết nối quanh COMMIT

Một request đặt hàng gửi transaction COMMIT, nhưng mạng đứt trước khi client nhận phản hồi. Database có thể **đã commit hoặc chưa**. Tại Java, một `SQLException` hay exception của ORM không tự chứng minh rollback.

Nếu API retry tạo đơn với ID mới, có thể tạo đơn trùng và trừ kho hai lần. Cần operation ID/idempotency key ổn định và ràng buộc ở DB.

Một ví dụ khái niệm:

~~~sql
CREATE TABLE order_commands (
    request_id UUID PRIMARY KEY,
    payload_hash TEXT NOT NULL,
    order_id BIGINT,
    state TEXT NOT NULL
);
~~~

Trong transaction:

1. Claim `request_id` duy nhất.
2. Nếu key đã tồn tại, đối chiếu payload hash và kết quả.
3. Chỉ thực hiện nghiệp vụ khi lần xử lý được xác định là mới.
4. Ghi order, inventory, command result cùng transaction.
5. Sau commit, request lặp có thể đọc lại kết quả đã ghi.

Đây là mô hình tư duy, không phải SQL hoàn chỉnh cho đồng thời; cần thiết kế isolation/unique/locking, trạng thái đang xử lý và xử lý những transaction chưa rõ kết quả.

### 15.2. Retry cần chạy lại transaction, không tái sử dụng session lỗi

Khi gặp deadlock hoặc serialization failure, một transaction có thể bị hủy. Không tiếp tục sử dụng session với managed entities đang mang trạng thái lỗi rồi cố flush thêm.

Một retry hợp lệ thường:

- Chỉ áp dụng cho nhóm lỗi có thể retry.
- Rollback transaction đã lỗi.
- Bắt đầu transaction/persistence context mới.
- Đọc lại trạng thái và kiểm tra invariant.
- Có giới hạn số lần thử, backoff và metric.
- Tránh lặp tác dụng phụ ngoài DB.

Một unique violation do trùng business key không phải lúc nào cũng đáng retry; cần xử lý conflict theo nghĩa domain.

### 15.3. Đừng dùng catch-and-ignore để “ORM tự xử lý”

~~~java
try {
    repository.save(entity);
} catch (RuntimeException ex) {
    log.warn("Ignoring persistence error", ex);
}
~~~

Nếu lỗi xảy ra khi flush/commit sau method `save`, đoạn catch có thể thậm chí không quan sát đúng nơi phát lỗi. Nếu transaction đã rollback-only, nuốt lỗi sẽ không khiến transaction commit hợp lệ. Cần xử lý lỗi ở boundary đã hiểu transaction state, giữ cause/SQLSTATE và trả kết quả nghiệp vụ đáng tin.

## 16. Sai lầm 13: Gọi hệ thống bên ngoài trong DB transaction

Một transaction DB cục bộ chỉ bảo đảm atomicity cho những tài nguyên thực sự tham gia transaction. Gọi payment API, email, Kafka hoặc object storage từ method `@Transactional` không tự làm các tác dụng phụ đó rollback.

### 16.1. Ví dụ không an toàn

~~~java
@Transactional
public void checkout(CheckoutCommand command) {
    orderRepository.save(toOrder(command));
    paymentGateway.charge(command.paymentToken(), command.amount());
    emailGateway.sendReceipt(command.customerEmail());
}
~~~

Nếu `charge` đã thành công nhưng INSERT sau đó thất bại hoặc transaction rollback, việc charge **không được đảo** bởi DB rollback. Nếu email gửi thành công rồi commit thất bại, người nhận có thể thấy thông báo cho đơn không tồn tại.

Thêm `REQUIRES_NEW` ở một phương thức cũng không biến HTTP API thành thành viên của cùng atomic transaction.

### 16.2. Transactional outbox

Một chiến lược phổ biến là ghi order và outbox event trong cùng DB transaction:

~~~sql
BEGIN;

INSERT INTO orders (id, status) VALUES (?, 'PENDING');

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload
) VALUES (?, ?, 'OrderCreated', ?);

COMMIT;
~~~

Câu SQL minh họa sử dụng `?` placeholders theo chuẩn JDBC; việc bind và schema thực của outbox phải được định nghĩa rõ. Sau COMMIT, worker lấy event và publish tới broker.

Outbox giúp tránh tình trạng DB commit nhưng event cần publish không được lưu như một nhiệm vụ bền vững. Nhưng outbox relay có thể gửi **trùng**, nên consumer phải idempotent. Ngoài ra outbox không tự biến payment provider thành transaction chung: workflow thanh toán thường cần saga/state machine, operation ID, reconciliation và có thể có compensation.

### 16.3. Side effect phải có ranh giới và retry riêng

Đối với các API thanh toán:

- Lưu request ID/operation ID để chống gửi trùng.
- Biết khi nào trạng thái charge đã được xác nhận.
- Tránh gửi lại sau timeout khi kết quả có thể chưa rõ.
- Phối hợp payment provider qua idempotency key và truy vấn trạng thái nếu hỗ trợ.
- Đặt timeout, circuit breaker và backoff phù hợp.
- Duy trì trạng thái trung gian trong DB cho việc xử lý bất đồng bộ.

ORM giúp lưu trạng thái workflow; **nó không thiết kế workflow đúng thay developer**.

## 17. Sai lầm 14: ORM loại bỏ nhu cầu quan tâm SQL injection và phân quyền

### 17.1. Bind parameters, không nối chuỗi SQL tùy tiện

ORM thường hỗ trợ bind parameters khi dùng JPQL/Criteria/derived queries, nhưng có thể vẫn bị lỗi nếu developer tự dựng chuỗi query từ dữ liệu người dùng.

Không an toàn:

~~~java
String jpql = "select u from UserEntity u " +
    "where u.displayName = '" + userInput + "'";

entityManager.createQuery(jpql).getResultList();
~~~

Cần bind giá trị:

~~~java
List<UserEntity> users = entityManager.createQuery(
    "select u from UserEntity u where u.displayName = :name",
    UserEntity.class
)
.setParameter("name", userInput)
.getResultList();
~~~

Với native SQL qua `PreparedStatement`, dùng `?` placeholders và bind đúng thứ tự. **Parameter binding chỉ bảo vệ giá trị**, không thể bind trực tiếp tên bảng, tên cột hoặc fragment `ORDER BY`. Nếu cho người dùng chọn sort field, ánh xạ từ một allowlist các tên trường hợp lệ do code định nghĩa; không ghép SQL identifier tùy ý.

### 17.2. ORM repository không tự bảo đảm tenant isolation

Một service đa tenant:

~~~java
Optional<OrderEntity> findById(Long id);
~~~

không tự giới hạn dữ liệu theo tenant. Nếu chỉ dựa trên ID đoán được, một lỗi access control có thể trả đơn của người khác.

Cần ràng buộc quyền ở query/use case:

~~~sql
SELECT id, amount, status
FROM orders
WHERE tenant_id = ?
  AND id = ?;
~~~

Ở tầng database, row-level security hoặc cơ chế tương đương có thể tăng lớp bảo vệ, nhưng cần cấu hình role/connection state đúng và kiểm thử với pooling. Không cho rằng annotation `@Entity` hoặc Hibernate filter mặc định đủ ngăn mọi query native, job nền hoặc đường admin.

### 17.3. Entity mapping không thay được bảo mật backup

DataSource credential và connection pool phải có quyền tối thiểu. Một tài khoản ứng dụng có quyền tạo/drop mọi schema có thể làm hỏng dữ liệu khi bug hoặc xâm nhập. Migration runner và runtime service có thể cần identity khác nhau.

Nếu hệ thống sao lưu database cho kiểm thử, ORM mapping không tự làm sạch PII trong dump, event, log và search index. Dữ liệu production cần được bảo vệ ở mọi bản sao và chỉ phát hành dataset đã được sanitize theo policy.

### 17.4. Log SQL có thể tiết lộ dữ liệu

Để debug, developer thường bật SQL logging kèm bind parameters. Khi production có email, token, địa chỉ, số thẻ hoặc dữ liệu nghiệp vụ nhạy cảm, log có thể trở thành bản sao dữ liệu thứ hai.

Nên:

- Ghi SQL template, thời gian, statement ID và mã lỗi hơn là payload thô.
- Giới hạn sampling và quyền xem log chi tiết.
- Redact/băm các field được cho phép theo chính sách.
- Không in toàn bộ entity/toString trong exception log.
- Giữ SQLSTATE/vendor code và trace ID để điều tra mà không rò dữ liệu.

**Bảo mật và khả năng quan sát** phải cùng được thiết kế; không hy sinh một bên vì muốn debug N+1.

## 18. Sai lầm 15: Không tính connection pool và transaction duration

ORM che sự phức tạp của connection, nhưng mỗi query/transaction cuối cùng cần tài nguyên DB thật.

### 18.1. Một pool nhỏ và nhiều transaction chờ network

Giả sử một ứng dụng có 50 request đồng thời nhưng pool cho tối đa 10 connection. Nếu mỗi request giữ connection trong transaction 5 giây vì gọi HTTP service ngoài, throughput bị giới hạn và 40 request còn lại có thể chờ connection.

Mô hình:

~~~text
HTTP requests -> thread pool -> transaction manager
              -> HikariCP / JDBC pool (10 connections)
              -> PostgreSQL server (CPU/I/O/locks)
~~~

Nâng pool từ 10 lên 100 không tự cải thiện kết quả nếu DB đã bị quá tải. Nhiều replica với mỗi pool riêng còn có thể vượt giới hạn connection của server.

### 18.2. Tách connection acquisition khỏi transaction span

Việc Hibernate/Spring lấy connection từ pool có thể được trì hoãn tùy cấu hình, nhưng không được dựa vào chi tiết đó để cho phép transaction cực dài. Cần đo:

- Transaction duration và thời gian connection được mượn.
- Pool active/idle/pending.
- Connection acquisition timeout.
- Thời gian chờ DB lock, deadlocks.
- Query latency và DB server CPU/I/O.
- Số connection của **toàn bộ replicas**, không chỉ một instance.

Nếu một transaction read-only load 100.000 entity rồi chuyển chúng sang JSON ở controller trong khi session vẫn mở, nó có thể giữ memory/connection lâu hơn cần thiết và ảnh hưởng SLO.

### 18.3. Resource cleanup và lỗi

ORM và Spring quản lý nhiều tài nguyên tự động nhưng có giới hạn. Khi dùng JDBC trực tiếp phải đóng `ResultSet`, `Statement`, `Connection` theo đúng ownership (thường dùng try-with-resources). Không đóng tay một connection do transaction manager đang quản lý giữa method `@Transactional`.

Nếu cleanup/rollback ném lỗi, giữ lỗi gốc và thêm suppressed cause phù hợp. Không ghi một `RuntimeException("DB failed")` làm mất SQLSTATE, constraint name và thông tin lỗi cần phân loại retry.

### 18.4. Streaming nhiều entity cần transaction phù hợp

Một stream kết quả JPA/JDBC có thể giữ cursor, transaction và connection cho tới khi stream đóng. Nếu trả `Stream<Entity>` ra ngoài service transaction rồi tiêu thụ dần ở controller, query có thể lỗi khi session đã đóng hoặc khiến connection bị giữ lâu.

Thay vào đó:

- Xử lý stream **bên trong** scope quản lý tài nguyên.
- Giới hạn lượng dữ liệu được đọc.
- Dùng keyset pagination/chunk nếu phù hợp.
- Tách upload/network I/O dài khỏi transaction.
- Kiểm tra consistency giữa các trang nếu dữ liệu biến đổi.

## 19. Chọn công cụ theo use case thay vì dùng ORM cho mọi thứ

Một thiết kế persistence tốt có thể kết hợp nhiều kỹ thuật, miễn là ownership, transaction, dữ liệu và test rõ ràng.

| Use case | ORM hữu ích khi | SQL/JDBC hoặc kỹ thuật khác cần xem xét |
|---|---|---|
| CRUD đơn giản có quan hệ | Entity lifecycle, dirty checking, mapping | Query/DTO nếu chỉ cần một số trường |
| Dữ liệu aggregate nhiều bảng | Cùng transaction, kiểm soát identity/relationship | Constraint + conditional SQL cho invariant |
| Tra cứu danh sách lớn | Projection/EntityGraph phù hợp | Native SQL/index/EXPLAIN, keyset paging |
| Báo cáo phân tích | JPQL đủ đơn giản và chi phí phù hợp | CTE/window function/read model |
| Cập nhật hàng loạt | Entity callbacks/version cần bảo toàn | Set-based SQL, bulk operation có kiểm soát |
| Import file lớn | Mapping phức tạp phải qua domain validation | Staging + PostgreSQL COPY/batch JDBC |
| Ghi event bền vững | ORM ghi outbox trong cùng transaction | Relay/idempotent consumer/broker |
| Tối ưu khóa nóng | ORM `@Version` hoặc pessimistic lock phù hợp | Conditional SQL/DB locking/serialization |
| Tiến hóa schema | Mapping giữ tương thích với cột mới | Flyway/Liquibase + backfill + rehearsal |
| Audit và bảo mật | Entity metadata có ích | DB grants/RLS, immutable audit, encryption |

### 19.1. Đặt business invariant trước rồi chọn API

Ví dụ mục tiêu “đặt hàng không vượt tồn kho” có ít nhất ba yêu cầu:

1. Không để tồn kho âm.
2. Tạo đơn và trừ kho cùng atomic transaction.
3. Request lặp không tạo đơn/trừ kho hai lần.

Chọn `Repository.save` không trả lời ba yêu cầu này. Sau khi định nghĩa invariant mới chọn:

- DB constraint `CHECK (available >= 0)`.
- Conditional UPDATE hoặc locking phù hợp.
- Transaction boundary ở application service.
- Unique idempotency key/command ledger.
- Outbox nếu cần publish event.
- Integration tests điều khiển concurrency và failure.

### 19.2. Chọn query model riêng cho đọc khi cần

Đọc danh sách đơn thường không cần materialize toàn bộ aggregate với cascade và lazy state. Một projection SQL/JPQL chỉ lấy các field API cần có thể giảm memory, tránh lazy loading và làm phép truy cập dễ tối ưu hơn.

Cách tiếp cận này **không bắt buộc phải dùng CQRS hoàn chỉnh**. Đơn giản tách repository command use cases khỏi query/projection use cases cũng có thể mang lại lợi ích mà không tạo hệ thống phân tán mới.

### 19.3. Kết hợp JPA và JDBC cần thống nhất transaction

Nếu cùng một use case gọi JPA rồi JDBC raw SQL, cần chắc chắn chúng tham gia cùng transaction manager và connection/resource boundary khi muốn atomicity. Một `DriverManager.getConnection(...)` mở connection mới ngoài transaction Spring có thể tự commit riêng.

Thực hành tốt hơn là dùng DataSource được Spring quản lý, `JdbcTemplate` hoặc cấu hình transaction-aware API phù hợp, đồng thời test rollback xuyên hai đường truy cập. Không chỉ thấy một method `@Transactional` rồi mặc định mọi kết nối trong JVM đã cùng transaction.

## 20. Kiểm thử integration để bắt lỗi ORM không thể thấy bằng mock

### 20.1. Unit test không thay được database test

Một unit test mock:

~~~java
when(orderRepository.save(any()))
    .thenAnswer(call -> call.getArgument(0));

orderService.placeOrder(command);

verify(orderRepository).save(any());
~~~

có thể chứng minh service gọi repository, nhưng không chứng minh:

- DB constraint được áp dụng.
- SQL thực sự UPDATE đúng hàng.
- Transaction rollback cả order/inventory.
- Optimistic lock phát hiện tranh chấp.
- Query không gây N+1.
- Hibernate flush trước commit và phát lỗi constraint.
- Transaction annotation hoạt động qua proxy.
- Index/plan đáp ứng tải.

Cần integration tests chạy trên DBMS/driver/transaction manager thật.

### 20.2. Testcontainers/JDBC để kiểm tra transaction

Ví dụ dùng PostgreSQL Testcontainers và JDBC thuần để minh họa ranh giới transaction. Đây không phải test cho chính JPA provider; nó chứng minh cách tiếp cận **assert DB state sau lỗi**.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;

class TransactionRollbackTest {
    @Test
    void rollbackRestoresState() throws Exception {
        try (PostgreSQLContainer<?> pg =
                new PostgreSQLContainer<>("postgres:16-alpine")) {
            pg.start();

            try (Connection c = DriverManager.getConnection(
                    pg.getJdbcUrl(), pg.getUsername(), pg.getPassword());
                 Statement s = c.createStatement()) {
                s.executeUpdate(
                    "CREATE TABLE demo_balance (" +
                    "id INTEGER PRIMARY KEY, amount INTEGER NOT NULL)");
                s.executeUpdate(
                    "INSERT INTO demo_balance VALUES (1, 10)");

                c.setAutoCommit(false);
                try {
                    s.executeUpdate(
                        "UPDATE demo_balance SET amount = 7 WHERE id = 1");
                    // Mô phỏng một bước nghiệp vụ thất bại.
                    throw new IllegalStateException("payment record failed");
                } catch (IllegalStateException failure) {
                    c.rollback();
                } finally {
                    c.setAutoCommit(true);
                }

                try (ResultSet rs = s.executeQuery(
                        "SELECT amount FROM demo_balance WHERE id = 1")) {
                    assertTrue(rs.next());
                    assertEquals(10, rs.getInt(1));
                    assertFalse(rs.next());
                }
            }
        }
    }
}
~~~

Ví dụ giả định dependencies JUnit 5, Testcontainers và PostgreSQL JDBC được cấu hình. Code tạo table/row dùng autocommit trước khi bắt đầu transaction update nên rollback update không làm mất table/row.

Trong dự án Spring JPA thực tế, còn phải kiểm thử application service gọi qua Spring proxy, dữ liệu được flush và transaction manager xử lý rollback đúng. Không dùng annotation `@Transactional` trên **test method** rồi mặc định điều đó kiểm tra transaction của service; nhiều framework tự rollback transaction test sau khi hoàn tất, có thể che lỗi transaction boundary ở production.

### 20.3. Kiểm thử tích hợp cho N+1 và fetch plan

Một test dữ liệu:

~~~text
Tạo 30 orders, mỗi order có customer riêng.
Gọi API/query lấy danh sách order summaries.
Đo số SELECT thực và rows fetched.
Kiểm tra kết quả và giới hạn query budget phù hợp.
~~~

Đừng chỉ assert số query bằng 1 nếu giải pháp có 2 query được thiết kế hiệu quả. Một budget hợp lý như “không tăng tuyến tính theo số order” cộng metric latency/rows có thể phản ánh mục tiêu hơn.

Kiểm tra cả:

- Cold/warm persistence context và second-level cache.
- Query có paging/sorting đúng.
- Không sinh truy vấn ngoài transaction khi serialize response.
- Có giới hạn số row/memory.
- Không vô ý fetch field nhạy cảm.

### 20.4. Kiểm thử hai transaction concurrent

Tạo hai connection hoặc hai bean service chạy ở hai thread, điều phối bằng latch/barrier để cả hai đọc cùng trạng thái trước khi cập nhật. Sau đó kiểm tra:

- Không oversell/ghi đè trong conditional stock decrement.
- Optimistic locking ném exception khi version không khớp.
- Retry sử dụng transaction mới và không nhân đôi order.
- Không để DB connection bị treo nếu một thread lỗi.
- Test có timeout rõ, cleanup sau khi hoàn thành.

Các concurrency tests có thể không deterministic nếu chỉ dùng `Thread.sleep(...)`. Nên dùng barrier và trạng thái/row locks phù hợp, quan sát chính xác DB state cuối.

### 20.5. Chạy migration và data quality tests

Một thay đổi entity `@Column(nullable=false)` không tự làm sạch dữ liệu cũ. Test nên:

1. Dựng schema trước migration có dữ liệu legacy.
2. Chạy đúng Flyway/Liquibase migration đã versioned.
3. Kiểm tra count, tập ID, FK, giá trị tiền và constraints.
4. Chạy reader cũ/mới theo hợp đồng.
5. Thử dữ liệu không thể chuyển một cách an toàn.
6. Dừng/retry backfill và kiểm tra checkpoint.
7. Diễn tập restore từ backup cũ trên engine tương thích.

Không tự sửa migration đã áp dụng để “schema validation xanh”: checksum, artifact retention và đường nâng cấp lịch sử phải được bảo vệ.

## 21. Quan sát hành vi ORM bằng SQL và metrics

Một đội dùng ORM tốt vẫn cần khả năng nhìn thấy tác động tới database.

### 21.1. Những chỉ số quan trọng

| Chỉ số | Câu hỏi |
|---|---|
| SQL statements per request | Một endpoint đang phát bao nhiêu câu? |
| Rows returned / bytes transferred | Có tải dư do eager fetch/JOIN? |
| Query p50/p95/p99 | Chậm ở query nào, có regression? |
| Database CPU, I/O, temp files | Optimizer/index có đang làm quá nhiều việc? |
| Lock wait/deadlocks | Transaction có chặn nhau? |
| Connection pool active/pending | Có giữ connection quá lâu? |
| Transaction duration/rollbacks | Có transaction dài hoặc fail nhiều? |
| Optimistic locking conflicts | Có contention hoặc retry sai? |
| Batch sizes / inserts | Hibernate batching có hoạt động thật? |
| Cache hit/miss | Có che N+1 hoặc stale reads? |
| Replication lag/WAL | Bulk writes/migration có quá tải DB? |
| Idempotency conflicts | Retry có tạo lệnh trùng/payload khác? |

### 21.2. Tracing cần nối được request với query

Khi một request chậm, log nên giúp nối:

~~~text
trace_id
  -> HTTP endpoint / use case
  -> transaction boundary
  -> repository/JPQL/native query
  -> SQL template + duration + rows
  -> DB lock wait / connection borrow
~~~

Đừng lấy stack trace có bind values chứa PII làm phương pháp mặc định. Dùng template, sampling, redaction và quyền truy cập log phù hợp.

### 21.3. Bộ kiểm tra trước khi tối ưu

Một chu trình thực tế:

1. Xác định use case và dữ liệu trả về thực sự cần.
2. Ghi nhận SQL phát ra, số query và số row.
3. Đo p95/p99 và execution plan trên dữ liệu đại diện.
4. Kiểm tra index, fetch plan, transaction và connection pool.
5. Thay đổi một yếu tố có kiểm soát.
6. Chạy lại correctness/concurrency tests.
7. So sánh throughput và tác động lên use case khác.
8. Theo dõi sau deploy, chuẩn bị cách roll-forward nếu regression.

**Tăng cache hoặc bật batch có thể chỉ che một query/domain design sai**. Nên sửa ranh giới và query shape trước khi thêm lớp cache phức tạp không cần thiết.

## 22. Tình huống tổng hợp: checkout chậm và tạo đơn trùng

Một nhóm phát triển ứng dụng thương mại điện tử qua Spring Boot, Spring Data JPA và PostgreSQL. Sau một đợt quảng cáo, hệ thống gặp bốn triệu chứng:

1. Trang checkout chậm khi giỏ có nhiều dòng.
2. Một số SKU bị bán vượt tồn kho.
3. Người dùng bấm thanh toán lại sau timeout làm xuất hiện hai order.
4. Email xác nhận đôi khi gửi dù database rollback.

Đội phát triển nói: “Tất cả đã dùng Hibernate, repository và `@Transactional`, chắc DB sẽ xử lý.” Đây là lúc cần đi từ triệu chứng tới SQL và transaction thực.

### 22.1. Phân tích từng lớp

| Triệu chứng | Nguyên nhân cần kiểm chứng | Công cụ/giải pháp |
|---|---|---|
| Checkout chậm | Lazy N+1 khi đọc sản phẩm/giá/khuyến mãi | SQL tracing, projection/EntityGraph, query plan |
| Overselling | Check–then–act trên snapshot cũ, thiếu locking | Conditional UPDATE, constraint, transaction |
| Order trùng | HTTP retry sau commit không rõ kết quả | Idempotency key + unique/command ledger |
| Email sai | Gửi ngoài DB transaction nhưng tưởng sẽ rollback | Outbox/async worker + consumer idempotency |
| Pool chờ | Transaction giữ connection trong lúc gọi payment | Chia transaction ngắn, workflow trạng thái |
| Record stale | Bulk update/second-level cache chưa đồng bộ | Version check và cache invalidation |

### 22.2. Cách tái hiện một oversell

Giả sử `available = 5`, hai transaction cùng muốn mua 4:

~~~text
T1: read available = 5
T2: read available = 5
T1: save available = 1
T2: save available = 1

Nếu cả hai request đều được xác nhận:
  đã bán 8, nhưng DB còn ghi available = 1.
~~~

Một phép trừ có điều kiện:

~~~sql
UPDATE inventory
SET available = available - 4
WHERE sku = 'BOOK-01' AND available >= 4;
~~~

với affected-row count được kiểm tra trong cùng transaction đặt đơn sẽ ngăn **cả hai cùng trừ thành công** trong mô hình cập nhật đó. Nhưng vẫn cần các test cho duplicate request, nhiều kho, reservation expiration và mọi writer khác.

### 22.3. Ranh giới nghiệp vụ cải tiến

~~~text
POST /checkout (idempotency-key)
   |
   v
Application service:
  1. Kiểm tra/claim idempotency key trong DB.
  2. Conditional inventory decrement.
  3. Insert order + payment-intent state.
  4. Insert outbox event.
  5. COMMIT transaction ngắn.
   |
   v
Outbox relay:
  publish event (at-least-once possible)
   |
   v
Payment worker:
  call external provider with stable operation ID
  reconcile timeout/unknown result
  update order/payment state in new transaction
   |
   v
Notification worker:
  send email only after state confirmed, deduplicate event
~~~

Đây là một kiến trúc minh họa; có nhiều cách thiết kế hợp lệ tùy yêu cầu sản phẩm. **Không** suy ra rằng flow này đảm bảo exactly-once end-to-end, đặc biệt khi provider/broker có thể gửi hoặc nhận trùng. Phải thiết kế và test từng ranh giới consistency.

### 22.4. Những bài test chặn regression

- 100 order summaries → số SQL không tăng tuyến tính theo số order.
- Hai request cạnh tranh SKU còn 5, mỗi request mua 4 → tối đa một request giữ hàng thành công.
- Request gửi lại cùng idempotency key/payload → không tạo thêm order.
- Cùng key nhưng payload khác → trả conflict rõ.
- Lỗi sau insert order nhưng trước commit → order, inventory, outbox rollback cùng nhau.
- Broker gửi event hai lần → consumer chỉ thực hiện tác dụng phụ một lần theo idempotency.
- Payment timeout quanh response → reconcile trước khi retry.
- Load test kiểm tra p95/p99, pool active, SQL plan và lock wait.
- Schema migration trên backup cũ → code hiện tại còn đọc đúng dữ liệu lịch sử.

Bộ test này đo **hợp đồng nghiệp vụ và hành vi persistence thực**, không chỉ kiểm tra một repository method được gọi.

## 23. Bảng lỗi thiết kế thường gặp

| Nhận định sai | Hậu quả | Sửa theo hướng |
|---|---|---|
| “ORM đã tối ưu SQL cho mình” | N+1, scan/sort tốn kém | Đọc generated SQL, đo plan và rows |
| “EAGER ở mọi association là nhanh” | Tải dư, JOIN phình, pagination sai | Fetch plan/projection theo use case |
| “`save` nghĩa là COMMIT rồi” | Báo thành công trước khi transaction commit | Hiểu flush/commit và lỗi commit mơ hồ |
| “`flush()` giống `commit()`” | Dữ liệu đã flush có thể bị rollback | Thiết kế transaction boundary rõ |
| “`@Transactional` trên mọi method đều hoạt động” | Self-invocation, async, proxy sai | Test qua bean boundary đúng |
| “Checked exception luôn rollback” | Transaction có thể commit dù báo lỗi | Cấu hình rollback rules/test thực |
| “`readOnly=true` là chặn mọi UPDATE” | Không phải quyền DB bảo mật | DB role và enforcement thật |
| “`REQUIRES_NEW` sửa được mọi rollback” | Commit rời nghiệp vụ, tốn connection | Chỉ tách transaction khi đúng semantics |
| “Transaction tránh mọi race” | Lost update/write skew | Version, conditional SQL, lock/isolation |
| “`@Version` chặn mọi xung đột” | Bulk SQL, invariant nhiều row vẫn lọt | Test concurrency ở đúng domain boundary |
| “Validate ở Java là đủ” | Duplicate/FK/stock âm từ đường ghi khác | DB constraints + transaction |
| “`saveAll` luôn là batch hiệu quả” | Nhiều INSERT/ID generation overhead | Đo driver SQL, ID strategy và batch |
| “Bulk JPQL cập nhật managed entity ngay” | Stale state/dirty checking sai | Flush/clear/refresh có kiểm soát |
| “Cache luôn trả dữ liệu mới nhất” | Stale business decision | Consistency policy/version/invalidation |
| “Một annotation rollback được payment API” | Charge/email không được đảo | Workflow/outbox/saga và idempotency |
| “Retry mọi SQLException đều an toàn” | Trùng order/side effect | Phân loại lỗi và đối soát commit |
| “Repository tự giới hạn tenant” | Rò dữ liệu giữa tenant | Scope query, authz, RLS theo policy |
| “Test mock là đủ” | Không thấy SQL/lock/DDL/constraint | DBMS integration và failure tests |
| “Mở pool lớn là giải pháp chậm” | DB connection exhaustion | Giảm transaction duration, đo toàn hệ |
| “Auto-DDL thay được migration” | Lỗi schema/data lịch sử và DDL lock | Versioned migrations + backfill + rehearsal |

## 24. Bài tập vận dụng

### Bài 1. Tại sao một vòng lặp Java có thể phát nhiều SQL?

Code duyệt 500 `OrderEntity` rồi đọc `order.getCustomer().getDisplayName()`. Vì sao có thể có N+1 queries, và có cách nào kiểm chứng?

**Gợi ý:** Lazy association phát SELECT khi chưa nạp; xem SQL log/statistics, thử projection/JOIN/EntityGraph và đo số row/round trip với cache cold.

### Bài 2. Một query thay cho nhiều query có luôn tốt?

Nhóm đổi N+1 sang fetch join hai collections, rồi response tăng kích thước gấp nhiều lần. Vì sao?

**Gợi ý:** Cartesian multiplication của hai collections, tải dư và nguy cơ pagination sai. Cân nhắc chia query theo tập và DTO.

### Bài 3. Vì sao `save` không chứng minh commit?

Một managed entity đã được flush thành SQL, sau đó service ném RuntimeException. Dữ liệu có chắc còn không?

**Gợi ý:** Không. Flush chưa commit; transaction có thể rollback những SQL đã gửi.

### Bài 4. Self-invocation

Một method public `run()` gọi `this.processChunk()` và method con có `@Transactional`. Tại sao nó có thể không mở transaction theo ý định?

**Gợi ý:** Spring proxy interceptor không đi qua lời gọi nội bộ; tách bean hoặc dùng TransactionTemplate.

### Bài 5. Checked exception

Một service `@Transactional` ném checked exception, nhưng database vẫn commit. Có mâu thuẫn không?

**Gợi ý:** Không nhất thiết; Spring rollback rules mặc định thường không rollback checked exception. Cần cấu hình/test đúng.

### Bài 6. Tồn kho

Tồn kho 10, hai request lần lượt đòi 7 và 6, cùng đọc 10. Làm sao bảo đảm không oversell?

**Gợi ý:** Conditional UPDATE kiểm tra available đủ ngay tại DB, affected rows, cùng transaction order và constraint.

### Bài 7. Write skew

Hai bác sĩ đều thấy có hai người đang trực rồi mỗi người tự nghỉ. `@Version` trên từng row có đủ ngăn không?

**Gợi ý:** Có thể không; hai transaction cập nhật hai row khác nhau. Cần invariant serialization/locking hoặc constraint phù hợp.

### Bài 8. Bulk JPQL và stale entity

Sau khi bulk update archived=true, entity đã load trong persistence context vẫn trả archived=false. Cần làm gì?

**Gợi ý:** Nhận diện bulk không đồng bộ managed state; flush trước khi cần, clear/refresh có kiểm soát và test lifecycle.

### Bài 9. `saveAll` chậm

Hibernate bật batch size 50, nhưng entity dùng `GenerationType.IDENTITY` và có rất nhiều INSERT. Phải điều tra gì?

**Gợi ý:** ID generation, driver rewrite/generated keys, statement shape, số SQL thực và lựa chọn sequence/ID chiến lược phù hợp.

### Bài 10. `REQUIRES_NEW` và audit

Audit method commit trong `REQUIRES_NEW`, outer order transaction rollback. Điều đó luôn sai không?

**Gợi ý:** Phụ thuộc nghĩa audit: ghi “attempt” có thể đúng, ghi “order succeeded” là sai. Transaction phải theo invariant.

### Bài 11. Timeout khi thanh toán

Payment provider đã thu tiền nhưng Java nhận timeout, DB rollback. Retry thế nào an toàn?

**Gợi ý:** Operation ID/idempotency key với provider, truy vấn đối soát, workflow state và không charge lại mù.

### Bài 12. Môi trường nhiều tenant

Service gọi `findById(orderId)` và trả entity, không kiểm tra tenant. ORM có tự chặn cross-tenant access không?

**Gợi ý:** Không mặc định; scope query theo tenant, authorization và policy DB/RLS nếu cần.

### Bài 13. Đo hiệu năng

Query JPQL trả kết quả đúng trên 100 row nhưng chậm với 5 triệu row. Tại sao cần `EXPLAIN` và thống kê dữ liệu?

**Gợi ý:** Execution plan, selectivity, index, sort/hash, row count và skew quyết định chi phí.

### Bài 14. Test mock repository

Một test xác nhận `orderRepository.save` được gọi nhưng không phát hiện oversell. Test nào bổ sung?

**Gợi ý:** Integration test với DB thật, hai transaction concurrent, barrier, kiểm tra stock/order cuối và rollback.

### Bài 15. Chọn ORM hay SQL bulk

Một job nhập 10 triệu dòng CSV, không cần entity lifecycle nhưng cần validate và deduplicate. ORM `persist` từng row có phải lựa chọn mặc định?

**Gợi ý:** Xem xét staging + bulk load/SQL set-based, transaction theo chunk, idempotency và ràng buộc ở DB.

### Bài 16. Restore sau migration

Hibernate entity mới yêu cầu cột currency non-null, nhưng backup cũ chưa có currency. Bật ORM auto-update khi restore có đủ an toàn không?

**Gợi ý:** Không. Cần versioned migration, reader tương thích, backfill, verify và rehearsal trước khi mở traffic.

## 25. Ghi nhớ

- **ORM là công cụ ánh xạ, không thay database.** Mỗi entity/query cuối cùng vẫn dùng SQL, index, connection, lock, transaction và storage.
- **Học SQL để hiểu ORM.** Quan sát generated SQL, N+1, fetch plan, join cardinality, `EXPLAIN` và index trên dữ liệu đại diện.
- **Hiểu persistence context.** `persist`/`merge`/`dirty checking`/`flush` khác `COMMIT`, và bulk operations có thể để managed state lỗi thời.
- **Đặt transaction ở nghiệp vụ.** Một use case cần atomicity không thể chỉ dựa vào từng repository; tránh giữ transaction xuyên network call dài.
- **Không dùng `@Transactional` như phép màu.** Proxy, self-invocation, checked exception, propagation, `readOnly` và async là những điểm cần kiểm thử thật.
- **Isolation không thay bất biến.** Dùng constraint, conditional UPDATE, optimistic/pessimistic locking và retry theo ngữ nghĩa để chống race.
- **Dữ liệu bền vững có nhiều đường ghi.** ORM validation không thay unique/FK/check/permission và migration versioned tại DB.
- **Cache và batching có điều kiện.** Không mặc định `saveAll` batch tốt hoặc cache luôn nhất quán; đo và kiểm tra driver/provider.
- **DB transaction không bao hệ ngoài.** Outbox, idempotency, workflow/saga và reconciliation cần được thiết kế riêng.
- **Test với DBMS thật.** Mock repository không thể chứng minh locking, commit, schema migration hay execution plan.
- **Quan sát toàn hệ thống.** Query count, p95/p99, lock wait, pool saturation, WAL/replica lag và correctness quan trọng hơn số annotation.

ORM giúp Java developer xây dựng persistence nhanh hơn bằng cách giảm mã ánh xạ lặp lại, nhưng nó **không thể thay kiến thức về mô hình quan hệ, truy vấn và giao dịch**. Thiết kế tốt là biết lúc nào ORM giúp ích, lúc nào cần SQL trực tiếp hoặc mô hình xử lý khác, và luôn có bằng chứng rằng dữ liệu được đọc đúng, ghi đúng, commit đúng và giữ đúng khi nhiều request cùng hoạt động.







# Phát hiện flush ngoài dự kiến, truy vấn trong vòng lặp và tải trì hoãn

## 1. Vì sao một endpoint chỉ đọc dữ liệu lại có thể chạy rất nhiều SQL?

Một endpoint trả danh sách đơn hàng thường trông rất đơn giản:

~~~java
@Transactional(readOnly = true)
public List<OrderSummary> listOrders() {
    List<PurchaseOrder> orders = entityManager.createQuery(
        "select o from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    ).getResultList();

    return orders.stream()
        .map(o -> new OrderSummary(
            o.getId(),
            o.getCustomer().getName(),
            o.getItems().size()
        ))
        .toList();
}
~~~

Developer có thể tưởng một truy vấn `select o from PurchaseOrder` sẽ tạo ra một lượt đọc. Nhưng với các association được tải trì hoãn, Hibernate có thể thực thi:

~~~sql
SELECT ... FROM purchase_orders ORDER BY id;

-- Khi vòng lặp đọc o.getCustomer().getName():
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
...

-- Khi vòng lặp đọc o.getItems().size():
SELECT ... FROM order_items WHERE order_id = ?;
SELECT ... FROM order_items WHERE order_id = ?;
...
~~~

Một endpoint khác có thể làm tình huống khó hiểu hơn: code vừa thay managed entity rồi chạy một query đếm số đơn hàng; Hibernate tự `flush` các thay đổi đang chờ trước query đó. SQL UPDATE xuất hiện “ở giữa hàm đọc”, không phải ở cuối transaction như developer dự đoán.

Ba triệu chứng cần phân biệt:

1. **Flush ngoài dự kiến:** SQL INSERT/UPDATE/DELETE được phát ở thời điểm không mong đợi vì dirty checking, auto-flush, explicit flush hoặc transaction boundary.
2. **Truy vấn trong vòng lặp / N+1:** số SELECT tăng theo số entity/row được duyệt thay vì theo số truy vấn được thiết kế.
3. **Tải trì hoãn (lazy loading):** truy cập một proxy hoặc collection khiến Hibernate truy vấn DB về sau, hoặc ném `LazyInitializationException` khi context đã đóng.

Ba vấn đề có thể cùng xảy ra, nhưng cách đo và cách chữa **không giống nhau**. Bài học thuộc chương **Quan sát và chẩn đoán** trong module *Data Persistence Relational Access ORM Hibernate* và tập trung vào phương pháp từ triệu chứng đến bằng chứng.

### 1.1. Mục tiêu

Sau bài học, bạn có thể:

- Biết flush khác commit, dirty checking và JDBC batch.
- Phân biệt auto-flush trước query với flush ở cuối transaction.
- Quan sát SQL, bound parameters, flushes, entity loads, collection fetches, query counts và thời gian DB theo đúng phạm vi.
- Tìm điểm gọi gây N+1 ngay cả khi SQL log không ghi rõ tên Java method.
- Kiểm tra một association/proxy có được initialize chưa, tránh vô tình kích hoạt SQL khi debug/serialize.
- Chọn fetch join, entity graph, DTO projection, batch fetching hoặc explicit query thay vì “đổi tất cả sang EAGER”.
- Xử lý transaction scope, OSIV, `@Transactional(readOnly = true)`, pagination và hiệu năng.
- Viết integration tests có ngưỡng query budget hoặc kiểm tra flush trong điều kiện có kiểm soát.

## 2. Mô hình ví dụ: đơn hàng, khách hàng và dòng hàng

Giả sử database có ba bảng:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(160) NOT NULL
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status VARCHAR(40) NOT NULL,
    version BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_items (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
~~~

### 2.1. JPA entities minh họa

~~~java
import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {}
    public Long getId() { return id; }
    public String getName() { return name; }
}

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderItem> items = new ArrayList<>();

    @Column(nullable = false)
    private String status;

    @Version
    private long version;

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Customer getCustomer() { return customer; }
    public List<OrderItem> getItems() { return items; }
    public String getStatus() { return status; }

    public void markProcessing() {
        status = "PROCESSING";
    }
}

@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    private String sku;
    private int quantity;

    protected OrderItem() {}

    public String getSku() { return sku; }
    public int getQuantity() { return quantity; }
}
~~~

Đây là các class rút gọn; trong dự án thật bổ sung constructor, validation, identifier generator, schema migration và business methods phù hợp. Điểm quan trọng của ví dụ:

- Một `PurchaseOrder` có một `Customer`, quan hệ to-one được chỉ định `LAZY`.
- Một `PurchaseOrder` có nhiều `OrderItem`, collection mặc định lazy và cũng được khai báo rõ.
- `@Version` cho optimistic locking trong entity-level UPDATE.
- `status` là state được Hibernate dirty-check khi entity còn managed.

### 2.2. Dữ liệu để quan sát

Giả sử có:
- 30 PurchaseOrders.
- 30 Customers khác nhau (mỗi order thuộc một customer).
- 4 OrderItems mỗi order.

Nếu code load 30 orders rồi đọc customer + items của từng order, một pattern thiếu fetch plan có thể sinh:

~~~text
1 SELECT orders
30 SELECT customers
30 SELECT order_items
---------------------
61 SELECT statements
~~~

**61 chỉ là mô hình minh họa**, không phải số Hibernate luôn phát. Identity map, second-level cache, batch fetching, association sharing, fetch mapping và query plan có thể làm số SELECT giảm hoặc đổi. Việc quan sát thực tế mới quyết định kết luận.

### 2.3. Vì sao cần dataset có nhiều chủ thể khác nhau?

Nếu 30 orders cùng tham chiếu **một Customer**, persistence context có thể load Customer đó một lần và tái sử dụng cho 29 orders còn lại. Test kiểu này dễ bỏ sót N+1 to-one.

Muốn phát hiện N+1:
- Dùng đủ nhiều distinct customer IDs.
- Mỗi order có items cần truy cập.
- Đảm bảo cache warm/cold scenario được mô tả.
- Tách việc tạo fixture ra ngoài khoảng đang đo query count.

## 3. Nền tảng: persistence context, SQL timing và flush

### 3.1. Một setter không tương đương một UPDATE ngay lập tức

~~~java
@Transactional
public void changeStatus(Long id) {
    PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, id);

    order.markProcessing();

    // Không có gọi repository.update(...).
    // Hibernate có thể chờ tới flush/commit mới gửi SQL.
}
~~~

`order` đang managed. Hibernate ghi nhận snapshot/state và khi flush sẽ xác định có cần một UPDATE hay không. Một lần gọi setter không nhất thiết tạo SQL ngay thời điểm setter chạy.

### 3.2. Flush đưa SQL đang chờ xuống transaction

~~~text
Java managed entity
     |
     | order.markProcessing()
     v
Persistence context (L1)
  - current field values
  - entity snapshots/dirty state
  - pending actions
     |
     | flush
     v
JDBC SQL INSERT / UPDATE / DELETE
     |
     v
Database transaction
     |
     +-- COMMIT: thay đổi được xác nhận
     |
     +-- ROLLBACK: thay đổi SQL được hoàn tác
~~~

`flush()` **không phải `commit()`**. Khi `flush` trả về thành công, SQL có thể đã được thực thi nhưng transaction khác chưa nhìn thấy dữ liệu theo isolation semantics; rollback sau đó vẫn có thể hủy các thay đổi.

### 3.3. Nhiều nguyên nhân dẫn tới flush

| Tình huống | Có thể kích hoạt flush? | Điểm cần chú ý |
|---|---|---|
| `entityManager.flush()` | Có, tường minh | Có thể flush **toàn bộ** pending changes trong context |
| `repository.saveAndFlush(entity)` | Có, theo Spring Data contract | Không tương đương commit |
| Transaction commit | Thường có khi flush mode cho phép | JPA provider xử lý pending DML |
| HQL/JPQL SELECT khi có pending changes liên quan | Có thể, theo AUTO flush semantics | Query và pending DML liên quan cùng query spaces |
| Native SQL qua EntityManager | Có thể, tùy API/provider version và synchronization | Không suy diễn từ HQL behavior |
| Query không liên quan table đã sửa | Có thể không flush trong Hibernate AUTO | Phụ thuộc flush mode/query spaces |
| `entityManager.clear()` | **Không tự flush** | Pending changes chưa flush có thể bị mất |
| `entityManager.refresh(entity)` | Không nên coi là cách flush | Reload state và có thể ghi đè local changes |
| Gọi `toString()` của một entity | Không phải flush trigger mặc định | Nhưng có thể kích hoạt **lazy SELECT** |

### 3.4. Auto-flush không phải bug

Ví dụ:

~~~java
@Transactional
public long countProcessingOrders(Long id) {
    PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, id);

    order.markProcessing();

    Long count = entityManager.createQuery(
        """
        select count(o)
        from PurchaseOrder o
        where o.status = 'PROCESSING'
        """,
        Long.class
    ).getSingleResult();

    return count;
}
~~~

Trong `FlushModeType.AUTO`, Hibernate/JPA cần bảo đảm query nhìn thấy pending changes theo contract và có thể gửi UPDATE trước khi thực thi SELECT COUNT.

Log có thể xuất hiện:

~~~text
SELECT ... FROM purchase_orders WHERE id=?
UPDATE purchase_orders SET status=?, version=? WHERE id=? AND version=?
SELECT COUNT(...) FROM purchase_orders WHERE status='PROCESSING'
~~~

Developer tưởng “method chỉ query count rồi commit” nhưng update xảy ra trước count vì **auto-flush có chủ đích để query nhất quán**.

### 3.5. Khi query không liên quan, Hibernate có thể hoãn flush

Nếu một managed `PurchaseOrder` được sửa nhưng ngay sau đó truy vấn bảng `customers` không phụ thuộc `purchase_orders`, Hibernate Session với `FlushMode.AUTO` có thể không cần flush trước query.

Tuy nhiên chi tiết còn phụ thuộc:
- Hibernate vs `EntityManager` query API.
- Query spaces và mapping nhiều bảng.
- Transaction/flush mode.
- Native SQL và query synchronization.
- Hibernate version/dialect.

**Không xây quy tắc tuyệt đối “mọi SELECT đều flush” hoặc “SELECT không bao giờ flush”.** Quan sát actual SQL và query boundaries.

## 4. Flush modes: khi nào auto-flush được phép?

### 4.1. JPA FlushModeType.AUTO và COMMIT

JPA định nghĩa:

~~~java
entityManager.setFlushMode(FlushModeType.AUTO);
entityManager.setFlushMode(FlushModeType.COMMIT);
~~~

- `AUTO`: provider phải làm cho những pending entity changes có khả năng ảnh hưởng query được phản ánh trong query results theo contract; thường bằng flush trước query.
- `COMMIT`: flush được dời tới commit theo policy; hiệu ứng của pending changes lên query results trước commit có thể không được bảo đảm như AUTO.

Không đổi sang COMMIT chỉ để “ẩn” auto-flush khi query cần nhìn thay đổi vừa thực hiện.

### 4.2. Hibernate flush modes

Hibernate có flush modes riêng (tên API đúng tùy version), thường gặp:

| Hibernate flush mode | Ý tưởng | Cảnh báo |
|---|---|---|
| `AUTO` | Flush khi cần, nhất là trước query liên quan và transaction completion | Mặc định thường dùng |
| `COMMIT` | Cố gắng dời flush tới transaction commit | Query trước commit có thể không thấy pending state như mong đợi |
| `ALWAYS` | Flush trước queries nhiều hơn | Dễ tạo overhead nếu ứng dụng query trong vòng lặp |
| `MANUAL` | Chỉ flush khi được yêu cầu tường minh theo contract | Dễ mất pending updates nếu quên flush |
| `PERSISTENCE_CONTEXT` hoặc mode/version-specific khác | Xem Javadoc của Hibernate version đang dùng | Không đoán enum giữa phiên bản |

Ở Hibernate 6.x phổ biến có `ALWAYS`, `AUTO`, `COMMIT` và `MANUAL`; dùng Javadoc đúng dependency.

Ví dụ chỉ khi hiểu rõ:

~~~java
Session session = entityManager.unwrap(Session.class);
FlushMode previous = session.getHibernateFlushMode();

try {
    session.setHibernateFlushMode(FlushMode.MANUAL);
    // Những query/operations có chủ đích...
    session.flush(); // Chỉ khi cần và đảm bảo transaction.
} finally {
    session.setHibernateFlushMode(previous);
}
~~~

**Đổi flush mode trên Session hiện hành có thể ảnh hưởng code khác** dùng cùng persistence context trong transaction. Restore trong `finally` không thay thế thiết kế transaction đúng; một exception trước flush vẫn có thể khiến pending writes không được gửi.

### 4.3. @Transactional(readOnly = true)

Trong Spring + Hibernate, `@Transactional(readOnly = true)` thường được dùng cho read use cases và có thể ảnh hưởng flush mode/default read-only handling tùy Spring/Hibernate version:

~~~java
@Transactional(readOnly = true)
public List<OrderSummary> listOrders() {
    // Read operations, DTO projection...
}
~~~

Đừng nghĩ annotation này là một database-level security rule luôn cấm DML. Nó là read-only transaction hint và integration optimization; DB/provider vẫn có khác biệt. Ngược lại, nếu code thực sự sửa entity trong readOnly transaction, không nên mặc định dirty checking/auto-flush sẽ phát UPDATE.

**Tắt auto-flush để che log không phải giải quyết N+1.** N+1 chủ yếu là số lần tải association; flush chủ yếu là đồng bộ pending writes.

## 5. Phát hiện flush ngoài dự kiến: từ log tới nguyên nhân

### 5.1. Ví dụ tình huống

~~~java
@Transactional
public OrderSummary updateAndRead(Long id) {
    PurchaseOrder order =
        entityManager.find(PurchaseOrder.class, id);

    order.markProcessing();

    Long count = entityManager.createQuery(
        "select count(o) from PurchaseOrder o",
        Long.class
    ).getSingleResult();

    return new OrderSummary(
        order.getId(), order.getCustomer().getName(),
        Math.toIntExact(count)
    );
}
~~~

Ba điểm cần quan sát:

1. `find` có thể thực hiện SELECT order.
2. Query `count` có thể kích hoạt **auto-flush** UPDATE vì nó phụ thuộc bảng orders mà context có pending change.
3. `order.getCustomer().getName()` có thể kích hoạt **lazy SELECT** nếu Customer chưa initialized.

Nhìn log thấy UPDATE trước COUNT rồi SELECT Customer không đủ để kết luận “Hibernate random SQL”. Phải gán mỗi statement vào một trong ba cơ chế.

### 5.2. Vì sao flush nhiều lần gây vấn đề?

Một loop:

~~~java
@Transactional
public void updateMany(List<Long> orderIds) {
    for (Long id : orderIds) {
        PurchaseOrder o = entityManager.find(PurchaseOrder.class, id);
        o.markProcessing();
        entityManager.flush();  // Flush mỗi iteration.
    }
}
~~~

Khi có 1.000 orders, code có thể tạo nhiều vòng flush/dirty checking và phá cơ hội gom UPDATE vào JDBC batches hiệu quả.

Nó khác với:

~~~java
@Transactional
public void updateManyBetter(List<Long> orderIds) {
    int i = 0;

    for (Long id : orderIds) {
        PurchaseOrder o = entityManager.find(PurchaseOrder.class, id);
        o.markProcessing();

        if (++i % 100 == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
}
~~~

Ví dụ thứ hai dùng flush/clear theo chunk để giới hạn persistence context, nhưng **không bảo đảm hiệu quả tối ưu**: mỗi `find` vẫn có thể gây SELECT, `clear` detach mọi entity trong context, và transaction vẫn có thể dài. Nó chỉ minh họa khác biệt giữa flush mỗi row và flush có chủ đích theo khoảng.

### 5.3. Auto-flush do query trong loop

~~~java
@Transactional
public void processBad(List<Long> ids) {
    for (Long id : ids) {
        PurchaseOrder o = entityManager.find(PurchaseOrder.class, id);
        o.markProcessing();

        // Truy vấn liên quan purchase_orders:
        entityManager.createQuery(
            "select count(o) from PurchaseOrder o",
            Long.class
        ).getSingleResult();
    }
}
~~~

Ngoài `N` SELECT COUNT, flush có thể được kích hoạt lặp lại trước các query này. Đây là **hai vấn đề cộng hưởng**:

- Query-in-loop: N lần `COUNT`.
- Auto-flush: nhiều lần đồng bộ pending changes hơn dự kiến.

Giải pháp không phải chỉ `setHibernateFlushMode(MANUAL)`; hãy xem **tại sao phải count trong từng iteration** và có thể chuyển sang aggregate query hoặc tính toán ngoài loop không.

### 5.4. Queries và dirty checking có thể không phát UPDATE

Một lần auto-flush vẫn có thể tiêu tốn overhead để kiểm tra dirty entities nhưng không phát SQL nếu không có persistent changes. Ngược lại, SQL UPDATE có thể được phát dù developer không gọi `flush()` tường minh do query/commit boundary.

Vì vậy đo riêng:
- Số lần flush và thời gian flush.
- Số entity updates/inserts/deletes.
- Số SQL statements và JDBC batches.
- Wall-clock latency.
- Kích thước persistence context và memory pressure.

Chỉ đếm UPDATE lines không đủ để suy ra toàn bộ flush overhead.
+
## 6. Quan sát SQL bằng log đúng tầng

### 6.1. Bật Hibernate SQL logger

Trong Spring Boot/Hibernate 6.x:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

- `org.hibernate.SQL` ghi SQL statement template (thường có placeholders `?`).
- `org.hibernate.orm.jdbc.bind` ghi chi tiết bind parameters ở Hibernate 6.x, tùy patch version và logging integration.

Khi debug query shape trong môi trường local/staging, có thể bổ sung:

~~~properties
spring.jpa.properties.hibernate.format_sql=true
~~~

Trong code cấu hình Hibernate thuần:

~~~properties
hibernate.show_sql=false
hibernate.format_sql=true
~~~

Thường ưu tiên **logger** thay vì `show_sql=true` vì logger dễ cấu hình level, sink, correlation và không ghi thẳng console bằng đường riêng.

**Cẩn trọng:** bind logging có thể lộ email, token, địa chỉ, dữ liệu bệnh nhân hoặc bí mật trong WHERE/INSERT. Không bật TRACE bind values ở production nếu chưa có chính sách masking, access control và retention. Có thể chỉ bật SQL shape/slow-query metrics.

### 6.2. Đọc SQL log như một chuỗi sự kiện

Một request có thể tạo log:

~~~text
[request=abc] select ... from purchase_orders where id=?
[request=abc] update purchase_orders set status=?, version=? where id=? and version=?
[request=abc] select count(*) from purchase_orders
[request=abc] select ... from customers where id=?
~~~

Có thể suy luận bước đầu:
1. Entity được tìm.
2. Một UPDATE xảy ra trước query COUNT → có thể là auto-flush.
3. Customer được tải sau COUNT → có thể là lazy initialization.

Nhưng SQL logger **không ghi “đây là flush vì method X” một cách mặc định**. Cần kết hợp:
- Correlation/request ID.
- Method tracing hoặc instrumentation.
- Hibernate statistics/session metrics.
- JDBC-level statement counts.
- Application code path.

Không kết luận theo thứ tự log khi nhiều requests/threads cùng ghi và không có correlation.

### 6.3. Vì sao nhiều dòng SQL không đồng nghĩa nhiều network round trips?

Khi Hibernate dùng JDBC batching cho INSERT/UPDATE, SQL logger vẫn có thể ghi nhiều **logical SQL executions**. Driver có thể gom chúng thông qua `addBatch()/executeBatch()` hoặc rewrite statements.

Để phân biệt:
- Số entity actions.
- Số JDBC prepared statements/execute calls.
- Số `executeBatch`.
- Số DB round trips/protocol messages nếu driver/database expose.
- End-to-end latency.

Ngược lại, một SQL statement với JOIN phức tạp có thể trả hàng trăm nghìn rows và chậm hơn 10 SELECT được index tốt. **Query count là một chỉ báo, không phải mục tiêu tối ưu duy nhất.**

### 6.4. Hibernate slow query logging

Hibernate cung cấp cấu hình/metrics slow query tùy phiên bản và logging integration. Ví dụ thường gặp trong Hibernate 6.x:

~~~properties
hibernate.log_slow_query=100
~~~

Giá trị được diễn giải là ngưỡng thời gian theo contract phiên bản (trong Hibernate 6.x thường là milliseconds). Phải kiểm tra Javadocs/config version dự án nếu dùng vào production.

Slow SQL logging hữu ích để phát hiện một truy vấn nặng; nhưng **N+1 có thể gồm 100 truy vấn, mỗi truy vấn chỉ 2 ms**, nên không truy vấn nào vượt ngưỡng slow query dù request mất hơn 200 ms. Vì thế vẫn phải đếm statements.

### 6.5. Tách log query và log DML

Khi xem log, nhóm các SQL thành:
- SELECT root entities.
- SELECT associations.
- Count/exists queries.
- INSERT/UPDATE/DELETE do flush.
- Bulk HQL/native DML.
- SQL do schema/metadata/health checks.
- Các câu JDBC từ thư viện khác.

Một SQL SELECT lặp lại cùng shape với các bind IDs khác nhau là dấu hiệu N+1 mạnh hơn một SQL SELECT xuất hiện nhiều lần ở nhiều requests khác nhau.

## 7. Hibernate Statistics: đo flush, fetch, entity load và query cache

### 7.1. Bật statistics có chủ đích

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Hoặc Hibernate configuration:

~~~properties
hibernate.generate_statistics=true
~~~

Hibernate `SessionFactory.getStatistics()` cho các counters tổng hợp liên quan entity/query/collection/flush/cache. Ví dụ:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics stats = sessionFactory.getStatistics();

long flushes = stats.getFlushCount();
long entityLoads = stats.getEntityLoadCount();
long entityFetches = stats.getEntityFetchCount();
long collectionFetches = stats.getCollectionFetchCount();
long queryExecutions = stats.getQueryExecutionCount();

System.out.println("flushes = " + flushes);
System.out.println("entityLoads = " + entityLoads);
System.out.println("entityFetches = " + entityFetches);
System.out.println("collectionFetches = " + collectionFetches);
System.out.println("queryExecutions = " + queryExecutions);
~~~

Ý nghĩa cần phân biệt:

| Metric | Diễn giải hướng tới | Không phải |
|---|---|---|
| `getFlushCount()` | Số flush events được thống kê | Số SQL UPDATE |
| `getEntityLoadCount()` | Số entity instances được load | Số SELECT network calls |
| `getEntityFetchCount()` | Entity fetch events (thường liên quan fetch ngoài load ban đầu) | Số entity trong root result |
| `getCollectionFetchCount()` | Collection fetch events | Số rows trong collections |
| `getQueryExecutionCount()` | Query executions được Hibernate thống kê | Mọi SQL statement qua mọi JDBC clients |
| `getPrepareStatementCount()` | Prepared statement count theo Hibernate statistics | Chính xác số network round trips |
| `getSecondLevelCacheHitCount()` | Shared cache hit events | Bằng chứng DB không có query từ code khác |

Mỗi counter theo Hibernate `Statistics` contract và có thể thay đổi chi tiết giữa versions. Đừng thiết kế assertion sai vì coi `entityLoads == SELECT count` hay `queryExecutions == tất cả JDBC SELECT`.

### 7.2. Statistics thường gắn với SessionFactory, không riêng request

Một đoạn đo thiếu kiểm soát:

~~~java
long before = stats.getQueryExecutionCount();
callEndpoint();
long after = stats.getQueryExecutionCount();
System.out.println(after - before);
~~~

chỉ đáng tin khi **không có traffic khác** dùng cùng SessionFactory giữa hai lần đọc. Trong production đa luồng, counters tổng hợp có thể chứa hoạt động của requests khác.

Với integration test chạy tuần tự, delta có thể hữu ích nếu:
- Reset/clear counters trước đoạn test theo test isolation.
- Tách setup fixtures khỏi đoạn đo.
- Không chạy tests song song trên cùng SessionFactory.
- Nêu rõ L2/query cache warm hay cold.
- Không coi một số counter là số statements nếu provider không bảo đảm.

Khi cần **theo request**, dùng JDBC proxy/APM spans với request correlation hoặc session metrics có scope rõ.

### 7.3. Session metrics logging

Hibernate có các log thống kê theo Session được ghi qua event listener/stats integration ở những versions/cấu hình phù hợp. Một log session có thể chứa:
- Thời gian acquire/release JDBC connection.
- Số prepared statements.
- Số JDBC batches.
- Số flushes và entities/collections processed.
- Thời gian JDBC execution.

Tên class/log category và đơn vị đo khác theo Hibernate version. Đừng copy y nguyên category của Hibernate 5 vào Hibernate 6 rồi kết luận “không có flush” khi log trống.

Nếu log chỉ xuất hiện lúc Session đóng, với OSIV Session có thể đóng **sau** service transaction; phải liên hệ log với request/session scope thật.

### 7.4. Những statistic không đủ để quy ra N+1

Một request có:
- 30 entities loaded từ root query.
- 30 entity fetches cho 30 customers.
- 30 collection fetches.

Đây là dấu hiệu đáng chú ý. Nhưng Hibernate statistics tự nó chưa xác định:
- Java method đã gọi getter nào.
- Một query chạy trong loop nào.
- Bind IDs.
- SQL timing/network latency.
- N+1 có bị che bởi cache hay không.

Kết hợp statistics với SQL shape + trace để khoanh đúng call site.

## 8. JDBC instrumentation và APM: đếm statement thực thi

### 8.1. Vì sao cần đo ở JDBC layer?

Hibernate SQL logger có thể cho thấy SQL templates, nhưng một workload có:
- Một SELECT từ JPA.
- N SELECT từ lazy associations.
- JDBC direct query qua `Session.doWork()`.
- Query từ `JdbcTemplate`.
- JDBC batches.

Nếu cần số thực thi SQL thực tế **từ cùng DataSource**, một datasource proxy/instrumentation phù hợp có thể đếm `executeQuery`, `executeUpdate` và `executeBatch`.

Các thư viện thường được dùng gồm datasource-proxy hoặc P6Spy; chọn phiên bản phù hợp Spring Boot/JDBC driver và cấu hình bảo vệ dữ liệu. Chúng là **một lựa chọn instrumentation**, không phải một chức năng bắt buộc của Hibernate.

### 8.2. Mô hình đếm theo request

~~~text
HTTP request (correlationId=abc)
                 |
                 v
   Spring service @Transactional
                 |
                 v
      Hibernate/JDBC statements
                 |
                 v
   DataSource proxy / APM JDBC spans
                 |
                 v
       Metrics/traces grouped by
         correlationId=abc
~~~

Khi dùng tracing:
- Gắn span/trace ID ở ingress.
- Dùng propagation thích hợp qua service calls.
- Ghi SQL **shape hoặc normalized operation name**, tránh bind values nhạy cảm.
- Thu duration, statement count, transaction time.
- Liên kết JDBC spans với endpoint/method và DB server metrics.

### 8.3. Phân biệt prepared statement và execution

Một `PreparedStatement` có thể được prepare một lần rồi execute 100 lần với 100 parameter sets. Count `prepareStatement` khác count `execute`.

Một JDBC batch có thể gọi:
- `addBatch` 25 lần.
- `executeBatch` một lần.

Vậy metrics nên phân biệt:
- Statement preparation.
- Logical executions/batch elements.
- `executeBatch` invocations.
- Driver/server protocol round trips nếu đo được.

Nếu chỉ đếm `prepareStatement`, bạn có thể bỏ sót một pattern query-in-loop tái sử dụng cùng statement.

### 8.4. Slow request ≠ một slow SQL

Một request có 50 SELECT, mỗi SELECT 4 ms, tổng DB latency có thể lớn dù không query nào vượt slow query threshold. Cần request-wide count + cumulative DB time, kết hợp p95/p99 latency.

Mẫu telemetry hữu ích:

| Trường | Ví dụ minh họa |
|---|---|
| Endpoint | `GET /orders` |
| Request trace ID | `abc123` |
| DB query count | 61 |
| Repeated SQL fingerprint | `select ... from order_items where order_id=?` |
| Times repeated | 30 |
| Total JDBC time | 215 ms |
| Flush events | 0 |
| Entity loads | 180 |
| Collection fetch events | 30 |
| Response elapsed | 270 ms |

Đây là **mẫu quan sát**, không phải số thực nghiệm. Đếm collection fetches không tự đồng nghĩa số statements khi có batch fetching.

## 9. Hibernate StatementInspector: thấy SQL nhưng không phải mọi sự kiện

Hibernate có SPI `org.hibernate.resource.jdbc.spi.StatementInspector` để inspect SQL string Hibernate chuẩn bị. Ví dụ:

~~~java
import org.hibernate.resource.jdbc.spi.StatementInspector;

public class SqlLoggingInspector implements StatementInspector {

    @Override
    public String inspect(String sql) {
        // Dùng logger/metrics trong implementation thực.
        // Đừng in bind parameters hoặc SQL động thiếu masking.
        return sql;
    }
}
~~~

Có thể cấu hình inspector theo `hibernate.session_factory.statement_inspector` hoặc integration programmatic tương ứng Hibernate version:

~~~properties
hibernate.session_factory.statement_inspector=com.example.SqlLoggingInspector
~~~

### 9.1. Inspector dùng để làm gì?

- Quan sát SQL shape do Hibernate tạo.
- Thêm comment/tag có chủ đích khi provider cho phép.
- Thu fingerprint hoặc phát hiện nhiều SQL giống nhau.
- Đối chiếu query generation trong test.

### 9.2. Inspector không chứng minh số round trips

`inspect(String sql)` được gọi ở tầng SQL preparation/inspection, không nhất thiết một lần cho mỗi network execution, không biết đầy đủ bound values hoặc số row trả về.

Nó không nhận SQL từ:
- JDBC client khác không qua Hibernate inspector.
- Một process khác.
- DB triggers/stored procedures nội bộ.
- Một số direct JDBC trong `doWork` nếu không đi qua SQL generation của Hibernate.

Nếu yêu cầu đếm thực thi SQL chính xác, dùng JDBC instrumentation hoặc DB/tracing tương ứng.

### 9.3. Không đặt SQL parsing nghiệp vụ trong inspector

Đừng phân tích SQL string bằng regex để quyết định authorization, soft-delete, tenant isolation hoặc audit nghiệp vụ. SQL có aliases, CTE, dialect-specific syntax, comment, quoted identifiers, schema prefixes và prepared params.

`StatementInspector` là extension phục vụ quan sát/điều chỉnh SQL có giới hạn; không phải database firewall hay row-level audit mechanism.

## 10. Gắn nguyên nhân flush với điểm gọi trong Java

### 10.1. Phân biệt triệu chứng và call site

Bạn nhìn thấy:

~~~sql
UPDATE purchase_orders SET status=?, version=? WHERE id=? AND version=?;
SELECT COUNT(*) FROM purchase_orders;
~~~

Cần trả lời:
1. Ai đã thay `status`?
2. Query nào khiến pending change phải được đồng bộ?
3. Có `flush()` tường minh không?
4. Có `saveAndFlush()`/`saveAllAndFlush()` không?
5. Có method `@Transactional` nào đang ở chế độ read-only/khác flush mode không?
6. Có lifecycle callbacks chạm entity khác trước flush không?
7. SQL là Hibernate entity dirty checking hay JDBC/native UPDATE trực tiếp?

### 10.2. Dùng instrumentation ở các ranh giới quan trọng

Một kỹ thuật thực tế là log mốc thời gian (không log data nhạy cảm):

~~~java
@Transactional
public long countAfterChange(Long id) {
    log.debug("before find");
    PurchaseOrder o =
        entityManager.find(PurchaseOrder.class, id);

    log.debug("before mutate");
    o.markProcessing();

    log.debug("before count query");
    Long count = entityManager.createQuery(
        "select count(o) from PurchaseOrder o",
        Long.class
    ).getSingleResult();

    log.debug("after count query");
    return count;
}
~~~

Khi SQL UPDATE xuất hiện giữa “before count query” và “after count query”, đó là dấu hiệu query boundary đã kích hoạt auto-flush, nếu không có một thao tác SQL explicit khác trong khoảng.

Không biến debugging markers thành logging vĩnh viễn quá nhiều; sử dụng log levels/traces có thể bật theo môi trường.

### 10.3. Pending dirty entities có thể đến từ repository khác

Trong một transaction:

~~~java
@Transactional
public long useCase(Long id) {
    orderWriter.changeStatus(id);
    return orderReader.countAll();
}
~~~

`changeStatus` có thể chỉ sửa managed entity, chưa flush. `countAll` chạy query liên quan orders và trigger flush. Developer nhìn vào `orderReader` thấy SQL UPDATE, tưởng reader đang ghi.

**Nguyên nhân gốc nằm ở state đã sửa trước đó trong cùng persistence context**, còn query hiện tại chỉ là thời điểm flush được phát.

### 10.4. Tránh thay đổi flush mode khi chưa biết invariant

Nếu query COUNT phải phản ánh trạng thái sau update, auto-flush có thể là hành vi đúng. Đổi sang `COMMIT`/`MANUAL` mà không thay query/transaction semantics có thể trả count sai.

Cách tối ưu thường là:
- Không query lại DB nếu đã có đủ state để tính.
- Dời aggregate query tới sau một explicit flush có chủ đích.
- Gom nhiều thay đổi rồi query một lần.
- Tách các use cases đọc/ghi bằng transaction boundaries rõ ràng.
- Dùng SQL set-based khi thao tác nghiệp vụ cho phép.
+
## 11. N+1 queries: một truy vấn gốc và N truy vấn phụ

### 11.1. Định nghĩa

N+1 thường xuất hiện khi một SELECT lấy N root entities, rồi code duyệt N entities và lần lượt tải association chưa được fetch:

~~~text
SELECT 1: PurchaseOrder #1 ... #30
             |
             +--> SELECT Customer của Order#1
             +--> SELECT Customer của Order#2
             +--> ...
             +--> SELECT Customer của Order#30

Tổng có thể gần 1 + N = 31 SELECT.
~~~

Nếu code đọc thêm `items` của mỗi order, có thể có thêm N collection SELECTs, tổng gần `1 + N + N`. **Đây chỉ là mô hình:** identity map, cache, batch fetching, associations trùng customer và fetch plans có thể làm số queries khác.

### 11.2. N+1 từ lazy to-one

~~~java
@Transactional(readOnly = true)
public List<String> customerNames() {
    List<PurchaseOrder> orders = entityManager.createQuery(
        "from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    ).getResultList();

    List<String> names = new ArrayList<>();
    for (PurchaseOrder o : orders) {
        names.add(o.getCustomer().getName());
    }
    return names;
}
~~~

Khi `customer` là lazy proxy chưa initialize và mỗi order tham chiếu customer khác, `getName()` có thể gây N SELECTs.

Một số mapping/proxy có thể truy cập identifier bằng `order.getCustomer().getId()` mà không cần initialize toàn bộ Customer; điều này phụ thuộc proxy/enhancement/id mapping. **Đừng đoán có SQL hay không chỉ từ tên getter**.

### 11.3. N+1 từ lazy collection

~~~java
@Transactional(readOnly = true)
public List<Integer> sizes() {
    List<PurchaseOrder> orders = entityManager.createQuery(
        "from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    ).getResultList();

    return orders.stream()
        .map(o -> o.getItems().size())
        .toList();
}
~~~

`size()` thường initialize lazy collection. Nếu dùng mapping extra-lazy, Hibernate có thể chạy COUNT thay vì load toàn bộ collection; nhưng nếu vẫn chạy COUNT cho từng order thì N+1 **chưa mất**.

### 11.4. Truy vấn trong loop không cần lazy association

~~~java
for (PurchaseOrder o : orders) {
    long itemCount = itemRepository.countByOrderId(o.getId());
    boolean refunded = refundRepository.existsByOrderId(o.getId());
    // ...
}
~~~

Đây là hai queries explicit **cho mỗi root row**. Thêm fetch join vào `PurchaseOrder.customer` sẽ không chữa `countByOrderId`/`existsByOrderId` trong vòng lặp.

Cách tối ưu là gom IDs và chạy aggregate/set-based query, hoặc projection gồm giá trị cần thiết ngay từ root query.

### 11.5. N+1 dù association EAGER

Đổi `@ManyToOne(fetch = FetchType.EAGER)` không đảm bảo JPQL root query dùng JOIN. Hibernate có thể dùng secondary SELECTs để thỏa eager loading, tùy query/fetch plan. EAGER còn làm các use cases **không cần Customer** cũng phải tải nó.

Nguyên tắc thực dụng: định nghĩa mapping LAZY có chủ đích, sau đó quyết định fetch plan **theo use case** thay vì biến mọi relation thành EAGER.

### 11.6. N+1 lồng nhau

Một endpoint có thể:
1. Load 50 orders.
2. Đọc Customer của mỗi order → tối đa 50 SELECTs.
3. Đọc Items của mỗi order → tối đa 50 SELECTs.
4. Với mỗi Item, đọc Product hay TaxRule → thêm nhiều SELECTs.

Query explosion có thể tăng rất nhanh khi serializer hoặc DTO mapper duyệt một graph sâu. Vì vậy chỉ sửa cấp đầu của N+1 chưa chắc giải quyết toàn bộ endpoint.

## 12. Tìm N+1 bằng fingerprints và query budgets

### 12.1. Tín hiệu trong JDBC trace

~~~text
SELECT ... FROM purchase_orders ORDER BY id

SELECT c.id, c.name FROM customers c WHERE c.id = ?
SELECT c.id, c.name FROM customers c WHERE c.id = ?
SELECT c.id, c.name FROM customers c WHERE c.id = ?
...
~~~

Cùng SQL shape lặp với bind IDs khác nhau là dấu hiệu:
- Lazy to-one initialization.
- Repository lookup trong loop.
- Secondary SELECTs do eager fetching.

Để quy về Java method, kết hợp SQL fingerprint với request trace/stack instrumentation thay vì chỉ đọc một danh sách SQL trộn nhiều requests.

### 12.2. Query budget không nên phụ thuộc cứng vào một con số

Với endpoint trả 30 orders, một thiết kế có thể dùng:
- Một SELECT root orders.
- Một query gom Customers.
- Một query gom Items.

Số query mục tiêu có thể là 2–3 hoặc số nhỏ hơn N tùy fetch strategy. Trong integration test, nên kiểm tra:
- Không tăng gần tuyến tính từ 10 → 50 orders.
- Một SQL fingerprint không lặp theo số order.
- Query count và cumulative JDBC time dưới ngưỡng phù hợp.
- Đáp ứng đúng dữ liệu, không duplicate/missing rows.

Đừng đếm query của fixture creation hoặc migration làm một phần của endpoint query budget.

### 12.3. Query count khác latency

50 SELECTs mỗi query 2 ms có thể làm request chậm đáng kể dù chẳng có slow query riêng lẻ. Ngược lại, một JOIN FETCH trả 100.000 rows có thể chậm hơn một vài indexed SELECTs.

Tối ưu có hai chiều: **round trips** và **row/result volume**. Cần xem execution plan, DB CPU/IO, network bytes, JVM heap và latency p95/p99 trước khi kết luận.

## 13. Lazy loading, proxies và collections

### 13.1. Đọc reference không nhất thiết tải state

~~~java
PurchaseOrder order =
    entityManager.find(PurchaseOrder.class, 42L);

Customer customer = order.getCustomer();
List<OrderItem> items = order.getItems();

// Những access sau có thể kích hoạt SQL:
String name = customer.getName();
int count = items.size();
~~~

Hibernate có thể dùng proxies, persistent collection wrappers hoặc bytecode enhancement. To-one LAZY behavior có giới hạn phụ thuộc mapping, especially inverse one-to-one và enhancement; không coi mọi association LAZY đều trì hoãn thành công theo cùng cách.

### 13.2. Kiểm tra tình trạng initialized mà không tải dữ liệu

Hibernate:

~~~java
import org.hibernate.Hibernate;

boolean customerReady =
    Hibernate.isInitialized(order.getCustomer());

boolean itemsReady =
    Hibernate.isInitialized(order.getItems());
~~~

JPA:

~~~java
import jakarta.persistence.Persistence;
import jakarta.persistence.PersistenceUtil;

PersistenceUtil util = Persistence.getPersistenceUtil();

boolean itemsLoaded = util.isLoaded(order, "items");
~~~

Hoặc:

~~~java
PersistenceUnitUtil util =
    entityManagerFactory.getPersistenceUnitUtil();

boolean customerLoaded =
    util.isLoaded(order, "customer");
~~~

`isInitialized` và `isLoaded` quan sát mức độ load theo contract provider; nó không đảm bảo **mọi nested relation** cũng đã initialized. Kiểm tra trước khi gọi getter sâu, logger/debugger có thể đã làm thay đổi trạng thái.

### 13.3. Logger hoặc debugger có thể gây lazy SQL

Một `toString()` bất cẩn:

~~~java
@Override
public String toString() {
    return "Order{id=" + id
        + ", customer=" + customer
        + ", items=" + items + "}";
}
~~~

Khi code:

~~~java
log.debug("order={}", order);
~~~

logger có thể invoke `toString()`, từ đó initialize lazy associations và gây N+1 hoặc recursion trong bidirectional graph.

Tốt hơn:

~~~java
log.debug("orderId={} status={}",
    order.getId(), order.getStatus());
~~~

Debugger watches có biểu thức `getCustomer().getName()` hoặc `getItems().size()` cũng có thể truy vấn SQL, khiến người debug vô tình tạo workload không có trong đường request bình thường.

### 13.4. Serializer cũng là một consumer của lazy associations

Controller trả entity trực tiếp:

~~~java
@GetMapping("/orders")
public List<PurchaseOrder> orders() {
    return service.findAll();
}
~~~

Jackson có thể gọi getters khi serialize, kéo theo:
- N+1 sau service method.
- `LazyInitializationException` nếu context đã đóng.
- SQL ở web layer nếu OSIV bật.
- Infinite recursion hoặc lộ fields không mong muốn.

Nên trả DTO/record được materialize trong service transaction, với fetch plan rõ.

## 14. LazyInitializationException và ranh giới Session

### 14.1. Ví dụ

~~~java
@Transactional(readOnly = true)
public PurchaseOrder load(Long id) {
    return entityManager.find(PurchaseOrder.class, id);
}
~~~

Sau khi transaction/context kết thúc, caller:

~~~java
PurchaseOrder order = service.load(42L);
String customerName =
    order.getCustomer().getName();
~~~

có thể gặp `org.hibernate.LazyInitializationException` vì Customer chưa loaded và không còn Session để initialize.

### 14.2. OSIV làm lazy loading xuất hiện ở nơi khó kiểm soát

Spring **Open EntityManager in View (OSIV)** có thể giữ EntityManager mở trong suốt HTTP request, vượt khỏi transaction service. Khi OSIV bật, JSON serializer có thể lazy-load associations và khiến endpoint chạy nhiều SQL mà service trace không bao phủ rõ.

Cấu hình Spring Boot minh họa:

~~~properties
spring.jpa.open-in-view=false
~~~

Khi OSIV tắt, cần fetch dữ liệu đủ trong transaction và trả DTO; không chữa bằng việc bật EAGER cho mọi relation. Khi OSIV bật, Session còn mở **không** đồng nghĩa cùng business transaction vẫn active trong view phase.

### 14.3. Hibernate.initialize có phạm vi giới hạn

~~~java
Hibernate.initialize(order.getCustomer());
Hibernate.initialize(order.getItems());
~~~

Có thể chủ động initialize trong Session phù hợp, nhưng gọi trong vòng lặp vẫn tạo N+1 nếu chưa có batching/fetch plan. Nó không thay thế giải pháp “fetch đúng dữ liệu cần” khi query nhiều orders.

### 14.4. Không chuyển Session/entity proxy qua async thread

`Session`/`EntityManager` không thread-safe và transaction của Spring imperative thường thread-bound. Đừng truyền managed PurchaseOrder có lazy fields tới `@Async` hoặc `parallelStream()` rồi sử dụng sau. Hãy truyền IDs/DTO và tạo transaction/context ở worker.
+
## 15. Giải pháp 1: fetch join đúng association cần dùng

### 15.1. Fetch join to-one cho danh sách orders

Nếu endpoint trả order ID và customer name, một fetch join có thể loại các SELECT phụ cho Customer:

~~~java
@Transactional(readOnly = true)
public List<PurchaseOrder> loadWithCustomers() {
    return entityManager.createQuery(
        """
        select o
        from PurchaseOrder o
        join fetch o.customer
        order by o.id
        """,
        PurchaseOrder.class
    ).getResultList();
}
~~~

Một SQL có JOIN có thể tải `PurchaseOrder` cùng `Customer`, thay vì 1 root SELECT + N SELECT Customers. `join fetch` trong HQL/JPQL yêu cầu association mapping tồn tại và có ý nghĩa fetch data ngay trong query.

Khi relationship optional, dùng `left join fetch` để không làm mất orders thiếu Customer (nếu schema/constraint cho phép):

~~~java
"select o from PurchaseOrder o left join fetch o.customer"
~~~

**Không biến mọi query thành fetch tất cả associations.** Chỉ fetch những gì application cần dùng ở unit of work đó.

### 15.2. Fetch join to-many: ít round trips nhưng có row multiplication

~~~java
@Transactional(readOnly = true)
public List<PurchaseOrder> loadWithItems() {
    return entityManager.createQuery(
        """
        select o
        from PurchaseOrder o
        left join fetch o.items
        order by o.id
        """,
        PurchaseOrder.class
    ).getResultList();
}
~~~

Nếu một order có 100 items, SQL result có thể chứa 100 rows của cùng order, mỗi row lặp order columns. Hibernate dựng entity/collection graph và có thể de-duplicate root entities theo Hibernate version (Hibernate 6 làm việc này cho những fetch-join duplicates), nhưng **database/network vẫn xử lý row multiplication**.

Vì vậy một query không đồng nghĩa tối ưu:
- Nhiều child rows có thể làm result cực lớn.
- Multiple to-many fetch joins có thể tạo Cartesian product.
- Fetch nhiều bag collections đồng thời có thể gặp `MultipleBagFetchException` trong những mapping Hibernate.
- Pagination trên collection fetch join có thể bị thực hiện ở memory hoặc cảnh báo/exception tùy config/version.

### 15.3. Pagination với to-one khác pagination với collection fetch

To-one fetch join thường có thể dùng cùng database pagination trên root rows nếu query shape phù hợp. Collection fetch join khó hơn vì một order có thể tạo nhiều joined rows, làm giới hạn SQL rows không tương ứng số parent orders cần trả.

Không làm tùy tiện:

~~~java
entityManager.createQuery(
    "select o from PurchaseOrder o left join fetch o.items",
    PurchaseOrder.class
)
.setFirstResult(0)
.setMaxResults(20)
.getResultList();
~~~

Hibernate có thể cảnh báo và áp dụng limit ở memory thay vì database, rất nguy hiểm với bảng lớn. Trong môi trường Hibernate có thể bật fail-fast setting để phát hiện kiểu pagination này, ví dụ:

~~~properties
hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

Hãy kiểm tra option và cách Spring Boot chuyển property trên version đang dùng.

## 16. Giải pháp 2: DTO projection và set-based aggregate

### 16.1. Chỉ cần DTO, không cần entity graph

Nếu endpoint chỉ cần order ID, customer name và số items, việc load toàn bộ `PurchaseOrder.items` thường không cần thiết.

Định nghĩa DTO:

~~~java
package com.example.order;

public record OrderSummary(
    Long orderId,
    String customerName,
    long itemCount
) {}
~~~

Query HQL/JPQL:

~~~java
@Transactional(readOnly = true)
public List<OrderSummary> summaries() {
    return entityManager.createQuery(
        """
        select new com.example.order.OrderSummary(
            o.id,
            c.name,
            count(i.id)
        )
        from PurchaseOrder o
        join o.customer c
        left join o.items i
        group by o.id, c.name
        order by o.id
        """,
        OrderSummary.class
    ).getResultList();
}
~~~

Ứng dụng nhận các DTO có đúng những fields cần hiển thị. Hibernate không cần initialize Customer proxy hay Items collection cho từng order để code sau gọi getter.

Điểm cần chú ý:
- `count(...)` trong JPQL/HQL trả giá trị kiểu `Long` theo contract phù hợp; record `long` dùng primitive unboxing được constructor resolution hỗ trợ trong Hibernate version tương ứng.
- Nếu sau đó join thêm một collection khác, COUNT có thể bị nhân bởi row multiplication, cần `count(distinct ...)` hoặc query riêng.
- GROUP BY, ORDER BY và aggregates có thể tốn DB resources; đo execution plan.
- DTO không managed, nên đổi field của DTO không làm Hibernate dirty-check/update DB.

### 16.2. Dùng hai query thay vì N queries

Một thiết kế khác, đặc biệt khi cần pagination:

1. Query page orders (hoặc DTO root).
2. Query item counts cho **toàn bộ IDs của page** bằng GROUP BY.
3. Merge kết quả vào DTO trong memory.

~~~java
List<Long> orderIds = page.stream()
    .map(PurchaseOrder::getId)
    .toList();

List<Object[]> counts = entityManager.createQuery(
    """
    select i.order.id, count(i.id)
    from OrderItem i
    where i.order.id in :orderIds
    group by i.order.id
    """,
    Object[].class
)
.setParameter("orderIds", orderIds)
.getResultList();
~~~

Trước query, xử lý trường hợp `orderIds.isEmpty()` để tránh `IN ()` không portable. Dựng `Map<Long, Long>` từ result và dùng `getOrDefault(id, 0L)` cho orders chưa có items.

Một query aggregate cho 20 IDs tốt hơn 20 `countByOrderId` calls nếu workload/DB plan phù hợp. Tuy nhiên DB giới hạn số bind parameters và size của IN list; với pages rất lớn, chia chunks hoặc dùng strategy khác.

### 16.3. Root page trước, children sau

Khi endpoint cần thực sự trả items:
1. Page parent IDs theo một thứ tự ổn định.
2. Query parent + to-one associations cho IDs đó.
3. Query child rows hoặc fetch collection cho tập parents đã chọn.
4. Sắp xếp output theo thứ tự IDs của page gốc.

Ví dụ bước chọn IDs:

~~~java
List<Long> ids = entityManager.createQuery(
    """
    select o.id from PurchaseOrder o
    where o.status = :status
    order by o.id
    """,
    Long.class
)
.setParameter("status", "PROCESSING")
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
~~~

Bước load:

~~~java
List<PurchaseOrder> orders = ids.isEmpty()
    ? List.of()
    : entityManager.createQuery(
        """
        select distinct o
        from PurchaseOrder o
        join fetch o.customer
        left join fetch o.items
        where o.id in :ids
        """,
        PurchaseOrder.class
    )
    .setParameter("ids", ids)
    .getResultList();
~~~

Kết quả bước hai có thể không giữ ordering giống `ids`; cần reorder trong memory. Truy vấn trong cùng transaction cũng phải chấp nhận isolation/concurrent change semantics, ví dụ một row bị xóa hoặc item được thêm giữa hai SELECTs.

Đây là **two-step pagination**, không phải giải pháp mặc định cho mọi API. Nếu chỉ cần summary, DTO projection thường đơn giản hơn.

## 17. Giải pháp 3: EntityGraph cho fetch plan tùy use case

### 17.1. Dynamic entity graph

JPA EntityGraph có thể được dùng để yêu cầu fetch những associations cụ thể.

~~~java
import jakarta.persistence.EntityGraph;

EntityGraph<PurchaseOrder> graph =
    entityManager.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = entityManager.createQuery(
    "select o from PurchaseOrder o order by o.id",
    PurchaseOrder.class
)
.setHint("jakarta.persistence.fetchgraph", graph)
.getResultList();
~~~

Intent: khi truy vấn PurchaseOrder, Customer là association thuộc fetch graph cho use case này.

Tuy nhiên:
- Provider có quyền chọn SQL execution strategy phù hợp.
- EntityGraph không bảo đảm mọi quan hệ được fetch bằng đúng một JOIN.
- Nếu graph chứa collection lớn, có thể gặp row multiplication/pagination vấn đề tương tự fetch joins.
- Một entity đã tồn tại trong persistence context có loaded state riêng; đừng coi graph hint là phép `refresh` mọi object.

### 17.2. @EntityGraph trong Spring Data JPA

Một repository:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = {"customer"})
    List<PurchaseOrder> findByStatusOrderById(String status);
}
~~~

Spring Data JPA có thể chuyển annotation này thành JPA entity graph/fetch plan. Nhưng nếu service sau đó vẫn lặp `order.getItems().size()`, N+1 collection **vẫn còn** vì graph chỉ chứa Customer.

### 17.3. Fetchgraph vs loadgraph

JPA có hints:
- `jakarta.persistence.fetchgraph`: chỉ định attributes cần eager trong graph theo graph semantics; những attributes ngoài graph có default lazy treatment theo specification/provider behavior.
- `jakarta.persistence.loadgraph`: chỉ định attributes cần eager, còn những attributes ngoài graph tuân theo mapping fetch defaults.

Chi tiết provider/version cần kiểm tra. Không dùng graph như “tắt mọi eager/association fetch” mà không xác minh SQL.

### 17.4. Đặt fetch plan ở boundary

Cùng một entity:
- Order list page cần Customer name và status.
- Order detail page cần Items.
- Reporting cần SUM/COUNT.
- Update status cần Order row và version.

Không một fetch plan EAGER toàn cục nào tối ưu cho cả bốn. EntityGraph/DTO/fetch joins nên được chọn ở repository/query phục vụ use case.

## 18. Giải pháp 4: batch fetching cho lazy associations

### 18.1. Hibernate default batch fetch size

Hibernate có thể gom nhiều lazy entity/collection initializations thành một query với nhiều IDs:

~~~properties
hibernate.default_batch_fetch_size=16
~~~

Với Spring Boot:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=16
~~~

Thay vì:

~~~sql
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
SELECT ... FROM customers WHERE id = ?;
~~~

có thể có dạng:

~~~sql
SELECT ... FROM customers WHERE id IN (?, ?, ?, ...);
~~~

Batch fetching **không bắt buộc** Hibernate gửi một query có chính xác 16 IDs mọi lần; nó phụ thuộc số proxies đang chờ initialize, cache, dialect/parameter padding, Hibernate version và fetching context.

### 18.2. @BatchSize cho một entity hoặc collection

~~~java
@Entity
@BatchSize(size = 16)
public class Customer {
    // ...
}
~~~

Hoặc:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@BatchSize(size = 16)
private List<OrderItem> items = new ArrayList<>();
~~~

Khi access một lazy association, Hibernate có thể gom thêm những associations chưa initialize trong cùng Session thành batch fetch.

Không nhầm:
- `hibernate.jdbc.batch_size`: gom INSERT/UPDATE/DELETE ở JDBC write side.
- `hibernate.default_batch_fetch_size` hoặc `@BatchSize`: gom **lazy SELECT fetches**.

Cả hai cùng có chữ “batch” nhưng giải quyết hai vấn đề khác nhau.

### 18.3. SUBSELECT fetching

Hibernate có `@Fetch(FetchMode.SUBSELECT)` ở collection mapping trong những điều kiện phù hợp:

~~~java
@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
@Fetch(FetchMode.SUBSELECT)
private List<OrderItem> items = new ArrayList<>();
~~~

Khi initialize một collection trong tập parents được nạp từ một query, Hibernate có thể load nhiều collections theo subselect liên quan tới câu parent query, thay vì một SELECT riêng cho mỗi order.

Trade-offs:
- Có thể kéo **nhiều collections hơn nhu cầu** nếu parent query trả nhiều rows.
- Tương tác với pagination/filter/transaction phải được kiểm tra.
- Có thể tăng memory/DB rows.
- Tùy Hibernate version và mapping, SQL strategy khác.

Dùng batch fetch hoặc subselect khi phù hợp với actual workload, không xem chúng là luôn tốt hơn query-specific fetch join.

### 18.4. So sánh các lựa chọn

| Kỹ thuật | Điểm mạnh | Cần thận trọng |
|---|---|---|
| To-one fetch join | Thường loại N+1 to-one cho query cụ thể | Không fetch graph không cần |
| To-many fetch join | Có thể loại N+1 collection | Row multiplication, pagination, multiple bags |
| EntityGraph | Fetch plan theo use case, JPA-centric | SQL strategy tùy provider |
| DTO constructor projection | Chỉ đọc fields cần; ít managed entities | Không phù hợp khi cần update entity |
| GROUP BY aggregate | Trả counts/sums theo tập hợp | Query plan, join fanout |
| Batch fetching | Giảm round trips cho lazy SELECTs | Vẫn lazy, có thể nhiều queries, memory |
| SUBSELECT fetching | Một query cho nhiều collections | Có thể load dư |
| Hibernate.initialize trong loop | Chủ động load một lazy object | Dễ giữ nguyên N+1 |
| Chuyển mọi quan hệ thành EAGER | Dễ nghĩ tới nhưng hiếm khi đúng toàn cục | Thường tăng SQL/memory ở use cases khác |

## 19. Vì sao “chỉ thêm cache” không chữa gốc N+1?

L2 cache có thể khiến lần chạy thứ hai không cần SELECT Customer đã cache. Nhưng:
- Cold cache/first request vẫn N+1.
- Data mutable có thể invalidation thường xuyên.
- Collection/query caches có phạm vi và coherence riêng.
- Khi query IDs chưa từng xuất hiện, DB vẫn bị truy vấn.
- Không giải quyết repository COUNT/EXISTS trong loop nếu query không cacheable/phù hợp.
- Không làm SQL plan/row multiplication trở nên tốt hơn.

**Cache là một lớp tối ưu có điều kiện**, không phải thay thế fetch-plan design.

Khi benchmark:
1. Đo cold-cache scenario.
2. Đo warm-cache scenario.
3. Đo sau invalidation/TTL.
4. So sánh query count + latency.
5. Kiểm tra stale data policy.

Nếu chỉ benchmark sau khi làm nóng cache, bạn có thể bỏ sót N+1 gây hại ở traffic thực tế.
+
## 20. Quy trình chẩn đoán có thể lặp lại

Một quy trình hiệu quả không bắt đầu bằng “thử thêm EAGER”, mà bắt đầu bằng **khoanh phạm vi và thu bằng chứng**.

### 20.1. Bước 1 — Xác định endpoint/use case và dataset

Ghi nhận:
- Endpoint hoặc job bị chậm.
- Kích thước result: 10, 100 hay 10.000 entities?
- Use case chỉ đọc, chỉ ghi hay trộn đọc/ghi?
- Cần fields/associations nào?
- Cache cold/warm?
- Có OSIV, `@Async`, scheduler hoặc transaction propagation khác?
- Hibernate/JPA/Spring/driver/DB versions.

Nếu latency chỉ tăng theo kích thước danh sách, ưu tiên điều tra N+1 và kết quả JOIN lớn. Nếu UPDATE xuất hiện ngay trước SELECT, điều tra flush. Nếu lỗi chỉ xuất hiện sau khi service trả về, điều tra lazy loading/transaction scope.

### 20.2. Bước 2 — Thu SQL count và SQL fingerprints

Dùng Hibernate SQL logger, JDBC instrumentation hoặc APM với request correlation.

Đặt câu hỏi:

| Quan sát | Giả thuyết đầu tiên |
|---|---|
| Một SELECT root + nhiều SELECT by ID cùng table | N+1 to-one hoặc repository find trong loop |
| Một SELECT root + nhiều SELECT by parent FK | N+1 collection |
| N câu COUNT/EXISTS khác ID | Repository call trong loop |
| UPDATE xuất hiện ngay trước HQL COUNT | Auto-flush do pending dirty state |
| N lần flush nhưng ít UPDATE | Flush/dirty checking overhead |
| Không có SQL nhưng object vẫn cũ | L1/L2 cache hoặc transaction visibility |
| SQL sau service method khi serialize | OSIV/lazy loading ở web layer |
| `LazyInitializationException` | Access proxy/collection ngoài Session phù hợp |
| Một JOIN SQL trả cực nhiều rows | Collection fetch row multiplication |
| Query count thấp nhưng latency cao | Slow query, lock, I/O, network hoặc large result |

Đây là điểm khởi đầu, không phải phép chẩn đoán chắc chắn từ một dấu hiệu.

### 20.3. Bước 3 — Tìm Java call sites

- Tìm loops gọi repository/EntityManager.
- Tìm DTO mapper gọi `getCustomer().getName()`, `getItems().size()`.
- Kiểm tra `toString`, logging, serialization.
- Kiểm tra explicit `flush()`, `saveAndFlush()`, `saveAllAndFlush()`.
- Kiểm tra queries chạy sau entity setters trong cùng transaction.
- Kiểm tra eager mappings và query-specific graphs.
- Kiểm tra `@Transactional(readOnly = true)`, OSIV, flush modes.
- Kiểm tra listener/callback có làm thay đổi state trước flush không.

Nên xác định **một path cụ thể** trước khi thay đổi global settings.

### 20.4. Bước 4 — Thử giả thuyết với thay đổi nhỏ

Ví dụ:
- Thay N calls `countByOrderId` bằng một aggregate query.
- Thêm `join fetch o.customer` ở đúng list query.
- Dùng DTO projection nếu chỉ cần scalars.
- Đo batch fetching size 16 trong cùng dataset.
- Chuyển một COUNT query ra ngoài loop.
- Bỏ explicit flush per row, thay bằng transaction/chunk boundary có chủ đích.
- Tắt/đánh giá OSIV và trả DTO thay entity.

Không thay đồng thời năm yếu tố rồi khẳng định biết yếu tố nào cải thiện.

### 20.5. Bước 5 — Xác nhận correctness và performance

Cần kiểm tra:
- Trả đủ root rows, không trùng/mất parents vì JOIN.
- Pagination đúng thứ tự/size.
- Count/SUM đúng khi joins có fanout.
- Không có LazyInitializationException.
- UPDATE/INSERT/DELETE vẫn được commit/rollback đúng.
- Không làm mất pending dirty changes do `clear()` hoặc MANUAL flush.
- Optimistic locking/`@Version` vẫn đúng.
- Query count, total JDBC time và response latency cải thiện thực tế.
- Cache cold/warm và production-sized dataset.

### 20.6. Sơ đồ quyết định

~~~text
Có SQL quá nhiều hoặc sai thời điểm?
                   |
                   v
        SQL loại gì là chủ yếu?
         /           |           \
      SELECT       UPDATE      Không SQL nhưng lỗi
        |            |                |
        v            v                v
  SELECT lặp ID?   Trước query?     LazyInitialization?
   /       \        /      \           /     \
 Có        Không   Có      Không      Có     Không
  |          |      |        |         |        |
  v          v      v        v         v        v
N+1 / loop  DB plan  AUTO    Explicit  Scope/  Cache/
fetch plan  /results FLUSH   flush/    fetch   snapshot/
                     query   commit    plan    other
~~~

Một request có thể cùng lúc rơi vào **hai nhánh**: loop chạy N COUNT queries và mỗi COUNT lại kích hoạt flush pending state.

## 21. Spring Data JPA và các nguồn query phát sinh gián tiếp

### 21.1. Repository method trong vòng lặp

~~~java
@Transactional(readOnly = true)
public List<Long> countsBad() {
    List<PurchaseOrder> orders = orderRepository.findAll();

    return orders.stream()
        .map(o -> itemRepository.countByOrderId(o.getId()))
        .toList();
}
~~~

Nếu 100 orders, có thể chạy 1 root SELECT + 100 COUNT statements. `@Transactional(readOnly=true)` không tự gom 100 repository calls thành một SQL.

Để tối ưu, thêm một query aggregate:

~~~java
public interface OrderItemRepository
        extends JpaRepository<OrderItem, Long> {

    @Query(
        """
        select i.order.id as orderId,
               count(i.id) as itemCount
        from OrderItem i
        where i.order.id in :ids
        group by i.order.id
        """
    )
    List<OrderCountProjection> countByOrderIds(
        @Param("ids") Collection<Long> ids
    );
}
~~~

Projection interface minh họa:

~~~java
public interface OrderCountProjection {
    Long getOrderId();
    Long getItemCount();
}
~~~

Spring Data projection alias/constructor resolution và type coercion phụ thuộc mapping/version; một DTO constructor projection tường minh là lựa chọn khác. Khi `ids` rỗng, xử lý ở service trước khi gọi query.

### 21.2. @EntityGraph trong repository

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @EntityGraph(attributePaths = "customer")
    List<PurchaseOrder> findByStatus(String status);
}
~~~

Điều này có thể giảm lazy Customer SELECTs của use case đó. Nó **không** sửa các repository COUNT calls trong loop và không bảo đảm Items được fetch.

### 21.3. @Transactional(readOnly=true) không bảo đảm lazy graph đầy đủ

~~~java
@Transactional(readOnly = true)
public List<PurchaseOrder> findAll() {
    return repository.findAll();
}
~~~

Transaction read-only cho phép làm việc trong persistence context bên trong method, nhưng nếu caller gọi getters sau khi EntityManager đóng thì lazy loading vẫn có thể lỗi. Chuyển entity sang DTO **trong method** hoặc dùng query trả projection.

### 21.4. saveAndFlush trong vòng lặp

~~~java
@Transactional
public void processBad(List<PurchaseOrder> orders) {
    for (PurchaseOrder order : orders) {
        order.markProcessing();
        repository.saveAndFlush(order);
    }
}
~~~

Nếu orders đã managed, gọi `save` thường không cần thiết để dirty checking; `saveAndFlush` mỗi iteration buộc flush thường xuyên. Thay bằng một use case chỉnh managed entities, flush khi cần hoặc commit ở boundary.

Với detached entities, `save` có thể dùng `merge`; phải hiểu entity state và kết quả managed return value. Không xóa `save` bừa bãi khi inputs là detached objects mà không thiết kế lại attach/merge behavior.

### 21.5. @Modifying và bulk SQL

~~~java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query(
    "update PurchaseOrder o set o.status = :status where o.id in :ids"
)
int bulkUpdateStatus(
    @Param("status") String status,
    @Param("ids") Collection<Long> ids
);
~~~

Spring Data `@Modifying` flags:
- `flushAutomatically` yêu cầu flush trước modifying query.
- `clearAutomatically` clear persistence context sau.

Điều đó có thể tạo một flush “không mong đợi” trong service caller. Nhưng nó phục vụ semantics đã cấu hình; đừng bỏ flag chỉ vì thấy SQL trước query mà không đánh giá pending changes.

Bulk UPDATE bỏ qua per-entity dirty checking/`@Version` tự động và không đồng bộ managed instances; dùng strategy riêng cho business invariants, version, cache và callbacks.

## 22. Integration tests để khóa chặt query behavior

### 22.1. Test cần DB/provider thật

Các lỗi N+1, auto-flush và lazy loading thuộc Hibernate runtime behavior. Unit test mock repository thường **không** phát SQL, không tạo Session real và không kiểm tra fetch plans.

Một integration test phù hợp dùng:
- Spring context/EntityManagerFactory/Hibernate version thật.
- PostgreSQL/MySQL/H2 theo mục tiêu; nếu kiểm tra dialect/SQL shape production, ưu tiên DB engine tương ứng.
- Fixtures có N orders và distinct customers.
- Cache policy được xác định.
- Transaction boundary như service production.
- Query counter/instrumentation cho đoạn đo.
- Assertions về dữ liệu và execution budget.

### 22.2. Đo Hibernate statistics với test được cô lập

Ví dụ:

~~~java
@SpringBootTest
class OrderDiagnosticsIT {

    @Autowired
    private EntityManagerFactory emf;

    @Autowired
    private OrderQueryService service;

    @Test
    void recordsHibernateStatistics() {
        SessionFactory sf = emf.unwrap(SessionFactory.class);
        Statistics stats = sf.getStatistics();

        stats.setStatisticsEnabled(true);

        long beforeFlushes = stats.getFlushCount();
        long beforeFetches = stats.getEntityFetchCount();

        List<OrderSummary> result = service.listOrders();

        long flushDelta =
            stats.getFlushCount() - beforeFlushes;
        long fetchDelta =
            stats.getEntityFetchCount() - beforeFetches;

        assertFalse(result.isEmpty());

        System.out.println("flushDelta=" + flushDelta);
        System.out.println("entityFetchDelta=" + fetchDelta);
    }
}
~~~

Giả định `OrderQueryService`/fixtures/DTO được triển khai tương ứng. Đo delta kiểu này chỉ đáng tin **khi không có traffic/tests song song** dùng cùng SessionFactory. Đối với test assertion query count nghiêm ngặt, JDBC proxy được reset theo test/connection/request thường phù hợp hơn global statistics.

### 22.3. Cách tránh false negatives

Các lỗi test phổ biến:
- Fixture setup tạo entities trong cùng L1 rồi không clear trước đo, nên root/associations đã managed.
- L2 cache warm từ test trước khiến N+1 biến mất.
- Chỉ có một Customer dùng chung cho 50 orders.
- Test method bao quanh transaction nhưng production service không có transaction tương tự.
- Đếm query bao gồm schema validation/fixture INSERTs.
- Assert exact Hibernate statistics count khi Hibernate version đổi strategy.
- Không thực sự truy cập lazy field trong test, nên không thấy SQL.
- Test chạy song song trên cùng SessionFactory global counters.

Tạo data trong transaction setup riêng, commit, dùng EntityManager mới (và evict cache có chủ đích nếu đo cold) trước khi thực thi subject method.

### 22.4. Test so sánh query growth

Ví dụ kiểm chứng không tăng tuyến tính:

~~~text
Dataset A: 10 orders / 10 distinct customers
Dataset B: 50 orders / 50 distinct customers

Bad plan:
  count(A) ~ 11
  count(B) ~ 51

Better plan:
  count(A) ~ 1..few
  count(B) ~ 1..few
~~~

Con số minh họa, không phải requirement cứng. Điều cần chứng minh là query count không tăng theo từng parent do lazy loading ở cùng path.

### 22.5. Test LazyInitializationException

Một test có thể gọi service transactional từ bên ngoài transaction test, nhận entity rồi truy cập lazy Customer sau khi context đóng; tùy OSIV/testing config, có thể xảy ra `LazyInitializationException`.

Tốt hơn kiểm thử **public contract**: service trả DTO có đầy đủ customer name/items count và không cần lazy SQL sau khi transaction kết thúc. Không buộc production phải xuất entity để test được một lỗi có thể tránh bằng thiết kế.

### 22.6. Test unexpected flush

Một test chuyên biệt:
1. Nạp managed PurchaseOrder.
2. Thay `status`.
3. Thực hiện query liên quan purchase_orders.
4. Đo flush events/JDBC UPDATE timing.
5. So sánh với query không liên quan (trong cùng controlled setup).
6. Xác nhận transaction rollback/commit semantics.

Nếu dùng `Statistics.getFlushCount()`, nhớ đó là counter tổng hợp; cần test isolation. Khi muốn xác định statement order, JDBC trace/SQL logger với correlation giúp hơn một counter đơn lẻ.

## 23. Một case study: từ 61 SELECTs về truy vấn theo nhu cầu

### 23.1. Endpoint ban đầu

~~~java
@Transactional(readOnly = true)
public List<OrderSummary> listBad() {
    List<PurchaseOrder> orders = entityManager.createQuery(
        "from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    ).getResultList();

    return orders.stream()
        .map(o -> new OrderSummary(
            o.getId(),
            o.getCustomer().getName(),
            o.getItems().size()
        ))
        .toList();
}
~~~

Với 30 orders, 30 distinct customers và 4 items/order, nếu không batch/cache, có thể gần 61 SELECTs.

### 23.2. Bản tối ưu nếu chỉ cần summary

~~~java
@Transactional(readOnly = true)
public List<OrderSummary> listBetter() {
    return entityManager.createQuery(
        """
        select new com.example.order.OrderSummary(
            o.id, c.name, count(i.id)
        )
        from PurchaseOrder o
        join o.customer c
        left join o.items i
        group by o.id, c.name
        order by o.id
        """,
        OrderSummary.class
    ).getResultList();
}
~~~

Trong trường hợp mapping/schema/DB tương ứng, query này có thể lấy đủ information trong một aggregate query; không cần initialize từng Customer proxy/Items collection trong Java.

**Đừng chỉ đếm query:** với bảng items rất lớn, GROUP BY có thể phải sort/hash nhiều rows. Cần EXPLAIN/Analyze, indexes, row counts và page size.

### 23.3. Bản tối ưu nếu cần cả items

Nếu cần danh sách Item DTO cho từng Order:
- Page root orders trước.
- Fetch Customers theo to-one.
- Query Items theo page order IDs.
- Group Items trong memory theo `orderId`.
- Trả DTO, không trả entities có lazy graph.

Mô hình:

~~~text
Query 1: page 30 orders + customers
         |
         v
Query 2: all items for order IDs 1..30
         |
         v
Map<OrderId, List<ItemDTO>>
         |
         v
30 OrderDetails DTOs, no lazy SQL in serializer
~~~

### 23.4. Bảng đối chiếu trước/sau

| Tiêu chí | Cách cũ | Cách mới |
|---|---|---|
| Root SELECT | Một query | Một query/projection |
| Customer fetch | Có thể N SELECT | JOIN/projection theo use case |
| Item count fetch | Có thể N SELECT | Aggregate GROUP BY |
| Managed entities | N orders, có thể N customers + items | Có thể chỉ DTO |
| SQL trong serializer | Có thể nếu trả entity/OSIV | Không cần cho DTO đã materialize |
| Query count tăng theo N | Có thể | Thiết kế để tránh tuyến tính |
| DB result volume | Nhiều round trips | Có thể nhiều join rows; phải đo |
| Tính đúng | Phụ thuộc lazy scope | Phụ thuộc GROUP BY/DTO mapping |
| Performance validation | SQL traces | SQL traces + DB plan + latency |

Không tự báo “đã giảm 61 xuống 1” nếu chưa thực nghiệm trên mapping/database thật. Bảng là phân tích khả năng, không phải kết quả benchmark.
+
## 24. Những quan sát bổ sung trong production

### 24.1. Đếm truy vấn theo endpoint, không chỉ toàn ứng dụng

Một dashboard tổng số JDBC statements/giây không trả lời “endpoint nào tạo N+1”. Cần liên kết số queries với:
- Endpoint/route hoặc scheduled job.
- Trace/request ID.
- Transaction/Session boundary.
- SQL fingerprint.
- Số rows trả về.
- Tổng thời gian JDBC và p95/p99 latency.

Nếu request thực hiện 100 queries nhưng cả application đang có 10.000 queries/giây, aggregate metrics có thể che vấn đề. Trace cấp request giúp tìm “100 SELECTs tới customers” xuất hiện trong một call path.

### 24.2. Query count phải đi cùng database metrics

Những câu SQL lặp không phải lúc nào cũng là bottleneck duy nhất. Khi điều tra, cũng xem:
- PostgreSQL `pg_stat_statements`/slow query telemetry nếu có.
- MySQL Performance Schema/slow query log nếu phù hợp.
- SQL Server Query Store hoặc DMVs.
- DB CPU, I/O, cache hit, locks và waits.
- Connection pool wait/connection hold time.
- Network latency và payload.
- JVM heap/GC, số managed entities.
- Query execution plan và index usage.

Những công cụ này có permissions/overhead/version-specific configuration. Cần tránh bật tracing quá chi tiết trên production traffic lớn nếu chưa đánh giá chi phí.

### 24.3. SQL comment để liên kết query với use case

Hibernate/JPA có cơ chế query comments theo version, ví dụ với Hibernate Query API có thể đặt comment cho SQL generated:

~~~java
Session session = entityManager.unwrap(Session.class);

List<PurchaseOrder> orders =
    session.createSelectionQuery(
        "from PurchaseOrder o order by o.id",
        PurchaseOrder.class
    )
    .setComment("catalog-order-list")
    .getResultList();
~~~

Nếu SQL comments được bật theo cấu hình phù hợp, comment có thể xuất hiện trong generated SQL và hỗ trợ truy tìm use case.

Không đặt request ID đầy đủ, email, token hay input người dùng không được kiểm soát vào SQL comment. Nếu comment khác nhau trên mỗi request, có thể ảnh hưởng SQL fingerprint/statement cache/DB query grouping tùy driver và DB.

### 24.4. Tránh đo query count sai phạm vi

Một request có thể dùng:
- Hibernate JPA DataSource.
- `JdbcTemplate` qua DataSource thứ hai.
- REST/gRPC call tới service khác, nơi lại thực hiện SQL.
- Read replica/primary routing.
- Background events sau commit.

Một Hibernate `SessionFactory Statistics` chỉ phản ánh provider/factory của nó, **không thể tự đếm SQL từ mọi service hoặc DB connection**.

Để có performance profile end-to-end, kết hợp distributed tracing + JDBC metrics + server metrics. Trong test cô lập Hibernate module, chỉ cần instrumentation tới DataSource mục tiêu cũng có thể đủ.

### 24.5. Đặt ngưỡng cảnh báo có ngữ cảnh

Một dashboard có thể theo dõi:
- p95 SQL count per request của route.
- p95 cumulative JDBC time.
- Distribution of repeated SQL fingerprints.
- Flush count/session.
- Entity/collection fetch count.
- LazyInitializationException occurrences.
- Connection pool wait.
- Number of DB queries during JSON serialization.

Ngưỡng phù hợp khác nhau giữa một report tải 10.000 rows và một API đọc single order. Alert nên gắn vào user impact và baseline, tránh bắn cảnh báo vì mỗi lần query count tăng một chút.

## 25. Bảng lỗi và hiểu lầm thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra / hướng xử lý |
|---|---|---|
| UPDATE xuất hiện trước COUNT query | Hibernate AUTO flush pending changes | Tìm managed mutations trước query, kiểm tra query spaces |
| UPDATE không xuất hiện ngay sau setter | Dirty checking chờ flush | Phân biệt Java state, flush và commit |
| `flush()` chạy nhưng transaction khác không thấy update | Chưa commit, isolation | Kiểm tra transaction boundaries/snapshot |
| `saveAndFlush` trong loop chậm | Flush mỗi entity, overhead và giảm JDBC batching | Gom operations; flush theo boundary có chủ đích |
| Query trong loop gây N COUNT statements | Repository count/exists trong iteration | GROUP BY/IN aggregate query |
| Một SELECT root + N SELECT Customers | Lazy to-one hoặc eager secondary selects | Fetch join, EntityGraph, DTO projection |
| Một SELECT root + N SELECT Items | Lazy collection | Batch fetch, subselect, query items theo IDs |
| Chuyển EAGER nhưng SELECT vẫn nhiều | JPQL fetch plan/secondary selects | Query-specific fetch plan, log SQL |
| Một JOIN FETCH trả rất nhiều rows | To-many row multiplication | Projection/two-step page/batch fetching |
| Pagination collection fetch bị cảnh báo | JOIN FETCH to-many với limit | Page IDs trước rồi load children |
| `MultipleBagFetchException` | Fetch nhiều bag collections đồng thời | Tách queries/fetch strategies, đổi mapping đúng |
| Debugger mở entity làm SQL tăng | Watch/toString/equals truy cập lazy fields | Debug scalars, tránh deep getter |
| JSON serialization gọi SQL | OSIV, entity được trả trực tiếp | DTO trong service, fetch đủ |
| `LazyInitializationException` | Proxy/collection chưa load, context đóng | Transaction fetch plan/DTO; không bật EAGER toàn cục |
| `Hibernate.initialize` trong loop không giúp | Vẫn initialize một collection mỗi iteration | Batch fetch hoặc load theo tập |
| Local nhanh, production N+1 | N nhỏ, cache warm, DB gần | Test data đại diện, cold cache và network latency |
| Hibernate statistics query count không khớp JDBC log | Counters đo tầng khác nhau | JDBC instrumentation khi cần count statements |
| Statistics thay đổi do tests khác | SessionFactory-wide counters | Isolate tests/measure per request |
| SQL logger nhiều UPDATE dù dùng JDBC batch | Logical SQL executions khác driver batches | Đo `executeBatch()` |
| SQL log trống nhưng SQL từ JdbcTemplate | Logger chỉ Hibernate | Instrument DataSource hoặc Spring JDBC |
| Query lặp hình dạng nhưng bind IDs bị ẩn | Prepared statements | Fingerprint + safe bind metadata trong test |
| Một slow endpoint không có slow SQL | N truy vấn nhanh cộng lại | Đếm toàn request và cumulative JDBC time |
| `@Transactional(readOnly=true)` vẫn có SQL SELECT lặp | Read-only không chữa fetch plan | DTO/joins/batch fetch |
| `MANUAL` “chữa” SQL log nhưng mất update | Flush mode đổi behavior ghi | Restore AUTO/use case transaction đúng |
| `clear()` khiến thay đổi mất | Clear trước flush | Flush pending changes nếu cần, không clear tùy tiện |
| Cached entity đã load nên test không thấy N+1 | L1/L2 warm | Tách fixture, context mới/cold cache |
| 30 orders chỉ 1 Customer SELECT | Nhiều orders cùng một Customer | Test distinct customer IDs |
| Eager graph làm heap tăng | Fetch dư/large result | Giới hạn projection, paginate/two-query |
| Query result đúng nhưng request chậm | Lock/DB execution/row volume | EXPLAIN/DB waits/cumulative timings |
| Lazy proxy giữ qua async job | Session/thread scope sai | Truyền ID/DTO, mở transaction trong worker |
| Auto-flush bị quy sai cho reader | Writer trước đó sửa managed entity trong cùng context | Trace toàn unit of work, không chỉ query method |

## 26. Bài tập thực hành

### Bài 1 — Flush hay commit?

~~~java
order.markProcessing();
entityManager.flush();
throw new IllegalStateException("rollback");
~~~

**Hỏi:** `flush` đã gửi UPDATE thì row có chắc được commit không?

**Đáp án:** Không. Flush gửi pending SQL trong transaction; exception có thể khiến transaction rollback.

### Bài 2 — Auto-flush trước query

Managed Order#42 được đổi status thành PROCESSING, sau đó JPQL COUNT từ `PurchaseOrder` chạy trong `AUTO` mode.

**Hỏi:** Vì sao có UPDATE trước COUNT?

**Đáp án:** Query liên quan table/entity có pending changes; provider có thể flush để query phản ánh state vừa thay đổi theo AUTO semantics.

### Bài 3 — Query không liên quan

Sau khi đổi PurchaseOrder, service query `Customer` độc lập.

**Hỏi:** Hibernate AUTO có bắt buộc flush trước mọi SELECT không?

**Đáp án:** Không. Với query spaces không liên quan, Hibernate có thể trì hoãn flush; behavior còn phụ thuộc API/path/version.

### Bài 4 — Đếm flush bằng SQL UPDATE count

Một request có 4 flush events nhưng chỉ 1 UPDATE.

**Hỏi:** Có mâu thuẫn không?

**Đáp án:** Không. Flush có thể kiểm tra context nhưng không có dirty SQL cần gửi. `getFlushCount()` không bằng UPDATE count.

### Bài 5 — N+1 Customer

Một query lấy 50 orders có 50 distinct Customers. Vòng lặp gọi `getCustomer().getName()`.

**Hỏi:** Có thể xảy ra bao nhiêu SELECT nếu không cache/batch fetching?

**Đáp án:** Mô hình tối đa gần 1 root + 50 customer = 51 SELECTs, nhưng actual counts phụ thuộc mappings/cache.

### Bài 6 — Orders cùng Customer

50 orders đều tham chiếu cùng Customer#1, trong một persistence context.

**Hỏi:** Có chắc chạy 50 Customer SELECTs không?

**Đáp án:** Không. Identity map có thể reuse Customer, nên dataset này dễ bỏ sót N+1.

### Bài 7 — COUNT trong loop

~~~java
for (PurchaseOrder o : orders) {
    itemRepository.countByOrderId(o.getId());
}
~~~

**Hỏi:** Đây có phải lazy loading không?

**Đáp án:** Không nhất thiết. Đây là N explicit repository queries, dù association không được truy cập. Thay bằng aggregate query theo danh sách IDs.

### Bài 8 — EAGER có đủ không?

Developer đổi `@ManyToOne` thành `EAGER`.

**Hỏi:** Query gốc chắc chỉ còn một SQL không?

**Đáp án:** Không. EAGER có thể dùng secondary selects, và làm các queries khác tải dư data. Dùng fetch plan theo use case.

### Bài 9 — Fetch join to-one

**Hỏi:** HQL nào có thể nạp Order cùng Customer để vòng lặp không phải lazy-load Customer?

**Đáp án:**

~~~java
"select o from PurchaseOrder o join fetch o.customer"
~~~

### Bài 10 — Fetch join collection và pagination

Query có `left join fetch o.items` kết hợp `setMaxResults(20)`.

**Hỏi:** Rủi ro gì?

**Đáp án:** Row multiplication và pagination ở memory/cảnh báo/exception tùy provider config. Có thể page parent IDs trước rồi query items cho page.

### Bài 11 — Multiple bag collections

Entity có hai `List` collection dạng bags, query fetch join cả hai.

**Hỏi:** Lỗi nào có thể gặp?

**Đáp án:** `MultipleBagFetchException` trong Hibernate khi fetch đồng thời những bag mappings không được hỗ trợ. Tách query hoặc đổi fetch strategy/mapping theo semantics thật.

### Bài 12 — DTO projection

Endpoint chỉ cần OrderId, CustomerName, ItemCount.

**Hỏi:** Có cần load `order.getItems()` không?

**Đáp án:** Không. Dùng DTO constructor projection với JOIN/GROUP BY hoặc aggregate query riêng.

### Bài 13 — BatchSize

`hibernate.default_batch_fetch_size=16`.

**Hỏi:** Nó điều khiển JDBC UPDATE batching hay lazy SELECT fetching?

**Đáp án:** Lazy SELECT fetching. `hibernate.jdbc.batch_size` là setting khác cho JDBC DML batching.

### Bài 14 — SUBSELECT

**Hỏi:** `@Fetch(FetchMode.SUBSELECT)` có thể giảm N collection SELECTs nhưng có tác dụng phụ gì?

**Đáp án:** Nó có thể nạp nhiều collections hơn caller cần và làm tăng row/memory volume; kiểm thử với parent query và pagination thực tế.

### Bài 15 — isInitialized

~~~java
Hibernate.isInitialized(order.getItems());
~~~

**Hỏi:** Có chủ đích initialize collection không?

**Đáp án:** Không. Nó kiểm tra trạng thái initialized. `Hibernate.initialize(...)` mới chủ động initialize.

### Bài 16 — toString

Entity `toString()` duyệt `items` và `customer`.

**Hỏi:** Gọi log.debug có thể làm thay đổi SQL workload không?

**Đáp án:** Có. Logger có thể gọi toString, kích hoạt lazy loading; log scalar IDs/status thay vì cả graph.

### Bài 17 — OSIV

OSIV bật, service read-only trả entity và JSON serializer lazy-load items.

**Hỏi:** Có phải các SELECT serializer luôn nằm trong service transaction không?

**Đáp án:** Không. Session/context có thể còn mở sau transaction service kết thúc; SQL có thể chạy ở web layer.

### Bài 18 — Lỗi LazyInitializationException

**Hỏi:** Cách sửa nên ưu tiên điều gì thay vì EAGER toàn cục?

**Đáp án:** Query/fetch graph đủ dữ liệu trong transaction và chuyển sang DTO; không dựa vào proxy sau khi context đóng.

### Bài 19 — Stats scope

Service đang chạy dưới traffic production, developer lấy delta `Statistics.getQueryExecutionCount()` quanh một request.

**Hỏi:** Delta có chắc chỉ thuộc request đó không?

**Đáp án:** Không. Statistics thường gắn SessionFactory và traffic đồng thời có thể làm số đo nhiễu. Dùng request-scoped JDBC tracing/proxy.

### Bài 20 — SQL logging và batching

Hibernate SQL logger cho 100 dòng INSERT cùng shape.

**Hỏi:** Có chắc driver gửi 100 network round trips không?

**Đáp án:** Không. JDBC batching/rewrite có thể gom executions. Đo addBatch/executeBatch và DB metrics.

### Bài 21 — Test không tìm thấy N+1

Test tạo orders rồi query bằng cùng EntityManager, tất cả Customers đã managed.

**Hỏi:** Nên làm gì?

**Đáp án:** Tách fixture setup, flush/clear hoặc transaction/context mới, kiểm soát cache state và dùng distinct customer IDs.

### Bài 22 — Read-only và writes

Method `@Transactional(readOnly=true)` đổi managed status rồi không thấy UPDATE.

**Hỏi:** Có nên kết luận Hibernate mất dữ liệu?

**Đáp án:** Trước hết kiểm tra read-only/flush mode settings. Use case ghi phải dùng transaction ghi phù hợp; đừng dựa dirty checking dưới read-only optimization.

### Bài 23 — @Modifying(clearAutomatically)

Spring Data repository chạy bulk UPDATE có `clearAutomatically=true`.

**Hỏi:** Điều này có thể ảnh hưởng caller thế nào?

**Đáp án:** Clear detach toàn bộ managed entities trong context; nếu caller còn pending changes hoặc giữ Java references, phải có quy tắc flush/context rõ ràng.

### Bài 24 — Cải thiện nhưng vẫn chậm

Sau khi giảm từ 51 SELECTs về 1 JOIN FETCH, endpoint vẫn chậm vì JOIN trả 250.000 rows.

**Hỏi:** Bước tiếp theo?

**Đáp án:** Đo execution plan, result volume, pagination, index và memory. Cân nhắc projection/two-step page/aggregate thay vì chỉ tối thiểu hóa SQL count.

### Bài 25 — Một query trong loop vừa tạo N+1 vừa auto-flush

Loop sửa Order status rồi chạy COUNT orders trong mỗi iteration.

**Hỏi:** Có hai vấn đề nào?

**Đáp án:** N lần COUNT (query-in-loop) và các auto-flush trước query liên quan; giải pháp thường là gom state changes và query aggregate một lần theo business semantics.

### Bài 26 — Metric nào đáng theo dõi?

**Hỏi:** Chỉ đo `getEntityLoadCount()` đã đủ phân biệt root SELECT với lazy loads chưa?

**Đáp án:** Chưa. Kết hợp entity/collection fetch counters, SQL/JDBC statement count, fingerprints, request trace và timings.

### Bài 27 — Transaction/Session và @Async

Một worker async dùng Hibernate proxy từ request transaction ban đầu.

**Hỏi:** Vì sao nguy hiểm?

**Đáp án:** Hibernate Session không thread-safe, transaction context không tự truyền giữa threads; worker nên nhận ID/DTO rồi tự load trong transaction mới.

### Bài 28 — Thiết kế test tăng dữ liệu

Khi tăng orders từ N=10 lên N=100, SQL count tăng gần 10 lần.

**Hỏi:** Có phải N+1 chắc chắn không?

**Đáp án:** Đây là dấu hiệu mạnh nếu cùng SQL fingerprints lặp theo IDs, nhưng cần kiểm tra root pagination, query design, cache và các repository calls trước khi kết luận chính xác nguồn.

## 27. Tổng kết

### 27.1. Đừng trộn lẫn ba nguyên nhân

| Vấn đề | Tín hiệu nổi bật | Tư duy khắc phục |
|---|---|---|
| **Flush ngoài dự kiến** | UPDATE/INSERT/DELETE xuất hiện trước query hoặc nhiều flushes | Xác định dirty state, flush mode, query spaces, transaction boundaries |
| **Truy vấn trong vòng lặp / N+1** | N câu SELECT/COUNT/EXISTS cùng shape theo N entities | Query theo tập hợp, fetch plan, projection, batch fetching |
| **Tải trì hoãn** | Getter/serializer kích hoạt SELECT hoặc LazyInitializationException | Materialize dữ liệu cần trong Session; trả DTO, kiểm soát OSIV |

### 27.2. Các quy tắc quan trọng

1. Một setter trên managed entity không nhất thiết phát UPDATE ngay: Hibernate có write-behind và dirty checking.
2. `flush` khác `commit`. Auto-flush trước JPQL/HQL query liên quan có thể hoàn toàn đúng để bảo đảm kết quả.
3. Đừng tắt flush mode để che dấu SQL khi chưa hiểu tính nhất quán cần thiết.
4. N+1 không chỉ do LAZY: repository call trong loop và EAGER secondary SELECTs cũng là nguồn phổ biến.
5. `FetchType.EAGER` toàn cục không phải công thức chữa N+1.
6. Fetch join/EntityGraph/batch fetching/projection có trade-offs về rows, memory, pagination và portability.
7. Logger, debugger, `toString` hoặc JSON serializer có thể là nơi lazy loading thực sự xảy ra.
8. `LazyInitializationException` báo rằng dữ liệu cần chưa được initialize trước khi Session/context thích hợp kết thúc.
9. Hibernate Statistics, SQL logger, StatementInspector và JDBC proxy nhìn vào **các tầng khác nhau**; không coi counter của tầng này đồng nghĩa counter tầng kia.
10. Kết luận performance cần query count **và** cumulative DB time, row volume, end-to-end latency và integration tests với dữ liệu đại diện.

### 27.3. Quy trình ghi nhớ

~~~text
1. Xác định use case chậm/sai SQL timing
              |
              v
2. Correlate request -> SQL fingerprints/count/timings
              |
              v
3. Phân loại: AUTO FLUSH / N+1 / LAZY / SLOW QUERY
              |
              v
4. Tìm Java caller + transaction/fetch scope
              |
              v
5. Chọn thay đổi nhỏ, đúng nguyên nhân
              |
              v
6. Integration test + cold/warm + DB execution metrics
              |
              v
7. Giữ query budget/regression guard phù hợp
~~~

Một câu hỏi chẩn đoán rất hữu ích:

> “Dữ liệu này thực sự cần được load và đồng bộ **khi nào**, do **code path nào**, và đã có **bằng chứng SQL/transaction** cho giả thuyết đó chưa?”

## Tài liệu chính thức

- [Hibernate ORM Documentation](https://docs.hibernate.org/orm/) — chọn User Guide/Javadocs theo version của dự án.
- [Hibernate ORM 6.6 User Guide](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html) — flushing, batch fetching, fetching strategies, statistics, query plan.
- [Hibernate ORM 6.6 Introduction](https://docs.hibernate.org/orm/6.6/introduction/html_single/) — Sessions, fetching và persistence context.
- [Hibernate ORM 6.6 FlushMode Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/FlushMode.html) — `AUTO`, `COMMIT`, `ALWAYS`, `MANUAL`.
- [Hibernate ORM 6.6 Hibernate class Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Hibernate.html) — `isInitialized`/`initialize`.
- [Hibernate ORM 6.6 Statistics Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/stat/Statistics.html) — counters và measurement semantics.
- [Hibernate ORM 6.6 StatementInspector Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/resource/jdbc/spi/StatementInspector.html) — SQL inspection.
- [Hibernate ORM 6.6 @BatchSize Javadoc](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/annotations/BatchSize.html) — Hibernate batch fetching.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — EntityManager, fetch types, flush modes, entity graphs.
- [Spring Framework — Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html) — transaction boundaries/proxy.
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/) — repositories, projections, entity graphs, modifying queries.
- [Spring Boot Data SQL / JPA](https://docs.spring.io/spring-boot/reference/data/sql.html#data.sql.jpa-and-spring-data) — JPA integration và OSIV.
- [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — đọc execution plans và row estimates.

> Ví dụ và log trong bài là mô hình hướng dẫn cho Hibernate ORM 6.x, Jakarta Persistence và Spring. Hành vi flush/fetch, logger categories, statistics và SQL generation phụ thuộc Hibernate version, cache, JDBC driver, database dialect, query shape và transaction scope. Mọi giả thuyết hiệu năng cần được xác nhận trên stack và dataset phù hợp; SQL ít hơn không tự động có nghĩa query nhanh hơn hoặc đúng hơn.






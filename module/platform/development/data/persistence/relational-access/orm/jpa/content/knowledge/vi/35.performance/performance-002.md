# Phân biệt nút thắt SQL, kế hoạch tải và chi phí quản lý entity

Ứng dụng JPA có thể chậm dù mỗi dòng Java trông rất đơn giản:

```java
List<Order> orders = em.createQuery(
    "SELECT o FROM Order o WHERE o.status = :status",
    Order.class
).setParameter("status", OrderStatus.PAID)
 .getResultList();
```

Một truy vấn như trên có thể chậm vì những nguyên nhân **khác nhau về bản chất**:

- **Nút thắt SQL/database:** Một câu SQL mất nhiều thời gian do thiếu chỉ mục, lọc/sắp xếp tốn kém, join sai, đọc quá nhiều rows, lock waits, I/O hoặc server quá tải.
- **Nút thắt kế hoạch tải (*fetch plan*):** JPA phát sinh quá nhiều câu SQL do quan hệ lazy (N+1), hoặc một `JOIN FETCH` kéo về một lượng rows lặp rất lớn. Vấn đề nằm ở **khi nào và bằng cách nào** dữ liệu liên quan được tải.
- **Chi phí quản lý entity:** SQL thực tế đã khá nhanh, nhưng ứng dụng vẫn chậm do tạo hàng chục nghìn đối tượng, đăng ký chúng vào persistence context, quản lý identity, dirty checking, snapshots, collection wrappers, proxies, flush, garbage collection và ánh xạ kết quả.

Ngoài ba nhóm này, một request còn có thể bị ảnh hưởng bởi **connection pool, serialization, network, transaction contention, cache và code ứng dụng**. Đừng gọi mọi request chậm là “SQL chậm” hoặc chữa mọi màn hình chậm bằng thêm `JOIN FETCH`.

Bài **“Phân biệt nút thắt SQL, kế hoạch tải và chi phí quản lý entity”**, thuộc chương **Hiệu năng** trong chủ đề **Data Persistence Relational Access ORM JPA**, xây dựng phương pháp chẩn đoán theo **bằng chứng đo đạc**: xác định thời gian biến mất ở đâu, đọc được SQL thật và kế hoạch thực thi, nhận ra N+1/over-fetch, chọn giữa entity và DTO projection, giới hạn kích thước persistence context, và kiểm tra tối ưu dưới workload thực.

Các ví dụ dùng Java 17+, Jakarta Persistence (`jakarta.persistence`) và SQL quan hệ. Những tính năng như Hibernate `Statistics`, `@BatchSize`, `@Fetch(SUBSELECT)`, JDBC batching, read-only queries hoặc `StatelessSession` là **provider-specific**, sẽ được ghi rõ. Các câu `EXPLAIN` khác nhau theo database: cần dùng cú pháp của PostgreSQL/MySQL/SQL Server/Oracle đang triển khai, không xem ví dụ một dialect là SQL portable.

**Nguyên tắc trung tâm: đo trước, phân loại nguyên nhân, thay đổi đúng một nhóm yếu tố, đo lại cùng điều kiện.**

---

## 1. Mô hình chi phí của một request JPA

Có thể hình dung tổng thời gian gần đúng:

```text
T_request
  ≈ T_connection_wait
  + T_sql_roundtrips
  + T_database_execution_and_lock_waits
  + T_result_transfer
  + T_jdbc_result_processing
  + T_entity_hydration_and_persistence_context
  + T_business_mapping
  + T_serialization
  + T_other
```

Các thành phần có thể chồng lấn (ví dụ network và streaming/JDBC processing), nên đây **không phải đẳng thức đo chính xác**. Mục đích là biết muốn tối ưu phần nào.

Ví dụ ba request đều mất khoảng 800 ms nhưng nguyên nhân khác:

| Request | SQL count | SQL execution | Rows từ DB | JVM work sau DB | Chẩn đoán gợi ý |
| --- | ---: | ---: | ---: | ---: | --- |
| A | 1 | 680 ms | 40 | 30 ms | Một SQL/database plan chậm |
| B | 101 | ~480 ms cộng dồn | 300 | 40 ms | N+1/fetch plan |
| C | 1 | 35 ms | 100.000 | 570 ms | Hydration, managed entities, serialization/heap |

Các con số **chỉ minh họa**, không phải benchmark hoặc chỉ tiêu hiệu năng mặc định.

Nếu sửa A bằng `JOIN FETCH`, SQL vẫn có thể chậm. Nếu sửa B bằng thêm một index mà vẫn giữ 101 roundtrips, độ trễ còn cao. Nếu sửa C bằng `@BatchSize` nhưng màn hình chỉ cần ba trường, bạn vẫn tạo rất nhiều managed entities không cần thiết.

## 2. Ba nhóm nguyên nhân cần giữ tách biệt

| Nhóm | Tín hiệu thường gặp | Cần đo | Hướng sửa thường phù hợp |
| --- | --- | --- | --- |
| SQL/database | Một vài SQL nhưng mỗi câu lâu; lock waits, sort/spill, table scan lớn | Query latency, actual plan, buffer/I/O, indexes, row estimates | SQL shape, predicate, index, schema, transaction/lock |
| Kế hoạch tải | Nhiều SQL tương tự lặp theo số cha; hoặc JOIN trả rows lặp nhiều | Statement count, SQL patterns, row count, associations accessed | Fetch join có chọn lọc, EntityGraph, DTO, batch fetching, split query |
| Quản lý entity | SQL nhanh nhưng heap/CPU/GC cao; flush chậm; session giữ nhiều objects | Allocation, heap histogram, persistence-context size, flush time | DTO/scalar, paging/chunking, read-only settings, flush/clear an toàn |
| Không thuộc cả ba | Chờ connection, network, JSON, thread pool | Pool wait, tracing spans, serialization profiles | Pool/load/concurrency/application design |

**Một màn hình có thể bị nhiều nút thắt cùng lúc.** Ví dụ N+1 tạo hàng trăm SQL; mỗi SQL lại thiếu index; sau đó serializer duyệt graph lớn gây memory pressure. Phải ưu tiên theo tỷ lệ đóng góp được đo.

## 3. Phân biệt độ trễ, thông lượng và tài nguyên

Các metric phản ánh các câu hỏi khác nhau:

- **Latency:** một request mất bao lâu? P50, P95, P99 phản ánh trải nghiệm và tail latency.
- **Throughput:** xử lý bao nhiêu requests/jobs mỗi giây ở mức tải cho trước?
- **SQL count:** mỗi use case tạo bao nhiêu database roundtrips?
- **DB execution time:** SQL dành thời gian ở database bao lâu, kể cả waits?
- **Rows read/returned:** DB quét bao nhiêu rows, trả về bao nhiêu rows?
- **Bytes transferred:** result set lớn đến mức nào?
- **CPU/allocations:** Java phải tạo/xử lý bao nhiêu objects?
- **Heap/GC:** persistence context và DTO/JSON graph giữ bao nhiêu memory?
- **Connection wait:** phải chờ lấy JDBC connection bao lâu?
- **Lock wait:** SQL đang chờ row/table lock hay thực thi thực sự?
- **Error/retry rate:** có deadlock, optimistic conflict hoặc timeouts gây lặp công việc?

Một SQL count thấp **không** tự chứng minh nhanh; một SQL count cao **không** tự chứng minh cần JOIN tất cả quan hệ. Thời gian thực và kích thước dữ liệu mới cho biết ưu tiên.

### P95 khác trung bình

Nếu 95% requests chạy 50 ms và 5% kéo dài 3 giây do lock contention, trung bình có thể che vấn đề người dùng gặp. Khi đánh giá thay đổi JPA, đo P95/P99 cùng tải đồng thời thực tế, không chỉ một lần chạy local.

---

## 4. Mô hình dữ liệu ví dụ

Giả sử hệ thống bán hàng:

```text
Customer (1) ───── (N) PurchaseOrder
                         │
                         ├── (N) OrderLine ── (1) Product
                         │
                         └── (1) ShippingAddress
```

Order có customer, nhiều lines; mỗi line trỏ Product. Màn hình “Danh sách 20 đơn hàng gần đây” chỉ hiển thị:

- Mã đơn.
- Thời điểm tạo.
- Tên khách hàng.
- Tổng tiền.
- Trạng thái.

Màn hình “Chi tiết một đơn hàng” lại cần:

- Các thông tin ở trên.
- Danh sách lines và product name.
- Địa chỉ giao hàng.

Hai màn hình có **fetch plan khác nhau**. Nếu dùng một mapping mặc định “lúc nào cũng tải Customer + Lines + Product + Address”, màn hình danh sách có thể over-fetch. Nếu để tất cả lazy mà không kiểm soát truy cập, màn hình chi tiết có thể N+1.

### Entity mapping tham khảo

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    private Instant createdAt;

    private BigDecimal totalAmount;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public Instant getCreatedAt() { return createdAt; }
    public OrderStatus getStatus() { return status; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public Customer getCustomer() { return customer; }
    public List<OrderLine> getLines() { return lines; }
}
```

```java
@Entity
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    private Product product;

    private int quantity;
    private BigDecimal unitPrice;

    protected OrderLine() {}

    public Product getProduct() { return product; }
    public int getQuantity() { return quantity; }
}
```

Ví dụ lược bỏ constructor và những fields phụ không liên quan. Mục đích là hình dung fetch behavior, không phải một domain model hoàn chỉnh có mọi invariant.

## 5. Bắt đầu từ một use case cụ thể

Đừng tối ưu một entity class “toàn cục” khi chưa biết màn hình nào bị chậm.

Một bản mô tả use case:

```text
API: GET /orders?status=PAID&page=0&size=20

Trả về:
- 20 OrderSummary DTOs
- id, createdAt, status, customerName, totalAmount

Không cần:
- OrderLines
- Product details
- ShippingAddress
- Payment events

Tải thực tế:
- 200 requests/giây vào giờ cao điểm
- Dữ liệu 2 triệu Orders
- 500.000 Customers

Vấn đề quan sát:
- P95 latency cao
- DB CPU bình thường hay cao?
- SQL count mỗi request?
- Heap allocation mỗi request?
```

Những con số trên chỉ là tình huống minh họa. Nhưng **yêu cầu trả dữ liệu** là căn cứ quyết định có cần entity graph hay DTO.

Nếu endpoint chỉ cần năm giá trị, mọi dữ liệu thêm được nạp là chi phí cần biện minh.

## 6. Thiết lập baseline trước khi chỉnh code

Đối với một API hoặc batch, ghi nhận:

1. Input parameters và page size.
2. Dataset size và phân bố dữ liệu liên quan.
3. Số requests đồng thời.
4. DB engine/version, indexes và statistics state.
5. Warm-up/JIT và trạng thái cache.
6. JDBC connection pool size/wait.
7. Tổng SQL statements và từng pattern.
8. DB execution time, row counts, lock waits.
9. JVM CPU/allocations/GC.
10. P50/P95/P99 end-to-end latency.
11. Transaction scope và flush mode.
12. Version JPA provider, database driver và cache config.

Không nhất thiết bật mọi metric ở production với mức logging cao. Có thể dùng tracing/sampling, profiling trong staging và báo cáo DB để tránh overhead hoặc lộ parameters.

Baseline là điều kiện cần để biết sau thay đổi **thứ gì thật sự cải thiện và thứ gì bị xấu đi**.

---

## 7. Nút thắt nhóm 1: một câu SQL thực sự chậm

Ví dụ JPQL:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.status = :status " +
    "ORDER BY o.createdAt DESC",
    PurchaseOrder.class
).setParameter("status", OrderStatus.PAID)
 .setMaxResults(20)
 .getResultList();
```

SQL do provider tạo có thể gần như:

```sql
SELECT
    o.id,
    o.status,
    o.created_at,
    o.total_amount,
    o.customer_id
FROM purchase_orders o
WHERE o.status = ?
ORDER BY o.created_at DESC
FETCH FIRST 20 ROWS ONLY;
```

Đây chỉ là SQL minh họa: cú pháp paging và các cột có thể khác theo dialect/provider, mappings và inheritance.

Nếu bảng có hàng triệu records nhưng thiếu index phù hợp, DB có thể quét/lọc/sắp xếp lượng lớn data chỉ để trả 20 rows.

### SQL count thấp nhưng latency cao

```text
1 SQL / request
DB elapsed: 600 ms
Result: 20 rows
JVM mapping: 5 ms
```

Đây thường là **SQL-plan/index/I/O/lock** problem, không phải N+1 hoặc chi phí quản lý 20 entity.

## 8. Đọc SQL thật, không chỉ JPQL

JPQL là ngôn ngữ trên entity model, nhưng database thực thi **SQL đã được dịch**.

Cần thu thập:

- SQL text thực tế.
- Bind parameters (chỉ khi an toàn; tránh log PII/secrets).
- Execution duration.
- Rows returned/fetched.
- Transaction context.
- Indexes đang được sử dụng.
- Database plan.
- Thời gian chờ lock.
- Cấu trúc JOIN/ORDER BY/LIMIT/OFFSET.

Cùng một JPQL có thể tạo SQL khác khi:

- Đổi fetch mappings.
- Có inheritance strategy.
- Có tenant/soft-delete filters.
- Có pageable sorting.
- Đổi database dialect.
- Sử dụng EntityGraph.
- Thêm eager associations.
- Bật second-level cache hoặc batching.

**Đừng tối ưu JPQL chỉ dựa vào vẻ ngắn gọn của chuỗi query.** Hãy xem SQL chạy thật.

## 9. Phân tích kế hoạch thực thi bằng EXPLAIN

Ví dụ trên PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    id, status, created_at, total_amount, customer_id
FROM purchase_orders
WHERE status = 'PAID'
ORDER BY created_at DESC
LIMIT 20;
```

Khi đọc plan, quan sát:

- Scan type: sequential scan, index scan, bitmap scan...
- Estimated rows vs actual rows.
- Total elapsed time của execution plan.
- Buffers hit/read (đọc từ cache hay storage).
- Sort operations, memory/disk spill.
- Join algorithms: nested loop, hash join, merge join.
- Filters và rows removed.
- Loops — một operation có bị lặp nhiều lần?
- Time spent trong child nodes.
- Khác biệt giữa dữ liệu thống kê DB ước lượng và thực tế.

**`EXPLAIN ANALYZE` thực sự thực thi SQL** trên PostgreSQL. Không chạy vô ý với câu UPDATE/DELETE nguy hiểm trên production. Với các câu ghi, dùng môi trường test hoặc transaction/điều kiện an toàn và hiểu side effects. MySQL, Oracle, SQL Server có cú pháp và công cụ plan riêng.

### Ví dụ index theo query

```sql
CREATE INDEX idx_orders_status_created
ON purchase_orders (status, created_at DESC);
```

Index này có thể hữu ích cho `WHERE status=? ORDER BY created_at DESC LIMIT 20`, nhưng **không bảo đảm** DB luôn chọn nó hoặc query luôn nhanh. Phụ thuộc selectivity, cardinality, index-only coverage, statistics, data distribution, write cost và planner.

Không tạo index theo phản xạ cho mọi cột `WHERE`; index làm chậm writes và tốn storage.

## 10. Một SQL chậm do lock wait không nhất thiết thiếu index

Giả sử `UPDATE inventory_items` mất 2 giây. Có thể DB đã tìm đúng row bằng primary key trong dưới 1 ms, nhưng phải chờ transaction khác giữ lock.

Dấu hiệu:

- Execution elapsed time cao, actual row count thấp.
- Lock wait trong DB monitor.
- Slow requests xuất hiện theo bursts.
- Connection pool bị chiếm lâu.
- Transactions dài do logic ứng dụng.
- Deadlock/timeout/retry rate tăng.

Cách xử lý khác với thêm index:

- Rút ngắn transaction.
- Không gọi external HTTP/email trong transaction đang giữ locks.
- Thiết kế thứ tự lock nhất quán.
- Dùng optimistic locking khi phù hợp.
- Xem isolation level và blocking queries.
- Tối ưu use case tranh chấp cùng một row.
- Không tăng connection pool vô hạn để “chữa” lock contention.

Một trace phân biệt **DB CPU time** với **time waiting for lock** sẽ tiết kiệm rất nhiều tối ưu sai hướng.

## 11. OFFSET pagination có thể là bottleneck SQL

Ví dụ:

```sql
SELECT *
FROM purchase_orders
WHERE status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 200000;
```

Ở trang sâu, database có thể phải duyệt/bỏ qua rất nhiều rows trước khi trả 20 rows, ngay cả khi có index phù hợp.

Với UI cần duyệt theo thứ tự ổn định, có thể xem xét **keyset/seek pagination**:

```sql
SELECT id, created_at, status, total_amount
FROM purchase_orders
WHERE status = 'PAID'
  AND (
       created_at < :last_created_at
       OR (
           created_at = :last_created_at
           AND id < :last_id
       )
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Cần index/phân trang và token đúng sorting/filter context. Keyset phù hợp navigation next/previous, nhưng không thay thế mọi nhu cầu “nhảy tới trang số 8.000”.

**Không quy chậm ở page sâu thành JPA entity overhead khi SQL plan đang bỏ qua hàng trăm nghìn rows.**

## 12. Batching writes không phải thuốc chữa một SELECT chậm

Một batch save 10.000 Orders phát 10.000 INSERT riêng có thể tối ưu bằng JDBC batching khi provider, ID generation và mapping hỗ trợ. Nhưng điều này **không liên quan trực tiếp** tới SELECT list endpoint đang quét bảng do thiếu index.

Hãy xác định operation:

- Read query slow → SQL shape/index/fetch/projection.
- Write throughput slow → batch size, flush/clear chunks, transactions, ID strategy.
- Transaction update slow → locks/version checks.
- Heap pressure → entity lifetime/object creation.

Không trộn các giải pháp chỉ vì chúng đều có nhãn “JPA performance”.

---

## 13. Nút thắt nhóm 2: kế hoạch tải dữ liệu

**Fetch plan** là cách ORM quyết định các association/attributes nào được tải ở cùng SQL, SQL phụ hoặc khi code truy cập lazy property.

Các khái niệm:

- `FetchType.LAZY`: một gợi ý/yêu cầu trì hoãn tải cho một quan hệ theo mapping/provider; hỗ trợ lazy cho một số loại mapping phụ thuộc enhancement/provider.
- `FetchType.EAGER`: liên kết phải được load eager theo semantics; không hứa chỉ một câu SQL.
- `JOIN FETCH`: yêu cầu truy vấn fetch association cùng query cho use case cụ thể.
- `EntityGraph`: khai báo fetch graph/load graph cho operation.
- Batch fetching: provider gom nhiều lazy loads thành những SQL dùng tập IDs.
- Subselect fetching: provider lấy nhiều collections dựa vào tập parent IDs theo cơ chế riêng.
- DTO projection: trả đúng các giá trị cần dùng, thay vì managed entity graph.

Một mô hình có mapping đúng vẫn có thể có fetch plan rất tệ cho một endpoint.

## 14. N+1 là gì?

Giả sử một câu query tải 20 Orders:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "ORDER BY o.createdAt DESC",
    PurchaseOrder.class
).setMaxResults(20)
 .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getDisplayName()
    );
}
```

Với `customer` lazy, nếu 20 Orders tham chiếu 20 Customers chưa ở cache, provider có thể chạy:

```text
SQL 1: SELECT 20 purchase_orders
SQL 2: SELECT Customer for Order #1
SQL 3: SELECT Customer for Order #2
...
SQL 21: SELECT Customer for Order #20
```

Tổng khoảng **1 + N** SQL. Nếu 20 Orders dùng chung 3 Customers và persistence context/cache tái sử dụng entity theo ID, SQL bổ sung có thể ít hơn 20. N+1 là **pattern phụ thuộc số lượng entities/associations khác nhau được truy cập**, không phải một phép đếm cứng cho mọi dữ liệu.

### Vì sao N+1 chậm dù từng SQL nhanh?

Giả sử mỗi SELECT Customer chỉ 2 ms trên DB, nhưng mỗi roundtrip còn network, JDBC processing và queue waits. Hai mươi lần lặp tạo độ trễ tích lũy. Khi P95 network cao hoặc DB pool bận, vấn đề nặng hơn nhiều.

**N+1 là vấn đề fetch plan/roundtrip, không nhất thiết là một SQL có execution plan chậm.**

## 15. EAGER không bảo đảm hết N+1

JPA mặc định `@ManyToOne` và `@OneToOne` thường là EAGER nếu không chỉ định. Nhưng EAGER có nghĩa association cần được nạp, **không có nghĩa provider bắt buộc dùng JOIN trong cùng SQL**.

Một JPQL query root entity:

```java
SELECT o FROM PurchaseOrder o
```

có thể được provider thực hiện bằng SQL lấy Orders rồi các SQL phụ nạp eager Customers nếu fetch plan của query không chỉ định join tương ứng.

Vì vậy:

- Đổi `LAZY` thành `EAGER` **không phải cách chữa N+1 đáng tin**.
- EAGER trên mapping có thể over-fetch ở rất nhiều use cases.
- EAGER khó “tắt” hơn tại nơi chỉ cần scalar fields.
- Nên cân nhắc mặc định LAZY với các quan hệ phù hợp và chọn fetch plan tại truy vấn.
- Cần quan sát generated SQL trên provider đang dùng.

Đặc biệt, default EAGER của to-one relations là một nguồn SQL phụ dễ bị bỏ sót khi chạy repository `findAll`.

## 16. Giải pháp: JOIN FETCH cho to-one khi thực sự cần

Nếu list endpoint cần tên Customer:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "JOIN FETCH o.customer " +
    "WHERE o.status = :status " +
    "ORDER BY o.createdAt DESC",
    PurchaseOrder.class
).setParameter("status", OrderStatus.PAID)
 .setMaxResults(20)
 .getResultList();
```

Vì `customer` là to-one, join thường không làm mỗi Order nhân lên nhiều rows như một collection fetch. Có thể giảm N+1, nếu dữ liệu và join semantics phù hợp.

Nhưng lưu ý:

- `JOIN` là inner join; nếu association optional, có thể cần `LEFT JOIN FETCH`.
- Join chỉ phục vụ data mà endpoint thật sự dùng.
- SQL có thể đọc thêm nhiều cột của Customer không cần.
- Nếu Customers có những eager relations khác, vẫn có thể phát SQL phụ.
- Pagination cần xem SQL thực tế, nhưng to-one fetch thường dễ phân trang hơn to-many fetch.
- Cần index FK/join columns và DB plan phù hợp.

### Dùng LEFT JOIN FETCH cho optional association

```java
SELECT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.optionalPromotion
WHERE o.id = :id
```

Điều này tránh loại root row chỉ vì optional association vắng mặt. Chọn inner/outer join theo domain semantics, không chỉ để giảm SQL count.

## 17. DTO projection có thể tốt hơn JOIN FETCH

Nếu list chỉ cần năm trường:

```java
public record OrderSummary(
    Long id,
    Instant createdAt,
    OrderStatus status,
    String customerName,
    BigDecimal totalAmount
) {}
```

JPQL constructor expression:

```java
List<OrderSummary> rows = em.createQuery(
    "SELECT new com.example.api.OrderSummary(" +
    "  o.id, o.createdAt, o.status, " +
    "  c.displayName, o.totalAmount" +
    ") " +
    "FROM PurchaseOrder o " +
    "JOIN o.customer c " +
    "WHERE o.status = :status " +
    "ORDER BY o.createdAt DESC",
    OrderSummary.class
).setParameter("status", OrderStatus.PAID)
 .setMaxResults(20)
 .getResultList();
```

Lợi ích tiềm năng:

- Chỉ chọn cột cần hiển thị.
- Không cần tạo managed `PurchaseOrder` và `Customer` entities cho mỗi row.
- Tránh lazy navigation trong JSON mapper.
- Giảm memory và dirty-checking overhead.
- API contract rõ ràng.
- Join là query join lấy scalar values, không phải `JOIN FETCH` trả entity graph.

Tuy nhiên:

- DTO không tự có dirty checking/persistence lifecycle.
- JPQL constructor phải trỏ đúng package/class và parameter types.
- Nhiều computed values có thể cần DB aggregation/projection.
- Nếu cần thay entity sau đó, dùng managed entity/query phù hợp.
- DTO projection không cứu một SQL với plan/index tệ; hãy đo cả DB và JVM.

**Dữ liệu chỉ để đọc và hiển thị thường là ứng viên mạnh cho projection**, nhưng quyết định phải dựa vào access pattern và benchmark.

## 18. Vì sao không SELECT toàn bộ entity để rồi map sang DTO?

Cách thường thấy:

```java
List<PurchaseOrder> orders = repository.findAll(...);

return orders.stream()
    .map(this::toSummary)
    .toList();
```

Nếu `toSummary` gọi `order.getCustomer().getDisplayName()`:

1. Query gốc tải entities.
2. Mapper có thể kích hoạt N+1 Customers.
3. Provider phải hydrate và quản lý các entities.
4. DTO được tạo thêm bên cạnh.
5. Entity graphs vẫn nằm trong persistence context tới khi close/clear.
6. Có thể kéo theo những EAGER mappings không cần.

Không phải lúc nào sai; nếu sau đó business logic cần managed entities, hướng này có thể hợp lý. Nhưng nếu endpoint chỉ cần read-only summary, direct projection thường đáng thử.

**Đếm số object được tạo**, không chỉ số DTO cuối cùng trả ra.

---

## 19. Một-to-many JOIN FETCH dễ nhân số rows

Giả sử có 100 Orders, mỗi Order có trung bình 10 Lines.

```java
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.status = :status
```

Một SQL JOIN có thể trả khoảng **1.000 rows**, trong khi result Java chỉ có 100 unique Order objects. Nếu mỗi Order có 50 Lines, nó có thể trả khoảng 5.000 rows.

Đây là **row multiplication** do quan hệ một-nhiều.

Mặt trái:

- DB phải join và chuyển nhiều rows hơn.
- Các cột Order lặp lại trên mỗi Line.
- JDBC phải đọc nhiều dữ liệu.
- ORM phải khử trùng lặp root entity identity và xây collections.
- Heap allocations tăng.
- Nếu có nhiều collections join cùng lúc, số rows có thể nhân chéo.

Một query ít roundtrips chưa chắc nhanh nếu result set phình lên 100 lần.

## 20. Cartesian explosion khi fetch hai collections

Giả sử mỗi Order có:

- 10 OrderLines.
- 8 AuditEvents.

Nếu fetch hai to-many collections cùng query:

```java
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
LEFT JOIN FETCH o.auditEvents
WHERE o.id = :id
```

SQL join có thể tạo **10 × 8 = 80 rows cho một Order**, dù dữ liệu cần chỉ gồm 10 Lines và 8 Events.

Với 100 Orders, mức nhân row có thể cực lớn. Hibernate có thể từ chối fetch đồng thời nhiều bag collections bằng `MultipleBagFetchException` trong một số mappings; một số mappings vẫn chạy nhưng chịu row explosion.

Giải pháp thường phù hợp:

- Không fetch hai to-many collections trong một SQL.
- Fetch roots/IDs trước.
- Batch-load collections theo nhu cầu.
- Dùng hai queries với cùng persistence context khi cần managed graph.
- Dùng DTO projections và tổng hợp theo group trên service với kích thước bounded.
- Tách endpoint summary/detail.
- Cân nhắc pagination và giới hạn graph.

Đừng chữa N+1 bằng một query JOIN FETCH mọi collection nếu kết quả là Cartesian explosion.

## 21. Pagination + fetch join collection là trường hợp cần đặc biệt cẩn thận

Ví dụ:

```java
List<PurchaseOrder> page = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "LEFT JOIN FETCH o.lines " +
    "ORDER BY o.createdAt DESC",
    PurchaseOrder.class
).setFirstResult(0)
 .setMaxResults(20)
 .getResultList();
```

Vì một Order có nhiều lines, giới hạn 20 SQL rows không tương đương 20 Orders.

Một số providers (ví dụ Hibernate với cấu hình nhất định) có thể **phân trang trong memory**, cảnh báo hoặc ném exception khi gặp collection fetch + pagination. Điều này nguy hiểm vì query có thể đọc một lượng lớn rows trước khi cắt còn 20 root entities.

### Cách thường an toàn hơn: phân trang IDs rồi tải details

Bước 1:

```java
List<Long> ids = em.createQuery(
    "SELECT o.id FROM PurchaseOrder o " +
    "WHERE o.status = :status " +
    "ORDER BY o.createdAt DESC, o.id DESC",
    Long.class
).setParameter("status", OrderStatus.PAID)
 .setMaxResults(20)
 .getResultList();
```

Bước 2:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT DISTINCT o FROM PurchaseOrder o " +
    "LEFT JOIN FETCH o.lines " +
    "WHERE o.id IN :ids",
    PurchaseOrder.class
).setParameter("ids", ids)
 .getResultList();
```

Cần hiểu:

- `ids` rỗng thì không chạy bước 2 (tránh SQL `IN ()` không hợp lệ).
- `IN` **không bảo đảm giữ thứ tự** giống page IDs; phải reorder kết quả theo IDs ở Java hoặc SQL phù hợp.
- Một Order có rất nhiều Lines vẫn có thể tạo result set lớn.
- Nếu page IDs thay đổi đồng thời giữa hai queries, tính nhất quán phụ thuộc transaction isolation.
- Kích thước `IN`/bind parameter có giới hạn tùy database.
- Page count query là câu khác, cần profile riêng.

Đây là một **mẫu hai pha**, không phải giải pháp duy nhất. Với summary list thường tốt hơn là dùng DTO projection ngay từ đầu thay vì fetch toàn Lines.

## 22. EntityGraph: khai báo fetch plan theo use case

JPA có entity graphs:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

Map<String, Object> hints = Map.of(
    "jakarta.persistence.fetchgraph",
    graph
);

PurchaseOrder order = em.find(
    PurchaseOrder.class,
    orderId,
    hints
);
```

Với một màn hình cần Customer nhưng không cần Lines, graph có thể diễn đạt fetch intent rõ hơn thay `EAGER` trên mapping.

Cần phân biệt:

- `jakarta.persistence.fetchgraph`: thuộc tính được chỉ định được xem eager; những thuộc tính còn lại có lazy semantics theo fetch graph rules, nhưng provider có thể tải thêm dữ liệu.
- `jakarta.persistence.loadgraph`: thuộc tính trong graph được fetch eager; các thuộc tính khác theo mapping default fetch semantics.
- Graph chỉ định **cần fetch gì**, không luôn bảo đảm **số SQL chính xác bằng một**.
- To-many graph vẫn có thể tạo row multiplication hoặc secondary selects tùy provider.
- Nếu graph nested nhiều levels, cần đo SQL và số rows.

Không coi EntityGraph là một syntax đẹp hơn cho “join mọi thứ”. Nó vẫn cần phù hợp use case.

## 23. Fetch plan nên được chọn tại repository boundary

Một ứng dụng có thể có các operations:

```java
findSummaryPage(status, pageable)
findOrderDetail(orderId)
findOrderForPaymentUpdate(orderId)
findOrderForReconciliation(orderId)
```

Mỗi operation có data needs khác:

| Operation | Cần data | Fetch strategy gợi ý |
| --- | --- | --- |
| Summary page | Order ID, status, Customer name, total | DTO projection |
| Order detail | Order + Customer + Lines + Product labels | Một số joins chọn lọc, batched loading/split queries |
| Update payment status | Một Order và state liên quan | Managed entity, chỉ fetch relations cần rule |
| Export 1 triệu rows | Scalar/report columns | Streaming/chunked DTO/JDBC |
| Analytics SUM/COUNT | Aggregate values | SQL/JPQL aggregation, không load 1 triệu entities |
| Audit recent changes | Event DTOs, IDs | Read-only projection |

Lựa chọn fetch plan dựa vào **contract của operation**, không đơn thuần quan hệ được khai báo trong entity model.

## 24. Batch fetching: giảm N+1 mà không JOIN phình rows

Khi một collection lazy được truy cập cho nhiều parent IDs, một ORM provider có thể tải theo batches.

Ví dụ Hibernate có thể dùng setting:

```properties
hibernate.default_batch_fetch_size=32
```

hoặc extension:

```java
@org.hibernate.annotations.BatchSize(size = 32)
@OneToMany(mappedBy = "order")
private List<OrderLine> lines;
```

Ý tưởng:

```text
Thay vì:
  SELECT lines WHERE order_id = 1
  SELECT lines WHERE order_id = 2
  ...
  SELECT lines WHERE order_id = 32

Có thể:
  SELECT lines WHERE order_id IN (1, 2, ..., 32)
```

Ưu điểm:

- Giảm roundtrips.
- Không nhất thiết nhân chéo rows của nhiều collections trong cùng JOIN.
- Có thể giữ mapping LAZY và chỉ tải khi cần.

Giới hạn:

- Đây là Hibernate/provider-specific, không phải API bắt buộc của JPA.
- Kích thước batch tối ưu phụ thuộc DB, ID distribution, parameter limits và workload.
- Không giải quyết query chính thiếu index.
- Có thể tải nhiều associated entities hơn cần nếu batch prefetch.
- Khi màn hình chỉ cần Customer name, DTO projection vẫn có thể tốt hơn.

**Batch fetching là một lựa chọn giảm SQL count, không phải bằng chứng mọi thứ nên để lazy vô hạn.**

## 25. Subselect fetching

Hibernate có cơ chế `FetchMode.SUBSELECT` cho một số collections. Khi một collection được khởi tạo, provider có thể dùng một subselect dựa trên parent query để lấy collections của các parents có liên quan.

Tư duy:

```text
Query 1: Load 20 Orders
Query 2: Load Lines for those Orders via subselect
```

So với 21 SQL, số roundtrips có thể giảm. Nhưng:

- Subselect có thể tải nhiều collections hơn dự kiến.
- Có tương tác với pagination và session context.
- SQL shape/DB plan phải được kiểm tra.
- Mapping annotation của Hibernate không portable sang JPA provider khác.

Dùng khi có pattern rõ ràng “load một nhóm parents rồi truy cập cùng collection”, không dùng chỉ vì tên subselect nghe nhanh hơn JOIN.

## 26. LAZY không tự bảo đảm ít SQL

Một mapper có thể vô tình kích hoạt nhiều loads:

```java
OrderSummary toSummary(PurchaseOrder order) {
    return new OrderSummary(
        order.getId(),
        order.getCreatedAt(),
        order.getStatus(),
        order.getCustomer().getDisplayName(),
        order.getTotalAmount()
    );
}
```

Nếu `customer` LAZY mà collection đầu vào chứa nhiều Orders, code này có thể là nguồn N+1. Tương tự:

- JSON serializers.
- `toString()`.
- `equals()`/`hashCode()` truy cập associations.
- Logging template.
- Debuggers gọi getters.
- Mapping frameworks.
- Business rules duyệt collections.
- View layer/OIV.

Vì vậy “mapping LAZY” chỉ nói **khi nào có thể trì hoãn**; kế hoạch tải thật được quyết định bởi **toàn bộ đường dùng entity trong request**.

---

## 27. Nút thắt nhóm 3: chi phí quản lý entity

Khi JPA trả một managed entity, provider thường phải làm nhiều việc hơn tạo một record DTO:

1. Đọc cột từ JDBC result set.
2. Chuyển kiểu SQL → Java.
3. Xác định entity identity (class + ID + tenant/context metadata).
4. Kiểm tra persistence context đã có đại diện cho ID đó chưa.
5. Tạo entity/proxy nếu cần.
6. Hydrate persistent fields.
7. Quản lý các association references/collection wrappers.
8. Ghi nhận trạng thái cần thiết cho dirty checking và versioning.
9. Đăng ký entity trong persistence context.
10. Duy trì lifecycle/callback hooks.
11. Theo dõi thay đổi và chuẩn bị flush khi transaction kết thúc.
12. Giữ objects trong heap cho tới khi context đóng/detach/clear.

Không phải mọi provider lúc nào cũng lưu snapshot giống nhau: bytecode enhancement, read-only mode, immutable entities, fetch profiles và provider settings có thể thay đổi chi phí. Nhưng **managed entity có thêm trách nhiệm so với một scalar/DTO chỉ để đọc**.

## 28. L1 identity map giúp đúng nhưng cũng dùng memory

Trong một persistence context:

```java
PurchaseOrder a = em.find(PurchaseOrder.class, 42L);
PurchaseOrder b = em.find(PurchaseOrder.class, 42L);

System.out.println(a == b); // Cùng managed identity.
```

Đây là thuộc tính quan trọng cho tính nhất quán identity. Nhưng một batch load 200.000 entities có thể khiến context giữ rất nhiều objects cùng snapshots/wrappers, dù ứng dụng đã xử lý xong 199.000 entities đầu tiên.

Dấu hiệu:

- Heap tăng tuyến tính theo số entities đã đọc.
- Full GC hoặc allocation rate cao.
- Flush/clear chậm dần.
- CPU ở ORM hydration/dirty checking.
- SQL execution thực tế ngắn.
- Batch throughput giảm theo thời gian.

Không nên chỉ tăng `-Xmx` rồi bỏ qua persistence context lifetime.

## 29. Managed entity khác DTO projection

Entity query:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
```

DTO query:

```java
List<OrderIdAndTotal> totals = em.createQuery(
    "SELECT new com.example.report.OrderIdAndTotal(" +
    "o.id, o.totalAmount) " +
    "FROM PurchaseOrder o",
    OrderIdAndTotal.class
).getResultList();
```

DTO:

```java
public record OrderIdAndTotal(
    Long id,
    BigDecimal totalAmount
) {}
```

Với một báo cáo chỉ cần ID và total, DTO query có thể:

- Chọn ít cột hơn.
- Tạo object đơn giản, không managed.
- Không giữ entity trong L1.
- Không dirty-check.
- Không cần lazy associations.
- Tiết kiệm bộ nhớ/network.
- Dễ serializable theo API contract.

Nhưng không dùng DTO rồi gọi `em.merge(dto)`: DTO không phải JPA entity. Khi cần cập nhật, load managed entity hoặc dùng một write command/SQL update có concurrency policy phù hợp.

## 30. Trường hợp SQL nhanh mà API vẫn chậm

Giả sử trace:

```text
SQL SELECT:        40 ms
JDBC result read:  90 ms
Entity hydration: 220 ms
DTO mapping:      110 ms
JSON serialization: 240 ms
GC/other:         100 ms
Total:            800 ms
```

Cách sửa phải khác N+1:

- Giảm số rows và cột.
- Dùng projection.
- Phân trang hoặc stream bounded.
- Tránh trả toàn graph.
- Không serialize managed entities trực tiếp.
- Đo allocations và retained heap.
- Giảm số lớp chuyển đổi không cần.
- Dùng batch/chunk khi export.
- Kiểm tra garbage collector/heap sizing sau khi giảm work.

Một DB plan tốt không chứng minh end-to-end latency tốt.

## 31. Dirty checking và snapshot overhead

JPA có cơ chế phát hiện thay đổi của managed entities để khi flush cập nhật database. Provider có thể sử dụng:

- Snapshots của state đã load.
- Bytecode enhancement/field interception.
- Dirty flags.
- Version fields.
- Các cấu trúc metadata và collection change tracking.

Nếu bạn load 100.000 managed entities để chỉ đọc, provider vẫn có thể giữ/traversal dữ liệu liên quan tới khả năng update, trừ khi có read-only optimization phù hợp.

### Đừng hiểu sai `@Transactional(readOnly = true)`

Trong Spring:

```java
@Transactional(readOnly = true)
public List<OrderSummary> list() {
    // ...
}
```

đây là một **hint/transaction definition của Spring**. Nó có thể ảnh hưởng flush mode, JDBC connection read-only hoặc provider optimization tùy stack, nhưng **không phải bảo đảm chuẩn JPA rằng mọi entity không được managed hoặc không có snapshot**.

Đo persistence context allocations và behavior trên phiên bản Spring/Hibernate thực tế thay vì tin một annotation luôn loại bỏ toàn bộ ORM overhead.

## 32. Hibernate read-only query/session: một extension hữu ích

Hibernate có các cơ chế đọc entity ở read-only mode theo API/hints của nó. Một kiểu hint thường gặp qua JPA query:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).setHint(
    "org.hibernate.readOnly",
    true
).getResultList();
```

Tên hint và behavior phải được xác minh theo Hibernate version. Đây không phải hint chuẩn Jakarta Persistence.

Read-only optimization có thể giảm một phần chi phí dirty checking, nhưng:

- Entity vẫn có thể nằm trong persistence context.
- Không tự giảm số rows/cột được SELECT.
- Không tự sửa N+1.
- Không phải cách bảo vệ write permissions.
- Không dùng khi sẽ sửa entity rồi mong provider tự flush thay đổi.
- Không mặc định mọi entity types/collections được tối ưu như nhau.

Nếu chỉ cần vài scalar fields, DTO projection thường là lựa chọn rõ hơn đọc managed entities read-only.

## 33. Query flush có thể tốn CPU dù không nhiều UPDATE

Khi `em.flush()`, provider phải xử lý trạng thái persistence context và quyết định thao tác SQL cần làm. Nếu context rất lớn, chi phí flush/dirty tracking có thể tăng, kể cả khi chỉ một số entity thực sự thay đổi.

Một dấu hiệu:

```text
Context chứa 100.000 entities
Chỉ 10 entities thay đổi
SQL UPDATE tổng cộng 10
Flush mất đáng kể CPU/allocations
```

Tối ưu có thể là:

- Giữ transaction/persistence context ngắn hơn.
- Phân chia batch thành chunks hợp lý.
- Chỉ load những entities cần sửa.
- Dùng SQL bulk/DTO cho read-only reporting.
- Dùng provider enhancements khi đã đo hiệu quả.
- Tránh vô tình hydrate cả graph qua EAGER fetches.

Nhưng **không tự động gọi `clear()` giữa một business transaction phức tạp** nếu còn pending changes/associations cần quản lý.

## 34. `flush()`, `clear()` và `detach()` làm gì?

| Lời gọi | Ý nghĩa | Rủi ro khi dùng để tối ưu |
| --- | --- | --- |
| `em.flush()` | Đồng bộ pending state với DB trong transaction | Không commit; có thể gửi nhiều SQL |
| `em.clear()` | Detach tất cả managed entities trong context | Pending changes chưa flush có thể bị bỏ qua |
| `em.detach(entity)` | Detach một entity cụ thể | Các thay đổi sau detach không được tự flush |
| `em.close()` | Kết thúc EntityManager | Không dùng lại; transaction phải được xử lý đúng |
| `em.refresh(entity)` | Reload managed entity state | Có thể ghi đè pending changes |
| `emf.getCache().evict(...)` | Evict shared/L2 cache entry | Không detach L1 managed entity |

Khi tối ưu batch, kết hợp flush/clear **ở ranh giới được kiểm soát**, không dùng như thủ thuật “xóa memory” khi còn dữ liệu chưa đồng bộ.

## 35. Batch update theo chunks

Một ví dụ khái niệm:

```java
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    int processed = 0;

    for (Long id : idsToUpdate) {
        PurchaseOrder order = em.find(
            PurchaseOrder.class,
            id
        );

        if (order == null) {
            continue;
        }

        order.markReconciled();
        processed++;

        if (processed % 100 == 0) {
            em.flush();
            em.clear();
        }
    }

    em.flush();
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        tx.rollback();
    }
    throw failure;
}
```

Đoạn code giả định có `markReconciled()` và một EntityManager được đóng bởi caller; nó minh họa chunking, không phải recipe phù hợp mọi workloads.

Cần cân nhắc:

- `em.clear()` detach mọi entities, không chỉ Order hiện tại.
- Nếu có reference/collection chưa flush xong, clear sai thời điểm phá unit of work.
- Transaction vẫn kéo dài suốt vòng lặp nếu chỉ flush/clear; locks/undo log có thể tăng.
- Với millions of rows, chia **transactions** thành các chunks có thể phù hợp hơn, nhưng thay đổi atomicity/retry semantics.
- SQL count có thể tăng nếu mỗi `find` nạp một entity riêng; có thể dùng bulk updates khi rule cho phép.
- JDBC batching phụ thuộc provider settings và ID strategy.

**Flush/clear giảm L1 footprint nhưng không tự giảm số SQL.** Nó là giải pháp cho memory/dirty tracking, không phải bản thân fetch plan.

## 36. Bulk JPQL UPDATE có thể tránh hydrate entity

Nếu yêu cầu đơn giản là cập nhật hàng loạt:

```java
int changed = em.createQuery(
    "UPDATE PurchaseOrder o " +
    "SET o.status = :newStatus " +
    "WHERE o.status = :oldStatus"
).setParameter("newStatus", OrderStatus.ARCHIVED)
 .setParameter("oldStatus", OrderStatus.COMPLETED)
 .executeUpdate();
```

Một bulk update có thể hiệu quả hơn load từng entity rồi setter, vì:

- Không phải hydrate hàng nghìn objects.
- Không giữ chúng trong L1.
- Không chạy dirty checking per entity.
- Có thể gửi ít roundtrips hơn.

Nhưng semantics **khác hẳn entity lifecycle updates**:

- Không gọi `@PreUpdate`/`@PostUpdate` per entity.
- Không áp per-entity Bean Validation theo lifecycle.
- Không tự xử lý optimistic `@Version` như managed updates.
- L1 managed entities có thể stale.
- Có thể không kích hoạt audit callbacks.
- DB constraints vẫn phải bảo vệ.
- Query update có thể ảnh hưởng nhiều rows hơn dự tính.

Không chỉ thay vòng lặp entity bằng bulk SQL vì benchmark nhanh nếu nghiệp vụ cần callbacks, version checks hoặc aggregate invariants. Khi dùng bulk, phải thiết kế bù những semantics cần giữ.

## 37. JDBC batch insert và IDENTITY ID strategy

Với nhiều inserts:

```java
for (int i = 0; i < 10_000; i++) {
    em.persist(new EventLog(...));
}
```

JPA provider có thể phát từng INSERT hoặc batch theo settings. Hibernate thường có cấu hình:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
```

Tuy nhiên, cách sinh ID ảnh hưởng batching. Với Hibernate và `GenerationType.IDENTITY`, provider thường cần INSERT sớm để nhận generated key, có thể hạn chế hoặc vô hiệu hóa batching insert cho mapping đó. Với sequence/pooled optimizer phù hợp, batching có thể hiệu quả hơn.

Đừng hiểu `hibernate.jdbc.batch_size=50` là cam kết mọi INSERT đều được gửi theo lô 50. Hãy kiểm tra logs/statistics/driver behavior thực tế.

### Chia chunk cũng cần định nghĩa retry

Nếu chia 10.000 rows thành 100 transactions:

- Một batch fail có thể chỉ rollback batch đó.
- Job phải có checkpoint/idempotency.
- Application không được báo toàn bộ job atomic nếu đã commit từng phần.
- Unique constraints và versioning vẫn phải đúng.
- Re-run sau lỗi cần tránh duplicate data.

Tối ưu hiệu năng không được âm thầm thay đổi tính đúng của giao dịch.

---

## 38. Phân biệt hydrate cost với mapping cost

Một request có thể tạo:

```text
SQL rows
   ↓
JDBC ResultSet
   ↓
Entity hydration + identity management
   ↓
Domain mapping Entity → DTO
   ↓
JSON serialization
```

Nếu SQL nhanh mà tổng request chậm, hãy đo từng bước:

- Thời gian `getResultList()`: gồm SQL + fetch rows + hydration.
- Thời gian mapping `toDto`: có thể kích hoạt thêm lazy loads!
- Thời gian serialization: có thể duyệt nested DTO/entity graph.
- Allocation/GC.
- Số managed entities trong persistence context.
- Số bytes HTTP response.

Một phép đo “getResultList mất 400 ms” chưa đủ biết 400 ms nằm ở DB hay hydration. Cần kết hợp DB-side timing và JVM profiler/tracing.

### Ví dụ phân chia thời gian

```text
DB execution (server measured): 20 ms
JDBC fetch + hydration:        280 ms
Map entities to DTO:           180 ms
Serialize response:            140 ms
Total:                         620 ms
```

Chỉ thêm DB index khó cải thiện đáng kể nếu 600/620 ms nằm ngoài DB.

## 39. L2 cache không thay thế fetch planning

Shared cache/L2 có thể giảm database reads của entities theo ID, nhưng:

- Không xóa chi phí Java object hydration/managed state.
- Không biến JPQL aggregate thành miễn phí.
- Không bảo đảm query result set được cache.
- Không sửa việc serializer cần duyệt 10.000 nested objects.
- Không bảo đảm cache hits khi workloads phân tán hoặc data thay đổi.
- Có consistency/invalidation cost.

Một N+1 có thể ít SQL hơn trong benchmark warm L2, nhưng vẫn tạo nhiều lazy lookups và work. Trên cold cache hoặc sau eviction, vấn đề trở lại.

**Đừng dựa vào cache warm-up để che N+1 thiết kế sai.** Đo cả cold và warm cases.

## 40. Một request có thể bị connection pool, không phải SQL

Dấu hiệu:

```text
API latency:          900 ms
Wait for JDBC pool:   750 ms
Execute SQL:           20 ms
Map DTO:               20 ms
Other:                110 ms
```

Thêm index hoặc JOIN FETCH có thể hầu như không giúp.

Nguyên nhân pool wait:

- Transaction quá dài.
- Leak connections hoặc sessions.
- Pool size nhỏ hơn nhu cầu thật.
- DB max connections bị giới hạn.
- Slow queries giữ connection lâu.
- Thread concurrency không có backpressure.
- Retry storms.

Giải pháp phải dựa vào pool metrics và tracing. Tăng pool size có thể chuyển nghẽn sang database hoặc làm lock contention trầm trọng hơn. **Không đoán pool size từ số CPU cores một cách máy móc.**

---

## 41. Công cụ đo JPA và database

Một bộ công cụ nhiều tầng:

| Tầng | Công cụ/thông tin | Dùng để tìm |
| --- | --- | --- |
| HTTP/service | OpenTelemetry spans, Micrometer timers, APM | Latency, fan-out, transaction spans |
| JDBC | Datasource proxy/P6Spy/driver metrics | SQL count, durations, bind values khi an toàn |
| ORM | Hibernate Statistics hoặc provider metrics | Entity load/fetch counts, query count, cache hits |
| JVM | Java Flight Recorder (JFR), async-profiler, heap dump | CPU, allocations, GC, object retention |
| Connection pool | HikariCP/driver pool metrics | Acquire wait, active/idle/pending connections |
| Database | Slow query logs, pg_stat_statements/Query Store/Performance Schema | SQL frequency và elapsed |
| SQL optimizer | EXPLAIN/EXPLAIN ANALYZE, actual execution plan | Scan, join, sort, row estimates |
| DB concurrency | Lock activity/transaction monitor | Blocking, deadlocks, timeouts |

Các sản phẩm cụ thể là ví dụ; không phải mọi công cụ hoạt động giống nhau trên mọi DB.

### Không bật logging chi tiết vô hạn ở production

SQL/bind-parameter logs có thể chứa PII, token, payment data và tạo I/O lớn. Dùng sampling, masking và quyền truy cập logs phù hợp; tắt hoặc giới hạn khi chẩn đoán xong.

## 42. Hibernate Statistics: ví dụ provider-specific

Với Hibernate có thể bật thống kê (cấu hình tùy version):

```properties
hibernate.generate_statistics=true
```

Một ví dụ qua Hibernate API:

```java
org.hibernate.SessionFactory sessionFactory =
    emf.unwrap(org.hibernate.SessionFactory.class);

org.hibernate.stat.Statistics stats =
    sessionFactory.getStatistics();

long beforePrepare = stats.getPrepareStatementCount();

// Chạy use case trong EntityManager/transaction riêng.

long afterPrepare = stats.getPrepareStatementCount();

long preparedStatements = afterPrepare - beforePrepare;
```

Cần hiểu:

- Statistics là counters ở phạm vi SessionFactory, có thể bị **nhiễu bởi tests/requests đồng thời**.
- Counter prepared statements không tự đồng nghĩa số rows hoặc tổng database execution time.
- Một JDBC batch có thể có nhiều execute/addBatch operations nhưng prepare count khác.
- Cache hits làm thay đổi số SQL quan sát.
- `stats.clear()` trong shared production factory có thể xóa metrics của request khác; không dùng tùy tiện.
- Hibernate version có thể có API/metric khác nhau.

Đối với integration test cô lập, statistics rất hữu ích để nhận ra N+1. Trong load test, kết hợp metrics per-request/JDBC tracing thay vì chỉ trừ global counters khi có concurrency.

## 43. Đo SQL count phải dựa trên workload cô lập

Một test:

```java
@Test
void summaryQueryDoesNotHaveCustomerNPlusOne() {
    // Seed 20 Orders với Customers riêng.
    // Đóng seed EntityManager để tránh L1 warm cache.

    List<OrderSummary> page =
        repository.findOrderSummaryPage(...);

    assertEquals(20, page.size());

    // Assert SQL pattern/count bằng datasource proxy hoặc
    // provider statistics trong môi trường cô lập.
}
```

Nếu chỉ assert `page.size() == 20`, N+1 vẫn có thể tồn tại.

Nếu muốn kiểm tra query count:

- Dùng database/cache state kiểm soát được.
- Seed trong transaction khác rồi close context.
- Không chạy parallel tests dùng chung statistics.
- Không để lazy mapper/serializer nằm ngoài vùng đo.
- Đo **cả repository + mapper**.
- Kiểm tra số lượng SQL có scale theo N không.
- Không hardcode count cực kỳ cụ thể nếu provider setup/metadata queries thêm SQL không liên quan; isolate/normalize patterns.

Một test mạnh là so sánh N=1, 10, 30 và xem statement count có tăng tuyến tính theo số rows/associations không.

## 44. SQL count growth curve là dấu hiệu fetch-plan rất mạnh

Giả sử đo:

| Orders N | SQL statements |
| ---: | ---: |
| 1 | 2 |
| 10 | 11 |
| 30 | 31 |

Đây là dấu hiệu rõ của N+1 nếu workload có cấu trúc tương đồng và cache được kiểm soát.

Sau thay bằng một projection:

| Orders N | SQL statements |
| ---: | ---: |
| 1 | 1 |
| 10 | 1 |
| 30 | 1 |

Nhưng nếu thay bằng JOIN FETCH hai collections mà result rows tăng từ 30 lên 900, SQL count là 1 **không đủ kết luận nhanh hơn**. Phải đo latency, bytes, row count và heap.

## 45. Đo “rows per root” để phát hiện over-fetch

Một phép đo đơn giản:

```text
Root entities requested: 20 Orders
Database result rows:   4.000
Rows per root:          200
```

Nếu fetch join nhiều to-many relations, đây có thể là dấu hiệu nhân rows.

So sánh ba chiến lược:

| Chiến lược | Roundtrips | SQL rows | JVM objects | Khi nào phù hợp |
| --- | --- | --- | --- | --- |
| Lazy N+1 | Rất nhiều | Ít ở mỗi SQL | Entities và lazy graph | Dataset nhỏ/cache tốt; không nên mặc định |
| One giant JOIN FETCH | Ít | Có thể rất lớn do multiplication | Entities + collection de-dup | To-one hoặc một to-many nhỏ |
| Split query/batch fetch | Vài SQL | Thường gần tổng data thực cần | Entities, có thể kiểm soát | Nhiều to-many/nested graph |
| DTO projection | Thường ít | Cột/rows đúng query | DTO, không managed | Read-only list/report |
| SQL aggregate | Thường ít | Một hoặc ít rows/group | Scalars/DTO | COUNT/SUM/GROUP BY |

Đây là quan hệ xu hướng, không phải bảng bảo đảm tuyệt đối. Mỗi strategy cần test trên workload thật.

## 46. N+1 có thể ẩn ở EAGER associations của entity phụ

Một JPQL list query có thể không truy cập Customer trong Java, nhưng provider vẫn load Customer vì mapping EAGER.

Ví dụ:

```java
@ManyToOne // JPA mặc định EAGER.
private Customer customer;
```

Khi tải Orders, provider phải đáp ứng eager state, có thể dùng secondary selects gây N+1 dù mapper không gọi `getCustomer()`.

Điều tra:

- Mappings to-one không chỉ định LAZY.
- Default fetch types.
- Entity graphs/load graphs.
- Multiple eager paths.
- Serialization side effects.
- SQL count trước khi mapper chạy.

Nếu SQL count đã tăng **ngay trong getResultList()**, tìm eager fetching/query shape; nếu chỉ tăng **khi mapper chạy**, tìm lazy dereference.

---

## 47. Chi phí quản lý entity khi chạy báo cáo lớn

Ví dụ:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
```

Nếu bảng có 500.000 rows, lệnh này có thể:

- Tạo hàng trăm nghìn managed objects.
- Tạo nhiều wrapper/proxy/snapshot structures.
- Giữ danh sách kết quả trong heap.
- Tốn heap cho JDBC processing.
- Kéo dài transaction và giữ connections.
- Gây full GC hoặc out-of-memory.
- Tốn thời gian dirty checking/flush.

Không nhất thiết SQL database chậm; dữ liệu **quá lớn cho cách sử dụng entity materialization hiện tại**.

Hướng xử lý:

1. Đặt giới hạn rows/page.
2. Query projection chỉ cột cần.
3. Streaming/cursor với transaction/lifecycle phù hợp.
4. Xử lý theo chunks, tránh giữ cả List trong heap.
5. Với updates, flush/clear có kiểm soát.
6. Với read-only analytics, cân nhắc database aggregation/reporting query.
7. Với rất lớn ETL, JDBC hoặc provider stateless API có thể phù hợp nếu domain semantics cho phép.

## 48. JDBC streaming và JPA `getResultStream()`

JPA cung cấp stream:

```java
try (Stream<OrderIdAndTotal> stream =
        em.createQuery(
            "SELECT new com.example.report.OrderIdAndTotal(" +
            "o.id, o.totalAmount) FROM PurchaseOrder o",
            OrderIdAndTotal.class
        ).getResultStream()) {

    stream.forEach(this::writeReportRow);
}
```

Nhưng **`getResultStream()` không bảo đảm mọi provider dùng server-side cursor/constant memory**. Một implementation có thể tải list rồi tạo stream; khi dùng provider-specific streaming, fetch size, JDBC driver và transaction configuration còn quan trọng.

Khi dùng streaming:

- Giữ transaction/EntityManager/connection mở suốt thời gian đọc nếu provider cần.
- Đóng `Stream`/resources đúng contract.
- Tránh `toList()` trên một stream khổng lồ nếu muốn tiết kiệm memory.
- Cẩn trọng side effects trong consumer khi stream có thể fail giữa chừng.
- Không chạy lâu trong transaction có locks không cần.
- Với data consistency, quyết định snapshot semantics.
- Với managed entity stream, persistence context vẫn có thể giữ entities trừ khi detach/clear/provider mode phù hợp.

Đừng thay `getResultList()` bằng `getResultStream()` rồi mặc định memory tự ổn.

## 49. Keyset batching cho export lớn

Một lựa chọn khác: phân đoạn theo key ổn định.

Ví dụ:

```sql
SELECT id, total_amount
FROM purchase_orders
WHERE id > :last_id
ORDER BY id
LIMIT :batch_size;
```

Sau mỗi batch:

1. Xử lý DTO rows.
2. Ghi/checkpoint last_id.
3. Giải phóng list.
4. Bắt đầu batch tiếp theo.
5. Quyết định consistency khi rows được thêm/xóa trong khi export.
6. Có thể dùng snapshot/high-watermark để tránh đọc dữ liệu ngoài phạm vi mong muốn.

Ưu điểm: memory bounded, không tạo managed entity context rất lớn và tránh OFFSET sâu. Nhưng data snapshot/ordering và resume semantics phải được thiết kế đúng.

## 50. Khi dùng Hibernate `StatelessSession`

Hibernate cung cấp `StatelessSession`, một API riêng không có cùng first-level persistence context và lifecycle semantics như `EntityManager` managed entities.

Nó có thể hữu ích cho workloads dạng ETL/bulk processing, nhưng đánh đổi:

- Không có dirty checking giống managed Session.
- Không có cùng cascade/lifecycle guarantees.
- Không tự xử lý object graph như EntityManager.
- Có thể bỏ qua interceptor/callback behaviors tùy Hibernate version/contract.
- Cần viết logic cập nhật/transaction rõ.
- Không portable sang mọi JPA provider.

Không đề xuất `StatelessSession` để chữa mọi endpoint chậm. Nếu domain cần JPA lifecycle/optimistic invariants, mất managed semantics có thể là regression nghiêm trọng.

---

## 51. Tìm bottleneck theo thứ tự phép đo

Một quy trình thực hành:

**Bước 1.** Đo endpoint p95, throughput và breakdown spans.

**Bước 2.** Đếm SQL statements, phân nhóm theo SQL normalized pattern.

**Bước 3.** Với mỗi pattern, đo executions, total time, average/p95 time và rows.

**Bước 4.** Xác định SQL chậm nhất và SQL gọi lặp nhiều nhất.

**Bước 5.** Với SQL chậm, đọc actual execution plan/lock/IO.

**Bước 6.** Với SQL lặp, tìm lazy/eager association và mapper/serializer trigger.

**Bước 7.** Với ít SQL nhanh nhưng request chậm, dùng JFR/CPU/allocations profiler.

**Bước 8.** Chọn tối ưu tối thiểu dựa trên root cause.

**Bước 9.** Đo lại với cùng dataset, load, cache state và transaction config.

**Bước 10.** Viết regression tests cho SQL count, fetch size, memory và correctness khi phù hợp.

### Sơ đồ quyết định

```text
Request JPA chậm
       │
       ▼
Có đang chờ JDBC connection pool?
       ├── Có → xem pool/transactions/threads/DB capacity
       └── Không
             │
             ▼
        Bao nhiêu SQL?
             │
      ┌──────┴───────────┐
      │                  │
   Ít SQL             Rất nhiều SQL
      │                  │
      ▼                  ▼
SQL server time cao?   SQL lặp theo số rows/associations?
  ├─ Có → plan/index    ├─ Có → N+1 / fetch plan
  │       lock/I/O       └─ Không → tìm source/loop/pagination
  └─ Không
      │
      ▼
SQL rows/bytes lớn?
  ├─ Có → over-fetch, projections, pagination
  └─ Không
      │
      ▼
JVM CPU/allocations/GC cao?
  ├─ Có → hydration, L1, dirty checking, mapping, JSON
  └─ Không → tracing app code/network/other waits
```

Một bottleneck có thể nằm ở nhiều nhánh. Quy trình lặp lại sau mỗi cải tiến.

## 52. Ba kịch bản giống nhau về triệu chứng nhưng khác cách xử lý

### Kịch bản A: dashboard chậm 900 ms, chỉ một SQL

Observations:

```text
SQL count = 1
DB time = 780 ms
SQL result rows = 20
App CPU = thấp
```

Giả thuyết:

- Missing composite index.
- Bad execution plan do stale statistics.
- Sorting/scan quá lớn.
- Lock wait.
- Query predicate kém sargable.

Bước tiếp: `EXPLAIN ANALYZE`/database monitor. **Không thêm `JOIN FETCH` trước khi biết SQL plan.**

### Kịch bản B: dashboard chậm 900 ms, có 201 SQL

```text
SQL 1: SELECT 100 Orders
SQL 2..101: SELECT Customers
SQL 102..201: SELECT Lines
```

Giả thuyết: N+1 ở Customer và Lines. Hướng sửa:

- Nếu dashboard chỉ cần tên Customer, DTO projection join Customer.
- Nếu cần aggregate số lines, query COUNT/GROUP BY hoặc stored total đúng semantics.
- Nếu detail cần Lines, batch fetching/split query.
- Đừng fetch toàn bộ Lines cho list nếu UI không dùng.

### Kịch bản C: dashboard chậm 900 ms, một SQL nhanh

```text
SQL count = 1
DB execution = 25 ms
Rows = 100.000
Hydration/mapping/JSON = 800 ms
Heap và GC cao
```

Giả thuyết: materialization quá lớn, không đúng API contract. Hướng sửa:

- Pagination.
- DTO.
- SQL aggregation.
- Trả ít fields/rows.
- Bounded streaming/export.
- Không tạo managed entities cho report.

Ba kịch bản có cùng p95 nhưng phải sửa **ba nhóm nguyên nhân khác nhau**.

## 53. Một query COUNT chậm không cần load entities

Anti-pattern:

```java
long count = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.status = :status",
    PurchaseOrder.class
).setParameter("status", OrderStatus.PAID)
 .getResultList()
 .size();
```

Nó có thể load hàng nghìn managed Orders chỉ để đếm.

Tốt hơn:

```java
Long count = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o " +
    "WHERE o.status = :status",
    Long.class
).setParameter("status", OrderStatus.PAID)
 .getSingleResult();
```

Lợi ích là DB thực hiện aggregate và trả scalar, không hydrate toàn bộ Orders. Nhưng COUNT trên bảng rất lớn vẫn có thể tốn DB I/O; cần plan/index/data distribution phù hợp.

Không lạm dụng `COUNT` query cho mọi infinite-scroll endpoint nếu không cần tổng số pages.

## 54. Aggregate SUM/GROUP BY nên tính ở DB khi thích hợp

Anti-pattern:

```java
BigDecimal total = em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultStream()
 .map(PurchaseOrder::getTotalAmount)
 .reduce(BigDecimal.ZERO, BigDecimal::add);
```

Tốt hơn:

```java
BigDecimal total = em.createQuery(
    "SELECT COALESCE(SUM(o.totalAmount), 0) " +
    "FROM PurchaseOrder o",
    BigDecimal.class
).getSingleResult();
```

Cần xác minh type inference/provider của `COALESCE`/numeric literals nếu gặp type mismatch. Có thể dùng `SUM` rồi xử lý null tường minh:

```java
BigDecimal sum = em.createQuery(
    "SELECT SUM(o.totalAmount) FROM PurchaseOrder o",
    BigDecimal.class
).getSingleResult();

BigDecimal total = sum == null
    ? BigDecimal.ZERO
    : sum;
```

Điểm chính: không tạo managed entity graph chỉ để tính aggregate mà database có thể tính trực tiếp.

## 55. Query DISTINCT không tự giảm SQL row multiplication

JPQL:

```java
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
```

có thể trả unique Java Order references. Nhưng database vẫn có thể xử lý rất nhiều join rows. `DISTINCT` có thể thêm sort/hash/dedup overhead tùy SQL generated và provider.

Không kết luận “đã SELECT DISTINCT nên Cartesian explosion đã hết”.

Cần đo:

- Rows database trả.
- SQL bytes/result width.
- DB CPU/sort.
- Time hydrate collections.
- Heap allocation.

Nếu nhiều collections, split queries/batch fetching thường đáng thử hơn thêm DISTINCT.

## 56. Projection và fetch plan có thể ảnh hưởng row width

Hai queries đều trả 20 Orders:

```sql
SELECT o.*
FROM purchase_orders o
WHERE o.status = 'PAID'
LIMIT 20;
```

và:

```sql
SELECT o.id, o.created_at, o.status, o.total_amount
FROM purchase_orders o
WHERE o.status = 'PAID'
LIMIT 20;
```

Với columns có large text/JSON/BLOB, query thứ hai có thể giảm đáng kể bytes chuyển và hydration work. DB cũng có khả năng dùng index-only scan nếu index và visibility phù hợp, nhưng không mặc định guaranteed.

Tuy nhiên, entity mapping có lazy basic attributes (`@Basic(fetch=LAZY)`) không phải một cách portable chắc chắn để giảm cột mà không có provider enhancement. Nếu muốn chọn đúng fields, DTO/scalar projection diễn đạt rõ hơn.

---

## 57. Kiểm thử hồi quy N+1 bằng dữ liệu đủ đa dạng

Một test seed 20 Orders nhưng tất cả dùng **cùng một Customer** có thể không thấy N+1 thật vì persistence context chỉ cần load một Customer.

Để phát hiện N+1 Customer:

- Seed 20 Orders với 20 Customers khác nhau.
- Đóng seed context.
- Tắt/kiểm soát L2 cache nếu test SQL count.
- Lấy Orders theo API cần kiểm thử.
- Gọi mapper/serializer giống production.
- Quan sát SQL count/pattern.
- So sánh số SQL với N=1, 10, 20.
- Đảm bảo không có test khác làm nóng caches/ghi statistics.

Tương tự, test OrderLines cần nhiều Orders có số Lines khác nhau. Dataset “mỗi Order không có Line” không thể phát hiện cost của collection fetching.

## 58. JUnit test minh họa statement growth

Một skeleton:

```java
@Test
void summaryPageShouldNotTriggerNPlusOne() {
    seedTwentyOrdersWithDistinctCustomersAndCommit();

    SqlRecorder recorder = sqlRecorder(); // Test helper riêng.
    recorder.clear();

    List<OrderSummary> result =
        orderService.getSummaryPage(
            OrderStatus.PAID,
            0,
            20
        );

    assertEquals(20, result.size());

    List<String> sql = recorder.executedStatements();

    assertFalse(
        hasRepeatedCustomerLookupPattern(sql),
        "Customer lookups should not scale linearly with orders"
    );
}
```

`SqlRecorder` và `hasRepeatedCustomerLookupPattern` là test helpers cần triển khai dựa trên datasource-proxy/P6Spy/provider statistics phù hợp, không phải API JPA chuẩn có sẵn.

Test này nên assert *behavioral performance invariant*, chẳng hạn không xuất hiện 20 SQL SELECT Customer riêng, thay vì bắt mọi provider luôn sinh đúng một SQL text y hệt nhau.

## 59. Integration test cho pagination với collection fetch

Một test quan trọng:

1. Seed ít nhất 50 Orders.
2. Mỗi Order có nhiều Lines.
3. Yêu cầu page size 20.
4. Xác minh trả đúng **20 unique Orders** và thứ tự ổn định.
5. Quan sát SQL thực tế có áp LIMIT/OFFSET đúng trên root IDs không.
6. Nếu Hibernate có option fail-on-pagination-over-collection-fetch, bật trong test phù hợp.
7. Đo rows fetched và memory khi page size tăng.
8. Xác minh không bị mất/nhân root rows.
9. Không chỉ assert Java list size mà bỏ qua việc DB đã đọc toàn bảng.
10. Kiểm tra count query có vô tình fetch collection không.

Một test trả 20 objects nhưng tải 100.000 SQL rows **vẫn có performance bug**.

## 60. Test memory footprint cho batch

Một batch 100.000 rows nên đo:

- Peak heap.
- Allocated bytes.
- GC pause/frequency.
- Throughput rows/s.
- Entity count trong persistence context nếu provider hỗ trợ.
- Database SQL count/time.
- DB transaction duration.
- Flush time theo chunk.
- Retry/commit success.

So sánh:

A. Load all managed entities vào `List`.

B. DTO projection với paged/streaming.

C. Managed entity chunk processing với flush/clear.

Không kết luận “B nhanh hơn” khi B bỏ những business updates mà A phải thực hiện. **Chỉ so sánh workloads tương đương về dữ liệu và semantics.**

## 61. Kỹ thuật benchmark công bằng

Một phép đo tốt:

1. Dùng cùng dataset, indexes, RDBMS version và driver.
2. Chạy warm-up đủ cho JIT/connection pool/cache.
3. Đo riêng cold và warm cache nếu chúng đều quan trọng.
4. Đảm bảo request outputs tương đương.
5. Dùng nhiều iterations, ghi phân bố/p95, không chỉ một mẫu.
6. Đo concurrency production-like.
7. Không bật SQL logging debug với overhead khác nhau giữa các runs.
8. Kiểm tra DB có background activity/maintenance ảnh hưởng không.
9. Không để EntityManagerFactory bootstrap nằm trong thời gian đo endpoint thường xuyên.
10. Reset/isolated counters khi đo SQL count.
11. Xác nhận data cardinality thực: số Customers/Lines/Orders.
12. Kiểm tra optimizer statistics và execution plan không đổi ngoài chủ ý.
13. Đo CPU, memory, rows và SQL cùng latency.
14. Test correctness: kết quả không mất Orders/Lines.
15. Ghi lại config để có thể lặp lại.

Nếu thử tối ưu một trang dữ liệu trống, kết quả thường không đại diện cho production.

## 62. Đánh giá tác động của read replica và cache

Một query có thể nhanh trên read replica nhưng chậm trên primary, hoặc ngược lại, vì:

- Replica lag/CPU contention.
- Page cache state khác.
- Index/statistics khác.
- Network path khác.
- Transaction isolation/visibility khác.
- Cache hit ratio khác.

Khi làm benchmark, ghi rõ DB endpoint và consistency expectations. **Không nên chuyển hết reads sang replica** để giảm DB CPU nếu business cần read-your-writes hoặc current inventory.

L2 cache có thể giúp đọc ít thay đổi nhưng cần invalidation và metrics. Đừng mặc định cache là giải pháp cho một SQL có plan tệ ở cold cache hoặc dữ liệu liên tục thay đổi.

---

## 63. Các anti-pattern thường làm mất khả năng chẩn đoán

### Anti-pattern 1: “Request chậm thì thêm `JOIN FETCH` mọi nơi”

Có thể chuyển N+1 thành Cartesian explosion, memory/DB row explosion hoặc in-memory pagination.

### Anti-pattern 2: “`EAGER` sẽ bảo đảm một SQL”

Sai. EAGER không đồng nghĩa JOIN và có thể over-fetch.

### Anti-pattern 3: “`LAZY` luôn ít SQL”

Sai. Lazy access bên trong loops/mappers có thể N+1.

### Anti-pattern 4: “Một SQL nghĩa là không còn nút thắt”

Sai. Một SQL có thể scan/sort lớn hoặc trả hàng triệu rows.

### Anti-pattern 5: “Đếm SQL count là đủ”

Sai. Cần DB elapsed, rows/bytes, allocations, P95.

### Anti-pattern 6: “SQL chậm thì chỉ cần thêm index”

Sai nếu nguyên nhân là lock wait, network hoặc result size.

### Anti-pattern 7: “DTO projection là một entity tốt hơn”

DTO không managed, không dirty checking/cascade. Dùng cho read-only workloads.

### Anti-pattern 8: “Phân trang luôn an toàn với collection JOIN FETCH”

Không. Một Order có nhiều rows khiến database paging trên join không tương đương paging root entities.

### Anti-pattern 9: “`DISTINCT` loại toàn bộ rows lặp ở DB”

Không bảo đảm; database vẫn có thể xử lý lượng join rows lớn.

### Anti-pattern 10: “Cứ bật `hibernate.jdbc.batch_size` là mọi inserts được batch”

Không. ID strategy và provider/driver ảnh hưởng.

### Anti-pattern 11: “`@Transactional(readOnly=true)` bỏ hết ORM overhead”

Không portable; behavior tùy Spring/provider.

### Anti-pattern 12: “`getResultStream()` luôn giữ constant memory”

Không. Provider có thể materialize list, và managed entities có thể vẫn ở L1.

### Anti-pattern 13: “`em.clear()` là dọn memory vô hại”

Không. Detach entities và có thể bỏ pending changes chưa flush.

### Anti-pattern 14: “Bulk JPQL UPDATE giống loop setter của managed entities”

Không. Bulk bypass callbacks/Bean Validation/version semantics thông thường và làm L1 stale.

### Anti-pattern 15: “Cache hit che được mọi N+1”

Cold cache/invalidation sẽ phơi bày N+1; caching không tự thay fetch plan.

### Anti-pattern 16: “Một test dùng cùng Customer ID đủ bắt N+1”

Không. L1 có thể chỉ load Customer một lần.

### Anti-pattern 17: “Benchmark chỉ chạy một lần”

Không đáng tin vì JIT, cache, DB statistics, concurrency.

### Anti-pattern 18: “Đếm SQL bằng Hibernate global Statistics trong parallel tests”

Dễ nhiễu vì counters thuộc SessionFactory.

### Anti-pattern 19: “Bật bind logging trên production không có rủi ro”

Có thể lộ dữ liệu nhạy cảm và tăng I/O.

### Anti-pattern 20: “Chi phí SQL luôn bằng toàn bộ `getResultList()`”

Không. Nó còn có JDBC fetch, hydration và entity management.

### Anti-pattern 21: “`EntityManagerFactory` tạo mỗi request để tối ưu isolation”

Sai về chi phí và resource management; factory thường được tái sử dụng.

### Anti-pattern 22: “DB SELECT chỉ 20 rows nghĩa là API trả đúng dữ liệu”

Có thể fetch-plan hoặc serializer phát SQL khác sau query gốc.

### Anti-pattern 23: “To-one mapping lazy đã đủ sửa SQL của mọi repository”

Không nếu query/eager nested paths hoặc mapper kích hoạt loads.

### Anti-pattern 24: “Thêm nhiều connection sẽ luôn tăng throughput”

Không nếu DB đang nghẽn locks/CPU; pool lớn có thể làm tệ hơn.

### Anti-pattern 25: “Giảm thời gian bằng cách bỏ validation/callbacks mà không xét semantics”

Không. Tối ưu performance không được làm mất business invariants và transaction correctness.

---

## 64. Bài tập thực hành

### Bài 1: Phân loại dấu hiệu

Request mất 600 ms, có 1 SQL mất 550 ms, trả 15 rows.

**Đáp án:** Ưu tiên SQL/database plan, locks, I/O, indexes; chưa có bằng chứng N+1 hay entity overhead.

### Bài 2: N+1

10 Orders + 10 distinct Customers, truy cập customer.name trong vòng lặp gây 11 SQL.

**Đáp án:** Fetch plan, cân nhắc DTO projection hoặc to-one JOIN FETCH/EntityGraph.

### Bài 3: SQL nhanh nhưng heap cao

Một SELECT 300.000 Orders, DB mất 40 ms, JVM mất 2 giây hydrate/GC.

**Đáp án:** Quản lý entity/over-materialization; phân trang, DTO, streaming/chunking.

### Bài 4: EAGER

`@ManyToOne` không chỉ định fetch type; JPQL list query vẫn phát SQL phụ.

**Câu hỏi:** Mâu thuẫn với EAGER không?

**Đáp án:** Không. EAGER không bắt buộc cùng một SQL.

### Bài 5: DTO

Summary page chỉ cần Order ID và Customer name.

**Câu hỏi:** Có cần tạo managed Order + Customer không?

**Đáp án:** Không nhất thiết. JPQL constructor DTO projection có thể đọc đúng fields.

### Bài 6: Collection JOIN

100 Orders × 15 Lines, một SQL JOIN trả khoảng 1.500 rows.

**Câu hỏi:** Một SQL có chắc nhanh hơn 2 SQL không?

**Đáp án:** Không; phải đo rows/bytes/JVM hydration/latency.

### Bài 7: Hai collections

Một Order có 12 Lines và 10 Events; fetch cả hai to-many trong cùng SQL.

**Đáp án:** Có nguy cơ 120 join rows một Order; split/batch fetch có thể tốt hơn.

### Bài 8: Pagination

Page size 20 trên query LEFT JOIN FETCH lines.

**Câu hỏi:** Có chắc DB chỉ đọc data của 20 Orders không?

**Đáp án:** Không. Provider có thể pagination in memory hoặc xử lý rất nhiều joined rows.

### Bài 9: DISTINCT

Thêm `SELECT DISTINCT o` vào collection fetch.

**Câu hỏi:** Có xóa tất cả row explosion không?

**Đáp án:** Không. Result entity unique không đồng nghĩa DB/JDBC chỉ xử lý số rows bằng số root IDs.

### Bài 10: EntityGraph

Màn hình detail cần Customer nhưng không cần Lines.

**Đáp án:** Graph với Customer có thể phù hợp; vẫn cần kiểm tra SQL thật.

### Bài 11: Batch fetch

30 Orders, mỗi Order có lazy Lines; Hibernate batch fetch size 16.

**Câu hỏi:** N+1 có thể giảm không?

**Đáp án:** Có, provider có thể gom IDs; số SQL và performance thực tế phải được đo.

### Bài 12: Query chậm có LIMIT

`WHERE status=? ORDER BY created_at DESC LIMIT 20` mất 800 ms trên bảng lớn.

**Đáp án:** Đọc actual plan, xem composite index/selectivity/sort/locks. Không bắt đầu bằng dirty checking.

### Bài 13: Deep OFFSET

`OFFSET 1000000 LIMIT 20` chậm hơn trang đầu.

**Đáp án:** Xem keyset pagination và index/order semantics nếu use case phù hợp.

### Bài 14: Lock wait

UPDATE bằng primary key mất 3 giây do chờ lock.

**Đáp án:** Xem transaction duration/lock contention, không chỉ tạo index.

### Bài 15: Pool wait

SQL mất 10 ms, request chờ pool 900 ms.

**Đáp án:** Connection pool/long transactions/concurrency bottleneck, không phải SQL optimizer trực tiếp.

### Bài 16: Flush

Context chứa 100.000 managed entities, chỉ 10 dirty, flush tốn CPU.

**Đáp án:** Xem entity management overhead, context lifetime, chunking, read-only projections.

### Bài 17: Clear

Batch persist 100 rows rồi `em.clear()` trước `flush()`.

**Câu hỏi:** Có nguy cơ gì?

**Đáp án:** Pending changes của detached entities có thể không được đồng bộ như mong muốn. Flush trước clear nếu design yêu cầu.

### Bài 18: Bulk UPDATE

Thay per-entity loop bằng JPQL bulk UPDATE nhanh hơn.

**Câu hỏi:** Cần kiểm tra gì?

**Đáp án:** Callback/Bean Validation/versioning/L1 stale state và nghiệp vụ.

### Bài 19: Hibernate read-only

`@Transactional(readOnly=true)` trên Spring service.

**Câu hỏi:** Có chắc không còn entity management overhead?

**Đáp án:** Không. Tùy provider/config; entity vẫn có thể managed.

### Bài 20: Streaming

Thay `getResultList()` bằng `getResultStream()` rồi `toList()`.

**Đáp án:** Vẫn materialize toàn bộ kết quả, không đạt mục tiêu bounded memory.

### Bài 21: Cache

Warm L2 benchmark cho SQL count thấp, cold cache bị N+1.

**Đáp án:** Cần sửa fetch plan hoặc đảm bảo SLA cả cold cases; L2 không thay thiết kế truy vấn.

### Bài 22: Count

Muốn đếm số Orders nhưng load toàn bộ entity list rồi gọi `size()`.

**Đáp án:** Dùng `SELECT COUNT(o)`, đo DB plan nếu data lớn.

### Bài 23: Bảo mật log

Bật SQL parameter logging chứa email/payment tokens trên production.

**Đáp án:** Có nguy cơ lộ dữ liệu và tăng overhead; dùng masking/sampling.

### Bài 24: Regression test

Test 20 Orders nhưng chỉ có một Customer, SQL count = 2.

**Câu hỏi:** Đã chứng minh không N+1 không?

**Đáp án:** Chưa. Seed distinct Customers và kiểm tra growth curve khi N tăng.

### Bài 25: Chọn chiến lược cuối cùng

Endpoint list 20 Orders cần id/status/createdAt/customerName/total, không sửa entities; profiler thấy 1 SQL cho Orders + 20 Customer SELECTs và allocation đáng kể.

**Gợi ý:** Thử DTO projection join Customer chỉ các fields cần, pagination ở SQL, index phù hợp; đo SQL count, DB time, rows, heap và P95. Không fetch Lines/Product khi UI không cần.

---

## 65. Checklist chẩn đoán hiệu năng JPA

Trước khi tuyên bố đã tìm đúng bottleneck:

1. Đã chọn đúng endpoint/job/use case và dữ liệu cần trả chưa?
2. Có baseline P50/P95/P99 và throughput chưa?
3. Đã đo JDBC pool acquisition wait chưa?
4. Có đếm SQL per request/unit of work không?
5. Đã nhóm các SQL giống nhau theo pattern chưa?
6. Có một SQL đơn lẻ chậm hay hàng trăm SQL nhanh?
7. Có actual database execution plan không?
8. Có phân biệt CPU/query time với lock wait không?
9. Có xem rows scanned vs returned không?
10. Có kiểm tra index/selectivity/stale statistics không?
11. Có kiểm tra deep OFFSET và sort không?
12. Có biết mọi association mapper/serializer sẽ truy cập không?
13. Có phân biệt EAGER và JOIN FETCH không?
14. Có đo N+1 bằng distinct foreign keys và caches được kiểm soát không?
15. Có chú ý EAGER to-one nested relations không?
16. Có dùng DTO projection cho read-only summary/report thích hợp không?
17. Có đo kích thước row width/result bytes không?
18. Có tránh fetch nhiều to-many collections trong một SQL không?
19. Có xem collection fetch + pagination trong provider hiện tại không?
20. Nếu dùng two-phase ID paging, có giữ đúng order của result không?
21. Có kiểm tra semantics khi concurrent changes giữa hai queries không?
22. Có biết EntityGraph không bảo đảm chỉ một SQL không?
23. Có thử batch/subselect fetching khi N+1 collections không?
24. Có đếm managed entities/heap allocation/GC không?
25. Có tách SQL DB time khỏi JDBC hydration/mapping time không?
26. Có giới hạn persistence context lifetime không?
27. Nếu flush/clear theo chunk, có bảo toàn pending changes không?
28. Có test callback/versioning/validation khi chuyển sang bulk DML không?
29. Có hiểu ID generation ảnh hưởng JDBC insert batching không?
30. Có đo L2 cache cold và warm workloads không?
31. Có đóng streams/EntityManagers/transactions đúng vòng đời không?
32. Có dùng database và dữ liệu production-like không?
33. Có tránh logging overhead trong benchmark không?
34. Có giảm dữ liệu được trả đúng API contract không?
35. Có dùng HTTP/DTO serialization profiling không?
36. Có tests cho SQL count growth và N+1 không?
37. Có tests cho pagination correctness và row multiplication không?
38. Có tests với nhiều association cardinalities khác nhau không?
39. Có giữ correctness, locking và transaction semantics sau tối ưu không?
40. Có đo lại sau mỗi thay đổi một cách công bằng không?

Checklist không yêu cầu bật mọi công cụ cho mọi request. Nó giúp **phân loại chính xác nguyên nhân trước khi sửa code**.

## Kết luận

Khi một ứng dụng JPA chậm, hãy phân biệt ba nhóm nguyên nhân lớn:

1. **Nút thắt SQL/database**: ít SQL nhưng query execution, scan, sort, I/O, lock hoặc OFFSET quá đắt. Điều tra bằng generated SQL, actual execution plan, index/statistics và DB monitoring.
2. **Nút thắt kế hoạch tải**: quá nhiều roundtrips do N+1, hoặc quá nhiều joined rows do over-fetch/Cartesian explosion. Điều chỉnh fetch plan theo use case bằng projection, to-one JOIN FETCH, EntityGraph, batch fetching hoặc split queries. Không biến mọi association thành EAGER.
3. **Chi phí quản lý entity**: DB trả dữ liệu nhanh nhưng Java phải hydrate quá nhiều managed entities, quản lý identity/snapshots/dirty checking, map DTO và GC. Với read-only reporting, ưu tiên DTO/scalar và bounded pagination; với batch updates, quản lý context/flush/clear và transaction chunks có chủ đích.

Thêm vào đó, **connection pool, serialization, cache, transaction contention và network** có thể gây latency lớn mà không thuộc riêng một trong ba nhóm.

Hãy nhớ ba đối chiếu then chốt: **ít SQL không có nghĩa SQL nhanh; một SQL không có nghĩa ít dữ liệu; và SQL nhanh không có nghĩa request nhanh**.

Quy trình hiệu quả là: **đo tổng thời gian → đếm và phân nhóm SQL → đọc database plan/row counts → đo Java allocations/hydration → chọn một tối ưu đúng nhóm → chạy lại benchmark và regression tests**. Đó là cách tối ưu JPA dựa trên nguyên nhân thay vì thay annotation theo trực giác.

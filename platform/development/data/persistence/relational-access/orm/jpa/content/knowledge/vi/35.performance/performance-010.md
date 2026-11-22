# Kết hợp chỉ mục cơ sở dữ liệu với điều kiện JPQL thực tế

Trong một ứng dụng JPA, câu JPQL ngắn chưa chắc dẫn tới một truy vấn database nhanh:

```java
List<PurchaseOrder> orders = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.tenantId = :tenantId " +
    "AND o.status = :status " +
    "ORDER BY o.createdAt DESC, o.id DESC",
    PurchaseOrder.class
).setParameter("tenantId", tenantId)
 .setParameter("status", OrderStatus.PAID)
 .setMaxResults(20)
 .getResultList();
```

Khi bảng có hàng triệu dòng, database phải tìm đúng tenant, chọn trạng thái, sắp xếp theo thời gian và chỉ trả 20 đơn mới nhất. Một composite index như sau có thể phù hợp:

```sql
CREATE INDEX idx_order_tenant_status_created_id
ON purchase_orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
```

Tuy nhiên, **có index không có nghĩa database chắc chắn sử dụng nó hoặc truy vấn chắc chắn nhanh**. Một câu JPQL có thể bị biến đổi bởi fetch graph, soft-delete filter, tenant predicate, paging và mapping. Cơ sở dữ liệu còn lựa chọn kế hoạch theo statistics, độ chọn lọc của điều kiện, chi phí I/O và phân bố dữ liệu. Vì vậy, thiết kế index phải xuất phát từ **SQL thật và execution plan thật**, không chỉ nhìn Java property names.

Bài **“Kết hợp chỉ mục cơ sở dữ liệu với điều kiện JPQL thực tế”**, thuộc chương **Hiệu năng** của chủ đề **Data Persistence Relational Access ORM JPA**, trình bày:

- Đọc JPQL, Criteria API rồi đối chiếu với SQL do provider tạo.
- Phân tích điều kiện equality, range, IN, NULL, LIKE, function, JOIN, ORDER BY và pagination.
- Chọn index một cột, nhiều cột, partial, expression, unique và covering.
- Hiểu nguyên tắc equality-prefix-range-sort, giới hạn của các index.
- Dùng EXPLAIN/ANALYZE, actual rows, buffer reads và metrics để kiểm chứng.
- Phân biệt index tuning với N+1, over-fetch và chi phí hydration của entity.
- Thiết kế migration, benchmark, integration test và regression monitoring.

Các ví dụ dùng Java 17+, Jakarta Persistence 3.x và SQL quan hệ. PostgreSQL được sử dụng cho những ví dụ index nâng cao; MySQL, SQL Server, Oracle hoặc những database khác có cú pháp, statistics và optimizer riêng. **Không coi tính năng index đặc thù của PostgreSQL là một phần của JPQL/JPA chuẩn.**

---

## 1. Từ JPQL đến dữ liệu: index nằm ở bước nào?

```text
Application service
     │
     ▼
JPQL / Criteria API / Repository
     │
     ▼
JPA provider
  - Entity/property → table/column
  - Fetch graph, joins, tenant filters
  - Bind parameters, paging, SQL dialect
     │
     ▼
JDBC query
     │
     ▼
Database query planner
  - Chọn index scan hay table scan
  - Chọn join order/algorithm
  - Dự đoán row count, chi phí sort
  - Xử lý I/O, memory, lock waits
     │
     ▼
Rows / ResultSet
     │
     ▼
JPA hydration, managed entities hoặc DTO
     │
     ▼
Mapper / JSON response
```

Chỉ mục trực tiếp giúp database truy cập, lọc, sắp xếp và nối rows hiệu quả hơn. Nó **không tự loại bỏ** số SQL N+1 do ORM phát sinh, không biến một JOIN FETCH hai collections thành tập kết quả nhỏ, và không loại chi phí tạo 100.000 managed entities.

Trước khi tạo index, hãy phân biệt bottleneck.

| Dấu hiệu | Vấn đề nên điều tra trước | Công cụ |
| --- | --- | --- |
| Một SQL mất 800 ms, chỉ trả 20 rows | Query plan, index, sort, lock/I/O | Actual EXPLAIN, slow query metrics |
| 101 SQL mỗi request | N+1, fetch plan | SQL count và tracing |
| SQL chạy 20 ms nhưng request mất 900 ms | Result transfer/hydration/JSON/GC | JDBC timings, JVM profiler |
| Request chờ connection 700 ms | Pool/transaction/threads | Connection pool metrics |
| Page đầu nhanh, page số 5000 chậm | OFFSET, sort/index | Plan theo page, keyset benchmark |
| Chỉ tenant lớn bị chậm | Data skew, selectivity, plan cache | Per-tenant data distribution |

**Một request có thể có nhiều bottleneck đồng thời.** Tối ưu đúng SQL nhưng vẫn N+1 thì latency có thể không giảm như mong muốn.

## 2. Xác định một truy vấn thật trước khi tối ưu

Ví dụ endpoint:

```text
GET /tenants/7/orders?status=PAID&size=20

Yêu cầu:
- Chỉ thấy Order của tenant 7
- Chỉ trạng thái PAID
- Chỉ Orders chưa soft-delete
- Đơn mới nhất trước
- Nếu hai Orders có cùng createdAt, dùng id làm tie-breaker
- Trả id, createdAt, status, totalAmount, customerName
```

Ta cần đo:

1. SQL được JPA gửi, gồm JOIN và filter bổ sung.
2. Số rows được database kiểm tra và trả về.
3. Thời gian execution của từng SQL.
4. Số SQL từ query/mapping/serialization.
5. Tổng request latency P50/P95/P99.
6. Số Orders/Customers theo tenant.
7. Chỉ mục và DB statistics hiện có.
8. Workload đọc/ghi trên bảng.

**Không tối ưu một chuỗi JPQL trừu tượng khi chưa biết data contract và mức tải thực tế.**

## 3. Entity và schema dùng xuyên suốt

Một mô hình đơn hàng đa tenant:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "order_no", nullable = false, length = 40)
    private String orderNo;

    @Enumerated(EnumType.STRING)
    @Column(name = "status", nullable = false)
    private OrderStatus status;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Column(name = "deleted_at")
    private Instant deletedAt;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "customer_id")
    private Customer customer;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    private Long version;

    protected PurchaseOrder() {}

    // Constructors, getters, business methods...
}
```

Customer:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private Long tenantId;

    @Column(name = "email", nullable = false)
    private String email;

    @Column(name = "display_name")
    private String displayName;

    protected Customer() {}
}
```

Schema logic:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(160)
);

CREATE TABLE purchase_orders (
    id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_no VARCHAR(40) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    total_amount DECIMAL(14,2) NOT NULL,
    deleted_at TIMESTAMP,
    version BIGINT NOT NULL,
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE order_lines (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(14,2) NOT NULL,
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
```

DDL trên chỉ minh họa bảng và ràng buộc. Chi tiết auto-generated IDs, timestamp, precision và migrations phải phù hợp DB/dialect thật.

**Lưu ý:** JPQL dùng tên Java `tenantId` và `createdAt`; SQL dùng `tenant_id` và `created_at`. Khi tạo index phải dùng tên cột **thật trong database**, không dùng tên property Java.

---

## 4. Workflow tối ưu có thể lặp lại

```text
1. Chọn endpoint/job đang chậm
          ↓
2. Thu SQL thật và bind types/parameters an toàn
          ↓
3. Đo SQL count + DB execution time + row counts
          ↓
4. Phân loại equality/range/join/sort/paging
          ↓
5. Đọc actual query plan và existing indexes
          ↓
6. Đề xuất một hoặc vài candidate indexes
          ↓
7. Tạo index ở môi trường đại diện
          ↓
8. Đo trước/sau cả SELECT lẫn INSERT/UPDATE/DELETE
          ↓
9. Test dữ liệu, tenant scope, sort và pagination đúng
          ↓
10. Deploy migration, theo dõi regression
```

Việc cải thiện phải dựa trên **thay đổi định lượng** thay vì chỉ nhìn query planner có nhắc tới index mới.

## 5. Đọc SQL generated, không chỉ đọc JPQL

JPQL:

```java
"SELECT o FROM PurchaseOrder o WHERE o.status = :status"
```

có thể sinh SQL nhiều hơn bạn tưởng do:

- Ánh xạ inheritance/discriminator.
- FetchType.EAGER cho một số relationships.
- Tenant filter hoặc soft-delete predicate.
- EntityGraph/JOIN FETCH.
- Pagination, sort do Spring Data tạo.
- Criteria API bổ sung điều kiện.
- SQL dialect/cast cần cho parameter types.
- Cấu trúc JOIN khi truy cập association path.

Ngay cả `findAll()` không chứa JOIN trong Java cũng có thể phát SQL phụ để nạp EAGER associations. Một index trên bảng Orders không tự giải quyết 20 SELECT Customers phát sinh thêm.

### Công cụ thu SQL

Có thể sử dụng Hibernate SQL logging, datasource-proxy, P6Spy, JDBC tracing, APM hoặc DB-side slow query logs. Với Hibernate Statistics (provider-specific) có thể xem statement/query counts và cache hits. DB-side metrics như PostgreSQL `pg_stat_statements` hữu ích để biết SQL patterns nào tiêu tốn tổng thời gian nhiều nhất.

Cần bảo mật parameters: đừng bật bind logging chứa email, token, định danh cá nhân hoặc dữ liệu thanh toán trên production nếu không có masking và kiểm soát truy cập phù hợp.

## 6. Một query chậm không nhất thiết do index

Các nguyên nhân khác:

- Chờ row/table lock.
- Chờ lấy JDBC connection.
- Database CPU/memory saturated.
- Sort lớn đổ ra disk.
- Kết nối mạng chậm.
- Trả quá nhiều bytes/rows.
- Entity hydration và persistence context quá lớn.
- Các SQL N+1 cộng dồn latency.
- Cache cold/warm chênh lệch.
- Large OFFSET.
- Prepared/generic plan không phù hợp một tenant.

Chỉ tạo index khi actual plan/row counts cho thấy database access/search/sort là một phần đáng kể.

---

## 7. Index B-tree phù hợp với những điều kiện nào?

B-tree thường phù hợp với exact lookup, range scan và đọc dữ liệu theo thứ tự index:

| Điều kiện SQL | Khả năng dùng B-tree | Lưu ý |
| --- | --- | --- |
| `column = ?` | Thường tốt | Tùy selectivity/data |
| `column IN (?, ?)` | Có thể tốt | Nhiều values có thể cần merge/sort |
| `column >= ? AND column < ?` | Thường tốt | Range scan |
| `ORDER BY column LIMIT 20` | Có thể tốt | Khi prefix/filter/sort khớp |
| `column IS NULL` | Có thể | DB/index type/selectivity khác nhau |
| `column LIKE 'abc%'` | Có thể | Phụ thuộc collation/operator class |
| `column LIKE '%abc%'` | B-tree thường không phù hợp | Cần search index khác nếu lớn |
| `LOWER(column) = ?` | Raw-column index có thể không phù hợp | Expression index/collation |
| `DATE(timestamp_col) = ?` | Có thể mất range optimization | Thường rewrite thành range |
| `column <> ?` | Có thể ít lợi | Nếu giữ lại phần lớn rows |

Đây là hướng dẫn, không phải bảo đảm. Optimizer có thể chọn Seq Scan nếu bảng nhỏ hoặc điều kiện lấy đa số rows.

## 8. Sargability: điều kiện giúp DB tìm đúng dải index

Predicate dễ tận dụng index timestamp:

```sql
WHERE created_at >= :from
  AND created_at < :to
```

Predicate thường kém phù hợp với index raw timestamp:

```sql
WHERE DATE(created_at) = :date
```

Với query trên:

```java
"WHERE FUNCTION('date', o.createdAt) = :date"
```

provider có thể gọi DB function, khiến DB phải tính giá trị trên nhiều rows hoặc cần expression index tương ứng.

Thay bằng:

```java
"WHERE o.createdAt >= :from " +
"AND o.createdAt < :to"
```

là một lựa chọn dễ portable và thường phù hợp range index hơn.

Nếu DB có expression index cho DATE(created_at), plan có thể khác; cần đo thay vì khẳng định mọi function predicate đều chậm.

## 9. Chuyển ngày nghiệp vụ thành half-open range

Ví dụ lọc ngày ở timezone Việt Nam:

```java
LocalDate day = LocalDate.of(2026, 11, 15);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant start = day
    .atStartOfDay(zone)
    .toInstant();

Instant end = day
    .plusDays(1)
    .atStartOfDay(zone)
    .toInstant();
```

JPQL:

```java
"WHERE o.createdAt >= :start " +
"AND o.createdAt < :end"
```

Với khoảng `[start, end)`, hai ngày kề nhau không chồng mốc. Đây cũng là cách tránh viết `23:59:59.999` phụ thuộc precision.

Mapping `Instant`, timezone/column type và JDBC configuration phải phù hợp quy ước lưu thời gian của hệ thống; không suy rằng mọi kiểu SQL TIMESTAMP luôn là UTC.

## 10. Một index riêng cho mỗi field chưa chắc tối ưu

Giả sử:

```sql
CREATE INDEX idx_orders_tenant ON purchase_orders(tenant_id);
CREATE INDEX idx_orders_status ON purchase_orders(status);
CREATE INDEX idx_orders_created ON purchase_orders(created_at);
```

Query:

```sql
WHERE tenant_id = 7
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Một số DB có thể kết hợp nhiều indexes bằng bitmap/index merge, nhưng còn sort, row fetching và overhead. Một composite index sắp đúng columns có thể hiệu quả hơn khi query hot.

Tuy nhiên, không xóa indexes cũ hoặc thêm index tổng hợp chỉ bằng trực giác; cần xem toàn workload và plan.

---

## 11. Composite index và thứ tự cột

Candidate:

```sql
CREATE INDEX idx_orders_tenant_status_date_id
ON purchase_orders (
    tenant_id,
    status,
    created_at DESC,
    id DESC
);
```

Query:

```sql
WHERE tenant_id = ?
  AND status = ?
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

có thể thuận lợi:

1. Cố định tenant equality.
2. Thu hẹp status equality.
3. Duyệt rows theo created_at/id đã sắp.
4. Dừng khi đủ 20 rows nếu kế hoạch, filter và visibility cho phép.

Trong B-tree composite, các cột dẫn đầu có ý nghĩa quan trọng. Nhưng DB engines có skip-scan, bitmap, index merge hoặc lựa chọn khác; “leftmost prefix” là **quy tắc thực hành**, không phải một định luật giống nhau trên mọi RDBMS.

## 12. Equality trước range/sort: hướng dẫn phổ biến

Đối với:

```sql
WHERE tenant_id = 7
  AND status = 'PAID'
  AND created_at >= :start
  AND created_at < :end
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

index `(tenant_id, status, created_at DESC, id DESC)` là candidate hợp lý.

Mô hình:

```text
Equality columns
     ↓
Range / ORDER BY column
     ↓
Tie-breaker
     ↓
Covering columns khi phù hợp
```

Đây không phải công thức tuyệt đối. Thứ tự hai equality columns có thể phụ thuộc tần suất các query variants không dùng đầy đủ cả hai, tính chọn lọc và đặc tính engine.

## 13. Range đứng quá sớm có thể làm giảm lợi ích của các cột sau

So sánh:

```sql
-- Candidate A
(tenant_id, created_at DESC, status)

-- Candidate B
(tenant_id, status, created_at DESC)
```

Với `tenant_id = ? AND status = ? AND created_at >= ?`, candidate B thường đáng thử vì status equality giúp thu hẹp trước dải date.

Với query `tenant_id = ? ORDER BY created_at DESC` **không lọc status**, candidate A có thể phù hợp hơn.

Một index “tốt nhất” cho query A không nhất thiết tốt nhất cho query B. Hãy ghi tần suất truy vấn và tác động write trước khi duy trì hai indexes.

## 14. Index theo equality + ORDER BY

Query list đơn hàng một tenant:

```java
String jpql =
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.tenantId = :tenantId " +
    "ORDER BY o.createdAt DESC, o.id DESC";
```

Candidate:

```sql
CREATE INDEX idx_orders_tenant_created_id
ON purchase_orders (
    tenant_id,
    created_at DESC,
    id DESC
);
```

Điều kiện tenant equality đi trước hai cột sort.

**Không tự cho rằng index `(tenant_id, status, created_at)` đủ phục vụ thứ tự toàn tenant**, vì khi status không bị cố định, index sẽ nhóm rows theo status trước.

## 15. Thứ tự predicates viết trong JPQL không phải thứ tự index

Hai JPQL/SQL filters:

```sql
WHERE tenant_id = 7 AND status = 'PAID'
```

và:

```sql
WHERE status = 'PAID' AND tenant_id = 7
```

có ngữ nghĩa tương đương đối với những predicate thuần này. Optimizer quyết định access path; không phải vì bạn viết tenant trước trong chuỗi JPQL nên DB “đi theo thứ tự” đó.

Điều cần quan tâm là **thứ tự cột trong định nghĩa index** và actual execution plan.

## 16. ORDER BY nhiều cột và tie-breaker

Nếu sort chỉ:

```java
"ORDER BY o.createdAt DESC"
```

nhiều Orders cùng timestamp có thể đổi thứ tự giữa các executions, gây duplicate/missing items khi phân trang.

Nên có tie-breaker:

```java
"ORDER BY o.createdAt DESC, o.id DESC"
```

Index có thể chứa cả created_at và id theo thứ tự phù hợp.

Chi tiết ASC/DESC, index scan ngược, mixed ordering và NULLS FIRST/LAST tùy engine. Đừng tạo cả ASC và DESC indexes theo phản xạ; kiểm tra plan vì B-tree có thể được quét ngược.

## 17. LIMIT/OFFSET và giới hạn của index

JPQL dùng:

```java
query.setFirstResult(200000);
query.setMaxResults(20);
```

Một index đúng có thể tránh sort lớn, nhưng database thường vẫn phải **skip rất nhiều entries** trước khi trả 20 rows.

Nếu màn hình cần duyệt tuần tự qua các trang, **keyset pagination** đáng thử.

SQL dạng keyset:

```sql
SELECT id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = :tenantId
  AND (
       created_at < :lastCreatedAt
       OR (
           created_at = :lastCreatedAt
           AND id < :lastId
       )
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

Candidate index `(tenant_id, created_at DESC, id DESC)` hỗ trợ lọc và thứ tự. Predicate OR có thể được optimizer xử lý khác nhau; đo plan thật, đặc biệt trên DB/driver cụ thể.

## 18. Viết keyset JPQL portable

```java
String jpql =
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.tenantId = :tenantId " +
    "AND (" +
    "  o.createdAt < :lastCreatedAt " +
    "  OR (" +
    "    o.createdAt = :lastCreatedAt " +
    "    AND o.id < :lastId" +
    "  )" +
    ") " +
    "ORDER BY o.createdAt DESC, o.id DESC";

List<PurchaseOrder> page = em.createQuery(
    jpql, PurchaseOrder.class
).setParameter("tenantId", tenantId)
 .setParameter("lastCreatedAt", lastCreatedAt)
 .setParameter("lastId", lastId)
 .setMaxResults(pageSize)
 .getResultList();
```

Trang đầu cần query không có cursor predicate. Cursor phải mang cùng tenant/filter/sort scope và được bảo vệ trước việc dùng chéo tenant. Các cột sort cần có semantics phù hợp khi null/concurrent updates.

Keyset không thay thế mọi yêu cầu “nhảy tới trang số N” nhưng thường cải thiện duyệt sâu có thứ tự ổn định.

---

## 19. Unique index cho exact lookup

JPQL:

```java
PurchaseOrder order = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.tenantId = :tenantId " +
    "AND o.orderNo = :orderNo",
    PurchaseOrder.class
).setParameter("tenantId", tenantId)
 .setParameter("orderNo", orderNo)
 .getSingleResult();
```

Nếu business rule là mã đơn duy nhất trong tenant, dùng ràng buộc:

```sql
ALTER TABLE purchase_orders
ADD CONSTRAINT uq_orders_tenant_no
UNIQUE (tenant_id, order_no);
```

Nhiều DB thực thi UNIQUE bằng index. Vì vậy một unique key có thể đồng thời bảo vệ integrity và tăng tốc lookup. Không tạo một index không unique trùng cùng columns nếu đã có unique index đủ dùng, trừ khi có lý do cụ thể đã đo.

`getSingleResult()` không tự bảo đảm tính duy nhất dữ liệu. Nếu thiếu UNIQUE thật, hai concurrent writers vẫn có thể tạo trùng orderNo.

## 20. `IN` với nhiều giá trị và ORDER BY

JPQL:

```java
"WHERE o.tenantId = :tenantId " +
"AND o.status IN :statuses " +
"ORDER BY o.createdAt DESC"
```

Một index `(tenant_id, status, created_at DESC)` có thể giúp tìm theo từng status, nhưng khi `statuses` có nhiều giá trị, index đang nhóm theo status trước. DB có thể cần **merge hoặc sort** để tạo thứ tự createdAt toàn cục.

Nếu query chọn gần như tất cả statuses và quan trọng nhất là latest first, index `(tenant_id, created_at DESC, id DESC)` có thể hợp lý hơn.

Danh sách `IN` quá dài còn có thể gây overhead ở bind variables, planner, SQL text và chạm giới hạn DB. Cần xử lý collection rỗng để không tạo SQL `IN ()` không portable.

## 21. Low cardinality và selectivity của status

Giả sử 80% Orders có `status = PAID`. Một index đơn:

```sql
CREATE INDEX idx_orders_status
ON purchase_orders(status);
```

chưa chắc hữu ích cho `WHERE status='PAID'` vì phần lớn rows được chọn. DB có thể chọn scan.

Nhưng với query có tenant equality, sort và LIMIT, composite index `(tenant_id, status, created_at DESC, id DESC)` vẫn có thể hiệu quả.

**Selectivity là thuộc tính của điều kiện trên dữ liệu thật**, không chỉ của từng column. Status hiếm ở tenant A có thể rất phổ biến ở tenant B.

## 22. Data skew theo tenant

Ví dụ:

```text
Tenant A:       500 Orders
Tenant B:  8.000.000 Orders
Tenant C:     35.000 Orders
```

Cùng SQL và index có thể có latency/plan khác nhau theo tenant:

- Row count khác.
- Tỷ lệ PAID/CANCELLED khác.
- Customer/order cardinality khác.
- Planner estimates khác.
- Parameter sniffing/generic plans khác theo DB.
- Partitioning/extended statistics có thể ảnh hưởng.

Benchmark chỉ với tenant A thường không phản ánh tenant B. Với prepared statements, phải xem DB có dùng cached/generic plan phù hợp mọi parameter values không.

## 23. Bind parameters an toàn và đúng kiểu

Dùng:

```java
query.setParameter("tenantId", tenantId);
query.setParameter("status", status);
```

thay vì nối input vào query string:

```java
// Không làm: SQL/JPQL injection và plan fragmentation.
String jpql =
    "SELECT o FROM PurchaseOrder o WHERE o.orderNo = '"
    + userInput + "'";
```

Binding giữ type semantics và giảm nguy cơ injection. Nhưng cần bảo đảm Java type khớp property/DB type; implicit casts quanh indexed column có thể khiến plan kém.

Nếu SQL phát `CAST(order_no AS BIGINT) = ?` trong khi orderNo là VARCHAR, tìm nguyên nhân type mismatch hoặc function ở JPQL trước khi thêm index.

---

## 24. Optional filters và bẫy OR

JPQL tiện lợi:

```java
"WHERE o.tenantId = :tenantId " +
"AND (:status IS NULL OR o.status = :status)"
```

Một số DB có thể khó tối ưu cùng prepared plan cho hai trường hợp “có status” và “không status”. Các OR predicates có thể thay đổi selectivity estimate/access path.

Có thể dùng hai query variants hoặc Criteria API để tạo đúng predicates xuất hiện.

```java
CriteriaBuilder cb = em.getCriteriaBuilder();
CriteriaQuery<PurchaseOrder> cq =
    cb.createQuery(PurchaseOrder.class);

Root<PurchaseOrder> root =
    cq.from(PurchaseOrder.class);

List<Predicate> predicates = new ArrayList<>();

predicates.add(
    cb.equal(root.get("tenantId"), tenantId)
);

if (status != null) {
    predicates.add(
        cb.equal(root.get("status"), status)
    );
}

cq.where(predicates.toArray(Predicate[]::new));
cq.orderBy(
    cb.desc(root.get("createdAt")),
    cb.desc(root.get("id"))
);

List<PurchaseOrder> page = em.createQuery(cq)
    .setMaxResults(20)
    .getResultList();
```

Dùng imports `jakarta.persistence.criteria.*` và `java.util.*` phù hợp.

Không khẳng định OR luôn chậm. Với query hot, **so sánh SQL/plans theo cả hai kiểu parameters** rồi quyết định.

## 25. Soft-delete và `IS NULL`

JPQL:

```java
"WHERE o.tenantId = :tenantId " +
"AND o.status = :status " +
"AND o.deletedAt IS NULL " +
"ORDER BY o.createdAt DESC, o.id DESC"
```

Có thể dùng composite index gồm `deleted_at`:

```sql
CREATE INDEX idx_orders_active_filter
ON purchase_orders(
    tenant_id, deleted_at, status, created_at DESC, id DESC
);
```

Nhưng nếu đa số rows chưa xóa, column deleted_at có selectivity thấp. PostgreSQL hỗ trợ partial index:

```sql
CREATE INDEX idx_active_orders_status_date
ON purchase_orders(
    tenant_id, status, created_at DESC, id DESC
)
WHERE deleted_at IS NULL;
```

Index chỉ gồm active rows, có thể giảm size/maintenance. Tuy nhiên:

- Đây là PostgreSQL-specific.
- Query predicate phải đủ rõ để optimizer chứng minh khớp partial index.
- Các query tìm deleted rows không được index này phục vụ.
- Nếu hầu hết rows active, lợi ích size có thể nhỏ.
- Phải đo query/write costs và tenant data distribution.
- Parameterized conditions có thể ảnh hưởng predicate implication.

## 26. Khi nào partial index phù hợp?

Thường đáng thử khi:

- Một phần nhỏ rows được truy vấn thường xuyên.
- Điều kiện lọc ổn định, ví dụ `deleted_at IS NULL`.
- Query hot luôn áp filter đó.
- Database có filtered/partial index đúng semantics.
- Không cần index toàn bộ historical data cho các use cases khác.

Không nên dùng partial index như cách thay một constraint bảo mật hoặc soft-delete policy ở application. Nếu query bỏ predicate, data vẫn có thể được đọc; index không quyết định quyền truy cập.

## 27. `NULL` và comparison semantics

Trong SQL:

```sql
WHERE deleted_at IS NULL
```

khác:

```sql
WHERE deleted_at = NULL
```

Vì NULL dùng three-valued logic, phải viết IS NULL trong JPQL/SQL theo đúng ý định.

Index hỗ trợ null keys/IS NULL khác nhau theo engine và index type. Nếu dùng composite index, null distribution và stats vẫn ảnh hưởng planner.

---

## 28. `LIKE` prefix và contains

Các tìm kiếm:

| Search | Predicate | B-tree thường có ích? |
| --- | --- | --- |
| Exact code | `code = 'ABC123'` | Có |
| Starts-with | `code LIKE 'ABC%'` | Có thể, tùy collation/operator class |
| Contains | `name LIKE '%board%'` | Thường không bằng B-tree mặc định |
| Case-insensitive exact | `LOWER(email)=...` | Expression/generated/collation |
| Case-insensitive contains | DB-specific search | Trigram/fulltext/search engine |

Đừng tạo một B-tree index cho `productName` rồi coi contains search `'%term%'` đã được tối ưu.

Trên PostgreSQL, extension `pg_trgm` và trigram indexes có thể phù hợp contains/ILIKE patterns; trên các DB khác có full-text/index/search features riêng. Cần xét ngôn ngữ, accent, Unicode và business search semantics.

## 29. `LOWER(column)` có thể cần expression index

JPQL:

```java
"SELECT c FROM Customer c " +
"WHERE c.tenantId = :tenantId " +
"AND LOWER(c.email) = :normalizedEmail"
```

Generated SQL có thể là:

```sql
WHERE tenant_id = ?
  AND LOWER(email) = ?
```

Index trên `email` gốc không nhất thiết hỗ trợ expression. PostgreSQL có:

```sql
CREATE INDEX idx_customers_tenant_lower_email
ON customers(
    tenant_id,
    LOWER(email)
);
```

Nếu business yêu cầu uniqueness theo dạng đó:

```sql
CREATE UNIQUE INDEX uq_customers_tenant_lower_email
ON customers(
    tenant_id,
    LOWER(email)
);
```

Nhưng cần định nghĩa canonicalization, Unicode normalization, collation và đặc điểm email. `LOWER` không tự giải mọi vấn đề equivalence đa ngôn ngữ. Nếu application normalize một kiểu còn DB index normalize kiểu khác, uniqueness có thể sai.

## 30. `ORDER BY LOWER(name)` khác ORDER BY raw column

JPQL:

```java
"ORDER BY LOWER(c.displayName)"
```

Index trên `display_name` nguyên gốc có thể không khớp thứ tự biểu thức. Cân nhắc expression index, generated sort column hoặc DB collation phù hợp.

Tuy nhiên, thêm một index chỉ để tăng tốc sort của một trang ít sử dụng có thể không đáng. Đo sort node, memory/disk spills và tần suất query.

---

## 31. JOIN Customer và tìm theo email

JPQL:

```java
"SELECT o FROM PurchaseOrder o " +
"JOIN o.customer c " +
"WHERE o.tenantId = :tenantId " +
"AND c.tenantId = :tenantId " +
"AND LOWER(c.email) = :email " +
"ORDER BY o.createdAt DESC"
```

DB có thể cần:

```sql
CREATE INDEX idx_customers_tenant_lower_email
ON customers(tenant_id, LOWER(email));

CREATE INDEX idx_orders_customer_created
ON purchase_orders(customer_id, created_at DESC);
```

Nhưng index selection còn phụ thuộc join order:

- Tìm một Customer bằng email trước rồi Orders của Customer?
- Hay duyệt Orders tenant mới nhất rồi kiểm tra Customer?
- Email có selective/unique không?
- Một Customer có bao nhiêu Orders?
- Join có filters soft-delete/tenant khác không?
- LIMIT/ORDER BY tác động join strategy ra sao?

Index trên cả hai bảng có thể hữu ích, nhưng không mặc định “index mọi join key” luôn đem lại lợi ích xứng đáng với write overhead.

## 32. Foreign key không nhất thiết có index ở bảng con

```sql
FOREIGN KEY (customer_id) REFERENCES customers(id)
```

bảo đảm referential integrity, nhưng **không phải mọi RDBMS tự tạo secondary index trên child referencing column**. Ví dụ PostgreSQL không mặc nhiên tạo index cho foreign key bên con.

Vì vậy index `purchase_orders(customer_id)` có thể giúp:

- Truy vấn Orders theo Customer.
- JOIN parent-to-child.
- Một số referential integrity checks khi xóa/sửa parent.
- Giảm table scanning trong workload phù hợp.

Nhưng với bảng nhỏ hoặc query hiếm, index có thể không cần thiết. Điều quan trọng là **plan và workload thực tế**.

## 33. Thứ tự tenant và customer trong composite index

Hai candidate indexes:

```sql
(tenant_id, customer_id, created_at DESC)
(customer_id, created_at DESC)
```

Candidate đầu phù hợp query tenant-scoped, nhất là nếu customer IDs chỉ unique trong tenant hoặc workload cần tenant prefix. Candidate sau có thể đủ với customer IDs unique toàn cục và query theo customer.

**Không bỏ tenant condition trong JPQL để tối ưu query**: đó là vấn đề bảo mật/tenant isolation. Chọn index phục vụ predicate bắt buộc, không thay đổi scope authorization.

## 34. JOIN khác JOIN FETCH

JPQL lọc theo Customer:

```java
"SELECT o FROM PurchaseOrder o " +
"JOIN o.customer c " +
"WHERE c.email = :email"
```

JPQL tải Customer cùng Order:

```java
"SELECT o FROM PurchaseOrder o " +
"JOIN FETCH o.customer " +
"WHERE o.tenantId = :tenantId"
```

Cả hai có thể dùng SQL JOIN, nhưng:

- JOIN lọc theo association.
- JOIN FETCH yêu cầu tải association cho entity graph.
- JOIN FETCH có thể tăng số columns và hydration.
- JOIN FETCH to-many có thể nhân nhiều SQL rows.
- Index giúp JOIN tìm rows nhưng không giảm chi phí quản lý entity tự động.
- Một DTO projection JOIN Customer name có thể hợp hơn list endpoint.

Thiết kế index theo SQL; thiết kế fetch plan theo dữ liệu thật sự cần.

## 35. Đừng chữa N+1 chỉ bằng index

Ví dụ:

```java
List<PurchaseOrder> orders = loadTwentyOrders();

for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getDisplayName()
    );
}
```

Với lazy associations, có thể tạo 1 SQL Orders + 20 SQL Customers. Từng Customer SELECT có thể dùng PK index rất tốt, nhưng 21 roundtrips vẫn tốn latency.

Hướng sửa N+1:

- DTO projection JOIN Customer name.
- To-one JOIN FETCH có chọn lọc.
- EntityGraph phù hợp use case.
- Batch fetching provider-specific.

Một index mới trên Orders không tự gom 20 SQL Customers thành một.

## 36. Đừng chữa Cartesian explosion bằng index

JPQL fetch hai to-many collections:

```java
"SELECT DISTINCT o FROM PurchaseOrder o " +
"LEFT JOIN FETCH o.lines " +
"LEFT JOIN FETCH o.auditEvents"
```

Nếu một Order có 10 Lines và 8 AuditEvents, joined SQL có thể trả khoảng 80 rows cho một root Order. Dù có indexes tốt trên `order_id` ở hai bảng con, phép nhân dữ liệu vẫn tồn tại.

Cân nhắc split queries, batch fetching, selective DTO projections hoặc chỉ fetch collection thật sự cần. `DISTINCT` trên root entities không tự làm result set của database hết nhân rows.

---

## 37. Covering index và DTO projection

List endpoint chỉ cần:

```sql
SELECT id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = 7
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Candidate PostgreSQL:

```sql
CREATE INDEX idx_orders_summary_cover
ON purchase_orders(
    tenant_id, status, created_at DESC, id DESC
)
INCLUDE (total_amount);
```

Nếu index chứa những columns query cần, optimizer **có thể** sử dụng index-only scan. Nhưng PostgreSQL có visibility map/heap visibility rules: index-only không luôn tránh truy cập heap.

Phân biệt:

- Key columns dùng tìm kiếm/sắp xếp.
- INCLUDE columns là payload để cover projection, không cho cùng lợi thế search ordering.
- INCLUDE làm index rộng hơn và tăng write cost.
- Entity query `SELECT o` thường cần nhiều fields hơn DTO.
- DDL INCLUDE không portable sang mọi database.

**Projection nhỏ và covering index có thể bổ trợ nhau**, nhưng phải đo actual plan.

## 38. `SELECT entity` và `SELECT DTO` tạo nhu cầu index khác

Entity query:

```java
"SELECT o FROM PurchaseOrder o WHERE o.tenantId = :t"
```

thường phải đọc các basic mapped columns và hydrate managed entity. DTO:

```java
"SELECT new com.example.api.OrderSummary(" +
"o.id, o.createdAt, o.totalAmount) " +
"FROM PurchaseOrder o WHERE o.tenantId = :t"
```

có thể chỉ cần một số cột và không đăng ký managed entities vào persistence context. Tùy workload, điều này giảm network, heap và dirty checking.

Tuy nhiên DTO không có JPA lifecycle/dirty checking để cập nhật. Khi cần ghi, dùng domain service với managed entity hoặc bulk DML được thiết kế concurrency policy.

---

## 39. Xem execution plan trước khi tạo index

PostgreSQL SELECT ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = 7
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Quan sát:

- Seq Scan, Index Scan, Index Only Scan hay Bitmap Heap Scan?
- Index Cond và Filter khác nhau như thế nào?
- Estimated rows vs actual rows?
- Sort node, sort method, disk spill?
- Buffers hit/read?
- Heap Fetches trong Index Only Scan?
- Join strategy và loops?
- Time của child nodes?
- Có scan quá nhiều rows so với 20 rows trả về?
- Lock waits có nằm ngoài query plan không?

Không chỉ nhìn chữ `Index Scan` rồi kết luận query nhanh. Một index scan đọc hàng triệu entries vẫn có thể tốn kém.

## 40. Phân biệt `Index Cond` với `Filter`

Một plan minh họa:

```text
Index Scan using idx_orders_tenant_created
  Index Cond: (tenant_id = 7)
  Filter: (status = 'PAID')
```

Nó có thể duyệt một dải tenant rồi lọc status. Một candidate khác:

```text
Index Scan using idx_orders_tenant_status_date
  Index Cond: ((tenant_id = 7) AND (status = 'PAID'))
```

có thể thu hẹp scan tốt hơn.

Nhưng cần xem **Rows Removed by Filter**, buffer reads và execution time. Một predicate nằm ở Filter không tự chứng minh plan sai; có thể index khác tốn tổng chi phí lớn hơn.

## 41. Estimated rows sai lệch và statistics

Nếu plan báo:

```text
Estimated rows = 100
Actual rows    = 800000
```

optimizer đánh giá sai cardinality. Có thể vì:

- Statistics cũ.
- Data skew theo tenant.
- Correlation giữa tenant và status.
- Expressions không có statistics.
- Prepared/generic plan.
- Query pattern rất khác phổ biến.
- Sampling/histogram giới hạn.

Cân nhắc cập nhật statistics (PostgreSQL `ANALYZE`), extended statistics ở engine hỗ trợ, query rewrite hoặc index/partition strategy. Không ép index một cách mù quáng nếu estimates còn sai.

## 42. Seq Scan đôi khi là lựa chọn đúng

Nếu 90% rows là PAID:

```sql
SELECT *
FROM purchase_orders
WHERE status = 'PAID';
```

table scan có thể nhanh hơn nhiều random index-to-heap lookups. Với bảng nhỏ, sequential scan cũng có thể rẻ hơn index startup.

Đừng biến mục tiêu performance thành “100% queries có Index Scan”. Mục tiêu là **độ trễ và tài nguyên tổng thể** dưới workload thật.

## 43. `EXPLAIN ANALYZE` không phải lệnh chỉ đọc tuyệt đối

Trên PostgreSQL, `EXPLAIN ANALYZE` **thực thi statement**. Với SELECT thường dùng được khi kiểm soát tải, nhưng với UPDATE/DELETE/INSERT có thể gây thay đổi dữ liệu thật.

Không chạy:

```sql
EXPLAIN ANALYZE DELETE FROM purchase_orders ...;
```

trên production mà không hiểu tác dụng thực thi. Dùng môi trường test/staging hoặc công cụ/transaction được phê duyệt; ngay cả rollback có thể không hoàn tác external side effects hoặc sequence increments như mong đợi.

---

## 44. Ví dụ hoàn chỉnh: list Paid Orders của tenant

DTO:

```java
public record OrderSummary(
    Long id,
    Instant createdAt,
    OrderStatus status,
    BigDecimal totalAmount
) {}
```

JPQL:

```java
String jpql =
    "SELECT new com.example.api.OrderSummary(" +
    "o.id, o.createdAt, o.status, o.totalAmount" +
    ") FROM PurchaseOrder o " +
    "WHERE o.tenantId = :tenantId " +
    "AND o.status = :status " +
    "AND o.deletedAt IS NULL " +
    "ORDER BY o.createdAt DESC, o.id DESC";

List<OrderSummary> page = em.createQuery(
    jpql, OrderSummary.class
).setParameter("tenantId", tenantId)
 .setParameter("status", OrderStatus.PAID)
 .setMaxResults(20)
 .getResultList();
```

Index PostgreSQL candidate:

```sql
CREATE INDEX idx_active_orders_tenant_paid_list
ON purchase_orders(
    tenant_id,
    status,
    created_at DESC,
    id DESC
)
INCLUDE (total_amount)
WHERE deleted_at IS NULL;
```

Tại sao?

- Tenant equality.
- Status equality.
- Partial predicate khớp active-only query.
- Sort khớp createdAt/id.
- INCLUDE cover totalAmount cho projection.

Nhưng **đây chỉ là candidate**. Nếu 99,9% Orders active, partial lợi ít; nếu provider thêm JOIN khác, SQL plan khác; nếu visibility map không phù hợp, index-only không được bảo đảm. Đo cùng dataset, parameters và traffic thực tế.

## 45. Khi endpoint không lọc status

Query variant:

```java
"WHERE o.tenantId = :tenantId " +
"AND o.deletedAt IS NULL " +
"ORDER BY o.createdAt DESC, o.id DESC"
```

Index status-list có cột status ở giữa nên có thể không thuận lợi cho sort toàn tenant.

Candidate khác:

```sql
CREATE INDEX idx_active_orders_tenant_date
ON purchase_orders(
    tenant_id,
    created_at DESC,
    id DESC
)
WHERE deleted_at IS NULL;
```

Có nên giữ cả hai? Phải cân nhắc:

- Tần suất hai endpoints.
- Độ trễ so với SLA.
- Dung lượng indexes.
- Tỷ lệ INSERT/UPDATE.
- Indexes hiện có và duplicate prefixes.
- Query có cần một generic-plan biến thể không.

Không tạo index cho mọi combination khi chỉ một số patterns thật sự nóng.

## 46. Tìm Customer bằng email rồi lấy Orders

JPQL:

```java
String jpql =
    "SELECT new com.example.api.CustomerOrderView(" +
    "o.id, o.createdAt, c.displayName) " +
    "FROM PurchaseOrder o JOIN o.customer c " +
    "WHERE o.tenantId = :tenantId " +
    "AND c.tenantId = :tenantId " +
    "AND LOWER(c.email) = :email " +
    "ORDER BY o.createdAt DESC, o.id DESC";
```

Candidates:

```sql
CREATE INDEX idx_customer_email_tenant
ON customers(tenant_id, LOWER(email));

CREATE INDEX idx_order_customer_date
ON purchase_orders(customer_id, created_at DESC, id DESC);
```

Cần kiểm tra:

- Email có unique trong tenant?
- DB có dùng expression index không?
- Join order bắt đầu từ Customer hay Order?
- Tenant filter có được áp đúng cả hai bảng?
- Một Customer có bao nhiêu Orders?
- SQL có thêm soft-delete filter không?
- Có cần `LEFT JOIN` theo nghiệp vụ?
- Result là DTO hay managed graph?

Không coi JPQL constructor expression là giải pháp tự động cho một database join plan kém.

## 47. Index cho range tổng tiền

JPQL:

```java
"WHERE o.tenantId = :tenantId " +
"AND o.totalAmount >= :min " +
"ORDER BY o.totalAmount DESC, o.id DESC"
```

Index candidate:

```sql
CREATE INDEX idx_order_tenant_amount_id
ON purchase_orders(
    tenant_id, total_amount DESC, id DESC
);
```

Nó khác với index tenant/status/date. Một B-tree key order không thể đồng thời tối ưu mọi loại ORDER BY trên mọi cột.

Nếu có hai range conditions (date và amount), phải cân nhắc range nào selective/có sort quan trọng hơn, index combinations hoặc rewrite query. Không lạm dụng composite index với 15 cột để bao mọi filter của UI.

## 48. Index cho aggregate/count query

Sai mục đích:

```java
long count = em.createQuery(
    "SELECT o FROM PurchaseOrder o " +
    "WHERE o.tenantId = :tenantId",
    PurchaseOrder.class
).setParameter("tenantId", tenantId)
 .getResultList()
 .size();
```

Tốt hơn:

```java
Long count = em.createQuery(
    "SELECT COUNT(o) FROM PurchaseOrder o " +
    "WHERE o.tenantId = :tenantId " +
    "AND o.status = :status",
    Long.class
).setParameter("tenantId", tenantId)
 .setParameter("status", OrderStatus.PAID)
 .getSingleResult();
```

Composite index prefix `(tenant_id, status)` có thể giúp đếm. Nhưng một COUNT trên hàng triệu rows vẫn có chi phí, tùy DB MVCC/visibility/index-only scan.

Không hydrate hàng triệu Orders chỉ để tính COUNT/SUM nếu database có thể tính aggregate trực tiếp.

---

## 49. `@Table(indexes=...)` có nghĩa gì?

JPA hỗ trợ metadata:

```java
@Entity
@Table(
    name = "purchase_orders",
    indexes = @Index(
        name = "idx_orders_tenant_status_created",
        columnList = "tenant_id, status, created_at"
    )
)
public class PurchaseOrder {
    // ...
}
```

Nhưng:

- `columnList` dùng tên SQL columns.
- Metadata có thể được DDL generation dùng, không tự sửa schema production.
- Standard annotation không diễn đạt được mọi PostgreSQL partial/expression/INCLUDE indexes.
- Index sort directions và dialect capabilities cần kiểm tra.
- Nếu schema quản lý bằng Flyway/Liquibase, migration mới là nguồn deploy.
- Index có thể trùng PK/UNIQUE indexes đã có.

**Đừng nhầm annotation trên entity với một index đã được triển khai và dùng trong production.**

## 50. Migration và online index creation

Một migration PostgreSQL:

```sql
CREATE INDEX idx_orders_tenant_status_date
ON purchase_orders(
    tenant_id, status, created_at DESC, id DESC
);
```

Trên bảng lớn cần tính:

- Thời gian build.
- Locking/online DDL semantics.
- CPU/I/O pressure.
- Replication/WAL.
- Disk space.
- Failure/retry/cleanup plan.
- Query planner statistics.
- Rolling deployments.

PostgreSQL có `CREATE INDEX CONCURRENTLY` nhưng **không chạy bên trong transaction block thông thường**; công cụ migration phải cấu hình riêng khi dùng nó. SQL Server/MySQL có online DDL options khác và những giới hạn riêng.

Không deploy một index lớn vào giờ cao điểm chỉ vì môi trường test tạo index tức thì.

## 51. Chỉ mục có chi phí ghi và lưu trữ

Mỗi index thêm làm database phải bảo trì khi:

- INSERT Order.
- DELETE Order.
- UPDATE indexed columns.
- Cập nhật trạng thái/soft-delete.
- Vacuum/maintenance và replication.
- Page split/fragmentation theo engine.

Một index giúp report hiếm dùng giảm 20 ms nhưng làm write path tốn thêm IO đáng kể có thể không đáng giữ.

Đo cả:

- Query latency và tần suất reads.
- INSERT/UPDATE throughput/latency.
- Index size.
- Buffer cache hit ratios.
- Maintenance cost.
- Effects lên concurrent workloads.

**Index tuning là tối ưu tổng thể, không phải thêm càng nhiều càng tốt.**

## 52. Chỉ mục trùng/lồng nhau

Ví dụ:

```sql
CREATE INDEX idx_a ON purchase_orders(tenant_id);
CREATE INDEX idx_b ON purchase_orders(tenant_id, status);
CREATE INDEX idx_c ON purchase_orders(
    tenant_id, status, created_at DESC
);
```

Index c có prefix của a/b nên có thể phục vụ một số queries tương tự. Nhưng không khẳng định a/b luôn dư thừa: index hẹp có thể nhỏ hơn, query frequency khác, PK/unique semantics hoặc engine khác.

Trước khi drop:

1. Xem usage metrics/actual plans.
2. Đo SELECT hot paths.
3. Kiểm tra integrity indexes, FK support.
4. Đo storage/write savings.
5. Theo dõi regression sau rollout.

Đặc biệt đừng drop UNIQUE constraint chỉ vì một nonunique composite index có cùng prefix.

## 53. Kiểm tra indexes thực trong PostgreSQL

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'purchase_orders'
ORDER BY indexname;
```

Kiểm tra index có:

- Đúng schema/table.
- Key order.
- ASC/DESC và collation.
- INCLUDE columns.
- Partial predicate.
- Unique flag.
- State hợp lệ.
- Không quá nhiều redundant indexes.

Đây là PostgreSQL-specific catalog view; database khác có system catalogs tương ứng.

---

## 54. Benchmark trước và sau tạo index

Trước thay đổi, chạy SELECT phù hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total_amount
FROM purchase_orders
WHERE tenant_id = 7
  AND status = 'PAID'
  AND deleted_at IS NULL
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Ghi:

- Planning/execution time.
- Actual/estimated rows.
- Index/table scan type.
- Buffers hit/read.
- Sort method/memory spill.
- Row width và rows removed by filter.
- Query parameters và dataset size.

Sau index migration, đo **cùng SQL, cùng parameters và trạng thái dữ liệu tương đương**. Không kết luận từ một lần chạy, vì warm cache, JIT, background DB activity và concurrency gây nhiễu.

## 55. Benchmark nhiều tenants và filter combinations

Data setup nên có:

- Tenant nhỏ/vừa/lớn.
- PAID phổ biến hoặc hiếm.
- Date range hẹp/rộng.
- Page 1 và page sâu.
- Customer có rất ít/nhiều Orders.
- Soft-deleted data theo tỷ lệ thực.
- Cột JSON/text lớn nếu entity có.
- Rows có createdAt trùng.
- Dataset đủ lớn để optimizer không chọn bảng nhỏ hoàn toàn khác production.

So sánh cả cold/warm cache khi cần, và giữ phiên bản DB/driver/indexes đồng nhất.

## 56. Kiểm thử correctness sau rewrite JPQL

Khi thay query để dùng index tốt hơn, vẫn cần giữ:

- Tenant scope.
- Authorization.
- Soft-delete.
- Đúng status.
- Đúng timezone/time boundaries.
- No duplicates/missing roots khi JOIN.
- Sort ổn định.
- Pagination semantics.
- Null behavior.
- Concurrent update consistency.

Một query có thể chạy nhanh hơn nhưng **trả sai tenant data** nếu developer bỏ điều kiện tenant. Không bao giờ đánh đổi correctness/security lấy hiệu năng.

## 57. Integration test result ordering

Ví dụ pseudocode JUnit:

```java
@Test
void pageHasStableOrderAndCorrectTenant() {
    seedTwoTenantsAndDuplicateTimestamps();

    List<OrderSummary> page =
        service.listPaidOrders(7L, 20);

    assertEquals(expectedIds, page.stream()
        .map(OrderSummary::id)
        .toList());

    // Kiểm tra expectedIds đều thuộc tenant 7
    // và không chứa soft-deleted orders.
}
```

Fixtures/helpers cần được triển khai theo codebase thật. Mục đích test là chứng minh JPQL rewriting không thay business behavior.

## 58. Có nên assert plan chứa tên index?

Test:

```text
EXPLAIN ... → Index Scan using idx_xyz
```

có thể flaky nếu:

- Dataset nhỏ.
- DB statistics thay đổi.
- Version optimizer thay đổi.
- Cache/parameters khác.
- Seq Scan thực tế rẻ hơn.
- Query planner chọn index khác hợp lệ.

Các lớp test nên tách:

1. Functional integration test: bắt buộc đúng dữ liệu.
2. SQL count/fetch-plan test: phát hiện N+1.
3. Schema migration test: index thật tồn tại.
4. Performance benchmark: latency/buffers/rows trên dữ liệu đại diện.
5. Plan monitoring: phát hiện thay đổi đáng nghi, không nhất thiết fail vì thay đổi plan text.

Không biến mong muốn “phải dùng index X” thành tiêu chí duy nhất cho hiệu năng.

## 59. SQL count growth test phân biệt N+1 và index

Seed:

```text
1 Order + 1 Customer       → 2 SQL
10 Orders + 10 Customers  → 11 SQL
30 Orders + 30 Customers  → 31 SQL
```

Đây là dấu hiệu N+1 khi không bị cache nhiễu.

Nếu sau DTO projection:

```text
1 Order    → 1 SQL
10 Orders  → 1 SQL
30 Orders  → 1 SQL
```

là tín hiệu fetch plan đã cải thiện. Nhưng cần đo thêm rows, bytes, latency và heap; một SQL JOIN khổng lồ có thể tệ hơn nhiều SQL nhỏ.

Test SQL count không thay thế actual execution plan cho việc chọn index.

---

## 60. Các lỗi thực hành thường gặp

### Lỗi 1: Tạo index cho mọi field có trong `WHERE`

Không xét composite order, query patterns và write overhead.

### Lỗi 2: Tưởng ba single-column indexes luôn bằng một composite index

Không đúng trong nhiều access patterns, nhất là equality + sort.

### Lỗi 3: Dựa vào thứ tự predicates trong JPQL để quyết định index

DB optimizer không vận hành đơn giản theo thứ tự văn bản.

### Lỗi 4: Index cột status ít giá trị rồi mặc định nhanh

Low selectivity có thể khiến scan rẻ hơn.

### Lỗi 5: Bỏ qua tenant data skew

Một plan tốt cho tenant nhỏ có thể rất kém cho tenant lớn.

### Lỗi 6: `LOWER`/`DATE`/`CAST` trên indexed column nhưng không xem plan

Functions/casts có thể làm raw index kém hiệu quả.

### Lỗi 7: Dùng B-tree cho contains search `LIKE '%x%'`

Cần giải pháp search phù hợp engine.

### Lỗi 8: Dùng OR-optional query cho mọi tình huống mà không benchmark

Query variants có thể có plans khác; dynamic predicates đáng cân nhắc.

### Lỗi 9: Bỏ tie-breaker trong pagination

Rows có cùng timestamp có thể không có thứ tự ổn định.

### Lỗi 10: Chỉ thêm index để chữa deep OFFSET

Offset vẫn có chi phí bỏ qua rows; xem keyset khi phù hợp.

### Lỗi 11: Cho rằng index status + date luôn tối ưu query không lọc status

Cột status ở giữa có thể cản trở sort toàn tenant.

### Lỗi 12: Cho rằng FK tự có index child

Không phải mọi RDBMS tự tạo child index.

### Lỗi 13: Cho rằng `JOIN FETCH` tương đương index optimization

Fetch plan và index giải quyết khác tầng.

### Lỗi 14: Cho rằng DISTINCT xóa Cartesian explosion

Database vẫn có thể tạo/xử lý joined rows lặp.

### Lỗi 15: Tối ưu một SELECT nhưng để N+1 từ serializer

Cần đo toàn request, kể cả mapper/JSON.

### Lỗi 16: Covering index luôn bảo đảm index-only scan

Tùy DB visibility/cost, có thể vẫn cần table fetch.

### Lỗi 17: Có `@Index` trong Java nghĩa production có index

Schema thật phụ thuộc migration.

### Lỗi 18: Thêm index trùng unique constraint

Tăng maintenance mà có thể không thêm ích lợi.

### Lỗi 19: Một Seq Scan đồng nghĩa planner sai

Có thể là plan tối ưu cho bảng nhỏ/low selectivity.

### Lỗi 20: Một Index Scan đồng nghĩa query nhanh

Có thể quét hàng triệu index entries.

### Lỗi 21: Chạy EXPLAIN ANALYZE DML vô ý

Nó thực thi statement, có thể thay đổi dữ liệu.

### Lỗi 22: Benchmark chỉ 100 rows

Không phản ánh 10 triệu rows trong production.

### Lỗi 23: Benchmark chỉ một tenant/filter value

Không bao phủ selectivity/data skew.

### Lỗi 24: Bỏ kiểm thử write workload sau index mới

INSERT/UPDATE/DELETE có thể chậm hơn.

### Lỗi 25: Bỏ tenant filter để index dễ dùng

Có thể tạo lỗi bảo mật nghiêm trọng.

---

## 61. Bài tập 1 — Composite index

JPQL:

```java
"WHERE o.tenantId = :t AND o.status = :s " +
"ORDER BY o.createdAt DESC, o.id DESC"
```

**Gợi ý:** Candidate `(tenant_id, status, created_at DESC, id DESC)`. Đo plan với dữ liệu tenant/status đại diện.

## 62. Bài tập 2 — Không lọc status

JPQL:

```java
"WHERE o.tenantId = :t " +
"ORDER BY o.createdAt DESC"
```

**Đáp án:** Index có `status` ở giữa không nhất thiết tốt. Xem `(tenant_id, created_at DESC, id DESC)`.

## 63. Bài tập 3 — Ngày

JPQL dùng `FUNCTION('date', createdAt) = :day`.

**Đáp án:** Thử half-open range với `>= :start AND < :end` và index raw timestamp; tính timezone đúng.

## 64. Bài tập 4 — Mã đơn unique

Rule: orderNo duy nhất theo tenant.

**Đáp án:** DB UNIQUE(tenant_id, order_no), đồng thời là index exact lookup nếu engine hỗ trợ như thường thấy.

## 65. Bài tập 5 — LIKE contains

`name LIKE '%book%'` trên bảng rất lớn.

**Đáp án:** Raw B-tree thường không giải hiệu quả; cân nhắc full-text/trigram/search index DB-specific.

## 66. Bài tập 6 — LOWER email

JPQL so sánh `LOWER(c.email) = :email`.

**Đáp án:** Xem expression index hoặc normalized column/collation và bảo đảm canonicalization policy phù hợp.

## 67. Bài tập 7 — IN nhiều trạng thái

Query `status IN ('PAID','SHIPPED') ORDER BY createdAt DESC`.

**Đáp án:** Index `(status, created_at)` có thể cần merge/sort across groups; test plan với real distributions.

## 68. Bài tập 8 — FK child

OrderLines có FK order_id nhưng thiếu index.

**Đáp án:** Xem index `order_lines(order_id)` nếu thường tìm lines theo order; FK không tự đảm bảo index child trên mọi DB.

## 69. Bài tập 9 — N+1

20 Orders dẫn đến 20 Customer SELECT.

**Đáp án:** Đây là fetch-plan issue; DTO JOIN Customer hoặc fetch join/batch fetching, không chỉ tạo thêm Order index.

## 70. Bài tập 10 — Collection join

Một Order 12 Lines và 10 Events; JOIN FETCH cả hai.

**Đáp án:** Có nguy cơ 120 joined rows/Order. Index không tự giải row multiplication.

## 71. Bài tập 11 — Soft delete

99% queries có `deletedAt IS NULL`, 70% rows đã soft-deleted.

**Đáp án:** Partial index `WHERE deleted_at IS NULL` đáng thử trên DB hỗ trợ; cần đo plan/size/write overhead.

## 72. Bài tập 12 — Covering

Endpoint chỉ cần id, createdAt, totalAmount.

**Đáp án:** Index keys cho predicates/sort với INCLUDE totalAmount có thể tạo cơ hội index-only scan trên PostgreSQL, không bảo đảm.

## 73. Bài tập 13 — Status low selectivity

80% records PAID.

**Đáp án:** Index đơn status không chắc hữu ích; composite tenant/status/sort/limit có thể tốt hơn.

## 74. Bài tập 14 — Deep OFFSET

Page 5.000 bị chậm dù index đúng sort.

**Đáp án:** Keyset pagination có thể giảm chi phí skip, nếu use case cần duyệt tuần tự.

## 75. Bài tập 15 — Index Cond vs Filter

Plan có `Index Cond tenant_id=?` nhưng status ở Filter và loại rất nhiều rows.

**Đáp án:** Cân nhắc composite index tenant/status trước date; so actual buffers/time.

## 76. Bài tập 16 — Seq Scan

Có index nhưng query lấy 90% bảng và optimizer chọn Seq Scan.

**Đáp án:** Có thể hợp lý; đo execution time và total cost, không ép dùng index chỉ vì nó tồn tại.

## 77. Bài tập 17 — Data skew

Tenant nhỏ query 5 ms, tenant lớn 800 ms.

**Đáp án:** Xem per-tenant distributions, statistics, plan caching, index và sort/limit, test workload lớn.

## 78. Bài tập 18 — Migration

Java có `@Table(indexes=...)` nhưng DB production không có index.

**Đáp án:** Cần migration, schema verification và deploy plan. Annotation tự nó không tạo index trên DB đã triển khai.

## 79. Bài tập 19 — Redundant index

Có UNIQUE(tenant_id, order_no), định thêm INDEX(tenant_id, order_no).

**Đáp án:** Thường dư thừa; không thêm nếu chưa chứng minh lợi ích khác biệt.

## 80. Bài tập 20 — Safe EXPLAIN

Developer chạy `EXPLAIN ANALYZE DELETE ...` trên production.

**Đáp án:** Nguy hiểm vì thực thi DML; chỉ dùng môi trường/quy trình có kiểm soát.

## 81. Bài tập 21 — Tính đúng sau rewrite

Query nhanh hơn sau khi bỏ tenant predicate.

**Đáp án:** Không chấp nhận; phá isolation/security. Tối ưu phải giữ kết quả và quyền truy cập đúng.

## 82. Bài tập 22 — Performance test

Plan đổi từ Index Scan sang Seq Scan sau nâng cấp DB nhưng latency tốt hơn.

**Đáp án:** Không mặc định regression; đánh giá latency/buffers/actual data thay vì assert plan text cứng.

## 83. Bài tập 23 — Chi phí ghi

Một index mới cải thiện report hiếm dùng nhưng làm UPDATE cực thường xuyên chậm đáng kể.

**Đáp án:** Cân nhắc workload tổng, partial/narrow index, reporting replica/materialized view hoặc bỏ index.

## 84. Bài tập 24 — Two-phase fetch

Pagination root Orders rồi JOIN FETCH Lines theo IDs.

**Đáp án:** Cần giữ thứ tự IDs ban đầu (IN không bảo đảm order), handle list rỗng, kiểm tra transaction consistency và data cardinality.

## 85. Bài tập 25 — Tổng hợp

List 20 Orders PAID mới nhất trong tenant, chỉ cần id, date, Customer name, total; đang có N+1 Customers và SQL gốc sort nhiều rows.

**Gợi ý:** Viết DTO projection JOIN Customer, filter tenant/status/soft-delete, order theo date/id, cân nhắc index `orders(tenant_id,status,created_at DESC,id DESC)` và index phía Customer nếu cần; đo SQL count, actual plans, rows/bytes, heap và P95. Không fetch toàn Lines nếu không cần.

---

## 86. Checklist thiết kế index cho JPQL

Trước khi quyết định tạo hoặc giữ một index:

1. Đã xác định endpoint/query nóng và input thực chưa?
2. Có baseline P50/P95/P99 và tần suất không?
3. Đã phân biệt database bottleneck với N+1 và hydration chưa?
4. Có SQL generated thực tế không?
5. Có biết bind types và parameters đại diện không?
6. Có tenant/soft-delete/filter khác được thêm tự động không?
7. Có phân biệt Java property names với SQL column names không?
8. Đã xem actual execution plan chưa?
9. Có biết estimated/actual rows và buffer reads không?
10. Có biết query đang sort/spill/lock wait không?
11. Predicate nào là equality?
12. Predicate nào là range?
13. Có IN list nhiều values không?
14. Có optional OR predicates không?
15. Có function/cast trên indexed column không?
16. LIKE là prefix hay contains?
17. Có NULL/soft-delete predicates không?
18. Tenant/status data có skew không?
19. Có ORDER BY với tie-breaker ổn định không?
20. OFFSET có quá sâu không?
21. Composite index key order có khớp prefix và sort không?
22. Có existing PK/UNIQUE/index trùng không?
23. Các FK child columns có cần index không?
24. Query JOIN có index ở phía selective không?
25. Có N+1 cần sửa fetch plan không?
26. Có row multiplication khi JOIN FETCH collections không?
27. Có thể thay entity query bằng DTO projection không?
28. Covering/index-only có thật sự hữu ích không?
29. Partial/expression index có được DB hỗ trợ không?
30. Partial predicate có khớp SQL thật không?
31. Collation/timezone/Unicode rules có đúng không?
32. Có prepared/generic-plan issues không?
33. Benchmark có tenant nhỏ/vừa/lớn không?
34. Có test date range hẹp/rộng và các statuses không?
35. Dataset/index/statistics có production-like không?
36. Có đo cold/warm cache không?
37. Có tính chi phí INSERT/UPDATE/DELETE không?
38. Có tính disk/maintenance/replication cost không?
39. Index có trong migration được quản lý không?
40. Có kế hoạch online creation/lock/rollback không?
41. Có xác minh index thật trong DB catalog không?
42. Có test tenant scope/authorization không?
43. Có test sort/paging/NULL semantics không?
44. Có tách benchmark khỏi test plan text quá cứng không?
45. Có đo lại end-to-end API latency sau index change không?

Checklist nhằm giúp nhóm kỹ thuật lựa chọn **ít index nhưng có tác dụng rõ ràng**, không phải tạo một index cho mỗi dòng điều kiện JPQL.

## Kết luận

**Kết hợp chỉ mục database với JPQL hiệu quả bắt đầu từ SQL thực thi và workload thật, không bắt đầu từ annotation hay tên property.**

Các điểm cốt lõi:

- Thu generated SQL, bind types, actual execution plan và row counts trước khi quyết định index.
- Với B-tree composite, equality prefix trước range/sort thường là candidate tốt; cần xem thêm variants không có một predicate, dữ liệu skew và cách optimizer hoạt động.
- Điều kiện `IN`, `IS NULL`, `LIKE`, functions `LOWER/DATE`, ORDER BY và pagination thay đổi khả năng dùng index.
- Rewrite timestamp filter thành half-open range có thể vừa đúng biên thời gian vừa thuận lợi cho index.
- Unique index phục vụ integrity và lookup; partial/expression/covering index phục vụ những use cases cụ thể, có tính phụ thuộc RDBMS.
- Index trên FK và JOIN cần xét cả hai phía của plan; N+1 và Cartesian explosion là **vấn đề fetch plan**, không thể chữa chỉ bằng index.
- `@Table(indexes=...)` là mapping metadata, không chứng minh production schema đã có index; cần migration và catalog verification.
- Một index có thể cải thiện đọc nhưng tăng chi phí ghi, storage và maintenance; phải benchmark tổng thể.
- Tối ưu query không được làm thay đổi kết quả, tenant isolation, transaction semantics hoặc pagination correctness.

Quy trình nên nhớ là: **JPQL → SQL thật → predicates và actual plan → candidate index → benchmark trước/sau → kiểm thử correctness → migration có kiểm soát**. Khi đi theo quy trình đó, chỉ mục trở thành một công cụ tối ưu có căn cứ thay vì một tập hợp cấu hình được thêm theo cảm giác.

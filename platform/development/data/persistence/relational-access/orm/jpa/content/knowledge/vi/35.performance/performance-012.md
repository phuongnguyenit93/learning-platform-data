# Đo trên dữ liệu và hệ quản trị đại diện cho môi trường triển khai trong JPA

Một truy vấn JPA chạy rất nhanh trên laptop với 200 bản ghi **không đủ chứng minh** nó sẽ nhanh khi triển khai lên hệ thống có hàng triệu đơn hàng, nhiều tenant, hàng chục kết nối đồng thời và một cơ sở dữ liệu khác loại. Tối ưu hiệu năng không chỉ là đổi `LAZY` thành `JOIN FETCH`, thêm `@BatchSize` hoặc nhìn vào thời gian một lần gọi repository. Cần đo trên một tổ hợp **dữ liệu – schema – hệ quản trị – hạ tầng – tải truy cập** đủ đại diện cho nơi ứng dụng sẽ vận hành.

Ví dụ, một query JPQL:

```java
List<SalesOrder> orders = em.createQuery(
    """
    select o
    from SalesOrder o
    where o.tenantId = :tenant
      and o.status = :status
    order by o.createdAt desc, o.id desc
    """,
    SalesOrder.class
)
.setParameter("tenant", authorizedTenant)
.setParameter("status", OrderStatus.PAID)
.setMaxResults(50)
.getResultList();
```

Trên database test có 100 Orders và không có index, nó có thể trả kết quả trong vài milliseconds. Trên PostgreSQL production với 10 triệu Orders, hàng triệu rows thuộc một tenant “nóng”, nhiều rows cùng trạng thái PAID, collations khác, bảng đã cập nhật/xóa lâu ngày và hàng trăm requests đồng thời, thời gian có thể tăng đáng kể. Ngược lại, **một query dùng sequential scan trên bảng rất nhỏ không nhất thiết là “chậm”**: tạo index chỉ vì thấy `Seq Scan` có thể khiến writes tốn hơn mà reads không nhanh lên.

Muốn ra quyết định kỹ thuật đáng tin cậy, phải trả lời:

1. **Đang đo cái gì?** Một SELECT, một endpoint có mapping DTO, hay cả transaction tạo Order?
2. **Dữ liệu có giống quy mô và phân phối thật không?** Số rows, số child/parent, tenant skew, tỷ lệ NULL, tần suất UPDATE/DELETE?
3. **Hệ quản trị có giống môi trường đích không?** Engine, major version, dialect, extensions, indexes, thống kê optimizer, isolation và cấu hình?
4. **Có đo đúng điều kiện vận hành không?** Cold/warm cache, connection pool, network latency, concurrency, background jobs?
5. **Kết quả có lặp lại được không?** Seed data cố định, cùng queries/parameters, warmup, baseline, monitoring và báo cáo sai số?
6. **Có kiểm tra correctness không?** Truy vấn nhanh nhưng bỏ thiếu rows, sai thứ tự trang hoặc lộ dữ liệu tenant khác không phải tối ưu thành công.

> **Nguyên tắc:** Một benchmark JPA có giá trị khi phản ánh đủ gần **workload production**, đồng thời giữ được **khả năng lặp lại và so sánh nguyên nhân**. Hệ quản trị giống production nhưng dữ liệu quá nhỏ vẫn sai; dữ liệu lớn nhưng engine khác hoàn toàn cũng có thể dẫn đến kết luận sai.

Bài học thuộc chương **Hiệu năng** của module *Data Persistence Relational Access ORM JPA*. Nội dung tập trung thiết kế phép đo có cơ sở, không phải chạy benchmark production nguy hiểm hoặc chạy một lệnh có số đẹp.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt benchmark đơn lẻ, integration performance test, load test và production observability.
2. Xác định các chiều **đại diện**: database engine/version, schema, dữ liệu, tải, topology, cấu hình.
3. Giải thích vì sao H2/SQLite hoặc database rỗng không đủ để kết luận hiệu năng PostgreSQL/MySQL/Oracle/SQL Server.
4. Tạo bộ dữ liệu test có quy mô, phân phối, hot keys, tenants và quan hệ gần thực tế.
5. Dùng migrations và database statistics để phản ánh schema/query planner thật.
6. Đo latency p50/p95/p99, throughput, error rate, SQL count, pool wait, row count, CPU và memory.
7. Phân biệt cold cache, warm cache, L1/L2/query cache, database buffer cache và JIT warmup.
8. Xem `EXPLAIN`/`EXPLAIN ANALYZE` đúng cách; hiểu plan, estimates, actual rows và `BUFFERS`.
9. Dùng Testcontainers hoặc database môi trường thử nghiệm được chuẩn hóa để kiểm tra SQL/JPA behavior.
10. Đo N+1, collection fetch, projections, pagination, batch insert/update và transaction contention.
11. Thiết kế thí nghiệm A/B có baseline, biến kiểm soát, sample size và các lần đo lặp.
12. Viết performance regression tests có ngưỡng hợp lý, không phụ thuộc quá mức vào timings của CI.
13. Ghi nhận kết quả thành báo cáo có khả năng đưa ra quyết định và tái lập.
14. Không dùng dữ liệu cá nhân production không được phép để tạo benchmark.

## 2. “Đại diện cho môi trường triển khai” nghĩa là gì?

Tính đại diện không phải một con số. Có ít nhất **năm trục**:

| Trục | Cần phản ánh | Ví dụ sai lệch |
|---|---|---|
| **Database** | Engine, major version, dialect, extensions, collation, isolation, query planner settings | Test trên H2 rồi triển khai PostgreSQL |
| **Schema** | Tables, column types, indexes, FK/UNIQUE/CHECK, partitions, migrations | Test database tự tạo bảng nhưng production thiếu index |
| **Dữ liệu** | Số rows, phân phối khóa, tỷ lệ NULL, số children, tenant skew, dữ liệu lịch sử | Test chỉ có 3 Orders, mỗi Order 1 Line |
| **Workload** | Query mix, params, concurrency, hot endpoints, background jobs | Chỉ chạy một SELECT tuần tự |
| **Hạ tầng** | CPU/RAM, disk latency, IOPS, network RTT, pool size, replicas, resource contention | PostgreSQL cùng máy app, không có network và không có concurrent load |

Một phép đo không cần tái tạo từng byte của production. Nhưng phải **biết trục nào được giữ giống**, trục nào không, và **kết luận được phép suy ra tới đâu**.

### 2.1. Ví dụ hai phép đo không so sánh được

```text
Benchmark A:
  H2 in-memory
  1.000 orders
  1 HTTP thread
  JPA provider Hibernate
  all data cached

Benchmark B:
  PostgreSQL server
  10.000.000 orders
  100 HTTP threads
  10 DB connections
  network latency + background writes
```

Nếu A mất 3 ms còn B mất 45 ms, không thể kết luận “PostgreSQL chậm hơn H2 15 lần”. Hàng loạt biến đã thay đổi cùng lúc.

### 2.2. Tính đại diện phụ thuộc câu hỏi

Nếu bạn chỉ kiểm tra **JPQL có hợp lệ trên PostgreSQL hay không**, PostgreSQL Testcontainers với dữ liệu nhỏ có thể đủ. Nhưng nếu muốn kết luận **offset pagination trang thứ 100.000 có p95 nhỏ hơn 200 ms**, phải có dữ liệu lớn, indexes/planner statistics, hot/cold profiles và tải thích hợp.

### 2.3. Mục tiêu là quyết định đáng tin, không phải môi trường giống tuyệt đối

Một performance experiment hiệu quả cho biết: “trong workload tương ứng với trang tìm kiếm phổ biến, truy vấn DTO giảm p95 và database CPU mà không làm sai phân trang”. Nó không cần nhân bản toàn hệ thống thanh toán, nhưng cần giữ những yếu tố ảnh hưởng trực tiếp tới query.

---

## 3. Bốn cấp độ kiểm tra hiệu năng

| Cấp độ | Trọng tâm | Dùng khi |
|---|---|---|
| **Microbenchmark** | Một phép biến đổi nhỏ, code path/JVM behavior | Đo CPU cost của mapper/converter thuần Java |
| **JPA/database integration test** | Mappings, SQL, constraints, plans với DB mục tiêu | N+1, index, batch, pagination, dialect |
| **Load/soak test** | Tải đồng thời, latency percentiles, saturation, ổn định lâu dài | API hot path, pool sizing, GC, lock contention |
| **Production observability** | Thực tế người dùng, dữ liệu và hạ tầng đang chạy | Regression detection, ưu tiên tối ưu, sự cố |

### 3.1. Không dùng microbenchmark để kết luận transaction end-to-end

Đo một Java mapper bằng JMH là phù hợp để so sánh mapper implementations. Nhưng nó không đo TCP round-trips, SQL planner, pool wait, locks hay commit time. **JMH không tự biến database benchmark thành production workload**.

### 3.2. Không dùng load test để thay correctness test

Một endpoint có throughput cao vì bỏ qua tenant condition hoặc chỉ trả 10 trong 50 Orders là **sai nghiệp vụ**. Performance testing phải đi sau/đi cùng kiểm chứng dữ liệu và transaction behavior.

### 3.3. Không dùng chỉ production telemetry để điều tra nguyên nhân

Dashboard cho thấy p99 tăng nhưng không tự biết vì index thiếu, N+1 hay lock wait. Cần reproducible test để kiểm chứng giả thuyết.

### 3.4. Không copy dataset production vào laptop theo mặc định

Nếu có PII, secrets hoặc dữ liệu nhạy cảm, phải dùng sanitized/anonymized data theo chính sách hoặc synthetic dataset có cùng thống kê phân phối.

---

## 4. Đặt mục tiêu trước khi đo

Một câu hỏi mơ hồ:

> “OrderRepository chậm quá, tối ưu đi.”

Nên chuyển thành:

> “Với trang danh sách 50 Orders thuộc tenant hoạt động cao, PostgreSQL version tương ứng production, 40 concurrent users, tỷ lệ cache hit tương đương, endpoint phải trả đúng dữ liệu và có p95 dưới ngân sách đã thống nhất.”

### 4.1. Các loại mục tiêu

- **Latency:** p50/p95/p99 của GET /orders, tính tới response DTO đã được tạo.
- **Throughput:** số requests hoặc business operations hoàn tất mỗi giây.
- **Resource use:** database CPU, I/O, memory, network, connection pool wait.
- **Correctness:** số rows và tenant scope chính xác.
- **Stability:** latency/error rate không tăng không kiểm soát qua soak period.
- **Cost:** số DB connections, data transfer và hạ tầng cần cấp.

### 4.2. SLO và benchmark threshold là hai thứ khác

SLO là cam kết/chỉ tiêu dịch vụ ở vận hành thực tế. Ngưỡng test có thể là tín hiệu sớm trong môi trường thử nghiệm. Nếu test không có cùng load/topology, đừng khẳng định chỉ vì 50 ms ở CI thì production p95 cũng 50 ms.

### 4.3. Một mẫu hypothesis

```text
Giả thuyết:
  Thay Orders entity+lazy Customer bằng DTO projection
  sẽ giảm queries từ xấp xỉ 1+N xuống 1 query cho mỗi page.

Điều giữ cố định:
  PostgreSQL version, dataset snapshot, query filter,
  page size, pool size, concurrency, warmup procedure.

Đo:
  SELECT count, rows, p50/p95/p99 endpoint,
  database CPU và bytes transferred.

Điều kiện thành công:
  Cùng 50 Orders, cùng thứ tự/các giá trị;
  không lộ tenant khác;
  giảm round-trips và không tăng p95.
```

---

## 5. Dữ liệu đại diện: quy mô là cần nhưng chưa đủ

Một bộ dữ liệu chỉ có **nhiều rows** vẫn có thể không phản ánh production nếu phân phối khác.

Ví dụ:

```text
Production:
  8.000.000 Orders
  400.000 Customers
  32.000.000 OrderLines
  2.000 tenants
  10 tenants lớn chiếm 60% traffic
  20% Orders ở trạng thái NEW/PAID
  1% Orders có > 80 Lines

Synthetic test:
  8.000.000 Orders
  8.000.000 Customers (mỗi Order một Customer)
  8.000.000 OrderLines (mỗi Order một Line)
  đều nhau giữa 2.000 tenants
  50% PAID
```

Cùng 8 triệu Orders nhưng **join cardinality, index selectivity, cache reuse và skew hoàn toàn khác**.

### 5.1. Những thống kê nên thu thập trước khi seed

- Tổng số rows của từng bảng.
- Số rows theo tenant/status/time window.
- Number of distinct foreign keys.
- Percentiles số Lines/Order (p50, p95, max).
- Tỷ lệ NULL và blank/soft-deleted rows.
- Tỷ lệ dữ liệu mới vs lịch sử.
- Các giá trị đặc biệt hoặc “hot keys”.
- Tỷ lệ Update/Delete/Insert.
- Các combinations thường nằm trong WHERE filters.

### 5.2. Dataset nên có ít nhất ba tiers

| Tier | Mục tiêu | Ví dụ |
|---|---|---|
| Small deterministic | Test correctness nhanh | 100 Orders, có edge cases |
| Medium integration | Phát hiện N+1/query plan surprises | 100.000 Orders, 400.000 Lines |
| Representative perf | Đo scale/production-like workloads | Hàng triệu Orders theo statistics mục tiêu |

Con số chỉ là ví dụ. Một hệ thống nhỏ thật sự có thể không cần hàng triệu rows. **Representative** nghĩa là gần quy mô mà sản phẩm dự kiến phục vụ, không phải “cứ benchmark 10 triệu rows mới đúng”.

### 5.3. Có dữ liệu “xấu” nhưng hợp lệ

Không chỉ seed records đẹp:

- Name rất dài trong giới hạn.
- Customer có 0, 1, 50 hoặc 500 Orders.
- Order có 0 hoặc nhiều Lines theo domain rules.
- Nhiều Orders cùng timestamp.
- Một số foreign keys lặp lại tạo hot spots.
- Records cũ và mới xen kẽ.
- Soft-deleted rows nếu có.
- Tenant lớn vượt xa tenant trung bình.

Các edge cases này thay đổi plan, join result rows, sorting và cache behavior.

---

## 6. Phân phối dữ liệu ảnh hưởng query planner như thế nào?

Optimizer chọn kế hoạch dựa vào ước lượng:

- Có bao nhiêu rows thỏa `tenant_id = ?`?
- `status = PAID` chiếm bao nhiêu phần trăm?
- Index sẽ lọc được bao nhiêu rows?
- Join với OrderLine nhân rows bao nhiêu lần?
- Có cần sort lớn hoặc materialize không?

### 6.1. Uniform distribution dễ tạo kết luận sai

Nếu 1.000 tenants có số Orders bằng nhau, query `tenant_id = :id` có vẻ luôn lọc đúng 0,1% bảng. Nhưng production có tenant lớn chiếm 15% Orders, planner có thể chọn scan/join strategy khác cho tenant đó.

### 6.2. Correlated columns

`tenant_id` và `order_status` có thể tương quan mạnh: một tenant có 90% PAID, tenant khác 5% PAID. Không giả định xác suất hai predicates độc lập.

### 6.3. Time distribution

Dữ liệu thường tập trung vào thời gian gần đây, có mùa cao điểm, và retention policy. Test time window query với dữ liệu phân bố đều 10 năm có thể không giống một hệ thống có 80% traffic/records trong 90 ngày gần nhất.

### 6.4. Test nhiều parameter classes

Không chỉ `tenant='small-test'`. Nên chọn representative examples:

- Tenant nhỏ.
- Tenant trung bình.
- Tenant lớn.
- Status hiếm.
- Status phổ biến.
- Time range hẹp và rộng.
- Search term rất chọn lọc và rất phổ biến.
- Trang đầu và trang sâu.

### 6.5. Query plan parameter sensitivity

Prepared statements có thể được database cache/chọn generic/custom plans theo driver/config/DB. Một plan tốt cho tenant nhỏ không chắc tốt cho tenant lớn. Test với các nhóm parameters thay vì một key duy nhất.

---

## 7. Hệ quản trị đại diện: chọn gì để kiểm thử?

Giả sử production dùng PostgreSQL. Thứ tự ưu tiên thường:

1. PostgreSQL cùng major version và extensions tương ứng.
2. PostgreSQL gần cấu hình/dialect mục tiêu trên môi trường isolation.
3. PostgreSQL Testcontainers cho CI integration tests.
4. H2/HSQLDB chỉ dùng cho một số unit/smoke cases không phụ thuộc planner/dialect.
5. Mock `EntityManager` chỉ dùng khi kiểm tra service control flow, không phải SQL performance.

### 7.1. H2 không phải PostgreSQL thu nhỏ

H2 có optimizer, SQL type support, locking, indexing, collation, sequence và transaction semantics khác PostgreSQL. H2 compatibility mode có thể giúp cú pháp, **không biến nó thành PostgreSQL**.

### 7.2. Cùng engine nhưng version khác vẫn có rủi ro

Major upgrades có thể thay query planner behavior, indexing options, statistics handling, parallel execution và optimizer heuristics. Với một regression quan trọng, pin đúng version image/package tương ứng deployment.

### 7.3. Dialect cần đúng

Hibernate SQL dialect quyết định SQL được phát (pagination, functions, generated keys, locking). Đo Hibernate+H2 dialect rồi suy luận PostgreSQL execution plan không hợp lệ.

### 7.4. Extensions và collation

Nếu production dùng `pg_trgm`/full-text search, ICU collation hoặc custom operators, test không có chúng có thể tạo plan hoàn toàn khác.

### 7.5. SQLite/embedded DB vẫn có chỗ dùng

Phù hợp một số workflows local/offline hoặc dự án production thực sự dùng SQLite. Sai là dùng nó để đại diện một production database khác mà không nêu giới hạn.

---

## 8. Schema phải là bản có thể đối chiếu với production

Một bộ data đại diện trên schema sai vẫn đưa ra kết quả sai.

Kiểm tra:

- Column types và widths.
- Nullable/defaults/check constraints.
- PK/FK/UNIQUE constraints.
- Single-column và composite indexes.
- Partial/functional indexes.
- Partitioning và partition keys.
- Materialized views/triggers nếu query có liên quan.
- Generated columns.
- Tablespaces/storage settings khi quan trọng.
- Table statistics, index bloat và vacuum state khi có ảnh hưởng.

### 8.1. Migration là nguồn schema đáng tin

Thay vì để Hibernate `create-drop` tự tạo bảng khác production, chạy versioned migrations tương tự deployment:

```text
Fresh database
   |
   v
Flyway / Liquibase migrations
   |
   v
Seed representative dataset
   |
   v
ANALYZE / update planner statistics
   |
   v
Run integration/performance scenarios
```

### 8.2. `ddl-auto=validate` không thay migration

Hibernate `validate` có thể phát hiện một số schema mismatches nhưng không xác nhận tất cả index predicates, statistics, collation hay physical storage behavior.

### 8.3. Index phải khớp thực tế

Ví dụ:

```sql
CREATE INDEX idx_order_tenant_status_created
ON sales_order (
    tenant_id,
    order_status,
    created_at DESC,
    order_id DESC
);
```

Một index phù hợp query list có thể cải thiện sorting/filtering, nhưng cũng tăng cost của INSERT/UPDATE/DELETE. Đừng thêm index chỉ vì benchmark read-only một query đã nhanh hơn; đánh giá write mix.

### 8.4. Partial indexes cần đúng business predicates

Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_active_order_lookup
ON sales_order (tenant_id, created_at DESC)
WHERE deleted_at IS NULL;
```

Nếu query không có predicate tương ứng hoặc soft delete logic khác, index này có thể không được chọn. Đây là tính năng database-specific và cần migration.

---

## 9. Ví dụ mô hình JPA dùng trong phép đo

Entity Order:

```java
package com.example.shop.persistence;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.*;

@Entity
@Table(name = "sales_order")
public class SalesOrder {

    @Id
    @Column(name = "order_id")
    private Long id;

    @Column(name = "tenant_id", nullable = false)
    private String tenantId;

    @Enumerated(EnumType.STRING)
    @Column(name = "order_status", nullable = false)
    private OrderStatus status;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @Column(name = "total_amount", precision = 16, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    @Version
    @Column(name = "row_version", nullable = false)
    private Long version;

    protected SalesOrder() {}

    public Long getId() { return id; }
    public String getTenantId() { return tenantId; }
    public OrderStatus getStatus() { return status; }
    public Customer getCustomer() { return customer; }
    public Instant getCreatedAt() { return createdAt; }
    public BigDecimal getTotalAmount() { return totalAmount; }
    public List<OrderLine> getLines() { return lines; }
}
```

Customer và OrderLine:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @Column(name = "customer_id")
    private Long id;

    @Column(name = "customer_name")
    private String name;

    protected Customer() {}

    public String getName() { return name; }
}

@Entity
@Table(name = "order_line")
public class OrderLine {

    @Id
    @Column(name = "line_id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private SalesOrder order;

    @Column(name = "quantity", nullable = false)
    private int quantity;

    protected OrderLine() {}

    public int getQuantity() { return quantity; }
}
```

Enum:

```java
public enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
```

Đây là mô hình ví dụ phục vụ đọc/truy vấn; imports và repository/service class thực tế cần được tổ chức theo dự án. Việc data seeding dùng assigned IDs riêng giúp SQL dễ tái lập; production có thể dùng `@GeneratedValue` theo thiết kế khác.

---

## 10. Bộ dữ liệu synthetic có tính tái lập

Để so sánh baseline và candidate, dataset không nên thay ngẫu nhiên ở mỗi lần chạy.

### 10.1. Dùng seed cố định

Ví dụ pseudocode:

```text
randomSeed = 20261115

for orderId from 1 to 1_000_000:
    tenantId = sampleTenantFromSkewedDistribution()
    customerId = sampleCustomer()
    status = sampleStatusConditionalOnTenant()
    createdAt = sampleTimeDistribution()
    lineCount = sampleLinesPerOrder()
    write Order and lines
```

Các hàm sampling phải có specification/seed và log dataset version để có thể tái tạo chính xác.

### 10.2. Seed theo từng nhóm nghiệp vụ

Một dataset hữu ích có thể gồm:

| Nhóm | Tỷ lệ minh họa | Đặc điểm |
|---|---:|---|
| Small tenants | 60% tenants | Mỗi tenant ít Orders |
| Medium tenants | 35% tenants | Dữ liệu trung bình |
| Large tenants | 5% tenants | Chiếm phần lớn Orders |
| Orders ít Lines | 75% Orders | 1–3 Lines |
| Orders trung bình | 20% Orders | 4–20 Lines |
| Orders nhiều Lines | 5% Orders | 21–100+ Lines |

**Đây là số minh họa**, không phải thống kê mặc định của thương mại điện tử. Thay tỷ lệ bằng phân phối từ hệ thống mục tiêu, đã được tổng hợp/anonymize nếu cần.

### 10.3. Đừng seed bằng một transaction khổng lồ qua JPA nếu mục tiêu chỉ đo read

Dùng batch JDBC/SQL import, chia transactions hoặc bulk loading phù hợp. Seeding nên được tách khỏi benchmark measurement để tránh tính thời gian INSERT fixtures vào read latency.

### 10.4. Có thể seed bằng PostgreSQL generate_series

Ví dụ riêng cho PostgreSQL:

```sql
-- Giả sử schema có sales_order và customers
-- với IDs được chuẩn bị trước; chỉ minh họa.
INSERT INTO sales_order (
    order_id,
    tenant_id,
    customer_id,
    order_status,
    total_amount,
    created_at,
    row_version
)
SELECT
    i,
    CASE
        WHEN i % 10 < 6 THEN 'tenant-hot'
        ELSE 'tenant-' || ((i % 100) + 1)::text
    END,
    ((i % 100000) + 1),
    CASE
        WHEN i % 10 < 2 THEN 'PAID'
        WHEN i % 10 < 7 THEN 'SHIPPED'
        ELSE 'NEW'
    END,
    (i % 10000)::numeric / 100,
    TIMESTAMP '2026-01-01'
        + (i % 300) * INTERVAL '1 day',
    0
FROM generate_series(1, 1000000) AS g(i);
```

Đoạn SQL trên **chỉ chạy được khi các Customers/FKs và column types tương thích đã được chuẩn bị**. Distribution này có tính quy luật rất mạnh, không giống thật; dùng làm demo kỹ thuật, không coi đây là bộ benchmark đủ đại diện. Với benchmark thực, cần phân phối/correlation được kiểm soát và dữ liệu tuân thủ domain constraints.

### 10.5. Verify dataset bằng số liệu tổng hợp

```sql
SELECT count(*) FROM sales_order;

SELECT tenant_id, count(*)
FROM sales_order
GROUP BY tenant_id
ORDER BY count(*) DESC
LIMIT 10;

SELECT order_status, count(*)
FROM sales_order
GROUP BY order_status;

SELECT min(created_at), max(created_at)
FROM sales_order;
```

Không chỉ kiểm tra “INSERT thành công”; phải xem liệu dataset thật sự tạo skew theo yêu cầu.

---

## 11. Thống kê số child/parent

N+1 và fetch joins phụ thuộc rất lớn vào cardinality.

Ví dụ PostgreSQL:

```sql
WITH line_counts AS (
    SELECT order_id, count(*) AS line_count
    FROM order_line
    GROUP BY order_id
)
SELECT
    min(line_count) AS min_lines,
    percentile_cont(0.5)
        WITHIN GROUP (ORDER BY line_count) AS p50_lines,
    percentile_cont(0.95)
        WITHIN GROUP (ORDER BY line_count) AS p95_lines,
    max(line_count) AS max_lines
FROM line_counts;
```

### 11.1. Chú ý Orders không có Lines

Query trên chỉ nhìn Orders có ít nhất một Line. Nếu domain cho phép Orders có 0 Lines, cần `LEFT JOIN` từ Orders khi tính phân phối toàn bộ.

### 11.2. Tại sao p95 quan trọng hơn average?

Nếu trung bình 4 Lines/Order nhưng có 1% Orders chứa 2.000 Lines, detail fetch graph có thể gây memory spike chỉ ở một số request. Average che tail behavior.

### 11.3. Trường hợp có nhiều collection

Nếu Order có 30 Lines và 20 Payments, fetch join đồng thời có nguy cơ nhân khoảng 600 SQL rows cho một Order trước filters. Benchmark với mỗi collection chỉ 1 child sẽ không phát hiện vấn đề.

### 11.4. Cần đo cả distinct keys

100 Orders có 1 Customer khác với 100 Orders có 100 Customers. L1 cache có thể che N+1 trong trường hợp đầu; test phải có cả hai.

---

## 12. Planner statistics: dữ liệu lớn nhưng ANALYZE chưa chạy cũng sai

PostgreSQL và nhiều DBs dùng thống kê để ước lượng selectivity/cardinality. Sau bulk seed/migration:

```sql
ANALYZE sales_order;
ANALYZE order_line;
ANALYZE customer;
```

### 12.1. Không có statistics, plan có thể khác production

Một table vừa bulk loaded nhưng stats chưa cập nhật có thể khiến optimizer estimate sai số rows và chọn join/index scan không phù hợp.

### 12.2. Stats cũng có thể stale ở production

Nếu production có frequent updates/deletes, statistics freshness và autovacuum/analyze scheduling ảnh hưởng plans. Benchmark trên freshly analyzed database có thể đại diện **cho một healthy state**, nhưng chưa mô phỏng stale stats/bloat.

### 12.3. ANALYZE không tự tạo index

Nó thu thập statistics, không thay schema. Nếu index cần thiết không tồn tại, planner vẫn không dùng được.

### 12.4. Cẩn thận VACUUM FULL/REINDEX

Đây là các thao tác bảo trì có thể gây locks/cost lớn. Không chạy vô điều kiện trên production để “cải thiện benchmark”. Cần maintenance plan, quyền và hiểu rõ DB.

---

## 13. Testcontainers: dùng engine gần production trong integration tests

Nếu production dùng PostgreSQL, Testcontainers giúp khởi tạo một PostgreSQL instance tạm thời cho tests thay vì H2.

Ví dụ với Spring Boot/JUnit 5 (mã minh họa theo APIs hiện hành của bộ thư viện tương ứng):

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest
@Testcontainers
class OrderQueryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry
    ) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            postgres::getUsername
        );
        registry.add(
            "spring.datasource.password",
            postgres::getPassword
        );
    }

    @Test
    void loadsExpectedOrders() {
        // Seed and assert result correctness using
        // the database/provider setup under test.
    }
}
```

### 13.1. Version trong ví dụ không phải khuyến nghị production

`postgres:16` chỉ minh họa pin major version. Trong dự án thật, chọn image có version tương ứng production, và ưu tiên kiểm soát image digest/minor version theo policy.

### 13.2. Testcontainers kiểm tra compatibility tốt hơn H2

Có thể phát hiện syntax, JSON, sequences, collation, locking, indexes và dialect behaviors liên quan PostgreSQL mà H2 không tái hiện đúng.

### 13.3. Container local không tự đại diện production capacity

Một container PostgreSQL trên laptop/CI thường dùng CPU/RAM/network/storage khác production. Nó rất tốt cho **integration behavior và relative comparisons**; không tự là chứng cứ SLA p99 production.

### 13.4. Dùng migrations thật

Đừng để test `ddl-auto=create` tạo schema khác production nếu mục tiêu là plan fidelity. Chạy migrations/seed, rồi assert schema tương ứng.

### 13.5. CI time budget

Một dataset 10 triệu rows cho mọi commit có thể quá chậm. Dùng fast integration tests trên CI và representative-scale performance suite chạy theo lịch/release pipeline riêng.

---

## 14. Không nên khẳng định “mọi thứ giống production” khi thực ra không phải

Một báo cáo nên khai rõ:

```text
Database:
  PostgreSQL 16.x, Testcontainers
  same major version as staging, not same hardware

Schema:
  Flyway migrations V1..V42

Data:
  1.2m Orders, 5.8m Lines
  anonymized distribution estimates from production

Runtime:
  Java 21, Hibernate version X
  pool max 20

Workload:
  read-only list endpoints
  10 and 50 concurrent virtual users

Limitations:
  local network, no read replica,
  no background jobs, no production bloat
```

Một báo cáo minh bạch với giới hạn rõ đáng tin hơn câu “đã benchmark giống production 100%” nhưng không có metadata tái lập.

---

## 15. Các lớp cache cần kiểm soát khi đo

```text
HTTP/request cache
       |
       v
Application memoization / Redis
       |
       v
JPA L1 persistence context
       |
       v
JPA L2 entity cache / provider query cache
       |
       v
JDBC/driver prepared statement caches
       |
       v
Database shared buffers / OS page cache
       |
       v
Disk / remote storage
```

### 15.1. L1 cache

Trong cùng EntityManager, tải Product#42 lần hai có thể không phát SQL nữa. Nếu benchmark gọi repository 1.000 lần với **một EM dài sống**, bạn có thể đang đo mostly L1 cache hits, không phải DB.

### 15.2. L2 cache

Hibernate hoặc provider khác có thể cache entities across persistence contexts. Warm L2 giúp reference data nhưng không phải mọi tables đều cacheable. Test phải nêu L2 on/off/hit rate.

### 15.3. Query cache

Một số providers hỗ trợ query-result cache với semantics invalidation riêng. Query cache hit có thể làm kết quả khác hoàn toàn khi đo cùng JPQL query lặp lại. Không giả định query cache là mặc định chuẩn JPA.

### 15.4. Database buffer cache

PostgreSQL shared buffers/OS file cache khiến repeated SELECT nhanh hơn disk-cold run. Cold database cache rất khó reset an toàn và nhất quán trên shared DB.

### 15.5. App cache khác JPA cache

Nếu API lấy response từ Redis, có thể không gọi JPA. Đó là benchmark endpoint cache, không phải phép đo JPA query path. Cần tách hai scenarios.

---

## 16. Cold vs warm: mô tả điều kiện cụ thể

“Cold cache” có nhiều nghĩa:

- New EntityManager (cold L1).
- Evicted L2 regions.
- Empty application cache.
- Database pages chưa ở shared buffers.
- JVM chưa JIT warmed.
- JDBC pool chưa mở connections.

Không nên viết “cold” mà không nói **cold tại lớp nào**.

### 16.1. Ví dụ hai scenarios hợp lý

**Cold L1, warm DB:** Mỗi operation mở EntityManager/transaction mới, nhưng database đã được warmup. Phản ánh nhiều web requests đọc một database hoạt động ổn định.

**Warm L2 reference data:** Mỗi request có EM riêng, Customer/Product cache hit rate tương đối cao. Phản ánh hot reference data, cần test cache invalidation correctness.

### 16.2. Đừng reset database OS cache trên môi trường chia sẻ

Các lệnh hệ thống làm drop global caches hoặc reboot database chỉ để tạo cold run có thể ảnh hưởng người khác. Nếu cần cold-storage benchmark, dùng môi trường dedicated và procedure được phê duyệt.

### 16.3. Có cả cold và warm kết quả

Nếu một optimization chỉ nhanh khi cache warm nhưng rất chậm sau restart/deploy, cần biết điều đó để quyết định startup/traffic ramp behavior.

### 16.4. Ghi rõ cache state trong báo cáo

Ví dụ: “new EntityManager each request; Hibernate L2 disabled; database warm after 10-minute warmup”. Cụ thể hơn nhiều so với “cache off”.

---

## 17. JVM và connection pool warmup

Một Java application mới chạy khác ứng dụng đã hoạt động 10 phút:

- JIT compilation.
- Classloading.
- Lazy bean initialization.
- JDBC connection establishment.
- Statement preparation.
- HikariCP pool ramp-up.
- L2/app cache warmup.
- Database plan/buffer warmup.

### 17.1. Đo sau warmup

Một protocol có thể:

```text
Start application + database
Verify schema/data
Warmup: 5–10 minutes under target workload
Measure: fixed window
Cooldown / record metrics
Repeat: several independent runs
```

Thời lượng là ví dụ, không phải giá trị chuẩn. Phải kiểm tra metrics đã ổn định trước measurement.

### 17.2. Không bỏ cold-start hoàn toàn

Startup latency, first-request cost và cache refill đôi khi là yêu cầu riêng. Đo chúng như **separate metrics**, không trộn với steady-state latency.

### 17.3. Đừng tái sử dụng pooled connection theo cách che query behavior

Một micro loop trong một transaction/connection có thể cho kết quả quá đẹp so với requests thực sự lấy connection từ pool và chịu queue wait.

### 17.4. Connection pool size là một biến độc lập quan trọng

Nếu HTTP có 200 concurrent requests nhưng Hikari maximum pool size 10, nhiều requests phải đợi connection. Tăng pool không luôn tăng throughput: database có thể bị quá tải với nhiều concurrent queries. Cần đo cả pool wait và DB saturation.

---

## 18. Đo đúng thời gian: end-to-end vs JDBC vs database execution

Một request có các giai đoạn:

```text
HTTP request enters
   |
   +-- Authentication/authorization
   +-- Application mapping/validation
   +-- Wait for JDBC connection
   +-- SQL execution + network round-trip
   +-- Hydrate entities/proxies
   +-- Lazy association SQL (maybe many)
   +-- DTO mapping
   +-- JSON serialization
   +-- Commit/read-only transaction cleanup
   v
HTTP response delivered
```

Các số đo tương ứng:

| Metric | Đo ở đâu | Dùng để |
|---|---|---|
| HTTP latency | Boundary request/response | Trải nghiệm người dùng |
| Service method latency | Application span | Logic ứng dụng |
| JDBC span latency | DataSource instrumentation | SQL + network + driver |
| Database server execution time | DB statistics/EXPLAIN | Cost bên DB |
| Connection acquisition wait | Pool metrics | Pool contention |
| JPA hydration/allocation | Profiling/tracing | Cost ORM |
| SQL count | Hibernate Statistics/JDBC proxy | N+1, lazy loads |
| Rows returned/processed | DB plan/JDBC profiling | Join amplification |

### 18.1. Database 5 ms không có nghĩa API 5 ms

20 SQL queries × network RTT có thể tạo latency lớn dù mỗi query server chạy < 1 ms. N+1 thường bị đánh giá thấp khi benchmark database ngay trên localhost.

### 18.2. SQL count không phải latency

Một query fetch join trả 1 triệu duplicated rows có thể chậm hơn 5 queries bounded. Phải đo bytes/rows và Java hydration.

### 18.3. Percentiles cần sample đủ

p99 của 20 requests không đáng tin. Thu đủ samples theo workload/stability target và báo cả số samples, measurement duration và confidence/variance khi đưa ra quyết định.

### 18.4. Có phân biệt lỗi và timeout

Một endpoint có p95 thấp vì 20% requests đã timeout/failed không phải thành công. Báo latency cùng throughput và error/timeout rate.

---

## 19. p50, p95, p99 và phân phối thời gian

Giả sử 1.000 requests có phần lớn nhanh, một số rất chậm:

```text
p50 = 20 ms
p95 = 90 ms
p99 = 400 ms
max = 2,000 ms
```

Đây là số minh họa.

### 19.1. Vì sao average không đủ?

Nếu 990 requests mất 10 ms và 10 requests mất 1.000 ms, average có thể trông hợp lý nhưng một phần người dùng chịu delay rất lớn.

### 19.2. Tail latency và database

p99 có thể bị ảnh hưởng bởi:

- GC pauses.
- Connection pool wait.
- Database lock waits.
- Occasional expensive query plans.
- Large Orders có nhiều Lines.
- Disk cache misses.
- Network jitter.
- Background batch jobs.

### 19.3. Cần histogram/time series

Một p95 đơn lẻ không cho thấy hệ thống đã ổn định hay có spike theo giờ. Đo over-time và quan sát load/throughput cùng lúc.

### 19.4. Tránh coordinated omission

Một load generator chỉ gửi request tiếp theo sau khi request trước hoàn thành có thể bỏ sót khoảng thời gian server bị ngẽn, báo latency quá đẹp. Cân nhắc arrival rate/open-loop workloads khi mục tiêu là hệ thống chịu traffic theo thời gian.

---

## 20. Concurrency: tại sao đo một request tuần tự là chưa đủ?

Một SELECT nhanh ở 1 user có thể chậm hơn nhiều dưới 100 users do:

- Pool connections bị chờ.
- DB CPU/IO saturation.
- Contention trên indexes/pages/locks.
- Transaction isolation và row locks.
- Shared buffer churn.
- Checkpoints/WAL pressure.
- Background writes.
- JPA L2/query cache contention.

### 20.1. Chọn các mức tải

```text
1 concurrent user  -> Baseline latency
10 users            -> Light load
40 users            -> Expected steady load
100 users           -> Peak estimate
200 users           -> Stress (beyond normal)
```

Các mức chỉ minh họa; nên dựa vào request arrival rate và traffic distribution thực, không gắn cứng.

### 20.2. Phân biệt throughput và concurrency

**Concurrency** là số operations đang chạy đồng thời. **Throughput** là số operations hoàn thành mỗi giây. Khi hệ thống bão hòa, tăng concurrency có thể khiến throughput hầu như không tăng nhưng latency tăng mạnh.

### 20.3. Test nhiều operation mixes

Ví dụ workload mẫu:

```text
70% GET /orders list
15% GET /orders/{id} detail
10% POST /orders
 5% PATCH /orders/{id}
```

Đây là phân phối minh họa. Chỉ chạy SELECT list có thể che write contention/index maintenance phát sinh ở hệ thống thật.

### 20.4. Background jobs quan trọng

Một nightly cleanup, bulk import hoặc report export có thể làm cùng endpoint chậm vào một thời điểm nhất định. Nếu đó là production reality, tạo một scenario mixed load có controlled background work.

---

## 21. Đo trên hệ quản trị cùng phiên bản vẫn có sai khác hạ tầng

Một PostgreSQL container trên laptop và một managed PostgreSQL cluster có thể khác:

- CPU count/frequency/throttling.
- RAM/shared_buffers/work_mem.
- Storage SSD/NVMe/EBS/network disk.
- IOPS/throughput limits.
- Network RTT app↔DB.
- Backup/checkpoint/autovacuum workload.
- Read replicas và replication lag.
- Connection caps.
- Parallel query settings.
- DB parameter groups.

### 21.1. Relative comparison vs absolute SLA

Trên CI Testcontainers, một query A nhanh hơn B có thể là tín hiệu hữu ích **trong cùng môi trường**. Nhưng không suy ra p99 production bằng thời gian CI.

### 21.2. Muốn chứng minh SLO gần production

Dùng staging/performance environment có CPU/storage/network/topology gần thực tế, dataset tương ứng và tải đại diện. Nêu rõ khác biệt còn lại.

### 21.3. Network latency nhân N+1

Nếu mỗi round-trip mất thêm 3 ms và query path tạo 50 secondary SELECTs, riêng round-trip component có thể lớn hơn 150 ms trong scenario giả định. Điều này giải thích vì sao localhost che N+1.

### 21.4. Không dùng cùng DB production cho destructive load test

Load test nặng có thể ảnh hưởng khách hàng, locks, storage và cost. Ưu tiên isolated environment; production canary/load monitoring chỉ theo chính sách được phê duyệt, có rollback/safety budgets.

---

## 22. EXPLAIN: xem database định thực thi SQL như thế nào

JPQL cuối cùng được provider dịch thành SQL. Muốn hiểu plan, phải kiểm tra **SQL thật** và bind parameters/query shapes tương đương.

Ví dụ PostgreSQL:

```sql
EXPLAIN
SELECT
    o.order_id,
    o.created_at,
    o.total_amount
FROM sales_order o
WHERE o.tenant_id = 'tenant-hot'
  AND o.order_status = 'PAID'
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 50;
```

### 22.1. Các node thường gặp

| Plan node | Ý nghĩa khái quát |
|---|---|
| Seq Scan | Quét bảng/partition tuần tự |
| Index Scan | Dò index rồi lấy rows |
| Index Only Scan | Có thể lấy dữ liệu từ index, nhưng visibility checks vẫn có thể cần heap |
| Bitmap Index/Heap Scan | Gom row locations rồi đọc heap |
| Nested Loop | Join lặp theo input rows |
| Hash Join | Xây/tra bảng hash theo join keys |
| Merge Join | Join sorted inputs |
| Sort | Sắp xếp rows |
| Aggregate/HashAggregate | Tính COUNT/SUM/GROUP BY |
| Gather | Kết hợp parallel workers |

### 22.2. Seq Scan không tự là lỗi

Nếu query cần đọc 80% bảng hoặc bảng rất nhỏ, sequential scan có thể tốt hơn index scan.

### 22.3. Index Scan không chắc đã tối ưu

Nếu index lookup trả 1 triệu rows và phải random-access nhiều heap pages, nó có thể tốn hơn một plan khác. Đừng chỉ nhìn có chữ “Index Scan” rồi dừng phân tích.

### 22.4. Kế hoạch phụ thuộc SQL thật

Tên cột, predicate, JOIN, ORDER BY, LIMIT, parameter casts và index expressions của provider quyết định query plan. Một SQL viết tay “na ná” JPQL generated SQL có thể cho kết quả khác.

---

## 23. EXPLAIN ANALYZE BUFFERS: ước lượng so với thực tế

PostgreSQL:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    o.order_id,
    o.total_amount,
    o.created_at
FROM sales_order o
WHERE o.tenant_id = 'tenant-hot'
  AND o.order_status = 'PAID'
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 50;
```

### 23.1. EXPLAIN và EXPLAIN ANALYZE khác nhau

- `EXPLAIN` mô tả planned execution mà không thực hiện query SELECT theo cách `ANALYZE` chạy nó.
- `EXPLAIN ANALYZE` **thực sự thực thi statement** để thu actual timing/rows.

**Cảnh báo quan trọng:** Với INSERT/UPDATE/DELETE, `EXPLAIN ANALYZE` thực thi DML và có thể sửa dữ liệu. Chỉ làm trên môi trường thử nghiệm có kiểm soát hoặc transaction rollback thích hợp, đồng thời nhớ database triggers/external side effects có thể không tự rollback.

### 23.2. Đọc những thông tin nào?

- Estimated cost/rows.
- Actual time/rows.
- Number of loops.
- Buffer hits/reads.
- Rows removed by filter.
- Sort method/memory/disk spill.
- Join strategy.
- Parallel workers.
- Planning vs execution time.

### 23.3. Estimated rows sai rất xa actual rows

Nếu plan dự đoán 50 rows nhưng thực tế có 500.000 rows, optimizer có thể chọn join/index strategy không phù hợp. Kiểm tra statistics, parameter skew, correlations và indexes.

### 23.4. BUFFERS cho biết gì?

`shared hit`, `shared read` và các buffer categories giúp hiểu memory/disk activity tương đối. Buffer hit cao không đồng nghĩa kết quả “miễn phí”: CPU, locking và network vẫn có cost.

### 23.5. EXPLAIN ANALYZE không chứa toàn bộ API latency

Nó đo SQL bên database, không bao gồm mọi bước JDBC network, JPA hydration, DTO serialization, waiting for pool và external calls.

---

## 24. Query planner và bind parameters

Application có:

```java
.setParameter("tenant", tenant)
.setParameter("status", OrderStatus.PAID)
```

SQL thường dùng bind parameters, không inline values. Database driver/server có thể dùng prepared statements, cached plans và strategies phụ thuộc parameter selectivity.

### 24.1. Đừng so sánh sai loại SQL

Một manual EXPLAIN dùng literal `tenant='tenant-small'` không nhất thiết phản ánh plan của prepared query với `tenant-hot`.

### 24.2. Parameter distribution matters

Test các tenant/status/time-range classes đã xác định. Nếu query performance cực khác theo parameters, không báo một average duy nhất.

### 24.3. Dynamic IN lists

`WHERE id IN (:ids)` với 10 IDs khác 10.000 IDs. Số bind parameters, plan shape và serialization overhead có thể thay đổi; benchmark theo page/chunk sizes thật.

### 24.4. Pagination parameter values

`LIMIT 50 OFFSET 0` khác `LIMIT 50 OFFSET 500000`. Test page đầu và page sâu; cân nhắc keyset nếu business cho phép.

---

## 25. Benchmark N+1 trên dữ liệu đủ đa dạng

Một test naive:

```java
List<SalesOrder> orders = repository.findTop50();

for (SalesOrder order : orders) {
    String customerName =
        order.getCustomer().getName();
}
```

### 25.1. Dataset dễ che N+1

50 Orders cùng một Customer → L1 có thể chỉ tải một Customer. Test cần 50 Orders trỏ 50 Customers khác nhau để nhìn query growth trong cold context.

### 25.2. Baseline và candidate

**Baseline:** Root entity query + lazy Customer access trong loop.

**Candidate A:** JPQL `JOIN FETCH o.customer`.

**Candidate B:** DTO projection `select new OrderRow(o.id,c.name,...)`.

Đo:

- SQL SELECT count.
- Rows transferred.
- Entity/DTO allocations.
- API p95.
- DB CPU.
- Correctness của 50 rows.

### 25.3. Query count chỉ là một dimension

Candidate A có thể giảm 51 SQL xuống 1 nhưng hydrate 50 Order + 50 Customer entities. Candidate B có thể hydrate DTOs mà không quản lý 100 entities. Use case list read-only thường phù hợp Candidate B; domain write workflow có thể phù hợp A.

### 25.4. Test cold and warm scenarios

L2 warm có thể giảm lazy Customer queries của baseline. Nhưng nếu Customer keys chưa cache hoặc nhiều customers mới, pattern vẫn có vấn đề.

---

## 26. Benchmark fetch join collection và row explosion

Giả sử 50 Orders, trung bình 20 Lines/Order:

```text
Root query:
  50 Order rows

Fetch join Lines:
  about 1,000 joined rows

Fetch join Lines + Payments:
  có thể nhiều nghìn rows, tùy cardinality.
```

### 26.1. Đo cả SQL row count

Một query duy nhất có thể truyền 1.000 Order+Line composite rows, làm dữ liệu Order lặp lại. Network transfer/hydration tăng, dù query count giảm.

### 26.2. Đo nested lazy loads

Nếu đọc Product.name cho từng Line mà Product là LAZY, N+1 lồng nhau có thể còn. Entity graph/subgraph hoặc truy vấn Line+Product cần được test.

### 26.3. So sánh với two-phase reads

Một phương án:

1. Page Order IDs (50).
2. Fetch Orders+to-one Customer.
3. Fetch Lines+Products theo page IDs.

Ba bounded queries có thể hiệu quả hơn một giant join nhiều collections.

### 26.4. Cẩn thận pagination correctness

Collection fetch join + `setMaxResults` có thể khiến provider fetch/paginate trong memory hoặc fail. Test không chỉ latency mà phải assert số Orders, Lines đầy đủ, thứ tự trang và SQL có LIMIT áp ở đâu.

---

## 27. Benchmark offset vs keyset pagination

JPQL offset:

```java
query
    .setFirstResult(pageIndex * pageSize)
    .setMaxResults(pageSize);
```

Keyset theo `createdAt DESC, id DESC`:

```jpql
select o.id
from SalesOrder o
where o.tenantId = :tenant
  and (
      o.createdAt < :cursorTime
      or (
          o.createdAt = :cursorTime
          and o.id < :cursorId
      )
  )
order by o.createdAt desc, o.id desc
```

### 27.1. Thử theo độ sâu

```text
Page 0
Page 100
Page 10,000
Page 100,000
```

Chỉ những page tồn tại trong dataset mới có ý nghĩa; không benchmark page sâu trên table nhỏ rồi kết luận “offset ổn”.

### 27.2. Đảm bảo semantics tương đương

Keyset/cursor không thể cho phép nhảy tới bất kỳ page index như offset mà không có thông tin cursor phù hợp. Hai chiến lược có UX contract khác nhau. So sánh cần cùng business goal.

### 27.3. Cần index hỗ trợ ordering

Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_order_tenant_created_id
ON sales_order(
    tenant_id,
    created_at DESC,
    order_id DESC
);
```

Index không bảo đảm plan luôn chọn index scan; kiểm tra actual selectivity/plan.

### 27.4. Concurrent writes ảnh hưởng kết quả

Thêm/xóa rows giữa page requests có thể gây duplicates/omissions với offset; keyset cũng có trade-offs theo mutable sort keys. Test correctness và định nghĩa snapshot/cursor policy.

---

## 28. Benchmark COUNT và aggregate queries

Một trang `Page<Order>` có thể chạy query list **và** count query. Với table lớn, `COUNT(*)` có thể thành phần đắt hơn list retrieval.

### 28.1. Không chỉ đo query danh sách

Đo toàn repository method/endpoint gồm:

- Root data SELECT.
- Count SELECT nếu API yêu cầu total.
- Mapping DTO/entities.
- Any nested lazy loads.

### 28.2. Khi UX chỉ cần “còn trang tiếp”

Có thể dùng Slice hoặc fetch `pageSize+1` để biết có trang sau, tránh total count trong một số use cases.

### 28.3. Aggregate per parent trong loop

Sai:

```java
for (SalesOrder order : orders) {
    long lines = repository.countLines(order.getId());
}
```

Có thể thành 1+N queries. Tối ưu:

```jpql
select l.order.id, count(l)
from OrderLine l
where l.order.id in :orderIds
group by l.order.id
```

Benchmark cả hai dưới dataset 50/100 Orders và Lines distribution thực.

### 28.4. Aggregate query có thể tốn DB CPU

Một query GROUP BY trên hàng triệu child rows không mặc định rẻ. Cần indexes, partition pruning, read model/materialized summaries theo nghiệp vụ và update consistency.

---

## 29. Benchmark INSERT và batching

Khi ứng dụng tạo 10.000 child entities, throughput chịu ảnh hưởng:

- Generated ID strategy.
- JDBC batching.
- Flush frequency.
- Persistence context size.
- Cascades.
- Index maintenance.
- FK/UNIQUE checks.
- WAL/disk durability.
- Transaction boundaries.

### 29.1. Hibernate JDBC batch size

Ví dụ extension property:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
hibernate.order_updates=true
```

Đây là Hibernate-specific behavior. Batching có thể khác theo provider/dialect, generated ID strategy và SQL statements thực tế.

### 29.2. IDENTITY có thể hạn chế insert batching

Với database-generated IDENTITY, provider thường cần nhận key tại INSERT và khả năng JDBC batch có thể bị giới hạn. So sánh với SEQUENCE strategy chỉ khi hai thiết kế cùng hợp lệ, không đổi ID generator tùy tiện chỉ để benchmark đẹp.

### 29.3. Batching không đồng nghĩa commit theo batch

`hibernate.jdbc.batch_size=50` là mức gom JDBC operations, không tự tạo 50-record transactions. Cần định nghĩa transaction boundaries riêng.

### 29.4. Đo nhiều transaction sizes

```text
100 entities per transaction
1,000 entities per transaction
10,000 entities per transaction
```

Đo memory, flush latency, transaction duration, throughput và rollback impact. Transaction lớn có thể giữ locks lâu, context phình to, khó phục hồi khi fail.

### 29.5. Flush/clear theo lô

Trong batch job có thể:

```java
for (int i = 0; i < items.size(); i++) {
    em.persist(items.get(i));

    if ((i + 1) % 50 == 0) {
        em.flush();
        em.clear();
    }
}
em.flush();
```

Đây là pattern minh họa. `clear` detach toàn context, có thể ảnh hưởng associations và pending changes; cần xác nhận domain workflow. `flush` không commit và exception/rollback vẫn áp dụng.

---

## 30. Benchmark UPDATE, dirty checking và @Version

Một workflow sửa 1.000 Orders khác bulk SQL UPDATE.

### 30.1. Managed entity loop

```java
for (Long id : ids) {
    SalesOrder o = em.find(SalesOrder.class, id);
    o.changeStatus(OrderStatus.SHIPPED);
}
em.flush();
```

Có thể tạo N SELECT + N UPDATE (tùy context, cache/batching). `changeStatus` là domain method minh họa.

### 30.2. Bulk JPQL update

```java
int changed = em.createQuery(
    """
    update SalesOrder o
    set o.status = :next
    where o.tenantId = :tenant
      and o.status = :current
    """
)
.setParameter("next", OrderStatus.SHIPPED)
.setParameter("tenant", tenant)
.setParameter("current", OrderStatus.PAID)
.executeUpdate();
```

Bulk UPDATE có thể nhanh hơn ở số statements, nhưng bypass entity lifecycle callbacks/automatic version management/dirty checking theo semantics của bulk DML. **Không so sánh chỉ throughput nếu hai phương án không giữ cùng business contract**.

### 30.3. Version/callback correctness là điều kiện đo

Nếu managed updates gọi validation/listeners và kiểm tra `@Version` còn bulk query không, hai methods không tương đương. Cần xác định requirements trước.

### 30.4. Đo contention

Khi hai transactions cùng update hot Order/Product, lock waits và optimistic conflict rate có thể chi phối latency hơn SQL planning.

---

## 31. Transaction isolation và khóa ảnh hưởng phép đo

Các isolation levels được DB triển khai khác nhau; việc benchmark chỉ trên một transaction không thể cho thấy contention.

### 31.1. READ COMMITTED

Có thể thấy committed data giữa statements khác nhau; phù hợp nhiều transactional APIs nhưng không bảo đảm repeatable snapshot trên toàn use case.

### 31.2. REPEATABLE READ / SNAPSHOT behaviors

Có thể bảo vệ snapshot reads theo DB semantics, nhưng không tự thay business uniqueness/lock strategies. Benchmark phiên bản và engine thực tế, không suy từ tên isolation level chung.

### 31.3. SERIALIZABLE

Có thể làm tăng abort/retry rates dưới contention. Latency của **successful business transaction bao gồm retries** quan trọng hơn chỉ thời gian một attempt.

### 31.4. Optimistic locking

Test hai transactions update cùng `@Version` entity, đo conflict rate và client-visible retries. Bỏ qua failures rồi chỉ tính successful fast requests sẽ cho kết quả quá lạc quan.

### 31.5. Pessimistic locking

`PESSIMISTIC_WRITE` có thể tạo queue/lock waits. Đo cùng hot keys và concurrency theo production, không đo với IDs luôn khác nhau nếu thực tế có contention.

---

## 32. Connection pool và database capacity

Giả sử:

```text
HTTP concurrency = 100
Hikari maximumPoolSize = 10
PostgreSQL available connections = 50
```

Nếu 100 concurrent requests đều cần JDBC connection, phần lớn có thể phải chờ một trong 10 pool connections, dù mỗi SQL chỉ mất vài milliseconds.

### 32.1. Metrics cần lấy

- Active connections.
- Idle connections.
- Pending threads/connection wait.
- Connection acquire latency.
- Connection timeout count.
- DB active sessions/locks.
- DB CPU/I/O saturation.

### 32.2. Tăng pool size không chắc tốt hơn

Nếu DB CPU đã 100%, tăng từ 10 lên 100 active queries có thể tăng contention/cache misses và làm p99 tệ hơn.

### 32.3. Transaction duration liên quan

Nếu code giữ connection trong lúc gọi remote HTTP hoặc stream file, pool có thể cạn. Trước khi tăng pool, điều tra thời gian giữ transaction/connection.

### 32.4. Test các cấu hình một biến mỗi lần

Ví dụ giữ dataset/query/load cố định, thay maximumPoolSize 10/20/40. Không vừa đổi pool, index, JVM heap và SQL rồi kết luận nguyên nhân duy nhất.

---

## 33. Tác động của query shape với JSON/LOB và cột rộng

Một entity có các cột:

```text
Order.id
Order.status
Order.totalAmount
Order.largeJsonDocument
Order.binaryAttachment
```

Nếu list page chỉ cần id/status/total nhưng entity query tải nhiều cột rộng theo mapping/default, network và hydration cost tăng.

### 33.1. DTO projection

```jpql
select new com.example.api.OrderRow(
    o.id, o.status, o.totalAmount
)
from SalesOrder o
where o.tenantId = :tenant
```

Truy vấn selected columns có thể tránh tải payload lớn không cần thiết.

### 33.2. @Basic(fetch=LAZY) cho basic attributes không phải bảo đảm tuyệt đối

Lazy basic properties có thể cần bytecode enhancement/provider support; không giả định annotation luôn trì hoãn tải large field trên mọi JPA runtime.

### 33.3. Đo row width

Hai queries cùng 50 rows nhưng một query trả 50 × 1 KB, query khác 50 × 100 KB thì network transfer/hydration khác biệt lớn.

### 33.4. Cẩn thận N+1 với LOB access

Nếu danh sách load root entities rồi mỗi row gọi getter LOB, có thể tạo secondary loading cost lớn. Chọn DTO/read model theo nhu cầu.

---

## 34. Transaction size, GC và ORM hydration

JPA quản lý entity states trong persistence context. Đọc 100.000 entities bằng một `getResultList()` có thể giữ nhiều managed objects/collections trong memory.

### 34.1. Không chỉ đo database latency

Server DB có thể trả rows nhanh, nhưng JVM mất thời gian/hạ memory tạo entities, proxies, snapshots và collections.

### 34.2. Theo dõi

- Heap usage before/after.
- Allocation rate.
- GC pause p95/p99.
- Entity count managed.
- Persistence context clear/detach frequency.
- Response serialization memory.
- Batch size/chunk memory.

### 34.3. Export dùng DTO stream/chunks

Với read-only export lớn, dùng projection, stream/chunk APIs theo provider/driver, pagination keyset và transaction boundaries phù hợp. Không hydrate toàn entity graph nếu không sửa chúng.

### 34.4. Streaming không tự giải phóng tài nguyên

ResultSet/stream có thể giữ JDBC connection và transaction mở. Cần close đúng, backpressure và test long-running failure/retry semantics.

---

## 35. Kịch bản benchmark với Testcontainers và Spring

Một quy trình hợp lý:

```text
1. Start PostgreSQL container đúng major version.
2. Apply migrations.
3. Seed representative dataset với seed cố định.
4. Run ANALYZE / verify indexes.
5. Start app with pinned Hibernate/Spring configuration.
6. Warm up query + pool + JVM.
7. Execute baseline scenario ở concurrency cố định.
8. Record metrics/query plans.
9. Reset state cần thiết (hoặc dùng immutable dataset snapshot).
10. Execute candidate ở cùng workload.
11. Repeat runs, report variance.
12. Assert correctness và compare distributions.
```

### 35.1. Đừng seed và đo trong cùng khoảng thời gian

Seeding tạo WAL/index changes và làm DB caches/stats khác trạng thái ổn định. Nếu mục tiêu steady-state read benchmark, để DB settle và ANALYZE theo procedure.

### 35.2. Không bật debug SQL quá mức trong load test

Logging mọi SQL/params có thể chi phối CPU/disk và làm thay đổi kết quả. Dùng sampled tracing/aggregated metrics, hoặc đo SQL count riêng ở integration tests.

### 35.3. Giữ cấu hình xác định

Pin Java version, ORM provider version, JDBC driver, database image/version, migration commit, container resources và pool settings trong report.

### 35.4. Tránh CI noisy neighbors khi đo timings tuyệt đối

Shared CI runner có CPU scheduling/I/O fluctuations. Dùng dedicated runners khi cần reliable latency comparisons; trên shared CI ưu tiên non-timing regression checks như SQL count/correctness.

---

## 36. Đo Hibernate Statistics đúng cách

Khi ứng dụng dùng Hibernate ORM, bật statistics:

```properties
hibernate.generate_statistics=true
```

Ví dụ Java:

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics stats = sessionFactory.getStatistics();
stats.setStatisticsEnabled(true);
stats.clear();

// Thực hiện một use case trong môi trường test cô lập.

long preparedStatements =
    stats.getPrepareStatementCount();

long entityLoads =
    stats.getEntityLoadCount();

long collectionFetches =
    stats.getCollectionFetchCount();
```

### 36.1. Đây là API Hibernate, không phải JPA standard

`unwrap(SessionFactory.class)` và `Statistics` phụ thuộc provider. Khi dùng EclipseLink hoặc provider khác, dùng equivalent instrumentation/tooling của nó.

### 36.2. Statistics thường cấp SessionFactory

Một test chạy song song có thể ghi statement counts của threads khác. Không reset global stats trên production, cũng không dùng global count test dưới parallel runs mà không cô lập.

### 36.3. PreparedStatement count không hẳn bằng số network round-trips

Prepared statement creation/execution/batching/caching có semantics khác nhau; phải hiểu metric cụ thể. Dùng JDBC proxy/tracing và DB monitoring để bổ sung khi cần.

### 36.4. Đếm SELECT riêng

Nếu cần assertion “tối đa 3 SELECT cho 50 Orders”, một datasource proxy/SQL inspector có filter SELECT trong scope test thường rõ hơn tổng prepared statements nếu method có writes hoặc metadata queries.

---

## 37. Production observability: xác định query thực sự đắt

Một số nguồn thông tin:

- HTTP server latency histograms.
- Distributed traces (OpenTelemetry).
- JDBC spans.
- Connection pool metrics.
- Hibernate metrics/statistics theo sampling.
- Database slow query logs.
- PostgreSQL `pg_stat_statements` nếu extension/permissions cho phép.
- Database dashboards về waits, locks, buffer hit, CPU, I/O.
- Database query plan sampling có kiểm soát.

### 37.1. pg_stat_statements

Trên PostgreSQL, extension này có thể tổng hợp thời gian và call counts theo query fingerprint. Nó hỗ trợ tìm queries chiếm phần lớn total execution time, nhưng không tự chỉ ra toàn bộ JPA callsite hay HTTP latency.

### 37.2. Query fingerprint khác raw SQL text

Cùng SQL với parameter values khác thường được gom; cần bổ sung distribution/hot tenant diagnostics nếu performance phụ thuộc parameter skew.

### 37.3. N+1 nhìn từ trace

Một request trace có 51 JDBC spans tương tự `SELECT customer WHERE id=?`. Đó là bằng chứng rất hữu ích để liên hệ SQL với mapper/resolver code.

### 37.4. Không lạm dụng production logs

Full bind parameter logging có thể lộ dữ liệu cá nhân và gây overhead lớn. Chỉ dùng mức logging được cho phép và masking phù hợp.

### 37.5. Production telemetry để ưu tiên

Một query chỉ chạy 10 lần/ngày, dù mỗi lần 2s, có thể ít ưu tiên hơn query mất 30ms nhưng chạy hàng triệu lần/ngày và chiếm database CPU đáng kể. Xem cả latency * frequency * business importance.

---

## 38. Cách so sánh baseline và candidate công bằng

Để kết luận một thay đổi có ích:

- Cùng dataset snapshot.
- Cùng database engine/version.
- Cùng schema/indexes (trừ khi index chính là biến đang thử).
- Cùng query result contract.
- Cùng workload mix/parameters.
- Cùng number of virtual users/arrival rate.
- Cùng warmup procedure.
- Cùng cache policy.
- Cùng measurement duration.
- Cùng instrumentation overhead.
- Cùng application/runtime configuration.

### 38.1. Thay một biến mỗi lần

Nếu muốn chứng minh DTO projection tốt hơn entity+lazy loading, không đồng thời thêm index và tăng pool size rồi quy hết improvement cho DTO.

### 38.2. Khi thay nhiều biến là mục tiêu

Một candidate solution có thể là gói “DTO + index + keyset”. Có thể benchmark gói để đánh giá business impact, nhưng nếu muốn biết đóng góp từng thành phần, chạy experiments riêng.

### 38.3. Lặp lại nhiều run

Một lần A=30ms, B=25ms có thể do noise. Chạy nhiều measurement windows/independent runs và báo median/variance/confidence phù hợp.

### 38.4. A/B order

Nếu luôn chạy A trước rồi B sau, B có thể được lợi vì DB cache warm. Có thể alternating order A/B hoặc dùng reset/snapshot procedure phù hợp.

### 38.5. Không so sánh bằng kết quả từ hai ngày khác nhau mà không kiểm soát

Hạ tầng, background workload, dữ liệu và query plan có thể đổi. Nếu cần so sánh lịch sử, ghi lại metadata và dùng monitoring/statistical approaches.

---

## 39. Mẫu bảng kết quả benchmark

Ví dụ **dữ liệu giả định để minh họa cách trình bày**, không phải số đo thực tế:

| Metric | Baseline: entity + lazy Customer | Candidate: DTO join |
|---|---:|---:|
| Orders/page | 50 | 50 |
| Distinct Customers | 50 | 50 |
| SELECT statements/request | 51 | 1 |
| p50 API latency | 120 ms | 28 ms |
| p95 API latency | 260 ms | 52 ms |
| p99 API latency | 490 ms | 110 ms |
| Throughput ở tải cố định | 210 req/s | 345 req/s |
| Error rate | 0% | 0% |
| Page correctness | Pass | Pass |
| Tenant filter | Pass | Pass |

### 39.1. Không báo “nhanh hơn X%” khi result contract khác

Nếu candidate trả thiếu Customer name hoặc chỉ 20 Orders, kết quả không hợp lệ cho comparison.

### 39.2. Tại sao cần DB metrics?

Ứng dụng có thể nhanh hơn vì cache/app-layer behavior trong khi DB vẫn bão hòa. Theo dõi CPU/IO/pool cùng client-side metrics.

### 39.3. Ghi n và thời gian đo

Một bảng thực tế cần bổ sung `requests measured`, measurement window, warmup window, environment config và statistical method.

### 39.4. Kết luận có điều kiện

“Candidate giúp endpoint list trên dataset/perf environment X” chính xác hơn “DTO projection luôn nhanh hơn EntityGraph trong mọi JPA use case”.

---

## 40. Tìm bottleneck theo phương pháp từng tầng

Một endpoint GET /orders chậm:

### Bước 1 — Vẽ critical path

```text
Network
  -> HTTP middleware
  -> App/service
  -> Connection pool
  -> JDBC calls
  -> Database execution
  -> ORM hydration
  -> DTO mapping
  -> JSON response
```

### Bước 2 — Đo từng phần

Nếu 300 ms total, 200 ms pool wait, 30 ms SQL, 70 ms serialization/hydration, thêm database index chưa chắc cải thiện đáng kể.

### Bước 3 — Xác định đúng dạng bottleneck

- Nhiều JDBC spans → N+1/loop queries.
- Một SQL span rất chậm → plan/index/stats.
- Pool wait cao → transaction duration/pool/DB capacity.
- GC cao → entity graph/large result/allocations.
- High lock waits → concurrency/transaction conflict.
- High network bytes → over-fetch/wide rows.

### Bước 4 — Thay đổi tối thiểu có thể kiểm chứng

Thử DTO vs JOIN FETCH; thêm index; giảm collection join; tăng batch size; đổi keyset; xử lý pool/transaction scope. Không trộn giải pháp trước khi biết bottleneck.

### Bước 5 — Đo lại toàn endpoint và DB

Một optimization SQL có thể chuyển cost sang JVM mapping hoặc network. Xem end-to-end performance.

---

## 41. Không tối ưu sai kết quả dưới quyền hạn truy cập

Một query:

```jpql
select o
from SalesOrder o
where o.status = :status
```

có thể nhanh hơn query:

```jpql
select o
from SalesOrder o
where o.tenantId = :authorizedTenant
  and o.status = :status
```

nhưng nếu ứng dụng multi-tenant, query thứ nhất có thể trả dữ liệu không được phép. Không có improvement nào hợp lệ nếu bỏ security predicates.

### 41.1. Dataset phải có nhiều tenants

Nếu benchmark chỉ có một tenant, việc quên tenant predicate có thể không bị phát hiện. Seed ít nhất một vài tenants và assert isolation.

### 41.2. Cache keys cũng cần scope

L2/Redis/application cache phải có policy tenant isolation; performance test không được bỏ qua correctness của cache hit.

### 41.3. Không dùng production raw PII

Nếu cần distribution của email/phone/address lengths, có thể lấy aggregated histograms hoặc tạo synthetic values cùng length/selectivity, không sao chép raw values.

### 41.4. Test data retention

Các snapshots phải có lifecycle xóa/rotation/access controls. Benchmark artifacts/logs cũng có thể chứa sensitive metadata.

---

## 42. Dữ liệu thật, dữ liệu tổng hợp và dữ liệu giả lập

Có ba cách phổ biến:

| Cách | Ưu điểm | Nhược điểm/rủi ro |
|---|---|---|
| Synthetic data theo distribution | Dễ tái lập, ít rủi ro PII | Có thể không mô phỏng correlations |
| Anonymized production snapshot | Gần shape thực | Privacy/security, anonymization có thể làm sai distribution |
| Curated anonymized aggregates + generator | Kết hợp realism và kiểm soát | Cần thiết kế generator nghiêm túc |

### 42.1. Ẩn danh không phải chỉ thay tên

Nếu giữ nguyên customer IDs, timestamps và order patterns, dataset có thể vẫn có nguy cơ tái nhận diện. Tuân theo chính sách dữ liệu của tổ chức; loại fields nhạy cảm không cần thiết cho benchmark.

### 42.2. Bảo toàn thống kê cần thiết

Nếu benchmark index selectivity trên `tenant_id`, randomize tenant IDs có thể được nhưng **không phá tenant-size distribution**. Nếu benchmark search text, random ASCII có thể không thay thế collation/Unicode/token distributions thật.

### 42.3. Không đưa keys/secrets vào test fixtures

Dùng generated fake tokens/credentials. Không commit production connection URLs chứa password.

### 42.4. Synthetic seed là artifact có version

Ghi seed, generator version và dataset checksum/aggregate statistics để so sánh A/B trên cùng data.

---

## 43. Schema drift và môi trường đo

Ứng dụng production dùng migration V42, nhưng benchmark DB mới chỉ tới V39: query plans có thể khác vì V40 đã thêm index, V41 đổi column type và V42 partition table.

### 43.1. Ghi migration version

Ví dụ:

```text
Application commit: abc1234
Migrations: V1..V42
Database major version: PostgreSQL 16
Data generator version: 3
Seed: 20261115
```

### 43.2. Không benchmark trên Hibernate create-drop schema khi mục tiêu là production mapping

Auto-DDL có thể không tái tạo partial indexes, triggers, collation, partitioning hoặc các migration legacy constraints.

### 43.3. Kiểm tra indexes/constraints thực

Dùng DB catalog/introspection trên test database, không chỉ nhìn entity `@Index`/`@Column` annotations. Production migrations mới quyết định schema thực.

### 43.4. Cẩn thận rollback migrations

Một optimization dựa trên index mới nhưng release rollback app có thể vẫn còn index; thông thường index thêm không nguy hiểm, nhưng destructive schema changes cần expand/contract plan.

---

## 44. Đo dưới write workload và database maintenance

Một read-only benchmark trên bảng immutable có thể đẹp hơn production nhiều.

Production có thể có:

- Continuous INSERT/UPDATE.
- Dead tuples/bloat.
- Autovacuum.
- Checkpoints/WAL flush.
- Index page splits.
- Replication.
- Backups.
- Archival jobs.
- Maintenance tasks.

### 44.1. Mixed workload

Nếu production có 80% reads/20% writes, hãy có ít nhất một scenario phản ánh tỷ lệ tương ứng (sau khi đo read-only baseline để hiểu phần riêng).

### 44.2. Không phá production để mô phỏng bloat

Tạo môi trường test dedicated, seed và chạy controlled update/delete cycles nếu cần đánh giá bloat-related plans. Đừng thực hiện destructive “experiments” trên database khách hàng.

### 44.3. Đo commit latency

Các writes có thể nhanh ở statement execution nhưng commit chậm do WAL/fsync/replication settings. Chỉ đo `em.flush()` là chưa đủ.

### 44.4. Metrics theo trạng thái

Ghi database configuration, checkpoints, autovacuum activity và replica lag nếu chúng chi phối workload.

---

## 45. Benchmark read replicas: không chỉ đo SELECT

Nếu production đọc từ replica:

- Replica có network topology khác.
- Data lag sau primary commit.
- Query planner statistics có thể khác.
- Connection routing có thể quyết định endpoint nào dùng replica.
- Long-running reads có thể có conflict với replication cleanup tùy DB.

### 45.1. Không đánh giá tính đúng đắn chỉ bằng latency

Một replica response nhanh nhưng stale không đáp ứng use case “đọc ngay sau khi ghi” nếu contract yêu cầu read-your-writes.

### 45.2. Test topology thật khi cần

Nếu hệ thống dùng primary-write/replica-read, benchmark trên một local single DB chỉ mô phỏng query execution một phần.

### 45.3. Không dùng replica lag như một chi tiết bỏ qua

Endpoint reporting eventual consistency có thể chấp nhận lag, còn payment/order confirmation không chắc.

### 45.4. Pool per datasource

Read/write pools có size và capacity khác nhau, ảnh hưởng latency. Ghi riêng.

---

## 46. Khi nào được dùng H2 trong dự án JPA?

H2 vẫn hữu ích cho:

- Fast local smoke tests.
- Một số repository logic checks đơn giản không dựa dialect.
- Unit tests cho code độc lập database.
- Training examples khi production target chưa được chọn.

Nhưng đừng dùng H2 làm **bằng chứng cuối** cho:

- PostgreSQL-specific JSONB/native SQL.
- Sequence/identity pooling behavior.
- Locking/transaction isolation.
- SQL optimizer/index performance.
- Collation/case-insensitive searches.
- Pagination/fetch join behavior ở target dialect.
- Large data index selectivity.
- Production throughput/p95.

### 46.1. H2 compatibility mode

Giúp một số SQL syntax tương thích, không cam kết cùng planner/statistics/locking/transaction behavior.

### 46.2. Đặt test đúng mục đích

Tên test `OrderRepositorySmokeTest` trên H2 có thể hợp lý. Tên `PostgresOrderPerformanceTest` nhưng chạy H2 là gây hiểu lầm.

### 46.3. Một DB mục tiêu cụ thể tốt hơn mock khi đo persistence

Mock `EntityManager` chỉ có thể xác nhận method calls; nó không tạo SQL hay phản ánh optimizer behavior. Muốn đo JPA/database path, cần DB thật.

---

## 47. Performance regression tests trong CI

Có hai nhóm test:

**Nhóm ổn định, nên chạy thường xuyên:**

- Đúng result data, ordering, tenant scope.
- SQL count không tăng theo N.
- Không có pagination-over-collection-fetch.
- Query plan có index/predicate cần thiết trong vài critical cases (assert cẩn thận).
- Không có SELECT per row trong mapper.

**Nhóm cần môi trường ổn định hơn:**

- p95/p99 end-to-end.
- Throughput at concurrency 100.
- DB CPU/IO saturation.
- Soak test vài giờ.
- Large-scale export memory.

### 47.1. Tránh flaky timing assertions trên shared runners

Một assertion `assertTrue(durationMs < 20)` có thể fail do unrelated CI noise. Thay bằng query budget hoặc relative comparison trong dedicated performance environment.

### 47.2. Không assert exact SQL text quá cứng

Provider minor version có thể đổi aliases/format nhưng không đổi semantics. Nếu cần test query shape, dùng SQL recorder/AST/normalized fingerprint phù hợp.

### 47.3. Có giới hạn kỹ thuật nhưng không đánh đổi correctness

Một test “list 50 Orders dùng tối đa 3 SELECT” phải đồng thời assert đủ 50 Orders và đúng Customer name, để code không thể “tối ưu” bằng bỏ nested data.

### 47.4. Phát hiện thay đổi ngay từ PR

Khi một developer thêm `customer.country.name` vào response mapper, SQL count có thể tăng 50. Regression test data shape đa dạng sẽ bắt đúng kiểu lỗi này.

---

## 48. Mẫu protocol thực hành đầy đủ

Một đội muốn đánh giá tối ưu GET /orders:

### Bước 1 — Định nghĩa câu hỏi

```text
Mục tiêu:
  Trang Orders 50 rows, có Customer.name.
  Giảm N+1 mà giữ đúng kết quả/phân trang.
```

### Bước 2 — Xác định hệ mục tiêu

```text
PostgreSQL major version = cùng staging/production
JPA provider = Hibernate version của application
JDBC driver = version đang deploy
Java runtime = version đang deploy
```

### Bước 3 — Khởi tạo schema

Chạy migrations hiện hành. Kiểm tra indexes, constraints, collation, time zones và schema settings.

### Bước 4 — Sinh dữ liệu

Seed cố định, tối thiểu đủ Orders/Customers, có tenant skew và distinct Customers để lộ N+1.

### Bước 5 — Kiểm tra distributions

Count rows, per-tenant distribution, lines/Order p50/p95, statuses/time ranges.

### Bước 6 — Chạy ANALYZE

Đảm bảo optimizer statistics phù hợp trước khi đo query plans.

### Bước 7 — Xác định parameter set

Chọn tenant nhỏ/trung bình/lớn; PAID phổ biến/hiếm; page đầu/sâu.

### Bước 8 — Warmup

Ổn định JVM, JDBC pool, database caches và application state theo scenario. Ghi thời lượng/điều kiện.

### Bước 9 — Baseline

Chạy list entity+lazy mapping; đo SQL count, p50/p95/p99, DB metrics.

### Bước 10 — Candidate

Thay bằng DTO join projection; cùng dataset/params/load.

### Bước 11 — Repeat/A-B

Chạy nhiều windows, có thể alternating A/B để giảm cache/time drift.

### Bước 12 — Correctness

Assert same IDs/order, names, count semantics và authorized tenant.

### Bước 13 — Review query plans

Xem `EXPLAIN ANALYZE BUFFERS` cho generated SQL representative parameters.

### Bước 14 — Kết luận có điều kiện

Ghi improvement, regressions, resource trade-offs, limitation và kế hoạch production monitoring.

---

## 49. Mẫu báo cáo kỹ thuật nên lưu lại

```text
Title:
  GET /orders performance comparison

Code:
  commit abc1234
  Java 21, Hibernate X.Y, JDBC driver Z

Database:
  PostgreSQL 16.x
  schema migrations V1..V42
  indexes recorded
  ANALYZE completed

Dataset:
  generator v3, seed=20261115
  Orders=1,200,000; Lines=5,600,000
  top 10 tenants hold 55% of Orders
  p95 Lines/Order=14

Workload:
  50 Orders/page
  tenant-small, tenant-medium, tenant-hot
  concurrency=1,20,50
  10-min warmup, 15-min measurements
  5 repeated runs

Cache:
  L1 new EM/request
  L2 disabled during SQL-count test
  database buffer cache warm

Metrics:
  p50/p95/p99, throughput, errors
  SELECT count, rows, DB CPU/IO
  pool wait, GC pauses

Correctness:
  same IDs/order/tenant scope
  no missing Lines or duplicate roots

Limitations:
  single DB node, no production replica
  storage/network smaller than production

Decision:
  candidate accepted/rejected; reasons
  rollback/monitoring plan
```

Tất cả numbers là minh họa format; thay bằng measurement thực và ghi rõ environment.

---

## 50. Những sai lầm dễ gặp nhất

### 50.1. Kết luận từ 100 rows trên H2

Không phản ánh index selectivity, dialect và scale production.

### 50.2. Dùng cùng engine nhưng sai major version

Planner/SQL optimizer khác; phải pin/ghi version.

### 50.3. Dataset đủ lớn nhưng phân phối đều giả tạo

Không phát hiện hot tenants, selective queries và key skew.

### 50.4. Chỉ seed một Customer cho mọi Orders

L1 có thể che N+1.

### 50.5. Chỉ có một Line mỗi Order

Không phát hiện collection row explosion.

### 50.6. Không có soft-deleted/null/legacy data

Query filters/index predicates không được thử theo các trường hợp thật.

### 50.7. Chỉ test query với một tenant nhỏ

Không thấy plan/latency của tenant lớn.

### 50.8. Không dùng migrations production

Test schema khác constraints/indexes thực tế.

### 50.9. Không ANALYZE sau bulk seed

Optimizer estimates có thể sai.

### 50.10. Chỉ nhìn EXPLAIN estimated cost

Không so với actual rows/time/buffers.

### 50.11. Chạy EXPLAIN ANALYZE UPDATE trên production mà không biết nó ghi dữ liệu

Nguy hiểm; nó thực sự thực thi DML.

### 50.12. Tối ưu chỉ theo SQL count

Một giant fetch join có thể rất tốn memory/rows.

### 50.13. Tối ưu chỉ theo average latency

Bỏ qua p95/p99 và timeout spikes.

### 50.14. Không ghi throughput/error rate

Latency có thể giảm chỉ vì requests bị lỗi hoặc workload ít đi.

### 50.15. Đo một request tuần tự rồi suy ra concurrent capacity

Không thấy pool wait/lock contention.

### 50.16. So sánh A cold và B warm

Cache state làm kết quả không công bằng.

### 50.17. Không warmup JVM/pool

JIT/classloading/connection creation làm lệch timings.

### 50.18. Dùng một EntityManager cho hàng nghìn benchmark iterations

Đang đo L1 hits, không giống requests mới.

### 50.19. Bật L2 warm rồi kết luận N+1 không còn

Cold misses vẫn có thể tạo N+1.

### 50.20. Benchmark trên CI shared runners với threshold mili-giây cứng

Dễ flaky và ít đại diện.

### 50.21. Vừa thay index, fetch plan và pool size

Không biết thành phần nào tạo improvement.

### 50.22. Lưu dữ liệu production raw PII vào test repository

Vi phạm kiểm soát dữ liệu; cần synthetic/anonymized data được phép.

### 50.23. Quên tenant filter để query nhanh hơn

Performance không hợp lệ vì sai security/correctness.

### 50.24. Không assert result shape/order

Query nhanh có thể trả thiếu hoặc duplicate Orders.

### 50.25. Dùng batch JPA nhưng không đo commit

Chỉ flush pass không chứng minh transaction durability/latency.

### 50.26. Đổi IDENTITY sang SEQUENCE chỉ để đạt benchmark

Có thể ảnh hưởng migrations/ID semantics; cần quyết định kiến trúc riêng.

### 50.27. Chạy destructive load test trên DB chia sẻ

Gây locks/I/O/cost cho dịch vụ khác.

### 50.28. Tăng connection pool mà không đo DB saturation

Có thể làm p99 tệ hơn.

### 50.29. Bỏ qua network RTT

N+1 có thể ít tốn trên localhost nhưng rất tốn khi app và DB tách hosts.

### 50.30. Không đo long-tail Orders có nhiều Lines

Detail endpoint p99 có thể vẫn rất xấu.

### 50.31. Đo SQL gõ tay thay vì generated SQL

Aliases, casts, joins hoặc LIMIT từ ORM có thể khác.

### 50.32. Kết luận từ một run duy nhất

Noise/cache/drift có thể quyết định kết quả.

### 50.33. Chỉ nhìn success requests, loại timeout khỏi phân tích

Che lỗi dưới tải.

### 50.34. Không đo lock waits và retries

Transaction throughput thực bị đánh giá sai.

### 50.35. Không lưu benchmark metadata

Không tái lập được khi query lại chậm sau ba tháng.

---

## 51. Bài tập thực hành

### Bài 1 — H2 vs production

Một repository query mất 1 ms trên H2 với 300 Orders. Có thể cam kết PostgreSQL production cũng < 1 ms không?

**Gợi ý:** Không. Engine, planner, data scale, network, load và caching khác.

### Bài 2 — Cùng số rows

Hai datasets đều 1 triệu Orders, nhưng dataset A có một Customer cho tất cả Orders, B có 500.000 Customers. N+1 đo được có thể khác không?

**Đáp án:** Có, vì L1/L2 cache reuse và số distinct keys khác.

### Bài 3 — Tenant skew

Số Orders per tenant phân phối rất không đều. Benchmark nên chọn những tenant nào?

**Gợi ý:** Small/median/hot tenants, không chỉ một tenant trung bình.

### Bài 4 — Child distribution

Trung bình 4 Lines/Order nhưng p99 là 100 Lines. Vì sao đo only average là không đủ?

**Gợi ý:** Tail requests và join row explosion.

### Bài 5 — Default database

Production dùng PostgreSQL 16 nhưng tests dùng H2 PostgreSQL mode. Những phép đo nào không nên suy ra?

**Gợi ý:** Locking, optimizer/index, SQL dialect, plan, performance p95.

### Bài 6 — Schema version

Test DB dùng Flyway V39, production V42 thêm index. Kết luận query chưa có index có hợp lệ không?

**Đáp án:** Không đại diện schema production.

### Bài 7 — Statistics

Sau import 5 triệu rows, planner vẫn ước lượng vài nghìn rows. Nên kiểm tra gì?

**Gợi ý:** ANALYZE/stats freshness/selectivity.

### Bài 8 — Param skew

Query `tenant_id=:tenant` chạy nhanh với tenant-small nhưng chậm với tenant-hot.

**Gợi ý:** Đo plans/estimates/selectivity và prepared-plan behavior cho cả hai.

### Bài 9 — Count vs page

GET /orders có 1 SELECT page và 1 COUNT toàn bộ. Tối ưu page làm p95 vẫn cao.

**Gợi ý:** Đo cả count; nếu UX chỉ cần hasNext cân nhắc Slice/cursor.

### Bài 10 — EXPLAIN

`Seq Scan` có luôn là dấu hiệu phải tạo index không?

**Đáp án:** Không; có thể tốt khi bảng nhỏ hoặc scan tỷ lệ lớn.

### Bài 11 — EXPLAIN ANALYZE

Dùng `EXPLAIN ANALYZE DELETE ...` có thực sự DELETE không?

**Đáp án:** Có, nó thực thi DML; cần môi trường/rollback an toàn.

### Bài 12 — Actual vs estimate

Optimizer dự đoán 100 rows nhưng thực tế 500.000.

**Gợi ý:** Kiểm tra stats, correlated predicates, distributions, query plan.

### Bài 13 — Buffers

Query có 100% shared-buffer hits nhưng API vẫn chậm.

**Gợi ý:** Network, SQL count, locks, ORM mapping, CPU, pool wait.

### Bài 14 — Network N+1

50 secondary queries và 3 ms RTT/query. Phần network round-trip có thể đóng góp tối thiểu cỡ bao nhiêu trong tình huống lý tưởng tuần tự?

**Đáp án:** Khoảng 150 ms, chưa kể DB/JVM execution.

### Bài 15 — Warmup

A đo ngay sau startup, B đo sau 15 phút. So sánh công bằng không?

**Gợi ý:** Không, JIT/pool/caches chưa được kiểm soát.

### Bài 16 — L1 cache

Benchmark 1.000 `find` cùng ID trong một EM. Điều gì đang được đo nhiều nhất?

**Gợi ý:** L1 cache identity map sau lần đầu.

### Bài 17 — L2 cache

L2 warm làm SQL count giảm. Đã chứng minh không có N+1 structure chưa?

**Đáp án:** Chưa; thử cold/miss scenarios.

### Bài 18 — SQL count

Candidate có 1 query nhưng trả 200.000 joined rows, baseline 3 queries tổng 1.000 rows. Chọn theo gì?

**Gợi ý:** Đo end-to-end latency, bytes, memory, CPU, correctness.

### Bài 19 — p99

Một số Orders có 5.000 Lines. Metric nào dễ phát hiện nhất?

**Gợi ý:** Tail latency p95/p99, distribution/GC/rows.

### Bài 20 — Throughput

Tăng concurrency từ 50 lên 200 nhưng throughput không tăng, latency tăng.

**Gợi ý:** Hệ thống đang bão hòa/contended; xem CPU/IO/pool/locks.

### Bài 21 — Pool size

Pool 10, 100 concurrent requests. Vì sao query server 2 ms nhưng HTTP p95 300 ms?

**Gợi ý:** Pool acquisition queue, transactions dài, network và app work.

### Bài 22 — HikariCP

Tăng pool size 10→100 có chắc tăng throughput không?

**Đáp án:** Không; DB saturation có thể gây regressions.

### Bài 23 — Pagination

OFFSET 0 rất nhanh, OFFSET 500000 chậm. Hướng nào nên thử?

**Gợi ý:** Keyset/cursor và composite index theo sort.

### Bài 24 — Pagination correctness

JOIN FETCH Lines + `setMaxResults(20)`: vấn đề gì?

**Gợi ý:** Limit theo SQL rows khác limit theo distinct Orders; provider có thể paginate in memory.

### Bài 25 — Two-step

Cách page 50 Orders và load Lines tránh N+1?

**Gợi ý:** Page IDs rồi fetch children theo bounded IDs, ghép DTO/restore ordering.

### Bài 26 — Data consistency

Hai-step read ở READ COMMITTED có thể thấy hai snapshots khác nhau không?

**Đáp án:** Có, tùy concurrent transactions/DB semantics.

### Bài 27 — Batch insert

Test throughput JPA insert với IDENTITY và SEQUENCE. Cần kiểm soát biến nào?

**Gợi ý:** Same schema/constraints, generator config, batch size, transaction sizes, correctness.

### Bài 28 — Flush vs commit

Đo `em.flush()` 5 ms rồi nói transaction complete 5 ms được không?

**Đáp án:** Không; commit may add WAL/durability/lock costs.

### Bài 29 — Optimistic conflict

20% concurrent updates gặp `OptimisticLockException`. Có nên loại chúng khỏi latency/business throughput?

**Gợi ý:** Không; đo error/retry rate và successful operation latency gồm retries theo contract.

### Bài 30 — Testcontainers

Dùng PostgreSQL Testcontainers cùng major version có đủ chứng minh production SLA chưa?

**Đáp án:** Không; hardware/network/load khác.

### Bài 31 — Query plan SQL

Đã EXPLAIN SQL viết tay nhưng Hibernate generated SQL có thêm JOIN/ORDER BY. Kết luận plan có chắc đúng không?

**Gợi ý:** Không; đo generated SQL/bind shapes thực.

### Bài 32 — Index

Một index mới làm list query nhanh hơn nhưng writes chậm hơn. Cần làm gì?

**Gợi ý:** Benchmark query mix và resource cost, không tối ưu chỉ read path.

### Bài 33 — Anonymization

Có được copy raw customer emails vào benchmark fixtures không?

**Đáp án:** Không khi chưa có quyền/policy; dùng synthetic/anonymized distribution.

### Bài 34 — Cold vs warm

“Cold cache” có thể chỉ những lớp nào?

**Gợi ý:** L1, L2, app cache, DB shared buffers, JVM/pool. Phải nói rõ.

### Bài 35 — CI threshold

`assertTrue(apiTimeMs < 10)` trên shared runner thỉnh thoảng fail. Tốt hơn là gì?

**Gợi ý:** SQL-count/correctness regression tests, dedicated performance environment, relative comparisons.

### Bài 36 — Query count regression

Trước khi thêm field response 1 SELECT; sau thêm `customer.country.name` thành 51 SELECT.

**Gợi ý:** Mapper N+1; thêm projection/graph và regression test 50 distinct relations.

### Bài 37 — Export

Xuất 1 triệu Orders bằng `findAll()` khiến OOM dù SQL nhanh.

**Gợi ý:** Chunked DTO projections, streaming, cursor/keyset, memory/transaction monitoring.

### Bài 38 — Monitoring

Production p95 tăng, DB execution time không đổi, pool wait tăng.

**Gợi ý:** Điều tra connection pool/transaction duration hơn là đổi index.

### Bài 39 — Environment report

Benchmark thiếu Java/DB/provider versions và dataset seed. Vấn đề gì?

**Gợi ý:** Không thể tái lập hoặc phân biệt nguyên nhân performance change.

### Bài 40 — Chọn quyết định

A có 2 SELECT, p95 80 ms, đúng dữ liệu; B 1 SELECT, p95 120 ms, memory cao, đúng dữ liệu.

**Đáp án:** Không mặc định B tốt hơn vì ít queries. Cần chọn theo SLO/resource và các workloads liên quan.

---

## 52. Checklist trước khi tin một kết quả hiệu năng

- [ ] Đã mô tả use case và expected response/write contract.
- [ ] Có baseline và hypothesis rõ.
- [ ] Có SLO hoặc budget cần kiểm chứng.
- [ ] Dùng cùng database engine với môi trường đích.
- [ ] Đã ghi major/minor version, dialect, extensions/collation nếu liên quan.
- [ ] Schema được tạo bằng migrations thực.
- [ ] Indexes, FK/UNIQUE/CHECK, partitioning khớp.
- [ ] Đã xác nhận statistics/ANALYZE sau seed.
- [ ] Data volume đủ cho câu hỏi hiệu năng đang kiểm tra.
- [ ] Có phân phối hot tenants/status/time ranges, NULL/soft-delete.
- [ ] Có phân phối child collections p50/p95/max.
- [ ] Dataset có seed/version và thống kê aggregate để tái tạo.
- [ ] Không sử dụng dữ liệu production nhạy cảm trái phép.
- [ ] Query parameters đại diện cho common và edge workloads.
- [ ] Đã đo đúng generated SQL/dialect, không chỉ SQL viết tay.
- [ ] Có sample query plans với estimates và actual rows.
- [ ] Đã phân biệt cold/warm L1/L2/app/database caches.
- [ ] Đã warmup JVM, DB, pool và ghi điều kiện warmup.
- [ ] Có các mức concurrency và request mix tương ứng.
- [ ] Có error/timeout/retry rates bên cạnh latency.
- [ ] Có p50/p95/p99, throughput và sample counts.
- [ ] Có JDBC SQL count và query duration/tracing.
- [ ] Có DB CPU/I/O/lock waits, pool wait, memory/GC metrics.
- [ ] Đo toàn endpoint và transaction commit khi cần.
- [ ] Query count reduction không làm tăng row multiplication quá mức.
- [ ] Test pagination/ordering/COUNT semantics đúng.
- [ ] Test authorization/tenant filter đầy đủ.
- [ ] Không so A cold với B warm.
- [ ] Thay một biến mỗi experiment khi cần giải thích nguyên nhân.
- [ ] Có repeated measurements và báo variance.
- [ ] Dedicated environment khi cần stable absolute timings.
- [ ] Không chạy destructive load tests trên production/shared DB.
- [ ] Có performance regression tests phù hợp với CI.
- [ ] Có báo cáo hạn chế của môi trường đo.
- [ ] Có production monitoring/canary/rollback strategy nếu triển khai tối ưu.

## 53. Bảng tra cứu nhanh

| Câu hỏi | Hướng tiếp cận |
|---|---|
| Test H2 có đủ đại diện PostgreSQL production? | Không cho planner/locking/latency claims |
| Test gần production bằng Java? | Testcontainers với engine/version phù hợp |
| Schema representative? | Versioned migrations + index/catalog check |
| Data representative? | Volume + distribution + skew + cardinality |
| Đặc biệt cần test N+1? | Distinct referenced IDs, cold L1, nhiều roots |
| Đặc biệt cần test join to-many? | p95/max children/parent, nhiều collections |
| Seed reproducibility? | Fixed seed + generator version + statistics |
| Sau bulk seed? | ANALYZE/update planner stats |
| Kiểm tra SQL plan PostgreSQL? | EXPLAIN, EXPLAIN (ANALYZE, BUFFERS) |
| EXPLAIN ANALYZE thực thi DML? | Có; cảnh báo dữ liệu và side effects |
| Dấu hiệu estimate sai? | Estimated rows khác actual rows lớn |
| SQL query-count metrics Hibernate? | SessionFactory Statistics |
| JPA standard có Hibernate Statistics không? | Không |
| Measure HTTP p99? | Latency histogram/load test/observability |
| Query count đủ đánh giá optimization? | Không, cần rows/bytes/CPU/memory |
| Khi nào đo commit? | Write transactions/batching/consistency |
| L1 cache làm gì? | Reuse managed entities trong EM |
| L2 cache làm gì? | Shared entity cache nếu bật |
| DB warm buffer cache? | Repeated pages có thể memory-resident |
| Tại sao cần warmup JVM? | JIT/classloading/pool/cache stabilization |
| Test concurrency ở đâu? | Dedicated perf/staging environment |
| Pool bottleneck? | Connection wait/pending/active metrics |
| OFFSET sâu? | Đo keyset/cursor + index |
| Nhiều JOIN to-many? | Xem Cartesian rows/GC, split queries |
| Dataset production raw? | Chỉ theo policy; ưu tiên sanitized/synthetic |
| Stable CI tests? | SQL budgets/correctness, hạn chế hard timing |
| Tối ưu SQL nhưng endpoint vẫn chậm? | Profile pool/network/ORM/serialization |
| p95 đẹp, p99 tệ? | Large data tails, GC, locks, plan variability |
| DB đang nóng vì writes? | Mixed workload, I/O/WAL/lock metrics |
| Query hot tenant chậm? | Skew/correlations/index/parameter plans |
| Khi báo cáo kết quả? | Environment, dataset, workload, metrics, limits |
| Điều kiện thành công tối thiểu? | Correctness + performance + security |

## 54. Tổng kết

Những nguyên tắc quan trọng nhất:

1. **Tối ưu JPA cần được đo trên tổ hợp dữ liệu và hệ quản trị đủ đại diện**, không chỉ trên database in-memory nhỏ.
2. **Dữ liệu lớn chưa đủ**: phân phối tenant, trạng thái, thời gian, số children và hot keys ảnh hưởng plan và N+1.
3. **Đúng engine/version/schema/indexes/statistics** là điều kiện để đánh giá SQL planner gần production.
4. **Testcontainers với DB mục tiêu rất hữu ích cho integration tests**, nhưng container trên laptop không tự đại diện hạ tầng production.
5. **Chỉ đo query count là chưa đủ**; cần p50/p95/p99, throughput, error rate, SQL rows/bytes, DB CPU/IO, pool wait và memory/GC.
6. **Cache state và JVM/pool warmup phải được mô tả rõ**, nếu không A/B comparison dễ bị lệch.
7. **EXPLAIN ANALYZE giúp đối chiếu estimates và actual execution**, nhưng với DML nó thực thi statement thật, cần môi trường an toàn.
8. **Đo đúng workload/concurrency**, không suy ra p99 dưới tải từ một lần gọi repository tuần tự.
9. **Đảm bảo correctness, pagination, authorization và transaction semantics** trước khi gọi một thay đổi là cải thiện.
10. **Batch writes phải đo cả commit và rollback behavior**, không chỉ thời gian `persist`/`flush`.
11. **So sánh có kiểm soát và đo lặp lại** để tránh kết luận từ cache, noise hoặc workload drift.
12. **Data privacy và operational safety là một phần của benchmark design**; không copy PII hoặc stress database production tùy tiện.
13. **Báo cáo đầy đủ environment, dataset, workload và giới hạn suy luận** làm cho kết quả có thể kiểm chứng và tái lập.
14. **Performance regression tests nên kết hợp SQL-budget/correctness checks thường xuyên với representative-scale load tests định kỳ**.

**Kết luận:** Đo hiệu năng JPA có giá trị khi kết quả trả lời được câu hỏi thực tế về hệ thống sẽ triển khai: truy vấn chạy trên đúng loại database, với schema và dữ liệu đủ giống production, ở mức tải có ý nghĩa, đồng thời vẫn trả kết quả chính xác. Khi thiết kế workload khoa học, kiểm soát cache và môi trường, đọc query plans, đo toàn bộ transaction/API và lặp lại A/B experiments, bạn có thể lựa chọn fetch plan, projection, index, batching hay pagination dựa trên bằng chứng thay vì các “mẹo tối ưu” chỉ hiệu quả trên một database thử nghiệm quá đơn giản.

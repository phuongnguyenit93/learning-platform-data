# Phân biệt chậm do ORM, mạng, bộ kết nối hay cơ sở dữ liệu

Một endpoint Spring Boot dùng Hibernate trả về HTTP 200 nhưng mất 4 giây. Khi nhìn log, ta thấy câu `SELECT` chỉ mất 30 ms trong database. Có thể kết luận Hibernate chậm? Chưa chắc. Có thể request đã **chờ connection trong pool 3 giây**, mất thêm thời gian tải dữ liệu qua mạng, hoặc Java mất thời gian hydrate hàng chục nghìn entity. Ngược lại, nếu Hibernate log ghi 200 câu SELECT, một database chạy mỗi câu rất nhanh vẫn có thể làm endpoint chậm do tổng round-trips.

Vì thế, câu hỏi **“ORM chậm hay database chậm?”** không nên được trả lời bằng cảm giác hay chỉ một log. Cần đặt mốc đo ở **đúng ranh giới của từng tầng**:

- **ORM/application:** chuẩn bị query, dirty checking, flush, lazy loading, chuyển đổi `ResultSet` thành entities/DTO, serialization.
- **Connection pool:** đợi lấy connection, khởi tạo connection mới, thời gian giữ connection, pool saturation.
- **Network/protocol:** DNS/TCP/TLS khi kết nối mới, round-trip latency, truyền kết quả, proxy/load balancer và lỗi mạng.
- **Database:** parse/plan, execution, index/table scan, lock wait, disk I/O, CPU, temp spills, transaction commit/WAL.
- **Tầng ngoài:** HTTP queue, executor queue, GC pause, downstream calls, response serialization.

Bài thuộc chương **Quan sát và chẩn đoán** của Hibernate/JPA, trình bày cách tách nguyên nhân, dựng bộ đo theo request/SQL/transaction, đọc Hibernate Statistics, HikariCP metrics và database execution plans, rồi chứng minh giả thuyết bằng thí nghiệm có kiểm soát. Những ví dụ PostgreSQL và Spring Boot chỉ mang tính đại diện; khi dùng database/driver/Hibernate version khác cần đối chiếu công cụ tương đương.

---

## 1. Một request “chậm” đi qua những đâu?

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["Controller/service"]
    B --> C["Transaction/EntityManager"]
    C --> D["Lấy connection từ pool"]
    D --> E["Hibernate/JDBC chuẩn bị SQL"]
    E --> F["Network round-trip"]
    F --> G["Database: lock/plan/execute/IO"]
    G --> H["Truyền ResultSet"]
    H --> I["Hibernate hydrate entities/DTO"]
    I --> J["Service mapping/serialization"]
    J --> K["HTTP response"]
~~~

Đường đi thực tế có thể lặp lại nhiều lần: một request có 1, 20 hoặc 500 câu SQL; transaction có thể flush khi query được thực thi; connection có thể được giữ qua nhiều câu SQL hoặc được acquire/release theo handling mode.

### 1.1. Phân rã độ trễ có ý nghĩa

Với một lần query đơn giản, có thể hình dung:

\[
T_{\text{query observed}}
\approx
T_{\text{acquire}}
+ T_{\text{JDBC/ORM prep}}
+ T_{\text{round-trips}}
+ T_{\text{DB work/wait}}
+ T_{\text{result transfer}}
+ T_{\text{hydrate}}
\]

Nhưng đây là **mô hình tư duy**, không phải công thức cộng số đo một cách máy móc. Các timers có thể bao phủ nhau:

- Timer quanh `repository.findAll()` thường chứa cả acquisition, SQL, network, hydration.
- JDBC timer quanh `executeQuery()` có thể không chứa thời gian đọc hết `ResultSet`.
- Hibernate query metrics có cách đếm khác timer HTTP.
- Database `EXPLAIN ANALYZE` không tính toàn bộ Java mapping/HTTP serialization.
- Một trace có thể chứa các spans lồng nhau; tổng span durations dễ **đếm đôi**.

Cần xác định *start/end* của mỗi measurement trước khi so.

### 1.2. Ví dụ một timeline

~~~text
HTTP request: 1.300 ms
  0–45 ms     authentication + service logic
  45–845 ms   chờ lấy connection từ pool
  845–890 ms  JDBC/SQL + network + database
  890–1.180 ms Hibernate hydrate nhiều rows
  1.180–1.300 ms map DTO + JSON serialization
~~~

Nếu chỉ thấy database query 20 ms rồi kết luận “DB nhanh, Hibernate chắc chắn chậm”, ta bỏ qua **800 ms pool wait**. Trước tiên phải đo các tầng.

### 1.3. Tầng chậm và nguyên nhân gốc có thể khác nhau

Pool wait cao không có nghĩa cấu hình pool là nguyên nhân gốc. Database bị lock hoặc query chậm có thể khiến connection bị giữ lâu, làm pool hết connection và tăng wait.

~~~text
DB lock wait
   -> transaction giữ connection lâu
   -> pool active đạt max
   -> các request khác chờ acquisition
   -> p99 HTTP latency tăng
~~~

Nếu chỉ tăng `maximumPoolSize`, nhiều transaction hơn có thể vào DB và khiến lock contention nặng hơn. **Điểm chậm được quan sát** khác **nguyên nhân làm hệ thống chậm**.

## 2. Phân biệt latency, throughput, concurrency và saturation

Bốn khái niệm này liên quan nhưng khác nhau:

| Khái niệm | Ví dụ | Câu hỏi trả lời |
| --- | --- | --- |
| **Latency** | Request mất 1,2 giây | Mỗi công việc hoàn thành chậm tới mức nào? |
| **Throughput** | 800 requests/giây | Hệ thống xử lý được bao nhiêu việc trong một khoảng? |
| **Concurrency** | 150 requests đang chạy | Có bao nhiêu tác vụ đồng thời? |
| **Saturation** | Pool pending=40, active=max=20 | Resource đã quá tải/chờ đến mức nào? |

### 2.1. Percentiles quan trọng hơn average

~~~text
Trước incident:
  p50 = 70 ms
  p95 = 180 ms
  p99 = 350 ms

Trong incident:
  p50 = 72 ms
  p95 = 900 ms
  p99 = 5.200 ms
~~~

Average có thể chỉ tăng nhẹ nhưng 1% requests rất chậm. DB lock, GC, pool queue và network retransmission thường biểu hiện rõ ở tail latency.

Nên đo p50/p95/p99 theo endpoint/query shape và window, đồng thời ghi số mẫu. Một p99 từ 20 requests có giá trị thống kê hạn chế.

### 2.2. Throughput thấp không đồng nghĩa latency thấp

Một hệ thống có ít requests nhưng một query chạy 90 giây vẫn chậm. Ngược lại, tăng concurrency có thể đẩy throughput lên tới ngưỡng, sau đó saturation khiến p99 tăng dù throughput không tăng nữa.

### 2.3. Định luật Little như một phép kiểm tra sức chứa

Trong trạng thái ổn định, gần đúng:

\[
L = \lambda W
\]

Trong đó `L` là số tác vụ đang trong hệ thống, `λ` là tốc độ đến/hoàn thành, và `W` là thời gian ở hệ thống đó.

Ví dụ mỗi transaction giữ connection trung bình 100 ms, throughput khoảng 100 transactions/giây, số connections **đang được sử dụng trung bình** cần khoảng:

\[
100 \times 0.1 = 10
\]

Đây là phép tính mức tải trung bình, **không phải công thức chọn pool size chính xác**: còn burst, tail latency, transactions giữ connection nhiều lần, headroom và sức chịu đựng của DB.

## 3. Bảng nhận diện triệu chứng ban đầu

| Triệu chứng đo được | Nghi ngờ ưu tiên | Bằng chứng cần xem |
| --- | --- | --- |
| HTTP p99 cao, pool acquire p99 cao | Pool exhaustion/giữ connection lâu | Hikari active, idle, pending, usage; DB waits |
| Hibernate phát hàng trăm SELECT cho một request | N+1 hoặc lazy loading ngoài ý muốn | SQL count per request, stack, fetch plan |
| Một SQL statement rất chậm trên DB | Execution plan/IO/lock/CPU | `EXPLAIN`, `pg_stat_statements`, wait events |
| SQL trên DB nhanh nhưng ResultSet về app chậm | Network transfer hoặc quá nhiều rows | Bytes, result cardinality, JDBC fetch/hydration |
| Query count thấp, Java CPU/alloc cao | Hydration, mapping, JSON/GC | JFR, profiler, heap allocation |
| Chỉ chậm khi traffic tăng | Saturation, locks, pool/DB max | Concurrency, pending queue, DB active sessions |
| Chỉ chậm ở cold start | Connection creation/DNS/TLS/JIT/cache | Connection creation time, handshake, warm-up |
| Chỉ chậm khi gọi DB vùng xa | RTT/transfer | Network path, per-query latency, packet metrics |
| Flush/commit chậm, SELECT nhanh | Writes, locks, WAL, FK/index maintenance | Transaction spans, DB waits, storage metrics |
| Query nhanh ở dev, chậm ở prod | Data volume/stats/index/plan/config | Actual rows, `EXPLAIN ANALYZE`, environment diff |
| Thỉnh thoảng timeout lấy connection | Pool queue/leak hoặc downstream giữ transaction | Hikari timeout, pool usage, thread dumps |
| Chậm sau deploy thêm lazy properties | N+1 hoặc serialization | SQL per request, DTO mapping, entity graph |

Đây là **danh sách giả thuyết**, không phải kết luận. Cần tìm bằng chứng ở từng tầng, nhất là khi nhiều nguyên nhân kết hợp.

## 4. Tạo một bộ đo tối thiểu theo bốn ranh giới

Để phân biệt nguyên nhân, nên quan sát:

1. **HTTP/service duration:** bắt đầu khi nhận request đến lúc trả response.
2. **Connection acquisition duration:** từ khi code yêu cầu connection đến khi pool trả connection.
3. **JDBC execution/result processing duration:** thời gian driver thực thi SQL và ứng dụng đọc kết quả, với definition rõ.
4. **Database server duration/wait breakdown:** thời gian DB thực thi query, đợi lock, IO, CPU, commit.

Bổ sung:

- Số SQL statements mỗi request/transaction.
- Số rows trả về, bytes truyền, số entities/collections hydrated.
- Thời gian transaction giữ connection.
- Pool active/idle/pending và connection creation/timeout.
- JVM CPU, allocation rate, GC pauses.
- DB CPU, disk, IOPS, locks, temp spills và backend session count.

### 4.1. Một phép đo application-layer đơn giản

~~~java
long start = System.nanoTime();

try {
    List<OrderView> result =
        orderQueryService.findForOrganization(orgId);

    return result;
} finally {
    long elapsedNanos = System.nanoTime() - start;
    metrics.recordServiceElapsed(elapsedNanos);
}
~~~

`System.nanoTime()` phù hợp cho duration vì là đồng hồ đơn điệu; `Instant.now()`/wall clock thích hợp timestamp, không lý tưởng để tính duration khi hệ thống chỉnh giờ.

**Lưu ý:** Timer này bao quanh service operation và có thể chứa pool wait, SQL, network, mapping. Nó **không cô lập thời gian Hibernate**.

### 4.2. Định nghĩa đơn vị trước khi đối chiếu

| Metric | Đơn vị | Bao gồm |
| --- | --- | --- |
| `http.server.requests` duration | ms/s | HTTP handler tùy instrumentation |
| `hikaricp.connections.acquire` | ms/s | Pool acquisition |
| JDBC statement timer | ms/s | Theo driver/wrapper và khi nào ResultSet được đọc |
| DB mean_exec_time | ms | Server execution aggregate của normalized statement |
| `hikaricp.connections.usage` | ms/s | Thời gian ứng dụng giữ connection |
| ORM entity load count | entities | Số entity loads, không phải thời gian |
| Request SQL count | SQL executions | Số statements, không phải số queries nghiệp vụ |

Không được cộng tất cả cột duration một cách vô điều kiện; nhiều timers là parent/child.

## 5. Dựng distributed trace có cấu trúc

Một trace tốt có thể nhìn như:

~~~text
HTTP GET /orders                   1450 ms
  ├─ Auth                            25 ms
  ├─ OrderService.list             1390 ms
  │    ├─ Hikari acquire            920 ms
  │    ├─ SQL SELECT                 110 ms
  │    ├─ ORM hydration              210 ms
  │    └─ DTO mapping                 80 ms
  └─ JSON serialization              35 ms
~~~

Số liệu ví dụ chỉ để minh họa; spans có thể chồng lấn, nên tổng phần con không nhất thiết bằng span cha.

### 5.1. Trace context đi qua những đâu?

- HTTP inbound → service method.
- Transaction/job context.
- JDBC calls.
- External HTTP/gRPC.
- Async executor.
- Message producer/consumer.
- Background scheduler.

Nếu trace context không được truyền qua `@Async` hay queue, ta có thể thấy request nhanh nhưng job chậm trong một trace tách biệt. Cần propagation theo framework và security policy.

### 5.2. Trace IDs không phải tenant/security credentials

Nên gắn metadata tối thiểu:

~~~text
operation = listOrders
db.system = postgresql
db.operation = SELECT
query.fingerprint = ...
request.id = ...
organization.scope = ... (nếu policy cho phép)
~~~

Tránh đưa raw SQL bind values, password, JWT, email hoặc business PII vào spans. Tenant ID thường có cardinality cao; cách dùng traces/logs khác metrics labels.

### 5.3. Sampled traces chưa phản ánh toàn bộ p99

Sampling có thể bỏ lỡ requests hiếm mà rất chậm. Kết hợp histograms, logs chậm, error metrics, slow query traces và sampling policy phù hợp. Không dùng 1 trace thành công để bác bỏ incident mà p99 tăng liên tục.

## 6. Spring Boot/Micrometer: quan sát pool và HTTP

Ví dụ cấu hình định hướng:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        http.server.requests: true
spring:
  datasource:
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 20
      connection-timeout: 3000
~~~

Với Spring Boot Actuator, Micrometer và HikariCP được cấu hình hỗ trợ metrics, các metrics có thể được expose tùy phiên bản/naming registry.

**Đừng mở actuator metrics/prometheus cho internet công khai** mà không có quyền truy cập và chính sách bảo mật.

### 6.1. HikariCP metrics đáng chú ý

| Metric thường gặp | Type | Chẩn đoán |
| --- | --- | --- |
| `hikaricp.connections.active` | Gauge | Số connection đang được dùng |
| `hikaricp.connections.idle` | Gauge | Connections rỗi |
| `hikaricp.connections.pending` | Gauge | Threads đang chờ connection |
| `hikaricp.connections.max` | Gauge | Giới hạn pool |
| `hikaricp.connections.acquire` | Timer | Thời gian lấy connection từ pool |
| `hikaricp.connections.usage` | Timer | Thời gian connection được checkout |
| `hikaricp.connections.creation` | Timer | Thời gian tạo connection |
| `hikaricp.connections.timeout` | Counter | Số lần acquisition timeout |

Tên metric/units/tags có thể được registry chuyển đổi, ví dụ Prometheus dùng naming convention khác tên Micrometer gốc. Kiểm tra `/actuator/metrics` hoặc registry thực tế.

### 6.2. Chú ý cardinality của pool-name

Gắn pool-name vào metric là hữu ích nếu số pools nhỏ. Trong database-per-tenant với hàng nghìn pools, metric labels theo tên tenant có thể tạo cardinality rất lớn. Nên thiết kế cơ chế aggregation/observability riêng.

### 6.3. Hikari pending và active phải đọc cùng thời điểm

Một snapshot:

~~~text
active  = 20
idle    = 0
pending = 35
max     = 20
~~~

cho thấy pool đang bão hòa và có queue. Nhưng cần xem thêm **vì sao usage duration cao**: SQL lock, transaction dài, external call nằm trong transaction, connection leak hay pool size quá nhỏ so với mức tải hợp lý.

## 7. Hibernate Statistics: ORM làm bao nhiêu việc?

Trong Hibernate có thể bật Statistics cho giai đoạn chẩn đoán:

~~~properties
hibernate.generate_statistics=true
~~~

Hoặc Spring Boot:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
~~~

Một số phiên bản cho phép đọc:

~~~java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

Statistics s = sessionFactory.getStatistics();

long queries = s.getQueryExecutionCount();
long prepared = s.getPrepareStatementCount();
long entitiesLoaded = s.getEntityLoadCount();
long entityFetches = s.getEntityFetchCount();
long collectionsFetched = s.getCollectionFetchCount();
long flushes = s.getFlushCount();
long connectionsObtained = s.getConnectCount();
~~~

### 7.1. Statistics có phạm vi nào?

Những counters này thường tổng hợp theo `SessionFactory`, không tự động theo một HTTP request. Nếu 200 requests chạy đồng thời, delta counters trước/sau một request **bị nhiễu bởi các requests khác**.

Khi cần SQL count per request, dùng instrumentation gắn trace/request scope ở JDBC layer, hoặc integration test đơn luồng với kiểm soát concurrent traffic.

### 7.2. getQueryExecutionCount khác getPrepareStatementCount

- `getQueryExecutionCount()` liên quan số lần ORM query executions theo loại query/statistics API.
- `getPrepareStatementCount()` phản ánh prepared JDBC statement preparations.
- `getEntityLoadCount()`/`getEntityFetchCount()` phản ánh entity loads/fetches.
- `getCollectionFetchCount()` phản ánh collection fetches.

Các counters **không nhất thiết tăng 1:1** do persistence context, caching, prepared statement batching, native queries và Hibernate version. Đừng suy ngược “có 100 entity loads nên 100 SQL queries” nếu chưa kiểm tra.

### 7.3. Bật Statistics có chi phí

Statistics/logging chi tiết có overhead và phạm vi toàn SessionFactory. Trong production, dùng sampling, profiling window hoặc cấu hình observability đã được đo overhead. Không bật TRACE SQL/bind vô thời hạn chỉ để “chắc có dữ liệu”.

### 7.4. Slow query logging của Hibernate

Một số dòng Hibernate có slow SQL query logging settings/logger chuyên biệt; tên setting và khả năng đo phụ thuộc Hibernate version. Nếu dùng, xác nhận **chính xác measurement boundary** của logger: nó không tự đại diện toàn bộ HTTP request hoặc pool queue trước khi SQL được gửi.

## 8. Log SQL không phải log thời gian thực thi

Bật SQL log:

~~~yaml
logging:
  level:
    org.hibernate.SQL: DEBUG
    org.hibernate.orm.jdbc.bind: TRACE
~~~

có thể giúp phát hiện:

- SQL nào được phát.
- Thứ tự statement.
- N+1 queries.
- Unexpected flush/UPDATE.
- Truy vấn có tenant predicate hay không.

Nhưng:

- Một dòng SQL DEBUG **không tự có duration**.
- Bind TRACE có thể lộ password, access token, địa chỉ và thông tin cá nhân.
- Ghi log nhiều có thể làm hệ thống chậm, ảnh hưởng benchmark.
- SQL xuất hiện trong log không chứng minh transaction đã commit.

### 8.1. Muốn đo JDBC execution thì cần gì?

Có thể dùng:

- JDBC instrumentation của OpenTelemetry phù hợp driver/framework.
- DataSource proxy/wrapper có timers.
- Driver-level diagnostic được hỗ trợ.
- Sampling slow SQL logs với execution durations.
- Database-side statements statistics.

Cần rõ measurement time quanh `executeQuery()`, `executeUpdate()`, `ResultSet.next()` hay toàn transaction. Một proxy chỉ đo lệnh execute có thể **không tính thời gian fetch từng row** khi ResultSet được đọc lazy/streaming.

### 8.2. Cẩn thận với SQL normalization

Hai statements chỉ khác bind values:

~~~sql
SELECT * FROM orders WHERE id = 1;
SELECT * FROM orders WHERE id = 2;
~~~

nên thường được nhóm theo query fingerprint khi phân tích performance. Nhưng có thể có data skew: cùng fingerprint, giá trị bind khác nhau dẫn tới plan/rows khác. Khi điều tra, giữ **shape và một bộ tham số đại diện an toàn** thay vì chỉ so average fingerprint.

## 9. ORM chậm kiểu thứ nhất: N+1 queries

Entity:

~~~java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;
}
~~~

Code:

~~~java
List<PurchaseOrder> orders =
    em.createQuery("""
        select o from PurchaseOrder o
        order by o.id
        """, PurchaseOrder.class)
      .setMaxResults(100)
      .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(
        order.getCustomer().getDisplayName()
    );
}
~~~

Nếu mỗi order tham chiếu một Customer chưa có trong persistence context, Hibernate có thể chạy:

~~~text
1 SELECT orders
+ nhiều SELECT customer
= 1 + N queries
~~~

Trong thực tế số SELECT phụ thuộc số customer distinct, cache, batch fetching và entity state, nên **N+1 là mô hình**, không phải count chắc chắn trong mọi lần.

### 9.1. Vì sao DB nhìn từng query vẫn nhanh?

Giả sử 101 SQL statements, mỗi statement mất 2 ms trên DB, nhưng mỗi round-trip thêm 7 ms:

\[
101 \times (2 + 7) \approx 909\text{ ms}
\]

Không có câu SQL đơn lẻ nào “chậm”, nhưng tổng thời gian request gần một giây, chưa tính hydration.

Đây là **ORM query-shape problem tạo nhiều network round-trips**. Không phải chỉ là lỗi mạng; ORM đã tạo một pattern không phù hợp với RTT hiện tại.

### 9.2. Cách phát hiện

- Bật SQL count per request ở test/staging.
- Nhìn SQL lặp lại cùng shape với parameter khác.
- Kiểm tra trace có một span SELECT parent và nhiều spans SELECT child.
- Xem entity/collection fetch metrics.
- Đọc mapping `LAZY`/`EAGER` và chỗ DTO/serializer truy cập relations.

### 9.3. Sửa bằng JOIN FETCH có kiểm soát

~~~java
List<PurchaseOrder> orders =
    em.createQuery("""
        select o
        from PurchaseOrder o
        join fetch o.customer
        where o.tenantId = :tenantId
        order by o.id
        """, PurchaseOrder.class)
      .setParameter("tenantId", tenantId)
      .setMaxResults(100)
      .getResultList();
~~~

Với to-one `customer`, join fetch thường là ứng viên tốt khi cần Customer cùng Order. Nó có thể giảm round-trips.

### 9.4. Không JOIN FETCH mọi collection

Nếu một Order có 100 lines và 50 tags, join fetch hai to-many associations có thể tạo tích Descartes rất lớn, gây:

- Database đọc/trả nhiều rows hơn.
- Network transfer lớn.
- Hibernate deduplicate/hydrate nặng.
- Memory pressure.
- Pagination của root entities không như mong đợi.
- Một số mapping nhiều bag có thể gặp exception.

Giải pháp cần chọn fetch plan đúng với cardinality, không phải “bật EAGER mọi thứ”.

## 10. ORM chậm kiểu thứ hai: fetch quá nhiều dữ liệu

Một endpoint chỉ cần mã đơn và tổng tiền nhưng lại tải cả entity graph:

~~~java
List<PurchaseOrder> orders =
    repository.findAll();
~~~

Có thể Hibernate phải hydrate nhiều fields, collections và proxies rồi serializer chạm lazy relations.

### 10.1. DTO projection

Nếu UI chỉ cần summary:

~~~java
public record OrderSummary(
    Long id,
    String status,
    BigDecimal totalAmount
) {}
~~~

~~~java
List<OrderSummary> rows = em.createQuery("""
    select new com.example.api.OrderSummary(
        o.id, o.status, o.totalAmount
    )
    from PurchaseOrder o
    where o.tenantId = :tenantId
    order by o.id
    """, OrderSummary.class)
    .setParameter("tenantId", tenantId)
    .setMaxResults(50)
    .getResultList();
~~~

Projection thường giảm columns, hydration, lazy loading và JSON payload. Cần benchmark và nhớ nó không tự giải quyết một SQL plan chậm.

### 10.2. Phân trang và giới hạn rows

Không trả `findAll()` trên bảng có hàng triệu rows. Dùng pagination với thứ tự ổn định; với OFFSET rất sâu hoặc các quy trình streaming, cân nhắc keyset/seek pagination khi contract hỗ trợ.

### 10.3. Fetch size và streaming

JDBC fetch size có thể giúp driver đọc kết quả theo nhiều đợt thay vì nạp toàn bộ ngay; cách hoạt động phụ thuộc driver, autoCommit, cursor mode và database.

Với PostgreSQL JDBC, cursor-based fetching thường cần điều kiện transaction/autocommit phù hợp và fetch size dương; không chỉ gọi `setFetchSize(100)` rồi giả định mọi driver đều stream.

Nếu stream entities:

- Giữ transaction/session mở khi đang tiêu thụ stream.
- Đóng stream/ResultSet.
- Không share EntityManager giữa threads.
- Chú ý persistence context có thể vẫn tích lũy managed entities.
- Không để một HTTP client chậm giữ connection mở quá lâu nếu có thể xuất DTO/chunk phù hợp.

## 11. ORM chậm kiểu thứ ba: dirty checking và flush

Khi Hibernate quản lý nhiều entities, flush cần xác định thay đổi và thực thi SQL actions.

Ví dụ:

~~~java
@Transactional
public void importRows(List<ImportRow> items) {
    for (ImportRow item : items) {
        em.persist(toEntity(item));
    }

    em.flush();
}
~~~

Nếu persistence context giữ hàng trăm nghìn entities, memory và flush overhead có thể tăng. Hibernate còn có cascades, collection changes, listeners, optimistic locking và ordering.

### 11.1. Nhận biết flush chậm

- Service time cao quanh flush/commit.
- SQL statement count lớn, nhiều INSERT/UPDATE.
- Java allocation/CPU tăng.
- Hibernate flush metrics tăng.
- Entity/collection actions lớn.
- DB server SQL execution có thể nhanh nhưng tổng flush lâu do nhiều statements/round-trips.

### 11.2. Batch writing đúng cách

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
~~~

Và khi workload cho phép:

~~~java
for (int i = 0; i < items.size(); i++) {
    em.persist(toEntity(items.get(i)));

    if ((i + 1) % 50 == 0) {
        em.flush();
        em.clear();
    }
}

em.flush();
em.clear();
~~~

`flush()` đẩy SQL xuống DB, `clear()` detach entities. **Flush/clear không phải commit**; transaction boundary và idempotency vẫn phải thiết kế riêng. Với parent-child graph đang managed, clear có thể làm các references detached, cần hiểu lifecycle.

### 11.3. ID strategy ảnh hưởng batching

`GenerationType.IDENTITY` thường có thể hạn chế INSERT batching vì Hibernate cần lấy generated key từ INSERT. Sequence/allocation strategies có thể cải thiện trong một số database/version, nhưng phải benchmark và giữ semantics của ID.

### 11.4. Bulk HQL có thể nhanh hơn vòng lặp entity updates

Nếu chỉ cần đổi một trạng thái cho rất nhiều rows và không cần per-entity lifecycle semantics, bulk HQL/JDBC có thể giảm ORM overhead. Tuy nhiên nó có semantics khác về callbacks, persistence context, versioning, Envers và tenant filtering. Không thay bằng bulk SQL chỉ để tăng tốc nếu mất audit/concurrency invariants.

## 12. ORM chậm kiểu thứ tư: lazy loading trong JSON serialization

Controller trả entity trực tiếp:

~~~java
@GetMapping("/orders/{id}")
public PurchaseOrder getOrder(@PathVariable Long id) {
    return repository.findById(id).orElseThrow();
}
~~~

Serializer có thể gọi getters trên lazy relations. Hệ quả:

- N+1 queries xuất hiện **sau service method**, trong serialization.
- Nếu session đã đóng, có thể gặp `LazyInitializationException`.
- Nếu bật Open Session in View, SQL có thể chạy ngoài service transaction.
- HTTP duration tăng dù service timer nhỏ.
- Output JSON có thể lớn hoặc vòng lặp graph gây recursion.

### 12.1. Giải pháp

- Trả DTO thay vì expose JPA entities.
- Fetch đúng những relations cần trong service transaction.
- Tắt/lựa chọn OSIV có chủ đích; không dùng OSIV để che query plan.
- Đo cả response serialization, không chỉ repository method.

### 12.2. Vì sao pool metrics có thể lẫn?

OSIV giữ EntityManager trong request scope nhưng **không có nghĩa connection luôn được giữ suốt request**; connection acquisition/release phụ thuộc Hibernate connection handling/transaction. Cần đo actual connection usage, không suy từ việc OSIV bật.

## 13. Connection pool: thời gian acquire là gì?

HikariCP giữ một tập connections mở sẵn hoặc tạo dần. Khi app yêu cầu connection:

~~~java
Connection connection = dataSource.getConnection();
~~~

có thể:

- Lấy một idle connection nhanh.
- Chờ vì tất cả connections đang active.
- Cần tạo connection mới nếu pool chưa đủ size.
- Thất bại vì timeout hoặc DB/network không thể tạo connection.

### 13.1. Acquire wait khác query execution

Nếu timer quanh repository là 800 ms, còn `hikaricp.connections.acquire` p95 là 650 ms, khả năng lớn request đang chờ **pool**, không phải câu SQL đơn lẻ chạy 800 ms.

Nhưng pool wait có thể do DB queries giữ connection quá lâu; cần xem `usage` và DB waits đồng thời.

### 13.2. Cấu hình Hikari quan trọng

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 10
      connection-timeout: 3000
      validation-timeout: 1000
      idle-timeout: 600000
      max-lifetime: 1800000
~~~

Đây là ví dụ cấu hình, không phải giá trị tối ưu phổ quát. Mỗi tham số có điều kiện riêng:

- `maximum-pool-size`: số connections tối đa một pool.
- `minimum-idle`: mục tiêu số connections rỗi.
- `connection-timeout`: thời gian chờ tối đa khi lấy connection.
- `validation-timeout`: thời gian validation một connection.
- `idle-timeout`: cleanup connections rỗi khi phù hợp.
- `max-lifetime`: tuổi tối đa trước khi connection được retire theo lifecycle pool.

Một connection đang dùng không bị “giật” ra giữa transaction chỉ vì tới maxLifetime theo cơ chế pool bình thường.

### 13.3. Kết nối timeout không đồng nghĩa SQL timeout

Exception Hikari “Connection is not available, request timed out” thường liên quan **không lấy được connection từ pool**, không chứng minh câu SQL cụ thể chạy quá timeout.

Ngược lại, `statement_timeout` của DB hoặc JDBC query timeout liên quan **thời gian statement thực thi**. Cần phân biệt log/exception loại nào.

## 14. Vì sao pool có thể cạn?

Các nguyên nhân phổ biến:

1. Traffic/concurrency vượt sức chứa.
2. SQL chạy lâu hoặc lock wait.
3. Transaction chứa external HTTP call chậm.
4. Stream/ResultSet không đóng, giữ connection.
5. Connection leak (không close trong plain JDBC).
6. `@Transactional(REQUIRES_NEW)` lồng nhau cần thêm connections.
7. Quá nhiều application instances, mỗi instance có pool lớn.
8. DB chậm tạo connection hoặc từ chối connections.
9. Event-loop/executor threads bị block, không giải phóng resources kịp.
10. Connection được giữ qua các bước xử lý CPU/file I/O không cần DB.

### 14.1. Ví dụ giao dịch giữ connection qua HTTP call

~~~java
@Transactional
public void checkout(OrderRequest request) {
    orderRepository.save(toEntity(request));
    paymentGateway.capture(request); // HTTP call có thể mất vài giây
    auditRepository.save(toAudit(request));
}
~~~

Nếu transaction/connection đã được acquire trước HTTP call, nó có thể bị giữ trong lúc chờ gateway, làm tăng `hikaricp.connections.usage` và pool pressure.

Không phải mọi transaction luôn giữ physical connection từ đầu; cần đo thực tế. Nhưng **long-running external call trong transaction** vẫn là dấu hiệu cần review.

### 14.2. Tách external calls khỏi transaction một cách có thiết kế

Cần xác định atomicity và failure behavior, không đơn giản dời dòng HTTP ra ngoài rồi coi xong. Với payment/order cần saga, idempotency key, outbox hoặc workflow state machine thích hợp.

### 14.3. REQUIRES_NEW và pool pressure

Nếu outer transaction giữ connection A rồi inner transaction `REQUIRES_NEW` cần connection B, nhiều requests đồng thời có thể dẫn đến pool exhaustion. Cần sizing và kiến trúc tránh nested transactions tùy tiện.

## 15. Connection leak và leak detection

Một lỗi plain JDBC:

~~~java
Connection c = dataSource.getConnection();
// Không close trên mọi control path.
~~~

Cách an toàn:

~~~java
try (Connection c = dataSource.getConnection();
     PreparedStatement ps =
         c.prepareStatement("select 1");
     ResultSet rs = ps.executeQuery()) {

    if (rs.next()) {
        System.out.println(rs.getInt(1));
    }
}
~~~

Trong Spring-managed JPA/JDBC transaction, framework quản lý resource lifecycle. Không tự close Connection do transaction manager quản lý trừ khi API/contract yêu cầu.

### 15.1. Hikari leakDetectionThreshold

Có thể bật tạm:

~~~yaml
spring:
  datasource:
    hikari:
      leak-detection-threshold: 20000
~~~

Nếu connection bị checkout lâu hơn threshold, Hikari có thể log stack trace giúp điều tra. Nhưng:

- **Đây là cảnh báo giữ connection lâu, không chứng minh leak thật.**
- Một transaction hợp lệ dài cũng có thể bị cảnh báo.
- Ngưỡng quá thấp gây noise.
- Leak detection không tự thu hồi/đóng connection bị mất.
- Cần giới hạn/sampling và kiểm tra chi phí trong production.

### 15.2. Dấu hiệu leak thật

- Active tăng rồi không giảm khi traffic dừng.
- Pending tăng liên tục.
- Connections chỉ được giải phóng khi request/thread bị hủy.
- Stack traces lặp cùng nơi checkout.
- Không thấy connection release tương ứng.
- Cùng đoạn code lỗi làm pool hỏng qua thời gian.

Đừng đồng nhất mọi pool saturation với leak; một DB query 60 giây có thể giữ connection hợp lệ nhưng quá lâu.

## 16. Pool size: tăng thêm connection có giúp không?

Giả sử 5 app instances, mỗi instance `maximumPoolSize=40`:

~~~text
Max theoretical app connections = 5 × 40 = 200
~~~

DB còn có maintenance connections, monitoring, migrations và các apps khác. Nếu PostgreSQL `max_connections` thấp hơn tổng nhu cầu, có thể gặp lỗi tạo connection.

### 16.1. Pool lớn hơn không luôn tăng throughput

Quá nhiều active DB sessions có thể:

- Tăng context switching.
- Tranh chấp CPU/disk/cache.
- Tăng lock contention.
- Gây nhiều concurrent queries không có tài nguyên.
- Làm p99 tệ hơn.

Pool size nên được thử với **throughput và tail latency**, không chỉ xem connection-timeout giảm.

### 16.2. Thử nghiệm có kiểm soát

So sánh ví dụ:

~~~text
MaxPool = 10, 20, 30
Load = 100, 200, 300 rps

Đo:
  HTTP p95/p99
  pool pending, acquire p95
  pool usage p95
  DB active sessions
  DB CPU, lock waits, I/O
  error/timeout rate
~~~

Nếu tăng pool từ 10→20 giảm pending và DB vẫn dư tài nguyên, đó có thể là cải thiện. Nếu DB CPU đã 100%, tăng pool có thể tăng queue trong DB thay vì queue ở app.

## 17. Network latency: round-trip hay data transfer?

Có ít nhất ba thành phần mạng khác nhau:

1. **Kết nối mới:** DNS lookup, TCP handshake, TLS handshake, authentication.
2. **Mỗi round-trip SQL:** yêu cầu/response qua network, protocol overhead.
3. **Truyền kết quả lớn:** bytes transfer, bandwidth, packet loss/retransmission, nhiều fetch rounds.

### 17.1. RTT nhân với số queries

Giả sử database ở vùng khác, RTT trung bình 35 ms. Nếu Hibernate phát 100 queries tuần tự, chỉ latency tối thiểu của round-trips đã có thể rất lớn:

\[
100 \times 35\text{ ms} = 3.500\text{ ms}
\]

Nếu database thực thi mỗi query 1 ms, một slow-query log chỉ nhìn server execution sẽ không phát hiện “câu SQL chậm”. Nhưng sửa ORM N+1 hoặc colocate app–DB có thể tạo cải thiện đáng kể.

### 17.2. Data transfer khác RTT

Một SELECT trả 500.000 rows có thể có chỉ một SQL statement nhưng truyền nhiều MB. Chậm có thể do:

- Bandwidth thấp.
- Driver fetch/cursor settings.
- TLS encryption cost.
- ResultSet decoding.
- Hibernate hydration/GC.
- Serialization tiếp theo.

Không nên suy “1 SQL thôi nên ORM không liên quan”. ORM có thể đang tải quá nhiều entity/columns.

### 17.3. Connection creation riêng với acquire wait

Nếu pool rỗng và cần tạo connection, acquisition có thể bao gồm chi phí DNS/TCP/TLS/authentication. Hikari `creation` timer giúp phân biệt **tạo connection chậm** với **chờ idle connection vì pool full**.

Một số pool metrics không tách mọi substep chi tiết; cần network/driver logs và traces bổ sung.

## 18. Đo network như thế nào cho đúng?

Một phép thử mạng cần dùng **cùng application host/region/container network path** tới DB thật hoặc staging tương đương.

### 18.1. Không coi ping là SQL round-trip

ICMP ping có thể bị ưu tiên/blocked và không phản ánh TCP/TLS/proxy/database protocol. `ping=1ms` không đảm bảo JDBC query=1ms.

### 18.2. Đo các câu SQL nhẹ

Ví dụ:

~~~sql
SELECT 1;
~~~

Lặp lại qua một **connection đã được mở**, đo distribution latency của một statement đơn giản (có warm-up). Nếu `SELECT 1` rất chậm từ app host nhưng nhanh khi chạy gần DB, có thể nghi network/driver/proxy path. Tuy nhiên vẫn phải xét pool wait và JDBC overhead.

### 18.3. So hai môi trường

~~~text
A: psql/app client chạy gần DB
B: JDBC client chạy tại app host

Cùng SQL, cùng dữ liệu và bind values
So:
  server execution time
  client-observed elapsed time
  rows/bytes returned
  network RTT/retransmissions
  connection creation duration
~~~

Sự khác biệt còn có thể đến từ client protocol, prepared statements, result decoding và network; cần giữ kiểm soát biến số.

### 18.4. TLS/DNS và lạnh/nóng

Nếu chỉ request đầu tiên chậm:

- Pool warm-up và connection creation.
- DNS cache.
- TLS handshake/certificate validation.
- JIT/class loading.
- DB plan/data cache.

Nếu mọi SQL tuần tự đều chậm cùng khoảng RTT, xem per-statement network/protocol overhead và query count.

### 18.5. Packet loss thường tạo tail spikes

Mạng có packet loss hoặc retransmission có thể tạo p99 cao ngẫu nhiên. Thu thập TCP retransmits, connection resets và network telemetry nếu có quyền; tránh kết luận từ một lần traceroute.

## 19. Database chậm: tách execution, lock và I/O

Một câu SQL “chậm trong database” cũng có nhiều nguyên nhân:

~~~text
SQL server elapsed
  = parse/plan + scheduling/resource wait
  + lock wait
  + execution CPU
  + disk/cache IO wait
  + temp/sort spill
  + commit-related waits (khi transaction hoàn tất)
~~~

Các thành phần phụ thuộc DB, có thể chồng nhau và không luôn đo được riêng rẽ chỉ với một query log.

### 19.1. Kế hoạch truy vấn

Ví dụ:

~~~sql
SELECT id, status, created_at
FROM purchase_orders
WHERE organization_id = :org
  AND status = :status
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Một index ứng viên:

~~~sql
CREATE INDEX idx_orders_org_status_created_id
ON purchase_orders (
    organization_id,
    status,
    created_at DESC,
    id DESC
);
~~~

Không kết luận chắc index này tối ưu khi chưa biết predicate selectivity, data distribution, write cost và DB optimizer.

### 19.2. EXPLAIN ANALYZE

PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, created_at
FROM purchase_orders
WHERE organization_id = 'org-A'
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Đọc:

- Planned vs actual row counts.
- Index scan, bitmap scan, sequential scan.
- Loops/rows per loop.
- Sort và temp spill.
- Shared buffer hits/reads.
- Execution time.
- Filters and rows removed.
- Nested loops/cardinality explosion.

**`EXPLAIN ANALYZE` thực sự chạy statement.** Với UPDATE/DELETE/INSERT, nó có thể gây thay đổi dữ liệu; chỉ chạy trong điều kiện an toàn, thường ở staging hoặc một transaction test được rollback có kiểm soát (và hiểu các side effects không rollback như sequences/external calls).

### 19.3. EXPLAIN không tính mọi phần của client latency

PostgreSQL `EXPLAIN ANALYZE` thường không truyền toàn bộ ResultSet gốc về application, không hydrate Java entities và không JSON serialize. Một query trả triệu rows có thể thấy execution plan nhanh hơn client-observed processing nhiều lần.

Vì vậy “EXPLAIN 20 ms, endpoint 3 s” là **manh mối**, không tự chứng minh network là thủ phạm.

## 20. PostgreSQL pg_stat_statements

Khi extension được cài và cấu hình bởi DBA:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    LEFT(query, 160) AS sql_shape
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Tên cột phụ thuộc PostgreSQL/extension version. Đây là ví dụ PostgreSQL hiện đại; kiểm tra extension đã được enable và quyền đọc stats.

### 20.1. Total time khác mean time

Một query gọi 100.000 lần, mỗi lần 2 ms, có thể tiêu tốn tổng DB time lớn hơn một query hiếm khi chạy 500 ms.

Ưu tiên tối ưu tùy mục tiêu:

- Giảm total resource cost: xem `total_exec_time` × frequency.
- Giảm p99 cho endpoint: xem queries tham gia critical path, đặc biệt outliers.
- Giảm pool usage: xem transaction duration, không chỉ query mean.

### 20.2. Aggregate làm mất outlier details

`mean_exec_time` không phản ánh đầy đủ p99. Một query trung bình 10 ms nhưng vài lần bị lock 5 giây cần thêm slow query logs/wait events hoặc tracing. Dữ liệu aggregated còn trộn nhiều bind values/tenants.

### 20.3. Normalized SQL có thể che data skew

Cùng statement shape nhưng tenant lớn có 50 triệu orders còn tenant nhỏ 1000 orders. Nếu query plan dựa vào statistics chung hoặc generic prepared plans, hiệu năng có thể khác theo binds. Khi điều tra cần giữ thông tin workload/cấu trúc phân bố ở mức phù hợp mà không lộ dữ liệu nhạy cảm.

## 21. Database lock waits

Một câu UPDATE có thể chậm không phải vì thiếu index mà vì **đang đợi transaction khác**.

Ví dụ PostgreSQL:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    NOW() - query_start AS query_age,
    NOW() - xact_start AS transaction_age,
    pg_blocking_pids(pid) AS blocking_pids,
    LEFT(query, 160) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle';
~~~

Kết quả cần diễn giải cẩn thận: `query_start` là thời điểm bắt đầu query hiện hành/giữ trạng thái, `xact_start` là thời điểm bắt đầu transaction. Những giá trị có thể NULL; thông tin thấy được tùy quyền database.

### 21.1. wait_event_type = Lock

Nếu một backend có:

~~~text
state = active
wait_event_type = Lock
wait_event = transactionid
blocking_pids = {12345}
~~~

khả năng lớn query đang chờ lock do một transaction khác. Điều tra **blocker transaction** và hành vi nghiệp vụ gây giữ lock, không vội thêm index.

### 21.2. Idle in transaction

Một connection có:

~~~text
state = idle in transaction
transaction_age = 120 seconds
~~~

có thể đang giữ transaction mở dù không chạy SQL. Điều này có thể giữ locks/snapshots, ảnh hưởng vacuum hoặc blocker chain.

Điều tra application path:

- Transaction mở rồi gọi HTTP external service?
- Stream/iterator không đóng?
- Exception bị nuốt?
- Đang chờ user input?
- Batch job xử lý file trong transaction?
- Thread pool worker bị block?

### 21.3. Không tự động kill mọi session lâu

Terminate session có thể rollback business transactions và gây cascading retries. Với production incident cần quy trình vận hành, xác định blocker, owner, ảnh hưởng dữ liệu và phương án rollback/compensation phù hợp.

## 22. Disk I/O, buffer cache và sort spill

Một SQL chậm có thể bị giới hạn bởi:

- Table scan đọc nhiều pages.
- Random reads do index pattern không phù hợp.
- Sort/hash aggregation vượt `work_mem` (PostgreSQL) và spill ra temporary files.
- Storage throughput/IOPS.
- Cache cold sau restart hoặc dữ liệu mới.
- Bloat/statistics cũ.
- Index không tương thích filter/order.
- Join cardinality ước lượng sai.

### 22.1. Sequential scan không luôn là lỗi

Nếu truy vấn cần 80% table rows, sequential scan có thể tốt hơn index lookups. Đừng thấy `Seq Scan` trong EXPLAIN rồi kết luận phải tạo index.

### 22.2. Actual vs estimated rows

Nếu planner ước tính 100 rows nhưng thực tế trả 10 triệu rows, join order/strategy có thể sai. Cần kiểm tra statistics, data skew, predicates, parameterization và schema design.

### 22.3. Sort và pagination

~~~sql
SELECT *
FROM purchase_orders
ORDER BY created_at DESC
OFFSET 1000000 LIMIT 50;
~~~

OFFSET sâu có thể buộc database quét/bỏ qua nhiều rows. Keyset pagination với stable sort key thường đáng thử cho luồng duyệt dữ liệu lớn.

Nhưng muốn random access tới trang 2000 theo số trang, keyset có trade-off API; không thay mọi pagination bằng seek mà chưa xét yêu cầu sản phẩm.

## 23. Commit chậm: đừng chỉ đo SELECT

Một transaction gồm:

~~~java
@Transactional
public void transfer(...) {
    em.persist(...);
    em.flush();
    // Transaction manager commit sau khi method return.
}
~~~

Có thể:

- SQL UPDATE/INSERT nhanh.
- Commit chờ WAL fsync hoặc synchronous replication.
- Deferred constraint phát hiện lỗi lúc commit.
- Transaction holding locks gây blocking.
- Network response của COMMIT chậm/mất.

### 23.1. Flush khác commit

`em.flush()` gửi SQL nhưng không kết thúc transaction. Timer quanh `flush()` không tính đầy đủ commit cost. Với Spring proxy, commit thường xảy ra khi lời gọi transactional method kết thúc và interceptor xử lý completion.

### 23.2. Đo transaction boundary bên ngoài proxy

Ví dụ:

~~~java
long start = System.nanoTime();

try {
    transactionWorker.performBusinessOperation();
} finally {
    recordElapsed(System.nanoTime() - start);
}
~~~

Nếu `transactionWorker` là một Spring bean proxy độc lập và method `@Transactional` tạo local transaction, thời gian bao quanh invocation thường gồm commit/rollback của transaction đó. Nếu method join outer transaction, commit thực tế có thể diễn ra ở một boundary khác, nên timer không đại diện commit cuối cùng.

### 23.3. Commit-unknown không phải performance-only bug

Nếu network mất sau khi gửi COMMIT, caller có thể không biết DB đã commit hay rollback. Khi retry ghi, cần idempotency và reconciliation theo business key; không chạy lại mù quáng chỉ vì request timeout.

## 24. Java CPU, memory và GC là tầng thứ năm

Có trường hợp:

~~~text
DB execution:          15 ms
Connection acquisition: 2 ms
Request elapsed:     1600 ms
JVM CPU:              high
Allocations:          high
GC pauses:            repeated
~~~

Nghi ngờ:

- Hydrating hàng trăm nghìn entity/collections.
- Mapping DTO phức tạp.
- Sorting/filtering trong Java.
- JSON serialization graph lớn.
- Dữ liệu duplicate do join fetch cartesian product.
- GC pressure.
- ORM reflection/bytecode enhancement/proxy initialization.
- Regex/string transforms hoặc business CPU cost.

### 24.1. Java Flight Recorder (JFR)

JFR có thể giúp thấy:

- CPU hot methods.
- Object allocations.
- GC pauses/safepoints.
- Thread blocking/park.
- Socket read/write timing ở những event được hỗ trợ.
- JDBC instrumentation nếu tích hợp phù hợp.

JFR sampling/profiling có overhead; dùng configuration và retention phù hợp workload.

### 24.2. Flame graph

Nếu flame graph tập trung vào `org.hibernate.*` hydration code, entity mapping, Jackson hoặc application mapper, đó là bằng chứng mạnh hơn việc chỉ thấy Hibernate được gọi trong stack trace.

Nhưng nhiều CPU ở Hibernate có thể là **hậu quả của query trả quá nhiều rows**. Sửa SQL projection/cardinality thường tốt hơn chỉ tinh chỉnh JVM.

### 24.3. GC pause không tự do Hibernate

GC có thể do nhiều nguồn (HTTP JSON, logs, caches). Phải nối allocation profile và traces để xác định object graph nào gây áp lực.

## 25. Tập hợp instrumentation: một lớp chứng minh một điều

| Công cụ | Thấy tốt | Không đủ để kết luận |
| --- | --- | --- |
| HTTP Actuator metrics | Request p95/p99, throughput, errors | SQL nào chậm |
| OpenTelemetry traces | Critical path qua services/JDBC | DB IO/lock nếu thiếu server metrics |
| Hibernate Statistics | Entities/queries/flush/prepares | Per-request DB wall time chính xác |
| SQL DEBUG logs | Query shapes, N+1, ordering | Execution/commit duration |
| HikariCP metrics | Acquire, usage, pending, timeouts | Vì sao connections giữ lâu |
| JDBC proxy/instrumentation | Client-observed SQL execution | DB CPU/IO breakdown |
| pg_stat_statements | SQL shape frequency, total/mean server time | Tail outliers, Java hydration |
| EXPLAIN ANALYZE | Query plan, actual rows, buffer usage | Network transfer, Java mapping |
| pg_stat_activity/waits | Lock/session waits | Full business call graph |
| DB CPU/IO/WAL metrics | Resource saturation | Exact caller/ORM statement shape |
| JFR/profiler | Java CPU, allocations, blocking | DB plan details |
| Network telemetry | RTT, retransmits, connection resets | N+1/business query shape |
| Load tests | End-to-end behavior theo tải | Root cause nếu không có layer metrics |

Một hệ thống chẩn đoán tốt **kết hợp** các bằng chứng, thay vì chọn một công cụ và cố suy luận mọi tầng từ nó.

## 26. Một quy trình điều tra sự cố có thứ tự

### Bước 1 — Xác định triệu chứng

Ghi rõ:

- Endpoint/use case/job nào?
- p50/p95/p99 nào tăng?
- Bắt đầu lúc nào? Có deploy, index change, traffic spike?
- Ảnh hưởng mọi tenant hay chỉ một tenant?
- Chỉ đọc hay cả ghi?
- Có timeout/errors không?
- Có tương quan CPU/DB/connection metrics?

Không bắt đầu bằng “tăng pool lên 100” khi chưa biết triệu chứng.

### Bước 2 — Lấy trace cho một request chậm điển hình

Dựng timeline service, connection acquisition, JDBC, external calls, serialization.

### Bước 3 — Đếm statements và result sizes

Một request tạo 200 queries hay chỉ một query? Query trả 50 rows hay 500.000 rows?

### Bước 4 — Kiểm tra pool

`active / idle / pending / acquire p95 / usage p95 / timeouts`. Nếu pending cao, điều tra vì sao connections đang dùng lâu.

### Bước 5 — Kiểm tra database

Query top total time, per-query execution, lock waits, IO pressure và EXPLAIN trên representative binds.

### Bước 6 — Kiểm tra network/client

So server execution với client-observed duration, RTT, payload bytes, connection creation và ResultSet processing.

### Bước 7 — Kiểm tra JVM

JFR/profiler, allocations, GC, thread dumps, serialization, entity hydration.

### Bước 8 — Thử một giả thuyết mỗi lần

Ví dụ:

- Giảm 200 SELECT xuống 2 bằng fetch plan.
- Thay entity graph lớn bằng DTO projection.
- Tối ưu index phù hợp query.
- Rút transaction chứa HTTP external call.
- Thay đổi connection pool size sau khi DB capacity đã được xác minh.
- Đưa app–DB gần nhau hoặc giảm round-trips.

### Bước 9 — Đo trước/sau

So cùng workload, DB size, data distribution, concurrency, warm-up và metrics. Nếu p99 giảm nhưng DB CPU tăng 3 lần, vẫn phải đánh giá trade-off.

### Bước 10 — Lưu kết luận dựa trên bằng chứng

Một incident report nên ghi nguyên nhân gốc, contributing factors, changes, measurements, rollback và preventive alerts.

## 27. Tình huống A: N+1 dưới mạng RTT cao

Triệu chứng:

~~~text
Endpoint GET /orders
HTTP p95:             1.450 ms
Pool acquire p95:         2 ms
SQL statements/request: 152
DB mean per SELECT:       1.5 ms
App-to-DB RTT:            7 ms
Returned orders:        150
~~~

Giả thuyết: Hibernate lazy loading chạy nhiều câu SELECT tuần tự.

**Bằng chứng:** trace hiển thị 1 query order và nhiều query customer; SQL logs lặp cùng shape. Database mỗi query nhanh, pool không chờ.

**Hành động:** projection hoặc to-one fetch join/batch fetching, benchmark query count/rows và HTTP p95.

Sau sửa giả định:

~~~text
SQL statements/request:   2
HTTP p95:              180 ms
DB CPU:               tương đương hoặc thấp hơn
~~~

Không cần thêm index cho 150 truy vấn nhỏ nếu root cause là query multiplicity.

## 28. Tình huống B: chờ pool vì transaction quá dài

Triệu chứng:

~~~text
HTTP p99:              5.000 ms
Pool max:                  20
Active:                    20
Pending:                   45
Acquire p95:           3.200 ms
Connection usage p95:  2.800 ms
DB query mean:            30 ms
~~~

SQL server nhanh nhưng connections bị giữ lâu. Thread dump/trace cho thấy app gọi payment gateway 2 giây **bên trong transaction**.

**Root cause khả dĩ:** transaction scope kéo dài qua external I/O.

**Hành động:** thiết kế lại workflow/idempotency/outbox/saga để không giữ DB transaction trong lúc chờ HTTP; kiểm tra pool usage sau thay đổi. Tăng maximumPoolSize trước khi sửa workflow có thể làm nặng DB.

## 29. Tình huống C: pool wait do DB lock

Triệu chứng:

~~~text
Pool pending:              35
Connection usage p95:   4.500 ms
DB CPU:                    thấp
Many sessions:             waiting on Lock
One blocker:               idle in transaction
~~~

Pool chỉ là tầng chịu ảnh hưởng. Query đang chờ lock do transaction khác giữ.

**Hành động:** xác định blocker và business operation giữ transaction; rút transaction, xử lý lock order, đặt timeout phù hợp, đo retry. Không tăng connections nếu nó chỉ tạo nhiều blocked sessions.

## 30. Tình huống D: một query execution plan tệ

Triệu chứng:

~~~text
HTTP p95:               2.200 ms
Pool acquire p95:          1 ms
SQL statements/request:    1
DB execution:           1.900 ms
Result rows:                50
~~~

`EXPLAIN ANALYZE` cho thấy scan rất nhiều rows và external sort trước LIMIT, hoặc join estimate sai.

**Hành động:** kiểm tra query predicates, composite index, statistics, join strategy, data skew và plan cache behavior. Với tenant + status + sort, index bắt đầu bằng tenant/status có thể là ứng viên; xác minh bằng EXPLAIN thực tế.

Không sửa bằng “Hibernate lazy=true” khi chỉ một SQL đã tốn 1.900 ms ở database.

## 31. Tình huống E: network và ResultSet lớn

Triệu chứng:

~~~text
HTTP p95:               3.500 ms
Pool acquire:              2 ms
SQL count:                 1
DB execution:             70 ms
Rows returned:       250.000
App-to-DB bytes:      lớn
Java hydration:      nhiều CPU/allocations
~~~

Root cause không đơn thuần là “mạng chậm”, mà là **truyền/hydrate quá nhiều dữ liệu so với nhu cầu**.

**Hành động:** LIMIT/pagination, DTO projection, chọn ít columns, stream/fetch-size phù hợp, giảm graph; chỉ sau đó mới xem network bandwidth.

## 32. Tình huống F: cold connection creation

Triệu chứng:

~~~text
Request đầu sau scale-up: 1.200 ms
Requests sau:                70 ms
Pool creation p95:          900 ms
Pool pending:                 0 khi ổn định
DB execution:                10 ms
~~~

Nghi ngờ DNS/TLS/authentication/DB connection startup hoặc pool warm-up. Cần đo trên app host, xem creation metrics, DNS failures và số connections mở khi autoscale. Có thể điều chỉnh pre-warm/minimumIdle/connection lifecycle nếu hợp lý.

Không dùng tăng timeout vô hạn như cách che connection handshake issues.

## 33. Tình huống G: nhiều schema/tenant pools

Hệ thống database-per-tenant có 300 tenants, mỗi tenant một pool với maximum 10.

~~~text
300 × 10 = 3.000 potential connections
~~~

Nếu các pools mở gần mức tối đa, DB/cluster có thể quá tải dù từng tenant traffic nhỏ.

Giải pháp có thể là:

- Pool per active tenant có eviction/lifecycle đúng.
- Giới hạn tổng connections trên mỗi cluster.
- Shared pool/routing strategy khi mô hình cho phép.
- Connection proxy/pooling layer với hiểu biết transaction semantics.
- Concurrency limit theo tenant.
- Theo dõi hot-tenant vs cold-tenant demand.

**Pool sizing trong multi-tenant deployment là bài toán tổng sức chứa**, không chỉ cấu hình một Hikari pool.

## 34. Tình huống H: commit chậm vì WAL/replication

Triệu chứng:

~~~text
INSERT/UPDATE execution:     40 ms
Transaction completion:     600 ms
Pool acquire:                 1 ms
DB wait:                   WAL/synchronous replication
~~~

Có thể transaction đang đợi durable commit hoặc synchronous replica acknowledgment. Cần kiểm tra DB commit-related waits, storage I/O và replication health, cùng transaction sizes.

Không gọi `flush()` thêm nhiều lần để “đẩy nhanh commit”; flush tạo SQL work khác, không giải quyết storage/replication bottleneck.

## 35. Các anti-pattern khi chẩn đoán

| Anti-pattern | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Thấy Hibernate trong stack trace rồi đổ lỗi ORM | Mọi JPA call đều đi qua Hibernate | Đo SQL count, hydrate, DB time, pool wait |
| Thấy SQL DEBUG rồi suy statement nhanh/chậm | DEBUG thường không có duration | JDBC timers + DB metrics |
| Chỉ xem average | p99 có thể cực tệ | Histograms và tail traces |
| Cộng mọi span duration | Spans có thể lồng/overlap | Đọc critical path và timing boundaries |
| Query nhanh trong psql nên DB chắc chắn không vấn đề | Binds, cache, network, concurrency khác | So cùng workload/binds/host |
| EXPLAIN ANALYZE trực tiếp UPDATE prod | Nó thực sự thực thi DML | Staging/transaction rollback có kiểm soát |
| Mọi Seq Scan đều xấu | Quét tuần tự có thể tối ưu | Dựa vào cardinality/plan |
| Hikari pending cao → tăng pool ngay | DB lock/long transaction có thể là gốc | Xem usage và DB waits |
| Hikari leak warning → memory leak chắc chắn | Chỉ báo checkout quá lâu | Kiểm tra release paths/stacks |
| SQL server 10 ms → client phải ~10 ms | Round-trip, transfer, hydration | Đo các lớp riêng |
| “Một query” thì ORM không liên quan | Một query có thể hydrate triệu rows | Projection/fetch/pagination |
| EAGER/JOIN FETCH tất cả | Cartesian product và memory | Fetch plan theo use case |
| Streaming giữ transaction suốt HTTP response | Giữ connection lâu, khó cleanup | Chunked processing với lifecycle rõ |
| Dùng pool quá lớn | Nhiều concurrent DB sessions làm chậm | Capacity testing |
| Tối ưu index mà không đọc plan | Có thể sai index/write overhead | EXPLAIN/ANALYZE có kiểm soát |
| Bật bind TRACE production | Lộ dữ liệu, log overhead | Sampling/redaction |
| Chỉ theo dõi DB CPU | Lock waits có thể CPU thấp | Wait events, blockers |
| Test chỉ chạy H2/in-memory | Plan/locks khác production | Testcontainers/DB gần production |
| Chỉ đếm số SQL khi có cache | Cache làm số đo thay đổi | Kiểm soát cache state |
| Đổi nhiều biến cùng lúc | Không biết thay đổi nào hiệu quả | Controlled experiments |

## 36. Thiết kế benchmark có thể lặp lại

Một benchmark có ý nghĩa cần ghi:

- Git commit/ứng dụng/Hibernate version.
- Database version/dialect/driver.
- Schema/indexes và thống kê DB.
- Dataset size/data distribution.
- Ratio reads/writes, hot keys, tenant skew.
- Concurrent users, rate và ramp-up.
- Connection pool settings và instance counts.
- Cache warm/cold, plan warm-up.
- Network topology/RTT.
- Query binds representative.
- HTTP p50/p95/p99, errors.
- Pool acquisition/usage/creation.
- Server execution/locks/IO.
- JVM allocation/GC/CPU.

### 36.1. Không benchmark không có warm-up

JIT, connection pool creation, statement cache, DB buffer cache và TLS sessions thay đổi nhiều giữa cold run và steady-state. Tách cold-start latency và steady-state latency.

### 36.2. Không dùng throughput “attempted” làm success

Nếu request timeout nhưng DB đã commit, hoặc retry gây duplicate, throughput logic cần tính các **business outcomes được xác nhận**. Với job ghi, latency và correctness phải được đo cùng nhau.

### 36.3. Kiểm soát tải generator

Load generator cũng có thể trở thành bottleneck (CPU, network, connection limit). Theo dõi generator resource usage và tránh kết luận app đã bão hòa khi nguồn phát không đủ.

### 36.4. So sánh bằng confidence/biến động

Chạy nhiều lần, báo percentiles và độ biến thiên. Một lần p95 giảm 10 ms có thể nằm trong noise nếu environment không ổn định.

## 37. Checklist quan sát tối thiểu cho Spring Boot + Hibernate

- [ ] Có HTTP response latency histogram, throughput, error rate.
- [ ] Có trace ID giữa HTTP, service, JDBC và downstream.
- [ ] Biết số SQL statements theo request/transaction ở môi trường đo phù hợp.
- [ ] Có Hibernate entity/collection fetch/flush metrics hoặc equivalent profile.
- [ ] Có Hikari active/idle/pending và acquire/usage/creation/timeout metrics.
- [ ] Phân biệt acquisition timeout với statement timeout.
- [ ] Biết transaction boundary và connection holding time.
- [ ] Có DB slow query insights, normalized SQL frequency/total time.
- [ ] Có query plans cho top high-cost statements.
- [ ] Có DB lock/wait, CPU, IO, WAL/replication metrics.
- [ ] Có network RTT/retransmission signals giữa app và DB.
- [ ] Có JVM CPU/allocation/GC observations.
- [ ] Có kết quả query row count/response size.
- [ ] Đo p95/p99, không chỉ average.
- [ ] Có cảnh báo pool pending/timeout, query waits và SQL count spike.
- [ ] Có kiểm soát quyền xem SQL, binds và dữ liệu tenant.
- [ ] Có load test trên DB gần production, với dữ liệu đủ lớn.
- [ ] Có incident report phân biệt symptom và root cause.

## 38. Bài tập thực hành

### Bài 1 — Phân rã thời gian

Một request mất 1.400 ms; pool acquire 1.050 ms, DB query 20 ms, DTO/serialization 120 ms. Nên điều tra tầng nào trước? Vì sao không quy ngay cho Hibernate?

### Bài 2 — N+1

Một request tải 100 Orders và 100 Customer lazy khác nhau, tạo 101 SELECTs. RTT 8 ms, DB execution 1 ms mỗi query. Ước lượng phần độ trễ tuần tự và đề xuất hai fetch strategies.

### Bài 3 — Metrics Hikari

Pool max=20, active=20, idle=0, pending=35, acquire p95=2.000 ms. Có phải pool size luôn cần tăng lên 40 không? Cần xem thêm metric nào?

### Bài 4 — Long transaction

Một method `@Transactional` gọi remote payment service 3 giây sau lần SQL đầu. Đề xuất workflow giảm connection holding time mà vẫn giữ correctness/idempotency.

### Bài 5 — Connection creation

Chỉ request đầu của pod mới mất 1 giây, creation timer cao. Nêu ba nguyên nhân khác với query execution time.

### Bài 6 — Hibernate Statistics

`getEntityLoadCount()=500` và `getPrepareStatementCount()=20`. Có thể kết luận mỗi entity load cần một SELECT không? Vì sao statistics toàn SessionFactory khó áp cho một request?

### Bài 7 — Lazy serialization

Service method kết thúc 40 ms, HTTP response hoàn thành sau 2 giây, SQL logs xuất hiện trong Jackson serialization. Nguyên nhân khả dĩ và giải pháp?

### Bài 8 — EXPLAIN

Một query có Seq Scan nhưng trả 80% bảng. Có cần index ngay không? Nếu query chỉ trả 0,01% row mà scan cả bảng thì sao?

### Bài 9 — Lock wait

DB CPU thấp, nhiều `pg_stat_activity` rows đang đợi `Lock`, có một blocker `idle in transaction`. Vì sao tăng DB CPU không giải quyết? Cần điều tra gì?

### Bài 10 — Result size

Một query server execution 25 ms, JDBC client mất 2 giây để đọc 500.000 rows. Nêu những yếu tố ở network, driver và ORM cần kiểm tra.

### Bài 11 — DML EXPLAIN

Vì sao chạy `EXPLAIN (ANALYZE, BUFFERS) UPDATE ...` trên production có rủi ro? Nêu cách thử an toàn.

### Bài 12 — Commit time

`em.flush()` mất 40 ms nhưng transactional service call mất 700 ms. Kể ba nơi có thể phát sinh thời gian sau flush.

### Bài 13 — Query shape

`pg_stat_statements` cho thấy query A gọi 1 triệu lần × 2 ms, query B gọi 100 lần × 500 ms. Nên tối ưu cái nào trước? Điều gì quyết định?

### Bài 14 — Network RTT

App–DB RTT 40 ms, request phát 80 sequential queries, server execute mỗi query 1 ms. Giải thích vì sao SQL logs từng query không có slow statement nhưng request rất chậm.

### Bài 15 — DTO projection

UI cần 3 fields nhưng repository trả entity 40 fields với 4 relations. So sánh entity loading và DTO projection về rows/columns/GC/network.

### Bài 16 — Nested transactions

Một request có outer transaction giữ connection, sau đó `REQUIRES_NEW` inner transaction dùng connection khác. Nếu concurrency cao, pool có rủi ro nào?

### Bài 17 — Database index

Thiết kế index ứng viên cho query theo `organization_id`, `status`, `ORDER BY created_at DESC,id DESC`, `LIMIT 50`. Nêu cách xác minh bằng plan.

### Bài 18 — Timeout

Phân biệt Hikari `connection-timeout`, JDBC query timeout và database `statement_timeout`. Loại nào xảy ra trước khi SQL được gửi?

### Bài 19 — Cache

Một endpoint nhanh ở lần hai nhưng chậm ở lần đầu. Tại sao không nên quy ngay cho DB index? Cần kiểm tra những caches/warm-up nào?

### Bài 20 — Threads

Thread dump cho thấy nhiều threads đang BLOCKED/WAITING, pool pending cao. Vì sao cần phân biệt thread waiting for pool, DB lock và Java monitor lock?

### Bài 21 — SQL log

Hibernate DEBUG in SQL nhưng không có timing. Làm sao biết SQL server chậm, network chậm hay hydrate chậm?

### Bài 22 — Multi-tenancy

Một instance có 200 tenant pools, mỗi pool max 10. Vì sao số connection lý thuyết là một nguy cơ dù traffic mỗi tenant thấp? Đề xuất cách quản lý.

### Bài 23 — Query plan skew

Cùng normalized SQL nhưng tenant lớn chậm còn tenant nhỏ nhanh. Nêu vai trò của parameter values, cardinality, statistics và generic plan.

### Bài 24 — JFR

Server query nhanh, pool chờ thấp, Java allocation/GC cao. Nên dùng công cụ nào để định vị object allocations? Vì sao tăng pool không giúp?

### Bài 25 — Incident

Hãy mô tả một incident report gồm bằng chứng về p99, Hikari, JDBC, database waits, network, code change, before/after và rollback plan. Phân biệt symptom với root cause.

### Gợi ý đáp án

- **Bài 1:** Pool acquisition là phần lớn request; kiểm tra active/usage/pending và nguyên nhân connections giữ lâu.
- **Bài 2:** Xấp xỉ 101 × (8+1)=909 ms chưa tính hydration; dùng to-one fetch join, batch fetching hoặc DTO projection.
- **Bài 3:** Không. Xem usage p95, DB locks, CPU/IO, transaction duration, leaks, request concurrency.
- **Bài 4:** Rút transaction quanh DB work, dùng idempotency/outbox/saga theo nghiệp vụ; không để remote call giữ locks vô ích.
- **Bài 5:** DNS/TCP/TLS/authentication, pool warm-up hoặc driver connection setup.
- **Bài 6:** Không 1:1; cache/batch fetch/query shapes khác nhau; SessionFactory counters chứa mọi requests.
- **Bài 7:** Lazy loading/N+1 trong serializer hoặc OSIV; trả DTO và fetch đúng trong service.
- **Bài 8:** Scan 80% có thể đúng; scan toàn bảng để lấy 0,01% đáng kiểm tra index/stats/plan.
- **Bài 9:** Query bị block trên lock; điều tra blocking transaction và code giữ transaction lâu.
- **Bài 10:** Network bytes/bandwidth/RTT, fetch size/ResultSet streaming, ORM hydration/GC.
- **Bài 11:** ANALYZE thực thi DML; chạy staging hoặc transaction rollback có kiểm soát và hiểu side effects.
- **Bài 12:** Commit WAL/replication, deferred constraint, network COMMIT response và transaction manager completion.
- **Bài 13:** A có total server cost lớn, B có tail latency cao; ưu tiên theo SLO và critical path.
- **Bài 14:** Round-trips tuần tự chiếm khoảng 3,2 giây; giảm query count/đưa app gần DB.
- **Bài 15:** Projection giảm columns/entities/relations và allocation nếu query đúng.
- **Bài 16:** Nested connection demand gây pool starvation; xem outer/inner resource usage và sizing.
- **Bài 17:** Index `(organization_id,status,created_at DESC,id DESC)` là ứng viên; kiểm tra EXPLAIN actual rows/buffers.
- **Bài 18:** Hikari connection-timeout thường xảy ra lúc chờ acquire; hai timeout còn lại thuộc statement execution.
- **Bài 19:** JIT, DB buffer cache, ORM/second-level/application cache, pool warm-up, DNS/TLS.
- **Bài 20:** Thread trạng thái WAITING không đủ kết luận; cần stack traces và resource metrics.
- **Bài 21:** JDBC timers/trace, DB execution metrics/EXPLAIN, pool metrics và JVM profiler.
- **Bài 22:** Có thể tới 2.000 connections; cần global limit, pool lifecycle và concurrency per tenant.
- **Bài 23:** Data skew/stats/plan cache và binds làm hiệu năng khác nhau theo tenant.
- **Bài 24:** JFR/allocation profiler/flame graph; bottleneck Java CPU/heap chứ không phải thiếu connection.
- **Bài 25:** Nêu mốc thời gian, SLO, giả thuyết, dữ liệu từng tầng, nguyên nhân gốc, thử nghiệm và kết quả trước/sau.

---

## Tổng kết

**Độ trễ của một request Hibernate không đồng nhất với thời gian database chạy SQL.** Để tìm đúng nguyên nhân:

1. **Đo đúng ranh giới:** HTTP/service, connection acquisition/usage, JDBC statement và ResultSet, DB execution/wait, network transfer, ORM hydration và serialization.
2. **Nhận diện lỗi ORM:** N+1, fetch graph quá rộng, pagination thiếu giới hạn, dirty checking/flush và nhiều SQL round-trips. DB có thể chạy mỗi câu nhanh mà request vẫn rất chậm.
3. **Nhận diện lỗi pool:** active đạt max, pending/timeout tăng, acquire p95 cao. Nhưng phải tìm vì sao connections được giữ lâu — DB locks, long transactions, leak hay concurrency.
4. **Nhận diện lỗi mạng:** connection creation, DNS/TCP/TLS, per-query RTT, data transfer và packet loss. Một SQL server execution ngắn không có nghĩa client-observed latency ngắn.
5. **Nhận diện lỗi DB:** query plan, indexes, cardinality estimates, lock wait, I/O, temp spill, WAL/commit và replication. Dùng EXPLAIN, wait events và server metrics.
6. **Xác minh bằng thí nghiệm:** giữ workload/data/driver/DB tương đương, đo p95/p99 và total costs trước/sau; không tăng pool, đổi fetch strategy hay thêm index theo cảm giác.

**Điểm quan trọng nhất:** Hãy phân biệt **nơi thời gian được tiêu thụ** với **nguyên nhân gốc làm thời gian đó tăng**. Một pool đang chờ có thể bắt nguồn từ database locks; một database có nhiều round-trips có thể bắt nguồn từ ORM N+1; một request “chậm vì mạng” có thể thực ra đang truyền quá nhiều rows. Chỉ khi đo đủ các tầng, ta mới chọn đúng biện pháp tối ưu mà không làm vấn đề chuyển sang tầng khác.

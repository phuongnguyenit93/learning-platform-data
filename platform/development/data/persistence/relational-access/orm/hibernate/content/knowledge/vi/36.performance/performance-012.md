# Đánh giá bộ nhớ, số kết nối và hành vi dưới tải đồng thời

Một ứng dụng Hibernate chạy tốt với vài người dùng thử nghiệm chưa chắc chịu được tải production. Khi concurrency tăng, vấn đề thường xuất hiện ở ba nhóm tài nguyên liên quan:

- **Bộ nhớ:** Session giữ bao nhiêu entity, snapshot dirty checking, collection và kết quả query? JVM có cấp phát quá nhiều object hoặc chạy GC liên tục không?
- **Kết nối:** Có đủ JDBC connections cho workload không? Request phải chờ pool bao lâu? Connection có bị giữ lâu trong transaction không?
- **Hành vi đồng thời:** Nhiều transactions cùng đọc/ghi có gây lock contention, deadlock, optimistic-lock failures, connection starvation hoặc latency tăng mạnh không?

Đánh giá đúng cần quan sát đồng thời Hibernate, JVM, connection pool và database. Tăng heap hoặc tăng số connections riêng lẻ có thể chỉ chuyển điểm nghẽn sang tầng khác.

Bài thuộc chương **Hiệu năng** của module *Data Persistence Relational Access ORM Hibernate*. Nội dung hướng đến Hibernate ORM 6.x/7.x, JDBC, HikariCP và Spring Boot; tập trung vào cách đo, đọc metrics, thiết kế load test và chọn biện pháp tối ưu dựa trên bằng chứng.

## 1. Ba nhóm tài nguyên và mối quan hệ

~~~text
HTTP / message / batch requests
              |
              v
       Application threads
              |
              v
       Transaction boundary
              |
              v
        Hibernate Session
      /       |          \
     v        v           v
 L1 cache  Action queue  Fetch state
     \        |           /
      \       v          /
       JDBC connection pool
              |
              v
          Database
       /      |       \
   CPU/IO   Locks    Buffer cache
~~~

Trong một request:

1. Application thread giữ stack và object của request.
2. Session giữ persistence context và managed entity/collection state.
3. Hibernate chuẩn bị SQL, dirty checking và action queue.
4. Transaction cần JDBC connection khi thực hiện database work.
5. Database xử lý SQL, locks, indexes, I/O và transaction log.
6. Khi transaction kết thúc, connection được trả về pool; Session được đóng hoặc giải phóng theo scope.

Một request có thể tiêu thụ heap trong thời gian dài nhưng chỉ giữ connection một phần thời gian, tùy connection handling mode và transaction. Ngược lại, transaction chậm có thể giữ connection trong lúc chờ lock hoặc chờ code ứng dụng, làm pool cạn dù CPU ứng dụng còn rảnh.

## 2. Bộ metrics tối thiểu

| Tầng | Chỉ số | Câu hỏi |
| --- | --- | --- |
| JVM | Heap used/committed/max | Heap có tăng liên tục hoặc gần giới hạn không? |
| JVM | Allocation rate, GC pause | Object churn và GC có làm tăng latency không? |
| JVM | Thread count, blocked threads | Threads có bị block/chờ quá nhiều không? |
| Hibernate | Entity load/fetch counts | ORM đang nạp bao nhiêu entities? |
| Hibernate | Query executions, prepared statements | Có N+1 hoặc query lặp không? |
| Hibernate | Flush count, L2 cache hits/misses | Flush/cache có bất thường không? |
| Pool | Active, idle, pending | Có request chờ connection không? |
| Pool | Acquire time, usage time | Lấy và giữ connection mất bao lâu? |
| Database | Active sessions, CPU, I/O | DB đang bão hòa tài nguyên nào? |
| Database | Lock waits, deadlocks | Transactions đang tranh chấp gì? |
| Application | Throughput, p50/p95/p99 | Người dùng thấy độ trễ nào? |
| Application | Error/timeout rate | Hệ thống thất bại ở mức tải nào? |

Metrics phải có cùng time window và timestamp. Một ảnh chụp heap hoặc pool tại một thời điểm thường không đủ để giải thích nguyên nhân.

## 3. Session và persistence context tiêu thụ bộ nhớ

Hibernate **Session** không chỉ là wrapper quanh JDBC connection. Nó quản lý persistence context (first-level cache, L1), identity map, entity state, collection state và các action cần flush.

Khi load một entity, Hibernate có thể giữ:

- Entity instance trong heap.
- Entry mô tả entity và trạng thái managed.
- Snapshot hoặc thông tin cần cho dirty checking.
- Collection wrappers và collection snapshots.
- Proxy/bytecode-enhanced state nếu mapping sử dụng.
- Pending insert/update/delete actions trong action queue.
- References giữa các entities qua associations.
- Query result list hoặc DTO/object do application giữ.

Ví dụ:

~~~java
List<Order> orders = session.createSelectionQuery(
    "from Order o",
    Order.class
).getResultList();
~~~

Nếu query trả 200.000 Orders, Session có thể giữ tất cả managed instances và state liên quan. Application còn giữ List kết quả, vì vậy entity không thể được thu hồi chỉ bằng cách kết thúc vòng lặp.

### Bộ nhớ tăng theo số managed objects

~~~text
Heap used
  = application objects
  + Session/persistence context
  + managed entity state
  + collection state
  + query results
  + caches
  + JDBC/driver buffers
  + framework/runtime overhead
~~~

Không có một con số byte/entity đúng cho mọi mapping. Entity có vài scalar fields khác xa entity có nhiều eager associations và collections lớn. Hãy đo bằng heap profiling với dữ liệu thực tế.

## 4. L1 cache thuộc về Session

Trong một Session, cùng một entity identity thường được đại diện bởi một managed object duy nhất:

~~~java
Product first = session.find(Product.class, 42L);
Product again = session.find(Product.class, 42L);

assert first == again;
~~~

Hibernate có thể trả cùng instance mà không query database lần nữa.

Ưu điểm:

- Tránh load lặp một entity đã managed.
- Hỗ trợ dirty checking.
- Giữ identity semantics trong unit of work.
- Điều phối cascade và association state.

Chi phí:

- Entity đã load có thể tiếp tục nằm trong heap tới khi detach/clear/close và không còn reference khác.
- Session dài hạn có thể tích lũy hàng nghìn hoặc hàng triệu managed objects.
- Collection lớn có thể giữ cả object graph.
- Dirty checking trên quá nhiều managed entities làm flush tốn CPU.

**Session nên có scope ngắn, thường tương ứng một unit of work/transaction**, không phải object singleton hoặc Session dùng cho cả ngày.

## 5. Dirty checking và snapshot state

Hibernate cần phát hiện thay đổi trên managed entities để tạo UPDATE khi flush. Tùy mapping, bytecode enhancement và read-only mode, Hibernate có thể dùng snapshot/state tracking.

~~~java
Product product = session.find(Product.class, 42L);
product.setName("Updated name");

transaction.commit();
~~~

Khi flush, Hibernate xác định entity thay đổi và tạo SQL phù hợp.

Nếu Session giữ 100.000 managed entities, flush có thể phải kiểm tra một lượng lớn state. Chi phí gồm CPU, allocations, SQL preparation và database work.

Không giữ toàn bộ entities chỉ để thay đổi vài bản ghi. Dùng query hẹp, DTO hoặc batch/chunk processing.

### Read-only mode

Với tác vụ chỉ đọc, có thể xem xét:

~~~java
session.setDefaultReadOnly(true);
~~~

hoặc trên query:

~~~java
query.setReadOnly(true);
~~~

Read-only entities có thể giảm snapshot/dirty-checking work tùy mapping và version. Đây là hợp đồng về cách ứng dụng sử dụng entity: không dựa vào việc sửa các object read-only rồi mong Hibernate tự lưu. Kiểm tra behavior theo Hibernate version, nhất là khi dùng bytecode enhancement và associations.

Read-only mode không phải database lock và không thay transaction isolation.

## 6. Flush không giải phóng persistence context

Phân biệt:

- **flush()** đồng bộ thay đổi pending xuống database.
- **clear()** detach tất cả entities khỏi persistence context.
- **close()** kết thúc Session và giải phóng resources theo lifecycle.
- **commit()** kết thúc transaction thành công; thường dẫn tới flush theo flush mode/contract.

**Gọi flush không làm Session quên entities đã load hoặc persist.**

Ví dụ chưa đủ:

~~~java
for (int i = 0; i < 100_000; i++) {
    session.persist(new Product("SKU-" + i));
    if (i % 50 == 0) {
        session.flush();
    }
}
~~~

Dù flush định kỳ, persistence context vẫn có thể giữ mọi Product.

Với batch insert, cân nhắc flush và clear:

~~~java
int batchSize = 50;

for (int i = 0; i < products.size(); i++) {
    session.persist(products.get(i));

    if ((i + 1) % batchSize == 0) {
        session.flush();
        session.clear();
    }
}

session.flush();
session.clear();
~~~

Sau clear, entities trong Session bị detach. Nếu còn pending changes chưa flush, clear có thể làm chúng không được ghi. Vì vậy **flush trước clear** khi cần giữ các thay đổi.

### Flush/clear không kết thúc transaction

Nếu một triệu rows vẫn nằm trong một transaction:

- DB transaction log/undo retention có thể lớn.
- Locks có thể được giữ lâu.
- Connection có thể bị chiếm lâu.
- Rollback có thể tốn thời gian.
- Replication/cleanup có thể bị ảnh hưởng.

Nếu nghiệp vụ cho phép, commit theo từng chunk bằng transaction/Session riêng. Nếu cần atomicity toàn bộ, phải chấp nhận chi phí transaction lớn hoặc thiết kế quy trình khác như staging, checkpoint và idempotent chunks.

## 7. Batch insert theo từng chunk

Ví dụ native Hibernate:

~~~java
void insertChunk(
        SessionFactory sessionFactory,
        List<ProductInput> chunk) {

    try (Session session = sessionFactory.openSession()) {
        Transaction tx = session.beginTransaction();

        try {
            int count = 0;

            for (ProductInput input : chunk) {
                session.persist(
                    new Product(input.sku(), input.name())
                );

                if (++count % 50 == 0) {
                    session.flush();
                    session.clear();
                }
            }

            session.flush();
            tx.commit();
        } catch (RuntimeException ex) {
            if (tx.isActive()) {
                tx.rollback();
            }
            throw ex;
        }
    }
}
~~~

ProductInput là DTO đầu vào minh họa. Caller chia dữ liệu thành chunks và gọi method cho từng chunk.

| Một transaction cho toàn batch | Transaction theo từng chunk |
| --- | --- |
| Atomicity toàn batch | Mỗi chunk commit độc lập |
| Rollback có thể rất lớn | Retry/checkpoint dễ hơn |
| Connection/locks giữ lâu | Giảm thời gian giữ tài nguyên mỗi chunk |
| Transaction log có thể lớn | Nhiều commits hơn |
| Khó resume khi thất bại | Có thể tiếp tục từ chunk đã commit |

Nếu chunk 1 đã commit và chunk 2 lỗi, không thể giả định toàn batch rollback. Cần thiết kế idempotency, unique keys và checkpoint.

## 8. JDBC batching khác fetch size

Hai khái niệm thường bị nhầm:

- **JDBC batch size:** gom nhiều DML statements để driver gửi theo batch.
- **JDBC fetch size:** gợi ý cho driver số rows muốn lấy mỗi lần khi đọc result set.

Cấu hình JDBC batching:

~~~properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
~~~

hibernate.jdbc.batch_size cho phép Hibernate gom các INSERT/UPDATE tương thích thành JDBC batches. Giá trị 50 chỉ là điểm khởi đầu minh họa; phải đo với driver/database.

### Identifier generator có ảnh hưởng

Với identity identifier generation, Hibernate thường phải thực thi INSERT để lấy generated key ngay. Do đó JDBC insert batching có thể không hoạt động như mong đợi. Kiểm tra generator strategy và Hibernate version trước khi kết luận batching không có tác dụng.

Property hibernate.jdbc.batch_versioned_data liên quan batching UPDATE/DELETE có version checking. Default và behavior phụ thuộc version/dialect; không thay đổi chỉ dựa trên một ví dụ cũ.

## 9. Đọc dữ liệu lớn: tránh materialize toàn bộ List

~~~java
List<AuditRecord> records = session.createSelectionQuery(
    "from AuditRecord order by id",
    AuditRecord.class
).getResultList();
~~~

Query trên có thể giữ tất cả kết quả trong List, cộng với managed entity state trong Session.

Các lựa chọn:

1. DTO projection nếu không cần entity lifecycle/dirty checking.
2. Pagination theo key để xử lý từng trang.
3. Scroll/stream với resource lifecycle được đóng đúng.
4. Batch read với Session ngắn theo chunk.
5. Native/JDBC streaming khi cần kiểm soát result set trực tiếp.

Ví dụ DTO projection:

~~~java
List<ProductRow> rows = session.createSelectionQuery(
    """
    select new com.example.ProductRow(p.id, p.sku, p.name)
    from Product p
    order by p.id
    """,
    ProductRow.class
).getResultList();
~~~

ProductRow là DTO có constructor tương ứng. DTO không cần trở thành managed entity, giúp giảm persistence-context overhead.

### Stream phải được đóng

~~~java
try (Stream<Product> stream = session.createSelectionQuery(
        "from Product p order by p.id",
        Product.class
    ).getResultStream()) {

    stream.forEach(this::process);
}
~~~

Đóng Stream giúp giải phóng resources liên quan. Tuy nhiên, **đừng mặc định mọi provider/driver đều stream thật sự không buffer**. Kiểm tra Hibernate version, driver fetch behavior, JDBC fetch size và heap profile. Stream vẫn có thể gây memory pressure nếu rows được materialize hoặc application giữ references.

## 10. Scroll và JDBC fetch size

Khi phải đọc rất nhiều rows, Hibernate scroll APIs hoặc JDBC forward-only result processing có thể phù hợp.

~~~java
query.setFetchSize(500);

try (ScrollableResults<Product> results =
         query.scroll(ScrollMode.FORWARD_ONLY)) {

    while (results.next()) {
        Product product = results.get();
        process(product);
    }
}
~~~

Chữ ký generic/return type của ScrollableResults khác nhau theo Hibernate major versions; hãy dùng API của phiên bản dự án. Ví dụ minh họa ý tưởng, không bảo đảm compile trên mọi version.

Fetch size là **hint cho JDBC driver**, không phải giới hạn cứng heap. Driver/database có thể diễn giải khác nhau; một số driver cần transaction/cursor settings riêng để stream thật sự.

Khi scroll entity, persistence context vẫn có thể giữ entities đã đọc. Có thể flush/clear theo chunk nếu tác vụ thay đổi dữ liệu và lifecycle cho phép, hoặc dùng scalar/DTO/JDBC khi không cần managed entities.

## 11. Pagination: offset và keyset

Offset pagination:

~~~java
List<Product> page = session.createSelectionQuery(
    "from Product p order by p.id",
    Product.class
)
.setFirstResult(offset)
.setMaxResults(pageSize)
.getResultList();
~~~

Phù hợp cho trang nhỏ hoặc khi UI cần nhảy tới trang cụ thể. Offset lớn có thể buộc database đọc/bỏ qua nhiều rows; dữ liệu thay đổi giữa các trang cũng có thể gây lặp/bỏ sót.

Keyset pagination:

~~~java
List<Product> page = session.createSelectionQuery(
    """
    from Product p
    where p.id > :lastId
    order by p.id
    """,
    Product.class
)
.setParameter("lastId", lastSeenId)
.setMaxResults(pageSize)
.getResultList();
~~~

Keyset sử dụng giá trị cuối trang trước làm cursor. Cần thứ tự ổn định và cursor đầy đủ. Nếu sort theo nhiều cột như (createdAt, id), cursor phải chứa cả hai và predicate phải thể hiện đúng thứ tự.

Keyset hữu ích cho batch/export và infinite scroll; không thay thế offset trong mọi UI.

## 12. N+1 query và memory pressure

Một query lấy 100 Orders rồi mỗi Order lazy-load Customer riêng có thể tạo:

~~~text
1 query lấy Orders
100 queries lấy Customer
------------------------
101 SQL executions
~~~

N+1 làm tăng round trips, statement creation, connection usage time, transaction duration, entity hydration và allocations.

Các lựa chọn:

- Fetch join khi phù hợp.
- EntityGraph.
- Batch fetching bằng @BatchSize hoặc hibernate.default_batch_fetch_size.
- DTO projection.
- Query riêng cho association cần thiết.

Ví dụ:

~~~java
@OneToMany(mappedBy = "order")
@BatchSize(size = 32)
private List<OrderLine> lines;
~~~

Hoặc:

~~~properties
spring.jpa.properties.hibernate.default_batch_fetch_size=32
~~~

Batch fetching có thể gom lazy loads thành ít queries hơn. Nhưng batch size cần đo; quá lớn có thể tạo IN lists lớn và memory spike.

### Fetch join collection và pagination

Fetch join một collection to-many có thể nhân số rows SQL. Kết hợp collection fetch join với pagination thường gây vấn đề; Hibernate có thể phải paginate trong memory hoặc báo warning/failure tùy configuration/version.

Có thể bật:

~~~properties
spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true
~~~

để phát hiện query kiểu này sớm. Thay thế có thể là page IDs trước, rồi fetch associations cho nhóm IDs đó, hoặc dùng DTO query.

## 13. Cache và chi phí bộ nhớ

| Cache | Scope | Tác dụng | Chi phí |
| --- | --- | --- | --- |
| L1 persistence context | Một Session | Identity map, dirty checking | Tăng theo managed entities |
| L2 entity cache | SessionFactory/cache provider | Tái sử dụng entity state | Heap/off-heap/remote cache |
| Collection cache | Cache provider | Collection membership/state | Entries và invalidation |
| Query cache | Cache provider | Query result information | Memory + invalidation |
| Application cache | Application | DTO/domain result cache | Do app tự quản lý |

L2 cache không mặc định luôn tăng hiệu năng. Với dữ liệu thay đổi liên tục hoặc ít được đọc lại, cache có thể tăng memory và invalidation overhead mà không giảm DB load đáng kể.

Query cache cũng không phải cache mọi SQL. Nó cần cache provider/regions và invalidation phù hợp. Bật cache cho tất cả queries có thể làm tăng memory và churn.

Chỉ cache queries có access pattern lặp lại, dữ liệu phù hợp và hit ratio đo được. Đặt bounds/expiry/eviction trong cache provider.

## 14. Đo memory ngoài heap

Process memory không chỉ có Java heap:

~~~text
Process memory
  = Java heap
  + Metaspace
  + Thread stacks
  + Direct/native buffers
  + JDBC driver/native allocations
  + JIT/code cache
  + JVM/native overhead
~~~

Heap có thể ổn nhưng container vẫn OOM do direct buffers, thread stacks hoặc native allocations.

Theo dõi:

- Heap used sau GC và xu hướng theo thời gian.
- Old-generation occupancy.
- Allocation rate.
- GC pause p95/p99.
- GC cycles.
- Live objects và retained size từ heap dump.
- Thread count/stack memory.
- Direct buffer pool usage.
- Container RSS/cgroup memory.
- JDBC driver buffers khi result sets lớn.

Dùng Java Flight Recorder (JFR), heap dump và profiler để tìm object retention. Không kết luận memory leak chỉ vì heap tăng trong warm-up; hãy xem sau GC và qua chu kỳ workload dài.

## 15. Hibernate Statistics

Bật statistics:

~~~properties
spring.jpa.properties.hibernate.generate_statistics=true
~~~

Lấy metrics:

~~~java
Statistics statistics = sessionFactory.getStatistics();

long entityLoads = statistics.getEntityLoadCount();
long entityFetches = statistics.getEntityFetchCount();
long queryExecutions = statistics.getQueryExecutionCount();
long preparedStatements = statistics.getPrepareStatementCount();
long flushes = statistics.getFlushCount();
~~~

Một số metrics hữu ích khác tùy Hibernate version:

- getSecondLevelCacheHitCount()
- getSecondLevelCacheMissCount()
- getSecondLevelCachePutCount()
- getConnectCount()
- getOptimisticFailureCount()
- Query statistics theo query key khi được bật.

Statistics thường là số liệu cấp SessionFactory, không phải dashboard tự động theo từng HTTP request. Trong multi-tenant app, không suy luận tenant-specific performance từ counter toàn cục nếu không có instrumentation bổ sung.

Statistics có overhead; bật có chủ đích trong benchmark/observability và kiểm tra chi phí. Có thể reset giữa benchmark phases để baseline rõ.

## 16. Kết hợp Hibernate, JVM và database metrics

Một query chậm có thể do nhiều tầng:

~~~text
Application:
  Thread pool queueing?
  CPU / serialization?

Hibernate:
  N+1?
  Too many managed entities?
  Flush / dirty checking?

Connection pool:
  Waiting for connection?
  Connection held too long?

Database:
  Slow execution plan?
  Lock wait?
  I/O saturation?
~~~

Không kết luận “Hibernate chậm” chỉ từ endpoint latency. Cần phân rã:

- Request queue time.
- Session/transaction initialization.
- Connection acquisition time.
- SQL execution time.
- Result fetch/hydration time.
- Application processing.
- Flush/commit time.
- Serialization/network.

Tracing/Micrometer/OpenTelemetry có thể liên kết request với JDBC spans. Tránh gắn tenant ID hoặc SQL parameters nhạy cảm vào labels có cardinality quá cao.

## 17. Connection pool làm nhiệm vụ gì?

Mở JDBC connection mới có chi phí: network handshake, authentication, TLS, server session setup và resource allocation. Connection pool giữ sẵn connections để nhiều transactions mượn/trả.

~~~text
Hibernate / JDBC
       |
       v
Connection pool
  |     |      |
  C1    C2     C3 ...
       |
       v
Database
~~~

Một pool có:

- Active connections: đang được ứng dụng mượn.
- Idle connections: đang rảnh.
- Pending/waiting threads: đang chờ connection.
- Maximum pool size.
- Minimum idle.
- Acquisition timeout.
- Connection usage duration.
- Leak detection/validation metrics.

Trong Spring Boot, HikariCP thường là pool mặc định khi dependency phù hợp có mặt. Không tạo một pool mới mỗi lần mở Session.

## 18. Session không nhất thiết giữ connection suốt vòng đời

Hibernate có connection handling modes và có thể trì hoãn lấy JDBC connection cho tới khi cần thực thi SQL. Connection release timing phụ thuộc transaction mode, provider và configuration.

- Mở Session không luôn đồng nghĩa ngay lập tức mượn connection.
- Transaction đang thực hiện SQL thường cần giữ connection trong thời gian phù hợp với handling mode.
- Connection có thể được trả về pool khi transaction kết thúc hoặc theo release mode phù hợp.
- Không giả định Session open/close và connection checkout có thời gian giống hệt nhau.

Đo pool metrics thực tế thay vì suy luận chỉ từ số Sessions đang mở.

## 19. Pool size không nên bằng số threads

Nếu application có 200 worker threads, không có nghĩa DB nên nhận 200 connections từ instance đó.

Nếu database chỉ xử lý hiệu quả 30 concurrent transactions cho workload hiện tại, mở thêm connections có thể tăng context switching, lock contention, memory per database session và latency.

Pool size là quyết định về **capacity của database và thời gian giữ connection**, không phải số thread tối đa của application.

## 20. Ước lượng concurrency bằng Little's Law

Little's Law:

\[
L = \lambda \times W
\]

Trong đó:

- \(L\): số requests/transactions trung bình đang sử dụng resource.
- \(\lambda\): throughput trung bình (transactions/second).
- \(W\): thời gian trung bình giữ resource (seconds).

Ví dụ giả định:

- Database throughput: 80 transactions/second.
- Connection được giữ trung bình: 0,15 giây.

\[
L = 80 \times 0.15 = 12
\]

Trung bình khoảng 12 connections đang bận. Đây **không phải công thức trực tiếp ra maximum pool size**. Cần tính burst/variance, transaction tail latency, DB capacity, replica count và các workloads khác.

Nếu connection được giữ 1 giây thay vì 0,15 giây:

\[
L = 80 \times 1 = 80
\]

Pool pressure tăng dù throughput yêu cầu không đổi. Giảm thời gian giữ connection thường hiệu quả hơn chỉ tăng pool size.

## 21. Tổng connection budget trên toàn hệ thống

~~~text
12 application instances
maximumPoolSize = 20 each

Potential pool connections:
12 × 20 = 240
~~~

Database còn cần connections cho migration jobs, admin/monitoring, background workers, reporting và services khác.

| Thành phần | Instances | Pool max/instance | Tổng tiềm năng |
| --- | ---: | ---: | ---: |
| API service | 8 | 15 | 120 |
| Worker service | 3 | 8 | 24 |
| Reporting service | 2 | 5 | 10 |
| Migration/admin reserve | — | — | 10 |
| Tổng dự kiến | | | 164 |

Số liệu chỉ minh họa. So sánh tổng pool potential với DB max connections và reserve thực tế. Autoscaling có thể làm tổng connections tăng đột ngột.

## 22. HikariCP configuration

Ví dụ Spring Boot:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000
      max-lifetime: 1700000
      idle-timeout: 600000
      validation-timeout: 5000
      leak-detection-threshold: 60000
~~~

Không copy các giá trị này cho mọi hệ thống. Đối chiếu DB/network idle timeouts, số replicas, DB connection limit, transaction duration và pool metrics.

Theo dõi:

- Active.
- Idle.
- Pending.
- Maximum.
- Acquisition time.
- Usage time.
- Timeout count.

Nếu Pending tăng liên tục và Active gần maximum, pool đang chịu pressure. Nguyên nhân có thể là SQL chậm, lock wait, connection leak hoặc transaction giữ connection lâu; tăng max pool chưa chắc giải quyết đúng nguyên nhân.

Leak detection threshold giúp phát hiện connection bị giữ lâu trong môi trường chẩn đoán, nhưng threshold quá thấp có thể tạo cảnh báo false positive. Nó không tự giải phóng connection leak.

## 23. Connection acquisition timeout

Khi pool hết connections, thread phải chờ tới khi có connection hoặc timeout.

~~~yaml
spring:
  datasource:
    hikari:
      connection-timeout: 30000
~~~

Khi timeout, application có thể nhận exception từ pool. Đừng tăng timeout lên vài phút để che saturation; request threads sẽ bị giữ lâu hơn và queueing có thể lan rộng.

Chẩn đoán:

1. Active có chạm max không?
2. Pending threads có tăng không?
3. Usage time có tăng không?
4. SQL duration/lock wait có tăng không?
5. Có transaction mở nhưng không thực hiện SQL lâu không?
6. Có connection leak hoặc resource không được close không?
7. Tổng pool max của replicas có vượt DB capacity không?

## 24. Connection leak và transaction quá dài

Với JDBC trực tiếp, dùng try-with-resources:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             "select id from products where sku = ?"
         )) {

    statement.setString(1, sku);

    try (ResultSet resultSet = statement.executeQuery()) {
        // Đọc kết quả.
    }
}
~~~

Với Hibernate/Spring, thường để framework quản lý connections; không tự lấy connection từ DataSource rồi quên close.

Transaction dài cũng giữ connection lâu dù không phải leak:

~~~java
@Transactional
public void processOrder(Long id) {
    Order order = repository.findById(id).orElseThrow();

    callSlowRemoteApi();
    performMoreDatabaseWork(order);
}
~~~

Không gọi remote API hoặc chờ user input trong transaction nếu không cần. Có thể đọc dữ liệu, tính toán ngoài DB, rồi mở transaction ngắn để ghi kết quả; cần xem consistency và optimistic locking nếu dữ liệu có thể đổi giữa hai bước.

## 25. Pool starvation với nested transactions

Một tình huống:

- N threads bắt đầu outer transactions.
- Mỗi thread đang giữ một connection.
- Mỗi thread gọi REQUIRES_NEW cần connection thứ hai.
- Pool không còn connection rảnh.
- Inner transactions chờ trong khi outer transactions chưa thể hoàn tất.

Điều này có thể gây connection starvation tùy pool size/workload.

Cân nhắc transaction propagation, tránh giữ outer connection không cần thiết, giảm nested transaction pattern, giới hạn worker concurrency và bảo đảm pool có capacity cho workload thực.

Không giải quyết bằng cách tăng pool vô hạn.

## 26. Database capacity là giới hạn cuối

Pool có thể cấp 100 connections, nhưng DB có thể chỉ phục vụ tốt 25 concurrent transactions của workload hiện tại.

Khi DB bão hòa:

- CPU tăng.
- I/O queue tăng.
- Lock waits/deadlocks tăng.
- Query p95/p99 tăng.
- Buffer cache hit giảm.
- Transaction log/WAL pressure tăng.
- Connection usage time tăng.
- Pool pending tăng theo sau.

Nếu pool Active cao và database CPU/locks đã bão hòa, tăng pool max thường làm tình hình tệ hơn. Tối ưu query/index, giảm transaction duration, kiểm soát concurrency hoặc tăng DB capacity mới là hướng cần đo.

## 27. Session không thread-safe

Hibernate Session không thread-safe. Không chia sẻ một Session hoặc EntityManager cho nhiều threads.

Sai:

~~~java
@Component
public class SharedRepositoryHelper {

    private Session session;

    public void initialize(Session session) {
        this.session = session;
    }

    public Product load(Long id) {
        return session.find(Product.class, id);
    }
}
~~~

Hai requests đồng thời có thể thao tác cùng persistence context, transaction và JDBC resources.

Mô hình phù hợp:

- Session/EntityManager theo unit of work.
- Transaction boundary rõ.
- SessionFactory được dùng chung bởi nhiều threads.
- Không truyền Session qua threads.
- Không giữ managed entity trong singleton application state.
- Nếu cần truyền dữ liệu, chuyển thành DTO/value object.

## 28. Optimistic locking với @Version

Khi hai transactions cùng cập nhật một entity, optimistic locking giúp phát hiện lost update:

~~~java
@Entity
public class Inventory {

    @Id
    private Long id;

    private int available;

    @Version
    private long version;
}
~~~

Hai transactions cùng đọc version 5:

~~~text
Transaction A: read version 5
Transaction B: read version 5

A updates row where version = 5
  -> version becomes 6

B updates row where version = 5
  -> affected rows = 0
  -> optimistic lock failure
~~~

Hibernate/JPA có thể ném OptimisticLockException hoặc exception tương ứng.

Optimistic locking phù hợp khi conflict tương đối hiếm. Nó không tự retry an toàn; retry phải xem nghiệp vụ có idempotent và dữ liệu đầu vào còn hợp lệ không.

## 29. Pessimistic locking và lock contention

Hibernate/JPA hỗ trợ lock mode như PESSIMISTIC_WRITE:

~~~java
Inventory inventory = entityManager.find(
    Inventory.class,
    id,
    LockModeType.PESSIMISTIC_WRITE
);
~~~

Database có thể khóa row tới khi transaction kết thúc. Điều này giúp tuần tự hóa cập nhật quan trọng nhưng có chi phí:

- Transactions khác phải chờ.
- Lock duration tăng khi transaction dài.
- Deadlock có thể xảy ra nếu thứ tự lock không nhất quán.
- Throughput giảm ở hot rows.
- Connection bị giữ trong lúc chờ lock.

Dùng pessimistic lock khi business semantics cần và đã đo contention. Không khóa tất cả entities chỉ để tránh optimistic-lock exceptions.

Nếu transaction A lock row 1 rồi row 2, còn B lock row 2 rồi row 1, có thể tạo deadlock. Truy cập rows theo thứ tự ổn định giúp giảm một số deadlocks, nhưng không loại bỏ mọi deadlock.

## 30. Isolation level và concurrency

| Isolation | Ý nghĩa tổng quát |
| --- | --- |
| READ UNCOMMITTED | Có thể thấy dữ liệu chưa commit tùy DB |
| READ COMMITTED | Mỗi statement chỉ thấy dữ liệu đã commit |
| REPEATABLE READ | Snapshot/row stability tùy DB |
| SERIALIZABLE | Cô lập cao, có thể gây serialization failures/retries |

Hibernate dựa vào isolation do JDBC/database transaction cung cấp. Không giả định cùng tên isolation có semantics giống hệt giữa mọi database.

Chọn isolation theo business invariant, không chỉ để tăng throughput. Nếu nâng isolation, test lock waits, serialization failures và retry policy.

## 31. Flush mode và SQL phát sinh trong transaction

Hibernate có thể flush trước một số queries để query thấy pending changes phù hợp.

~~~java
session.persist(new Product("NEW-1"));

List<Product> products = session.createSelectionQuery(
    "from Product p where p.sku like 'NEW-%'",
    Product.class
).getResultList();
~~~

Tùy flush mode và query spaces, Hibernate có thể flush pending INSERT trước SELECT.

Điều này có thể gây latency bất ngờ nếu Session tích lũy nhiều changes. Không đặt hàng loạt writes rồi query trong cùng Session mà không hiểu flush behavior.

Đừng thay flush mode chỉ để che SQL nếu chưa hiểu consistency implications.

## 32. Chọn kỹ thuật theo bottleneck

| Tối ưu | Giải quyết | Không giải quyết |
| --- | --- | --- |
| JDBC batching | Giảm round trips cho DML | Không giảm số managed entities |
| Batch fetching | Giảm N+1 | Không tự giải quyết mọi query plan |
| Fetch join | Nạp association trong một SQL | Có thể nhân rows/pagination khó |
| DTO projection | Tránh entity state không cần | Không có dirty checking/lifecycle |
| Flush/clear | Giới hạn persistence-context growth | Không commit transaction |
| Pagination | Giới hạn kết quả mỗi chunk | Offset lớn vẫn có thể tốn DB |
| L2 cache | Giảm DB reads khi dữ liệu phù hợp | Invalidation/memory có chi phí |

Không bật tất cả options cùng lúc. Xác định bottleneck trước.

## 33. Hibernate settings thường dùng

Ví dụ Spring Boot:

~~~yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
        jdbc:
          batch_size: 50
          fetch_size: 200
        order_inserts: true
        order_updates: true
        default_batch_fetch_size: 32
        query:
          fail_on_pagination_over_collection_fetch: true
~~~

Các giá trị 50/200/32 chỉ minh họa; kiểm tra property binding và Hibernate version.

- generate_statistics: bật Hibernate statistics.
- jdbc.batch_size: JDBC DML batching.
- jdbc.fetch_size: fetch hint cho JDBC.
- order_inserts/order_updates: sắp xếp DML để tăng cơ hội batching.
- default_batch_fetch_size: batch lazy fetch.
- fail_on_pagination_over_collection_fetch: phát hiện pagination với collection fetch join.

Không bật SQL bind parameter TRACE trong production mặc định; có thể log dữ liệu nhạy cảm và tạo I/O overhead lớn.

## 34. Micrometer và connection pool metrics

Spring Boot Actuator/Micrometer có thể expose metrics cho JVM, HikariCP và datasource tùy dependencies/configuration.

Dashboard hữu ích gồm:

- Hikari active/idle/pending/max connections.
- Connection acquisition duration.
- Connection usage duration.
- JVM heap used/max.
- GC pause và allocation rate.
- Thread pool active/queue size.
- HTTP request p95/p99/error rate.
- Hibernate statistics.
- DB active sessions/locks/slow queries.

Không gắn tenant ID làm metric label nếu số tenants lớn và cardinality không kiểm soát. Có thể dùng sampled logs/traces hoặc nhóm tenants để quan sát.

## 35. SQL logging và execution plan

Trong môi trường phát triển:

~~~properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Logger và binding behavior tùy Hibernate version. Bind logging có thể lộ dữ liệu nhạy cảm; không bật rộng rãi ở production.

Khi query chậm:

1. Lấy SQL thực tế và bind types/values an toàn.
2. Chạy EXPLAIN hoặc execution plan trên DB.
3. Kiểm tra index, cardinality và selectivity.
4. Xem join order, sort, scan và temporary work.
5. Kiểm tra lock waits và transaction duration.
6. Đối chiếu ORM hydration/object allocations.
7. So sánh p95/p99 trước và sau thay đổi.

Query có DB execution time thấp nhưng endpoint chậm có thể đang hydrate hàng chục nghìn entities hoặc serialize graph lớn.

## 36. Thiết kế load test đáng tin cậy

Load test phải phản ánh workload, không chỉ bắn một query lặp vô hạn.

Xác định read/write mix, query distribution, result sizes, hot rows, tenant/data skew, transaction duration, batch jobs, cache state, số replicas, pool config và database size/index distribution.

Dữ liệu test phải đủ lớn để execution plan, cache và lock behavior gần production. Một bảng 1.000 rows không đại diện cho bảng production 100 triệu rows.

## 37. Các pha kiểm thử tải

~~~text
Warm-up
   |
   v
Ramp-up: tăng dần concurrent users
   |
   v
Steady state: giữ tải mục tiêu
   |
   v
Peak/spike: tăng nhanh vượt mức thường
   |
   v
Soak: duy trì tải lâu
   |
   v
Recovery: giảm tải và quan sát hồi phục
~~~

| Pha | Mục tiêu |
| --- | --- |
| Warm-up | JIT, connection pools, caches khởi tạo |
| Ramp-up | Tìm điểm latency bắt đầu tăng |
| Steady state | Đánh giá throughput ổn định |
| Spike | Đánh giá burst và queueing |
| Soak | Tìm memory/connection leaks, cache growth |
| Recovery | Xem pool/heap/queue có trở lại bình thường không |

Đừng lấy số liệu warm-up làm kết quả benchmark. Ghi lại duration, concurrency và workload profile mỗi pha.

## 38. Throughput và latency percentiles

Ít nhất cần transactions per second, p50, p95, p99, error rate/timeouts, queue/wait time và successful DB commits per second.

Average latency có thể che tail latency. Nếu p50 là 40 ms nhưng p99 là 4 giây, một nhóm người dùng vẫn có trải nghiệm rất xấu.

~~~text
Concurrency tăng
      |
      v
Throughput tăng tới saturation point
      |
      v
DB / locks / pool bão hòa
      |
      v
Latency và errors tăng
      |
      v
Throughput đứng yên hoặc giảm
~~~

Tìm điểm bão hòa thay vì chỉ thử concurrency tối đa.

## 39. Soak test tìm lỗi dài hạn

Một test 5 phút có thể không phát hiện Session/entity references bị giữ trong cache, ThreadLocal không cleanup, connection leak hiếm, cache tăng không giới hạn, connection pool churn, GC overhead tăng, DB transaction log/replication lag hoặc background job backlog.

Chạy workload ổn định đủ lâu, quan sát heap **sau GC**, active connections, cache sizes, thread count và queue depth. Memory tăng rồi ổn định sau warm-up khác với memory tăng liên tục.

## 40. Hot spots và data skew

Một load test chỉ truy cập IDs ngẫu nhiên có thể không mô phỏng hot rows. Production có thể có:

- Một inventory row được nhiều buyers cập nhật.
- Một account balance bị tranh chấp.
- Một tenant lớn chiếm phần lớn traffic.
- Một parent entity có collection cực lớn.
- Một unique key hoặc sequence hot.
- Một batch job quét bảng cùng lúc API writes.

Tạo workload có phân bố thực tế và test cả skew. Đo lock waits, deadlocks, optimistic failures và p99.

## 41. Thread pool và connection pool phải phối hợp

Application có thể có 200 worker threads nhưng Hikari pool 20 connections. Nếu mỗi operation giữ một connection, tối đa khoảng 20 DB operations đồng thời từ pool đó.

Điều này không nhất thiết sai. Các threads còn lại có thể làm CPU work hoặc chờ; nhưng nếu tất cả chờ connection, queueing và thread stack memory tăng mà throughput không cải thiện.

Phân biệt application worker concurrency, concurrent transactions, checked-out connections, DB capacity, async tasks chờ executor và requests đang chờ pool.

Nếu worker pool quá lớn, nhiều threads chờ connection có thể làm heap/thread stack tăng. Điều chỉnh admission control/backpressure thay vì chỉ tăng mọi pool.

## 42. Lock waits và deadlocks

Khi transaction chờ row/table lock, nó có thể vẫn giữ connection. Connection usage time tăng, pool active tăng, pending requests tăng và application latency tăng dù CPU app thấp.

Đo DB wait events và deadlock logs. Xác định transaction giữ lock, SQL lấy lock và thứ tự truy cập rows.

Có thể cân nhắc:

- Giảm transaction duration.
- Cập nhật rows theo thứ tự ổn định.
- Index đúng để giảm rows scan/lock.
- Giảm hot-spot contention.
- Dùng optimistic locking khi phù hợp.
- Dùng pessimistic locking có chọn lọc.
- Retry deadlock/serialization failure với backoff và operation idempotent.

Không retry mọi exception một cách mù quáng; side effects có thể bị lặp.

## 43. Tối ưu write throughput

Với batch writes:

1. Bật JDBC batching phù hợp.
2. Kiểm tra identifier generator có cho batching không.
3. Cân nhắc order inserts/updates.
4. Flush/clear theo chunk để giới hạn L1.
5. Giới hạn transaction duration nếu nghiệp vụ cho phép.
6. Đánh giá indexes/constraints và write amplification.
7. Đo lock waits và log/WAL throughput.
8. Dùng bulk DML khi semantics cho phép.

Bulk update có thể nhanh hơn entity-by-entity nhưng bypass callbacks/dirty checking và có thể làm managed entities stale. Sau bulk mutation, xử lý persistence context và cache theo Hibernate semantics.

## 44. Tối ưu read throughput

- Chọn DTO projection khi không cần managed entity.
- Giới hạn columns thay vì load graph lớn.
- Dùng pagination/keyset cho dữ liệu lớn.
- Xử lý N+1 bằng batch fetching hoặc fetch plan phù hợp.
- Dùng index theo execution plan.
- Tránh fetch join collection rộng.
- Dùng read-only transaction/hints khi đúng semantics.
- Cân nhắc L2/query cache cho dữ liệu đọc lặp lại, ít thay đổi.
- Không giữ Session mở trong lúc gọi remote service hoặc serialize chậm.

@Transactional(readOnly=true) không tự bảo đảm database không ghi. Spring/Hibernate có thể tối ưu flush/dirty checking tùy configuration; DB enforcement là chuyện riêng.

## 45. Open Session in View và tài nguyên

Open Session in View (OSIV) giữ persistence context qua controller/view rendering trong một số Spring Boot configurations.

Điều này có thể tiện cho lazy loading nhưng làm Session sống lâu hơn service transaction, lazy SQL phát sinh khi serialize, entity graph được giữ lâu và query count khó dự đoán.

Với API cần kiểm soát hiệu năng, thường dễ đo hơn khi service transaction load dữ liệu cần thiết, map DTO và kết thúc Session trước serialization.

Không tắt OSIV một cách mù quáng nếu app đang phụ thuộc lazy loading ngoài service; cần chuyển fetch plan/DTO trước.

## 46. Chẩn đoán pool saturation

| Quan sát | Khả năng | Bước tiếp theo |
| --- | --- | --- |
| Active gần max, Pending tăng, DB CPU thấp | Connection giữ lâu, leak hoặc transaction chờ app | Xem usage time và traces |
| Active gần max, DB CPU cao | DB bão hòa query/CPU | Query plan, index, DB capacity |
| Active gần max, lock waits cao | Transaction contention | Xem blockers, lock order, duration |
| Pending cao nhưng Active thấp | Connection creation/validation/network issue | Kiểm tra pool logs/network |
| Connection timeout nhưng DB còn capacity | Pool nhỏ, leak hoặc acquisition path chậm | Xem acquisition/usage |
| Active thấp, request vẫn chậm | Bottleneck app/CPU/network/serialization | Trace end-to-end |
| Pool churn cao | Lifetime/idle/network resets | Kiểm tra lifecycle settings |

Đây là heuristic, không phải kết luận tự động. Đối chiếu pool metrics với DB wait events và request traces.

## 47. Chẩn đoán memory pressure

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Heap tăng theo số rows xử lý | L1 persistence context hoặc List giữ toàn bộ | Chunk, DTO, flush/clear |
| Heap ổn nhưng GC pause cao | Allocation churn hoặc heap sizing | JFR, allocation profile |
| Heap sau GC tăng liên tục | Retained references/cache leak | Heap dump, dominator tree |
| Memory tăng khi bật L2 cache | Cache regions quá lớn | Bounds/expiry/eviction |
| Stream vẫn dùng nhiều heap | Driver/provider buffering hoặc app giữ refs | Kiểm tra fetch behavior |
| Threads tăng mạnh | Queue/backpressure kém | Giới hạn concurrency |
| Container OOM dù heap chưa đầy | Native/direct/thread memory | RSS, NMT, direct buffers |
| Flush CPU tăng theo thời gian | Quá nhiều managed entities | Clear theo chunk, Session ngắn |

## 48. Cấu hình baseline minh họa

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 30000

  jpa:
    properties:
      hibernate:
        generate_statistics: true
        jdbc:
          batch_size: 50
          fetch_size: 200
        order_inserts: true
        order_updates: true
        default_batch_fetch_size: 32
        query:
          fail_on_pagination_over_collection_fetch: true
~~~

Đây là baseline minh họa, không phải cấu hình production phổ quát. Trước khi dùng:

- Tính tổng connection budget của tất cả replicas.
- So với database max connections và reserve.
- Kiểm tra Hibernate/JDBC driver versions.
- Chạy baseline load test.
- Quan sát heap/GC/pool/DB.
- Chỉ thay một nhóm settings mỗi lần.
- Ghi lại latency, throughput và error rate.

Không bật statistics và SQL logging chi tiết mãi mãi nếu overhead chưa được đánh giá.

## 49. Quy trình điều tra endpoint chậm

Giả sử endpoint GET orders có p99 tăng từ 300 ms lên 3 giây khi concurrency tăng.

1. **Xác nhận latency:** p50/p95/p99, throughput, errors và workload có thay đổi không?
2. **Xem pool:** active/max/pending/acquisition/usage. Có chờ connection không?
3. **Xem database:** query duration, CPU, lock waits, I/O, deadlocks.
4. **Xem Hibernate:** statement count, entity load/fetch, flush count. Có N+1 không?
5. **Xem JVM:** heap after GC, allocation, pause, blocked threads.
6. **Xem query plan:** index, join, sort, cardinality.
7. **Đặt giả thuyết:** ví dụ N+1 làm connection usage tăng.
8. **Thay một yếu tố:** batch fetch hoặc DTO projection.
9. **Chạy lại cùng workload:** so sánh p95/p99, throughput, memory và DB CPU.
10. **Giữ thay đổi khi tổng thể tốt hơn** và correctness vẫn được bảo đảm.

Đừng tăng Hikari max pool chỉ vì Pending cao trước khi biết DB đang làm gì.

## 50. Benchmark report có thể lặp lại

| Trường | Nội dung cần ghi |
| --- | --- |
| Commit/build | Version ứng dụng |
| JVM | Version, heap limits, GC |
| Hibernate | Version và key settings |
| JDBC driver | Vendor/version |
| Database | Version, CPU/RAM, connection limit |
| Pool | Provider, max/min, timeout |
| Dataset | Rows, distribution, indexes |
| Workload | Read/write mix, query mix |
| Concurrency | Users/workers/transactions |
| Warm-up | Duration và cache strategy |
| Measurement | Duration/steady state |
| Results | Throughput, p50/p95/p99, errors |
| Resources | Heap, GC, pool, DB |
| Changes | Settings đã thay |
| Notes | Limits, anomalies, test environment |

Lưu kết quả để so sánh theo thời gian. Không so hai benchmark nếu dataset, cache state, DB resources hoặc concurrency profile khác nhau mà không ghi rõ.

## 51. Chọn kỹ thuật theo triệu chứng

| Vấn đề | Kỹ thuật đáng xem xét |
| --- | --- |
| Heap tăng khi batch insert | Flush/clear theo chunk, transaction chunks |
| Nhiều entity không cần update | DTO projection, read-only entities |
| N+1 | Batch fetching, entity graph, fetch join có chọn lọc |
| DML round trips nhiều | JDBC batching |
| Export lớn | Keyset pagination, scroll/JDBC streaming |
| Pool pending cao | Giảm connection hold time, query/lock tuning, capacity |
| DB quá nhiều concurrent sessions | Giới hạn pool/workers, backpressure |
| Optimistic failures | Xem conflict rate, retry semantics, data model |
| Deadlocks | Lock order, transaction duration, indexes |
| L2 cache memory tăng | Region bounds/expiry và cache only useful data |
| Query p99 cao | Execution plan, DB waits, hydration, GC |

## 52. Những anti-patterns cần tránh

**Một Session dùng toàn application:**

~~~java
static Session session;
~~~

Session không thread-safe và persistence context sẽ phình lên.

**Flush nhưng không clear:** flush không giải phóng managed entities.

**Một transaction cho batch không giới hạn:** có thể giữ locks, connection và transaction log lâu dù đã clear L1.

**Tăng pool để chữa mọi latency:** nếu DB bão hòa, thêm connections có thể tăng contention.

**Một pool mỗi request hoặc mỗi Session:** tạo connection churn và resource exhaustion.

**Fetch join tất cả collections:** có thể nhân rows, tăng heap và phá pagination.

**Bật L2 cache cho mọi entity:** cache có cost và invalidation; không phải dữ liệu nào cũng có reuse tốt.

**Gọi remote API trong transaction:** giữ connection/locks trong lúc chờ network.

**Chia sẻ Session giữa threads:** làm hỏng persistence context và transaction semantics.

**Chỉ nhìn average latency:** che tail latency và trải nghiệm p99.

## 53. Checklist đo hiệu năng trước production

- Có workload đại diện read/write mix và dữ liệu production.
- Có baseline throughput, p50/p95/p99 và error rate.
- Theo dõi heap sau GC, allocation, GC pauses và container RSS.
- Đo entity load/fetch, query count, flush count và prepared statements.
- Đo pool active/idle/pending, acquisition/usage time và timeout.
- Đo DB CPU, I/O, lock waits, deadlocks và active sessions.
- Session/EntityManager có scope ngắn và không chia sẻ threads.
- Batch jobs có flush/clear và transaction chunk policy.
- Large reads không materialize vô hạn.
- JDBC batch size/fetch size được đo trên driver thật.
- N+1 và fetch join pagination được kiểm soát.
- Tổng pool connections của replicas nằm trong DB budget.
- Worker concurrency phù hợp pool và DB capacity.
- Transaction không giữ connection khi chờ remote calls.
- Optimistic/pessimistic locking phù hợp business invariant.
- L2/query/application cache có giới hạn và metrics.
- Load test có warm-up, ramp, steady, spike và soak.
- Có test hot rows/tenant skew và background jobs đồng thời.
- Có benchmark report ghi rõ môi trường và settings.
- Mọi tuning được so sánh trên cùng workload.

## 54. Tổng kết

Đánh giá Hibernate dưới tải cần xem đồng thời **heap/persistence context, connection pool, transaction và database concurrency**.

1. Session giữ L1 persistence context, managed entities, collection state và dirty-check information; Session dài hạn có thể làm heap tăng.
2. flush() gửi pending changes xuống DB nhưng **không** giải phóng managed objects; dùng clear() sau flush khi xử lý chunks.
3. Một transaction dài vẫn giữ locks/connection/log resources dù persistence context đã clear.
4. DTO projection, keyset pagination, scroll/fetch size và batch processing phù hợp cho dữ liệu lớn.
5. JDBC batch size khác JDBC fetch size; identity generator có thể hạn chế insert batching.
6. Pool size dựa trên DB capacity và connection hold time, không đơn giản bằng số application threads.
7. Tổng pool max của mọi replicas phải nằm trong database connection budget.
8. Pool pending/active cần đối chiếu SQL duration, lock waits và connection leaks.
9. Session không thread-safe; mỗi unit of work cần persistence context riêng.
10. Optimistic/pessimistic locking và isolation level có trade-offs về throughput/correctness.
11. Hibernate statistics, Micrometer, JVM profiling và database metrics phải được quan sát cùng nhau.
12. Load tests cần realistic dataset, warm-up, ramp, steady, spike và soak phases.
13. Theo dõi p95/p99, không chỉ average latency.
14. Tối ưu một giả thuyết mỗi lần và so sánh bằng cùng workload.
15. Không dùng tăng heap, pool size hoặc cache như cách chữa mọi vấn đề.

Mục tiêu không phải làm đẹp một metric riêng lẻ. Mục tiêu là giữ **latency, throughput, memory và correctness ổn định ở concurrency mà hệ thống thực sự cần phục vụ**.

## Tài liệu tham khảo

- [Hibernate ORM 6.6 User Guide — Batch processing](https://docs.hibernate.org/orm/6.6/userguide/html_single/)
- [Hibernate ORM 7.2 User Guide — Batch processing and fetching](https://docs.hibernate.org/orm/7.2/userguide/html_single/)
- [Hibernate ORM 7.2 Javadocs — Statistics](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/stat/Statistics.html)
- [Hibernate ORM 6.6 Javadocs — Session](https://docs.hibernate.org/orm/6.6/javadocs/org/hibernate/Session.html)
- [Hibernate ORM 7.2 Javadocs — Session](https://docs.hibernate.org/orm/7.2/javadocs/org/hibernate/Session.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby)
- [HikariCP — Pool sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing)
- [Spring Boot — Metrics and Actuator](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)
- [Micrometer — JVM metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html)
- [Java Flight Recorder — Oracle documentation](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.pdf)
- [PostgreSQL — Monitoring database activity](https://www.postgresql.org/docs/current/monitoring.html)

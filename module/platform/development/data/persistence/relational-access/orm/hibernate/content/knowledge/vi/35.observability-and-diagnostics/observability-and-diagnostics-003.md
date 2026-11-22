# Thống kê SessionFactory và các chỉ số tải thực thể hoặc tập hợp trong Hibernate ORM

Khi một API chậm, chúng ta cần biết Hibernate thực sự đã làm gì: nạp bao nhiêu thực thể (*entity*), khởi tạo bao nhiêu tập hợp (*collection*), chạy bao nhiêu truy vấn, có phát sinh N+1 hay không, và bộ nhớ đệm có giúp giảm số lần đọc database không. Nhìn vào số method repository được gọi thường không đủ: Hibernate có thể sinh SQL khi lazy loading, trước lúc flush, trong cascade, khi cấp phát identifier hoặc do fetch plan.

Hibernate ORM cung cấp **Statistics API**, thường truy cập qua `SessionFactory.getStatistics()`, để quan sát các sự kiện ở tầng ORM. Các nhóm chỉ số tiêu biểu là:

- Entity: load, fetch, insert, update, delete, optimistic locking failure.
- Collection: load, fetch, update, recreate, remove.
- Query: execution count, thời gian thực thi được thống kê, query cache.
- JDBC/Session: prepare statement, flush, session open/close, connection, transaction.
- Cache: second-level cache hit/miss/put, query cache hit/miss/put.
- Statistics chi tiết theo entity name, collection role, query string và cache region tùy Hibernate version.

**Quan trọng:** Một SQL SELECT có thể tải 200 entities; một collection gồm 500 phần tử vẫn là **một collection instance**; một lần query HQL có thể kéo theo 20 SQL SELECT khác do lazy loading. Vì vậy **load, fetch, query execution và prepared statement không phải những phép đếm tương đương**.

Bài học này giới thiệu cách bật/lấy `Statistics`, diễn giải đúng từng counter, truy tìm N+1, phân biệt batch fetching với JDBC batching, đọc cache/query statistics, đo một use case trong integration test, kết nối monitoring và tránh các kết luận sai từ số liệu toàn `SessionFactory`.

---

## 1. Statistics ở đâu trong kiến trúc Hibernate?

Đường đi của một use case:

```text
HTTP / Scheduled Job
        |
        v
Application Service
        |
        v
EntityManager / Session
        |
        +-- JPQL/HQL/Criteria
        +-- find/getReference
        +-- lazy entity/collection loading
        +-- dirty checking/cascade
        |
        v
Hibernate SQL generation
        |
        v
JDBC prepare/bind/execute
        |
        v
Database

SessionFactory Statistics
        ^
        | ORM events từ nhiều Sessions
        +-- Entity/collection counters
        +-- Query statistics
        +-- Cache statistics
        +-- Session/JDBC preparation counters
```

Một `SessionFactory` có thể được dùng bởi nhiều `Session`/`EntityManager` và rất nhiều transactions. Các counters của `Statistics` là **thống kê tích lũy phạm vi SessionFactory**, không phải mặc định theo một HTTP request.

### 1.1. SessionFactory khác Session

- `SessionFactory`: object có vòng đời dài, giữ mapping metadata và cung cấp Session; statistics thuộc phạm vi này.
- `Session`: unit of work có persistence context/first-level cache, quản lý entity instances.
- `EntityManager`: API Jakarta Persistence; khi provider là Hibernate có thể `unwrap` để dùng Hibernate APIs.

Một ứng dụng nhiều EntityManagerFactories có thể có nhiều SessionFactories và nhiều bộ statistics độc lập.

### 1.2. Một thống kê không bao trùm toàn cụm

Nếu ứng dụng chạy ba pods:

```text
Pod 1 -> SessionFactory 1 -> Statistics 1
Pod 2 -> SessionFactory 2 -> Statistics 2
Pod 3 -> SessionFactory 3 -> Statistics 3
```

Không thể lấy `getEntityLoadCount()` ở Pod 1 rồi cho rằng đó là tổng toàn hệ thống. Muốn metrics toàn cụm, cần exporter/monitoring tổng hợp theo instance.

## 2. Bật Hibernate statistics

Cấu hình Hibernate:

```properties
hibernate.generate_statistics=true
```

Spring Boot truyền Hibernate properties qua:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Ví dụ YAML:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        generate_statistics: true
```

Cú pháp thuộc Hibernate configuration; ứng dụng có nhiều persistence units phải bảo đảm property được đặt trên đúng factory.

### 2.1. Xác minh đã bật

```java
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

Statistics stats = sessionFactory.getStatistics();

if (!stats.isStatisticsEnabled()) {
    throw new IllegalStateException(
        "Hibernate statistics are disabled"
    );
}
```

Một counter bằng 0 khi statistics **chưa bật** không chứng minh ứng dụng không chạy truy vấn.

### 2.2. Bật/tắt bằng API

```java
stats.setStatisticsEnabled(true);
```

Cách này tác động tới việc thu thập trên SessionFactory, không chỉ thread đang gọi. Trong production, không nên mở một endpoint công khai cho phép bất kỳ user nào bật/tắt statistics hoặc reset counters.

### 2.3. Overhead

Statistics tạo chi phí cập nhật counters, có thể lưu metadata theo query và kết hợp logging. Tác động cụ thể tùy phiên bản, workload và số query shapes. Bật trong development/test là hợp lý; production cần đánh giá overhead, memory, access control và metrics cardinality.

## 3. Lấy Statistics trong ứng dụng Java/JPA

Native Hibernate:

```java
SessionFactory factory = ...;

Statistics stats = factory.getStatistics();
```

Qua JPA EntityManagerFactory:

```java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory factory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics stats = factory.getStatistics();
```

Đây là Hibernate-specific API, không phải JPA chuẩn. Nếu provider khác Hibernate, unwrap có thể không hoạt động.

Một Spring component:

```java
@Component
public final class HibernateDiagnostics {

    private final Statistics statistics;

    public HibernateDiagnostics(
            EntityManagerFactory emf) {

        SessionFactory sf = emf.unwrap(
            SessionFactory.class
        );

        this.statistics = sf.getStatistics();
    }

    public Statistics statistics() {
        return statistics;
    }
}
```

Không expose trực tiếp toàn bộ `Statistics` qua REST cho user bên ngoài; thông tin query/entity/region có thể tiết lộ cấu trúc hệ thống.

## 4. Entity load, fetch, insert, update, delete

Các methods phổ biến:

```java
long loads = stats.getEntityLoadCount();
long fetches = stats.getEntityFetchCount();
long inserts = stats.getEntityInsertCount();
long updates = stats.getEntityUpdateCount();
long deletes = stats.getEntityDeleteCount();
long optimisticFailures =
    stats.getOptimisticFailureCount();
```

Tên API có thể biến đổi nhẹ theo Hibernate version. Mục tiêu là hiểu từng counter:

| Chỉ số | Ý nghĩa thực dụng | Không được hiểu thành |
|---|---|---|
| Entity load | Entity instances được ORM load/hydrate theo thống kê | Số SELECT |
| Entity fetch | Những entity fetch operations theo semantics Hibernate, thường gắn với lazy association/lookup | Mọi entity xuất hiện trong kết quả HQL |
| Entity insert | Những inserts qua entity lifecycle được thống kê | Số JDBC round trips |
| Entity update | Những updates qua entity lifecycle | Số setter calls |
| Entity delete | Những deletes qua entity lifecycle | Tất cả physical rows xóa bởi DB |
| Optimistic failure | Những optimistic locking failures Hibernate ghi nhận | Mọi database deadlock hoặc business conflict |

### 4.1. Một SELECT, nhiều entity loads

Ví dụ:

```java
List<Customer> customers = em.createQuery("""
    select c
    from Customer c
    where c.active = true
    """, Customer.class)
    .getResultList();
```

Nếu query trả 100 Customer entities chưa được managed/cached, `entityLoadCount` có thể tăng khoảng 100 trong khi SQL có thể chỉ là một SELECT.

**Entity load là phép đo ở tầng đối tượng, không phải phép đếm câu SQL.**

### 4.2. Entity fetch khác entity load

Nếu root query trả 20 PurchaseOrder entities và sau đó code lần lượt truy cập 20 lazy Customer associations chưa có trong context/cache, Hibernate có thể tạo thêm SELECTs để fetch Customers.

Entity fetch counter có thể tăng trong pattern này. Tuy nhiên nó không mặc định tăng 20 chỉ vì root query trả 20 Orders. Phải xem SQL và exact mapping để diễn giải.

### 4.3. Query scalar không load entity

```java
Long count = em.createQuery("""
    select count(c)
    from Customer c
    """, Long.class)
    .getSingleResult();
```

Câu query có thể chạm database nhưng không hydrate Customer entities, nên entity load count có thể không tăng.

### 4.4. Bulk DML không là per-entity update

```java
int changed = em.createQuery("""
    update Customer c
    set c.active = false
    where c.expiredAt < :cutoff
    """)
    .setParameter("cutoff", cutoff)
    .executeUpdate();
```

Bulk HQL UPDATE không duyệt từng managed Customer để dirty-check và gọi callback như entity lifecycle. Không dùng `entityUpdateCount` làm số rows thực sự được bulk-updated.

## 5. Collection load và collection fetch

Các methods:

```java
long loads = stats.getCollectionLoadCount();
long fetches = stats.getCollectionFetchCount();
long updates = stats.getCollectionUpdateCount();
long recreated = stats.getCollectionRecreateCount();
long removed = stats.getCollectionRemoveCount();
```

| Chỉ số | Ý nghĩa | Cần tránh |
|---|---|---|
| Collection load | Số persistent collection instances được initialized/loaded | Không phải tổng số phần tử |
| Collection fetch | Các collection fetch operations theo Hibernate statistics | Không đơn giản bằng số query do application gọi |
| Collection update | Collection update operations do ORM ghi nhận | Không bằng số child entity updates |
| Collection recreate | Collection recreation operations | Không đếm số Java ArrayList được tạo |
| Collection remove | Collection removal operations | Không nhất thiết bằng số DELETE rows |

### 5.1. Một collection có 500 phần tử vẫn là một collection

```java
PurchaseOrder order = em.find(
    PurchaseOrder.class, orderId
);

int lineCount = order.getLines().size();
```

Nếu collection chưa initialized, Hibernate có thể tải 500 OrderLine rows. Collection load count có thể tăng một cho `PurchaseOrder.lines`; entity load count có thể tăng theo số OrderLine entities.

Với extra-lazy mapping hoặc collection đã được cache, `size()` có thể chạy theo đường khác. Không lấy ví dụ này làm công thức tuyệt đối cho mọi mapping.

### 5.2. Collection load khác separate fetch

`JOIN FETCH` có thể initialize collections trong chính root query. Khi đó số collections loaded vẫn tăng, nhưng số separate SELECTs do lazy collection fetch có thể giảm mạnh.

Đây là ví dụ vì sao **giảm collection fetch count không bắt buộc giảm collection load count**.

### 5.3. Collection statistics là tín hiệu quan trọng của N+1

Nhiều lazy to-many associations được initialized tuần tự có thể làm `collectionFetchCount` tăng theo số root owners. Kết hợp với `prepareStatementCount` và SQL logs để xác nhận có N+1 thật hay không.

## 6. EntityStatistics theo loại entity

Global entity counts chỉ cho biết tổng. Muốn biết entity nào gây tải nhiều:

```java
import org.hibernate.stat.EntityStatistics;

String entityName =
    "com.example.domain.PurchaseOrder";

EntityStatistics es =
    stats.getEntityStatistics(entityName);

long loads = es.getLoadCount();
long fetches = es.getFetchCount();
long inserts = es.getInsertCount();
long updates = es.getUpdateCount();
long deletes = es.getDeleteCount();
```

Entity name phải khớp với metadata của Hibernate, đặc biệt khi dùng `@Entity(name = "...")`.

Có thể khám phá tên entity ở những versions cung cấp API:

```java
for (String name : stats.getEntityNames()) {
    System.out.println(name);
}
```

### 6.1. Một màn hình trả 20 Orders nhưng load 2.000 lines

Per-entity stats có thể cho thấy `PurchaseOrder` load 20 và `OrderLine` load 2.000. Đó là tín hiệu **over-fetching** ngay cả khi SQL chỉ có một câu JOIN.

### 6.2. Entity load không chỉ đọc từ database

L2 cache có thể cung cấp entity state; khi materialize entity vào context, một số load counters vẫn phản ánh ORM load. Để xác định SQL thực tế, xem statement/cache metrics riêng.

### 6.3. Không dùng entity names làm metric label vô hạn

Số entity classes thường hữu hạn, nhưng tuyệt đối không thêm entity ID, user ID hoặc tenant ID tùy ý vào metrics labels. Đó là high-cardinality và có thể tiết lộ dữ liệu.

## 7. CollectionStatistics theo association role

Một mapping:

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @OneToMany(mappedBy = "order")
    private List<OrderLine> lines = new ArrayList<>();
}
```

Hibernate nhận diện collection theo **role**, thường ở dạng:

```text
com.example.domain.PurchaseOrder.lines
```

Đọc thống kê theo role:

```java
import org.hibernate.stat.CollectionStatistics;

CollectionStatistics cs =
    stats.getCollectionStatistics(
        "com.example.domain.PurchaseOrder.lines"
    );

long loadCount = cs.getLoadCount();
long fetchCount = cs.getFetchCount();
long updateCount = cs.getUpdateCount();
```

### 7.1. Role không phải table name

`PurchaseOrder.lines` là collection role; `order_lines` là tên bảng. Cùng một bảng child có thể tham gia nhiều associations khác nhau; Hibernate thống kê theo mapping role.

### 7.2. Xác định role từ runtime

```java
for (String role : stats.getCollectionRoleNames()) {
    System.out.println(role);
}
```

Phù hợp cho development/test. Khi triển khai, xác nhận method tồn tại trong Hibernate version đang dùng và hạn chế xuất metadata qua endpoint public.

### 7.3. Tìm đúng collection gây N+1

Global `collectionFetchCount` có thể tăng từ `Order.lines`, `Order.shipments` và `Customer.addresses`. Per-role counters giúp khoanh vùng association gây fetch nhiều.

## 8. Query execution statistics

Các methods thường gặp:

```java
long queryExecutions = stats.getQueryExecutionCount();
long maxQueryTime = stats.getQueryExecutionMaxTime();
```

Để đọc theo query string:

```java
import org.hibernate.stat.QueryStatistics;

String hql =
    "select o from PurchaseOrder o where o.status = :status";

QueryStatistics qs = stats.getQueryStatistics(hql);

long executed = qs.getExecutionCount();
long minTime = qs.getExecutionMinTime();
long avgTime = qs.getExecutionAvgTime();
long maxTime = qs.getExecutionMaxTime();
```

Query time units/API details cần đối chiếu Hibernate version; các API truyền thống dùng milliseconds nhưng timing/precision có thể thay đổi theo implementation.

### 8.1. QueryExecutionCount không đếm mọi SELECT

Một service có một HQL query tải 20 Orders, sau đó 20 lazy collection fetches. `queryExecutionCount` có thể phản ánh chủ yếu query do ứng dụng gọi, không bao gồm mỗi generated lazy SELECT như một HQL execution.

Vì vậy **không dùng `queryExecutionCount` một mình để chặn N+1**.

### 8.2. Key của query statistics phải khớp

Whitespace, query comments, Criteria-generated query keys và native SQL có thể khiến key thực tế khác string bạn dự đoán.

Một số Hibernate versions có:

```java
String[] queries = stats.getQueries();

for (String queryKey : queries) {
    QueryStatistics details =
        stats.getQueryStatistics(queryKey);
}
```

Không expose raw query strings công khai; có thể chứa schema details hoặc literals do application tạo.

### 8.3. Max query time chưa đủ phân tích latency

Một query max time cao có thể do database lock, network stall, result hydration hoặc outlier. Muốn biết nguyên nhân, cần JDBC tracing và database `EXPLAIN`/slow query logs.

## 9. Prepared statement count: một chỉ số đặc biệt hữu ích

```java
long prepared = stats.getPrepareStatementCount();
```

Đây là số lần Hibernate chuẩn bị JDBC statements theo Statistics instrumentation.

### 9.1. Một request có thể prepare rất nhiều statements

```text
SELECT purchase_orders         1
SELECT order_lines for #1      1
SELECT order_lines for #2      1
...
SELECT order_lines for #20     1
-------------------------------
Total                          21
```

`prepareStatementCount` delta trong test cô lập có thể tăng tương ứng, dù application chỉ gọi một HQL.

### 9.2. Không bằng số câu SQL execute thành công

- Statement được prepare nhưng có thể execute lỗi hoặc rollback.
- Một PreparedStatement có thể dùng nhiều parameter sets trong JDBC batch.
- JDBC driver có thể reuse/caching riêng.
- DB triggers chạy SQL nội bộ không hiện như Hibernate prepare.
- `JdbcTemplate`/JDBC ngoài Hibernate không được tính trong ORM Statistics.
- Một SELECT có thể trả nhiều rows.

Đặt tên metric là `preparedStatements`, không gọi nhầm `executedSqlCount`.

### 9.3. Không đo database round trips bằng một counter

JDBC batching, driver protocol, statement reuse và connection behavior quyết định số round trips. Dùng JDBC instrumentation/driver/database metrics khi cần con số thực tế.

## 10. Session, connection, flush và transaction statistics

Những counters phổ biến:

```java
long opens = stats.getSessionOpenCount();
long closes = stats.getSessionCloseCount();
long flushes = stats.getFlushCount();
long connections = stats.getConnectCount();
long transactions = stats.getTransactionCount();
long successfulTransactions =
    stats.getSuccessfulTransactionCount();
```

### 10.1. Session opened không bằng HTTP requests

Một request có thể dùng nhiều persistence contexts hoặc không cần truy cập DB. Một scheduler cũng mở Session. Đừng suy ra user traffic trực tiếp từ session-open counter.

### 10.2. Flush không phải commit

```java
em.persist(order);
em.flush();
em.clear();
```

`flush()` đồng bộ pending actions xuống DB nhưng không commit. `clear()` detach managed entities, không commit và không reset Statistics.

Một transaction có thể có nhiều flushes và chỉ một commit. Ngược lại, flush do Hibernate tự thực hiện tại commit không nhất thiết tương ứng một explicit `em.flush()` trong code.

### 10.3. Flush count cao chưa chắc là lỗi

Flush trước một query cần đọc pending changes hoặc theo batch chunks có thể hợp lý. Nhưng flush sau mỗi entity trong loop có thể giảm hiệu quả JDBC batching.

Kết hợp `flushCount` với entity update/insert counts, JDBC timings và transaction duration.

### 10.4. Connection count không phải connection leak detector

Một Session có thể acquire connection muộn hoặc reuse theo connection handling mode. So sánh Session open/close và connect counters chỉ cho tín hiệu. Connection pool metrics, leak detection và tracing phù hợp hơn để tìm leak thực sự.

## 11. Second-level cache: hit, miss, put

Hibernate L2 cache lưu entity/collection state giữa nhiều Sessions khi mapping và cache provider được cấu hình phù hợp.

```java
long hits =
    stats.getSecondLevelCacheHitCount();

long misses =
    stats.getSecondLevelCacheMissCount();

long puts =
    stats.getSecondLevelCachePutCount();
```

| Counter | Ý nghĩa |
|---|---|
| Hit | Lookup tìm thấy entry trong Hibernate L2 |
| Miss | Lookup không tìm thấy entry phù hợp |
| Put | Một entry được đưa vào L2 |

### 11.1. Phân biệt L1 và L2

Nếu hai lần `em.find(Customer.class, id)` xảy ra trong cùng persistence context, lần thứ hai có thể trả managed entity từ L1 mà không lookup L2.

`L2 hit count` không phải phép đếm mọi lần “tránh được SELECT”.

### 11.2. Hit rate

\[
\text{Hit rate} =
\frac{\Delta hits}{\Delta hits + \Delta misses}
\]

Chỉ tính khi mẫu số dương và hai deltas thuộc cùng window có ý nghĩa.

Hit rate 95% không bảo đảm endpoint nhanh nếu cached entities rất lớn, query vẫn kéo nhiều rows hoặc invalidation tốn kém.

### 11.3. Cache region

Hibernate có region-level cache statistics APIs. Tên classes/methods khác giữa Hibernate 5.x và 6.x/7.x, vì vậy không dùng ví dụ `SecondLevelCacheStatistics` cũ như API chắc chắn của bản mới. Xác nhận region name và API theo dependencies hiện tại.

### 11.4. Tenant isolation và quyền

L2 cache khi multi-tenancy được cấu hình đúng có cơ chế tenant-aware identity. Nhưng **cache hit không chứng minh actor có quyền đọc entity**; authorization ở application service vẫn phải chạy.

## 12. Query cache không phải L2 entity cache

Query cache lưu kết quả các queries được đánh dấu cacheable trong cấu hình hỗ trợ; L2 cache lưu entity/collection state.

```java
long hits = stats.getQueryCacheHitCount();
long misses = stats.getQueryCacheMissCount();
long puts = stats.getQueryCachePutCount();
```

Chỉ bật:

```properties
hibernate.cache.use_query_cache=true
```

không tự cache mọi query. Một query có thể yêu cầu hint:

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o from PurchaseOrder o
    where o.status = :status
    """, PurchaseOrder.class)
    .setParameter("status", "OPEN")
    .setHint("org.hibernate.cacheable", true)
    .getResultList();
```

Provider/configuration/cache region phải hỗ trợ và query thực sự cacheable.

### 12.1. Query cache hit vẫn có thể cần entity state

Tùy query shape và Hibernate version, cached query result có thể chứa entity identifiers; Hibernate vẫn cần hydrate entities từ L2 hoặc database.

### 12.2. Dữ liệu hay đổi có thể làm query cache ít hiệu quả

Nếu query spaces liên tục invalidated, hit rate thấp và overhead nhiều. Cần đo hit/miss/put, heap và latency trước khi bật query cache đại trà.

### 12.3. Query cache không tự biết ACL bên ngoài Hibernate

Quyền đọc theo user/tenant có thể thay đổi ở external IAM hoặc application cache. Query cache metrics không chứng minh kết quả được authorized. Query/cached view cần được scoped và invalidated theo policy riêng.

## 13. Query plan cache khác query result cache

Các phiên bản Hibernate hiện đại có query plan cache, và Statistics ở một số versions cung cấp:

```java
long planHits =
    stats.getQueryPlanCacheHitCount();

long planMisses =
    stats.getQueryPlanCacheMissCount();
```

Ba lớp khác nhau:

```text
Hibernate query plan cache
  -> tái sử dụng interpretation/plan cho HQL/Criteria

Hibernate query result cache
  -> tái sử dụng kết quả cacheable query

Hibernate L2 cache
  -> tái sử dụng entity/collection state
```

Database cũng có execution-plan cache riêng, không đồng nhất với Hibernate plan cache.

### 13.1. Dynamic query làm tăng plan misses

Không ghép raw values vào HQL string:

```java
String hql =
    "from PurchaseOrder o where o.status = '" + status + "'";
```

Dùng parameter:

```java
String hql =
    "from PurchaseOrder o where o.status = :status";

em.createQuery(hql, PurchaseOrder.class)
    .setParameter("status", status)
    .getResultList();
```

Cách này còn giúp tránh SQL injection và giảm biến thể query shape.

## 14. Mô hình ví dụ N+1 collection

Entity:

```java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    public Long getId() {
        return id;
    }

    public List<OrderLine> getLines() {
        return lines;
    }
}
```

Child:

```java
@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    private PurchaseOrder order;

    private int quantity;

    public int getQuantity() {
        return quantity;
    }
}
```

Service:

```java
@Transactional(readOnly = true)
public List<OrderDto> getOrders(Long customerId) {
    List<PurchaseOrder> orders = em.createQuery("""
        select o
        from PurchaseOrder o
        where o.customer.id = :customerId
        order by o.id
        """, PurchaseOrder.class)
        .setParameter("customerId", customerId)
        .getResultList();

    return orders.stream()
        .map(o -> new OrderDto(
            o.getId(),
            o.getLines().stream()
                .map(OrderLine::getQuantity)
                .toList()
        ))
        .toList();
}
```

Giả sử có 20 Orders và mỗi Order có collection lazy chưa initialized.

### 14.1. Trường hợp cache lạnh, không batch fetching

Có thể có một SELECT Orders và 20 SELECTs lines: mô hình N+1. Số liệu **minh họa**, không phải kết quả Hibernate bảo đảm trong mọi mapping:

| Counter delta | Dự kiến tương đối |
|---|---:|
| Prepared JDBC statements | Khoảng 21 |
| Collection fetches | Khoảng 20 |
| Collection loads | Khoảng 20 |
| Query executions | Có thể chỉ khoảng 1 |
| Entity loads | Khoảng Orders + OrderLines được hydrate |

### 14.2. Vì sao chỉ nhìn queryExecutionCount dễ bỏ sót?

Service chỉ gọi một HQL query; phần còn lại phát sinh khi mapper gọi `getLines()`. Lazy collection SQL không nhất thiết được tính như một query execution ở HQL statistics.

### 14.3. Đọc cùng SQL logs

```sql
select ... from purchase_orders where customer_id = ?
select ... from order_lines where order_id = ?
select ... from order_lines where order_id = ?
select ... from order_lines where order_id = ?
```

Những query shapes lặp lại cùng số root owners là dấu hiệu N+1. Statistics giúp cảnh báo, còn SQL trace xác nhận hình dạng.

## 15. Tối ưu bằng JOIN FETCH

```java
List<PurchaseOrder> orders = em.createQuery("""
    select distinct o
    from PurchaseOrder o
    left join fetch o.lines
    where o.customer.id = :customerId
    order by o.id
    """, PurchaseOrder.class)
    .setParameter("customerId", customerId)
    .getResultList();
```

Hibernate có thể hydrate Orders và lines từ một SQL join result.

### 15.1. Counter nào giảm?

Có thể giảm:

- `prepareStatementCount`.
- Separate `collectionFetchCount`.

Không nhất thiết giảm:

- `collectionLoadCount` vì vẫn initialize collections.
- `entityLoadCount` vì vẫn hydrate OrderLine entities.
- Tổng bytes truyền từ DB, nếu JOIN nhân rows.

### 15.2. Cartesian product

Fetch hai to-many collections của cùng parent có thể nhân SQL rows: 10 lines × 20 shipments = 200 SQL rows cho một Order. Một số bag mappings có thể gặp `MultipleBagFetchException`.

**Một SQL statement không phải luôn tốt hơn nhiều SELECTs.**

### 15.3. Pagination

Fetch join collection cùng limit/offset có thể khiến Hibernate paginate trong memory hoặc cảnh báo/lỗi. Với paginated root list, thường query page IDs trước rồi fetch associations của IDs đó.

## 16. Tối ưu bằng @BatchSize

```java
import org.hibernate.annotations.BatchSize;

@OneToMany(mappedBy = "order")
@BatchSize(size = 20)
private List<OrderLine> lines = new ArrayList<>();
```

Khi initialize một collection, Hibernate có thể fetch nhiều collections thuộc những owners khác đang chờ trong persistence context:

```sql
select ...
from order_lines
where order_id in (?, ?, ?, ...);
```

### 16.1. Khác biệt counters

Vẫn có thể có 20 collections loaded, nhưng các SQL SELECT fetch được gom theo batches. `prepareStatementCount` giảm, trong khi `collectionLoadCount` có thể vẫn khoảng 20.

Không mặc định `@BatchSize(20)` bảo đảm đúng một query cho 20 owners. Cache, batch queue, DB IN limits và Hibernate version có thể làm số SQL khác.

### 16.2. JDBC batching khác batch fetching

- `hibernate.jdbc.batch_size`: gom nhiều DML parameter sets khi ghi.
- `@BatchSize` hoặc `hibernate.default_batch_fetch_size`: gom lazy loads khi đọc.

Tăng JDBC batch size **không tự giải quyết** N+1 SELECT collections.

## 17. Tối ưu bằng SUBSELECT fetching

Một mapping:

```java
import org.hibernate.annotations.Fetch;
import org.hibernate.annotations.FetchMode;

@OneToMany(mappedBy = "order")
@Fetch(FetchMode.SUBSELECT)
private List<OrderLine> lines = new ArrayList<>();
```

Trong những use cases phù hợp, Hibernate có thể fetch collections của nhiều owners bằng SQL dựa trên subselect của query gốc.

Ưu điểm: giảm số separate selects khi cần collections cho cả tập parents.

Rủi ro: có thể tải nhiều collections/elements hơn API cần, đặc biệt nếu tập parents rộng. Vì vậy cần xem **prepared statements, collection loads, entity loads, heap và DB time**, không chỉ số SQL giảm.

## 18. Lazy @ManyToOne và entity fetch counter

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o from PurchaseOrder o
    """, PurchaseOrder.class).getResultList();

for (PurchaseOrder o : orders) {
    System.out.println(o.getCustomer().getName());
}
```

Nếu nhiều Customers khác nhau chưa được managed/cached, truy cập lazy to-one có thể phát sinh nhiều SELECT. Khi đó `entityFetchCount` và `prepareStatementCount` có thể tăng.

Nếu 100 Orders cùng tham chiếu một Customer, L1 identity map có thể làm Customer chỉ cần tải một lần. Vì vậy N+1 thực tế phụ thuộc số distinct targets, cache và fetch plan.

### 18.1. JOIN FETCH to-one

```java
List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    join fetch o.customer
    where o.status = :status
    """, PurchaseOrder.class)
    .setParameter("status", "OPEN")
    .getResultList();
```

To-one join fetch thường không nhân root SQL rows như to-many, nhưng vẫn hydrate Customer entities. Nếu DTO chỉ cần `customerId`, một projection có thể hiệu quả hơn.

## 19. EntityGraph và thống kê

JPA `EntityGraph` xác định fetch plan theo use case:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders = em.createQuery("""
    select o
    from PurchaseOrder o
    where o.status = :status
    """, PurchaseOrder.class)
    .setParameter("status", "OPEN")
    .setHint("jakarta.persistence.fetchgraph", graph)
    .getResultList();
```

Graph có thể giảm lazy fetches ở những đường ORM nhất định. Nhưng không hứa luôn một SQL; provider/mapping/dialect quyết định execution plan.

Đo:

- Query execution count.
- Prepared statements.
- Entity fetches/loads.
- Collection fetches nếu graph có association to-many.
- DTO mapping time, heap, response latency.

Không chuyển mọi association sang EAGER chỉ để một endpoint ít query hơn.

## 20. Snapshot counters: cách đo trong test

Một record đơn giản:

```java
import org.hibernate.stat.Statistics;

public record StatsSnapshot(
    long prepared,
    long entityLoads,
    long entityFetches,
    long collectionLoads,
    long collectionFetches,
    long queryExecutions
) {
    public static StatsSnapshot capture(Statistics s) {
        return new StatsSnapshot(
            s.getPrepareStatementCount(),
            s.getEntityLoadCount(),
            s.getEntityFetchCount(),
            s.getCollectionLoadCount(),
            s.getCollectionFetchCount(),
            s.getQueryExecutionCount()
        );
    }

    public StatsSnapshot minus(StatsSnapshot before) {
        return new StatsSnapshot(
            prepared - before.prepared,
            entityLoads - before.entityLoads,
            entityFetches - before.entityFetches,
            collectionLoads - before.collectionLoads,
            collectionFetches - before.collectionFetches,
            queryExecutions - before.queryExecutions
        );
    }
}
```

Sử dụng:

```java
StatsSnapshot before = StatsSnapshot.capture(stats);

List<OrderDto> result =
    orderReadService.getOrders(customerId);

StatsSnapshot delta =
    StatsSnapshot.capture(stats).minus(before);
```

### 20.1. Điều kiện cần thiết

Để delta phản ánh use case:

- Không có requests/jobs khác dùng cùng factory trong measurement.
- Fixture setup đã kết thúc.
- Persistence context sạch hoặc state được xác định.
- Cache cold/warm theo kịch bản test.
- Statistics được bật.
- Không test khác gọi `stats.clear()` song song.

### 20.2. Vì sao production delta không chính xác cho request?

SessionFactory counters được tăng bởi **mọi threads**. Khi thread A chụp before/after, thread B có thể đang import dữ liệu. Delta A không còn chỉ thuộc request A.

Để đo theo request, dùng tracing/JDBC instrumentation scoped to request hoặc dedicated profiler.

### 20.3. Snapshot không nguyên tử

Đọc sáu getter nối tiếp nhau không tạo một snapshot atomic trong hệ thống đang thay đổi. Với test tuần tự điều này thường chấp nhận; với monitoring concurrent, xem số liệu theo windowed rates.

## 21. Viết integration test chặn N+1

Ví dụ Spring Boot test:

```java
@SpringBootTest
class OrderReadStatsTest {

    @Autowired
    EntityManagerFactory emf;

    @Autowired
    OrderReadService service;

    @Test
    void loadsOrdersWithoutOneCollectionQueryPerOrder() {
        Statistics stats = emf
            .unwrap(SessionFactory.class)
            .getStatistics();

        assertThat(stats.isStatisticsEnabled()).isTrue();

        // Fixture đã được tạo/commit trước test này.
        // Service dùng persistence context sạch.
        stats.clear();

        List<OrderDto> result =
            service.getOrders(TEST_CUSTOMER_ID);

        assertThat(result).hasSize(20);

        assertThat(stats.getCollectionFetchCount())
            .isLessThanOrEqualTo(2);

        assertThat(stats.getPrepareStatementCount())
            .isLessThanOrEqualTo(5);
    }
}
```

Các ngưỡng `2` và `5` chỉ **minh họa** sau khi biết fetch strategy, query count và fixtures cụ thể. Chúng không phải limits Hibernate mặc định.

### 21.1. Tách fixture setup và đo

Nếu test `@Transactional` vừa tạo Orders, giữ entities managed trong L1 rồi gọi service, code có thể tránh SQL chỉ vì setup đã nạp association. Test pass nhưng production vẫn N+1.

Cách thích hợp:

1. Tạo fixture trong transaction riêng.
2. Commit/flush, kết thúc context setup.
3. Mở context mới cho service.
4. Reset/capture counters.
5. Gọi service và assert kết quả.
6. Đọc counters.

### 21.2. Không chạy statistics tests song song trên cùng factory

`Statistics.clear()` reset counters chung. Nếu test A và B chạy đồng thời, kết quả có thể sai dù production behavior đúng.

### 21.3. Kết quả nghiệp vụ phải đúng

Không cho một “tối ưu” chỉ trả Order IDs rồi bỏ Lines cần thiết vượt qua test bằng cách giảm query counts. Assert DTO đúng và đủ dữ liệu trước khi assert performance budget.

## 22. Statistics.clear và các loại clear khác

```java
stats.clear();
```

reset statistics theo semantics của Hibernate version.

Nó **không đồng nghĩa**:

```java
entityManager.clear();
```

và cũng **không đồng nghĩa** evict L2 cache.

| Lệnh | Mục đích |
|---|---|
| `stats.clear()` | Reset statistics counters |
| `entityManager.clear()` | Detach managed entities khỏi persistence context |
| `sessionFactory.getCache().evictAllRegions()` | Evict cache regions theo Hibernate API |

Nếu test cần cold L1, phải clear/new EntityManager. Nếu test cần cold L2, cần evict cache tương ứng; reset counters không làm dữ liệu cached biến mất.

### 22.1. Không clear statistics giữa production traffic

Một reset từ admin endpoint có thể làm metrics exporter thấy counter giảm bất thường và sai rate. Trong production, ưu tiên snapshots với windowed deltas và xử lý process restart như counter reset tự nhiên.

## 23. Warm cache và cold cache: hai bài toán

Cùng một query, kết quả Statistics có thể khác khi:

- L1 đã có entity.
- L2 entity/collection cache có data.
- Query cache đã có result.
- Lazy collection đã initialized.
- Batch fetching có những pending owners khác.

### 23.1. Cold-cache test

Giúp thấy chi phí request đầu tiên, tenant mới hoặc sau cache eviction.

### 23.2. Warm-cache test

Cho biết mức tái sử dụng, cache hit behavior và correctness khi dữ liệu thay đổi.

### 23.3. Cache-disabled test

Giúp xác minh fetch plan không phụ thuộc tình cờ vào L2 để tránh N+1.

### 23.4. Không tối ưu theo một trường hợp duy nhất

Một endpoint rất nhanh khi cache nóng nhưng chậm 20 lần khi cold có thể gây p99 spike sau deploy/restart. Cần đo cả hai.

## 24. Session Metrics logging: khác Statistics API

Một số Hibernate versions có **Session Metrics** logging thông qua event listeners như `StatisticalLoggingSessionEventListener`. Log có thể chứa:

```text
Session Metrics {
    time spent acquiring JDBC connections
    time spent preparing JDBC statements
    time spent executing JDBC statements
    time spent executing JDBC batches
    time spent performing flushes
    entities/collections processed during flush
}
```

Đây là thông tin ở **Session event** level, khác với counters tích lũy trên SessionFactory.

### 24.1. Khi có ích?

- Tìm Session nào thực hiện nhiều JDBC work.
- Thấy flush duration hoặc JDBC execution timing trong môi trường thử nghiệm.
- So sánh ảnh hưởng của batching và dirty checking.

### 24.2. Không phải API tracing end-to-end

Nó không nhất thiết bao gồm thời gian HTTP security, JSON serialization, remote calls hoặc frontend. Để đo API latency, dùng service metrics/tracing.

### 24.3. Cẩn thận log flood

Nếu mỗi request đóng Session và ghi toàn bộ Session Metrics, production logs có thể bùng nổ. Bật có kiểm soát, sampling hoặc dùng metrics binder phù hợp.

## 25. Kết nối Micrometer/Actuator

Có những Hibernate metrics integrations/binders để đưa counters vào hệ sinh thái Micrometer, tùy version stack (có thể qua module Hibernate Micrometer và cấu hình Spring Boot tương ứng).

Pipeline:

```text
SessionFactory / Statistics
       |
       v
Hibernate metrics binder
       |
       v
Micrometer MeterRegistry
       |
       v
Prometheus / OTLP / Monitoring
       |
       v
Dashboard / Alert
```

### 25.1. Đúng phiên bản thư viện

Tên module/class/constructor cho metrics binder có thể khác theo Hibernate 5/6/7 và Spring Boot major version. Kiểm tra dependencies trước khi sao chép ví dụ từ tài liệu phiên bản khác.

### 25.2. Metrics nên có những nhóm nào?

- Entity loads/s, fetches/s, inserts/updates/deletes/s.
- Collection loads/s và fetches/s.
- Prepared statements/s và flushes/s.
- L2/query cache hit/miss rates.
- Query latency qua JDBC/APM.
- JVM heap/GC, DB connections/locks, API p95/p99.

### 25.3. Tránh high cardinality

Không gắn raw SQL, HQL có literals, resourceId, userId hay tenantId vào labels không kiểm soát. Các label như persistence-unit, entity-type hữu hạn, collection-role quan trọng thường dễ quản lý hơn.

## 26. Đo writes và JDBC batching

Một import:

```java
@Transactional
public void importProducts(List<ProductInput> inputs) {
    int count = 0;

    for (ProductInput input : inputs) {
        em.persist(
            new Product(input.code(), input.name())
        );

        if (++count % 50 == 0) {
            em.flush();
            em.clear();
        }
    }

    em.flush();
}
```

Hibernate JDBC batching configuration có thể gồm:

```properties
hibernate.jdbc.batch_size=50
hibernate.order_inserts=true
```

### 26.1. Những counters cần đọc

- `entityInsertCount`: số ORM insert entities.
- `flushCount`: flush operations.
- `prepareStatementCount`: JDBC statement preparations.
- Session/JDBC metrics: thời gian chuẩn bị và thực thi batches nếu instrumentation có.
- DB metrics: actual round trips/rows/time.

### 26.2. Batching có thể làm entity inserts nhiều nhưng preparations ít

Một prepared statement được dùng với nhiều parameter sets. Đây là lý do không thể lấy `prepareStatementCount` làm số rows inserted.

### 26.3. IDENTITY và sequence

`GenerationType.IDENTITY` thường cần INSERT để có ID và có thể hạn chế insert batching. SEQUENCE với pooled optimizer thường thuận lợi hơn trong một số workloads. Cần kiểm tra dialect/generator, không suy từ một counter đơn lẻ.

### 26.4. Batch size và transaction size khác nhau

Chunk size 50, JDBC batch size 25 và một transaction toàn job là ba khái niệm độc lập. `flush()/clear()` không tự commit mỗi chunk.

## 27. Query pagination và các chỉ số tải

Spring Data `Page<T>` thường có nhu cầu count query để biết total, trong khi `Slice<T>` thường tránh exact count và chỉ xác định còn trang tiếp.

Một endpoint được đổi từ List sang Page có thể hợp lý tăng thêm query COUNT.

### 27.1. Query count không load entity

```java
Long total = em.createQuery("""
    select count(o)
    from PurchaseOrder o
    """, Long.class).getSingleResult();
```

Có một query/statement, nhưng không hydrate Order entities.

### 27.2. DTO projection

```java
List<OrderSummary> rows = em.createQuery("""
    select new com.example.OrderSummary(
        o.id, o.status
    )
    from PurchaseOrder o
    """, OrderSummary.class).getResultList();
```

Query trả nhiều DTOs nhưng entity load count có thể thấp vì không phải entity hydration.

### 27.3. Collection fetch join cùng pagination

Nếu fetch join to-many collection trong paginated query, SQL rows có thể nhân và Hibernate có thể paginate trong memory. Đừng cố giảm query count bằng cách fetch toàn graph rồi phân trang ở JVM.

## 28. Statistics không phải audit hoặc accounting

Một application có thể muốn biết tổng số invoices đã phát hành hoặc số orders đã deleted.

Không nên dựa vào `entityInsertCount`/`entityDeleteCount` vì:

- Counter reset khi restart/`stats.clear()`.
- Chỉ phản ánh activity của một SessionFactory instance.
- Bulk SQL và external writers không được tính tương tự.
- Transaction failures/rollbacks và entity lifecycle có semantics riêng.
- Database triggers/cascades có thể tác động nhiều rows.
- Một counter không chứa business identity hoặc audit metadata.

Dùng database transactional records, audit/outbox hoặc domain reporting query cho số liệu kinh doanh.

## 29. Statistics không đo toàn bộ SQL database

Những SQL có thể không xuất hiện trong Statistics của một SessionFactory:

- `JdbcTemplate` chạy trực tiếp.
- Stored procedures phát sinh statements nội bộ.
- Triggers trong DB.
- SQL từ Flyway/Liquibase.
- Worker khác dùng data source khác.
- Reporting service/ETL.
- Manual SQL tooling.
- Queries ở SessionFactory thứ hai.

Vì vậy chỉ số `getPrepareStatementCount()` thấp không chứng minh toàn database ít load.

## 30. Chẩn đoán khi số prepared statements giảm nhưng API vẫn chậm

Ví dụ trước tối ưu:

```text
Orders = 20
SELECT statements ~21
Total SQL rows ~200
Response latency ~180 ms
```

Sau khi fetch join nhiều collections:

```text
SELECT statements ~1
Total SQL rows ~50.000
Response latency ~700 ms
Heap/GC tăng mạnh
```

Các số là kịch bản minh họa.

### 30.1. Vì sao tệ hơn?

SQL join nhân rows, tăng transfer và hydration, dù số lần prepare giảm.

### 30.2. Cách phân tích

- Xem `entityLoadCount` và `collectionLoadCount`.
- Kiểm tra SQL result row count/bytes.
- Đo heap allocations và GC.
- Xem database execution plan.
- Cân nhắc two-step loading, DTO/aggregate projection, batch fetch.

### 30.3. Mục tiêu đúng

Tối ưu **end-to-end latency và resource usage với dữ liệu đúng**, không chỉ tối ưu một counter.

## 31. Chẩn đoán khi entity load thấp nhưng SQL rất nhiều

Một code:

```java
for (Long productId : productIds) {
    long count = em.createQuery("""
        select count(o)
        from PurchaseOrder o
        where o.product.id = :productId
        """, Long.class)
        .setParameter("productId", productId)
        .getSingleResult();
}
```

Có thể chạy 100 scalar queries mà entity load count gần 0.

Cách tối ưu có thể là GROUP BY cho các product IDs:

```java
List<Object[]> counts = em.createQuery("""
    select o.product.id, count(o)
    from PurchaseOrder o
    where o.product.id in :productIds
    group by o.product.id
    """, Object[].class)
    .setParameter("productIds", productIds)
    .getResultList();
```

Ví dụ này giả định mapping `PurchaseOrder.product` có tồn tại trong bài toán riêng.

## 32. Query plan/cache metrics không thay database EXPLAIN

Một query có Hibernate query-plan cache hit cao vẫn có thể:

- Scan toàn bảng không index.
- Chờ row locks.
- Sort khối lượng lớn.
- Trả triệu rows.
- Dùng execution plan không phù hợp data distribution.

Khi chậm, phân tích:

1. SQL thực tế và bind values đã được redacted.
2. Indexes và selectivity.
3. `EXPLAIN`/`EXPLAIN ANALYZE` trên môi trường thích hợp.
4. DB CPU/IO/locks.
5. Network transfer, JDBC result processing.
6. Entity hydration và DTO mapping.

Statistics cung cấp tín hiệu ORM, không thay query-plan analysis của database.

## 33. Phân biệt cache cold/warm khi test nhiều tenants

Một SaaS có tenant A traffic cao, tenant B ít traffic. Global L2 hit rate có thể cao nhờ A nhưng cold latency của B vẫn kém.

### 33.1. Không suy ra per-tenant counters từ global Statistics

Statistics không tự có mọi metric theo tenant. Nếu cần tenant-specific performance, dùng instrumentation thích hợp và cân nhắc cardinality/privacy, không thêm toàn bộ tenant IDs làm metric labels trên hệ thống lớn.

### 33.2. Multi-tenancy không thay authorization

Hibernate multi-tenancy và tenant-aware L2 cache có thể giúp phân tách entity identity theo tenant. Nhưng user A có quyền đọc resource nào trong cùng tenant là câu hỏi authorization khác.

### 33.3. Không dùng Hibernate Statistics làm chứng cứ truy cập dữ liệu

Entity load count không cho biết actor, resource ID, permission policy hay API response. Security audit phải có cơ chế riêng.

## 34. Quy trình thực hành chẩn đoán N+1

1. Tạo dataset đủ lớn, ví dụ 30 Orders với Lines và Customers khác nhau.
2. Bật `hibernate.generate_statistics` trong test.
3. Commit fixtures rồi mở persistence context sạch.
4. Chụp `StatsSnapshot` hoặc reset khi test hoàn toàn cô lập.
5. Gọi service và **thực sự map DTO**, đừng dừng ngay sau root query.
6. Đọc `entityLoadCount`, `entityFetchCount`, `collectionLoadCount`, `collectionFetchCount`, `prepareStatementCount`.
7. Bật SQL logs có kiểm soát để tìm repeated query shapes.
8. Đổi fetch plan bằng batch fetch/EntityGraph/to-one fetch join/two-phase query phù hợp.
9. So sánh lại statistics, SQL timings, heap, response latency.
10. Viết regression test với query/fetch budget và fixtures đủ đại diện.

### 34.1. Nhìn độ dốc

Nếu tăng số Orders từ 10 lên 100 khiến SQL preparations tăng từ 11 lên 101, dấu hiệu N+1 rõ hơn một test chỉ có một Order.

### 34.2. Đừng bỏ correctness để giảm query

Một service trả thiếu child records có thể có chuẩn bị SQL thấp. Tests phải xác minh dữ liệu đủ và đúng trước performance assertions.

## 35. Những lỗi thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
|---|---|---|
| Quên bật statistics | Counters bằng 0 | Xác minh `isStatisticsEnabled()` |
| Đếm entity loads như SQL | Kết luận sai | Một query có thể load nhiều entities |
| Đếm collection loads như số elements | Ước lượng sai dữ liệu | Một collection có nhiều phần tử |
| Chỉ nhìn queryExecutionCount | Bỏ sót lazy N+1 | Xem fetch + prepare counts và SQL |
| Xem prepare count như DB round trips | Sai dưới batching/reuse | JDBC/DB metrics |
| Xem entityUpdateCount như bulk update rows | Sai business counts | executeUpdate/DB auditing |
| Gọi stats.clear trong request production | Reset counters toàn factory | Snapshot/rates thay vì reset |
| Test song song cùng Stats | Nhiễu/reset lẫn nhau | Cô lập/tuần tự |
| Không clear context sau fixture | L1 che N+1 | Fresh EntityManager |
| Chỉ test warm cache | Cold-start regression | Đo cold và warm |
| Giảm SQL bằng fetch join nhiều bags | Cartesian product/heap cao | Bounded fetch plan/projections |
| Tăng JDBC batch size để sửa lazy SELECT | Không đúng cơ chế | Batch fetching khi đọc |
| Đọc role sai tên | Per-role stats không đúng | Khám phá runtime role names |
| Dùng raw query string làm metric label | High cardinality/PII | Bounded metrics labels |
| Tin cache hit nghĩa được quyền xem | Security bug | Authorization riêng |
| Chỉ đo SQL count | Bỏ qua row volume/GC/locks | Latency, DB IO, allocations |
| Đọc factory A cho persistence unit B | Kết luận sai | Chọn đúng SessionFactory |
| So counters xuyên restart như liên tục | Rate âm/giả | Xử lý reset đúng |
| Bật full bind log production | Lộ secrets/PII | Sampling/redaction/access control |
| Dùng Statistics làm audit trail | Mất dữ liệu sau restart/bulk | Database/domain audit |

## 36. Bài tập 1: một query, 100 entities

Một HQL query trả 100 Customers mới được hydrate.

**Câu hỏi:** `getEntityLoadCount()` có chắc tăng một không?

**Giải thích:** Không. Counter có thể tăng theo số entity instances, khoảng 100; SQL SELECT có thể chỉ là một.

## 37. Bài tập 2: collection N+1

Một query tải 20 Orders, sau đó truy cập lazy `lines` cho từng Order. Cache lạnh, không batch/subselect fetch.

**Câu hỏi:** Những counters nào đáng quan sát?

**Giải thích:** `collectionFetchCount`, `collectionLoadCount` và `prepareStatementCount`; thêm SQL logs để xác định repeated SELECTs. `queryExecutionCount` có thể chỉ phản ánh một HQL execution.

## 38. Bài tập 3: JOIN FETCH

Sau khi thêm `left join fetch o.lines`, `collectionFetchCount` giảm mạnh nhưng `collectionLoadCount` vẫn cao.

**Câu hỏi:** Có mâu thuẫn không?

**Giải thích:** Không. Hibernate vẫn initialize collections nhưng không cần nhiều separate collection fetch SELECTs.

## 39. Bài tập 4: batch fetching

Có 40 Orders, đặt `@BatchSize(size=20)` trên `lines`.

**Câu hỏi:** Có phải collectionLoadCount chắc chắn giảm xuống 2?

**Giải thích:** Không. Có thể vẫn load 40 collection instances, nhưng số SQL SELECT batches giảm; quan sát prepared statements và SQL.

## 40. Bài tập 5: warm cache

Lần đầu tải Customer#7 từ database và cache L2. Lần thứ hai mở EntityManager mới và tải cùng ID.

**Câu hỏi:** Có bắt buộc chạy SELECT lần hai?

**Giải thích:** Không nếu Hibernate L2 cache hit đúng mapping/config, nhưng vẫn có thể có entity materialization trong context. Cache hit, entity load và SQL prepare là ba phép đo khác.

## 41. Bài tập 6: bulk HQL UPDATE

Một bulk query sửa trạng thái cho 10.000 Orders.

**Câu hỏi:** `entityUpdateCount` có chắc tăng 10.000 không?

**Giải thích:** Không. Bulk HQL DML không phải per-entity lifecycle updates; dùng result từ bulk mutation/DB metrics cho số rows affected.

## 42. Bài tập 7: concurrent delta

Thread A chụp counters, thực hiện một request; thread B đồng thời import 1.000 Products; A chụp counters lần hai.

**Câu hỏi:** Delta của A có chính xác per-request không?

**Giải thích:** Không. SessionFactory statistics là shared counters, nên có thể chứa cả hoạt động B.

## 43. Bài tập 8: fixture gây lệch test

Test tạo 20 Orders và Lines trong cùng persistence context, rồi gọi service và thấy số SQL rất thấp.

**Câu hỏi:** Test này đã chứng minh không có N+1 chưa?

**Giải thích:** Chưa. L1 có thể đã chứa entities/collections; cần tách setup khỏi measurement và chạy với context sạch.

## 44. Checklist khi quan sát SessionFactory

1. Đã bật `hibernate.generate_statistics` đúng SessionFactory?
2. `isStatisticsEnabled()` trả true?
3. Số liệu là global factory, hay đã dùng instrumentation per-request?
4. Có nhiều application pods/EntityManagerFactories không?
5. Có concurrent requests/jobs trong measurement?
6. Fixtures/setup đã commit và persistence context sạch?
7. L1/L2/query cache đang cold hay warm?
8. `entityLoadCount` có cao bất thường so với DTO cần trả?
9. `entityFetchCount` có chỉ ra lazy to-one fetches?
10. `collectionLoadCount` có phản ánh collections initialized?
11. `collectionFetchCount` có dấu hiệu N+1?
12. Đã khoanh vùng đúng collection role?
13. `prepareStatementCount` có tăng theo số root owners?
14. `queryExecutionCount` có bỏ qua generated lazy SQL?
15. Query-specific statistics có dùng đúng query key?
16. Có flush tự động trên read path?
17. Entity updates/inserts có bị nhầm với bulk DML?
18. JDBC batch size và batch fetching đã phân biệt?
19. Query fetch join có nhân SQL rows hoặc paginate trong memory?
20. Cache hit rates có được diễn giải theo traffic mix?
21. Có query plan misses do dynamic query literals?
22. Có xem SQL logs, JDBC timing và DB EXPLAIN không?
23. API latency/heap/GC có được đo bên cạnh số statements?
24. Tests có assert kết quả nghiệp vụ trước query budget?
25. Có tránh `stats.clear()` trên production concurrent workload?
26. Logs/metrics có chứa secrets, raw SQL hoặc tenant IDs quá chi tiết?
27. API thống kê có bị expose công khai không?
28. Đã kiểm tra Hibernate version cho stats/cache APIs?
29. Có regression test với dữ liệu đủ lớn?
30. Kết luận hiệu năng dựa trên end-to-end resource usage, không một counter?

## 45. Ghi nhớ

- **`SessionFactory.getStatistics()`** cho biết hoạt động Hibernate ORM ở phạm vi SessionFactory, không tự chia theo request/tenant/toàn cluster.
- Bật bằng **`hibernate.generate_statistics=true`** và xác nhận `isStatisticsEnabled()`.
- **Entity load** đếm entities được nạp; **entity fetch** là fetch operations theo semantics ORM; cả hai **không bằng số SELECT**.
- **Collection load** đếm collection instances, không phải elements; **collection fetch** giúp tìm lazy-loading/N+1 nhưng cần xem SQL tương ứng.
- Per-entity `EntityStatistics` và per-role `CollectionStatistics` giúp khoanh vùng mapping gây over-fetching.
- **`queryExecutionCount` không đếm mọi SQL** do lazy associations, identifier generation và flush sinh ra.
- **`prepareStatementCount` đo số lần Hibernate chuẩn bị JDBC statements**, không phải rows hoặc round trips.
- `flushCount` không phải commit count; managed writes và bulk DML có semantics thống kê khác.
- L1, L2, query cache và query plan cache là các cơ chế khác nhau; hit/miss có ý nghĩa riêng.
- **JOIN FETCH** có thể giảm separate SELECTs nhưng vẫn load nhiều entities/collections và có thể nhân SQL rows.
- **Batch fetching** thường giảm số SELECTs khi đọc; **JDBC batching** tối ưu việc ghi DML.
- `Statistics.clear()` reset counters chung, không clear EntityManager hoặc L2 cache.
- Test statistics cần context sạch, cache state xác định và không bị nhiễu concurrent workload.
- Giám sát production cần chi phí vừa phải, metrics labels hữu hạn và bảo vệ query/tenant information.
- Để tìm nguyên nhân chậm, kết hợp Statistics với SQL logs, JDBC tracing, database execution plans, heap và API latency.

**Kết luận:** Statistics của Hibernate giúp trả lời **đã nạp bao nhiêu entities/collections, đã fetch bao nhiêu associations, đã chuẩn bị bao nhiêu JDBC statements và cache hoạt động ra sao**. Giá trị lớn nhất nằm ở việc đọc đúng tầng đo: một SQL có thể hydrate rất nhiều entities, một collection fetch không tương đương một collection element, và một HQL query có thể kích hoạt nhiều SQL lazy loads. Dùng các counters để hình thành giả thuyết, xác minh bằng SQL/database metrics, thay đổi fetch plan hay batching theo use case, sau đó kiểm tra correctness và performance với integration tests thực tế.

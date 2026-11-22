# Đo số truy vấn, thời gian truy vấn và số entity được tải trong JPA

Trong **Jakarta Persistence (JPA)**, một đoạn code Java ngắn không nhất thiết tương ứng với một câu SQL ngắn. Một lời gọi repository có thể khiến provider thực thi nhiều câu truy vấn, nạp hàng nghìn entity và dựng một đồ thị đối tượng lớn. Ngược lại, một câu SQL duy nhất vẫn có thể rất chậm nếu trả về quá nhiều hàng, join sai cách hoặc dùng execution plan kém.

Ví dụ:

```java
List<PurchaseOrder> orders =
    em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    ).getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

Nhìn từ Java, chỉ có **một** câu JPQL rõ ràng. Nhưng nếu `customer` được ánh xạ `LAZY` và các Customer chưa có trong persistence context, việc truy cập `getName()` có thể phát sinh nhiều câu SQL bổ sung. Đây là một tình huống **N+1 query** điển hình.

Để hiểu hiệu năng thật, cần đo **ít nhất ba nhóm chỉ số**:

1. **Số truy vấn/câu lệnh SQL thực sự được thực thi:** ứng dụng đã thực hiện bao nhiêu round-trip hoặc lần gọi JDBC tới database?
2. **Thời gian:** mỗi câu SQL mất bao lâu, một thao tác ORM mất bao lâu, và toàn bộ request mất bao lâu?
3. **Số entity được tải:** JPA đã nạp bao nhiêu entity instances vào persistence context, fetch thêm bao nhiêu quan hệ, và dữ liệu trả về lớn đến đâu?

> **Nguyên tắc:** Không kết luận “nhanh” chỉ vì số SQL ít, cũng không kết luận “chậm” chỉ vì một query trả nhiều entity. Phải xem **số lần gọi SQL, thời gian, lượng dữ liệu, cache và ngữ cảnh nghiệp vụ cùng lúc**.

Bài học thuộc chương **Hiệu năng** trong module **Data Persistence Relational Access ORM JPA**. Ta sẽ xây dựng một phương pháp đo có thể lặp lại, phân biệt các loại query count, dùng Hibernate Statistics như một ví dụ công cụ provider-specific, đo JDBC/database/request latency, phân biệt entity load với row count, nhận diện N+1 và over-fetching, kiểm soát L1/L2 cache, thiết kế benchmark và chống hồi quy hiệu năng.

---

## 1. Bản đồ của một thao tác JPA

Một request có thể đi qua các tầng sau:

```text
HTTP request
    |
    v
Controller / Application Service
    |
    v
Repository / EntityManager / JPQL
    |
    v
Persistence context (L1 cache)
    |
    +---- managed instance có sẵn? ----> trả entity
    |
    v
Shared cache (L2, nếu bật)
    |
    +---- cache hit hợp lệ? -----------> hydrate/reuse state
    |
    v
JPA provider
    |
    v
JDBC PreparedStatement
    |
    v
Connection pool / Network
    |
    v
Database:
  parse / plan / wait / execute / return rows
    |
    v
JDBC ResultSet
    |
    v
ORM hydration, identity map, collections
    |
    v
DTO mapping / JSON serialization
    |
    v
HTTP response
```

Mỗi tầng có độ trễ và tài nguyên riêng.

Nếu chỉ đo:

```java
long start = System.nanoTime();
List<Product> products = repository.findAll();
long elapsed = System.nanoTime() - start;
```

ta đo thời gian của lời gọi repository, **không riêng thời gian SQL trên database**. Nó có thể bao gồm ORM, JDBC, network, xử lý result set và chi phí khởi tạo proxy; đồng thời có thể **chưa bao gồm** các truy vấn LAZY phát sinh sau khi method trả về.

### 1.1. Ba chỉ số chính và đơn vị

| Chỉ số | Đơn vị thường gặp | Câu hỏi trả lời |
| --- | --- | --- |
| SQL execution count | Lần thực thi | Database bị gọi bao nhiêu lần? |
| JPQL/HQL execution count | Lần | Provider thực hiện bao nhiêu ORM queries? |
| Query latency | ms hoặc µs | Một câu SQL/thao tác mất bao lâu? |
| Request latency | ms | Người gọi chờ bao lâu? |
| Entity load count | Entity instances | Bao nhiêu entity được materialize/đưa vào persistence context? |
| Entity fetch count | Lượt fetch quan hệ/entity | Có bao nhiêu lượt tải bổ sung theo cách provider đo? |
| Collection fetch count | Lượt fetch collection | Có thể đang tạo N+1 collections không? |
| Rows returned | Rows | JDBC/SQL truyền bao nhiêu bản ghi? |
| Bytes transferred | B/KB/MB | Khối lượng dữ liệu chuyển qua mạng? |

**Không thể dùng một cột thay cho tất cả các cột còn lại.**

### 1.2. Một số liệu phải gắn với phạm vi đo

“20 queries” là thông tin chưa đủ nếu không biết:

- Trong một HTTP request hay cả 10 phút?
- Trong một transaction hay một test?
- Trên một `EntityManagerFactory` hay toàn service?
- Có cùng DB/schema và số records không?
- L1/L2 cache đang lạnh hay nóng?
- Có chạy đồng thời request khác không?
- Query count là JPQL, JDBC statement chuẩn bị hay SQL execute?
- Có tính SQL phát sinh khi flush/commit không?

Một phép đo đáng tin cậy phải ghi rõ **điểm bắt đầu, điểm kết thúc và ý nghĩa của bộ đếm**.

## 2. Vì sao không nên đếm lời gọi repository?

Ví dụ:

```java
List<PurchaseOrder> orders =
    orderRepository.findAll();

for (PurchaseOrder order : orders) {
    Customer customer = order.getCustomer();
    System.out.println(customer.getName());
}
```

Trong source Java, chỉ có một lần gọi repository. Nhưng các lời gọi `getCustomer()` có thể kích hoạt SQL.

Ở chiều ngược lại:

```java
Product a = em.find(Product.class, 101L);
Product b = em.find(Product.class, 101L);
```

Hai lời gọi `find()` trong **cùng persistence context** có thể chỉ cần một lần nạp entity; lần thứ hai lấy lại managed instance.

Vì thế:

```text
# Repository method calls
       !=
# JPQL queries
       !=
# JDBC executions
       !=
# SQL statements prepared
       !=
# Rows returned
       !=
# Entity instances loaded
```

### 2.1. SQL count là chỉ số quan trọng với N+1

Nếu cùng một response trả 100 Orders mà có 101 SQL executions, rất đáng xem liệu một query tải Orders và 100 queries tải Customers đã xảy ra hay không.

Nhưng **101 SQL** chưa tự chứng minh N+1: có thể là 101 operations hợp lệ theo use case. Cần nhìn SQL patterns, call stacks và đường truy cập associations.

### 2.2. Ít SQL không luôn tốt hơn

Một câu query:

```sql
SELECT ...
FROM purchase_orders o
JOIN order_lines l ON l.order_id = o.id
JOIN customers c ON c.id = o.customer_id;
```

có thể trả hàng triệu rows và gây tốn memory, network, CPU dù chỉ là **một statement**.

Một chiến lược hai hoặc ba queries với batching/projections đôi khi nhanh hơn nhiều so với một join khổng lồ.

### 2.3. Query nhanh riêng lẻ vẫn có thể thành request chậm

Nếu một câu SQL mất 2 ms, nhưng chạy 150 lần tuần tự:

\[
T_{\text{SQL tổng gần đúng}} = 150 \times 2 \text{ ms} = 300 \text{ ms}
\]

Chưa kể network, ORM hydration và application logic. Đây là lý do phải đo **count và latency** đồng thời.

## 3. Mô hình ví dụ: PurchaseOrder, Customer và OrderLine

Dùng mô hình:

```text
Customer (1) -------- (*) PurchaseOrder
                            |
                            | (1)
                            v
                            (*) OrderLine
                                  |
                                  v
                                Product
```

Ứng dụng có 100 Orders, mỗi Order thuộc một Customer và chứa trung bình 8 Lines.

### 3.1. Customer

```java
package com.example.shop.domain;

import jakarta.persistence.*;

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
```

### 3.2. PurchaseOrder

```java
package com.example.shop.domain;

import jakarta.persistence.*;
import java.util.ArrayList;
import java.util.List;

@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String reference;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {}

    public Long getId() { return id; }
    public String getReference() { return reference; }
    public Customer getCustomer() { return customer; }
    public List<OrderLine> getLines() { return lines; }
}
```

### 3.3. OrderLine

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "order_lines")
public class OrderLine {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private PurchaseOrder order;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "product_id", nullable = false)
    private Product product;

    @Column(nullable = false)
    private int quantity;

    protected OrderLine() {}

    public Long getId() { return id; }
    public PurchaseOrder getOrder() { return order; }
    public Product getProduct() { return product; }
    public int getQuantity() { return quantity; }
}
```

### 3.4. Product

```java
package com.example.shop.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @Column(nullable = false)
    private String sku;

    protected Product() {}

    public Long getId() { return id; }
    public String getSku() { return sku; }
}
```

Ví dụ tập trung vào hiệu năng đọc; constructor/domain methods để tạo dữ liệu test có thể bổ sung trong một fixture riêng.

## 4. Kịch bản N+1 cơ bản

Code:

```java
List<PurchaseOrder> orders =
    em.createQuery(
        "SELECT o FROM PurchaseOrder o",
        PurchaseOrder.class
    ).getResultList();

for (PurchaseOrder order : orders) {
    String customerName =
        order.getCustomer().getName();
    System.out.println(customerName);
}
```

Nếu có 100 Orders và mỗi Order liên quan đến một Customer **khác nhau, chưa có trong L1/L2**, một cách thực thi thường gặp là:

```sql
-- Query 1: lấy 100 orders
SELECT id, reference, customer_id
FROM purchase_orders;

-- Query 2
SELECT id, name
FROM customers WHERE id = 1;

-- Query 3
SELECT id, name
FROM customers WHERE id = 2;

-- ...

-- Query 101
SELECT id, name
FROM customers WHERE id = 100;
```

### 4.1. Vì sao gọi là N+1?

Một query tải tập root entities, sau đó N truy vấn khác để tải quan hệ của N phần tử.

\[
Q(N) \approx 1 + N
\]

Trong đó `Q(N)` là số SQL statements thực thi trong mô hình minh họa.

**Đây không phải định luật của mọi mapping.** N thực tế phụ thuộc số Customer IDs khác nhau, persistence context, cache hits, batching, fetch plan và provider.

### 4.2. Khi 100 Orders cùng một Customer

Nếu 100 Orders đều có cùng `customer_id` và Customer đã được load vào L1 sau lần đầu, có thể chỉ phát sinh một query bổ sung.

Do vậy, test N+1 chỉ với tất cả Orders chung một Customer sẽ **che giấu** vấn đề.

### 4.3. Khi cache L2 đang nóng

Provider có thể lấy Customer từ L2 thay vì SQL. Trong một benchmark chỉ đo SQL count, lỗi fetch pattern có thể không lộ rõ khi cache nóng.

Vì vậy cần đo **cold-cache** và **warm-cache**, không chỉ một trường hợp.

### 4.4. Khi Open Session in View còn bật

Trong một web app, quan hệ LAZY có thể được truy cập trong bước JSON serialization ở sau service method. Nếu chỉ đo quanh repository call, bạn có thể bỏ sót các câu SQL phát sinh muộn.

Điểm đo phải bao trùm **toàn bộ luồng đọc cần đo**, hoặc thiết kế DTO mapping hoàn tất bên trong transaction để scope rõ ràng.

## 5. Ba kiểu đếm truy vấn phải gọi đúng tên

Một hệ thống dùng Hibernate có thể cung cấp nhiều bộ đếm. Chúng không đồng nghĩa.

| Chỉ số | Ý nghĩa thường gặp | Điều không suy ra được |
| --- | --- | --- |
| `Statistics.getQueryExecutionCount()` | Số lần thực thi các query cấp Hibernate/HQL/JPQL được statistics theo dõi | Không đại diện chắc chắn cho toàn bộ SQL/JDBC statements |
| `Statistics.getPrepareStatementCount()` | Số JDBC PreparedStatements được chuẩn bị theo Hibernate statistics | Không luôn bằng số lần thực thi SQL nếu statement reuse/cache/batch khác |
| Datasource/JDBC execution count | Số lần gọi JDBC execute/query/update qua proxy phù hợp | Không trực tiếp nói có bao nhiêu entity objects tạo ra |
| SQL text log lines | Dòng SQL provider ghi log | Không phải bộ đếm đã chuẩn hóa cho mọi execution |
| Database statement metrics | DBMS nhìn thấy hoạt động theo database accounting | Không tự quy cho một HTTP request nếu thiếu trace context |

### 5.1. Hibernate query count có thể bỏ sót thao tác gì?

Một thao tác:

```java
em.find(Product.class, 101L);
```

không phải do application gọi một JPQL query. Nếu muốn đo tổng SQL, không chỉ dựa vào số `getQueryExecutionCount()`.

Các SQL phát sinh do lazy loading, flush DML, batch fetch hoặc ID generation cũng cần được tính theo mục tiêu quan sát.

### 5.2. Prepare count không luôn là execution count

Trong JDBC:

```java
PreparedStatement ps =
    connection.prepareStatement(sql);

ps.setLong(1, 101L);
ps.executeQuery();

ps.setLong(1, 202L);
ps.executeQuery();
```

Một lần `prepareStatement` nhưng **hai lần `executeQuery`** trong mô hình này.

Vì vậy thống kê “prepared statement count” là chỉ báo hữu ích nhưng không thể tuyên bố nó luôn chính xác bằng số lần SQL được thực thi, nhất là khi có statement caching và batching.

### 5.3. Batch execution cần định nghĩa riêng

Một JDBC batch có thể thêm 100 thao tác DML rồi gọi `executeBatch()` một lần. Tùy công cụ, bạn có thể thấy:

- Một JDBC executeBatch invocation.
- N batch entries.
- Ít round-trips hơn.
- N database row modifications.

Một chỉ số duy nhất “number of queries” không mô tả đủ tất cả những điều đó.

## 6. Cách dễ bắt đầu: bật SQL logging

Trong môi trường phát triển, provider SQL log cho phép quan sát patterns.

Với Hibernate 6:

```properties
hibernate.format_sql=true
hibernate.show_sql=false
```

Logging framework, ví dụ cấu hình kiểu Spring Boot:

```properties
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

### 6.1. Ý nghĩa

- `org.hibernate.SQL`: thường ghi các câu SQL do Hibernate tạo.
- `org.hibernate.orm.jdbc.bind`: có thể ghi giá trị bind parameters theo Hibernate 6 logging categories/version.
- `format_sql`: định dạng SQL cho dễ đọc.

`show_sql=false` trong ví dụ nhằm tránh đẩy SQL thẳng ra console song song với logging framework. Đây là **cấu hình Hibernate/Spring Boot**, không phải các properties đo hiệu năng chuẩn của Jakarta Persistence.

### 6.2. Những gì SQL log giúp phát hiện

Một pattern lặp:

```text
select ... from purchase_orders ...
select ... from customers where id=?
select ... from customers where id=?
select ... from customers where id=?
...
```

là tín hiệu rõ của N+1 hoặc một dạng fetch lặp cần điều tra.

### 6.3. Những gì SQL log chưa đủ

- Không mặc nhiên có thời gian mỗi câu SQL.
- Không phân biệt rõ statement prepared và executed nếu không kiểm tra logger.
- Có thể gây overhead đáng kể khi log quá nhiều.
- Có thể làm nhiễu kết quả benchmark.
- Không đo đầy đủ thời gian ORM hydration hoặc JSON serialization.
- Có nguy cơ lộ dữ liệu nhạy cảm qua bind parameter logs.

**Không bật bind parameter TRACE vô điều kiện trên production.** Chỉ dùng trong môi trường đã kiểm soát thông tin hoặc có chính sách che dữ liệu.

### 6.4. Không đếm log lines thủ công làm metric production

Một câu SQL có thể bị format thành nhiều dòng. Logging có thể bị sampling, mất dòng hoặc thay đổi category theo version.

Đếm số dòng chứa `select` chỉ có thể là một thủ thuật debug sơ bộ, không phải định nghĩa vững chắc của SQL execution count.

## 7. Hibernate Statistics: quan sát cấp ORM

Jakarta Persistence **không chuẩn hóa API đo đầy đủ** số SQL, thời gian query hay entity load count. Một ứng dụng dùng Hibernate có thể sử dụng **Hibernate Statistics API**.

Bật:

```properties
hibernate.generate_statistics=true
```

Trong Spring Boot dùng Hibernate, có thể cấu hình:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Tên property và behavior thuộc Hibernate. Nếu đổi JPA provider, các API sau không portable.

### 7.1. Lấy Statistics từ SessionFactory

```java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

SessionFactory sessionFactory =
    emf.unwrap(SessionFactory.class);

Statistics stats =
    sessionFactory.getStatistics();

System.out.println(
    "Prepared statements: " +
    stats.getPrepareStatementCount()
);

System.out.println(
    "ORM query executions: " +
    stats.getQueryExecutionCount()
);

System.out.println(
    "Entity loads: " +
    stats.getEntityLoadCount()
);
```

### 7.2. Những counters hữu ích

| Hibernate Statistics method | Ý định quan sát |
| --- | --- |
| `getPrepareStatementCount()` | JDBC statements chuẩn bị theo statistics |
| `getQueryExecutionCount()` | ORM query executions được thống kê |
| `getEntityLoadCount()` | Entity load events |
| `getEntityFetchCount()` | Entity fetch events |
| `getCollectionLoadCount()` | Collection loads |
| `getCollectionFetchCount()` | Collection fetch events |
| `getSecondLevelCacheHitCount()` | L2 cache hits |
| `getSecondLevelCacheMissCount()` | L2 cache misses |
| `getSecondLevelCachePutCount()` | L2 cache puts |
| `getQueryExecutionMaxTime()` | Thời gian tối đa của query executions được statistics theo dõi |

Các method names gắn với Hibernate Statistics API; cần dùng version Hibernate tương ứng trong project. Cụ thể semantics **load** và **fetch** phụ thuộc Hibernate accounting; đừng tự suy chúng bằng số JDBC rows hoặc SQL statements.

### 7.3. Một đoạn code đo trước–sau

```java
import jakarta.persistence.EntityManagerFactory;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;

public final class HibernateStatsProbe {

    private final Statistics statistics;

    public HibernateStatsProbe(EntityManagerFactory emf) {
        SessionFactory sessionFactory =
            emf.unwrap(SessionFactory.class);
        this.statistics =
            sessionFactory.getStatistics();
    }

    public Snapshot snapshot() {
        return new Snapshot(
            statistics.getPrepareStatementCount(),
            statistics.getQueryExecutionCount(),
            statistics.getEntityLoadCount(),
            statistics.getEntityFetchCount(),
            statistics.getCollectionLoadCount(),
            statistics.getCollectionFetchCount(),
            statistics.getSecondLevelCacheHitCount()
        );
    }

    public record Snapshot(
        long preparedStatements,
        long ormQueries,
        long entityLoads,
        long entityFetches,
        long collectionLoads,
        long collectionFetches,
        long l2Hits
    ) {
        public Snapshot minus(Snapshot before) {
            return new Snapshot(
                preparedStatements - before.preparedStatements,
                ormQueries - before.ormQueries,
                entityLoads - before.entityLoads,
                entityFetches - before.entityFetches,
                collectionLoads - before.collectionLoads,
                collectionFetches - before.collectionFetches,
                l2Hits - before.l2Hits
            );
        }
    }
}
```

Sử dụng trong **một test cô lập**:

```java
HibernateStatsProbe probe =
    new HibernateStatsProbe(emf);

HibernateStatsProbe.Snapshot before =
    probe.snapshot();

List<PurchaseOrder> orders =
    loadOrdersAndAccessCustomers(em);

HibernateStatsProbe.Snapshot after =
    probe.snapshot();

System.out.println(after.minus(before));
```

`loadOrdersAndAccessCustomers(em)` là method của test được định nghĩa theo kịch bản, ví dụ chạy JPQL rồi duyệt Customer; nó không phải JPA API.

### 7.4. Counter ở phạm vi nào?

Hibernate Statistics thường là **counters toàn `SessionFactory`**; chúng không tự thuộc riêng một request/thread/transaction.

Nếu cùng lúc có request khác:

```text
T1: snapshot before
T2: other request executes 20 SQL statements
T1: load orders executes 5 statements
T1: snapshot after
```

chênh lệch statistics có thể phản ánh cả hai workloads.

**Vì vậy test theo before/after yêu cầu cô lập workload**, hoặc cần instrumentation per-request/per-thread ở tầng JDBC/tracing.

### 7.5. Có nên gọi Statistics.clear()?

Trong một test hoàn toàn cô lập:

```java
stats.clear();
```

có thể giúp đưa counters về trạng thái ban đầu. Nhưng không gọi `clear()` giữa các production requests hoặc parallel tests dùng chung SessionFactory, vì bạn sẽ xóa thống kê của tác vụ khác.

Đo bằng snapshots cũng không tránh được nhiễu concurrent activity; isolation vẫn là điều kiện thiết yếu.

### 7.6. Statistics có overhead

Bật statistics giúp quan sát nhưng tạo overhead thu thập metrics, có thể làm sai benchmark rất nhỏ. Khi so sánh hiệu năng, ghi rõ instrumentation nào đang bật và giữ điều kiện hai lần đo tương đương.

## 8. Đo đúng số SQL executions: DataSource/JDBC instrumentation

Nếu mục tiêu là **đếm số lần gọi SQL ở tầng JDBC**, công cụ tại `DataSource` hoặc JDBC driver/proxy thường phù hợp hơn chỉ đếm JPQL.

Các lựa chọn thực tế:

- DataSource proxy hỗ trợ đếm `executeQuery`, `executeUpdate`, `execute` và `executeBatch`.
- JDBC tracing/observability instrumentation.
- P6Spy cho quan sát SQL/JDBC theo cấu hình.
- Driver/database telemetry.
- SQL statement metrics của DBMS.

### 8.1. Vị trí đặt JDBC proxy

```text
JPA EntityManager
        |
        v
Hibernate / EclipseLink
        |
        v
Instrumented DataSource / JDBC proxy
        |
        v
Connection pool / Driver
        |
        v
Database
```

Proxy tại đây có thể thấy những lần thực thi SQL do provider tạo, bao gồm lazy loads và các DML khi flush.

### 8.2. Chọn metric cụ thể

Một hệ thống nên phân biệt:

```text
jdbc.execute.count
jdbc.execute.duration
jdbc.execute.batch.count
jdbc.execute.batch.items
jdbc.connection.acquire.duration
```

Tên metric chỉ là ví dụ đặt tên; không phải bộ tên bắt buộc của Jakarta Persistence.

### 8.3. Đếm theo HTTP request

Có thể tổ chức:

```text
Begin request observation
     |
     v
Open/participate in transaction
     |
     v
Repository operations
     |
     v
DTO mapping / deliberate lazy access
     |
     v
Flush / commit (if write operation)
     |
     v
End request observation
     |
     v
sql_execute_count = 17
```

Nếu thiết kế per-thread, phải hiểu **async/reactive processing** có thể đổi thread. ThreadLocal không phải lúc nào cũng xác định được cùng một request ở mọi ứng dụng.

### 8.4. Không chỉ đếm SELECT

Một request ghi có thể phát sinh:

- SELECT để kiểm tra state.
- INSERT/UPDATE/DELETE khi flush.
- SELECT sau insert để lấy generated values tùy strategy.
- Sequence allocation.
- SQL cho collections/associations.
- Prepared statements khác từ provider.

Nếu metric chỉ lọc SQL bắt đầu bằng `SELECT`, tổng database load bị đánh giá thiếu.

### 8.5. Không tự gán mọi thứ cho JPA

Nếu cùng DataSource còn có JDBC template, jOOQ hoặc custom SQL, proxy có thể thấy cả các calls đó. Khi mục tiêu là “JPA SQL count”, cần gắn span/caller attribution hoặc tách tập công việc cho đúng.

## 9. Thời gian nào là “thời gian truy vấn”?

Một câu “query mất 100 ms” có thể mang ít nhất bốn nghĩa:

1. **DB server execution time**: database thực thi plan và trả dữ liệu ở mức server.
2. **JDBC duration**: client gọi statement, chờ network, driver và dữ liệu.
3. **ORM duration**: provider thực thi, đọc ResultSet, dựng entities, duy trì persistence context.
4. **End-to-end duration**: repository/service/HTTP request, có thể gồm validation, JSON, network với services khác.

```text
HTTP request -------------- 200 ms -----------------
  Controller/service ------- 175 ms ---------------
    ORM operation ---------- 145 ms ----------
      JDBC waits ---------- 100 ms -------
        DB execution ------ 70 ms -----
      ORM hydration ---------- 45 ms ---
  Serialization ------------ 25 ms ----
```

Các thời gian trên là minh họa, không phải công thức cộng đơn giản giữa những lớp lồng nhau: một span có thể bao gồm spans con.

### 9.1. Đo repository time bằng System.nanoTime()

```java
long started = System.nanoTime();

try {
    List<Product> products =
        em.createQuery(
            "SELECT p FROM Product p",
            Product.class
        ).getResultList();

    return products;
} finally {
    long elapsedNanos =
        System.nanoTime() - started;

    System.out.printf(
        "JPA operation: %.3f ms%n",
        elapsedNanos / 1_000_000.0
    );
}
```

`System.nanoTime()` phù hợp đo **elapsed duration trong cùng process**; không dùng `System.currentTimeMillis()` để suy elapsed benchmark ngắn khi clock có thể điều chỉnh.

### 9.2. Lưu ý scope

Nếu sau khi return, controller truy cập lazy associations hoặc serialize entities, những thao tác đó nằm **ngoài** thời gian được đo trong method trên.

Đối với use case “trả danh sách Orders kèm Customer names”, timer phải bao gồm cả phần lấy Customer names.

### 9.3. Flush có thể đẩy SQL đến cuối transaction

Một service ghi:

```java
em.persist(order);
```

có thể chưa thực thi toàn bộ INSERT ngay lúc đó; SQL có thể chạy ở flush hoặc commit tùy ID strategy, flush mode và provider.

Nếu dừng timer trước `flush()`/`commit()`, số liệu sẽ bỏ sót chi phí DML thực tế.

### 9.4. Connection acquisition khác query execution

Khi connection pool hết connection, ứng dụng có thể mất 300 ms chờ lấy connection, rồi câu SQL chỉ chạy 5 ms.

Nếu chỉ nhìn service timer 305 ms và gọi đó là “SQL chậm”, chẩn đoán sai. Cần tách **pool wait**, JDBC execution và ORM costs khi công cụ hỗ trợ.

## 10. Đo per-query latency qua JDBC proxy

Một JDBC instrumentation phù hợp có thể tạo các spans dạng:

```text
Request: GET /orders
  [SQL #1] SELECT orders                 12 ms
  [SQL #2] SELECT customer WHERE id=?     2 ms
  [SQL #3] SELECT customer WHERE id=?     3 ms
  ...
  [SQL #101] SELECT customer WHERE id=?   2 ms
```

Khi có timings, ta biết:

- SQL #1 không hẳn chậm.
- 100 round-trips nhỏ mới là vấn đề.
- Tổng thời gian bị chi phối bởi số lượng executions.

### 10.1. Tại sao JDBC duration không bằng database execution?

Nó có thể bao gồm:

- Chờ lock.
- Network latency.
- Driver processing.
- Đọc/chuyển dữ liệu ở phía client.
- Batching behavior.
- Connection/pool waits nếu instrumentation bao trùm bước đó.

Do đó luôn ghi rõ measurement point.

### 10.2. Cẩn thận với streaming ResultSet

Nếu instrumentation chỉ đo thời gian của `executeQuery()` mà không đo toàn bộ quá trình đọc `ResultSet.next()`, nó có thể bỏ qua một phần đáng kể chi phí chuyển dữ liệu và hydration.

Một công cụ observability cần mô tả nó kết thúc span khi nào: khi `execute()` trả về hay khi toàn bộ rows đã được đọc.

### 10.3. SQL fingerprints

Các câu sau có SQL shape giống nhau:

```sql
SELECT id, name FROM customers WHERE id = 101;
SELECT id, name FROM customers WHERE id = 202;
```

Có thể normalize thành fingerprint:

```sql
SELECT id, name FROM customers WHERE id = ?;
```

Một fingerprint xuất hiện 100 lần trong cùng request là tín hiệu N+1 mạnh hơn danh sách những SQL text có literals khác nhau.

### 10.4. Tránh high-cardinality metrics

Không gắn `customerId`, `orderId` hoặc toàn bộ SQL text vào **metric labels** như:

```text
jdbc_query_duration{order_id="1234567"}
```

vì sẽ tạo số lượng time series khổng lồ và có thể làm lộ identifiers.

Metric labels thường nên dùng tên operation/endpoint/tên nhóm query ổn định; SQL chi tiết có thể đi vào tracing/logging có sampling và redaction.

## 11. Đo thời gian với Micrometer trong Spring

Nếu ứng dụng sử dụng Spring + Micrometer, có thể đo operation-level latency bằng `Timer`.

```java
package com.example.shop.observability;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;

public class OrderReadService {

    @PersistenceContext
    private EntityManager em;

    private final MeterRegistry registry;

    public OrderReadService(MeterRegistry registry) {
        this.registry = registry;
    }

    public List<OrderSummary> listOrderSummaries() {
        Timer.Sample sample = Timer.start(registry);

        try {
            return em.createQuery(
                """
                SELECT new com.example.shop.observability.OrderSummary(
                    o.id, o.reference, c.name
                )
                FROM PurchaseOrder o
                JOIN o.customer c
                ORDER BY o.id
                """,
                OrderSummary.class
            )
            .setMaxResults(100)
            .getResultList();
        } finally {
            sample.stop(
                registry.timer(
                    "shop.jpa.operation.duration",
                    "operation",
                    "list-order-summaries"
                )
            );
        }
    }
}
```

DTO projection:

```java
package com.example.shop.observability;

public record OrderSummary(
    Long id,
    String reference,
    String customerName
) {}
```

Với JPQL constructor expression, lớp DTO cần constructor tương ứng và tên class đầy đủ trong JPQL. Ví dụ dùng Java hỗ trợ text blocks và records; imports/domain class configuration cần phù hợp project.

### 11.1. Timer này đo gì?

Tính từ lúc vào service method đến lúc hoàn thành query và dựng danh sách DTOs, trong phạm vi `try/finally`.

Nó **không** trực tiếp đo:

- Một SQL riêng lẻ.
- Số SQL executions.
- HTTP network duration.
- JSON serialization sau service.
- Connection pool thời gian ngoài operation scope.

### 11.2. Ghi cả lỗi

`finally` khiến timer ghi nhận duration kể cả khi query ném exception. Nhưng metrics dạng duration không tự phân biệt success/failure; nếu cần, thêm status label có tập giá trị nhỏ hoặc đo error counter riêng.

### 11.3. Không gắn tham số nghiệp vụ vào tag

Đúng hướng:

```text
operation=list-order-summaries
```

Nguy hiểm:

```text
orderId=9381238123
customerName=...
rawSql=...
```

Các tags biến thiên theo từng request làm metric cardinality tăng mạnh.

### 11.4. Phân biệt JPA operation timer với end-to-end timer

HTTP server metrics có thể cho thấy request p95 là 350 ms trong khi JPA operation p95 là 40 ms. Phần còn lại cần được phân tích qua serialization, external calls, thread scheduling hoặc các bước khác.

## 12. Percentiles: đừng chỉ xem trung bình

Giả sử 10 requests có duration (ms):

```text
12, 13, 14, 14, 15, 15, 16, 16, 18, 260
```

Giá trị trung bình:

\[
\bar{T} = \frac{12+13+14+14+15+15+16+16+18+260}{10}
       = 39.3 \text{ ms}
\]

Phần lớn requests gần 15 ms, nhưng một request mất 260 ms. Trung bình che giấu hình dạng phân phối.

### 12.1. Những thống kê nên dùng

| Metric | Câu hỏi |
| --- | --- |
| Mean/average | Chi phí trung bình là bao nhiêu? |
| Median (p50) | Một request “điển hình” mất bao lâu? |
| p95 | 95% mẫu không vượt quá mức nào? |
| p99 | Tail latency ảnh hưởng nhóm request chậm nhất ra sao? |
| Max | Có outlier lớn không? |
| Throughput | Xử lý bao nhiêu requests/transactions mỗi giây? |
| Error rate | Bao nhiêu request timeout/failed? |

Percentile với mẫu quá nhỏ không ổn định; một bộ 10 observations chỉ minh họa khái niệm chứ không đủ làm SLO production.

### 12.2. Vì sao p95/p99 quan trọng với JPA?

Các nguyên nhân tail latency:

- Connection pool cạn.
- Database bị lock.
- GC pause do materialize graph lớn.
- Query plan thay đổi theo tham số.
- Cache miss.
- Một số customers có cực nhiều orders.
- Statement timeout/retry.
- Đường đi N+1 chỉ xuất hiện ở một tập dữ liệu.

### 12.3. Không tối ưu chỉ vì một outlier chưa hiểu nguyên nhân

Cần kết hợp traces, SQL timings, DB wait metrics, JVM GC/pool metrics và workload context trước khi quyết định đổi fetch plan.

## 13. Entity load count đo cái gì?

Một `Product` được nạp từ database hoặc một cache theo cơ chế provider có thể được đưa vào persistence context dưới dạng **managed entity instance**.

`Hibernate Statistics.getEntityLoadCount()` phản ánh các **entity load events** theo cách Hibernate thống kê.

Nó **không đồng nghĩa**:

- Số rows mà một SQL trả về.
- Số lần gọi `find()`.
- Số Java object bất kỳ được tạo.
- Số DTO objects được trả.
- Số SQL SELECT.
- Số entity distinct trong toàn database.

### 13.1. Ví dụ cùng một entity hai lần

```java
Product p1 = em.find(Product.class, 101L);
Product p2 = em.find(Product.class, 101L);

System.out.println(p1 == p2);
```

Nếu cả hai lượt trong một persistence context, JPA identity map đảm bảo một managed instance cho cùng persistence identity. Lượt sau thường không materialize thêm entity.

### 13.2. 100 rows không chắc là 100 entity loads

Một JOIN có thể trả 1.000 rows do cùng Order lặp lại với nhiều Lines, nhưng provider chỉ materialize 100 Order entities cùng 1.000 Line entities (minh họa), hoặc ít hơn nếu một phần đã managed.

### 13.3. Một câu query có thể tải nhiều entity types

```jpql
SELECT o
FROM PurchaseOrder o
JOIN FETCH o.customer
```

Một SQL có thể hydrate cả Order và Customer. Query count nhỏ, nhưng tổng entity load count có thể lớn hơn số Orders.

### 13.4. L1/L2 ảnh hưởng interpretation

Nếu entity đã có trong L1, có thể không phát sinh load event mới. Nếu L2 cache hit, provider có thể dựng state vào L1 mà không cần SQL; việc metrics tính load/fetch cần được giải thích theo Hibernate version.

Không dùng `entityLoadCount == 0` để khẳng định “không có dữ liệu được sử dụng”; application có thể dùng entities đã managed hoặc DTO projections.

## 14. Entity load khác entity fetch

Hibernate có các counters như:

```java
stats.getEntityLoadCount();
stats.getEntityFetchCount();
```

Ý định thường gặp:

- **Load**: entity đã được tải/materialize vào session/persistence context.
- **Fetch**: các lượt fetch entity liên quan theo cơ chế statistics của Hibernate, thường hữu ích khi phân tích secondary fetching.

### 14.1. Không suy entityFetchCount = SELECT count

Một fetch operation có thể dùng batching, cache hoặc join; một SQL có thể phục vụ nhiều entities.

Ngược lại, SQL có thể là aggregate query, DML hoặc DTO projection và không tương ứng với entity fetch.

### 14.2. Collection metrics có giá trị riêng

```java
stats.getCollectionLoadCount();
stats.getCollectionFetchCount();
```

Nếu tải 100 Orders rồi gọi `order.getLines().size()` với LAZY collections, những metrics này có thể giúp nhận diện pattern secondary collection loading.

### 14.3. Một baseline minh họa

| Kịch bản | SQL executions* | Entity loads* | Collection fetches* |
| --- | ---: | ---: | ---: |
| 100 Orders, không truy cập relations | 1 | ~100 | 0 |
| 100 Orders, mỗi Order có Customer khác, LAZY | ~101 | ~200 | 0 |
| 100 Orders, JOIN FETCH Customers | ~1 | ~200 | 0 |
| 100 Orders, mỗi Order truy cập Lines LAZY | ~101 | ~900 (100 Orders + 800 Lines) | ~100 |
| 100 Orders, batch fetch Lines | Có thể ít hơn đáng kể | ~900 | Tùy provider accounting |

*Các số là **giả định minh họa** với cache lạnh, dữ liệu cụ thể và mapping đơn giản. Không phải số cố định của JPA hoặc Hibernate trên mọi version.*

## 15. Collection load, số hàng JDBC và memory

Một Order có 1.000 lines và một query:

```jpql
SELECT DISTINCT o
FROM PurchaseOrder o
LEFT JOIN FETCH o.lines
WHERE o.id = :id
```

có thể trả nhiều JDBC rows dù kết quả Java chỉ là **một PurchaseOrder**.

### 15.1. Sơ đồ nhân bản rows

```text
Database ResultSet:
  Order#10 + Line#1
  Order#10 + Line#2
  Order#10 + Line#3
  ...
  Order#10 + Line#1000

Java result:
  PurchaseOrder#10
    lines=[Line#1,...,Line#1000]
```

Nếu chỉ đếm số Order objects trả về, ta sẽ bỏ qua lượng dữ liệu truyền qua network và chi phí materialize lines.

### 15.2. Hai collections fetch join tạo nguy cơ nhân bội

Nếu Order có 20 Lines và 15 Payments, join fetch hai quan hệ to-many có thể tạo khoảng:

\[
20 \times 15 = 300
\]

rows cho **một** Order, tùy join semantics. Đây là hiện tượng **row multiplication/cartesian explosion**.

Một query ít round-trip nhưng tạo quá nhiều rows có thể chậm hơn hai queries riêng biệt.

### 15.3. Hibernate MultipleBagFetchException

Hibernate có những giới hạn riêng khi fetch nhiều bag collections cùng lúc, có thể ném exception với một số mapping. Đây là provider-specific behavior và không nên được “chữa” bằng thay collection type bừa bãi mà chưa phân tích mô hình dữ liệu.

### 15.4. Phải đo khối lượng dữ liệu

Đối với query quan trọng, ngoài số SQL và entity loads, nên biết:

- Rows returned.
- Columns selected.
- ResultSet bytes.
- Graph depth và collection sizes.
- Allocated memory.
- GC activity.
- Thời gian serialization.

## 16. Đo query từ phía database

JPA chỉ cho biết một phần. Khi một SQL cụ thể chậm, cần điều tra **database execution plan**.

Với PostgreSQL (ví dụ):

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.reference, c.name
FROM purchase_orders o
JOIN customers c
  ON c.id = o.customer_id
WHERE o.status = 'SUBMITTED'
ORDER BY o.id
LIMIT 100;
```

### 16.1. EXPLAIN ANALYZE cho biết gì?

Tùy DBMS, có thể quan sát:

- Sequential scan hay index scan.
- Join strategy: nested loop, hash join, merge join.
- Estimated rows so với actual rows.
- Sort và memory usage.
- Buffers/cache effects.
- Execution time và planning time.
- Rows bị lọc qua conditions.

### 16.2. Không đánh đồng database plan time với HTTP time

Database có thể mất 5 ms để thực thi SELECT, trong khi service mất 150 ms vì:

- 100 lần round-trip query tương tự.
- JDBC chuyển dữ liệu.
- JPA materialization.
- Mapping sang DTO.
- Serialization.
- Pool waits.
- GC.

Cần đặt DB time trong bối cảnh toàn request trace.

### 16.3. Cẩn thận với EXPLAIN ANALYZE trên DML

Trong PostgreSQL, `EXPLAIN ANALYZE` thực sự thực thi statement để đo. Với `INSERT/UPDATE/DELETE` có thể làm thay đổi dữ liệu nếu không được rollback/kiểm soát.

Không chạy tùy tiện DML plan analysis trên production.

### 16.4. Database metrics theo workload

PostgreSQL có những công cụ như `pg_stat_statements` (nếu được bật), slow query logging và statistics views. MySQL, SQL Server, Oracle có cơ chế theo dõi riêng. Đây không phải API chuẩn JPA.

Khi điều tra, nên kết hợp query fingerprint, số lần gọi, tổng execution time, mean time và high-percentile latency nếu hệ thống đo được.

## 17. Tối ưu N+1 bằng JOIN FETCH

Một cách cải thiện ví dụ Orders–Customers là fetch Customer ngay cùng Orders:

```java
List<PurchaseOrder> orders =
    em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        JOIN FETCH o.customer
        ORDER BY o.id
        """,
        PurchaseOrder.class
    )
    .setMaxResults(100)
    .getResultList();

for (PurchaseOrder order : orders) {
    System.out.println(order.getCustomer().getName());
}
```

### 17.1. Điều gì thường cải thiện?

Với `ManyToOne` Customer, provider có thể dùng một SQL join để nạp cả Orders lẫn Customers, tránh 100 secondary selects.

Mô hình:

```text
Before:
  SELECT orders
  + SELECT customer #1
  + ...
  + SELECT customer #100

After:
  SELECT orders JOIN customers
```

### 17.2. Điều cần đo

| Trước–sau | Trước | Sau |
| --- | --- | --- |
| SQL executions | ~101 | ~1 |
| Orders loaded | 100 | 100 |
| Customers loaded | 100 | 100 |
| JDBC rows | ~200 qua 101 statements* | ~100 qua join* |
| Request time | Cần đo | Cần đo |
| Memory | Cần đo | Cần đo |

*Ví dụ giả định, không phải thông số cố định.*

### 17.3. JOIN FETCH không luôn giải quyết mọi thứ

- Nạp thêm entity state dù UI chỉ cần tên Customer.
- Có thể trùng rows khi fetch to-many.
- Có thể khiến paging khó khăn với collection fetch joins.
- Có thể tải dữ liệu không cần cho use case.
- Kết quả còn phụ thuộc mappings/provider.

**Hãy đo lại thời gian và entity count**, không chỉ xác nhận SQL count giảm.

## 18. EntityGraph: kiểm soát fetch plan theo use case

JPA có `EntityGraph` và các cache/fetch graph hints để chọn associations cần lấy.

Ví dụ:

```java
EntityGraph<PurchaseOrder> graph =
    em.createEntityGraph(PurchaseOrder.class);

graph.addAttributeNodes("customer");

List<PurchaseOrder> orders =
    em.createQuery(
        "SELECT o FROM PurchaseOrder o ORDER BY o.id",
        PurchaseOrder.class
    )
    .setHint("jakarta.persistence.fetchgraph", graph)
    .setMaxResults(100)
    .getResultList();
```

### 18.1. Vì sao hữu ích?

- Fetch plan gắn với use case thay vì thay global mapping thành EAGER.
- Có thể tránh N+1 cho những associations cần dùng.
- Giữ mappings mặc định LAZY ở những đường truy cập khác.

### 18.2. Một EntityGraph không bảo đảm đúng một SQL

JPA chỉ mô tả ý định fetch; provider có thể thực thi bằng JOIN hoặc secondary selects theo mapping, graph và implementation.

**Phải đếm SQL thực tế** sau khi thêm graph.

### 18.3. Không tự biến mọi relationship thành EAGER

Thay:

```java
@ManyToOne(fetch = FetchType.LAZY)
```

thành:

```java
@ManyToOne(fetch = FetchType.EAGER)
```

không tự bảo đảm một SQL join tối ưu. Với một số JPQL queries, provider có thể phát secondary selects để thỏa EAGER requirements.

Fetch plan nên được quyết định theo **từng use case**, không phải chỉ để làm test N+1 hôm nay pass.

## 19. DTO projection: giảm entity load khi chỉ cần dữ liệu hiển thị

Nếu UI chỉ cần ID, reference và Customer name, không nhất thiết load nguyên Order và Customer entities.

```java
List<OrderSummary> summaries =
    em.createQuery(
        """
        SELECT new com.example.shop.observability.OrderSummary(
            o.id,
            o.reference,
            c.name
        )
        FROM PurchaseOrder o
        JOIN o.customer c
        ORDER BY o.id
        """,
        OrderSummary.class
    )
    .setMaxResults(100)
    .getResultList();
```

### 19.1. Khi projection có lợi

- Chỉ lấy những columns cần cho UI/API.
- Không dựng entity graph đầy đủ cho một danh sách read-only.
- Không vô tình kích hoạt lazy relationships sau service.
- Có thể giảm heap allocation và cost của persistence context.
- Tránh dirty checking không cần thiết với các object read-only.

### 19.2. Entity load count sẽ thế nào?

Với projection chỉ lấy scalar fields vào DTO và không chọn managed entities, provider không cần materialize cả Order/Customer dưới dạng managed entities theo cùng cách như entity query.

Vì vậy **entity load count có thể giảm mạnh**, nhưng số DTOs vẫn là 100. Đây là lý do không dùng entity load count để đếm “số record hiển thị”.

### 19.3. Projection không mặc nhiên nhanh hơn mọi entity query

Một projection có thể dùng complex joins/subqueries, tạo rows lớn hoặc bị DB plan xấu. Vẫn phải đo latency/rows/SQL count trong tình huống thật.

### 19.4. Tránh over-fetching từ JSON

Trả thẳng entities từ controller có thể khiến serializer truy cập association graph mà service không chủ định. DTOs giúp ranh giới dữ liệu API rõ hơn và làm phép đo dễ xác định hơn.

## 20. Pagination và số entity được tải

Một API danh sách có 1 triệu Orders không nên gọi:

```java
em.createQuery(
    "SELECT o FROM PurchaseOrder o",
    PurchaseOrder.class
).getResultList();
```

rồi phân trang **trong memory**.

### 20.1. Pagination ở database

```java
List<PurchaseOrder> page =
    em.createQuery(
        """
        SELECT o
        FROM PurchaseOrder o
        ORDER BY o.id
        """,
        PurchaseOrder.class
    )
    .setFirstResult(0)
    .setMaxResults(50)
    .getResultList();
```

Provider chuyển pagination sang SQL phù hợp DB dialect.

### 20.2. Cần thứ tự ổn định

`ORDER BY o.id` giúp các trang có thứ tự xác định hơn. Trong production có inserts/deletes đồng thời, offset pagination vẫn có thể gặp dịch chuyển dữ liệu; keyset pagination có thể phù hợp cho feeds lớn.

### 20.3. Count query là một SQL bổ sung

Một paginated API thường muốn `totalElements`, nên cần:

```jpql
SELECT COUNT(o)
FROM PurchaseOrder o
WHERE o.status = :status
```

Đó là một SQL hợp lý thêm vào request. Không nên coi mọi query count hơn 1 là N+1.

### 20.4. Fetch join collection và pagination

`LEFT JOIN FETCH o.lines` kết hợp `setMaxResults(50)` có thể gây các vấn đề về pagination, duplicate rows hoặc in-memory pagination tùy Hibernate/provider.

Một hướng thường tốt hơn:

1. Query page IDs/roots.
2. Query detail/collections cho page đó bằng `IN :ids`.
3. Map kết quả giữ đúng thứ tự.
4. Đo tổng SQL, rows và entity loads.

Không tối ưu query count bằng cách phá tính đúng của phân trang.

## 21. Batch fetching và số truy vấn

Khi fetch join không phù hợp, provider có thể hỗ trợ **batch fetching**.

Với Hibernate, một cấu hình provider-specific:

```properties
hibernate.default_batch_fetch_size=32
```

có thể cho phép provider nhóm tải những associations còn LAZY, tùy mapping và state.

### 21.1. So sánh khái niệm

```text
No batching:
  SELECT customer WHERE id=1
  SELECT customer WHERE id=2
  ...
  SELECT customer WHERE id=100

With batching:
  SELECT customer WHERE id IN (?, ..., ?)
  SELECT customer WHERE id IN (?, ..., ?)
  ...
```

Nếu mỗi batch có 25 keys, 100 customers có thể được tải bằng khoảng 4 secondary queries thay vì 100, cộng query root. Đây là mô hình minh họa; provider có thể thực thi khác.

### 21.2. Entity load count không nhất thiết giảm

Dù query count giảm từ 101 xuống 5, ứng dụng vẫn cần 100 Orders + 100 Customers.

**Batching giảm round-trips; projection có thể giảm entity materialization; pagination giảm số records cần đọc.** Ba chiến lược phục vụ những nhu cầu khác nhau.

### 21.3. Batch size không phải số càng lớn càng tốt

`IN` có quá nhiều IDs có thể:

- Gặp giới hạn tham số DBMS.
- Tăng query planning cost.
- Chuyển dữ liệu không cần.
- Dùng nhiều memory.
- Có plan không tối ưu.

Cần benchmark các giá trị thực tế thay vì tự động đặt batch size rất lớn.

## 22. First-level cache: yếu tố làm sai benchmark

Mỗi `EntityManager` có một **persistence context/L1 identity map**.

Ví dụ:

```java
Product first = em.find(Product.class, 101L);

// Đo lượt hai:
long started = System.nanoTime();
Product second = em.find(Product.class, 101L);
long elapsed = System.nanoTime() - started;
```

Lượt hai có thể rất nhanh vì state đã managed; bạn đang đo cache hit, không đo một lần load database điển hình.

### 22.1. Kiểm soát L1 trong test

Một cách:

```java
em.clear();
```

sẽ detach managed entities trong persistence context đó. Nhưng:

- Không tự xóa L2.
- Có thể làm mất pending changes chưa flush/commit.
- Thay đổi đối tượng mà caller đang sử dụng.
- Không nên gọi tùy tiện trong production.

Trong performance test read-only, **mở EntityManager mới cho mỗi operation** thường giúp scope rõ hơn.

### 22.2. L1 không thuộc toàn bộ application

Một EntityManager khác có persistence context khác. Không suy từ cache hit trong EM A rằng EM B sẽ có cùng kết quả khi load.

### 22.3. Flush mode tác động thời gian

Một JPQL query có thể khiến provider flush pending changes trước khi đọc, tùy flush mode/transaction. Benchmark có thể đo cả INSERT/UPDATE bị flush chứ không chỉ SELECT như người viết tưởng.

Giữ transaction state sạch và flush mode nhất quán khi so sánh.

## 23. Second-level cache: đo cold và warm cases

Nếu provider bật shared/L2 cache, entity có thể được nạp mà không phát sinh SQL mới.

### 23.1. Hai kịch bản khác nhau

**Cold L2:**

```text
New EntityManager
  -> L1 miss
  -> L2 miss
  -> SQL SELECT
  -> entity materialization
```

**Warm L2:**

```text
New EntityManager
  -> L1 miss
  -> L2 hit
  -> entity state reused/hydrated
  -> perhaps no SELECT
```

### 23.2. Ghi rõ mục tiêu benchmark

- **Cold-cache performance**: hệ thống mới khởi động hoặc ít được truy cập.
- **Warm-cache performance**: request lặp lại trên dữ liệu phổ biến.
- **Mixed-cache performance**: gần workload production hơn.

Cả ba đều có giá trị. Không có nghĩa cứ xóa cache là đang đo “hiệu năng thật” duy nhất.

### 23.3. Cache.eviction để test

```java
emf.getCache().evict(Product.class, 101L);
```

hoặc:

```java
emf.getCache().evictAll();
```

có thể loại L2 cached entity entries trong phạm vi tiêu chuẩn, nhưng không đảm bảo xóa **provider-specific query cache**, database buffer cache hoặc các cache khác.

Không dùng `evictAll()` trên production chỉ để chạy một benchmark cá nhân; ảnh hưởng cache hit của các request khác.

### 23.4. Thống kê hit/miss

Hibernate Statistics có thể giúp hiểu cache:

```java
long hits =
    stats.getSecondLevelCacheHitCount();

long misses =
    stats.getSecondLevelCacheMissCount();

long puts =
    stats.getSecondLevelCachePutCount();
```

Một query count nhỏ do cache L2 có thể là kết quả mong muốn, nhưng vẫn cần đo freshness/consistency theo nghiệp vụ.

## 24. Query cache, database cache và đo đúng nguyên nhân

Một provider có thể có query result cache riêng, khác entity L2. Database còn có:

- Buffer pool/page cache.
- Query plan cache.
- Index caches.
- OS filesystem cache.
- Network/driver caches.

Nếu query chạy lần đầu 120 ms, lần sau 9 ms, không thể vội kết luận Hibernate L2 đã làm nhanh hơn. Có thể dữ liệu đã vào DB buffer cache hoặc plan đã được warm.

### 24.1. Những câu hỏi khi thấy chênh lệch

1. L1 có bị giữ từ lượt trước?
2. L2 có bật không?
3. Query cache có bật không?
4. Database buffer cache đang nóng?
5. Có query plan compilation ở lượt đầu?
6. JVM JIT đã warm chưa?
7. Connection pool đang khởi tạo?
8. Schema/data/parameter giống nhau?
9. GC hoặc lock contention có xảy ra?
10. Có cùng tracing/logging settings?

### 24.2. L2 cache hits không phải SQL execution count

Một L2 hit có thể tránh SELECT nhưng vẫn có ORM work. Một SQL COUNT query có thể chạy database mà không tạo entity load event.

### 24.3. Query cache cần đo riêng

Nếu provider hỗ trợ query cache, cần biết:

- Query cache hit/miss.
- Cache invalidation behavior.
- Tỷ lệ query result thay đổi.
- DB rows và entities còn cần tải.
- Memory và cache key cardinality.

Không gọi `EntityManagerFactory.getCache().evictAll()` là “xóa mọi query cache” theo một hợp đồng JPA portable.

## 25. Đếm object được tải không phải đo memory đầy đủ

Hai entity types có số lượng bằng nhau nhưng memory footprint khác:

```text
100 Product(id, sku, name)
100 Product(id, sku, name, description LOB,
            embedded details, large collections)
```

Entity load count có thể đều bằng 100, nhưng bộ thứ hai có thể tốn memory/network hơn.

### 25.1. Các thước đo bổ sung

- Heap allocation per operation.
- Young/old GC pauses.
- Live set sau request.
- Size của serialized response.
- JDBC result bytes.
- SQL column count.
- Collection sizes.
- Persistence context size.
- Thời gian DTO conversion.
- Number of proxies initialized.

### 25.2. Persistence context dài hạn

Nếu một transaction đọc hàng chục nghìn entities rồi giữ tất cả managed trong cùng EntityManager, persistence context có thể tiêu thụ nhiều memory và tạo chi phí dirty checking.

Đối với batch processing, cần pagination/chunking, có thể kết hợp `flush()/clear()` một cách có kiểm soát **sau khi đã đảm bảo pending changes được xử lý phù hợp**.

### 25.3. Streaming không miễn phí

`getResultStream()` hoặc provider cursor/stream có thể giảm peak memory trong những điều kiện nhất định, nhưng vẫn cần transaction/connection/resource lifecycle đúng và có thể tạo entities trong persistence context.

Không coi stream là cách tự động giải quyết mọi vấn đề entity load count.

## 26. Thiết kế một phép đo có thể lặp lại

Một benchmark JPA nên được viết như một thí nghiệm, không chỉ một dòng `System.nanoTime()`.

### 26.1. Xác định câu hỏi

Ví dụ:

> Với 100 Orders, mỗi Order thuộc một Customer khác nhau, phương án JOIN FETCH có giảm SQL count và p95 latency so với LAZY secondary selects không, khi kết quả business giống nhau?

### 26.2. Giữ dataset cố định

- 100 Orders.
- 100 Customers khác nhau.
- 8 Lines trên mỗi Order.
- Cùng schema/indexes.
- Cùng DBMS/version.
- Cùng JPA provider/version.
- Cùng JVM heap/GC settings.
- Cùng network topology.
- Cùng SQL isolation.
- Cùng concurrency workload.

Nếu phương án sau chạy trên một database khác có index mới, không thể quy mọi cải thiện cho JOIN FETCH.

### 26.3. Ghi rõ cache state

Tách các lần đo:

```text
A. Cold L1, cold L2
B. Cold L1, warm L2
C. Warm application under representative traffic
```

Không trộn A và C vào một con số rồi kết luận.

### 26.4. Warm up JVM và connection pool

Các lượt đầu có thể bao gồm:

- Class loading.
- JIT compilation.
- Connection pool initialization.
- ORM metadata/query plan caching.
- Database buffer cache warming.

Nên có warm-up phase rồi đo nhiều repetitions trên điều kiện rõ ràng.

### 26.5. Đo đủ metrics

Với mỗi run, có thể ghi:

```text
operation
dataset_size
cache_mode
sql_execution_count
jdbc_total_duration_ms
orm_operation_duration_ms
end_to_end_duration_ms
entity_load_count
entity_fetch_count
collection_fetch_count
result_rows
result_items
heap_allocated_bytes
error_count
```

Không phải hệ thống nào cũng có tất cả các metrics này. Hãy ghi những metric có nguồn đo đáng tin, không tự tạo giá trị ước lượng rồi báo như kết quả thật.

## 27. Baseline và bảng so sánh trước–sau

Giả sử một lần thử trong môi trường **minh họa, không phải số đã đo ở dự án thực tế**:

| Metric | LAZY N+1 | JOIN FETCH Customer | DTO projection |
| --- | ---: | ---: | ---: |
| Business results | 100 | 100 | 100 |
| JDBC SQL executions | 101 | 1 | 1 |
| Entity loads | 200 | 200 | 0 cho hai entity types trong ví dụ scalar DTO |
| JDBC total duration | 260 ms | 30 ms | 18 ms |
| Service duration | 330 ms | 65 ms | 35 ms |
| Response size | 20 KB | 20 KB | 20 KB |

### 27.1. Cách diễn giải đúng

- JOIN FETCH chủ yếu giảm SQL round-trips.
- DTO projection còn tránh dựng những managed entities không cần thiết.
- Response size bằng nhau vì API trả cùng dữ liệu hiển thị.
- Các latency numbers là **giả định minh họa**, phải đo lại trên hệ thống thật.

### 27.2. Cách diễn giải sai

> “DTO projection luôn nhanh nhất cho mọi trường hợp.”

Không. Với use case cần update entities, transaction/dirty checking hoặc relationship operations, việc tải managed entities có thể là yêu cầu nghiệp vụ.

### 27.3. Không chọn giải pháp chỉ bằng trung bình

Nếu JOIN FETCH có mean thấp nhưng p99 tăng do vài Orders cực nhiều Lines, cần phân tích tail latency, row multiplication và memory.

## 28. Query budgets trong integration tests

Một cách chống hồi quy là đặt **ngưỡng số SQL** cho một use case quan trọng.

Ví dụ:

> API danh sách 50 Orders kèm Customer names không được thực thi hơn 3 SELECTs ở dataset/cấu hình test xác định.

### 28.1. Tại sao có budget?

Giả sử trước refactor, test ghi:

```text
SQL executions: 2
```

Sau developer thêm một getter trong DTO mapper:

```java
summary.setCustomerTier(
    order.getCustomer().getMembership().getTier()
);
```

Nó có thể kích hoạt N+1 mới. Test dựa trên query budget có thể phát hiện trước production.

### 28.2. Cần đo đúng tầng

Để assert số SQL thực thi, dùng một SQL execution counter thực sự (DataSource/JDBC instrumentation) nếu đó là metric mục tiêu. `getPrepareStatementCount()` có thể dùng như **proxy/chỉ báo gần đúng** trong test Hibernate cô lập nhưng không nên tuyên bố nó luôn chính là execute count.

### 28.3. Query budget không phải luật tuyệt đối cho mọi input

Budget cần gắn với:

- Dataset size.
- Cache mode.
- Query parameters.
- Fetch plan.
- Provider version.
- Transaction boundary.
- Result shape.

Một budget `<= 3` cho mọi trường hợp từ 1 tới 1 triệu items có thể không thực tế; nên giới hạn hoặc phân cấp theo use case.

### 28.4. Performance tests không thay correctness tests

Một query rất nhanh nhưng trả thiếu records hoặc bỏ qua authorization không phải tối ưu thành công.

Test nên kiểm tra **kết quả business trước**, sau đó mới đo/budget performance.

## 29. Đo trong transaction ghi: SQL không chỉ là SELECT

Một service:

```java
@Transactional
public void updatePrices(List<PriceChange> changes) {
    for (PriceChange change : changes) {
        Product product =
            em.find(Product.class, change.productId());

        product.changePrice(change.newPrice());
    }
}
```

Có thể thực hiện:

- N SELECTs để load Products.
- N UPDATEs khi flush.
- Extra SQL tùy cascades/version/generation.
- Batch execution nếu cấu hình và DB hỗ trợ.

### 29.1. Timer chỉ bao service method có thể bỏ qua commit

Trong Spring `@Transactional`, transaction interceptor thường commit **sau khi method body trả về**. Nếu timer nằm trong method, có thể không đo chi phí flush/commit do interceptor thực hiện ở cuối.

Muốn đo end-to-end transaction duration, đặt instrumentation bao ngoài transaction boundary hoặc ở tầng transaction/JDBC instrumentation phù hợp.

### 29.2. Dirty checking có chi phí

Ngay cả khi SQL UPDATEs được batching, Hibernate còn quản lý dirty state và entity identity. Số managed entities lớn có thể tốn CPU/memory.

### 29.3. JDBC batch size khác fetch batch size

- `hibernate.jdbc.batch_size`: provider-specific setting cho batch các thao tác DML.
- `hibernate.default_batch_fetch_size`: provider-specific setting để tải entity/association theo batch.

Chúng giải quyết hai vấn đề khác nhau và tạo metrics khác nhau.

### 29.4. Không chỉ tối ưu số queries khi updates liên quan version

Một bulk JPQL UPDATE có thể giảm số SQL nhưng bỏ qua entity-level lifecycle callbacks và không tự bảo toàn semantics versioning giống managed changes.

Bất kỳ tối ưu nào chuyển từ managed updates sang bulk DML cần đánh giá correctness, cache và transaction behavior.

## 30. Hiệu năng và thời gian phản hồi HTTP

Giả sử:

```text
GET /orders -> 620 ms
    |
    +-- Connection acquisition: 200 ms
    +-- JDBC SQL execution:     80 ms
    +-- ORM hydrate:            50 ms
    +-- DTO mapping:            40 ms
    +-- JSON serialization:    120 ms
    +-- Other processing:      130 ms
```

Đây là **ví dụ phân rã minh họa**. Tại hệ thống thực tế, spans có thể chồng nhau, hoạt động async, và các totals không cộng đơn giản như mẫu trên.

### 30.1. Khi SQL count tốt mà request vẫn chậm

Có thể do:

- Pool waits.
- Large result mapping.
- Lazy access ở serializer.
- Network với service khác.
- JSON cycles/very large payload.
- CPU contention/GC.
- Authentication/authorization.
- Large transaction holding locks.
- Slow downstream client.

### 30.2. Khi DB execution nhanh mà SQL executions quá nhiều

N+1 là ứng viên rõ. Cải thiện có thể bằng fetch plan, batching, projection hoặc thiết kế API khác.

### 30.3. Khi SQL executions ít nhưng SQL duration rất lớn

Hãy điều tra:

- Query plan.
- Missing/wrong index.
- Cardinality estimates.
- Sorting/hashing.
- Lock waits.
- Full scans.
- Parameter skew.
- Rows/columns quá nhiều.
- Long-running transactions.

Không sửa N+1 khi vấn đề là một SQL statement có plan chậm.

## 31. Tracing nhiều tầng

Distributed tracing/OpenTelemetry có thể gắn spans theo request:

```text
HTTP GET /orders (traceId=...)
  |
  +-- app.orders.list
      |
      +-- JDBC SELECT purchase_orders
      |
      +-- JDBC SELECT customers
      |
      +-- DTO mapping
      |
      +-- JSON serialization
```

### 31.1. Tại sao tracing hữu ích?

Nó giúp nhìn **một request cụ thể** đã phát sinh câu SQL nào, lúc nào và trong context nào, thay vì chỉ thấy statistics toàn SessionFactory.

### 31.2. Metrics và traces bổ sung nhau

- **Metrics**: lượng lớn mẫu, xu hướng, p95/p99, alerts.
- **Traces**: causal path của từng request, SQL spans, bottlenecks.
- **Logs**: SQL detail/errors khi cần debug.
- **DB plans**: vì sao một statement có runtime cost như vậy.

### 31.3. Không log sensitive SQL params

Tracing SQL statements có thể chứa PII hoặc bí mật. Ưu tiên normalized SQL template/fingerprint và che bind values theo chính sách.

### 31.4. Sampling

Full tracing cho mọi request có thể tốn overhead/storage. Có thể lấy mẫu có chủ đích và giữ error/slow traces phù hợp hệ thống quan sát.

## 32. Dashboard quan sát JPA trong production

Một dashboard có thể gồm:

| Nhóm | Chỉ số |
| --- | --- |
| HTTP | Request rate, error rate, p50/p95/p99 |
| JPA operations | Count, duration histogram, errors |
| JDBC | Execute count per request, duration, timeout/error |
| Connection pool | Active, idle, pending, acquisition latency |
| Database | QPS, slow statements, wait events, CPU/IO |
| Cache | L2 hit/miss/put, query cache if used |
| ORM hydration | Entity/collection load/fetch counters hoặc sampled traces |
| Memory | Allocation, heap usage, GC pause |
| Business | Result item count, pagination, records scanned |

### 32.1. Tên operation phải có cardinality thấp

Đúng:

```text
operation="order-list"
operation="order-detail"
operation="product-search"
```

Không dùng:

```text
operation="order-detail-#123456789"
```

### 32.2. Counter tích lũy và rate

Một cumulative counter:

```text
total_sql_executions_since_start = 1020400
```

không nói một request đang tốn bao nhiêu. Cần rate theo thời gian hoặc per-request distribution.

### 32.3. Số lượng entities theo process khó quy cho endpoint

Hibernate Statistics toàn SessionFactory có thể cho biết xu hướng entity loads, nhưng muốn biết một endpoint cụ thể gây bao nhiêu tải thường cần instrumentation/tracing với context của operation hoặc cô lập benchmark.

### 32.4. Alert dựa trên SLO

Thay vì alert chỉ vì có SQL count > 5, có thể xem:

- Error rate tăng.
- p95 request latency vượt target.
- JDBC wait/DB time tăng bất thường.
- Connection pool saturation.
- Query count per request tăng đột ngột so với baseline.
- Cache hit rate tụt bất thường.

Không có ngưỡng đúng chung cho mọi ứng dụng.

## 33. Sự khác nhau giữa tải entity và tải DTO

Giả sử cần trả:

```json
[
  {"id": 1, "reference": "PO-1", "customerName": "A"},
  {"id": 2, "reference": "PO-2", "customerName": "B"}
]
```

Hai cách:

**Cách A — Entity query rồi map:**

```java
List<PurchaseOrder> orders = ...
return orders.stream()
    .map(o -> new OrderSummary(
        o.getId(),
        o.getReference(),
        o.getCustomer().getName()
    ))
    .toList();
```

**Cách B — JPQL constructor projection:**

```java
SELECT new com.example.shop.observability.OrderSummary(
    o.id, o.reference, c.name
)
FROM PurchaseOrder o
JOIN o.customer c
```

### 33.1. Cần đo những gì?

- SQL executions của cả hai.
- SQL rows và columns.
- Entity loads.
- End-to-end DTO materialization time.
- Heap allocation.
- Serialization time.
- Correctness (cùng data).
- Reusability/maintainability của query.

### 33.2. Khi cách A vẫn phù hợp

Nếu nghiệp vụ cần managed entities để thay đổi/cascade/lock/version, DTO projection không thay thế tương đương.

### 33.3. Khi cách B thường phù hợp

Read-only list endpoint chỉ cần ít columns và không có thao tác lifecycle trên entities.

### 33.4. Dữ liệu đã có trong L1 làm kết quả đổi

Nếu EntityManager đã managed các Orders/Customers từ thao tác khác, entity query có thể tận dụng state đã có. Một benchmark cô lập mới mở EM sẽ cho hình ảnh khác với một transaction dài đã load nhiều dữ liệu.

## 34. Đo khi có nhiều kiểu truy vấn trong một request

Một dashboard tổng hợp có thể hiển thị:

```text
GET /orders?status=SUBMITTED

Query A: count orders by status       1 SQL
Query B: fetch page order summaries   1 SQL
Query C: fetch totals by order IDs    1 SQL
Total: 3 SQL
```

Ba SQL này có thể là thiết kế phù hợp hơn một SQL khổng lồ.

### 34.1. Định nghĩa query budget theo use case

Ví dụ kỳ vọng:

- API list: 3 SQL, p95 dưới 150 ms với 50 rows.
- API detail: 2 SQL, p95 dưới 100 ms với 1 Order có tối đa 20 lines.
- Nightly batch: 20.000 SQL nhưng throughput phù hợp.

Đây là **mục tiêu ví dụ**, không phải tiêu chuẩn chung hay số đã đo.

### 34.2. Không cứng hóa budget dựa trên số được chọn tùy tiện

Một query bổ sung để kiểm tra authorization/tenant có thể là cần thiết. Nếu budget quá thấp dẫn đến bỏ kiểm tra an toàn, đó là “tối ưu” sai.

### 34.3. Correctness + latency + resource usage

Một yêu cầu “giảm 3 SQL xuống 1” phải kèm:

- Kết quả không thiếu/thừa.
- Không thay đổi transaction semantics.
- Không tạo duplicate/row explosion.
- Latency được cải thiện hoặc ít nhất không thoái hóa ngoài ngưỡng.
- Memory/DB load ở mức chấp nhận được.

## 35. Một quy trình điều tra N+1 từng bước

Giả sử endpoint Orders bị chậm khi số Orders tăng.

### Bước 1 — Thu thập triệu chứng

```text
/orders?limit=10   -> 11 SQL, 50 ms
/orders?limit=50   -> 51 SQL, 180 ms
/orders?limit=100  -> 101 SQL, 330 ms
```

Số liệu minh họa. SQL count tăng gần tuyến tính theo số Orders — dấu hiệu N+1.

### Bước 2 — Tìm SQL lặp

Log/tracing:

```sql
SELECT id, name FROM customers WHERE id = ?;
```

xuất hiện rất nhiều lần trong cùng request.

### Bước 3 — Tìm code kích hoạt

```java
order.getCustomer().getName();
```

được gọi khi mapping sang response DTO.

### Bước 4 — Xác định dữ liệu thực sự cần

Nếu chỉ cần Customer name, có thể chọn DTO projection. Nếu cần managed Customer cho nghiệp vụ, có thể chọn JOIN FETCH/EntityGraph.

### Bước 5 — Thực hiện thay đổi nhỏ

Ví dụ chuyển sang:

```jpql
SELECT new com.example.shop.observability.OrderSummary(
    o.id, o.reference, c.name
)
FROM PurchaseOrder o
JOIN o.customer c
ORDER BY o.id
```

### Bước 6 — Đo lại cùng dataset

Ghi SQL count, entity loads, JDBC total duration, p95, heap/GC và response correctness.

### Bước 7 — Thêm regression test

Đặt query budget hoặc performance test trên dataset có **nhiều distinct Customer IDs**, tránh test data che N+1.

### Bước 8 — Kiểm tra production-like load

Một test đơn luồng có thể pass nhưng hệ thống thực tế vẫn chậm vì pool contention hoặc DB saturation. Cần test đại diện concurrency.

## 36. Những vấn đề đo lường thường làm kết luận sai

### 36.1. Dữ liệu test quá ít

10 Orders có thể chạy nhanh dù N+1. Với 1.000 Orders, 1.001 round-trips có thể gây latency lớn.

### 36.2. Test chỉ dùng một Customer

L1 caching làm N+1 Customers không xuất hiện đầy đủ.

### 36.3. Chỉ đo query method, bỏ serialization

LAZY loading có thể xảy ra sau khi method trả về.

### 36.4. Lấy Hibernate prepared count làm SQL execution count tuyệt đối

PreparedStatements có thể được reuse/batched; mục tiêu metric cần định nghĩa chính xác.

### 36.5. Reset Hibernate Statistics trên production

Counters toàn SessionFactory bị xóa và ảnh hưởng quan sát của tác vụ khác.

### 36.6. Chạy benchmarks đồng thời rồi trừ global counters

Diff chứa activity của workers khác, không thuộc riêng use case.

### 36.7. Nhầm entity load với result item count

Một query trả 100 DTOs có thể không load 100 managed entities.

### 36.8. Nhầm một SQL join với ít dữ liệu

JOIN FETCH to-many có thể trả rất nhiều rows.

### 36.9. Không so sánh cold/warm cache

L2 hit rate làm SQL count biến động; kết luận dễ lệch.

### 36.10. Không đo DBMS đích

Query plan, lock, type, index và network khác biệt.

### 36.11. Bật TRACE logging trong benchmark rồi quên chi phí log

Kết quả có thể chậm do instrumentation.

### 36.12. Chỉ đo average

Tail latency/GC/lock contention bị che.

### 36.13. Không đo connection acquisition

App mất thời gian chờ pool nhưng bị quy cho SQL query.

### 36.14. Không phân biệt SELECT và DML

Một write transaction có nhiều SQL do flush/commit, không chỉ query ban đầu.

### 36.15. Không tính count query trong pagination

Một API list có page metadata có thể hợp lý khi cần hai SQL.

### 36.16. Thay mọi LAZY bằng EAGER

Có thể tạo nhiều secondary selects hoặc over-fetching ở use cases khác.

### 36.17. JOIN FETCH nhiều collections cùng lúc

Dễ row multiplication, memory pressure hoặc provider-specific exceptions.

### 36.18. Batch fetch size quá lớn

Có thể làm SQL `IN` quá to hoặc vượt giới hạn parameters.

### 36.19. Không giữ kết quả business tương đương

Giảm SQL count bằng cách trả thiếu data không phải tối ưu.

### 36.20. Đo bằng System.currentTimeMillis cho microbenchmark

Wall-clock adjustments và độ phân giải có thể không phù hợp. Dùng `System.nanoTime()` cho elapsed process measurements.

### 36.21. Coi database execution time là HTTP latency

Bỏ network, ORM hydration và serialization.

### 36.22. Không xác định transaction boundary

Timer kết thúc trước flush/commit có thể bỏ sót DML cost.

### 36.23. Dùng entity cache eviction liên tục trong production để “test lạnh”

Làm giảm cache hiệu năng của toàn hệ thống và ảnh hưởng users.

### 36.24. Không giữ DB statistics/indexes ổn định

Hai query plans khác nhau có thể do dữ liệu và statistics thay đổi, không phải do fetch plan.

### 36.25. Gắn raw SQL/IDs vào metrics

High-cardinality và rủi ro dữ liệu nhạy cảm.

### 36.26. Cho rằng mọi số đo được từ Hibernate đều thuộc chuẩn JPA

Hibernate Statistics là provider-specific API.

### 36.27. Coi EXPLAIN ANALYZE là read-only trong mọi trường hợp

Nó có thể thực thi DML; phải kiểm soát tác động.

### 36.28. Không kiểm tra số rows trả về

Một SELECT query duy nhất vẫn có thể đọc hàng triệu rows.

### 36.29. Không đo memory

Entity count gần nhau nhưng đồ thị/LOB/collections có thể chênh lệch memory lớn.

### 36.30. Chỉ tối ưu query count mà bỏ tổng chi phí hệ thống

Thêm complex joins có thể làm DB CPU tăng dù SQL count giảm.

## 37. Bài tập thực hành

### Bài 1 — Phân biệt query types

Một method gọi `em.find()` 10 lần cho 10 IDs khác nhau và không gọi JPQL.

**Hỏi:** `getQueryExecutionCount()` có đủ để khẳng định số SQL thực thi không?

**Đáp án:** Không. Dùng JDBC execution instrumentation hoặc quan sát SQL thực tế; các counters có semantics khác nhau.

### Bài 2 — L1 reuse

Gọi `em.find(Product.class, 1L)` hai lần trong cùng EM.

**Hỏi:** Có bắt buộc hai SELECT không?

**Đáp án:** Không. Lượt hai thường dùng managed entity trong L1.

### Bài 3 — N+1

100 Orders có 100 Customers khác nhau. Query Orders rồi truy cập Customer.name; cache lạnh.

**Hỏi:** Pattern thường gặp?

**Đáp án:** Một SELECT Orders cộng tối đa khoảng 100 secondary SELECT Customers nếu không có batch/fetch optimization.

### Bài 4 — Cache che N+1

Test có 100 Orders cùng một Customer.

**Đáp án:** Test data không lộ rõ N+1 vì Customer có thể được reuse trong L1. Hãy thêm nhiều distinct IDs.

### Bài 5 — JOIN FETCH

Chuyển sang `JOIN FETCH o.customer`.

**Hỏi:** Entity load count có bắt buộc giảm từ 200 xuống 100 không?

**Đáp án:** Không. Application vẫn cần 100 Orders và 100 Customers, dù SQL executions giảm.

### Bài 6 — DTO projection

API chỉ cần Order ID, reference, Customer name.

**Gợi ý:** Dùng JPQL constructor expression/DTO projection để hạn chế entity materialization.

### Bài 7 — Query count thấp nhưng chậm

Một query join trả 1 triệu rows.

**Đáp án:** Xem SQL execution plan, result rows, bytes, heap và DTO/entity hydration; một SQL vẫn có thể rất nặng.

### Bài 8 — Collection N+1

50 Orders, mỗi Order có collection Lines LAZY; loop gọi `getLines().size()`.

**Đáp án:** Có nguy cơ secondary collection fetches. Đo collection fetch count và JDBC SQL executions; cân nhắc batch fetching, projections hoặc fetch theo page.

### Bài 9 — Prepared count

Một `PreparedStatement` được execute hai lần.

**Đáp án:** Prepare count không bằng số lần execute.

### Bài 10 — Global Hibernate stats

Test A và Test B cùng dùng một SessionFactory và cùng chạy.

**Đáp án:** Snapshot delta sẽ bị lẫn. Isolate test workload hoặc dùng per-request instrumentation phù hợp.

### Bài 11 — Query method timer

Timer kết thúc khi `getResultList()` trả về, sau đó serializer truy cập lazy collections.

**Đáp án:** Timer chưa bao gồm phát sinh SQL ở serializer; mở rộng scope hoặc map DTO đầy đủ trước khi kết thúc service.

### Bài 12 — Write transaction

Timer ở trong `@Transactional` method, flush diễn ra lúc interceptor commit sau return.

**Đáp án:** Timer bên trong method có thể thiếu chi phí cuối transaction; dùng instrumentation bao ngoài transaction boundary.

### Bài 13 — p95 cao

Mean SQL time 10 ms nhưng p95 request 700 ms.

**Đáp án:** Xem lock contention, pool waits, GC, query count outliers, serialization và traces.

### Bài 14 — SQL plan

PostgreSQL query chậm trên production nhưng nhanh trên H2 local.

**Đáp án:** So sánh DBMS/version, indexes, statistics, dataset, parameters và execution plan thực tế.

### Bài 15 — Pagination

Một query fetch join to-many với `setMaxResults(50)`.

**Đáp án:** Cần kiểm tra pagination có được áp ở DB hay xử lý trong memory và nguy cơ duplicate rows. Có thể dùng two-step page IDs + batch details.

### Bài 16 — Cache cold

Benchmark gọi `emf.getCache().evictAll()` trên production trước mỗi request.

**Đáp án:** Không phù hợp. Chạy trong test cô lập; production cần theo dõi workload thật.

### Bài 17 — Entity load count

Một query trả 500 scalar DTOs.

**Hỏi:** Có bắt buộc entityLoadCount = 500 không?

**Đáp án:** Không; DTO projection không cần materialize cùng số managed entities.

### Bài 18 — Metric cardinality

Gắn `orderId` làm tag cho timer.

**Đáp án:** Không nên; tăng cardinality và nguy cơ lộ identifiers. Dùng operation label có tập giá trị nhỏ.

### Bài 19 — SQL logging

Bật `org.hibernate.SQL` DEBUG và đếm số dòng logger bằng tay.

**Đáp án:** Hữu ích để debug pattern nhưng không phải counter chính xác khi logs nhiều dòng/sampling hoặc nhiều hoạt động.

### Bài 20 — Thêm regression guard

Một endpoint trước refactor chạy 2 SQL, sau refactor chạy 52 SQL cho 50 Orders.

**Gợi ý:** Xác định SQL fingerprint lặp, bổ sung query budget test trong workload cô lập với distinct associations.

## 38. Câu hỏi tự kiểm tra

**1. Ba nhóm chỉ số chính khi đo hiệu năng JPA là gì?**

Số SQL/queries, thời gian và số entity được tải; cần thêm rows/cache/heap khi phù hợp.

**2. Một repository method tương đương một SQL không?**

Không.

**3. N+1 query nghĩa là gì?**

Một query tải roots và nhiều secondary queries tải dữ liệu phụ thuộc các roots.

**4. SQL count có luôn bằng JPQL count không?**

Không.

**5. Hibernate getPrepareStatementCount có luôn bằng số SQL executions không?**

Không, nó đo prepared statements theo statistics.

**6. Hibernate getQueryExecutionCount có đại diện toàn bộ SQL không?**

Không nên suy vậy.

**7. API Hibernate nào cho thống kê ORM?**

`SessionFactory.getStatistics()` với `org.hibernate.stat.Statistics`.

**8. Cấu hình bật Hibernate Statistics?**

`hibernate.generate_statistics=true`.

**9. Hibernate Statistics có chuẩn Jakarta Persistence không?**

Không, đây là provider-specific API.

**10. Global counters có tự tách từng HTTP request không?**

Không.

**11. Công cụ nào thường phù hợp để đếm JDBC executions?**

Instrumentation/DataSource proxy hoặc JDBC tracing ở tầng thực thi.

**12. SQL logging có đo chính xác mọi duration không?**

Không mặc nhiên.

**13. L1 có thể ảnh hưởng số SQL như thế nào?**

Managed entity đã có có thể được reuse không cần SQL mới.

**14. L2 có thể ảnh hưởng số SQL như thế nào?**

Cache hit có thể tránh truy vấn database.

**15. Vì sao cần đo cold và warm cache?**

Hai workload có behavior khác nhau; một trường hợp không đại diện toàn bộ.

**16. Entity load count có giống number of ResultSet rows không?**

Không.

**17. Một SQL có thể materialize bao nhiêu loại entity?**

Có thể nhiều entity types cùng lúc, tùy projection/fetch plan.

**18. JOIN FETCH Customer thường giúp gì?**

Giảm secondary selects để tải Customer khi use case cần association đó.

**19. JOIN FETCH có bắt buộc giảm entity count?**

Không.

**20. DTO projection có thể giúp gì?**

Giảm lượng entity state cần materialize khi chỉ cần scalar result fields.

**21. Pagination giúp gì?**

Giới hạn số rows/entities mà một request cần xử lý.

**22. Vì sao pagination với collection fetch join nguy hiểm?**

Row multiplication, duplicates hoặc provider-specific in-memory pagination.

**23. Batch fetching khác JDBC write batching thế nào?**

Một bên nhóm tải dữ liệu liên quan; bên kia nhóm DML executions.

**24. Query latency và request latency khác nhau không?**

Có, request còn nhiều tầng ngoài SQL.

**25. Nên dùng System.nanoTime hay currentTimeMillis cho elapsed benchmark ngắn?**

`System.nanoTime()`.

**26. Vì sao p95/p99 quan trọng?**

Cho thấy các requests chậm ở phần đuôi phân phối.

**27. EXPLAIN ANALYZE có ích khi nào?**

Khi cần hiểu database execution plan và chi phí của SQL cụ thể.

**28. EXPLAIN ANALYZE với UPDATE có thể gây tác động gì?**

Có thể thực thi DML; phải kiểm soát transaction/môi trường.

**29. Tại sao statement fingerprint hữu ích?**

Giúp nhóm SQL cùng cấu trúc và phát hiện một dạng query lặp nhiều lần.

**30. Vì sao không dùng orderId như metric label?**

High cardinality và rủi ro riêng tư.

**31. Khi nào cần kiểm tra connection pool?**

Khi request/JDBC duration cao nhưng DB statement execution không chậm tương ứng.

**32. Tại sao benchmark cần dataset ổn định?**

Để so sánh công bằng, không nhầm tác động của dữ liệu/indexes với code.

**33. Vì sao phải test với nhiều distinct Customer IDs?**

Để tránh L1 reuse che N+1.

**34. Tại sao chỉ đo một lượt chạy chưa đủ?**

JIT, cache warming, scheduling và nhiễu hệ thống gây biến thiên.

**35. Có nên giảm query count bằng mọi giá không?**

Không. Cần giữ correctness và kiểm tra latency, rows, memory, DB load.

**36. Khi nào cần kiểm tra memory/GC?**

Khi query count thấp nhưng nạp graph lớn hoặc latency tail cao.

**37. Hibernate entity fetch count có bằng SQL SELECT count không?**

Không nhất thiết; hai metrics có semantics khác nhau.

**38. Timer ở trong @Transactional method có thể thiếu gì?**

Chi phí flush/commit xảy ra sau method return do interceptor.

**39. Metrics, traces và DB plans bổ sung nhau thế nào?**

Metrics cho xu hướng, traces cho đường thực thi request, plans cho hành vi SQL phía database.

**40. Nguyên tắc đo hiệu năng JPA quan trọng nhất?**

Đo đúng tầng, đúng phạm vi và cùng dataset/cache state; kết hợp số SQL, latency và entity loads thay vì tối ưu một con số riêng lẻ.

## 39. Kịch bản tổng hợp: tối ưu API danh sách đơn hàng

Một ứng dụng thương mại có endpoint:

```text
GET /api/orders?status=SUBMITTED&page=0&size=50
```

Yêu cầu hiển thị:

- ID và reference Order.
- Customer name.
- Số lines.
- Tổng tiền từ giá snapshot.
- Tình trạng thanh toán.
- Tổng số Orders để phân trang.

### 39.1. Cách triển khai ban đầu

```text
findAllByStatus(Pageable)
       |
       v
Page<PurchaseOrder>
       |
       +-- for each order:
       |      customer.getName()       -> lazy Customer SELECT
       |      order.getLines().size()  -> lazy Lines SELECT
       |      calculate total          -> may initialize Lines
       |      payment.getStatus()      -> lazy Payment SELECT
       |
       v
JSON response
```

Dưới 50 Orders, có thể phát sinh một SQL cho page, một SQL count và hàng chục/hàng trăm secondary selects.

### 39.2. Thiết lập baseline đo

Đo:

```text
HTTP request latency p50/p95/p99
JDBC SQL executions per request
Top repeated SQL fingerprints
JDBC total duration
JPA entity loads
Collection fetches
L2 cache hits/misses
Response item count
Response payload size
DB scan/row counts for slow SQL
```

Chọn dataset có Customers, Lines, Payments phân bố giống production, không chỉ một vài Order giống nhau.

### 39.3. Phương án tối ưu

Một hướng khả thi:

1. Page Order IDs với điều kiện/filter, giữ sort ổn định.
2. Dùng projection query join Customer để lấy tên.
3. Dùng aggregate query group theo Order IDs để lấy line counts/totals nếu business semantics cho phép.
4. Dùng một query batch để lấy payment statuses.
5. Map DTOs trong service, không trả entities trực tiếp cho serializer.
6. Thực hiện count query riêng nếu UI cần tổng số phần tử.
7. Giữ các rules authorization/tenant tại query/service.

### 39.4. Vì sao không JOIN FETCH tất cả?

Nếu join fetch cả Lines và Payments cùng lúc, số rows có thể nhân bội và pagination phức tạp. Một vài query có kiểm soát có thể nhanh hơn.

### 39.5. Phương án thành công phải thỏa gì?

- Kết quả business giống ban đầu.
- Đúng authorization và tenant isolation.
- Page size/sort chính xác.
- SQL count tăng chậm hoặc ổn định theo page size.
- p95 latency cải thiện trên workload thực tế.
- Entity loads/heap allocation phù hợp.
- DB CPU/IO/rows scanned không tăng quá mức.
- Không dùng cache làm che dữ liệu lỗi thời.

### 39.6. Thiết lập regression guard

Trong CI:

- Database test từ migrations.
- 50 Orders với distinct Customers.
- Mỗi Order có nhiều Lines.
- Cache state định nghĩa rõ.
- Per-request SQL execution measurement.
- Assert response correctness.
- Assert SQL budget có lý do rõ ràng.
- Giữ baseline latency trong performance tests có đủ samples.

### 39.7. Quan sát sau triển khai

Theo dõi:

- p95/p99 request duration.
- Query execution count distribution.
- DB load và waits.
- Connection pool utilization.
- Error rate.
- Cache hit ratio.
- Response size.
- Traffic changes.

Nếu SQL count giảm nhưng DB CPU tăng mạnh hoặc p99 xấu đi, cần điều tra lại query plan/rows, không coi tối ưu hoàn thành chỉ vì một chỉ số đẹp hơn.

## 40. Kết luận

Đo hiệu năng JPA là quá trình quan sát **toàn bộ hệ quả của một thao tác persistence**, không chỉ đếm những lời gọi repository xuất hiện trong code.

Những bài học quan trọng:

1. **Đếm đúng số SQL executions** nếu mục tiêu là database round-trips; không dùng JPQL count hoặc prepared-statement count như những từ đồng nghĩa tuyệt đối.
2. **Đo thời gian đúng tầng:** database execution, JDBC operation, ORM operation, transaction boundary và HTTP response đều khác nhau.
3. **Đo số entity và collection được nạp** để nhận ra over-fetching, object graph quá lớn và vấn đề memory, nhưng không đánh đồng với JDBC rows hoặc DTO count.
4. **Hibernate Statistics là công cụ hữu ích nhưng provider-specific**, các counters thường ở phạm vi SessionFactory và cần workload cô lập nếu đo chênh lệch.
5. **SQL logging và query fingerprints giúp phát hiện N+1**, còn JDBC instrumentation và tracing giúp xác định executions/timings ở đúng phạm vi.
6. **L1/L2 cache có thể che hoặc thay đổi SQL count**, nên ghi rõ cold/warm state.
7. **JOIN FETCH, EntityGraph, batching, DTO projection và pagination giải quyết những loại chi phí khác nhau**; lựa chọn dựa trên dữ liệu đo.
8. **Một SQL không luôn nhanh hơn nhiều SQL** nếu nó nhân bội rows hoặc hydrate quá nhiều entities.
9. **Đo nhiều lần và xem phân phối p95/p99**, không chỉ một request hoặc giá trị trung bình.
10. **Giữ correctness, transaction semantics và schema behavior** khi tối ưu. Một query trả thiếu dữ liệu hoặc bỏ qua quyền truy cập không phải giải pháp hiệu năng.
11. **Tạo baseline và regression tests** theo use case, dataset, provider và cache state xác định.
12. **Kết hợp metrics, tracing, database execution plans và integration tests** để có kết luận đáng tin.

Mục tiêu cuối cùng không phải “đạt 1 query” hay “entity load count bằng 0”, mà là **cung cấp đúng dữ liệu nghiệp vụ với độ trễ, tải database và chi phí bộ nhớ chấp nhận được khi hệ thống hoạt động ở quy mô thực tế**.

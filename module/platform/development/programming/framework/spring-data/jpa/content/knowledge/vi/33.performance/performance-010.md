# Thống kê Hibernate, công cụ theo dõi SQL và chỉ số vận hành

## Mục tiêu

Tối ưu hiệu năng Spring Data JPA cần bằng chứng từ nhiều lớp. Hibernate có thể cho biết số câu lệnh JDBC được chuẩn bị, số query đã chạy, entity/collection được load hoặc fetch và thống kê theo từng query. Log SQL giúp nhìn câu lệnh thực tế cùng bind parameter. Spring Boot Actuator và Micrometer cung cấp chỉ số request, connection pool và tài nguyên ứng dụng. Execution plan của database giải thích vì sao một câu SQL chạy nhanh hoặc chậm.

Không có một con số đơn lẻ nào mô tả đầy đủ hiệu năng. Cần kết hợp:

- **Hibernate Statistics:** số lượng query/statement, entity load/fetch, collection fetch, cache và transaction.
- **SQL logging:** câu SQL, bind parameter, thời điểm và tần suất thực thi.
- **Application metrics:** latency p50/p95/p99, throughput, error rate, request timeout.
- **Connection pool metrics:** connection active/idle/pending, thời gian chờ và số lần timeout.
- **Database metrics và execution plan:** CPU, I/O, lock, index, row estimate/actual và thời gian thực thi.

Bài này hướng dẫn bật và đọc Hibernate Statistics, nhận diện N+1, theo dõi SQL an toàn, kết hợp Actuator/Micrometer và kiểm tra execution plan. Ví dụ Java 17+ với Spring Boot, Hibernate và H2 sẽ đo số JDBC statement của một query gây N+1 và so sánh với `JOIN FETCH`.

## 1. Xây dựng quy trình quan sát hiệu năng

Khi một endpoint chậm, hãy lần theo các lớp theo thứ tự:

1. Đo latency và throughput ở endpoint để biết vấn đề xảy ra với request nào và thường xuyên đến mức nào.
2. Đo thời gian ở service/repository để khoanh vùng phần truy cập dữ liệu.
3. Kiểm tra số SQL statement và thời gian từng câu; tìm N+1, query lặp, query quá rộng hoặc flush ngoài dự kiến.
4. Lấy execution plan của SQL chậm để xem scan, join, sort, index và số hàng thực tế.
5. Đối chiếu connection pool, lock wait, database CPU/I/O và cache để xác định nút thắt.
6. Thay đổi một yếu tố, chạy lại cùng workload và so sánh bằng cùng bộ chỉ số.

Ví dụ một request mất 900 ms không có nghĩa một câu SQL mất 900 ms. Request có thể chạy 40 query mỗi query 10 ms, chờ connection pool 300 ms, hoặc serialize một response rất lớn. Cần đo đúng lớp trước khi tối ưu.

## 2. Bật Hibernate Statistics

Hibernate cung cấp `org.hibernate.stat.Statistics` thông qua `SessionFactory`. Trong Spring Boot, có thể bật thống kê bằng property:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Hoặc bật bằng API:

```java
SessionFactory sessionFactory = entityManagerFactory.unwrap(SessionFactory.class);
sessionFactory.getStatistics().setStatisticsEnabled(true);
```

Với Spring Boot 3 và Hibernate 6, import API từ `org.hibernate.stat.Statistics` và `org.hibernate.SessionFactory`.

### Lấy Statistics từ EntityManagerFactory

```java
@Component
public class HibernateDiagnostics {
    private final Statistics statistics;

    public HibernateDiagnostics(EntityManagerFactory entityManagerFactory) {
        SessionFactory sessionFactory =
                entityManagerFactory.unwrap(SessionFactory.class);
        this.statistics = sessionFactory.getStatistics();
    }

    public Statistics statistics() {
        return statistics;
    }
}
```

`Statistics` thuộc về `SessionFactory`/persistence unit và được chia sẻ giữa các request trong ứng dụng. Các counter thường là số tích lũy từ lúc khởi động hoặc từ lần gọi `clear()` gần nhất.

### Cẩn thận khi gọi clear()

`statistics.clear()` reset thống kê toàn cục của SessionFactory. Điều này hữu ích trong một chương trình demo hoặc test chạy đơn luồng, nhưng không nên gọi ở mỗi request production: request này có thể xóa số liệu mà request khác hoặc dashboard đang quan sát.

Trong production, thường để counter tích lũy và thu thập định kỳ; nếu cần số liệu theo request, dùng tracing, timer hoặc datasource instrumentation có scope theo request thay vì reset Statistics toàn cục.

## 3. Những counter quan trọng

API `Statistics` có nhiều counter. Một số chỉ số thường dùng:

| Counter | Ý nghĩa | Dùng để điều tra |
| --- | --- | --- |
| `getPrepareStatementCount()` | Số JDBC statement Hibernate đã chuẩn bị | Ước lượng số statement phát sinh trong một khoảng đo. |
| `getQueryExecutionCount()` | Số lần thực thi HQL/JPQL query được Hibernate thống kê | Phát hiện query chạy lặp. |
| `getEntityLoadCount()` | Số entity được load vào persistence context | Nhận diện việc tải nhiều entity. |
| `getEntityFetchCount()` | Số entity được fetch theo cơ chế fetch ngoài lần load ban đầu | Tìm lazy fetch/N+1. |
| `getCollectionLoadCount()` | Số collection được load | Phát hiện tải nhiều collection. |
| `getCollectionFetchCount()` | Số collection được fetch | Tìm N+1 trên quan hệ to-many. |
| `getFlushCount()` | Số lần flush Session | Tìm flush thường xuyên hoặc ngoài dự kiến. |
| `getConnectCount()` | Số lần Hibernate lấy JDBC connection | Quan sát hoạt động connection ở tầng Hibernate. |
| `getTransactionCount()` | Số transaction được thống kê | Hiểu nhịp hoạt động transaction. |
| `getOptimisticFailureCount()` | Số optimistic locking failure | Theo dõi tranh chấp cập nhật. |
| `getSecondLevelCacheHitCount()` | Số lần hit second-level cache | Đánh giá cache entity/collection nếu đã bật. |
| `getQueryCacheHitCount()` | Số lần hit query cache | Đánh giá query cache nếu đã cấu hình. |

Counter không tự nói query nào chậm. Ví dụ `getPrepareStatementCount()` tăng cao có thể do N+1, do một request gọi nhiều repository method hoặc do batch job xử lý nhiều hàng. Cần đối chiếu với request trace và SQL log.

`entityLoadCount` và `entityFetchCount` có ý nghĩa khác nhau; không cộng chúng rồi coi là số hàng database đã trả. Chúng là thống kê hoạt động ORM, không phải số row đọc vật lý của database.

## 4. Thống kê theo từng query

Ngoài counter toàn cục, Hibernate có `QueryStatistics` để theo dõi query string cụ thể:

```java
Statistics statistics = sessionFactory.getStatistics();
QueryStatistics queryStats = statistics.getQueryStatistics(
        "select p from Product p where p.category = :category");

long executions = queryStats.getExecutionCount();
long averageMillis = queryStats.getExecutionAvgTime();
long maxMillis = queryStats.getExecutionMaxTime();
long totalMillis = queryStats.getExecutionTotalTime();
```

Query key phải khớp query string mà Hibernate thống kê. Query derivation, JPQL và native SQL có thể được ghi nhận theo dạng khác nhau; kiểm tra key trong môi trường chạy thực tế.

QueryStatistics thường cung cấp số lần chạy, thời gian trung bình, tổng, min/max và một số thông tin cache. Thời gian thống kê query không nhất thiết bằng latency endpoint: nó không bao gồm toàn bộ thời gian xử lý HTTP, serialize JSON hoặc logic service.

### Bật thống kê và log query chậm

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Hibernate có thể ghi thống kê Session/SessionFactory qua logger. Dùng mức log phù hợp để không tạo quá nhiều log trong môi trường có tải cao. Query-level statistics cũng có thể giúp tìm query chạy nhiều lần nhưng mỗi lần chỉ mất ít thời gian.

### Đọc counter theo khoảng thời gian

Nếu counter là số tích lũy, lấy snapshot ở hai thời điểm và tính delta:

```java
long before = statistics.getPrepareStatementCount();
// Run a measured workload.
long after = statistics.getPrepareStatementCount();
long statementsInWorkload = after - before;
```

Cách này chỉ cho kết quả chính xác theo workload nếu không có request khác đồng thời làm tăng counter. Trong production có concurrency, không dùng delta toàn cục để gán số statement cho một request cụ thể.

## 5. Theo dõi SQL bằng logging

Với Hibernate 6, có thể bật log SQL và bind parameter:

```properties
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.highlight_sql=true
spring.jpa.properties.hibernate.use_sql_comments=true

logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

- `org.hibernate.SQL=DEBUG` hiển thị SQL Hibernate gửi xuống JDBC.
- `org.hibernate.orm.jdbc.bind=TRACE` hiển thị giá trị bind parameter.
- `format_sql` định dạng câu SQL dễ đọc.
- `highlight_sql` tô màu SQL trong console terminal có hỗ trợ.
- `use_sql_comments` thêm comment hỗ trợ liên kết SQL với query/đường gọi trong một số trường hợp.

Trong Hibernate 5, logger bind parameter có tên khác; không sao chép cấu hình Hibernate 5 vào dự án Hibernate 6 mà không kiểm tra phiên bản.

### Ví dụ SQL được sinh

JPQL:

```java
@Query("select p from Product p where p.category = :category")
List<Product> findByCategory(@Param("category") String category);
```

SQL có thể tương tự:

```sql
select p.id, p.name, p.category, p.supplier_id
from products p
where p.category = ?
```

Bind log có thể hiển thị giá trị `BOOK` được gắn vào dấu `?`. SQL chính xác phụ thuộc dialect, mapping, naming strategy và phiên bản Hibernate.

### Rủi ro của bind logging

Bind parameter có thể chứa email, số điện thoại, token, địa chỉ, dữ liệu thanh toán hoặc thông tin cá nhân. TRACE có thể làm log rất lớn và lộ dữ liệu nhạy cảm.

Chỉ bật bind logging trong local/dev hoặc một khoảng điều tra có kiểm soát. Production nên hạn chế thời gian, che dữ liệu, kiểm soát quyền đọc log và tránh ghi payload nhạy cảm. Không đưa SQL parameter hoặc user ID riêng lẻ thành metric tag vì sẽ tạo high cardinality.

### show-sql và logging framework

`spring.jpa.show-sql=true` cũng có thể in SQL ra console, nhưng thường ít linh hoạt hơn logger chuẩn: khó lọc theo category, khó đưa vào pipeline log và không kiểm soát bind parameter giống logger. Với hệ thống cần observability, ưu tiên logging framework.

## 6. Nhận diện N+1 bằng thống kê và SQL log

N+1 xảy ra khi query đầu lấy N entity, sau đó ứng dụng phát thêm một query cho mỗi entity để lấy association hoặc collection lazy.

Ví dụ:

```java
List<Product> products = repository.findByCategory("BOOK");
for (Product product : products) {
    System.out.println(product.getSupplier().getName());
}
```

Nếu có 20 sản phẩm thuộc 20 supplier khác nhau, SQL có thể gồm:

1. Một query lấy danh sách product.
2. Hai mươi query lấy supplier theo từng product.

Statistics cho thấy số prepared statement tăng nhanh so với số lần gọi repository. SQL log hiển thị nhiều câu `select ... from suppliers where id = ?` có cấu trúc giống nhau.

### Cách sửa tùy use case

- Dùng `JOIN FETCH` nếu endpoint luôn cần association đó.
- Dùng `@EntityGraph` nếu muốn định nghĩa fetch plan theo repository method.
- Dùng projection/DTO nếu chỉ cần vài trường từ nhiều bảng.
- Dùng batch fetching khi cần giữ lazy loading nhưng muốn gom nhiều ID trong một query `IN`.
- Với collection lớn, cân nhắc query riêng hoặc phân trang thay vì fetch join nhiều collection cùng lúc.

Không thêm `EAGER` cho mọi quan hệ để chữa N+1. EAGER có thể chuyển vấn đề thành query lớn, join thừa hoặc tải dữ liệu không cần thiết. Chọn fetch plan theo từng use case.

### JOIN FETCH có giới hạn

Fetch join to-one thường dễ dự đoán. Fetch join collection cùng phân trang có thể làm Hibernate phải đọc nhiều hàng, cảnh báo hoặc phân trang trong bộ nhớ tùy phiên bản/cấu hình. Tránh fetch nhiều collection to-many trong một query vì có thể tạo tích Descartes và nhân bản dữ liệu.

## 7. Theo dõi thời gian query và slow query

Đếm số query chỉ là bước đầu. Một request có một query nhưng query đó scan hàng triệu bản ghi vẫn có thể chậm.

Nên theo dõi:

- Thời gian mỗi query hoặc nhóm query.
- Query p50/p95/p99 và max, không chỉ average.
- Số lần chạy của query trong một request.
- Rows returned và rows examined nếu database cung cấp.
- Lock wait, deadlock và timeout.
- Query plan có thay đổi sau khi dữ liệu lớn lên hay sau khi deploy không.

Slow query logging có thể được thực hiện ở database, JDBC proxy hoặc instrumentation. Hibernate cũng có thể ghi thông tin query theo ngưỡng trong các phiên bản hỗ trợ. Hãy chọn một nguồn slow-query có thể liên kết với SQL, timestamp và trace ID; tránh bật mọi logger ở TRACE lâu dài.

## 8. Spring Boot Actuator và Micrometer

Hibernate Statistics mô tả hoạt động ORM. Actuator/Micrometer bổ sung góc nhìn ứng dụng và connection pool.

Thêm dependency Actuator:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Cấu hình expose endpoint cần thiết:

```properties
management.endpoints.web.exposure.include=health,info,metrics
```

Trong môi trường local, có thể xem:

```text
GET /actuator/health
GET /actuator/metrics
GET /actuator/metrics/http.server.requests
GET /actuator/metrics/hikaricp.connections.active
GET /actuator/metrics/hikaricp.connections.pending
```

Tên metric phụ thuộc registry, connection pool và cấu hình instrumentation. Dùng `/actuator/metrics` để xem những metric thực sự được đăng ký; không giả định mọi ứng dụng đều có cùng danh sách.

### Chỉ số cần quan sát

| Nhóm | Chỉ số | Dấu hiệu cần điều tra |
| --- | --- | --- |
| HTTP | Request count, p95/p99 latency, error rate | Endpoint chậm hoặc lỗi tăng sau deploy. |
| HikariCP | Active, idle, pending, max, timeout | Pending tăng hoặc pool cạn cho thấy request đang chờ connection. |
| JDBC | Connection active/usage nếu được instrument | Thời gian giữ connection lâu. |
| Hibernate | Statement/query/entity/collection counters | Query lặp, fetch quá nhiều hoặc flush bất thường. |
| Database | CPU, I/O, locks, cache, slow query | Nút thắt nằm ở engine hoặc truy cập dữ liệu. |

Không phải mọi Hibernate Statistics counter đều tự động xuất hiện thành Micrometer metric. Nếu cần đưa chúng lên dashboard, đăng ký binder phù hợp với phiên bản hoặc tạo `MeterBinder` riêng; giữ metric tag có cardinality thấp.

### Ví dụ MeterBinder cho counter Hibernate

```java
@Bean
MeterBinder hibernateStatisticsBinder(EntityManagerFactory emf) {
    return registry -> {
        Statistics stats = emf.unwrap(SessionFactory.class).getStatistics();

        Gauge.builder("app.hibernate.prepared.statements",
                stats, Statistics::getPrepareStatementCount).register(registry);

        Gauge.builder("app.hibernate.entities.loaded",
                stats, Statistics::getEntityLoadCount).register(registry);

        Gauge.builder("app.hibernate.entities.fetched",
                stats, Statistics::getEntityFetchCount).register(registry);

        Gauge.builder("app.hibernate.queries.executed",
                stats, Statistics::getQueryExecutionCount).register(registry);
    };
}
```

Đây là gauge của counter tích lũy toàn SessionFactory. Không gọi `stats.clear()` khi binder đang được dashboard đọc. Nếu cần tốc độ tăng theo thời gian, hệ thống metric có thể tính rate/delta từ counter; không gắn raw SQL hoặc ID từng người dùng thành tag.

### Prometheus

Nếu dùng Prometheus, thêm `micrometer-registry-prometheus` cùng phiên bản được Spring Boot quản lý và expose endpoint `prometheus` theo chính sách bảo mật của hệ thống. Dashboard có thể hiển thị rate, histogram và percentile dựa trên metric đã instrument.

## 9. Theo dõi connection pool

Spring Boot thường dùng HikariCP làm connection pool mặc định khi có JDBC/JPA. Các chỉ số quan trọng:

- `active`: connection đang được sử dụng.
- `idle`: connection sẵn sàng.
- `pending`: thread đang chờ connection.
- `max`: giới hạn connection của pool.
- `connection timeout`: số lần không lấy được connection trong thời gian quy định.

Nếu `pending` tăng trong khi database CPU thấp, có thể request giữ connection quá lâu hoặc transaction mở quá rộng. Nếu pool luôn active gần max và database CPU/I/O cao, database có thể là bottleneck. Tăng pool size không phải lúc nào cũng tăng throughput; quá nhiều connection có thể làm database tranh chấp tài nguyên nhiều hơn.

Kiểm tra transaction boundary, query chậm, stream chưa đóng, connection leak và thời gian xử lý bên ngoài database trong transaction. Không giữ transaction mở trong lúc gọi API bên ngoài nếu không cần.

## 10. Execution plan của database

Hibernate cho biết SQL được gửi; database execution plan cho biết cách engine thực thi SQL.

Với PostgreSQL, có thể dùng:

```sql
EXPLAIN
SELECT id, name FROM products WHERE category = 'BOOK';
```

Để đo thực thi thật:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, name FROM products WHERE category = 'BOOK';
```

`EXPLAIN` thường chỉ lập kế hoạch ước lượng; `EXPLAIN ANALYZE` thực sự chạy câu lệnh và báo thời gian/rows thực tế cùng thông tin buffer. Không chạy `EXPLAIN ANALYZE` trên câu UPDATE/DELETE production một cách tùy tiện vì nó thực thi thay đổi dữ liệu. Dùng môi trường staging hoặc transaction có rollback được kiểm soát khi phù hợp.

Khi đọc plan, xem:

- Sequential/table scan hay index scan.
- Estimated rows so với actual rows.
- Join algorithm và thứ tự join.
- Sort, aggregate và temporary spill.
- Buffer hit/read và I/O.
- Filter loại bao nhiêu hàng sau khi đọc.
- Index có phù hợp với filter, sort và selectivity thực tế không.

Không tạo index cho mọi cột xuất hiện trong WHERE. Index làm tăng dung lượng và chi phí INSERT/UPDATE/DELETE. Dựa trên workload và execution plan để chọn index đơn hoặc composite.

## 11. Phân biệt các lớp thống kê

| Công cụ | Quan sát tốt | Không thay thế được |
| --- | --- | --- |
| Hibernate Statistics | Hoạt động ORM, query/statement/entity/cache counters | Execution plan và tài nguyên vật lý database. |
| Hibernate SQL logger | SQL và bind values tại tầng ORM | Latency tổng thể, pool wait và CPU/I/O. |
| JDBC proxy/P6Spy/datasource-proxy | SQL qua JDBC, timing và đôi khi bind parameters | Nội bộ ORM như entity load/fetch. |
| Actuator/Micrometer | Request, JVM, pool và metric ứng dụng | Chi tiết execution plan của từng SQL. |
| Database monitoring | CPU, I/O, locks, buffer, slow queries và plan | Mapping entity, N+1 trong code và logic service. |

Những công cụ này bổ sung cho nhau. Không cần bật tất cả cùng lúc trong production; chọn mức quan sát phù hợp với câu hỏi đang điều tra.

## 12. Ví dụ chạy được với Java 17+, Spring Boot 3.4.5, Hibernate và H2

Ví dụ tạo ba supplier và ba product. Quan hệ `Product.supplier` là LAZY. Một service chạy hai cách:

- Query đầu lấy product rồi truy cập supplier từng hàng, tạo N+1.
- Query sau dùng `JOIN FETCH` để lấy product và supplier trong một SQL.

Hibernate Statistics đo chênh lệch `prepareStatementCount` trong mỗi đoạn đo. Chương trình demo chạy một mình nên có thể dùng delta toàn cục; không dùng cách reset/delta này để đo từng request trong production nhiều luồng.

### Cấu trúc dự án

```text
hibernate-observability/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/observability/
        │   ├── ObservabilityApplication.java
        │   ├── Supplier.java
        │   ├── Product.java
        │   ├── SupplierRepository.java
        │   ├── ProductRepository.java
        │   └── CatalogDiagnosticsService.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>hibernate-observability</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:observability;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.use_sql_comments=true
logging.level.org.hibernate.SQL=DEBUG
management.endpoints.web.exposure.include=health,info,metrics
```

Bind parameter TRACE không bật mặc định trong ví dụ để tránh log giá trị đầu vào. Khi debug local có thể thêm:

```properties
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

### `Supplier.java`

```java
package com.example.observability;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "suppliers")
public class Supplier {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Supplier() {
    }

    public Supplier(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

### `Product.java`

```java
package com.example.observability;

import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    private String category;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "supplier_id", nullable = false)
    private Supplier supplier;

    protected Product() {
    }

    public Product(String name, String category, Supplier supplier) {
        this.name = name;
        this.category = category;
        this.supplier = supplier;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public Supplier getSupplier() {
        return supplier;
    }
}
```

### `SupplierRepository.java`

```java
package com.example.observability;

import org.springframework.data.jpa.repository.JpaRepository;

public interface SupplierRepository extends JpaRepository<Supplier, Long> {
}
```

### `ProductRepository.java`

```java
package com.example.observability;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository extends JpaRepository<Product, Long> {
    List<Product> findByCategory(String category);

    @Query("select p from Product p join fetch p.supplier "
         + "where p.category = :category")
    List<Product> findByCategoryWithSupplier(@Param("category") String category);
}
```

### `CatalogDiagnosticsService.java`

```java
package com.example.observability;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import java.util.List;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogDiagnosticsService {
    private final ProductRepository productRepository;
    private final EntityManager entityManager;
    private final Statistics statistics;

    public CatalogDiagnosticsService(
            ProductRepository productRepository,
            EntityManager entityManager,
            EntityManagerFactory entityManagerFactory) {
        this.productRepository = productRepository;
        this.entityManager = entityManager;
        this.statistics = entityManagerFactory
                .unwrap(SessionFactory.class)
                .getStatistics();
    }

    @Transactional(readOnly = true)
    public void compareFetchPlans() {
        long beforeNPlusOne = statistics.getPrepareStatementCount();
        List<Product> products = productRepository.findByCategory("BOOK");
        products.forEach(product ->
                System.out.println(product.getName()
                        + " -> " + product.getSupplier().getName()));
        long nPlusOneStatements =
                statistics.getPrepareStatementCount() - beforeNPlusOne;

        // Detach prior entities so the next measurement must fetch its own data.
        entityManager.clear();

        long beforeJoinFetch = statistics.getPrepareStatementCount();
        List<Product> fetched =
                productRepository.findByCategoryWithSupplier("BOOK");
        fetched.forEach(product ->
                System.out.println(product.getName()
                        + " -> " + product.getSupplier().getName()));
        long joinFetchStatements =
                statistics.getPrepareStatementCount() - beforeJoinFetch;

        System.out.println("N+1 JDBC statements: " + nPlusOneStatements);
        System.out.println("JOIN FETCH JDBC statements: " + joinFetchStatements);
        System.out.println("Hibernate entity loads: " + statistics.getEntityLoadCount());
        System.out.println("Hibernate entity fetches: " + statistics.getEntityFetchCount());
    }
}
```

Service có `@Transactional` để lazy association được truy cập khi persistence context còn mở. `entityManager.clear()` giữa hai phép đo giúp query thứ hai không dùng lại supplier đã load trong first-level cache. Trong ứng dụng nhiều request đồng thời, counter toàn cục có thể bị request khác làm thay đổi; đoạn đo này chỉ dành cho demo chạy đơn luồng.

### `ObservabilityApplication.java`

```java
package com.example.observability;

import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ObservabilityApplication {
    public static void main(String[] args) {
        SpringApplication.run(ObservabilityApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            SupplierRepository supplierRepository,
            ProductRepository productRepository,
            CatalogDiagnosticsService diagnostics) {
        return args -> {
            Supplier one = supplierRepository.saveAndFlush(new Supplier("Supplier One"));
            Supplier two = supplierRepository.saveAndFlush(new Supplier("Supplier Two"));
            Supplier three = supplierRepository.saveAndFlush(new Supplier("Supplier Three"));

            productRepository.saveAllAndFlush(List.of(
                    new Product("JPA Basics", "BOOK", one),
                    new Product("Spring Data JPA", "BOOK", two),
                    new Product("Hibernate Guide", "BOOK", three)
            ));

            diagnostics.compareFetchPlans();
        };
    }
}
```

### Chạy chương trình

```bash
mvn spring-boot:run
```

Với ba product và ba supplier khác nhau, phần SQL statement count dự kiến:

```text
N+1 JDBC statements: 4
JOIN FETCH JDBC statements: 1
```

Con số gồm một SELECT lấy product và ba SELECT lazy lấy supplier trong trường hợp đầu; query thứ hai lấy product cùng supplier bằng một JOIN FETCH. Dòng entity load/fetch tổng thể phụ thuộc trạng thái SessionFactory và các thao tác khởi tạo khác; không dùng một con số cố định cho dòng đó.

Trong log, có thể quan sát một câu SELECT từ `products` rồi ba câu SELECT tương tự trên `suppliers`. Sau khi dùng `JOIN FETCH`, một SQL statement lấy cả hai bảng.

### Xem Actuator metrics

Khi ứng dụng đang chạy:

```bash
curl http://localhost:8080/actuator/health
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/http.server.requests
```

Metric connection pool có thể xuất hiện nếu pool được instrument và metric binder đang hoạt động. Endpoint metrics chỉ trả các tên metric đã đăng ký trong ứng dụng.

## 13. Đưa quan sát vào production an toàn

### Chọn mức logging theo môi trường

- Local/dev: có thể bật SQL DEBUG và bind TRACE trong thời gian debug.
- Test/CI: bật SQL logging khi cần xác nhận fetch plan hoặc điều tra test chậm.
- Production: ưu tiên metric, trace và slow-query log có ngưỡng; hạn chế bind values và thời gian log chi tiết.

### Correlation ID và trace

Gắn trace ID hoặc request ID vào log để nối endpoint, service và SQL log trong cùng một lần xử lý. Nếu dùng distributed tracing, instrument HTTP, JDBC và các lời gọi downstream để biết thời gian nằm ở đâu.

Không dùng SQL nguyên văn, email, account ID hoặc request ID làm metric label. Những giá trị này tạo cardinality rất lớn và có thể làm hệ thống metric quá tải. Dùng metric tag ổn định như operation, repository area hoặc query category đã được kiểm soát.

### Overhead của statistics và log

Statistics và SQL logging có chi phí CPU, bộ nhớ và I/O log. Bind TRACE đặc biệt tốn dung lượng. Bật đúng phạm vi, đo overhead và tắt mức chi tiết sau khi điều tra xong.

### Bảo mật Actuator

Không expose tất cả Actuator endpoint ra Internet. Chỉ expose endpoint cần thiết, bảo vệ bằng authentication/network policy và hạn chế quyền đọc metric/log có thể tiết lộ cấu trúc hệ thống.

## 14. Chỉ số nào nên đưa vào dashboard?

Dashboard vận hành cho một ứng dụng JPA có thể nhóm như sau:

| Nhóm | Metric/góc nhìn | Câu hỏi cần trả lời |
| --- | --- | --- |
| Endpoint | Request rate, p95/p99 latency, 5xx | Người dùng đang bị ảnh hưởng ở endpoint nào? |
| Persistence | Query/statement count, entity fetch, collection fetch | Một request có phát sinh quá nhiều SQL không? |
| Database | Slow query, CPU, I/O, lock wait, deadlock | Database có đang là bottleneck? |
| Pool | Active/idle/pending connection, timeout | Request có phải chờ connection? |
| JVM | Heap, GC pause, thread count | Ứng dụng có bị áp lực bộ nhớ hoặc thread? |
| Cache | Hit/miss/put nếu bật cache | Cache có giảm tải thật hay chỉ tăng độ phức tạp? |

Đặt alert theo baseline và SLO của hệ thống, không dùng ngưỡng tùy ý. Ví dụ p99 tăng đồng thời pool pending và database lock wait là tín hiệu khác với p99 tăng trong khi SQL latency bình thường.

## 15. Lỗi thường gặp

1. **Chỉ bật SQL log rồi kết luận hiệu năng:** cần latency, query count, pool và execution plan.
2. **Nhìn average mà bỏ p95/p99:** tail latency có thể rất xấu dù average vẫn thấp.
3. **Nhầm entity load với entity fetch:** đây là các counter ORM khác nhau, không phải số row vật lý.
4. **Reset Statistics trong mỗi request:** counter toàn SessionFactory bị request khác xóa hoặc làm sai delta.
5. **Dùng global statement delta dưới concurrency:** không thể gán chính xác statement cho một request khi request khác cùng chạy.
6. **Bật bind TRACE lâu dài:** log phình to và có thể lộ PII/secret.
7. **Cho rằng một query chậm là do Hibernate:** kiểm tra execution plan, lock, I/O và network.
8. **Dùng `show-sql` thay cho logging pipeline:** khó lọc, gắn trace và kiểm soát dữ liệu.
9. **Tăng connection pool để chữa query chậm:** có thể làm database quá tải hơn.
10. **Thêm EAGER cho mọi quan hệ để chữa N+1:** có thể tạo join thừa và tải dữ liệu quá mức.
11. **Fetch join nhiều collection khi phân trang:** có thể nhân bản hàng, tăng bộ nhớ hoặc làm phân trang không hiệu quả.
12. **Tạo index theo cảm tính:** xác nhận bằng execution plan và workload thực tế.
13. **Dùng `EXPLAIN ANALYZE` trên DML production tùy tiện:** lệnh này thực thi câu lệnh.
14. **Expose Actuator không bảo vệ:** endpoint metrics/env/config có thể tiết lộ thông tin vận hành.
15. **Dùng metric tag có SQL hoặc ID động:** cardinality tăng không kiểm soát.

## 16. Checklist điều tra một endpoint JPA chậm

- [ ] Ghi nhận endpoint, trace ID, request size và latency p50/p95/p99.
- [ ] Xác định thời gian ở service, repository, JDBC và serialization.
- [ ] Đo số prepared statement/query trong workload được kiểm soát.
- [ ] Kiểm tra N+1 ở to-one và to-many association.
- [ ] Xem SQL thực tế và parameter đã bind trong môi trường an toàn.
- [ ] Lấy execution plan cho query chậm trên dữ liệu gần production.
- [ ] Kiểm tra estimated rows so với actual rows, scan, join, sort và buffer.
- [ ] Kiểm tra Hikari active/pending/idle và connection wait.
- [ ] Kiểm tra lock wait, deadlock, database CPU/I/O và cache.
- [ ] Thay đổi một fetch plan/index/query rồi chạy lại cùng workload.
- [ ] So sánh cả latency, statement count, rows, pool và database load.
- [ ] Tắt bind TRACE và logging chẩn đoán khi kết thúc điều tra.

## 17. Nguyên tắc thực hành

- Bật Hibernate Statistics khi cần đo hoạt động ORM và hiểu rõ counter là toàn cục.
- Dùng query-level statistics để tìm query chạy nhiều hoặc có max latency cao.
- Dùng SQL logger để xác nhận câu lệnh thật; bind TRACE chỉ bật có kiểm soát.
- Kết hợp Actuator/Micrometer với HikariCP metrics để theo dõi endpoint và pool.
- Dùng trace ID để nối request với log và SQL.
- Dùng execution plan của database để kiểm tra scan, join, index, rows và buffer.
- Dùng statistics delta chỉ trong workload cô lập; không reset global counters theo request.
- Nhận diện N+1 bằng statement count và SQL lặp, sau đó chọn fetch join, EntityGraph, projection hoặc batch fetching theo use case.
- Không tăng pool size hay thêm index nếu chưa có bằng chứng từ metrics và plan.
- Bảo vệ Actuator, che dữ liệu nhạy cảm và tránh high-cardinality metric tags.

Điểm cốt lõi: **Hibernate Statistics cho biết ORM đang làm bao nhiêu việc; SQL logging cho thấy câu lệnh và bind values; Actuator/Micrometer cho biết request và connection pool; execution plan cho biết database thực thi ra sao. Kết hợp các nguồn này giúp xác định đúng bottleneck, đo tác động của thay đổi và giữ observability an toàn trong production.**
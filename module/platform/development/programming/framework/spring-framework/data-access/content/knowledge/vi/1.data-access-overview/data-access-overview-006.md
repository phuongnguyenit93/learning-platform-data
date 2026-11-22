# Chọn SQL tường minh, ORM hoặc truy cập reactive theo bài toán

## 1. Mục tiêu và câu hỏi cần trả lời

Trong Spring Framework, cùng một cơ sở dữ liệu quan hệ có thể được truy cập qua **SQL tường minh với JDBC**, **ORM với JPA/Hibernate**, hoặc **SQL/truy cập dữ liệu không chặn với R2DBC**. Không có cách nào luôn nhanh hơn, đơn giản hơn hoặc đúng hơn trong mọi trường hợp. Quyết định phải dựa vào kiểu truy vấn, mô hình miền, tải thực tế, giao diện ứng dụng, giao dịch và khả năng vận hành.

Sau bài này, bạn cần giải thích và lựa chọn được:
- Khi nào cần kiểm soát trực tiếp câu SQL, phép JOIN, projection, batch và kế hoạch thực thi.
- Khi nào ánh xạ quan hệ–đối tượng, dirty checking và mô hình aggregate của JPA giúp giảm mã lặp.
- Khi nào truy cập không chặn bằng R2DBC có ích, và điều kiện để một luồng xử lý thật sự reactive từ đầu đến cuối.
- Sự khác nhau giữa transaction dạng imperative và transaction trong Reactor context.
- Cách chứng minh lựa chọn bằng phép đo và kiểm thử thay vì mặc định “ORM chậm” hoặc “reactive nhanh”.

Bối cảnh: một ứng dụng Spring Boot/Spring Framework dùng PostgreSQL; ví dụ Java 17+ và API phổ biến trong Spring Framework 6.1+/Spring Boot 3.2+. Những đoạn có chú thích tên tệp là mã **trong một dự án Spring Boot đã cấu hình dependency**, không phải chương trình Java độc lập chạy bằng `javac` thuần.

## 2. Phân biệt ba khái niệm trước khi chọn

### SQL tường minh/JDBC

**JDBC** là API truy cập cơ sở dữ liệu quan hệ kiểu blocking của Java. Trong Spring, thường dùng:
- `JdbcTemplate` và `NamedParameterJdbcTemplate`: thực thi truy vấn, cập nhật, ánh xạ `ResultSet` và chuyển lỗi JDBC sang hệ ngoại lệ Spring.
- `JdbcClient` (Spring Framework 6.1+): giao diện fluent thống nhất cho nhiều tác vụ query/update; vẫn chạy trên JDBC và vẫn blocking.
- Công cụ xây SQL như jOOQ, khi cần SQL mạnh và an toàn kiểu dữ liệu, là lựa chọn bổ sung; không biến JDBC thành reactive.

“SQL tường minh” nghĩa là ứng dụng sở hữu nội dung truy vấn và quyết định những cột/row cần lấy. Nó **không** đồng nghĩa với nối chuỗi SQL bằng tay: giá trị đầu vào phải được bind bằng tham số.

### ORM/JPA

**ORM** ánh xạ đối tượng và quan hệ giữa đối tượng thành bảng/hàng trong cơ sở dữ liệu. Trong hệ Spring:
- **JPA/Jakarta Persistence** là đặc tả.
- **Hibernate** là một nhà cung cấp JPA thường dùng.
- **Spring Data JPA** tạo repository và các tiện ích query trên JPA; không phải một ORM hoàn toàn khác.
- `EntityManager`/persistence context quản lý trạng thái entity; thay đổi entity được đồng bộ với database khi flush (thường tại commit).

JPA vẫn sinh và thực thi SQL qua JDBC. Sử dụng repository không xóa nhu cầu hiểu SQL, chỉ số, transaction, lazy loading và truy vấn được sinh ra.

**Spring Data JDBC** là một lựa chọn khác với JPA: ánh xạ aggregate đơn giản trên JDBC, không có persistence context hay cơ chế lazy loading/dirty checking tương tự JPA. Đừng gom Spring Data JDBC và JPA thành cùng một mô hình ORM.

### R2DBC/reactive access

**R2DBC** là SPI/driver để truy cập cơ sở dữ liệu quan hệ bằng thao tác bất đồng bộ, không chặn luồng trong thời gian chờ I/O khi driver hỗ trợ. Spring có:
- `DatabaseClient` để viết SQL reactive trực tiếp.
- `R2dbcEntityTemplate` để mapping/query theo entity.
- Spring Data R2DBC repositories với `Mono<T>`, `Flux<T>`.

Reactive **không phải** “JPA trả về `Mono`” hay “gọi `JdbcTemplate` trong `Mono.fromCallable`”. JDBC/JPA vẫn là blocking khi được bọc trong reactive type. Spring Data R2DBC có mapping đối tượng, nhưng không có persistence context và hệ quan hệ lazy-loading như Hibernate ORM.

## 3. Cơ chế thực thi và tài nguyên

```text
SQL tường minh (blocking)
HTTP/Service → JdbcClient/JdbcTemplate → JDBC driver
             → JDBC connection → database → RowMapper/DTO

JPA ORM (blocking)
HTTP/Service → Repository/EntityManager → Hibernate
             → SQL sinh ra → JDBC connection → database
             → managed entity/persistence context

R2DBC (non-blocking I/O)
Reactive handler/service → Mono/Flux → DatabaseClient/R2dbcEntityTemplate
                         → R2DBC driver/connection → database
                         → publisher phát row theo nhu cầu
```

- **JDBC/JPA:** một thao tác chờ I/O thường giữ luồng gọi đến khi hoàn tất; connection pool giới hạn số truy vấn đồng thời. Với virtual threads trên Java 21, chi phí giữ *platform thread* có thể giảm, nhưng JDBC vẫn là API blocking và pool/database vẫn giới hạn năng lực.
- **JPA:** ngoài chi phí SQL còn có materialize entity, persistence context, dirty checking, cascade và load quan hệ. Những khả năng này có giá trị nếu logic miền cần chúng, nhưng tốn tài nguyên khi chỉ lấy ba cột của báo cáo.
- **R2DBC:** có thể duy trì nhiều tác vụ đang chờ I/O với ít luồng hơn, nhưng **không làm database thực thi truy vấn nhanh hơn**. Số connection, giới hạn giao dịch, lock, index và độ trễ truy vấn vẫn quan trọng. `Flux` không tự động đồng nghĩa dữ liệu được server stream vô hạn hoặc toàn bộ tầng ứng dụng có backpressure.

## 4. So sánh để ra quyết định

| Tiêu chí | SQL tường minh qua JDBC | ORM/JPA (Hibernate) | R2DBC / Spring Data R2DBC |
|---|---|---|---|
| Cách lập trình | SQL + mapper/DTO do ứng dụng kiểm soát | Entity, quan hệ, repository, query JPQL/Criteria/native | SQL hoặc template/repository trả `Mono`/`Flux` |
| I/O database | Blocking | Blocking, thường thông qua JDBC | Non-blocking nếu dùng driver R2DBC thật |
| Kiểm soát SQL | Cao, thuận lợi với JOIN/projection/CTE/vendor features | Có nhưng cần hiểu SQL sinh ra; có thể dùng native SQL | Cao với `DatabaseClient`; tùy mức hỗ trợ của driver/dialect |
| Mô hình miền có quan hệ phức tạp | Phải tự mapping/chỉnh sửa trạng thái | Mạnh với identity map, dirty checking, cascading, associations | Mapping đơn giản hơn; quản lý quan hệ/aggregate tường minh hơn |
| Giao dịch | `PlatformTransactionManager`, thường `JdbcTransactionManager`/`DataSourceTransactionManager` | `JpaTransactionManager` và persistence context | `ReactiveTransactionManager`/`R2dbcTransactionManager`, Reactor context |
| Chi phí cần quản lý | SQL/mapping và vòng đời connection | N+1, fetch strategy, flush, persistence context | Reactive composition, subscription, context, driver/pool |
| Hợp với | Báo cáo, SQL tối ưu, batch, legacy SQL | CRUD gắn với miền và vòng đời entity | Reactive pipeline có nhiều I/O đồng thời và driver tương thích |

Bảng mô tả khuynh hướng, không phải bảo đảm tốc độ. Một truy vấn JPA được thiết kế đúng có thể nhanh hơn SQL thủ công viết kém; một truy vấn R2DBC có thể chậm hơn JDBC khi tải thấp vì chi phí điều phối.

## 5. Quy trình chọn trong dự án thực tế

Hãy xét lần lượt:

1. **Nhiệm vụ chính là đọc/ghi kiểu nào?** Nếu trọng tâm là truy vấn nhiều bảng, báo cáo, aggregate SQL, projection lớn, cần kiểm soát index/hint/CTE, hãy ưu tiên **SQL tường minh**. Nếu trọng tâm là thay đổi trạng thái các entity gắn quy tắc nghiệp vụ và quan hệ, cân nhắc **JPA**.
2. **Luồng gọi hiện tại có blocking không?** Ứng dụng Spring MVC, client HTTP blocking, thư viện xác thực blocking và database JDBC thường có lợi từ stack imperative đơn giản. Nếu sử dụng WebFlux/Reactor và nhiều I/O không chặn trong toàn pipeline, **R2DBC** là ứng viên đáng thử.
3. **Driver và database hỗ trợ đầy đủ tính năng yêu cầu không?** Kiểm tra driver R2DBC cho hệ quản trị cụ thể, pooling, kiểu dữ liệu, transaction, isolation, batch, timeout, cancellation và quan sát hệ thống. Thiếu hỗ trợ quan trọng thì không ép reactive.
4. **Giao dịch liên kết những gì?** Giao dịch JPA/JDBC trên một `DataSource` và giao dịch R2DBC trên một `ConnectionFactory` không tự trở thành một transaction ACID duy nhất. Nếu cần thao tác nhất quán trên cả hai, phải thiết kế ranh giới hoặc dùng giải pháp phối hợp phù hợp.
5. **Chi phí đội ngũ và hệ thống?** Xét kiến thức SQL/JPA/Reactor, tooling, test, lỗi production, khả năng debug và chi phí chuyển đổi.
6. **Đã đo bằng tải thực tế chưa?** Chọn phương án đơn giản đáp ứng yêu cầu trước, rồi chứng minh thay đổi bằng throughput, p95/p99, pool saturation, SQL plan và lỗi.

### Cây quyết định ngắn

```text
Bài toán có cần nhiều quan hệ/entity lifecycle/dirty checking?
  ├─ Có → JPA là mặc định để đánh giá
  └─ Không → SQL tường minh là mặc định để đánh giá
             ↓
Luồng xử lý có thật sự reactive end-to-end, nhiều I/O chờ,
và driver/tài nguyên hỗ trợ?
  ├─ Có → Đo thử R2DBC; có thể dùng SQL qua DatabaseClient
  └─ Không → Giữ JDBC hoặc JPA
             ↓
Benchmark và kiểm thử đúng ranh giới giao dịch
  ├─ Đạt SLA, dễ bảo trì → Giữ lựa chọn
  └─ Không đạt → Tối ưu SQL/index/pool, rồi xét đổi công nghệ
```

“Reactive” là đặc điểm thực thi I/O; “SQL tường minh hay mapping entity” là mức trừu tượng. Với R2DBC, vẫn có thể viết SQL thủ công hoặc dùng template/repository.

## 6. Một bài toán chung: đơn hàng

Giả sử có bảng PostgreSQL tối giản:

```sql
CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name VARCHAR(150) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL CHECK (total_amount >= 0),
    status VARCHAR(16) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX idx_orders_status_id ON orders (status, id);
```

Hai yêu cầu được tách rõ:
- **Màn hình danh sách** chỉ cần `id`, `customer_name`, `total_amount` của đơn có `status = 'NEW'`: projection/SQL rõ ràng, không cần materialize graph.
- **Thanh toán đơn hàng** chuyển `NEW → PAID` đúng một lần, cần kiểm soát concurrent update; có thể biểu diễn bằng hành vi của entity JPA hoặc câu `UPDATE ... WHERE status = 'NEW'`.

Mỗi ví dụ dưới đây là **một phương án triển khai độc lập**; không cấu hình cả ba cùng lúc để làm một transaction. Các tệp ở package `example.data`; thêm dependency tương ứng, PostgreSQL connection configuration và schema ở trên rồi mới chạy ứng dụng.

### 6.1. SQL tường minh với JdbcClient

Dependency Gradle điển hình:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

`OrderView.java`:

```java
package example.data;

import java.math.BigDecimal;

public record OrderView(long id, String customerName, BigDecimal totalAmount) {}
```

`JdbcOrderQuery.java`:

```java
package example.data;

import java.util.List;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcOrderQuery {
    private final JdbcClient jdbc;

    public JdbcOrderQuery(JdbcClient jdbc) {
        this.jdbc = jdbc;
    }

    public List<OrderView> findByStatus(String status) {
        return jdbc.sql("""
                SELECT id, customer_name, total_amount
                FROM orders
                WHERE status = :status
                ORDER BY id
                """)
            .param("status", status)
            .query((rs, rowNum) -> new OrderView(
                rs.getLong("id"),
                rs.getString("customer_name"),
                rs.getBigDecimal("total_amount")))
            .list();
    }

    public boolean markPaid(long id) {
        int affected = jdbc.sql("""
                UPDATE orders
                SET status = 'PAID', version = version + 1
                WHERE id = :id AND status = 'NEW'
                """)
            .param("id", id)
            .update();
        return affected == 1;
    }
}
```

**Giải thích:** `:status`/`:id` là tham số bind, tránh biến input thành SQL thực thi. `RowMapper` chỉ ánh xạ đúng ba cột cần trả về. `UPDATE` với điều kiện trạng thái là một dạng **compare-and-set tại DB**: hai lời gọi cạnh tranh không thể cùng chuyển một đơn từ `NEW` sang `PAID` thành công; lời gọi sau nhận `affected = 0`. Cần phân biệt không tìm thấy ID với trạng thái không hợp lệ nếu giao diện nghiệp vụ yêu cầu mã lỗi riêng.

Nếu nhiều lệnh phải nguyên tử, đặt `@Transactional` trên **phương thức service public** được gọi qua Spring proxy, chẳng hạn cập nhật đơn và ghi một dòng audit cùng transaction manager JDBC. Bản thân một lệnh `UPDATE` như trên đã là atomic statement đối với PostgreSQL, nhưng một workflow nhiều câu lệnh phải có transaction rõ ràng. Với batch lớn hoặc stored procedure, xem `JdbcTemplate`/API batch chuyên dụng thay vì cố dùng một phương thức `JdbcClient` cho mọi thứ.

### 6.2. JPA cho vòng đời entity

Dependency Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
```

`OrderEntity.java`:

```java
package example.data;

import java.math.BigDecimal;
import jakarta.persistence.*;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "customer_name", nullable = false)
    private String customerName;

    @Column(name = "total_amount", nullable = false)
    private BigDecimal totalAmount;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Version
    private long version;

    protected OrderEntity() {}

    public OrderEntity(String customerName, BigDecimal totalAmount) {
        this.customerName = customerName;
        this.totalAmount = totalAmount;
        this.status = OrderStatus.NEW;
    }

    public void markPaid() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException("Order is not NEW");
        }
        this.status = OrderStatus.PAID;
    }
}

enum OrderStatus { NEW, PAID }
```

`OrderRepository.java`:

```java
package example.data;

import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderEntity, Long> {}
```

`OrderService.java`:

```java
package example.data;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void markPaid(long id) {
        OrderEntity order = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Order not found"));
        order.markPaid();
        // Managed entity: Hibernate phát UPDATE khi flush/commit.
    }
}
```

**Giải thích:** Trong transaction, entity đọc từ repository là **managed**. Thay đổi `status` được Hibernate nhận biết và đồng bộ khi flush; không cần gọi `save` để cập nhật entity đang managed. `@Version` giúp phát hiện **optimistic locking conflict** khi hai transaction đồng thời sửa cùng một version; ứng dụng phải chọn cách trả lỗi/retry theo nghiệp vụ. Giá trị version phải có cột tương ứng trong schema.

Điểm mạnh của JPA lộ rõ khi entity có quan hệ và hành vi miền phức tạp, nhưng cũng cần chủ động kiểm soát:
- `LAZY`/`EAGER`, `JOIN FETCH`, `@EntityGraph` và projection cho đúng use case; không load toàn bộ quan hệ chỉ để dựng danh sách.
- N+1 query: ví dụ đọc 50 đơn rồi truy cập khách hàng lazily trong vòng lặp có thể sinh thêm 50 truy vấn. Theo dõi số query và tối ưu fetch strategy.
- `flush` là đồng bộ SQL chưa chắc đã `commit`; `@Transactional(readOnly = true)` là gợi ý tối ưu/framework contract, không nên xem là bảo đảm database từ chối mọi câu ghi.
- Tránh trả trực tiếp entity với lazy association ra JSON sau khi transaction đã đóng; tạo DTO trong service/projection phù hợp.

JPA không cấm SQL tường minh: `@Query`, native query, projection hay `JdbcClient` cho một báo cáo vẫn có thể là lựa chọn tốt trong cùng ứng dụng nếu ranh giới giao dịch được thiết kế rõ.

### 6.3. R2DBC với DatabaseClient

Dependency Gradle điển hình:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
```

Với PostgreSQL, cấu hình `spring.r2dbc.url` theo dạng `r2dbc:postgresql://host:port/db`, cùng user/password; đây là kết nối khác với `spring.datasource.url` của JDBC. Kết hợp Spring WebFlux khi HTTP pipeline cũng reactive; thư viện Reactor/R2DBC tự nó không bắt buộc controller phải là WebFlux.

`ReactiveOrderQuery.java` (dùng lại record `OrderView` ở trên):

```java
package example.data;

import java.math.BigDecimal;
import java.util.Objects;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;

@Repository
public class ReactiveOrderQuery {
    private final DatabaseClient db;

    public ReactiveOrderQuery(DatabaseClient db) {
        this.db = db;
    }

    public Flux<OrderView> findByStatus(String status) {
        return db.sql("""
                SELECT id, customer_name, total_amount
                FROM orders
                WHERE status = :status
                ORDER BY id
                """)
            .bind("status", status)
            .map((row, metadata) -> new OrderView(
                ((Number) Objects.requireNonNull(row.get("id"))).longValue(),
                row.get("customer_name", String.class),
                row.get("total_amount", BigDecimal.class)))
            .all();
    }
}
```

**Giải thích:** `Flux<OrderView>` mô tả công việc; truy vấn thường bắt đầu khi có **subscription**, không nhất thiết tại lúc gọi `findByStatus`. `all()` phát lần lượt các row theo publisher, còn mức độ streaming và backpressure thực tế phụ thuộc driver, truy vấn và cách dùng toán tử. Không gọi `block()` ở handler/reactive service, cũng không gọi `subscribe()` thủ công để “kích hoạt” side effect trong một transaction.

Một cập nhật reactive, được gọi qua Spring proxy và có `R2dbcTransactionManager` phù hợp, có thể viết:

```java
package example.data;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderService {
    private final DatabaseClient db;

    public ReactiveOrderService(DatabaseClient db) {
        this.db = db;
    }

    @Transactional
    public Mono<Void> markPaid(long id) {
        return db.sql("""
                UPDATE orders
                SET status = 'PAID', version = version + 1
                WHERE id = :id AND status = 'NEW'
                """)
            .bind("id", id)
            .fetch()
            .rowsUpdated()
            .flatMap(count -> count == 1
                ? Mono.<Void>empty()
                : Mono.error(new IllegalStateException(
                    "Order not found or not NEW")));
    }
}
```

Ở đây transaction reactive gắn với **Reactor context** của publisher và diễn ra khi publisher được subscribe, không dựa vào `ThreadLocal` của transaction imperative. Nếu ứng dụng có nhiều transaction manager, chỉ rõ manager cho method để tránh chọn nhầm. Không nên chia nhỏ transaction bằng `subscribe()` nội bộ, `block()` hoặc chuyển qua JDBC trong chuỗi reactive và mặc định nghĩ rằng chúng dùng chung transaction.

Spring Data R2DBC repository/`R2dbcEntityTemplate` phù hợp với CRUD và mapping đơn giản, nhưng không cung cấp lazy-loading graph, managed-entity dirty checking và cascade semantics giống JPA. Nếu business logic đòi hỏi các khả năng đó, cần tự triển khai aggregate và các lệnh liên quan hoặc chọn JPA.

## 7. Transaction, tính nhất quán và xử lý đồng thời

### Với JDBC

`@Transactional` thông qua transaction manager imperative liên kết JDBC connection với luồng thực thi của transaction. Nếu thao tác nhiều bảng phải cùng thành công/thất bại, đặt transaction ở tầng service:

```java
@Transactional
public void payOrder(long orderId) {
    // UPDATE orders WHERE status = 'NEW'
    // INSERT payment_audit ...
    // cùng một JDBC transaction manager/DataSource
}
```

Đây là **mã minh họa cấu trúc**, không phải method độc lập có thể biên dịch (các lệnh trong comment cần được hiện thực).

### Với JPA

Persistence context gắn với transaction; `@Version` hỗ trợ optimistic locking. Khi update đồng thời, exception có thể xuất hiện tại flush/commit, kể cả sau dòng `order.markPaid()`. Không bắt optimistic locking rồi retry vô hạn: đánh giá idempotency, version mới và ý nghĩa nghiệp vụ.

### Với R2DBC

Reactive transaction manager gắn connection vào Reactor context. Để nhiều thao tác nằm trong cùng transaction, **compose chúng trong một publisher**:
- `then`, `flatMap`/`concatMap` hoặc `TransactionalOperator` để ghép bước phụ thuộc.
- Propagate error để rollback theo chính sách; “nuốt lỗi” bằng `onErrorResume` có thể khiến transaction commit nếu kết quả được xem là thành công.
- Phân biệt transaction trong một database với giao dịch xuyên hệ thống (DB + broker/email/REST). Gửi sự kiện sau commit hoặc dùng **transactional outbox** khi cần tránh ghi DB thành công nhưng publish event thất bại.

**Không có một ACID transaction tự động bao trùm cùng lúc JDBC/JPA và R2DBC**, dù chúng trỏ cùng database. Chọn một đường truy cập cho mỗi ranh giới transaction; nếu phối hợp nhiều công nghệ, thiết kế consistency rõ ràng.

### Isolation, lock và idempotency

Cả ba stack đều chịu quy tắc của database:
- `READ COMMITTED`/`REPEATABLE READ`/`SERIALIZABLE` có ý nghĩa và chi phí khác nhau tùy database.
- Cần kiểm soát lost update, non-repeatable read, phantom, deadlock và lock wait theo workload.
- Dùng điều kiện trạng thái/version trong `UPDATE`, unique constraint hoặc idempotency key cho lệnh có thể retry.
- Không giữ transaction lâu trong lúc gọi mạng bên ngoài hoặc chờ người dùng.
- Retry chỉ cho lỗi có thể retry và ở ranh giới an toàn; đặc biệt phải bảo đảm không lặp side effect.

## 8. Truy cập reactive chỉ có ích khi cả chuỗi phù hợp

Một pipeline muốn khai thác R2DBC nên gần với:

```text
WebFlux request → reactive auth/client → reactive service
               → R2DBC driver → database → Flux/Mono response
```

Nếu phần lớn lời gọi vẫn dùng JDBC/JPA, filesystem blocking, HTTP client blocking hoặc xử lý CPU nặng trên event loop, đổi một repository sang `Flux` không tạo ra đường đi không chặn. Dùng `Schedulers.boundedElastic()` để cô lập API blocking khi bắt buộc là giải pháp tích hợp tạm/biên; nó sử dụng luồng để chạy blocking work, không biến driver thành non-blocking.

**Backpressure** là cách downstream yêu cầu số phần tử được phát trong pipeline Reactor, không bảo đảm database hủy/giảm toàn bộ workload tương ứng. Muốn trả danh sách lớn, vẫn cần phân trang/keyset pagination, giới hạn kết quả, timeout và hiểu hành vi fetch của driver. Reactive thường có lợi khi nhiều kết nối yêu cầu đồng thời phải chờ I/O; nó không thay thế index, SQL plan và kích thước connection pool.

## 9. Chi phí truy vấn quyết định nhiều hơn tên framework

Trước khi chuyển stack, đo các yếu tố:
- SQL thực tế chạy gì, số query/request bao nhiêu, có N+1 không.
- `EXPLAIN (ANALYZE, BUFFERS)` của truy vấn tiêu biểu (trên môi trường an toàn, hiểu rằng `ANALYZE` thực thi query).
- Index, join order, selectivity, sort, row count, payload, pagination và độ trễ mạng.
- Database CPU/I/O/locks, connection pool active/idle/wait, timeout và transaction duration.
- Throughput, latency p50/p95/p99, memory/GC, threads/event loops dưới cùng tải và cùng dataset.

**Quy tắc thực hành:** tối ưu query, index, số round-trip và payload trước; chọn ORM/JDBC/R2DBC theo yêu cầu kỹ thuật và tính bảo trì. Một `SELECT *` lấy 10.000 row vẫn nặng dù API là `Flux`; một ORM query đúng projection và fetch plan hoàn toàn có thể phù hợp production.

## 10. Bốn tình huống chọn điển hình

**A. Báo cáo doanh thu/đối soát:** cần `JOIN` nhiều bảng, `GROUP BY`, window function/CTE, projection DTO, yêu cầu DBA phân tích SQL. Ưu tiên **JdbcClient/JdbcTemplate** hoặc SQL DSL nếu thích hợp. JPA native query vẫn có thể dùng, nhưng đừng ép một graph entity cho kết quả tổng hợp.

**B. Quản lý vòng đời đơn hàng:** đơn có nhiều dòng hàng, trạng thái, invariant, cascade phù hợp, optimistic locking và transaction theo aggregate. Ưu tiên **JPA/Hibernate** nếu quan hệ/mô hình thực sự hưởng lợi; kiểm tra fetch để tránh N+1. Với aggregate nhỏ, SQL/Spring Data JDBC vẫn có thể đơn giản hơn.

**C. Gateway WebFlux có rất nhiều request đồng thời chờ database:** đội ngũ đã dùng Reactor, driver PostgreSQL R2DBC đáp ứng tính năng, và load test cho thấy thread/pool pressure. Thử **R2DBC**; đo throughput/latency và giới hạn connection. Không chọn chỉ vì endpoint trả `Mono`.

**D. CRUD nội bộ ít tải, đội ngũ đã quen MVC:** ưu tiên phương án imperative dễ bảo trì nhất, thường **JPA** nếu domain entity rõ hoặc **JdbcClient** nếu bảng đơn giản/truy vấn đặc thù. Reactive làm tăng cách suy nghĩ và debug mà có thể không đem lại lợi ích.

Trong ứng dụng lớn có thể phối hợp **JPA cho command/domain write** và **SQL tường minh cho read model/báo cáo**. Đây là lựa chọn ở cấp use case, không nhất thiết một framework cho toàn bộ module. Nhưng mỗi thao tác cần ranh giới transaction/data consistency rõ.

## 11. Thiết kế kiểm thử và kiểm chứng lựa chọn

### Kiểm thử tính đúng

- Dùng PostgreSQL thật trong Testcontainers khi dựa vào cú pháp SQL, lock, isolation, enum, index, behavior của driver; H2 không luôn tái hiện PostgreSQL.
- JDBC: kiểm tra mapper, tên cột, tham số bind, số row ảnh hưởng, rollback khi lỗi.
- JPA: kiểm tra entity mapping, cascade, lazy/fetch query count, flush, optimistic locking, rollback và N+1. `@DataJpaTest` là lựa chọn slice test phù hợp nếu cấu hình cần thiết được nạp.
- R2DBC: kiểm tra kết quả `Mono`/`Flux` và tín hiệu error/complete bằng `StepVerifier`, subscription, transaction rollback, pool/driver behavior. `@DataR2dbcTest` hỗ trợ slice test với các thành phần liên quan.
- Concurrency: chạy hai yêu cầu cùng cập nhật đơn `NEW` để xác minh chỉ một thành công; đừng chỉ test tuần tự.

### Load test công bằng

1. Dùng cùng PostgreSQL version, schema, dữ liệu, index và logic nghiệp vụ.
2. Warm up tương đương; tách latency khởi tạo connection, JIT và cache khỏi đo ổn định.
3. Đặt connection pool/giới hạn đồng thời có chủ đích; không so sánh hai cấu hình mặc định bất cân xứng.
4. Chạy nhiều mức tải, gồm tải vượt năng lực để thấy queue, timeout và degraded behavior.
5. Ghi p95/p99, throughput, lỗi, CPU/heap, số connection và kế hoạch SQL. Kiểm tra cả tính đúng và eventual resource cleanup.
6. Chọn phương án đáp ứng SLA, dễ triển khai/quan sát và chi phí vận hành hợp lý; không chỉ nhìn một con số trung bình.

Một benchmark nhỏ trên máy phát triển không chứng minh R2DBC hay ORM luôn nhanh/chậm hơn cho production.

## 12. Bảo mật và tính bền vững

- **Bind tham số** cho giá trị `WHERE`/`INSERT`/`UPDATE`. Không nối trực tiếp input thành chuỗi SQL. Tên bảng, cột và `ORDER BY` identifier không thể bind như giá trị: chỉ chọn từ allowlist đã định nghĩa.
- Dùng DB user quyền tối thiểu; không cấp quyền quản trị cho ứng dụng.
- Áp dụng schema migration bằng Flyway/Liquibase có quản lý phiên bản; R2DBC application có thể cần kết nối JDBC riêng cho migration, nhưng migration và runtime query không tự chia sẻ transaction.
- Chọn timeout rõ ràng cho connection, query, transaction; phân biệt timeout ứng dụng với query cancellation thực tế ở driver.
- Ghi log SQL/metrics vừa đủ để chẩn đoán; không log password, token, dữ liệu nhạy cảm hay nguyên văn các tham số chứa thông tin riêng tư.
- Kiểm tra transaction manager nào đang dùng khi có nhiều `DataSource`/`ConnectionFactory`; đặt tên bean hoặc qualifier rõ ràng thay vì dựa vào suy đoán.

## 13. Sai lầm phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Chọn JPA vì “không phải học SQL” | N+1, query khó giải thích, tải entity không cần thiết | Đọc SQL log/plan, dùng projection/fetch plan và hiểu transaction |
| Chọn JDBC vì “SQL thủ công luôn nhanh hơn” | Mapping và transaction code lặp, query vẫn có thể kém | So sánh theo use case; dùng `JdbcClient` và tái sử dụng mapping rõ ràng |
| Trả `Mono` từ một lời gọi JDBC và gọi đó là reactive database | Blocking vẫn chiếm luồng | Dùng driver R2DBC thật hoặc giữ contract imperative |
| Gọi `block()` trong reactive handler/event loop | Tắc event loop, giảm khả năng phục vụ | Compose bằng `flatMap`/`map`/`then`; xử lý blocking ở biên được kiểm soát |
| Gọi `subscribe()` thủ công trong service transaction | Side effect tách khỏi lifecycle/error/transaction của request | Trả publisher để framework/subscriber cuối cùng quản lý |
| Giả định JDBC và R2DBC cùng database là cùng transaction | Ghi một phía thành công, phía kia thất bại | Tách ranh giới, dùng outbox/compensation khi phù hợp |
| Trả toàn bộ entity graph cho API danh sách | Truy vấn và serialization bùng nổ | Projection/DTO, pagination, tránh lazy access ngoài transaction |
| Chỉ đo latency trung bình | Bỏ qua pool starvation, tail latency và error | Đo p95/p99, throughput, pool và database metrics |
| Bỏ qua khóa, isolation, retry/idempotency | Lost update, double processing | Dùng constraint/version/conditional update và kiểm thử cạnh tranh |

## 14. Checklist trước khi quyết định

- [ ] Mô tả rõ truy vấn nóng nhất, kích thước dữ liệu và yêu cầu nhất quán.
- [ ] Biết API/domain cần entity lifecycle hay chỉ DTO/projection.
- [ ] Kiểm tra luồng gọi blocking/reactive và hỗ trợ của driver DB.
- [ ] Xác định transaction manager, scope, isolation, concurrency và idempotency.
- [ ] Phân tích SQL thực thi, index, N+1 và connection pool.
- [ ] Chạy test đúng dữ liệu, bao gồm rollback/concurrent update.
- [ ] Load test cùng điều kiện, ghi SLA p95/p99, throughput, tài nguyên và lỗi.
- [ ] Đánh giá độ dễ đọc, bảo trì, debug và chuyển giao của đội ngũ.

**Kết luận kỹ thuật:** chọn **SQL tường minh** khi quyền kiểm soát truy vấn và projection là trọng tâm; chọn **JPA** khi việc quản lý vòng đời và quan hệ của entity mang lại giá trị rõ ràng; chọn **R2DBC** khi có yêu cầu và bằng chứng cho xử lý I/O không chặn end-to-end. Cả ba đều cần hiểu SQL, cơ sở dữ liệu, transaction và kiểm thử dựa trên tải thật.

## Tài liệu tham khảo chính thức

- Spring Framework JDBC Core/`JdbcClient`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework Data Access with R2DBC: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- Spring Data JPA Reference: https://docs.spring.io/spring-data/jpa/reference/
- Spring Data R2DBC Reference: https://docs.spring.io/spring-data/relational/reference/r2dbc.html
- Spring Framework Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction.html

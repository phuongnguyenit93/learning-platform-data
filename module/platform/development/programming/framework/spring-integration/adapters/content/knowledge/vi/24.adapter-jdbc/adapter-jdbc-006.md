# DataSource và JdbcTemplate trong Spring Integration JDBC

## 1. DataSource và JdbcTemplate giải quyết bài toán gì?

Trong một luồng tích hợp, dữ liệu có thể đến từ HTTP, file, SFTP, JMS, AMQP hoặc Kafka, sau đó cần tra cứu hay ghi thay đổi vào database. Ví dụ, khi nhận message `order.paid`, ứng dụng phải cập nhật trạng thái đơn, ghi sự kiện vào bảng outbox và chỉ xác nhận message nguồn khi các thao tác cần thiết đã thành công.

Spring JDBC cung cấp hai khối nền tảng:

- **`DataSource`** là hợp đồng JDBC tạo/cấp phát `Connection`. Khi triển khai bằng connection pool, nó còn quản lý việc tái sử dụng kết nối, giới hạn số kết nối đồng thời và vòng đời của các kết nối.
- **`JdbcTemplate`** là công cụ thực thi SQL trên `DataSource`. Nó lấy và giải phóng connection, tạo statement, gắn tham số, đọc `ResultSet` và chuyển `SQLException` thành ngoại lệ thuộc hệ phân cấp Spring `DataAccessException`.

Trong chương **Adapter JDBC** của module **SPRING_INTEGRATION_ADAPTERS**, những lớp này là nền móng cho JDBC inbound/outbound adapter, JDBC outbound gateway, stored procedure endpoint và các service activator truy cập database. Module nói chung kết nối hệ thống ngoài bằng inbound/outbound adapter, gateway, poller và `MessageChannel`; vì vậy ngoài cú pháp SQL, bài học còn phải làm rõ **hợp đồng message, lỗi, transaction, giới hạn tải và vòng đời connection**.

~~~mermaid
flowchart LR
    A["Kafka / HTTP / JMS / SFTP"] --> B["Spring Integration MessageChannel"]
    B --> C["JDBC adapter / gateway / service activator"]
    C --> D["JdbcTemplate / JdbcOperations"]
    D --> E["DataSource"]
    E --> F["Connection pool"]
    F --> G[("Database")]
    G --> F
    F --> E
    E --> D
    D -->|"Rows / count / exception"| C
~~~

**Phân biệt quan trọng:** `DataSource` không phải một JDBC connection duy nhất; `JdbcTemplate` không phải một pool. `JdbcTemplate` dùng `DataSource` đã được cấu hình, còn `MessageChannel` và các endpoint quyết định khi nào một thao tác JDBC được gọi, có reply hay không và transaction chạy ở thread nào.

## 2. Sơ đồ trách nhiệm từ message đến SQL

| Thành phần | Trách nhiệm | Điều không tự đảm bảo |
|---|---|---|
| `MessageChannel` | Chuyển Spring Integration message tới handler | Database đã commit khi `send()` trả về |
| JDBC inbound adapter | Poll `SELECT` và tạo message từ rows | Từng row tự thành từng message; không trùng khi nhiều replicas |
| JDBC outbound adapter | Thực hiện DML từ message, không phát reply nghiệp vụ | Trả update count cho downstream |
| JDBC outbound gateway | Thực hiện SQL và trả rows/count/keys theo cấu hình | Transaction bên ngoài đã commit |
| `DataSource` | Cấp `Connection` theo cấu hình | SQL đúng hoặc tự retry message |
| `JdbcTemplate` | Thực thi SQL, quản lý JDBC resources, dịch exception | Logic nghiệp vụ, event ordering, idempotency |
| `PlatformTransactionManager` | Quản lý commit/rollback trong phạm vi resource | Atomic transaction xuyên Kafka/JMS/HTTP mặc định |
| `DataSource` pool (ví dụ HikariCP) | Giới hạn/tái sử dụng physical connections | Rate limit nghiệp vụ hoặc backpressure xuyên broker |

Ví dụ một message có thể đi qua:

~~~text
Message<OrderPaid>
  -> DirectChannel
  -> ServiceActivator
  -> OrderJdbcRepository (JdbcTemplate)
  -> DataSource / HikariCP
  -> PreparedStatement UPDATE ...
  -> database transaction
  -> kết quả hoặc exception
~~~

Khi cần một thành phần một chiều, service activator có thể được thay bằng `JdbcMessageHandler`. Khi cần reply, chọn `JdbcOutboundGateway` hoặc một service method trả kết quả. **Chọn endpoint theo hợp đồng message**, không chỉ theo việc dùng JDBC.

## 3. Chuẩn bị Spring Boot, Spring Integration JDBC và H2

Ví dụ dùng Java 17+, Spring Boot và một database H2 để thực hành mà không cần cài một server riêng. Nên sử dụng dependency management của Spring Boot để Spring Framework, Spring Integration, HikariCP và JDBC driver tương thích.

~~~groovy
// build.gradle - phần dependencies
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.integration:spring-integration-jdbc'

    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-jdbc` thường đưa `JdbcTemplate`, transaction support và HikariCP vào ứng dụng; `spring-integration-jdbc` cung cấp các JDBC adapters/gateways, message store và stored procedure support. H2 chỉ là database dùng cho học tập; khi triển khai PostgreSQL, SQL Server, MySQL hoặc Oracle, thay bằng driver và SQL dialect tương ứng.

~~~yaml
# application.yml - H2 demo
spring:
  datasource:
    url: "jdbc:h2:mem:integration_orders;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
    hikari:
      pool-name: integration-order-pool
      maximum-pool-size: 10
      minimum-idle: 2
      connection-timeout: 3000
      max-lifetime: 1800000
  sql:
    init:
      mode: always
~~~

Các giá trị Hikari ở đây là **minh họa**, không phải cấu hình tối ưu cho mọi ứng dụng. `connection-timeout`/`max-lifetime` của Hikari tính bằng **mili giây**. Với embedded database, `DB_CLOSE_DELAY=-1` giữ database trong JVM đến khi đóng; dữ liệu vẫn không bền vững qua restart quy trình.

### 3.1. Tạo schema

Đặt nội dung dưới đây trong `src/main/resources/schema.sql` của **ứng dụng thực hành**; đây chỉ là một ví dụ để hiểu nội dung bài học, không phải yêu cầu tạo file ngoài Markdown đang được giao.

~~~sql
CREATE TABLE order_projection (
    order_id       VARCHAR(64) PRIMARY KEY,
    status         VARCHAR(32) NOT NULL,
    total_amount   DECIMAL(18, 2) NOT NULL,
    version        INTEGER NOT NULL DEFAULT 0,
    updated_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE outbox_event (
    outbox_id      BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_id       VARCHAR(64) NOT NULL UNIQUE,
    aggregate_id   VARCHAR(64) NOT NULL,
    event_type     VARCHAR(64) NOT NULL,
    published      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO order_projection(order_id, status, total_amount, version)
VALUES ('ORD-1001', 'RECEIVED', 125000.00, 0),
       ('ORD-1002', 'RECEIVED', 75000.00, 0),
       ('ORD-1003', 'PAID', 30000.00, 1);
~~~

H2 và một số database hỗ trợ câu `INSERT` nhiều rows như ví dụ; vẫn phải kiểm tra SQL dialect khi chuyển production. Với dự án thực tế, ưu tiên migration Flyway/Liquibase thay vì tạo schema tự động mỗi khi ứng dụng chạy.

## 4. Spring Boot tạo DataSource và JdbcTemplate như thế nào?

Khi có JDBC starter, một driver phù hợp và các thuộc tính `spring.datasource.*`, Spring Boot thường **tự cấu hình**:

1. Một `DataSource`, ưu tiên HikariCP nếu có trên classpath.
2. Một `JdbcTemplate` dùng `DataSource` tương ứng.
3. Một `NamedParameterJdbcTemplate` để dùng `:namedParameter`.
4. JDBC transaction infrastructure phù hợp khi điều kiện auto-configuration được đáp ứng.

Vì vậy, trong ứng dụng đơn giản, chỉ cần **inject các bean có sẵn**:

~~~java
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class DatabaseAccessSummary {

    private final DataSource dataSource;
    private final JdbcTemplate jdbcTemplate;
    private final NamedParameterJdbcTemplate namedJdbc;

    public DatabaseAccessSummary(
            DataSource dataSource,
            JdbcTemplate jdbcTemplate,
            NamedParameterJdbcTemplate namedJdbc) {
        this.dataSource = dataSource;
        this.jdbcTemplate = jdbcTemplate;
        this.namedJdbc = namedJdbc;
    }
}
~~~

Không tạo một `new HikariDataSource()` trong mỗi handler hoặc tạo `JdbcTemplate` mới mỗi message. Pool cần được **dùng chung** giữa những bước JDBC phục vụ cùng database. `JdbcTemplate` giữ reference đến `DataSource` và được thiết kế để nhiều DAO dùng chung sau khi cấu hình hoàn tất.

### 4.1. Tự định nghĩa DataSource khi nào?

Tự tạo `@Bean DataSource` thường chỉ cần khi:

- Ứng dụng có nhiều database/tenant với các pool riêng.
- Cần tùy biến TLS, credentials rotation hoặc failover ngoài khả năng auto-configuration thông thường.
- Chạy trong application server dùng JNDI datasource.
- Có cấu hình hạ tầng bắt buộc phải kiểm soát chính xác datasource bean.

**Thận trọng:** tự định nghĩa `DataSource` bean có thể khiến một phần DataSource auto-configuration của Boot không chạy nữa. Nếu có nhiều nguồn, nên định nghĩa `@Primary` hoặc `@Qualifier` rõ, đồng thời xác định transaction manager nào gắn với database nào.

## 5. Vòng đời connection: acquire, execute, release

`DataSource` là **factory**, còn `Connection` là tài nguyên JDBC cần trả về pool khi xong. Một lượt `JdbcTemplate.query(...)` điển hình:

~~~mermaid
sequenceDiagram
    participant Handler as JDBC handler
    participant Template as JdbcTemplate
    participant Source as DataSource / pool
    participant DB as Database
    Handler->>Template: query(sql, mapper, args)
    Template->>Source: Get Connection
    Source-->>Template: Pooled Connection
    Template->>DB: PreparedStatement + executeQuery
    DB-->>Template: ResultSet
    Template->>Template: RowMapper / ResultSet extraction
    Template->>Source: Release Connection
    Template-->>Handler: List<T> hoặc exception
~~~

`JdbcTemplate` quản lý việc đóng `ResultSet`/`Statement` và giải phóng connection theo quy tắc Spring JDBC. Nếu đang có transaction gắn với thread, connection **có thể được giữ đến khi transaction hoàn tất**, thay vì trả ngay về pool sau một câu query.

**Không lưu một `Connection` vào field của service để dùng xuyên messages.** Connection/JDBC statement không phải một tài nguyên được thiết kế để chia sẻ vô hạn giữa nhiều threads. Khi một connection bị rò rỉ, số slot còn lại trong pool giảm và các messages sau có thể bị timeout khi acquire.

### 5.1. HikariCP là pool, không phải database

| Thông số Hikari | Ý nghĩa | Hiểu nhầm cần tránh |
|---|---|---|
| `maximum-pool-size` | Số connection tối đa mà pool có thể quản lý tại một thời điểm | Không phải số SQL statements/giây |
| `minimum-idle` | Mục tiêu số kết nối idle duy trì | Không phải pool size bắt buộc cố định trong mọi hoàn cảnh |
| `connection-timeout` | Thời gian tối đa chờ lấy connection trước khi lỗi | Không phải SQL query timeout |
| `idle-timeout` | Tuổi idle để connection đủ điều kiện bị loại theo chính sách pool | Không cắt ngay query đang chạy |
| `max-lifetime` | Tuổi tối đa connection trước khi đủ điều kiện thay mới | Connection đang dùng thường không bị đóng giữa query chỉ vì hết tuổi |
| `pool-name` | Tên nhận diện logs/metrics | Không ảnh hưởng logic message delivery |

Một workload có 200 messages/giây không nhất thiết cần 200 connections. Concurrency cần thiết phụ thuộc thời gian giữ connection, SQL throughput, giới hạn DB server, khóa và transaction. Nếu database đang chịu lock contention, **tăng pool vô hạn** thường làm tình hình xấu hơn.

## 6. JdbcTemplate thực thi SQL như thế nào?

`JdbcTemplate` cung cấp các nhóm API quan trọng:

| Nhóm API | Công dụng | Kiểu trả về thường gặp |
|---|---|---|
| `update(sql, args...)` | INSERT/UPDATE/DELETE | `int` số rows affected |
| `query(sql, RowMapper, args...)` | SELECT nhiều rows | `List<T>` |
| `queryForObject(sql, RowMapper, args...)` | SELECT kỳ vọng đúng một row | `T` hoặc lỗi nếu số rows không đúng |
| `queryForObject(sql, Class<T>, args...)` | Đọc một giá trị scalar | `T` hoặc lỗi nếu cardinality sai |
| `batchUpdate(...)` | Thực thi nhiều updates cùng loại | `int[]`/các biến thể kết quả batch |
| `execute(...)` | Thao tác JDBC tùy biến | Theo callback |
| `call(...)`, `SimpleJdbcCall` | CallableStatement/stored procedure | Theo OUT params/result sets |

Điểm chung: **JDBC vẫn là blocking I/O**. `JdbcTemplate` giúp quản lý resource, SQL và exception, chứ **không trả một `Mono`/`Flux` non-blocking** như R2DBC. Nếu xử lý WebFlux hoặc reactive chain, phải chủ động tạo ranh giới thread để không chặn event loop.

### 6.1. Tạo model và RowMapper

~~~java
package com.example.orders;

import java.math.BigDecimal;

public record OrderRecord(
    String orderId,
    String status,
    BigDecimal totalAmount,
    int version) {
}
~~~

`RowMapper<T>` xác định cách map **một** hàng JDBC thành Java object:

~~~java
import org.springframework.jdbc.core.RowMapper;

RowMapper<OrderRecord> orderRowMapper = (rs, rowNum) ->
    new OrderRecord(
        rs.getString("order_id"),
        rs.getString("status"),
        rs.getBigDecimal("total_amount"),
        rs.getInt("version"));
~~~

`ResultSet.getBigDecimal` phù hợp giá trị tiền hơn `double`; với những cột numeric có thể NULL, nên dùng wrapper hoặc `rs.wasNull()` để không vô tình nhận giá trị mặc định của primitive.

## 7. Ví dụ hoàn chỉnh: Repository dùng JdbcTemplate

Repository sau cho thấy cách dùng lại cùng `JdbcTemplate` để đọc/ghi bảng `order_projection`. `RowMapper` là một cấu hình bất biến và có thể tái sử dụng.

~~~java
package com.example.orders;

import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {

    private static final RowMapper<OrderRecord> ORDER_MAPPER =
        (rs, rowNum) -> new OrderRecord(
            rs.getString("order_id"),
            rs.getString("status"),
            rs.getBigDecimal("total_amount"),
            rs.getInt("version"));

    private final JdbcTemplate jdbc;

    public OrderJdbcRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public Optional<OrderRecord> findById(String orderId) {
        return jdbc.query(
            "SELECT order_id, status, total_amount, version "
          + "FROM order_projection WHERE order_id = ?",
            ORDER_MAPPER, orderId)
            .stream()
            .findFirst();
    }

    public List<OrderRecord> findByStatus(
            String status, int limit) {
        if (limit < 1 || limit > 500) {
            throw new IllegalArgumentException("limit must be 1..500");
        }
        // LIMIT là ví dụ phù hợp H2; DB khác có thể dùng FETCH/TOP.
        return jdbc.query(
            "SELECT order_id, status, total_amount, version "
          + "FROM order_projection WHERE status = ? "
          + "ORDER BY order_id LIMIT ?",
            ORDER_MAPPER, status, limit);
    }

    public int changeStatus(
            String orderId,
            String expectedStatus,
            String newStatus,
            int expectedVersion) {
        return jdbc.update(
            "UPDATE order_projection "
          + "SET status = ?, version = version + 1, "
          + "updated_at = CURRENT_TIMESTAMP "
          + "WHERE order_id = ? AND status = ? AND version = ?",
            newStatus, orderId, expectedStatus, expectedVersion);
    }

    public int countByStatus(String status) {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM order_projection WHERE status = ?",
            Integer.class, status);
        return count == null ? 0 : count;
    }
}
~~~

**Đọc kết quả:**

- `findById("ORD-1001")` trả `Optional<OrderRecord>`, không ném lỗi chỉ vì không có row. `stream().findFirst()` ở đây ổn khi predicate trên **PRIMARY KEY**, không thay thế cơ chế kiểm tra uniqueness cho một SELECT tùy ý.
- `findByStatus("RECEIVED", 100)` trả list có tối đa 100 phần tử theo SQL dialect đã chọn.
- `changeStatus(..., expectedVersion)` trả `1` nếu một bản ghi khớp, `0` nếu không tìm thấy, trạng thái/version đã thay đổi hoặc predicate không còn đúng.
- `countByStatus` dùng scalar query, không cần lấy cả bảng lên bộ nhớ rồi đếm.

**Thứ tự lưu trữ dữ liệu:** SQL `ORDER BY` cần thiết khi business logic phụ thuộc thứ tự; không mặc định database trả theo primary key nếu query không có ORDER BY.

## 8. `queryForObject`, `query` và cardinality

`JdbcTemplate.queryForObject(...)` được thiết kế cho kết quả **đúng một hàng**. Nếu SQL trả 0 hoặc nhiều hơn một hàng, Spring JDBC thường ném các subtype của `IncorrectResultSizeDataAccessException`, gồm `EmptyResultDataAccessException` cho 0 row.

~~~java
// Chỉ phù hợp khi COUNT(*) luôn có đúng một row.
int count = jdbc.queryForObject(
    "SELECT COUNT(*) FROM order_projection",
    Integer.class);

// Đọc một row theo khóa duy nhất:
OrderRecord record = jdbc.queryForObject(
    "SELECT order_id, status, total_amount, version "
  + "FROM order_projection WHERE order_id = ?",
    orderRowMapper, "ORD-1001");
~~~

Nếu “không tìm thấy” là một **kết quả hợp lệ**, hai cách có thể sử dụng:

1. `query(..., RowMapper, args).stream().findFirst()` như repository ở mục 7 (với predicate bảo đảm uniqueness).
2. Bắt riêng `EmptyResultDataAccessException` và trả `Optional.empty()`; không bắt mọi `DataAccessException` rồi trả empty, vì sẽ che lỗi kết nối và cú pháp SQL.

| SQL result | `query(...)` | `queryForObject(...)` |
|---|---|---|
| 0 hàng | List rỗng | Thường ném `EmptyResultDataAccessException` |
| 1 hàng | List có 1 phần tử | Trả đúng một object/scalar |
| Nhiều hàng | List nhiều phần tử | Thường ném `IncorrectResultSizeDataAccessException` |

**Không nhầm absence với timeout:** nếu query không có row, đó thường là kết quả domain; nếu database không kết nối được, đó là lỗi hạ tầng cần được ghi nhận và có chính sách riêng.

## 9. PreparedStatement và NamedParameterJdbcTemplate

### 9.1. Bind tham số bằng `?`

Ở `JdbcTemplate`, các tham số được bind qua JDBC `PreparedStatement`:

~~~java
int rows = jdbc.update(
    "UPDATE order_projection SET status = ? WHERE order_id = ?",
    "PAID", "ORD-1001");
~~~

`?` tương ứng các giá trị theo thứ tự từ trái sang phải. Không tự tạo SQL bằng:

~~~java
// KHÔNG LÀM: dữ liệu bên ngoài được nối thành SQL.
String unsafe =
    "SELECT * FROM order_projection WHERE order_id = '" + orderId + "'";
~~~

Với SQL injection, ngay cả một lệnh SELECT cũng có thể bị lạm dụng để đọc dữ liệu không được phép. Sử dụng bind parameters cho **giá trị**; tên bảng/tên cột/chiều sort phải lấy từ allowlist do ứng dụng kiểm soát.

### 9.2. NamedParameterJdbcTemplate cho SQL dễ đọc

~~~java
package com.example.orders;

import java.util.List;
import java.util.Map;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class NamedOrderRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public NamedOrderRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<Map<String, Object>> findByStatuses(
            List<String> statuses) {
        if (statuses == null || statuses.isEmpty()) {
            return List.of();
        }
        return jdbc.queryForList(
            "SELECT order_id, status, total_amount "
          + "FROM order_projection WHERE status IN (:statuses) "
          + "ORDER BY order_id",
            Map.of("statuses", statuses));
    }
}
~~~

`NamedParameterJdbcTemplate` chuyển `:statuses` thành số lượng placeholders tương ứng với các phần tử. Ví dụ không chạy câu `IN ()` với list rỗng vì cú pháp không được hỗ trợ nhất quán giữa các database.

**Nhớ phân biệt:** `NamedParameterJdbcTemplate` dùng tham số SQL kiểu `:statuses`; cú pháp `:payload[orderId]` trong Spring Integration JDBC adapter là **cách lấy parameter từ Spring Integration message theo property path**. Đừng mặc định mọi chuỗi có dấu `:` là SpEL; nếu cần đánh giá SpEL tùy biến, Spring Integration cung cấp `ExpressionEvaluatingSqlParameterSourceFactory`.

### 9.3. JdbcClient là lựa chọn API fluent

Spring Framework từ 6.1 có `JdbcClient` giúp viết truy vấn với cả named và positional parameters. Nó dùng hạ tầng Spring JDBC bên dưới, không phải một hệ thống kết nối/database khác.

~~~java
import org.springframework.jdbc.core.simple.JdbcClient;

int count = JdbcClient.create(dataSource)
    .sql("SELECT COUNT(*) FROM order_projection WHERE status = :status")
    .param("status", "PAID")
    .query(Integer.class)
    .single();
~~~

`JdbcTemplate` và `NamedParameterJdbcTemplate` vẫn rất hữu ích cho batch, JDBC callbacks và Spring Integration endpoints. Bài này ưu tiên JdbcTemplate vì các adapter/gateway của Spring Integration nhận `DataSource` hoặc `JdbcOperations`/template tùy API.

## 10. Batch update, generated keys và chi phí thực tế

### 10.1. Batch update không phải nhiều transaction mặc định

Thay vì gọi một SQL UPDATE trong vòng lặp hàng nghìn lần, `JdbcTemplate.batchUpdate(...)` có thể gom các câu cùng cấu trúc thành một batch JDBC:

~~~java
import java.util.List;
import org.springframework.jdbc.core.BatchPreparedStatementSetter;

record StatusChange(String orderId, String newStatus) { }

List<StatusChange> changes = List.of(
    new StatusChange("ORD-1001", "PAID"),
    new StatusChange("ORD-1002", "PAID"));

int[] counts = jdbc.batchUpdate(
    "UPDATE order_projection SET status = ? "
  + "WHERE order_id = ?",
    new BatchPreparedStatementSetter() {
        @Override
        public void setValues(
                java.sql.PreparedStatement ps, int i)
                throws java.sql.SQLException {
            StatusChange change = changes.get(i);
            ps.setString(1, change.newStatus());
            ps.setString(2, change.orderId());
        }

        @Override
        public int getBatchSize() {
            return changes.size();
        }
    });
~~~

`counts` có thể chứa số rows cho từng phần tử, hoặc giá trị đặc biệt do JDBC driver trả (như `Statement.SUCCESS_NO_INFO`). **Đừng giả định mỗi phần tử luôn bằng 1**. Nếu một phần tử lỗi, trạng thái batch phụ thuộc driver, transaction boundary và khả năng rollback; cần integration test với database thực.

Trong ứng dụng lớn, giới hạn kích thước batch và thời gian transaction. Một batch khổng lồ có thể giữ locks lâu, chiếm bộ nhớ và khiến retry khó kiểm soát.

### 10.2. Lấy generated keys bằng KeyHolder

Ví dụ lưu một event audit/outbox và lấy khóa tự sinh:

~~~java
import java.sql.PreparedStatement;
import java.util.Objects;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

KeyHolder keyHolder = new GeneratedKeyHolder();

int inserted = jdbc.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO outbox_event(event_id, aggregate_id, event_type) "
      + "VALUES (?, ?, ?)",
        new String[] {"outbox_id"});
    ps.setString(1, "evt-1001-paid");
    ps.setString(2, "ORD-1001");
    ps.setString(3, "order.paid");
    return ps;
}, keyHolder);

if (inserted != 1) {
    throw new IllegalStateException("Expected one outbox row");
}
Number generated = Objects.requireNonNull(
    keyHolder.getKey(), "No generated key returned");
long outboxId = generated.longValue();
~~~

Hỗ trợ generated keys, tên cột và kiểu number phụ thuộc JDBC driver/database. H2 chỉ minh họa; với SQL Server, Oracle hoặc PostgreSQL, cần chạy integration test đúng dialect. Generated ID **không tự khử trùng lặp event**: unique `event_id` trong schema đóng vai trò riêng.

## 11. Transaction: JDBC thực thi trong phạm vi nào?

### 11.1. Transaction-aware connection

Spring JDBC dùng `DataSourceUtils` để lấy/giải phóng connection theo ngữ cảnh Spring transaction. Khi một `@Transactional` sử dụng transaction manager JDBC phù hợp, nhiều lời gọi `JdbcTemplate` đến **cùng datasource** trong **cùng thread** có thể tham gia **một local DB transaction**.

~~~mermaid
sequenceDiagram
    participant Service as Transactional service
    participant TX as TransactionManager
    participant JDBC as JdbcTemplate
    participant DB as Database
    Service->>TX: begin transaction
    Service->>JDBC: UPDATE order_projection
    JDBC->>DB: SQL trên transactional Connection
    Service->>JDBC: INSERT outbox_event
    JDBC->>DB: SQL cùng transaction
    alt Thành công
        Service->>TX: commit
    else RuntimeException
        Service->>TX: rollback
    end
~~~

### 11.2. Ví dụ service ghi trạng thái và outbox

~~~java
package com.example.orders;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {

    private final OrderJdbcRepository orders;
    private final JdbcTemplate jdbc;

    public OrderPaymentService(
            OrderJdbcRepository orders, JdbcTemplate jdbc) {
        this.orders = orders;
        this.jdbc = jdbc;
    }

    @Transactional
    public void markPaid(
            String orderId, int expectedVersion, String eventId) {
        int changed = orders.changeStatus(
            orderId, "RECEIVED", "PAID", expectedVersion);
        if (changed != 1) {
            throw new IllegalStateException(
                "Order missing, stale or already changed: " + orderId);
        }

        jdbc.update(
            "INSERT INTO outbox_event(event_id, aggregate_id, event_type) "
          + "VALUES (?, ?, ?)",
            eventId, orderId, "order.paid");
    }
}
~~~

Nếu việc insert `outbox_event` ném `DataAccessException` và exception truyền ra khỏi method, Spring transaction mặc định thường rollback cả hai thao tác, **giả định** method được gọi qua Spring transaction proxy và các thao tác dùng cùng `DataSource`/transaction manager.

Ví dụ chưa mô tả đầy đủ cách xử lý duplicate `eventId`: khi redelivery, `changeStatus` có thể trả 0. Để có **idempotency**, phải đối chiếu event ID/phiên bản đã lưu, không tự biến mọi 0 thành “xử lý lại thành công”. Với nhiều workers, unique `event_id` và kiểm tra transaction conflict là thiết yếu.

**Không gửi event Kafka trực tiếp giữa hai thao tác JDBC rồi tuyên bố atomic.** Transactional outbox nghĩa là lưu event vào bảng trong DB transaction, sau đó một publisher riêng đọc outbox, gửi broker và cập nhật trạng thái có retry/deduplication.

### 11.3. @Transactional và các lỗi phổ biến

- `@Transactional` theo proxy mặc định chỉ can thiệp khi phương thức được gọi **qua Spring-managed proxy**; tự gọi bằng `this.markPaid(...)` từ cùng object có thể bỏ qua advice.
- `@Transactional(readOnly=true)` là hint/contract tối ưu cho đọc theo khả năng DB/driver, **không phải cơ chế phân quyền chống mọi UPDATE**.
- Mặc định Spring thường rollback trên `RuntimeException`/`Error`; với checked exception cần cấu hình `rollbackFor` hoặc quy tắc mặc định phù hợp phiên bản.
- Nếu có nhiều transaction managers, phải chỉ rõ manager đúng với datasource.
- `REQUIRES_NEW` có thể cần một connection riêng khi transaction ngoài vẫn giữ connection: phải tính pool capacity.

## 12. DirectChannel, ExecutorChannel và ranh giới transaction

Trong Spring Integration, loại channel quyết định **thread thực thi** của JDBC handler:

| Channel/nguồn | Cách thực thi JDBC | Hệ quả |
|---|---|---|
| `DirectChannel` | Cùng thread của sender | Có thể tham gia transaction JDBC của caller |
| `ExecutorChannel` | Thread executor riêng | Transaction thread-bound **không tự lan** sang executor |
| `QueueChannel` với poller | Poller lấy message ở thời điểm sau | Cần transaction boundary riêng tại poller/handler |
| JDBC inbound poller | Poller chủ động chạy `SELECT` | Có thể bọc poll operation bằng transaction |
| Kafka/JMS inbound adapter | Theo listener container/adapter | ACK/offset commit không tự đồng bộ với DB |

~~~mermaid
flowchart TB
    A["Producer @Transactional"] --> B{"MessageChannel"}
    B -->|"DirectChannel"| C["JDBC handler cùng thread / có thể cùng TX"]
    B -->|"ExecutorChannel"| D["Worker thread / TX khác"]
    B -->|"QueueChannel"| E["Poller / thời điểm khác"]
    D --> F["Cần TX rõ ràng ở consumer"]
    E --> F
~~~

**Ví dụ cần tránh:** caller gọi `send()` sang `ExecutorChannel`, nhận true rồi ACK Kafka ngay, trong khi worker JDBC chưa chạy hoặc đang lỗi. Số boolean trả về từ `send()` không phải biên nhận **database commit** trong một luồng bất đồng bộ.

Với `DirectChannel`, handler JDBC có thể tham gia transaction từ caller; nhưng ngay cả khi DML đã chạy thành công, transaction ngoài vẫn có thể rollback **sau khi handler trả về**.

## 13. Áp dụng DataSource/JdbcTemplate vào JDBC adapters và gateways

### 13.1. Java DSL cho JDBC outbound channel adapter — Spring Integration 7.x

Từ **Spring Integration 7.0**, module JDBC có factory `org.springframework.integration.jdbc.dsl.Jdbc` để cấu hình adapters/gateways bằng Java DSL. Ví dụ dưới đây nhận `Message<StatusCommand>` rồi chạy một lệnh DML **một chiều**:

~~~java
package com.example.orders;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.jdbc.dsl.Jdbc;

@Configuration
@EnableIntegration
public class JdbcOutboundFlow {

    public record StatusCommand(
        String orderId, String status, int expectedVersion) { }

    @Bean
    public IntegrationFlow storeStatuses(DataSource dataSource) {
        return IntegrationFlow.from("statusWriteRequests")
            .handle(Jdbc.outboundAdapter(dataSource,
                    "UPDATE order_projection "
                  + "SET status = ?, version = version + 1 "
                  + "WHERE order_id = ? AND version = ?")
                .preparedStatementSetter((ps, message) -> {
                    StatusCommand command =
                        (StatusCommand) message.getPayload();
                    ps.setString(1, command.status());
                    ps.setString(2, command.orderId());
                    ps.setInt(3, command.expectedVersion());
                }))
            .get();
    }
}
~~~

`Jdbc.outboundAdapter(dataSource, sql)` sử dụng `DataSource` được inject từ Spring Boot hoặc bean do ứng dụng định nghĩa. Endpoint sẽ lấy connection qua Spring JDBC; bạn **không cần mở/đóng Connection thủ công** trong từng handler.

Vì là **outbound channel adapter**, đoạn code này **không phát reply update count** cho downstream. Nếu nghiệp vụ cần biết `UPDATED=0` hay `UPDATED=1` để route message, dùng **JDBC outbound gateway** hoặc service activator có `JdbcTemplate.update(...)` trả kết quả.

### 13.2. Dùng JdbcOperations/JdbcTemplate thay DataSource

Nhiều Spring Integration JDBC components nhận **`DataSource` hoặc `JdbcOperations`/`JdbcTemplate`** qua constructor/factory tùy version. Hai cách này không tạo ra hai database khác nhau nếu chúng dùng cùng `DataSource`:

~~~java
// Ý tưởng về dependency injection:
// JdbcTemplate template = bean từ Boot, sử dụng bean DataSource.
// JDBC endpoint có thể nhận DataSource hoặc JdbcOperations
// theo overload tương ứng của phiên bản Spring Integration đang dùng.
~~~

Lợi ích của inject `JdbcTemplate` là có thể dùng chung một số cấu hình template (ví dụ query timeout/SQL exception translator) nếu endpoint thực sự nhận template đó. **Đừng giả định mọi endpoint đều tự kế thừa mọi custom setting của một JdbcTemplate bean riêng** khi bạn lại truyền trực tiếp `DataSource` để nó tạo template khác.

### 13.3. Spring Integration 6.x: dựng JdbcMessageHandler

Java DSL factory `Jdbc.outboundAdapter(...)` thuộc **7.x**. Với Spring Integration **6.x**, có thể dựng handler trực tiếp:

~~~java
package com.example.orders;

import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.jdbc.JdbcMessageHandler;
import org.springframework.messaging.MessageHandler;

@Configuration
public class LegacyJdbcWriteConfiguration {

    @Bean
    @ServiceActivator(inputChannel = "legacyStatusWriteRequests")
    public MessageHandler legacyJdbcWriter(DataSource dataSource) {
        JdbcMessageHandler handler = new JdbcMessageHandler(
            dataSource,
            "UPDATE order_projection SET status = ? WHERE order_id = ?");
        handler.setPreparedStatementSetter((ps, message) -> {
            JdbcOutboundFlow.StatusCommand command =
                (JdbcOutboundFlow.StatusCommand) message.getPayload();
            ps.setString(1, command.status());
            ps.setString(2, command.orderId());
        });
        return handler;
    }
}
~~~

Đoạn 6.x giả định bạn có DTO `StatusCommand` như ví dụ trước; nếu chạy 6.x **độc lập**, chuyển DTO về một class/record thuộc ứng dụng 6.x, không đưa Java DSL 7.x vào classpath chỉ để lấy DTO.

Với Spring Integration **7.x**, nếu dựng `JdbcMessageHandler` trực tiếp, package handler là `org.springframework.integration.jdbc.outbound.JdbcMessageHandler`. **Đừng trộn import của 6.x và 7.x.**

## 14. JdbcTemplate trong service activator khi cần reply hoặc logic phức tạp

Nếu yêu cầu của integration flow là **“nhận status command, trả lại update count”**, một service activator trả kết quả có thể dễ hiểu hơn adapter DML một chiều:

~~~java
package com.example.orders;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class StatusCommandHandler {

    private final OrderJdbcRepository repository;

    public StatusCommandHandler(OrderJdbcRepository repository) {
        this.repository = repository;
    }

    @ServiceActivator(inputChannel = "statusCommandRequests",
                      outputChannel = "statusCommandResults")
    public UpdateResult update(JdbcOutboundFlow.StatusCommand command) {
        int affected = repository.changeStatus(
            command.orderId(),
            "RECEIVED",
            command.status(),
            command.expectedVersion());
        return new UpdateResult(command.orderId(), affected);
    }

    public record UpdateResult(String orderId, int affectedRows) { }
}
~~~

`@ServiceActivator` có thể nhận payload đã được converter/messaging framework ánh xạ theo cấu hình và trả object trở thành reply payload. Ví dụ này tạo một reply có kiểu domain `UpdateResult` thay vì phụ thuộc vào `Map{UPDATED=n}`; bạn cần bảo đảm có consumer hoặc reply context thích hợp tại `statusCommandResults`.

**Hợp đồng cần quyết định:** `affectedRows=0` có thể là không tìm thấy order, stale version hoặc event đã được xử lý. Nếu cần xác nhận chắc chắn, truy vấn bổ sung/đối soát event ID trong một **transaction nghiệp vụ**. Đừng tự diễn giải 0 thành “thành công” hoặc “lỗi hạ tầng”.

## 15. JDBC inbound adapter, poller và dữ liệu lặp

JDBC inbound channel adapter đọc `SELECT` theo lịch. Nó dùng `DataSource`/`JdbcTemplate` để lấy danh sách rows và phát message; nếu cần **một message cho mỗi row**, dùng splitter. Với database là nguồn của sự kiện, cần quy tắc đánh dấu bản ghi đã đọc.

~~~mermaid
flowchart LR
    P["Poller: fixedDelay"] --> A["JDBC inbound adapter"]
    A --> B["SELECT pending rows"]
    B --> C["Message<List<Row>>"]
    C --> D["Splitter"]
    D --> E["Message<Row>"]
    E --> F["Kafka / JMS / handler"]
~~~

Một số endpoint JDBC inbound cho phép cấu hình `SELECT` cùng `UPDATE` để đánh dấu những rows vừa poll, theo transaction của poller. Phân biệt:

| Tùy chọn | Đơn vị | Ý nghĩa |
|---|---|---|
| Poller `fixedDelay` | Thời gian | Nhịp gọi message source |
| `maxMessagesPerPoll` | Số lần `receive()` | Số lần hỏi source trong một trigger |
| JDBC inbound `maxRows` | Rows / query | Giới hạn số hàng trả từ một lượt query |
| Splitter | Số phần tử | Tách list thành các messages riêng |

`maxMessagesPerPoll(1)` **không** có nghĩa một row. Nó có thể tương ứng với một `SELECT` trả một list 100 rows, rồi splitter tạo 100 messages. Poller transaction chỉ có hiệu lực với những thao tác nằm trong scope transaction đó. Nếu gửi kết quả sang Kafka/JMS hoặc một executor bất đồng bộ, **database update/mark-read không tự atomic** với broker ACK.

Đối với hệ thống cần không mất event, cân nhắc **outbox table, atomic claim/lease, hồi phục messages chưa hoàn tất và idempotency** ở consumer. Polling thuần một bảng rồi đánh dấu `PROCESSED` trước khi publish có thể làm mất sự kiện nếu tiến trình chết giữa hai bước.

## 16. Exception translation và xử lý lỗi

Spring JDBC chuyển các `SQLException` có tính chất theo driver thành các ngoại lệ thuộc hệ `DataAccessException`. Điều này giúp code/service không phải bắt trực tiếp nhiều loại `SQLException` khác nhau.

| Ngoại lệ / tình huống | Nguyên nhân thường gặp | Phản ứng |
|---|---|---|
| `DuplicateKeyException` | Vi phạm unique/primary key | Kiểm tra trùng event hay conflict |
| `DataIntegrityViolationException` | NOT NULL, FK, check constraint... | Sửa dữ liệu/hợp đồng |
| `EmptyResultDataAccessException` | `queryForObject` kỳ vọng 1 row nhưng nhận 0 | Chuyển thành not-found theo domain |
| `IncorrectResultSizeDataAccessException` | Kết quả không đúng cardinality | Kiểm tra SQL/uniqueness |
| `BadSqlGrammarException` | SQL/column/table sai | Sửa migration/query, không retry mù quáng |
| `DataAccessResourceFailureException` | Connection/DB không sẵn sàng | Retry có giới hạn nếu transient |
| `CannotAcquireLockException` / deadlock-related exception | Lock contention/transaction serialization | Rollback rồi retry toàn transactional unit khi an toàn |
| SQL statement trả update count 0 | Không có row khớp predicate | Kết quả nghiệp vụ; không mặc nhiên là exception |

**Không bắt `DataAccessException` rồi trả “thành công mặc định”** trong payment/order pipelines. Nếu lỗi kết nối bị biến thành `Optional.empty()`, phía trên có thể hiểu nhầm rằng database hoạt động nhưng không có đơn hàng.

### 16.1. Retry đúng đơn vị

Với deadlock, retry một câu SQL đơn lẻ trong cùng một transaction đã rollback-only có thể không giải quyết được. Thường cần retry **toàn bộ transaction** từ boundary nghiệp vụ sau rollback, có exponential backoff/jitter và giới hạn attempts.

Khi connection rớt sau khi DB có thể đã commit, outcome có thể ở trạng thái **không chắc chắn** đối với caller; idempotency key và reconciliation quan trọng hơn retry vô hạn.

### 16.2. Error channel của Spring Integration

Tùy endpoint và loại channel, một `DataAccessException` có thể truyền đồng bộ về caller, được bọc thành `MessagingException` hoặc được chuyển qua `ErrorMessage`/`errorChannel` ở consumer/poller thread.

- `DirectChannel`: caller có thể nhận lỗi ngay trong `send()`.
- `ExecutorChannel`/poller: lỗi có thể xuất hiện về sau, cần error handler/error channel phù hợp.
- Kafka/JMS inbound: quyết định retry, DLQ và ACK/offset commit theo semantics của adapter và broker.

Không mặc định mọi lỗi JDBC trở thành một **reply message** có payload lỗi; SQL gateway bình thường trả kết quả thành công, còn xử lý error đi theo đường riêng.

## 17. JdbcTemplate là blocking I/O: ranh giới với WebFlux

Một ứng dụng có WebFlux inbound gateway có thể cần JDBC để tra cứu. **Dùng `JdbcTemplate` trực tiếp trên Reactor Netty event loop sẽ chặn thread**, gây ảnh hưởng tới các HTTP request khác.

Nếu không dùng R2DBC, hãy đưa JDBC blocking sang scheduler/worker phù hợp, với giới hạn số tác vụ đang chạy:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<OrderRecord> lookup = Mono
    .fromCallable(() -> repository.findById("ORD-1001"))
    .subscribeOn(Schedulers.boundedElastic())
    .flatMap(optional -> Mono.justOrEmpty(optional));
~~~

Trong snippet, `repository` là bean `OrderJdbcRepository` và `fromCallable` nhận `Optional<OrderRecord>`. `subscribeOn(boundedElastic())` chuyển việc gọi JDBC sang worker dùng cho blocking I/O thay vì giữ event loop bận chờ.

**Giới hạn:** boundedElastic có giới hạn riêng nhưng không tự làm JDBC non-blocking, không thay thế giới hạn Hikari pool hay bảo đảm transaction thread-bound đi theo mọi reactive signal. Nếu cần **nhiều thao tác JDBC trong cùng transaction**, hãy đặt chúng trong **một phương thức dịch vụ `@Transactional` đồng bộ**, gọi nguyên phương thức đó bên trong blocking boundary; không tách từng query ra nhiều `subscribeOn` khác nhau rồi suy rằng chúng chia sẻ connection/transaction.

Nếu workload cần database reactive end-to-end, xem xét `R2dbcEntityTemplate`/R2DBC với hợp đồng khác. Không gọi JDBC và R2DBC là cùng một stack chỉ vì đều truy cập SQL.

## 18. Nhiều DataSource và transaction manager

Với nhiều database, không nên inject một `DataSource` mơ hồ. Ví dụ ứng dụng có DB nghiệp vụ và DB audit:

~~~java
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class MultiDatabaseJdbcConfiguration {

    @Bean("ordersJdbcTemplate")
    public JdbcTemplate ordersJdbcTemplate(
            @Qualifier("ordersDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }

    @Bean("auditJdbcTemplate")
    public JdbcTemplate auditJdbcTemplate(
            @Qualifier("auditDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }
}
~~~

Ví dụ giả định **`ordersDataSource` và `auditDataSource` đã được định nghĩa và quản lý ở phần cấu hình khác**. Đây là snippet để minh họa qualifiers; không phải một ứng dụng có đủ hai pools chỉ từ đoạn code này.

Với `@Transactional(transactionManager = "ordersTransactionManager")`, chỉ những resources tham gia transaction manager tương ứng được quản lý atomic theo semantics của manager đó. **Hai DataSource dùng hai transaction managers không tự có commit nguyên tử**. Khi tích hợp nhiều DB hoặc DB + broker, cân nhắc outbox/CDC, saga hoặc một cơ chế transaction phân tán được thiết kế riêng nếu thật sự cần.

## 19. Vận hành: pool sizing, timeouts, metrics và bảo mật

### 19.1. Ba timeout không giống nhau

| Thời hạn | Tầng | Khi hết hạn |
|---|---|---|
| Hikari `connectionTimeout` | Chờ lấy connection | Pool có thể ném timeout khi không lấy được connection |
| JDBC `queryTimeout` | Thực thi statement | Driver/database có thể hủy hoặc báo lỗi statement |
| Spring `@Transactional(timeout=...)` | Transaction service | Transaction manager áp dụng timeout theo khả năng resource/infrastructure |

Một timeout ở ứng dụng **không tự bảo đảm DB chưa commit**. Với Kafka/JMS messages cần idempotency khi xử lý lại, vì lệnh database có thể đã thành công nhưng xác nhận bị mất.

Để cấu hình query timeout cho các lời gọi qua `JdbcTemplate`, có thể dùng thuộc tính Boot như `spring.jdbc.template.query-timeout` khi auto-configuration hỗ trợ, hoặc cấu hình trực tiếp template. Khi một JDBC adapter tự tạo template từ `DataSource`, phải kiểm tra xem setting đó có được kế thừa không.

### 19.2. Chỉ số nên theo dõi

1. **Hikari pool:** active, idle, pending/waiting connections, acquire timeouts, connection creation.
2. **Database:** p50/p95/p99 query latency, slow SQL, locks, deadlocks, connection errors, statement timeouts.
3. **IntegrationFlow:** tốc độ message vào/ra, queue depth, consumer lag, failed messages, retry rate và DLQ.
4. **Transaction:** commit/rollback counts, transaction duration, outbox backlog.
5. **Nghiệp vụ:** tỷ lệ `UPDATED=0`, duplicate event IDs, record versions conflict và data freshness.

Micrometer/Actuator có thể cung cấp các metric phù hợp khi registry/instrumentation đã được bật. Không coi Hikari metrics hay SQL tracing đã tự xuất hiện chỉ vì có `spring-boot-starter-jdbc`. Tránh tags cardinality cao như mỗi `orderId` hoặc `eventId`; dùng tracing/log có giới hạn để điều tra từng giao dịch.

### 19.3. Bảo mật

- Dùng secret manager/biến môi trường thay vì hardcode DB password.
- Áp dụng account DB có quyền tối thiểu `SELECT/INSERT/UPDATE/DELETE/EXECUTE` cho các bảng/procedure thực sự cần.
- Bảo vệ TLS/truststore đúng DB vendor, không vô hiệu hóa xác minh chứng chỉ để tránh lỗi.
- Bind parameters, validate input và allowlist SQL identifiers động.
- Không ghi toàn bộ SQL parameters, token hay PII vào logs; log có kiểm soát correlation ID và loại lỗi.
- Kiểm tra tenant/authorization trước khi ghi. `tenantId` từ message header không tự chứng minh caller được phép truy cập tenant đó.

## 20. Kiểm thử DataSource, JdbcTemplate và transaction

### 20.1. Spring Boot integration test trên H2

Với schema và dữ liệu ví dụ ở mục 3:

~~~java
package com.example.orders;

import static org.junit.jupiter.api.Assertions.*;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class OrderJdbcRepositoryTest {

    @Autowired
    OrderJdbcRepository repository;

    @Autowired
    JdbcTemplate jdbc;

    @Test
    void queryAndOptimisticUpdate() {
        String id = "ORD-" + UUID.randomUUID();
        jdbc.update(
            "INSERT INTO order_projection "
          + "(order_id, status, total_amount, version) "
          + "VALUES (?, ?, ?, ?)",
            id, "RECEIVED", new java.math.BigDecimal("50000.00"), 0);

        OrderRecord before = repository.findById(id).orElseThrow();
        assertEquals("RECEIVED", before.status());

        assertEquals(1, repository.changeStatus(
            id, "RECEIVED", "PAID", 0));
        assertEquals(0, repository.changeStatus(
            id, "RECEIVED", "PAID", 0));

        OrderRecord after = repository.findById(id).orElseThrow();
        assertEquals("PAID", after.status());
        assertEquals(1, after.version());
    }
}
~~~

Test có thể xác nhận **row mapping, update count và optimistic check**. Để kiểm tra transaction rollback thực, nên gọi **một service `@Transactional` qua Spring bean proxy**, cố tình ném exception sau câu SQL đầu tiên, rồi query dữ liệu từ một transaction mới/connection độc lập. Nếu test method chính nó được đánh dấu `@Transactional` và rollback cuối test, việc thấy dữ liệu trong cùng transaction **không chứng minh đã commit**.

### 20.2. Kiểm thử với database production-compatible

H2 rất tốt cho unit/integration test cơ bản, nhưng có những khác biệt lớn về locking, generated keys, SQL dialect, isolation và kiểu dữ liệu. Với các hệ thống quan trọng, dùng Testcontainers hoặc database test đúng vendor để kiểm thử:

| Tình huống | Điều cần xác minh |
|---|---|
| Kết nối sai password, DB down | Pool timeout/connection exception đúng loại |
| 0/1/nhiều rows từ query | `query` và `queryForObject` xử lý đúng cardinality |
| UPDATE version không khớp | `affectedRows=0`, không ghi đè trạng thái |
| Duplicate key | Ném lỗi phù hợp, phân biệt duplicate và conflict |
| Transaction nhiều câu lệnh | Rollback toàn bộ khi lỗi giữa transaction |
| Batch có một item lỗi | Rollback/partial result theo DB/driver và transaction |
| Generated keys | Tên/kiểu key đúng với DB production |
| Pool hết connection | Backpressure/bounded queue và timeout phù hợp |
| ExecutorChannel thay DirectChannel | Transaction/ACK/reply semantics thay đổi |
| Kafka/JMS redelivery | Không nhân đôi outbox/business side effect |
| Poller đánh dấu đã đọc | Không mất event khi crash sau DB update trước broker publish |

## 21. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “DataSource là một JDBC Connection cố định” | Nó là interface cấp connections, thường được hỗ trợ bởi pool |
| “JdbcTemplate tự tạo một pool mới mỗi SQL” | Template **dùng lại DataSource** được inject |
| “DataSourceUtils/JdbcTemplate sẽ commit mọi thao tác ngay” | Nếu có transaction, commit theo transaction manager |
| “`send() == true` là DB đã commit” | Phụ thuộc channel/transaction boundary |
| “`maximumPoolSize=20` nghĩa 20 SQL/giây” | Đây là giới hạn connection, không phải throughput |
| “`connectionTimeout` là query timeout” | Một cái đợi pool, một cái giới hạn SQL statement |
| “SELECT không có row phải là lỗi database” | Có thể là kết quả nghiệp vụ bình thường |
| “queryForObject 0 row trả null” | Thường ném `EmptyResultDataAccessException` |
| “NamedParameterJdbcTemplate và SpEL trong Integration là giống nhau” | Named SQL bind khác với đánh giá SpEL/custom parameter factory |
| “`batchUpdate` luôn trả từng row count chính xác” | Driver có thể trả `SUCCESS_NO_INFO` và nhiều kiểu partial result |
| “@Transactional ở caller tự đi theo ExecutorChannel” | Thread-bound transaction không tự truyền sang worker |
| “JDBC trong WebFlux app đã non-blocking” | JDBC là blocking; cần ranh giới worker/R2DBC |
| “JDBC outbound adapter tự tạo reply count” | Cần gateway hoặc service activator trả kết quả |
| “Retry lỗi DB luôn an toàn” | Outcome có thể không chắc chắn; cần idempotency |
| “Tăng pool/concurrency vô hạn giải quyết lock contention” | Có thể làm database quá tải hơn |

## 22. Bài thực hành

1. Khởi tạo H2 theo mục 3, inject `DataSource`, `JdbcTemplate`, `NamedParameterJdbcTemplate` và xác nhận chúng dùng cùng nguồn dữ liệu.
2. Viết `RowMapper<OrderRecord>` cho bảng `order_projection`, so sánh kiểu dữ liệu `BigDecimal` với `double`.
3. Thực hiện `query` và `queryForObject` trong các trường hợp 0, 1 và nhiều rows; ghi nhận exception thực tế.
4. Viết tìm đơn hàng bằng `Optional<OrderRecord>`, không nuốt lỗi `DataAccessException` thành “không tìm thấy”.
5. Thực hiện UPDATE với `WHERE version = ?`, gửi hai command cùng version và xác nhận một lệnh trả 0.
6. Chuyển một query sang `NamedParameterJdbcTemplate` với `IN (:statuses)` và xử lý danh sách rỗng.
7. Dùng `batchUpdate` để cập nhật nhiều đơn; test một phần tử lỗi, số update counts và transaction rollback.
8. Tạo row trong `outbox_event`, lấy generated key bằng `KeyHolder` và kiểm tra unique `event_id`.
9. Đặt UPDATE và INSERT outbox trong một `@Transactional` service; ném exception giữa chừng và xác nhận rollback.
10. Thay input `DirectChannel` bằng `ExecutorChannel`, quan sát thread, connection và transaction boundary.
11. Xây dựng JDBC outbound adapter một chiều bằng Java DSL 7.x; thay bằng service activator khi downstream cần update count.
12. Cấu hình inbound JDBC poller, giới hạn maxRows và so sánh với maxMessagesPerPoll; thêm splitter cho list rows.
13. Chạy một WebFlux endpoint dùng `JdbcTemplate`, chuyển phần blocking sang `Schedulers.boundedElastic()` và đo tác động lên event loop.
14. Giảm Hikari pool xuống 1 rồi tạo nhiều request đồng thời; phân biệt lỗi connection acquire với SQL statement timeout.
15. Gắn Kafka/JMS source và mô phỏng crash sau DB commit trước ACK; đề xuất bảng idempotency/outbox và quy trình redelivery.
16. Tách hai DataSource để hiểu `@Qualifier`, `@Primary` và transaction manager; kiểm tra rằng hai local transactions không atomic mặc định.

**Tình huống tổng hợp:** Kafka gửi `order.paid`, một `DirectChannel` chuyển tới service cập nhật database bằng JdbcTemplate và ghi outbox. Sau khi DB commit, ứng dụng crash trước khi ACK Kafka; message được gửi lại. Hãy mô tả ranh giới transaction, event ID, optimistic version, unique constraint, cơ chế ACK, outbox publisher và lý do tăng `maximumPoolSize` không giải quyết yêu cầu “không nhân đôi tác dụng”.

## 23. Tài liệu tham khảo

- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): `DataSource` auto-configuration, HikariCP, `JdbcTemplate` và `NamedParameterJdbcTemplate`.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, query/update, batch, `RowMapper` và generated keys.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSource`, `DataSourceUtils` và transaction-aware connections.
- [Spring Framework — JDBC Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, local transaction, propagation và rollback.
- [Spring Integration — JDBC Support](https://docs.spring.io/spring-integration/reference/jdbc.html): JDBC inbound/outbound adapter, gateway, stored procedures và JDBC message store.
- [Spring Integration — JDBC Java DSL](https://docs.spring.io/spring-integration/reference/jdbc/dsl.html): `Jdbc` factory từ Spring Integration 7.0.
- [Spring Integration — JDBC Inbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/inbound-channel-adapter.html): poller, `SELECT`/`UPDATE`, `maxRows` và transaction.
- [Spring Integration — JDBC Outbound Channel Adapter](https://docs.spring.io/spring-integration/reference/jdbc/outbound-channel-adapter.html): `DataSource`/`JdbcTemplate`, parameter binding, prepared statement callback và batch.
- [Spring Integration — JDBC Outbound Gateway](https://docs.spring.io/spring-integration/reference/jdbc/outbound-gateway.html): reply rows/update count/generated keys.
- [HikariCP Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): connection pool sizing, acquire timeout và lifecycle settings.

> **Ghi nhớ:** `DataSource` quản lý **nguồn connections**, `JdbcTemplate` quản lý **thao tác JDBC và JDBC resources**, còn Spring Integration adapter/gateway quản lý **cách message kích hoạt SQL và có reply hay không**. Muốn chạy ổn định cần dùng chung pool, bind tham số an toàn, khai báo transaction đúng thread/resource, phân biệt kết quả 0 row với lỗi hạ tầng, giới hạn tải và thiết kế idempotency khi message bị gửi lại.

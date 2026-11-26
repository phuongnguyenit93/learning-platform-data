# SELECT, INSERT, UPDATE và DELETE theo khóa với CQL và CqlTemplate

Trong **Spring Data Cassandra**, `CqlTemplate` là lớp hỗ trợ thực thi **CQL trực tiếp** trên Apache Cassandra. Nó cung cấp các phương thức đọc hàng, ánh xạ kết quả, thực hiện `INSERT`, `UPDATE`, `DELETE` và chuyển ngoại lệ từ Java Driver sang hệ ngoại lệ truy cập dữ liệu của Spring. Đổi lại, lập trình viên phải tự viết câu CQL và xác định cách chuyển hàng dữ liệu thành đối tượng Java.

Bài học thuộc chương **CQL và CqlTemplate** của module **SPRING_DATA_CASSANDRA**. Mục tiêu là thực hiện bốn thao tác dữ liệu cơ bản **theo đúng primary key**, không chỉ học thuộc cú pháp. Bởi Cassandra lưu dữ liệu theo partition key và clustering columns, một `SELECT` hoặc `UPDATE` hợp lệ ở SQL quan hệ chưa chắc được Cassandra hỗ trợ hoặc có hiệu năng ổn định. Các ví dụ cũng liên hệ với entity mapping, repository, `CassandraTemplate`, consistency, paging và cách làm việc đúng với mô hình phân tán.

## 1. CqlTemplate đứng ở đâu trong hệ sinh thái Spring Data Cassandra?

| API | Đơn vị lập trình chủ yếu | Khi nào chọn? |
|---|---|---|
| `CqlTemplate` / `CqlOperations` | Chuỗi CQL, bind parameters, `RowMapper` | Cần kiểm soát rõ statement và kết quả CQL |
| `CassandraTemplate` / `CassandraOperations` | Entity, `Query`, `Criteria`, mapping metadata | Truy vấn theo khóa nhưng muốn framework ánh xạ entity |
| `CassandraRepository` | Interface CRUD và query methods | Những thao tác ổn định, đơn giản theo khóa |
| Java Driver `CqlSession` | `PreparedStatement`, `BoundStatement`, `Row` | Cần kiểm soát tùy chọn statement, paging hoặc CQL đặc biệt |

`CqlTemplate` là nền tảng CQL-level của Spring Data; nó không tương đương một ORM tự động suy ra cấu trúc khóa. Với `CqlTemplate`, thường cần tự viết `SELECT` và ánh xạ `Row`; với `CassandraTemplate`, một entity `@Table` có thể được framework ánh xạ dựa trên metadata.

~~~text
Service / DAO
    |
    +-- CqlOperations (CqlTemplate)
    |        |
    |        +-- CQL + bound parameters
    |        +-- RowMapper / ResultSetExtractor
    |
    +-- CassandraOperations (CassandraTemplate)
    |        |
    |        +-- Entity mapping + Query / Criteria
    |
    v
Java Driver / CqlSession
    |
    v
Cassandra cluster → replica theo partition key
~~~

Cả hai template đều truy cập cùng Cassandra cluster. Việc đổi từ `CassandraRepository` sang `CqlTemplate` **không** tạo index, không sửa partition key và không cho phép dùng `WHERE` tùy ý.

## 2. Thiết kế bảng theo bốn thao tác cần thực hiện

Giả sử ứng dụng quản lý đơn hàng cần:

1. `SELECT` 20 đơn hàng gần nhất của **một khách hàng trong một tháng**.
2. `INSERT` một đơn mới, có ID ổn định qua các lần retry.
3. `UPDATE` trạng thái hoặc tổng tiền của **một hàng đã xác định**.
4. `DELETE` một đơn theo đúng khóa hàng, khi quy trình nghiệp vụ cho phép.

Bảng theo truy vấn:

~~~sql
CREATE TABLE orders_by_customer_month (
    tenant_id uuid,
    customer_id uuid,
    month_bucket date,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY (
        (tenant_id, customer_id, month_bucket),
        created_at,
        order_id
    )
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

Phân tích primary key:

| Cột | Vai trò | Vì sao chọn? |
|---|---|---|
| `tenant_id` | Partition key, thành phần 1 | Cô lập đường truy vấn theo tenant |
| `customer_id` | Partition key, thành phần 2 | Giới hạn dữ liệu của khách |
| `month_bucket` | Partition key, thành phần 3 | Không để lịch sử một khách tăng vô hạn trong một partition |
| `created_at` | Clustering column 1, giảm dần | Đọc bản ghi mới nhất trước |
| `order_id` | Clustering column 2 | Phân biệt hai đơn cùng thời điểm |
| `status`, `total_amount` | Cột thường | Thuộc tính nghiệp vụ có thể cập nhật |

Với bảng này, **đủ partition key** là `(tenant_id, customer_id, month_bucket)`; **đủ primary key của một hàng** phải gồm **cả** `created_at` và `order_id`.

~~~text
Partition (tenant A, customer C, tháng 11)
   created_at DESC            order_id     status
   2026-11-25T09:30:00Z       id-003       PAID
   2026-11-25T09:10:00Z       id-002       NEW
   2026-11-24T15:00:00Z       id-001       PAID

Partition (tenant A, customer C, tháng 10)
   ... tập hàng khác ...
~~~

`id-001` chỉ là nhãn minh họa. Trong bảng thật, `order_id` là UUID. Nếu hệ thống cần **tra một đơn chỉ bằng `order_id`**, bảng này không trực tiếp đáp ứng vì `order_id` không đủ để tìm partition; phải có một bảng tra theo ID hoặc một đường truy cập khác được thiết kế phù hợp.

## 3. Chuẩn bị CqlTemplate và dữ liệu CQL

Khi Spring Boot đã cấu hình `CqlSession` bằng contact points, local datacenter, keyspace và credentials, có thể khai báo `CqlTemplate` một lần ở application context:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.data.cassandra.core.cql.CqlTemplate;

@Configuration(proxyBeanMethods = false)
public class CqlAccessConfiguration {

    @Bean
    CqlOperations orderCqlOperations(CqlSession session) {
        return new CqlTemplate(session);
    }
}
~~~

Nếu ứng dụng đã có bean `CqlOperations` phù hợp, **không tạo thêm bean cùng mục đích** mà không kiểm soát cách inject. `CqlSession` nên là bean dùng chung, không được tạo rồi đóng trong mỗi request.

Ví dụ cấu hình kết nối Spring Boot 3.x:

~~~yaml
spring:
  cassandra:
    contact-points:
      - cass-1.internal:9042
      - cass-2.internal:9042
    local-datacenter: dc1
    keyspace-name: app_data
    username: ${CASSANDRA_USERNAME}
    password: ${CASSANDRA_PASSWORD}
    schema-action: NONE
~~~

Các host, DC và keyspace là ví dụ, phải thay bằng giá trị thực của cluster. Keyspace **phải được tạo trước**; `schema-action: NONE` để ứng dụng không tự tạo/xóa bảng production. Không commit credentials thật vào repository. Nếu dùng TLS hoặc managed Cassandra, cấu hình kết nối phải tuân thủ hướng dẫn của môi trường đó.

### 3.1. Xác định RowMapper trước khi đọc

`CqlTemplate` không tự tạo entity `@Table` từ `Row` trong mọi lời gọi; thường dùng `RowMapper<T>` để chỉ rõ cột nào ánh xạ vào đối tượng Java. Một projection dành cho màn hình danh sách:

~~~java
package example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderSummary(
        UUID orderId,
        Instant createdAt,
        String status,
        BigDecimal totalAmount) {
}
~~~

`RowMapper` là functional interface, nhận `Row` và số thứ tự hàng:

~~~java
import org.springframework.data.cassandra.core.cql.RowMapper;

RowMapper<OrderSummary> orderMapper = (row, rowNum) ->
        new OrderSummary(
                row.getUuid("order_id"),
                row.getInstant("created_at"),
                row.getString("status"),
                row.getBigDecimal("total_amount"));
~~~

Kiểu `timestamp` CQL thường được giải mã thành `Instant`; `decimal` thành `BigDecimal`. Nếu nullable, getter có thể trả `null`. Cần định nghĩa chính sách kiểm tra dữ liệu thiếu và không biến `null` thành giá trị mặc định làm mất thông tin.

## 4. SELECT: đọc theo partition key và clustering columns

### 4.1. Đọc danh sách mới nhất trong một partition

CQL:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
LIMIT 20;
~~~

Phương thức trong một DAO có `CqlOperations`:

~~~java
import java.time.LocalDate;
import java.util.List;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.CqlOperations;
import org.springframework.data.cassandra.core.cql.RowMapper;

public class OrderCqlReader {
    private static final RowMapper<OrderSummary> ORDER_MAPPER =
            (row, rowNum) -> new OrderSummary(
                    row.getUuid("order_id"),
                    row.getInstant("created_at"),
                    row.getString("status"),
                    row.getBigDecimal("total_amount"));

    private final CqlOperations cql;

    public OrderCqlReader(CqlOperations cql) {
        this.cql = cql;
    }

    public List<OrderSummary> latestInMonth(
            UUID tenantId, UUID customerId, LocalDate monthBucket) {

        String statement = """
                SELECT order_id, created_at, status, total_amount
                FROM orders_by_customer_month
                WHERE tenant_id = ? AND customer_id = ?
                  AND month_bucket = ?
                LIMIT 20
                """;

        return cql.query(
                statement, ORDER_MAPPER,
                tenantId, customerId, monthBucket);
    }
}
~~~

Đoạn này sử dụng **Java text block** (Java 15+). Với phiên bản Java cũ hơn có thể nối chuỗi thông thường. Việc truyền `tenantId`, `customerId`, `monthBucket` dưới dạng đối số cho `query(String, RowMapper<T>, Object...)` tạo đường **prepared/bound** của template; không nối giá trị người dùng vào chuỗi CQL.

Cassandra định vị partition nhờ đủ ba cột khóa, rồi đọc theo `created_at DESC` và `order_id ASC`. `LIMIT 20` hạn chế số hàng trong kết quả **của truy vấn đúng khóa**, không phải một cơ chế giới hạn chi phí khi cố tình quét dữ liệu bằng `ALLOW FILTERING`.

### 4.2. Đọc chính xác một hàng

Khi biết toàn bộ primary key:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;
~~~

Trong service:

~~~java
public Optional<OrderSummary> findExact(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        Instant createdAt, UUID orderId) {

    String cql = """
            SELECT order_id, created_at, status, total_amount
            FROM orders_by_customer_month
            WHERE tenant_id = ? AND customer_id = ?
              AND month_bucket = ? AND created_at = ? AND order_id = ?
            """;

    List<OrderSummary> found = this.cql.query(
            cql, ORDER_MAPPER,
            tenantId, customerId, monthBucket, createdAt, orderId);

    return found.stream().findFirst();
}
~~~

`this.cql` và `ORDER_MAPPER` là các thành phần của lớp `OrderCqlReader` ở ví dụ trước; cần import `Optional` và `Instant`. Vì truy vấn có **đúng toàn bộ primary key**, kết quả hợp lệ có tối đa một hàng.

Có thể dùng `queryForObject(cql, mapper, args...)` nếu hợp đồng yêu cầu **đúng một hàng**. Tuy nhiên, cần nhớ rằng API dạng này có thể ném `IncorrectResultSizeDataAccessException` nếu không có hàng hoặc có số hàng khác kỳ vọng; `query(...).stream().findFirst()` diễn đạt rõ hơn tình huống không tìm thấy. Không dùng `findFirst()` để che giấu truy vấn vốn có thể trả nhiều hàng một cách bất ngờ.

### 4.3. Lọc theo khoảng thời gian

Khi `created_at` là clustering column đầu tiên, truy vấn khoảng trong **một partition** có thể dùng:

~~~sql
SELECT order_id, created_at, status
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at >= ?
  AND created_at < ?
LIMIT 100;
~~~

Ví dụ bind:

~~~java
List<OrderSummary> window = cql.query(
        """
        SELECT order_id, created_at, status, total_amount
        FROM orders_by_customer_month
        WHERE tenant_id = ? AND customer_id = ?
          AND month_bucket = ?
          AND created_at >= ? AND created_at < ?
        LIMIT 100
        """,
        ORDER_MAPPER,
        tenantId, customerId, monthBucket,
        Instant.parse("2026-11-25T09:00:00Z"),
        Instant.parse("2026-11-25T12:00:00Z"));
~~~

Khoảng nửa mở `[09:00, 12:00)` giúp tránh lấy trùng mốc khi chia thời gian thành nhiều khoảng liên tiếp. CQL `timestamp` có độ chính xác mili giây, nên thời gian đưa vào partition/clustering key phải có quy tắc chuẩn hóa thống nhất khi ghi và truy vấn.

### 4.4. Những SELECT không phù hợp với bảng này

| Truy vấn muốn thực hiện | Vấn đề | Hướng xử lý |
|---|---|---|
| Chỉ `WHERE customer_id = ?` | Thiếu `tenant_id`, `month_bucket` trong partition key | Bổ sung khóa theo API hoặc thiết kế bảng khác |
| `WHERE status = 'PAID'` toàn hệ thống | `status` là cột thường | Access table theo trạng thái, hoặc index được chứng minh phù hợp |
| `WHERE order_id = ?` | `order_id` không định vị được partition | Dùng `orders_by_id` hoặc bảng tra cứu theo ID |
| `ORDER BY total_amount DESC` | `total_amount` không phải clustering column | Bảng truy cập/xếp hạng phù hợp |
| Chỉ `WHERE tenant_id = ?` | Partition key ghép chưa đầy đủ | Không xem đây là scan hiệu quả mặc định |

**`CqlTemplate` không tự thêm `ALLOW FILTERING`.** Không nên thêm tùy chọn này chỉ để query chạy được khi bộ lọc thiếu đường khóa; việc lọc có thể duyệt lượng dữ liệu rất lớn, không đạt SLA.

## 5. INSERT: tạo một hàng bằng toàn bộ primary key

Trong Cassandra, `INSERT` bắt buộc cung cấp **đủ toàn bộ primary key** để xác định hàng. Ví dụ:

~~~sql
INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, month_bucket,
    created_at, order_id, status, total_amount
) VALUES (?, ?, ?, ?, ?, ?, ?);
~~~

Thực thi bằng `CqlTemplate`:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public boolean insertOrder(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        Instant createdAt, UUID orderId,
        String status, BigDecimal totalAmount) {

    return cql.execute(
            """
            INSERT INTO orders_by_customer_month (
                tenant_id, customer_id, month_bucket,
                created_at, order_id, status, total_amount
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            tenantId, customerId, monthBucket, createdAt, orderId,
            status, totalAmount);
}
~~~

`execute(String, Object...)` dùng prepared statement và bind giá trị. Phương thức trả `boolean` thể hiện kết quả **applied** theo ngữ nghĩa của CQL/driver, **không phải số hàng được thêm**. Với lệnh ghi vô điều kiện, việc thành công không có nghĩa trước đó chưa tồn tại hàng ở khóa ấy.

### 5.1. INSERT của Cassandra là upsert

Nếu hai `INSERT` sử dụng **cùng toàn bộ primary key**, Cassandra không thêm hai hàng phân biệt; nó ghi vào cùng vị trí hàng và hòa giải các giá trị cột theo cơ chế timestamp của Cassandra. Vì vậy:

- `INSERT` **không mặc nhiên báo lỗi trùng khóa** như một số cơ sở dữ liệu quan hệ.
- Ghi lại cùng khóa và cùng payload thường thuận lợi cho retry, nhưng phải xem xét thời điểm ghi, TTL và tác động của các mutation cạnh tranh.
- Nếu mỗi lần retry lại sinh `UUID.randomUUID()` hoặc `Instant.now()` làm một phần primary key, **khóa mới khác khóa cũ** và có thể xuất hiện hai hàng cho cùng một đơn nghiệp vụ.
- Nếu cần đảm bảo một mã nghiệp vụ chỉ được tạo một lần, phải thiết kế cơ chế uniqueness riêng; không suy ra uniqueness toàn hệ thống từ UUID hay một bảng truy cập theo khách.

Ví dụ tạo ID đúng:

~~~java
UUID orderId = UUID.randomUUID();
Instant createdAt = Instant.parse("2026-11-25T09:30:00.123Z");
LocalDate monthBucket = LocalDate.of(2026, 11, 1);

// Sinh một lần khi nhận command, lưu vào record/message nghiệp vụ.
// Nếu retry cùng command: tái sử dụng orderId, createdAt, monthBucket.
~~~

### 5.2. IF NOT EXISTS có ngữ nghĩa khác

Khi nghiệp vụ cần **chỉ thêm nếu khóa hàng chưa tồn tại**, CQL hỗ trợ lightweight transaction (LWT):

~~~sql
INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, month_bucket,
    created_at, order_id, status, total_amount
) VALUES (?, ?, ?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

Với lệnh có điều kiện, kết quả applied **false** nghĩa là điều kiện không thỏa (ví dụ hàng đã tồn tại). Trường hợp này khác với lỗi mạng, timeout hoặc exception. LWT đắt hơn thao tác thông thường và **không tự tạo giao dịch nhiều bảng**; chỉ sử dụng khi hợp đồng nghiệp vụ thực sự cần.

~~~java
boolean inserted = cql.execute(
        """
        INSERT INTO orders_by_customer_month (
            tenant_id, customer_id, month_bucket,
            created_at, order_id, status, total_amount
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        IF NOT EXISTS
        """,
        tenantId, customerId, monthBucket,
        createdAt, orderId, status, totalAmount);

if (!inserted) {
    // Khóa hàng đã tồn tại; xử lý theo hợp đồng nghiệp vụ.
}
~~~

Nếu timeout xảy ra khi thực hiện LWT, **không tự suy ra điều kiện đã thất bại hoặc thao tác chưa được áp dụng**. Cần chiến lược retry/kiểm tra idempotency phù hợp.

## 6. UPDATE: sửa cột thường, không sửa primary key

Để đổi trạng thái một đơn, cần biết **đủ khóa hàng**:

~~~sql
UPDATE orders_by_customer_month
SET status = ?
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;
~~~

`CqlTemplate`:

~~~java
public boolean updateStatus(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        Instant createdAt, UUID orderId, String status) {

    return cql.execute(
            """
            UPDATE orders_by_customer_month SET status = ?
            WHERE tenant_id = ? AND customer_id = ?
              AND month_bucket = ? AND created_at = ? AND order_id = ?
            """,
            status, tenantId, customerId, monthBucket, createdAt, orderId);
}
~~~

Thứ tự các đối số bind phải khớp **thứ tự dấu `?`** trong CQL. Trong ví dụ `UPDATE`, `status` là tham số đầu tiên, còn ở `INSERT` nó nằm sau các cột khóa. Thay đổi thứ tự có thể gây lỗi kiểu hoặc ghi sai dữ liệu hợp lệ về mặt kiểu.

### 6.1. UPDATE cũng mang tính upsert

CQL `UPDATE` vô điều kiện có thể **tạo một hàng mới** khi hàng ở primary key chưa tồn tại. Vì vậy, `boolean` trả về sau `execute` thành công **không đồng nghĩa** “đã sửa đúng một hàng có sẵn”.

Nếu cần “chỉ đổi trạng thái nếu hàng tồn tại”, có thể dùng:

~~~sql
UPDATE orders_by_customer_month
SET status = ?
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?
IF EXISTS;
~~~

`IF EXISTS` là điều kiện LWT, làm tăng chi phí. Một bước `SELECT` trước `UPDATE` thông thường **không thay thế** nó, vì giữa hai thao tác writer khác có thể thay đổi dữ liệu.

### 6.2. Điều kiện trên giá trị hiện tại: compare-and-set

Nếu nghiệp vụ chỉ cho phép `NEW → PAID`:

~~~sql
UPDATE orders_by_customer_month
SET status = 'PAID'
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?
IF status = 'NEW';
~~~

LWT so sánh trạng thái hiện có trước khi thực hiện mutation. Nếu điều kiện không đúng, thao tác **không được áp dụng**. Ứng dụng cần phân biệt `false` với exception; nếu cần biết trạng thái hiện tại, có thể xử lý kết quả có điều kiện bằng driver/CQL theo API phù hợp.

Lưu ý: điều kiện trên `status` ở đây là **điều kiện LWT khi đã biết toàn bộ primary key**, không phải một `SELECT WHERE status = ...` chạy trên toàn bộ bảng.

### 6.3. Không sửa thành phần khóa bằng UPDATE

Không thể dùng:

~~~sql
-- Ý tưởng sai: created_at là clustering column thuộc primary key.
UPDATE orders_by_customer_month
SET created_at = ?
WHERE tenant_id = ? AND customer_id = ?
  AND month_bucket = ? AND created_at = ? AND order_id = ?;
~~~

Muốn đổi `created_at`, `order_id` hoặc `month_bucket` đồng nghĩa **đổi primary key**. Phải ghi hàng ở khóa mới rồi xử lý hàng ở khóa cũ, với chính sách đồng bộ, retry và đối soát. Nếu cần thường xuyên sắp xếp theo “thời điểm cập nhật” đang thay đổi, nên cân nhắc **bảng truy cập khác** thay vì di chuyển hàng liên tục.

## 7. DELETE: xóa đúng hàng, đúng cột hoặc đúng partition

Để xóa **một hàng**:

~~~sql
DELETE FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;
~~~

`CqlTemplate`:

~~~java
public boolean deleteExact(
        UUID tenantId, UUID customerId, LocalDate monthBucket,
        Instant createdAt, UUID orderId) {

    return cql.execute(
            """
            DELETE FROM orders_by_customer_month
            WHERE tenant_id = ? AND customer_id = ?
              AND month_bucket = ? AND created_at = ? AND order_id = ?
            """,
            tenantId, customerId, monthBucket, createdAt, orderId);
}
~~~

Cassandra ghi **tombstone** để biểu diễn xóa, vì dữ liệu có thể tồn tại trên nhiều replica và SSTable. `DELETE` thành công không tương đương “đã giải phóng dung lượng vật lý ngay lập tức”.

### 7.1. Xóa một cột thường

~~~sql
DELETE total_amount FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;
~~~

Thao tác này chỉ xóa giá trị cột `total_amount` của hàng đã định danh; các cột thường khác như `status` không bị xóa vì câu lệnh đó. Ở đường đọc, `total_amount` có thể trở thành `null`, nên DTO và nghiệp vụ phải xử lý đúng tình huống thiếu dữ liệu.

### 7.2. Xóa cả partition là một thao tác khác

~~~sql
-- CẢNH BÁO: xóa tất cả các hàng của một khách trong tháng.
DELETE FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?;
~~~

Do chỉ cung cấp **partition key**, câu lệnh trên không chỉ xóa một đơn, mà đánh dấu xóa **cả partition** tương ứng. Điều này có thể phù hợp với quy trình dọn dữ liệu theo chính sách lưu giữ, nhưng đặc biệt nguy hiểm nếu API được thiết kế với mục tiêu xóa đúng một đơn.

Để tránh sai sót, nên đặt tên phương thức DAO rõ ràng như `deleteExactOrder(...)` và không dùng một hàm `deleteByCustomer(...)` mơ hồ cho cả hai ý định.

### 7.3. DELETE không mặc định đếm số hàng đã xóa

Một `execute("DELETE ...", args)` vô điều kiện thành công **không xác nhận** có hàng tồn tại trước đó. Nếu nghiệp vụ cần “xóa nếu có” với ngữ nghĩa applied, dùng LWT `DELETE ... IF EXISTS` theo khóa cụ thể, cân nhắc chi phí.

Xóa có thể để lại tombstone cho đến khi compaction và quy tắc garbage collection phù hợp; các lần xóa/cập nhật lặp lại có thể tăng chi phí đọc. Cần thận trọng với TTL, dữ liệu replica tạm không đồng nhất và chính sách retention.

## 8. Tổng hợp: cùng một khóa cho SELECT, INSERT, UPDATE, DELETE

| Câu lệnh | Điều kiện khóa tối thiểu cho tình huống bài học | Ý nghĩa |
|---|---|---|
| `SELECT` danh sách đơn | Đủ `tenant_id, customer_id, month_bucket` | Đọc nhiều hàng trong một partition |
| `SELECT` một đơn | Đủ cả năm cột primary key | Tìm chính xác một hàng |
| `INSERT` một đơn | Có giá trị của đủ năm cột khóa | Xác định hàng cần ghi |
| `UPDATE` trạng thái một đơn | `WHERE` có đủ năm cột khóa | Sửa cột thường của một hàng xác định |
| `DELETE` một đơn | `WHERE` có đủ năm cột khóa | Xóa đúng một hàng |
| `DELETE` cả tháng của khách | Chỉ đủ ba cột partition key | Xóa cả partition, **không** chỉ một đơn |

Khác biệt giữa `SELECT` danh sách và `UPDATE/DELETE` một hàng là điểm cốt lõi: **đường đọc nhiều hàng cần biết partition**, còn **mutation của một hàng cần biết toàn bộ primary key**. Không áp dụng máy móc suy nghĩ “biết customer ID là đủ” khi primary key thực tế còn tenant, tháng, thời gian và ID đơn.

### 8.1. Vì sao một orderId chưa chắc đủ?

Giả sử phía client chỉ gửi:

~~~text
PATCH /orders/{orderId}/status
~~~

Với bảng `orders_by_customer_month`, chỉ có `orderId` chưa biết partition. Một đường tra cứu chuyên biệt có thể là:

~~~sql
CREATE TABLE order_locator_by_id (
    order_id uuid PRIMARY KEY,
    tenant_id uuid,
    customer_id uuid,
    month_bucket date,
    created_at timestamp
);
~~~

Ứng dụng tra `order_locator_by_id` để tìm **đủ khóa**, sau đó cập nhật `orders_by_customer_month`. Tuy nhiên đây là **bảng projection bổ sung**: phải duy trì dữ liệu ở hai bảng, giải quyết event trễ, lỗi ghi từng phần và quyền tenant; nhiều bảng không phải một transaction ACID tự động.

Nếu `order_id` chỉ duy nhất trong mỗi tenant, hãy thiết kế locator có `(tenant_id, order_id)` làm khóa thay vì giả định ID duy nhất toàn hệ thống. Mục tiêu không phải tạo thêm bảng theo thói quen, mà là phục vụ một truy vấn sản phẩm có tần suất và SLA xác định.

## 9. Prepared statements và binding an toàn

Với `CqlTemplate`:

~~~java
cql.execute(
        "UPDATE orders_by_customer_month SET status = ? " +
        "WHERE tenant_id = ? AND customer_id = ? " +
        "AND month_bucket = ? AND created_at = ? AND order_id = ?",
        status, tenantId, customerId, monthBucket, createdAt, orderId);
~~~

Phương thức `execute(String, Object...)` chuẩn bị statement và bind các giá trị. Tương tự, `query(String, RowMapper<T>, Object...)` dùng cách thực thi có bind parameters. Cách này tránh việc ghép các giá trị người dùng trực tiếp vào chuỗi CQL.

**Không bind được tên bảng hoặc tên cột thay cho CQL identifier thông thường.** Không viết API cho phép client truyền `tableName`, `columnName`, `ORDER BY` rồi ghép thẳng vào statement. Những phần cấu trúc cần được xác định bằng một **danh sách lựa chọn tin cậy** ở ứng dụng, còn dữ liệu trong `WHERE`/`SET` phải được bind.

Khi một truy vấn được gọi rất thường xuyên và muốn kiểm soát vòng đời prepared statement hay cấu hình chi tiết, có thể dùng driver:

~~~java
import java.util.UUID;
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class OrderStatusStatement {
    private final CqlSession session;
    private final PreparedStatement update;

    public OrderStatusStatement(CqlSession session) {
        this.session = session;
        this.update = session.prepare(
                "UPDATE orders_by_customer_month SET status = ? " +
                "WHERE tenant_id = ? AND customer_id = ? " +
                "AND month_bucket = ? AND created_at = ? AND order_id = ?");
    }

    // Tạo và tái sử dụng PreparedStatement, bind ở từng lần gọi.
}
~~~

Trong ví dụ, trường `update` và `session` dành cho các phương thức tiếp theo của DAO; đoạn code nhấn mạnh **prepare một lần, bind nhiều lần**. `CqlTemplate` thích hợp khi muốn Spring quản lý execution/mapping/exception translation, còn `CqlSession` cho phép khai báo chi tiết `BoundStatement`.

## 10. Consistency, retry và TTL cho thao tác ghi/xóa

### 10.1. Mức nhất quán không được quyết định bởi cú pháp SELECT/UPDATE

`LOCAL_ONE`, `LOCAL_QUORUM` và các mức khác mô tả yêu cầu xác nhận replica dựa trên replication của keyspace và topology. Với RF=3 ở datacenter cục bộ, `LOCAL_QUORUM` thường yêu cầu hai replica đáp ứng. Nhưng:

- `LOCAL_QUORUM` không sửa được `WHERE` thiếu partition key.
- `LOCAL_QUORUM` cho một mutation không làm hai bảng projection trở thành một transaction ACID.
- Mức nhất quán nên được chọn theo SLA, khả năng chịu lỗi, yêu cầu nghiệp vụ và cấu hình cluster thực tế.

`CqlTemplate` có thể dùng cấu hình mặc định phù hợp hoặc statement do driver cung cấp với consistency rõ ràng. Khi cần điều khiển statement-specific timeout, fetch size hay idempotency flag, hãy kiểm tra API Spring Data/Java Driver của phiên bản đang sử dụng.

### 10.2. Retry phải giữ khóa và ngữ nghĩa

Sau timeout, client có thể chưa biết mutation đã được áp dụng hay chưa. Với `INSERT`/upsert cùng toàn bộ primary key và cùng dữ liệu, retry thường dễ xử lý hơn thao tác tạo ID mới mỗi lần. Nhưng retry vẫn cần xem xét:

- **Idempotency** của thao tác (ví dụ phép tăng counter hoặc append list không như set một giá trị).
- **Thứ tự cập nhật**: một thao tác đến muộn không được kéo trạng thái nghiệp vụ về giá trị cũ nếu hệ thống cần tiến trình đơn điệu.
- **LWT**: timeout có thể có kết quả chưa rõ, cần xác minh hoặc áp dụng lại theo idempotency key/quy trình.
- **Tải cluster**: retry đồng loạt có thể tạo bão request; cần backoff, giới hạn đồng thời và observability.

### 10.3. TTL trên dữ liệu cần tự hết hạn

CQL cho phép TTL với thao tác ghi:

~~~sql
INSERT INTO orders_by_customer_month (
    tenant_id, customer_id, month_bucket,
    created_at, order_id, status, total_amount
) VALUES (?, ?, ?, ?, ?, ?, ?)
USING TTL 86400;
~~~

Ví dụ 86400 giây chỉ phù hợp khi nghiệp vụ **thật sự muốn dữ liệu ghi bởi câu lệnh này hết hạn sau một ngày**. Không đặt TTL tùy tiện cho đơn hàng cần lưu trữ lâu dài. TTL áp dụng theo quy tắc từng cell/mutation của Cassandra; khi hết hạn, tombstone có thể phát sinh. Cập nhật một cột ở thời điểm khác với TTL khác có thể làm các cột có vòng đời khác nhau.

## 11. Paging và LIMIT: tránh đọc vô hạn

`CqlTemplate.query(...)` tiện để ánh xạ một tập hàng **đã có giới hạn nhỏ**. Nếu ứng dụng cần đọc rất nhiều đơn trong một partition, không dùng:

~~~java
// Không phù hợp nếu truy vấn có thể trả dữ liệu rất lớn.
List<OrderSummary> all =
        cql.query("SELECT * FROM orders_by_customer_month", ORDER_MAPPER);
~~~

Ngoài việc thiếu partition key, truy vấn này đòi hỏi ứng dụng xử lý một tập dữ liệu lớn không xác định. Thay vào đó:

1. Chốt đường `WHERE` với **đầy đủ partition key**.
2. Dùng `LIMIT` cho API chỉ cần một số hàng đầu tiên.
3. Với danh sách dài có nút “xem thêm”, dùng **paging state** của Cassandra/driver hoặc API paging của Spring Data phù hợp.
4. Không dùng mô hình `OFFSET 100000` hoặc tải mọi hàng rồi chia trang trong bộ nhớ.

Ví dụ kiểm soát `page size` ở mức Java Driver:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

PreparedStatement ps = session.prepare(
        "SELECT order_id, created_at, status, total_amount " +
        "FROM orders_by_customer_month " +
        "WHERE tenant_id = ? AND customer_id = ? AND month_bucket = ?");

BoundStatement bs = ps.bind(tenantId, customerId, monthBucket)
        .setPageSize(20);

ResultSet rs = session.execute(bs);
// Driver có thể tự lấy thêm trang khi duyệt ResultSet.
// Để xây API cursor từng trang, phải quản lý paging state đúng cách,
// không lặp toàn bộ ResultSet và nghĩ rằng chỉ có 20 hàng.
~~~

`setPageSize(20)` điều khiển số hàng trên **một lần fetch** tương ứng, **không tương đương `LIMIT 20`** tổng số hàng. Khi duyệt đồng bộ `ResultSet`, driver có thể tự fetch các trang tiếp theo. Muốn API “mỗi request trả một trang”, cần sử dụng API paging/driver theo đúng ngữ nghĩa và quản lý cursor sau trang đã tiêu thụ; không chỉ đặt page size rồi `forEach` toàn bộ `ResultSet`.

Paging state gắn với statement, điều kiện và tham số tương thích. Không dùng paging state của khách C/tháng 11 cho khách khác hoặc tháng khác. Nếu cần lịch sử nhiều tháng, ứng dụng phải quản lý cursor/tập kết quả cho **nhiều partition** rồi ghép thứ tự, chứ không có một cursor toàn cục miễn phí.

## 12. Kiểm thử CRUD và cách xác nhận kết quả

Khi đã có test Cassandra instance, keyspace và bảng fixture, nên kiểm thử bằng dữ liệu thật:

| Tình huống | Kết quả cần xác minh |
|---|---|
| `INSERT` hàng mới | `SELECT` đúng toàn bộ primary key trả dữ liệu đã ghi |
| Ghi lại cùng khóa/payload | Không sinh hàng thứ hai với khóa khác |
| Retry cố tình đổi `order_id` | Chỉ ra nguy cơ sinh hàng trùng nghiệp vụ |
| `UPDATE status` theo khóa đủ | Chỉ hàng mục tiêu đổi trạng thái |
| `UPDATE` với khóa chưa có, không `IF EXISTS` | Hiểu nguy cơ upsert; không hiểu sai boolean |
| `UPDATE ... IF status = 'NEW'` | Applied đúng khi trạng thái phù hợp; false khi không phù hợp |
| `DELETE` theo đủ khóa | Không còn hàng mục tiêu, các đơn cùng partition vẫn còn |
| `DELETE` theo chỉ partition key | Có thể xóa **cả partition**; chỉ thử trên dữ liệu test cô lập |
| `SELECT` nhiều hàng | Thứ tự clustering đúng, `LIMIT` và paging phù hợp |
| `null`, TTL, tombstone | Kết quả đọc phản ánh lifecycle dữ liệu, không nhầm với lỗi mapping |

### 12.1. Khung integration test minh họa

~~~java
@Test
void insertUpdateDeleteOneOrderByFullPrimaryKey() {
    // Given: tạo tenantId, customerId, monthBucket, createdAt,
    // orderId một lần; keyspace/test table đã có.

    boolean inserted = writer.insertOrder(
            tenantId, customerId, monthBucket,
            createdAt, orderId, "NEW", new BigDecimal("125000.00"));
    assertTrue(inserted);

    OrderSummary found = reader.findExact(
            tenantId, customerId, monthBucket,
            createdAt, orderId).orElseThrow();
    assertEquals("NEW", found.status());

    assertTrue(writer.updateStatus(
            tenantId, customerId, monthBucket,
            createdAt, orderId, "PAID"));
    assertEquals(
            "PAID",
            reader.findExact(tenantId, customerId, monthBucket,
                    createdAt, orderId).orElseThrow().status());

    assertTrue(writer.deleteExact(
            tenantId, customerId, monthBucket, createdAt, orderId));
    assertTrue(reader.findExact(
            tenantId, customerId, monthBucket,
            createdAt, orderId).isEmpty());
}
~~~

Đây là **khung test**, không phải code đã chạy. Để biên dịch, cần đặt các phương thức vào DAO/service tương ứng, khai báo `writer`/`reader`, import JUnit và chuẩn bị fixture trong một môi trường test. Nó minh họa việc xác nhận **giá trị sau ghi** bằng `SELECT`, thay vì chỉ nhìn boolean returned của `execute`.

### 12.2. Đối chiếu dữ liệu trực tiếp bằng CQL

Sau `INSERT`, có thể đọc CQL không qua mapper:

~~~sql
SELECT tenant_id, customer_id, month_bucket,
       created_at, order_id, status, total_amount
FROM orders_by_customer_month
WHERE tenant_id = ?
  AND customer_id = ?
  AND month_bucket = ?
  AND created_at = ?
  AND order_id = ?;
~~~

Điều này giúp phát hiện mapping sai cột, `BigDecimal` bị đổi thành kiểu gần đúng, sai số `Instant` dưới mili giây, hay khác biệt giữa entity Java và dữ liệu CQL thật.

Trong các kiểm thử tích hợp, tránh dùng `COUNT(*)` quét toàn bộ bảng lớn như một cách kiểm tra thao tác của một hàng. Hãy kiểm tra đúng khóa mục tiêu và những hàng lân cận cần bảo toàn.

## 13. Lỗi phổ biến và cách khoanh vùng

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `SELECT` thiếu điều kiện trên partition key | Không định vị được partition theo đường chuẩn | Bổ sung đủ khóa hoặc dùng bảng truy cập khác |
| `INSERT` báo thiếu primary key | Một thành phần partition/clustering key `null` hoặc bị bỏ qua | Validate đủ năm field khóa |
| `INSERT` không lỗi nhưng thay thế dữ liệu | Cassandra có semantics upsert | Xem lại khóa và dùng `IF NOT EXISTS` khi cần |
| `UPDATE` chạy nhưng hàng không có trước đó | Upsert của `UPDATE` vô điều kiện | Dùng `IF EXISTS` nếu yêu cầu thật sự là cập nhật hàng tồn tại |
| `DELETE` xóa nhiều đơn | Chỉ cung cấp partition key | Xác định đầy đủ clustering key cho thao tác xóa một hàng |
| Cột `total_amount` đọc ra `null` | Chưa ghi, bị xóa hoặc TTL hết hạn | Xác nhận lifecycle và chính sách nullable |
| Boolean `execute` trả true nhưng không biết số hàng thay đổi | API không trả affected-row-count theo SQL quan hệ | Đọc lại dữ liệu hoặc dùng LWT cho điều kiện cụ thể |
| Lỗi kiểu bind `UUID/LocalDate/Instant` | Thứ tự tham số sai hoặc kiểu Java/CQL không tương thích | Đối chiếu từng dấu `?` với schema |
| `queryForObject` ném lỗi không có hàng | API kỳ vọng đúng một hàng | Chọn `query` + `Optional` cho trường hợp not found |
| Truy vấn chậm dù có `LIMIT` | Hot/large partition hoặc lọc ngoài đường khóa | Đo partition/tombstone, cân nhắc bucket và read model |
| Hàng “biến mất” sau một thời gian | TTL hoặc xóa tạo tombstone | Kiểm tra TTL/schema/policy, không đổ lỗi cho RowMapper |

Nếu driver không kết nối được contact points, sai local datacenter hoặc keyspace chưa tồn tại, sửa `SELECT`/DAO cũng không giải quyết được. Phải tách lỗi **kết nối**, **schema**, **CQL theo khóa** và **mapping** để chẩn đoán đúng.

## 14. Bài tập thực hành

Một hệ thống giao nhận có API:

~~~text
GET    /packages/{packageId}/events?day=2026-11-25&limit=50
POST   /packages/{packageId}/events
PATCH  /packages/{packageId}/events/{eventId}
DELETE /packages/{packageId}/events/{eventId}
~~~

Bảng:

~~~sql
CREATE TABLE package_events_by_day (
    package_id uuid,
    event_day date,
    occurred_at timestamp,
    event_id uuid,
    event_type text,
    notes text,
    PRIMARY KEY ((package_id, event_day), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, event_id ASC);
~~~

**Yêu cầu:**

1. Viết `SELECT` trả 50 event mới nhất trong ngày bằng đủ partition key.
2. Viết `INSERT` với đủ `package_id, event_day, occurred_at, event_id`; đảm bảo `event_id` và `occurred_at` được giữ nguyên qua retry.
3. Viết `UPDATE` chỉ sửa `notes` của một event, yêu cầu đủ primary key.
4. Viết `DELETE` một event cụ thể, tránh xóa cả partition.
5. Giải thích vì sao `eventId` trong route `PATCH/DELETE` chưa đủ để tìm hàng khi thiếu `event_day` và `occurred_at`.
6. Thêm một bảng locator theo event ID nếu yêu cầu tra bằng ID là phổ biến, trình bày chi phí duy trì projection và kiểm tra quyền truy cập.

**Lời giải CQL tham khảo:**

~~~sql
-- 1. SELECT danh sách trong một partition.
SELECT occurred_at, event_id, event_type, notes
FROM package_events_by_day
WHERE package_id = ? AND event_day = ?
LIMIT 50;

-- 2. INSERT một event với đầy đủ primary key.
INSERT INTO package_events_by_day (
    package_id, event_day, occurred_at, event_id, event_type, notes
) VALUES (?, ?, ?, ?, ?, ?);

-- 3. UPDATE cột thường của đúng một event.
UPDATE package_events_by_day SET notes = ?
WHERE package_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;

-- 4. DELETE đúng một hàng.
DELETE FROM package_events_by_day
WHERE package_id = ? AND event_day = ?
  AND occurred_at = ? AND event_id = ?;
~~~

### Câu hỏi tự kiểm tra

1. `CqlTemplate` khác `CassandraTemplate` ở mức trừu tượng và mapping thế nào?
2. Vì sao `SELECT` danh sách chỉ cần partition key còn `UPDATE` một hàng phải có đủ clustering columns?
3. `INSERT` cùng toàn bộ primary key có mặc nhiên báo lỗi trùng không?
4. Giá trị `boolean` của `execute` có tương đương affected-row-count của SQL quan hệ không?
5. `UPDATE ... IF EXISTS` được dùng khi nào, và chi phí chính là gì?
6. Lệnh `DELETE` chỉ có `package_id` và `event_day` trong bảng ví dụ xóa gì?
7. Vì sao phải bind giá trị bằng `?` thay vì nối `customerId` trực tiếp vào chuỗi CQL?
8. `setPageSize(20)` có bắt buộc driver chỉ trả đúng 20 hàng trong toàn bộ ResultSet không?
9. Chọn `LOCAL_QUORUM` có tự bảo đảm hai bảng projection cập nhật nguyên tử không?

**Đáp án ngắn:** (1) CqlTemplate thực thi/mapping CQL trực tiếp, CassandraTemplate dựa trên entity mapping; (2) đọc một partition khác thao tác đúng một hàng; (3) không, upsert; (4) không; (5) khi muốn chỉ sửa hàng có sẵn, dùng LWT; (6) cả partition ngày của package; (7) an toàn và đúng kiểu bind; (8) không, driver có thể fetch thêm trang; (9) không.

## 15. Checklist trước khi triển khai CQL CRUD

- [ ] Nắm rõ **partition key** và **clustering columns** của bảng, không suy từ tên `id`.
- [ ] `SELECT` danh sách có đủ partition key và giới hạn số hàng.
- [ ] `SELECT` một hàng, `UPDATE` một hàng, `DELETE` một hàng dùng đủ primary key.
- [ ] `INSERT` có mọi field khóa, ID và thời điểm nghiệp vụ ổn định qua retry.
- [ ] Hiểu `INSERT`/`UPDATE` vô điều kiện là upsert; không mặc định kiểm tra trùng.
- [ ] Dùng `IF NOT EXISTS`/`IF EXISTS`/CAS có chủ đích và đánh giá chi phí LWT.
- [ ] Không nhầm `execute` boolean với số hàng thay đổi.
- [ ] Bind giá trị bằng tham số `?`, whitelist tên bảng/cột nếu có lựa chọn cấu trúc.
- [ ] Không dùng `ALLOW FILTERING` để che truy vấn sai partition key.
- [ ] Kiểm tra nguy cơ xóa cả partition và tombstone khi `DELETE`.
- [ ] Dùng paging state cho danh sách dài; không nhầm fetch size với tổng giới hạn.
- [ ] Chọn consistency, TTL, retry và timeout theo replication/điều kiện nghiệp vụ.
- [ ] So sánh kết quả đọc lại bằng CQL và integration test, có kiểm thử race condition.
- [ ] Đo p95/p99, hot partition, tombstones, số trang và write amplification trên dữ liệu đại diện.

## Tài liệu tham khảo

- [Spring Data Cassandra — CQL Template API](https://docs.spring.io/spring-data/cassandra/reference/cassandra/cql-template.html).
- [Spring Data Cassandra — Prepared Statements](https://docs.spring.io/spring-data/cassandra/reference/cassandra/prepared-statements.html).
- [Spring Data Cassandra — CassandraTemplate](https://docs.spring.io/spring-data/cassandra/reference/cassandra/template.html).
- [Spring Data Cassandra — Object Mapping](https://docs.spring.io/spring-data/cassandra/reference/cassandra/object-mapping.html).
- [Apache Cassandra — CQL Data Manipulation](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/index.html).

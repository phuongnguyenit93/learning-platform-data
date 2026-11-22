# Batch JDBC, fetch size, cursor và đọc kết quả lớn trong PostgreSQL

Ứng dụng Java kết nối PostgreSQL thường gặp hai tình huống hiệu năng rất khác nhau:

- **Ghi nhiều bản ghi**: nhập hàng chục nghìn đơn hàng, đồng bộ trạng thái từ một dịch vụ khác hoặc thực hiện nhiều lệnh UPDATE. Nếu gửi riêng từng lệnh, số round trip mạng và chi phí thực thi có thể rất lớn.
- **Đọc kết quả rất lớn**: xuất 500.000 dòng báo cáo hoặc duyệt nhiều sự kiện. Nếu driver tập hợp hết rows vào heap Java, ứng dụng có thể tăng GC, hết bộ nhớ hoặc giữ connection quá lâu.

JDBC cung cấp các cơ chế khác nhau cho hai nhu cầu:

| Bài toán | Công cụ | Mục đích |
| --- | --- | --- |
| Nhiều bộ tham số cho cùng SQL | `PreparedStatement.addBatch()`, `executeBatch()` | Giảm overhead ghi hàng loạt |
| Transaction bao nhiều thao tác | `setAutoCommit(false)`, `commit()`, `rollback()` | Kiểm soát atomicity |
| Duyệt một ResultSet lớn | `setFetchSize(n)` | Điều chỉnh nhóm hàng driver lấy |
| Giữ trạng thái duyệt ở server | Cursor/portal | Lấy tiếp dữ liệu từng nhóm |
| Lấy nhiều trang độc lập | Keyset pagination | Tránh OFFSET sâu và giữ transaction quá lâu |
| Bulk load chuyên dụng | `COPY` và pgJDBC Copy API | Truyền dữ liệu lớn hiệu quả |

**Batch ghi khác fetch batch.** `executeBatch()` xử lý nhiều commands hoặc nhiều parameter sets. `setFetchSize()` áp dụng cho việc lấy các rows của **một kết quả SELECT**.

~~~mermaid
flowchart TD
    A["Ứng dụng Java"] --> Q{"Kiểu workload?"}
    Q -->|"Ghi hàng loạt"| W["PreparedStatement.addBatch"]
    W --> WX["executeBatch"]
    WX --> T["COMMIT / ROLLBACK"]
    Q -->|"Đọc một SELECT lớn"| F["setFetchSize(n)"]
    F --> C["ResultSet forward-only, transaction"]
    C --> S["pgJDBC cursor/portal"]
    S --> R["Xử lý từng row, không giữ cả kết quả"]
    Q -->|"Các trang độc lập"| K["Keyset + LIMIT"]
    K --> P["Checkpoint và resume"]
~~~

Bài học thuộc chương **Kết nối ứng dụng**, module **Database Engine Relational PostgreSQL**. Mọi ví dụ dùng database thực hành riêng, Java/JDBC và pgJDBC tương thích môi trường của bạn.

## 1. Mục tiêu học tập

Sau bài, bạn có thể:

1. Phân biệt batch INSERT/UPDATE, fetch size và SQL cursor.
2. Viết `PreparedStatement` dùng `addBatch`, `executeBatch` và transaction.
3. Hiểu `BatchUpdateException`, update counts, lỗi SQLSTATE và rollback.
4. Chọn batch size và transaction chunk khác nhau theo business contract.
5. Biết tác dụng và giới hạn của `reWriteBatchedInserts` trong pgJDBC.
6. Sử dụng `ON CONFLICT` và idempotency key để xử lý retry.
7. So sánh JDBC batch và PostgreSQL `COPY`.
8. Giải thích vì sao `ResultSet.next()` không tự bảo đảm streaming bộ nhớ.
9. Dùng `setFetchSize` đúng điều kiện pgJDBC: `autoCommit=false`, forward-only, fetchSize dương và query/protocol phù hợp.
10. Quản lý vòng đời `ResultSet`, `Statement`, `Connection` và transaction.
11. Phân biệt cursor do driver quản lý và SQL `DECLARE/FETCH/CLOSE`.
12. Tránh giữ snapshot/locks/connection quá lâu, ảnh hưởng VACUUM và pool.
13. Viết keyset pagination có khóa sắp xếp ổn định.
14. Xây export có backpressure, timeout và cleanup.
15. Đo end-to-end throughput, heap/GC, server IO, WAL, latency và transaction duration.

## 2. Đường đi của dữ liệu từ PostgreSQL tới Java

~~~text
Java code
  |
  | PreparedStatement.executeQuery()
  v
pgJDBC
  |
  | PostgreSQL wire protocol
  v
PostgreSQL backend
  |
  | Scan / Join / Aggregate / Sort
  v
Row production
  |
  | Fetch all hoặc cursor fetch
  v
ResultSet.next()
  |
  | Row mapping
  v
CSV writer / domain consumer / streaming sink
~~~

Muốn ứng dụng chạy tốt, phải xem toàn bộ pipeline:

- SQL có đọc quá nhiều rows không?
- Query plan có Sort/HashAggregate tốn memory không?
- Driver buffer bao nhiêu rows?
- Mỗi row chứa bao nhiêu bytes?
- Java có tạo `List` tích lũy vô hạn không?
- Sink ghi file/network có nhanh bằng tốc độ đọc không?
- Transaction và DB connection được giữ bao lâu?

**Fetch size không thay cho SQL index và WHERE tốt.** Nó chủ yếu điều khiển cách driver nhận kết quả, không thay số hàng PostgreSQL phải tính.

## 3. Môi trường thực hành

Các đoạn Java dùng:

- JDK hỗ trợ Java text blocks, ví dụ Java 17.
- JDBC chuẩn `java.sql`.
- PostgreSQL JDBC driver **pgJDBC** tương thích JDK/PostgreSQL.
- Một database lab được phép tạo bảng.
- `DataSource` (từ connection pool) hoặc connection hợp lệ.

Ví dụ dependency Maven:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version><!-- Phiên bản đã được dự án chốt và kiểm chứng --></version>
</dependency>
~~~

Không hard-code user/password thật trong code, log hoặc tài liệu. Kết nối mẫu:

~~~text
jdbc:postgresql://localhost:5432/training_db
~~~

Tên `training_db` chỉ là ví dụ. Phải cấu hình credentials bằng secret manager hoặc cơ chế triển khai an toàn.

## 4. Lab: schema cho ghi và đọc lớn

**Cảnh báo:** `DROP SCHEMA ... CASCADE` sẽ xóa toàn bộ đối tượng trong schema được chỉ định. Chỉ dùng ở **database lab riêng**, không chạy trên production.

~~~sql
-- CHỈ CHẠY TRONG DATABASE THỰC HÀNH.
DROP SCHEMA IF EXISTS jdbc_batch_lab CASCADE;
CREATE SCHEMA jdbc_batch_lab;

CREATE TABLE jdbc_batch_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key text NOT NULL UNIQUE,
    customer_ref text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount > 0),
    status text NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'confirmed', 'cancelled')),
    created_at timestamptz NOT NULL
        DEFAULT transaction_timestamp()
);

CREATE TABLE jdbc_batch_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type text NOT NULL,
    event_time timestamptz NOT NULL,
    payload text NOT NULL
);

CREATE INDEX idx_events_time_id
ON jdbc_batch_lab.events (event_time, event_id);
~~~

Nạp vài đơn hàng ban đầu:

~~~sql
INSERT INTO jdbc_batch_lab.orders (
    idempotency_key, customer_ref, amount
)
VALUES
    ('seed-001', 'customer-A', 100.00),
    ('seed-002', 'customer-B',  75.50),
    ('seed-003', 'customer-C',  24.00);
~~~

Tạo dữ liệu đọc lớn:

~~~sql
-- 50.000 rows minh họa; nếu lab nhỏ, dùng 5.000.
INSERT INTO jdbc_batch_lab.events (
    event_type, event_time, payload
)
SELECT
    CASE WHEN g % 5 = 0 THEN 'payment' ELSE 'view' END,
    timestamptz '2026-01-01 00:00:00+00'
        + g * interval '1 second',
    repeat('x', 200)
FROM generate_series(1, 50000) AS s(g);

ANALYZE jdbc_batch_lab.orders;
ANALYZE jdbc_batch_lab.events;
~~~

Lab có 50.000 sự kiện × payload 200 ký tự; phần ghi này tạo index/WAL và dùng tài nguyên thật. Không chạy trên database có tải production.

## 5. PreparedStatement thay ghép chuỗi SQL

Sai:

~~~java
// ANTI-PATTERN: input được ghép vào SQL.
String sql = "INSERT INTO jdbc_batch_lab.orders (customer_ref,amount)"
    + " VALUES ('" + customerRef + "'," + amount + ")";
~~~

Đúng:

~~~java
String sql = """
    INSERT INTO jdbc_batch_lab.orders (
        idempotency_key, customer_ref, amount
    ) VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, idempotencyKey);
    ps.setString(2, customerRef);
    ps.setBigDecimal(3, amount);
    ps.executeUpdate();
}
~~~

Bind parameters giúp chống SQL injection, tránh lỗi quoting và tạo một template SQL có thể tái sử dụng nhiều lần. Đây cũng là nền tảng của JDBC batch.

## 6. Ghi từng hàng có những chi phí gì?

Ví dụ:

~~~java
for (OrderInput order : orders) {
    try (PreparedStatement ps =
            connection.prepareStatement(INSERT_SQL)) {
        ps.setString(1, order.key());
        ps.setString(2, order.customerRef());
        ps.setBigDecimal(3, order.amount());
        ps.executeUpdate();
    }
}
~~~

Nếu có 10.000 phần tử, code tạo nhiều statements và thực hiện nhiều lần giao tiếp với server. Khi `autoCommit=true`, mỗi statement còn có thể nằm trong một transaction riêng.

Tối ưu theo mức độ:

1. Tái sử dụng một `PreparedStatement`.
2. Gộp các bộ tham số bằng `addBatch()`.
3. Xác định transaction boundary phù hợp.
4. Kiểm chứng `reWriteBatchedInserts` nếu dùng pgJDBC.
5. Với bulk load lớn, cân nhắc `COPY`.

**Đừng dùng batch để che một SQL query vốn có thể xử lý set-based tốt hơn.**

## 7. addBatch và executeBatch

~~~java
try (PreparedStatement ps = connection.prepareStatement(INSERT_SQL)) {
    for (OrderInput order : orders) {
        ps.setString(1, order.key());
        ps.setString(2, order.customerRef());
        ps.setBigDecimal(3, order.amount());
        ps.addBatch();
    }

    int[] updateCounts = ps.executeBatch();
}
~~~

### Ý nghĩa chính xác

- `setString/setBigDecimal`: bind values cho statement.
- `addBatch`: thêm một bộ values vào batch logic.
- `executeBatch`: yêu cầu JDBC driver thực thi batch.
- `updateCounts`: báo kết quả của các commands theo hợp đồng JDBC.
- `commit`: kết thúc transaction khi autocommit tắt.

**Gọi addBatch không đồng nghĩa row đã được lưu. Gọi executeBatch cũng không đồng nghĩa đã COMMIT** nếu connection đang trong transaction do caller quản lý.

## 8. Ví dụ Java hoàn chỉnh: batch INSERT atomic

Đầu vào:

~~~java
import java.math.BigDecimal;

public record OrderInput(
    String key,
    String customerRef,
    BigDecimal amount
) {}
~~~

Method tự mở connection và quản lý transaction:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.List;

public final class OrderImporter {

    private static final String INSERT_SQL = """
        INSERT INTO jdbc_batch_lab.orders (
            idempotency_key, customer_ref, amount
        )
        VALUES (?, ?, ?)
        ON CONFLICT (idempotency_key) DO NOTHING
        """;

    public static void insertOrders(
            DataSource dataSource,
            List<OrderInput> orders
    ) throws SQLException {

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (PreparedStatement ps =
                        connection.prepareStatement(INSERT_SQL)) {

                    for (OrderInput order : orders) {
                        ps.setString(1, order.key());
                        ps.setString(2, order.customerRef());
                        ps.setBigDecimal(3, order.amount());
                        ps.addBatch();
                    }

                    ps.executeBatch();
                }

                connection.commit();

            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
~~~

Giải thích:

- `DataSource` cung cấp connection từ pool.
- Method sở hữu connection/transaction riêng.
- `setAutoCommit(false)` cho phép commit sau cả nhóm.
- `ON CONFLICT DO NOTHING` xử lý duplicate key được dự kiến.
- Exception được rollback rồi ném lại; lỗi rollback được giữ trong `suppressed exceptions`.
- `try-with-resources` đóng statement/connection.

**Không copy `commit()` vào function đã tham gia transaction của Spring/JTA hoặc caller khác**. Nếu transaction do framework quản lý, framework phải quyết định boundary.

## 9. Dùng BigDecimal cho tiền

~~~java
new OrderInput(
    "ext-001",
    "customer-A",
    new BigDecimal("19.99")
);
~~~

Tránh:

~~~java
new BigDecimal(0.1);
~~~

khi mong đúng thập phân `0.1`, vì constructor từ `double` có thể giữ sai số biểu diễn nhị phân. Dùng string hoặc một cách chuyển giá trị an toàn theo contract.

PostgreSQL `numeric(12,2)` phù hợp số tiền cố định hai chữ số thập phân theo ví dụ; hệ thống nhiều đơn vị tiền tệ có thể cần mô hình precision/currency riêng.

## 10. Batch size: chia nhóm lệnh

Một triệu rows không nên dồn hết vào một batch duy nhất rồi giữ mọi parameter trong bộ nhớ.

~~~java
int batchSize = 500;
int pending = 0;

try (PreparedStatement ps = connection.prepareStatement(INSERT_SQL)) {
    for (OrderInput order : orders) {
        ps.setString(1, order.key());
        ps.setString(2, order.customerRef());
        ps.setBigDecimal(3, order.amount());
        ps.addBatch();

        pending++;

        if (pending >= batchSize) {
            ps.executeBatch();
            ps.clearBatch();
            pending = 0;
        }
    }

    if (pending > 0) {
        ps.executeBatch();
        ps.clearBatch();
    }
}
~~~

**Chia batch không phải chia transaction.** Nếu `connection.commit()` chỉ gọi một lần cuối cùng, các lần executeBatch vẫn thuộc cùng transaction.

### Chọn bao nhiêu rows mỗi batch?

Thử 100, 500, 1.000 hoặc giá trị phù hợp bằng benchmark. Phụ thuộc:

- Kích thước mỗi row.
- Số parameters mỗi command.
- Round-trip latency.
- RAM driver/JVM.
- WAL, index và trigger costs.
- Lock duration.
- Replication lag.
- Giới hạn protocol/driver.
- Yêu cầu rollback khi lỗi.

Không tự xem 10.000 luôn nhanh hơn 500.

## 11. Batch size và transaction chunk là hai thứ

**Một transaction duy nhất:**

~~~text
BEGIN
  executeBatch(500)
  executeBatch(500)
  ...
COMMIT
~~~

Nếu một batch giữa chừng lỗi không được xử lý, có thể rollback toàn bộ job. Phù hợp khi cần **all-or-nothing**, nhưng transaction có thể dài.

**Nhiều transaction nhỏ:**

~~~text
BEGIN -> executeBatch(500) -> COMMIT
BEGIN -> executeBatch(500) -> COMMIT
...
~~~

Giảm thời gian giữ lock/snapshot và dễ resume, nhưng job có thể thành công một phần nếu batch sau lỗi.

### Thiết kế nghiệp vụ phải trả lời

- Có chấp nhận partial import không?
- Đã xử lý tới batch nào?
- Làm sao retry an toàn?
- Input có idempotency key?
- Có transaction checkpoint cùng dữ liệu không?
- Điều gì xảy ra khi network mất ngay sau COMMIT?

**Không đổi atomicity chỉ vì muốn cải thiện rows/s.**

## 12. Đọc update counts

`PreparedStatement.executeBatch()` trả `int[]`. `executeLargeBatch()` trả `long[]` khi cần đại diện số lượng rất lớn theo JDBC contract.

Một phần tử có thể là:

| Giá trị | Ý nghĩa |
| --- | --- |
| Số nguyên không âm | Số hàng được báo đã tác động |
| `Statement.SUCCESS_NO_INFO` (-2) | Thành công nhưng không biết count chính xác |
| `Statement.EXECUTE_FAILED` (-3) | Lệnh lỗi khi driver tiếp tục batch và báo trạng thái đó |

~~~java
int[] counts = ps.executeBatch();

for (int count : counts) {
    if (count >= 0) {
        System.out.println("Affected rows = " + count);
    } else if (count == java.sql.Statement.SUCCESS_NO_INFO) {
        System.out.println("Succeeded, count not available");
    } else if (count == java.sql.Statement.EXECUTE_FAILED) {
        System.out.println("Batch command failed");
    }
}
~~~

Với `ON CONFLICT DO NOTHING`, một command có thể ghi **0 hàng**. Khi driver rewrite batch, count chi tiết còn có thể khác tùy phiên bản/cách tối ưu.

**Không coi `counts.length` là số bản ghi đã commit.** Cần xác minh bằng truy vấn sau COMMIT theo batch ID/idempotency keys.

## 13. BatchUpdateException

~~~java
try {
    ps.executeBatch();
} catch (java.sql.BatchUpdateException ex) {
    int[] counts = ex.getUpdateCounts();
    String sqlState = ex.getSQLState();

    // Chỉ ghi metadata được phép; tránh log PII.
    System.err.println(
        "Batch failed: SQLSTATE=" + sqlState
        + ", counts reported=" + counts.length
    );

    throw ex;
}
~~~

Theo JDBC, driver có thể dừng khi gặp lỗi hoặc tiếp tục xử lý một số commands, và update counts phản ánh điều đó.

Trong PostgreSQL, một SQL statement lỗi bên trong explicit transaction thường khiến transaction rơi vào trạng thái **aborted** cho tới khi `ROLLBACK` hoặc rollback về savepoint hợp lệ. Không cứ tiếp tục executeBatch mới trên connection đó mà tưởng lỗi đã được “bỏ qua”.

### Hướng xử lý an toàn

1. Phân loại SQLSTATE.
2. Rollback transaction đã thất bại.
3. Ghi log có cấu trúc, không ghi toàn bộ payload nhạy cảm.
4. Xác định lỗi có thể retry không.
5. Retry toàn transaction có giới hạn và idempotency.
6. Kiểm tra trạng thái commit khi client không rõ kết quả.

## 14. SQLSTATE quan trọng

| Mã | Ý nghĩa | Cách tiếp cận |
| --- | --- | --- |
| `23505` | Unique violation | Kiểm tra key/payload và duplicate policy |
| `23503` | Foreign key violation | Dữ liệu tham chiếu hoặc thứ tự import |
| `23514` | Check violation | Input vi phạm bất biến |
| `23502` | Not-null violation | Thiếu giá trị bắt buộc |
| `40001` | Serialization failure | Retry toàn transaction khi an toàn |
| `40P01` | Deadlock detected | Rollback, backoff và retry phù hợp |
| `55P03` | Lock not available | Điều chỉnh lock strategy/timeout |
| `57014` | Query cancelled | Xử lý timeout/cancel |
| `08006` | Connection failure | Có thể không rõ transaction đã commit chưa |

Không retry mù mọi lỗi constraint. Nếu input amount âm, thực hiện lại một triệu lần cũng không sửa được dữ liệu.

## 15. Idempotency để tránh ghi trùng

Giả sử server đã COMMIT một batch nhưng client mất connection trước khi nhận kết quả. Client có thể retry.

Schema dùng:

~~~sql
idempotency_key text NOT NULL UNIQUE
~~~

Ví dụ:

~~~sql
INSERT INTO jdbc_batch_lab.orders (
    idempotency_key, customer_ref, amount
)
VALUES (
    'external-123',
    'customer-A',
    100.00
)
ON CONFLICT (idempotency_key) DO NOTHING;
~~~

Cùng key sẽ không tạo thêm row. Tuy nhiên phải xử lý **cùng key nhưng payload khác**; `DO NOTHING` một mình có thể che lỗi nghiệp vụ nếu caller gửi dữ liệu thay đổi.

Thiết kế production thường cần canonical payload hash/kiểm tra những field đã ghi và error contract rõ. Đừng tạo một key ngẫu nhiên **mới** cho mỗi lần retry của cùng request.

## 16. reWriteBatchedInserts trong pgJDBC

Driver pgJDBC có connection property:

~~~text
reWriteBatchedInserts=true
~~~

Ví dụ URL:

~~~text
jdbc:postgresql://localhost:5432/training_db?reWriteBatchedInserts=true
~~~

Khi statement/batch đủ điều kiện, driver có thể rewrite nhiều INSERT thành dạng multi-values:

~~~sql
INSERT INTO jdbc_batch_lab.orders (
    idempotency_key, customer_ref, amount
)
VALUES
    (?, ?, ?),
    (?, ?, ?),
    (?, ?, ?);
~~~

### Lợi ích

- Giảm overhead/round trips với nhiều INSERT cùng template.
- Có thể nâng rows/s đáng kể trong workload phù hợp.

### Giới hạn

- Đây là **property của pgJDBC**, không phải JDBC chuẩn.
- Không phải mọi SQL/batch đều đủ điều kiện rewrite.
- `RETURNING`, generated keys và câu INSERT phức tạp có thể tác động khả năng rewrite.
- Driver có thể chia nhóm để tuân giới hạn parameters/protocol.
- Batch counts có thể không luôn map như từng INSERT riêng.
- PostgreSQL vẫn phải kiểm tra UNIQUE/FK/CHECK/triggers.
- Cần test phiên bản driver thật.

**Không giả định bật property thì mọi thao tác sẽ nhanh hơn một tỷ lệ cố định hoặc tạo một statement không giới hạn kích thước.**

## 17. Generated keys với batch cần thận trọng

Một INSERT đơn:

~~~java
String sql = """
    INSERT INTO jdbc_batch_lab.orders (
        idempotency_key, customer_ref, amount
    )
    VALUES (?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(
        sql,
        java.sql.Statement.RETURN_GENERATED_KEYS)) {

    ps.setString(1, "generated-key-demo");
    ps.setString(2, "customer-A");
    ps.setBigDecimal(3, new java.math.BigDecimal("25.00"));

    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long orderId = keys.getLong(1);
            System.out.println(orderId);
        }
    }
}
~~~

Với batch:

- `getGeneratedKeys()` và `RETURNING` có driver-specific mapping/performance.
- `ON CONFLICT DO NOTHING` có thể không sinh key.
- Không giả định mỗi input command đều có đúng một generated key trả về.
- Nếu cần mapping chính xác, dùng correlation key bên ứng dụng và thiết kế SQL phù hợp.

Đừng đổi tính đúng đắn của mapping lấy throughput.

## 18. Batch UPDATE hoặc SQL set-based?

Một batch UPDATE:

~~~java
String sql = """
    UPDATE jdbc_batch_lab.orders
    SET status = ?
    WHERE idempotency_key = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (String key : keys) {
        ps.setString(1, "confirmed");
        ps.setString(2, key);
        ps.addBatch();
    }

    ps.executeBatch();
}
~~~

Nhưng nếu tất cả key đã biết:

~~~sql
UPDATE jdbc_batch_lab.orders
SET status = 'confirmed'
WHERE idempotency_key IN ('seed-001', 'seed-002');
~~~

Một câu SQL set-based có thể đơn giản và nhanh hơn hàng trăm UPDATE riêng. Với dữ liệu lớn, cân nhắc staging table, `UPDATE ... FROM`, `INSERT ... ON CONFLICT DO UPDATE` hoặc `COPY` rồi merge theo thiết kế.

**Batch JDBC giảm chi phí gửi nhiều commands, không thay thế tư duy set-based SQL.**

## 19. COPY cho bulk load

PostgreSQL `COPY` hỗ trợ nhập/xuất dữ liệu hàng loạt và pgJDBC có Copy API mở rộng, khác `PreparedStatement.executeBatch`.

| Yêu cầu | JDBC batch | COPY |
| --- | --- | --- |
| Nhiều INSERT parameterized | Phù hợp | Có thể dùng nguồn stream/file |
| Bulk load rất lớn | Tốt tùy workload | Thường hiệu quả |
| ON CONFLICT trực tiếp | Có qua INSERT | COPY trực tiếp không có ON CONFLICT |
| Lấy per-row generated keys | Cần driver/SQL mapping | Không giống INSERT RETURNING |
| Validation từng row | Java/JDBC dễ kiểm soát | Nên xem staging/validation |
| Atomicity | Transaction | Transaction |
| Portable JDBC | Có | Copy API riêng PostgreSQL |

Ví dụ quy trình:

~~~text
BEGIN
  COPY staging_orders FROM input stream
  Validate and transform in SQL
  INSERT INTO orders SELECT ... FROM staging_orders
    ON CONFLICT (...) DO NOTHING
COMMIT
~~~

Nếu data source lớn nhưng bẩn, staging cho phép kiểm tra duplicates, mapping, constraints và báo cáo lỗi. Không tắt constraints production chỉ để import nhanh.

## 20. Khi nào dùng Savepoint?

JDBC có `Savepoint` để rollback một phần:

~~~java
java.sql.Savepoint sp = connection.setSavepoint();

try {
    // Thực thi một nhóm SQL.
} catch (SQLException ex) {
    connection.rollback(sp);
    // Quyết định bỏ qua hay báo lỗi theo chính sách import.
}
~~~

Sau statement lỗi trong transaction, phải rollback tới savepoint hợp lệ trước khi tiếp tục công việc khác theo semantics PostgreSQL.

Nhưng:

- Savepoint có overhead.
- Không được nuốt lỗi không biết cách xử lý.
- Không làm side effect bên ngoài được rollback.
- Nếu dữ liệu sai nguyên nhân rõ, retry không giúp gì.
- Thường không cần savepoint cho import all-or-nothing; rollback toàn transaction đơn giản hơn.

## 21. Fetch size là gì?

Ví dụ:

~~~sql
SELECT event_id, event_type, event_time, payload
FROM jdbc_batch_lab.events
ORDER BY event_id;
~~~

Trả về 50.000 rows. Một vòng Java:

~~~java
while (rs.next()) {
    // Xử lý một row.
}
~~~

**không tự bảo đảm driver chỉ giữ một row**. Trong cấu hình mặc định, pgJDBC có thể nhận toàn bộ kết quả về client trước hoặc trong khi duyệt.

~~~java
ps.setFetchSize(500);
~~~

chỉ ra kích thước nhóm rows muốn fetch khi driver dùng cursor mode phù hợp.

**`setFetchSize(500)` không có nghĩa SELECT chỉ trả 500 hàng.** Nó cũng không tương đương `LIMIT 500`.

## 22. Điều kiện pgJDBC dùng cursor fetch

Trong trường hợp pgJDBC server-side cursor/portal fetch thông thường, cần:

1. Connection **không ở autocommit mode** khi thực thi SELECT.
2. ResultSet/Statement **forward-only**.
3. Fetch size **dương**.
4. Query phù hợp, thường chỉ một statement.
5. Query protocol/driver settings hỗ trợ cursor fetch.
6. Transaction/statement/connection còn sống trong lúc duyệt.

### Vì sao autoCommit=false?

Cursor thường được đóng khi transaction kết thúc. Nếu SELECT nằm trong một transaction được autocommit ngay, driver không thể tiếp tục lấy nhiều batch từ portal theo cơ chế đang mong muốn.

Một hướng dẫn chỉ nói “`setFetchSize(100)` là đã streaming” mà không nhắc `autoCommit=false` **dễ gây hiểu lầm với PostgreSQL**.

## 23. Ví dụ thiếu điều kiện cursor

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement("""
         SELECT event_id, event_type
         FROM jdbc_batch_lab.events
         ORDER BY event_id
         """)) {

    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Kết quả đúng không chứng minh driver dùng cursor fetch.
        }
    }
}
~~~

Nếu connection vẫn `autoCommit=true`, pgJDBC không nhất thiết dùng server-side cursor fetch như mong đợi. Cần kiểm tra driver/version/query mode.

## 24. Ví dụ đúng: đọc ResultSet lớn

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class EventScanner {

    public static long scan(DataSource source)
            throws SQLException {

        String sql = """
            SELECT event_id, event_type, event_time
            FROM jdbc_batch_lab.events
            ORDER BY event_id
            """;

        try (Connection connection = source.getConnection()) {
            connection.setAutoCommit(false);
            connection.setReadOnly(true);

            try {
                long rows = 0L;

                try (PreparedStatement ps =
                        connection.prepareStatement(
                            sql,
                            ResultSet.TYPE_FORWARD_ONLY,
                            ResultSet.CONCUR_READ_ONLY)) {

                    ps.setFetchSize(500);

                    try (ResultSet rs = ps.executeQuery()) {
                        while (rs.next()) {
                            long id = rs.getLong("event_id");
                            String type = rs.getString("event_type");

                            consume(id, type);
                            rows++;
                        }
                    }
                }

                connection.commit();
                return rows;

            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }

    private static void consume(long id, String type) {
        // Demo xử lý nhanh, không giữ cả ResultSet vào List.
        if (id < 0) {
            throw new IllegalArgumentException(type);
        }
    }
}
~~~

Điểm chính:

- Connection thuộc riêng method này.
- `setAutoCommit(false)` mở điều kiện quan trọng cho pgJDBC cursor fetch.
- `TYPE_FORWARD_ONLY`, `CONCUR_READ_ONLY` phù hợp duyệt tuần tự.
- `setFetchSize(500)` chỉ định kích thước nhóm.
- `ResultSet` được xử lý trong scope của PreparedStatement/Connection.
- Chỉ commit sau khi duyệt xong, rollback khi lỗi.
- Không tích lũy mọi row vào List.

### Lưu ý read-only mode

`Connection.setReadOnly(true)` là một API hint/cấu hình có behavior phụ thuộc driver và `readOnlyMode`. Không thay quyền object của PostgreSQL hoặc tự bảo đảm mọi statement đều read-only; cần đối chiếu pgJDBC version/config.

### Transaction do framework quản lý

Nếu code chạy trong Spring-managed transaction hoặc caller đã sở hữu connection, không tự thay `autoCommit` và gọi `commit` mà không có hợp đồng transaction rõ. Mẫu trên dành cho method **sở hữu transaction riêng**.

## 25. fetchSize 0 và số dương

| Cấu hình | Ý nghĩa thông thường với pgJDBC |
| --- | --- |
| `setFetchSize(0)` | Mặc định, thường lấy toàn bộ kết quả thay vì cursor fetch từng nhóm |
| `setFetchSize(100)` | Nhóm khoảng 100 rows khi cursor mode phù hợp |
| `setFetchSize(500)` | Nhóm khoảng 500 rows khi cursor mode phù hợp |
| `setFetchSize(10000)` | Nhóm lớn hơn, ít lượt fetch hơn nhưng nhiều buffer hơn |
| Số âm | Không hợp lệ theo JDBC fetch size contract |

### Chọn số nào?

100, 500 hay 1000 là những điểm xuất phát thử nghiệm, không phải thông số “chuẩn”.

- Nhóm nhỏ → nhiều lượt fetch/round trips hơn.
- Nhóm lớn → có thể tăng peak memory.
- Row nhỏ 100 bytes khác row JSON 5 MB.
- Driver và query có giới hạn riêng.

**Đo heap, time to first row, total duration, round trips, network và pool occupancy** với dữ liệu thực tế.

## 26. fetchSize khác LIMIT và setMaxRows

~~~java
ps.setFetchSize(100);
~~~

không làm SQL query chỉ trả 100 rows.

Nếu người dùng chỉ được xem 100 rows, nên thể hiện giới hạn query:

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id
LIMIT 100;
~~~

`Statement.setMaxRows` có semantics JDBC riêng, nhưng SQL `LIMIT` thể hiện mục tiêu business rõ hơn.

**Fetch size = cách lấy kết quả. LIMIT = kích thước tập kết quả.**

## 27. Forward-only khác scrollable ResultSet

~~~java
connection.prepareStatement(
    sql,
    ResultSet.TYPE_FORWARD_ONLY,
    ResultSet.CONCUR_READ_ONLY
);
~~~

được thiết kế cho duyệt tuần tự bằng `next()`.

Nếu dùng `TYPE_SCROLL_INSENSITIVE`/`TYPE_SCROLL_SENSITIVE` để gọi `previous()`/`absolute()`, driver có thể phải buffer/materialize nhiều dữ liệu và không dùng cursor fetch như forward-only.

Nếu bạn đang xây export đọc một lần, đừng yêu cầu scrollable chỉ để tiện thử nghiệm.

## 28. Query/protocol có ảnh hưởng cursor mode

Một query duy nhất:

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id;
~~~

thường phù hợp.

Không gộp nhiều statements trong một chuỗi rồi mong driver mở cursor cho một SELECT:

~~~java
// Không nên dùng với kỳ vọng cursor fetch như một SELECT đơn.
String sql = "SET search_path TO jdbc_batch_lab; "
    + "SELECT * FROM events";
~~~

PgJDBC query protocol và properties như `preferQueryMode` có thể ảnh hưởng khả năng dùng portal/cursor. Đừng copy các property `useCursorFetch` của MySQL rồi dùng cho pgJDBC.

## 29. defaultRowFetchSize

PgJDBC có connection property `defaultRowFetchSize`:

~~~text
jdbc:postgresql://localhost:5432/training_db?defaultRowFetchSize=500
~~~

Nó đặt fetch size mặc định cho các statements theo driver/version tương ứng. Nhưng:

- Không tự tắt autocommit.
- Có thể tác động nhiều query không cần streaming.
- Framework có thể override fetch size riêng.
- Vẫn cần query và protocol phù hợp.

Nếu chỉ một báo cáo cần đọc lớn, cấu hình `ps.setFetchSize(500)` gần query sẽ dễ bảo trì hơn, trừ khi dự án muốn default toàn connection.

## 30. SQL cursor: DECLARE, FETCH, CLOSE

Một SQL cursor tường minh trong PostgreSQL:

~~~sql
BEGIN;

DECLARE event_cursor NO SCROLL CURSOR FOR
SELECT event_id, event_type, event_time
FROM jdbc_batch_lab.events
ORDER BY event_id;

FETCH FORWARD 5 FROM event_cursor;
FETCH FORWARD 5 FROM event_cursor;

CLOSE event_cursor;

COMMIT;
~~~

Giải thích:

- `DECLARE` mở cursor trong transaction.
- `FETCH FORWARD 5` lấy 5 rows tiếp theo.
- `CLOSE` đóng cursor khi hoàn tất.
- `COMMIT` kết thúc transaction.

Cursor không holdable thường bị đóng khi transaction kết thúc. Đóng sớm khi xong vẫn là thói quen tốt.

### PgJDBC ResultSet có cần DECLARE thủ công?

**Không.** Khi dùng `setFetchSize` đúng điều kiện, pgJDBC quản lý server-side cursor/portal qua protocol. SQL `DECLARE/FETCH` là cách bạn trực tiếp điều khiển cursor bằng SQL, không phải bước bắt buộc trước `ResultSet.next()`.

## 31. WITH HOLD qua COMMIT

PostgreSQL có SQL cursor `WITH HOLD`:

~~~sql
BEGIN;

DECLARE held_events CURSOR WITH HOLD FOR
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id;

COMMIT;

FETCH FORWARD 10 FROM held_events;

CLOSE held_events;
~~~

### Đánh đổi

Để giữ cursor qua COMMIT, server có thể **materialize tập kết quả vào bộ nhớ hoặc file tạm**, tạo chi phí server-side. Không xem `WITH HOLD` là streaming miễn phí.

JDBC ResultSet holdability và SQL cursor `WITH HOLD` có khác biệt API/driver; phải kiểm chứng trước khi kết hợp.

## 32. SQL cursor vs JDBC ResultSet

| Tiêu chí | SQL cursor | JDBC ResultSet với fetchSize |
| --- | --- | --- |
| Mở cursor | `DECLARE` do ứng dụng gửi | Driver quản lý nội bộ |
| Lấy rows | `FETCH n` | `rs.next()` |
| Đóng | `CLOSE` hoặc transaction end | `ResultSet.close`/Statement/Connection |
| Transaction | Theo PostgreSQL cursor semantics | Theo driver, transaction mode |
| Fetch size | Số rows mỗi `FETCH` | `Statement.setFetchSize` |
| Phù hợp Java row mapping | Cần tự viết SQL flow | Tự nhiên hơn |

Khi đọc tuần tự trong Java, ResultSet thường dễ dùng. Khi cần cursor SQL vì công việc database-side cụ thể, DECLARE/FETCH có ý nghĩa riêng.

## 33. Cursor không loại bỏ server-side Sort

Ví dụ:

~~~sql
SELECT event_type, COUNT(*) AS count_events
FROM jdbc_batch_lab.events
GROUP BY event_type
ORDER BY count_events DESC;
~~~

PostgreSQL có thể phải scan/aggregate nhiều rows trước khi trả các hàng đầu tiên. `setFetchSize(500)` không làm phép aggregate tự nhiên rẻ hơn.

Tương tự, nếu query có sort lớn, hash join, window function hoặc aggregate, driver fetch size không loại các bước đó.

**Trước khi tối ưu fetch, tối ưu query SQL bằng WHERE, projection, index và EXPLAIN.**

## 34. Snapshot, isolation và fetch

Với `READ COMMITTED`, mỗi SQL statement bình thường có snapshot theo semantics của isolation level. Nhưng một SELECT đang được duyệt qua portal không nên bị hiểu như **mỗi FETCH là một SELECT mới có thể thấy mọi commit mới**.

Với `REPEATABLE READ`, transaction snapshot được giữ theo quy tắc isolation, và transaction đọc lâu có thể giữ versions cần thiết.

### Hệ quả

- Fetch theo nhóm **không tự cập nhật** tập kết quả với mọi row mới.
- Cursor có thể cho trải nghiệm kết quả nhất quán hơn paging độc lập theo một query/snapshot.
- Muốn dữ liệu “mới nhất theo từng trang” phải định nghĩa semantics riêng.
- Nếu bảng liên tục UPDATE/DELETE, long-running snapshot có thể ảnh hưởng VACUUM cleanup.

## 35. Transaction dài ảnh hưởng VACUUM và pool

Một export 2 triệu rows mất 30 phút vì client tải chậm có thể giữ connection/transaction trong suốt quá trình.

Hệ quả:

- Giữ pool slot lâu.
- Backend/portal resources còn được sử dụng.
- Snapshot/xmin horizon có thể cản thu hồi dead tuples.
- Bloat và autovacuum lag tăng trong một số workload.
- Timeout/cancel xảy ra giữa chừng.
- Nếu query dùng `FOR UPDATE`, row locks có thể giữ lâu.
- Hệ thống trả lời chậm cho những request khác khi pool cạn.

Không stream trực tiếp một cursor vô hạn ra client internet không kiểm soát tốc độ mà không có deadline, concurrency limits và cancellation.

## 36. Streaming không đồng nghĩa Java ít RAM

Sai:

~~~java
List<Event> allEvents = new ArrayList<>();

while (rs.next()) {
    allEvents.add(mapEvent(rs));
}
~~~

Dù driver fetch 500 hàng mỗi lần, Java vẫn giữ mọi events.

Tốt hơn khi nhu cầu là xử lý một lượt:

~~~java
while (rs.next()) {
    Event event = mapEvent(rs);
    sink.write(event);
}
~~~

Nhưng `sink` cũng cần bounded buffering. Nếu sink ghi vào một queue vô hạn, memory vẫn tăng. Nếu sink rất chậm, transaction bị kéo dài.

**Kiểm soát cả driver buffering, Java mapping và downstream sink.**

## 37. Không trả ResultSet sau khi Connection đóng

Sai:

~~~java
public ResultSet loadEvents(DataSource ds) throws SQLException {
    try (Connection connection = ds.getConnection();
         PreparedStatement ps = connection.prepareStatement(
             "SELECT * FROM jdbc_batch_lab.events")) {
        return ps.executeQuery();
    }
}
~~~

Khi method thoát, statement/connection đã close. Caller không còn lifecycle hợp lệ để dùng ResultSet.

Cách đúng:

- Tiêu thụ ResultSet trong phạm vi connection.
- Hoặc API lazy iterator phải sở hữu/đóng connection được mô tả rõ.
- Không trả Java Stream từ repository khi transaction đã kết thúc trước lúc stream được duyệt.

**Resource ownership là một phần correctness, không chỉ tối ưu.**

## 38. SELECT cột cần thiết, đừng SELECT *

Nếu export chỉ cần event ID và loại:

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id;
~~~

Tốt hơn:

~~~sql
SELECT *
FROM jdbc_batch_lab.events;
~~~

khi payload 200 bytes hoặc nhiều MB mà không dùng.

Lợi ích:

- Ít bytes network.
- Ít memory driver/Java.
- Ít GC.
- Có thể tận dụng index tốt hơn trong một số query.
- Hạn chế lộ dữ liệu nhạy cảm không cần xuất.
- Ít phụ thuộc việc schema thêm cột.

Fetch size không bù được việc gửi các field không cần thiết.

## 39. Large Object, bytea và stream API

JDBC có `getBinaryStream` và `getCharacterStream`:

~~~java
try (java.io.Reader reader = rs.getCharacterStream("payload")) {
    char[] buf = new char[8192];
    while (reader.read(buf) != -1) {
        // Xử lý buffer theo business contract.
    }
}
~~~

**Không mặc định** mọi data type/driver trả dữ liệu từ PostgreSQL theo network streaming hoàn toàn mà không materialize một phần.

- `bytea` khác PostgreSQL Large Object (OID).
- Large Object API có transaction/lifecycle riêng.
- Một field rất lớn có thể tự tạo áp lực RAM dù `fetchSize=1`.
- Nếu payload không cần, không SELECT nó.
- Nếu cần tải file lớn, cân nhắc storage/stream API phù hợp.

## 40. Keyset pagination vs OFFSET

OFFSET:

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id
LIMIT 500 OFFSET 100000;
~~~

PostgreSQL có thể phải duyệt/bỏ qua nhiều hàng trước khi trả page. Dữ liệu INSERT/DELETE đồng thời còn có thể làm dịch vị trí.

Keyset:

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
WHERE event_id > 1000
ORDER BY event_id
LIMIT 500;
~~~

Ứng dụng giữ `last_seen_id`, lấy page tiếp theo với điều kiện lớn hơn ID cuối. Khi có B-tree index phù hợp, thường hiệu quả hơn offset sâu.

### Ưu điểm

- Không phải bỏ qua offset ngày càng lớn.
- Mỗi page có thể là một transaction ngắn.
- Dễ checkpoint/resume.
- Phù hợp background export jobs.

### Giới hạn

- Các page độc lập **không tự có cùng snapshot**.
- UPDATE/DELETE concurrent có thể thay đổi kết quả.
- ID tăng không bắt buộc trùng commit order.
- Nếu muốn “xuất đúng mọi event đã commit trong một khoảng” cần cutoff/watermark hoặc chiến lược consistency phù hợp.

## 41. Keyset theo hai cột

Nếu sắp theo thời điểm rồi ID:

~~~sql
SELECT event_id, event_time, event_type
FROM jdbc_batch_lab.events
WHERE (event_time, event_id) > (
    timestamptz '2026-01-01 12:00:00+00',
    1000
)
ORDER BY event_time, event_id
LIMIT 500;
~~~

Index lab:

~~~sql
CREATE INDEX idx_events_time_id
ON jdbc_batch_lab.events (event_time, event_id);
~~~

Đã được tạo ở phần lab. Nếu nhiều rows cùng `event_time`, ID giúp tạo tie-breaker duy nhất.

**Thiếu tie-breaker có thể bỏ sót các rows cùng timestamp.** Cần cùng thứ tự `WHERE` và `ORDER BY` trong keyset.

## 42. Cursor hay keyset?

| Tiêu chí | ResultSet cursor | Keyset pagination |
| --- | --- | --- |
| Một SELECT lớn duyệt tuần tự | Phù hợp | Có thể |
| Client memory bounded | Có nếu dùng đúng và sink bounded | Có nhờ LIMIT |
| Giữ transaction dài | Thường có | Thường không cần |
| Resume sau failure | Khó hơn | Có checkpoint |
| Snapshot của một query | Theo cursor/transaction semantics | Cần thiết kế thêm |
| Truy cập mạng client chậm | Có nguy cơ giữ DB pool lâu | Có thể tạo file rồi trả kết quả |
| Parallel export workers | Khó hơn | Có thể chia ranges |
| Dữ liệu đồng thời thay đổi | Theo snapshot query | Page consistency cần xử lý |
| Server query phải Sort lớn | Không loại Sort | Không tự loại Sort |

Không có một lựa chọn tốt nhất cho mọi ứng dụng. Export nhỏ vài giây dùng cursor rất hợp lý; job vài giờ cần resume thường nên cân nhắc keyset/CDC/file job.

## 43. Connection pool, backpressure và HTTP

Một pool có 20 connections. Nếu 20 request dùng cursor để xuất CSV qua client tải rất chậm, pool có thể hết connection cho request bình thường.

Dòng dữ liệu thực:

~~~text
PostgreSQL -> pgJDBC -> Java mapping -> CSV encoder
           -> HTTP buffer -> network -> browser/client
~~~

Nếu downstream chậm:

- Tăng buffer hoặc giữ connection.
- Transaction dài.
- Idle transaction có thể giữ snapshot.
- User khác chờ pool slot.
- Export bị cancel giữa chừng.

### Kiến trúc phù hợp khi export rất lớn

1. API tạo export job và trả job ID.
2. Worker có concurrency limit đọc theo cursor hoặc keyset.
3. Ghi file vào storage có chính sách bảo vệ dữ liệu.
4. Đóng DB connection sau khi job tạo file.
5. Client tải file độc lập với transaction DB.
6. Có expiration/retention và xóa file sau thời hạn.

Đánh đổi là quy trình phức tạp hơn nhưng giảm rủi ro giữ transaction lâu.

## 44. Timeout và cancellation

JDBC:

~~~java
ps.setQueryTimeout(60); // Seconds theo JDBC.
~~~

PostgreSQL trong transaction có thể đặt:

~~~sql
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '5s';
SET LOCAL idle_in_transaction_session_timeout = '30s';
~~~

Các timeout giải quyết vấn đề khác nhau:

| Timeout | Phạm vi |
| --- | --- |
| JDBC `setQueryTimeout` | Driver cố giới hạn statement |
| `statement_timeout` | Thời lượng statement ở server |
| `lock_timeout` | Chờ lock |
| `idle_in_transaction_session_timeout` | Session không hoạt động trong transaction |
| Pool connection timeout | Chờ mượn connection |
| Socket/network timeout | Hành vi đọc ghi network theo driver |

Không mặc định một `setQueryTimeout(60)` sẽ đảm bảo **toàn export gồm mọi lần fetch và sink.write** xong trong 60 giây. Cần deadline/job cancellation ở application.

Sau timeout/cancellation, transaction có thể cần rollback; luôn đóng ResultSet/Statement/Connection trong các đường lỗi.

## 45. Một callback API tự quản lý tài nguyên

~~~java
@FunctionalInterface
public interface EventConsumer {
    void accept(long id, String type) throws Exception;
}
~~~

Ví dụ:

~~~java
public static long scanEvents(
        javax.sql.DataSource ds,
        EventConsumer consumer
) throws Exception {

    String sql = """
        SELECT event_id, event_type
        FROM jdbc_batch_lab.events
        ORDER BY event_id
        """;

    try (java.sql.Connection c = ds.getConnection()) {
        c.setAutoCommit(false);

        try {
            long total = 0L;

            try (java.sql.PreparedStatement ps =
                    c.prepareStatement(
                        sql,
                        java.sql.ResultSet.TYPE_FORWARD_ONLY,
                        java.sql.ResultSet.CONCUR_READ_ONLY)) {

                ps.setFetchSize(500);

                try (java.sql.ResultSet rs = ps.executeQuery()) {
                    while (rs.next()) {
                        consumer.accept(
                            rs.getLong("event_id"),
                            rs.getString("event_type")
                        );
                        total++;
                    }
                }
            }

            c.commit();
            return total;

        } catch (Exception ex) {
            try {
                c.rollback();
            } catch (java.sql.SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        }
    }
}
~~~

Callback được gọi **khi DB transaction còn mở**. Không để callback gọi API mạng rất chậm, gửi email hoặc thực hiện side effects không rollback được rồi tưởng DB rollback sẽ thu hồi chúng.

Nếu cần resume, kiểm soát job và keyset checkpoint có thể phù hợp hơn.

## 46. SELECT FOR UPDATE và cursor dài

Ví dụ:

~~~sql
SELECT order_id, status
FROM jdbc_batch_lab.orders
WHERE status = 'new'
ORDER BY order_id
FOR UPDATE;
~~~

Trong transaction, thao tác có thể giữ row locks. Nếu duyệt 100.000 rows rất chậm, những locks có thể làm các session khác chờ.

Với queue-like workloads, có thể thiết kế batch ngắn:

~~~sql
SELECT order_id
FROM jdbc_batch_lab.orders
WHERE status = 'new'
ORDER BY order_id
FOR UPDATE SKIP LOCKED
LIMIT 100;
~~~

`SKIP LOCKED` phù hợp một số job queue nhưng có góc nhìn không nhất quán; không dùng như cách sửa mọi vấn đề concurrency.

Giữ lock ngắn và thực hiện cập nhật transactionally thường quan trọng hơn cố stream một cursor có khóa trong thời gian dài.

## 47. Monitoring transaction kéo dài

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Cần xem:

- Session `idle in transaction` lâu.
- Transaction start cũ.
- Wait events/locks.
- Pool active/wait metrics.
- Snapshot/replication slot liên quan nếu VACUUM không cleanup.

Không kết luận mọi VACUUM lag chỉ do cursor; replication slots, prepared transactions và long-running transactions khác cũng có thể giữ xmin horizon.

Cột `pg_stat_activity.query` có thể chứa SQL nhạy cảm; phân quyền monitoring theo security policy.

## 48. EXPLAIN không đo thời gian truyền dữ liệu tới Java

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, event_type, event_time
FROM jdbc_batch_lab.events
WHERE event_time >= timestamptz '2026-01-01 01:00:00+00'
ORDER BY event_time, event_id;
~~~

Xem:

- `Seq Scan`, `Index Scan`, `Bitmap Scan`.
- Rows removed by filter.
- Sort và temp disk.
- Buffers hit/read.
- Actual rows và execution time.

**EXPLAIN ANALYZE chạy query trong server**, không đo chính xác thời gian truyền ResultSet qua mạng, map object trong JVM và ghi CSV.

End-to-end:

~~~text
Server SQL execution
+ Network transfer/fetch trips
+ pgJDBC buffering
+ Java row mapping/GC
+ Sink/file/network latency
+ Pool wait
~~~

SQL server 200 ms vẫn có thể thành API export 30 giây nếu network/sink chậm.

## 49. Đo batch ghi như thế nào?

Benchmark nên giữ cố định:

- Bộ input, row size, constraints, indexes, triggers.
- Network path và connection pool.
- Server resource limits.
- Transaction isolation.
- Tình huống có/không duplicates.

Thử:

1. executeUpdate từng row.
2. PreparedStatement batch 100.
3. Batch 500 và 1.000.
4. `reWriteBatchedInserts=false/true`.
5. COPY vào staging + merge nếu phù hợp.

Đo:

| Metric | Ý nghĩa |
| --- | --- |
| Rows thực sự COMMIT/s | Throughput đúng nghiệp vụ |
| Batch latency p50/p95 | Độ trễ mỗi transaction |
| Driver/client heap/GC | Chi phí ứng dụng |
| DB CPU/IO/WAL | Chi phí server |
| Replication lag | Tác động downstream |
| Locks/deadlocks | Cạnh tranh ghi |
| Error/retry/duplicate | Tính ổn định |
| Total job completion | Hiệu quả end-to-end |

**Không benchmark trên production bằng INSERT lớn nếu không có kế hoạch và quyền vận hành phù hợp.**

## 50. Đo streaming như thế nào?

Thử những dataset:

- 1.000 rows × 100 bytes.
- 100.000 rows × 100 bytes.
- 100.000 rows × 10 KB.
- 1.000 rows có payload rất lớn.

Với mỗi dataset:

- So fetchSize = 0, 100, 500, 1000.
- Giữ nguyên SQL, driver version, transaction mode.
- Xác nhận cursor conditions đúng.
- Đo heap peak, time-to-first-row, total duration, network bytes.
- Đo transaction lifetime, pool occupancy, GC.
- Đo sink throughput và cancellation.
- Kiểm tra số hàng và tính đúng thứ tự.

**Fetch size lớn nhất không mặc định là tốt nhất; time to first row và tổng throughput có thể đi theo hai hướng khác nhau.**

## 51. Lỗi thường gặp khi batch JDBC

1. **addBatch xong quên executeBatch** nên không có SQL được thực thi.
2. **Tưởng executeBatch tự commit** khi autoCommit=false.
3. **Dùng autoCommit=true cho import cần atomicity toàn bộ**, dẫn đến partial result.
4. **Batch một triệu rows không chia nhóm**, gây memory pressure.
5. **Commit mỗi row** và tăng overhead.
6. **Nhầm batch size với transaction chunk size.**
7. **Coi counts.length là số rows đã INSERT**, bỏ qua conflicts.
8. **Không xử lý SUCCESS_NO_INFO/0/EXECUTE_FAILED**.
9. **Không rollback sau BatchUpdateException**.
10. **Cứ tiếp tục SQL trên transaction aborted**.
11. **Retry không có idempotency**, tạo duplicate.
12. **Tạo idempotency key mới cho mỗi retry**.
13. **Dùng double cho tiền**.
14. **Ghép SQL từ input không tin cậy**.
15. **Bật rewrite rồi nghĩ mọi INSERT đều được gộp**.
16. **Không test mapping generated keys với batch/RETURNING**.
17. **Nghĩ COPY có ON CONFLICT trực tiếp**.
18. **Chỉ đo driver call time**, không đo commit/WAL/locks.
19. **Tắt constraints/triggers trong benchmark nhưng production vẫn cần**.
20. **Không phân loại SQLSTATE trước khi retry**.

## 52. Lỗi thường gặp khi đọc kết quả lớn

1. **setFetchSize > 0 nhưng vẫn autoCommit=true**, không bảo đảm cursor mode.
2. **Dùng scrollable ResultSet**, làm buffer nhiều.
3. **Gộp nhiều SQL statements trong một query** mà vẫn kỳ vọng cursor fetch.
4. **Dùng config của driver khác** cho pgJDBC.
5. **Nhầm fetchSize với LIMIT**.
6. **Trả ResultSet sau khi connection đóng**.
7. **Trả lazy Stream ra ngoài scope transaction**.
8. **Tích lũy mọi row trong List**, mất lợi ích streaming.
9. **SELECT *** và kéo các cột dữ liệu lớn/nhạy cảm.
10. **Dùng fetchSize 1000 với row payload hàng MB**.
11. **Giữ cursor khi HTTP client tải chậm**, cạn connection pool.
12. **Không đóng resources khi exception**.
13. **Không rollback khi timeout/cancel**.
14. **Dùng WITH HOLD mà quên server materialization cost**.
15. **Dùng OFFSET sâu để xuất file nhiều triệu rows**.
16. **Keyset không có tie-breaker**, làm mất các rows cùng timestamp.
17. **Giả định sequence ID đồng nghĩa commit order**.
18. **Không định nghĩa snapshot consistency cho export**.
19. **Giữ SELECT FOR UPDATE lâu trong cursor**.
20. **Chỉ đo thời gian SQL server, bỏ network/mapping/sink**.
21. **Không giới hạn concurrency export jobs**.
22. **Không ngừng DB scan khi client disconnect**.
23. **Nghĩ mỗi fetch thấy mọi commit mới nhất**, bỏ qua isolation.
24. **Không có checkpoint/retry** cho job chạy hàng giờ.
25. **Không kiểm soát quyền export dữ liệu nhạy cảm**.

## 53. Bài tập thực hành có đáp án

Sử dụng schema `jdbc_batch_lab` đã tạo; các ví dụ DML cần chạy trong database lab và rollback nếu chỉ thử nghiệm.

### Bài 1. Batch và fetch size khác gì?

**Đáp án:** Batch xử lý nhiều commands/parameter sets; fetch size xác định nhóm rows được lấy khi duyệt một ResultSet theo driver.

### Bài 2. addBatch đã ghi row chưa?

**Đáp án:** Chưa bảo đảm. Nó thêm command/parameter set vào batch, cần executeBatch.

### Bài 3. executeBatch tự commit?

**Đáp án:** Không nếu autoCommit=false; transaction caller phải commit hoặc rollback.

### Bài 4. Vì sao dùng PreparedStatement?

**Đáp án:** Bind input tránh SQL injection và giúp tái sử dụng cùng SQL template.

### Bài 5. Tạo một batch INSERT

~~~java
try (PreparedStatement ps = connection.prepareStatement("""
    INSERT INTO jdbc_batch_lab.orders (
        idempotency_key, customer_ref, amount
    ) VALUES (?, ?, ?)
    """)) {

    ps.setString(1, "exercise-1");
    ps.setString(2, "customer-A");
    ps.setBigDecimal(3, new BigDecimal("9.99"));

    ps.addBatch();
    ps.executeBatch();
}
~~~

**Đáp án:** Một parameter set đã được thực thi; transaction cần được quản lý riêng nếu tắt autocommit.

### Bài 6. SUCCESS_NO_INFO nghĩa gì?

**Đáp án:** Command thành công nhưng driver không báo được số hàng chính xác.

### Bài 7. Update count 0 có thể nghĩa gì?

**Đáp án:** Command không tác động row; ví dụ ON CONFLICT DO NOTHING gặp key trùng.

### Bài 8. BatchUpdateException làm gì?

**Đáp án:** Phân loại SQLSTATE/update counts, rollback transaction theo hợp đồng, không coi các commands trước lỗi đã commit.

### Bài 9. Chia executeBatch mỗi 500, commit cuối cùng có atomic toàn job?

**Đáp án:** Có thể, nếu tất cả cùng một transaction và commit duy nhất cuối.

### Bài 10. Commit mỗi nhóm 500 có atomic cả job?

**Đáp án:** Không, các nhóm đã commit giữ nguyên nếu nhóm sau thất bại.

### Bài 11. reWriteBatchedInserts là JDBC standard?

**Đáp án:** Không. Đây là property pgJDBC cho một số batch INSERT.

### Bài 12. Generated keys trong batch có thể map theo input tuyệt đối?

**Đáp án:** Không tự giả định; cần kiểm tra driver/SQL behavior và dùng correlation key khi cần.

### Bài 13. Khi nào dùng COPY?

**Đáp án:** Bulk load lớn, thường từ stream/file, có thể vào staging để validate/merge.

### Bài 14. COPY trực tiếp có ON CONFLICT như INSERT không?

**Đáp án:** Không; thường COPY vào staging rồi INSERT SELECT ON CONFLICT.

### Bài 15. setFetchSize(100) có trả đúng 100 rows?

**Đáp án:** Không, nó không giới hạn tổng ResultSet.

### Bài 16. Điều kiện chính của pgJDBC cursor fetch?

**Đáp án:** autoCommit=false, forward-only ResultSet, fetchSize dương và query/protocol phù hợp.

### Bài 17. Vì sao autoCommit=true có thể làm pgJDBC fetch all?

**Đáp án:** Cursor/portal thông thường đóng khi transaction kết thúc nên driver không giữ được cursor để fetch tiếp.

### Bài 18. setFetchSize(0) thường nghĩa gì trong pgJDBC?

**Đáp án:** Default/all-result behavior, không yêu cầu fetch theo cursor từng nhóm dương.

### Bài 19. TYPE_FORWARD_ONLY phù hợp khi nào?

**Đáp án:** Khi duyệt một chiều bằng next(), phù hợp đọc tuần tự lớn và cursor behavior.

### Bài 20. Viết SQL cursor lấy 10 rows

~~~sql
BEGIN;

DECLARE c NO SCROLL CURSOR FOR
SELECT event_id, event_type
FROM jdbc_batch_lab.events
ORDER BY event_id;

FETCH FORWARD 10 FROM c;

CLOSE c;
COMMIT;
~~~

**Đáp án:** Cursor được khai báo trong transaction, FETCH 10, đóng rồi commit.

### Bài 21. WITH HOLD không mất cursor sau commit?

**Đáp án:** Có thể trong ngữ cảnh hỗ trợ, nhưng server có thể materialize kết quả và tốn temp disk/memory.

### Bài 22. Vì sao không trả ResultSet sau khi Connection close?

**Đáp án:** ResultSet cần Statement/Connection còn sống để duyệt.

### Bài 23. Driver fetch từng nhóm nhưng List vẫn tăng RAM?

**Đáp án:** Đúng. List tích lũy tất cả rows ở application.

### Bài 24. Vì sao SELECT * nguy hiểm cho export?

**Đáp án:** Truyền nhiều cột/payload không cần thiết, tốn memory/network và có thể lộ PII.

### Bài 25. OFFSET sâu chậm vì sao?

**Đáp án:** Server có thể phải đi qua/bỏ nhiều rows trước khi trả page.

### Bài 26. Keyset sau event_id 1000

~~~sql
SELECT event_id, event_type
FROM jdbc_batch_lab.events
WHERE event_id > 1000
ORDER BY event_id
LIMIT 500;
~~~

**Đáp án:** Lấy tối đa 500 rows có ID lớn hơn 1000, có thể dùng index PK.

### Bài 27. Nếu ORDER BY event_time, làm sao không bỏ mất timestamp trùng?

**Đáp án:** Thêm event_id unique làm tie-breaker, dùng WHERE (event_time,event_id) và ORDER BY cùng thứ tự.

### Bài 28. Sequence ID có luôn theo thứ tự commit không?

**Đáp án:** Không; transaction lấy sequence trước có thể commit sau transaction khác.

### Bài 29. Vì sao cursor dài ảnh hưởng VACUUM?

**Đáp án:** Transaction/snapshot có thể giữ các row versions cũ cần cho khả năng nhìn thấy dữ liệu, cản cleanup.

### Bài 30. fetchSize=1 có chắc nhanh nhất?

**Đáp án:** Không; quá nhiều lượt fetch/round trips.

### Bài 31. Row 5 MB với fetchSize 1000 có rủi ro gì?

**Đáp án:** Kích thước một nhóm có thể rất lớn, tăng heap/network pressure.

### Bài 32. Query rất chậm có nên chỉ tăng fetchSize?

**Đáp án:** Không; tối ưu plan/index/WHERE trước, fetchSize chủ yếu giảm client buffering.

### Bài 33. setQueryTimeout(60) có đảm bảo toàn bộ file export xong trong 60 giây?

**Đáp án:** Không nhất thiết; các lượt fetch và sink có semantics thời gian khác. Cần job deadline/cancel riêng.

### Bài 34. Vì sao streaming HTTP dễ cạn pool?

**Đáp án:** Client chậm giữ cursor/transaction/connection lâu, nhiều concurrent exports chiếm hết pool.

### Bài 35. SELECT FOR UPDATE với cursor dài có vấn đề gì?

**Đáp án:** Có thể giữ locks lâu, chặn các update khác.

### Bài 36. Ngoài SQL execution time cần đo gì?

**Đáp án:** Network, driver fetch, heap/GC, Java mapping, sink latency, pool wait, transaction duration, WAL và retries.

### Bài 37. SQLSTATE 40001 nên retry thế nào?

**Đáp án:** Rollback và retry **toàn transaction** có bounded backoff, tính lại quyết định nghiệp vụ.

### Bài 38. Mất kết nối ngay sau COMMIT?

**Đáp án:** Commit outcome có thể không rõ. Kiểm tra trạng thái theo idempotency key trước khi retry.

## 54. Checklist triển khai

- [ ] Phân biệt workload ghi nhiều commands với đọc một ResultSet lớn.
- [ ] Dùng PreparedStatement/bind parameters.
- [ ] Dùng addBatch/executeBatch khi nhiều parameter sets cùng SQL.
- [ ] Có transaction boundary và rollback policy rõ.
- [ ] Chọn batch size bằng benchmark, không dồn vô hạn.
- [ ] Phân biệt chunk batch và chunk commit.
- [ ] Xử lý BatchUpdateException/update counts chính xác.
- [ ] Dùng idempotency key cho unknown commit outcome/retry.
- [ ] Không retry lỗi validation vô hạn.
- [ ] Test reWriteBatchedInserts theo version/statement.
- [ ] Kiểm tra generated keys mapping trong batch.
- [ ] Cân nhắc COPY + staging cho bulk load.
- [ ] Không bỏ constraints/triggers chỉ để tăng tốc.
- [ ] Dùng autoCommit=false cho pgJDBC cursor fetch.
- [ ] Dùng TYPE_FORWARD_ONLY và CONCUR_READ_ONLY.
- [ ] Đặt fetchSize dương và query một statement phù hợp.
- [ ] Không nhầm fetchSize với LIMIT.
- [ ] Đọc ResultSet trong scope connection/transaction.
- [ ] Đóng ResultSet/Statement/Connection và rollback khi lỗi.
- [ ] Không trả lazy ResultSet ra ngoài resource owner.
- [ ] Không tích lũy mọi hàng vào List nếu cần bounded memory.
- [ ] Chỉ SELECT cột cần thiết.
- [ ] Đo row size khi chọn fetchSize.
- [ ] Giới hạn số rows/thời gian/concurrency export.
- [ ] Có cancel/timeout và cleanup sau client disconnect.
- [ ] Theo dõi pool active/wait và long-running xact_start.
- [ ] Tránh giữ SELECT FOR UPDATE locks quá lâu.
- [ ] Dùng keyset nếu cần job resume và transaction ngắn.
- [ ] Có tie-breaker ổn định và cutoff/consistency policy.
- [ ] Không đồng nhất sequence ID với commit order.
- [ ] Đo EXPLAIN riêng, end-to-end Java riêng.
- [ ] Xem WAL/replication lag và lock contention cho batch ghi.
- [ ] Test trên PostgreSQL/pgJDBC/JDK version thực tế.
- [ ] Không log secret/PII từ parameters hoặc ResultSet.
- [ ] Không chạy batch DML lớn/EXPLAIN ANALYZE UPDATE bừa bãi trên production.

## 55. Tài liệu chính thức

Đối chiếu đúng PostgreSQL, pgJDBC và JDK version đang sử dụng:

- [pgJDBC: Cursor-based results](https://jdbc.postgresql.org/documentation/query/#getting-results-based-on-a-cursor) — autoCommit=false, fetch size, forward-only và điều kiện cursor.
- [pgJDBC: Connection parameters](https://jdbc.postgresql.org/documentation/use/#connection-parameters) — reWriteBatchedInserts, defaultRowFetchSize và các properties.
- [pgJDBC documentation](https://jdbc.postgresql.org/documentation/) — hướng dẫn chính thức của driver.
- [Java PreparedStatement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/PreparedStatement.html) — parameters, addBatch và executeBatch.
- [Java Statement](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html) — fetch size, counts, result set type.
- [Java Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html) — autoCommit, commit, rollback, savepoints, isolation.
- [Java ResultSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/ResultSet.html) — cursor lifecycle, getters, navigation.
- [Java BatchUpdateException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/BatchUpdateException.html) — lỗi batch/update counts.
- [PostgreSQL DECLARE](https://www.postgresql.org/docs/current/sql-declare.html) — cursor SQL.
- [PostgreSQL FETCH](https://www.postgresql.org/docs/current/sql-fetch.html) — lấy hàng từ cursor.
- [PostgreSQL CLOSE](https://www.postgresql.org/docs/current/sql-close.html) — đóng cursor.
- [PostgreSQL COPY](https://www.postgresql.org/docs/current/sql-copy.html) — bulk load/export.
- [PostgreSQL Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html) — snapshots và concurrency.
- [PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html) — row locks, SKIP LOCKED.
- [PostgreSQL EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html) — query plan và ANALYZE.
- [PostgreSQL Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — pg_stat_activity và transaction states.
- [PostgreSQL Runtime Client Settings](https://www.postgresql.org/docs/current/runtime-config-client.html) — timeouts và session settings.

Các links `/current/` dẫn tới tài liệu PostgreSQL hiện hành; thuộc tính driver có thể đổi giữa các phiên bản. Hãy kiểm chứng trong môi trường triển khai của dự án.

## 56. Tổng kết

**JDBC batch và JDBC cursor fetch giải quyết hai phía khác nhau của việc xử lý dữ liệu lớn: gửi nhiều lệnh tới PostgreSQL và nhận nhiều hàng từ PostgreSQL.**

1. **`addBatch()/executeBatch()`** giảm overhead gửi các bộ tham số; chúng không tự quyết định atomicity.
2. **Batch chunk khác transaction chunk.** Nếu commit nhiều nhóm, job có thể thành công một phần; cần checkpoint và idempotency.
3. **BatchUpdateException/update counts không tự chứng minh rows đã commit.** Phải rollback và xác minh business result.
4. **`reWriteBatchedInserts` là tối ưu riêng pgJDBC**, cần test điều kiện rewrite và mapping generated keys.
5. **`COPY` phù hợp bulk load**, thường kết hợp staging/merge khi cần validation và conflict handling.
6. **`setFetchSize(n)` không phải LIMIT.** Với pgJDBC, cursor fetch thường cần **`autoCommit=false`**, forward-only ResultSet, fetchSize dương và query/protocol phù hợp.
7. **SQL DECLARE/FETCH khác cursor/portal do pgJDBC quản lý**; Java thường chỉ cần ResultSet khi driver đã cấu hình đúng.
8. **Streaming không đồng nghĩa ít RAM** nếu application vẫn giữ toàn bộ rows hoặc từng row quá lớn.
9. **Cursor có chi phí transaction/snapshot/pool**, cần deadline và giới hạn concurrency để không ảnh hưởng VACUUM và các request khác.
10. **Keyset pagination** phù hợp job có checkpoint/resume, nhưng snapshot consistency/concurrent writes cần một thiết kế riêng.
11. **Tối ưu thực tế phải đo query, server, driver, Java và sink end-to-end**, thay vì chỉ chọn số batch/fetch lớn nhất.

Khi xác định rõ **đơn vị batch, transaction boundary, vòng đời cursor và cách tiêu thụ ResultSet**, ứng dụng Java có thể ghi và đọc PostgreSQL quy mô lớn mà vẫn kiểm soát bộ nhớ, tính nhất quán và tài nguyên vận hành.

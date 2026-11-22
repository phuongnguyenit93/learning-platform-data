# Phát hiện truy vấn chậm và giao dịch giữ khóa lâu trong JDBC

Một API Java gọi `PreparedStatement.executeQuery()` và mất 15 giây để trả kết quả. Lập trình viên có thể nghĩ rằng câu SQL đã chạy 15 giây và cần thêm chỉ mục. Nhưng độ trễ đó cũng có thể do **chờ lấy kết nối từ pool**, **đợi một transaction khác nhả khóa**, **driver fetch hàng theo nhiều đợt**, hoặc **mã Java xử lý kết quả quá chậm**. Ngược lại, một câu `UPDATE` hoàn thành trong 5 ms có thể nằm trong **transaction không được commit suốt vài phút**, tiếp tục giữ khóa và chặn những request khác.

Vì vậy, vận hành JDBC cần quan sát **cả truy vấn chậm và giao dịch giữ khóa lâu**, đồng thời phân biệt chúng. Chủ đề thuộc chương **Giám sát vận hành** của module JDBC, kết nối thực hành truy cập cơ sở dữ liệu qua `DataSource`, `PreparedStatement`, `ResultSet` với các tín hiệu giám sát từ database.

Mục tiêu của bài học:

- Phân rã độ trễ JDBC thành thời gian chờ pool, thực thi SQL, fetch/mapping và vòng đời transaction.
- Xác định truy vấn chậm bằng metric ứng dụng, slow-query log và thống kê phía DBMS.
- Phân biệt query đang chạy lâu, query đang **đợi khóa**, và session `idle in transaction` nhưng vẫn giữ khóa.
- Sử dụng các công cụ PostgreSQL như `pg_stat_activity`, `pg_blocking_pids(...)`, `pg_locks`, `pg_stat_statements` và `EXPLAIN` theo cách an toàn.
- Liên hệ các quan sát với những API JDBC thực tế: `setQueryTimeout(...)`, `commit()`, `rollback()`, `Connection.close()` và connection pool.
- Xây dựng cảnh báo, quy trình xử lý sự cố và kiểm thử tái hiện lock wait có kiểm soát.

**Phạm vi minh họa:** các SQL chẩn đoán chi tiết dùng PostgreSQL. Nguyên tắc áp dụng cho JDBC nói chung, nhưng tên view, quyền truy cập và các cơ chế lock/timeout cần đối chiếu với từng DBMS và phiên bản driver.

## 1. Ba hiện tượng nhìn giống nhau từ ứng dụng

Hãy xem ba request đều mất 10 giây:

| Hiện tượng | JDBC có thể biểu hiện | Điều xảy ra thực tế | Cách tìm nguyên nhân |
|---|---|---|---|
| **Query tốn công** | `executeQuery()` hoặc `rs.next()` mất lâu | Quét nhiều hàng, join/sort đắt, I/O lớn | `EXPLAIN`, thống kê query, buffer I/O |
| **Query chờ khóa** | `executeUpdate()` bị chặn, chưa trả kết quả | Transaction khác đang giữ khóa xung đột | Wait event, blocking PID, transaction age |
| **Chờ connection pool** | `dataSource.getConnection()` mất lâu | Pool hết connection rảnh vì request khác dùng lâu/rò rỉ | Active/idle/pending, borrow latency, connection hold time |

Còn một hiện tượng rất quan trọng:

**Giao dịch giữ khóa lâu không nhất thiết đang thực thi câu SQL chậm.** Sau `UPDATE`, ứng dụng có thể chờ một lời gọi HTTP hoặc đơn giản quên `commit()`. SQL đã kết thúc nhưng transaction vẫn mở, khiến các khóa có thể tiếp tục tồn tại.

```text
Request A                                 Request B
------------------------------            -------------------------
borrow Connection A                       borrow Connection B
setAutoCommit(false)
UPDATE accounts WHERE id=7
  -> SQL xong trong 5 ms
                                       UPDATE accounts WHERE id=7
                                          -> chờ khóa 10 giây
gọi HTTP bên ngoài 10 giây
commit()
                                       UPDATE tiếp tục khi khóa được nhả
```

Nếu chỉ lấy danh sách “SQL chạy lâu” thì request A có thể không xuất hiện như một query active chậm, dù chính nó là **blocker**. Ngược lại, request B xuất hiện như query lâu nhưng chưa chắc cần thêm index.

## 2. Đặt tên đúng cho các khoảng thời gian

Một request dùng JDBC có thể trải qua nhiều giai đoạn:

```text
HTTP / message / job
    |
    +-- [A] chờ mượn Connection từ DataSource/pool
    |
    +-- [B] tạo PreparedStatement, bind tham số
    |
    +-- [C] executeQuery()/executeUpdate()
    |           |
    |           +-- database parse / plan / execute
    |           +-- đợi row/table/advisory lock
    |           +-- network / response đầu tiên
    |
    +-- [D] ResultSet.next() + getXxx() + ánh xạ dữ liệu
    |           |
    |           +-- có thể fetch thêm dữ liệu từ database
    |
    +-- [E] tính toán nghiệp vụ trong transaction
    |
    +-- [F] commit() hoặc rollback()
    |
    +-- [G] close() logical Connection -> trả về pool
```

Một bộ metric có ích:

| Metric | Điểm đo trong Java | Diễn giải |
|---|---|---|
| `db.pool.acquire.duration` | Trước/sau `DataSource.getConnection()` | Thời gian chờ pool và mở/kiểm tra kết nối |
| `db.query.execute.duration` | Trước/sau `Statement.execute...()` | Thời gian thực hiện lời gọi JDBC, **không luôn bằng toàn bộ server execution** |
| `db.result.fetch.duration` | Từ khi có `ResultSet` đến khi đọc hết hàng cần thiết | Fetch qua mạng và ánh xạ hàng |
| `db.rows.read` | Số lần `rs.next()` trả `true` | Khối lượng kết quả bên Java |
| `db.transaction.duration` | Từ lúc bắt đầu transaction tới commit/rollback | Thời gian transaction ở phía ứng dụng |
| `db.transaction.commit.duration` | Trước/sau `commit()` | Thời gian xác nhận transaction |
| `db.pool.connection.usage` | Lúc borrow đến close | Thời gian giữ connection logic |

Các tên trên là **gợi ý thiết kế metric**, không phải bộ tên chuẩn bắt buộc của JDBC/Micrometer.

### `executeQuery()` trả nhanh chưa chắc fetch nhanh

Tùy driver và kiểu result set, `executeQuery()` có thể trả về sau khi đã nhận một phần dữ liệu; những lời gọi `ResultSet.next()` sau đó tiếp tục tải các đợt hàng mới. Driver khác có thể nạp sẵn nhiều dữ liệu trước khi trả `ResultSet`.

Vì vậy, chỉ ghi duration quanh `executeQuery()` có thể bỏ sót bottleneck của ứng dụng đọc hàng triệu bản ghi. Mặt khác, thời gian `fetch + mapping` còn bao gồm CPU của Java; không được gán toàn bộ khoảng đó cho database.

### `System.nanoTime()` và thời gian tường (wall clock)

Trong Java, dùng `System.nanoTime()` để tính **khoảng thời gian đã trôi qua** vì đây là đồng hồ đơn điệu phù hợp hơn `System.currentTimeMillis()` cho đo duration. Khi cần ghép timeline đa hệ thống, log thêm timestamp tường theo hệ thống log/tracing. Không trừ các giá trị `nanoTime()` lấy từ **hai JVM khác nhau**.

## 3. Đo truy vấn JDBC từ phía ứng dụng

Ví dụ Java 17+ sau dùng một bảng đơn hàng:

```sql
CREATE TABLE sales_orders (
    id           BIGINT PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL
);
```

Các đoạn SQL schema ở đây dành cho PostgreSQL. Mục đích là đo nhiều giai đoạn khi lấy danh sách đơn của một tenant.

### 3.1. Mẫu đo pool, execute và fetch

```java
import javax.sql.DataSource;
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.logging.Level;
import java.util.logging.Logger;

public final class OrderQueryProbe {
    private static final Logger LOG =
            Logger.getLogger(OrderQueryProbe.class.getName());

    private final DataSource dataSource;

    public OrderQueryProbe(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record OrderSummary(long id, BigDecimal totalAmount) {}

    public List<OrderSummary> findRecentOrders(
            long tenantId, int limit) throws SQLException {

        if (tenantId <= 0 || limit <= 0 || limit > 500) {
            throw new IllegalArgumentException("Tham số không hợp lệ");
        }

        final String queryName = "orders.findRecentByTenant";
        final String sql =
                "SELECT id, total_amount " +
                "FROM sales_orders " +
                "WHERE tenant_id = ? " +
                "ORDER BY created_at DESC, id DESC LIMIT ?";

        long started = System.nanoTime();
        long borrowNs = -1;
        long executeNs = -1;
        long fetchNs = -1;
        int rowsRead = 0;
        boolean success = false;

        try (Connection connection = dataSource.getConnection()) {
            borrowNs = System.nanoTime() - started;

            try (PreparedStatement ps =
                         connection.prepareStatement(sql)) {
                ps.setLong(1, tenantId);
                ps.setInt(2, limit);

                // Một lớp bảo vệ; không phải deadline cứng mọi trường hợp.
                ps.setQueryTimeout(5);

                long executeStarted = System.nanoTime();
                try (ResultSet rs = ps.executeQuery()) {
                    executeNs = System.nanoTime() - executeStarted;

                    long fetchStarted = System.nanoTime();
                    List<OrderSummary> result = new ArrayList<>();

                    while (rs.next()) {
                        result.add(new OrderSummary(
                                rs.getLong("id"),
                                rs.getBigDecimal("total_amount")));
                        rowsRead++;
                    }

                    fetchNs = System.nanoTime() - fetchStarted;
                    success = true;
                    return result;
                }
            }
        } catch (SQLException failure) {
            LOG.log(Level.WARNING,
                    "JDBC query failed: " + queryName
                    + ", SQLState=" + failure.getSQLState()
                    + ", vendorCode=" + failure.getErrorCode());
            throw failure;
        } finally {
            long totalNs = System.nanoTime() - started;

            // Ví dụ log gọn để học: hệ thống thực nên xuất
            // histogram/trace theo queryName thay vì log mọi request.
            LOG.log(Level.INFO, String.format(Locale.ROOT,
                    "query=%s success=%s rows=%d " +
                    "borrow_ms=%.3f execute_ms=%.3f " +
                    "fetch_ms=%.3f total_ms=%.3f",
                    queryName, success, rowsRead,
                    millis(borrowNs), millis(executeNs),
                    millis(fetchNs), millis(totalNs)));
        }
    }

    private static double millis(long ns) {
        return ns < 0 ? -1.0 : ns / 1_000_000.0;
    }
}
```

Đối với mã này:

- `borrow_ms` gồm chờ pool và công việc `getConnection()` của implementation.
- `execute_ms` đo lời gọi Java `executeQuery()`, có thể gồm gửi SQL, chờ lock, thực thi và nhận phần dữ liệu đầu.
- `fetch_ms` đo vòng `rs.next()` và ánh xạ giá trị; tùy driver, nó cũng gồm các lần fetch mạng bổ sung.
- `total_ms` gồm thêm chuẩn bị, đóng tài nguyên và phần logging không nằm trong các giai đoạn khác.
- Giá trị `-1` có nghĩa **chưa đi đến giai đoạn đó** vì lỗi; không ghi nó như một duration đo được bằng 0.
- `rowsRead` cho biết số hàng đã xử lý thành công; khi lỗi giữa chừng, đó có thể chỉ là số hàng đã xử lý trước lỗi.

**Không ghi raw customer ID, tenant ID nhạy cảm hoặc toàn bộ SQL đã nội suy tham số vào metric label.** Khi cần theo dõi nhiều tenant, chỉ thêm dimension có cardinality được kiểm soát và phù hợp chính sách riêng tư. Dùng tên query ổn định như `orders.findRecentByTenant` để tổng hợp số liệu.

### 3.2. Vì sao không đo mỗi request một lần rồi kết luận lỗi DB?

Giả sử log của một request:

```text
borrow_ms=8900
execute_ms=12
fetch_ms=3
total_ms=8920
```

DB query có thể chạy rất nhanh; vấn đề chính là **pool wait**. Tăng index trên `sales_orders` không trực tiếp giúp được nếu pool hết connection vì request trước giữ transaction chờ dịch vụ bên ngoài.

Ngược lại:

```text
borrow_ms=2
execute_ms=12000
fetch_ms=4
total_ms=12010
```

Ở đây cần kiểm tra xem `execute_ms` chậm do **DB đang làm việc** hay **đang chờ lock**. Hai nguyên nhân này cần cách khắc phục khác nhau.

Một ví dụ khác:

```text
borrow_ms=2
execute_ms=8
fetch_ms=15000
total_ms=15020
```

Có thể đang tải rất nhiều hàng, mạng chậm hoặc mapper Java nặng. Hãy nhìn số hàng, kích thước dữ liệu và hoạt động `ResultSet.next()` trước khi quyết định thay index.

## 4. Theo dõi transaction duration tách khỏi query duration

Thời gian gọi `executeUpdate()` không đại diện cho toàn bộ thời gian giữ khóa. Một transaction giữ khóa đến khi kết thúc bằng `commit()`/`rollback()` (hoặc theo ngữ nghĩa lock cụ thể của DBMS). Vì vậy, cần theo dõi **thời điểm bắt đầu và thời điểm kết thúc transaction**.

Một mẫu JDBC thuần:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;
import java.util.logging.Logger;

public final class InventoryReservation {
    private static final Logger LOG =
            Logger.getLogger(InventoryReservation.class.getName());

    private final DataSource dataSource;

    public InventoryReservation(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void reserve(long itemId, int quantity)
            throws SQLException {

        if (itemId <= 0 || quantity <= 0) {
            throw new IllegalArgumentException("Đầu vào không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            long transactionStarted = System.nanoTime();
            String outcome = "UNKNOWN";

            try {
                try (PreparedStatement ps = connection.prepareStatement(
                        "UPDATE inventory_items " +
                        "SET available = available - ? " +
                        "WHERE id = ? AND available >= ?")) {

                    ps.setInt(1, quantity);
                    ps.setLong(2, itemId);
                    ps.setInt(3, quantity);
                    ps.setQueryTimeout(4);

                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                                "Không có bản ghi hoặc không đủ tồn kho");
                    }
                }

                // Không làm HTTP call / sleep / chờ người dùng ở đây.
                connection.commit();
                outcome = "COMMITTED";

            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                    outcome = "ROLLED_BACK";
                } catch (SQLException rollbackFailure) {
                    outcome = "UNKNOWN";
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            } finally {
                long elapsed = System.nanoTime() - transactionStarted;
                LOG.info("operation=inventory.reserve outcome="
                        + outcome + " transaction_ms="
                        + TimeUnit.NANOSECONDS.toMillis(elapsed));
            }
        }
    }
}
```

Ví dụ này giả định bảng `inventory_items(id, available)` tồn tại. `transactionStarted` được ghi sau `setAutoCommit(false)` để đo phạm vi do ứng dụng khai báo; **thời điểm `xact_start` của PostgreSQL có thể khác**, vì DBMS đánh dấu transaction khi nó thực sự bắt đầu xử lý SQL và tùy cách driver khởi tạo transaction.

Đặc biệt, nếu `commit()` báo lỗi do mất kết nối, kết quả ghi có thể **chưa biết chắc**. Một nỗ lực rollback sau đó không chứng minh rằng commit đã không xảy ra. Hãy gắn request ID/idempotency key với nghiệp vụ ghi quan trọng và đối soát trước khi tự động retry.

Trong ứng dụng dùng **Spring `@Transactional`**, không nên lặp lại `setAutoCommit(false)`, `commit()` và `rollback()` trong DAO nếu Spring transaction manager đang sở hữu connection. Đặt đo duration ở biên transaction/service hoặc dùng instrumentation phù hợp để không thay đổi chính sách commit của framework.

## 5. Từ slow-query log đến dấu hiệu cần điều tra

Một **slow query** không có một ngưỡng tuyệt đối đúng cho mọi sản phẩm. Truy vấn dashboard trả 20 hàng mất 800 ms có thể bất thường, trong khi báo cáo tổng hợp hàng chục triệu bản ghi mất 2 giây có thể nằm trong mục tiêu đã chấp nhận.

Nên thu thập:

| Tín hiệu | Ý nghĩa | Dùng để |
|---|---|---|
| Số lần gọi query theo tên/fingerprint | Tần suất | Phát hiện N+1 và workload bất thường |
| `p50` / `p95` / `p99` thời gian | Độ trễ điển hình và đuôi | Xem SLA/SLO và regression |
| Tổng thời gian tiêu thụ | Query nào “ăn” nhiều thời gian DB nhất | Ưu tiên tối ưu |
| Số hàng trả / số hàng bị quét | Query có lọc hiệu quả không | Phát hiện over-fetch |
| Thời gian chờ pool | Tài nguyên ứng dụng đang thiếu | Điều chỉnh transaction/pool |
| Thời gian transaction mở | Khả năng giữ lock và snapshot lâu | Phát hiện transaction kéo dài |
| Lock wait count/duration | Có contention không | Điều tra blocker |
| Lỗi timeout/deadlock/serialization | Tác động tới nghiệp vụ | Alert và kiểm thử retry |

### Phân biệt log query chậm của Java và của DBMS

- Log **phía ứng dụng** đo đường gọi JDBC, có thể gồm pool wait, network, fetch và Java work tùy phạm vi instrumentation.
- Log **phía DBMS** tập trung vào hoạt động SQL trên server, thường không tính thời gian mượn connection ở pool và không bao gồm toàn bộ serialization của HTTP response.
- `EXPLAIN ANALYZE` là một phép thực thi có instrumentation, **không thay thế** telemetry dài hạn ở production.

Độ lệch giữa hai nguồn không phải tự nó là lỗi. Phải biết khoảng thời gian mỗi nguồn đo và nơi bắt đầu/kết thúc.

## 6. Bật slow-query log PostgreSQL một cách có kiểm soát

PostgreSQL hỗ trợ một số cấu hình hữu ích:

```conf
# Ví dụ giá trị cân nhắc trong cấu hình PostgreSQL:
log_min_duration_statement = '500ms'
log_lock_waits = on
deadlock_timeout = '1s'
```

Ý nghĩa:

- `log_min_duration_statement` ghi những câu SQL vượt ngưỡng thời gian được cấu hình; `500ms` ở đây chỉ là **giá trị minh họa**.
- `log_lock_waits = on` yêu cầu ghi các lần đợi lock vượt ngưỡng `deadlock_timeout` trong trường hợp PostgreSQL hỗ trợ.
- `deadlock_timeout` còn liên quan đến tần suất kiểm tra deadlock, không đơn thuần là thời gian “query được phép chờ” trước khi bị hủy.

**Không tự thay đổi cấu hình toàn cluster trên production chỉ để làm bài thực hành.** Một số thiết lập đòi quyền quản trị và reload/restart tùy tham số, trong khi log ở ngưỡng thấp có thể tạo lượng dữ liệu lớn và vô tình ghi câu SQL chứa dữ liệu nhạy cảm. Làm việc với DBA/SRE, áp dụng chính sách retention, mask/redaction và sampling phù hợp.

Các ngưỡng có thể bắt đầu bằng SLO hoặc baseline hiện tại, ví dụ query OLTP thường dưới 100 ms nhưng alert khi p95 tăng bất thường liên tục. Không thiết kế cảnh báo chỉ bằng một con số 500 ms cho mọi query.

### Dữ liệu từ log cần được chuẩn hóa

Trong log/tracing, nên gắn:

- `query_name` hoặc fingerprint chuẩn hóa, không dùng nguyên SQL đã nội suy giá trị làm metric label.
- `operation`, service, environment, database role (nếu an toàn).
- Correlation ID / trace ID để nối request với JDBC và database log, khi hạ tầng hỗ trợ.
- Duration, số hàng, SQLSTATE và outcome.
- `application_name` có kiểm soát trên session database, nếu driver hỗ trợ.

Tránh đưa password, connection URL có credential, token, email, nội dung thanh toán hoặc toàn bộ tham số người dùng vào log. Việc bật SQL logging của một thư viện có thể làm lộ giá trị bind; phải kiểm tra cấu hình thực tế.

## 7. Tìm session đang chạy lâu bằng `pg_stat_activity`

Trên PostgreSQL, view `pg_stat_activity` mô tả các backend/session hiện tại. Một truy vấn read-only để xem active query và transaction dài:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    wait_event_type,
    wait_event,
    clock_timestamp() - xact_start AS transaction_age,
    CASE
        WHEN state = 'active' THEN
            clock_timestamp() - query_start
        ELSE NULL
    END AS active_query_age,
    clock_timestamp() - state_change AS time_in_state
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
  AND (
        state = 'active'
        OR (
            xact_start IS NOT NULL
            AND clock_timestamp() - xact_start > interval '30 seconds'
        )
      )
ORDER BY transaction_age DESC NULLS LAST;
```

Vì sao dùng `clock_timestamp()`? Trong PostgreSQL, `now()`/`transaction_timestamp()` cố định tại thời điểm bắt đầu **transaction của chính phiên đang quan sát**. Nếu công cụ giám sát tái sử dụng một transaction kéo dài, `now()` có thể làm tuổi query/transaction bị tính từ mốc không còn cập nhật. `clock_timestamp()` trả thời điểm hiện tại theo wall clock tại lúc đánh giá.

### Những cột cần hiểu

| Cột | Ý nghĩa | Lưu ý |
|---|---|---|
| `pid` | Process/backend ID của phiên DB | Không đồng nghĩa Java thread ID hoặc HTTP request ID |
| `application_name` | Nhãn client do phiên cung cấp | Hữu ích để nhóm service, nhưng cần cấu hình và giới hạn cardinality |
| `state` | `active`, `idle`, `idle in transaction`, ... | `idle in transaction` có thể giữ transaction và khóa dù không chạy SQL |
| `wait_event_type` | Loại sự kiện đang chờ | `Lock` là một manh mối lock wait, không phải mọi query chậm |
| `wait_event` | Sự kiện cụ thể | Đọc cùng loại wait event và phiên bản PostgreSQL |
| `xact_start` | Thời điểm transaction hiện tại bắt đầu | Có thể NULL khi không có transaction hiện hành |
| `query_start` | Thời điểm query hiện tại bắt đầu, hoặc query cuối ở trạng thái khác | **Không lấy query age của session idle như đang chạy SQL** |
| `state_change` | Lần cuối trạng thái thay đổi | Giúp xác định phiên idle trong transaction bao lâu |

`pg_stat_activity` cũng có cột `query`, nhưng văn bản SQL có thể bị cắt theo cấu hình và chứa dữ liệu nhạy cảm. Trên dashboard diện rộng, **không mặc định hiển thị/log query text đầy đủ**. Chỉ dùng khi cần điều tra với quyền và chính sách bảo mật phù hợp.

Quyền xem thông tin về session khác phụ thuộc role và phiên bản PostgreSQL. Tài khoản giám sát có thể cần quyền quan sát như `pg_read_all_stats` hoặc `pg_monitor` theo chính sách DBA; không cấp superuser cho ứng dụng chỉ để lấy metric.

## 8. Phân biệt `active`, `idle` và `idle in transaction`

Ba trạng thái rất khác nhau:

### `active`

Session đang thực thi một query hoặc xử lý lệnh. Nếu `wait_event_type = 'Lock'`, có thể đang **chờ khóa**. Nếu `wait_event_type` là I/O hoặc loại khác, nguyên nhân có thể khác. Query `active` lâu cũng có thể do CPU, scan hoặc thao tác DBMS dài.

### `idle`

Session đang chờ lệnh tiếp theo và **không có transaction đang hoạt động theo cách hiển thị của DBMS**. Một pooled connection rảnh có thể ở trạng thái này; bản thân `idle` không phải bằng chứng có leak hoặc lock contention.

### `idle in transaction`

Session không thực thi query tại thời điểm quan sát, **nhưng transaction vẫn mở**. Có thể do:

- Code JDBC gọi `setAutoCommit(false)` rồi quên `commit()/rollback()`.
- Service thực hiện `UPDATE` và sau đó chờ HTTP request bên ngoài.
- Một `@Transactional` bao quanh xử lý lâu, gọi API bên ngoài hoặc chờ I/O khác.
- Lỗi bị catch/nuốt, khiến transaction không kết thúc đúng cách.
- Đọc `ResultSet` rất chậm trong transaction và để connection mở.

Không phải mọi `idle in transaction` đều đang giữ khóa gây chặn; điều đó phụ thuộc lệnh đã chạy và loại lock. Tuy nhiên, nó có thể giữ snapshot và những tài nguyên khác, gây ảnh hưởng VACUUM/maintenance. Vì vậy, **tuổi transaction cao là một tín hiệu điều tra**, không tự động chứng minh có blocker.

### Vì sao `query_start` của session idle dễ gây hiểu sai?

`query_start` ở trạng thái không active có thể phản ánh thời điểm **query cuối cùng**. Dùng `clock_timestamp() - query_start` rồi gán nhãn “query đã chạy 40 phút” có thể đánh lừa người vận hành: câu SQL đã kết thúc từ lâu, còn session đang idle trong transaction. Hãy xem đồng thời `state`, `state_change` và `xact_start`.

## 9. Tìm ai đang chặn ai bằng `pg_blocking_pids(...)`

Khi một query đang đợi lock, điều tra **blocking session** thường hiệu quả hơn việc xem kế hoạch query của chính waiter.

```sql
SELECT
    waiting.pid AS waiting_pid,
    waiting.application_name AS waiting_app,
    waiting.state AS waiting_state,
    waiting.wait_event_type,
    waiting.wait_event,
    clock_timestamp() - waiting.query_start
        AS waiting_query_age,
    blocker.pid AS blocking_pid,
    blocker.application_name AS blocking_app,
    blocker.state AS blocking_state,
    clock_timestamp() - blocker.xact_start
        AS blocking_transaction_age
FROM pg_stat_activity AS waiting
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(waiting.pid)) AS blocked_by(pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = blocked_by.pid
WHERE waiting.datname = current_database()
ORDER BY waiting_query_age DESC;
```

Ví dụ diễn giải:

```text
waiting_pid = 22015
waiting_app = checkout-service
wait_event_type = Lock
waiting_query_age = 00:00:12

blocking_pid = 21988
blocking_app = batch-worker
blocking_state = idle in transaction
blocking_transaction_age = 00:05:20
```

Đây là **minh họa**, không phải dữ liệu được thu thập trên server thật.

Trong tình huống này, vấn đề trước mắt có thể là batch worker đã `UPDATE` một hàng rồi bỏ transaction mở. Chỉ thêm index cho query checkout thường **không giải quyết được** khóa mà worker đang giữ.

### Giới hạn khi dùng `pg_blocking_pids`

- Truy vấn có thể trả nhiều blocking PID cho một waiter; hệ thống có thể có **chuỗi blocker**.
- Một PID chặn nhiều request, tạo hiện tượng hàng đợi lan rộng.
- Có những trường hợp liên quan prepared transaction, parallel worker hoặc lock manager mà việc ghép PID với một row `pg_stat_activity` cần kiểm tra thêm.
- Kết quả là **ảnh chụp tức thời**; một transaction có thể kết thúc ngay sau khi truy vấn.
- Lấy thông tin lock/wait quá thường xuyên trên server bận có thể tạo chi phí giám sát. Dùng polling hợp lý hoặc truy vấn khi có tín hiệu sự cố.

Dùng `pg_blocking_pids(...)` để tìm các blocker thực tế thường đáng tin cậy hơn việc tự join `pg_locks` chỉ theo relation, vì quy tắc xung đột khóa và thứ tự chờ phức tạp hơn nhiều.

## 10. `pg_locks` giúp giải thích loại khóa đang chờ

Khi cần xem thêm thông tin, PostgreSQL cung cấp `pg_locks`:

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name,
    transactionid,
    virtualtransaction
FROM pg_locks
WHERE NOT granted
ORDER BY pid, locktype, mode;
```

Thông tin nổi bật:

- `locktype`: loại đối tượng khóa, như relation, transactionid, tuple, advisory...
- `mode`: chế độ khóa mà session yêu cầu.
- `granted=false`: yêu cầu khóa **đang chờ**, chưa được cấp.
- `relation`: ID relation khi có; có thể NULL đối với các kiểu lock khác.
- `transactionid`: hữu ích với một số lock wait ở mức transaction.

**Một session đang chờ row lock không nhất thiết chỉ hiện dưới `locktype='tuple'`**. Trong PostgreSQL, xung đột khi cập nhật hàng có thể xuất hiện dưới dạng chờ transaction ID của transaction đang giữ phiên bản hàng. Không được kết luận “không thấy tuple lock tức là không bị row lock”.

Không tự tạo logic “mọi session có `granted=true` trên cùng bảng đều là blocker” bằng join thô: nhiều loại khóa trên cùng relation tương thích với nhau. Khi cần xác định quan hệ chặn, bắt đầu bằng `pg_blocking_pids` rồi dùng `pg_locks` để giải thích.

### Điều gì khiến transaction giữ khóa lâu?

- DML `UPDATE`/`DELETE` làm phát sinh lock cho đến khi transaction kết thúc.
- `SELECT ... FOR UPDATE` hoặc cơ chế row locking tương tự.
- DDL như `ALTER TABLE` có thể đòi khóa mạnh, gây tắc nghẽn khi chạy cùng workload.
- Stored procedure có thể mở rộng phạm vi công việc và giữ transaction.
- Advisory lock cấp **transaction** hoặc cấp **session** có vòng đời khác nhau.
- Transaction chờ người dùng, HTTP call, message hoặc thiết bị ngoại vi thay vì commit sớm.

**Session-level advisory lock** của PostgreSQL có thể còn tồn tại sau commit/rollback; trường hợp này khác row lock thông thường. Cần đối chiếu loại khóa và API đã dùng trước khi đưa ra kết luận “chỉ cần rollback là sẽ nhả mọi khóa”.

## 11. Một kịch bản khóa dễ tái hiện trong môi trường test

Để học cách quan sát, có thể dùng **ba kết nối SQL riêng** (A, B và monitor C) trên PostgreSQL thử nghiệm. Không tạo lock contention kiểu này trên production.

Bảng:

```sql
CREATE TABLE inventory_items (
    id        BIGINT PRIMARY KEY,
    available INTEGER NOT NULL
);

INSERT INTO inventory_items(id, available)
VALUES (1, 100);
```

**Kết nối A** bắt đầu transaction, cập nhật và cố ý chưa commit:

```sql
BEGIN;

UPDATE inventory_items
SET available = available - 1
WHERE id = 1;

-- Chỉ trong lab: giữ transaction mở để quan sát.
-- Không chạy COMMIT/ROLLBACK ngay.
```

**Kết nối B** thử cập nhật cùng hàng:

```sql
BEGIN;

UPDATE inventory_items
SET available = available - 1
WHERE id = 1;

-- Lệnh có thể phải đợi A nhả lock.
```

**Kết nối C** chạy truy vấn `pg_stat_activity` và `pg_blocking_pids(...)` ở phần 7–9. Kỳ vọng thường thấy:

- B đang `active` và chờ `Lock`.
- A có thể là `idle in transaction` nếu SQL UPDATE của A đã kết thúc và đang chờ lệnh tiếp theo.
- B bị chặn bởi A.

Sau đó ở **A**:

```sql
ROLLBACK;
```

B có thể tiếp tục khi lock được nhả. Kết thúc **B**:

```sql
ROLLBACK;
```

Hãy rollback cả hai trong lab để trả dữ liệu về trạng thái ban đầu. Nếu B có timeout trước khi A rollback, PostgreSQL có thể đưa transaction của B vào trạng thái lỗi; cần rollback B trước khi thực hiện lệnh mới. Không để phiên test `idle in transaction` sau khi hoàn thành thử nghiệm.

### Bài học từ kịch bản này

Truy vấn B bị chặn không nhất thiết có execution plan tệ. Dữ liệu chỉ một hàng và index đã có khóa chính, nhưng B vẫn phải đợi A kết thúc transaction. Khi incident thực tế xảy ra, **xác định blocker và lý do transaction sống lâu** là bước ưu tiên trước khi tối ưu câu SQL của waiter.

## 12. Quan sát query tích lũy với `pg_stat_statements`

`pg_stat_activity` phù hợp với tình trạng **đang diễn ra**. Để tìm những mẫu SQL tiêu tốn nhiều thời gian trong một khoảng hoạt động, PostgreSQL có extension `pg_stat_statements` nếu DBA đã cấu hình.

Ví dụ truy vấn trên môi trường có extension/view tương ứng:

```sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    max_exec_time,
    rows
FROM pg_stat_statements
WHERE dbid = (
    SELECT oid
    FROM pg_database
    WHERE datname = current_database()
)
ORDER BY total_exec_time DESC
LIMIT 20;
```

Các trường có ý nghĩa:

| Trường | Điều cần đọc |
|---|---|
| `calls` | Số lần mẫu statement được thực thi trong khoảng thống kê |
| `total_exec_time` | Tổng thời gian thực thi do extension ghi nhận (ms) |
| `mean_exec_time` | Thời gian thực thi trung bình (ms) |
| `max_exec_time` | Lần thực thi tốn thời gian nhất được ghi nhận |
| `rows` | Tổng số hàng được báo trong thống kê |
| `queryid` | ID nhận diện mẫu truy vấn theo cơ chế PostgreSQL |

**Không đọc `mean_exec_time` một mình.** Một query mất trung bình 2 ms nhưng chạy 2 triệu lần có thể chiếm nhiều tài nguyên hơn query mất 500 ms chỉ chạy vài lần. Ngược lại, p99 của một truy vấn quan trọng có thể cao bất thường dù average thấp; `pg_stat_statements` và histogram ở ứng dụng bổ sung cho nhau.

`pg_stat_statements` cần cài đặt và cấu hình thích hợp; tùy phiên bản có yêu cầu `shared_preload_libraries` và restart, cũng như quyền đọc thống kê. Không giả định extension luôn có sẵn hoặc ứng dụng được quyền tự tạo trên production.

Thống kê tích lũy có thể được reset, và mẫu query được chuẩn hóa theo cách PostgreSQL quy định. Nó không tự cho biết **một request cụ thể** đã bị blocker nào chặn; cần kết hợp với wait sampling, logging và traces.

## 13. Khi nào xem `EXPLAIN` thay vì lock?

Sau khi xác nhận query đang **thực thi công việc DB nặng** chứ không chỉ bị chờ lock, hãy điều tra execution plan:

```sql
EXPLAIN
SELECT id, total_amount
FROM sales_orders
WHERE tenant_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Trong lab:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, total_amount
FROM sales_orders
WHERE tenant_id = 7
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

Các điểm cần đọc:

- `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`, `Sort`, `Hash Join`, `Nested Loop`.
- `estimated rows` so với `actual rows`, nhất là khi số hàng ước lượng lệch xa thực tế.
- `Rows Removed by Filter` và `Index Cond`.
- `loops` ở các toán tử con; một node đọc ít hàng mỗi vòng nhưng chạy nhiều lần vẫn có thể rất đắt.
- `Buffers`: shared hit/read, temp read/write, để hiểu áp lực cache/I/O.
- Thời gian planner/execute và tác động của `LIMIT`, `ORDER BY`, index.

**`EXPLAIN ANALYZE` thực sự thực thi SQL.** Với `UPDATE`, `DELETE` hoặc `INSERT`, nó có thể thay đổi dữ liệu, chạy trigger và giữ khóa. Không thử trực tiếp trên production chỉ để xem kế hoạch; dùng môi trường đo có kiểm soát hoặc phương pháp read-only phù hợp.

Nếu thấy query đang `wait_event_type='Lock'` với blocker rõ ràng, hãy xử lý **vòng đời transaction** trước. Index đôi khi giảm thời gian giữ lock bằng cách giảm công việc, nhưng không thay thế việc commit/rollback đúng hạn.

## 14. Pool đầy có thể là hậu quả của transaction giữ khóa

Một thread đang chờ lock vẫn có thể **giữ một connection trong pool**. Khi nhiều thread cùng bị chặn, số connection active tăng, số connection idle giảm, và request mới bắt đầu chờ `DataSource.getConnection()`. Sự cố tại database vì thế lan thành pool starvation ở ứng dụng.

```text
Transaction A giữ khóa lâu
       |
       v
Nhiều UPDATE khác chờ lock
       |
       v
Mỗi request vẫn giữ Connection
       |
       v
Pool active đạt max, pending tăng
       |
       v
Request mới chờ lấy Connection
       |
       v
Timeout pool / HTTP timeout hàng loạt
```

Với pool như HikariCP, những tín hiệu thường có thể quan sát qua MBeans/Micrometer hoặc cơ chế monitoring được cấu hình:

- Số connection **active**, **idle**, **total**.
- Số thread/request **pending** đang chờ connection.
- Thời gian chờ mượn connection.
- Thời gian connection được giữ trong một lần borrow.
- Connection timeout, validation failure, connection được thay thế.
- Cảnh báo leak detection (nếu bật): một connection được giữ vượt ngưỡng, **không phải bằng chứng chắc chắn đã rò rỉ**.

Các metric/tên thuộc tính cụ thể phụ thuộc pool và phiên bản. Đừng suy rằng cứ tăng `maximumPoolSize` sẽ giải quyết gốc rễ: nếu database đang bị blocker, nhiều connection hơn có thể tạo **thêm nhiều query chờ khóa**, làm tải xấu đi.

## 15. Ba tầng timeout và tác dụng thực tế

Một số team nhầm timeout với cách sửa lock lâu. JDBC có nhiều ranh giới timeout khác nhau:

| Cơ chế | Ngăn điều gì? | Giới hạn |
|---|---|---|
| Timeout borrow của pool | Chờ quá lâu để lấy `Connection` | Không kết thúc transaction đang giữ khóa trong DB |
| `Statement.setQueryTimeout(seconds)` | Yêu cầu driver giới hạn thời gian thực thi statement | Không phải hard deadline xuyên mọi DBMS/network |
| PostgreSQL `statement_timeout` | Giới hạn thời gian xử lý statement ở DBMS | Không tự bảo đảm rollback toàn transaction do ứng dụng quản lý |
| PostgreSQL `lock_timeout` | Giới hạn thời gian chờ lấy khóa | Không giảm CPU/I/O của query chạy không bị lock |
| PostgreSQL `idle_in_transaction_session_timeout` | Ngắt session idle trong transaction quá ngưỡng | Biện pháp bảo vệ cuối, gây lỗi connection và cần xử lý tại app/pool |
| `Connection.setNetworkTimeout(...)` | Timeout hoạt động mạng của JDBC connection | Không đồng nghĩa giới hạn query hay lock wait |

Ví dụ `PreparedStatement`:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE inventory_items SET available = available - ? " +
        "WHERE id = ? AND available >= ?")) {

    ps.setInt(1, quantity);
    ps.setLong(2, itemId);
    ps.setInt(3, quantity);

    ps.setQueryTimeout(3); // Giây, theo khả năng driver.
    int affected = ps.executeUpdate();
}
```

Khi `executeUpdate()` ném `SQLTimeoutException` hoặc một `SQLException` liên quan timeout, **không mặc định connection đang ở trạng thái sạch**. Với PostgreSQL, statement lỗi trong transaction thường khiến transaction hiện hành không thể tiếp tục bình thường trước khi rollback. Ứng dụng phải quản lý `rollback()` hoặc để transaction manager thực hiện.

### Biện pháp PostgreSQL cần quản trị cẩn trọng

Một môi trường có thể cấu hình:

```conf
# Ví dụ phòng vệ, không phải giá trị mặc định khuyên áp dụng mọi nơi:
statement_timeout = '30s'
lock_timeout = '5s'
idle_in_transaction_session_timeout = '60s'
```

Các ngưỡng này cần cân bằng với batch job, migration, transaction hợp lệ, driver và pool. Nếu database đóng session vì idle-in-transaction timeout, pool phải phát hiện connection hỏng và thay thế; ứng dụng cần xử lý ngoại lệ, không coi timeout là kết quả nghiệp vụ thành công.

**Timeout chỉ giới hạn tác hại, không sửa nguồn gốc** như transaction bao quanh I/O ngoài DB, khóa DDL, SQL chọn quá nhiều hàng hoặc retry không kiểm soát.

## 16. Hành động khẩn cấp: cancel khác terminate

Trong PostgreSQL có hai thao tác quản trị thường được nhắc đến:

```sql
-- Minh họa dành cho người có quyền vận hành.
-- Chỉ sử dụng PID đã được xác minh trong incident.
SELECT pg_cancel_backend(12345);

-- Mạnh hơn: chấm dứt cả phiên backend.
SELECT pg_terminate_backend(12345);
```

Khác biệt:

| Hành động | Mục tiêu | Hệ quả cần đánh giá |
|---|---|---|
| `pg_cancel_backend(pid)` | Yêu cầu hủy query hiện hành | Session có thể còn mở; transaction có thể rơi vào trạng thái lỗi và cần rollback |
| `pg_terminate_backend(pid)` | Yêu cầu chấm dứt backend/session | Connection JDBC mất hiệu lực; DB có thể phải rollback transaction và giải phóng tài nguyên |
| Yêu cầu service commit/rollback hợp lệ | Kết thúc transaction qua đường ứng dụng | Thường an toàn hơn nếu còn kiểm soát được request và tính toàn vẹn nghiệp vụ |

**Không tự động kill mọi session trên một ngưỡng transaction age.** Một transaction có thể đang làm công việc hợp lệ; hủy một blocker có thể khiến rollback nhiều dữ liệu rất lâu, ảnh hưởng các request khác hoặc gây lỗi nghiệp vụ. Cần xác minh chủ sở hữu, loại transaction, mức độ tác động, quan hệ blocker và phương án khôi phục.

Với một session `idle in transaction` đang giữ khóa làm gián đoạn hệ thống, runbook vận hành có thể xem xét terminate sau khi đã liên hệ service owner, đánh giá rủi ro và được cấp quyền phù hợp. Kết quả thành công của hàm quản trị không bảo đảm ứng dụng đã hiểu đúng kết quả giao dịch.

## 17. Quy trình xử lý sự cố có thể thực hành

Một runbook ngắn để điều tra “API checkout đột ngột tăng lên 20 giây”:

### Bước 1 — Xác nhận tác động và phạm vi

- Xem latency p95/p99, error rate, timeout và số request bị ảnh hưởng.
- Tách theo `query_name`, operation và service, tránh dashboard gộp tất cả SQL.
- Kiểm tra có deploy, migration, thay đổi schema/index hoặc tải tăng gần thời điểm bắt đầu hay không.

### Bước 2 — Xem độ trễ nằm ở đâu

- Nếu **pool acquire** lớn: xem active/pending/usage và các request giữ connection lâu.
- Nếu **execute** lớn: xem wait event, blocker, query plan và DB CPU/I/O.
- Nếu **fetch** lớn: xem số hàng trả, fetch size, kết nối mạng và mapper Java.
- Nếu **transaction duration** lớn: xem thời gian ở service giữa các lệnh SQL, các cuộc gọi remote và đường commit/rollback.

### Bước 3 — Xác định waiter và blocker

Dùng `pg_stat_activity` và `pg_blocking_pids(...)`, lưu:

- PID của waiter/blocker, service/application name.
- Query age, transaction age, state, wait event.
- Số lượng session bị cùng một blocker chặn.
- Có DDL/migration hoặc job batch đang hoạt động không.
- Có session `idle in transaction` nhưng đã `UPDATE` trước đó không.

### Bước 4 — Đặt giả thuyết và sửa đúng nguyên nhân

| Bằng chứng | Giả thuyết ưu tiên | Hướng xử lý |
|---|---|---|
| `Lock` wait, blocker `idle in transaction` | Transaction chưa kết thúc | Sửa biên transaction, bỏ I/O ngoài DB, rollback/commit đúng |
| DB active query CPU/IO cao, không chờ Lock | Query plan hoặc data volume | `EXPLAIN`, index, statistics, giới hạn dữ liệu |
| Query nhanh, pool wait cao | Pool starvation/leak hoặc hold time lớn | Đo connection usage, đóng tài nguyên, xử lý blocker |
| Execute nhanh, fetch rất lâu | Quá nhiều hàng hoặc Java/mạng chậm | Phân trang, chọn ít cột, tối ưu ánh xạ |
| Timeouts tăng sau migration | DDL lock, schema change hoặc plan regression | Kiểm tra migration/lock và kế hoạch mới |

### Bước 5 — Giảm tác động và xác minh

Nếu cần can thiệp vận hành, ưu tiên cách giải phóng transaction hợp lệ qua application; các hành động cancel/terminate phải được thực hiện theo quyền và runbook. Sau đó xác minh:

1. Blocking PID/lock wait giảm.
2. Pool pending và borrow latency trở về mức bình thường.
3. Query p95/p99 cải thiện.
4. Error rate và retry volume không tiếp tục tăng.
5. Không có giao dịch nghiệp vụ bị trùng do retry sau kết quả commit chưa rõ.

### Bước 6 — Phòng ngừa tái diễn

- Giảm phạm vi `@Transactional`; không thực hiện HTTP call chậm bên trong transaction nếu tránh được.
- Kết thúc transaction JDBC bằng `commit()/rollback()` rõ ràng và đóng connection bằng `try-with-resources` khi app sở hữu.
- Giới hạn query/lock timeout hợp lý; thiết lập idle-in-transaction policy nếu đáp ứng yêu cầu.
- Bổ sung dashboard query fingerprint, transaction age, blockers và pool metrics.
- Tạo integration test tái hiện lock wait và transaction cleanup.
- Đánh giá index/statistics khi bằng chứng chỉ ra query thật sự tốn công.

## 18. Gắn thông tin từ Java đến PostgreSQL đúng cách

Khi incident trải qua nhiều tầng, cần một cách nối tín hiệu:

```text
HTTP trace / request ID
       |
       v
Service operation: inventory.reserve
       |
       v
JDBC query name: inventory.decrementIfAvailable
       |
       +--> pool borrow latency
       +--> execute duration / rows affected
       +--> transaction duration
       |
       v
PostgreSQL application_name + backend PID + DB wait metrics
```

`application_name` của PostgreSQL có thể được thiết lập qua thuộc tính kết nối do driver hỗ trợ (ví dụ cấu hình `ApplicationName` của pgJDBC), nhưng đó là **khả năng đặc thù driver**, không phải một thuộc tính chuẩn chung của mọi JDBC driver. Nên dùng tên service ổn định, tránh tạo application name riêng cho mỗi request gây cardinality và overhead.

`pg_backend_pid()` có thể giúp xác minh physical session trong môi trường test/điều tra. Nhưng pool tái sử dụng session, nên PID không xác định duy nhất một request qua mọi thời điểm. Correlation cần gắn với **timestamp, trace context và khoảng thời gian borrow/transaction**, không chỉ một PID.

Một số công cụ proxy/observability có thể gắn trace ID vào SQL comment, nhưng làm như vậy có thể ảnh hưởng query normalization/plan cache hoặc lộ dữ liệu nếu comment chứa thông tin nhạy cảm. Không thêm comment tùy tiện vào mọi SQL chỉ để dễ tìm kiếm.

## 19. Các DBMS khác có công cụ quan sát tương tự nhưng không cùng cú pháp

JDBC là API chung, còn cơ chế theo dõi slow query và lock wait thuộc DBMS.

| DBMS | Công cụ/nguồn thường dùng | Giới hạn cần lưu ý |
|---|---|---|
| PostgreSQL | `pg_stat_activity`, `pg_blocking_pids`, `pg_locks`, `pg_stat_statements`, slow-query log | Phân biệt state và wait event; extension/quyền quan sát |
| MySQL 8 / InnoDB | Performance Schema, `performance_schema.data_lock_waits`, `performance_schema.data_locks`, Performance Schema statement summaries | Cần bật/giữ phù hợp instrumentation, quyền và hiểu cơ chế InnoDB |
| SQL Server | `sys.dm_exec_requests`, `sys.dm_tran_locks`, Query Store, execution plans | Session ID, blocking_session_id, wait_type; quyền DMV theo phiên bản |
| Oracle Database | Dynamic performance views như `V$SESSION`, ASH/AWR khi được cấp phép, execution plans | Thống kê, quyền truy cập và giấy phép tính năng cần xác minh |

Ví dụ khám phá InnoDB lock wait trên MySQL 8, với quyền phù hợp:

```sql
SELECT *
FROM performance_schema.data_lock_waits;

SELECT *
FROM performance_schema.data_locks;
```

Hai view giúp điều tra lock của InnoDB; cách ghép các row và tên cột phụ thuộc phiên bản. Chúng không cung cấp cùng cấu trúc với PostgreSQL `pg_locks`. Không nhầm thời gian của Performance Schema statement timer với mili giây nếu chưa quy đổi đơn vị: nhiều timer được báo theo **picosecond**.

Với SQL Server, một phép nhìn nhanh các request đang chờ (quyền phù hợp):

```sql
SELECT
    session_id,
    blocking_session_id,
    status,
    wait_type,
    wait_time,
    total_elapsed_time
FROM sys.dm_exec_requests
WHERE blocking_session_id <> 0;
```

`blocking_session_id` là dấu hiệu hữu ích nhưng không mô tả đầy đủ mọi dạng contention. Khi phân tích production, cần dùng đúng công cụ của DBMS, không copy SQL chẩn đoán PostgreSQL sang hệ khác và suy kết quả tương đương.

## 20. Thiết kế cảnh báo tránh nhiễu

Một dashboard có giá trị khi giúp phân biệt **“đang chậm bình thường”** và **“đã hình thành sự cố”**. Không cảnh báo chỉ vì có một query chạy trên 1 giây.

### Cặp tín hiệu nên theo dõi cùng nhau

| Cặp tín hiệu | Vì sao quan trọng? |
|---|---|
| Query p95/p99 + request error rate | Chậm có gây hỏng tác vụ người dùng không? |
| Pool active/pending + acquire duration | Có đang cạn pool hoặc mất cân bằng tải không? |
| Lock wait count/duration + blocker transaction age | Có transaction nào làm nhiều waiter bị kẹt không? |
| `idle in transaction` count/age + active transactions | Có giao dịch bị bỏ mở không? |
| DB CPU/IO + `pg_stat_statements` total time | Query nào tiêu thụ tài nguyên thật sự? |
| Timeout/deadlock rate + retry count | Retry có đang khuếch đại sự cố không? |

Có thể định nghĩa một **mốc ví dụ** (không phải mặc định chuẩn):

- Alert khi query `inventory.reserve` p95 vượt 300 ms **liên tục** trong một khoảng quan sát và lượng mẫu đủ lớn.
- Alert khi có lock wait kéo dài hơn 10 giây đối với luồng OLTP nhạy cảm, đồng thời ghi blocking PID.
- Alert khi session `idle in transaction` vượt 60 giây **và** có dấu hiệu giữ khóa/chặn request.
- Alert khi pool pending > 0 duy trì và thời gian borrow p95 tăng mạnh so với baseline.

Chọn ngưỡng theo đặc tính workload, SLO, retention, mức dữ liệu và số lượng mẫu. Một batch job hợp lệ chạy 30 phút không nên dùng chung threshold của một request thanh toán cần dưới 200 ms.

### Vì sao histogram hữu ích hơn average?

Giả sử 99 request mất 20 ms và một request mất 10 giây. Giá trị trung bình có thể che khuất vấn đề của một nhóm người dùng. Histogram/percentile giúp thấy tail latency; nhưng p99 trên số mẫu quá ít có thể dao động mạnh. Nên kết hợp số lượng request, phân nhóm operation và thời gian quan sát thay vì chỉ nhìn một percentile.

### Cardinality và chi phí giám sát

Không dùng `tenant_id`, `request_id`, SQL có giá trị bind, user email hoặc backend PID làm label của time-series metric có cardinality vô hạn. Có thể đưa những thông tin này vào **trace/log có kiểm soát** trong phạm vi retention/permission phù hợp, còn metric nên dùng query name, service, outcome và vài nhóm kích thước hữu hạn.

Đồng thời, việc truy vấn `pg_stat_activity`/`pg_locks` theo chu kỳ quá dày hoặc bật logging mọi câu SQL có thể trở thành một phần tải đáng kể. Monitoring phải được đo overhead và giới hạn quyền tương xứng.

## 21. Kiểm thử tích hợp phát hiện lock wait và cleanup

Một unit test mock `PreparedStatement` không chứng minh DB thực sự bị lock; nó chỉ kiểm tra code có gọi method nào. Muốn xác minh timeout, lock wait và ranh giới transaction phải có **hai connection độc lập trên DBMS thật**.

### 21.1. Kịch bản cần xác minh

| Bước | Thao tác | Kỳ vọng |
|---|---|---|
| A1 | Connection A `setAutoCommit(false)` rồi `UPDATE` hàng ID 1 | Chưa commit; có thể giữ lock |
| B1 | Connection B trong transaction khác `UPDATE` cùng hàng | Có thể chờ lock |
| C1 | Connection C đọc `pg_stat_activity` và `pg_blocking_pids` | Phát hiện B bị A chặn |
| B2 | Query timeout hoặc DB lock timeout trên B | Báo `SQLException`/timeout theo driver; B cần rollback |
| A2 | A rollback/commit | Lock được nhả theo quy tắc DB |
| B3 | B rollback, close | Không còn transaction đang mở |
| C2 | Kiểm tra lại state và dữ liệu | Không còn waiter/blocker do test để lại |

Khi tự động hóa test bằng JUnit, nên dùng `ExecutorService`, `CountDownLatch` và timeout có giới hạn để điều phối hai thread. Không dùng `Thread.sleep(...)` trong business transaction production; trong test có thể điều phối bằng latch thay vì giấc ngủ cố định để tránh flaky test.

Ví dụ phác thảo vị trí gây chờ (đặt vào hai tác vụ/kết nối riêng):

```java
// Connection A: tạo lock trong một transaction test.
a.setAutoCommit(false);
try (PreparedStatement ps = a.prepareStatement(
        "UPDATE inventory_items SET available = available - 1 " +
        "WHERE id = ?")) {
    ps.setLong(1, 1L);
    ps.executeUpdate();
}

// Connection B: khi A chưa commit/rollback,
// lệnh UPDATE cùng hàng có thể phải chờ lock.
b.setAutoCommit(false);
try (PreparedStatement ps = b.prepareStatement(
        "UPDATE inventory_items SET available = available - 1 " +
        "WHERE id = ?")) {
    ps.setLong(1, 1L);
    ps.setQueryTimeout(2);
    ps.executeUpdate();
}

// Trong finally của test, rollback cả A và B,
// và đóng cả hai connection bằng try-with-resources.
```

**Đây là hai đoạn công việc để chạy đồng thời trong lab**, không phải một phương thức đơn luồng có thể chạy từ đầu đến cuối mà không bị treo. Test thực phải có timeout tổng, cleanup ở `finally` và tránh giữ connection A mở nếu assertion thất bại. Một `SQLException` timeout trên B không phải bằng chứng A đã bị rollback.

### 21.2. Kiểm thử transaction bị giữ mở

Tạo test cố tình giữ transaction A sau một `UPDATE`, sau đó dùng connection C kiểm tra `xact_start`, `state` và `pg_blocking_pids`. Cuối cùng rollback A và xác nhận B không còn bị chặn.

Trong code Spring, kiểm thử cả trường hợp `@Transactional` chứa lời gọi giả lập mất thời gian **bên ngoài DB**. Mục tiêu là thấy duration transaction tăng dù từng `executeUpdate()` nhanh, rồi sửa thiết kế để thực hiện phần I/O lâu **trước khi mở** hoặc **sau khi kết thúc** transaction nếu bất biến nghiệp vụ cho phép.

### 21.3. Test phải xác minh không rò rỉ connection

Sau các test có timeout/lỗi:

1. `ResultSet`/`PreparedStatement` được đóng.
2. Transaction kết thúc rõ ràng bằng rollback/commit.
3. Logical `Connection` được trả về pool.
4. Pool không còn pending request vì test bỏ một connection giữ mãi.
5. Session PostgreSQL không còn `idle in transaction` do test.
6. Nếu driver/session bị lỗi không thể khôi phục, pool phát hiện và loại bỏ connection không an toàn.

Không chỉ assert “nhận được `SQLTimeoutException`”. Một bài test vận hành tốt phải xác minh **hệ thống hồi phục và không để lại blocker**.

## 22. Các sai lầm điển hình

| Sai lầm | Vì sao sai? | Hướng đúng |
|---|---|---|
| Thấy request mất 15 s thì khẳng định SQL chạy 15 s | Pool wait/fetch/Java có thể chiếm phần lớn | Đo riêng acquire, execute, fetch, transaction |
| Chỉ xem execution plan của waiter khi DB báo chờ `Lock` | Blocker mới là nguyên nhân trực tiếp | `pg_blocking_pids`, xem transaction của blocker |
| Thấy `idle in transaction` rồi cho rằng mọi session đều giữ row lock | Không phải transaction nào cũng giữ lock xung đột | Kiểm tra DML trước đó và lock thực |
| Dùng `query_start` để tính tuổi query của session idle | Có thể là thời điểm query cuối cùng, không đang chạy | Kết hợp `state`, `state_change`, `xact_start` |
| Tin `Connection.close()` tự rollback đúng mọi trường hợp | Hành vi pool/driver khác nhau | Chủ transaction commit/rollback rõ ràng |
| Gọi `setAutoCommit(true)` để “dọn” transaction lỗi | Có thể commit công việc chưa xác nhận | Rollback trước, không reuse khi trạng thái không rõ |
| Ghi toàn bộ SQL kèm tham số vào metric label | Lộ dữ liệu và nổ cardinality | Dùng query name/fingerprint ổn định |
| Chỉ xem query trung bình | Che tail latency và query hiếm nhưng rất chậm | p95/p99, max, calls, total time |
| Tăng pool size khi DB đang bị lock contention | Có thể thêm nhiều waiter, tăng tải | Tìm blocker và giảm transaction hold time |
| Dùng `setQueryTimeout` làm giải pháp duy nhất | Không sửa transaction dài, query có thể lỗi giữa transaction | Fix root cause, rollback đúng |
| Auto-kill mọi transaction > 30 s | Có thể hủy batch/migration hợp lệ | Runbook phân loại workload, quyền và đánh giá tác động |
| Gọi `EXPLAIN ANALYZE UPDATE` trên production | Thật sự có thể sửa dữ liệu | Đo trong lab, thận trọng với side effect |
| Thấy `Index Scan` rồi kết luận không có vấn đề | Có thể vẫn tốn I/O hoặc chờ lock | Đọc actual plan, buffers, wait event |
| Dùng mock làm bằng chứng lock timeout của PostgreSQL | Mock không có lock manager | Integration test với DB thật |
| Không cleanup sau test bị timeout | Để lại transaction/blocker, gây flaky test tiếp theo | Rollback và close trong `finally` |

## 23. Checklist triển khai giám sát JDBC

Trước khi coi hệ thống đã giám sát tốt truy vấn chậm và khóa lâu, hãy kiểm tra:

1. **Tách thời gian:** có metric riêng cho pool acquire, execute, fetch và transaction duration không?
2. **Query identity:** có query name/fingerprint ổn định, không đưa tham số nhạy cảm vào label không?
3. **Phân vị:** đã theo dõi p95/p99 cùng calls, error rate và tổng thời gian chưa?
4. **DB-side:** có slow-query log/thống kê từ DBMS tương ứng và giới hạn overhead/log retention không?
5. **Transaction age:** có tìm được `xact_start`, `state` và `idle in transaction` trên PostgreSQL không?
6. **Blocker:** có phân biệt waiting PID và blocking PID, biết ai đang thực sự giữ lock không?
7. **Lock detail:** có biết dùng `pg_locks` để giải thích mode/locktype nhưng không tự join xung đột một cách ngây thơ không?
8. **Pool:** có metric active, idle, pending, borrow latency và connection hold time không?
9. **Timeout:** có phân biệt query, lock, pool, network và transaction timeout; xử lý rollback/eviction khi lỗi không?
10. **An toàn vận hành:** có runbook rõ ràng trước khi cancel/terminate backend, tránh ngắt nhầm giao dịch quan trọng không?
11. **Kiểm thử:** đã tạo lock wait trong DB test, xác minh cleanup và hồi phục đúng khi timeout chưa?
12. **Ngăn tái diễn:** đã loại bỏ I/O chậm trong transaction, giới hạn dữ liệu và tối ưu plan khi có bằng chứng chưa?

## Ghi nhớ

- **Truy vấn chậm, chờ khóa và chờ pool là ba vấn đề khác nhau**, dù đều làm request mất nhiều giây.
- **Transaction giữ khóa lâu có thể không còn query đang chạy**; `idle in transaction` là một tín hiệu cần điều tra.
- Trong PostgreSQL, `pg_stat_activity` cho biết trạng thái phiên; **`pg_blocking_pids(...)` giúp tìm blocker**; `pg_locks` cho biết thêm loại/chế độ khóa.
- `pg_stat_statements` và slow-query log giúp tìm mẫu truy vấn tiêu tốn nhiều thời gian, nhưng cần cấu hình và quyền phù hợp.
- **`EXPLAIN ANALYZE` chạy thật câu SQL**; đừng dùng tùy tiện trên production, đặc biệt với DML.
- Theo dõi **pool borrow, execute, fetch, transaction** từ phía Java/JDBC để tránh kết luận sai nguyên nhân.
- `setQueryTimeout()` và timeout DBMS là công cụ giới hạn tác hại; vẫn cần **commit/rollback đúng, connection cleanup và root-cause fix**.
- Monitoring cần bảo vệ dữ liệu nhạy cảm, kiểm soát label cardinality và đo chính overhead của hệ thống giám sát.

Một hệ thống JDBC vận hành tốt không chỉ ghi nhận “câu SQL nào vượt 1 giây” mà còn trả lời được **nó chậm ở tầng nào, có đang đợi ai, transaction nào giữ khóa và cần thay đổi điều gì để sự cố không tái diễn**. Khi nối metric Java, trạng thái pool, wait event PostgreSQL và kế hoạch thực thi, đội phát triển có thể xử lý đúng nguyên nhân thay vì tăng pool hoặc thêm index theo cảm tính.

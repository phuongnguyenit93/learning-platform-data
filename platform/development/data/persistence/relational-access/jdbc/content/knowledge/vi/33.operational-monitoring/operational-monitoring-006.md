# Theo dõi timeout, bế tắc và lỗi kết nối trong JDBC

Một hệ thống Java sử dụng **JDBC** có thể hoạt động bình thường khi tải thấp nhưng phát sinh hàng loạt lỗi khi số người dùng tăng: `DataSource.getConnection()` mất vài giây, `PreparedStatement.executeUpdate()` bị timeout, hai transaction chờ khóa lẫn nhau, hoặc `Connection.commit()` trả lỗi mạng. Nếu chỉ ghi một dòng log **“Database error”**, người vận hành khó phân biệt nguyên nhân và có thể áp dụng cách xử lý sai, chẳng hạn tăng pool khi database đang nghẽn khóa hoặc retry một lệnh ghi chưa rõ đã commit hay chưa.

Bài **“Theo dõi timeout, bế tắc và lỗi kết nối”** thuộc chương **Giám sát vận hành** của module **JDBC**. Mục tiêu là xây dựng cách **quan sát, phân loại, cảnh báo và điều tra** các sự cố trên đường đi của một yêu cầu dữ liệu: từ lấy `Connection` qua `DataSource`, chạy SQL bằng `PreparedStatement`, đọc `ResultSet`, đến `commit()`, `rollback()` và trả kết nối về pool. Các ví dụ dùng API JDBC chuẩn; phần thông tin riêng của pool và hệ quản trị được mô tả rõ là đặc thù implementation.

**Nguyên tắc trung tâm:** phải gắn mỗi lỗi với **giai đoạn**, **khoảng thời gian**, **trạng thái transaction**, **SQLState/vendor code**, **metric của pool** và **bằng chứng từ database**. Timeout, chờ khóa, deadlock và mất kết nối có thể gây triệu chứng giống nhau ở API, nhưng **không có cùng nguyên nhân hay chiến lược khôi phục**.

## 1. Một yêu cầu JDBC đi qua những giai đoạn nào?

Trước khi phân loại sự cố, cần xác định chỗ đo.

```text
HTTP request / background job
              │
              ▼
      DataSource.getConnection()
         │             │
         │             └── Pool đợi connection rảnh,
         │                 tạo/kiểm tra connection vật lý
         ▼
      Connection có thể dùng
              │
              ▼
   prepareStatement(...) + bind parameter
              │
              ▼
   executeQuery() / executeUpdate() / executeBatch()
         │          │
         │          └── Server parse/plan, đọc/ghi, chờ khóa,
         │               thực thi và phản hồi
         ▼
      ResultSet.next() / getXxx()
         │
         └── Có thể fetch thêm dữ liệu qua mạng
              │
              ▼
    commit() hoặc rollback() nếu có transaction
              │
              ▼
    ResultSet/Statement/Connection.close()
              │
              └── Pooled Connection thường được trả về pool
```

Không phải mọi yêu cầu đều có tất cả các bước. Ví dụ `SELECT` ở chế độ auto-commit không nhất thiết có lời gọi `commit()` tường minh. Driver có thể chuẩn bị statement ở phía client hoặc server, fetch dữ liệu sớm hay muộn và thay đổi số lượt mạng. Vì vậy các mốc đo dưới đây là **mốc quan sát từ ứng dụng**, không phải phép đo trực tiếp CPU database.

| Giai đoạn | Tên đo gợi ý | Câu hỏi cần trả lời |
| --- | --- | --- |
| Lấy kết nối | `jdbc.acquire.duration` | Yêu cầu phải chờ bao lâu để nhận `Connection`? |
| Tạo kết nối vật lý | `jdbc.connection.creation.duration` nếu pool/driver có | DNS, TCP, TLS, xác thực và khởi tạo phiên có chậm không? |
| Kiểm tra kết nối | `jdbc.connection.validation.duration` nếu pool có | Có nhiều kết nối idle bị hỏng phải loại bỏ không? |
| Chuẩn bị và chạy SQL | `jdbc.statement.duration` | Câu SQL nào chậm, có bị chờ khóa hay lỗi không? |
| Đọc kết quả | `jdbc.resultset.read.duration` | Query trả nhanh nhưng fetch/mapping lâu không? |
| Giữ kết nối | `jdbc.connection.hold.duration` | Connection bị giữ bao lâu từ checkout đến trả? |
| Kết thúc transaction | `jdbc.transaction.commit.duration` / `rollback.duration` | Có chậm hoặc lỗi ở bước commit/rollback không? |
| Toàn yêu cầu | `request.duration` | Người dùng thực sự phải chờ bao lâu? |

Không nên cộng các phép đo từ nhiều nguồn một cách máy móc: một số đồng hồ **chồng lấn**. Ví dụ `statement.duration` có thể đã bao gồm fetch nếu đo quanh toàn bộ `ResultSet`.

## 2. Phân biệt bốn nhóm triệu chứng dễ bị gom nhầm

| Nhóm | Triệu chứng điển hình | Dấu hiệu quan sát bổ sung | Hướng điều tra |
| --- | --- | --- | --- |
| **Timeout khi chờ mượn** | `getConnection()` ném `SQLException` sau thời gian chờ | Pool `active` gần tối đa, `idle=0`, `pending` tăng | Connection bị giữ lâu, SQL chậm, pool sizing, leak |
| **Timeout khi chạy SQL** | `executeQuery()`/`executeUpdate()` ném `SQLTimeoutException` hoặc lỗi timeout khác | Statement latency cao, lock wait hoặc query execution cao | Execution plan, lock, timeout của driver/server |
| **Bế tắc (*deadlock*)** | DB chọn hủy một transaction để phá vòng chờ | Deadlock diagnostics/log, SQLState/vendor code tương ứng | Thứ tự cập nhật hàng, phạm vi transaction, index, contention |
| **Lỗi kết nối** | `getConnection()`, `execute...()` hoặc `commit()` báo connection exception | SQLState class `08` có thể xuất hiện; pool creation/validation failures tăng | DNS, TCP/TLS, xác thực, DB restart/failover, server session limit |

Bốn nhóm **không loại trừ nhau**. Ví dụ một câu `UPDATE` bị chặn do khóa kéo dài, người dùng thấy query timeout; nhiều request tiếp tục giữ connection trong lúc chờ khóa, khiến pool đầy và các request sau gặp borrow timeout. Lỗi ban đầu là **tranh chấp khóa**, còn borrow timeout là **hậu quả dây chuyền**.

Ngược lại, không nên quy mọi statement timeout là do deadlock. Có thể server chưa dùng index, phải quét quá nhiều dòng hoặc đang chờ IO. Cần đối chiếu sự kiện ở DB thay vì suy đoán từ độ dài thời gian.

## 3. Phân biệt timeout theo phạm vi và đơn vị

JDBC và connection pool có nhiều đồng hồ độc lập:

| Giới hạn | Thao tác được tác động | Cấu hình / API tiêu biểu | Điều không bảo đảm |
| --- | --- | --- | --- |
| **Pool acquisition/borrow timeout** | Chờ lấy connection từ pool | Thuộc tính riêng của pool | Không tự giới hạn thời gian chạy SQL |
| **Connect/login timeout** | Thiết lập kết nối vật lý, đăng nhập | Driver properties, `DataSource.setLoginTimeout(seconds)` | Không đồng nghĩa borrow timeout của mọi pool |
| **Validation timeout** | Kiểm tra connection trước khi cấp phát | Pool, `Connection.isValid(seconds)` | Không bảo đảm connection luôn sống sau kiểm tra |
| **Query timeout** | Lời gọi thực thi statement theo driver | `Statement.setQueryTimeout(seconds)` | Không bao toàn request, fetch, commit và rollback |
| **Network/socket timeout** | Chờ phản hồi/truyền dữ liệu qua kết nối | `Connection.setNetworkTimeout(executor, millis)` hoặc thuộc tính driver | Không thay thế query timeout hoặc transaction deadline |
| **Transaction timeout** | Phạm vi transaction theo transaction manager/server | Framework/server, không có một setter JDBC chuẩn duy nhất | Không nhất thiết hủy từng thao tác đúng thời điểm |
| **Request deadline** | Ngân sách đầu-cuối của nghiệp vụ | Được ứng dụng/framework truyền qua các tầng | Không tự hủy một JDBC call đang bị chặn |

**Đơn vị không giống nhau:** `setQueryTimeout(int)` và `isValid(int)` dùng **giây**; `setNetworkTimeout(..., int)` dùng **mili giây**. Thuộc tính HikariCP, DBCP, Tomcat JDBC Pool và driver có thể mang tên và đơn vị khác nhau. Mọi dashboard/runbook phải ghi **rõ tầng và đơn vị**.

Một lời gọi `DataSource.getConnection()` chậm **không chứng minh** driver mất cùng thời lượng để tạo kết nối. Pool có thể đơn giản là hết connection rảnh. Một lời gọi `executeQuery()` nhanh cũng không chứng minh toàn bộ quá trình đọc dữ liệu nhanh, vì `ResultSet.next()` có thể fetch qua mạng.

### Timeout không tương đương “server chắc chắn đã dừng”

Khi `Statement.setQueryTimeout(2)` hoặc `Statement.cancel()` được sử dụng, driver phải phối hợp với database để thử giới hạn/hủy câu SQL theo khả năng hỗ trợ. Việc Java nhận `SQLTimeoutException` hay `cancel()` trả về **không chứng minh** rằng:

- Server chưa hề thực hiện phần nào của lệnh.
- Transaction đã rollback hoặc không có dữ liệu được commit.
- Kết nối vẫn an toàn để tái sử dụng.
- Hệ thống khác chưa nhận tác động phụ từ trigger, event hoặc lời gọi bên ngoài.

Đặc biệt, **lỗi ở `Connection.commit()` có thể để lại trạng thái commit không xác định**. Đây là tình huống cần đối soát/idempotency, không phải retry mù quáng.

## 4. Bế tắc, chờ khóa và serialization failure là ba khái niệm khác nhau

### Chờ khóa (*lock wait*)

Transaction B muốn sửa hàng đang bị A giữ khóa. B phải chờ A commit/rollback hoặc hết giới hạn chờ. Nếu A rồi sẽ kết thúc, đây là **chờ khóa thông thường**, chưa phải deadlock.

```text
Transaction A                 Transaction B
-------------                 -------------
UPDATE row #1
   giữ lock #1                 UPDATE row #1
                                  chờ lock #1
COMMIT
   nhả lock #1                 tiếp tục thực thi
```

Chờ khóa kéo dài có thể làm query timeout. Thông tin cần tìm là **transaction nào chặn**, lệnh SQL và thời lượng giao dịch của bên chặn, không chỉ câu SQL của bên bị chặn.

### Bế tắc (*deadlock*)

Deadlock là **vòng phụ thuộc**: A đang giữ tài nguyên mà B cần, đồng thời B giữ tài nguyên mà A cần. Không bên nào có thể tiến lên nếu không có cơ chế phá vòng.

```text
Transaction A                    Transaction B
-------------                    -------------
UPDATE row #1                    UPDATE row #2
giữ lock #1                      giữ lock #2
        │                               │
        ▼                               ▼
đợi lock #2 ◄──── vòng chờ ──────► đợi lock #1
        │                               │
        └────── Database phát hiện ──────┘
                 và hủy một bên
```

Hệ quản trị thường có cơ chế phát hiện/giải quyết deadlock và chọn một transaction làm nạn nhân. **Nạn nhân có thể thay đổi** tùy lịch chạy, engine, mức khóa và tải. Ứng dụng nên xử lý rollback và có chính sách thử lại **toàn transaction** khi chứng minh được an toàn.

### Serialization failure hoặc rollback do xung đột

Một transaction có thể bị hủy vì database không thể duy trì mức cô lập yêu cầu (đặc biệt `SERIALIZABLE`), dù không xuất hiện vòng deadlock khóa kiểu cổ điển. **SQLState `40001`** thường được dùng cho lỗi serialization/transaction rollback; trong một số hệ, deadlock cũng có thể xuất hiện dưới mã này. Vì thế:

- **Không xem mọi `40001` là deadlock.**
- **Không xem mọi deadlock có cùng vendor code hoặc cùng SQLState trên tất cả database.**
- **Không xem mọi timeout khi `UPDATE` là lock wait/deadlock.**

Ví dụ cụ thể cần được xác nhận theo driver:

| Cơ sở dữ liệu | Tín hiệu thường gặp | Lưu ý |
| --- | --- | --- |
| PostgreSQL | SQLState `40P01` cho deadlock; `40001` cho serialization failure | Cần log server và phân tích thứ tự khóa; hai trạng thái không có cùng nguyên nhân |
| MySQL/InnoDB | Deadlock thường có vendor error code `1213`, SQLState `40001`; lock wait timeout có mã khác | Cách hủy câu lệnh/transaction sau lock wait timeout phụ thuộc cấu hình/engine |
| SQL Server | Deadlock victim thường có error number `1205` | SQLState/lớp ngoại lệ cần kiểm tra theo driver phiên bản thực tế |
| Oracle Database | Deadlock thường được báo qua lỗi như `ORA-00060` | Không quy mọi lỗi khóa thành deadlock; kiểm tra trace/log và transaction state |

Bảng trên là **ví dụ nhận diện sản phẩm**, không phải bộ quy tắc phân loại đa database chỉ dựa trên một con số. Nếu hệ thống hỗ trợ nhiều driver, bộ phân loại cần dữ liệu kiểm thử và tài liệu riêng cho từng sản phẩm.

## 5. SQLState, lớp SQLException và vendor code dùng để làm gì?

`SQLException` cung cấp những tín hiệu chuẩn:

```java
String sqlState = exception.getSQLState();
int vendorCode = exception.getErrorCode();
SQLException next = exception.getNextException();
```

Các lớp thường gặp:

- `SQLTimeoutException`: driver báo timeout theo cơ chế hỗ trợ; cần thêm **giai đoạn** để xác định là query, network hay thao tác khác.
- `SQLTransientConnectionException`: một dạng connection exception có tính chất tạm thời theo phân loại JDBC; không chứng minh ngay rằng retry nghiệp vụ là an toàn.
- `SQLNonTransientConnectionException`: connection exception được driver phân loại không tạm thời; cần kiểm tra cấu hình, TLS, quyền hoặc endpoint.
- `SQLTransactionRollbackException`: transaction rollback theo phân loại driver, có thể liên quan deadlock/serialization; không đủ để kết luận nguyên nhân riêng.
- `BatchUpdateException`: lỗi batch; có thể chứa `getUpdateCounts()` và chuỗi `getNextException()`.

Một số nhóm SQLState hữu ích:

| SQLState | Ý nghĩa khái quát | Điều nên làm |
| --- | --- | --- |
| Class `08` | Nhóm lỗi kết nối | Kiểm tra kết nối hỏng, mạng, driver, DB/pool, **giai đoạn xảy ra** |
| Class `40` | Nhóm lỗi transaction rollback | Kiểm tra isolation, tranh chấp, deadlock diagnostics và chính sách retry |
| `40001` | Serialization failure theo quy ước SQL/JDBC; có thể được driver dùng cho xung đột khác | Đối chiếu vendor code/driver và thử nghiệm transaction |
| `40P01` | Deadlock detected theo PostgreSQL | Kiểm tra log PostgreSQL và vòng khóa liên quan |
| `null` hoặc mã riêng | Không thể phân loại chỉ bằng SQLState | Dùng loại exception, vendor code và bằng chứng pool/DB |

Những mã này **không phải ranh giới duy nhất của lỗi**. Một lỗi mạng khi đang `commit()` nguy hiểm hơn một lỗi kết nối khi chưa chạy SQL, dù cả hai cùng có SQLState class `08`. Nếu một driver thay đổi SQLState sau nâng cấp, cần chạy lại kiểm thử phân loại.

### Đừng bỏ qua chuỗi ngoại lệ

Một `SQLException` có thể có nhiều `nextException`; `BatchUpdateException` thường đặc biệt cần thông tin này. Với Java `try-with-resources`, lỗi phát sinh lúc đóng tài nguyên có thể nằm trong `getSuppressed()`. Hãy giữ đủ dữ kiện để chẩn đoán, nhưng tránh lộ thông tin nhạy cảm vào phản hồi của API.

## 6. Bộ metric tối thiểu cho một dịch vụ JDBC

Một dashboard có ích nên ghép metric **ứng dụng**, **pool**, **driver/network** và **database**, không chỉ đếm `SQLException`.

| Tín hiệu | Loại đo | Câu hỏi có thể trả lời |
| --- | --- | --- |
| Request latency p50/p95/p99 | Histogram | Người dùng bị chậm đến mức nào và ở request nào? |
| `jdbc.acquire.duration`, cả thành công/lỗi | Histogram | Mượn connection có chậm không? |
| `jdbc.statement.duration` theo operation | Histogram | Thao tác SQL nào chiếm thời gian? |
| `jdbc.resultset.read.duration` | Histogram nếu có | Chậm khi xử lý/fetch kết quả hay ở bước execute? |
| `jdbc.connection.hold.duration` | Histogram | Connection đang bị giữ bao lâu? |
| Pool `active`, `idle`, `pending`, `max` | Gauge | Pool bão hòa hay chưa, có hàng đợi không? |
| Pool borrow timeout count | Counter | Có yêu cầu không lấy được connection đúng hạn? |
| Connection creation failures/duration | Counter/histogram | Mạng, auth, server hoặc driver đang tạo connection lỗi/chậm? |
| Validation failure/eviction count | Counter | Có nhiều connection idle chết hoặc bị loại bỏ? |
| Query/statement timeout count | Counter | Những operation nào vượt ngưỡng SQL? |
| Transaction rollback/deadlock/serialization count | Counter | Mức tranh chấp và lỗi giao dịch thay đổi thế nào? |
| Commit/rollback failure count | Counter | Có xuất hiện kết quả transaction không rõ trạng thái? |
| Database lock wait/blocking time | Metric DBMS | Có long-running blocker hay lock contention không? |
| Database active sessions, CPU, IO, connection limit | Metric DBMS | Database bão hòa tài nguyên gì? |

**Tên metric chỉ là gợi ý**, không phải chuẩn bắt buộc của JDBC. `javax.sql.DataSource` không có API chuẩn để lấy `active/idle/pending` hoặc thời gian tạo physical connection. Những metric đó phải lấy từ **pool implementation** và công cụ quan sát tương ứng. Tương tự, số deadlock thực sự cần thêm metric/log của DBMS; tự đếm `40001` ở Java chưa chắc phản ánh số deadlock.

### Những thuộc tính nên dùng làm nhãn metric

Nhãn có tính ổn định và cardinality thấp:

- `operation`: tên logic như `orders.reserve`, `customers.find`.
- `phase`: `acquire`, `execute`, `fetch`, `commit`, `rollback`.
- `outcome`: `success`, `timeout`, `connection_error`, `transaction_rollback`, `other`.
- `db_profile`: định danh cố định do server quản lý, ví dụ `orders-primary`.
- `driver_family` hoặc `db_product` nếu có danh sách hữu hạn và cần so sánh.

**Không** làm label từ JDBC URL thô, SQL nguyên văn, câu SQL chứa tham số, tên khách hàng, ID request, email hoặc toàn bộ thông điệp lỗi: các giá trị này vừa có thể lộ dữ liệu nhạy cảm, vừa làm nổ số lượng chuỗi thời gian trong hệ giám sát.

## 7. Ví dụ Java: đo lấy kết nối, thực thi SQL và thời gian giữ connection

Ví dụ dưới đây dùng một `DataSource` và một interface ghi metric nhỏ để không khóa bài học vào thư viện giám sát cụ thể. Nó phân biệt **acquire duration**, **toàn bộ giai đoạn xử lý SQL** và **connection hold duration**.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;

public final class MonitoredCustomerDao {
    private final DataSource dataSource;
    private final Metrics metrics;

    public MonitoredCustomerDao(DataSource dataSource, Metrics metrics) {
        this.dataSource = Objects.requireNonNull(dataSource);
        this.metrics = Objects.requireNonNull(metrics);
    }

    public Optional<String> findName(long customerId)
            throws SQLException {

        long acquisitionStarted = System.nanoTime();
        Connection acquired;

        try {
            acquired = dataSource.getConnection();
            metrics.duration(
                    "jdbc.acquire", System.nanoTime() - acquisitionStarted,
                    true);
        } catch (SQLException failure) {
            metrics.duration(
                    "jdbc.acquire", System.nanoTime() - acquisitionStarted,
                    false);
            metrics.failure("acquire", failure.getSQLState(),
                    failure.getErrorCode());
            throw failure;
        }

        long holdStarted = System.nanoTime();

        // Chỉ đóng Connection mà DAO tự mượn và sở hữu.
        try (Connection connection = acquired) {
            long operationStarted = System.nanoTime();
            boolean succeeded = false;

            try (PreparedStatement statement =
                         connection.prepareStatement(
                                 "SELECT name FROM customers WHERE id = ?")) {

                statement.setLong(1, customerId);

                try (ResultSet result = statement.executeQuery()) {
                    if (!result.next()) {
                        succeeded = true;
                        return Optional.empty();
                    }

                    // Schema ví dụ khai báo name NOT NULL.
                    String name = result.getString("name");
                    succeeded = true;
                    return Optional.of(name);
                }

            } catch (SQLException failure) {
                metrics.failure("query", failure.getSQLState(),
                        failure.getErrorCode());
                throw failure;

            } finally {
                // Bao gồm prepare/execute/fetch/đóng statement;
                // không đồng nghĩa thời gian CPU database.
                metrics.duration(
                        "jdbc.customer.find.total",
                        System.nanoTime() - operationStarted, succeeded);
            }

        } finally {
            // Tính cả thời gian Connection.close() để đo
            // từ khi nhận đến khi trả quyền sử dụng.
            metrics.duration(
                    "jdbc.connection.hold",
                    System.nanoTime() - holdStarted, true);
        }
    }

    public interface Metrics {
        void duration(String operation, long nanoseconds, boolean success);
        void failure(String phase, String sqlState, int vendorCode);
    }
}
```

**Các giới hạn và điểm cải tiến khi triển khai:**

1. `jdbc.acquire` đo **toàn bộ thời gian `getConnection()`** chứ không đo riêng queue wait. Nếu pool tạo connection mới hoặc validation trong lời gọi, chi phí đó cũng được tính.
2. `jdbc.customer.find.total` đo từ lúc `prepareStatement()` đến sau khi hoàn tất `ResultSet` trong scope, không riêng thời gian server thực thi câu SQL.
3. `jdbc.connection.hold` đo từ lúc nhận đến sau `Connection.close()`, giúp nhìn thấy transaction/DAO giữ kết nối lâu. Trong ví dụ, nhãn `success=true` của hold chỉ mang nghĩa phép đo được ghi lại, **không xác nhận đóng kết nối thành công**; để theo dõi lỗi close cần bắt/ghi riêng hoặc decorator pool phù hợp.
4. Nếu mã nằm trong một transaction Spring hoặc service đã sở hữu connection, **không dùng ví dụ này để tự checkout connection mới**. Chuyển instrument sang tầng sở hữu transaction hoặc sử dụng `JdbcTemplate`/`DataSourceUtils` tương thích; không để ghi metric làm thay đổi kết nối thuộc giao dịch.
5. `Metrics` là interface minh họa; triển khai sản phẩm nên dùng hệ metric như Micrometer/OpenTelemetry đã cấu hình, không tự tạo chuỗi label ngẫu nhiên.
6. Trong một `ResultSet` lớn, cần đo rõ thời gian `executeQuery()` và thời gian `next()`/mapping nếu muốn tách parse/execute/fetch. Đừng mặc định fetch dữ liệu xảy ra hết trước khi `executeQuery()` trả về.
7. Nếu `Optional.of(name)` có thể nhận `null` vì schema thực tế cho SQL `NULL`, cần chọn mô hình kết quả phù hợp. Điều này không liên quan trực tiếp đến timeout nhưng nhắc rằng metric không thay thế hợp đồng ánh xạ dữ liệu.

### Đồng hồ nào nên dùng?

`System.nanoTime()` phù hợp để đo **elapsed duration** trong một JVM, không phải timestamp giờ lịch. Hãy chuyển sang giây/mili giây theo công cụ metric; không so sánh trực tiếp giá trị `nanoTime()` giữa hai máy. Để tương quan log nhiều service, dùng trace ID và timestamp đã đồng bộ theo cơ chế tracing.

## 8. Đọc SQLException mà không mất dữ liệu chẩn đoán

Một lỗi ban đầu có thể chứa chuỗi `getNextException()` và lỗi bổ sung ở `getSuppressed()`. Ví dụ hàm thu thập **mã phân loại ổn định**, không tự in full SQL/URL:

```java
import java.sql.SQLException;
import java.sql.SQLTimeoutException;
import java.sql.SQLTransactionRollbackException;

public final class SqlFailureInspector {
    private SqlFailureInspector() {
    }

    public static String category(SQLException failure) {
        SQLException current = failure;
        int checked = 0;

        while (current != null && checked++ < 20) {
            String state = current.getSQLState();

            if ("40P01".equals(state)) {
                return "deadlock_postgresql";
            }
            if ("40001".equals(state)) {
                return "transaction_conflict";
            }
            if (state != null && state.startsWith("08")) {
                return "connection_error";
            }
            if (current instanceof SQLTimeoutException) {
                return "reported_timeout";
            }
            if (current instanceof SQLTransactionRollbackException) {
                return "transaction_rollback";
            }

            current = current.getNextException();
        }

        return "other_sql_error";
    }

    public static void logCodes(SQLException failure) {
        SQLException current = failure;

        for (int index = 0;
             current != null && index < 20;
             index++, current = current.getNextException()) {

            System.out.println(
                    "index=" + index
                    + " class=" + current.getClass().getSimpleName()
                    + " sqlState=" + current.getSQLState()
                    + " vendorCode=" + current.getErrorCode());
        }
    }
}
```

**Đừng dùng phương thức `category(...)` như một bộ quyết định retry tự động.** Nó chỉ là ví dụ phân loại sơ bộ dựa trên lớp exception/SQLState. Độ ưu tiên có thể cần điều chỉnh với từng driver; một `BatchUpdateException` có thể chứa lỗi gốc sâu hơn; còn nguyên nhân thật của transaction failure cần xác nhận từ logs/metrics DB.

Lỗi ở `commit()` và lỗi ở `getConnection()` có thể cùng thuộc `connection_error` nhưng **khác hẳn độ an toàn khi thử lại**. Do đó sự kiện ghi metric/log phải có thêm:

```text
phase=acquire | execute | fetch | commit | rollback | close
operation=orders.create
category=connection_error
sqlState=08006             # ví dụ minh họa, không suy cho mọi driver
vendorCode=<mã của driver>
transactionOutcome=unknown # chỉ khi kết quả thực sự chưa xác định
traceId=<định danh trace do hệ thống tạo>
```

Đây là format **minh họa**, không phải giá trị đo được của một lỗi cụ thể. Ghi `transactionOutcome=unknown` đặc biệt khi request đã gửi commit hoặc thao tác ghi mà không biết server hoàn tất đến đâu, không tự đặt nhãn này cho mọi lỗi acquire trước khi có SQL.

## 9. Theo dõi trạng thái transaction và xử lý rollback an toàn

Khi đo lỗi ở một transaction gồm nhiều câu SQL, **giai đoạn commit/rollback là bắt buộc**. Nếu code chỉ ghi thời gian `executeUpdate()`, có thể bỏ qua tình huống query thành công nhưng `commit()` mới phát sinh lỗi mạng.

Một khung transaction JDBC thủ công:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class InventoryService {
    private final DataSource dataSource;

    public InventoryService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void reserve(long productId, int quantity) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }

        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();
            if (!originalAutoCommit) {
                throw new SQLException(
                        "This service expects to own a new transaction");
            }

            connection.setAutoCommit(false);
            boolean transactionEnded = false;
            boolean commitAttempted = false;
            Throwable primary = null;

            try {
                String sql =
                        "UPDATE inventory SET available = available - ? " +
                        "WHERE product_id = ? AND available >= ?";

                try (PreparedStatement statement =
                             connection.prepareStatement(sql)) {
                    statement.setInt(1, quantity);
                    statement.setLong(2, productId);
                    statement.setInt(3, quantity);

                    if (statement.executeUpdate() != 1) {
                        throw new SQLException(
                                "No inventory row could be reserved");
                    }
                }

                commitAttempted = true;
                connection.commit();
                transactionEnded = true;

            } catch (SQLException | RuntimeException | Error failure) {
                primary = failure;

                // Phải ghi metric riêng: commitAttempted giúp
                // phân biệt lỗi trước commit với trạng thái mơ hồ
                // khi lỗi xuất hiện trong/lúc sau commit().
                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }

                if (commitAttempted) {
                    // Không tự kết luận chắc chắn commit chưa xảy ra;
                    // cần đối soát/idempotency trước bất kỳ retry nào.
                }

                throw failure;

            } finally {
                // Tránh setAutoCommit(true) khi rollback thất bại.
                if (transactionEnded) {
                    try {
                        connection.setAutoCommit(originalAutoCommit);
                    } catch (SQLException restoreError) {
                        if (primary != null) {
                            primary.addSuppressed(restoreError);
                        } else {
                            throw restoreError;
                        }
                    }
                }
            }
        }
    }
}
```

Đoạn trên là **ví dụ trách nhiệm kết thúc transaction**, chưa có implementation metric và không thay cho transaction manager của framework. Trong hệ thống thực tế, đo riêng thời gian `commit()`/`rollback()`, ghi nhận `commitAttempted` và lỗi suppressed. Nếu rollback thất bại, kết nối có thể ở trạng thái nghi vấn; pool cần cơ chế **evict/invalidate** phù hợp, không tự coi `Connection.close()` là bằng chứng physical connection đã bị loại bỏ.

**Sau khi `commit()` ném lỗi, rollback thành công cũng không chứng minh server chưa commit trước đó.** Đây là lý do chính sách retry của `orders.create` khác với retry một `SELECT` an toàn hoặc một request bị từ chối **trước khi gửi SQL**.

Trong ứng dụng Spring, nếu `@Transactional` hoặc `TransactionTemplate` đang sở hữu transaction, repository **không tự gọi `commit()`/`rollback()`**. Hãy instrument transaction manager hoặc observability hook tương ứng, đồng thời ghi các lỗi từ repository để ghép đúng cùng trace.

## 10. Điều tra pool bão hòa trước khi tăng kích thước

Khi hệ thống báo “Could not get connection within timeout”, một phản xạ thường thấy là tăng `maximumPoolSize`. Nhưng cần nhìn tổng thể:

```text
Pool maximum = 20
Active       = 20
Idle         = 0
Pending      = 30
Acquire p99  = cao

Các giả thuyết:
  A. SQL / transaction giữ Connection quá lâu
  B. Có connection leak
  C. DB nghẽn lock hoặc CPU/IO
  D. Lưu lượng đến vượt năng lực ổn định của DB
```

**Cần phân biệt:**

- **Pool đầy và DB vẫn khỏe:** có thể request giữ connection trong khi gọi HTTP/API bên ngoài, đọc `ResultSet` chậm hoặc không đóng tài nguyên.
- **Pool đầy do DB chậm:** query chờ lock, chạy sai execution plan hoặc server quá tải khiến thời gian giữ connection tăng.
- **Pool chưa đầy nhưng borrow vẫn chậm:** có thể pool đang tạo connection mới, validation kết nối idle, hoặc bị giới hạn bởi chính sách nội bộ.
- **Creation failures cao:** DNS/TCP/TLS/auth, giới hạn server session hoặc DB endpoint không khả dụng, không chỉ thiếu pool size.

Một số metric pool có thể cung cấp **leak detection warning** hoặc thống kê connection hold. Nhưng warning “đã mượn quá lâu” **không tự chứng minh leak**; transaction hợp lệ đang chạy lâu cũng có thể phát tín hiệu này. Cần đối chiếu transaction trace, active SQL, stack và thời điểm mượn/trả.

### Lưu ý nhiều replica

Giả sử có 10 replica Java, mỗi replica đặt pool tối đa 30 connection. Tổng trần tiềm năng là **300 connection vật lý**, chưa tính batch job, migration và công cụ quản trị. Nâng mọi pool lên 50 có thể tạo **500 connection**, vượt giới hạn hoặc làm nghẽn DB. Khi sizing, phải xem throughput thực tế, thời gian giữ connection và giới hạn session của server, không chỉ metric một replica.

## 11. Đối chiếu với bằng chứng từ database

JDBC chỉ thấy **triệu chứng tại client**. Để biết nguyên nhân deadlock hoặc query wait, cần thêm dữ liệu DBMS:

- Những session/transaction đang chạy hoặc bị blocked.
- Thời gian bắt đầu transaction, SQL đang thực thi, loại wait (lock, IO, network, CPU... theo DB).
- Session/blocking tree hoặc lock graph để biết **ai giữ tài nguyên mà ai đang đợi**.
- Deadlock report/trace và statement khiến DB chọn nạn nhân.
- Query plan, index, statistics và số hàng thực tế.
- Số lượng kết nối hiện tại so với giới hạn server.
- Lỗi xác thực, TLS, mạng, restart/failover và health event.

Ví dụ **chỉ dành cho PostgreSQL**, không phải SQL chuẩn đa hệ:

```sql
-- Phân tích các session có trạng thái chờ lock.
-- Cần quyền xem thông tin thống kê phù hợp.
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start
FROM pg_stat_activity
WHERE datname = current_database()
  AND wait_event_type = 'Lock';
```

Trên PostgreSQL có thể dùng những chức năng thống kê như `pg_blocking_pids(pid)` để tìm process đang chặn, nếu quyền và phiên bản hỗ trợ. SQL Server, MySQL/InnoDB và Oracle có các catalog/view/trace riêng; không copy truy vấn PostgreSQL sang hệ quản trị khác. Trước khi chạy các truy vấn chẩn đoán trên production, cần phân quyền và giới hạn tần suất vì chính hoạt động quan sát cũng tiêu tốn tài nguyên.

**Một lock wait được quan sát không chứng minh deadlock.** Chỉ deadlock report hoặc tín hiệu tương đương ở server/driver mới củng cố kết luận có vòng chờ. Ngược lại, deadlock có thể xảy ra và được giải quyết rất nhanh, không còn hiện trong ảnh chụp session tại thời điểm người vận hành mở dashboard; cần có **event log/metrics lịch sử**, không chỉ các gauge hiện tại.

## 12. Thiết kế tracing nối ứng dụng, pool và database

Trong môi trường nhiều service, cần theo dõi một thao tác từ request đến DB:

```text
trace_id = 7af...  (ví dụ định danh do tracing system cấp)

HTTP POST /orders
  └─ service.orders.create
       ├─ jdbc.acquire          12 ms
       ├─ jdbc.inventory.reserve 45 ms
       ├─ jdbc.orders.insert    30 ms
       ├─ jdbc.transaction.commit  8 ms
       └─ jdbc.connection.release  1 ms
```

Thời gian trên chỉ là **ví dụ minh họa**. Nên dùng **operation name ổn định** (`inventory.reserve`, `orders.insert`), không tạo span name chứa ID động.

### Các trường nên xuất hiện trong log sự cố

| Trường | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| `timestamp` | Thời điểm xảy ra | Ghép với DB logs/host metrics |
| `trace_id` / `span_id` | ID tracing ổn định theo request | Nối các đoạn xử lý |
| `db_profile` | `orders-primary` | Biết pool và database logic nào |
| `operation` | `inventory.reserve` | Tên thao tác, không cần raw SQL |
| `phase` | `execute`, `commit`, `acquire` | Xác định điểm thất bại |
| `duration_ms` | Độ trễ đã đo | So với baseline/SLO |
| `sql_state` / `vendor_code` | Mã từ SQLException | Đối chiếu driver/database |
| `exception_class` | `SQLTimeoutException` | Phân loại loại lỗi |
| `attempt` | Số lần thử (nếu retry) | Phân biệt một lỗi với nhiều lỗi do retry |
| `transaction_outcome` | `rolled_back`, `committed`, `unknown` | Giảm nguy cơ retry sai |
| `db_server_version` / `driver_version` | Version đã xác minh | Phát hiện lỗi sau nâng cấp |

### Về SQL trong log/tracing

Không log toàn bộ câu SQL kèm giá trị bind khi dữ liệu có thể chứa PII, token, số thẻ, khóa hay thông tin truy cập. Nếu cần nhóm các truy vấn tương đương, dùng **tên operation** hoặc một **SQL fingerprint đã chuẩn hóa và kiểm soát quyền truy cập**. SQL có thể chứa literal ngay trong văn bản, nên ngay cả query text không có parameters cũng có thể nhạy cảm.

Tránh log raw JDBC URL và connection properties vì có thể chứa password, token, host nội bộ và thông tin TLS. Không xuất nguyên `SQLException.getMessage()` ra response công khai; chỉ dùng lỗi phân loại ổn định như `DATABASE_UNAVAILABLE` hoặc `REQUEST_TIMEOUT`, còn thông tin chi tiết được giữ trong hệ thống vận hành đã phân quyền.

## 13. Cảnh báo theo triệu chứng và tác động, không theo một ngưỡng đơn lẻ

Đặt alert chỉ dựa trên `SQLException` count có thể gây nhiễu: một bản ghi lỗi được retry ba lần có thể tạo ba sự kiện nhưng chỉ một request thất bại, hoặc một deadlock đơn lẻ đã được retry an toàn có thể không ảnh hưởng người dùng.

Một cấu hình cảnh báo hợp lý kết hợp:

1. **Tác động:** request error rate, timeout rate, p95/p99 latency hoặc SLO burn rate tăng kéo dài.
2. **Phạm vi:** service, DB profile, environment, operation quan trọng.
3. **Triệu chứng JDBC:** acquire timeout, query timeout, connection creation failures, deadlock/serialization failures.
4. **Nguyên nhân hỗ trợ:** active/idle/pending, DB lock wait, session limit, CPU/IO, mạng hoặc TLS.
5. **Thời gian duy trì:** kiểm tra qua một cửa sổ đủ để tránh spike thoáng qua, đồng thời đủ nhanh để phát hiện sự cố nghiêm trọng.

Bảng cảnh báo ví dụ định tính:

| Tín hiệu kết hợp | Loại cảnh báo | Phản ứng |
| --- | --- | --- |
| API error rate tăng + borrow timeout tăng + pool full | Pool/throughput incident | Xác định ai giữ connection; kiểm tra SQL và transaction |
| Query p99 tăng + lock wait tăng | Lock contention | Truy blocking tree, transaction dài, index, thứ tự cập nhật |
| Deadlock victim count tăng bất thường | Concurrency regression | Xem deadlock reports, transaction order và retry |
| Creation failures tăng + TLS/auth/connect errors | Connectivity/security incident | Kiểm tra endpoint, cert, secret rotation, DB availability |
| Commit errors/unknown outcomes xuất hiện | Data correctness risk | Hạn chế retry, đối soát theo operation/idempotency |
| DB CPU/IO cao + latency tăng, pool chưa full | DB capacity/query plan | Phân tích query plan và tài nguyên DB |

Không có một ngưỡng `p99=200 ms` hay `pending=5` áp dụng được cho mọi hệ thống. Ngưỡng nên dựa trên **SLO, tải bình thường, độ biến thiên và khả năng phản ứng của nhóm trực vận hành**. Các cảnh báo phải dẫn tới **một hành động điều tra cụ thể**, không chỉ làm tăng thông báo.

## 14. Runbook A: timeout khi mượn Connection

**Tín hiệu khởi đầu:** `DataSource.getConnection()` thất bại sau borrow timeout hoặc latency checkout tăng mạnh.

**Quy trình:**

1. **Xác định phạm vi:** chỉ một replica, một pool hay tất cả instance? Bắt đầu từ thời điểm nào?
2. **Đọc pool metrics:** active, idle, pending, max, checkout latency, connection hold duration.
3. **Nếu pool đang đầy:** tìm request giữ connection lâu qua trace, thread dump và SQL/transaction metrics. Phân biệt leak với SQL chậm và tác vụ ngoài DB.
4. **Nếu pool chưa đầy:** xem creation duration/failures, validation failures, DNS/TCP/TLS/auth và giới hạn tạo connection.
5. **Kiểm tra database:** số phiên hiện tại, lock wait, CPU/IO, query đang chặn; một DB chậm có thể làm connection hold time tăng dây chuyền.
6. **Giảm tác động:** hạn chế lưu lượng/batch job, sửa query hoặc transaction kéo dài, tách tác vụ ngoài DB khi phù hợp. Chỉ điều chỉnh pool size sau khi tính tổng kết nối của toàn hệ thống.
7. **Xác minh:** pending giảm, acquire p99 trở lại ngưỡng, không có connection leak và không làm DB quá tải.

**Không** chỉ nâng borrow timeout để “giảm lỗi”. Điều đó có thể khiến request chờ lâu hơn, tăng backlog và vượt deadline của API. Cũng không nâng connect timeout nếu pool đã tối đa và không được phép tạo thêm connection.

## 15. Runbook B: deadlock hoặc transaction rollback bất thường

**Tín hiệu khởi đầu:** SQLState `40P01` trong PostgreSQL, `40001`/`SQLTransactionRollbackException` hoặc vendor code được xác nhận; kèm tăng số transaction rollback.

**Quy trình:**

1. **Xác định loại lỗi:** deadlock, serialization failure hay lock wait timeout? Không phân loại dựa duy nhất vào `SQLException.getMessage()`.
2. **Lấy bằng chứng DB:** deadlock report, blocking tree, statement và thứ tự lấy khóa; xem transaction nào giữ khóa quá lâu.
3. **Tìm thao tác bị ảnh hưởng:** operation/trace, khóa hàng/bảng, điều kiện `WHERE` và index của các câu `UPDATE`.
4. **Xem thứ tự truy cập tài nguyên:** nếu hai transaction cập nhật các bảng/hàng theo thứ tự đảo nhau, cân nhắc thống nhất thứ tự khi phù hợp.
5. **Giảm phạm vi transaction:** tránh gọi API ngoài DB giữa các lần ghi; giảm thời gian giữ khóa, xem lại số hàng một batch.
6. **Đảm bảo xử lý lỗi đúng:** transaction nạn nhân phải được rollback/xử lý theo hợp đồng DB, không tiếp tục commit các bước còn lại.
7. **Thiết kế retry có giới hạn:** chỉ retry **toàn transaction** cho lỗi đã được xác định an toàn, kèm backoff/jitter và deadline; không retry thao tác có tác động ngoài DB không idempotent.
8. **Đo lại dưới tải:** số deadlock, rollback, lock wait, latency p99 và throughput, không chỉ đo một request.

Deadlock là hiện tượng có thể xuất hiện ngay cả trong hệ thống thiết kế tốt dưới tải cao; một số lượng nhỏ được retry đúng có thể chấp nhận được. Nhưng sự tăng đột biến sau migration, đổi thứ tự cập nhật hoặc thêm index/trigger là tín hiệu cần điều tra.

**Cần phân biệt:** dùng isolation `SERIALIZABLE` có thể tăng số lỗi serialization dù không có deadlock; không tự giảm isolation chỉ để loại bỏ lỗi nếu điều đó phá bất biến nghiệp vụ.

## 16. Runbook C: lỗi kết nối, TLS và trạng thái commit chưa rõ

**Tín hiệu khởi đầu:** nhiều `SQLException` class `08`, pool tạo connection thất bại, mất kết nối giữa SQL hoặc lỗi tại `commit()`.

**Quy trình:**

1. **Xác định thời điểm:** lỗi xảy ra **trước khi có transaction**, lúc thực thi một câu `SELECT`, sau `INSERT` hay trong `commit()`?
2. **Phân loại kết nối:** lỗi DNS, TCP, TLS handshake, credential, server session limit, restart/failover hoặc socket đã bị đóng.
3. **Đối chiếu metric pool và DB:** creation failures/validation failures, active sessions, kết nối bị từ chối, database events.
4. **Kiểm tra thay đổi gần nhất:** secret rotation, certificate expiry, JDBC URL/driver upgrade, network policy, DB failover, pool lifetime.
5. **Phục hồi kết nối:** để pool loại bỏ connection không hợp lệ và cấp phát connection mới theo chính sách implementation; không tự dùng lại kết nối trạng thái nghi vấn.
6. **Nếu lỗi tại commit hoặc sau ghi:** đánh dấu **kết quả transaction chưa xác định** đến khi được đối soát bằng business ID/idempotency key hoặc dữ liệu có thẩm quyền.
7. **Không tự retry mù quáng:** retry một thao tác đọc idempotent khác với replay một `INSERT` có thể đã commit; áp dụng chính sách riêng cho mỗi operation.
8. **Kiểm tra phục hồi:** tỷ lệ lỗi kết nối giảm, TLS/auth xác thực đúng, pool thay connection hỏng, không có dữ liệu ghi trùng/sai.

### Vì sao commit timeout nghiêm trọng?

```text
Ứng dụng                          Database
────────                          ────────
INSERT order ───────────────────► ghi trong transaction
COMMIT ─────────────────────────► có thể đã commit
       ◄─────── kết nối bị ngắt ── không nhận được xác nhận
Ứng dụng thấy SQLException
    │
    └─ KHÔNG biết chắc commit đã xảy ra hay chưa
```

Trong tình huống này, một lần `rollback()` ở client không chứng minh chắc chắn rằng commit ở server chưa hoàn tất. Hệ thống cần cơ chế **idempotent business key**, đối soát trạng thái hoặc transaction/outbox pattern tùy nghiệp vụ.

## 17. Chọn chính sách retry dựa trên ngữ nghĩa thao tác

Retry không phải thuốc chữa chung cho timeout/deadlock/connection error.

| Hoàn cảnh | Có nên retry? | Điều kiện |
| --- | --- | --- |
| `getConnection()` lỗi trước khi gửi SQL | Có thể, có giới hạn | Còn request deadline, backoff và không tạo quá tải |
| `SELECT` idempotent lỗi do connection | Có thể cân nhắc | Đọc không gây side effect; dùng connection mới và giữ semantics |
| Deadlock/serialization failure rõ ràng | Có thể retry **toàn transaction** | Transaction được rollback theo hợp đồng; không chứa side effect ngoài DB không idempotent |
| Query timeout khi `UPDATE` | Không tự retry ngay | Xác định trạng thái transaction và khả năng server đã ghi |
| Lỗi socket sau `INSERT` | Không retry mù quáng | Phải có idempotency/đối soát trước |
| `commit()` báo mất kết nối | Không retry giao dịch như thể chưa commit | Kết quả commit có thể chưa rõ |
| Vi phạm unique/check/foreign key | Thông thường không retry tự động | Đây thường là lỗi dữ liệu/hợp đồng; cần sửa input hoặc luồng nghiệp vụ |
| Pool đầy vì DB quá tải | Retry quá nhanh có hại | Giới hạn concurrency, backoff/jitter, circuit breaker hoặc load shedding khi phù hợp |

Khi retry một transaction do deadlock, nên **bắt đầu transaction mới** và thực thi lại toàn bộ phép đọc/ghi cần thiết; không chỉ chạy lại câu `UPDATE` cuối trong transaction đã thất bại. Thêm **jitter** để nhiều request không lặp lại đồng thời và tạo thêm contention.

Ví dụ pseudocode giới hạn theo deadline:

```java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    deadline.requireTime("before database attempt");

    try {
        runWholeTransaction();
        return;
    } catch (SQLException failure) {
        if (!retryPolicy.isKnownSafeTransactionConflict(failure)
                || attempt == maxAttempts) {
            throw failure;
        }

        // Không tạo một deadline mới cho lần thử sau.
        long delay = Math.min(
                retryPolicy.backoffNanos(attempt),
                deadline.remainingNanos());

        // Pseudocode: cần xử lý InterruptedException,
        // kiểm tra cancellation và ngân sách tối thiểu.
        TimeUnit.NANOSECONDS.sleep(delay);
    }
}
```

Đây là **khung ý tưởng**, giả định `deadline`, `retryPolicy` và `runWholeTransaction()` do ứng dụng định nghĩa. Không dùng mã này để tự retry lỗi commit không rõ hoặc bất kỳ `SQLException` nào: chính sách `isKnownSafeTransactionConflict` phải có test theo driver/database và ranh giới nghiệp vụ.

## 18. Kiểm thử giám sát bằng các lỗi có kiểm soát

Một hệ thống observability chỉ đáng tin khi đã kiểm tra rằng **metric/log/trace thật sự xuất hiện đúng** cho từng tình huống. Không thực hiện fault injection hoặc chặn kết nối trên DB production hay hệ thống dùng chung không được phép.

| Kịch bản | Cách tái hiện trong môi trường thử nghiệm | Bằng chứng mong đợi |
| --- | --- | --- |
| Pool borrow timeout | Đặt max pool nhỏ, giữ hết các connection bằng `CountDownLatch` rồi thử checkout thứ ba | Acquire failure, pool full/pending, không nhầm với connect timeout |
| Physical connection failure | Thử endpoint test không sẵn sàng hoặc TLS/credential sai | Creation/auth/TLS error và connection exception đúng giai đoạn |
| Query timeout | SQL chậm có kiểm soát với `setQueryTimeout(...)` | `phase=execute`, duration, lỗi SQLState/exception phù hợp driver |
| ResultSet fetch chậm | Kết quả lớn hoặc network shaping ở test environment | Đo thời gian `next()`/mapping, không gán hết cho server execute |
| Lock wait | A giữ lock một hàng, B thử cập nhật cùng hàng | Bị blocking và vượt ngưỡng nếu cấu hình; không gắn nhãn deadlock nếu không có vòng chờ |
| Deadlock | A khóa hàng 1 rồi cần hàng 2; B khóa hàng 2 rồi cần hàng 1 | DB deadlock report, một transaction bị hủy, lỗi được phân loại đúng |
| Serialization failure | Hai transaction gây xung đột dưới isolation phù hợp | Transaction rollback signal; thử lại có giới hạn nếu hợp đồng cho phép |
| Commit outcome unknown | Mô phỏng đứt kết nối tại thời điểm commit trong test riêng | Operation marked unknown, không replay ghi mù quáng |
| Connection leak/hold lâu | Giữ connection quá lâu có chủ đích, sau đó đóng | Hold duration tăng, pool metrics thay đổi, metric phục hồi sau release |
| Pool validation failure | Làm hỏng một connection idle trong môi trường riêng | Validation/eviction/creation metrics và recovery |
| Lỗi khi rollback | Mô phỏng lỗi driver/connection ở cleanup | Suppressed/cause được lưu; connection nghi vấn không tái sử dụng sai |

### Điều phối deadlock bằng hai connection

Trong test, mở **hai `Connection` riêng**, đặt `autoCommit=false`, dùng `CountDownLatch` hoặc `CyclicBarrier` để chắc rằng mỗi transaction đã khóa được hàng đầu tiên trước khi thử khóa hàng còn lại. Sau đó cho A cập nhật hàng 2 và B cập nhật hàng 1.

Đảm bảo:

- Mỗi thread **sở hữu connection riêng**, không chia sẻ một `Connection` như mặc định thread-safe.
- Có timeout cho barrier/test để không treo CI vô hạn.
- Bắt và phân loại `SQLException` ở đúng thread, không nuốt exception.
- Rollback cả hai transaction trước khi trả connection về pool.
- Dọn fixture và ghi SQLState/vendor code, DB version, driver version.
- Khẳng định **bất biến dữ liệu và lỗi deadlock thực tế**; không khóa cứng transaction A hay B phải là nạn nhân.

Các engine có thể dùng khóa hàng, gap lock, table lock hoặc snapshot theo cách khác; cần điều chỉnh hai câu `UPDATE` để tạo vòng chờ đúng với database thử nghiệm. Không dùng một test deadlock giả định chung rồi áp dụng tuyệt đối cho mọi sản phẩm.

## 19. Đề xuất dashboard vận hành cho JDBC

Một dashboard nên ưu tiên câu hỏi người trực vận hành cần trả lời nhanh.

### Tầng 1 — Tác động tới người dùng

- Request rate, error rate, latency p50/p95/p99 theo endpoint hoặc operation.
- SLO burn rate và các khung thời gian có regression.
- Số request thất bại sau khi đã retry, phân biệt với số attempt nội bộ.

### Tầng 2 — Kết nối và pool

- Active, idle, pending, maximum pool size cho từng profile.
- Acquire duration, borrow timeout count và connection hold duration.
- Creation/validation failures, số connection đang được tái tạo nếu pool có chỉ số.
- So sánh tổng số connection trên **mọi instance** với giới hạn của DB.

### Tầng 3 — SQL và transaction

- Operation chậm nhất theo p95/p99, số lần thực thi, timeout count.
- Tỷ lệ `BatchUpdateException`, serialization/deadlock candidates và transaction rollback.
- Commit/rollback failures và operation có **unknown outcome**.
- Long-running transaction/lock wait và top blocker từ DBMS.

### Tầng 4 — Sức khỏe hệ quản trị

- CPU, memory, IO, active sessions, connection limit, transaction log nếu có.
- Deadlock event count/server diagnostics.
- Lock wait/blocking chains và query plans cho các operation quan trọng.
- DB restart/failover, TLS/auth failures và sự kiện cấu hình.

**Đọc theo chuỗi nhân quả:** nếu SQL p99 tăng trước, connection hold tăng sau, pool active tăng và cuối cùng acquire timeout tăng, ưu tiên xử lý **SQL/lock** thay vì chỉ tăng pool. Nếu creation failures tăng trước khi pool full, ưu tiên điều tra **endpoint/TLS/network/DB availability**.

## 20. Bài thực hành tổng hợp

### Bài 1 — instrument một repository

Từ `MonitoredCustomerDao` ở phần 7, bổ sung một phương thức `UPDATE inventory` và một `Metrics` implementation ghi histogram/counter bằng công cụ dự án. Đo riêng acquire, execute, result reading (nếu có) và hold. Đối chiếu với latency end-to-end của request.

### Bài 2 — mô phỏng pool bão hòa

Dùng pool tối đa hai connection trong môi trường thử. Mượn hai connection, giữ chúng qua latch có timeout, rồi gọi `getConnection()` thứ ba. Ghi acquire latency, loại lỗi, active/idle/pending và thời gian hold; giải thích vì sao đây không phải bằng chứng server tạo connection chậm.

### Bài 3 — deadlock và lock wait

Tạo hai transaction dùng hai connection như phần 18. Thử lần đầu chỉ gây một transaction chờ khóa rồi được giải phóng; lần hai tạo vòng chờ thật. So sánh SQLState, vendor code, DB logs và trạng thái rollback; không dán nhãn tất cả lỗi timeout là deadlock.

### Bài 4 — lỗi kết nối ở ba giai đoạn

Trong database thử nghiệm, tạo những lỗi có kiểm soát khi **mở kết nối**, khi **chạy query**, và khi **commit**. Ghi các giai đoạn khác nhau, xác định trường hợp nào có thể retry an toàn và trường hợp nào cần đối soát trạng thái ghi.

### Bài 5 — thiết kế alert và runbook

Thiết kế ba cảnh báo:

1. Pool borrow timeout tăng đồng thời pending tăng.
2. Deadlock/serialization count tăng cùng transaction rollback.
3. Connection creation failures tăng hoặc xuất hiện commit outcome unknown.

Với mỗi cảnh báo, ghi **điều kiện kích hoạt**, **bằng chứng cần kiểm tra**, **người/nhóm xử lý**, **hành động giảm tác động**, **tiêu chí kết thúc sự cố**. Không đặt ngưỡng tùy ý khi chưa có baseline/SLO.

### Câu hỏi tự kiểm tra

- Một `getConnection()` mất 3 giây có chứng minh TCP/TLS handshake mất 3 giây không?
- `SQLTimeoutException` xảy ra trong một `UPDATE` có chứng minh chưa có hàng nào được ghi không?
- Một session đang đợi khóa có phải deadlock không? Cần thêm dấu hiệu nào?
- Tại sao SQLState `40001` không đủ để khẳng định đó là deadlock trên mọi DB?
- Vì sao một query nhanh nhưng `ResultSet.next()` chậm vẫn có thể làm pool cạn?
- Nên làm gì khi `Connection.commit()` ném lỗi mất kết nối?
- Tại sao retry toàn bộ transaction sau serialization failure khác với retry riêng câu `UPDATE` cuối?
- Vì sao không dùng raw JDBC URL và SQL parameters làm nhãn Prometheus?
- Trong trường hợp pool full do transaction giữ connection lâu, tăng max pool có thể gây hậu quả gì?
- Vì sao deadlock report của DB và SQLState của JDBC nên được đối chiếu cùng trace thay vì chỉ dựa một nguồn?

## 21. Checklist giám sát vận hành

- [ ] Có đo **acquire duration**, statement duration, thời gian đọc kết quả và connection hold duration.
- [ ] Có metric pool **active/idle/pending/max** và số lần borrow timeout, creation/validation failure.
- [ ] Có phân loại lỗi theo **phase**, `SQLException` class, SQLState, vendor code, next/suppressed exceptions.
- [ ] Có tách lock wait, deadlock, serialization failure và query timeout trong runbook.
- [ ] Có dữ liệu DBMS về blocking tree/deadlock, long transaction, session limit và health.
- [ ] Có trace ID/operation name để tương quan Java request với SQL và DB events.
- [ ] Không log secret, raw JDBC URL, tham số nhạy cảm hoặc tạo metric label cardinality cao.
- [ ] Có theo dõi commit/rollback errors và đánh dấu **unknown transaction outcome** khi cần.
- [ ] Có retry policy chỉ cho lỗi/operation **an toàn**, giới hạn attempt, backoff và deadline.
- [ ] Có integration test tái hiện pool full, timeout, deadlock, lỗi kết nối và cleanup.
- [ ] Có cảnh báo dựa trên SLO/tác động, không chỉ một ngưỡng SQL exception count.
- [ ] Có quy trình phối hợp application owner, DBA, mạng/bảo mật và nhóm vận hành khi sự cố vượt một tầng.

## 22. Tổng kết

1. **Đặt lỗi vào đúng giai đoạn của JDBC**: acquire, execute, fetch, commit, rollback hay close. Cùng một `SQLException` có thể mang rủi ro khác nhau tùy lúc xảy ra.
2. **Đo cả ứng dụng, pool và database**. Không thể quy `getConnection()` chậm thành tạo connection chậm, hoặc timeout `UPDATE` thành deadlock nếu chưa có bằng chứng.
3. **Phân biệt deadlock, lock wait và serialization failure**. SQLState/vendor code là tín hiệu hỗ trợ, còn DB logs và lock graph giúp xác nhận nguyên nhân.
4. **Theo dõi vòng đời transaction đến kết quả cuối cùng**. `cancel()`/timeout không chứng minh rollback; lỗi `commit()` có thể để lại trạng thái chưa rõ.
5. **Không dùng retry mù quáng để che lỗi**. Chỉ retry lỗi được xác định, trong ngân sách thời gian còn lại, với idempotency/đối soát phù hợp.
6. **Giữ dữ liệu giám sát an toàn và hữu ích**. Dùng operation name, phase, profile và trace; tránh secret, PII và metric labels có cardinality cao.
7. **Kiểm thử cảnh báo và runbook**, không chỉ kiểm thử nghiệp vụ. Mục tiêu là phát hiện nhanh, giảm tác động và chứng minh hệ thống trở lại trạng thái ổn định.

**Kết luận:** theo dõi timeout, bế tắc và lỗi kết nối trong JDBC không chỉ là đếm ngoại lệ. Một hệ thống quan sát tốt phải nối được **trạng thái pool, giai đoạn SQL, mã lỗi, sự kiện transaction và bằng chứng từ DBMS** để phân biệt triệu chứng với nguyên nhân. Nhờ vậy, nhóm vận hành có thể tối ưu đúng nút thắt, xử lý an toàn những transaction chưa rõ kết quả và bảo vệ độ tin cậy của ứng dụng Java khi tải và sự cố thay đổi.

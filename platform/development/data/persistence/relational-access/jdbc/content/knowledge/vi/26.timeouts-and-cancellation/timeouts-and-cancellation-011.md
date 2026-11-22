# Kiểm thử hành vi timeout trên driver và môi trường thực tế trong JDBC

Trong ứng dụng Java dùng JDBC, đặt `Statement.setQueryTimeout(2)` không có nghĩa chắc chắn mọi truy vấn sẽ dừng sau đúng hai giây. Timeout có thể được thực thi ở **pool, driver, mạng, DBMS, khóa hoặc tầng request**; mỗi nơi có đồng hồ, đơn vị thời gian, phạm vi tác động và cách báo lỗi khác nhau. Một driver có thể gửi yêu cầu hủy SQL khi hết thời gian, driver khác có thể đóng connection, còn hệ quản trị có thể chỉ dừng statement hoặc đặt toàn bộ transaction vào trạng thái lỗi.

Vì vậy, bài toán không phải chỉ là **cấu hình timeout**, mà là **kiểm thử hành vi thực tế**: lệnh có thực sự dừng không, sau bao lâu, ngoại lệ gì được ném ra, transaction còn dùng được không, connection có an toàn để trả pool không và liệu dữ liệu đã được commit hay chưa.

Bài thuộc chương **Timeout và hủy** trong module JDBC, tập trung vào các phép thử có thể lặp lại trên chính phiên bản Java, JDBC driver, `DataSource`/connection pool và DBMS của dự án. Ví dụ Java/SQL sử dụng PostgreSQL để dựng tình huống có thể kiểm soát; cách kết luận và bộ tiêu chí kiểm thử có thể áp dụng cho những DBMS khác sau khi điều chỉnh cú pháp và cấu hình.

## 1. Cần phân biệt những loại timeout nào?

Một request HTTP gọi tới database thường đi qua nhiều giai đoạn:

```text
Client / HTTP deadline
         |
         v
Ứng dụng -> chờ connection trong pool
         |
         v
JDBC driver -> mở/authenticate kết nối (nếu cần)
         |
         v
Gửi SQL -> DBMS nhận SQL
         |
         +--> chờ khóa
         |
         +--> thực thi truy vấn
         |
         +--> fetch các hàng / đọc phản hồi mạng
         |
         v
commit/rollback -> trả connection về pool
```

Mỗi giai đoạn có thể chịu một timeout khác nhau:

| Lớp | API hoặc cấu hình điển hình | Đơn vị | Giới hạn tác động |
|---|---|---|---|
| Chờ mượn connection từ pool | Thuộc tính *connection acquisition timeout* của pool | Thường ms | Chỉ giai đoạn chờ một connection khả dụng |
| Login vào DB | `DataSource.setLoginTimeout(int)`, `DriverManager.setLoginTimeout(int)` | Giây | Giai đoạn thiết lập kết nối theo khả năng driver |
| TCP connect/socket | Thuộc tính driver hoặc OS, ví dụ *connect timeout*, *socket/read timeout* | Tùy driver | Kết nối hoặc truyền nhận dữ liệu qua mạng |
| Chạy một statement JDBC | `Statement.setQueryTimeout(int)` | Giây | Thời gian driver cho phép một statement thực thi theo hợp đồng hỗ trợ |
| Hủy chủ động | `Statement.cancel()` | Không phải timeout | Yêu cầu driver hủy statement đang chạy, thường từ thread khác |
| Hoạt động mạng của connection | `Connection.setNetworkTimeout(Executor, int)` | Mili giây | Thời gian chờ thao tác mạng theo driver, có thể dẫn tới đóng connection |
| Thực thi SQL phía DB | PostgreSQL `statement_timeout` | Mili giây khi cấu hình bằng `ms` | Chính sách thời gian thực thi statement trên DBMS |
| Chờ khóa | PostgreSQL `lock_timeout`, MySQL InnoDB `innodb_lock_wait_timeout` | Tùy DBMS | Thời gian chờ khóa, **không phải** tổng thời gian query |
| Transaction/phiên nhàn rỗi | PostgreSQL `idle_in_transaction_session_timeout` | ms khi cấu hình tương ứng | Kiểm soát session giữ transaction nhưng không thực thi lệnh |
| Nghiệp vụ/request | Deadline HTTP/gRPC, job hoặc queue consumer | Tùy framework | Thời gian tối đa một yêu cầu được phép chiếm |

Không có một “timeout JDBC tổng” áp dụng thống nhất cho tất cả các hàng trong bảng. Ví dụ, **query timeout không giới hạn thời gian chờ mượn connection từ pool**, còn timeout chờ khóa không hạn chế một truy vấn tính toán dài nhưng không đụng khóa.

## 2. Điều cần xác minh, thay vì chỉ xem setter có thành công

Một phép thử đáng tin phải trả lời tối thiểu sáu câu hỏi:

1. **Điểm bắt đầu:** đồng hồ bắt đầu khi gọi `getConnection()`, `executeQuery()`, `rs.next()` hay `commit()`?
2. **Nguyên nhân:** timeout đến từ client driver, DBMS, lock manager, connection pool hay request deadline?
3. **Khoảng thời gian đo được:** lệnh có dừng trong khoảng hợp lý, hay vẫn chạy lâu hơn timeout được cấu hình?
4. **Tín hiệu:** nhận được `SQLTimeoutException`, `SQLException` với `SQLState` nào, exception của pool hay lỗi mạng?
5. **Trạng thái sau lỗi:** transaction có cần rollback không; connection còn `isValid(...)` không và có được phép tái sử dụng không?
6. **Tác động dữ liệu:** thay đổi có bị hủy, vẫn chưa commit hay có khả năng đã commit dù client không nhận được phản hồi?

Một bài test chỉ viết:

```java
ps.setQueryTimeout(2);
assertEquals(2, ps.getQueryTimeout());
```

mới chứng minh driver lưu/báo lại giá trị cấu hình (nếu API được hỗ trợ). Nó **không** chứng minh query đã được hủy sau hai giây, server đã ngừng xử lý, khóa đã được giải phóng hay connection vẫn sạch.

## 3. Chuẩn bị môi trường kiểm thử có thể lặp lại

Để quan sát timeout mà không ảnh hưởng dữ liệu thật:

- Dùng **database thử nghiệm riêng**, có thể là PostgreSQL trong container/lab, với schema và tài khoản có quyền hạn phù hợp. Không cố tình kéo dài hoặc khóa các transaction trên production.
- Ghi **Java version, JDBC driver version, DBMS version, connection-pool implementation/version**, cấu hình timeout và mạng. Kết quả trên H2 hoặc một driver giả lập không chứng minh hành vi của PostgreSQL/MySQL production.
- Cố định một **kịch bản gây chậm rõ ràng** và một kịch bản đối chứng bình thường. Với PostgreSQL, `pg_sleep(...)` giúp mô phỏng server xử lý chậm; hai connection tranh cùng một hàng giúp mô phỏng chờ khóa.
- Đo bằng `System.nanoTime()` để tính **elapsed time** thay vì đồng hồ hệ thống có thể được điều chỉnh. Đồng hồ này chỉ phản ánh thời gian phía Java nhìn thấy, không phải thời gian thực thi server chính xác.
- Lặp lại nhiều lần trong phạm vi test hợp lý, chú ý warm-up, CPU tải cao, GC, mạng, CI worker bị chậm và độ trễ driver/pool. Không assert chính xác từng mili giây.
- Giữ thời gian truy vấn thử nghiệm **dài hơn đáng kể** timeout cần kiểm tra để phân biệt lệnh đã bị hủy với lệnh tự hoàn tất.
- Đảm bảo có **deadline bên ngoài phép thử** để ngăn test treo vô hạn. Timeout của test runner không thay thế việc dọn connection/DB nếu driver không đáp ứng hủy.

Ví dụ hồ sơ cấu hình để ghi cùng kết quả:

```text
Java: 21
DBMS: PostgreSQL, version ghi từ DatabaseMetaData
Driver: pgJDBC, version ghi từ DatabaseMetaData
Pool: implementation/version ghi từ ứng dụng
autoCommit: true hoặc false (ghi rõ)
JDBC queryTimeout: 1 giây
DB statement_timeout: đọc current_setting(...)
SQL: SELECT pg_sleep(...)
Thời gian đo: System.nanoTime()
SQLState/vendor code: lấy từ SQLException
Kết quả transaction/connection: xác minh riêng
```

Phiên bản Java 21 chỉ là ví dụ; code trong bài có thể dùng phiên bản Java tương thích với những API được minh họa. Trước khi kết luận, phải thay dữ liệu hồ sơ bằng thông tin **thực tế** của hệ thống test.

## 4. Phép thử đầu tiên: `Statement.setQueryTimeout(...)`

### 4.1. Ý nghĩa hợp đồng API

`Statement.setQueryTimeout(int seconds)` yêu cầu số giây tối đa driver cho phép một statement thực thi. Giá trị `0` được JDBC định nghĩa là **không giới hạn** thời gian thực thi ở lớp query-timeout này; nó không tắt các timeout của server, mạng hay request.

`Statement.getQueryTimeout()` cho biết giá trị driver đang báo lại. `SQLTimeoutException` có thể được ném khi driver xác định query timeout; nhưng driver và DBMS cũng có thể báo một `SQLException` khác hoặc mã SQLSTATE đặc thù. Vì vậy nên ghi **cả class ngoại lệ, SQLState, vendor code và toàn bộ exception chain**.

Nếu driver không hỗ trợ khả năng được yêu cầu, có thể gặp `SQLFeatureNotSupportedException` hoặc lỗi tương ứng. Không được bắt mọi exception rồi giả định query đã được hủy thành công.

### 4.2. Mã Java đo một truy vấn chậm có chủ đích

Ví dụ dùng `SELECT pg_sleep(...)` của PostgreSQL. Giá trị ngủ năm giây lớn hơn nhiều so với query timeout một giây. Mã thử nghiệm lấy connection qua `DataSource`, tạo `PreparedStatement` và đo thời gian quanh `executeQuery()`:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;

public final class QueryTimeoutProbe {
    private QueryTimeoutProbe() {
    }

    public static void run(DataSource source) throws SQLException {
        String sql =
                "SELECT pg_sleep(CAST(? AS double precision))";

        try (Connection connection = source.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {

            ps.setDouble(1, 5.0);
            ps.setQueryTimeout(1);

            System.out.println("Requested query timeout: 1 s");
            System.out.println("Reported query timeout: "
                    + ps.getQueryTimeout() + " s");

            long started = System.nanoTime();

            try (ResultSet ignored = ps.executeQuery()) {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - started);

                System.out.println("Query completed in "
                        + elapsedMs + " ms");
                // Nếu query hoàn tất sau khoảng 5 giây, timeout
                // chưa hoạt động như test kỳ vọng.
            } catch (SQLException error) {
                long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                        System.nanoTime() - started);

                System.out.println("Query failed after "
                        + elapsedMs + " ms");
                System.out.println("Exception type: "
                        + error.getClass().getName());
                System.out.println("SQLState: "
                        + error.getSQLState());
                System.out.println("Vendor code: "
                        + error.getErrorCode());

                // Trong một phép đo có chủ đích, giữ lỗi để
                // test runner xác nhận loại lỗi được mong đợi.
                throw error;
            }
        }
    }
}
```

Gọi trong bộ kiểm thử tích hợp bằng một `DataSource` dành riêng cho PostgreSQL. Khi test được mong đợi gây timeout, cần bắt ngoại lệ ở **lớp test** và xác minh nó phản ánh hủy/timeout, không phải lỗi cú pháp hay mất quyền:

```java
// Mã trong @Test với dataSource test đã cấu hình:
long begin = System.nanoTime();

SQLException error = org.junit.jupiter.api.Assertions.assertThrows(
        SQLException.class,
        () -> QueryTimeoutProbe.run(dataSource));

long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
        System.nanoTime() - begin);

System.out.println("Test-level elapsed = " + elapsedMs + " ms");
System.out.println("SQLState = " + error.getSQLState());
```

Đo ở tầng test bao gồm cả thời gian lấy/đóng connection, không trùng chính xác với khoảng đo quanh `executeQuery()` trong probe. Đây là hai số có chủ ý khác nhau.

### 4.3. Cách đánh giá kết quả

Một phép thử đạt yêu cầu có thể ghi nhận:

- Câu SQL bị từ chối hoặc hủy rõ ràng vì timeout, thay vì chạy hết năm giây bình thường.
- Khoảng elapsed gần mức timeout hợp lý có tính đến overhead, không đòi chính xác `1000ms`.
- Exception có mã và message phù hợp với driver/DBMS; ghi lại khi driver thay đổi giữa các phiên bản.
- Connection/transaction được dọn theo chính sách và không còn truy vấn server-side tiếp tục giữ tài nguyên bất thường.

**Không viết assert cứng kiểu `elapsedMs == 1000`**. Ngay cả giới hạn `elapsedMs < 1500` cũng dễ gây flaky test trên CI chậm. Hãy chọn biên dung sai dựa trên khoảng cách giữa truy vấn bình thường 5 giây và timeout 1 giây; nếu quá tải, báo kết quả **không xác định** thay vì khẳng định JDBC sai.

Với PostgreSQL, việc hủy statement thường có thể xuất hiện dưới SQLSTATE `57014` (*query_canceled*), nhưng không được coi đó là mã duy nhất cho **mọi** nguyên nhân timeout của JDBC. Một lỗi network timeout có thể có mã khác hoàn toàn.

## 5. Phân biệt client query timeout và server `statement_timeout`

Trên PostgreSQL, `statement_timeout` giới hạn thời gian thực thi statement theo quy tắc của database. Nó là **cấu hình phía DBMS**, độc lập với `Statement.setQueryTimeout(...)` trên Java.

Ví dụ kiểm tra phía database:

```sql
SHOW statement_timeout;

SELECT current_setting('statement_timeout');
```

Có thể dùng `SET LOCAL` để đặt timeout **chỉ trong một transaction thử nghiệm**, giảm nguy cơ để lại trạng thái phiên trong pooled connection:

```sql
BEGIN;
SET LOCAL statement_timeout = '800ms';
SELECT pg_sleep(5);
-- Mong đợi statement bị PostgreSQL hủy do timeout.
ROLLBACK;
```

Khi `SELECT` bị hủy trong transaction PostgreSQL, các lệnh tiếp theo thường không chạy bình thường cho đến khi transaction được rollback. Trong ứng dụng JDBC, hãy gọi `connection.rollback()` trong nhánh xử lý lỗi thay vì tiếp tục query trên transaction lỗi.

### 5.1. Java kiểm thử timeout phía server

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;

public final class ServerTimeoutProbe {
    private ServerTimeoutProbe() {}

    public static void run(DataSource source) throws SQLException {
        try (Connection connection = source.getConnection()) {
            connection.setAutoCommit(false);

            try {
                try (Statement st = connection.createStatement()) {
                    // PostgreSQL: chỉ áp dụng trong transaction.
                    st.execute("SET LOCAL statement_timeout = '800ms'");

                    // Query timeout JDBC dài hơn server timeout
                    // để dễ quan sát server timeout.
                    st.setQueryTimeout(5);
                    st.executeQuery("SELECT pg_sleep(5)").close();
                }

                // Nếu không có timeout (khác kỳ vọng), kết thúc
                // transaction thử nghiệm sạch sẽ.
                connection.rollback();

            } catch (SQLException failure) {
                System.out.println("Server probe SQLState: "
                        + failure.getSQLState());

                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }

                throw failure;
            }
        }
    }
}
```

Đoạn này thử nghiệm một statement bị hủy trong transaction, không thao tác dữ liệu nghiệp vụ. Một bài test có thể so sánh với trường hợp **đổi lại thứ tự** thời hạn: query timeout JDBC ngắn hơn server timeout. Mục tiêu là xác định **lớp nào chấm dứt trước** và nó báo lỗi thế nào, không đoán từ mỗi giá trị setter.

Nếu driver triển khai query timeout bằng cách gửi một yêu cầu cancel đến server, kết quả quan sát cũng có thể là một lỗi cancellation do server phát ra. Chỉ dựa vào SQLSTATE hoặc message không phải lúc nào cũng phân biệt được **ai là bên ra quyết định ban đầu**; cần bổ sung thông tin cấu hình, log, trace, metrics.

### 5.2. Các deadline chồng lên nhau

Ví dụ:

```text
Request deadline                 3.0 s
Pool acquisition timeout         0.5 s
Statement.setQueryTimeout(...)   2.0 s
DB statement_timeout             1.5 s
Network timeout                  4.0 s
```

Nếu connection có ngay và SQL chạy dài, server timeout 1,5 giây thường có cơ hội xảy ra trước query timeout 2 giây. Nhưng nếu request đã mất 1,8 giây trước khi chạy SQL, **deadline request** có thể kết thúc trước. Thời gian các lớp không luôn cộng tuyến tính và khả năng các timeout chồng lên nhau phụ thuộc cách framework/driver triển khai.

Để phân tích lỗi, ghi nhận **thời điểm vào từng giai đoạn** thay vì chỉ tổng thời gian request.

## 6. Kiểm thử timeout khi chờ khóa

`pg_sleep` kiểm tra query chậm mà không cần tranh chấp dữ liệu. Nó **không đại diện cho mọi tình huống khóa**. Để thử lock timeout hoặc deadlock, cần có ít nhất hai connection và một hàng dữ liệu.

Tạo bảng riêng cho test:

```sql
CREATE TABLE timeout_lab_items (
    id       BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL
);

INSERT INTO timeout_lab_items(id, quantity)
VALUES (1, 10);
```

Mở hai SQL session độc lập, **A** và **B**.

**Session A — giữ khóa hàng trong transaction:**

```sql
BEGIN;

SELECT id, quantity
FROM timeout_lab_items
WHERE id = 1
FOR UPDATE;

-- Giữ transaction mở trong lúc session B chạy.
-- Cuối bài thử: ROLLBACK;
```

**Session B — yêu cầu UPDATE cùng hàng, giới hạn thời gian chờ:**

```sql
BEGIN;

SET LOCAL lock_timeout = '800ms';

UPDATE timeout_lab_items
SET quantity = quantity - 1
WHERE id = 1;

-- Khi timeout: mong đợi lỗi chờ khóa.
ROLLBACK;
```

Sau đó quay lại **Session A** và chạy `ROLLBACK;` để giải phóng khóa.

Đối với PostgreSQL, lock timeout có thể được báo bằng SQLSTATE `55P03` (*lock_not_available*). Nếu đồng thời áp đặt `statement_timeout` ngắn hơn, statement timeout có thể xảy ra trước và che giấu lỗi chờ khóa. Vì vậy nên thiết lập môi trường có **lock timeout ngắn hơn statement timeout**, và ghi rõ cả hai giá trị.

### Điều cần kiểm tra trong bài thử chờ khóa

1. A thực sự giữ khóa trên hàng mục tiêu trước khi B chạy. Nếu A đã commit hoặc rollback, B có thể chạy ngay và test mất ý nghĩa.
2. B bị chặn **vì khóa**, không phải query chậm do bảng lớn hoặc thiếu index.
3. Ngoại lệ B phản ánh đúng loại lỗi theo DBMS, thời gian chờ nằm trong khoảng hợp lý.
4. B kết thúc transaction lỗi bằng rollback; A cũng được rollback trong `finally`/bước cleanup.
5. Sau test, không có connection giữ khóa hay transaction idle, pool trở về trạng thái bình thường.
6. Thử lại đối chứng khi A **không giữ khóa**; câu UPDATE của B phải hoàn tất bình thường.

Với MySQL InnoDB, `innodb_lock_wait_timeout` có ngữ nghĩa khác PostgreSQL: theo cấu hình mặc định thường **chỉ statement bị rollback** sau lock wait timeout, không tự rollback toàn transaction. Hệ thống dùng JDBC nên chủ động rollback **toàn bộ transaction nghiệp vụ** nếu không muốn tiếp tục từ trạng thái đã xử lý một phần. Deadlock cũng có cơ chế hủy riêng.

**Không áp dụng SQLSTATE `55P03` như luật chung cho mọi DBMS.** Hãy dùng vendor error code, SQLSTATE, cấu hình và trạng thái DB tương ứng.

## 7. Kiểm thử `Statement.cancel()` khác gì timeout?

`Statement.cancel()` là lệnh **yêu cầu hủy một statement đang chạy**; nó không tự đặt một mốc thời gian. JDBC cho phép ứng dụng gọi cancel, thường từ **một thread khác** khi thread đang chạy SQL bị chặn.

```text
Thread truy vấn                      Thread điều khiển
       |                                   |
       |  statement.executeQuery()         |
       |  (SQL chạy lâu)                    |
       |                                   |  người dùng nhấn Hủy
       |<------------- statement.cancel() --|
       |                                   |
       |  Có thể ném SQLException          |
       |  hoặc hoàn tất trước cancel       |
       |                                   |
       v                                   v
     Cleanup                            Ghi kết quả
```

Lưu ý:

- `cancel()` có thể thất bại, không được hỗ trợ hoặc gửi yêu cầu hủy nhưng DB vẫn cần thời gian để đáp ứng.
- Nếu statement vừa hoàn thành trước khi `cancel()` được xử lý, việc cancel có thể **không tạo exception**.
- `cancel()` không đồng nghĩa với `Connection.rollback()`. Nếu transaction ở trạng thái lỗi hoặc đã cập nhật một phần, chủ transaction vẫn phải quyết định rollback.
- Ngoại lệ do cancel có thể là `SQLException` chung hoặc mang SQLSTATE của DBMS; không giả định phải là `SQLTimeoutException`.
- Một statement và connection JDBC nói chung không phải object để nhiều thread tự do chạy thao tác SQL đồng thời. Việc gọi **`Statement.cancel()` từ thread điều khiển** là trường hợp API dự kiến; không lấy đó làm bằng chứng mọi phương thức JDBC đều thread-safe.

### 7.1. Một phép thử cancel có điều phối

Trong integration test, có thể tổ chức như sau:

1. Thread A mượn connection riêng, tạo `Statement` và chia sẻ **tham chiếu statement chỉ cho mục đích cancel**.
2. Thread A bắt đầu `executeQuery("SELECT pg_sleep(10)")`.
3. Thread B xác nhận A đã tới bước execute (ví dụ bằng `CountDownLatch`) và yêu cầu `statement.cancel()` sau một khoảng ngắn được kiểm soát.
4. Thread A thu kết quả: exception, thời gian hoàn thành, SQLState và trạng thái transaction; đóng statement/connection trong `finally`.
5. Test xác nhận A không treo vô hạn và không để statement còn chạy trên server. Nếu cancel không có tác dụng trên driver cần thiết, coi đó là **hạn chế cần giải quyết** chứ không bỏ qua.

Mã minh họa phần điều phối:

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public static void exerciseCancel(javax.sql.DataSource source)
        throws Exception {

    ExecutorService worker = Executors.newSingleThreadExecutor();
    CountDownLatch ready = new CountDownLatch(1);
    AtomicReference<Statement> active = new AtomicReference<>();

    Future<?> operation = worker.submit(() -> {
        try (Connection connection = source.getConnection();
             Statement st = connection.createStatement()) {

            active.set(st);
            ready.countDown();

            // Dùng PostgreSQL lab để tạo statement đủ dài.
            st.execute("SELECT pg_sleep(10)");

        } catch (SQLException error) {
            System.out.println("Worker SQLState="
                    + error.getSQLState());
        }
    });

    try {
        if (!ready.await(3, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                    "Worker chưa tạo statement");
        }

        // Chừa khoảng ngắn để query có cơ hội bắt đầu.
        // Đây không phải đồng bộ tuyệt đối với thời điểm server chạy.
        Thread.sleep(250);

        Statement st = active.get();
        if (st != null && !st.isClosed()) {
            st.cancel();
        }

        // Timeout của Future chỉ bảo vệ test thread:
        // nó KHÔNG chứng minh SQL phía server đã dừng.
        operation.get(5, TimeUnit.SECONDS);

    } finally {
        operation.cancel(true);
        worker.shutdownNow();
    }
}
```

Đây là đoạn mã **thực hành** đặt trong lớp test có import phù hợp, không phải thư viện cancellation hoàn chỉnh. `Future.cancel(true)` và `ExecutorService.shutdownNow()` gửi tín hiệu ngắt thread Java nhưng **không bảo đảm** JDBC query bị hủy, connection đóng tức thì hoặc server đã ngừng thực thi. Khi phép thử vượt deadline, cần cơ chế quản lý tài nguyên và quan sát phía DB độc lập; không để test chạy vô hạn trong một thread mà driver không thể hủy.

Vì có race giữa thời điểm statement bắt đầu chạy và thời điểm cancel được gửi, hãy lặp phép thử vài lần và phân loại **cancel thành công**, **query hoàn tất trước cancel**, **cancel không hỗ trợ**, **timeout/hang**. Không coi mọi lần kết thúc nhanh là bằng chứng cancel thành công.

## 8. Kiểm thử `Connection.setNetworkTimeout(...)`

`Connection.setNetworkTimeout(Executor executor, int milliseconds)` thiết lập mức timeout cho hoạt động network của connection theo khả năng driver. Đây **không phải** cách khác để viết `Statement.setQueryTimeout(...)`.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class NetworkTimeoutProbe {
    private NetworkTimeoutProbe() {
    }

    public static void showConfiguredValue(DataSource source)
            throws SQLException {

        ExecutorService timeoutExecutor =
                Executors.newSingleThreadExecutor();

        try (Connection connection = source.getConnection()) {
            connection.setNetworkTimeout(timeoutExecutor, 2_000);

            System.out.println("Network timeout (ms) = "
                    + connection.getNetworkTimeout());

        } finally {
            timeoutExecutor.shutdownNow();
        }
    }
}
```

Hàm chỉ kiểm tra việc **cấu hình và đọc lại** giá trị 2.000 ms. Nó **chưa** kiểm thử timeout mạng thật.

Để kiểm thử mạng, cần một tình huống do môi trường test kiểm soát: proxy mạng có thể trì hoãn hoặc cắt phản hồi, database test bị tách mạng có thời hạn, hoặc fault injection ở mức TCP. Một `pg_sleep` dài đôi khi giúp quan sát socket đọc nhưng không chứng minh chính xác **loại timeout network** của driver; một số driver triển khai cancellation/streaming khác nhau.

Hãy ghi:

- Network timeout được báo lại qua `getNetworkTimeout()`.
- Thời gian từ thao tác JDBC đến exception.
- Loại exception, SQLState, vendor code và cause chain.
- Trạng thái `connection.isClosed()` và `connection.isValid(...)`, nếu có thể kiểm tra an toàn.
- Pool có loại bỏ connection lỗi và cấp connection khỏe mới không.
- Có còn transaction/khóa hoặc SQL chạy dở phía DB không.

Theo hợp đồng JDBC, lỗi network timeout có thể khiến driver đánh dấu connection không còn dùng được và đóng connection để giải phóng tài nguyên. **Không đưa connection có tình trạng mạng không chắc chắn trở về luồng nghiệp vụ như thể nó vẫn sạch.** Để pool quyết định evict/replace theo API của implementation.

## 9. Timeout mượn kết nối và login timeout

### 9.1. Timeout chờ connection từ pool

Một HTTP request có thể bị trễ ngay ở `dataSource.getConnection()` vì pool hết connection. Lúc này `Statement.setQueryTimeout(...)` **chưa được áp dụng**, bởi statement thậm chí chưa được tạo.

Phép thử đơn giản:

- Cấu hình **pool dành riêng cho test** với tối đa một connection khả dụng và acquisition timeout, ví dụ khoảng 500 ms.
- Borrow A và giữ nó mở.
- Thử borrow B khi A chưa trả.
- Đo thời gian chờ và loại exception của implementation.
- Trả A, thử borrow C và xác minh pool hoạt động bình thường.

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.concurrent.TimeUnit;

public static void probePoolAcquisition(DataSource testPool)
        throws SQLException {

    // Điều kiện test: pool có tối đa 1 connection
    // và timeout chờ borrow được cấu hình riêng.
    try (Connection held = testPool.getConnection()) {
        long started = System.nanoTime();

        try (Connection unexpected = testPool.getConnection()) {
            System.out.println(
                    "Pool cấp connection thứ hai; xem lại cấu hình test");
        } catch (SQLException error) {
            long elapsedMs = TimeUnit.NANOSECONDS.toMillis(
                    System.nanoTime() - started);

            System.out.println("Pool wait = " + elapsedMs + " ms");
            System.out.println("Exception = " + error);
        }
    }
}
```

Một số pool ném `SQLException`, một số framework bọc lỗi thành exception riêng. Ví dụ chỉ bắt `SQLException` để minh họa JDBC; bộ test thực tế phải phân loại theo pool đang dùng và không coi mọi `SQLException` là timeout. **Không thực hiện phép thử cố tình làm cạn pool trên pool đang phục vụ người dùng.**

### 9.2. `DataSource.setLoginTimeout(...)`

`DataSource.setLoginTimeout(int seconds)` và `DriverManager.setLoginTimeout(int seconds)` liên quan đến việc thiết lập kết nối, không phải thời gian chờ một connection **đang được pool giữ** trở nên rảnh.

Với một số driver hoặc pool, login timeout được áp dụng khác nhau hoặc cần cấu hình riêng. Không coi `dataSource.setLoginTimeout(1)` là cách chuẩn để ấn định acquisition timeout cho mọi pool. Cần kiểm tra setter/getter, điều kiện login lỗi có kiểm soát, và kết quả thực tế trên nhà cung cấp đang dùng.

Các lỗi xác thực do sai mật khẩu/thếu quyền thường **không trở nên thành công nhờ retry vô hạn**. Đừng dùng lỗi xác thực làm phép thử timeout trừ khi bạn đang kiểm tra loại lỗi phân biệt rõ ràng.

## 10. Timeout trong transaction: điều gì đã được commit?

Đây là phần quan trọng nhất khi quyết định test **PASS** về dữ liệu.

Giả sử transaction gồm hai bước:

```java
connection.setAutoCommit(false);

try {
    debitAccount(connection, fromId, amount);
    updateDestination(connection, toId, amount); // có thể timeout
    connection.commit();
} catch (SQLException failure) {
    connection.rollback();
    throw failure;
}
```

Đoạn trên là **mẫu rút gọn** để diễn giải; code production cần `try-with-resources`, xử lý rollback lỗi và phân biệt trạng thái commit chưa rõ. Khi bước thứ hai timeout, bước đầu **có thể đã chạy** nhưng còn chưa commit. Với một transaction có thể rollback và connection còn sử dụng được, rollback phải hoàn tác cả thay đổi trước đó.

Tuy nhiên:

- Trên PostgreSQL, một lỗi SQL trong transaction thường khiến transaction lỗi cho đến khi `rollback()`.
- Trên MySQL InnoDB, lock wait timeout có thể chỉ hủy statement ở chế độ mặc định. Nếu không rollback toàn transaction, các lệnh trước đó có thể vẫn tồn tại và còn có thể được commit.
- Có driver/socket timeout dẫn đến **connection mất khả năng sử dụng**, khiến `rollback()` cũng ném lỗi. Cần ghi nhận lỗi này và không tự cho rằng dữ liệu đã được hủy.
- Nếu timeout hoặc mất kết nối xảy ra trong hoặc sau `commit()`, **trạng thái cuối cùng có thể không rõ**: DBMS có thể đã commit nhưng phản hồi bị mất.

Khi commit chưa rõ, cách xử lý an toàn là dùng mã yêu cầu nghiệp vụ ổn định (`request_id`), thiết kế idempotency và tra cứu/đối soát kết quả trước khi thử lại. Không retry mù toàn bộ giao dịch chỉ vì nhận `SQLTimeoutException` hoặc `SQLTransientConnectionException`.

### 10.1. Mẫu xử lý rollback và giữ lỗi gốc

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        // Thực hiện DML/SELECT thuộc một transaction.
        // ...
        connection.commit();

    } catch (SQLException | RuntimeException original) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            original.addSuppressed(rollbackFailure);
        }
        throw original;
    }
}
```

**Chỉ dùng retry** khi có đủ bằng chứng giao dịch cũ chưa commit, tác động bên ngoài DB an toàn, lỗi thật sự retryable và có giới hạn số lần thử. Timeout tự nó không phải giấy phép retry.

### 10.2. Không reset connection mù sau timeout

Sau timeout, đặc biệt là network timeout, không gọi `setAutoCommit(true)` rồi tiếp tục sử dụng connection như thể transaction chắc chắn đã bị hủy. Theo hợp đồng JDBC, đổi `autoCommit` từ `false` sang `true` khi transaction còn hoạt động có thể khiến transaction được commit. Nếu rollback hoặc validation thất bại, pool cần loại bỏ physical connection hoặc cách ly theo cơ chế được hỗ trợ.

## 11. Trạng thái server có thể khác trạng thái client

Một request bị timeout phía HTTP không có nghĩa server database đã dừng query. Tương tự, `Future.cancel(true)` không bảo đảm thread JDBC ngừng chờ socket, và driver báo timeout không phải lúc nào cũng chứng minh server đã giải phóng khóa.

Trong môi trường test PostgreSQL, có thể quan sát hoạt động phiên bằng công cụ và quyền phù hợp:

```sql
SELECT pid,
       state,
       wait_event_type,
       wait_event,
       query_start,
       xact_start
FROM pg_stat_activity
WHERE datname = current_database();
```

Nên lọc/nhận diện các connection test bằng `application_name` riêng hoặc cơ chế gắn nhãn được kiểm soát. Không dựa vào text SQL trong log để tự nhận diện nếu có nguy cơ lộ dữ liệu nhạy cảm.

Đối với một connection đang được mượn, có thể đọc `SELECT pg_backend_pid()` để ghi **backend PID tại thời điểm đó**, hỗ trợ đối chiếu với hoạt động phía server. PID có thể thay đổi khi pool tái kết nối; đừng sử dụng nó như ID nghiệp vụ hay ID toàn cục vĩnh viễn.

Các điều cần quan sát sau một timeout:

- Statement cũ còn ở trạng thái `active` không?
- Connection có đang `idle in transaction` không?
- Có còn `wait_event_type='Lock'` hoặc lock chờ trên hàng test không?
- Database đã nhận lệnh cancel/đóng session hay chỉ client dừng chờ?
- Pool có trả connection về idle trong khi server còn giữ transaction không?

Nếu chỉ số hoạt động chậm cập nhật, cần chờ kiểm chứng trong thời gian có giới hạn và kiểm soát điều kiện test. Không kill backend production để “làm sạch test”.

## 12. Cấu hình và kiểm thử timeout trong môi trường dùng pool

Pool thường có ít nhất ba nhóm timeout riêng:

1. **Acquisition/borrow timeout:** chờ lấy connection khả dụng.
2. **Idle/max lifetime:** thời gian connection được giữ nhàn rỗi hoặc sống tối đa trước khi pool xem xét thay thế.
3. **Validation/health-check timeout:** thời gian kiểm tra connection còn sử dụng được.

Các timeout này không thay thế `Statement.setQueryTimeout(...)` và không bảo đảm loại bỏ query chạy quá lâu. `Connection.isValid(timeoutSeconds)` cũng chỉ kiểm tra connection có vẻ hoạt động theo driver; **không chứng minh session sạch, transaction đã rollback hoặc server không còn SQL cũ**.

Một test pool phù hợp cần:

- Đo timeout borrow trong lúc pool bị chiếm hết.
- Đo timeout query khi đã mượn được connection.
- Gây lỗi mạng có kiểm soát rồi xác nhận connection bị loại bỏ hoặc được phục hồi an toàn.
- Kiểm tra sau timeout, borrower mới nhận được baseline `autoCommit`, isolation, schema và session settings phù hợp.
- Không để một `Statement` hoặc `ResultSet` mở giữ connection quá lâu.
- Bảo đảm không có transaction treo/khóa rò rỉ khi test hoàn tất.

Tuyệt đối không suy rằng `DataSource.setLoginTimeout(...)` cấu hình đồng thời tất cả các timeout của pool. Tên thuộc tính và đơn vị của acquisition timeout thay đổi theo sản phẩm pool.

## 13. Lập bảng kết quả thử nghiệm có thể so sánh giữa driver

Sau mỗi scenario, ghi một dòng kết quả có cả **kỳ vọng** và **thực tế**:

| Trường cần ghi | Ví dụ trong lab | Lý do |
|---|---|---|
| Driver/DBMS/pool version | Lấy bằng `DatabaseMetaData` và cấu hình ứng dụng | Phân biệt thay đổi giữa môi trường |
| Scenario | `query_timeout_pg_sleep` | Tránh gộp query chậm với lock hoặc mạng |
| Requested timeout | 1.000 ms tương đương 1 s ở API thích hợp | Làm rõ đơn vị và ý định |
| Server-side timeout hiện hành | `statement_timeout=0` hoặc cấu hình được đọc lại | Tránh lớp khác kết thúc trước |
| Time measured | Ví dụ khoảng 1,1 s | Chỉ số thực nghiệm, không làm tròn thành cam kết |
| Exception class | `SQLException`/`SQLTimeoutException`/... | Phân loại theo API |
| SQLState và vendor code | Ví dụ `57014` trên PostgreSQL cancellation | Chẩn đoán theo DBMS |
| Stage | Borrow / execute / fetch / commit | Xác định phạm vi đã đo |
| Transaction outcome | Rollback xác nhận / commit thành công / chưa rõ | Phục vụ quyết định retry |
| Connection after error | Dùng được / đã đóng / phải evict | Tránh trả kết nối lỗi vào pool |
| Server-side cleanup | Query/khóa đã hết / vẫn còn | Xác minh timeout thật sự dọn tài nguyên |
| Repetitions | 5 lần trong lab | Phát hiện race/flaky behavior |

**Không “chuẩn hóa” SQLState một cách giả tạo.** Ví dụ `57014` trên PostgreSQL là tín hiệu query bị hủy, nhưng có thể do `statement_timeout`, cancel từ client hoặc lý do khác. Chỉ khi kết hợp thời điểm, cấu hình và dấu vết quan sát mới xác định được cơ chế chi phối.

## 14. Phân loại lỗi và quyết định thử lại

Sau timeout, cần phân biệt:

| Lỗi/sự kiện | Có thể retry? | Điều kiện |
|---|---|---|
| Không lấy được connection vì pool tạm thời bận | Có thể retry **borrow** | Giới hạn số lần, deadline; chưa bắt đầu transaction |
| PostgreSQL `statement_timeout` trước commit | Có thể retry toàn transaction trong một số nghiệp vụ | Sau rollback/abort rõ ràng; nguyên nhân tạm thời; idempotent, có backoff |
| Lock timeout trước commit | Tùy DBMS và nghiệp vụ | Rollback cả transaction theo chính sách; không chỉ chạy lại statement lỗi |
| Lỗi SQL cú pháp, sai quyền | Không retry mù | Sửa SQL/cấu hình |
| `Statement.cancel()` do người dùng yêu cầu hủy | Thường **không tự retry** | Tôn trọng ý định hủy, dọn transaction |
| Network timeout khi commit | **Không retry mù** | Cần xác minh kết quả bằng mã yêu cầu/đối soát |
| Timeout HTTP sau khi server đã commit | Không được giả định xử lý chưa xảy ra | API idempotency, đọc trạng thái nghiệp vụ |
| Timeout trong lúc fetch kết quả | Không tự động chạy lại mọi DML | Xem transaction và kết quả commit; tài nguyên phải được xử lý |

Chọn điều kiện retry theo **giai đoạn lỗi**, không chỉ class ngoại lệ. Một số lỗi tạm thời có thể thử lại giao dịch, nhưng chỉ sau khi đảm bảo **toàn bộ đơn vị nghiệp vụ** có thể thực hiện lại mà không phát sinh side effect trùng. Với các hệ thống gửi email, queue hoặc API thanh toán ngoài DB, cân nhắc transactional outbox, idempotency key hoặc quy trình bù trừ.

## 15. Các nguồn sai lệch và flaky tests thường gặp

### 15.1. Timeout thấp hơn độ phân giải thực tế

Thử đặt timeout một vài mili giây nhưng API chỉ nhận **giây nguyên** có thể bị làm tròn hoặc bị từ chối. `Statement.setQueryTimeout(int)` nhận **số giây**, còn `Connection.setNetworkTimeout(..., int)` nhận **mili giây**. Không đổi đơn vị theo cảm tính.

### 15.2. Server timeout đang chạy trước

Nếu `statement_timeout='500ms'` nhưng JDBC query timeout là 2 giây, sự kiện bị hủy trước 2 giây không chứng minh JDBC query timeout hoạt động. Thử nghiệm cô lập một lớp tại một thời điểm, sau đó mới thử các lớp chồng lên nhau.

### 15.3. `pg_sleep` không đại diện lock wait hoặc mạng bị cắt

Truy vấn ngủ ở DB có thể bị hủy dễ dàng nhưng không phản ánh hành vi khi socket bị treo hoặc một row lock chưa được giải phóng. Mỗi loại cần kịch bản riêng.

### 15.4. Đánh giá pass chỉ dựa vào exception

Một `SQLException` có thể là thiếu bảng, sai cú pháp hoặc mất quyền. Phải kiểm tra `SQLState`, stage, message (không phụ thuộc cứng vào text), elapsed và trạng thái phía server/transaction.

### 15.5. Giới hạn quá chặt theo đồng hồ

CI chịu scheduler delay, tải máy ảo, GC và mạng biến động. Nếu query timeout là một giây và SQL bình thường ngủ năm giây, nên dùng biên dung sai đủ rộng để phân biệt hai trường hợp, không assert đúng 1000 ms. Với môi trường dao động quá mạnh, ghi phép thử là không kết luận được thay vì sửa ngưỡng cho luôn pass.

### 15.6. Dùng test runner interrupt thay JDBC cancel

Một thread test bị interrupt không đồng nghĩa driver đã gửi `Statement.cancel()`. `assertTimeoutPreemptively(...)` hoặc `Future.cancel(true)` chủ yếu giới hạn/chấm dứt thread theo cơ chế Java; driver có thể tiếp tục đợi dữ liệu. Hãy chủ động kiểm tra cleanup và có phương án cách ly test khi driver treo.

### 15.7. Không làm sạch khóa hoặc connection sau thử nghiệm

Một test lock timeout bị lỗi trước `ROLLBACK` có thể làm những test tiếp theo thất bại. Dùng `finally`/`try-with-resources`, rollback cả hai transaction, đóng handle, và theo dõi các session test còn giữ khóa.

### 15.8. Vô tình thay đổi SQL session pool lâu dài

`SET statement_timeout='1s'` ở mức session có thể tồn tại sau commit và ảnh hưởng borrower tiếp theo. Trong PostgreSQL, ưu tiên `SET LOCAL` trong transaction thử nghiệm; nếu phải dùng `SET` thường, cần reset có kiểm chứng hoặc loại bỏ connection test. Không mặc định pool sẽ nhận ra mọi câu `SET`.

## 16. Bộ kịch bản tích hợp tối thiểu

Một bộ test cho JDBC timeout nên có cả **positive**, **negative** và **recovery scenarios**:

| Mã test | Điều kiện | Kết quả cần xác minh |
|---|---|---|
| T01 | `SELECT 1`, không có tranh chấp | Query hoàn tất, không bị timeout giả |
| T02 | `setQueryTimeout(1)` + `pg_sleep(5)` | Query bị hủy trước khi ngủ hết; ghi exception/elapsed |
| T03 | JDBC query timeout dài, DB `statement_timeout` ngắn | Quan sát lỗi do timeout phía server, transaction rollback |
| T04 | Hai connection, A giữ row lock, B có `lock_timeout` | B timeout chờ khóa; A/B đều dọn transaction |
| T05 | A giữ khóa, B không bị tranh chấp sau rollback A | Query B thành công; chứng minh kịch bản đối chứng |
| T06 | `Statement.cancel()` trên query đang chạy | Không treo; phân loại thành công/race/không hỗ trợ |
| T07 | Pool max 1, giữ connection A và borrow B | Borrow timeout theo pool, không bị nhầm query timeout |
| T08 | Proxy mạng gây trì hoãn/mất kết nối | Connection network timeout hoặc lỗi theo driver, trạng thái connection được xử lý |
| T09 | DML trước query bị timeout trong một transaction | Rollback hủy tất cả thay đổi chưa commit |
| T10 | `commit()` mất phản hồi trong môi trường có fault injection | Không retry mù; đối soát theo `request_id` |
| T11 | Một exception rollback do network failure | Lỗi gốc giữ nguyên, connection không được tiếp tục dùng như sạch |
| T12 | Trả connection sau timeout rồi borrow lại | Pool khôi phục baseline hoặc thay physical connection |
| T13 | Thay driver version hoặc DBMS minor version | Chạy lại ma trận, ghi sự khác biệt có ý nghĩa |
| T14 | Hết HTTP deadline trước JDBC timeout | Không khẳng định server tự dừng; test cleanup/cancellation |

Không cần chạy mọi kịch bản trong mỗi commit CI nếu một số test đòi proxy hoặc fault injection phức tạp. Có thể tách **test nhanh** và **nightly/chaos test có môi trường cách ly**. Tuy nhiên, những kịch bản quan trọng về commit không rõ và hồi phục connection nên được kiểm chứng trước khi triển khai tính năng có rủi ro nghiệp vụ cao.

## 17. Gợi ý thiết kế một harness kiểm thử thực tế

Có thể tổ chức bộ kiểm thử thành ba nhóm:

**Nhóm A — JDBC/API và thời gian thực thi SQL:** dùng `DataSource` test, `pg_sleep`, `setQueryTimeout`, `setQueryTimeout(0)` theo phạm vi được kiểm soát, `setFetchSize` nếu cần khảo sát fetch, và ghi đầy đủ exception/elapsed.

**Nhóm B — concurrency/locking/transaction:** dùng hai connection riêng, `CountDownLatch` hoặc phối hợp SQL session để tạo lock wait có thể tái hiện, sau đó rollback cả hai. Kiểm tra tính nguyên tử của DML khi một bước timeout.

**Nhóm C — mạng và recovery:** dùng network proxy/fault injection, giới hạn số connection và thời gian sống của test, quan sát pool/DB activity; kiểm tra connection lỗi không bị tái sử dụng thiếu kiểm soát, cùng quy trình đối soát khi commit mơ hồ.

Một hàm tiện ích in dấu vết lỗi có thể dùng chung trong test:

```java
import java.sql.SQLException;

public final class SqlErrorTrace {
    private SqlErrorTrace() {
    }

    public static void print(SQLException original) {
        for (SQLException current = original;
             current != null;
             current = current.getNextException()) {

            System.out.println(
                    current.getClass().getSimpleName()
                    + " | SQLState=" + current.getSQLState()
                    + " | vendor=" + current.getErrorCode()
                    + " | message=" + current.getMessage());
        }
    }
}
```

Nếu một exception có nguyên nhân bọc bên ngoài hoặc suppressed exceptions từ rollback, cần ghi nhận cả `getCause()` và `getSuppressed()` khi chẩn đoán. Trong production, không log URL chứa credential, dữ liệu khách hàng hoặc câu SQL chứa giá trị nhạy cảm.

### Đo lường nên so sánh những gì?

- **Client elapsed:** từ trước `executeQuery()` đến khi trả về/ném lỗi.
- **Request elapsed:** từ đầu request đến kết thúc trả lời.
- **Pool acquisition time:** chỉ thời gian `getConnection()`.
- **DB execution/wait time:** từ log/metrics/tracing DB, không suy hoàn toàn từ elapsed client.
- **Cleanup time:** từ lúc nhận timeout đến khi transaction đóng và pool có connection an toàn.
- **Success/error rate:** query hoàn tất, timeout, cancel, lỗi connection, timeout không được tôn trọng.

Đánh giá cả **độ chính xác dữ liệu**, không chỉ latency. Một phép thử timeout nhanh nhưng để lại transaction nửa chừng không phải kết quả thành công.

## 18. Checklist trước khi đưa timeout/cancel vào production

1. Đã phân biệt **timeout mượn pool, login, query, network, DB, lock và deadline nghiệp vụ** chưa?
2. Có xác nhận **đơn vị** của từng setting (giây/mili giây) và có ghi lại giá trị thực tế không?
3. `setQueryTimeout(...)` đã được kiểm chứng trên **driver/DBMS thật**, không chỉ qua `getQueryTimeout()` chưa?
4. Đã thử **truy vấn chậm, lock wait, DB timeout, cancel chủ động và lỗi mạng** như các tình huống riêng chưa?
5. Có ghi class ngoại lệ, SQLState, vendor code, giai đoạn lỗi và elapsed thay vì chỉ dò một chuỗi message không?
6. Sau timeout có kiểm tra **transaction rollback, dữ liệu cuối, khóa và trạng thái connection** không?
7. Khi `rollback()` hoặc network operation lỗi, có ngăn connection không đáng tin được tái sử dụng không?
8. Khi commit không rõ, đã có **idempotency key/đối soát** thay vì retry toàn nghiệp vụ mù chưa?
9. Test có **đối chứng thành công**, biên dung sai phù hợp CI, deadline và cleanup độc lập không?
10. Có theo dõi sự khác biệt sau khi cập nhật Java, driver, DBMS hoặc pool không?

## Ghi nhớ

- **Timeout là một hành vi phải kiểm chứng**, không chỉ một setter được gọi thành công.
- `Statement.setQueryTimeout(...)` dùng **giây**, `Connection.setNetworkTimeout(...)` dùng **mili giây**; pool, DB và request có deadline riêng.
- `Statement.cancel()` là yêu cầu hủy **best-effort theo khả năng driver/DBMS**, không đồng nghĩa tự rollback transaction.
- `SQLTimeoutException` và SQLSTATE chỉ là **dấu vết**; cần kết hợp stage, timing, log và trạng thái server để xác định nguyên nhân.
- **Sau timeout, trạng thái transaction và connection có thể khác nhau giữa DBMS/driver**; rollback/dọn tài nguyên phải được kiểm tra thực tế.
- **Mất phản hồi ở commit không chứng minh commit đã thất bại**. Không retry mù khi có nguy cơ nhân đôi tác động nghiệp vụ.
- Một phép thử đạt yêu cầu phải chứng minh **đã giới hạn thời gian, đã dọn tài nguyên và dữ liệu cuối cùng đúng**.

Khi kiểm thử có hệ thống từ pool đến driver, network và DBMS, ứng dụng JDBC có thể chọn giới hạn thời gian phù hợp, phát hiện những khác biệt giữa môi trường trước khi triển khai và xử lý hủy truy vấn mà không đánh đổi tính nhất quán dữ liệu.

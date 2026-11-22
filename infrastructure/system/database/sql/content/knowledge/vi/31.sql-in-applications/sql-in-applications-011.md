# Timeout, hủy truy vấn và phân loại lỗi có thể thử lại

Một request API gọi database để đọc đơn hàng. Query chạy lâu hơn dự kiến, người dùng rời màn hình hoặc gateway hết thời gian chờ. Ứng dụng cần quyết định: tiếp tục đợi, hủy statement, đóng connection, rollback transaction hay thử lại?

Đây là những quyết định khác nhau. **Timeout không đồng nghĩa với cancellation; cancellation không đồng nghĩa với rollback; và lỗi có thể thử lại không có nghĩa mọi lỗi vừa xảy ra đều nên retry.**

Một hệ thống SQL trong ứng dụng cần phối hợp ba việc:

1. **Giới hạn thời gian:** đặt deadline cho request, thời gian lấy connection, kết nối, câu lệnh, chờ khóa và giao tiếp mạng.
2. **Hủy có kiểm soát:** khi kết quả không còn cần thiết, yêu cầu driver/database dừng công việc, giải phóng tài nguyên và xử lý transaction theo trạng thái thực tế.
3. **Phân loại lỗi:** chỉ retry lỗi tạm thời đã nhận diện, với thao tác an toàn, giới hạn số lần và tổng thời gian; không lặp vô hạn hoặc tạo tác dụng phụ trùng lặp.

Bài học thuộc chương **SQL trong ứng dụng** của module **Database SQL**, tập trung vào JDBC/Spring và các khác biệt quan trọng giữa PostgreSQL, MySQL, MariaDB, SQL Server, Oracle và SQLite.

> Các giá trị timeout trong ví dụ chỉ minh họa cách cấu hình. Tên property, đơn vị, phạm vi áp dụng và hành vi khi timeout phụ thuộc driver, connection pool, framework, DBMS và phiên bản. Hãy kiểm tra tài liệu đúng phiên bản đang vận hành và thử trên môi trường riêng.

## 1. Phân biệt timeout, cancellation và retry

| Khái niệm | Ý nghĩa | Điều nó không bảo đảm |
|---|---|---|
| **Timeout** | Một giới hạn thời gian đã hết | Không chứng minh server đã dừng query hoặc transaction đã rollback |
| **Cancellation** | Gửi yêu cầu dừng công việc đang chạy | Không bảo đảm yêu cầu đến server trước khi query hoàn tất |
| **Retry** | Thực hiện lại thao tác sau lỗi được phân loại | Không bảo đảm thao tác trước chưa commit hoặc lặp lại là an toàn |

Ví dụ: ứng dụng gửi lệnh thanh toán trong transaction. Server commit thành công, nhưng mạng đứt trước khi response về. Driver báo lỗi kết nối. Ứng dụng không biết chắc lệnh đã commit chưa. Nếu gửi lại mà không có idempotency key hoặc deduplication, có thể tạo **hai lần thanh toán**.

### 1.1. Timeout xuất hiện ở nhiều tầng

```text
Client / HTTP request
       |
       | Request deadline
       v
Application service
       |
       | Connection-pool acquisition timeout
       v
Connection pool
       |
       | Connect / login timeout
       v
Network + database authentication
       |
       | Statement / query timeout
       v
Database execution
       |
       | Lock wait timeout
       v
Locks, storage, CPU, other transactions
       |
       v
Response travels back to application
       |
       | Network read / socket timeout
       v
HTTP response
```

Một request có thể thất bại ở bất kỳ tầng nào. Đặt timeout ở JDBC statement không giới hạn thời gian chờ lấy connection từ pool; đặt HTTP timeout cũng không tự hủy SQL đang chạy.

### 1.2. Timeout không cho biết chắc dữ liệu đã thay đổi hay chưa

Một câu UPDATE có thể hoàn thành trước deadline, bị server hủy, hoàn thành nhưng response bị mất, chờ lock rồi hết thời gian hoặc bị rollback do lỗi khác trong transaction.

Do đó, log “query timeout” chưa đủ để kết luận dữ liệu không thay đổi. Phải xem **giai đoạn xảy ra lỗi, transaction state và khả năng xác minh kết quả**.

## 2. Các loại timeout cần nhận diện

### 2.1. Request deadline / end-to-end timeout

Đây là tổng thời gian tối đa mà request được phép sử dụng trước khi ứng dụng phải trả kết quả hoặc lỗi cho client.

Ví dụ:

| Giai đoạn | Ngân sách minh họa |
|---|---:|
| Lấy connection từ pool | 300 ms |
| Connect/login nếu phải mở mới | 500 ms |
| Query database | 1.200 ms |
| Xử lý kết quả | 400 ms |
| Serialize/trả response và dự phòng | 600 ms |
| **Tổng** | **3.000 ms** |

Các bước không phải lúc nào cũng cộng tuyến tính; pool có thể trả connection đã mở hoặc request có nhiều query tuần tự. Bảng chỉ minh họa việc **chia ngân sách**, tránh để một query chiếm toàn bộ thời gian.

Nếu request có deadline tại thời điểm D, khi bắt đầu bước mới:

```text
remaining = D - current_time
step_timeout = min(configured_step_limit, remaining - safety_margin)
```

Không đặt query timeout mới là 3 giây sau khi application đã dùng 2,5 giây. Khi đó request có thể chạy vượt deadline tổng.

### 2.2. Connection-pool acquisition timeout

Ứng dụng cần lấy connection từ pool nhưng mọi connection đang được sử dụng. Pool có thể chờ đến giới hạn rồi báo lỗi.

Nguyên nhân thường gặp: pool quá nhỏ, query chạy lâu/chờ lock, code không đóng tài nguyên, transaction giữ connection lâu, request tạo hàng đợi hoặc database quá tải.

Đây là **timeout chờ connection**, không phải query timeout. Chưa lấy được connection thì statement chưa được gửi đến DB.

### 2.3. Connect timeout và login timeout

Kết nối TCP hoặc quá trình xác thực có thể mất quá lâu do DNS, firewall, network, database quá tải hoặc server không phản hồi.

- Connect timeout giới hạn thời gian thiết lập kết nối mạng.
- Login timeout giới hạn thời gian hoàn tất kết nối/xác thực theo API/driver.
- Một số driver dùng property riêng, một số dùng JDBC API hoặc cấu hình pool.

Kết nối thành công không có nghĩa query sau đó sẽ chạy nhanh.

### 2.4. Statement/query timeout

Đây là giới hạn thời gian thực thi câu lệnh SQL theo cơ chế driver hoặc server.

```java
try (PreparedStatement ps = connection.prepareStatement("""
        SELECT order_id, status
        FROM orders
        WHERE tenant_id = ?
        """)) {

    ps.setLong(1, authorizedTenantId);
    ps.setQueryTimeout(2); // JDBC dùng đơn vị giây.

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc dữ liệu cần thiết.
        }
    }
}
```

`setQueryTimeout(2)` yêu cầu driver giới hạn thời gian chờ thực thi statement theo hợp đồng JDBC. **Độ chính xác và cách hủy thực tế phụ thuộc driver/database**. Không giả định đây là hard real-time deadline chính xác đến mili giây.

### 2.5. Lock-wait timeout

Một transaction cần lock nhưng transaction khác đang giữ lock. DBMS có thể chờ đến giới hạn rồi báo lỗi.

Ví dụ: Transaction A cập nhật một hàng và chưa commit; transaction B muốn cập nhật cùng hàng; B chờ lock rồi hết thời gian. Đây không nhất thiết là query tốn CPU; nó có thể đang **đợi transaction khác**.

Lock timeout cần phân biệt với statement timeout: một statement có thể bị dừng vì tổng thời gian vượt giới hạn, hoặc vì riêng thời gian chờ lock vượt giới hạn.

### 2.6. Network/socket read timeout

Client gửi query rồi chờ dữ liệu. Nếu mạng im lặng lâu hơn socket/read timeout, driver có thể báo lỗi I/O.

Điểm nguy hiểm: **socket timeout không chứng minh database đã hủy statement**. Server có thể vẫn chạy query, đã commit transaction hoặc đang gửi kết quả mà client không còn nhận được.

### 2.7. Transaction timeout và idle-in-transaction timeout

Framework hoặc transaction manager có thể đặt giới hạn cho toàn transaction. DBMS cũng có thể có timeout cho session/statement, nhưng không phải hệ nào cũng có transaction timeout tổng quát giống nhau.

Transaction timeout ở framework không tự bảo đảm database lập tức rollback nếu driver không truyền cancellation hoặc connection bị mất. Một session mở transaction nhưng không chạy statement lâu có thể giữ snapshot/lock hoặc cản trở cleanup; một số DBMS có cơ chế đóng session idle-in-transaction.

Không mở transaction rồi chờ người dùng, gọi HTTP hoặc xử lý file lâu.

## 3. Timeout phải phù hợp với ngân sách tổng

Request có deadline 3 giây nhưng query timeout 5 giây là cấu hình không nhất quán. Gateway có thể ngắt request trước khi query timeout; SQL vẫn có thể chạy nếu cancellation không được truyền xuống.

Cần phối hợp gateway/client request timeout, application deadline, pool acquisition timeout, connect/login timeout, transaction timeout, statement/query timeout, lock wait timeout và network timeout.

Không đặt mỗi tầng một timeout dài độc lập. Truyền deadline còn lại giữa các bước, chừa thời gian cho xử lý kết quả và response.

### 3.1. Timeout không thay thế tối ưu query

Nếu một query thường chạy 4 giây do thiếu index, đặt timeout 1 giây sẽ biến vấn đề hiệu năng thành lỗi liên tục.

Hãy xem execution plan, số hàng đọc, lock wait, transaction giữ lock, network, số byte trả về, N+1 và overfetch. Timeout là **giới hạn tài nguyên và trải nghiệm**, không thay thế tối ưu truy vấn.

## 4. Hủy truy vấn: ai gửi yêu cầu và điều gì xảy ra?

Cancellation có thể bắt đầu từ người dùng nhấn Cancel, HTTP client ngắt kết nối, gateway hết deadline, application không còn cần kết quả, job bị dừng, workflow thất bại hoặc statement timeout ở driver/server.

```text
Ứng dụng phát hiện không cần kết quả
             |
             v
Yêu cầu driver hủy statement
             |
             v
Driver gửi cancellation / interrupt
             |
             v
Database nhận yêu cầu (nếu còn đang chạy)
             |
             v
Statement kết thúc hoặc đã hoàn tất
             |
             v
Ứng dụng nhận kết quả/lỗi
             |
             v
Kiểm tra transaction, rollback/commit phù hợp
```

### 4.1. Cancellation có thể đến quá muộn

Giữa lúc application gọi cancel và lúc server nhận yêu cầu, query có thể đã hoàn thành, server đang gửi result set, network có thể lỗi, driver chưa gửi cancellation hoặc DBMS chỉ xử lý cancellation tại điểm an toàn tiếp theo.

Cancellation là **yêu cầu dừng**, không phải bằng chứng chắc chắn không có side effect.

### 4.2. Hủy statement khác đóng connection

JDBC có `Statement.cancel()` để yêu cầu hủy statement đang thực thi. Đóng connection ảnh hưởng tới toàn bộ transaction và các statement trên connection đó.

Trong connection pool, không tự ý đóng socket hoặc giữ connection đã ở trạng thái không rõ. Hãy để driver/pool quản lý lifecycle; connection lỗi cần được đánh dấu và loại khỏi pool theo contract.

### 4.3. Hủy query không tự động rollback mọi thứ

Khi statement bị cancel, DBMS có thể dừng statement và báo lỗi; transaction có thể vẫn mở; một số lỗi làm transaction chuyển sang trạng thái aborted; statement trước đó có thể đã hoàn thành; nếu transaction đã commit, cancellation sau đó không thể đảo ngược commit.

Luôn xử lý trạng thái transaction theo DBMS/framework. Với thao tác ghi quan trọng, khi không chắc transaction còn dùng được, rollback toàn transaction thường là lựa chọn an toàn.

### 4.4. Sau khi cancel vẫn phải cleanup

- Chờ/thu nhận kết quả kết thúc theo driver.
- Đóng ResultSet và Statement.
- Rollback transaction nếu cần.
- Đảm bảo connection được trả về pool ở trạng thái sạch.
- Ghi log lý do hủy và thời điểm.
- Không trả kết quả thành công giả cho caller.

## 5. JDBC: query timeout, cancel và network timeout

### 5.1. Statement.setQueryTimeout

```java
String sql = """
    SELECT order_id, total_amount
    FROM orders
    WHERE tenant_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, authorizedTenantId);
    ps.setQueryTimeout(2);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            BigDecimal total = rs.getBigDecimal("total_amount");
        }
    }
}
```

Đơn vị JDBC API là **giây**. Giá trị 0 thường biểu thị không giới hạn theo JDBC contract. Hãy xác nhận driver hỗ trợ và xử lý timeout như thế nào.

Statement timeout không nhất thiết bao gồm thời gian lấy connection, DNS/connect/login trước khi có connection, xử lý result ở application hoặc toàn bộ request.

### 5.2. Statement.cancel

Một thread điều khiển có thể yêu cầu hủy statement đang chạy ở thread khác nếu driver hỗ trợ:

```java
Statement statement = connection.createStatement();

try {
    statement.setQueryTimeout(5);

    ResultSet rs = statement.executeQuery(
        "SELECT order_id FROM large_report"
    );

    // Xử lý result...
} finally {
    statement.close();
}
```

Thread khác có thể gọi `statement.cancel()` khi không còn cần kết quả. Phải kiểm tra thread-safety của driver và lifecycle. Tránh nhiều thread tự ý thao tác cùng một connection mà không có đồng bộ.

### 5.3. Connection.setNetworkTimeout

JDBC có `Connection.setNetworkTimeout(Executor, milliseconds)` trong các phiên bản hỗ trợ API này. Nó giới hạn thời gian chờ một thao tác giao tiếp mạng với database theo contract driver.

```java
ExecutorService networkExecutor =
    Executors.newSingleThreadExecutor();

try {
    connection.setNetworkTimeout(networkExecutor, 3_000);

    // Thực hiện công việc JDBC.
} finally {
    networkExecutor.shutdown();
}
```

Đây không phải thay thế statement timeout. Khi network timeout xảy ra, connection có thể không còn dùng an toàn. Kiểm tra driver/pool có đánh dấu connection hỏng và loại khỏi pool hay không. Executor cần lifecycle rõ; không tạo thread pool mới cho mỗi query.

### 5.4. Login timeout và pool acquisition timeout

`DriverManager.setLoginTimeout(...)` hoặc property driver có thể giới hạn login. Connection pool như HikariCP có cấu hình acquisition timeout và connection timeout riêng.

```java
HikariConfig config = new HikariConfig();

config.setJdbcUrl(jdbcUrl);
config.setUsername(username);
config.setPassword(password);

config.setConnectionTimeout(500); // ms chờ lấy connection
config.setValidationTimeout(300); // ms kiểm tra connection
config.setMaximumPoolSize(20);
```

Các giá trị trên chỉ minh họa. Pool acquisition timeout quá ngắn có thể làm request lỗi khi tải tăng; quá dài có thể tạo hàng đợi. Cần sizing pool theo DB capacity, concurrency và thời gian giữ connection.

### 5.5. Đóng tài nguyên bằng try-with-resources

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(
         "SELECT order_id FROM orders WHERE tenant_id = ?")) {

    ps.setLong(1, authorizedTenantId);
    ps.setQueryTimeout(2);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // ...
        }
    }
}
```

Try-with-resources đóng tài nguyên kể cả khi exception. Với pool, `Connection.close()` thường trả logical connection về pool thay vì đóng socket vật lý, nếu connection còn hợp lệ.

## 6. Spring: transaction timeout và retry boundary

Spring có thể quản lý transaction:

```java
@Transactional(timeout = 3)
public OrderSummary loadSummary(long tenantId) {
    return repository.loadSummary(tenantId);
}
```

`timeout` thường tính bằng giây trong annotation. Hành vi phụ thuộc transaction manager/resource; không giả định mọi driver đều hủy statement ngay lập tức.

### 6.1. Transaction timeout không phải HTTP timeout

Request có thể có deadline ngắn hơn transaction timeout hoặc ngược lại. Cần cấu hình các tầng nhất quán và truyền deadline còn lại xuống thao tác tiếp theo.

### 6.2. Retry phải nằm ngoài transaction bị lỗi

Nếu method có `@Transactional` rồi retry query sau deadlock bên trong cùng transaction, transaction có thể đã rollback-only hoặc không còn dùng được.

Mô hình đúng thường là mỗi attempt tạo transaction mới:

```text
Retry coordinator (ngoài transaction)
        |
        +--> Attempt 1: BEGIN -> work -> ROLLBACK
        |
        +--> backoff
        |
        +--> Attempt 2: BEGIN -> work -> COMMIT
```

Trong Spring, có thể đặt retry ở service bên ngoài gọi bean khác có `@Transactional`, hoặc dùng `TransactionTemplate` để tạo transaction mới mỗi lần thử. Cần hiểu proxy/self-invocation: gọi method transactional khác trong cùng object có thể không đi qua proxy.

### 6.3. Không retry mọi RuntimeException

Lỗi nghiệp vụ như `InsufficientInventoryException` không trở nên thành công chỉ vì đợi 100 ms rồi thử lại. Retry policy phải phân loại exception cụ thể và nguyên nhân SQLSTATE/vendor code.

### 6.4. HTTP disconnect không tự hủy JDBC

HTTP client disconnect không tự động hủy query trong mọi framework. Cần cơ chế request cancellation/deadline rõ ràng và liên kết với statement đang chạy. Không giả định thread interrupt luôn dừng JDBC.

Với reactive stack, cancellation propagation tùy driver và R2DBC implementation. Phải test driver thật.

## 7. Timeout phía database

Đặt timeout ở server có lợi vì server có thể tự dừng công việc ngay cả khi client không nhận response. Tên và phạm vi cấu hình khác theo DBMS.

### 7.1. PostgreSQL

Các cấu hình thường gặp:

- `statement_timeout`: giới hạn thời gian một statement.
- `lock_timeout`: giới hạn thời gian chờ lock.
- `idle_in_transaction_session_timeout`: đóng session idle trong transaction quá lâu.
- `idle_session_timeout`: giới hạn session idle.
- `transaction_timeout`: có ở các phiên bản PostgreSQL mới; kiểm tra version trước khi dùng.

Ví dụ session-local:

```sql
BEGIN;

SET LOCAL statement_timeout = '2s';
SET LOCAL lock_timeout = '500ms';

SELECT order_id, status
FROM orders
WHERE tenant_id = 10;

COMMIT;
```

`lock_timeout` thường nên nhỏ hơn statement timeout nếu muốn phân biệt chờ lock với query tổng thể. `SET LOCAL` chỉ có hiệu lực trong transaction hiện tại; tránh để session setting rò sang request khác qua connection pool.

Khi statement timeout hết, PostgreSQL thường trả SQLSTATE `57014` (query_canceled). Trong explicit transaction, transaction thường ở trạng thái aborted và cần rollback hoặc rollback to savepoint trước khi tiếp tục.

### 7.2. MySQL

Một số cấu hình:

- `max_execution_time` giới hạn thời gian thực thi cho SELECT read-only trong phạm vi/phiên bản hỗ trợ.
- `innodb_lock_wait_timeout` giới hạn thời gian chờ InnoDB row lock.
- `connect_timeout`, `net_read_timeout`, `net_write_timeout` liên quan kết nối/giao tiếp.
- Driver có query timeout riêng.

Ví dụ:

```sql
SET SESSION max_execution_time = 2000;

SELECT order_id, status
FROM orders
WHERE tenant_id = 10;
```

`max_execution_time` không phải timeout tổng quát cho mọi DML/DDL. Lock timeout và deadlock có semantics rollback khác nhau; kiểm tra cấu hình InnoDB và transaction state.

### 7.3. MariaDB

MariaDB có `max_statement_time` cho giới hạn thời gian statement trong phạm vi hỗ trợ và `innodb_lock_wait_timeout` cho chờ InnoDB lock.

```sql
SET STATEMENT max_statement_time = 2 FOR
SELECT order_id, status
FROM orders
WHERE tenant_id = 10;
```

Không sao chép cấu hình `max_execution_time` của MySQL sang MariaDB mà không kiểm tra tài liệu MariaDB và phiên bản thực tế.

### 7.4. SQL Server

Các lớp khác nhau:

- Client/driver `CommandTimeout` giới hạn thời gian client chờ command.
- `SET LOCK_TIMEOUT` giới hạn thời gian chờ lock theo session.
- `remote query timeout` áp dụng cho một số thao tác remote query, không phải mọi local query.
- Login/connect timeout do client/driver quản lý.

```sql
-- SQL Server: lock wait tối đa 1.5 giây.
SET LOCK_TIMEOUT 1500;

SELECT order_id, status
FROM dbo.orders
WHERE tenant_id = 10;
```

`SET LOCK_TIMEOUT` tính bằng milliseconds; `-1` có nghĩa chờ vô hạn. `CommandTimeout` phía client có thể gây attention/cancel nhưng không giống server-side lock timeout. Khi xử lý lỗi, xem `XACT_STATE()` và rollback khi cần.

### 7.5. Oracle Database

Các cơ chế gồm JDBC `Statement.setQueryTimeout`, Resource Manager/profile theo chính sách DBA, `DDL_LOCK_TIMEOUT` cho một số thao tác DDL và `FOR UPDATE WAIT n`/`NOWAIT` cho khóa hàng.

```sql
-- Oracle: không chờ khóa hàng.
SELECT order_id, status
FROM orders
WHERE order_id = 1001
FOR UPDATE NOWAIT;
```

Nếu không lấy được lock, Oracle có thể báo lỗi như ORA-00054. Đây không phải lỗi cú pháp hay dữ liệu cố định; có thể trả conflict hoặc thử lại nếu use case và deadline cho phép.

Oracle không có một tham số session đơn giản tương đương `statement_timeout` PostgreSQL cho mọi câu SQL. Cần phối hợp client timeout, Resource Manager và chính sách DB phù hợp.

### 7.6. SQLite

SQLite là embedded database; timeout thường liên quan lock contention và API connection:

- `PRAGMA busy_timeout`.
- `sqlite3_busy_timeout()` ở C API.
- `sqlite3_interrupt()` để yêu cầu dừng hoạt động trên connection.
- Progress handler cho ứng dụng cơ hội hủy query dài.
- Driver như Python/JDBC có API/property riêng.

```sql
PRAGMA busy_timeout = 2000;
```

Đây là thời gian chờ khi database bận/khóa, không phải deadline tổng cho mọi query. `SQLITE_BUSY`, `SQLITE_LOCKED` và `SQLITE_INTERRUPT` cần được phân loại riêng.

## 8. Bảng so sánh timeout theo DBMS

| DBMS | Query/statement | Lock wait | Điểm cần nhớ |
|---|---|---|---|
| PostgreSQL | `statement_timeout` hoặc JDBC | `lock_timeout` | Timeout thường SQLSTATE 57014; transaction có thể aborted |
| MySQL | `max_execution_time` cho SELECT được hỗ trợ, client timeout | `innodb_lock_wait_timeout` | Lock timeout và deadlock khác nhau |
| MariaDB | `max_statement_time` | `innodb_lock_wait_timeout` | Kiểm tra version và scope |
| SQL Server | Client `CommandTimeout`/resource controls | `SET LOCK_TIMEOUT` | Client timeout khác lock timeout |
| Oracle | JDBC/client, Resource Manager | `NOWAIT`/`WAIT` | Không có một statement timeout session chung cho mọi query như PG |
| SQLite | Driver/progress handler/interrupt | `busy_timeout` | Embedded; busy timeout không phải query deadline |

## 9. Phân loại lỗi: lỗi nào có thể thử lại?

| Nhóm lỗi | Ví dụ | Retry mặc định? |
|---|---|---|
| Validation/kiểu dữ liệu | Sai kiểu, vượt miền | Không |
| Syntax/schema | SQL sai, bảng/cột không tồn tại | Không |
| Permission/authentication | Thiếu quyền, credential sai | Không |
| Constraint/business conflict | UNIQUE/FK/CHECK, trạng thái không hợp lệ | Thường không; xử lý nghiệp vụ |
| Deadlock | Transaction bị chọn làm victim | Có thể retry toàn transaction |
| Serialization failure | Isolation yêu cầu chạy lại transaction | Có thể retry toàn transaction |
| Lock timeout/busy | Không lấy được lock trong giới hạn | Có thể nếu còn deadline và an toàn |
| Query timeout | Statement chạy quá lâu | Không tự động; thường cần điều tra |
| Pool exhausted | Không lấy được connection | Chờ/try lại rất hạn chế; xem tải |
| Connect failure trước khi gửi query | Không thiết lập kết nối | Có thể thử lại với backoff |
| Connection lost khi đang ghi/commit | Không rõ server đã commit chưa | Outcome mơ hồ; cần idempotency |
| User cancellation | Người dùng không còn cần kết quả | Thường không retry |
| Database unavailable | Server tạm không nhận kết nối | Theo retry budget/circuit breaker |

Retryable không chỉ dựa vào mã lỗi. Cần biết lỗi có tạm thời không, transaction đã side effect chưa, commit outcome có xác định không, thao tác có idempotent không, còn deadline không và tải hệ thống có đang quá cao không.

## 10. SQLSTATE và vendor code thường gặp

SQLSTATE chuẩn hóa theo nhóm, nhưng vendor code và semantics chi tiết khác nhau. Các ví dụ sau không phải danh sách đầy đủ hoặc quy tắc retry tự động.

### 10.1. PostgreSQL

| SQLSTATE | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `40001` | serialization_failure | Retry toàn transaction nếu an toàn |
| `40P01` | deadlock_detected | Retry toàn transaction với backoff |
| `55P03` | lock_not_available | Có thể thử lại nếu còn deadline |
| `57014` | query_canceled | Xem timeout hay user cancel; không retry mù |
| `23505` | unique_violation | Conflict nghiệp vụ, không retry nguyên xi |
| `23503` | foreign_key_violation | Không retry |
| `23514` | check_violation | Validation/bug, không retry |
| `42501` | insufficient_privilege | Không retry |
| `08xxx` | connection exception class | Xem phase và commit outcome |

Trong PostgreSQL, statement lỗi trong explicit transaction thường làm transaction ở trạng thái aborted. Cần rollback transaction hoặc rollback tới savepoint trước khi tiếp tục.

### 10.2. MySQL / InnoDB

| Mã thường gặp | Ý nghĩa | Hướng xử lý |
|---|---|---|
| Error 1213 / SQLSTATE `40001` | Deadlock victim | Retry toàn transaction |
| Error 1205 | Lock wait timeout | Xem `innodb_rollback_on_timeout` và transaction state |
| Error 1062 | Duplicate key | Conflict, không retry nguyên xi |
| Error 1452 | Foreign key constraint | Không retry |
| Error 1142 | Command denied | Không retry |
| Error 2006/2013 | Server gone away / lost connection | Outcome có thể mơ hồ |
| Error 1045 | Access denied | Không retry |

MySQL lock wait timeout thường chỉ rollback statement theo cấu hình mặc định, còn deadlock thường rollback transaction victim. Cấu hình InnoDB có thể thay đổi hành vi. Ứng dụng cần rollback/restart transaction theo trạng thái thực tế.

### 10.3. MariaDB

MariaDB có mã lỗi gần MySQL cho InnoDB như 1213 (deadlock), 1205 (lock wait timeout), 1062 (duplicate entry), 1452 (foreign key constraint). Tuy nhiên driver, storage engine và version có thể ảnh hưởng SQLSTATE/vendor code. Phân loại bằng test trên phiên bản MariaDB thực tế.

### 10.4. SQL Server

| Mã thường gặp | Ý nghĩa | Hướng xử lý |
|---|---|---|
| 1205 | Deadlock victim | Retry transaction |
| 1222 | Lock request timeout | Có thể retry nếu còn deadline |
| -2 ở SqlClient | Command timeout phía client | Xem cancellation và transaction state |
| 2601/2627 | Duplicate key/unique constraint | Conflict, không retry nguyên xi |
| 547 | FK/CHECK constraint | Không retry |
| 18456 | Login failed | Không retry |
| 4060 | Cannot open database | Kiểm tra cấu hình/quyền |
| 08xxx | Connection exception class qua driver | Xác minh outcome |

SQL Server có `XACT_STATE()` để xác định transaction còn khả năng commit hay đã ở trạng thái không thể commit. Sau lỗi cần rollback phù hợp; không tiếp tục query trên transaction doomed.

### 10.5. Oracle Database

| Mã Oracle | Ý nghĩa | Hướng xử lý |
|---|---|---|
| ORA-00060 | Deadlock detected | Rollback/restart transaction |
| ORA-08177 | Cannot serialize access | Retry transaction phù hợp |
| ORA-00054 | Resource busy / NOWAIT | Có thể thử lại có giới hạn |
| ORA-00001 | Unique constraint | Conflict, không retry nguyên xi |
| ORA-02291 | Parent key not found | Không retry nếu dữ liệu chưa đổi |
| ORA-01017 | Invalid credentials | Không retry |
| ORA-01013 | Operation canceled | Xem nguồn cancellation |
| ORA-03113/03114 | Communication channel/session lost | Outcome có thể mơ hồ |

Một số lỗi Oracle rollback statement, một số ảnh hưởng transaction/session khác nhau. Đọc error stack, transaction state và driver behavior.

### 10.6. SQLite

| Mã/nhóm | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `SQLITE_BUSY` | Database/table đang bận | Có thể chờ/retry ngắn |
| `SQLITE_LOCKED` | Lock conflict trong connection/shared cache | Xem transaction/connection usage |
| `SQLITE_INTERRUPT` | Operation bị interrupt | Thường do cancellation; không retry mù |
| `SQLITE_CONSTRAINT` | Vi phạm constraint | Không retry nguyên xi |
| `SQLITE_IOERR` | I/O error | Xem thiết bị/file |
| `SQLITE_CORRUPT` | Database corruption | Không retry như lỗi tạm thời |

SQLite có extended result codes để phân biệt thêm nguyên nhân. Driver có thể chỉ expose primary code; kiểm tra API cụ thể.

## 11. Timeout không đồng nghĩa retryable

Query timeout có thể do thiếu index, đọc quá nhiều dữ liệu, lock bị giữ lâu, database quá tải, result set lớn, network không phản hồi hoặc người dùng hủy.

Nếu retry ngay cùng query, hệ thống có thể làm **nhiều việc hơn đúng lúc đang quá tải**.

Có thể cân nhắc retry nếu timeout do lock contention tạm thời đã nhận diện, thao tác chưa commit hoặc có idempotency, còn deadline, query đã tối ưu, retry budget nhỏ và hệ thống không quá tải kéo dài.

Không nên retry khi user đã cancel, query timeout do workload cố định quá nặng, lỗi constraint/validation/permission/syntax, commit outcome mơ hồ, request hết deadline hoặc pool đang cạn.

## 12. Kết quả mơ hồ: rủi ro lớn nhất khi retry thao tác ghi

```text
Application                     Database
    |                               |
    |---- INSERT payment ---------->|
    |                               |
    |                         COMMIT thành công
    |                               |
    |<--- response bị mất -------- X|
    |
    | Driver báo connection error
    |
    | Ứng dụng không biết INSERT đã commit chưa
```

Ứng dụng không thể kết luận “không có dữ liệu” chỉ vì không nhận response.

### 12.1. Idempotency key

Một request nghiệp vụ có thể mang mã duy nhất, ví dụ `payment_request_id`. Database bảo đảm uniqueness:

```sql
CREATE TABLE payment_requests (
    request_id UUID PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    provider_reference TEXT,
    created_at TIMESTAMP NOT NULL
);
```

Khi retry cùng request ID, ứng dụng tìm kết quả đã ghi thay vì tạo payment mới. Thiết kế thật cần xác định scope key, request hash, trạng thái đang xử lý/hoàn tất, retention, concurrency và đối soát với provider.

### 12.2. Unique constraint là một phần của idempotency

Nếu chỉ SELECT key trước rồi INSERT, hai request đồng thời vẫn có thể cùng vượt qua kiểm tra. Unique constraint/index ở DB là lớp quyết định. Ứng dụng bắt duplicate key rồi đọc kết quả đã lưu.

### 12.3. Outbox và consumer idempotency

Outbox giúp ghi dữ liệu và event trong cùng transaction. Worker có thể publish lại sau crash, vì vậy consumer cần xử lý trùng event bằng event ID hoặc idempotency key. Không coi outbox là exactly-once tự động.

## 13. Retry đúng cách: toàn transaction, giới hạn và backoff

### 13.1. Retry transaction thay vì tiếp tục transaction lỗi

Deadlock hoặc serialization failure thường yêu cầu rollback rồi chạy lại từ đầu. Không chỉ chạy lại câu cuối vì các câu trước có thể đã đọc snapshot hoặc ra quyết định dựa trên giả định không còn đúng.

```text
for each bounded attempt:
    BEGIN
    try:
        perform all reads and writes
        COMMIT
        return success
    catch known transient transaction error:
        ROLLBACK
        wait with bounded backoff + jitter
        retry if budget remains
    catch non-retryable error:
        ROLLBACK
        return/raise error
```

### 13.2. Exponential backoff

```text
delay(attempt) = min(maxDelay, baseDelay * 2^(attempt - 1))
```

Ví dụ base 50 ms, max 500 ms:

| Lần thử | Delay cơ sở |
|---:|---:|
| 1 | 0 ms trước lần đầu |
| 2 | 50 ms |
| 3 | 100 ms |
| 4 | 200 ms |
| 5 | 400 ms |

### 13.3. Jitter và retry budget

Nếu hàng nghìn request cùng retry sau đúng 100 ms, chúng có thể tạo đợt tải mới. Thêm random jitter:

```text
actual_delay = random(0, calculated_backoff)
```

Xác định số lần thử tối đa, tổng thời gian tối đa, deadline còn lại, backoff tối đa, lỗi nào được retry và thao tác nào phải idempotent. Nếu request chỉ còn 100 ms, không bắt đầu retry có backoff 500 ms.

## 14. Java: cấu trúc retry transaction có kiểm soát

Ví dụ dưới đây minh họa ý tưởng. Hàm `isRetryableTransactionError` phải được triển khai bằng mapping SQLSTATE/vendor code đã xác nhận cho driver/DBMS; không coi mọi SQLException là retryable.

```java
public <T> T executeWithRetry(
        DataSource dataSource,
        int maxAttempts,
        Duration totalBudget,
        SqlWork<T> work) throws SQLException {

    long deadline = System.nanoTime() + totalBudget.toNanos();

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        if (System.nanoTime() >= deadline) {
            throw new SQLTimeoutException("Retry budget exhausted");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                T result = work.execute(connection);
                connection.commit();
                return result;
            } catch (SQLException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }

                if (!isRetryableTransactionError(ex)
                        || attempt == maxAttempts) {
                    throw ex;
                }

                long remainingNanos =
                    deadline - System.nanoTime();

                if (remainingNanos <= 0) {
                    throw ex;
                }

                long backoffMillis = calculateBackoffWithJitter(attempt);
                long waitMillis = Math.min(
                    backoffMillis,
                    TimeUnit.NANOSECONDS.toMillis(remainingNanos)
                );

                sleepWithoutLosingInterrupt(waitMillis);
            }
        }
    }

    throw new SQLTransientException("Retry attempts exhausted");
}
```

Đây là skeleton, chưa phải thư viện retry hoàn chỉnh. Cần xử lý thêm:

- Phân biệt lỗi khi lấy connection với lỗi trong transaction.
- Nếu commit ném lỗi mạng, outcome có thể **mơ hồ**; không tự động chạy lại write nếu chưa có idempotency/đối soát.
- Hàm sleep phải khôi phục interrupt flag và dừng retry khi thread bị interrupt.
- Work không được gửi side effect bên ngoài transaction.
- Mỗi attempt lấy connection/transaction mới.
- Không retry validation, constraint, syntax hoặc permission.
- Áp query timeout/deadline cho statement bên trong.
- Giới hạn concurrency/retry để không làm quá tải DB.

### 14.1. Không retry lỗi commit mơ hồ như deadlock

Deadlock victim được DBMS xác định rollback transaction; có thể retry toàn transaction. Connection mất ngay sau khi client gửi COMMIT có thể không rõ commit đã thành công chưa. Trường hợp này cần idempotency key hoặc query đối soát bằng business identifier.

### 14.2. Không nuốt InterruptedException

```java
try {
    Thread.sleep(waitMillis);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new CancellationException("Retry interrupted");
}
```

Nếu thread bị interrupt trong lúc backoff, nên dừng retry và khôi phục trạng thái interrupt.

## 15. Spring Retry và transaction boundary

Có thể dùng thư viện retry hoặc cơ chế retry của ứng dụng. Thứ tự retry và transaction rất quan trọng.

```java
@Service
public class OrderRetryCoordinator {

    private final OrderTransactionWorker worker;

    public OrderRetryCoordinator(OrderTransactionWorker worker) {
        this.worker = worker;
    }

    public OrderResult confirmWithRetry(ConfirmOrderCommand command) {
        // Retry coordinator ở ngoài transaction.
        return retryTemplate.execute(context ->
            worker.confirmInNewTransaction(command)
        );
    }
}

@Service
public class OrderTransactionWorker {

    @Transactional
    public OrderResult confirmInNewTransaction(
            ConfirmOrderCommand command) {
        // Đọc, kiểm tra và ghi toàn bộ transaction.
        return ...;
    }
}
```

Đây là ví dụ rút gọn với hai bean riêng. Thực tế cần propagation phù hợp (`REQUIRES_NEW` chỉ khi semantics yêu cầu), rollback rules, exception translation và allowlist exception retry. Trong Spring proxy mode, gọi method transactional khác trong cùng object có thể không đi qua proxy.

## 16. Phân loại SQLException trong Java

JDBC cung cấp:

- `SQLException.getSQLState()`.
- `SQLException.getErrorCode()` (vendor-specific).
- `getNextException()` cho chuỗi lỗi tiếp theo.
- Subtype như `SQLTransientException`, `SQLNonTransientException`, `SQLRecoverableException`.
- `SQLTimeoutException`.

Không chỉ dựa vào class exception. Driver có thể ánh xạ khác nhau; cần đọc SQLSTATE và vendor code, kiểm thử theo DBMS/driver.

| SQLSTATE class | Ý nghĩa khái quát | Hướng xử lý |
|---|---|---|
| `08` | Connection exception | Xem phase và outcome |
| `22` | Data exception | Thường không retry |
| `23` | Integrity constraint violation | Conflict/validation |
| `28` | Invalid authorization | Không retry |
| `40` | Transaction rollback | Một số lỗi có thể retry transaction |
| `42` | Syntax/access rule | Thường là lỗi code/schema/quyền |
| `HYT00`/`HYT01` | Timeout theo ODBC/driver context | Xem driver và cancellation |
| `57014` PostgreSQL | Query canceled | Xem nguyên nhân |

Không retry mọi exception có chữ “timeout”. Hãy viết mapping cụ thể, có unit test cho mã lỗi đã xác nhận và mặc định **không retry** nếu chưa biết.

## 17. Cancellation trong Java: request deadline và thread interrupt

### 17.1. Future.cancel(true) không bảo đảm dừng SQL

Nếu query chạy trong executor:

```java
Future<Result> future = executor.submit(() -> repository.loadReport());

future.cancel(true);
```

`cancel(true)` yêu cầu interrupt thread. JDBC driver không bắt buộc mọi query lập tức dừng chỉ vì thread bị interrupt. Một số driver hỗ trợ tốt hơn; một số cần `Statement.cancel()` hoặc timeout riêng.

### 17.2. Giữ tham chiếu statement để hủy

```java
AtomicReference<Statement> runningStatement =
    new AtomicReference<>();

// Thread thực thi tạo statement và đăng ký.
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    runningStatement.set(ps);
    ps.setQueryTimeout(2);
    // execute...
} finally {
    runningStatement.set(null);
}

// Thread điều khiển khi cần cancel:
Statement current = runningStatement.get();
if (current != null) {
    current.cancel();
}
```

Đây chỉ là ý tưởng. Cần đồng bộ lifecycle, tránh race giữa đóng statement và cancel, không dùng chung connection không an toàn giữa nhiều thread và kiểm tra driver hỗ trợ hành vi này.

### 17.3. Không giữ statement reference quá lifecycle

Khi request kết thúc, dọn tham chiếu và đóng statement/result set. Nếu cancellation đến sau khi resource đã đóng, xử lý lỗi cancel như một tình huống race, không làm rò tài nguyên.

## 18. Retry và idempotency cho thao tác ghi

Một lệnh đọc thường dễ retry hơn lệnh ghi, nhưng vẫn cần cân nhắc chi phí và deadline. Lệnh ghi cần biết **nó đã được áp dụng chưa**.

### 18.1. Idempotent và non-idempotent

Một thao tác đặt cờ về giá trị cố định thường idempotent:

```sql
UPDATE orders
SET archived = TRUE
WHERE order_id = ?
  AND tenant_id = ?;
```

Thực hiện lại thường vẫn để archived = TRUE, nhưng trigger/audit có thể tạo side effect lặp, cần xem toàn bộ luồng.

Một thao tác trừ tiền không idempotent:

```sql
UPDATE accounts
SET balance = balance - ?
WHERE account_id = ?;
```

Nếu chạy lại sau timeout, số dư có thể bị trừ hai lần. Cần operation ID/idempotency key, ledger và unique constraint.

### 18.2. Idempotency table

```sql
CREATE TABLE idempotency_records (
    tenant_id BIGINT NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    response_payload TEXT,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);
```

Trong transaction:

1. Insert key nếu chưa tồn tại.
2. Nếu key đã tồn tại, xác minh request hash giống lần đầu.
3. Nếu đã hoàn tất, trả kết quả đã lưu.
4. Nếu đang xử lý, áp dụng chính sách chờ/trả trạng thái.
5. Thực hiện business write.
6. Lưu kết quả và đánh dấu hoàn tất.
7. Commit cùng transaction.

Schema thật cần xử lý concurrency, retention, response nhạy cảm và trạng thái xử lý bị treo.

### 18.3. Outbox và consumer idempotency

Outbox giúp ghi dữ liệu và event trong cùng transaction. Worker có thể publish lại sau crash, vì vậy consumer cần xử lý trùng event bằng event ID hoặc idempotency key. Không coi outbox là exactly-once tự động.

## 19. Circuit breaker, bulkhead và retry budget

Retry giúp vượt qua lỗi ngắn, nhưng khi database unavailable lâu, retry liên tục làm tải tăng.

```text
CLOSED
  | lỗi vượt ngưỡng
  v
OPEN
  | hết thời gian chờ
  v
HALF-OPEN
  | probe thành công -> CLOSED
  | probe thất bại  -> OPEN
```

- **Closed:** request được phép đi qua, theo dõi lỗi.
- **Open:** từ chối nhanh hoặc trả lỗi tạm thời.
- **Half-open:** cho một số probe thử lại.

Không mở circuit breaker vì lỗi validation hoặc unique violation; chỉ dùng tín hiệu hạ tầng phù hợp.

Bulkhead giới hạn số công việc database đồng thời hoặc tách pool cho workload nặng/nhẹ. Tính tổng connection giữa mọi instance để không vượt capacity DB.

Retry budget giới hạn attempts theo request/service. Mỗi request có số lần thử nhỏ, tổng thời gian không vượt deadline và không lặp lỗi non-retryable.

## 20. Connection pool và lỗi sau timeout

Connection pool tái sử dụng connection vật lý. Sau network error/cancellation, connection có thể vẫn hợp lệ, đã bị server đóng, đang ở transaction aborted, còn session state của request trước, driver không còn đồng bộ protocol hoặc pool đã đánh dấu broken và loại bỏ.

### 20.1. Không trả connection lỗi về pool

Dùng pool theo contract: đóng logical connection để trả về pool; để pool/driver kiểm tra và loại connection hỏng. Nếu ứng dụng giữ connection sau fatal network error rồi dùng tiếp, statement sau có thể lỗi bất ngờ.

### 20.2. Reset session state

Các thiết lập như search_path, timezone, role, lock timeout hoặc isolation có thể tồn tại khi connection được tái sử dụng. Ưu tiên transaction-local setting hoặc cấu hình reset/initialization của pool. Không để request A thay session state ảnh hưởng request B.

### 20.3. Pool quá lớn không chữa timeout

Tăng maximum pool size có thể làm DB chịu nhiều query đồng thời hơn. Kiểm tra thời gian giữ connection, query latency, lock wait, leak detection, concurrency và số connection DB có thể phục vụ.

## 21. Cancellation và transaction state theo DBMS

| DBMS | Cơ chế/biểu hiện | Điểm cần chú ý |
|---|---|---|
| PostgreSQL | Cancel request, SQLSTATE `57014` | Explicit transaction thường aborted sau statement error |
| MySQL | Client cancel/KILL QUERY/driver timeout | Statement dừng nhưng transaction có thể còn |
| MariaDB | Cancel/statement time limit theo driver/server | Kiểm tra storage engine và transaction state |
| SQL Server | Attention/cancel từ client, command timeout | Kiểm tra `XACT_STATE()` và rollback |
| Oracle | JDBC cancel, ORA-01013 trong một số tình huống | Phân biệt statement cancellation và session/network loss |
| SQLite | `sqlite3_interrupt`, SQLITE_INTERRUPT | Cleanup theo API/driver và transaction state |

Không áp quy tắc “timeout luôn rollback toàn transaction” cho mọi DBMS.

## 22. Những lỗi thường không retry

Một policy an toàn thường mặc định không retry:

- SQL syntax error.
- Table/column/schema không tồn tại.
- Permission denied hoặc login failed.
- Invalid data type/cast.
- NOT NULL, CHECK, FK constraint.
- Duplicate key, trừ khi duplicate là cơ chế idempotency có chủ đích và ứng dụng đọc kết quả hiện có.
- Business validation như không đủ tồn kho.
- Người dùng chủ động hủy.
- Request hết deadline.
- Unsupported feature hoặc lỗi cấu hình.

Nếu lỗi cần thay input/cấu hình/schema, retry cùng request thường chỉ lặp lại thất bại.

## 23. Những lỗi có thể retry nhưng phải có điều kiện

### 23.1. Deadlock

DBMS chọn một transaction làm victim để phá vòng chờ. Nếu lỗi xác định transaction bị rollback, có thể retry toàn transaction với backoff nhỏ và số lần giới hạn.

### 23.2. Serialization failure

Ở isolation serializable, DBMS có thể yêu cầu transaction chạy lại vì kết quả không tương thích với thứ tự tuần tự hợp lệ. Retry phải chạy lại toàn bộ logic đọc/ghi để tính lại quyết định.

### 23.3. Lock timeout / busy

Có thể retry nếu lock contention ngắn hạn, còn deadline và thao tác an toàn. Nếu nguyên nhân là transaction giữ lock lâu hoặc hệ thống tải cao, retry liên tục sẽ làm tình hình tệ hơn.

### 23.4. Connection establishment failure

Nếu kết nối thất bại **trước khi query được gửi**, có thể thử lại kết nối theo backoff. Nếu connection mất khi đang thực thi hoặc commit, outcome có thể không rõ và cần idempotency/đối soát.

### 23.5. Database unavailable

Có thể dùng circuit breaker và retry budget. Không retry nhanh liên tục trong lúc database restart hoặc quá tải.

## 24. Quan sát và log timeout/cancellation

Để phân tích lỗi, cần request ID/trace ID, operation/use case, query fingerprint, DBMS/driver/version, timeout mỗi tầng, thời gian lấy connection, execute/fetch, SQLSTATE/vendor code, transaction attempt/isolation, nguồn cancellation, commit outcome, số lần retry/backoff và pool/database load.

### 24.1. Không log raw parameter nhạy cảm

Bind values có thể chứa PII, token hoặc dữ liệu thanh toán. Dùng query fingerprint, bind type/size khi cần, redaction và retention. Không log password/access token hoặc toàn bộ payload không giới hạn.

### 24.2. Metrics hữu ích

- Query latency p50/p95/p99.
- Timeout count theo query fingerprint.
- Cancellation count và nguyên nhân.
- Lock wait duration.
- Connection acquisition wait.
- Pool active/idle/pending.
- Retry attempts và retry exhaustion.
- Deadlock/serialization rate.
- Transaction duration.
- Unknown commit outcome count.

Một dashboard chỉ đếm tổng SQLException khó chỉ ra nguyên nhân.

## 25. Kiểm thử timeout, cancellation và retry

Test cần database thật hoặc môi trường DBMS tương thích, không chỉ mock SQLException.

### 25.1. Test lock wait có kiểm soát

Trong database test:

1. Connection A mở transaction và lock một hàng.
2. Connection B chạy UPDATE cùng hàng với lock timeout ngắn.
3. Xác nhận B nhận đúng lỗi lock timeout.
4. Rollback A.
5. Xác nhận B có thể thử lại trong transaction mới nếu policy cho phép.

Không chạy bài test này trên bảng production.

### 25.2. Test statement timeout

Chọn query test có thời gian thực thi kiểm soát được theo DBMS, đặt timeout nhỏ và xác nhận driver nhận lỗi timeout/cancel. Đừng dùng hàm sleep giả định trong SQL nếu dialect không hỗ trợ hoặc gây tải không cần thiết.

### 25.3. Test cancellation race

- Bắt đầu query đủ lâu trong database test.
- Yêu cầu cancellation từ thread khác.
- Kiểm tra statement kết thúc và tài nguyên được đóng.
- Kiểm tra transaction có cần rollback không.
- Thử trường hợp query hoàn tất ngay trước cancel.
- Kiểm tra connection sau đó có được pool tái sử dụng an toàn không.

### 25.4. Test unknown commit outcome

Có thể mô phỏng mất response sau commit bằng proxy/network fault injection trong môi trường test. Xác nhận retry dùng cùng idempotency key, không tạo hai business records, ứng dụng đọc lại kết quả đã commit và event/outbox không gây side effect trùng.

### 25.5. Test retry classification

Tạo test cho từng SQLSTATE/vendor code: deadlock retry transaction; serialization retry transaction; unique/FK/CHECK/permission không retry; query timeout có policy riêng; connection loss khi commit là unknown outcome; user cancellation thì dừng retry.

Mock kiểm tra mapping unit-level; integration test xác nhận driver thật trả mã như dự kiến.

## 26. Quy trình xử lý lỗi thực tế

Khi nhận exception từ JDBC:

1. **Xác định giai đoạn:** lấy connection, connect/login, execute, fetch, commit hay rollback?
2. **Đọc mã lỗi:** SQLSTATE, vendor code, subtype và chained exceptions.
3. **Xác định nguồn cancellation:** server timeout, client deadline, user cancel hay network failure?
4. **Kiểm tra transaction state:** active, aborted, committed hay unknown?
5. **Đánh giá side effect:** đọc, ghi idempotent, ghi non-idempotent hay external side effect?
6. **Phân loại:** permanent, transient-known-rollback, transient-connection, timeout, cancellation hoặc unknown outcome.
7. **Quyết định:** trả lỗi, rollback, retry transaction mới, đối soát idempotency hoặc yêu cầu xử lý thủ công.
8. **Ghi telemetry:** không lộ parameter nhạy cảm.
9. **Giới hạn:** deadline, attempts, backoff và concurrency.

```text
SQLException
    |
    v
Xác định phase + SQLSTATE/vendor code
    |
    +--> Validation / syntax / permission / constraint
    |       |
    |       v
    |     Không retry; map lỗi phù hợp
    |
    +--> Deadlock / serialization / lock conflict
    |       |
    |       v
    |     Rollback; retry toàn transaction nếu còn budget
    |
    +--> Query timeout / user cancellation
    |       |
    |       v
    |     Dừng; kiểm tra transaction và nguyên nhân
    |
    +--> Connection lost / commit response mất
            |
            v
       Outcome có thể mơ hồ
            |
            v
       Idempotency / đối soát trước khi retry write
```

## 27. Sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Cách đúng |
|---|---|---|
| Chỉ đặt HTTP timeout | SQL có thể vẫn chạy sau disconnect | Truyền deadline/cancellation tới JDBC/DB |
| Chỉ đặt statement timeout | Không giới hạn pool wait/connect/login | Cấu hình từng tầng |
| Nghĩ timeout = rollback | DBMS và transaction state khác nhau | Kiểm tra/rollback theo trạng thái |
| Nghĩ cancel chắc chắn server dừng | Cancellation có thể đến muộn | Xem kết quả và cleanup |
| Retry mọi SQLException | Lặp lỗi permanent và tăng tải | Phân loại SQLSTATE/vendor code |
| Retry mọi timeout | Có thể lặp write hoặc quá tải | Chỉ retry khi semantics cho phép |
| Retry câu cuối trong transaction lỗi | Snapshot/logic trước đó không còn đúng | Rollback và chạy lại transaction |
| Retry lỗi commit mơ hồ | Có thể tạo duplicate side effect | Idempotency và đối soát |
| Không có retry limit | Retry storm | Budget, backoff, jitter |
| Backoff cố định | Nhiều request retry cùng lúc | Jitter |
| Giữ connection khi sleep | Làm pool cạn | Rollback/close trước backoff |
| Nuốt InterruptedException | Không dừng khi shutdown/cancel | Khôi phục interrupt và dừng |
| Dùng Future.cancel(true) rồi nghĩ SQL đã dừng | Driver có thể không hủy theo interrupt | Statement.cancel/timeout và test |
| Pool quá lớn để chữa timeout | DB bị quá tải hơn | Đo connection hold time/capacity |
| Timeout quá ngắn che query kém | Tăng lỗi mà không sửa gốc | EXPLAIN, index, lock analysis |
| Retry payment không idempotent | Trừ tiền/gửi lệnh hai lần | Idempotency key và unique constraint |
| Không rollback transaction aborted | Query tiếp theo tiếp tục lỗi | Rollback/savepoint đúng DBMS |
| Log toàn bộ bind values | Rò PII/secrets | Query fingerprint và redaction |
| Coi lock timeout giống deadlock | Rollback semantics khác | Mapping riêng |
| Coi connection error là chưa commit | Outcome có thể unknown | Phân biệt trước execute và sau commit |
| Không test với driver thật | Mã lỗi/cancel khác mock | Integration/fault-injection test |

## 28. Checklist cấu hình và vận hành

### 28.1. Timeout

- Có request deadline end-to-end.
- Pool acquisition timeout nhỏ hơn request deadline.
- Connect/login timeout phù hợp môi trường mạng.
- Statement/query timeout theo workload.
- Lock timeout được xác định riêng khi cần.
- Network timeout không phá vỡ cleanup.
- Transaction không giữ mở khi chờ user/HTTP.
- Các bước dùng ngân sách deadline còn lại.

### 28.2. Cancellation

- User/request cancellation được truyền xuống DB nếu driver hỗ trợ.
- Statement có thể cancel/timeout.
- ResultSet/Statement/Connection được cleanup.
- Transaction được rollback khi cần.
- Connection lỗi không quay lại pool ở trạng thái hỏng.
- Race giữa cancel và query completion được test.
- Không coi cancellation là bằng chứng side effect chưa xảy ra.

### 28.3. Retry

- Có allowlist lỗi retryable theo DBMS/driver.
- Deadlock/serialization retry toàn transaction.
- Permanent errors không retry.
- Unknown commit outcome dùng idempotency/đối soát.
- Có maximum attempts, total budget, backoff và jitter.
- Không giữ connection trong thời gian backoff.
- Retry dừng khi request bị interrupt/cancel.
- Circuit breaker/bulkhead có khi workload cần.

### 28.4. Observability

- Log SQLSTATE/vendor code, phase và query fingerprint.
- Theo dõi latency, pool wait, lock wait và retry.
- Không log secrets/raw parameters.
- Có alert khi timeout/deadlock/retry tăng.
- Có trace ID liên kết app và database.

## 29. Bài tập thực hành có đáp án

### Bài 1. Phân biệt timeout

**Tình huống:** lời gọi lấy connection từ DataSource chờ 1 giây rồi lỗi; chưa có statement nào được tạo.

**Đáp án:** connection-pool acquisition timeout, không phải query timeout. Xem pool saturation, connection leak, query latency và acquisition config.

### Bài 2. Statement timeout JDBC

**Yêu cầu:** giới hạn query ở 2 giây.

**Đáp án:**

```java
PreparedStatement ps = connection.prepareStatement(sql);
ps.setQueryTimeout(2);
```

Đơn vị JDBC là giây; hành vi cancel phụ thuộc driver.

### Bài 3. HTTP timeout có hủy SQL không?

**Đáp án:** không tự động. Cần cancellation propagation hoặc statement timeout/driver mechanism; test với framework và driver thật.

### Bài 4. PostgreSQL statement timeout

**Yêu cầu:** giới hạn statement trong transaction ở 2 giây.

**Đáp án:**

```sql
BEGIN;
SET LOCAL statement_timeout = '2s';
SELECT * FROM orders WHERE tenant_id = 10;
COMMIT;
```

Nếu statement lỗi và transaction aborted, rollback hoặc rollback to savepoint trước khi tiếp tục.

### Bài 5. PostgreSQL lock timeout

**Hỏi:** muốn chờ lock tối đa 300 ms.

**Đáp án:**

```sql
SET LOCAL lock_timeout = '300ms';
```

Đặt trong transaction; không nhầm với tổng statement timeout.

### Bài 6. MySQL lock wait timeout

**Tình huống:** MySQL trả error 1205.

**Đáp án:** lock wait timeout. Kiểm tra InnoDB configuration và transaction state; hành vi mặc định có thể rollback statement chứ không nhất thiết toàn transaction.

### Bài 7. Deadlock

**Tình huống:** PostgreSQL trả SQLSTATE `40P01`.

**Đáp án:** deadlock_detected. Thường rollback transaction victim và retry toàn bộ transaction mới với backoff/jitter nếu thao tác an toàn.

### Bài 8. Serialization failure

**Tình huống:** PostgreSQL trả `40001`.

**Đáp án:** serialization failure. Chạy lại toàn transaction để read/decision/write được tính trên snapshot mới.

### Bài 9. Query canceled

**Tình huống:** PostgreSQL trả `57014`.

**Đáp án:** query_canceled. Xác định do statement_timeout, user cancel hay cơ chế khác. Không retry mọi `57014`.

### Bài 10. SQL Server lock timeout

**Yêu cầu:** giới hạn lock wait 1 giây.

**Đáp án:**

```sql
SET LOCK_TIMEOUT 1000;
```

Đơn vị milliseconds. Khác `CommandTimeout` phía client.

### Bài 11. SQL Server deadlock

**Tình huống:** SQL Server báo error 1205.

**Đáp án:** transaction bị chọn làm deadlock victim; rollback/retry toàn transaction với số lần giới hạn nếu thao tác an toàn.

### Bài 12. Oracle ORA-00054

**Tình huống:** SELECT FOR UPDATE NOWAIT không lấy được lock.

**Đáp án:** resource busy/NOWAIT. Có thể trả conflict hoặc thử lại ngắn hạn theo deadline; không lặp vô hạn.

### Bài 13. Oracle ORA-00001

**Tình huống:** INSERT bị unique constraint violation.

**Đáp án:** integrity/business conflict, thường không retry nguyên xi. Nếu là idempotency key, đọc kết quả hiện có và xác minh request.

### Bài 14. SQLite SQLITE_BUSY

**Tình huống:** SQLite báo database is locked/busy.

**Đáp án:** kiểm tra transaction giữ lock, busy_timeout và concurrency. Có thể retry ngắn với backoff nếu còn deadline và thao tác an toàn.

### Bài 15. SQLite SQLITE_INTERRUPT

**Tình huống:** query trả SQLITE_INTERRUPT sau khi app gọi interrupt.

**Đáp án:** cancellation. Không retry vì người dùng/ứng dụng đã yêu cầu dừng, trừ khi policy riêng nói rõ công việc vẫn cần tiếp tục.

### Bài 16. Connection lost khi COMMIT

**Tình huống:** driver báo network error ngay sau khi gửi COMMIT.

**Đáp án:** unknown commit outcome. Không chạy lại write mù; tra idempotency key/business operation ID hoặc đối soát.

### Bài 17. Retry duplicate key

**Tình huống:** duplicate key xuất hiện sau retry.

**Đáp án:** không retry nguyên xi. Xác định conflict thật hay request idempotent đã hoàn thành; nếu cùng idempotency key và payload hợp lệ, đọc kết quả trước đó.

### Bài 18. Backoff

**Yêu cầu:** base delay 50 ms, exponential backoff.

**Đáp án:** lần 2 khoảng 50 ms, lần 3 100 ms, lần 4 200 ms, lần 5 400 ms trước max delay/jitter. Lần đầu thực hiện ngay.

### Bài 19. Retry storm

**Tình huống:** 1.000 request retry đúng sau 200 ms.

**Đáp án:** thêm jitter, giới hạn attempts/budget, bulkhead và circuit breaker; theo dõi tải DB.

### Bài 20. Future.cancel(true)

**Hỏi:** gọi `future.cancel(true)` có bảo đảm SQL server dừng không?

**Đáp án:** không. Nó yêu cầu interrupt thread; driver có thể cần Statement.cancel hoặc timeout riêng.

### Bài 21. Connection trong lúc backoff

**Tình huống:** transaction deadlock, code sleep 1 giây nhưng vẫn giữ connection.

**Đáp án:** rollback và trả connection trước backoff; mỗi attempt lấy connection/transaction mới.

### Bài 22. Retry trong @Transactional

**Tình huống:** method transactional bắt deadlock rồi lặp query trong cùng transaction.

**Đáp án:** transaction có thể rollback-only/aborted. Retry coordinator nên ở ngoài và mỗi attempt dùng transaction mới.

### Bài 23. SQL syntax error

**Tình huống:** query lỗi vì tên cột sai.

**Đáp án:** không retry. Sửa code/schema/migration; log fingerprint và lỗi đã redaction.

### Bài 24. Query timeout do thiếu index

**Tình huống:** query luôn vượt 2 giây với cùng điều kiện.

**Đáp án:** không retry liên tục. Xem execution plan, index, cardinality, lock wait và số hàng trả về.

### Bài 25. Thao tác trừ tiền

**Tình huống:** UPDATE balance trừ 100 rồi mất connection trước response.

**Đáp án:** không retry mù. Dùng operation ID/idempotency key, ledger/unique constraint và đối soát commit outcome.

### Bài 26. Lock timeout có luôn rollback transaction không?

**Đáp án:** không có quy tắc chung. Hành vi khác theo DBMS/storage engine/configuration. Kiểm tra transaction state và rollback phù hợp.

### Bài 27. Query hoàn thành ngay trước cancel

**Tình huống:** application gọi Statement.cancel nhưng query đã trả kết quả.

**Đáp án:** cancellation có thể đến quá muộn. Xử lý race, đóng tài nguyên và không suy rằng statement chưa có side effect.

### Bài 28. Timeout nhiều tầng

**Tình huống:** gateway 3 giây, query timeout 5 giây.

**Đáp án:** gateway có thể ngắt request trước query timeout. Truyền deadline còn lại và cấu hình query budget nhỏ hơn deadline tổng.

### Bài 29. Test retry mapping

**Yêu cầu:** test SQLSTATE 40001 và 23505.

**Đáp án:** 40001 có thể được allowlist retry toàn transaction; 23505 là constraint conflict, mặc định không retry nguyên xi. Kiểm tra vendor code và driver.

### Bài 30. User bấm Cancel

**Hỏi:** ứng dụng nên retry query đã hủy không?

**Đáp án:** thường không. Đây là tín hiệu không còn cần kết quả. Hủy công việc, cleanup và rollback phù hợp.

## 30. Tài liệu chính thức để tra cứu

Tên property, đơn vị và semantics thay đổi theo driver/DBMS/phiên bản. Hãy đọc tài liệu đúng môi trường đang chạy:

- **JDBC — Statement.setQueryTimeout / cancel:** https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html
- **JDBC — Connection.setNetworkTimeout:** https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html
- **Spring — Transaction Management:** https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- **PostgreSQL — Client Connection Defaults:** https://www.postgresql.org/docs/current/runtime-config-client.html
- **PostgreSQL — Error Codes:** https://www.postgresql.org/docs/current/errcodes-appendix.html
- **MySQL — Server System Variables:** https://dev.mysql.com/doc/refman/8.4/en/server-system-variables.html
- **MySQL — InnoDB Error Handling:** https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html
- **MariaDB — Aborting Statements:** https://mariadb.com/docs/server/ha-and-performance/optimization-and-tuning/query-optimizations/aborting-statements
- **SQL Server — SET LOCK_TIMEOUT:** https://learn.microsoft.com/en-us/sql/t-sql/statements/set-lock-timeout-transact-sql
- **SQL Server — XACT_STATE:** https://learn.microsoft.com/en-us/sql/t-sql/functions/xact-state-transact-sql
- **Oracle — JDBC coding tips:** https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/JDBC-coding-tips.html
- **Oracle — SELECT:** https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html
- **SQLite — busy_timeout:** https://www.sqlite.org/pragma.html#pragma_busy_timeout
- **SQLite — Interrupt API:** https://www.sqlite.org/c3ref/interrupt.html
- **SQLite — Result Codes:** https://www.sqlite.org/rescode.html

## Kết luận

Timeout, cancellation và retry là ba cơ chế liên quan nhưng không thay thế nhau.

- **Timeout** đặt giới hạn cho một bước hoặc toàn request; cần cấu hình pool, connect/login, statement, lock, network và deadline phù hợp.
- **Cancellation** yêu cầu dừng công việc; nó có thể đến muộn và không tự chứng minh transaction đã rollback.
- **Retry** chỉ phù hợp với lỗi tạm thời đã nhận diện, thao tác an toàn, còn deadline và có giới hạn attempts/backoff/jitter.
- **Deadlock và serialization failure** thường cần rollback rồi chạy lại toàn transaction.
- **Syntax, permission, validation và constraint errors** thường không retry nguyên xi.
- **Mất kết nối quanh thời điểm commit** có thể tạo kết quả mơ hồ; dùng idempotency key, unique constraint và đối soát trước khi thử lại thao tác ghi.

Nguyên tắc vận hành: **mỗi request có một deadline; mỗi query có giới hạn phù hợp; mỗi cancellation phải cleanup transaction/resource; và mỗi retry phải có lý do, budget cùng bảo vệ idempotency.** Khi phân loại đúng lỗi và biết database đã ở trạng thái nào, ứng dụng có thể phục hồi từ sự cố tạm thời mà không biến một lỗi ngắn thành retry storm hoặc một thao tác ghi thành side effect trùng lặp.


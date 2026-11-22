# SQLTimeoutException và phân biệt lỗi kết nối với lỗi truy vấn trong JDBC

## 1. Mục tiêu và tình huống thực tế

Trong ứng dụng Java sử dụng JDBC, một request có thể chậm hoặc thất bại ở **hai giai đoạn rất khác nhau**:

1. **Chưa có kết nối**: ứng dụng đang tìm driver, mở socket, xác thực, lấy kết nối từ `DataSource` hoặc chờ pool cấp một logical connection.
2. **Đã có kết nối, đang thực thi truy vấn**: ứng dụng gọi `PreparedStatement.executeQuery()`, `executeUpdate()`, `Statement.execute()` hoặc nhận dữ liệu từ `ResultSet`.

Cả hai giai đoạn đều có thể xuất hiện **`java.sql.SQLTimeoutException`**. Vì vậy **chỉ nhìn tên exception “timeout” không đủ** để kết luận database connection bị hỏng, SQL chạy quá lâu hay có nên retry hay không.

Một vài tình huống điển hình:

- `DataSource.getConnection()` vượt giới hạn đăng nhập/thiết lập kết nối → login timeout.
- `PreparedStatement.executeQuery()` vượt thời gian từ `setQueryTimeout` → query timeout.
- Kết nối mất mạng trong khi đang chạy truy vấn → `SQLTransientConnectionException`, `SQLRecoverableException`, `SQLException` khác hoặc driver-specific error.
- SQL sai cú pháp → `SQLSyntaxErrorException`, không phải lỗi mạng dù request cũng mất thời gian.
- Database từ chối giao dịch do serialization conflict → `SQLTransactionRollbackException`, nên cân nhắc **thực thi lại cả transaction**, không chỉ phát lại câu SQL cuối.
- Network timeout đã hết và driver đóng connection → connection/statement không còn dùng tiếp được, khác với query timeout mà cancel thành công.

Đề bài này thuộc **Ngoại lệ JDBC**. Bài tập trung vào **`SQLTimeoutException` và phân biệt lỗi kết nối với lỗi truy vấn**, rồi đưa ra quy trình retry/rollback/cleanup phù hợp. Nội dung chỉ dùng API JDBC và kiến thức **còn hiện hành đến Java SE 26**, có chú thích nơi behavior phụ thuộc driver và database.

**Kết quả học tập**:
- Hiểu vị trí `SQLTimeoutException` trong cây exception và thực tế nó **không có SQLState chuẩn riêng**.
- Phân biệt login timeout, query timeout, network timeout, pool acquisition timeout và deadline của ứng dụng.
- Biết dùng `Statement.setQueryTimeout(seconds)`, `DataSource.setLoginTimeout(seconds)`, `DriverManager.setLoginTimeout(seconds)`, `Connection.setNetworkTimeout(...)` mà không nhầm mục đích/đơn vị.
- Phân biệt `SQLTransientConnectionException`, `SQLNonTransientConnectionException`, `SQLRecoverableException`, `SQLTransactionRollbackException`, `SQLSyntaxErrorException` và `SQLException` chung.
- Đọc `getSQLState()`, `getErrorCode()` và `getNextException()`; không giả định mọi driver có cùng message hoặc SQLState.
- Quyết định **có cần thay connection, retry transaction hay sửa SQL/config** mà không tạo duplicate writes.
- Có ví dụ Java 17+ **biên dịch/chạy được** và integration snippets dùng `DataSource` thật.

**Kiểm chứng**: Ví dụ `JdbcTimeoutDemo.java` ở phần 11 đã chạy trên OpenJDK 24, biên dịch bằng `javac --release 17`, kết quả **33/33 assertions PASS**. Ví dụ dùng JDBC dynamic proxies để giả lập lỗi; nó kiểm chứng phân loại exception và resource handling, **không giả vờ đo được timeout từ một database thật**.

## 2. Thứ bậc `SQLException`: “timeout” không đồng nghĩa “mất kết nối”

Các exception của JDBC không chỉ có một loại `SQLException`. Java SE hiện hành cung cấp các subclasses có ý nghĩa:

```text
java.lang.Exception
  └── java.sql.SQLException
      ├── SQLTransientException
      │   ├── SQLTimeoutException
      │   ├── SQLTransientConnectionException
      │   └── SQLTransactionRollbackException
      ├── SQLNonTransientException
      │   ├── SQLNonTransientConnectionException
      │   ├── SQLSyntaxErrorException
      │   ├── SQLInvalidAuthorizationSpecException
      │   └── SQLIntegrityConstraintViolationException
      └── SQLRecoverableException
```

Cây trên chỉ hiển thị **một số subclasses liên quan**, không phải danh sách đầy đủ `java.sql`.

**Điểm cần nhớ:** `SQLTimeoutException extends SQLTransientException`. “Transient” ở đây diễn tả **một lỗi có thể không lặp lại khi thử lần nữa trong điều kiện thích hợp**; nó **không bảo đảm** an toàn để tự động replay câu `INSERT`, `UPDATE` hoặc một request đã có side effects.

### 2.1. Bảng nhận diện các nhóm lỗi

| Type hoặc signal | Ý nghĩa JDBC chính | Phản ứng ban đầu |
| --- | --- | --- |
| `SQLTimeoutException` ở `getConnection` | Login/acquire timeout theo JDBC hoặc driver | Phân tích giai đoạn ACQUIRE và pool/network; retry với giới hạn nếu hợp lý |
| `SQLTimeoutException` ở `execute...` | Query timeout sau khi driver xác định hạn mức đã hết và ít nhất đã cố cancel | Không mặc định connection hỏng; xác minh trạng thái giao dịch/kết quả trước retry |
| `SQLTransientConnectionException` | Lỗi connection, thường SQLState class `08` hoặc vendor condition; có khả năng thử lại | Dùng connection mới nếu phù hợp; đánh giá transaction/replay safety |
| `SQLNonTransientConnectionException` | Connection operation khó thành công nếu không sửa nguyên nhân | Kiểm tra endpoint, credentials, TLS, cấu hình, quyền |
| `SQLRecoverableException` | Cần phục hồi: **ít nhất đóng connection cũ, lấy connection mới** | Xem xét retry **toàn transaction/branch** sau phục hồi, không chỉ statement cuối |
| `SQLTransactionRollbackException` | Transaction bị rollback/aborted, thường SQLState class `40` hoặc vendor condition | Có thể retry **toàn transaction** khi được phép |
| `SQLSyntaxErrorException` | SQLState class `42` hoặc vendor condition | Sửa SQL/schema, không retry mù |
| `SQLException` chung, SQLState bắt đầu `08` | Gợi ý nhóm lỗi connection | Phân tích error/vendor/phase; không xem SQLState là bằng chứng duy nhất |
| `SQLException` chung, SQLState bắt đầu `40` | Gợi ý transaction rollback | Kiểm tra transaction state và chính sách retry |
| `SQLException` không rõ subclass/state | Không đủ thông tin để tự động kết luận | Ghi diagnostic an toàn, dừng/điều tra |

**Chú ý:** Driver có thể ném `SQLException` thường thay vì subclass chuyên biệt, và `getSQLState()` có thể là `null`. Các type/subclass cũng có thể theo vendor-specific conditions. Đừng phân loại lỗi chỉ bằng `message.contains("timeout")` hay mã số tự đoán.

### 2.2. Một `SQLTimeoutException` không có SQLState chuẩn

Javadoc Java SE 26 viết rõ: **`SQLTimeoutException` không tương ứng với một standard SQLState**. Constructor mặc định có thể tạo exception với `getSQLState() == null` và `getErrorCode() == 0`.

Bởi vậy:

```java
SQLException ex = new SQLTimeoutException("deadline exceeded");

System.out.println(ex instanceof SQLTransientException); // true
System.out.println(ex.getSQLState() == null);             // true
```

Đây là đoạn code minh họa với imports `java.sql.*`; output đúng với exception vừa tạo trong Java. Nhưng trong database thật **driver có thể gắn SQLState/vendor code cụ thể**; không khẳng định mọi SQLTimeoutException runtime đều trả `null`.

Nếu chỉ kiểm tra `sqlState.startsWith("08")`, bạn có thể bỏ sót login timeout hoặc query timeout thật. **Kiểm tra exception type, operation phase, SQLState và driver-specific fields cùng nhau.**

## 3. Bốn loại timeout cần tách rõ

### 3.1. Login timeout — kết nối chưa được trao cho caller

`DriverManager.setLoginTimeout(seconds)` quy định giới hạn thời gian driver chờ **thiết lập kết nối** sau khi tìm ra driver phù hợp. `DataSource.setLoginTimeout(seconds)` cũng quy định giới hạn cho datasource trong việc lấy kết nối đến database theo hợp đồng `CommonDataSource`.

Ví dụ:

```java
dataSource.setLoginTimeout(5);
try (Connection c = dataSource.getConnection()) {
    // Đã có Connection mới làm SQL operations.
}
```

Snippet này cần `javax.sql.DataSource dataSource` thật đã được cấu hình. `setLoginTimeout` nhận đơn vị **giây**, không phải milliseconds. Với `DriverManager`:

```java
DriverManager.setLoginTimeout(5);
Connection c = DriverManager.getConnection(jdbcUrl, user, password);
```

Đây là snippet cần `jdbcUrl/user/password`/driver thực tế. `DriverManager.setLoginTimeout` là **global setting** tại DriverManager, nên cẩn thận với các ứng dụng đa datasource. Trong hệ thống thực tế thường dùng `DataSource`/pool cấu hình riêng.

**Quan trọng:** Hết thời gian trong `getConnection()` có thể ném `SQLTimeoutException` theo JDBC contract. Trong pool, việc **chờ một connection rảnh** có thể có timeout cấu hình riêng và exception type riêng của pool. Đừng mặc định `DataSource.setLoginTimeout` điều khiển hoàn toàn thời gian chờ queue của mọi connection pool.

### 3.2. Query timeout — statement đang chạy

`Statement.setQueryTimeout(int seconds)` quy định số giây driver chờ `Statement` execute. Theo JDBC Javadoc:
- Driver **phải áp dụng hạn mức** cho `execute`, `executeQuery`, `executeUpdate`.
- Giá trị `0` có nghĩa **không giới hạn query timeout theo setting này**.
- Giá trị âm không hợp lệ và thường ném `SQLException`.
- Hết hạn dẫn tới `SQLTimeoutException` **sau khi driver xác định timeout và ít nhất đã cố gắng cancel statement**.
- Driver có thể áp dụng hạn mức cho `ResultSet` methods, nhưng đây là **vendor-specific**.
- Với `executeBatch`, hạn mức áp dụng cho từng item hay toàn batch là **implementation-defined**.

Ví dụ:

```java
try (PreparedStatement ps =
        conn.prepareStatement("SELECT amount FROM orders WHERE id = ?")) {
    ps.setQueryTimeout(3); // 3 seconds
    ps.setLong(1, id);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả trong scope phù hợp.
        }
    }
}
```

Đây là snippet cần `Connection conn` thực, `id` và bảng `orders`; không phải chương trình JDK-only. Timeout áp dụng theo statement object; đừng nghĩ `setQueryTimeout(3)` đồng nghĩa “mọi hoạt động socket, pool và parse trong request chắc chắn dừng sau 3 giây”.

### 3.3. Network timeout — database operation bị chặn do mạng

`Connection.setNetworkTimeout(Executor executor, int milliseconds)` đặt hạn mức chờ **network/database operation** trên connection theo JDBC. **Đơn vị milliseconds**, khác `setQueryTimeout`.

Java SE 26 `Connection` Javadoc mô tả một điểm tinh tế:
- Nếu **query timeout hết trước** network timeout, driver có cơ hội cancel query; nếu network còn hoạt động thì **statement và connection có thể vẫn dùng tiếp**.
- Nếu **network timeout hết trước** query timeout, hoặc cancel query thất bại vì mạng, driver **đánh dấu connection đã đóng**, giải phóng resources và cả connection/statement trở nên unusable.

Do đó set network timeout **không phải** giải pháp tương đương `Statement.setQueryTimeout`. Network timeout là giới hạn bảo vệ connection trước mạng bị treo, thường cần **cao hơn** query timeout để tạo cơ hội cho cancel.

Snippet cấu hình (cần một `Executor` do ứng dụng sở hữu):

```java
Executor executor = ...; // Executor do application quản lý.
conn.setNetworkTimeout(executor, 8_000); // 8 seconds
```

Đây là **pseudocode snippet**, không standalone vì cần `Executor` và `conn` thực. JDBC có thể ném `SQLFeatureNotSupportedException` nếu driver không hỗ trợ; kiểm tra driver docs và pool policy. Không tạo thread pool vô hạn hoặc giữ executor không shutdown chỉ để set một timeout.

### 3.4. Pool acquisition timeout và application deadline

Ngoài JDBC còn có:
- **Pool acquisition timeout**: ứng dụng chờ lấy một connection có sẵn trong pool.
- **Socket connect/read timeout**: driver-specific properties kiểm soát TCP/network.
- **Database server statement timeout**: database tự hủy operation theo policy.
- **HTTP/request deadline**: thời gian tối đa toàn bộ business operation được phép tiêu tốn.
- **Transaction timeout**: framework/transaction manager đặt hạn mức cho giao dịch.

Các cơ chế này **không nhất thiết cùng exception class** và không bắt buộc áp dụng cùng đơn vị. Pool/driver/server mỗi bên có option riêng; cần xem documentation của đúng version. **Không nên** lấy một con số `setQueryTimeout(5)` rồi suy cả request (bao gồm pool, login, SQL, read rows và downstream calls) sẽ dừng đúng 5 giây.

## 4. Dùng “operation phase” để phân biệt loại timeout

Hãy ghi giai đoạn ngay tại nơi thực hiện JDBC call, thay vì cố suy từ exception message sau khi nó đã bị wrap nhiều tầng.

```text
        HTTP / service operation
                  |
                  v
           DataSource.getConnection()
                  |
            [ ACQUIRE PHASE ]
              /          \
           fail          success
             |             |
  login/pool/network       v
      diagnostics       PreparedStatement
                           |
                           v
                executeQuery/executeUpdate
                           |
                      [ EXECUTE PHASE ]
                        /          \
                     fail         success
                       |            |
              timeout / SQL error   v
                                    ResultSet
                                       |
                                  [ FETCH PHASE ]
                                       |
                                  process rows
```

Ví dụ **cùng class** `SQLTimeoutException` nhưng khác ý nghĩa:
- Ném trong `getConnection()` → lập log `phase=ACQUIRE`, không có `Connection` hợp lệ để close/reuse.
- Ném trong `executeQuery()` → lập log `phase=EXECUTE`, phải quyết định query đã bị cancel thành công hay connection bị đóng, và transaction còn hợp lệ không.
- Ném trong `ResultSet.next()` nếu driver áp dụng query timeout đến fetch → lập log `phase=FETCH`, kiểm tra driver và reader path.

**SQLState không thay thế phase.** Một `SQLTimeoutException` không có chuẩn SQLState riêng; driver có thể dùng custom state. Phase giúp quyết định cần điều tra **DB authentication/network/pool** hay **SQL execution plan/locks/load**.

### 4.1. Ghi log an toàn

Một cấu trúc log nên có:
- `operation`: tên nghiệp vụ hoặc query identifier (không phải SQL với secrets).
- `phase`: `ACQUIRE`, `EXECUTE`, `FETCH`, `COMMIT`.
- `elapsedMs` và budget còn lại.
- Exception class, `getSQLState()` (có thể null), `getErrorCode()`.
- Đã có `Connection` hay chưa, connection state nếu kiểm tra hợp lệ.
- Retry attempt và deadline.
- Idempotency key/request ID nếu policy cho phép.
- Pool name/driver version ở mức không chứa credentials.

Đừng log raw passwords, tokens, database URLs có secrets, full parameter values chứa PII hoặc SQL có sensitive literals. Với `SQLException.getNextException()`, có thể có lỗi bổ sung cần tổng hợp nhưng vẫn phải redact thông tin nhạy cảm.

## 5. SQLState và exception subclasses: cách đọc đúng

`SQLException` có các method:
- `getSQLState()`: code theo SQLState convention nếu driver cung cấp, **có thể null**.
- `getErrorCode()`: vendor-specific integer, không portable giữa databases.
- `getNextException()`: một exception JDBC tiếp theo trong chuỗi.
- `iterator()`: duyệt các SQLExceptions và causes theo contract.
- `getCause()`: underlying cause thông thường của Java exceptions.

Những code phổ biến:

| SQLState class prefix | Nhóm lỗi thường gặp | Lưu ý |
| --- | --- | --- |
| `08` | Connection exception | Có thể cần reconnect; transient vs non-transient còn tùy subclass/cause |
| `40` | Transaction rollback | Retry **cả transaction** khi safe |
| `42` | Syntax/access rule issues | Thường phải sửa SQL/schema/permissions |
| `23` | Integrity constraint violation | Không retry mù khi vi phạm unique/FK |
| `28` | Invalid authorization specification | Sửa credentials/permission |
| `22` | Data exception | Sửa dữ liệu hoặc cách bind |
| `HY...` | Vendor/ODBC style general codes thường gặp | Không suy portability theo prefix này một cách chắc chắn |

Đây là **heuristics để chẩn đoán**, không phải mapping đầy đủ cho mọi driver. JDBC subclasses có thể được tạo theo SQLState classes **hoặc vendor-specified conditions**. Một vài vendors dùng SQLState không chuẩn, đặc biệt với network/socket lỗi.

**Phân loại ưu tiên theo type rồi mới dùng SQLState làm hint**:

```java
static boolean connectionStateHint(SQLException e) {
    String s = e.getSQLState();
    return s != null && s.startsWith("08");
}
```

Đây là method minh họa. Không gọi `e.getSQLState().startsWith("08")` nếu state có thể null; sẽ bị `NullPointerException`.

### 5.1. `SQLRecoverableException` không giống “retry ngay trên connection cũ”

Javadoc `SQLRecoverableException` yêu cầu **recovery steps** trước khi retry. Ở mức tối thiểu:
- **Đóng connection hiện tại**.
- **Lấy connection mới**.
- Thử lại **toàn bộ transaction** (hoặc transaction branch) khi policy cho phép.

Nếu chỉ bắt `SQLRecoverableException` rồi gọi lại `executeUpdate()` trên **cùng `PreparedStatement`**, đó không đúng recovery contract.

### 5.2. SQLTransient vs SQLNonTransient

`SQLTransientException`: một operation đã thất bại có thể thành công khi thử lại mà không cần thay đổi chức năng ứng dụng. Nhưng điều đó không bảo đảm side effects an toàn để replay.

`SQLNonTransientException`: retry cùng operation không có khả năng thành công nếu chưa sửa nguyên nhân. Ví dụ SQL syntax error hoặc credentials sai.

**Không đơn giản hóa thành** “transient = retry luôn”, “non-transient = bỏ qua”. Cần phân biệt operation idempotency, transaction state, deadline, driver guidance và business correctness.

## 6. Timeout và transaction: kết quả có thể chưa rõ

Một điểm nguy hiểm trong distributed systems: **client timeout không đồng nghĩa server chắc chắn rollback mọi thay đổi**.

Ví dụ:
1. App gửi `INSERT INTO payments ...`.
2. Server đã xử lý và có thể commit transaction ở một thời điểm nào đó.
3. Client không nhận được response do network timeout hoặc cancel race.
4. App tự động phát lại `INSERT` → có thể tạo **double charge/duplicate record**.

Vì vậy có **hai câu hỏi độc lập**:

- **Có thể kết nối/SQL chạy lại được không?** Do transient error, health và timeout budget quyết định.
- **Replay có giữ nguyên tính đúng đắn nghiệp vụ không?** Do idempotency key, transaction outcome, unique constraints, deduplication và domain semantics quyết định.

Một read-only `SELECT` đơn giản thường dễ retry hơn, **nhưng cũng không mặc định** nếu query gọi stored procedure/hàm gây side effects, giữ locks quan trọng hoặc phụ thuộc snapshot giao dịch.

### 6.1. Hướng xử lý cho từng trường hợp

| Trường hợp | Có thể thử lại? | Hành động an toàn |
| --- | --- | --- |
| Login timeout, chưa có connection | Thường có, nếu lỗi transient và deadline còn | Retry kết nối có giới hạn/backoff, kiểm tra pool/network |
| Query timeout, SELECT thuần, replay-safe | Có thể | Rollback nếu transaction cần, dùng statement mới hoặc connection phù hợp, budget/backoff |
| Query timeout, UPDATE/INSERT không có idempotency | **Không tự động** | Xác minh outcome, reconcile theo PK/idempotency key |
| `SQLTransientConnectionException` trong transaction | Có thể, nhưng connection cũ không đáng tin | Kiểm tra trạng thái, thường lấy connection mới, retry whole unit nếu safe |
| `SQLRecoverableException` | Sau recovery | Đóng connection cũ, lấy connection mới, retry **entire transaction/branch** nếu safe |
| `SQLTransactionRollbackException` | Có thể | Retry **toàn transaction** nếu replay-safe và policy cho phép |
| `SQLSyntaxErrorException` | Không cho cùng SQL/config | Sửa SQL/schema |
| `SQLNonTransientConnectionException` | Không trước khi sửa nguyên nhân | Sửa endpoint/TLS/auth/config |
| Generic SQLState `08` | Chỉ là dấu hiệu | Điều tra type/driver/phase/connection liveness |
| Unknown `SQLException` | Không mặc định | Ghi diagnostic an toàn và dừng để tránh lỗi dây chuyền |

### 6.2. Đặt retry budget

Một policy có thể có:
- Tối đa 2–3 attempts cho operation **replay-safe** (con số là ví dụ, không phải chuẩn JDBC).
- Backoff có jitter để tránh gây “thundering herd”.
- **Absolute deadline** của request: không retry nếu quá hạn.
- Circuit breaker/rate limit khi database đang quá tải.
- Idempotency key hoặc unique constraint khi gửi write.
- Transaction wrapper retry **từ đầu**, không chỉ method cuối.
- Metrics cho attempts, categories và final outcomes.

Không cho phép infinite retry trong request thread. Nếu connection pool đang cạn, mỗi retry có thể làm tình hình tệ hơn.

## 7. Các API timeout hiện đại và quan hệ ưu tiên

| API | Đối tượng | Đơn vị | Điều kiểm soát |
| --- | --- | --- | --- |
| `DriverManager.setLoginTimeout(int)` | DriverManager | giây | Thời gian mở connection khi dùng DriverManager |
| `DataSource.setLoginTimeout(int)` | DataSource | giây | Login timeout theo datasource contract |
| `Statement.setQueryTimeout(int)` | Statement/PreparedStatement | giây | Thời gian thực thi statement |
| `Connection.setNetworkTimeout(Executor,int)` | Connection | milliseconds | Giới hạn network/database operation; hết hạn có thể làm connection closed |
| Pool acquisition timeout | Pool implementation | driver/pool-specific | Thời gian chờ lấy connection rảnh |
| Driver socket/connect timeout | Driver implementation | vendor-specific | Network socket connect/read |
| Server-side statement timeout | Database server | vendor-specific | Query cancellation theo database |
| Request deadline | Application/framework | ứng dụng quyết định | Tổng thời gian business operation |

### 7.1. Thứ tự cấu hình có chủ đích

Ví dụ business request deadline là 10 giây. Một chính sách minh họa có thể:
- Pool acquire budget 1–2 giây.
- Login/network connection budgets riêng.
- Query timeout 3 giây trên statement.
- Network timeout 6–8 giây để query cancellation có cơ hội hoạt động.
- Giữ thêm budget cho fetch, mapping, rollback, cleanup và response.

Đây **chỉ là ví dụ thiết kế**, không phải công thức chung hay khẳng định JDBC sẽ bảo đảm wall-clock deadline chính xác. Trên một vài drivers, timeout granularity/rounding và cancel behavior khác nhau. Không dùng nhiều timeouts độc lập rồi cộng số giây một cách máy móc; **absolute deadline** của request giúp giữ tổng ngân sách.

### 7.2. `Statement.cancel()` có thay query timeout không?

`Statement.cancel()` gửi yêu cầu hủy statement nếu driver hỗ trợ. Một `SQLTimeoutException` theo JDBC query timeout nghĩa là driver xác định timeout và **ít nhất đã cố cancel**; không đồng nghĩa cancellation hoàn tất ngay hoặc SQL chưa có side effect. `Statement.cancel()` có thể được app gọi khi user hủy request, nhưng cần phân biệt **attempted cancel** với **transaction confirmed rolled back**.

### 7.3. Một exception do pool ném có thể không cùng class

Ví dụ một pool tự đặt acquisition timeout có thể bọc nguyên nhân thành `SQLException` hoặc type của pool/framework. Hãy biết pool library/version đang dùng và log `phase=ACQUIRE`. Không assume `SQLTimeoutException` luôn đồng nghĩa chính xác “SQL query slow”.

## 8. Thiết kế classifier an toàn

Một classifier hữu ích nên trả ít nhất:
- **Category**: login timeout, query timeout, transient connection, recoverable connection, rollback, syntax error, unknown.
- **Action hint**: retry có giới hạn, thay connection và retry transaction, sửa SQL/config, hoặc reconcile.
- **Context**: operation phase và **replaySafe** do tầng nghiệp vụ xác định.

Không để classifier tự xác định side-effect safety chỉ từ một exception object. Một `INSERT` và một `SELECT` có thể ném cùng subclass; retry safety khác nhau.

Pseudocode:

```text
SQLException
    |
    +-- instanceof SQLTimeoutException?
    |      +-- phase=ACQUIRE -> LOGIN_TIMEOUT
    |      +-- phase=EXECUTE -> QUERY_TIMEOUT
    |
    +-- SQLRecoverableException?
    |      -> close old connection, borrow new, retry entire txn if safe
    |
    +-- SQLTransientConnectionException?
    |      -> investigate link; new connection and bounded retry if safe
    |
    +-- SQLNonTransientConnectionException?
    |      -> fix cause, not blind retry
    |
    +-- SQLTransactionRollbackException?
    |      -> retry whole transaction if replay-safe
    |
    +-- SQLSyntaxErrorException?
    |      -> fix SQL/schema
    |
    +-- generic SQLState prefix "08"/"40"?
    |      -> classification HINT only
    |
    +-- otherwise -> inspect and stop
```

Trên thực tế thứ tự check subclass có thể tùy code, nhưng **`SQLTimeoutException` phải được xử lý trước `SQLTransientException` tổng quát** để không mất tín hiệu timeout. `SQLRecoverableException` không phải subclass `SQLTransientException`; nó có recovery contract riêng.

## 9. Kiểm thử bằng mock JDBC, không cần database thật

Để có ví dụ độc lập, ta dựng:
- `DataSource` giả trả `Connection` hoặc ném `SQLTimeoutException` ở `getConnection`.
- `Connection` giả trả `PreparedStatement`, tự đếm số lần `close`.
- `PreparedStatement` giả nhận `setQueryTimeout`, ném timeout ở `executeQuery` hoặc trả `ResultSet` có một hàng.
- `ResultSet` giả trả giá trị `7` và hỗ trợ `close`.
- Một classifier đọc exception type, SQLState, phase và flag `replaySafe`.
- Một bộ assertions kiểm tra cả flows thành công/thất bại, cleanup và an toàn retry.

Không cần `H2`, PostgreSQL, MySQL hay driver nào khác: tất cả là Java SE `java.sql`, `javax.sql` và `java.lang.reflect.Proxy`. Mock chỉ hỗ trợ những methods cần test; các methods khác ném `SQLFeatureNotSupportedException`.

**Lưu ý:** Mock tạo SQLTimeoutException theo ý test; nó không đo thời gian thật, không thực sự mở socket/cancel SQL và không thay thế integration tests với driver/server.

## 10. Chương trình Java 17+ đầy đủ — `JdbcTimeoutDemo.java`

Lưu nội dung dưới đây vào **một file duy nhất** `JdbcTimeoutDemo.java`. Source sử dụng Java 17 `record` và `switch expression`. Đã kiểm chứng với `javac --release 17`/OpenJDK 24.

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLNonTransientConnectionException;
import java.sql.SQLRecoverableException;
import java.sql.SQLSyntaxErrorException;
import java.sql.SQLTimeoutException;
import java.sql.SQLTransactionRollbackException;
import java.sql.SQLTransientConnectionException;
import java.sql.SQLTransientException;
import javax.sql.DataSource;

public final class JdbcTimeoutDemo {
    enum Phase { ACQUIRE, EXECUTE }
    record Decision(String category, String action) { }
    static int passed;

    static void check(String label, boolean ok) {
        if (!ok) throw new AssertionError("FAIL " + label);
        System.out.println("PASS " + label);
        passed++;
    }

    static Decision classify(
            SQLException e, Phase phase, boolean replaySafe) {
        if (e instanceof SQLTimeoutException) {
            if (phase == Phase.ACQUIRE) {
                return new Decision(
                        "LOGIN_TIMEOUT", "RECONNECT_WITH_BUDGET");
            }
            return new Decision("QUERY_TIMEOUT",
                    replaySafe ? "RETRY_IF_CONFIRMED_SAFE"
                            : "RECONCILE_BEFORE_RETRY");
        }
        if (e instanceof SQLRecoverableException) {
            return new Decision("RECOVERABLE_CONNECTION",
                    replaySafe ? "NEW_CONNECTION_RETRY_TRANSACTION"
                            : "NEW_CONNECTION_RECONCILE");
        }
        if (e instanceof SQLTransientConnectionException) {
            return new Decision("TRANSIENT_CONNECTION",
                    replaySafe ? "RECONNECT_WITH_BUDGET"
                            : "RECONCILE_BEFORE_RETRY");
        }
        if (e instanceof SQLNonTransientConnectionException) {
            return new Decision(
                    "NONTRANSIENT_CONNECTION", "FIX_CAUSE");
        }
        if (e instanceof SQLTransactionRollbackException) {
            return new Decision("TRANSACTION_ROLLBACK",
                    replaySafe ? "RETRY_ENTIRE_TRANSACTION"
                            : "RECONCILE_BEFORE_RETRY");
        }
        if (e instanceof SQLSyntaxErrorException) {
            return new Decision("SYNTAX_ERROR", "FIX_SQL");
        }

        String state = e.getSQLState();
        if (state != null && state.length() >= 2
                && state.startsWith("08")) {
            return new Decision("SQLSTATE_08_HINT",
                    "INSPECT_CONNECTION_AND_OPERATION");
        }
        if (state != null && state.length() >= 2
                && state.startsWith("40")) {
            return new Decision("SQLSTATE_40_HINT",
                    "INSPECT_TRANSACTION");
        }
        return new Decision("UNKNOWN_SQL", "INSPECT_AND_STOP");
    }

    @SuppressWarnings("unchecked")
    static <T> T proxy(Class<T> api, InvocationHandler h) {
        return (T) Proxy.newProxyInstance(
                JdbcTimeoutDemo.class.getClassLoader(),
                new Class<?>[] { api },
                h);
    }

    static final class MockDb {
        final SQLException acquireFailure;
        final SQLException executeFailure;
        final boolean queryTimeoutSupported;
        int loginTimeout;
        int requestedQueryTimeout = -1;
        int connectionCloseCount;
        int statementCloseCount;
        int resultCloseCount;

        MockDb(
                SQLException acquireFailure,
                SQLException executeFailure,
                boolean queryTimeoutSupported) {
            this.acquireFailure = acquireFailure;
            this.executeFailure = executeFailure;
            this.queryTimeoutSupported = queryTimeoutSupported;
        }

        DataSource dataSource() {
            return proxy(DataSource.class, (p, m, a) -> {
                return switch (m.getName()) {
                    case "setLoginTimeout" -> {
                        loginTimeout = (Integer) a[0];
                        yield null;
                    }
                    case "getLoginTimeout" -> loginTimeout;
                    case "getConnection" -> {
                        if (acquireFailure != null) {
                            throw acquireFailure;
                        }
                        yield connection();
                    }
                    default ->
                            throw new SQLFeatureNotSupportedException(
                                    "Not implemented by mock: "
                                            + m.getName());
                };
            });
        }

        Connection connection() {
            return proxy(Connection.class, new InvocationHandler() {
                boolean closed;

                @Override
                public Object invoke(
                        Object p, Method m, Object[] a)
                        throws SQLException {
                    return switch (m.getName()) {
                        case "close" -> {
                            if (!closed) {
                                closed = true;
                                connectionCloseCount++;
                            }
                            yield null;
                        }
                        case "isClosed" -> closed;
                        default -> {
                            if (closed) {
                                throw new SQLNonTransientConnectionException(
                                        "connection is closed", "08003");
                            }
                            if (m.getName().equals(
                                    "prepareStatement")) {
                                yield statement();
                            }
                            throw new SQLFeatureNotSupportedException(
                                    m.getName());
                        }
                    };
                }
            });
        }

        PreparedStatement statement() {
            return proxy(PreparedStatement.class,
                    new InvocationHandler() {
                boolean closed;
                int seconds;

                @Override
                public Object invoke(
                        Object p, Method m, Object[] a)
                        throws SQLException {
                    return switch (m.getName()) {
                        case "close" -> {
                            if (!closed) {
                                closed = true;
                                statementCloseCount++;
                            }
                            yield null;
                        }
                        case "isClosed" -> closed;
                        default -> {
                            if (closed) {
                                throw new SQLException(
                                        "closed statement");
                            }
                            yield switch (m.getName()) {
                                case "setQueryTimeout" -> {
                                    if (!queryTimeoutSupported) {
                                        throw new SQLFeatureNotSupportedException(
                                                "query timeout unsupported");
                                    }
                                    int n = (Integer) a[0];
                                    if (n < 0) {
                                        throw new SQLException(
                                                "negative timeout");
                                    }
                                    seconds = n;
                                    requestedQueryTimeout = n;
                                    yield null;
                                }
                                case "getQueryTimeout" -> seconds;
                                case "executeQuery" -> {
                                    if (executeFailure != null) {
                                        throw executeFailure;
                                    }
                                    yield result();
                                }
                                default ->
                                        throw new SQLFeatureNotSupportedException(
                                                m.getName());
                            };
                        }
                    };
                }
            });
        }

        ResultSet result() {
            return proxy(ResultSet.class,
                    new InvocationHandler() {
                boolean closed;
                boolean visited;
                boolean onRow;

                @Override
                public Object invoke(
                        Object p, Method m, Object[] a)
                        throws SQLException {
                    return switch (m.getName()) {
                        case "close" -> {
                            if (!closed) {
                                closed = true;
                                resultCloseCount++;
                            }
                            yield null;
                        }
                        case "isClosed" -> closed;
                        default -> {
                            if (closed) {
                                throw new SQLException(
                                        "closed result");
                            }
                            yield switch (m.getName()) {
                                case "next" -> {
                                    onRow = !visited;
                                    visited = true;
                                    yield onRow;
                                }
                                case "getInt" -> {
                                    if (!onRow) {
                                        throw new SQLException("no row");
                                    }
                                    yield 7;
                                }
                                default ->
                                        throw new SQLFeatureNotSupportedException(
                                                m.getName());
                            };
                        }
                    };
                }
            });
        }
    }

    static SQLException runQuery(
            DataSource ds, int timeoutSeconds) {
        try (Connection conn = ds.getConnection();
             PreparedStatement stmt =
                     conn.prepareStatement("SELECT 7")) {
            stmt.setQueryTimeout(timeoutSeconds);

            try (ResultSet rs = stmt.executeQuery()) {
                check("query-row",
                        rs.next() && rs.getInt(1) == 7);
            }
            return null;
        } catch (SQLException failure) {
            return failure;
        }
    }

    public static void main(String[] args) throws Exception {
        SQLTimeoutException login =
                new SQLTimeoutException("login deadline");
        SQLTimeoutException query =
                new SQLTimeoutException("query deadline");

        check("timeout-is-transient",
                login instanceof SQLTransientException);
        check("timeout-no-standard-state",
                login.getSQLState() == null);
        check("login-phase",
                classify(login, Phase.ACQUIRE, true).category()
                        .equals("LOGIN_TIMEOUT"));
        check("login-action",
                classify(login, Phase.ACQUIRE, true).action()
                        .equals("RECONNECT_WITH_BUDGET"));
        check("query-phase",
                classify(query, Phase.EXECUTE, true).category()
                        .equals("QUERY_TIMEOUT"));
        check("safe-query-retry-guarded",
                classify(query, Phase.EXECUTE, true).action()
                        .equals("RETRY_IF_CONFIRMED_SAFE"));
        check("unsafe-query-not-retried-blindly",
                classify(query, Phase.EXECUTE, false).action()
                        .equals("RECONCILE_BEFORE_RETRY"));

        MockDb loginDb = new MockDb(login, null, true);
        DataSource source = loginDb.dataSource();
        source.setLoginTimeout(3);
        check("login-timeout-configured",
                source.getLoginTimeout() == 3);

        SQLException observedLogin = runQuery(source, 2);
        check("login-failure-during-acquire",
                observedLogin instanceof SQLTimeoutException);
        check("no-connection-acquired",
                loginDb.connectionCloseCount == 0);

        MockDb queryDb = new MockDb(null, query, true);
        SQLException observedQuery =
                runQuery(queryDb.dataSource(), 2);
        check("query-failure-during-execute",
                observedQuery instanceof SQLTimeoutException);
        check("query-timeout-configured",
                queryDb.requestedQueryTimeout == 2);
        check("query-resources-closed",
                queryDb.connectionCloseCount == 1
                && queryDb.statementCloseCount == 1);
        check("query-no-row-produced",
                queryDb.resultCloseCount == 0);

        MockDb successDb = new MockDb(null, null, true);
        check("successful-query",
                runQuery(successDb.dataSource(), 2) == null);
        check("successful-resources-closed",
                successDb.connectionCloseCount == 1
                && successDb.statementCloseCount == 1
                && successDb.resultCloseCount == 1);

        MockDb unsupportedDb =
                new MockDb(null, null, false);
        check("unsupported-timeout",
                runQuery(unsupportedDb.dataSource(), 2)
                    instanceof SQLFeatureNotSupportedException);
        check("unsupported-cleanup",
                unsupportedDb.connectionCloseCount == 1
                && unsupportedDb.statementCloseCount == 1);

        SQLTransientConnectionException temporary =
                new SQLTransientConnectionException(
                        "link down", "08006");
        check("transient-connection",
                classify(temporary, Phase.EXECUTE, true).category()
                        .equals("TRANSIENT_CONNECTION"));
        check("transient-unsafe-no-blind-retry",
                classify(temporary, Phase.EXECUTE, false).action()
                        .equals("RECONCILE_BEFORE_RETRY"));

        SQLNonTransientConnectionException badConfig =
                new SQLNonTransientConnectionException(
                        "wrong endpoint", "08001");
        check("nontransient-connection",
                classify(badConfig, Phase.ACQUIRE, true).category()
                        .equals("NONTRANSIENT_CONNECTION"));
        check("nontransient-fix-cause",
                classify(badConfig, Phase.ACQUIRE, true).action()
                        .equals("FIX_CAUSE"));

        SQLRecoverableException recoverable =
                new SQLRecoverableException(
                        "replace connection", "08006");
        check("recoverable-new-connection",
                classify(recoverable, Phase.EXECUTE, true).action()
                        .equals("NEW_CONNECTION_RETRY_TRANSACTION"));
        check("recoverable-unsafe-reconcile",
                classify(recoverable, Phase.EXECUTE, false).action()
                        .equals("NEW_CONNECTION_RECONCILE"));

        SQLTransactionRollbackException rollback =
                new SQLTransactionRollbackException(
                        "serialization", "40001");
        check("rollback-transaction",
                classify(rollback, Phase.EXECUTE, true).action()
                        .equals("RETRY_ENTIRE_TRANSACTION"));
        check("rollback-unsafe",
                classify(rollback, Phase.EXECUTE, false).action()
                        .equals("RECONCILE_BEFORE_RETRY"));

        SQLSyntaxErrorException syntax =
                new SQLSyntaxErrorException(
                        "invalid SQL", "42000");
        check("syntax-fix",
                classify(syntax, Phase.EXECUTE, true).action()
                        .equals("FIX_SQL"));

        SQLException generic08 =
                new SQLException("driver specific", "08S01");
        check("generic-sqlstate08-hint",
                classify(generic08, Phase.EXECUTE, true).category()
                        .equals("SQLSTATE_08_HINT"));

        SQLException generic40 =
                new SQLException("rollback vendor", "40P01");
        check("generic-sqlstate40-hint",
                classify(generic40, Phase.EXECUTE, true).category()
                        .equals("SQLSTATE_40_HINT"));

        check("unknown-sql-requires-inspection",
                classify(new SQLException("unknown"),
                        Phase.EXECUTE, true)
                    .action().equals("INSPECT_AND_STOP"));

        SQLException withNext =
                new SQLException("root", "08001", 23);
        withNext.setNextException(
                new SQLException("detail", "HY000", 44));
        check("diagnostics-next-sql-exception",
                withNext.getNextException().getErrorCode() == 44);
        check("diagnostics-vendor-code",
                withNext.getErrorCode() == 23);

        System.out.println("passed=" + passed);
    }
}
```

### 10.1. Chạy bằng JDK 17+

Trong folder chứa file:

```bash
javac --release 17 -encoding UTF-8 JdbcTimeoutDemo.java
java JdbcTimeoutDemo
```

Chạy được trên Linux/macOS hoặc Windows PowerShell nếu JDK 17+ đã nằm trong PATH. Không cần mở database, cài driver hoặc biến môi trường chứa credentials.

### 10.2. Stdout chính xác đã kiểm chứng

```text
PASS timeout-is-transient
PASS timeout-no-standard-state
PASS login-phase
PASS login-action
PASS query-phase
PASS safe-query-retry-guarded
PASS unsafe-query-not-retried-blindly
PASS login-timeout-configured
PASS login-failure-during-acquire
PASS no-connection-acquired
PASS query-failure-during-execute
PASS query-timeout-configured
PASS query-resources-closed
PASS query-no-row-produced
PASS query-row
PASS successful-query
PASS successful-resources-closed
PASS unsupported-timeout
PASS unsupported-cleanup
PASS transient-connection
PASS transient-unsafe-no-blind-retry
PASS nontransient-connection
PASS nontransient-fix-cause
PASS recoverable-new-connection
PASS recoverable-unsafe-reconcile
PASS rollback-transaction
PASS rollback-unsafe
PASS syntax-fix
PASS generic-sqlstate08-hint
PASS generic-sqlstate40-hint
PASS unknown-sql-requires-inspection
PASS diagnostics-next-sql-exception
PASS diagnostics-vendor-code
passed=33
```

Fixture đã được biên dịch `javac --release 17` và chạy trên OpenJDK 24: **33/33 kiểm tra PASS**. Tên labels và thứ tự output trên là từ code fixture, không phải output của một JDBC driver thật.

### 10.3. Các phần quan trọng trong mã

- `Phase.ACQUIRE` vs `Phase.EXECUTE` giúp cùng `SQLTimeoutException` được phân loại đúng lúc.
- `Decision` là một Java `record` chỉ giữ **hint**, không thực hiện retry tự động.
- `replaySafe` do caller quyết định: `false` ngăn auto replay writes ngay cả khi timeout là transient.
- `MockDb` tạo các dynamic proxies cho `DataSource`, `Connection`, `PreparedStatement`, `ResultSet`.
- `source.setLoginTimeout(3)` được mock ghi lại; không mở socket hay đợi 3 giây thật.
- `stmt.setQueryTimeout(2)` được mock ghi lại; không có timer thật.
- Hai sự kiện timeout được giả lập ở **hai method khác nhau**: `getConnection` và `executeQuery`.
- `try-with-resources` đóng ResultSet/Statement/Connection theo ownership, kể cả khi execute ném lỗi.
- `SQLFeatureNotSupportedException` kiểm thử nhánh driver không hỗ trợ setter.
- `SQLTransientConnectionException` và `SQLNonTransientConnectionException` kiểm tra type-based classification.
- `SQLRecoverableException` đòi thay connection và xử lý entire transaction.
- `SQLTransactionRollbackException` yêu cầu retry entire transaction, không chỉ query cuối.
- `SQLException.getSQLState` chỉ làm dấu hiệu với các errors chung, không tự quyết định replay.
- `getNextException`/`getErrorCode` minh họa diagnostic metadata.

**Phạm vi chứng cứ:** Mock không chứng minh một driver hiện hành có query cancellation chính xác, không kiểm tra lock wait trên database thật, không đo deadline, không mô phỏng partial commit và không khẳng định pool nào cũng ném đúng subclass. Cần integration tests trên driver/server/pool thực tế.

## 11. Mẫu code thực tế với `DataSource`: giữ phase rõ ràng

Một helper cho query read-only (chỉ minh họa; cần datasource/schema):

```java
import java.sql.*;
import javax.sql.DataSource;

static int readAmount(DataSource source, long id)
        throws SQLException {

    final Connection conn;
    try {
        conn = source.getConnection();
    } catch (SQLTimeoutException loginTimeout) {
        // phase=ACQUIRE: chưa có borrowed Connection.
        throw loginTimeout;
    }

    try (conn) {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT amount FROM orders WHERE id = ?")) {
            ps.setQueryTimeout(3);
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("order not found");
                }
                return rs.getInt(1);
            }
        } catch (SQLTimeoutException queryTimeout) {
            // phase=EXECUTE/FETCH trong try:
            // không mặc định conn hỏng; vẫn cần transaction policy.
            throw queryTimeout;
        }
    }
}
```

Đây là một **method snippet**, không standalone, cần bảng `orders` và `DataSource` thật. `try (conn)` là Java 9+ syntax khi biến hiệu quả final đã có giá trị, phù hợp với `--release 17`.

Tại sao tách hai `try/catch`?
- `getConnection` nằm trong block riêng → timeout ở đây là **acquisition/login phase**.
- Query block chỉ bắt sau khi connection đã cấp → dễ phân biệt **execution/fetch phase**.
- `Connection` được close khi xong, không đóng nhầm một connection chưa bao giờ được cấp.
- Timeout và SQLState được propagate lên layer orchestration để xét retry/metrics; không nuốt exception.

**Bẫy với snippet:** `ps.setQueryTimeout(3)` chỉ giới hạn statement, không điều khiển toàn bộ thời gian `rs.next()` trên tất cả drivers. Nếu cần phân biệt chính xác `EXECUTE` và `FETCH`, đặt catch riêng cho từng method call thay vì một catch bao trùm cả block.

### 11.1. Một classifier helper cho hệ thống thật

Bạn có thể bắt specific types theo thứ tự:

```java
try {
    // JDBC call đã biết phase và replay policy.
} catch (SQLTimeoutException timeout) {
    // Xử lý login/query dựa vào phase.
} catch (SQLRecoverableException recoverable) {
    // Close old connection, acquire new, retry entire txn if safe.
} catch (SQLTransientConnectionException transientConnection) {
    // Điều tra/đổi connection, retry có giới hạn nếu safe.
} catch (SQLNonTransientConnectionException permanentConnection) {
    // Sửa nguyên nhân, không retry mù.
} catch (SQLTransactionRollbackException rollback) {
    // Entire-transaction retry khi replay-safe.
} catch (SQLException other) {
    // Đọc SQLState, vendor code, chained exceptions.
}
```

Đây là **pseudocode Java** vì phần `try` chứa placeholder comment và không gọi DB, cần được đặt trong method và handler bodies thực tế. `SQLTimeoutException` không nên bị swallow bởi `catch (SQLTransientException)` chung ở phía trước; nếu bắt superclass trước, subclass-specific catch có thể trở nên unreachable.

### 11.2. Lỗi `getConnection` không giống lỗi query

Một query có thể timeout vì:
- Không có index phù hợp, plan kém.
- Database bị lock wait/deadlock.
- Hệ thống quá tải CPU/I/O.
- Dữ liệu quá nhiều và server quá chậm.
- Statement timeout được đặt quá thấp so với SLO.

Một connection acquisition có thể timeout vì:
- Pool cạn logical connections hoặc leak.
- Database hết slots, overload, restart.
- Network firewall/TLS handshake chậm.
- DNS/endpoint không ổn định.
- Credentials/auth server chậm.
- Driver connect/socket settings không phù hợp.

Đừng giải quyết **pool exhaustion** bằng tăng `Statement.setQueryTimeout`; cũng đừng giải quyết **SQL plan chậm** chỉ bằng tăng pool size. Phải quan sát đúng phase và metrics.

## 12. Sự kiện “timeout” không tự cho biết tình trạng connection

Sau query timeout có nhiều khả năng:
- Statement được cancel, connection vẫn usable.
- Transaction bị đánh dấu aborted và cần rollback, tùy database.
- Driver không cancel được vì network error, connection unusable.
- Network timeout đã đóng connection.
- Operation bên server vẫn đang tiếp tục hoặc đã tạo side effects, tùy timing/semantics.

Do đó **không** thiết kế mặc định:

```java
catch (SQLTimeoutException ex) {
    // Sai: luôn coi connection tốt và retry cùng statement.
    statement.executeUpdate();
}
```

Cũng không nên luôn coi query timeout là mất connection để hủy cả pool. Với pooled connection, **close borrowed logical handle** theo try-with-resources; pool có trách nhiệm loại bỏ unhealthy underlying physical connection nếu có cơ chế phát hiện phù hợp.

### `Connection.isValid(int seconds)` có giải quyết hết không?

`Connection.isValid(timeout)` kiểm tra connection theo JDBC driver; nó có thể dùng để kiểm tra liveness khi cần và hợp đồng cho phép. Nhưng:
- Nó không xác minh transaction đã commit hay rollback.
- Không quyết định INSERT có side effect trước timeout.
- Không thay thế query timeout hoặc network timeout.
- Tốn thêm roundtrip/driver operation.
- Pool có thể đã có health-check riêng và dùng `isValid` bên trong.

Dùng `isValid` chỉ khi thích hợp với architecture, không kiểm tra redundant trên mọi query nếu pool đã quản lý health.

## 13. Retry ở transaction boundary, không rải trong từng DAO method

Trong app dùng transaction, một operation có thể bao gồm:

```text
BEGIN
   UPDATE inventory
   INSERT order
   INSERT audit event
COMMIT
```

Nếu database abort transaction sau một statement timeout/serialization conflict, chỉ retry `INSERT audit event` **không thể** phục hồi tính đúng đắn của toàn bộ unit. Ngay cả khi statement có thể thực thi lại, transaction vẫn cần một boundary mới.

Một chiến lược thực tế:
1. Tầng orchestration xác định **business operation replay-safe**.
2. Bắt các transient/recoverable/rollback errors theo loại và context.
3. Đảm bảo transaction cũ được rollback/closed theo policy (hoặc kết quả chưa rõ được reconcile).
4. **Lấy connection mới** khi connection đã hỏng hoặc theo `SQLRecoverableException` contract.
5. Chạy lại **entire transaction** trong deadline và max-attempt budget.
6. Nếu write không chắc outcome, dùng **idempotency key/unique constraint** hoặc đọc trạng thái trước khi thử lại.
7. Không retry liên tục vào server đang quá tải; dùng backoff/jitter/circuit breaker.

**Lưu ý:** Một số transaction managers (Spring, Jakarta Transactions, JTA, v.v.) đã sở hữu commit/rollback và transaction propagation. Đừng tự gọi `conn.commit()` trong helper nếu framework quản lý transaction.

### 13.1. Idempotency keys cho writes

Ví dụ ứng dụng nhận request thanh toán có `paymentRequestId` duy nhất:
- DB có unique constraint trên request ID.
- Mọi attempts xử lý cùng request dùng cùng idempotency key.
- Khi timeout không rõ outcome, ứng dụng truy vấn state theo request ID và quyết định trả kết quả hay thực hiện phần còn thiếu.
- Không phát sinh double charge hay duplicate order chỉ vì client timeout.

Đây là **pattern hệ thống**, không phải method của JDBC. `SQLTimeoutException` chỉ nói có timeout trong JDBC; business safety phải do application quản lý.

### 13.2. Đặt max attempts và absolute deadline

Không dùng:

```java
while (true) {
    try {
        performDatabaseWrite();
        break;
    } catch (SQLTimeoutException e) {
        // Sai: infinite retry, không kiểm tra side effects.
    }
}
```

Đây là **anti-pattern minh họa**, không standalone vì method placeholder. Production retry nên được giới hạn, có backoff/jitter và theo request deadline. Retry budgets không có một giá trị JDBC chuẩn; cấu hình theo tải thực tế.

## 14. Diagnostic chain và error handling

Một `SQLException` có thể được nối với các SQLException khác:

```java
SQLException root = new SQLException(
        "connection failed", "08001", 23);
root.setNextException(
        new SQLException("detail", "HY000", 44));

System.out.println(root.getSQLState()); // 08001
System.out.println(root.getErrorCode()); // 23
System.out.println(
        root.getNextException().getErrorCode()); // 44
```

Đây là đoạn code minh họa, output được xác định bởi chính constructor calls. Các mã `23` và `44` trong đoạn này **không phải error codes của một vendor cụ thể**.

Trong handler thực:
- Lưu class name, SQLState, vendor code, phase.
- Đọc exception chain và root cause (chẳng hạn `SocketTimeoutException` nằm trong `getCause()` nếu driver bao lại).
- Dùng `getNextException()` để thấy errors bổ sung, nhưng đề phòng chuỗi nhiều phần và không log secrets.
- Không chỉ dùng `e.getMessage()` để phân loại, vì message có thể thay theo driver version, locale hoặc SQL.
- Nếu error là generic `SQLException` có SQLState `08...`, coi đó là **gợi ý connection issue**, không tự gán là recoverable hay replay-safe.
- Khi retry, ghi attempt number và final outcome; không log mỗi lỗi thành alert độc lập gây nhiễu.

### 14.1. `SQLException` từ `close` có thể bị suppressed

Trong `try-with-resources`, nếu body ném `SQLException` và việc close cũng ném exception, lỗi close thường xuất hiện trong `getSuppressed()`. Không chỉ ghi mỗi root message rồi đánh mất các lỗi cleanup. Trước khi thay connection, kiểm tra pool/driver handling và không cố reuse resource đã fail close.

`SQLWarning` là nhánh riêng cho warnings (thông thường không làm `executeQuery` ném exception ngay). Không lẫn warnings với fatal timeout; dùng `getWarnings()` khi thực sự cần.

## 15. Tích hợp cùng connection pool

Mỗi pool có cấu hình riêng. Ví dụ với HikariCP hoặc pool của application server, bạn có thể gặp ba bộ timeout:
1. Pool acquisition timeout — chờ borrowed handle.
2. Driver login/connect/socket timeouts — thiết lập mạng và đăng nhập.
3. JDBC statement query timeout — execute SQL.

Hệ thống có thể đặt pool acquire 2 giây, driver login 5 giây và query timeout 3 giây, nhưng những con số này **không tự tạo một request deadline tuyệt đối 10 giây**. Mỗi bước có thể có retry, queue và cleanup overhead.

### 15.1. Pool metrics cần theo dõi

- Active connections, idle connections.
- Threads đang chờ pool, borrow wait time.
- Connection creation errors/login timeout.
- Query latency histograms (p50/p95/p99).
- Number of `SQLTimeoutException` per phase.
- Connection reset/broken counts.
- SQLState class `08` và rollback errors class `40`.
- Retry rate, rejected retries, deadline exceeded.
- Database server-side wait events/locks/query plans.

Không gán mọi query timeout cho database “chết”. Có thể database khỏe nhưng một query plan quá đắt hoặc app giữ connection lâu gây nghẽn pool.

### 15.2. Close và pool

`try (Connection c = dataSource.getConnection())` có ý nghĩa rất quan trọng:
- Caller sở hữu **borrowed logical handle**.
- `close()` thường trả handle về pool.
- Pool chịu trách nhiệm xác định underlying connection còn khỏe và có nên recycle.
- Không gọi direct physical driver connection.close() ngoài quyền của pool.
- Nếu SQLRecoverableException xảy ra, không retry trên cùng handle đã lỗi; để pool xử lý đóng và tạo/borrow connection mới.

## 16. Test integration trên driver/database thật

Fixture Java ở phần 10 cho biết classifier hoạt động với các exception được tạo có chủ đích. Để khẳng định hành vi JDBC trong production, cần test **đúng database/driver/pool versions**.

| Nhóm test | Cách tạo tình huống | Điều phải kiểm tra |
| --- | --- | --- |
| Acquisition timeout | DB không trả lời/login chậm hoặc pool cạn | Exception class, phase=ACQUIRE, elapsed, cleanup |
| Query timeout | Query có thời gian chạy/lock vượt query timeout | `SQLTimeoutException` hoặc vendor mapping thực tế |
| Query cancel | Query bị cancel theo timeout | Statement/connection có còn usable không |
| Network timeout | Mô phỏng mạng treo/partition bằng test tool | Connection bị close theo driver, không reuse |
| Pool acquire timeout | Không còn idle/available connections | Pool-specific error mapping, wait time |
| Driver login timeout | Cấu hình `DataSource.setLoginTimeout` | Có thực sự được driver/pool hỗ trợ không |
| Timeout zero | `setQueryTimeout(0)` | No query limit từ setting này |
| Timeout negative | `setQueryTimeout(-1)` | Báo SQLException |
| Unsupported setter | Driver không hỗ trợ timeout | Không silently giả định timeout đã được bảo vệ |
| Fetch timeout | Đọc ResultSet chậm | Driver có áp dụng timeout tới `next` không |
| Batch timeout | `executeBatch` chậm | Timeout áp item hay toàn batch theo vendor |
| Lost connection | Kill server/socket | Exception class/SQLState, transaction state |
| Recoverable exception | Mô phỏng transient network/session failure | Close old, acquire new, retry whole txn nếu safe |
| Serialization failure | Hai transactions cạnh tranh | Rollback/retry entire transaction |
| SQL syntax error | Query sai cú pháp | Không auto-retry mù |
| Ambiguous write outcome | Timeout ngay sau write/commit | Idempotency/reconcile, không double write |
| Cleanup exception | Driver close thất bại | Suppressed errors không bị mất |
| Deadline stress | Nhiều concurrent requests | Retry budget không kéo dài quá SLO |
| Driver upgrade | Nâng driver/JDK | Không regress error mappings/timeout support |

**Không sử dụng SQL `SELECT pg_sleep(...)` làm mặc định universal:** đó là PostgreSQL-specific. Oracle, MySQL, SQL Server có cách mô phỏng delays/locks khác, cần tài liệu đúng vendor. Test suite nên tạo tình huống bằng môi trường test, không làm nghẽn production database.

## 17. Các lỗi thường gặp

**Lỗi 1 — Bắt `SQLTimeoutException` rồi kết luận mất kết nối.**  
Sai. Nó có thể là login timeout **hoặc** query timeout; cần phase và network context.

**Lỗi 2 — Bắt `SQLTimeoutException` rồi retry `UPDATE` ngay.**  
Không an toàn nếu outcome chưa biết; dùng idempotency/reconcile và transaction policy.

**Lỗi 3 — Coi `SQLTimeoutException` luôn có SQLState `HYT00` hay `08xxx`.**  
Java SE nói exception không có một standard SQLState riêng; driver có thể cung cấp hoặc không.

**Lỗi 4 — Coi mọi `SQLTransientException` là automatic retry.**  
Transient không bảo đảm replay-safe side effects, transaction liveness hoặc có deadline.

**Lỗi 5 — Retry `SQLRecoverableException` trên cùng Connection.**  
Sai recovery contract. Ít nhất phải close cũ, lấy connection mới; retry **entire transaction** khi an toàn.

**Lỗi 6 — Retry chỉ câu SQL cuối sau `SQLTransactionRollbackException`.**  
Sai nếu cả transaction đã rollback. Retry entire unit of work theo policy.

**Lỗi 7 — Coi `SQLNonTransientConnectionException` là lỗi có thể chữa bằng retry loop.**  
Thông thường cần sửa nguyên nhân endpoint/auth/TLS/config.

**Lỗi 8 — Dựa duy nhất vào `SQLException.getMessage()`.**  
Messages đổi theo driver/version. Dùng type + phase + state + vendor code.

**Lỗi 9 — Không check SQLState null.**  
`getSQLState()` có thể null, `startsWith` trực tiếp gây NPE.

**Lỗi 10 — Dùng `Statement.setQueryTimeout` để giới hạn thời gian lấy connection từ pool.**  
Sai phase. Query timeout áp dụng statement execution, pool có acquire timeout riêng.

**Lỗi 11 — Dùng `DataSource.setLoginTimeout` để giới hạn SQL execution.**  
Sai. Nó giới hạn login/acquisition theo datasource, không thay `setQueryTimeout`.

**Lỗi 12 — Nhầm seconds và milliseconds.**  
`setLoginTimeout`, `setQueryTimeout` dùng giây; `setNetworkTimeout` dùng milliseconds.

**Lỗi 13 — Cho rằng `setQueryTimeout(0)` là hủy query ngay lập tức.**  
Không. `0` nghĩa là không có query timeout giới hạn bởi setting đó.

**Lỗi 14 — Nghĩ `setQueryTimeout` chắc chắn áp dụng cho mọi `ResultSet.next()`.**  
Vendor-specific. Javadoc chỉ quy định tối thiểu cho execute methods.

**Lỗi 15 — Mong batch timeout luôn áp dụng từng statement.**  
JDBC Javadoc nói batch timeout semantics implementation-defined.

**Lỗi 16 — Nghĩ driver đã “at least attempted cancel” nghĩa server chắc chắn rollback.**  
Không. Cần kiểm tra DB transaction/outcome; cancellation có thể trễ hoặc fail.

**Lỗi 17 — Coi network timeout và query timeout là cùng loại.**  
Network timeout có thể đóng connection; query timeout được cancel thành công thì connection có thể vẫn usable.

**Lỗi 18 — Dùng connection cũ sau network timeout.**  
Nếu driver đã mark closed, connection không usable; đóng borrowed handle, acquire mới.

**Lỗi 19 — Không phân biệt pool acquire timeout với driver login timeout.**  
Có thể đều xuất hiện ở `getConnection` nhưng do các cơ chế khác nhau.

**Lỗi 20 — Tăng pool size khi root cause là SQL plan chậm.**  
Không giải quyết query bottleneck, đôi khi tăng tải database.

**Lỗi 21 — Tăng query timeout vô hạn khi đang có lock contention.**  
Có thể làm request queue/pool cạn và kéo dài sự cố. Đo wait events/plan trước.

**Lỗi 22 — Không đóng PreparedStatement/ResultSet/Connection khi timeout.**  
Dùng try-with-resources, đặc biệt với failed execute.

**Lỗi 23 — Đánh mất `getNextException` và suppressed cleanup errors.**  
Có thể che root cause/driver error. Ghi đủ metadata, redact secrets.

**Lỗi 24 — Chỉ unit test fake exception rồi tin production driver có cùng behavior.**  
Mock không thực thi mạng/cancel. Integration-test vendor-specific JDBC/pool/server.

**Lỗi 25 — Log SQL với passwords/PII để phân tích lỗi.**  
Không cần thiết và rủi ro; log query identifiers, phase, safe metadata.

**Lỗi 26 — Infinite retries khi database đã quá tải.**  
Đặt max attempts, backoff, jitter, deadline và circuit breaker.

**Lỗi 27 — Không xác minh outcome của write khi connection đứt ngay sau commit.**  
Có thể đã commit dù client không nhận response. Reconcile/idempotency trước retry.

## 18. Câu hỏi tự kiểm tra

**1. `SQLTimeoutException` kế thừa trực tiếp lớp nào?**  
`SQLTransientException`, lớp này kế thừa `SQLException`.

**2. `SQLTimeoutException` có standard SQLState riêng không?**  
Không. Java SE Javadoc nói exception này không tương ứng với standard SQLState.

**3. Cùng `SQLTimeoutException` xảy ra ở `getConnection` và `executeQuery` có cùng ý nghĩa không?**  
Không. Một là login/acquisition phase, một là statement execution phase.

**4. Phương thức cấu hình query timeout chuẩn JDBC?**  
`Statement.setQueryTimeout(int seconds)`, được thừa kế bởi `PreparedStatement`.

**5. `setQueryTimeout(0)` nghĩa là gì?**  
Không có query timeout limit từ setting này.

**6. JDBC bắt buộc query timeout áp dụng cho methods nào?**  
`execute`, `executeQuery`, `executeUpdate`.

**7. Query timeout có bắt buộc áp dụng mọi ResultSet methods không?**  
Không. Tùy driver vendor implementation.

**8. Query timeout có bảo đảm SQL server đã rollback dữ liệu không?**  
Không. Driver đã cố cancel không đồng nghĩa confirmed rollback hoặc side-effect-free.

**9. `DataSource.setLoginTimeout` dùng đơn vị gì?**  
Giây.

**10. `Connection.setNetworkTimeout` dùng đơn vị gì?**  
Milliseconds và cần một `Executor` hợp lệ.

**11. Network timeout hết trước query timeout có thể xảy ra điều gì?**  
Driver mark connection closed; cả statement và connection unusable theo JDBC contract.

**12. Gặp `SQLRecoverableException` thì cần tối thiểu làm gì?**  
Đóng connection cũ, lấy connection mới; retry entire transaction nếu an toàn.

**13. Gặp `SQLTransactionRollbackException` có nên phát lại chỉ statement cuối không?**  
Không. Cần xét retry toàn transaction/branch.

**14. SQLState bắt đầu `08` thường gợi ý gì?**  
Connection error class, nhưng vẫn phải xét subclass/driver/phase.

**15. Vì sao không thể tự động retry mọi `INSERT` sau timeout?**  
Client không biết chắc server đã commit hay chưa; có nguy cơ duplicate write.

**16. Nếu `getSQLState()` trả null, classifier phải làm gì?**  
Kiểm tra null và dùng exception class, phase, cause và vendor diagnostics.

**17. Nếu database pool cạn connection, tăng query timeout có sửa gốc lỗi không?**  
Không. Phải quan sát pool wait/connection leak, query latency và workload.

**18. Tại sao ví dụ Java thuần 33 PASS không chứng minh driver PostgreSQL/Oracle sẽ phát same subclass?**  
Fixture tạo exceptions bằng mock, không chạy network/database/driver thật.

## 19. Nguồn tài liệu chính thức và khuyến nghị cập nhật

- [Oracle Java SE 26 — `SQLTimeoutException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTimeoutException.html): lớp kế thừa `SQLTransientException`, các nguồn timeout và không có standard SQLState riêng.
- [Oracle Java SE 26 — `Statement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Statement.html): `setQueryTimeout`, `getQueryTimeout`, `cancel`, áp dụng execute methods và vendor-dependent batch/ResultSet.
- [Oracle Java SE 26 — `PreparedStatement`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): executeQuery/executeUpdate, `SQLTimeoutException` khi driver xác định timeout và cố cancel.
- [Oracle Java SE 26 — `DataSource`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): `setLoginTimeout/getLoginTimeout` và connection acquisition.
- [Oracle Java SE 26 — `DriverManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/DriverManager.html): `setLoginTimeout` và timeout trong `getConnection`.
- [Oracle Java SE 26 — `Connection`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): `setNetworkTimeout`, `isValid`, `close`, query/network timeout ordering và transaction semantics.
- [Oracle Java SE 26 — `SQLException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code, next exception, iterator.
- [Oracle Java SE 26 — `SQLTransientConnectionException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransientConnectionException.html): lỗi connection transient.
- [Oracle Java SE 26 — `SQLNonTransientConnectionException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLNonTransientConnectionException.html): lỗi connection không thể chỉ retry mà khỏi cần sửa nguyên nhân.
- [Oracle Java SE 26 — `SQLRecoverableException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLRecoverableException.html): recovery steps và yêu cầu new connection/entire-transaction retry.
- [Oracle Java SE 26 — `SQLTransactionRollbackException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransactionRollbackException.html): lỗi rollback transaction.
- [Oracle Java SE 26 — `SQLSyntaxErrorException`](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLSyntaxErrorException.html): syntax/access rule errors.

**Ghi nhớ:** `SQLTimeoutException` nói rằng **một hạn mức thời gian JDBC đã hết**; nó **không tự cho biết** thời gian hết ở login hay query, connection còn khỏe hay không, hay write đã xảy ra chưa. Phân biệt **phase + exception subclass + SQLState/vendor diagnostics**, rồi chọn đúng cách đóng tài nguyên, recovery và retry dựa trên **transaction outcome, idempotency và deadline**. Với hệ thống thật, kiểm thử đúng JDBC driver, database và connection pool trước khi bật automatic retries.

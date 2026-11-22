# Phân biệt phục hồi kết nối với chạy lại một câu lệnh

## 1. Cốt lõi của bài: reconnect không phải retry SQL

Khi JDBC gặp lỗi mất kết nối, có hai việc rất khác nhau:

- **Phục hồi kết nối (connection recovery)**: đóng/loại bỏ `Connection` hỏng, lấy một `Connection` mới từ `DataSource` hoặc connection pool và thiết lập lại trạng thái session cần thiết.
- **Chạy lại câu lệnh/giao dịch (statement/transaction replay)**: gửi thêm một lần `INSERT`, `UPDATE`, `DELETE`, `SELECT` hoặc một chuỗi câu lệnh trong transaction đã thử gửi trước đó.

**Lấy được connection mới không chứng minh lần thực thi SQL trước đã rollback.** Database có thể đã ghi nhận thay đổi nhưng network làm mất xác nhận. Nếu tự động replay một thao tác tăng số dư, chuyển tiền, ghi đơn hàng hoặc gửi sự kiện, application có thể thực hiện business effect **hai lần**.

~~~text
Application                              DB server
    |                                       |
    |---- INSERT payment ------------------>|
    |                                       | write
    |---- COMMIT -------------------------->| commit completed
    |                                       |
    X---- acknowledgement lost <------------X
    |                                       |
    | JDBC throws SQLException             |
    | (client sees failure)                 |
    |                                       |
    |---- request NEW Connection ---------->|  connection recovered
    |                                       |
    |---- replay INSERT again?             |  MAY DOUBLE WRITE
~~~

Một exception ở client đôi khi chỉ nói rằng **client chưa nhận được kết quả**, không nói server **chưa thực hiện** operation.

**Nguyên tắc an toàn:** reconnect để khôi phục giao tiếp; chỉ replay khi **đã biết transaction bị rollback/chưa bắt đầu**, hoặc đã thiết kế **idempotency và reconciliation** bảo đảm business effect không bị lặp.

### Mục tiêu sau bài học

1. Giải thích `SQLRecoverableException`, `SQLTransientConnectionException`, `SQLTransactionRollbackException`, `SQLTimeoutException` và giới hạn của việc chỉ dựa trên exception class.
2. Phân biệt lỗi **trước khi gửi SQL**, lỗi **trong lúc execute**, và lỗi **trong lúc COMMIT** (outcome có thể không biết).
3. Đóng connection cũ/lấy connection mới mà không tự tái dùng `PreparedStatement`, `ResultSet`, `Savepoint`, transaction hoặc stream đã tiêu thụ.
4. Viết retry có giới hạn cho **connection acquisition trước mọi SQL**.
5. Hiểu idempotency key/UNIQUE constraint, đọc kết quả trên DB authoritative và xử lý key collision/duplicate requests.
6. Test một fixture Java 17+ mô phỏng **COMMIT thực sự áp dụng nhưng ACK bị mất**, sau đó **chỉ phục hồi connection và xác minh**, không replay INSERT.
7. Biết khi nào có thể retry **toàn transaction** sau lỗi rollback được xác nhận, và khi nào phải trả trạng thái UNKNOWN.

## 2. Những hợp đồng JDBC còn áp dụng trong Java hiện đại

Các JDBC exception subclasses `SQLRecoverableException`, `SQLTransientException` và `SQLTransactionRollbackException` được giới thiệu từ **Java 6/JDBC 4.0** và **vẫn còn trong Java SE 26**. Chúng không phải các API lỗi thời cần thay bằng một thư viện khác. Chương trình minh họa dùng **Java 17+** và try-with-resources — bản thân try-with-resources cho `Connection`/`Statement`/`ResultSet` được hỗ trợ từ **Java 7/JDBC 4.1**, không phải tính năng lần đầu ở Java 6.

| API | Ý nghĩa còn dùng |
| --- | --- |
| `javax.sql.DataSource.getConnection()` | Lấy connection từ cấu hình/pool; trong ứng dụng thực được ưu tiên hơn phân tán `DriverManager` |
| `Connection` | Một session với DB; quản lý auto-commit, isolation, transaction boundaries, schema/catalog, resources |
| `PreparedStatement` | Câu SQL có bind parameters, gắn với connection đã tạo |
| `ResultSet` | Cursor/rows cũng gắn với statement/connection; phải đóng |
| `Connection.commit/rollback` | Hoàn tất hoặc hủy giao dịch khi application trực tiếp quản lý |
| `Connection.isValid(timeoutSeconds)` | Kiểm tra kết nối **hiện tại** còn hợp lệ; không nói gì về commit lịch sử |
| `SQLException` | Phân loại lỗi bằng subtype, SQLState, vendor code, cause/chain |
| `SQLRecoverableException` | Operation có thể thành công sau recovery steps và retry **entire transaction/branch**; tối thiểu phải close old/get new connection |

### 2.1. Điểm chính xác về SQLRecoverableException

Oracle Java SE 26 Javadoc cho `SQLRecoverableException` nói: previously failed operation **might be able to succeed** nếu ứng dụng thực hiện recovery steps và retry **entire transaction** (hoặc một transaction branch trong distributed transaction). **At a minimum**, phải **đóng connection hiện tại và lấy một connection mới**.

Điều Javadoc **không nói**:

- Không khẳng định statement trước **chưa chạy**.
- Không khẳng định COMMIT trước **đã rollback**.
- Không cho phép lấy transaction cũ để tiếp tục trên connection mới.
- Không tự cho phép replay **chỉ câu SQL cuối** khi transaction gồm nhiều câu.
- Không chứng minh idempotency hoặc loại bỏ side effects ngoài database.
- Không đảm bảo một driver có thể phục hồi mọi session-local state.

**Phân biệt quan trọng:** `SQLRecoverableException` **trực tiếp kế thừa `SQLException`**, **không** là subtype của `SQLTransientException`. Phục hồi session không đồng nghĩa SQL safe-to-retry.

## 3. Taxonomy: một exception không đủ để quyết định retry

| Loại SQLException | Ý nghĩa chính | Retry đúng bối cảnh |
| --- | --- | --- |
| `SQLRecoverableException` | Có thể phục hồi sau các bước ở application; thường phải thay connection | Đóng connection cũ, lấy mới; replay transaction **chỉ khi chứng minh an toàn** |
| `SQLTransientConnectionException` | Lỗi kết nối tạm thời (subclass `SQLTransientException`, SQLState class `08` hoặc vendor-specific) | Retry **getConnection trước khi gửi SQL** có thể an toàn với budget |
| `SQLNonTransientConnectionException` | Connection problem không tạm thời (subclass `SQLNonTransientException`) | Sửa auth/config/server trước, không hammer DB |
| `SQLTransactionRollbackException` | DB báo transaction rollback (subclass `SQLTransientException`, SQLState class `40` hoặc vendor-specific) | Nếu rollback được xác nhận, retry **toàn transaction** với điều kiện nghiệp vụ |
| `SQLTimeoutException` | Operation/login/query timeout (subclass `SQLTransientException`) | **Không** tự suy operation chưa chạy; kiểm tra outcome |
| `SQLIntegrityConstraintViolationException` | Primary/unique/foreign-key constraint violation | Không blanket-retry. Nếu cùng idempotency key, kiểm tra payload/result |
| `SQLFeatureNotSupportedException` | Driver thiếu optional feature/overload/mode | Retry không làm API được triển khai |
| `SQLException` chung | Vendor có thể không trả subclass mong đợi | Xem SQLState, vendor code, phase of execution, operation |

**Không** suy mọi lỗi `SQLTransientException` đều cho phép replay write. `SQLTimeoutException` thuộc transient về khả năng operation thử lại có thể thành công, nhưng một lần timeout có thể xảy ra **sau khi server đã thực thi**.

### 3.1. Phân biệt SQLState và Java class

- Class SQLState `08` thường liên quan connection error.
- Class `40` thường liên quan transaction rollback.
- SQLState từ `getSQLState()` có thể **null**; driver có thể dùng vendor-specific codes.
- `SQLRecoverableException` có thể mang class `08` nhưng không bắt buộc mọi instance có SQLState như vậy.
- `SQLTimeoutException` không có một SQLState chuẩn cố định duy nhất theo Javadoc.

Vì thế `e.getSQLState().startsWith("08")` có thể ném NPE khi state null, và ngay cả nếu true cũng **không** chứng minh câu `INSERT` trước chưa commit.

### 3.2. Một classifier tối thiểu chỉ dùng để chẩn đoán

~~~java
static String describe(SQLException e) {
    String state = e.getSQLState();
    String stateClass = (state != null && state.length() >= 2)
            ? state.substring(0, 2) : "UNKNOWN";
    return e.getClass().getSimpleName() + ":SQLStateClass=" + stateClass;
}
~~~

Đây chỉ là **đoạn method** có `import java.sql.SQLException`; nó mô tả lỗi cho log đã lọc, **không** quyết định tự động replay dựa trên string được trả về.

## 4. Lỗi ở giai đoạn nào là điểm khác biệt lớn nhất?

| Giai đoạn | Điều biết chắc | Quyết định thực tế |
| --- | --- | --- |
| **A — getConnection thất bại trước SQL** | Request này chưa gửi statement từ connection được yêu cầu | Có thể retry acquisition bounded |
| **B — connection hỏng nhưng chưa execute** | Chưa gửi statement có side effect (theo luồng được kiểm soát) | Replace connection, bắt đầu lại khi hợp lệ |
| **C — execute đã gửi, chưa nhận response** | **Không chắc** DB đã làm gì | Không replay write mù quáng |
| **D — UPDATE báo thành công, transaction chưa commit** | Client đã có result của statement, nhưng transaction chưa hoàn tất | Xác định rollback/transaction manager, không chỉ tiếp tục trên connection mới |
| **E — COMMIT đã gửi, ACK bị mất** | **UNKNOWN**: có thể commit thành công hoặc không | Reconcile trên DB có thẩm quyền; đừng giả định rollback |
| **F — DB xác nhận transaction rollback** | Transaction không commit theo contract/vendor | Có thể retry **toàn transaction** nếu safe |
| **G — DB xác nhận COMMIT success** | Work đã hoàn tất | Không replay work; cùng business request dùng kết quả lưu sẵn |
| **H — SELECT thuần thất bại** | Thường không có data mutation | Retry query có thể hợp lý nếu consistency/side effects được xem xét |

### 4.1. Lỗi ở COMMIT: “outcome unknown” không đồng nghĩa failed write

~~~text
BEGIN
  INSERT payment_records (request_id, amount)
  UPDATE accounts SET ...
  INSERT outbox ...
COMMIT  -------------> DB applies COMMIT
                       X ACK lost
Java receives SQLException
                       |
                  UNKNOWN
                       |
              New Connection
                       |
              Query requestId
                 /           \
          FOUND/MATCH        NOT FOUND/UNCERTAIN
             |                    |
          Report done      Reconcile per DB consistency,
                           unique constraint and policy
~~~

Với database có replica, đọc ngay trên **read replica đang lag** có thể trả NOT FOUND dù primary đã commit. Cần kiểm tra **nguồn authoritative với mức nhất quán phù hợp**, và không diễn giải “chưa thấy row” là chứng cứ tuyệt đối chưa commit khi vẫn có khả năng failover/lag/race.

### 4.2. Auto-commit cũng có uncertainty

JDBC `Connection` mặc định ở auto-commit mode, trừ khi pool/framework thay đổi. Nếu:

~~~java
int updated = ps.executeUpdate();
~~~

ném exception do mất response sau khi DB đã thực thi, lệnh có thể **đã commit tự động** dù application chưa gọi `connection.commit()`. Vì vậy **“không thấy commit trong Java code” không đủ chứng minh rollback**.

### 4.3. setAutoCommit(true) không phải nút reset vô hại

Trong JDBC, việc đổi `setAutoCommit` từ false sang true trong lúc transaction còn hoạt động có thể **commit transaction**. Nếu code tự cleanup bằng `connection.setAutoCommit(true)` trong `finally` mà chưa xử lý transaction, có thể vô tình commit.

Với pooled connection, nên để transaction manager/pool reset theo policy được kiểm thử; không tự bật/tắt auto-commit bất cẩn sau commit failure.

## 5. Connection mới khác session cũ

Một `Connection` đại diện session. Khi đóng connection cũ và lấy mới:

- `PreparedStatement` và `ResultSet` cũ không thể chuyển sang kết nối mới.
- `Savepoint`, active transaction, locks và open cursors không chuyển sang session mới.
- Auto-commit, isolation, read-only, schema, catalog có thể phải thiết lập lại.
- Tenant-specific variables, database roles, time zone, temporary tables và vendor session settings có thể mất.
- Các stream parameters có thể đã tiêu thụ đến EOF và không thể dùng lại.
- Driver/pool có thể làm một phần session initialization nhưng không có cam kết universal cho custom session state.
- Nếu dùng XA/distributed transaction, coordinator/framework chịu trách nhiệm recovery branch, không tự tạo một transaction khác rồi giả vờ tiếp tục branch cũ.

### 5.1. Đóng connection lỗi và tạo resources mới

~~~text
FAILED CONNECTION
  - PreparedStatement  (invalid)
  - ResultSet          (invalid)
  - Savepoint          (invalid)
  - Transaction state  (not portable)
       |
       X close/discard
       |
NEW CONNECTION
  - NEW PreparedStatement
  - NEW ResultSet
  - NEW transaction if replay policy allows
~~~

Không giữ `PreparedStatement` trong static field dùng lại qua các connection failures. Không share `Connection` giữa concurrent requests nếu driver/pool không cho phép.

### 5.2. isValid không xác nhận commit status

`Connection.isValid(int timeout)` từ JDBC 4.0 kiểm tra connection đang mở có hợp lệ. Nó **không** biết transaction trên connection cũ đã commit hay rollback, không khôi phục SQL session state, không xác minh các side effects và không đảm bảo query kế tiếp không thất bại.

Một connection mới `isValid(1)==true` chỉ nên được hiểu là “đường kết nối đang hợp lệ theo driver”, **không** phải “giao dịch trước chưa chạy”.

## 6. Java 17+ runnable: phục hồi mà không replay INSERT

Ví dụ độc lập `RecoveryVsReplayDemo.java` tạo `FakeDataSource` và Java dynamic proxies mô phỏng `Connection`/`PreparedStatement`/`ResultSet`.

Các tình huống được test:

1. Lần đầu `DataSource.getConnection()` thất bại **trước bất kỳ SQL** bằng `SQLTransientConnectionException`; lần hai lấy connection thành công.
2. Một INSERT được bind, `commit()` trong fake **áp dụng bản ghi** rồi cố tình ném `SQLRecoverableException` để giả lập **ACK bị mất**.
3. Application **đóng connection cũ** bằng try-with-resources.
4. Connection **mới** thực hiện SELECT theo `request_id` và xác minh row đã có.
5. **Không replay INSERT**, số lần ghi mock đúng 1.
6. Kiểm tra exception hierarchy `SQLRecoverableException` khác `SQLTransientException`.

**Lưu ý quan trọng:** FakeDb dùng `HashMap`, không phải database, và proxy không thực thi SQL thật. Đây là **contract/decision test** để dạy flow an toàn, không phải JDBC driver mẫu hoặc bằng chứng khả năng của PostgreSQL/MySQL/Oracle/SQL Server.

### 6.1. File RecoveryVsReplayDemo.java — mã hoàn chỉnh

~~~java
import java.io.PrintWriter;
import java.lang.reflect.*;
import java.sql.*;
import java.util.*;
import java.util.logging.Logger;
import javax.sql.DataSource;

public final class RecoveryVsReplayDemo {
    private static void check(boolean value, String reason) {
        if (!value) throw new AssertionError(reason);
    }

    static final class FakeDb {
        final Map<String, Long> committed = new HashMap<>();
        int physicalWrites;
    }

    static final class FakeDataSource implements DataSource {
        final FakeDb db = new FakeDb();
        boolean failFirstAcquire = true;
        boolean loseFirstCommitAcknowledgment = true;
        int acquisitionFailures;
        int opened;
        int closed;

        @Override public Connection getConnection() throws SQLException {
            if (failFirstAcquire) {
                failFirstAcquire = false;
                acquisitionFailures++;
                throw new SQLTransientConnectionException(
                        "Simulated pool checkout failure", "08001");
            }
            opened++;
            return new FakeSession(this).proxy();
        }

        @Override public Connection getConnection(String user, String password)
                throws SQLException {
            return getConnection();
        }
        @Override public PrintWriter getLogWriter() { return null; }
        @Override public void setLogWriter(PrintWriter out) {}
        @Override public void setLoginTimeout(int seconds) {}
        @Override public int getLoginTimeout() { return 0; }
        @Override public Logger getParentLogger() { return Logger.getLogger("demo"); }
        @Override public <T> T unwrap(Class<T> iface) throws SQLException {
            if (iface.isInstance(this)) return iface.cast(this);
            throw new SQLException("Not a wrapper");
        }
        @Override public boolean isWrapperFor(Class<?> iface) {
            return iface.isInstance(this);
        }
    }

    static final class FakeSession implements InvocationHandler {
        final FakeDataSource source;
        boolean closed;
        boolean autoCommit = true;
        String pendingKey;
        long pendingAmount;

        FakeSession(FakeDataSource source) { this.source = source; }

        Connection proxy() {
            return (Connection) Proxy.newProxyInstance(
                    Connection.class.getClassLoader(),
                    new Class<?>[]{Connection.class}, this);
        }

        private PreparedStatement statement(String sql) {
            InvocationHandler h = new InvocationHandler() {
                String requestId;
                long amount;
                boolean statementClosed;

                @Override public Object invoke(Object proxy, Method m, Object[] args)
                        throws Throwable {
                    if (statementClosed && !m.getName().equals("isClosed"))
                        throw new SQLException("Statement closed", "07000");
                    switch (m.getName()) {
                        case "setString":
                            check(((Integer) args[0]) == 1, "request id index");
                            requestId = (String) args[1];
                            return null;
                        case "setLong":
                            check(((Integer) args[0]) == 2, "amount index");
                            amount = (Long) args[1];
                            return null;
                        case "executeUpdate":
                            check(sql.startsWith("INSERT INTO payment_records"),
                                    "unknown INSERT");
                            check(!autoCommit, "transaction required");
                            check(requestId != null && amount > 0, "invalid payment");
                            pendingKey = requestId;
                            pendingAmount = amount;
                            return 1;
                        case "executeQuery":
                            check(sql.startsWith("SELECT amount_cents FROM payment_records"),
                                    "unknown SELECT");
                            Long value = source.db.committed.get(requestId);
                            return resultSet(value);
                        case "close": statementClosed = true; return null;
                        case "isClosed": return statementClosed;
                        default: throw new SQLFeatureNotSupportedException(
                                "Fixture statement: " + m.getName());
                    }
                }
            };
            return (PreparedStatement) Proxy.newProxyInstance(
                    PreparedStatement.class.getClassLoader(),
                    new Class<?>[]{PreparedStatement.class}, h);
        }

        private static ResultSet resultSet(Long value) {
            InvocationHandler h = new InvocationHandler() {
                boolean beforeFirst = true;
                boolean rowActive;
                boolean closedResult;
                @Override public Object invoke(Object proxy, Method m, Object[] args)
                        throws Throwable {
                    switch (m.getName()) {
                        case "next":
                            if (closedResult) throw new SQLException("ResultSet closed");
                            if (!beforeFirst) return false;
                            beforeFirst = false;
                            rowActive = value != null;
                            return rowActive;
                        case "getLong":
                            if (!rowActive) throw new SQLException("Cursor not on row");
                            return value.longValue();
                        case "close": closedResult = true; return null;
                        case "isClosed": return closedResult;
                        default: throw new SQLFeatureNotSupportedException(
                                "Fixture result: " + m.getName());
                    }
                }
            };
            return (ResultSet) Proxy.newProxyInstance(
                    ResultSet.class.getClassLoader(),
                    new Class<?>[]{ResultSet.class}, h);
        }

        @Override public Object invoke(Object proxy, Method m, Object[] args)
                throws Throwable {
            switch (m.getName()) {
                case "setAutoCommit": autoCommit = (Boolean) args[0]; return null;
                case "getAutoCommit": return autoCommit;
                case "prepareStatement":
                    if (closed) throw new SQLException("Connection closed", "08003");
                    return statement((String) args[0]);
                case "commit":
                    if (closed) throw new SQLException("Connection closed", "08003");
                    if (autoCommit) throw new SQLException("Auto-commit enabled");
                    if (pendingKey != null) {
                        if (!source.db.committed.containsKey(pendingKey)) {
                            source.db.committed.put(pendingKey, pendingAmount);
                            source.db.physicalWrites++;
                        }
                        pendingKey = null;
                    }
                    if (source.loseFirstCommitAcknowledgment) {
                        source.loseFirstCommitAcknowledgment = false;
                        throw new SQLRecoverableException(
                                "Commit applied, acknowledgment lost (fixture)", "08006");
                    }
                    return null;
                case "rollback": pendingKey = null; return null;
                case "close":
                    if (!closed) {
                        closed = true;
                        source.closed++;
                    }
                    return null;
                case "isClosed": return closed;
                case "isValid": return !closed;
                default: throw new SQLFeatureNotSupportedException(
                        "Fixture connection: " + m.getName());
            }
        }
    }

    static Connection acquireBeforeSql(DataSource source, int maxAttempts)
            throws SQLException {
        check(maxAttempts > 0, "maxAttempts must be positive");
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                return source.getConnection();
            } catch (SQLTransientConnectionException e) {
                if (attempt == maxAttempts) throw e;
                // Test only. Real systems need bounded delay/jitter/deadline.
            }
        }
        throw new AssertionError("unreachable");
    }

    public static void main(String[] args) throws Exception {
        FakeDataSource source = new FakeDataSource();

        Connection original = acquireBeforeSql(source, 2);
        check(source.acquisitionFailures == 1, "expected one checkout failure");
        System.out.println("acquisition-retried-before-sql=true");

        boolean outcomeUnknown = false;
        try (original) {
            original.setAutoCommit(false);
            try (PreparedStatement insert = original.prepareStatement(
                    "INSERT INTO payment_records(request_id, amount_cents) VALUES (?, ?)")) {
                insert.setString(1, "request-42");
                insert.setLong(2, 500L);
                check(insert.executeUpdate() == 1, "insert");
            }
            try {
                original.commit();
                throw new AssertionError("expected lost commit acknowledgment");
            } catch (SQLRecoverableException e) {
                check("08006".equals(e.getSQLState()), "SQLState");
                outcomeUnknown = true;
                System.out.println("commit-outcome=UNKNOWN_TO_CLIENT");
            }
        }
        check(original.isClosed(), "failed connection should be closed");
        check(outcomeUnknown, "commit result should be unknown");
        check(source.db.physicalWrites == 1, "first commit should apply once");

        try (Connection recovered = source.getConnection();
             PreparedStatement query = recovered.prepareStatement(
                     "SELECT amount_cents FROM payment_records WHERE request_id = ?")) {
            query.setString(1, "request-42");
            try (ResultSet rows = query.executeQuery()) {
                check(rows.next(), "durable record not found");
                check(rows.getLong(1) == 500L, "wrong amount");
                check(!rows.next(), "duplicate idempotency key");
            }
            check(recovered.isValid(1), "new connection invalid");
            System.out.println("new-connection-valid=true");
        }
        System.out.println("replayed-insert=false");
        System.out.println("verified-amount-cents=" +
                source.db.committed.get("request-42"));
        System.out.println("physical-inserts=" + source.db.physicalWrites);
        check(source.closed == 2 && source.opened == 2,
                "connections should be closed and reacquired");

        SQLException recoverable = new SQLRecoverableException("recover", "08006");
        SQLException rollback = new SQLTransactionRollbackException("deadlock", "40001");
        System.out.println("recoverable-is-transient=" +
                (recoverable instanceof SQLTransientException));
        System.out.println("rollback-is-transient=" +
                (rollback instanceof SQLTransientException));
        System.out.println("tests=PASS");
    }
}
~~~

### 6.2. Lệnh biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 17 RecoveryVsReplayDemo.java
java RecoveryVsReplayDemo
~~~

Kết quả **stdout chính xác** đã được kiểm thử trên **OpenJDK 24** với target Java 17:

~~~text
acquisition-retried-before-sql=true
commit-outcome=UNKNOWN_TO_CLIENT
new-connection-valid=true
replayed-insert=false
verified-amount-cents=500
physical-inserts=1
recoverable-is-transient=false
rollback-is-transient=true
tests=PASS
~~~

### 6.3. Những kết quả này thực sự nói gì?

- `acquisition-retried-before-sql=true`: retry `getConnection` chỉ diễn ra **trước khi gửi bất kỳ SQL nào**.
- `commit-outcome=UNKNOWN_TO_CLIENT`: fake DB đã áp dụng commit nhưng client không nhận acknowledgement; đúng tình huống mà một `SQLRecoverableException` không thể chứng minh rollback.
- `new-connection-valid=true`: connection cũ đã đóng, connection mới được lấy và kiểm tra `isValid(1)`.
- `replayed-insert=false`: chương trình **không gửi lại INSERT** sau lỗi commit.
- `verified-amount-cents=500` và `physical-inserts=1`: truy vấn trên new connection tìm thấy mock row theo request ID, mô phỏng reconciliation.
- `recoverable-is-transient=false`: đúng hierarchy; recoverable trực tiếp kế thừa `SQLException`.
- `rollback-is-transient=true`: `SQLTransactionRollbackException` kế thừa `SQLTransientException`.
- `tests=PASS`: asserts và connection resource closes đạt yêu cầu.

**Không được suy rộng:** fake `HashMap` không có durable transactions, WAL, network, locking, failover, TLS, snapshot isolation, constraints hoặc real database driver. Kết quả chỉ test **cách application ra quyết định**. Để chứng minh không ghi trùng trong production cần database thật và unique constraint/transaction + chaos testing.

### 6.4. Hạn chế của retry acquisition demo

`acquireBeforeSql` cố tình **không đợi** giữa các lần thử để lab chạy nhanh, nhưng production cần **bounded retries, exponential backoff, jitter, total deadline, cancellation, pool acquisition timeout, circuit breaker**. Không copy nguyên vòng lặp retry tức thì cho dịch vụ xử lý nhiều requests. Điều kiện làm ví dụ retry tương đối an toàn là **không có SQL nào được gửi trước khi acquisition thất bại**.

## 7. Idempotency key: một điều kiện rất quan trọng để replay write an toàn

Khi một business request có thể được gửi lại bởi HTTP client, queue consumer hoặc job scheduler, application phải dùng **cùng request ID** cho cùng logical operation. Database nên enforce uniqueness của requestId trong **cùng transaction** với business changes.

Schema ý tưởng:

~~~sql
-- DDL minh họa, điều chỉnh theo DBMS cụ thể.
CREATE TABLE payment_records (
    request_id VARCHAR(128) NOT NULL UNIQUE,
    amount_cents BIGINT NOT NULL
);
~~~

Đây là schema tối giản để giải thích; production cần tenant/account/currency/status/payloadHash, response record và có thể outbox. **UNIQUE constraint phải thật sự được DB enforce**; một Map trong JVM hoặc thao tác SELECT xem đã có rồi mới INSERT **không chống được race** giữa hai servers.

### 7.1. Ví dụ compile-only với DataSource thật

File `PaymentRepositoryExample.java`:

~~~java
import java.sql.*;
import java.util.Objects;
import java.util.OptionalLong;
import javax.sql.DataSource;

public final class PaymentRepositoryExample {
    private final DataSource source;

    public PaymentRepositoryExample(DataSource source) {
        this.source = Objects.requireNonNull(source);
    }

    public static final class CommitOutcomeUnknown extends Exception {
        public CommitOutcomeUnknown(String message, SQLException cause) {
            super(message, cause);
        }
    }

    // payment_records.request_id must have a DB-enforced UNIQUE constraint.
    // All business changes in the operation must share this same transaction.
    public void insertOnce(String requestId, long cents)
            throws SQLException, CommitOutcomeUnknown {
        if (requestId == null || requestId.isBlank() || cents <= 0) {
            throw new IllegalArgumentException("Invalid payment parameters");
        }
        try (Connection connection = source.getConnection()) {
            connection.setAutoCommit(false);
            try (PreparedStatement insert = connection.prepareStatement(
                    "INSERT INTO payment_records(request_id, amount_cents) VALUES (?, ?)")) {
                insert.setString(1, requestId);
                insert.setLong(2, cents);
                insert.executeUpdate();
            } catch (SQLException beforeCommit) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    beforeCommit.addSuppressed(rollbackFailure);
                }
                throw beforeCommit;
            }

            try {
                connection.commit();
            } catch (SQLException duringCommit) {
                throw new CommitOutcomeUnknown(
                        "Commit status unknown: reconcile requestId on authoritative DB",
                        duringCommit);
            }
        }
    }

    // Query an authoritative, appropriately consistent database, not a lagging replica.
    public OptionalLong findCommittedAmount(String requestId) throws SQLException {
        try (Connection connection = source.getConnection();
             PreparedStatement query = connection.prepareStatement(
                     "SELECT amount_cents FROM payment_records WHERE request_id = ?")) {
            query.setString(1, requestId);
            try (ResultSet rows = query.executeQuery()) {
                if (!rows.next()) return OptionalLong.empty();
                return OptionalLong.of(rows.getLong("amount_cents"));
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 --release 17 PaymentRepositoryExample.java
~~~

Đây là **code đã biên dịch thành công** trên OpenJDK 24 với `--release 17`, nhưng **không có `main` và chưa chạy với DB thật**. Khi tích hợp phải có `DataSource`, bảng/schema thật và tests theo DB vendor. Không khẳng định đoạn code được thử commit/rollback trên production DB.

### 7.2. Vì sao gọi CommitOutcomeUnknown thay vì retry?

Trong `insertOnce`, khi `commit` ném `SQLException`, application **không biết** transaction đã commit hay chưa. Code nâng lỗi thành `CommitOutcomeUnknown` để caller thực hiện **reconciliation**, thay vì catch và gửi lại INSERT ngay lập tức.

`findCommittedAmount` mở **connection mới** và query theo **requestId ổn định**. Nếu tìm thấy row với cùng amount (và trong app thực cả currency, target, payloadHash), có bằng chứng phù hợp rằng operation đã được DB ghi. Nếu query không thấy row, **chưa được tự động kết luận rollback** khi có replica lag, failover, network delay, unfinished transaction hoặc policy consistency chưa xác định.

### 7.3. Trường hợp SQL lỗi trước commit

Trong ví dụ, catch trước `commit` cố gọi `rollback()` và thêm lỗi rollback dưới dạng suppressed nếu có. Nhưng **gọi rollback không đồng nghĩa biết chắc rollback thành công** nếu connection đã mất hoặc rollback cũng ném lỗi. Trên hệ thống nhạy cảm, một lỗi I/O khi đang thực thi statement vẫn có thể cần trạng thái UNKNOWN/reconciliation; không lấy việc “đã vào catch trước commit” làm bằng chứng mọi side effects đã hủy, đặc biệt với auto-commit, implicit commits của DDL và external side effects.

### 7.4. Cùng key nhưng payload khác phải là conflict

Nếu requestId `req-42` đã dùng cho một thanh toán 500, request lần sau dùng cùng ID nhưng amount 900 **không** được tự động trả success. Hãy lưu payload hash/identity và so sánh. Một `SQLIntegrityConstraintViolationException` khi INSERT cùng key có thể do genuine duplicate hoặc key collision; **không bắt mọi unique violation rồi im lặng coi thành công**.

### 7.5. Idempotency key không bảo vệ mọi side effect

Một UNIQUE row chỉ ngăn duplicate row đó. Nếu bạn gọi email service, payment gateway hoặc message broker **ngoài DB transaction**, replay có thể gửi trùng dù INSERT bị unique conflict.

Với events, pattern **transactional outbox** lưu business update + outbox record trong **cùng DB transaction**; worker gửi message có ID ổn định, consumer dedup/idempotent. Dù vậy, vẫn phải thiết kế theo hệ thống downstream; **JDBC không cung cấp exactly-once end-to-end** tự động.

## 8. Retry sau deadlock/rollback: thường phải chạy lại toàn transaction

`SQLTransactionRollbackException` có thể xuất hiện khi DB chấm dứt transaction, ví dụ deadlock victim/serialization failure theo vendor. Nếu **DB xác nhận rollback toàn transaction**, một ứng dụng có thể retry transaction **từ đầu** với điều kiện:

- Cùng business requestId và payload, có cơ chế idempotency.
- Không có side effects bên ngoài DB đã xảy ra trước rollback, hoặc chúng đã được bảo vệ bởi outbox/dedup.
- Mọi statement, constraints, locks và invariant được thực thi trong **transaction mới**.
- Lấy lại dữ liệu đầu vào/queries trong isolation đúng; không dùng state/cursor cũ như thể snapshot không đổi.
- Giới hạn số lần và thời gian với backoff/jitter.
- Nếu concurrency/DB overload vẫn quá cao thì fail rõ sau budget, không retry vô hạn.

**Không chỉ retry statement cuối** của một transaction có ba bước, bởi các bước đầu có thể đã bị rollback và không tồn tại nữa.

### 8.1. Rollback đã được DB xác nhận khác “rollback() được gọi”

Nếu connection đã gãy trước COMMIT, thử `connection.rollback()` có thể ném lỗi. Lời gọi rollback không thành công **không** xác nhận DB đã rollback. Tương tự, nếu COMMIT đang xảy ra, transaction outcome có thể vẫn UNKNOWN.

Trong JTA/XA, transaction coordinator chịu trách nhiệm recovery transaction branch. Không tự viết vòng retry câu SQL trên một connection mới để bypass coordinator.

## 9. SELECT có thể retry nhưng còn phụ thuộc consistency

SELECT thuần thường ít rủi ro hơn INSERT/UPDATE, nhưng cũng không thể gọi an toàn tuyệt đối:

- `SELECT ... FOR UPDATE` đặt lock và thường nằm trong transaction, không phải chỉ đọc vô hại.
- Stored functions/procedures trong SELECT có thể có side effects.
- Data có thể thay đổi giữa hai lần SELECT; một query mới không nhất thiết trả cùng snapshot.
- Paging `OFFSET/LIMIT` và streaming ResultSet có thể mất thứ tự/duplicate/skip khi chạy lại giữa chừng.
- Query báo cáo nhiều bảng cần transaction/snapshot nhất quán, không ghép kết quả từ hai connections khác nhau.
- Session tenant/schema/roles đã cài trên connection cũ phải được thiết lập trên connection mới.
- Một ResultSet đã đọc nửa chừng không thể khôi phục vị trí chỉ bằng cách lấy new Connection.

Vì vậy khi replay read-only query, hãy xác định **consistency contract** và có retry budget. Với một danh sách sản phẩm trong UI có thể chấp nhận dữ liệu mới hơn; với báo cáo tài chính hoặc ledger snapshot, yêu cầu nghiêm ngặt hơn.

## 10. Timeout và exception handling không phải nút retry tự động

### 10.1. SQLTimeoutException

`SQLTimeoutException` được dùng khi một timeout do JDBC API quy định hết hạn. Nó là subclass của `SQLTransientException`, nhưng **không bảo đảm** lệnh ở server chưa thực thi hoặc chưa commit. Statement cancellation và transaction state phụ thuộc driver/DBMS.

Đừng viết “catch `SQLTimeoutException` → executeUpdate lại”. Trước hết cần biết statement đã gửi chưa, auto-commit mode, kết quả nghiệp vụ đã xuất hiện chưa, và có idempotency key không.

### 10.2. Lỗi kết nối non-transient

Nếu `SQLNonTransientConnectionException` do credentials sai, DNS config sai, driver version không tương thích, thiếu quyền hoặc JDBC URL không hợp lệ, retry vô hạn không giải quyết. Phải sửa configuration, secrets, server availability, driver artifact hoặc quyền.

### 10.3. SQLRecoverableException không tự reset transaction state

Tối thiểu theo Oracle Javadoc là close old/get new. Tại đây application phải thiết lập lại transaction/session settings **một cách có kiểm soát** trước khi thực hiện công việc khác. Nếu dùng framework/pool, phân biệt trách nhiệm của framework với repository code; tránh hai tầng retry nhân nhau và gây retry storm.

### 10.4. Không dùng Class.forName/autoreconnect như giải pháp retry business

Từ JDBC 4.0, driver có thể tự được phát hiện qua Service Provider; gọi `Class.forName` thủ công **không giải quyết ambiguous commit**. Một driver có tùy chọn tự reconnect cũng **không thể** tự bảo đảm toàn bộ transaction business logic/idempotency và session state. Đừng tin rằng reconnect trong driver đồng nghĩa replay an toàn.

## 11. Retry policy thực tế: giới hạn, backoff, deadline và circuit breaker

Với **acquisition trước SQL**, bounded retry có thể dùng:

~~~java
static Connection acquireBeforeSql(DataSource ds, int attempts)
        throws SQLException {
    for (int i = 1; i <= attempts; i++) {
        try {
            return ds.getConnection();
        } catch (SQLTransientConnectionException e) {
            if (i == attempts) throw e;
            // Production: exponential backoff + jitter + deadline.
        }
    }
    throw new AssertionError("unreachable");
}
~~~

Đây là **đoạn method** cần import `java.sql.*` và `javax.sql.DataSource`, có chức năng tương đương fixture ở mục 6. **Chỉ retry việc lấy connection trước SQL**. Trong production, thay comment bằng logic retry policy của ứng dụng/framework được kiểm thử; không nên tự tạo nhiều layers retry độc lập.

### 11.1. Các ràng buộc production

- Giới hạn số attempts và tổng deadline, không tăng độ trễ không giới hạn.
- Exponential backoff với jitter để nhiều services không gây thác retry khi DB đang quá tải.
- Tôn trọng interruption/cancellation, không nuốt `InterruptedException` nếu dùng `Thread.sleep`.
- Pool acquisition timeout và circuit breaker để hạ tải khi DB outage.
- Retry only những lỗi có căn cứ; không auth/syntax/feature unsupported.
- Không lặp lại operation đã có side effect nếu chưa xác nhận replay policy.
- Monitor failure rate, pool connections borrowed, waiting time, timeout, connection invalidations.
- Bảo vệ dữ liệu nhạy cảm trong logs; không ghi raw JDBC URL có passwords/SQL parameters.

### 11.2. Một chương trình cần phân biệt bốn scopes

~~~text
1. Acquisition retry:  chưa có SQL, chỉ getConnection
2. Statement retry:    lặp một SQL (cần biết side effects!)
3. Transaction retry:  lặp TOÀN bộ transaction (cần rollback certainty/idempotency)
4. Request retry:      client gửi lại cả business operation (cần requestId/dedup)
~~~

Một hệ thống có HTTP client retry, message queue redelivery, ORM retry và pool retry có thể gây **rất nhiều executions** cho một business request nếu không kiểm soát. Đặt ownership rõ ràng và bảo vệ business effect bằng DB constraints/idempotency chứ không dựa vào việc một layer “chắc không retry”.

## 12. Quan sát và debug: log đúng giai đoạn, không lộ bí mật

Trong `SQLException`, các dữ liệu thường hữu ích:

- **Operation name:** `getConnection`, `executeUpdate`, `commit`, `rollback`, `executeQuery`.
- **Stage:** BEFORE_SQL, SQL_SENT, EXECUTE_RESPONSE_RECEIVED, COMMIT_SENT, ACK_RECEIVED.
- Exception subtype; `getSQLState()` (có thể null), `getErrorCode()`.
- `getCause()`, `getNextException()`, suppressed rollback/close failures.
- Driver/version, DB product/version, transaction manager/pool version.
- Auto-commit, isolation/transaction configuration.
- Request ID/idempotency key, payload hash **không phải raw payment data**.
- Retry attempt, total elapsed, deadline, backoff.
- Reconciliation state: CONFIRMED_COMMITTED, CONFIRMED_NOT_APPLIED hoặc UNKNOWN.

Đừng log credentials, full URL có password, tokens, PII, dữ liệu thanh toán hay SQL với literal secrets. Không gửi raw SQLState/vendor exception lên UI như thông điệp cho end user.

### 12.1. Lưu cả lỗi rollback/close mà không mất lỗi chính

Khi transaction thất bại, rollback cũng có thể ném `SQLException`. Nếu cần, đưa rollback error vào `original.addSuppressed(rollbackFailure)`, rồi throw original; tránh để rollback/close error che mất sự kiện COMMIT ACK lost. Try-with-resources quản lý suppressed exceptions khi close phát sinh lỗi sau body error.

### 12.2. Outcome ba trạng thái

Không ép mọi transaction vào boolean success/fail khi có lỗi network:

~~~text
CONFIRMED_COMMITTED
CONFIRMED_ROLLED_BACK / NOT_APPLIED (có bằng chứng phù hợp)
UNKNOWN / NEEDS_RECONCILIATION
~~~

**UNKNOWN không có nghĩa transaction bị rollback.** Nếu chưa thể xác minh, nên trả trạng thái pending/unknown và cung cấp API tra cứu requestId, không để caller tự tạo request mới mỗi lần timeout.

## 13. Những lỗi phổ biến và cách tránh

| Thói quen sai | Rủi ro | Cách đúng |
| --- | --- | --- |
| Catch `SQLRecoverableException` rồi execute SQL lại | COMMIT trước có thể đã thành công | Replace connection, reconcile outcome |
| Retry mọi `SQLException` | Syntax/auth/constraint lỗi không transient | Phân loại exception + phase + operation |
| Dùng `isValid()` để đo commit status | Chỉ kiểm tra connection hiện tại | Query authoritative business record |
| Retry chỉ câu cuối của multi-statement transaction | Invariant sai nếu toàn transaction bị rollback | Retry whole transaction khi rollback confirmed |
| Retry `commit()` trên session hỏng | Không biết kết quả commit cũ | Close/replace, reconcile |
| Gán `SQLRecoverableException` là SQLTransientException | Hierarchy sai | Đọc Javadoc: trực tiếp từ SQLException |
| Xem SQLState `08` là “SQL chưa chạy” | Lỗi có thể sau server commit | Stage-aware recovery |
| Xem timeout là “server không làm gì” | Server có thể đã thực thi | Idempotency/verify, vendor docs |
| Tạo requestId mới mỗi retry | Unique key không thể dedup | Giữ nguyên key theo logical request |
| Chỉ dùng in-memory Map để dedup | Nhiều JVM/race/restart | DB-enforced UNIQUE + atomic transaction |
| Catch unique violation rồi trả success | Có thể trùng ID nhưng payload khác | Query kết quả/payload hash, conflict nếu khác |
| Đọc replica lag rồi kết luận không có row | False negative | Authoritative appropriately consistent read |
| Gọi external API trước commit rồi retry | External effect không rollback | Transactional outbox/consumer dedup |
| Lấy new connection và dùng PreparedStatement cũ | Resources gắn session cũ | Tạo mới sau khi xác định replay safe |
| Gọi `setAutoCommit(true)` trong finally | Có thể commit uncommitted transaction | Transaction manager hoặc rõ commit/rollback |
| Retry không backoff | Thêm tải lúc DB down | Bounded exponential backoff/jitter |
| Retry SELECT FOR UPDATE như read-only | Locks/side effects | Xử lý theo transaction semantics |
| Giữ stream đã tiêu thụ rồi retry | Payload thiếu/truncated | Reopen source nếu operation được phép replay |
| Log full JDBC URL/PII | Lộ secrets | Structured diagnostics đã lọc |
| Không xử lý outcome UNKNOWN | Dễ duplicate payment | Reconciliation/idempotency/request status |

## 14. Integration test: mock không thay thế DB thật

Test Java ở phần 6 chỉ mô phỏng tình huống. Với driver/database sandbox phải kiểm tra:

| Tình huống | Mục tiêu |
| --- | --- |
| Lỗi `getConnection` trước SQL | Acquisition bounded, không replay statement |
| Pool trả connection stale | Đóng/loại session, thiết lập context mới |
| Connection chết giữa SELECT | Không ghép cursor/snapshot sai |
| Connection chết khi INSERT dưới auto-commit | Không double INSERT |
| Connection chết giữa transaction | Không tiếp tục session cũ |
| Connection mất ACK ở COMMIT | UNKNOWN handling và authoritative reconciliation |
| Deadlock/serialization rollback | Retry whole transaction có giới hạn |
| Hai clients cùng requestId | UNIQUE constraint bảo vệ business effect |
| Cùng key nhưng payload khác | Phát hiện conflict |
| Read replica lag | Không false negative kết luận rollback |
| Timeout/slow statement | Không tự replay write |
| Tenant-specific session state | Khôi phục đúng khi lấy connection mới |
| Outbox/external events | Không double side effects |
| Đổi driver/DB version | Phân loại exception/recovery policy vẫn đúng |
| Retry storm/load test | Backoff, pool size, circuit breaker |
| Cleanup failure | Statement/connection được release, suppressed errors giữ được |
| Security/logging | Không xuất credentials, requestId không tiết lộ thông tin nhạy cảm |

### 14.1. Fault injection vào COMMIT phải đúng failpoint

Một bài test chỉ “kill database bất kỳ lúc nào” không chắc tạo đúng tình huống **COMMIT đã được áp dụng nhưng ACK chưa đến client**. Cần test hạ tầng/network proxy có thể tạo lỗi tại từng thời điểm, sau đó đối chiếu dữ liệu durable/audit. Chỉ thử trong database sandbox, không làm với thanh toán/đơn hàng production.

### 14.2. Assert business outcome, không chỉ assert reconnect

Một test reconnect PASS nhưng ghi hai payment rows là test **thất bại** về nghiệp vụ. Cần kiểm tra số business effects, amount/target/currency, idempotency key, outbox event ID, resource leaks, retry attempts và deadline. Kết quả của mock chỉ minh họa flow, không chứng minh SQL vendor đảm bảo exactly-once.

## 15. Câu hỏi tự đánh giá

**Câu 1.** Reconnect thành công có chứng minh COMMIT trước đã rollback?

**Đáp án:** Không. Nó chỉ khôi phục kết nối; transaction outcome phải được xác minh riêng.

**Câu 2.** `SQLRecoverableException` có kế thừa `SQLTransientException` không?

**Đáp án:** Không; nó kế thừa trực tiếp `SQLException`. Javadoc yêu cầu tối thiểu đóng old Connection/lấy new Connection cho recovery.

**Câu 3.** Tại sao retry `getConnection` trước SQL khác retry `executeUpdate` sau lỗi?

**Đáp án:** Trong giai đoạn acquisition chưa gửi SQL của operation này. Sau execute, DB có thể đã thay đổi dữ liệu/commit trước khi mất response.

**Câu 4.** Timeout có chứng minh statement chưa commit?

**Đáp án:** Không. `SQLTimeoutException` không bảo đảm server chưa thực thi hay rollback; phải xét operation/transaction semantics.

**Câu 5.** Vì sao không retry một câu cuối sau `SQLTransactionRollbackException`?

**Đáp án:** Có thể toàn transaction đã rollback; các statements tiền đề cần thực thi lại trong transaction mới.

**Câu 6.** Tại sao cần UNIQUE request_id?

**Đáp án:** DB enforce uniqueness ở các concurrent requests; không dùng Map/check-then-insert để bảo vệ cross-process.

**Câu 7.** Nếu cùng key có amount khác thì sao?

**Đáp án:** Báo conflict, không tự trả success. Cần kiểm tra request payload hash/identity.

**Câu 8.** Vì sao replica không thấy row chưa chứng minh rollback?

**Đáp án:** Replica có thể lag hoặc có consistency khác; cần query authoritative theo protocol.

**Câu 9.** `Connection.isValid(1)` có biết transaction trên connection cũ không?

**Đáp án:** Không. Chỉ kiểm tra connection hiện tại.

**Câu 10.** SELECT luôn retry an toàn?

**Đáp án:** Không. SELECT FOR UPDATE, stored functions, snapshot/pagination và session state có thể khiến replay khác nghĩa.

**Câu 11.** Khi reconnect có tái dùng PreparedStatement/ResultSet cũ không?

**Đáp án:** Không. Chúng gắn với old connection và phải tạo lại nếu replay được phép.

**Câu 12.** Transactional outbox giúp gì?

**Đáp án:** Ghi event intent trong cùng DB transaction với business update; delivery và consumer dedup giảm external side effects trùng.

**Câu 13.** `PaymentRepositoryExample` có thật sự chạy SQL trên DB trong bài này không?

**Đáp án:** Không. Mã đã compile nhưng cần driver/DataSource/schema thật để chạy, khác mock executable.

**Câu 14.** Nếu `connection.rollback()` bị lỗi vì mất mạng, có chắc DB đã rollback?

**Đáp án:** Không. Cần coi outcome chưa rõ và reconcile tùy loại lỗi/transaction phase.

### Bài tập

1. Chạy `RecoveryVsReplayDemo`, giải thích 9 dòng stdout và tại sao `physical-inserts=1`.
2. Đổi fixture `failFirstAcquire=false`, xác minh không có lần checkout thất bại (viết test riêng).
3. Đổi `loseFirstCommitAcknowledgment=false` để xem đường commit có ACK và sửa assertions tương ứng.
4. Tạo một mock case trong đó commit thất bại **trước** khi áp dụng; cho client trả UNKNOWN và chứng minh phải reconcile thay vì đoán.
5. Thêm classifier phân biệt SQLState class `08`/`40` nhưng không tự replay.
6. Giả lập `SQLTimeoutException` ở `executeUpdate` và viết policy không tự retry payment.
7. Tạo DB sandbox với `payment_records(request_id UNIQUE)`, chạy `PaymentRepositoryExample`, verify cùng key không double write.
8. Cùng key nhưng amount khác phải trả conflict sau khi đọc authoritative result.
9. Viết outbox record trong cùng DB transaction, giả lập queue deliver hai lần và dùng eventId dedup.
10. Mô phỏng replica lag; chứng minh NOT FOUND trên replica chưa đủ là rollback.
11. Test deadlock/serialization rollback ở DB test, retry **full transaction** với budget.
12. Đo reconnect/close counts, pool timeouts và retry jitter khi DB outage ngắn.
13. Test SELECT paging/snapshot bị thay đổi khi query restart và thiết kế consistency policy.
14. Viết endpoint status trả `CONFIRMED_COMMITTED`, `CONFIRMED_ROLLED_BACK` hoặc `UNKNOWN`.

## 16. Tài liệu chính thức và nguồn tham khảo

- [Oracle Java SE 26 — SQLRecoverableException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLRecoverableException.html): ít nhất close old/get new, khả năng retry entire transaction/XA branch sau recovery.
- [Oracle Java SE 26 — SQLTransientConnectionException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransientConnectionException.html): kết nối transient, SQLState class 08.
- [Oracle Java SE 26 — SQLTransientException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransientException.html): transient error classification.
- [Oracle Java SE 26 — SQLNonTransientConnectionException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLNonTransientConnectionException.html): non-transient connection errors.
- [Oracle Java SE 26 — SQLTransactionRollbackException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransactionRollbackException.html): transaction rollback, SQLState class 40.
- [Oracle Java SE 26 — SQLTimeoutException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTimeoutException.html): timeout exception semantics.
- [Oracle Java SE 26 — SQLException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor codes, cause và exception chain.
- [Oracle Java SE 26 — Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): auto-commit, commit/rollback, isValid, session lifecycle.
- [Oracle Java SE 26 — PreparedStatement](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html): bind parameters/statement lifecycle.
- [Oracle Java SE 26 — ResultSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html): cursor and lifecycle.
- [Oracle Java SE 26 — javax.sql.DataSource](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/javax/sql/DataSource.html): lấy connection/pooling.
- [Oracle Java SE 26 — java.sql package summary](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html): JDBC 4.x lịch sử, exception taxonomy hiện hành.
- [Oracle Java SE 17 — SQLRecoverableException](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/SQLRecoverableException.html): xác nhận Java 17 target.
- [Microsoft Learn — Commit failure and idempotency](https://learn.microsoft.com/en-us/ef/core/miscellaneous/connection-resiliency): phân tích rủi ro commit outcome unknown; tài liệu cho nền tảng khác nhưng nguyên lý database transaction không riêng JDBC.

**Ghi nhớ:** `SQLRecoverableException` có thể cần **close connection cũ + mở mới**, nhưng đó chỉ là bước **phục hồi giao tiếp**. Một statement đã gửi hoặc COMMIT đang diễn ra có thể đã làm thay đổi dữ liệu trước khi client thấy lỗi. Không được tự replay write chỉ vì “connection đã hồi phục”; phải dựa vào **rollback được xác nhận** hoặc thiết kế **idempotency key/UNIQUE, transaction, authoritative reconciliation và outbox** được kiểm thử trên DB thật. Nếu chưa xác định được outcome, trả **UNKNOWN**, không giả định “thất bại = chưa ghi”.

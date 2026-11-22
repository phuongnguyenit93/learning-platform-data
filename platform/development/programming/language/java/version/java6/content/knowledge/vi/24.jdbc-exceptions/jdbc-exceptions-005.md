# SQLTransactionRollbackException và thất bại giao dịch trong JDBC (Java 17+)

## 1. Vấn đề: giao dịch đã thất bại không thể tiếp tục như thể chưa có gì xảy ra

Khi một ứng dụng thực hiện nhiều thao tác JDBC trong **cùng một transaction**, cơ sở dữ liệu có thể phải hủy bỏ hoặc từ chối một số thao tác để giữ tính đúng đắn trước các giao dịch chạy đồng thời. Hai nguyên nhân quan trọng:

- **Deadlock:** hai hoặc nhiều transactions giữ các khóa mà transaction khác đang chờ, tạo một chu trình phụ thuộc. Database thường chọn một transaction làm **victim** và hủy nó để các transaction còn lại tiến lên.
- **Serialization failure:** database không thể bảo đảm kết quả của các transaction concurrent tương đương một thứ tự chạy tuần tự hợp lệ dưới chính sách isolation. Nó có thể báo lỗi và yêu cầu một transaction chạy lại từ đầu.

Trong JDBC, Java có subclass **`java.sql.SQLTransactionRollbackException`** để biểu diễn một nhóm lỗi rollback giao dịch. Đây là **một subclass của `SQLTransientException`**, bản thân là subclass của `SQLException`:

~~~text
java.lang.Exception
  └── java.sql.SQLException
        └── java.sql.SQLTransientException
              └── java.sql.SQLTransactionRollbackException
~~~

Javadoc Java SE 25 mô tả class này dùng khi **SQLState class là `40`** hoặc khi có các điều kiện riêng do vendor chỉ định; tình huống thường gặp là database tự rollback statement vì deadlock/transaction serialization failure. **Tuy nhiên**, phạm vi rollback thực tế (statement, toàn transaction, trạng thái aborted) và việc JDBC driver có ném đúng subclass này hay ném một `SQLException` khác **phụ thuộc driver và DBMS**. Không được suy diễn “mọi `SQLTransactionRollbackException` đều chỉ rollback một statement” hoặc “mọi deadlock đều là subclass ấy”.

**Quy tắc nghiệp vụ an toàn:** Khi xảy ra serialization conflict/deadlock cần retry, hãy **kết thúc lượt transaction lỗi**, rollback/cleanup theo hợp đồng driver, **mở transaction mới** và **chạy lại toàn bộ đơn vị công việc** gồm cả các truy vấn đọc và quyết định giá trị cần ghi. Không chỉ gọi lại câu SQL cuối trên connection đang ở transaction lỗi.

### Ví dụ: chuyển tiền gồm hai bước phải nguyên tử

~~~text
Transaction chuyển 50 đơn vị từ tài khoản A sang B:
    BEGIN
      UPDATE accounts SET balance = balance - 50 WHERE id = A;
      UPDATE accounts SET balance = balance + 50 WHERE id = B;
    COMMIT

Giả sử giao dịch thất bại ở câu UPDATE thứ hai:
    Database: transaction rollback / serialization conflict
    App: không được coi lệnh debit đã thành công
    Retry: bắt đầu transaction MỚI, chạy lại debit VÀ credit
~~~

Nếu chỉ retry `UPDATE credit`, ứng dụng có thể tạo kết quả sai tùy DBMS đã rollback phần nào. Với PostgreSQL `40001` và deadlock rollback của SQL Server/MySQL InnoDB, chính sách là **retry toàn bộ transaction**. Đối với lỗi lock wait timeout, database khác có thể chỉ rollback **statement** và giữ transaction đang hoạt động; xử lý theo **đúng vendor semantics**, không gom chung tất cả lỗi lock thành một chiến lược.

## 2. Đọc chính xác `SQLTransactionRollbackException`

### API và ý nghĩa

~~~java
public class SQLTransactionRollbackException extends SQLTransientException
~~~

Đây là **mô tả chữ ký** của class thuộc `java.sql`, không phải class bạn cần tự định nghĩa. Constructors đang được hỗ trợ cho phép cung cấp thông báo, `SQLState`, vendor error code và cause, ví dụ:

~~~java
SQLTransactionRollbackException example =
        new SQLTransactionRollbackException(
                "Simulated serialization conflict", "40001", 0);
~~~

Đây là đoạn Java minh họa trong method với import `java.sql.SQLTransactionRollbackException`. Trong thực tế, **JDBC driver** thường ném exception khi câu SQL hoặc commit gặp lỗi; application không tự ném nó để “yêu cầu database rollback”.

Thông tin cần đọc ở một `SQLException`:

| Thành phần | Phương thức | Tại sao quan trọng? |
| --- | --- | --- |
| Runtime class | `ex.getClass().getName()` hoặc `instanceof` | Có thể là `SQLTransactionRollbackException`, một `SQLException` chung hoặc vendor-specific subclass |
| SQLState | `ex.getSQLState()` | Mã SQLSTATE chuẩn/thông dụng, ví dụ `40001`, `40P01` |
| Vendor error code | `ex.getErrorCode()` | Mã số riêng theo DBMS/driver, ví dụ SQL Server `1205` |
| Message | `ex.getMessage()` | Gợi ý chẩn đoán, **không** phải nguồn nhận diện lỗi duy nhất |
| Cause | `ex.getCause()` | Lỗi gốc được bọc, có thể gồm network/I/O/driver detail |
| Chained SQL exceptions | `ex.getNextException()` | Một chuỗi các lỗi JDBC từ driver; không phải đồng nghĩa `getCause()` |
| Suppressed exceptions | `ex.getSuppressed()` | Ví dụ lỗi `rollback` hoặc `close` phát sinh khi đang xử lý lỗi chính |

`SQLTransactionRollbackException` là subclass của **`SQLTransientException`**, ám chỉ nguyên nhân **có thể** tạm thời và thao tác **có thể** thành công nếu thử lại trong điều kiện phù hợp. Nó **không** có nghĩa Java hoặc DriverManager sẽ tự retry, và cũng **không** chứng minh việc retry không có rủi ro nghiệp vụ.

### Kiểu exception và SQLState không luôn đi thành cặp hoàn hảo

Một số driver dùng subclass JDBC cụ thể; một số dùng loại exception riêng hoặc `SQLException` chung với `SQLState` thích hợp. Nếu chỉ bắt:

~~~java
catch (SQLTransactionRollbackException ex) {
    // ...
}
~~~

bạn **có thể bỏ sót** lỗi deadlock/serialization của một driver không dùng subclass này. Ngược lại, chỉ thấy `getSQLState().startsWith("40")` chưa đủ để quyết định retry vô điều kiện mọi trường hợp. SQLState class `40` có nhiều trạng thái, trong đó `40003` là **statement_completion_unknown** ở những hệ hỗ trợ, khác với retry được phép một cách chắc chắn.

**Đặt retry classification theo database đã chọn**, dựa trên SQLState/vendorCode/cause chain có tài liệu, không parse nội dung message dễ thay đổi theo phiên bản và ngôn ngữ. Thử lại code path với **driver version thật** vì mapping exception có thể khác kỳ vọng.

## 3. SQLState class `40`, mã lỗi và các ngoại lệ dễ nhầm

**SQLState** thường là chuỗi năm ký tự. **Hai ký tự đầu** biểu thị class; class `40` liên quan **transaction rollback**. Các mã quan trọng:

| Mã/loại | Ý nghĩa thường gặp | Hướng xử lý |
| --- | --- | --- |
| `40001` | `serialization_failure` — lỗi serialization, được PostgreSQL mô tả rõ; cũng gặp ở drivers khác tùy vendor | Thường retry **trọn transaction** nếu an toàn |
| `40P01` | PostgreSQL `deadlock_detected` | Có thể retry trọn transaction; điều tra lock ordering nếu lặp |
| `40000` | Transaction rollback, điều kiện chung | Đọc vendor docs, không tự động retry mù |
| `40002` | Transaction integrity constraint violation theo hệ thống SQLState hỗ trợ | Xem nguyên nhân/constraint, không mặc định transient |
| `40003` | Statement completion unknown (nơi được hỗ trợ) | **Cẩn trọng về tính chắc chắn của kết quả**, không retry ghi vô điều kiện |
| SQL Server vendor code `1205` | Deadlock victim; SQL Server rollback victim transaction | Retry trọn giao dịch nếu có idempotency/đúng business contract |
| MySQL InnoDB vendor code `1213` | Deadlock detected; InnoDB rollback cả transaction | Retry trọn giao dịch |
| MySQL InnoDB `1205` | Lock wait timeout (mặc định chỉ rollback statement) | Khác deadlock; policy tùy server setting và app transaction |
| `23505` ở PostgreSQL | Unique-violation, class `23` (integrity violation) | Thường **không** retry; một số trường hợp concurrency đặc biệt cần policy tường minh |
| `08xxx` | Connection exception class trong nhiều drivers | Kết nối/commit có thể ở trạng thái không rõ; không coi như lỗi serialization an toàn |
| `SQLTimeoutException` | Timeout ở JDBC layer | Không đồng nghĩa transaction đã rollback cả; xác định trạng thái và deadline |
| `SQLNonTransientException` | Lỗi được phân loại là không transient | Thường cần sửa đầu vào/cấu hình, không retry vô hạn |

**Các mã trong bảng là minh họa theo SQLState/DBMS nêu rõ**, không phải cam kết mọi driver sẽ dùng cùng một Java exception subclass hoặc errorCode. Ví dụ PostgreSQL pgJDBC có thể bọc lỗi thành vendor-specific `PSQLException` với `getSQLState()`; phải phân loại theo API và docs của driver, không cast cứng `SQLTransactionRollbackException`.

### PostgreSQL: `40001` và `40P01`

PostgreSQL 18 documentation nêu:

- `40001` = `serialization_failure` ở những transaction isolation levels có thể phát hiện serialization anomaly, chẳng hạn Repeatable Read và Serializable.
- `40P01` = `deadlock_detected`.
- Khi gặp `40001`, cần thử lại **giao dịch đầy đủ**, gồm **toàn bộ logic chọn SQL và tính toán các tham số**. PostgreSQL không tự retry thay application vì DB không thể bảo đảm tính đúng đắn của logic ứng dụng.
- `40P01` cũng có thể được retry nếu phù hợp; nên điều tra nguyên nhân deadlock.
- Có các trường hợp đặc biệt liên quan `23505` hoặc exclusion constraint `23P01` do cạnh tranh chọn khóa, nhưng **không** có nghĩa retry mọi integrity violation là đúng.

Trong PostgreSQL, sau lỗi một transaction explicit thường ở trạng thái **aborted** và những câu tiếp theo có thể nhận `25P02` (current transaction is aborted) cho đến khi rollback. `SAVEPOINT` có ứng dụng riêng nhưng **không** biến serialization failure thành một transaction đã được xác nhận thành công. Retry một attempt mới từ đầu khi chính sách yêu cầu full transaction.

### Microsoft SQL Server: deadlock victim `1205`

Microsoft SQL Server Deadlocks Guide mô tả engine phát hiện chu trình khóa, chọn một transaction victim, **rollback transaction đó** và báo lỗi `1205`. Việc retry toàn bộ transaction với delay nhỏ là một phương án ứng dụng có thể dùng. Cách tránh deadlock quan trọng: truy cập các bảng/rows theo **cùng thứ tự** giữa những luồng nghiệp vụ khác nhau.

**Không** chỉ dựa vào `ex instanceof SQLTransactionRollbackException` khi code phải hoạt động với Microsoft JDBC Driver: hãy đọc vendor code/SQLState mà driver trả thực tế và test. Tài liệu driver có cả các tính năng retry ở mức connection hoặc statement trong một số phiên bản; các tính năng ấy **không đồng nghĩa tái thực hiện mọi statement và business decision của một multi-statement transaction**.

### MySQL InnoDB: deadlock khác lock-wait timeout

MySQL 8.4 manual phân biệt:

- **Deadlock:** InnoDB rollback **cả transaction** của victim; cần chuẩn bị retry transaction.
- **Lock wait timeout:** mặc định InnoDB rollback **statement hiện tại**, không phải toàn transaction. Nếu server bật `innodb_rollback_on_timeout`, toàn transaction có thể bị rollback. Phải biết cấu hình hệ thống và trạng thái transaction.
- Trong cả hai trường hợp, hãy giới hạn retries, giảm transaction length và chú ý lock order. Không dựa vào câu chữ lỗi chứa từ `timeout` để suy ra toàn transaction đã rollback.

**Kết luận:** ý nghĩa retry là kết hợp **JDBC exception + SQLState + vendor code + transaction boundary + DBMS semantics**, không phải một phép `startsWith("40")` áp dụng cho mọi database.

## 4. Deadlock, serialization failure và lock timeout khác nhau thế nào?

### Deadlock

Một diễn biến đơn giản:

~~~text
Transaction T1: UPDATE accounts WHERE id = 1  -> giữ lock A
Transaction T2: UPDATE accounts WHERE id = 2  -> giữ lock B
T1: UPDATE accounts WHERE id = 2              -> chờ lock B
T2: UPDATE accounts WHERE id = 1              -> chờ lock A

T1 <---wait---> T2  (cycle)

Database phát hiện deadlock, chọn một victim,
rollback victim theo DBMS và báo lỗi cho ứng dụng.
~~~

Deadlock có thể xảy ra **ngay cả khi isolation không phải SERIALIZABLE**, vì write locks vẫn có thể tranh chấp. Thay isolation level có thể thay đổi workload, nhưng không thay yêu cầu xử lý concurrent updates.

**Phòng ngừa:** sắp thứ tự lock thống nhất; transaction ngắn; indexes đúng cho UPDATE/SELECT FOR UPDATE; tránh giữ transaction khi gọi mạng/HTTP; hạn chế số rows bị khóa. Với tranh chấp cao, giảm độ rộng transaction hoặc thiết kế queue per-key khi hợp lý.

### Serialization conflict

Ở một isolation level với kiểm tra tính tuần tự, hai transactions có thể **không deadlock** nhưng lịch sử đọc/ghi của chúng không thể hợp thức hóa thành thứ tự tuần tự được. Database từ chối một transaction để bảo toàn tính đúng đắn.

Ví dụ:

~~~text
T1 đọc các booking hiện có trước khi quyết định tạo booking.
T2 đồng thời đọc cùng điều kiện và quyết định tạo booking khác.
Cả hai cùng ghi theo kết quả snapshot cũ.

Database kiểm tra concurrent history và có thể từ chối
một transaction bằng serialization failure (ví dụ PostgreSQL 40001).
~~~

Đây là **mô hình khái niệm**, không phải cam kết mọi engine đều dùng Serializable Snapshot Isolation hoặc mọi trường hợp phantom/write skew đều bị phát hiện ở cùng isolation mode. Tùy DBMS, loại isolation, indexes và transaction shape.

**Quan trọng:** khi retry, ứng dụng phải **đọc lại các booking**, tính lại quyết định và tham số. Không chỉ replay một câu INSERT đã được tính từ snapshot cũ.

### Lock wait timeout

Một transaction có thể chờ khóa quá lâu mà **không có cycle deadlock**. Database/driver có thể báo timeout và phạm vi rollback phụ thuộc DBMS. Retry quá nhanh có thể tạo thêm load và kéo dài contention. Phải phân biệt **pool acquisition timeout**, **JDBC statement timeout**, **network/socket timeout** và **DB lock timeout**; chúng không nhất thiết thuộc SQLState class `40`.

## 5. Retry boundary đúng: toàn bộ giao dịch, không chỉ statement

Một cấu trúc transaction JDBC thuần:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);
    try {
        debit(connection, fromAccount, amount);
        credit(connection, toAccount, amount);
        connection.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
~~~

Đây là **đoạn minh họa bên trong method**: `dataSource`, `debit`, `credit`, `fromAccount`, `toAccount` và `amount` phải được khai báo; imports và SQLException handling phù hợp. Chỉ phù hợp khi code **tự sở hữu transaction boundary**. Trong application dùng transaction manager/container, không tự chuyển autoCommit/commit/rollback trên connection do framework quản lý nếu transaction manager mới là owner.

Các nguyên tắc:

1. **Một attempt = một transaction độc lập.** Mượn Connection, thiết lập transaction, thực hiện tất cả reads/decisions/writes, commit hoặc rollback.
2. **Exception có thể xuất hiện ở bất kỳ statement hoặc `commit()`.** Catch bao trọn toàn attempt, không chỉ `executeUpdate()` cuối.
3. **Rollback best effort** trong catch. Nếu rollback cũng lỗi, giữ exception gốc và `addSuppressed` lỗi rollback; không nuốt lỗi gốc.
4. **Đóng connection qua try-with-resources**, kể cả nếu rollback/commit lỗi. Lỗi close cũng có thể được suppressed tự động.
5. **Retry ở bên ngoài transaction boundary**, sau khi attempt cũ đã kết thúc và connection cũ được đóng. Không tái dùng một connection đang aborted.
6. **Giới hạn retries** và dùng backoff/jitter/deadline; không tạo vòng lặp vô hạn.
7. **Đánh giá idempotency và side effects:** nếu transaction có HTTP call, gửi email hoặc publish event trực tiếp, thực hiện lại cả method có thể thực thi tác dụng phụ hai lần.
8. **Không coi mọi lỗi transaction là retryable:** unique constraint, permission failure, syntax error, invalid parameters thường cần sửa chứ không chờ thử lại.

**Hợp đồng của JDBC không bảo đảm rollback() trên mọi connection hỏng đều thành công.** Đừng dựa vào `rollback` trả về được để chắc chắn database chưa commit nếu đã mất kết nối trong lúc commit. Nếu commit outcome không rõ, xử lý bằng idempotency key, kiểm tra trạng thái/transaction ledger theo nghiệp vụ, thay vì tự replay giao dịch ghi mù quáng.

## 6. Java 17+ runnable demo: thất bại một lần, thử lại trọn transaction

Ví dụ sau dùng **JDK chuẩn** và mô phỏng `DataSource`/`Connection`/`PreparedStatement` bằng **dynamic proxies**. Nó không yêu cầu PostgreSQL, SQL Server hoặc MySQL; không tạo socket và **không thay đổi database thật**. Mục đích là kiểm chứng bằng code:

- Transaction attempt 1 mở một connection, chạy câu `UPDATE debit` thành công, rồi câu `UPDATE credit` ném `SQLTransactionRollbackException("...", "40001")`.
- Khối catch **rollback** attempt 1, sau đó try-with-resources đóng connection.
- Retry controller bắt lỗi cụ thể `SQLTransactionRollbackException` với **SQLState chính xác `40001`** và gọi lại **`transferOnce` từ đầu**.
- Transaction attempt 2 mở **connection mới**, chạy lại **debit và credit** rồi commit đúng một lần.
- Bộ đếm quan sát việc toàn transaction được replay, không chỉ câu credit.

**Giới hạn của demo:** fake driver không thực hiện SQL, không kiểm thử locking, isolation, race conditions hoặc database state. `getConnection` với username/password cũng được fake trả connection bất kể credential. Lỗi `40001` được **cố ý tạo** để kiểm tra retry flow; với production, driver quyết định SQLState/class thực tế. Demo retry ngay để kết quả xác định; production phải có **backoff với jitter và deadline**.

Tạo file duy nhất **`TransactionRetryDemo.java`**:

~~~java
import java.io.PrintWriter;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import java.sql.SQLTransactionRollbackException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.logging.Logger;
import javax.sql.DataSource;

public final class TransactionRetryDemo {
    static final class SimulatedDataSource implements DataSource {
        final AtomicInteger opened = new AtomicInteger();
        final AtomicInteger closed = new AtomicInteger();
        final AtomicInteger executions = new AtomicInteger();
        final AtomicInteger commits = new AtomicInteger();
        final AtomicInteger rollbacks = new AtomicInteger();

        @Override public Connection getConnection() {
            int attempt = opened.incrementAndGet();
            AtomicBoolean ended = new AtomicBoolean();
            return (Connection) Proxy.newProxyInstance(
                    getClass().getClassLoader(), new Class<?>[]{Connection.class},
                    (proxy, method, args) -> switch (method.getName()) {
                        case "setAutoCommit" -> null;
                        case "prepareStatement" -> {
                            if (ended.get()) throw new SQLException("Closed connection");
                            yield statement((String) args[0], attempt);
                        }
                        case "commit" -> {
                            if (ended.get()) throw new SQLException("Closed connection");
                            commits.incrementAndGet();
                            yield null;
                        }
                        case "rollback" -> {
                            rollbacks.incrementAndGet();
                            yield null;
                        }
                        case "close" -> {
                            if (ended.compareAndSet(false, true)) closed.incrementAndGet();
                            yield null;
                        }
                        case "isClosed" -> ended.get();
                        default -> throw new SQLFeatureNotSupportedException(method.getName());
                    });
        }

        private PreparedStatement statement(String sql, int attempt) {
            return (PreparedStatement) Proxy.newProxyInstance(
                    getClass().getClassLoader(), new Class<?>[]{PreparedStatement.class},
                    (proxy, method, args) -> switch (method.getName()) {
                        case "setInt", "setLong", "close" -> null;
                        case "executeUpdate" -> {
                            executions.incrementAndGet();
                            if (attempt == 1 && sql.contains("balance + ?")) {
                                throw new SQLTransactionRollbackException(
                                        "Simulated serialization conflict", "40001");
                            }
                            yield 1;
                        }
                        default -> throw new SQLFeatureNotSupportedException(method.getName());
                    });
        }

        @Override public Connection getConnection(String username, String password)
                throws SQLException { return getConnection(); }
        @Override public PrintWriter getLogWriter() { return null; }
        @Override public void setLogWriter(PrintWriter writer) { }
        @Override public void setLoginTimeout(int seconds) { }
        @Override public int getLoginTimeout() { return 0; }
        @Override public Logger getParentLogger() {
            return Logger.getLogger("demo.transactions");
        }
        @Override public <T> T unwrap(Class<T> type) throws SQLException {
            if (type.isInstance(this)) return type.cast(this);
            throw new SQLException("Unsupported wrapper");
        }
        @Override public boolean isWrapperFor(Class<?> type) { return type.isInstance(this); }
    }

    static void update(Connection connection, String sql, long account, int amount)
            throws SQLException {
        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setInt(1, amount);
            ps.setLong(2, account);
            int count = ps.executeUpdate();
            if (count != 1) throw new SQLException("Account not found");
        }
    }

    static void transferOnce(DataSource source) throws SQLException {
        try (Connection c = source.getConnection()) {
            c.setAutoCommit(false);
            try {
                update(c, "UPDATE accounts SET balance = balance - ? WHERE id = ?", 10L, 50);
                update(c, "UPDATE accounts SET balance = balance + ? WHERE id = ?", 20L, 50);
                c.commit();
            } catch (SQLException | RuntimeException ex) {
                try {
                    c.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }

    static void transferWithRetry(DataSource source, int maxAttempts)
            throws SQLException {
        if (maxAttempts < 1) throw new IllegalArgumentException("maxAttempts");
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                transferOnce(source);
                System.out.println("committed attempt: " + attempt);
                return;
            } catch (SQLTransactionRollbackException e) {
                if (!"40001".equals(e.getSQLState())) throw e;
                System.out.println("retryable SQLState: " + e.getSQLState());
                if (attempt == maxAttempts) throw e;
                // Simulated local driver: immediate retry is deterministic.
                // Production: bounded exponential backoff with jitter and deadline.
            }
        }
    }

    public static void main(String[] args) throws SQLException {
        SimulatedDataSource source = new SimulatedDataSource();
        transferWithRetry(source, 3);
        System.out.println("connections opened: " + source.opened.get());
        System.out.println("SQL statements executed: " + source.executions.get());
        System.out.println("commits: " + source.commits.get());
        System.out.println("rollbacks: " + source.rollbacks.get());
        System.out.println("connections closed: " + source.closed.get());
    }
}
~~~

Biên dịch và chạy trên JDK 17+ tại thư mục chứa source:

~~~bash
javac --release 17 TransactionRetryDemo.java
java TransactionRetryDemo
~~~

**Stdout đã kiểm chứng chính xác** trên **OpenJDK 24.0.2** với `javac --release 17`:

~~~text
retryable SQLState: 40001
committed attempt: 2
connections opened: 2
SQL statements executed: 4
commits: 1
rollbacks: 1
connections closed: 2
~~~

### Giải thích từng dòng

- `retryable SQLState: 40001`: attempt 1 lỗi ở câu `UPDATE credit`; retry classifier trong demo chỉ chấp nhận **một mã chính xác `40001`**, không retry mọi `SQLException`.
- `committed attempt: 2`: attempt 2 hoàn thành và commit; attempt 1 không có commit.
- `connections opened: 2`: mỗi attempt dùng **một Connection khác**, minh họa lifetime rõ ràng.
- `SQL statements executed: 4`: attempt 1 thực hiện debit/credit (credit ném lỗi) và attempt 2 **thực hiện lại cả debit/credit**. Nếu chỉ retry câu thứ hai, bộ đếm sẽ là 3.
- `commits: 1`, `rollbacks: 1`: phân biệt một lần rollback attempt cũ và một commit attempt mới.
- `connections closed: 2`: try-with-resources đóng Connection ở cả hai lượt.
- `SQLFeatureNotSupportedException` trong fake dành cho method chưa mô phỏng: **không dùng fake này trong production**.
- Các câu UPDATE không tương tác với bảng `accounts` thật. Để chuyển tiền thật, còn cần kiểm soát balance check, negative balance, isolation, data constraints, idempotency và transaction manager; demo chỉ tập trung exception flow.

### Tại sao fake phải tạo exception ở câu SQL thứ hai?

Nếu lỗi xảy ra ngay ở câu đầu, một retry chỉ gồm phần còn lại khó bộc lộ sai lầm. Đặt lỗi ở câu thứ hai tạo ra trường hợp có **một statement trước đó đã chạy**; bản demo cho thấy rollback và replay toàn bộ transaction là quyết định có chủ đích.

### Vì sao retry bao ngoài `transferOnce`?

`transferOnce` **sở hữu transaction**: mở connection, `setAutoCommit(false)`, hai statements, `commit`, `rollback` và close. `transferWithRetry` không giữ connection lỗi; nó chỉ xác định điều kiện retry, ngân sách số lượt, gọi lại nguyên hàm.

**Không bắt `SQLTransactionRollbackException` rồi gọi `c.commit()` tiếp như thể transaction vẫn dùng được.** Nhiều database đã rollback hoặc chuyển connection transaction sang aborted state. Thoát lượt cũ, cleanup và tạo attempt mới.

## 7. Chính sách retry production: classifier, attempt budget, backoff và deadline

### Chỉ retry lỗi được chứng minh là retryable

Một ứng dụng PostgreSQL có thể bắt `SQLException` chung và phân loại SQLState, bởi một số drivers không nhất thiết dùng subclass `SQLTransactionRollbackException`:

~~~java
static boolean retryablePostgresTransactionFailure(SQLException ex) {
    for (SQLException current = ex;
         current != null;
         current = current.getNextException()) {
        String sqlState = current.getSQLState();
        if ("40001".equals(sqlState) || "40P01".equals(sqlState)) {
            return true;
        }
    }
    return false;
}
~~~

Đây là **một method minh họa**, cần import `java.sql.SQLException`. Nó xử lý hai mã mà PostgreSQL documentation khuyến nghị xét retry, kể cả khi JDBC driver không ném subclass chuyên biệt. **Không dùng nguyên method này làm classifier chung cho Oracle, SQL Server, MySQL**. Nếu vendor chỉ công bố errorCode và driver không đặt SQLState phù hợp, cần policy riêng.

**Chú ý:** `getNextException()` là một chain JDBC riêng; lỗi cũng có thể được bọc trong `getCause()` bởi framework (chẳng hạn `DataAccessException` của Spring). Khi có framework, xem khả năng unwrap cause **theo API framework**, kiểm tra root cause/SQLState có thể cần duyệt cả cause chain, nhưng không đi vòng vô hạn và không tự tạo policy retry từ message text.

### Retry phải giới hạn số lần và thời gian

Mô hình khuyến nghị:

~~~text
for attempt = 1 .. MAX_ATTEMPTS:
    if requestDeadlineExceeded: abort

    BEGIN transaction mới
       đọc lại dữ liệu
       tính lại quyết định / parameters
       chạy các câu SQL liên quan
       COMMIT
    nếu thành công: return

    nếu lỗi:
       rollback/cleanup
       nếu lỗi KHÔNG thuộc policy retry: throw
       nếu đạt maxAttempts: throw
       nếu deadline hết: throw
       sleep với backoff + jitter (có tôn trọng interruption)
       thử lại từ đầu
~~~

**Backoff exponential có jitter** giúp các workers thất bại cùng lúc không lập tức tranh nhau cùng các locks, giảm "thundering herd". Chẳng hạn đặt base delay nhỏ 20–50 ms, cap phù hợp với service latency budget, random jitter. Không có một bộ thông số đúng cho mọi workload; hãy đo trên DB thực, với deadline của request.

Đoạn Java 17+ minh họa một lần backoff có giới hạn:

~~~java
static void backoff(int attempt) throws SQLException {
    int exponent = Math.max(0, Math.min(attempt - 1, 5));
    long capMillis = Math.min(1000L, 25L * (1L << exponent));
    long sleepMillis = java.util.concurrent.ThreadLocalRandom.current()
            .nextLong(capMillis + 1);
    try {
        Thread.sleep(sleepMillis);
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        throw new SQLException("Retry interrupted", interrupted);
    }
}
~~~

Đây là **method minh họa** dùng trong retry controller khi lỗi thuộc allowlist, không được tự chèn vào fake demo nếu muốn giữ stdout/execution deterministic ở trên. `Thread.sleep` là blocking: với event-loop/reactive app, dùng **scheduler bất đồng bộ** của framework và truyền request deadline thay vì block event loop. Tính `attempt` và cap giúp tránh overflow shift; trong production, kết hợp cả **tổng deadline** và cancellation.

### Không retry một transaction với side effect nằm ngoài DB

Ví dụ nguy hiểm:

~~~text
BEGIN DB transaction
    UPDATE orders SET status = 'PAID' ...
    call external payment API      <-- side effect không rollback theo DB
    send confirmation email        <-- email đã gửi không bị SQL ROLLBACK hủy
    COMMIT (gặp serialization conflict)
Retry toàn method:
    payment bị gọi lần nữa, email gửi lần nữa ...
~~~

**Cách phòng:** tách hiệu ứng ngoài DB và bảo đảm **idempotency**:

- Dùng **business operation ID/idempotency key** có unique constraint và transactionally recorded state.
- Đưa message vào **transactional outbox** cùng transaction DB; một publisher độc lập gửi khi commit thành công, dùng deduplication/idempotent consumer.
- Với payment API, truyền idempotency key được gateway hỗ trợ, ghi nhận request/result và có reconciliation process cho outcome chưa xác định.
- Với email/sự kiện, thiết kế **at-least-once delivery** và consumer deduplication; không giả định exactly-once end-to-end chỉ nhờ JDBC transaction.
- Nếu một business step gọi API ngoài DB trong transaction, cân nhắc saga/compensation riêng thay vì mù quáng retry toàn bộ.

### Idempotent SQL không đồng nghĩa idempotent nghiệp vụ

`UPDATE accounts SET balance = balance - 50 WHERE id = 10` là **không idempotent** nếu thực thi hai lần và cả hai cùng commit. Khi attempt lỗi đã chắc chắn rollback, thực thi lại toàn transaction có thể an toàn; nhưng **khi kết quả commit không rõ**, hai lần chạy có thể trừ tiền hai lần. Giải pháp là operation key/ledger với unique constraint, kiểm tra committed operation và chặn duplicate.

`INSERT ... ON CONFLICT`, upsert hoặc unique keys có thể là công cụ tốt nhưng phải thiết kế dựa trên **business identity**. Chọn generated keys trong lần chạy trước rồi reuse sau serialization failure có thể không còn hợp lệ; PostgreSQL khuyến nghị retry cả logic quyết định dữ liệu ghi.

## 8. `commit()` cũng có thể thất bại — outcome chưa rõ khác với rollback có xác nhận

Một retry controller không nên chỉ catch lỗi tại `PreparedStatement.executeUpdate()`. `Connection.commit()` cũng có thể ném `SQLException` vì database phát hiện conflict **ở commit time** (ví dụ constraint/serialization checks) hoặc vì lỗi mạng trong lúc commit.

Phân biệt:

- **Transaction rollback được database xác nhận:** `40001`/deadlock victim theo DBMS → bắt đầu transaction mới và retry nếu business operation an toàn.
- **`commit` đã được gửi, connection đứt trước khi client nhận kết quả:** **không biết** database đã commit thành công hay chưa. Chỉ tạo connection mới và replay những thao tác ghi là **nguy hiểm**.
- **Integrity/validation failure không transient:** cần đổi dữ liệu, không dùng retry/backoff để che constraint violation.
- **Connection invalid:** khôi phục connection/pool là một bài toán khác với retry business operation; tránh chạy tiếp transaction đã hỏng.

Ví dụ đặc biệt nguy hiểm là một payment request đã ghi thành công vào DB nhưng client nhận network error. Nếu app retry với payment ID mới mà không tra cứu ledger, có thể ghi trùng. Cần **reconciliation/idempotency key** để xác định outcome trước khi quyết định tái thực hiện.

**`SQLTransactionRollbackException` không có phương thức thần kỳ nào xác nhận business outcome.** `getSQLState` và `getErrorCode` giúp phân loại, còn tính idempotency và consistency cần thiết kế nghiệp vụ và database constraints.

## 9. JDBC transaction isolation và điều kiện xảy ra lỗi

JDBC có `Connection.setTransactionIsolation(int level)` với các hằng:

| JDBC isolation constant | Ý nghĩa khái quát |
| --- | --- |
| `Connection.TRANSACTION_READ_UNCOMMITTED` | Có thể cho phép một số hiện tượng đọc chưa commit; phụ thuộc DBMS |
| `Connection.TRANSACTION_READ_COMMITTED` | Chỉ thấy dữ liệu đã commit theo quy tắc engine |
| `Connection.TRANSACTION_REPEATABLE_READ` | Thường ngăn non-repeatable reads; semantics snapshot/locking khác nhau |
| `Connection.TRANSACTION_SERIALIZABLE` | Yêu cầu execution tương đương serial order theo semantics DBMS |

**Không giả định mọi DBMS triển khai các isolation levels bằng cùng thuật toán.** PostgreSQL và MySQL có MVCC/locking khác nhau; SQL Server có thêm snapshot-related options. Một DBMS có thể map một mức isolation được yêu cầu sang mức khác, hoặc không hỗ trợ. Kiểm tra `DatabaseMetaData.supportsTransactionIsolationLevel(...)`, `Connection.getTransactionIsolation()` và driver documentation.

- Deadlock có thể xảy ra ở nhiều isolation levels khi write locks/row locks tranh chấp.
- PostgreSQL Repeatable Read và Serializable có thể sinh `40001`; policy retry phải sẵn sàng nếu workload dùng những mức này.
- Chuyển thẳng `SERIALIZABLE` sang `READ_COMMITTED` **không phải** một fix an toàn cho `40001` nếu nghiệp vụ cần chống write skew/serialization anomaly.
- Isolation level thấp hơn có thể giảm một số conflicts nhưng tạo anomlies nghiệp vụ; một số constraints/atomic updates vẫn cần design riêng.
- Với pool, cấu hình isolation ở **transaction manager/connection scope** rõ ràng và đảm bảo connection state được reset trước khi pool tái sử dụng.

### Deadlock prevention không thay thế retry

Ngay cả khi luôn lock theo cùng thứ tự, còn có interactions qua foreign keys, secondary indexes, triggers hoặc jobs mà bạn không kiểm soát hoàn toàn. Cần thiết kế chống deadlock **và** có retry policy cho những lỗi được xác định. Nếu deadlocks tăng mạnh, đừng chỉ tăng maxAttempts: hãy điều tra query plans, indexes, transaction ordering, lock durations và contention hotspot.

## 10. Tích hợp với Spring/Jakarta transaction manager

Trong ứng dụng Java server, nhiều dự án dùng Spring `@Transactional` hoặc Jakarta transactions thay vì tự gọi `setAutoCommit(false)`/`commit()`. Khi đó **framework quản lý transaction boundary**. Retry phải nằm **ngoài boundary** để mỗi attempt thực sự có một transaction mới.

Mô hình khái niệm:

~~~text
RetryingApplicationService  (outer retry)
   ├─ attempt 1 -> gọi TransactionalBusinessService qua proxy
   │                   @Transactional -> begin / rollback
   ├─ backoff
   └─ attempt 2 -> gọi TransactionalBusinessService qua proxy
                       @Transactional -> begin / commit
~~~

**Cảnh báo quan trọng:**

- Nếu đặt retry loop **bên trong cùng một `@Transactional` method**, nhiều attempts có thể chạy trong **một transaction đã bị đánh dấu rollback-only/aborted**, không có ích.
- Spring proxy-based AOP có hạn chế **self-invocation**: gọi method `@Transactional` của chính instance từ method khác cùng instance có thể không đi qua proxy, nên transaction boundary mong muốn không được tạo. Dùng bean/service boundary rõ hoặc programmatic `TransactionTemplate` khi phù hợp.
- `@Retryable` từ thư viện Spring Retry là **framework-specific**, không phải thành phần JDK/JDBC. Thứ tự interceptor/advice, exception translation và transaction manager configuration quyết định mỗi lần retry có transaction mới không.
- PostgreSQL 40001 có thể được framework dịch sang một subclass của `DataAccessException` thay vì để `SQLException` trần. Phân loại theo **root cause/SQLState/cause chain** hoặc policy framework được tài liệu hỗ trợ.
- Nếu một method được đánh dấu `REQUIRES_NEW`, transaction mới có thể dùng pool connection bổ sung; số concurrent retries phải có giới hạn và pool capacity.
- Không gọi `connection.rollback()` thủ công trên một connection mà container quản lý nếu transaction manager đã sở hữu rollback boundary.

Trong Jakarta EE, transaction có thể được quản lý bởi `UserTransaction`/CDI/JTA tùy môi trường; logic tương tự: **retry bên ngoài transaction owner**, không chèn `rollback/commit` khi container đã điều phối.

## 11. Logging, metrics và phân loại sự cố

Mỗi lần lỗi giao dịch nên có metadata phục vụ điều tra, nhưng không làm lộ SQL parameters/secrets:

| Trường ghi nhận | Giá trị hữu ích |
| --- | --- |
| Logical operation | Chẳng hạn `transferFunds`, `submitOrder`, `allocateInventory` |
| Attempt count | Lần thứ mấy / max attempts |
| SQLState | `40001`, `40P01` hoặc mã thực |
| Vendor errorCode | Ví dụ SQL Server `1205`, nếu driver cung cấp |
| Exception class | Java exception/runtime class |
| Correlation ID | Một ID của request/business operation **không nhạy cảm** |
| Transaction scope | Tên transaction/unit of work và thời gian chạy |
| Database/driver info | Vendor/version theo môi trường deployment |
| Retry decision | Retry/exhausted/non-retryable/unknown-outcome |
| Backoff delay | Giúp chẩn đoán thundering herd |
| Pool metrics | Active/idle/waiting connections, acquisition timeouts |
| DB metrics | Deadlocks/serialization failures, lock wait time, long transactions |

**Không log** password, JDBC URL chứa secrets, PII trong SQL bind parameters, full exception message chứa nội dung truy vấn nhạy cảm hoặc nội dung nghiệp vụ không cần thiết. Giữ nguyên SQLState/errorCode và sanitized operation identity là đủ để phân nhóm cơ bản.

### `SQLException` có thể có nhiều chẩn đoán

Một số drivers nối thêm exceptions bằng `getNextException`, hoặc bọc nhiều causes. Trong log có kiểm soát, có thể duyệt:

~~~java
static void inspectSqlExceptions(SQLException first) {
    for (SQLException current = first;
         current != null;
         current = current.getNextException()) {
        System.out.printf("SQLState=%s vendorCode=%d type=%s%n",
                current.getSQLState(),
                current.getErrorCode(),
                current.getClass().getSimpleName());
    }
}
~~~

Đây là method Java 17+ hợp lệ nếu import `java.sql.SQLException`, nhưng gọi trong hệ thống thật cần logging đã sanitize và giới hạn số entries theo policy. **Không** dùng `getMessage()` như classifier duy nhất, vì messages có thể thay đổi theo localization, driver update hoặc parameter values.

Nếu `rollback()` ném thêm lỗi, `addSuppressed(rollbackFailure)` giữ cả hai: exception gây transaction fail và exception xảy ra khi cleanup. Nếu một framework đã xử lý rollback, hãy để framework giữ diagnostic chain và không gọi rollback thêm.

### Metrics cần theo dõi theo outcome

Đếm riêng **transaction attempts**, **successful commits**, **confirmed rollbacks**, **retry exhausted**, **non-retryable failures**, **unknown commit outcomes** và **request latency percentiles**. Đừng dùng `retryCount` như một success metric. Một hệ thống có 95% requests phải retry 3 lần đang có contention lớn dù eventual success rate cao.

## 12. Các anti-patterns thường gặp

| Cách làm sai | Vì sao nguy hiểm | Cách đúng |
| --- | --- | --- |
| `catch(SQLException) { retry(); }` cho mọi lỗi | Retry cả syntax/auth/constraint/permanent failures | Classifier theo SQLState/vendor docs + business semantics |
| `getMessage().contains("deadlock")` | Message thay đổi theo driver/ngôn ngữ | Dựa vào SQLState/errorCode và exception class |
| Chỉ bắt `SQLTransactionRollbackException` rồi tin mọi driver đều ném class này | Vendor driver có thể dùng `SQLException` riêng | Kiểm tra SQLState/driver mapping |
| `ex.getSQLState().startsWith("40")` không kiểm tra null | Có thể NPE và retry nhầm trạng thái | Kiểm tra null, allowlist mã được hỗ trợ |
| Retry **statement** thứ hai sau khi transaction đã rollback | Debit/read logic trước đó không được replay | Retry **toàn transaction** trên attempt mới |
| Retry trong một `@Transactional` method | Dùng lại transaction bị rollback-only | Đặt retry ngoài transaction boundary |
| Retry ngay, vô hạn, mọi thread | Tạo retry storm và database contention | Attempt budget + backoff/jitter/deadline |
| Coi SQLSTATE `40001` là thành công nếu retry sắp hết | Che mất lỗi thực | Khi hết attempts propagate lỗi có metadata |
| Bỏ qua SQLException ở `commit()` | Có thể mất consistency hoặc unknown outcome | Catch cả commit, phân biệt confirmed rollback và uncertain |
| Retry tất cả network errors sau commit | Có thể duplicate write | Idempotency key, ledger/reconciliation |
| Gửi email/payment mỗi attempt | Side effects không được DB rollback | Outbox, idempotent external APIs hoặc saga |
| Bỏ qua lỗi rollback | Mất thông tin cleanup | `addSuppressed`, propagate lỗi gốc |
| Dùng Connection cũ sau rollback/abort | Transaction state có thể không hợp lệ | Close/release, attempt mới |
| Giữ transaction mở trong lúc đợi API ngoài | Lock duration tăng, dễ deadlock | Tách external calls khỏi DB transaction |
| Tăng `SERIALIZABLE` một cách tùy tiện | Có thể tăng conflict rate | Chọn isolation theo correctness, có retry policy |
| Giảm isolation chỉ để hết `40001` | Có thể làm mất business invariants | Phân tích anomaly và lựa chọn có test |
| Bỏ constraints để tránh lỗi | Mất consistency dữ liệu | Giữ constraints, xử lý đúng concurrency |
| Không phân biệt lock timeout và deadlock | Rollback scope khác nhau giữa DBMS | Vendor policy rõ, test driver |
| Dùng fake test làm bằng chứng DB thật sẽ retry đúng | Fake không có locking/wire/protocol | Integration test với DB đúng version |
| Trả `null` cho mọi SQLException | Lỗi giao dịch thành “không có dữ liệu” | Error/result type tường minh |
| Log full SQL/parameters để debug | Lộ secrets và dữ liệu nhạy cảm | SQLState/errorCode, sanitized metadata |

## 13. Thiết kế integration tests cho serialization/deadlock

### Kiểm thử không cần DB: demo ở phần 6

Đoạn `TransactionRetryDemo` đã chứng minh:
- Controller nhận subclass transaction rollback exception;
- transaction attempt lỗi được rollback;
- toàn transaction chạy lại, **không chỉ câu statement thứ hai**;
- connection và PreparedStatement được đóng;
- attempt mới commit một lần;
- output/deterministic counters khớp.

Nhưng nó **không** chứng minh query thật có lock conflict, isolation của server, network failure hay JDBC vendor subclass mapping. Vì vậy cần bổ sung integration tests.

### Test với database thật

1. Dùng **test database riêng**, cùng JDBC driver và isolation/DB version production; không chạy deadlock stress test trên production.
2. Tạo các bản ghi có khóa định danh rõ; reset data giữa tests.
3. Dùng **hai connections khác nhau** từ DataSource/pool, `setAutoCommit(false)` và isolation level phù hợp.
4. Điều phối concurrency bằng barriers/latches trong **test harness**, không phụ thuộc timing ngẫu nhiên hoặc `Thread.sleep` cố định để tạo lock conflict.
5. Tạo hai transactions truy cập rows theo thứ tự đối nghịch để mô phỏng deadlock khi DBMS hỗ trợ, hoặc tạo workload serialization conflict có kiểm soát.
6. Ghi nhận **exception class, SQLState, vendorCode, transaction state và outcome thực tế**.
7. Xác nhận victim transaction đã rollback, không còn partial writes; winner commit chính xác.
8. Chạy retry ở **outer transaction boundary**, xác nhận transaction cuối có trạng thái đúng và số lần thử nằm trong giới hạn.
9. Kiểm tra câu `commit()` lỗi và connection broken, phân loại outcome unknown, không auto double-spend.
10. Kiểm tra resilience khi pool đầy, cancellation/deadline, rollback lỗi và lỗi `close()` bị suppressed.
11. Test side effects không lặp (outbox, payment idempotency, event deduplication).
12. Cleanup connections, executor threads và test records; không để test thất bại vì deadlock giả gây leak.

**Cảnh báo về test thời gian:** Deadlock reproduction có thể phụ thuộc lock/index/engine implementation; hãy thiết kế công cụ điều phối test theo DBMS và đặt timeout dứt khoát. Một số test serialization anomalies chỉ xuất hiện ở isolation level nhất định. Đừng biến integration test thành một benchmark ngẫu nhiên khó tái lập.

### Ví dụ SQL về lock order

~~~sql
-- Hai luồng cùng thống nhất khóa id theo thứ tự tăng dần.
-- Cú pháp và lock behavior thực tế phụ thuộc DBMS.
UPDATE accounts SET balance = balance - ? WHERE id = ?;
UPDATE accounts SET balance = balance + ? WHERE id = ?;
~~~

Đây là **SQL templates minh họa**. Để tránh deadlock do lock order khi transfer hai chiều, app có thể sắp xếp account IDs theo thứ tự ổn định khi lấy locks, nhưng vẫn áp dụng debit/credit theo vai trò nguồn/đích và business invariants. Nếu chỉ đổi thứ tự hai câu UPDATE mà vô tình đảo vai trò debit/credit, transaction có thể sai nghiệp vụ.

## 14. Checklist triển khai production

1. **Xác định DBMS và JDBC driver** đang chạy, version, SQLState/errorCode mappings; không giả định JDK tự nhận diện mọi vendor deadlock qua đúng subclass.
2. **Định nghĩa một unit of work/transaction rõ ràng:** các reads và writes cần atomic nằm trong cùng boundary.
3. **Giữ idempotency/consistency:** không gọi external payment/email trực tiếp trong retryable DB transaction; thiết kế outbox/ledger nếu cần.
4. **Phân loại error theo allowlist:** ví dụ PostgreSQL `40001`/`40P01`; SQL Server `1205`, MySQL InnoDB `1213` theo vendor docs; không retry mù toàn class `40`.
5. **Retry full transaction:** tính lại business decisions, mở connection/transaction mới, không dùng transaction aborted.
6. **Giới hạn retry:** maxAttempts, request deadline/cancellation, exponential backoff và jitter.
7. **Rollback/cleanup:** giữ exception gốc, thêm suppressed rollback failure, đóng Connection đúng owner.
8. **Xử lý commit uncertainty:** nếu không chắc commit đã xảy ra, đối soát bằng operation ID/idempotency key trước khi replay.
9. **Không trộn retry controller với framework transaction manager:** đảm bảo mỗi attempt thật sự có transaction mới; kiểm tra proxy/annotation order.
10. **Giảm contention:** consistent locking order, transactions ngắn, index đúng, không giữ locks qua network I/O.
11. **Quan sát:** SQLState/errorCode, attempt count, deadlock rate, latency, pool pressure, retry budget exhausted.
12. **Kiểm thử:** synthetic test + concurrency integration tests trên DB/driver thật, commit failures và side effects.
13. **Bảo mật:** không log secrets/SQL parameters nhạy cảm; không retry vô hạn dẫn tới DDoS DB.
14. **Nâng cấp driver/DB:** regression tests cho classification và rollback semantics, không chỉ compile qua JDK mới.

## 15. Câu hỏi tự kiểm tra

1. **`SQLTransactionRollbackException` kế thừa class nào?** `SQLTransientException`, rồi `SQLException`.
2. **SQLState class `40` nói về nhóm gì?** Transaction rollback.
3. **`40001` thường biểu thị điều gì?** Serialization failure, đặc biệt theo PostgreSQL docs.
4. **`40P01` ở PostgreSQL là gì?** Deadlock detected.
5. **Có thể giả định PostgreSQL pgJDBC luôn ném đúng `SQLTransactionRollbackException` không?** Không; phải kiểm tra exception/SQLState thực của driver.
6. **Tại sao retry một câu SQL cuối có thể sai?** Transaction trước đó có thể đã rollback, các reads/writes/decisions cần replay.
7. **Retry serialization failure có cần đọc lại dữ liệu và tính lại tham số không?** Có, bao gồm các business decisions của transaction.
8. **Deadlock có phải chỉ xảy ra ở SERIALIZABLE không?** Không, write locks có thể deadlock ở các levels khác.
9. **SQL Server deadlock victim báo mã nào?** Vendor error `1205`, theo SQL Server docs.
10. **MySQL InnoDB deadlock và lock-wait timeout có phạm vi rollback mặc định giống nhau không?** Không: deadlock rollback transaction; timeout mặc định rollback statement.
11. **`SQLTransientException` có đồng nghĩa retry luôn an toàn không?** Không, phải xét DBMS, SQLState, idempotency và transaction boundary.
12. **`Connection.commit()` có thể ném `SQLException` không?** Có; phải phân biệt confirmed rollback với unknown commit outcome.
13. **Mất mạng ngay sau khi gửi COMMIT có được retry một lệnh trừ tiền không?** Không mù quáng; cần operation ID, đối soát/idempotency.
14. **`rollback()` ném lỗi thì nên làm gì?** Giữ lỗi gốc, `addSuppressed` rollback failure, giải phóng connection.
15. **`getNextException()` giống `getCause()` không?** Không; SQL exception chain và Java cause chain là hai kênh thông tin.
16. **Vì sao không retry trong một `@Transactional` method đang chạy?** Nó có thể vẫn nằm trong transaction aborted/rollback-only; outer retry phải tạo boundary mới.
17. **Nếu retries quá nhanh, vấn đề gì có thể xảy ra?** Retry storm, tăng contention và latency.
18. **Backoff có nghĩa gì?** Tạm lùi thời điểm retry, thường exponential với jitter, bị giới hạn bởi deadline.
19. **`40003` có nên tự động retry mọi write không?** Không, vì ý nghĩa completion unknown đòi phân tích outcome/idempotency.
20. **Vì sao fake Java demo không chứng minh deadlock DB thật?** Nó chủ động tạo SQLException, không thực hiện khóa hay SQL.
21. **Tại sao cần consistent lock ordering?** Giảm chu trình phụ thuộc khóa và deadlock.
22. **Nếu có external payment trong transaction retry, cần gì?** Idempotency key/outbox/saga hoặc thiết kế tránh lặp side effect.
23. **Nếu cột đã có unique constraint bị `23505`, có luôn retry không?** Không; chỉ một vài tình huống concurrent business logic đặc biệt mới có căn cứ.
24. **Điều gì quan trọng hơn success sau nhiều retries?** Correctness/idempotency, ngân sách latency, DB load và metric contention.
25. **Khi SQLState null, có được gọi `startsWith("40")` không?** Không; phải null-check và chọn classifier khác theo driver.
26. **Một retry gồm bao nhiêu attempt được phép?** Một con số hữu hạn phù hợp workload, deadline, policy; không có số chuẩn cho mọi ứng dụng.

## 16. Tham khảo hiện hành và chính thức

- [Java SE 25 — SQLTransactionRollbackException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLTransactionRollbackException.html): class hierarchy, SQLState class `40`, vendor-specified conditions và constructors.
- [Java SE 25 — SQLTransientException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLTransientException.html): ý nghĩa transient và subclass JDBC.
- [Java SE 25 — SQLException](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/SQLException.html): `getSQLState`, `getErrorCode`, `getNextException`, JDBC exception chain.
- [Java SE 25 — Connection](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/Connection.html): `setAutoCommit`, `commit`, `rollback`, transaction isolation và `close`.
- [Java SE 25 — DataSource](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/javax/sql/DataSource.html): injected source of JDBC connections.
- [PostgreSQL 18 — Serialization Failure Handling](https://www.postgresql.org/docs/18/mvcc-serialization-failure-handling.html): `40001`/`40P01`, retry **entire transaction** bao gồm logic quyết định SQL/values.
- [PostgreSQL 18 — Error Codes](https://www.postgresql.org/docs/18/errcodes-appendix.html): class 40, `40001`, `40P01`, `25P02`.
- [Microsoft SQL Server — Deadlocks Guide](https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-deadlocks-guide): error `1205`, victim rollback và retry/prevention.
- [MySQL 8.4 — InnoDB Error Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html): deadlock rollback toàn transaction, lock wait timeout mặc định statement-only.
- [MySQL 8.4 — How to Minimize and Handle Deadlocks](https://dev.mysql.com/doc/refman/8.4/en/innodb-deadlocks-handling.html): lock ordering, transaction duration và retry.
- [Microsoft JDBC Driver for SQL Server](https://learn.microsoft.com/en-us/sql/connect/jdbc/microsoft-jdbc-driver-for-sql-server): driver/version-specific exception mapping và connection/retry capabilities.

**Ghi nhớ:** `SQLTransactionRollbackException` là tín hiệu JDBC về một nhóm lỗi rollback transaction, **không phải giấy phép retry vô điều kiện**. Muốn retry an toàn, phải biết **SQLState/vendor code và phạm vi rollback của DBMS**, **đặt retry bên ngoài transaction boundary**, chạy lại **toàn bộ reads/decisions/writes**, dùng giới hạn/backoff/deadline, và xử lý riêng những trường hợp **commit outcome chưa rõ** hoặc có tác dụng phụ ngoài DB.
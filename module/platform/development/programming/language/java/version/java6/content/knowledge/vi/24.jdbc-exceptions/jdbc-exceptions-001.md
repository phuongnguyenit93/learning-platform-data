# Ngoại lệ JDBC: SQLTransientException, SQLNonTransientException và SQLRecoverableException

## Mục tiêu học tập

**SQLException** là ngoại lệ trung tâm của JDBC. Khi một câu SQL hoặc thao tác Connection thất bại, ứng dụng không chỉ cần biết **nguyên nhân** mà còn cần quyết định **dừng, thử lại thao tác, hay tái tạo connection và transaction**. JDBC phân biệt ba nhóm ngoại lệ có ý nghĩa trực tiếp đối với chiến lược phục hồi:

- **SQLTransientException**: lỗi có thể biến mất khi thao tác được thử lại **mà ứng dụng không cần sửa nguyên nhân ở application level**.
- **SQLNonTransientException**: khi nguyên nhân chưa được sửa, thử lại cùng thao tác có xu hướng vẫn thất bại.
- **SQLRecoverableException**: thao tác có thể thành công sau khi ứng dụng thực hiện **recovery steps**. Theo API, tối thiểu phải **đóng Connection hiện tại, lấy Connection mới** rồi, nếu an toàn, **thực hiện lại toàn transaction** (hoặc nhánh distributed transaction).

**Cảnh báo trọng tâm:** Loại ngoại lệ nói về khả năng khôi phục ở tầng JDBC, **không chứng minh việc phát lại một nghiệp vụ là an toàn**. Nếu client gửi COMMIT rồi mất kết nối trước khi nhận phản hồi, transaction có thể đã commit. Retry một khoản thanh toán hoặc một INSERT không có idempotency có thể gây tác động hai lần.

Sau bài, bạn có thể:

1. Đọc đúng **cây phân cấp JDBC exception** và các subclass thường gặp.
2. Phân biệt **retry operation** với **replay toàn transaction** và **reconnect**.
3. Hiểu **SQLState, vendor error code, getNextException(), getCause(), getSuppressed()**.
4. Tránh suy sai rằng **SQLState class 08 luôn là transient**.
5. Biết vì sao **SQLTransactionRollbackException** cần transaction boundary thích hợp.
6. Đánh giá **idempotency**, commit outcome ambiguity, external side effects trước retry.
7. Viết policy có **bounded attempts, backoff, jitter, deadline, cancellation, connection cleanup**.
8. Biên dịch/chạy ví dụ **Java 17+** độc lập mô phỏng ba nhóm ngoại lệ bằng các JDBC dynamic proxies.
9. Phân biệt một mô phỏng Java đã kiểm thử với hành vi cần xác minh trên database driver/server thực tế.

**Phiên bản hiện hành:** Các API thuộc **java.sql** còn được hỗ trợ trên Java 17+ và Java SE 26. Mẫu runnable trong bài đã được kiểm thử trên **OpenJDK 24.0.2**, dùng **javac --release 17**. Chỉ sử dụng kiến thức đang áp dụng.

## 1. Cây phân cấp ngoại lệ JDBC

~~~text
java.lang.Exception
  └── java.sql.SQLException
      ├── SQLTransientException
      │   ├── SQLTimeoutException
      │   ├── SQLTransactionRollbackException
      │   └── SQLTransientConnectionException
      │
      ├── SQLNonTransientException
      │   ├── SQLDataException
      │   ├── SQLFeatureNotSupportedException
      │   ├── SQLIntegrityConstraintViolationException
      │   ├── SQLInvalidAuthorizationSpecException
      │   ├── SQLNonTransientConnectionException
      │   └── SQLSyntaxErrorException
      │
      ├── SQLRecoverableException
      │
      ├── BatchUpdateException
      ├── SQLClientInfoException
      ├── SQLWarning
      └── các nhánh khác
~~~

Ba nhóm chính là **ba nhánh con trực tiếp của SQLException**, không phải SQLRecoverableException là subclass của SQLTransientException. Bởi vậy code chỉ bắt **SQLTransientException** sẽ không tự động bắt lỗi **SQLRecoverableException**.

**BatchUpdateException**, **SQLClientInfoException** và **SQLWarning** cũng không tự nằm trong ba nhóm. Đặc biệt, SQLWarning thường được truy xuất qua **Statement.getWarnings()** hoặc **Connection.getWarnings()**, không nên xử lý như một request error phải retry.

### 1.1. So sánh nhanh

| Class | Ý nghĩa | Quyết định mặc định nên cân nhắc |
| --- | --- | --- |
| **SQLTransientException** | Có thể thành công sau khi thử lại nếu điều kiện tạm thời qua đi | Chỉ retry nếu operation repeatable và còn deadline/budget |
| **SQLNonTransientException** | Cùng thao tác có khả năng lỗi lại nếu không sửa nguyên nhân | Dừng; sửa SQL, data, permission, schema hoặc driver |
| **SQLRecoverableException** | Cần app-level recovery, ít nhất connection mới | Đóng connection cũ; khôi phục state và replay cả transaction nếu an toàn |
| **SQLException chưa phân loại** | Chưa đủ thông tin để tự động retry | Dừng, thu thập SQLState/vendor code và driver docs |
| **SQLWarning** | Thông tin cảnh báo | Xử lý warning chain, không coi là quyết định retry tự động |

### 1.2. Cùng tên lỗi, nghiệp vụ vẫn có thể khác

Hai service có thể nhận cùng SQLTransientException nhưng hành động hợp lý khác nhau. Một **SELECT thuần** (không side effect) thường có thể retry trong budget. Một **UPDATE balance = balance + 100** thì không được bắn lại nếu không biết lần trước đã commit hay chưa.

Vì thế, quyết định retry có hai tầng: **khả năng phục hồi của JDBC** và **tính an toàn để lặp lại của nghiệp vụ**.

## 2. SQLTransientException: lỗi có thể hết khi thử lại

**SQLTransientException extends SQLException**. Theo Javadoc, nó mô tả lỗi mà thao tác trước đó **có thể** thành công nếu được thử lại **không cần application-level intervention** để thay đổi nguyên nhân.

Từ khóa là **“có thể”**, không phải “chắc chắn”. Transient không có nghĩa thử lại vô hạn, và cũng không tự chứng minh transaction cũ còn hợp lệ.

### 2.1. Các subclass trực tiếp

| Subclass | Thường thể hiện | Điều phải kiểm tra |
| --- | --- | --- |
| **SQLTimeoutException** | Query/login timeout theo những JDBC timeout APIs liên quan | Statement có thể đã gây side effect; còn deadline không? |
| **SQLTransactionRollbackException** | Transaction rollback, như serialization/deadlock theo driver | Có phải replay toàn transaction thay vì statement cuối? |
| **SQLTransientConnectionException** | Lỗi kết nối được driver đánh giá là tạm thời | Connection có còn khỏe hay cần tạo mới? |

**SQLTimeoutException** có thể xảy ra khi query vượt ngưỡng, server quá tải hoặc network chậm. Nếu câu SQL cố định luôn mất vài phút trong khi timeout 1 giây, retry nhiều lần chỉ tốn tài nguyên; cần sửa query/cấu hình trước.

**SQLTransactionRollbackException** thường liên quan SQLState class **40**. Khi transaction bị rollback, những bước thành công trước trong cùng transaction cũng không còn tồn tại; đừng retry riêng statement cuối mà bỏ qua toàn bộ business context.

**SQLTransientConnectionException** có thể dùng SQLState class **08**, nhưng không phải mọi lỗi class 08 transient: JDBC có cả **SQLNonTransientConnectionException**.

### 2.2. Ví dụ deadlock/serialization conflict

~~~text
BEGIN transaction
  1. SELECT dữ liệu cần đọc
  2. UPDATE số lượng tồn kho
  3. INSERT order / outbox record
COMMIT
~~~

Khi transaction bị rollback do serialization conflict ở bước 3, cách làm đúng nếu operation repeatable là:

1. Kết thúc scope transaction đã lỗi.
2. Chờ một backoff phù hợp nếu cần.
3. Bắt đầu transaction mới.
4. Chạy lại **toàn workflow** có cùng input và idempotency policy.
5. Commit và kiểm tra business result.

Không gửi lại duy nhất bước INSERT vào transaction đã rollback và mong hệ thống đúng.

### 2.3. Timeout không chứng minh server chưa làm gì

~~~text
Client gửi UPDATE hoặc COMMIT
            │
            ▼
Server có thể đã thực hiện/commit
            │
Client timeout/mất kết nối trước phản hồi
            │
            ▼
Client chưa biết chắc kết quả thực tế
~~~

Nếu lặp lại thao tác không idempotent, có thể có **double insert, double charge hoặc duplicate event**. Timeout chỉ là một tín hiệu lỗi, không phải chứng từ rollback.

## 3. SQLNonTransientException: cần sửa nguyên nhân

**SQLNonTransientException extends SQLException**. Class này thể hiện rằng nếu chưa sửa nguyên nhân, **lặp lại y nguyên** operation sẽ không giải quyết vấn đề theo phân loại JDBC.

| Subclass | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **SQLSyntaxErrorException** | Query sai cú pháp/cột không có hoặc violation do driver quy định | Sửa query/schema/query builder |
| **SQLIntegrityConstraintViolationException** | Unique/FK/check constraint | Sửa dữ liệu hoặc đối chiếu idempotency |
| **SQLDataException** | Conversion, overflow, dữ liệu không hợp lệ | Validate input/type mapping |
| **SQLInvalidAuthorizationSpecException** | Account/quyền/cấu hình authorization không đúng | Sửa credentials/permissions, không log secret |
| **SQLFeatureNotSupportedException** | Driver/API/DBMS không hỗ trợ feature | Chọn cách được hỗ trợ hoặc nâng driver |
| **SQLNonTransientConnectionException** | Connection lỗi bởi nguyên nhân không tự hết | Sửa endpoint/TLS/auth/config hoặc phần liên quan |

**Non-transient không có nghĩa vĩnh viễn.** Sau khi deploy migration hoặc cấp đúng quyền, operation có thể thành công. Nó có nghĩa **đừng retry khi cùng nguyên nhân chưa đổi**.

### 3.1. Cú pháp sai không tự hết

~~~java
// Mảnh minh họa, không phải file Java độc lập.
try (PreparedStatement ps = connection.prepareStatement(
        "SELEC label FROM widgets")) {
    ps.executeQuery();
} catch (SQLSyntaxErrorException e) {
    // Không lặp lại cùng câu sai chỉ vì còn retry budget.
    throw e;
}
~~~

Không có backoff nào tự sửa **SELEC** thành **SELECT**.

### 3.2. Vi phạm unique constraint và idempotency

Một INSERT với idempotency key có thể bị **unique constraint violation** vì lần yêu cầu trước đã hoàn tất. Trường hợp đó có thể xử lý bằng **status query và so sánh kết quả** theo contract, thay vì retry INSERT. Phân biệt rõ “trả kết quả cũ cho yêu cầu trùng” với “thử chạy lại thao tác ghi”.

## 4. SQLRecoverableException: khôi phục Connection và cả transaction

**SQLRecoverableException extends SQLException trực tiếp**. Javadoc Java SE 26 mô tả lỗi mà operation có thể thành công nếu ứng dụng thực hiện **các bước recovery**, sau đó replay **toàn transaction** hoặc **nhánh transaction** trong distributed transaction.

**Tối thiểu:** **close connection hiện tại, acquire một connection mới**. Không tiếp tục dùng cùng physical session hoặc PreparedStatement cũ và gọi execute lần nữa.

~~~text
SQLRecoverableException
     │
     ▼
Đóng/loại bỏ connection lỗi
     │
     ▼
Nhận connection mới từ pool/DataSource
     │
     ▼
Thiết lập transaction và session state cần thiết
     │
     ▼
Nếu outcome commit chưa rõ: reconcile trước
     │
     ▼
Replay toàn transaction khi an toàn
~~~

Đóng connection giúp phục hồi khả năng truy cập DB, **không chứng minh rằng transaction cũ đã rollback**.

### 4.1. Tình huống COMMIT có kết quả không xác định

Giả sử một thanh toán:

~~~text
1. INSERT payment event
2. UPDATE balance
3. COMMIT gửi tới DB
4. DB có thể đã COMMIT
5. Connection mất trước khi client nhận ACK
~~~

Mở connection mới chỉ giúp bạn kiểm tra/truy cập hệ thống trở lại; không tự trả lời **“payment đã hoàn thành chưa?”**. Nếu bắn lại whole transaction khi chưa có idempotency, có nguy cơ tạo tác động lần hai.

Cần thiết kế **idempotency key, unique constraint, operation-status query, reconciliation, transactional outbox** hoặc cơ chế tương đương, rồi mới quyết định có replay hay trả kết quả cũ.

### 4.2. State cần xây lại trên Connection mới

Connection mới có thể không giữ:

- Auto-commit, transaction isolation, schema/catalog, read-only settings.
- Temporary tables, session variables, tenant context.
- Prepared statements, cursors, ResultSet, JDBC LOB locators.
- Client-info metadata phục vụ diagnostics.
- Locks và những hiệu ứng session-local.
- State do XA/JTA transaction coordinator quản lý.

Không tự ý copy mọi state từ connection lỗi; dùng pool/transaction-manager configuration theo ownership. **Không chuyển ResultSet/PreparedStatement từ Connection cũ sang Connection mới**.

### 4.3. Distributed transactions

Với XA/JTA, Javadoc đề cập **transaction branch**. Khôi phục giao dịch phân tán là công việc của transaction manager/coordinator theo recovery protocol. Không bắt recoverable rồi tạo nhánh XA mới bừa bãi, vì kết quả nhánh trước có thể đã commit hoặc đang ở trạng thái in-doubt.

## 5. Retry phải an toàn ở cấp nghiệp vụ

Hỏi câu quan trọng trước mọi retry: **“Nếu lần trước đã chạy thành công ở server nhưng response mất, lần này có tạo tác động ngoài ý muốn không?”**

| Operation | Chính sách an toàn sơ bộ | Lý do |
| --- | --- | --- |
| SELECT thuần, side-effect-free | Có thể retry có giới hạn | Không mutation; kết quả có thể đổi theo thời điểm |
| SELECT gọi function ghi dữ liệu | Không mặc định | Dù tên là SELECT vẫn có thể tác động |
| UPDATE balance = balance + 100 | Không blind retry | Có thể cộng hai lần |
| INSERT tạo UUID mới mỗi attempt | Không blind retry | Có thể tạo duplicate logical records |
| INSERT có idempotency key và dedupe | Có thể thiết kế retry/reconcile | Bắt buộc đối chiếu kết quả và uniqueness |
| UPDATE đặt giá trị tuyệt đối | Còn tùy | Trigger/outbox/audit vẫn có thể chạy lặp |
| COMMIT timeout/lost response | Không blind retry | Commit outcome unknown |
| Transaction chắc chắn rollback và workflow repeatable | Có thể retry **cả transaction** | Vẫn cần kiểm soát external side effects |
| Gửi email/payment API trước DB commit | Không blind retry whole workflow | Side effect bên ngoài có thể đã xảy ra |

Đừng dựa trên dạng SQL để kết luận hoàn toàn idempotent. Trigger, CDC, audit hoặc business events có thể xuất hiện dù SQL statement trông đơn giản.

### 5.1. Những công cụ giúp an toàn

- **Idempotency key** duy nhất theo business request.
- **Unique constraint** với deduplication/result lookup.
- **Transactional outbox** cho việc phát sự kiện liên quan đến DB.
- **Reconciliation query** sau connection loss.
- **Operation state machine** (pending/completed/failed).
- **At-least-once delivery và idempotent consumer** cho message processing.
- **Tách canonical business data khỏi localized/log strings**, không dùng text message để xác định kết quả transaction.

Đây là trách nhiệm application-level, không phải chức năng tự động của SQLException.

## 6. SQLState, vendor code, cause và next exception

Một SQLException thường có nhiều thông tin:

~~~java
// Mảnh minh họa trong catch (SQLException ex).
String sqlState = ex.getSQLState();
int vendorCode = ex.getErrorCode();
String message = ex.getMessage();
Throwable cause = ex.getCause();
SQLException next = ex.getNextException();
Throwable[] suppressed = ex.getSuppressed();
~~~

**SQLState** theo X/Open hoặc SQL standard conventions; có thể là null. **Vendor code** phụ thuộc DBMS/driver, không portable giữa các hãng. **Message** phục vụ diagnostics nhưng không là contract để parse, có thể chứa input/table/parameter nhạy cảm.

**getNextException()** khác **getCause()**: nó là một linked chain các SQLException. **getSuppressed()** có thể chứa exception khi try-with-resources đóng resources trong lúc một lỗi chính đang được ném.

### 6.1. SQLState class thường liên quan

| Hai ký tự đầu | Nhóm thường gặp | JDBC subclass |
| --- | --- | --- |
| **08** | Connection exception | SQLTransientConnectionException **hoặc** SQLNonTransientConnectionException |
| **40** | Transaction rollback | SQLTransactionRollbackException |
| **42** | Syntax/access rule | SQLSyntaxErrorException |
| **23** | Integrity constraint | SQLIntegrityConstraintViolationException |
| **22** | Data exception | SQLDataException |
| **28** | Authorization specification | SQLInvalidAuthorizationSpecException |
| **0A** | Unsupported feature | SQLFeatureNotSupportedException |

**Không có quy tắc rằng SQLState bắt đầu bằng 08 thì luôn retry được.** Các class connection exceptions có thể khác nhau dù cùng SQLState class. Một JDBC driver cũng có thể ném **SQLException generic** hoặc sử dụng code vendor-specific thay vì Java subtype mong đợi.

Các giá trị **08006, 08001, 40001, 42000, HY000, HYT00** trong chương trình demo là giá trị **mô phỏng xác định**, không phải cam kết mọi database trả đúng cùng mã.

### 6.2. Xem next-exception chain

~~~java
// Mảnh minh họa với SQLException ex.
for (SQLException e = ex; e != null; e = e.getNextException()) {
    System.err.println("SQLState=" + e.getSQLState()
            + ", vendorCode=" + e.getErrorCode());
}
~~~

Khi áp dụng production, giới hạn số phần tử và guard trường hợp chain lặp bất thường, không log SQL parameters/password/PII. Không thấy một lỗi transient ở next chain rồi quyết định blind retry nếu primary exception hoặc commit outcome chưa rõ.

### 6.3. Không parse message để retry

~~~java
// Mã sai về policy, chỉ minh họa điều cần tránh.
if (ex.getMessage().contains("timeout")) {
    runMutationAgain();
}
~~~

Exception message có thể localized hoặc đổi theo vendor. “Timeout” không nói rõ server đã COMMIT hay chưa. Ưu tiên runtime subtype, SQLState/vendor mapping được test, và **safe-to-repeat policy** của nghiệp vụ.

## 7. Bounded retry, backoff và pool discipline

Một policy production cần:

1. **Safe-to-repeat** do business contract xác nhận.
2. **Transaction owner** có quyền retry toàn workflow.
3. **Classification** theo subclass, không chỉ string message.
4. **Connection health** và recovery đúng khi recoverable.
5. **maxAttempts** tính cả lần đầu.
6. **End-to-end deadline** (request/SLA budget).
7. **Exponential backoff + jitter**, không busy loop.
8. **Cancellation/interrupt** được bảo toàn.
9. **Resource cleanup** bằng try-with-resources và pool APIs.
10. **Observability** theo type, SQLState, count, duration mà không lộ data.
11. **Driver-specific mapping** được xác minh trên server/version.
12. **Default STOP** cho unknown errors.
13. **Circuit breaker/concurrency controls** để tránh retry storm.

~~~text
Operation repeatable
        │
        ▼
Attempt 1 với Connection mới
        │
      success ───> RETURN
        │ error
        ▼
Đóng ResultSet/Statement/Connection
        │
        ▼
Classify JDBC error + kiểm tra business safety
        │
  ┌─────┼────────────────────────┐
  ▼     ▼                        ▼
Transient Recoverable      NonTransient/Unknown
  │     │                        │
  └──┬──┘                        └──> STOP
     │
     ▼
Còn deadline, budget, chưa cancel?
     │
 no ─┴───> STOP
     │ yes
     ▼
Backoff+jitter → new attempt
~~~

### 7.1. Backoff minh họa

~~~java
// Mảnh minh họa; cần import ThreadLocalRandom.
static void pauseBeforeRetry(int retryNumber) throws InterruptedException {
    int shift = Math.min(Math.max(retryNumber - 1, 0), 4);
    long upperBound = Math.min(1_000L, 50L << shift);
    long millis = java.util.concurrent.ThreadLocalRandom.current()
            .nextLong(upperBound + 1);
    Thread.sleep(millis);
}
~~~

Ví dụ này **chưa có deadline/cancellation check** và không được gọi trong chương trình kiểm thử chính để stdout deterministic. Nếu thread bị interrupt, cần propagate/re-interrupt theo service contract. Khi nhiều clients cùng lỗi, jitter/backpressure giúp tránh tất cả cùng gửi query một lúc.

### 7.2. Recoverable bắt buộc làm mới connection

Connection.close() trong connection pool thường **trả logical handle về pool**, không nhất thiết đóng socket vật lý. Với SQLRecoverableException, cần bảo đảm **connection vật lý hỏng không bị phát lại** qua pool error handling hoặc API eviction/invalidation thích hợp.

Một test double đếm Connection.close **không chứng minh** pool thật đã loại physical session. Cần integration test với JDBC driver và pool thực tế.

## 8. Ví dụ Java 17+ chạy độc lập

Chương trình sau dùng **dynamic proxies cho Connection, PreparedStatement và ResultSet** để tạo một **test double** không cần DBMS, JDBC URL, credentials hay JAR bên ngoài. Nó không chạy SQL thật, không mô phỏng transaction/COMMIT; chỉ mô phỏng lỗi ở **executeQuery()** của một **SELECT được giả định side-effect-free**.

Nó kiểm tra recoverable/reconnect, transient rollback, timeout, nontransient syntax error, SQLException generic, exhausted attempts, cùng SQLState với Java classes khác nhau, safe-to-repeat flag, SQLException chaining và số connection đã đóng.

**Quan trọng:** Không sao chép vòng retry SELECT này vào INSERT/UPDATE/COMMIT. Nó cũng chưa thêm retry delays/deadline; những phần đó đã được giải thích ở trên.

### 8.1. File JdbcExceptionPolicyDemo.java

~~~java
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

public final class JdbcExceptionPolicyDemo {
    enum Decision { RECONNECT, RETRY, STOP }

    @FunctionalInterface
    interface ConnectionFactory {
        Connection open() throws SQLException;
    }

    static Decision decide(SQLException problem, boolean repeatIsSafe) {
        if (!repeatIsSafe) return Decision.STOP;
        if (problem instanceof SQLRecoverableException) return Decision.RECONNECT;
        if (problem instanceof SQLTransientException) return Decision.RETRY;
        // Includes SQLNonTransientException and unclassified SQLException.
        return Decision.STOP;
    }

    // Only for a genuinely side-effect-free, repeatable SELECT.
    // No writes or ambiguous commit are ever retried here.
    static String readWithRetries(ConnectionFactory factory, long id, int maxAttempts)
            throws SQLException {
        if (maxAttempts < 1) throw new IllegalArgumentException("maxAttempts");
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try (Connection connection = factory.open();
                 PreparedStatement ps = connection.prepareStatement(
                         "SELECT label FROM widgets WHERE id = ?")) {
                ps.setLong(1, id);
                try (ResultSet rs = ps.executeQuery()) {
                    return rs.next() ? rs.getString(1) : null;
                }
            } catch (SQLException failure) {
                Decision decision = decide(failure, true);
                if (decision == Decision.STOP || attempt == maxAttempts) {
                    System.out.println("stop attempt=" + attempt
                            + " kind=" + decision
                            + " state=" + failure.getSQLState());
                    throw failure;
                }
                // The previous connection has been closed by try-with-resources.
                // A new one is acquired at the start of the next attempt.
                System.out.println("retry attempt=" + attempt
                        + " kind=" + decision
                        + " state=" + failure.getSQLState());
                // In production: bounded exponential backoff + jitter + deadline.
            }
        }
        throw new AssertionError("unreachable");
    }

    public static void main(String[] args) throws SQLException {
        ScriptedFactory recoverable = new ScriptedFactory(
                new SQLRecoverableException("Session lost", "08006", 1001));
        System.out.println("recoverableResult="
                + readWithRetries(recoverable, 42, 3));
        System.out.println("recoverableConnections="
                + recoverable.opened + "/" + recoverable.closed);

        ScriptedFactory transientFailure = new ScriptedFactory(
                new SQLTransactionRollbackException(
                        "Serialization conflict", "40001", 1213));
        System.out.println("transientResult="
                + readWithRetries(transientFailure, 42, 3));
        System.out.println("transientConnections="
                + transientFailure.opened + "/" + transientFailure.closed);

        ScriptedFactory timeout = new ScriptedFactory(
                new SQLTimeoutException("Query timed out", "HYT00", 3));
        System.out.println("timeoutResult="
                + readWithRetries(timeout, 42, 2));

        ScriptedFactory nontransient = new ScriptedFactory(
                new SQLSyntaxErrorException("Bad SQL", "42000", 1064));
        try {
            readWithRetries(nontransient, 42, 3);
        } catch (SQLSyntaxErrorException e) {
            System.out.println("nontransientState=" + e.getSQLState());
        }
        System.out.println("nontransientConnections="
                + nontransient.opened + "/" + nontransient.closed);

        ScriptedFactory unknown = new ScriptedFactory(
                new SQLException("Unclassified", "HY000", 77));
        try {
            readWithRetries(unknown, 42, 3);
        } catch (SQLException e) {
            System.out.println("unknownState=" + e.getSQLState());
        }

        ScriptedFactory exhausted = new ScriptedFactory(
                new SQLTransactionRollbackException("Conflict 1", "40001"),
                new SQLTransactionRollbackException("Conflict 2", "40001"),
                new SQLTransactionRollbackException("Conflict 3", "40001"));
        try {
            readWithRetries(exhausted, 42, 3);
        } catch (SQLTransactionRollbackException e) {
            System.out.println("exhaustedState=" + e.getSQLState());
        }
        System.out.println("exhaustedConnections="
                + exhausted.opened + "/" + exhausted.closed);

        System.out.println("state08Transient=" + decide(
                new SQLTransientConnectionException("Busy", "08001"), true));
        System.out.println("state08NonTransient=" + decide(
                new SQLNonTransientConnectionException("Bad config", "08001"), true));
        System.out.println("unsafeRecoverable=" + decide(
                new SQLRecoverableException("Commit outcome unknown", "08006"), false));

        SQLException primary = new SQLException("Primary", "HY000", 1);
        primary.setNextException(new SQLException("Secondary", "01000", 2));
        System.out.println("nextExceptionState="
                + primary.getNextException().getSQLState());
    }

    // Deterministic JDBC test double; does not contact a database.
    static final class ScriptedFactory implements ConnectionFactory {
        final SQLException[] failures;
        int opened;
        int closed;
        ScriptedFactory(SQLException... failures) {
            this.failures = failures;
        }

        @Override
        public Connection open() {
            int current = opened++;
            SQLException scripted = current < failures.length
                    ? failures[current] : null;
            boolean[] isClosed = {false};
            return (Connection) Proxy.newProxyInstance(
                    JdbcExceptionPolicyDemo.class.getClassLoader(),
                    new Class<?>[] {Connection.class},
                    (proxy, method, args) -> {
                        switch (method.getName()) {
                            case "prepareStatement":
                                return statement(scripted);
                            case "close":
                                if (!isClosed[0]) {
                                    isClosed[0] = true;
                                    closed++;
                                }
                                return null;
                            case "isClosed":
                                return isClosed[0];
                            default:
                                throw new SQLFeatureNotSupportedException(
                                        "Not implemented in fake: " + method.getName());
                        }
                    });
        }

        static PreparedStatement statement(SQLException scripted) {
            return (PreparedStatement) Proxy.newProxyInstance(
                    JdbcExceptionPolicyDemo.class.getClassLoader(),
                    new Class<?>[] {PreparedStatement.class},
                    (proxy, method, args) -> {
                        switch (method.getName()) {
                            case "setLong":
                            case "close":
                                return null;
                            case "executeQuery":
                                if (scripted != null) throw scripted;
                                return resultSet();
                            default:
                                throw new SQLFeatureNotSupportedException(
                                        "Not implemented in fake: " + method.getName());
                        }
                    });
        }

        static ResultSet resultSet() {
            boolean[] next = {true};
            return (ResultSet) Proxy.newProxyInstance(
                    JdbcExceptionPolicyDemo.class.getClassLoader(),
                    new Class<?>[] {ResultSet.class},
                    (proxy, method, args) -> {
                        switch (method.getName()) {
                            case "next":
                                if (next[0]) {
                                    next[0] = false;
                                    return true;
                                }
                                return false;
                            case "getString":
                                return "widget-42";
                            case "close":
                                return null;
                            default:
                                throw new SQLFeatureNotSupportedException(
                                        "Not implemented in fake: " + method.getName());
                        }
                    });
        }
    }
}
~~~

### 8.2. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 17 JdbcExceptionPolicyDemo.java
java JdbcExceptionPolicyDemo
~~~

Windows PowerShell cũng sử dụng hai lệnh như trên. Chương trình không cần DataSource, JDBC URL, database server hoặc thư viện ngoài JDK.

### 8.3. Stdout chính xác đã kiểm chứng

~~~text
retry attempt=1 kind=RECONNECT state=08006
recoverableResult=widget-42
recoverableConnections=2/2
retry attempt=1 kind=RETRY state=40001
transientResult=widget-42
transientConnections=2/2
retry attempt=1 kind=RETRY state=HYT00
timeoutResult=widget-42
stop attempt=1 kind=STOP state=42000
nontransientState=42000
nontransientConnections=1/1
stop attempt=1 kind=STOP state=HY000
unknownState=HY000
retry attempt=1 kind=RETRY state=40001
retry attempt=2 kind=RETRY state=40001
stop attempt=3 kind=RETRY state=40001
exhaustedState=40001
exhaustedConnections=3/3
state08Transient=RETRY
state08NonTransient=STOP
unsafeRecoverable=STOP
nextExceptionState=01000
~~~

**Đã so khớp chính xác 22 dòng stdout** sau khi compile trên OpenJDK 24.0.2 với **--release 17**. Đây là kết quả **JDBC test double**, không phải output của database thật.

### 8.4. Diễn giải các trường hợp

**Recoverable:** attempt 1 ném SQLRecoverableException (08006). Handler phân loại **RECONNECT**, đóng Connection cũ và lấy Connection mới ở lần sau, rồi nhận widget-42. **recoverableConnections=2/2** xác minh cleanup trong fake.

**Transient rollback:** attempt 1 ném SQLTransactionRollbackException (40001). Operation SELECT an toàn nên retry thành công; **transientConnections=2/2**.

**Timeout:** SQLTimeoutException (HYT00) được phân loại RETRY cho read-only operation. Một timeout của UPDATE/COMMIT có thể có outcome khác nên không được suy rộng.

**Non-transient:** SQLSyntaxErrorException (42000) dừng ngay lần 1. **nontransientConnections=1/1** xác minh Connection được đóng.

**Unknown:** SQLException generic HY000 dừng theo default STOP; không retry chỉ vì thông báo lỗi nghe có vẻ tạm thời.

**Retry exhaustion:** Ba transient errors liên tiếp dẫn tới retry sau attempt 1 và 2; attempt 3 kết thúc lỗi, không có attempt thứ tư.

**Same SQLState, different class:** Cùng 08001, transient connection trả RETRY còn nontransient connection trả STOP.

**Unsafe operation:** Nếu flag repeatIsSafe=false, policy trả STOP ngay cả với SQLRecoverableException.

**Next-exception:** SQLException thứ hai trong chain có SQLState 01000, được truy cập qua getNextException.

## 9. Tích hợp DataSource thật

Với một DataSource và bảng widgets(id,label) có thật:

~~~java
// Mảnh minh họa trong cùng package; DataSource dataSource đã được cấu hình.
String result = JdbcExceptionPolicyDemo.readWithRetries(
        dataSource::getConnection, 42L, 3);
~~~

**Chỉ dùng cho SELECT thực sự side-effect-free.** Helper mẫu mở/đóng Connection ở mỗi attempt, không xử lý transaction ghi, COMMIT, outbox hay distributed transaction; nó cũng chưa thực thi backoff/deadline trong code chạy chính.

Đối với transaction nhiều statement, retry phải nằm ở **service/transaction coordinator**:

1. Bắt đầu transaction mới theo owner.
2. Chạy lại **toàn workflow**, không riêng statement cuối.
3. Nếu rollback được xác định rõ, có thể replay khi business repeatable.
4. Nếu connection recoverable, đóng session lỗi và lấy connection mới.
5. Nếu COMMIT outcome chưa rõ, reconcile/idempotency trước.
6. Với JTA/XA, để transaction manager quản lý branch recovery.
7. Không copy Connection/ResultSet/PreparedStatement/LOB locator đã lỗi.
8. Khi rollback/close cũng ném lỗi, giữ nguyên exception gốc, gắn suppressed hoặc ghi cleanup error theo policy.

## 10. BatchUpdateException và kết quả một phần

**BatchUpdateException extends SQLException trực tiếp**, không mặc nhiên là một trong ba nhóm. Nó có **getUpdateCounts()** mô tả kết quả các lệnh trong batch.

~~~java
// Mảnh minh họa bên trong catch (BatchUpdateException e).
int[] counts = e.getUpdateCounts();
// Diễn giải theo JDBC/vendor contract; không tự xem cả batch atomic.
~~~

Driver có thể tiếp tục hoặc dừng ở phần tử lỗi theo cách triển khai; auto-commit, transaction mode, savepoints và side effects còn ảnh hưởng trạng thái cuối. Không retry nguyên batch nếu vài statement đã thành công trước khi error xảy ra, trừ khi thiết kế idempotency/transaction chứng minh an toàn.

Với **SQLRecoverableException từ COMMIT**, thậm chí có thể không biết trạng thái toàn bộ batch; cần query/reconcile theo business key.

## 11. Connection pooling và lỗi giữa quá trình cleanup

Connection.close() trên logical connection của pool thường chỉ **trả handle**, không bảo đảm socket vật lý bị đóng. Khi nhận SQLRecoverableException, cần xác minh pool phát hiện connection hỏng và **evict/invalidate physical session** theo API được hỗ trợ.

Để triển khai chắc chắn:

- Không dùng lại connection cũ khi đã recoverable.
- Để DataSource/pool quản lý acquisition, monitoring và eviction.
- Không gọi abort/close physical session bừa bãi ngoài contract pool.
- Giới hạn retries và concurrency để tránh làm cạn pool.
- Khi Statement.close/Connection.close ném SQLException, giữ thông tin primary + suppressed.
- Nếu không thể bảo đảm session state sạch, không phát lại session nghi ngờ cho request tiếp theo.
- Kiểm tra pool/version-specific SQLState mapping bằng integration test.

## 12. Lỗi thường gặp và cách khắc phục

| Vấn đề | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Bắt SQLException rồi retry mọi lỗi | Data duplicate và DB quá tải | Classify + business safety |
| Chỉ bắt SQLTransientException | Bỏ sót recoverable errors | Nhớ 3 nhánh cùng cấp |
| Recoverable nhưng dùng Connection cũ | Session vẫn có thể hỏng | Đóng/lấy connection mới |
| Recoverable nhưng chỉ chạy lại statement cuối | Transaction state thiếu | Replay toàn transaction nếu an toàn |
| Transaction rollback nhưng dùng lại transaction cũ | Workflow sai | Tạo transaction mới |
| Retry SQL syntax error | Lặp bug và tăng tải | Sửa query/schema |
| Retry update khi COMMIT ACK mất | Có thể ghi hai lần | Idempotency/reconciliation |
| Mọi SQLState 08 được xem transient | Retry lỗi cấu hình vô ích | Java subtype + vendor mapping |
| Chỉ parse message “timeout” | Quyết định sai | SQLState/type, safety policy |
| Retry generic SQLException | Che unknown root cause | Default STOP |
| Không có maxAttempts/deadline | Request treo, retry storm | Budget/deadline/backoff |
| Không có jitter | Load spike đồng loạt | Jitter/circuit breaker |
| Nuốt InterruptedException | Request bị hủy vẫn chạy | Propagate/re-interrupt |
| Không đóng resource trước attempt mới | Connection leak | try-with-resources |
| Pool close bị hiểu là physical eviction | Tái dùng session hỏng | Test pool invalidate |
| Batch retry bỏ qua updateCounts | Duplicate partial work | Phân tích batch outcome |
| Log nguyên SQLException message và SQL parameters | Rò data/PII | Redaction/sanitized codes |
| Unit test fake pass nhưng driver thật khác | Production bug | Integration tests với driver thật |

## 13. Integration test với DBMS/driver thật

| Test | Kết quả cần xác minh |
| --- | --- |
| Syntax error | Subclass, SQLState/vendor code và fail fast |
| Unique constraint | Correct mapping, idempotency policy |
| Serialization conflict/deadlock | Transaction rollback và whole-transaction replay |
| Query timeout | Connection validity/cancellation/side effects |
| Connection outage | Recoverable hay transient/nontransient mapping của driver |
| Pool eviction | Broken physical session không được tái sử dụng |
| SQLState class 08 | Không mặc định mọi state 08 transient |
| Connection acquisition failure | Budget/deadline và pool saturation |
| COMMIT response lost | Reconciliation/idempotency của nghiệp vụ |
| Batch partial failure | Update counts và transaction boundaries |
| XA recovery | Coordinator/branch semantics |
| Suppressed exceptions | Root cause được giữ khi cleanup fail |
| Concurrent clients retry | Jitter, throttling, circuit breaker |
| Vendor upgrade | Mapping thay đổi khi driver/DBMS đổi phiên bản |

**Không chủ động tạo network failover, database outage hoặc commit ambiguity trên production để học bài.** Dùng database test và fault injection có kiểm soát.

### 13.1. Kiểm thử commit outcome mơ hồ

1. Tạo một operation key duy nhất.
2. Gửi transaction ghi, mô phỏng mất phản hồi ngay sau thời điểm COMMIT có thể thành công.
3. Mở connection mới qua recovery.
4. Query theo operation key để xác định trạng thái.
5. Nếu kết quả đã tồn tại, trả lại kết quả cũ; nếu chưa, dùng retry có deduplication.
6. Xác minh không có hai payments, hai orders hay hai outbox events cho cùng logical operation.
7. Ghi metrics về outcome nhưng không log secrets.

## 14. Bài tập tự luyện

1. Biên dịch/chạy ví dụ, giải thích recoverableConnections=2/2.
2. Đổi SQLRecoverableException thành SQLTransientConnectionException với SQLState 08006; kiểm tra Decision.
3. Đổi SQLSyntaxErrorException thành SQLIntegrityConstraintViolationException và giải thích STOP.
4. Thay maxAttempts=3 thành 2 ở kịch bản exhausted; dự đoán opened/closed.
5. Thêm SQLTimeoutException cho SELECT safe rồi thử một operation có side effect để lý giải policy khác.
6. Kiểm tra hai subclasses khác nhau cùng SQLState 08001.
7. Thêm SQLException cause và nextException, viết helper chẩn đoán có giới hạn vòng lặp.
8. Cài đặt end-to-end deadline + exponential backoff + jitter.
9. Thêm cancellation/interruption propagation.
10. Thiết kế transaction runner replay toàn workflow sau serialization rollback.
11. Thiết kế idempotency table cho COMMIT response lost.
12. Tạo test pool connection invalidation khi SQLRecoverableException.
13. Mô phỏng BatchUpdateException với nhiều update counts khác nhau.
14. Viết vendor-specific mapping có default STOP và test đa phiên bản driver.
15. Thêm retry metrics/trace nhưng không ghi SQL parameters nhạy cảm.

## 15. Checklist production

- [ ] Phân biệt SQLTransientException, SQLNonTransientException, SQLRecoverableException và unknown.
- [ ] Không nhầm SQLRecoverableException là subclass của SQLTransientException.
- [ ] Safe-to-repeat được xác nhận bởi business operation, không theo tên class/SQL.
- [ ] Với mutation/COMMIT outcome unknown, có idempotency và reconciliation.
- [ ] SQLTransactionRollbackException được xử lý ở **transaction boundary**.
- [ ] SQLRecoverableException dẫn tới **đóng connection cũ, lấy mới**.
- [ ] Session/transaction state mới được thiết lập có chủ đích.
- [ ] Non-transient và unclassified SQLException mặc định không blind retry.
- [ ] SQLState/vendor mapping đã được kiểm chứng trên driver/version thật.
- [ ] Có bounded maxAttempts, tổng deadline, backoff và jitter.
- [ ] Cancellation/interrupt được tôn trọng.
- [ ] try-with-resources đảm bảo ResultSet/Statement/Connection cleanup.
- [ ] Connection pool có cơ chế invalidate broken connections.
- [ ] BatchUpdateException được xử lý theo updateCounts/partial result.
- [ ] Có tests cho deadlock, timeout, failover, commit ambiguity và XA nếu dùng.
- [ ] Không log secrets/PII/SQL parameters nhạy cảm.
- [ ] Không dùng demo fake thay integration test với database thật.
- [ ] Không dùng retry để che syntax, integrity, authorization hoặc schema bugs.

## Kết luận

**SQLTransientException** biểu đạt một lỗi có thể tạm thời hết khi retry, nhưng việc retry vẫn phải **an toàn theo nghiệp vụ**, có budget và deadline. **SQLNonTransientException** cần sửa nguyên nhân trước khi thử cùng operation. **SQLRecoverableException** yêu cầu **application-level recovery**: tối thiểu đóng Connection cũ, lấy Connection mới và chỉ replay toàn transaction/branch khi đã xác minh kết quả cũ và tính repeatable.

**Exception type, SQLState và vendor code là thông tin chẩn đoán, không phải giấy phép phát lại giao dịch ghi**. Với read-only SELECT không side effect, retry ngắn có thể hữu ích. Với payment/order/COMMIT không rõ outcome, ưu tiên idempotency, reconciliation và transaction ownership.

**Tài liệu chính thức hiện hành:**

- [SQLException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html)
- [SQLTransientException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransientException.html)
- [SQLNonTransientException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLNonTransientException.html)
- [SQLRecoverableException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLRecoverableException.html)
- [SQLTransactionRollbackException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransactionRollbackException.html)
- [SQLTimeoutException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTimeoutException.html)
- [SQLTransientConnectionException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransientConnectionException.html)
- [SQLNonTransientConnectionException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLNonTransientConnectionException.html)
- [BatchUpdateException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/BatchUpdateException.html)
- [Connection — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html)
# Phân loại retry theo lỗi và tính lặp an toàn của giao dịch JDBC

## 1. Câu hỏi quan trọng: SQLException nào có thể retry?

Khi thao tác JDBC thất bại, phản ứng "bắt `SQLException` rồi gọi lại ngay" có thể làm hệ thống **ghi dữ liệu trùng, trừ tiền hai lần, gửi email hai lần, tạo hai đơn hàng hoặc làm tăng tải khi database đang sự cố**. Ngược lại, một số lỗi do tranh chấp giao dịch như serialization failure lại **được thiết kế để ứng dụng retry toàn bộ transaction**.

Để xử lý đúng, phải trả lời **ba câu hỏi độc lập**:

1. **Lỗi thuộc nhóm nào?** SQLState, subclass của `SQLException`, mã lỗi của database/driver, ngữ cảnh và nguyên nhân.
2. **Lỗi xảy ra ở giai đoạn nào?** Mở connection, thực hiện câu SQL, kết thúc transaction bằng `COMMIT`, hoặc cleanup.
3. **Việc phát lại có an toàn không?** Có biết transaction cũ chắc chắn rollback không? Có side effect bên ngoài DB không? Có idempotency key/deduplication và cách reconcile khi không rõ commit đã thành công?

Một hướng xử lý an toàn phải kết hợp **classification + transaction phase + replay-safety**. Không có một danh sách SQLState ngắn nào tự giải quyết được cả ba.

~~~text
SQLException
     |
     v
Lấy SQLState / subclass / vendor code
     |
     v
Xác định phase: CONNECT / WORK / COMMIT
     |
     +--> Transaction chắc chắn aborted (ví dụ PostgreSQL 40001)?
     |        |
     |        v
     |   Rollback/khởi tạo transaction mới
     |   Re-run TOÀN BỘ quyết định và SQL
     |   Chỉ khi side effects cho phép replay
     |
     +--> Lỗi kết nối trước khi bắt đầu transaction?
     |        |
     |        v
     |   Có thể mượn connection mới với retry budget
     |
     +--> Không rõ COMMIT đã thành công?
     |        |
     |        v
     |   KHÔNG replay mù quáng
     |   Reconcile bằng business key/idempotency key
     |
     +--> Constraint/syntax/permission cố định?
              |
              v
           Fail fast, sửa dữ liệu hoặc cấu hình
~~~

Trong bài này, ta dùng **Java 17+**, các JDBC exceptions vẫn có hiệu lực hiện nay và ví dụ PostgreSQL được phân biệt rõ với quy tắc portable. Một chương trình Java SE độc lập sẽ chạy unit-style retry policy không cần database; mẫu JDBC thật được biên dịch riêng nhưng chỉ thực thi được khi có driver và DB.

## 2. Hiểu `SQLException` trước khi phân loại

`java.sql.SQLException` có các trường và method quan trọng:

~~~java
String sqlState = error.getSQLState();
int vendorCode = error.getErrorCode();
String message = error.getMessage();
SQLException next = error.getNextException();
Throwable cause = error.getCause();
~~~

Đây là **snippet** trong scope có `SQLException error`, không phải chương trình hoàn chỉnh.

| Thành phần | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `getSQLState()` | SQLState chuẩn hoặc vendor-specific, **có thể null** | Phân loại theo error class / code |
| `getErrorCode()` | Mã số **vendor-specific**, có thể 0 | Tra tài liệu DBMS/driver |
| `getMessage()` | Văn bản chẩn đoán, phụ thuộc phiên bản và ngôn ngữ | Log có redaction, không làm điều kiện retry |
| `getNextException()` | Chuỗi exceptions JDBC bổ sung | Driver/batch errors, tìm nguyên nhân đầy đủ |
| `getCause()` | Nguyên nhân Java bên dưới | Network/driver diagnostics |
| `getSuppressed()` | Lỗi khi cleanup trong `try-with-resources` | Phân biệt lỗi SQL chính và lỗi close/rollback |

**Không phân loại bằng `message.contains("deadlock")` hoặc các chuỗi do driver trả về.** Error message có thể thay đổi giữa driver versions, ngôn ngữ hoặc cấu hình. Ưu tiên SQLState cùng vendor code đã được tài liệu hóa, subclass và phase.

### 2.1. SQLState thường có 5 ký tự

Các SQLState quan trọng:

| SQLState / class | Ý nghĩa | Hành động gợi ý |
| --- | --- | --- |
| `40001` | Serialization failure (trên PostgreSQL) | Retry **whole transaction** sau khi đảm bảo transaction bị rollback và side effects an toàn |
| `40P01` | PostgreSQL deadlock detected | Thường retry whole transaction theo policy và ngân sách |
| Class `08` (ví dụ `08006`) | Connection exception | Cần xem phase, hủy connection hỏng; tại COMMIT có thể **unknown outcome** |
| `23505` | PostgreSQL unique violation | Mặc định **không retry**; có thể cần reconcile idempotency key |
| `23P01` | PostgreSQL exclusion constraint violation | Mặc định fail/đánh giá; chỉ retry trong tình huống nghiệp vụ xác định |
| Class `42` (ví dụ `42601`) | SQL syntax hoặc schema/privilege-related trong PostgreSQL | Sửa code/schema/quyền; không retry mù quáng |
| `57014` | PostgreSQL query canceled | Không đồng nghĩa transaction chưa có side effects; cần xét ngữ cảnh |
| Không có SQLState | Driver không cung cấp đủ metadata | Dùng subclass/cause/vendor docs; mặc định bảo thủ |

JavaDoc `SQLTransactionRollbackException` mô tả subclass gắn với SQLState class `40` **hoặc điều kiện riêng do vendor định nghĩa**. Tuy nhiên driver có thể trả một `SQLException` chung với `getSQLState()=="40001"` thay vì subclass cụ thể. Ngược lại, không nên coi mọi lỗi class `40` trên mọi hệ quản trị là hoàn toàn giống PostgreSQL.

### 2.2. Đừng bỏ qua chuỗi `getNextException`

Với JDBC batch hoặc một số driver, lỗi gốc có thể nằm ở `getNextException()`. Một thao tác có thể có nhiều lỗi, nên lựa chọn policy cần **quan sát tất cả lỗi liên quan** chứ không lấy trạng thái đầu tiên rồi bỏ qua phần còn lại.

~~~java
for (SQLException current = error;
     current != null;
     current = current.getNextException()) {
    System.out.println(current.getSQLState()
            + " / vendor=" + current.getErrorCode());
}
~~~

Đây là snippet chẩn đoán. Trong code production, chú ý exception chain có thể chứa lỗi không cùng ý nghĩa; **đừng thấy một lỗi 40001 ở phía sau rồi bỏ qua một lỗi COMMIT ambiguous hoặc authentication error ở phía trước**. Tạo classifier phù hợp driver và kiểm thử với exception fixtures.

## 3. JDBC exception hierarchy vẫn còn áp dụng

JDBC cung cấp những subclass nhằm phân biệt khả năng recovery:

| Class | Ý nghĩa của JavaDoc | Cách hiểu đúng |
| --- | --- | --- |
| `SQLTransientException` | Một operation trước đó **có thể** thành công nếu thử lại không cần can thiệp ở mức ứng dụng | Chưa đủ để kết luận việc phát lại **giao dịch** an toàn |
| `SQLTransactionRollbackException` | Statement/transaction bị database rollback do deadlock hoặc serialization failure | Có thể thử lại **toàn bộ transaction**, với policy/side effects phù hợp |
| `SQLTransientConnectionException` | Lỗi connection tạm thời | Nếu chưa có transaction, có thể retry kết nối; nếu tại COMMIT, phải reconcile |
| `SQLTimeoutException` | Timeout do query/login timeout | Có thể đã có tác động tại server; **không blind retry write** |
| `SQLNonTransientException` | Lỗi có thể không tự khắc phục nếu thử lại ngay | Thường fail fast/sửa nguyên nhân |
| `SQLIntegrityConstraintViolationException` | Constraint bị vi phạm (SQLState class `23` hoặc vendor) | Mặc định fail, nhưng có ngoại lệ nghiệp vụ đặc biệt |
| `SQLSyntaxErrorException` | Syntax/query/schema error (SQLState class `42` hoặc vendor) | Mặc định fail fast |
| `SQLNonTransientConnectionException` | Lỗi connection không dự kiến tự khỏi nếu retry giống cũ | Thay connection/chẩn đoán, không tự replay transaction |
| `SQLRecoverableException` | Có thể phục hồi sau khi ứng dụng **đóng connection và tạo connection mới**, sau đó thử lại toàn transaction/branch | Recovery của connection khác với việc biết transaction trước đã commit hay chưa |

**Điểm then chốt:** `SQLTimeoutException` là subclass của `SQLTransientException`, nhưng một timeout nhận phản hồi không có nghĩa server đã hủy thành công câu lệnh. `SQLRecoverableException` gợi ý cách phục hồi tài nguyên, **không phải giấy phép tự chạy lại mọi thao tác ghi**.

### 3.1. Subclass không chứng minh phase và outcome

Giả sử cùng một `SQLTransientConnectionException("connection lost","08006")`:

- Xảy ra ở **lúc mượn connection**, trước mọi SQL: có thể retry mở connection.
- Xảy ra ở **giữa transaction**: connection có thể hỏng, phải xác định transaction và side effects; không tái dùng connection cũ.
- Xảy ra khi **đợi phản hồi COMMIT**: server có thể đã commit, nhưng client chưa nhận acknowledgment; trạng thái **unknown**. Tự chạy lại lệnh chuyển tiền là nguy hiểm.

Vì thế classifier cần nhận **phase** bên cạnh exception.

## 4. Phân loại retry theo lỗi PostgreSQL

Tài liệu PostgreSQL hiện hành dành riêng một mục cho **Serialization Failure Handling**:

- SQLSTATE **`40001`** là `serialization_failure`. Ứng dụng nên retry **complete transaction**, bao gồm các bước quyết định câu SQL nào cần thực thi và các giá trị sử dụng. PostgreSQL không cung cấp cách tự replay transaction thay ứng dụng, vì không thể đảm bảo giữ đúng logic nghiệp vụ.
- SQLSTATE **`40P01`** là `deadlock_detected`. Retry có thể thích hợp sau khi transaction bị rollback.
- SQLSTATE **`23505`** là `unique_violation` và **`23P01`** là `exclusion_violation`. Tài liệu nêu **một số trường hợp cụ thể** chúng thực chất liên quan tới cạnh tranh đồng thời và có thể retry, nhưng đây **không phải quy tắc mặc định**: lỗi có thể là constraint violation bền vững.

| Lỗi PostgreSQL | Mặc định cho bài học | Vì sao |
| --- | --- | --- |
| `40001` | Retry whole transaction có giới hạn | Transaction không đạt serializable outcome; thực hiện lại theo snapshot mới |
| `40P01` | Có thể retry whole transaction | Deadlock victim/rollback; đợi jitter tránh lặp xung đột |
| `23505` | Không tự retry; kiểm tra duplicate/idempotency | Phần tử trùng có thể là lỗi data thực |
| `23P01` | Không tự retry; xem constraint và nguyên nhân | Exclusion constraint có thể phản ánh xung đột nghiệp vụ thật |
| `08006` khi CONNECT | Mượn connection khác có giới hạn | Chưa phát hành SQL work |
| `08006` khi COMMIT | **Reconcile trước** | Có thể không biết COMMIT đã hoàn thành |
| `42601` | Fail fast | SQL syntax sai sẽ không tự sửa bằng retry |

**Không áp dụng bảng PostgreSQL nguyên xi cho SQL Server, Oracle hoặc MySQL.** Mỗi vendor có tập mã, chính sách rollback và retry semantics khác nhau. Ví dụ deadlock của SQL Server có vendor error code riêng; phải ánh xạ dựa trên tài liệu driver.

### 4.1. Vì sao cần retry cả transaction?

Giả sử transaction:

~~~sql
BEGIN;
SELECT quantity FROM inventory WHERE sku = 'SKU-1';
UPDATE inventory SET quantity = quantity - 1 WHERE sku = 'SKU-1';
INSERT INTO reservation_audit (...);
COMMIT;
~~~

Đây là **mã SQL khái niệm**, không phải script portable chạy độc lập (cột audit/table chưa được định nghĩa). Nếu serialization failure xảy ra, **không** chỉ chạy lại câu `UPDATE` cuối. Các dữ liệu đọc ban đầu và mọi quyết định (điều kiện đủ hàng, giá, khóa, batch size) đều có thể thay đổi sau khi transaction khác đã commit.

**Retry toàn bộ unit**: lấy **connection/transaction mới**, đọc lại dữ liệu, tính lại quyết định, chạy lại tất cả SQL và commit. Tránh giữ state cũ từ attempt trước làm cho retry quyết định dựa trên snapshot lỗi thời.

### 4.2. Retry transaction không đồng nghĩa mọi SQL bên trong phải là idempotent

Nếu PostgreSQL **chắc chắn rollback** attempt bị `40001`, một câu `UPDATE count=count+1` của attempt đó **không để lại database effect đã commit**, nên thực hiện lại **toàn transaction** có thể an toàn trong DB.

Tuy nhiên, nếu code bên trong transaction đã gọi API thanh toán, gửi email, publish message hoặc sửa file **ngoài DB**, những side effects có thể đã thành công dù DB rollback. Khi retry transaction, các side effects đó sẽ bị lặp.

Vì vậy hãy phân biệt:

- **Database-only atomic transaction đã được chứng minh rollback:** SQL bên trong có thể phát lại toàn unit theo policy; không đòi từng SQL tự idempotent.
- **External side effects nằm trong callback transaction:** không tự replay trừ khi có cơ chế idempotency/deduplication mạnh và thiết kế cụ thể.
- **COMMIT outcome unknown:** kể cả database-only writes có thể đã commit; không phát lại mù quáng.

Đây là nguồn gốc khác nhau của **transaction replay safety** và **business request idempotency**.

## 5. Mất kết nối lúc COMMIT: tình huống nguy hiểm nhất

Hãy xét timeline:

~~~text
Client JDBC                  Database
     |                          |
     +---- UPDATE ... --------->|
     |<---- success ------------+
     +---- COMMIT ------------->|
     |                          +--- có thể đã ghi commit log
     X  network lost            |
     |                          |
     +--- SQLException 08006    |
     |
     v
 Không biết: COMMIT thành công hay chưa
~~~

Khi nhận `SQLException` sau `commit()`, **không suy ra transaction đã rollback chỉ từ việc client không nhận phản hồi**. Một lỗi mạng/timeout khi COMMIT có thể để lại trạng thái **unknown outcome**. Gọi `rollback()` trên cùng connection sau đó cũng **không thể đảo ngược một transaction đã commit trước đó**.

Nếu request là “trừ 100 nghìn đồng và tạo giao dịch thanh toán”, retry vô điều kiện có thể trừ hai lần.

### 5.1. Reconcile nghĩa là gì?

Reconciliation là xác minh kết quả **bằng khóa nghiệp vụ ổn định** trước khi quyết định thực hiện thao tác lại. Chẳng hạn request có `transfer_request_id` do client/backend tạo **một lần** và giữ nguyên qua retries:

1. Truy vấn record `payment_requests`/`transfers` theo request ID bằng connection mới.
2. Kiểm tra trạng thái và dữ liệu đã lưu, không chỉ kiểm tra một số dư tổng quát.
3. Nếu record thể hiện giao dịch hoàn tất cùng input, trả lại kết quả cũ.
4. Nếu record đang pending/unknown, chạy quy trình reconcile theo DB/payment provider.
5. Nếu chắc chắn chưa tồn tại và nghiệp vụ cho phép, mới khởi tạo transaction mới **với cùng idempotency key**.
6. Tránh tạo request ID mới khi caller retry cùng một yêu cầu.

**Không** dùng transaction ID mới cho mỗi attempt nếu mục tiêu là chống trùng lặp nghiệp vụ. Một request business logical phải có key ổn định.

### 5.2. Unique key giúp deduplicate, nhưng không phải toàn bộ giải pháp

Một schema khái niệm:

~~~sql
CREATE TABLE transfer_requests (
    request_id VARCHAR(80) PRIMARY KEY,
    source_account BIGINT NOT NULL,
    destination_account BIGINT NOT NULL,
    amount DECIMAL(18, 2) NOT NULL,
    status VARCHAR(24) NOT NULL
);
~~~

Đây là DDL khái niệm, cần tùy chỉnh DBMS. Khi ghi giao dịch, bản ghi idempotency và tác động database nên nằm trong **cùng một transaction** nếu có thể. Unique constraint trên `request_id` ngăn hai transaction cùng commit một key, nhưng ứng dụng vẫn cần kiểm tra **input fingerprint**, status và trả kết quả cũ; không coi mọi `23505` đều thành công hoặc đều được phép retry.

Với payment provider hoặc message broker nằm ngoài cùng DB transaction, cần **idempotency phía provider**, transactional outbox/inbox hoặc dedupe bằng event ID. Một database unique constraint không tự undo một HTTP call đã hoàn thành.

## 6. Các quyết định retry nên mô hình hóa rõ ràng

Bốn quyết định mang ý nghĩa khác nhau:

| Decision | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `RETRY_WHOLE_TRANSACTION` | Transaction cũ chắc chắn aborted; mở transaction mới và chạy lại toàn unit, nếu side effects cho phép | PostgreSQL `40001`/`40P01` |
| `RETRY_CONNECTION` | Retry **mượn/mở connection** trước khi có SQL work | Lỗi connection tạm thời tại ACQUIRE |
| `RECONCILE_FIRST` | Chưa biết kết quả hoặc connection hỏng; không replay mù quáng | Timeout ở WORK, mất phản hồi COMMIT |
| `FAIL_FAST` | Không dự kiến retry tự sửa được lỗi | Syntax `42601`, constraint `23505` không có ngữ cảnh đặc biệt |

Một retry engine production nên biết **phase**:

~~~text
ACQUIRE -> BEGIN -> WORK -> COMMIT -> SUCCESS
              |       |        |
              |       |        +--> SQLException:
              |       |             có thể unknown outcome
              |       +--> SQLException:
              |             xét rollback/side effects
              +--> SQLException:
                    chưa bắt đầu work hoặc chưa rõ BEGIN
~~~

Giai đoạn `CLOSE/RETURN_TO_POOL` cũng cần được theo dõi: **lỗi đóng connection sau khi `commit()` đã trả về thành công không có nghĩa transaction phải được replay**. Đừng vô tình retry cả request chỉ vì exception từ resource cleanup che khuất một commit thành công.

## 7. Retry budget, exponential backoff và jitter

Ngay cả `40001` hợp lệ vẫn không nên retry vô hạn. Các xung đột đồng thời có thể kéo dài; nhiều clients retry tức thời có thể tăng tranh chấp.

Một retry policy nên đặt:

- **`maxAttempts`**: ví dụ 3 lần, **bao gồm attempt đầu tiên**.
- **Deadline tổng**: giới hạn thời gian request còn được phép chi cho retry; không chỉ đếm attempts.
- **Backoff có jitter**: delay ngẫu nhiên trong một giới hạn để tránh nhiều clients đồng bộ retry.
- **Per-query/login/network timeouts**: phối hợp với deadline của request và JDBC pool.
- **Cancellation**: khi thread bị interrupt, giữ `Thread.currentThread().interrupt()` và dừng; không nuốt interruption.
- **Circuit breaker/bulkhead** ở service layer khi DB đang outage diện rộng; tránh mọi thread cùng chiếm pool slots.
- **Metrics**: attempts, SQLState, phase, retry reason, terminal outcome, replays refused, latency.
- **Idempotency/reconciliation**: bắt buộc với requests có thể bị gọi lại bởi HTTP clients/jobs/queues.

Ví dụ thuật toán delay có giới hạn:

~~~java
long capMs = Math.min(200L, 25L * attempt);
long jitterMs = ThreadLocalRandom.current().nextLong(capMs + 1);
Thread.sleep(jitterMs);
~~~

Đây là snippet Java, cần import `java.util.concurrent.ThreadLocalRandom` và xử lý `InterruptedException`; `attempt` là số lần retry hiện tại, không phải biến toàn JVM. Delay này đơn giản cho mục đích học; production có thể dùng exponential backoff với jitter, max elapsed time và retry budget theo service SLO.

**Không sleep trong khi đang giữ connection hỏng hoặc transaction lock**. Thoát/đóng connection attempt cũ, rồi mới backoff trước khi mượn connection mới.

## 8. Ví dụ Java 17+ tự chạy: SQLState + phase + transaction replay safety

### 8.1. Tính trung thực của ví dụ

Chương trình `JdbcRetryDemo.java` dùng:

- Các subclass `SQLException` thực sự thuộc Java SE.
- SQLState giả lập `40001`, `40P01`, `23505`, `08006` và `42601`.
- Một **classifier bảo thủ** trả bốn decisions.
- Dynamic proxy triển khai các method của `Connection` cần để quan sát `setAutoCommit(false)`, `rollback`, `commit` và `close`.
- Hai attempts: attempt 1 ném `SQLTransactionRollbackException("40001")`, attempt 2 thành công.
- Một test với flag `replaySafe=false` để từ chối phát lại khi callback có side effects bên ngoài.
- Một test mô phỏng lỗi connection trong WORK và xác nhận không replay mù quáng.

**Đây là in-memory test double; nó KHÔNG mở JDBC connection tới DB, không phát hành SQL và không khẳng định database nào đã rollback thật.** Các phase và SQLState là fixture do test tạo. Mã nhằm dạy logic ra quyết định và kiểm soát lifecycle trên Java 17+.

### 8.2. Mã hoàn chỉnh: `JdbcRetryDemo.java`

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.SQLRecoverableException;
import java.sql.SQLTimeoutException;
import java.sql.SQLTransactionRollbackException;
import java.sql.SQLTransientConnectionException;
import java.sql.SQLTransientException;
import java.util.ArrayList;
import java.util.List;

public final class JdbcRetryDemo {
    enum Phase { ACQUIRE, WORK, COMMIT }
    enum Decision {
        RETRY_WHOLE_TRANSACTION, RETRY_CONNECTION,
        RECONCILE_FIRST, FAIL_FAST
    }

    static Decision classify(SQLException error, Phase phase) {
        String state = error.getSQLState();
        boolean aborted = error instanceof SQLTransactionRollbackException
                || "40001".equals(state) || "40P01".equals(state);
        boolean connection = error instanceof SQLTransientConnectionException
                || error instanceof SQLRecoverableException
                || (state != null && state.startsWith("08"));
        boolean timeout = error instanceof SQLTimeoutException;
        if (phase == Phase.COMMIT && (connection || timeout)) {
            return Decision.RECONCILE_FIRST;
        }
        if (aborted) return Decision.RETRY_WHOLE_TRANSACTION;
        if (phase == Phase.ACQUIRE && connection) {
            return Decision.RETRY_CONNECTION;
        }
        if (connection || timeout) return Decision.RECONCILE_FIRST;
        return Decision.FAIL_FAST;
    }

    @FunctionalInterface
    interface ConnectionFactory {
        Connection open(int attempt) throws SQLException;
    }

    @FunctionalInterface
    interface TransactionWork {
        void run(Connection connection, int attempt) throws SQLException;
    }

    static void runTransaction(ConnectionFactory factory,
                               TransactionWork work,
                               int maxAttempts,
                               boolean replaySafe) throws SQLException {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try (Connection c = factory.open(attempt)) {
                c.setAutoCommit(false);
                Phase phase = Phase.WORK;
                try {
                    work.run(c, attempt);
                    phase = Phase.COMMIT;
                    c.commit();
                    System.out.println("Attempt " + attempt + ": committed");
                    return;
                } catch (SQLException failure) {
                    try {
                        c.rollback();
                    } catch (SQLException rollbackError) {
                        failure.addSuppressed(rollbackError);
                    }
                    Decision decision = classify(failure, phase);
                    if (decision != Decision.RETRY_WHOLE_TRANSACTION
                            || !replaySafe || attempt == maxAttempts) {
                        throw failure;
                    }
                    System.out.println("Attempt " + attempt
                            + ": rolled back; retry whole transaction");
                }
            }
        }
    }

    static Connection fakeConnection(int attempt, List<String> events) {
        InvocationHandler handler = (proxy, method, args) -> {
            switch (method.getName()) {
                case "setAutoCommit" -> {
                    events.add("begin#" + attempt);
                    return null;
                }
                case "rollback" -> {
                    events.add("rollback#" + attempt);
                    return null;
                }
                case "commit" -> {
                    events.add("commit#" + attempt);
                    return null;
                }
                case "close" -> {
                    events.add("close#" + attempt);
                    return null;
                }
                default -> throw new java.sql.SQLFeatureNotSupportedException(
                        method.getName());
            }
        };
        return (Connection) Proxy.newProxyInstance(
                Connection.class.getClassLoader(),
                new Class<?>[] {Connection.class}, handler);
    }

    static void show(String label, SQLException e, Phase phase) {
        System.out.println(label + ": " + classify(e, phase));
    }

    public static void main(String[] args) throws SQLException {
        show("Serialization 40001",
                new SQLTransactionRollbackException("serialization", "40001"),
                Phase.WORK);
        show("Deadlock 40P01", new SQLException("deadlock", "40P01"),
                Phase.WORK);
        show("Unique 23505", new SQLException("unique", "23505"),
                Phase.WORK);
        show("Transient connect",
                new SQLTransientConnectionException("connect", "08006"),
                Phase.ACQUIRE);
        show("Timeout during work",
                new SQLTimeoutException("timed out"), Phase.WORK);
        show("Lost reply at COMMIT",
                new SQLTransientConnectionException("unknown commit", "08006"),
                Phase.COMMIT);
        show("Recoverable during work",
                new SQLRecoverableException("reopen", "08006"),
                Phase.WORK);
        show("Syntax 42601", new SQLException("syntax", "42601"),
                Phase.WORK);
        show("Generic transient",
                new SQLTransientException("unknown"), Phase.WORK);

        List<String> events = new ArrayList<>();
        runTransaction(
                attempt -> fakeConnection(attempt, events),
                (c, attempt) -> {
                    if (attempt == 1) {
                        throw new SQLTransactionRollbackException(
                                "synthetic conflict", "40001");
                    }
                },
                3,
                true);
        System.out.println("Connection lifecycle: "
                + String.join(", ", events));

        try {
            runTransaction(
                    attempt -> fakeConnection(attempt, new ArrayList<>()),
                    (c, attempt) -> {
                        throw new SQLTransactionRollbackException(
                                "synthetic conflict", "40001");
                    },
                    3, false);
            throw new AssertionError("Unsafe replay should be blocked");
        } catch (SQLTransactionRollbackException expected) {
            System.out.println("Unsafe replay: blocked");
        }

        try {
            runTransaction(
                    attempt -> fakeConnection(attempt, new ArrayList<>()),
                    (c, attempt) -> {
                        throw new SQLTransientConnectionException(
                                "simulated unknown outcome", "08006");
                    },
                    3, true);
            throw new AssertionError("Unknown outcome should be blocked");
        } catch (SQLTransientConnectionException expected) {
            System.out.println("Unknown outcome: reconcile, do not replay");
        }
        System.out.println("Test double only (no database): true");
    }
}
~~~

### 8.3. Lệnh biên dịch/chạy và stdout chuẩn xác

Lưu source với đúng tên `JdbcRetryDemo.java`. Tại thư mục chứa file:

~~~sh
javac --release 17 JdbcRetryDemo.java
java JdbcRetryDemo
~~~

Chương trình chỉ dùng Java SE, không cần JDBC driver JAR hoặc database. Đã biên dịch bằng `javac --release 17` và chạy trên JDK 24, nhận **stdout chính xác**:

~~~text
Serialization 40001: RETRY_WHOLE_TRANSACTION
Deadlock 40P01: RETRY_WHOLE_TRANSACTION
Unique 23505: FAIL_FAST
Transient connect: RETRY_CONNECTION
Timeout during work: RECONCILE_FIRST
Lost reply at COMMIT: RECONCILE_FIRST
Recoverable during work: RECONCILE_FIRST
Syntax 42601: FAIL_FAST
Generic transient: FAIL_FAST
Attempt 1: rolled back; retry whole transaction
Attempt 2: committed
Connection lifecycle: begin#1, rollback#1, close#1, begin#2, commit#2, close#2
Unsafe replay: blocked
Unknown outcome: reconcile, do not replay
Test double only (no database): true
~~~

### 8.4. Giải thích các điểm quan trọng

- `40001` và `40P01` dẫn đến `RETRY_WHOLE_TRANSACTION` vì policy mô phỏng **PostgreSQL**. Driver có thể dùng subclass hoặc `SQLException` chung nên classifier xét cả hai.
- `23505` và `42601` mặc định `FAIL_FAST`: unique violation/syntax thường không tự biến mất chỉ vì gọi lại.
- `RETRY_CONNECTION` chỉ dành cho phase **ACQUIRE**, khi chưa bắt đầu công việc. Demo **chỉ phân loại** nhóm này, không xây retry loop cho việc mở connection.
- `SQLTimeoutException` tại WORK được xếp `RECONCILE_FIRST` vì subtype transient **không chứng minh statement chưa có side effect**.
- `SQLTransientConnectionException` tại COMMIT cũng được xếp `RECONCILE_FIRST` vì client có thể không biết outcome.
- `SQLRecoverableException` gợi ý đóng connection cũ và tạo connection mới; không được tự diễn dịch thành replay-safe.
- `Connection lifecycle` cho thấy attempt thất bại gọi rollback, đóng handle, rồi attempt thành công bắt đầu trên **connection mới**.
- `replaySafe=false` là **cổng an toàn** cho công việc có external side effects chưa được bảo vệ. Điều này không có nghĩa SQL `UPDATE` trong một transaction đã rollback luôn phải idempotent ở mức statement.
- Mã `runTransaction` mô phỏng đơn giản: nó **không** implement retry acquisition, jitter, retry deadline, hay phương thức xử lý connection-close failure sau successful commit. Đó là những yêu cầu của production ở các mục tiếp theo.
- `fakeConnection` không kết nối server và không thực thi statement SQL nào. Output chỉ phản ánh thứ tự method gọi trong test double.

### 8.5. Không bê classifier minh họa vào production mà không bổ sung context

Classifier trong demo cố ý bảo thủ nhưng vẫn thiếu những thuộc tính mà production cần: SQLState/vendor map của driver thật, nested SQLExceptions, rollback outcome, auto-commit mode, trace ID, external side effects, operation type, cancellation và budget. Một `SQLTransactionRollbackException` với SQLState null vẫn được demo xếp retry; khi triển khai thật cần xác nhận vendor mapping và **transaction-aborted semantics**.

Đặc biệt, demo gọi `c.rollback()` trong catch rồi quyết định retry dựa vào error type, chứ **không kiểm tra rollback có thành công hay không**. Mẫu integration ở mục 9 xử lý lỗi rollback chặt hơn. Một sự cố network làm rollback không xác nhận có thể tạo tình huống unknown outcome cần đánh giá thêm.

## 9. Mẫu Java 17+ với JDBC thật (PostgreSQL)

### 9.1. Vì sao retry loop phải bao quanh cả transaction?

Đây là class Java với `runTransaction`:

- Mở **connection mới cho mỗi attempt**.
- Đặt `autoCommit=false` trước công việc.
- Thực thi callback chứa toàn bộ các bước đọc/ghi SQL cần replay.
- Commit khi thành công, trả kết quả.
- Nếu `SQLException` là PostgreSQL `40001` hoặc `40P01`, cố rollback rồi bỏ connection cũ; chỉ retry nếu rollback thành công và còn budget.
- Nếu rollback thất bại, exception khác hoặc đã hết attempts: **không retry**.
- Backoff với jitter sau khi connection attempt cũ được đóng.
- Giữ trạng thái interrupted khi sleep bị hủy.

**Giới hạn thiết kế:** callback chỉ được chứa **database-only work** hoặc các side effects đã bảo vệ đúng cách; không đặt email/payment HTTP call vào bên trong rồi retry vô thức. Mẫu **không tự retry lỗi tại `DriverManager.getConnection`** và **không retry lỗi COMMIT mất kết nối/timeout**, vì chỉ hai SQLStates PostgreSQL đã biết transaction bị abort mới được retry.

### 9.2. Source hoàn chỉnh: `JdbcRetryRealTemplate.java`

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Properties;
import java.util.concurrent.ThreadLocalRandom;

public final class JdbcRetryRealTemplate {
    @FunctionalInterface
    interface ConnectionFactory {
        Connection open() throws SQLException;
    }

    @FunctionalInterface
    interface UnitOfWork {
        int execute(Connection connection) throws SQLException;
    }

    static boolean knownPostgresAbort(SQLException error) {
        String state = error.getSQLState();
        return "40001".equals(state) || "40P01".equals(state);
    }

    static int runTransaction(ConnectionFactory factory,
                              UnitOfWork work,
                              int maxAttempts) throws SQLException {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException("maxAttempts must be >= 1");
        }
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            boolean retry = false;
            try (Connection connection = factory.open()) {
                connection.setAutoCommit(false);
                try {
                    int result = work.execute(connection);
                    connection.commit();
                    return result;
                } catch (SQLException error) {
                    boolean rolledBack = true;
                    try {
                        connection.rollback();
                    } catch (SQLException rollbackError) {
                        rolledBack = false;
                        error.addSuppressed(rollbackError);
                    }

                    if (!rolledBack || !knownPostgresAbort(error)
                            || attempt == maxAttempts) {
                        throw error;
                    }
                    retry = true;
                }
            }
            if (retry) {
                long ceilingMs = Math.min(200L, 25L * attempt);
                long jitterMs =
                        ThreadLocalRandom.current().nextLong(ceilingMs + 1);
                try {
                    Thread.sleep(jitterMs);
                } catch (InterruptedException interruption) {
                    Thread.currentThread().interrupt();
                    throw new SQLException(
                            "Interrupted during transaction retry",
                            interruption);
                }
            }
        }
        throw new SQLException("Retry attempts exhausted");
    }

    public static void main(String[] args) throws SQLException {
        String url = System.getenv("JDBC_URL");
        if (url == null || url.isBlank()) {
            System.out.println(
                    "Set JDBC_URL and install a PostgreSQL JDBC driver.");
            return;
        }

        Properties properties = new Properties();
        String user = System.getenv("JDBC_USER");
        String password = System.getenv("JDBC_PASSWORD");
        if (user != null) properties.setProperty("user", user);
        if (password != null) properties.setProperty("password", password);

        int rows = runTransaction(
                () -> DriverManager.getConnection(url, properties),
                connection -> {
                    try (PreparedStatement statement =
                            connection.prepareStatement(
                                "UPDATE inventory SET quantity = quantity - 1 "
                                + "WHERE sku = ? AND quantity > 0")) {
                        statement.setString(1, "SKU-DEMO");
                        return statement.executeUpdate();
                    }
                },
                3);
        System.out.println("Updated rows: " + rows);
    }
}
~~~

### 9.3. Biên dịch, guard và chạy với DB thật

~~~sh
javac --release 17 JdbcRetryRealTemplate.java
java JdbcRetryRealTemplate
~~~

Đã biên dịch thành công trên JDK 24. Khi chưa cấu hình `JDBC_URL`, stdout chính xác:

~~~text
Set JDBC_URL and install a PostgreSQL JDBC driver.
~~~

Đây là **nhánh guard đã chạy**; không tác động tới database. Để chạy thao tác thật, cần:

- PostgreSQL JDBC driver JAR tương thích JDK 17+ được đưa vào runtime classpath.
- PostgreSQL database và biến môi trường `JDBC_URL`, `JDBC_USER`, `JDBC_PASSWORD`.
- Bảng **`inventory(sku, quantity)`** có dữ liệu test thích hợp; `UPDATE` là operation **ghi dữ liệu thật**, nên chỉ chạy trên môi trường thử nghiệm mà bạn có quyền thay đổi.
- Transaction policy, isolation level và pool phù hợp; `40001` thường gắn với transaction isolation của PostgreSQL như Repeatable Read/Serializable.
- Không đặt external HTTP side effects trong callback.

Ví dụ URL PostgreSQL:

~~~text
jdbc:postgresql://localhost:5432/appdb
~~~

Đây là **ví dụ cú pháp**, không có server được bảo đảm ở địa chỉ ấy.

Lệnh Linux/macOS với JAR có thật:

~~~sh
java -cp ".:/path/to/postgresql.jar" JdbcRetryRealTemplate
~~~

Với Windows dùng classpath separator `;`:

~~~text
java -cp ".;C:\drivers\postgresql.jar" JdbcRetryRealTemplate
~~~

**Không có stdout cố định nào được cam kết cho nhánh database thật**, vì số dòng được update, retries và locks phụ thuộc trạng thái DB. Bài đã test compile và guard nhưng **không chạy UPDATE trên DB thật** (không có driver/server/credentials được cung cấp). Nếu table không tồn tại hoặc driver chưa được thêm vào classpath, `SQLException` là kết quả có thể xảy ra.

### 9.4. Giới hạn an toàn của mẫu real-JDBC

Mẫu là **điểm bắt đầu có kiểm soát**, không phải thư viện transaction production hoàn chỉnh:

- Nó xác minh rollback operation trả về bình thường trước khi retry PostgreSQL `40001/40P01`. Nếu rollback fail, nó dừng.
- Dù rollback thành công, **một lỗi không phải known abort sẽ bị từ chối retry**, bao gồm lỗi mất kết nối tại COMMIT.
- Một failure từ `connection.close()` sau commit **không tự bị retry**; caller cần phân biệt cleanup failure với outcome transaction.
- Mã chỉ xét SQLState đầu tiên, không có vendor-specific error chain classifier. Hãy bổ sung theo driver.
- Có tối đa 3 attempts nhưng chưa có **request deadline tổng** hoặc metrics/logging; cần thêm trước khi áp dụng production.
- Không có idempotency key; nếu cùng một HTTP request được gửi lại ngoài retry loop (ví dụ client timeout), code vẫn có thể UPDATE thêm lần nữa. Cần business-level idempotency riêng.
- `DriverManager` phù hợp minh họa; ứng dụng server thường dùng `DataSource`/pool và một connection cho mỗi transaction attempt.
- Không dùng trên DBMS khác bằng cách copy `knownPostgresAbort`; tạo policy khác theo vendor.

## 10. Phân biệt ba mức idempotency

### 10.1. Idempotent operation

Một operation là **idempotent** nếu thực hiện nó nhiều lần với cùng input tạo cùng trạng thái nghiệp vụ cuối.

Ví dụ có điều kiện:

~~~sql
UPDATE orders SET status = 'CONFIRMED' WHERE id = ?;
~~~

Nếu không có trigger/side effects và context khác thay đổi, việc đặt cùng status lặp lại có thể có tính idempotent về trạng thái. Nhưng nếu trigger phát sự kiện mỗi lần UPDATE hoặc hệ thống ghi audit row, kết quả tổng thể có thể **không idempotent**. Đừng xét SQL text đơn độc.

Một lệnh sau rõ ràng **không idempotent** khi được commit lặp lại:

~~~sql
UPDATE inventory SET quantity = quantity - 1 WHERE sku = ?;
~~~

Nếu chạy và commit hai lần cho cùng request, số lượng giảm hai đơn vị.

### 10.2. Safe transaction replay

Khi một transaction chắc chắn bị rollback vì serialization/deadlock, việc chạy lại toàn bộ transaction có thể không tạo duplicate **database commit** dù bên trong dùng lệnh `quantity=quantity-1`. Nhưng điều kiện là không có side effects bên ngoài DB không được rollback.

Trước mỗi retry, cần kiểm soát:

- Transaction cũ đã bị DB abort theo known semantics?
- Connection đã được dispose/rollback đúng?
- Có email/payment/cache mutation hoặc queue publish từ attempt cũ không?
- Logic quyết định đã được **tính lại** khi mở transaction mới?
- Có max attempts, deadline và jitter không?
- Cancellation có được tôn trọng không?

### 10.3. Business request idempotency

Ngay cả khi retry loop đúng, HTTP client hoặc message broker có thể gửi **cùng request nhiều lần**, có thể vào các instances khác nhau. Đây là lý do cần một business idempotency key, ví dụ `order_request_id`, tồn tại **qua retries và retries ở lớp transport**.

**Chỉ cho retry loop có giới hạn không đủ để chống trùng request.** Một transaction đã commit có thể bị client coi thất bại do mất phản hồi; lần request sau phải có cách nhận ra kết quả cũ.

## 11. Transactional outbox khi có side effects ngoài DB

Ví dụ nghiệp vụ tạo đơn hàng và gửi email/queue:

~~~text
BEGIN TRANSACTION
  INSERT order
  INSERT outbox_event (event_id, payload)
COMMIT
         |
         v
Outbox worker đọc event đã commit
         |
         v
Publish message / gửi notification
         |
         v
Consumer deduplicates event_id
~~~

Đây là thiết kế **transactional outbox**. Transaction trong DB ghi order và một outbox row cùng lúc. Khi DB báo serialization failure, cả order và outbox row của attempt bị rollback, nên retry toàn bộ transaction không gửi event ra ngoài trong lúc chưa commit.

Publisher ngoài transaction có thể phát trùng khi gặp lỗi network; consumer phải xử lý idempotency/deduplication theo `event_id` hoặc cơ chế tương ứng. Outbox không mặc nhiên bảo đảm exactly-once delivery trên mọi hệ thống.

**Không** thực hiện `sendEmail()` hoặc gọi payment API trực tiếp giữa các câu SQL trong callback transaction rồi tự retry `40001` mà không có sự bảo vệ.

## 12. Các lỗi khác không được retry mù quáng

### 12.1. Unique violation `23505`

Lỗi unique có thể xuất hiện khi:

- Một người dùng nhập username đã tồn tại.
- Cùng idempotency key được submit lại.
- Hai transactions đồng thời cố tạo một key được chọn sau khi đọc trạng thái trước.

Tài liệu PostgreSQL nói có **một số tình huống** unique violation phát sinh từ cạnh tranh có thể retry, nhưng cần **logic nghiệp vụ đủ thông tin**. Mặc định `23505` không phải transient error chung. Nếu dùng idempotency key, thay vì retry insert vô hạn, hãy **lookup request_id đã tồn tại và so sánh payload/result**.

### 12.2. Syntax, schema, permission

Lỗi cú pháp, bảng không tồn tại, quyền thiếu hoặc kiểu dữ liệu không tương thích không tự biến mất khi thử lại nhiều lần. Khi deploy/schema migration đang diễn ra, một số lỗi có thể hết sau khi thao tác quản trị hoàn thành, nhưng policy chung vẫn nên fail/alert thay vì saturate database với retries.

### 12.3. Timeout

`SQLTimeoutException` có thể xảy ra khi query timeout hoặc login timeout. Với login chưa mở connection và chưa chạy SQL, có thể retry **connection acquisition** có giới hạn. Với write/commit, timeout có thể làm **không rõ outcome**.

Không viết một rule kiểu:

~~~java
if (e instanceof SQLTransientException) {
    return retryWholeTransaction();
}
~~~

Đây là **anti-pattern**: `SQLTimeoutException` và `SQLTransientConnectionException` cũng là transient subclasses. Loại lỗi chỉ cho biết khả năng transient, **không phải chứng chỉ an toàn để phát lại transaction**.

### 12.4. `SQLRecoverableException`

JavaDoc `SQLRecoverableException` yêu cầu recovery tối thiểu **đóng current connection và lấy connection mới** trước khi thử lại transaction/branch. Điều này khác với lời hứa rằng **transaction trước chắc chắn chưa commit**. Nếu failure xảy ra gần COMMIT hoặc có side effects không rõ, cần reconcile; không reuse một `Connection` đã bị driver xem là unrecoverable.

### 12.5. Connection pool và stale connections

Một pool hiện đại thường dùng `Connection.isValid(timeout)` để kiểm tra connection trước khi mượn/tái sử dụng khi cần. Tuy nhiên connection có thể mất sau kiểm tra; ứng dụng vẫn phải xử lý `SQLException` tại SQL operation.

Nếu lỗi xảy ra khi mượn connection mà chưa có SQL work, có thể retry acquisition với backoff/deadline. Đừng chia sẻ cùng một `Connection` giữa nhiều transaction attempts; pooled connection bị lỗi cần được trả/discard theo pool policy.

## 13. Vòng đời transaction và các trường hợp cần thận trọng

### 13.1. Thời điểm rõ ràng rollback

Với PostgreSQL serialization failure, DB transaction bị abort theo contract cụ thể. Đây là tình huống có thể retry whole transaction. Dù vậy nên gọi rollback/close phù hợp để đưa JDBC connection vào trạng thái sạch trước khi trả về pool; không tái sử dụng connection đang ở aborted transaction.

### 13.2. Khi rollback cũng lỗi

Giả sử `work.execute` ném `SQLException`, rồi `connection.rollback` ném thêm `SQLException`:

~~~java
try {
    connection.rollback();
} catch (SQLException rollbackFailure) {
    originalFailure.addSuppressed(rollbackFailure);
    // Đừng coi rollback đã được xác nhận.
}
~~~

Đây là snippet. Việc rollback không trả về bình thường khiến transaction outcome/connection health không rõ; đừng dựa vào một biến `retryable=true` cũ rồi tự phát lại. Bỏ connection hỏng và áp recovery theo DB semantics.

### 13.3. Lỗi đóng connection sau commit

`try-with-resources` đóng connection khi rời scope. Nếu `commit()` đã trả về thành công, rồi `close()` thất bại, **không tự chạy lại toàn transaction**. Commit success và cleanup failure là hai sự kiện khác nhau. Khi caller nhận exception nhưng không biết phase, cần telemetry/response logic để tránh tự replay một yêu cầu đã thành công.

### 13.4. Auto-commit mode

Nếu dùng `Connection` với `autoCommit=true`, mỗi statement có thể commit khi hoàn thành tùy JDBC contract. Không thể tự tạo một retry loop cho nhiều statements mà vẫn gọi đó là "retry whole transaction".

Với unit cần atomicity, đặt `connection.setAutoCommit(false)`, thực thi toàn unit, `commit/rollback` rồi đóng/trả connection. Trong connection pool, framework transaction manager có thể đã kiểm soát auto-commit và boundaries; không tự quản lý đồng thời với `@Transactional` nếu framework đã là owner.

### 13.5. Nested retry từ framework

Một framework hoặc driver có thể có retry/failover semantics riêng. Nếu cả repository, service layer, HTTP client và message consumer đều tự retry 3 lần, tổng số attempts có thể bị nhân lên rất lớn. Xác định **một lớp sở hữu transaction retry**, giới hạn tổng budget và đặt idempotency ở biên nghiệp vụ.

## 14. Observability: biết retry có thật sự giúp không

Một sự kiện chẩn đoán hữu ích có thể ghi:

~~~text
operation_name
request_id_hash / idempotency_key_hash
phase = ACQUIRE | WORK | COMMIT | CLEANUP
sql_state (nullable)
vendor_error_code
jdbc_exception_class
decision = RETRY_WHOLE_TRANSACTION | RETRY_CONNECTION | RECONCILE_FIRST | FAIL_FAST
attempt_number / max_attempts
rollback_confirmed
elapsed_ms / remaining_deadline_ms
pool_name / db_role
final_outcome = COMMITTED | ABORTED | UNKNOWN
~~~

Đây là **schema telemetry minh họa**, không phải fields mà `SQLException` tự lưu sẵn. Không log credentials, toàn bộ SQL parameters, thông tin cá nhân hoặc raw connection string có secret.

Các chỉ số quan trọng:

- Transaction retry success rate và attempts distribution.
- Số lỗi `40001` và `40P01` theo operation, DB role, deployment.
- Timeout, connection acquisition failures, pool active/pending, saturation.
- Tỷ lệ unknown-commit cases cần reconciliation.
- Số duplicate requests được idempotency key ngăn chặn.
- Retry exhausted, cancellation và rollback failures.
- Độ trễ p95/p99 tính **cả** thời gian backoff và attempts.

Nếu retry attempts tăng, có thể cần cải thiện transaction isolation/workload, lock ordering, index, transaction duration hoặc pool sizing; không chỉ tăng maxRetries.

## 15. Kế hoạch integration testing

### 15.1. Unit tests cho classifier

Dùng fixtures rõ SQLState và phase:

| Test | Phase | Kỳ vọng |
| --- | --- | --- |
| `SQLTransactionRollbackException` / `40001` | WORK | `RETRY_WHOLE_TRANSACTION` |
| `SQLException("40P01")` | WORK | `RETRY_WHOLE_TRANSACTION` |
| `SQLException("23505")` | WORK | `FAIL_FAST` theo default |
| `SQLTransientConnectionException("08006")` | ACQUIRE | `RETRY_CONNECTION` |
| `SQLTimeoutException` | WORK | `RECONCILE_FIRST` |
| `SQLTransientConnectionException("08006")` | COMMIT | `RECONCILE_FIRST` |
| `SQLRecoverableException` | WORK | `RECONCILE_FIRST` |
| `SQLException("42601")` | WORK | `FAIL_FAST` |
| Generic `SQLTransientException` không có SQLState | WORK | `FAIL_FAST` cho policy bảo thủ |
| `40001` nhưng `replaySafe=false` | WORK | Không tự replay |
| `40001` đã hết retry budget | WORK | Propagate original SQLException |
| `40001` và rollback fail | WORK | Không retry, lưu suppressed rollback error |

### 15.2. Integration tests với PostgreSQL

Trong test DB có quyền điều khiển dữ liệu/transaction:

1. Tạo scenario **serialization failure** có thể tái hiện với hai concurrent transactions và xác minh `40001`.
2. Đảm bảo callback thực hiện lại **cả read-and-decision logic**, không chỉ câu UPDATE cuối.
3. Kiểm chứng mỗi retry dùng **transaction mới** và attempt lỗi không để lại committed DB effects.
4. Tạo deadlock trong môi trường thử nếu phù hợp; xác nhận `40P01` và bounded retry.
5. Test unique constraint `23505` không bị retry vô hạn.
6. Mô phỏng network drop tại **COMMIT** và xác minh service trả **unknown/reconcile**, không tự tạo thêm business side effect.
7. Test cùng idempotency key được gửi hai lần đồng thời; DB chỉ có **một logical result**.
8. Test rollback failure/close failure, connection pool exhaustion và driver SQLState mapping.
9. Test cancellation, deadline và thundering herd để hiệu chỉnh jitter.
10. Test duplicate delivery từ queue/webhook và consumer dedupe khi có outbox.

Không chạy fault injection, kill connection hoặc deadlock stress trên production chỉ để minh họa học tập.

## 16. Bài toán thực tế: tạo đơn hàng và giảm tồn kho

Giả sử business operation:

~~~text
REQUEST (stable request_id)
    |
    v
Check request_id đã xử lý?
    |
    +--> Đã commit, cùng payload -> return stored result
    |
    +--> Đang pending/unknown -> reconcile theo policy
    |
    +--> Chưa tồn tại -> BEGIN TRANSACTION
          |
          +--> Check inventory and business constraints
          +--> Decrement inventory
          +--> Insert order
          +--> Insert request-id record + outbox event
          |
          +--> COMMIT
                |
                +--> Success -> trả order id
                |
                +--> 40001 -> rollback, retry toàn unit
                |
                +--> 08006 -> outcome unknown, reconcile bằng request_id
~~~

Điều đáng lưu ý:

- Retry toàn unit nếu PostgreSQL abort với `40001`; **các quyết định về tồn kho phải tính lại**.
- Side effects như publish event được đưa vào **outbox**, không gửi ra broker trước commit.
- Có một request ID ổn định và unique constraint, giúp nhận diện request lặp từ client/worker.
- Nếu kết nối mất lúc COMMIT, query request ID từ một connection mới trước khi làm lại.
- Nếu request ID đã tồn tại với payload khác, đây là conflict cần xử lý, không coi là duplicate thành công.
- Nếu tồn kho không đủ, đó là business outcome, **không retry** chỉ vì muốn thành công.

## 17. Lỗi phổ biến và cách sửa

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `catch(SQLException) -> retry` | Ghi trùng, load storm, lỗi logic bị che | Classify SQLState/subclass/phase và side effects |
| `instanceof SQLTransientException` là đủ | Timeout/connection lost có thể có unknown outcome | Không đồng nghĩa replay-safe |
| Retry chỉ câu SQL thất bại sau `40001` | Dùng snapshot và quyết định cũ | Retry **entire transaction** |
| Retry trên cùng Connection đang aborted | Driver/session state có thể hỏng | Rollback/close, transaction mới |
| `COMMIT` ném `08006` thì mặc định rollback | Server có thể đã commit | Reconcile bằng business idempotency key |
| `23505` luôn là transient | Có thể là duplicate thật | Fail fast hoặc policy nghiệp vụ cụ thể |
| Bỏ qua rollback error | Không biết transaction đã rollback chưa | Attach suppressed, stop retry |
| Gửi email trong transaction callback rồi retry | Email gửi hai lần | Transactional outbox/idempotent consumers |
| Dùng request ID mới mỗi attempt | Mất khả năng deduplicate | Stable request ID qua toàn bộ retries |
| Retry không giới hạn | Saturate pool/DB | Max attempts, deadline, jitter |
| Sleep khi vẫn giữ connection/lock | Kéo dài contention | Đóng attempt trước khi backoff |
| Nuốt `InterruptedException` | Không thể cancel request | Re-interrupt và dừng |
| Dựa vào exception message text | Fragile, localized/vendor-specific | SQLState + vendor code + phase |
| Áp `40P01` cho mọi DBMS | SQLState/vendor mapping khác nhau | Driver-specific policy |
| Retry ở 3-4 tầng cùng lúc | Attempts nhân lên | Một retry owner và tổng budget |
| Coi `isValid(true)` đảm bảo commit | Network có thể ngắt sau check | Xử lý SQL thực, unknown commit |
| Rely vào một unit mock như DB thật | Không có transaction/server thật | Integration tests có rollback/commit thực |
| Không ghi metrics retries | Không biết khi nào policy hỏng | Quan sát phase, SQLState, attempts, outcome |

## 18. Câu hỏi kiểm tra kiến thức

**Câu 1.** `SQLTransientException` có nghĩa thao tác ghi SQL chắc chắn có thể chạy lại không?

**Trả lời:** Không. Đây là phân loại lỗi có thể tạm thời theo JDBC. Một timeout hoặc mất kết nối ở COMMIT có thể có outcome không rõ; cần phase, semantics và idempotency.

**Câu 2.** PostgreSQL trả `40001`. Nên retry câu UPDATE cuối hay toàn bộ transaction?

**Trả lời:** **Toàn bộ transaction**, gồm đọc dữ liệu và logic quyết định SQL/giá trị. Retry có budget, connection/transaction mới, không phát lại side effects bên ngoài không an toàn.

**Câu 3.** PostgreSQL `40P01` là gì?

**Trả lời:** Deadlock detected; có thể retry whole transaction sau khi rollback, tùy chính sách và max attempts.

**Câu 4.** Vì sao `23505` không được retry mặc định?

**Trả lời:** Unique violation có thể là dữ liệu trùng thật. Một số concurrency cases có thể retry theo tài liệu PostgreSQL, nhưng cần business-specific rule hoặc idempotency reconciliation.

**Câu 5.** Khi `connection.commit()` mất phản hồi mạng, có thể kết luận chưa commit không?

**Trả lời:** Không. Server có thể đã commit; nếu lỗi connection/timeout không bảo đảm abort, phải reconcile với stable business key, không replay mù quáng.

**Câu 6.** `SQLRecoverableException` đòi hỏi điều gì?

**Trả lời:** Tối thiểu đóng connection hiện tại và tạo connection mới trước khi retry theo recovery contract; không có nghĩa transaction trước chắc chắn chưa commit.

**Câu 7.** Retry transaction đã rollback có cần mọi SQL statement là idempotent không?

**Trả lời:** Không nhất thiết với database-only atomic effects khi đã chứng minh rollback; tuy nhiên side effects ngoài database không được rollback nên phải idempotent hoặc chuyển sang outbox.

**Câu 8.** Vì sao không dùng `error.getMessage().contains("deadlock")`?

**Trả lời:** Message thay đổi theo vendor, driver, ngôn ngữ và version. Dùng SQLState, vendor code và subclass đã kiểm chứng.

**Câu 9.** Idempotency key phải thay đổi hay giữ nguyên qua retries?

**Trả lời:** **Giữ nguyên** cho cùng logical business request. Kết quả cũ có thể được lấy lại bằng key khi response bị mất.

**Câu 10.** Nếu `rollback()` ném SQLException, có nên retry ngay không?

**Trả lời:** Không mặc định. Chưa xác nhận rollback/connection health; ghi suppressed exception và dừng hoặc áp recovery theo DB semantics.

**Câu 11.** Timeout ở ACQUIRE khác timeout ở COMMIT thế nào?

**Trả lời:** Tại ACQUIRE chưa có transaction work nên có thể thử mượn connection mới trong budget. Tại COMMIT có thể đã có committed effects nhưng client không nhận kết quả, nên cần reconcile.

**Câu 12.** Tại sao không sleep giữa retries khi đang giữ transaction cũ?

**Trả lời:** Có thể giữ locks/connection pool slot, làm tranh chấp tăng. Đóng/rollback attempt cũ rồi backoff với jitter.

**Câu 13.** Unit test JDBC retry qua dynamic proxy chứng minh điều gì?

**Trả lời:** Chứng minh logic phân loại và thứ tự gọi Java methods theo fixture. Nó **không** chứng minh PostgreSQL/driver thật đã rollback, commit hay mất mạng.

**Câu 14.** Nếu callback transaction gọi HTTP payment API, retry `40001` có an toàn không?

**Trả lời:** Không tự động. DB rollback không đảo ngược HTTP payment. Cần provider idempotency key, outbox/saga hoặc thiết kế side effects được bảo vệ.

**Câu 15.** Tại sao driver close error sau successful commit không nên kích hoạt retry?

**Trả lời:** Commit có thể đã thành công; lỗi cleanup không đồng nghĩa work thất bại. Cần track phase và outcome thay vì dùng catch toàn bộ resource scope để replay.

**Ghi nhớ:** **Retry JDBC an toàn = lỗi + thời điểm xảy ra + khả năng phát lại nghiệp vụ**. PostgreSQL `40001` và nhiều `40P01` cho phép retry **whole transaction** sau rollback với budget; `23505` thường cần fail/reconcile; mất kết nối/timeout tại COMMIT là **unknown outcome** và phải kiểm tra bằng stable idempotency key. Tách DB transaction effects khỏi side effects ngoài DB, dùng outbox khi cần, luôn mở transaction mới và không retry mù quáng.

### Tài liệu chính thức và hiện hành

- [Oracle Java SE 26 — SQLException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html): SQLState, vendor code, nextException, causes.
- [Oracle Java SE 26 — SQLTransientException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransientException.html): nhóm lỗi tạm thời và các subclass.
- [Oracle Java SE 26 — SQLTransactionRollbackException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTransactionRollbackException.html): SQLState class 40, deadlock/serialization.
- [Oracle Java SE 26 — SQLRecoverableException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLRecoverableException.html): recovery cần connection mới.
- [Oracle Java SE 26 — SQLTimeoutException](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLTimeoutException.html): timeout là transient subclass nhưng không tự xác nhận transaction outcome.
- [Oracle Java SE 26 — Connection](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html): autoCommit, commit, rollback, close.
- [PostgreSQL 18 — Serialization Failure Handling](https://www.postgresql.org/docs/18/mvcc-serialization-failure-handling.html): 40001, 40P01, 23505 và yêu cầu retry complete transaction.
- [PostgreSQL 18 — Error Codes](https://www.postgresql.org/docs/18/errcodes-appendix.html): SQLState codes và error classes.

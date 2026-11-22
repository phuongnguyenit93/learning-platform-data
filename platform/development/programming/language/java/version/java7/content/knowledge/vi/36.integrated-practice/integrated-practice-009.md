# Kiểm thử JDBC theo từng loại lỗi và vòng đời tài nguyên

JDBC cung cấp các interface `Connection`, `PreparedStatement`, `ResultSet` để truy cập cơ sở dữ liệu trong Java. Một tác vụ có thể lỗi khi **mở kết nối, chuẩn bị SQL, bind tham số, thực thi, duyệt kết quả, commit/rollback hoặc đóng tài nguyên**. Muốn hệ thống an toàn, kiểm thử phải xác minh cả **lỗi chính**, **lỗi thứ cấp khi dọn dẹp**, **trạng thái transaction** và **tài nguyên còn mở**.

Bài thực hành dùng API JDBC trong Java 17+ còn được hỗ trợ hiện nay, với **11 kịch bản có thể chạy mà không cần database**. Sau đó phân biệt giới hạn của giả lập với integration test dùng driver/DB thật. Trọng tâm là tính đúng đắn và vòng đời tài nguyên, không phải giả định mọi hệ quản trị CSDL trả cùng một mã lỗi.

## 1. Bản đồ vòng đời JDBC

```text
DataSource.getConnection()
    -> Connection
        -> prepareStatement(sql)
            -> PreparedStatement
                -> setInt / setString / ...
                -> executeQuery()
                    -> ResultSet
                        -> next()
                        -> getString / getInt / ...
                        -> close ResultSet
                -> close PreparedStatement
        -> commit / rollback (nếu quản lý transaction)
        -> close Connection
```

`try-with-resources` khởi tạo các tài nguyên trong header **từ trái sang phải** và thử đóng các tài nguyên đã khởi tạo thành công **theo thứ tự ngược**. Với `Connection` → `PreparedStatement` → `ResultSet`, đóng là **ResultSet → PreparedStatement → Connection**.

Đường đi thực tế có thể rẽ trước khi tạo đủ ba đối tượng:

- **`getConnection()` thất bại:** caller chưa nhận connection, nên không có đối tượng hợp lệ để gọi `close()`.
- **`prepareStatement()` thất bại:** connection đã có; Java vẫn thử đóng connection. Chưa có statement hợp lệ.
- **`executeQuery()` thất bại:** connection và statement được thử đóng; result set chưa được trả về.
- **`ResultSet.next()` hoặc `getXxx()` thất bại:** cả result set, statement và connection vẫn được thử đóng.
- **`close()` thất bại:** các lần đóng còn lại vẫn được thử; exception đóng có thể thành primary hoặc suppressed.

`Statement.close()` theo JDBC cũng đóng `ResultSet` hiện tại của nó nếu có, nhưng **đóng ResultSet tường minh** vẫn là thói quen hữu ích: xác định sớm lúc không còn dùng kết quả, dễ kiểm thử ownership và không giữ cursor lâu hơn cần thiết.

Với connection pool, `Connection.close()` thường trả **logical connection** về pool, không đồng nghĩa đóng socket vật lý. Kiểm thử leak ở pool cần quan sát borrowed/active count và việc reset trạng thái của connection, không chỉ đếm số lần gọi `close()` trên một mock.

## 2. Phân loại lỗi cần kiểm thử

| Loại exception Java | Tình huống | Hướng xử lý |
| --- | --- | --- |
| `SQLTransientConnectionException` | Lỗi kết nối có tính tạm thời | Có thể retry có giới hạn nếu an toàn |
| `SQLNonTransientConnectionException` | Kết nối không thể khắc phục bằng lặp lại đơn giản | Sửa cấu hình/quyền hoặc thay connection |
| `SQLTimeoutException` | Hết thời gian chờ query/login theo API | Xác định trạng thái thực thi trước khi retry |
| `SQLSyntaxErrorException` | SQL sai cú pháp hoặc không hợp lệ | Sửa câu SQL, schema hoặc quyền |
| `SQLIntegrityConstraintViolationException` | Unique/foreign key/check constraint | Sửa dữ liệu hoặc luồng nghiệp vụ |
| `SQLTransactionRollbackException` | Deadlock, serialization conflict tùy DB | Rollback rồi có thể retry **toàn transaction** |
| `SQLRecoverableException` | Lỗi yêu cầu bước phục hồi đặc biệt | Ít nhất đóng connection cũ, lấy connection mới |
| `SQLFeatureNotSupportedException` | Driver không hỗ trợ tính năng | Thay cách triển khai, không retry mù |
| `BatchUpdateException` | Lỗi khi thực hiện batch | Kiểm `getUpdateCounts()`, `getNextException()` và transaction |
| `SQLException` chung | Lỗi đọc, execute, close hoặc driver không phân lớp chi tiết | Đọc SQLState, vendor code và exception chain |

Các lớp trên nằm trong `java.sql` hiện hành. `SQLTransientException` mô tả tình huống có thể thành công khi thử lại; **không bảo đảm retry an toàn về mặt nghiệp vụ**, đặc biệt sau lỗi mạng/timeout lúc ghi. `SQLRecoverableException` yêu cầu thao tác recovery, thường có connection mới.

### Đọc lỗi đúng cách

`SQLException` cung cấp **`getMessage()`**, **`getSQLState()`**, **`getErrorCode()`** và **`getNextException()`**. SQLState có thể theo chuẩn SQL hoặc XOPEN; hai ký tự đầu thường là nhóm: `08` kết nối, `23` integrity, `40` transaction rollback, `42` syntax/access. Mã chi tiết và vendor code **khác nhau giữa các DB/driver**, một số lỗi có SQLState `null`.

Ba đường thông tin khác nhau:

- `getNextException()`: chuỗi SQLException do JDBC/driver cung cấp.
- `getCause()`: lỗi nguyên nhân của exception được bọc.
- `getSuppressed()`: lỗi thứ cấp khi cleanup hoặc code chủ động `addSuppressed()`; **không phải** chuỗi `getNextException()`.

Khi assert integration test, ưu tiên hành vi và SQLState theo **driver thật**; không so sánh message tùy locale/phiên bản nếu không có yêu cầu riêng.

## 3. Ma trận điểm lỗi và thao tác cleanup

| Điểm xảy ra lỗi | Resource có thể đã được mở | Thứ tự được thử đóng |
| --- | --- | --- |
| `getConnection` | Chưa có resource trong caller | Không có |
| `prepareStatement` | Connection | Connection |
| `setInt` / bind | Connection, statement | Statement → Connection |
| `executeQuery` / `executeUpdate` | Connection, statement | Statement → Connection |
| `ResultSet.next` / `getString` | Connection, statement, result | Result → Statement → Connection |
| `ResultSet.close` | Result có rồi | Result (lỗi) → Statement → Connection |
| `Statement.close` | Statement có rồi | Statement (lỗi) → Connection |
| `Connection.close` | Connection có rồi | Connection (lỗi) |
| Execute lỗi + đóng statement và connection cùng lỗi | Statement + connection | Cả hai close vẫn được thử; lỗi execute là **primary** |
| Commit/rollback lỗi | Connection thuộc transaction | Xử lý outcome và lỗi thứ cấp; không để transaction treo |

Nếu một tài nguyên trong header chưa **khởi tạo thành công**, `try-with-resources` không thể tự đóng đối tượng chưa được trả về. Bên trong constructor/factory/driver, việc mở tài nguyên rồi lỗi trước khi trả đối tượng cần được chính thành phần đó dọn dẹp.

## 4. Bài thực hành Java 17+: tạo 11 lỗi JDBC không cần database

Chương trình sử dụng `java.lang.reflect.Proxy` để tạo bản giả lập một phần các interface JDBC. Fake ghi từng thao tác vào danh sách sự kiện và ném `SQLException` tại điểm được chỉ định. **Không có SQL parser, network, transaction engine hay driver thật**; các mã SQLState là giá trị mô phỏng để minh họa phân loại.

Lưu mã vào tệp **`JdbcFailureLab.java`**:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;
import java.sql.*;
import java.util.*;

public final class JdbcFailureLab {
    enum Fault {
        NONE, CONNECT, PREPARE, TIMEOUT, INTEGRITY, DEADLOCK,
        READ, CLOSE_RESULT, CLOSE_STATEMENT, CLOSE_CONNECTION,
        TIMEOUT_AND_CLOSE
    }

    static final class Fake {
        final Fault fault;
        final List<String> events = new ArrayList<>();

        Fake(Fault fault) {
            this.fault = fault;
        }

        private static <T> T proxy(
                Class<T> api, InvocationHandler handler) {
            return api.cast(Proxy.newProxyInstance(
                    api.getClassLoader(),
                    new Class<?>[] { api }, handler));
        }

        Connection connect() throws SQLException {
            events.add("connect");
            if (fault == Fault.CONNECT) {
                throw new SQLTransientConnectionException(
                        "connect failed", "08001");
            }
            return proxy(Connection.class, (obj, method, args) -> {
                return switch (method.getName()) {
                    case "prepareStatement" -> {
                        events.add("prepare");
                        if (fault == Fault.PREPARE) {
                            throw new SQLSyntaxErrorException(
                                    "prepare failed", "42000");
                        }
                        yield statement();
                    }
                    case "close" -> {
                        events.add("close connection");
                        if (fault == Fault.CLOSE_CONNECTION
                                || fault == Fault.TIMEOUT_AND_CLOSE) {
                            throw new SQLException(
                                    "connection close failed", "08006");
                        }
                        yield null;
                    }
                    default -> throw new UnsupportedOperationException(
                            "Not simulated: Connection."
                                    + method.getName());
                };
            });
        }

        PreparedStatement statement() {
            return proxy(PreparedStatement.class, (obj, method, args) -> {
                return switch (method.getName()) {
                    case "setInt" -> {
                        events.add("bind");
                        yield null;
                    }
                    case "executeQuery" -> {
                        events.add("executeQuery");
                        if (fault == Fault.TIMEOUT
                                || fault == Fault.TIMEOUT_AND_CLOSE) {
                            throw new SQLTimeoutException(
                                    "query timed out", "HYT00");
                        }
                        yield resultSet();
                    }
                    case "executeUpdate" -> {
                        events.add("executeUpdate");
                        if (fault == Fault.INTEGRITY) {
                            throw new SQLIntegrityConstraintViolationException(
                                    "duplicate key", "23505");
                        }
                        if (fault == Fault.DEADLOCK) {
                            throw new SQLTransactionRollbackException(
                                    "deadlock", "40001");
                        }
                        yield 1;
                    }
                    case "close" -> {
                        events.add("close statement");
                        if (fault == Fault.CLOSE_STATEMENT
                                || fault == Fault.TIMEOUT_AND_CLOSE) {
                            throw new SQLException(
                                    "statement close failed", "HY000");
                        }
                        yield null;
                    }
                    default -> throw new UnsupportedOperationException(
                            "Not simulated: PreparedStatement."
                                    + method.getName());
                };
            });
        }

        ResultSet resultSet() {
            boolean[] alreadyRead = { false };
            return proxy(ResultSet.class, (obj, method, args) -> {
                return switch (method.getName()) {
                    case "next" -> {
                        events.add("next");
                        if (fault == Fault.READ) {
                            throw new SQLException(
                                    "row read failed", "HY000");
                        }
                        if (!alreadyRead[0]) {
                            alreadyRead[0] = true;
                            yield true;
                        }
                        yield false;
                    }
                    case "getString" -> "sample";
                    case "close" -> {
                        events.add("close result");
                        if (fault == Fault.CLOSE_RESULT) {
                            throw new SQLException(
                                    "result close failed", "HY000");
                        }
                        yield null;
                    }
                    default -> throw new UnsupportedOperationException(
                            "Not simulated: ResultSet."
                                    + method.getName());
                };
            });
        }
    }

    static void run(Fault fault) {
        Fake fake = new Fake(fault);
        boolean write = fault == Fault.INTEGRITY
                || fault == Fault.DEADLOCK;
        String sql = write
                ? "INSERT INTO demo(id) VALUES (?)"
                : "SELECT label FROM demo WHERE id = ?";

        try (Connection connection = fake.connect();
             PreparedStatement statement =
                     connection.prepareStatement(sql)) {
            statement.setInt(1, 7);

            if (write) {
                fake.events.add("rows=" + statement.executeUpdate());
            } else {
                try (ResultSet result = statement.executeQuery()) {
                    if (result.next()) {
                        fake.events.add(
                                "row=" + result.getString(1));
                    }
                }
            }
        } catch (SQLException error) {
            fake.events.add(
                    "error=" + error.getClass().getSimpleName()
                            + "/" + error.getSQLState());
            for (Throwable ignoredDuringClose
                    : error.getSuppressed()) {
                fake.events.add(
                        "suppressed="
                                + ignoredDuringClose.getMessage());
            }
        }
        System.out.println(
                fault + ": " + String.join(" > ", fake.events));
    }

    public static void main(String[] args) {
        for (Fault fault : Fault.values()) {
            run(fault);
        }
    }
}
```

Biên dịch và chạy (JDK 17 trở lên, không cần thư viện khác):

```bash
javac -encoding UTF-8 JdbcFailureLab.java
java JdbcFailureLab
```

**Stdout chính xác** của chương trình:

```text
NONE: connect > prepare > bind > executeQuery > next > row=sample > close result > close statement > close connection
CONNECT: connect > error=SQLTransientConnectionException/08001
PREPARE: connect > prepare > close connection > error=SQLSyntaxErrorException/42000
TIMEOUT: connect > prepare > bind > executeQuery > close statement > close connection > error=SQLTimeoutException/HYT00
INTEGRITY: connect > prepare > bind > executeUpdate > close statement > close connection > error=SQLIntegrityConstraintViolationException/23505
DEADLOCK: connect > prepare > bind > executeUpdate > close statement > close connection > error=SQLTransactionRollbackException/40001
READ: connect > prepare > bind > executeQuery > next > close result > close statement > close connection > error=SQLException/HY000
CLOSE_RESULT: connect > prepare > bind > executeQuery > next > row=sample > close result > close statement > close connection > error=SQLException/HY000
CLOSE_STATEMENT: connect > prepare > bind > executeQuery > next > row=sample > close result > close statement > close connection > error=SQLException/HY000
CLOSE_CONNECTION: connect > prepare > bind > executeQuery > next > row=sample > close result > close statement > close connection > error=SQLException/08006
TIMEOUT_AND_CLOSE: connect > prepare > bind > executeQuery > close statement > close connection > error=SQLTimeoutException/HYT00 > suppressed=statement close failed > suppressed=connection close failed
```

### Đọc kết quả theo từng loại lỗi

- **NONE:** mở connection, tạo statement, bind, đọc một row; đóng result → statement → connection.
- **CONNECT:** ngay bước đầu đã lỗi; không có tài nguyên thuộc caller để đóng.
- **PREPARE:** connection đã mở nên vẫn được đóng; statement chưa tạo thành công.
- **TIMEOUT:** execute chưa trả result set; chỉ statement và connection cần đóng. `HYT00` do mock tự đặt, không phải mã bắt buộc trên mọi DB.
- **INTEGRITY:** mô phỏng vi phạm ràng buộc ở `executeUpdate()`; không retry cùng dữ liệu sai.
- **DEADLOCK:** giả lập `SQLTransactionRollbackException` khi ghi; trong DB thật có thể phải rollback rồi chạy lại **cả transaction**.
- **READ:** lỗi ở `ResultSet.next()`; Java vẫn cố đóng đủ ba resource.
- **CLOSE_RESULT / CLOSE_STATEMENT / CLOSE_CONNECTION:** phần xử lý trước đó đã thành công, nhưng lỗi cleanup trở thành primary; các close còn lại vẫn được gọi.
- **TIMEOUT_AND_CLOSE:** lỗi chính vẫn là `SQLTimeoutException`; hai lỗi đóng lần lượt thành **suppressed**. Không dùng `finally` nối tiếp các lệnh `close()` mà không bảo vệ từng lệnh, vì lỗi close đầu tiên có thể che lỗi chính và bỏ qua close còn lại.

Fake này không kiểm tra việc `Statement.close()` tự đóng `ResultSet` đang mở, vì chương trình đã đóng result tường minh. Hành vi tự đóng của JDBC driver thật cần integration test riêng.

## 5. Kiểm thử transaction: commit, rollback và lỗi không chắc kết quả

**Đóng connection không phải là commit hay rollback.** Theo Java SE `Connection`, khi ứng dụng dùng `setAutoCommit(false)`, nó nên **commit/rollback tường minh trước khi đóng**. Gọi `close()` khi transaction vẫn mở có kết quả phụ thuộc implementation. Đừng trông chờ mặc định “driver tự rollback an toàn”.

Mẫu phương thức dùng `DataSource` thực (đoạn **tích hợp**, cần DB/schema tương ứng):

```java
static int insertInTransaction(
        javax.sql.DataSource source,
        long id,
        String label) throws java.sql.SQLException {

    try (java.sql.Connection connection =
                 source.getConnection()) {
        connection.setAutoCommit(false);

        try {
            int count;

            try (java.sql.PreparedStatement statement =
                         connection.prepareStatement(
                                 "INSERT INTO demo(id, label) VALUES (?, ?)")) {
                statement.setLong(1, id);
                statement.setString(2, label);
                count = statement.executeUpdate();
            }

            connection.commit();
            return count;

        } catch (java.sql.SQLException primary) {
            try {
                connection.rollback();
            } catch (java.sql.SQLException rollbackFailure) {
                primary.addSuppressed(rollbackFailure);
            }
            throw primary;
        }
    }
}
```

Các ca cần có khi chạy DB thật:

1. **Commit thành công:** dữ liệu xuất hiện qua connection khác; connection được trả pool/đóng.
2. **Insert lỗi trước commit:** rollback được thử, không có dữ liệu dở dang tồn tại sau rollback.
3. **Rollback cũng lỗi:** primary từ SQL gốc không mất, rollback được giữ bằng suppressed; connection hỏng không được tái sử dụng thiếu an toàn.
4. **Commit ném SQLException:** có thể **không xác định server đã commit hay chưa** (ví dụ mất phản hồi). Rollback thử sau đó **không chứng minh** giao dịch chưa từng commit. Cần đối soát theo business key, idempotency và quy tắc DB trước khi retry.
5. **Close connection lỗi:** giữ exception; không cho rằng ứng dụng đã trả connection thành công.
6. **Pool reuse:** xác minh trạng thái auto-commit/isolation/read-only không rò từ request trước sang request sau.

Không đặt `setAutoCommit(true)` vô điều kiện vào `finally` trong khi giao dịch có thể chưa hoàn tất: việc chuyển chế độ có thể dẫn tới commit theo JDBC. Connection pool có thể reset trạng thái theo contract riêng; kiểm thử chính xác pool đó.

## 6. Thiết kế kiểm thử thật có thể tin cậy

**Unit test:** tiêm lỗi vào từng phương thức gọi của code, ghi sự kiện và assert **thứ tự cleanup**; ví dụ đã chạy dùng Proxy/JDK thuần. Để dùng trong JUnit, tách `run` thành hàm trả về primary `SQLException` và sự kiện của fake; sau đó assert `getSuppressed().length == 2` trong ca `TIMEOUT_AND_CLOSE`.

**Integration test:** dùng một database test với schema/migration, cùng driver/version và cấu hình pooling như hệ thống thực. Các ca quan trọng gồm:

| Ca | Assertion quan trọng |
| --- | --- |
| Query/insert thành công | Row đúng và connection/statement được đóng |
| Trùng unique key | Không có bản ghi sai; SQLState thực đúng với driver được chọn |
| Syntax error | Kiểm tra lỗi ở prepare hoặc execute, không giả định lúc nào |
| Deadlock/serialization conflict | Dùng **hai transaction phối hợp**; thử rollback và retry toàn transaction khi an toàn |
| Query timeout | Kiểm tra query được hủy, connection còn dùng được không, trạng thái DB sau timeout |
| Đọc nhiều row rồi lỗi | Kết quả dở dang được phát hiện, không âm thầm trả “thành công” |
| Commit/rollback failure | Bảo toàn primary, suppressed và quản lý connection nghi vấn |
| Trả connection về pool | Số borrowed connections trở về baseline; state reset đúng |
| Driver mất kết nối | Connection hỏng bị loại, lỗi có thể quan sát, retry bị giới hạn |

Không dựa vào `Thread.sleep()` để tạo deadlock ổn định; dùng các điểm đồng bộ giữa hai connection. Không giả định lỗi constraint/timeout có cùng subclass hoặc SQLState trên PostgreSQL, MySQL, Oracle, SQL Server hay các driver khác.

**Resilience test:** mô phỏng database restart, mạng gián đoạn, hết connection pool, mất phản hồi commit. Các trường hợp này cần môi trường test riêng. Retry phải có **giới hạn, backoff, deadline và idempotency**; không retry một thao tác ghi chỉ vì ngoại lệ là `SQLTransientException`.

## 7. Những lỗi thường gặp

| Sai lầm | Hậu quả và cách sửa |
| --- | --- |
| Mở connection ngoài `try-with-resources` | Prepare lỗi có thể rò connection; đưa connection vào header `try` ngay từ đầu |
| Không đóng result set sớm | Cursor/statement sống quá lâu; dùng `try (ResultSet rs = ...)` |
| Nối nhiều `close()` trong `finally` | Close đầu ném lỗi làm bỏ qua close sau; dùng `try-with-resources` |
| Chỉ log `getMessage()` | Mất stack trace, suppressed, chain; log exception đầy đủ và che dữ liệu nhạy cảm |
| Nhầm `getNextException()` với `getSuppressed()` | Hai cấu trúc khác nhau; kiểm cả hai khi cần |
| Retry mọi `SQLException` | Có thể ghi trùng và tăng tải; phân loại theo contract + idempotency |
| Dựa vào SQLState giả lập như mã chuẩn mọi DB | Integration test phải đo SQLState thật của driver |
| Coi `Connection.close()` là rollback | Commit/rollback rõ ràng trước khi close |
| Coi `executeUpdate()` thành công là transaction đã commit | Nếu autoCommit=false, cần `commit()` và xác minh |
| Dùng mock làm bằng chứng driver không leak | Mock chỉ kiểm tra lời gọi; phải đo pool/DB thật |
| Không xử lý kết quả commit bất định | Có thể retry và tạo giao dịch trùng; cần đối soát/idempotency |

## 8. Bài tập tự kiểm tra

1. Thêm lỗi ở `PreparedStatement.setInt`; dự đoán log đóng statement rồi connection và không có execute.
2. Thêm lỗi ở `ResultSet.getString` thay vì `next`; xác minh vẫn thử đóng đủ ba resource.
3. Sửa fake để `ResultSet.close` và `Statement.close` cùng lỗi sau một lần đọc thành công. Dự đoán **primary là lỗi đóng result**, lỗi đóng statement trở thành suppressed, connection vẫn được thử đóng.
4. Tách chương trình thành hàm trả primary exception; viết unit test kiểm tra subtype, SQLState được tiêm, thứ tự sự kiện, số lượng và thứ tự suppressed.
5. Thêm test `BatchUpdateException` với `getUpdateCounts()`; phân biệt số row đã thực thi với việc toàn transaction có commit hay không.
6. Với DB test thật, thử insert hai row trùng unique key, rollback, rồi query bằng connection khác để xác minh không còn thay đổi chưa commit.
7. Tạo integration test cho connection pool: borrow connection, đổi `autoCommit`, đóng/trả; borrow lại và kiểm tra pool reset trạng thái theo contract.
8. Thiết kế một chính sách retry an toàn cho deadlock/serialization failure, có giới hạn lần và bảo vệ chống duplicate write.

## 9. Checklist trước khi áp dụng production

- [ ] Có ownership rõ và `try-with-resources` cho Connection, Statement, ResultSet?
- [ ] Đã thử lỗi ở connect, prepare, bind, execute, read, close?
- [ ] Primary exception và suppressed đều được bảo toàn?
- [ ] Transaction commit/rollback được xử lý rõ ràng trước khi trả connection?
- [ ] Có kiểm thử kết quả commit không xác định và chính sách idempotency?
- [ ] Có integration test cho SQLState và vendor error code thực?
- [ ] Deadlock và timeout không được xử lý bằng retry vô hạn?
- [ ] Có metrics về connection leak/pool exhausted và cảnh báo phù hợp?
- [ ] Không log credentials hoặc dữ liệu nhạy cảm trong SQL parameters?
- [ ] Các test DB có cleanup và không làm thay đổi dữ liệu production?

## Kết luận

Kiểm thử JDBC phải bao quát **phân loại lỗi, điểm lỗi trong luồng xử lý và vòng đời mọi tài nguyên**. `try-with-resources` bảo đảm nỗ lực đóng theo thứ tự ngược và giữ lỗi đóng thứ cấp bằng suppressed exceptions. Tuy nhiên, tính nhất quán transaction, hành vi network timeout, trạng thái connection pool và mã SQLState thực tế **phải được kiểm chứng bằng database/driver thật**. Kết hợp fault-injection unit test, integration test và quản lý transaction tường minh là phương pháp phù hợp với Java hiện đại.

## Tài liệu tham khảo chính thức

- [java.sql package — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/package-summary.html)
- [Connection — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Connection.html)
- [Statement — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/Statement.html)
- [PreparedStatement — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/PreparedStatement.html)
- [ResultSet — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/ResultSet.html)
- [SQLException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLException.html)
- [SQLRecoverableException — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.sql/java/sql/SQLRecoverableException.html)
- [Try-with-resources — JLS SE 25 `14.20.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.20.3)

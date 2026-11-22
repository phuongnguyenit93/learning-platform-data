# Kiểm thử commit, rollback và savepoint

Trong **JDBC**, gọi `Connection.commit()`, `Connection.rollback()` hay `Connection.rollback(Savepoint)` là thao tác trên **transaction thực của cơ sở dữ liệu**, không chỉ là một lời gọi Java. Một unit test kiểm tra rằng phương thức `commit()` đã được gọi chưa thể chứng minh các dòng SQL đã được lưu bền vững. Muốn kiểm thử đúng, cần chuẩn bị dữ liệu đã commit, thực hiện thay đổi trong transaction được kiểm soát, **kết thúc transaction**, rồi xác nhận trạng thái database bằng một connection khác.

Bài học thuộc chương **Kiểm thử JDBC** của module **JDBC**. Chúng ta sẽ dùng `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` và `Savepoint` để thử ba tính chất: **commit lưu đủ dữ liệu**, **rollback hủy toàn bộ thay đổi chưa commit**, và **rollback tới savepoint chỉ hủy phần sau mốc**. Ngoài đường đi thành công, bài học còn bao gồm lỗi SQL, connection pool, transaction do framework quản lý, môi trường CI và những trường hợp commit không chắc chắn.

## 1. Kết quả cần đạt

Sau khi hoàn thành bài, bạn có thể:

1. Phân biệt test dùng mock với test transaction tích hợp trên database thật.
2. Tạo fixture và cleanup trong các transaction **độc lập với transaction cần kiểm thử**.
3. Kiểm tra cả dữ liệu chính và dữ liệu phụ sau `commit()`/`rollback()`.
4. Sử dụng **connection quan sát mới** để tránh kết luận sai do *read-your-writes*.
5. Thử `Savepoint` và chứng minh transaction ngoài vẫn quyết định commit.
6. Dùng `DatabaseMetaData.supportsSavepoints()` để biết khả năng được driver công bố.
7. Kiểm tra đường đi có `SQLException`, constraint violation và rollback lỗi.
8. Tránh các bẫy `autoCommit`, DDL implicit commit và `@Transactional` bao quanh test.
9. Thiết kế test lặp lại được trong CI mà không tác động dữ liệu của test khác.
10. Phân loại các lỗi timeout, deadlock, serialization và **commit outcome bất định**.

## 2. Hợp đồng giao dịch của JDBC

| API | Ý nghĩa | Assertion cần có |
| --- | --- | --- |
| `setAutoCommit(false)` | Ứng dụng chủ động xác nhận hoặc hủy transaction | Các lệnh DML trong một transaction thực sự |
| `commit()` | Xác nhận các thay đổi chưa commit | Một connection **khác** đọc được kết quả mới |
| `rollback()` | Hủy toàn bộ thay đổi chưa commit | Database trở về trạng thái đã commit trước transaction |
| `setSavepoint()` | Tạo mốc trong transaction hiện hành | Có thể quay lui phần việc sau mốc |
| `setSavepoint("step")` | Tạo mốc có tên | Savepoint tồn tại, thao tác sau đó được phân biệt rõ |
| `rollback(savepoint)` | Quay về mốc, không kết thúc transaction ngoài | Dữ liệu trước mốc còn trong transaction, phần sau mốc bị hủy |
| `releaseSavepoint(savepoint)` | Giải phóng mốc theo driver/DBMS | **Không** commit phần việc trước mốc |
| `getMetaData().supportsSavepoints()` | Driver công bố khả năng savepoint | Test có chính sách fail hoặc skip phù hợp |

Một `Savepoint` **không phải giao dịch con có commit độc lập**. Khi gọi `rollback(savepoint)`, transaction hiện tại vẫn mở. Nó còn có thể bị `rollback()` toàn bộ, khi đó cả thay đổi **trước** savepoint cũng biến mất.

~~~mermaid
sequenceDiagram
    participant T as Connection T
    participant DB as Database
    T->>DB: setAutoCommit(false)
    T->>DB: UPDATE A (bắt buộc)
    T->>DB: setSavepoint("optional")
    T->>DB: INSERT B (tùy chọn)
    T->>DB: rollback(savepoint)
    Note over T,DB: B bị hủy; A vẫn chưa commit
    T->>DB: commit()
    Note over T,DB: Chỉ A trở thành dữ liệu đã commit
~~~

### Các kết luận mà test phải phân biệt

- `commit()` **không ném exception** chưa đủ: câu SQL có thể cập nhật **0 dòng** hoặc thao tác không đúng bảng.
- `rollback()` **được gọi** chưa đủ: DML có thể đã auto-commit trước đó hoặc được thực hiện trên connection khác.
- Đọc lại từ chính writer **trước commit** chưa đủ: transaction thông thường đọc thấy thay đổi của chính nó.
- Kiểm tra chỉ một bảng chưa đủ nếu nghiệp vụ phải thay đổi nhiều bảng một cách nguyên tử.
- Gọi `releaseSavepoint` thành công không có nghĩa phần việc trước mốc đã commit.

## 3. Unit test và integration test bổ sung cho nhau

Giả sử một unit test dùng thư viện mock:

~~~java
// Pseudocode; không phải ví dụ tự chạy.
verify(connection).setAutoCommit(false);
verify(connection).commit();
~~~

Điều này hữu ích để xác minh **thứ tự gọi API** và **nhánh xử lý exception**, nhưng không chứng minh DBMS đã ghi đúng. Các khác biệt như transaction mode, engine lưu trữ, khóa ngoại, savepoint và cách DBMS phản ứng sau SQL error chỉ được kiểm chứng đáng tin cậy bằng **database thật**.

| Loại test | Tốt cho | Không chứng minh được |
| --- | --- | --- |
| Unit test logic | Quyết định có commit/rollback, lỗi nghiệp vụ | Thay đổi dữ liệu thực sự đã được commit |
| Mock JDBC | Binding, gọi statement, xử lý exception | Constraint, lock, savepoint của DBMS |
| Embedded database khác production | Test nhanh mapper và CRUD cơ bản | Mọi ngữ nghĩa transaction của production DBMS |
| Integration test đúng loại DBMS | DML commit/rollback, savepoint, constraint | Sự cố mạng production nếu không fault-inject |
| Fault injection | Timeout, network failure, kết quả commit bất định | Mọi quy tắc nghiệp vụ nếu thiếu assertion dữ liệu |

Hãy dùng **cùng DBMS/driver** với hệ thống triển khai cho các test transaction quan trọng. Test chạy tốt trên H2 không tự chứng minh PostgreSQL, MySQL InnoDB, SQL Server hay Oracle sẽ có hành vi lỗi SQL giống hệt.

## 4. Dữ liệu thử và ranh giới transaction

Tạo bảng trước khi chạy test bằng migration hoặc setup riêng. SQL minh họa:

~~~sql
CREATE TABLE tx_test_account (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
);

CREATE TABLE tx_test_event (
    id BIGINT PRIMARY KEY,
    account_id BIGINT NOT NULL,
    note VARCHAR(80) NOT NULL
);
~~~

Mỗi phép thử dùng ID riêng, ví dụ:

| Phép thử | `account_id` | `event_id` | Fixture đã commit |
| --- | ---: | ---: | --- |
| Commit | 70001 | 80001 | Balance = 100.00; 0 event |
| Rollback | 70002 | 80002 | Balance = 100.00; 0 event |
| Savepoint | 70003 | 80003 | Balance = 100.00; 0 event |

Lớp code ở phần sau **tự seed và cleanup** theo ID. Cấu trúc không dùng ID tự tăng để fixture dễ đoán; trong CI chạy song song hãy phân vùng ID theo test run hoặc dùng schema/database riêng.

**Không tạo bảng bên trong transaction đang test rollback.** Nhiều DBMS thực hiện *implicit commit* với một số lệnh DDL. Nếu trộn `CREATE TABLE` với `UPDATE` rồi `rollback()`, bạn có thể vô tình đo hành vi DDL thay vì tính nguyên tử của DML.

### Trình tự kiểm thử chuẩn

~~~mermaid
flowchart TD
    S["SETUP: seed fixture và COMMIT"] --> A["ACT: bắt đầu transaction, chạy DML"]
    A --> E["END: commit, rollback, hoặc rollback savepoint + commit"]
    E --> O["OBSERVE: mở connection khác để đọc trạng thái cuối"]
    O --> V["ASSERT: balance và event count đúng"]
    V --> C["CLEANUP: xóa fixture và COMMIT riêng"]
~~~

Các lưu ý:

1. **Seed phải được commit** trước khi transaction cần thử bắt đầu.
2. **Writer phải tắt auto-commit** trước câu DML đầu tiên.
3. **Observer chạy sau khi writer kết thúc**; không dùng connection writer để kết luận commit.
4. Assert **đủ các hiệu ứng**, ví dụ balance và số event, không chỉ số dòng từ `executeUpdate()`.
5. **Cleanup dùng transaction riêng** và chạy kể cả khi assertion thất bại.
6. Nếu cleanup thất bại, test phải báo lỗi; không âm thầm để fixture rác trong database.
7. Không chạy các test này trên database production hoặc database dùng chung mà không được phép.

## 5. Ví dụ Java đầy đủ: bộ kiểm chứng transaction dùng DataSource

Đây là lớp Java 8+ dùng **JDBC thuần**, không phụ thuộc JUnit. Nó có ba phương thức `verifyCommit`, `verifyRollback` và `verifySavepoint`. Mỗi phương thức sẽ ném `AssertionError` nếu trạng thái cuối không đúng. `DataSource` phải được cung cấp từ hạ tầng test trỏ vào database đã tạo hai bảng ở phần 4.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Savepoint;
import java.sql.SQLFeatureNotSupportedException;
import java.util.Objects;
import javax.sql.DataSource;

public final class TransactionProbe {
    private final DataSource dataSource;

    public TransactionProbe(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource);
    }

    @FunctionalInterface
    private interface SqlWork {
        void run(Connection connection) throws SQLException;
    }

    private static BigDecimal amount(String text) {
        return new BigDecimal(text);
    }

    private static void rollbackBestEffort(
            Connection connection, Throwable failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            failure.addSuppressed(rollbackError);
        }
    }

    private void runSetupTransaction(SqlWork work)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                work.run(connection);
                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                rollbackBestEffort(connection, failure);
                throw failure;
            }
        }
    }

    private static void deleteEvents(
            Connection c, long accountId) throws SQLException {
        try (PreparedStatement ps = c.prepareStatement(
                "DELETE FROM tx_test_event WHERE account_id = ?")) {
            ps.setLong(1, accountId);
            ps.executeUpdate();
        }
    }

    private static void deleteAccount(
            Connection c, long accountId) throws SQLException {
        try (PreparedStatement ps = c.prepareStatement(
                "DELETE FROM tx_test_account WHERE id = ?")) {
            ps.setLong(1, accountId);
            ps.executeUpdate();
        }
    }

    private static void insertAccount(
            Connection c, long id, BigDecimal balance)
            throws SQLException {
        String sql = "INSERT INTO tx_test_account (id, balance) "
                   + "VALUES (?, ?)";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, id);
            ps.setBigDecimal(2, balance);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Fixture INSERT không thành công");
            }
        }
    }

    private static void updateBalance(
            Connection c, long id, BigDecimal balance)
            throws SQLException {
        String sql = "UPDATE tx_test_account SET balance = ? "
                   + "WHERE id = ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setBigDecimal(1, balance);
            ps.setLong(2, id);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("UPDATE không tác động đúng 1 dòng");
            }
        }
    }

    private static void insertEvent(
            Connection c, long eventId, long accountId, String note)
            throws SQLException {
        String sql = "INSERT INTO tx_test_event "
                   + "(id, account_id, note) VALUES (?, ?, ?)";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, eventId);
            ps.setLong(2, accountId);
            ps.setString(3, note);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Event INSERT không thành công");
            }
        }
    }

    private static BigDecimal readBalance(
            Connection c, long accountId) throws SQLException {
        String sql = "SELECT balance FROM tx_test_account WHERE id = ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, accountId);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Không có fixture account");
                }
                BigDecimal value = rs.getBigDecimal("balance");
                if (value == null) {
                    throw new SQLException("balance là NULL");
                }
                return value;
            }
        }
    }

    private static int countEvents(
            Connection c, long accountId) throws SQLException {
        String sql = "SELECT COUNT(*) FROM tx_test_event "
                   + "WHERE account_id = ?";
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            ps.setLong(1, accountId);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    throw new SQLException("Không có kết quả COUNT");
                }
                return rs.getInt(1);
            }
        }
    }

    private static void requireMoney(
            String expected, BigDecimal actual) {
        if (amount(expected).compareTo(actual) != 0) {
            throw new AssertionError(
                    "Expected balance=" + expected
                  + ", actual=" + actual);
        }
    }

    private static void requireEvents(
            int expected, int actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "Expected events=" + expected
                  + ", actual=" + actual);
        }
    }

    private void seed(long accountId) throws SQLException {
        runSetupTransaction(c -> {
            deleteEvents(c, accountId);
            deleteAccount(c, accountId);
            insertAccount(c, accountId, amount("100.00"));
        });
    }

    private void cleanup(long accountId) throws SQLException {
        runSetupTransaction(c -> {
            deleteEvents(c, accountId);
            deleteAccount(c, accountId);
        });
    }

    private void assertFinalState(
            long accountId, String balance, int events)
            throws SQLException {
        // Không dùng writer: quan sát sau transaction
        // bằng một connection khác của DataSource.
        try (Connection observer = dataSource.getConnection()) {
            requireMoney(balance, readBalance(observer, accountId));
            requireEvents(events, countEvents(observer, accountId));
        }
    }

    public void verifyCommit(long accountId, long eventId)
            throws SQLException {
        seed(accountId);
        try {
            try (Connection writer = dataSource.getConnection()) {
                writer.setAutoCommit(false);
                try {
                    updateBalance(writer, accountId, amount("135.00"));
                    insertEvent(writer, eventId, accountId, "committed");
                    writer.commit();
                } catch (SQLException | RuntimeException failure) {
                    rollbackBestEffort(writer, failure);
                    throw failure;
                }
            }
            // Cả hai câu SQL phải được commit.
            assertFinalState(accountId, "135.00", 1);
        } finally {
            cleanup(accountId);
        }
    }

    public void verifyRollback(long accountId, long eventId)
            throws SQLException {
        seed(accountId);
        try {
            try (Connection writer = dataSource.getConnection()) {
                writer.setAutoCommit(false);
                try {
                    updateBalance(writer, accountId, amount("135.00"));
                    insertEvent(writer, eventId, accountId, "discarded");
                    writer.rollback();
                } catch (SQLException | RuntimeException failure) {
                    rollbackBestEffort(writer, failure);
                    throw failure;
                }
            }
            // Không có thay đổi chưa commit nào tồn tại.
            assertFinalState(accountId, "100.00", 0);
        } finally {
            cleanup(accountId);
        }
    }

    public void verifySavepoint(long accountId, long eventId)
            throws SQLException {
        seed(accountId);
        try {
            try (Connection writer = dataSource.getConnection()) {
                DatabaseMetaData meta = writer.getMetaData();
                if (!meta.supportsSavepoints()) {
                    throw new SQLFeatureNotSupportedException(
                            "Driver/DBMS không hỗ trợ savepoint");
                }

                writer.setAutoCommit(false);
                try {
                    // Bước bắt buộc nằm TRƯỚC savepoint.
                    updateBalance(writer, accountId, amount("120.00"));

                    Savepoint point =
                            writer.setSavepoint("optional_stage");

                    // Hai thao tác tùy chọn nằm SAU savepoint.
                    insertEvent(writer, eventId, accountId, "optional");
                    updateBalance(writer, accountId, amount("999.00"));

                    writer.rollback(point);

                    // Kiểm chứng trạng thái trong transaction.
                    requireMoney("120.00",
                            readBalance(writer, accountId));
                    requireEvents(0,
                            countEvents(writer, accountId));

                    // Lúc này phần bắt buộc mới được commit.
                    writer.commit();
                } catch (SQLException | RuntimeException failure) {
                    rollbackBestEffort(writer, failure);
                    throw failure;
                }
            }

            // Connection độc lập xác nhận kết quả bền vững.
            assertFinalState(accountId, "120.00", 0);
        } finally {
            cleanup(accountId);
        }
    }
}
~~~

### Vì sao bộ kiểm chứng này có giá trị?

**Test commit**: Sau `UPDATE balance=135.00` và `INSERT event` trong cùng transaction, `commit()` phải làm cả hai thay đổi xuất hiện với connection observer. Chỉ update được balance nhưng không có event thì test thất bại.

**Test rollback**: Writer cũng cập nhật hai bảng, nhưng gọi `rollback()`. Connection mới vẫn phải thấy balance `100.00` và không có event mới. Điều này phân biệt rollback thực với việc chỉ trả về từ một method Java.

**Test savepoint**: Phần bắt buộc đặt balance `120.00` trước mốc. Phần tùy chọn thêm event và đổi balance thành `999.00` sau mốc. `rollback(point)` trả balance về `120.00` và xóa event tùy chọn trong transaction, rồi `commit()` làm **chỉ phần trước mốc** xuất hiện ở connection mới.

**Dọn dẹp**: `seed` và `cleanup` dùng transaction tách biệt, mỗi lần commit rõ ràng; `cleanup` chạy qua `finally`. Các ID test phải duy nhất, và test không nên chạy đồng thời với công việc khác sử dụng cùng ID.

**Tài nguyên**: `Connection`, `PreparedStatement`, `ResultSet` được đóng bằng `try-with-resources`. Nếu SQL lỗi, helper `rollbackBestEffort` giữ lỗi rollback thành *suppressed exception* thay vì che lỗi chính. Trong môi trường test lớn, còn nên bảo toàn lỗi assertion nếu cleanup ở `finally` bị lỗi (xem mục 12).

## 6. Dùng bộ kiểm chứng trong JUnit 5

Ví dụ test suite:

~~~java
import org.junit.jupiter.api.Test;

final class JdbcTransactionIT {
    // TestDatabase là hạ tầng dự án tự cung cấp;
    // không phải lớp có sẵn trong JDK/JUnit.
    private final TransactionProbe probe =
            new TransactionProbe(TestDatabase.dataSource());

    @Test
    void commitPersistsBothChanges() throws Exception {
        probe.verifyCommit(70001L, 80001L);
    }

    @Test
    void rollbackDiscardsBothChanges() throws Exception {
        probe.verifyRollback(70002L, 80002L);
    }

    @Test
    void savepointKeepsOnlyEarlierChanges() throws Exception {
        probe.verifySavepoint(70003L, 80003L);
    }
}
~~~

Cần chuẩn bị `TestDatabase.dataSource()` trỏ đến **database test** bằng cấu hình dự án, tạo bảng qua migration trước khi chạy và bảo đảm đủ connection. Đây là điểm nối được cố ý để người học lựa chọn H2, PostgreSQL test container hoặc database test thật; JDK không có một `DataSource` cụ thể tự kết nối tới mọi DBMS.

Nếu ứng dụng **bắt buộc** hỗ trợ savepoint, trường hợp `supportsSavepoints()==false` nên làm test **fail**. Nếu savepoint là tính năng tùy chọn và có fallback nghiệp vụ hợp lệ, test có thể dùng `Assumptions.assumeTrue(...)` của JUnit để skip cùng lý do rõ ràng. **Không skip một test bắt buộc chỉ để CI xanh.**

## 7. Đọc bằng connection mới quan trọng thế nào?

Hãy xem một test sai:

~~~java
connection.setAutoCommit(false);
updateBalance(connection, id, new BigDecimal("200.00"));

BigDecimal actual = readBalance(connection, id);
// actual == 200.00 không chứng minh COMMIT!
~~~

Trong transaction, một session thường nhìn thấy bản ghi do chính nó cập nhật. Để xác minh commit:

~~~text
Transaction writer:
  BEGIN
  UPDATE balance = 200.00
  COMMIT
  CLOSE

Connection observer mới:
  SELECT balance
  ASSERT balance == 200.00
~~~

Tương tự, để xác minh rollback:

~~~text
Seed:
  INSERT balance = 100.00
  COMMIT

Transaction writer:
  BEGIN
  UPDATE balance = 200.00
  ROLLBACK
  CLOSE

Connection observer mới:
  SELECT balance
  ASSERT balance == 100.00
~~~

Nếu muốn quan sát **trước commit** ở một session khác, đó còn là phép thử về isolation/locking. Khi dùng `READ_COMMITTED`, observer có thể thấy giá trị cũ hoặc bị chặn nếu writer giữ khóa; tùy DBMS. Không biến test commit cơ bản thành test treo vì đợi observer trước khi writer được phép kết thúc.

Trên DBMS dùng snapshot, observer đã mở transaction từ trước có thể vẫn thấy phiên bản cũ **sau khi writer commit**. Vì vậy hãy tạo connection/transaction observer mới **sau** bước commit/rollback khi chỉ cần kiểm chứng trạng thái cuối.

## 8. Kiểm thử lỗi SQL và rollback toàn bộ

Đường đi thành công chưa đủ. Trong hệ thống thực, service có thể cập nhật bảng A rồi câu `INSERT` vào bảng B thất bại vì trùng khóa, thiếu foreign key, sai kiểu dữ liệu hoặc lỗi DBMS. Nếu code nuốt lỗi và vẫn commit, dữ liệu có thể bị cập nhật **một phần**.

Kịch bản đề xuất:

1. Seed account balance `100.00` và event có ID `81001`; **commit fixture**.
2. Writer tắt auto-commit, cập nhật account balance `150.00`.
3. Writer cố insert một event khác với cùng ID `81001`, gây **vi phạm primary key**.
4. Xác nhận câu insert ném `SQLException`, xử lý `rollback()` toàn transaction.
5. Connection mới xác nhận balance vẫn `100.00` và event ban đầu vẫn tồn tại, không có event ngoài dự kiến.

Minh họa xử lý lỗi trong test:

~~~java
try (Connection writer = dataSource.getConnection()) {
    writer.setAutoCommit(false);

    try {
        updateBalance(writer, accountId, new BigDecimal("150.00"));

        // duplicateEventId đã được INSERT và COMMIT từ setup.
        insertEvent(writer, duplicateEventId, accountId, "duplicate");

        throw new AssertionError("Lẽ ra INSERT phải thất bại");

    } catch (SQLException expectedConstraintError) {
        writer.rollback();
    }
}

// Sau khi đóng writer, mở observer mới kiểm tra trạng thái.
~~~

Các helper `updateBalance` và `insertEvent` được minh họa trong lớp `TransactionProbe`; `duplicateEventId` phải là khóa **đã tồn tại** trong fixture. Nếu không, phép insert có thể thành công và test không tạo được lỗi mong đợi. Để kiểm tra SQLState chính xác, đối chiếu driver/DBMS; không assert nguyên văn lỗi tiếng Anh vì driver/version khác nhau.

**Quan trọng:** Nếu một `SQLException` xảy ra, transaction có thể không còn ở trạng thái có thể tiếp tục. PostgreSQL, ví dụ, đánh dấu transaction failed sau nhiều lỗi SQL cho tới khi rollback hoặc rollback tới savepoint thích hợp. Khi nghiệp vụ không có chính sách phục hồi một phần, hãy rollback **toàn bộ transaction**.

### Đừng che lỗi rollback

~~~java
try {
    connection.rollback();
} catch (SQLException ignored) {
    // Sai: không biết rollback thật sự có thành công không.
}
~~~

Trong test, rollback lỗi phải được báo. Trong code ứng dụng, có thể gắn `rollbackError` vào exception chính qua `addSuppressed`, đánh dấu connection không còn đáng tin cậy và để pool/driver xử lý, không tiếp tục dùng cùng connection cho nghiệp vụ mới.

## 9. Kiểm thử lỗi SQL sau savepoint

Một phép thử `rollback(savepoint)` khi không có lỗi (mục 5) giúp xác nhận API cơ bản. Nhưng một test quan trọng hơn là **quay lui khi câu SQL tùy chọn thực sự thất bại**.

Giả sử event có ID `81002` đã được commit trong setup:

~~~text
BEGIN
UPDATE account SET balance = 120.00       -- phần bắt buộc
SAVEPOINT optional
INSERT event id = 81002                   -- trùng khóa, SQLException
ROLLBACK TO SAVEPOINT optional            -- phục hồi transaction
COMMIT                                    -- giữ lại balance = 120.00
~~~

Mẫu JDBC:

~~~java
try (Connection writer = dataSource.getConnection()) {
    writer.setAutoCommit(false);

    try {
        updateBalance(writer, accountId, new BigDecimal("120.00"));
        Savepoint optional = writer.setSavepoint();

        try {
            insertEvent(writer, existingEventId, accountId, "duplicate");

            throw new AssertionError("Kỳ vọng unique constraint lỗi");
        } catch (SQLException expectedUniqueViolation) {
            // Phải rollback về mốc trước khi thử commit phần A.
            writer.rollback(optional);
        }

        writer.commit();

    } catch (SQLException | RuntimeException failure) {
        try {
            writer.rollback();
        } catch (SQLException rollbackError) {
            failure.addSuppressed(rollbackError);
        }
        throw failure;
    }
}
~~~

Đây là **mẫu trong test harness** đã tạo và commit fixture `existingEventId`, không phải một test tự chạy nếu thiếu setup và assertion. Sau khi writer kết thúc, connection observer phải thấy balance `120.00`, còn event trùng khóa không có thêm bản ghi mới.

Không bắt mọi exception rồi rollback tới mốc một cách vô điều kiện. Lỗi mất connection, deadlock hoặc serialization failure có thể khiến **toàn bộ transaction** không thể tiếp tục. Test từng loại lỗi trên DBMS thực tế và xây dựng chính sách rollback/retry phù hợp.

### Bài test bổ sung: rollback toàn bộ sau rollback savepoint

~~~text
Seed balance = 100.00, COMMIT
BEGIN
UPDATE balance = 120.00
SAVEPOINT s
INSERT event tùy chọn
ROLLBACK TO s
ROLLBACK toàn transaction
Observer mới: balance = 100.00 và không có event
~~~

Test này chứng minh `rollback(savepoint)` **không commit** phần trước mốc. Kết quả cuối hoàn toàn do `commit()` hoặc `rollback()` của transaction ngoài quyết định.

## 10. Những bẫy auto-commit

### Quên tắt auto-commit

~~~java
try (Connection c = dataSource.getConnection()) {
    updateBalance(c, id, new BigDecimal("200.00"));
    c.rollback();
}
~~~

Nếu connection ở `autoCommit=true`, câu `UPDATE` có thể đã được commit, nên `rollback()` sau đó **không hoàn tác** được. Test phải chủ động đặt `setAutoCommit(false)` trước DML đầu tiên; không phụ thuộc trạng thái mặc định của pool.

### Bật lại auto-commit khi transaction vẫn mở

~~~java
c.setAutoCommit(false);
updateBalance(c, id, new BigDecimal("200.00"));

c.setAutoCommit(true); // Có thể COMMIT transaction hiện tại.
c.rollback();          // Không phải biện pháp khôi phục.
~~~

Theo JDBC, thay đổi auto-commit từ `false` sang `true` trong lúc transaction đang hoạt động sẽ commit transaction đó. Không sử dụng `setAutoCommit(true)` như thao tác cleanup **trước khi** kết thúc transaction. Khi dùng connection pool, để tầng sở hữu connection/pool quản lý việc reset trạng thái theo hợp đồng.

### Thay isolation giữa transaction

Một số driver/DBMS không cho đổi transaction isolation khi transaction đã bắt đầu, hoặc có hành vi khác nhau. Nếu test cần isolation nhất định, hãy đặt trước câu SQL mở transaction. Đối với commit/rollback cơ bản, chọn cấu hình rõ nhưng tránh đưa isolation khác biệt DBMS vào assertion không liên quan.

### Đóng connection rồi mặc định rollback

`Connection.close()` không thay thế việc gọi rollback có chủ đích. Hành vi khi đóng connection còn transaction đang mở có thể phụ thuộc driver/pool; trong test, luôn gọi `commit()` hoặc `rollback()` rồi mới đóng.

## 11. DDL, connection pool và framework transaction

### DDL implicit commit

SQL `CREATE TABLE`, `ALTER TABLE`, `TRUNCATE` có thể làm commit ngầm tùy DBMS, dù connection đang có `autoCommit=false`. Không dùng DDL để chứng minh chung cho rollback của DML. Tạo schema **trước test**, test transaction chỉ thao tác `INSERT`, `UPDATE` và `DELETE`.

### Connection pool

Mỗi lần `dataSource.getConnection()` thường mượn một logical connection từ pool. Sau network timeout hoặc lỗi nghiêm trọng, pool phải loại bỏ connection vật lý không còn hợp lệ. Khi test giả lập lỗi, tránh sử dụng lại connection đã hỏng chỉ vì vẫn giữ reference Java.

Một test với `Pool size = 1` có thể bị chặn khi cố mượn observer trong lúc writer vẫn đang giữ connection. Trong các phép kiểm chứng cơ bản của mục 5, writer được **đóng trước** khi observer mượn connection. Khi kiểm thử hai transaction thực sự đồng thời, pool phải đủ ít nhất hai connection.

### `@Transactional` và test rollback tự động

Một số framework test tự động mở một transaction quanh phương thức `@Test` rồi rollback khi test kết thúc. Điều này tiện để dọn dữ liệu, nhưng **có thể tạo dương tính giả khi muốn kiểm chứng commit thật của service**.

~~~java
// Minh họa nguy cơ khi dùng framework:
@Transactional
@Test
void savesSuccessfully() {
    service.save(...);
    assertNotNull(repository.find(...)); // Có thể ở cùng transaction!
}
~~~

Nếu service chỉ **tham gia transaction do test sở hữu**, assertion thấy thay đổi chưa commit và test vẫn pass, dù transaction service chưa thực sự được commit như trong production.

Để kiểm chứng commit:

- Xác định ai sở hữu transaction: service, framework test hay JDBC connection.
- Đảm bảo transaction cần kiểm thử **kết thúc thật**.
- Quan sát từ connection/transaction **độc lập** sau bước kết thúc đó.
- Không phụ thuộc rollback tự động của test để dọn fixture nếu đang thử commit.
- Hiểu khác biệt giữa transaction propagation `REQUIRED`, `REQUIRES_NEW` và `NESTED` của framework; savepoint không đồng nghĩa transaction con độc lập.

## 12. Dọn dẹp fixture mà không che lỗi gốc

Trong `TransactionProbe`, `cleanup(accountId)` nằm ở `finally` để luôn chạy. Đó là cách đơn giản, nhưng nếu cleanup ném `SQLException` sau khi một assertion đã thất bại, exception cleanup có thể **che mất assertion gốc**.

Trong test framework lớn, có thể:

- Dùng fixture manager quản lý setup/teardown.
- Lưu lỗi đầu tiên và thêm cleanup exception làm *suppressed exception*.
- Cô lập schema/database theo test run để xóa dữ liệu an toàn.
- Ghi rõ thông tin fixture cần điều tra mà không log dữ liệu nhạy cảm.
- Không tự chạy lệnh dọn sạch toàn bộ schema trong một test song song với các test khác.

Ví dụ nguyên tắc bảo toàn exception:

~~~java
Throwable primary = null;
try {
    runAssertions();
} catch (Exception | AssertionError failure) {
    primary = failure;
    throw failure;
} finally {
    try {
        cleanupFixture();
    } catch (Exception cleanupFailure) {
        if (primary != null) {
            primary.addSuppressed(cleanupFailure);
        } else {
            throw cleanupFailure;
        }
    }
}
~~~

Khối này là **mẫu cấu trúc** cho test harness có `runAssertions`/`cleanupFixture` tự định nghĩa. Với checked exceptions, chữ ký phương thức phải khai báo phù hợp hoặc framework test phải bao gói lại. Mục tiêu là giữ **lỗi gốc** để kết quả CI không trở nên khó chẩn đoán.

## 13. Kiểm thử song song và visibility giữa hai transaction

Commit/rollback/savepoint cơ bản **không bắt buộc** có hai thread; chỉ cần writer kết thúc rồi observer mới đọc. Khi muốn kiểm tra visibility **trước khi writer commit**, hãy dùng hai connection **mở đồng thời** và thiết kế điều phối.

~~~mermaid
sequenceDiagram
    participant A as Connection A
    participant B as Connection B
    A->>A: setAutoCommit(false)
    A->>A: UPDATE balance = 180.00
    B->>B: SELECT balance (trước commit)
    Note over B: Thường thấy giá trị cũ hoặc bị chặn theo DBMS
    A->>A: COMMIT
    B->>B: Transaction mới / SELECT balance
    Note over B: Kiểm tra giá trị đã commit
~~~

Khi cần đúng lịch interleaving, dùng `CountDownLatch`/`CyclicBarrier` và timeout. Không dùng `Thread.sleep(1000)` như một điều kiện kiểm chứng vì timing phụ thuộc tải máy CI. Nếu B bị block bởi lock mà test chỉ có một thread đang chờ B hoàn tất trước khi cho A commit, test có thể **treo**.

Đồng thời, nếu observer dùng isolation snapshot và transaction B đã mở từ trước, nó có thể tiếp tục thấy giá trị cũ dù A đã commit. Khi mục tiêu chỉ là khẳng định commit, **observer transaction mới** là lựa chọn dễ hiểu và ổn định hơn.

## 14. Khác biệt DBMS và các lỗi không thể phục hồi cục bộ

| DBMS | Lưu ý cần đưa vào test plan |
| --- | --- |
| **PostgreSQL** | Hỗ trợ savepoint. Nhiều SQL error làm transaction rơi vào trạng thái failed cho tới khi rollback hoặc rollback đến savepoint phù hợp; việc catch exception một mình không phục hồi transaction. |
| **MySQL InnoDB** | Hỗ trợ transaction/savepoint trên bảng InnoDB. Bảng dùng engine không hỗ trợ transaction có thể khiến rollback không đạt kỳ vọng; nhiều DDL gây implicit commit. |
| **SQL Server** | Hỗ trợ save transaction; trạng thái giao dịch sau lỗi có thể phụ thuộc loại lỗi và cấu hình như `XACT_ABORT`. Không phải transaction nào sau lỗi cũng còn commit được. |
| **Oracle Database** | Hỗ trợ savepoint; nhiều thao tác DDL implicit commit. Kiểm tra lỗi constraint và transaction theo driver thực tế. |
| **SQLite** | Hỗ trợ savepoint nhưng cơ chế khóa và transaction khác DBMS client/server, nhất là khi nhiều connection ghi đồng thời. |

Một số tình huống cần **rollback toàn bộ**, không cố cứu bằng savepoint:

- Deadlock khiến DBMS hủy transaction.
- Serialization failure yêu cầu chạy lại toàn bộ logic trên một transaction mới.
- Mất kết nối/network timeout khiến transaction không còn dùng được.
- Transaction rơi vào trạng thái không thể commit theo quy tắc DBMS.
- Tác động bên ngoài DB như gửi email/HTTP đã diễn ra, savepoint không thể hoàn tác chúng.

**SQLState** và mã lỗi vendor giúp phân loại. Ví dụ SQLState `40001` thường dùng cho serialization failure; nhiều DBMS có mã riêng cho deadlock. Không bắt nguyên văn thông báo tiếng Anh rồi mặc định giống nhau trên mọi phiên bản driver.

### Commit outcome bất định

Nếu Java gửi `COMMIT` và mất kết nối trước khi nhận phản hồi, **database có thể đã commit**. `SQLException` không tự chứng minh transaction đã rollback. Với nghiệp vụ ghi quan trọng, dùng idempotency key, unique constraint và tra cứu trạng thái qua connection mới khi hệ thống hồi phục. Không retry mù cùng một thao tác có tác dụng phụ.

## 15. Ma trận kịch bản kiểm thử nên có

| Kịch bản | Thao tác | Oracle kiểm thử (trạng thái cuối) |
| --- | --- | --- |
| Commit 1 UPDATE | Tắt auto-commit, update, commit | Connection mới thấy balance mới |
| Commit nhiều bảng | Update account + insert event, commit | Cả hai tồn tại |
| Rollback toàn bộ | Update + insert rồi rollback | Balance gốc, không có event mới |
| Rollback sau constraint violation | Update rồi insert trùng khóa, rollback | Không có partial commit |
| Savepoint thành công | A, savepoint, B, rollback mốc, commit | A tồn tại, B bị hủy |
| Savepoint sau SQL error | A, savepoint, B lỗi, rollback mốc, commit | A tồn tại nếu DBMS hỗ trợ phục hồi transaction |
| Rollback toàn bộ sau rollback mốc | A, savepoint, B, rollback mốc, rollback toàn bộ | Cả A và B bị hủy |
| `releaseSavepoint` | Tạo mốc, release, không commit | Release không tự lưu dữ liệu |
| Auto-commit bật nhầm | Update với `autoCommit=true` rồi rollback | Test phát hiện update đã commit |
| Schema/DDL xen kẽ | DDL trong transaction test | Kiểm tra implicit commit DBMS; không dùng làm oracle DML |
| Observer cùng writer | Đọc lại trước commit | Không chấp nhận làm bằng chứng commit |
| Nhiều test đồng thời | Mỗi test dùng ID riêng | Không can thiệp fixture của test khác |
| Rollback exception | Tạo tình huống cleanup/rollback lỗi | Bảo toàn lỗi gốc, không dùng lại connection hỏng |
| Commit timeout/network failure | Mất phản hồi khi commit | Đánh dấu kết quả chưa chắc chắn, có đối soát |

## 16. Bài tập tự luyện

### Bài 1 — Tìm lỗ hổng trong test

~~~java
connection.setAutoCommit(false);
updateBalance(connection, id, new BigDecimal("500.00"));
BigDecimal value = readBalance(connection, id);
assertEquals(0, new BigDecimal("500.00").compareTo(value));
~~~

**Hỏi:** Test này chứng minh commit thành công chưa? Vì sao?

**Gợi ý:** Chưa; cùng transaction tự thấy thay đổi chưa commit. Phải commit thành công, kết thúc transaction và đọc bằng connection khác.

### Bài 2 — Rollback hai bảng

Fixture có balance `100.00` và 0 event. Writer đổi balance thành `150.00` và thêm event, rồi `rollback()`. Cần ít nhất những assertion nào?

**Gợi ý:** Connection mới đọc balance bằng `BigDecimal` so sánh số và đếm event. Kết quả `100.00` và 0.

### Bài 3 — Savepoint thành công

~~~text
BEGIN
UPDATE balance = 120
SAVEPOINT optional
INSERT event
UPDATE balance = 999
ROLLBACK TO optional
COMMIT
~~~

**Hỏi:** Balance cuối và số event là bao nhiêu?

**Gợi ý:** `120` và 0. Phần trước mốc được commit bởi transaction ngoài.

### Bài 4 — Savepoint rồi rollback toàn bộ

Giữ lịch trên nhưng thay `COMMIT` cuối bằng `ROLLBACK` toàn bộ. Balance cuối là bao nhiêu nếu fixture ban đầu đã commit `100`?

**Gợi ý:** `100`. Rollback mốc không tự commit phần A.

### Bài 5 — SQL error và transaction failed

Trên một DBMS, sau câu `INSERT` trùng khóa, mọi SQL tiếp theo trong transaction đều thất bại dù Java đã catch `SQLException`. Nếu có savepoint trước INSERT, cần làm gì để có thể tiếp tục?

**Gợi ý:** `rollback(savepoint)` nếu DBMS/loại lỗi cho phép phục hồi; nếu không phải rollback toàn bộ. Chỉ catch exception không thay đổi trạng thái DBMS.

### Bài 6 — Framework test rollback tự động

Một JUnit test chạy trong transaction do framework tạo; service cập nhật và cùng test đọc ra giá trị mới, sau đó framework rollback khi test kết thúc. Vì sao test có thể báo sai về commit?

**Gợi ý:** Test chưa quan sát trạng thái đã commit từ transaction độc lập; nó chỉ đọc dữ liệu chưa commit trong transaction test.

### Bài 7 — Lỗi mạng lúc commit

`commit()` ném exception do mất mạng. Có thể khẳng định thao tác thanh toán chưa được commit không? Khi cần retry phải thêm gì?

**Gợi ý:** Không. Cần idempotency key, unique constraint và xác minh trạng thái nghiệp vụ qua connection mới/đối soát.

### Bài 8 — Chạy song song

Hai test đều dùng `account_id=70001` và cùng gọi seed/cleanup. Những lỗi chập chờn có thể xảy ra? Làm cách nào giảm chúng?

**Gợi ý:** Test A có thể xóa fixture của test B, gây sai balance/COUNT hoặc unique constraint. Dùng ID riêng theo test run hay schema/database riêng.

## 17. Checklist trước khi chấp nhận bộ test

- [ ] Dùng **database test** với đúng DBMS/driver quan trọng, không đụng production.
- [ ] Schema tạo trước khi kiểm thử transaction; không đưa DDL implicit commit vào oracle DML.
- [ ] Fixture được **commit trước** khi writer bắt đầu.
- [ ] Có ID riêng, cleanup rõ và không phụ thuộc thứ tự chạy test.
- [ ] `setAutoCommit(false)` xảy ra trước câu DML đầu tiên của transaction.
- [ ] Test commit xác minh **tất cả** hiệu ứng bắt buộc từ connection khác.
- [ ] Test rollback xác minh trạng thái fixture gốc và không có dữ liệu phụ chưa commit.
- [ ] Test savepoint xác minh cả trạng thái sau `rollback(savepoint)` và sau `commit()` ngoài.
- [ ] Đã kiểm tra `supportsSavepoints()`, có chính sách fail/skip rõ.
- [ ] Có test lỗi SQL thật và hành vi rollback/transaction failed theo DBMS.
- [ ] Không để `@Transactional` của test làm che commit thật.
- [ ] Có kiểm soát tài nguyên, rollback khi lỗi và không nuốt cleanup exception.
- [ ] Có chính sách khi driver connection chết, timeout hoặc commit outcome bất định.
- [ ] Dữ liệu và thông tin xác thực không bị in vào log kiểm thử ngoài quy định.
- [ ] Kết quả được xác nhận bằng **assertion dữ liệu**, không chỉ bằng mock API calls.

**Kết luận:** Kiểm thử `commit`, `rollback` và `savepoint` trong JDBC là kiểm chứng **trạng thái của database sau transaction**, không chỉ thứ tự lời gọi Java. Hãy seed fixture đã commit, thực hiện DML trong transaction có ranh giới rõ, kết thúc bằng commit/rollback đúng kịch bản, rồi dùng một **connection mới** để kiểm tra cả dữ liệu chính và dữ liệu phụ. Savepoint chỉ hủy phần công việc sau mốc **bên trong transaction hiện tại**; quyết định commit hoặc rollback toàn bộ vẫn thuộc transaction ngoài. Kết hợp lỗi SQL thực, kiểm thử DBMS mục tiêu và cleanup an toàn để có kết quả đáng tin cậy.

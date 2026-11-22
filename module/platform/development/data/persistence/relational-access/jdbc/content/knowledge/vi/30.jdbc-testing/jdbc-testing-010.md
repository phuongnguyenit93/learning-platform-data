# Kiểm thử rò rỉ tài nguyên khi thao tác thất bại

Một thao tác **JDBC** không chỉ thất bại khi câu SQL sai. Lỗi có thể xảy ra ngay lúc `DataSource.getConnection()`, khi tạo `PreparedStatement`, bind tham số, gọi `executeQuery()`, đọc `ResultSet.next()`, chuyển dữ liệu thành đối tượng Java, `commit()`, `rollback()` hoặc chính lúc `close()`. Nếu code chỉ đóng kết nối trong nhánh thành công, một lượng nhỏ request lỗi cũng có thể làm **cạn connection pool**, giữ cursor/statement lâu hơn cần thiết và khiến các request không liên quan bị timeout.

Bài học thuộc chương **Kiểm thử JDBC** của module **JDBC**. Mục tiêu là kiểm chứng một cách có hệ thống rằng `Connection`, `PreparedStatement` và `ResultSet` được giải phóng **ở mọi đường đi**, kể cả khi lỗi lồng lỗi. Chúng ta sẽ viết DAO có ownership rõ ràng, xây dựng ma trận chèn lỗi (fault injection), dùng **JUnit 5 + Mockito** để kiểm tra thứ tự đóng, kiểm thử transaction và ngoại lệ bị suppressed, rồi thử trên **JDBC driver + connection pool + database thật** để phát hiện những rò rỉ mà mock không thể chứng minh.

Điểm cần nhớ: một unit test xác nhận `Connection.close()` được gọi **không đủ** để chứng minh physical connection được pool trả/loại đúng hoặc DB đã giải phóng cursor. Test tốt cần kết hợp **lời gọi cleanup, trạng thái tài nguyên, thời gian giải phóng và dữ liệu cuối trong DB**.

## 1. Rò rỉ tài nguyên JDBC là gì?

Một tài nguyên bị rò rỉ khi ứng dụng **không kết thúc vòng đời sử dụng đúng lúc**, khiến tài nguyên tiếp tục bị giữ dù không còn nhiệm vụ hợp lệ. Với JDBC, có nhiều tầng:

| Tài nguyên | Ai tạo ra? | Cách kết thúc bình thường | Nếu quên hoặc thất bại |
| --- | --- | --- | --- |
| `Connection` | `DataSource.getConnection()` / `DriverManager` | `Connection.close()` | Pool giữ connection ở trạng thái mượn; socket/session có thể tồn tại |
| `PreparedStatement` / `Statement` | `Connection.prepareStatement()` / `createStatement()` | `Statement.close()` | Cursor/server-side statement, bộ nhớ hoặc handle không được dọn đúng lúc |
| `ResultSet` | `executeQuery()` / `getGeneratedKeys()` | `ResultSet.close()` | Cursor, bộ nhớ đệm và tài nguyên driver còn giữ |
| `InputStream` / `Reader` từ BLOB/CLOB | `ResultSet.getBinaryStream()` / `getCharacterStream()` | Đóng stream đúng scope trước khi đóng `ResultSet` | Đọc dữ liệu lớn có thể kẹt hoặc giữ buffer/stream |
| Transaction đang mở | `setAutoCommit(false)` rồi thực thi SQL | `commit()` hoặc `rollback()` theo kết quả | Giữ lock/snapshot, trạng thái mơ hồ khi trả về pool |
| Pool/`DataSource` được quản lý | Lifecycle ứng dụng/container | API đóng của **pool provider** khi ứng dụng dừng | Thread/socket của pool có thể sống quá vòng đời ứng dụng |

Với pooled `Connection`, `close()` thường trả **logical connection** về pool, không nhất thiết đóng physical socket. Vì vậy, không nên kiểm tra “số socket bằng 0” sau **mỗi request**; điều cần kiểm tra là **không còn connection bị mượn trái phép**. Khi ứng dụng shutdown, lifecycle owner mới đóng cả pool theo API của implementation.

Các vấn đề liên quan nhưng không đồng nhất:

- **Resource leak:** đường xử lý không đóng hoặc không trả tài nguyên đúng hạn.
- **Long-running legitimate work:** connection vẫn đang làm việc hợp lệ; không phải leak chỉ vì vượt một ngưỡng ngắn.
- **Connection bị hỏng:** code có thể đã gọi `close()` nhưng pool/driver không khôi phục đúng; cần kiểm tra khả năng loại physical connection.
- **Transaction leak:** connection được trả mà transaction chưa được kết thúc rõ ràng; `close()` không phải bằng chứng chắc chắn `rollback()` đã thành công.
- **DB-side resource retention:** dù client gọi close, driver/network có thể trì hoãn cleanup cursor ở server; phải quan sát cả DB khi cần.

## 2. Quy tắc sở hữu tài nguyên và thứ tự đóng

Một truy vấn thông thường có chuỗi sở hữu:

```text
DataSource
  └─ Connection                    mượn từ pool
       └─ PreparedStatement        tạo từ connection
            └─ ResultSet           tạo từ executeQuery()
                 └─ BLOB stream    nếu đọc dữ liệu lớn

Thứ tự kết thúc:
BLOB stream → ResultSet → PreparedStatement → Connection
```

Phạm vi `try-with-resources` thực thi `close()` theo **thứ tự ngược** với thứ tự khai báo. Nếu một resource chưa tạo thành công, Java chỉ đóng **những resource đã khởi tạo**. Đây là thuộc tính quan trọng khi chèn lỗi vào `prepareStatement()` hoặc `executeQuery()`.

```java
try (Connection con = source.getConnection();
     PreparedStatement ps = con.prepareStatement(sql)) {
    ps.setLong(1, id);
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc và xử lý hàng.
        }
    }
}
```

Với cấu trúc trên:

1. `getConnection()` lỗi → chưa có `Connection` hợp lệ để đóng.
2. `prepareStatement()` lỗi → `Connection` đã tạo **vẫn được đóng**.
3. `setLong()` hoặc `executeQuery()` lỗi → `PreparedStatement` và `Connection` được đóng.
4. `rs.next()`, `rs.getXxx()` hoặc mapper lỗi → `ResultSet`, `PreparedStatement` và `Connection` được đóng.
5. Thoát vòng lặp bằng `break` hoặc `return` → cleanup vẫn được thực hiện.
6. `close()` của một tài nguyên cũng lỗi → Java **vẫn thử đóng các tài nguyên còn lại**; cấu trúc lỗi được bảo toàn bằng suppressed exceptions.

`try-with-resources` bảo đảm **gọi** `close()` theo quy tắc Java; nó không bảo đảm mọi lời gọi dọn dẹp bên trong driver luôn thành công. Kiểm thử phải phân biệt hai điều đó.

## 3. Mẫu repository làm đối tượng cần kiểm thử

Giả sử bảng quan hệ:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    owner_name VARCHAR(120) NOT NULL,
    balance NUMERIC(18, 2) NOT NULL
);
```

Một DAO dùng `DataSource` và `PreparedStatement` để đọc một tài khoản bằng khóa chính. Không trả `ResultSet` ra ngoài phạm vi sở hữu:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Objects;
import java.util.Optional;
import javax.sql.DataSource;

public final class AccountReader {
    private static final String SQL = """
            SELECT id, owner_name, balance
            FROM accounts WHERE id = ?
            """;

    private final DataSource source;

    public record Account(long id, String ownerName, BigDecimal balance) {}

    public AccountReader(DataSource source) {
        this.source = Objects.requireNonNull(source);
    }

    public Optional<Account> findById(long id) throws SQLException {
        try (Connection con = source.getConnection();
             PreparedStatement ps = con.prepareStatement(SQL)) {
            ps.setLong(1, id);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }

                long accountId = rs.getLong("id");
                String ownerName = rs.getString("owner_name");
                BigDecimal balance = rs.getBigDecimal("balance");
                if (ownerName == null || balance == null) {
                    throw new SQLException(
                            "Dữ liệu accounts không thỏa ràng buộc NOT NULL");
                }
                return Optional.of(
                        new Account(accountId, ownerName, balance));
            }
        }
    }
}
```

Mẫu có các tính chất có thể kiểm chứng:

- Dùng SQL tham số hóa với `?`, không ghép `id` vào chuỗi SQL.
- Một `Connection` được mượn cho **một** lần gọi và đóng sau khi mọi statement/result set đã được đóng.
- Trường hợp **không có hàng** trả `Optional.empty()`, khác với trường hợp SQL hoặc mapper thất bại: khi lỗi, ném ngoại lệ.
- Giá trị trả về là Java record độc lập với tài nguyên JDBC.
- Lỗi tạo statement, thực thi, đọc cột hoặc chuyển dữ liệu đều đi qua `try-with-resources`.

**Lưu ý:** `findById()` là truy vấn chỉ đọc, không tự thay đổi `autoCommit`. Phần transaction nhiều bước sẽ được kiểm thử riêng ở mục 9.

## 4. Ma trận fault injection: gây lỗi ở từng đường đi

Đừng chỉ viết test “truy vấn thành công và có hàng”. Các điểm lỗi khác nhau quyết định **resource nào đã được tạo** và do đó resource nào phải được đóng:

| Điểm chèn lỗi | Resource đã được tạo | Cleanup kỳ vọng | Dữ liệu/ngoại lệ |
| --- | --- | --- | --- |
| `DataSource.getConnection()` | Chưa có connection | Không gọi close trên một connection không tồn tại | Ném nguyên `SQLException` |
| `Connection.prepareStatement()` | `Connection` | Đóng connection | Không tự gọi close một statement chưa được trả về |
| `PreparedStatement.setLong()` | Connection + statement | Đóng statement rồi connection | Bảo toàn lỗi bind |
| `PreparedStatement.executeQuery()` | Connection + statement | Đóng statement rồi connection | Bảo toàn lỗi execute |
| `ResultSet.next()` | Cả ba | Đóng result set, statement, connection | Bảo toàn lỗi fetch |
| `ResultSet.getString()/getBigDecimal()` | Cả ba | Đóng cả ba | Bảo toàn lỗi đọc cột |
| Mapper ném `RuntimeException` | Cả ba | Đóng cả ba | Không nuốt lỗi mapper |
| `ResultSet.close()` | Cả ba | Vẫn đóng statement, connection | Lỗi close nổi lên nếu không có lỗi chính; nếu có thì suppressed |
| `PreparedStatement.close()` | Connection + statement | Vẫn đóng connection | Lỗi close được báo/đính kèm |
| `Connection.close()` | Connection | Không còn resource khác để đóng | Lỗi close được báo/đính kèm; không mặc định pool đã nhận connection |
| `Statement.executeBatch()` | Connection + statement | Đóng statement, connection, rollback nếu có transaction | Đọc `BatchUpdateException` khi phù hợp |
| `Connection.commit()` | Connection/transaction | Xử lý ngoại lệ và đóng/loại connection theo chính sách | **Commit có thể đã thành công** dù client nhận lỗi |
| `Connection.rollback()` | Connection/transaction | Giữ lỗi chính, thử close an toàn | Không báo “rollback thành công” khi nó ném lỗi |

Ma trận là **hợp đồng quan sát**. Test cần xác minh đúng số lần gọi và thứ tự cleanup, nhưng cũng phải bảo đảm kết quả nghiệp vụ không bị thay đổi thành “thành công” giả khi cleanup lỗi.

## 5. Unit test với JUnit 5 và Mockito

Để chủ động gây lỗi tại từng phương thức, dùng mock của `DataSource`, `Connection`, `PreparedStatement` và `ResultSet`. Test không cần database thật và có thể kiểm tra thứ tự `close()`.

Ví dụ dưới đây dành cho **JUnit Jupiter 5** và **Mockito**. Dự án phải có dependencies test phù hợp. Các static imports được khai báo đầy đủ để dễ tách thành file `AccountReaderTest.java`.

```java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.InOrder;

class AccountReaderTest {
    DataSource source;
    Connection con;
    PreparedStatement ps;
    ResultSet rs;
    AccountReader reader;

    @BeforeEach
    void setUp() throws SQLException {
        source = mock(DataSource.class);
        con = mock(Connection.class);
        ps = mock(PreparedStatement.class);
        rs = mock(ResultSet.class);

        when(source.getConnection()).thenReturn(con);
        when(con.prepareStatement(anyString())).thenReturn(ps);
        when(ps.executeQuery()).thenReturn(rs);
        reader = new AccountReader(source);
    }

    @Test
    void closesAllOnSuccessfulRead() throws SQLException {
        when(rs.next()).thenReturn(true);
        when(rs.getLong("id")).thenReturn(42L);
        when(rs.getString("owner_name")).thenReturn("A");
        when(rs.getBigDecimal("balance"))
                .thenReturn(new BigDecimal("125.50"));

        Optional<AccountReader.Account> found = reader.findById(42L);

        assertTrue(found.isPresent());
        assertEquals(42L, found.orElseThrow().id());

        InOrder order = inOrder(rs, ps, con);
        order.verify(rs).close();
        order.verify(ps).close();
        order.verify(con).close();
    }

    @Test
    void closesAllWhenNoRow() throws SQLException {
        when(rs.next()).thenReturn(false);

        assertEquals(Optional.empty(), reader.findById(42L));
        InOrder order = inOrder(rs, ps, con);
        order.verify(rs).close();
        order.verify(ps).close();
        order.verify(con).close();
    }

    @Test
    void closesAllWhenFetchingThrows() throws SQLException {
        SQLException fetchFailure =
                new SQLException("fetch failed", "08006");
        when(rs.next()).thenThrow(fetchFailure);

        SQLException received = assertThrows(
                SQLException.class, () -> reader.findById(42L));

        assertSame(fetchFailure, received);
        InOrder order = inOrder(rs, ps, con);
        order.verify(rs).close();
        order.verify(ps).close();
        order.verify(con).close();
    }

    @Test
    void closesAllWhenMapperThrows() throws SQLException {
        when(rs.next()).thenReturn(true);
        when(rs.getLong("id")).thenReturn(42L);
        IllegalStateException mappingFailure =
                new IllegalStateException("mapping failed");
        when(rs.getString("owner_name"))
                .thenThrow(mappingFailure);

        IllegalStateException received = assertThrows(
                IllegalStateException.class,
                () -> reader.findById(42L));

        assertSame(mappingFailure, received);
        verify(rs).close();
        verify(ps).close();
        verify(con).close();
    }
}
```

Các assertion quan trọng:

- `assertSame(original, received)` xác nhận DAO **không thay lỗi gốc bằng lỗi giả**.
- `InOrder` xác nhận thứ tự đóng `ResultSet → PreparedStatement → Connection`.
- `verify(...).close()` chứng minh phương thức được gọi, **không** chứng minh physical connection đã được pool trả.
- Test “không có hàng” quan trọng ngang test lỗi: `return` sớm cũng phải đóng tài nguyên.

Nếu dùng một framework khác để mock, ý tưởng vẫn tương tự: tạo một lỗi được kiểm soát, gọi phương thức thật của repository, rồi kiểm tra mọi resource được đóng và lỗi không bị che.

## 6. Lỗi lúc khởi tạo: đừng đóng resource chưa tồn tại

Với `try-with-resources`, Java chỉ đóng những giá trị đã được khởi tạo thành công. Kiểm thử riêng hai trường hợp:

```java
@Test
void connectionAcquisitionFailureHasNoResourcesToClose()
        throws SQLException {
    SQLException openFailure = new SQLException("no connection", "08001");
    when(source.getConnection()).thenThrow(openFailure);

    SQLException received = assertThrows(
            SQLException.class, () -> reader.findById(42L));

    assertSame(openFailure, received);
    verifyNoInteractions(con, ps, rs);
}

@Test
void prepareStatementFailureStillClosesConnection()
        throws SQLException {
    SQLException prepareFailure =
            new SQLException("prepare failed", "42000");
    when(con.prepareStatement(anyString())).thenThrow(prepareFailure);

    SQLException received = assertThrows(
            SQLException.class, () -> reader.findById(42L));

    assertSame(prepareFailure, received);
    verify(con).close();
    verify(ps, never()).close();
    verify(rs, never()).close();
}

@Test
void parameterBindingFailureClosesStatementAndConnection()
        throws SQLException {
    SQLException bindFailure = new SQLException("invalid bind", "22000");
    doThrow(bindFailure).when(ps).setLong(1, 42L);

    assertSame(bindFailure, assertThrows(
            SQLException.class, () -> reader.findById(42L)));

    verify(ps).close();
    verify(con).close();
    verify(rs, never()).close();
}

@Test
void executeFailureClosesStatementAndConnection()
        throws SQLException {
    SQLException executeFailure =
            new SQLException("execute failed", "42000");
    when(ps.executeQuery()).thenThrow(executeFailure);

    assertSame(executeFailure, assertThrows(
            SQLException.class, () -> reader.findById(42L)));

    verify(ps).close();
    verify(con).close();
    verify(rs, never()).close();
}
```

Đây là **các phương thức test bổ sung** để đặt bên trong lớp `AccountReaderTest` ở mục 5, nơi đã có các field, `@BeforeEach` và static imports. Không ghép code trực tiếp bên ngoài một lớp Java.

Trường hợp `getConnection()` thất bại khác với “pool đã cấp connection nhưng statement lỗi”. Khi chưa có connection, không có gì để `Connection.close()`. Còn khi đã lấy thành công connection, dù statement chưa được tạo, **caller vẫn sở hữu trách nhiệm trả connection**. Test giúp phát hiện một refactor vô tình chuyển `prepareStatement()` ra trước scope quản lý tài nguyên.

## 7. Ngoại lệ bị suppressed khi chính close cũng thất bại

Một lỗi JDBC có thể kéo theo nhiều lỗi khác. Ví dụ `ResultSet.next()` ném `SQLException A`; sau đó `rs.close()` ném B, `ps.close()` ném C và `con.close()` ném D.

```text
rs.next()      → A, lỗi chính
rs.close()     → B
ps.close()     → C
con.close()    → D

throw A
  ├─ suppressed: B
  ├─ suppressed: C
  └─ suppressed: D
```

`try-with-resources` của Java không bỏ qua cleanup chỉ vì một lần `close()` đã ném lỗi. Lỗi chính được bảo toàn; lỗi đóng được gắn thông qua `Throwable.addSuppressed()`.

### Kiểm thử ba lỗi close đồng thời

```java
@Test
void keepsMainFailureAndAllCloseFailures() throws SQLException {
    SQLException readFailure = new SQLException("read", "08006");
    SQLException rsCloseFailure = new SQLException("rs close");
    SQLException psCloseFailure = new SQLException("ps close");
    SQLException conCloseFailure = new SQLException("con close");

    when(rs.next()).thenThrow(readFailure);
    doThrow(rsCloseFailure).when(rs).close();
    doThrow(psCloseFailure).when(ps).close();
    doThrow(conCloseFailure).when(con).close();

    SQLException received = assertThrows(
            SQLException.class, () -> reader.findById(42L));

    assertSame(readFailure, received);
    assertArrayEquals(
            new Throwable[] {
                rsCloseFailure, psCloseFailure, conCloseFailure
            },
            received.getSuppressed());
    verify(rs).close();
    verify(ps).close();
    verify(con).close();
}
```

Vì `readFailure` xảy ra trước các lần close, nó là ngoại lệ chính. Nếu *không có lỗi đọc* mà `rs.close()` thất bại, lỗi close đầu tiên có thể trở thành ngoại lệ chính; những lỗi close sau được suppressed. Cả hai tình huống đều cần test.

```java
@Test
void closeFailureAfterSuccessIsReported() throws SQLException {
    when(rs.next()).thenReturn(false);
    SQLException closeFailure = new SQLException("rs close failed");
    doThrow(closeFailure).when(rs).close();

    SQLException received = assertThrows(
            SQLException.class, () -> reader.findById(42L));

    assertSame(closeFailure, received);
    verify(ps).close();
    verify(con).close();
}
```

Các test trên thuộc cùng `AccountReaderTest` của mục 5. **Không giả định rằng đóng thất bại nghĩa là tài nguyên chắc chắn còn mở**, cũng không giả định ngược lại rằng đã giải phóng xong. Với driver/pool thật, cần quan sát trạng thái session và khả năng mượn connection mới.

## 8. Chống phản mẫu finally che mất ngoại lệ ban đầu

Code dạng sau khó bảo toàn đầy đủ thông tin lỗi:

```java
Connection con = source.getConnection();
try {
    // SQL có thể ném SQLException gốc.
    runSql(con);
} finally {
    con.close();  // Nếu lỗi, có thể thay thế SQLException gốc.
}
```

Một trường hợp khác:

```java
try {
    runSql(con);
} catch (SQLException e) {
    logger.warning(e.getMessage());
    return false; // Nuốt lỗi SQL và có thể che việc transaction chưa kết thúc.
}
```

Hướng tốt hơn là **đặt tài nguyên ngay trong `try-with-resources`**, dùng `catch` chỉ khi cần chuyển thành lỗi nghiệp vụ có cause hoặc quyết định rollback/retry theo chính sách. Không cần tạo quá nhiều khối `finally` đóng lồng nhau nếu cú pháp Java đã làm được.

Khi ứng dụng cố ý bọc lỗi:

```java
public final class DataAccessFailure extends RuntimeException {
    public DataAccessFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

// Ở ranh giới repository/service có chính sách bọc lỗi:
try {
    performJdbcOperation();
} catch (SQLException sqlFailure) {
    throw new DataAccessFailure(
            "Không thể hoàn tất thao tác dữ liệu", sqlFailure);
}
```

`performJdbcOperation()` là tên minh họa cho phương thức đã thực hiện đầy đủ cleanup; đoạn code không phải một class chạy độc lập. **Luôn giữ `cause`** để có thể kiểm tra SQLState, vendor code và suppressed của lỗi SQL gốc ở tầng xử lý được phép. Với log production, cân nhắc việc message/stack trace của driver có thể chứa giá trị SQL hoặc dữ liệu nhạy cảm; không vì cần debug mà tự động dump mọi exception ra sink rộng quyền.

## 9. Transaction: kiểm thử cả rollback, commit và reset trạng thái

Test tài nguyên cho truy vấn chỉ đọc chưa đủ. Với `setAutoCommit(false)`, ứng dụng còn phải quản lý **trạng thái transaction** trước khi trả connection về pool:

1. Đọc trạng thái `autoCommit` ban đầu.
2. Bắt đầu transaction.
3. Chạy nhiều câu SQL trên **cùng một connection**.
4. `commit()` nếu thành công; `rollback()` nếu thất bại và transaction đã bắt đầu.
5. Giữ lỗi chính khi rollback hoặc khôi phục trạng thái connection lỗi.
6. Chỉ khôi phục trạng thái khi transaction đã kết thúc an toàn theo tín hiệu driver; nếu không, connection có thể cần được loại khỏi pool.
7. Đóng connection dù transaction thành công hay lỗi.

Ví dụ DAO cập nhật trạng thái đơn hàng trong transaction:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class OrderStatusWriter {
    private final DataSource source;

    public OrderStatusWriter(DataSource source) {
        this.source = Objects.requireNonNull(source);
    }

    public int markConfirmed(long orderId) throws SQLException {
        String sql = "UPDATE orders SET status = ? WHERE id = ?";

        try (Connection con = source.getConnection()) {
            boolean originalAutoCommit = con.getAutoCommit();
            boolean transactionStarted = false;
            boolean transactionEnded = false;
            Throwable primaryFailure = null;

            try {
                con.setAutoCommit(false);
                transactionStarted = true;

                int affected;
                try (PreparedStatement ps = con.prepareStatement(sql)) {
                    ps.setString(1, "CONFIRMED");
                    ps.setLong(2, orderId);
                    affected = ps.executeUpdate();
                }

                con.commit();
                transactionEnded = true;
                return affected;
            } catch (SQLException | RuntimeException | Error failure) {
                primaryFailure = failure;
                if (transactionStarted) {
                    try {
                        con.rollback();
                        transactionEnded = true;
                    } catch (SQLException | RuntimeException | Error rollbackFailure) {
                        if (rollbackFailure != failure) {
                            failure.addSuppressed(rollbackFailure);
                        }
                    }
                }
                throw failure;
            } finally {
                if (transactionStarted && transactionEnded) {
                    try {
                        con.setAutoCommit(originalAutoCommit);
                    } catch (SQLException | RuntimeException | Error resetFailure) {
                        if (primaryFailure != null) {
                            if (resetFailure != primaryFailure) {
                                primaryFailure.addSuppressed(resetFailure);
                            }
                        } else {
                            throw resetFailure;
                        }
                    }
                }
            }
        }
    }
}
```

Đây là ví dụ về **đường cleanup có thể kiểm thử**, không phải transaction helper production đầy đủ. Một `commit()` ném `SQLException` do mất kết nối **có thể đã commit hoặc chưa**; thử `rollback()` sau đó không chứng minh đã hoàn tác. Nếu yêu cầu có tác động nghiệp vụ quan trọng, phải dùng khóa idempotency, trạng thái và đối soát khi commit không rõ kết quả.

Một số trường hợp nghiêm trọng (`setAutoCommit(false)` thất bại sau khi đã thay state phía driver, `rollback()` lỗi, connection mất mạng) cần pool/driver **loại physical connection**. Ví dụ tránh khôi phục `autoCommit` nếu rollback thất bại; nhưng `close()` trên logical connection **không tự bảo đảm mọi pool loại connection hỏng**. Cần kiểm chứng chính sách invalidate/evict của pool và driver.

## 10. Unit test transaction và lỗi cleanup kết hợp

Với `OrderStatusWriter`, mock các trạng thái transaction:

| Tình huống | Điều phải xác minh |
| --- | --- |
| Thực thi thành công và `commit()` thành công | Gọi `commit()` một lần, không rollback, reset `autoCommit` và close |
| `executeUpdate()` ném `SQLException` | Gọi rollback, reset chỉ sau rollback thành công, statement/connection đóng |
| `PreparedStatement.close()` ném lỗi trước commit | Không commit, rollback, giữ lỗi close làm lỗi chính nếu không có lỗi trước |
| `rollback()` cũng thất bại | Lỗi execute chính, lỗi rollback suppressed, không tự bật lại autoCommit |
| `Connection.close()` cũng thất bại | Lỗi chính vẫn được giữ, close suppressed |
| `commit()` ném lỗi | Có đường xử lý kết quả không rõ, không đánh dấu thành công nghiệp vụ |
| `setAutoCommit(false)` ném lỗi | Không mặc định rollback đã bắt đầu; vẫn đóng/loại connection |
| `setAutoCommit(original)` ném lỗi | Không mất exception trước; caller nhận cleanup failure nếu không có lỗi chính |

Ví dụ JUnit 5 + Mockito:

```java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.*;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;
import org.junit.jupiter.api.Test;

class OrderStatusWriterTest {
    @Test
    void rollbackAndCloseFailuresAreSuppressed()
            throws SQLException {

        DataSource ds = mock(DataSource.class);
        Connection con = mock(Connection.class);
        PreparedStatement ps = mock(PreparedStatement.class);
        when(ds.getConnection()).thenReturn(con);
        when(con.getAutoCommit()).thenReturn(true);
        when(con.prepareStatement(anyString())).thenReturn(ps);

        SQLException executeFailure =
                new SQLException("write failed", "40001");
        SQLException rollbackFailure =
                new SQLException("rollback failed", "08006");
        SQLException closeFailure =
                new SQLException("close failed", "08006");

        when(ps.executeUpdate()).thenThrow(executeFailure);
        doThrow(rollbackFailure).when(con).rollback();
        doThrow(closeFailure).when(con).close();

        SQLException received = assertThrows(
                SQLException.class,
                () -> new OrderStatusWriter(ds).markConfirmed(42L));

        assertSame(executeFailure, received);
        assertArrayEquals(
                new Throwable[] {rollbackFailure, closeFailure},
                received.getSuppressed());
        verify(con).setAutoCommit(false);
        verify(con).rollback();
        verify(con, never()).setAutoCommit(true);
        verify(ps).close();
        verify(con).close();
        verify(con, never()).commit();
    }
}
```

Lưu ý thứ tự: `PreparedStatement.close()` được thực thi trước khi khối `catch` của transaction chạy rollback (vì statement có scope nội bộ). Lỗi statement close có thể chính là nguyên nhân kích hoạt rollback, ngay cả khi `executeUpdate()` thành công.

Với lỗi `commit()`, test unit có thể kiểm tra rằng DAO **không trả kết quả thành công** và giải phóng tài nguyên, nhưng không thể dựa vào mock để kết luận transaction ngoài DB đã commit hay rollback. Cần test integration hoặc cơ chế đối soát theo request ID để xác minh kết quả nghiệp vụ.

## 11. Test với database thật và connection pool thật

Mocks xác minh lời gọi; **integration test** xác minh cách driver/pool vận hành. Những thứ khó chứng minh chỉ bằng Mockito:

- Sau một lỗi SQL, pooled connection có được trả về pool và được mượn lại không?
- Tình huống connection hỏng có được phát hiện/evict thay vì cấp lại cho request khác không?
- Cursor phía server có được giải phóng khi ResultSet đóng sớm không?
- Transaction đã rollback hay vẫn giữ lock/snapshot?
- Truy vấn timeout/cancel có giải phóng connection trong deadline thực tế không?
- Driver có ném lỗi ở `close()`, hoặc `getConnection()` đợi pool thế nào khi tải đồng thời?

Một test thực tế có thể dùng **Testcontainers PostgreSQL** + **HikariCP** + **JUnit 5**. Đoạn dưới đây minh họa kiểm tra pool trở về trạng thái không còn connection đang được mượn sau các lỗi cố ý. Cần dependencies cho JUnit Jupiter, Testcontainers PostgreSQL/JUnit Jupiter, HikariCP và PostgreSQL JDBC driver.

```java
import static org.junit.jupiter.api.Assertions.*;
import static org.awaitility.Awaitility.await;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class JdbcPoolLeakIT {
    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void sqlErrorsDoNotLeaveConnectionsBorrowed() throws Exception {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(postgres.getJdbcUrl());
        config.setUsername(postgres.getUsername());
        config.setPassword(postgres.getPassword());
        config.setMaximumPoolSize(2);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(1_000);
        config.setPoolName("jdbc-leak-test");

        try (HikariDataSource pool = new HikariDataSource(config)) {
            for (int i = 0; i < 20; i++) {
                assertThrows(SQLException.class, () -> {
                    try (Connection con = pool.getConnection();
                         PreparedStatement ps = con.prepareStatement(
                                 "SELECT * FROM table_that_does_not_exist")) {
                        ps.executeQuery();
                    }
                });
            }

            await().atMost(Duration.ofSeconds(5)).until(
                    () -> pool.getHikariPoolMXBean()
                            .getActiveConnections() == 0);

            // Pool vẫn còn phục vụ được sau nhiều truy vấn SQL lỗi.
            try (Connection con = pool.getConnection()) {
                assertTrue(con.isValid(2));
            }
            await().atMost(Duration.ofSeconds(5)).until(
                    () -> pool.getHikariPoolMXBean()
                            .getActiveConnections() == 0);
        }
    }
}
```

### Cách đọc test integration này

1. Tạo PostgreSQL test container và pool có kích thước nhỏ để dễ thấy tình huống cạn connection.
2. Lặp lại lỗi SQL cố ý ở `executeQuery()`. Mỗi lần borrow phải đi qua `try-with-resources` và trả connection.
3. Dùng **Awaitility** để chờ một điều kiện metric đạt yêu cầu trong thời hạn, thay vì `Thread.sleep(1000)` rồi giả định pool đã cập nhật số đếm.
4. Xác minh sau nhiều lỗi vẫn có thể mượn một connection hợp lệ.
5. Đóng pool khi hết scope `try (HikariDataSource pool = ...)`; đây là **lifecycle của test**, không phải DAO tự tắt pool.

**Lưu ý:** `HikariPoolMXBean.getActiveConnections()` phản ánh số connection đang được pool tính là active tại thời điểm lấy mẫu. Nó không chứng minh tất cả cursor phía DB đã đóng, mọi transaction đã rollback, hoặc physical connections về 0. Với các rủi ro đó cần test và quan sát bổ sung.

Version tag `postgres:16-alpine` là ví dụ cho môi trường test; lựa chọn version phù hợp với DB production và chạy test trên driver tương ứng. Testcontainers cần runtime container; Awaitility là dependency **bổ sung**. Đừng để integration test mặc định dùng credential/data production.

## 12. Đo pool exhaustion bằng kiểm thử có kiểm soát

Một cách phát hiện rõ leak là dùng pool nhỏ và tạo tải vừa đủ để nếu một connection bị giữ, lần mượn kế tiếp sẽ timeout.

Ví dụ với pool `maximumPoolSize=1` trong **test riêng**, giữ một connection rồi cố mượn connection thứ hai:

```java
try (Connection borrowed = pool.getConnection()) {
    // Pool chỉ có một connection active.
    assertThrows(SQLException.class, pool::getConnection);
    // Cần đặt connectionTimeout ngắn ở HikariConfig của test.
}

// Sau khi close() logical connection, borrow lại phải thành công.
try (Connection afterReturn = pool.getConnection()) {
    assertTrue(afterReturn.isValid(2));
}
```

**Đây là phép thử cho hành vi pool khi hết connection**, không phải code ứng dụng nên giữ connection cố tình. Với pool `maximumPoolSize=1`, nếu configuration có minimum idle hoặc những connection khác đang hoạt động, phải khởi tạo fixture độc lập để test deterministic.

Không thực hiện kiểu “giữ connection để gây timeout” trên production. Dùng container DB riêng, pool test nhỏ và deadline chặt chẽ.

Để phân biệt leak và truy vấn chậm:

- **Leak:** active connections không giảm ngay cả khi request/job đã hoàn tất.
- **Truy vấn hợp lệ chạy lâu:** active connections vẫn tăng trong khi công việc thực sự đang chạy.
- **Pool đang mở nhiều physical connections nhưng idle:** không phải leak của logical connection; pool thường giữ idle connection để tái sử dụng.

Phải liên kết pool metrics với ranh giới công việc và thời điểm `close()`; chỉ nhìn đồ thị `active > 0` chưa đủ kết luận có leak.

## 13. Kiểm thử kết thúc sớm, streaming và cancel

Các thao tác đọc nhiều hàng có nguy cơ rò rỉ khi bên gọi dừng sớm. Cần kiểm thử cả:

1. Caller yêu cầu tối đa N hàng rồi `break`/`return`.
2. Mapper phát hiện dữ liệu bất hợp lệ và ném `RuntimeException`.
3. `ResultSet.next()` ném `SQLException` sau khi đã đọc một phần.
4. Đang đọc stream từ BLOB/CLOB thì `InputStream.read()`/`Reader.read()` lỗi.
5. HTTP client disconnect hoặc deadline request hết, worker được yêu cầu dừng.
6. Driver không đáp ứng kịp `Statement.cancel()` hoặc `setQueryTimeout(...)`.

Mẫu bảo vệ scope:

```java
public static long readAtMost(DataSource source, int limit)
        throws SQLException {
    if (limit < 0) throw new IllegalArgumentException("limit < 0");
    String sql = "SELECT id FROM accounts ORDER BY id";

    try (Connection con = source.getConnection();
         PreparedStatement ps = con.prepareStatement(
                 sql,
                 ResultSet.TYPE_FORWARD_ONLY,
                 ResultSet.CONCUR_READ_ONLY)) {
        // Cấu hình statement TRƯỚC lúc executeQuery().
        ps.setFetchSize(100);
        ps.setQueryTimeout(10);

        try (ResultSet rs = ps.executeQuery()) {
            long consumed = 0;
            while (consumed < limit && rs.next()) {
                long id = rs.getLong("id");
                consumed++;
            }
            return consumed;
        }
    }
}
```

Đoạn mã là một ví dụ **đặt bên trong lớp có import** `java.sql.*` và `javax.sql.DataSource`. Nó cố tình cấu hình `setFetchSize(100)` và `setQueryTimeout(10)` **trước** khi gọi `executeQuery()`; khi thoát sớm khỏi vòng lặp, `try-with-resources` vẫn đóng đủ các tài nguyên.

Nếu chỉ cần N hàng, tốt hơn là đặt giới hạn trong SQL (ví dụ `LIMIT ?` ở DB hỗ trợ) để tránh DB tạo nhiều hàng không cần thiết. `setFetchSize` chỉ là gợi ý, không phải bằng chứng server streaming đúng số hàng.

### Kiểm thử cancel

`Statement.cancel()` là **yêu cầu** gửi tới driver/DB, không cam kết statement dừng tức thì. Với test concurrency:

- Dùng `CountDownLatch` để biết lúc nào worker đã bắt đầu query.
- Trên thread khác, gửi tín hiệu cancel phù hợp và gọi `Statement.cancel()` khi có statement đang hoạt động.
- Đợi worker kết thúc **có deadline**, xác minh nó đóng `ResultSet`, `Statement` và `Connection`.
- Kiểm tra pool active giảm; nếu DB còn query đang chạy, thu thập bằng chứng từ server theo khả năng test.
- Không giả định `Thread.interrupt()` hoặc `Future.cancel(true)` một mình sẽ hủy JDBC I/O đang chờ.

Với streaming dưới transaction `autoCommit=false`, đóng ResultSet **không đồng nghĩa transaction đã kết thúc**. Test phải xác nhận `commit()`/`rollback()` và trạng thái connection trước khi trả pool.

## 14. Batch và generated keys cũng tạo ResultSet cần đóng

Một lỗi thường bị bỏ qua là `Statement.getGeneratedKeys()` trả về **ResultSet**. Khi chèn dữ liệu, resource này cũng cần được đóng:

```java
String sql = "INSERT INTO customers(full_name) VALUES (?)";
try (Connection con = source.getConnection();
     PreparedStatement ps = con.prepareStatement(
             sql, Statement.RETURN_GENERATED_KEYS)) {
    ps.setString(1, name);
    ps.executeUpdate();
    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long id = keys.getLong(1);
            // Sử dụng id.
        }
    }
}
```

Nếu `getGeneratedKeys()` hoặc `keys.next()` ném lỗi, test phải xác nhận statement và connection vẫn được đóng. Việc generated keys được hỗ trợ và kiểu ID được trả phụ thuộc DB/driver; không cần dựa vào cấu trúc SQL này để kết luận mọi DB đều tự sinh ID giống nhau.

Với `executeBatch()`:

```java
try (Connection con = source.getConnection();
     PreparedStatement ps = con.prepareStatement(
             "UPDATE accounts SET balance = ? WHERE id = ?")) {
    for (AccountChange change : changes) {
        ps.setBigDecimal(1, change.balance());
        ps.setLong(2, change.id());
        ps.addBatch();
    }
    ps.executeBatch();
}
```

Ví dụ dùng kiểu nghiệp vụ `AccountChange` và danh sách `changes` do caller cung cấp; cần khai báo chúng ở lớp dùng mẫu. Đây chỉ là **cấu trúc scope tài nguyên**; khi cần atomicity cho cả batch phải mở transaction và rollback nếu `BatchUpdateException` xảy ra. Test cần bảo đảm `ps.close()` và `con.close()` ngay cả khi batch báo thất bại giữa chừng, đồng thời đọc `getUpdateCounts()`/`getLargeUpdateCounts()` để đánh giá trạng thái theo driver.

Nếu dùng `Clob`, `Blob`, `SQLXML` hoặc các tài nguyên JDBC khác, hãy kiểm tra API cleanup riêng như `free()` khi phù hợp với đối tượng và driver; không giả định đóng statement tự thay thế mọi lời gọi cleanup cần thiết của một tài nguyên đã lấy ra.

## 15. Kiểm thử đồng thời và phát hiện race khi thất bại

Một repository có thể hoạt động đúng với một thread nhưng rò rỉ trong stress test khi hàng chục tác vụ cùng gặp lỗi.

Ví dụ điều phối test:

```text
Khởi tạo pool maximumPoolSize = 3
  |
  +-- Worker A: borrow connection → SQL lỗi ở execute
  +-- Worker B: borrow connection → lỗi ở mapper
  +-- Worker C: borrow connection → cancel khi đang fetch
  +-- Worker D: chờ pool vì đang đủ 3 active
  |
  +-- Thả latch cho A/B/C kết thúc
  +-- A/B/C đóng resource ở finally / try-with-resources
  +-- D được cấp connection trước deadline
  +-- Pool active → 0 khi tất cả work đã hoàn tất
```

Nên dùng `CountDownLatch`, `CyclicBarrier` hoặc công cụ đồng bộ tương ứng để tạo **điểm lỗi tái hiện được**. Dùng `Thread.sleep()` tùy tiện thường tạo test flakey và có thể che một race thực sự.

Kiểm tra ít nhất:

- Không chia sẻ cùng một `Connection`/`PreparedStatement` mutable giữa request song song.
- Số connection active không vượt giới hạn pool, và trở về mức phù hợp sau khi task hoàn tất.
- Tác vụ chờ borrow không bị treo vô hạn sau khi những tác vụ trước gặp lỗi.
- Khi một task bị cancel, nó không đóng connection của task khác.
- Nếu pool chủ động evict connection hỏng, task sau nhận một connection dùng được thay vì tái sử dụng vật lý không an toàn.
- Không có thread ngầm/queue tiếp tục giữ reference đến result set đã đóng.

Điều kiện đạt không nên chỉ là “test chạy xong không timeout”: kiểm tra **metric pool, kết quả từng worker, số lần cleanup và dữ liệu cuối**.

## 16. Leak detection: công cụ hỗ trợ, không phải bằng chứng duy nhất

Connection pool thường có thống kê và cơ chế phát hiện việc mượn connection quá lâu. Ví dụ HikariCP có cấu hình **leak detection threshold** cho mục đích chẩn đoán:

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(jdbcUrl);
config.setUsername(user);
config.setPassword(password);
config.setMaximumPoolSize(4);
config.setLeakDetectionThreshold(10_000); // milliseconds, chỉ minh họa.
```

Ngưỡng này giúp pool **cảnh báo** nếu một connection được mượn lâu hơn mức đã đặt. Nó không biến lời gọi `Connection.close()` sai thành đúng, không tự rollback giao dịch và không thể phân biệt hoàn toàn giữa leak thật và một truy vấn hợp lệ đang chạy lâu. Trong production, chọn ngưỡng dựa trên phân phối thời gian giữ connection thực tế và chính sách logging/bảo mật.

Khi kiểm thử, quan sát:

| Chỉ số | Ý nghĩa khi kiểm thử lỗi |
| --- | --- |
| Active connections | Có logical connection bị mượn mà không được trả? |
| Idle connections | Pool còn connection sẵn sàng hay đã bị tiêu thụ hết? |
| Pending/awaiting borrow | Có tác vụ bị kẹt vì thiếu connection? |
| Borrow/usage duration | Tài nguyên được giữ bao lâu sau khi request lỗi? |
| Connection timeout count | Các request khác bắt đầu chịu ảnh hưởng chưa? |
| Leak detection warnings | Có đường code mượn connection bất thường? |
| DB active sessions/cursors | Tài nguyên phía server có được giải phóng? |
| Transaction state/locks | Có transaction chưa kết thúc giữ khóa/snapshot? |

**Pool active về 0 là điều kiện quan sát hữu ích nhưng không đủ**: mock test còn phải chứng minh thứ tự close và lỗi được giữ, integration test cần xác minh dữ liệu/transaction, còn DB-side cursor/session có thể cần công cụ giám sát riêng.

Không log nguyên `PreparedStatement.toString()`, bind values, SQL có PII hay toàn bộ message ngoại lệ khi test leak. Chỉ cần query ID, trace ID, SQLState, thời gian borrow và số connection. Nếu test dùng canary data, xác minh log của driver/pool không vô tình chứa dữ liệu nhạy cảm.

## 17. Những phản mẫu nên tránh

| Phản mẫu | Vì sao thất bại | Thay thế |
| --- | --- | --- |
| Chỉ test query thành công | Không có bằng chứng cleanup khi ném lỗi | Chèn lỗi ở mọi giai đoạn |
| Đóng connection trong nhánh `if (success)` | Lỗi bị bỏ qua cleanup | `try-with-resources` quanh connection |
| Gọi `close()` trong `finally` không bảo toàn suppressed | Lỗi close có thể che lỗi SQL chính | `try-with-resources` hoặc `addSuppressed()` đúng |
| Mock `Connection.close()` rồi tuyên bố không leak pool | Mock không chứng minh physical connection | Integration test pool/driver thật |
| Chỉ assert không có exception | Code có thể nuốt lỗi/đóng sai | Assert lỗi chính, suppressed, close order |
| Dùng `Thread.sleep()` để ép race | Test không ổn định | Latch/barrier, deadline hữu hạn |
| Kiểm tra socket vật lý về 0 sau mỗi request | Pool cố ý giữ idle connections | Đo active/borrowed; close pool ở lifecycle |
| Sau `rollback()` lỗi vẫn reset `autoCommit(true)` | Có thể tạo trạng thái transaction không an toàn | Tách trạng thái transaction, loại connection nghi hỏng |
| Cho rằng `commit()` timeout nghĩa rollback | Commit có thể đã xảy ra | Request ID/idempotency và đối soát |
| Đóng `ResultSet` nhưng để transaction mở | Lock/snapshot còn giữ | Kết thúc transaction rõ ràng |
| Trả `ResultSet` ra ngoài repository | Không rõ ai đóng statement và connection | Trả DTO hoặc callback sở hữu scope |
| Đóng pool trong DAO khi một query thất bại | Làm hỏng request không liên quan | DAO chỉ trả logical connection |
| Bỏ qua `getGeneratedKeys()` ResultSet | Dễ quên cursor phụ | Đóng generated keys bằng `try-with-resources` |
| Báo test PASS chỉ vì leak warning không xuất hiện | Threshold có thể quá cao hoặc không bật | Assert resource counts/close behavior |
| Test lỗi bằng cách làm rơi DB production | Ảnh hưởng người dùng và khó phục hồi | Testcontainer/sandbox DB riêng |

## 18. Bài tập thực hành

**Bài 1 — Ma trận lỗi.** Với DAO ở mục 3, viết thêm test gây lỗi tại `rs.getBigDecimal("balance")` và xác nhận `ResultSet`, `PreparedStatement`, `Connection` được đóng đúng thứ tự. Giải thích tại sao test chỉ gọi `verify(con).close()` là chưa đủ.

**Bài 2 — Close cũng lỗi.** Mô phỏng `executeQuery()` ném SQLException A, `ps.close()` ném SQLException B và `con.close()` ném SQLException C. Chứng minh caller nhận A và `getSuppressed()` có B, C. Sau đó thử trường hợp chỉ close lỗi mà phần đọc đã thành công.

**Bài 3 — Transaction thất bại.** Viết test cho `OrderStatusWriter`: lệnh UPDATE lỗi, rollback thành công rồi reset autoCommit; một test khác rollback lỗi nên không reset autoCommit. Nêu cách xác minh pool không cấp lại một connection hỏng trong integration test.

**Bài 4 — Kết quả commit không rõ.** Trong hệ thống đơn hàng, `commit()` ném lỗi mất kết nối sau khi server đã xử lý commit. Tại sao test mock không thể khẳng định DB rollback? Thiết kế khóa request và truy vấn đối soát để tránh tạo đơn trùng.

**Bài 5 — Test pool exhaustion.** Dựng pool có maximumPoolSize=1 và connectionTimeout ngắn. Cố ý giữ connection trong một scope test, xác nhận borrow thứ hai timeout, sau khi trả connection có thể borrow lại. Từ đó đề xuất test phát hiện rò rỉ sau 100 request lỗi.

**Bài 6 — Đọc stream lớn.** Truy vấn BLOB qua `ResultSet.getBinaryStream()`, copy đến một `OutputStream` giả ném IOException sau N byte. Thiết kế các scope cleanup cho input stream, result set, statement và connection; test không còn active borrow sau lỗi.

**Bài 7 — Cancel race.** Một thread đang `ResultSet.next()`, thread khác gửi tín hiệu hủy. Dùng `CountDownLatch` để tạo điểm hủy, kiểm tra driver có hỗ trợ `Statement.cancel()` và chứng minh worker vẫn kết thúc scope cleanup trong deadline được cấu hình.

## 19. Checklist cho test JDBC chống leak

- [ ] Đã xác định ai sở hữu `Connection`, `PreparedStatement`, `ResultSet` và các stream phụ?
- [ ] Có `try-with-resources` ở mỗi cấp thích hợp, không trả tài nguyên JDBC ra ngoài scope đã đóng?
- [ ] Test từng điểm lỗi: borrow, prepare, bind, execute, fetch, getter/mapper, commit, rollback và close?
- [ ] Test cả đường `Optional.empty()`/`return`/`break` sớm?
- [ ] Assert **đúng lỗi chính** và kiểm tra `getSuppressed()` khi cleanup cũng thất bại?
- [ ] Assert thứ tự `ResultSet.close() → Statement.close() → Connection.close()`?
- [ ] Với lỗi `getConnection()`, không cố đóng connection chưa được cấp?
- [ ] Với transaction, assert rollback, commit, reset trạng thái và trường hợp rollback thất bại?
- [ ] Không coi `Connection.close()` là bảo đảm tự rollback hoặc loại physical connection hỏng?
- [ ] Có integration test với driver, DB và pool thật để xác minh active connections và khả năng borrow lại?
- [ ] Có kiểm thử concurrency, timeout và cancel bằng latch/deadline thay cho sleep tùy tiện?
- [ ] Với batch/generated keys/BLOB, đã đóng mọi ResultSet/stream phụ?
- [ ] Có đo pool active/idle/pending, borrow duration và leak warnings theo ngữ cảnh?
- [ ] Test không vô tình log SQL parameter, credential, PII hoặc dữ liệu nhạy cảm trong exception?
- [ ] Khi `commit()` mơ hồ, có idempotency/đối soát thay vì retry ghi mù?
- [ ] Các test gây mất kết nối và pool exhaustion chỉ chạy trên môi trường test có giới hạn?

**Kiểm thử rò rỉ tài nguyên khi thao tác thất bại** cần nhiều hơn một assertion “đã gọi `close()`”. Ở tầng Java, unit test chèn lỗi vào từng bước và xác nhận **đúng resource được đóng, đúng thứ tự, đúng ngoại lệ được giữ**. Ở tầng tích hợp, kiểm tra **pool thực sự nhận lại logical connection, DB không giữ transaction/cursor bất thường, công việc tiếp theo vẫn có thể lấy connection**. Kết hợp hai tầng này giúp ứng dụng JDBC xử lý lỗi mà không biến một vài request thất bại thành sự cố cạn kết nối của cả hệ thống.

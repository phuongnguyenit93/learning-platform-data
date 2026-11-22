# Thiết kế khối xử lý lỗi vẫn bảo toàn ngoại lệ ban đầu

Một giao dịch JDBC thường thực hiện nhiều câu SQL như một đơn vị: hoặc tất cả thay đổi được xác nhận bằng `commit()`, hoặc các thay đổi chưa được xác nhận được hủy bằng `rollback()`. Nhưng khi chính lệnh `rollback()`, bước khôi phục trạng thái `Connection` hoặc thao tác đóng tài nguyên cũng thất bại, **ngoại lệ nào phải được trả cho người gọi?**

Đối với một ứng dụng Java sử dụng JDBC, `DataSource`, `PreparedStatement`, `ResultSet` và transaction, câu trả lời quan trọng là: **giữ ngoại lệ đã gây ra sự cố nghiệp vụ/SQL làm ngoại lệ chính; gắn các lỗi phát sinh trong quá trình dọn dẹp dưới dạng thông tin bổ sung**. Nếu mã xử lý lỗi vô tình thay thế lỗi chính bằng lỗi `rollback()`, người vận hành có thể chỉ thấy “connection closed” mà không còn biết câu SQL nào đã vi phạm ràng buộc hoặc gây deadlock.

Bài này tập trung vào cách thiết kế khối `try/catch/finally` trong chương **Giao dịch cơ bản**: phân định lỗi chính và lỗi thứ cấp, dùng `Throwable.addSuppressed()`, tận dụng `try-with-resources`, quản lý `autoCommit`, và kiểm thử các trường hợp hỏng liên tiếp. Các ví dụ dùng API JDBC chuẩn; hành vi riêng của transaction và connection pool cần được xác nhận với driver và cơ sở dữ liệu thực tế.

## 1. Vì sao lỗi trong `finally` có thể che mất lỗi gốc?

Giả sử một ứng dụng chuyển tiền từ tài khoản A sang B. Khi câu `UPDATE` thứ hai bị lỗi, ứng dụng phải rollback. Nhưng kết nối vừa mất, nên `rollback()` cũng ném `SQLException`:

```text
executeUpdate()  -> SQLException A: deadlock / constraint / network ...
rollback()       -> SQLException B: connection is closed
close()          -> SQLException C: cannot return connection to pool
```

Trong ngữ cảnh này, **A là nguyên nhân chính của luồng thất bại**, còn B và C giải thích vì sao khôi phục/dọn dẹp cũng không hoàn tất. Nếu chỉ trả B hoặc C, thông tin giúp xác định thao tác ban đầu gây lỗi sẽ bị mất.

Một cách viết dễ gặp nhưng không an toàn:

```java
try {
    connection.setAutoCommit(false);
    doBusinessUpdates(connection);
    connection.commit();
} catch (SQLException original) {
    connection.rollback();  // Có thể ném lỗi mới, che original.
    throw original;
} finally {
    connection.close();     // Cũng có thể che ngoại lệ đang lan truyền.
}
```

Nếu `rollback()` thất bại, dòng `throw original` không được thực thi. Nếu `close()` ném lỗi trong `finally`, lỗi đó có thể thay thế ngoại lệ đang được ném. Cả hai đều khiến chẩn đoán sự cố khó hơn.

Đặc biệt **không dùng `return` trong `finally`**. `return` ở đây có thể làm mất hẳn ngoại lệ và giá trị trả về của khối `try/catch`. Cũng không dùng `catch (SQLException e) { /* bỏ qua */ }` để biến một lần ghi dữ liệu thất bại thành kết quả thành công giả.

## 2. Phân loại ngoại lệ theo giai đoạn giao dịch

| Giai đoạn | Ví dụ lỗi | Điều cần bảo toàn |
| --- | --- | --- |
| Lấy kết nối | `dataSource.getConnection()` lỗi | Ngoại lệ lấy kết nối là lỗi chính; chưa có connection để rollback |
| Chuẩn bị giao dịch | `getAutoCommit()` hoặc `setAutoCommit(false)` lỗi | Lỗi thiết lập là lỗi chính; không mặc định transaction đã bắt đầu |
| Thực thi SQL | `prepareStatement()`, `executeUpdate()`, `ResultSet` hoặc logic xử lý lỗi | Ngoại lệ SQL/logic là lỗi chính; thử rollback |
| `commit()` | Mất kết nối, timeout hoặc DB báo lỗi | Lỗi commit là lỗi chính; **trạng thái commit có thể không xác định** |
| `rollback()` trong đường lỗi | Kết nối không còn dùng được | Gắn lỗi rollback vào ngoại lệ chính, không thay thế nó |
| Khôi phục cấu hình | `setAutoCommit(original)` lỗi | Gắn vào lỗi chính nếu có; nếu không, đây là lỗi đầu tiên cần báo |
| Đóng `Statement`, `ResultSet`, `Connection` | `close()` lỗi | `try-with-resources` tự gắn dưới dạng `suppressed` khi đã có lỗi chính |

Từ góc nhìn hệ thống, ngoại lệ đầu tiên thường hữu ích nhất vì nó xảy ra trước những lỗi dây chuyền. Nhưng “đầu tiên” không nhất thiết nói lên **nguyên nhân hạ tầng sâu nhất**: lỗi khi commit đôi khi chỉ phản ánh việc mất kết nối với DB. Vì vậy cần giữ **cả ngoại lệ chính lẫn dấu vết lỗi dọn dẹp**, thông điệp SQL và ngữ cảnh thao tác.

## 3. Công cụ của Java: `addSuppressed()`, `getSuppressed()` và `try-with-resources`

Mỗi `Throwable` có thể chứa các ngoại lệ *suppressed* (bị giữ lại như thông tin phụ):

```java
SQLException original =
        new SQLException("INSERT failed", "23505");
SQLException rollbackFailure =
        new SQLException("Rollback failed", "08006");

original.addSuppressed(rollbackFailure);

System.out.println(original.getMessage());            // INSERT failed
System.out.println(original.getSuppressed().length);  // 1
original.printStackTrace(); // Hiển thị cả nhánh Suppressed.
```

Khi một hàm ném `original`, người gọi vẫn bắt được **đúng đối tượng `SQLException` ban đầu**. `rollbackFailure` chỉ nằm trong `original.getSuppressed()`. Không gọi `original.addSuppressed(original)` vì Java cấm tự-suppression.

`try-with-resources` xử lý tình huống này tự động đối với tài nguyên `AutoCloseable`:

```java
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.executeUpdate(); // Ném lỗi A.
}                     // ps.close() ném lỗi B.
```

Trong trường hợp trên, A tiếp tục là ngoại lệ chính và B được Java gắn vào A. Nếu thân `try` chạy thành công nhưng `close()` thất bại, lỗi đóng tài nguyên trở thành ngoại lệ chính vì không có lỗi trước đó. Với nhiều tài nguyên, chúng được đóng theo **thứ tự ngược khi khai báo**; các lỗi đóng sau tiếp tục được lưu dưới dạng suppressed nếu đã có lỗi đang lan truyền.

Điểm cần phân biệt:

- **`getCause()`** diễn tả một ngoại lệ được bọc bởi ngoại lệ khác, chẳng hạn `throw new RepositoryException("...", sqlError)`.
- **`getSuppressed()`** diễn tả các lỗi bổ sung xảy ra trong khi xử lý hoặc dọn dẹp cho lỗi chính.
- **`SQLException.getNextException()`** là chuỗi thông tin lỗi SQL do driver/DB cung cấp; nó **không thay thế** `getSuppressed()` và không nên bị bỏ qua khi chẩn đoán lỗi JDBC.

Nếu ứng dụng bọc một `SQLException` bằng ngoại lệ nghiệp vụ, phải giữ nó làm **cause**; việc bọc lỗi không nên xóa mất chuỗi `nextException` hoặc suppressed đã có trên đối tượng SQL gốc.

## 4. Quy tắc thiết kế khối giao dịch an toàn

Một cấu trúc giao dịch nên tuân theo thứ tự:

1. Lấy kết nối và bảo đảm kết nối được đóng bằng `try-with-resources`.
2. Ghi nhớ trạng thái `autoCommit` trước khi thay đổi.
3. Tắt `autoCommit` thành công mới xem là đã bước vào giao dịch do hàm quản lý.
4. Chạy tất cả câu SQL trên **cùng một `Connection`** rồi gọi `commit()` khi hoàn tất.
5. Nếu phát sinh lỗi, thử `rollback()`; lỗi rollback nếu có được gắn vào lỗi ban đầu và lỗi ban đầu được ném lại.
6. Chỉ khôi phục `autoCommit` khi đã xác định giao dịch kết thúc bằng `commit()` hoặc rollback **thành công**. Nếu rollback thất bại, không tùy tiện gọi `setAutoCommit(true)` vì một số cách chuyển từ `false` sang `true` có thể xác nhận giao dịch còn dang dở.
7. Để `try-with-resources` đóng kết nối; kiểm tra connection pool có loại bỏ kết nối không an toàn sau lỗi kết nối/rollback.

Hai biến trạng thái cần được hiểu đúng:

- `transactionStarted`: hàm đã gọi `setAutoCommit(false)` thành công, nên có quyền thử rollback khi xử lý thất bại.
- `transactionEnded`: `commit()` hoặc `rollback()` đã **trả về thành công**, đủ cơ sở tiến hành bước khôi phục `autoCommit`.

Đây là trạng thái quản lý luồng code, không phải lời khẳng định tuyệt đối về số phận dữ liệu khi mất kết nối. Chẳng hạn, `commit()` có thể đã được DB thực hiện nhưng ứng dụng không nhận được phản hồi; việc bắt được `SQLException` từ `commit()` **không chứng minh DB đã rollback**.

## 5. Ví dụ hoàn chỉnh: chuyển tiền và bảo toàn lỗi gốc

Ví dụ sử dụng schema PostgreSQL:

```sql
CREATE TABLE bank_accounts (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(19, 2) NOT NULL CHECK (balance >= 0)
);
```

Ứng dụng chỉ coi giao dịch thành công khi tài khoản nguồn đã bị trừ tiền, tài khoản đích đã được cộng tiền và `commit()` hoàn tất. `PreparedStatement` được dùng để tham số hóa SQL, còn các helper đóng statement đúng cách.

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.Objects;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = Objects.requireNonNull(dataSource, "dataSource");
    }

    public void transfer(long fromId, long toId, BigDecimal amount)
            throws SQLException {
        Objects.requireNonNull(amount, "amount");
        if (fromId == toId || amount.signum() <= 0) {
            throw new IllegalArgumentException("Tài khoản hoặc số tiền không hợp lệ");
        }

        try (Connection con = dataSource.getConnection()) {
            boolean previousAutoCommit = con.getAutoCommit();
            boolean transactionStarted = false;
            boolean transactionEnded = false;
            Throwable originalFailure = null;

            try {
                con.setAutoCommit(false);
                transactionStarted = true;

                debit(con, fromId, amount);
                credit(con, toId, amount);

                con.commit();
                transactionEnded = true;
            } catch (SQLException | RuntimeException | Error failure) {
                originalFailure = failure;

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

                throw failure; // Luôn ném lại chính lỗi đã bắt.
            } finally {
                if (transactionStarted && transactionEnded) {
                    try {
                        con.setAutoCommit(previousAutoCommit);
                    } catch (SQLException | RuntimeException | Error resetFailure) {
                        if (originalFailure != null) {
                            if (resetFailure != originalFailure) {
                                originalFailure.addSuppressed(resetFailure);
                            }
                        } else {
                            // Commit đã thành công nhưng khôi phục connection lỗi.
                            throw resetFailure;
                        }
                    }
                }
            }
        } // Nếu close() lỗi, try-with-resources giữ lỗi chính nếu đã có.
    }

    private static void debit(
            Connection con, long accountId, BigDecimal amount)
            throws SQLException {
        String sql = """
                UPDATE bank_accounts
                SET balance = balance - ?
                WHERE id = ? AND balance >= ?
                """;

        try (PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, accountId);
            ps.setBigDecimal(3, amount);
            if (ps.executeUpdate() != 1) {
                throw new SQLException(
                        "Tài khoản nguồn không tồn tại hoặc không đủ số dư");
            }
        }
    }

    private static void credit(
            Connection con, long accountId, BigDecimal amount)
            throws SQLException {
        String sql = """
                UPDATE bank_accounts
                SET balance = balance + ?
                WHERE id = ?
                """;

        try (PreparedStatement ps = con.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, accountId);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Tài khoản đích không tồn tại");
            }
        }
    }
}
```

Ví dụ sử dụng text block nên cần Java 15+ (khuyến nghị Java 17+ trong dự án mới). Nếu ứng dụng dùng Java cũ hơn, thay text block bằng chuỗi thông thường. Mã ví dụ giả định `DataSource` cấp kết nối dành riêng cho thao tác và việc đóng kết nối được quản lý đúng bởi driver/pool. Chỉ dùng số tiền có độ chính xác phù hợp với `NUMERIC(19, 2)` sau khi validate theo quy tắc nghiệp vụ.

### Vì sao từng phần quan trọng?

| Cơ chế | Vai trò |
| --- | --- |
| `try (Connection con = ...)` | Đóng kết nối ngay cả khi SQL, rollback hoặc khôi phục trạng thái lỗi; lỗi `close()` không che lỗi đang lan truyền |
| `previousAutoCommit` | Khôi phục cấu hình ban đầu, tránh làm rò rỉ trạng thái giao dịch sang lần sử dụng kết nối tiếp theo |
| `transactionStarted` | Chỉ thử rollback khi đã thiết lập chế độ giao dịch thành công |
| `transactionEnded` | Tránh gọi `setAutoCommit(true)` sau khi rollback thất bại |
| `originalFailure` | Cho biết có lỗi xảy ra trước `finally` để gắn lỗi khôi phục như suppressed |
| `failure.addSuppressed(rollbackFailure)` | Giữ nguyên lỗi gây thất bại, bổ sung lý do rollback không thành công |
| `throw failure` | Ném lại ngoại lệ chính, giữ stack trace và SQLState của nó |
| `PreparedStatement` + `executeUpdate() == 1` | Truyền tham số đúng kiểu và từ chối thao tác khi không tác động đúng một tài khoản |

Không bắt `SQLException` rồi tự động chuyển thành kết quả `false` hoặc giá trị mặc định: người gọi cần biết transaction thất bại để phản hồi, ghi nhận và xử lý thích hợp.

### Giới hạn quan trọng của ví dụ

- **Nếu `rollback()` thất bại**, kết nối có thể không còn đáng tin cậy. Ví dụ bỏ qua khôi phục `autoCommit`, để cơ chế `close()` xử lý; trong production phải cấu hình pool loại bỏ/không tái sử dụng connection bị lỗi hoặc dùng API vô hiệu hóa riêng của pool. API JDBC chuẩn không bảo đảm mọi pool sẽ loại bỏ connection hỏng khi `close()`.
- **Nếu `commit()` ném lỗi**, trạng thái cuối cùng của transaction có thể chưa xác định, kể cả khi thử rollback sau đó. Không tự động chuyển tiền lại dựa duy nhất trên kết quả ngoại lệ; cần kiểm tra trạng thái hoặc dùng khóa idempotency/tham chiếu giao dịch.
- **Nếu `setAutoCommit(previousAutoCommit)` lỗi sau khi `commit()` thành công**, hàm báo lỗi dọn dẹp dù dữ liệu có thể đã được commit. Người gọi phải phân biệt lỗi cleanup với lỗi SQL khi quyết định retry.
- **Nếu `setAutoCommit(false)` ném lỗi**, đoạn code không coi giao dịch đã bắt đầu và không gọi rollback mù; đóng và kiểm tra connection. Trạng thái thực tế của kết nối sau lỗi thiết lập có thể phụ thuộc driver.
- **Nếu driver ném `Error` nghiêm trọng**, chương trình vẫn ném lại `Error` gốc sau nỗ lực dọn dẹp. Trong tình huống cạn kiệt tài nguyên JVM, không thể bảo đảm tất cả thao tác cleanup hoàn tất; mục tiêu của mẫu là giữ luồng ngoại lệ hợp lý, không khẳng định có thể phục hồi mọi lỗi hệ thống.

Trong hệ thống chuyển tiền thực tế, ngoài transaction còn cần kiểm soát concurrency (khóa, isolation level, deadlock), idempotency, nhật ký giao dịch và đối soát. Bài này giới hạn vào **bảo toàn ngoại lệ khi khối giao dịch thất bại**.

## 6. Diễn biến khi nhiều bước liên tiếp thất bại

Xét đoạn code trên với tình huống câu `UPDATE` thứ hai thất bại:

```text
1. debit()                 -> thành công; thay đổi chưa commit
2. credit()                -> SQLException A
3. catch giữ A             -> originalFailure = A
4. con.rollback()          -> SQLException B
5. A.addSuppressed(B)      -> A vẫn là lỗi chính
6. transactionEnded=false  -> bỏ qua khôi phục autoCommit
7. con.close()             -> SQLException C
8. try-with-resources      -> A.getSuppressed() chứa B và C
9. Caller nhận lại         -> chính SQLException A
```

Nếu rollback **thành công** nhưng khôi phục `autoCommit` thất bại, A sẽ có lỗi khôi phục dưới dạng suppressed. Nếu đóng kết nối cũng lỗi, lỗi đóng tiếp tục bị suppressed. Nếu phần SQL, commit, restore đều thành công mà **chỉ close lỗi**, lỗi close là ngoại lệ chính duy nhất.

Một ma trận kết quả:

| Lỗi SQL/commit | Lỗi rollback | Lỗi restore/close | Ngoại lệ người gọi nhận |
| --- | --- | --- | --- |
| Không | Không áp dụng | Không | Không có ngoại lệ |
| Có: A | Không | Không | A |
| Có: A | Có: B | Có: C khi close | A; B và C là suppressed |
| Có: A | Rollback thành công | Có: C khi restore | A; C là suppressed |
| Không, commit thành công | Không áp dụng | Có: C khi restore | C, vì đây là lỗi đầu tiên |
| Không, commit thành công | Không áp dụng | Có: C khi close | C, vì đây là lỗi đầu tiên |

Điểm then chốt: **không che lỗi ban đầu**, nhưng cũng **không xóa lỗi phát sinh sau đó**. Điều này giúp biết cả nguyên nhân sự cố lẫn rủi ro transaction có thể chưa được dọn sạch.

## 7. Cách xử lý `SQLException`: SQLState, mã nhà cung cấp và chuỗi lỗi

Ngoài `getMessage()`, `SQLException` có:

- `getSQLState()`: mã trạng thái SQL (ví dụ lớp `23` thường liên quan ràng buộc toàn vẹn; `40` liên quan rollback transaction; `08` liên quan kết nối). Mã cụ thể và mức độ tuân thủ khác theo driver/DB.
- `getErrorCode()`: mã lỗi do nhà cung cấp cơ sở dữ liệu định nghĩa.
- `getNextException()`: chuỗi ngoại lệ bổ sung do driver gửi, ví dụ nhiều lỗi từ cùng một batch.
- `getSuppressed()`: lỗi thứ cấp như rollback, restore, close mà ứng dụng/Java gắn vào.
- `getCause()`: ngoại lệ gốc khi một lỗi được bọc bởi lỗi khác.

Ví dụ ghi log với ngữ cảnh hợp lý:

```java
import java.sql.SQLException;
import java.util.logging.Level;
import java.util.logging.Logger;

public static void logSqlFailure(Logger logger, SQLException e) {
    logger.log(Level.SEVERE,
            "Giao dịch JDBC thất bại: SQLState=" + e.getSQLState()
            + ", vendorCode=" + e.getErrorCode(), e);

    for (SQLException next = e.getNextException();
         next != null; next = next.getNextException()) {
        logger.log(Level.SEVERE,
                "Lỗi SQL bổ sung: state=" + next.getSQLState()
                + ", vendorCode=" + next.getErrorCode(), next);
    }
}
```

Đặt hàm này trong lớp tiện ích logging phù hợp. `Logger.log(..., e)` thường in stack trace và nhánh suppressed/cause; vòng `getNextException()` minh họa vì sao cần xem thêm chuỗi của JDBC. Khi kết hợp với framework logging, nên tránh in cùng một đối tượng nhiều lần không cần thiết.

Giữ đủ ngữ cảnh để xác định thao tác đang làm (tên nghiệp vụ, mã tương quan, mã transaction nội bộ, câu lệnh SQL đã chuẩn hóa), nhưng không ghi mật khẩu, chuỗi kết nối có thông tin nhạy cảm hoặc giá trị tham số chứa dữ liệu cá nhân vào log.

Với `BatchUpdateException`, mã cần kiểm tra thêm `getUpdateCounts()`/`getLargeUpdateCounts()` và `getNextException()`. Ngoại lệ từ một `executeBatch()` vẫn phải được bảo toàn làm lỗi chính, trong khi lỗi rollback (nếu có) được suppressed giống như trường hợp lệnh đơn.

## 8. Không mất lỗi khi bọc thành ngoại lệ tầng repository

Một ứng dụng có thể không muốn tầng service phụ thuộc trực tiếp vào `SQLException`. Khi chuyển sang ngoại lệ chuyên biệt, **giữ SQL error làm cause**, không chỉ chép mỗi thông điệp:

```java
public final class DataAccessFailure extends RuntimeException {
    public DataAccessFailure(String message, Throwable cause) {
        super(message, cause);
    }
}

public void runBusinessOperation() {
    try {
        transferService.transfer(101L, 202L, new BigDecimal("50.00"));
    } catch (SQLException sqlFailure) {
        throw new DataAccessFailure(
                "Không thể hoàn thành chuyển tiền", sqlFailure);
    }
}
```

Đây là các đoạn mã minh họa cần đặt vào lớp phù hợp, với trường `transferService` và import `BigDecimal`/`SQLException` tương ứng. `sqlFailure` giữ `SQLState`, vendor code, `nextException` và các ngoại lệ suppressed; tất cả vẫn truy cập được qua `getCause()`.

Đoạn sau làm mất thông tin quan trọng và nên tránh:

```java
// Không giữ cause và các lỗi phụ:
throw new DataAccessFailure(sqlFailure.getMessage(), null);
```

Tương tự, đừng bắt `Exception` ở mọi tầng rồi tạo một ngoại lệ mới với mỗi message; stack trace nguồn, SQLState và suppressed sẽ bị chôn vùi.

## 9. Retry, timeout và trạng thái commit chưa biết

Giữ ngoại lệ ban đầu là điều kiện cần để phân tích đúng, nhưng **không đủ** để quyết định chạy lại giao dịch:

1. **Lỗi trước commit, rollback thành công**: transaction hiện tại đã được rollback; có thể xem xét retry có giới hạn với các lỗi tạm thời phù hợp, theo chính sách nghiệp vụ.
2. **Lỗi kết nối hoặc timeout trong `commit()`**: DB **có thể đã commit** dù ứng dụng nhận `SQLException`. Retry vô điều kiện có thể ghi trùng, chuyển tiền hai lần hoặc tạo hai đơn hàng.
3. **Rollback thất bại**: trạng thái giao dịch và kết nối cần được xem là không đáng tin cậy. Giữ cả lỗi đầu tiên và lỗi rollback để hệ thống cảnh báo, loại connection không an toàn và đối soát.
4. **Lỗi chỉ xảy ra khi restore/close sau commit**: thao tác dữ liệu có thể đã thành công. Retry như thể transaction chắc chắn thất bại là nguy hiểm.

Ví dụ một API tạo giao dịch tài chính có thể nhận `request_id` duy nhất được lưu cùng bản ghi trong transaction. Khi mất phản hồi commit, client truy vấn trạng thái theo `request_id` trước khi tạo yêu cầu mới. Trong hệ quản trị hỗ trợ, ràng buộc `UNIQUE(request_id)` hỗ trợ chống ghi trùng; nhưng luồng xử lý kết quả “đã tồn tại” vẫn phải được định nghĩa rõ.

Với những lỗi có SQLState thuộc nhóm rollback transaction (như serialization conflict hoặc deadlock), chỉ retry khi toàn bộ thao tác có thể thực hiện lại an toàn và trạng thái commit đã được xác định theo hợp đồng của DB. Không áp dụng một chính sách retry chung cho mọi `SQLException`.

## 10. Những phản mẫu cần tránh

| Phản mẫu | Tại sao gây lỗi | Cách thay thế |
| --- | --- | --- |
| `catch (SQLException e) { rollback(); throw e; }` | Rollback ném lỗi sẽ che e | Bắt lỗi rollback riêng, `e.addSuppressed(...)`, ném lại e |
| `finally { connection.close(); }` thủ công | `close()` ném lỗi có thể thay thế ngoại lệ chính | `try-with-resources` cho JDBC resources |
| `finally { return false; }` | Mất ngoại lệ đang lan truyền | Không `return` từ `finally` |
| `catch (Exception e) { log(e); }` rồi trả thành công | Che thất bại và có thể để transaction dở dang | Ghi log đủ ngữ cảnh rồi propagate, hoặc trả kết quả lỗi có kiểu |
| `throw new RuntimeException(e.getMessage())` | Mất cause, SQLState, nextException, suppressed | `throw new RuntimeException(message, e)` |
| `setAutoCommit(true)` bất kể rollback có lỗi hay không | Có thể commit thay đổi đang chờ khi bật lại autoCommit | Chỉ restore sau commit/rollback thành công; xử lý connection hỏng riêng |
| Dùng một connection khác để rollback | Transaction gắn với **kết nối đã chạy SQL** | Gọi rollback trên chính connection đó |
| Đóng connection giữa các câu lệnh cần atomicity | Các câu lệnh có thể thuộc transaction khác nhau | Dùng một connection xuyên suốt |
| Mặc định `autoCommit=true` với nhiều câu SQL | Mỗi câu có thể được commit riêng, rollback sau đó không thể hủy các câu trước | Tắt `autoCommit` trước khi thực thi |
| Retry mọi lỗi kể cả commit không rõ kết quả | Có thể ghi dữ liệu trùng | Xác minh trạng thái, dùng idempotency hoặc đối soát |

Mã `try-with-resources` giải quyết vòng đời đóng tài nguyên, nhưng **không tự rollback** như một bảo đảm chung của JDBC. Phải gọi `rollback()` khi cần, và không dựa vào `close()` như một thay thế duy nhất cho xử lý giao dịch.

## 11. Kiểm thử những chuỗi lỗi khó

Kiểm thử cần xác minh không chỉ câu SQL thành công mà cả **danh tính ngoại lệ ban đầu và danh sách suppressed**. Có thể dùng fake/stub `Connection` và `PreparedStatement` có kiểm soát để kích hoạt nhiều lỗi liên tiếp, sau đó chạy kiểm thử tích hợp trên DB/driver thật cho phần hành vi transaction.

### Ma trận kiểm tra

| Kịch bản | Kết quả mong muốn |
| --- | --- |
| SQL thành công, commit thành công, close thành công | Không ném ngoại lệ; dữ liệu được commit |
| SQL lỗi A, rollback thành công | Người gọi nhận chính A; dữ liệu được rollback |
| SQL lỗi A, rollback lỗi B | Người gọi nhận chính A; `A.getSuppressed()` chứa B |
| SQL lỗi A, rollback lỗi B, close lỗi C | Người gọi nhận A; B và C nằm trong suppressed |
| SQL lỗi A, rollback thành công, restore lỗi B | Người gọi nhận A; B nằm trong suppressed |
| Commit thành công, restore lỗi B | Người gọi nhận B; cần biết transaction có thể đã commit |
| Commit thành công, close lỗi C | Người gọi nhận C; không được giả định transaction đã rollback |
| Commit lỗi A | Người gọi nhận A; kết quả commit chưa chắc chắn, có thể có lỗi rollback bổ sung |
| `setAutoCommit(false)` lỗi A | Không coi transaction đã khởi tạo thành công; A vẫn được bảo toàn |
| Statement lỗi A, đóng Statement lỗi B | A là chính, B suppressed nhờ `try-with-resources` |
| Code nghiệp vụ ném `RuntimeException` A | Cũng thử rollback, giữ A dù rollback/close lỗi |

Ví dụ assertion minh họa ý nghĩa cần kiểm tra:

```java
SQLException sqlError = new SQLException("DML failed");
SQLException rollbackError = new SQLException("Rollback failed");
sqlError.addSuppressed(rollbackError);

assert sqlError.getSuppressed().length == 1;
assert sqlError.getSuppressed()[0] == rollbackError;
```

Đây là minh họa nhỏ ở mức Java; `assert` chỉ chạy khi bật `-ea`. Test quan trọng hơn là gọi hàm `transfer(...)` với các tài nguyên được cấu hình để ném lỗi ở những vị trí cụ thể, rồi dùng assertion của framework kiểm thử để so sánh **cùng tham chiếu Throwable** (`assertSame`, nếu framework hỗ trợ). Trên DB thật, thử lỗi ràng buộc, deadlock, timeout và sự cố kết nối theo điều kiện thử nghiệm được kiểm soát.

Với transaction có nhiều câu SQL, nên xác nhận dữ liệu sau rollback thực sự trở lại trạng thái trước đó. Nếu connection/pool bị hỏng, cần xác minh connection ấy không bị phát lại cho yêu cầu khác; đây là phần không thể kết luận chỉ bằng mock.

## 12. Bài tập vận dụng

**Bài 1 — Sửa khối lỗi.** Đoạn code sau có thể làm mất lỗi ban đầu. Hãy sửa để dùng `try-with-resources`, rollback có `addSuppressed` và bảo toàn ngoại lệ từ `executeUpdate()`.

```java
Connection con = dataSource.getConnection();
try {
    con.setAutoCommit(false);
    updateA(con);
    updateB(con);
    con.commit();
} catch (SQLException e) {
    con.rollback();
    throw e;
} finally {
    con.close();
}
```

**Bài 2 — Chuỗi lỗi.** Giả sử `updateB` ném A, `rollback` ném B và `Connection.close` ném C. Người gọi nên nhận ngoại lệ nào? Dùng `getSuppressed()` để tìm B và C như thế nào?

**Bài 3 — Phân biệt lỗi cleanup và kết quả dữ liệu.** `commit()` thành công nhưng `setAutoCommit(true)` ném lỗi. Tại sao không thể kết luận transaction bị rollback và không thể retry chuyển tiền tùy ý?

**Bài 4 — Bọc lỗi.** Ở tầng repository, chuyển `SQLException` sang `DataAccessFailure` mà vẫn truy xuất được SQLState, vendor code, `getNextException()` và lỗi rollback suppressed. Viết một log entry cho mã tương quan của yêu cầu mà không đưa dữ liệu nhạy cảm vào log.

**Gợi ý:** Bài 1 tham khảo cấu trúc ở mục 5. Bài 2: A là lỗi chính, B/C là suppressed. Bài 3: quyết định commit đã có thể được DB thực thi trước khi cleanup lỗi. Bài 4: đặt SQL exception làm `cause` và khi cần kiểm tra `((SQLException) error.getCause()).getSuppressed()`.

## 13. Checklist trước khi hoàn tất một transaction JDBC

- [ ] Mọi câu SQL cần nhất quán chạy trên cùng một `Connection` và `autoCommit` được kiểm soát.
- [ ] Khi lỗi ở phần chính, code thử rollback và **ném lại ngoại lệ đầu tiên**.
- [ ] Lỗi rollback/restore được gắn bằng `addSuppressed`, không đè lên lỗi chính.
- [ ] `Connection`, `PreparedStatement` và `ResultSet` được quản lý bằng `try-with-resources`.
- [ ] Không `return` trong `finally`, không nuốt lỗi rồi báo thành công.
- [ ] Không bật lại autoCommit khi rollback thất bại và giao dịch có thể còn dang dở.
- [ ] Connection pool có chính sách xử lý connection không còn đáng tin cậy.
- [ ] Lỗi commit/cleanup được phân biệt với trạng thái dữ liệu; retry có kiểm soát và có idempotency khi cần.
- [ ] Log/giám sát giữ SQLState, vendor code, cause, nextException và suppressed có liên quan.
- [ ] Có kiểm thử tình huống SQL lỗi, rollback lỗi, restore lỗi, close lỗi và kiểm thử dữ liệu rollback trên DB thật.

Khi một giao dịch JDBC gặp nhiều lỗi nối tiếp, **ngoại lệ ban đầu kể câu chuyện thao tác đã thất bại; ngoại lệ suppressed kể chuyện những nỗ lực khôi phục cũng thất bại ra sao**. Thiết kế đúng khối `catch/finally` giúp cả hai phần thông tin cùng tồn tại, cho phép chẩn đoán chính xác hơn và tránh quyết định retry nguy hiểm khi trạng thái commit chưa rõ.

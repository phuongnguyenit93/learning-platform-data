# Nhận diện cập nhật bị mất khi đọc – sửa – ghi trong JDBC

Trong chương **Cô lập và khóa**, một lỗi đồng thời nguy hiểm là **cập nhật bị mất** (*lost update*). Lỗi xảy ra khi hai giao dịch cùng đọc một giá trị, mỗi giao dịch tính giá trị mới dựa trên bản đã đọc, rồi lần lượt ghi kết quả. Giao dịch ghi sau có thể **ghi đè kết quả của giao dịch ghi trước**, khiến một thay đổi hợp lệ biến mất.

Ví dụ, một tài khoản có 100.000 đồng. Hai yêu cầu đồng thời rút 10.000 đồng và 20.000 đồng. Nếu mỗi yêu cầu đều đọc số dư ban đầu là 100.000 rồi tự tính số dư còn lại và chạy `UPDATE account SET balance = ?`, kết quả cuối có thể là **80.000 hoặc 90.000 đồng**, thay vì **70.000 đồng**. Cả hai câu SQL đều có thể chạy thành công nhưng nghiệp vụ vẫn sai.

Với JDBC, nhận diện lỗi này đòi hỏi hiểu phạm vi transaction của `Connection`, cách `PreparedStatement` thực hiện `SELECT`/`UPDATE`, ý nghĩa của các isolation level và cơ chế khóa hoặc kiểm tra xung đột của cơ sở dữ liệu. Bài học trình bày các dấu hiệu nhận biết, lịch xen kẽ gây lỗi, ba phương án phòng tránh và cách kiểm chứng trên driver/DB thực tế.

## 1. Mô hình đọc – sửa – ghi dễ gây mất cập nhật

Giả sử có bảng:

```sql
CREATE TABLE account (
    id      BIGINT PRIMARY KEY,
    balance DECIMAL(18, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT account_balance_nonnegative CHECK (balance >= 0)
);
```

Cột `version` sẽ được dùng cho một giải pháp kiểm soát xung đột ở phần sau. Cú pháp `CHECK`, `DEFAULT` và cách kiểm tra ràng buộc có thể cần điều chỉnh theo hệ quản trị cơ sở dữ liệu.

Ứng dụng có thể viết luồng xử lý rút tiền như sau:

```text
SELECT balance FROM account WHERE id = ?
         |
         v
newBalance = balance - amount
         |
         v
UPDATE account SET balance = ? WHERE id = ?
```

Điểm rủi ro nằm ở khoảng trống **giữa câu `SELECT` và `UPDATE`**: giao dịch khác có thể cập nhật cùng bản ghi. Bản sao `balance` trong bộ nhớ Java không tự được làm mới khi dữ liệu trong DB thay đổi.

### Lịch chạy gây lỗi

Hai kết nối JDBC, `A` và `B`, xử lý cùng tài khoản có số dư ban đầu 100.000:

| Bước | Giao dịch A: rút 10.000 | Giao dịch B: rút 20.000 | Giá trị trong DB |
| --- | --- | --- | --- |
| 1 | `SELECT balance` → 100.000 | | 100.000 |
| 2 | | `SELECT balance` → 100.000 | 100.000 |
| 3 | Tính `100.000 - 10.000 = 90.000` | | 100.000 |
| 4 | | Tính `100.000 - 20.000 = 80.000` | 100.000 |
| 5 | `UPDATE ... SET balance = 90000`, commit | | 90.000 |
| 6 | | `UPDATE ... SET balance = 80000`, commit | **80.000** |

Đây là **lịch minh họa mà DB/isolation cho phép giao dịch B ghi giá trị cũ đã tính**. Trên một số cơ sở dữ liệu hoặc mức cô lập mạnh hơn, bước 6 có thể bị chặn, thất bại vì xung đột hoặc buộc giao dịch phải chạy lại. **Không thể khẳng định lịch này sẽ thành công giống nhau trên mọi DB.**

Điều quan trọng là **hai yêu cầu cùng nhận thành công nhưng một lần rút đã không còn được phản ánh trong số dư cuối**. Số tiền đúng sau hai lần rút là 70.000.

## 2. Vì sao transaction riêng lẻ vẫn có thể gặp lost update?

Một hiểu nhầm phổ biến là cứ gọi `setAutoCommit(false)` và `commit()` thì thao tác đọc – sửa – ghi chắc chắn an toàn. Transaction bảo đảm ranh giới commit/rollback, nhưng **mức cô lập và chiến lược điều phối ghi đồng thời** mới quyết định có xảy ra xung đột đọc cũ/ghi đè hay không.

```java
connection.setAutoCommit(false);
try {
    // SELECT balance ...
    // Tính newBalance trong Java ...
    // UPDATE account SET balance = ? WHERE id = ? ...
    connection.commit();
} catch (SQLException failure) {
    connection.rollback();
    throw failure;
}
```

Đoạn mã cho thấy ranh giới transaction; nó **chưa có cơ chế** kiểm tra xem giá trị đọc lúc đầu đã bị giao dịch khác sửa trước khi `UPDATE` hay chưa.

Nếu để `autoCommit=true`, mỗi statement lại có thể được commit độc lập; khoảng thời gian giữa hai statement càng không được bảo vệ bởi một transaction duy nhất. Dù vậy, **chỉ đổi sang `autoCommit=false` cũng không phải cách sửa đầy đủ**.

### Phân biệt lost update với các hiện tượng cô lập khác

| Hiện tượng | Dấu hiệu nhận biết | Điểm khác lost update |
| --- | --- | --- |
| **Lost update** | Hai luồng cùng đọc dữ liệu cũ rồi ghi giá trị mới; một cập nhật bị ghi đè | Thay đổi đã ghi của một luồng không còn trong kết quả cuối |
| Dirty read | Đọc được dữ liệu chưa commit của transaction khác | Vấn đề là đọc dữ liệu chưa được xác nhận |
| Non-repeatable read | Đọc cùng một hàng hai lần trong một transaction được hai kết quả khác nhau | Chỉ sự thay đổi khi đọc lại; chưa nhất thiết có ghi đè |
| Phantom read | Cùng điều kiện truy vấn nhưng tập hàng thay đổi giữa các lần đọc | Ảnh hưởng đến tập hàng thỏa điều kiện, không chỉ một giá trị cũ |
| Write skew | Hai transaction đọc các dữ kiện liên quan rồi cập nhật **các hàng khác nhau**, làm sai bất biến chung | Không nhất thiết ghi đè cùng một hàng |

Lost update thường được phát hiện qua **số liệu tổng cuối không khớp với chuỗi thao tác đã thành công**, hoặc qua nhật ký nhiều giao dịch đọc cùng phiên bản rồi cập nhật hàng đó.

## 3. JDBC isolation level giúp đến đâu?

JDBC cung cấp các hằng mức cô lập qua `Connection.setTransactionIsolation(...)`:

| Mức cô lập JDBC | Nhận định liên quan đến lost update |
| --- | --- |
| `TRANSACTION_READ_UNCOMMITTED` | Không thể trông đợi tránh lost update; khả năng hỗ trợ/diễn giải còn tùy DB |
| `TRANSACTION_READ_COMMITTED` | Có thể vẫn gặp đọc cũ – ghi đè khi ứng dụng tự tính giá trị; khóa ghi tự động không nhất thiết bảo vệ `SELECT` trước đó |
| `TRANSACTION_REPEATABLE_READ` | Có thể hạn chế một số kiểu xung đột; một số DB chặn hoặc báo lỗi giao dịch ghi dựa trên snapshot cũ, nhưng hành vi không đồng nhất |
| `TRANSACTION_SERIALIZABLE` | Hướng tới kết quả tương đương một thứ tự giao dịch tuần tự; DB có thể chặn hoặc hủy một transaction và yêu cầu thử lại |

Không nên viết quy tắc cố định như **“REPEATABLE_READ luôn ngăn lost update”** hoặc **“SERIALIZABLE khiến mọi truy vấn chạy thành công ngay lần đầu”**. Driver, engine, MVCC/locking, điều kiện câu SQL và cơ chế phát hiện xung đột quyết định kết quả thực tế.

Kiểm tra mức cô lập:

```java
int isolation = connection.getTransactionIsolation();
System.out.println("Isolation code: " + isolation);

DatabaseMetaData metadata = connection.getMetaData();
boolean supported = metadata.supportsTransactionIsolationLevel(
        Connection.TRANSACTION_SERIALIZABLE);
System.out.println("Serializable supported: " + supported);
```

`getTransactionIsolation()` cho biết mức cấu hình hiện tại; `supportsTransactionIsolationLevel(...)` cho biết driver báo khả năng hỗ trợ mức được hỏi. **Không có phương thức metadata tổng quát nào chứng minh một chuỗi đọc – sửa – ghi cụ thể chắc chắn không bị mất cập nhật.** Phải thử trên DB thực tế.

Khi cần đổi mức cô lập, cấu hình **trước khi bắt đầu transaction**, đồng thời khôi phục theo chính sách của `DataSource`/pool sau khi giao dịch kết thúc. Không tùy tiện thay đổi thuộc tính kết nối khi đã tham gia transaction do framework quản lý.

## 4. Cách 1 — Cập nhật tương đối trực tiếp bằng SQL

Khi nghiệp vụ có thể biểu đạt bằng **một câu SQL**, cách đơn giản và thường hiệu quả nhất là để DB tính từ giá trị hiện hành:

```sql
-- Dễ mất cập nhật khi newBalance được tính từ lần SELECT cũ:
UPDATE account SET balance = ? WHERE id = ?;

-- Cách an toàn hơn cho thao tác cộng số dư:
UPDATE account SET balance = balance + ? WHERE id = ?;

-- Rút tiền và kiểm tra số dư trong chính câu UPDATE:
UPDATE account
SET balance = balance - ?
WHERE id = ? AND balance >= ?;
```

Ở câu lệnh cuối, phép trừ và điều kiện `balance >= ?` được DB xử lý như một thao tác cập nhật có điều kiện trên hàng. Hai yêu cầu đồng thời không tự gửi hai giá trị tuyệt đối được tính từ cùng một bản đọc cũ. DB thường điều phối cập nhật hàng và khóa ghi hoặc báo lỗi xung đột theo mức cô lập.

### Ví dụ JDBC: rút tiền không cần đọc số dư rồi ghi lại

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AtomicDebitRepository {
    private final DataSource dataSource;

    public AtomicDebitRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean debit(long accountId, BigDecimal amount)
            throws SQLException {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        BigDecimal checked = amount.setScale(
                2, RoundingMode.UNNECESSARY);

        String sql = """
                UPDATE account
                SET balance = balance - ?, version = version + 1
                WHERE id = ? AND balance >= ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, checked);
            ps.setLong(2, accountId);
            ps.setBigDecimal(3, checked);

            int rows = ps.executeUpdate();
            if (rows == 1) {
                return true;
            }
            if (rows == 0) {
                // Tài khoản không tồn tại hoặc số dư không đủ.
                return false;
            }
            throw new SQLException(
                    "Khóa chính id phải giới hạn UPDATE tối đa một hàng");
        }
    }
}
```

Ví dụ giả định `DataSource` cung cấp kết nối ở chế độ `autoCommit=true` và thao tác rút chỉ gồm **một câu `UPDATE`**. `balance` dùng `DECIMAL(18,2)` và phía Java dùng `BigDecimal` để tránh sai số dấu phẩy động. Việc tăng `version` đồng thời bảo đảm các luồng dùng optimistic locking ở phần sau nhận ra thay đổi.

Nếu thao tác còn phải ghi sổ cái, log giao dịch hoặc thay đổi nhiều bảng, cần đưa **tất cả bước ghi** vào một transaction duy nhất; không thể chỉ dựa vào câu `UPDATE` riêng lẻ để bảo đảm tính nguyên tử của toàn bộ nghiệp vụ. Khi DB báo lỗi deadlock hoặc serialization, ứng dụng phải xử lý theo chính sách retry phù hợp.

## 5. Cách 2 — Optimistic locking bằng cột phiên bản

Đọc – sửa – ghi có thể cần thiết khi phép tính nghiệp vụ phức tạp và phải chạy ở Java. Khi đó, **optimistic locking** phát hiện bản ghi đã đổi kể từ lần đọc bằng điều kiện `WHERE version = ?`.

Quy trình:

1. `SELECT balance, version FROM account WHERE id = ?`.
2. Tính giá trị mới từ `balance` đã đọc.
3. `UPDATE account SET balance = ?, version = version + 1 WHERE id = ? AND version = ?`.
4. Nếu `executeUpdate()` trả **1**, thay đổi được áp dụng. Nếu trả **0**, hàng đã bị cập nhật hoặc không còn tồn tại: không được giả định bản tính cũ vẫn hợp lệ.

Ví dụ, cả A và B đều đọc `version=7`. A cập nhật trước và nâng lên `version=8`. B thử `WHERE version=7` sẽ không còn khớp; ứng dụng có thể báo xung đột và yêu cầu chạy lại từ dữ liệu mới.

### Ví dụ JDBC: phát hiện xung đột trước khi ghi đè

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ConcurrentModificationException;
import javax.sql.DataSource;

public final class VersionedAccountRepository {
    private final DataSource dataSource;

    public VersionedAccountRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public BigDecimal debit(long id, BigDecimal amount) throws SQLException {
        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        BigDecimal checked =
                amount.setScale(2, RoundingMode.UNNECESSARY);

        try (Connection connection = dataSource.getConnection()) {
            // Ví dụ một thao tác đọc rồi cập nhật một hàng:
            // tính đúng đắn dựa vào điều kiện version trong UPDATE.
            BigDecimal currentBalance;
            long currentVersion;

            String selectSql =
                    "SELECT balance, version FROM account WHERE id = ?";
            try (PreparedStatement ps =
                    connection.prepareStatement(selectSql)) {
                ps.setLong(1, id);
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Không tìm thấy tài khoản");
                    }
                    currentBalance = rs.getBigDecimal("balance");
                    currentVersion = rs.getLong("version");
                }
            }

            BigDecimal newBalance = currentBalance.subtract(checked);
            if (newBalance.signum() < 0) {
                throw new IllegalStateException("Số dư không đủ");
            }

            String updateSql = """
                    UPDATE account
                    SET balance = ?, version = version + 1
                    WHERE id = ? AND version = ?
                    """;
            try (PreparedStatement ps =
                    connection.prepareStatement(updateSql)) {
                ps.setBigDecimal(1, newBalance);
                ps.setLong(2, id);
                ps.setLong(3, currentVersion);

                int rows = ps.executeUpdate();
                if (rows == 0) {
                    throw new ConcurrentModificationException(
                            "Tài khoản đã thay đổi; tải lại rồi tính tiếp");
                }
                if (rows != 1) {
                    throw new SQLException("UPDATE ảnh hưởng quá một hàng");
                }
                return newBalance;
            }
        }
    }
}
```

Trong ví dụ, kết nối phải sử dụng `autoCommit=true` và chỉ có một câu cập nhật; **điều kiện `version` trong `UPDATE`** mới là cơ chế phát hiện xung đột. Nếu hệ thống dùng transaction thủ công hoặc framework, hãy để tầng sở hữu transaction quyết định `commit`/`rollback`. Nếu cần thêm những câu ghi khác, đặt chúng trong cùng transaction và kiểm tra xung đột **trước commit**.

Để optimistic locking có hiệu lực, **mọi đường cập nhật cùng hàng** phải cùng quy ước tăng `version`, bao gồm cập nhật bằng SQL thủ công, batch, job nền hoặc một lớp persistence khác. Nếu một đường ghi thay đổi `balance` nhưng không tăng `version`, giao dịch đọc bản cũ có thể không phát hiện được thay đổi ấy.

Trả về `rows=0` không tự chứng minh lỗi nào đã xảy ra: có thể một transaction khác đã cập nhật hàng, hoặc hàng bị xóa. Sau xung đột, chỉ thử lại bằng cách **đọc giá trị/phiên bản mới và tính lại toàn bộ nghiệp vụ**, có giới hạn số lần và chính sách xử lý xung đột rõ ràng. Không chạy lại nguyên `UPDATE` với cùng `newBalance` cũ.

## 6. Cách 3 — Pessimistic locking bằng khóa hàng

Khi cần chắc chắn không có giao dịch khác thay đổi hàng giữa **đọc và sửa**, có thể dùng **khóa bi quan** (*pessimistic lock*). Nhiều DB hỗ trợ cú pháp `SELECT ... FOR UPDATE` để khóa những hàng được chọn cho đến khi transaction kết thúc.

```sql
SELECT balance
FROM account
WHERE id = ?
FOR UPDATE;
```

Một transaction khác muốn cập nhật cùng hàng thường phải chờ hoặc bị báo lỗi theo chính sách khóa và timeout. Sau khi transaction đầu `commit`/`rollback`, khóa được giải phóng. Cú pháp và thời điểm lấy khóa là **phụ thuộc hệ quản trị**: SQL Server thường dùng lock hint khác, và một số engine/kiểu bảng không hỗ trợ cùng ngữ nghĩa.

### Mẫu điều phối transaction

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public void debitWithLock(DataSource dataSource, long id, BigDecimal amount)
        throws SQLException {
    if (amount == null || amount.signum() <= 0) {
        throw new IllegalArgumentException("Số tiền phải dương");
    }
    BigDecimal checked = amount.setScale(2, RoundingMode.UNNECESSARY);

    try (Connection connection = dataSource.getConnection()) {
        if (!connection.getAutoCommit()) {
            throw new SQLException(
                    "Ví dụ yêu cầu kết nối mới ở autoCommit=true");
        }
        connection.setAutoCommit(false);
        boolean transactionEnded = false;

        try {
            BigDecimal balance;
            try (PreparedStatement ps = connection.prepareStatement(
                    "SELECT balance FROM account WHERE id = ? FOR UPDATE")) {
                ps.setLong(1, id);
                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        throw new SQLException("Không tìm thấy tài khoản");
                    }
                    balance = rs.getBigDecimal(1);
                }
            }

            BigDecimal newBalance = balance.subtract(checked);
            if (newBalance.signum() < 0) {
                throw new IllegalStateException("Số dư không đủ");
            }

            try (PreparedStatement ps = connection.prepareStatement(
                    """
                    UPDATE account
                    SET balance = ?, version = version + 1
                    WHERE id = ?
                    """)) {
                ps.setBigDecimal(1, newBalance);
                ps.setLong(2, id);
                if (ps.executeUpdate() != 1) {
                    throw new SQLException("Không cập nhật đúng một tài khoản");
                }
            }

            connection.commit();
            transactionEnded = true;
        } catch (SQLException | RuntimeException failure) {
            if (!transactionEnded) {
                try {
                    connection.rollback();
                    transactionEnded = true;
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
            }
            throw failure;
        } finally {
            if (transactionEnded) {
                connection.setAutoCommit(true);
            }
            // Nếu rollback thất bại, trạng thái kết nối có thể không xác định:
            // không bật autoCommit vì việc đổi cờ có thể commit ngoài ý muốn.
        }
    }
}
```

Đây là **mẫu phương thức** đặt trong một lớp Java. Ví dụ kiểm tra `amount` khác null, dương và có đúng hai chữ số thập phân trước khi truy cập DB; ứng dụng thực tế cần chọn quy tắc làm tròn theo nghiệp vụ và xử lý lỗi khôi phục cấu hình của connection pool. Mẫu dùng `try-with-resources` để đóng tài nguyên, `rollback()` nếu thất bại, và chỉ khôi phục `autoCommit` khi transaction đã kết thúc. Nếu `commit()` thất bại do mất kết nối, kết quả commit có thể **chưa xác định**; không tự động chạy lại nghiệp vụ không có cơ chế chống thực thi trùng.

**Những điểm cần cân nhắc:** khóa hàng giữ lâu sẽ làm giảm thông lượng; hai giao dịch khóa nhiều hàng theo thứ tự khác nhau có thể bị deadlock; cần đặt timeout phù hợp và luôn giải phóng transaction sớm. Không sử dụng `SELECT ... FOR UPDATE` với `autoCommit=true` nếu mục tiêu là giữ khóa qua câu `UPDATE` tiếp theo, vì khóa có thể được giải phóng ngay khi statement đầu kết thúc.

## 7. Chọn giải pháp nào?

| Nhu cầu | Phương án phù hợp | Điều cần lưu ý |
| --- | --- | --- |
| Cộng/trừ một giá trị, có điều kiện đơn giản | `UPDATE col = col + ?` hoặc `UPDATE ... WHERE ...` | Thao tác phải thực hiện nguyên tử trong DB |
| Đọc dữ liệu rồi tính phức tạp trong Java | Optimistic locking với `version` | Có xung đột thì tính lại từ dữ liệu mới |
| Phải giữ bản ghi không đổi xuyên suốt nhiều bước đọc/ghi | `SELECT ... FOR UPDATE` trong transaction | Khóa, chờ, timeout, deadlock và cú pháp DB |
| Nhiều điều kiện và bất biến liên quan đến nhiều hàng/bảng | Transaction, khóa phù hợp hoặc isolation mạnh hơn | Kiểm chứng tính tuần tự và chính sách retry |
| Ghi đồng thời thường xuyên lên cùng một hàng | Ưu tiên SQL atomic hoặc cân nhắc khóa bi quan | Optimistic locking có thể xung đột nhiều |
| Ghi ít, chủ yếu đọc | Optimistic locking có thể giảm thời gian giữ khóa | Mọi đường ghi phải cập nhật version |

Các phương án có thể kết hợp. Ví dụ, vừa dùng `UPDATE ... SET balance = balance - ? WHERE balance >= ?` vừa tăng `version` sẽ bảo vệ thao tác hiện tại và cho phép luồng khác nhận diện bản đọc đã cũ. Để kiểm tra số dư không âm, nên bổ sung ràng buộc DB `CHECK(balance >= 0)` khi hệ quản trị hỗ trợ đầy đủ.

## 8. Xử lý xung đột, deadlock và retry

Một giao dịch không thể ngăn lost update bằng cách **nuốt lỗi rồi báo thành công**. Khi gặp các loại lỗi dưới đây, ứng dụng cần quyết định rõ có thể thử lại hay không:

- **Optimistic conflict:** `UPDATE ... WHERE version = ?` trả 0 hàng. Tải lại bản mới, tính lại nghiệp vụ và thử lại có giới hạn hoặc trả xung đột cho người gọi.
- **Deadlock:** DB hủy một transaction để phá vòng chờ khóa. Thường cần rollback rồi chạy lại **toàn bộ transaction** nếu nghiệp vụ cho phép.
- **Serialization failure:** Transaction bị hủy vì không thể bảo đảm mức cô lập yêu cầu. Thường retry lại toàn bộ đơn vị công việc với dữ liệu mới.
- **Commit outcome unknown:** Mất kết nối khi commit có thể khiến ứng dụng không biết giao dịch đã commit chưa. Không chạy lại lệnh chuyển tiền hoặc tạo đơn ngay nếu thiếu **idempotency key**, tra cứu trạng thái hoặc cơ chế chống trùng.

Không nên giả định mọi DB dùng cùng mã lỗi SQLState/vendor code. JDBC có `SQLException.getSQLState()`, `getErrorCode()` và các lớp như `SQLTransactionRollbackException`, nhưng chính sách retry nên dựa trên tài liệu của DB/driver đang dùng.

Nếu áp dụng retry, hãy **giới hạn số lần**, thêm độ trễ phù hợp khi xung đột liên tục và bảo đảm không lặp lại các tác dụng phụ bên ngoài DB (gửi email, gọi cổng thanh toán). Nhiều bước ghi liên quan phải cùng transaction; chỉ `commit` khi tất cả bước hợp lệ.

## 9. Thực hành phát hiện lost update bằng hai kết nối JDBC

Để quan sát lỗi một cách có kiểm soát, chuẩn bị bảng `account` và một bản ghi thử nghiệm có `balance=100000.00`. Dùng **hai kết nối độc lập** từ `DataSource` để mô phỏng hai request; không dùng chung một `Connection` cho hai luồng.

1. Chọn DB và ghi lại driver, isolation hiện tại qua `connection.getTransactionIsolation()`. Đặt `autoCommit=false` cho hai kết nối và cấu hình isolation trước khi mở giao dịch.
2. Trên kết nối A, `SELECT balance`; giữ giá trị đọc được trong Java.
3. Trên kết nối B, `SELECT balance` cùng tài khoản; hai kết nối có thể cùng đọc `100000.00`.
4. Trên A, tính và `UPDATE ... SET balance = 90000.00` rồi commit.
5. Trên B, dùng **giá trị cũ đã tính** để `UPDATE ... SET balance = 80000.00` rồi commit. Ghi nhận DB cho phép, bắt chờ hay báo lỗi xung đột.
6. Đọc số dư cuối. Nếu cả hai thao tác được chấp nhận và kết quả là `80000.00`, đã tái hiện lost update; kết quả đúng về nghiệp vụ phải là `70000.00`.
7. Khởi tạo lại dữ liệu và lặp bài thử với `UPDATE balance = balance - ?`, sau đó với `WHERE version = ?` hoặc `SELECT ... FOR UPDATE`. So sánh số dư, update count và lỗi phát sinh.

Không thử lịch cập nhật mất dữ liệu trên tài khoản thật hoặc bảng production. Để chủ động xen kẽ trong chương trình kiểm thử, dùng hai luồng với các điểm đồng bộ như `CountDownLatch` tại **sau hai lần `SELECT` và trước các lần `UPDATE`**; luôn đặt timeout tránh chờ vô hạn. Không dùng thời gian ngủ ngẫu nhiên để “chứng minh” chương trình không có race condition.

### Những câu hỏi tự kiểm tra

- Vì sao hai `SELECT` đều trả về `100000.00` rồi hai lệnh `UPDATE` đều thành công vẫn có thể dẫn tới dữ liệu sai?
- Khi đổi `autoCommit=true` thành `false`, phần nào của luồng đọc – sửa – ghi vẫn chưa được bảo vệ?
- `UPDATE balance = balance - ?` khác gì `UPDATE balance = ?` khi hai request đồng thời?
- Vì sao `executeUpdate()==0` trong optimistic locking là tín hiệu xung đột cần xử lý, chứ không phải lỗi được phép bỏ qua?
- Nếu `SELECT ... FOR UPDATE` chờ quá lâu hoặc deadlock, ứng dụng nên xử lý transaction ra sao?
- Tại sao một retry sau lỗi commit cần cơ chế chống thực thi trùng?

**Ghi nhớ:** Lost update xuất hiện khi kết quả **đọc – tính – ghi** của một transaction được xây trên dữ liệu đã cũ và ghi đè cập nhật của transaction khác. Trong JDBC, hãy ưu tiên **`UPDATE` nguyên tử** khi phép tính đơn giản; dùng **cột `version`** để phát hiện xung đột khi cần tính ở Java; dùng **khóa hàng trong transaction** khi cần ngăn thay đổi giữa đọc và ghi. Isolation level ảnh hưởng hành vi đồng thời nhưng không thay thế việc thiết kế đúng câu SQL và kiểm tra trên DB/driver thực tế.

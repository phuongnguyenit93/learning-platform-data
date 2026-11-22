# Phân biệt DAO, Repository và lớp dịch vụ nghiệp vụ

## 1. Ba khái niệm cùng tham gia truy cập dữ liệu, nhưng không cùng trách nhiệm

Trong ứng dụng Java dùng **JDBC**, một yêu cầu nghiệp vụ có thể cần đọc nhiều bảng, cập nhật nhiều hàng và hoàn thành trong một transaction. Nếu đặt toàn bộ câu SQL, vòng lặp `ResultSet`, kiểm tra nghiệp vụ và `commit()` vào controller, code sẽ khó kiểm thử, khó tái sử dụng và dễ sai ranh giới giao dịch.

Ba khái niệm thường dùng để tổ chức mã:

- **DAO (*Data Access Object*)**: tập trung vào **cách** dữ liệu được đọc/ghi từ nguồn lưu trữ, chẳng hạn SQL, `PreparedStatement`, `ResultSet` và ánh xạ hàng.
- **Repository**: cung cấp một **giao diện theo ngôn ngữ miền nghiệp vụ** để truy xuất và lưu các đối tượng/aggregate; phần dùng JDBC có thể **ủy quyền cho DAO** hoặc tự thực thi truy vấn.
- **Lớp dịch vụ nghiệp vụ (*service*)**: điều phối **việc cần làm** cho một use case, kiểm tra điều kiện nghiệp vụ, phối hợp repository và xác định ranh giới transaction.

Ví dụ use case chuyển 25.00 từ tài khoản A sang B:

```text
HTTP Controller
    |
    v
TransferService.transfer(A, B, 25.00)  <- use case, quy tắc nghiệp vụ
    |
    v
TransactionRunner / Unit of Work       <- một Connection, commit/rollback
    |
    v
AccountRepository                      <- ngôn ngữ miền: debit, credit
    |
    v
JdbcAccountRepository + AccountDao     <- SQL, parameter binding, row mapping
    |
    v
DataSource -> Connection -> Database
```

**Đây là một cách tổ chức có chủ đích, không phải quy tắc buộc mọi dự án phải có đủ ba lớp riêng.** Ứng dụng CRUD nhỏ hoàn toàn có thể dùng DAO cùng service; ở nhiều dự án, lớp `JdbcAccountRepository` **chính là DAO theo nghĩa rộng**. Giá trị của việc tách lớp nằm ở **ranh giới trách nhiệm**, không ở số lượng interface/class.

## 2. So sánh nhanh

| Tiêu chí | DAO | Repository | Service nghiệp vụ |
| --- | --- | --- | --- |
| Câu hỏi trả lời | “Đọc/ghi dữ liệu bằng kỹ thuật nào?” | “Tìm/lưu đối tượng nghiệp vụ nào?” | “Use case này phải làm những bước gì?” |
| Ngôn ngữ API thường dùng | `selectById`, `insertRow`, `updateBalance` | `findAccountById`, `debitIfEnough`, `save` | `transferMoney`, `placeOrder`, `reserveStock` |
| Phụ thuộc JDBC | Thường **có** | Interface có thể **không**; adapter JDBC thì có | Nên được che bởi transaction abstraction khi cần |
| Mối quan tâm chính | SQL, binding, mapping, số dòng cập nhật | Identity, truy xuất theo nhu cầu domain, aggregate | Quy tắc và thứ tự thao tác, kết quả, transaction |
| Có quản lý transaction không? | Thường **không sở hữu** transaction nhiều bước | Thường **tham gia** transaction do tầng trên điều phối | Xác định ranh giới nghiệp vụ cần nguyên tử |
| Kiểm thử phù hợp | Integration test với DBMS/driver thật | Contract test, test adapter và mapping | Unit test theo use case; thêm integration test transaction |
| Lỗi dễ mắc | Nhúng quy tắc nghiệp vụ trong mapper/SQL tùy tiện | Biến thành lớp chuyển tiếp không có giá trị | Viết SQL trực tiếp hoặc gọi nhiều DAO mỗi cái tự commit |

Định nghĩa này là **quy ước kiến trúc hữu ích**, không phải phân cấp class của JDBC: thư viện chuẩn `java.sql` không có interface `Dao`, `Repository` hay `BusinessService`. JDBC cung cấp `DataSource`, `Connection`, `PreparedStatement`, `ResultSet` và các API giao dịch; ứng dụng tự định nghĩa các lớp còn lại.

## 3. DAO: đặt SQL và ánh xạ dữ liệu sát nguồn lưu trữ

DAO nên gom các chi tiết hạ tầng không đáng để tầng nghiệp vụ biết:

1. Câu SQL và tên bảng/cột.
2. Gán tham số qua `PreparedStatement.setXxx(...)`, không nối dữ liệu đầu vào thành SQL.
3. Đọc `ResultSet.getXxx(...)`, xử lý SQL `NULL` và chuyển kiểu (`DECIMAL` sang `BigDecimal`, chẳng hạn).
4. Kiểm tra `executeUpdate()` đã ảnh hưởng số hàng dự kiến.
5. Đóng `PreparedStatement`/`ResultSet` đúng lúc và báo lỗi `SQLException` có ngữ cảnh.

Ví dụ DAO đọc một tài khoản:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;

public final class AccountDao {
    public Optional<Account> findById(
            Connection connection, long accountId) throws SQLException {
        String sql = """
                SELECT account_id, balance
                FROM accounts
                WHERE account_id = ?
                """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setLong(1, accountId);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return Optional.empty();
                }
                return Optional.of(new Account(
                        rs.getLong("account_id"),
                        rs.getBigDecimal("balance")));
            }
        }
    }

    public int debitIfEnough(
            Connection connection, long accountId, BigDecimal amount)
            throws SQLException {
        String sql = """
                UPDATE accounts
                SET balance = balance - ?
                WHERE account_id = ? AND balance >= ?
                """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, accountId);
            ps.setBigDecimal(3, amount);
            return ps.executeUpdate();
        }
    }

    public int credit(
            Connection connection, long accountId, BigDecimal amount)
            throws SQLException {
        String sql = """
                UPDATE accounts
                SET balance = balance + ?
                WHERE account_id = ?
                """;

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setBigDecimal(1, amount);
            ps.setLong(2, accountId);
            return ps.executeUpdate();
        }
    }
}
```

Mã trên cố ý **nhận `Connection` từ bên ngoài**, thay vì tự gọi `dataSource.getConnection()` trong từng phương thức. Nhờ đó, tầng điều phối có thể dùng **cùng một connection** cho nhiều DAO call thuộc một transaction. DAO chỉ đóng các tài nguyên **do nó tạo ra** là `PreparedStatement` và `ResultSet`, **không đóng connection mà caller đang sở hữu**.

Kiểu `Account` sẽ được khai báo ở mục 8. DAO trả `Optional.empty()` khi không có hàng và `int` từ `executeUpdate()` để tầng trên phân biệt cập nhật thành công với “không có tài khoản hoặc không đủ tiền”.

**Không để DAO quyết định “nếu thiếu tiền thì gửi email từ chối”**: đó không phải nhiệm vụ truy cập dữ liệu. Ngược lại, việc kiểm tra điều kiện `balance >= ?` **trong câu UPDATE** là hợp lý để bảo vệ tính nguyên tử trước cập nhật đồng thời. Ranh giới giữa logic SQL bảo vệ dữ liệu và quy tắc nghiệp vụ được giải thích ở mục 11.

## 4. Repository: một góc nhìn theo mô hình miền nghiệp vụ

Repository thường dùng các tên và đối tượng phản ánh **domain**, không phải cấu trúc vật lý của database. Theo tinh thần Domain-Driven Design (DDD), nó có thể mang cảm giác thao tác trên một tập các aggregate: tìm, thêm, lưu, xóa đối tượng theo quy tắc đã xác định.

Ví dụ:

```java
import java.math.BigDecimal;
import java.sql.SQLException;
import java.util.Optional;

public interface AccountRepository {
    Optional<Account> findById(long id) throws SQLException;

    boolean debitIfEnough(long id, BigDecimal amount)
            throws SQLException;

    boolean credit(long id, BigDecimal amount)
            throws SQLException;
}
```

Trong ví dụ học JDBC này, `AccountRepository` giữ `throws SQLException` để người học thấy lỗi JDBC có thể đi qua tầng gọi. Trong thiết kế miền độc lập hạ tầng hơn, có thể thay bằng **ngoại lệ lưu trữ do ứng dụng định nghĩa**, bảo toàn nguyên nhân `SQLException` ở tầng adapter. Không nhất thiết để service/domain import `java.sql`.

Một hiện thực JDBC:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Optional;

public final class JdbcAccountRepository implements AccountRepository {
    private final Connection connection;
    private final AccountDao dao;

    public JdbcAccountRepository(
            Connection connection, AccountDao dao) {
        this.connection = connection;
        this.dao = dao;
    }

    @Override
    public Optional<Account> findById(long id) throws SQLException {
        return dao.findById(connection, id);
    }

    @Override
    public boolean debitIfEnough(long id, BigDecimal amount)
            throws SQLException {
        return dao.debitIfEnough(connection, id, amount) == 1;
    }

    @Override
    public boolean credit(long id, BigDecimal amount)
            throws SQLException {
        return dao.credit(connection, id, amount) == 1;
    }
}
```

Trong ví dụ này:

- **DAO** biết câu `UPDATE accounts SET balance ...` và cách đếm số hàng.
- **Repository** biết thao tác có ý nghĩa miền là **trừ tiền khi đủ số dư**; nó chuyển kết quả kỹ thuật `int` thành `boolean` cho use case.
- **Service** ở mục 8 quyết định khi nào trừ và cộng, có hủy toàn bộ nghiệp vụ nếu một bước thất bại hay không.

Repository **không nhất thiết** có một class DAO bên dưới. Với dự án nhỏ, hoàn toàn có thể viết SQL trực tiếp trong `JdbcAccountRepository` và bỏ `AccountDao` trung gian. Hãy tách khi điều đó thực sự giúp cô lập mapping/SQL, tái sử dụng hoặc kiểm thử.

### Repository khác “mỗi bảng một class CRUD”

Một aggregate `Order` có thể trải trên các bảng `orders`, `order_lines` và `order_addresses`. `OrderRepository.findById(orderId)` có thể lấy **toàn bộ aggregate** để bảo đảm quy tắc của đơn hàng, dù phía dưới cần nhiều câu SQL và nhiều row mapper.

Ngược lại, màn hình báo cáo doanh thu có thể chỉ cần projection `RevenueSummary` từ nhiều bảng. Không bắt buộc biến projection thành một aggregate hay nhét mọi câu thống kê vào repository domain. Một `ReportDao` hoặc **query service** chuyên đọc dữ liệu có thể rõ ràng hơn.

Không nên nhầm **Repository pattern** với việc dùng annotation `@Repository` của một framework, hoặc với interface repository tự sinh của một ORM. Những công nghệ đó có quy ước riêng; **JDBC thuần không yêu cầu framework** để áp dụng pattern.

## 5. Service: nơi điều phối một use case

Service nghiệp vụ (đặc biệt là **application service**) nên nhận một yêu cầu có ý nghĩa, xác thực các điều kiện ở cấp use case và điều phối những thao tác cần thực hiện.

Ví dụ `TransferService.transfer(source, destination, amount)`:

1. Kiểm tra hai tài khoản hợp lệ và khác nhau, số tiền dương đúng precision/scale.
2. Yêu cầu trừ tiền nguồn **nếu số dư đủ**.
3. Nếu trừ thành công, cộng đúng số tiền đó vào tài khoản đích.
4. Đảm bảo **cả hai cập nhật thành một đơn vị nguyên tử** hoặc đều không được lưu.
5. Chuyển kết quả thành mã nghiệp vụ hoặc ngoại lệ phù hợp.

**Service không nên phải biết** tên cột `balance`, vị trí tham số `?` hay cách gọi `ResultSet.next()`. Nếu cần transaction JDBC thủ công, có thể để một đối tượng `TransactionRunner` / *Unit of Work* thực hiện phần `Connection.commit/rollback` thay cho service.

Phân biệt thêm:

| Loại thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **Application service** | Điều phối use case, transaction, phối hợp repository và hệ thống khác | `TransferService.transfer(...)` |
| **Domain service** | Thể hiện một quy tắc miền không thuộc tự nhiên về một entity/aggregate đơn lẻ | `TransferFeePolicy.calculate(...)` |
| **Infrastructure service** | Cung cấp thao tác kỹ thuật như email, file, clock, event publisher | `SmtpNotificationSender` |

Không phải ứng dụng nào cũng cần ba loại service. Quy tắc tính phí chỉ là một phép tính thuần có thể nằm trong class domain; controller không nên kiêm luôn transaction service chỉ vì muốn giảm số lớp.

## 6. Quyền sở hữu `Connection` và ranh giới transaction

Đây là điểm quyết định cách tách DAO, Repository và Service trong **JDBC**.

**Thiết kế dễ sai:**

```java
// AccountDao mở Connection riêng trong mỗi phương thức:
accountDao.debit(sourceId, amount);  // autoCommit: đã commit
accountDao.credit(targetId, amount); // lỗi ở đây!
```

Nếu câu lệnh thứ nhất đã commit độc lập nhưng câu thứ hai thất bại, tiền đã bị trừ mà chưa được cộng. Việc từng DAO có `try-with-resources` không sửa được lỗi nguyên tử.

**Thiết kế phù hợp:**

```text
Một use case chuyển tiền
    -> mượn một Connection
    -> setAutoCommit(false)
    -> gọi DAO/Repository trừ tiền trên Connection đó
    -> gọi DAO/Repository cộng tiền trên Connection đó
    -> nếu cả hai thành công: COMMIT
    -> nếu lỗi trước COMMIT: cố ROLLBACK
    -> đóng statement/result set và trả Connection về pool
```

Ai **mở** connection thì cần xác định rõ ai **đóng** nó. Khi DAO nhận một connection do tầng trên cung cấp, DAO không tự `close()` connection. Khi một transaction scope đã kết thúc, repository buộc với connection đó **không nên được giữ lại để gọi trong request khác**.

Trong ứng dụng dùng transaction manager của framework, hãy để framework sở hữu ranh giới commit/rollback; đừng tự mở một connection mới trong repository rồi làm vỡ transaction mà framework đang quản lý.

## 7. Mô hình mẫu: dữ liệu tài khoản và nghiệp vụ chuyển tiền

Để thấy sự khác nhau rõ ràng, ta xây dựng một ví dụ JDBC độc lập với **PostgreSQL** và **Java 17+**. SQL dưới đây tương đối phổ biến trên DBMS quan hệ, nhưng cú pháp DDL/driver có thể cần điều chỉnh theo hệ quản trị.

### 7.1. Schema và dữ liệu thử

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance DECIMAL(18, 2) NOT NULL,
    CONSTRAINT ck_accounts_balance CHECK (balance >= 0)
);

INSERT INTO accounts (account_id, balance)
VALUES (1, 100.00), (2, 50.00);
```

Số dư ban đầu:

| Tài khoản | Số dư |
| --- | ---: |
| `1` | 100.00 |
| `2` | 50.00 |

Nếu chuyển `25.00` từ tài khoản 1 sang tài khoản 2 thành công, số dư lần lượt phải là **75.00** và **75.00**. Nếu tài khoản đích không tồn tại, phải rollback cả bước trừ tiền trước đó.

### 7.2. Domain model

File `Account.java`:

```java
import java.math.BigDecimal;

public record Account(long id, BigDecimal balance) {}
```

`Account` chỉ mô tả một giá trị miền đơn giản; nó **không tự biết** JDBC, `PreparedStatement` hay tên bảng. Trong hệ thống lớn hơn, đối tượng miền có thể có phương thức bảo vệ invariant, kiểu `Money` chứa đơn vị tiền tệ, version để optimistic locking và quy tắc điều chỉnh số dư cụ thể.

### 7.3. DAO và Repository

Dùng `AccountDao` ở mục 3 và `AccountRepository/JdbcAccountRepository` ở mục 4. Các phương thức DAO đều nhận một `Connection` từ caller, giúp service sử dụng chúng trong **một transaction**.

Các thao tác đã phân chia như sau:

| Phương thức | Lớp chịu trách nhiệm SQL | Lớp cung cấp API nghiệp vụ |
| --- | --- | --- |
| Đọc tài khoản | `AccountDao.findById(connection,id)` | `AccountRepository.findById(id)` |
| Trừ nếu đủ tiền | `AccountDao.debitIfEnough(connection,id,amount)` | `AccountRepository.debitIfEnough(id,amount)` |
| Cộng vào tài khoản | `AccountDao.credit(connection,id,amount)` | `AccountRepository.credit(id,amount)` |

Nội dung nghiệp vụ quan trọng ở đây là **kiểm tra số dòng**: `UPDATE ... WHERE balance >= ?` trả `1` nghĩa là cập nhật một tài khoản; trả `0` nghĩa là không tồn tại hoặc số dư không đủ. Không nên phân biệt hai nguyên nhân chỉ bằng `executeUpdate()` nếu SQL chưa cung cấp đủ thông tin; muốn báo lỗi chi tiết hơn thì cần truy vấn hoặc mô hình lỗi được thiết kế riêng.

## 8. Ví dụ hoàn chỉnh: service không tự viết SQL

Ta thêm một abstraction nhỏ để service có thể điều phối transaction **mà không tự gọi `Connection.commit()`**.

### 8.1. Giao diện chạy một use case trong transaction

File `AccountTransaction.java`:

```java
import java.sql.SQLException;

public interface AccountTransaction {
    @FunctionalInterface
    interface Work<T> {
        T apply(AccountRepository repository) throws SQLException;
    }

    <T> T run(Work<T> work) throws SQLException;
}
```

Hợp đồng này cung cấp `AccountRepository` **đã được gắn với connection của transaction hiện hành**. Trong use case phức tạp cần nhiều repository, có thể đổi tham số callback thành một `UnitOfWork` chứa `accounts()`, `orders()`, `reservations()`... — tất cả dùng cùng transaction.

### 8.2. Triển khai `AccountTransaction` bằng JDBC

File `JdbcAccountTransaction.java`:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class JdbcAccountTransaction implements AccountTransaction {
    private final DataSource dataSource;
    private final AccountDao dao = new AccountDao();

    public JdbcAccountTransaction(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public <T> T run(Work<T> work) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            boolean originalAutoCommit = connection.getAutoCommit();

            if (!originalAutoCommit) {
                throw new SQLException(
                        "Ví dụ yêu cầu Connection chưa có transaction");
            }
            connection.setAutoCommit(false);

            boolean commitInvoked = false;
            boolean transactionEnded = false;
            Throwable originalFailure = null;

            try {
                AccountRepository accounts =
                        new JdbcAccountRepository(connection, dao);
                T result = work.apply(accounts);

                // Đã bước vào commit: nếu không có phản hồi thì
                // KHÔNG tự khẳng định transaction trước đã rollback.
                commitInvoked = true;
                connection.commit();
                transactionEnded = true;
                return result;
            } catch (SQLException | RuntimeException | Error failure) {
                originalFailure = failure;

                if (!commitInvoked) {
                    try {
                        connection.rollback();
                        transactionEnded = true;
                    } catch (SQLException rollbackFailure) {
                        failure.addSuppressed(rollbackFailure);
                    }
                }
                throw failure;
            } finally {
                // Chỉ khôi phục autoCommit khi đã xác nhận
                // transaction kết thúc bằng commit/rollback.
                if (transactionEnded) {
                    try {
                        connection.setAutoCommit(originalAutoCommit);
                    } catch (SQLException resetFailure) {
                        if (originalFailure != null) {
                            originalFailure.addSuppressed(resetFailure);
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

Các điểm cần hiểu:

- `DataSource` thuộc vòng đời ứng dụng; transaction runner chỉ **mượn** `Connection`.
- `AccountRepository` được tạo **bên trong** transaction và chỉ dùng trong callback. DAO không mở thêm connection.
- Nếu service ném lỗi **trước khi gọi commit**, runner cố `rollback()`; nếu rollback thất bại, exception gốc mang thêm lỗi phụ qua `addSuppressed`.
- Nếu `commit()` được gọi rồi ném `SQLException`, kết quả có thể **chưa xác định**. Runner không được tự tuyên bố rollback đã thành công hoặc tự retry.
- `close()` trên handle được đảm bảo bởi `try-with-resources`, kể cả khi giao dịch lỗi. Với connection pool, việc connection vật lý bị loại bỏ khi lỗi nghiêm trọng còn phụ thuộc driver và pool.

**Ranh giới ví dụ:** Runner minh họa cách quản lý transaction trong JDBC thuần; nó chưa cung cấp chính sách hoàn chỉnh cho *commit outcome unknown*, connection eviction, timeout, nested transactions, savepoint và retry lũy đẳng. Nếu `commit()` đã thành công nhưng việc reset thuộc tính hoặc `close()` lỗi, caller có thể nhận `SQLException` dù dữ liệu đã commit. Production cần giữ thông tin **pha transaction** để tránh coi mọi ngoại lệ từ runner là “chưa ghi dữ liệu” và thử lại mù quáng.

### 8.3. Service nghiệp vụ

File `TransferService.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.SQLException;

public final class TransferService {
    private final AccountTransaction transaction;

    public TransferService(AccountTransaction transaction) {
        this.transaction = transaction;
    }

    public void transfer(
            long sourceId, long destinationId, BigDecimal rawAmount)
            throws SQLException {

        if (sourceId <= 0 || destinationId <= 0
                || sourceId == destinationId
                || rawAmount == null || rawAmount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Thông tin chuyển tiền không hợp lệ");
        }

        // Không dùng double cho tiền; yêu cầu đúng hai chữ số
        // thập phân và từ chối giá trị cần làm tròn.
        BigDecimal amount =
                rawAmount.setScale(2, RoundingMode.UNNECESSARY);

        transaction.run(accounts -> {
            if (!accounts.debitIfEnough(sourceId, amount)) {
                throw new IllegalStateException(
                        "Tài khoản nguồn không tồn tại hoặc không đủ tiền");
            }
            if (!accounts.credit(destinationId, amount)) {
                throw new IllegalStateException(
                        "Tài khoản đích không tồn tại");
            }
            return null;
        });
    }
}
```

Service biết **nghiệp vụ cần trừ trước, cộng sau và nguyên tử hóa cả hai**. Nó không biết SQL `UPDATE`, không tự đọc `ResultSet` và không có lời gọi `Connection.rollback()` vì phần đó đã được transaction runner xử lý.

Trong một hệ thống tài chính thực, cần thêm quy tắc đồng tiền, giới hạn số tiền, phân quyền, nhật ký giao dịch, chống gửi lặp bằng request ID, xử lý deadlock và đối soát khi commit chưa rõ. Ví dụ này **chỉ nhằm giải thích trách nhiệm giữa các lớp**, không nên dùng nguyên xi làm hệ thống chuyển tiền production.

### 8.4. Ghép các thành phần

```java
import java.math.BigDecimal;
import javax.sql.DataSource;

// Giả định dataSource đã kết nối PostgreSQL và schema được tạo.
AccountTransaction transaction =
        new JdbcAccountTransaction(dataSource);
TransferService service = new TransferService(transaction);

service.transfer(1L, 2L, new BigDecimal("25.00"));
// accounts(1) = 75.00; accounts(2) = 75.00.
```

Ví dụ trên thể hiện **dependency direction**: `TransferService` chỉ biết `AccountTransaction` và `AccountRepository` ở tầng hợp đồng; việc dùng `PostgreSQL`, `DataSource`, `Connection` và `PreparedStatement` nằm trong adapter JDBC.

## 9. Kịch bản lỗi và lý do transaction thuộc phạm vi service

| Kịch bản | Điều xảy ra | Kết quả kỳ vọng |
| --- | --- | --- |
| Chuyển `25.00` từ 1 sang 2 | Debit và credit đều ảnh hưởng một hàng | Commit cả hai, tổng tiền không đổi |
| Chuyển `200.00` khi nguồn có 100.00 | `debitIfEnough` trả `false` | Service báo lỗi, transaction rollback |
| Tài khoản đích không tồn tại | Debit thành công nhưng credit trả `false` | Rollback debit, không mất tiền |
| Câu `UPDATE` bị deadlock | DBMS/driver ném `SQLException` | Xử lý rollback theo DBMS; retry có điều kiện ở cấp use case |
| Mất mạng trong `commit()` | Java không nhận được xác nhận | Kết quả có thể UNKNOWN; không chạy lại một cách mù quáng |
| Hai yêu cầu chuyển ngược chiều đồng thời | Có thể tranh khóa/deadlock | Cần thứ tự khóa nhất quán và chính sách retry giới hạn |

**Không để DAO âm thầm commit từng bước.** Khi use case gồm nhiều repository — ví dụ trừ tồn kho, tạo đơn, ghi dấu yêu cầu — các repository phải cùng tham gia **một transaction scope**, không tự gọi `dataSource.getConnection()` ở mỗi hàm rồi commit độc lập.

Với transaction manual, `SQLException` có thể khiến kết nối vẫn sống nhưng transaction ở trạng thái lỗi. Việc tiếp tục chạy SQL trên transaction đó không an toàn; service/runner phải chủ động quyết định rollback. Và **rollback chỉ hoàn tác các thay đổi DB nằm trong transaction đó**: email, request HTTP hoặc thông báo đã gửi ra ngoài không tự quay ngược.

## 10. Chọn mức độ tách lớp theo độ phức tạp

Không nên biến “DAO → Repository → Service” thành ba lớp bắt buộc chỉ chuyển tiếp một hàm. Có ít nhất ba kiểu kiến trúc hợp lý:

### 10.1. Ứng dụng CRUD nhỏ

```text
Controller -> ProductService -> ProductDao -> JDBC
```

DAO nhận/giao DTO rõ ràng, service xác thực request và điều phối transaction nếu có. Không cần thêm `ProductRepository` chỉ để gọi lại `ProductDao.findById()` với cùng tên và cùng kiểu.

### 10.2. Ứng dụng cần mô hình miền độc lập hạ tầng

```text
Application Service -> OrderRepository (interface)
                            ^
                            |
                     JdbcOrderRepository
                            |
                     JDBC / Row Mapper
```

Repository interface có thể mô tả `findOrder`/`saveOrder` bằng đối tượng miền. Adapter JDBC tự quản lý cách ghép nhiều bảng hoặc dùng DAO phụ để đọc. Phù hợp khi nghiệp vụ có aggregate, kiểm thử bằng fake, hoặc cần thay thế storage adapter.

### 10.3. Hệ thống đọc báo cáo phức tạp

```text
ReportService -> RevenueQueryDao -> JDBC -> Projection
OrderService  -> OrderRepository -> JDBC -> Aggregate
```

Đọc báo cáo và ghi aggregate có thể có mô hình khác nhau (*CQRS-style separation*) mà không cần áp dụng đầy đủ CQRS. Tránh biến một repository thành “bộ sưu tập mọi câu SQL” cho cả domain lẫn báo cáo, khiến API dài và trách nhiệm thiếu rõ ràng.

**Quy tắc thiết kế:** tách lớp khi nó tạo một ranh giới có ý nghĩa: ngôn ngữ API, quyền sở hữu connection, chiến lược mapping, kiểm thử, giới hạn phụ thuộc hoặc tái sử dụng thực tế.

## 11. Quy tắc nghiệp vụ nằm ở đâu?

Một số điều kiện xuất hiện trong SQL nhưng vẫn phục vụ miền nghiệp vụ. Không nên hiểu máy móc rằng “mọi điều kiện `WHERE` thuộc DAO và không thể liên quan business”.

Ví dụ:

```sql
UPDATE accounts
SET balance = balance - ?
WHERE account_id = ?
  AND balance >= ?;
```

Điều kiện `balance >= ?` thể hiện invariant **không âm** ở mức cập nhật nguyên tử. Nếu service đọc số dư rồi mới quyết định ở Java:

```text
Transaction A: SELECT balance = 100.
Transaction B: SELECT balance = 100.
A trừ 80; B cũng trừ 80 dựa trên giá trị cũ.
=> Có thể sai nếu UPDATE không có cơ chế đồng bộ phù hợp.
```

Kiểm tra điều kiện ngay trong `UPDATE` và đọc `executeUpdate()` giúp tránh kiểu race condition đó trong nhiều DBMS quan hệ. Service vẫn chịu trách nhiệm **quyết định hành vi** khi cập nhật trả 0, chẳng hạn báo không đủ tiền và rollback toàn use case.

Có thể phân định:

- **Domain/service** xác định quy tắc: “không trừ vượt số dư”, “hai tài khoản khác nhau”, “phải tạo lịch sử nếu chuyển thành công”.
- **DAO/SQL** hiện thực một thao tác dữ liệu **an toàn dưới đồng thời** theo quy tắc đó: conditional update, unique constraint, optimistic locking, transaction/row lock phù hợp.
- **DB schema** có thể bảo vệ invariant nền tảng qua `CHECK`, `UNIQUE`, `FOREIGN KEY` để dữ liệu vẫn đúng ngay cả khi gọi qua đường mã khác.

Đây là **phòng vệ nhiều lớp**, không phải vi phạm kiến trúc.

## 12. DTO, row mapper, entity và aggregate khác nhau

Không phải mọi đối tượng Java trả từ `ResultSet` đều cần là entity hoặc aggregate:

| Loại đối tượng | Vai trò | Ví dụ |
| --- | --- | --- |
| **Row/DTO** | Hình dạng dữ liệu cần đọc/ghi hoặc trả API | `AccountRow(id,balance)`, `OrderSummaryDto` |
| **Domain entity** | Đối tượng có định danh và quy tắc riêng | `Account`, `Order` |
| **Value object** | Giá trị được định nghĩa qua thuộc tính, thường bất biến | `Money(currency, amount)` |
| **Aggregate** | Nhóm entity/value object có ranh giới invariant và giao dịch | `Order` cùng các dòng hàng |
| **Projection** | Kết quả đọc tổng hợp, có thể không trùng bảng gốc | `MonthlyRevenueReport` |

DAO có thể ánh xạ `ResultSet` thành row DTO rồi repository chuyển sang domain object, hoặc mapping trực tiếp nếu điều đó đơn giản và không làm rò rỉ thông tin hạ tầng. Không có quy tắc “mỗi bảng một entity” bắt buộc với JDBC.

Ví dụ đọc tổng doanh thu bằng một câu `SUM(...) GROUP BY ...` không cần dựng hàng trăm `Order` chỉ để cộng lại trong service. Một `RevenueQueryDao` có thể trả projection tổng hợp.

Nếu repository tải một aggregate qua nhiều bảng, cần tránh mô hình **N+1**: tải danh sách cha rồi chạy một `SELECT` riêng cho từng cha. Các chiến lược `JOIN`, truy vấn theo nhóm `WHERE id IN (...)` hoặc projection chuyên biệt có thể phù hợp hơn; hãy đo số query thay vì chỉ nhìn cấu trúc class.

## 13. Xử lý lỗi SQL và lỗi nghiệp vụ

`SQLException` chứa thông tin kỹ thuật như `SQLState`, vendor error code, chuỗi exception và cause. Trong kiến trúc nhiều lớp:

| Loại lỗi | Nơi phát sinh | Cách diễn đạt ở service/API |
| --- | --- | --- |
| Không tìm thấy bản ghi | DAO `SELECT` không có hàng | Repository trả `Optional.empty()`; service quyết định Not Found |
| Không đủ tiền | Conditional `UPDATE` ảnh hưởng 0 hàng | Service chuyển thành lỗi nghiệp vụ nếu đúng ngữ cảnh |
| Trùng khóa duy nhất | DBMS/DAO báo constraint violation | Repository/service xem đó là xung đột, hoặc đối chiếu idempotency key |
| Lỗi SQL syntax/schema | Driver ném `SQLException` | Lỗi hạ tầng; ghi log và sửa mã/schema |
| Deadlock/serialization | DBMS báo lỗi transaction | Retry **toàn transaction** khi an toàn, có giới hạn |
| Lỗi mạng khi commit | `commit()` không trả xác nhận | Outcome chưa rõ; không khẳng định rollback |

Đừng chuyển **mọi `SQLException` thành `IllegalArgumentException`** hoặc trả HTTP 400. Các lỗi thuộc hạ tầng, concurrency và dữ liệu đầu vào có bản chất khác nhau.

Trong dự án muốn domain độc lập SQL, có thể tạo `DataAccessException`/`PersistenceException` của ứng dụng ở adapter và giữ `SQLException` làm cause. Nhưng không nên che mất `SQLState`, mã driver và pha transaction khi cần xử lý lỗi có điều kiện.

### Idempotency khi use case ghi dữ liệu

Ví dụ chuyển tiền ở trên **không tự thử lại**. Nếu client có thể gửi lại request sau timeout, phải thiết kế **request ID duy nhất** lưu cùng transaction với các cập nhật và so sánh payload khi request ID đã tồn tại. Đặc biệt, khi `commit()` trả lỗi kết nối, không thể suy đã rollback từ việc đóng `Connection`. Service hoặc workflow đối soát phải phân biệt `COMMIT_CONFIRMED`, `ROLLBACK_CONFIRMED` và `UNKNOWN`.

Đây là trách nhiệm phối hợp của tầng use case, transaction scope và hạ tầng; không thể giải quyết chỉ bằng một DAO method `updateBalance(...)`.

## 14. Kiểm thử ở đúng ranh giới

Một ưu điểm thực tế của việc tách lớp là **chọn loại kiểm thử phù hợp**.

### 14.1. Unit test cho service

Vì `TransferService` chỉ phụ thuộc `AccountTransaction`, có thể tạo một triển khai giả chạy callback với repository giả:

```java
import java.math.BigDecimal;
import java.sql.SQLException;
import java.util.Optional;

public final class FakeAccountRepository implements AccountRepository {
    private final java.util.Map<Long, BigDecimal> balances =
            new java.util.HashMap<>();

    public FakeAccountRepository add(long id, String amount) {
        balances.put(id, new BigDecimal(amount));
        return this;
    }

    @Override
    public Optional<Account> findById(long id) {
        BigDecimal balance = balances.get(id);
        return balance == null
                ? Optional.empty()
                : Optional.of(new Account(id, balance));
    }

    @Override
    public boolean debitIfEnough(long id, BigDecimal amount) {
        BigDecimal old = balances.get(id);
        if (old == null || old.compareTo(amount) < 0) {
            return false;
        }
        balances.put(id, old.subtract(amount));
        return true;
    }

    @Override
    public boolean credit(long id, BigDecimal amount) {
        BigDecimal old = balances.get(id);
        if (old == null) {
            return false;
        }
        balances.put(id, old.add(amount));
        return true;
    }
}
```

Fake này giúp kiểm tra logic **thứ tự gọi, kiểm tra số tiền và thông báo lỗi** mà không cần DBMS. Nhưng nó **không tự mô phỏng rollback**, vì thay đổi đã ghi trực tiếp vào map. Để kiểm thử trường hợp “credit thất bại làm debit được hoàn tác”, `FakeAccountTransaction` phải chụp snapshot map và khôi phục khi callback ném lỗi, hoặc cần **integration test với JDBC thật**.

Không nên coi unit test với fake là bằng chứng các câu `UPDATE` chạy đúng dưới đồng thời hoặc transaction đã rollback chính xác.

### 14.2. Integration test cho DAO/Repository và transaction

Trên PostgreSQL test database với schema mục 7, xác minh:

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| `findById(1)` | Đúng `Account` và `BigDecimal` |
| `findById(999)` | `Optional.empty()` |
| Debit đủ tiền | `executeUpdate()` ảnh hưởng một hàng |
| Debit vượt số dư | Trả `false`, số dư không âm |
| Credit tới tài khoản không tồn tại | Trả `false`, transaction có thể rollback |
| Transfer 25.00 | Số dư 75.00 / 75.00 |
| Transfer tới tài khoản không tồn tại | Sau rollback, số dư nguồn giữ nguyên |
| Hai transfer đồng thời | Không xuất hiện số dư âm; xử lý lock/deadlock theo DBMS |
| Lỗi sau `commit()` | Không retry tự động khi outcome chưa rõ |
| DAO đóng statement | Connection vẫn có thể dùng cho bước tiếp trong cùng transaction |
| Service qua transaction runner | Không mở thêm connection riêng cho từng DAO method |

Với kiểm thử đồng thời, dùng **hai `Connection` độc lập**, barrier/`CountDownLatch` và kiểm tra dữ liệu sau commit bằng kết nối thứ ba. Tránh dùng mỗi `Thread.sleep` rồi suy đoán transaction nào đang giữ lock.

## 15. Anti-pattern và cách sửa

| Anti-pattern | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Controller chạy SQL và gọi `commit` trực tiếp | Trộn HTTP, nghiệp vụ và hạ tầng | Dời use case vào service, SQL vào DAO/adapter |
| Mỗi DAO method tự mở/commit/đóng connection | Không đảm bảo nguyên tử cho nghiệp vụ nhiều bước | Transaction runner/service sở hữu một scope chung |
| Service duyệt `ResultSet` và biết tên cột SQL | Phụ thuộc schema/driver | Mapper/DAO chuyển dữ liệu trước khi trả |
| Repository chỉ gọi lại mọi method DAO mà không tạo abstraction | Tăng class và chỗ sửa, không thêm giá trị | Hợp nhất lớp hoặc định nghĩa API domain thực sự |
| Repository chứa quy tắc gửi email, kiểm tra HTTP role | Lẫn nghiệp vụ bên ngoài vào lưu trữ | Service điều phối, port cho external integration |
| DAO âm thầm rollback transaction do caller sở hữu | Có thể hoàn tác cả các bước khác | DAO ném lỗi; tầng quản lý transaction quyết định rollback |
| Service đọc balance rồi ghi giá trị tuyệt đối thiếu khóa | Lost update/race condition | Conditional UPDATE/locking/optimistic version |
| `SELECT *` trong mọi DAO | Đọc dư dữ liệu, phụ thuộc schema | Chọn cột cần và projection phù hợp |
| Danh sách cha rồi truy vấn con từng hàng | N+1, tăng round-trip | JOIN/batch fetch hoặc query projection |
| Bắt mọi `SQLException` rồi retry từng DAO call | Lặp tác dụng phụ, bỏ ranh giới transaction | Retry nguyên use case khi an toàn và lũy đẳng |
| Giữ `ResultSet/Connection` ngoài scope | Leak kết nối, cursor hết hạn | Materialize DTO trong scope và đóng tài nguyên |

## 16. Checklist thiết kế DAO–Repository–Service

Trước khi triển khai một chức năng JDBC mới:

1. **Mô tả use case trước:** cần đọc/ghi gì, quy tắc nào, những thao tác nào phải nguyên tử?
2. **Xác định hợp đồng dữ liệu:** DTO, aggregate hoặc projection nào cần trả?
3. **Đặt SQL và row mapping ở lớp hạ tầng:** dùng `PreparedStatement`, kiểm tra `ResultSet` và `executeUpdate()`.
4. **Quyết định có cần Repository abstraction không:** nếu interface không khác DAO và không giúp giảm phụ thuộc, cân nhắc bỏ lớp trung gian.
5. **Để service điều phối nghiệp vụ:** xác thực, quy tắc, nhiều repository và thông báo kết quả.
6. **Có chủ sở hữu transaction rõ:** một `Connection` cho toàn đơn vị cần commit/rollback; DAO không đóng connection mượn từ caller.
7. **Tách SQL lỗi với lỗi nghiệp vụ:** giữ nguyên nhân `SQLException` khi dịch lỗi qua adapter.
8. **Bảo vệ concurrency và dữ liệu:** ràng buộc DBMS, conditional update, khóa/optimistic locking nếu cần.
9. **Cẩn thận khi retry:** kết quả commit không rõ phải đối chiếu bằng idempotency key.
10. **Đo truy vấn và kiểm thử theo tầng:** fake/unit test cho service; DBMS thật cho SQL, transaction, mapping và concurrency.

**Ghi nhớ:** **DAO** nắm *cách* truy cập dữ liệu qua JDBC; **Repository** trình bày *những đối tượng/nghiệp vụ nào* được truy xuất hoặc lưu và có thể ẩn DAO; **Service** nắm *use case làm gì* và những thao tác nào cần cùng transaction. Ba khái niệm hỗ trợ nhau nhưng không đòi hỏi ba lớp vật lý riêng trong mọi dự án. Cấu trúc tốt nhất là cấu trúc giúp **SQL được quản lý tập trung, nghiệp vụ rõ ràng, transaction đúng ranh giới và kiểm thử được cả dữ liệu lẫn hành vi**.

# Auto-commit và nhiều câu lệnh trên cùng kết nối

> **Bối cảnh:** Spring Framework — Transaction Management → Nền tảng giao dịch. Bài học giải thích vì sao nhiều lệnh SQL được thực thi qua cùng một JDBC `Connection` vẫn có thể thuộc các giao dịch khác nhau, cách kiểm soát `commit`/`rollback` và cách Spring quản lý ranh giới giao dịch.

## 1. Phân biệt kết nối, câu lệnh và giao dịch

Ba khái niệm liên quan nhưng không đồng nghĩa:

- **Kết nối (JDBC `Connection`):** phiên làm việc mà ứng dụng dùng để gửi SQL đến cơ sở dữ liệu. Một kết nối có thể thực thi rất nhiều câu lệnh theo thời gian.
- **Câu lệnh (SQL statement):** một thao tác `SELECT`, `INSERT`, `UPDATE`, `DELETE`... được thực thi thông qua `Statement` hoặc `PreparedStatement`.
- **Giao dịch (transaction):** đơn vị công việc được xác nhận bằng `COMMIT` hoặc hủy bằng `ROLLBACK`. Khi cơ sở dữ liệu và các thao tác hỗ trợ giao dịch, các thay đổi của cùng giao dịch được commit cùng nhau hoặc rollback cùng nhau.

**Cùng một `Connection` không có nghĩa là cùng một giao dịch.** Ranh giới giao dịch phụ thuộc vào chế độ auto-commit, lệnh `commit()`/`rollback()` hoặc bộ quản lý giao dịch (như Spring). Một `Connection` có thể lần lượt phục vụ transaction T1, T2, T3.

Ví dụ nghiệp vụ chuyển 30 đơn vị tiền giữa hai tài khoản có số dư ban đầu A = 100 và B = 100:

```sql
UPDATE accounts SET balance = balance - 30 WHERE id = 1;
UPDATE accounts SET balance = balance + 30 WHERE id = 2;
```

Bất biến nghiệp vụ là tổng A + B vẫn bằng 200 nếu toàn bộ phép chuyển thành công. Nếu lệnh trừ tiền thành công nhưng lệnh cộng tiền thất bại và lệnh đầu đã commit, A = 70, B = 100: dữ liệu sai. Bởi vậy, **hai lệnh cần chung một transaction**, thay vì chỉ chung một connection.

## 2. Auto-commit trong JDBC thực sự làm gì?

Theo hợp đồng JDBC, một `Connection` mới mặc định có `autoCommit = true`; mã ứng dụng có thể kiểm tra bằng `connection.getAutoCommit()`. Với `autoCommit = true`, **mỗi câu lệnh SQL hoàn tất sẽ được commit như một transaction riêng**. Đây là quy tắc JDBC; khi dùng connection pool hoặc Spring, trạng thái kết nối nhận được có thể đã được cấu hình lại, vì vậy đừng đoán trạng thái thực tế.

```java
boolean enabled = connection.getAutoCommit();
connection.setAutoCommit(true);  // Mỗi statement là một transaction riêng.
connection.setAutoCommit(false); // Ứng dụng phải commit/rollback rõ ràng.
```

Đoạn trên minh họa API của một `Connection` đã có sẵn, không phải chương trình Java chạy độc lập.

### Hai lệnh trên cùng connection, auto-commit bật

```text
Connection C1, autoCommit = true

UPDATE A = A - 30  ── thành công ── COMMIT T1
UPDATE B = B + 30  ── lỗi ────────── T2 không commit
                                      |
Kết quả: T1 vẫn tồn tại; rollback T2 không thể hoàn tác T1.
```

Trong tình huống đó, gọi `rollback()` sau lỗi **không thể đảo ngược lệnh đầu đã commit**. Hơn nữa, JDBC không cho phép gọi `commit()`/`rollback()` khi connection đang ở auto-commit mode (driver sẽ báo lỗi theo API). Phải tắt auto-commit *trước* khi thực hiện các lệnh thuộc một đơn vị công việc.

### Hai lệnh trên cùng connection, auto-commit tắt

```text
Connection C1, autoCommit = false

Bắt đầu transaction T1 khi công việc SQL diễn ra
    |
    +-- UPDATE A = A - 30 ── thành công (chưa commit)
    |
    +-- UPDATE B = B + 30 ── thành công (chưa commit)
    |
    +-- COMMIT ──────────── cả hai thay đổi được xác nhận

Nếu lệnh thứ hai lỗi:
    +-- ROLLBACK ────────── hoàn tác cả thay đổi đầu tiên
```

Khi `autoCommit = false`, các lệnh thực thi sau một ranh giới commit/rollback sẽ thuộc giao dịch kế tiếp theo cơ chế JDBC/DBMS; không phải mỗi lần gọi `executeUpdate()` là một transaction độc lập.

### Chính xác khi nào auto-commit xảy ra?

JDBC định nghĩa thời điểm một statement hoàn tất:

| Loại thao tác | Khi nào statement được xem là hoàn tất để auto-commit? |
| --- | --- |
| `INSERT`, `UPDATE`, `DELETE` | Khi thao tác thực thi xong. |
| `SELECT` trả `ResultSet` | Khi `ResultSet` liên quan đã đóng. |
| `CallableStatement` hoặc statement có nhiều kết quả | Sau khi các `ResultSet` liên quan đã đóng và các kết quả/update count/output parameter đã được lấy đầy đủ. |

Chi tiết này quan trọng khi giữ `ResultSet` mở lâu: việc thực thi `executeQuery()` không đồng nghĩa giao dịch auto-commit luôn kết thúc ngay tại lời gọi đó. Sử dụng `try-with-resources` để đóng tài nguyên đúng lúc.

## 3. Bảng so sánh các tình huống dễ nhầm

| Tình huống | Một connection? | Một transaction cho cả hai SQL? | Nếu SQL thứ hai lỗi |
| --- | --- | --- | --- |
| JDBC `autoCommit=true`, thực thi 2 `UPDATE` | Có | **Không** | SQL thứ nhất đã commit nếu hoàn tất thành công |
| JDBC `autoCommit=false`, 2 `UPDATE`, sau đó `commit()` | Có | **Có** | Gọi `rollback()` trước khi commit để hủy cả hai |
| JDBC `autoCommit=false` nhưng `commit()` sau SQL thứ nhất | Có | **Không** | SQL thứ nhất đã commit |
| 2 `Connection` độc lập, mỗi cái tự commit | Không | **Không** | Không có rollback chung theo JDBC cục bộ |
| Spring `@Transactional` hoạt động, cả hai thao tác JDBC dùng đúng datasource/transaction manager | Spring quản lý connection tham gia transaction | **Có**, với propagation phù hợp | Rollback theo chính sách của transaction manager |

Chế độ auto-commit không quyết định **mức cô lập** (`READ_COMMITTED`, `REPEATABLE_READ`...) và cũng không tự giải quyết deadlock, lost update hoặc các vấn đề cạnh tranh dữ liệu. Atomicity và isolation là hai khía cạnh khác nhau.

## 4. Chạy một ví dụ JDBC hoàn chỉnh trên Java 17+

Ví dụ dùng **H2 in-memory database** để có thể chạy độc lập, không cần cài một máy chủ cơ sở dữ liệu. H2 là JDBC driver bên ngoài JDK; Java SE chỉ cung cấp các API `java.sql`, không tích hợp sẵn driver H2.

Tạo tệp `AutoCommitDemo.java`:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class AutoCommitDemo {
    // DB_CLOSE_DELAY=-1 giữ cơ sở dữ liệu trong bộ nhớ khi
    // tất cả connection đóng, cho đến khi JVM kết thúc.
    private static final String URL =
            "jdbc:h2:mem:tx_demo;DB_CLOSE_DELAY=-1";

    public static void main(String[] args) throws SQLException {
        initialize();

        demoAutoCommit();
        resetBalances();

        demoRollback();
        demoCommit();
    }

    private static Connection open() throws SQLException {
        return DriverManager.getConnection(URL, "sa", "");
    }

    private static void initialize() throws SQLException {
        try (Connection c = open();
             Statement s = c.createStatement()) {
            s.executeUpdate("""
                    CREATE TABLE accounts (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL CHECK (balance >= 0)
                    )
                    """);
            s.executeUpdate("""
                    INSERT INTO accounts (id, balance)
                    VALUES (1, 100), (2, 100)
                    """);
        }
    }

    private static void resetBalances() throws SQLException {
        try (Connection c = open();
             Statement s = c.createStatement()) {
            s.executeUpdate("UPDATE accounts SET balance = 100");
        }
    }

    private static void demoAutoCommit() throws SQLException {
        try (Connection c = open()) {
            // Connection do DriverManager tạo mới: autoCommit = true.
            try {
                adjustBalance(c, 1, -30);
                insertDuplicateId(c); // Cố ý vi phạm PRIMARY KEY.
            } catch (SQLException expected) {
                System.out.println("Auto-commit: lệnh thứ hai thất bại");
            }
        }
        printBalances("Sau lỗi với auto-commit");
    }

    private static void demoRollback() throws SQLException {
        try (Connection c = open()) {
            c.setAutoCommit(false);
            try {
                adjustBalance(c, 1, -30);
                insertDuplicateId(c); // Gây lỗi trong cùng transaction.
                c.commit();           // Không chạy đến đây.
            } catch (SQLException expected) {
                c.rollback();
                System.out.println("Giao dịch thủ công: ROLLBACK");
            }
        }
        printBalances("Sau rollback");
    }

    private static void demoCommit() throws SQLException {
        try (Connection c = open()) {
            c.setAutoCommit(false);
            try {
                adjustBalance(c, 1, -30);
                adjustBalance(c, 2, 30);
                c.commit();
                System.out.println("Giao dịch thủ công: COMMIT");
            } catch (SQLException error) {
                try {
                    c.rollback();
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            }
        }
        printBalances("Sau commit");
    }

    private static void adjustBalance(
            Connection c, int accountId, int delta)
            throws SQLException {
        try (PreparedStatement p = c.prepareStatement(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {
            p.setInt(1, delta);
            p.setInt(2, accountId);

            if (p.executeUpdate() != 1) {
                throw new SQLException("Unknown account: " + accountId);
            }
        }
    }

    private static void insertDuplicateId(Connection c)
            throws SQLException {
        try (PreparedStatement p = c.prepareStatement(
                "INSERT INTO accounts (id, balance) VALUES (1, 999)")) {
            p.executeUpdate(); // id=1 đã tồn tại nên H2 ném SQLException.
        }
    }

    private static void printBalances(String label)
            throws SQLException {
        try (Connection c = open();
             Statement s = c.createStatement();
             ResultSet rs = s.executeQuery(
                     "SELECT id, balance FROM accounts ORDER BY id")) {
            if (!rs.next()) {
                throw new SQLException("Missing account 1");
            }
            int a = rs.getInt("balance");

            if (!rs.next()) {
                throw new SQLException("Missing account 2");
            }
            int b = rs.getInt("balance");

            System.out.printf("%s: A=%d, B=%d%n", label, a, b);
        }
    }
}
```

**Chuẩn bị driver** bằng Maven và truy cập Internet (hoặc tải thủ công tệp `h2-2.3.232.jar` từ Maven Central):

```bash
mvn dependency:copy -Dartifact=com.h2database:h2:2.3.232 -DoutputDirectory=.
javac -encoding UTF-8 -cp h2-2.3.232.jar AutoCommitDemo.java
```

Chạy trên **Windows PowerShell/CMD** (classpath dùng dấu `;`):

```powershell
java -cp ".;h2-2.3.232.jar" AutoCommitDemo
```

Chạy trên **Linux/macOS** (classpath dùng dấu `:`):

```bash
java -cp ".:h2-2.3.232.jar" AutoCommitDemo
```

Kết quả chuẩn:

```text
Auto-commit: lệnh thứ hai thất bại
Sau lỗi với auto-commit: A=70, B=100
Giao dịch thủ công: ROLLBACK
Sau rollback: A=100, B=100
Giao dịch thủ công: COMMIT
Sau commit: A=70, B=130
```

**Phân tích từng lượt chạy:**

1. `demoAutoCommit()` dùng connection mới với auto-commit bật. `adjustBalance()` giảm A xuống 70 và được commit. `insertDuplicateId()` cố ý vi phạm khóa chính, ném `SQLException`. Dù hai lệnh dùng cùng `c`, thay đổi đầu tiên vẫn tồn tại.
2. `resetBalances()` đưa hai tài khoản về 100 để hai thí nghiệm sau có cùng điểm xuất phát.
3. `demoRollback()` tắt auto-commit trước khi cập nhật A. Lỗi ở câu lệnh thứ hai dẫn tới `rollback()`, làm A trở về 100; B không đổi.
4. `demoCommit()` cập nhật cả A và B rồi `commit()` một lần: A = 70, B = 130. `printBalances()` dùng một connection khác để quan sát dữ liệu đã được xác nhận.

**Giới hạn ví dụ:** giá trị `int` được dùng cho số dư nhỏ để minh họa transaction; trong nghiệp vụ tiền tệ thực tế hãy dùng kiểu số thập phân phù hợp (ví dụ `DECIMAL` trong SQL và `BigDecimal` trong Java), quy tắc làm tròn, kiểm tra số dư và chính sách chống xử lý lặp.

## 5. Mẫu quản lý transaction JDBC an toàn

Với JDBC thuần, mẫu phổ biến là: lấy connection → tắt auto-commit → chạy tất cả thao tác → commit nếu thành công → rollback nếu lỗi → đóng tài nguyên. Chỉ điều khiển transaction ở **một nơi sở hữu ranh giới giao dịch**.

```java
// Phác thảo hàm: dataSource, debit() và credit() được khai báo
// trong ứng dụng; đoạn này không phải chương trình độc lập.
void transfer(javax.sql.DataSource dataSource) throws SQLException {
    try (Connection c = dataSource.getConnection()) {
        boolean previousAutoCommit = c.getAutoCommit();

        try {
            c.setAutoCommit(false);
            debit(c);
            credit(c);
            c.commit();
        } catch (SQLException | RuntimeException failure) {
            try {
                c.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        } finally {
            // Chỉ khôi phục sau khi transaction đã commit/rollback.
            if (c.getAutoCommit() != previousAutoCommit) {
                c.setAutoCommit(previousAutoCommit);
            }
        }
    }
}
```

**Điều kiện sử dụng:** mẫu trên dành cho code **tự quản lý** connection JDBC độc lập, không nằm trong một transaction do Spring quản lý. `debit(c)` và `credit(c)` phải dùng chính tham số `c`; nếu mỗi hàm tự gọi `dataSource.getConnection()`, chúng có thể chạy trên các connection/transaction khác nhau. Với production, cần thiết kế rõ cách xử lý lỗi khi rollback hoặc khôi phục trạng thái thất bại; không để lỗi cleanup che khuất nguyên nhân gốc.

Hai bẫy quan trọng:

- **Không bật lại auto-commit trước khi rollback.** Theo JDBC, nếu thay đổi chế độ auto-commit trong khi transaction đang hoạt động, transaction sẽ được commit. Vì vậy lời gọi `setAutoCommit(true)` trong `finally` mà chưa `rollback()` có thể biến giao dịch lỗi thành giao dịch đã commit.
- **Không dựa vào `close()` để tự động rollback.** JDBC không quy định một kết quả thống nhất khi đóng connection còn transaction đang hoạt động; hãy kết thúc transaction rõ ràng trước khi trả connection về pool/đóng nó.

Nếu transaction bao gồm `SQLException` nhưng code bắt và **nuốt lỗi**, dòng điều khiển có thể đi tiếp đến `commit()`. Luôn xác định lỗi nào buộc rollback và ném lại hoặc đánh dấu rollback phù hợp.

## 6. Spring quản lý auto-commit và connection như thế nào?

Trong ứng dụng Spring sử dụng JDBC, `@Transactional` thiết lập ranh giới transaction **ở lời gọi phương thức qua Spring proxy** (trong chế độ proxy mặc định). `PlatformTransactionManager` thích hợp, chẳng hạn `JdbcTransactionManager` hoặc `DataSourceTransactionManager`, phối hợp lấy connection, thiết lập trạng thái transaction, commit/rollback và dọn dẹp khi phương thức kết thúc.

Khi có transaction JDBC đang hoạt động trên cùng `DataSource`, `JdbcTemplate` dùng cơ chế `DataSourceUtils` để tham gia vào connection được gắn với transaction hiện tại. Do đó nhiều lời gọi `jdbcTemplate.update(...)` trong một phương thức `@Transactional` có thể nằm trong **cùng một transaction vật lý**. Cơ chế này không có nghĩa mọi câu lệnh trên mọi datasource hoặc mọi connection của ứng dụng đều dùng chung transaction.

### Ví dụ Spring JDBC: một chuyển tiền là một transaction

Đây là lớp service dành cho **ứng dụng Spring đã cấu hình** `DataSource`, `JdbcTemplate`, transaction management và bảng `accounts(id, balance)`. Đoạn này không chạy độc lập nếu thiếu môi trường Spring và database.

```java
import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
                """
                UPDATE accounts
                SET balance = balance - ?
                WHERE id = ? AND balance >= ?
                """,
                amount, fromId, amount);

        if (debited != 1) {
            throw new IllegalStateException(
                    "Source account missing or insufficient balance");
        }

        int credited = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, toId);

        if (credited != 1) {
            throw new IllegalStateException(
                    "Destination account missing");
        }
    }
}
```

Khi một bean khác gọi `transferService.transfer(...)` qua Spring proxy, manager bắt đầu/tham gia transaction trước khi chạy thân hàm. Nếu cả hai `UPDATE` thành công và phương thức kết thúc bình thường, transaction được commit. Nếu lệnh thứ hai không cập nhật được hàng nào, code ném `IllegalStateException`; mặc định Spring đánh dấu rollback cho runtime exception, nên cả hai cập nhật bị rollback.

Giá trị trả về của `JdbcTemplate.update` là số hàng bị tác động. Việc kiểm tra `!= 1` tránh kiểu lỗi nghiệp vụ rất thường gặp: SQL thực thi không ném exception nhưng không cập nhật dòng đích nào; nếu không kiểm tra, một nửa nghiệp vụ vẫn có thể được commit.

**Vì sao không gọi `connection.setAutoCommit(false)` thủ công ở đây?** Khi transaction thuộc quyền Spring, chính transaction manager phải sở hữu việc bắt đầu/kết thúc nó. Can thiệp `commit()`/`rollback()` hoặc thay auto-commit trực tiếp ở tầng repository có thể phá vỡ ranh giới do Spring điều phối.

### Những điều kiện để `@Transactional` thực sự có tác dụng

1. **Proxy phải được đi qua.** Trong chế độ proxy thông thường, lời gọi từ bean khác vào phương thức được Spring quản lý mới được intercept. Gọi `this.transfer(...)` trong cùng đối tượng (*self-invocation*) không tự kích hoạt advice transaction cho phương thức được gọi.
2. **Tài nguyên phải tham gia đúng manager.** `JdbcTemplate` phải dùng `DataSource` được transaction manager quản lý. Tự mở connection bằng `DriverManager.getConnection(...)`, hoặc lấy trực tiếp một connection khác ngoài cơ chế transaction, sẽ không tự tham gia vào transaction Spring hiện tại.
3. **Propagation có thể thay đổi ranh giới.** Mặc định `Propagation.REQUIRED` tham gia transaction hiện có hoặc tạo mới nếu chưa có. `REQUIRES_NEW` tạo transaction riêng và tạm treo transaction ngoài; không thể suy diễn rằng hai service methods gọi nối tiếp luôn dùng một transaction.
4. **Quy tắc rollback cần được hiểu đúng.** Mặc định của `@Transactional` là rollback cho `RuntimeException` và `Error`; checked `Exception` không mặc nhiên kích hoạt rollback. Có thể cấu hình `rollbackFor = Exception.class` cho yêu cầu phù hợp. Nếu bắt lỗi rồi trả kết quả bình thường, Spring có thể commit, trừ khi transaction đã được đánh dấu rollback-only hoặc cấu hình khác.
5. **Không trộn mô hình giao dịch.** Ví dụ JDBC imperative này áp dụng cho transaction dựa trên thread của Spring. R2DBC/reactive dùng cơ chế gắn transaction vào reactive context, không thể suy luận y hệt theo thread-bound JDBC connection.

Một transaction database đơn lẻ không tự rollback được tác dụng phụ bên ngoài như gọi HTTP, gửi email hoặc ghi sang một hệ dữ liệu độc lập không được phối hợp trong cùng transaction.

## 7. Các trường hợp thường làm mất tính nguyên tử

### Gọi `commit()` giữa chừng

```java
connection.setAutoCommit(false);
debit(connection);
connection.commit(); // T1 đã kết thúc.
credit(connection);   // Thuộc transaction kế tiếp.
connection.rollback(); // Chỉ rollback phần chưa commit của T2.
```

Mã chỉ minh họa; `debit`/`credit` là các hàm giả định nhận cùng connection. Một lời gọi `commit()` giữa hai thao tác đã chia nghiệp vụ thành hai transaction bất kể connection có giữ nguyên hay không.

### Dùng hai connection khác nhau

```java
try (Connection c1 = dataSource.getConnection();
     Connection c2 = dataSource.getConnection()) {
    // c1 và c2 là hai connection được lấy độc lập.
    // commit của c1 không tự động commit/rollback c2.
}
```

Có thể hai logical connections trong một số môi trường được hệ thống quản lý đặc biệt, nhưng **không được giả định** chúng thuộc chung một JDBC local transaction. Với JDBC thuần, muốn nhiều câu lệnh cùng một transaction thì truyền cùng connection và kiểm soát commit ở điểm chung; với Spring, dùng cơ chế tham gia transaction của framework.

### Bắt lỗi nhưng vẫn commit

```java
connection.setAutoCommit(false);
debit(connection);
try {
    credit(connection);
} catch (SQLException ignored) {
    // Sai: lỗi đã bị bỏ qua.
}
connection.commit(); // Có thể xác nhận chỉ thao tác debit.
```

Không phải mọi `SQLException` đều tự rollback toàn bộ giao dịch. Một số hệ quản trị có thể chuyển transaction sang trạng thái lỗi cần rollback; điều đó vẫn **không** thay thế chính sách xử lý lỗi rõ ràng của ứng dụng.

### Nhầm `executeBatch()` với transaction

`executeBatch()` gom các statement để gửi/thực thi hiệu quả hơn, nhưng **batching không bảo đảm tính nguyên tử của cả nhóm trong mọi chế độ/driver/DBMS**. `autoCommit=true` và `BatchUpdateException` có thể dẫn đến trạng thái đã thực thi một phần, tùy driver và database. Nếu toàn bộ batch phải thành công hoặc thất bại cùng nhau, hãy đặt nó trong transaction do ứng dụng hoặc Spring quản lý và xử lý rollback.

### Nhầm transaction với một request HTTP

Một request có thể gọi nhiều repository, nhiều datasource hoặc service. Một HTTP request **không tự động** là một transaction database. Phạm vi transaction nên bám theo đơn vị nghiệp vụ cần atomicity và tránh giữ transaction mở qua các thao tác mạng chậm khi không cần.

## 8. Kiểm tra và xử lý sự cố

Khi thấy dữ liệu thay đổi một nửa dù hai SQL được chạy liên tiếp, kiểm tra theo thứ tự:

1. **Có thực sự một connection tham gia?** Trong JDBC thuần, theo dõi object/connection nhận vào mỗi DAO. Trong Spring, xác nhận cùng `DataSource`/transaction manager và dùng `JdbcTemplate` hoặc `DataSourceUtils` đúng cách.
2. **Auto-commit ở thời điểm thực thi là gì?** `getAutoCommit()` hữu ích để chẩn đoán JDBC thuần; tránh thay đổi trạng thái trực tiếp của connection đang do Spring quản lý chỉ để thử.
3. **`commit` hoặc thay đổi `autoCommit` có diễn ra sớm?** Tìm lời gọi `commit()` giữa chừng, helper tự commit, `setAutoCommit(true)` trước rollback và cơ chế thư viện tạo transaction riêng.
4. **`@Transactional` đã được intercept chưa?** Xem cách bean được khởi tạo/gọi, self-invocation, cấu hình transaction management, propagation và manager.
5. **Lỗi có thoát ra ngoài boundary không?** Kiểm tra exception bị bắt/nuốt, checked exception và rollback rules, hoặc nhánh trả về bình thường sau lỗi.
6. **Thao tác có thật sự tác động đúng hàng không?** Kiểm tra update count, ràng buộc database và điều kiện `WHERE`. Không có exception chưa chắc có thay đổi như dự kiến.
7. **Database và thao tác có hỗ trợ transaction không?** Một số DDL, storage engine hoặc thao tác ngoài database có quy tắc commit/rollback riêng. Xem tài liệu DBMS cụ thể trước khi khẳng định mọi SQL đều có thể rollback.
8. **Có cạnh tranh giữa các transaction không?** Nếu thao tác không lỗi nhưng kết quả sai khi chạy đồng thời, kiểm tra isolation level, locking, lost update, deadlock và chiến lược retry ở cấp nghiệp vụ.

### Kịch bản kiểm thử tối thiểu

- **Thành công:** cả debit và credit chạy xong; tổng số dư trước/sau không đổi và hai thay đổi đều nhìn thấy sau commit.
- **Lỗi ở lệnh thứ hai:** cố ý gây lỗi SQL hoặc ném runtime exception; xác nhận số dư cả hai bên giữ nguyên sau rollback.
- **Không tìm thấy tài khoản đích:** `UPDATE` trả về 0; xác nhận không commit phần trừ tiền.
- **Nhiều lời gọi service lồng nhau:** xác nhận propagation mong muốn (ví dụ `REQUIRED` so với `REQUIRES_NEW`).
- **Hai yêu cầu đồng thời:** bảo vệ bất biến số dư và kiểm tra chính sách isolation/locking riêng; atomicity của từng transaction một mình chưa giải quyết mọi race condition.

## 9. Ghi nhớ

- **Connection là đường thực thi SQL; transaction là ranh giới commit/rollback.** Chúng không đồng nghĩa.
- **`autoCommit=true`:** mỗi statement hoàn tất sẽ tự commit, dù tất cả chạy trên cùng connection.
- **`autoCommit=false`:** nhiều statement có thể thuộc cùng transaction; phải gọi `commit()` hoặc `rollback()` rõ ràng.
- **Một thao tác nghiệp vụ có nhiều bước phụ thuộc nhau** cần cùng một transaction; rollback phải được kiểm chứng bằng tình huống lỗi thực tế.
- **Trong Spring:** đặt `@Transactional` ở boundary service thích hợp, dùng DAO/JdbcTemplate tham gia đúng transaction manager và hiểu quy tắc proxy, propagation, exception.

## Tài liệu tham khảo

- [Java SE 17 — `java.sql.Connection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): auto-commit, statement completion, `commit`, `rollback` và `setAutoCommit`.
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceUtils`, `JdbcTemplate` và connection gắn với transaction.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy, propagation và mặc định rollback.

# Vai trò của JDBC trong giao tiếp với cơ sở dữ liệu quan hệ

Khi một ứng dụng Java cần đọc khách hàng, lưu đơn hàng hoặc chuyển tiền, nó phải giao tiếp với hệ quản trị cơ sở dữ liệu quan hệ (RDBMS). Java không trực tiếp sửa trang dữ liệu của PostgreSQL hay MySQL. Thay vào đó, ứng dụng dùng **JDBC (Java Database Connectivity)** để **mở kết nối, gửi SQL và tham số, đọc kết quả, quản lý giao dịch và nhận lỗi**. JDBC driver cụ thể sẽ triển khai việc trao đổi với server.

Bài học thuộc chương **Hệ sinh thái Java** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Mục tiêu là hiểu ranh giới persistence giữa ứng dụng Java và DBMS, cách xử lý kết nối, truy vấn, giao dịch, tài nguyên và lỗi. Các ví dụ minh họa dùng Java cùng PostgreSQL; cú pháp SQL và khả năng driver có thể khác trên MySQL, SQL Server hoặc DBMS khác.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của JDBC API, JDBC driver, SQL và DBMS.
2. Phân biệt **DriverManager**, **DataSource** và connection pool.
3. Sử dụng **Connection**, **PreparedStatement** và **ResultSet**.
4. Quản lý tài nguyên bằng **try-with-resources**.
5. Điều khiển **auto-commit**, **commit**, **rollback** trong một transaction JDBC.
6. Phân loại **SQLException/SQLSTATE**, nhận biết lỗi connection và COMMIT chưa rõ kết quả.
7. Hiểu JDBC đứng ở đâu bên dưới **Spring JDBC**, **JPA** và **Hibernate**.

## 2. Kiến trúc: JDBC là lớp giao tiếp, không phải DBMS

~~~text
HTTP API / Message Consumer / Batch Job
                    |
                    v
              Java Service
                    |
                    v
          Repository / Data Gateway
                    |
           +--------+---------+
           |                  |
       JDBC trực tiếp     Spring JDBC / ORM
           |                  |
           +--------+---------+
                    |
           JDBC API (java.sql,
                    javax.sql)
                    |
               JDBC Driver
                    |
            Network + DB Protocol
                    |
                  RDBMS
              SQL/Transaction
                    |
           Tables, Indexes, WAL
~~~

**JDBC API** là những class và interface chuẩn như Connection, Statement, PreparedStatement, ResultSet, SQLException. **JDBC driver** biết cách chuyển lời gọi API thành thông điệp giao tiếp với một DBMS cụ thể. **DBMS** mới là thành phần xác thực session, lập kế hoạch và thực thi SQL, thực hiện khóa, kiểm soát đồng thời, ghi WAL và xác nhận commit.

Khi Java gọi **statement.executeQuery()**, JDBC không chạy câu SQL trong JVM. Driver gửi yêu cầu sang DB, nhận kết quả và trình bày dữ liệu dưới dạng ResultSet.

| Thành phần | Trách nhiệm |
|---|---|
| **JDBC** | Chuẩn hóa giao diện Java để giao tiếp với RDBMS |
| **JDBC driver** | Hiện thực JDBC và giao thức của DBMS |
| **SQL** | Ngôn ngữ truy vấn/thao tác dữ liệu do DBMS thực thi |
| **Connection pool** | Quản lý, tái sử dụng và giới hạn số connection |
| **JdbcTemplate / Spring JDBC** | Giảm mã lặp lại khi dùng JDBC, tích hợp Spring transaction |
| **JPA** | Chuẩn persistence theo entity và persistence context |
| **Hibernate** | ORM thường dùng JDBC làm tầng giao tiếp RDBMS ở phía dưới |

**JDBC không phải ORM.** Nó không tự tạo mapping entity và quan hệ như JPA/Hibernate. JDBC cũng không xóa bỏ khác biệt về **SQL dialect**: PostgreSQL có ON CONFLICT và INSERT ... RETURNING, trong khi DBMS khác có cú pháp upsert hoặc generated key khác nhau.

## 3. Các thành phần JDBC quan trọng

| API | Dùng để | Lưu ý |
|---|---|---|
| **DriverManager** | Tìm driver theo JDBC URL và mở Connection | Không phải connection pool |
| **DataSource** | Cấp Connection, thường được inject vào repository | Có thể có pool hoặc không |
| **Connection** | Phiên giao tiếp với trạng thái transaction | Đóng/trả lại pool kịp thời |
| **Statement** | Gửi SQL trực tiếp | Không ghép input người dùng vào SQL |
| **PreparedStatement** | SQL có placeholder và bind tham số | Ưu tiên cho dữ liệu đầu vào |
| **CallableStatement** | Gọi stored procedure nếu DBMS hỗ trợ | Hành vi phụ thuộc driver |
| **ResultSet** | Duyệt các hàng và cột kết quả | Vòng đời gắn với Statement/Connection |
| **SQLException** | Thông báo lỗi từ driver/DB | Đọc SQLSTATE và mã lỗi vendor |
| **DatabaseMetaData** | Tra capability, thông tin bảng và driver | Hữu ích cho công cụ/chẩn đoán |

Cách map dữ liệu thường gặp:

- **BIGINT** ↔ **long / Long**.
- **VARCHAR** ↔ **String**.
- **NUMERIC/DECIMAL** ↔ **BigDecimal**, phù hợp cho dữ liệu tiền cần tính thập phân chính xác.
- **BOOLEAN** ↔ **boolean / Boolean**.
- **DATE** ↔ **LocalDate** nếu driver hỗ trợ mapping Java time phù hợp.
- **TIMESTAMP** ↔ kiểu thời gian Java thích hợp theo quy ước timezone của DB/driver.

Nếu cột SQL có thể NULL, không tùy tiện map thành giá trị nguyên thủy rồi hiểu đó là số không hoặc false. Với tiền, tránh dùng **double** khi cần độ chính xác thập phân.

## 4. Luồng một câu SQL từ Java tới DB

~~~mermaid
sequenceDiagram
    participant J as Java Repository
    participant P as DataSource/Pool
    participant D as JDBC Driver
    participant S as RDBMS
    J->>P: getConnection()
    P-->>J: Connection
    J->>D: prepareStatement + bind
    J->>D: executeQuery()
    D->>S: SQL + tham số
    S-->>D: Rows hoặc lỗi
    D-->>J: ResultSet / SQLException
    J->>P: Connection.close()
~~~

Quy trình thực tế:

1. Repository mượn Connection từ DataSource.
2. Java chuẩn bị SQL có placeholder, đặt tham số.
3. Driver chuyển lệnh và tham số sang giao thức DBMS.
4. DBMS thực thi SQL theo schema, quyền, transaction và chỉ mục.
5. Driver nhận hàng dữ liệu hoặc số dòng cập nhật.
6. Repository map dữ liệu sang DTO/domain object và đóng tài nguyên.

**PreparedStatement** giúp tách câu lệnh khỏi dữ liệu đầu vào. Việc server có cache/reuse kế hoạch truy vấn hay không tùy DBMS và driver; không được coi đây là bảo đảm tuyệt đối mỗi PreparedStatement sẽ dùng plan đã cache.

## 5. Mở kết nối: DriverManager và DataSource

### 5.1. DriverManager cho ví dụ nhỏ

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

public class JdbcConnectDemo {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:postgresql://localhost:5432/training";
        Properties properties = new Properties();
        properties.setProperty("user", System.getenv("DB_USER"));
        properties.setProperty("password", System.getenv("DB_PASSWORD"));

        try (Connection connection =
                     DriverManager.getConnection(url, properties)) {
            System.out.println(connection.getAutoCommit());
        }
    }
}
~~~

Ví dụ giả định PostgreSQL đã có database **training**, có JDBC driver trong dependency và hai biến môi trường đã được đặt. Không hardcode mật khẩu trong source code hay URL ghi log. Với JDBC driver hiện đại, thư viện thường tự đăng ký qua cơ chế Service Provider; không nhất thiết gọi Class.forName như các ví dụ cũ.

**DriverManager không phải connection pool.** Mỗi lần mở Connection qua DriverManager thường tạo một phiên mới, có chi phí kết nối, xác thực và tài nguyên phía server. Với service nhiều request, DataSource được pool quản lý thường phù hợp hơn.

### 5.2. DataSource cho repository

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class DbHealthProbe {
    private final DataSource dataSource;

    public DbHealthProbe(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean canConnect() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            return connection.isValid(2);
        }
    }
}
~~~

**javax.sql.DataSource** là tên package chuẩn trong Java, không phải jakarta.sql. Một DataSource có thể là pool (ví dụ HikariCP) hoặc dạng không có pool; interface này tự nó không bắt buộc pooling.

**Connection.isValid(2)** kiểm tra kết nối tại thời điểm gọi với timeout bằng giây. Sau kiểm tra, mạng vẫn có thể mất ngay trước khi gửi SQL, nên phải xử lý SQLException tại thao tác thật.

### 5.3. Connection pool và try-with-resources

~~~text
Request A -> mượn Connection 1 -> query -> close -> trả pool
Request B -> mượn Connection 1 -> query -> close -> trả pool
Request C -> mượn Connection 2 -> transaction -> close -> trả pool
~~~

Với pool, gọi **Connection.close()** trên wrapper thường mang nghĩa **trả connection cho pool**, không phải chắc chắn đóng socket vật lý. Vì vậy, không lưu Connection vào một field singleton dùng chung cho nhiều thread.

Pool có giới hạn như maximumPoolSize và connectionTimeout. Nếu quá nhiều request giữ connection lâu, pool cạn và các request mới phải đợi. Tăng pool vô hạn không làm một câu SQL thiếu chỉ mục chạy nhanh hơn; tổng số connection của mọi instance còn có thể gây quá tải DB.

## 6. Bảng ví dụ trong PostgreSQL

~~~sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    owner_name VARCHAR(120) NOT NULL,
    balance NUMERIC(18, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts (id, owner_name, balance)
VALUES
    (101, 'An', 150000.00),
    (102, 'Binh', 50000.00);
~~~

**PRIMARY KEY** ngăn ID trùng. **CHECK(balance >= 0)** bảo vệ một quy tắc ở DB. **NUMERIC(18,2)** phù hợp minh họa tiền hơn số chấm động; production còn cần mã tiền tệ, quy tắc làm tròn, kiểm toán và chống ghi trùng.

## 7. Truy vấn với PreparedStatement và ResultSet

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class AccountRepository {
    private final DataSource dataSource;

    public AccountRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public record Account(
            long id, String ownerName, BigDecimal balance) {}

    public Optional<Account> findById(long accountId)
            throws SQLException {
        String sql = """
                SELECT id, owner_name, balance
                FROM accounts
                WHERE id = ?
                """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement stmt = connection.prepareStatement(sql)) {
            stmt.setLong(1, accountId);

            try (ResultSet rows = stmt.executeQuery()) {
                if (!rows.next()) {
                    return Optional.empty();
                }

                return Optional.of(new Account(
                        rows.getLong("id"),
                        rows.getString("owner_name"),
                        rows.getBigDecimal("balance")));
            }
        }
    }
}
~~~

Giải thích:

- **?** là placeholder cho giá trị SQL, tham số JDBC bắt đầu từ **vị trí 1**.
- **setLong(1, accountId)** truyền giá trị thay vì ghép chuỗi vào SQL.
- **executeQuery()** trả ResultSet, cursor ban đầu ở trước hàng đầu; **next()** chuyển tới hàng kế tiếp.
- **getLong/getString/getBigDecimal** đọc cột và map sang Java record.
- **Optional.empty()** diễn tả không tìm thấy bản ghi.
- **try-with-resources** đóng ResultSet, PreparedStatement và Connection kể cả khi có exception.

### 7.1. executeQuery và executeUpdate

| Phương thức | Dùng để | Kết quả |
|---|---|---|
| **executeQuery()** | Câu trả tập hàng, thường là SELECT | ResultSet |
| **executeUpdate()** | INSERT, UPDATE, DELETE hoặc DDL phù hợp | Update count/số dòng thay đổi |
| **execute()** | Câu có thể trả nhiều dạng kết quả | Boolean báo kết quả đầu là ResultSet hay không |

Ví dụ cập nhật tên:

~~~java
String sql = "UPDATE accounts SET owner_name = ? WHERE id = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement stmt = connection.prepareStatement(sql)) {
    stmt.setString(1, newOwnerName);
    stmt.setLong(2, accountId);

    int affected = stmt.executeUpdate();
    if (affected != 1) {
        throw new IllegalStateException("Không tìm thấy tài khoản");
    }
}
~~~

Đây là đoạn mã minh họa, giả định các biến cần thiết đã có. **Một câu lệnh thành công không chứng minh toàn bộ nghiệp vụ nhiều bước đã thành công**; cần transaction nếu nhiều câu phải commit cùng nhau.

### 7.2. Chống SQL injection

Không an toàn:

~~~java
String sql = "SELECT id FROM accounts WHERE owner_name = '"
        + userSuppliedName + "'";
~~~

Một input đặc biệt có thể thay đổi cú pháp/ý nghĩa SQL, tạo lỗ hổng **SQL injection**.

Dùng bind:

~~~java
String sql = "SELECT id FROM accounts WHERE owner_name = ?";
try (PreparedStatement stmt = connection.prepareStatement(sql)) {
    stmt.setString(1, userSuppliedName);
    try (ResultSet rows = stmt.executeQuery()) {
        while (rows.next()) {
            // Xử lý các ID tìm được.
        }
    }
}
~~~

Placeholder **?** dùng cho **giá trị**, không dùng để thay tên bảng/cột hay từ khóa ORDER BY. Nếu API cho chọn cột sắp xếp, phải đối chiếu với danh sách tên cột cho phép.

PreparedStatement không thay thế việc phân quyền DB tối thiểu và kiểm tra quyền người dùng.

## 8. ResultSet, NULL, bộ nhớ và vòng đời

Khi đọc nhiều hàng:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement stmt = connection.prepareStatement(
             "SELECT id, owner_name, balance "
             + "FROM accounts ORDER BY id");
     ResultSet rows = stmt.executeQuery()) {

    while (rows.next()) {
        long id = rows.getLong("id");
        String owner = rows.getString("owner_name");
        BigDecimal balance = rows.getBigDecimal("balance");
        // Map sang DTO khi ResultSet còn sống.
    }
}
~~~

Nếu cột SQL có thể **NULL** thì getter kiểu nguyên thủy như **getLong** có thể trả 0 cho NULL. Dùng **rows.wasNull()** ngay sau getter để phân biệt:

~~~java
long value = rows.getLong("referrer_id");
Long referrerId = rows.wasNull() ? null : value;
~~~

Không trả ResultSet sau khi đã đóng Connection:

~~~java
// Thiết kế sai: tài nguyên đã đóng khi caller nhận ResultSet.
public ResultSet findAll() throws SQLException {
    try (Connection connection = dataSource.getConnection();
         PreparedStatement stmt = connection.prepareStatement(
                 "SELECT * FROM accounts")) {
        return stmt.executeQuery();
    }
}
~~~

**Nên map ResultSet thành DTO/record** trong repository. Khi xử lý dữ liệu lớn, cần thiết kế streaming có kiểm soát, không giữ Connection mở xuyên thời gian chờ của HTTP request.

**Statement.setFetchSize(n)** là hint về cách driver lấy dữ liệu, **không phải LIMIT**. Với PostgreSQL JDBC, cursor-based fetching có các điều kiện về auto-commit, ResultSet và driver. Nếu API chỉ cần 20 dòng, dùng SQL LIMIT và ORDER BY ổn định hoặc keyset pagination.

## 9. Transaction JDBC: auto-commit, commit và rollback

Một JDBC Connection mới thường có **autoCommit = true**: mỗi câu lệnh SQL được commit riêng khi hoàn tất. Điều này tiện cho truy vấn và thao tác đơn lẻ, nhưng có thể làm sai nghiệp vụ gồm **nhiều thay đổi cần nguyên tử**.

Giả sử chuyển 100.000 đồng từ tài khoản 101 sang tài khoản 102. Nếu trừ tiền đã commit nhưng cộng tiền thất bại, số dư bị mất. Cần thực hiện cả hai bước trong **cùng transaction trên cùng một Connection**.

~~~text
connection.setAutoCommit(false)
               |
               v
     UPDATE trừ tài khoản 101
               |
     UPDATE cộng tài khoản 102
               |
      Kiểm tra số hàng thay đổi
              / \
            OK   Lỗi
            |     |
         COMMIT  ROLLBACK
~~~

### 9.1. Mẫu Java JDBC có ranh giới giao dịch

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class TransferService {
    private final DataSource dataSource;

    public TransferService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void transfer(long fromId, long toId, BigDecimal amount)
            throws SQLException {
        if (fromId == toId || amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Thông tin giao dịch sai");
        }

        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getAutoCommit()) {
                throw new SQLException(
                        "Connection đang thuộc transaction khác");
            }

            connection.setAutoCommit(false);
            boolean transactionEnded = false;
            boolean commitSent = false;
            try {
                String debitSql = "UPDATE accounts "
                        + "SET balance = balance - ? "
                        + "WHERE id = ? AND balance >= ?";
                try (PreparedStatement debit =
                             connection.prepareStatement(debitSql)) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, fromId);
                    debit.setBigDecimal(3, amount);

                    if (debit.executeUpdate() != 1) {
                        throw new IllegalStateException(
                                "Tài khoản nguồn không đủ số dư");
                    }
                }

                String creditSql = "UPDATE accounts "
                        + "SET balance = balance + ? WHERE id = ?";
                try (PreparedStatement credit =
                             connection.prepareStatement(creditSql)) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, toId);

                    if (credit.executeUpdate() != 1) {
                        throw new IllegalStateException(
                                "Không tìm thấy tài khoản đích");
                    }
                }

                commitSent = true;
                connection.commit();
                transactionEnded = true;
            } catch (SQLException | RuntimeException failure) {
                if (!commitSent) {
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
                    // Chỉ bật autoCommit khi đã kết thúc transaction.
                    connection.setAutoCommit(true);
                }
            }
        }
    }
}
~~~

**Những ý quan trọng:**

- **setAutoCommit(false)** chuyển sang quản lý giao dịch thủ công.
- **UPDATE ... WHERE balance >= ?** kiểm tra và trừ số dư trong một câu SQL. Nó tốt hơn cách đọc số dư, kiểm tra trong Java rồi ghi một con số tính từ snapshot cũ mà thiếu kiểm soát đồng thời.
- **executeUpdate()** trả số dòng ảnh hưởng. Nếu trừ hoặc cộng cập nhật 0 hàng thì nghiệp vụ thất bại và phải rollback, dù JDBC không nhất thiết ném SQLException.
- **commit()** chấp nhận transaction; **rollback()** hủy các thay đổi chưa commit.
- **setAutoCommit(true)** khi transaction còn mở có thể khiến transaction commit ngầm theo JDBC, vì vậy ví dụ chỉ khôi phục cấu hình sau khi xác nhận đã kết thúc.

**Giới hạn của mẫu:** đây là code nhằm minh họa một transaction JDBC do phương thức tự sở hữu. Nếu COMMIT gây lỗi mạng, kết quả có thể **không xác định**: server có thể đã commit trước khi phản hồi mất. Code không retry tự động ở nhánh đó. Production cần **operation_id/idempotency**, quy trình đối soát và chính sách connection pool loại bỏ hoặc dọn Connection ở trạng thái không đáng tin. Mẫu cũng chưa bao gồm ghi lịch sử chuyển tiền; hệ thống tài chính thực tế cần thêm kiểm toán và bảo vệ nghiệp vụ.

### 9.2. Cùng một Connection cho một transaction

Nếu phần trừ tiền dùng Connection A và phần cộng tiền dùng Connection B, việc cả hai cùng tắt auto-commit **không tạo ra một transaction chung**. Mỗi connection có ranh giới commit/rollback riêng. Giao dịch qua nhiều DB hoặc hệ thống ngoài cần cơ chế điều phối khác, chẳng hạn outbox/saga hoặc distributed transaction khi hạ tầng hỗ trợ.

### 9.3. Isolation và savepoint

JDBC cho phép yêu cầu isolation:

~~~java
connection.setTransactionIsolation(
        Connection.TRANSACTION_SERIALIZABLE);
~~~

Một số hằng số khác là **TRANSACTION_READ_COMMITTED** và **TRANSACTION_REPEATABLE_READ**. DBMS có thể khác về chi tiết hiện thực và mức hỗ trợ; nên đặt isolation trước khi bắt đầu transaction và để connection pool/framework khôi phục trạng thái khi trả connection.

JDBC cũng có savepoint khi được hỗ trợ:

~~~java
Savepoint mark = connection.setSavepoint("before_optional");
try {
    writeOptionalNote(connection);
} catch (SQLException error) {
    connection.rollback(mark);
} finally {
    connection.releaseSavepoint(mark);
}
~~~

Đây là snippet minh họa; **writeOptionalNote** do ứng dụng tự định nghĩa và connection đang quản lý giao dịch thủ công. Rollback tới savepoint **không commit phần còn lại**; release/rollback savepoint cũng có thể gặp lỗi. Chỉ dùng cho bước nghiệp vụ thực sự không bắt buộc.

## 10. SQLException và những lỗi cần phân loại

JDBC báo lỗi thông qua **SQLException**. Những thông tin hữu ích gồm:

~~~java
try {
    // Thực hiện câu SQL hoặc transaction...
} catch (SQLException failure) {
    String sqlState = failure.getSQLState();
    int vendorCode = failure.getErrorCode();

    // Phân loại theo DBMS và vị trí lỗi.
    // Không log mật khẩu hoặc dữ liệu nhạy cảm.
    throw failure;
}
~~~

**SQLSTATE** là mã phân loại lỗi; **getErrorCode()** chứa mã riêng của nhà cung cấp DBMS/driver. Có thể có thêm **getNextException()** và cause chain, đặc biệt khi dùng framework bọc lỗi.

Ví dụ thường gặp với PostgreSQL:

| SQLSTATE | Ý nghĩa | Cách xử lý thường gặp |
|---|---|---|
| **23505** | Vi phạm UNIQUE | Kiểm tra dữ liệu/nghiệp vụ, không retry vô điều kiện |
| **23503** | Vi phạm FOREIGN KEY | Kiểm tra dữ liệu tham chiếu |
| **40001** | Serialization failure | Rollback và retry **toàn transaction** nếu an toàn |
| **40P01** | Deadlock detected | Có thể retry toàn transaction; nên sửa thứ tự khóa |
| **08xxx** | Lỗi kết nối | Bỏ Connection lỗi, xác định giai đoạn xảy ra |
| **57014** | Query canceled | Xem timeout/hủy truy vấn, không mặc định retry |

**Không retry mọi SQLException.** Ràng buộc UNIQUE hoặc CHECK bị vi phạm thường là vấn đề nghiệp vụ ổn định. Khi DBMS xác nhận transaction đã bị hủy bởi serialization/deadlock, một attempt mới phải mở transaction mới và **đọc lại dữ liệu để ra quyết định**.

### 10.1. Mất phản hồi ở COMMIT không đồng nghĩa rollback

~~~text
Java                           Database
 |--- INSERT đơn hàng --------->|
 |<-- execute thành công -------|
 |--- COMMIT ------------------>|
 |                        Đã commit
 X mất kết nối                   |
 |<-- phản hồi không tới --------|
~~~

Nếu **connection.commit()** ném SQLException do mạng, Java không biết chắc DBMS đã commit hay chưa. Một lần **rollback** sau đó không thể hủy transaction thực sự đã commit.

Thiết kế cho nghiệp vụ quan trọng nên:

1. Nhận **operation_id/idempotency key** ổn định cho một yêu cầu.
2. Lưu mã này cùng dữ liệu nghiệp vụ **trong một transaction** và có ràng buộc UNIQUE.
3. Sau lỗi COMMIT không rõ, đối soát theo mã trên **nguồn dữ liệu có thẩm quyền**.
4. Nếu bản ghi đã có và dữ liệu khớp thì trả lại kết quả; nếu dữ liệu không khớp thì báo xung đột.
5. Nếu chưa thấy dữ liệu, phải tính đến transaction cũ còn chạy hoặc replica bất đồng bộ bị trễ; không tự tạo mã mới để retry mù quáng.

**Reconnect chỉ tạo kết nối mới**, không hồi sinh transaction đã mất của connection cũ. Các side effect ngoài DB như email hoặc gọi cổng thanh toán không tự rollback theo JDBC transaction; có thể cần transactional outbox và giao thức idempotent.

## 11. Timeout, connection lỗi và tài nguyên

Một request Java có nhiều chặng chờ:

| Chặng | Giới hạn | Điều cần phân biệt |
|---|---|---|
| Pool acquisition | Chờ mượn Connection | Pool hết slot không chứng minh DB hỏng |
| Connect/login | Mở session TCP/TLS/xác thực | Không phải thời gian chạy SQL |
| JDBC Statement | **setQueryTimeout(seconds)** | Không thay mọi socket timeout |
| DBMS statement/lock | Chờ/thi hành câu SQL | Tùy DBMS có thể hủy statement/transaction |
| Socket/network | Chờ phản hồi | Kết quả phía server có thể chưa rõ |
| HTTP/gRPC | Deadline của request | Bao gồm chờ pool, query, mapping và retry |

Ví dụ:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement stmt = connection.prepareStatement(
             "SELECT id FROM accounts WHERE id = ?")) {
    stmt.setLong(1, accountId);
    stmt.setQueryTimeout(2); // đơn vị: giây
    try (ResultSet rows = stmt.executeQuery()) {
        // Đọc ResultSet...
    }
}
~~~

Không có bảo đảm rằng **setQueryTimeout(2)** sẽ hủy mọi chờ mạng đúng sau 2 giây; driver và DBMS có thể có hành vi khác nhau. Phối hợp với pool timeout, socket timeout và deadline API.

### 11.1. Connection leak

Đoạn sai:

~~~java
Connection connection = dataSource.getConnection();
PreparedStatement stmt =
        connection.prepareStatement("SELECT * FROM accounts");
ResultSet rows = stmt.executeQuery();
// Nếu có exception, có thể không trả tài nguyên về pool.
~~~

Dùng **try-with-resources** trong mọi đường thành công và lỗi. Không giữ Connection khi gọi HTTP service chậm, xử lý file lớn hoặc chờ người dùng. Với pool cạn, kiểm tra **active, idle, pending**, transaction mở lâu và thời gian giữ connection trước khi tăng pool size.

Một Connection cũng mang trạng thái transaction, isolation và session; không chia sẻ tùy tiện cùng một Connection giữa các thread trong singleton repository.

## 12. Hiệu năng JDBC: SQL, round trip và batch

JDBC chuyển SQL tới DBMS. Tốc độ thực tế phụ thuộc kế hoạch truy vấn, chỉ mục, số round trip, khóa, băng thông, kích thước kết quả và Java mapping.

### 12.1. N+1 query

~~~text
1 SELECT lấy danh sách 100 đơn hàng
100 SELECT lấy khách hàng của mỗi đơn
=> 101 lần truy vấn và trao đổi mạng
~~~

Cân nhắc **JOIN**, truy vấn theo tập ID hoặc batch fetching. Đo kích thước kết quả và kế hoạch thực thi để tránh đổi N+1 lấy một truy vấn trả quá nhiều dữ liệu.

### 12.2. PreparedStatement batch

~~~java
try (PreparedStatement stmt = connection.prepareStatement(
        "INSERT INTO accounts(id, owner_name, balance) VALUES (?, ?, ?)")) {
    for (AccountRow account : accountsToInsert) {
        stmt.setLong(1, account.id());
        stmt.setString(2, account.ownerName());
        stmt.setBigDecimal(3, account.balance());
        stmt.addBatch();
    }

    int[] counts = stmt.executeBatch();
    // Phân tích counts và lỗi BatchUpdateException khi cần.
}
~~~

Ví dụ giả định có các kiểu/danh sách **AccountRow**, **accountsToInsert** và Connection thuộc transaction phù hợp. **addBatch/executeBatch** có thể giảm round trip; driver có thể báo **BatchUpdateException** với số hàng xử lý trước khi lỗi. Không coi batch đã hoàn tất nếu chưa kiểm tra và commit transaction.

Batch quá lớn có thể làm tăng thời gian giữ khóa, Connection và bộ nhớ. Chọn batch size theo thực nghiệm, không dùng batch để thay ràng buộc dữ liệu.

### 12.3. Generated keys và driver differences

JDBC hỗ trợ **Statement.RETURN_GENERATED_KEYS**, nhưng mức hỗ trợ khác nhau theo driver. PostgreSQL có **INSERT ... RETURNING**. Không mặc định mọi DBMS trả generated key hay update counts theo cùng một cách.

### 12.4. Quan sát hiệu năng

Nên đo riêng **thời gian mượn Connection**, **thời gian thực thi SQL**, **số hàng trả về**, **số câu SQL mỗi request**, **thời gian transaction giữ Connection**. Nếu truy vấn chậm, xem execution plan và index trước khi chỉ tăng pool hoặc query timeout.

## 13. Bảo mật tại ranh giới JDBC

- **PreparedStatement với các giá trị do người dùng nhập**; whitelist tên cột/bảng và thứ tự sắp xếp khi phải tạo SQL động.
- **Tài khoản DB tối thiểu quyền**, tránh dùng superuser cho API thông thường.
- **Secret manager/biến môi trường phù hợp** để cung cấp credentials; không hardcode hoặc ghi password vào log.
- **TLS và xác minh chứng chỉ/hostname** theo hạ tầng triển khai.
- **Giới hạn số hàng, thời gian truy vấn và đồng thời** để tránh lạm dụng tài nguyên.
- **Kiểm soát quyền nghiệp vụ**: role DB của service không thay thế kiểm tra người dùng HTTP được xem hàng dữ liệu nào.
- **Log có trách nhiệm**: dùng correlation ID, SQLSTATE và tên thao tác; không log giá trị cá nhân hoặc dữ liệu nhạy cảm không cần thiết.

PreparedStatement giúp hạn chế SQL injection ở vị trí giá trị, nhưng không tự ngăn lộ dữ liệu nếu truy vấn thiếu điều kiện phân quyền.

## 14. JDBC trong Spring JDBC, JPA và Hibernate

### 14.1. Spring JdbcTemplate

~~~java
@Repository
public class SpringAccountRepository {
    private final JdbcTemplate jdbcTemplate;

    public SpringAccountRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public BigDecimal getBalance(long accountId) {
        return jdbcTemplate.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                BigDecimal.class,
                accountId);
    }
}
~~~

Đây là đoạn minh họa có các imports Spring và BigDecimal tương ứng. **JdbcTemplate** dùng DataSource và JDBC bên dưới, giúp giảm mã boilerplate liên quan đến Connection, Statement, ResultSet và ánh xạ SQLException. Khi không tìm thấy bản ghi, **queryForObject** có thể ném exception do Spring ánh xạ; cần xử lý đúng hợp đồng nghiệp vụ.

### 14.2. JPA/Hibernate

JPA làm việc với entity và persistence context. Hibernate là ORM thường sinh SQL và sử dụng JDBC driver/Connection bên dưới. ORM giúp quản lý entity lifecycle, dirty checking và quan hệ; nhưng không loại bỏ:

- **N+1 query** do cách fetch.
- Flush trước commit hoặc query.
- Khóa, transaction isolation và deadlock.
- Lỗi pool và SQL dialect.
- Nhu cầu quan sát SQL thật và execution plan.

### 14.3. Transaction do Spring quản lý

~~~java
@Service
public class PaymentService {
    private final PaymentRepository repository;

    public PaymentService(PaymentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void transfer(TransferCommand command) {
        repository.debit(command);
        repository.credit(command);
        repository.recordAudit(command);
    }
}
~~~

Các kiểu **PaymentRepository** và **TransferCommand** được xem là thành phần do ứng dụng tự định nghĩa. Khi dùng transaction manager của Spring, **không tự gọi commit/rollback hoặc setAutoCommit** trên Connection do framework sở hữu. Cần kiểm tra propagation, rollback rules và self-invocation/proxy của phương thức được đánh dấu Transactional.

## 15. Nên dùng JDBC trực tiếp khi nào?

| Nhu cầu | Cách tiếp cận phù hợp để cân nhắc |
|---|---|
| Học SQL/transaction, viết ứng dụng hoặc tool nhỏ | JDBC trực tiếp |
| Service cần kiểm soát SQL rõ ràng, ít entity phức tạp | Spring JDBC/JdbcTemplate hoặc SQL mapper |
| Domain nhiều entity, relationships và lifecycle | JPA/Hibernate khi đội ngũ hiểu ORM |
| Báo cáo SQL nâng cao, dữ liệu định dạng đặc thù | JDBC/native SQL nếu dễ kiểm soát hơn |
| Import/export lượng lớn | JDBC batch/streaming hoặc công cụ DB chuyên biệt |

Không có nguyên tắc **JDBC luôn nhanh hơn ORM**. SQL thực tế, cách fetch, số truy vấn, caching, batch và transaction thường ảnh hưởng hơn nhãn công nghệ. Quyết định theo khả năng bảo trì và số đo hiệu năng.

## 16. Kiểm thử và chẩn đoán JDBC

Một lớp persistence nên có integration test với DBMS gần production để kiểm tra:

1. **SELECT có/không có hàng**, mapping NULL/BigDecimal.
2. **PreparedStatement** với input chứa dấu nháy/ký tự đặc biệt.
3. Lỗi **PRIMARY KEY, UNIQUE, CHECK và FOREIGN KEY**.
4. **Rollback** khi bước thứ hai của nghiệp vụ nhiều bước thất bại.
5. Hai giao dịch đồng thời không phá bất biến.
6. Hành vi **40001/40P01**, retry toàn transaction có giới hạn.
7. Lỗi network hoặc COMMIT không rõ không tạo nghiệp vụ trùng.
8. Connection/Statement/ResultSet được đóng dù có lỗi.
9. Chỉ số **N+1**, độ trễ SQL và thời gian giữ Connection.

PostgreSQL hỗ trợ xem session:

~~~sql
SELECT state, COUNT(*) AS sessions
FROM pg_stat_activity
WHERE datname = current_database()
GROUP BY state;
~~~

Xem transaction mở lâu:

~~~sql
SELECT pid, state,
       now() - xact_start AS transaction_age,
       wait_event_type, wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Các truy vấn này chỉ là ảnh chụp ở một thời điểm và quyền xem còn phụ thuộc vai trò DB. Kết hợp metric pool **active/idle/pending/acquire duration** để phân biệt chờ connection với SQL chậm.

## 17. Những hiểu nhầm và lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Coi JDBC là ORM hoặc DBMS | Sai mô hình trách nhiệm | Phân biệt API, driver, SQL và server |
| DriverManager trên mọi request production | Mở nhiều phiên mới, khó giới hạn | DataSource/pool |
| Ghép input vào SQL | SQL injection | PreparedStatement |
| Quên đóng tài nguyên | Pool cạn, leak cursor/connection | try-with-resources |
| Trả ResultSet đã đóng connection | Không còn truy cập hàng an toàn | Map DTO trước khi đóng |
| Mỗi câu SQL tự commit trong nghiệp vụ nhiều bước | Dữ liệu ghi nửa chừng | Một transaction |
| Hai Connection cho một chuyển tiền | Không có atomicity chung | Cùng Connection |
| Không kiểm tra update count | Có thể commit nghiệp vụ sai | Kiểm tra từng bước |
| Bật autoCommit khi transaction chưa kết thúc | Có nguy cơ commit ngầm | Dọn transaction rõ ràng |
| Retry mọi SQLException | Khuếch đại tải, ghi trùng | Phân loại lỗi và idempotency |
| Coi COMMIT timeout là chưa commit | Có thể tạo bản ghi trùng | Operation ID/đối soát |
| Giữ Connection qua HTTP call chậm | Giữ khóa, cạn pool | Transaction ngắn |
| Dùng double cho số tiền | Sai số nhị phân | BigDecimal và quy tắc tiền tệ |

## 18. Bài tập tự kiểm tra

**Bài 1 — Vai trò JDBC.** Thành phần nào lập kế hoạch và thực thi SQL khi Java gọi executeQuery?

*Gợi ý:* DBMS; driver thực hiện giao tiếp và JDBC cung cấp interface phía Java.

**Bài 2 — DataSource.** Vì sao một web service không nên tự tạo Connection bằng DriverManager cho mọi request?

*Gợi ý:* chi phí tạo phiên và thiếu giới hạn/tái sử dụng kết nối; dùng DataSource có pool khi phù hợp.

**Bài 3 — Bind parameter.** Vì sao WHERE owner_name = ? với setString an toàn hơn nối trực tiếp user input?

*Gợi ý:* giá trị được truyền dưới dạng dữ liệu, không trở thành cú pháp SQL.

**Bài 4 — ResultSet.** Một method đóng Connection trước khi trả ResultSet. Thiết kế này có vấn đề gì?

*Gợi ý:* ResultSet cần tài nguyên đang mở; map DTO bên trong phạm vi try-with-resources.

**Bài 5 — Transaction.** Debit cập nhật đúng 1 hàng, credit cập nhật 0 hàng. Có được COMMIT không?

*Gợi ý:* không. Business invariant chưa đạt; rollback toàn transaction.

**Bài 6 — SQLSTATE.** Nhận 40001 sau transaction đã đọc và ghi. Có được retry chỉ câu UPDATE cuối?

*Gợi ý:* không; mở transaction mới, đọc lại và ra quyết định từ đầu.

**Bài 7 — COMMIT timeout.** Connection mất sau khi gửi COMMIT tạo đơn. Client định gửi lại với mã mới. Rủi ro là gì?

*Gợi ý:* đơn đầu có thể đã commit; phải đối soát operation ID cũ.

**Bài 8 — Hiệu năng.** API cần 100 đơn hàng và 100 khách hàng nhưng thực hiện 101 SELECT. Hướng tối ưu?

*Gợi ý:* giảm N+1 bằng JOIN/batch fetching, đo SQL plan và lượng dữ liệu.

**Bài 9 — Pool cạn.** DB vẫn khỏe nhưng getConnection() timeout nhiều. Kiểm tra gì?

*Gợi ý:* leak, transaction giữ lâu, số connection active/idle/pending, tổng pool toàn cụm.

## 19. Ghi nhớ và áp dụng

**JDBC là cầu nối chuẩn giữa Java và cơ sở dữ liệu quan hệ**: ứng dụng gọi JDBC API, driver trao đổi với DBMS, và DBMS thực thi SQL cùng các bảo đảm transaction/lưu trữ. Các công cụ cốt lõi là **DataSource/Connection**, **PreparedStatement**, **ResultSet**, **SQLException** và API commit/rollback.

Trong tầng persistence Java, hãy dùng SQL có tham số, map dữ liệu đúng kiểu, đóng tài nguyên có cấu trúc, kiểm tra affected rows và giữ transaction ngắn. Với lỗi, phân biệt ràng buộc nghiệp vụ, transaction bị hủy có thể retry và COMMIT chưa xác định kết quả. Dù dùng JDBC trực tiếp, Spring JDBC hay JPA/Hibernate, hiểu ranh giới này giúp xây dựng hệ thống **nhất quán, bền vững, bảo mật và vận hành hiệu quả**.

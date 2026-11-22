# Kiểm tra hỗ trợ giao dịch, batch và khóa sinh

## 1. Vì sao cần kiểm tra năng lực của JDBC driver và cơ sở dữ liệu?

Khi xây dựng ứng dụng Java dùng **JDBC** để truy cập cơ sở dữ liệu quan hệ, việc một API xuất hiện trong `java.sql` không có nghĩa là mọi tổ hợp **driver + hệ quản trị cơ sở dữ liệu + cấu hình kết nối** đều hỗ trợ giống nhau. Đây là vấn đề quan trọng khi lập trình các thao tác CRUD và những tính năng như:

- **Transaction:** thực hiện nhiều lệnh SQL theo một đơn vị thành công hoặc thất bại; dùng `commit()`, `rollback()` và mức cô lập.
- **Batch:** gửi nhiều bộ tham số cho một `PreparedStatement` bằng `addBatch()` và `executeBatch()` nhằm giảm chi phí thực thi/giao tiếp.
- **Khóa sinh (generated keys):** sau `INSERT`, lấy khóa chính do cơ sở dữ liệu tự tạo qua `getGeneratedKeys()` thay vì tự đoán ID.

JDBC có giao diện **`DatabaseMetaData`**, lấy từ `Connection.getMetaData()`, để hỏi driver/cơ sở dữ liệu về các đặc tính hỗ trợ. Ba phương thức trọng tâm:

```java
DatabaseMetaData metadata = connection.getMetaData();

boolean transactionSupported = metadata.supportsTransactions();
boolean batchSupported = metadata.supportsBatchUpdates();
boolean generatedKeysSupported = metadata.supportsGetGeneratedKeys();
```

Những giá trị này giúp chương trình **chọn đường xử lý phù hợp** trước khi thực hiện lệnh thay đổi dữ liệu. Ví dụ, nếu batch không được hỗ trợ, ứng dụng có thể dùng các lần gọi `executeUpdate()` riêng lẻ; nếu không hỗ trợ generated keys, cần cơ chế lấy ID phù hợp với DB hoặc báo rõ tính năng không khả dụng.

> **Giới hạn quan trọng:** `supports...()` là **thông tin năng lực do driver cung cấp**, không phải chứng nhận rằng mọi câu SQL, mọi bảng hoặc mọi chế độ kết nối đều hoạt động đúng ý định. Cần kiểm thử với driver, phiên bản database và kiểu bảng thực tế.

**Mục tiêu học tập:** biết khi nào nên truy vấn `DatabaseMetaData`; đọc và diễn giải ba cờ hỗ trợ; kiểm tra mức cô lập và các giới hạn transaction; chọn cách triển khai `PreparedStatement` cho batch và generated keys; kiểm tra số dòng bị ảnh hưởng và xử lý `SQLException` có transaction an toàn.

## 2. `DatabaseMetaData` lấy từ đâu?

Mỗi kết nối JDBC có thể cung cấp metadata về driver và DB đang được truy cập:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

// dataSource đã được cấu hình với driver và thông tin kết nối.
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData md = connection.getMetaData();

    String database = md.getDatabaseProductName();
    String databaseVersion = md.getDatabaseProductVersion();
    String driver = md.getDriverName();

    boolean transactions = md.supportsTransactions();
    boolean batches = md.supportsBatchUpdates();
    boolean generatedKeys = md.supportsGetGeneratedKeys();

    // Sử dụng các giá trị trên để chọn chính sách truy cập dữ liệu.
}
```

`DataSource` là nguồn cấp kết nối và thường được cấu hình với connection pool; `try-with-resources` bảo đảm `Connection.close()` được gọi khi xong, thường trả kết nối vào pool. Chỉ đọc metadata không yêu cầu thực thi DML.

| API | Nội dung trả về | Cách sử dụng |
|---|---|---|
| `Connection.getMetaData()` | `DatabaseMetaData` | Điểm bắt đầu kiểm tra năng lực |
| `supportsTransactions()` | `boolean` | Kiểm tra DB/driver có báo hỗ trợ transaction hay không |
| `supportsBatchUpdates()` | `boolean` | Kiểm tra khả năng thực thi batch JDBC |
| `supportsGetGeneratedKeys()` | `boolean` | Kiểm tra khả năng trả khóa tự sinh qua API JDBC |
| `getDatabaseProductName()` | `String` | Xác định hệ quản trị để lựa chọn cách viết SQL phù hợp |
| `getDatabaseProductVersion()` | `String` | Biết phiên bản DB khi phân tích khác biệt tính năng |
| `getDriverName()`, `getDriverVersion()` | `String` | Biết driver đang dùng để tái hiện lỗi tương thích |

Không ghi nguyên `metadata.getURL()` hoặc thông tin `metadata.getUserName()` vào log chung: URL có thể chứa thông tin kết nối và tham số nhạy cảm, còn tên tài khoản DB thường không cần thiết cho chẩn đoán thông thường.

### Đọc metadata có phải là thao tác “cố định một lần”?

Không nên giả định toàn bộ môi trường luôn bất biến. Driver có thể thay đổi khi triển khai, cấu hình connection pool có thể chuyển đến một DB khác, và khả năng hỗ trợ có thể phụ thuộc chế độ hoặc cấu hình cụ thể. Có thể kiểm tra năng lực khi khởi tạo dịch vụ và lưu vào đối tượng cấu hình cho cùng nguồn kết nối, nhưng cần đánh giá lại khi thay driver/DB hoặc khi kiểm thử trên môi trường khác.

Đừng gọi nhiều phương thức metadata trong mỗi vòng lặp xử lý hàng dữ liệu. Một số truy vấn metadata cần giao tiếp với DB; nên tách kiểm tra năng lực ra khỏi đường xử lý nóng nếu đặc tính môi trường đã được xác định.

## 3. Xây dựng bản chụp năng lực JDBC có kiểu rõ ràng

Đoạn mã sau dùng Java 17+ với `record` để gom các năng lực cần thiết vào một kết quả tự chứa. Nó **chỉ đọc**, không thay đổi transaction hay dữ liệu.

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class JdbcCapabilityInspector {
    private JdbcCapabilityInspector() {}

    public record Capabilities(
            String database,
            String driver,
            boolean transactions,
            boolean batchUpdates,
            boolean generatedKeys,
            int defaultIsolation,
            int connectionIsolation,
            boolean readCommitted,
            boolean serializable,
            boolean savepoints) {}

    public static Capabilities inspect(DataSource dataSource)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData md = connection.getMetaData();
            boolean tx = md.supportsTransactions();

            return new Capabilities(
                    md.getDatabaseProductName(),
                    md.getDriverName(),
                    tx,
                    md.supportsBatchUpdates(),
                    md.supportsGetGeneratedKeys(),
                    md.getDefaultTransactionIsolation(),
                    connection.getTransactionIsolation(),
                    tx && md.supportsTransactionIsolationLevel(
                            Connection.TRANSACTION_READ_COMMITTED),
                    tx && md.supportsTransactionIsolationLevel(
                            Connection.TRANSACTION_SERIALIZABLE),
                    tx && md.supportsSavepoints()
            );
        }
    }
}
```

Giá trị `defaultIsolation` là mức cô lập mặc định do metadata báo; `connectionIsolation` là mức cô lập của **kết nối đang được cấp**. Hai giá trị có thể khác nhau nếu pool hoặc framework thay đổi cấu hình. Các cờ `readCommitted`, `serializable` và `savepoints` giúp kiểm tra thêm những khả năng có liên quan đến transaction.

Ví dụ sử dụng:

```java
JdbcCapabilityInspector.Capabilities capabilities =
        JdbcCapabilityInspector.inspect(dataSource);

if (!capabilities.transactions()) {
    throw new IllegalStateException(
            "Database does not report transaction support");
}

if (capabilities.batchUpdates()) {
    // Có thể xem xét dùng addBatch()/executeBatch().
}

if (capabilities.generatedKeys()) {
    // Có thể xem xét RETURN_GENERATED_KEYS/getGeneratedKeys().
}
```

`Capabilities` không lưu credential hoặc tham số SQL. Khi hiển thị thông tin driver/DB cho trang chẩn đoán nội bộ, chỉ cấp quyền phù hợp và tránh trả chi tiết môi trường ra API công khai.

## 4. Kiểm tra transaction: `supportsTransactions()`

```java
boolean supported = connection.getMetaData().supportsTransactions();
```

Nếu `supported == false`, ứng dụng không nên phụ thuộc vào khả năng commit/rollback nhiều lệnh như một transaction hoàn chỉnh. Với một nghiệp vụ bắt buộc bảo đảm **tất cả cùng thành công hoặc tất cả bị hủy**, cách đúng là từ chối triển khai đường ghi đó trên cấu hình hiện tại hoặc chuyển sang cơ sở dữ liệu/cơ chế transaction phù hợp; không âm thầm chạy các lệnh độc lập rồi tuyên bố đã có tính nguyên tử.

Nếu `supported == true`, ứng dụng có thể tiếp tục kiểm tra **mức cô lập**, hỗ trợ savepoint và khả năng transaction với loại statement dự kiến. Điều này không tự bật transaction: `autoCommit` là trạng thái của **`Connection`**, cần được quản lý riêng.

### Phân biệt hỗ trợ transaction với `autoCommit`

```java
boolean canTransact = connection.getMetaData().supportsTransactions();
boolean autoCommitNow = connection.getAutoCommit();
int isolationNow = connection.getTransactionIsolation();
```

| Điều kiện | Ý nghĩa |
|---|---|
| `supportsTransactions() == true`, `getAutoCommit() == true` | DB/driver báo hỗ trợ transaction, nhưng connection đang tự commit theo quy tắc JDBC. |
| `supportsTransactions() == true`, `getAutoCommit() == false` | Connection đang cho phép kiểm soát ranh giới commit/rollback theo cấu hình hiện hành. |
| `supportsTransactions() == false` | Không được coi `rollback()` là bảo đảm cho nghiệp vụ nhiều lệnh. |
| `getTransactionIsolation() == TRANSACTION_NONE` | Kết nối báo không hỗ trợ transaction isolation; cần xem lại giả định transaction. |

Đừng gọi `setAutoCommit(false)` trong lúc chỉ **kiểm tra metadata**. Đây là thao tác thay đổi trạng thái kết nối, có thể can thiệp transaction do framework quản lý. Chỉ thay đổi trên connection mà thành phần hiện tại thực sự sở hữu và điều phối transaction.

### Kiểm tra mức cô lập và savepoint

```java
DatabaseMetaData md = connection.getMetaData();

boolean readCommittedSupported =
        md.supportsTransactionIsolationLevel(
                Connection.TRANSACTION_READ_COMMITTED);

boolean serializableSupported =
        md.supportsTransactionIsolationLevel(
                Connection.TRANSACTION_SERIALIZABLE);

boolean savepointsSupported = md.supportsSavepoints();
```

Các mức JDBC phổ biến gồm `TRANSACTION_READ_UNCOMMITTED`, `TRANSACTION_READ_COMMITTED`, `TRANSACTION_REPEATABLE_READ` và `TRANSACTION_SERIALIZABLE`. `TRANSACTION_NONE` biểu thị không hỗ trợ transaction. Hỗ trợ một mức không có nghĩa mọi DB thực hiện hành vi khóa và snapshot giống nhau; cần hiểu mô hình isolation của hệ quản trị thực tế.

`supportsSavepoints()` kiểm tra khả năng tạo `Savepoint` để rollback một phần transaction. Nếu trả `false`, logic nghiệp vụ không được giả định rằng `connection.setSavepoint()` sẽ chạy được. Trường hợp không hỗ trợ rollback một phần cần thiết kế lại ranh giới nghiệp vụ hoặc rollback toàn transaction.

### Transaction với DDL không giống DML

Nhiều hệ quản trị có quy tắc riêng cho `CREATE TABLE`, `ALTER TABLE` hoặc các lệnh thay đổi schema. JDBC còn có metadata:

```java
boolean ddlAndDmlTogether =
        md.supportsDataDefinitionAndDataManipulationTransactions();
boolean onlyDmlInTransaction =
        md.supportsDataManipulationTransactionsOnly();
boolean ddlCausesCommit =
        md.dataDefinitionCausesTransactionCommit();
boolean ddlIgnoredInTransactions =
        md.dataDefinitionIgnoredInTransactions();
```

Các cờ này giúp đặt câu hỏi đúng về DDL trong transaction. Không suy từ `supportsTransactions() == true` rằng một lệnh `ALTER TABLE` luôn rollback được. Cần kiểm thử DDL/transaction theo DB cụ thể; triển khai migration schema không nên trộn tùy tiện với transaction nghiệp vụ.

## 5. Ví dụ transaction JDBC dùng khi đã kiểm tra hỗ trợ

Giả sử chuyển tiền giữa hai tài khoản. Bảng mẫu:

```sql
CREATE TABLE accounts (
    id      BIGINT PRIMARY KEY,
    balance DECIMAL(15, 2) NOT NULL
);
```

Hai lệnh `UPDATE` phải cùng thành công:

```sql
UPDATE accounts
SET balance = balance - ?
WHERE id = ? AND balance >= ?;

UPDATE accounts
SET balance = balance + ?
WHERE id = ?;
```

Ví dụ Java sau kiểm tra khả năng transaction, sử dụng một `Connection` duy nhất và điều khiển commit/rollback theo số dòng bị ảnh hưởng. Nó giả định connection mới cấp có `autoCommit = true` và chưa thuộc transaction do framework quản lý.

```java
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
        if (fromId <= 0 || toId <= 0 || fromId == toId ||
                amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        try (Connection connection = dataSource.getConnection()) {
            if (!connection.getMetaData().supportsTransactions()) {
                throw new SQLException("Transactions are not supported");
            }
            if (!connection.getAutoCommit()) {
                throw new SQLException("Expected an unmanaged connection");
            }

            connection.setAutoCommit(false);
            boolean finished = false;
            try {
                String debit = """
                        UPDATE accounts
                        SET balance = balance - ?
                        WHERE id = ? AND balance >= ?
                        """;
                try (PreparedStatement ps =
                             connection.prepareStatement(debit)) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, fromId);
                    ps.setBigDecimal(3, amount);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException(
                                "Source missing or insufficient balance");
                    }
                }

                String credit = """
                        UPDATE accounts
                        SET balance = balance + ?
                        WHERE id = ?
                        """;
                try (PreparedStatement ps =
                             connection.prepareStatement(credit)) {
                    ps.setBigDecimal(1, amount);
                    ps.setLong(2, toId);
                    if (ps.executeUpdate() != 1) {
                        throw new SQLException("Destination missing");
                    }
                }

                connection.commit();
                finished = true;
            } catch (SQLException | RuntimeException error) {
                try {
                    connection.rollback();
                    finished = true;
                } catch (SQLException rollbackError) {
                    error.addSuppressed(rollbackError);
                }
                throw error;
            } finally {
                // Bật lại auto-commit chỉ khi transaction đã kết thúc.
                // Nếu rollback thất bại, không vô tình commit phần dang dở.
                if (finished) {
                    connection.setAutoCommit(true);
                }
            }
        }
    }
}
```

Các điểm cần hiểu:

- `supportsTransactions()` quyết định ứng dụng có thể **thử** transaction theo hợp đồng driver hay không; tính đúng của hai lệnh còn phụ thuộc SQL và ràng buộc bảng.
- `BigDecimal` giữ độ chính xác của tiền so với `double`.
- `executeUpdate() == 1` đảm bảo câu lệnh đã tác động đúng một hàng theo điều kiện được đặt trong `WHERE`. Điều kiện đủ số dư nằm trong chính SQL giảm tiền.
- Nếu trừ tiền thành công nhưng cộng tiền không tác động hàng nào, `rollback()` hoàn tác cả phần giảm trên cùng connection.
- Chỉ khi `commit()` thành công mới thông báo giao dịch hoàn tất. Nếu kết nối mất trong lúc commit, kết quả thực tế có thể không rõ; với nghiệp vụ tiền phải có khóa chống thực thi lặp, đối soát và chiến lược xử lý riêng.

Với kết nối do transaction manager quản lý, không tự tắt/bật auto-commit hoặc gọi commit theo cách trên. Tầng transaction của ứng dụng cần sở hữu ranh giới commit/rollback.

## 6. Kiểm tra batch: `supportsBatchUpdates()`

```java
boolean canBatch = connection.getMetaData().supportsBatchUpdates();
```

Nếu `true`, driver báo hỗ trợ cơ chế JDBC batch:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE products SET price = ? WHERE id = ?")) {
    ps.setBigDecimal(1, new BigDecimal("12.50"));
    ps.setLong(2, 101L);
    ps.addBatch();

    ps.setBigDecimal(1, new BigDecimal("14.00"));
    ps.setLong(2, 102L);
    ps.addBatch();

    int[] counts = ps.executeBatch();
}
```

Với `PreparedStatement`, cùng một SQL được thực thi với nhiều bộ giá trị. Tùy driver/DB, batch có thể giảm số lần giao tiếp hoặc cải thiện hiệu năng; bản thân cờ `supportsBatchUpdates()` **không bảo đảm sẽ nhanh hơn** với mọi kích thước batch và câu SQL.

### Không giả định mọi update count là số dương

`executeBatch()` trả một mảng `int[]` theo thứ tự các lệnh đã thêm. Phần tử có thể là số không âm hoặc hai hằng:

| Giá trị | Nghĩa trong batch JDBC | Phản ứng |
|---|---|---|
| `0` | Driver báo không có hàng bị tác động | Với thao tác mong chờ đúng một hàng, xem là không đạt điều kiện |
| `1` hoặc số dương khác | Driver báo số hàng tác động | Kiểm tra theo số dòng kỳ vọng |
| `Statement.SUCCESS_NO_INFO` (`-2`) | Lệnh thành công nhưng không có số hàng cụ thể | Không thể xác nhận “đúng một hàng” chỉ bằng count |
| `Statement.EXECUTE_FAILED` (`-3`) | Lệnh bị lỗi trong batch khi driver tiếp tục sau lỗi | Xử lý batch thất bại; rollback nếu cần tất cả cùng thành công |

Khi một lệnh thất bại, driver có thể ném `BatchUpdateException` và cung cấp các count đã ghi nhận qua `getUpdateCounts()`. Một số driver dừng ngay tại lỗi, driver khác tiếp tục các lệnh sau. Không suy từ độ dài mảng rằng mọi lệnh đã được commit.

### Fallback khi không hỗ trợ batch

Hàm sau **nhận connection do tầng transaction cung cấp**, để cùng một transaction có thể sử dụng batch nếu được hỗ trợ hoặc các lần `executeUpdate()` riêng lẻ nếu không.

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.List;

record PriceChange(long productId, BigDecimal newPrice) {}

static int[] updatePrices(Connection connection, List<PriceChange> changes)
        throws SQLException {
    String sql = "UPDATE products SET price = ? WHERE id = ?";

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        if (connection.getMetaData().supportsBatchUpdates()) {
            for (PriceChange change : changes) {
                ps.setBigDecimal(1, change.newPrice());
                ps.setLong(2, change.productId());
                ps.addBatch();
            }
            int[] counts = ps.executeBatch();

            if (counts.length != changes.size()) {
                throw new SQLException("Unexpected batch result length");
            }
            for (int count : counts) {
                if (count == Statement.EXECUTE_FAILED || count == 0) {
                    throw new SQLException("Batch update not fully applied");
                }
                if (count < 0 && count != Statement.SUCCESS_NO_INFO) {
                    throw new SQLException("Unknown batch update count");
                }
            }
            return counts;
        }

        // Driver không hỗ trợ batch: thực thi từng bộ tham số.
        int[] counts = new int[changes.size()];
        for (int i = 0; i < changes.size(); i++) {
            PriceChange change = changes.get(i);
            ps.setBigDecimal(1, change.newPrice());
            ps.setLong(2, change.productId());
            counts[i] = ps.executeUpdate();
            if (counts[i] != 1) {
                throw new SQLException("Price update did not affect one row");
            }
        }
        return counts;
    }
}
```

Ở nhánh batch, ví dụ xem `SUCCESS_NO_INFO` là đủ để biết **lệnh thành công** khi mục tiêu chỉ yêu cầu thực thi thành công. Nếu nghiệp vụ bắt buộc **chính xác một hàng cho mỗi ID**, `SUCCESS_NO_INFO` **chưa đủ bằng chứng**; thay vì chấp nhận nhánh đó, hãy chọn cách thực thi riêng từng câu lệnh hoặc kiểm tra một cơ chế xác nhận đáng tin cậy khác.

Điểm quan trọng về transaction: phương thức `updatePrices` **không gọi commit/rollback**. Tầng gọi cần mở một transaction trên **cùng connection** nếu toàn bộ danh sách phải đồng thời thành công hoặc cùng thất bại. Nếu phương thức ném exception giữa batch hoặc vòng lặp, tầng gọi phải rollback. Batch không tự bảo đảm tính nguyên tử.

Nếu ứng dụng cần biết số hàng lớn hơn kiểu `int`, JDBC còn có `executeLargeBatch()` trả `long[]` trên driver hỗ trợ.

## 7. Kiểm tra khóa sinh: `supportsGetGeneratedKeys()`

```java
boolean canReturnKeys =
        connection.getMetaData().supportsGetGeneratedKeys();
```

Giả sử bảng có cột `id` tự sinh:

```sql
-- Ví dụ lược đồ, cú pháp IDENTITY có thể khác giữa các RDBMS:
CREATE TABLE customers (
    id   BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(120) NOT NULL
);
```

Với driver hỗ trợ, cách lấy khóa sinh bằng JDBC là:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public final class CustomerInsert {
    private CustomerInsert() {}

    // Connection do tầng transaction sở hữu, được truyền vào phương thức.
    public static long insertCustomer(Connection connection, String name)
            throws SQLException {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Customer name is required");
        }
        if (!connection.getMetaData().supportsGetGeneratedKeys()) {
            throw new SQLException(
                    "Generated keys are unavailable for this JDBC driver");
        }

        String sql = "INSERT INTO customers (name) VALUES (?)";
        try (PreparedStatement ps = connection.prepareStatement(
                sql, Statement.RETURN_GENERATED_KEYS)) {

            ps.setString(1, name);
            if (ps.executeUpdate() != 1) {
                throw new SQLException("Expected exactly one inserted customer");
            }

            try (ResultSet keys = ps.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException("No generated key was returned");
                }
                long newId = keys.getLong(1);
                if (keys.wasNull()) {
                    throw new SQLException("Generated key was NULL");
                }
                return newId;
            }
        }
    }
}
```

**Phân biệt ba bước:**

1. `supportsGetGeneratedKeys()`: hỏi driver có báo hỗ trợ API lấy khóa sinh hay không.
2. `prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)`: yêu cầu statement giữ khóa tự sinh khi thực thi.
3. `getGeneratedKeys()`: sau `executeUpdate()`, lấy `ResultSet` chứa các khóa mà driver trả. Đây **không phải** update count; `executeUpdate() == 1` không cho biết giá trị ID.

Với ví dụ bảng `customers` có ID kiểu `BIGINT`, `keys.getLong(1)` đọc khóa ở cột đầu tiên của result set khóa sinh. Cách trình bày cột, kiểu khóa và số hàng trả về phụ thuộc driver/DB. Nếu khóa là UUID hoặc kiểu khác, không dùng `getLong()`.

### Cờ hỗ trợ true vẫn có thể không trả khóa mong muốn

`supportsGetGeneratedKeys() == true` không có nghĩa bất kỳ bảng và câu `INSERT` nào cũng có khóa do database sinh. Chẳng hạn:

- Cột ID được ứng dụng tự gán nên không có khóa mới để trả.
- SQL có `INSERT ... SELECT`, multi-row insert, trigger hoặc biểu thức DB riêng mà driver xử lý khác với `INSERT ... VALUES (?)` đơn giản.
- Driver hỗ trợ API chung nhưng không trả giá trị mong muốn với kiểu khóa hoặc cấu hình hiện tại.
- Sau `INSERT` vào nhiều hàng hoặc `executeBatch()`, số khóa và thứ tự khóa được trả cần được kiểm chứng với driver; không gán ID theo vị trí một cách mù quáng.

Nếu driver báo không hỗ trợ hoặc `getGeneratedKeys()` không trả khóa, ứng dụng cần **chiến lược DB-specific đã được kiểm chứng**, ví dụ câu `INSERT ... RETURNING ...` trên hệ quản trị hỗ trợ, hoặc cơ chế ID do ứng dụng cấp phát. Không dùng `SELECT MAX(id)` để suy ID vừa chèn: câu lệnh đó có thể lấy ID của transaction khác trong môi trường đồng thời.

Ví dụ `CustomerInsert.insertCustomer(...)` nhận `Connection` từ tầng gọi và **không tự commit**. Nếu việc trả ID là điều kiện bắt buộc của nghiệp vụ, tầng gọi nên sở hữu một transaction: dùng connection đó để chèn và đọc khóa, **rollback khi thiếu khóa** rồi chỉ `commit()` sau khi có khóa hợp lệ. Nếu chạy trong chế độ auto-commit, `INSERT` có thể đã được commit ngay cả khi `getGeneratedKeys()` không trả hàng và code ném `SQLException`; việc ném ngoại lệ không tự hoàn tác bản ghi đã chèn.

Một khóa sinh được đọc trước commit **không chứng minh giao dịch đã commit**. Một số cơ chế cấp phát ID không hoàn tác bộ đếm khi transaction rollback nên có thể có khoảng trống ID; đây thường là hành vi bình thường.

## 8. Chọn đường thực thi dựa trên metadata

Để sử dụng các cờ hỗ trợ đúng mục đích, có thể thiết lập một ma trận quyết định:

| Năng lực | Metadata báo hỗ trợ | Metadata báo không hỗ trợ | Kiểm chứng bổ sung |
|---|---|---|---|
| Transaction | Dùng một connection và `commit()/rollback()` khi sở hữu transaction | Từ chối nghiệp vụ bắt buộc nguyên tử hoặc thay cấu hình | Thử rollback các DML thực tế; kiểm tra storage engine, isolation, DDL |
| Batch | Có thể dùng `addBatch()/executeBatch()` | Thực thi từng lệnh `executeUpdate()`, giữ cùng transaction nếu cần | Đọc count, `BatchUpdateException`; đo hiệu năng |
| Generated keys | Dùng `RETURN_GENERATED_KEYS` và `getGeneratedKeys()` | Dùng kỹ thuật lấy ID theo DB hoặc ID do ứng dụng cấp | Thử kiểu ID, insert một/nhiều hàng, batch và rollback |

Không nên viết logic theo tên DB kiểu “MySQL luôn hỗ trợ X, PostgreSQL luôn hỗ trợ Y” mà bỏ qua phiên bản driver, phiên bản server và đường SQL cụ thể. Metadata là bước phát hiện ban đầu; kiểm thử tích hợp khẳng định đặc tính mà nghiệp vụ thực sự cần.

### Phân biệt “không hỗ trợ” với “không hoạt động trên một trường hợp”

- `supportsBatchUpdates() == false`: theo thông tin driver, không nên dùng API batch như cơ chế dựa vào đó; có thể chọn fallback ngay.
- `supportsBatchUpdates() == true` nhưng một câu batch thất bại: đó có thể là lỗi ràng buộc, timeout hoặc hạn chế của loại statement; không tự suy toàn bộ batch không được hỗ trợ.
- `supportsGetGeneratedKeys() == true` nhưng `keys.next() == false`: API có thể được hỗ trợ nhưng statement/bảng không trả khóa; phải xử lý thiếu kết quả theo hợp đồng.
- `supportsTransactions() == true` nhưng `rollback()` không phục hồi dữ liệu: cần xem DB, loại bảng, thay đổi DDL, kết nối và hành vi transaction; chỉ đọc cờ không đủ.

## 9. Thử nghiệm tích hợp để xác minh metadata

Trên database thử nghiệm với phiên bản driver dự định dùng khi triển khai:

### Tình huống A — Transaction

1. Gọi `supportsTransactions()` và ghi nhận kết quả; kiểm tra `getAutoCommit()` và `getTransactionIsolation()` của kết nối.
2. Với DB báo hỗ trợ, tạo dữ liệu thử trong bảng có hỗ trợ transaction.
3. Mở một connection, gọi `setAutoCommit(false)`, thực hiện `INSERT`/`UPDATE`, kiểm tra thay đổi thấy được trên **cùng connection**.
4. Gọi `rollback()`, sau đó truy vấn lại để xác nhận các thay đổi chưa commit bị hoàn tác.
5. Thực hiện lại và `commit()` để xác nhận khác biệt; không chạy thử nghiệm này trên dữ liệu thật.

### Tình huống B — Batch

1. Gọi `supportsBatchUpdates()`.
2. Với driver báo hỗ trợ, thêm nhiều bộ tham số bằng `addBatch()` rồi `executeBatch()`.
3. Kiểm tra `counts.length`, từng phần tử `0`/số dương/`SUCCESS_NO_INFO`/`EXECUTE_FAILED`, và hành vi `BatchUpdateException`.
4. Với trường hợp lỗi, nếu đang trong transaction do test quản lý, rollback toàn bộ và xác nhận dữ liệu không bị ghi một phần.
5. So sánh với việc gọi `executeUpdate()` riêng từng lệnh trên cùng lượng dữ liệu mẫu; đo thời gian thực tế trước khi quyết định batch size.

### Tình huống C — Generated keys

1. Gọi `supportsGetGeneratedKeys()`.
2. Trên bảng có ID do DB tự sinh, thực hiện `INSERT` một hàng với `RETURN_GENERATED_KEYS`.
3. Kiểm tra `executeUpdate() == 1` và result set `getGeneratedKeys()` có ID hợp lệ; truy vấn bảng để đối chiếu.
4. Thử khi transaction rollback và quan sát hàng không còn dù số ID có thể không được tái sử dụng.
5. Nếu hệ thống thực sự cần insert nhiều hàng hoặc batch, kiểm tra số lượng, thứ tự và kiểu khóa mà driver trả trong **đúng kiểu statement đó**.

### Tình huống D — Tính di động

Chạy cùng bộ kiểm tra với các môi trường có driver/phiên bản server khác nhau. Lưu kết quả vào bảng tương thích của dự án (không chứa credential) để lựa chọn fallback và xác định các tính năng được phép bật.

## 10. Lỗi triển khai thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Có `Connection.commit()` trong API nên mặc định DB hỗ trợ transaction | Nghiệp vụ nhiều lệnh có thể không nguyên tử | Kiểm tra `supportsTransactions()` và thử rollback DML |
| `supportsTransactions() == true` nên cho rằng connection đã tắt auto-commit | Mỗi lệnh có thể tự commit | Kiểm tra `getAutoCommit()` và để transaction owner điều khiển |
| Đổi isolation hoặc auto-commit khi chỉ đọc metadata | Ảnh hưởng transaction của pool/framework | Giữ kiểm tra năng lực ở chế độ đọc |
| `supportsBatchUpdates() == true` nên mọi count phải bằng `1` | Driver có thể trả `SUCCESS_NO_INFO` | Diễn giải các hằng JDBC, chọn chính sách kiểm chứng phù hợp |
| Chạy batch mà không có transaction nhưng muốn “tất cả hoặc không gì” | Một phần lệnh có thể đã được commit | Dùng transaction cùng connection khi hỗ trợ |
| `supportsGetGeneratedKeys() == true` nên không kiểm tra `keys.next()` | Có thể không có khóa trả về | Kiểm tra result set và kiểu khóa thực tế |
| Dùng `SELECT MAX(id)` lấy khóa vừa sinh | Có thể lấy ID của transaction khác | Dùng `getGeneratedKeys()` hoặc kỹ thuật an toàn của DB |
| Lấy khóa sinh trước commit rồi tuyên bố đã tạo dữ liệu bền vững | Transaction có thể rollback | Xác nhận commit theo hợp đồng ứng dụng |
| Tắt kiểm tra metadata vì đã biết tên DB | Driver/config/phiên bản có thể thay đổi | Kiểm tra khả năng ở cấu hình triển khai, có test tích hợp |
| Ghi toàn bộ `DatabaseMetaData` hoặc JDBC URL vào log | Có thể lộ chi tiết kết nối | Chỉ ghi trường cần thiết và đã được kiểm soát |

## 11. Ghi nhớ

`DatabaseMetaData` là công cụ JDBC để **phát hiện khả năng của driver và cơ sở dữ liệu** trước khi lựa chọn cách thực thi SQL. Ba kiểm tra quan trọng là:

```java
md.supportsTransactions();
md.supportsBatchUpdates();
md.supportsGetGeneratedKeys();
```

Kết quả giúp chọn transaction với `commit()/rollback()`, batch với `addBatch()/executeBatch()` và lấy khóa sinh với `Statement.RETURN_GENERATED_KEYS` cùng `getGeneratedKeys()`. Nhưng **cờ hỗ trợ không thay thế kiểm thử tích hợp**: ứng dụng vẫn phải kiểm tra `autoCommit`, isolation, update count, trạng thái transaction, tính chất của bảng, kiểu khóa và sai khác giữa driver. Dùng `DataSource` để lấy kết nối, `PreparedStatement` để tham số hóa SQL và `ResultSet` để đọc khóa sinh; xác nhận đầy đủ kết quả rồi mới coi thao tác nghiệp vụ hoàn tất.

# Kiểm tra năng lực hỗ trợ trước khi sử dụng tính năng tùy chọn trong JDBC

## 1. Vấn đề: cùng API JDBC, khả năng hỗ trợ có thể khác nhau

**JDBC (Java Database Connectivity)** cung cấp các giao diện tiêu chuẩn để ứng dụng Java kết nối và thao tác với cơ sở dữ liệu quan hệ. Tuy nhiên, việc một phương thức xuất hiện trong `java.sql` hoặc `javax.sql` **không đồng nghĩa mọi JDBC driver và mọi hệ quản trị cơ sở dữ liệu (DBMS) đều hỗ trợ phương thức đó**.

Ví dụ, ứng dụng có thể muốn:

- Dùng **savepoint** để chỉ hoàn tác một phần transaction.
- Gửi **batch update** để giảm số lần trao đổi với database.
- Nhận **khóa tự sinh** ngay sau khi thêm bản ghi.
- Tạo **ResultSet có thể di chuyển ngược**, hoặc cập nhật qua con trỏ.
- Gọi **stored procedure** hay đọc nhiều tập kết quả trong một lần gọi.
- Chỉ định **transaction isolation level** cụ thể.

Các khả năng này phụ thuộc vào sự kết hợp giữa API JDBC, phiên bản driver, cơ sở dữ liệu, phiên bản máy chủ và đôi khi cả cấu hình phiên kết nối. Chẳng hạn, một driver hỗ trợ `ResultSet.TYPE_FORWARD_ONLY` chưa chắc hỗ trợ `ResultSet.TYPE_SCROLL_INSENSITIVE`; một DBMS có transaction chưa chắc cho phép mọi mức isolation.

**Mục tiêu bài học:** Biết xác định tính năng nào là tùy chọn, dùng metadata để tra cứu khả năng hỗ trợ, kiểm tra lại hành vi thật, xây dựng nhánh dự phòng có kiểm soát và báo lỗi rõ ràng khi tính năng bắt buộc không khả dụng.

## 2. Ba tầng cần kiểm tra

Khi sử dụng một tính năng JDBC, hãy phân biệt ba tầng sau:

| Tầng | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **JDBC API** | Phiên bản Java mà ứng dụng dùng có công bố phương thức/constant này không? | `Connection.setSavepoint()` tồn tại trong API JDBC. |
| **JDBC driver** | Driver cụ thể có triển khai khả năng này không? | `DatabaseMetaData.supportsSavepoints()` báo khả năng hỗ trợ savepoint. |
| **DBMS + môi trường kết nối** | Server và cấu hình phiên hiện tại có thực hiện được thao tác theo yêu cầu không? | Savepoint không thể dùng hợp lệ khi connection đang ở chế độ auto-commit. |

~~~mermaid
flowchart TD
    A[Ứng dụng muốn dùng tính năng JDBC] --> B{API có phương thức?}
    B -- Không --> X[Chọn API khác hoặc nâng JDK]
    B -- Có --> C[Đọc DatabaseMetaData của Connection]
    C --> D{Driver báo hỗ trợ?}
    D -- Không / chưa xác định --> E{Tính năng bắt buộc?}
    E -- Có --> F[Fail fast với thông báo rõ]
    E -- Không --> G[Chọn phương án dự phòng phù hợp]
    D -- Có --> H[Thực thi và kiểm tra hành vi thật]
    H --> I{Hoạt động đúng?}
    I -- Có --> J[Sử dụng tính năng]
    I -- Không --> K[Phân loại lỗi và xử lý an toàn]
    K --> E
~~~

Từ sơ đồ này rút ra hai nguyên tắc:

1. **Metadata là bước sàng lọc**, không phải giấy bảo đảm tính năng sẽ hoạt động trong mọi tình huống. Hành vi thực tế vẫn có thể phụ thuộc loại câu lệnh, quyền truy cập, trạng thái transaction hoặc giới hạn DBMS.
2. **Một phương án dự phòng phải giữ đúng nghiệp vụ.** Nếu nghiệp vụ cần khả năng rollback một phần transaction, không thể âm thầm thay bằng rollback toàn bộ hoặc bỏ rollback rồi xem như tương đương.

## 3. Công cụ chính: `DatabaseMetaData`

Đối tượng `DatabaseMetaData` mô tả khả năng của driver và database mà một `Connection` đang kết nối đến. Lấy nó bằng:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    System.out.println("Database: " + meta.getDatabaseProductName());
    System.out.println("Database version: " + meta.getDatabaseProductVersion());
    System.out.println("Driver: " + meta.getDriverName());
    System.out.println("Driver version: " + meta.getDriverVersion());
    System.out.println("JDBC level: " + meta.getJDBCMajorVersion()
            + "." + meta.getJDBCMinorVersion());
}
~~~

Trong ví dụ này, `dataSource` là `javax.sql.DataSource` đã được cấu hình trước và `Connection` tự đóng khi ra khỏi khối `try-with-resources`.

**Không suy ra hỗ trợ tính năng chỉ từ tên hoặc phiên bản driver.** `getJDBCMajorVersion()` / `getJDBCMinorVersion()` cho biết mức API JDBC mà driver công bố, nhưng không nói rằng mọi tính năng tùy chọn đều được triển khai. Để tra cứu một khả năng cụ thể, cần gọi đúng phương thức `supports...()` tương ứng.

### 3.1. Các phép kiểm tra phổ biến

| Nhóm khả năng | Phương thức `DatabaseMetaData` | Ý nghĩa khi trả `true` |
| --- | --- | --- |
| Transaction | `supportsTransactions()` | Driver/DBMS công bố hỗ trợ transaction. |
| Isolation level | `supportsTransactionIsolationLevel(Connection.TRANSACTION_REPEATABLE_READ)` | Công bố hỗ trợ mức isolation chỉ định. |
| Savepoint | `supportsSavepoints()` | Công bố hỗ trợ JDBC savepoint. |
| Batch update | `supportsBatchUpdates()` | Công bố hỗ trợ thực thi batch. |
| Khóa tự sinh | `supportsGetGeneratedKeys()` | Công bố hỗ trợ lấy generated keys bằng JDBC. |
| Con trỏ di chuyển ngược | `supportsResultSetType(ResultSet.TYPE_SCROLL_INSENSITIVE)` | Công bố hỗ trợ kiểu ResultSet được yêu cầu. |
| Con trỏ có khả năng cập nhật | `supportsResultSetConcurrency(type, ResultSet.CONCUR_UPDATABLE)` | Công bố hỗ trợ cặp **type + concurrency** đó. |
| Giữ ResultSet khi commit | `supportsResultSetHoldability(ResultSet.HOLD_CURSORS_OVER_COMMIT)` | Công bố hỗ trợ holdability được yêu cầu. |
| Stored procedure | `supportsStoredProcedures()` | Công bố hỗ trợ gọi stored procedure. |
| Named parameter cho callable | `supportsNamedParameters()` | Công bố hỗ trợ gọi các phương thức `CallableStatement` dùng tên tham số. |
| Nhiều ResultSet | `supportsMultipleResultSets()` | Công bố một câu lệnh có thể trả nhiều ResultSet. |
| Nhiều ResultSet còn mở | `supportsMultipleOpenResults()` | Công bố hỗ trợ nhiều ResultSet mở đồng thời từ một lệnh. |
| Statement pooling | `supportsStatementPooling()` | Công bố hỗ trợ statement pooling ở cấp driver/DBMS. |
| REF CURSOR | `supportsRefCursors()` | Công bố hỗ trợ JDBC REF CURSOR (API có từ JDBC 4.2). |

**Cần đọc kỹ chữ “supports”:** phương thức này cung cấp thông tin từ driver về khả năng của hệ thống, không phải phép thử trực tiếp trên từng câu SQL. Nếu `supportsResultSetType(TYPE_SCROLL_INSENSITIVE)` trả `true`, ứng dụng vẫn nên kiểm tra kiểu thực tế bằng `ResultSet.getType()` sau khi tạo statement.

**Phân biệt:** `supportsStatementPooling()` nói về khả năng **tái sử dụng statement**, không chứng minh có **connection pool**. Connection pool như HikariCP quản lý `Connection` và có tập chỉ số riêng.

### 3.2. Kiểm tra khả năng phải theo đúng cặp tham số

Một kiểm tra thiếu thường gặp:

~~~java
// Chưa đủ để kết luận có thể tạo scrollable + updatable ResultSet.
boolean scrollable = meta.supportsResultSetType(
        ResultSet.TYPE_SCROLL_INSENSITIVE);
~~~

Nếu cần đồng thời khả năng cuộn và cập nhật, kiểm tra tiếp:

~~~java
int type = ResultSet.TYPE_SCROLL_INSENSITIVE;
int concurrency = ResultSet.CONCUR_UPDATABLE;

boolean supported = meta.supportsResultSetType(type)
        && meta.supportsResultSetConcurrency(type, concurrency);
~~~

Tương tự, việc database có transaction không chứng minh nó hỗ trợ **mọi** isolation level. Hãy gọi `supportsTransactionIsolationLevel(level)` với đúng mức mà nghiệp vụ yêu cầu.

## 4. Phân biệt `false`, lỗi và “chưa xác định”

Trong JDBC, nhiều phương thức metadata có thể trả `false` để nói **không hỗ trợ**. Một số phương thức cũng có thể ném `SQLException` khi không truy vấn được metadata; một số driver có thể dùng `SQLFeatureNotSupportedException` khi một phương thức cụ thể không được triển khai.

Không nên gom tất cả vào một `catch (SQLException) { return false; }`: làm vậy có thể biến lỗi mất kết nối, sai quyền hoặc lỗi server thành “tính năng không được hỗ trợ”.

| Kết quả | Diễn giải | Hành động |
| --- | --- | --- |
| `true` | Driver công bố khả năng có sẵn. | Cho phép thử tính năng, sau đó kiểm tra hiệu lực/hành vi. |
| `false` | Driver công bố không hỗ trợ. | Dùng dự phòng đã thiết kế hoặc dừng nếu bắt buộc. |
| `SQLFeatureNotSupportedException` | Driver không hỗ trợ phương thức đang gọi, hoặc báo thao tác không khả dụng. | Ghi là chưa xác minh/không khả dụng theo ngữ cảnh, không thử mù quáng. |
| `SQLException` khác | Có vấn đề khi tra cứu hay thực thi, chẳng hạn kết nối hoặc quyền. | Báo lỗi và xử lý theo chính sách retry/điều tra; không tự kết luận driver thiếu tính năng. |

Một cách biểu diễn hữu ích là ba trạng thái:

~~~java
enum Support {
    YES, NO, UNKNOWN
}
~~~

**`UNKNOWN` không phải `YES`.** Nếu tính năng bắt buộc cho tính đúng đắn của nghiệp vụ, ứng dụng nên dừng có thông báo thay vì âm thầm sử dụng khi chưa có bằng chứng hỗ trợ.

## 5. Ví dụ đầy đủ: lập báo cáo khả năng JDBC

Ví dụ sau dùng Java 17 trở lên. Nó kiểm tra một tập tính năng thực tế trên đúng `DataSource` của ứng dụng, bảo toàn kết nối và không thay đổi dữ liệu. Một số tính năng có thể không có trong phiên bản JDBC cũ; ví dụ được biên dịch bằng JDK hiện đại có đầy đủ các phương thức sử dụng bên dưới.

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.SQLFeatureNotSupportedException;
import javax.sql.DataSource;

public final class JdbcCapabilityInspector {
    private JdbcCapabilityInspector() {}

    public enum Support {
        YES, NO, UNKNOWN
    }

    @FunctionalInterface
    private interface SqlBooleanCheck {
        boolean check() throws SQLException;
    }

    private static Support inspect(SqlBooleanCheck check)
            throws SQLException {
        try {
            return check.check() ? Support.YES : Support.NO;
        } catch (SQLFeatureNotSupportedException ex) {
            return Support.UNKNOWN;
        }
    }

    public record Capabilities(
            String database,
            String databaseVersion,
            String driver,
            String driverVersion,
            Support transactions,
            Support readCommitted,
            Support savepoints,
            Support batch,
            Support generatedKeys,
            Support scrollInsensitive,
            Support scrollUpdatable,
            Support storedProcedures,
            Support multipleResultSets) {}

    public static Capabilities read(DataSource dataSource)
            throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            DatabaseMetaData meta = connection.getMetaData();

            int scrollType = ResultSet.TYPE_SCROLL_INSENSITIVE;
            int update = ResultSet.CONCUR_UPDATABLE;

            return new Capabilities(
                    meta.getDatabaseProductName(),
                    meta.getDatabaseProductVersion(),
                    meta.getDriverName(),
                    meta.getDriverVersion(),
                    inspect(meta::supportsTransactions),
                    inspect(() -> meta.supportsTransactionIsolationLevel(
                            Connection.TRANSACTION_READ_COMMITTED)),
                    inspect(meta::supportsSavepoints),
                    inspect(meta::supportsBatchUpdates),
                    inspect(meta::supportsGetGeneratedKeys),
                    inspect(() -> meta.supportsResultSetType(scrollType)),
                    inspect(() -> meta.supportsResultSetConcurrency(
                            scrollType, update)),
                    inspect(meta::supportsStoredProcedures),
                    inspect(meta::supportsMultipleResultSets));
        }
    }
}
~~~

Sử dụng sau khi `DataSource` đã được cấu hình:

~~~java
JdbcCapabilityInspector.Capabilities capabilities =
        JdbcCapabilityInspector.read(dataSource);

System.out.println(capabilities);

// Tính năng bắt buộc phải có bằng chứng rõ ràng.
if (capabilities.savepoints() != JdbcCapabilityInspector.Support.YES) {
    throw new IllegalStateException(
            "Chức năng này yêu cầu JDBC savepoint được hỗ trợ");
}
~~~

Đoạn mã cố ý:

- Giữ `DataSource` là đầu vào, để kiểm tra đúng driver và DBMS của ứng dụng thay vì tạo một connection đến database khác.
- Không “nuốt” mọi `SQLException`: các lỗi ngoài `SQLFeatureNotSupportedException` vẫn được ném lên cho tầng gọi xử lý.
- Chỉ trả về **khả năng tự công bố**. Không làm các thao tác kiểm thử savepoint, DML hoặc stored procedure khi đọc metadata.
- Ghi nhận phiên bản DBMS/driver cùng kết quả: báo cáo chỉ có ý nghĩa với môi trường và phiên bản mà connection đó thực sự sử dụng.

**Giới hạn quan trọng:** `Capabilities` được lấy từ **một connection**. Nếu pool định tuyến tới nhiều phiên bản DBMS, có failover, database proxy hoặc cấu hình tenant khác nhau, không được xem kết quả này là bất biến toàn hệ thống.

## 6. Ví dụ: kiểm tra scrollable `ResultSet` và xác minh kiểu thực tế

Giả sử giao diện cần đọc một tập kết quả và đôi khi muốn dùng `ResultSet.previous()`. Có hai chính sách:

- **Yêu cầu bắt buộc:** Không hỗ trợ cuộn thì dừng và báo rõ khả năng bị thiếu.
- **Tối ưu tùy chọn:** Có hỗ trợ thì dùng cursor cuộn; không có thì dùng `TYPE_FORWARD_ONLY` và xử lý tuần tự, miễn nghiệp vụ vẫn đúng.

Ví dụ tạo statement và kiểm tra kết quả thực tế:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static void readUsers(Connection connection) throws SQLException {
    DatabaseMetaData meta = connection.getMetaData();
    boolean wantsScroll = meta.supportsResultSetType(
            ResultSet.TYPE_SCROLL_INSENSITIVE);

    int requestedType = wantsScroll
            ? ResultSet.TYPE_SCROLL_INSENSITIVE
            : ResultSet.TYPE_FORWARD_ONLY;

    try (PreparedStatement ps = connection.prepareStatement(
            "SELECT id, name FROM app_user ORDER BY id",
            requestedType,
            ResultSet.CONCUR_READ_ONLY);
         ResultSet rs = ps.executeQuery()) {

        int actualType = rs.getType();
        System.out.println("Requested type = " + requestedType);
        System.out.println("Actual type = " + actualType);

        while (rs.next()) {
            long id = rs.getLong("id");
            String name = rs.getString("name");
            System.out.println(id + ": " + name);
        }

        // Chỉ gọi previous() nếu logic thật sự cần và kiểu hiện tại cho phép.
        // Với TYPE_FORWARD_ONLY, phương thức previous() không được bảo đảm.
    }
}
~~~

Trường hợp driver **hạ cấp yêu cầu** (chẳng hạn chuyển cursor cuộn sang forward-only), đừng dựa vào `requestedType` để gọi `previous()`. Đọc `rs.getType()`, `rs.getConcurrency()` và, khi cần chẩn đoán, `ps.getWarnings()` để biết loại ResultSet thực tế.

**Không thử `previous()` trên cursor chỉ hỗ trợ đi tới** rồi bắt exception như chiến lược vận hành thường xuyên. Nếu nghiệp vụ chỉ cần xử lý tất cả hàng một lần, chọn forward-only từ đầu thường rõ ràng và phù hợp hơn.

### 6.1. Holdability là một khả năng riêng

`ResultSet.HOLD_CURSORS_OVER_COMMIT` yêu cầu con trỏ được giữ mở qua commit. `ResultSet.CLOSE_CURSORS_AT_COMMIT` cho phép con trỏ bị đóng khi commit.

~~~java
boolean holdable = meta.supportsResultSetHoldability(
        ResultSet.HOLD_CURSORS_OVER_COMMIT);
~~~

Nếu cần hành vi đó, ngoài kiểm tra metadata còn nên xác minh `connection.getHoldability()` hoặc `rs.getHoldability()` khi dùng. Hạn chế transaction giữ cursor lâu và hiểu rõ chi phí tài nguyên tại server.

## 7. Ví dụ: kiểm tra savepoint trước khi rollback một phần

Savepoint cho phép quay về một mốc bên trong transaction, nhưng chỉ khi cả driver và server hỗ trợ. Thêm vào đó, việc tạo savepoint khi `autoCommit=true` là không phù hợp: mỗi câu lệnh có thể được commit riêng và không có transaction dài để rollback một phần.

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.Savepoint;
import java.sql.SQLException;

public static void useSavepoint(
        Connection connection) throws SQLException {

    DatabaseMetaData meta = connection.getMetaData();

    if (!meta.supportsTransactions()) {
        throw new IllegalStateException("Database không hỗ trợ transaction");
    }
    if (!meta.supportsSavepoints()) {
        throw new IllegalStateException("Driver không hỗ trợ savepoint");
    }
    if (connection.getAutoCommit()) {
        throw new IllegalStateException(
                "Cần bắt đầu transaction (autoCommit=false) trước");
    }

    Savepoint checkpoint = connection.setSavepoint("before_optional_step");
    try {
        performOptionalStep(connection);
    } catch (SQLException ex) {
        connection.rollback(checkpoint);
        // Lỗi nghiệp vụ có thể cần được báo lên ngay cả khi đã rollback.
        throw ex;
    } finally {
        // Một số driver/DBMS có giới hạn khi release savepoint.
        // Chỉ release theo chính sách và trạng thái transaction phù hợp.
    }
}
~~~

Hàm `performOptionalStep(Connection)` biểu thị thao tác nghiệp vụ được gọi từ ứng dụng; nó chưa được định nghĩa trong đoạn trích để người học tập trung vào **cổng kiểm tra capability**. Phương thức ở trên giả định **tầng gọi đang sở hữu transaction** và quyết định commit/rollback toàn bộ; không tự `commit()` trong helper.

**Dự phòng đúng nghĩa là gì?** Nếu savepoint chỉ để giảm chi phí khi một bước phụ thất bại, có thể thiết kế lại thành transaction độc lập, hoặc bỏ bước phụ khi yêu cầu cho phép. Nếu savepoint cần thiết để bảo đảm toàn vẹn dữ liệu, hãy **báo không tương thích**. Rollback cả transaction rồi tiếp tục như thể chỉ rollback một phần là hành vi khác.

Lưu ý: sau một số lỗi SQL, DBMS có thể đưa toàn bộ transaction vào trạng thái lỗi (ví dụ cần rollback trước khi tiếp tục). Kiểm tra khả năng savepoint không đủ để bảo đảm mọi lỗi có thể được phục hồi tại cùng một mốc.

## 8. Ví dụ: batch update và generated keys

### 8.1. Batch update

Trước khi gọi `addBatch()` / `executeBatch()` trong một luồng yêu cầu batch, kiểm tra:

~~~java
DatabaseMetaData meta = connection.getMetaData();
boolean supportsBatch = meta.supportsBatchUpdates();
~~~

Nếu batch là tối ưu tùy chọn, nhánh dự phòng có thể gọi `executeUpdate()` lần lượt trên cùng `PreparedStatement`. Hai phương án chỉ tương đương về nghiệp vụ khi bạn đã xác định rõ transaction boundary, thứ tự cập nhật, cơ chế bắt lỗi và yêu cầu atomicity.

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE inventory SET quantity = ? WHERE item_id = ?")) {
    if (supportsBatch) {
        for (InventoryChange change : changes) {
            ps.setInt(1, change.quantity());
            ps.setLong(2, change.itemId());
            ps.addBatch();
        }
        int[] counts = ps.executeBatch();
        // Kiểm tra số phần tử và các giá trị SUCCESS_NO_INFO /
        // EXECUTE_FAILED theo contract của driver và ứng dụng.
    } else {
        for (InventoryChange change : changes) {
            ps.setInt(1, change.quantity());
            ps.setLong(2, change.itemId());
            ps.executeUpdate();
        }
    }
}
~~~

`InventoryChange` và `changes` là các kiểu/dữ liệu mẫu do ứng dụng cung cấp. Ví dụ minh họa cấu trúc nhánh tính năng; để dùng trong production cần bao transaction và kiểm tra kết quả cập nhật theo yêu cầu nghiệp vụ.

**Không tự động chạy lại toàn bộ batch khi có `BatchUpdateException`**. Một số phần tử có thể đã thành công; chạy lại mù quáng có thể tạo thao tác trùng. Xem `getUpdateCounts()`, trạng thái transaction và tính idempotent trước khi retry.

### 8.2. Generated keys

Với insert cần trả ID được tạo bởi database:

~~~java
if (!meta.supportsGetGeneratedKeys()) {
    throw new IllegalStateException(
            "Yêu cầu lấy generated key, driver không hỗ trợ");
}

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO app_user(name) VALUES (?)",
        Statement.RETURN_GENERATED_KEYS)) {
    ps.setString(1, "Lan");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException(
                    "INSERT đã chạy nhưng không có generated key được trả");
        }
        long newId = keys.getLong(1);
        System.out.println("newId=" + newId);
    }
}
~~~

Bên cạnh `supportsGetGeneratedKeys()`, phải xác định rõ **câu INSERT, cấu trúc bảng và DBMS có thực sự sinh khóa**. Một số DBMS có cơ chế trả khóa khác như cú pháp `RETURNING`, `OUTPUT` hoặc SQL riêng; nếu chọn cách đó thì cần kiểm chứng và không mặc định thay thế được trên mọi hệ quản trị.

## 9. Stored procedure, named parameters và nhiều ResultSet

Các phép kiểm tra sau liên quan các yêu cầu khác nhau:

~~~java
boolean procedures = meta.supportsStoredProcedures();
boolean namedCallableParams = meta.supportsNamedParameters();
boolean multipleResults = meta.supportsMultipleResultSets();
boolean multipleOpen = meta.supportsMultipleOpenResults();
~~~

- `supportsStoredProcedures()` nói đến khả năng gọi thủ tục lưu trữ, nhưng không khẳng định mọi kiểu tham số/kiểu trả về đều dùng được.
- `supportsNamedParameters()` liên quan việc dùng **tên tham số trong `CallableStatement`**. Nó không nói rằng mọi SQL text đều hỗ trợ cú pháp `:name` (JDBC chuẩn dùng dấu hỏi `?` cho placeholder positional).
- `supportsMultipleResultSets()` cho biết một lần thực thi có thể trả về nhiều `ResultSet` theo cơ chế hỗ trợ.
- `supportsMultipleOpenResults()` là yêu cầu mạnh hơn: có thể **giữ nhiều ResultSet mở cùng lúc**. Đừng suy hai khả năng là một.

Ví dụ, nếu chỉ cần đọc lần lượt từng kết quả từ `CallableStatement`, ứng dụng vẫn cần xử lý kết hợp `getResultSet()`, `getUpdateCount()` và `getMoreResults()` theo đúng trạng thái trả về, vì một thủ tục có thể xen kẽ result set và update count. Nếu cần `getMoreResults(Statement.KEEP_CURRENT_RESULT)` để giữ kết quả cũ mở, kiểm tra `supportsMultipleOpenResults()` trước.

Đối với REF CURSOR, kiểm tra `supportsRefCursors()` trên driver/JDK có API hỗ trợ, rồi dùng cách khai báo tham số và đọc kết quả theo tài liệu DBMS đích.

## 10. Tính năng không có công tắc `supports...()` tương ứng

Không phải phương thức nào của `Connection`, `Statement` hay `ResultSet` cũng có một phương thức `DatabaseMetaData.supports...()` dành riêng. Ví dụ:

| Khả năng | Cách xác định phù hợp |
| --- | --- |
| `Connection.setNetworkTimeout(...)` | Đọc tài liệu driver và kiểm tra trên kết nối thử; có thể ném `SQLFeatureNotSupportedException`. |
| `Connection.createArrayOf(...)` | Kiểm tra kiểu SQL cụ thể và tài liệu driver; thử ở môi trường kiểm thử, vì kiểu mảng phụ thuộc DBMS. |
| `Connection.createSQLXML()` | Đối chiếu hỗ trợ SQLXML của driver/server; thực hiện thử với dữ liệu test. |
| `ResultSet.getObject(index, SomeClass.class)` | Kiểm tra mapping kiểu Java–SQL của driver đối với cột cần đọc. |
| `PreparedStatement.setQueryTimeout(...)` | Xác minh cách driver/server áp dụng timeout cho truy vấn thực tế. |
| `Connection.beginRequest()` / `endRequest()`, API sharding | Đối chiếu JDK/JDBC 4.3, driver và tài liệu provider; không mặc định có hiệu lực trên mọi DBMS. |

`DatabaseMetaData.getTypeInfo()` có thể giúp tìm kiểu dữ liệu SQL mà driver công bố; `ResultSetMetaData` mô tả các cột của một kết quả cụ thể; `ParameterMetaData` có thể mô tả placeholder của `PreparedStatement`. Đây là **những nguồn thông tin bổ sung**, nhưng một mapping thực tế vẫn cần được kiểm thử với kiểu dữ liệu, driver và câu SQL thật.

Đặc biệt với `ParameterMetaData`, một số driver không xác định được kiểu tham số khi câu SQL chưa được chuẩn bị hoàn toàn phía server. Không buộc ứng dụng phụ thuộc tuyệt đối vào metadata đó nếu dữ liệu/SQL đã xác định rõ kiểu và có cách `setXxx` thích hợp.

### 10.1. Kiểm thử tính năng thiếu metadata bằng một probe an toàn

Nếu không có phương thức `supports...()` riêng, hãy:

1. Xác minh phiên bản driver, DBMS và tài liệu tính năng.
2. Chạy một phép thử **trên connection dành riêng** ở môi trường kiểm thử hoặc lúc khởi tạo có kiểm soát.
3. Dùng đúng quyền hạn và dữ liệu test; hạn chế DDL/DML khi chỉ cần kiểm thử tính năng đọc hoặc cấu hình.
4. Bắt `SQLFeatureNotSupportedException` riêng và không che lỗi `SQLException` khác.
5. Dùng kết quả để chọn đường đi tại runtime; không chạy probe tốn kém trên từng hàng/record.

Ví dụ, khi `setNetworkTimeout` không được hỗ trợ, cần chọn cơ chế giới hạn thời gian thay thế ở tầng ứng dụng, driver hoặc network. Một timeout của `Statement` không nhất thiết thay được timeout kết nối mạng; phải xét loại sự cố cần giới hạn.

## 11. Kiểm tra metadata rồi vẫn phải xác minh kết quả thực tế

### 11.1. ResultSet và statement có thể bị hạ cấp

Bạn có thể yêu cầu `TYPE_SCROLL_INSENSITIVE` và `CONCUR_UPDATABLE`, nhưng driver/DBMS có thể chỉ tạo được một kiểu thấp hơn. Kiểm tra:

~~~java
try (Statement st = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_UPDATABLE);
     ResultSet rs = st.executeQuery(
             "SELECT id, name FROM app_user")) {
    System.out.println("type: " + rs.getType());
    System.out.println("concurrency: " + rs.getConcurrency());
}
~~~

Một phép thử đúng nghiệp vụ phải xác minh cả **thao tác sẽ dùng**: cursor di chuyển, cập nhật hàng có thực hiện được, commit ảnh hưởng thế nào, timeout có hiệu lực không. Không chỉ in hai con số rồi suy luận tất cả thao tác đều hợp lệ.

### 11.2. Isolation và transaction phụ thuộc ngữ cảnh

~~~java
DatabaseMetaData meta = connection.getMetaData();
int expected = Connection.TRANSACTION_REPEATABLE_READ;

if (!meta.supportsTransactions()
        || !meta.supportsTransactionIsolationLevel(expected)) {
    throw new IllegalStateException(
            "Không hỗ trợ transaction/isolation level yêu cầu");
}

connection.setTransactionIsolation(expected);

int actual = connection.getTransactionIsolation();
if (actual != expected) {
    throw new IllegalStateException(
            "Isolation level thực tế không như yêu cầu");
}
~~~

Đặt isolation level nên thực hiện ở **điểm sở hữu connection/transaction**, trước khi transaction bắt đầu theo quy tắc DBMS; không tùy tiện đổi mức cô lập giữa transaction đang chạy. Nếu dùng pool hoặc framework transaction, cũng phải tuân theo cách framework quản lý và khôi phục trạng thái connection. `getTransactionIsolation()` giúp phát hiện mức đang khai báo, nhưng vẫn cần kiểm thử hiện tượng concurrent transaction nếu nghiệp vụ phụ thuộc ngữ nghĩa đặc biệt của DBMS.

### 11.3. Khả năng có thể phụ thuộc câu SQL và quyền truy cập

Một driver có thể hỗ trợ generated keys, stored procedure và batch nói chung, nhưng một lệnh cụ thể vẫn thất bại do:

- Bảng không có cột tự sinh khóa hoặc cú pháp INSERT không trả khóa.
- Account thiếu quyền gọi stored procedure hay truy cập bảng.
- DBMS cấm một thao tác trong kiểu transaction hiện tại.
- Schema hoặc kiểu dữ liệu không tương thích với cách mapping được chọn.
- Driver yêu cầu cấu hình fetch, holdability, server-side cursor hoặc chế độ auto-commit đặc biệt.

Cần phân biệt **unsupported feature** với **SQL syntax error**, **permission error** và **connection failure**. Mỗi loại đòi hỏi cách xử lý khác nhau.

## 12. Thiết kế fallback và xử lý lỗi an toàn

Một tính năng tùy chọn cần có **chính sách rõ ràng trước khi chạy**. Có thể chia thành:

| Loại yêu cầu | Ví dụ | Chính sách |
| --- | --- | --- |
| Bắt buộc về tính đúng đắn | Cần savepoint để bảo toàn ranh giới rollback cụ thể | `supportsSavepoints() != true` ⇒ fail fast; triển khai nơi khác hoặc thay đổi thiết kế. |
| Tối ưu hiệu năng | Batch update thay cho cập nhật từng hàng | Khi không hỗ trợ, dùng cập nhật tuần tự nếu vẫn giữ được transaction và kết quả nghiệp vụ. |
| Tiện ích API | Dùng scrollable ResultSet để duyệt lại hàng | Nếu nghiệp vụ cho phép, thay bằng forward-only và buffer ở tầng ứng dụng có giới hạn. |
| Phụ thuộc DBMS | Lấy generated keys, REF CURSOR, named callable parameters | Xác minh với DBMS cụ thể; nếu cần, dùng SQL hoặc API thay thế đã kiểm thử. |
| Không có tương đương an toàn | Tính năng transaction hoặc xác thực bắt buộc | Báo không tương thích, không tự bỏ qua thao tác. |

### 12.1. Xử lý `SQLFeatureNotSupportedException`

`SQLFeatureNotSupportedException` là một subtype của `SQLException`, được dùng để báo tính năng JDBC không được hỗ trợ. Có thể bắt cụ thể để giải thích lỗi:

~~~java
try {
    connection.setNetworkTimeout(executor, 5_000);
} catch (SQLFeatureNotSupportedException ex) {
    // Không giả định đã đặt được timeout.
    // Thực hiện phương án xử lý đã định nghĩa hoặc fail fast.
    throw new IllegalStateException(
            "Driver không hỗ trợ network timeout theo JDBC", ex);
}
~~~

Ở đây `executor` phải là một `java.util.concurrent.Executor` do ứng dụng quản lý. Ví dụ chỉ minh họa nhánh xử lý; không tạo thread pool trong mỗi request chỉ để thử timeout.

Một số driver có thể ném `SQLException` chung cùng mã SQLState/exception của hãng thay vì `SQLFeatureNotSupportedException`. Hãy đọc tài liệu driver và log `SQLState`/vendor error code khi điều tra. **Không dựa duy nhất vào chuỗi thông báo lỗi để chọn fallback**, vì thông báo có thể thay đổi theo phiên bản/ngôn ngữ.

### 12.2. Khi nào không tự động fallback?

Không fallback sau khi đã có **side effect không chắc chắn**. Ví dụ: batch thất bại giữa chừng, driver báo mất kết nối ngay sau insert, hoặc transaction bị lỗi trạng thái. Trong các trường hợp này, làm lại câu SQL một lần nữa có thể tạo duplicate.

Để giữ tính đúng đắn, cần một trong các cơ chế: transaction rollback có bảo đảm, yêu cầu idempotent, khóa nghiệp vụ duy nhất, kiểm tra trạng thái sau lỗi hoặc quy trình retry ở tầng trên được thiết kế rõ ràng.

## 13. Thời điểm kiểm tra và chiến lược cache kết quả

Không nên gọi hàng loạt phương thức metadata trong mỗi truy vấn hoặc mỗi dòng dữ liệu. Kiểm tra khả năng có thể cần trao đổi với server; việc lặp lại làm tăng độ trễ và tải.

Một chiến lược thường dùng:

1. **Khi ứng dụng khởi động:** Tạo/nhận `DataSource`, lấy một connection, đọc capability cần thiết và xác minh các tính năng **bắt buộc**. Nếu thiếu, báo lỗi cấu hình rõ ràng.
2. **Ở đầu transaction yêu cầu hành vi đặc biệt:** Xác minh trạng thái thực tế như `autoCommit`, isolation, kiểu ResultSet, tùy tình huống.
3. **Khi chạy:** Quan sát lỗi bất ngờ; không xem metadata snapshot là bất biến trước failover hay nâng cấp.
4. **Sau khi đổi driver, DBMS, cấu hình pool hoặc route:** Chạy lại kiểm tra và kiểm thử tích hợp.

Có thể cache kết quả **theo cấu hình đích cụ thể**, gồm DBMS, phiên bản server, phiên bản driver và đặc điểm tuyến kết nối. Nếu một `DataSource` có thể đến nhiều server/tenant với năng lực khác nhau, cần kiểm tra từng nhóm đích hoặc áp dụng tập khả năng giao nhau an toàn.

Không log mật khẩu, token hoặc connection URL đầy đủ nếu URL có thông tin bí mật. Nên ghi: tên DBMS, phiên bản driver, tên logical datasource, tên tính năng và trạng thái hỗ trợ.

## 14. Quy trình thực hành: đánh giá khả năng trước khi thêm tính năng mới

Giả sử một dịch vụ Java muốn tối ưu cập nhật bằng batch, dùng savepoint để bỏ qua thao tác phụ không quan trọng và lấy generated keys từ INSERT.

**Bước 1 — Xác định bản chất yêu cầu.** Batch là tối ưu; savepoint phục vụ hành vi rollback một phần; generated keys có thể là đầu vào bắt buộc cho bước tiếp theo. Chỉ định trước các trường hợp được fallback.

**Bước 2 — Lấy metadata từ cùng `DataSource` dùng trong production.** Đọc `supportsBatchUpdates()`, `supportsSavepoints()`, `supportsGetGeneratedKeys()` và `supportsTransactions()`. Ghi tên driver/DBMS/version.

**Bước 3 — Chạy trên môi trường thử nghiệm tương đương.** Với bảng test, kiểm tra `executeBatch()`, `setSavepoint()/rollback(savepoint)` và `getGeneratedKeys()`. Test cả thành công và lỗi có chủ đích, rồi kiểm tra nội dung bảng sau rollback.

**Bước 4 — Đối chiếu điều kiện thực tế.** Kiểm tra `autoCommit=false` trong transaction, generated key phù hợp schema, `BatchUpdateException` được xử lý và statement không bị hạ cấp âm thầm.

**Bước 5 — Chốt đường thực thi.** Khi batch không khả dụng, ứng dụng có thể cập nhật từng hàng trong transaction phù hợp. Khi savepoint không khả dụng mà nghiệp vụ bắt buộc rollback một phần, báo không tương thích. Khi generated keys không khả dụng, chỉ dùng cách thay thế nếu có chiến lược lấy khóa đáng tin cậy cho DBMS đó.

**Bước 6 — Quan sát và duy trì.** Lưu báo cáo khả năng vào log khởi động/health diagnostic đã lọc bí mật và chạy test lại sau khi nâng cấp driver, Java hoặc database.

Ví dụ bảng báo cáo:

| Tính năng | Metadata | Kiểm thử trên DBMS đích | Quyết định |
| --- | --- | --- | --- |
| Batch update | YES | PASS, kết quả và transaction đúng | Bật batch. |
| Savepoint | NO | Không chạy vì metadata đã báo không hỗ trợ | Dừng tính năng cần rollback một phần. |
| Generated keys | YES | PASS với bảng có identity/auto-generated key | Dùng `getGeneratedKeys()`. |
| Scrollable ResultSet | UNKNOWN | Không cần trong nghiệp vụ | Dùng forward-only. |

Các kết quả **YES/NO/UNKNOWN/PASS** trong bảng chỉ là minh họa; môi trường thật phải được đo trực tiếp.

## 15. Những lỗi thiết kế phổ biến

- **Giả định dùng JDBC 4.x là được mọi tính năng.** Mức API không thay cho `supports...()` và kiểm thử thực tế.
- **Dùng `supportsResultSetType()` để suy ra `CONCUR_UPDATABLE`.** Concurrency phụ thuộc cặp type + concurrency và cả câu SELECT.
- **Kiểm tra hỗ trợ rồi bỏ qua trạng thái transaction.** Savepoint, isolation và holdability còn phụ thuộc `autoCommit`, transaction và cấu hình DB.
- **Xem `SQLException` nào cũng là “không hỗ trợ”.** Mất mạng, hết kết nối và thiếu quyền là lỗi cần điều tra, không phải lý do để đi đường fallback.
- **Thử lỗi bằng DML ngay trên production.** Capability probe có thể tạo dữ liệu, giữ khóa hoặc tiêu hao kết nối; ưu tiên kiểm tra read-only và test ở môi trường riêng.
- **Bắt lỗi rồi chạy lại DML không kiểm soát.** Sau batch/insert thất bại có thể đã có thao tác được áp dụng; retry cần dựa vào transaction và idempotency.
- **Cache capability mãi mãi dù pool đổi server.** Sau failover hoặc nâng cấp, năng lực có thể thay đổi; cần chiến lược làm mới và kiểm thử.
- **Không đọc lại trạng thái thực tế.** Metadata là lời công bố; kiểu ResultSet, isolation và hành vi kết quả cần được xác minh tại nơi sử dụng.

## 16. Checklist trước khi sử dụng một tính năng JDBC tùy chọn

- [ ] Ghi rõ tên tính năng, DBMS và mục tiêu nghiệp vụ: **bắt buộc** hay chỉ **tối ưu**.
- [ ] Xác minh API tồn tại trên JDK đang chạy; biết các yêu cầu phiên bản JDBC.
- [ ] Đọc `DatabaseMetaData` trên kết nối của đúng `DataSource` và ghi driver/DBMS/version.
- [ ] Gọi đúng phương thức `supports...()`, gồm cặp type/concurrency hoặc mức isolation khi cần.
- [ ] Phân biệt `YES`, `NO`, `UNKNOWN` và `SQLException` do lỗi hệ thống.
- [ ] Kiểm tra trạng thái transaction, quyền truy cập, kiểu dữ liệu và cấu hình liên quan.
- [ ] Xác minh hành vi thực tế với câu SQL hoặc dữ liệu test đại diện.
- [ ] Đọc lại trạng thái hiệu lực như `ResultSet.getType()`, `getConcurrency()`, `Connection.getTransactionIsolation()` khi áp dụng.
- [ ] Định nghĩa fallback **giữ đúng nghiệp vụ**; fail fast nếu không có phương án an toàn.
- [ ] Xử lý transaction/rollback, side effect và retry đúng trường hợp lỗi.
- [ ] Chạy kiểm thử lại sau nâng cấp driver, JDK, DBMS hoặc thay đổi tuyến kết nối.

**Ghi nhớ:** Trong kiến trúc JDBC, tính năng có trong giao diện Java chỉ là **khả năng gọi API**. Trước khi sử dụng tính năng tùy chọn, hãy tra cứu `DatabaseMetaData`, đánh giá điều kiện của connection/DBMS, kiểm tra hành vi thực tế và quyết định rõ khi nào được fallback. Cách làm này giúp cùng một ứng dụng JDBC chạy có kiểm soát trên các hệ quản trị và môi trường Java khác nhau.

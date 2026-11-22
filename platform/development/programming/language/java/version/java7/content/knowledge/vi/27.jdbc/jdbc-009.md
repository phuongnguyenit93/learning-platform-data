# Kiểm tra khả năng hỗ trợ bằng `DatabaseMetaData` trong JDBC

## 1. Bài toán: JDBC chuẩn nhưng mỗi driver và DBMS có năng lực khác nhau

**JDBC** (`java.sql`) cung cấp API truy cập cơ sở dữ liệu quan hệ, giúp ứng dụng Java làm việc với nhiều hệ quản trị khác nhau thông qua JDBC driver. Tuy nhiên, một API có sẵn **không đồng nghĩa mọi driver và mọi phiên bản database đều hỗ trợ cùng một chức năng**.

Ví dụ ứng dụng muốn:

- Dùng `PreparedStatement.addBatch()/executeBatch()` để cập nhật nhiều dòng.
- Mở transaction, rollback tới `Savepoint` hoặc chọn isolation level cụ thể.
- Xin `RETURN_GENERATED_KEYS` khi thêm bản ghi.
- Tạo `ResultSet` cuộn được, cập nhật được hoặc giữ cursor sau `commit()`.
- Gọi stored procedure, đọc nhiều result sets, dùng named parameters.
- Khám phá schemas, tables, columns, primary/foreign keys, kiểu SQL.

Nếu viết theo một database duy nhất rồi giả định DBMS khác cũng làm hệt, ứng dụng có thể gặp `SQLFeatureNotSupportedException`, `SQLException`, thay đổi hành vi cursor, DDL tự commit, kết quả không có generated keys hoặc các lỗi khó phát hiện hơn.

**`DatabaseMetaData` là API chính thức để hỏi driver về khả năng của *cặp driver + database* đang kết nối.** Không chỉ xét tên hệ quản trị. Oracle Java SE 21 Javadoc nói rõ metadata mô tả **DBMS kết hợp với driver**; driver có thể tự triển khai một số tính năng nằm trên khả năng do DBMS cung cấp. Vì thế, cùng tên DBMS nhưng driver/version khác nhau có thể báo khác; cấu hình database, quyền user và trạng thái connection còn ảnh hưởng bước thực thi thật.

Bài học này thuộc chủ đề cha **“JDBC”**, đề bài **“Kiểm tra khả năng hỗ trợ bằng DatabaseMetaData”**.

**Yêu cầu Special Note:** chỉ dùng kiến thức **vẫn còn áp dụng trên Java/JDBC hiện nay**, không hướng dẫn dựa vào API hoặc kỹ thuật lỗi thời, legacy. `DatabaseMetaData`, `Connection.getMetaData()`, `supportsBatchUpdates()`, `supportsTransactions()`, `supportsResultSetType()`, `supportsSavepoints()` và các API liên quan đều là API Java SE đang được hỗ trợ. Bài mẫu dùng **JDK 21**, `try-with-resources`, `DriverManager`, `Properties` và `java.sql`; không dựa vào driver cụ thể hoặc mẹo JDBC cũ để giả vờ tạo database.

### Sau bài học, bạn cần đạt

1. Hiểu bản chất metadata là **báo cáo năng lực** của driver/DBMS, không phải đảm bảo thao tác luôn thành công.
2. Biết lấy `DatabaseMetaData` từ **một `Connection` đã mở** và đóng connection đúng ownership.
3. Phân biệt `true`, `false` và **không xác định do lỗi truy vấn metadata**.
4. Biết các phương thức kiểm tra transaction, savepoint, isolation, batch, generated keys và cursor capabilities.
5. Biết `supportsResultSetType` khác `supportsResultSetConcurrency` và `supportsResultSetHoldability`.
6. Phân biệt **capability check** với **feature probe bằng tác vụ thật** và quyền của user.
7. Chọn fallback an toàn khi feature không được báo hỗ trợ; không silent downgrade khi business semantics bị thay đổi.
8. Khám phá schema, bảng, cột, key bằng metadata `ResultSet`, hiểu mẫu tìm kiếm và quản lý tài nguyên.
9. Biên dịch/chạy chương trình Java 21 **không cần database** để kiểm tra chính thuật toán branch theo metadata.
10. Biết chạy **chế độ JDBC thật** khi ứng dụng có driver JAR, URL và credentials; không giả tạo kết quả của một DBMS chưa được kết nối.

## 2. Lấy `DatabaseMetaData` từ `Connection`

Điểm bắt đầu chuẩn:

~~~java
try (Connection connection = DriverManager.getConnection(jdbcUrl, properties)) {
    DatabaseMetaData meta = connection.getMetaData();
    boolean supportsBatch = meta.supportsBatchUpdates();
    boolean transactions = meta.supportsTransactions();
    // Chọn nhánh xử lý tương ứng theo yêu cầu nghiệp vụ.
}
~~~

Đây là **đoạn mã minh họa**, cần imports `java.sql.Connection`, `DatabaseMetaData`, `DriverManager`, `Properties` và khai báo `jdbcUrl`/`properties`. Nó cần JDBC driver và database thật, do đó **không có stdout cố định**. Chương trình hoàn chỉnh ở phần 11 có thêm chế độ mock để chạy được chỉ bằng JDK.

Các bước sử dụng thực tế:

1. Cung cấp đúng JDBC driver cho runtime/classpath theo hướng dẫn của nhà cung cấp.
2. Mở `Connection` qua `DataSource` hoặc `DriverManager`. Trong production thường dùng `DataSource`/pool và cơ chế secret-management thích hợp.
3. Gọi `connection.getMetaData()` khi connection **còn mở**.
4. Đọc product/driver/version và các cờ `supports...` cần cho thuật toán.
5. Nếu một lời gọi metadata ném `SQLException`, ghi nhận lỗi; **không tự biến lỗi thành `false` như thể driver đã kết luận không hỗ trợ**.
6. Đưa ra fallback phù hợp hoặc fail-fast nếu tính năng bắt buộc.
7. Dù metadata trả `true`, phải vẫn xử lý lỗi thực thi SQL và kiểm tra hành vi thực tế.
8. Đóng resources thuộc sở hữu ứng dụng bằng `try-with-resources`, đặc biệt `Connection`, `Statement` và `ResultSet`.

`DatabaseMetaData` **không phải object quản lý schema migration hoặc permissions**. Nó là giao diện mô tả khả năng, cấu trúc và hạn mức do driver cung cấp; nó **không tự mở transaction**, không tự lưu dữ liệu, cũng không bảo đảm current user được quyền chạy một SQL cụ thể.

### 2.1. Vì sao không lấy metadata theo tên database trên Internet?

Hai môi trường cùng dùng một sản phẩm có thể chạy các **phiên bản khác nhau**, driver khác, database settings khác và account khác. Một bảng so sánh tính năng từ Internet chỉ nên xem là tài liệu tham khảo; **metadata của connection đang dùng** là tín hiệu trực tiếp hơn để quyết định nhánh JDBC.

Ví dụ **“PostgreSQL hỗ trợ savepoint”** là thông tin ở mức sản phẩm, còn ứng dụng vẫn phải xét driver thực tế và transaction semantics. Không hardcode `if (productName.contains(...))` làm giải pháp tổng quát khi `supportsSavepoints()` đã cung cấp một câu hỏi chuẩn.

### 2.2. Khi nào đọc metadata?

Thường đọc khi tạo/khởi tạo module tích hợp, khi xây capability matrix hoặc trước khi bật optional feature. Với pool có nhiều target databases/tenants, có thể cần snapshot **theo target/driver/config**. Không lấy một snapshot của database A áp cho database B.

Không nhất thiết gọi lại mọi `supportsX` cho mỗi row trong batch: một số metadata queries có thể tốn round-trip hoặc work bên driver. Cache có thời hạn/phạm vi hợp lý và invalidation khi driver, server, connection properties, tenant hoặc deployment thay đổi.

## 3. `DatabaseMetaData` mô tả điều gì?

API có ba nhóm hữu ích:

| Nhóm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Thông tin kết nối/driver/DBMS | `getDatabaseProductName()`, `getDatabaseProductVersion()`, `getDriverName()`, `getDriverVersion()`, `getJDBCMajorVersion()` | Chẩn đoán chính xác *cặp* driver và DBMS; ghi nhận trong capabilities log |
| Trả lời hỗ trợ một tính năng | `supportsTransactions()`, `supportsBatchUpdates()`, `supportsSavepoints()`, `supportsResultSetType(int)`, `supportsGetGeneratedKeys()` | `boolean` cho một năng lực được JDBC định nghĩa |
| Khám phá cấu trúc/mô tả | `getSchemas()`, `getTables(...)`, `getColumns(...)`, `getPrimaryKeys(...)`, `getImportedKeys(...)`, `getTypeInfo()` | Trả `ResultSet` với những hàng mô tả đối tượng DB |

Nhiều phương thức có chữ **`supports`**, nhưng **không phải tất cả metadata methods là boolean**. Một số trả `int` limits, `String` hoặc metadata `ResultSet`. Chọn đúng phương thức theo câu hỏi, đừng suy ra mọi thứ từ một cờ tổng quát.

### 3.1. Driver và database version

~~~java
DatabaseMetaData m = connection.getMetaData();
String product = m.getDatabaseProductName();
String productVersion = m.getDatabaseProductVersion();
String driverName = m.getDriverName();
String driverVersion = m.getDriverVersion();
int jdbcMajor = m.getJDBCMajorVersion();
int jdbcMinor = m.getJDBCMinorVersion();
~~~

Đây là đoạn minh họa với connection có sẵn. **`getJDBCMajorVersion` mô tả phiên bản JDBC mà driver hỗ trợ**, không phải phiên bản của JDK đang chạy; `getDatabaseProductVersion` mô tả DBMS, không phải driver. Đừng nhầm Java 21 với JDBC 21: tên và chu kỳ phiên bản khác nhau.

Khi cần debug capability khác nhau giữa môi trường staging/production, log product/driver/version **có kiểm soát**, tránh log password, full JDBC URL chứa secrets hoặc thông tin nhạy cảm.

### 3.2. Metadata không phải kiểm tra quyền

`supportsStoredProcedures()==true` không chứng minh user hiện tại có quyền `EXECUTE` một procedure cụ thể. Tương tự, `supportsTransactions()==true` không chứng minh transaction của ứng dụng có thể thành công sau mọi lỗi, và `supportsGetGeneratedKeys()==true` không bảo đảm tất cả loại statement hoặc mọi table sẽ trả key.

Một API capability check **là điều kiện đầu**, không phải lời hứa về dữ liệu, quyền, isolation hoặc tính sẵn sàng của server.

## 4. Phân biệt ba kết quả: YES, NO, UNKNOWN

Một phương thức như:

~~~java
boolean allowed = metadata.supportsBatchUpdates();
~~~

có hai giá trị trả về nếu chạy thành công, nhưng cũng có thể ném `SQLException`. Do đó thuật toán tích hợp thường cần ba trạng thái:

| Kết quả | Ý nghĩa cho ứng dụng | Nhánh an toàn |
| --- | --- | --- |
| **YES** | Driver/DBMS báo hỗ trợ tính năng được hỏi | Có thể **thử sử dụng** tính năng và xử lý runtime errors |
| **NO** | Driver/DBMS báo không hỗ trợ tính năng này | Dùng fallback hoặc fail-fast nếu bắt buộc |
| **UNKNOWN** | Không đọc được metadata do lỗi/cách triển khai | Ghi nhận nguyên nhân, fallback bảo thủ hoặc fail-fast; không giả định YES |

Đặc biệt **UNKNOWN không phải NO**: database có thể hỗ trợ nhưng connection tạm hỏng, driver trả `SQLFeatureNotSupportedException`, method metadata gặp lỗi transport hoặc user thiếu điều kiện để truy vấn. Nếu một capability **bắt buộc để bảo đảm correctness**, fallback có thể không đủ; hãy fail-fast rõ ràng thay vì âm thầm tắt transaction/constraints.

Mẫu khái niệm:

~~~java
enum Support { YES, NO, UNKNOWN }

// SqlCheck là functional interface nhận một thao tác trả boolean có thể
// ném SQLException. Trong chương trình chạy đầy đủ, interface được khai báo.
static Support probe(SqlCheck check) {
    try {
        return check.check() ? Support.YES : Support.NO;
    } catch (SQLException e) {
        // Bản sản xuất nên log an toàn SQLState và diagnostic context.
        return Support.UNKNOWN;
    }
}
~~~

Đây là **snippet minh họa lấy từ mẫu chương trình**, không độc lập vì `SqlCheck` chưa khai báo ở đây; xem full class phần 11. Không catch tất cả `Exception` rồi mặc định true/false: lỗi lập trình trong application không phải khả năng hỗ trợ DB.

### 4.1. `SQLFeatureNotSupportedException`

Đây là một subclass của `SQLException` thể hiện JDBC driver không hỗ trợ một API feature/operation nhất định. Nhưng nó **khác với một câu trả lời boolean false** của metadata. Trong adapter của một hệ thống nhiều database, cả hai đều cần policy.

Nếu một capability returns YES nhưng lúc chạy driver ném `SQLFeatureNotSupportedException`, phải xử lý như một **mismatch giữa báo cáo và vận hành**, log context và dùng fallback phù hợp; không coi YES là bảo đảm tuyệt đối.

### 4.2. `false` và “thiếu quyền” khác nhau

Metadata thường mô tả **khả năng DBMS+driver**, còn lỗi permission là vấn đề của user/role/đối tượng cụ thể. Một database có khả năng hỗ trợ transactional DML nhưng user thiếu quyền cập nhật table không phải là “DBMS không hỗ trợ transactions”.

### 4.3. Đừng probe một cách phá hoại

Không nên kiểm tra feature bằng cách thực hiện `DROP TABLE`, `ALTER TABLE` hoặc thêm/commit dữ liệu thật vào bảng production chỉ để xem driver hỗ trợ. Nếu cần integration test behavior, dùng **database sandbox và transaction/test data riêng**, có cleanup và quyền được cấp, tránh side effects không đảo ngược.

## 5. Transaction và isolation capabilities

Các câu hỏi thường gặp:

| Câu hỏi | `DatabaseMetaData` | Lưu ý |
| --- | --- | --- |
| DBMS+driver hỗ trợ transactions? | `supportsTransactions()` | Không tự bật/tắt auto-commit |
| Có hỗ trợ JDBC savepoints? | `supportsSavepoints()` | Cần transaction policy đúng |
| Có isolation level `READ_COMMITTED`? | `supportsTransactionIsolationLevel(Connection.TRANSACTION_READ_COMMITTED)` | Cần kiểm tra đúng level dự kiến |
| Có `REPEATABLE_READ`? | `supportsTransactionIsolationLevel(Connection.TRANSACTION_REPEATABLE_READ)` | SQL semantics còn phụ thuộc database |
| Isolation mặc định? | `getDefaultTransactionIsolation()` | Không phải isolation hiện tại của mọi connection |
| DDL và DML cùng nằm trong transaction? | `supportsDataDefinitionAndDataManipulationTransactions()` | Quan trọng với schema migrations |
| DDL có khiến transaction commit? | `dataDefinitionCausesTransactionCommit()` | Không mặc định DDL rollback được |
| DDL bị bỏ qua trong transactions? | `dataDefinitionIgnoredInTransactions()` | Dùng để hiểu hạn chế DB |

### 5.1. Kiểm tra hỗ trợ trước khi thiết kế logic

~~~java
DatabaseMetaData meta = connection.getMetaData();
if (!meta.supportsTransactions()) {
    throw new SQLException("This workflow requires transactions");
}
if (!meta.supportsTransactionIsolationLevel(
        Connection.TRANSACTION_READ_COMMITTED)) {
    throw new SQLException("READ_COMMITTED is required");
}
~~~

Đây là snippet minh họa, chưa thực hiện transaction. **Không tự rơi về autocommit** nếu business flow cần **atomicity**: một fallback làm mất atomic guarantee là sai hơn việc fail-fast.

### 5.2. Hỗ trợ transactions không phải đã mở transaction

Với JDBC, `Connection` thường bắt đầu ở auto-commit mode theo contract. Muốn kiểm soát transaction phải sử dụng `setAutoCommit(false)` khi phù hợp, thực hiện SQL, `commit` hoặc `rollback`, và trả connection về trạng thái đúng theo lifecycle của pool.

`supportsTransactions()==true` không tự đặt `autoCommit=false`, cũng không tự rollback khi exception. Không gộp capability check và transaction execution vào một khái niệm.

### 5.3. `getDefaultTransactionIsolation` khác `Connection.getTransactionIsolation`

- `meta.getDefaultTransactionIsolation()`: mức isolation **mặc định của database** theo JDBC metadata.
- `connection.getTransactionIsolation()`: mức isolation **trên connection hiện tại**.
- `supportsTransactionIsolationLevel(level)`: khả năng dùng một level **cụ thể**.

Không nhầm một giá trị default với việc level nào cũng supported. Nếu workflow đòi `TRANSACTION_SERIALIZABLE` và metadata chỉ trả hỗ trợ `READ_COMMITTED`, không tự hạ isolation rồi tuyên bố bảo đảm tương đương.

### 5.4. Savepoint không phải replacement cho transaction

`supportsSavepoints()==true` cho phép thiết kế xử lý `setSavepoint()`/`rollback(savepoint)` khi transaction state đúng. Nhưng `Savepoint` không phải full independent transaction: rollback tới savepoint vẫn nằm trong transaction ngoài, chưa commit business side effects.

Khi capability là NO/UNKNOWN mà workflow phụ thuộc rollback-to-savepoint, các lựa chọn là: thiết kế một transaction riêng, dừng workflow, hoặc thay phương án nghiệp vụ. Không giả lập savepoint bằng cách “đoán trạng thái trước đó” nếu không có recovery guarantee.

## 6. Batch updates và generated keys

### 6.1. `supportsBatchUpdates()`

~~~java
if (meta.supportsBatchUpdates()) {
    // Có thể chọn PreparedStatement.addBatch()/executeBatch().
} else {
    // Xử lý từng statement bằng một nhánh dự phòng.
}
~~~

Snippet minh họa; `meta` là `DatabaseMetaData` đang hoạt động. `supportsBatchUpdates()` cho biết driver/DBMS báo hỗ trợ JDBC batch updates; **không cho biết** mỗi SQL statement có thể batch vô hạn, mọi parameter set đều hợp lệ hay batch tự có transaction atomic.

**Đừng đánh đồng batch với transaction:** trong một transaction, batch execution vẫn có thể thành công một phần hoặc ném `BatchUpdateException` và cung cấp update counts. Cần quyết định rollback/commit và retry/idempotency theo nghiệp vụ, không nghĩ “batch=true” bảo đảm all-or-nothing.

### 6.2. `executeBatch` không đồng nghĩa bulk SQL tối ưu

Một driver có thể triển khai batch ở client hoặc server với hiệu năng khác nhau; metadata chỉ cho biết hỗ trợ, không chứng minh batch luôn nhanh hơn. Đo execution time, network round-trips, memory và transaction contention trên DB thực. Đừng submit một batch vô hạn, vì có thể gây RAM/truyền tải/timeouts lớn.

### 6.3. `supportsGetGeneratedKeys()`

`supportsGetGeneratedKeys()` cho biết driver/DBMS hỗ trợ lấy auto-generated keys sau khi chạy statement, ít nhất cho SQL `INSERT` khi báo true theo Javadoc.

~~~java
if (meta.supportsGetGeneratedKeys()) {
    try (PreparedStatement insert = connection.prepareStatement(
            "INSERT INTO items (name) VALUES (?)",
            Statement.RETURN_GENERATED_KEYS)) {
        insert.setString(1, "sample");
        insert.executeUpdate();
        try (ResultSet keys = insert.getGeneratedKeys()) {
            if (keys.next()) {
                long id = keys.getLong(1);
                // Sử dụng ID theo contract của schema/driver.
            }
        }
    }
}
~~~

Đây là **snippet cần database và table `items`**, chỉ minh họa API. Tạo/ghi bảng thật là hành động có side effect: chỉ chạy trong môi trường được phép. `getGeneratedKeys` có thể trả `ResultSet` trống hoặc driver xử lý khác tùy table/cấu hình; metadata=true không thay thế kiểm tra thực tế.

**Fallback cần đúng nghiệp vụ:** không lấy ID bằng `SELECT MAX(id)` sau INSERT trong môi trường nhiều connections vì bị race với transactions của người khác. Nếu JDBC generated keys không được hỗ trợ, cân nhắc câu lệnh `RETURNING` của DBMS cụ thể, sequence, UUID hoặc schema design phù hợp và kiểm thử transaction/permissions riêng.

### 6.4. Batch + generated keys là hai feature khác nhau

`supportsBatchUpdates()==true` và `supportsGetGeneratedKeys()==true` **không tự bảo đảm** driver hỗ trợ trả generated keys tương ứng mọi phần tử trong một batch với đúng thứ tự/cột mà ứng dụng mong đợi. Muốn kết hợp phải thử trên driver/schema cụ thể và có fallback; metadata cung cấp hai capability flags riêng, không chứng minh mọi tổ hợp nâng cao.

## 7. Khả năng của `ResultSet`: phải kiểm tra *đúng tổ hợp*

`ResultSet` có các đặc điểm độc lập:

1. **Type**: forward-only, scroll-insensitive hoặc scroll-sensitive.
2. **Concurrency**: read-only hoặc updatable.
3. **Holdability**: cursor có tồn tại qua commit hay bị đóng theo policy.

| Kiểm tra | Ý nghĩa |
| --- | --- |
| `supportsResultSetType(ResultSet.TYPE_SCROLL_INSENSITIVE)` | Hỗ trợ result set cuộn kiểu scroll-insensitive |
| `supportsResultSetType(ResultSet.TYPE_SCROLL_SENSITIVE)` | Hỗ trợ dạng scroll-sensitive |
| `supportsResultSetConcurrency(type, ResultSet.CONCUR_UPDATABLE)` | Hỗ trợ **tổ hợp type + updatable concurrency** |
| `supportsResultSetHoldability(ResultSet.HOLD_CURSORS_OVER_COMMIT)` | Hỗ trợ giữ cursor qua commit |
| `getResultSetHoldability()` | Holdability mặc định của database/driver theo metadata |
| `ownUpdatesAreVisible(type)` | Cập nhật do chính result set thực hiện có nhìn thấy không |
| `othersUpdatesAreVisible(type)` | Cập nhật từ các giao dịch khác có nhìn thấy không |

### 7.1. Một boolean về type chưa đủ để xin updatable

~~~java
boolean scrollable = meta.supportsResultSetType(
        ResultSet.TYPE_SCROLL_INSENSITIVE);
boolean updatable = meta.supportsResultSetConcurrency(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_UPDATABLE);
~~~

Các snippets cần meta đang mở. Nếu `scrollable=true` nhưng `updatable=false`, đừng xin scroll-insensitive **updatable** mà coi đó là supported. Nên chọn forward-only + read-only hoặc cặp type/concurrency khác thực sự được báo hỗ trợ.

### 7.2. Type và concurrency là request, không là bảo đảm runtime

Một ví dụ tạo statement có yêu cầu:

~~~java
try (Statement statement = connection.createStatement(
        ResultSet.TYPE_SCROLL_INSENSITIVE,
        ResultSet.CONCUR_READ_ONLY)) {
    int actualType = statement.getResultSetType();
    int actualConcurrency = statement.getResultSetConcurrency();
    // Kiểm tra actualType/actualConcurrency và SQLWarnings khi cần.
}
~~~

Đây là snippet cần JDBC connection. Driver có thể downgrade một request không hỗ trợ hoặc ném lỗi theo contract/implementation; ứng dụng cần kiểm tra **thực tế** thay vì chỉ dựa vào tham số truyền vào. Nếu thuật toán dựa vào `absolute(n)`, cần xác nhận result set thực sự cuộn được.

### 7.3. Holdability là một trục khác

`supportsResultSetHoldability(ResultSet.HOLD_CURSORS_OVER_COMMIT)` trả lời khả năng giữ cursor qua commit. Nhưng không phải mọi result set đều “tự sống qua commit” chỉ vì driver báo có support; cần yêu cầu đúng holdability trong statement/connection và kiểm tra lifecycle thực.

Nếu thiết kế code cần đọc cursor sau transaction commit mà metadata báo không hỗ trợ, có thể đọc/buffer dữ liệu cần thiết **trước commit** hoặc thiết kế lại giao dịch; không cứ dùng cursor cũ và mong driver cho phép.

### 7.4. Khả năng hiển thị cập nhật

Các phương thức như `ownUpdatesAreVisible(type)`, `othersUpdatesAreVisible(type)` hoặc `updatesAreDetected(type)` mô tả visibility/detection của các changes theo kiểu `ResultSet`. Không suy ra isolation semantics của database chỉ từ một flag cursor. Hãy kiểm tra đúng mức transaction isolation và business consistency requirements riêng.

## 8. Stored procedures, nhiều results và tính năng nâng cao

| Capability | Method |
| --- | --- |
| Có thể dùng stored procedures? | `supportsStoredProcedures()` |
| Một lần `Statement.execute` có thể trả nhiều result sets? | `supportsMultipleResultSets()` |
| Một `CallableStatement` có thể có nhiều result sets đồng thời? | `supportsMultipleOpenResults()` |
| `CallableStatement` có named parameters? | `supportsNamedParameters()` |
| Có REF CURSOR? | `supportsRefCursors()` |
| Có outer joins? | `supportsOuterJoins()`, `supportsFullOuterJoins()` |
| Có dùng `ORDER BY`, subqueries, correlated subqueries? | Các methods `supports...` tương ứng |

**Đừng nhầm** `supportsMultipleResultSets` với `supportsMultipleOpenResults`. Một method kiểm tra có thể nhận nhiều result sets từ một `execute`, method còn lại kiểm tra **nhiều result sets vẫn mở đồng thời từ một `CallableStatement`**. Đó là hai contract khác nhau.

Với `supportsNamedParameters()`, tên tham số của stored procedure phải trùng schema/procedure thực tế và tài khoản phải có quyền thực thi. Driver báo support không cho phép gọi tên parameter không có trong procedure.

`supportsRefCursors` và nhiều APIs hiện đại vẫn thuộc JDBC; chỉ bật khi driver/DBMS cụ thể hỗ trợ. Không viết một adapter “portable” bằng cách hardcode rằng database nào cũng hỗ trợ cùng một loại cursor hoặc stored procedure grammar.

### 8.1. SQL grammar cũng cần kiểm tra theo tính năng

`supportsFullOuterJoins()` không tương đương mọi biến thể của `JOIN` được hỗ trợ. `supportsConvert(fromType,toType)` trả lời khả năng dùng JDBC scalar function `CONVERT` cho cặp SQL types được xác định bằng `java.sql.Types`, **không phải** câu hỏi chung về mọi `CAST` hoặc mọi chuyển đổi vendor-specific.

Một SQL generator portable cần kết hợp metadata, SQL dialect mapping, feature tests và fallback, không chỉ đổi tên database trong URL.

## 9. Khám phá schema bằng metadata `ResultSet`

`DatabaseMetaData` không chỉ có `supports...`. Nó còn cung cấp thông tin cấu trúc database:

- `getCatalogs()`, `getSchemas()`: catalogs và schemas được expose.
- `getTableTypes()` và `getTables(catalog,schemaPattern,tableNamePattern,types)`: loại đối tượng và các bảng/view matching.
- `getColumns(catalog,schemaPattern,tableNamePattern,columnNamePattern)`: columns, SQL types và nullable metadata.
- `getPrimaryKeys(catalog,schema,table)`: primary key columns.
- `getImportedKeys(catalog,schema,table)`: foreign key columns của table tham chiếu primary keys khác.
- `getExportedKeys(...)`: bảng khác tham chiếu primary key của table này.
- `getIndexInfo(...)`: indices và statistics theo arguments.
- `getTypeInfo()`: SQL types driver mô tả.
- `getProcedures(...)`, `getProcedureColumns(...)`: stored procedures và parameters.

Các methods này trả **`ResultSet` có cột chuẩn theo Javadoc**; có thể có vendor-specific columns bổ sung. Nếu một loại metadata không khả dụng, Javadoc nêu có thể trả **ResultSet rỗng**; vì vậy “không thấy bảng” có thể do filters/schema/permissions/driver chứ không tự chứng minh bảng không tồn tại.

### 9.1. Ví dụ đọc tên bảng

~~~java
DatabaseMetaData metadata = connection.getMetaData();
try (ResultSet rs = metadata.getTables(
        connection.getCatalog(), null, "%", new String[] { "TABLE" })) {
    while (rs.next()) {
        String schema = rs.getString("TABLE_SCHEM");
        String table = rs.getString("TABLE_NAME");
        // Xử lý cặp (schema,table) trong phạm vi tài khoản hiện tại.
    }
}
~~~

Đây là **mã minh họa chỉ chạy với database thật**, chưa khai báo connection và chưa có stdout. `getTables` có thể trả nhiều bảng và một số driver dùng loại table/case khác; điều chỉnh catalog, schema và `types` theo target. **Đóng metadata `ResultSet`** bằng try-with-resources vì nó có thể giữ driver/network resources.

### 9.2. Pattern và `null` không giống chuỗi rỗng

Đối với nhiều metadata methods có tên tham số `...Pattern`:

- `%` khớp 0 hoặc nhiều ký tự;
- `_` khớp đúng một ký tự;
- `null` trong pattern thường nghĩa **không dùng tiêu chí đó để giới hạn tìm kiếm**;
- `""` trong catalog/schema parameters có thể nghĩa **những đối tượng không có catalog/schema** theo hợp đồng method.

Ví dụ:

~~~java
try (ResultSet rs = metadata.getColumns(
        null, null, "orders", "%")) {
    while (rs.next()) {
        String name = rs.getString("COLUMN_NAME");
        int sqlType = rs.getInt("DATA_TYPE");
        String typeName = rs.getString("TYPE_NAME");
        // Chọn mapping phù hợp với driver/schema.
    }
}
~~~

Mã minh họa; không tạo hay thay đổi table. Nếu ứng dụng cần tìm tên có ký tự `%` hoặc `_` **theo nghĩa literal**, tra `getSearchStringEscape()` của metadata thay vì ghép wildcard tùy tiện. Không nhầm metadata pattern với SQL parameters; không dùng input chưa kiểm tra như identifier.

### 9.3. Nhận biết rules của identifier

`getIdentifierQuoteString()` trả ký tự/chuỗi quote identifier mà DBMS hỗ trợ; có thể là khoảng trắng khi không hỗ trợ quote. Các methods `storesUpperCaseIdentifiers()`, `storesLowerCaseIdentifiers()`, `supportsMixedCaseIdentifiers()` và variants cho quoted identifiers mô tả cách xử lý case.

Không tự sửa mọi tên bảng sang uppercase/lowercase theo kinh nghiệm từ một DBMS khác. Tránh ghép trực tiếp untrusted table/column names vào SQL: bind parameters qua `PreparedStatement` chỉ áp dụng **cho giá trị**, không cho SQL identifier, nên dynamic table names cần allowlist và quoting phù hợp dialect.

### 9.4. Query metadata không luôn rẻ

`getTables("%")` trên database có hàng nghìn schema/tables có thể trả nhiều rows hoặc tốn round-trips. Chỉ hỏi những schemas/tables cần thiết, dùng patterns cụ thể, đóng ResultSet và cache snapshot đúng vòng đời. Đừng gọi metadata schema scan trước mọi INSERT.

## 10. Thiết kế một bộ “capability matrix” đúng cách

Một ứng dụng đa DBMS có thể xây cấu trúc:

~~~text
Connection đến DBMS với JDBC driver thực tế
              |
              v
        DatabaseMetaData
              |
              v
    Hỏi những feature cần thiết
              |
              v
        YES / NO / UNKNOWN
              |
       +------+-------+
       |              |
   Supported      NO / UNKNOWN
       |              |
       v              v
    Try feature     Fallback / fail-fast
       |              |
       v              v
 Validate actual result / log operational errors
~~~

**Không scan mọi method của `DatabaseMetaData` chỉ để tạo một object khổng lồ** nếu ứng dụng chỉ cần batch và generated keys. Hỏi theo nhu cầu, bởi một vài method có thể trả rất nhiều data hoặc có vendor-specific quirks.

### 10.1. Cách chọn fallback theo mức quan trọng

| Tính năng | Nếu YES | Nếu NO/UNKNOWN |
| --- | --- | --- |
| Batch updates | Thử `addBatch/executeBatch`, xử lý partial errors | Execute từng statement, giới hạn throughput; vẫn có transaction policy riêng |
| Generated keys | Thử `RETURN_GENERATED_KEYS` và kiểm tra ResultSet | Dùng ID chiến lược khác như UUID/sequence/DB-specific returning nếu được phép, không `SELECT MAX(id)` |
| Savepoints | Có thể thử `setSavepoint` trong transaction | Thiết kế rollback toàn transaction hoặc fail nếu cần partial rollback |
| Scrollable ResultSet | Thử yêu cầu scroll type | Dùng forward-only cursor hoặc materialize có giới hạn |
| Updatable ResultSet | Chỉ thử đúng type+concurrency pair | Dùng explicit `UPDATE ... WHERE ...` trong transaction |
| Hold cursor across commit | Chỉ thử nếu được báo hỗ trợ | Đọc/buffer dữ liệu trước commit hoặc đổi workflow |
| Isolation level cần thiết | Chọn level khi supported và verify connection state | Fail-fast nếu business bắt buộc; không âm thầm hạ consistency |
| Named parameters | Dùng feature khi stored procedure/driver support | Dùng positional parameters khi driver/procedure contract cho phép |

### 10.2. False/unknown không có nghĩa cứ chạy fallback “cho xong”

Nếu nghiệp vụ yêu cầu rollback atomic và DBMS không hỗ trợ transactions, việc chạy từng SQL trên auto-commit có thể làm **sai correctness**. Trường hợp ấy phải báo feature unavailable và không thực hiện nửa workflow.

Tương tự, nếu app cần scrollable result set để đọc lại dữ liệu nhiều lần, fallback forward-only chỉ đúng khi app có cách buffering/rewind phù hợp. Một fallback hợp lệ cần giữ **ý nghĩa nghiệp vụ** chứ không chỉ tránh exception.

### 10.3. Tránh speculative feature usage trong production

Khi metadata báo NO, đừng cứ chạy feature rồi catch lỗi liên tục ở mọi request; điều đó có thể tạo network load và log noise. Với metadata UNKNOWN, lựa chọn phải có deadline/retry policy và có thể fail-fast để tránh silently incorrect behavior. Có thể triển khai small integration probe trong môi trường kiểm soát với schema fixture để xác minh reporting.

## 11. Ví dụ Java 21 hoàn chỉnh: mock xác định và JDBC thật tùy chọn

Chương trình dưới đây có **hai chế độ trong một class**:

1. **Không truyền tham số:** tạo một `DatabaseMetaData` **giả lập** bằng Java `Proxy`. Fixture mô tả một database/driver tưởng tượng `FixtureDB/FixtureDriver`. Nó cố tình có:
   - Transactions YES.
   - Savepoints **UNKNOWN** vì `supportsSavepoints()` ném `SQLException`.
   - Batch updates YES.
   - Generated keys NO.
   - Scroll-insensitive YES nhưng scroll-updatable NO.
   - Hold cursors over commit NO, repeatable-read YES.
   - Stored procedures, multiple results, named parameters NO.

   Chương trình in **20 dòng cố định**, đủ kiểm thử rằng branch chọn batch, từ chối savepoint khi unknown, chọn scrollable read-only và dùng fallback cho generated keys. **Đây không phải kết quả đo bất kỳ DBMS thật nào.**
2. **`--live`:** đọc `JDBC_URL` từ environment; có thể đọc thêm `JDBC_USER` và `JDBC_PASSWORD`. Kết nối thật qua `DriverManager` và gọi **cùng hàm `inspect`** trên `connection.getMetaData()`. Chế độ này cần một JDBC driver phù hợp (vendor JAR) cùng cơ sở dữ liệu có thể truy cập; output **thay đổi theo driver/DBMS** nên không có stdout cố định.

Chương trình minh họa cách **cùng một nhánh logic** hoạt động với fake metadata và live metadata, thay vì hardcode tên database để quyết định feature. Nó dùng `LinkedHashMap` khi thu thập flags và mảng `order` riêng khi in để **không phụ thuộc thứ tự duyệt `Map.copyOf()`**. API `Proxy` chỉ dùng trong bộ mô phỏng/tự kiểm thử, **không dùng để giả mạo báo cáo capability production**.

### 11.1. Tệp chạy được

Tạo file `src/main/java/demo/JdbcCapabilityExample.java`:

~~~java
package demo;

import java.lang.reflect.Proxy;
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Properties;

public final class JdbcCapabilityExample {
    private JdbcCapabilityExample() {}

    private enum Support { YES, NO, UNKNOWN }

    @FunctionalInterface
    private interface SqlCheck {
        boolean check() throws SQLException;
    }

    private record Snapshot(
            String product, String driver, String jdbcVersion,
            Map<String, Support> features) {}

    private static Support probe(SqlCheck check) {
        try {
            return check.check() ? Support.YES : Support.NO;
        } catch (SQLException e) {
            return Support.UNKNOWN;
        }
    }

    private static Snapshot inspect(DatabaseMetaData metadata)
            throws SQLException {
        Map<String, Support> flags = new LinkedHashMap<>();
        flags.put("transactions", probe(metadata::supportsTransactions));
        flags.put("savepoints", probe(metadata::supportsSavepoints));
        flags.put("batch-updates", probe(metadata::supportsBatchUpdates));
        flags.put("generated-keys", probe(metadata::supportsGetGeneratedKeys));
        flags.put("scroll-insensitive",
                probe(() -> metadata.supportsResultSetType(
                        ResultSet.TYPE_SCROLL_INSENSITIVE)));
        flags.put("scroll-updatable",
                probe(() -> metadata.supportsResultSetConcurrency(
                        ResultSet.TYPE_SCROLL_INSENSITIVE,
                        ResultSet.CONCUR_UPDATABLE)));
        flags.put("hold-cursors-after-commit",
                probe(() -> metadata.supportsResultSetHoldability(
                        ResultSet.HOLD_CURSORS_OVER_COMMIT)));
        flags.put("repeatable-read",
                probe(() -> metadata.supportsTransactionIsolationLevel(
                        Connection.TRANSACTION_REPEATABLE_READ)));
        flags.put("stored-procedures", probe(metadata::supportsStoredProcedures));
        flags.put("multiple-results", probe(metadata::supportsMultipleResultSets));
        flags.put("named-parameters", probe(metadata::supportsNamedParameters));

        return new Snapshot(
                metadata.getDatabaseProductName(),
                metadata.getDriverName(),
                metadata.getJDBCMajorVersion() + "."
                        + metadata.getJDBCMinorVersion(),
                Map.copyOf(flags));
    }

    private static String choose(Support flag, String yes, String fallback) {
        return flag == Support.YES ? yes : fallback;
    }

    private static void show(Snapshot snapshot) {
        System.out.println("database=" + snapshot.product());
        System.out.println("driver=" + snapshot.driver());
        System.out.println("jdbc=" + snapshot.jdbcVersion());
        String[] order = {
            "transactions", "savepoints", "batch-updates", "generated-keys",
            "scroll-insensitive", "scroll-updatable",
            "hold-cursors-after-commit", "repeatable-read",
            "stored-procedures", "multiple-results", "named-parameters"
        };
        for (String key : order) {
            System.out.println(key + "=" + snapshot.features().get(key));
        }
        Map<String, Support> f = snapshot.features();
        System.out.println("batch-path=" + choose(
                f.get("batch-updates"), "TRY_BATCH", "INDIVIDUAL_EXECUTION"));
        System.out.println("savepoint-path=" +
                (f.get("transactions") == Support.YES
                 && f.get("savepoints") == Support.YES
                 ? "TRY_SAVEPOINT" : "NO_SAVEPOINT_FALLBACK"));
        System.out.println("cursor-path=" + choose(
                f.get("scroll-insensitive"), "TRY_SCROLLABLE", "FORWARD_ONLY"));
        System.out.println("update-path=" +
                (f.get("scroll-insensitive") == Support.YES
                 && f.get("scroll-updatable") == Support.YES
                 ? "TRY_UPDATABLE" : "READ_ONLY"));
        System.out.println("keys-path=" + choose(
                f.get("generated-keys"), "TRY_GENERATED_KEYS",
                "DB_SPECIFIC_FALLBACK"));
    }

    private static DatabaseMetaData fixture() {
        return (DatabaseMetaData) Proxy.newProxyInstance(
                DatabaseMetaData.class.getClassLoader(),
                new Class<?>[] { DatabaseMetaData.class },
                (proxy, method, args) -> switch (method.getName()) {
                    case "getDatabaseProductName" -> "FixtureDB";
                    case "getDriverName" -> "FixtureDriver";
                    case "getJDBCMajorVersion" -> 4;
                    case "getJDBCMinorVersion" -> 3;
                    case "supportsTransactions", "supportsBatchUpdates" -> true;
                    case "supportsSavepoints" ->
                        throw new SQLException("Mock metadata unavailable", "0A000");
                    case "supportsGetGeneratedKeys", "supportsStoredProcedures",
                         "supportsMultipleResultSets", "supportsNamedParameters",
                         "supportsResultSetHoldability",
                         "supportsResultSetConcurrency" -> false;
                    case "supportsResultSetType" ->
                        ((Integer) args[0]) == ResultSet.TYPE_SCROLL_INSENSITIVE;
                    case "supportsTransactionIsolationLevel" ->
                        ((Integer) args[0]) == Connection.TRANSACTION_REPEATABLE_READ;
                    default -> throw new UnsupportedOperationException(
                        "Fixture does not model: " + method.getName());
                });
    }

    public static void main(String[] args) throws SQLException {
        if (args.length == 0) {
            System.out.println("mode=MOCK_NOT_REAL_DB");
            show(inspect(fixture()));
            return;
        }
        if (args.length != 1 || !"--live".equals(args[0])) {
            throw new IllegalArgumentException("Use no args or --live");
        }
        String url = System.getenv("JDBC_URL");
        if (url == null || url.isBlank()) {
            throw new IllegalArgumentException("Set JDBC_URL for --live");
        }
        Properties credentials = new Properties();
        String user = System.getenv("JDBC_USER");
        String password = System.getenv("JDBC_PASSWORD");
        if (user != null) {
            credentials.setProperty("user", user);
        }
        if (password != null) {
            credentials.setProperty("password", password);
        }
        try (Connection connection =
                     DriverManager.getConnection(url, credentials)) {
            System.out.println("mode=LIVE_DB");
            show(inspect(connection.getMetaData()));
        }
    }
}
~~~

### 11.2. Biên dịch và chạy chế độ không cần database

Từ thư mục chứa `src`, dùng **JDK 21**:

~~~sh
javac --release 21 -encoding UTF-8 -Xlint:all -d out src/main/java/demo/JdbcCapabilityExample.java
java -cp out demo.JdbcCapabilityExample
~~~

Đây là chương trình Java chuẩn, không cần JDBC driver JAR bên thứ ba cho **chế độ mock** vì interface `DatabaseMetaData` đã có trong module `java.sql` của JDK.

**Stdout chính xác của chế độ mock trên Java 21:**

~~~text
mode=MOCK_NOT_REAL_DB
database=FixtureDB
driver=FixtureDriver
jdbc=4.3
transactions=YES
savepoints=UNKNOWN
batch-updates=YES
generated-keys=NO
scroll-insensitive=YES
scroll-updatable=NO
hold-cursors-after-commit=NO
repeatable-read=YES
stored-procedures=NO
multiple-results=NO
named-parameters=NO
batch-path=TRY_BATCH
savepoint-path=NO_SAVEPOINT_FALLBACK
cursor-path=TRY_SCROLLABLE
update-path=READ_ONLY
keys-path=DB_SPECIFIC_FALLBACK
~~~

### 11.3. Đọc các kết quả

- `mode=MOCK_NOT_REAL_DB`: cố ý phân biệt fake metadata với DBMS thật.
- `database=FixtureDB`, `driver=FixtureDriver`, `jdbc=4.3`: đây là **giá trị fixture**, không phải kết luận về một server đang hoạt động.
- `transactions=YES`: mock báo có transactions, nhưng nó **không thật sự mở transaction**.
- `savepoints=UNKNOWN`: fixture ném `SQLException`; hàm `probe` không ép nó thành NO.
- `batch-updates=YES`: thuật toán chọn `TRY_BATCH`; vẫn phải xử lý `BatchUpdateException` nếu chạy thật.
- `generated-keys=NO`: thuật toán không tự gọi `RETURN_GENERATED_KEYS` rồi giả định thành công; chọn fallback chuyên biệt.
- `scroll-insensitive=YES` nhưng `scroll-updatable=NO`: nhận kiểu scroll, không bật updatable; `update-path=READ_ONLY`.
- `hold-cursors-after-commit=NO`: không hứa cursor sẽ tồn tại qua commit.
- `repeatable-read=YES`: metadata báo hỗ trợ isolation này; chưa có transaction thật nào được tạo.
- `stored-procedures=NO`, `multiple-results=NO`, `named-parameters=NO`: ví dụ mô phỏng những tổ hợp không được hỗ trợ.
- `savepoint-path=NO_SAVEPOINT_FALLBACK`: **UNKNOWN bị xử lý bảo thủ**, không thử partial-rollback như thể chắc chắn hỗ trợ.
- `cursor-path=TRY_SCROLLABLE`: “TRY” nhấn mạnh capability check chưa đảm bảo statement cụ thể tạo được cursor như yêu cầu.

### 11.4. Chạy với driver/database thật

Muốn dùng `--live`, ứng dụng phải có **JDBC driver JAR tương thích** trong runtime classpath (hoặc được ứng dụng/build tool đưa vào dependency graph), cùng URL, credentials và kết nối DB thật.

Trên **PowerShell**, cấu hình môi trường theo secrets policy của hệ thống, rồi chạy với driver JAR đã được cài hợp lệ:

~~~powershell
$env:JDBC_URL = "jdbc:yourvendor:yourdatabase"
$env:JDBC_USER = "your_user"
# JDBC_PASSWORD phải lấy từ secret manager hoặc môi trường được quản lý.
java -cp "out;vendor-driver.jar" demo.JdbcCapabilityExample --live
~~~

Trên **Linux/macOS**, dấu phân tách classpath là dấu hai chấm thay vì dấu chấm phẩy:

~~~sh
JDBC_URL="jdbc:yourvendor:yourdatabase" JDBC_USER="your_user" \
  java -cp "out:vendor-driver.jar" demo.JdbcCapabilityExample --live
~~~

Các chuỗi `yourvendor:yourdatabase` và `vendor-driver.jar` **chỉ minh họa dạng URL và đường dẫn**, không phải một JDBC driver có thể kết nối ngay. Cấu hình thực tế theo nhà cung cấp và cơ chế lưu secrets của bạn. Không nên truyền password trong command-line arguments hoặc log full URL nếu URL chứa credentials; env vars cũng phải được kiểm soát theo policy vì có thể bị nhìn thấy bởi các processes/công cụ quản trị phù hợp quyền.

Chế độ live **không cần ghi/chỉnh bảng**, nhưng việc mở connection và hỏi metadata vẫn có thể tạo network traffic và chịu quy định access của DB. Nó có thể ném `SQLException` nếu URL sai, driver không có, authentication thất bại hoặc metadata không thể đọc được. Bài kiểm thử tự động **chỉ xác nhận mock stdout và compile**, không giả mạo output live.

### 11.5. Giới hạn có chủ đích của demo

- `Proxy` fixture chỉ implement **những methods được `inspect` gọi**; gọi method khác trên fixture sẽ ném `UnsupportedOperationException`. Đó là hành vi của **mock test**, không phải thông tin về JDBC driver thật.
- `probe` bắt `SQLException` và trả UNKNOWN nhưng không log mã `SQLState` để giữ output mẫu cố định; production phải log diagnostic context không lộ secrets.
- Snapshot chứa các capability cốt lõi, không là catalog đầy đủ mọi JDBC methods.
- Logic chọn fallback chỉ in **nhãn quyết định**, không thực thi SQL (tránh tác dụng phụ).
- Live mode mở connection thực, nhưng không chạy `INSERT`/`UPDATE`; metadata vẫn có thể khác nhau giữa drivers/environments.
- Không dùng một snapshot mock để quyết định tính năng production; phải đọc từ actual `Connection`.

## 12. Diễn giải “feature supported” trong hệ thống thực

### 12.1. Cần kiểm tra cả version và khả năng

`getDatabaseProductName()`/`getDriverVersion()` giúp theo dõi môi trường, nhưng không nên dùng `if ("SomeDB".equals(product))` làm thay thế mọi capability check. Có các trường hợp driver update, server upgrade hoặc connection config làm behavior đổi mà tên product vẫn giữ nguyên.

Gắn capability snapshot với target database, driver/version và timestamp đo; vô hiệu cache sau upgrade/cấu hình thay đổi hoặc lỗi vận hành.

### 12.2. Kiểm tra capability không thay thế integration tests

Metadata có thể báo YES nhưng:

- Một SQL statement cụ thể không đủ điều kiện, ví dụ query phức tạp không updatable.
- User hiện tại thiếu quyền trên table/procedure.
- Database object không tồn tại hoặc schema khác.
- Driver thực tế hạ cấp statement type/concurrency.
- Một phiên bản driver có bug hoặc config thay đổi.
- Connection bị đứt sau lúc đọc metadata.
- Isolation level danh nghĩa được map khác với các bảo đảm cần trong business.

Vì vậy với chức năng quan trọng, **metadata + integration test trên driver thật + runtime error handling** là bộ ba cần thiết. Nếu false/unknown, fallback chỉ được chọn khi đáp ứng đúng nghiệp vụ.

### 12.3. Metadata snapshot không phải distributed consensus

Nếu ứng dụng có connection pool trỏ tới nhiều DB endpoints, khả năng từng endpoint có thể khác. Snapshot đọc từ một connection không phải bằng chứng mọi replica/shard đều cùng phiên bản driver/server. Với multi-tenant/multi-cluster, kiểm tra đúng target và không áp một capability flag global khi chưa có contract đồng nhất.

### 12.4. Lỗi metadata có thể là transient

Một `SQLException` khi hỏi supports may reflect network issue, DB state hoặc driver limitation. Chính sách có thể retry có deadline **theo error classification**, nhưng không retry vô hạn và không mặc định YES. Nếu chức năng bắt buộc cho correctness, fail-fast và báo lý do cụ thể thường an toàn hơn âm thầm chạy đường ít bảo đảm.

## 13. Metadata cho code generator và schema migration

Một ORM/schema tool có thể dùng metadata để xây SQL portable:

- `getTables` và `getColumns` để biết tên/kiểu columns.
- `getPrimaryKeys`/`getImportedKeys` để khám phá keys.
- `getTypeInfo` và `supportsConvert` để map SQL data types.
- Identifier quote/case methods để tạo tên object hợp lệ.
- Transaction/DDL capability methods để quyết định giới hạn của migrations.

Nhưng **metadata không phải SQL parser** và không có nghĩa mọi DDL đều được rollback. Một migration tool phải hiểu SQL dialect và transaction semantics của DBMS. Khi schema changes gây commit tự động, rollback theo JDBC `Connection.rollback()` không nhất thiết đảo ngược DDL đã thực thi.

### 13.1. Không chạy migration tùy tiện từ metadata

Đọc `getTables` là thao tác khám phá; nó **không cho phép** ứng dụng tự động `ALTER TABLE` hoặc cấp quyền. Nếu một bảng thiếu, đó có thể do schema pattern, permissions hoặc metadata visibility, không phải bằng chứng phải tạo bảng mới.

### 13.2. Metadata đọc bao nhiêu là đủ?

Với một service chỉ cần batch insert và generated keys, hai capability flags là đủ cho quyết định ban đầu; không cần scan hàng nghìn bảng/columns mỗi request. Với một migration tool, schema metadata có thể là phần chính của nhiệm vụ, nhưng cần cache, filters và đóng resources đầy đủ.

## 14. Bảo mật và vận hành khi đọc metadata

- **Không log credentials** từ connection properties, environment hoặc JDBC URL chứa password.
- **Không cho client chọn trực tiếp driver class/JDBC URL** để server mở connection ngoài chính sách, tránh SSRF/secret leakage và kết nối tới endpoint không được phép.
- Metadata có thể chứa schema/table/procedure names nhạy cảm; xuất báo cáo với quyền và phạm vi được cho phép.
- Sử dụng `PreparedStatement` cho **giá trị** SQL, không coi metadata quote string là một sanitizer cho identifier tùy ý.
- Đối với dynamic table/column names, dùng allowlist và identifier quoting/escaping đúng dialect.
- Nếu JDBC driver báo năng lực không hỗ trợ, không lén dùng native SQL không kiểm soát trong một đường portable mà không kiểm thử.
- Chỉ dùng connection đang thuộc vòng đời ứng dụng; với connection pool, trả connection đúng cách (đóng logical handle) để không làm rò rỉ pool.
- Phân loại lỗi driver/network/authentication/permission và báo thông tin không lộ secrets.
- Nếu cần diagnostic logs, ghi product/driver **một cách chọn lọc**, không biến toàn bộ schema introspection thành dữ liệu công khai.
- Đánh giá chính sách least-privilege: introspection quyền lớn hơn cần thiết có thể gây rủi ro.
- Phần “mock” trong bài không thực sự liên hệ database; đừng coi các giá trị `FixtureDB` là security/feature evidence.

## 15. Các lỗi phổ biến và cách khắc phục

| Sai lầm | Vì sao sai | Cách khắc phục |
| --- | --- | --- |
| Cho rằng JDBC interface tồn tại là mọi DBMS có feature | JDBC chuẩn hóa API, không chuẩn hóa mọi optional capability | `DatabaseMetaData.supportsX` và integration tests |
| Hardcode theo tên DBMS duy nhất | Driver/version/config có thể khác | Dùng metadata của connection |
| Coi `supportsTransactions` đã mở transaction | Không thay đổi auto-commit | Quản lý `setAutoCommit`/`commit`/`rollback` riêng |
| Nếu savepoints UNKNOWN thì tự gọi `setSavepoint` như chắc chắn | UNKNOWN không phải YES | Fallback bảo thủ hoặc fail-fast |
| Nếu metadata throw, map trực tiếp thành NO | Mất nguyên nhân lỗi | Phân biệt YES/NO/UNKNOWN và log |
| Catch mọi `Exception` làm UNKNOWN | Che bug application | Catch `SQLException` cho JDBC query |
| Nếu batch YES thì nghĩ tự atomic | Batch không đồng nghĩa transaction | `BatchUpdateException`/update counts/rollback policy |
| Nếu generated keys YES thì mọi INSERT luôn trả key | Có thể tùy table/statement | Kiểm tra ResultSet và schema contract |
| Lấy ID bằng `SELECT MAX(id)` | Race với concurrent transactions | Dùng sequence/UUID/RETURNING hợp lệ |
| Chỉ kiểm tra `supportsResultSetType` trước khi tạo updatable | Cần cặp type+concurrency | `supportsResultSetConcurrency(type, concurrency)` |
| Không kiểm tra requested vs actual cursor type | Driver có thể downgrade | Đọc `Statement.getResultSetType`/`getResultSetConcurrency` |
| Coi holdability chung cho mọi statement | Holdability là một dimension riêng | `supportsResultSetHoldability` và runtime check |
| Nhầm multiple result sets với multiple open results | Hai contract khác nhau | Hỏi đúng method |
| Nhầm default isolation với current connection isolation | Có thể được thay đổi sau khi mở | `Connection.getTransactionIsolation` |
| Giả định DDL rollback như DML | DDL có thể commit/không vào transaction | DDL metadata methods + integration test |
| Không đóng metadata ResultSet | Rò resources network/driver | Try-with-resources |
| Dùng `getTables(null,null,"%")` quá rộng mọi request | Expensive/unnecessary | Narrow patterns và cache |
| Nhầm `null` với chuỗi rỗng trong schema filter | Kết quả khác nhau | Đọc parameter contract |
| Ghép identifier untrusted vào SQL | Injection/quote errors | Allowlist và quote đúng dialect |
| Log full JDBC URL/secret | Rò thông tin nhạy cảm | Secret management và log có chọn lọc |
| Test mock rồi khẳng định driver thật hỗ trợ | Mock chỉ kiểm tra branch logic | Test live trên driver/DB thật |
| Fail open khi capability UNKNOWN và feature critical | Sai correctness | Fail-fast với diagnostic hữu ích |

## 16. Bài tập có lời giải

**Câu 1.** `DatabaseMetaData` lấy từ đâu?  
**Đáp án:** `Connection.getMetaData()` trên JDBC connection đang hoạt động.

**Câu 2.** Metadata phản ánh một DBMS độc lập với driver?  
**Đáp án:** Không. Nó phản ánh **DBMS kết hợp JDBC driver** trên connection.

**Câu 3.** `getJDBCMajorVersion()` có phải JDK major version?  
**Đáp án:** Không. Đó là phiên bản JDBC mà driver hỗ trợ.

**Câu 4.** Muốn biết có dùng `executeBatch` được không, hỏi gì?  
**Đáp án:** `supportsBatchUpdates()`; nếu true vẫn phải xử lý execution errors.

**Câu 5.** Batch=true thì mọi cập nhật là atomic?  
**Đáp án:** Không. Transaction management và partial batch results là vấn đề riêng.

**Câu 6.** Muốn dùng savepoint hỏi gì?  
**Đáp án:** `supportsSavepoints()`, cùng kiểm tra transactions và current connection state.

**Câu 7.** Metadata ném `SQLException` khi hỏi savepoints nên coi là false?  
**Đáp án:** Không. Ghi **UNKNOWN**, fallback bảo thủ hoặc fail-fast khi feature critical.

**Câu 8.** `supportsTransactions()==true` có tắt auto-commit không?  
**Đáp án:** Không. Phải quản lý `Connection.setAutoCommit(false)`/commit/rollback.

**Câu 9.** Isolation mặc định và isolation hiện tại giống nhau mãi?  
**Đáp án:** Không. `getDefaultTransactionIsolation` của metadata khác `Connection.getTransactionIsolation`.

**Câu 10.** `supportsTransactionIsolationLevel(Connection.TRANSACTION_REPEATABLE_READ)` kiểm tra gì?  
**Đáp án:** Khả năng hỗ trợ một isolation level được yêu cầu.

**Câu 11.** Muốn scroll-insensitive updatable cần mấy kiểm tra?  
**Đáp án:** `supportsResultSetType(TYPE_SCROLL_INSENSITIVE)` và `supportsResultSetConcurrency(TYPE_SCROLL_INSENSITIVE,CONCUR_UPDATABLE)`.

**Câu 12.** `supportsResultSetType` true đã bảo đảm actual Statement type đúng chưa?  
**Đáp án:** Chưa. Driver/statement cụ thể có thể khác; kiểm tra actual type/concurrency và xử lý warning/error.

**Câu 13.** Có thể giữ ResultSet qua commit?  
**Đáp án:** Hỏi `supportsResultSetHoldability(HOLD_CURSORS_OVER_COMMIT)` và yêu cầu đúng holdability; không mặc định.

**Câu 14.** `supportsGetGeneratedKeys()==true` nghĩa là key luôn có?  
**Đáp án:** Không; phải execute đúng API, kiểm tra `getGeneratedKeys` và schema.

**Câu 15.** Có nên lấy ID sau INSERT bằng `SELECT MAX(id)` không?  
**Đáp án:** Không, race với connections khác.

**Câu 16.** `supportsMultipleResultSets` và `supportsMultipleOpenResults` có giống nhau?  
**Đáp án:** Không. Lần lượt là nhiều result sets từ một execute và nhiều result sets còn mở đồng thời từ CallableStatement.

**Câu 17.** `supportsStoredProcedures` true chứng minh có quyền gọi procedure?  
**Đáp án:** Không; permissions và procedure existence riêng.

**Câu 18.** `getTables` trả kiểu gì?  
**Đáp án:** `ResultSet` chứa metadata rows, cần đóng sau dùng.

**Câu 19.** `%` trong metadata pattern có nghĩa gì?  
**Đáp án:** Khớp 0 hoặc nhiều ký tự; `_` khớp đúng một.

**Câu 20.** `null` và `""` trong schema filter có luôn giống nhau?  
**Đáp án:** Không; null thường bỏ filter, empty string có thể chỉ schema không có tên.

**Câu 21.** Không thấy table trong metadata chắc chắn table không tồn tại?  
**Đáp án:** Không; có thể do permissions, catalog/schema filter, table type hoặc driver behavior.

**Câu 22.** `getIdentifierQuoteString` có thay PreparedStatement bind values?  
**Đáp án:** Không. Identifier quoting và value binding là hai việc khác nhau.

**Câu 23.** Mock ở phần 11 chứng minh một DBMS thật hỗ trợ gì?  
**Đáp án:** Không. Nó chỉ kiểm thử branching algorithm với capability values giả định.

**Câu 24.** Chế độ `--live` cần gì?  
**Đáp án:** JDBC driver JAR tương thích, JDBC URL, credentials và database có thể truy cập.

**Câu 25.** Database upgrade rồi có nên dùng lại snapshot capability cũ vô thời hạn?  
**Đáp án:** Không; cache có phạm vi/lifecycle và invalidation rõ.

**Câu 26.** Nếu feature critical không hỗ trợ, fallback âm thầm giảm consistency có tốt không?  
**Đáp án:** Không. Fail-fast hoặc chọn một phương án vẫn bảo đảm contract nghiệp vụ.

## 17. Checklist triển khai

- [ ] Xác định rõ feature cần kiểm tra và yêu cầu nghiệp vụ tương ứng.
- [ ] Có đúng JDBC driver và connection tới target DBMS hiện hành.
- [ ] Lấy metadata bằng `connection.getMetaData()`; không chỉ đoán từ tên DBMS.
- [ ] Ghi nhận product/driver/version một cách không lộ secrets.
- [ ] Đọc đúng `supportsX` cho tính năng cụ thể; không suy ra mọi capability từ một flag.
- [ ] Với transactions, xem `supportsTransactions`, isolation và DDL behavior khi liên quan.
- [ ] Với savepoint, biết transaction state và fallback/abort policy.
- [ ] Với batch, xử lý partial failures/`BatchUpdateException`.
- [ ] Với generated keys, kiểm tra actual returned keys, không dùng `SELECT MAX(id)`.
- [ ] Với cursor, kiểm tra type, concurrency **kết hợp** và holdability.
- [ ] Với stored procedures, phân biệt named parameters, multiple results và quyền gọi.
- [ ] Phân biệt YES/NO/UNKNOWN khi metadata throws.
- [ ] Nếu UNKNOWN ở feature critical, fail-safe, không mặc định YES.
- [ ] Khi metadata báo YES, vẫn xử lý runtime `SQLException` và validate behavior.
- [ ] Khi metadata báo NO, fallback phải giữ đúng business semantics.
- [ ] Với schema introspection, dùng filters hợp lý và đọc patterns đúng contract.
- [ ] Đóng `ResultSet`/`Statement`/`Connection` theo ownership/`try-with-resources`.
- [ ] Không chạy SQL phá dữ liệu production để “test khả năng hỗ trợ”.
- [ ] Không dùng mock fixture làm chứng cứ về database thật.
- [ ] Test integration trên đúng driver/DBMS/version/config đã triển khai.
- [ ] Cache capability snapshot theo đúng database/driver/tenant và invalidate khi nâng cấp.
- [ ] Không log secrets hoặc full JDBC URL nhạy cảm.
- [ ] Dynamic SQL identifiers qua allowlist/quote đúng dialect, values qua prepared statement.
- [ ] Chỉ sử dụng JDBC APIs hiện hành; loại bỏ các workaround lỗi thời/legacy.
- [ ] Nếu phải bắt đầu trong môi trường chỉ có JDK, dùng mock để kiểm thử branch, không giả lập một kết nối DB thật.

## 18. Nguồn tài liệu chính thức còn áp dụng

- [Oracle Java SE 21 — DatabaseMetaData](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/DatabaseMetaData.html): contract driver+DBMS, methods `supports...`, patterns, metadata `ResultSet` và các khả năng JDBC.
- [Oracle Java SE 21 — Connection](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Connection.html): `getMetaData`, transaction state, isolation, statements, savepoints.
- [Oracle Java SE 21 — DriverManager](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/DriverManager.html): lấy JDBC connection thông qua driver có sẵn ở runtime.
- [Oracle Java SE 21 — ResultSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/ResultSet.html): TYPE, CONCUR, holdability constants và lifecycle.
- [Oracle Java SE 21 — Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html): `RETURN_GENERATED_KEYS`, `getResultSetType`, `getResultSetConcurrency` và execution.
- [Oracle Java SE 21 — PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html): parameter binding và batch.
- [Oracle Java SE 21 — BatchUpdateException](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/BatchUpdateException.html): partial batch update counts khi execution fail.
- [Oracle Java SE 21 — SQLFeatureNotSupportedException](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/SQLFeatureNotSupportedException.html): subclass của SQLException cho feature chưa được hỗ trợ.
- [Oracle Java SE 21 — SQLException](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/SQLException.html): SQLState/vendor error code, exception chaining.
- [Oracle Java SE 21 — Proxy](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html): fake metadata interface cho test deterministic, không thay connection integration test.

**Kết luận:** `DatabaseMetaData` là công cụ chuẩn giúp một ứng dụng JDBC hỏi **cặp driver và DBMS đang dùng** có hỗ trợ từng tính năng không. Nó hỗ trợ thiết kế code portable nhưng **không thay thế** permissions, connection state, integration tests và xử lý lỗi thực thi. Hãy hỏi đúng method (đặc biệt tổ hợp `ResultSet` type/concurrency/holdability), phân biệt NO với UNKNOWN, chọn fallback giữ đúng correctness và dùng metadata `ResultSet` một cách có kiểm soát. Đây là cách dùng JDBC hiện hành, không dựa vào giả định lỗi thời/legacy.

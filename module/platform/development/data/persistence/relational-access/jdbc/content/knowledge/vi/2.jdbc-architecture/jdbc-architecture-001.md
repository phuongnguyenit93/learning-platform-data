# Vai trò của các gói `java.sql` và `javax.sql` trong kiến trúc JDBC

## 1. Bối cảnh: JDBC giải quyết vấn đề gì?

**JDBC (Java Database Connectivity)** là API chuẩn của Java để ứng dụng truy cập cơ sở dữ liệu quan hệ: mở kết nối, gửi câu lệnh SQL, truyền tham số, nhận kết quả, quản lý giao dịch và xử lý lỗi. JDBC cung cấp các interface và kiểu dữ liệu chung; JDBC driver của từng hệ quản trị cơ sở dữ liệu hiện thực việc trao đổi thực tế với PostgreSQL, MySQL, SQL Server, Oracle hoặc hệ quản trị khác.

Trong kiến trúc JDBC, hai gói quan trọng có vai trò bổ sung cho nhau:

- **`java.sql`** cung cấp các thành phần cốt lõi để *làm việc trên một kết nối*: kết nối, thực thi SQL, đọc kết quả, transaction, metadata và ngoại lệ.
- **`javax.sql`** bổ sung các hợp đồng để *cung cấp và quản lý kết nối*, hỗ trợ connection pooling, kết nối dùng trong giao dịch phân tán và mô hình `RowSet`.

Ứng dụng JDBC hiện đại thường lấy `Connection` từ một `DataSource` của `javax.sql`, sau đó dùng `Connection`, `PreparedStatement` và `ResultSet` của `java.sql` để thao tác dữ liệu. Vì vậy, hai gói không cạnh tranh hay thay thế nhau.

### Mục tiêu sau bài học

Sau khi học, bạn có thể nhận diện lớp/interface nằm trong từng gói, phân biệt `DriverManager` với `DataSource`, hiểu luồng lấy kết nối → chạy SQL → đóng tài nguyên, và quyết định khi nào cần connection pool hoặc XA transaction.

## 2. Sơ đồ quan hệ giữa hai gói

~~~mermaid
flowchart TD
    A["Ứng dụng Java"] --> B{"Lấy kết nối"}
    B --> C["DataSource<br/>(javax.sql)"]
    B --> D["DriverManager<br/>(java.sql)"]
    C --> E["Connection<br/>(java.sql)"]
    D --> E
    E --> F["PreparedStatement / CallableStatement<br/>(java.sql)"]
    F --> G[("Cơ sở dữ liệu quan hệ<br/>thông qua JDBC driver")]
    F --> H["ResultSet<br/>(java.sql)"]
    I["Connection pool hoặc XA provider<br/>(triển khai javax.sql)"] -. "có thể đứng sau" .-> C
~~~

`DataSource` là **interface**, không mặc nhiên đồng nghĩa với connection pool: một implementation có thể tạo kết nối trực tiếp hoặc sử dụng pool. `DriverManager` là điểm vào đơn giản do JDBC cung cấp, thường phù hợp với chương trình nhỏ và ví dụ học tập. Cả hai cuối cùng đều cung cấp đối tượng `java.sql.Connection` để ứng dụng sử dụng.

| Khía cạnh | `java.sql` | `javax.sql` |
|---|---|---|
| Trọng tâm | Thực hiện thao tác SQL và quản lý trạng thái kết nối | Trừu tượng hóa nguồn kết nối, tích hợp hạ tầng và hỗ trợ `RowSet` |
| Thành phần thường gặp | `DriverManager`, `Connection`, `Statement`, `PreparedStatement`, `ResultSet`, `SQLException` | `DataSource`, `ConnectionPoolDataSource`, `PooledConnection`, `XADataSource`, `XAConnection`, `RowSet` |
| Ai sử dụng? | Hầu hết mã repository/DAO thực thi SQL | Tầng cấu hình, DI container, connection pool, transaction manager; đôi khi mã xử lý `RowSet` |
| Công việc điển hình | Truy vấn, cập nhật, batch, commit/rollback, đọc metadata | Cấp phát kết nối, tái sử dụng kết nối vật lý, tích hợp giao dịch phân tán |

## 3. `java.sql`: các thành phần JDBC cốt lõi

### 3.1. Mở kết nối: `Driver` và `DriverManager`

`java.sql.Driver` là hợp đồng mà JDBC driver thực hiện để Java giao tiếp với một hệ quản trị cơ sở dữ liệu cụ thể. `DriverManager` quản lý các driver đã đăng ký và chọn driver phù hợp theo JDBC URL khi gọi `getConnection(...)`.

Ví dụ, với driver thích hợp đã nằm trên classpath/module path và cơ sở dữ liệu đã được cấu hình:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class JdbcConnectExample {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("JDBC_URL");
        String username = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                     DriverManager.getConnection(url, username, password)) {
            System.out.println("Kết nối thành công: " + !connection.isClosed());
        }
    }
}
~~~

JDBC URL có cú pháp phụ thuộc driver, chẳng hạn `jdbc:postgresql://localhost:5432/appdb`. Đây là ví dụ cấu trúc URL, không phải thông số bắt buộc. Với JDBC driver hiện đại hỗ trợ Java Service Provider, thường không cần gọi thủ công `Class.forName(...)` để nạp driver; tuy nhiên JAR driver phù hợp vẫn phải có mặt trong ứng dụng.

**Giới hạn:** `DriverManager.getConnection(...)` tự nó không cung cấp cơ chế pooling tiêu chuẩn. Khi ứng dụng mở nhiều kết nối thường xuyên, cách tổ chức dựa trên `DataSource` sẽ linh hoạt hơn.

### 3.2. `Connection`: phiên làm việc và transaction

`Connection` đại diện cho một kết nối logic mà mã ứng dụng dùng để làm việc với cơ sở dữ liệu. Các thao tác chính:

- `prepareStatement(sql)` tạo câu lệnh SQL có tham số; `createStatement()` tạo câu lệnh thông thường; `prepareCall(sql)` gọi stored procedure.
- `setAutoCommit(false)`, `commit()`, `rollback()` điều khiển **giao dịch cục bộ** trên chính kết nối đó.
- `setTransactionIsolation(...)`, `getMetaData()`, `setReadOnly(...)` và `setSavepoint()` quản lý đặc tính phiên hoặc transaction khi driver/database hỗ trợ.
- `close()` giải phóng kết nối logic; nếu đến từ pool, lệnh này thông thường trả kết nối về pool để tái sử dụng.

Mặc định, một `Connection` mới thường ở chế độ auto-commit: mỗi câu lệnh hoàn thành sẽ được commit theo quy tắc của JDBC. Muốn nhiều thao tác SQL có tính nguyên tử, hãy tắt auto-commit và tự `commit`/`rollback`, hoặc dùng transaction manager của framework.

### 3.3. `Statement`, `PreparedStatement`, `CallableStatement`

| Interface | Mục đích | Trường hợp phù hợp |
|---|---|---|
| `Statement` | Thực thi chuỗi SQL không có tham số ràng buộc | SQL tĩnh, ví dụ công cụ quản trị |
| `PreparedStatement` | SQL có dấu `?` và giá trị được bind theo kiểu | Truy vấn/cập nhật thông thường, nhất là dữ liệu do người dùng cung cấp |
| `CallableStatement` | Gọi stored procedure; có thể nhận tham số OUT | Hệ thống dùng thủ tục lưu trữ |

`PreparedStatement` giúp truyền **giá trị** tách khỏi cú pháp SQL, làm giảm nguy cơ SQL injection so với ghép chuỗi trực tiếp. Dấu `?` chỉ thay cho giá trị, **không** dùng thay tên bảng, tên cột hay từ khóa SQL. Các định danh SQL động cần được kiểm soát bằng danh sách cho phép.

Các phương thức quan trọng: `executeQuery()` trả về `ResultSet` cho truy vấn, `executeUpdate()` trả về số hàng bị tác động đối với DML (hoặc 0 với một số lệnh không trả số hàng), `execute()` dùng khi cần xử lý kiểu kết quả linh hoạt; `addBatch()` và `executeBatch()` hỗ trợ batch.

### 3.4. `ResultSet`, kiểu dữ liệu, metadata và lỗi

`ResultSet` cho phép duyệt từng dòng kết quả bằng `next()` rồi đọc dữ liệu qua `getString(...)`, `getLong(...)`, `getBigDecimal(...)`, `getTimestamp(...)` và các getter thích hợp. Giá trị SQL `NULL` cần được xét đúng: getter đối tượng có thể trả `null`; với một số getter kiểu nguyên thủy, dùng `wasNull()` khi phải phân biệt `NULL` với giá trị mặc định.

Những nhóm API khác của `java.sql` cũng quan trọng:

- **Kiểu SQL/JDBC:** `Types`, `JDBCType`, `SQLType`; các kiểu dữ liệu phức tạp như `Blob`, `Clob`, `NClob`, `SQLXML`, `Array`, `Struct`.
- **Metadata:** `DatabaseMetaData` mô tả khả năng của driver/database, bảng/cột; `ResultSetMetaData` mô tả cột của kết quả; `ParameterMetaData` mô tả tham số nếu được hỗ trợ.
- **Lỗi và cảnh báo:** `SQLException` cung cấp thông điệp, `SQLState`, mã lỗi vendor và chuỗi lỗi tiếp theo; các subclass như `SQLTransientException` và `SQLIntegrityConstraintViolationException` giúp phân loại tình huống.

Để tránh rò rỉ tài nguyên, dùng `try-with-resources` cho `Connection`, `Statement` và `ResultSet`. Thứ tự đóng là ngược với thứ tự khai báo tài nguyên.

## 4. `javax.sql`: nguồn kết nối và các tiện ích mở rộng

### 4.1. `DataSource`: điểm truy cập kết nối nên ưu tiên

`DataSource` là interface tiêu chuẩn chứa `getConnection()` và `getConnection(username, password)`. Implementation cụ thể thường đến từ JDBC driver, thư viện connection pool hoặc application server. Mã nghiệp vụ chỉ phụ thuộc vào interface này nên dễ thay đổi cấu hình kết nối và kiểm thử hơn.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Optional;
import javax.sql.DataSource;

public final class UserRepository {
    private final DataSource dataSource;

    // DataSource được cung cấp từ cấu hình ứng dụng, DI hoặc container.
    public UserRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Optional<String> findEmailById(long userId) throws SQLException {
        String sql = "SELECT email FROM users WHERE id = ?";

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {

            statement.setLong(1, userId);

            try (ResultSet resultSet = statement.executeQuery()) {
                if (!resultSet.next()) {
                    return Optional.empty();
                }
                return Optional.ofNullable(resultSet.getString("email"));
            }
        }
    }
}
~~~

Ở ví dụ trên, **`DataSource` thuộc `javax.sql`**, nhưng **`Connection`, `PreparedStatement`, `ResultSet`, `SQLException` đều thuộc `java.sql`**. Mã truy vấn không cần biết kết nối do pool hay driver trực tiếp cung cấp. Bảng `users` và cột `id`, `email` là schema minh họa; cần thay bằng schema thực tế khi chạy.

Lưu ý cấu hình cụ thể như URL, tên người dùng, mật khẩu, kích thước pool, timeout thường do thư viện, driver hoặc framework đảm nhận; không có một bộ setter cấu hình URL/pool chung cho mọi implementation `DataSource`.

### 4.2. Connection pooling: tái sử dụng kết nối vật lý

Thiết lập kết nối đến database có chi phí đáng kể. Connection pool quản lý một tập kết nối vật lý đã mở hoặc có thể được mở theo nhu cầu; ứng dụng mượn kết nối logic và trả lại sau khi dùng.

~~~mermaid
sequenceDiagram
    participant App as Repository / Service
    participant DS as Pool-backed DataSource
    participant Pool as Connection pool
    participant DB as Database
    App->>DS: getConnection()
    DS->>Pool: Mượn kết nối khả dụng
    Pool-->>App: Connection (logic handle)
    App->>DB: SQL qua Connection
    DB-->>App: Kết quả
    App->>Pool: connection.close()
    Note over Pool: Hoàn trả cho pool; kết nối vật lý<br/>thường được giữ để tái sử dụng
~~~

Các hợp đồng ở `javax.sql` liên quan đến pooling:

- `DataSource`: API mà **ứng dụng** thường gọi để lấy kết nối.
- `ConnectionPoolDataSource`: API để **pool manager** lấy `PooledConnection` từ nguồn kết nối phù hợp; mã DAO thường không gọi trực tiếp.
- `PooledConnection`: đại diện cho nguồn kết nối vật lý và cung cấp các logical connection handle; hỗ trợ thông báo sự kiện đóng/lỗi thông qua `ConnectionEventListener`.

Một `DataSource` tích hợp pooling có thể được xây dựng bằng implementation riêng của thư viện pool; **không phải** mọi `DataSource` đều bắt buộc triển khai `ConnectionPoolDataSource`.

**Quy tắc vận hành:** luôn gọi `close()` sau khi dùng, kể cả khi đã kích hoạt pool. Quên đóng kết nối sẽ làm cạn pool; đóng đúng cách thường *trả* kết nối logic về pool thay vì đóng socket vật lý. Không chia sẻ một `Connection` cho nhiều luồng cùng thao tác khi chưa có bảo đảm cụ thể từ driver.

### 4.3. Giao dịch phân tán: `XADataSource` và `XAConnection`

`Connection.commit()` trong `java.sql` điều khiển **local transaction** trên một kết nối. Nếu một giao dịch phải phối hợp nhiều tài nguyên tham gia, ví dụ hai database khác nhau, một transaction manager có thể dùng giao thức XA/two-phase commit.

- `XADataSource` cung cấp `XAConnection` cho môi trường có XA transaction manager.
- `XAConnection` cho phép lấy JDBC `Connection` và `XAResource` (trong `javax.transaction.xa`) để transaction manager điều phối.
- XA có chi phí cấu hình/vận hành cao hơn; không dùng chỉ vì ứng dụng có nhiều câu SQL trên **một** database.

Trong ứng dụng do framework/container quản lý transaction, tránh tự ý trộn `commit()` hoặc `rollback()` thủ công với transaction manager đang sở hữu cùng kết nối.

### 4.4. `RowSet` và các gói con

`javax.sql.RowSet` mở rộng `ResultSet` và bổ sung mô hình JavaBeans, property và listener, giúp biểu diễn dữ liệu hàng theo cách thuận tiện hơn trong một số ứng dụng. `javax.sql.RowSetEvent` và `RowSetListener` hỗ trợ thông báo thay đổi.

Một số kiểu `RowSet` cụ thể nằm trong **gói khác là `javax.sql.rowset`**, không nằm trực tiếp trong `javax.sql`:

| Kiểu | Vai trò |
|---|---|
| `JdbcRowSet` | RowSet có kết nối, bọc thao tác trên JDBC ResultSet |
| `CachedRowSet` | Có thể giữ dữ liệu đã lấy trong bộ nhớ để xử lý khi không còn kết nối |
| `WebRowSet` | Mở rộng CachedRowSet, hỗ trợ biểu diễn dữ liệu dưới dạng XML |
| `FilteredRowSet` | Cho phép lọc các hàng hiển thị theo predicate |
| `JoinRowSet` | Kết hợp dữ liệu từ các RowSet phù hợp |

RowSet hữu ích cho một số tác vụ dữ liệu tách kết nối, nhưng không phải lựa chọn mặc định cho mọi repository. Với ứng dụng web thông thường, `ResultSet` được đọc rồi ánh xạ sang DTO/domain object thường đơn giản và rõ ràng hơn.

## 5. So sánh hai cách lấy kết nối

| Tiêu chí | `DriverManager.getConnection(...)` | `DataSource.getConnection()` |
|---|---|---|
| API tạo kết nối | `java.sql.DriverManager` | `javax.sql.DataSource` |
| Cách cấu hình | Truyền URL và thông tin xác thực khi gọi | Chuẩn bị implementation qua cấu hình/DI/container |
| Pooling | Không được `DriverManager` tự cung cấp | Có thể tích hợp pool tùy implementation |
| Phù hợp | Ví dụ học, công cụ nhỏ, kiểm tra kết nối | Backend nhiều request, ứng dụng vận hành lâu dài |
| Kết quả trả về | `java.sql.Connection` | `java.sql.Connection` |
| Mã truy vấn phía sau | Dùng API `java.sql` | Vẫn dùng API `java.sql` |

Trong môi trường production nhiều request, cấu hình một `DataSource` chung rồi inject vào DAO/repository giúp tránh lặp thông số kết nối và tập trung quản lý pool, timeout và credential. Việc dùng `DataSource` **không** tự động bảo đảm hiệu năng tốt: cần chọn implementation và cấu hình pool hợp lý.

## 6. Ví dụ transaction với `DataSource` và `java.sql.Connection`

Tình huống chuyển tiền giữa hai tài khoản minh họa cách **`javax.sql` cung cấp kết nối** còn **`java.sql` thực thi hai thay đổi trong cùng local transaction**:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class AccountTransfer {
    public static void transfer(
            DataSource dataSource, long fromId, long toId, BigDecimal amount)
            throws SQLException {

        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Giao dịch chuyển tiền không hợp lệ");
        }

        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);
            try {
                String debitSql = """
                        UPDATE accounts
                        SET balance = balance - ?
                        WHERE id = ? AND balance >= ?
                        """;
                try (PreparedStatement debit = connection.prepareStatement(debitSql)) {
                    debit.setBigDecimal(1, amount);
                    debit.setLong(2, fromId);
                    debit.setBigDecimal(3, amount);
                    if (debit.executeUpdate() != 1) {
                        throw new SQLException("Tài khoản nguồn không tồn tại hoặc thiếu số dư");
                    }
                }

                String creditSql =
                        "UPDATE accounts SET balance = balance + ? WHERE id = ?";
                try (PreparedStatement credit = connection.prepareStatement(creditSql)) {
                    credit.setBigDecimal(1, amount);
                    credit.setLong(2, toId);
                    if (credit.executeUpdate() != 1) {
                        throw new SQLException("Tài khoản đích không tồn tại");
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException exception) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    exception.addSuppressed(rollbackError);
                }
                throw exception;
            }
        }
    }
}
~~~

Ví dụ dùng Java 15+ (text block) và giả định bảng `accounts` có các cột `id`, `balance`, chạy trên database có transaction và mức cô lập phù hợp. Điều kiện `balance >= ?` ở câu `UPDATE` giảm nguy cơ ghi nợ vượt số dư khi giao dịch đồng thời; các bất biến khác vẫn cần ràng buộc và kiểm thử phù hợp với database thực tế.

Hai câu `UPDATE` sử dụng **cùng một `Connection`**. Nếu câu thứ hai thất bại, `rollback()` hoàn tác câu thứ nhất. Nếu cả hai thành công, `commit()` xác nhận giao dịch. `try-with-resources` luôn đóng logical connection sau khi kết thúc; connection pool, nếu có, chịu trách nhiệm xử lý việc hoàn trả và khôi phục trạng thái kết nối. Trong hệ thống dùng transaction manager của Spring/Jakarta EE, nên để framework quản lý ranh giới giao dịch thay cho thao tác thủ công kiểu này.

## 7. Các điểm dễ nhầm lẫn

1. **`javax.sql` có phải thư viện Java EE/Jakarta EE bên ngoài JDK?** Không. `javax.sql` là API JDBC chuẩn của **Java SE** và giữ namespace `javax.sql`. Đừng tự đổi import thành `jakarta.sql`.
2. **Có bắt buộc dùng `javax.sql` mới chạy SQL được?** Không. `DriverManager` thuộc `java.sql` đủ cho luồng cơ bản. `DataSource` hữu ích khi cấu hình và quản lý kết nối cần linh hoạt.
3. **Dùng `DataSource` là mặc nhiên có connection pool?** Không. Pool phụ thuộc implementation và cấu hình.
4. **`ConnectionPoolDataSource` có phải thứ cần inject vào repository?** Thông thường không. Repository chỉ cần `DataSource`; pool manager sử dụng các API cấp thấp khi implementation hỗ trợ.
5. **`ResultSet` có thuộc `javax.sql` vì `RowSet` ở đó?** Không. `ResultSet` thuộc `java.sql`; `RowSet` thuộc `javax.sql` và mở rộng `ResultSet`.
6. **XA có cần cho transaction nhiều SQL?** Không. Một `Connection` với commit/rollback đã hỗ trợ local transaction; XA dành cho phối hợp nhiều tài nguyên.
7. **`java.sql` và `javax.sql` nằm ở module nào từ Java 9?** Cả hai được xuất bởi module JDK `java.sql`. Khi khai báo `module-info.java`, có thể dùng `requires java.sql;`. Riêng các interface như `CachedRowSet` trong `javax.sql.rowset` thuộc module `java.sql.rowset` và cần `requires java.sql.rowset;` nếu sử dụng trong named module.

## 8. Cách chọn API trong dự án JDBC

Khi bắt đầu một chức năng truy cập dữ liệu quan hệ:

1. Chuẩn bị JDBC driver đúng database; thống nhất URL, credential và timeout tại tầng cấu hình.
2. Với ứng dụng có nhiều request hoặc cần DI, cung cấp `DataSource` cho repository/service; cân nhắc pool tùy tải thực tế.
3. Mở `Connection` trong phạm vi thao tác; dùng `PreparedStatement` với parameter binding.
4. Duyệt `ResultSet`, ánh xạ dữ liệu sang kiểu miền nghiệp vụ, xử lý SQL NULL và lỗi.
5. Với nhiều cập nhật cần tính nguyên tử, dùng local transaction trên cùng kết nối hoặc transaction manager tương ứng.
6. Đóng mọi tài nguyên bằng `try-with-resources`; theo dõi thời gian mượn kết nối và số kết nối đang sử dụng nếu có pool.

**Ghi nhớ:** `javax.sql.DataSource` trả về `java.sql.Connection`; `Connection` tạo `java.sql.PreparedStatement`; câu truy vấn trả về `java.sql.ResultSet`. Đó là sự phân chia trách nhiệm quan trọng nhất giữa hai gói trong kiến trúc JDBC.

### Tài liệu tham khảo chính thức

- [Java SE 21 API — `java.sql`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/package-summary.html)
- [Java SE 21 API — `javax.sql`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/javax/sql/package-summary.html)
- [Java SE 21 API — `javax.sql.rowset`](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql.rowset/javax/sql/rowset/package-summary.html)

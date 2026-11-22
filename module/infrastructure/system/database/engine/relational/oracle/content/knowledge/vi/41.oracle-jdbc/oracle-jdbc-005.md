# Connection, Statement, PreparedStatement và CallableStatement

Oracle JDBC là cầu nối giữa ứng dụng Java và Oracle Database. JDBC cung cấp các interface chuẩn để mở kết nối, gửi SQL, truyền tham số, đọc kết quả và gọi thủ tục lưu trong database. Bốn interface quan trọng nhất trong phần này là `Connection`, `Statement`, `PreparedStatement` và `CallableStatement`.

Chúng có quan hệ theo một luồng sử dụng phổ biến:

```text
Java application
      |
      v
DataSource / DriverManager
      |
      v
Connection
      |
      +---- createStatement() ------> Statement
      |
      +---- prepareStatement(sql) --> PreparedStatement
      |
      +---- prepareCall(sql) -------> CallableStatement
                                         |
                                         v
                                  ResultSet / OUT values
```

`Connection` đại diện cho một phiên làm việc với database. Từ kết nối, ứng dụng tạo một đối tượng statement phù hợp với loại SQL cần thực thi. Các câu lệnh truy vấn có thể trả về `ResultSet`; DML có thể trả về số dòng bị ảnh hưởng; thủ tục có thể trả kết quả qua tham số `OUT`, `IN OUT` hoặc `REF CURSOR`.

## 1. Chuẩn bị Oracle JDBC và kết nối database

### 1.1. JDBC driver

Oracle JDBC driver triển khai các interface JDBC để Java giao tiếp với Oracle Database. Driver Thin thường được dùng trong ứng dụng vì kết nối trực tiếp qua Oracle Net mà không cần cài Oracle Client đầy đủ trên máy chạy ứng dụng.

Ứng dụng cần dependency `ojdbc` phù hợp với phiên bản Java và môi trường triển khai. Ví dụ cấu hình Maven dưới đây minh họa cách khai báo dependency; nên quản lý phiên bản bằng dependency management của dự án và chọn artifact tương thích với JDK đang dùng:

```xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>${oracle.jdbc.version}</version>
</dependency>
```

Tên artifact và phiên bản driver cần được chọn theo JDK, Oracle Database và tính năng sử dụng. Không nên lấy một phiên bản ngẫu nhiên từ ví dụ rồi dùng cho mọi môi trường.

Với JDBC hiện đại, driver thường được tự động đăng ký thông qua cơ chế service provider. Vì vậy, ứng dụng thường không cần gọi `Class.forName("oracle.jdbc.OracleDriver")` nữa. Nếu dùng môi trường cũ hoặc cấu hình class loader đặc biệt, hãy kiểm tra hướng dẫn driver tương ứng.

### 1.2. JDBC URL dạng service name

URL Oracle Thin thường dùng dạng service name:

```text
jdbc:oracle:thin:@//dbhost.example.com:1521/orclpdb.example.com
```

Các thành phần:

- `jdbc:oracle:thin:`: dùng Oracle Thin JDBC driver.
- `dbhost.example.com`: hostname hoặc địa chỉ máy chủ database.
- `1521`: listener port trong ví dụ.
- `orclpdb.example.com`: service name mà listener công bố.

Trong ứng dụng production, dùng service name phù hợp với PDB hoặc database service, không tự suy ra service từ SID. URL dạng SID cũ có cú pháp khác và không nên nhầm với dạng service name.

### 1.3. Mở kết nối đơn giản bằng DriverManager

`DriverManager` phù hợp với ví dụ nhỏ, chương trình dòng lệnh hoặc công cụ kiểm tra. Ví dụ:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class OracleConnectionExample {
    private static final String URL =
        "jdbc:oracle:thin:@//dbhost.example.com:1521/orclpdb.example.com";

    public static void main(String[] args) throws SQLException {
        String username = System.getenv("DB_USERNAME");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(URL, username, password)) {
            System.out.println("Connected: " + !connection.isClosed());
        }
    }
}
```

`getConnection` trả về một `Connection` nếu kết nối thành công; nếu thất bại, JDBC ném `SQLException`. Ví dụ lấy credential từ environment variable để tránh ghi cứng mật khẩu trong source code. Với hệ thống thật, nên dùng secret manager hoặc cơ chế credential được nền tảng triển khai quản lý. Environment variable chỉ là ví dụ đơn giản và vẫn cần được bảo vệ.

### 1.4. Dùng DataSource trong ứng dụng thực tế

`DataSource` là cách lấy kết nối được khuyến nghị cho ứng dụng server. Nó tách cấu hình kết nối khỏi code và có thể tích hợp connection pool, JNDI hoặc Oracle Universal Connection Pool (UCP).

Ví dụ sử dụng một `DataSource` đã được cấu hình bởi application server hoặc dependency injection:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

public class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void checkConnection() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Thực hiện thao tác database trong phạm vi kết nối này.
        }
    }
}
```

Trong môi trường có pool, `dataSource.getConnection()` thường mượn một connection đã được pool quản lý. Gọi `close()` trả connection về pool để tái sử dụng, thay vì nhất thiết đóng physical connection tới database. Vì vậy, vẫn phải đóng connection bằng try-with-resources sau mỗi đơn vị công việc.

Không tạo một `Connection` toàn cục rồi chia sẻ tùy tiện cho mọi request hoặc thread. Connection mang trạng thái transaction, session setting và cursor; chia sẻ đồng thời có thể gây trộn giao dịch và lỗi khó đoán. Mỗi đơn vị công việc nên mượn connection theo quy ước của pool.

## 2. Connection

### 2.1. Vai trò của Connection

`java.sql.Connection` đại diện cho một kết nối/session JDBC tới database. Nó là điểm bắt đầu để:

- Tạo `Statement`, `PreparedStatement` và `CallableStatement`.
- Quản lý transaction bằng `commit`, `rollback` và `setAutoCommit`.
- Thiết lập isolation level, read-only hint, schema và một số thuộc tính session.
- Tạo `Savepoint`.
- Lấy metadata về database và driver.
- Đóng hoặc trả connection về pool.

Một connection thường tương ứng với một database session trong suốt thời gian được mượn. Session có thể giữ trạng thái như transaction đang mở, NLS setting, current schema, package state và temporary object tùy cấu hình.

### 2.2. Auto-commit mặc định

Theo JDBC, connection mới thường có `autoCommit = true`. Khi đó, mỗi câu lệnh SQL được commit tự động khi hoàn tất. Có thể kiểm tra hoặc thay đổi:

```java
boolean autoCommit = connection.getAutoCommit();
connection.setAutoCommit(false);
```

Khi `autoCommit` là `false`, ứng dụng chịu trách nhiệm kết thúc transaction bằng `commit()` hoặc `rollback()`.

### 2.3. Ví dụ transaction với Connection

Giả sử cần trừ tiền từ tài khoản A và cộng tiền vào tài khoản B. Hai thao tác phải cùng thành công hoặc cùng thất bại:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public class TransferService {
    public void transfer(
            Connection connection,
            long fromAccount,
            long toAccount,
            BigDecimal amount) throws SQLException {

        boolean previousAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement debit = connection.prepareStatement(
                    "UPDATE accounts SET balance = balance - ? " +
                    "WHERE account_id = ? AND balance >= ?")) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromAccount);
                debit.setBigDecimal(3, amount);

                int debited = debit.executeUpdate();
                if (debited != 1) {
                    throw new SQLException("Insufficient funds or source account missing");
                }
            }

            try (PreparedStatement credit = connection.prepareStatement(
                    "UPDATE accounts SET balance = balance + ? " +
                    "WHERE account_id = ?")) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toAccount);

                int credited = credit.executeUpdate();
                if (credited != 1) {
                    throw new SQLException("Destination account not found");
                }
            }

            connection.commit();
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        } finally {
            connection.setAutoCommit(previousAutoCommit);
        }
    }
}
```

Ví dụ tập trung vào transaction boundary. Trong code thực tế, cần xác định rõ ai sở hữu connection và ai chịu trách nhiệm commit. Nếu connection do transaction manager của framework quản lý, repository không nên tự ý commit hoặc đổi `autoCommit`; transaction manager phải điều khiển vòng đời transaction.

Lưu ý rằng Oracle DDL như `CREATE`, `ALTER` hoặc `DROP` có implicit commit theo quy tắc Oracle. Không trộn DDL với DML trong một transaction rồi kỳ vọng `rollback()` hoàn tác toàn bộ DDL.

### 2.4. Savepoint

Savepoint cho phép quay lui một phần thao tác trong transaction:

```java
import java.sql.Savepoint;

connection.setAutoCommit(false);

try {
    updateOrder(connection);
    Savepoint beforeOptionalStep = connection.setSavepoint("BEFORE_OPTIONAL");

    try {
        applyOptionalDiscount(connection);
    } catch (SQLException optionalFailure) {
        connection.rollback(beforeOptionalStep);
    }

    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
```

Sau `rollback(savepoint)`, các thao tác trước savepoint vẫn nằm trong transaction; các thao tác sau savepoint bị hoàn tác. Savepoint không thay thế transaction design rõ ràng và không nên dùng để che giấu lỗi nghiệp vụ.

### 2.5. Transaction isolation

Oracle mặc định dùng `READ COMMITTED`: mỗi câu SQL nhìn thấy dữ liệu đã commit tại thời điểm câu lệnh bắt đầu, theo cơ chế read consistency của Oracle. Oracle cũng hỗ trợ `SERIALIZABLE` và transaction read-only theo cú pháp phù hợp.

JDBC có thể thiết lập isolation level:

```java
connection.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
```

Hoặc:

```java
connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);
```

Không giả định mọi mức isolation JDBC đều được Oracle hỗ trợ như nhau. Oracle không cung cấp `READ UNCOMMITTED` theo cách của một số database khác. `Connection.setReadOnly(true)` là hint cho driver/DBMS, không nên coi đó là cơ chế phân quyền bảo mật. Nếu cần transaction read-only của Oracle, hãy dùng cơ chế transaction tương ứng và xác nhận cú pháp theo phiên bản.

`SERIALIZABLE` có thể dẫn đến lỗi serialization khi transaction không thể tiếp tục an toàn, ví dụ `ORA-08177`. Ứng dụng cần có chính sách retry có giới hạn cho transaction có thể chạy lại an toàn.

### 2.6. Metadata và trạng thái connection

Một số API hữu ích:

```java
DatabaseMetaData metadata = connection.getMetaData();
System.out.println(metadata.getDatabaseProductName());
System.out.println(metadata.getDatabaseProductVersion());
System.out.println(metadata.getDriverName());

boolean valid = connection.isValid(5);
```

`isValid(timeout)` kiểm tra connection còn hợp lệ theo cơ chế driver. Trong ứng dụng server, connection pool nên có validation phù hợp; không nên tự chạy một truy vấn ping trước mọi câu SQL nếu pool đã quản lý validation hiệu quả.

## 3. Statement

### 3.1. Statement dùng khi nào?

`Statement` thực thi câu SQL không cần truyền tham số bind. Nó phù hợp với câu lệnh tĩnh, chẳng hạn truy vấn cố định hoặc một số lệnh quản trị. Ví dụ:

```java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public void listStatuses(Connection connection) throws SQLException {
    String sql = "SELECT status_code, status_name FROM order_status";

    try (Statement statement = connection.createStatement();
         ResultSet resultSet = statement.executeQuery(sql)) {

        while (resultSet.next()) {
            System.out.println(
                resultSet.getString("status_code") + " - " +
                resultSet.getString("status_name")
            );
        }
    }
}
```

`createStatement()` tạo statement gắn với connection. `executeQuery()` dùng cho câu truy vấn trả một `ResultSet`. `ResultSet` là cursor để đọc từng dòng kết quả; gọi `next()` để chuyển tới dòng tiếp theo.

### 3.2. Các phương thức thực thi

| Phương thức | Dùng cho | Kết quả |
|---|---|---|
| `executeQuery(sql)` | Truy vấn trả dữ liệu, thường là `SELECT`. | `ResultSet`. |
| `executeUpdate(sql)` | `INSERT`, `UPDATE`, `DELETE` và một số DDL. | Số dòng bị ảnh hưởng; với DDL thường là 0. |
| `execute(sql)` | Khi chưa biết kết quả là ResultSet hay update count, hoặc cần xử lý kết quả tổng quát. | `true` nếu kết quả đầu là ResultSet, `false` nếu là update count hoặc không có kết quả. |
| `addBatch(sql)` / `executeBatch()` | Gom nhiều câu lệnh tĩnh để thực thi theo batch. | Mảng update count. |

Ví dụ DML với `Statement`:

```java
try (Statement statement = connection.createStatement()) {
    int updated = statement.executeUpdate(
        "UPDATE app_settings SET setting_value = 'ON' " +
        "WHERE setting_name = 'FEATURE_X'"
    );
    System.out.println("Rows updated: " + updated);
}
```

Ví dụ này dùng chuỗi SQL cố định. Khi giá trị đến từ người dùng hoặc dữ liệu động, hãy ưu tiên `PreparedStatement` để bind tham số.

### 3.3. Giới hạn và rủi ro

`Statement` không cung cấp bind parameter. Nếu nối chuỗi đầu vào vào SQL, ứng dụng có nguy cơ SQL injection:

```java
// Không an toàn: userInput có thể làm thay đổi cấu trúc SQL.
String sql = "SELECT * FROM users WHERE username = '" + userInput + "'";
try (Statement statement = connection.createStatement()) {
    ResultSet rs = statement.executeQuery(sql);
}
```

Ngoài nguy cơ injection, nối chuỗi làm SQL thay đổi theo từng giá trị, khiến việc tái sử dụng cursor và theo dõi câu lệnh khó hơn. Dùng `PreparedStatement` để tách SQL khỏi giá trị dữ liệu.

## 4. PreparedStatement

### 4.1. PreparedStatement là gì?

`PreparedStatement` là statement có tham số bind, được tạo từ SQL chứa dấu `?`. Ứng dụng đặt giá trị cho từng vị trí bằng các phương thức `setXxx()` rồi thực thi.

Ví dụ:

```java
String sql = "SELECT customer_id, customer_name " +
             "FROM customers WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String name = rs.getString("customer_name");
            System.out.println(name);
        }
    }
}
```

Vị trí bind bắt đầu từ 1, không phải 0. Dấu `?` đại diện cho giá trị, không phải tên bảng, tên cột, từ khóa SQL hoặc một đoạn biểu thức tùy ý.

### 4.2. Vì sao bind variable quan trọng?

Bind variable giúp:

- Tách dữ liệu đầu vào khỏi cấu trúc SQL, giảm nguy cơ SQL injection.
- Tránh phải tự escape dấu nháy và ký tự đặc biệt trong giá trị.
- Cho phép database tái sử dụng cursor/SQL statement khi câu SQL có cùng cấu trúc và phù hợp cơ chế cursor sharing.
- Truyền giá trị theo kiểu dữ liệu rõ ràng, ví dụ số, ngày giờ, decimal hoặc binary.

Bind variable không tự động làm mọi truy vấn nhanh hơn trong mọi trường hợp. Kế hoạch thực thi còn phụ thuộc thống kê, bind peeking, adaptive cursor sharing, độ chọn lọc và phiên bản Oracle. Tuy nhiên, bind thường là lựa chọn đúng cho giá trị dữ liệu động.

### 4.3. Các kiểu bind thông dụng

| Phương thức | Kiểu dữ liệu Java thường dùng | Gợi ý |
|---|---|---|
| `setString()` | `String` | `VARCHAR2`, `CHAR`; chú ý độ dài và character semantics. |
| `setNString()` | `String` | Cột national character như `NVARCHAR2` khi cần. |
| `setInt()`, `setLong()` | `int`, `long` | Giá trị số nguyên. |
| `setBigDecimal()` | `BigDecimal` | `NUMBER` cần độ chính xác thập phân. |
| `setDate()` | `java.sql.Date` | Ngày theo JDBC; lưu ý Oracle `DATE` còn có phần giờ. |
| `setTimestamp()` | `java.sql.Timestamp` | Oracle `DATE`/`TIMESTAMP` khi cần giữ thành phần thời gian. |
| `setBoolean()` | `boolean` | Kiểm tra kiểu đích và hỗ trợ của phiên bản/driver; Oracle SQL truyền thống không có kiểu SQL BOOLEAN cho mọi ngữ cảnh. |
| `setBytes()` | `byte[]` | Dữ liệu nhị phân có kích thước phù hợp. |
| `setBinaryStream()` | `InputStream` | Dữ liệu nhị phân lớn. |
| `setCharacterStream()` | `Reader` | Văn bản dài/CLOB. |

Ví dụ bind ngày giờ:

```java
String sql = "SELECT order_id, order_date " +
             "FROM orders WHERE order_date >= ? AND order_date < ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, startTimestamp);
    ps.setTimestamp(2, endTimestamp);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý từng dòng.
        }
    }
}
```

Oracle `DATE` lưu cả ngày và thời gian tới giây. Nếu dùng `java.sql.Date` cho cột Oracle `DATE`, phần thời gian có thể không được biểu diễn như mong muốn. Khi phần giờ quan trọng, cân nhắc `Timestamp` hoặc Java time API được driver hỗ trợ, và kiểm thử timezone/precision rõ ràng. Với `TIMESTAMP WITH TIME ZONE`, phải chọn kiểu mapping bảo toàn offset/region theo yêu cầu.

### 4.4. Bind NULL đúng cách

Nếu giá trị có thể là `null`, dùng `setNull(index, sqlType)` hoặc `setObject` với kiểu phù hợp:

```java
if (middleName == null) {
    ps.setNull(2, java.sql.Types.VARCHAR);
} else {
    ps.setString(2, middleName);
}
```

Không nối chuỗi chữ `NULL` vào SQL. SQL `NULL` là giá trị đặc biệt có ngữ nghĩa riêng; phép so sánh với `NULL` phải dùng `IS NULL` hoặc `IS NOT NULL`, không dùng `= NULL`.

### 4.5. Bind không thay thế được tên bảng hoặc tên cột

Đoạn sau không hoạt động như mong đợi:

```java
PreparedStatement ps = connection.prepareStatement(
    "SELECT * FROM ? WHERE customer_id = ?"
);
ps.setString(1, "CUSTOMERS");
ps.setLong(2, customerId);
```

Bind đầu tiên là một giá trị, không thể thay thế identifier `CUSTOMERS`. Nếu tên bảng hoặc cột phải thay đổi theo yêu cầu, dùng allowlist cố định do ứng dụng kiểm soát:

```java
Set<String> allowedSortColumns = Set.of("ORDER_DATE", "TOTAL_AMOUNT");

if (!allowedSortColumns.contains(sortColumn)) {
    throw new IllegalArgumentException("Unsupported sort column");
}

String sql = "SELECT order_id, total_amount FROM orders ORDER BY " +
             sortColumn + " DESC";
```

Chỉ nối identifier sau khi kiểm tra allowlist; các giá trị lọc vẫn phải bind bằng `?`. Không dùng trực tiếp identifier do client gửi vào SQL.

### 4.6. Dùng lại PreparedStatement

Một `PreparedStatement` có thể được dùng nhiều lần trên cùng connection bằng cách đặt lại giá trị bind:

```java
String sql = "SELECT order_id FROM orders WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (long customerId : customerIds) {
        ps.setLong(1, customerId);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getLong("order_id"));
            }
        }
    }
}
```

Đóng `ResultSet` trước khi thực thi lại statement. Prepared statement caching của Oracle JDBC có thể giúp tái sử dụng statement trong một số cấu hình, nhưng không nên dựa vào cache để bỏ qua việc đóng tài nguyên.

### 4.7. Batch DML

Khi cần thực hiện nhiều thao tác cùng cấu trúc, `PreparedStatement` hỗ trợ batch:

```java
String sql = "INSERT INTO audit_events(event_id, event_type, created_at) " +
             "VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    connection.setAutoCommit(false);

    for (AuditEvent event : events) {
        ps.setLong(1, event.id());
        ps.setString(2, event.type());
        ps.setTimestamp(3, event.createdAt());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
    connection.commit();
}
```

Batch giảm số lần round trip và có thể cải thiện throughput. Tuy nhiên, batch rất lớn có thể dùng nhiều bộ nhớ hoặc tạo transaction dài. Hãy chia batch theo kích thước phù hợp, đo trên dữ liệu đại diện và quản lý commit theo yêu cầu nghiệp vụ.

Kết quả `executeBatch()` có thể chứa số dòng cập nhật, `Statement.SUCCESS_NO_INFO` hoặc `Statement.EXECUTE_FAILED`. Nếu có lỗi, JDBC có thể ném `BatchUpdateException` và cung cấp update counts đã hoàn tất trước lỗi; cách driver thực thi batch và mức độ thành công từng phần cần được xử lý theo tài liệu driver.

Ví dụ xử lý lỗi batch:

```java
try {
    ps.executeBatch();
    connection.commit();
} catch (java.sql.BatchUpdateException ex) {
    connection.rollback();
    int[] updateCounts = ex.getUpdateCounts();
    // Ghi nhận số liệu kỹ thuật; không ghi dữ liệu nhạy cảm.
    throw ex;
}
```

Nếu transaction manager đang quản lý connection, không tự gọi `commit()`/`rollback()` trong repository. Hãy để transaction boundary do một lớp thống nhất điều khiển.

## 5. CallableStatement

### 5.1. Dùng để gọi stored procedure hoặc function

`CallableStatement` mở rộng `PreparedStatement` để gọi stored procedure hoặc function. Trong Oracle, procedure/function thường được viết bằng PL/SQL và có thể nằm trong package.

Gọi procedure bằng JDBC escape syntax:

```java
CallableStatement cs = connection.prepareCall(
    "{call app_customer_pkg.update_status(?, ?)}"
);
```

Hoặc dùng anonymous PL/SQL block:

```java
CallableStatement cs = connection.prepareCall(
    "BEGIN app_customer_pkg.update_status(?, ?); END;"
);
```

JDBC escape syntax giúp driver xử lý lời gọi theo chuẩn JDBC. PL/SQL block hữu ích khi cần gọi nhiều thao tác hoặc dùng cú pháp Oracle cụ thể.

### 5.2. IN parameter

Tham số `IN` được truyền tương tự `PreparedStatement`:

```java
String call = "{call app_customer_pkg.update_status(?, ?)}";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, customerId);
    cs.setString(2, "ACTIVE");
    cs.execute();
}
```

Thứ tự tham số phải khớp chữ ký procedure. Nếu package overload nhiều procedure cùng tên, kiểu và thứ tự bind phải đủ để Oracle xác định overload đúng.

### 5.3. OUT parameter

Với tham số `OUT`, cần đăng ký kiểu SQL trước khi thực thi:

```java
String call = "{call app_customer_pkg.get_customer_name(?, ?)}";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, customerId);
    cs.registerOutParameter(2, java.sql.Types.VARCHAR);

    cs.execute();

    String customerName = cs.getString(2);
    System.out.println(customerName);
}
```

`registerOutParameter(2, Types.VARCHAR)` khai báo vị trí thứ hai là output kiểu chuỗi. Chỉ đọc OUT value sau khi procedure đã thực thi thành công.

### 5.4. IN OUT parameter

Tham số `IN OUT` vừa nhận giá trị đầu vào vừa trả giá trị mới:

```java
String call = "{call app_counter_pkg.increase_counter(?)}";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setInt(1, currentValue);
    cs.registerOutParameter(1, java.sql.Types.INTEGER);
    cs.execute();

    int updatedValue = cs.getInt(1);
}
```

Vị trí bind vừa được set vừa được đăng ký output. Kiểu Java/SQL phải tương thích với khai báo PL/SQL.

### 5.5. Gọi function trả về giá trị

Với function, vị trí đầu tiên thường dành cho return value:

```java
String call = "{? = call app_tax_pkg.calculate_tax(?)}";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.registerOutParameter(1, java.sql.Types.NUMERIC);
    cs.setBigDecimal(2, taxableAmount);
    cs.execute();

    BigDecimal tax = cs.getBigDecimal(1);
}
```

Thứ tự tham số là: return value trước, rồi đến các tham số của function. Kiểu `NUMBER` thường được ánh xạ sang `BigDecimal` để giữ độ chính xác thập phân.

### 5.6. REF CURSOR

Procedure Oracle có thể trả một `REF CURSOR` để ứng dụng đọc nhiều dòng. Với JDBC driver hỗ trợ `Types.REF_CURSOR`, ví dụ:

```java
String call = "{call app_report_pkg.get_orders(?, ?)}";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, customerId);
    cs.registerOutParameter(2, java.sql.Types.REF_CURSOR);
    cs.execute();

    try (ResultSet rs = (ResultSet) cs.getObject(2)) {
        while (rs.next()) {
            long orderId = rs.getLong("ORDER_ID");
            BigDecimal amount = rs.getBigDecimal("TOTAL_AMOUNT");
            // Xử lý dòng kết quả.
        }
    }
}
```

Một số phiên bản Oracle JDBC cũ dùng `OracleTypes.CURSOR` từ package Oracle extension thay cho `Types.REF_CURSOR`. Chọn cách đăng ký theo JDK và driver đang dùng. Đóng `ResultSet` và `CallableStatement` sau khi đọc xong; cursor là tài nguyên database, không nên để mở lâu.

### 5.7. Khi nào nên dùng stored procedure?

Stored procedure có thể phù hợp khi:

- Logic nghiệp vụ cần chạy gần dữ liệu và được nhiều ứng dụng dùng chung.
- Cần gom nhiều thao tác SQL trong một lời gọi để giảm round trip.
- Muốn quản lý quyền thông qua `EXECUTE` trên package/procedure.
- Có quy trình xử lý dữ liệu lớn hoặc logic cần transaction boundary được định nghĩa rõ.

Không nên chuyển mọi câu SQL đơn giản thành stored procedure chỉ vì có `CallableStatement`. Hãy chọn nơi đặt logic dựa trên khả năng bảo trì, kiểm thử, phân quyền và cách triển khai ứng dụng.

## 6. ResultSet và đọc dữ liệu

### 6.1. ResultSet là cursor

`ResultSet` giữ con trỏ tới tập kết quả của câu truy vấn. Ban đầu con trỏ nằm trước dòng đầu tiên; `next()` di chuyển tới dòng tiếp theo và trả `false` khi hết dữ liệu.

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT employee_id, first_name, salary FROM employees WHERE department_id = ?")) {
    ps.setInt(1, departmentId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("EMPLOYEE_ID");
            String name = rs.getString("FIRST_NAME");
            BigDecimal salary = rs.getBigDecimal("SALARY");
        }
    }
}
```

Có thể đọc cột theo index bắt đầu từ 1 hoặc theo column label. Dùng label thường dễ đọc hơn và ít phụ thuộc thứ tự cột. Nếu truy vấn có hai cột cùng label, nên đặt alias rõ ràng.

### 6.2. Xử lý SQL NULL

Các getter primitive như `getInt()` hoặc `getLong()` trả về 0 khi SQL value là `NULL`. Để phân biệt `NULL` với giá trị 0, gọi `wasNull()` ngay sau getter:

```java
long managerId = rs.getLong("MANAGER_ID");
if (rs.wasNull()) {
    // MANAGER_ID là SQL NULL.
}
```

Với kiểu object như `getBigDecimal()` hoặc `getString()`, JDBC thường trả `null` nếu SQL value là `NULL`.

### 6.3. ResultSet type và concurrency

Mặc định, statement thường tạo ResultSet forward-only và read-only. Có thể yêu cầu loại khác:

```java
Statement statement = connection.createStatement(
    ResultSet.TYPE_FORWARD_ONLY,
    ResultSet.CONCUR_READ_ONLY
);
```

Không phải mọi loại ResultSet đều được driver hoặc database hỗ trợ đầy đủ. Scrollable hoặc updatable ResultSet có thể tốn tài nguyên và có giới hạn; trong ứng dụng Oracle, thường nên dùng truy vấn rõ ràng và DML riêng thay vì phụ thuộc cập nhật qua cursor.

### 6.4. Fetch size và truy vấn nhiều dòng

JDBC cho phép gợi ý số dòng lấy mỗi lần từ database:

```java
ps.setFetchSize(500);
```

Fetch size lớn hơn có thể giảm số round trip khi đọc nhiều dòng, nhưng tăng bộ nhớ phía client. Giá trị phù hợp phụ thuộc kích thước row, độ trễ mạng, số dòng và giới hạn heap. Oracle JDBC còn có cơ chế row prefetch; fetch size và cấu hình prefetch cần được hiểu theo driver version. Đo hiệu năng bằng dữ liệu thực tế thay vì đặt một giá trị rất lớn cho mọi truy vấn.

Nếu truy vấn có thể trả hàng triệu dòng, cân nhắc lọc dữ liệu, phân trang theo khóa, streaming hoặc xử lý theo batch. Không giữ một `ResultSet` và connection mở trong khi ứng dụng chờ người dùng thao tác.

### 6.5. Đọc LOB bằng stream

Với CLOB/BLOB lớn, không nhất thiết tải toàn bộ nội dung vào bộ nhớ. Có thể dùng stream:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT document_content FROM documents WHERE document_id = ?")) {
    ps.setLong(1, documentId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (java.io.Reader reader = rs.getCharacterStream("DOCUMENT_CONTENT")) {
                char[] buffer = new char[8192];
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    // Ghi hoặc xử lý từng đoạn.
                }
            }
        }
    }
}
```

Stream LOB thường phụ thuộc ResultSet/connection còn mở. Hãy tiêu thụ stream trước khi đóng cursor và connection, đồng thời xử lý IOException bên cạnh SQLException.

## 7. Quản lý tài nguyên bằng try-with-resources

`Connection`, `Statement`, `PreparedStatement`, `CallableStatement` và `ResultSet` đều là tài nguyên cần được đóng. Cách an toàn và dễ đọc là try-with-resources:

```java
String sql = "SELECT customer_id, customer_name FROM customers WHERE status = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setString(1, "ACTIVE");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý kết quả.
        }
    }
}
```

Khi rời khỏi block, Java tự đóng tài nguyên theo thứ tự ngược lại với lúc khai báo. Đóng statement cũng đóng ResultSet hiện tại của nó; tuy nhiên, khai báo ResultSet riêng vẫn làm rõ ownership và bảo đảm cursor được đóng đúng lúc.

Không chỉ đóng connection khi có exception. Nếu để rò rỉ ResultSet hoặc statement, ứng dụng có thể giữ cursor, session và tài nguyên server lâu hơn cần thiết. Với connection pool, rò rỉ connection có thể khiến pool cạn và các request khác phải chờ.

## 8. Xử lý SQLException

### 8.1. Thông tin trong SQLException

`SQLException` có thể cung cấp:

- `getMessage()`: thông điệp lỗi.
- `getSQLState()`: mã trạng thái SQL theo driver.
- `getErrorCode()`: vendor error code; với Oracle thường là mã lỗi số.
- `getNextException()`: lỗi tiếp theo trong chuỗi exception.
- `getCause()`: nguyên nhân gốc nếu có.

Ví dụ:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT customer_id FROM customers WHERE customer_id = ?")) {
    ps.setLong(1, customerId);
    ps.executeQuery();
} catch (SQLException ex) {
    System.err.println("SQLState: " + ex.getSQLState());
    System.err.println("Vendor code: " + ex.getErrorCode());
    System.err.println("Message: " + ex.getMessage());

    for (SQLException next = ex.getNextException();
         next != null;
         next = next.getNextException()) {
        System.err.println("Next SQL error: " + next.getMessage());
    }
    throw ex;
}
```

Trong production, dùng logging framework và correlation ID; tránh log password, token, bind value nhạy cảm hoặc toàn bộ dữ liệu khách hàng. Thông tin SQL và error code có thể hữu ích cho điều tra nhưng cần được kiểm soát quyền đọc.

### 8.2. Phân loại lỗi và retry

Không retry mọi `SQLException`. Lỗi sai cú pháp, thiếu quyền hoặc constraint violation thường không tự hết khi chạy lại. Lỗi network tạm thời hoặc transaction serialization có thể retry trong một số trường hợp, nhưng cần xác định transaction có thể chạy lại an toàn hay không.

Một retry policy nên:

- Giới hạn số lần retry và dùng backoff.
- Chỉ retry lỗi được phân loại là transient.
- Rollback transaction lỗi trước khi retry.
- Bảo đảm thao tác idempotent hoặc có khóa chống xử lý trùng.
- Không retry một thao tác thanh toán/ghi dữ liệu khi chưa biết lần trước đã commit hay chưa.

## 9. Chọn đúng interface cho từng tình huống

| Interface | Khi nên dùng | Điểm cần nhớ |
|---|---|---|
| `Connection` | Quản lý session, transaction và tạo statement. | Một connection cho một đơn vị công việc; đóng/trả pool đúng lúc. |
| `Statement` | SQL tĩnh, không có giá trị đầu vào động. | Không nối dữ liệu người dùng vào SQL. |
| `PreparedStatement` | SQL có tham số, truy vấn/DML lặp lại, batch. | Dùng `?` và `setXxx`; bind không thay thế identifier. |
| `CallableStatement` | Gọi PL/SQL procedure/function, OUT hoặc REF CURSOR. | Đăng ký OUT parameter trước khi execute; quản lý cursor trả về. |

Một quy tắc thực tế: nếu SQL có giá trị dữ liệu đến từ bên ngoài, ưu tiên `PreparedStatement`; nếu cần gọi logic PL/SQL đã định nghĩa, dùng `CallableStatement`; chỉ dùng `Statement` cho SQL tĩnh đã được kiểm soát.

## 10. Ví dụ kết hợp đầy đủ

Ví dụ repository đọc khách hàng bằng `PreparedStatement`, sau đó gọi procedure lấy số đơn hàng bằng `CallableStatement`. `DataSource` được inject từ cấu hình ứng dụng:

```java
import javax.sql.DataSource;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

public class CustomerService {
    private final DataSource dataSource;

    public CustomerService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public CustomerSummary loadSummary(long customerId) throws SQLException {
        String name;
        int orderCount;

        try (Connection connection = dataSource.getConnection()) {
            String query =
                "SELECT customer_name FROM customers WHERE customer_id = ?";

            try (PreparedStatement ps = connection.prepareStatement(query)) {
                ps.setLong(1, customerId);

                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        return null;
                    }
                    name = rs.getString("CUSTOMER_NAME");
                }
            }

            String call = "{call app_order_pkg.get_order_count(?, ?)}";
            try (CallableStatement cs = connection.prepareCall(call)) {
                cs.setLong(1, customerId);
                cs.registerOutParameter(2, Types.INTEGER);
                cs.execute();
                orderCount = cs.getInt(2);
            }
        }

        return new CustomerSummary(customerId, name, orderCount);
    }
}
```

`CustomerSummary` là DTO do ứng dụng định nghĩa. Ví dụ dùng một connection cho hai thao tác đọc, đóng từng statement/result set ngay sau khi dùng và đóng connection khi hoàn thành. Nếu hai thao tác phải nhìn thấy cùng một snapshot nhất quán hoặc nằm trong một transaction nghiệp vụ, cần thiết lập transaction/isolation phù hợp thay vì dựa vào mặc định.

## 11. Oracle JDBC và một số lưu ý đặc thù

### 11.1. NUMBER và độ chính xác

Oracle `NUMBER` có thể biểu diễn số thập phân với độ chính xác cao. Với tiền tệ hoặc giá trị cần giữ chính xác, dùng `BigDecimal` và `setBigDecimal()`/`getBigDecimal()` thay vì `double`/`float`, vì floating point có thể tạo sai số nhị phân.

### 11.2. DATE và TIMESTAMP

Oracle `DATE` lưu năm, tháng, ngày, giờ, phút và giây; nó không tương đương hoàn toàn với `java.sql.Date` chỉ biểu diễn ngày theo ý nghĩa JDBC. Nếu cần giữ phần thời gian, dùng mapping phù hợp như `Timestamp` hoặc Java time API được driver hỗ trợ. Với `TIMESTAMP WITH TIME ZONE` và `TIMESTAMP WITH LOCAL TIME ZONE`, cần hiểu quy tắc timezone của database/session và cách driver chuyển đổi.

### 11.3. LOB và streaming

Với CLOB/BLOB lớn, ưu tiên stream thay vì tải toàn bộ vào `String` hoặc `byte[]`. LOB locator và stream có thể phụ thuộc connection/cursor còn mở. Đóng tài nguyên đúng thứ tự và không chuyển stream ra khỏi phạm vi sống của connection.

### 11.4. REF CURSOR

Oracle PL/SQL thường dùng `SYS_REFCURSOR` để trả tập kết quả. JDBC driver hiện đại có thể hỗ trợ `Types.REF_CURSOR`; driver cũ có thể cần `OracleTypes.CURSOR`. Kiểm tra version của JDK và `ojdbc` trước khi chọn API.

### 11.5. Statement caching và fetch behavior

Oracle JDBC có thể hỗ trợ implicit statement cache và row prefetch. Cấu hình pool/driver có thể ảnh hưởng đến cách tái sử dụng statement và số dòng lấy mỗi round trip. Tránh bật cache hoặc đặt fetch size quá cao mà không đo memory, cursor và workload thực tế.

### 11.6. TCPS và wallet

Kết nối JDBC có thể dùng TCPS và Oracle wallet để bảo vệ đường truyền hoặc xác thực theo cấu hình. URL, trust material, certificate và wallet phải được quản lý theo chính sách bảo mật; không tắt kiểm tra certificate chỉ để làm cho kết nối chạy được.

## 12. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `SQLException: No suitable driver` | Thiếu `ojdbc` hoặc dependency không có trong runtime classpath. | Kiểm tra dependency, packaging và class loader. |
| `ORA-01017` | Username/password sai hoặc kết nối nhầm service. | Kiểm tra credential, service name và nguồn secret. |
| `ORA-28000` / `ORA-28001` | Account bị khóa hoặc password hết hạn. | Kiểm tra trạng thái user/profile và quy trình DBA. |
| `ORA-12514` | Listener không nhận diện service trong connect descriptor. | Xác nhận service name, listener registration và URL. |
| `ORA-12170` | Kết nối timeout. | Kiểm tra network, firewall, listener và timeout cấu hình. |
| `ORA-00942` | Bảng/view không tồn tại trong schema phân giải hoặc thiếu quyền. | Kiểm tra owner, synonym, current schema và grants. |
| `ORA-01008` | Thiếu bind variable. | Kiểm tra số lượng dấu `?` và mọi vị trí `setXxx`. |
| `ORA-01722` | Chuyển đổi chuỗi sang số không hợp lệ. | Bind đúng kiểu, kiểm tra dữ liệu và implicit conversion. |
| `ORA-00001` | Vi phạm unique constraint. | Xác định khóa trùng; không retry mù quáng. |
| `ORA-08177` | Transaction serializable không thể tiếp tục do xung đột. | Rollback và cân nhắc retry có giới hạn nếu nghiệp vụ cho phép. |
| Connection pool cạn | Rò rỉ connection, transaction giữ quá lâu hoặc pool quá nhỏ. | Dùng try-with-resources, theo dõi borrow time và cấu hình pool. |

Khi điều tra, ghi lại Oracle error code, SQLState, thời điểm, service và correlation ID. Không ghi mật khẩu hoặc dữ liệu nhạy cảm vào log.

## 13. Quy tắc thực hành tốt

- Dùng `DataSource` và connection pool trong ứng dụng server; dùng `DriverManager` chủ yếu cho ví dụ hoặc công cụ đơn giản.
- Mượn connection cho một đơn vị công việc và luôn đóng/trả pool đúng lúc.
- Dùng try-with-resources cho connection, statement, callable statement và result set.
- Dùng `PreparedStatement` cho giá trị động; không nối dữ liệu người dùng vào SQL.
- Bind đúng kiểu dữ liệu, đặc biệt với `NUMBER`, ngày giờ, `NULL` và LOB.
- Dùng `CallableStatement` cho procedure/function và đăng ký OUT parameter đúng vị trí/kiểu.
- Quản lý transaction ở một tầng nhất quán; không để nhiều lớp cùng commit/rollback tùy tiện.
- Chia batch hợp lý và xử lý `BatchUpdateException`.
- Đóng ResultSet trước khi dùng lại statement hoặc trả connection về pool.
- Đặt fetch size theo dữ liệu và độ trễ thực tế; tránh tải toàn bộ kết quả lớn vào heap.
- Phân loại SQLException trước khi retry; thao tác retry phải an toàn hoặc idempotent.
- Không chia sẻ connection đồng thời giữa các thread.
- Kiểm tra compatibility giữa JDK, Oracle JDBC driver và Oracle Database.

## Kết luận

`Connection` quản lý session và transaction; `Statement` thực thi SQL tĩnh; `PreparedStatement` truyền giá trị bằng bind parameter; `CallableStatement` gọi procedure/function và nhận kết quả qua OUT parameter hoặc REF CURSOR. Chọn đúng interface giúp code dễ bảo trì, giảm nguy cơ SQL injection và kiểm soát tài nguyên tốt hơn. Khi kết hợp `DataSource`/connection pool, try-with-resources, transaction boundary rõ ràng, bind đúng kiểu và xử lý lỗi có chủ đích, ứng dụng Java có thể làm việc với Oracle Database ổn định và an toàn hơn.

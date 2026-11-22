# Quản lý kết nối, statement và tập kết quả

## 1. JDBC là cầu nối giữa Java và cơ sở dữ liệu

Một ứng dụng Java thường thực hiện một chuỗi công việc:

1. Lấy một kết nối đến database.
2. Chuẩn bị câu SQL và truyền tham số.
3. Gửi câu lệnh cho database thực thi.
4. Đọc các hàng trả về hoặc số hàng bị tác động.
5. Hoàn tất hoặc rollback transaction nếu có.
6. Đóng các tài nguyên đã mở để trả kết nối về pool hoặc giải phóng socket.

JDBC (*Java Database Connectivity*) cung cấp API chuẩn cho các bước đó. Các interface quan trọng nhất:

| API | Vai trò |
| --- | --- |
| `DataSource` | Cung cấp kết nối; thường được cấu hình để sử dụng connection pool |
| `Connection` | Đại diện một phiên kết nối và quản lý transaction |
| `Statement` | Thực thi SQL được tạo thành chuỗi |
| `PreparedStatement` | Thực thi SQL có tham số bind |
| `CallableStatement` | Gọi stored procedure/function theo khả năng driver |
| `ResultSet` | Con trỏ đọc tập hàng do truy vấn trả về |
| `ResultSetMetaData` | Mô tả cột của một tập kết quả |
| `DatabaseMetaData` | Mô tả DBMS, driver, schema và khả năng JDBC |
| `SQLException` | Mô tả lỗi JDBC/SQL |

Một luồng xử lý cơ bản:

~~~text
DataSource
    |
    | getConnection()
    v
Connection
    |
    | prepareStatement(sql)
    v
PreparedStatement
    |
    | setXxx(...) + executeQuery()
    v
ResultSet
    |
    | next() -> đọc từng cột
    v
Java objects / DTO
    |
    | đóng ResultSet, Statement, Connection
    v
Connection được trả về pool hoặc được giải phóng
~~~

Bài này tập trung vào **quản lý kết nối, statement và tập kết quả** trong Java JDBC. Các ví dụ dùng API JDBC phổ biến, cú pháp SQL gần ANSI/PostgreSQL và kiểu Java chuẩn. Chi tiết kết nối, kiểu dữ liệu, generated keys, streaming và stored procedure có thể phụ thuộc driver.

## 2. Chuẩn bị JDBC driver và DataSource

### 2.1. JDBC API và JDBC driver là hai thành phần khác nhau

JDBC API nằm trong Java (package `java.sql` và `javax.sql`). Nhưng để kết nối PostgreSQL, MySQL, SQL Server, Oracle hoặc SQLite, ứng dụng còn cần **JDBC driver tương ứng**.

Ví dụ:

- PostgreSQL: PostgreSQL JDBC Driver.
- MySQL: MySQL Connector/J.
- SQL Server: Microsoft JDBC Driver for SQL Server.
- Oracle: Oracle JDBC Driver.
- SQLite: SQLite JDBC driver.

Driver thực hiện giao thức và chuyển lời gọi JDBC thành giao tiếp mà DBMS hiểu. Cùng một đoạn Java có thể làm việc với nhiều hệ, nhưng SQL dialect, kiểu dữ liệu và tính năng mở rộng vẫn có thể khác nhau.

Với Maven, dependency có dạng:

~~~xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <version><!-- Chọn phiên bản phù hợp với môi trường --></version>
</dependency>
~~~

Không sao chép một phiên bản cũ từ ví dụ trên mạng vào dự án mới. Chọn phiên bản driver tương thích với Java runtime, DBMS và chính sách cập nhật của dự án.

### 2.2. DataSource là điểm vào nên dùng trong ứng dụng

`DataSource` là abstraction chuẩn để lấy connection:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

public final class ConnectionExample {
    private final DataSource dataSource;

    public ConnectionExample(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void checkConnection() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            System.out.println(
                "Connected: " + !connection.isClosed()
            );
        }
    }
}
~~~

Ứng dụng nhận `DataSource` từ cấu hình hoặc dependency injection. Lợi ích:

- Tách cấu hình database khỏi code truy vấn.
- Có thể thay driver/database mà không thay toàn bộ tầng repository.
- Hỗ trợ connection pool.
- Dễ kiểm thử bằng DataSource giả hoặc database test.

### 2.3. DriverManager phù hợp cho ví dụ nhỏ

Một chương trình đơn giản có thể dùng `DriverManager`:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class DirectConnectionDemo {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("DB_URL");
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {
            System.out.println("Connected to database");
        }
    }
}
~~~

Không đặt mật khẩu thật trong source code, Git hoặc log. Dùng biến môi trường, secret manager hoặc cơ chế cấu hình bảo mật của nền tảng triển khai.

JDBC hiện đại hỗ trợ tự phát hiện driver thông qua cơ chế service provider khi driver được đưa vào classpath/module path. Các ứng dụng mới thường không cần gọi `Class.forName("...Driver")` thủ công, trừ môi trường hoặc driver cũ có yêu cầu riêng.

### 2.4. Không tạo một connection mới cho từng câu SQL trong ứng dụng có tải

Một kết nối database có thể cần thiết lập socket, xác thực, thương lượng TLS và cấp phát tài nguyên server. Nếu mỗi lần query đều tạo connection vật lý mới, chi phí và số phiên database tăng nhanh.

Trong ứng dụng server, thường dùng **connection pool**:

~~~text
Application threads
   |       |       |
   v       v       v
Connection Pool
   |       |       |
   +-------+-------+
           |
     Database server
~~~

Pool giữ một số kết nối vật lý để tái sử dụng. Mỗi request mượn một connection, thực hiện công việc ngắn, rồi đóng connection logic để trả lại pool.

### 2.5. Ví dụ cấu hình HikariCP

HikariCP là một thư viện pool phổ biến; đây là ví dụ tùy chọn, không phải một phần của JDBC chuẩn:

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DataSourceFactory {
    public static HikariDataSource create() {
        HikariConfig config = new HikariConfig();

        config.setJdbcUrl(System.getenv("DB_URL"));
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASSWORD"));

        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(5_000);
        config.setValidationTimeout(2_000);
        config.setMaxLifetime(1_800_000);

        return new HikariDataSource(config);
    }
}
~~~

Đóng pool khi ứng dụng dừng:

~~~java
try (HikariDataSource dataSource =
         DataSourceFactory.create()) {
    // Khởi tạo service và chạy ứng dụng trong phạm vi phù hợp.
}
~~~

Trong ứng dụng web, DataSource thường có vòng đời ứng dụng và được framework quản lý. Không tạo rồi đóng pool cho từng request.

Các con số pool trong ví dụ chỉ để minh họa. Kích thước hợp lý phụ thuộc số instance ứng dụng, số worker, giới hạn kết nối DB, thời gian query và mức đồng thời. Pool quá lớn có thể làm database quá tải; pool quá nhỏ có thể khiến request chờ lâu.

## 3. Vòng đời Connection

### 3.1. Lấy và đóng connection

~~~java
try (Connection connection = dataSource.getConnection()) {
    // Thực hiện SQL tại đây.
}
~~~

`Connection` triển khai `AutoCloseable`, nên có thể dùng try-with-resources.

- Khi dùng connection trực tiếp, `close()` giải phóng kết nối/tài nguyên.
- Khi lấy connection từ pool, `close()` trên connection proxy thường **trả connection về pool** thay vì đóng socket vật lý.
- Dù vậy, phải gọi `close()`. Không đóng sẽ giữ connection bị mượn và có thể làm cạn pool.

Đừng giữ connection trong một field static hoặc một biến singleton để mọi request dùng chung.

### 3.2. Connection là tài nguyên có trạng thái

Một connection mang trạng thái, chẳng hạn:

- Auto-commit bật hay tắt;
- Transaction đang mở;
- Isolation level;
- Read-only flag;
- Catalog/schema hiện hành;
- Network timeout;
- Các session settings của DBMS;
- Tài nguyên statement/result set còn mở.

Connection pool thường cố reset một số trạng thái khi connection được trả về, nhưng không nên dựa vào reset mọi session setting tùy biến của mọi driver. Nếu code thay đổi trạng thái connection, phải quản lý và khôi phục đúng cách.

### 3.3. Không chia sẻ một Connection cho nhiều thread cùng thao tác

JDBC không cung cấp bảo đảm chung rằng `Connection` có thể được nhiều thread sử dụng đồng thời một cách an toàn. Một transaction cũng gắn với connection cụ thể.

Mẫu dễ lỗi:

~~~java
// Không nên: nhiều request cùng sửa một connection dùng chung.
public final class BadRepository {
    private final Connection sharedConnection;
}
~~~

Một request có thể bật transaction, request khác chạy query trên cùng connection, rồi một request commit hoặc rollback transaction của request còn lại.

Mẫu phù hợp hơn:

~~~java
public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Order findById(long orderId) throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            return findById(connection, orderId);
        }
    }

    // Phương thức nhận connection được gọi trong transaction do caller quản lý.
    public Order findById(Connection connection, long orderId)
            throws SQLException {
        // Thực hiện query với connection đã được cấp.
        return null; // Phần mapping được minh họa ở mục 9.
    }
}
~~~

Connection được mượn theo đơn vị công việc/transaction, không chia sẻ tùy tiện giữa các thread.

### 3.4. isClosed và isValid không thay thế quản lý lifecycle

`connection.isClosed()` chỉ cho biết connection đã được đóng theo trạng thái JDBC. Nó không phải phép kiểm tra sức khỏe đầy đủ cho mọi tình huống mạng.

`connection.isValid(timeoutSeconds)` có thể kiểm tra khả năng kết nối theo driver, nhưng gọi nó trước mọi câu SQL thường là thừa: giữa lúc kiểm tra và lúc query vẫn có thể mất mạng (*time-of-check to time-of-use*). Hãy để pool/driver quản lý validation và xử lý lỗi kết nối tại thao tác thực tế.

## 4. Statement, PreparedStatement và CallableStatement

Ba interface đều thực thi SQL nhưng có mục đích khác nhau.

| Interface | Dùng cho | Tham số bind | Ví dụ |
| --- | --- | --- | --- |
| `Statement` | SQL tĩnh, không có giá trị đầu vào cần bind | Không | `SELECT CURRENT_DATE` |
| `PreparedStatement` | SQL có tham số | Có dấu `?` | `SELECT ... WHERE id = ?` |
| `CallableStatement` | Gọi stored procedure/function theo khả năng DBMS | Có tham số IN/OUT tùy DBMS | `{ call recalculate(?) }` |

Trong ứng dụng, `PreparedStatement` thường là lựa chọn mặc định cho SQL có tham số.

### 4.1. Statement

~~~java
try (Connection connection = dataSource.getConnection();
     Statement statement = connection.createStatement();
     ResultSet resultSet =
         statement.executeQuery("SELECT CURRENT_DATE")) {

    if (resultSet.next()) {
        System.out.println(resultSet.getDate(1));
    }
}
~~~

`Statement` thích hợp với câu SQL cố định, không ghép dữ liệu người dùng vào chuỗi. Không dùng cách nối chuỗi để tạo điều kiện tìm kiếm theo input.

### 4.2. PreparedStatement

~~~java
String sql = """
    SELECT order_id, order_status
    FROM orders
    WHERE customer_id = ?
      AND order_status = ?
    ORDER BY order_id
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql)) {

    statement.setLong(1, 1L);
    statement.setString(2, "PAID");

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            String status = resultSet.getString("order_status");

            System.out.println(orderId + ": " + status);
        }
    }
}
~~~

Điểm cần nhớ:

- Dấu `?` là placeholder cho **giá trị**.
- Vị trí tham số bắt đầu từ **1**, không phải 0.
- Phải bind đủ tham số cần thiết trước khi execute.
- Một `PreparedStatement` có thể được dùng lại với nhiều bộ giá trị nếu reset/bind lại đúng.
- Driver/database có thể tối ưu việc chuẩn bị/thực thi; không khẳng định mọi PreparedStatement luôn được compile một lần duy nhất ở server.

### 4.3. PreparedStatement giúp tránh SQL injection

Không an toàn:

~~~java
String sql =
    "SELECT * FROM users WHERE email = '" + email + "'";
Statement statement = connection.createStatement();
ResultSet resultSet = statement.executeQuery(sql);
~~~

Nếu `email` chứa chuỗi được tạo có chủ ý để thay đổi cấu trúc SQL, câu truy vấn có thể bị thao túng.

An toàn hơn:

~~~java
String sql = "SELECT user_id, email FROM users WHERE email = ?";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {
    statement.setString(1, email);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Đọc dữ liệu.
        }
    }
}
~~~

Driver bind giá trị như một tham số, không diễn giải nội dung tham số thành mệnh đề SQL.

**PreparedStatement không tự động làm mọi câu SQL động an toàn.** Nếu ứng dụng nối tên bảng, tên cột hoặc từ khóa sort do người dùng nhập, placeholder `?` thường không thể thay cho identifier.

### 4.4. Không thể bind tên cột bằng dấu ?

Sai ý định:

~~~java
String sql = "SELECT ? FROM orders";
statement.setString(1, "order_id");
~~~

Dấu `?` được hiểu là **một giá trị**, không phải tên cột. Truy vấn có thể trả chuỗi literal "order_id" cho mỗi hàng thay vì đọc cột đó.

Nếu cần sort động, dùng whitelist:

~~~java
String sortColumn;

switch (requestedSort) {
    case "date":
        sortColumn = "ordered_at";
        break;
    case "amount":
        sortColumn = "total_amount";
        break;
    default:
        sortColumn = "order_id";
}

String sql =
    "SELECT order_id, ordered_at, total_amount " +
    "FROM orders ORDER BY " + sortColumn;
~~~

Chỉ những identifier được chọn từ whitelist do ứng dụng kiểm soát mới được nối vào SQL. Các **giá trị lọc** vẫn phải bind bằng PreparedStatement.

### 4.5. Bind kiểu dữ liệu chính xác

~~~java
statement.setLong(1, orderId);
statement.setString(2, status);
statement.setBigDecimal(3, amount);
statement.setBoolean(4, active);
statement.setDate(5, sqlDate);
statement.setTimestamp(6, timestamp);
~~~

Đối với SQL NULL:

~~~java
statement.setNull(1, java.sql.Types.VARCHAR);
~~~

Hoặc dùng `setObject` với kiểu phù hợp khi driver hỗ trợ. Không truyền chuỗi "NULL" để thay cho SQL NULL.

JDBC 4.2 trở lên có hỗ trợ làm việc với nhiều kiểu thời gian Java hiện đại, ví dụ:

~~~java
statement.setObject(1, java.time.LocalDate.of(2026, 10, 1));
statement.setObject(
    2,
    java.time.OffsetDateTime.parse("2026-10-01T09:00:00+07:00")
);
~~~

Khả năng ánh xạ kiểu thời gian cụ thể còn phụ thuộc driver và kiểu cột DB. Kiểm tra contract của database thay vì giả định mọi kiểu Java có ánh xạ giống nhau.

### 4.6. LIKE và tham số

Nếu tìm chuỗi bắt đầu bằng một tiền tố:

~~~java
String sql =
    "SELECT product_id, product_name " +
    "FROM products WHERE product_name LIKE ?";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {
    statement.setString(1, prefix + "%");
}
~~~

Bind an toàn với SQL injection, nhưng ký tự `%` và `_` vẫn mang ý nghĩa wildcard của LIKE. Nếu người dùng cần tìm literal, phải escape wildcard theo quy tắc DBMS và thêm `ESCAPE` phù hợp.

### 4.7. CallableStatement

Gọi procedure có một tham số IN minh họa:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement statement =
         connection.prepareCall("{ call recalculate_customer(?) }")) {

    statement.setLong(1, 1001L);
    statement.execute();
}
~~~

Procedure `recalculate_customer` là ví dụ giả định; cú pháp call, tên tham số và cách lấy kết quả phụ thuộc DBMS/driver.

Với OUT parameter, đăng ký kiểu trước khi thực thi:

~~~java
try (CallableStatement statement =
         connection.prepareCall("{ call calculate_total(?, ?) }")) {

    statement.setLong(1, 1001L);
    statement.registerOutParameter(2, java.sql.Types.DECIMAL);

    statement.execute();

    java.math.BigDecimal total = statement.getBigDecimal(2);
}
~~~

Không phải mọi database có cùng cú pháp procedure/function call hoặc cùng hỗ trợ OUT parameters. Kiểm tra tài liệu driver khi chuyển hệ.

## 5. Chọn đúng phương thức thực thi

### 5.1. executeQuery

Dùng cho câu SQL trả về một tập kết quả:

~~~java
try (PreparedStatement statement =
         connection.prepareStatement(
             "SELECT order_id FROM orders WHERE customer_id = ?")) {
    statement.setLong(1, 1L);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            System.out.println(resultSet.getLong("order_id"));
        }
    }
}
~~~

`executeQuery()` trả `ResultSet`. Với JDBC chuẩn, dùng nó cho truy vấn cần đọc tập kết quả.

### 5.2. executeUpdate

Dùng cho INSERT, UPDATE, DELETE và các câu không trả một ResultSet thông thường:

~~~java
String sql =
    "UPDATE orders SET order_status = ? WHERE order_id = ?";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {
    statement.setString(1, "PAID");
    statement.setLong(2, 1001L);

    int affectedRows = statement.executeUpdate();
    System.out.println("Affected rows: " + affectedRows);
}
~~~

Số trả về thường là số hàng bị tác động theo ngữ nghĩa driver/DBMS. Với DDL hoặc một số lệnh đặc thù, kết quả có thể là 0. Đừng diễn giải mọi giá trị 0 thành “SQL lỗi”.

### 5.3. execute

Dùng khi câu SQL có thể trả ResultSet hoặc update count, ví dụ một số procedure hoặc batch nhiều kết quả:

~~~java
boolean hasResultSet = statement.execute();

if (hasResultSet) {
    try (ResultSet resultSet = statement.getResultSet()) {
        // Đọc tập kết quả.
    }
} else {
    int updateCount = statement.getUpdateCount();
    // Xử lý update count.
}
~~~

`execute()` trả `true` nếu kết quả đầu tiên là ResultSet, `false` nếu kết quả đầu tiên là update count hoặc không còn kết quả. Với nhiều result sets/update counts, cần dùng `getMoreResults()` và `getUpdateCount()` theo đúng trình tự.

### 5.4. Bảng lựa chọn

| Câu lệnh | Phương thức thường dùng |
| --- | --- |
| SELECT | `executeQuery()` |
| INSERT | `executeUpdate()` hoặc batch |
| UPDATE | `executeUpdate()` |
| DELETE | `executeUpdate()` |
| DDL CREATE/ALTER/DROP | `executeUpdate()` hoặc `execute()` theo nhu cầu/driver |
| Procedure có nhiều kết quả | `execute()` và đọc các kết quả tiếp theo |

Không gọi `executeQuery()` cho UPDATE hoặc `executeUpdate()` cho SELECT chỉ vì hai phương thức có vẻ tương tự. Chọn theo loại kết quả mong đợi.

## 6. ResultSet là con trỏ đọc hàng

### 6.1. Cursor bắt đầu trước hàng đầu tiên

Sau `executeQuery()`, `ResultSet` không tự đứng ở hàng đầu. Cursor ban đầu ở vị trí **before first**.

~~~java
try (ResultSet resultSet = statement.executeQuery()) {
    while (resultSet.next()) {
        long id = resultSet.getLong("order_id");
        String status = resultSet.getString("order_status");
        System.out.println(id + " " + status);
    }
}
~~~

`next()`:

- Di chuyển tới hàng tiếp theo và trả `true` nếu có hàng.
- Trả `false` khi đã hết tập kết quả.
- Lần gọi đầu tiên đưa cursor tới hàng đầu tiên nếu tập có dữ liệu.

Quên gọi `next()` trước khi gọi getter thường dẫn đến `SQLException` vì cursor chưa đứng trên một hàng hợp lệ.

### 6.2. Đọc cột bằng tên hoặc chỉ số

~~~java
long orderId = resultSet.getLong("order_id");
String status = resultSet.getString("order_status");
~~~

Hoặc:

~~~java
long orderId = resultSet.getLong(1);
String status = resultSet.getString(2);
~~~

Chỉ số cột JDBC bắt đầu từ **1**. Đọc theo label thường dễ bảo trì hơn khi SELECT thay đổi thứ tự cột.

Label có thể chịu ảnh hưởng của alias và quy tắc không phân biệt chữ hoa/thường của driver. Dùng alias rõ ràng:

~~~sql
SELECT
    o.order_id AS order_id,
    o.order_status AS order_status
FROM orders AS o
~~~

### 6.3. Chọn getter theo kiểu Java phù hợp

| SQL/DB type thường gặp | Getter JDBC gợi ý |
| --- | --- |
| SMALLINT/INTEGER | `getShort` / `getInt` |
| BIGINT | `getLong` |
| DECIMAL/NUMERIC | `getBigDecimal` |
| REAL/FLOAT | `getFloat` / `getDouble` |
| VARCHAR/TEXT | `getString` |
| BOOLEAN | `getBoolean` |
| DATE | `getDate` hoặc `getObject(..., LocalDate.class)` |
| TIME | `getTime` hoặc kiểu Java thời gian phù hợp |
| TIMESTAMP | `getTimestamp` hoặc kiểu Java thời gian phù hợp |
| BINARY/BLOB | `getBytes` / `getBlob` |
| CLOB/TEXT lớn | `getCharacterStream` / `getClob` |

Đối với tiền, thường dùng `BigDecimal` thay vì `double` để giữ phép tính thập phân theo precision/scale của cột.

### 6.4. Primitive getter và SQL NULL

Một chi tiết rất quan trọng:

~~~java
int quantity = resultSet.getInt("quantity");
~~~

Nếu SQL column là NULL, `getInt` trả 0. Muốn biết 0 là giá trị thật hay do SQL NULL, gọi `wasNull()` **ngay sau getter**:

~~~java
int quantity = resultSet.getInt("quantity");
boolean quantityWasNull = resultSet.wasNull();

if (quantityWasNull) {
    // SQL NULL
} else {
    // Giá trị quantity, có thể là 0 thật.
}
~~~

Tương tự với `getLong` và `getBoolean`. Nếu cần giữ null rõ ràng, dùng wrapper hoặc đọc `wasNull`:

~~~java
Integer quantity = null;
int raw = resultSet.getInt("quantity");

if (!resultSet.wasNull()) {
    quantity = raw;
}
~~~

Với `getString`, SQL NULL thường trả Java `null`, không phải chuỗi "null".

### 6.5. Đọc BigDecimal

~~~java
java.math.BigDecimal amount =
    resultSet.getBigDecimal("total_amount");
~~~

Không chuyển tiền sang double chỉ để tiện tính toán:

~~~java
// Không nên cho phép sai số nhị phân trong nghiệp vụ tiền.
double amount = resultSet.getDouble("total_amount");
~~~

Khi cần so sánh BigDecimal theo giá trị số, dùng `compareTo`:

~~~java
if (amount.compareTo(java.math.BigDecimal.ZERO) > 0) {
    // amount > 0
}
~~~

`equals` còn xét scale, nên `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` là false dù hai số có cùng giá trị toán học.

### 6.6. Đọc ngày giờ

Ví dụ JDBC hiện đại:

~~~java
java.time.LocalDate orderDate =
    resultSet.getObject("order_date", java.time.LocalDate.class);
~~~

~~~java
java.time.LocalDateTime localTimestamp =
    resultSet.getObject(
        "created_at",
        java.time.LocalDateTime.class
    );
~~~

Với cột có timezone/offset, chọn kiểu Java biểu diễn đúng ngữ nghĩa (ví dụ `OffsetDateTime`) nếu driver hỗ trợ. Không tự đổi mọi `TIMESTAMP` thành `LocalDateTime` rồi giả định đó là một thời điểm toàn cầu duy nhất.

### 6.7. ResultSetMetaData

Khi chưa biết trước schema của kết quả, có thể đọc metadata:

~~~java
try (ResultSet resultSet = statement.executeQuery(sql)) {
    java.sql.ResultSetMetaData metadata =
        resultSet.getMetaData();

    int columnCount = metadata.getColumnCount();

    for (int i = 1; i <= columnCount; i++) {
        System.out.printf(
            "%d: label=%s, type=%s%n",
            i,
            metadata.getColumnLabel(i),
            metadata.getColumnTypeName(i)
        );
    }
}
~~~

`getColumnLabel` thường phản ánh alias trong SELECT, còn `getColumnName` có thể phản ánh tên cột gốc theo driver. Metadata hữu ích cho công cụ tổng quát, export và debug; với repository nghiệp vụ, nên mapping các cột rõ ràng thay vì phụ thuộc vào metadata động.

## 7. ResultSet có thể duyệt lùi hoặc cập nhật không?

### 7.1. Mặc định thường là forward-only, read-only

Một `ResultSet` thông thường được tạo với loại:

- `TYPE_FORWARD_ONLY`: chỉ tiến tới.
- `CONCUR_READ_ONLY`: không cập nhật hàng qua ResultSet.

Mẫu `while (resultSet.next())` là cách dùng phổ biến và ít giả định nhất.

### 7.2. Scrollable ResultSet

JDBC cho phép yêu cầu loại scrollable:

~~~java
try (Statement statement = connection.createStatement(
         ResultSet.TYPE_SCROLL_INSENSITIVE,
         ResultSet.CONCUR_READ_ONLY);
     ResultSet resultSet = statement.executeQuery(
         "SELECT order_id FROM orders ORDER BY order_id")) {

    if (resultSet.last()) {
        int rowCount = resultSet.getRow();
        System.out.println("Rows: " + rowCount);
    }

    resultSet.beforeFirst();

    while (resultSet.next()) {
        System.out.println(resultSet.getLong("order_id"));
    }
}
~~~

Các phương thức có thể gồm `first()`, `last()`, `previous()`, `absolute()` và `beforeFirst()`, tùy loại ResultSet và driver.

Không phải driver/database đều hỗ trợ mọi kiểu scrollable. Kiểm tra `DatabaseMetaData.supportsResultSetType(...)` hoặc xử lý `SQLFeatureNotSupportedException` khi cần portability.

### 7.3. INSENSITIVE và SENSITIVE

- `TYPE_SCROLL_INSENSITIVE`: cursor scrollable, thường không phản ánh thay đổi dữ liệu từ transaction khác sau khi ResultSet được tạo.
- `TYPE_SCROLL_SENSITIVE`: có thể phản ánh thay đổi theo khả năng driver/DBMS, nhưng không được mọi hệ hỗ trợ đầy đủ.

Tên loại không thay thế transaction isolation. Đừng dựa vào ResultSet sensitive để đồng bộ dữ liệu nhiều người dùng.

### 7.4. Updatable ResultSet

JDBC có `CONCUR_UPDATABLE` và các phương thức như `updateString`, `updateRow`, nhưng hỗ trợ phụ thuộc driver và cấu trúc SELECT. Một truy vấn JOIN/aggregate phức tạp thường không cập nhật được theo cách đơn giản.

Trong ứng dụng nghiệp vụ, UPDATE rõ bằng `PreparedStatement` thường dễ kiểm soát hơn:

~~~java
String sql =
    "UPDATE orders SET order_status = ? WHERE order_id = ?";

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setString(1, "PAID");
    statement.setLong(2, 1001L);
    int affected = statement.executeUpdate();
}
~~~

## 8. Quản lý tài nguyên với try-with-resources

### 8.1. Vì sao phải đóng đủ ba lớp?

Một truy vấn thường mở:

1. Connection;
2. Statement/PreparedStatement;
3. ResultSet.

Mỗi tài nguyên có thể giữ buffer, cursor, handle server, socket hoặc slot pool. Không đóng đúng cách có thể gây:

- Cạn connection pool;
- ResultSet/cursor còn mở;
- Server giữ statement/resource;
- Bộ nhớ tăng;
- Các request sau phải chờ connection.

### 8.2. Mẫu chuẩn

~~~java
String sql = """
    SELECT order_id, order_status
    FROM orders
    WHERE customer_id = ?
    ORDER BY order_id
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql)) {

    statement.setLong(1, 1L);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong("order_id");
            String status = resultSet.getString("order_status");

            System.out.printf("%d %s%n", id, status);
        }
    }
}
~~~

Khi thoát khỏi khối:

- ResultSet đóng trước;
- PreparedStatement đóng sau;
- Connection đóng cuối.

Java đóng tài nguyên theo thứ tự ngược với thứ tự khai báo. Nếu một thao tác trong body ném exception, Java vẫn cố đóng các tài nguyên và có thể gắn lỗi đóng thành *suppressed exception*.

### 8.3. Không chỉ đóng ResultSet

Sai:

~~~java
Connection connection = dataSource.getConnection();
PreparedStatement statement = connection.prepareStatement(sql);
ResultSet resultSet = statement.executeQuery();

// Đọc xong nhưng không đóng bất kỳ tài nguyên nào.
~~~

Cách an toàn là try-with-resources. Nếu phải hỗ trợ Java cũ không có try-with-resources, cần dùng `finally` và đóng theo thứ tự ResultSet → Statement → Connection, đồng thời không làm mất exception gốc.

### 8.4. Đóng Statement sẽ đóng ResultSet hiện tại

Khi Statement đóng, ResultSet liên quan của nó cũng đóng. Nhiều thao tác thực thi tiếp theo trên cùng Statement cũng có thể đóng ResultSet hiện tại theo quy tắc JDBC/driver.

Không giữ ResultSet để đọc sau khi đã đóng Statement hoặc Connection. Đọc/map dữ liệu trong phạm vi resource còn mở.

### 8.5. Không trả ResultSet ra khỏi repository

Anti-pattern:

~~~java
public ResultSet findOrders(long customerId) throws SQLException {
    Connection connection = dataSource.getConnection();
    PreparedStatement statement =
        connection.prepareStatement(
            "SELECT * FROM orders WHERE customer_id = ?"
        );

    statement.setLong(1, customerId);
    return statement.executeQuery();
}
~~~

Phương thức trả ResultSet nhưng không có nơi rõ ràng đóng Statement/Connection. Caller có thể quên đóng, và ResultSet phụ thuộc vào hai tài nguyên đó.

Nên trả object Java:

~~~java
public List<Order> findOrders(long customerId) throws SQLException {
    List<Order> orders = new ArrayList<>();

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT order_id, order_status " +
                 "FROM orders WHERE customer_id = ?"
             )) {

        statement.setLong(1, customerId);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                orders.add(new Order(
                    resultSet.getLong("order_id"),
                    resultSet.getString("order_status")
                ));
            }
        }
    }

    return orders;
}
~~~

Kết quả là dữ liệu Java đã được materialize độc lập với cursor. Với tập rất lớn, có thể dùng stream/callback có lifecycle rõ hoặc pagination thay vì tải tất cả vào List.

## 9. Mapping ResultSet sang DTO/Entity

### 9.1. Một DTO đơn giản

~~~java
public final class Order {
    private final long orderId;
    private final String status;

    public Order(long orderId, String status) {
        this.orderId = orderId;
        this.status = status;
    }

    public long getOrderId() {
        return orderId;
    }

    public String getStatus() {
        return status;
    }
}
~~~

Mapping:

~~~java
private Order mapOrder(ResultSet resultSet) throws SQLException {
    return new Order(
        resultSet.getLong("order_id"),
        resultSet.getString("order_status")
    );
}
~~~

Đưa mapping vào một phương thức riêng giúp query code dễ đọc và dễ kiểm thử hơn.

### 9.2. Repository hoàn chỉnh

~~~java
import javax.sql.DataSource;
import java.sql.*;
import java.util.ArrayList;
import java.util.List;

public final class JdbcOrderRepository {
    private final DataSource dataSource;

    public JdbcOrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<Order> findByCustomer(long customerId)
            throws SQLException {
        String sql = """
            SELECT order_id, order_status
            FROM orders
            WHERE customer_id = ?
            ORDER BY order_id
            """;

        List<Order> result = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    result.add(new Order(
                        rs.getLong("order_id"),
                        rs.getString("order_status")
                    ));
                }
            }
        }

        return result;
    }
}
~~~

Phương thức này:

- Mượn một connection;
- Bind tham số;
- Đọc tất cả hàng;
- Map thành DTO;
- Đóng mọi tài nguyên;
- Trả List Java độc lập với database cursor.

### 9.3. Một hàng hoặc không có hàng

Dùng `Optional` khi truy vấn có thể không tìm thấy:

~~~java
public Optional<Order> findOne(long orderId) throws SQLException {
    String sql =
        "SELECT order_id, order_status FROM orders WHERE order_id = ?";

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setLong(1, orderId);

        try (ResultSet rs = statement.executeQuery()) {
            if (!rs.next()) {
                return Optional.empty();
            }

            Order order = new Order(
                rs.getLong("order_id"),
                rs.getString("order_status")
            );

            return Optional.of(order);
        }
    }
}
~~~

Nếu truy vấn theo khóa chính, tối đa một hàng. Nếu query không bảo đảm duy nhất, nên xác định rõ xử lý nhiều hàng thay vì lấy tùy tiện hàng đầu.

### 9.4. Đọc nhiều cột nullable

~~~java
int rawQuantity = rs.getInt("quantity");
Integer quantity = rs.wasNull() ? null : rawQuantity;

BigDecimal amount = rs.getBigDecimal("amount");
String note = rs.getString("note");
~~~

Đọc `wasNull()` ngay sau getter tương ứng; nếu gọi getter cột khác trước, trạng thái `wasNull` có thể phản ánh getter mới nhất thay vì cột cần kiểm tra.

## 10. Transaction và Connection

### 10.1. Auto-commit

Mặc định JDBC thường bắt đầu với `autoCommit=true`. Mỗi statement được commit tự động khi hoàn tất theo quy tắc driver/database.

~~~java
try (Connection connection = dataSource.getConnection()) {
    System.out.println(connection.getAutoCommit());
}
~~~

Với thao tác độc lập đơn giản, auto-commit có thể phù hợp. Nhưng khi nhiều câu SQL phải **thành công hoặc thất bại cùng nhau**, cần transaction tường minh:

~~~java
connection.setAutoCommit(false);
try {
    // Nhiều câu SQL thuộc một transaction.
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
~~~

### 10.2. Ví dụ chuyển tiền cần transaction

Giả sử bảng:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(18, 2) NOT NULL CHECK (balance >= 0)
);
~~~

Chuyển tiền gồm hai UPDATE:

1. Trừ tiền tài khoản nguồn.
2. Cộng tiền tài khoản đích.

Nếu câu thứ hai lỗi mà câu đầu đã commit riêng, tiền có thể biến mất khỏi tài khoản nguồn. Cần transaction.

~~~java
public void transfer(
        DataSource dataSource,
        long fromAccount,
        long toAccount,
        BigDecimal amount) throws SQLException {

    if (amount == null || amount.signum() <= 0) {
        throw new IllegalArgumentException(
            "amount must be positive"
        );
    }

    if (fromAccount == toAccount) {
        throw new IllegalArgumentException(
            "source and destination must differ"
        );
    }

    String debitSql = """
        UPDATE accounts
        SET balance = balance - ?
        WHERE account_id = ?
          AND balance >= ?
        """;

    String creditSql = """
        UPDATE accounts
        SET balance = balance + ?
        WHERE account_id = ?
        """;

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            int debited;

            try (PreparedStatement debit =
                     connection.prepareStatement(debitSql)) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromAccount);
                debit.setBigDecimal(3, amount);
                debited = debit.executeUpdate();
            }

            if (debited != 1) {
                throw new SQLException(
                    "Source account missing or insufficient balance"
                );
            }

            int credited;

            try (PreparedStatement credit =
                     connection.prepareStatement(creditSql)) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toAccount);
                credited = credit.executeUpdate();
            }

            if (credited != 1) {
                throw new SQLException("Destination account not found");
            }

            connection.commit();

        } catch (SQLException | RuntimeException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }
            throw e;
        }
    }
}
~~~

Câu UPDATE nguồn có guard `balance >= amount` tại thời điểm ghi. Điều đó giúp tránh trừ tiền khi số dư không đủ; constraint `CHECK` cũng là lớp bảo vệ bổ sung.

Transaction bảo đảm hai thay đổi cùng commit hoặc cùng rollback theo cơ chế database. Trong hệ thống thật, còn phải xét khóa hàng, isolation, deadlock, thứ tự khóa và idempotency của yêu cầu chuyển tiền.

### 10.3. Đừng commit trong từng vòng lặp nếu nghiệp vụ cần all-or-nothing

Nếu một batch gồm 100 đơn phải thành công cùng nhau, commit sau từng đơn có thể khiến 60 đơn đầu đã ghi còn 40 đơn sau thất bại. Đó có thể là thiết kế đúng nếu nghiệp vụ chấp nhận xử lý từng phần, nhưng không còn là một transaction all-or-nothing.

Hãy quyết định ranh giới transaction theo **đơn vị nghiệp vụ**, không theo tiện lợi của vòng lặp Java.

### 10.4. Savepoint

Khi cần rollback một phần trong transaction:

~~~java
connection.setAutoCommit(false);

Savepoint savepoint = connection.setSavepoint("before_optional_step");

try {
    // Thực hiện bước có thể thất bại.
    connection.releaseSavepoint(savepoint);
} catch (SQLException e) {
    connection.rollback(savepoint);
    // Tiếp tục theo chính sách của ứng dụng.
}
~~~

Savepoint không commit transaction. Sau rollback về savepoint, transaction vẫn mở và cần commit/rollback cuối cùng. Hỗ trợ và hành vi chi tiết có thể khác theo driver/database.

### 10.5. Isolation level

JDBC định nghĩa các mức phổ biến:

- `TRANSACTION_READ_UNCOMMITTED`;
- `TRANSACTION_READ_COMMITTED`;
- `TRANSACTION_REPEATABLE_READ`;
- `TRANSACTION_SERIALIZABLE`.

Đặt mức:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
~~~

Mức có sẵn và semantics thực tế phụ thuộc DBMS. Database có thể ánh xạ hoặc không hỗ trợ một mức theo cùng cách.

Không tự chọn `SERIALIZABLE` cho mọi truy vấn với suy nghĩ “càng cao càng tốt”: mức cô lập cao có thể tăng khóa, xung đột và yêu cầu retry. Chọn theo anomaly nghiệp vụ cần ngăn và cách xử lý khi transaction bị từ chối.

### 10.6. Read-only hint

~~~java
connection.setReadOnly(true);
~~~

Đây là gợi ý cho driver/DBMS, có thể giúp chọn đường thực thi phù hợp hoặc ngăn ghi tùy engine. Không coi nó thay thế quyền SQL `GRANT/REVOKE` hay bảo đảm bảo mật tuyệt đối.

### 10.7. Khôi phục trạng thái khi dùng pool

Khi dùng connection pool, các thay đổi trạng thái connection như auto-commit, isolation, read-only và schema có thể ảnh hưởng lần mượn sau nếu pool/driver không reset đúng hoặc code quản lý sai.

Nguyên tắc:

- Không thay trạng thái nếu không cần;
- Nếu thay, khôi phục sau transaction hoặc dùng abstraction transaction quản lý;
- Đóng connection trong mọi đường code;
- Không giữ transaction mở qua thao tác HTTP, chờ người dùng hoặc xử lý lâu ngoài DB.

Trong ví dụ chuyển tiền, connection được đóng ngay sau commit/rollback; pool có thể reset proxy trước khi cấp cho request tiếp theo.

## 11. Batch processing

### 11.1. Vì sao dùng batch?

Nếu cần insert nhiều hàng, gọi execute riêng từng hàng tạo nhiều lượt trao đổi client-server. `addBatch()` và `executeBatch()` cho phép gom các thao tác cùng PreparedStatement:

~~~java
String sql = """
    INSERT INTO order_items (
        order_id, line_no, product_id, quantity, unit_price
    )
    VALUES (?, ?, ?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    connection.setAutoCommit(false);

    try {
        for (OrderItem item : items) {
            statement.setLong(1, item.getOrderId());
            statement.setInt(2, item.getLineNo());
            statement.setLong(3, item.getProductId());
            statement.setInt(4, item.getQuantity());
            statement.setBigDecimal(5, item.getUnitPrice());

            statement.addBatch();
        }

        int[] updateCounts = statement.executeBatch();
        connection.commit();

    } catch (SQLException | RuntimeException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
~~~

Batch có thể giảm round trips và tận dụng tối ưu driver, nhưng không bảo đảm mọi driver gửi đúng một gói hay mọi database thực thi như một câu lệnh duy nhất.

### 11.2. Update counts

Mảng trả về từ `executeBatch()` có thể chứa:

- Số hàng bị tác động;
- `Statement.SUCCESS_NO_INFO`: thành công nhưng driver không biết chính xác số hàng;
- `Statement.EXECUTE_FAILED`: lệnh batch thất bại trong một số chế độ tiếp tục thực thi.

Một số lỗi tạo `BatchUpdateException`, chứa các update counts đã thực thi hoặc được báo trước lỗi. Chi tiết phụ thuộc driver và cách DBMS xử lý batch.

Không giả định mỗi phần tử luôn bằng 1. Nếu nghiệp vụ cần đảm bảo từng bản ghi được tạo đúng, cần kiểm tra count/khóa/constraint theo khả năng driver.

### 11.3. Chia batch lớn thành chunk

Một danh sách hàng triệu phần tử không nên luôn đưa vào một batch duy nhất. Có thể chia thành từng nhóm:

~~~java
int batchSize = 500;
int pending = 0;

for (OrderItem item : items) {
    bindItem(statement, item);
    statement.addBatch();
    pending++;

    if (pending == batchSize) {
        statement.executeBatch();
        statement.clearBatch();
        pending = 0;
    }
}

if (pending > 0) {
    statement.executeBatch();
}
~~~

`bindItem` là phương thức ứng dụng tự định nghĩa. Nếu các chunk cùng thuộc một transaction, bộ nhớ và thời gian transaction vẫn tăng theo tổng công việc; có thể cần commit theo chunk nếu nghiệp vụ chấp nhận tính từng phần.

### 11.4. Batch không thay validation

Trước khi thêm batch, kiểm tra dữ liệu đầu vào hoặc để constraint database bảo vệ:

- NOT NULL;
- CHECK;
- FOREIGN KEY;
- UNIQUE;
- giới hạn precision/scale;
- quy tắc trạng thái nghiệp vụ.

Nếu một hàng sai, batch có thể thất bại tùy driver/database. Cần xác định chính sách: rollback toàn batch, ghi nhận hàng lỗi và tiếp tục, hoặc chia lô có kiểm soát.

## 12. Generated keys và RETURNING

### 12.1. Lấy khóa tự sinh bằng JDBC

Nếu bảng có identity/auto-increment, dùng:

~~~java
String sql = """
    INSERT INTO orders (customer_id, ordered_at, order_status)
    VALUES (?, CURRENT_TIMESTAMP, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(
             sql,
             Statement.RETURN_GENERATED_KEYS
         )) {

    statement.setLong(1, 1L);
    statement.setString(2, "NEW");

    int affected = statement.executeUpdate();

    if (affected != 1) {
        throw new SQLException("Expected one inserted order");
    }

    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (keys.next()) {
            long generatedOrderId = keys.getLong(1);
            System.out.println(generatedOrderId);
        } else {
            throw new SQLException("No generated key returned");
        }
    }
}
~~~

`getGeneratedKeys()` trả ResultSet các khóa được driver cung cấp theo khả năng. Không phải mọi driver/database đều trả cùng số lượng hoặc cùng loại khóa cho mọi kiểu INSERT/batch. Kiểm tra tài liệu driver và thử trên database thật.

### 12.2. PostgreSQL RETURNING

PostgreSQL hỗ trợ:

~~~sql
INSERT INTO orders (
    customer_id, ordered_at, order_status
)
VALUES (?, CURRENT_TIMESTAMP, ?)
RETURNING order_id, ordered_at;
~~~

JDBC có thể dùng `executeQuery()` cho câu có `RETURNING` theo driver PostgreSQL:

~~~java
String sql = """
    INSERT INTO orders (customer_id, ordered_at, order_status)
    VALUES (?, CURRENT_TIMESTAMP, ?)
    RETURNING order_id, ordered_at
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, 1L);
    statement.setString(2, "NEW");

    try (ResultSet rs = statement.executeQuery()) {
        if (rs.next()) {
            long id = rs.getLong("order_id");
        }
    }
}
~~~

`RETURNING` là tính năng SQL theo DBMS, không phải cú pháp SQL phổ quát. SQL Server có `OUTPUT INSERTED...`; MySQL/Oracle có cơ chế riêng tùy phiên bản/driver.

## 13. Xử lý tập kết quả lớn

### 13.1. Đừng tải mọi hàng vào List nếu không cần

Mẫu:

~~~java
List<Order> all = repository.findAll();
~~~

nếu bảng có hàng triệu đơn có thể giữ lượng lớn object trong heap. Cân nhắc:

- Lọc theo điều kiện;
- Phân trang;
- Keyset pagination;
- Đọc theo luồng với cursor/fetch size;
- Export theo batch;
- Aggregate ở database khi chỉ cần thống kê.

### 13.2. Fetch size

JDBC cho phép đặt gợi ý:

~~~java
statement.setFetchSize(500);
~~~

`fetchSize` là gợi ý số hàng driver nên lấy mỗi lần từ database, không phải giới hạn tổng số hàng. Hỗ trợ và hiệu quả phụ thuộc driver.

Một số driver tải toàn bộ kết quả ngay cả khi đã đặt fetch size. Một số driver yêu cầu cấu hình transaction/cursor cụ thể mới streaming.

### 13.3. PostgreSQL JDBC cursor-based fetching

Với PostgreSQL JDBC driver, để dùng cursor-based fetching thay vì mặc định tải toàn bộ kết quả, thường cần:

- `ResultSet` forward-only;
- `fetchSize` lớn hơn 0;
- `autoCommit=false` để cursor sống trong transaction;
- Đọc ResultSet trong khi transaction/connection còn mở.

Ví dụ:

~~~java
String sql = """
    SELECT order_id, order_status
    FROM orders
    ORDER BY order_id
    """;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement statement =
             connection.prepareStatement(
                 sql,
                 ResultSet.TYPE_FORWARD_ONLY,
                 ResultSet.CONCUR_READ_ONLY
             )) {

        statement.setFetchSize(500);

        try (ResultSet rs = statement.executeQuery()) {
            while (rs.next()) {
                long orderId = rs.getLong("order_id");
                String status = rs.getString("order_status");

                process(orderId, status);
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
~~~

`process` là logic ứng dụng minh họa. Nếu xử lý từng hàng lâu hoặc gọi API ngoài trong lúc cursor mở, transaction có thể kéo dài; cần cân nhắc đọc theo trang và đóng transaction sớm.

Đây là **hành vi đặc thù PostgreSQL JDBC driver**, không áp dụng nguyên xi cho MySQL/SQL Server/Oracle.

### 13.4. Keyset pagination

Thay vì offset rất lớn:

~~~sql
SELECT order_id, order_status
FROM orders
ORDER BY order_id
LIMIT 500 OFFSET 500000;
~~~

có thể dùng khóa trang cuối:

~~~sql
SELECT order_id, order_status
FROM orders
WHERE order_id > ?
ORDER BY order_id
LIMIT ?;
~~~

Java:

~~~java
long lastSeenId = 0L;
int pageSize = 500;

while (true) {
    List<Order> page =
        repository.findAfter(lastSeenId, pageSize);

    if (page.isEmpty()) {
        break;
    }

    for (Order order : page) {
        process(order);
        lastSeenId = order.getOrderId();
    }
}
~~~

Keyset pagination thường hiệu quả hơn khi đi sâu vào bảng lớn nếu có index phù hợp và thứ tự sort ổn định. Nếu sort theo nhiều cột, cần cursor chứa **toàn bộ khóa sắp xếp** và điều kiện so sánh tương ứng.

### 13.5. Không trả ResultSet qua tầng web

Không giữ ResultSet mở trong lúc client HTTP tải dữ liệu chậm. Hãy đọc/map thành DTO trong transaction/resource scope rồi đóng database resource, hoặc dùng một pipeline streaming được thiết kế rõ với timeout, cancellation và lifecycle.

Database connection là tài nguyên có giới hạn; một client mạng chậm không nên giữ slot pool vô thời hạn.

## 14. Statement timeout, fetch direction và các giới hạn

### 14.1. Query timeout

~~~java
statement.setQueryTimeout(10);
~~~

Tham số tính bằng giây theo JDBC. Driver có thể yêu cầu database hủy câu SQL khi vượt thời gian. Mức hỗ trợ và độ chính xác tùy driver/database.

Timeout phía JDBC không thay thế:

- Timeout lấy connection từ pool;
- Network/socket timeout;
- Transaction timeout của framework;
- Deadline tổng thể của HTTP request;
- Timeout khóa/statement ở DBMS.

Cần cấu hình nhất quán để request không bị giữ tài nguyên quá lâu.

### 14.2. Max rows

~~~java
statement.setMaxRows(1000);
~~~

Giới hạn số hàng tối đa mà ResultSet trả theo khả năng driver. Đây không thay thế `LIMIT`/`FETCH FIRST` trong SQL khi cần optimizer giới hạn công việc ở database.

### 14.3. Fetch direction

`setFetchDirection(ResultSet.FETCH_FORWARD)` là gợi ý cho driver; không nên xem nó là bảo đảm hiệu năng. Phần lớn truy vấn ứng dụng dùng forward-only.

### 14.4. Cancel statement

JDBC có `Statement.cancel()` để yêu cầu hủy câu đang thực thi theo hỗ trợ driver. Việc hủy có thể không tức thì và không bảo đảm mọi DBMS dừng ngay. Sau cancel hoặc timeout, cần xử lý trạng thái transaction và connection theo tài liệu driver.

### 14.5. Network timeout

Connection có `setNetworkTimeout(Executor, milliseconds)` ở JDBC hiện đại. Cấu hình này liên quan thời gian chờ thao tác mạng; không nhầm với statement timeout. Driver có thể có hỗ trợ riêng và cần Executor phù hợp.

## 15. SQLException và chiến lược xử lý lỗi

### 15.1. SQLException mang nhiều thông tin hơn message

Các thuộc tính quan trọng:

~~~java
try {
    // JDBC operation
} catch (SQLException e) {
    System.err.println(e.getMessage());
    System.err.println(e.getSQLState());
    System.err.println(e.getErrorCode());
    throw e;
}
~~~

- `getMessage()`: thông báo lỗi.
- `getSQLState()`: mã trạng thái SQL theo chuẩn/driver.
- `getErrorCode()`: mã lỗi vendor của DBMS.
- `getNextException()`: chuỗi lỗi JDBC tiếp theo.

Đừng chỉ parse message text để quyết định retry; message có thể thay đổi theo phiên bản, ngôn ngữ hoặc driver.

### 15.2. Duyệt chained exceptions

~~~java
catch (SQLException e) {
    for (SQLException current = e;
         current != null;
         current = current.getNextException()) {

        logger.error(
            "SQLState={}, vendorCode={}, message={}",
            current.getSQLState(),
            current.getErrorCode(),
            current.getMessage()
        );
    }

    throw e;
}
~~~

Logger ở đây minh họa API logging kiểu SLF4J. Không ghi password, token hoặc toàn bộ dữ liệu nhạy cảm của câu SQL vào log.

### 15.3. Phân loại lỗi

JDBC có các subtype hữu ích:

| Loại | Ý nghĩa khái quát |
| --- | --- |
| `SQLTransientException` | Lỗi có thể tạm thời, thử lại có thể thành công |
| `SQLNonTransientException` | Lỗi thường không hết nếu lặp lại cùng thao tác |
| `SQLRecoverableException` | Có thể cần khôi phục kết nối hoặc hành động phục hồi |
| `SQLTimeoutException` | Hết thời gian chờ |
| `SQLIntegrityConstraintViolationException` | Vi phạm ràng buộc toàn vẹn |
| `SQLSyntaxErrorException` | SQL sai cú pháp hoặc lỗi cú pháp tương tự |

Driver không phải lúc nào cũng ánh xạ mọi lỗi vào đúng subtype. Vẫn cần xem SQLState/vendor code và semantics của database.

### 15.4. Không retry tất cả SQLException

Retry có thể hợp lý với deadlock/serialization failure hoặc lỗi mạng tạm thời, nhưng:

- Syntax error sẽ không tự sửa khi retry;
- Vi phạm unique constraint có thể là xung đột nghiệp vụ;
- Một lệnh INSERT có thể đã commit ở server nhưng client mất kết nối trước khi nhận phản hồi;
- Retry một thao tác không idempotent có thể tạo dữ liệu trùng hoặc trừ tiền hai lần.

Với transaction bị deadlock/serialization failure, thường phải **retry toàn transaction** theo chính sách, không chỉ retry câu SQL cuối. Cần giới hạn số lần, backoff, deadline và idempotency key phù hợp.

### 15.5. Lỗi đóng tài nguyên và suppressed exception

Try-with-resources tự đóng tài nguyên khi có exception. Nếu body đã ném exception và close cũng lỗi, lỗi close thường được gắn vào `getSuppressed()` chứ không ghi đè lỗi chính.

Khi debug:

~~~java
for (Throwable suppressed : e.getSuppressed()) {
    logger.warn("Resource close failed", suppressed);
}
~~~

Không nuốt exception gốc bằng một khối finally chỉ in message rồi tiếp tục như thể transaction thành công.

## 16. Quản lý connection pool và vận hành

### 16.1. Các khái niệm pool

| Cấu hình | Ý nghĩa |
| --- | --- |
| Maximum pool size | Số connection vật lý tối đa pool giữ |
| Minimum idle | Số connection nhàn rỗi mục tiêu/tối thiểu tùy pool |
| Connection timeout | Thời gian chờ mượn connection |
| Idle timeout | Thời gian connection nhàn rỗi trước khi pool có thể thu hồi |
| Max lifetime | Tuổi tối đa connection trước khi pool thay thế |
| Validation timeout | Giới hạn kiểm tra connection |
| Leak detection | Cảnh báo connection bị mượn quá lâu theo ngưỡng cấu hình |

Tên và semantics cụ thể tùy thư viện pool.

### 16.2. Pool exhaustion

Một pool có 10 connection. Nếu 10 request đều mượn connection và không đóng, request thứ 11 phải chờ hoặc timeout. Nguyên nhân thường gặp:

- Quên try-with-resources;
- Giữ ResultSet khi trả HTTP response;
- Transaction mở trong lúc gọi API ngoài;
- Query chạy quá lâu;
- Một code path exception không đóng resource;
- Mượn connection lồng nhau trong cùng request mà không đủ pool.

### 16.3. Không tăng pool size để che query chậm

Nếu query chậm, tăng pool có thể làm nhiều query cùng chạy và tăng contention, khiến database còn chậm hơn. Cần xem:

- Query plan và index;
- Số connection active/idle;
- Wait time lấy connection;
- Thời gian thực thi query;
- Lock waits và deadlocks;
- CPU, I/O, memory trên DB;
- Transaction duration.

Pool là bộ giới hạn concurrency và tái sử dụng kết nối, không phải bộ tăng tốc câu SQL.

### 16.4. Không mở connection quá sớm

Trong service:

~~~java
public OrderSummary buildSummary(long customerId) throws SQLException {
    // Tính toán không cần database trước khi mượn connection.
    validateCustomerId(customerId);

    try (Connection connection = dataSource.getConnection()) {
        return querySummary(connection, customerId);
    }
}
~~~

Nếu phải gọi dịch vụ bên ngoài, tránh giữ connection/transaction suốt thời gian chờ mạng nếu có thể tách quy trình.

### 16.5. Một DataSource dùng chung, connection riêng cho công việc

Thông thường DataSource/pool là đối tượng dùng chung và thread-safe theo tài liệu thư viện. Connection, Statement và ResultSet được tạo cho một đơn vị công việc, rồi đóng. Không nhầm DataSource thread-safe với việc mọi đối tượng nó cấp ra đều được chia sẻ tùy tiện.

## 17. Mẫu kiến trúc: Service, Repository và transaction boundary

### 17.1. Repository quản lý query đơn giản

Repository nhận DataSource và đóng connection khi kết thúc thao tác:

~~~java
public List<Order> findByStatus(String status) throws SQLException {
    String sql = """
        SELECT order_id, order_status
        FROM orders
        WHERE order_status = ?
        ORDER BY order_id
        """;

    List<Order> orders = new ArrayList<>();

    try (Connection connection = dataSource.getConnection();
         PreparedStatement statement =
             connection.prepareStatement(sql)) {

        statement.setString(1, status);

        try (ResultSet rs = statement.executeQuery()) {
            while (rs.next()) {
                orders.add(mapOrder(rs));
            }
        }
    }

    return orders;
}
~~~

### 17.2. Nhiều repository cùng transaction phải dùng chung Connection

Nếu service cần cập nhật order và payment trong **một transaction**, không để mỗi repository tự lấy connection độc lập. Nếu mỗi repository mở connection riêng, hai thao tác có thể thuộc hai transaction khác nhau.

Một cách đơn giản là service mở connection rồi truyền cho repository:

~~~java
public void completeOrder(long orderId) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            orderRepository.markPaid(connection, orderId);
            paymentRepository.recordCapture(connection, orderId);
            connection.commit();
        } catch (SQLException | RuntimeException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }
            throw e;
        }
    }
}
~~~

Các phương thức repository nhận `Connection` không đóng connection do caller sở hữu:

~~~java
public void markPaid(Connection connection, long orderId)
        throws SQLException {
    String sql = """
        UPDATE orders
        SET order_status = 'PAID'
        WHERE order_id = ?
          AND order_status = 'PENDING'
        """;

    try (PreparedStatement statement =
             connection.prepareStatement(sql)) {
        statement.setLong(1, orderId);

        int affected = statement.executeUpdate();
        if (affected != 1) {
            throw new SQLException("Order not pending or not found");
        }
    }
}
~~~

Quy ước ownership rất quan trọng:

- Phương thức nào **mượn** connection thì phương thức đó đóng.
- Phương thức nào **nhận** connection từ caller thì không tự đóng.
- Service hoặc transaction manager chịu trách nhiệm commit/rollback.
- Statement/ResultSet do repository tạo thì repository đóng.

Framework như Spring có transaction manager và DataSource integration riêng. Khi dùng framework, không tự trộn quản lý transaction thủ công với transaction proxy nếu chưa hiểu cơ chế connection binding.

### 17.3. Đừng để transaction phụ thuộc vào thời gian xử lý HTTP

Sai thiết kế thường gặp:

~~~text
BEGIN TRANSACTION
  UPDATE database
  Gọi API thanh toán qua mạng (mất 8 giây)
  Chờ người dùng xác nhận
  UPDATE database
COMMIT
~~~

Transaction giữ connection/lock trong lúc chờ bên ngoài. Hệ thống dễ nghẽn và có rủi ro side effect bên ngoài không rollback cùng database.

Thiết kế thường tốt hơn là dùng state machine, outbox, saga hoặc quy trình bất đồng bộ với transaction ngắn ở từng bước.

## 18. Kiểm tra tính năng driver bằng DatabaseMetaData

JDBC hỗ trợ truy vấn khả năng driver/database:

~~~java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println(metadata.getDatabaseProductName());
    System.out.println(metadata.getDatabaseProductVersion());
    System.out.println(metadata.getDriverName());
    System.out.println(metadata.getDriverVersion());

    boolean supportsBatch =
        metadata.supportsBatchUpdates();

    boolean supportsTransactions =
        metadata.supportsTransactions();

    System.out.println("Batch: " + supportsBatch);
    System.out.println("Transactions: " + supportsTransactions);
}
~~~

Một số kiểm tra khác:

- `supportsResultSetType`;
- `supportsResultSetConcurrency`;
- `supportsSavepoints`;
- `supportsTransactionIsolationLevel`;
- Khi cần generated keys, xem khả năng API/driver cụ thể và thử thực tế; không suy ra mọi driver hỗ trợ mọi dạng INSERT/batch.

Không dùng metadata để thay thế kiểm thử integration. Metadata cho biết khả năng được driver công bố, nhưng hành vi cụ thể vẫn phải được kiểm tra trong môi trường triển khai.

## 19. Các anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách đúng |
| --- | --- | --- |
| Nối input vào SQL | SQL injection | PreparedStatement và bind giá trị |
| Dùng một Connection static cho mọi request | Transaction lẫn nhau, concurrency lỗi | Mượn connection riêng từ DataSource/pool |
| Quên đóng ResultSet/Statement/Connection | Leak cursor và pool | try-with-resources |
| Trả ResultSet ra khỏi repository | Caller khó quản lý lifecycle | Map DTO/List hoặc stream có ownership rõ |
| Gọi getInt rồi quên wasNull | Nhầm SQL NULL với 0 | Gọi wasNull ngay sau getter |
| Dùng double cho tiền | Sai số thập phân | BigDecimal |
| Gọi executeQuery cho UPDATE | Sai kiểu thực thi | executeUpdate |
| Dùng executeUpdate cho SELECT | Không đọc ResultSet | executeQuery |
| Dùng Statement với giá trị người dùng | Injection/escaping lỗi | PreparedStatement |
| Bind tên cột bằng ? | Placeholder trở thành giá trị | Whitelist identifier |
| Mở transaction rồi gọi HTTP | Giữ lock/connection lâu | Tách transaction và side effect |
| Commit từng hàng ngoài ý muốn | Mất tính all-or-nothing | Định nghĩa transaction boundary |
| Retry mọi SQLException | Lặp lỗi vĩnh viễn hoặc tạo duplicate | Phân loại lỗi, idempotency, retry có giới hạn |
| Tăng pool để chữa query chậm | DB bị quá tải hơn | Phân tích query và concurrency |
| Dùng fetchSize tưởng là LIMIT | Vẫn có thể đọc toàn bộ hàng | SQL filter/pagination |
| Tải triệu hàng vào ArrayList | Heap tăng cao | Streaming/cursor/keyset pagination |
| Mượn connection lồng nhau không kiểm soát | Pool exhaustion | Truyền connection trong transaction |
| Tự đóng connection do caller cấp | Transaction caller bị hỏng | Quy ước ownership |
| Không rollback sau exception | Connection trả pool với transaction lỗi | Rollback trước khi đóng |
| Chỉ log e.getMessage() | Mất SQLState/vendor code | Log thông tin chẩn đoán an toàn |
| Ghi password/SQL nhạy cảm vào log | Rò bí mật | Redact dữ liệu nhạy cảm |

## 20. Bài tập thực hành có đáp án

### Bài 1 — Kết nối bằng DataSource

Viết đoạn Java lấy một connection và đóng nó tự động.

**Đáp án:**

~~~java
try (Connection connection = dataSource.getConnection()) {
    System.out.println(connection.getMetaData().getURL());
}
~~~

Try-with-resources gọi close khi thoát block.

### Bài 2 — PreparedStatement

Tìm đơn theo `order_id` bằng tham số.

**Đáp án:**

~~~java
String sql =
    "SELECT order_id, order_status FROM orders WHERE order_id = ?";

try (Connection c = dataSource.getConnection();
     PreparedStatement ps = c.prepareStatement(sql)) {
    ps.setLong(1, orderId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String status = rs.getString("order_status");
        }
    }
}
~~~

### Bài 3 — Chỉ số placeholder bắt đầu từ đâu?

Với `WHERE customer_id = ? AND order_status = ?`, chỉ số tham số là gì?

**Đáp án:** tham số đầu tiên là 1, tham số thứ hai là 2. JDBC không đánh số placeholder từ 0.

### Bài 4 — Chọn phương thức thực thi

Một SELECT trả nhiều hàng nên dùng phương thức nào?

**Đáp án:** `executeQuery()`, sau đó duyệt ResultSet bằng `next()`.

### Bài 5 — UPDATE và số hàng

Câu UPDATE cần biết có bao nhiêu hàng bị tác động. Dùng phương thức nào?

**Đáp án:** `executeUpdate()` trả update count dạng int cho câu lệnh phù hợp.

### Bài 6 — SQL injection

Vì sao `"WHERE email = '" + email + "'"` nguy hiểm? Cách sửa?

**Đáp án:** input có thể thay đổi cấu trúc SQL. Dùng `WHERE email = ?` và `setString(1, email)`.

### Bài 7 — Bind tên cột

Có thể dùng `ORDER BY ?` rồi bind "created_at" để chọn cột sort không?

**Đáp án:** không. Placeholder là giá trị. Chọn identifier từ whitelist rồi ghép vào SQL; các giá trị lọc vẫn bind.

### Bài 8 — ResultSet cursor

Sau `executeQuery()`, có thể gọi `getLong(1)` ngay không?

**Đáp án:** không. Cursor ban đầu ở before-first; gọi `next()` và chỉ đọc getter khi nó trả true.

### Bài 9 — JDBC column index

Cột đầu tiên trong ResultSet có index bao nhiêu?

**Đáp án:** 1. JDBC dùng chỉ số cột bắt đầu từ 1.

### Bài 10 — NULL và getInt

Cột SQL NULL được đọc bằng `getInt("quantity")` trả về gì? Làm sao phân biệt?

**Đáp án:** trả 0; gọi `wasNull()` ngay sau getter. Nếu true thì giá trị SQL là NULL.

### Bài 11 — BigDecimal

Vì sao cột tiền nên đọc bằng `getBigDecimal`?

**Đáp án:** BigDecimal biểu diễn số thập phân theo precision/scale phù hợp hơn floating-point nhị phân như double cho phép tính tiền.

### Bài 12 — Đóng tài nguyên

Khai báo theo thứ tự Connection, PreparedStatement, ResultSet trong try-with-resources. Java đóng theo thứ tự nào?

**Đáp án:** ngược thứ tự khai báo: ResultSet, PreparedStatement, Connection.

### Bài 13 — Ai đóng Connection?

Một repository nhận Connection từ service đang quản lý transaction. Repository có nên tự đóng connection đó không?

**Đáp án:** không. Caller/service sở hữu connection và chịu trách nhiệm commit/rollback/close. Repository đóng Statement/ResultSet do chính nó tạo.

### Bài 14 — Auto-commit

Muốn hai UPDATE cùng thành công hoặc cùng rollback, cần làm gì?

**Đáp án:** tắt auto-commit, thực hiện cả hai trên cùng connection, commit khi tất cả thành công và rollback khi lỗi.

### Bài 15 — Pool

Khi gọi `close()` trên connection lấy từ HikariCP, có nhất thiết socket vật lý bị đóng không?

**Đáp án:** không. Proxy thường trả connection về pool để tái sử dụng. Nhưng ứng dụng vẫn phải gọi close.

### Bài 16 — Batch

Dùng phương thức nào để thêm nhiều bộ tham số vào một batch PreparedStatement?

**Đáp án:** bind từng bộ, gọi `addBatch()`, sau đó `executeBatch()`; xử lý update counts và lỗi batch.

### Bài 17 — Generated key

Muốn lấy identity key vừa INSERT, có thể chuẩn bị statement với tùy chọn nào?

**Đáp án:** `Statement.RETURN_GENERATED_KEYS`, thực thi, sau đó đọc `statement.getGeneratedKeys()` theo hỗ trợ driver.

### Bài 18 — Fetch size

`setFetchSize(500)` có nghĩa chỉ lấy tối đa 500 hàng không?

**Đáp án:** không. Nó là gợi ý kích thước fetch mỗi lần cho driver, không phải giới hạn tổng hàng. Muốn giới hạn, dùng SQL LIMIT/FETCH FIRST hoặc pagination.

### Bài 19 — Retry

Một INSERT có thể đã commit nhưng client mất mạng trước khi nhận kết quả. Retry mù có thể gây gì?

**Đáp án:** có thể tạo bản ghi trùng hoặc lặp side effect. Cần idempotency key/unique constraint và chiến lược xác định kết quả trước khi retry.

### Bài 20 — Connection dùng chung

Hai thread dùng cùng Connection, một thread commit còn thread kia đang thao tác. Vì sao nguy hiểm?

**Đáp án:** transaction và trạng thái connection có thể bị trộn; JDBC không bảo đảm cách dùng đồng thời như vậy an toàn. Mỗi công việc cần connection riêng hoặc cơ chế transaction manager được thiết kế phù hợp.

### Bài 21 — Scrollable ResultSet

Muốn gọi `last()` hoặc `previous()`, cần yêu cầu loại ResultSet nào?

**Đáp án:** một loại scrollable như `TYPE_SCROLL_INSENSITIVE` hoặc `TYPE_SCROLL_SENSITIVE` nếu driver hỗ trợ. Default forward-only không đáp ứng.

### Bài 22 — SQLException

Ngoài message, cần xem thông tin nào khi chẩn đoán lỗi SQL?

**Đáp án:** SQLState, vendor error code, chained exceptions qua `getNextException()` và suppressed exceptions khi đóng tài nguyên.

### Bài 23 — Transaction boundary

Một transaction UPDATE database, sau đó chờ người dùng bấm nút trong 30 giây rồi mới commit. Rủi ro?

**Đáp án:** giữ connection/lock lâu, cạn pool và tăng contention. Tách quy trình thành các transaction ngắn hoặc workflow state rõ ràng.

### Bài 24 — Mapping DTO

Vì sao repository thường trả List/DTO thay vì ResultSet?

**Đáp án:** DTO không phụ thuộc cursor/Statement/Connection, nên resource có thể đóng trước khi dữ liệu được dùng ở tầng service/web. Với dữ liệu lớn, cần stream hoặc pagination có lifecycle rõ.

### Bài 25 — Chọn API đúng

Một câu SQL có thể trả ResultSet hoặc update count tùy procedure. Dùng API nào?

**Đáp án:** `execute()`, sau đó kiểm tra `getResultSet()`/`getUpdateCount()` và `getMoreResults()` khi có nhiều kết quả.

## 21. Checklist trước khi đưa JDBC code vào ứng dụng

1. **Driver:** dependency và phiên bản có tương thích DBMS/Java runtime?
2. **DataSource:** dùng DataSource/pool có lifecycle do ứng dụng quản lý?
3. **Connection ownership:** ai mượn, ai đóng, ai commit/rollback?
4. **Concurrency:** có chia sẻ Connection/Statement/ResultSet giữa thread không?
5. **SQL safety:** giá trị có bind bằng PreparedStatement? Identifier động có whitelist?
6. **Statement API:** executeQuery, executeUpdate hay execute được chọn đúng?
7. **ResultSet:** có gọi next trước getter, đọc đúng kiểu và đúng label?
8. **NULL:** primitive getter có kiểm tra wasNull khi cần?
9. **Precision:** tiền có dùng BigDecimal?
10. **Resources:** ResultSet, Statement, Connection đều đóng ở mọi đường?
11. **Transaction:** nhiều bước nghiệp vụ có nằm trên cùng connection và transaction?
12. **Rollback:** exception có rollback và giữ lỗi rollback dưới dạng suppressed?
13. **Pool:** timeout, pool size và max lifetime phù hợp tổng tải database?
14. **Batch:** có xử lý update counts, BatchUpdateException và chunk size?
15. **Generated keys:** driver có hỗ trợ cách lấy khóa đã chọn?
16. **Large results:** có pagination/fetch size/streaming thay vì tải tất cả vào heap?
17. **Timeout:** statement, network, pool và request deadline có phối hợp?
18. **Retry:** chỉ retry lỗi phù hợp, có giới hạn và idempotency?
19. **Logging:** có log SQLState/vendor code nhưng che dữ liệu nhạy cảm?
20. **Integration test:** có kiểm thử bằng đúng DBMS/driver được triển khai?

## 22. Tổng kết

Quản lý JDBC tốt là quản lý **vòng đời tài nguyên, tham số SQL, cursor và transaction**:

- **DataSource** cung cấp connection; ứng dụng server thường dùng pool để tái sử dụng kết nối vật lý.
- **Connection** giữ trạng thái phiên và transaction. Mượn cho một đơn vị công việc, không chia sẻ tùy tiện giữa thread, và đóng khi xong.
- **Statement** thực thi SQL tĩnh; **PreparedStatement** bind giá trị an toàn; **CallableStatement** gọi routine theo hỗ trợ DBMS.
- Chọn đúng `executeQuery`, `executeUpdate` hoặc `execute` theo loại kết quả.
- **ResultSet** là cursor: gọi `next()` trước khi đọc, dùng getter đúng kiểu, kiểm tra `wasNull()` sau primitive getter và map dữ liệu trong phạm vi resource còn mở.
- **try-with-resources** giúp đóng ResultSet, Statement và Connection theo thứ tự phù hợp.
- **Transaction** gom các thao tác phải thành công/thất bại cùng nhau; rollback khi lỗi và giữ transaction ngắn.
- **Batch, generated keys, fetch size và pagination** hỗ trợ workload lớn, nhưng chi tiết phụ thuộc driver và DBMS.
- **SQLException** cần được phân loại; retry phải có giới hạn, idempotency và hiểu kết quả có thể đã commit.

Nguyên tắc thực hành: **mượn connection đúng phạm vi, bind dữ liệu thay vì ghép SQL, đọc ResultSet trong lúc tài nguyên còn mở, đóng mọi resource và xác định transaction boundary theo nghiệp vụ**. Khi hiểu rõ các ranh giới này, code Java truy cập database dễ kiểm soát, an toàn và vận hành ổn định hơn.

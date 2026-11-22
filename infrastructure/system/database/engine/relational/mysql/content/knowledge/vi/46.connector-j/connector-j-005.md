# Connection, Statement, PreparedStatement và CallableStatement

MySQL Connector/J là JDBC driver giúp ứng dụng Java kết nối và làm việc với MySQL. JDBC định nghĩa các interface chuẩn như Connection, Statement, PreparedStatement, CallableStatement và ResultSet; Connector/J cung cấp phần triển khai để những interface này giao tiếp với MySQL Server.

Chọn đúng loại statement ảnh hưởng trực tiếp đến an toàn SQL, khả năng tái sử dụng câu lệnh, cách truyền tham số và xử lý kết quả. Statement phù hợp với SQL tĩnh không có tham số; PreparedStatement phù hợp với truy vấn có dữ liệu đầu vào; CallableStatement dành cho stored procedure hoặc stored function. Cả ba đều hoạt động trên một Connection và cần được đóng đúng cách.

Bài học thuộc chương **Connector/J** của module DATABASE_MYSQL. Module bao quát thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, tối ưu truy vấn, phân quyền, sao lưu và vận hành cơ sở dữ liệu quan hệ. Ví dụ dùng Java JDBC và MySQL Connector/J hiện đại; hãy đối chiếu tài liệu của phiên bản Connector/J và JDK thực tế trong dự án.

Sau bài học, bạn có thể:

- Tạo và quản lý Connection tới MySQL bằng JDBC.
- Phân biệt Statement, PreparedStatement và CallableStatement.
- Bind đúng kiểu dữ liệu và xử lý giá trị NULL.
- Đọc ResultSet, update count và generated keys.
- Thực thi batch và transaction có kiểm soát.
- Gọi stored procedure/function với tham số IN, OUT và INOUT.
- Xử lý SQLException, retry có giới hạn và quản lý tài nguyên.
- Chọn cấu hình Connector/J phù hợp với TLS, connection pool và workload.

## 1. Vai trò của JDBC và Connector/J

JDBC là API chuẩn của Java để truy cập cơ sở dữ liệu quan hệ. Ứng dụng gọi các interface trong package java.sql và javax.sql; driver chuyển các lời gọi đó thành giao thức phù hợp với database.

Các thành phần thường gặp:

| Thành phần | Vai trò |
|---|---|
| DriverManager | Tạo kết nối từ JDBC URL và thông tin xác thực. |
| DataSource | Cách tạo kết nối được khuyến nghị trong ứng dụng; có thể được bọc bởi connection pool. |
| Connection | Đại diện cho một phiên làm việc với MySQL, quản lý transaction và tạo statement. |
| Statement | Thực thi SQL không cần bind tham số. |
| PreparedStatement | Thực thi SQL có placeholder và bind giá trị theo vị trí. |
| CallableStatement | Gọi stored procedure hoặc stored function và đăng ký tham số OUT. |
| ResultSet | Đọc hàng và cột được trả về bởi truy vấn. |
| SQLException | Mang thông tin lỗi JDBC, SQLState và mã lỗi của driver/server. |

Connector/J hiện đại tự đăng ký JDBC driver thông qua cơ chế service provider của Java. Trong ứng dụng thông thường, không cần gọi Class.forName để nạp driver bằng tay. Class driver hiện tại là com.mysql.cj.jdbc.Driver; tên class cũ com.mysql.jdbc.Driver thuộc các phiên bản Connector/J rất cũ và không nên dùng trong code mới.

## 2. Thêm Connector/J vào dự án

Nếu dự án dùng Maven, khai báo dependency Connector/J. Chọn phiên bản đã được kiểm thử và tương thích với JDK cùng MySQL Server của dự án.

~~~xml
<dependency>
  <groupId>com.mysql</groupId>
  <artifactId>mysql-connector-j</artifactId>
  <version>VERSION_APPROVED_BY_PROJECT</version>
</dependency>
~~~

Thay VERSION_APPROVED_BY_PROJECT bằng phiên bản cụ thể được dự án phê duyệt; không để chuỗi giữ chỗ này trong file build thật.

Nếu dùng Gradle:

~~~gradle
dependencies {
    runtimeOnly("com.mysql:mysql-connector-j:VERSION_APPROVED_BY_PROJECT")
}
~~~

Ứng dụng chỉ cần driver ở runtime nếu compile code chỉ dùng interface JDBC chuẩn. Nếu code khởi tạo class đặc thù của Connector/J như MysqlDataSource, dependency có thể cần ở compile classpath.

Không tải JAR không rõ nguồn hoặc đặt nhiều phiên bản Connector/J cùng lúc trong classpath. Phiên bản driver được nạp có thể khác phiên bản dự kiến, gây lỗi khó chẩn đoán.

## 3. JDBC URL và tạo Connection

JDBC URL của MySQL có dạng tổng quát:

~~~text
jdbc:mysql://host:port/database?property=value
~~~

Ví dụ:

~~~text
jdbc:mysql://mysql.example.internal:3306/sales?sslMode=VERIFY_IDENTITY&connectionTimeZone=UTC
~~~

Trong URL:

- jdbc:mysql là scheme dành cho MySQL Connector/J.
- mysql.example.internal là hostname của server.
- 3306 là cổng MySQL thường dùng, có thể khác theo môi trường.
- sales là database mặc định của kết nối.
- sslMode=VERIFY_IDENTITY yêu cầu TLS và kiểm tra danh tính server theo chứng thư.
- connectionTimeZone=UTC cấu hình múi giờ kết nối theo UTC trên các phiên bản Connector/J hỗ trợ thuộc tính này.

Khi dùng VERIFY_IDENTITY, cấu hình trust store/CA phù hợp để driver xác minh chứng thư của server. Không tắt xác minh TLS để né lỗi chứng thư trong production. Kiểm tra tài liệu Connector/J cho các thuộc tính bảo mật và timezone theo phiên bản.

### 3.1. Dùng DriverManager

Ví dụ tạo một kết nối đơn giản:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class DbConnectionExample {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("MYSQL_JDBC_URL");
        String user = System.getenv("MYSQL_USER");
        String password = System.getenv("MYSQL_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {
            System.out.println("Connected: " +
                connection.getMetaData().getDatabaseProductVersion());
        }
    }
}
~~~

Ví dụ lấy thông tin xác thực từ biến môi trường để minh họa. Trong hệ thống thực tế, dùng secret manager hoặc cơ chế cấp phát secret của nền tảng. Không hard-code mật khẩu vào source code, commit file cấu hình có secret hoặc ghi mật khẩu vào log.

Try-with-resources tự đóng Connection khi thoát khỏi block, kể cả khi có exception. Khi connection đến từ pool, close thường trả connection về pool để tái sử dụng thay vì đóng socket vật lý; chi tiết này phụ thuộc DataSource/pool.

### 3.2. Dùng DataSource

DataSource tách cấu hình tạo kết nối khỏi code nghiệp vụ và là điểm tích hợp với connection pool.

Có thể khởi tạo DataSource của Connector/J:

~~~java
import com.mysql.cj.jdbc.MysqlDataSource;
import javax.sql.DataSource;

MysqlDataSource mysqlDataSource = new MysqlDataSource();
mysqlDataSource.setURL(
    "jdbc:mysql://mysql.example.internal:3306/sales" +
    "?sslMode=VERIFY_IDENTITY&connectionTimeZone=UTC"
);

DataSource dataSource = mysqlDataSource;

try (Connection connection =
         dataSource.getConnection(user, password)) {
    // Thực hiện công việc JDBC.
}
~~~

MysqlDataSource của Connector/J cung cấp DataSource, nhưng bản thân việc dùng DataSource không đồng nghĩa đã có connection pool. Trong ứng dụng server, thường đặt một pool được quản lý như HikariCP trước DataSource để giới hạn số connection, tái sử dụng socket và kiểm soát timeout.

Không tạo một connection pool mới cho từng request. Tạo pool ở vòng đời ứng dụng, cấu hình giới hạn connection theo năng lực MySQL và đóng pool khi ứng dụng dừng.

## 4. Quản lý vòng đời Connection

Connection đại diện cho một phiên database và có thể mang trạng thái:

- Auto-commit bật/tắt.
- Transaction isolation level.
- Read-only hint.
- Catalog/schema hiện tại.
- Session variables và timezone.
- Các statement đang mở.

Một số nguyên tắc:

- Mở connection gần thời điểm cần dùng.
- Đóng connection bằng try-with-resources.
- Không giữ connection trong thời gian gọi HTTP hoặc chờ người dùng.
- Không chia sẻ một Connection giữa nhiều thread cùng lúc.
- Không lưu Connection như singleton dùng chung cho toàn ứng dụng.
- Với pool, trả connection sớm để request khác có thể sử dụng.
- Đặt connect timeout, socket timeout và pool timeout theo yêu cầu ứng dụng.

Ví dụ đọc trạng thái:

~~~java
try (Connection connection =
         dataSource.getConnection()) {
    System.out.println("Auto commit: " +
        connection.getAutoCommit());
    System.out.println("Read only: " +
        connection.isReadOnly());
    System.out.println("Isolation: " +
        connection.getTransactionIsolation());
}
~~~

Không dựa vào Connection mặc định để suy luận isolation level hoặc trạng thái session của mọi môi trường. Hãy kiểm tra và cấu hình rõ ràng khi nghiệp vụ có yêu cầu.

## 5. Statement: thực thi SQL tĩnh

Statement phù hợp khi câu SQL cố định và không cần đưa giá trị từ đầu vào vào câu lệnh. Ví dụ chạy một câu truy vấn metadata hoặc DDL đã được xác định trong code:

~~~java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

String sql = "SELECT VERSION()";

try (Connection connection = dataSource.getConnection();
     Statement statement = connection.createStatement();
     ResultSet resultSet = statement.executeQuery(sql)) {

    if (resultSet.next()) {
        System.out.println(resultSet.getString(1));
    }
}
~~~

Các phương thức thường dùng:

| Phương thức | Dùng khi | Kết quả |
|---|---|---|
| executeQuery(sql) | Câu lệnh trả về một ResultSet, thường là SELECT | ResultSet |
| executeUpdate(sql) | INSERT, UPDATE, DELETE hoặc DDL đơn giản | Số hàng bị tác động; DDL thường trả về 0 |
| execute(sql) | Chưa biết câu lệnh trả ResultSet hay update count, hoặc có nhiều kết quả | boolean cho biết kết quả đầu tiên có phải ResultSet hay không |
| addBatch(sql) | Thêm câu SQL tĩnh vào batch | Không trả kết quả ngay |
| executeBatch() | Chạy các câu đã thêm vào batch | Mảng update count |

Không dùng Statement để ghép dữ liệu người dùng vào SQL. Ví dụ sau không an toàn:

~~~java
String sql =
    "SELECT * FROM sales.orders WHERE customer_id = " +
    requestCustomerId;
Statement statement = connection.createStatement();
ResultSet resultSet = statement.executeQuery(sql);
~~~

Nếu requestCustomerId chứa cú pháp SQL ngoài dự kiến, câu lệnh có thể bị thay đổi. Dùng PreparedStatement để truyền dữ liệu thay vì nối chuỗi.

Statement cũng có thể tạo PreparedStatement và CallableStatement thông qua Connection. Khi một Statement thực thi câu SQL mới, ResultSet hiện tại gắn với statement đó thường sẽ bị đóng. Hãy đọc hết ResultSet hoặc đóng nó trước khi tái sử dụng statement.

## 6. PreparedStatement: SQL có tham số

PreparedStatement là lựa chọn mặc định cho truy vấn có dữ liệu đầu vào. Câu SQL dùng dấu hỏi làm placeholder; ứng dụng bind giá trị theo vị trí, bắt đầu từ 1.

~~~java
String sql = """
    SELECT order_id, total_amount, status
    FROM sales.orders
    WHERE customer_id = ?
      AND status = ?
    ORDER BY order_id DESC
    LIMIT ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);
    statement.setString(2, "PAID");
    statement.setInt(3, 50);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            var total = resultSet.getBigDecimal("total_amount");
            String status = resultSet.getString("status");

            System.out.printf(
                "%d %s %s%n", orderId, total, status
            );
        }
    }
}
~~~

Ví dụ dùng text block của Java 15 trở lên. Nếu dự án dùng Java cũ hơn, thay text block bằng chuỗi nối dòng hoặc chuỗi thông thường.

PreparedStatement có các lợi ích:

- Tách cấu trúc SQL khỏi giá trị đầu vào.
- Tránh việc dữ liệu bind được diễn giải như cú pháp SQL.
- Giảm công việc parse/prepare khi statement được tái sử dụng phù hợp.
- Bind kiểu dữ liệu rõ ràng.
- Hỗ trợ batch với cùng một cấu trúc SQL.

PreparedStatement không tự động làm truy vấn nhanh trong mọi trường hợp. Index, execution plan, số hàng trả về, network round trip và cách dùng connection vẫn quyết định phần lớn hiệu năng.

## 7. Bind kiểu dữ liệu đúng cách

Dùng setter phù hợp với kiểu cột và giá trị Java:

| Kiểu SQL thường gặp | Setter JDBC gợi ý |
|---|---|
| TINYINT, SMALLINT, INT | setByte, setShort, setInt |
| BIGINT | setLong |
| DECIMAL, NUMERIC | setBigDecimal |
| FLOAT, DOUBLE | setFloat, setDouble |
| CHAR, VARCHAR, TEXT | setString |
| BINARY, VARBINARY, BLOB | setBytes hoặc stream setter |
| DATE | setDate hoặc setObject với LocalDate nếu phiên bản hỗ trợ |
| TIME | setTime hoặc setObject với LocalTime nếu hỗ trợ |
| TIMESTAMP | setTimestamp hoặc setObject với LocalDateTime/Instant theo mapping đã chọn |
| BOOLEAN | setBoolean; xác nhận quy ước kiểu boolean/tinyint trong schema |

Không chuyển mọi dữ liệu thành chuỗi rồi dựa vào MySQL tự ép kiểu. Bind đúng kiểu giúp code rõ ràng và tránh khác biệt chuyển đổi giữa phiên bản, timezone hoặc SQL mode.

### 7.1. DECIMAL và tiền tệ

Với giá trị tiền tệ, dùng BigDecimal thay cho double/float để tránh sai số nhị phân:

~~~java
BigDecimal amount = new BigDecimal("1250.75");

try (PreparedStatement statement =
         connection.prepareStatement(
             "UPDATE sales.orders SET total_amount = ? " +
             "WHERE order_id = ?")) {

    statement.setBigDecimal(1, amount);
    statement.setLong(2, orderId);
    int changed = statement.executeUpdate();
}
~~~

Tạo BigDecimal từ chuỗi thập phân hoặc nguồn dữ liệu thập phân chính xác. Không dùng new BigDecimal(0.1) nếu cần biểu diễn chính xác giá trị thập phân 0.1.

### 7.2. Giá trị NULL

Dùng setNull với SQL type tương ứng khi tham số có giá trị null:

~~~java
if (phoneNumber == null) {
    statement.setNull(1, java.sql.Types.VARCHAR);
} else {
    statement.setString(1, phoneNumber);
}
~~~

Có thể dùng setObject(index, null, Types.VARCHAR) khi phù hợp. Không truyền chuỗi "NULL" vì đó là văn bản, không phải SQL NULL.

Điều kiện SQL cũng cần xử lý đúng NULL. So sánh cột bằng dấu bằng với tham số NULL không trả về TRUE; dùng IS NULL hoặc biểu thức null-safe phù hợp. Ví dụ, nếu bộ lọc có thể vắng mặt, hãy xây dựng điều kiện rõ ràng thay vì mong đợi column = NULL hoạt động.

### 7.3. Ngày giờ và timezone

MySQL có DATE, TIME, DATETIME và TIMESTAMP với ngữ nghĩa khác nhau. TIMESTAMP được chuyển đổi theo timezone session khi ghi/đọc; DATETIME lưu thành phần ngày giờ mà không tự biểu diễn một instant có timezone.

Chọn mapping Java theo ý nghĩa nghiệp vụ:

- LocalDate cho ngày lịch, chẳng hạn ngày sinh hoặc ngày lập hóa đơn.
- LocalDateTime cho thời điểm ngày/giờ không gắn timezone, nếu schema dùng DATETIME theo quy ước đó.
- Instant hoặc OffsetDateTime cho một thời điểm toàn cục; chuyển đổi rõ ràng sang kiểu SQL và timezone kết nối.
- Không dựa vào timezone mặc định của máy chạy ứng dụng.

Cấu hình timezone kết nối nhất quán giữa ứng dụng và database. Kiểm thử dữ liệu qua thời điểm chuyển ngày và các môi trường có timezone khác nhau.

## 8. Placeholder chỉ dùng cho giá trị, không dùng cho tên cột

Dấu hỏi trong PreparedStatement đại diện cho giá trị dữ liệu. Nó không thay thế được tên table, tên column, từ khóa ORDER BY hoặc một phần cú pháp SQL.

Ví dụ không hoạt động như mong đợi:

~~~java
String sql = "SELECT * FROM sales.orders ORDER BY ?";
~~~

Placeholder trên là một giá trị biểu thức, không phải tên cột động. Nếu cần sort theo lựa chọn người dùng, dùng whitelist:

~~~java
String sortColumn;
switch (requestedSort) {
    case "created" -> sortColumn = "created_at";
    case "amount" -> sortColumn = "total_amount";
    default -> sortColumn = "order_id";
}

String sql =
    "SELECT order_id, total_amount " +
    "FROM sales.orders ORDER BY " + sortColumn + " DESC";
~~~

Chỉ ghép tên cột được chọn từ danh sách cố định do ứng dụng kiểm soát. Không ghép trực tiếp giá trị request vào SQL.

### 8.1. IN với số lượng tham số thay đổi

Để truyền danh sách ID, tạo đúng số placeholder và bind từng phần tử. Kiểm tra trường hợp danh sách rỗng trước khi tạo SQL:

~~~java
if (orderIds.isEmpty()) {
    return List.of();
}

String placeholders = String.join(
    ",", Collections.nCopies(orderIds.size(), "?")
);

String sql =
    "SELECT order_id, status " +
    "FROM sales.orders WHERE order_id IN (" +
    placeholders + ")";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {
    for (int i = 0; i < orderIds.size(); i++) {
        statement.setLong(i + 1, orderIds.get(i));
    }

    try (ResultSet rs = statement.executeQuery()) {
        // Đọc kết quả.
    }
}
~~~

Danh sách rất lớn có thể tạo SQL dài và nhiều placeholder. Khi đó, chia thành batch, dùng bảng tạm hoặc cơ chế truyền tập dữ liệu phù hợp. Luôn giới hạn kích thước đầu vào để tránh statement quá lớn.

## 9. ResultSet: đọc kết quả truy vấn

ResultSet thường là cursor tiến về phía trước. Gọi next() để chuyển tới hàng kế tiếp; khi trả về false thì đã hết kết quả.

~~~java
String sql =
    "SELECT order_id, total_amount, created_at " +
    "FROM sales.orders WHERE customer_id = ?";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            BigDecimal amount = rs.getBigDecimal("total_amount");
            Timestamp createdAt = rs.getTimestamp("created_at");

            System.out.println(orderId + " " + amount + " " + createdAt);
        }
    }
}
~~~

Có thể truy cập cột bằng index bắt đầu từ 1 hoặc bằng label. Dùng label thường dễ đọc và ít phụ thuộc thứ tự cột trong SELECT.

### 9.1. Phân biệt SQL NULL với giá trị mặc định của Java

Một số getter trả về primitive nên không thể biểu diễn null. Ví dụ getLong trả về 0 nếu cột SQL là NULL. Gọi wasNull ngay sau getter để kiểm tra:

~~~java
long quantity = rs.getLong("quantity");
if (rs.wasNull()) {
    // Cột quantity là SQL NULL.
} else {
    // quantity chứa giá trị thực.
}
~~~

Với kiểu tham chiếu như String, BigDecimal, Date, getter thường trả null khi SQL value là NULL. Dù vậy, hãy kiểm tra null trước khi dùng.

### 9.2. ResultSet và vòng đời Statement

ResultSet phụ thuộc vào Statement đã tạo ra nó. Đóng Statement thường đóng ResultSet liên quan. Try-with-resources lồng nhau giúp đóng đúng thứ tự:

1. ResultSet được đóng trước.
2. PreparedStatement được đóng tiếp.
3. Connection được đóng cuối cùng.

Không trả ResultSet ra khỏi phạm vi mà Statement/Connection đã bị đóng. Nếu tầng service cần dữ liệu sau khi đóng kết nối, map kết quả thành DTO hoặc collection trước.

### 9.3. ResultSet lớn

Mặc định, cách driver lấy dữ liệu có thể khiến kết quả lớn tiêu tốn nhiều bộ nhớ phía client. Hãy giới hạn số hàng bằng SQL, phân trang theo keyset hoặc dùng cơ chế streaming/cursor fetch được Connector/J hỗ trợ.

setFetchSize là gợi ý cho driver, không phải cam kết chung rằng dữ liệu sẽ được tải theo từng batch. Connector/J có các chế độ streaming riêng; một số cấu hình dùng server-side prepared statements cùng useCursorFetch và fetch size dương. Cấu hình streaming đặc thù cần kiểm tra tài liệu Connector/J, vì có thể giữ connection bận cho đến khi ResultSet được đọc hết hoặc đóng.

Không mở một ResultSet streaming lớn rồi thực hiện thêm truy vấn khác trên cùng connection khi driver yêu cầu ResultSet phải được tiêu thụ trước. Với kết quả lớn, đọc tuần tự, xử lý từng hàng và đóng cursor sớm.

## 10. executeQuery, executeUpdate và execute

Chọn phương thức theo loại kết quả mong đợi.

~~~java
// Truy vấn trả ResultSet
try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT status FROM sales.orders WHERE order_id = ?")) {
    ps.setLong(1, orderId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String status = rs.getString(1);
        }
    }
}

// DML trả update count
try (PreparedStatement ps =
         connection.prepareStatement(
             "UPDATE sales.orders SET status = ? WHERE order_id = ?")) {
    ps.setString(1, "SHIPPED");
    ps.setLong(2, orderId);
    int affectedRows = ps.executeUpdate();
}

// DDL hoặc câu lệnh chưa biết kiểu kết quả
try (Statement st = connection.createStatement()) {
    boolean hasResultSet = st.execute(
        "CREATE TEMPORARY TABLE tmp_work (id BIGINT PRIMARY KEY)"
    );
}
~~~

executeUpdate thường dùng cho INSERT, UPDATE, DELETE và DDL. Với DDL, update count thường là 0; không diễn giải 0 là DDL thất bại.

execute dùng khi câu lệnh có thể trả ResultSet, update count hoặc nhiều kết quả. Ví dụ stored procedure có thể trả nhiều result set và update count; hãy dùng getResultSet, getUpdateCount và getMoreResults để tiêu thụ kết quả theo thứ tự.

## 11. Lấy generated key sau INSERT

Nếu table dùng AUTO_INCREMENT, có thể yêu cầu JDBC trả generated keys:

~~~java
String sql =
    "INSERT INTO sales.orders (customer_id, status, total_amount) " +
    "VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(
         sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setLong(1, customerId);
    ps.setString(2, "NEW");
    ps.setBigDecimal(3, new BigDecimal("125.00"));

    int inserted = ps.executeUpdate();

    if (inserted != 1) {
        throw new SQLException("Unexpected insert count: " + inserted);
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long newOrderId = keys.getLong(1);
        } else {
            throw new SQLException("No generated key returned");
        }
    }
}
~~~

Generated keys là cách JDBC lấy khóa do database sinh ra cho lần thực thi đó. Không dùng SELECT MAX(id) để tìm khóa vừa insert vì kết nối khác có thể insert một hàng giữa hai câu lệnh, khiến kết quả sai.

Nếu insert nhiều hàng trong một batch, khả năng và số lượng generated keys trả về phụ thuộc driver, phiên bản và cấu hình. Hãy kiểm thử với đúng phiên bản Connector/J; nếu cần ánh xạ chính xác từng khóa, cân nhắc insert theo nhóm nhỏ hoặc thiết kế API database phù hợp.

## 12. Batch với PreparedStatement

Batch giảm số lần round trip khi thực hiện nhiều câu lệnh có cùng cấu trúc SQL.

~~~java
String sql =
    "INSERT INTO sales.order_items " +
    "(order_id, product_id, quantity) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderItem item : items) {
        ps.setLong(1, item.orderId());
        ps.setLong(2, item.productId());
        ps.setInt(3, item.quantity());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

Mỗi vòng lặp gán lại tất cả tham số rồi gọi addBatch. Nếu bỏ quên một tham số, giá trị cũ có thể còn gắn với placeholder đó tùy trạng thái statement; luôn bind đầy đủ các tham số cho mỗi batch entry.

### 12.1. Batch update count

Mảng kết quả của executeBatch có thể chứa:

- Số hàng bị tác động.
- Statement.SUCCESS_NO_INFO nếu driver không biết chính xác số hàng.
- Statement.EXECUTE_FAILED cho phần tử thất bại trong một số trường hợp.

BatchUpdateException cung cấp getUpdateCounts để điều tra phần kết quả. Không giả định toàn bộ batch đã thành công chỉ vì một số phần tử có update count hợp lệ.

### 12.2. Batch và transaction

Batch không tự đảm bảo tính nguyên tử của toàn bộ công việc. Nếu cần tất cả hàng cùng commit hoặc rollback, dùng transaction rõ ràng:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO sales.order_items " +
            "(order_id, product_id, quantity) VALUES (?, ?, ?)")) {

        for (OrderItem item : items) {
            ps.setLong(1, item.orderId());
            ps.setLong(2, item.productId());
            ps.setInt(3, item.quantity());
            ps.addBatch();
        }

        ps.executeBatch();
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

Nếu batch rất lớn, không nhất thiết gom toàn bộ vào một transaction duy nhất. Chia thành batch transaction nhỏ để kiểm soát undo/redo, lock time và khả năng retry. Điều đó có nghĩa mỗi batch là một đơn vị commit riêng; thiết kế nghiệp vụ phải chấp nhận tiến trình từng phần.

Connector/J có thuộc tính rewriteBatchedStatements để tối ưu một số batch bằng cách viết lại thành câu lệnh nhiều hàng hoặc cách thực thi tương ứng. Đây là tối ưu phụ thuộc loại SQL và driver version; đo thực tế và kiểm tra semantics/update counts trước khi bật rộng rãi.

## 13. CallableStatement: gọi stored procedure

CallableStatement dùng cú pháp JDBC escape để gọi stored procedure hoặc function. Với procedure, dạng phổ biến là:

~~~text
{call schema.procedure_name(?, ?, ?)}
~~~

Ví dụ procedure nhận order ID và trả tổng tiền qua tham số OUT:

~~~sql
DELIMITER //

CREATE PROCEDURE sales.get_order_total(
    IN p_order_id BIGINT,
    OUT p_total DECIMAL(12,2)
)
BEGIN
    SELECT COALESCE(SUM(total_amount), 0)
    INTO p_total
    FROM sales.orders
    WHERE order_id = p_order_id;
END//

DELIMITER ;
~~~

Gọi procedure từ Java:

~~~java
String call = "{call sales.get_order_total(?, ?)}";

try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(call)) {

    cs.setLong(1, orderId);
    cs.registerOutParameter(2, Types.DECIMAL);

    cs.execute();

    BigDecimal total = cs.getBigDecimal(2);
}
~~~

Thứ tự quan trọng:

1. Tạo CallableStatement bằng prepareCall.
2. Bind tham số IN.
3. Đăng ký kiểu SQL cho tham số OUT.
4. Gọi execute.
5. Đọc giá trị OUT bằng getter phù hợp.

### 13.1. Tham số IN, OUT và INOUT

| Loại tham số | Cách dùng |
|---|---|
| IN | Gọi setXxx để truyền giá trị vào procedure. |
| OUT | Gọi registerOutParameter trước execute, rồi đọc giá trị sau execute. |
| INOUT | Vừa set giá trị đầu vào vừa registerOutParameter, sau đó đọc giá trị mới. |

Ví dụ INOUT:

~~~java
try (CallableStatement cs =
         connection.prepareCall("{call sales.adjust_limit(?, ?)}")) {

    cs.setLong(1, accountId);
    cs.setBigDecimal(2, currentLimit);
    cs.registerOutParameter(2, Types.DECIMAL);

    cs.execute();

    BigDecimal adjustedLimit = cs.getBigDecimal(2);
}
~~~

Ví dụ này giả định tham số thứ hai trong procedure được khai báo INOUT DECIMAL. Phải khớp thứ tự, kiểu và mode với định nghĩa procedure trên server.

### 13.2. Gọi stored function

Function trả một giá trị thông qua placeholder đầu tiên:

~~~java
try (CallableStatement cs =
         connection.prepareCall(
             "{? = call sales.calculate_tax(?)}")) {

    cs.registerOutParameter(1, Types.DECIMAL);
    cs.setBigDecimal(2, new BigDecimal("100.00"));

    cs.execute();

    BigDecimal tax = cs.getBigDecimal(1);
}
~~~

Placeholder đầu tiên là giá trị trả về của function; tham số tiếp theo là tham số đầu vào. Kiểu SQL đăng ký phải tương thích với kiểu trả về thực tế.

## 14. CallableStatement có ResultSet và nhiều kết quả

Stored procedure có thể trả một hoặc nhiều ResultSet, update count và OUT parameter. Trong trường hợp này, execute trả boolean cho biết kết quả đầu tiên có phải ResultSet hay không. Dùng getMoreResults để tiếp tục đọc.

~~~java
try (CallableStatement cs =
         connection.prepareCall("{call sales.get_customer_orders(?)}")) {

    cs.setLong(1, customerId);

    boolean hasResultSet = cs.execute();

    while (true) {
        if (hasResultSet) {
            try (ResultSet rs = cs.getResultSet()) {
                while (rs.next()) {
                    long orderId = rs.getLong("order_id");
                    String status = rs.getString("status");
                }
            }
        } else {
            int updateCount = cs.getUpdateCount();
            if (updateCount == -1) {
                break;
            }
        }

        hasResultSet =
            cs.getMoreResults(Statement.CLOSE_CURRENT_RESULT);
    }
}
~~~

Không chỉ đọc ResultSet đầu tiên rồi đóng CallableStatement nếu procedure còn trả kết quả tiếp theo mà ứng dụng cần. Kiểm tra thiết kế procedure để tránh trả result set không cần thiết.

OUT parameter có thể được đọc sau khi procedure thực thi; khi procedure trả nhiều result set, hãy tiêu thụ các kết quả theo quy tắc JDBC và kiểm tra hành vi của Connector/J theo phiên bản. Không để ứng dụng phụ thuộc vào một thứ tự kết quả không được quy định trong hợp đồng procedure.

## 15. Transaction qua Connection

Mặc định, JDBC Connection thường ở chế độ auto-commit. Mỗi câu lệnh được commit riêng khi hoàn thành. Với nghiệp vụ gồm nhiều thao tác cần nguyên tử, tắt auto-commit và điều khiển transaction tường minh.

Ví dụ chuyển tiền giữa hai tài khoản:

~~~java
String debitSql =
    "UPDATE banking.account " +
    "SET balance = balance - ? " +
    "WHERE account_id = ? AND balance >= ?";

String creditSql =
    "UPDATE banking.account " +
    "SET balance = balance + ? " +
    "WHERE account_id = ?";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement debit =
             connection.prepareStatement(debitSql);
         PreparedStatement credit =
             connection.prepareStatement(creditSql)) {

        BigDecimal amount = new BigDecimal("50.00");

        debit.setBigDecimal(1, amount);
        debit.setLong(2, fromAccountId);
        debit.setBigDecimal(3, amount);

        int debited = debit.executeUpdate();
        if (debited != 1) {
            throw new SQLException("Insufficient funds or account missing");
        }

        credit.setBigDecimal(1, amount);
        credit.setLong(2, toAccountId);

        int credited = credit.executeUpdate();
        if (credited != 1) {
            throw new SQLException("Destination account missing");
        }

        connection.commit();
    } catch (SQLException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
~~~

Trong ví dụ, debit chỉ thành công nếu số dư đủ và account tồn tại. Nếu credit thất bại, rollback đưa cả hai thao tác về trạng thái trước transaction. Các bảng phải dùng engine transactional như InnoDB để có bảo đảm rollback phù hợp.

Không gọi dịch vụ thanh toán, gửi email hoặc thực hiện HTTP request bên trong transaction database dài. Giao dịch ngoài database không tự rollback cùng MySQL. Dùng transactional outbox hoặc quy trình phối hợp phù hợp nếu nghiệp vụ cần đồng bộ side effect.

### 15.1. Isolation level

JDBC cho phép đọc và đặt isolation level:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
~~~

Các mức chuẩn gồm:

- TRANSACTION_READ_UNCOMMITTED.
- TRANSACTION_READ_COMMITTED.
- TRANSACTION_REPEATABLE_READ.
- TRANSACTION_SERIALIZABLE.

InnoDB thường mặc định REPEATABLE READ, nhưng cấu hình server/session có thể thay đổi. Chọn isolation level theo yêu cầu nhất quán và mô hình khóa; không đổi chỉ để giảm lock wait mà chưa kiểm tra ảnh hưởng đến nghiệp vụ.

### 15.2. Savepoint

Savepoint cho phép rollback một phần công việc trong transaction:

~~~java
Savepoint savepoint = connection.setSavepoint("before_optional_step");

try {
    // Thao tác tùy chọn.
} catch (SQLException e) {
    connection.rollback(savepoint);
}

// Tiếp tục hoặc commit transaction.
~~~

Savepoint không phải transaction độc lập. Commit hoặc rollback transaction ngoài cùng vẫn quyết định kết quả cuối.

## 16. SQLException và chẩn đoán lỗi

SQLException cung cấp nhiều thông tin hơn message:

~~~java
try {
    // Thao tác JDBC.
} catch (SQLException e) {
    System.err.println("Message: " + e.getMessage());
    System.err.println("SQLState: " + e.getSQLState());
    System.err.println("Vendor code: " + e.getErrorCode());

    for (SQLException next = e.getNextException();
         next != null;
         next = next.getNextException()) {
        System.err.println("Next: " + next.getMessage());
    }

    throw e;
}
~~~

Các trường cần lưu ý:

- getMessage(): mô tả lỗi.
- getSQLState(): mã trạng thái theo chuẩn SQL hoặc driver.
- getErrorCode(): mã lỗi cụ thể của MySQL/driver.
- getNextException(): lỗi tiếp theo trong chuỗi lỗi.
- getCause(): nguyên nhân gốc nếu có.

Có thể phân loại theo SQLState và mã lỗi vendor. Ví dụ, nhóm SQLState bắt đầu bằng 23 thường liên quan vi phạm constraint; deadlock MySQL thường có mã lỗi 1213 và SQLState 40001; lock wait timeout thường có mã lỗi 1205. Luôn xác nhận mã theo phiên bản và ngữ cảnh lỗi thực tế.

### 16.1. Retry transaction

Retry chỉ phù hợp với lỗi tạm thời có thể phục hồi và nghiệp vụ cho phép thực hiện lại. Với deadlock, transaction bị chọn làm nạn nhân đã rollback; ứng dụng có thể retry toàn bộ transaction từ đầu với giới hạn số lần và backoff.

Không retry chỉ dựa vào việc bắt mọi SQLException. Lỗi cú pháp, thiếu quyền, sai schema, vi phạm dữ liệu hoặc lỗi xác thực không được giải quyết bằng retry.

Nếu mất kết nối trong lúc commit, kết quả commit có thể chưa rõ đối với client. Không được giả định transaction chắc chắn rollback. Với nghiệp vụ cần chống lặp, dùng idempotency key hoặc mã giao dịch duy nhất để kiểm tra kết quả trước khi thực hiện lại.

### 16.2. SQLWarning

Một số thao tác có thể trả cảnh báo mà không ném SQLException. JDBC cung cấp getWarnings và clearWarnings trên Connection, Statement và ResultSet. Khi import hoặc chuyển đổi dữ liệu, hãy kiểm tra warning để phát hiện truncation, conversion hoặc điều kiện bất thường mà câu lệnh vẫn hoàn thành.

Không bỏ qua warning trong migration dữ liệu quan trọng chỉ vì executeUpdate không ném exception.

## 17. Cấu hình Connector/J thường gặp

Connector/J có nhiều connection property. Chỉ bật thuộc tính khi hiểu mục tiêu và đã kiểm thử trong workload thật.

| Thuộc tính | Mục đích | Lưu ý |
|---|---|---|
| sslMode=VERIFY_IDENTITY | Mã hóa kết nối và xác minh danh tính server | Cần CA/trust store và hostname khớp chứng thư. |
| connectionTimeZone=UTC | Quy định timezone kết nối | Kiểm tra mapping TIMESTAMP/DATETIME và phiên bản driver. |
| connectTimeout | Giới hạn thời gian mở kết nối | Chọn theo network và chính sách fail-fast. |
| socketTimeout | Giới hạn thời gian chờ socket đọc dữ liệu | Quá thấp có thể cắt truy vấn hợp lệ lâu. |
| useServerPrepStmts | Dùng server-side prepared statements khi được hỗ trợ | Kiểm tra tương thích câu lệnh và hiệu năng. |
| cachePrepStmts | Cache prepared statement theo connection | Tăng hiệu quả khi cùng SQL được tái sử dụng. |
| prepStmtCacheSize | Số statement cache tối đa theo connection | Cân bằng memory và tỷ lệ tái sử dụng. |
| prepStmtCacheSqlLimit | Giới hạn độ dài SQL được cache | SQL dài có thể không được cache. |
| rewriteBatchedStatements | Tối ưu một số JDBC batch | Kiểm tra update count, generated keys và semantics. |
| useCursorFetch | Cho phép cursor fetch với server-side prepared statements | Cần cấu hình tương thích, thường đi cùng useServerPrepStmts và fetch size. |

Ví dụ URL cấu hình một số thuộc tính:

~~~text
jdbc:mysql://mysql.example.internal:3306/sales?sslMode=VERIFY_IDENTITY&connectionTimeZone=UTC&connectTimeout=10000&socketTimeout=30000&useServerPrepStmts=true&cachePrepStmts=true
~~~

Các giá trị timeout trong ví dụ là minh họa theo millisecond; chọn theo SLA và thời gian truy vấn thực tế. Tránh đưa mật khẩu hoặc secret vào JDBC URL vì URL có thể xuất hiện trong log hoặc trang quản trị.

### 17.1. Client-side và server-side prepared statements

PreparedStatement là abstraction JDBC. Tùy cấu hình và khả năng câu lệnh, Connector/J có thể mô phỏng prepared statement ở client hoặc dùng prepared statement phía server.

useServerPrepStmts=true yêu cầu sử dụng server-side prepared statements khi driver hỗ trợ. Điều này có thể thay đổi cách truyền tham số, số lần round trip, tài nguyên statement trên server và hành vi của một số câu lệnh. Không mặc định rằng server-side luôn nhanh hơn client-side; đo với câu SQL và workload thực tế.

cachePrepStmts=true cho phép driver cache prepared statement phù hợp trong từng connection. Cache theo connection có nghĩa pool với nhiều connection có thể giữ nhiều bản cache riêng; tính toán tổng bộ nhớ theo số connection và số statement.

## 18. Connection pool và giới hạn đồng thời

Tạo connection mới cho mỗi thao tác có thể tốn chi phí TCP, TLS, xác thực và khởi tạo session. Connection pool giữ một số kết nối được quản lý để tái sử dụng.

Khi cấu hình pool:

- Đặt maximum pool size theo số connection MySQL có thể phục vụ, không theo số thread ứng dụng một cách máy móc.
- Đặt connection timeout để request không chờ vô hạn.
- Kiểm tra idle timeout, max lifetime và giới hạn của proxy/load balancer.
- Theo dõi active, idle, pending và connection acquisition time.
- Đặt transaction ngắn và trả connection sớm.
- Không giữ connection trong lúc thực hiện công việc CPU dài hoặc chờ dịch vụ ngoài.
- Không chia sẻ connection hoặc statement giữa nhiều thread.

Pool quá lớn có thể làm tăng context switching, contention và số session trên MySQL, khiến hệ thống chậm hơn. Hãy chọn kích thước dựa trên throughput, latency và giới hạn server.

Connection pool thường reset một số trạng thái connection khi trả về pool, nhưng ứng dụng vẫn nên kết thúc transaction và đóng tài nguyên đúng cách. Không để một connection có transaction chưa commit hoặc session variable tùy chỉnh bị rò sang request khác.

## 19. Timeout, cancel và truy vấn dài

JDBC cung cấp query timeout trên Statement:

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT order_id FROM sales.orders WHERE status = ?")) {

    ps.setString(1, "PENDING");
    ps.setQueryTimeout(20);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý hàng.
        }
    }
}
~~~

query timeout là giới hạn theo giây ở API JDBC. Hành vi hủy truy vấn và độ chính xác thời gian phụ thuộc driver/server. Không coi nó thay thế timeout ở pool, socket hoặc tầng request.

Có thể gọi cancel từ một luồng khác theo hỗ trợ JDBC/driver, nhưng cần thiết kế cẩn thận để không tạo race với statement đang đóng hoặc tái sử dụng. Khi hủy truy vấn, kiểm tra trạng thái transaction và rollback nếu nghiệp vụ yêu cầu.

## 20. Statement và thread safety

Connection, Statement, PreparedStatement, CallableStatement và ResultSet có trạng thái mutable. Không nên dùng chung một instance giữa các thread đồng thời.

Một mô hình an toàn thường là:

- Một request hoặc đơn vị công việc mượn một Connection từ pool.
- Request tạo statement riêng cho câu SQL.
- ResultSet được đọc và đóng trong cùng phạm vi.
- Transaction được commit/rollback trước khi trả connection.
- Connection được close để trả lại pool.

Nếu cần song song, dùng nhiều connection độc lập và kiểm soát số worker theo giới hạn pool/server. Đừng tạo hàng trăm thread chỉ để gửi truy vấn đồng thời nếu database không thể xử lý mức tải đó.

## 21. Ví dụ tổng hợp: repository truy vấn đơn hàng

Một phương thức repository nên nhận giá trị nghiệp vụ, bind qua PreparedStatement, map kết quả sang đối tượng và đóng tài nguyên trước khi trả về.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public record OrderSummary(
    long orderId,
    String status,
    BigDecimal totalAmount
) {}

public class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderSummary> findByCustomer(long customerId)
            throws SQLException {
        String sql =
            "SELECT order_id, status, total_amount " +
            "FROM sales.orders " +
            "WHERE customer_id = ? " +
            "ORDER BY order_id DESC";

        List<OrderSummary> orders = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    orders.add(new OrderSummary(
                        rs.getLong("order_id"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount")
                    ));
                }
            }
        }

        return orders;
    }
}
~~~

Record yêu cầu Java 16 trở lên. Với Java cũ hơn, thay bằng class DTO thông thường. Repository không trả ResultSet ra ngoài vì ResultSet phụ thuộc statement và connection.

## 22. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| No suitable driver | Thiếu Connector/J hoặc dependency không nằm trong runtime classpath | Kiểm tra dependency và JDBC URL. |
| Access denied | Sai user/password, host không khớp hoặc thiếu quyền | Kiểm tra account host, secret và grants trên MySQL. |
| Communications link failure | Network, TLS, server restart hoặc timeout | Kiểm tra network, chứng thư, server log và timeout. |
| Unknown column hoặc syntax error | SQL không tương thích schema/version hoặc placeholder sai vị trí | Kiểm tra DDL, SQL và thứ tự bind. |
| Parameter index out of range | Index placeholder bắt đầu từ 1 hoặc số tham số không khớp | Đếm dấu hỏi và bind đầy đủ theo thứ tự. |
| Data truncation/conversion | Bind sai kiểu hoặc giá trị vượt precision/length | Dùng setter đúng kiểu, kiểm tra schema và SQLWarning. |
| ResultSet closed | Statement đã thực thi lại hoặc tài nguyên đã đóng | Giữ ResultSet trong phạm vi Statement/Connection. |
| Generated key không có | Không yêu cầu RETURN_GENERATED_KEYS hoặc câu lệnh không tạo key | Dùng overload phù hợp và kiểm tra loại insert. |
| CallableStatement không tìm thấy routine | Sai schema, routine name, quyền EXECUTE hoặc signature | Kiểm tra procedure/function, grants và thứ tự tham số. |
| Deadlock hoặc lock timeout | Transaction cạnh tranh | Rollback toàn transaction, retry có giới hạn nếu nghiệp vụ cho phép. |
| Pool cạn connection | Connection không được đóng hoặc transaction giữ quá lâu | Dùng try-with-resources, theo dõi pool và rút ngắn transaction. |
| Kết quả ngày giờ lệch | Timezone mapping không nhất quán | Chuẩn hóa timezone kết nối và chọn Java type theo ngữ nghĩa cột. |

## 23. Bài tập thực hành

### Bài 1: Tạo kết nối an toàn

Tạo một ứng dụng Java nhỏ dùng Connector/J để kết nối database sales. Đọc JDBC URL và credentials từ cấu hình môi trường; bật TLS verification trong môi trường có CA hợp lệ. In ra phiên bản server và đóng Connection đúng cách.

### Bài 2: So sánh Statement và PreparedStatement

Viết hai truy vấn tìm đơn hàng theo customer ID. Thử truyền đầu vào chứa ký tự đặc biệt và chuỗi có cú pháp SQL. Quan sát cách Statement nối chuỗi làm thay đổi SQL và cách PreparedStatement bind dữ liệu như một giá trị.

### Bài 3: Bind kiểu dữ liệu và NULL

Tạo câu INSERT có VARCHAR, BIGINT, DECIMAL, DATE và một cột nullable. Bind bằng setter tương ứng, thử setNull và đọc lại bằng ResultSet. Xác nhận cách xử lý wasNull khi dùng getter primitive.

### Bài 4: Generated key và batch

Insert một đơn hàng rồi lấy order ID bằng getGeneratedKeys. Sau đó insert nhiều order item bằng PreparedStatement batch. Thử transaction rollback và xác nhận dữ liệu trong InnoDB.

### Bài 5: Gọi procedure

Tạo procedure có tham số IN và OUT, gọi bằng CallableStatement. Mở rộng procedure để trả ResultSet và kiểm tra cách đọc nhiều kết quả bằng getMoreResults.

### Bài 6: Retry transaction

Tạo hai session cập nhật các hàng theo thứ tự khác nhau để có thể phát sinh deadlock trong môi trường thử nghiệm. Bắt SQLException, ghi SQLState/vendor code, rollback toàn bộ transaction và retry với backoff có giới hạn.

## 24. Checklist trước khi đưa JDBC code vào production

- [ ] Connector/J version tương thích với JDK và MySQL Server.
- [ ] JDBC URL dùng hostname/cổng/database đúng môi trường.
- [ ] TLS được cấu hình và xác minh chứng thư khi kết nối production.
- [ ] Credentials được lấy từ secret manager hoặc nguồn cấu hình bảo mật.
- [ ] Connection được quản lý bằng try-with-resources hoặc pool.
- [ ] Không chia sẻ Connection/Statement giữa các thread.
- [ ] PreparedStatement được dùng cho mọi SQL có giá trị đầu vào.
- [ ] Tên cột/table động chỉ được chọn từ whitelist.
- [ ] Setter JDBC khớp kiểu SQL và NULL được xử lý rõ ràng.
- [ ] ResultSet được đọc và đóng trong phạm vi Statement.
- [ ] Generated keys được lấy qua JDBC API phù hợp.
- [ ] Batch có giới hạn kích thước và transaction semantics rõ ràng.
- [ ] CallableStatement khớp signature IN/OUT/INOUT của routine.
- [ ] Transaction có commit/rollback rõ ràng và không giữ connection quá lâu.
- [ ] SQLException được ghi nhận bằng SQLState và vendor code, không log secret.
- [ ] Retry chỉ áp dụng cho lỗi tạm thời và nghiệp vụ có thể lặp lại an toàn.
- [ ] Timeout, pool size và fetch strategy được đo trên workload thực tế.
- [ ] Có kiểm thử integration với đúng phiên bản MySQL và Connector/J triển khai.

Connection quản lý phiên làm việc và transaction; Statement thực thi SQL tĩnh; PreparedStatement bind giá trị an toàn theo vị trí; CallableStatement gọi routine với tham số vào/ra. Dùng try-with-resources, kiểu bind phù hợp và transaction rõ ràng để tránh rò tài nguyên và lỗi dữ liệu. Trong production, kết hợp connection pool, TLS, timeout và giám sát; kiểm thử hành vi của driver theo phiên bản thực tế thay vì dựa vào giả định về tối ưu hoặc streaming.


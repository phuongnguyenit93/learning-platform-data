# JDBC URL, DataSource và thuộc tính kết nối

## Mục tiêu

Sau bài học này, bạn có thể:

- Đọc và xây dựng JDBC URL đúng cú pháp cho MySQL Connector/J.
- Phân biệt kết nối bằng DriverManager, DataSource và connection pool.
- Cấu hình MySQL DataSource trong Java hoặc môi trường quản lý ứng dụng.
- Chọn thuộc tính kết nối phù hợp cho TLS, timeout, timezone, character set và hiệu năng.
- Quản lý thông tin xác thực an toàn, vòng đời Connection và tài nguyên JDBC.
- Chẩn đoán lỗi kết nối thường gặp và kiểm tra cấu hình thực tế của driver.

## 1. MySQL Connector/J trong kiến trúc JDBC

MySQL Connector/J là JDBC driver cho phép ứng dụng Java giao tiếp với MySQL Server thông qua API JDBC. Ứng dụng gọi các interface chuẩn như Connection, PreparedStatement, ResultSet và DataSource; Connector/J chuyển những thao tác đó thành giao thức mà MySQL Server hiểu.

Luồng kết nối cơ bản:

~~~mermaid
flowchart LR
    APP[Ứng dụng Java] --> JDBC[JDBC API]
    JDBC --> CJ[MySQL Connector/J]
    CJ --> TCP[TCP + TLS nếu bật]
    TCP --> MYSQL[MySQL Server]
~~~

Connector/J cung cấp driver cho DriverManager, các lớp DataSource và các cơ chế kết nối nâng cao. Driver không phải database server và cũng không tự tạo connection pool cho ứng dụng khi dùng DriverManager hoặc MysqlDataSource thông thường.

Trong một ứng dụng thực tế, cần phân biệt:

- **JDBC URL:** mô tả máy chủ, cổng, database và các thuộc tính kết nối.
- **DriverManager:** API đơn giản để lấy Connection từ một JDBC URL.
- **DataSource:** abstraction chuẩn để cung cấp kết nối, có thể được cấu hình trong code, JNDI hoặc application server.
- **Connection pool:** quản lý và tái sử dụng các kết nối vật lý để tránh tạo TCP connection mới cho mỗi thao tác.

Một lựa chọn phù hợp giúp cấu hình dễ kiểm soát, bảo mật tốt và giảm lỗi khi triển khai nhiều môi trường.

## 2. Thêm Connector/J vào dự án Java

Với Maven, dependency của MySQL Connector/J có tọa độ:

~~~xml
<dependency>
    <groupId>com.mysql</groupId>
    <artifactId>mysql-connector-j</artifactId>
    <version>${mysql.connector.version}</version>
</dependency>
~~~

Quản lý version qua property hoặc dependency management để các module dùng cùng một bản driver. Chọn phiên bản Connector/J tương thích với Java runtime và MySQL Server đang triển khai; không sao chép một version cũ chỉ vì ví dụ trên Internet đang dùng nó.

Driver class hiện đại là:

~~~text
com.mysql.cj.jdbc.Driver
~~~

Với JDBC 4 trở lên, driver được tự động phát hiện khi JAR có service provider metadata hợp lệ và nằm trên classpath/module path. Ứng dụng thông thường không cần gọi Class.forName để nạp driver. Lệnh Class.forName chỉ còn hữu ích trong một số môi trường cũ hoặc khi tự kiểm tra quá trình nạp driver.

Nếu gặp lỗi No suitable driver, hãy kiểm tra dependency có thực sự nằm trong runtime artifact/container hay không, URL có dùng đúng tiền tố jdbc:mysql: không và driver có tương thích Java runtime không.

## 3. Cấu trúc JDBC URL

Cú pháp kết nối thông dụng:

~~~text
jdbc:mysql://host[:port]/database?property1=value1&property2=value2
~~~

Trong đó:

- jdbc:mysql: xác định loại JDBC driver.
- host là hostname hoặc địa chỉ IP của MySQL Server.
- port là cổng TCP; cổng mặc định của MySQL thường là 3306.
- database là schema mặc định của connection; phần này có thể bỏ nếu ứng dụng chọn database sau khi kết nối.
- Phần sau dấu hỏi là danh sách thuộc tính, ngăn cách bằng dấu &.

Ví dụ tối giản:

~~~text
jdbc:mysql://db.internal.example:3306/sales_app
~~~

Ví dụ có các thuộc tính:

~~~text
jdbc:mysql://db.internal.example:3306/sales_app?sslMode=VERIFY_IDENTITY&connectTimeout=5000&socketTimeout=30000&connectionTimeZone=UTC
~~~

Các giá trị trong ví dụ là cấu hình minh họa; phải thay hostname, database, chứng chỉ và timeout theo môi trường thực tế.

### 3.1. Host, port và database

Một số ví dụ:

| Mục đích | JDBC URL |
|---|---|
| Máy chủ local, cổng mặc định | jdbc:mysql://localhost/sales_app |
| Máy chủ và cổng cụ thể | jdbc:mysql://10.20.0.15:3307/sales_app |
| Không chọn database mặc định | jdbc:mysql://db.internal.example:3306/ |
| Host IPv6 | jdbc:mysql://[2001:db8::15]:3306/sales_app |

Địa chỉ IPv6 cần đặt trong dấu ngoặc vuông để phân biệt dấu hai chấm của địa chỉ với dấu hai chấm phân cách port.

Database trong URL là schema mặc định cho connection. Có thể đổi schema hiện hành bằng Connection.setCatalog hoặc lệnh SQL phù hợp, nhưng nên cấu hình rõ database mà ứng dụng cần truy cập để giảm nguy cơ truy vấn nhầm schema.

### 3.2. Nhiều thuộc tính trong URL

Thuộc tính đầu tiên bắt đầu sau dấu hỏi, thuộc tính tiếp theo nối bằng dấu &:

~~~text
jdbc:mysql://db.internal.example:3306/sales_app?sslMode=VERIFY_IDENTITY&connectTimeout=5000&socketTimeout=30000
~~~

Không nối nhiều dấu hỏi cho nhiều thuộc tính. Các ký tự đặc biệt như &, =, ? trong giá trị có thể bị parser hiểu thành dấu phân cách. Khi giá trị phức tạp, nên cấu hình bằng Properties hoặc DataSource setter thay vì tự ghép chuỗi URL.

Không đặt password trực tiếp trong JDBC URL, file cấu hình được commit hoặc log khởi động. URL thường xuất hiện trong log, exception, dashboard hoặc thông tin chẩn đoán; thông tin xác thực nên được truyền riêng.

## 4. Kết nối bằng DriverManager

DriverManager phù hợp với chương trình nhỏ, công cụ command-line, bài thực hành hoặc ứng dụng ít kết nối đồng thời.

Ví dụ:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.util.Properties;

public class JdbcExample {
    public static void main(String[] args) throws Exception {
        String url =
            "jdbc:mysql://db.internal.example:3306/sales_app"
            + "?sslMode=VERIFY_IDENTITY"
            + "&connectTimeout=5000"
            + "&socketTimeout=30000"
            + "&connectionTimeZone=UTC";

        Properties properties = new Properties();
        properties.setProperty("user", System.getenv("DB_USER"));
        properties.setProperty("password", System.getenv("DB_PASSWORD"));

        String sql =
            "SELECT order_id, total_amount "
            + "FROM orders WHERE customer_id = ?";

        try (Connection connection =
                 DriverManager.getConnection(url, properties);
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, 501L);

            try (ResultSet resultSet = statement.executeQuery()) {
                while (resultSet.next()) {
                    long orderId = resultSet.getLong("order_id");
                    java.math.BigDecimal amount =
                        resultSet.getBigDecimal("total_amount");

                    System.out.println(orderId + " " + amount);
                }
            }
        }
    }
}
~~~

Ví dụ dùng biến môi trường để minh họa cách tách credentials khỏi source code. Trong môi trường production, có thể lấy bí mật từ secret manager hoặc cơ chế cấp phát credential của nền tảng. Phải kiểm tra biến môi trường có tồn tại và không rỗng trước khi tạo kết nối.

Try-with-resources tự đóng ResultSet, PreparedStatement và Connection theo thứ tự ngược khi thoát khối. Điều này giúp trả lại tài nguyên JDBC kể cả khi câu lệnh phát sinh exception.

DriverManager tạo connection mới khi gọi getConnection. Không gọi nó cho mọi truy vấn trong một ứng dụng web có tải cao nếu chưa có chiến lược tái sử dụng connection.

## 5. DataSource là gì?

DataSource là interface trong package javax.sql, cung cấp một cách chuẩn để lấy Connection. So với DriverManager, DataSource hỗ trợ cấu hình tách khỏi code và có thể được quản lý bởi application server, JNDI hoặc thư viện connection pool.

DataSource không nhất thiết là pool. Có ba khái niệm thường gặp:

| Loại | Vai trò |
|---|---|
| DataSource cơ bản | Cung cấp Connection theo cấu hình; có thể mở connection vật lý mới cho mỗi lần gọi |
| ConnectionPoolDataSource | API mức thấp để pool manager quản lý PooledConnection |
| Pooled DataSource | DataSource do thư viện pool cung cấp; getConnection lấy connection logic từ pool và close sẽ trả connection về pool |

MySQL Connector/J có lớp MysqlDataSource trong package com.mysql.cj.jdbc. Lớp này là DataSource cơ bản. Dùng MysqlDataSource trực tiếp không đồng nghĩa đã có pooling.

## 6. Cấu hình MysqlDataSource trong Java

Ví dụ cấu hình DataSource bằng code:

~~~java
import com.mysql.cj.jdbc.MysqlDataSource;
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class DataSourceExample {
    public static void main(String[] args) throws Exception {
        MysqlDataSource mysql = new MysqlDataSource();

        mysql.setURL(
            "jdbc:mysql://db.internal.example:3306/sales_app"
            + "?sslMode=VERIFY_IDENTITY"
            + "&connectTimeout=5000"
            + "&socketTimeout=30000"
            + "&connectionTimeZone=UTC"
        );
        mysql.setUser(System.getenv("DB_USER"));
        mysql.setPassword(System.getenv("DB_PASSWORD"));

        DataSource dataSource = mysql;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(
                 "SELECT COUNT(*) FROM orders");
             ResultSet resultSet = statement.executeQuery()) {

            if (resultSet.next()) {
                System.out.println("Order count: " + resultSet.getLong(1));
            }
        }
    }
}
~~~

Có thể cấu hình DataSource bằng các setter riêng như server name, port, database, user và password. Dùng setURL là cách ngắn gọn khi đã có một URL đầy đủ. Tránh cấu hình cùng một thuộc tính ở nhiều nơi mà không xác định rõ nguồn cấu hình chính.

Trong ứng dụng lớn, nên tạo DataSource một lần trong quá trình khởi động ứng dụng và tái sử dụng nó. Không tạo mới MysqlDataSource cho từng request. Nếu cần pooling, đặt DataSource này phía sau một pool manager hoặc dùng DataSource do thư viện pool cung cấp.

## 7. DataSource trong application server và JNDI

Trong Jakarta EE hoặc một application server, quản trị viên có thể tạo DataSource ở cấp máy chủ rồi đăng ký dưới một tên JNDI. Ứng dụng tra cứu DataSource theo tên và lấy Connection.

Ví dụ ý tưởng:

~~~java
import javax.naming.InitialContext;
import javax.sql.DataSource;
import java.sql.Connection;

InitialContext context = new InitialContext();
DataSource dataSource =
    (DataSource) context.lookup("java:comp/env/jdbc/SalesDB");

try (Connection connection = dataSource.getConnection()) {
    // Thực hiện thao tác JDBC trong phạm vi công việc.
}
~~~

Tên JNDI và cách khai báo resource phụ thuộc application server. DataSource do server quản lý có thể tích hợp connection pool, transaction manager, credential store, monitoring và giới hạn kết nối. Khi đó, ứng dụng không nên tự tạo một pool khác cho cùng database nếu không có lý do kiến trúc rõ ràng.

Một lợi ích của JNDI là thay đổi hostname, port, credential hoặc pool size có thể được thực hiện qua cấu hình triển khai mà không sửa source code. Tuy nhiên, cấu hình server và cấu hình ứng dụng phải thống nhất tên resource, transaction policy và quyền truy cập.

## 8. Connection pool và HikariCP

Tạo kết nối TCP/TLS, xác thực và khởi tạo session MySQL có chi phí. Với ứng dụng web, tạo một connection mới cho mỗi request có thể làm tăng latency và tạo nhiều connection đồng thời. Connection pool duy trì một tập kết nối vật lý, cho ứng dụng mượn connection trong thời gian ngắn rồi trả lại.

Luồng sử dụng:

1. Ứng dụng gọi DataSource.getConnection.
2. Pool cấp một connection logic gắn với kết nối vật lý đang rảnh.
3. Ứng dụng thực hiện truy vấn hoặc transaction.
4. Ứng dụng gọi close.
5. Pool reset trạng thái cần thiết và đưa connection về danh sách sẵn sàng.

Trong pool, close thường trả connection về pool, không đóng TCP connection vật lý ngay lập tức. Vì vậy, luôn đóng Connection bằng try-with-resources để connection không bị giữ lại ngoài ý muốn.

### 8.1. Ví dụ HikariCP

HikariCP là connection pool phổ biến. Có thể cấu hình JDBC URL và credential như sau:

Nếu dùng Maven, thêm dependency HikariCP riêng bên cạnh Connector/J:

~~~xml
<dependency>
    <groupId>com.zaxxer</groupId>
    <artifactId>HikariCP</artifactId>
    <version>${hikari.version}</version>
</dependency>
~~~

~~~java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class PooledJdbcExample {
    public static void main(String[] args) throws Exception {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(
            "jdbc:mysql://db.internal.example:3306/sales_app"
            + "?sslMode=VERIFY_IDENTITY"
            + "&connectTimeout=5000"
            + "&socketTimeout=30000"
            + "&connectionTimeZone=UTC"
        );
        config.setUsername(System.getenv("DB_USER"));
        config.setPassword(System.getenv("DB_PASSWORD"));
        config.setPoolName("sales-app-pool");
        config.setMaximumPoolSize(12);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(3000);
        config.setValidationTimeout(1000);
        config.setMaxLifetime(1500000);

        try (HikariDataSource dataSource =
                 new HikariDataSource(config)) {
            try (Connection connection = dataSource.getConnection();
                 PreparedStatement statement =
                     connection.prepareStatement("SELECT 1");
                 ResultSet resultSet = statement.executeQuery()) {
                resultSet.next();
                System.out.println(resultSet.getInt(1));
            }
        }
    }
}
~~~

Ví dụ dùng các giá trị cấu hình minh họa. Pool được đóng khi ứng dụng kết thúc; trong ứng dụng server, vòng đời DataSource thường do dependency injection container hoặc lifecycle manager điều khiển.

Chọn maxLifetime nhỏ hơn giới hạn tuổi kết nối do database, proxy hoặc network đặt ra. Giá trị trong ví dụ là 25 phút và chỉ phù hợp nếu các giới hạn hạ tầng cho phép.

### 8.2. Phân biệt timeout của pool và timeout của driver

Hai thuộc tính có tên gần giống nhau nhưng xử lý các giai đoạn khác nhau:

| Thuộc tính | Thành phần | Ý nghĩa |
|---|---|---|
| connectTimeout | Connector/J | Thời gian chờ thiết lập kết nối mạng đến MySQL |
| socketTimeout | Connector/J | Thời gian chờ thao tác socket trước khi báo timeout |
| connectionTimeout | HikariCP | Thời gian tối đa chờ lấy connection từ pool |
| validationTimeout | HikariCP | Thời gian tối đa cho kiểm tra connection |
| maxLifetime | HikariCP | Tuổi tối đa của connection trong pool trước khi được loại bỏ theo vòng đời pool |

connectionTimeout của HikariCP không thay thế connectTimeout của Connector/J. Nếu pool đã đầy và không có connection rảnh, ứng dụng có thể chờ pool dù MySQL vẫn khỏe. Ngược lại, nếu pool đang tạo connection mới nhưng TCP connect bị treo, connectTimeout quyết định thời gian chờ kết nối mạng.

### 8.3. Chọn kích thước pool

Không đặt maximumPoolSize thật lớn chỉ để tránh chờ. Mỗi connection tiêu thụ tài nguyên trên MySQL: bộ nhớ session, thread, socket và khả năng xử lý. Tổng số connection phải tính trên tất cả instance ứng dụng, worker, cron job và công cụ quản trị.

Ví dụ, 10 instance ứng dụng với pool tối đa 20 có thể mở đến 200 connection, chưa tính các dịch vụ khác. Hãy so sánh tổng này với max_connections, workload thực tế và khả năng xử lý đồng thời của database.

Một cách tiếp cận:

- Đo thời gian truy vấn và thời gian connection được mượn.
- Ước tính mức concurrency cần thiết theo throughput và thời gian giữ connection.
- Bắt đầu với pool nhỏ, tăng dần khi có số liệu chứng minh cần thiết.
- Đặt giới hạn tổng connection trên toàn hệ thống, không chỉ từng instance.
- Theo dõi active, idle, pending borrower, timeout và connection creation rate.
- Giữ transaction ngắn và không thực hiện HTTP call hoặc chờ người dùng trong khi đang giữ connection.

## 9. Các thuộc tính kết nối quan trọng

Connector/J hỗ trợ nhiều connection property. Có thể đặt trong JDBC URL, Properties hoặc các setter tương ứng của DataSource. Chỉ bật thuộc tính khi hiểu rõ tác động và đã kiểm tra với phiên bản Connector/J đang dùng.

### 9.1. Nhóm mạng và timeout

| Thuộc tính | Ý nghĩa | Gợi ý |
|---|---|---|
| connectTimeout | Timeout khi thiết lập kết nối socket | Đặt giới hạn phù hợp để ứng dụng không chờ vô hạn khi host không phản hồi |
| socketTimeout | Timeout thao tác đọc socket | Chọn theo thời gian truy vấn hợp lệ; quá ngắn có thể ngắt truy vấn chậm hợp lệ |
| tcpKeepAlive | Bật TCP keepalive ở socket | Có thể hỗ trợ phát hiện kết nối chết theo chính sách hệ điều hành |
| localSocketAddress | Địa chỉ local dùng khi bind socket | Chỉ cấu hình khi hạ tầng mạng có yêu cầu cụ thể |

Giá trị timeout tính bằng millisecond trong Connector/J. Giá trị 0 thường có nghĩa không đặt timeout ở cấp thuộc tính đó. Không dùng timeout thấp như cách xử lý query chậm; hãy tối ưu SQL, index và server load.

### 9.2. Nhóm TLS và bảo mật

Thuộc tính quan trọng nhất để chọn chế độ TLS là sslMode. Các giá trị thường gặp:

| Giá trị | Hành vi |
|---|---|
| DISABLED | Không dùng TLS |
| PREFERRED | Ưu tiên TLS nhưng có thể fallback sang kết nối không mã hóa nếu server không hỗ trợ |
| REQUIRED | Yêu cầu TLS, nhưng không xác minh đầy đủ CA và hostname |
| VERIFY_CA | Yêu cầu TLS và xác minh certificate chain theo CA tin cậy |
| VERIFY_IDENTITY | Xác minh CA và hostname của server khớp chứng chỉ |

Với kết nối qua mạng không tin cậy, lựa chọn chặt chẽ thường là VERIFY_IDENTITY, kèm trust store/CA được quản lý đúng cách. Chứng chỉ server phải có Subject Alternative Name phù hợp hostname trong JDBC URL. Nếu kết nối bằng IP, chứng chỉ cần chứa IP tương ứng hoặc ứng dụng nên dùng hostname hợp lệ.

Ví dụ:

~~~text
jdbc:mysql://mysql.prod.example:3306/sales_app?sslMode=VERIFY_IDENTITY&connectTimeout=5000
~~~

useSSL là thuộc tính kiểu cũ; với cấu hình mới nên dùng sslMode để thể hiện rõ mức xác minh. Không tắt xác minh chứng chỉ chỉ để vượt qua lỗi TLS trong production.

Một số hệ thống xác thực MySQL có thể cần trao đổi public key khi không dùng TLS. Connector/J có thuộc tính allowPublicKeyRetrieval. Thuộc tính này thường bị tắt mặc định. Không bật nó một cách tùy tiện trên mạng không tin cậy; ưu tiên cấu hình TLS với xác minh certificate đúng cách.

Không ghi truststore password, client keystore password hoặc private key vào JDBC URL hoặc repository. Đưa chúng qua secret manager hoặc cấu hình bảo mật của runtime.

### 9.3. Nhóm timezone và dữ liệu thời gian

Ứng dụng, JDBC driver và MySQL session có thể dùng timezone khác nhau. Điều này đặc biệt quan trọng khi làm việc với TIMESTAMP, DATETIME, java.time và dữ liệu được ghi từ nhiều vùng địa lý.

Connector/J hiện đại cung cấp thuộc tính connectionTimeZone. Ví dụ:

~~~text
jdbc:mysql://db.internal.example:3306/sales_app?connectionTimeZone=UTC
~~~

connectionTimeZone điều khiển timezone mà driver dùng trong chuyển đổi giá trị thời gian; thuộc tính này có trên các bản Connector/J hiện đại (từ 8.0.23). Nếu cần đồng bộ timezone của MySQL session, xem xét thêm forceConnectionTimeZoneToSession theo semantics và phiên bản Connector/J. Hai khái niệm này có liên quan nhưng không đồng nghĩa.

Thuộc tính serverTimezone xuất hiện trong cấu hình cũ; với cấu hình mới nên ưu tiên tên connectionTimeZone theo tài liệu Connector/J của phiên bản triển khai.

Không giả định mọi cột thời gian đều được chuyển đổi giống nhau:

- MySQL TIMESTAMP lưu thời điểm theo UTC và chuyển đổi giữa session timezone khi ghi/đọc.
- MySQL DATETIME lưu thành phần ngày giờ mà không tự gắn timezone.
- Java Instant biểu diễn một thời điểm tuyệt đối.
- LocalDateTime không mang timezone.

Hãy định nghĩa quy tắc nghiệp vụ cho từng loại dữ liệu, dùng kiểu Java phù hợp và kiểm tra trường hợp qua ranh giới DST nếu có timezone địa phương.

### 9.4. Nhóm character set

Với ứng dụng đa ngôn ngữ, cần bảo đảm Java, Connector/J, MySQL database, table và connection thống nhất cách mã hóa. MySQL hiện đại thường dùng utf8mb4 để hỗ trợ Unicode đầy đủ, gồm cả emoji và ký tự ngoài BMP.

Có thể kiểm tra session:

~~~sql
SHOW SESSION VARIABLES LIKE 'character_set_%';
SHOW SESSION VARIABLES LIKE 'collation_%';
~~~

Nếu cần đặt rõ encoding, tham khảo property characterEncoding và cách Connector/J ánh xạ charset Java sang charset MySQL ở phiên bản đang dùng. Không nhầm charset của connection với collation của cột: charset quyết định cách mã hóa ký tự, collation quyết định quy tắc so sánh và sắp xếp.

Không dùng charset cũ chỉ để làm mất lỗi ký tự. Nếu dữ liệu bị mojibake, cần tìm nơi mã hóa sai trong toàn bộ đường đi thay vì đổi charset ngẫu nhiên trên connection.

### 9.5. Nhóm câu lệnh và hiệu năng

Một số thuộc tính có thể ảnh hưởng cách Connector/J gửi câu lệnh:

| Thuộc tính | Tác dụng |
|---|---|
| useServerPrepStmts | Cho phép dùng prepared statement phía server khi phù hợp |
| cachePrepStmts | Bật cache prepared statement ở phía driver |
| prepStmtCacheSize | Kích thước cache prepared statement |
| prepStmtCacheSqlLimit | Giới hạn độ dài SQL được cache |
| rewriteBatchedStatements | Cho phép driver viết lại một số batch statement để giảm round trip |
| allowMultiQueries | Cho phép nhiều câu SQL trong một lần gửi; chỉ bật khi ứng dụng thật sự cần |

Các thuộc tính này không phải lúc nào cũng cải thiện hiệu năng. Hiệu quả phụ thuộc kiểu workload, số lượng câu SQL lặp lại, kích thước batch, server version và cách ứng dụng dùng PreparedStatement. Hãy đo bằng benchmark gần với workload thực tế.

Không bật allowMultiQueries để tiện ghép nhiều SQL string. Dùng PreparedStatement với parameter binding để giảm SQL injection và kiểm soát dữ liệu đầu vào.

### 9.6. Tránh thuộc tính tự reconnect như giải pháp chung

Không dựa vào một thuộc tính reconnect để làm connection đang lỗi tự phục hồi như chưa có gì xảy ra. Khi TCP connection bị mất, transaction có thể ở trạng thái không rõ đã commit hay chưa. Tự gửi lại câu lệnh có thể tạo giao dịch trùng hoặc làm sai nghiệp vụ.

Hãy để pool loại bỏ connection hỏng, lấy connection mới và để ứng dụng xử lý lỗi ở ranh giới transaction. Chỉ retry thao tác khi có thể xác định tính idempotent hoặc có khóa idempotency/transaction identifier để tránh thực hiện hai lần.

## 10. Cấu hình bằng Properties thay vì URL dài

Khi có nhiều thuộc tính, Properties giúp tách cấu hình khỏi chuỗi URL:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.Properties;

String url = "jdbc:mysql://db.internal.example:3306/sales_app";

Properties properties = new Properties();
properties.setProperty("user", System.getenv("DB_USER"));
properties.setProperty("password", System.getenv("DB_PASSWORD"));
properties.setProperty("sslMode", "VERIFY_IDENTITY");
properties.setProperty("connectTimeout", "5000");
properties.setProperty("socketTimeout", "30000");
properties.setProperty("connectionTimeZone", "UTC");

try (Connection connection =
         DriverManager.getConnection(url, properties)) {
    // Dùng connection trong phạm vi công việc.
}
~~~

Cách này giúp credentials không nằm chung chuỗi URL, đồng thời dễ tạo cấu hình theo môi trường. Properties vẫn phải được bảo vệ; không in toàn bộ object ra log vì có thể chứa password hoặc thông tin nhạy cảm.

## 11. Nhiều máy chủ và URL nâng cao

Connector/J hỗ trợ một số kiểu URL nhiều host. Cần chọn đúng loại theo mục tiêu kết nối và hiểu hành vi failover hoặc routing của driver.

### 11.1. Danh sách host

Ví dụ URL có nhiều host:

~~~text
jdbc:mysql://mysql-a.internal:3306,mysql-b.internal:3306/sales_app
~~~

Danh sách host cho phép Connector/J thử host khác theo cơ chế failover của kiểu URL và cấu hình liên quan. Điều này không tự bảo đảm mọi topology có thể failover an toàn. Các host phải phục vụ cùng một database logic, quyền và schema tương thích; ứng dụng vẫn cần xử lý connection bị ngắt và transaction chưa rõ kết quả.

### 11.2. Load balancing URL

Connector/J có dạng URL load balancing:

~~~text
jdbc:mysql:loadbalance://mysql-a.internal:3306,mysql-b.internal:3306/sales_app
~~~

Kiểu này phân phối connection giữa các host theo cơ chế load balance của driver. Nó không tự hiểu mọi quy tắc đọc/ghi của ứng dụng và không thay thế kiến trúc MySQL InnoDB Cluster, MySQL Router hoặc bộ điều phối endpoint được tổ chức sử dụng.

### 11.3. Replication URL

Connector/J cũng có dạng URL replication:

~~~text
jdbc:mysql:replication://mysql-source.internal:3306,mysql-replica.internal:3306/sales_app
~~~

Kiểu URL này biểu diễn source và replica cho replication-aware connection. Việc chuyển connection giữa source và replica phụ thuộc API, cấu hình và cách ứng dụng điều khiển read-only mode. Không mặc định mọi câu SELECT tự động đi đến replica trong mọi tình huống.

Với replication-aware connection, ứng dụng thường dùng Connection.setReadOnly(true) cho công việc đọc và chuyển lại setReadOnly(false) cho công việc ghi theo hướng dẫn của driver. Hãy đặt chế độ trước khi bắt đầu transaction; không chuyển hướng giữa một transaction đang mở.

Với production HA, ưu tiên endpoint do hạ tầng MySQL quản lý, chẳng hạn MySQL Router cho InnoDB Cluster, nếu đó là kiến trúc của hệ thống. Router định tuyến theo trạng thái topology; Connector/J vẫn chịu trách nhiệm tạo JDBC connection và ứng dụng vẫn phải xử lý reconnect/retry.

## 12. Quản lý Connection và transaction

Connection là một session có trạng thái. Nó giữ transaction, autocommit, isolation level, schema hiện hành, session variables và các thiết lập khác. Khi dùng pool, connection được tái sử dụng nên ứng dụng phải kết thúc transaction và đóng tài nguyên đúng cách.

Ví dụ transaction:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement debit = connection.prepareStatement(
                 "UPDATE accounts SET balance = balance - ? "
                 + "WHERE account_id = ?");
             PreparedStatement credit = connection.prepareStatement(
                 "UPDATE accounts SET balance = balance + ? "
                 + "WHERE account_id = ?")) {

            debit.setBigDecimal(1, amount);
            debit.setLong(2, fromAccountId);
            int debitRows = debit.executeUpdate();

            credit.setBigDecimal(1, amount);
            credit.setLong(2, toAccountId);
            int creditRows = credit.executeUpdate();

            if (debitRows != 1 || creditRows != 1) {
                throw new IllegalStateException(
                    "Account was not found or not updated");
            }
        }

        connection.commit();
    } catch (Exception exception) {
        try {
            connection.rollback();
        } catch (Exception rollbackException) {
            exception.addSuppressed(rollbackException);
        }
        throw exception;
    }
}
~~~

Ví dụ minh họa ranh giới transaction. Trong ứng dụng thật, cần kiểm tra số dư không âm, khóa hàng, xử lý deadlock và quy tắc idempotency. Không giữ Connection lâu hơn thời gian cần thiết.

Nếu dùng pool, không tự giữ reference Connection trong field static để chia sẻ giữa các thread. JDBC Connection không được thiết kế để nhiều thread cùng thao tác một cách tùy tiện. Mỗi đơn vị công việc nên mượn connection riêng và trả lại khi hoàn tất.

## 13. Kiểm tra cấu hình và metadata driver

Khi khởi động hoặc trong công cụ chẩn đoán, có thể lấy thông tin từ JDBC:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;

try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData metadata = connection.getMetaData();

    System.out.println("Driver: " + metadata.getDriverName());
    System.out.println("Driver version: "
        + metadata.getDriverVersion());
    System.out.println("Database: " + metadata.getDatabaseProductName());
    System.out.println("Server version: "
        + metadata.getDatabaseProductVersion());
    System.out.println("URL: " + metadata.getURL());
}
~~~

Không ghi metadata URL nếu URL có thể chứa thông tin nhạy cảm trong cấu hình. Với driver hiện đại, có thể dùng metadata để xác nhận runtime đang nạp đúng Connector/J và kết nối đến đúng phiên bản server.

Kiểm tra session MySQL:

~~~sql
SELECT
  @@hostname AS server_host,
  @@port AS server_port,
  @@version AS server_version,
  @@session.time_zone AS session_time_zone,
  @@character_set_connection AS connection_charset,
  @@collation_connection AS connection_collation;
~~~

Đối chiếu kết quả với cấu hình dự kiến. Nếu URL đặt timezone UTC nhưng session time_zone không phải UTC, hãy xem lại connectionTimeZone, forceConnectionTimeZoneToSession, session initialization và cấu hình server.

## 14. Chẩn đoán lỗi kết nối thường gặp

| Lỗi | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| No suitable driver | Thiếu Connector/J trong runtime, URL sai tiền tố hoặc classloader không thấy driver | Kiểm tra dependency runtime và URL jdbc:mysql: |
| Communications link failure | DNS, firewall, route, server down, timeout hoặc kết nối bị đóng giữa chừng | Kiểm tra hostname, TCP port, log server, network và timeout |
| Access denied for user | Sai password, user@host không khớp hoặc thiếu quyền | Kiểm tra account, host matching, secret và GRANT |
| Unknown database | Schema trong URL chưa tồn tại hoặc sai tên | Kiểm tra database và quyền truy cập |
| TLS handshake/certificate error | CA không tin cậy, certificate hết hạn hoặc hostname không khớp | Kiểm tra trust store, SAN, chain và sslMode |
| Public Key Retrieval is not allowed | Authentication cần public key retrieval trong cấu hình hiện tại | Ưu tiên TLS; chỉ xem xét retrieval trong môi trường tin cậy và theo chính sách bảo mật |
| Timezone không nhận diện | Driver/server không thống nhất timezone hoặc cấu hình cũ | Kiểm tra connectionTimeZone, session time_zone và version |
| Too many connections | Tổng connection từ ứng dụng vượt khả năng server | Tính tổng pool size, kiểm tra connection leak và max_connections |
| Pool connection timeout | Pool hết connection rảnh hoặc connection bị giữ quá lâu | Kiểm tra active/idle/pending, thời gian mượn và transaction |
| Socket timeout khi query | Query chậm, mạng chập chờn hoặc timeout quá thấp | Xem slow query, execution plan, server load và socketTimeout |

### 14.1. Phân biệt lỗi mạng và lỗi SQL

Một lỗi kết nối có thể xảy ra trước khi MySQL nhận câu SQL, trong lúc đang thực thi hoặc khi gửi kết quả về client. Nếu connection bị ngắt trong lúc COMMIT, ứng dụng có thể không biết transaction đã commit thành công hay chưa.

Không retry mù quáng một thao tác ghi sau lỗi Communications link failure. Trước hết cần xác định tính chất thao tác, dùng khóa idempotency hoặc truy vấn trạng thái nghiệp vụ để xác minh kết quả. Với thao tác đọc thuần túy, retry thường dễ hơn nhưng vẫn cần giới hạn số lần và backoff.

### 14.2. Log exception hữu ích

Khi xử lý SQLException, ghi nhận các trường:

- getSQLState() — mã phân loại lỗi SQL theo chuẩn.
- getErrorCode() — mã lỗi vendor của MySQL.
- getMessage() — thông điệp chẩn đoán, sau khi loại bỏ thông tin bí mật.
- getNextException() — chuỗi lỗi JDBC tiếp theo nếu có.

Không log password, token, full URL chứa secret hoặc dữ liệu cá nhân trong câu SQL. Nếu bật JDBC logging để điều tra, giới hạn thời gian và quyền truy cập log.

## 15. Các lỗi cấu hình cần tránh

- Nhúng username/password trong URL hoặc source code.
- Dùng sslMode=DISABLED trên mạng production không tin cậy.
- Dùng PREFERRED khi chính sách yêu cầu bắt buộc TLS và xác minh danh tính server.
- Bật allowPublicKeyRetrieval để bỏ qua vấn đề chứng chỉ mà không đánh giá rủi ro.
- Tạo DataSource hoặc connection pool mới cho mỗi request.
- Đặt pool size rất lớn trên từng instance mà không tính tổng connection toàn hệ thống.
- Giữ Connection trong cache, field static hoặc thread-local vô thời hạn.
- Không đóng ResultSet, Statement hoặc Connection.
- Dùng timeout quá thấp khiến truy vấn hợp lệ bị ngắt.
- Bật multi-query hoặc thuộc tính hiệu năng mà không có nhu cầu và kiểm thử.
- Dùng một URL multi-host rồi giả định nó thay thế được router, quorum hoặc cơ chế failover của topology.
- Retry transaction không idempotent sau khi connection mất mà chưa xác minh trạng thái commit.

## 16. Checklist cấu hình trước production

### Driver và URL

- [ ] Connector/J được khai báo trong runtime artifact và tương thích Java.
- [ ] JDBC URL dùng đúng hostname, port, database và kiểu URL.
- [ ] Thuộc tính được đặt rõ ràng, không trùng lặp hoặc mâu thuẫn.
- [ ] Giá trị đặc biệt trong property không làm hỏng parser URL.

### Bảo mật

- [ ] Credentials lấy từ secret manager hoặc cơ chế cấp phát được duyệt.
- [ ] TLS được bật theo chính sách; xác minh CA và hostname khi cần.
- [ ] Trust store/client certificate được quản lý và có kế hoạch rotate.
- [ ] Không ghi secret vào log hoặc exception report.

### Kết nối và pool

- [ ] Chọn DriverManager, DataSource hoặc pooled DataSource theo workload.
- [ ] DataSource được tạo một lần và có lifecycle rõ ràng.
- [ ] Pool size được tính trên tổng số instance và worker.
- [ ] connectTimeout, socketTimeout và pool connectionTimeout phù hợp.
- [ ] Connection được đóng sau mỗi đơn vị công việc.
- [ ] Transaction ngắn và xử lý lỗi commit không rõ kết quả.

### Dữ liệu và vận hành

- [ ] Timezone và character set được kiểm tra ở session.
- [ ] PreparedStatement được dùng cho tham số đầu vào.
- [ ] Cấu hình batch/prepared statement được benchmark nếu bật.
- [ ] Metrics pool, timeout, connection creation và SQL latency được theo dõi.
- [ ] Có runbook xử lý DNS, TLS, authentication, connection leak và database failover.

## 17. Bài tập thực hành

Bạn được giao kết nối một ứng dụng Java bán hàng đến MySQL production và staging. Hai môi trường dùng hostname, credential, certificate và database khác nhau. Ứng dụng chạy 6 instance API, 3 worker và cần pool connection.

Hãy thực hiện trong môi trường lab:

1. Thêm dependency MySQL Connector/J tương thích với Java runtime.
2. Viết JDBC URL riêng cho staging và production, dùng TLS với xác minh hostname.
3. Tạo MysqlDataSource, truyền user/password riêng qua secret manager hoặc biến môi trường.
4. Thực hiện một SELECT bằng PreparedStatement và đóng toàn bộ tài nguyên bằng try-with-resources.
5. Tích hợp HikariCP, đặt pool size nhỏ ban đầu và cấu hình timeout riêng cho pool và driver.
6. Chạy thử nhiều request đồng thời, quan sát active/idle/pending connection và MySQL Threads_connected.
7. Tắt MySQL hoặc chặn TCP trong lab, quan sát connect timeout và pool timeout.
8. Thử certificate không khớp hostname và xác nhận VERIFY_IDENTITY từ chối kết nối.
9. Kiểm tra timezone, charset và database hiện hành bằng session variables.
10. Ghi lại driver version, server version, cấu hình timeout và số connection tối đa dự kiến khi cả 9 process chạy đồng thời.

**Câu hỏi tự kiểm tra:**

1. JDBC URL khác DataSource ở vai trò nào?
2. Vì sao MysqlDataSource không đồng nghĩa connection pool?
3. connectTimeout khác connectionTimeout của HikariCP như thế nào?
4. Vì sao sslMode=VERIFY_IDENTITY mạnh hơn chỉ yêu cầu TLS?
5. Tại sao không nên đặt password trong JDBC URL?
6. connectionTimeZone có đồng nghĩa luôn thay đổi session time_zone không?
7. Vì sao tổng pool size của mọi instance quan trọng hơn pool size của một instance riêng lẻ?
8. Khi connection mất trong lúc COMMIT, vì sao không thể retry mọi câu lệnh một cách tự động?
9. Khi nào nên dùng JNDI DataSource do application server quản lý?
10. Khi nào URL nhiều host cần được thay bằng endpoint do MySQL Router quản lý?

## Kết luận

JDBC URL mô tả đích kết nối và các thuộc tính của Connector/J; DataSource cung cấp abstraction chuẩn để ứng dụng lấy Connection; connection pool quản lý việc tái sử dụng kết nối vật lý. Một cấu hình MySQL an toàn cần tách credentials, bật TLS phù hợp, đặt timeout đúng tầng, thống nhất timezone/charset và giới hạn pool theo tổng tải. Hãy kiểm tra cấu hình thực tế từ JDBC metadata và MySQL session, đồng thời xử lý lỗi kết nối ở ranh giới transaction để tránh thực hiện giao dịch ghi nhiều lần.

## Tài liệu tham khảo

- [MySQL Connector/J Developer Guide — Driver/Datasource Class Names](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-driver-name.html)
- [MySQL Connector/J Developer Guide — Connecting to MySQL Using JDBC](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-connect-drivermanager.html)
- [MySQL Connector/J Developer Guide — Configuration Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-configuration-properties.html)
- [MySQL Connector/J Developer Guide — Using JDBC Data Sources](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-j2ee-concepts-datasource.html)
- [MySQL Connector/J Developer Guide — Connection Pooling](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-j2ee-concepts-connection-pooling.html)
- [MySQL Connector/J Developer Guide — TLS/SSL Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-security.html)

# Prepared statement phía client/server và useServerPrepStmts

Bài học này thuộc module **DATABASE_MYSQL**. Khi ứng dụng Java truy cập MySQL qua MySQL Connector/J, JDBC PreparedStatement giúp tách câu SQL khỏi giá trị đầu vào, tái sử dụng câu lệnh và truyền tham số đúng kiểu dữ liệu. Tuy nhiên, việc ứng dụng gọi Connection.prepareStatement() không tự động có nghĩa MySQL Server đang giữ một prepared statement. Connector/J có thể xử lý tham số ở phía client hoặc dùng prepared statement phía server, tùy cấu hình và khả năng hỗ trợ của câu lệnh.

Thuộc tính useServerPrepStmts điều khiển lựa chọn này. Hiểu rõ hai chế độ giúp thiết kế truy vấn an toàn, đánh giá hiệu năng, quản lý tài nguyên theo connection pool và chẩn đoán những khác biệt khi chạy trên production.

## 1. JDBC PreparedStatement là gì?

PreparedStatement là API JDBC dùng để thực thi một câu SQL có các dấu tham số ?. Ứng dụng tạo câu lệnh một lần, gán giá trị cho từng vị trí tham số rồi thực thi:

~~~java
String sql = "SELECT order_id, total_amount "
           + "FROM orders "
           + "WHERE customer_id = ? AND created_at >= ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    ps.setTimestamp(2, Timestamp.valueOf(startTime));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            BigDecimal total = rs.getBigDecimal("total_amount");
            // Xử lý kết quả
        }
    }
}
~~~

Một số điểm cần nhớ:

- Vị trí tham số bắt đầu từ **1**, không phải 0.
- Mỗi dấu ? là một tham số riêng. Nếu cùng một giá trị xuất hiện hai lần, cần gán cho cả hai vị trí.
- Dùng setter phù hợp với kiểu dữ liệu như setLong, setString, setBigDecimal, setDate, setTimestamp hoặc setBytes.
- JDBC PreparedStatement không cung cấp cú pháp tham số có tên theo chuẩn. Các tham số được gán theo thứ tự vị trí.
- Đóng PreparedStatement và ResultSet sau khi sử dụng; try-with-resources là cách thuận tiện để giải phóng tài nguyên ngay cả khi có exception.

Prepared statement có thể được thực thi nhiều lần với các giá trị khác nhau:

~~~java
String sql = "SELECT order_id FROM orders WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (long customerId : customerIds) {
        ps.setLong(1, customerId);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                processOrder(rs.getLong("order_id"));
            }
        }
    }
}
~~~

Việc tái sử dụng cùng đối tượng statement tránh phải tạo một đối tượng JDBC mới cho mỗi lần lặp. Mức độ tái sử dụng ở MySQL Server còn phụ thuộc chế độ prepare và cache được cấu hình.

## 2. Hai cách Connector/J xử lý prepared statement

Connector/J có thể thực hiện PreparedStatement theo hai cách.

### 2.1. Client-side prepared statement (mô phỏng phía client)

Ở chế độ client-side, Connector/J giữ mẫu SQL và các giá trị tham số trong driver. Khi thực thi, driver chuyển các giá trị thành literal SQL phù hợp, escape và định dạng chúng theo metadata của connection rồi gửi câu SQL hoàn chỉnh tới MySQL Server qua giao thức văn bản.

Ví dụ ứng dụng tạo mẫu:

~~~sql
SELECT order_id FROM orders WHERE customer_id = ?
~~~

Khi giá trị customer_id là 501, driver gửi một câu SQL đã được tạo với giá trị đó. MySQL Server nhận câu SQL văn bản, phân tích và thực thi như một câu lệnh thông thường.

Đặc điểm:

- Không cần tạo handle prepared statement ở server cho mỗi câu lệnh.
- Có thể giảm chi phí quản lý prepared statement phía server.
- SQL sau khi thay tham số vẫn phải được server phân tích ở mỗi lần thực thi.
- Driver chịu trách nhiệm chuyển kiểu và escape giá trị đúng với connection, charset và SQL mode.

Đây vẫn là việc sử dụng JDBC PreparedStatement; tên API không cho biết statement được prepare ở đâu.

### 2.2. Server-side prepared statement

Ở chế độ server-side, Connector/J sử dụng giao thức prepared statement nhị phân của MySQL. Driver gửi mẫu SQL để server chuẩn bị, sau đó gửi giá trị tham số riêng trong các lần thực thi.

Luồng khái quát:

1. Client gửi mẫu SQL bằng lệnh giao thức prepare (COM_STMT_PREPARE).
2. Server phân tích câu lệnh, tạo prepared statement handle và trả về metadata tham số/kết quả phù hợp.
3. Client gửi giá trị tham số và yêu cầu thực thi (COM_STMT_EXECUTE).
4. Server thực thi statement đã chuẩn bị với bộ giá trị mới.
5. Khi không còn dùng, client đóng handle (COM_STMT_CLOSE) hoặc driver quản lý vòng đời theo cache.

Ví dụ SQL vẫn là:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ? AND created_at >= ?
~~~

Các giá trị customer_id và created_at được gửi riêng trong protocol execute thay vì nối trực tiếp vào chuỗi SQL văn bản.

Đặc điểm:

- Server phân tích câu lệnh khi prepare và có thể tái sử dụng prepared statement cho các lần execute tiếp theo.
- Tham số được truyền theo giao thức nhị phân với thông tin kiểu dữ liệu.
- Mỗi prepared statement thuộc session/connection MySQL đã tạo nó.
- Server phải giữ tài nguyên cho statement đang mở; số lượng quá lớn có thể chạm giới hạn toàn cục.
- Một số thay đổi metadata có thể khiến server phải reprepare statement.

Server-side prepare không đảm bảo mọi truy vấn nhanh hơn. Nó hữu ích nhất khi cùng một mẫu SQL được thực thi lặp lại; với câu lệnh chỉ chạy một lần, chi phí prepare và quản lý handle có thể không đem lại lợi ích đáng kể.

## 3. Bật useServerPrepStmts

Trong MySQL Connector/J, thuộc tính useServerPrepStmts mặc định là false. Muốn yêu cầu sử dụng prepared statement phía server, bật thuộc tính trong JDBC URL hoặc cấu hình DataSource:

~~~text
jdbc:mysql://db.example.net:3306/shop?useServerPrepStmts=true
~~~

Ví dụ cấu hình bằng MysqlDataSource:

~~~java
import com.mysql.cj.jdbc.MysqlDataSource;
import javax.sql.DataSource;

MysqlDataSource mysql = new MysqlDataSource();
mysql.setURL("jdbc:mysql://db.example.net:3306/shop");
mysql.setUser("shop_app");
mysql.setPassword(readSecret());
mysql.setUseServerPrepStmts(true);

DataSource dataSource = mysql;
~~~

Tên setter và package cần tương ứng với phiên bản Connector/J đang sử dụng. Nếu dùng connection pool như HikariCP, cấu hình thuộc tính trong JDBC URL hoặc properties của driver mà pool chuyển tới Connector/J. Hãy xác minh cấu hình thực tế trên từng physical connection.

Ví dụ URL kết hợp server-side prepare và cache:

~~~text
jdbc:mysql://db.example.net:3306/shop?useServerPrepStmts=true&cachePrepStmts=true&prepStmtCacheSize=100&prepStmtCacheSqlLimit=2048
~~~

Các con số cache trên chỉ là giá trị minh họa để bắt đầu thử nghiệm, không phải khuyến nghị cố định cho mọi workload. Cần đo số lượng SQL template, độ dài câu lệnh, số connection và giới hạn prepared statement của server trước khi điều chỉnh.

### 3.1. useServerPrepStmts không phải một cam kết tuyệt đối cho mọi câu lệnh

Thuộc tính này yêu cầu Connector/J dùng prepared statement phía server khi server và câu lệnh hỗ trợ. Một số loại câu lệnh hoặc tình huống không được server hỗ trợ có thể được driver xử lý bằng cách mô phỏng phía client. Vì vậy, không nên suy luận rằng mọi PreparedStatement trong ứng dụng đều đã tạo handle server-side chỉ vì URL có useServerPrepStmts=true.

Hãy thử đúng câu SQL, phiên bản MySQL và Connector/J đang chạy; kiểm tra counter hoặc Performance Schema nếu cần chứng minh hành vi thực tế.

## 4. So sánh client-side và server-side

| Tiêu chí | Client-side (emulated) | Server-side (useServerPrepStmts=true) |
|---|---|---|
| Nơi xử lý tham số | Connector/J định dạng/escape và tạo SQL văn bản | Driver gửi tham số riêng qua binary protocol |
| Parse SQL | Server phân tích SQL đã thay tham số ở mỗi lần thực thi | Server prepare mẫu SQL và có thể tái sử dụng statement |
| Tài nguyên server | Không cần handle prepared statement cho cách mô phỏng | Giữ handle trong session khi statement còn mở/cache |
| Kiểu tham số | Driver chuyển giá trị thành literal phù hợp | Tham số được gửi kèm thông tin kiểu theo protocol |
| Câu lệnh chạy một lần | Có thể tránh chi phí prepare handle riêng ở server | Có thêm bước prepare và quản lý handle |
| Câu lệnh lặp lại | Server vẫn parse các câu SQL văn bản sau thay tham số | Có thể giảm chi phí parse và truyền mẫu SQL lặp lại |
| Giới hạn | Phụ thuộc việc escape/chuyển kiểu của driver | Phụ thuộc hỗ trợ prepared statement và giới hạn server |

Cả hai chế độ đều có thể được dùng qua JDBC PreparedStatement. Dùng API tham số hóa đúng cách là quan trọng; bật server-side prepare là một lựa chọn về giao thức và vòng đời statement, không phải điều kiện duy nhất để viết SQL an toàn.

## 5. Phòng chống SQL injection

Không nối dữ liệu người dùng trực tiếp vào SQL:

~~~java
// Không an toàn: input có thể thay đổi cấu trúc câu SQL
String sql = "SELECT * FROM users WHERE email = '" + email + "'";
Statement st = connection.createStatement();
ResultSet rs = st.executeQuery(sql);
~~~

Dùng tham số:

~~~java
String sql = "SELECT user_id, email FROM users WHERE email = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, email);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý người dùng phù hợp
        }
    }
}
~~~

Trong server-side mode, giá trị được truyền riêng với SQL template nên server không diễn giải nội dung tham số như cú pháp SQL. Trong client-side mode, Connector/J mô phỏng bằng cách escape và định dạng literal. Dù dùng chế độ nào, ứng dụng nên luôn dùng PreparedStatement và không tự nối chuỗi dữ liệu không tin cậy vào SQL.

### 5.1. Tham số chỉ đại diện cho giá trị

Dấu ? không thể thay thế tên bảng, tên cột, từ khóa, toán tử hoặc hướng sắp xếp. Ví dụ sau không làm việc như mong muốn:

~~~java
String sql = "SELECT * FROM ? WHERE customer_id = ?";
PreparedStatement ps = connection.prepareStatement(sql);
ps.setString(1, "orders");
ps.setLong(2, customerId);
~~~

MySQL cần biết tên bảng khi phân tích cấu trúc câu lệnh; tham số JDBC không thể biến thành identifier. Nếu cần chọn cột sắp xếp, dùng whitelist cố định:

~~~java
Set<String> allowedSortColumns = Set.of("created_at", "total_amount");
String sortColumn = allowedSortColumns.contains(requestedSort)
        ? requestedSort
        : "created_at";

String sql = "SELECT order_id, total_amount FROM orders "
           + "WHERE customer_id = ? ORDER BY " + sortColumn + " DESC";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);
    // Thực thi truy vấn
}
~~~

Chỉ identifier đã được kiểm tra từ whitelist mới được đưa vào SQL. Không dùng giá trị người dùng làm identifier trực tiếp.

### 5.2. IN (?) không tự mở rộng danh sách

Một dấu ? tương ứng một giá trị. Gán chuỗi "1,2,3" vào một placeholder không biến nó thành ba phần tử trong mệnh đề IN.

Nếu cần truy vấn một danh sách có kích thước thay đổi, tạo số placeholder tương ứng rồi gán từng phần tử:

~~~java
List<Long> ids = List.of(101L, 102L, 103L);
String placeholders = String.join(",", Collections.nCopies(ids.size(), "?"));
String sql = "SELECT order_id FROM orders WHERE order_id IN (" + placeholders + ")";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < ids.size(); i++) {
        ps.setLong(i + 1, ids.get(i));
    }
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            processOrder(rs.getLong(1));
        }
    }
}
~~~

Chuỗi SQL ở đây chỉ được tạo từ số lượng dấu ?; mọi giá trị vẫn được bind. Cần xử lý riêng danh sách rỗng và giới hạn kích thước danh sách để tránh câu SQL quá lớn.

## 6. Gán kiểu dữ liệu chính xác

Chọn setter phù hợp giúp tránh chuyển đổi không cần thiết và giữ đúng ngữ nghĩa dữ liệu:

| Kiểu MySQL thường gặp | Setter JDBC gợi ý |
|---|---|
| TINYINT, INT trong phạm vi Java int | setInt |
| BIGINT | setLong |
| DECIMAL, NUMERIC | setBigDecimal |
| VARCHAR, TEXT | setString |
| DATE | setDate hoặc API java.time được Connector/J hỗ trợ |
| DATETIME, TIMESTAMP | setTimestamp hoặc kiểu java.time phù hợp |
| BINARY, VARBINARY, BLOB | setBytes, setBinaryStream |

Ví dụ với DECIMAL và giá trị NULL:

~~~java
String sql = "INSERT INTO invoices (invoice_no, amount, due_date) "
           + "VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, invoiceNumber);

    if (amount == null) {
        ps.setNull(2, Types.DECIMAL);
    } else {
        ps.setBigDecimal(2, amount);
    }

    if (dueDate == null) {
        ps.setNull(3, Types.DATE);
    } else {
        ps.setDate(3, java.sql.Date.valueOf(dueDate));
    }

    ps.executeUpdate();
}
~~~

Không truyền chuỗi "NULL" để biểu diễn SQL NULL; hãy dùng setNull với JDBC type phù hợp. Với ngày giờ, cần thống nhất timezone của JVM, JDBC connection và MySQL, đặc biệt khi dùng TIMESTAMP vì kiểu này được chuyển đổi theo timezone của session.

## 7. Tái sử dụng và cache prepared statement

Server-side prepare có lợi nhất khi một SQL template được thực thi nhiều lần trên cùng connection. Có hai lớp tái sử dụng cần phân biệt:

- Tái sử dụng cùng đối tượng PreparedStatement trong code: giữ statement mở và gọi setX()/execute...() nhiều lần.
- Cache của Connector/J: driver giữ statement đã prepare để có thể tái sử dụng khi ứng dụng đóng statement và sau đó prepare lại cùng SQL trên cùng physical connection.

Thuộc tính cachePrepStmts điều khiển cache phía driver; thuộc tính này mặc định không bật. Khi cần thử cache, có thể cấu hình:

~~~text
useServerPrepStmts=true
cachePrepStmts=true
prepStmtCacheSize=100
prepStmtCacheSqlLimit=2048
~~~

Ý nghĩa:

- cachePrepStmts: bật cache prepared statement trong Connector/J.
- prepStmtCacheSize: số lượng statement cache tối đa theo connection.
- prepStmtCacheSqlLimit: giới hạn độ dài SQL được cache.

Cache gắn với physical connection. Nếu pool có 40 connection và mỗi connection giữ cache tối đa 100 statement, tổng số handle có thể tăng đáng kể nếu workload sử dụng nhiều mẫu SQL. Không nên đặt cache size lớn mà không tính đến số connection, số SQL template và max_prepared_stmt_count trên MySQL Server.

### 7.1. Quản lý vòng đời statement

Mẫu nên dùng:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "UPDATE inventory SET quantity = ? WHERE product_id = ?")) {
    ps.setInt(1, newQuantity);
    ps.setLong(2, productId);
    ps.executeUpdate();
}
~~~

Khi statement được đóng, driver giải phóng hoặc đưa handle vào cache theo cấu hình. Không giữ hàng nghìn statement mở trong một request hoặc lưu statement lâu hơn vòng đời connection. Khi connection pool trả connection về pool, các statement đang mở cần được đóng để tránh rò rỉ tài nguyên và trạng thái session.

Prepared statement server-side thuộc connection cụ thể. Không thể prepare trên connection A rồi thực thi handle đó trên connection B. Nếu ứng dụng lấy connection khác từ pool cho lần gọi tiếp theo, statement phải được tạo hoặc lấy lại từ cache của connection đó.

### 7.2. Giới hạn ở MySQL Server

MySQL giới hạn tổng số prepared statement đang mở bằng biến max_prepared_stmt_count. Có thể kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'max_prepared_stmt_count';
SHOW GLOBAL STATUS LIKE 'Prepared_stmt_count';
SHOW GLOBAL STATUS LIKE 'Com_stmt_prepare';
SHOW GLOBAL STATUS LIKE 'Com_stmt_execute';
SHOW GLOBAL STATUS LIKE 'Com_stmt_close';
~~~

Nếu số lượng statement tăng liên tục, kiểm tra connection leak, statement không được đóng, cache quá lớn hoặc pool có quá nhiều physical connection. Không chỉ tăng max_prepared_stmt_count để che giấu lỗi quản lý vòng đời.

## 8. Batching và prepared statement

Với nhiều thao tác cùng mẫu SQL, có thể dùng addBatch() và executeBatch():

~~~java
String sql = "INSERT INTO order_items (order_id, product_id, quantity) "
           + "VALUES (?, ?, ?)";

boolean originalAutoCommit = connection.getAutoCommit();
connection.setAutoCommit(false);
try {
    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        int count = 0;
        for (OrderItem item : items) {
            ps.setLong(1, item.orderId());
            ps.setLong(2, item.productId());
            ps.setInt(3, item.quantity());
            ps.addBatch();

            if (++count % 500 == 0) {
                ps.executeBatch();
            }
        }

        ps.executeBatch();
    }
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
} finally {
    connection.setAutoCommit(originalAutoCommit);
}
~~~

Đoạn mã minh họa cách gom nhiều thao tác và kết thúc transaction khi thành công hoặc lỗi. Trong code production, cần xử lý riêng exception phát sinh khi rollback hoặc khôi phục autoCommit để không che mất lỗi ban đầu. Batch size 500 chỉ là ví dụ, cần đo theo payload, transaction duration, packet size, lock contention và replication lag.

useServerPrepStmts và batching là hai lựa chọn riêng. Bật server-side prepare không tự động có nghĩa driver sẽ gộp mọi batch thành một câu SQL duy nhất. Connector/J có thuộc tính batching riêng, và hành vi có thể phụ thuộc loại câu lệnh cùng phiên bản driver. Đo hiệu năng với cấu hình thực tế trước khi bật thêm tùy chọn.

## 9. Fetch dữ liệu lớn và server-side cursor

Với kết quả rất lớn, việc giữ toàn bộ ResultSet trong bộ nhớ client có thể gây áp lực heap. Connector/J hỗ trợ cursor fetch trong những điều kiện nhất định; useCursorFetch=true yêu cầu server-side prepared statements và cần fetch size khác 0 để sử dụng cơ chế cursor phía server.

Ví dụ URL:

~~~text
jdbc:mysql://db.example.net:3306/shop?useServerPrepStmts=true&useCursorFetch=true&defaultFetchSize=500
~~~

Hoặc đặt fetch size trên statement:

~~~java
String sql = "SELECT order_id, created_at FROM orders ORDER BY order_id";

try (PreparedStatement ps = connection.prepareStatement(
        sql, ResultSet.TYPE_FORWARD_ONLY, ResultSet.CONCUR_READ_ONLY)) {
    ps.setFetchSize(500);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            processOrder(rs.getLong("order_id"));
        }
    }
}
~~~

Fetch size là gợi ý/điều khiển cách lấy kết quả theo driver; nó không giới hạn số hàng mà câu SQL trả về. Server-side cursor có thể giữ tài nguyên server và connection trong suốt thời gian duyệt kết quả. Hãy đóng ResultSet sớm, tránh giữ cursor trong khi xử lý công việc bên ngoài lâu và đo cả heap client lẫn tài nguyên server.

## 10. Kiểm tra server-side prepare có thực sự hoạt động

Không nên chỉ nhìn JDBC URL để kết luận. Có thể dùng một số dấu hiệu ở phía server.

### 10.1. Status counters

Các counter Com_stmt_* cho biết hoạt động prepared statement ở cấp server:

~~~sql
SHOW GLOBAL STATUS LIKE 'Com_stmt%';
SHOW GLOBAL STATUS LIKE 'Prepared_stmt_count';
~~~

Chạy một workload thử nghiệm có nhiều lần prepareStatement() và executeQuery() trên connection được cấu hình useServerPrepStmts=true, sau đó quan sát sự thay đổi của Com_stmt_prepare, Com_stmt_execute và Com_stmt_close. Counter global có thể bị ảnh hưởng bởi ứng dụng khác; nên đo trong môi trường thử nghiệm hoặc đối chiếu mức tăng trước/sau một workload cô lập.

### 10.2. Performance Schema

Nếu Performance Schema được bật và có đủ quyền, kiểm tra các prepared statement server-side hiện đang mở:

~~~sql
SELECT STATEMENT_ID, STATEMENT_NAME, SQL_TEXT,
       OWNER_THREAD_ID, COUNT_EXECUTE, COUNT_REPREPARE
FROM performance_schema.prepared_statements_instances;
~~~

Bảng này hiển thị statement còn được giữ ở server tại thời điểm truy vấn. Nếu ứng dụng đóng statement ngay và driver không cache, handle có thể biến mất trước khi kiểm tra. Một lần truy vấn không thấy dòng nào không đủ để kết luận driver chưa từng dùng server-side prepare.

Có thể xem thêm các counter reprepare để tìm thay đổi metadata hoặc tình huống server phải chuẩn bị lại statement. Tên cột và khả năng quan sát cụ thể cần đối chiếu với phiên bản MySQL đang dùng.

## 11. Hiệu năng và các tình huống cần cân nhắc

### 11.1. Khi server-side prepare có thể hữu ích

- Một câu SQL template được thực thi lặp lại với nhiều bộ tham số.
- Ứng dụng dùng connection lâu sống và tái sử dụng statement hiệu quả.
- Giảm chi phí parse lại câu SQL văn bản là một phần đáng kể của workload.
- Cần truyền tham số kiểu nhị phân, đặc biệt với dữ liệu số, ngày giờ hoặc payload phù hợp.
- Dùng cursor fetch cho kết quả lớn và chấp nhận vòng đời cursor trên server.

### 11.2. Khi lợi ích có thể thấp hoặc có chi phí

- Câu SQL chỉ thực thi một lần; chi phí prepare/close có thể lớn hơn phần tiết kiệm.
- Ứng dụng tạo rất nhiều câu SQL khác nhau do nối literal hoặc tạo cấu trúc động, làm cache khó đạt hit rate tốt.
- Pool có nhiều physical connection, khiến mỗi connection có cache riêng và tổng số server handle tăng.
- Statement được giữ mở lâu, tiêu thụ tài nguyên server hoặc connection.
- Metadata/schema thay đổi làm statement phải reprepare.
- Một số câu lệnh không hỗ trợ server-side prepare và driver phải dùng cơ chế mô phỏng.

Server-side prepare không tự tạo index, không sửa execution plan kém và không bảo đảm MySQL luôn dùng cùng một kế hoạch tối ưu. Vẫn phải tối ưu SQL, index, thống kê và transaction độc lập với lựa chọn prepare mode.

### 11.3. Tránh tạo SQL template không ổn định

Nếu ứng dụng đưa giá trị vào chuỗi SQL thay vì placeholder, mỗi giá trị tạo ra một SQL text khác nhau. Điều đó làm giảm khả năng tái sử dụng statement và cache. Hãy giữ cấu trúc SQL ổn định, bind giá trị qua setter và chỉ tạo phần identifier từ whitelist khi thực sự cần.

## 12. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/xử lý |
|---|---|---|
| Không thấy server-side statement | Thuộc tính chưa áp dụng cho physical connection, statement không hỗ trợ hoặc handle đã đóng | Kiểm tra JDBC URL/DataSource, counter và Performance Schema trong lúc chạy |
| max_prepared_stmt_count bị vượt | Quá nhiều handle, statement không đóng hoặc cache/pool quá lớn | Đo Prepared_stmt_count, kiểm tra vòng đời statement và tính tổng cache theo connection |
| Truy vấn chậm hơn sau khi bật | Workload ít tái sử dụng, chi phí prepare, cache miss hoặc kiểu tham số không phù hợp | Benchmark theo từng nhóm SQL, so sánh p95/p99 và tài nguyên server |
| Lỗi chuyển kiểu tham số | Dùng setter không phù hợp, NULL không có JDBC type rõ hoặc timezone khác nhau | Dùng setter/setNull đúng kiểu và kiểm tra session timezone |
| Lỗi khi dùng placeholder cho tên bảng/cột | Parameter marker chỉ đại diện giá trị | Dùng whitelist identifier đã xác thực và bind phần dữ liệu |
| IN (?) chỉ khớp một giá trị | Một placeholder là một giá trị đơn | Sinh số placeholder phù hợp hoặc dùng chiến lược staging cho danh sách lớn |
| Statement phải prepare lại | Metadata bảng thay đổi hoặc server phát hiện cần reprepare | Kiểm tra COUNT_REPREPARE, thời điểm DDL và vòng đời statement |
| Heap tăng khi đọc nhiều hàng | Driver/client đang buffer kết quả lớn | Đánh giá fetch size, cursor fetch, ResultSet mode và thời gian giữ cursor |

Khi ghi log để điều tra, ưu tiên ghi SQL template, thời gian, số hàng và loại lỗi. Tránh ghi password, token, dữ liệu cá nhân hoặc toàn bộ bind values nhạy cảm vào log ứng dụng.

## 13. Quy trình benchmark trước khi bật trong production

Không bật useServerPrepStmts trên toàn bộ hệ thống chỉ dựa vào một truy vấn mẫu. Nên so sánh trên môi trường gần production:

1. Chọn một tập truy vấn đại diện: truy vấn lặp lại nhiều, truy vấn chỉ chạy một lần, DML, batch và truy vấn trả nhiều hàng.
2. Giữ nguyên SQL template, tham số, index, dữ liệu và concurrency giữa hai lượt thử.
3. Chạy lượt A với client-side mode và lượt B với useServerPrepStmts=true.
4. Nếu đánh giá cache, thực hiện thêm lượt với cachePrepStmts=true và cùng kích thước pool.
5. Đo throughput, p50/p95/p99 latency, CPU client/server, network bytes, số prepared statement, parse/execute counters, heap và replication lag.
6. Lặp lại đủ lâu để cache nóng và tải ổn định; tránh chỉ đo một lần chạy ngắn.
7. Thử reconnect, connection eviction, failover và đóng/mở statement để phát hiện lỗi vòng đời.
8. Triển khai theo tỷ lệ traffic nhỏ, theo dõi metric và có cách tắt thuộc tính nếu kết quả xấu.

Một thay đổi có thể cải thiện CPU nhưng làm tăng số handle hoặc memory. Hãy chọn dựa trên tổng thể latency, throughput, tài nguyên và độ ổn định của hệ thống.

## 14. Checklist triển khai

- [ ] Đã xác định phiên bản MySQL Server và Connector/J.
- [ ] Đã xác định các truy vấn nào thực sự lặp lại và phù hợp với prepared statement.
- [ ] Đã giữ SQL template ổn định và bind toàn bộ giá trị bằng setter.
- [ ] Đã không dùng placeholder cho identifier hoặc danh sách IN theo cách sai.
- [ ] Đã cấu hình useServerPrepStmts ở đúng DataSource/physical connection.
- [ ] Đã kiểm tra cachePrepStmts, cache size và giới hạn độ dài SQL nếu bật cache.
- [ ] Đã tính số handle tối đa theo số physical connection và max_prepared_stmt_count.
- [ ] Đã đóng statement/result set đúng vòng đời và xử lý lỗi transaction.
- [ ] Đã benchmark client-side và server-side trên workload đại diện.
- [ ] Đã kiểm tra counter Com_stmt_* hoặc Performance Schema để xác nhận hành vi.
- [ ] Đã đánh giá cursor fetch nếu đọc kết quả lớn.
- [ ] Đã bảo đảm log không làm lộ tham số nhạy cảm.
- [ ] Đã có kế hoạch rollout, theo dõi và tắt cấu hình khi cần.

## 15. Tự kiểm tra

1. JDBC PreparedStatement có đồng nghĩa MySQL Server đang dùng prepared statement phía server không? Giải thích.
2. Khác biệt về giao thức giữa client-side emulation và server-side prepare là gì?
3. useServerPrepStmts=true điều khiển hành vi nào của Connector/J?
4. Vì sao server-side prepare có thể hữu ích với SQL được thực thi lặp lại nhưng không luôn nhanh hơn?
5. Vì sao ? không thể thay thế tên bảng hoặc tên cột?
6. Vì sao IN (?) không thể nhận một chuỗi chứa nhiều ID để tạo danh sách phần tử?
7. cachePrepStmts khác việc tái sử dụng cùng một đối tượng PreparedStatement như thế nào?
8. Vì sao cần tính số connection pool khi điều chỉnh cache và max_prepared_stmt_count?
9. useCursorFetch liên quan thế nào đến server-side prepared statement và fetch size?
10. Hãy đề xuất một benchmark để quyết định có bật server-side prepare cho dịch vụ Java xử lý nhiều truy vấn đơn hàng hay không.

Khi tối ưu MySQL Connector/J, hãy phân biệt API JDBC với cơ chế protocol thực tế. PreparedStatement là cách ứng dụng biểu diễn truy vấn có tham số; useServerPrepStmts quyết định driver có yêu cầu MySQL chuẩn bị câu lệnh ở server hay không. Cần kết hợp bind đúng kiểu, quản lý vòng đời, kiểm soát cache và đo workload thực tế để chọn cấu hình phù hợp.

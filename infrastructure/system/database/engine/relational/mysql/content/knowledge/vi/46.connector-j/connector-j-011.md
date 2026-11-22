# Generated keys, AUTO_INCREMENT và ranh giới kết nối

Khi ứng dụng Java chèn một hàng vào bảng MySQL có cột AUTO_INCREMENT, nó thường cần lấy ID vừa được tạo để ghi hàng con, trả kết quả cho API hoặc lưu dấu vết giao dịch. Với MySQL Connector/J, cách chuẩn là yêu cầu JDBC trả generated keys và đọc chúng từ chính PreparedStatement đã thực hiện INSERT. Nếu dùng LAST_INSERT_ID(), câu truy vấn phải chạy trên cùng kết nối vật lý với lệnh INSERT. Hiểu ranh giới giữa statement, transaction và connection giúp tránh lấy nhầm ID khi có nhiều request đồng thời, connection pool hoặc batch insert.

Bài học này thuộc chương **Connector/J** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành, Connector/J là lớp kết nối để ứng dụng Java thực hiện các thao tác đó. Bài này tập trung vào generated keys, quy tắc cấp AUTO_INCREMENT và việc dữ liệu trạng thái của MySQL gắn với một phiên kết nối.

## 1. AUTO_INCREMENT được cấp như thế nào?

Một cột AUTO_INCREMENT là cột số nguyên mà MySQL tự cấp giá trị khi INSERT không cung cấp giá trị tường minh cho cột đó:

~~~sql
CREATE TABLE customers (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  email VARCHAR(254) NOT NULL,
  display_name VARCHAR(120) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_customers_email (email)
) ENGINE=InnoDB;
~~~

Ứng dụng có thể chèn hàng mà không truyền `id`:

~~~sql
INSERT INTO customers (email, display_name)
VALUES ('linh@example.com', 'Linh Nguyen');
~~~

MySQL cấp một giá trị cho `id` và lưu hàng. Trong JDBC, ứng dụng có thể lấy khóa vừa sinh qua API `getGeneratedKeys()`.

AUTO_INCREMENT là cơ chế cấp giá trị định danh, không phải bộ đếm số hàng và cũng không phải số thứ tự nghiệp vụ liên tục. Giá trị có thể có khoảng trống vì:

- Transaction chèn hàng rồi rollback.
- INSERT thất bại hoặc bỏ qua hàng do duplicate/IGNORE.
- Nhiều kết nối chèn đồng thời.
- Một câu INSERT cấp nhiều giá trị hoặc batch bị chia thành nhiều statement.
- Ứng dụng xóa hàng đã được cấp ID.
- Cấu hình `auto_increment_increment` và `auto_increment_offset` tạo bước nhảy khác 1, thường gặp trong một số topology replication.

Không dùng ID để suy ra số lượng hàng, thời điểm commit hoặc thứ tự nghiệp vụ tuyệt đối. Nếu cần số hóa đơn không được bỏ số theo quy định nghiệp vụ, hãy thiết kế cơ chế đánh số riêng với khóa và quy trình kiểm soát phù hợp; AUTO_INCREMENT không bảo đảm dãy liên tục.

### Chọn kiểu dữ liệu và giới hạn tăng trưởng

Chọn kiểu số nguyên dựa trên số lượng bản ghi tối đa dự kiến và thời gian lưu giữ:

| Kiểu | Phạm vi UNSIGNED | Khi cân nhắc |
|---|---:|---|
| TINYINT | 0 đến 255 | Bảng rất nhỏ, ít hàng |
| SMALLINT | 0 đến 65.535 | Tập dữ liệu nhỏ |
| MEDIUMINT | 0 đến 16.777.215 | Hệ thống có giới hạn tăng trưởng rõ |
| INT | 0 đến 4.294.967.295 | Nhiều ứng dụng nghiệp vụ |
| BIGINT | 0 đến 18.446.744.073.709.551.615 | Bảng lớn, vòng đời dài hoặc cần headroom cao |

Các giới hạn trên là phạm vi của kiểu UNSIGNED. Nếu dùng kiểu signed, phạm vi dương thấp hơn. Khi schema dùng `BIGINT UNSIGNED`, phía Java nên đọc bằng `ResultSet.getLong()` nếu giá trị nằm trong miền signed 64-bit của Java. Miền BIGINT UNSIGNED của MySQL lớn hơn `Long.MAX_VALUE`; nếu hệ thống có thể vượt giới hạn đó, cần một cách biểu diễn khác như `BigInteger` và chuyển đổi cẩn thận từ giá trị trả về của driver.

Đừng chọn BIGINT chỉ vì “lớn hơn thì tốt hơn” mà không xét kích thước index, foreign key và dữ liệu truyền qua mạng. Các cột khóa cha-con phải có kiểu tương thích. Nhưng cũng đừng dùng INT khi tốc độ tăng trưởng có thể làm cạn miền giá trị trong thời gian vận hành dự kiến.

## 2. Lấy generated key bằng JDBC

JDBC cung cấp cờ `Statement.RETURN_GENERATED_KEYS`. Truyền cờ này khi tạo PreparedStatement, thực hiện INSERT rồi đọc ResultSet do `getGeneratedKeys()` trả về:

Các ví dụ Java dùng text block (`"""`), được hỗ trợ từ Java 15. Nếu dự án dùng JDK cũ hơn, thay text block bằng chuỗi Java thông thường và giữ nguyên placeholder.

~~~java
String sql = """
    INSERT INTO customers (email, display_name)
    VALUES (?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         sql,
         Statement.RETURN_GENERATED_KEYS
     )) {

    statement.setString(1, "linh@example.com");
    statement.setString(2, "Linh Nguyen");

    int affectedRows = statement.executeUpdate();
    if (affectedRows != 1) {
        throw new SQLException(
            "Expected one inserted customer, got " + affectedRows
        );
    }

    try (ResultSet keys = statement.getGeneratedKeys()) {
        if (!keys.next()) {
            throw new SQLException("MySQL did not return a generated key");
        }

        long customerId = keys.getLong(1);
        if (keys.wasNull()) {
            throw new SQLException("Generated key is NULL");
        }

        System.out.println("Created customer id = " + customerId);
    }
}
~~~

Các điểm quan trọng:

1. Tạo statement với `Statement.RETURN_GENERATED_KEYS`; nếu không yêu cầu generated keys, không nên giả định driver luôn trả về.
2. Dùng `executeUpdate()` cho INSERT/UPDATE/DELETE.
3. Gọi `getGeneratedKeys()` trên chính statement đã thực hiện INSERT.
4. Kiểm tra ResultSet có hàng trước khi đọc.
5. Đọc cột đầu tiên bằng `getLong(1)` hoặc kiểu Java phù hợp với cột ID.
6. Đọc generated key trước khi đóng statement và connection.

Có thể chỉ định tên cột generated key bằng overload `prepareStatement(sql, new String[] {"id"})` nếu cần. Với AUTO_INCREMENT thông thường, `Statement.RETURN_GENERATED_KEYS` là cách ngắn gọn và phổ biến.

Không dùng `SELECT MAX(id)` để tìm ID vừa chèn. Kết nối khác có thể chèn hàng giữa INSERT của bạn và truy vấn MAX, khiến ứng dụng lấy ID của request khác. Generated keys gắn với statement hiện tại nên không có race condition đó.

## 3. Lấy ID bằng LAST_INSERT_ID()

MySQL cung cấp hàm `LAST_INSERT_ID()` để trả về giá trị AUTO_INCREMENT đầu tiên được tạo bởi câu lệnh INSERT gần nhất trong **session hiện tại**:

~~~sql
INSERT INTO customers (email, display_name)
VALUES ('linh@example.com', 'Linh Nguyen');

SELECT LAST_INSERT_ID();
~~~

Kết quả chỉ đúng với session đã chạy INSERT. Mỗi kết nối MySQL có trạng thái LAST_INSERT_ID riêng; một kết nối khác chèn hàng không làm thay đổi giá trị của session hiện tại.

Trong JDBC, có thể thực hiện hai câu lệnh trên cùng Connection:

~~~java
long customerId;

try (Connection connection = dataSource.getConnection()) {
    try (PreparedStatement insert = connection.prepareStatement(
            "INSERT INTO customers (email, display_name) VALUES (?, ?)")) {
        insert.setString(1, "linh@example.com");
        insert.setString(2, "Linh Nguyen");
        insert.executeUpdate();
    }

    try (Statement query = connection.createStatement();
         ResultSet result = query.executeQuery("SELECT LAST_INSERT_ID()")) {
        if (!result.next()) {
            throw new SQLException("LAST_INSERT_ID() returned no row");
        }
        customerId = result.getLong(1);
    }
}
~~~

Cách này có thể hoạt động, nhưng phải giữ nguyên Connection xuyên suốt cả hai câu lệnh. Không gọi `connection.close()` sau INSERT rồi lấy một Connection mới từ pool để chạy `SELECT LAST_INSERT_ID()`; kết nối mới là một session khác và có trạng thái LAST_INSERT_ID riêng.

Với JDBC, ưu tiên `getGeneratedKeys()` vì API thể hiện trực tiếp mối liên hệ giữa INSERT và khóa được sinh. Dùng LAST_INSERT_ID() khi có lý do cụ thể, chẳng hạn cần đọc lại trạng thái session hoặc tích hợp với một câu lệnh SQL đặc thù.

### LAST_INSERT_ID() và INSERT nhiều hàng

Với một câu INSERT nhiều hàng, `LAST_INSERT_ID()` trả về giá trị AUTO_INCREMENT đầu tiên được tạo bởi statement đó, không phải danh sách toàn bộ ID. Không tính các ID tiếp theo bằng cách cộng 1 một cách máy móc: cấu hình auto-increment, concurrency, kiểu INSERT và cơ chế cấp ID có thể tạo khoảng trống hoặc bước nhảy.

Nếu cần ánh xạ chính xác từng bản ghi đầu vào sang ID đầu ra, hãy dùng generated keys và xác minh hành vi của Connector/J ở phiên bản cùng chế độ batch đang triển khai. Nếu cần ánh xạ chắc chắn bất kể cách driver tối ưu batch, dùng một khóa nghiệp vụ/UUID ổn định trong dữ liệu để truy vấn lại mapping, hoặc thực hiện từng INSERT và đọc key tương ứng.

## 4. Ranh giới giữa Connection, Statement và ResultSet

JDBC có ba đối tượng liên quan trực tiếp:

- **Connection:** đại diện cho một session kết nối tới MySQL. Trạng thái transaction, session variable, temporary table và LAST_INSERT_ID() gắn với session này.
- **Statement/PreparedStatement:** thực thi một câu SQL trên Connection. Generated keys được lấy từ statement đã yêu cầu và thực hiện INSERT.
- **ResultSet:** chứa các hàng được trả về, bao gồm ResultSet generated keys. Nó cần được đọc trước khi đóng tài nguyên liên quan.

Sơ đồ vòng đời:

~~~text
DataSource
    |
    | getConnection()
    v
Connection (một MySQL session)
    |
    +--> PreparedStatement (INSERT ... RETURN_GENERATED_KEYS)
    |          |
    |          +--> executeUpdate()
    |          |
    |          +--> getGeneratedKeys()
    |                    |
    |                    v
    |               ResultSet: id
    |
    +--> Có thể dùng tiếp cùng Connection
    |    cho INSERT hàng con / LAST_INSERT_ID()
    |
    v
commit hoặc rollback
    |
    v
close Connection
    |
    +--> Với pool: trả logical connection về pool
    +--> Không pool: đóng physical connection
~~~

Khi dùng connection pool, `dataSource.getConnection()` thường trả một logical connection mượn từ pool. Gọi `close()` trả connection về pool để tái sử dụng, không nhất thiết đóng TCP connection. Pool có trách nhiệm reset một số trạng thái khi trả connection; ứng dụng vẫn phải commit/rollback đúng cách và không giữ reference sau khi đã close.

Không lưu ID session vào biến static hoặc biến dùng chung giữa request. Một request phải dùng Connection của chính nó cho toàn bộ thao tác cần cùng transaction hoặc cùng session state.

## 5. Ghi hàng cha và hàng con trong cùng transaction

Generated key thường được dùng để ghi một hàng cha rồi ghi các hàng con tham chiếu đến nó. Hai thao tác cần cùng Connection và cùng transaction để bảo đảm tính nguyên tử.

Ví dụ tạo khách hàng và đơn hàng:

~~~java
String insertCustomerSql = """
    INSERT INTO customers (email, display_name)
    VALUES (?, ?)
    """;

String insertOrderSql = """
    INSERT INTO orders (order_no, customer_id, total_amount)
    VALUES (?, ?, ?)
    """;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        long customerId;

        try (PreparedStatement customerInsert =
                 connection.prepareStatement(
                     insertCustomerSql,
                     Statement.RETURN_GENERATED_KEYS
                 )) {

            customerInsert.setString(1, "linh@example.com");
            customerInsert.setString(2, "Linh Nguyen");

            int rows = customerInsert.executeUpdate();
            if (rows != 1) {
                throw new SQLException("Customer insert did not affect one row");
            }

            try (ResultSet keys = customerInsert.getGeneratedKeys()) {
                if (!keys.next()) {
                    throw new SQLException("Missing customer generated key");
                }
                customerId = keys.getLong(1);
                if (keys.wasNull()) {
                    throw new SQLException("Customer id is NULL");
                }
            }
        }

        try (PreparedStatement orderInsert =
                 connection.prepareStatement(insertOrderSql)) {
            orderInsert.setString(1, "ORD-2026-0001");
            orderInsert.setLong(2, customerId);
            orderInsert.setBigDecimal(3, new BigDecimal("125000.00"));

            int rows = orderInsert.executeUpdate();
            if (rows != 1) {
                throw new SQLException("Order insert did not affect one row");
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }
}
~~~

Quy trình này có các đặc điểm:

- ID khách hàng được đọc trước khi commit, nên có thể dùng ngay để insert đơn hàng trong cùng transaction.
- Nếu insert đơn hàng thất bại và rollback thành công, cả khách hàng và đơn hàng đều không được commit.
- Giá trị AUTO_INCREMENT đã cấp có thể không được tái sử dụng sau rollback; khoảng trống trong dãy ID là bình thường.
- Không gửi ID cho hệ thống bên ngoài hoặc phát thông báo “đã tạo thành công” trước khi transaction commit thành công.

Nếu kết nối bị mất đúng lúc COMMIT, client có thể không biết server đã commit hay chưa. Không tự động retry toàn bộ nghiệp vụ mà không có cơ chế idempotency; dùng khóa yêu cầu duy nhất hoặc business key để truy vấn và xác định kết quả trước khi chạy lại.

Trong framework quản lý transaction như Spring, để framework điều khiển commit/rollback và lấy generated key bên trong transaction đó. Không tự mở Connection riêng bên ngoài transaction manager rồi kỳ vọng hai kết nối cùng tham gia một transaction.

## 6. INSERT ON DUPLICATE KEY UPDATE và lấy ID hàng đã tồn tại

Một trường hợp đặc biệt là upsert: nếu khóa unique chưa tồn tại thì INSERT tạo hàng mới; nếu đã tồn tại thì MySQL chạy nhánh UPDATE. Khi duplicate, ứng dụng có thể cần ID của hàng đã tồn tại.

Ví dụ:

~~~sql
INSERT INTO customers (email, display_name)
VALUES (?, ?)
ON DUPLICATE KEY UPDATE
  id = LAST_INSERT_ID(id);
~~~

Nếu INSERT tạo hàng mới, MySQL thiết lập LAST_INSERT_ID theo ID vừa cấp. Nếu nhánh UPDATE chạy, biểu thức `LAST_INSERT_ID(id)` đưa ID của hàng hiện có vào trạng thái LAST_INSERT_ID của session.

JDBC có thể đọc giá trị sau đó trên cùng Connection:

~~~java
try (Connection connection = dataSource.getConnection();
     PreparedStatement upsert = connection.prepareStatement("""
         INSERT INTO customers (email, display_name)
         VALUES (?, ?)
         ON DUPLICATE KEY UPDATE
           id = LAST_INSERT_ID(id)
         """)) {

    upsert.setString(1, "linh@example.com");
    upsert.setString(2, "Linh Nguyen");
    upsert.executeUpdate();

    try (Statement query = connection.createStatement();
         ResultSet result = query.executeQuery("SELECT LAST_INSERT_ID()")) {
        if (!result.next()) {
            throw new SQLException("No customer id returned");
        }
        long customerId = result.getLong(1);
    }
}
~~~

Chỉ áp dụng pattern này khi duplicate key xác định đúng một hàng theo quy tắc nghiệp vụ. Nếu bảng có nhiều unique index và đầu vào có thể xung đột với các hàng khác nhau qua các unique key khác nhau, cần xác định rõ hàng nào được phép cập nhật. Không dùng upsert như một cách thay thế validation.

Số hàng affected của INSERT ... ON DUPLICATE KEY UPDATE có thể khác nhau tùy insert/update/no-op và cờ CLIENT_FOUND_ROWS. Không suy luận rằng affectedRows luôn bằng 1 có nghĩa là insert mới hoặc bằng 2 có nghĩa là update. Nếu nghiệp vụ cần phân biệt, dùng một khóa duy nhất và kiểm tra kết quả theo cách được thiết kế rõ ràng.

## 7. Generated keys với batch insert

JDBC cho phép thêm nhiều lệnh vào batch:

~~~java
String sql = """
    INSERT INTO customers (email, display_name)
    VALUES (?, ?)
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
         sql,
         Statement.RETURN_GENERATED_KEYS
     )) {

    statement.setString(1, "a@example.com");
    statement.setString(2, "Customer A");
    statement.addBatch();

    statement.setString(1, "b@example.com");
    statement.setString(2, "Customer B");
    statement.addBatch();

    int[] counts = statement.executeBatch();

    try (ResultSet keys = statement.getGeneratedKeys()) {
        while (keys.next()) {
            long id = keys.getLong(1);
            System.out.println("Generated id: " + id);
        }
    }
}
~~~

Batch giúp giảm round trip và tăng throughput khi nạp nhiều hàng. Tuy nhiên, cần thận trọng khi ánh xạ generated key về từng phần tử đầu vào:

- Connector/J có thể tối ưu batch bằng cách viết lại nhiều INSERT thành một câu INSERT nhiều hàng nếu bật `rewriteBatchedStatements`.
- Kết quả batch có thể chứa `SUCCESS_NO_INFO` hoặc `EXECUTE_FAILED` tùy driver và lỗi.
- Duplicate, INSERT IGNORE, upsert hoặc batch bị ngắt giữa chừng làm quan hệ giữa phần tử đầu vào và số hàng thực tế phức tạp hơn.
- Cách driver trả generated keys phụ thuộc phiên bản Connector/J và cách câu lệnh được rewrite.

Nếu toàn bộ batch phải thành công hoặc thất bại cùng nhau, chạy nó trong transaction tường minh bằng `setAutoCommit(false)`, commit khi mọi lệnh thành công và rollback khi có lỗi. `executeBatch()` tự nó không đảm bảo tính nguyên tử cho mọi cấu hình auto-commit hoặc cách driver xử lý batch.

Nếu ứng dụng cần mapping tuyệt đối chính xác từng bản ghi, hãy kiểm thử với đúng Connector/J version, URL properties và MySQL version. Xác minh số key, thứ tự và xử lý trường hợp lỗi một phần. Với thao tác quan trọng, có thể insert từng hàng và đọc key ngay sau mỗi lệnh hoặc dùng một correlation key ổn định do ứng dụng tạo để truy vấn lại kết quả.

Không tự tạo dãy ID bằng cách lấy ID đầu tiên rồi cộng số thứ tự hàng. Cách đó không an toàn khi auto_increment_increment khác 1, có cấp phát đồng thời, batch rewrite hoặc hàng bị bỏ qua.

## 8. Những trường hợp không nên giả định generated key

| Tình huống | Điều cần lưu ý |
|---|---|
| INSERT cung cấp ID tường minh | Giá trị không nhất thiết là một ID mới do AUTO_INCREMENT sinh |
| INSERT IGNORE bỏ qua duplicate | Không phải đầu vào nào cũng tạo hàng hoặc có key tương ứng |
| ON DUPLICATE KEY UPDATE | Có thể cập nhật hàng hiện tại; cần xác định ID của hàng đó |
| INSERT nhiều hàng | LAST_INSERT_ID() chỉ cho ID đầu tiên; không tự suy ra các ID còn lại |
| Batch có lỗi một phần | Không mặc định mỗi lệnh đầu vào có đúng một key |
| Transaction rollback | ID đã cấp có thể bị bỏ trống; không dùng ID đó như một bản ghi đã tồn tại |
| Connection bị reconnect | Session state cũ, gồm LAST_INSERT_ID(), không còn được bảo đảm |
| Connection trả về pool | Không dùng connection mới để đọc session state của connection đã trả |

Một số câu lệnh INSERT có thể cung cấp giá trị `0` cho AUTO_INCREMENT và được MySQL hiểu là yêu cầu tự sinh ID, trừ khi bật SQL mode `NO_AUTO_VALUE_ON_ZERO`. Nếu ứng dụng hoặc file import có thể truyền 0, hãy kiểm tra SQL mode và thống nhất quy ước. Không để ý nghĩa của ID phụ thuộc ngầm vào cấu hình môi trường.

## 9. Cấu hình Connector/J và connection pool

Kết nối Java thường được tạo từ DataSource hoặc JDBC URL. Ví dụ URL tối giản:

~~~text
jdbc:mysql://db.example.internal:3306/appdb
~~~

Trong production, cấu hình thêm TLS, xác thực, timeout và connection pool theo chính sách của hệ thống. Các thuộc tính như `rewriteBatchedStatements` có thể thay đổi cách driver gửi batch, vì vậy phải ghi nhận chúng trong benchmark và kiểm thử generated keys.

Một số nguyên tắc:

- Mỗi thao tác nghiệp vụ mượn một Connection từ DataSource và trả nó bằng try-with-resources.
- Không lưu Connection dùng chung toàn ứng dụng hoặc chia sẻ đồng thời giữa nhiều thread.
- Không gọi close rồi tiếp tục dùng Connection hoặc Statement đã đóng.
- Không giả định hai lần `getConnection()` trả cùng một physical session.
- Không dùng `autoReconnect` để che lỗi kết nối trong transaction; reconnect tạo session mới và không khôi phục trạng thái transaction/session cũ.
- Đặt connection timeout, socket timeout và pool lifetime theo môi trường, sau đó thử tình huống server restart/failover.
- Khi transaction có lỗi, rollback trước khi trả connection về pool; nếu trạng thái connection không còn tin cậy, để pool loại bỏ connection theo cơ chế phù hợp.

Có thể dùng `SELECT CONNECTION_ID()` trong môi trường thử nghiệm để quan sát hai thao tác có thực hiện trên cùng MySQL session hay không. Không dùng connection ID làm khóa nghiệp vụ; nó chỉ phục vụ chẩn đoán session.

## 10. Kiểm tra và xử lý lỗi thường gặp

### Không có generated key

Kiểm tra:

1. Statement có được tạo với `Statement.RETURN_GENERATED_KEYS` không?
2. INSERT có thực sự tạo hàng mới hay bị bỏ qua/đi vào nhánh duplicate?
3. Cột có phải AUTO_INCREMENT hoặc cột generated mà driver hỗ trợ trả về không?
4. Có đọc `getGeneratedKeys()` trên đúng statement vừa thực hiện không?
5. Driver Connector/J có tương thích với phiên bản MySQL server và JDBC API đang dùng không?

Nếu không có key, không tự fallback sang `SELECT MAX(id)`. Ghi log SQL operation, affected rows và driver version; xử lý theo semantics của câu lệnh.

### LAST_INSERT_ID() trả về giá trị cũ

Nguyên nhân thường gặp là truy vấn chạy trên connection khác, INSERT không tạo AUTO_INCREMENT mới, hoặc thao tác hiện tại là duplicate/update. Xác nhận Connection không bị close/reacquire giữa hai câu lệnh và xem lại nhánh SQL thực tế.

### Lấy nhầm ID khi có nhiều request

Nguyên nhân thường gặp là ứng dụng dùng biến static/shared để giữ last ID, gọi MAX(id), hoặc chia sẻ một Connection giữa các luồng. Dùng generated keys từ statement riêng của từng request và giữ transaction trong Connection riêng.

### Có khoảng trống trong AUTO_INCREMENT

Khoảng trống là bình thường. Rollback, lỗi, concurrent insert và xóa hàng không làm MySQL tái sử dụng ID theo cách bảo đảm liên tục. Không chạy ALTER TABLE để reset AUTO_INCREMENT chỉ nhằm lấp khoảng trống; thao tác này có thể gây trùng hoặc phá giả định của hệ thống.

### Batch trả số key khác số hàng đầu vào

Kiểm tra lỗi từng phần tử trong batch, duplicate handling, rewriteBatchedStatements và phiên bản driver. Nếu cần mapping chính xác, thay đổi cách ghi để có correlation key hoặc xử lý từng INSERT. Không dựa vào giả định rằng số key luôn bằng số lệnh addBatch.

## 11. Checklist triển khai

**Khi thiết kế schema**

- [ ] Chọn kiểu INT/BIGINT theo tốc độ tăng trưởng và thời gian lưu dữ liệu.
- [ ] Đặt AUTO_INCREMENT trên khóa chính hoặc khóa unique phù hợp.
- [ ] Đảm bảo kiểu khóa ngoại tương thích với khóa được tham chiếu.
- [ ] Không dùng ID làm số thứ tự nghiệp vụ liên tục.
- [ ] Kiểm tra auto_increment_increment, auto_increment_offset và SQL mode nếu môi trường replication/import có thể thay đổi.

**Khi viết JDBC**

- [ ] Tạo PreparedStatement với Statement.RETURN_GENERATED_KEYS.
- [ ] Đọc getGeneratedKeys() từ chính statement vừa INSERT.
- [ ] Kiểm tra ResultSet có key và đọc đúng kiểu dữ liệu.
- [ ] Dùng cùng Connection cho thao tác cha-con và LAST_INSERT_ID().
- [ ] Commit trước khi công bố ID như một giao dịch đã thành công.
- [ ] Rollback khi transaction lỗi và không tái sử dụng connection có trạng thái không rõ.
- [ ] Kiểm thử batch với đúng Connector/J version và URL properties.

**Khi vận hành**

- [ ] Ghi nhận phiên bản Connector/J, MySQL và cấu hình pool.
- [ ] Theo dõi lỗi insert, duplicate, rollback và connection reset.
- [ ] Không dùng SELECT MAX(id) hoặc biến toàn cục để lấy ID.
- [ ] Có idempotency/correlation key cho retry khi kết quả COMMIT không rõ.
- [ ] Chấp nhận khoảng trống AUTO_INCREMENT như hành vi bình thường.

## 12. Ghi nhớ

- AUTO_INCREMENT cấp ID, không tạo dãy số liên tục và không phản ánh thứ tự commit.
- Dùng `Statement.RETURN_GENERATED_KEYS` và `PreparedStatement.getGeneratedKeys()` để lấy ID của INSERT hiện tại.
- `LAST_INSERT_ID()` là trạng thái theo MySQL session; phải chạy trên cùng physical connection với INSERT.
- Không dùng `SELECT MAX(id)` vì kết nối đồng thời có thể chèn hàng khác.
- Giữ cùng Connection cho thao tác cha-con trong một transaction; đọc key trước khi commit và chỉ công bố thành công sau commit.
- Rollback không bảo đảm tái sử dụng AUTO_INCREMENT đã cấp.
- Upsert, IGNORE, multi-row INSERT và batch có semantics generated key riêng; kiểm thử theo phiên bản driver.
- Connection pool trả logical connection về pool khi close; không giả định lần mượn tiếp theo có cùng session.
- Không chia sẻ Connection giữa các thread và không dùng lại connection sau khi đã close.

Lấy generated key đúng là vấn đề về ranh giới statement và session. Khi ứng dụng đọc key từ chính statement INSERT, giữ transaction trên một Connection rõ ràng và xử lý batch theo hành vi thực tế của Connector/J, việc tạo khóa cha-con và retry nghiệp vụ sẽ đáng tin cậy hơn.

## Tài liệu tham khảo

- [MySQL Connector/J Developer Guide: Using AUTO_INCREMENT](https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-last-insert-id.html)
- [MySQL Connector/J Developer Guide: JDBC API Implementation Notes](https://dev.mysql.com/doc/connector-j/en/connector-j-reference-implementation-notes.html)
- [MySQL Connector/J Developer Guide: Performance Extensions and rewriteBatchedStatements](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-performance-extensions.html)
- [MySQL 8.0 Reference Manual: Information Functions — LAST_INSERT_ID()](https://dev.mysql.com/doc/refman/8.0/en/information-functions.html#function_last-insert-id)
- [MySQL 8.0 Reference Manual: InnoDB AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/8.0/en/innodb-auto-increment-handling.html)
- [Java JDBC API: Statement.getGeneratedKeys()](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html#getGeneratedKeys())


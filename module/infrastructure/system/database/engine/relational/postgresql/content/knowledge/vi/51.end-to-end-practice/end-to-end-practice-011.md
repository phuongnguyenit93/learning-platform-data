# Tích hợp JDBC, pool kết nối và xử lý lỗi giao dịch

Một ứng dụng Java làm việc với PostgreSQL cần quản lý ba phần gắn chặt với nhau: JDBC để gửi câu lệnh và nhận kết quả, connection pool để tái sử dụng kết nối hiệu quả, và transaction để bảo đảm các thay đổi dữ liệu được thực hiện nhất quán. Nếu quản lý sai vòng đời connection hoặc không xử lý đúng lỗi transaction, ứng dụng có thể gặp tình trạng cạn pool, truy vấn chờ lâu, dữ liệu cập nhật dở dang hoặc lỗi deadlock lặp lại.

Bài học này trình bày cách kết nối Java với PostgreSQL bằng JDBC, cấu hình pool kết nối, tổ chức ranh giới transaction, xử lý lỗi SQLSTATE, retry an toàn và theo dõi hoạt động khi ứng dụng chạy thực tế.

## 1. Kiến trúc tích hợp Java và PostgreSQL

JDBC (Java Database Connectivity) là API chuẩn của Java để làm việc với cơ sở dữ liệu quan hệ. PostgreSQL cung cấp JDBC driver riêng, thường được gọi là pgJDBC. Ứng dụng gọi API JDBC; driver chuyển lời gọi đó thành giao thức PostgreSQL để gửi đến server và chuyển kết quả trả về thành các kiểu Java.

Trong môi trường ứng dụng, nên đặt một connection pool giữa mã nghiệp vụ và driver:

```text
Java service / repository
        |
        v
    DataSource
        |
        v
  Connection pool
        |
        v
 PostgreSQL JDBC driver
        |
        v
 PostgreSQL server
```

Các thành phần có vai trò khác nhau:

- **DataSource:** giao diện JDBC cung cấp connection. Mã ứng dụng phụ thuộc vào DataSource thay vì tự tạo connection theo từng request.
- **Connection pool:** quản lý một tập connection vật lý đã mở tới PostgreSQL. Khi mã ứng dụng gọi phương thức lấy connection, pool cho mượn một connection; khi gọi close, connection thường được trả về pool để tái sử dụng.
- **JDBC driver:** triển khai giao thức kết nối PostgreSQL, xử lý tham số, kiểu dữ liệu, kết quả và lỗi từ server.
- **Connection:** đại diện cho một phiên làm việc với database. Transaction, isolation level và một số thiết lập JDBC gắn với connection này.
- **PreparedStatement:** đại diện cho câu SQL có tham số. Dùng tham số giúp truyền dữ liệu an toàn và cho phép driver/server tái sử dụng kế hoạch phù hợp.
- **ResultSet:** tập kết quả truy vấn. Cần đóng ResultSet và Statement sau khi đọc xong.

Một connection đang được một request sử dụng không nên được chia sẻ đồng thời cho nhiều thread. Transaction và trạng thái của connection có tính phiên; nếu hai luồng cùng thay đổi trạng thái hoặc chạy câu lệnh trên một connection, kết quả có thể khó dự đoán.

## 2. Thêm PostgreSQL JDBC driver và pool vào ứng dụng

Với Maven, ứng dụng thường khai báo PostgreSQL JDBC driver và một thư viện pool như HikariCP. Phiên bản cụ thể nên được quản lý tập trung theo dependency management của dự án.

```xml
<dependencies>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <version>YOUR_APPROVED_PGJDBC_VERSION</version>
    </dependency>

    <dependency>
        <groupId>com.zaxxer</groupId>
        <artifactId>HikariCP</artifactId>
        <version>YOUR_APPROVED_HIKARICP_VERSION</version>
    </dependency>
</dependencies>
```

Trong các ứng dụng hiện đại, driver JDBC tự được phát hiện qua cơ chế service provider. Thông thường không cần gọi Class.forName để nạp driver thủ công. Cách tạo kết nối trực tiếp bằng DriverManager vẫn hữu ích cho chương trình nhỏ hoặc công cụ thử nghiệm, nhưng ứng dụng server nên sử dụng DataSource được quản lý lâu dài.

URL JDBC cơ bản có dạng:

```text
jdbc:postgresql://db-host:5432/orders
```

Trong đó:

- jdbc:postgresql xác định driver PostgreSQL.
- db-host là hostname hoặc địa chỉ máy chủ.
- 5432 là cổng mặc định thường dùng của PostgreSQL.
- orders là tên database.

Có thể truyền thêm tham số kết nối trong URL hoặc cấu hình riêng trên DataSource. Ví dụ, ApplicationName giúp nhận diện ứng dụng trong pg_stat_activity. Thông tin đăng nhập nên được lấy từ secret manager hoặc biến môi trường do nền tảng triển khai quản lý, không ghi mật khẩu trực tiếp vào mã nguồn hay repository.

Ví dụ tạo DataSource với HikariCP:

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(System.getenv("DB_JDBC_URL"));
config.setUsername(System.getenv("DB_USERNAME"));
config.setPassword(System.getenv("DB_PASSWORD"));
config.setPoolName("orders-pool");
config.setMaximumPoolSize(12);

config.addDataSourceProperty("ApplicationName", "orders-api");

HikariDataSource dataSource = new HikariDataSource(config);
```

DataSource nên được tạo một lần trong vòng đời ứng dụng và được inject vào các repository/service cần sử dụng. Không tạo một pool mới cho mỗi HTTP request hoặc mỗi lần gọi repository. Khi ứng dụng dừng, cần đóng DataSource để pool giải phóng connection và thread nền.

## 3. Connection pool hoạt động như thế nào?

Mở một kết nối TCP, xác thực và thiết lập phiên PostgreSQL có chi phí. Nếu ứng dụng mở rồi đóng connection vật lý cho mọi truy vấn, chi phí này có thể lớn khi số request tăng. Pool giữ một số connection đã được tạo sẵn để nhiều request lần lượt sử dụng.

Vòng đời điển hình:

1. Ứng dụng gọi dataSource.getConnection().
2. Pool cấp một connection đang rảnh hoặc chờ đến khi có connection được trả lại.
3. Ứng dụng thực hiện câu lệnh và transaction.
4. Ứng dụng đóng ResultSet, Statement và Connection.
5. Pool thu hồi connection, kiểm tra và đặt lại các trạng thái JDBC cần thiết trước khi cấp cho request tiếp theo.

Trong môi trường có pool, Connection.close() thường chỉ trả connection về pool. Nó không nhất thiết đóng socket tới PostgreSQL. Vì thế, việc đóng connection trong finally hoặc try-with-resources vẫn bắt buộc: nếu không, pool có thể mất dần connection khả dụng.

### 3.1 Vì sao không nên tăng pool size tùy ý?

Mỗi connection PostgreSQL tiêu thụ tài nguyên server: bộ nhớ, backend process và năng lực lập lịch. Nếu nhiều instance ứng dụng cùng tạo pool lớn, tổng số connection có thể vượt giới hạn hoặc làm database chịu quá nhiều truy vấn đồng thời.

Hãy tính tổng ngân sách kết nối:

```text
Tổng connection ứng dụng
  = số instance ứng dụng × maximumPoolSize mỗi instance

Tổng connection dự kiến
  = connection ứng dụng
  + job nền
  + công cụ quản trị
  + các dịch vụ khác
```

Tổng này phải nằm trong giới hạn max_connections, đồng thời chừa chỗ cho hoạt động quản trị và các kết nối đặc biệt. Cũng cần xem xét proxy hoặc pooler bên ngoài nếu hệ thống có sử dụng.

Pool lớn hơn không tự động làm throughput cao hơn. Nếu PostgreSQL đã bão hòa CPU, I/O hoặc khóa, tăng số request đồng thời có thể làm hàng đợi và độ trễ tăng lên. Hãy bắt đầu với một kích thước có cơ sở, đo thời gian chờ lấy connection và tải database, sau đó điều chỉnh bằng thử nghiệm.

### 3.2 Cấu hình HikariCP thường dùng

Ví dụ cấu hình:

```java
HikariConfig config = new HikariConfig();

config.setJdbcUrl(System.getenv("DB_JDBC_URL"));
config.setUsername(System.getenv("DB_USERNAME"));
config.setPassword(System.getenv("DB_PASSWORD"));

config.setPoolName("orders-api-pool");
config.setMaximumPoolSize(12);
config.setMinimumIdle(2);

config.setConnectionTimeout(3000);
config.setValidationTimeout(1000);

config.setMaxLifetime(1500000);
config.setIdleTimeout(300000);

config.setLeakDetectionThreshold(20000);

config.addDataSourceProperty("ApplicationName", "orders-api");

HikariDataSource dataSource = new HikariDataSource(config);
```

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa | Cách lựa chọn |
|---|---|---|
| maximumPoolSize | Số connection tối đa trong pool | Cân đối với tổng ngân sách connection và tải PostgreSQL |
| minimumIdle | Số connection nhàn rỗi pool cố gắng duy trì | Chọn theo mức tải nền và khả năng tạo connection mới |
| connectionTimeout | Thời gian chờ lấy connection từ pool | Đặt theo SLA request; timeout này là chờ pool, không phải timeout truy vấn |
| validationTimeout | Thời gian tối đa cho kiểm tra connection | Phải nhỏ hơn connectionTimeout |
| maxLifetime | Tuổi tối đa của connection trong pool | Đặt thấp hơn giới hạn tuổi connection của proxy hoặc hạ tầng mạng nếu có |
| idleTimeout | Thời gian connection nhàn rỗi có thể được loại bỏ | Có ý nghĩa khi pool được phép co lại dưới mức tối đa |
| leakDetectionThreshold | Ngưỡng ghi log khi connection được mượn quá lâu | Dùng để phát hiện nơi quên đóng connection; đây là cảnh báo, không tự thu hồi connection |

HikariCP thường dùng JDBC4 Connection.isValid() để kiểm tra connection. Không cần đặt test query thủ công nếu driver hỗ trợ cơ chế này đúng cách. Chỉ cấu hình test query khi có yêu cầu tương thích cụ thể và đã hiểu chi phí của nó.

maxLifetime không cắt ngang connection đang được ứng dụng mượn. Pool loại connection sau khi nó được trả lại. Đặt maxLifetime thấp hơn giới hạn của proxy, load balancer hoặc firewall giúp giảm khả năng ứng dụng nhận lại một connection đã bị hạ tầng đóng âm thầm.

leakDetectionThreshold hữu ích khi điều tra leak, nhưng ngưỡng quá thấp có thể tạo cảnh báo giả cho các transaction hợp lệ chạy lâu. Cần xem stack trace và thời gian sử dụng connection trước khi kết luận có leak.

### 3.3 Phân biệt timeout của pool và timeout của database

Các timeout có phạm vi khác nhau:

- connectionTimeout của HikariCP giới hạn thời gian chờ mượn connection từ pool.
- connectTimeout của pgJDBC giới hạn thời gian thiết lập kết nối mạng tới PostgreSQL.
- socketTimeout của pgJDBC giới hạn thời gian chờ đọc dữ liệu từ socket; khi hết hạn, connection có thể không còn sử dụng được.
- Statement.setQueryTimeout() giới hạn thời gian thực thi câu lệnh theo JDBC driver.
- lock_timeout của PostgreSQL giới hạn thời gian chờ lấy khóa.
- statement_timeout của PostgreSQL giới hạn tổng thời gian thực thi một câu lệnh.

Không nên đặt mọi timeout cùng một giá trị. Hãy chọn từng ngưỡng theo tầng chịu trách nhiệm và yêu cầu phục hồi. Đặc biệt, socketTimeout không phải cách thay thế cho statement_timeout: timeout socket có thể làm ứng dụng mất connection trong khi chưa biết server đã hoàn tất transaction hay chưa.

## 4. Mượn và trả connection đúng cách

Dùng try-with-resources để bảo đảm các tài nguyên JDBC được đóng ngay cả khi câu lệnh phát sinh lỗi:

```java
String sql = """
    SELECT id, customer_name, total
    FROM orders
    WHERE id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        if (resultSet.next()) {
            long id = resultSet.getLong("id");
            String customerName = resultSet.getString("customer_name");
            BigDecimal total = resultSet.getBigDecimal("total");

            // Chuyển dữ liệu sang đối tượng ứng dụng.
        }
    }
}
```

Khi khối try kết thúc, ResultSet, PreparedStatement và Connection lần lượt được đóng. Với pooled DataSource, connection được trả về pool.

Một số nguyên tắc cần giữ:

- Mỗi thao tác hoặc đơn vị công việc lấy connection trong phạm vi cần thiết và đóng ngay khi hoàn tất.
- Không lưu Connection, Statement hoặc ResultSet vào biến static hay field dùng chung của service.
- Không truyền cùng một Connection cho nhiều thread chạy song song.
- Không giữ ResultSet mở trong khi thực hiện HTTP call hoặc chờ người dùng.
- Không trả connection về pool khi transaction vẫn đang ở trạng thái lỗi hoặc chưa được kết thúc.
- Đóng cả ResultSet và Statement, kể cả khi connection cuối cùng cũng sẽ được đóng.

Trong một request có nhiều câu lệnh cần cùng transaction, hãy lấy một connection và truyền nó cho các hàm repository bên trong đơn vị công việc đó. Không để mỗi repository tự lấy connection riêng nếu các thao tác phải commit hoặc rollback cùng nhau.

## 5. Tổ chức transaction bằng JDBC

Mặc định, JDBC connection thường ở chế độ auto-commit. Khi autoCommit = true, mỗi câu lệnh được thực hiện như một transaction riêng và tự commit khi hoàn tất. Cách này phù hợp với truy vấn độc lập, nhưng không đủ khi một nghiệp vụ cần nhiều thay đổi cùng thành công hoặc cùng thất bại.

Để quản lý transaction tường minh:

1. Lấy connection.
2. Gọi setAutoCommit(false).
3. Thực hiện các câu lệnh thuộc cùng đơn vị nghiệp vụ.
4. Gọi commit() khi tất cả thành công.
5. Gọi rollback() nếu có lỗi.
6. Đóng connection để trả về pool.

Ví dụ chuyển tiền giữa hai tài khoản:

```java
public void transfer(
        DataSource dataSource,
        long fromAccountId,
        long toAccountId,
        BigDecimal amount
) throws SQLException {

    if (amount.signum() <= 0) {
        throw new IllegalArgumentException("Amount must be positive");
    }

    String lockSql = """
        SELECT id, balance
        FROM accounts
        WHERE id IN (?, ?)
        ORDER BY id
        FOR UPDATE
        """;

    String debitSql = """
        UPDATE accounts
        SET balance = balance - ?
        WHERE id = ? AND balance >= ?
        """;

    String creditSql = """
        UPDATE accounts
        SET balance = balance + ?
        WHERE id = ?
        """;

    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            Map<Long, BigDecimal> balances = new HashMap<>();

            try (PreparedStatement lockStatement =
                         connection.prepareStatement(lockSql)) {
                lockStatement.setLong(1, fromAccountId);
                lockStatement.setLong(2, toAccountId);

                try (ResultSet resultSet = lockStatement.executeQuery()) {
                    while (resultSet.next()) {
                        balances.put(
                            resultSet.getLong("id"),
                            resultSet.getBigDecimal("balance")
                        );
                    }
                }
            }

            if (!balances.containsKey(fromAccountId)
                    || !balances.containsKey(toAccountId)) {
                throw new SQLException("Account not found");
            }

            try (PreparedStatement debit =
                         connection.prepareStatement(debitSql)) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromAccountId);
                debit.setBigDecimal(3, amount);

                if (debit.executeUpdate() != 1) {
                    throw new SQLException("Insufficient balance");
                }
            }

            try (PreparedStatement credit =
                         connection.prepareStatement(creditSql)) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toAccountId);

                if (credit.executeUpdate() != 1) {
                    throw new SQLException("Destination account not found");
                }
            }

            connection.commit();
        } catch (SQLException | RuntimeException | Error failure) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                failure.addSuppressed(rollbackFailure);
            }
            throw failure;
        }
    }
}
```

Ví dụ minh họa các nguyên tắc:

- Hai hàng được khóa trong cùng một transaction.
- Các hàng được lấy theo thứ tự id nhất quán để giảm nguy cơ deadlock khi nhiều giao dịch chuyển tiền đồng thời.
- Cập nhật số dư nguồn có điều kiện balance >= amount, tránh số dư âm do cạnh tranh.
- Số hàng được cập nhật được kiểm tra để phát hiện tài khoản không tồn tại hoặc không đủ tiền.
- Nếu bất kỳ bước nào thất bại, toàn transaction được rollback.

Đoạn mã giả định fromAccountId và toAccountId là hai tài khoản khác nhau. Ứng dụng thực tế nên kiểm tra điều kiện nghiệp vụ này trước khi mở transaction. Cũng cần xử lý trường hợp số dư, currency, hạn mức và quy tắc kế toán theo mô hình nghiệp vụ.

Với pool như HikariCP, khi connection được đóng, pool khôi phục các trạng thái JDBC được hỗ trợ về trạng thái ban đầu. Dù vậy, mã ứng dụng vẫn phải tự commit hoặc rollback rõ ràng trước khi đóng connection. Không dựa vào hành vi đóng connection để thay thế việc kết thúc transaction.

### 5.1 Không giữ transaction khi gọi dịch vụ bên ngoài

Giả sử một nghiệp vụ cập nhật đơn hàng rồi gọi dịch vụ thanh toán qua HTTP trong khi transaction vẫn mở. Nếu API thanh toán mất 10 giây, connection và các khóa liên quan có thể bị giữ trong suốt thời gian đó.

Nên tách quy trình thành các bước có ranh giới rõ ràng:

1. Mở transaction, ghi đơn hàng ở trạng thái PENDING và thông tin cần gửi đi.
2. Commit transaction.
3. Worker đọc công việc từ outbox hoặc hàng đợi và gọi dịch vụ thanh toán.
4. Mở transaction mới để cập nhật kết quả thanh toán.
5. Dùng mã nghiệp vụ hoặc idempotency key để xử lý an toàn khi worker chạy lại.

Mô hình outbox giúp lưu thay đổi nghiệp vụ và sự kiện cần phát đi trong cùng transaction. Worker có thể gửi sự kiện sau commit mà không phải giữ connection database trong khi chờ mạng.

## 6. Xử lý lỗi transaction và SQLException

JDBC biểu diễn lỗi database qua SQLException và các lớp con. Khi nhận lỗi, đừng chỉ đọc thông điệp. Hãy xem SQLSTATE, vendor error code, chuỗi exception và ngữ cảnh transaction.

Các phương thức hữu ích:

- getSQLState(): mã SQLSTATE chuẩn hoặc do driver cung cấp.
- getErrorCode(): mã lỗi riêng của database.
- getNextException(): lỗi tiếp theo trong chuỗi exception, thường hữu ích với batch.
- getCause(): nguyên nhân gốc nếu exception được bọc.
- getMessage(): thông điệp mô tả, hữu ích cho log nội bộ nhưng không nên hiển thị nguyên văn cho người dùng cuối.

Ví dụ ghi log thông tin lỗi:

```java
catch (SQLException exception) {
    logger.error(
        "Database operation failed: sqlState={}, vendorCode={}",
        exception.getSQLState(),
        exception.getErrorCode(),
        exception
    );
    throw exception;
}
```

Không ghi password, token, dữ liệu cá nhân hoặc toàn bộ payload nhạy cảm vào log. Query text và tham số cũng cần được xử lý theo chính sách bảo vệ dữ liệu của hệ thống.

### 6.1 SQLSTATE thường gặp trong PostgreSQL

| SQLSTATE | Tên lỗi | Tình huống thường gặp | Hướng xử lý |
|---|---|---|---|
| 23505 | unique_violation | Trùng giá trị khóa duy nhất | Kiểm tra nghiệp vụ; có thể trả lỗi xung đột hoặc dùng upsert nếu phù hợp |
| 23503 | foreign_key_violation | Tham chiếu tới bản ghi không tồn tại hoặc xóa bản ghi còn được tham chiếu | Kiểm tra thứ tự thao tác và tính hợp lệ của quan hệ |
| 23502 | not_null_violation | Ghi NULL vào cột bắt buộc | Sửa dữ liệu đầu vào hoặc quy tắc mặc định |
| 23514 | check_violation | Giá trị vi phạm CHECK constraint | Kiểm tra điều kiện nghiệp vụ và dữ liệu |
| 40001 | serialization_failure | Transaction không thể hoàn tất ở mức cô lập yêu cầu | Rollback và cân nhắc retry toàn transaction |
| 40P01 | deadlock_detected | Hai hay nhiều transaction chờ khóa theo chu trình | Rollback và retry có giới hạn; sửa thứ tự lấy khóa |
| 55P03 | lock_not_available | Không lấy được khóa theo chế độ không chờ hoặc timeout liên quan | Xem chính sách chờ, timeout và tải cạnh tranh |
| 57014 | query_canceled | Câu lệnh bị hủy, có thể do statement_timeout hoặc cancel từ bên ngoài | Xác định nguồn hủy và điều chỉnh truy vấn hoặc timeout |
| 25P02 | in_failed_sql_transaction | Transaction đã lỗi trước đó nhưng ứng dụng vẫn gửi câu lệnh | Rollback hoặc rollback về savepoint |
| 08003 | connection_does_not_exist | Connection không còn tồn tại | Loại connection hỏng khỏi luồng xử lý; lấy connection mới |
| 08006 | connection_failure | Kết nối bị lỗi trong lúc giao tiếp | Điều tra mạng/server; xác định transaction có thể đã commit hay chưa |

SQLSTATE thường được chia thành hai ký tự đầu là class và ba ký tự sau là condition. Ví dụ, class 23 là lỗi ràng buộc toàn vẹn; class 40 là lỗi transaction rollback; class 08 là lỗi kết nối.

Không nên dựa duy nhất vào nội dung thông điệp để phân loại lỗi vì thông điệp có thể thay đổi theo phiên bản hoặc ngôn ngữ. Dùng SQLSTATE để quyết định nhánh xử lý; dùng message và log để hỗ trợ điều tra.

### 6.2 Transaction PostgreSQL chuyển sang trạng thái lỗi

Trong một transaction tường minh, nếu một câu lệnh gặp lỗi như vi phạm unique constraint, PostgreSQL đánh dấu transaction ở trạng thái lỗi. Các câu lệnh tiếp theo thường nhận lỗi 25P02 cho đến khi transaction được rollback.

Ví dụ:

```sql
BEGIN;

INSERT INTO customers(id, email)
VALUES (10, 'a@example.com');

-- Giả sử email đã tồn tại và INSERT phát sinh 23505.

SELECT count(*) FROM customers;
-- Lỗi 25P02: transaction hiện ở trạng thái failed.

ROLLBACK;
```

Ứng dụng phải rollback trước khi sử dụng transaction tiếp theo. Chỉ bắt exception ở Java rồi tiếp tục gửi câu SQL mới trên cùng transaction là sai.

### 6.3 Dùng Savepoint khi cần xử lý lỗi cục bộ

Savepoint cho phép rollback một phần transaction. Điều này hữu ích khi một phần công việc có thể thất bại nhưng phần còn lại vẫn được phép tiếp tục theo nghiệp vụ.

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        insertOrderHeader(connection);

        Savepoint beforeOptionalItem = connection.setSavepoint();

        try {
            insertOptionalItem(connection);
            connection.releaseSavepoint(beforeOptionalItem);
        } catch (SQLException itemFailure) {
            if ("23505".equals(itemFailure.getSQLState())) {
                connection.rollback(beforeOptionalItem);
                connection.releaseSavepoint(beforeOptionalItem);
                logger.info("Optional item already exists; skipped");
            } else {
                throw itemFailure;
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException | Error failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Khi rollback về savepoint, các thay đổi sau savepoint bị hủy và transaction có thể tiếp tục. Chỉ xử lý các SQLSTATE đã được nghiệp vụ cho phép; không bắt mọi SQLException rồi bỏ qua, vì có thể đó là lỗi mất kết nối, lỗi schema hoặc lỗi nghiêm trọng khác.

Một số constraint có thể được khai báo DEFERRABLE và chỉ được kiểm tra tại thời điểm commit. Vì vậy, một câu lệnh có thể chạy thành công nhưng commit() vẫn thất bại. Luôn đặt commit trong vùng xử lý lỗi của transaction.

## 7. Isolation level và tính nhất quán

Isolation level xác định mức độ một transaction nhìn thấy thay đổi từ transaction khác. JDBC cung cấp các hằng số như TRANSACTION_READ_COMMITTED, TRANSACTION_REPEATABLE_READ và TRANSACTION_SERIALIZABLE.

PostgreSQL mặc định dùng READ COMMITTED. Mỗi câu lệnh trong transaction có snapshot tại thời điểm câu lệnh bắt đầu. Vì vậy, hai lần SELECT trong cùng transaction có thể nhìn thấy dữ liệu đã commit ở giữa hai lần đọc.

| Isolation level | Hành vi tổng quát trong PostgreSQL | Lưu ý |
|---|---|---|
| READ COMMITTED | Mỗi câu lệnh đọc snapshot mới nhất đã commit tại thời điểm câu lệnh bắt đầu | Mặc định; phù hợp với nhiều ứng dụng CRUD |
| REPEATABLE READ | Các câu lệnh trong transaction dùng cùng snapshot | Có thể phát sinh serialization failure khi xung đột cập nhật |
| SERIALIZABLE | PostgreSQL theo dõi phụ thuộc để bảo đảm kết quả tương đương một thứ tự tuần tự | Có thể từ chối transaction bằng SQLSTATE 40001; ứng dụng phải retry |

Thiết lập isolation level trước khi thực hiện câu lệnh trong transaction:

```java
try (Connection connection = dataSource.getConnection()) {
    connection.setTransactionIsolation(
        Connection.TRANSACTION_SERIALIZABLE
    );
    connection.setAutoCommit(false);

    try {
        performBusinessOperation(connection);
        connection.commit();
    } catch (SQLException | RuntimeException | Error failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Không tăng isolation level chỉ để “an toàn hơn” mà không hiểu workload. SERIALIZABLE có thể làm tăng số transaction phải retry; ứng dụng cần thiết kế lại retry và bảo đảm thao tác có thể chạy lại. Với một số nghiệp vụ, khóa tường minh hoặc câu lệnh cập nhật có điều kiện đơn giản hơn và hiệu quả hơn.

Isolation level là thuộc tính của connection/transaction. Khi dùng pool, thiết lập này cần được khôi phục hoặc được quản lý nhất quán để không rò rỉ sang request tiếp theo.

## 8. PreparedStatement, kiểu dữ liệu và an toàn truy vấn

Dùng PreparedStatement để truyền giá trị:

```java
String sql = """
    SELECT id, status
    FROM orders
    WHERE customer_id = ?
      AND created_at >= ?
    ORDER BY created_at DESC
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);
    statement.setTimestamp(2, Timestamp.from(startInstant));

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Đọc từng dòng kết quả.
        }
    }
}
```

Không ghép trực tiếp dữ liệu đầu vào vào chuỗi SQL. Ví dụ sau có nguy cơ SQL injection:

```java
String sql = "SELECT * FROM users WHERE email = '" + email + "'";
```

Hãy dùng placeholder và setter tương ứng. Placeholder ? chỉ đại diện cho giá trị; không thể dùng nó thay tên bảng, tên cột, từ khóa hoặc hướng sắp xếp. Nếu cần tạo SQL động cho identifier, hãy chọn từ danh sách cho phép được định nghĩa trong mã ứng dụng.

Với PostgreSQL, kiểu Java và kiểu SQL cần được ánh xạ phù hợp:

| Kiểu Java | Kiểu PostgreSQL thường dùng | Ghi chú |
|---|---|---|
| long / Long | bigint | Dùng setLong() và getLong() |
| int / Integer | integer | Dùng setInt() và getInt() |
| BigDecimal | numeric / decimal | Tránh dùng double cho tiền tệ |
| String | text / varchar | Có thể dùng setString() |
| boolean | boolean | Xử lý NULL riêng nếu cột nullable |
| LocalDate | date | Dùng API JDBC hỗ trợ Java time hoặc chuyển đổi phù hợp |
| LocalDateTime | timestamp without time zone | Không mang thông tin múi giờ |
| OffsetDateTime | timestamp with time zone (timestamptz) | PostgreSQL lưu thời điểm theo UTC; offset gốc không được giữ như một thuộc tính riêng |
| UUID | uuid | pgJDBC hỗ trợ ánh xạ UUID |
| byte[] | bytea | Dùng cho dữ liệu nhị phân |

Với timestamp, cần thống nhất ý nghĩa thời gian trong hệ thống. timestamp without time zone là ngày giờ địa phương không mang timezone; timestamptz biểu diễn một thời điểm và được PostgreSQL chuẩn hóa nội bộ. Không dùng lẫn hai loại mà không có quy ước rõ ràng.

Đối với giá trị SQL NULL, các phương thức getter dạng primitive như getLong() trả về 0 khi giá trị là NULL. Hãy gọi wasNull() ngay sau getter hoặc dùng kiểu object phù hợp để phân biệt NULL với giá trị 0.

## 9. Batch và truy vấn dữ liệu lớn

### 9.1 Batch insert/update

Khi cần ghi nhiều dòng cùng một dạng câu lệnh, batching giảm số lần trao đổi giữa ứng dụng và database:

```java
String sql = """
    INSERT INTO inventory(product_id, quantity)
    VALUES (?, ?)
    ON CONFLICT (product_id)
    DO UPDATE SET quantity = EXCLUDED.quantity
    """;

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        for (InventoryItem item : items) {
            statement.setLong(1, item.productId());
            statement.setInt(2, item.quantity());
            statement.addBatch();
        }

        int[] counts = statement.executeBatch();
        connection.commit();
    } catch (SQLException | RuntimeException | Error failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

executeBatch() có thể trả về số dòng cập nhật hoặc các giá trị đặc biệt như SUCCESS_NO_INFO; driver cũng có thể ném BatchUpdateException kèm kết quả một phần. Nếu batch thuộc một transaction nguyên tử, cần rollback khi có lỗi và kiểm tra chuỗi exception để biết câu lệnh nào thất bại.

Batch quá lớn có thể làm tăng bộ nhớ, thời gian transaction và thời gian giữ khóa. Chia lô theo kích thước phù hợp với dữ liệu, mạng và giới hạn nghiệp vụ.

### 9.2 Đọc dữ liệu lớn bằng fetch size

Với pgJDBC, mặc định driver có thể tải toàn bộ kết quả truy vấn về client. Khi đọc hàng trăm nghìn hoặc hàng triệu dòng, điều này có thể tiêu tốn bộ nhớ lớn.

Có thể yêu cầu driver đọc theo từng đợt bằng fetch size:

```java
String sql = "SELECT id, payload FROM event_log ORDER BY id";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement statement = connection.prepareStatement(sql)) {
        statement.setFetchSize(500);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                processEvent(resultSet.getLong("id"),
                             resultSet.getString("payload"));
            }
        }

        connection.commit();
    } catch (SQLException | RuntimeException | Error failure) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Cơ chế cursor/fetch của pgJDBC cần transaction tường minh; ví dụ đặt autoCommit thành false trước khi chạy truy vấn. Điều này đồng nghĩa transaction và connection có thể được giữ trong suốt thời gian xử lý toàn bộ kết quả. Hãy tránh thực hiện công việc ngoài database hoặc xử lý từng dòng quá chậm trong khi cursor còn mở. Nếu xử lý kéo dài, cân nhắc phân trang theo khóa (keyset pagination) để mỗi đợt dùng transaction ngắn.

## 10. Retry an toàn khi có lỗi cạnh tranh

Một số lỗi PostgreSQL là lỗi tạm thời do cạnh tranh transaction:

- 40P01: deadlock detected.
- 40001: serialization failure.

Có thể retry các lỗi này, nhưng cần tuân thủ các nguyên tắc:

1. Rollback transaction hiện tại.
2. Bắt đầu transaction mới trên connection hợp lệ.
3. Chạy lại toàn bộ đơn vị nghiệp vụ từ đầu.
4. Giới hạn số lần thử.
5. Dùng backoff tăng dần và jitter để các client không retry đồng loạt.
6. Ghi log SQLSTATE, số lần thử và mã nghiệp vụ để theo dõi.

Ví dụ bộ nhận diện lỗi retry:

```java
private boolean isRetryableTransactionError(SQLException exception) {
    String sqlState = exception.getSQLState();

    return "40P01".equals(sqlState)
        || "40001".equals(sqlState);
}
```

Một vòng retry cần tạo transaction mới mỗi lần. Không retry trực tiếp trên transaction đã bị đánh dấu lỗi.

```java
public <T> T executeWithRetry(
        int maxAttempts,
        SqlWork<T> work
) throws SQLException {

    SQLException lastFailure = null;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                T result = work.execute(connection);
                connection.commit();
                return result;
            } catch (SQLException | RuntimeException | Error failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }

                if (failure instanceof SQLException sqlException
                        && isRetryableTransactionError(sqlException)) {
                    lastFailure = sqlException;
                } else {
                    throw failure;
                }
            }
        }

        if (attempt < maxAttempts) {
            sleepWithBackoffAndJitter(attempt);
        }
    }

    throw lastFailure;
}
```

Đây là khung minh họa; SqlWork, sleepWithBackoffAndJitter và chính sách interrupt cần được triển khai phù hợp với ứng dụng. Trong mã production, cần bảo đảm retry không vượt quá deadline của request và không làm mất trạng thái interrupt của thread.

**Không retry mọi SQLException.** Vi phạm unique constraint, sai kiểu dữ liệu, thiếu bảng hoặc lỗi quyền thường không tự biến mất sau một khoảng chờ. Chỉ retry những lỗi đã được phân loại là tạm thời và có thể phục hồi.

### 10.1 Rủi ro khi mất kết nối trong lúc commit

Trường hợp nguy hiểm là ứng dụng gửi COMMIT nhưng mất kết nối trước khi nhận được phản hồi. Khi đó, ứng dụng không biết chắc server đã commit hay chưa. Gọi lại toàn bộ thao tác có thể ghi trùng hoặc thực hiện nghiệp vụ hai lần.

Không thể giải quyết tình huống này bằng cách retry mù. Hãy thiết kế thao tác có idempotency key hoặc mã yêu cầu duy nhất được lưu trong cùng transaction với dữ liệu nghiệp vụ. Khi client thử lại, server kiểm tra mã đó để trả kết quả đã ghi nhận thay vì thực hiện lại thay đổi.

Với nghiệp vụ cần phát sự kiện, transactional outbox giúp ghi sự kiện trong cùng transaction. Worker gửi sự kiện có thể chạy lại; consumer cần idempotent để xử lý trùng an toàn.

## 11. Quản lý trạng thái session khi dùng pool

Connection pool tái sử dụng cùng một session PostgreSQL qua nhiều request. Các trạng thái không được reset có thể ảnh hưởng request sau.

Những thiết lập cần quan tâm:

- autoCommit
- transaction isolation level
- read-only mode
- schema/catalog nếu ứng dụng thay đổi
- network timeout
- session variables hoặc SET ở PostgreSQL
- role, search path và các thiết lập phiên khác

HikariCP có thể theo dõi và khôi phục một số trạng thái JDBC tiêu chuẩn khi connection được trả về. Tuy nhiên, các câu lệnh SQL như SET search_path, SET statement_timeout hoặc SET application_name có thể thay đổi trạng thái phía server mà pool không tự hiểu đầy đủ trong mọi trường hợp.

Nếu một thiết lập chỉ áp dụng cho một transaction, ưu tiên SET LOCAL sau khi transaction đã bắt đầu:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '15s';

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42;

COMMIT;
```

SET LOCAL tự hết hiệu lực khi transaction kết thúc. Nếu dùng SET ở cấp session, phải có cơ chế reset rõ ràng trước khi trả connection về pool, hoặc cấu hình mặc định ở cấp role/database để mọi connection nhận cùng chính sách.

Không để một request tùy ý thay đổi search_path hoặc role rồi trả connection về pool mà không khôi phục. Đây vừa là lỗi cách ly request vừa có thể tạo rủi ro bảo mật.

## 12. Theo dõi pool và database trong production

Khi ứng dụng chậm, cần quan sát cả pool ở phía Java lẫn session ở PostgreSQL. Chỉ xem một phía có thể dẫn đến kết luận sai.

### 12.1 Chỉ số phía pool

Với HikariCP, nên theo dõi các số liệu tương đương:

- **Active connections:** số connection đang được mượn.
- **Idle connections:** số connection sẵn sàng được mượn.
- **Total connections:** tổng connection hiện có.
- **Threads awaiting connection:** số thread đang chờ pool cấp connection.
- **Acquisition time:** thời gian từ lúc gọi getConnection() đến khi nhận được connection.
- **Usage time:** thời gian connection được giữ trước khi trả lại pool.
- **Timeout count:** số lần không lấy được connection trong thời hạn.

Nếu active luôn bằng maximum, idle bằng 0 và số thread chờ tăng, pool có thể đang thiếu connection hoặc connection bị giữ quá lâu. Hãy tìm nơi giữ connection, transaction dài, truy vấn chậm hoặc tác vụ xử lý ResultSet lâu.

Nếu pool còn idle nhưng request vẫn chậm, nguyên nhân có thể nằm ở SQL, network, thread pool của ứng dụng hoặc dịch vụ khác.

### 12.2 Nhận diện connection từ PostgreSQL

Đặt ApplicationName khi cấu hình pgJDBC để quan sát session:

```sql
SELECT
    pid,
    application_name,
    usename,
    client_addr,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

Có thể lọc theo application:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    clock_timestamp() - xact_start AS transaction_age,
    left(query, 500) AS query
FROM pg_stat_activity
WHERE application_name = 'orders-api'
ORDER BY xact_start NULLS LAST;
```

Các trạng thái đáng chú ý:

- active: backend đang thực thi câu lệnh; cần xem wait event để biết có đang chờ hay không.
- idle: connection rảnh, không có transaction mở.
- idle in transaction: transaction còn mở dù backend không chạy câu lệnh; có thể giữ khóa và snapshot cũ.
- idle in transaction (aborted): transaction đã lỗi và chưa được rollback.

Một pool bình thường có thể giữ nhiều session ở trạng thái idle. Điều đó không có nghĩa connection bị rò rỉ. Cần đối chiếu số session với cấu hình pool và trạng thái pool metrics.

### 12.3 Phát hiện connection leak

Dấu hiệu thường gặp:

- Active connections tăng dần nhưng không giảm.
- Pool cạn dù lượng request không tăng tương ứng.
- Thread chờ connection tăng.
- HikariCP ghi cảnh báo connection bị giữ lâu.
- Stack trace cảnh báo trỏ đến đường code không đóng tài nguyên.

Các nguyên nhân điển hình là thiếu try-with-resources, nhánh exception bỏ qua close(), ResultSet được giữ trong object sống lâu hoặc một tác vụ giữ connection trong lúc gọi dịch vụ bên ngoài.

Leak detection chỉ hỗ trợ xác định nơi mượn connection. Nó không tự đóng connection bị leak. Sau khi tìm được stack trace, sửa vòng đời tài nguyên và xác minh bằng metrics sau triển khai.

## 13. Kiểm thử tích hợp transaction và pool

Kiểm thử với database thật rất quan trọng vì hành vi transaction, khóa, SQLSTATE và kiểu dữ liệu của PostgreSQL có thể khác database giả lập hoặc H2.

Các tình huống nên kiểm thử:

1. **Commit thành công:** thay đổi được nhìn thấy từ connection khác sau commit.
2. **Rollback:** khi câu lệnh thứ hai thất bại, thay đổi của câu lệnh thứ nhất không còn.
3. **Constraint violation:** ứng dụng nhận đúng SQLSTATE và rollback transaction.
4. **Transaction failed:** sau lỗi, câu lệnh tiếp theo không chạy thành công cho đến khi rollback hoặc rollback về savepoint.
5. **Deadlock:** hai transaction khóa hai hàng theo thứ tự ngược nhau; ứng dụng nhận diện 40P01 và retry đúng đơn vị công việc.
6. **Serialization failure:** transaction ở isolation level cao có thể nhận 40001; retry có giới hạn.
7. **Pool reuse:** trạng thái auto-commit, isolation và thiết lập session không rò rỉ sang request tiếp theo.
8. **Connection leak:** mọi đường thành công và lỗi đều trả connection về pool.
9. **Network failure:** ứng dụng xử lý mất kết nối và trạng thái commit không xác định bằng idempotency.
10. **Shutdown:** DataSource được đóng và pool giải phóng tài nguyên khi ứng dụng dừng.

Test cạnh tranh cần điều khiển thứ tự thực thi bằng latch/barrier hoặc cơ chế đồng bộ của test. Không dựa vào Thread.sleep() đơn thuần để tạo deadlock vì thứ tự chạy không ổn định.

## 14. Một số lỗi tích hợp thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Connection is not available, request timed out | Pool hết connection, connection bị giữ lâu hoặc database không nhận thêm kết nối | Xem active/idle/pending, acquisition time và pg_stat_activity |
| current transaction is aborted | Một câu lệnh trước đó đã lỗi và chưa rollback | Tìm lỗi SQLSTATE đầu tiên; rollback hoặc dùng savepoint đúng cách |
| duplicate key value violates unique constraint | Hai request cùng tạo một khóa duy nhất hoặc dữ liệu đầu vào bị trùng | Kiểm tra SQLSTATE 23505; dùng upsert hoặc xử lý conflict theo nghiệp vụ |
| deadlock detected | Transaction khóa tài nguyên theo thứ tự khác nhau | Đọc log deadlock, chuẩn hóa thứ tự khóa và retry toàn transaction |
| canceling statement due to statement timeout | Câu lệnh vượt statement_timeout | Xem query plan, tải, lock wait và ngưỡng timeout |
| Connection reset hoặc socket timeout | Mạng, proxy, server restart hoặc timeout phía driver | Xác định connection có thể tái sử dụng không; lấy connection mới và xử lý commit uncertainty |
| Nhiều session idle in transaction | Ứng dụng không commit/rollback hoặc giữ transaction khi xử lý việc ngoài DB | Tìm đường code mở transaction và cấu hình idle_in_transaction_session_timeout |
| Truy vấn chạy chậm dù pool còn connection | SQL, index, lock hoặc tài nguyên server | Xem pg_stat_activity, wait event, EXPLAIN và metrics PostgreSQL |

Không nên xử lý tất cả lỗi bằng cách tăng pool size hoặc tăng timeout. Cần xác định tầng phát sinh lỗi trước khi điều chỉnh.

## 15. Quy trình xây dựng một luồng JDBC an toàn

Một quy trình triển khai có thể áp dụng cho service Java:

**Bước 1 — Khởi tạo DataSource.** Tạo một pool dùng chung ở phạm vi ứng dụng. Đọc URL, username và password từ cấu hình an toàn; đặt ApplicationName.

**Bước 2 — Định nghĩa ranh giới transaction.** Xác định những thay đổi nào phải commit cùng nhau. Lấy một connection cho toàn đơn vị nghiệp vụ.

**Bước 3 — Dùng PreparedStatement.** Truyền dữ liệu qua placeholder, đóng Statement và ResultSet bằng try-with-resources.

**Bước 4 — Kết thúc transaction rõ ràng.** Commit khi thành công; rollback khi có lỗi; không để transaction mở khi trả connection về pool.

**Bước 5 — Phân loại lỗi.** Dùng SQLSTATE để phân biệt lỗi dữ liệu, lỗi cạnh tranh, lỗi kết nối và lỗi timeout. Không retry các lỗi không thể tự phục hồi.

**Bước 6 — Retry có giới hạn.** Chỉ retry lỗi transaction tạm thời như deadlock hoặc serialization failure; mỗi lần thử phải dùng transaction mới và bảo đảm idempotency.

**Bước 7 — Đo lường.** Theo dõi metrics của pool, connection acquisition time, thời gian giữ connection, transaction age và wait event trong PostgreSQL.

**Bước 8 — Kiểm thử lỗi.** Kiểm thử rollback, deadlock, constraint, connection loss, pool reuse và shutdown bằng PostgreSQL thật.

## 16. Ghi nhớ

- Dùng DataSource và một connection pool dùng chung trong ứng dụng server; không tạo pool theo request.
- Luôn đóng Connection, Statement và ResultSet bằng try-with-resources. Với pooled connection, close() trả connection về pool.
- Transaction cần một connection xuyên suốt; commit hoặc rollback rõ ràng trước khi trả connection.
- PostgreSQL đánh dấu transaction ở trạng thái lỗi sau một câu lệnh thất bại; cần rollback hoặc rollback về savepoint trước khi tiếp tục.
- Dùng SQLSTATE để phân loại lỗi. 40P01 và 40001 có thể retry toàn transaction với số lần giới hạn.
- Mất kết nối trong lúc commit tạo ra kết quả không xác định; dùng idempotency key và cơ chế đối soát để tránh xử lý trùng.
- Chọn pool size theo ngân sách connection toàn hệ thống và số liệu đo thực tế.
- Phân biệt timeout chờ pool, timeout kết nối mạng, timeout câu lệnh và timeout chờ khóa.
- Theo dõi metrics phía pool cùng pg_stat_activity để tìm connection leak, transaction dài và lock wait.
- Kiểm thử tích hợp với PostgreSQL thật để xác nhận transaction, locking và hành vi driver đúng như mong đợi.


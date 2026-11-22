# Connect timeout, read timeout, query timeout và hủy câu lệnh trong Oracle JDBC

## 1. Vì sao cần nhiều loại timeout?

Ứng dụng Java kết nối Oracle Database qua JDBC phải chờ nhiều giai đoạn khác nhau: lấy connection từ pool, mở kết nối mạng, xác thực session, gửi SQL, chờ database xử lý, nhận dữ liệu và đọc hết `ResultSet`. Mỗi giai đoạn có kiểu chờ và nguyên nhân lỗi riêng.

Nếu chỉ đặt một timeout chung, ứng dụng có thể vẫn treo ở giai đoạn khác. Ví dụ:
- Pool hết connection, request chờ rất lâu trước khi JDBC driver được gọi.
- TCP hoặc listener không phản hồi khi tạo physical connection.
- Database đang chạy truy vấn nhưng client chờ socket đọc dữ liệu.
- Một câu SQL chạy quá lâu và cần được hủy.
- Người dùng hủy request nhưng câu SQL vẫn tiếp tục ở database.
- Một lần đọc dữ liệu lớn hoặc LOB bị chậm sau khi câu lệnh đã trả về cursor.

Bài học thuộc module **Database Engine Relational Oracle**, chương **Oracle JDBC**, tập trung vào **connect timeout, read timeout, query timeout và hủy câu lệnh**.

Cần phân biệt các lớp:

| Loại timeout | Kiểm soát điều gì? | Ví dụ cơ chế |
|---|---|---|
| Pool acquisition timeout | Thời gian chờ lấy connection từ pool | Cấu hình của connection pool |
| Connect timeout | Thời gian mở kết nối tới database/listener | Oracle Net connect descriptor, JDBC connection properties |
| Read/socket timeout | Thời gian chờ dữ liệu từ socket | `oracle.jdbc.ReadTimeout` |
| Query timeout | Thời gian cho phép statement thực thi | `Statement.setQueryTimeout()` |
| Call timeout | Thời gian tối đa cho một database round-trip | `OracleConnection.setCallTimeout()` |
| Network timeout | Thời gian JDBC request chờ database phản hồi trước khi connection bị đánh dấu không dùng được | `Connection.setNetworkTimeout()` |
| Application deadline | Tổng thời gian caller chờ toàn bộ request | API/service layer |

Các timeout này không thay thế nhau. Một cấu hình đúng phải xác định timeout ở từng tầng, liên kết chúng với deadline tổng và có quy trình xử lý connection/transaction sau khi timeout.

## 2. Vòng đời một request JDBC

Một request thường đi qua trình tự:

```text
HTTP / application request
          |
          v
Chờ connection từ pool
          |
          v
Mở physical connection nếu pool cần
          |
          v
Oracle Net / TCP / listener / service
          |
          v
Gửi SQL và bind parameters
          |
          v
Oracle parse / execute / fetch
          |
          v
Nhận kết quả qua socket
          |
          v
Đọc ResultSet / LOB / batch result
          |
          v
Commit hoặc rollback transaction
          |
          v
Trả response cho caller
```

Mỗi bước có thể chờ. Một request bị timeout ở tầng HTTP không có nghĩa database đã dừng câu SQL. Một socket read timeout cũng không đồng nghĩa transaction đã rollback.

Thiết kế timeout phải trả lời:
1. Request được phép chờ tổng cộng bao lâu?
2. Mỗi lần lấy connection hoặc kết nối mới được chờ bao lâu?
3. Câu SQL được phép chạy bao lâu?
4. Nếu không nhận phản hồi, connection còn sử dụng được không?
5. Transaction có thể đã commit hay chưa?
6. Ai chịu trách nhiệm hủy statement và giải phóng tài nguyên?

## 3. Pool acquisition timeout: chờ connection không phải connect timeout

Ứng dụng thường gọi:

```java
Connection connection = dataSource.getConnection();
```

Nếu dùng connection pool, lời gọi có thể phải chờ một connection rảnh. Đây là **pool acquisition timeout**. Trong lúc pool chưa cấp connection, JDBC driver có thể chưa thực hiện bất kỳ kết nối mạng mới nào.

Các nguyên nhân thường gặp:
- Tất cả connection đang được request khác mượn.
- Transaction giữ connection quá lâu.
- Một số connection bị treo hoặc chưa được phát hiện là hỏng.
- Pool có giới hạn `maximumPoolSize` nhỏ hơn concurrency thực tế.
- Request giữ connection trong lúc gọi API ngoài hoặc ngủ chờ retry.
- Connection leak do không đóng `Connection`, `Statement` hoặc `ResultSet`.

### 3.1. Cấu hình ở pool

Tên thuộc tính tùy thư viện. Ví dụ với HikariCP, `connectionTimeout` giới hạn thời gian chờ mượn connection từ pool:

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl(jdbcUrl);
config.setUsername(username);
config.setPassword(passwordFromSecretProvider);

config.setMaximumPoolSize(20);
config.setConnectionTimeout(2_000);
config.setValidationTimeout(1_000);
```

Các con số chỉ minh họa. `connectionTimeout` của pool không phải thời gian tạo socket đến Oracle. Khi pool cần tạo physical connection mới, driver còn có connect timeout riêng.

### 3.2. Không tăng pool size để che timeout

Nếu pool thường xuyên hết connection, hãy kiểm tra:
- Số request đồng thời.
- Thời gian giữ connection.
- Transaction duration.
- Slow SQL.
- Connection leak.
- Database session/process limit.
- Các request chờ dịch vụ bên ngoài trong khi vẫn giữ connection.

Tăng pool size có thể làm database nhận quá nhiều session và tăng contention. Hãy sửa nguyên nhân giữ connection lâu trước khi tăng giới hạn.

### 3.3. Trả connection trong mọi nhánh

Dùng try-with-resources để bảo đảm JDBC resource được đóng:

```java
try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(
             "SELECT order_id FROM app.orders WHERE order_id = ?")) {

    statement.setLong(1, orderId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long id = resultSet.getLong(1);
        }
    }
}
```

Khi dùng pool, `Connection.close()` thường trả logical connection về pool. Nó không nhất thiết đóng physical socket. Connection bị hỏng phải được driver/pool đánh dấu và loại bỏ theo cơ chế tương ứng.

## 4. Connect timeout: giới hạn thời gian mở kết nối Oracle

Connect timeout giới hạn thời gian client chờ thiết lập kết nối tới Oracle. Giai đoạn này có thể bao gồm các bước khác nhau:
- Phân giải hostname/DNS.
- Thiết lập TCP connection.
- Kết nối tới listener.
- Listener tìm service/handler phù hợp.
- Database tạo session và xác thực user.
- Các bước TLS/wallet nếu cấu hình.

Một timeout ở một bước không nhất thiết giới hạn toàn bộ thời gian `DataSource.getConnection()` nếu pool, DNS hoặc retry có thời gian riêng.

### 4.1. Oracle Net connect descriptor

Có thể đặt timeout trong connect descriptor:

```text
jdbc:oracle:thin:@(DESCRIPTION=
  (CONNECT_TIMEOUT=5)
  (TRANSPORT_CONNECT_TIMEOUT=3)
  (RETRY_COUNT=1)
  (ADDRESS=
    (PROTOCOL=TCP)
    (HOST=db.example.internal)
    (PORT=1521)
  )
  (CONNECT_DATA=
    (SERVICE_NAME=orders.example.internal)
  )
)
```

Trong ví dụ:
- `TRANSPORT_CONNECT_TIMEOUT` giới hạn thời gian thiết lập transport connection theo semantics Oracle Net.
- `CONNECT_TIMEOUT` giới hạn thời gian kết nối theo mô tả Oracle Net.
- `RETRY_COUNT` điều khiển số lần thử lại địa chỉ/kết nối theo cấu hình hỗ trợ.

Đơn vị, phạm vi áp dụng và tương tác giữa các tham số cần kiểm tra theo Oracle Database/Oracle Net/Oracle JDBC release đang dùng. Nếu có nhiều địa chỉ trong `ADDRESS_LIST`, nhiều retry hoặc nhiều service, tổng thời gian có thể lớn hơn một giá trị timeout đơn lẻ.

### 4.2. Oracle JDBC connection properties

Oracle JDBC Thin Driver hỗ trợ các thuộc tính kết nối Oracle Net. Một cách truyền thuộc tính qua `Properties`:

```java
Properties properties = new Properties();
properties.setProperty("user", username);
properties.setProperty("password", passwordFromSecretProvider);

// Giá trị minh họa theo đơn vị milliseconds của JDBC property.
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "5000");

Connection connection =
        DriverManager.getConnection(jdbcUrl, properties);
```

Không đặt password thật trong source code, log hoặc command line. Lấy credential từ secret manager/wallet theo kiến trúc triển khai.

Cần phân biệt thuộc tính JDBC `oracle.net.CONNECT_TIMEOUT` với `CONNECT_TIMEOUT` trong Oracle Net connect descriptor; cách biểu diễn và đơn vị không nhất thiết giống nhau. Đối chiếu tài liệu driver đang triển khai trước khi cấu hình.

### 4.3. DriverManager login timeout

JDBC có API:

```java
DriverManager.setLoginTimeout(5);
```

Giá trị là giây. Đây là timeout đăng nhập ở mức `DriverManager`; nó là cấu hình toàn cục cho các kết nối do DriverManager quản lý và có thể ảnh hưởng các datasource khác trong cùng JVM.

Với ứng dụng dùng nhiều database hoặc pool, ưu tiên cấu hình timeout cụ thể ở datasource/driver/pool thay vì thay đổi một giá trị global mà không đánh giá tác động.

### 4.4. DataSource login timeout

JDBC `DataSource` có API `setLoginTimeout(int seconds)` trong các triển khai hỗ trợ. Đây là một cơ chế ở lớp datasource; driver và datasource cụ thể quyết định cách áp dụng.

Không nhầm nó với thời gian chờ pool cấp connection. Hãy kiểm tra tài liệu của pool và Oracle datasource đang sử dụng.

### 4.5. Các lỗi connect thường gặp

| Lỗi | Hướng điều tra |
|---|---|
| `ORA-12170` | Connect timeout; kiểm tra network, listener, DNS và timeout |
| `ORA-12541` | Không có listener tại host/port |
| `ORA-12514` | Listener không nhận diện service name |
| `ORA-12154` | Không phân giải được connect identifier |
| `ORA-01017` | Credential không hợp lệ; không retry cùng thông tin |
| `ORA-28000` | Account bị khóa |
| Socket connect timeout | Kiểm tra firewall, routing, host và transport timeout |

Không retry vô hạn lỗi service name hoặc credential. Phân loại lỗi cấu hình với lỗi mạng tạm thời.

## 5. Read timeout và socket read timeout

Sau khi kết nối thành công, JDBC gửi request đến database và chờ phản hồi. **Read timeout** giới hạn thời gian chờ dữ liệu đọc từ socket.

Oracle JDBC Thin Driver có thuộc tính:

```text
oracle.jdbc.ReadTimeout
```

Thuộc tính này thường được cấu hình theo milliseconds. Ví dụ:

```java
Properties properties = new Properties();
properties.setProperty("user", username);
properties.setProperty("password", passwordFromSecretProvider);
properties.setProperty("oracle.jdbc.ReadTimeout", "15000");

Connection connection =
        DriverManager.getConnection(jdbcUrl, properties);
```

Có thể cấu hình qua OracleDataSource hoặc cơ chế datasource properties tương ứng. Cách truyền thuộc tính phụ thuộc cách ứng dụng tạo connection.

### 5.1. Read timeout không phải query timeout

Giả sử database đang chạy một truy vấn mất 60 giây. Nếu socket read timeout là 15 giây, client có thể ngừng chờ dữ liệu sau khoảng thời gian đó và nhận lỗi socket/read timeout.

Điều này không có nghĩa database chắc chắn đã dừng câu SQL ở giây thứ 15. Read timeout ở tầng socket không phải cam kết hủy statement ở server. Câu lệnh có thể còn chạy cho đến khi server nhận được tín hiệu hủy, client đóng connection hoặc operation tự kết thúc.

Nếu cần giới hạn thời gian thực thi SQL, hãy dùng query timeout hoặc call timeout phù hợp, không chỉ dựa vào socket read timeout.

### 5.2. Read timeout có thể xảy ra khi fetch

Một câu SELECT có thể execute nhanh nhưng trả về rất nhiều hàng. Ứng dụng đọc `ResultSet` theo nhiều lần fetch. Một lần fetch có thể phải chờ database gửi batch tiếp theo.

Do đó, read timeout có thể xảy ra:
- Trong lúc chờ kết quả execute.
- Trong lúc fetch thêm hàng.
- Khi đọc LOB hoặc dữ liệu lớn qua nhiều round trip.
- Khi database hoặc network tạm ngừng phản hồi.

`Statement.setQueryTimeout()` không nên được coi là giới hạn chắc chắn cho tổng thời gian ứng dụng tiêu thụ mọi hàng trong `ResultSet`. Kiểm thử riêng giai đoạn fetch và đặt deadline ở application layer.

### 5.3. Connection sau read timeout

Sau socket read timeout, trạng thái connection có thể không còn đáng tin cậy. Với Oracle JDBC Thin, một lỗi đọc socket có thể làm connection không sử dụng được hoặc bị đánh dấu hỏng.

Ứng dụng nên:
1. Dừng dùng connection hiện tại.
2. Đóng/discard connection theo cơ chế pool.
3. Không trả connection lỗi về pool như một connection khỏe.
4. Nếu transaction có DML, xác định trạng thái transaction trước khi gửi lại nghiệp vụ.
5. Lấy connection mới cho thao tác tiếp theo.

Không gọi lại cùng statement trên một socket đã timeout rồi giả định session vẫn đồng bộ.

## 6. Query timeout bằng Statement.setQueryTimeout()

JDBC cung cấp:

```java
statement.setQueryTimeout(5);
```

Tham số có đơn vị **giây**. Nếu thời gian thực thi vượt ngưỡng, driver cố gắng hủy statement và báo lỗi cho ứng dụng, thường qua `SQLTimeoutException` hoặc `SQLException` tùy driver/operation.

Ví dụ:

```java
String sql = """
    SELECT order_id, customer_id, amount
    FROM app.orders
    WHERE status = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setQueryTimeout(5);
    statement.setString(1, "OPEN");

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            BigDecimal amount = resultSet.getBigDecimal("amount");
        }
    }
}
```

### 6.1. Đặt timeout trước khi execute

Gọi `setQueryTimeout()` trước `executeQuery()`, `executeUpdate()` hoặc `execute()`. Đặt timeout trên statement sau khi execute không thể áp dụng ngược cho lần thực thi đã bắt đầu.

### 6.2. Đơn vị là giây

`setQueryTimeout(5)` nghĩa là 5 giây, không phải 5 milliseconds. Giá trị 0 có nghĩa không có giới hạn query timeout theo JDBC API.

Không truyền `5000` với ý định 5 giây; điều đó có thể trở thành 5.000 giây.

### 6.3. Query timeout có giới hạn gì?

Query timeout là giới hạn cho việc thực thi statement theo JDBC driver. Nó không tự bao gồm:
- Thời gian chờ connection pool.
- Thời gian thiết lập physical connection trước khi có statement.
- Toàn bộ thời gian xử lý request ở application.
- Mọi thời gian xử lý sau khi statement đã trả cursor, chẳng hạn toàn bộ vòng lặp đọc kết quả.
- Thời gian chờ một dịch vụ HTTP khác được gọi trong cùng request.

Cần kết hợp query timeout với pool/connect/read timeout và application deadline.

### 6.4. Query timeout là yêu cầu hủy, không phải rollback transaction

Khi timeout, driver cố gắng hủy statement. Nhưng transaction có thể đã chứa các statement thành công trước đó. Hủy statement hiện tại không tự động đồng nghĩa toàn bộ transaction đã rollback.

Nếu business operation phải nguyên tử, ứng dụng cần rollback transaction khi xác định connection/session còn sử dụng được và transaction chưa commit. Nếu connection mất trong vùng COMMIT, phải xử lý outcome không rõ ràng theo thiết kế transaction.

## 7. Oracle JDBC call timeout

Oracle JDBC cung cấp extension `OracleConnection.setCallTimeout(int milliseconds)` trong các driver hỗ trợ.

API này đặt giới hạn cho **một database round-trip**. Một câu SQL hoặc stored procedure có thể phát sinh nhiều round-trip, vì vậy call timeout không nhất thiết là tổng thời gian wall-clock của toàn bộ nghiệp vụ.

Ví dụ:

```java
import oracle.jdbc.OracleConnection;

try (Connection connection = dataSource.getConnection()) {
    OracleConnection oracleConnection =
            connection.unwrap(OracleConnection.class);

    // Mỗi database round-trip bị giới hạn 5 giây.
    oracleConnection.setCallTimeout(5_000);

    try (PreparedStatement statement =
                 connection.prepareStatement(
                     "SELECT order_id FROM app.orders WHERE order_id = ?")) {

        statement.setLong(1, orderId);
        statement.setQueryTimeout(10);

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                long id = resultSet.getLong(1);
            }
        }
    }
}
```

Đây là ví dụ minh họa. Import package, API và hành vi chính xác phụ thuộc Oracle JDBC driver version.

### 7.1. Call timeout khác query timeout

- Query timeout giới hạn thời gian statement theo JDBC.
- Call timeout giới hạn thời gian cho một round-trip tới database.
- Một thao tác có thể có nhiều round-trip, chẳng hạn execute, fetch nhiều batch hoặc gọi nhiều lần trong stored procedure/client interaction.

Vì vậy, không thay query timeout bằng call timeout mà không hiểu số round-trip và cách driver thực hiện operation.

### 7.2. Đặt lại timeout khi dùng connection pool

`setCallTimeout()` là trạng thái ở connection. Nếu connection được trả về pool, request tiếp theo có thể kế thừa cấu hình timeout nếu pool không reset nó.

Cần:
- Đặt timeout theo từng request/connection checkout.
- Khôi phục giá trị mặc định hoặc policy chuẩn trước khi trả connection.
- Không để một request có timeout ngắn làm hỏng request tiếp theo.
- Kiểm tra connection labeling/reset callback nếu pool hỗ trợ.

### 7.3. Khi nào call timeout hữu ích?

Call timeout có thể hữu ích để giới hạn một lần chờ database response, đặc biệt với ứng dụng cần ngăn socket read kéo dài. Tuy nhiên, vẫn phải kết hợp application deadline và query timeout để kiểm soát tổng request.

## 8. JDBC Connection.setNetworkTimeout()

JDBC 4.1 có API:

```java
connection.setNetworkTimeout(executor, milliseconds);
```

API này đặt giới hạn thời gian một JDBC request chờ database phản hồi qua connection. Nếu quá hạn, driver có thể đánh dấu connection không còn hợp lệ và sử dụng executor để thực hiện hành động abort theo JDBC contract.

Ví dụ:

```java
ExecutorService networkTimeoutExecutor =
        Executors.newSingleThreadExecutor();

try (Connection connection = dataSource.getConnection()) {
    connection.setNetworkTimeout(
            networkTimeoutExecutor,
            15_000
    );

    // Thực hiện các thao tác JDBC có giới hạn network wait.
} finally {
    networkTimeoutExecutor.shutdown();
}
```

Đây là ví dụ tối giản. Trong ứng dụng thực tế, không tạo một executor mới cho từng request. Dùng executor được quản lý theo vòng đời ứng dụng và đóng khi application shutdown.

### 8.1. Connection network timeout không phải statement timeout

Network timeout là giới hạn chờ response ở cấp connection. Nó có thể làm connection bị abort khi quá hạn. Query timeout có semantics ở cấp statement và thường cho driver cơ hội gửi yêu cầu hủy statement.

Không dùng network timeout quá ngắn như cách thay thế query cancellation. Nếu network timeout kích hoạt trước, connection có thể bị loại bỏ trong khi server-side statement chưa được xử lý dừng theo cách ứng dụng mong muốn.

### 8.2. Reset trước khi trả connection

Nếu dùng pool, timeout phải được khôi phục theo policy của pool trước khi trả connection. JDBC `getNetworkTimeout()` có thể đọc giá trị hiện tại; việc reset cần tuân theo API và driver hỗ trợ.

Một connection đã bị abort không được tái sử dụng. Pool phải loại nó khỏi circulation.

## 9. Hủy statement chủ động bằng Statement.cancel()

Ngoài timeout tự động, ứng dụng có thể chủ động hủy một statement đang chạy:

```java
statement.cancel();
```

Điều này hữu ích khi:
- Người dùng bấm Cancel.
- HTTP request bị client ngắt.
- Application deadline hết.
- Một tác vụ nền bị dừng.
- Circuit breaker hoặc orchestration quyết định không cần kết quả nữa.

JDBC cho phép một thread gọi `cancel()` để yêu cầu hủy statement đang được thread khác thực thi.

### 9.1. Ví dụ hủy từ thread điều khiển

```java
ExecutorService executor = Executors.newSingleThreadExecutor();

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
             connection.prepareStatement(
                 "SELECT order_id FROM app.large_orders")) {

    Future<?> cancelTask = executor.submit(() -> {
        try {
            Thread.sleep(5_000);
            statement.cancel();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (SQLException e) {
            // Ghi nhận lỗi cancel mà không log dữ liệu nhạy cảm.
        }
    });

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            // Xử lý kết quả.
        }
    } finally {
        cancelTask.cancel(true);
    }
} finally {
    executor.shutdownNow();
}
```

Đây là ví dụ minh họa cách một thread khác yêu cầu cancel. Không nên dùng `Thread.sleep()` làm cơ chế timeout production; dùng scheduler/deadline/cancellation token của framework. Nếu `cancel()` không thành công hoặc connection đã hỏng, cần xử lý connection theo trạng thái thực tế.

### 9.2. Cancel là best effort

`Statement.cancel()` gửi yêu cầu hủy qua driver/database. Không nên giả định:
- Server dừng đúng tại thời điểm client gọi cancel.
- Mọi loại operation có thể bị ngắt tức thì.
- Connection luôn còn khỏe sau cancel.
- Transaction tự rollback hoàn toàn.

Ứng dụng cần bắt lỗi cancel, chờ statement kết thúc theo giới hạn hợp lý và kiểm tra connection trước khi tái sử dụng.

### 9.3. ORA-01013

Khi operation bị hủy, Oracle có thể trả:

```text
ORA-01013: user requested cancel of current operation
```

Đây thường là tín hiệu operation đã bị yêu cầu hủy. Tuy nhiên, ứng dụng cần phân biệt:
- User chủ động hủy.
- Query timeout của JDBC.
- Một tầng middleware gửi cancel.
- Một thao tác quản trị hủy SQL.

Không coi `ORA-01013` là lỗi database cần retry tự động. Tôn trọng cancellation của caller.

## 10. Phân biệt cancel statement, rollback transaction và đóng connection

Ba thao tác có mục đích khác nhau:

| Hành động | Mục tiêu | Tác động |
|---|---|---|
| `Statement.cancel()` | Dừng statement đang chạy | Yêu cầu hủy operation hiện tại |
| `Connection.rollback()` | Hủy thay đổi chưa commit trong transaction hiện tại | Hoàn tác transaction theo semantics Oracle |
| `Connection.close()` | Đóng logical connection/trả về pool | Giải phóng connection theo datasource/pool |
| `Connection.abort(executor)` | Hủy connection vật lý theo JDBC | Connection không còn dùng được |

### 10.1. Cancel không phải rollback

Ví dụ transaction:
1. UPDATE số dư tài khoản A.
2. INSERT ledger.
3. SELECT báo cáo xác nhận.
4. SELECT bị timeout.

Nếu chỉ cancel SELECT cuối, hai thay đổi trước đó vẫn có thể còn trong transaction. Nếu nghiệp vụ cần tất cả cùng thành công hoặc cùng thất bại, caller phải rollback.

### 10.2. Rollback cần connection còn hoạt động

Nếu connection vẫn khỏe và transaction chưa commit, gọi `rollback()` để hoàn tác thay đổi chưa commit. Nếu connection đã mất, không thể dựa vào một lệnh rollback gửi trên socket hỏng để kết luận server đã rollback.

Oracle sẽ xử lý session/transaction khi phát hiện session bị ngắt theo cơ chế database. Nhưng nếu lỗi xảy ra quanh COMMIT, outcome có thể chưa rõ với client. Dùng idempotency key hoặc Transaction Guard trong môi trường được hỗ trợ để xác định kết quả trước khi gửi lại nghiệp vụ.

### 10.3. Khi nào cần abort connection?

Nếu statement không dừng, socket hỏng hoặc connection không thể đồng bộ, có thể cần loại bỏ/abort connection theo API và policy của pool. Abort là biện pháp mạnh: connection không được tái sử dụng.

Không abort connection chỉ vì một query chậm nếu `Statement.cancel()` có thể giải quyết an toàn. Chọn biện pháp dựa trên trạng thái driver/session.

## 11. Thiết kế timeout theo deadline tổng

Timeout ở từng tầng phải nằm trong ngân sách của request. Giả sử API có deadline 10 giây:

| Giai đoạn | Ngân sách minh họa |
|---|---:|
| Chờ pool | 1 giây |
| Mở connection mới nếu cần | 2 giây |
| Thực thi SQL | 5 giây |
| Đọc kết quả và hoàn tất | 1 giây |
| Dự phòng/response | 1 giây |
| Tổng | 10 giây |

Không phải mọi request đều tạo physical connection mới. Bảng trên là ngân sách tối đa để minh họa.

### 11.1. Công thức tư duy

\[
T_{\text{pool}} + T_{\text{connect}} + T_{\text{execute}}
+ T_{\text{fetch}} + T_{\text{application}} \leq T_{\text{deadline}}
\]

Khi retry:
\[
\sum T_{\text{attempt}} + \sum T_{\text{backoff}}
\leq T_{\text{request deadline}}
\]

Không bắt đầu một attempt mới nếu thời gian còn lại không đủ cho attempt có ý nghĩa.

### 11.2. Thứ tự timeout hợp lý

Một nguyên tắc cấu hình thường dùng:
- Pool acquisition timeout nằm trong application deadline.
- Connect timeout nằm trong ngân sách tạo connection.
- Query timeout nhỏ hơn hoặc bằng thời gian còn lại dành cho database work.
- Read/socket timeout đủ dài để query cancellation có cơ hội được xử lý và phản hồi.
- Application deadline là giới hạn tổng cuối cùng.

Ví dụ query timeout 5 giây và read timeout 15 giây có thể hợp lý cho một workload cụ thể; đây không phải giá trị mặc định phổ quát. Nếu read timeout ngắn hơn query timeout, socket có thể đóng trước khi driver hoàn tất quy trình cancel statement.

### 11.3. Không cộng timeout theo cách máy móc

Một câu SQL có thể có nhiều round-trip, fetch nhiều batch hoặc thực hiện call nội bộ. Query timeout, call timeout và read timeout không phải ba khoảng thời gian luôn cộng nối tiếp. Chúng có thể cùng giám sát các phần chờ khác nhau.

Cần đo hành vi thực tế của driver và workload thay vì suy luận tổng thời gian chỉ bằng cách cộng các con số cấu hình.

## 12. Timeout cho execute, fetch, batch và LOB

### 12.1. Execute query

`executeQuery()` gửi SQL và nhận cursor/kết quả. Query timeout thường được áp dụng cho statement execution theo driver. Nhưng nếu câu SQL trả rất nhiều hàng, phần fetch có thể chiếm thêm thời gian đáng kể.

### 12.2. Fetch và ResultSet

JDBC có thể fetch theo từng batch. `setFetchSize()` ảnh hưởng số hàng driver lấy mỗi lần round-trip:

```java
statement.setFetchSize(200);
```

Fetch size lớn có thể giảm số round-trip nhưng tăng memory. Fetch size nhỏ có thể giảm memory nhưng tăng network latency.

Read timeout/call timeout có thể tác động tới các lần fetch. Hãy đặt application deadline cho toàn bộ quá trình đọc và xử lý ResultSet, không chỉ thời gian `executeQuery()`.

### 12.3. Batch DML

Với:

```java
statement.executeBatch();
```

query timeout và driver behavior cần được kiểm thử trên batch thực tế. Nếu batch timeout, `BatchUpdateException` có thể chứa update counts cho các phần đã thực hiện theo driver/database. Không suy luận rằng toàn bộ batch tự rollback nếu transaction boundary chưa được kiểm soát.

Trong transaction thủ công:
- Bắt lỗi.
- Rollback toàn transaction nếu nghiệp vụ yêu cầu nguyên tử.
- Không commit phần kết quả chưa được xác minh.
- Nếu connection mất, xác định outcome trước khi retry.

### 12.4. LOB và streaming

Đọc CLOB/BLOB lớn có thể gồm nhiều lần trao đổi dữ liệu sau khi query đã execute. Socket read timeout có thể xảy ra trong lúc đọc stream. Đóng stream, ResultSet và connection đúng cách; không giữ connection lâu hơn cần thiết.

Với LOB streaming, kiểm thử dữ liệu kích thước đại diện và network chậm. Một query timeout ngắn không nhất thiết giới hạn toàn bộ thời gian ứng dụng đọc hết LOB.

### 12.5. Stored procedure

Stored procedure có thể thực hiện nhiều SQL statement và xử lý lâu ở server. Query timeout áp dụng cho lời gọi JDBC, nhưng cần kiểm tra cách driver xử lý call, nested SQL và cancellation trên release cụ thể.

Không thiết kế procedure chạy vô hạn rồi trông chờ client socket timeout là cơ chế quản trị workload. Có thể cần Resource Manager, giới hạn tài nguyên hoặc logic deadline ở server.

## 13. Cấu hình nhiều lớp trong Oracle JDBC

Ví dụ dưới đây minh họa một tập cấu hình có chủ đích. Giá trị cần điều chỉnh theo latency mạng, SLA, connection pool và driver version.

```java
Properties properties = new Properties();
properties.setProperty("user", username);
properties.setProperty("password", passwordFromSecretProvider);

// Oracle JDBC property: milliseconds.
properties.setProperty("oracle.net.CONNECT_TIMEOUT", "3000");

// Socket read timeout: milliseconds.
properties.setProperty("oracle.jdbc.ReadTimeout", "12000");

Connection connection =
        DriverManager.getConnection(jdbcUrl, properties);

try {
    try (PreparedStatement statement =
                 connection.prepareStatement(
                     "SELECT order_id FROM app.orders WHERE status = ?")) {

        // JDBC query timeout: seconds.
        statement.setQueryTimeout(5);
        statement.setString(1, "OPEN");

        try (ResultSet resultSet = statement.executeQuery()) {
            while (resultSet.next()) {
                long orderId = resultSet.getLong(1);
            }
        }
    }
} finally {
    connection.close();
}
```

Cần lưu ý:
- Connect property chỉ áp dụng khi tạo physical connection.
- Nếu connection được lấy từ pool, pool có thể trả về connection đã mở; connect timeout không giới hạn thời gian chờ pool.
- `ReadTimeout` là socket-level guard, không thay query timeout.
- `setQueryTimeout(5)` dùng giây.
- Mọi giá trị timeout phải nằm trong application deadline.
- Connection có lỗi mạng cần được kiểm tra/loại khỏi pool.

## 14. Timeout và Oracle RAC/service failover

Trong Oracle RAC, service có thể chuyển giữa các instance. Một connection đang dùng có thể bị ảnh hưởng khi node hoặc instance gặp sự cố.

Các cơ chế liên quan:
- **FAN (Fast Application Notification):** thông báo sự kiện service/instance cho client/middleware hỗ trợ.
- **FCF (Fast Connection Failover):** giúp pool loại connection bị ảnh hưởng và tạo connection mới theo service còn hoạt động.
- **UCP:** Oracle Universal Connection Pool hỗ trợ các khả năng HA và quản lý connection theo cấu hình/phiên bản.
- **Application Continuity/TAC:** có thể replay request đủ điều kiện sau outage theo cấu hình và driver được hỗ trợ.

Timeout vẫn cần thiết:
- FAN/FCF giúp phát hiện sự kiện và xử lý connection pool.
- Connect timeout giới hạn thời gian tạo connection mới.
- Query timeout giới hạn statement.
- Read timeout giới hạn socket wait.
- Application deadline giới hạn request tổng.

Failover không đồng nghĩa transaction chắc chắn chưa commit. Nếu mất phản hồi quanh COMMIT, cần xác định outcome bằng Transaction Guard hoặc idempotency design phù hợp trước khi gửi lại nghiệp vụ.

## 15. Quản lý timeout và cancellation với connection pool

Timeout là trạng thái có thể tồn tại ở nhiều cấp. Connection pool tái sử dụng connection nên cần quản lý việc reset.

### 15.1. Những trạng thái cần reset

Nếu ứng dụng thay đổi trên connection:
- Call timeout.
- Network timeout.
- Read timeout nếu driver cho phép thay đổi ở runtime.
- Auto-commit.
- Transaction isolation.
- Read-only mode.
- Schema/catalog.
- Client identifier, module/action.
- Application context.
- NLS/session settings.

Hãy dùng pool reset callback hoặc wrapper tập trung thay vì để từng repository tự đặt cấu hình tùy ý.

### 15.2. Connection lỗi phải bị loại

Khi nhận lỗi socket hoặc connection fatal:
- Đánh dấu connection hỏng.
- Không trả về idle pool.
- Đóng/discard theo API pool.
- Tạo connection mới ở lần request tiếp theo.
- Ghi metric về validation failure và connection eviction.

Một lỗi query timeout có thể không làm hỏng connection trong mọi trường hợp; cần phân loại theo exception/driver state. Không đóng toàn bộ pool chỉ vì một statement timeout.

### 15.3. Không giữ connection khi chờ retry

Nếu retry được phép:
1. Kết thúc/rollback transaction theo trạng thái xác định.
2. Đóng statement/result set.
3. Trả connection khỏe hoặc discard connection lỗi.
4. Thực hiện backoff bên ngoài connection.
5. Lấy connection mới cho attempt tiếp theo.

Không giữ connection trong lúc sleep hoặc chờ một dịch vụ khác.

## 16. Phân loại exception và hành động phù hợp

| Tình huống | Ví dụ tín hiệu | Hành động |
|---|---|---|
| Pool hết connection | Pool acquisition timeout | Kiểm tra pool usage/leak/slow SQL; không retry dồn dập |
| Connect timeout | `ORA-12170`, socket connect timeout | Kiểm tra mạng/listener; retry giới hạn nếu transient |
| Service sai | `ORA-12514` | Sửa service name/registration; không retry vô hạn |
| Credential sai | `ORA-01017` | Dừng retry, xử lý secret/account |
| Read timeout | Socket read timed out | Loại connection nếu không còn tin cậy; kiểm tra server/query |
| Query timeout | `SQLTimeoutException`, có thể `ORA-01013` | Dừng operation, xử lý transaction |
| User cancel | `ORA-01013` hoặc cancellation exception | Tôn trọng yêu cầu hủy, không tự retry |
| Connection reset | `ORA-03113`, `ORA-03114`, `ORA-03135` | Loại connection; xác định transaction outcome |
| Deadlock | `ORA-00060` | Rollback toàn business transaction rồi retry có giới hạn nếu phù hợp |
| Serialization conflict | `ORA-08177` | Rollback và retry toàn transaction khi nghiệp vụ cho phép |

Không chỉ dựa vào mã lỗi. Cần xem exception chain, SQLState, vendor code, transaction phase và driver version.

### 16.1. Phân biệt timeout với cancellation

Timeout là lý do hệ thống quyết định dừng chờ hoặc dừng operation. Cancellation là hành động yêu cầu statement dừng.

Một timeout ở socket layer có thể không gửi được cancel request nếu socket đã hỏng. Một query timeout ở JDBC có thể cho driver cơ hội gửi cancel. Vì vậy hai khái niệm liên quan nhưng không đồng nghĩa.

### 16.2. Phân biệt lỗi có thể retry và lỗi không retry

Có thể cân nhắc retry:
- Connect failure tạm thời.
- Một số lỗi outage/failover.
- Deadlock sau khi rollback toàn transaction.
- Serialization conflict sau khi rollback.

Không retry cùng cách:
- Credential sai.
- Service name sai.
- SQL syntax sai.
- Thiếu quyền.
- Constraint violation nghiệp vụ.
- User chủ động cancel.
- Request đã hết deadline.

## 17. Hủy câu lệnh khi người dùng hủy HTTP request

Trong ứng dụng web, người dùng có thể rời trang hoặc gateway hủy request. Ứng dụng nên truyền cancellation signal từ tầng HTTP tới tầng JDBC.

Một thiết kế tổng quát:
1. Mỗi request có deadline và cancellation token.
2. JDBC operation đăng ký statement đang chạy với request context.
3. Khi request bị hủy, cancellation handler gọi `Statement.cancel()`.
4. Đóng ResultSet/Statement.
5. Rollback nếu business transaction bị hủy và connection còn dùng được.
6. Trả hoặc loại connection theo trạng thái.
7. Ghi nhận cancellation reason và duration.

Không để thread xử lý request bị giữ mãi chỉ vì JDBC call không có timeout.

### 17.1. Tránh dùng Thread.interrupt thay cho JDBC cancel

Interrupt thread không đảm bảo database statement dừng. Một số framework/driver có thể phản ứng với interrupt, nhưng cần API cancellation được hỗ trợ rõ ràng. Dùng `Statement.cancel()` hoặc cơ chế cancel của framework/driver và kiểm thử với Oracle JDBC.

### 17.2. Không hủy thao tác dùng chung

Nếu một `Statement` hoặc `Connection` được chia sẻ giữa nhiều request, việc cancel có thể ảnh hưởng nhầm request khác. JDBC connection/statement không nên được dùng đồng thời bởi nhiều business request theo cách không được hỗ trợ.

Mỗi request/transaction cần quyền sở hữu rõ ràng đối với connection và statement.

## 18. Giới hạn query ở phía database

Client timeout bảo vệ request và connection, nhưng database cũng cần quản trị workload.

Có thể cân nhắc:
- Oracle Database Resource Manager để giới hạn CPU, parallelism hoặc thời gian theo consumer group.
- Service riêng cho workload báo cáo/batch.
- Profile/resource limits theo user khi phù hợp.
- SQL plan management và tuning để xử lý truy vấn chậm.
- Giới hạn concurrency ở application/pool.
- SQL Monitor/trace theo quyền và license phù hợp.

Không dùng client timeout như biện pháp duy nhất để ngăn truy vấn runaway. Nếu client ngừng chờ nhưng server vẫn làm việc, database vẫn có thể tiêu thụ CPU, I/O, PGA và lock.

## 19. Đo lường và giám sát timeout

Log nên ghi metadata đủ điều tra:
- Request/correlation ID.
- Database service và application module/action.
- Pool name.
- Timeout loại nào đã kích hoạt.
- Cấu hình timeout áp dụng.
- Thời điểm bắt đầu/kết thúc.
- SQL_ID nếu lấy được.
- Oracle vendor error code và SQLState.
- Transaction phase: pool, connect, execute, fetch, commit.
- Connection được giữ, trả hay discard.
- Có cancel/rollback hay không.
- Retry attempt và thời gian còn lại của deadline.

Không ghi password, token, toàn bộ bind values hoặc dữ liệu nghiệp vụ nhạy cảm.

### 19.1. Metrics cần theo dõi

| Metric | Ý nghĩa |
|---|---|
| Pool acquisition latency | Thời gian chờ connection |
| Physical connect latency | Thời gian tạo kết nối mới |
| Connect timeout count | Số lần không kết nối kịp |
| Socket read timeout count | Số lần chờ socket quá hạn |
| Query timeout count | Số statement vượt giới hạn |
| Cancel success/failure | Kết quả yêu cầu hủy |
| Connection eviction count | Số connection bị loại |
| Statement execution latency | Phân bố thời gian SQL |
| ResultSet fetch latency | Thời gian đọc dữ liệu |
| Request deadline exceeded | Request vượt tổng ngân sách |
| Pool active/idle/pending | Áp lực connection pool |

Theo dõi p50, p95 và p99, không chỉ average. Một số ít truy vấn rất chậm có thể ảnh hưởng đáng kể tới request tail latency.

### 19.2. Tương quan client và database

Khi timeout:
- Ghi timestamp đồng bộ.
- Ghi service/module/action.
- Ghi SQL_ID nếu có.
- Kiểm tra session còn chạy không.
- Xem alert log, listener log và wait events.
- Kiểm tra session bị cancel hay chỉ client mất kết nối.
- Xác định transaction có commit hay không.

Nếu có quyền và license phù hợp, dùng công cụ Oracle monitoring để điều tra; không bật trace/bind logging rộng rãi mà chưa đánh giá dữ liệu nhạy cảm.

## 20. Kiểm thử timeout trong môi trường lab

Không kiểm thử bằng cách làm treo production hoặc kill instance dùng chung. Dùng schema/database lab và câu SQL có thời gian chạy được kiểm soát.

### Bước 1. Kiểm tra driver và datasource

Ghi nhận:
- Oracle Database version.
- Oracle JDBC driver version.
- Thin/OCI driver.
- Pool implementation/version.
- Service name.
- Các timeout đang cấu hình và đơn vị.

### Bước 2. Kiểm tra pool acquisition timeout

Giới hạn pool ở một connection trong lab. Giữ connection đầu tiên, sau đó request thứ hai gọi `getConnection()`. Xác nhận request thứ hai hết thời gian chờ pool theo cấu hình.

### Bước 3. Kiểm tra connect timeout

Dùng endpoint lab không phản hồi hoặc port được firewall chặn có kiểm soát. Xác nhận thời gian tạo physical connection bị giới hạn. Không dùng hostname/service production cho test lỗi.

### Bước 4. Kiểm tra query timeout

Chọn một câu truy vấn lab có thời gian chạy dài đã biết hoặc procedure kiểm thử được DBA phê duyệt. Đặt:

```java
statement.setQueryTimeout(2);
```

Xác nhận driver trả timeout/cancel exception và quan sát database session có dừng operation hay không.

### Bước 5. Kiểm tra read timeout

Trong môi trường riêng, cấu hình `oracle.jdbc.ReadTimeout` thấp hơn thời gian chờ phản hồi của một operation kiểm thử. Xác nhận socket read timeout, trạng thái connection và hành vi pool eviction.

### Bước 6. Kiểm tra Statement.cancel()

Chạy query từ một thread, sau đó yêu cầu thread điều khiển gọi `statement.cancel()`. Xác nhận exception và thời gian server dừng operation.

### Bước 7. Kiểm tra fetch

Dùng result set đủ lớn để có nhiều fetch round-trip. Đo riêng thời gian execute và thời gian lặp `ResultSet.next()`.

### Bước 8. Kiểm tra transaction

Trong lab, thực hiện DML rồi hủy một statement sau đó. Xác nhận transaction có thay đổi chưa commit và kiểm tra hành vi rollback. Không giả định cancel statement đã rollback mọi DML trước đó.

### Bước 9. Kiểm tra connection pool

Sau từng loại lỗi, kiểm tra connection được giữ lại hay discard. Xác nhận request kế tiếp lấy được connection khỏe.

### Bước 10. Ghi kết quả

Ghi timeout thực tế, thời gian server dừng, exception, connection state, transaction outcome và tác động tới request tiếp theo.

## 21. Ví dụ cấu hình timeout theo loại workload

Các giá trị dưới đây chỉ là điểm bắt đầu minh họa, cần benchmark và điều chỉnh.

| Workload | Pool wait | Connect | Query | Read/socket | Ghi chú |
|---|---:|---:|---:|---:|---|
| API OLTP ngắn | 1 s | 3 s | 3 s | 10 s | Deadline request ngắn, ít hàng |
| API đọc báo cáo nhỏ | 2 s | 3 s | 8 s | 15 s | Kiểm soát fetch và số hàng |
| Batch ETL | 5 s | 5 s | 120 s | 180 s | Có deadline job và checkpoint |
| Admin operation | Theo change window | Theo môi trường | Theo thao tác | Theo network | Có phê duyệt và giám sát |

Không copy bảng này thành cấu hình mặc định. Một báo cáo cần 60 giây có thể hợp lệ; một API thanh toán có thể cần dưới 2 giây. Timeout phải theo SLA và hành vi thực tế.

## 22. Những lỗi thiết kế thường gặp

| Anti-pattern | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ đặt query timeout | Request vẫn có thể chờ pool/connect | Đặt timeout ở từng lớp |
| Nhầm pool timeout với connect timeout | Không giới hạn thời gian tạo physical connection | Cấu hình cả pool và driver |
| Chỉ dùng read timeout | Client ngừng đọc nhưng SQL có thể còn chạy | Dùng query/call timeout và cancellation |
| Đặt read timeout thấp hơn query timeout | Socket có thể hỏng trước khi cancel hoàn tất | Phối hợp timeout và kiểm thử |
| Dùng `setQueryTimeout(5000)` cho 5 giây | Thực tế là 5.000 giây | Nhớ đơn vị giây |
| Nghĩ timeout tự rollback transaction | DML trước đó có thể còn trong transaction | Rollback rõ ràng khi có thể |
| Gọi `cancel()` rồi tái sử dụng mọi connection | Connection có thể không còn đồng bộ | Kiểm tra và discard nếu cần |
| Retry ngay sau timeout quanh COMMIT | Có thể tạo giao dịch trùng | Resolve outcome/idempotency |
| Giữ connection khi chờ retry | Cạn pool | Release trước backoff |
| Chỉ đặt HTTP timeout | Database query có thể tiếp tục chạy | Truyền cancellation xuống JDBC |
| Tạo executor cho từng request không đóng | Rò thread | Quản lý executor theo vòng đời ứng dụng |
| Thay global login timeout không đánh giá | Ảnh hưởng datasource khác | Cấu hình theo datasource/driver |
| Tăng pool để hết timeout | Database có thể quá tải hơn | Điều tra leak, query và concurrency |
| Không reset call/network timeout | Request sau kế thừa trạng thái | Reset connection trước khi trả pool |

## 23. Checklist triển khai

### Kết nối
- Pool acquisition timeout được cấu hình.
- Connect timeout giới hạn physical connection.
- DNS/listener/service và TLS có thời gian chờ phù hợp.
- Retry connection có giới hạn.
- Connection lỗi được loại khỏi pool.

### Thực thi SQL
- Query timeout được đặt trước execute.
- Đơn vị giây được xác nhận.
- Read timeout là safety net phù hợp.
- Call timeout được cân nhắc cho driver Oracle hỗ trợ.
- Fetch/LOB/batch được kiểm thử riêng.
- Có application deadline bao trùm execute và fetch.

### Cancellation và transaction
- Có cơ chế nhận cancellation signal.
- `Statement.cancel()` được dùng đúng statement/request.
- Cancel failure được xử lý.
- Rollback transaction khi business operation bị hủy và trạng thái cho phép.
- Commit outcome unknown được xử lý an toàn.
- Connection hỏng không được tái sử dụng.

### Pool và vận hành
- Timeout/session state được reset.
- Executor dùng cho network timeout có vòng đời rõ.
- Có metrics và alert theo từng lớp timeout.
- Có runbook điều tra local và remote database.
- Có test fault injection trong môi trường lab.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** Connect timeout kiểm soát điều gì?

**Trả lời:** Thời gian thiết lập kết nối vật lý tới endpoint/listener/service theo cơ chế driver và Oracle Net.

**Câu 2.** Pool acquisition timeout khác connect timeout thế nào?

**Trả lời:** Pool timeout là thời gian chờ connection rảnh trong pool; connect timeout áp dụng khi cần mở physical connection mới.

**Câu 3.** `oracle.jdbc.ReadTimeout` dùng để làm gì?

**Trả lời:** Giới hạn thời gian chờ đọc dữ liệu từ socket theo đơn vị milliseconds trong Oracle JDBC Thin Driver được hỗ trợ.

**Câu 4.** Read timeout có bảo đảm server dừng SQL không?

**Trả lời:** Không. Nó giới hạn client chờ socket; server-side statement có thể còn chạy nếu chưa nhận hoặc xử lý yêu cầu hủy.

**Câu 5.** `Statement.setQueryTimeout()` dùng đơn vị nào?

**Trả lời:** Giây. Giá trị 0 nghĩa là không đặt giới hạn theo JDBC API.

**Câu 6.** Query timeout có bao gồm thời gian chờ pool không?

**Trả lời:** Không. Pool acquisition xảy ra trước khi statement được tạo/thực thi.

**Câu 7.** `OracleConnection.setCallTimeout()` giới hạn điều gì?

**Trả lời:** Thời gian của một database round-trip, không nhất thiết là tổng thời gian của toàn bộ request nhiều round-trip.

**Câu 8.** `Connection.setNetworkTimeout()` có tác dụng gì?

**Trả lời:** Giới hạn thời gian JDBC request chờ database phản hồi ở cấp connection; quá hạn có thể làm connection bị abort.

**Câu 9.** `Statement.cancel()` có phải rollback không?

**Trả lời:** Không. Nó yêu cầu hủy statement hiện tại; transaction có thể vẫn chứa thay đổi chưa commit từ statement trước.

**Câu 10.** ORA-01013 thường có nghĩa gì?

**Trả lời:** Operation bị yêu cầu hủy, ví dụ từ user, query timeout hoặc cơ chế quản trị.

**Câu 11.** Vì sao không nên tái sử dụng connection sau socket read timeout?

**Trả lời:** Connection có thể đã mất đồng bộ hoặc không còn hợp lệ; pool cần loại bỏ khi driver đánh dấu hỏng.

**Câu 12.** Vì sao query timeout không luôn giới hạn toàn bộ thời gian đọc ResultSet?

**Trả lời:** Execute và fetch có thể là các giai đoạn/round-trip riêng; cần read/call timeout và application deadline cho quá trình fetch.

**Câu 13.** Khi người dùng hủy HTTP request nên làm gì?

**Trả lời:** Truyền cancellation signal tới JDBC, gọi cancel statement, đóng resource và xử lý transaction/connection theo trạng thái.

**Câu 14.** Nếu timeout xảy ra quanh COMMIT thì sao?

**Trả lời:** Client có thể không biết transaction đã commit hay chưa; cần xác định outcome bằng cơ chế phù hợp hoặc idempotency.

**Câu 15.** Vì sao cần reset timeout khi dùng connection pool?

**Trả lời:** Timeout là trạng thái connection; request sau có thể kế thừa cấu hình của request trước nếu không reset.

**Câu 16.** Có nên chỉ dùng timeout phía client để bảo vệ database?

**Trả lời:** Không. Cần thêm Resource Manager, workload governance, giới hạn concurrency và tuning phía database.

## 25. Kết luận

Connect timeout, read timeout, query timeout và cancellation kiểm soát những giai đoạn khác nhau trong vòng đời một request Oracle JDBC. Pool acquisition timeout giới hạn thời gian chờ connection rảnh; connect timeout giới hạn việc tạo physical connection; read/socket timeout giới hạn thời gian chờ dữ liệu qua mạng; query timeout giới hạn statement theo JDBC; call timeout giới hạn một database round-trip trong Oracle JDBC; application deadline bao trùm toàn bộ request.

`Statement.cancel()` yêu cầu hủy operation đang chạy, còn `rollback()` hoàn tác transaction chưa commit và `Connection.abort()` loại bỏ connection. Không được coi ba hành động này là tương đương. Read timeout có thể làm client ngừng chờ nhưng không chứng minh server đã dừng SQL. Query timeout cũng không tự rollback mọi thay đổi trước đó trong transaction. Nếu mất phản hồi quanh COMMIT, outcome có thể chưa rõ và cần được xác định trước khi retry nghiệp vụ.

Một cấu hình đáng tin cậy cần phối hợp timeout ở pool, Oracle Net, JDBC driver, statement và application deadline; kiểm thử execute, fetch, batch và LOB; loại connection hỏng khỏi pool; reset trạng thái connection khi tái sử dụng; và truyền cancellation từ request tới JDBC. Theo dõi riêng latency và số lần timeout ở từng lớp để phân biệt pool exhaustion, network issue, SQL chậm và lỗi server. Chỉ khi đã thử nghiệm trên đúng Oracle JDBC driver và workload đại diện, timeout mới trở thành cơ chế bảo vệ dịch vụ thay vì nguồn gây lỗi khó chẩn đoán.


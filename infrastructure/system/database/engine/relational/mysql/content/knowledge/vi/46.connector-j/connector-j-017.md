# Connector/J

## Đóng ResultSet/Statement, trả kết nối về pool và dọn trạng thái phiên

Trong ứng dụng Java dùng MySQL Connector/J, một truy vấn thường mở nhiều tài nguyên theo thứ tự: lấy kết nối, tạo statement, thực thi câu SQL và đọc ResultSet. Khi xử lý xong, các tài nguyên phải được đóng đúng thứ tự để giải phóng cursor, bộ nhớ, server-side statement và cuối cùng là kết nối. Nếu kết nối đến từ connection pool, gọi close trên đối tượng Connection thường trả kết nối logic về pool để tái sử dụng; nó không nhất thiết đóng socket vật lý.

Việc trả kết nối về pool cũng là ranh giới bàn giao trạng thái phiên. Một transaction còn mở, session variable, temporary table, named lock hoặc thay đổi SQL mode có thể ảnh hưởng request tiếp theo nếu pool không reset trạng thái đó. Vì vậy, ứng dụng cần đóng ResultSet/Statement, kết thúc transaction rõ ràng và khôi phục những thay đổi session mà nó tạo ra.

Trong module **DATABASE_MYSQL**, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài này kết nối các kỹ năng đó với vòng đời JDBC: quản lý tài nguyên, transaction, session state, hiệu năng truy vấn và độ tin cậy khi dùng pool.

### 1. Vòng đời tài nguyên JDBC

Một thao tác truy vấn thường có các tài nguyên:

1. **DataSource/Connection:** cung cấp phiên làm việc với database. Khi dùng pool, ứng dụng mượn một connection logic.
2. **Statement/PreparedStatement/CallableStatement:** đại diện cho câu SQL hoặc lời gọi stored procedure.
3. **ResultSet:** giữ con trỏ đọc kết quả truy vấn.
4. **Stream/LOB:** dữ liệu lớn có thể được đọc qua InputStream, Reader, Blob hoặc Clob.

Các tài nguyên có quan hệ sở hữu. ResultSet được tạo từ Statement; Statement được tạo từ Connection. Hãy đóng tài nguyên con trước tài nguyên cha:

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT order_id, total_amount FROM orders WHERE status = ?")) {

    ps.setString(1, "PAID");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            BigDecimal total = rs.getBigDecimal("total_amount");
            // Xử lý hàng hiện tại.
        }
    }
}
~~~

try-with-resources tự gọi close khi rời khỏi khối, kể cả khi có exception. Trong một danh sách resource, Java đóng theo thứ tự ngược với thứ tự khai báo: ResultSet đóng trước PreparedStatement, rồi Connection. Việc lồng ResultSet trong khối riêng làm rõ thời điểm kết thúc đọc kết quả và giúp tránh giữ cursor lâu hơn cần thiết.

JDBC cũng quy định đóng Statement sẽ đóng ResultSet hiện tại do Statement tạo ra. Tuy nhiên, vẫn nên quản lý ResultSet rõ ràng bằng try-with-resources, đặc biệt khi có nhiều result set, generated keys hoặc stream. Không giữ ResultSet sống sau khi Statement/Connection đã đóng.

### 2. Vì sao phải đóng ResultSet và Statement?

Đóng ResultSet giải phóng trạng thái đọc kết quả. Tùy cách thực thi và cấu hình Connector/J, dữ liệu có thể đã được buffer ở client hoặc vẫn được đọc dần từ server. Với kết quả lớn, ResultSet còn mở có thể giữ cursor, protocol state, bộ nhớ và connection bận trong thời gian dài.

Đóng Statement giải phóng tài nguyên gắn với câu lệnh. Với prepared statement phía server, server có thể đang giữ statement handle. Connector/J có thể cache prepared statement nếu cấu hình cache được bật; gọi close vẫn cần thiết vì driver quản lý việc trả đối tượng nội bộ về cache.

Nếu không đóng tài nguyên:

- Connection không thể được trả về pool sớm.
- Pool có thể hết connection khả dụng dù số request không tăng.
- Server có thể giữ cursor hoặc prepared statement lâu hơn cần thiết.
- Truy vấn streaming có thể giữ protocol ở trạng thái chưa đọc hết.
- Ứng dụng có thể tăng bộ nhớ do giữ ResultSet và object mapping.
- Khi gặp exception, tài nguyên dễ bị rò rỉ nếu chỉ đóng ở nhánh thành công.

Không dùng một biến toàn cục để giữ Statement/ResultSet dùng chung giữa nhiều request. JDBC Connection, Statement và ResultSet không phải đối tượng dùng chung an toàn cho nhiều luồng. Mỗi đơn vị công việc nên mượn connection riêng và sở hữu tài nguyên của nó.

### 3. Đóng nhiều loại kết quả và statement

#### 3.1. PreparedStatement và ResultSet

Đây là trường hợp phổ biến nhất. Khai báo cả Connection và PreparedStatement trong try-with-resources, rồi đóng ResultSet trong khối lồng:

~~~java
String sql = """
    SELECT order_id, created_at
    FROM orders
    WHERE customer_id = ?
    ORDER BY created_at DESC
    """;

try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(sql)) {

    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            Timestamp createdAt = rs.getTimestamp("created_at");
            // Chuyển đổi sang DTO hoặc xử lý nghiệp vụ.
        }
    }
}
~~~

Dùng PreparedStatement cho tham số giúp tránh nối chuỗi SQL từ dữ liệu người dùng và cho phép driver/server xử lý tham số đúng kiểu. Tên bảng, tên cột và từ khóa SQL không thể truyền bằng placeholder ?; nếu cần chọn động, dùng allowlist và quote identifier theo đúng quy tắc.

#### 3.2. Generated keys

Khi insert và cần khóa được sinh tự động, đóng cả ResultSet trả về bởi getGeneratedKeys:

~~~java
String sql = "INSERT INTO orders(customer_id, status) VALUES (?, ?)";

try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setLong(1, customerId);
    ps.setString(2, "NEW");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long orderId = keys.getLong(1);
        }
    }
}
~~~

Không giả định mọi driver hoặc mọi câu lệnh đều trả generated key theo cùng cách. Kiểm tra tài liệu Connector/J và test trường hợp insert nhiều hàng, batch hoặc dùng trigger.

#### 3.3. Stored procedure và nhiều ResultSet

CallableStatement có thể trả nhiều ResultSet, update count hoặc output parameter. Phải đọc và đóng từng ResultSet trước khi chuyển sang kết quả kế tiếp:

~~~java
try (Connection conn = dataSource.getConnection();
     CallableStatement cs = conn.prepareCall("{call get_order_report(?)}")) {

    cs.setLong(1, customerId);
    boolean hasResultSet = cs.execute();

    while (true) {
        if (hasResultSet) {
            try (ResultSet rs = cs.getResultSet()) {
                while (rs.next()) {
                    // Đọc kết quả hiện tại.
                }
            }
        } else if (cs.getUpdateCount() == -1) {
            break;
        }

        hasResultSet = cs.getMoreResults(Statement.CLOSE_CURRENT_RESULT);
    }
}
~~~

Mẫu này minh họa vòng lặp xử lý kết quả; stored procedure cụ thể có thể trả output parameter hoặc nhiều update count. Nếu procedure tạo nhiều kết quả, kiểm tra thứ tự và số lượng kết quả theo hợp đồng của procedure. Không bỏ qua kết quả chưa đọc rồi giữ connection mở.

### 4. ResultSet lớn, streaming và thời gian giữ connection

Connector/J có thể buffer toàn bộ kết quả truy vấn trong client tùy chế độ thực thi. Với tập dữ liệu lớn, điều này làm tăng bộ nhớ. Các chế độ đọc theo dòng hoặc cursor fetch có thể giảm bộ nhớ nhưng giữ connection bận cho đến khi đọc xong hoặc đóng ResultSet.

Khi xử lý kết quả lớn:

- Chỉ SELECT các cột cần thiết; tránh lấy LOB không cần dùng.
- Chia công việc theo khóa hoặc khoảng dữ liệu khi có thể.
- Dùng fetch size và chế độ cursor/streaming phù hợp với Connector/J.
- Đọc ResultSet tuần tự, không giữ hàng đã đọc trong collection nếu không cần.
- Đóng ResultSet ngay khi hoàn tất hoặc khi hủy xử lý.
- Đặt query timeout và theo dõi thời gian giữ connection.

Connector/J có các tùy chọn như useCursorFetch và useServerPrepStmts cho cursor-based fetching. Cách streaming forward-only cũng có quy tắc fetch size riêng theo phiên bản driver. Không sao chép một giá trị fetch size từ ví dụ cũ mà chưa xác minh cấu hình driver đang dùng.

Nếu ứng dụng đọc dữ liệu chậm từ ResultSet rồi đồng thời gọi truy vấn khác trên cùng connection, cần xem xét giới hạn của chế độ streaming và protocol. Nhiều chế độ yêu cầu đọc hết hoặc đóng kết quả hiện tại trước khi thực thi câu lệnh tiếp theo trên cùng connection.

Đối với Blob/Clob hoặc stream trả về từ ResultSet, đọc xong và đóng stream trước khi đóng ResultSet. Không trả stream cho tầng khác sử dụng sau khi connection đã được trả về pool.

### 5. Trả kết nối về pool

#### 5.1. Connection logic và connection vật lý

DataSource là giao diện JDBC cung cấp connection. Bản thân một DataSource không nhất thiết có pooling. Khi dùng pool như HikariCP hoặc một pool do application server quản lý, getConnection() thường trả về một proxy/connection logic.

Trong mô hình pool:

1. Ứng dụng gọi dataSource.getConnection() để mượn một connection.
2. Ứng dụng thực hiện truy vấn/transaction.
3. Ứng dụng gọi conn.close().
4. Pool thu hồi connection logic và đưa connection vật lý trở lại hàng chờ idle nếu connection còn khỏe và được phép tái sử dụng.

Trong mô hình không pool, close() thường đóng connection vật lý và giải phóng socket/session ở server. Vì vậy, hiểu đúng DataSource được cấu hình là điều kiện để hiểu ý nghĩa của close.

Ví dụ dùng HikariCP:

~~~java
HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:mysql://db.example.net:3306/appdb");
config.setUsername("app_user");
config.setPassword(secret);
config.setMaximumPoolSize(20);
config.setAutoCommit(true);

HikariDataSource dataSource = new HikariDataSource(config);
~~~

Đối tượng HikariDataSource có vòng đời dài theo ứng dụng; đóng nó khi ứng dụng shutdown để giải phóng pool. Không tạo pool mới cho mỗi request.

#### 5.2. close không có nghĩa là bỏ qua cleanup

Pool thường theo dõi các thuộc tính JDBC chuẩn mà ứng dụng thay đổi, ví dụ autoCommit, readOnly, transaction isolation, catalog/schema hoặc network timeout tùy implementation. Khi logical connection được đóng, pool có thể rollback transaction chưa hoàn tất và khôi phục các thuộc tính đã theo dõi.

Tuy nhiên, không nên giả định mọi pool đều reset mọi trạng thái session do SQL tạo ra. Các lệnh như SET @user_var, SET SESSION sql_mode, SET time_zone, USE schema, tạo temporary table hoặc lấy named lock có thể để lại trạng thái nếu pool không reset vật lý session hoặc không biết các thay đổi đó.

Một số pool/driver có thể sử dụng cơ chế reset session ở giao thức MySQL; việc có dùng hay không phụ thuộc phiên bản, cấu hình và implementation. Kiểm tra tài liệu của pool và Connector/J, sau đó thử nghiệm bằng cách mượn lại cùng connection vật lý nếu cần chứng minh hành vi. Không dựa vào việc close trả về thành công để kết luận mọi session variable đã được xóa.

### 6. Kết thúc transaction trước khi close

Khi autoCommit=true, mỗi statement thường được commit độc lập sau khi thực thi thành công. Khi autoCommit=false, các thay đổi thuộc transaction cho đến khi ứng dụng gọi commit hoặc rollback.

Luôn kết thúc transaction rõ ràng trước khi trả connection:

~~~java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try (PreparedStatement debit = conn.prepareStatement(
             "UPDATE accounts SET balance = balance - ? WHERE account_id = ?");
         PreparedStatement credit = conn.prepareStatement(
             "UPDATE accounts SET balance = balance + ? WHERE account_id = ?")) {

        debit.setBigDecimal(1, amount);
        debit.setLong(2, fromAccount);
        debit.executeUpdate();

        credit.setBigDecimal(1, amount);
        credit.setLong(2, toAccount);
        credit.executeUpdate();

        conn.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            conn.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    }
}
~~~

Ví dụ trên minh họa transaction chuyển tiền. Trong ứng dụng thực tế, cần kiểm tra số dòng bị ảnh hưởng, tài khoản tồn tại, số dư đủ, deadlock và quy tắc retry. Nếu commit() trả lỗi do mất kết nối, kết quả transaction có thể chưa xác định từ phía client; không retry mù quáng một giao dịch không idempotent. Hãy đối chiếu trạng thái nghiệp vụ hoặc dùng transaction ID/idempotency key.

JDBC khuyến nghị ứng dụng commit hoặc rollback trước khi close. Hành vi khi close một connection có transaction chưa kết thúc có thể phụ thuộc implementation; pool thường có biện pháp rollback khi thu hồi nhưng đó là lớp bảo vệ cuối cùng, không phải cách quản lý transaction chính.

Nếu thay đổi autoCommit hoặc isolation, hãy khôi phục baseline trước khi trả connection. Thứ tự quan trọng: rollback transaction còn mở trước, sau đó khôi phục các thuộc tính khác và cuối cùng mới bật lại autoCommit nếu baseline yêu cầu. Đổi autoCommit từ false sang true có thể commit transaction hiện tại.

### 7. Những trạng thái phiên cần dọn

Session MySQL tồn tại cùng connection vật lý. Những thay đổi sau có thể ảnh hưởng request tiếp theo nếu connection được tái sử dụng:

| Trạng thái | Ví dụ | Cách xử lý |
|---|---|---|
| Transaction/autocommit | SET autocommit = 0, transaction chưa commit | Commit/rollback rõ ràng; khôi phục autoCommit baseline |
| Isolation/read-only | SET SESSION TRANSACTION ISOLATION LEVEL ..., SET SESSION transaction_read_only=... | Lưu trạng thái cũ hoặc dùng API JDBC; khôi phục trước khi trả connection |
| Session variables | SET @tenant_id = ... | Tránh nếu có thể; nếu dùng, lưu và khôi phục hoặc bảo đảm reset session |
| System/session variables | SET SESSION sql_mode, time_zone, foreign_key_checks, unique_checks | Lưu giá trị cũ và khôi phục chính xác |
| Default schema | USE appdb, Connection.setCatalog()/setSchema() | Khôi phục catalog/schema baseline |
| Temporary table | CREATE TEMPORARY TABLE | DROP rõ ràng trong finally; không giả định commit sẽ xóa |
| Named lock | GET_LOCK() | Gọi RELEASE_LOCK(); kiểm tra kết quả lấy/nhả lock |
| Table lock | LOCK TABLES | UNLOCK TABLES trước khi trả connection |
| Prepared statement/cursor | Statement hoặc ResultSet còn mở | Đóng mọi ResultSet, Statement và stream |
| Warnings | JDBC warning chain | Đọc nếu cần, sau đó clearWarnings(); thao tác này không reset session variables |
| Client info/network timeout | JDBC setClientInfo, setNetworkTimeout | Khôi phục baseline theo hợp đồng của pool |

SET SESSION chỉ ảnh hưởng session hiện tại; SET GLOBAL ảnh hưởng cấu hình toàn server và thường cần quyền quản trị. Ứng dụng nghiệp vụ không nên thay đổi biến GLOBAL để xử lý một request.

#### 7.1. Session variables và SQL mode

Ví dụ một đoạn code thay đổi SQL mode:

~~~sql
SELECT @@SESSION.sql_mode;
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
~~~

Nếu connection được trả về pool khi chưa khôi phục, truy vấn tiếp theo có thể chạy với SQL mode khác dự kiến. Hãy lưu giá trị ban đầu và khôi phục trong finally, hoặc dùng cơ chế reset session đã được kiểm chứng. Khi dùng SQL string để lưu/khôi phục, xử lý giá trị đầy đủ và không nối chuỗi từ dữ liệu người dùng.

Tương tự, thay đổi time_zone có thể làm kết quả đọc/ghi TIMESTAMP khác. Đặt timezone chuẩn ở cấu hình pool/connection init nếu đó là chính sách toàn ứng dụng; tránh mỗi request tùy ý thay đổi rồi quên khôi phục.

#### 7.2. Temporary table và named lock

Temporary table thuộc session và có thể tồn tại sau COMMIT. Nếu request tạo temporary table rồi trả connection về pool mà không DROP, request sau mượn cùng session có thể nhìn thấy bảng cũ hoặc bị lỗi khi tạo bảng trùng tên.

Named lock tạo bằng GET_LOCK() cũng gắn với session. Transaction rollback không tự giải phóng named lock. Luôn gọi RELEASE_LOCK() trong finally và kiểm tra kết quả. Khi session vật lý bị đóng, lock sẽ được giải phóng; nhưng connection pool có thể giữ session sống sau khi logical connection close.

### 8. Mẫu cleanup cho trạng thái tùy chỉnh

Khi một đoạn code cần đổi thuộc tính connection, lưu trạng thái cũ rồi khôi phục. Ví dụ sau giả định ứng dụng cần tạm đổi isolation level:

~~~java
try (Connection conn = dataSource.getConnection()) {
    // Ví dụ giả định pool trả connection sạch với autoCommit=true.
    int originalIsolation = conn.getTransactionIsolation();
    boolean originalAutoCommit = conn.getAutoCommit();
    boolean transactionActive = false;
    boolean safeToReturn = true;
    Throwable primaryFailure = null;
    SQLException cleanupFailure = null;

    try {
        conn.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
        conn.setAutoCommit(false);
        transactionActive = true;

        // Thực hiện công việc trong transaction.

        conn.commit();
        transactionActive = false;
    } catch (SQLException | RuntimeException ex) {
        primaryFailure = ex;
        if (transactionActive) {
            try {
                conn.rollback();
                transactionActive = false;
            } catch (SQLException rollbackError) {
                safeToReturn = false;
                ex.addSuppressed(rollbackError);
            }
        }
        throw ex;
    } finally {
        if (safeToReturn) {
            try {
                if (transactionActive) {
                    conn.rollback();
                }
                conn.setTransactionIsolation(originalIsolation);
                if (conn.getAutoCommit() != originalAutoCommit) {
                    conn.setAutoCommit(originalAutoCommit);
                }
            } catch (SQLException resetError) {
                safeToReturn = false;
                cleanupFailure = resetError;
                if (primaryFailure != null) {
                    primaryFailure.addSuppressed(resetError);
                }
            }
        }

        if (!safeToReturn) {
            // Gọi API eviction của pool đang dùng trước khi connection được tái sử dụng.
        }
        if (cleanupFailure != null && primaryFailure == null) {
            throw cleanupFailure;
        }
    }
}
~~~

Đây là skeleton minh họa; phần eviction phải được nối với API của pool cụ thể trước khi dùng production. Nếu commit ném lỗi do mất kết nối, kết quả giao dịch có thể chưa xác định dù rollback sau đó thành công; cần đối soát nghiệp vụ bằng transaction key/idempotency key. Không để exception ở finally che mất exception gốc. JDBC không có một API portable chung để yêu cầu mọi pool loại bỏ một connection logic.

Với trạng thái session tạo bằng SQL, mẫu tương tự:

1. Đọc và lưu giá trị cũ của biến/session setting.
2. Thay đổi trong phạm vi ngắn nhất có thể.
3. Chạy công việc.
4. Khôi phục trong finally, kể cả khi SQL lỗi.
5. Nếu khôi phục thất bại, không trả connection bẩn vào pool.

Nếu trạng thái có thể được cấu hình cố định cho toàn pool, hãy đặt trong cấu hình DataSource hoặc connection initialization thay vì thay đổi theo từng request.

### 9. Cấu hình reset và hành vi của pool

Mỗi pool có quy tắc thu hồi khác nhau. Khi chọn và cấu hình pool, xác minh:

- Có rollback transaction chưa commit khi logical connection close không.
- Có khôi phục autoCommit, readOnly, isolation, catalog/schema và network timeout không.
- Có reset session state phía server hay chỉ khôi phục thuộc tính JDBC mà pool theo dõi.
- Có kiểm tra connection khi mượn hoặc khi trả không; cách xử lý connection đã hỏng.
- Có loại bỏ connection khi phát hiện lỗi nghiêm trọng không.
- Có cấu hình leak detection, maximum lifetime, idle timeout và validation timeout không.

MySQL hỗ trợ giao thức reset connection để đưa session vật lý về trạng thái ban đầu mà không cần tạo socket mới. Nhưng ứng dụng không nên tự giả định Connection.close() của JDBC luôn phát lệnh reset này. Cần kiểm tra pool và driver cụ thể có dùng nó hay không, và test các trạng thái như user variable, temporary table, prepared statement và lock.

Một số thuộc tính Connector/J như cachePrepStmts, useServerPrepStmts hoặc các tùy chọn theo dõi trạng thái session ảnh hưởng cách driver quản lý statement và trạng thái nội bộ. Chúng không thay thế quy tắc đóng resource hoặc cleanup ở tầng ứng dụng. Chỉ bật/tắt sau khi đo và kiểm thử với phiên bản Connector/J đang triển khai.

### 10. Xử lý exception và connection không còn khỏe

Khi Statement/ResultSet ném SQLException, hãy phân loại lỗi:

- Lỗi SQL nghiệp vụ như duplicate key, constraint violation hoặc syntax error.
- Lỗi transaction như deadlock hoặc lock wait timeout.
- Lỗi kết nối như communications link failure, socket timeout hoặc server đã đóng session.
- Lỗi cleanup như rollback/close thất bại.

Với deadlock, MySQL thường rollback transaction bị chọn làm nạn nhân; ứng dụng có thể retry toàn transaction nếu thao tác idempotent và có giới hạn retry/backoff. Với lỗi mất kết nối trong lúc commit, kết quả có thể chưa xác định; cần đối soát bằng transaction key trước khi chạy lại.

Pool thường có cơ chế nhận diện một số lỗi connection-fatal và loại connection vật lý. Tuy nhiên, không phải mọi SQLException đều có nghĩa connection hỏng. Không tự đóng toàn bộ pool khi gặp một lỗi SQL đơn lẻ.

Connection.isClosed() chỉ cho biết trạng thái đóng theo JDBC; nó không chứng minh socket còn hoạt động. Dùng validation do pool cung cấp hoặc Connection.isValid(timeout) khi cần kiểm tra. Tránh chạy một truy vấn kiểm tra trên mỗi request nếu pool đã có cơ chế validation phù hợp.

Nếu rollback hoặc cleanup thất bại, ghi log cả exception gốc lẫn exception phụ. Với try-with-resources, exception phát sinh khi đóng tài nguyên được lưu dưới dạng suppressed exception nếu đã có exception chính; hãy giữ thông tin này trong log để điều tra.

### 11. Theo dõi connection pool và phát hiện rò rỉ

Các chỉ số quan trọng:

| Chỉ số | Ý nghĩa | Dấu hiệu cần điều tra |
|---|---|---|
| Active connections | Connection đang được ứng dụng mượn | Luôn gần maximum pool size |
| Idle connections | Connection sẵn sàng cho request | Luôn bằng 0 trong khi request chờ |
| Pending/waiting threads | Request đang chờ mượn connection | Tăng kéo dài, latency tăng |
| Connection acquisition time | Thời gian chờ lấy connection | P95/P99 tăng đột biến |
| Usage/hold time | Thời gian một request giữ connection | Truy vấn chậm hoặc xử lý ngoài DB trong lúc giữ connection |
| Leak detection | Connection mượn quá lâu chưa được close | Stack trace chỉ ra đường code không trả connection |
| Validation failures | Connection không qua kiểm tra sức khỏe | Mạng/server/pool lifetime có vấn đề |

Không tăng maximum pool size chỉ để che tình trạng giữ connection lâu. Một pool quá lớn có thể làm MySQL chịu quá nhiều concurrent session, tăng contention và giảm throughput. Tối ưu truy vấn, rút ngắn thời gian giữ connection và xử lý tài nguyên trước khi thay đổi pool size.

Đừng giữ connection trong lúc gọi HTTP service, gửi email, chờ người dùng hoặc xử lý file. Chỉ mượn connection ngay trước phần công việc database và trả lại ngay sau khi transaction/statement hoàn tất.

### 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Pool hết connection | ResultSet/Statement/Connection không được đóng hoặc truy vấn giữ lâu | Dùng try-with-resources, bật leak detection và xem stack trace |
| Request sau nhìn thấy dữ liệu/session khác | Session variable, SQL mode, timezone hoặc schema chưa được khôi phục | Kiểm tra cleanup và khả năng reset của pool |
| Lỗi commands out of sync hoặc không thực thi truy vấn kế tiếp | ResultSet/multiple results chưa đọc hết hoặc chưa đóng | Đọc hết/đóng kết quả trước khi tái sử dụng Statement/Connection |
| Server giữ nhiều prepared statement | Statement không được đóng hoặc cache cấu hình không phù hợp | Đóng PreparedStatement, kiểm tra cache và số statement trên server |
| Bộ nhớ Java tăng khi truy vấn lớn | Driver buffer toàn bộ ResultSet hoặc ứng dụng giữ object | Dùng streaming/cursor fetch phù hợp, giảm cột và xử lý theo batch |
| Temporary table đã tồn tại khi request mới chạy | Temporary table của session cũ còn tồn tại trong connection pool | DROP rõ ràng hoặc reset session đã kiểm chứng |
| Named lock bị giữ sau khi request xong | Không gọi RELEASE_LOCK và connection vật lý vẫn sống | Release trong finally, theo dõi owner và cleanup |
| Transaction bị commit ngoài ý muốn | Bật autoCommit trước khi rollback hoặc pool state không đúng | Kết thúc transaction trước, khôi phục autoCommit theo thứ tự an toàn |
| Connection close ném lỗi | Connection đã hỏng hoặc lỗi khi pool thu hồi/reset | Log suppressed exception, kiểm tra eviction và health metrics |
| Deadlock lặp lại | Thứ tự khóa không nhất quán hoặc transaction quá dài | Chuẩn hóa thứ tự cập nhật, rút ngắn transaction và retry có giới hạn |

### 13. Checklist trước khi trả connection

- [ ] Mọi ResultSet đã được đọc xong hoặc đóng.
- [ ] Mọi Statement, PreparedStatement và CallableStatement đã đóng.
- [ ] Mọi InputStream/Reader/Blob/Clob được mở từ kết quả đã được xử lý và đóng.
- [ ] Transaction đã commit hoặc rollback rõ ràng.
- [ ] Không còn transaction chưa kết thúc trước khi close.
- [ ] autoCommit, isolation, readOnly và catalog/schema được khôi phục theo baseline.
- [ ] Session variables, SQL mode, timezone và các biến session tùy chỉnh đã được dọn.
- [ ] Temporary table đã DROP hoặc session reset được xác minh.
- [ ] Named lock đã RELEASE; table lock đã UNLOCK.
- [ ] Không còn cursor, multiple result hoặc batch đang chờ xử lý.
- [ ] Nếu cleanup thất bại, connection được loại khỏi pool theo cơ chế phù hợp.
- [ ] Metrics pool và log không cho thấy connection leak kéo dài.

### 14. Bài tập thực hành

Một ứng dụng Java dùng Connector/J và HikariCP. Một request lấy connection, đặt autoCommit=false, tạo temporary table, đặt @tenant_id, gọi procedure trả hai ResultSet rồi gặp exception khi xử lý kết quả đầu tiên. Request catch exception và gọi conn.close(). Request kế tiếp nhận connection từ pool và thấy temporary table cũ.

1. Những tài nguyên JDBC nào cần được đóng và theo thứ tự nào?
2. Vì sao Connection.close() có thể không đóng session MySQL vật lý?
3. Cần rollback ở đâu và xử lý thế nào nếu rollback cũng ném SQLException?
4. Những trạng thái nào có thể còn lại ngoài autoCommit?
5. Làm thế nào bảo đảm temporary table và named lock được dọn ngay cả khi procedure lỗi?
6. Hãy viết lại đoạn code bằng try-with-resources và finally để đóng từng ResultSet, Statement và Connection.
7. Cần cấu hình hoặc kiểm thử điều gì ở HikariCP/Connector/J để xác nhận session được reset khi trả pool?
8. Bạn sẽ dùng metric nào để phân biệt connection leak với truy vấn chậm giữ connection lâu?

### 15. Nguyên tắc vận hành

Mỗi ResultSet và Statement phải có chủ sở hữu rõ ràng và được đóng ngay khi công việc kết thúc. Mỗi transaction phải được commit hoặc rollback tường minh. Với connection pool, close trả connection logic về pool; session vật lý có thể tiếp tục sống nên mọi thay đổi session cần được khôi phục hoặc reset bằng cơ chế đã kiểm chứng. Hãy dùng try-with-resources, giữ transaction ngắn, dọn temporary table/lock/session variable, theo dõi pool metrics và loại bỏ connection khi không thể xác nhận trạng thái sạch. Điều đó giúp request tiếp theo nhận được một phiên làm việc đúng trạng thái và tránh cạn connection dưới tải.

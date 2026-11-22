# SQLState, vendor code, CommunicationsException và phân loại lỗi retry

Khi ứng dụng Java làm việc với MySQL qua Connector/J, một lỗi SQL thường được biểu diễn bằng **SQLException**. Để quyết định có nên thử lại hay không, ứng dụng cần đọc ít nhất ba thông tin: SQLState, vendor error code và nguyên nhân gốc trong chuỗi exception. Với lỗi mạng như **CommunicationsException**, còn phải biết lỗi xảy ra trước khi gửi câu lệnh, trong lúc thực thi hay đúng thời điểm **COMMIT**, vì trạng thái transaction có thể chưa xác định.

Bài học thuộc module **DATABASE_MYSQL**, tập trung vào xử lý lỗi kết nối và SQL trong ứng dụng Java: phân biệt lỗi dữ liệu với lỗi tạm thời, nhận diện communications failure, quản lý connection pool và thiết kế retry có giới hạn để không tạo giao dịch trùng lặp.

## 1. SQLException chứa những thông tin nào?

Các API JDBC thường ném **SQLException** khi truy vấn, kết nối hoặc thao tác transaction gặp lỗi. Lớp này cung cấp nhiều trường thông tin:

| API | Ý nghĩa | Cách dùng |
|---|---|---|
| **getSQLState()** | Mã trạng thái theo quy ước SQLState | Phân loại nhóm lỗi ở mức tương đối chuẩn hóa |
| **getErrorCode()** | Mã lỗi riêng của driver/database (vendor code) | Nhận diện lỗi MySQL cụ thể như 1062, 1205 hoặc 1213 |
| **getMessage()** | Mô tả lỗi dành cho người vận hành | Hỗ trợ chẩn đoán; không nên dùng chuỗi message làm khóa phân loại chính |
| **getNextException()** | Exception tiếp theo trong chuỗi lỗi JDBC | Đọc thêm lỗi được driver hoặc batch operation cung cấp |
| **getCause()** | Nguyên nhân gốc theo cơ chế exception của Java | Tìm lỗi mạng, timeout hoặc lỗi ở tầng thấp hơn |

Không phải lỗi nào cũng có đủ mọi trường. Một exception do driver tạo ở phía client có thể có vendor code bằng 0 hoặc SQLState không đặc hiệu. Ngược lại, lỗi do MySQL Server trả về thường có mã lỗi MySQL và SQLState tương ứng.

Không chỉ ghi getMessage() vào log rồi bỏ qua mã lỗi. Message có thể thay đổi theo phiên bản driver, ngôn ngữ hoặc ngữ cảnh. Hãy lưu SQLState, vendor code, loại exception, nguyên nhân gốc và giai đoạn transaction.

## 2. SQLState là gì?

SQLState là mã gồm năm ký tự dùng để phân loại trạng thái hoặc lỗi theo quy ước SQL. Hai ký tự đầu xác định lớp lỗi; ba ký tự sau xác định trạng thái cụ thể trong lớp đó.

Ví dụ:

| SQLState | Nhóm | Ý nghĩa thường gặp |
|---|---|---|
| **08xxx** | Connection exception | Lỗi kết nối hoặc communications |
| **22xxx** | Data exception | Dữ liệu không phù hợp, lỗi chuyển đổi hoặc giá trị ngoài miền |
| **23xxx** | Integrity constraint violation | Vi phạm khóa hoặc ràng buộc dữ liệu |
| **28xxx** | Invalid authorization | Lỗi xác thực hoặc quyền truy cập |
| **40xxx** | Transaction rollback | Transaction bị rollback, có thể do deadlock hoặc serialization conflict |
| **42xxx** | Syntax error or access rule violation | Cú pháp SQL hoặc quyền truy cập đối tượng |
| **HYT00**, **HYT01** | Timeout trong một số driver | Mã timeout theo quy ước được một số driver sử dụng |

SQLState có tính chuẩn hóa hơn vendor code, nhưng không phải mọi driver đều ánh xạ mọi lỗi giống hệt nhau. MySQL có thể trả SQLState tổng quát như **HY000** cho một số lỗi. Vì vậy, hãy kết hợp SQLState với mã MySQL và ngữ cảnh thao tác.

### Phân loại theo hai ký tự đầu

Trong code Java, có thể lấy lớp lỗi bằng:

~~~java
String sqlState = exception.getSQLState();
String sqlStateClass =
        sqlState != null && sqlState.length() >= 2
                ? sqlState.substring(0, 2)
                : null;
~~~

Ví dụ, **08S01** thuộc lớp 08, thường biểu thị communications link failure. **23000** thuộc lớp 23, thường liên quan vi phạm constraint.

Không suy ra mọi lỗi lớp 08 đều có thể retry ngay. Một kết nối có thể bị mất sau khi server đã commit transaction; lúc đó việc gửi lại toàn bộ yêu cầu có thể tạo dữ liệu trùng.

### Các lớp exception chuẩn của JDBC

Ngoài SQLState, JDBC định nghĩa một số lớp con để mô tả tính chất lỗi:

- **SQLTransientException:** lỗi có thể hết khi thử lại mà không cần thay đổi nguyên nhân bên ngoài.
- **SQLNonTransientException:** thử lại nguyên trạng thường không giải quyết được; cần sửa dữ liệu, SQL, quyền hoặc cấu hình.
- **SQLRecoverableException:** ứng dụng có thể phục hồi bằng cách đóng connection hiện tại, lấy connection mới và thử lại thao tác phù hợp.
- **SQLTransientConnectionException** và **SQLNonTransientConnectionException:** mô tả hai nhóm lỗi kết nối tạm thời và không tạm thời.
- **SQLTransactionRollbackException:** transaction bị rollback, thường liên quan serialization failure hoặc deadlock.
- **SQLIntegrityConstraintViolationException:** vi phạm ràng buộc dữ liệu.
- **SQLSyntaxErrorException:** lỗi cú pháp hoặc truy cập đối tượng.
- **SQLTimeoutException:** thao tác vượt quá thời hạn được cấu hình.

Các lớp này hữu ích để viết code ít phụ thuộc vendor hơn, nhưng driver có thể ánh xạ lỗi cụ thể theo cách khác nhau. Vẫn cần đọc SQLState, vendor code và ngữ cảnh transaction. Một SQLTimeoutException không tự chứng minh rằng server chưa thực hiện câu lệnh; một SQLRecoverableException cũng không có nghĩa có thể gửi lại một thao tác ghi không idempotent.

## 3. Vendor code và MySQL error number

**SQLException.getErrorCode()** trả mã lỗi do vendor định nghĩa. Với Connector/J, khi MySQL Server trả lỗi, giá trị này thường tương ứng với MySQL error number.

Một số mã quan trọng:

| MySQL error code | Tên thường gặp | Ý nghĩa | Hướng xử lý |
|---:|---|---|---|
| 1062 | ER_DUP_ENTRY | Trùng khóa PRIMARY/UNIQUE | Kiểm tra nghiệp vụ hoặc idempotency; không retry mù |
| 1045 | ER_ACCESS_DENIED_ERROR | Xác thực bị từ chối | Kiểm tra user, host, mật khẩu và authentication plugin |
| 1142 | ER_TABLEACCESS_DENIED_ERROR | Thiếu quyền thao tác trên bảng | Sửa grant theo nguyên tắc tối thiểu |
| 1054 | ER_BAD_FIELD_ERROR | Không có cột được tham chiếu | Sửa SQL hoặc đồng bộ schema |
| 1064 | ER_PARSE_ERROR | SQL sai cú pháp | Sửa câu lệnh hoặc SQL được sinh ra |
| 1205 | ER_LOCK_WAIT_TIMEOUT | Hết thời gian chờ khóa | Rollback transaction, xem blocking transaction rồi cân nhắc retry |
| 1213 | ER_LOCK_DEADLOCK | InnoDB phát hiện deadlock | Retry toàn bộ transaction nếu nghiệp vụ cho phép |
| 2002 | CR_CONNECTION_ERROR | Không tạo được kết nối tới socket/local endpoint | Kiểm tra endpoint, socket, service và mạng |
| 2003 | CR_CONN_HOST_ERROR | Không kết nối được tới MySQL host | Kiểm tra DNS, route, firewall, port và server |
| 2006 | CR_SERVER_GONE_ERROR | Server đã đóng hoặc kết nối không còn sử dụng được | Loại connection khỏi pool; xác định thao tác có thể đã được thực thi hay chưa |
| 2013 | CR_SERVER_LOST | Mất kết nối trong lúc thực hiện thao tác | Kiểm tra giai đoạn lỗi; kết quả commit có thể chưa xác định |

Mã 2002, 2003, 2006 và 2013 là client error code của MySQL. Tùy điểm phát sinh, driver có thể gói chúng trong một SQLException hoặc một exception chuyên biệt. Không giả định mọi lỗi mạng đều có đúng một vendor code.

Vendor code là số nguyên, vì vậy hãy so sánh bằng **getErrorCode()**, không parse số từ message. Nếu dùng proxy hoặc gateway giữa ứng dụng và MySQL, lỗi có thể đến từ proxy thay vì MySQL Server; khi đó vendor code và SQLState có thể khác.

## 4. CommunicationsException là gì?

**CommunicationsException** là exception chuyên biệt của Connector/J dùng để biểu diễn sự cố giao tiếp giữa ứng dụng Java và MySQL Server. Nó thường xuất hiện khi socket bị đóng, kết nối bị reset, server không phản hồi trong thời gian chờ hoặc driver không thể gửi/nhận dữ liệu qua kết nối.

Tên lớp thường gặp trong Connector/J hiện đại:

~~~java
com.mysql.cj.jdbc.exceptions.CommunicationsException
~~~

Đây là chi tiết riêng của Connector/J. Ứng dụng có thể bắt **SQLException** để giữ tính tương thích JDBC, sau đó kiểm tra SQLState, cause chain và tên exception cụ thể khi cần chẩn đoán.

Một số nguyên nhân phổ biến:

- MySQL Server restart, crash hoặc bị failover.
- Firewall, NAT, load balancer hoặc proxy đóng kết nối idle.
- Mạng giữa ứng dụng và database bị gián đoạn hoặc packet loss.
- DNS trỏ đến địa chỉ không còn hợp lệ.
- Server quá tải, không trả lời trong timeout mà client cấu hình.
- Truy vấn hoặc result set kéo dài vượt giới hạn của một thành phần mạng.
- Ứng dụng dùng lại connection đã bị server hoặc pool đóng.

### SQLState và vendor code của communications failure

Communications link failure thường được ánh xạ vào SQLState lớp 08, thường gặp là **08S01**. Tuy nhiên, exception có thể do driver tạo trước khi nhận được phản hồi từ server; khi đó vendor code có thể bằng 0 hoặc không phải mã lỗi server.

Vì vậy:

1. Đọc SQLState nếu có.
2. Đọc vendor code nếu có.
3. Kiểm tra loại exception và toàn bộ cause chain.
4. Ghi nhận thời điểm và giai đoạn thao tác.
5. Đối chiếu log ứng dụng, log MySQL, proxy và hạ tầng mạng.

Không phân loại chỉ dựa trên việc message chứa cụm communications link failure. Một lỗi tương tự có thể xuất hiện ở nhiều tầng kết nối khác nhau.

## 5. Phân biệt lỗi kết nối theo thời điểm

Điểm quan trọng nhất khi xử lý communications failure là xác định server có thể đã thực hiện thao tác hay chưa.

| Thời điểm mất kết nối | Điều có thể kết luận | Hành động |
|---|---|---|
| Trước khi gửi câu lệnh | Thường chưa có thao tác nào đến server | Tạo connection mới và thử lại nếu request còn hạn |
| Khi đang gửi câu lệnh | Không biết server đã nhận đủ câu lệnh chưa | Kiểm tra trạng thái; không giả định thao tác chưa chạy |
| Khi server đang thực thi | Server có thể đã thực hiện một phần hoặc toàn bộ công việc | Với transaction tường minh, xử lý trạng thái connection và transaction; không dùng lại connection lỗi |
| Sau khi gửi COMMIT nhưng trước khi nhận phản hồi | Commit có thể đã thành công dù client không nhận được ACK | Xem kết quả là chưa xác định; tra cứu bằng idempotency key hoặc mã nghiệp vụ |
| Khi đọc ResultSet | Câu lệnh có thể đã hoàn tất nhưng dữ liệu trả về chưa được nhận hết | Đóng/loại connection lỗi; chỉ chạy lại truy vấn đọc nếu an toàn và còn trong deadline |

### Vì sao lỗi lúc COMMIT nguy hiểm?

Giả sử ứng dụng gửi:

~~~sql
START TRANSACTION;
INSERT INTO orders(order_id, customer_id, total_amount)
VALUES (90001, 42, 125000);
COMMIT;
~~~

Server có thể đã ghi transaction và commit thành công, nhưng mạng đứt trước khi phản hồi tới Java. Client nhận CommunicationsException và không biết chắc đơn hàng đã được tạo hay chưa.

Nếu ứng dụng chạy lại INSERT với một mã đơn hàng khác, khách hàng có thể bị tạo hai đơn. Nếu chạy lại cùng order_id có unique key, MySQL có thể trả lỗi duplicate key; đó là tín hiệu cần tra cứu kết quả cũ, không phải lý do để thử mã mới.

Giải pháp là gắn một request ID/idempotency key ổn định với yêu cầu nghiệp vụ, lưu nó trong cùng transaction với đơn hàng và tra cứu trạng thái trước khi quyết định gửi lại.

## 6. Các nhóm lỗi và quyết định retry

Retry nên dựa trên loại lỗi, trạng thái transaction, tính idempotent của thao tác và thời gian còn lại của request. Bảng dưới đây là định hướng cho ứng dụng JDBC với MySQL:

| Nhóm lỗi | Ví dụ | Retry tự động? | Điều kiện |
|---|---|---|---|
| Deadlock | SQLState 40001, MySQL 1213 | Có thể | Rollback toàn transaction, chạy lại từ đầu |
| Lock wait timeout | MySQL 1205, thường SQLState HY000 | Có thể có điều kiện | Chủ động rollback toàn transaction, kiểm tra tải và giới hạn số lần |
| Communications failure | SQLState lớp 08, CommunicationsException, 2006/2013 | Không mặc định | Cần connection mới; xác định thao tác và khả năng commit đã xảy ra |
| Query timeout | SQLTimeoutException hoặc timeout từ driver | Có điều kiện | Hủy/rollback transaction, xác minh trạng thái và thử lại chỉ khi an toàn |
| Constraint violation | SQLState lớp 23, MySQL 1062 | Thường không | Xử lý theo quy tắc nghiệp vụ hoặc idempotency |
| Syntax/schema error | SQLState lớp 42, MySQL 1064/1054 | Không | Sửa SQL hoặc schema |
| Authentication/authorization | SQLState lớp 28, MySQL 1045/1142 | Không | Sửa cấu hình hoặc grant |
| Data conversion | SQLState lớp 22 | Không | Sửa dữ liệu hoặc mapping |

### Retry deadlock 1213

InnoDB đã chọn transaction làm nạn nhân và rollback transaction đó để giải phóng deadlock. Ứng dụng có thể thử lại toàn bộ transaction sau một khoảng chờ ngắn. Không chỉ chạy lại câu SQL gây deadlock, vì các câu lệnh trước đó thuộc cùng transaction đã bị rollback.

### Retry lock wait timeout 1205

Mặc định, khi lock wait timeout xảy ra, MySQL thường rollback statement bị timeout; transaction có thể vẫn mở. Biến **innodb_rollback_on_timeout** có thể thay đổi hành vi để rollback toàn transaction. Vì vậy, ứng dụng nên gọi **rollback()** cho toàn transaction trước khi retry, tránh tiếp tục trên một transaction có trạng thái dở dang.

### Communications failure

Không retry chỉ vì SQLState bắt đầu bằng 08. Trước hết loại bỏ connection lỗi khỏi pool và lấy connection mới. Nếu thao tác là truy vấn đọc có thể lặp lại, việc retry thường đơn giản hơn. Nếu là ghi dữ liệu hoặc lỗi tại COMMIT, cần idempotency hoặc cơ chế xác minh kết quả.

### Constraint violation

Lỗi 1062 có thể có nghĩa yêu cầu đã được xử lý trước đó, hoặc dữ liệu đầu vào vi phạm quy tắc duy nhất. Ứng dụng cần kiểm tra khóa nghiệp vụ và trả kết quả phù hợp. Không retry cùng câu lệnh vô hạn.

## 7. Đọc SQLException chain và cause chain

Một lỗi có thể gồm nhiều exception liên kết. Ví dụ, **BatchUpdateException** có thể chứa update counts và exception tiếp theo; một communications failure có thể bọc nguyên nhân socket hoặc timeout.

Đoạn code sau duyệt cả getNextException() và getCause():

~~~java
import java.sql.SQLException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

public final class SqlExceptionLogger {
    private SqlExceptionLogger() {}

    public static void logChain(SQLException root) {
        Set<Throwable> seen =
                Collections.newSetFromMap(new IdentityHashMap<>());

        for (SQLException sql = root;
             sql != null && seen.add(sql);
             sql = sql.getNextException()) {
            System.err.printf(
                    "SQLState=%s vendorCode=%d type=%s message=%s%n",
                    sql.getSQLState(),
                    sql.getErrorCode(),
                    sql.getClass().getName(),
                    sql.getMessage()
            );

            Throwable cause = sql.getCause();
            while (cause != null && seen.add(cause)) {
                System.err.printf(
                        "Cause type=%s message=%s%n",
                        cause.getClass().getName(),
                        cause.getMessage()
                );
                cause = cause.getCause();
            }
        }
    }
}
~~~

Tập **seen** tránh lặp vô hạn nếu các exception tham chiếu vòng. Trong production, dùng logger có cấu trúc thay vì System.err, đồng thời che thông tin nhạy cảm. Không log mật khẩu, URL có credential, dữ liệu cá nhân hoặc nội dung truy vấn chứa bí mật.

## 8. Phân loại lỗi trong Java

Một bộ phân loại nên trả về nhóm hành động, không chỉ một boolean retryable. Ví dụ:

~~~java
import java.sql.SQLException;
import java.util.ArrayDeque;
import java.util.Collections;
import java.util.Deque;
import java.util.IdentityHashMap;
import java.util.Set;

enum SqlFailureKind {
    RETRY_TRANSACTION,
    CONNECTION_FAILURE,
    CONSTRAINT_VIOLATION,
    AUTH_OR_PERMISSION,
    SQL_OR_SCHEMA,
    DATA_ERROR,
    OTHER
}

final class MySqlErrorClassifier {
    static SqlFailureKind classify(SQLException root) {
        if (root == null) {
            return SqlFailureKind.OTHER;
        }

        Deque<Throwable> pending = new ArrayDeque<>();
        Set<Throwable> seen =
                Collections.newSetFromMap(new IdentityHashMap<>());
        pending.add(root);

        while (!pending.isEmpty()) {
            Throwable current = pending.removeFirst();
            if (current == null || !seen.add(current)) {
                continue;
            }

            if (current instanceof SQLException) {
                SQLException e = (SQLException) current;
                int code = e.getErrorCode();
                String state = e.getSQLState();

                if (code == 1213 || "40001".equals(state) || code == 1205) {
                    return SqlFailureKind.RETRY_TRANSACTION;
                }

                if (code == 2002 || code == 2003 ||
                    code == 2006 || code == 2013 ||
                    (state != null && state.startsWith("08"))) {
                    return SqlFailureKind.CONNECTION_FAILURE;
                }

                if (code == 1062 ||
                    (state != null && state.startsWith("23"))) {
                    return SqlFailureKind.CONSTRAINT_VIOLATION;
                }

                if (code == 1045 || code == 1142 ||
                    (state != null && state.startsWith("28"))) {
                    return SqlFailureKind.AUTH_OR_PERMISSION;
                }

                if (code == 1064 || code == 1054 ||
                    (state != null && state.startsWith("42"))) {
                    return SqlFailureKind.SQL_OR_SCHEMA;
                }

                if (state != null && state.startsWith("22")) {
                    return SqlFailureKind.DATA_ERROR;
                }

                SQLException next = e.getNextException();
                if (next != null) {
                    pending.addLast(next);
                }
            }

            Throwable cause = current.getCause();
            if (cause != null) {
                pending.addLast(cause);
            }
        }

        return SqlFailureKind.OTHER;
    }
}
~~~

Đây là ví dụ khởi đầu, không phải danh sách đầy đủ mã lỗi MySQL. Trong ứng dụng thực tế, cần:

- Duyệt cả cause chain và SQLException chain.
- Kiểm tra **BatchUpdateException** và update counts khi dùng batch.
- Phân biệt communications failure theo giai đoạn thao tác.
- Không coi mọi lỗi timeout là có thể retry.
- Bổ sung mã lỗi và SQLState phù hợp với workload và phiên bản driver.

Không nên gộp CONNECTION_FAILURE và RETRY_TRANSACTION thành một hành động. Lỗi kết nối yêu cầu thay connection và có thể cần xác minh kết quả nghiệp vụ; deadlock yêu cầu chạy lại transaction mới.

## 9. Retry transaction đúng cách

Với deadlock hoặc lỗi certification/transaction rollback có thể retry, phải bắt đầu một transaction mới, đọc lại dữ liệu và đánh giá lại điều kiện nghiệp vụ. Một vòng lặp retry có giới hạn:

~~~java
int maxAttempts = 4;

for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            reserveInventory(connection, sku, quantity);
            createOrder(connection, requestId, sku, quantity);
            connection.commit();
            return;
        } catch (SQLException error) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                error.addSuppressed(rollbackError);
            }

            SqlFailureKind kind = MySqlErrorClassifier.classify(error);
            boolean retry =
                    kind == SqlFailureKind.RETRY_TRANSACTION;

            if (!retry || attempt == maxAttempts) {
                throw error;
            }
        }
    }

    backoffWithJitter(attempt);
}
~~~

**reserveInventory**, **createOrder** và **backoffWithJitter** là hàm nghiệp vụ minh họa. Vòng lặp trên chỉ retry các lỗi transaction đã được phân loại. Communications failure cần nhánh xử lý riêng vì kết quả commit có thể chưa xác định.

Chính sách backoff nên có:

- Số lần thử tối đa.
- Thời gian chờ tăng dần.
- Jitter ngẫu nhiên để tránh nhiều client retry cùng lúc.
- Deadline tổng thể của request.
- Metric về số lần retry, mã lỗi và số request thất bại cuối cùng.

Không retry vô hạn hoặc giữ một transaction mở trong khi chờ backoff. Rollback và giải phóng connection trước khi chờ.

## 10. Xử lý CommunicationsException và connection pool

Khi gặp communications failure, connection hiện tại có thể đã hỏng hoặc không còn đồng bộ trạng thái với server. Không đưa connection đó trở lại pool như một kết nối khỏe mạnh.

Quy trình xử lý:

1. Ghi nhận SQLState, vendor code, loại exception, cause chain và giai đoạn thao tác.
2. Đánh dấu connection không còn sử dụng được; đóng connection và để pool loại bỏ nó.
3. Nếu transaction đang mở, thử rollback khi còn khả năng giao tiếp. Nếu không thể rollback, đóng connection để server xử lý session bị mất.
4. Lấy connection mới cho lần thao tác tiếp theo.
5. Nếu lỗi xảy ra trong lúc commit, tra cứu trạng thái nghiệp vụ bằng idempotency key trước khi gửi lại.
6. Theo dõi lỗi theo host, pool, thời điểm và topology để tìm nguyên nhân hạ tầng.

### Kiểm tra pool

Với HikariCP hoặc pool tương tự, kiểm tra:

- Validation và cách pool phát hiện connection đã bị đóng.
- **maxLifetime** so với thời hạn connection của MySQL, proxy, firewall hoặc load balancer.
- **keepaliveTime** nếu pool và phiên bản hỗ trợ.
- **connectionTimeout** và thời gian chờ lấy connection.
- **socketTimeout** và timeout ở proxy/network.
- Số connection đang active, idle, pending và số lần tạo connection mới.

Đặt maxLifetime thấp hơn giới hạn connection idle/maximum của thành phần hạ tầng có thể giảm việc lấy lại connection đã hết hạn. Không chọn timeout tùy tiện; đo latency, thời gian query và chính sách network trước khi điều chỉnh.

### Phân biệt timeout

| Timeout | Tầng | Ý nghĩa |
|---|---|---|
| Connection timeout | Mở kết nối | Không thiết lập được connection trong thời hạn |
| Socket timeout | Đọc/ghi socket | Không nhận được dữ liệu trong thời gian chờ |
| Query timeout | JDBC Statement | Truy vấn vượt thời gian thực thi được chỉ định ở client |
| Lock wait timeout | InnoDB | Chờ khóa vượt giới hạn của server |
| Transaction timeout | Framework/ứng dụng | Transaction vượt giới hạn thời gian nghiệp vụ |

Các timeout có thể chồng lấn nhưng không tương đương. Ví dụ, socketTimeout không phải cách thay thế innodb_lock_wait_timeout, và Statement.setQueryTimeout() không bảo đảm transaction đã rollback hoàn toàn khi client nhận exception.

## 11. Idempotency khi kết quả commit chưa xác định

Khi mạng đứt đúng lúc commit, ứng dụng không thể biết chắc transaction đã hoàn tất hay chưa. Một giải pháp phổ biến là tạo idempotency key ổn định cho mỗi yêu cầu nghiệp vụ.

Ví dụ bảng lưu yêu cầu đã xử lý:

~~~sql
CREATE TABLE processed_requests (
  request_id VARCHAR(64) PRIMARY KEY,
  result_code VARCHAR(32) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
~~~

Trong cùng transaction:

1. Ghi request_id vào bảng idempotency.
2. Thực hiện thay đổi nghiệp vụ như tạo đơn hàng hoặc trừ tồn kho.
3. Lưu kết quả nghiệp vụ gắn với request ID.
4. Commit.

Nếu client mất kết nối sau commit, lần gọi lại dùng cùng request ID. Ứng dụng tra cứu bản ghi đã xử lý và trả lại kết quả cũ. Unique key ngăn cùng một request được xử lý hai lần.

Việc ghi idempotency key phải nằm trong cùng transaction với thay đổi nghiệp vụ. Nếu ghi ở một transaction riêng, có thể xảy ra tình trạng key đã tồn tại nhưng nghiệp vụ chưa hoàn tất, hoặc nghiệp vụ đã commit nhưng key chưa được ghi.

Với tác dụng phụ ngoài database như gửi email, gọi thanh toán hoặc phát message, cân nhắc transactional outbox. Ghi sự kiện outbox trong cùng transaction rồi để worker gửi sau commit; worker cũng cần idempotency để xử lý trường hợp gửi lại.

## 12. BatchUpdateException và lỗi trong batch

Khi chạy JDBC batch, driver có thể ném **BatchUpdateException**. Ngoài SQLState và vendor code, exception này cung cấp **getUpdateCounts()** để xem trạng thái thực thi của các lệnh trong batch.

~~~java
try {
    statement.executeBatch();
} catch (BatchUpdateException error) {
    int[] counts = error.getUpdateCounts();
    for (int i = 0; i < counts.length; i++) {
        System.err.printf("batch[%d] updateCount=%d%n", i, counts[i]);
    }
    throw error;
}
~~~

Ý nghĩa của update count phụ thuộc driver và chế độ tiếp tục hay dừng khi gặp lỗi. Giá trị **Statement.EXECUTE_FAILED** biểu thị lệnh thất bại; **Statement.SUCCESS_NO_INFO** biểu thị thành công nhưng driver không cung cấp số hàng chính xác.

Nếu batch chạy trong transaction tường minh và ứng dụng rollback toàn bộ khi có lỗi, có thể đánh giá retry toàn batch sau khi xác định lỗi là tạm thời. Nếu auto-commit đang bật, một phần lệnh có thể đã commit trước khi batch thất bại. Không chạy lại toàn batch mà không kiểm tra trạng thái từng yêu cầu hoặc có cơ chế idempotency.

## 13. Ghi log và quan sát lỗi hiệu quả

Một log lỗi kết nối/SQL hữu ích nên có:

- Timestamp và correlation ID/request ID.
- Tên service, instance và pool.
- Database endpoint hoặc tên logical datasource, không ghi credential.
- SQLState, vendor code, exception class và cause chain.
- Giai đoạn thao tác: lấy connection, execute, đọc result, commit hoặc rollback.
- Transaction có auto-commit hay không.
- Số lần retry và thời gian chờ.
- Kết quả xác minh idempotency nếu commit chưa rõ.

Metric nên theo dõi:

- Tỷ lệ lỗi SQL theo SQLState class và vendor code.
- Số communications failure theo endpoint.
- Số connection bị loại khỏi pool.
- Số lần connection được tạo lại.
- Query timeout, lock wait timeout và deadlock.
- Retry attempts, retry exhaustion và latency tổng.
- Số request ở trạng thái kết quả commit chưa xác định.

Không log nguyên câu SQL cùng bind values nếu có dữ liệu nhạy cảm. Có thể log query fingerprint, tên thao tác hoặc bảng nghiệp vụ cùng correlation ID.

## 14. Quy trình chẩn đoán theo tình huống

### Tình huống A: SQLState 23000, vendor code 1062

Đây thường là duplicate key. Kiểm tra khóa unique nào vi phạm, request ID có trùng hay không và thao tác trước đó có thể đã thành công không. Nếu đây là lần gửi lại cùng request, tra cứu kết quả cũ. Nếu dữ liệu đầu vào thật sự vi phạm nghiệp vụ, trả lỗi phù hợp thay vì retry.

### Tình huống B: SQLState 40001, vendor code 1213

InnoDB đã phát hiện deadlock. Ghi nhận transaction và truy vấn liên quan, rollback toàn transaction, chờ backoff ngắn rồi thực hiện lại từ đầu với dữ liệu mới. Nếu xảy ra thường xuyên, xem lại thứ tự cập nhật hàng và thời gian giữ khóa.

### Tình huống C: SQLState HY000, vendor code 1205

Đây thường là lock wait timeout. Kiểm tra transaction đang giữ khóa, thời gian chạy và **innodb_lock_wait_timeout**. Rollback toàn transaction trong ứng dụng trước khi retry; nếu hệ thống đang quá tải, tăng retry có thể làm tình hình xấu hơn.

### Tình huống D: SQLState 08S01 hoặc CommunicationsException

Kiểm tra thời điểm lỗi, trạng thái server, proxy, firewall, DNS và timeout. Loại connection khỏi pool. Nếu lỗi xảy ra trước khi gửi thao tác, có thể thử lại trên connection mới. Nếu xảy ra khi commit, xác minh kết quả bằng request ID trước khi gửi lại.

### Tình huống E: No suitable driver hoặc lỗi khởi tạo datasource

Đây thường là lỗi dependency/classpath hoặc URL, không phải lỗi SQL cần retry. Kiểm tra Connector/J có trong runtime, dependency tree, tiền tố jdbc:mysql: và cấu hình DataSource.

## 15. Checklist thiết kế xử lý lỗi

- [ ] Đọc SQLState và vendor code thay vì chỉ đọc message.
- [ ] Duyệt getNextException() và cause chain.
- [ ] Ghi lại exception class và giai đoạn transaction.
- [ ] Phân biệt lỗi deadlock, lock timeout, communications và constraint.
- [ ] Retry deadlock bằng transaction mới và chạy lại toàn bộ logic.
- [ ] Với lock timeout, rollback toàn transaction trước khi retry.
- [ ] Không retry mù khi lỗi xảy ra trong lúc COMMIT.
- [ ] Dùng idempotency key cho yêu cầu ghi có thể được gửi lại.
- [ ] Loại connection hỏng khỏi pool và dùng connection mới.
- [ ] Đặt retry tối đa, backoff, jitter và deadline.
- [ ] Kiểm tra BatchUpdateException và update counts khi chạy batch.
- [ ] Có metric và log để nhận diện lỗi lặp lại.

## Tài liệu tham khảo

- [Java SE — SQLException](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/SQLException.html)
- [Java SE — SQLState](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/package-summary.html)
- [MySQL Connector/J Developer Guide — Exception Handling](https://dev.mysql.com/doc/connector-j/en/connector-j-exceptions.html)
- [MySQL Reference Manual — Server Error Message Reference](https://dev.mysql.com/doc/mysql-errors/8.0/en/server-error-reference.html)
- [MySQL Reference Manual — Client Error Message Reference](https://dev.mysql.com/doc/mysql-errors/8.0/en/client-error-reference.html)
- [MySQL Reference Manual — InnoDB Error Handling](https://dev.mysql.com/doc/refman/8.0/en/innodb-error-handling.html)

## Kết luận

SQLState cho biết nhóm lỗi, vendor code giúp nhận diện lỗi MySQL cụ thể, còn cause chain và thời điểm phát sinh giúp xác định nguyên nhân thực tế. Deadlock 1213 thường có thể retry toàn transaction; lock timeout 1205 cần rollback rõ ràng trước khi thử lại; communications failure cần connection mới và phải xác minh kết quả nếu lỗi xảy ra trong lúc commit. Hãy xây bộ phân loại dựa trên SQLState, mã lỗi và ngữ cảnh transaction, kết hợp retry có giới hạn, idempotency key và giám sát connection pool để ứng dụng phục hồi an toàn.

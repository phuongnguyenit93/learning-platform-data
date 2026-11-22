# Phân biệt timeout của ứng dụng với việc kết thúc giao dịch tại máy chủ

Khi một API, job hoặc ứng dụng báo timeout, điều đó chỉ cho biết một thành phần đã ngừng chờ trong thời hạn được cấu hình. Nó không tự chứng minh rằng câu SQL đã dừng trên database, transaction đã ROLLBACK, hay COMMIT đã thất bại.

Một yêu cầu có thể đi qua nhiều tầng: client, API gateway, application server, connection pool, JDBC driver, mạng và database. Mỗi tầng có timeout riêng và có thể chỉ hủy việc chờ ở chính tầng đó. Việc gửi tín hiệu hủy xuống tầng dưới là một thao tác khác; tín hiệu có thể đến muộn, không đến được hoặc chỉ hủy câu lệnh hiện tại mà vẫn để transaction mở.

Điểm cần phân biệt là:

- **Timeout ở ứng dụng:** ứng dụng hết thời gian chờ và quyết định trả lỗi, ngừng chờ hoặc hủy công việc.
- **Cancel statement:** database nhận được yêu cầu hủy câu SQL đang chạy và dừng câu lệnh theo khả năng của hệ quản trị.
- **Rollback transaction:** database hoàn tác các thay đổi chưa COMMIT trong transaction.
- **Kết quả COMMIT không xác định ở client:** server có thể đã commit nhưng phản hồi bị mất trước khi ứng dụng nhận được.

Các sự kiện này có thể xảy ra gần nhau nhưng không đồng nghĩa. Khi tích hợp ứng dụng với database, cần thiết kế timeout, cancellation, transaction boundary và retry như những phần riêng biệt của cùng một quy trình.

## 1. Timeout tồn tại ở nhiều tầng

Một request có thể có nhiều giới hạn thời gian độc lập.

| Tầng | Ví dụ timeout | Điều gì có thể kết thúc? |
|---|---|---|
| Client/browser/mobile | Request deadline | Client ngừng chờ response |
| API gateway/load balancer | Upstream timeout | Gateway ngừng chờ backend hoặc đóng kết nối |
| Application server | Request/async timeout | Server ngừng xử lý request hoặc đánh dấu request hết hạn |
| Application code | Future/task timeout | Thread gọi không chờ thêm kết quả |
| Connection pool | Connection acquisition timeout | Ứng dụng không lấy được connection trong thời hạn |
| JDBC/DB driver | Query/command timeout | Driver yêu cầu hủy câu lệnh hoặc dừng chờ |
| Socket/network | Read/write timeout | Một thao tác I/O hết thời gian |
| Database | Statement/query timeout | Server hủy câu lệnh theo cấu hình |
| Database | Lock wait timeout | Server kết thúc yêu cầu đang chờ khóa |
| Database | Idle transaction/session timeout | Server chấm dứt session hoặc transaction đang nhàn rỗi theo chính sách |

Một timeout ở tầng trên không tự động đặt lại hay thay đổi timeout ở tầng dưới. Ví dụ, gateway trả 504 sau 30 giây không có nghĩa database đã nhận lệnh cancel ở giây thứ 30.

### 1.1. Connection acquisition timeout không phải query timeout

Giả sử pool chỉ có 20 connection và cả 20 connection đang được sử dụng. Request thứ 21 chờ lấy connection.

Nếu pool có connectionTimeout = 2 giây, request có thể thất bại sau hai giây mà chưa gửi câu SQL nào đến database.

Đây là lỗi chờ connection trong pool. Không có câu lệnh database nào cần được hủy bởi timeout đó.

Ngược lại, nếu request đã lấy được connection và gửi UPDATE chạy 20 giây, pool acquisition timeout không còn liên quan. Cần query/statement timeout hoặc cơ chế hủy khác.

### 1.2. Query timeout không giống socket timeout

Query timeout thường là chính sách ở driver hoặc thư viện database, có thể gửi yêu cầu cancel cho server. Socket read timeout là giới hạn cho một lần đọc dữ liệu từ socket.

Nếu socket timeout xảy ra, client có thể mất khả năng nhận response. Server có thể vẫn đang chạy câu SQL hoặc đã hoàn tất nhưng response chưa đến nơi.

Socket timeout không nhất thiết gửi lệnh cancel hợp lệ. Một số driver cố gắng đóng connection hoặc gửi cancellation khi phát hiện timeout; hành vi phụ thuộc driver và cấu hình.

### 1.3. Request timeout không nhất thiết dừng công việc nền

Một request HTTP có thể khởi chạy một tác vụ bất đồng bộ. Client ngừng chờ sau 10 giây nhưng worker vẫn tiếp tục chạy vì tác vụ đã được đưa vào executor hoặc queue.

Tương tự, thread gọi Future.get với timeout có thể ngừng chờ Future nhưng không hủy task. Ngay cả khi gọi Future.cancel(true), interrupt chỉ có tác dụng nếu task và các thư viện bên dưới phản ứng với interrupt.

Vì vậy, cần xác định timeout chỉ kết thúc việc chờ của caller hay thực sự yêu cầu hủy công việc.

## 2. Một timeline điển hình: ứng dụng timeout nhưng database vẫn chạy

Giả sử ứng dụng gửi một truy vấn tổng hợp mất 40 giây. Request deadline là 15 giây.

~~~text
Thời gian     Ứng dụng                  Database
---------------------------------------------------------------
t0            Gửi SELECT  ------------> Nhận và chạy SELECT
t1            Chờ response              Đang đọc và tính toán
...
t15           Hết request timeout       Vẫn đang chạy
t16           Trả lỗi timeout            Vẫn đang chạy
...
t40                                      Hoàn tất câu SQL
t41                                      Gửi response (có thể không
                                         còn client nhận)
~~~

Ở thời điểm t15, chỉ có deadline của ứng dụng đã hết. Nếu không có cancellation được truyền đến và xử lý ở server, database có thể tiếp tục dùng CPU, I/O và giữ tài nguyên.

Nếu câu lệnh nằm trong transaction đã mở, transaction còn có thể giữ khóa cho đến khi được COMMIT, ROLLBACK, session bị kết thúc hoặc server áp dụng một timeout khác.

### 2.1. Hệ quả của việc chỉ ngừng chờ

Nếu ứng dụng chỉ trả timeout cho người dùng rồi bỏ mặc connection/task, có thể xảy ra:

- Database tiếp tục chạy câu SQL không còn ai cần kết quả.
- Transaction tiếp tục giữ khóa và chặn request khác.
- Connection bị giữ trong pool lâu hơn dự kiến.
- Pool cạn connection dù phía client đã nhận lỗi.
- Retry từ client tạo thêm một truy vấn thứ hai trong khi truy vấn đầu vẫn chạy.
- Hai lần xử lý cùng một nghiệp vụ cạnh tranh và có thể tạo tác dụng phụ trùng.

Đây là lý do timeout cần được thiết kế cùng cancellation và giới hạn tài nguyên.

### 2.2. Hủy câu lệnh không đồng nghĩa rollback toàn transaction

Một yêu cầu cancel có thể chỉ kết thúc câu SQL đang chạy. Transaction có thể vẫn mở, tùy DBMS và trạng thái lỗi.

~~~sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

-- Một câu SELECT dài bị timeout/cancel.

-- Transaction có thể vẫn giữ các thay đổi và khóa trước đó
-- cho đến khi ứng dụng ROLLBACK hoặc COMMIT hợp lệ.
~~~

Nếu ứng dụng bắt lỗi timeout rồi trả connection về pool mà không kết thúc transaction, connection có thể được tái sử dụng trong trạng thái không mong muốn.

Hãy xem cancellation, rollback và giải phóng connection là các bước riêng biệt trong luồng xử lý.

## 3. Các kiểu hủy và ý nghĩa của chúng

### 3.1. Caller ngừng chờ

Ví dụ:

~~~java
Future<Result> future = executor.submit(task);

try {
    return future.get(5, TimeUnit.SECONDS);
} catch (TimeoutException ex) {
    // Caller hết thời gian chờ.
}
~~~

TimeoutException cho biết get không nhận được kết quả trong năm giây. Nó không tự hủy task.

Nếu muốn yêu cầu hủy:

~~~java
future.cancel(true);
~~~

Lệnh này cố gắng hủy task và có thể gửi interrupt đến thread đang chạy. Task cần hợp tác với interrupt; JDBC driver và socket I/O có hành vi riêng. Không thể suy ra database chắc chắn đã dừng.

### 3.2. Hủy câu SQL qua driver

Một số API driver có phương thức cancel, ví dụ JDBC Statement.cancel(). Driver có thể gửi tín hiệu hủy đến database bằng kênh hoặc giao thức mà sản phẩm hỗ trợ.

Cancel là yêu cầu bất đồng bộ trong nhiều triển khai. Khi cancel() trả về, điều đó không nhất thiết chứng minh server đã rollback xong hoặc mọi tài nguyên đã được giải phóng.

Ứng dụng cần xử lý kết quả của câu lệnh, trạng thái transaction và connection sau khi cancellation hoàn tất.

Không nên gọi cancel trên một Statement đang được thread khác sử dụng mà không có cơ chế quản lý lifecycle rõ ràng. Cần phối hợp thread sở hữu statement, connection và transaction.

### 3.3. Đóng connection

Đóng connection có thể khiến server nhận ra session bị mất và dừng công việc gắn với session đó. Nhưng:

- Việc phát hiện mất kết nối có thể cần thời gian.
- Connection có thể đã được proxy hoặc pool quản lý theo cách khác.
- Driver có thể phải đóng socket mà không gửi được lệnh cancel riêng.
- Nếu COMMIT đã được server xử lý, đóng connection không thể hoàn tác một commit đã hoàn tất.
- Một số DBMS chỉ rollback transaction khi session thực sự kết thúc.

Đóng connection là biện pháp giải phóng session khi cần, nhưng không phải một xác nhận tức thời rằng transaction chưa commit.

### 3.4. Rollback transaction

ROLLBACK là lệnh yêu cầu database hoàn tác các thay đổi chưa commit của transaction hiện tại.

~~~sql
BEGIN;

UPDATE inventory
SET available = available - 1
WHERE sku = 'BOOK-01';

ROLLBACK;
~~~

Sau khi rollback thành công, các thay đổi transaction chưa xác nhận được hoàn tác theo semantics của DBMS. Nếu connection đã mất hoặc trạng thái transaction không rõ, ứng dụng có thể không nhận được xác nhận rollback dù server cuối cùng đã tự rollback khi session kết thúc.

### 3.5. Commit

COMMIT là điểm mà transaction trở thành đã xác nhận theo durability/transaction semantics của database.

~~~sql
BEGIN;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

COMMIT;
~~~

Nếu client nhận được phản hồi COMMIT thành công, ứng dụng có thể coi transaction đã commit theo hợp đồng của database.

Nếu client timeout hoặc mất kết nối trong lúc COMMIT, kết quả có thể không xác định từ góc nhìn client. Server có thể đã commit nhưng response bị mất; hoặc transaction chưa commit và bị rollback khi session kết thúc.

Đây là trường hợp cần xử lý đặc biệt, không thể mặc định timeout đồng nghĩa rollback.

## 4. Ba vùng thời gian quanh COMMIT

Một cách hữu ích để phân tích là xác định timeout xảy ra ở thời điểm nào.

### 4.1. Timeout trước khi gửi COMMIT

~~~text
BEGIN
  |
  v
UPDATE / INSERT
  |
  v
Ứng dụng timeout trước khi gửi COMMIT
  |
  v
ROLLBACK hoặc session bị kết thúc
~~~

Nếu ứng dụng còn connection và biết transaction đang mở, nó có thể ROLLBACK. Nếu connection bị mất, server thường sẽ rollback transaction chưa commit khi nhận diện session kết thúc.

Tuy nhiên, ứng dụng cần xác nhận trạng thái và không được tái sử dụng connection đang ở trạng thái không rõ.

### 4.2. Timeout trong lúc COMMIT đang được gửi/xử lý

~~~text
Ứng dụng gửi COMMIT
       |
       v
Database xử lý COMMIT
       |
       +---- Server commit thành công
       |        |
       |        v
       |     Response bị mất
       |
       +---- Commit chưa hoàn tất / thất bại
                |
                v
             Client timeout
~~~

Client không biết nhánh nào đã xảy ra. Đây là **ambiguous commit** (kết quả commit không xác định ở phía client).

Gửi ROLLBACK sau khi mất kết nối không thể đảo ngược một transaction đã commit. Gửi lại toàn bộ thao tác với một request mới có thể tạo tác dụng phụ lần hai.

Giải pháp là dùng định danh nghiệp vụ hoặc idempotency key để truy vấn kết quả trước khi quyết định thực hiện lại.

### 4.3. Timeout sau khi COMMIT thành công

~~~text
Database COMMIT thành công
       |
       v
Response gửi về
       |
       v
Gateway/client timeout hoặc mất kết nối
~~~

Database đã hoàn tất transaction. Người dùng có thể thấy thông báo timeout dù dữ liệu đã được lưu.

Khi client retry, server phải nhận ra đó là cùng một ý định nghiệp vụ và trả lại kết quả đã lưu thay vì tạo thêm một đơn hàng hoặc thanh toán.

## 5. JDBC: query timeout, cancel và transaction

### 5.1. Statement.setQueryTimeout

JDBC cho phép đặt timeout cho một Statement:

~~~java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT id, status FROM orders WHERE customer_id = ?")) {
    ps.setLong(1, customerId);
    ps.setQueryTimeout(10); // giây

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả.
        }
    }
}
~~~

setQueryTimeout(10) đặt giới hạn thời gian cho việc thực thi statement theo hợp đồng JDBC và khả năng driver. Khi hết hạn, driver thường cố gắng hủy statement và báo SQLTimeoutException.

Cần lưu ý:

- Đơn vị của API này là giây.
- Hành vi thực tế phụ thuộc driver và DBMS.
- Timeout có thể phát sinh trong lúc chờ khóa hoặc thực thi.
- Không nên xem exception là bằng chứng transaction đã rollback.
- Cần kiểm tra trạng thái connection/transaction sau lỗi.

### 5.2. Statement.cancel

Một thread khác có thể yêu cầu hủy statement:

~~~java
statement.cancel();
~~~

Ứng dụng có thể dùng cách này khi request bị hủy hoặc deadline bên ngoài đã hết. Nhưng cancel là yêu cầu gửi xuống driver/database; thời điểm server dừng và trạng thái transaction cần được xác định sau đó.

Không nên gọi cancel trên một Statement đang được thread khác sử dụng mà không có cơ chế quản lý lifecycle rõ ràng. Cần phối hợp thread sở hữu statement, connection và transaction.

### 5.3. Phân biệt SQLTimeoutException với lỗi mạng

Một số trường hợp:

- **SQLTimeoutException:** driver báo timeout thực thi statement.
- **SQLTransientConnectionException** hoặc exception mạng: connection không thể tiếp tục.
- **SQLRecoverableException:** có thể cần lấy connection mới.
- **SQLException** với SQLSTATE/vendor code của DBMS: lỗi server cụ thể.

Không nên chỉ bắt SQLException rồi coi tất cả là timeout. Hãy xem SQLSTATE, vendor code, exception cause và trạng thái connection.

### 5.4. Transaction thủ công

Ví dụ xử lý một transaction có nhiều câu lệnh:

~~~java
connection.setAutoCommit(false);

try {
    try (PreparedStatement update = connection.prepareStatement(
            "UPDATE inventory " +
            "SET available = available - 1 " +
            "WHERE sku = ? AND available > 0")) {
        update.setString(1, sku);
        update.setQueryTimeout(5);

        int changed = update.executeUpdate();
        if (changed != 1) {
            throw new IllegalStateException("Không đủ hàng hoặc SKU không tồn tại");
        }
    }

    // Các thao tác database khác trong cùng transaction.

    connection.commit();
} catch (Exception ex) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        ex.addSuppressed(rollbackError);
        // Connection có thể không còn an toàn để tái sử dụng.
    }
    throw ex;
} finally {
    // Trả connection về pool theo quy tắc của pool/framework.
}
~~~

Đây là cấu trúc minh họa. Trong ứng dụng thật, cần xử lý riêng trường hợp commit đã được gửi nhưng response bị mất. Nếu không biết COMMIT thành công hay chưa, rollback qua connection cũ có thể không giải quyết được sự mơ hồ; cần truy vấn trạng thái nghiệp vụ bằng idempotency key trên connection mới.

### 5.5. Timeout của pool khác timeout của statement

Các pool như HikariCP có connectionTimeout để giới hạn thời gian lấy connection từ pool. Nó không thay thế Statement.setQueryTimeout.

Cũng cần phân biệt:

- Connection acquisition timeout.
- Connection validation timeout.
- Idle timeout.
- Maximum lifetime.
- Leak detection threshold.

Các cấu hình này điều khiển vòng đời connection trong pool. Chúng không phải tất cả đều hủy câu SQL đang chạy.

## 6. Spring transaction và timeout

### 6.1. @Transactional(timeout = ...)

Spring cho phép cấu hình timeout cho transaction:

~~~java
@Transactional(timeout = 10)
public void processOrder(long orderId) {
    // Đọc và cập nhật dữ liệu.
}
~~~

Timeout này được transaction manager và resource integration sử dụng theo khả năng của chúng. Nó không phải một bộ đếm thời gian phổ quát có thể cưỡng bức dừng mọi câu SQL, mọi lời gọi HTTP hoặc mọi đoạn Java trong method.

Tùy transaction manager, JDBC driver và cách lấy statement, timeout có thể được áp dụng vào query timeout hoặc resource timeout. Cần kiểm tra stack thực tế.

### 6.2. Transaction timeout không phải request timeout

Một request HTTP có thể có deadline 5 giây trong khi transaction được cấu hình 10 giây. Khi client/gateway hết hạn ở giây thứ 5, transaction có thể vẫn tiếp tục nếu ứng dụng không truyền cancellation hoặc không có timeout thấp hơn ở database.

Ngược lại, transaction timeout 5 giây có thể hết hạn trong khi HTTP request vẫn đang chờ. Ứng dụng cần ánh xạ lỗi transaction thành response phù hợp.

Nên xác định một deadline tổng cho request và truyền budget còn lại qua các tầng, thay vì để mỗi tầng tự bắt đầu một timeout đầy đủ mới.

### 6.3. Rollback rules của Spring

Spring mặc định rollback transaction với unchecked exception (RuntimeException và Error), còn checked exception thường không tự động kích hoạt rollback nếu không cấu hình rollbackFor.

Ví dụ:

~~~java
@Transactional(rollbackFor = Exception.class)
public void updateOrder(...) throws Exception {
    // ...
}
~~~

Nếu timeout được bọc trong checked exception và không nằm trong rollback rule, transaction có thể không rollback theo điều mà người viết code mong đợi.

Cần xác định exception thực tế mà driver ném ra, cách Spring dịch exception và rollback rule của method. Đừng chỉ dựa vào tên TimeoutException.

### 6.4. Lỗi xảy ra ở thời điểm commit

Transaction interceptor có thể chỉ thực hiện COMMIT sau khi method body kết thúc. Vì vậy, lỗi commit có thể xuất hiện sau khi dòng code cuối cùng trong method đã chạy.

Nếu method tự trả về kết quả rồi interceptor mới commit, client vẫn có thể nhận lỗi commit thay vì kết quả. Với async boundary hoặc message handling, cần xác định rõ điểm nào thực sự xác nhận transaction.

Không phát email, gọi payment provider hoặc publish message trước khi transaction commit nếu tác dụng phụ đó không có cơ chế idempotency/outbox.

## 7. PostgreSQL: timeout và hủy ở phía server

PostgreSQL cung cấp một số timeout server-side có ý nghĩa khác nhau.

### 7.1. statement_timeout

statement_timeout giới hạn tổng thời gian một statement được phép chạy. Khi vượt quá, server hủy statement và trả lỗi timeout.

Có thể đặt theo session hoặc transaction:

~~~sql
SET statement_timeout = '8s';
~~~

Hoặc trong một transaction:

~~~sql
BEGIN;
SET LOCAL statement_timeout = '8s';

SELECT *
FROM orders
WHERE customer_id = 42;

COMMIT;
~~~

SET LOCAL chỉ có hiệu lực trong transaction hiện tại. Cần reset/kiểm tra cấu hình session khi dùng connection pool để tránh rò rỉ thiết lập sang request khác.

Nếu statement timeout xảy ra trong transaction PostgreSQL, transaction thường chuyển sang trạng thái aborted. Ứng dụng phải ROLLBACK transaction hoặc ROLLBACK TO SAVEPOINT phù hợp trước khi chạy câu lệnh tiếp theo.

### 7.2. lock_timeout

lock_timeout giới hạn thời gian chờ để lấy khóa:

~~~sql
SET lock_timeout = '2s';
~~~

Nó có thể làm statement thất bại nhanh khi bị blocker. Nó không giới hạn tổng thời gian CPU của truy vấn không chờ khóa.

Nếu statement_timeout và lock_timeout cùng được đặt, lock_timeout nên ngắn hơn nếu muốn giới hạn riêng thời gian chờ khóa. Khi statement đang chờ khóa quá lâu, lỗi có thể do lock_timeout trước khi statement_timeout hết hạn.

### 7.3. idle_in_transaction_session_timeout

Timeout này kết thúc session đang ở trong transaction nhưng không hoạt động trong khoảng thời gian quy định:

~~~sql
SET idle_in_transaction_session_timeout = '30s';
~~~

Nó giúp hạn chế transaction bị bỏ quên trong trạng thái idle, giữ khóa hoặc giữ snapshot lâu. Khi server kết thúc session, transaction chưa commit sẽ bị rollback.

Đây là timeout session/transaction idle, khác với timeout câu lệnh đang chạy.

### 7.4. Hủy backend bằng SQL

PostgreSQL có các hàm quản trị:

~~~sql
SELECT pg_cancel_backend(pid);
~~~

Hàm này yêu cầu hủy câu lệnh hiện tại của backend.

~~~sql
SELECT pg_terminate_backend(pid);
~~~

Hàm này yêu cầu kết thúc backend session. Khi session kết thúc, transaction chưa commit được rollback.

Cả hai cần quyền phù hợp. pg_cancel_backend không đồng nghĩa đã kết thúc transaction; sau khi câu lệnh bị hủy, transaction có thể ở trạng thái aborted và cần rollback.

### 7.5. Cancellation từ client

PostgreSQL protocol hỗ trợ CancelRequest. Driver có thể gửi yêu cầu hủy qua một kết nối điều khiển riêng. Nếu server nhận và xử lý yêu cầu, statement hiện tại bị hủy.

Nếu client đã mất mạng, driver không gửi được cancel hoặc request đến sau khi statement hoàn tất, kết quả vẫn có thể khác kỳ vọng. Ứng dụng cần xử lý lỗi và transaction state, không suy luận chỉ từ việc client đã timeout.

## 8. MySQL InnoDB: timeout, lock wait và session

### 8.1. innodb_lock_wait_timeout

Biến này giới hạn thời gian InnoDB chờ khóa:

~~~sql
SET SESSION innodb_lock_wait_timeout = 5;
~~~

Khi hết thời gian, InnoDB báo lock wait timeout. Theo mặc định phổ biến, InnoDB rollback statement bị timeout; toàn bộ transaction không nhất thiết bị rollback. Cấu hình innodb_rollback_on_timeout có thể thay đổi hành vi để rollback toàn transaction.

Vì vậy, ứng dụng phải biết cấu hình và không giả định lock wait timeout luôn đưa transaction về trạng thái giống deadlock.

Deadlock InnoDB thường được phát hiện riêng và một transaction victim được rollback toàn bộ.

### 8.2. max_execution_time

MySQL có max_execution_time để giới hạn thời gian một số SELECT read-only chạy, thường tính bằng milliseconds và áp dụng theo phạm vi hỗ trợ của phiên bản/câu lệnh.

Ví dụ dạng hint:

~~~sql
SELECT /*+ MAX_EXECUTION_TIME(3000) */
       *
FROM orders
WHERE customer_id = 42;
~~~

Đây không phải timeout tổng quát cho mọi UPDATE/INSERT/DELETE. Cần kiểm tra phiên bản MySQL và điều kiện áp dụng.

### 8.3. Network timeout

Một số biến liên quan:

- net_read_timeout: thời gian server chờ đọc thêm dữ liệu từ client.
- net_write_timeout: thời gian server chờ ghi block dữ liệu ra client.
- wait_timeout: thời gian chờ trên kết nối không tương tác ở trạng thái idle.
- interactive_timeout: timeout cho kết nối interactive theo cách client kết nối.

Các biến này điều khiển hoạt động mạng hoặc session idle. Chúng không tương đương với giới hạn thời gian chạy một câu SQL.

### 8.4. KILL QUERY và KILL CONNECTION

MySQL hỗ trợ:

~~~sql
KILL QUERY <processlist_id>;
~~~

Lệnh này yêu cầu hủy câu lệnh hiện tại của connection.

~~~sql
KILL CONNECTION <processlist_id>;
~~~

Lệnh này kết thúc connection/session. Transaction đang mở sẽ được rollback khi session kết thúc.

KILL QUERY không nhất thiết đóng connection và không mặc định rollback toàn transaction. Sau khi statement bị hủy, ứng dụng cần kiểm tra transaction state và thực hiện ROLLBACK nếu nghiệp vụ không thể tiếp tục.

## 9. SQL Server: command timeout và Attention

### 9.1. Command timeout ở client

Các driver như SqlClient có CommandTimeout. Khi vượt giới hạn, client gửi tín hiệu Attention để yêu cầu SQL Server dừng xử lý request.

Điều này khác với việc client chỉ ngừng đọc socket. Nhưng ứng dụng vẫn cần xác định server đã nhận và xử lý Attention chưa, và transaction hiện tại đang ở trạng thái nào.

### 9.2. Transaction có thể còn mở

Sau khi một statement bị cancel, transaction không nhất thiết đã được rollback toàn bộ. Hành vi phụ thuộc trạng thái transaction, loại lỗi, driver và thiết lập như XACT_ABORT.

Trong T-SQL, có thể kiểm tra:

~~~sql
SELECT XACT_STATE();
~~~

Giá trị thường được diễn giải:

- 1: transaction đang hoạt động và có thể commit.
- -1: transaction đang ở trạng thái không thể commit, chỉ có thể rollback toàn bộ.
- 0: không có transaction người dùng đang hoạt động.

Không nên tiếp tục nghiệp vụ sau timeout mà không xác định transaction state.

### 9.3. SET LOCK_TIMEOUT

SQL Server có thể giới hạn thời gian chờ khóa:

~~~sql
SET LOCK_TIMEOUT 3000;
~~~

Đơn vị là milliseconds. Khi hết hạn, statement nhận lỗi lock timeout. Đây là giới hạn chờ khóa, không phải giới hạn tổng thời gian thực thi.

### 9.4. SET XACT_ABORT

Với một số ứng dụng, SET XACT_ABORT ON giúp transaction tự rollback khi một số lỗi runtime xảy ra:

~~~sql
SET XACT_ABORT ON;

BEGIN TRANSACTION;

UPDATE account
SET balance = balance - 100
WHERE id = 10;

COMMIT TRANSACTION;
~~~

Không nên xem nó là giải pháp cho mọi kiểu timeout hoặc lỗi client. Cần thử nghiệm với driver và lỗi thực tế; một số lỗi compile, cancellation hoặc lỗi connection có semantics riêng.

### 9.5. Quan sát request bị hủy

SQL Server có thể ghi nhận Attention event qua Extended Events. Khi điều tra command timeout, nên đối chiếu thời điểm client timeout với Attention, request status, transaction state và deadlock/lock wait information.

## 10. Oracle: call timeout và cancel

Oracle JDBC có các cơ chế timeout/cancel riêng, ví dụ:

- Statement.setQueryTimeout theo JDBC.
- OracleConnection.setCallTimeout trong driver Oracle, áp dụng timeout cho round-trip database call theo API/phiên bản driver.
- Statement.cancel() để yêu cầu hủy statement.
- Resource Manager và các chính sách server-side để quản lý tài nguyên trong những cấu hình phù hợp.

Một call timeout hoặc cancel không nên được hiểu là transaction đã rollback toàn bộ. Nếu transaction có nhiều statement, ứng dụng cần kết thúc transaction theo chính sách rõ ràng.

Khi connection mất trong lúc COMMIT, kết quả commit vẫn có thể không xác định ở client. Cần dùng khóa nghiệp vụ/idempotency để đối soát.

## 11. Thiết kế deadline xuyên suốt request

### 11.1. Không đặt timeout độc lập mà không xét ngân sách tổng

Giả sử một request có deadline 12 giây. Nó phải:

- Lấy connection.
- Chạy hai câu SQL.
- Gọi một dịch vụ nội bộ.
- Commit.
- Serialize response.

Nếu mỗi tầng tự đặt timeout 12 giây, tổng thời gian có thể vượt xa deadline.

Nên phân bổ một ngân sách thời gian tổng. Ví dụ minh họa:

| Công đoạn | Ngân sách |
|---|---:|
| Lấy connection | 500 ms |
| SQL đọc | 2 s |
| SQL ghi/lock wait | 3 s |
| Phần xử lý ứng dụng | 2 s |
| Commit và hoàn tất | 1 s |
| Dự phòng/response | 1.5 s |
| Tổng | 10 s |

Phần còn lại của deadline được dành cho scheduling, network và sai số. Các con số phải dựa trên SLA và phân bố latency thực tế.

### 11.2. Đặt server-side timeout trước client deadline

Một nguyên tắc hữu ích là timeout database cho statement nên thấp hơn deadline ứng dụng một khoảng đủ để:

1. Database nhận ra timeout và hủy statement.
2. Driver nhận lỗi.
3. Ứng dụng rollback transaction.
4. Connection được trả về pool hoặc loại bỏ.
5. Ứng dụng trả response trước deadline phía trên.

Ví dụ, nếu request deadline là 10 giây, statement timeout có thể là 7 giây và client command timeout 8 giây, tùy driver và overhead. Đây chỉ là minh họa; cần thử nghiệm thực tế.

Nếu client timeout ngắn hơn server timeout, ứng dụng có thể trả lỗi trong khi database vẫn tiếp tục chạy.

### 11.3. Truyền deadline còn lại

Thay vì mỗi service bắt đầu lại một timeout đầy đủ, truyền deadline hoặc thời gian còn lại:

~~~text
Request deadline: 12 giây kể từ t0

Service A nhận lúc t0:
    còn 12 giây

Service B nhận lúc t0 + 4 giây:
    còn 8 giây

Database call bắt đầu lúc t0 + 7 giây:
    còn 5 giây
~~~

Mỗi tầng cần trừ thời gian đã tiêu thụ và dành ngân sách cho rollback/response. Đối với distributed tracing, ghi nhận deadline hoặc remaining budget giúp giải thích vì sao một downstream call bị hủy.

### 11.4. Không dùng timeout quá ngắn để che nghẽn

Giảm timeout có thể làm request thất bại nhanh hơn nhưng không làm hệ thống xử lý được nhiều công việc hơn. Nếu pool cạn, database quá tải hoặc index kém, timeout ngắn chỉ biến chờ lâu thành lỗi sớm và có thể tăng retry.

Cần tìm nguyên nhân gốc: throughput, connection pool sizing, execution plan, lock contention, query shape và số lần retry.

## 12. Xử lý connection sau timeout

### 12.1. Connection có thể còn transaction mở

Sau query timeout, cần biết:

- Statement đã bị hủy chưa?
- Transaction có đang ở trạng thái aborted không?
- Các thay đổi trước statement có còn trong transaction không?
- Connection có còn đồng bộ giao thức và an toàn để tái sử dụng không?
- Driver có đánh dấu connection invalid không?

Không nên đưa connection về pool khi transaction vẫn mở hoặc protocol state chưa được phục hồi.

### 12.2. Rollback trước khi trả về pool

Với connection còn hoạt động và transaction state đã biết, rollback là cách kết thúc các thay đổi chưa commit:

~~~java
try {
    connection.rollback();
} catch (SQLException ex) {
    // Không thể xác nhận rollback qua connection này.
    // Đánh dấu connection không hợp lệ/để pool loại bỏ theo API của pool.
}
~~~

Nếu rollback thất bại do connection mất, hãy loại bỏ connection thay vì tái sử dụng nó như connection sạch. Khi server phát hiện session mất, transaction chưa commit thường được rollback, nhưng ứng dụng vẫn phải xử lý kết quả COMMIT không xác định nếu COMMIT đã được gửi.

### 12.3. Không tự động trả connection bị lỗi về pool

Pool có thể cung cấp cách đánh dấu connection broken/evict/abort tùy thư viện. Đừng chỉ bắt exception rồi đóng wrapper nếu wrapper thực chất trả connection vật lý về pool trong trạng thái không sạch.

Dùng API quản lý connection của pool/framework và kiểm tra cách nó xử lý fatal SQLSTATE, socket exception, cancel và rollback failure.

### 12.4. Kiểm tra connection leak và transaction leak

Một request timeout có thể khiến thread kết thúc nhưng connection vẫn bị giữ bởi task nền hoặc code chưa đóng resource. Theo dõi:

- Active/idle connection.
- Connection acquisition latency.
- Connection usage duration.
- Leak detection.
- Transaction age.
- Session idle in transaction.
- Query đang chạy sau khi request đã kết thúc.

Nếu số active connection tăng mà request đang xử lý giảm, có thể có công việc hoặc transaction không được giải phóng đúng cách.

## 13. Retry khi timeout: khi nào an toàn?

### 13.1. Timeout trước khi request đến database

Nếu ứng dụng timeout khi chưa lấy được connection hoặc trước khi gửi SQL, có thể chắc chắn thao tác database chưa bắt đầu trong request đó. Retry có thể an toàn hơn, nhưng vẫn cần bảo đảm không có một worker khác đã thực hiện cùng nghiệp vụ.

### 13.2. Timeout khi statement đang chạy nhưng trước COMMIT

Nếu ứng dụng biết transaction chưa gửi COMMIT và rollback thành công, có thể chạy lại toàn bộ transaction. Cần tránh retry chỉ câu SQL cuối nếu các quyết định trước đó dựa trên snapshot cũ.

### 13.3. Timeout trong lúc COMMIT

Đây là trường hợp không thể suy ra thành công hay thất bại chỉ từ exception phía client.

Quy trình nên là:

1. Dùng một idempotency key hoặc business operation ID ổn định.
2. Kết nối lại database.
3. Tra cứu record kết quả theo key đó.
4. Nếu đã hoàn tất, trả kết quả đã lưu.
5. Nếu chưa có, xác định trạng thái xử lý và chỉ chạy lại theo giao thức an toàn.
6. Nếu trạng thái còn mơ hồ do worker khác đang xử lý, chờ/đối soát thay vì tạo thao tác mới ngay.

### 13.4. Timeout sau COMMIT nhưng trước response

Đây là tình huống phổ biến trong API. Dữ liệu đã commit nhưng client retry vì không nhận response.

Idempotency record nên được commit cùng thay đổi nghiệp vụ:

~~~sql
BEGIN;

INSERT INTO idempotency_record (
    tenant_id,
    operation,
    idempotency_key,
    request_hash,
    status
)
VALUES (
    :tenant_id,
    'CREATE_ORDER',
    :key,
    :request_hash,
    'PROCESSING'
);

INSERT INTO orders (...);

UPDATE idempotency_record
SET status = 'COMPLETED',
    response_body = :response
WHERE tenant_id = :tenant_id
  AND operation = 'CREATE_ORDER'
  AND idempotency_key = :key;

COMMIT;
~~~

Ví dụ này mô tả trường hợp nghiệp vụ có thể hoàn tất trong một transaction database. Nếu có dịch vụ ngoài hoặc xử lý dài, cần outbox/workflow và lease/recovery riêng.

### 13.5. Retry có backoff và giới hạn

Không retry vô hạn. Dùng:

- Số lần thử tối đa.
- Backoff tăng dần.
- Jitter để tránh nhiều request retry cùng lúc.
- Phân loại lỗi retryable và non-retryable.
- Idempotency key ổn định.
- Log mỗi lần thử và kết quả.

Timeout do lock contention có thể tái diễn nếu tất cả request retry ngay lập tức. Retry storm có thể làm pool và database quá tải hơn.

## 14. Idempotency và kết quả commit không xác định

### 14.1. Vì sao idempotency key cần thiết?

Giả sử API tạo đơn hàng:

~~~http
POST /orders
Idempotency-Key: order-request-abc123
~~~

Server tạo đơn và commit nhưng response bị mất. Client gửi lại cùng key.

Nếu server lưu key và kết quả trong cùng transaction với đơn hàng, lần retry có thể nhận ra request đã hoàn tất và trả lại order ID cũ.

Nếu client tạo key mới khi retry, server có thể coi đó là một ý định mới và tạo đơn thứ hai.

### 14.2. Kiểm tra payload

Cùng key nhưng payload khác phải được xử lý rõ:

- Lần đầu: amount = 100.
- Lần sau: amount = 500.

Server không nên âm thầm dùng kết quả cũ hoặc thực hiện nội dung mới dưới cùng key. Lưu request hash đã chuẩn hóa và trả conflict nếu nội dung khác.

### 14.3. Ghi nhận trạng thái và response

Một record idempotency có thể lưu:

- Scope (tenant/client/operation).
- Key.
- Request hash.
- Trạng thái PROCESSING/COMPLETED/FAILED.
- Resource ID.
- Response status/body.
- Thời điểm tạo và hoàn tất.
- Lease/owner nếu xử lý bất đồng bộ.

Với transaction ngắn, record và kết quả có thể commit nguyên tử. Với tác vụ dài, cần xử lý crash và takeover để tránh hai worker cùng thực hiện.

### 14.4. Không dùng “kiểm tra trước rồi mới tạo” làm dedup

Mẫu sau vẫn có race condition:

~~~sql
SELECT id
FROM idempotency_record
WHERE idempotency_key = :key;

-- Nếu chưa có thì INSERT
~~~

Hai request có thể cùng không thấy record. Dùng UNIQUE constraint trên đúng phạm vi key để database phân xử. Sau conflict, đọc trạng thái record hiện có.

## 15. Hủy request HTTP và tác vụ bất đồng bộ

### 15.1. Client disconnect

Khi browser hoặc mobile đóng kết nối, server có thể nhận biết client disconnect, nhưng không phải mọi framework đều tự hủy tác vụ đang chạy.

Một handler có thể tiếp tục:

- Chờ database.
- Gọi dịch vụ ngoài.
- Ghi dữ liệu.
- Phát message.

Nếu công việc cần dừng khi caller rời đi, ứng dụng phải có cơ chế cancellation rõ ràng. Nếu công việc đã được chấp nhận như một job bền vững, client disconnect không nên hủy job; client có thể truy vấn trạng thái bằng job ID.

### 15.2. Request-response và job bền vững là hai mô hình khác nhau

Với request đồng bộ, deadline thường giới hạn thời gian người gọi chờ kết quả.

Với job bất đồng bộ:

~~~text
POST /reports
   |
   v
Server tạo job và trả 202 + job_id
   |
   v
Worker xử lý độc lập
   |
   v
Client GET /jobs/{job_id}
~~~

Client có thể timeout khi polling nhưng job vẫn tiếp tục. Đây là hành vi mong muốn nếu API đã xác nhận nhận job.

Cần tài liệu hóa rõ: timeout của polling không hủy job. Muốn hủy job phải gọi endpoint cancellation riêng và worker phải hỗ trợ trạng thái hủy.

### 15.3. Cancellation token phải được truyền xuyên suốt

Trong hệ thống nhiều tầng, một cancellation token hoặc deadline cần được truyền qua:

- Controller/request handler.
- Service.
- Executor/task.
- Repository/DAO.
- Driver/database statement.
- Downstream HTTP client.

Nếu một tầng bỏ qua tín hiệu, công việc phía dưới có thể tiếp tục. Không thể giả định interrupt của thread tự động dừng mọi I/O hoặc rollback database.

### 15.4. Hủy công việc sau khi đã commit

Nếu database đã commit, hủy request không thể đảo ngược commit. Nếu nghiệp vụ cần “hủy đơn” sau commit, đó là một thao tác bù trừ riêng, chẳng hạn cập nhật trạng thái CANCELLED hoặc tạo refund, và phải có quy tắc nhất quán riêng.

Đừng dùng request cancellation để thay thế nghiệp vụ hoàn tác.

## 16. Timeout và khóa giao dịch

### 16.1. Lock wait timeout

Một câu UPDATE có thể chờ khóa do transaction khác giữ. Nếu DBMS có lock wait timeout, statement có thể thất bại sau một khoảng thời gian.

Đây là timeout của yêu cầu khóa ở database. Nó có thể xảy ra trước application query timeout.

### 16.2. Statement timeout

Một statement timeout có thể bao gồm cả thời gian chờ khóa và thời gian thực thi, tùy DBMS. Nó không nhất thiết chỉ đo CPU time.

Ví dụ PostgreSQL statement_timeout tính thời gian từ khi statement đến server đến khi hoàn tất; thời gian chờ lock có thể nằm trong đó. lock_timeout chỉ giới hạn riêng thời gian chờ lock.

### 16.3. Transaction idle timeout

Một transaction đã chạy câu lệnh xong nhưng ứng dụng giữ connection mở và chờ người dùng hoặc dịch vụ khác có thể tiếp tục giữ khóa/snapshot.

idle_in_transaction_session_timeout của PostgreSQL là ví dụ về timeout xử lý session idle trong transaction. Các DBMS khác có cơ chế và tên cấu hình khác nhau.

### 16.4. Timeout không thay thế thiết kế thứ tự khóa

Nếu hai transaction lấy khóa theo thứ tự ngược nhau, giảm lock timeout chỉ khiến một giao dịch thất bại sớm hơn. Nó không loại bỏ chu trình.

Cần kết hợp:

- Thứ tự truy cập tài nguyên ổn định.
- Transaction ngắn.
- Index phù hợp để thu hẹp scan.
- Retry có giới hạn.
- Timeout đúng tầng.
- Deadlock diagnostics.

## 17. Thiết kế thứ tự timeout

Một hệ thống có thể có nhiều timeout như:

~~~text
Client deadline
    > Gateway upstream timeout
        > Application request budget
            > JDBC command timeout
                > Database statement timeout
                    > Lock wait timeout
~~~

Đây là một ví dụ về thứ tự có thể dùng, không phải quy tắc bắt buộc. Cần xét kiến trúc: gateway có thể bao ngoài application deadline, client có thể đặt deadline lớn hơn gateway, còn database statement timeout nên đủ ngắn để ứng dụng còn thời gian rollback.

Một cấu hình minh họa cho request 15 giây:

| Thành phần | Timeout ví dụ |
|---|---:|
| Database lock wait | 2 s |
| Database statement | 8 s |
| JDBC command | 9 s |
| Application deadline | 11 s |
| Gateway upstream | 13 s |
| Client deadline | 15 s |

Mục tiêu là tầng dưới có cơ hội kết thúc và trả lỗi trước khi tầng trên bỏ cuộc. Phải kiểm tra semantics thực tế của từng timeout và cộng thêm thời gian cho connection acquisition, commit, rollback và response.

### 17.1. Tránh hai timeout bằng nhau sát nút

Nếu JDBC command timeout và server statement timeout đều 8 giây, race về thời điểm có thể khiến driver timeout trước khi server trả lỗi của chính nó. Khi đó log server có thể không phản ánh đúng lý do ứng dụng thấy.

Đặt khoảng chênh đủ lớn để server-side timeout xảy ra trước, sau đó driver nhận lỗi và ứng dụng xử lý. Khoảng chênh cần dựa trên latency mạng và độ trễ cancellation.

### 17.2. Timeout cho COMMIT

Không nên đặt timeout commit quá thấp đến mức nhiều transaction đã hoàn tất phần ghi nhưng client thường xuyên mất response ở bước commit. Commit có thể cần flush log/WAL/redo, đồng bộ replication hoặc chờ tài nguyên.

Nếu commit timeout xảy ra, phải xử lý ambiguous outcome bằng idempotency/đối soát. Không được coi mọi commit timeout là rollback.

## 18. Quan sát và chẩn đoán

### 18.1. Ghi thời điểm ở nhiều tầng

Một request nên có correlation ID xuyên suốt. Ghi nhận:

- Thời điểm request đến.
- Thời điểm lấy connection bắt đầu/kết thúc.
- Thời điểm gửi statement.
- Thời điểm driver báo timeout/cancel.
- Thời điểm rollback bắt đầu/kết thúc.
- Thời điểm COMMIT bắt đầu/kết thúc.
- Thời điểm server log ghi query cancel hoặc session terminate.
- Thời điểm gateway/client timeout.

Nếu chỉ log “request timed out after 10s”, không thể biết thời gian mất ở pool, network, lock wait, query execution hay commit.

### 18.2. Phân loại timeout

Nên có metric riêng cho:

- Pool acquisition timeout.
- Application deadline exceeded.
- HTTP upstream timeout.
- JDBC query timeout.
- Socket read/write timeout.
- Database statement timeout.
- Lock wait timeout.
- Transaction idle timeout.
- Commit outcome unknown.
- Cancellation failure.
- Rollback failure.

Một metric tổng hợp “timeout” không đủ để điều tra nguyên nhân.

### 18.3. Theo dõi truy vấn còn chạy sau khi request kết thúc

Đối chiếu application log với DB activity:

- PostgreSQL: pg_stat_activity, wait_event, xact_start, query_start, pg_blocking_pids.
- MySQL: Performance Schema, data_locks, data_lock_waits, process list và InnoDB status.
- SQL Server: sys.dm_exec_requests, sys.dm_tran_locks, Extended Events và Attention events.
- Oracle: V$SESSION, V$SQL, wait events và trace.

Nếu database vẫn chạy query sau khi ứng dụng timeout, cần kiểm tra cancellation propagation và connection lifecycle.

### 18.4. Đo transaction age và connection hold time

Các chỉ số hữu ích:

| Chỉ số | Dấu hiệu cần điều tra |
|---|---|
| Active connections | Tăng liên tục sau nhiều request timeout |
| Connection acquisition latency | Pool cạn hoặc connection giữ quá lâu |
| Transaction age | Transaction mở lâu bất thường |
| Idle-in-transaction sessions | Ứng dụng không kết thúc transaction |
| Query duration sau client timeout | Cancellation không đến server hoặc bị chậm |
| Rollback duration/failure | Connection/server không phục hồi đúng |
| Commit unknown count | Mất kết nối trong giai đoạn commit |
| Retry count | Retry storm hoặc contention |
| Lock wait/deadlock rate | Xung đột tài nguyên tăng |

### 18.5. Không log nhầm “timeout” thành “transaction rolled back”

Log cần mô tả điều đã biết:

- request_deadline_exceeded
- statement_cancel_requested
- statement_timeout_from_db
- rollback_confirmed
- connection_invalidated
- commit_outcome_unknown
- idempotency_replay

Chỉ ghi rollback_confirmed khi ứng dụng thực sự nhận xác nhận rollback hoặc có bằng chứng đủ tin cậy theo cơ chế hệ thống.

## 19. Ví dụ phân tích các tình huống thực tế

### Tình huống A: Pool timeout trước khi có connection

Ứng dụng báo timeout lấy connection sau 2 giây.

- Chưa gửi SQL.
- Database không có statement tương ứng từ request này.
- Cần kiểm tra số connection active, leak, query chậm và pool sizing.
- Retry ngay có thể làm hàng đợi pool nặng hơn.

Đây không phải transaction timeout.

### Tình huống B: Statement timeout trong PostgreSQL transaction

Ứng dụng đã chạy UPDATE, sau đó SELECT dài bị statement_timeout.

- PostgreSQL hủy statement.
- Transaction thường ở trạng thái aborted.
- Các thay đổi trước đó trong transaction chưa commit không thể được commit tiếp.
- Ứng dụng phải ROLLBACK transaction.
- Chỉ trả connection về pool sau khi transaction kết thúc hoặc connection bị loại bỏ nếu không phục hồi được.

### Tình huống C: JDBC socket timeout khi database vẫn chạy

Driver không nhận được response trong thời hạn socket read.

- Client thấy lỗi I/O.
- Server có thể vẫn chạy query.
- Connection có thể bị hỏng hoặc driver không còn biết trạng thái protocol.
- Cần loại bỏ connection nếu không thể xác nhận trạng thái.
- Đối chiếu DB activity và dùng idempotency nếu thao tác có thể đã commit.

### Tình huống D: Timeout ngay khi COMMIT

Ứng dụng đã thực hiện INSERT và gửi COMMIT nhưng socket bị đóng trước response.

- Server có thể đã commit.
- Server có thể chưa commit và rollback sau khi session mất.
- Client không thể suy ra từ socket exception.
- Kết nối lại và tra cứu theo idempotency/business key.
- Không tạo lại thao tác với key mới.

### Tình huống E: Gateway 504 nhưng worker tiếp tục

Một API khởi tạo báo cáo và chờ worker đồng bộ. Gateway timeout sau 30 giây.

- Gateway trả 504.
- Worker vẫn chạy và có thể ghi kết quả.
- Client retry có thể khởi tạo báo cáo thứ hai.
- Nên mô hình hóa công việc dài thành job có ID, idempotency key và endpoint truy vấn trạng thái.
- Timeout polling không hủy job đã được chấp nhận.

### Tình huống F: Lock wait timeout trong InnoDB

Một transaction chờ row lock quá innodb_lock_wait_timeout.

- InnoDB trả lỗi lock wait timeout.
- Theo mặc định phổ biến, statement bị rollback; transaction có thể còn mở.
- Nếu cấu hình innodb_rollback_on_timeout, hành vi rollback transaction khác đi.
- Ứng dụng phải xử lý theo cấu hình và rollback nếu không thể tiếp tục an toàn.
- Phân biệt với deadlock, vốn InnoDB phát hiện riêng và chọn victim.

## 20. Những lỗi triển khai thường gặp

**Cho rằng HTTP 504 có nghĩa database đã rollback.**

Gateway chỉ biết upstream không trả response trong hạn. Cần kiểm tra cancellation và transaction state ở backend.

**Dùng Future.get(timeout) rồi nghĩ task đã dừng.**

Timeout chỉ kết thúc việc chờ. Muốn hủy phải yêu cầu cancellation và task/driver phải phản ứng.

**Chỉ cấu hình connection pool timeout.**

Pool timeout giới hạn chờ lấy connection, không giới hạn thời gian câu SQL đang chạy.

**Chỉ cấu hình JDBC query timeout và bỏ qua server-side timeout.**

Driver có thể không gửi được cancel hoặc connection đã mất. Server-side timeout giúp giới hạn công việc ở database.

**Bắt timeout rồi trả connection về pool ngay.**

Connection có thể còn transaction mở hoặc protocol state không sạch. Cần rollback hoặc evict theo trạng thái thực tế.

**Coi Statement.cancel() là xác nhận rollback.**

Cancel nhắm đến statement. Transaction có thể còn mở hoặc ở trạng thái aborted; phải kết thúc transaction riêng.

**Retry ngay khi COMMIT timeout.**

Transaction có thể đã commit. Retry bằng request mới có thể tạo đơn hoặc thanh toán trùng. Dùng idempotency key và đối soát.

**Retry mọi timeout vô hạn.**

Retry storm làm tải và contention tăng. Cần giới hạn, backoff, jitter và phân loại lỗi.

**Gửi email hoặc gọi dịch vụ ngoài trước COMMIT.**

Nếu transaction rollback hoặc retry, tác dụng phụ có thể bị lặp hoặc mồ côi. Dùng outbox/idempotency và chỉ phát sau commit.

**Đặt timeout mọi tầng bằng nhau.**

Các tầng có thể timeout cùng lúc và ứng dụng không đủ thời gian rollback. Phân bổ deadline theo ngân sách và chừa khoảng cho cleanup.

**Giả định mọi DBMS rollback giống nhau khi statement bị cancel.**

PostgreSQL, InnoDB, SQL Server và Oracle có semantics khác nhau. Kiểm tra tài liệu đúng phiên bản và trạng thái transaction thực tế.

## 21. Quy trình thiết kế và xử lý timeout

Khi xây dựng hoặc điều tra một luồng database có timeout, hãy thực hiện:

1. **Liệt kê các tầng timeout.** Client, gateway, application, pool, driver, socket và database.
2. **Xác định deadline tổng.** Tính thời gian còn lại thay vì reset timeout ở mỗi tầng.
3. **Đặt timeout server-side.** Giới hạn statement/lock wait phù hợp để database có thể dừng công việc trước request deadline.
4. **Cấu hình driver timeout.** Dùng query/command timeout và cancellation API theo driver.
5. **Xác định transaction boundary.** Biết chính xác statement nào nằm trong transaction và điểm COMMIT.
6. **Thiết kế cleanup.** Rollback transaction khi có thể; evict connection nếu trạng thái không còn tin cậy.
7. **Xử lý ambiguous commit.** Dùng idempotency key hoặc business operation ID để đối soát.
8. **Phân loại lỗi.** Phân biệt pool timeout, query timeout, lock timeout, socket failure, deadlock, serialization failure và commit unknown.
9. **Kiểm thử cancellation.** Mô phỏng timeout khi query chạy, đang chờ khóa, trước COMMIT, trong COMMIT và sau COMMIT.
10. **Theo dõi nhiều tầng.** Dùng correlation ID, DB activity và metric transaction/connection để xác nhận server thực sự đã dừng.

## 22. Ma trận quyết định sau timeout

| Tình huống quan sát được | Điều có thể kết luận | Hành động phù hợp |
|---|---|---|
| Pool không cấp connection | Request chưa chạy SQL qua connection đó | Điều tra pool; retry có kiểm soát |
| App deadline hết nhưng DB query vẫn chạy | Caller đã ngừng chờ; server chưa dừng | Gửi cancel nếu còn khả năng, áp server timeout, theo dõi query |
| DB báo statement timeout | Server đã hủy statement theo timeout | Xử lý transaction state, rollback nếu cần |
| Lock wait timeout | Yêu cầu khóa vượt thời hạn | Phân tích blocker; xử lý transaction theo DBMS |
| Deadlock victim | DBMS đã hủy transaction được chọn | Retry toàn transaction nếu an toàn |
| Cancel thành công nhưng transaction vẫn mở | Statement dừng, transaction chưa kết thúc | ROLLBACK hoặc tiếp tục chỉ khi nghiệp vụ cho phép |
| Rollback được xác nhận | Thay đổi chưa commit đã được hoàn tác | Có thể chạy lại toàn transaction nếu an toàn |
| Socket mất trong COMMIT | Client không biết commit outcome | Tra cứu theo idempotency/business key |
| Timeout sau khi đã commit | Dữ liệu đã được xác nhận, response bị mất | Replay kết quả; không tạo request mới |
| Job async bị client timeout | Client ngừng chờ job status | Tra cứu job ID; chỉ hủy qua cơ chế cancellation riêng |

## 23. Câu hỏi cần trả lời trước khi kết luận một transaction đã kết thúc

- Timeout phát sinh ở tầng nào?
- Câu SQL đã được gửi đến database chưa?
- Driver chỉ ngừng chờ hay đã gửi cancellation?
- Database có log statement canceled/timeout không?
- Transaction đã gửi COMMIT chưa?
- Nếu COMMIT đã gửi, có nhận được xác nhận thành công không?
- Connection còn sử dụng được và transaction state có xác định không?
- Có cần ROLLBACK hay phải evict connection?
- Request retry có dùng cùng idempotency key không?
- Có thể tra cứu kết quả nghiệp vụ đã commit bằng business key không?
- Công việc là request đồng bộ hay job đã được chấp nhận chạy nền?
- Server-side timeout có thấp hơn deadline của ứng dụng đủ để cleanup không?
- Có metric chứng minh query đã dừng và connection đã được giải phóng không?

Timeout của ứng dụng mô tả giới hạn chờ của một thành phần; nó không phải bằng chứng rằng database đã dừng câu lệnh hoặc rollback transaction. Muốn kiểm soát đúng, hệ thống phải truyền cancellation xuống tầng thực thi, áp timeout server-side, kết thúc transaction rõ ràng, quản lý connection sau lỗi và xử lý riêng trường hợp COMMIT không có phản hồi xác nhận. Đặc biệt, khi kết quả COMMIT không xác định ở client, idempotency và đối soát trạng thái nghiệp vụ mới là cách an toàn để quyết định có cần thực hiện lại hay không.

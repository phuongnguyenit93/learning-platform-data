# Đặt timeout cho kết nối, truy vấn và giao dịch

Trong ứng dụng dùng **Spring Data Relational JDBC (Spring Data JDBC)**, một request có thể phải chờ lấy connection, thực thi một hoặc nhiều câu SQL, chờ khóa từ transaction khác và hoàn tất commit. Nếu không đặt giới hạn phù hợp, request có thể giữ thread và connection quá lâu, làm cạn connection pool và khiến các request khác phải chờ.

Spring Boot, Spring Framework, JDBC driver và database đều có cơ chế timeout, nhưng mỗi cơ chế kiểm soát một giai đoạn khác nhau:

- **Connection acquisition timeout:** giới hạn thời gian chờ lấy connection từ pool.
- **Connection establishment timeout:** giới hạn thời gian driver kết nối tới database qua mạng.
- **Query/statement timeout:** giới hạn thời gian thực thi một câu SQL.
- **Transaction timeout:** giới hạn thời gian transaction được phép hoạt động.
- **Database lock/statement timeout:** giới hạn thời gian chờ lock hoặc thực thi ở phía database.

Không có một thuộc tính timeout duy nhất tự động bao phủ tất cả các giai đoạn. Bài này trình bày cách cấu hình từng lớp, cách Spring Data JDBC sử dụng cấu hình JDBC, cách các timeout tương tác và cách xử lý khi hết thời gian.

## 1. Bản đồ các loại timeout

Một luồng request điển hình:

~~~mermaid
flowchart TD
    Request["HTTP request"]
    Pool["Lấy connection từ pool<br/>Hikari connectionTimeout"]
    Driver["Mở kết nối tới DB<br/>Driver connectTimeout"]
    Tx["Bắt đầu transaction<br/>Transaction timeout"]
    SQL["Thực thi câu SQL<br/>Statement queryTimeout"]
    Lock["Chờ database lock<br/>DB lock_timeout"]
    Commit["Commit / rollback"]
    Response["Trả response"]
    Request --> Pool --> Driver --> Tx --> SQL
    SQL --> Lock --> SQL
    SQL --> Commit --> Response
~~~

Các timeout có thể chồng lấp. Ví dụ transaction timeout còn 3 giây nhưng query timeout được cấu hình 8 giây, Spring có thể đặt statement timeout theo **thời gian còn lại của transaction**, vì vậy câu SQL không được phép sử dụng hết 8 giây. Ngược lại, nếu không có transaction timeout, query timeout có thể là giới hạn chính của statement.

| Loại timeout | Đối tượng được giới hạn | Nơi thường cấu hình |
|---|---|---|
| Chờ connection pool | Thời gian đợi một connection rảnh | HikariCP |
| Kết nối mạng/driver | Thời gian mở socket và đăng nhập database | JDBC driver |
| Query/statement | Một câu SQL | JdbcTemplate, JDBC Statement, driver |
| Transaction | Một transaction do Spring quản lý | @Transactional, TransactionTemplate, Boot properties |
| Chờ lock | Thời gian chờ khóa ở database | Database session/role/database configuration |

## 2. Timeout khi lấy connection từ HikariCP

Spring Boot thường dùng HikariCP khi Hikari có trên classpath. Thuộc tính **connectionTimeout** của HikariCP là thời gian tối đa một thread chờ **mượn connection từ pool**.

Khi pool đã đạt **maximumPoolSize** và không còn connection rảnh, thread gọi DataSource.getConnection() phải chờ. Nếu quá connectionTimeout, HikariCP ném lỗi thay vì chờ vô hạn.

Ví dụ cấu hình:

~~~properties
spring.datasource.hikari.connection-timeout=2000
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.validation-timeout=1000
~~~

Trong ví dụ:

- connection-timeout=2000 là tối đa 2.000 millisecond (2 giây) để chờ connection từ pool.
- maximum-pool-size=20 giới hạn tổng số connection đang rảnh và đang được sử dụng.
- validation-timeout=1000 giới hạn thời gian kiểm tra connection còn sống; giá trị này phải nhỏ hơn connection-timeout.

HikariCP mặc định connectionTimeout là 30.000 ms. Giá trị nhỏ nhất được chấp nhận là 250 ms. Các giá trị thời gian của HikariCP dùng millisecond.

### Connection timeout không phải thời gian kết nối tới database

Tên connectionTimeout dễ gây nhầm. Nó chủ yếu giới hạn thời gian chờ connection trong pool. Khi pool cần tạo một connection vật lý mới, JDBC driver còn có timeout riêng cho thao tác kết nối mạng.

Ví dụ PostgreSQL JDBC:

~~~properties
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/orders?connectTimeout=3
~~~

connectTimeout của pgJDBC được tính bằng giây và giới hạn thời gian mở socket tới server. Giá trị mặc định của driver hiện hành là 10 giây; giá trị 0 có nghĩa là không giới hạn.

Ví dụ MySQL Connector/J:

~~~properties
spring.datasource.url=jdbc:mysql://db.example.internal:3306/orders?connectTimeout=3000
~~~

connectTimeout của MySQL Connector/J được tính bằng millisecond; giá trị mặc định là 0, tức không giới hạn.

Đơn vị và tên thuộc tính phụ thuộc driver. Không sao chép connectTimeout=3 từ PostgreSQL sang MySQL rồi giả định nó vẫn có nghĩa 3 giây.

### Một số thuộc tính pool khác không phải query timeout

| Thuộc tính HikariCP | Ý nghĩa |
|---|---|
| connectionTimeout | Chờ mượn connection từ pool |
| validationTimeout | Thời gian tối đa để xác thực connection |
| idleTimeout | Thời gian connection rảnh trước khi có thể bị loại khỏi pool |
| maxLifetime | Tuổi thọ tối đa của connection trong pool |
| keepaliveTime | Chu kỳ kiểm tra/giữ sống connection rảnh |
| maximumPoolSize | Số connection tối đa trong pool |

maxLifetime nên ngắn hơn một chút so với giới hạn tuổi thọ connection do database, proxy hoặc hạ tầng mạng áp dụng. Nó không giới hạn thời gian một query chạy hoặc thời gian transaction tồn tại.

## 3. Timeout cho query và JDBC Statement

JDBC cung cấp Statement.setQueryTimeout(int seconds). Đây là giới hạn thời gian thực thi statement theo đơn vị giây. Nếu vượt ngưỡng, driver có thể hủy query hoặc báo lỗi timeout; cách hủy thực tế phụ thuộc JDBC driver và database.

Spring JdbcTemplate có thuộc tính queryTimeout:

~~~java
JdbcTemplate jdbcTemplate = new JdbcTemplate(dataSource);
jdbcTemplate.setQueryTimeout(5);
~~~

Giá trị 5 ở đây là 5 giây. Giá trị mặc định của JdbcTemplate là -1, nghĩa là không truyền timeout cụ thể cho JDBC driver và để driver dùng mặc định của nó.

### Cấu hình bằng Spring Boot

Spring Boot có property:

~~~properties
spring.jdbc.template.query-timeout=5s
~~~

Property này đặt query timeout mặc định cho JdbcTemplate do Boot cấu hình. Có thể dùng duration suffix như ms, s hoặc m; nếu không ghi suffix, đơn vị là giây.

Ví dụ:

~~~properties
# 5 giây
spring.jdbc.template.query-timeout=5s

# 750 millisecond
spring.jdbc.template.query-timeout=750ms
~~~

Nếu ứng dụng dùng NamedParameterJdbcTemplate, nó thường dùng JdbcTemplate bên dưới. Spring Data JDBC sử dụng các abstraction JDBC như NamedParameterJdbcOperations cho nhiều thao tác persistence, vì vậy cấu hình Boot trên thường ảnh hưởng đến những statement đi qua template được auto-configure.

Nếu ứng dụng tự tạo NamedParameterJdbcOperations, JdbcTemplate hoặc DataAccessStrategy riêng, hãy kiểm tra cấu hình timeout của instance thực sự được Spring Data JDBC sử dụng. Property không tự cấu hình mọi Statement được tạo trực tiếp bằng JDBC API.

### Cấu hình timeout cho một statement riêng

Khi cần giới hạn khác nhau cho từng query tùy chỉnh, có thể đặt timeout trên statement:

~~~java
public List<Order> findSlowReport(
        JdbcTemplate jdbcTemplate,
        String status) {

    return jdbcTemplate.query(connection -> {
        PreparedStatement statement = connection.prepareStatement("""
            SELECT id, customer_id, status
            FROM orders
            WHERE status = ?
            """);
        statement.setString(1, status);
        statement.setQueryTimeout(3);
        return statement;
    }, (resultSet, rowNumber) -> new Order(
        resultSet.getLong("id"),
        resultSet.getLong("customer_id"),
        resultSet.getString("status")
    ));
}
~~~

Đoạn code minh họa cách đặt timeout cho một PreparedStatement riêng. Trong ứng dụng thực tế, nên tái sử dụng RowMapper và constructor phù hợp với domain model. Khi dùng JdbcTemplate hoặc Spring Data JDBC, ưu tiên để Spring quản lý connection và transaction thay vì tự mở connection ngoài transaction context.

## 4. Transaction timeout với @Transactional

Một transaction có thể thực hiện nhiều câu SQL. Nếu mỗi câu SQL đều có timeout 5 giây, một transaction gồm nhiều câu lệnh vẫn có thể tồn tại lâu hơn 5 giây nếu chỉ dựa vào query timeout.

Spring cho phép đặt timeout trên transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(timeout = 10)
    public void confirmOrder(Long orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.confirm();
        orders.save(order);
    }
}
~~~

timeout = 10 được tính bằng giây. Transaction manager dùng giá trị này để giới hạn transaction; với JDBC transaction manager, thời gian còn lại của transaction có thể được áp dụng cho các statement được tạo qua Spring JDBC infrastructure.

@Transactional timeout chỉ áp dụng cho propagation REQUIRED hoặc REQUIRES_NEW. Nếu method tham gia một transaction REQUIRED đã tồn tại, transaction đang hoạt động giữ timeout của nó; khai báo timeout ở method bên trong không khởi tạo lại đồng hồ của transaction bên ngoài.

### Timeout mặc định cho transaction

Có thể cấu hình timeout mặc định trong Spring Boot:

~~~properties
spring.transaction.default-timeout=10s
~~~

Property này đặt default timeout cho transaction manager được Boot cấu hình nếu transaction manager hỗ trợ timeout. Một method có @Transactional(timeout = ...) có thể khai báo timeout riêng cho use case cần giới hạn khác.

### Dùng TransactionTemplate

Với transaction được điều khiển bằng code, có thể cấu hình timeout trên TransactionTemplate:

~~~java
TransactionTemplate transactionTemplate =
    new TransactionTemplate(transactionManager);

transactionTemplate.setTimeout(10);

transactionTemplate.execute(status -> {
    Order order = orders.findById(orderId).orElseThrow();
    order.confirm();
    orders.save(order);
    return null;
});
~~~

TransactionTemplate.setTimeout(10) cũng dùng đơn vị giây. Đây là cách phù hợp khi một đoạn code cần transaction boundary rõ ràng mà không muốn dùng annotation.

### Transaction timeout không phải bộ hẹn giờ giết thread

Transaction timeout không dừng tùy ý mọi hoạt động Java trong method:

- Nó không tự hủy HTTP call hoặc tác vụ ngoài database.
- Nó không bảo đảm dừng một vòng lặp CPU dài.
- Nó chỉ có tác dụng đầy đủ với transaction manager và resource tham gia transaction.
- JDBC statement được tạo ngoài Spring-managed connection có thể không nhận timeout còn lại của transaction.

Với JDBC, hãy dùng JdbcTemplate, NamedParameterJdbcTemplate, repository hoặc connection được lấy qua Spring transaction-aware infrastructure để timeout được áp dụng đúng.

## 5. Quan hệ giữa query timeout và transaction timeout

Spring JDBC áp dụng timeout còn lại của transaction khi tạo statement trong transaction. Nếu transaction timeout còn ít thời gian hơn query timeout cấu hình trên template, timeout còn lại của transaction sẽ được dùng.

Ví dụ:

~~~text
JdbcTemplate query timeout: 8 giây
Transaction timeout:       5 giây

Transaction bắt đầu
  Query 1 chạy 2 giây
  Query 2 bắt đầu, transaction còn khoảng 3 giây
  Query 2 nhận timeout theo thời gian còn lại
~~~

Điều này ngăn từng query trong cùng transaction sử dụng lại toàn bộ query timeout trong khi transaction đã gần hết hạn.

| Query timeout | Transaction timeout | Hành vi mong đợi |
|---:|---:|---|
| 5 giây | Không đặt | Statement dùng query timeout 5 giây |
| 8 giây | 4 giây | Statement trong transaction bị giới hạn theo thời gian transaction còn lại |
| 3 giây | 10 giây | Statement có thể hết query timeout trước khi transaction hết hạn |
| Không đặt | 10 giây | Spring có thể áp dụng thời gian còn lại của transaction cho statement qua Spring JDBC |

Đây là hành vi của Spring JDBC với connection/statement được quản lý đúng cách. Driver và transaction manager cụ thể vẫn ảnh hưởng đến thời điểm phát hiện và cách hủy câu lệnh.

## 6. Timeout ở phía database

Timeout ở tầng ứng dụng và driver không phải lúc nào cũng đủ. Database có thể tiếp tục thực thi câu lệnh sau khi client timeout hoặc client có thể mất kết nối mà query chưa bị hủy ngay. Database-side timeout giúp giới hạn công việc ngay tại server.

### PostgreSQL

PostgreSQL cung cấp một số tham số hữu ích:

| Tham số | Ý nghĩa |
|---|---|
| statement_timeout | Giới hạn tổng thời gian thực thi statement |
| lock_timeout | Giới hạn thời gian chờ khóa |
| idle_in_transaction_session_timeout | Đóng session để transaction ở trạng thái idle quá lâu |

Có thể cấu hình theo database, role hoặc session. Ví dụ áp dụng trong một transaction:

~~~sql
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
~~~

SET LOCAL có hiệu lực trong transaction hiện tại. Đây là cấu hình phía PostgreSQL; không dùng cú pháp này trên MySQL hoặc database khác.

### MySQL

MySQL có các cơ chế riêng:

- innodb_lock_wait_timeout giới hạn thời gian chờ InnoDB row lock.
- max_execution_time có thể giới hạn thời gian thực thi một số câu SELECT.
- Connector/J có connectTimeout và socketTimeout cho kết nối mạng.

Các thuộc tính có phạm vi và đơn vị riêng. Hãy đọc tài liệu đúng phiên bản MySQL và Connector/J đang triển khai trước khi đặt giá trị.

### Driver socket timeout

Socket timeout giới hạn thời gian đọc dữ liệu qua socket. Nó có thể phát hiện kết nối mạng bị treo, nhưng không giống query timeout:

- Query timeout điều khiển thời gian thực thi statement theo JDBC.
- Socket timeout điều khiển thao tác đọc mạng.
- Connection timeout điều khiển thời gian thiết lập kết nối hoặc chờ pool tùy thuộc cấu hình cụ thể.

Ví dụ PostgreSQL JDBC:

~~~properties
spring.datasource.url=jdbc:postgresql://db:5432/orders?connectTimeout=3&socketTimeout=12
~~~

Trong pgJDBC, connectTimeout và socketTimeout được tính bằng giây. socketTimeout có thể đóng kết nối khi đọc từ server quá lâu; không nên đặt quá thấp nếu ứng dụng có truy vấn hợp lệ trả về dữ liệu lớn hoặc chạy lâu.

Ví dụ MySQL Connector/J:

~~~properties
spring.datasource.url=jdbc:mysql://db:3306/orders?connectTimeout=3000&socketTimeout=12000
~~~

Trong Connector/J, hai thuộc tính này được tính bằng millisecond. Đơn vị khác nhau giữa driver là lý do cần kiểm tra tài liệu driver trước khi copy cấu hình.

## 7. Một cấu hình timeout nhiều lớp

Ví dụ minh họa cho ứng dụng Spring Boot dùng HikariCP và Spring Data JDBC:

~~~properties
# Chờ tối đa 2 giây để lấy connection từ Hikari pool
spring.datasource.hikari.connection-timeout=2000

# Kiểm tra connection tối đa 1 giây
spring.datasource.hikari.validation-timeout=1000

# Mặc định mỗi JDBC template statement có timeout 5 giây
spring.jdbc.template.query-timeout=5s

# Transaction mặc định có timeout 10 giây
spring.transaction.default-timeout=10s
~~~

Ví dụ này minh họa các lớp cấu hình, không phải bộ giá trị phù hợp cho mọi ứng dụng. Hãy chọn giá trị theo latency budget của API, pool size, thời gian query thực tế và yêu cầu nghiệp vụ.

Có thể đặt timeout cụ thể cho một use case:

~~~java
@Transactional(timeout = 4)
public Order loadOrderForConfirmation(Long id) {
    return orders.findById(id).orElseThrow();
}
~~~

Method này dùng transaction timeout 4 giây, ngắn hơn default 10 giây trong cấu hình trên.

## 8. Thiết kế timeout theo ngân sách request

Timeout nên được thiết kế từ giới hạn ngoài cùng đi vào các lớp bên trong. Ví dụ một API có deadline 5 giây:

| Lớp | Giới hạn minh họa | Mục tiêu |
|---|---:|---|
| HTTP/request deadline | 5 giây | Không giữ request quá lâu |
| Chờ connection pool | 300 ms | Phát hiện pool bão hòa sớm |
| Transaction | 3 giây | Giới hạn công việc database của use case |
| Query mặc định | 2 giây | Chặn một statement bất thường |
| Database lock wait | 500 ms | Không chờ lock quá lâu |

Các con số trên chỉ là ví dụ để minh họa thứ tự ngân sách. Transaction timeout bao gồm thời gian của các statement tham gia transaction; không cộng các giá trị thành một tổng đơn giản.

Một số nguyên tắc:

- Timeout bên trong nên nhỏ hơn deadline request để còn thời gian rollback, ghi log và trả response.
- Connection pool timeout cần đủ ngắn để pool exhaustion không chiếm hết request threads.
- Query timeout phải dựa trên phân bố latency thật, không chọn quá thấp khiến truy vấn hợp lệ liên tục bị hủy.
- Transaction timeout nên phản ánh độ dài use case; tránh giữ transaction trong khi chờ người dùng, HTTP call hoặc message broker.
- Lock timeout có thể ngắn hơn statement timeout để transaction nhanh chóng xử lý xung đột.
- Socket timeout cần tính đến thời gian truyền dữ liệu lớn và đặc điểm mạng.

## 9. Timeout, retry và idempotency

Timeout không chứng minh rằng database chưa thực hiện thao tác. Ví dụ client gửi INSERT, database thực hiện thành công nhưng kết nối bị đứt trước khi client nhận kết quả. Ứng dụng thấy timeout nhưng trạng thái commit có thể không rõ.

Vì vậy:

- Không retry mù quáng các thao tác ghi không idempotent.
- Dùng idempotency key hoặc unique business key khi một command có thể được gửi lại.
- Nếu transaction bị timeout và rollback được xác nhận, có thể đánh giá retry theo chính sách nghiệp vụ.
- Với lỗi mạng sau khi gửi commit, cần kiểm tra trạng thái bằng business key hoặc cơ chế reconciliation.
- Giới hạn số lần retry và dùng backoff có jitter để tránh làm database quá tải thêm.

Ví dụ một lệnh tạo thanh toán không nên được gửi lại chỉ vì client không nhận response. Hệ thống cần khóa idempotency hoặc truy vấn trạng thái giao dịch trước khi thực hiện lần nữa.

## 10. Connection pool exhaustion và thời gian giữ connection

Pool exhaustion thường là dấu hiệu hệ thống đang giữ connection quá lâu hoặc có nhiều request đồng thời hơn khả năng database/pool phục vụ.

Nguyên nhân thường gặp:

- Query chậm hoặc thiếu index.
- Transaction chứa công việc không liên quan database.
- Code quên đóng stream/result set hoặc connection tự quản lý.
- Pool size quá nhỏ so với concurrency thực tế.
- Database chậm, lock contention hoặc network latency tăng.
- Connection leak.

HikariCP có thể cấu hình leak detection để log connection bị giữ lâu hơn ngưỡng:

~~~properties
spring.datasource.hikari.leak-detection-threshold=20000
~~~

Giá trị tính bằng millisecond. Leak detection là công cụ chẩn đoán, không phải cơ chế timeout tự giải phóng mọi connection đang được sử dụng. Không bật ngưỡng quá thấp trong production nếu nó tạo nhiều cảnh báo giả.

Theo dõi các chỉ số:

- Active connections.
- Idle connections.
- Pending threads chờ connection.
- Connection acquisition latency.
- Query latency và timeout count.
- Transaction duration.
- Lock wait/deadlock.

Tăng maximumPoolSize không phải cách chữa mặc định. Pool lớn hơn có thể làm database chịu nhiều query đồng thời hơn và khiến độ trễ tăng nếu database đã bão hòa.

## 11. Xử lý lỗi timeout trong Spring

JDBC driver thường ném SQLException hoặc SQLTimeoutException. Spring chuyển đổi nhiều lỗi JDBC thành hệ thống DataAccessException.

Các exception có thể gặp:

| Tình huống | Exception thường thấy |
|---|---|
| Không lấy được connection từ pool | CannotGetJdbcConnectionException hoặc DataAccessResourceFailureException |
| Query hết thời gian | QueryTimeoutException hoặc một subtype DataAccessException tùy driver |
| Transaction timeout | Exception từ transaction manager hoặc lỗi truy cập dữ liệu khi statement hết thời gian |
| Mất kết nối/socket timeout | DataAccessResourceFailureException hoặc exception dịch từ SQLException |

Không nên chỉ bắt Exception rồi trả về kết quả rỗng. Hãy phân biệt lỗi timeout có thể retry, lỗi dữ liệu, lỗi constraint và lỗi nghiệp vụ.

Ví dụ xử lý ở tầng API:

~~~java
@RestControllerAdvice
public class DatabaseExceptionHandler {

    @ExceptionHandler(QueryTimeoutException.class)
    @ResponseStatus(HttpStatus.GATEWAY_TIMEOUT)
    public ApiError handleQueryTimeout(QueryTimeoutException exception) {
        return new ApiError(
            "DATABASE_QUERY_TIMEOUT",
            "The database query took too long. Please retry later."
        );
    }
}
~~~

HTTP 504 có thể phù hợp khi ứng dụng không hoàn thành thao tác do dependency database timeout. Một số hệ thống chọn 503 cho tình trạng database quá tải hoặc không sẵn sàng. Hãy thống nhất mapping lỗi với API contract và gateway/load balancer.

Lưu ý rằng driver-specific exception có thể được dịch sang subtype khác. Trong hệ thống thực tế, log exception chain và SQL state để xác định nguyên nhân chính xác.

## 12. Những lỗi cấu hình thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ connectionTimeout của Hikari là timeout kết nối mạng | Driver có thể vẫn chờ mở socket lâu | Cấu hình driver connectTimeout riêng |
| Chỉ đặt query timeout | Một transaction nhiều query vẫn có thể tồn tại lâu | Thêm transaction timeout |
| Chỉ đặt transaction timeout nhưng dùng JDBC connection tự mở | Statement có thể không nhận timeout còn lại | Dùng Spring-managed DataSource/connection |
| Nhầm đơn vị giây và millisecond | Timeout quá ngắn hoặc quá dài | Kiểm tra đơn vị của từng property/driver |
| Đặt socketTimeout quá thấp | Query hợp lệ hoặc kết quả lớn bị ngắt giữa chừng | Chọn theo thời gian đọc và driver |
| Cho rằng query timeout luôn hủy server statement ngay | Database có thể còn xử lý hoặc cancellation phụ thuộc driver | Cấu hình thêm timeout phía database |
| Đặt transaction timeout quá ngắn | Transaction hợp lệ thường xuyên rollback | Đo latency và đặt budget thực tế |
| Transaction giữ connection trong lúc gọi HTTP | Pool cạn khi dịch vụ ngoài chậm | Không giữ transaction khi chờ hệ thống ngoài |
| Tăng pool size để chữa timeout | Database có thể bị quá tải nặng hơn | Kiểm tra query, lock và connection hold time |
| Retry mọi timeout | Có thể ghi trùng hoặc thực hiện command hai lần | Dùng idempotency và retry có kiểm soát |
| Nghĩ timeout luôn đồng nghĩa rollback | Kết quả commit có thể không rõ khi mất kết nối | Reconcile trạng thái bằng business key |
| Nhầm maxLifetime với query timeout | Connection bị retire không giới hạn query đang chạy | Dùng đúng loại timeout cho từng giai đoạn |

## 13. Kiểm thử timeout

Timeout nên được kiểm thử ở nhiều tầng:

### Kiểm thử query timeout

Với database hỗ trợ câu lệnh chờ, có thể dùng query cố ý chạy lâu trong test integration. Ví dụ PostgreSQL:

~~~sql
SELECT pg_sleep(3);
~~~

Đặt query timeout thấp hơn thời gian sleep và xác minh ứng dụng nhận lỗi timeout. Chỉ dùng câu lệnh như vậy trong database test riêng.

### Kiểm thử transaction timeout

Tạo một use case transaction có nhiều câu lệnh hoặc một statement chạy lâu. Đặt @Transactional(timeout = 1) và xác minh transaction không commit khi vượt thời hạn được transaction manager áp dụng.

Không dùng Thread.sleep() làm bằng chứng duy nhất cho transaction timeout: nó chỉ chặn thread Java, không nhất thiết khiến transaction manager hủy công việc ngoài JDBC ngay lập tức.

### Kiểm thử pool acquisition timeout

Trong test riêng, cấu hình pool có kích thước rất nhỏ, giữ connection bằng một transaction và yêu cầu một thread khác lấy connection. Xác minh thread thứ hai nhận timeout theo cấu hình. Đảm bảo test giải phóng connection và không ảnh hưởng các test khác.

### Kiểm thử driver/network timeout

Không nên dùng một địa chỉ database không phản hồi trong test suite thông thường vì kết quả phụ thuộc DNS, firewall và hạ tầng. Có thể dùng môi trường integration chuyên biệt hoặc proxy/network fault injection để kiểm tra connectTimeout và socketTimeout.

## 14. Quy trình cấu hình trong ứng dụng Spring Data JDBC

1. Xác định request deadline và latency budget của use case.
2. Kiểm tra DataSource đang dùng pool nào; nếu là HikariCP, đặt connection acquisition timeout.
3. Đặt connect timeout theo JDBC driver để giới hạn thời gian mở kết nối vật lý.
4. Cấu hình spring.jdbc.template.query-timeout cho các statement đi qua template auto-configured.
5. Đặt transaction timeout mặc định bằng spring.transaction.default-timeout nếu phù hợp.
6. Dùng @Transactional(timeout = ...) cho use case có yêu cầu riêng.
7. Cấu hình database-side statement_timeout/lock_timeout nếu cần giới hạn tại server.
8. Đảm bảo timeout ở các tầng có thứ tự hợp lý và không mâu thuẫn với request deadline.
9. Theo dõi pool metrics, query latency, transaction duration và timeout count.
10. Kiểm thử cả timeout thành công, rollback và trạng thái không rõ sau lỗi mạng.

## 15. Bài thực hành

1. Tạo ứng dụng Spring Data JDBC dùng HikariCP và quan sát thời gian chờ lấy connection khi pool đã hết connection rảnh.
2. Đặt spring.datasource.hikari.connection-timeout=1000; tạo tình huống pool saturation và quan sát lỗi.
3. Đặt spring.jdbc.template.query-timeout=2s; chạy một query test mất hơn 2 giây.
4. Viết service có @Transactional(timeout = 5) và thực hiện nhiều câu SQL trong một transaction.
5. Đặt query timeout dài hơn transaction timeout; quan sát statement bị giới hạn theo thời gian transaction còn lại.
6. Cấu hình spring.transaction.default-timeout=8s rồi override một method bằng @Transactional(timeout = 3).
7. Thử connectTimeout của PostgreSQL và MySQL Connector/J; ghi lại sự khác nhau về đơn vị.
8. Với PostgreSQL test container, thử SET LOCAL statement_timeout và SET LOCAL lock_timeout.
9. Tạo một query timeout và xác minh transaction rollback khi lỗi xảy ra.
10. Thử tình huống client mất kết nối sau khi gửi lệnh ghi; thiết kế cách kiểm tra trạng thái để tránh retry tạo dữ liệu trùng.
11. Quan sát Hikari active/idle/pending metrics và xác định nguyên nhân pool exhaustion.
12. Viết exception handler phân biệt query timeout, không lấy được connection và lỗi dữ liệu.

## 16. Ghi nhớ

Đặt timeout cho Spring Data JDBC cần bao phủ nhiều giai đoạn. Hikari connectionTimeout giới hạn thời gian chờ mượn connection từ pool; JDBC driver connectTimeout giới hạn thời gian mở kết nối vật lý; JdbcTemplate query timeout giới hạn một statement; transaction timeout giới hạn thời gian transaction do Spring quản lý. Database còn có thể đặt statement timeout và lock timeout để bảo vệ tài nguyên ở phía server.

Spring Boot cung cấp spring.datasource.hikari.connection-timeout, spring.jdbc.template.query-timeout và spring.transaction.default-timeout. Có thể đặt timeout riêng cho use case bằng @Transactional(timeout = ...). Luôn kiểm tra đơn vị thời gian, driver đang dùng và connection có tham gia Spring transaction hay không. Kết hợp timeout với đo đạc, xử lý lỗi và idempotency; timeout giúp giới hạn thời gian chờ nhưng không tự chứng minh một thao tác ghi chưa được commit.

## Tài liệu tham khảo

- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Framework — Declarative Transaction Annotations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP)
- [PostgreSQL JDBC — Connection Parameters](https://jdbc.postgresql.org/documentation/use/)
- [MySQL Connector/J — Networking Properties](https://dev.mysql.com/doc/connector-j/en/connector-j-connp-props-networking.html)

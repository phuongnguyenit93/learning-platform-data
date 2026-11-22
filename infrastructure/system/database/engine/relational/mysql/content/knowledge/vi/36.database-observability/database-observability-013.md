# Giữ ngữ cảnh ứng dụng khi đối chiếu log với CONNECTION_ID

Khi một request của ứng dụng chạy chậm hoặc thất bại trong MySQL, người vận hành thường phải nối nhiều mảnh thông tin: trace trong log ứng dụng, phiên kết nối đang chạy, câu SQL, thời gian chờ khóa và bản ghi trong general log hoặc slow query log. Khóa nối hữu ích nhất ở phía MySQL là connection ID của phiên vật lý. Hàm CONNECTION_ID() trả về ID của kết nối hiện tại; ID này xuất hiện trong PROCESSLIST_ID của Performance Schema và trong trường thread_id của general log.

Connection ID chỉ nhận diện một phiên kết nối tại một máy chủ MySQL trong một khoảng thời gian. Nó không phải trace ID, request ID hay Performance Schema THREAD_ID. Muốn điều tra đáng tin cậy, ứng dụng phải ghi lại connection ID cùng định danh instance và trace của request; phía MySQL phải ánh xạ đúng ID sang thread và statement; connection pool phải quản lý ngữ cảnh theo từng lần mượn kết nối.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

- Giải thích connection ID đại diện cho điều gì và phân biệt nó với THREAD_ID, request ID và trace ID.
- Lấy CONNECTION_ID() trên đúng connection mà request đang sử dụng và ghi nó vào log ứng dụng.
- Gắn thuộc tính tĩnh của ứng dụng vào handshake để nhận diện service, phiên bản và instance.
- Gắn ngữ cảnh request vào session hoặc từng câu SQL mà không làm rò rỉ dữ liệu giữa các lượt mượn connection pool.
- Dùng performance_schema.threads, session_connect_attrs và các bảng statement event để tìm hoạt động của một connection.
- Đối chiếu connection ID với general log, slow query log và error log trong giới hạn dữ liệu mà từng loại log cung cấp.
- Xử lý các tình huống reconnect, proxy, replica, connection pool và lịch sử Performance Schema bị ghi đè.

Phạm vi ở đây là MySQL Server và ứng dụng kết nối trực tiếp hoặc qua connection pool. Nếu có proxy hoặc lớp định tuyến SQL, cần xác định rõ ID thuộc kết nối phía client hay kết nối backend tới MySQL.

## 2. CONNECTION_ID() nhận diện phiên nào?

Mỗi kết nối client tới MySQL được máy chủ gán một connection ID. Trên chính kết nối đó, chạy:

~~~sql
SELECT CONNECTION_ID() AS connection_id;
~~~

Kết quả là số định danh của phiên hiện tại. Có thể dùng ID này trong các lệnh chẩn đoán như SHOW PROCESSLIST hoặc KILL QUERY, và đối chiếu với PROCESSLIST_ID trong Performance Schema.

Ví dụ, ứng dụng đang xử lý request checkout và nhận được connection ID là 18427. Khi mở một kết nối quản trị tới đúng MySQL instance, người vận hành có thể tìm phiên 18427 trong danh sách thread đang tồn tại. Kết nối quản trị dùng một connection ID khác; điều đó không ảnh hưởng đến việc tra cứu ID của phiên checkout.

### 2.1. Phân biệt các loại ID

| Giá trị | Ý nghĩa | Nơi thường gặp |
|---|---|---|
| CONNECTION_ID() | ID của phiên client hiện tại trên MySQL Server | Hàm SQL, PROCESSLIST_ID, general log |
| PROCESSLIST_ID | Connection ID được biểu diễn trong hàng thread của Performance Schema | performance_schema.threads |
| THREAD_ID | ID nội bộ của Performance Schema dùng để nối các bảng event | performance_schema.threads và các bảng events_* |
| request_id | ID của một request nghiệp vụ hoặc một lần xử lý công việc | Log ứng dụng, message hoặc job |
| trace_id | ID nối các span trong một distributed trace | Hệ thống tracing |
| span_id | ID của một đoạn xử lý trong trace | Hệ thống tracing |

Không so sánh CONNECTION_ID() trực tiếp với THREAD_ID. Muốn tìm statement event của một connection, trước tiên ánh xạ PROCESSLIST_ID sang THREAD_ID qua bảng performance_schema.threads, sau đó dùng THREAD_ID để truy vấn bảng events_statements_*.

Connection ID cũng không phải khóa toàn cục vĩnh viễn. Nó gắn với một instance MySQL và một phiên kết nối. Sau reconnect, ứng dụng nhận ID mới. Khi điều tra qua thời điểm restart, failover hoặc nhiều máy chủ, hãy ghi thêm tên định danh instance, endpoint hoặc vai trò primary/replica và thời điểm. Không dùng riêng một số connection ID để nhận diện phiên trên toàn cluster.

### 2.2. Kết nối vật lý và request logic

Một connection pool giữ một số kết nối vật lý tới MySQL và cho nhiều request mượn dùng lần lượt. Nhiều request khác nhau có thể dùng cùng một connection ID ở các thời điểm khác nhau:

~~~text
Request A ── mượn connection vật lý 18427 ── trả connection
Request B ── mượn lại connection 18427 ──── trả connection
Request C ── mượn connection vật lý 18431 ── trả connection
~~~

Vì vậy, connection ID cho biết câu SQL đi qua phiên nào, nhưng không tự cho biết request nào đã gửi câu SQL đó. Ứng dụng cần ghi trace_id hoặc request_id trong cùng bản ghi log với connection ID. Khi một request dùng nhiều connection, hãy ghi từng connection đã tham gia hoặc ghi một sự kiện riêng cho mỗi lần mượn connection.

## 3. Xây dựng chuỗi đối chiếu từ ứng dụng tới MySQL

Một chuỗi đối chiếu có thể được tổ chức như sau:

~~~text
HTTP request / message / scheduled job
              |
              v
     trace_id, request_id
              |
              v
  application acquires pooled connection
              |
              +---- SELECT CONNECTION_ID()
              |
              v
  application log: trace + db instance + connection_id
              |
              v
         MySQL Server
              |
              +---- PROCESSLIST_ID -> THREAD_ID
              |                         |
              |                         +--> statement event history
              |
              +---- general log thread_id
              |
              +---- slow log connection Id (nếu định dạng có trường này)
              |
              +---- connection attributes
~~~

Mỗi thành phần trả lời một câu hỏi khác nhau:

- Log ứng dụng cho biết request nghiệp vụ nào đang chạy, ai gọi nó, trace nào đang theo dõi và ứng dụng đã mượn connection nào.
- Connection ID nối hoạt động của request với phiên MySQL cụ thể.
- Performance Schema cho biết thread nội bộ nào tương ứng với connection đó và những statement event nào còn nằm trong vùng lịch sử.
- General log có thể cho thấy các lệnh đã đi qua server, bao gồm cả những câu lệnh ngắn không xuất hiện trong slow query log.
- Slow query log tập trung vào câu lệnh vượt ngưỡng ghi nhận; một số định dạng có trường Id để nhận diện connection.
- Error log ghi sự kiện máy chủ. Không phải mọi thông điệp error log đều mang connection ID, nên không thể xem đây là khóa nối duy nhất cho mọi lỗi.

Nên thống nhất tên trường trong log ứng dụng, ví dụ db_instance, db_connection_id, db_user, db_schema, request_id và trace_id. Giữ nguyên kiểu số của connection ID khi ghi log; tránh chuyển đổi qua kiểu số có thể làm mất độ chính xác.

## 4. Lấy connection ID trong chính connection của request

Điểm quan trọng nhất là truy vấn CONNECTION_ID() trên chính đối tượng connection đang được dùng để chạy nghiệp vụ. Nếu gọi hàm trên một connection quản trị hoặc một connection khác lấy từ pool, kết quả sẽ không đại diện cho phiên thực thi câu SQL cần điều tra.

Ví dụ với JDBC:

~~~java
long readConnectionId(Connection connection) throws SQLException {
    String sql = "SELECT CONNECTION_ID()";
    try (Statement statement = connection.createStatement();
         ResultSet result = statement.executeQuery(sql)) {
        if (!result.next()) {
            throw new SQLException("MySQL did not return CONNECTION_ID()");
        }
        return result.getLong(1);
    }
}
~~~

Sau khi mượn connection, ứng dụng lấy ID và ghi cùng ngữ cảnh request:

~~~java
try (Connection connection = dataSource.getConnection()) {
    long connectionId = readConnectionId(connection);

    logger.info(
        "mysql connection acquired",
        kv("trace_id", traceId),
        kv("request_id", requestId),
        kv("db_instance", dbInstance),
        kv("db_connection_id", connectionId)
    );

    // Thực hiện các câu SQL nghiệp vụ trên chính connection này.
}
~~~

Đây là ví dụ minh họa; hàm kv phụ thuộc thư viện logging của ứng dụng. Nếu pool có hook lúc tạo connection vật lý, có thể lưu connection ID ở metadata của đối tượng connection sau khi kiểm tra hành vi reconnect của driver. Với cách lưu đó, khi mượn connection vẫn phải ghi ID vào log của request hiện tại. Nếu driver tự reconnect hoặc proxy đổi backend, cần lấy lại thông tin nhận diện phù hợp.

Một bản ghi log có ích thường chứa:

~~~json
{
  "timestamp": "2026-11-19T07:15:32.412Z",
  "level": "INFO",
  "event": "mysql_connection_acquired",
  "service": "orders-api",
  "service_instance": "orders-api-7f3a",
  "environment": "production",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "req-20261119-00421",
  "db_instance": "mysql-orders-primary-a",
  "db_connection_id": 18427,
  "db_schema": "orders"
}
~~~

Dùng timestamp UTC hoặc một quy ước thời gian thống nhất. Đồng bộ đồng hồ giữa ứng dụng, MySQL Server và máy thu thập log để có thể so sánh sự kiện theo thời gian. Nếu một request truy cập primary và replica, hãy ghi riêng instance và connection ID cho từng endpoint.

Không cần ghi connection ID vào mọi metric label. ID có độ phân biệt cao, khiến số lượng chuỗi thời gian tăng mạnh. Hãy để ID trong log hoặc trace; metric nên dùng nhãn có tập giá trị giới hạn như service, instance, operation và database role.

## 5. Gắn thuộc tính tĩnh khi mở kết nối

MySQL có thể nhận các connection attributes do client gửi trong quá trình handshake. Các thuộc tính này hữu ích để nhận diện service, phiên bản ứng dụng, runtime hoặc instance của process. Chúng mô tả nguồn tạo kết nối, thường tồn tại trong suốt vòng đời connection vật lý.

Performance Schema cung cấp bảng performance_schema.session_connect_attrs:

~~~sql
SELECT
    PROCESSLIST_ID AS connection_id,
    ATTR_NAME,
    ATTR_VALUE,
    ORDINAL_POSITION
FROM performance_schema.session_connect_attrs
WHERE PROCESSLIST_ID = 18427
ORDER BY ORDINAL_POSITION;
~~~

PROCESSLIST_ID trong bảng này là connection ID. Một client có thể gửi nhiều cặp tên/giá trị; thứ tự được biểu diễn bằng ORDINAL_POSITION. Các thuộc tính mặc định và tên thuộc tính cụ thể phụ thuộc client library hoặc connector.

Ví dụ, MySQL Connector/J hỗ trợ thuộc tính kết nối tùy chỉnh qua connectionAttributes. Cấu hình minh họa:

~~~text
jdbc:mysql://db.example:3306/orders?connectionAttributes=service:orders-api,service_instance:orders-api-7f3a,environment:production
~~~

Cần kiểm tra cú pháp và phiên bản connector đang triển khai, nhất là khi giá trị có ký tự cần URL encode. Một số connector có cách cấu hình thuộc tính riêng; client không gửi thuộc tính thì server không thể tự suy ra tên service từ request.

Connection attributes phù hợp với thông tin tương đối ổn định:

- Tên service hoặc ứng dụng.
- Phiên bản build hoặc release.
- Tên instance của process.
- Runtime, nền tảng hoặc môi trường triển khai.

Không dùng connection attributes làm nơi lưu request_id hoặc trace_id thay đổi theo từng request. Khi connection pool tái sử dụng một connection, thuộc tính handshake vẫn mô tả process đã mở connection, không tự thay đổi theo request đang mượn nó.

Nếu bảng không có dữ liệu như mong đợi, kiểm tra Performance Schema có được bật hay không, connector có gửi thuộc tính hay không và giới hạn lưu thuộc tính của server qua performance_schema_session_connect_attrs_size. Thuộc tính quá dài hoặc vượt giới hạn có thể không được lưu đầy đủ. Không nên tăng giới hạn tùy tiện mà không cân nhắc bộ nhớ và kích thước metadata.

## 6. Gắn ngữ cảnh theo request trên connection pool

Khi cần giữ request context ở phía server trong thời gian một request sử dụng connection, có thể đặt các user-defined session variables:

~~~sql
SET
    @app_service = 'orders-api',
    @app_request_id = 'req-20261119-00421',
    @app_trace_id = '4bf92f3577b34da6a3ce929d0e0e4736';

SELECT
    CONNECTION_ID() AS connection_id,
    @app_service AS app_service,
    @app_request_id AS request_id,
    @app_trace_id AS trace_id;
~~~

Các biến này thuộc session hiện tại. Code chạy trên cùng connection có thể đọc lại chúng; câu SET cũng có thể tạo mốc trong log nếu đường ghi log đang thu thập statement. Trên MySQL 8.0.22 trở lên, Performance Schema cung cấp performance_schema.user_variables_by_thread để xem user-defined variables theo THREAD_ID từ một session quản trị, nếu bảng có sẵn và tài khoản có quyền đọc. Muốn kiểm tra một connection từ bên ngoài, trước tiên ánh xạ PROCESSLIST_ID sang THREAD_ID; chạy SELECT @app_request_id trên connection quản trị chỉ đọc biến của chính connection quản trị đó.

Ví dụ, sau khi đã xác định THREAD_ID=731:

~~~sql
SELECT THREAD_ID, VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.user_variables_by_thread
WHERE THREAD_ID = 731
  AND VARIABLE_NAME IN ('app_service', 'app_request_id', 'app_trace_id')
ORDER BY VARIABLE_NAME;
~~~

Bảng này giúp kiểm tra context còn gắn với session hay không. Giá trị có thể biến mất khi biến được xóa, session được reset hoặc thread kết thúc. Trên phiên bản không có bảng này, dựa vào log ứng dụng, statement history và thao tác kiểm tra ngay trong session. Vì bảng có thể hiển thị giá trị user variables của nhiều thread, giới hạn quyền truy cập và không lưu bí mật trong các biến này.

### 6.1. Quy tắc với pool

Một connection vật lý có thể được nhiều request mượn lần lượt. Vì vậy, mỗi lần checkout cần gán lại toàn bộ các biến context mà ứng dụng sử dụng, kể cả trường hợp giá trị mới là NULL. Khi trả connection, xóa context trong khối cleanup hoặc dùng cơ chế reset session của connector/pool đã được kiểm chứng.

Có thể đặt các giá trị bằng prepared statement:

~~~sql
SET
    @app_service = ?,
    @app_request_id = ?,
    @app_trace_id = ?;
~~~

Ứng dụng truyền giá trị bằng bind parameters. Không ghép trực tiếp dữ liệu request vào chuỗi SQL. Nếu một trường không có giá trị, vẫn truyền NULL để ghi đè dữ liệu còn sót từ lần mượn trước.

Khi kết thúc request, có thể xóa rõ ràng:

~~~sql
SET
    @app_service = NULL,
    @app_request_id = NULL,
    @app_trace_id = NULL;
~~~

Đặt thao tác cleanup trong finally hoặc callback trả connection để nó vẫn được thực hiện khi câu SQL nghiệp vụ ném exception. Nếu cleanup thất bại, đánh dấu connection không an toàn và loại nó khỏi pool theo chính sách của pool; đừng trả một session có context chưa xác định cho request tiếp theo.

### 6.2. Vì sao ROLLBACK không xóa user variables?

User-defined session variables thuộc trạng thái session, không phải dữ liệu transactional. ROLLBACK hoàn tác thay đổi dữ liệu trong transaction nhưng không tự xóa các biến @app_request_id hoặc @app_trace_id. Do đó, không dùng rollback như cơ chế dọn context.

Một số connector hoặc pool có thể reset session bằng giao thức COM_RESET_CONNECTION hoặc một cơ chế tương đương. Cơ chế này có thể xóa trạng thái session, nhưng cần xác nhận phiên bản driver, cấu hình pool và hành vi thực tế. Dù có reset, ứng dụng vẫn nên gán đầy đủ context khi checkout để không phụ thuộc vào trạng thái còn lại.

Không lưu password, access token, dữ liệu cá nhân hoặc nội dung nhạy cảm trong session variables. Những giá trị đó có thể xuất hiện trong general log, statement history hoặc bản ghi chẩn đoán. Chỉ truyền ID mờ, có thời hạn và không chứa bí mật.

## 7. Dùng SQL comment để gắn nhãn từng statement

Nếu mục tiêu là nối một câu SQL cụ thể với request đã phát ra nó, có thể thêm comment vào đầu câu lệnh:

~~~sql
/* service=orders-api request=req-20261119-00421 trace=4bf92f3577b34da6a3ce929d0e0e4736 */
SELECT order_id, status
FROM orders
WHERE customer_id = 9021
ORDER BY created_at DESC
LIMIT 20;
~~~

Comment giúp người đọc nhận ra request hoặc operation ngay trong SQL text được ghi nhận. Cách này hữu ích khi một connection chạy nhiều câu lệnh hoặc một request chỉ có một vài câu truy vấn cần theo dõi.

Cần kiểm chứng comment còn nguyên vẹn qua driver, ORM, proxy và đường ghi log đang sử dụng. Một số lớp trung gian có thể chuẩn hóa hoặc loại comment. Performance Schema có cả SQL_TEXT và DIGEST_TEXT: SQL_TEXT phù hợp hơn để kiểm tra câu lệnh gốc; DIGEST_TEXT là dạng chuẩn hóa để nhóm statement và có thể không giữ comment như một nhãn truy vết. Không dựa vào digest để tìm một request ID cụ thể.

Giữ comment ngắn, dùng ký tự an toàn và chỉ chèn các giá trị đã được kiểm soát. Không nối chuỗi tùy ý từ input người dùng vào comment. Không nhầm comment truy vết với optimizer hint có cú pháp /*+ ... */. Việc thêm request ID vào mọi statement cũng làm log lớn hơn và có thể làm giảm khả năng nhóm câu lệnh; chỉ dùng khi giá trị điều tra lớn hơn chi phí lưu trữ.

Comment và session variables có vai trò khác nhau. Comment gắn vào một statement cụ thể và có thể xuất hiện cùng SQL text. Session variable gắn với trạng thái connection và có thể được đọc lại trong chính session. Connection attribute gắn với handshake và mô tả process mở connection. Có thể kết hợp chúng, nhưng vẫn phải ghi trace/request ID trong log ứng dụng.

## 8. Ánh xạ connection ID sang Performance Schema THREAD_ID

Bảng performance_schema.threads chứa các thread đang được Performance Schema theo dõi. PROCESSLIST_ID là connection ID; THREAD_ID là khóa nội bộ để nối sang các bảng event.

~~~sql
SELECT
    THREAD_ID,
    PROCESSLIST_ID AS connection_id,
    NAME,
    TYPE,
    PROCESSLIST_USER,
    PROCESSLIST_HOST,
    PROCESSLIST_DB,
    PROCESSLIST_COMMAND,
    PROCESSLIST_TIME,
    PROCESSLIST_STATE,
    PROCESSLIST_INFO
FROM performance_schema.threads
WHERE PROCESSLIST_ID = 18427;
~~~

Nếu truy vấn trả về một hàng, lưu THREAD_ID để tra cứu statement history. Nếu không có hàng, connection có thể đã đóng, ID có thể thuộc instance khác, hoặc session đã đi qua proxy và ID bạn có là ID ở phía client. Các thread nền của MySQL thường không có PROCESSLIST_ID tương ứng với connection client.

Không nhầm PROCESSLIST_INFO với lịch sử đầy đủ. Cột này phản ánh thông tin statement hiện tại của thread và có thể NULL khi session đang idle. Muốn xem những statement gần đây, dùng các bảng events_statements_*.

### 8.1. Xem statement history của một thread

Sau khi có THREAD_ID, truy vấn lịch sử theo thread:

~~~sql
SELECT
    EVENT_ID,
    EVENT_NAME,
    SQL_TEXT,
    DIGEST_TEXT,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS elapsed_seconds,
    ROWS_EXAMINED,
    ROWS_SENT,
    MYSQL_ERRNO,
    RETURNED_SQLSTATE,
    MESSAGE_TEXT
FROM performance_schema.events_statements_history
WHERE THREAD_ID = 731
ORDER BY EVENT_ID DESC
LIMIT 20;
~~~

Thay 731 bằng THREAD_ID lấy từ truy vấn trước. TIMER_WAIT được biểu diễn bằng picosecond; chia cho 10^12 để đổi sang giây. Các cột lỗi và số hàng giúp phân biệt câu lệnh thất bại, câu lệnh trả nhiều dữ liệu và câu lệnh quét nhiều hàng.

events_statements_history giữ một số event gần đây theo từng thread. events_statements_history_long giữ một vùng lịch sử dùng chung cho nhiều thread. Cả hai là bộ đệm có giới hạn; event cũ sẽ bị ghi đè khi bộ đệm đầy. Đây không phải kho lịch sử bền vững để truy vấn tùy ý sau nhiều ngày.

Có thể truy vấn vùng lịch sử dùng chung:

~~~sql
SELECT
    THREAD_ID,
    EVENT_ID,
    SQL_TEXT,
    ROUND(TIMER_WAIT / 1000000000000, 6) AS elapsed_seconds,
    ROWS_EXAMINED,
    ROWS_SENT,
    MYSQL_ERRNO
FROM performance_schema.events_statements_history_long
WHERE THREAD_ID = 731
ORDER BY EVENT_ID DESC
LIMIT 50;
~~~

Nếu connection đã kết thúc, hàng trong performance_schema.threads có thể không còn để ánh xạ PROCESSLIST_ID sang THREAD_ID. Một số event lịch sử vẫn có thể còn trong history_long, nhưng muốn tìm đúng THREAD_ID sau khi thread biến mất cần có dữ liệu ánh xạ đã được ghi lại từ trước. Đây là lý do nên thu thập connection ID, instance và statement/log context khi phiên còn hoạt động.

### 8.2. Kiểm tra consumer và instrument

Performance Schema chỉ thu thập những loại event được bật. Kiểm tra consumer:

~~~sql
SELECT NAME, ENABLED
FROM performance_schema.setup_consumers
WHERE NAME IN (
    'global_instrumentation',
    'thread_instrumentation',
    'events_statements_current',
    'events_statements_history',
    'events_statements_history_long'
)
ORDER BY NAME;
~~~

Kiểm tra instrument cho statement:

~~~sql
SELECT NAME, ENABLED, TIMED
FROM performance_schema.setup_instruments
WHERE NAME LIKE 'statement/%'
ORDER BY NAME
LIMIT 30;
~~~

Nếu statement consumer hoặc instrument cần thiết đang tắt, lịch sử có thể trống hoặc không có thời gian thực thi. Chỉ bật đúng nhóm instrumentation cần dùng, cân nhắc overhead và dung lượng bộ đệm. Có thể bật consumer lịch sử trong một cửa sổ chẩn đoán có kiểm soát:

~~~sql
UPDATE performance_schema.setup_consumers
SET ENABLED = 'YES'
WHERE NAME IN (
    'events_statements_current',
    'events_statements_history',
    'events_statements_history_long'
);
~~~

Thay đổi setup table cần được thực hiện bởi tài khoản có quyền phù hợp và theo chính sách vận hành. Kích thước history long được cấu hình bằng các biến Performance Schema lúc khởi động; thay đổi kích thước có thể cần restart. Không bật mọi instrument trên production chỉ để tìm một request nếu chưa đánh giá tác động.

## 9. Đối chiếu với các loại log của MySQL

### 9.1. General query log

General query log ghi nhận các kết nối và câu lệnh mà server nhận được. Khi log được ghi ra TABLE, có thể truy vấn mysql.general_log:

~~~sql
SELECT
    event_time,
    user_host,
    thread_id,
    command_type,
    argument
FROM mysql.general_log
WHERE thread_id = 18427
ORDER BY event_time DESC
LIMIT 100;
~~~

Trong general log, thread_id là connection ID. Trường này cho phép nối trực tiếp với CONNECTION_ID() hoặc PROCESSLIST_ID. Khi log được ghi ra FILE, định dạng bản ghi cũng có thread ID để nhận diện connection.

General log có thể tạo lượng dữ liệu lớn và chứa SQL text hoặc thông tin nhạy cảm. Chỉ bật khi có mục tiêu điều tra cụ thể, thời lượng giới hạn, quyền truy cập phù hợp và kế hoạch tắt sau khi hoàn tất. Truy vấn mysql.general_log chỉ phản ánh bản ghi được ghi vào TABLE; nếu log_output chỉ ghi FILE thì bảng có thể không chứa các sự kiện mới. Đừng mặc định bảng luôn được cập nhật.

### 9.2. Slow query log

Slow query log chỉ ghi các statement thỏa điều kiện cấu hình, chẳng hạn vượt long_query_time hoặc đáp ứng các tùy chọn liên quan. Nhiều định dạng slow log có dòng User@Host kèm Id; Id này có thể dùng để nối với connection ID. Hãy kiểm tra định dạng thực tế của phiên bản MySQL và công cụ thu thập log đang sử dụng trước khi xây parser.

Slow log giúp tìm câu truy vấn tốn thời gian, thời gian chờ khóa, số hàng gửi và số hàng đã kiểm tra. Nó không phải bản ghi đầy đủ mọi câu SQL của một connection. Nếu request thất bại nhanh hoặc câu lệnh không vượt ngưỡng, statement có thể không xuất hiện trong slow log.

### 9.3. Error log

Error log tập trung vào sự kiện của server như lỗi khởi động, lỗi storage engine, cảnh báo, sự cố kết nối hoặc thông điệp từ subsystem. Cấu trúc và các trường đi kèm phụ thuộc phiên bản, log component và sink. Một số thông điệp có thông tin thread/connection; nhiều thông điệp khác không có.

Chỉ dùng connection ID để nối error log khi bản ghi thực sự cung cấp ID có ý nghĩa. Nếu không có, hãy ghép bằng thời gian, instance, host, user, trạng thái server và sự kiện ứng dụng liên quan. Tránh suy ra rằng mọi lỗi server đều phát sinh từ connection ID gần nhất trong log.

## 10. Quy trình điều tra một request chậm hoặc lỗi

Giả sử log ứng dụng ghi nhận request_id=req-20261119-00421, trace_id=4bf92f... và db_connection_id=18427.

1. **Xác định đúng MySQL instance.** Dùng db_instance hoặc endpoint được ghi trong log. Nếu hệ thống có nhiều replica, proxy hoặc cluster, xác định request đã đi tới node nào tại thời điểm đó.
2. **Tìm request trong log ứng dụng.** Đọc các sự kiện trước và sau khi mượn connection, thời gian bắt đầu/kết thúc truy vấn, retry, timeout và exception. Xác định request đã dùng một hay nhiều connection.
3. **Tìm connection đang hoạt động.** Trên đúng instance, tra performance_schema.threads với PROCESSLIST_ID=18427. Lưu THREAD_ID nếu còn hàng.
4. **Đọc statement event.** Dùng THREAD_ID để xem events_statements_current, events_statements_history hoặc events_statements_history_long. Đối chiếu SQL_TEXT, TIMER_WAIT, ROWS_EXAMINED, lỗi và thời điểm.
5. **Đối chiếu log SQL.** Tìm thread_id=18427 trong general log nếu log đang ghi vào TABLE, hoặc tìm Id tương ứng trong slow query log nếu định dạng có trường này.
6. **Đọc connection attributes.** Dùng session_connect_attrs để xác nhận service, phiên bản và instance process đã mở connection. Những giá trị này giúp phát hiện request đi qua nhầm service hoặc bản triển khai.
7. **So sánh thời gian và ngữ cảnh.** Chuẩn hóa timestamp, xem transaction, trạng thái chờ, câu lệnh trước đó và retry. Một request có thể bị chậm vì lock hoặc connection pool chờ cấp connection trước khi MySQL nhận SQL.
8. **Kết luận theo bằng chứng.** Phân biệt thời gian chờ pool, thời gian kết nối, thời gian chạy SQL, lock wait và thời gian xử lý phía ứng dụng. Connection ID nối phiên; nó không tự chứng minh nguyên nhân chậm.

Nếu thread vẫn tồn tại nhưng PROCESSLIST_INFO là NULL, session có thể đang idle hoặc chờ ứng dụng gửi câu lệnh tiếp theo. Xem statement history và log ứng dụng để hiểu những câu lệnh trước đó. Nếu thread đã biến mất, chuyển sang general/slow log, trace và dữ liệu thu thập trước đó; không thể yêu cầu Performance Schema khôi phục một ánh xạ session đã mất.

## 11. Các tình huống dễ làm sai kết quả

### 11.1. Connection pool tái sử dụng session

Connection ID có thể xuất hiện trong log của nhiều request ở các thời điểm khác nhau. Không gom tất cả statement của connection thành một request duy nhất. Dùng request_id/trace_id và timestamp để phân tách các lần mượn. Gán lại toàn bộ session context khi checkout và xóa khi trả connection.

### 11.2. Ứng dụng tự reconnect

Khi connection đứt và driver tạo phiên mới, connection ID thay đổi. Nếu ứng dụng chỉ lưu ID lúc khởi tạo pool, log có thể gắn câu SQL vào ID cũ. Lấy lại ID sau reconnect hoặc mỗi lần checkout theo thiết kế driver, rồi ghi nhận sự kiện thay đổi connection.

### 11.3. Proxy hoặc SQL router

Có thể tồn tại ít nhất hai phiên: client tới proxy và proxy tới MySQL backend. ID ở phía client không nhất thiết bằng PROCESSLIST_ID trên backend. Một proxy có thể tái sử dụng backend connection hoặc ghép nhiều frontend session theo chính sách riêng. Khi có proxy, thu thập ID ở cả hai phía nếu sản phẩm hỗ trợ, đồng thời ghi proxy node, backend endpoint và thời điểm định tuyến. Không giả định ID của driver luôn là ID xuất hiện trong MySQL.

### 11.4. Một request dùng nhiều connection

Một request có thể đọc từ replica, ghi vào primary, hoặc chạy song song nhiều tác vụ. Khi đó một trace_id tương ứng với nhiều connection ID. Ghi mỗi cặp db_instance và db_connection_id vào một span hoặc event riêng, gắn operation tương ứng để biết câu lệnh nào chạy trên node nào.

### 11.5. Connection ID bị dùng như khóa lâu dài

Connection ID chỉ có ý nghĩa trong phạm vi instance và phiên. Khi điều tra dài ngày, lưu thêm định danh instance ổn định do hệ thống vận hành cấp, thời điểm, endpoint và vai trò. Sau failover, cùng một số ID ở node khác không biểu thị cùng một session.

### 11.6. Dữ liệu lịch sử đã bị ghi đè

events_statements_history và events_statements_history_long có dung lượng hữu hạn. Nếu điều tra muộn, event có thể đã bị ghi đè. General log và slow query log cũng phụ thuộc cấu hình, rotation và thời gian lưu. Nếu cần điều tra sau nhiều giờ hoặc nhiều ngày, hãy chuyển dữ liệu cần thiết sang hệ thống log tập trung với retention phù hợp.

## 12. Ví dụ hoàn chỉnh: theo dõi một request checkout

Giả sử service orders-api nhận request checkout. Trace middleware cung cấp trace_id; tầng nghiệp vụ tạo request_id. Khi lấy connection từ pool, ứng dụng thực hiện theo thứ tự:

~~~sql
SELECT CONNECTION_ID();

SET
    @app_service = 'orders-api',
    @app_request_id = 'req-20261119-00421',
    @app_trace_id = '4bf92f3577b34da6a3ce929d0e0e4736';
~~~

Ứng dụng ghi log connection ID, db_instance, trace_id và request_id. Sau đó, câu truy vấn nghiệp vụ có thể mang comment:

~~~sql
/* service=orders-api request=req-20261119-00421 trace=4bf92f3577b34da6a3ce929d0e0e4736 */
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 9021
ORDER BY created_at DESC
LIMIT 20;
~~~

Khi cần điều tra, người vận hành dùng connection ID đã ghi trong log:

~~~sql
SELECT THREAD_ID, PROCESSLIST_ID, PROCESSLIST_USER,
       PROCESSLIST_HOST, PROCESSLIST_DB, PROCESSLIST_COMMAND,
       PROCESSLIST_TIME, PROCESSLIST_STATE
FROM performance_schema.threads
WHERE PROCESSLIST_ID = 18427;
~~~

Giả sử kết quả trả THREAD_ID=731. Tra lịch sử statement:

~~~sql
SELECT EVENT_ID, SQL_TEXT, DIGEST_TEXT,
       ROUND(TIMER_WAIT / 1000000000000, 6) AS elapsed_seconds,
       ROWS_EXAMINED, ROWS_SENT, MYSQL_ERRNO, RETURNED_SQLSTATE
FROM performance_schema.events_statements_history
WHERE THREAD_ID = 731
ORDER BY EVENT_ID DESC
LIMIT 20;
~~~

Tiếp theo, xác minh service và process đã mở connection:

~~~sql
SELECT ATTR_NAME, ATTR_VALUE
FROM performance_schema.session_connect_attrs
WHERE PROCESSLIST_ID = 18427
ORDER BY ORDINAL_POSITION;
~~~

Nếu general log đang ghi vào TABLE, có thể kiểm tra các lệnh cùng phiên:

~~~sql
SELECT event_time, command_type, argument
FROM mysql.general_log
WHERE thread_id = 18427
ORDER BY event_time DESC
LIMIT 100;
~~~

Khi hoàn tất request, ứng dụng xóa session context trước khi trả connection:

~~~sql
SET
    @app_service = NULL,
    @app_request_id = NULL,
    @app_trace_id = NULL;
~~~

Quy trình này tạo ra các mối nối có thể kiểm chứng: trace chỉ ra request; application log ghi connection ID và instance; PROCESSLIST_ID ánh xạ sang THREAD_ID; statement history cho thấy SQL; connection attributes xác nhận nguồn mở session; general/slow log cung cấp bằng chứng bổ sung nếu đã bật và còn dữ liệu.

## 13. Bảo mật và chi phí quan sát

Connection ID và trace ID thường không phải bí mật, nhưng log kết hợp chúng với user, host, schema, SQL text và dữ liệu nghiệp vụ có thể tiết lộ thông tin nhạy cảm. Áp dụng các nguyên tắc sau:

- Không đưa password, token, session cookie hoặc dữ liệu cá nhân vào connection attributes, session variables hay SQL comment.
- Giới hạn quyền đọc performance_schema, mysql.general_log và log tập trung theo vai trò vận hành.
- Tránh để general log bật kéo dài trên hệ thống có lưu lượng cao; đặt thời hạn, theo dõi dung lượng và tắt sau phiên điều tra.
- Không ghi request ID hoặc connection ID thành metric label có cardinality cao.
- Chuẩn hóa và giới hạn độ dài giá trị metadata; không nhận comment hoặc attribute tùy ý từ input bên ngoài.
- Quy định retention, masking và quyền truy cập đối với SQL text, vì câu lệnh có thể chứa literal hoặc thông tin nghiệp vụ.
- Kiểm tra chi phí của Performance Schema consumer/instrument trước khi bật rộng trên production.

## 14. Bảng xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| Không tìm thấy PROCESSLIST_ID | Session đã đóng, sai instance hoặc ID thuộc proxy/client | Xác minh db_instance, thời điểm, reconnect và backend endpoint |
| Có thread nhưng không có statement history | Consumer/instrument tắt, thread chưa chạy statement hoặc history đã bị ghi đè | Kiểm tra setup_consumers, setup_instruments và thời điểm thu thập |
| Không có connection attributes | Connector không gửi, Performance Schema tắt hoặc giới hạn thuộc tính | Kiểm tra cấu hình connector và performance_schema_session_connect_attrs_size |
| Request khác nhau dùng cùng connection ID | Pool tái sử dụng connection vật lý | Phân tách theo request_id, trace_id và timestamp; reset context khi checkout/return |
| Session context của request trước xuất hiện ở request sau | Không gán lại hoặc không cleanup user variables | Gán đầy đủ mọi biến khi checkout, cleanup trong finally, kiểm tra reset của pool |
| Comment không xuất hiện trong SQL_TEXT/log | Driver, ORM hoặc proxy đã chuẩn hóa câu SQL | Kiểm tra câu SQL thực tế tại từng lớp và dùng application log làm nguồn đối chiếu |
| ID trong app không khớp ID MySQL | Proxy tạo backend session hoặc driver reconnect | Ghi ID ở đúng phía, backend node và sự kiện reconnect |
| Không thấy truy vấn trong slow log | Câu lệnh không vượt ngưỡng hoặc log chưa bật | Dùng statement history/general log trong cửa sổ chẩn đoán phù hợp |
| Không nối được error log với request | Bản ghi không chứa connection ID | Ghép bằng instance, timestamp, subsystem và trace log ứng dụng |
| Không tìm thấy event sau một thời gian | Ring buffer đã bị ghi đè hoặc server restart | Thu thập/export event sớm và dùng log tập trung có retention |

## 15. Bài tập thực hành

### Bài 1: Phân biệt PROCESSLIST_ID và THREAD_ID

1. Mở một connection client và chạy SELECT CONNECTION_ID().
2. Từ connection quản trị, tìm ID đó trong performance_schema.threads.
3. Ghi lại PROCESSLIST_ID và THREAD_ID.
4. Dùng THREAD_ID để truy vấn events_statements_history.
5. Giải thích vì sao không dùng CONNECTION_ID() làm giá trị THREAD_ID.

Kết quả mong đợi: bạn chứng minh được ánh xạ qua performance_schema.threads và không nhầm hai không gian ID.

### Bài 2: Theo dõi một connection qua pool

1. Cấu hình ứng dụng lấy connection từ pool.
2. Ghi connection ID cùng request_id khi checkout.
3. Gửi hai request tuần tự để pool có cơ hội tái sử dụng một connection.
4. So sánh connection ID và request ID trong log.
5. Gán session variables cho request thứ nhất, sau đó kiểm tra request thứ hai không đọc được context cũ.

Kết quả mong đợi: bạn nhận ra connection ID có thể giống nhau trong khi request ID khác nhau, và session context phải được quản lý theo vòng đời checkout/return.

### Bài 3: So sánh connection attributes với request context

1. Gửi service, service instance và environment bằng connection attributes.
2. Đọc các giá trị trong performance_schema.session_connect_attrs.
3. Đặt @app_request_id trong một request.
4. Mượn lại connection và kiểm tra giá trị session variable.
5. Giải thích vì sao connection attribute mô tả process mở connection còn user variable mô tả trạng thái session hiện tại.

Kết quả mong đợi: bạn chọn đúng cơ chế cho metadata tĩnh và metadata thay đổi theo request.

### Bài 4: Điều tra câu SQL chậm

1. Ghi connection ID và trace ID từ log ứng dụng.
2. Tìm thread tương ứng trong performance_schema.threads.
3. Xem statement history và ghi lại SQL_TEXT, TIMER_WAIT, ROWS_EXAMINED.
4. Nếu có slow log, tìm Id tương ứng.
5. Xác định thời gian chậm nằm ở pool, kết nối, SQL execution hay lock wait dựa trên các mốc thời gian.

Kết quả mong đợi: báo cáo điều tra có instance, request, connection ID, THREAD_ID, câu SQL và bằng chứng thời gian.

## 16. Checklist triển khai

- [ ] Ứng dụng lấy CONNECTION_ID() từ đúng connection thực thi nghiệp vụ.
- [ ] Log ứng dụng ghi trace_id, request_id, db_instance và db_connection_id.
- [ ] Connection attributes chứa metadata tĩnh, không chứa dữ liệu nhạy cảm hoặc request context.
- [ ] Request context được gán đầy đủ khi checkout và xóa/reset khi return.
- [ ] Cleanup vẫn chạy khi statement lỗi hoặc transaction rollback.
- [ ] Các truy vấn Performance Schema phân biệt PROCESSLIST_ID và THREAD_ID.
- [ ] Consumer/instrument được bật có chủ đích và đã đánh giá chi phí.
- [ ] General log/slow log được dùng theo chính sách dung lượng, quyền truy cập và retention.
- [ ] Hệ thống có proxy/reconnect ghi nhận đúng backend instance và connection mapping.
- [ ] Timestamp được chuẩn hóa và đồng hồ các thành phần được đồng bộ.
- [ ] Trace/request ID nằm trong log hoặc trace, không trở thành metric label cardinality cao.
- [ ] Runbook nêu rõ cách xử lý khi thread đã đóng hoặc event history bị ghi đè.

## 17. Tài liệu cần tra cứu

Khi triển khai trên một phiên bản MySQL cụ thể, đối chiếu hành vi và tên cột với MySQL Reference Manual tương ứng:

- Information Functions: CONNECTION_ID().
- Performance Schema: threads table và PROCESSLIST_ID.
- Performance Schema: session_connect_attrs table.
- Performance Schema: user_variables_by_thread table (MySQL 8.0.22 trở lên).
- Performance Schema: statement event tables, setup_consumers và setup_instruments.
- The General Query Log và The Slow Query Log.
- MySQL Connector/J: connectionAttributes property.

Luôn kiểm tra phiên bản MySQL Server, connector, pool và proxy thực tế. Khả năng gửi connection attributes, định dạng log và cấu hình Performance Schema có thể khác giữa các phiên bản và triển khai.


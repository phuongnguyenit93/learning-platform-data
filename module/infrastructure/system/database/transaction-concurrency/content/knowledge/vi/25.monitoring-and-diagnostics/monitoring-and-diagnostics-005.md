# Liên kết mã yêu cầu ứng dụng với kết nối và giao dịch cơ sở dữ liệu

Khi một request chậm, bị deadlock hoặc trả về lỗi dữ liệu, log ứng dụng thường cho biết request nào thất bại nhưng log database lại chỉ hiển thị session, connection hoặc transaction ID. Nếu không có cách liên kết các định danh này, việc điều tra phải dựa vào thời gian gần đúng và suy đoán.

Mục tiêu của quan sát hệ thống là nối được các lớp thông tin:

**Request của người dùng → trace/span của ứng dụng → thao tác repository/ORM → connection vật lý → session của DBMS → transaction → câu lệnh SQL.**

Việc liên kết này không tự xuất hiện chỉ vì ứng dụng đã tạo một request ID. Request có thể dùng nhiều connection; một connection pool có thể tái sử dụng cùng session cho nhiều request khác nhau; một transaction có thể chạy nhiều câu SQL; và một request có thể tạo nhiều transaction độc lập. Vì vậy, cần hiểu từng loại định danh và gắn metadata ở đúng ranh giới.

Bài này trình bày cách thiết kế correlation ID, truyền trace context, gắn application metadata vào session database, ghi nhận transaction/connection ID, xử lý connection pool và nối log giữa ứng dụng với PostgreSQL, MySQL, SQL Server và Oracle.

## 1. Các định danh không có cùng phạm vi

Một hệ thống thường có nhiều ID cùng xuất hiện trong log. Chúng trả lời những câu hỏi khác nhau.

| Định danh | Phạm vi | Câu hỏi được trả lời |
|---|---|---|
| Request ID | Một lần nhận request ở một dịch vụ | Request HTTP hoặc RPC nào đang được xử lý? |
| Trace ID | Toàn bộ distributed trace | Những service/span nào thuộc cùng một hành trình nghiệp vụ? |
| Span ID | Một thao tác trong trace | Khoảng thời gian hoặc lời gọi cụ thể nào đang được đo? |
| Correlation ID | Một quy trình nghiệp vụ hoặc chuỗi message | Những log/event nào cần được nối với nhau? |
| Job ID | Một công việc nền | Worker đang xử lý job nào? |
| Connection ID | Một kết nối logic hoặc vật lý, tùy lớp | Kết nối nào đã thực hiện thao tác? |
| DB session ID | Một session phía DBMS | Process/session nào đang giữ khóa hoặc chạy SQL? |
| Transaction ID | Một transaction database | Thay đổi nào thuộc cùng đơn vị commit/rollback? |
| Statement/query ID | Một câu SQL hoặc lần thực thi | Câu lệnh cụ thể nào đã chạy? |

Không nên dùng một trường tên chung như request_id để chứa tất cả các giá trị trên. Một request có thể gọi nhiều service và mở nhiều transaction; một DB session có thể phục vụ nhiều request theo thời gian. Giữ các định danh riêng giúp phân tích đúng mối quan hệ.

### Request ID và Trace ID

Request ID thường được tạo ở gateway hoặc service đầu tiên nhận request. Nó hữu ích để tìm log của một lần gọi API. Trace ID có phạm vi rộng hơn: các service truyền trace context qua HTTP, RPC hoặc message để hệ thống tracing dựng được đường đi xuyên dịch vụ.

Một trace có thể chứa:

- Span nhận request ở API gateway.
- Span xử lý nghiệp vụ ở Order service.
- Span gọi Payment service.
- Span truy vấn database.
- Span publish event hoặc gọi broker.

Một request ID không nhất thiết bằng trace ID. Có thể dùng request ID làm thuộc tính của span, nhưng không nên ghi đè trace context chuẩn bằng một ID tự đặt nếu hệ thống tracing đã có cơ chế truyền context.

### Connection ID và DB session ID

Connection pool thường cung cấp một logical connection cho code ứng dụng. Logical connection có thể chỉ là handle mượn tạm; phía dưới nó là physical connection/socket và session thật ở DBMS. Khi code đóng logical connection, pool thường trả physical connection về pool thay vì đóng socket.

Vì vậy:

- Một request có thể mượn connection A, thực hiện transaction rồi trả lại pool.
- Request tiếp theo có thể mượn chính physical connection A và dùng lại DB session cũ.
- Một request có thể mượn nhiều connection nếu dùng nhiều datasource, transaction độc lập hoặc chạy song song.
- Một DB session có thể phục vụ nhiều request tuần tự, nhưng không nên được dùng đồng thời bởi nhiều request nếu driver/ORM không hỗ trợ.

Connection ID của driver, socket ID của pool và session ID của DBMS có thể là các giá trị khác nhau. Khi log, cần ghi rõ nguồn và loại ID.

## 2. Mô hình quan hệ giữa request, connection và transaction

Một request không tương đương với một transaction và cũng không tương đương với một connection.

~~~text
HTTP Request R-100 / Trace T-abc
        |
        +-- Service operation: load customer
        |       |
        |       +-- Connection C-1 / DB session 51
        |               +-- Transaction X-900
        |                       +-- SELECT customer
        |
        +-- Service operation: reserve inventory
        |       |
        |       +-- Connection C-2 / DB session 72
        |               +-- Transaction X-901
        |                       +-- UPDATE inventory
        |
        +-- Publish event
                +-- Broker span
~~~

Trong một request khác, có thể xảy ra trường hợp một connection/session chạy nhiều transaction:

~~~text
Request R-101
  Connection C-1 / DB session 51
    Transaction X-902 -> SELECT
    COMMIT
    Transaction X-903 -> UPDATE
    COMMIT
~~~

Session ID vẫn là 51, nhưng transaction ID thay đổi. Nếu chỉ log session ID, ta biết các câu lệnh dùng cùng session nhưng không thể khẳng định chúng thuộc cùng một transaction.

Ngược lại, một transaction có thể thực hiện nhiều statement trên cùng connection/session. Để điều tra một lỗi, cần nối cả request/trace, session và transaction chứ không chỉ một ID.

## 3. Thiết kế correlation metadata trong ứng dụng

Một log database hữu ích thường cần tối thiểu:

- Timestamp có timezone hoặc định dạng thống nhất.
- Service name và service version.
- Environment/region.
- Request ID hoặc correlation ID.
- Trace ID và span ID nếu có tracing.
- Job ID/message ID nếu thao tác đến từ worker.
- Logical connection label hoặc datasource name.
- DB session ID và transaction ID nếu lấy được.
- Tên operation/repository hoặc statement fingerprint.
- Thời gian chờ connection pool, thời gian thực thi SQL và kết quả.

Ví dụ log có cấu trúc:

~~~json
{
  "timestamp": "2026-11-14T10:15:30.120Z",
  "service": "order-service",
  "environment": "production",
  "request_id": "req-7f2a",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "operation": "OrderRepository.confirm",
  "datasource": "orders-primary",
  "db_session_id": 51,
  "db_transaction_id": "xid-900",
  "statement_fingerprint": "UPDATE orders SET status = ? WHERE id = ?",
  "duration_ms": 18,
  "rows_affected": 1
}
~~~

Các ID trong ví dụ là dữ liệu minh họa. Không log password, access token, connection string, dữ liệu thanh toán hoặc toàn bộ payload nhạy cảm. Với câu SQL có tham số nhạy cảm, nên log statement fingerprint/template và các thuộc tính đã được cho phép thay vì giá trị bind đầy đủ.

### Correlation ID phải được tạo và truyền nhất quán

Ở ranh giới HTTP:

1. Nếu request đến đã có trace context hợp lệ, tiếp tục trace theo chuẩn của hệ thống.
2. Tạo request ID riêng nếu service cần định danh lần nhận request.
3. Đưa các ID vào logging context để mọi log trong request tự mang cùng metadata.
4. Khi gọi service khác, truyền trace context qua cơ chế tracing; chỉ truyền business correlation ID riêng nếu cần nối workflow.
5. Khi enqueue job hoặc publish event, lưu correlation ID/trace context cần thiết trong message headers hoặc metadata.

Không tin một header correlation do client gửi vào một cách vô điều kiện. Cần giới hạn độ dài, chuẩn hóa định dạng và tránh cho client đặt giá trị có thể gây log injection hoặc làm lộ thông tin. Gateway có thể tạo ID nội bộ mới và lưu ID bên ngoài như một thuộc tính riêng nếu cần.

## 4. Truyền context qua thread, async và message

Trong xử lý đồng bộ, request context thường được lưu trong logging context như MDC (Mapped Diagnostic Context) hoặc cơ chế tương tự. Nhưng context gắn với thread không tự động đi theo mọi tác vụ bất đồng bộ.

Ví dụ:

~~~text
HTTP thread:
  request_id = R-100
  trace_id = T-abc
  submit task to executor
  return

Worker thread:
  nếu không truyền context:
    request_id = missing
    trace_id = missing
~~~

Khi dùng executor, thread pool, scheduler hoặc callback, cần truyền context bằng task decorator, context-propagation library hoặc API tracing phù hợp. Sau khi task hoàn tất, phải khôi phục/xóa context của thread để metadata của request trước không rò sang request tiếp theo.

Với reactive stack, context thường đi qua Reactor Context hoặc cơ chế tương đương, không nên dựa vào ThreadLocal như thể mỗi request luôn nằm trên một thread. Với message broker, trace context và correlation ID cần được đưa vào header/metadata của message rồi consumer tạo span mới liên kết với trace gốc hoặc theo quan hệ link phù hợp.

Một request có thể kết thúc trước khi job nền hoàn tất. Khi đó job cần giữ correlation ID/job ID đã được ghi nhận tại thời điểm enqueue; không phụ thuộc vào HTTP thread hoặc logging context đã biến mất.

## 5. Gắn metadata vào DB session

Log ở ứng dụng cho biết request nào gọi repository, nhưng khi DBA xem session đang block, họ thường chỉ có session ID và câu SQL. Có thể gắn application metadata vào session để truy vấn từ DBMS cũng thấy service/request liên quan.

Các trường metadata thường dùng:

- Application/service name.
- Module hoặc operation.
- Action cụ thể.
- Client identifier hoặc request correlation ID.
- Job/worker ID.
- Hostname/container instance.

Nên ưu tiên các trường session metadata được DBMS hỗ trợ thay vì thêm request ID vào mọi câu SQL bằng comment. Comment có thể hữu ích khi không có session metadata, nhưng làm query text thay đổi theo request có thể gây cardinality cao trong công cụ thống kê hoặc ảnh hưởng query fingerprint/cache tùy DBMS.

### Một quy tắc bắt buộc với connection pool

Vì physical session được tái sử dụng, metadata phải được đặt lại khi connection được mượn và được xóa/khôi phục khi trả về pool. Nếu không, request B có thể nhìn thấy request ID của request A trên cùng DB session.

Vòng đời an toàn:

~~~text
checkout physical connection
  reset/initialize session state
  set application/request metadata for this operation
  begin transaction
  execute statements
  commit or rollback
  clear or restore session metadata
return connection to pool
~~~

Nếu driver hoặc pool đã có cơ chế reset session state, cần xác minh chính xác những thuộc tính nào được reset. Không giả định reset transaction tự động xóa mọi session variable, application name hoặc client identifier.

### Request metadata có thể được đặt ở session hay transaction?

Chọn phạm vi ngắn nhất đủ dùng:

- **Transaction-local metadata:** phù hợp khi request/operation chỉ cần được liên kết trong một transaction. Tự hết hiệu lực khi transaction kết thúc nếu DBMS hỗ trợ local scope.
- **Session metadata:** phù hợp khi cần hiển thị application/client identity ở mọi statement của session. Phải reset khi trả connection về pool.
- **Statement tag:** hữu ích khi cần đánh dấu một câu lệnh cụ thể, nhưng không tự cho biết các câu lệnh trước đó trong transaction.

Nếu một request chạy nhiều transaction trên cùng session, metadata session có thể tiếp tục áp dụng qua commit. Nếu các transaction thuộc các request khác nhau, phải cập nhật metadata ở mỗi lần checkout/operation và dọn sạch đúng cách.

## 6. PostgreSQL: application_name, backend PID và transaction ID

PostgreSQL có trường **application_name** hiển thị trong **pg_stat_activity**. Có thể đặt tên ở connection string hoặc thay đổi trong session.

Ví dụ connection string có application name:

~~~text
jdbc:postgresql://db.example/orders?ApplicationName=order-service
~~~

Đặt tên service tĩnh giúp DBA nhận ra service. Để liên kết request cụ thể, có thể dùng **set_config** với transaction-local scope:

~~~sql
BEGIN;

SELECT set_config(
    'application_name',
    'order-service req-7f2a',
    true
);

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 123;

COMMIT;
~~~

Tham số cuối **true** yêu cầu giá trị chỉ có hiệu lực trong transaction hiện tại; sau khi transaction kết thúc, giá trị trước đó được khôi phục. Điều này phù hợp hơn với connection pool vì metadata request không tồn tại qua transaction tiếp theo. Nếu dùng **false**, giá trị có phạm vi session và ứng dụng phải reset rõ ràng.

**application_name** có giới hạn độ dài theo cấu hình PostgreSQL; không nên nhét cả payload hoặc chuỗi trace quá dài. Có thể dùng một phần request ID hoặc một correlation token ngắn, còn trace/span đầy đủ được giữ trong log ứng dụng.

### 6.1. Xem session và câu lệnh đang chạy

~~~sql
SELECT
    pid AS backend_pid,
    application_name,
    usename,
    datname,
    state,
    wait_event_type,
    wait_event,
    xact_start,
    query_start,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE application_name LIKE 'order-service%';
~~~

**pid** là backend process ID của session PostgreSQL. Đây là session identifier ở phía server, không phải transaction ID và có thể được tái sử dụng sau khi backend kết thúc.

### 6.2. Xem transaction ID

Trong PostgreSQL, có thể lấy transaction ID hiện tại bằng các hàm phù hợp với phiên bản, ví dụ **pg_current_xact_id()** trên phiên bản hỗ trợ kiểu XID8. **txid_current()** là API lịch sử trên các phiên bản cũ hơn và có semantics riêng. Không gọi hàm cấp transaction ID chỉ để log nếu việc đó làm transaction nhận XID sớm hơn hoặc gây overhead không cần thiết.

Để điều tra lock wait, **pg_stat_activity** cung cấp **xact_start** và **pg_locks** cung cấp thông tin lock. Transaction ID có thể xuất hiện trong lock wait detail; không nên nhầm nó với backend PID.

### 6.3. Giới hạn khi dùng application_name

**application_name** là metadata phục vụ nhận diện, không phải cơ chế xác thực. Một client có thể đặt giá trị tùy ý. Dùng nó để lọc/điều tra session, không dùng làm bằng chứng bảo mật về danh tính người dùng. Nếu cần phân quyền, hãy dựa trên database role, credential và chính sách quyền.

## 7. MySQL/InnoDB: CONNECTION_ID, connection attributes và Performance Schema

MySQL cung cấp **CONNECTION_ID()** để lấy connection ID của session hiện tại:

~~~sql
SELECT CONNECTION_ID();
~~~

Giá trị này giúp nối log ứng dụng với process list/session tại thời điểm kết nối. Khi dùng pool, một physical connection có thể phục vụ nhiều request theo thời gian, vì vậy connection ID không phải request ID.

### 7.1. Gắn tên service và connection attributes

MySQL clients có thể gửi connection attributes khi thiết lập kết nối. Các thuộc tính có thể được xem trong Performance Schema nếu được bật và lưu. Đây là vị trí phù hợp để gắn service name, client version hoặc instance name ở phạm vi connection.

Connection attributes thường gắn với physical connection, nên không phù hợp để thay đổi request ID cho mỗi lần mượn logical connection nếu driver không hỗ trợ cập nhật động. Với request-level correlation, có thể dùng session variable hoặc query instrumentation nhưng phải reset khi trả connection về pool.

### 7.2. Session variable cho request tag

Một cách minh họa:

~~~sql
SET @app_request_id = 'req-7f2a';

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = 123;

SELECT @app_request_id;
~~~

Ứng dụng có thể dùng user-defined session variable để gắn metadata, nhưng cần chú ý:

- Giá trị tồn tại trong session sau COMMIT/ROLLBACK.
- Physical connection có thể được tái sử dụng bởi request khác.
- Phải xóa hoặc ghi đè biến trong mọi đường cleanup, kể cả exception.
- Không đặt dữ liệu nhạy cảm vào session variable.
- Nếu reset thất bại, cần loại connection khỏi pool theo chính sách.

Ví dụ cleanup:

~~~sql
SET @app_request_id = NULL;
~~~

Không dựa vào việc đóng logical connection để xóa biến; pool có thể chỉ trả session về trạng thái idle.

### 7.3. Xem session và transaction

**performance_schema.threads** có thể nối thread ID với processlist ID; **performance_schema.events_statements_current** hoặc history có thể cung cấp câu lệnh nếu instrumentation được bật. **information_schema.innodb_trx** cung cấp thông tin transaction InnoDB đang tồn tại.

Ví dụ xem transaction:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_mysql_thread_id,
    trx_query,
    trx_wait_started
FROM information_schema.innodb_trx;
~~~

**trx_mysql_thread_id** có thể đối chiếu với connection ID/processlist ID. Transaction ID InnoDB và connection ID là hai định danh khác nhau.

Performance Schema có cấu hình consumer/instrumentation và giới hạn history; nếu không bật trước, một số statement history có thể không có sẵn sau sự cố. Hãy kiểm tra cấu hình theo phiên bản MySQL đang chạy.

## 8. SQL Server: Application Name, SESSION_CONTEXT và session_id

SQL Server có thể hiển thị application name từ connection string trong **sys.dm_exec_sessions.program_name**. Có thể đặt tên service tĩnh:

~~~text
Server=db.example;Database=Orders;Application Name=order-service;
~~~

Để gắn metadata request-level, SQL Server hỗ trợ **sp_set_session_context**:

~~~sql
EXEC sys.sp_set_session_context
    @key = N'request_id',
    @value = N'req-7f2a';
~~~

Đọc lại:

~~~sql
SELECT SESSION_CONTEXT(N'request_id') AS request_id;
~~~

Giá trị SESSION_CONTEXT thuộc session và có thể tồn tại qua COMMIT/ROLLBACK. Vì thế, với connection pool, phải xóa/ghi đè trong cleanup:

~~~sql
EXEC sys.sp_set_session_context
    @key = N'request_id',
    @value = NULL;
~~~

Không dùng tùy chọn read-only cho request ID nếu cùng session cần được cập nhật khi pool tái sử dụng. Một giá trị read-only không thể được thay đổi trong vòng đời session theo cách thông thường.

### 8.1. Xem session và request

~~~sql
SELECT
    s.session_id,
    s.login_name,
    s.host_name,
    s.program_name,
    s.status AS session_status,
    r.status AS request_status,
    r.command,
    r.wait_type,
    r.wait_time,
    r.wait_resource,
    r.blocking_session_id,
    c.connection_id,
    txt.text AS batch_text
FROM sys.dm_exec_sessions AS s
LEFT JOIN sys.dm_exec_requests AS r
    ON r.session_id = s.session_id
LEFT JOIN sys.dm_exec_connections AS c
    ON c.session_id = s.session_id
OUTER APPLY sys.dm_exec_sql_text(r.sql_handle) AS txt
WHERE s.is_user_process = 1;
~~~

**session_id** là SPID phía SQL Server; **connection_id** trong DMV là định danh connection riêng. Một session có thể có request hiện tại hoặc đang idle. Nếu query đã kết thúc, **sys.dm_exec_requests** có thể không còn hàng tương ứng.

### 8.2. Transaction ID

Có thể nối session với transaction đang tham gia bằng **sys.dm_tran_session_transactions**, rồi đối chiếu **transaction_id** với **sys.dm_tran_active_transactions**. Một session có thể có nhiều transaction context tùy cách dùng MARS/transaction; không giả định một session ID luôn ánh xạ một-một với transaction ID.

### 8.3. SESSION_CONTEXT và quyền tin cậy

SESSION_CONTEXT là metadata do client/session đặt. Không dùng giá trị này để quyết định quyền truy cập hoặc tin rằng người gọi thực sự là user được nêu trong request ID. Kẻ có quyền kết nối có thể đặt metadata theo cách riêng. Dùng database principal và authorization để bảo vệ dữ liệu.

## 9. Oracle: CLIENT_IDENTIFIER, MODULE, ACTION và SID

Oracle hỗ trợ gắn thông tin client vào session thông qua package **DBMS_SESSION** và **DBMS_APPLICATION_INFO**.

Ví dụ:

~~~sql
BEGIN
    DBMS_SESSION.SET_IDENTIFIER('req-7f2a');
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'order-service',
        action_name => 'OrderRepository.confirm'
    );
END;
/
~~~

Có thể xóa/khôi phục metadata khi trả connection về pool:

~~~sql
BEGIN
    DBMS_SESSION.CLEAR_IDENTIFIER;
    DBMS_APPLICATION_INFO.SET_MODULE(NULL, NULL);
END;
/
~~~

Các trường thường dùng:

- **CLIENT_IDENTIFIER:** định danh client/request hoặc user context do ứng dụng gắn.
- **MODULE:** tên module/service.
- **ACTION:** thao tác cụ thể.
- **CLIENT_INFO:** trường thông tin bổ sung có giới hạn.

DBA có thể xem trong **V$SESSION** hoặc view tương ứng được cấp quyền:

~~~sql
SELECT
    sid,
    serial#,
    username,
    machine,
    program,
    module,
    action,
    client_identifier,
    status,
    sql_id,
    prev_sql_id
FROM v$session
WHERE module = 'order-service';
~~~

Oracle dùng kết hợp **SID** và **SERIAL#** để nhận diện một session trong nhiều tình huống vì SID có thể được tái sử dụng. **SQL_ID** nhận diện SQL statement trong shared pool, không phải request ID hay transaction ID. Với transaction, có thể xem **V$TRANSACTION** và nối với session theo các trường phù hợp của phiên bản.

Oracle connection pool như UCP có cơ chế session callback để khởi tạo hoặc reset session state khi connection được mượn/trả. Nếu dùng pool khác, cần kiểm tra hook tương đương. Không để CLIENT_IDENTIFIER, MODULE hoặc ACTION của request trước tồn tại trên connection được tái sử dụng.

## 10. Connection pool: nơi dễ tạo correlation sai

Connection pool là một trong những nguyên nhân thường gặp khiến metadata request bị gắn nhầm. Ứng dụng nghĩ rằng đóng connection là kết thúc session, nhưng thực tế pool chỉ trả physical connection về danh sách sẵn sàng.

### 10.1. Metadata rò giữa hai request

~~~text
Request A checkout physical connection C-1
  SET request_id = A
  chạy SQL
  trả C-1 về pool nhưng quên reset

Request B checkout physical connection C-1
  chạy SQL
  DB session vẫn hiển thị request_id = A
~~~

Khi DBA xem blocker, họ có thể kết luận nhầm request A đang chạy dù request B mới là người dùng session.

### 10.2. Reset trong finally

Mẫu quản lý ở tầng ứng dụng:

~~~java
Connection connection = dataSource.getConnection();
try {
    setRequestMetadata(connection, requestId);
    performDatabaseWork(connection);
} finally {
    try {
        clearRequestMetadata(connection);
    } catch (SQLException cleanupError) {
        // Ghi log an toàn và loại connection khỏi pool nếu không thể reset.
        markConnectionAsUnusable(connection, cleanupError);
    } finally {
        connection.close(); // Với pool, thường là trả logical connection về pool.
    }
}
~~~

Đây là mã giả: API loại connection khỏi pool phụ thuộc thư viện pool/driver. Nếu transaction còn mở, phải rollback hoặc kết thúc đúng cách trước khi trả connection. Không gọi clear metadata trong khi một transaction khác vẫn đang sử dụng cùng session.

Nếu framework quản lý connection tự động, nên tích hợp metadata qua interceptor, connection customization, datasource proxy hoặc transaction callback thay vì tự lấy connection ngoài transaction manager.

### 10.3. Đừng gắn request ID vào physical connection lúc tạo pool rồi giữ nguyên

Thông tin service/instance có thể là thuộc tính tĩnh của physical connection. Request ID là thuộc tính động của lần sử dụng connection. Phân biệt hai loại:

| Thuộc tính | Ví dụ | Vòng đời |
|---|---|---|
| Service identity | order-service | Có thể tồn tại suốt physical connection |
| Instance identity | order-service-pod-3 | Có thể tồn tại suốt physical connection |
| Request ID | req-7f2a | Chỉ trong lần xử lý request/transaction phù hợp |
| Trace/span ID | trace-abc, span-123 | Thay đổi theo thao tác/trace |
| Transaction ID | DBMS cấp | Do DBMS quản lý cho mỗi transaction |

## 11. Java/JDBC và ORM: lấy thông tin ở đúng tầng

Trong Java, một request thường đi qua controller, service, repository, ORM và JDBC driver. Các tầng này có định danh riêng:

- HTTP filter/interceptor biết request ID và trace context.
- Service biết operation nghiệp vụ và transaction boundary.
- Hibernate/JPA biết persistence context/EntityManager.
- JDBC connection đại diện cho logical connection được ứng dụng mượn.
- Pool quản lý physical connection.
- DBMS biết session ID và transaction ID.

Không nên giả định EntityManager ID, Hibernate Session ID, JDBC connection object identity và DB backend PID là cùng một thứ.

### 11.1. Log ở ranh giới transaction

Một transaction interceptor có thể ghi:

~~~text
transaction.begin
  request_id=R-100
  trace_id=T-abc
  datasource=orders-primary
  isolation=READ_COMMITTED

transaction.commit
  request_id=R-100
  trace_id=T-abc
  duration_ms=42
  db_session_id=51
~~~

Nếu transaction rollback, log cần có exception class, SQLSTATE/vendor code và transaction outcome. Không chỉ log transaction.end, vì commit và rollback có ý nghĩa khác nhau.

### 11.2. Spring transaction và connection binding

Spring JDBC/JPA transaction manager thường gắn connection với transaction hiện tại. Các repository trong cùng transaction có thể dùng cùng connection thông qua transaction-aware access. Nếu code tự gọi **dataSource.getConnection()** thay vì dùng cơ chế tích hợp của Spring, nó có thể lấy connection khác và chạy ngoài transaction mong muốn.

Khi gắn metadata session, hãy bảo đảm câu lệnh set metadata chạy trên đúng connection mà transaction sẽ dùng. Có thể dùng JDBC callback/transaction synchronization hoặc cơ chế connection customization phù hợp. Nếu đặt application_name/session variable trên một connection khác, log ở DB session thực thi câu SQL sẽ không mang request ID.

Với propagation **REQUIRES_NEW**, framework có thể tạm suspend transaction hiện tại và dùng connection/transaction mới. Một request do đó có thể có hai transaction ID và có thể dùng hai session khác nhau. Log cần phân biệt outer và inner transaction thay vì gộp chúng thành một.

### 11.3. Hibernate/JPA

Một EntityManager/persistence context thường gắn với một đơn vị làm việc, nhưng việc lấy connection có thể lazy và provider có thể release/reacquire connection tùy connection handling mode. Nếu metadata được đặt ở session scope, hãy xác minh nó còn đúng khi provider đổi physical connection hoặc bắt đầu transaction khác.

Nếu dùng Hibernate interceptor, StatementInspector hoặc datasource proxy để gắn trace metadata vào SQL, cần tránh ghi request ID vào mọi SQL comment nếu điều đó làm query text thay đổi liên tục và gây nhiễu query statistics. Ưu tiên session metadata hoặc tracing span attributes; dùng statement comment chỉ khi DBMS/driver và công cụ quan sát cần cách đó.

### 11.4. JDBC wrapper/proxy

Một datasource proxy có thể ghi thời gian acquire connection, connection label, statement fingerprint và rows affected. Nó cũng có thể đọc DB session ID sau khi checkout. Cần đảm bảo thao tác lấy session ID không làm thay đổi transaction semantics hoặc tạo thêm round trip đáng kể trên mọi query.

Nếu connection proxy che giấu connection vật lý, không ép kiểu sang implementation cụ thể trừ khi thư viện cam kết API đó. Dùng wrapper/provider interface được hỗ trợ để tránh phụ thuộc driver nội bộ.

## 12. Async, nhiều datasource và request fan-out

Một request có thể:

- Gọi hai datasource khác nhau.
- Chạy hai transaction độc lập.
- Gửi một phần công việc sang executor.
- Enqueue job để worker xử lý sau khi HTTP response đã trả về.
- Gọi service ngoài rồi tiếp tục cập nhật database.

Do đó, mô hình quan sát nên ghi một span cho mỗi thao tác DB hoặc transaction. Trace ID chung nối các span; session ID và transaction ID mô tả tài nguyên DB thực tế ở từng span.

Ví dụ:

~~~text
Trace T-abc
  Request span R-100
    DB span S-1
      datasource=orders
      session=51
      transaction=X-900
    DB span S-2
      datasource=inventory
      session=72
      transaction=X-901
    HTTP span -> payment-service
~~~

Nếu hai DB span chạy song song, timestamp có thể chồng lấn. Không suy ra thứ tự nhân quả chỉ từ thời gian bắt đầu; dùng span parent/child, event timestamp và correlation metadata.

Với background job, lưu correlation ID và trace context trong message. Worker tạo span mới khi nhận job; không giả định trace request HTTP vẫn đang hoạt động hoặc context trong thread cũ còn tồn tại.

## 13. Liên kết với log lock wait và deadlock

Khi DBMS báo một session đang chờ khóa, quy trình điều tra nên là:

1. Lấy DB session ID/process ID từ deadlock graph hoặc lock-wait view.
2. Tìm application name, module, client identifier hoặc session context của session đó.
3. Lấy statement hiện tại và statement trước đó trong transaction nếu có.
4. Tìm log ứng dụng có cùng request/correlation ID.
5. Nối trace/span để biết request đến từ service nào, endpoint nào và thao tác nghiệp vụ nào.
6. Dùng transaction ID để gom các statement thuộc cùng transaction.
7. So sánh waiter và blocker; blocker có thể là session idle in transaction nên không có statement đang chạy tại thời điểm truy vấn.

Điểm cuối rất quan trọng: blocker có thể đang ở trạng thái idle nhưng vẫn giữ transaction và khóa. Khi đó, current query có thể rỗng hoặc là câu lệnh trước đó; cần xem xact_start, transaction age, last statement và log transaction boundary.

### Ví dụ điều tra

DBA thấy PostgreSQL backend PID 51 chờ một khóa. **pg_stat_activity.application_name** hiển thị **order-service req-7f2a**. Từ log ứng dụng tìm được:

~~~text
request_id=req-7f2a
trace_id=4bf92f...
operation=OrderRepository.confirm
transaction_attempt=1
~~~

Trace cho thấy span database mất 4.2 giây và gọi repository confirm. Log transaction ghi transaction bắt đầu trước đó 4 giây. Từ đây có thể nối deadlock/lock wait với request và thao tác nghiệp vụ cụ thể, rồi xem blocker tương ứng.

## 14. Query tagging: khi nào dùng comment trong SQL?

Một số hệ thống thêm comment vào SQL:

~~~sql
/* trace_id=4bf92f request_id=req-7f2a */
SELECT *
FROM orders
WHERE order_id = 123;
~~~

Ưu điểm:

- Metadata nằm ngay trong query text mà DBA hoặc query log nhìn thấy.
- Có thể hữu ích khi driver không hỗ trợ session metadata hoặc câu lệnh chạy qua nhiều lớp trung gian.

Đánh đổi:

- Mỗi request tạo query text khác nhau nếu comment chứa ID duy nhất.
- Query fingerprint, plan cache hoặc công cụ thống kê có thể nhóm câu lệnh khác đi tùy DBMS/công cụ.
- Comment có thể bị loại bỏ, chuẩn hóa hoặc không xuất hiện trong log.
- Comment không tự gắn metadata vào transaction nếu câu lệnh không được thực thi.
- Không đưa token, dữ liệu cá nhân hoặc secret vào comment.

Nếu dùng query tag, ưu tiên một operation name hoặc trace/span ID theo chính sách công cụ quan sát. Đo ảnh hưởng đến query normalization và plan cache trước khi áp dụng rộng. Với request-level metadata, session context thường dễ truy vấn hơn khi pool được quản lý đúng.

## 15. Đo thời gian ở các giai đoạn khác nhau

Một request chậm không nhất thiết do SQL chạy lâu. Cần tách:

| Khoảng thời gian | Ý nghĩa | Nguồn đo |
|---|---|---|
| Pool acquire time | Chờ mượn connection từ pool | Connection pool metrics/log |
| Session initialization time | Đặt/reset application metadata | Datasource instrumentation |
| Transaction duration | Từ begin đến commit/rollback | Transaction interceptor/DB log |
| Lock wait duration | Chờ khóa hoặc tài nguyên DB | DBMS wait event/lock diagnostics |
| SQL execution duration | Thời gian thực thi statement | JDBC/ORM instrumentation và DB statement stats |
| Network/round-trip time | Gửi câu lệnh và nhận kết quả | Driver tracing/APM |
| Result mapping time | Chuyển result set thành object | ORM/application span |

Nếu chỉ đo thời gian repository method, không thể biết request chậm do pool hết connection, chờ khóa, SQL chậm hay mapping object lớn. Các span lồng nhau giúp chia nhỏ thời gian và xác định phần cần tối ưu.

## 16. Bảo mật và quyền truy cập khi gắn metadata

Correlation metadata giúp điều tra nhưng không phải nguồn xác thực.

- Không dùng request ID, CLIENT_IDENTIFIER, application_name hoặc SESSION_CONTEXT để cấp quyền truy cập dữ liệu.
- Không đặt access token, session cookie, password, số thẻ hoặc payload nhạy cảm vào metadata DB.
- Giới hạn độ dài và ký tự cho giá trị do client cung cấp.
- Dùng ID ngẫu nhiên hoặc token nội bộ không chứa thông tin cá nhân.
- Hạn chế quyền xem log và DMV vì statement text có thể chứa dữ liệu nhạy cảm.
- Áp dụng retention và redaction cho trace/log theo chính sách dữ liệu.
- Không log bind parameter đầy đủ theo mặc định; chỉ bật khi có lý do và biện pháp bảo vệ.

Nếu cần liên kết người dùng, dùng user ID nội bộ đã được phép ghi log hoặc mã đã pseudonymize. Đừng đưa email, số điện thoại hoặc định danh nhạy cảm vào application_name chỉ vì nó dễ xem trong DB console.

## 17. Checklist triển khai theo từng lớp

| Lớp | Việc cần cấu hình | Kết quả mong muốn |
|---|---|---|
| Gateway/API | Tạo request ID và tiếp nhận trace context | Mọi request có định danh ổn định |
| Application logging | Đưa request/trace/span vào structured log | Log các tầng có thể được nối |
| Async/message | Propagate context và correlation metadata | Worker tiếp tục được liên kết với request/workflow gốc |
| Service/transaction | Log transaction begin/commit/rollback và attempt | Biết ranh giới transaction |
| Connection pool | Ghi datasource/connection label; reset session state | Không gắn nhầm request giữa các lần tái sử dụng |
| DB session | Đặt application_name/client identifier/session context | DBA có thể nhận diện service/request |
| DB diagnostics | Thu session ID, transaction ID, statement và wait resource | Nối được session với transaction và SQL |
| APM/tracing | Tạo span cho DB call, ghi pool wait và SQL duration | Phân biệt pool, lock, query và network latency |
| Security | Redact metadata và giới hạn quyền log/DMV | Không biến observability thành rò rỉ dữ liệu |

## 18. Những lỗi thường gặp khi liên kết ID

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi request ID bằng DB session ID | Gắn nhầm nhiều request vào cùng session | Ghi riêng từng loại ID và nguồn tạo |
| Coi một request chỉ dùng một transaction | Bỏ sót REQUIRES_NEW, nhiều datasource hoặc async | Ghi mỗi transaction/DB span riêng |
| Đặt request metadata một lần khi tạo pool | Request sau có thể mang metadata cũ | Đặt/reset ở mỗi lần checkout hoặc transaction |
| Quên reset session variable | Log DBA hiển thị request đã kết thúc | Cleanup trong finally và loại connection lỗi khỏi pool |
| Set metadata trên connection khác | SQL thực tế không mang correlation ID | Dùng đúng connection do transaction manager quản lý |
| Chỉ truyền MDC qua ThreadLocal | Async worker mất hoặc dùng nhầm context | Propagate context và clear sau task |
| Dùng session metadata làm căn cứ authorization | Client có thể giả mạo metadata | Dùng DB principal/credential và policy quyền |
| Log toàn bộ SQL parameters | Có thể lộ dữ liệu nhạy cảm | Dùng fingerprint, redaction và allowlist |
| Chỉ log session ID | Không biết request nào gây thao tác | Kết hợp request/trace ID, transaction ID và statement |
| Không lưu transaction boundary | Không phân biệt nhiều transaction cùng session | Log begin, commit, rollback và transaction outcome |

## 19. Quy trình điều tra từ request đến DB transaction

Khi một request gặp lỗi hoặc chậm, thực hiện theo trình tự:

1. Tìm request ID và trace ID từ log gateway hoặc API.
2. Mở trace để xác định service, operation và DB span bị lỗi/chậm.
3. Tìm log transaction tương ứng: begin, commit/rollback, attempt và datasource.
4. Lấy DB session ID/connection ID từ span hoặc session metadata.
5. Truy vấn DBMS để xem session state, statement, transaction age, wait event và blocker.
6. Dùng transaction ID để gom các statement thuộc cùng đơn vị commit.
7. Nếu có blocker, tìm application metadata và request/trace tương ứng của blocker.
8. So sánh timestamp, nhưng dùng correlation/span relation để xác định quan hệ nhân quả.
9. Phân loại lỗi: pool wait, lock wait, deadlock, SQL execution, network hoặc application processing.
10. Ghi lại kết luận cùng bằng chứng và điều chỉnh instrumentation nếu thiếu mắt xích.

Một báo cáo điều tra nên có:

~~~text
request_id:
trace_id:
service / operation:
datasource:
logical connection label:
DB session ID:
DB transaction ID:
statement fingerprint:
transaction start / end:
pool acquire duration:
SQL duration:
lock wait / blocker:
commit or rollback:
error code:
conclusion:
~~~

## 20. Nguyên tắc kết luận

Muốn liên kết mã yêu cầu ứng dụng với connection và transaction database, cần ghi nhận định danh ở từng ranh giới và hiểu vòng đời của chúng. Request ID/trace ID mô tả hành trình ứng dụng; connection ID và session ID mô tả kết nối phía client/server; transaction ID mô tả đơn vị commit/rollback; statement ID hoặc fingerprint mô tả câu SQL.

Connection pool làm cho session có thể được tái sử dụng, vì vậy metadata request phải được đặt đúng connection và reset trước khi trả về pool. Async và message processing cần propagate context rõ ràng. DBMS-specific application metadata giúp DBA nối session với service/request, còn log transaction và tracing giúp nối ngược về operation nghiệp vụ.

Khi giữ riêng các loại ID, truyền context đúng cách và đo riêng thời gian pool/transaction/lock/SQL, nhóm phát triển có thể đi từ một request lỗi đến đúng session, transaction và câu lệnh gây ra vấn đề mà không nhầm lẫn giữa các ranh giới.

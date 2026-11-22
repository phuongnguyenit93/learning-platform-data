# Thiết lập thời gian chờ khóa, thời gian chờ truy vấn và hủy thao tác

Trong hệ thống cơ sở dữ liệu có nhiều giao dịch chạy đồng thời, một truy vấn có thể phải chờ khóa do giao dịch khác đang giữ. Một truy vấn khác có thể chạy quá lâu vì đọc quá nhiều dữ liệu, thực hiện phép nối tốn kém hoặc chờ I/O. Ứng dụng cũng có thể cần dừng thao tác khi người dùng hủy yêu cầu hoặc khi ngân sách thời gian của API đã hết.

Thời gian chờ khóa (lock timeout), thời gian giới hạn thực thi câu lệnh (statement/query timeout) và thao tác hủy (cancel) giải quyết các vấn đề liên quan nhưng khác nhau. Lock timeout giới hạn thời gian chờ lấy khóa. Statement timeout giới hạn thời gian một câu lệnh được phép chạy. Cancel yêu cầu hệ quản trị dừng câu lệnh hoặc phiên làm việc đang thực hiện. Thiết lập sai có thể làm giao dịch giữ khóa quá lâu, tạo lỗi dây chuyền hoặc khiến ứng dụng tưởng truy vấn đã dừng trong khi database vẫn đang xử lý.

Trong phạm vi DATABASE_PERFORMANCE, cần đặt các giới hạn theo ngân sách thời gian của ứng dụng, hiểu phạm vi cấu hình trên từng hệ quản trị, xử lý transaction sau khi bị hủy và đo nguyên nhân chờ bằng công cụ chẩn đoán. Không có một con số timeout phù hợp cho mọi workload; giá trị phải dựa trên SLO, thời gian xử lý bình thường, mức đồng thời và khả năng phục hồi của ứng dụng.

## 1. Phân biệt các loại thời gian chờ

### 1.1. Lock timeout

Lock timeout giới hạn thời gian một thao tác phải chờ để lấy khóa đang được giao dịch khác giữ. Khi vượt ngưỡng, engine trả lỗi hoặc hủy statement theo quy tắc của nó.

Ví dụ: giao dịch A cập nhật một hàng orders và chưa commit. Giao dịch B muốn cập nhật cùng hàng đó. Nếu B chỉ được phép chờ khóa tối đa 500 mili giây, sau thời gian đó B nhận lỗi lock timeout thay vì chờ vô hạn.

Lock timeout hữu ích khi:

- Một giao dịch giữ khóa lâu bất thường.
- API cần phản hồi trong thời gian hữu hạn.
- Hàng nóng có nhiều giao dịch cạnh tranh.
- Batch hoặc worker không nên chiếm connection quá lâu khi bị chặn.

Lock timeout không giới hạn thời gian CPU, I/O hoặc thời gian thực hiện phép nối sau khi đã lấy được khóa. Một truy vấn có thể không chờ khóa nhưng vẫn chạy nhiều phút.

### 1.2. Statement timeout hoặc query timeout

Statement timeout giới hạn tổng thời gian thực thi một câu lệnh theo cơ chế của hệ quản trị. Tùy engine, thời gian này có thể bao gồm thời gian chờ khóa, đọc dữ liệu, tính toán, sắp xếp và trả kết quả.

Query timeout ở driver hoặc thư viện ứng dụng thường là giới hạn mà client chờ kết quả. Khi hết hạn, driver có thể gửi yêu cầu cancel đến server, hủy request hiện tại hoặc đóng connection tùy giao thức và cách triển khai.

Hai giới hạn này không đồng nhất:

- Server-side statement timeout được database thực thi theo cấu hình của engine.
- Client-side command timeout được driver hoặc ứng dụng theo dõi.
- Nếu client hết hạn nhưng server không nhận được tín hiệu hủy, câu lệnh có thể tiếp tục chạy.
- Nếu server hủy câu lệnh trước, ứng dụng cần nhận và xử lý lỗi tương ứng.

### 1.3. Transaction timeout và idle timeout

Không nên nhầm thời gian giới hạn câu lệnh với thời gian tồn tại của transaction hoặc session:

- Transaction có thể gồm nhiều statement; giới hạn từng statement không nhất thiết giới hạn tổng thời gian transaction.
- Idle-in-transaction timeout thường đóng session hoặc hủy transaction khi client mở transaction nhưng không gửi lệnh trong một khoảng thời gian.
- Connection idle timeout thường đóng kết nối không hoạt động; nó không nhất thiết dừng một câu lệnh đang chạy.
- Connection pool acquisition timeout giới hạn thời gian ứng dụng chờ mượn connection, không phải thời gian database thực thi SQL.

Một API có thể hết thời gian chờ khi đang đợi connection trong pool, trước khi SQL được gửi đến database. Khi chẩn đoán, cần xác định chính xác timeout xảy ra ở tầng pool, driver, server, lock hay transaction.

### 1.4. Cancel khác với timeout

Cancel là hành động yêu cầu dừng một câu lệnh hoặc phiên đang chạy. Nó có thể được kích hoạt bởi:

- Người dùng bấm nút hủy.
- Request HTTP bị hủy hoặc hết deadline.
- Driver phát hiện command timeout.
- DBA chủ động hủy một truy vấn gây tải lớn.
- Một worker dừng công việc do hết lease hoặc bị điều phối lại.

Cancel không bảo đảm mọi thay đổi đã ghi được hoàn tác theo cùng một cách trên mọi engine. Cần xác định statement đã thực hiện đến đâu, transaction còn mở hay không và có phải rollback toàn bộ transaction không.

## 2. Thiết kế ngân sách thời gian từ ứng dụng đến database

Timeout nên được thiết kế từ deadline của request hoặc job, sau đó phân bổ cho từng tầng. Không đặt một giá trị lớn tùy ý ở database rồi để API chờ lâu hơn SLO.

Ví dụ một API có ngân sách phản hồi 2 giây:

| Thành phần | Ngân sách minh họa |
|---|---:|
| Chờ connection pool | 200 ms |
| Thực thi statement, bao gồm cả thời gian chờ khóa | 1.200 ms |
| Giới hạn chờ khóa nằm bên trong ngân sách statement | Tối đa 300 ms |
| Xử lý ứng dụng và truyền kết quả | 300 ms |
| Phần dự phòng còn lại | 300 ms |

Các giá trị chỉ là ví dụ để minh họa cách chia ngân sách. Bốn phần cộng thành 2 giây là thời gian chờ pool, statement, xử lý ứng dụng và dự phòng. Giới hạn chờ khóa 300 ms là một phần của 1.200 ms dành cho statement, không phải một khoảng thời gian cộng thêm.

Một thứ tự cấu hình thường hữu ích:

1. Lock timeout ngắn hơn statement timeout để phát hiện tranh chấp sớm.
2. Server-side statement timeout đủ ngắn để database tự dừng câu lệnh trước deadline cuối của request.
3. Client command timeout dài hơn một chút so với server timeout để ứng dụng có cơ hội nhận lỗi server và dọn dẹp transaction.
4. Request deadline bao trùm pool wait, SQL, xử lý ứng dụng và truyền kết quả.

Nếu client timeout ngắn hơn server timeout, connection có thể bị bỏ trong khi server vẫn chạy. Nếu server timeout dài hơn request deadline quá nhiều, tài nguyên database có thể tiếp tục bị giữ sau khi người dùng đã rời đi.

### 2.1. Chọn giá trị theo loại workload

| Workload | Cách đặt giới hạn cần cân nhắc |
|---|---|
| API tương tác | Lock wait ngắn, statement timeout theo SLO, cancel khi request bị hủy |
| Báo cáo lớn | Timeout dài hơn nhưng có quota, giới hạn đồng thời và ưu tiên tài nguyên |
| Batch job | Deadline theo batch, transaction có kích thước hữu hạn và khả năng tiếp tục |
| Worker xử lý hàng đợi | Lock wait phù hợp lease, transaction ngắn và cơ chế claim/retry |
| Migration/DDL | Có thời gian chờ khóa DDL riêng và quy trình hủy an toàn |
| Tác vụ quản trị | Timeout có kiểm soát, theo dõi tiến độ và rollback khi dừng |

Không dùng timeout rất ngắn cho mọi truy vấn. Một báo cáo hợp lệ cần vài phút có thể bị hủy liên tục nếu áp chính sách của API tương tác. Nên phân loại workload bằng role, connection pool, job class hoặc cấu hình theo statement.

## 3. PostgreSQL: lock_timeout và statement_timeout

PostgreSQL cung cấp các tham số riêng:

- lock_timeout: giới hạn thời gian chờ mỗi lần lấy khóa.
- statement_timeout: giới hạn thời gian chạy statement.
- idle_in_transaction_session_timeout: đóng session có transaction đang mở nhưng không hoạt động trong khoảng thời gian cấu hình.

Ví dụ đặt giới hạn cục bộ cho một transaction:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '300ms';
SET LOCAL statement_timeout = '1500ms';

UPDATE orders
SET status = 'PROCESSING'
WHERE id = 125;

COMMIT;
~~~

SET LOCAL chỉ có hiệu lực trong transaction hiện tại và được khôi phục sau COMMIT hoặc ROLLBACK. Cách này phù hợp khi connection được tái sử dụng trong pool vì giảm nguy cơ để lại session setting cho request tiếp theo.

### 3.1. Quan hệ giữa hai timeout

statement_timeout tính thời gian của statement; lock_timeout chỉ áp dụng trong lúc statement chờ khóa. Nếu lock_timeout lớn hơn hoặc bằng statement_timeout, statement_timeout thường sẽ kết thúc thao tác trước khi lock_timeout có tác dụng.

Ví dụ:

- lock_timeout = 300 ms.
- statement_timeout = 1.500 ms.

Nếu statement chờ một khóa quá 300 ms, PostgreSQL báo lỗi lock timeout. Nếu statement không bị chặn nhưng chạy quá 1.500 ms, statement timeout hủy câu lệnh.

### 3.2. Hủy truy vấn và kết thúc session

PostgreSQL hỗ trợ hai hành động quản trị khác nhau:

- pg_cancel_backend(pid) gửi yêu cầu hủy câu lệnh đang chạy của backend.
- pg_terminate_backend(pid) kết thúc session backend.

Cancel thường giữ session để client có thể tiếp tục sau khi xử lý trạng thái transaction. Nếu statement bị hủy bên trong explicit transaction, transaction thường chuyển sang trạng thái lỗi và không thể tiếp tục câu lệnh bình thường cho đến khi ROLLBACK hoặc rollback về savepoint phù hợp.

Terminate session mạnh hơn: connection bị đóng và transaction chưa commit sẽ được rollback khi backend kết thúc. Cần quyền thích hợp và phải xác định đúng PID; không dùng terminate chỉ vì một truy vấn chậm nếu cancel là đủ.

### 3.3. Lỗi thường gặp

- Lock timeout thường có SQLSTATE 55P03.
- Statement timeout thường được báo dưới SQLSTATE 57014 với thông điệp query canceled.
- idle_in_transaction_session_timeout xử lý session bỏ transaction ở trạng thái idle, không phải giới hạn thời gian chạy của một statement.

Khi ứng dụng nhận lỗi hủy statement trong transaction, cần rollback transaction trước khi trả connection về pool. Không trả một connection còn transaction lỗi về pool như thể nó đang sạch.

### 3.4. Quan sát lock wait

Có thể xem các session đang hoạt động và loại wait:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query_start,
    now() - query_start AS query_age,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE state <> 'idle';
~~~

pg_locks cung cấp thông tin khóa ở mức thấp hơn. Kết hợp PID bị block với PID blocker, thời gian transaction và câu SQL đang chạy để tìm nguyên nhân. Cần hạn chế quyền xem query text vì câu lệnh có thể chứa dữ liệu nhạy cảm.

## 4. SQL Server: SET LOCK_TIMEOUT và command timeout

SQL Server có lệnh:

~~~sql
SET LOCK_TIMEOUT 300;
~~~

Giá trị tính bằng mili giây:

- -1: chờ vô hạn, là mặc định thông thường.
- 0: không chờ; nếu khóa không lấy được ngay thì trả lỗi.
- Số dương: thời gian chờ tối đa tính bằng mili giây.

Ví dụ:

~~~sql
SET LOCK_TIMEOUT 300;

BEGIN TRANSACTION;

UPDATE dbo.Orders
SET status = 'PROCESSING'
WHERE id = 125;

COMMIT TRANSACTION;

SET LOCK_TIMEOUT -1;
~~~

SET LOCK_TIMEOUT có phạm vi session và giá trị vẫn tồn tại sau COMMIT. Nếu dùng connection pool, phải khôi phục giá trị trước khi trả connection về pool hoặc dùng cơ chế reset session đã được xác minh.

### 4.1. Xử lý lỗi lock timeout

SQL Server thường trả lỗi 1222 khi hết thời gian chờ khóa. Statement bị hủy, nhưng không nên giả định transaction bao quanh đã tự động rollback hoàn toàn. Ứng dụng hoặc stored procedure cần kiểm tra trạng thái transaction và quyết định rollback.

Mẫu xử lý:

~~~sql
SET LOCK_TIMEOUT 300;

BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE dbo.Orders
    SET status = 'PROCESSING'
    WHERE id = 125;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    SET LOCK_TIMEOUT -1;
    THROW;
END CATCH;
~~~

Đây là mẫu minh họa; cần tích hợp với transaction ownership của ứng dụng. Nếu transaction được mở ở tầng gọi bên ngoài, không tự rollback một transaction mà procedure không sở hữu nếu hợp đồng ứng dụng yêu cầu caller quản lý.

### 4.2. Query timeout nằm ở client

SQL Server không có một câu lệnh T-SQL tổng quát tương đương statement_timeout của PostgreSQL cho mọi request đến server. Query timeout thường được cấu hình trong driver hoặc framework, ví dụ CommandTimeout của ADO.NET hoặc setQueryTimeout của JDBC.

Khi command timeout xảy ra, driver thường gửi attention để yêu cầu SQL Server dừng request. Cần xác minh hành vi theo driver, phiên bản và trạng thái mạng. Transaction explicit có thể vẫn cần được rollback bởi ứng dụng.

Không nhầm cấu hình remote query timeout của SQL Server với timeout cho câu SQL client gửi vào instance. Tham số remote query timeout chủ yếu áp dụng cho thao tác truy vấn từ SQL Server đến remote server.

### 4.3. Cancel request và KILL session

- Cancel từ client/driver thường yêu cầu hủy request đang chạy.
- KILL session_id kết thúc session và SQL Server phải rollback transaction còn mở.
- Rollback có thể mất thời gian; dùng KILL session_id WITH STATUSONLY để xem tiến độ rollback khi phù hợp.

KILL session có tác động rộng hơn cancel một statement. Cần kiểm tra session ID, login, host, transaction và blocker trước khi dùng.

### 4.4. Chẩn đoán blocking

Có thể bắt đầu từ:

- sys.dm_exec_requests: request đang chạy, blocking_session_id, wait_type, wait_time.
- sys.dm_tran_locks: khóa đang được cấp hoặc yêu cầu.
- sys.dm_exec_sessions: thông tin session.
- Actual execution plan và Extended Events để xem câu lệnh và sự kiện timeout/deadlock.

Các wait type có tiền tố LCK_M_ thường liên quan đến lock wait. Cần tìm cả transaction giữ khóa lâu, không chỉ session đang bị block.

## 5. MySQL InnoDB: row lock, metadata lock và query timeout

MySQL có nhiều tham số khác nhau cho các loại chờ:

- innodb_lock_wait_timeout: giới hạn chờ khóa hàng của InnoDB, tính bằng giây.
- lock_wait_timeout: giới hạn chờ metadata lock, cũng tính bằng giây.
- max_execution_time: giới hạn thời gian thực thi SELECT, tính bằng mili giây trong các phiên bản hỗ trợ.

Hai loại lock wait không thay thế nhau. Một câu ALTER TABLE có thể chờ metadata lock dù không bị chặn bởi innodb_lock_wait_timeout.

### 5.1. Đặt timeout cho InnoDB row lock

~~~sql
SET SESSION innodb_lock_wait_timeout = 2;

START TRANSACTION;

UPDATE orders
SET status = 'PROCESSING'
WHERE id = 125;

COMMIT;
~~~

Giá trị trên là ví dụ hai giây. innodb_lock_wait_timeout có thể cấu hình ở session hoặc global theo quyền và phiên bản. Khi dùng connection pool, cần reset session variable sau request hoặc khởi tạo connection theo một profile nhất quán.

### 5.2. Metadata lock timeout

Metadata lock bảo vệ cấu trúc và metadata của bảng khi DDL hoặc statement khác cần truy cập. Có thể đặt giới hạn riêng:

~~~sql
SET SESSION lock_wait_timeout = 5;
~~~

Ví dụ này giới hạn chờ metadata lock trong năm giây. Nó không thay cho timeout chờ row lock của InnoDB. Khi DDL bị chờ, hãy xác định transaction nào đang giữ metadata lock; một transaction đọc hoặc ghi chưa commit cũng có thể làm DDL chờ.

### 5.3. Giới hạn thời gian SELECT

MySQL hỗ trợ giới hạn thời gian SELECT bằng system variable hoặc optimizer hint trong các phiên bản phù hợp:

~~~sql
SELECT /*+ MAX_EXECUTION_TIME(1200) */
    id, customer_id, total_amount
FROM orders
WHERE status = 'OPEN';
~~~

Giá trị 1200 được tính bằng mili giây. Có thể cấu hình max_execution_time ở phạm vi session/global. Cần kiểm tra phiên bản và loại câu lệnh; cơ chế này không phải giới hạn tổng quát cho mọi INSERT, UPDATE, DELETE hoặc toàn bộ transaction.

### 5.4. Hủy truy vấn

MySQL phân biệt:

- KILL QUERY connection_id: hủy câu lệnh hiện tại nhưng giữ connection.
- KILL CONNECTION connection_id: kết thúc connection; transaction chưa commit sẽ được rollback khi session kết thúc.

Ứng dụng cũng có thể gửi cancel qua driver. Hãy xác nhận driver thực sự gửi lệnh hủy và connection sau cancel còn ở trạng thái sử dụng được.

### 5.5. Transaction sau lock wait timeout

Mặc định, InnoDB thường rollback statement bị lock wait timeout, không nhất thiết rollback toàn bộ transaction. Tham số innodb_rollback_on_timeout có thể thay đổi hành vi để rollback toàn transaction. Deadlock được InnoDB xử lý khác: một transaction được chọn làm victim và rollback.

Đối với một nghiệp vụ gồm nhiều statement, ứng dụng thường nên rollback toàn transaction khi một statement bị timeout để tránh commit một phần công việc ngoài ý muốn. Không tiếp tục transaction chỉ vì engine mặc định mới rollback statement.

### 5.6. Chẩn đoán lock wait

Có thể dùng Performance Schema:

- performance_schema.data_locks
- performance_schema.data_lock_waits
- performance_schema.metadata_locks
- performance_schema.threads

Các view trong sys schema như sys.innodb_lock_waits có thể giúp đọc quan hệ blocker/waiter dễ hơn tùy phiên bản. Kết hợp với SHOW PROCESSLIST, transaction age và statement hiện tại để xác định session giữ khóa.

## 6. Oracle Database: WAIT, NOWAIT và DML_LOCK_TIMEOUT

Oracle hỗ trợ điều khiển thời gian chờ khóa ở nhiều cấp:

- SELECT ... FOR UPDATE WAIT n: chờ tối đa n giây để lấy khóa hàng.
- SELECT ... FOR UPDATE NOWAIT: trả lỗi ngay nếu không lấy được khóa.
- SELECT ... FOR UPDATE SKIP LOCKED: bỏ qua các hàng đang bị khóa; thường hữu ích cho worker lấy việc, nhưng có thể làm tập kết quả không đầy đủ tại thời điểm đọc.
- DML_LOCK_TIMEOUT: giới hạn thời gian chờ khóa của DML theo cấu hình session/system.
- DDL_LOCK_TIMEOUT: giới hạn thời gian DDL chờ khóa cần thiết để thay đổi cấu trúc.

Ví dụ:

~~~sql
SELECT id, status
FROM orders
WHERE status = 'READY'
FOR UPDATE WAIT 3;
~~~

Statement chờ tối đa ba giây để khóa các hàng phù hợp. Với NOWAIT, thao tác trả lỗi nếu khóa chưa sẵn sàng. SKIP LOCKED có ngữ nghĩa khác WAIT: nó tiếp tục với các hàng không bị khóa, vì vậy chỉ dùng khi nghiệp vụ chấp nhận bỏ qua hàng đang được worker khác xử lý.

### 6.1. DML_LOCK_TIMEOUT và DDL_LOCK_TIMEOUT

Ví dụ cấu hình trong session:

~~~sql
ALTER SESSION SET DML_LOCK_TIMEOUT = 3;
ALTER SESSION SET DDL_LOCK_TIMEOUT = 5;
~~~

Các giá trị được tính bằng giây. DML_LOCK_TIMEOUT điều khiển thời gian chờ khóa liên quan đến DML theo quy tắc Oracle; SELECT FOR UPDATE có thể dùng WAIT/NOWAIT tường minh. DDL_LOCK_TIMEOUT điều khiển DDL chờ khóa DML. Cần kiểm tra tài liệu đúng phiên bản và reset ALTER SESSION settings khi dùng connection pool.

### 6.2. Query timeout và cancel

Oracle thường nhận giới hạn thời gian thực thi từ driver/client, ví dụ query timeout của JDBC hoặc call timeout của OCI. Các cơ chế này khác với DML_LOCK_TIMEOUT: query timeout giới hạn thời gian lời gọi, còn DML_LOCK_TIMEOUT tập trung vào chờ khóa.

Cancel từ client có thể tạo lỗi hủy như ORA-01013. Kết thúc session bằng thao tác quản trị như ALTER SYSTEM KILL SESSION mạnh hơn và có thể cần thời gian rollback. Chỉ dùng khi đã xác định đúng SID/serial và đánh giá transaction đang chạy.

### 6.3. Chẩn đoán blocking

DBA có thể xem:

- V$SESSION: trạng thái session, event, wait class, blocking_session.
- V$LOCK: loại khóa, mode và request.
- V$LOCKED_OBJECT: đối tượng đang bị khóa.
- V$SQL và các view liên quan để tìm SQL đang chạy.

Các view động có yêu cầu quyền phù hợp. Cần xác định session blocker gốc, transaction age và câu lệnh đã lấy khóa trước khi hủy.

## 7. SQLite và ứng dụng nhúng

SQLite thường dùng khóa ở mức database/page theo journal mode và cơ chế concurrency của phiên bản. Ứng dụng có thể cấu hình thời gian chờ bận:

~~~sql
PRAGMA busy_timeout = 2000;
~~~

Giá trị tính bằng mili giây. Khi database đang bận, SQLite chờ trong khoảng thời gian đã đặt trước khi trả SQLITE_BUSY nếu vẫn không thể tiếp tục.

Ở tầng C API, sqlite3_interrupt() có thể yêu cầu hủy thao tác đang chạy trên connection. Ứng dụng dùng binding khác cần kiểm tra API tương đương của thư viện. busy_timeout không phải giới hạn thời gian tổng quát cho mọi câu SQL; nó chỉ điều khiển chờ khi gặp trạng thái busy/locked theo cơ chế SQLite.

## 8. Hủy câu lệnh, rollback và trạng thái connection

Sau khi statement bị timeout hoặc cancel, ứng dụng phải xác định transaction đang ở trạng thái nào trước khi trả connection về pool.

| Hệ quản trị | Hủy statement | Điều cần làm rõ về transaction |
|---|---|---|
| PostgreSQL | Driver cancel hoặc pg_cancel_backend | Statement lỗi trong explicit transaction thường làm transaction ở trạng thái aborted; cần ROLLBACK hoặc xử lý savepoint |
| SQL Server | Driver gửi attention/cancel | Statement dừng nhưng explicit transaction có thể còn; kiểm tra XACT_STATE() và rollback theo hợp đồng |
| MySQL InnoDB | Driver cancel hoặc KILL QUERY | Lock wait timeout mặc định thường rollback statement; deadlock rollback transaction; ứng dụng nên quản lý atomicity |
| Oracle | Driver cancel/call timeout | Statement bị hủy; transaction có thể vẫn mở và cần rollback theo đơn vị nghiệp vụ |
| SQLite | sqlite3_interrupt() hoặc busy timeout hết hạn | Kiểm tra mã lỗi và transaction state; rollback nếu thao tác nghiệp vụ cần tính nguyên tử |

Một thao tác cancel không đồng nghĩa với việc mọi thay đổi trước đó trong transaction đã biến mất. Nếu transaction đã thực hiện ba statement và statement thứ tư bị hủy, ba statement trước có thể vẫn nằm trong transaction. Ứng dụng cần quyết định rollback toàn bộ để giữ tính nguyên tử.

### 8.1. Quy tắc xử lý trong ứng dụng

Một luồng xử lý an toàn thường gồm:

1. Bắt đầu transaction tại đúng tầng sở hữu transaction.
2. Thiết lập timeout phù hợp với loại workload.
3. Thực hiện statement và theo dõi cancellation token/deadline.
4. Khi có timeout hoặc cancel, ngừng gửi statement mới.
5. Rollback transaction nếu nghiệp vụ yêu cầu tất cả hoặc không gì cả.
6. Xác nhận connection ở trạng thái sạch trước khi trả về pool.
7. Ghi log loại timeout, thời gian chờ, SQL fingerprint, transaction age và blocker nếu có.
8. Chỉ retry nếu lỗi có thể phục hồi và thao tác có tính idempotent hoặc được bảo vệ bằng khóa/idempotency key.

Không nuốt lỗi timeout rồi trả kết quả thành công. Cũng không trả connection có transaction chưa kết thúc về pool; request sau có thể kế thừa trạng thái transaction hoặc session setting của request trước.

## 9. Deadlock khác lock timeout

Lock timeout xảy ra khi một thao tác chờ khóa quá lâu. Deadlock là chu trình phụ thuộc khóa: transaction A giữ khóa mà B cần, đồng thời B giữ khóa mà A cần. Nếu engine phát hiện chu trình, nó chọn một transaction làm victim và hủy/rollback theo cơ chế của hệ quản trị.

Timeout không thay thế deadlock detection:

- Một giao dịch có thể chờ lâu mà không có deadlock.
- Deadlock có thể được phát hiện ngay cả khi lock timeout được đặt dài.
- Tăng lock timeout không sửa thứ tự lấy khóa gây deadlock.
- Giảm lock timeout quá thấp có thể biến tải hợp lệ thành nhiều lỗi timeout.

Mã lỗi deadlock thường gặp:

| Hệ quản trị | Mã hoặc dấu hiệu |
|---|---|
| PostgreSQL | SQLSTATE 40P01 |
| SQL Server | Error 1205 |
| MySQL InnoDB | Error 1213 |
| Oracle | ORA-00060 |

Giải pháp gốc thường gồm lấy khóa theo thứ tự nhất quán, rút ngắn transaction, cập nhật ít hàng hơn, tạo index để tránh scan khi tìm hàng cần khóa và tránh chờ người dùng trong transaction.

### 9.1. Retry có giới hạn

Deadlock hoặc serialization failure có thể được retry ở cấp transaction nếu nghiệp vụ cho phép. Dùng số lần retry nhỏ, exponential backoff có jitter và deadline tổng. Trước khi retry, rollback transaction cũ và bảo đảm lần chạy trước không tạo tác dụng phụ bên ngoài database chưa được kiểm soát.

Không retry vô hạn. Retry một transaction không idempotent có thể gửi email, trừ tiền hoặc gọi dịch vụ ngoài nhiều lần. Với thao tác thanh toán hoặc tạo đơn, dùng idempotency key và transactional outbox hoặc cơ chế tương đương để kiểm soát tác dụng phụ.

## 10. Chẩn đoán nguyên nhân trước khi tăng timeout

Khi một request timeout, hãy xác định nó đã chờ ở đâu:

| Dấu hiệu | Khả năng cần kiểm tra |
|---|---|
| Pool acquisition timeout | Pool hết connection, connection bị giữ lâu hoặc giới hạn pool quá nhỏ |
| Lock timeout | Blocker giữ khóa, transaction dài, hàng nóng hoặc thứ tự khóa |
| Statement timeout | Scan lớn, join kém, sort/hash spill, I/O chậm hoặc cardinality sai |
| Client command timeout | Driver deadline ngắn, mạng chậm, server chưa nhận cancel hoặc trả kết quả lớn |
| Idle-in-transaction timeout | Ứng dụng mở transaction rồi chờ xử lý bên ngoài |
| DDL lock timeout | Transaction đang giữ metadata/schema lock |
| Deadlock | Chu trình khóa giữa nhiều transaction |

Tăng timeout chỉ làm request chờ lâu hơn; nó không làm truy vấn nhanh hơn hoặc giải phóng blocker. Trước khi thay đổi, đo:

- Thời gian từ lúc gửi statement đến lúc bắt đầu chạy.
- Thời gian chờ khóa và blocker.
- CPU, logical reads, physical reads và I/O wait.
- Số hàng ước lượng so với số hàng thực tế.
- Sort/hash spill và memory grant.
- Transaction age và số statement trong transaction.
- Số connection đang active, idle và chờ trong pool.
- Tỷ lệ timeout, deadlock, retry và request bị client hủy.

### 10.1. Tìm blocker gốc

Một session bị block có thể đang chờ một session khác, và session đó lại chờ session thứ ba. Cần lần theo chuỗi đến blocker gốc thay vì chỉ hủy waiter đầu tiên.

Kiểm tra:

- Session blocker có transaction mở từ bao lâu?
- Nó đang chạy SQL hay đang idle trong transaction?
- Có giữ khóa do đọc/ghi quá nhiều hàng không?
- Có gọi dịch vụ ngoài hoặc chờ user trong transaction không?
- Có index phù hợp để giảm phạm vi khóa không?
- Có nhiều transaction lấy khóa theo thứ tự khác nhau không?

Chỉ hủy blocker khi đã xác định tác động và chủ sở hữu nghiệp vụ. Hủy một session đang thực hiện giao dịch quan trọng có thể gây rollback dài và tăng tải I/O.

## 11. Timeout và connection pool

Connection pool tái sử dụng session, do đó một số cấu hình timeout có thể tồn tại sau khi request kết thúc:

- PostgreSQL session-level SET có thể tồn tại đến khi reset hoặc đóng session; SET LOCAL giới hạn trong transaction.
- SQL Server SET LOCK_TIMEOUT có phạm vi session.
- MySQL SET SESSION thay đổi biến của connection.
- Oracle ALTER SESSION thay đổi thuộc tính session.

Nếu một request đặt timeout 200 ms rồi connection được trả về pool mà không reset, request sau có thể bất ngờ nhận timeout 200 ms. Ngược lại, một request báo cáo có thể đặt timeout rất dài và làm request API sau chờ lâu.

Thực hành tốt:

1. Ưu tiên thiết lập transaction-local hoặc statement-level khi engine hỗ trợ.
2. Nếu phải dùng session setting, lưu giá trị ban đầu và khôi phục trong khối finally/cleanup.
3. Cấu hình reset session của pool và kiểm tra nó thực sự chạy sau lỗi/cancel.
4. Không trả connection về pool khi transaction chưa commit/rollback.
5. Theo dõi thời gian connection được mượn và số connection đang chờ.
6. Dùng pool riêng hoặc role riêng cho workload có timeout rất khác nhau nếu cần.

## 12. Ví dụ thiết kế timeout cho API cập nhật đơn hàng

Yêu cầu: API chuyển một đơn hàng từ READY sang PROCESSING. Nếu đơn đang bị giao dịch khác giữ khóa, API không nên chờ lâu. Tổng request phải phản hồi trong khoảng hai giây.

Với PostgreSQL, một cách triển khai minh họa:

~~~sql
BEGIN;

SET LOCAL lock_timeout = '250ms';
SET LOCAL statement_timeout = '1200ms';

UPDATE orders
SET status = 'PROCESSING',
    started_at = CURRENT_TIMESTAMP
WHERE id = :order_id
  AND status = 'READY';

COMMIT;
~~~

Ứng dụng đặt command timeout hơi dài hơn statement timeout, nhưng vẫn nằm trong deadline request. Khi nhận lỗi lock timeout hoặc statement timeout, ứng dụng rollback transaction, phân loại lỗi và trả phản hồi phù hợp.

Các điểm phải kiểm tra:

1. Có index trên khóa định vị hàng, thường là primary key id.
2. UPDATE chỉ tác động đúng một hàng.
3. Nếu số hàng cập nhật bằng 0, ứng dụng phân biệt đơn không tồn tại với đơn không còn READY.
4. Lock timeout đủ ngắn để tránh chờ lâu nhưng không thấp đến mức gây lỗi giả dưới tải bình thường.
5. Statement timeout bao trùm cả thời gian chạy và chờ khóa theo cơ chế PostgreSQL.
6. Transaction được rollback khi có lỗi trước khi connection quay lại pool.
7. Thao tác có thể retry an toàn hay không được xác định bằng trạng thái nghiệp vụ và idempotency.

Nếu dùng SQL Server, MySQL hoặc Oracle, phải thay phần cấu hình timeout bằng cơ chế tương ứng đã trình bày. Không sao chép trực tiếp đơn vị mili giây/giây hoặc giả định cùng phạm vi session.

## 13. Quy trình thiết lập và vận hành timeout

1. **Xác định deadline nghiệp vụ:** SLO của API, batch hoặc báo cáo và thời gian dự phòng cho ứng dụng.
2. **Phân loại loại chờ:** pool, lock, statement, metadata/DDL, network hoặc idle transaction.
3. **Đo baseline:** p50/p95/p99, thời gian chờ khóa, query duration, CPU, I/O và transaction age.
4. **Chọn phạm vi cấu hình:** statement, transaction, session, role, database hoặc client driver.
5. **Đặt lock timeout và statement timeout:** lock timeout thường ngắn hơn statement timeout; client deadline phải phối hợp với server.
6. **Xác định hành vi cancel:** driver gửi cancel hay đóng connection; DBA dùng cancel statement hay terminate session.
7. **Định nghĩa rollback:** xác định lỗi nào hủy statement, lỗi nào hủy transaction và ai sở hữu transaction.
8. **Kiểm thử đồng thời:** tạo blocker có kiểm soát, xác nhận waiter timeout đúng thời gian và blocker không bị ảnh hưởng ngoài dự kiến.
9. **Kiểm thử query dài:** xác nhận statement timeout dừng truy vấn và giải phóng tài nguyên.
10. **Kiểm thử pool:** xác nhận session setting được reset và connection sạch sau cancel/rollback.
11. **Đo lại dưới tải:** theo dõi throughput, latency, timeout rate, deadlock, lock wait và connection utilization.
12. **Điều chỉnh theo bằng chứng:** sửa query/index/transaction nếu nguyên nhân là hiệu năng hoặc contention; chỉ tăng timeout khi workload hợp lệ cần thêm thời gian.

## 14. Các sai lầm thường gặp

- **Dùng lock timeout như query timeout:** truy vấn không chờ khóa vẫn có thể chạy rất lâu.
- **Dùng query timeout như lock timeout:** có thể để một request chờ blocker gần hết toàn bộ deadline.
- **Chỉ cấu hình ở driver:** server có thể tiếp tục xử lý nếu cancel không được gửi hoặc không được nhận.
- **Chỉ cấu hình ở server:** ứng dụng có thể bỏ request trước khi server timeout và để connection ở trạng thái không rõ.
- **Đặt timeout giống nhau cho API và báo cáo:** hai workload có ngân sách và đặc tính khác nhau.
- **Đặt timeout quá thấp:** tạo nhiều lỗi dưới tải bình thường và làm tăng retry storm.
- **Tăng timeout để che blocker:** làm connection bị chiếm lâu hơn và có thể tăng hàng đợi.
- **Nhầm idle connection timeout với query timeout:** connection không hoạt động và statement đang chạy là hai trạng thái khác nhau.
- **Không rollback sau cancel:** transaction có thể còn mở, giữ khóa và làm bẩn connection pool.
- **Không reset session setting:** request tiếp theo kế thừa timeout của request trước.
- **Dùng KILL session khi chỉ cần cancel statement:** gây rollback rộng hơn và có thể làm gián đoạn giao dịch khác trong cùng session.
- **Retry vô hạn sau timeout/deadlock:** làm tăng tải và có thể lặp tác dụng phụ.
- **Nhầm deadlock với lock timeout:** một bên là chu trình khóa, một bên là chờ vượt ngưỡng.
- **Không theo dõi blocker gốc:** hủy waiter không giải quyết transaction đang giữ khóa.

## 15. Checklist cấu hình timeout và hủy thao tác

- [ ] Đã phân biệt pool timeout, lock timeout, statement timeout, transaction idle timeout và client deadline.
- [ ] Đã xác định SLO và ngân sách thời gian cho từng workload.
- [ ] Lock timeout ngắn hơn statement timeout khi phù hợp với engine.
- [ ] Client command timeout được phối hợp với server-side timeout và request deadline.
- [ ] Đã xác minh đơn vị và phạm vi session/transaction/statement của đúng hệ quản trị.
- [ ] Đã hiểu lỗi timeout có rollback statement hay toàn transaction.
- [ ] Cancel statement và terminate session được dùng đúng mục đích.
- [ ] Transaction được rollback hoặc phục hồi savepoint trước khi trả connection về pool.
- [ ] Session settings được reset sau request.
- [ ] Đã kiểm thử timeout khi có blocker và khi truy vấn chạy lâu không bị block.
- [ ] Đã đo p95/p99, throughput, lock wait, CPU, I/O và tỷ lệ timeout.
- [ ] Deadlock được chẩn đoán riêng và retry có giới hạn.
- [ ] Có log đủ để xác định blocker, SQL fingerprint, transaction age và loại timeout.
- [ ] Quy trình DBA cancel/kill có xác nhận session và đánh giá tác động rollback.

Thiết lập timeout đúng giúp giới hạn thời gian tài nguyên bị giữ và cho ứng dụng khả năng phục hồi khi có tranh chấp. Lock timeout kiểm soát thời gian chờ khóa; statement/query timeout kiểm soát thời gian thực thi; cancel yêu cầu dừng thao tác. Hãy phối hợp các giới hạn với deadline của ứng dụng, hiểu hành vi transaction của từng hệ quản trị và đo nguyên nhân trước khi thay đổi giá trị. Sau mọi timeout hoặc cancel, phải xử lý transaction và trạng thái connection rõ ràng để tránh giữ khóa hoặc làm nhiễm cấu hình cho request tiếp theo.

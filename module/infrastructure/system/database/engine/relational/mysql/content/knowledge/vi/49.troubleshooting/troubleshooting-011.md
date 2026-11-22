# Waiting for table metadata lock và giao dịch bỏ quên

Một câu lệnh ALTER TABLE có thể đứng chờ rất lâu dù CPU thấp, disk vẫn hoạt động và không có truy vấn SELECT nào chạy lâu. Nguyên nhân thường là một session khác đang giữ metadata lock trên bảng. Session giữ khóa có thể đang chạy transaction bình thường, hoặc đã chuyển sang trạng thái Sleep nhưng transaction vẫn mở vì ứng dụng quên commit/rollback. Nếu không nhận ra giao dịch bỏ quên, người vận hành có thể chỉ nhìn thấy DDL đang chờ và hàng loạt truy vấn mới bắt đầu timeout.

Bài học này thuộc chương **Xử lý sự cố** của module **DATABASE_MYSQL**. Trong lộ trình làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành, việc hiểu metadata lock giúp xác định vì sao DDL bị chặn và vì sao một kết nối tưởng như không làm gì vẫn có thể giữ schema không cho thay đổi.

## 1. Metadata lock là gì?

MySQL dùng **metadata lock (MDL)** để bảo vệ metadata của các đối tượng database như schema, table, view, stored program và một số đối tượng khác. Khi một câu lệnh truy cập bảng, MySQL lấy loại metadata lock phù hợp để ngăn một thay đổi cấu trúc không tương thích diễn ra trong lúc câu lệnh đang sử dụng đối tượng đó.

Ví dụ:

- SELECT lấy metadata lock đọc trên bảng.
- INSERT, UPDATE và DELETE lấy metadata lock phù hợp cho thao tác ghi.
- ALTER TABLE cần metadata lock độc quyền ở giai đoạn thay đổi metadata.
- DROP TABLE, RENAME TABLE và một số thao tác DDL khác cũng cần khóa metadata xung đột với hoạt động đang sử dụng đối tượng.

MDL khác với row lock của InnoDB. Row lock bảo vệ các hàng dữ liệu trong transaction; metadata lock bảo vệ định nghĩa và metadata của đối tượng. Một truy vấn có thể không chờ row lock nhưng vẫn giữ MDL, và DDL có thể bị chặn bởi MDL ngay cả khi không có hàng nào bị khóa.

### Vòng đời của MDL trong transaction

Với bảng transactional như InnoDB, metadata lock được lấy khi câu lệnh truy cập bảng và thường được giữ đến khi transaction kết thúc. Nếu transaction chạy SELECT rồi không COMMIT hoặc ROLLBACK, MDL có thể tiếp tục tồn tại dù câu SELECT đã kết thúc.

Ví dụ:

~~~sql
-- Session A
SET autocommit = 0;
START TRANSACTION;

SELECT *
FROM customers
WHERE id = 1001;

-- Session A chưa COMMIT hoặc ROLLBACK.
-- Kết nối có thể trở về trạng thái Sleep nhưng transaction vẫn mở.
~~~

Trong lúc đó, session B chạy:

~~~sql
-- Session B
ALTER TABLE customers
  ADD COLUMN source_system VARCHAR(32) NULL;
~~~

ALTER TABLE cần MDL độc quyền để hoàn tất thay đổi. Nó phải chờ metadata lock tương thích từ các session đang giữ khóa trên bảng. Session A có thể không còn câu SQL đang chạy, nhưng transaction chưa kết thúc nên vẫn giữ khóa.

Khi session A COMMIT hoặc ROLLBACK, MDL được giải phóng và DDL có thể tiếp tục nếu không còn blocker khác.

### Vì sao một DDL đang chờ có thể làm nhiều truy vấn khác bị chờ?

Khi DDL yêu cầu khóa độc quyền và phải xếp hàng chờ các khóa hiện có, các request metadata lock mới trên cùng đối tượng có thể bị xếp phía sau request đang chờ tùy quy tắc ưu tiên của lock manager. Vì vậy, một transaction bỏ quên có thể chặn DDL; sau đó DDL đang chờ lại khiến truy vấn đọc/ghi mới bị xếp hàng. Người dùng thấy cả bảng “đứng”, dù blocker ban đầu chỉ là một session.

Không phải mọi DDL wait đều làm toàn bộ truy vấn dừng. Mức ảnh hưởng phụ thuộc loại lock, thứ tự request và thao tác cụ thể. Cần quan sát danh sách lock đang chờ và đang được cấp thay vì suy luận chỉ từ một dòng processlist.

## 2. Phân biệt metadata lock với InnoDB row lock

Hai loại lock có nguồn và cách điều tra khác nhau:

| Dấu hiệu | Metadata lock | InnoDB row lock |
|---|---|---|
| Bảo vệ | Metadata/định nghĩa đối tượng | Hàng dữ liệu và phạm vi index liên quan |
| Tình huống thường gặp | ALTER TABLE chờ SELECT/transaction đang mở | UPDATE chờ transaction khác cập nhật cùng hàng |
| Processlist state | Có thể hiện Waiting for table metadata lock | Có thể hiện Waiting for row lock hoặc trạng thái chờ lock khác |
| Nguồn quan sát | performance_schema.metadata_locks, sys.schema_table_lock_waits | performance_schema.data_locks, data_lock_waits |
| Timeout chính | lock_wait_timeout | innodb_lock_wait_timeout cho InnoDB row lock |
| Cách giải phóng | Kết thúc session/transaction giữ MDL hoặc hoàn tất câu lệnh liên quan | Commit/rollback transaction giữ row lock |

Không dùng innodb_lock_wait_timeout để xử lý DDL đang chờ metadata lock. Hai timeout này điều khiển hai loại chờ khác nhau.

SHOW ENGINE INNODB STATUS hữu ích để xem transaction và row lock của InnoDB, nhưng không thay thế việc kiểm tra performance_schema.metadata_locks khi điều tra MDL.

## 3. Nhận diện câu lệnh đang chờ metadata lock

Bắt đầu bằng processlist:

~~~sql
SHOW FULL PROCESSLIST;
~~~

Tìm session có trạng thái như:

- Waiting for table metadata lock.
- Query đang chạy ALTER TABLE, CREATE INDEX, DROP TABLE hoặc RENAME TABLE.
- Các truy vấn khác trên cùng bảng có thời gian chờ tăng sau khi DDL bắt đầu.

Cột Time trong processlist cho biết thời gian ở trạng thái hiện tại, không phải lúc nào cũng là tổng thời gian từ khi request được gửi ở ứng dụng. Ghi lại Id, User, Host, db, Command, Time, State và Info.

Có thể lọc bằng Performance Schema:

~~~sql
SELECT
  PROCESSLIST_ID,
  PROCESSLIST_USER,
  PROCESSLIST_HOST,
  PROCESSLIST_DB,
  PROCESSLIST_COMMAND,
  PROCESSLIST_TIME,
  PROCESSLIST_STATE,
  LEFT(PROCESSLIST_INFO, 300) AS statement_sample
FROM performance_schema.threads
WHERE TYPE = 'FOREGROUND'
  AND PROCESSLIST_STATE LIKE '%metadata lock%'
ORDER BY PROCESSLIST_TIME DESC;
~~~

Một câu lệnh đang chờ thường có processlist state rõ ràng. Tuy nhiên, blocker có thể ở trạng thái Sleep và không có PROCESSLIST_INFO. Vì vậy, chỉ lọc các session có state chứa metadata lock sẽ tìm được waiter nhưng có thể bỏ sót blocker.

## 4. Xem lock đang chờ và lock đã được cấp

Bảng performance_schema.metadata_locks ghi nhận metadata lock được cấp hoặc đang chờ. Truy vấn sau liệt kê lock của các đối tượng trong schema hiện tại:

~~~sql
SELECT
  ml.OBJECT_TYPE,
  ml.OBJECT_SCHEMA,
  ml.OBJECT_NAME,
  ml.LOCK_TYPE,
  ml.LOCK_DURATION,
  ml.LOCK_STATUS,
  t.PROCESSLIST_ID,
  t.PROCESSLIST_USER,
  t.PROCESSLIST_HOST,
  t.PROCESSLIST_DB,
  t.PROCESSLIST_COMMAND,
  t.PROCESSLIST_TIME,
  t.PROCESSLIST_STATE,
  LEFT(t.PROCESSLIST_INFO, 250) AS statement_sample
FROM performance_schema.metadata_locks AS ml
LEFT JOIN performance_schema.threads AS t
  ON t.THREAD_ID = ml.OWNER_THREAD_ID
WHERE ml.OBJECT_SCHEMA = DATABASE()
ORDER BY
  ml.OBJECT_NAME,
  CASE ml.LOCK_STATUS
    WHEN 'PENDING' THEN 0
    ELSE 1
  END,
  t.PROCESSLIST_TIME DESC;
~~~

Các cột quan trọng:

- OBJECT_TYPE, OBJECT_SCHEMA, OBJECT_NAME: loại và tên đối tượng đang được khóa.
- LOCK_TYPE: loại MDL mà thread yêu cầu hoặc đang giữ.
- LOCK_DURATION: thời hạn khóa, thường là STATEMENT, TRANSACTION hoặc EXPLICIT.
- LOCK_STATUS: GRANTED nghĩa là lock đã được cấp; PENDING nghĩa là đang chờ.
- OWNER_THREAD_ID: Performance Schema thread đang sở hữu request lock.

Khi điều tra, tìm PENDING trước, sau đó xem các lock GRANTED trên cùng đối tượng. Một lock GRANTED không nhất thiết là blocker; phải xem loại lock có xung đột với lock đang chờ hay không và quan hệ transaction/session. Dùng sys view ở phần tiếp theo để xem cặp waiting/blocking đã được MySQL tổng hợp.

Nếu truy vấn không có dữ liệu, kiểm tra instrumentation của MDL:

~~~sql
SELECT
  NAME,
  ENABLED,
  TIMED
FROM performance_schema.setup_instruments
WHERE NAME = 'wait/lock/metadata/sql/mdl';
~~~

Nếu instrument bị tắt, việc bật cần được đánh giá theo chính sách giám sát và quyền vận hành. Không thay đổi instrumentation trên production trong lúc incident nếu chưa biết tác động và quy trình rollback cấu hình.

## 5. Dùng sys.schema_table_lock_waits để tìm blocker

MySQL có schema sys với view schema_table_lock_waits giúp ghép request đang chờ với thread có lock chặn. Nếu view có sẵn và được cấp quyền đọc, đây thường là cách nhanh nhất:

~~~sql
SELECT
  object_schema,
  object_name,
  waiting_pid,
  waiting_account,
  waiting_lock_type,
  waiting_lock_duration,
  waiting_query,
  waiting_query_secs,
  blocking_pid,
  blocking_account,
  blocking_lock_type,
  blocking_lock_duration,
  blocking_query,
  blocking_query_secs
FROM sys.schema_table_lock_waits
ORDER BY waiting_query_secs DESC;
~~~

Ý nghĩa:

- waiting_pid: connection ID của session đang chờ.
- waiting_query: câu lệnh đang chờ metadata lock.
- blocking_pid: connection ID của session được xác định là đang chặn.
- blocking_query: câu lệnh hiện tại của blocker; có thể NULL nếu blocker đang Sleep.
- blocking_query_secs: thời gian câu lệnh blocker đang chạy nếu có.

Nếu blocking_query là NULL và blocking_pid vẫn tồn tại, hãy kiểm tra transaction của connection đó. Đây là tình huống thường gặp với giao dịch đã chạy SELECT rồi để session idle.

View sys là lớp tiện ích trên Performance Schema. Nếu không có view hoặc phiên bản/thiết lập khác, dùng metadata_locks và threads để điều tra trực tiếp.

## 6. Tìm giao dịch InnoDB bị bỏ quên

Bảng INFORMATION_SCHEMA.INNODB_TRX cho biết các transaction InnoDB đang hoạt động, kể cả transaction không có câu SQL hiện tại. Truy vấn:

~~~sql
SELECT
  trx_id,
  trx_state,
  trx_started,
  TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
  trx_mysql_thread_id AS connection_id,
  trx_query,
  trx_operation_state,
  trx_tables_locked,
  trx_rows_locked,
  trx_rows_modified,
  trx_isolation_level,
  trx_is_read_only
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Các trường cần chú ý:

- trx_started: thời điểm transaction bắt đầu.
- trx_age_seconds: tuổi transaction tính đến thời điểm quan sát.
- connection_id: MySQL connection ID tương ứng với session.
- trx_query: câu SQL hiện tại; NULL có thể xuất hiện khi session không có câu SQL đang chạy.
- trx_rows_locked và trx_rows_modified: số hàng đang khóa hoặc đã sửa theo thông tin InnoDB.
- trx_operation_state: trạng thái thao tác hiện tại nếu có.

Transaction lâu không tự động là giao dịch bỏ quên. Một batch hợp lệ có thể chạy lâu; một transaction read-only có thể được giữ có chủ đích. Cần đối chiếu với owner, request, thời gian và mục đích nghiệp vụ.

### Ghép transaction với processlist

~~~sql
SELECT
  it.trx_id,
  it.trx_started,
  TIMESTAMPDIFF(SECOND, it.trx_started, NOW()) AS trx_age_seconds,
  it.trx_state,
  it.trx_query,
  it.trx_rows_locked,
  it.trx_rows_modified,
  p.ID AS connection_id,
  p.USER,
  p.HOST,
  p.DB,
  p.COMMAND,
  p.TIME AS processlist_time,
  p.STATE,
  p.INFO
FROM information_schema.innodb_trx AS it
LEFT JOIN information_schema.PROCESSLIST AS p
  ON p.ID = it.trx_mysql_thread_id
ORDER BY it.trx_started;
~~~

Một giao dịch có trx_query NULL và processlist COMMAND là Sleep là ứng viên cần kiểm tra. Nhưng không được kết luận chỉ từ Sleep: connection có thể đang nằm giữa các lệnh trong một transaction được thiết kế rõ. Hãy tra application request ID, pool metrics, log transaction và chủ sở hữu session.

### Transaction bỏ quên hình thành như thế nào?

Các nguyên nhân phổ biến:

- Code gọi setAutoCommit(false) nhưng quên commit/rollback ở một nhánh exception.
- Một phương thức @Transactional giữ transaction trong khi chờ HTTP call, message broker hoặc thao tác file.
- Ứng dụng mở transaction rồi trả response sớm nhưng cleanup không chạy.
- Connection được giữ quá lâu hoặc leak khỏi pool.
- Job batch xử lý một tập dữ liệu lớn trong một transaction duy nhất.
- Script DBA mở START TRANSACTION để kiểm tra dữ liệu rồi quên kết thúc.
- Framework quản lý transaction không đúng DataSource hoặc transaction manager.
- Một session dùng autocommit=0 và không kết thúc transaction sau SELECT.

Khi transaction chưa kết thúc, một câu SELECT đã xong vẫn có thể giữ MDL trên bảng đã đọc. Đó là lý do một session Sleep đôi khi chặn ALTER TABLE.

## 7. Xác định session nào đang chặn DDL

Một quy trình ghép thông tin:

1. Từ processlist, lấy connection ID của DDL đang ở trạng thái Waiting for table metadata lock.
2. Từ sys.schema_table_lock_waits hoặc metadata_locks, lấy blocking_pid hoặc OWNER_THREAD_ID.
3. Ghép connection ID với INNODB_TRX để tìm transaction start và trạng thái.
4. Ghép thread với processlist để biết user, host, command và thời gian idle.
5. Tra log ứng dụng hoặc pool để xác định request/service sở hữu connection.
6. Xác minh bảng/object và câu lệnh trước đó có liên quan tới DDL đang chờ.

Có thể lấy thread ID và connection ID từ Performance Schema:

~~~sql
SELECT
  t.THREAD_ID,
  t.PROCESSLIST_ID,
  t.PROCESSLIST_USER,
  t.PROCESSLIST_HOST,
  t.PROCESSLIST_DB,
  t.PROCESSLIST_COMMAND,
  t.PROCESSLIST_TIME,
  t.PROCESSLIST_STATE,
  t.PROCESSLIST_INFO
FROM performance_schema.threads AS t
WHERE t.PROCESSLIST_ID IN (12345, 12346);
~~~

Thay 12345 và 12346 bằng connection ID quan sát được. THREAD_ID là ID nội bộ của Performance Schema; PROCESSLIST_ID là connection ID dùng trong KILL.

Nếu blocker đã Sleep, PROCESSLIST_INFO thường không còn câu SELECT trước đó. Lịch sử câu lệnh có thể có trong events_statements_history hoặc events_statements_history_long nếu consumer được bật và sự kiện chưa bị ghi đè. Không đảm bảo history luôn chứa câu SQL đã tạo MDL; hãy dùng transaction age, log ứng dụng và thông tin connection pool để bổ sung.

## 8. lock_wait_timeout khác innodb_lock_wait_timeout

Đây là nhầm lẫn thường làm incident kéo dài:

| Biến | Điều khiển | Phạm vi |
|---|---|---|
| lock_wait_timeout | Thời gian chờ metadata lock | MDL trên metadata object |
| innodb_lock_wait_timeout | Thời gian chờ InnoDB row lock | Lock dữ liệu của InnoDB |

Trong MySQL, lock_wait_timeout có mặc định rất dài, thường là 31.536.000 giây (một năm). Vì vậy, một ALTER TABLE có thể chờ gần như vô thời hạn nếu không được đặt timeout phù hợp.

Có thể giới hạn thời gian chờ cho riêng session chạy migration:

~~~sql
SET SESSION lock_wait_timeout = 30;

ALTER TABLE customers
  ADD COLUMN source_system VARCHAR(32) NULL;
~~~

Nếu MDL chưa được cấp trong 30 giây, câu lệnh sẽ lỗi timeout thay vì tiếp tục chờ. Đây là giới hạn thời gian chờ lấy khóa, không phải giới hạn tổng thời gian chạy DDL sau khi đã lấy được khóa.

innodb_lock_wait_timeout không thay thế lock_wait_timeout. Nếu vấn đề là ALTER TABLE đang chờ metadata lock, giảm innodb_lock_wait_timeout không giải quyết đúng nguyên nhân.

Đặt timeout trong migration runner hoặc cùng session thực thi DDL. Nếu SET SESSION chạy trên connection khác với ALTER TABLE, timeout sẽ không áp dụng cho câu lệnh cần bảo vệ.

## 9. Xử lý an toàn khi phát hiện giao dịch bỏ quên

Không bắt đầu bằng KILL. Trước tiên xác định:

- Session có thuộc ứng dụng production, job batch hay DBA không?
- Transaction đã mở bao lâu?
- Có đang sửa dữ liệu hay chỉ đọc?
- Có hàng bị khóa hoặc thay đổi chưa commit không?
- DDL đang chờ có cần chạy ngay hay có thể hoãn?
- Có request nghiệp vụ đang phụ thuộc transaction đó không?
- Nếu rollback, lượng undo và thời gian phục hồi có thể lớn đến đâu?

Chọn hành động theo tình huống:

### Nếu transaction thuộc ứng dụng và request còn hoạt động

Liên hệ service owner hoặc tra request trace. Nếu request hợp lệ sắp hoàn tất, có thể chờ transaction kết thúc. Nếu code bị treo, xử lý ở tầng ứng dụng theo runbook và xác minh tác động trước khi ngắt session.

### Nếu transaction đã bị bỏ quên và có thể kết thúc an toàn

Ưu tiên để ứng dụng commit/rollback qua transaction manager nếu còn kiểm soát được request. Nếu phải chấm dứt session, ghi lại connection ID, owner, transaction age, câu SQL/lock và người phê duyệt theo quy trình vận hành.

### Nếu DDL đang chờ gây hàng đợi truy vấn

Nếu DDL có thể hoãn, hủy câu DDL đang chờ để giảm áp lực lên các request mới; sau đó xử lý blocker và lên lịch lại DDL với timeout. Hủy DDL đang chờ không tự giải phóng transaction blocker.

### Nếu phải kill session

Có hai lệnh khác nhau:

~~~sql
-- Chỉ dừng statement hiện tại của connection
KILL QUERY 12345;

-- Ngắt connection, kết thúc session và yêu cầu rollback transaction đang mở
KILL CONNECTION 12345;
~~~

KILL QUERY trên một session đang Sleep không kết thúc transaction; nó chỉ tác động statement hiện tại nếu có. Để giải phóng transaction bị bỏ quên, thường cần kết thúc transaction bằng COMMIT/ROLLBACK từ owner hoặc ngắt connection sau khi đã đánh giá tác động.

KILL CONNECTION không đồng nghĩa rollback hoàn tất ngay lập tức. InnoDB có thể cần thời gian để rollback các thay đổi đã thực hiện; trong thời gian rollback, tài nguyên và lock liên quan có thể chưa được giải phóng hoàn toàn. Theo dõi trạng thái sau thao tác, không chạy lặp KILL chỉ vì DDL chưa tiếp tục ngay.

Không dùng KILL trên connection ID chỉ dựa vào một snapshot cũ. Connection ID có thể đã kết thúc và được tái sử dụng; kiểm tra lại owner và trạng thái ngay trước thao tác.

## 10. Quy trình khắc phục một ALTER TABLE bị chờ

Giả sử migration cần thêm index vào bảng orders nhưng processlist cho thấy Waiting for table metadata lock.

**Bước 1 — Ghi nhận DDL waiter**

Lưu connection ID, user, host, câu ALTER, thời gian chờ và thời điểm bắt đầu.

**Bước 2 — Xác định object**

Lấy schema/table từ câu DDL và metadata_locks. Không chỉ xem DATABASE() của session điều tra vì DDL có thể nhắm tới schema khác.

**Bước 3 — Tìm blocker**

Dùng sys.schema_table_lock_waits; nếu không có view, đối chiếu PENDING và GRANTED trong metadata_locks theo cùng object.

**Bước 4 — Kiểm tra transaction**

Tra INNODB_TRX và processlist. Nếu blocker là Sleep, xác định transaction age, host và ứng dụng sở hữu session.

**Bước 5 — Đánh giá ảnh hưởng**

Xác định có truy vấn mới đang xếp hàng sau DDL không. So sánh số request timeout, pool pending và trạng thái các endpoint dùng bảng.

**Bước 6 — Chọn mitigation**

Nếu DDL không khẩn cấp và đang gây hàng đợi, cân nhắc hủy waiter. Nếu blocker là transaction bỏ quên, phối hợp owner để rollback hoặc kết thúc session an toàn.

**Bước 7 — Chạy lại có timeout**

Sau khi blocker được giải phóng và hệ thống ổn định, chạy lại migration với lock_wait_timeout phù hợp. Xác minh schema sau khi DDL hoàn tất.

**Bước 8 — Theo dõi phục hồi**

Xác nhận processlist không còn waiter, truy vấn ứng dụng hoạt động lại, pool pending giảm và migration history ghi nhận kết quả đúng.

Không tự động chạy lại ALTER TABLE sau timeout nếu chưa xác minh trạng thái schema. DDL có thể đã hoàn tất trước khi client mất kết nối hoặc nhận lỗi ở một bước tiếp theo; kiểm tra SHOW CREATE TABLE và migration history trước khi retry.

## 11. Phòng ngừa giao dịch bỏ quên trong ứng dụng

### Giữ transaction ngắn

Chỉ đặt các thao tác database cần tính nguyên tử bên trong transaction. Tránh gọi HTTP, gửi email, chờ người dùng, upload file hoặc đợi message broker trong khi transaction đang mở.

Ví dụ không tốt:

~~~java
@Transactional
public void createOrder(CreateOrderRequest request) {
    Order order = repository.save(toOrder(request));

    // Gọi dịch vụ bên ngoài trong khi transaction và MDL vẫn còn giữ.
    paymentClient.authorize(order);

    orderRepository.markAuthorized(order.getId());
}
~~~

Nếu payment service mất 20 giây, transaction database có thể giữ connection, row lock và MDL trong toàn bộ thời gian chờ.

Một thiết kế tốt hơn là chia ranh giới: ghi trạng thái cần thiết trong transaction ngắn, commit, gọi dịch vụ ngoài transaction, rồi mở transaction khác để cập nhật kết quả. Với nghiệp vụ cần tính nhất quán xuyên hệ thống, dùng outbox/saga hoặc cơ chế điều phối phù hợp thay vì giữ transaction SQL mở trong lúc chờ mạng.

### Kết thúc transaction trên mọi nhánh

Với JDBC thủ công, dùng try/catch/finally hoặc transaction manager để đảm bảo commit/rollback:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try {
        updateCustomer(connection);
        insertAuditRecord(connection);
        connection.commit();
    } catch (Exception error) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            error.addSuppressed(rollbackError);
        }
        throw error;
    }
}
~~~

Trong ứng dụng Spring, dùng @Transactional trên ranh giới nghiệp vụ phù hợp và để transaction manager quản lý commit/rollback. Tránh bắt exception rồi nuốt lỗi bên trong phương thức transaction nếu điều đó khiến framework không biết phải rollback. Cũng cần kiểm tra self-invocation, propagation và việc dùng đúng transaction manager/DataSource.

### Giới hạn batch transaction

Không giữ một transaction duy nhất cho hàng trăm nghìn hoặc hàng triệu hàng nếu không cần tính nguyên tử toàn bộ. Chia batch theo khóa chính hoặc phạm vi dữ liệu, commit từng batch, ghi checkpoint và thiết kế retry idempotent. Cách này giảm thời gian giữ MDL, undo log và row lock.

### Theo dõi connection pool

Theo dõi connection active, idle, pending, acquisition time và leak detection. Pool có thể phát hiện connection được giữ quá lâu, nhưng một connection idle trong pool không tự động là transaction đã đóng. Đảm bảo transaction được kết thúc trước khi logical connection được trả về pool.

## 12. Phòng ngừa DDL gây ảnh hưởng production

- Lập lịch DDL ngoài thời điểm traffic cao khi thao tác có thể cần MDL lâu.
- Trước migration, tìm transaction lâu và session idle in transaction.
- Đặt lock_wait_timeout cho session chạy DDL để tránh chờ vô hạn.
- Chạy thử trên bản sao có dữ liệu và workload gần production.
- Ước lượng thời gian rebuild, dung lượng tạm, I/O và tác động replication.
- Dùng native online DDL hoặc công cụ gh-ost/pt-online-schema-change khi phù hợp, nhưng vẫn dự kiến cần metadata lock ở một số thời điểm, đặc biệt khi đổi tên/hoán đổi bảng ở giai đoạn cutover.
- Theo dõi metadata lock trong suốt migration, không chỉ kiểm tra lúc bắt đầu.
- Có kế hoạch dừng DDL waiter nếu nó tạo hàng đợi ảnh hưởng ứng dụng.

Online DDL giảm thời gian chặn DML trong nhiều trường hợp nhưng không loại bỏ mọi yêu cầu MDL. Một transaction cũ có thể làm cả bước bắt đầu hoặc hoàn tất DDL chờ. Công cụ online schema change cũng phải lấy metadata lock để thực hiện một số thao tác cutover.

## 13. Giám sát transaction và metadata lock chủ động

Thiết lập cảnh báo dựa trên tuổi transaction và trạng thái lock, không chỉ dựa vào số connection.

Các chỉ số hữu ích:

- Transaction InnoDB lâu nhất.
- Số transaction có trx_query NULL nhưng vẫn mở.
- Số metadata lock PENDING theo object.
- Tuổi của MDL waiter.
- Số session Sleep đang có transaction.
- Số connection active/pending trong pool.
- Số request chờ database và p95/p99 latency.
- Số lần DDL timeout và lock wait timeout.

Có thể lấy transaction lâu nhất:

~~~sql
SELECT
  trx_mysql_thread_id AS connection_id,
  trx_started,
  TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age_seconds,
  trx_state,
  trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started
LIMIT 20;
~~~

Ngưỡng cảnh báo phải dựa trên đặc tính workload. Một transaction báo cáo 5 phút có thể hợp lệ; một transaction OLTP thường chỉ kéo dài vài mili giây. Nên phân loại theo tài khoản ứng dụng, schema, service và loại job thay vì dùng một ngưỡng duy nhất cho tất cả.

Có thể dùng Performance Schema/sys view để phát hiện waiter, sau đó gửi cảnh báo chứa object, waiting PID, blocking PID và tuổi transaction. Không tự động kill blocker chỉ vì vượt ngưỡng; tự động hóa chỉ nên thu thập và cảnh báo trừ khi tổ chức đã có chính sách xử lý được phê duyệt và kiểm thử.

## 14. Bảng triệu chứng và hướng kiểm tra

| Triệu chứng | Khả năng liên quan | Bằng chứng tiếp theo |
|---|---|---|
| ALTER TABLE ở Waiting for table metadata lock | Transaction khác đang giữ MDL xung đột | sys.schema_table_lock_waits, metadata_locks |
| Blocker có COMMAND=Sleep | Session idle nhưng transaction có thể chưa kết thúc | INNODB_TRX, transaction log, connection owner |
| Nhiều SELECT bắt đầu chờ sau khi DDL chờ | Lock queue trên cùng object | Processlist theo thời gian, MDL PENDING/GRANTED |
| innodb_lock_wait_timeout không ảnh hưởng DDL | Đang chờ MDL, không phải row lock | Kiểm tra lock_wait_timeout |
| KILL QUERY không giải phóng blocker Sleep | Không có statement hiện tại để dừng; transaction còn mở | Kết thúc transaction hoặc KILL CONNECTION sau đánh giá |
| KILL CONNECTION xong DDL vẫn chưa chạy | Rollback chưa hoàn tất hoặc còn blocker khác | Theo dõi INNODB_TRX, metadata_locks |
| DDL timeout nhưng schema có vẻ đã đổi | Trạng thái thực tế cần xác minh | SHOW CREATE TABLE, information_schema, migration history |

## 15. Checklist incident

**Khi phát hiện DDL đang chờ**

- [ ] Ghi lại câu DDL, connection ID, object và thời gian chờ.
- [ ] Chụp SHOW FULL PROCESSLIST.
- [ ] Kiểm tra sys.schema_table_lock_waits.
- [ ] Nếu cần, xem performance_schema.metadata_locks và threads.
- [ ] Xác định các lock GRANTED trên cùng object.
- [ ] Tra information_schema.innodb_trx để tìm transaction lâu.
- [ ] Xác định blocker có phải session Sleep hay không.
- [ ] Tra owner qua host, account, application trace và pool metrics.
- [ ] Đánh giá DDL waiter có đang làm các request mới xếp hàng.

**Trước khi kết thúc session**

- [ ] Xác minh connection ID và owner ngay trước thao tác.
- [ ] Kiểm tra transaction đã sửa bao nhiêu hàng và có tác động nghiệp vụ gì.
- [ ] Phối hợp owner để commit/rollback nếu có thể.
- [ ] Chỉ KILL CONNECTION khi đã đánh giá rollback và được phép theo runbook.
- [ ] Theo dõi cho đến khi rollback và lock thực sự được giải phóng.

**Sau khi khôi phục**

- [ ] Xác minh DDL hoàn tất hoặc bị hủy đúng trạng thái.
- [ ] Kiểm tra SHOW CREATE TABLE và migration history.
- [ ] Xác nhận processlist không còn waiter liên quan.
- [ ] Xác nhận pool pending, latency và error rate trở về ngưỡng.
- [ ] Ghi nguyên nhân gốc và bổ sung cảnh báo transaction/MDL.

## 16. Ghi nhớ

- Metadata lock bảo vệ metadata của bảng và đối tượng; nó khác row lock của InnoDB.
- Transaction InnoDB có thể giữ MDL đến COMMIT/ROLLBACK, kể cả khi session đã Sleep.
- DDL như ALTER TABLE có thể chờ transaction cũ; request mới trên cùng object cũng có thể bị xếp hàng.
- Dùng sys.schema_table_lock_waits và performance_schema.metadata_locks để tìm waiter/blocker.
- Dùng information_schema.innodb_trx để tìm transaction lâu hoặc idle; ghép với processlist để xác định owner.
- lock_wait_timeout điều khiển MDL; innodb_lock_wait_timeout điều khiển InnoDB row lock.
- KILL QUERY không kết thúc một transaction đang idle; KILL CONNECTION có thể kích hoạt rollback và rollback cần thời gian.
- Không kill session chỉ dựa vào trạng thái Sleep hoặc tuổi transaction; xác minh owner và tác động trước.
- Giữ transaction ngắn, không chờ dịch vụ ngoài trong transaction và commit/rollback trên mọi nhánh.
- Online DDL và công cụ schema change vẫn có thể cần MDL ở các giai đoạn quan trọng.

Khi một DDL bị chờ, hãy tìm session đang giữ metadata lock và kiểm tra transaction của nó trước khi can thiệp. Việc ghi nhận waiter, blocker, transaction age, owner và trạng thái sau mitigation giúp xử lý đúng sự cố hiện tại, đồng thời phát hiện lỗi quản lý transaction có thể tái diễn.

## Tài liệu tham khảo

- [MySQL 8.0 Reference Manual: Metadata Locking](https://dev.mysql.com/doc/refman/8.0/en/metadata-locking.html)
- [MySQL 8.0 Reference Manual: Performance Schema metadata_locks Table](https://dev.mysql.com/doc/refman/8.0/en/performance-schema-metadata-locks-table.html)
- [MySQL 8.0 Reference Manual: sys.schema_table_lock_waits View](https://dev.mysql.com/doc/refman/8.0/en/sys-schema-table-lock-waits.html)
- [MySQL 8.0 Reference Manual: INFORMATION_SCHEMA INNODB_TRX](https://dev.mysql.com/doc/refman/8.0/en/information-schema-innodb-trx-table.html)
- [MySQL 8.0 Reference Manual: lock_wait_timeout](https://dev.mysql.com/doc/refman/8.0/en/server-system-variables.html#sysvar_lock_wait_timeout)
- [MySQL 8.0 Reference Manual: InnoDB Lock Wait Timeout](https://dev.mysql.com/doc/refman/8.0/en/innodb-parameters.html#sysvar_innodb_lock_wait_timeout)
- [MySQL 8.0 Reference Manual: KILL Statement](https://dev.mysql.com/doc/refman/8.0/en/kill.html)


# Quan sát data_locks, data_lock_waits và phiên gây chặn

Trong MySQL, một câu lệnh có thể phải chờ vì transaction khác đang giữ khóa trên cùng bản ghi hoặc phạm vi dữ liệu. Khi sự cố xảy ra, cần trả lời được ba câu hỏi: transaction nào đang chờ, transaction nào đang giữ khóa gây chặn, và hai transaction đang tranh chấp đối tượng nào.

Với MySQL 8.0 sử dụng InnoDB, hai bảng Performance Schema quan trọng để điều tra là **performance_schema.data_locks** và **performance_schema.data_lock_waits**. Kết hợp chúng với **performance_schema.threads** và **information_schema.innodb_trx**, ta có thể lần từ quan hệ chờ khóa đến connection ID, người dùng, câu lệnh và tuổi transaction.

Bài học thuộc chương **Khóa và đồng thời** của module **DATABASE_MYSQL**. Trong phạm vi làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời, kỹ năng quan sát khóa giúp giải thích vì sao một câu UPDATE hoặc DELETE bị treo, vì sao transaction ngắn vẫn có thể bị chặn lâu, và cần kiểm tra gì trước khi can thiệp vào phiên đang chạy.

## 1. Phân biệt khóa đang tồn tại và quan hệ chờ khóa

**data_locks** cho biết các khóa mà storage engine đang theo dõi tại thời điểm truy vấn. Một dòng có thể biểu diễn khóa đã được cấp hoặc khóa đang chờ. Bảng này giúp trả lời: khóa thuộc schema, bảng và index nào; đó là khóa cấp bảng hay khóa bản ghi; chế độ khóa là gì; và transaction/thread nào yêu cầu khóa.

**data_lock_waits** mô tả quan hệ giữa khóa đang chờ và khóa đang ngăn nó được cấp. Mỗi dòng liên kết một khóa được yêu cầu với một khóa gây chặn. Một transaction có thể bị nhiều khóa hoặc nhiều transaction khác chặn, vì vậy kết quả có thể có nhiều dòng cho cùng một transaction đang chờ.

Có thể ghi nhớ vai trò của hai bảng như sau:

| Bảng | Câu hỏi chính | Dữ liệu cần chú ý |
|---|---|---|
| **performance_schema.data_locks** | Đang có những khóa nào? | Đối tượng, index, loại khóa, chế độ khóa, trạng thái, transaction và thread |
| **performance_schema.data_lock_waits** | Ai đang chờ ai? | ID khóa yêu cầu, ID khóa chặn, transaction ID và thread ID ở hai phía |

Hai bảng phản ánh trạng thái hiện tại. Nếu transaction được commit hoặc rollback trước khi truy vấn, quan hệ chờ có thể đã biến mất. Vì vậy, khi điều tra sự cố đang diễn ra, hãy chạy truy vấn ngay khi nhận được thông tin về hiện tượng chờ.

## 2. Điều kiện và quyền quan sát

Các truy vấn trong bài dùng giao diện Performance Schema của MySQL 8.0. Kiểm tra phiên bản và trạng thái Performance Schema trước:

~~~sql
SELECT
    VERSION() AS mysql_version,
    @@performance_schema AS performance_schema_enabled;
~~~

Nếu đang vận hành MySQL phiên bản cũ, hãy kiểm tra tài liệu đúng phiên bản trước khi dùng các bảng này; tên và giao diện chẩn đoán khóa đã thay đổi qua các đời MySQL. Trong MySQL 8.0, ưu tiên **data_locks** và **data_lock_waits** thay cho các bảng InnoDB lock cũ trong **INFORMATION_SCHEMA**.

Tài khoản giám sát cần quyền đọc các bảng Performance Schema liên quan. Để quan sát đầy đủ các phiên của người dùng khác, tài khoản thường cần thêm quyền **PROCESS** theo chính sách phân quyền của máy chủ. Nếu truy vấn không trả về phiên mà bạn biết đang tồn tại, hãy kiểm tra quyền trước khi kết luận rằng không có khóa.

Không nên cấp quyền quản trị rộng chỉ để tiện điều tra. Trong môi trường thật, hãy dùng tài khoản giám sát được phê duyệt, giới hạn quyền đọc theo nhu cầu và tránh đưa dữ liệu nhạy cảm từ **LOCK_DATA** hoặc câu SQL vào log công khai.

## 3. Đọc các khóa trong data_locks

Truy vấn dưới đây liệt kê các khóa của một schema. Thay **shop** bằng schema cần kiểm tra:

~~~sql
SELECT
    ENGINE,
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    EVENT_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    PARTITION_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = 'shop'
ORDER BY
    ENGINE_TRANSACTION_ID,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE;
~~~

Các cột thường cần đọc:

- **ENGINE**: storage engine sở hữu khóa; trong bài thực hành, ta quan tâm đến InnoDB.
- **ENGINE_TRANSACTION_ID**: mã transaction do engine cung cấp. Dùng nó để đối chiếu với transaction ID trong bảng chờ khóa.
- **THREAD_ID**: mã thread nội bộ của Performance Schema. Đây không phải connection ID mà ứng dụng dùng để kết nối.
- **OBJECT_SCHEMA**, **OBJECT_NAME**, **INDEX_NAME**: schema, bảng và index gắn với khóa.
- **LOCK_TYPE**: loại đối tượng khóa, thường gặp **TABLE** hoặc **RECORD**.
- **LOCK_MODE**: chế độ khóa. Ví dụ ở cấp bảng có thể gặp **IS** (intention shared) và **IX** (intention exclusive); ở cấp bản ghi có thể gặp **S**, **X** và các biến thể liên quan đến gap hoặc record.
- **LOCK_STATUS**: **GRANTED** nghĩa là khóa đã được cấp; **WAITING** nghĩa là yêu cầu khóa chưa được cấp.
- **LOCK_DATA**: dữ liệu gắn với khóa, nếu engine có thể cung cấp. Giá trị có thể là **NULL** trong một số trường hợp, chẳng hạn thông tin trang chưa sẵn trong buffer pool.

Không nên phân tích chuỗi **ENGINE_LOCK_ID** bằng cách tách các thành phần bên trong. Đây là định danh nội bộ của engine; hãy dùng nguyên giá trị để nối với **data_lock_waits**.

Khi đọc **LOCK_MODE**, đừng chỉ nhìn chữ **X** rồi kết luận câu lệnh đang cập nhật sai. Khóa ý định ở cấp bảng thường xuất hiện cùng khóa bản ghi trong hoạt động InnoDB bình thường. Cần xem **LOCK_TYPE**, **INDEX_NAME**, trạng thái và quan hệ chờ để hiểu đúng tình huống.

## 4. Tìm transaction đang chờ và transaction gây chặn

Truy vấn sau nối mỗi dòng trong **data_lock_waits** với hai dòng tương ứng trong **data_locks**: một dòng cho khóa đang được yêu cầu và một dòng cho khóa đang chặn. Nó cũng nối thread với **performance_schema.threads** để lấy thông tin connection ở cấp máy chủ.

~~~sql
SELECT
    w.ENGINE,
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
    wt.PROCESSLIST_ID AS waiting_connection_id,
    wt.PROCESSLIST_USER AS waiting_user,
    wt.PROCESSLIST_HOST AS waiting_host,
    wt.PROCESSLIST_COMMAND AS waiting_command,
    wt.PROCESSLIST_TIME AS waiting_command_seconds,
    wt.PROCESSLIST_STATE AS waiting_state,
    wt.PROCESSLIST_INFO AS waiting_sql,
    req.OBJECT_SCHEMA AS locked_schema,
    req.OBJECT_NAME AS locked_table,
    req.INDEX_NAME AS locked_index,
    req.LOCK_TYPE AS requested_lock_type,
    req.LOCK_MODE AS requested_lock_mode,
    req.LOCK_STATUS AS requested_lock_status,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
    bt.PROCESSLIST_ID AS blocking_connection_id,
    bt.PROCESSLIST_USER AS blocking_user,
    bt.PROCESSLIST_HOST AS blocking_host,
    bt.PROCESSLIST_COMMAND AS blocking_command,
    bt.PROCESSLIST_TIME AS blocking_command_seconds,
    bt.PROCESSLIST_STATE AS blocking_state,
    bt.PROCESSLIST_INFO AS blocking_sql,
    blk.LOCK_MODE AS blocking_lock_mode,
    blk.LOCK_STATUS AS blocking_lock_status
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
    ON req.ENGINE = w.ENGINE
   AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
    ON blk.ENGINE = w.ENGINE
   AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS wt
    ON wt.THREAD_ID = w.REQUESTING_THREAD_ID
LEFT JOIN performance_schema.threads AS bt
    ON bt.THREAD_ID = w.BLOCKING_THREAD_ID
ORDER BY
    waiting_connection_id,
    blocking_connection_id;
~~~

Cách đọc kết quả:

1. **waiting_connection_id** là connection ID của phiên đang chờ. Đây là ID có thể dùng với lệnh quản trị phiên sau khi đã xác minh đúng đối tượng.
2. **blocking_connection_id** là connection ID của phiên giữ khóa gây chặn.
3. **locked_schema**, **locked_table** và **locked_index** cho biết đối tượng tranh chấp.
4. **requested_lock_mode** là chế độ khóa mà phiên chờ cần; **blocking_lock_mode** là chế độ của khóa đang ngăn yêu cầu đó.
5. **waiting_sql** và **blocking_sql** là câu lệnh hiện tại mà Performance Schema ghi nhận cho hai thread, nếu có.

Điều kiện nối có cả **ENGINE** và **ENGINE_LOCK_ID**. Không nối hai phía chỉ bằng tên bảng hoặc transaction ID: một bảng có thể có nhiều khóa, và một transaction có thể giữ nhiều khóa cùng lúc.

**PROCESSLIST_ID** là connection ID ở cấp máy chủ; **THREAD_ID** là thread ID nội bộ của Performance Schema. Không tráo hai loại ID khi đối chiếu hoặc khi dùng lệnh KILL.

## 5. Xem tuổi transaction và trạng thái phiên

Thông tin trong **threads** cho biết phiên đang chạy câu lệnh nào. Tuy nhiên, câu SQL hiện tại không nhất thiết là câu lệnh đã lấy khóa. Một transaction có thể chạy UPDATE, sau đó chuyển sang trạng thái **Sleep** nhưng vẫn giữ khóa vì chưa COMMIT hoặc ROLLBACK.

Dùng **information_schema.innodb_trx** để xem tuổi transaction, thời điểm bắt đầu chờ và số dòng đang bị khóa:

~~~sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS trx_age_seconds,
    trx_wait_started,
    TIMESTAMPDIFF(SECOND, trx_wait_started, NOW()) AS lock_wait_seconds,
    trx_mysql_thread_id AS connection_id,
    trx_rows_locked,
    trx_rows_modified,
    trx_query
FROM information_schema.innodb_trx
ORDER BY trx_started;
~~~

Một số điểm cần phân biệt:

- **trx_started** giúp đánh giá transaction đã mở bao lâu. Transaction mở lâu có thể giữ khóa lâu, kể cả khi phiên không chạy câu SQL liên tục.
- **trx_wait_started** cho biết thời điểm transaction bắt đầu chờ khóa nếu transaction đang chờ.
- **trx_rows_locked** và **trx_rows_modified** hỗ trợ đánh giá phạm vi tác động; đây là số liệu tại thời điểm quan sát, không phải cam kết chính xác về số dòng ứng dụng dự định thay đổi.
- **trx_query** có thể là **NULL** nếu phiên đang rảnh giữa các câu lệnh trong một transaction mở.

Có thể lọc truy vấn theo các connection ID vừa tìm được:

~~~sql
SELECT
    t.PROCESSLIST_ID AS connection_id,
    t.PROCESSLIST_USER AS user_name,
    t.PROCESSLIST_HOST AS client_host,
    t.PROCESSLIST_DB AS current_schema,
    t.PROCESSLIST_COMMAND AS command_name,
    t.PROCESSLIST_TIME AS command_seconds,
    t.PROCESSLIST_STATE AS process_state,
    t.PROCESSLIST_INFO AS current_sql,
    it.trx_id,
    it.trx_state,
    it.trx_started,
    it.trx_rows_locked,
    it.trx_rows_modified,
    it.trx_query
FROM performance_schema.threads AS t
LEFT JOIN information_schema.innodb_trx AS it
    ON it.trx_mysql_thread_id = t.PROCESSLIST_ID
WHERE t.PROCESSLIST_ID IN (101, 102)
ORDER BY it.trx_started;
~~~

Thay **101** và **102** bằng connection ID lấy từ truy vấn quan hệ chờ. Truy vấn này giúp nhìn cả phiên không có transaction InnoDB đang hoạt động, vì vậy các cột từ **innodb_trx** có thể là **NULL**.

Đừng dùng riêng **PROCESSLIST_TIME** để kết luận tuổi transaction. Cột này mô tả thời gian của trạng thái/lệnh hiện tại trong process list; **trx_started** mới là mốc cần xem khi đánh giá transaction đã mở bao lâu.

## 6. Thực hành tái hiện một phiên gây chặn

Có thể quan sát trực tiếp bằng hai kết nối MySQL riêng biệt. Hãy thực hành trong schema thử nghiệm, không dùng bảng nghiệp vụ đang có dữ liệu thật.

Tạo bảng thử nghiệm và hai dòng dữ liệu:

~~~sql
CREATE TABLE IF NOT EXISTS lock_lab_accounts (
    id BIGINT NOT NULL PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

INSERT IGNORE INTO lock_lab_accounts (id, balance)
VALUES (1, 1000.00), (2, 1000.00);
~~~

**Kết nối A — lấy khóa và giữ transaction mở**

~~~sql
START TRANSACTION;

UPDATE lock_lab_accounts
SET balance = balance - 100.00
WHERE id = 1;

-- Giữ transaction mở để quan sát; chưa COMMIT hoặc ROLLBACK.
~~~

Câu UPDATE lấy khóa độc quyền trên bản ghi có **id = 1**. Vì transaction chưa kết thúc, khóa vẫn được giữ.

**Kết nối B — yêu cầu khóa trên cùng bản ghi**

~~~sql
START TRANSACTION;

UPDATE lock_lab_accounts
SET balance = balance + 50.00
WHERE id = 1;

-- Câu UPDATE sẽ phải chờ khóa do kết nối A đang giữ.
~~~

**Kết nối C — quan sát**

Chạy truy vấn ở mục 4. Kết quả sẽ cho thấy connection B là phía yêu cầu khóa và connection A là phía gây chặn. Đối tượng khóa là bản ghi trong **lock_lab_accounts** thông qua index chính. Chạy truy vấn ở mục 5 để kiểm tra tuổi transaction và trạng thái hai phiên.

Nếu kết nối A đang ở trạng thái **Sleep** và **blocking_sql** là **NULL**, điều đó không có nghĩa A đã nhả khóa. A vẫn có thể đang giữ transaction mở sau câu UPDATE trước đó. Hãy đối chiếu **blocking_connection_id**, **innodb_trx** và wait graph thay vì dựa vào câu SQL hiện tại.

**Kết thúc bài thực hành**

Trên kết nối A, kết thúc transaction:

~~~sql
COMMIT;
~~~

Ngay khi A commit, khóa được giải phóng và câu UPDATE đang chờ ở B có thể tiếp tục. Sau khi B hoàn tất, kết thúc transaction B:

~~~sql
COMMIT;
~~~

Nếu muốn hủy thay đổi trong bài thực hành, dùng ROLLBACK trên kết nối tương ứng thay cho COMMIT. Không để transaction thử nghiệm mở sau khi kết thúc.

## 7. Quy trình điều tra khi có blocking trong môi trường thật

Khi ứng dụng báo truy vấn chậm hoặc timeout, hãy đi theo trình tự sau để tránh xử lý nhầm phiên:

1. **Chụp trạng thái chờ hiện tại.** Chạy truy vấn data_lock_waits cùng hai lần nối data_locks. Ghi lại waiting transaction, blocking transaction, hai connection ID và đối tượng bị tranh chấp.
2. **Xác định phiên và transaction.** Đối chiếu connection ID với performance_schema.threads và information_schema.innodb_trx. Kiểm tra user, host, schema, câu SQL hiện tại, thời điểm bắt đầu transaction và số dòng bị khóa.
3. **Tìm nguyên nhân ở phía ứng dụng.** Kiểm tra transaction có đang chờ thao tác bên ngoài, gọi dịch vụ khác, chờ người dùng, hoặc quên commit/rollback hay không. Một transaction mở lâu có thể giữ khóa dù không có câu SQL đang chạy.
4. **Đánh giá phạm vi ảnh hưởng.** Xem có bao nhiêu phiên đang chờ, bảng/index nào bị tranh chấp và transaction gây chặn đã tồn tại bao lâu. Kiểm tra log ứng dụng để xác định thao tác nghiệp vụ tương ứng.
5. **Giải phóng bằng chủ sở hữu transaction khi có thể.** Nếu ứng dụng còn kiểm soát được phiên, để ứng dụng hoàn tất công việc rồi commit hoặc rollback theo đúng logic nghiệp vụ. Sau đó chạy lại truy vấn quan sát để xác nhận wait edge đã biến mất.
6. **Chỉ can thiệp phiên sau khi xác minh.** Nếu phải dừng phiên, xác nhận connection ID, chủ sở hữu, câu lệnh và tác động rollback với người chịu trách nhiệm vận hành trước khi thực hiện.

Có thể dùng KILL QUERY hoặc KILL CONNECTION khi quy trình vận hành cho phép:

~~~sql
-- Dừng câu lệnh hiện tại của connection 123.
KILL QUERY 123;

-- Đóng connection 123.
KILL CONNECTION 123;
~~~

Số **123** phải là **PROCESSLIST_ID** đã xác minh, không phải **THREAD_ID** hoặc transaction ID. KILL QUERY dừng câu lệnh đang chạy nhưng connection vẫn tồn tại; nếu transaction còn mở, các khóa do những câu lệnh trước đó lấy có thể vẫn được giữ. KILL CONNECTION đóng connection và khiến transaction InnoDB chưa commit phải rollback. Rollback có thể mất thời gian; khóa chỉ được giải phóng khi quá trình rollback thích hợp hoàn tất. Vì vậy, kill phiên không phải thao tác vô hại và không nên dùng chỉ vì thấy một connection ở trạng thái Sleep.

## 8. Những trường hợp dễ đọc sai kết quả

**Không có dòng trong data_lock_waits.** Đây chỉ là dấu hiệu không có quan hệ chờ khóa được ghi nhận tại thời điểm truy vấn. Có thể sự cố đã kết thúc, transaction vừa commit, hoặc truy vấn được chạy sau khi timeout. Nó không chứng minh rằng hệ thống chưa từng bị contention.

**Phiên gây chặn không có SQL hiện tại.** Một connection ở trạng thái Sleep vẫn có thể giữ khóa nếu transaction chưa kết thúc. Dùng transaction metadata và wait graph để xác minh.

**Nhiều dòng cho cùng một phiên chờ.** Một transaction có thể đang chờ nhiều khóa gây chặn. Đừng giả định chỉ có một blocker; hãy đọc từng cặp khóa trong data_lock_waits.

**Thấy khóa cấp bảng và cho rằng toàn bộ bảng bị khóa độc quyền.** Khóa ý định như IX thường phối hợp với khóa bản ghi. Hãy đọc đồng thời loại khóa, chế độ khóa, index và quan hệ chờ.

**Không tìm thấy tranh chấp trong data_locks nhưng DDL vẫn bị chờ.** Khóa dữ liệu InnoDB và metadata lock là hai cơ chế khác nhau. Khi nghi ngờ ALTER TABLE, DROP TABLE hoặc thao tác DDL đang chờ, kiểm tra thêm performance_schema.metadata_locks và các thread liên quan. data_locks không phải bảng tổng hợp mọi loại chờ trong MySQL.

**Dựa vào LOCK_DATA để nhận diện mọi bản ghi.** LOCK_DATA có thể không có giá trị hoặc không biểu diễn đầy đủ thông tin cần thiết. Hãy dùng schema, table, index, lock mode và transaction để phân tích; tránh đưa giá trị dữ liệu nhạy cảm vào báo cáo không được bảo vệ.

## 9. Checklist đọc một sự cố khóa

Khi nhận một báo cáo blocking, hãy bảo đảm đã trả lời được các câu hỏi sau:

- Transaction nào đang chờ và connection ID của nó là gì?
- Transaction nào đang giữ khóa gây chặn và connection ID của nó là gì?
- Schema, bảng, index và loại khóa nào đang tranh chấp?
- Khóa yêu cầu và khóa gây chặn có chế độ nào, trạng thái nào?
- Transaction gây chặn bắt đầu lúc nào; phiên đang chạy SQL hay đang Sleep?
- Có bao nhiêu transaction đang chờ cùng một blocker?
- Có phải metadata lock hoặc loại chờ khác thay vì data lock không?
- Ai sở hữu phiên và hành động commit, rollback hoặc dừng phiên nào được phép theo quy trình?

Khi trả lời được các câu hỏi này, bạn có thể giải thích hiện tượng chờ bằng bằng chứng từ MySQL thay vì chỉ suy đoán dựa trên một câu SQL chậm. Việc điều tra khóa cũng cung cấp đầu vào cho các bước tối ưu tiếp theo: xem lại thứ tự cập nhật giữa các transaction, rút ngắn thời gian giữ transaction, kiểm tra index và điều kiện lọc, đồng thời bảo đảm ứng dụng luôn kết thúc transaction trên mọi nhánh xử lý.

# Lock wait timeout và phạm vi rollback theo cấu hình

Khi một transaction cần khóa một hàng đang bị transaction khác giữ, InnoDB phải chờ. Nếu thời gian chờ vượt ngưỡng, MySQL trả lỗi lock wait timeout. Lỗi này không mặc định có nghĩa toàn bộ transaction đã bị hủy: với cấu hình mặc định, InnoDB chỉ rollback câu lệnh bị timeout, còn các thay đổi trước đó trong transaction vẫn có thể đang chờ commit.

Trong module DATABASE_MYSQL, hiểu đúng phạm vi rollback rất quan trọng để xử lý lỗi mà không vô tình commit một phần công việc. Bài này tập trung vào hai cấu hình InnoDB, sự khác nhau giữa row lock và metadata lock, cách tái hiện timeout bằng hai session, cùng quy trình rollback và retry an toàn.

## 1. Lock wait timeout xảy ra khi nào?

InnoDB sử dụng khóa để bảo vệ dữ liệu đang được transaction đọc hoặc thay đổi. Nếu transaction B muốn lấy một khóa không tương thích với khóa transaction A đang giữ, B phải chờ A giải phóng khóa bằng COMMIT hoặc ROLLBACK.

Ví dụ:

- Session A mở transaction và cập nhật tài khoản có account_id = 1.
- Session A chưa commit nên vẫn giữ khóa trên hàng đó.
- Session B cũng cập nhật account_id = 1.
- Session B phải đợi Session A.
- Nếu thời gian chờ vượt giới hạn, Session B nhận lỗi lock wait timeout.

Lock wait timeout thường được báo bằng lỗi MySQL 1205 (ER_LOCK_WAIT_TIMEOUT), với thông điệp “Lock wait timeout exceeded; try restarting transaction”. Đây là lỗi do hết thời gian chờ khóa, khác với deadlock.

Mã lỗi 1205 cũng có thể xuất hiện khi một thao tác chờ metadata lock vượt lock_wait_timeout. Vì vậy, hãy xác định loại lock đang chờ qua Performance Schema và ngữ cảnh câu lệnh; chỉ nhìn mã lỗi hoặc thông điệp chưa đủ để kết luận đó là InnoDB row lock.

Không phải mọi câu lệnh chờ đều là InnoDB row lock. MySQL còn có metadata lock (MDL), chẳng hạn DDL phải đợi transaction khác kết thúc trước khi thay đổi cấu trúc bảng. Cần xác định loại khóa trước khi điều chỉnh timeout.

## 2. Hai cấu hình cần phân biệt

| System variable | Phạm vi tác động | Ý nghĩa |
|---|---|---|
| innodb_lock_wait_timeout | InnoDB row lock | Số giây một transaction chờ khóa hàng InnoDB trước khi báo timeout |
| innodb_rollback_on_timeout | InnoDB transaction | Quyết định timeout rollback câu lệnh hiện tại hay toàn bộ transaction |
| lock_wait_timeout | Metadata lock | Thời gian chờ metadata lock, ví dụ khi DDL cần khóa metadata của bảng |

Ba biến này không thay thế cho nhau. Tăng innodb_lock_wait_timeout không xử lý được một DDL đang chờ metadata lock; thay đổi innodb_rollback_on_timeout cũng không quyết định thời gian chờ.

## 3. innodb_lock_wait_timeout: giới hạn thời gian chờ row lock

Biến innodb_lock_wait_timeout kiểm soát thời gian InnoDB chờ một row lock. Giá trị mặc định của MySQL là 50 giây nếu không bị cấu hình khác. Biến này có thể thay đổi động ở cấp GLOBAL hoặc SESSION.

Kiểm tra cấu hình:

~~~sql
SELECT
    @@GLOBAL.innodb_lock_wait_timeout AS global_timeout,
    @@SESSION.innodb_lock_wait_timeout AS session_timeout;
~~~

Đặt timeout 5 giây cho session hiện tại:

~~~sql
SET SESSION innodb_lock_wait_timeout = 5;
~~~

Đặt giá trị mặc định 10 giây cho các session mới:

~~~sql
SET GLOBAL innodb_lock_wait_timeout = 10;
~~~

Thay đổi GLOBAL không ghi đè giá trị SESSION đã được thiết lập trong các kết nối đang tồn tại. Với connection pool, cần thiết lập hoặc reset biến SESSION cho từng connection theo chính sách của ứng dụng.

Timeout ngắn giúp request thất bại sớm khi có tranh chấp, nhưng có thể làm các giao dịch hợp lệ thất bại nếu hệ thống thường xuyên giữ khóa lâu. Timeout dài hơn có thể giảm lỗi ở tải bình thường nhưng làm request treo lâu và che giấu transaction giữ khóa quá lâu. Điều chỉnh giá trị cần dựa trên latency mục tiêu, thời lượng transaction và dữ liệu quan sát.

Không xem việc tăng timeout là cách sửa gốc. Hãy tìm transaction đang giữ khóa, xác định vì sao nó chưa kết thúc và giảm phạm vi/thời gian giữ khóa.

## 4. innodb_rollback_on_timeout: quyết định phạm vi rollback

Đây là cấu hình quan trọng nhất của bài. Với cấu hình mặc định:

~~~ini
innodb_rollback_on_timeout = OFF
~~~

Khi InnoDB row lock wait timeout xảy ra, InnoDB chỉ rollback statement bị timeout. Trong bảng InnoDB, thay đổi của chính statement thất bại được hoàn tác như một đơn vị; các statement trước đó trong cùng transaction không tự động bị rollback. Transaction vẫn có thể còn mở và giữ các khóa đã lấy từ trước.

Nếu autocommit đang bật và câu lệnh chạy độc lập ngoài explicit transaction, statement đó thường chính là toàn bộ transaction; vì vậy statement rollback cũng đồng nghĩa transaction đơn câu lệnh không được commit. Khác biệt đáng chú ý nhất xuất hiện khi ứng dụng dùng START TRANSACTION hoặc tắt autocommit và thực hiện nhiều statement trước lỗi.

Nếu bật:

~~~ini
innodb_rollback_on_timeout = ON
~~~

InnoDB rollback toàn bộ transaction khi xảy ra lock wait timeout. Tất cả thay đổi chưa commit của transaction đó bị hủy.

Khác biệt này ảnh hưởng trực tiếp đến logic ứng dụng:

| Cấu hình | Khi statement bị lock wait timeout | Trạng thái các statement trước đó |
|---|---|---|
| OFF (mặc định) | Chỉ statement hiện tại bị rollback | Vẫn còn trong transaction; có thể được commit nếu ứng dụng tiếp tục COMMIT |
| ON | Toàn bộ transaction bị rollback | Các thay đổi chưa commit trước đó cũng bị hủy |

innodb_rollback_on_timeout là biến cấu hình cấp GLOBAL và không thay đổi động trong session. Cấu hình cần được đặt trong file option của MySQL hoặc tham số khởi động server, sau đó khởi động lại MySQL để áp dụng.

Với autocommit = 1, mỗi statement độc lập thường được thực thi như một transaction riêng. Khi statement đó timeout và bị rollback, không có các statement trước đó trong cùng transaction để giữ lại. Trong explicit transaction, ngược lại, các statement trước timeout có thể vẫn còn hiệu lực trong transaction khi biến này OFF.

Ví dụ trong file cấu hình:

~~~ini
[mysqld]
innodb_rollback_on_timeout = ON
~~~

Không thể dùng SET SESSION innodb_rollback_on_timeout = ON để thay đổi hành vi riêng cho một connection. Hãy kiểm tra tài liệu đúng phiên bản server và quy trình vận hành trước khi thay đổi cấu hình này trên môi trường production.

## 5. Ví dụ hai session: mặc định chỉ rollback statement

Tạo bảng thử nghiệm:

~~~sql
CREATE TABLE accounts (
    account_id INT NOT NULL,
    balance DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (account_id)
) ENGINE=InnoDB;

INSERT INTO accounts (account_id, balance)
VALUES (1, 1000.00), (2, 2000.00);
~~~

Mở hai kết nối MySQL độc lập.

**Session A — giữ khóa hàng thứ nhất**

~~~sql
START TRANSACTION;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1;

-- Tạm thời chưa COMMIT hoặc ROLLBACK.
~~~

Session A giữ khóa hàng account_id = 1 cho đến khi transaction kết thúc.

**Session B — thực hiện một statement trước, sau đó chờ khóa**

~~~sql
SET SESSION innodb_lock_wait_timeout = 5;

START TRANSACTION;

UPDATE accounts
SET balance = balance - 50.00
WHERE account_id = 2;

-- Câu lệnh này phải chờ Session A và sẽ timeout sau khoảng 5 giây.
UPDATE accounts
SET balance = balance + 50.00
WHERE account_id = 1;
~~~

Khi câu UPDATE cuối nhận lỗi 1205 và innodb_rollback_on_timeout đang OFF:

1. Câu UPDATE trên account_id = 1 bị rollback.
2. Câu UPDATE trước đó trên account_id = 2 vẫn nằm trong transaction B.
3. Transaction B vẫn chưa tự động kết thúc.
4. Nếu ứng dụng gọi COMMIT ngay sau lỗi, khoản giảm 50 trên account_id = 2 vẫn có thể được commit.

Vì vậy, trong ứng dụng nghiệp vụ, cách xử lý an toàn thường là ROLLBACK toàn bộ transaction sau lỗi timeout, trừ khi logic đã được thiết kế rõ ràng để tiếp tục từ trạng thái còn lại.

**Session B — kết thúc transaction**

~~~sql
ROLLBACK;
~~~

Sau đó Session A có thể giải phóng khóa:

~~~sql
COMMIT;
~~~

Ví dụ cho thấy lỗi của một statement không đồng nghĩa mọi thay đổi trước đó trong transaction đã bị hủy.

## 6. Lặp lại ví dụ với innodb_rollback_on_timeout = ON

Nếu server được khởi động với:

~~~ini
[mysqld]
innodb_rollback_on_timeout = ON
~~~

Hãy chạy lại thử nghiệm hai session. Session B thực hiện UPDATE account_id = 2 trước, sau đó UPDATE account_id = 1 và chờ đến timeout.

Khi timeout xảy ra:

- Statement đang chờ bị hủy.
- Toàn bộ transaction B bị rollback.
- Thay đổi trước đó trên account_id = 2 cũng bị hủy.
- Transaction B không còn giữ các khóa từ transaction đã rollback.

Không thể bật/tắt biến này bằng SET trong session để so sánh trực tiếp; cần thay cấu hình server và restart theo quy trình quản trị. Khi thử nghiệm, xác nhận giá trị cấu hình sau khi server khởi động:

~~~sql
SELECT @@GLOBAL.innodb_rollback_on_timeout;
~~~

Không chạy thử thay đổi cấu hình trên production chỉ để quan sát. Hãy dùng môi trường thử nghiệm và dữ liệu có thể khôi phục.

## 7. Lock wait timeout khác deadlock như thế nào?

Hai lỗi đều liên quan đến khóa nhưng cơ chế xử lý khác nhau:

| Tình huống | Lock wait timeout | Deadlock |
|---|---|---|
| Bản chất | Một transaction chờ khóa quá thời gian cấu hình | Các transaction tạo thành vòng chờ, không transaction nào tự tiến lên được |
| Phát hiện | Hết thời gian chờ | InnoDB phát hiện chu trình khóa khi deadlock detection hoạt động |
| Mã lỗi thường gặp | 1205 | 1213 (ER_LOCK_DEADLOCK) |
| Phạm vi rollback InnoDB | Phụ thuộc innodb_rollback_on_timeout | Transaction được chọn làm nạn nhân bị rollback toàn bộ |
| Xử lý ứng dụng | Thường rollback toàn bộ transaction rồi cân nhắc retry | Retry toàn bộ transaction đã bị rollback |

innodb_rollback_on_timeout không thay đổi quy tắc rollback của deadlock. Khi InnoDB phát hiện deadlock, nó chọn một transaction làm nạn nhân và rollback transaction đó để phá vòng chờ. Ứng dụng cần retry toàn bộ transaction với cùng idempotency key.

Nếu deadlock detector bị tắt hoặc không phát hiện được vòng chờ, timeout có thể là cơ chế cuối cùng giải phóng tình trạng chờ; không nên dựa vào điều đó để thiết kế transaction.

## 8. lock_wait_timeout: metadata lock có timeout riêng

Metadata lock bảo vệ metadata của đối tượng database như bảng, schema hoặc routine. Ví dụ, một transaction đang sử dụng bảng customers có thể giữ metadata lock đến khi transaction kết thúc; một câu ALTER TABLE trên cùng bảng phải chờ.

Biến lock_wait_timeout điều khiển thời gian chờ metadata lock. Nó khác innodb_lock_wait_timeout:

~~~sql
SELECT
    @@GLOBAL.lock_wait_timeout AS global_mdl_timeout,
    @@SESSION.lock_wait_timeout AS session_mdl_timeout;

-- Giới hạn thời gian chờ MDL của session hiện tại.
SET SESSION lock_wait_timeout = 60;
~~~

Giá trị mặc định của lock_wait_timeout trong MySQL thường rất dài (31.536.000 giây). Với một phiên DDL cần giới hạn thời gian chờ, có thể đặt SESSION timeout phù hợp trước khi chạy câu lệnh. Thay đổi này không làm thay đổi timeout row lock của InnoDB.

Một dấu hiệu điển hình:

- Một session mở transaction, SELECT hoặc UPDATE bảng rồi để transaction chưa kết thúc.
- Session khác chạy ALTER TABLE trên cùng bảng.
- ALTER TABLE chờ metadata lock, dù không nhất thiết có row lock conflict.
- Khi vượt lock_wait_timeout, câu lệnh DDL báo timeout.

Để chẩn đoán MDL, xem performance_schema.metadata_locks và process list. Không tăng innodb_lock_wait_timeout để xử lý loại chờ này.

## 9. Tại sao transaction có thể giữ khóa lâu?

Lock wait timeout thường là triệu chứng của một transaction giữ khóa lâu hoặc các transaction tranh chấp cùng vùng dữ liệu. Những nguyên nhân phổ biến:

- Ứng dụng mở transaction rồi thực hiện gọi HTTP, đọc file hoặc chờ người dùng trước khi commit.
- Một transaction cập nhật nhiều hàng nhưng xử lý theo thứ tự khác nhau giữa các worker.
- Câu UPDATE/DELETE quét quá nhiều hàng do thiếu index phù hợp.
- Một truy vấn phạm vi tạo next-key lock hoặc gap lock theo isolation level và access path.
- Batch lớn giữ khóa trong thời gian dài.
- Kết nối bị bỏ quên trong connection pool khi transaction chưa kết thúc.
- DDL phải đợi transaction cũ nhả metadata lock.

Một transaction nên làm phần công việc bên ngoài database trước khi mở transaction nếu có thể. Sau khi START TRANSACTION, chỉ thực hiện các câu SQL cần nằm trong cùng đơn vị nguyên tử; commit hoặc rollback sớm.

Index không chỉ ảnh hưởng tốc độ đọc. Với UPDATE/DELETE, index phù hợp giúp InnoDB tìm đúng hàng nhanh hơn và giảm số bản ghi cần khóa. Tuy nhiên, index mới cũng có chi phí ghi và không đảm bảo mọi range lock biến mất.

## 10. Chẩn đoán row lock đang chờ

Khi gặp lỗi, cần xác định:

1. Transaction nào đang chờ?
2. Transaction nào đang giữ khóa?
3. Bảng, index và hàng nào liên quan?
4. Transaction giữ khóa bắt đầu từ khi nào?
5. Câu SQL nào đã lấy khóa và vì sao transaction chưa kết thúc?

Trên MySQL 8.0, Performance Schema cung cấp data_locks và data_lock_waits. Có thể dùng view tiện ích của schema sys:

~~~sql
SELECT *
FROM sys.innodb_lock_waits;
~~~

View này có thể hiển thị session đang chờ, session chặn, thời gian chờ, bảng/index và câu SQL liên quan. Cần quyền đọc Performance Schema/sys và view có thể không tồn tại hoặc khác nhau trên một số bản phân phối.

Truy vấn trực tiếp Performance Schema:

~~~sql
SELECT
    w.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx_id,
    wt.PROCESSLIST_ID AS waiting_connection_id,
    w.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx_id,
    bt.PROCESSLIST_ID AS blocking_connection_id,
    dl.OBJECT_SCHEMA,
    dl.OBJECT_NAME,
    dl.INDEX_NAME,
    dl.LOCK_TYPE,
    dl.LOCK_MODE,
    dl.LOCK_DATA
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS dl
  ON dl.ENGINE = w.ENGINE
 AND dl.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
LEFT JOIN performance_schema.threads AS wt
  ON wt.THREAD_ID = w.REQUESTING_THREAD_ID
LEFT JOIN performance_schema.threads AS bt
  ON bt.THREAD_ID = w.BLOCKING_THREAD_ID;
~~~

Kiểm tra thêm transaction và câu lệnh đang chạy:

~~~sql
SHOW FULL PROCESSLIST;
SHOW ENGINE INNODB STATUS;
~~~

SHOW ENGINE INNODB STATUS cung cấp trạng thái InnoDB và thông tin deadlock gần nhất; nó không thay thế bảng theo dõi wait hiện tại. Không chỉ nhìn câu query đang chờ mà bỏ qua transaction blocker: blocker có thể đang ở trạng thái Sleep nhưng vẫn giữ transaction chưa commit.

## 11. Chẩn đoán metadata lock

Nếu nghi ngờ DDL chờ metadata lock, xem Performance Schema:

~~~sql
SELECT
    OBJECT_TYPE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE LOCK_STATUS = 'PENDING'
   OR OBJECT_NAME = 'customers';
~~~

Có thể nối OWNER_THREAD_ID với performance_schema.threads để tìm connection ID và process list. Một số view trong sys schema như schema_table_lock_waits cũng hỗ trợ truy vấn blocker/waiter dễ đọc hơn.

Khi DDL bị chặn:

- Tìm transaction đang giữ metadata lock trên đối tượng.
- Xác định session đó có còn cần transaction không.
- Yêu cầu ứng dụng kết thúc transaction đúng cách hoặc xử lý theo quy trình vận hành.
- Chỉ kill connection sau khi đánh giá tác động rollback và được phép theo quy trình.
- Đặt lock_wait_timeout hợp lý cho session DDL để không chờ vô hạn.

Không kill session blocker một cách tự động chỉ vì nó đang chặn DDL. Rollback transaction dài có thể tạo tải lớn và ảnh hưởng nghiệp vụ.

## 12. Quy trình ứng dụng nên xử lý lỗi 1205

Khi một câu lệnh trong transaction nhận lock wait timeout, ứng dụng nên:

1. Ghi log mã lỗi, batch/request ID, connection ID, câu lệnh hoặc operation, thời gian chờ và transaction context.
2. Nếu connection còn hoạt động, ROLLBACK toàn bộ transaction để đưa session về trạng thái sạch.
3. Không trả connection về pool khi chưa chắc transaction đã kết thúc.
4. Chờ một khoảng backoff có jitter ngoài transaction.
5. Nếu nghiệp vụ cho phép, retry toàn bộ transaction từ đầu bằng cùng idempotency key.
6. Giới hạn số lần retry; nếu tiếp tục thất bại, trả lỗi có thể xử lý và phát cảnh báo.

Ví dụ pseudocode:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    begin transaction
    try:
        execute all business statements
        commit
        return success
    catch lock_wait_timeout or deadlock:
        rollback transaction
        if attempt == MAX_ATTEMPTS:
            raise retryable database error
        sleep(exponential_backoff_with_jitter(attempt))
~~~

Đây là pseudocode, không phải cú pháp SQL. Việc retry cần được đặt ở tầng quản lý transaction để chắc chắn mọi statement trong đơn vị nghiệp vụ được thực hiện lại cùng nhau.

Nếu innodb_rollback_on_timeout đang OFF, rollback tường minh đặc biệt quan trọng vì transaction có thể còn chứa các thay đổi trước statement bị timeout. Nếu biến đang ON, vẫn nên xử lý trạng thái transaction rõ ràng và không giả định ứng dụng có thể tiếp tục câu lệnh tiếp theo.

## 13. Không nên làm gì khi gặp timeout?

| Cách xử lý sai | Vì sao nguy hiểm | Cách làm phù hợp |
|---|---|---|
| Bắt lỗi 1205 rồi COMMIT ngay | Có thể commit statement trước đó khi cấu hình rollback chỉ statement | ROLLBACK toàn bộ transaction rồi retry có kiểm soát |
| Tăng timeout rất lớn ngay lập tức | Làm request chờ lâu hơn và che transaction giữ khóa | Tìm blocker, thời lượng transaction và access path |
| Chỉ retry statement thất bại | Các statement trước đó có thể còn trong transaction; nghiệp vụ có thể mất tính nguyên tử | Retry toàn bộ transaction sau rollback |
| Kill blocker mà chưa điều tra | Có thể hủy giao dịch hợp lệ hoặc tạo rollback lớn | Xác minh owner, tuổi transaction và tác động trước khi can thiệp |
| Nhầm MDL với row lock | Sửa nhầm biến timeout và không giải quyết nguyên nhân | Kiểm tra data_lock_waits và metadata_locks |
| Trả connection lỗi về pool | Connection có thể còn transaction và giữ khóa | Rollback/reset connection trước khi trả pool |
| Retry vô hạn, không backoff | Tạo retry storm và tăng tranh chấp | Giới hạn lần thử, backoff và jitter |

## 14. Giảm khả năng xảy ra lock wait timeout

- Giữ transaction ngắn; không gọi dịch vụ ngoài hoặc chờ input trong lúc đang giữ khóa.
- Cập nhật các hàng theo thứ tự nhất quán giữa các transaction, ví dụ luôn theo account_id tăng dần.
- Tạo index phù hợp cho điều kiện WHERE và JOIN của UPDATE/DELETE.
- Chia batch lớn thành chunk có kích thước phù hợp, commit từng đơn vị đã được thiết kế idempotent.
- Tránh đọc rồi mới ghi nếu có thể dùng UPDATE có điều kiện hoặc khóa hàng rõ ràng.
- Dùng SELECT ... FOR UPDATE khi cần đọc rồi cập nhật một hàng trong cùng transaction, nhưng chỉ khóa các hàng cần thiết và kết thúc transaction nhanh.
- Không giữ transaction mở sau khi xử lý xong dữ liệu chỉ vì ứng dụng chưa đóng connection.
- Theo dõi transaction lâu, lock wait, deadlock và tỷ lệ lỗi theo thời gian.

Ví dụ khóa một hàng trước khi kiểm tra số dư:

~~~sql
START TRANSACTION;

SELECT balance
FROM accounts
WHERE account_id = 1
FOR UPDATE;

-- Ứng dụng kiểm tra số dư và thực hiện cập nhật cần thiết.
UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;

COMMIT;
~~~

SELECT ... FOR UPDATE lấy khóa độc quyền phù hợp trên hàng được đọc trong transaction. Cần kiểm tra số hàng bị ảnh hưởng của UPDATE; nếu không đủ số dư hoặc không tìm thấy tài khoản, rollback theo quy tắc nghiệp vụ. Không giữ khóa trong lúc ứng dụng thực hiện thao tác mạng hoặc công việc không liên quan.

## 15. Kiểm tra cấu hình và trạng thái transaction

Trước khi điều tra, ghi nhận giá trị các biến liên quan:

~~~sql
SELECT
    @@GLOBAL.innodb_lock_wait_timeout,
    @@SESSION.innodb_lock_wait_timeout,
    @@GLOBAL.innodb_rollback_on_timeout,
    @@GLOBAL.lock_wait_timeout,
    @@SESSION.autocommit,
    @@SESSION.transaction_isolation;
~~~

transaction_isolation có thể hiển thị khác tùy phiên bản MySQL; trên các phiên bản cũ hơn, biến tương ứng có thể mang tên tx_isolation. Nếu truy vấn một biến không tồn tại, kiểm tra phiên bản server và dùng tên được hỗ trợ.

Khi gặp timeout trong explicit transaction, đừng suy luận transaction đã kết thúc chỉ từ thông báo lỗi. Với cấu hình mặc định, kiểm tra trạng thái và chủ động ROLLBACK. Trong ứng dụng, luôn có nhánh cleanup transaction khi statement thất bại.

## 16. Checklist vận hành

1. Xác định timeout thuộc InnoDB row lock hay metadata lock.
2. Ghi lại innodb_lock_wait_timeout và innodb_rollback_on_timeout.
3. Kiểm tra lock_wait_timeout nếu DDL hoặc thao tác metadata đang chờ.
4. Xác định waiting transaction và blocking transaction.
5. Kiểm tra transaction blocker bắt đầu lúc nào, đã sửa những hàng nào và vì sao chưa kết thúc.
6. Phân biệt lỗi 1205 với deadlock 1213.
7. Sau timeout, rollback toàn bộ transaction ở tầng ứng dụng nếu nghiệp vụ cần tính nguyên tử.
8. Chỉ retry sau rollback, có backoff, jitter và giới hạn số lần.
9. Đảm bảo retry idempotent và không lặp side effect ngoài database.
10. Điều chỉnh timeout dựa trên số liệu, không dùng timeout dài để che lỗi thiết kế.
11. Nếu thay đổi innodb_rollback_on_timeout, đánh giá phạm vi ảnh hưởng toàn server và kế hoạch restart.
12. Sau thay đổi, xác minh cấu hình thực tế và theo dõi tỷ lệ timeout/deadlock.

## 17. Bài tập thực hành

1. Tạo bảng accounts và chạy thử hai session theo ví dụ; xác nhận Session B nhận lỗi 1205.
2. Với innodb_rollback_on_timeout mặc định OFF, cập nhật một hàng không bị khóa trước, sau đó chờ khóa hàng bị Session A giữ; quan sát thay đổi đầu tiên vẫn còn trong transaction.
3. Sau timeout, chạy ROLLBACK ở Session B và xác nhận thay đổi trước đó không được commit.
4. Trong môi trường thử nghiệm, bật innodb_rollback_on_timeout ở cấu hình server, restart và chạy lại; xác nhận toàn bộ transaction B bị rollback.
5. Thử SET SESSION innodb_lock_wait_timeout với các giá trị khác nhau; quan sát thời gian chờ và ảnh hưởng đến request.
6. Tạo một transaction giữ metadata lock, chạy ALTER TABLE ở session khác và quan sát lock_wait_timeout.
7. Dùng sys.innodb_lock_waits hoặc performance_schema.data_lock_waits để xác định blocker của row lock.
8. Dùng performance_schema.metadata_locks để xác định session giữ hoặc chờ MDL.
9. Tạo hai transaction cập nhật hai hàng theo thứ tự ngược nhau để quan sát deadlock; phân biệt lỗi 1213 với 1205.
10. Viết logic xử lý lỗi ở tầng ứng dụng: rollback toàn transaction, backoff và retry bằng cùng idempotency key.

Bạn hoàn thành bài khi giải thích được vì sao timeout mặc định chỉ rollback statement, biết cách innodb_rollback_on_timeout thay đổi phạm vi rollback, phân biệt row lock với metadata lock và deadlock, đồng thời xây dựng được quy trình rollback/retry không commit nhầm các thay đổi còn dang dở.

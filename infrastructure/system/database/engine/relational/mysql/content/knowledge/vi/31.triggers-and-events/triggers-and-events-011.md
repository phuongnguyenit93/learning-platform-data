# Theo dõi event thất bại và thiết kế công việc có thể thực hiện lại

Bài học thuộc chương **Trigger và event** của module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Event Scheduler giúp chạy công việc theo lịch ngay trong MySQL, nhưng metadata của event không phải lịch sử thực thi đầy đủ và một lần chạy lỗi không tự trở thành một giao dịch có thể phát lại an toàn. Muốn vận hành ổn định, cần kết hợp error log, metadata, bảng trạng thái công việc, khóa chống chạy trùng, idempotency, retry có backoff và quy trình phục hồi.

Sau bài này, bạn có thể kiểm tra Event Scheduler có thực sự chạy hay không, phát hiện event lỗi qua error log, phân biệt STATUS với kết quả nghiệp vụ, đọc INFORMATION_SCHEMA.EVENTS, xác minh DEFINER và quyền thực thi, ngăn các lần chạy chồng lấn, thiết kế run key duy nhất, lưu attempt/error/next_retry_at, rollback phần công việc thất bại, phát lại an toàn và xử lý tác vụ vượt quá số lần retry.

## 1. Event Scheduler không phải hệ thống hàng đợi công việc hoàn chỉnh

MySQL Event Scheduler thực thi câu lệnh SQL theo lịch. Một event có thể chạy một lần hoặc lặp lại:

~~~sql
CREATE EVENT ev_cleanup_sessions
ON SCHEDULE EVERY 1 HOUR
DO
    DELETE FROM sessions
    WHERE expires_at < CURRENT_TIMESTAMP;
~~~

Event Scheduler phù hợp với các công việc như:

- Dọn dữ liệu hết hạn.
- Tổng hợp báo cáo theo ngày.
- Kiểm tra và đánh dấu dữ liệu quá hạn.
- Tạo snapshot định kỳ.
- Gọi stored procedure xử lý một lô công việc.

Tuy nhiên, bản thân event không cung cấp đầy đủ các chức năng của một job queue:

- Không lưu lịch sử nghiệp vụ chi tiết cho từng lần chạy.
- Không lưu checkpoint cho từng bản ghi đã xử lý.
- Không có chính sách retry/backoff theo nghiệp vụ được cấu hình sẵn cho mỗi lần chạy.
- Không bảo đảm một event lặp lại không bao giờ chạy chồng lấn.
- Không tự làm cho câu lệnh trong event idempotent.
- Không biết một thao tác gửi email, gọi HTTP hoặc ghi sang hệ thống khác đã hoàn tất hay chưa.

Event Scheduler là bộ kích hoạt theo lịch. Trạng thái và lịch sử công việc nên được lưu trong các bảng do ứng dụng thiết kế.

Khi một lần chạy của event lặp bị lỗi, Event Scheduler ghi diagnostics vào error log; nó không biến lần chạy lỗi đó thành một mục retry có backoff để tự phát lại ngay. Lần kích hoạt tiếp theo vẫn theo lịch event. Muốn retry cùng một logical run, procedure phải nhận diện run key cũ và kiểm tra next_retry_at/status trong bảng công việc.

Một kiến trúc thực tế:

~~~text
Event Scheduler
      |
      v
Stored procedure / Job dispatcher
      |
      +----> Job run table
      |        - run key
      |        - status
      |        - attempts
      |        - next retry
      |        - last error
      |
      +----> Transaction xử lý nghiệp vụ
      |        - summary
      |        - ledger
      |        - checkpoint
      |
      +----> Outbox table
               - message key
               - payload
               - delivery status
~~~

Khi event lỗi, error log giúp tìm nguyên nhân kỹ thuật. Job run table giúp biết công việc nghiệp vụ nào chưa hoàn thành và có thể phát lại từ đâu.

## 2. Kiểm tra Event Scheduler có đang hoạt động

Biến toàn cục event_scheduler quyết định Event Scheduler có được bật hay không.

~~~sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';
~~~

Các giá trị có ý nghĩa:

| Giá trị | Ý nghĩa |
|---|---|
| ON | Scheduler được bật và thread scheduler chạy |
| OFF | Scheduler hiện không chạy; có thể bật/tắt khi server đang chạy nếu có quyền |
| DISABLED | Scheduler bị vô hiệu hóa từ lúc khởi động; không thể bật lại chỉ bằng SET GLOBAL trong runtime |

Bật scheduler khi giá trị đang OFF:

~~~sql
SET GLOBAL event_scheduler = ON;
~~~

Lệnh này yêu cầu quyền đủ để thay đổi system variable toàn cục. Để trạng thái được giữ sau khi restart, cấu hình trong file cấu hình server, ví dụ my.cnf hoặc my.ini:

~~~ini
[mysqld]
event_scheduler=ON
~~~

Nếu server khởi động với event_scheduler=DISABLED, phải sửa cấu hình khởi động và restart theo quy trình vận hành.

### Kiểm tra scheduler thread

~~~sql
SHOW PROCESSLIST;
~~~

Khi scheduler chạy, danh sách process có thread daemon của Event Scheduler. Người dùng cần quyền PROCESS để xem đầy đủ process của server.

Có thể xem trạng thái cùng các thông tin tổng quát khác bằng lệnh quản trị:

~~~text
mysqladmin debug
~~~

Lệnh này ghi thông tin debug của Event Scheduler vào error log. Chỉ dùng khi cần chẩn đoán sâu và có quyền quản trị phù hợp.

Không kết luận scheduler hoạt động chỉ vì biến event_scheduler có giá trị ON. Cần kiểm tra thread, lịch event, error log và kết quả nghiệp vụ.

## 3. Đọc metadata event trong INFORMATION_SCHEMA.EVENTS

INFORMATION_SCHEMA.EVENTS cung cấp metadata của các event đã định nghĩa.

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STATUS,
    LAST_EXECUTED,
    LAST_ALTERED,
    ON_COMPLETION,
    EVENT_COMMENT
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = DATABASE()
ORDER BY EVENT_NAME;
~~~

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| EVENT_SCHEMA | Schema chứa event |
| EVENT_NAME | Tên event |
| DEFINER | Tài khoản mà event sử dụng khi thực thi |
| TIME_ZONE | Múi giờ dùng cho lịch và session thực thi event |
| EVENT_TYPE | ONE TIME hoặc RECURRING |
| EXECUTE_AT | Thời điểm của event chạy một lần |
| INTERVAL_VALUE / INTERVAL_FIELD | Chu kỳ của event lặp |
| STARTS / ENDS | Khoảng thời gian bắt đầu và kết thúc lịch |
| STATUS | ENABLED, DISABLED hoặc REPLICA_SIDE_DISABLED |
| LAST_EXECUTED | Thời điểm event bắt đầu thực thi gần nhất |
| LAST_ALTERED | Thời điểm định nghĩa event được sửa gần nhất |
| ON_COMPLETION | PRESERVE hoặc NOT PRESERVE |
| EVENT_COMMENT | Ghi chú của event |

### STATUS không phải trạng thái thành công

STATUS chỉ mô tả event có được bật để scheduler thực thi hay không. Nó không nói rằng câu lệnh trong event đã chạy thành công.

Ví dụ:

- ENABLED: event được bật, nhưng có thể lỗi vì DEFINER thiếu quyền.
- DISABLED: event bị tắt; scheduler không thực thi nó.
- REPLICA_SIDE_DISABLED: event được sao chép từ source sang replica nhưng không chạy trên replica theo cơ chế replication của MySQL.

LAST_EXECUTED cũng không phải thời điểm hoàn thành. Trường này biểu thị thời điểm event bắt đầu thực thi. Nó không lưu thời lượng, số hàng xử lý, SQLSTATE hoặc kết quả nghiệp vụ.

Nếu LAST_EXECUTED là NULL, event chưa có lần thực thi được ghi nhận. Khi event đang ENABLED nhưng không có lần chạy, cần kiểm tra event_scheduler, STARTS/ENDS, múi giờ, DEFINER và error log.

Để xem định nghĩa đầy đủ:

~~~sql
SHOW CREATE EVENT ev_cleanup_sessions;
~~~

Để liệt kê event:

~~~sql
SHOW EVENTS FROM app_db;
~~~

Không dùng riêng LAST_EXECUTED hoặc STATUS làm dashboard thành công/thất bại. Hãy lưu trạng thái công việc vào bảng riêng.

## 4. Event thất bại được ghi vào đâu?

MySQL Event Scheduler ghi thông tin về event execution kết thúc với error hoặc warning vào MySQL Server error log.

Một thông báo có thể có dạng:

~~~text
[ERROR] Event Scheduler: [job_runner@localhost][app_db.ev_daily_report]
INSERT command denied to user ...
[Note] Event Scheduler: [app_db.ev_daily_report] event execution failed.
~~~

Error log là nơi đầu tiên cần kiểm tra khi event được bật nhưng không tạo ra kết quả.

### Đọc error log qua Performance Schema

Trong MySQL 9.7, nếu error log sink được cấu hình hỗ trợ Performance Schema, có thể đọc các thông báo gần đây qua performance_schema.error_log.

~~~sql
SELECT
    LOGGED,
    THREAD_ID,
    PRIO,
    ERROR_CODE,
    SUBSYSTEM,
    DATA
FROM performance_schema.error_log
WHERE DATA LIKE '%Event Scheduler%'
   OR DATA LIKE '%event execution failed%'
ORDER BY LOGGED DESC
LIMIT 100;
~~~

Các cột thường dùng:

- LOGGED: thời điểm ghi thông báo.
- THREAD_ID: thread ghi log; với background thread, giá trị có thể là 0.
- PRIO: System, Error, Warning hoặc Note.
- ERROR_CODE: mã lỗi server.
- SUBSYSTEM: subsystem phát sinh thông báo.
- DATA: nội dung thông báo.

performance_schema.error_log là view trên một ring buffer có kích thước cố định trong bộ nhớ. Khi buffer đầy, thông báo cũ bị loại bỏ để chứa thông báo mới. Nó không thay thế hệ thống lưu trữ log dài hạn.

### Nếu error_log không có dữ liệu

Không phải cấu hình error log nào cũng ghi sự kiện vào Performance Schema. Các sink truyền thống và JSON có hỗ trợ khả năng này, nhưng log_error_services quyết định sink nào đang hoạt động.

Kiểm tra:

~~~sql
SHOW GLOBAL VARIABLES LIKE 'log_error_services';
SHOW GLOBAL VARIABLES LIKE 'log_error';
~~~

Nếu error_log không có dữ liệu, đọc file error log trên host hoặc hệ thống thu thập log tập trung theo quy trình của tổ chức. Không yêu cầu ứng dụng có quyền FILE chỉ để đọc error log.

### Cảnh báo cũng có thể được ghi

Event Scheduler ghi cả diagnostics dạng warning. Ví dụ SELECT ... INTO không trả hàng có thể phát cảnh báo No data; nếu trả nhiều hơn một hàng thì phát lỗi Result consisted of more than one row.

Với event chạy thường xuyên, warning không được xử lý có thể tạo nhiều log gây nhiễu.

Ví dụ xử lý NOT FOUND trong stored program:

~~~sql
DECLARE v_value BIGINT DEFAULT NULL;
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_value = NULL;

SELECT id
INTO v_value
FROM source_queue
WHERE status = 'READY'
ORDER BY id
LIMIT 1;
~~~

Nếu nghiệp vụ chỉ cần một hàng, LIMIT 1 và điều kiện sắp xếp rõ ràng giúp tránh lỗi nhiều hàng. Nếu cần phát hiện trường hợp không có dữ liệu, xử lý NOT FOUND một cách tường minh.

Không che giấu warning quan trọng bằng handler tổng quát. Chỉ xử lý các điều kiện đã hiểu và có hành vi nghiệp vụ rõ ràng.

## 5. Kiểm tra DEFINER và quyền thực thi

Một event có thể được CREATE EVENT thành công nhưng câu lệnh trong DO thất bại khi scheduler chạy.

Nguyên nhân thường gặp:

- Tài khoản DEFINER không có SELECT, INSERT, UPDATE hoặc DELETE cần thiết.
- DEFINER đã bị xóa hoặc đổi.
- Stored procedure được event gọi có DEFINER hoặc SQL SECURITY khác với dự kiến.
- Routine phụ thuộc bảng, schema hoặc quyền đã thay đổi.
- Event chạy trong schema hoặc múi giờ không như người vận hành giả định.

Kiểm tra:

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    STATUS,
    EVENT_DEFINITION
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'app_db';
~~~

Xem định nghĩa:

~~~sql
SHOW CREATE EVENT app_db.ev_daily_report;
~~~

Kiểm tra quyền của tài khoản DEFINER bằng tài khoản quản trị:

~~~sql
SHOW GRANTS FOR 'job_runner'@'localhost';
~~~

### Hai lớp quyền cần phân biệt

- EVENT privilege cho phép tạo, sửa, xóa và hiển thị event trong phạm vi schema hoặc global.
- Quyền thực hiện câu lệnh trong event phải có sẵn cho tài khoản thực thi theo DEFINER.
- Nếu event gọi stored procedure, cần kiểm tra thêm quyền EXECUTE và security context của procedure.
- Bật/tắt event_scheduler là thay đổi system variable toàn cục, cần quyền quản trị biến tương ứng.

Ví dụ cấp quyền quản lý event ở một schema:

~~~sql
GRANT EVENT ON app_db.* TO 'scheduler_admin'@'localhost';
~~~

Không cấp quyền rộng hơn mức cần thiết cho tài khoản job. Nên dùng tài khoản DEFINER chuyên dụng, có quyền tối thiểu trên đúng bảng và routine cần xử lý.

Tài khoản DEFINER bị xóa có thể làm stored object trở thành orphaned. Trước khi xóa hoặc đổi tài khoản, cần rà soát các event, routine, trigger và view đang tham chiếu tài khoản đó.

## 6. Múi giờ và lịch chạy

Thời điểm trong event được diễn giải theo session time_zone tại thời điểm CREATE EVENT hoặc ALTER EVENT. Múi giờ đó trở thành TIME_ZONE của event và có hiệu lực trong session thực thi event.

Kiểm tra:

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    TIME_ZONE,
    STARTS,
    ENDS,
    EXECUTE_AT,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = DATABASE();
~~~

Nếu báo cáo theo ngày nghiệp vụ Việt Nam, cần thống nhất Asia/Ho_Chi_Minh thay vì trộn UTC và giờ local.

Ví dụ thiết lập session trước khi tạo event:

~~~sql
SET time_zone = 'Asia/Ho_Chi_Minh';

CREATE EVENT ev_daily_report_retry
ON SCHEDULE EVERY 5 MINUTE
STARTS CURRENT_TIMESTAMP + INTERVAL 1 MINUTE
DO
    CALL app_db.sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Tên múi giờ cần có trong timezone tables của MySQL. Nếu chưa nạp timezone tables, có thể dùng offset cố định nhưng cần cân nhắc quy tắc thay đổi giờ của môi trường.

Không giả định thời điểm trong CREATE EVENT được diễn giải theo múi giờ của máy client. Hãy kiểm tra TIME_ZONE sau khi tạo event.

## 7. Event Scheduler có thể tạo các lần chạy chồng lấn

Nếu một event lặp lại mỗi 5 phút nhưng mỗi lần chạy mất 8 phút, nhiều instance có thể chạy đồng thời.

Ví dụ:

~~~text
12:00  Instance A bắt đầu
12:05  Instance B bắt đầu trong khi A chưa xong
12:08  Instance A hoàn tất
12:10  Instance C có thể bắt đầu trong khi B chưa xong
~~~

Điều này có thể gây:

- Cùng một kỳ báo cáo bị tính hai lần.
- Hai worker cùng lấy một hàng queue.
- Hai transaction cập nhật cùng một aggregate.
- Gửi thông báo trùng.
- Tăng lock wait và deadlock.
- Tài nguyên CPU/I/O bị dồn tải.

MySQL khuyến nghị dùng cơ chế ngăn chạy đồng thời nếu event có thể vượt quá chu kỳ lịch. Có thể dùng GET_LOCK(), row lock hoặc table lock.

### Dùng named lock cho một công việc đơn

~~~sql
SELECT GET_LOCK('app_db.daily_sales_refresh', 0);
~~~

Kết quả:

- 1: lấy được lock.
- 0: lock đang do session khác giữ hoặc không lấy được trong timeout.
- NULL: có lỗi khi thực hiện.

Khi lấy được lock, thực hiện công việc rồi giải phóng:

~~~sql
SELECT RELEASE_LOCK('app_db.daily_sales_refresh');
~~~

Named lock thuộc về session, không thuộc transaction. COMMIT hoặc ROLLBACK không tự giải phóng named lock. Phải RELEASE_LOCK hoặc đóng connection.

Nếu procedure có lỗi, cần handler bảo đảm release lock trước khi RESIGNAL. Nếu connection bị đóng, MySQL giải phóng named lock của session đó.

GET_LOCK chỉ điều phối trong cùng MySQL server. Không coi nó là khóa phân tán xuyên nhiều server hoặc thay thế cơ chế leader trong kiến trúc nhiều primary.

### Dùng row lock theo run key

Với công việc theo ngày, một hàng trong job_run có khóa chính (job_name, run_date). Procedure lấy hàng đó bằng SELECT ... FOR UPDATE. Hai lần chạy cùng run key phải tuần tự qua hàng khóa; lần thứ hai đọc được trạng thái SUCCEEDED và bỏ qua.

Row lock phù hợp khi trạng thái công việc đã được lưu trong InnoDB và cần gắn việc khóa với cập nhật trạng thái.

## 8. Idempotency: điều kiện để retry an toàn

Một công việc idempotent là công việc có thể chạy lại với cùng đầu vào mà kết quả cuối cùng không bị nhân đôi hoặc sai lệch.

Không phải mọi SQL statement đều idempotent.

Ví dụ không an toàn khi retry:

~~~sql
UPDATE account_balance
SET balance = balance + 100
WHERE account_id = 42;
~~~

Nếu lần đầu đã commit nhưng event mất kết nối trước khi ghi nhận thành công, lần retry cộng thêm 100 lần nữa.

Ví dụ idempotent hơn:

~~~sql
UPDATE account_balance
SET balance = 1500
WHERE account_id = 42;
~~~

Nếu giá trị đích luôn là 1500 theo một snapshot cố định, chạy lại không cộng dồn. Tuy nhiên, phải đảm bảo giá trị đó là kết quả đúng và không ghi đè một thay đổi mới hơn.

Các nguyên tắc thiết kế:

1. Mỗi lần chạy logic có một run key xác định, ví dụ daily_sales:2026-11-18.
2. Đặt UNIQUE hoặc PRIMARY KEY trên run key để ngăn tạo hai lần chạy logic giống nhau.
3. Ghi trạng thái SUCCEEDED trong cùng transaction với dữ liệu nghiệp vụ.
4. Khi lỗi, rollback dữ liệu nghiệp vụ trước khi ghi trạng thái FAILED.
5. Không dùng phép cộng dồn không có khóa chống trùng cho công việc có thể retry.
6. Nếu cần ghi ledger, mỗi nghiệp vụ phải có operation_id duy nhất.
7. Nếu gọi hệ thống ngoài, dùng outbox và idempotency key ở phía nhận.
8. Công việc nhiều batch cần checkpoint bền vững và mỗi batch cũng phải idempotent.

### At-least-once và exactly-once

Với event scheduler, timeout, crash, retry và hệ thống ngoài, không nên giả định một thao tác chỉ xảy ra đúng một lần trên toàn bộ hệ thống.

Thiết kế thực tế thường là at-least-once delivery/execution kết hợp idempotency hoặc deduplication. Một request có thể được gửi lại, nhưng khóa nghiệp vụ khiến hiệu ứng chỉ được ghi nhận một lần.

Exactly-once end-to-end đòi hỏi phối hợp transaction và deduplication ở tất cả hệ thống tham gia; một COMMIT trong MySQL không thể tự bảo đảm email hoặc HTTP request chỉ được thực hiện một lần.

## 9. Thiết kế bảng theo dõi lần chạy

Ví dụ bảng job_run lưu trạng thái của một công việc theo ngày nghiệp vụ:

~~~sql
CREATE TABLE scheduled_job_run (
    job_name VARCHAR(64) NOT NULL,
    run_date DATE NOT NULL,
    status ENUM(
        'PENDING',
        'RUNNING',
        'SUCCEEDED',
        'FAILED',
        'DEAD'
    ) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 5,
    next_retry_at DATETIME(6) NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    last_sqlstate CHAR(5) NULL,
    last_error_code INT NULL,
    last_error_message VARCHAR(1000) NULL,
    PRIMARY KEY (job_name, run_date),
    KEY idx_job_retry (status, next_retry_at)
) ENGINE=InnoDB;
~~~

Ý nghĩa:

| Cột | Mục đích |
|---|---|
| job_name | Định danh loại công việc |
| run_date | Run key theo ngày nghiệp vụ |
| status | Trạng thái xử lý |
| attempt_count | Số lần đã thử |
| max_attempts | Giới hạn retry |
| next_retry_at | Thời điểm sớm nhất được thử lại |
| started_at | Thời điểm bắt đầu lần chạy gần nhất |
| finished_at | Thời điểm kết thúc gần nhất |
| last_sqlstate | SQLSTATE của lỗi gần nhất |
| last_error_code | Mã lỗi MySQL |
| last_error_message | Nội dung lỗi gần nhất |

PRIMARY KEY (job_name, run_date) ngăn tạo hai record cho cùng một công việc và cùng một ngày. Nếu nghiệp vụ cần nhiều lần chạy độc lập trong một ngày, run key phải chứa thêm period, batch id hoặc version.

### Kiểm tra trạng thái

~~~sql
SELECT
    job_name,
    run_date,
    status,
    attempt_count,
    max_attempts,
    next_retry_at,
    started_at,
    finished_at,
    last_sqlstate,
    last_error_code,
    last_error_message
FROM scheduled_job_run
ORDER BY run_date DESC, job_name;
~~~

Tìm công việc đang chờ retry:

~~~sql
SELECT
    job_name,
    run_date,
    attempt_count,
    max_attempts,
    next_retry_at,
    last_error_message
FROM scheduled_job_run
WHERE status = 'FAILED'
  AND next_retry_at <= CURRENT_TIMESTAMP(6)
ORDER BY next_retry_at;
~~~

Tìm công việc đã vượt số lần retry:

~~~sql
SELECT
    job_name,
    run_date,
    attempt_count,
    last_error_message
FROM scheduled_job_run
WHERE status = 'DEAD'
ORDER BY run_date DESC;
~~~

## 10. Quy trình xử lý lỗi và retry trong transaction

Với một job có thể tính lại toàn bộ dữ liệu theo ngày, có thể dùng mô hình:

1. Tạo hoặc tìm record job_run với run key duy nhất.
2. Commit record điều phối để nó tồn tại độc lập với transaction xử lý.
3. Bắt đầu transaction xử lý.
4. Khóa record job_run bằng SELECT ... FOR UPDATE.
5. Nếu đã SUCCEEDED hoặc chưa đến next_retry_at, kết thúc sớm.
6. Đánh dấu RUNNING và tăng attempt_count.
7. Xóa dữ liệu summary cũ trong phạm vi ngày.
8. Tính lại và INSERT dữ liệu mới.
9. Đánh dấu SUCCEEDED cùng transaction.
10. COMMIT.
11. Nếu lỗi: ROLLBACK dữ liệu nghiệp vụ, sau đó ghi FAILED/DEAD và thông tin lỗi trong transaction mới, rồi RESIGNAL để Event Scheduler ghi nhận lỗi.

Điểm quan trọng là dữ liệu summary và trạng thái SUCCEEDED phải commit cùng nhau. Nếu cập nhật summary thành công nhưng ghi SUCCEEDED ở transaction khác, crash giữa hai bước có thể làm job bị chạy lại và tạo hiệu ứng lặp.

### Ví dụ bảng summary

~~~sql
CREATE TABLE daily_sales_summary (
    sales_date DATE NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    revenue DECIMAL(18,2) NOT NULL,
    refreshed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (sales_date, product_id),
    KEY idx_summary_product_date (product_id, sales_date)
) ENGINE=InnoDB;
~~~

Mỗi hàng là một sản phẩm trong một ngày. Khóa chính biểu diễn grain của báo cáo.

## 11. Ví dụ procedure có thể chạy lại an toàn

Ví dụ sau giả định đã có các bảng InnoDB:

- orders(order_id, status, created_at).
- order_items(order_item_id, order_id, product_id, quantity, unit_price).
- scheduled_job_run như phần trên.
- daily_sales_summary như phần trên.

Procedure tính lại toàn bộ summary cho một ngày. Mỗi ngày có một run key duy nhất.

~~~sql
DELIMITER //

CREATE PROCEDURE sp_refresh_daily_sales(IN p_sales_date DATE)
main: BEGIN
    DECLARE v_status VARCHAR(16);
    DECLARE v_retry_at DATETIME(6);
    DECLARE v_sqlstate CHAR(5);
    DECLARE v_error_code INT;
    DECLARE v_error_message TEXT;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        GET DIAGNOSTICS CONDITION 1
            v_sqlstate = RETURNED_SQLSTATE,
            v_error_code = MYSQL_ERRNO,
            v_error_message = MESSAGE_TEXT;

        ROLLBACK;

        START TRANSACTION;

        UPDATE scheduled_job_run
        SET
            status = CASE
                WHEN attempt_count + 1 >= max_attempts THEN 'DEAD'
                ELSE 'FAILED'
            END,
            next_retry_at = CASE
                WHEN attempt_count + 1 >= max_attempts THEN NULL
                ELSE CURRENT_TIMESTAMP(6) + INTERVAL 5 MINUTE
            END,
            finished_at = CURRENT_TIMESTAMP(6),
            last_sqlstate = v_sqlstate,
            last_error_code = v_error_code,
            last_error_message = LEFT(v_error_message, 1000),
            attempt_count = LEAST(attempt_count + 1, max_attempts)
        WHERE job_name = 'daily_sales'
          AND run_date = p_sales_date;

        COMMIT;
        RESIGNAL;
    END;

    IF p_sales_date IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Sales date is required';
    END IF;

    INSERT INTO scheduled_job_run (
        job_name,
        run_date,
        status,
        attempt_count,
        max_attempts
    )
    VALUES (
        'daily_sales',
        p_sales_date,
        'PENDING',
        0,
        5
    ) AS incoming
    ON DUPLICATE KEY UPDATE
        job_name = incoming.job_name;

    COMMIT;

    START TRANSACTION;

    SELECT status, next_retry_at
    INTO v_status, v_retry_at
    FROM scheduled_job_run
    WHERE job_name = 'daily_sales'
      AND run_date = p_sales_date
    FOR UPDATE;

    IF v_status IN ('SUCCEEDED', 'DEAD') THEN
        COMMIT;
        LEAVE main;
    END IF;

    IF v_status = 'FAILED'
       AND v_retry_at IS NOT NULL
       AND v_retry_at > CURRENT_TIMESTAMP(6) THEN
        COMMIT;
        LEAVE main;
    END IF;

    UPDATE scheduled_job_run
    SET
        status = 'RUNNING',
        attempt_count = attempt_count + 1,
        started_at = CURRENT_TIMESTAMP(6),
        finished_at = NULL,
        last_sqlstate = NULL,
        last_error_code = NULL,
        last_error_message = NULL
    WHERE job_name = 'daily_sales'
      AND run_date = p_sales_date;

    DELETE FROM daily_sales_summary
    WHERE sales_date = p_sales_date;

    INSERT INTO daily_sales_summary (
        sales_date,
        product_id,
        order_count,
        revenue,
        refreshed_at
    )
    SELECT
        p_sales_date,
        oi.product_id,
        COUNT(DISTINCT o.order_id),
        SUM(oi.quantity * oi.unit_price),
        CURRENT_TIMESTAMP(6)
    FROM orders AS o
    JOIN order_items AS oi
        ON oi.order_id = o.order_id
    WHERE o.status = 'PAID'
      AND o.created_at >= p_sales_date
      AND o.created_at < p_sales_date + INTERVAL 1 DAY
    GROUP BY oi.product_id;

    UPDATE scheduled_job_run
    SET
        status = 'SUCCEEDED',
        next_retry_at = NULL,
        finished_at = CURRENT_TIMESTAMP(6),
        last_sqlstate = NULL,
        last_error_code = NULL,
        last_error_message = NULL
    WHERE job_name = 'daily_sales'
      AND run_date = p_sales_date;

    COMMIT;
END//

DELIMITER ;
~~~

Trong UPDATE một bảng, MySQL đánh giá các phép gán theo thứ tự từ trái sang phải. Vì vậy status và next_retry_at được tính từ attempt_count cũ cộng 1; phép gán attempt_count được đặt cuối. Giữ thứ tự này khi chỉnh sửa ví dụ để ngưỡng max_attempts không bị lệch.

### Vì sao procedure có thể retry?

- Run key (daily_sales, run_date) là duy nhất.
- Nếu đã SUCCEEDED, lần gọi sau bỏ qua.
- Nếu FAILED nhưng chưa đến next_retry_at, lần gọi sau bỏ qua.
- Nếu được retry, DELETE và INSERT được thực hiện trong cùng transaction.
- Nếu INSERT thất bại, ROLLBACK khôi phục summary đã commit trước đó.
- Handler ghi FAILED hoặc DEAD sau khi rollback.
- RESIGNAL giúp Event Scheduler ghi lỗi vào error log.
- Khi số lần thử đạt max_attempts, công việc chuyển DEAD và cần can thiệp vận hành.

Procedure này sở hữu transaction. Nó có COMMIT trước khi bắt đầu transaction xử lý để lưu record điều phối, do đó không được gọi bên trong một transaction nghiệp vụ của caller mà caller muốn giữ. Trong ví dụ event, procedure được gọi từ session riêng do Event Scheduler tạo.

Mẫu trên minh họa một job theo ngày trong một server. Với job nhiều batch, cần checkpoint riêng cho từng batch và khóa chống chạy trùng ở cấp batch.

## 12. Tạo event gọi lại cùng run key

Tạo event lặp mỗi 5 phút để gọi procedure cho ngày nghiệp vụ liền trước:

~~~sql
SET time_zone = 'Asia/Ho_Chi_Minh';

CREATE EVENT ev_retry_daily_sales
ON SCHEDULE EVERY 5 MINUTE
STARTS CURRENT_TIMESTAMP + INTERVAL 1 MINUTE
COMMENT 'Retry daily sales summary until success or DEAD'
DO
    CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Cơ chế:

- Mỗi lần event chạy, run key là ngày hôm qua theo TIME_ZONE của event.
- Nếu công việc đã SUCCEEDED, procedure bỏ qua.
- Nếu lần trước FAILED và chưa đến next_retry_at, procedure bỏ qua.
- Khi đã đến thời điểm retry, procedure thử lại.
- Nếu thành công, trạng thái trở thành SUCCEEDED.
- Nếu vượt max_attempts, trạng thái trở thành DEAD và các lần gọi sau không xử lý tiếp.

Đây là retry pump đơn giản cho một loại công việc. Trong hệ thống có nhiều job, nên có dispatcher đọc queue các run key đến hạn và xử lý theo batch.

Ví dụ giả định dữ liệu của ngày hôm trước đã đủ khi lần chạy đầu tiên thành công. Nếu nguồn có đơn đến muộn hoặc đơn được sửa sau đó, trạng thái SUCCEEDED sẽ khiến cùng run key bị bỏ qua. Khi đó cần watermark/độ trễ chốt sổ, một revision key mới hoặc chủ động mở lại phạm vi ngày bị ảnh hưởng theo quy trình audit.

### Bật và kiểm tra event

~~~sql
ALTER EVENT ev_retry_daily_sales ENABLE;

SHOW CREATE EVENT ev_retry_daily_sales;

SELECT
    EVENT_NAME,
    STATUS,
    DEFINER,
    TIME_ZONE,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = DATABASE()
  AND EVENT_NAME = 'ev_retry_daily_sales';
~~~

Event chỉ thực thi khi Event Scheduler được bật. Hãy kiểm tra cả event_scheduler và error log sau khi triển khai.

## 13. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng nên retry liên tục.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Tạm thời | Deadlock, lock wait timeout, tài nguyên tạm thời bận | Retry có backoff và giới hạn số lần |
| Mất kết nối | Connection bị ngắt trong lúc xử lý | Xác định transaction đã commit chưa; retry bằng run key idempotent |
| Quyền | DEFINER thiếu INSERT/UPDATE/EXECUTE | Sửa quyền, sau đó retry có kiểm soát |
| Schema | Cột bị đổi tên, bảng bị drop | Dừng retry, sửa migration hoặc routine |
| Dữ liệu | Giá trị không hợp lệ, vi phạm constraint | Đưa vào trạng thái DEAD hoặc quarantine để xử lý |
| Logic | Chia cho 0, sai giả định nghiệp vụ | Sửa code; không retry nguyên trạng |
| Cấu hình | Scheduler OFF, sai múi giờ, event DISABLED | Sửa cấu hình và xác minh lịch |

Retry một lỗi cú pháp hoặc thiếu quyền không làm nó tự hết. Retry liên tục có thể tạo log spam, tăng tải và che khuất lỗi gốc.

### Backoff

Thay vì thử lại liên tục, tăng khoảng chờ giữa các lần:

- Lần 1: chờ ngắn.
- Lần 2: chờ lâu hơn.
- Các lần sau: tăng theo exponential backoff và giới hạn ở một mức tối đa.
- Có thể thêm jitter để nhiều job không cùng retry vào một thời điểm.

Ví dụ đơn giản trong bài dùng 5 phút cố định. Production nên chọn backoff theo SLA, loại lỗi và tải hệ thống.

## 14. Không để hai event instance xử lý cùng một công việc

Một event có thể chạy lâu hơn khoảng lịch. Dùng một trong các cách:

### Cách A: khóa hàng job_run

SELECT ... FOR UPDATE trên PRIMARY KEY (job_name, run_date) làm các lần xử lý cùng run key tuần tự. Sau khi worker thứ nhất commit SUCCEEDED, worker thứ hai đọc trạng thái đó và thoát.

### Cách B: named lock

GET_LOCK phù hợp khi muốn khóa toàn bộ một loại công việc trong cùng server. Cần RELEASE_LOCK trong cả đường thành công và đường lỗi.

### Cách C: lease cho job dài

Nếu job phải commit theo batch và không thể giữ một transaction dài, dùng lease:

- owner_id nhận diện worker.
- lease_until là thời hạn giữ quyền xử lý.
- heartbeat_at cho biết worker còn hoạt động.
- worker khác chỉ nhận việc khi lease hết hạn.
- mỗi lần cập nhật phải kiểm tra owner_id để worker cũ không ghi đè worker mới.

Lease giúp phục hồi khi worker chết, nhưng phải xử lý worker cũ sống lại sau khi lease hết hạn. Có thể dùng fencing token tăng dần để từ chối thao tác từ worker cũ.

Không giữ transaction InnoDB mở hàng giờ chỉ để khóa một job lớn. Hãy chia batch, checkpoint và bảo đảm mỗi batch có thể chạy lại.

## 15. Tác vụ có hiệu ứng ngoài database: dùng outbox

Transaction MySQL không thể nguyên tử cùng một HTTP request hoặc thao tác gửi email bên ngoài.

Ví dụ:

1. Procedure cập nhật order thành PAID.
2. Procedure gửi email.
3. Connection mất trước khi ghi nhận email đã gửi.
4. Retry procedure gửi email lần thứ hai.

Không thể dùng ROLLBACK để thu hồi email đã gửi.

Giải pháp thường dùng là transactional outbox:

~~~sql
CREATE TABLE event_outbox (
    message_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    message_key VARCHAR(128) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload JSON NOT NULL,
    status ENUM('PENDING', 'PROCESSING', 'SENT', 'FAILED') NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL,
    sent_at DATETIME(6) NULL,
    UNIQUE KEY uq_outbox_message_key (message_key),
    KEY idx_outbox_pending (status, created_at)
) ENGINE=InnoDB;
~~~

Trong cùng transaction cập nhật order:

~~~sql
START TRANSACTION;

UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;

INSERT INTO event_outbox (
    message_key,
    event_type,
    payload,
    status,
    created_at
)
VALUES (
    'order-paid:1001',
    'ORDER_PAID',
    JSON_OBJECT('order_id', 1001),
    'PENDING',
    CURRENT_TIMESTAMP(6)
);

COMMIT;
~~~

Một worker riêng đọc outbox, gửi message và đánh dấu SENT. Nếu gửi thành công nhưng mất kết nối trước khi cập nhật SENT, worker có thể gửi lại. Hệ thống nhận nên hỗ trợ idempotency key message_key hoặc deduplicate theo khóa đó.

Outbox bảo đảm việc ghi nhận ý định gửi message cùng transaction nghiệp vụ. Nó không tự bảo đảm hệ thống bên ngoài chỉ nhận một lần.

## 16. Phục hồi và retry thủ công

Khi job chuyển FAILED:

1. Đọc last_error_message, SQLSTATE và error code.
2. Đối chiếu error log của Event Scheduler.
3. Xác định lỗi tạm thời hay lỗi cần sửa cấu hình/code/dữ liệu.
4. Kiểm tra dữ liệu summary có giữ nguyên bản trước đó hay không.
5. Sửa nguyên nhân.
6. Đưa next_retry_at về thời điểm hiện tại nếu muốn dispatcher thử lại.
7. Giữ nguyên attempt_count để audit.

Ví dụ đưa một job FAILED đến hạn ngay:

~~~sql
UPDATE scheduled_job_run
SET next_retry_at = CURRENT_TIMESTAMP(6)
WHERE job_name = 'daily_sales'
  AND run_date = '2026-11-18'
  AND status = 'FAILED';
~~~

Không tự chuyển DEAD về PENDING khi chưa xem lỗi và chưa quyết định có cho phép thêm lượt retry. Nếu cần mở lại, lưu dấu người thao tác, thời điểm, lý do và attempt policy mới.

### Nếu event bị DISABLED

Sau khi xác minh nguyên nhân và quyền:

~~~sql
ALTER EVENT ev_retry_daily_sales ENABLE;
~~~

Nếu muốn dừng event trong khi sửa:

~~~sql
ALTER EVENT ev_retry_daily_sales DISABLE;
~~~

Tắt event không xóa job_run. Khi bật lại, procedure có thể tiếp tục từ trạng thái bền vững trong bảng job.

### Nếu scheduler OFF

~~~sql
SET GLOBAL event_scheduler = ON;
~~~

Cần kiểm tra quyền thay đổi biến toàn cục và cấu hình sau restart.

## 17. Chạy event trên replica và môi trường HA

Event được lưu trong metadata và có thể được sao chép theo các quy tắc replication của MySQL. Trên replica, event được tạo từ source thường có trạng thái REPLICA_SIDE_DISABLED để tránh thực thi trùng.

Kiểm tra:

~~~sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    STATUS,
    ORIGINATOR
FROM INFORMATION_SCHEMA.EVENTS
ORDER BY EVENT_SCHEMA, EVENT_NAME;
~~~

Trong các phiên bản trước MySQL 8.2.0, tên trạng thái này là SLAVESIDE_DISABLED; từ MySQL 8.2.0 dùng REPLICA_SIDE_DISABLED.

Trong kiến trúc HA:

- Xác định server nào là writer/primary.
- Chỉ cho phép job có ghi dữ liệu chạy ở nơi được chỉ định.
- Không tự bật event trên mọi replica.
- Khi failover, xác định rõ thời điểm chuyển quyền chạy job.
- Dùng run key duy nhất và idempotency để bảo vệ khi failover gây chạy lại.
- Theo dõi event DEFINER và quyền trên node mới.

Event Scheduler không tự giải quyết vai trò leader cho nhiều MySQL server độc lập. Nếu nhiều primary có thể chạy cùng job, cần cơ chế điều phối cấp hệ thống hoặc thiết kế dữ liệu chống trùng xuyên node.

## 18. Các bước điều tra event không tạo ra kết quả

Khi dashboard không thấy dữ liệu mới, làm theo thứ tự:

1. Kiểm tra event_scheduler có ON.
2. Kiểm tra scheduler thread trong SHOW PROCESSLIST.
3. Kiểm tra event có tồn tại trong INFORMATION_SCHEMA.EVENTS.
4. Kiểm tra STATUS, STARTS, ENDS, TIME_ZONE và lịch tiếp theo.
5. Kiểm tra LAST_EXECUTED nhưng không xem nó là trạng thái thành công.
6. Kiểm tra DEFINER và SHOW GRANTS.
7. Kiểm tra routine mà event gọi, SQL SECURITY và EXECUTE privilege.
8. Đọc error log file hoặc performance_schema.error_log.
9. Gọi procedure trực tiếp trong session thử nghiệm với đúng tham số.
10. Kiểm tra job_run theo run key.
11. Đối chiếu summary, checkpoint, outbox và dữ liệu nguồn.
12. Kiểm tra job có bị overlap, lock wait, deadlock hoặc quá thời gian chạy không.
13. Xác minh timezone và ngày nghiệp vụ.
14. Sửa nguyên nhân rồi retry theo chính sách.

Nếu gọi procedure trực tiếp thành công nhưng event thất bại, ưu tiên kiểm tra DEFINER, quyền, SQL mode được lưu tại thời điểm CREATE/ALTER EVENT, time_zone và session context của event.

## 19. Bài thực hành: theo dõi event lỗi và retry summary

Bài lab tạo event chạy lại một summary theo ngày. Mục tiêu là quan sát metadata, lỗi, trạng thái job và cơ chế idempotency.

### Bước 1: tạo database và bảng nguồn

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_event_retry_lab;
USE mysql_event_retry_lab;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME(6) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE order_items (
    order_item_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    order_id BIGINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity DECIMAL(12,3) NOT NULL,
    unit_price DECIMAL(12,2) NOT NULL,
    KEY idx_items_order (order_id)
) ENGINE=InnoDB;

CREATE TABLE daily_sales_summary (
    sales_date DATE NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    order_count BIGINT UNSIGNED NOT NULL,
    revenue DECIMAL(18,2) NOT NULL,
    refreshed_at DATETIME(6) NOT NULL,
    PRIMARY KEY (sales_date, product_id)
) ENGINE=InnoDB;

CREATE TABLE scheduled_job_run (
    job_name VARCHAR(64) NOT NULL,
    run_date DATE NOT NULL,
    status ENUM(
        'PENDING',
        'RUNNING',
        'SUCCEEDED',
        'FAILED',
        'DEAD'
    ) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 0,
    max_attempts INT UNSIGNED NOT NULL DEFAULT 5,
    next_retry_at DATETIME(6) NULL,
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    last_sqlstate CHAR(5) NULL,
    last_error_code INT NULL,
    last_error_message VARCHAR(1000) NULL,
    PRIMARY KEY (job_name, run_date),
    KEY idx_job_retry (status, next_retry_at)
) ENGINE=InnoDB;
~~~

### Bước 2: nạp dữ liệu nguồn

~~~sql
INSERT INTO orders (order_id, status, created_at)
VALUES
    (1, 'PAID', CURRENT_TIMESTAMP(6) - INTERVAL 1 DAY),
    (2, 'PAID', CURRENT_TIMESTAMP(6) - INTERVAL 1 DAY),
    (3, 'PENDING', CURRENT_TIMESTAMP(6) - INTERVAL 1 DAY);

INSERT INTO order_items (
    order_item_id,
    order_id,
    product_id,
    quantity,
    unit_price
)
VALUES
    (101, 1, 10, 2.000, 100.00),
    (102, 1, 20, 1.000, 250.00),
    (103, 2, 10, 3.000, 100.00),
    (104, 3, 20, 2.000, 250.00);
~~~

### Bước 3: tạo procedure retry

Dùng procedure sp_refresh_daily_sales ở phần 11. Khi tạo trong lab, thay tên schema/table nếu bạn không dùng database mysql_event_retry_lab.

### Bước 4: gọi procedure thủ công lần đầu

~~~sql
CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Kiểm tra:

~~~sql
SELECT *
FROM scheduled_job_run
WHERE job_name = 'daily_sales';

SELECT *
FROM daily_sales_summary
ORDER BY sales_date, product_id;
~~~

Trạng thái kỳ vọng là SUCCEEDED. Summary có sản phẩm 10 và 20; đơn PENDING không được tính.

### Bước 5: gọi lại cùng run key

~~~sql
CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Kiểm tra attempt_count và summary. Vì trạng thái đã SUCCEEDED, procedure bỏ qua và không tính lại.

### Bước 6: mô phỏng lỗi có thể retry

Trong môi trường lab, tạm thời làm cho câu INSERT summary thất bại, ví dụ đổi tên cột đích trong procedure rồi tạo lại routine. Không làm trên production.

Gọi lại procedure:

~~~sql
CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Quan sát:

- Statement thất bại.
- Transaction summary bị rollback.
- Handler ghi trạng thái FAILED hoặc DEAD.
- SQLSTATE, error code và error message được lưu.
- Event Scheduler ghi thông báo lỗi khi procedure được gọi từ event và RESIGNAL lỗi ra ngoài.

Sau khi xác minh lỗi trong error log, khôi phục định nghĩa procedure.

### Bước 7: kiểm tra retry time

~~~sql
SELECT
    job_name,
    run_date,
    status,
    attempt_count,
    max_attempts,
    next_retry_at,
    last_sqlstate,
    last_error_code,
    last_error_message
FROM scheduled_job_run
WHERE job_name = 'daily_sales';
~~~

Nếu trạng thái FAILED và chưa đến next_retry_at, procedure sẽ bỏ qua lần gọi hiện tại. Khi đến thời điểm retry, procedure thử lại.

### Bước 8: tạo event

~~~sql
SET time_zone = 'Asia/Ho_Chi_Minh';

CREATE EVENT ev_retry_daily_sales_lab
ON SCHEDULE EVERY 1 MINUTE
STARTS CURRENT_TIMESTAMP + INTERVAL 1 MINUTE
COMMENT 'Lab: retry daily sales'
DO
    CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
~~~

Nếu Event Scheduler đang OFF, bật trong môi trường lab với tài khoản có quyền:

~~~sql
SET GLOBAL event_scheduler = ON;
~~~

### Bước 9: theo dõi event và error log

~~~sql
SELECT
    EVENT_NAME,
    STATUS,
    DEFINER,
    TIME_ZONE,
    LAST_EXECUTED
FROM INFORMATION_SCHEMA.EVENTS
WHERE EVENT_SCHEMA = 'mysql_event_retry_lab';
~~~

~~~sql
SELECT
    LOGGED,
    PRIO,
    ERROR_CODE,
    SUBSYSTEM,
    DATA
FROM performance_schema.error_log
WHERE DATA LIKE '%ev_retry_daily_sales_lab%'
   OR DATA LIKE '%Event Scheduler%'
ORDER BY LOGGED DESC
LIMIT 50;
~~~

Nếu error_log không có dữ liệu, đọc server error log theo cấu hình của môi trường.

### Bước 10: kiểm tra idempotency

Chạy procedure nhiều lần với cùng ngày. Xác nhận:

- Chỉ có một row job_run cho job_name + run_date.
- Khi SUCCEEDED, lần gọi sau không tăng attempt_count.
- Summary không bị cộng dồn.
- Dữ liệu summary không đổi khi nguồn không đổi.

### Bước 11: tắt event và dọn lab

~~~sql
ALTER EVENT ev_retry_daily_sales_lab DISABLE;

DROP EVENT ev_retry_daily_sales_lab;

DROP DATABASE mysql_event_retry_lab;
~~~

Chỉ chạy DROP DATABASE trên database lab vừa tạo. Không tắt Event Scheduler toàn server nếu có event khác đang phụ thuộc.

## 20. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Event ENABLED nhưng không chạy | event_scheduler OFF/DISABLED hoặc lịch chưa đến | Kiểm tra biến toàn cục, thread, STARTS/ENDS |
| Event có LAST_EXECUTED nhưng không có dữ liệu | Action lỗi sau khi bắt đầu | Đọc error log và kiểm tra job_run |
| LAST_EXECUTED là NULL | Event chưa được ghi nhận chạy; có thể lịch chưa đến hoặc lỗi trước khi action thực thi | Kiểm tra DEFINER, quyền, scheduler và error log |
| STATUS vẫn ENABLED sau lần chạy lỗi | STATUS chỉ phản ánh trạng thái bật/tắt | Theo dõi trạng thái nghiệp vụ riêng |
| CREATE EVENT thành công nhưng INSERT thất bại | DEFINER thiếu quyền INSERT | Kiểm tra SHOW GRANTS và security context |
| Error log không có thông báo trong Performance Schema | Log sink không hỗ trợ hoặc không ghi vào error_log | Kiểm tra log_error_services và đọc file log |
| Error log có quá nhiều warning | SELECT INTO phát No data hoặc nhiều hàng | Dùng handler đúng điều kiện, LIMIT 1 khi phù hợp |
| Event chạy hai lần cùng lúc | Thời gian chạy dài hơn chu kỳ | Dùng GET_LOCK hoặc row lock theo run key |
| Retry tạo dữ liệu trùng | Công việc không idempotent | Dùng unique key, upsert giá trị tuyệt đối hoặc ledger dedup |
| Job bị FAILED mãi | Lỗi logic/quyền/schema không được sửa | Phân loại lỗi, sửa nguyên nhân, retry có giới hạn |
| Job bị RUNNING sau khi worker chết | Trạng thái RUNNING đã được commit trước đó | Dùng lease/heartbeat và cơ chế thu hồi stale job |
| Event chạy trên replica | Event được enable sai node | Kiểm tra REPLICA_SIDE_DISABLED và vai trò writer |
| Báo cáo sai ngày | TIME_ZONE hoặc business date không nhất quán | Cố định múi giờ nghiệp vụ và kiểm tra TIME_ZONE |
| Gửi email/API trùng | Retry không thể rollback side effect bên ngoài | Dùng outbox, message key và dedup ở consumer |
| Retry gây tải tăng đột biến | Nhiều job cùng retry tức thì | Exponential backoff, jitter và giới hạn concurrency |
| Event chạy nhưng không có kết quả hiển thị | SELECT/SHOW chỉ trả result set bị bỏ đi | Dùng SELECT ... INTO, INSERT ... SELECT hoặc bảng trạng thái |

## 21. Checklist vận hành event và retry

- [ ] event_scheduler đang ON và scheduler thread tồn tại.
- [ ] Event có STATUS phù hợp.
- [ ] STARTS, ENDS, TIME_ZONE và chu kỳ được xác minh.
- [ ] LAST_EXECUTED được hiểu là thời điểm bắt đầu, không phải kết quả thành công.
- [ ] Error log được thu thập và giữ đủ lâu.
- [ ] performance_schema.error_log có sink hỗ trợ hoặc có đường đọc log khác.
- [ ] DEFINER tồn tại và có quyền tối thiểu cần thiết.
- [ ] Routine được event gọi có quyền EXECUTE và security context đúng.
- [ ] Event không chạy đồng thời cùng run key nếu nghiệp vụ không cho phép.
- [ ] Mỗi logical run có khóa duy nhất.
- [ ] Công việc có thể retry mà không cộng/trừ hoặc gửi trùng.
- [ ] Dữ liệu nghiệp vụ và trạng thái SUCCEEDED commit cùng transaction.
- [ ] Handler rollback công việc thất bại trước khi ghi trạng thái FAILED.
- [ ] Lỗi được lưu SQLSTATE, error code và message.
- [ ] Retry có next_retry_at, backoff và max_attempts.
- [ ] Công việc vượt ngưỡng chuyển DEAD và phát cảnh báo.
- [ ] Job dài có checkpoint, lease hoặc batch idempotent.
- [ ] Side effect bên ngoài dùng outbox và idempotency key.
- [ ] Có quy trình retry thủ công và audit người thao tác.
- [ ] Có kế hoạch failover để chỉ một node được quyền chạy job ghi dữ liệu.

## 22. Nguyên tắc cần ghi nhớ

1. Event Scheduler kích hoạt SQL theo lịch; nó không thay thế một job queue bền vững.
2. Event execution kết thúc với error hoặc warning được ghi vào server error log.
3. INFORMATION_SCHEMA.EVENTS mô tả event, không phải lịch sử kết quả nghiệp vụ.
4. STATUS ENABLED không chứng minh lần chạy gần nhất thành công.
5. LAST_EXECUTED biểu thị thời điểm event bắt đầu, không phải thời điểm hoàn thành.
6. performance_schema.error_log chỉ có dữ liệu nếu log sink hỗ trợ; đây là ring buffer, không phải kho log dài hạn.
7. Event chạy với DEFINER và quyền của security context liên quan; CREATE EVENT thành công không bảo đảm action có đủ quyền.
8. Event thực thi trong connection riêng; không dựa vào temporary table hoặc session variable của connection ứng dụng.
9. Event có thể overlap nếu thời gian chạy vượt chu kỳ.
10. GET_LOCK là named lock cấp session/server, không phải khóa phân tán xuyên nhiều server.
11. Mỗi logical job cần run key duy nhất và idempotency.
12. Retry nên là at-least-once kết hợp deduplication; không mặc định exactly-once.
13. Dữ liệu nghiệp vụ và trạng thái SUCCEEDED nên được commit cùng transaction.
14. Khi lỗi, rollback công việc trước rồi ghi FAILED trong transaction mới.
15. Phân loại lỗi trước retry; dùng backoff, max attempts và DEAD state.
16. Dùng outbox cho side effect bên ngoài database.
17. Theo dõi timezone, replication, failover và quyền DEFINER như một phần của vận hành.

## Tài liệu tham khảo chính thức

Các hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual**:

1. [Event Scheduler Overview](https://dev.mysql.com/doc/refman/9.7/en/events-overview.html): vòng đời event, quyền DEFINER và khả năng các instance chồng lấn.
2. [Event Scheduler Configuration](https://dev.mysql.com/doc/refman/9.7/en/events-configuration.html): event_scheduler ON/OFF/DISABLED, scheduler thread và cấu hình khởi động.
3. [Event Scheduler Status](https://dev.mysql.com/doc/refman/9.7/en/events-status-info.html): lỗi và warning khi event thực thi được ghi vào server error log.
4. [The Event Scheduler and MySQL Privileges](https://dev.mysql.com/doc/refman/9.7/en/events-privileges.html): EVENT privilege, quyền của DEFINER và lỗi quyền trong action.
5. [Event Metadata](https://dev.mysql.com/doc/refman/9.7/en/events-metadata.html): SHOW EVENTS, SHOW CREATE EVENT và múi giờ của event.
6. [INFORMATION_SCHEMA EVENTS Table](https://dev.mysql.com/doc/refman/9.7/en/information-schema-events-table.html): STATUS, DEFINER, TIME_ZONE và LAST_EXECUTED.
7. [CREATE EVENT Statement](https://dev.mysql.com/doc/refman/9.7/en/create-event.html): cú pháp lịch, EVERY, STARTS, ENDS và event action.
8. [The Performance Schema error_log Table](https://dev.mysql.com/doc/refman/9.7/en/performance-schema-error-log-table.html): đọc error log qua SQL, log sink và ring buffer.
9. [Error Log Configuration](https://dev.mysql.com/doc/refman/9.7/en/error-log-configuration.html): log_error_services và các log sink.
10. [MySQL Privileges](https://dev.mysql.com/doc/refman/9.7/en/privileges-provided.html): EVENT, EXECUTE và quyền quản lý stored object.


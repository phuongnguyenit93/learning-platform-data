# Event Scheduler, lịch một lần hoặc định kỳ và múi giờ

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích Event Scheduler và cách MySQL thực thi event mà không cần ứng dụng giữ một kết nối để chờ lịch.
- Kiểm tra và bật/tắt `event_scheduler`.
- Tạo event chạy một lần bằng `AT` và event lặp bằng `EVERY`.
- Chọn `STARTS`, `ENDS`, `ON COMPLETION PRESERVE` và trạng thái `ENABLE`/`DISABLE` phù hợp.
- Phân biệt múi giờ của server, session và event.
- Chọn UTC hoặc named time zone cho lịch chạy theo thời gian thực hoặc giờ địa phương.
- Hiểu tác động của daylight saving time (DST) và việc nạp time zone tables.
- Kiểm tra định nghĩa, lịch chạy, lần chạy gần nhất và trạng thái event.
- Quản lý `DEFINER`, quyền và replication để tránh event chạy trên sai node.
- Thiết kế job có thể chạy lại an toàn, có log, chống chạy chồng và phục hồi khi scheduler tạm dừng.

Các ví dụ hướng tới MySQL 8.0/8.4. Event Scheduler là cơ chế chạy tác vụ bên trong MySQL Server; nó không thay thế hệ thống orchestration bên ngoài khi cần retry phức tạp, giám sát phân tán hoặc phối hợp nhiều dịch vụ.

## 1. Event Scheduler là gì?

Event là một đối tượng schema lưu lịch thực thi một hoặc nhiều câu lệnh SQL. Khi Event Scheduler được bật, MySQL theo dõi các event đã enable và thực thi nội dung của event khi đến thời điểm được lên lịch.

Ví dụ, hệ thống cần mỗi đêm tổng hợp đơn hàng đã thanh toán. Có thể tạo event gọi một stored procedure:

```sql
CREATE EVENT ev_refresh_daily_sales
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_TIMESTAMP + INTERVAL 1 DAY
DO
    CALL sp_refresh_daily_sales();
```

Event được lưu trong schema và do server quản lý. Ứng dụng không cần giữ một thread hoặc connection chỉ để đợi đến giờ rồi gửi câu lệnh.

### 1.1. Thành phần của một event

Một event có các thành phần chính:

- **Tên và schema:** định danh event trong database.
- **Schedule:** chạy một lần (`AT`) hoặc lặp lại (`EVERY`).
- **Completion policy:** giữ lại hay tự xóa event sau khi lịch hoàn tất.
- **Status:** bật hoặc tắt event.
- **Definer:** tài khoản mà quyền của nó được dùng khi event thực thi.
- **Body:** câu SQL hoặc compound statement được chạy theo lịch.
- **Time zone:** múi giờ được gắn với event khi tạo hoặc thay đổi lịch.

### 1.2. Event khác cron job ở đâu?

| Tiêu chí | MySQL Event Scheduler | Cron/job scheduler bên ngoài |
|---|---|---|
| Nơi lưu lịch | Trong MySQL schema | Trong hệ điều hành hoặc nền tảng điều phối |
| Thực thi | SQL trong MySQL Server | Có thể gọi script, API, nhiều dịch vụ |
| Phụ thuộc | Server đang chạy và scheduler bật | Agent/daemon hoặc nền tảng scheduler hoạt động |
| Quan sát | `INFORMATION_SCHEMA.EVENTS`, log do ứng dụng thiết kế | Log và dashboard của hệ thống bên ngoài |
| Điều phối phân tán | Hạn chế, cần tự thiết kế | Thường có nhiều cơ chế retry, lease, queue, HA |
| Phù hợp | Job SQL gọn, gần dữ liệu, theo lịch đơn giản | Workflow nhiều bước, tích hợp dịch vụ, retry phức tạp |

Chọn Event Scheduler khi công việc chủ yếu là SQL và vòng đời vận hành có thể quản lý trong MySQL. Chọn scheduler bên ngoài khi cần workflow nhiều hệ thống, retry có kiểm soát, cảnh báo hoặc điều phối nhiều worker.

## 2. Kiểm tra trạng thái Event Scheduler

### 2.1. Xem biến hệ thống

```sql
SHOW GLOBAL VARIABLES LIKE 'event_scheduler';
```

Hoặc:

```sql
SELECT @@GLOBAL.event_scheduler;
```

Giá trị có thể là:

| Giá trị | Ý nghĩa |
|---|---|
| `ON` | Event Scheduler hoạt động và có thể thực thi event đang enable |
| `OFF` | Scheduler không thực thi event; các event vẫn được lưu trong schema |
| `DISABLED` | Scheduler bị vô hiệu hóa khi server khởi động và không thể bật bằng `SET GLOBAL` trong runtime |

Nếu giá trị là `OFF`, event không tự chạy cho đến khi scheduler được bật lại. Nếu là `DISABLED`, cần sửa cấu hình khởi động server rồi restart theo quy trình vận hành.

### 2.2. Bật scheduler trong runtime

Khi server cho phép thay đổi biến này:

```sql
SET GLOBAL event_scheduler = ON;
```

Lệnh cần quyền quản trị biến hệ thống phù hợp. Không cấp quyền quản trị global cho tài khoản ứng dụng chỉ để tạo một event.

### 2.3. Cấu hình khi server khởi động

Có thể cấu hình trong file cấu hình MySQL:

```ini
[mysqld]
event_scheduler=ON
```

Nếu cấu hình là:

```ini
[mysqld]
event_scheduler=DISABLED
```

thì scheduler bị khóa ở trạng thái disabled trong lần khởi động đó. `OFF` và `DISABLED` không tương đương: `OFF` có thể bật lại trong runtime nếu server cho phép; `DISABLED` không thể bật bằng lệnh SQL khi server đang chạy.

### 2.4. Scheduler OFF không xóa event

Tắt scheduler chỉ dừng việc dispatch event. Định nghĩa, lịch và trạng thái enable/disable của event vẫn nằm trong metadata. Bật lại scheduler không phải là một cơ chế retry đáng tin cậy cho mọi lần chạy đã bị bỏ lỡ.

Đừng giả định mọi occurrence trong thời gian scheduler tắt sẽ được chạy bù đầy đủ. Hãy thiết kế job có thể đối soát theo khoảng thời gian, ví dụ xử lý tất cả ngày chưa tổng hợp, thay vì chỉ xử lý “ngày hôm nay”. Sau khi bật lại scheduler, kiểm tra `LAST_EXECUTED`, trạng thái job và dữ liệu thực tế.

## 3. Cú pháp lịch một lần bằng AT

Event chạy một lần dùng `ON SCHEDULE AT`:

```sql
CREATE EVENT ev_close_expired_campaign
ON SCHEDULE AT CURRENT_TIMESTAMP + INTERVAL 2 HOUR
DO
    CALL sp_close_expired_campaigns();
```

Biểu thức thời gian được đánh giá khi tạo hoặc thay đổi event để xác định thời điểm thực thi. Event không phải câu lệnh được tính lại `CURRENT_TIMESTAMP + INTERVAL 2 HOUR` mỗi giây.

### 3.1. Chạy vào thời điểm cố định

```sql
CREATE EVENT ev_archive_2026_12_01
ON SCHEDULE AT '2026-12-01 01:30:00'
DO
    CALL sp_archive_orders_for_date('2026-11-30');
```

Thời điểm literal được diễn giải theo múi giờ của session khi tạo event. Vì vậy, trước khi tạo lịch, cần đặt session `time_zone` một cách tường minh và ghi nhận múi giờ đó trong quy trình triển khai.

### 3.2. ON COMPLETION NOT PRESERVE và PRESERVE

Event một lần sau khi hoàn tất có thể được tự động xóa hoặc được giữ lại:

```sql
CREATE EVENT ev_send_month_end_report
ON SCHEDULE AT '2026-12-01 08:00:00'
ON COMPLETION PRESERVE
DO
    CALL sp_send_month_end_report();
```

- `ON COMPLETION NOT PRESERVE`: event một lần được tự động xóa sau khi hoàn tất; đây là mặc định.
- `ON COMPLETION PRESERVE`: giữ định nghĩa event sau khi lịch hoàn tất. Event không tự lặp lại chỉ vì được preserve.

Nếu cần kiểm toán, giữ lại định nghĩa event có thể hữu ích, nhưng nên có quy trình dọn các event đã hoàn tất. Nếu không cần lưu định nghĩa sau khi chạy, mặc định `NOT PRESERVE` thường phù hợp.

### 3.3. Lịch một lần đã qua thời điểm

Không tạo event với thời điểm quá khứ rồi giả định nó sẽ được chạy ngay theo cách mong muốn. Hãy kiểm tra schedule, trạng thái scheduler và version cụ thể. Với tác vụ cần bù dữ liệu, tạo quy trình đối soát theo tham số thời gian thay vì phụ thuộc vào một event quá hạn.

## 4. Lịch định kỳ bằng EVERY

Event lặp dùng `EVERY` kèm một interval:

```sql
CREATE EVENT ev_refresh_hourly_metrics
ON SCHEDULE EVERY 1 HOUR
DO
    CALL sp_refresh_hourly_metrics();
```

Các đơn vị thường dùng gồm `SECOND`, `MINUTE`, `HOUR`, `DAY`, `WEEK`, `MONTH`, `QUARTER`, `YEAR` và các tổ hợp interval được MySQL hỗ trợ.

### 4.1. EVERY với STARTS

`STARTS` xác định thời điểm bắt đầu lịch định kỳ:

```sql
CREATE EVENT ev_daily_cleanup
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 02:00:00'
DO
    CALL sp_cleanup_expired_sessions();
```

Nếu không chỉ định `STARTS`, lịch bắt đầu theo quy tắc mặc định của MySQL kể từ lúc tạo event. Với job production, nên chỉ định mốc bắt đầu để lịch dễ kiểm tra và triển khai lặp lại.

### 4.2. EVERY với ENDS

`ENDS` xác định mốc kết thúc lịch định kỳ:

```sql
CREATE EVENT ev_campaign_reminder
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 09:00:00'
ENDS '2026-12-31 09:00:00'
ON COMPLETION PRESERVE
DO
    CALL sp_send_campaign_reminder();
```

Sau mốc kết thúc, event không tiếp tục được lên lịch. `ON COMPLETION PRESERVE` giữ định nghĩa sau khi lịch kết thúc; nếu không preserve, event có thể được tự động xóa khi hoàn tất lịch.

### 4.3. Lịch theo tuần hoặc tháng

Ví dụ chạy mỗi thứ Hai theo một mốc bắt đầu:

```sql
CREATE EVENT ev_weekly_inventory_report
ON SCHEDULE EVERY 1 WEEK
STARTS '2026-12-07 07:00:00'
DO
    CALL sp_build_inventory_report();
```

Ví dụ chạy mỗi tháng:

```sql
CREATE EVENT ev_monthly_billing_close
ON SCHEDULE EVERY 1 MONTH
STARTS '2027-01-01 01:00:00'
DO
    CALL sp_close_previous_billing_period();
```

Đối với lịch tháng, cần kiểm tra quy tắc ngày cuối tháng và mốc bắt đầu thực tế. Không tự suy ra rằng mọi tháng đều có cùng số ngày hoặc lịch sẽ luôn rơi đúng ngày 31.

### 4.4. Thay đổi lịch sau khi tạo

Dùng `ALTER EVENT` để thay đổi lịch, trạng thái hoặc thuộc tính:

```sql
ALTER EVENT ev_refresh_hourly_metrics
ON SCHEDULE EVERY 2 HOUR
STARTS CURRENT_TIMESTAMP + INTERVAL 2 HOUR
ENABLE;
```

Đọc lại `SHOW CREATE EVENT` và metadata sau khi thay đổi để xác nhận lịch mới. `ALTER EVENT` không phải cách chạy event ngay lập tức; nếu cần chạy thủ công, gọi procedure mà event sử dụng theo quy trình riêng.

## 5. ENABLE, DISABLE và trạng thái event

Scheduler có thể đang ON trong khi một event cụ thể bị disable. Hai trạng thái này độc lập.

### 5.1. Tạo event nhưng chưa chạy

```sql
CREATE EVENT ev_rebuild_search_summary
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_TIMESTAMP + INTERVAL 1 DAY
DISABLE
DO
    CALL sp_rebuild_search_summary();
```

`DISABLE` hữu ích khi triển khai trước, kiểm tra quyền và metadata, rồi mới enable sau khi được phê duyệt.

### 5.2. Bật và tắt event

```sql
ALTER EVENT ev_rebuild_search_summary ENABLE;

ALTER EVENT ev_rebuild_search_summary DISABLE;
```

Tắt event không xóa định nghĩa và không nhất thiết dừng một lần thực thi đang chạy. Khi cần dừng job đang chạy, phải kiểm tra session/thread tương ứng và quy trình hủy công việc an toàn.

### 5.3. DISABLE ON SLAVE

Trong topology replication, event được tạo ở source có thể được replicate tới replica. Nếu chỉ primary được phép thực thi job, có thể dùng:

```sql
CREATE EVENT ev_primary_daily_rollup
ON SCHEDULE EVERY 1 DAY
STARTS CURRENT_TIMESTAMP + INTERVAL 1 DAY
DISABLE ON SLAVE
DO
    CALL sp_refresh_daily_rollup();
```

`DISABLE ON SLAVE` đặt trạng thái event để nó không được thực thi trên replica theo cơ chế event scheduler. Hãy kiểm tra trạng thái thực tế trên từng node sau khi replication DDL và sau failover. Không dựa vào tên host hoặc giả định rằng chỉ một server sẽ có scheduler ON.

## 6. Múi giờ của server, session và event

MySQL có nhiều lớp múi giờ. Nhầm lẫn giữa chúng có thể khiến event chạy lệch giờ hoặc ghi timestamp không như mong đợi.

### 6.1. Múi giờ server

Kiểm tra:

```sql
SELECT
    @@GLOBAL.time_zone AS global_time_zone,
    @@SYSTEM_TIME_ZONE AS system_time_zone;
```

- `@@GLOBAL.time_zone` là giá trị múi giờ mặc định cho session mới.
- `@@SYSTEM_TIME_ZONE` phản ánh múi giờ hệ thống mà server nhận diện khi khởi động.

Nếu `time_zone = 'SYSTEM'`, session sử dụng múi giờ hệ thống. Điều này có thể phụ thuộc cấu hình OS/container và làm lịch khó dự đoán khi di chuyển môi trường.

### 6.2. Múi giờ session

Kiểm tra session hiện tại:

```sql
SELECT @@SESSION.time_zone;
```

Đặt múi giờ cho session:

```sql
SET time_zone = '+00:00';
```

Hoặc dùng tên múi giờ nếu time zone tables đã được nạp:

```sql
SET time_zone = 'Asia/Ho_Chi_Minh';
```

Giá trị `time_zone` của session tại thời điểm tạo event được lưu thành múi giờ của event. Vì vậy, không nên tạo event trong một session có múi giờ không xác định hoặc phụ thuộc cấu hình client.

### 6.3. Múi giờ của event

Event lưu múi giờ riêng, có thể xem trong `INFORMATION_SCHEMA.EVENTS.TIME_ZONE` và `SHOW CREATE EVENT`.

Khi event thực thi, MySQL đặt session thực thi theo múi giờ đã lưu của event. Các hàm thời gian session như `CURRENT_TIMESTAMP`, `CURRENT_DATE` và `NOW()` vì vậy được diễn giải theo múi giờ của event. Nếu cần thời điểm UTC tuyệt đối, dùng `UTC_TIMESTAMP()` hoặc chuyển đổi rõ ràng.

### 6.4. Đặt timezone rõ ràng trước CREATE EVENT

Ví dụ tạo lịch theo UTC:

```sql
SET time_zone = '+00:00';

CREATE EVENT ev_utc_hourly_rollup
ON SCHEDULE EVERY 1 HOUR
STARTS '2026-12-01 00:00:00'
DO
    CALL sp_refresh_hourly_rollup();
```

Ví dụ tạo lịch theo giờ Việt Nam:

```sql
SET time_zone = 'Asia/Ho_Chi_Minh';

CREATE EVENT ev_vietnam_morning_report
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 07:00:00'
DO
    CALL sp_send_morning_report();
```

Ở ví dụ thứ hai, `07:00:00` là giờ địa phương tại múi giờ được lưu cho event. Cần bảo đảm named time zone tồn tại trong MySQL time zone tables.

### 6.5. Không dựa vào timezone mặc định của connection pool

Connection pool có thể tái sử dụng session với `time_zone` đã được thay đổi bởi request trước. Khi triển khai event, hãy đặt session timezone ngay trong script migration và kiểm tra lại trước câu `CREATE EVENT` hoặc `ALTER EVENT`.

Nên ghi nhận timezone đã chọn trong migration review để người vận hành biết lịch đang được tính theo UTC, giờ server hay giờ địa phương.

## 7. UTC hay named time zone?

Chọn múi giờ theo ý nghĩa nghiệp vụ của lịch.

| Yêu cầu | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Chạy sau mỗi 60 phút thực | UTC hoặc offset cố định | Tránh phụ thuộc thay đổi giờ địa phương |
| Chạy mỗi ngày lúc 02:00 giờ địa phương | Named time zone | Lịch theo đồng hồ địa phương |
| Chạy đồng bộ giữa nhiều region | UTC | Một mốc thời gian chung |
| Báo cáo theo ngày làm việc tại Việt Nam | `Asia/Ho_Chi_Minh` | Ranh giới ngày theo lịch nghiệp vụ địa phương |
| Lưu thời điểm sự kiện xuyên hệ thống | UTC | Dễ đối chiếu log và replication |
| Job theo lịch pháp lý ở một quốc gia có DST | Named time zone đã kiểm tra | Giữ ý nghĩa giờ địa phương qua thay đổi DST |

Không có một lựa chọn timezone đúng cho mọi event. Job theo khoảng thời gian thực và job theo giờ làm việc địa phương có ngữ nghĩa khác nhau.

## 8. Daylight Saving Time và time zone tables

### 8.1. Offset cố định và tên múi giờ khác nhau

Offset như `'+07:00'` luôn biểu diễn độ lệch cố định so với UTC. Named time zone như `'America/New_York'` chứa quy tắc lịch sử và quy tắc DST được nạp vào MySQL.

Với vùng có DST, offset cố định không tự đổi khi quy tắc địa phương chuyển từ giờ mùa đông sang giờ mùa hè. Nếu lịch phải giữ nguyên giờ trên đồng hồ địa phương, dùng named time zone.

### 8.2. Nạp time zone tables

Kiểm tra named zone có sẵn:

```sql
SELECT Name
FROM mysql.time_zone_name
WHERE Name IN (
    'UTC',
    'Asia/Ho_Chi_Minh',
    'America/New_York'
);
```

Nếu không có kết quả, time zone tables có thể chưa được nạp hoặc chưa được cập nhật. DBA cần nạp dữ liệu timezone theo hướng dẫn của hệ điều hành và MySQL, thường dùng công cụ `mysql_tzinfo_to_sql` trên hệ thống Unix-like, rồi restart/flush theo quy trình phù hợp.

Không sửa trực tiếp các bảng `mysql.time_zone*` bằng DML thông thường. Cần cập nhật từ bộ dữ liệu timezone đáng tin cậy và kiểm thử sau khi nạp.

### 8.3. DST có thể tạo giờ bị bỏ qua hoặc lặp lại

Ở vùng có DST, khi đồng hồ chuyển tiến, một số giờ địa phương không tồn tại; khi chuyển lùi, một khoảng giờ địa phương có thể xuất hiện hai lần. Lịch chạy theo giờ địa phương cần được kiểm tra tại các ngày chuyển DST.

Nếu job phải chạy đúng một lần cho mỗi khoảng UTC hoặc xử lý dữ liệu theo mốc tuyệt đối, dùng UTC thường dễ kiểm soát hơn. Nếu nghiệp vụ yêu cầu chạy theo giờ địa phương, giữ named zone và thiết kế idempotency key theo kỳ nghiệp vụ để tránh xử lý trùng hoặc bỏ sót.

### 8.4. Kiểm thử chuyển DST

Với lịch tại vùng có DST, hãy kiểm tra:

- Thời điểm UTC tương ứng trước và sau khi chuyển DST.
- Event có chạy ở giờ địa phương bị lặp hay không.
- Nếu giờ địa phương bị bỏ qua, job được xử lý theo chính sách nào.
- Có thể chạy bù theo `business_date` hoặc `period_key` hay không.
- Các node source/replica có cùng dữ liệu timezone hay không.

Đừng chỉ kiểm tra một lần chạy trong tháng bình thường rồi kết luận lịch DST an toàn.

## 9. TIMESTAMP, DATETIME và hàm thời gian trong event

### 9.1. TIMESTAMP

MySQL chuyển giá trị `TIMESTAMP` từ timezone session sang UTC khi lưu và chuyển từ UTC về timezone session khi đọc. Do đó, cùng một giá trị lưu có thể hiển thị khác nhau ở các session timezone khác nhau.

### 9.2. DATETIME

`DATETIME` lưu các thành phần ngày giờ như được cung cấp và không tự chuyển đổi theo timezone session. Ứng dụng phải quy định rõ giá trị là UTC hay giờ địa phương.

### 9.3. So sánh

| Kiểu | Chuyển đổi timezone tự động | Cách dùng thường gặp |
|---|---|---|
| `TIMESTAMP` | Có, giữa session timezone và UTC | Thời điểm thực tế cần hiển thị theo timezone session |
| `DATETIME` | Không | Thời gian lịch nghiệp vụ hoặc giá trị đã chuẩn hóa theo quy ước riêng |

Ví dụ event:

```sql
INSERT INTO event_run_log (
    event_name,
    started_at_utc,
    started_at_session
)
VALUES (
    'ev_vietnam_morning_report',
    UTC_TIMESTAMP(6),
    CURRENT_TIMESTAMP(6)
);
```

Nếu `started_at_session` dùng `DATETIME`, giá trị lưu là giờ session của event. Cột `started_at_utc` thể hiện thời điểm UTC. Đặt tên cột và comment rõ để tránh so sánh hai giá trị có timezone semantics khác nhau.

### 9.4. Tính khoảng thời gian

Nếu cần tính thời gian đã trôi qua, ưu tiên so sánh mốc UTC hoặc timestamp chuẩn hóa. Nếu cần tính “ngày nghiệp vụ” theo giờ Việt Nam, hãy chuyển đổi thời điểm sang `Asia/Ho_Chi_Minh` trước khi lấy ngày hoặc thiết kế cột `business_date` riêng được xác định rõ.

## 10. Nội dung event và stored procedure

Event có thể chứa một câu lệnh hoặc compound statement. Với logic nghiệp vụ dài, nên tách sang stored procedure để dễ kiểm thử và gọi thủ công.

### 10.1. Event gọi procedure

```sql
CREATE EVENT ev_nightly_cleanup
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 02:30:00'
DO
    CALL sp_cleanup_expired_sessions();
```

Procedure có thể chứa transaction, handler, log và logic idempotent theo hợp đồng riêng.

### 10.2. Compound statement trong event

```sql
DELIMITER $$

CREATE EVENT ev_mark_stale_jobs
ON SCHEDULE EVERY 10 MINUTE
DO
BEGIN
    UPDATE background_jobs
    SET status = 'STALE',
        updated_at = CURRENT_TIMESTAMP(6)
    WHERE status = 'RUNNING'
      AND heartbeat_at < CURRENT_TIMESTAMP - INTERVAL 30 MINUTE;

    INSERT INTO event_run_log (
        event_name,
        affected_rows,
        executed_at
    )
    VALUES (
        'ev_mark_stale_jobs',
        ROW_COUNT(),
        CURRENT_TIMESTAMP(6)
    );
END$$

DELIMITER ;
```

`DELIMITER` là lệnh của MySQL client để phân tách statement; nó không phải câu SQL gửi tới server. Với ứng dụng hoặc migration tool, gửi toàn bộ câu `CREATE EVENT ... BEGIN ... END` theo cơ chế multi-statement/routine delimiter mà tool hỗ trợ.

Lưu ý ví dụ trên: `ROW_COUNT()` phải được gọi ngay sau UPDATE nếu muốn ghi số hàng thay đổi của UPDATE. Nếu có câu lệnh khác chen giữa, giá trị có thể phản ánh statement khác. Trong thực tế, có thể gán ngay vào biến cục bộ rồi INSERT log.

### 10.3. Event body không trả result set cho client

Event chạy trong thread nền, không có client đang chờ nhận result set. Không thiết kế body dựa trên việc hiển thị kết quả `SELECT` cho người dùng. Nếu cần lưu kết quả, hãy INSERT vào bảng log/summary hoặc gọi procedure ghi trạng thái.

## 11. DEFINER và quyền thực thi

Event chạy trong security context của `DEFINER`. Đây là tài khoản được gắn với event khi tạo hoặc thay đổi.

### 11.1. Tạo event với definer rõ ràng

```sql
CREATE DEFINER = 'job_runner'@'localhost'
EVENT ev_refresh_customer_summary
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 03:00:00'
DO
    CALL app_db.sp_refresh_customer_summary();
```

Tài khoản definer cần tồn tại và có quyền cần thiết để thực thi body, bao gồm `EXECUTE` trên procedure được gọi và quyền dữ liệu mà procedure cần theo security context của nó.

Không dùng `root` làm definer cho job ứng dụng. Tạo tài khoản riêng với quyền tối thiểu cần thiết, quản lý vòng đời tài khoản và kiểm tra definer khi restore hoặc failover sang server khác.

### 11.2. Quyền quản lý event

Các quyền liên quan thường gồm:

- `EVENT` trên schema để tạo, thay đổi hoặc xóa event.
- Quyền quản trị system variable phù hợp để bật/tắt `event_scheduler`.
- `EXECUTE` trên stored procedure được event gọi.
- Quyền SELECT/INSERT/UPDATE/DELETE trên bảng mà routine thực sự thao tác, tùy `SQL SECURITY` của routine.
- Quyền xem metadata phù hợp để kiểm tra event.

Ví dụ cấp quyền EVENT trên schema:

```sql
GRANT EVENT ON app_db.* TO 'job_deployer'@'localhost';
```

Đây là quyền quản lý event trong schema; nó không tự cấp quyền cho definer chạy các câu SQL bên trong event.

### 11.3. Kiểm tra definer sau restore/migration

```sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    STATUS,
    TIME_ZONE
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'app_db'
ORDER BY EVENT_NAME;
```

Nếu definer không tồn tại hoặc thiếu quyền, event có thể không chạy thành công. Hãy kiểm tra lỗi trong server log và quyền của tài khoản được lưu trong metadata.

## 12. Quản lý event: SHOW, ALTER và DROP

### 12.1. Liệt kê event

```sql
SHOW EVENTS FROM app_db;
```

Hoặc:

```sql
SELECT
    EVENT_SCHEMA,
    EVENT_NAME,
    DEFINER,
    TIME_ZONE,
    EVENT_TYPE,
    EXECUTE_AT,
    INTERVAL_VALUE,
    INTERVAL_FIELD,
    STARTS,
    ENDS,
    STATUS,
    ON_COMPLETION,
    LAST_EXECUTED
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = 'app_db'
ORDER BY EVENT_NAME;
```

### 12.2. Xem định nghĩa event

```sql
SHOW CREATE EVENT app_db.ev_refresh_customer_summary;
```

Đối chiếu schedule, timezone, definer, status, completion policy và body với migration source control.

### 12.3. Tạm dừng event

```sql
ALTER EVENT app_db.ev_refresh_customer_summary DISABLE;
```

Sau khi xử lý sự cố:

```sql
ALTER EVENT app_db.ev_refresh_customer_summary ENABLE;
```

Trước khi enable lại, xác minh job không còn chạy từ scheduler khác và dữ liệu chưa được xử lý trùng.

### 12.4. Xóa event

```sql
DROP EVENT IF EXISTS app_db.ev_old_monthly_report;
```

`DROP EVENT` xóa định nghĩa event. Nó không phải thao tác rollback dữ liệu mà event đã ghi trước đó.

## 13. Giám sát lịch và lần thực thi

### 13.1. LAST_EXECUTED

`INFORMATION_SCHEMA.EVENTS.LAST_EXECUTED` cho biết thời điểm event được thực thi gần nhất theo metadata server. Đây là một chỉ báo hữu ích nhưng không thay thế log nghiệp vụ về kết quả thành công/thất bại.

### 13.2. Tạo bảng log riêng

```sql
CREATE TABLE event_run_log (
    run_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_name VARCHAR(128) NOT NULL,
    started_at_utc DATETIME(6) NOT NULL,
    finished_at_utc DATETIME(6) NULL,
    status VARCHAR(20) NOT NULL,
    affected_rows BIGINT NULL,
    error_message TEXT NULL,
    PRIMARY KEY (run_id),
    KEY idx_event_run_name_started (event_name, started_at_utc)
) ENGINE = InnoDB;
```

Event hoặc procedure được gọi có thể ghi một hàng bắt đầu và cập nhật kết quả hoàn tất. Nếu cần log lỗi tồn tại sau rollback, thiết kế nơi ghi log và transaction boundary riêng; log nằm trong cùng transaction với dữ liệu nghiệp vụ sẽ bị rollback cùng transaction đó.

### 13.3. Phân biệt đã chạy với đã thành công

Một event có thể được dispatch nhưng body gặp lỗi. `LAST_EXECUTED` không phải status nghiệp vụ. Hãy ghi rõ:

- `STARTED` khi bắt đầu.
- `SUCCEEDED` sau khi công việc hoàn tất.
- `FAILED` khi handler ghi nhận lỗi.
- Thời điểm bắt đầu/kết thúc UTC.
- Kỳ dữ liệu hoặc `business_date` đã xử lý.
- Số hàng đọc/ghi và mã lỗi nếu có.

### 13.4. Kiểm tra thread và trạng thái server

Có thể kiểm tra process list để tìm event scheduler hoặc thread thực thi event:

```sql
SHOW PROCESSLIST;
```

Tên thread có thể khác theo version và trạng thái. Khi điều tra, kết hợp process list, server error log, `INFORMATION_SCHEMA.EVENTS` và bảng run log của ứng dụng.

## 14. Tránh chạy chồng và bảo đảm idempotency

Không nên giả định một lần chạy event luôn kết thúc trước occurrence kế tiếp. Nếu procedure chạy lâu hơn chu kỳ, các lần chạy có thể chồng lấn tùy lịch và trạng thái server.

### 14.1. Thiết kế idempotent theo kỳ

Thay vì “cộng thêm doanh thu ngày hôm qua” mỗi lần event chạy, hãy tính lại hoặc upsert theo khóa duy nhất `(business_date, customer_id)`. Như vậy, retry cùng một kỳ không tạo bản ghi trùng hoặc cộng số liệu hai lần.

### 14.2. Dùng bảng job state

Một bảng trạng thái có thể lưu:

- Tên job.
- Kỳ cần xử lý (`period_key`).
- Trạng thái `READY`, `RUNNING`, `SUCCEEDED`, `FAILED`.
- Thời điểm claim và lease hết hạn.
- Số lần thử và thông báo lỗi.

Việc claim một kỳ phải atomic bằng transaction và unique key/row lock để hai lần event hoặc hai node không cùng xử lý một kỳ ngoài ý muốn.

### 14.3. Advisory lock khi cần khóa theo tên job

MySQL cung cấp `GET_LOCK()` và `RELEASE_LOCK()` để lấy named lock theo connection. Ví dụ procedure có thể lấy lock không chờ:

```sql
SET v_lock_result = GET_LOCK('app_db:daily_sales', 0);

IF v_lock_result = 1 THEN
    -- Thực hiện job.
    DO RELEASE_LOCK('app_db:daily_sales');
ELSE
    -- Đã có session khác giữ lock hoặc có lỗi khi lấy lock.
    -- Ghi nhận trạng thái bỏ qua/không lấy được lock theo quy ước.
END IF;
```

Đoạn trên là phần minh họa bên trong procedure; cần khai báo biến, handler và cleanup trong `EXIT HANDLER` để lock luôn được nhả khi có lỗi. `GET_LOCK()` gắn với connection, không phải transaction; `COMMIT` hoặc `ROLLBACK` không tự nhả named lock. Khi connection đóng, lock được giải phóng.

Named lock chỉ bảo vệ các session dùng cùng tên lock trên cùng MySQL server. Nó không tự tạo distributed lock giữa các server độc lập. Với replication/failover, cần thêm quy tắc chỉ một node active và cơ chế fencing/lease ở tầng điều phối nếu yêu cầu nghiêm ngặt.

## 15. Event Scheduler trong replication và failover

Trong replication topology, event DDL có thể được replicate cùng schema. Nếu event chạy trên cả source và replica, job có thể thực thi trùng và ghi dữ liệu không mong muốn.

Checklist cho primary-only job:

1. Xác định node nào được phép chạy event.
2. Tạo event với `DISABLE ON SLAVE` nếu phù hợp với topology.
3. Kiểm tra `STATUS` trên source và replica sau khi replicate.
4. Kiểm tra `event_scheduler` trên từng node.
5. Xác nhận definer và quyền tồn tại trên node sẽ chạy.
6. Khi failover, có quy trình enable event trên primary mới và disable trên node cũ.
7. Dùng idempotency/unique period key để giảm thiệt hại nếu có lần chạy trùng.

`DISABLE ON SLAVE` không thay thế quy trình failover. Khi vai trò source/replica thay đổi, phải xác minh lại trạng thái event và scheduler thay vì giả định metadata tự phản ánh chính xác vai trò ứng dụng.

## 16. Ví dụ hoàn chỉnh: báo cáo mỗi ngày theo giờ Việt Nam

### 16.1. Stored procedure xử lý một ngày

Procedure nhận ngày nghiệp vụ rõ ràng để có thể chạy thủ công hoặc chạy bù:

```sql
DELIMITER $$

CREATE PROCEDURE sp_refresh_daily_sales(IN p_business_date DATE)
BEGIN
    IF p_business_date IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'business date is required';
    END IF;

    START TRANSACTION;

    DELETE FROM daily_customer_sales
    WHERE sales_date = p_business_date;

    INSERT INTO daily_customer_sales (
        sales_date,
        customer_id,
        order_count,
        total_amount
    )
    SELECT
        p_business_date,
        customer_id,
        COUNT(*),
        SUM(total_amount)
    FROM orders
    WHERE status = 'PAID'
      AND created_at >= CONVERT_TZ(
          CONCAT(p_business_date, ' 00:00:00'),
          'Asia/Ho_Chi_Minh', '+00:00'
      )
      AND created_at < CONVERT_TZ(
          CONCAT(p_business_date + INTERVAL 1 DAY, ' 00:00:00'),
          'Asia/Ho_Chi_Minh', '+00:00'
      )
    GROUP BY customer_id;

    COMMIT;
END$$

DELIMITER ;
```

Ví dụ giả định `orders.created_at` lưu thời điểm UTC theo một quy ước nhất quán. Nếu cột là `TIMESTAMP`, cách so sánh còn chịu ảnh hưởng session timezone; cần xác định kiểu cột và semantics trước khi áp dụng. Nếu timezone tables chưa được nạp, `CONVERT_TZ()` với named zone có thể trả `NULL`.

Trong production, procedure cần handler `SQLEXCEPTION` để rollback khi lỗi. Ví dụ được rút gọn để làm rõ cách truyền `business_date`; không triển khai nguyên trạng nếu chưa bổ sung handler và quyền.

### 16.2. Tạo event theo timezone Việt Nam

Đặt timezone của session trước khi tạo event:

```sql
SET time_zone = 'Asia/Ho_Chi_Minh';

CREATE DEFINER = 'job_runner'@'localhost'
EVENT ev_daily_sales_vietnam
ON SCHEDULE EVERY 1 DAY
STARTS '2026-12-01 02:15:00'
ON COMPLETION PRESERVE
ENABLE
DO
    CALL sp_refresh_daily_sales(CURRENT_DATE - INTERVAL 1 DAY);
```

Event chạy lúc 02:15 theo múi giờ đã lưu. `CURRENT_DATE` bên trong event được đánh giá theo timezone của event, nên tham số là ngày lịch địa phương hôm trước.

Nếu dữ liệu nguồn lưu UTC trong `DATETIME`, procedure cần chuyển ranh giới ngày địa phương sang UTC như ví dụ. Nếu dữ liệu nguồn dùng `TIMESTAMP`, kiểm tra session timezone của event và so sánh đúng semantics; không chuyển đổi hai lần.

### 16.3. Kiểm tra sau khi tạo

```sql
SHOW CREATE EVENT ev_daily_sales_vietnam;

SELECT
    EVENT_NAME,
    TIME_ZONE,
    EVENT_TYPE,
    STARTS,
    ENDS,
    STATUS,
    ON_COMPLETION,
    LAST_EXECUTED,
    DEFINER
FROM information_schema.EVENTS
WHERE EVENT_SCHEMA = DATABASE()
  AND EVENT_NAME = 'ev_daily_sales_vietnam';
```

Đối chiếu `TIME_ZONE`, `STARTS`, `STATUS` và `DEFINER` với yêu cầu vận hành. Kiểm tra thêm `@@GLOBAL.event_scheduler` và log của procedure.

### 16.4. Chạy bù một ngày bị bỏ lỡ

Không cần tạo event quá khứ để chạy bù. Gọi procedure trực tiếp với ngày cần đối soát:

```sql
CALL sp_refresh_daily_sales('2026-11-30');
```

Nhờ procedure nhận `business_date`, cùng một ngày có thể được chạy lại theo cách idempotent. Trước khi chạy bù, xác nhận transaction, nguồn dữ liệu đã đầy đủ và job không chạy đồng thời cho cùng kỳ.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Event không chạy | `event_scheduler=OFF` hoặc `DISABLED` | Kiểm tra global variable và cấu hình khởi động |
| Event đang DISABLE | Event riêng bị tắt dù scheduler ON | `SHOW CREATE EVENT`, `ALTER EVENT ... ENABLE` sau khi xác minh |
| Event chạy lệch giờ | Timezone session lúc tạo khác dự kiến | Kiểm tra `TIME_ZONE`, `STARTS`, timezone server/session |
| Named zone không dùng được | Time zone tables chưa nạp hoặc cũ | Nạp/cập nhật timezone tables theo quy trình DBA |
| `CONVERT_TZ()` trả NULL | Named zone không tồn tại trong timezone tables hoặc tham số không hợp lệ | Kiểm tra `mysql.time_zone_name` và input |
| Event không thực thi được procedure | Definer thiếu `EXECUTE` hoặc routine privilege | Kiểm tra `DEFINER`, `SHOW CREATE EVENT`, quyền routine |
| Event chạy trên replica | Trạng thái event/scheduler trên replica không đúng | Kiểm tra `DISABLE ON SLAVE`, event status và failover policy |
| Job chạy hai lần | Event overlap, nhiều node active hoặc retry không idempotent | Unique period key, claim atomic, named lock và fencing |
| Không biết job thành công hay chưa | Chỉ dựa vào `LAST_EXECUTED` | Ghi run log với trạng thái và lỗi nghiệp vụ |
| Scheduler bật lại nhưng thiếu kỳ dữ liệu | Không có cơ chế catch-up theo business period | Đối soát các kỳ còn thiếu và gọi procedure chạy bù |
| Event một lần biến mất | `ON COMPLETION NOT PRESERVE` | Dùng `PRESERVE` nếu cần giữ metadata hoặc lưu migration source |
| Event đã disable nhưng job vẫn đang chạy | DISABLE không phải cơ chế kill execution hiện tại | Tìm session/thread và dừng theo quy trình an toàn |

## 18. Checklist triển khai event production

- [ ] Đã xác định job phù hợp chạy trong MySQL hay cần scheduler bên ngoài.
- [ ] Đã kiểm tra `@@GLOBAL.event_scheduler`.
- [ ] Đã chọn lịch một lần (`AT`) hoặc định kỳ (`EVERY`).
- [ ] Đã xác định rõ `STARTS`, `ENDS` và `ON COMPLETION`.
- [ ] Đã chọn `ENABLE` hay `DISABLE` ở thời điểm triển khai.
- [ ] Đã đặt session `time_zone` tường minh trước CREATE/ALTER EVENT.
- [ ] Đã kiểm tra `INFORMATION_SCHEMA.EVENTS.TIME_ZONE`.
- [ ] Đã nạp và cập nhật named time zone tables nếu dùng named zone.
- [ ] Đã xác định lịch cần UTC, offset cố định hay giờ địa phương có DST.
- [ ] Đã kiểm thử giờ bị bỏ qua/lặp nếu timezone có DST.
- [ ] Đã kiểm tra `TIMESTAMP`/`DATETIME` và quy ước UTC/local của dữ liệu nguồn.
- [ ] Đã tạo definer riêng với quyền tối thiểu và xác nhận tồn tại trên node chạy job.
- [ ] Đã kiểm tra EVENT, EXECUTE và quyền truy cập dữ liệu cần thiết.
- [ ] Đã xác định node nào được phép chạy event trong replication/failover.
- [ ] Đã kiểm tra `DISABLE ON SLAVE` nếu job chỉ chạy trên primary.
- [ ] Procedure có transaction/handler phù hợp và có thể chạy thủ công.
- [ ] Job idempotent theo kỳ và có cơ chế chống chạy chồng.
- [ ] Có bảng log hoặc cơ chế quan sát kết quả thành công/thất bại.
- [ ] Có quy trình đối soát và chạy bù khi scheduler tắt hoặc job thất bại.
- [ ] Đã kiểm tra định nghĩa bằng `SHOW CREATE EVENT` và metadata sau triển khai.

## 19. Kết luận

Event Scheduler cho phép MySQL thực thi tác vụ SQL theo lịch một lần hoặc định kỳ. `AT` xác định thời điểm chạy một lần; `EVERY` kết hợp `STARTS` và `ENDS` xác định lịch lặp. `ON COMPLETION` quyết định event có được giữ sau khi lịch hoàn tất; `ENABLE`/`DISABLE` điều khiển trạng thái của từng event, độc lập với biến global `event_scheduler`.

Múi giờ session tại lúc tạo hoặc thay đổi event được lưu thành timezone của event. Khi chạy, event dùng timezone đó cho các hàm thời gian theo session. Hãy chọn UTC cho lịch theo thời gian tuyệt đối và named time zone cho lịch theo giờ địa phương; nạp timezone tables và kiểm thử DST nếu có. Quản lý definer, quyền, replication, idempotency, log và quy trình chạy bù để event có thể vận hành an toàn khi server restart, scheduler tắt hoặc một lần chạy thất bại.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual: Using the Event Scheduler](https://dev.mysql.com/doc/refman/8.4/en/events.html)
- [MySQL 8.4 Reference Manual: CREATE EVENT Statement](https://dev.mysql.com/doc/refman/8.4/en/create-event.html)
- [MySQL 8.4 Reference Manual: ALTER EVENT Statement](https://dev.mysql.com/doc/refman/8.4/en/alter-event.html)
- [MySQL 8.4 Reference Manual: The INFORMATION_SCHEMA EVENTS Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-events-table.html)
- [MySQL 8.4 Reference Manual: Time Zone Support](https://dev.mysql.com/doc/refman/8.4/en/time-zone-support.html)
- [MySQL 8.4 Reference Manual: Time Zone Variables](https://dev.mysql.com/doc/refman/8.4/en/time-zone-variables.html)
- [MySQL 8.4 Reference Manual: Replication and Events](https://dev.mysql.com/doc/refman/8.4/en/replication-features-events.html)

# Xử lý sự cố

## Incorrect datetime, zero date và lỗi chuyển đổi múi giờ

Lỗi ngày giờ trong MySQL thường xuất hiện khi dữ liệu đi qua nhiều hệ thống: biểu mẫu nhận ngày theo định dạng địa phương, ứng dụng Java phân tích chuỗi, Connector/J chuyển giá trị qua JDBC, MySQL áp dụng SQL mode và session time zone, rồi truy vấn đọc dữ liệu trong một múi giờ khác. Một giá trị có thể bị từ chối, bị chuyển thành zero date, bị lệch vài giờ hoặc không thể đọc lại bằng driver.

Trong module **DATABASE_MYSQL**, bạn học cách làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời. Bạn cũng thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Bài này áp dụng những kỹ năng đó để chẩn đoán dữ liệu ngày giờ, hiểu SQL mode và timezone, kiểm tra luồng JDBC, rồi sửa dữ liệu cũ mà không làm mất ý nghĩa nghiệp vụ.

Các ví dụ hướng đến MySQL 8.0/8.4, InnoDB và Connector/J hiện đại. Một số hành vi phụ thuộc phiên bản, SQL mode, kiểu cột và driver; hãy ghi nhận cấu hình thật của môi trường trước khi kết luận.

### 1. Phân biệt DATE, DATETIME và TIMESTAMP

Chọn đúng kiểu dữ liệu là bước đầu để tránh lỗi. Ba kiểu này không có cùng ngữ nghĩa:

| Kiểu | Ý nghĩa | Có chuyển đổi theo session time zone? | Phạm vi tổng quát |
|---|---|---|---|
| DATE | Ngày lịch, không có giờ | Không | 1000-01-01 đến 9999-12-31 |
| DATETIME | Ngày và giờ theo đồng hồ địa phương/ngữ cảnh nghiệp vụ | Không | 1000-01-01 00:00:00 đến 9999-12-31 23:59:59 |
| TIMESTAMP | Một thời điểm (instant) | Có; chuyển session time zone sang UTC khi ghi và ngược lại khi đọc | Thông thường từ 1970-01-01 00:00:01 UTC đến 2038-01-19 03:14:07 UTC |

Các kiểu TIME, DATETIME và TIMESTAMP có thể lưu fractional seconds với độ chính xác từ 0 đến 6 chữ số, ví dụ DATETIME(6) hoặc TIMESTAMP(6). Nếu cột chỉ có độ chính xác 0, phần microsecond đầu vào có thể bị làm tròn hoặc cắt theo SQL mode và quy tắc phiên bản.

#### 1.1. Khi nào dùng từng kiểu?

- Dùng DATE cho ngày sinh, ngày hóa đơn, ngày nghỉ hoặc ngày hiệu lực mà không có thời điểm trong ngày.
- Dùng DATETIME cho giờ mở cửa, lịch hẹn theo giờ địa phương, thời điểm nghiệp vụ được ghi như một giá trị lịch không tự đổi khi người xem ở múi giờ khác.
- Dùng TIMESTAMP cho thời điểm sự kiện cần biểu diễn cùng một instant trên toàn hệ thống, như thời điểm tạo bản ghi, nhận webhook hoặc ghi log.

TIMESTAMP lưu giá trị theo UTC và chuyển đổi theo session time_zone khi ghi/đọc. Nó không lưu tên múi giờ gốc hoặc offset mà người dùng đã chọn. DATETIME lưu các thành phần ngày/giờ như được cung cấp, không tự biết chúng thuộc múi giờ nào.

Ví dụ, cùng chuỗi 2026-06-01 09:00:00:

- Nếu lưu vào DATETIME, MySQL giữ 09:00:00 như một giá trị lịch.
- Nếu lưu vào TIMESTAMP trong session Asia/Ho_Chi_Minh, MySQL diễn giải 09:00 theo session đó, quy đổi thành UTC để lưu và chuyển về session time_zone khi đọc.

Không chọn TIMESTAMP chỉ vì tên cột có chữ timestamp. Nếu cần lưu lịch họp lúc 09:00 tại một thành phố, cần lưu cả múi giờ IANA hoặc quy tắc địa điểm; một DATETIME đơn lẻ không chứa đủ thông tin đó.

### 2. Zero date, zero-in-date và ngày không hợp lệ

MySQL có thể gặp các giá trị đặc biệt hoặc không hợp lệ trong dữ liệu lịch sử:

| Dạng | Ví dụ | Vấn đề |
|---|---|---|
| Zero date | 0000-00-00 | Không đại diện cho ngày lịch hợp lệ |
| Zero month | 2024-00-15 | Tháng bằng 0 |
| Zero day | 2024-01-00 | Ngày bằng 0 |
| Ngày ngoài lịch | 2024-02-30 | Tháng 2 không có ngày 30 |
| Sai tháng | 2024-13-01 | Tháng vượt phạm vi |
| Sai năm nhuận | 2023-02-29 | Năm 2023 không phải năm nhuận |

Zero date thường được dùng như sentinel trong hệ thống cũ để biểu thị “chưa biết”, “không áp dụng” hoặc “chưa nhập”. Cách này làm mơ hồ dữ liệu và có thể không tương thích với SQL mode nghiêm ngặt, driver Java hoặc phiên bản MySQL mới.

Nếu một trường chưa có ngày, ưu tiên NULL khi nghiệp vụ cho phép. Nếu có một ngày mặc định thật sự mang ý nghĩa, chọn một ngày hợp lệ và mô tả ý nghĩa trong schema/ứng dụng. Không thay mọi zero date bằng một ngày tùy ý.

### 3. SQL mode quyết định cách MySQL xử lý ngày sai

SQL mode ảnh hưởng việc MySQL từ chối, cảnh báo hoặc chấp nhận dữ liệu ngày giờ không hợp lệ. Trước khi điều tra, đọc cả global và session mode:

~~~sql
SELECT
  @@GLOBAL.sql_mode AS global_sql_mode,
  @@SESSION.sql_mode AS session_sql_mode,
  @@SESSION.time_zone AS session_time_zone,
  @@GLOBAL.time_zone AS global_time_zone;
~~~

Các mode cần biết:

| SQL mode | Tác động |
|---|---|
| STRICT_TRANS_TABLES | Chế độ nghiêm ngặt cho transactional table; giá trị sai thường gây lỗi thay vì âm thầm điều chỉnh |
| STRICT_ALL_TABLES | Áp dụng strict behavior rộng hơn cho các storage engine |
| NO_ZERO_DATE | Kiểm soát zero date 0000-00-00 |
| NO_ZERO_IN_DATE | Kiểm soát ngày có tháng hoặc ngày bằng 0 |
| ALLOW_INVALID_DATES | Nới kiểm tra đầy đủ ngày cho DATE/DATETIME; vẫn kiểm tra phạm vi tháng 1-12 và ngày 1-31 |
| TIME_TRUNCATE_FRACTIONAL | Cắt phần fractional seconds thay vì làm tròn khi độ chính xác đầu vào lớn hơn cột |

NO_ZERO_DATE và NO_ZERO_IN_DATE đã bị deprecated trong các bản MySQL 8.0 mới; cách chúng tương tác với strict mode phụ thuộc phiên bản. Không dựa vào việc bật riêng hai mode này như giải pháp lâu dài. Xác minh tài liệu đúng phiên bản và đặt chính sách strict nhất quán cho ứng dụng.

ALLOW_INVALID_DATES không biến một ngày sai thành ngày hợp lệ. Nó có thể cho phép lưu giá trị như 2024-02-31 trong DATE/DATETIME khi mode được bật; phép tính ngày sau đó có thể không có ý nghĩa nghiệp vụ. Chỉ dùng cho trường hợp nhập dữ liệu có kiểm soát, không dùng để bỏ qua validation.

Ví dụ kiểm thử trong session riêng:

~~~sql
SET SESSION sql_mode =
  'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,NO_ENGINE_SUBSTITUTION';

CREATE TEMPORARY TABLE date_mode_test (
  id BIGINT PRIMARY KEY,
  event_date DATE NULL
) ENGINE=InnoDB;

INSERT INTO date_mode_test VALUES (1, '2024-02-29');
-- Các giá trị dưới đây cần được thử riêng vì có thể phát sinh lỗi:
INSERT INTO date_mode_test VALUES (2, '2024-02-30');
INSERT INTO date_mode_test VALUES (3, '0000-00-00');
~~~

Không chạy toàn bộ ví dụ trên production. Câu lệnh lỗi có thể làm dừng script; dùng database kiểm thử và kiểm tra SHOW WARNINGS ngay sau mỗi thao tác có thể sinh warning.

### 4. Phân tích lỗi parse và chuyển đổi ngày

Ứng dụng thường nhận ngày dưới dạng chuỗi. Đừng giả định MySQL sẽ hiểu định dạng theo locale của người dùng. Một chuỗi như 03/04/2026 có thể có nghĩa ngày 3 tháng 4 hoặc ngày 4 tháng 3.

Ưu tiên định dạng trao đổi rõ ràng:

- DATE: YYYY-MM-DD.
- DATETIME: YYYY-MM-DD HH:MM:SS[.fraction].
- TIMESTAMP instant: truyền một instant có timezone/offset rõ ở tầng ứng dụng, rồi chuyển đổi theo chính sách kết nối.

Nếu cần parse trong SQL, STR_TO_DATE() nhận chuỗi và format string:

~~~sql
SELECT
  STR_TO_DATE('2026-04-03', '%Y-%m-%d') AS parsed_date,
  STR_TO_DATE('03/04/2026', '%d/%m/%Y') AS day_first_date,
  STR_TO_DATE('03/04/2026', '%m/%d/%Y') AS month_first_date;
~~~

Hai format cuối tạo ra hai ngày khác nhau. Format string phải được xác định từ hợp đồng dữ liệu, không đoán theo ngôn ngữ máy chủ.

Kiểm tra kết quả parse trước khi ghi:

~~~sql
SELECT
  STR_TO_DATE('2024-02-29', '%Y-%m-%d') AS leap_day,
  STR_TO_DATE('2023-02-29', '%Y-%m-%d') AS invalid_leap_day,
  STR_TO_DATE('2024-13-01', '%Y-%m-%d') AS invalid_month;
SHOW WARNINGS;
~~~

Hành vi kiểm tra đầy đủ của STR_TO_DATE() đã thay đổi trong các bản MySQL 8.0; từ 8.0.35, hàm thực hiện kiểm tra phạm vi ngày đầy đủ hơn và có thể báo lỗi cho ngày không hợp lệ trước đây từng được trả về dưới dạng giá trị chưa chuẩn hóa. Khi nâng cấp, chạy lại bộ test parse trên đúng phiên bản đích.

Tránh dùng INSERT IGNORE để “làm sạch” dữ liệu. IGNORE có thể hạ một số lỗi thành warning và làm dữ liệu được điều chỉnh hoặc thay thế. Sau khi import, đọc warnings và đối chiếu số hàng; tốt hơn là parse/validate ở staging trước khi ghi vào bảng chính.

### 5. Chẩn đoán dữ liệu ngày bất thường

Trước tiên kiểm tra kiểu cột và schema:

~~~sql
SHOW CREATE TABLE appdb.orders;

SELECT
  COLUMN_NAME,
  DATA_TYPE,
  COLUMN_TYPE,
  IS_NULLABLE,
  COLUMN_DEFAULT,
  DATETIME_PRECISION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'appdb'
  AND TABLE_NAME = 'orders'
  AND COLUMN_NAME IN ('created_at', 'delivery_date');
~~~

Kiểm tra NULL và zero date:

~~~sql
SELECT
  COUNT(*) AS total_rows,
  SUM(delivery_date IS NULL) AS null_rows,
  SUM(CAST(delivery_date AS CHAR) = '0000-00-00') AS zero_date_rows,
  SUM(CAST(created_at AS CHAR) = '0000-00-00 00:00:00') AS zero_timestamp_rows
FROM appdb.orders;
~~~

Kiểm tra các phần ngày bằng 0 hoặc chuỗi ngày bất thường trong một đợt audit:

~~~sql
SELECT order_id, delivery_date
FROM appdb.orders
WHERE MONTH(delivery_date) = 0
   OR DAYOFMONTH(delivery_date) = 0;
~~~

Các hàm MONTH() và DAYOFMONTH() trên cột có thể làm MySQL quét nhiều hàng; truy vấn audit này có thể tốn chi phí trên bảng lớn. Chạy ngoài giờ cao điểm hoặc giới hạn theo partition/key range nếu cần. Với dữ liệu kiểu DATE/DATETIME đã được server chuẩn hóa, các giá trị ngày sai có thể đã bị từ chối trước khi lưu; các trường hợp bất thường thường đến từ SQL mode cũ, import hoặc dữ liệu được tạo trên phiên bản khác.

Đối chiếu dữ liệu raw nếu nguồn là CSV hoặc API. Nếu chỉ còn cột DATE đã bị chuyển đổi, có thể không biết chuỗi đầu vào ban đầu là 03/04/2026 hay 04/03/2026. Staging nên giữ cột raw text và trạng thái parse để bảo toàn bằng chứng.

### 6. Hiểu múi giờ server, session và dữ liệu

MySQL có nhiều lớp timezone:

- system_time_zone: múi giờ hệ điều hành được phát hiện khi server khởi động.
- GLOBAL time_zone: mặc định được áp dụng cho session mới.
- SESSION time_zone: múi giờ của kết nối hiện tại; ảnh hưởng TIMESTAMP và các hàm thời gian liên quan.

Kiểm tra:

~~~sql
SELECT
  @@system_time_zone AS system_time_zone,
  @@global.time_zone AS global_time_zone,
  @@session.time_zone AS session_time_zone,
  NOW() AS session_now,
  UTC_TIMESTAMP() AS utc_now,
  CURRENT_TIMESTAMP() AS current_timestamp_value;
~~~

Nếu session time_zone là SYSTEM, MySQL sử dụng timezone hệ thống. Không giả định tất cả session có cùng timezone; connection pool có thể giữ lại session đã bị thay đổi bởi request trước.

Đặt UTC cho session ứng dụng là một chính sách phổ biến:

~~~sql
SET SESSION time_zone = '+00:00';
SELECT @@session.time_zone, NOW(), UTC_TIMESTAMP();
~~~

Nếu ứng dụng dùng pool, đặt session timezone qua cấu hình connection initialization được kiểm chứng hoặc đảm bảo reset khi trả kết nối. Không để một request thay đổi time_zone rồi trả connection bẩn cho request kế tiếp.

### 7. TIMESTAMP chuyển đổi, DATETIME không chuyển đổi

Khi ghi TIMESTAMP, MySQL diễn giải giá trị đầu vào theo session time_zone rồi chuyển thành UTC để lưu. Khi đọc, MySQL chuyển UTC sang session time_zone hiện tại. Vì vậy, hai session khác timezone có thể nhìn thấy giờ khác nhau cho cùng một TIMESTAMP nhưng cùng instant.

DATETIME không tự chuyển đổi. Nếu ghi 09:00 thì đọc từ session UTC hay Asia/Ho_Chi_Minh vẫn là 09:00. Nếu ứng dụng coi DATETIME là UTC nhưng người nhập thực ra cung cấp giờ địa phương, dữ liệu sẽ sai ngữ nghĩa dù chuỗi hiển thị có vẻ hợp lệ.

Ví dụ:

~~~sql
CREATE TEMPORARY TABLE time_zone_demo (
  id INT PRIMARY KEY,
  happened_at TIMESTAMP,
  wall_clock DATETIME
);

SET SESSION time_zone = '+07:00';
INSERT INTO time_zone_demo
VALUES (1, '2026-06-01 09:00:00', '2026-06-01 09:00:00');

SET SESSION time_zone = '+00:00';
SELECT * FROM time_zone_demo;
~~~

Trong ví dụ, happened_at được hiển thị thành 02:00 UTC còn wall_clock vẫn là 09:00. Đây là cùng một giá trị TIMESTAMP được nhìn từ session khác; DATETIME vẫn giữ nguyên các thành phần lịch.

TIMESTAMP có phạm vi nhỏ hơn DATETIME trên MySQL phổ biến, kết thúc vào tháng 1 năm 2038. Không lưu ngày lịch xa trong tương lai hoặc lịch sử quá sớm bằng TIMESTAMP nếu vượt phạm vi; chọn DATETIME khi cần dải năm rộng và tự quản lý timezone ở tầng ứng dụng.

### 8. Timezone tables và CONVERT_TZ()

MySQL hỗ trợ tên múi giờ như Asia/Ho_Chi_Minh hoặc America/New_York khi timezone tables được nạp. Offset cố định như +07:00 không cần tra quy tắc DST, nhưng tên IANA mới biểu diễn quy tắc lịch sử và thay đổi theo luật địa phương.

Kiểm tra chuyển đổi:

~~~sql
SELECT
  CONVERT_TZ(
    '2026-06-01 09:00:00',
    'Asia/Ho_Chi_Minh',
    'UTC'
  ) AS converted_utc;
~~~

Nếu kết quả là NULL, kiểm tra tên timezone và timezone tables. Trên Linux, quản trị viên thường nạp dữ liệu hệ thống bằng mysql_tzinfo_to_sql rồi import vào schema mysql; cách thực hiện phụ thuộc hệ điều hành và quyền quản trị. Sau khi cập nhật dữ liệu timezone của OS, cần cập nhật timezone tables của MySQL theo quy trình vận hành và khởi động lại server theo hướng dẫn phiên bản để các giá trị timezone đã cache được nạp lại.

Không dùng một offset cố định để thay thế tên timezone khi vùng đó có quy tắc DST hoặc thay đổi luật. Ví dụ một vùng có thể chuyển từ UTC-5 sang UTC-4 theo mùa; offset cố định không mô tả được lịch sử hoặc thời điểm tương lai.

### 9. Daylight Saving Time: giờ không tồn tại và giờ bị lặp

Khi một vùng chuyển sang giờ mùa hè, đồng hồ có thể nhảy qua một khoảng thời gian. Một số giờ địa phương không tồn tại. Khi kết thúc DST, một khoảng giờ có thể xuất hiện hai lần.

Điều này tạo ra hai trường hợp:

- **Gap:** giờ địa phương không tồn tại, ví dụ đồng hồ nhảy từ 01:59 lên 03:00; 02:30 không có instant tương ứng.
- **Fold:** giờ địa phương lặp lại, ví dụ 01:30 xuất hiện hai lần với hai UTC offset khác nhau.

Một DATETIME đơn lẻ không thể phân biệt hai instant trong fold và không thể chứng minh giờ thuộc gap. Nếu nghiệp vụ lưu lịch tương lai theo giờ địa phương, nên lưu:

- Local date/time mà người dùng chọn.
- Tên timezone IANA, ví dụ America/New_York.
- Quy tắc xử lý giờ gap/fold (từ chối, đẩy sang giờ hợp lệ kế tiếp, chọn offset sớm/muộn hoặc yêu cầu người dùng xác nhận).
- Instant UTC đã được giải quyết khi nghiệp vụ cần một thời điểm thực thi cụ thể.

Quy tắc DST có thể thay đổi theo luật. Với lịch dài hạn, có thể cần tính lại instant tương lai khi timezone database được cập nhật. Đừng lưu duy nhất offset hiện tại nếu cần áp dụng quy tắc địa phương trong tương lai.

### 10. Các hàm thời gian dễ gây nhầm

| Hàm | Hành vi cần nhớ |
|---|---|
| NOW() / CURRENT_TIMESTAMP() | Trả thời điểm hiện tại theo session time_zone |
| UTC_TIMESTAMP() | Trả thời điểm hiện tại theo UTC |
| CURDATE() | Ngày hiện tại theo session time_zone |
| UTC_DATE() | Ngày hiện tại theo UTC |
| UNIX_TIMESTAMP() | Không tham số: epoch hiện tại; có tham số ngày giờ: diễn giải theo session time_zone |
| FROM_UNIXTIME(epoch) | Chuyển epoch thành ngày giờ theo session time_zone |
| CONVERT_TZ(dt, from_tz, to_tz) | Chuyển giờ giữa hai timezone; có thể trả NULL nếu tên/đầu vào không hợp lệ hoặc thiếu timezone tables |

Ví dụ:

~~~sql
SELECT
  NOW(),
  UTC_TIMESTAMP(),
  UNIX_TIMESTAMP('2026-06-01 09:00:00'),
  FROM_UNIXTIME(1780304400),
  CONVERT_TZ('2026-06-01 09:00:00', '+07:00', '+00:00');
~~~

Epoch 1780304400 tương ứng 2026-06-01 09:00:00 UTC; FROM_UNIXTIME() hiển thị instant đó theo session time_zone hiện tại.

Không trộn giá trị epoch, local datetime và UTC datetime trong cùng một cột mà không có quy ước. Khi so sánh khoảng thời gian, ưu tiên khoảng nửa mở [start, end):

~~~sql
SELECT order_id, created_at
FROM appdb.orders
WHERE created_at >= '2026-06-01 00:00:00'
  AND created_at <  '2026-06-02 00:00:00';
~~~

Cách viết này tránh phải đoán giá trị cuối ngày như 23:59:59.999999 và hoạt động ổn định với cột có fractional seconds.

### 11. Kiểm thử và chẩn đoán từ Java/Connector/J

Java có các kiểu thời gian mang ngữ nghĩa khác nhau:

| Java type | Ý nghĩa phù hợp | MySQL type thường dùng |
|---|---|---|
| LocalDate | Ngày lịch | DATE |
| LocalDateTime | Ngày/giờ không kèm timezone | DATETIME |
| Instant | Một instant trên UTC timeline | TIMESTAMP theo cấu hình UTC rõ ràng |
| java.sql.Timestamp | Giá trị ngày giờ có độ chính xác nano; bản thân object không giữ zone ID, cần quy ước timezone khi bind/read | Chọn TIMESTAMP hoặc DATETIME theo ngữ nghĩa cột và cấu hình driver |

Không dùng LocalDateTime để biểu diễn một instant toàn cầu nếu không có timezone. Không dùng Instant cho lịch địa phương chưa được giải quyết thành instant.

Ví dụ lưu một instant theo chính sách UTC:

~~~java
Instant occurredAt = Instant.parse("2026-06-01T02:00:00Z");
Timestamp value = Timestamp.from(occurredAt);

try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "INSERT INTO appdb.events(occurred_at) VALUES (?)")) {
    ps.setTimestamp(1, value);
    ps.executeUpdate();
}
~~~

Để kết quả nhất quán, cấu hình Connector/J và session time_zone theo một chính sách được thống nhất. Các phiên bản Connector/J mới có thuộc tính như connectionTimeZone, forceConnectionTimeZoneToSession và preserveInstants; kiểm tra tài liệu đúng phiên bản, vì cách driver diễn giải và chuyển đổi kiểu thời gian phụ thuộc các thuộc tính này. Có thể dùng overload setTimestamp/getTimestamp với Calendar khi cần kiểm soát timezone rõ ràng ở JDBC.

Ví dụ kiểm tra round-trip:

~~~java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
         "SELECT occurred_at FROM appdb.events WHERE event_id = ?")) {
    ps.setLong(1, eventId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            Instant actual = rs.getTimestamp("occurred_at").toInstant();
            // So sánh với instant đã ghi theo precision của cột.
        }
    }
}
~~~

Nếu cột là DATETIME, không dùng round-trip trên để giả định MySQL đã lưu timezone. Chuyển đổi LocalDateTime theo timezone nghiệp vụ ở tầng ứng dụng một cách tường minh.

#### 11.1. Connector/J và zero date

Một số hệ thống cũ có thể trả zero date về JDBC. Connector/J có thuộc tính zeroDateTimeBehavior với các lựa chọn như EXCEPTION, CONVERT_TO_NULL và ROUND tùy phiên bản. EXCEPTION giúp phát hiện dữ liệu bất thường; CONVERT_TO_NULL có thể che việc dữ liệu đang chứa sentinel; ROUND có thể tạo một ngày thay thế không đúng nghiệp vụ.

Hãy sửa dữ liệu và schema ở nguồn thay vì dùng cấu hình driver để che zero date. Nếu buộc phải đọc dữ liệu cũ trong giai đoạn chuyển đổi, ghi nhận số lượng và giá trị bị chuyển đổi, sau đó loại bỏ compatibility workaround khi migration hoàn tất.

### 12. Quy trình sửa dữ liệu zero date và sai timezone

Không cập nhật hàng loạt ngay khi thấy zero date. Làm theo các bước:

1. **Sao lưu và giữ bằng chứng:** tạo backup có thể restore; lưu số hàng, khóa chính và giá trị raw.
2. **Phân loại ý nghĩa:** xác định zero date có nghĩa “chưa biết”, “không áp dụng”, dữ liệu import sai hay lỗi timezone.
3. **Kiểm tra nullability:** xác minh cột có cho phép NULL không và ứng dụng có xử lý NULL đúng không.
4. **Lập mapping:** quyết định chuyển thành NULL, ngày hợp lệ lấy từ nguồn khác, hoặc trạng thái riêng.
5. **Chạy staging:** thực hiện mapping trên bản sao, đối chiếu row count và business rule.
6. **Triển khai theo batch:** cập nhật theo primary key trong transaction nhỏ, lưu checkpoint và log số hàng.
7. **Xác minh:** đếm lại zero date, NULL, giá trị ngoài phạm vi và so sánh với báo cáo trước sửa.
8. **Siết schema:** thêm constraint/validation sau khi dữ liệu đã sạch và ứng dụng tương thích.

Nếu zero date biểu thị chưa có ngày, chỉ chuyển sang NULL sau khi cột cho phép NULL và downstream đã được cập nhật:

~~~sql
UPDATE appdb.orders
SET delivery_date = NULL
WHERE CAST(delivery_date AS CHAR) = '0000-00-00';
~~~

Đây là ví dụ cho một cột DATE; phép CAST có thể khiến MySQL quét bảng nên chỉ dùng trong đợt sửa có kiểm soát. Hãy xác minh predicate trên phiên bản và dữ liệu thật, chạy trong staging trước. Với bảng lớn, thêm điều kiện theo primary key và commit từng batch. Nếu zero date mang ý nghĩa nghiệp vụ khác, giữ mapping riêng thay vì chuyển hết thành NULL.

Nếu dữ liệu sai do lệch timezone, không cộng/trừ một số giờ cố định cho toàn bộ bảng khi chưa biết timezone nguồn, khoảng thời gian và DST. Xác định:

- Giá trị ban đầu được nhập theo timezone nào.
- Cột là TIMESTAMP hay DATETIME.
- Session time_zone tại thời điểm ghi.
- Driver/ứng dụng có tự chuyển đổi trước khi gửi không.
- Các bản ghi có thuộc thời kỳ DST hoặc thay đổi luật timezone không.

Sau đó tính lại instant theo nguồn gốc từng nhóm dữ liệu và đối chiếu với log/event bên ngoài. Một sai lệch timezone không thể được sửa chính xác nếu đã mất thông tin timezone nguồn và không còn bằng chứng độc lập.

### 13. Nhập dữ liệu và migration an toàn

Với CSV, file legacy hoặc API, không import chuỗi trực tiếp vào cột DATE/DATETIME trước khi kiểm tra. Dùng staging table lưu raw value:

~~~sql
CREATE TABLE staging.order_dates (
  source_id BIGINT NOT NULL PRIMARY KEY,
  raw_date VARCHAR(80) NULL,
  parsed_date DATE NULL,
  parse_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
  parse_error VARCHAR(255) NULL
) ENGINE=InnoDB;
~~~

Quy trình parse:

- Giữ nguyên raw_date để truy vết.
- Kiểm tra format được khai báo, không đoán theo locale.
- Parse thành kiểu ngày trong ứng dụng hoặc bằng STR_TO_DATE với format rõ.
- Kiểm tra ngày lịch hợp lệ, năm nhuận và giới hạn nghiệp vụ.
- Ghi parse_status là VALID hoặc INVALID và lưu nguyên nhân.
- Chỉ chuyển VALID vào bảng production.

Không dùng NULLIF(raw_date, '0000-00-00') như cách duy nhất để làm sạch. Nó chỉ xử lý đúng một chuỗi và bỏ qua zero-in-date, khoảng trắng, format sai hoặc timezone không rõ.

Với migration đổi kiểu hoặc timezone, ghi lại phiên bản MySQL, SQL mode, session timezone, Connector/J version và cấu hình driver trong báo cáo. Những thông tin này giúp tái tạo kết quả khi môi trường staging và production khác nhau.

### 14. Kiểm thử biên và regression

Một bộ test ngày giờ nên bao gồm:

| Nhóm | Giá trị mẫu | Kỳ vọng |
|---|---|---|
| Ngày thường | 2026-06-15 | Lưu và đọc đúng |
| Ngày nhuận | 2024-02-29 | Hợp lệ |
| Ngày nhuận sai | 2023-02-29 | Bị từ chối |
| Cuối tháng | 2026-04-30, 2026-04-31 | Một hợp lệ, một không hợp lệ |
| Zero date | 0000-00-00 | Bị từ chối theo chính sách |
| Zero-in-date | 2026-00-10, 2026-06-00 | Bị từ chối theo chính sách |
| Ngoài phạm vi | 2026-13-01 | Bị từ chối |
| Fractional seconds | .123456 vào DATETIME(6) | Giữ đúng precision |
| Precision mismatch | .123456 vào DATETIME(3) | Làm tròn/cắt đúng mode |
| UTC/session | Cùng TIMESTAMP đọc ở +00:00 và +07:00 | Hiển thị khác nhưng cùng instant |
| DATETIME | Cùng giá trị đọc ở hai session timezone | Thành phần giờ không đổi |
| DST gap | Giờ địa phương không tồn tại | Theo chính sách đã định |
| DST fold | Giờ địa phương xuất hiện hai lần | Chọn instant/offset rõ ràng |
| TIMESTAMP range | Giá trị sát giới hạn | Không vượt phạm vi cột |

Test thêm NOW(), UTC_TIMESTAMP(), FROM_UNIXTIME() và CONVERT_TZ() trên session thực tế. Kiểm tra connection pool bằng cách thay đổi session time_zone trong một request rồi mượn connection lại để xác nhận baseline được phục hồi.

Sau nâng cấp MySQL hoặc Connector/J, chạy lại regression cho:

- Parse chuỗi ngày và warning/error behavior.
- Zero date compatibility.
- Mapping Java temporal type sang SQL type.
- Session timezone khi kết nối và reconnect.
- Precision microsecond.
- Timezone tables và CONVERT_TZ.
- DST gap/fold và các ngày chuyển luật.

### 15. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
|---|---|---|
| Incorrect date value | Ngày ngoài lịch, zero date hoặc strict SQL mode | Đọc SQL mode, raw input và SHOW WARNINGS |
| Zero date bị từ chối sau upgrade | Strict/zero-date behavior thay đổi hoặc mode khác | So sánh session/global SQL mode và phiên bản nguồn/đích |
| JDBC ném exception khi đọc ngày | Zero date trong dữ liệu và zeroDateTimeBehavior | Truy vấn trực tiếp giá trị, sửa dữ liệu và kiểm tra cấu hình driver |
| Thời điểm lệch 7 giờ | Session time_zone hoặc driver conversion không thống nhất | Đọc @@session.time_zone và cấu hình Connector/J |
| DATETIME không đổi theo timezone | DATETIME không tự chuyển đổi | Xác định lại ý nghĩa cột và chuyển đổi ở tầng ứng dụng nếu cần |
| TIMESTAMP hiển thị khác giữa CLI và Java | Hai session dùng timezone khác nhau | So sánh session timezone trên từng connection |
| CONVERT_TZ trả NULL | Timezone name sai hoặc timezone tables chưa nạp | Kiểm tra tên IANA và timezone tables |
| Lịch chạy sai quanh DST | Giờ gap/fold hoặc chỉ lưu offset cố định | Lưu zone ID và chính sách giải quyết giờ địa phương |
| Ngày bị đổi sau import | Format không rõ, IGNORE hoặc STR_TO_DATE behavior | Đối chiếu raw input, warnings và phiên bản server |
| Microsecond mất | Cột có precision thấp hơn hoặc driver mapping khác | Kiểm tra DATETIME_PRECISION và round-trip |
| Lệch giờ sau khi trả connection về pool | Request trước đổi session time_zone | Kiểm tra reset session và connection initialization |

### 16. Checklist trước khi sửa lỗi ngày giờ

- [ ] Đã xác định kiểu DATE, DATETIME hay TIMESTAMP và ngữ nghĩa nghiệp vụ.
- [ ] Đã đọc global/session SQL mode và timezone.
- [ ] Đã phân biệt zero date, zero-in-date, ngày không hợp lệ và NULL.
- [ ] Đã kiểm tra dữ liệu raw trước parse/import.
- [ ] Đã kiểm tra STR_TO_DATE() trên đúng phiên bản MySQL.
- [ ] Đã ghi nhận fractional seconds precision và mode làm tròn/cắt.
- [ ] Đã xác định TIMESTAMP được ghi/đọc theo session timezone nào.
- [ ] Đã kiểm tra Connector/J và Java temporal type mapping.
- [ ] Đã xác minh timezone tables và kết quả CONVERT_TZ().
- [ ] Đã xác định vùng DST gap/fold nếu lưu giờ địa phương.
- [ ] Đã backup, thử mapping trên staging và xác định ý nghĩa nghiệp vụ trước khi chuyển zero date.
- [ ] Đã cập nhật ứng dụng để xử lý NULL và timezone đúng.
- [ ] Đã chạy regression test sau sửa hoặc nâng cấp.

### 17. Bài tập thực hành

Một hệ thống bán hàng lưu delivery_date bằng DATE, created_at bằng TIMESTAMP và appointment_at bằng DATETIME. Sau khi nâng cấp MySQL, import CSV báo Incorrect date value; một số hàng có 0000-00-00. Người dùng tại Việt Nam thấy created_at lệch bảy giờ so với báo cáo chạy trên server UTC. Lịch hẹn ở một quốc gia có DST bị chạy sớm hoặc muộn một giờ.

1. Bạn sẽ đọc SQL mode, global/session timezone và kiểu cột bằng những truy vấn nào?
2. Phân biệt zero date với ngày sai như 2024-02-30 và zero-in-date.
3. Vì sao created_at kiểu TIMESTAMP có thể hiển thị khác ở hai session timezone?
4. Vì sao appointment_at kiểu DATETIME không tự chuyển đổi?
5. Thiết kế staging table để giữ raw CSV và đánh dấu parse error.
6. Làm thế nào xác minh timezone tables và CONVERT_TZ cho Asia/Ho_Chi_Minh?
7. Vì sao một DATETIME đơn lẻ không thể phân biệt hai instant trong DST fold?
8. Lập kế hoạch chuyển zero date sang NULL hoặc giá trị nghiệp vụ hợp lệ mà không mất thông tin.

### 18. Nguyên tắc vận hành

Hãy chọn kiểu thời gian theo ý nghĩa dữ liệu: DATE cho ngày lịch, DATETIME cho giờ lịch không tự chuyển timezone và TIMESTAMP cho instant cần chuyển đổi theo session timezone. Dùng SQL mode nghiêm ngặt, validate input trước khi ghi và không dùng zero date làm sentinel cho dữ liệu thiếu. Chuẩn hóa chính sách timezone giữa MySQL, Connector/J và ứng dụng; ưu tiên UTC cho instant, đồng thời giữ timezone IANA khi cần lịch địa phương. Khi sự cố xảy ra, giữ raw input, đọc cấu hình session, kiểm tra timezone tables và thử migration trên staging trước khi sửa dữ liệu production.

# Khác biệt chuyển đổi múi giờ của TIMESTAMP và DATETIME

Bài học thuộc chương **Ngày giờ** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Việc lưu thời điểm đúng nghĩa là rất quan trọng với log, giao dịch, lịch hẹn, đơn hàng, đồng bộ và ứng dụng chạy ở nhiều múi giờ.

Sau bài này, bạn có thể phân biệt thời điểm tuyệt đối với giờ địa phương, giải thích cách MySQL chuyển đổi `TIMESTAMP` theo múi giờ session, hiểu vì sao `DATETIME` giữ nguyên giá trị ngày giờ, cấu hình session theo UTC, xử lý múi giờ có DST và lập kế hoạch chuyển đổi dữ liệu giữa hai kiểu.

## 1. Hai khái niệm cần phân biệt: thời điểm và giờ trên đồng hồ

Một chuỗi như `2026-11-19 09:30:00` chỉ mô tả ngày và giờ trên mặt đồng hồ. Nếu không có múi giờ hoặc offset, ta chưa biết nó tương ứng với thời điểm nào trên dòng thời gian toàn cầu.

Ví dụ, cùng một thời điểm có thể được hiển thị như sau:

| Cách biểu diễn | Giá trị |
|---|---|
| UTC | `2026-11-19 02:30:00+00:00` |
| Việt Nam | `2026-11-19 09:30:00+07:00` |
| Một múi giờ UTC-05:00 | `2026-11-18 21:30:00-05:00` |

Ba giá trị trên mô tả cùng một thời điểm, nhưng giờ trên đồng hồ khác nhau.

Cần phân biệt:

- **Thời điểm (instant):** một điểm duy nhất trên dòng thời gian, không phụ thuộc người xem ở múi giờ nào.
- **Giờ địa phương (local date-time / wall-clock time):** ngày và giờ theo lịch của một địa điểm, ví dụ 09:00 tại Thành phố Hồ Chí Minh.
- **Múi giờ (time zone):** tập quy tắc xác định offset UTC tại từng thời điểm. Một múi giờ có thể thay đổi offset theo lịch sử hoặc quy định DST.
- **Offset UTC:** độ lệch cụ thể so với UTC tại một thời điểm, ví dụ `+07:00`. Offset cố định không chứa toàn bộ quy tắc lịch sử/tương lai của một múi giờ.

Hai kiểu `TIMESTAMP` và `DATETIME` khác nhau chính ở cách MySQL xử lý ngữ nghĩa này.

## 2. TIMESTAMP và DATETIME khác nhau như thế nào?

**TIMESTAMP** biểu diễn một thời điểm. MySQL chuyển giá trị từ múi giờ session sang UTC khi lưu, rồi chuyển từ UTC về múi giờ session khi đọc.

**DATETIME** biểu diễn ngày và giờ như một giá trị lịch. MySQL lưu và trả lại giá trị đó mà không tự động chuyển đổi theo múi giờ session.

| Tiêu chí | TIMESTAMP | DATETIME |
|---|---|---|
| Ngữ nghĩa thường dùng | Thời điểm tuyệt đối | Ngày giờ trên lịch / giờ địa phương |
| Khi ghi | Chuyển từ session time zone sang UTC để lưu | Lưu ngày giờ được cung cấp; không tự chuyển đổi múi giờ |
| Khi đọc | Chuyển từ UTC sang session time zone | Trả lại giá trị đã lưu |
| Có lưu tên múi giờ/offset ban đầu không? | Không | Không |
| Phụ thuộc `time_zone` session | Có | Không, đối với giá trị đã lưu |
| Phạm vi năm của MySQL 9.7 | 1970 đến 2038 | 1000 đến 9999 |
| Độ chính xác phần giây | Tối đa 6 chữ số | Tối đa 6 chữ số |
| Phù hợp | Thời điểm tạo giao dịch, sự kiện, log | Giờ hẹn địa phương, giờ mở cửa, ngày giờ nghiệp vụ không tự quy về UTC |

Một điểm cần ghi nhớ: `TIMESTAMP` không lưu tên múi giờ như `Asia/Ho_Chi_Minh`. Nó lưu thời điểm theo UTC. Múi giờ chỉ tham gia vào quá trình chuyển đổi lúc ghi và đọc.

Tương tự, `DATETIME` cũng không tự lưu thông tin rằng giá trị thuộc múi giờ Việt Nam hay một offset cụ thể. Nếu cần biết giờ địa phương thuộc khu vực nào, phải lưu thêm thông tin múi giờ.

### Phạm vi giá trị

Theo MySQL 9.7 Reference Manual:

| Kiểu | Phạm vi được hỗ trợ |
|---|---|
| `DATETIME` | `1000-01-01 00:00:00` đến `9999-12-31 23:59:59` |
| `TIMESTAMP` | `1970-01-01 00:00:01 UTC` đến `2038-01-19 03:14:07 UTC` |

Giới hạn trên của `TIMESTAMP` là một yếu tố quan trọng khi thiết kế hệ thống lưu ngày giờ tương lai xa hoặc dữ liệu lịch sử ngoài phạm vi này. `DATETIME` có phạm vi rộng hơn, nhưng không tự cung cấp ngữ nghĩa thời điểm tuyệt đối.

### Độ chính xác phần giây

Cả hai kiểu hỗ trợ fractional seconds precision (FSP) từ 0 đến 6:

- `TIMESTAMP` tương đương `TIMESTAMP(0)` nếu không khai báo FSP.
- `DATETIME` tương đương `DATETIME(0)` nếu không khai báo FSP.
- `TIMESTAMP(6)` và `DATETIME(6)` lưu tới microsecond.

Ví dụ:

~~~sql
CREATE TABLE time_precision_demo (
    id BIGINT UNSIGNED PRIMARY KEY,
    event_ts TIMESTAMP(6) NOT NULL,
    scheduled_local DATETIME(6) NOT NULL
);
~~~

Nếu đưa giá trị có nhiều chữ số phần giây hơn FSP của cột, MySQL làm tròn theo mặc định. Có thể dùng SQL mode `TIME_TRUNCATE_FRACTIONAL` nếu nghiệp vụ yêu cầu cắt phần dư thay vì làm tròn.

## 3. Cơ chế chuyển đổi của TIMESTAMP

Khi session đang ở múi giờ `+07:00`, câu lệnh:

~~~sql
INSERT INTO event_log (occurred_at)
VALUES ('2026-11-19 09:30:00');
~~~

được MySQL hiểu là 09:30 theo múi giờ session. Máy chủ chuyển giá trị đó thành 02:30 UTC rồi lưu.

Khi đọc trong session có múi giờ `+00:00`, giá trị được hiển thị là 02:30. Nếu đọc trong session `+07:00`, nó hiển thị lại là 09:30.

Sơ đồ:

~~~mermaid
flowchart TD
    A[Client gửi 09:30 tại UTC+07] --> B[Session time_zone = +07:00]
    B --> C[MySQL chuyển thành 02:30 UTC]
    C --> D[(Lưu TIMESTAMP theo UTC)]
    D --> E[Session time_zone = +00:00]
    E --> F[Đọc ra 02:30]
    D --> G[Session time_zone = +07:00]
    G --> H[Đọc ra 09:30]
~~~

Giá trị hiển thị khác nhau nhưng thời điểm được lưu vẫn là một.

### Thử nghiệm trực tiếp

Tạo bảng:

~~~sql
CREATE TABLE event_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    description VARCHAR(100) NOT NULL,
    occurred_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id)
);
~~~

Đặt múi giờ session là UTC+00:00 rồi ghi một giá trị:

~~~sql
SET SESSION time_zone = '+00:00';

INSERT INTO event_log (description, occurred_at)
VALUES ('test event', '2026-11-19 02:30:00.123456');
~~~

Đọc trong cùng session:

~~~sql
SELECT
    id,
    description,
    occurred_at,
    @@session.time_zone AS session_time_zone
FROM event_log;
~~~

Kết quả có giờ 02:30.

Đổi session sang UTC+07:00 rồi đọc lại:

~~~sql
SET SESSION time_zone = '+07:00';

SELECT
    id,
    description,
    occurred_at,
    @@session.time_zone AS session_time_zone
FROM event_log;
~~~

Giá trị hiển thị là 09:30. Phần microsecond vẫn được giữ.

Trả session về UTC:

~~~sql
SET SESSION time_zone = '+00:00';
~~~

Thử nghiệm này cho thấy `TIMESTAMP` lưu một thời điểm duy nhất, còn cách hiển thị phụ thuộc session đang đọc.

## 4. Cơ chế của DATETIME: giữ nguyên giờ trên lịch

Với `DATETIME`, MySQL không tự chuyển giá trị theo múi giờ session khi ghi và đọc.

Tạo bảng:

~~~sql
CREATE TABLE appointment (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(100) NOT NULL,
    starts_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id)
);
~~~

Đặt session UTC+07:00 và ghi:

~~~sql
SET SESSION time_zone = '+07:00';

INSERT INTO appointment (title, starts_at)
VALUES ('Họp nhóm', '2026-11-19 09:30:00.123456');
~~~

Đọc trong session UTC+07:00:

~~~sql
SELECT starts_at
FROM appointment;
~~~

Kết quả là 09:30.

Đổi session sang UTC+00:00:

~~~sql
SET SESSION time_zone = '+00:00';

SELECT starts_at
FROM appointment;
~~~

Kết quả vẫn là 09:30. MySQL không tự đổi thành 02:30.

Đây là hành vi đúng của `DATETIME`: giá trị được lưu là giờ trên lịch, không phải một thời điểm được chuẩn hóa theo UTC.

### Khi nào đây là điều mong muốn?

Giả sử cửa hàng tại Việt Nam mở cửa lúc 09:00 mỗi ngày. Giờ mở cửa là một quy tắc địa phương. Nếu người quản trị thay đổi múi giờ session, giờ mở cửa vẫn phải là 09:00.

Tương tự, một lịch hẹn có thể được tạo với ý nghĩa “09:00 tại phòng khám ở Hà Nội”. Giá trị 09:00 cần được giữ như giờ địa phương. Để chuyển nó thành một thời điểm cụ thể, hệ thống cần biết múi giờ của địa điểm và chính sách xử lý DST nếu khu vực có DST.

## 5. Cấu hình múi giờ trong MySQL

MySQL duy trì nhiều mức cấu hình múi giờ:

| Biến | Phạm vi | Ý nghĩa |
|---|---|---|
| `system_time_zone` | Chỉ đọc | Múi giờ hệ điều hành mà máy chủ nhận diện khi khởi động |
| `@@GLOBAL.time_zone` | Global | Múi giờ mặc định cho các session mới |
| `@@SESSION.time_zone` | Session | Múi giờ của kết nối hiện tại |

Mặc định, global `time_zone` là `SYSTEM`. Khi client kết nối, session nhận giá trị từ global. Client có thể thay đổi múi giờ riêng của kết nối mà không thay đổi session khác.

Kiểm tra:

~~~sql
SELECT
    @@system_time_zone AS system_time_zone,
    @@global.time_zone AS global_time_zone,
    @@session.time_zone AS session_time_zone;
~~~

### Dùng offset cố định

Có thể dùng offset UTC như:

~~~sql
SET SESSION time_zone = '+00:00';
SET SESSION time_zone = '+07:00';
SET SESSION time_zone = '-05:00';
~~~

Offset cố định dễ cấu hình và không cần nạp bảng múi giờ. Tuy nhiên, nó chỉ biểu diễn độ lệch cố định. Nếu khu vực áp dụng DST hoặc thay đổi quy định múi giờ, offset cố định không tự cập nhật theo lịch.

### Dùng tên múi giờ

Có thể đặt tên múi giờ IANA:

~~~sql
SET SESSION time_zone = 'Asia/Ho_Chi_Minh';
SET SESSION time_zone = 'Europe/Amsterdam';
SET SESSION time_zone = 'America/New_York';
~~~

Tên múi giờ cung cấp quy tắc theo khu vực, bao gồm lịch sử thay đổi offset và DST.

Để sử dụng tên múi giờ, các bảng thông tin múi giờ trong schema `mysql` phải được nạp và cập nhật. Nếu chưa có dữ liệu, MySQL có thể báo:

~~~text
ERROR 1298 (HY000): Unknown or incorrect time zone
~~~

Trên các hệ điều hành có zoneinfo, quản trị viên có thể nạp dữ liệu bằng công cụ `mysql_tzinfo_to_sql`. Ví dụ trên Linux:

~~~bash
mysql_tzinfo_to_sql /usr/share/zoneinfo | mysql -u root -p mysql
~~~

Đây là thao tác quản trị cần quyền phù hợp. Khi hệ điều hành cập nhật dữ liệu múi giờ, cần đánh giá việc nạp lại các bảng múi giờ của MySQL để giữ quy tắc chuyển đổi hiện hành.

### Đặt múi giờ mặc định cho server

Có thể cấu hình lúc khởi động:

~~~ini
[mysqld]
default-time-zone = '+00:00'
~~~

Hoặc quản trị viên có thể đặt global khi server đang chạy:

~~~sql
SET GLOBAL time_zone = '+00:00';
~~~

Việc thay đổi global chỉ ảnh hưởng các kết nối mới. Các session đã mở vẫn giữ giá trị riêng cho đến khi thay đổi hoặc kết nối lại.

Quyền cần thiết để thay đổi global system variable là `SYSTEM_VARIABLES_ADMIN`; `SUPER` là quyền cũ đã deprecated.

## 6. Vì sao nên chuẩn hóa session theo UTC?

Một ứng dụng thường có nhiều thành phần:

- API server chạy ở một khu vực.
- Worker xử lý nền chạy ở khu vực khác.
- MySQL Server chạy trên máy chủ cloud có múi giờ hệ điều hành riêng.
- Nhân viên quản trị kết nối bằng Workbench từ máy cá nhân.
- Các dịch vụ báo cáo đọc dữ liệu từ replica.

Nếu mỗi kết nối sử dụng múi giờ khác nhau, cùng một cột TIMESTAMP có thể hiển thị các giá trị khác nhau. Điều này không sai về mặt lưu trữ, nhưng dễ gây nhầm lẫn khi log, so sánh, đối soát và debug.

Một quy ước thường dùng là:

1. Mọi kết nối ứng dụng đặt session `time_zone = '+00:00'`.
2. Lưu các thời điểm sự kiện bằng `TIMESTAMP` nếu nằm trong phạm vi năm hỗ trợ.
3. API truyền và nhận thời điểm theo ISO 8601 có offset hoặc chuẩn UTC rõ ràng.
4. Chỉ chuyển sang múi giờ địa phương ở tầng giao diện khi hiển thị cho người dùng.
5. Với lịch hẹn địa phương, lưu thêm tên múi giờ IANA để giữ ý nghĩa nghiệp vụ.

Ví dụ khởi tạo kết nối:

~~~sql
SET SESSION time_zone = '+00:00';
~~~

Ứng dụng nên thực hiện thao tác này trong bước khởi tạo mỗi kết nối, hoặc cấu hình trong connector. Nếu dùng connection pool, cần đảm bảo trạng thái session được đặt lại khi tái sử dụng kết nối; không giả định kết nối mới luôn được tạo cho mỗi request.

## 7. Các hàm ngày giờ chịu ảnh hưởng của múi giờ

Không chỉ cột TIMESTAMP bị ảnh hưởng. Một số hàm thời gian cũng dùng session time zone.

| Hàm | Kết quả |
|---|---|
| `NOW()` | Ngày giờ hiện tại theo session time zone |
| `CURRENT_TIMESTAMP()` | Tương đương NOW(), theo session time zone |
| `CURTIME()` | Giờ hiện tại theo session time zone |
| `UTC_TIMESTAMP()` | Ngày giờ hiện tại theo UTC |
| `UTC_DATE()` | Ngày hiện tại theo UTC |
| `UNIX_TIMESTAMP()` | Unix timestamp của thời điểm hiện tại |
| `UNIX_TIMESTAMP(datetime)` | Diễn giải đối số DATETIME theo session time zone rồi chuyển thành Unix timestamp |
| `FROM_UNIXTIME(epoch)` | Chuyển Unix timestamp thành ngày giờ theo session time zone |
| `CONVERT_TZ(dt, from_tz, to_tz)` | Chuyển một giá trị ngày giờ từ múi giờ nguồn sang múi giờ đích |

Kiểm tra các hàm:

~~~sql
SELECT
    NOW(6) AS session_now,
    CURRENT_TIMESTAMP(6) AS current_timestamp_value,
    UTC_TIMESTAMP(6) AS utc_now,
    UNIX_TIMESTAMP() AS unix_epoch,
    @@session.time_zone AS session_time_zone;
~~~

Nếu session đang là UTC+07:00, `NOW()` hiển thị giờ Việt Nam, trong khi `UTC_TIMESTAMP()` trả giờ UTC.

### NOW() và UTC_TIMESTAMP() trong DEFAULT

Cả `TIMESTAMP` và `DATETIME` đều hỗ trợ automatic initialization và updating bằng `CURRENT_TIMESTAMP`.

Ví dụ:

~~~sql
CREATE TABLE audit_event (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    action_name VARCHAR(100) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL
        DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id)
);
~~~

Trong ví dụ:

- `created_at` là TIMESTAMP. Giá trị hiện tại theo session được chuyển thành UTC để lưu.
- `updated_at` là DATETIME. Hàm CURRENT_TIMESTAMP trả giờ session và giá trị đó được lưu như một DATETIME, không tự chuyển đổi khi đọc lại.

Nếu muốn cột DATETIME theo quy ước UTC, hãy đảm bảo session tạo và cập nhật giá trị đang ở UTC. Cột DATETIME không tự biết rằng ứng dụng định dùng nó làm UTC.

### CONVERT_TZ()

Ví dụ chuyển 09:00 ở UTC+07:00 sang UTC:

~~~sql
SELECT CONVERT_TZ(
    '2026-11-19 09:00:00',
    '+07:00',
    '+00:00'
) AS utc_value;
~~~

Kết quả là 02:00 UTC.

Có thể chuyển giữa các tên múi giờ:

~~~sql
SELECT CONVERT_TZ(
    '2026-07-15 09:00:00',
    'Asia/Ho_Chi_Minh',
    'Europe/Amsterdam'
) AS amsterdam_time;
~~~

Với tên múi giờ, MySQL cần bảng timezone đã được nạp. Nếu múi giờ không hợp lệ hoặc không có trong bảng, hàm có thể trả về NULL. Hãy kiểm tra kết quả trước khi dùng trong thao tác ghi hàng loạt.

## 8. Offset trong literal ngày giờ: một chi tiết dễ nhầm

Từ MySQL 8.0.19, literal DATETIME/TIMESTAMP có thể kèm offset UTC, ví dụ:

~~~sql
'2026-11-19 09:30:00+07:00'
'2026-11-19 02:30:00+00:00'
'2026-11-18 21:30:00-05:00'
~~~

Các literal trên mô tả cùng một thời điểm. MySQL tôn trọng offset khi xử lý giá trị đầu vào, nhưng không lưu offset ban đầu như một phần riêng của cột.

Có một khác biệt quan trọng:

- Với `TIMESTAMP`, offset xác định thời điểm tuyệt đối; khi đọc, MySQL vẫn hiển thị theo session time zone.
- Với `DATETIME`, offset trong literal được dùng để chuyển giá trị sang múi giờ session tại thời điểm INSERT. Sau đó MySQL lưu phần ngày giờ đã chuyển đổi, không giữ offset ban đầu. Khi SELECT, không có offset nào được hiển thị.

Ví dụ trên MySQL 8.0.19 trở lên:

~~~sql
CREATE TABLE offset_demo (
    id INT PRIMARY KEY,
    event_ts TIMESTAMP NOT NULL,
    event_dt DATETIME NOT NULL
);

SET SESSION time_zone = '+00:00';

INSERT INTO offset_demo (id, event_ts, event_dt)
VALUES (
    1,
    '2026-11-19 09:30:00+07:00',
    '2026-11-19 09:30:00+07:00'
);

SELECT * FROM offset_demo;
~~~

Trong session UTC, cả hai giá trị được hiển thị là 02:30. Với TIMESTAMP, đó là thời điểm UTC đã chuẩn hóa. Với DATETIME, đó là giá trị lịch được chuyển sang giờ session UTC rồi lưu lại; DATETIME không còn thông tin rằng đầu vào ban đầu là UTC+07:00.

Nếu đổi session sang UTC+07:00:

~~~sql
SET SESSION time_zone = '+07:00';

SELECT * FROM offset_demo;
~~~

TIMESTAMP hiển thị 09:30. DATETIME vẫn giữ 02:30 vì giá trị đã lưu là DATETIME không kèm múi giờ.

Đừng dùng DATETIME nếu yêu cầu là lưu và truy xuất nguyên vẹn offset mà client đã gửi. Hãy lưu thêm offset hoặc tên múi giờ vào một cột riêng nếu nghiệp vụ cần giữ thông tin đó.

## 9. DST và các trường hợp giờ địa phương không duy nhất

Một số múi giờ áp dụng Daylight Saving Time (DST). Khi đồng hồ chuyển sang giờ mùa hè hoặc trở lại giờ chuẩn, có hai tình huống đặc biệt:

- **Giờ không tồn tại:** đồng hồ nhảy qua một khoảng thời gian. Ví dụ 01:59 chuyển thẳng sang 03:00, nên 02:30 không xảy ra ở ngày đó.
- **Giờ bị lặp:** đồng hồ quay lùi một giờ. Một giờ địa phương như 02:30 có thể xuất hiện hai lần, tương ứng hai thời điểm UTC khác nhau.

Ví dụ, trong một số khu vực châu Âu, khi kết thúc DST, hai thời điểm UTC khác nhau có thể cùng hiển thị thành 02:30 tại múi giờ địa phương.

MySQL Reference Manual minh họa hai giá trị TIMESTAMP UTC:

~~~text
2018-10-28 00:30:00 UTC
2018-10-28 01:30:00 UTC
~~~

Khi đọc trong múi giờ `MET`, cả hai có thể được hiển thị thành:

~~~text
2018-10-28 02:30:00
2018-10-28 02:30:00
~~~

Hai giá trị vẫn là hai thời điểm khác nhau; chỉ cách biểu diễn giờ địa phương bị trùng.

### Tác động với DATETIME

DATETIME chỉ lưu giờ trên lịch. Nếu lưu `2026-10-25 02:30:00` trong một khu vực có giờ 02:30 lặp lại, chỉ riêng giá trị DATETIME không cho biết đó là lần xuất hiện thứ nhất hay thứ hai.

Nếu nghiệp vụ cần xác định thời điểm duy nhất, phải lưu thêm offset, tên múi giờ cùng quy tắc chọn lần xuất hiện, hoặc lưu trực tiếp thời điểm UTC đã được xác định.

### Tác động với TIMESTAMP

TIMESTAMP lưu hai thời điểm khác nhau theo UTC, nhưng khi hiển thị ở múi giờ có DST, chúng có thể trông giống nhau.

Ngoài ra, MySQL có một lưu ý nâng cao: trong khoảng giờ bị lặp do DST, phép so sánh TIMESTAMP với literal địa phương có thể có kết quả khác nhau giữa truy vấn dùng index và truy vấn table scan. Lý do là đường truy vấn có index so sánh giá trị UTC bên trong index, trong khi table scan chuyển các giá trị sang session time zone trước khi so sánh.

Với truy vấn nhạy cảm ở khu vực có DST:

- Ưu tiên session UTC khi lọc theo thời điểm.
- Truyền giá trị UTC hoặc offset rõ ràng từ ứng dụng.
- Tránh dùng một literal giờ địa phương mơ hồ làm khóa nhận diện thời điểm.
- Kiểm thử truy vấn có index và không có index nếu ứng dụng buộc phải xử lý giờ địa phương trong vùng DST.

### Cách thiết kế lịch hẹn an toàn

Với lịch hẹn theo giờ địa phương, nên lưu các thông tin cần thiết:

~~~sql
CREATE TABLE appointments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    local_start DATETIME(6) NOT NULL,
    time_zone_name VARCHAR(64) NOT NULL,
    resolved_start_utc TIMESTAMP(6) NULL,
    PRIMARY KEY (id)
);
~~~

Ý nghĩa:

- `local_start`: giờ trên lịch mà người dùng chọn.
- `time_zone_name`: tên múi giờ IANA của địa điểm, ví dụ `Asia/Ho_Chi_Minh`.
- `resolved_start_utc`: thời điểm UTC đã được xác định sau khi áp dụng quy tắc múi giờ và chính sách DST.

Nếu giờ địa phương rơi vào khoảng không tồn tại hoặc bị lặp, ứng dụng cần quy định rõ cách xử lý, chẳng hạn từ chối, yêu cầu người dùng chọn offset hoặc chọn lần xuất hiện đầu/cuối. Không nên để dữ liệu mơ hồ tự động quyết định một cách âm thầm.

## 10. Chọn TIMESTAMP hay DATETIME theo nghiệp vụ

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Thời điểm tạo đơn hàng | TIMESTAMP | Cần xác định một thời điểm tuyệt đối |
| Thời điểm nhận request hoặc log sự kiện | TIMESTAMP | Nhiều server/múi giờ vẫn phải thống nhất thời điểm |
| Thời điểm đồng bộ dữ liệu | TIMESTAMP | Cần so sánh thứ tự sự kiện trên dòng thời gian |
| Ngày giờ sinh nhật hoặc ngày giờ ghi trên giấy tờ | DATETIME hoặc DATE | Là giá trị lịch, không phải thời điểm toàn cầu |
| Giờ mở cửa 09:00 mỗi ngày | TIME hoặc DATETIME tùy mô hình | Là quy tắc giờ địa phương |
| Lịch hẹn tại địa điểm có múi giờ riêng | DATETIME + tên múi giờ; có thể thêm UTC instant | Cần giữ giờ địa phương và quy tắc địa điểm |
| Thời điểm sau năm 2038 | DATETIME theo quy ước UTC hoặc mô hình khác | TIMESTAMP của MySQL có giới hạn năm 2038 |
| Thời điểm lịch sử trước năm 1970 | DATETIME theo quy ước UTC hoặc mô hình khác | Ngoài phạm vi TIMESTAMP |

Quy tắc thực tế:

- Nếu cần lưu “khi nào sự kiện xảy ra”, hãy dùng kiểu biểu diễn thời điểm và chuẩn hóa UTC.
- Nếu cần lưu “đồng hồ tại địa điểm ghi mấy giờ”, hãy lưu giờ địa phương và múi giờ tương ứng.
- Nếu cần giữ cả thời điểm tuyệt đối và cách người dùng đã nhập, hãy lưu cả UTC instant, local datetime và timezone/offset.
- Không dùng DATETIME với giả định MySQL sẽ tự đổi theo múi giờ.
- Không dùng TIMESTAMP cho giá trị lịch không có ý nghĩa thời điểm, như ngày sinh hoặc giờ mở cửa.

## 11. Chuyển đổi giữa TIMESTAMP và DATETIME

Chuyển đổi kiểu dữ liệu có thể làm thay đổi ý nghĩa dữ liệu nếu không biết giá trị cũ đang đại diện cho gì.

Trước khi chuyển đổi, cần xác định:

1. Cột hiện tại là TIMESTAMP hay DATETIME?
2. Giá trị DATETIME hiện lưu theo UTC hay giờ địa phương?
3. Nếu là giờ địa phương, thuộc múi giờ nào?
4. Có dữ liệu rơi vào khoảng DST bị lặp hoặc không tồn tại không?
5. Cột đích cần giữ thời điểm tuyệt đối hay giờ trên lịch?

### DATETIME UTC sang TIMESTAMP

Giả sử cột DATETIME cũ chứa giờ UTC theo quy ước của ứng dụng. Đặt session UTC trước khi chuyển dữ liệu để MySQL diễn giải giá trị nguồn là UTC:

~~~sql
SET SESSION time_zone = '+00:00';

INSERT INTO event_log_new (id, occurred_at)
SELECT id, old_datetime_utc
FROM event_log_old;
~~~

Cột đích `occurred_at` là TIMESTAMP. MySQL diễn giải giá trị nguồn trong session UTC rồi lưu thời điểm UTC tương ứng.

### DATETIME giờ địa phương sang TIMESTAMP

Giả sử DATETIME cũ chứa giờ địa phương ở Việt Nam:

~~~sql
SET SESSION time_zone = 'Asia/Ho_Chi_Minh';

INSERT INTO event_log_new (id, occurred_at)
SELECT id, old_local_datetime
FROM event_log_old;
~~~

MySQL diễn giải giá trị DATETIME như giờ địa phương của session rồi chuyển thành UTC khi ghi vào TIMESTAMP.

Chỉ thực hiện cách này nếu dữ liệu cũ thực sự cùng một múi giờ và các giá trị có thể xác định duy nhất. Nếu dữ liệu đến từ nhiều vùng hoặc có giờ DST mơ hồ, cần xử lý theo từng nhóm với metadata phù hợp.

### TIMESTAMP sang DATETIME UTC

Nếu muốn tạo cột DATETIME nhưng lưu quy ước UTC, đặt session UTC trước khi đọc TIMESTAMP và ghi sang DATETIME:

~~~sql
SET SESSION time_zone = '+00:00';

INSERT INTO event_log_utc_datetime (id, occurred_at_utc)
SELECT id, occurred_at
FROM event_log;
~~~

TIMESTAMP được đọc ở UTC, sau đó DATETIME nhận giá trị ngày giờ UTC đó và lưu nguyên trạng.

### TIMESTAMP sang DATETIME giờ địa phương

Nếu cần giữ cách hiển thị theo một múi giờ địa phương cụ thể:

~~~sql
SET SESSION time_zone = 'Asia/Ho_Chi_Minh';

INSERT INTO event_log_local_datetime (id, local_time)
SELECT id, occurred_at
FROM event_log;
~~~

DATETIME đích sẽ lưu giờ địa phương sau khi TIMESTAMP được chuyển đổi theo session. Hãy lưu thêm tên múi giờ nếu cần biết giá trị đó thuộc khu vực nào.

### Quy trình migration an toàn

Không nên thay đổi trực tiếp kiểu cột trên production trước khi xác định ngữ nghĩa.

Một quy trình kiểm soát:

1. Sao lưu dữ liệu và ghi lại cấu hình múi giờ của server/session.
2. Thống kê dữ liệu nguồn, phạm vi ngày, giá trị NULL, dữ liệu bất thường và nguồn tạo dữ liệu.
3. Tạo cột hoặc bảng đích song song với kiểu mới.
4. Chọn session time zone rõ ràng cho từng đợt chuyển đổi.
5. Backfill theo lô, tránh khóa bảng lâu.
6. Đối chiếu số hàng, giá trị đầu/cuối và các mẫu chuyển đổi ở nhiều múi giờ.
7. Kiểm tra dữ liệu trong khoảng DST và các giá trị gần biên phạm vi TIMESTAMP.
8. Chạy thử ứng dụng trên dữ liệu đích, xác nhận API và báo cáo hiển thị đúng.
9. Chuyển luồng đọc/ghi sau khi đã có phương án rollback.
10. Chỉ xóa cột cũ sau khi xác nhận đầy đủ.

Nếu DATETIME cũ không có metadata múi giờ, không thể khôi phục chính xác thời điểm UTC trong mọi trường hợp. Cần tìm nguồn dữ liệu hoặc quy tắc nghiệp vụ để xác định; việc chỉ đổi kiểu cột không thể tự suy ra múi giờ đã mất.

## 12. Bài thực hành: quan sát chuyển đổi theo session time zone

Bài thực hành này giúp so sánh trực tiếp hai kiểu. Thực hiện trên database lab riêng.

### Bước 1: tạo bảng

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_time_zone_lab;
USE mysql_time_zone_lab;

CREATE TABLE time_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    description VARCHAR(100) NOT NULL,
    event_ts TIMESTAMP(6) NOT NULL,
    event_dt DATETIME(6) NOT NULL,
    PRIMARY KEY (id)
);
~~~

### Bước 2: ghi dữ liệu ở UTC

~~~sql
SET SESSION time_zone = '+00:00';

INSERT INTO time_demo (
    description,
    event_ts,
    event_dt
)
VALUES (
    'inserted in UTC',
    '2026-11-19 02:30:00.123456',
    '2026-11-19 02:30:00.123456'
);
~~~

Đọc dữ liệu:

~~~sql
SELECT
    description,
    event_ts,
    event_dt,
    @@session.time_zone AS session_zone
FROM time_demo;
~~~

Hai giá trị hiển thị cùng là 02:30.

### Bước 3: đổi session sang UTC+07:00

~~~sql
SET SESSION time_zone = '+07:00';

SELECT
    description,
    event_ts,
    event_dt,
    @@session.time_zone AS session_zone
FROM time_demo;
~~~

Quan sát:

- `event_ts` hiển thị 09:30.
- `event_dt` vẫn hiển thị 02:30.

### Bước 4: ghi thêm dữ liệu khi session ở UTC+07:00

~~~sql
INSERT INTO time_demo (
    description,
    event_ts,
    event_dt
)
VALUES (
    'inserted in UTC+07',
    '2026-11-19 09:30:00.123456',
    '2026-11-19 09:30:00.123456'
);
~~~

Đổi lại UTC và đọc:

~~~sql
SET SESSION time_zone = '+00:00';

SELECT
    id,
    description,
    event_ts,
    event_dt
FROM time_demo
ORDER BY id;
~~~

Hai hàng TIMESTAMP biểu diễn cùng một thời điểm UTC nếu được nhập theo hai session tương ứng. DATETIME lưu hai giá trị giờ trên lịch được truyền vào, không tự quy về cùng một thời điểm.

### Bước 5: thử CONVERT_TZ

~~~sql
SELECT
    CONVERT_TZ(
        '2026-11-19 09:30:00',
        '+07:00',
        '+00:00'
    ) AS utc_value;
~~~

Kết quả là 02:30.

Nếu bảng múi giờ đã được nạp, thử chuyển theo tên khu vực:

~~~sql
SELECT CONVERT_TZ(
    '2026-11-19 09:30:00',
    'Asia/Ho_Chi_Minh',
    'UTC'
) AS utc_value;
~~~

So sánh kết quả với phép chuyển offset cố định. Với khu vực có DST, tên múi giờ có thể tạo kết quả khác offset cố định tại các thời điểm trong năm.

### Bước 6: kiểm tra Unix timestamp

~~~sql
SELECT
    event_ts,
    UNIX_TIMESTAMP(event_ts) AS epoch_seconds,
    FROM_UNIXTIME(UNIX_TIMESTAMP(event_ts)) AS back_in_session_zone
FROM time_demo;
~~~

Đổi session giữa UTC và UTC+07:00 rồi chạy lại. Quan sát giá trị epoch đại diện cho thời điểm, trong khi `FROM_UNIXTIME()` hiển thị theo session.

### Bước 7: dọn dẹp

~~~sql
DROP DATABASE mysql_time_zone_lab;
~~~

Chỉ chạy trên database lab vừa tạo. Lệnh sẽ xóa toàn bộ dữ liệu thực hành trong database đó.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra / xử lý |
|---|---|---|
| TIMESTAMP hiển thị khác nhau trên hai máy | Hai kết nối có session time zone khác nhau | Kiểm tra `@@session.time_zone`, chuẩn hóa session UTC hoặc chuyển đổi khi hiển thị |
| DATETIME không đổi khi đổi session | Đây là hành vi đúng của DATETIME | Nếu cần thời điểm, xác định múi giờ nguồn và chuyển đổi rõ ràng |
| Lỗi Unknown or incorrect time zone | Bảng múi giờ chưa được nạp hoặc tên không hợp lệ | Dùng offset cố định hoặc nạp bảng timezone |
| Dữ liệu bị lệch 7 giờ sau migration | DATETIME nguồn là giờ địa phương nhưng session chuyển sang UTC, hoặc ngược lại | Xác định quy ước nguồn; đặt session time zone phù hợp trước khi backfill |
| Hai sự kiện có cùng giờ địa phương | Có thể rơi vào khoảng DST lặp giờ | Lưu UTC instant hoặc offset/zone và chính sách phân biệt lần xuất hiện |
| Lịch hẹn rơi vào giờ không tồn tại | Khu vực chuyển sang DST và đồng hồ nhảy qua thời điểm đó | Kiểm tra giờ địa phương và yêu cầu người dùng chọn giờ hợp lệ |
| Giá trị TIMESTAMP ngoài phạm vi | Thời điểm trước 1970 hoặc sau giới hạn 2038 | Dùng DATETIME theo quy ước UTC hoặc mô hình khác |
| UNIX_TIMESTAMP trả 0 | Đối số ngoài phạm vi hoặc không hợp lệ | Kiểm tra giá trị đầu vào và session time zone |
| CONVERT_TZ trả NULL | Múi giờ không hợp lệ hoặc bảng timezone chưa có dữ liệu | Kiểm tra tên zone, nạp/cập nhật bảng timezone |
| Connection pool hiển thị múi giờ không nhất quán | Session bị tái sử dụng sau khi code khác đổi `time_zone` | Đặt lại `time_zone` trong khâu lấy connection hoặc reset session |

## 14. Checklist thiết kế ngày giờ cho ứng dụng

- [ ] Đã phân biệt dữ liệu là thời điểm tuyệt đối hay giờ địa phương.
- [ ] Đã chọn TIMESTAMP hoặc DATETIME theo đúng ngữ nghĩa.
- [ ] Đã kiểm tra phạm vi năm, đặc biệt giới hạn 2038 của TIMESTAMP.
- [ ] Đã xác định độ chính xác phần giây cần dùng: 0 đến 6.
- [ ] Đã quy định session time zone cho ứng dụng, tốt nhất là UTC đối với luồng thời điểm.
- [ ] Đã kiểm tra global, session và system time zone.
- [ ] Đã nạp bảng timezone nếu sử dụng tên múi giờ IANA.
- [ ] Đã lưu timezone riêng cho lịch hẹn địa phương.
- [ ] Đã xác định cách xử lý giờ DST bị lặp hoặc không tồn tại.
- [ ] Đã kiểm tra `NOW()`, `UTC_TIMESTAMP()`, `UNIX_TIMESTAMP()` và `FROM_UNIXTIME()`.
- [ ] Đã kiểm thử migration bằng dữ liệu mẫu ở nhiều múi giờ.
- [ ] Đã kiểm tra connection pool không giữ trạng thái session ngoài ý muốn.

Chọn đúng kiểu ngày giờ không chỉ là chọn định dạng cột. Cần thống nhất ngữ nghĩa dữ liệu từ API, ứng dụng, database, báo cáo đến giao diện. Với thời điểm sự kiện, UTC là quy ước dễ phối hợp giữa các hệ thống. Với lịch hẹn, giờ địa phương và tên múi giờ là dữ liệu nghiệp vụ cần được giữ rõ ràng.

## Tài liệu tham khảo chính thức

Các hành vi và giới hạn trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [The DATE, DATETIME, and TIMESTAMP Types](https://dev.mysql.com/doc/refman/9.7/en/datetime.html): phạm vi giá trị, chuyển đổi UTC của TIMESTAMP, DATETIME và offset literal.
2. [MySQL Server Time Zone Support](https://dev.mysql.com/doc/refman/9.7/en/time-zone-support.html): system/global/session time zone, tên múi giờ, nạp và cập nhật bảng timezone.
3. [Date and Time Literals](https://dev.mysql.com/doc/refman/9.7/en/date-and-time-literals.html): cú pháp literal ngày giờ có offset, hỗ trợ từ MySQL 8.0.19 và cách offset được xử lý.
4. [Date and Time Functions](https://dev.mysql.com/doc/refman/9.7/en/date-and-time-functions.html): NOW, UTC_TIMESTAMP, CONVERT_TZ, UNIX_TIMESTAMP và FROM_UNIXTIME.
5. [Fractional Seconds in Time Values](https://dev.mysql.com/doc/refman/9.7/en/fractional-seconds.html): độ chính xác microsecond và cách làm tròn/cắt phần giây.
6. [Indexed Lookups from TIMESTAMP Columns](https://dev.mysql.com/doc/refman/9.7/en/timestamp-lookups.html): các giới hạn truy vấn khi DST làm giờ địa phương không duy nhất.
7. [Automatic Initialization and Updating for TIMESTAMP and DATETIME](https://dev.mysql.com/doc/refman/9.7/en/timestamp-initialization.html): DEFAULT CURRENT_TIMESTAMP và ON UPDATE CURRENT_TIMESTAMP.
8. [MySQL 8.0 Release Notes — Changes in MySQL 8.0.19](https://dev.mysql.com/doc/relnotes/mysql/8.0/en/news-8-0-19.html): bổ sung hỗ trợ offset trong datetime literals.


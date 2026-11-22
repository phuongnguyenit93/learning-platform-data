# CONVERT_TZ, timezone table và thay đổi giờ mùa hè

Làm việc với ngày giờ theo múi giờ đòi hỏi phân biệt một **thời điểm tuyệt đối** với **giờ trên đồng hồ địa phương**. Cùng một thời điểm UTC có thể hiển thị thành các giờ khác nhau ở từng khu vực; ngược lại, một giờ địa phương trong ngày chuyển giờ mùa hè có thể không tồn tại hoặc xuất hiện hai lần. MySQL cung cấp `CONVERT_TZ()` để chuyển đổi giữa các múi giờ, nhưng chuyển đổi theo tên vùng như `Asia/Ho_Chi_Minh` hoặc `America/New_York` chỉ hoạt động đúng khi server có dữ liệu múi giờ tương ứng.

Bài học này tập trung vào ba phần: cách dùng `CONVERT_TZ()`, cách cài đặt và cập nhật timezone tables, và cách xử lý Daylight Saving Time (DST). Đây là nội dung quan trọng trong module `DATABASE_MYSQL`, vì sai lệch múi giờ có thể làm sai thời điểm tạo đơn hàng, lịch hẹn, báo cáo theo ngày, thời hạn thanh toán và dữ liệu đồng bộ giữa nhiều hệ thống.

## 1. Múi giờ là quy tắc, không chỉ là độ lệch UTC

Một múi giờ có tên như `America/New_York` là tập hợp quy tắc xác định độ lệch so với UTC tại từng thời điểm. Quy tắc đó có thể thay đổi theo lịch sử, luật pháp và chính sách của khu vực. Vì vậy, độ lệch hiện tại `-04:00` không đủ để đại diện cho toàn bộ múi giờ New York.

Phân biệt hai dạng:

- **Named time zone:** tên vùng theo cơ sở dữ liệu IANA, ví dụ `Asia/Ho_Chi_Minh`, `Europe/Paris`, `America/New_York`. Nó chứa lịch sử và quy tắc chuyển đổi theo ngày.
- **UTC offset cố định:** ví dụ `+07:00`, `-05:00`, `+00:00`. Nó chỉ biểu diễn một độ lệch tại thời điểm áp dụng, không chứa quy tắc DST hoặc lịch sử thay đổi của vùng.

Việt Nam hiện dùng `Asia/Ho_Chi_Minh` với độ lệch UTC+07:00 và không áp dụng DST trong giai đoạn hiện tại. Dù vậy, dùng tên vùng vẫn có ý nghĩa khi cần biểu diễn đúng múi giờ địa lý, lịch sử hoặc đồng bộ với hệ thống khác. Với một hệ thống chỉ cần lưu thời điểm tuyệt đối, lưu UTC thường đơn giản hơn.

Không nên dùng tên viết tắt như `EST`, `PST` hoặc `CST` làm định danh múi giờ. Chúng có thể mơ hồ, không thể hiện đầy đủ quy tắc DST hoặc được hiểu khác nhau giữa các hệ thống. Ưu tiên tên IANA đầy đủ.

## 2. `CONVERT_TZ()` hoạt động như thế nào?

Cú pháp:

```sql
CONVERT_TZ(datetime_value, from_tz, to_tz)
```

- `datetime_value`: giá trị ngày giờ cần chuyển.
- `from_tz`: múi giờ nguồn, có thể là tên vùng đã nạp hoặc UTC offset.
- `to_tz`: múi giờ đích, có thể là tên vùng đã nạp hoặc UTC offset.
- Kết quả: một giá trị `DATETIME` đã được chuyển sang múi giờ đích; hàm trả về `NULL` nếu đối số không hợp lệ hoặc tên múi giờ không được nhận diện.

Ví dụ chuyển một thời điểm UTC sang giờ Việt Nam:

```sql
SELECT CONVERT_TZ(
    '2026-01-15 12:00:00',
    '+00:00',
    'Asia/Ho_Chi_Minh'
) AS vietnam_time;
```

Kết quả là `2026-01-15 19:00:00`, vì Việt Nam nhanh hơn UTC bảy giờ tại thời điểm đó.

Chuyển giờ Việt Nam về UTC:

```sql
SELECT CONVERT_TZ(
    '2026-01-15 19:00:00',
    'Asia/Ho_Chi_Minh',
    '+00:00'
) AS utc_time;
```

Kết quả là `2026-01-15 12:00:00`.

### Chuyển đổi giữa hai named time zone

```sql
SELECT CONVERT_TZ(
    '2026-07-01 12:00:00',
    'America/New_York',
    'Europe/Paris'
) AS paris_time;
```

MySQL tra cứu quy tắc của vùng nguồn tại thời điểm đầu vào, xác định thời điểm tương ứng rồi áp dụng quy tắc của vùng đích tại chính thời điểm đó. Do DST, chênh lệch giữa hai vùng không nhất thiết cố định quanh năm.

### Dùng UTC offset cố định

```sql
SELECT CONVERT_TZ(
    '2026-01-15 12:00:00',
    '+00:00',
    '+07:00'
) AS fixed_offset_time;
```

Ví dụ này không cần tên vùng trong timezone tables vì hai đối số là offset cố định. Offset phù hợp cho một phép tính có độ lệch đã biết, nhưng không thay thế named time zone khi cần DST hoặc quy tắc lịch sử.

## 3. Vì sao `CONVERT_TZ()` có thể trả về `NULL`?

Các nguyên nhân thường gặp:

1. Tên múi giờ không đúng, ví dụ sai chính tả `Asia/Ho_Chi_Minh`.
2. Server chưa nạp timezone tables hoặc thiếu tên vùng cần dùng.
3. Giá trị ngày giờ hoặc offset không hợp lệ.
4. Đối số ngày giờ hoặc múi giờ không hợp lệ. Trường hợp ngày giờ nằm ngoài phạm vi mà phiên bản hỗ trợ chuyển đổi cần được kiểm tra riêng; MySQL có thể không thực hiện chuyển đổi thay vì trả `NULL`.

Kiểm tra nhanh:

```sql
SELECT
    CONVERT_TZ('2026-01-15 12:00:00', '+00:00', '+07:00') AS fixed_offset_result,
    CONVERT_TZ('2026-01-15 12:00:00', '+00:00', 'Asia/Ho_Chi_Minh') AS named_zone_result;
```

Nếu kết quả offset cố định có giá trị nhưng named zone là `NULL`, cần kiểm tra timezone tables và tên vùng. Nếu cả hai đều `NULL`, kiểm tra giá trị ngày giờ và cú pháp offset. Nếu đầu vào nằm ngoài phạm vi chuyển đổi của phiên bản MySQL, đừng chỉ dựa vào `NULL`: kiểm tra xem kết quả có bị trả lại mà không chuyển đổi hay không và đối chiếu tài liệu của phiên bản đang chạy.

Kiểm tra tên vùng có trong bảng hệ thống:

```sql
SELECT Name
FROM mysql.time_zone_name
WHERE Name IN (
    'UTC',
    'Asia/Ho_Chi_Minh',
    'America/New_York',
    'Europe/Paris'
)
ORDER BY Name;
```

Các bảng `mysql.time_zone*` thuộc schema hệ thống `mysql`. Tài khoản ứng dụng thường không cần quyền đọc hoặc sửa chúng; việc nạp và cập nhật dữ liệu múi giờ nên do DBA hoặc quy trình quản trị thực hiện.

## 4. Time zone tables của MySQL

MySQL dùng các bảng hệ thống để lưu dữ liệu múi giờ có tên. Những bảng chính gồm:

| Bảng | Vai trò khái quát |
|---|---|
| `mysql.time_zone_name` | Ánh xạ tên múi giờ sang ID nội bộ. |
| `mysql.time_zone` | Thông tin cấu trúc múi giờ. |
| `mysql.time_zone_transition` | Các thời điểm chuyển đổi quy tắc/offset. |
| `mysql.time_zone_transition_type` | Các kiểu offset và trạng thái áp dụng trong một vùng. |
| `mysql.time_zone_leap_second` | Dữ liệu leap second nếu được nạp và hỗ trợ. |

Các bảng này được nạp từ dữ liệu múi giờ của hệ điều hành hoặc bộ dữ liệu timezone phù hợp. Khi chúng trống hoặc thiếu vùng cần dùng, các hàm yêu cầu named time zone như `CONVERT_TZ()` không thể thực hiện chuyển đổi theo quy tắc vùng đó.

### Kiểm tra bảng đã được nạp

```sql
SELECT COUNT(*) AS named_zone_count
FROM mysql.time_zone_name;

SELECT Name
FROM mysql.time_zone_name
WHERE Name = 'America/New_York';
```

Nếu số lượng bằng 0 hoặc tên vùng không xuất hiện, nhiều khả năng timezone tables chưa được nạp đầy đủ. Việc chỉ thấy một số tên vùng chưa đảm bảo dữ liệu transition mới nhất đã được cài đặt.

## 5. Nạp timezone tables trên Linux/Unix

Trên nhiều hệ thống Linux/Unix, MySQL cung cấp tiện ích `mysql_tzinfo_to_sql` để đọc dữ liệu zoneinfo của hệ điều hành và sinh các câu lệnh SQL nạp vào schema `mysql`.

Trước tiên, cài hoặc cập nhật gói timezone database của hệ điều hành (thường là `tzdata`) theo quy trình quản trị của bản phân phối. Sau đó chạy lệnh tương tự:

```bash
mysql_tzinfo_to_sql /usr/share/zoneinfo | mysql -u root -p mysql
```

Lệnh đọc dữ liệu từ `/usr/share/zoneinfo`, chuyển thành SQL rồi gửi vào database `mysql`. Tùy hệ điều hành, thư mục zoneinfo có thể nằm ở vị trí khác; hãy xác nhận đường dẫn thực tế. Nhập mật khẩu tương tác khi client yêu cầu, không ghi mật khẩu quản trị trực tiếp vào command line.

Một quy trình cập nhật có kiểm soát:

1. Xác định phiên bản MySQL và dữ liệu timezone hiện tại.
2. Cập nhật gói `tzdata` trên máy chủ hoặc lấy bộ dữ liệu IANA được phê duyệt.
3. Nạp lại dữ liệu bằng `mysql_tzinfo_to_sql` vào schema `mysql`.
4. Khởi động lại MySQL theo cửa sổ vận hành để bảo đảm dữ liệu múi giờ đã cache được nạp lại.
5. Kiểm tra các tên vùng quan trọng và chạy truy vấn `CONVERT_TZ()` ở những mốc thời gian đã biết.
6. Theo dõi ứng dụng để phát hiện sai lệch thời gian hoặc lịch chạy sau cập nhật.

Không nên nạp dữ liệu timezone trực tiếp từ một thư mục tùy ý mà chưa xác minh nguồn. Quy tắc DST có thể thay đổi theo luật của từng quốc gia; dữ liệu mới cần đến từ nguồn timezone đáng tin cậy và được triển khai nhất quán giữa các môi trường.

## 6. Nạp timezone tables trên Windows

Trên Windows, không có cấu trúc zoneinfo tiêu chuẩn như `/usr/share/zoneinfo` của Linux. Vì vậy, quy trình dùng `mysql_tzinfo_to_sql` với thư mục đó không áp dụng trực tiếp.

Hãy dùng bộ SQL timezone tables dành cho MySQL/Windows từ nguồn phân phối chính thức phù hợp với phiên bản, hoặc quy trình đóng gói timezone data đã được DBA kiểm duyệt. Import các bảng vào schema `mysql` theo hướng dẫn của bản phân phối. Sau khi nạp, khởi động lại MySQL và kiểm tra các named zone cần dùng.

Không lấy tên múi giờ Windows như `Pacific Standard Time` rồi giả định MySQL hiểu đó là tên IANA. Các tên vùng trong MySQL thường theo dạng `America/Los_Angeles`, `Asia/Ho_Chi_Minh` hoặc `Europe/London`. Nếu ứng dụng nhận Windows time zone ID, hãy ánh xạ sang IANA time zone ID ở tầng ứng dụng bằng một thư viện hoặc bảng ánh xạ được quản lý.

## 7. Cập nhật dữ liệu timezone khi luật DST thay đổi

Dữ liệu timezone không bất biến. Cơ quan lập pháp có thể thay đổi ngày bắt đầu/kết thúc DST, bỏ DST hoặc thay đổi UTC offset. Cơ sở dữ liệu IANA Time Zone Database (tzdb) phát hành các bản cập nhật khi có thay đổi về quy tắc lịch sử hoặc tương lai.

Nếu server giữ timezone tables cũ, `CONVERT_TZ()` có thể trả kết quả sai cho các thời điểm sau khi quy định mới có hiệu lực, dù câu SQL và tên vùng hoàn toàn hợp lệ. Vì vậy, cập nhật timezone data là một phần của vận hành hệ thống ngày giờ.

### Quy trình quản lý cập nhật

- Theo dõi bản cập nhật tzdb và gói timezone của hệ điều hành.
- Đánh giá vùng địa lý mà ứng dụng thực sự sử dụng, đặc biệt các khu vực có DST hoặc luật thường xuyên thay đổi.
- Nạp dữ liệu mới vào timezone tables bằng quy trình đã kiểm thử.
- Khởi động lại MySQL khi cần để xóa dữ liệu múi giờ được cache trong tiến trình.
- Chạy regression test cho các mốc chuyển giờ trong quá khứ và tương lai.
- Đồng bộ dữ liệu timezone giữa primary, replica, môi trường batch và môi trường báo cáo.
- Ghi nhận phiên bản timezone data và thời điểm cập nhật để có thể truy vết khi kết quả báo cáo thay đổi.

Nếu MySQL đã cache thông tin của một time zone, việc cập nhật bảng hệ thống không nhất thiết làm mọi session đang chạy dùng ngay quy tắc mới. Khởi động lại server sau khi nạp dữ liệu mới là cách rõ ràng để bảo đảm tiến trình nạp lại thông tin timezone. Hãy thực hiện trong cửa sổ vận hành phù hợp với kiến trúc HA/replication.

## 8. Daylight Saving Time (DST) là gì?

Một số khu vực điều chỉnh đồng hồ theo mùa. Khi bắt đầu DST, đồng hồ thường nhảy tiến một khoảng (ví dụ từ 01:59:59 lên 03:00:00), tạo ra một đoạn giờ địa phương không tồn tại. Khi kết thúc DST, đồng hồ lùi lại, khiến một đoạn giờ địa phương xuất hiện hai lần.

Hai tình huống cần hiểu:

- **DST gap:** giờ địa phương không tồn tại. Ví dụ, một lịch hẹn đặt vào 02:30 trong ngày đồng hồ nhảy từ 02:00 lên 03:00 không ánh xạ tự nhiên tới một thời điểm thực.
- **DST overlap/fold:** giờ địa phương bị lặp. Ví dụ, 01:30 có thể xuất hiện một lần trước khi lùi đồng hồ và một lần sau khi lùi đồng hồ; hai lần đó là hai thời điểm UTC khác nhau.

Vì vậy, chuyển từ UTC sang giờ địa phương là xác định được khi timezone data đầy đủ: mỗi instant có một cách hiển thị theo quy tắc tại thời điểm đó. Chuyển từ local wall time sang UTC có thể mơ hồ hoặc không hợp lệ trong khoảng DST gap/overlap.

## 9. Quan sát DST bằng `CONVERT_TZ()`

### Bắt đầu DST: đồng hồ nhảy tiến

Với `America/New_York`, ngày 10-03-2024 đồng hồ chuyển từ giờ chuẩn sang giờ mùa hè. Hai instant UTC liên tiếp dưới đây được hiển thị thành giờ địa phương trước và sau bước nhảy:

```sql
SELECT
    utc_time,
    CONVERT_TZ(utc_time, '+00:00', 'America/New_York') AS new_york_time,
    TIMESTAMPDIFF(
        MINUTE,
        utc_time,
        CONVERT_TZ(utc_time, '+00:00', 'America/New_York')
    ) AS utc_offset_minutes
FROM (
    SELECT CAST('2024-03-10 06:59:59' AS DATETIME) AS utc_time
    UNION ALL
    SELECT CAST('2024-03-10 07:00:00' AS DATETIME)
) AS samples
ORDER BY utc_time;
```

Khi timezone tables có dữ liệu phù hợp, giờ địa phương chuyển từ `01:59:59` sang `03:00:00`; khoảng `02:00` đến trước `03:00` không tồn tại tại khu vực đó trong ngày chuyển DST.

### Kết thúc DST: đồng hồ lùi lại

Ngày 03-11-2024, New York kết thúc DST. Hai instant UTC khác nhau có thể cùng hiển thị thành 01:30 tại địa phương:

```sql
SELECT
    utc_time,
    CONVERT_TZ(utc_time, '+00:00', 'America/New_York') AS new_york_time,
    TIMESTAMPDIFF(
        MINUTE,
        utc_time,
        CONVERT_TZ(utc_time, '+00:00', 'America/New_York')
    ) AS utc_offset_minutes
FROM (
    SELECT CAST('2024-11-03 05:30:00' AS DATETIME) AS utc_time
    UNION ALL
    SELECT CAST('2024-11-03 06:30:00' AS DATETIME)
) AS samples
ORDER BY utc_time;
```

Hai hàng đều có giờ địa phương `01:30:00`, nhưng offset lần lượt là `-240` và `-300` phút. Nếu chỉ lưu chuỗi `2024-11-03 01:30:00` mà không lưu timezone/offset hoặc instant UTC tương ứng, bạn không thể biết đó là lần 01:30 thứ nhất hay thứ hai.

### Không giả định local time luôn ánh xạ một-một sang UTC

Một thời gian địa phương nằm trong DST gap không đại diện cho một instant hợp lệ theo quy tắc vùng. Một thời gian nằm trong DST overlap có hai instant hợp lệ. Khi nhận lịch hẹn từ người dùng, ứng dụng cần có chính sách rõ ràng: từ chối giờ không tồn tại, tự dịch sang giờ hợp lệ tiếp theo, hoặc yêu cầu người dùng chọn offset/occurrence khi giờ bị lặp.

Không nên dựa vào một kết quả `CONVERT_TZ(local_time, zone, 'UTC')` duy nhất để tự giải quyết mọi trường hợp gap/overlap mà không xác định chính sách. Hãy kiểm thử hành vi trên phiên bản MySQL thực tế và xử lý tính mơ hồ ở tầng nghiệp vụ.

## 10. Phân biệt `TIMESTAMP`, `DATETIME` và session time zone

`CONVERT_TZ()` là hàm chuyển đổi một giá trị ngày giờ; nó không tự thay đổi kiểu dữ liệu hoặc quy ước lưu trữ của cột. Khi thiết kế schema, cần biết `TIMESTAMP` và `DATETIME` có hành vi khác nhau:

| Kiểu | Hành vi múi giờ |
|---|---|
| `TIMESTAMP` | MySQL chuyển giá trị từ session time zone sang UTC khi lưu và từ UTC sang session time zone khi đọc. |
| `DATETIME` | Lưu giá trị ngày giờ theo nội dung được gửi; không tự chuyển đổi theo session time zone. |

Một mô hình phổ biến là lưu thời điểm sự kiện theo UTC, dùng `TIMESTAMP` khi phạm vi năm phù hợp, hoặc dùng `DATETIME` với quy ước UTC được áp dụng nhất quán. Nếu cần lưu lịch địa phương định kỳ (ví dụ 09:00 mỗi ngày theo giờ Paris), lưu cả local date/time và named time zone vì thời điểm UTC tương ứng có thể đổi khi DST thay đổi.

Kiểm tra cấu hình phiên:

```sql
SELECT
    @@global.time_zone AS global_time_zone,
    @@session.time_zone AS session_time_zone,
    @@system_time_zone AS system_time_zone;
```

`SYSTEM` nghĩa là MySQL dựa vào múi giờ hệ điều hành cho cấu hình tương ứng. Có thể đặt session riêng:

```sql
SET SESSION time_zone = '+00:00';
```

Đặt session UTC giúp ứng dụng có quy ước rõ ràng khi đọc/ghi `TIMESTAMP`. Nó không thay thế timezone tables khi cần chuyển đổi theo named zone. Nếu dùng connection pool, phải thiết lập session time zone mỗi khi connection được khởi tạo hoặc bảo đảm pool reset session đúng cách.

## 11. Mẫu thiết kế lưu sự kiện và lịch địa phương

### Sự kiện đã xảy ra: lưu instant UTC

Ví dụ đơn hàng được tạo tại một thời điểm tuyệt đối:

```sql
CREATE TABLE order_events (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    occurred_at_utc DATETIME NOT NULL,
    source_time_zone VARCHAR(64) NULL,
    PRIMARY KEY (id),
    KEY idx_order_events_time (occurred_at_utc)
) ENGINE=InnoDB;
```

Ở đây, ứng dụng cam kết `occurred_at_utc` luôn được gửi theo UTC. Có thể dùng `TIMESTAMP` thay cho `DATETIME` nếu giới hạn phạm vi năm và hành vi session conversion phù hợp. Cột `source_time_zone` là metadata hữu ích khi cần tái hiện cách thời điểm được hiển thị cho người dùng, nhưng không thay thế instant UTC.

### Lịch địa phương trong tương lai: lưu zone ID

Ví dụ một cuộc họp được đặt lúc 09:00 giờ Paris vào một ngày tương lai:

```sql
CREATE TABLE local_appointments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    local_start DATETIME NOT NULL,
    time_zone_id VARCHAR(64) NOT NULL,
    resolved_start_utc DATETIME NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

`local_start` lưu giờ đồng hồ theo lịch địa phương; `time_zone_id` lưu tên IANA như `Europe/Paris`. Ứng dụng dùng timezone database để giải quyết instant UTC. `resolved_start_utc` có thể lưu kết quả đã tính tại thời điểm đặt lịch nếu nghiệp vụ cần khóa một instant cụ thể. Nếu luật DST thay đổi trước ngày diễn ra, cần quyết định lịch giữ nguyên giờ địa phương hay giữ nguyên instant UTC; đây là quy tắc nghiệp vụ, không nên để ngầm định.

## 12. Xử lý truy vấn theo ngày địa phương

Một báo cáo “đơn hàng trong ngày 10-03 tại New York” phải xác định khoảng UTC tương ứng với ngày địa phương đó. Ngày có DST có thể dài 23 hoặc 25 giờ, nên không nên luôn lấy đầu ngày UTC cộng 24 giờ.

Quy trình đúng:

1. Tạo thời điểm bắt đầu ngày địa phương `00:00:00` ở named time zone.
2. Tạo thời điểm bắt đầu ngày địa phương kế tiếp `00:00:00` ở cùng vùng.
3. Chuyển cả hai mốc sang UTC bằng timezone rules.
4. Truy vấn dữ liệu theo khoảng nửa mở `[start_utc, next_start_utc)`.

Ví dụ minh họa với ngày Việt Nam, nơi hiện không áp dụng DST:

```sql
SET @start_local = '2026-01-15 00:00:00';
SET @next_local  = '2026-01-16 00:00:00';

SET @start_utc = CONVERT_TZ(
    @start_local,
    'Asia/Ho_Chi_Minh',
    '+00:00'
);

SET @next_utc = CONVERT_TZ(
    @next_local,
    'Asia/Ho_Chi_Minh',
    '+00:00'
);

SELECT id, order_id, occurred_at_utc
FROM order_events
WHERE occurred_at_utc >= @start_utc
  AND occurred_at_utc < @next_utc
ORDER BY occurred_at_utc;
```

Với vùng có DST, khoảng UTC giữa hai mốc có thể là 23, 24 hoặc 25 giờ. Cách tính hai mốc địa phương riêng biệt vẫn phản ánh đúng ngày trên lịch. Dùng điều kiện nửa mở cũng giúp tránh vấn đề độ chính xác phần giây ở mốc cuối ngày và thân thiện với index trên cột thời gian.

## 13. Chẩn đoán lỗi timezone và DST

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `CONVERT_TZ()` trả `NULL` với named zone | Timezone tables chưa nạp, thiếu vùng hoặc tên sai | Kiểm tra `mysql.time_zone_name`, tên IANA và truy vấn offset cố định đối chứng. |
| Offset mùa hè sai | Timezone tables cũ | Kiểm tra bản tzdb, nạp lại dữ liệu và khởi động lại MySQL theo quy trình. |
| Dev đúng nhưng production sai | Mỗi môi trường có timezone tables hoặc cấu hình session khác nhau | So sánh phiên bản MySQL, tzdb, `@@session.time_zone` và dữ liệu bảng hệ thống. |
| Thời gian hiển thị lệch theo user | `TIMESTAMP` được đọc theo session time zone khác nhau | Kiểm tra `@@session.time_zone` và quy ước của driver/pool. |
| Giờ lịch hẹn xuất hiện hai lần | DST overlap | Lưu zone ID và yêu cầu chính sách chọn occurrence/offset. |
| Giờ lịch hẹn không tồn tại | DST gap | Từ chối hoặc điều chỉnh theo chính sách nghiệp vụ đã định nghĩa. |
| Báo cáo ngày thiếu hoặc thừa bản ghi | Dùng khoảng 24 giờ cố định thay vì ranh giới ngày địa phương | Chuyển hai mốc đầu ngày và ngày kế tiếp riêng biệt sang UTC. |

Một checklist chẩn đoán:

```sql
SELECT VERSION();

SELECT
    @@global.time_zone,
    @@session.time_zone,
    @@system_time_zone;

SELECT COUNT(*) FROM mysql.time_zone_name;

SELECT Name
FROM mysql.time_zone_name
WHERE Name IN ('Asia/Ho_Chi_Minh', 'America/New_York');

SELECT
    CONVERT_TZ('2024-07-01 12:00:00', 'UTC', 'America/New_York') AS summer_time,
    CONVERT_TZ('2024-01-01 12:00:00', 'UTC', 'America/New_York') AS winter_time;
```

Nếu `UTC` hoặc named zone không được nhận diện trong timezone tables, hãy nạp dữ liệu timezone phù hợp. Với hệ thống cần chạy lâu dài, nên đưa kiểm tra named zone vào health check hoặc integration test để phát hiện môi trường thiếu dữ liệu trước khi người dùng gặp lỗi.

## 14. Bài tập thực hành

### Bài tập A — Kiểm tra timezone tables

1. Chạy `SELECT VERSION()` và xem `@@global.time_zone`, `@@session.time_zone`, `@@system_time_zone`.
2. Đếm số bản ghi trong `mysql.time_zone_name`.
3. Kiểm tra `Asia/Ho_Chi_Minh`, `America/New_York` và `Europe/Paris`.
4. Chạy `CONVERT_TZ()` từ UTC sang từng vùng.
5. Ghi lại cách nhận biết lỗi do named zone chưa được nạp.

### Bài tập B — Quan sát DST gap và overlap

1. Chạy truy vấn các instant UTC ngay trước và sau khi New York bắt đầu DST.
2. Quan sát bước nhảy từ `01:59:59` sang `03:00:00`.
3. Chạy hai instant UTC trong khoảng lặp khi kết thúc DST.
4. So sánh giờ địa phương và `utc_offset_minutes`.
5. Giải thích vì sao chỉ lưu local `01:30:00` không đủ xác định instant.

### Bài tập C — Thiết kế lịch hẹn

1. Tạo bảng lưu `local_start` và `time_zone_id`.
2. Chọn một lịch hẹn tại vùng có DST vào ngày chuyển giờ.
3. Định nghĩa chính sách khi giờ không tồn tại và khi giờ xuất hiện hai lần.
4. Chuyển sang UTC sau khi giải quyết chính sách.
5. Mô tả cách xử lý nếu luật DST thay đổi trước ngày diễn ra.

### Bài tập D — Báo cáo theo ngày địa phương

1. Chọn một ngày bình thường và một ngày chuyển DST ở New York.
2. Tính UTC instant của đầu ngày và đầu ngày kế tiếp.
3. Tính số giờ giữa hai mốc.
4. Truy vấn bảng sự kiện theo khoảng `[start_utc, next_start_utc)`.
5. Giải thích vì sao không nên cộng cố định 24 giờ để xác định ngày tiếp theo.

Bạn hoàn thành bài khi có thể nạp và kiểm tra timezone tables, dùng `CONVERT_TZ()` với named zone, phân biệt offset cố định và quy tắc vùng, giải thích DST gap/overlap, thiết kế cách lưu instant và lịch địa phương, và tính đúng khoảng UTC cho báo cáo ngày.

## 15. Nguyên tắc cần ghi nhớ

- Dùng tên IANA như `Asia/Ho_Chi_Minh` và `America/New_York` khi cần quy tắc vùng; offset như `+07:00` chỉ là độ lệch cố định.
- `CONVERT_TZ()` cần timezone tables được nạp để chuyển đổi named zone; tên không được nhận diện thường làm hàm trả `NULL`.
- Nạp timezone tables từ dữ liệu tzdb đáng tin cậy và cập nhật khi luật DST thay đổi.
- Sau khi cập nhật timezone tables, khởi động lại MySQL theo quy trình vận hành để làm mới dữ liệu múi giờ đã cache.
- DST gap tạo giờ địa phương không tồn tại; DST overlap tạo giờ địa phương xuất hiện hai lần.
- Chuyển UTC sang local time xác định được theo timezone rules; chuyển local time sang UTC có thể cần chính sách xử lý gap/overlap.
- Đặt session time zone nhất quán, thường là UTC cho ứng dụng; cấu hình pool phải giữ đúng trạng thái session.
- Lưu instant sự kiện theo UTC; với lịch địa phương tương lai, lưu cả giờ địa phương và named time zone.
- Tạo khoảng báo cáo bằng hai ranh giới ngày địa phương riêng biệt rồi chuyển từng mốc sang UTC; không giả định một ngày luôn dài 24 giờ.

Khi hiểu cách `CONVERT_TZ()`, timezone tables và DST phối hợp, bạn có thể xử lý thời gian nhất quán giữa MySQL và ứng dụng, cập nhật quy tắc múi giờ an toàn và tránh lỗi lịch hẹn hoặc báo cáo khi đồng hồ địa phương thay đổi.

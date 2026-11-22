# Kiểm thử múi giờ, giờ mùa hè, giá trị ngày giờ biên

Bài học này thuộc module **DATABASE_MYSQL**. Khi ứng dụng lưu thời điểm đặt hàng, lịch hẹn, thời hạn thanh toán hoặc dữ liệu đo đạc, kết quả có thể sai dù câu SQL hoàn toàn hợp lệ nếu MySQL, JDBC driver, JVM và ứng dụng đang dùng múi giờ khác nhau. Những lỗi khó phát hiện thường xuất hiện ở thời điểm chuyển sang giờ mùa hè (DST), giờ bị lặp hoặc bị bỏ qua, ngày nhuận, cuối tháng, cuối năm và giá trị có phần giây.

Kiểm thử ngày giờ cần phân biệt **một thời điểm tuyệt đối** với **một thời gian trên đồng hồ địa phương**. Ví dụ, 01:30 ngày 3 tháng 11 tại New York có thể xảy ra hai lần khi đồng hồ lùi một giờ. Một giá trị LocalDateTime không đủ để phân biệt hai thời điểm đó. Bài học này trình bày cách MySQL lưu các kiểu thời gian, cách session time zone và DST ảnh hưởng đến truy vấn, cách kiểm thử biên và cách phối hợp Java/Spring Boot với Connector/J.

## 1. Phân biệt thời điểm tuyệt đối và giờ địa phương

Có hai khái niệm khác nhau:

- **Instant:** một điểm duy nhất trên dòng thời gian, thường biểu diễn bằng UTC hoặc epoch. Ví dụ một giao dịch được xác nhận tại một thời điểm cụ thể.
- **Local date/time:** ngày và giờ theo lịch hoặc đồng hồ tại một địa điểm, chưa gắn với múi giờ. Ví dụ cửa hàng mở cửa lúc 09:00 hoặc cuộc hẹn vào 02:30 ngày 10 tháng 3.

Một instant có thể được hiển thị thành nhiều giờ địa phương tùy múi giờ. Ngược lại, một giờ địa phương có thể không tương ứng với instant nào hoặc tương ứng với hai instant khi quy tắc DST thay đổi đồng hồ.

Ví dụ:

- 2024-03-10 02:30 tại New York không tồn tại vì đồng hồ chuyển từ 01:59:59 sang 03:00:00.
- 2024-11-03 01:30 tại New York xảy ra hai lần: lần đầu theo UTC-04:00, lần sau theo UTC-05:00.

Vì vậy, trước khi chọn kiểu cột, hãy xác định dữ liệu đại diện cho điều gì:

| Nghiệp vụ | Mô hình dữ liệu thường phù hợp |
|---|---|
| Thời điểm thanh toán hoặc ghi nhận sự kiện | Instant, lưu theo quy ước UTC |
| Ngày sinh hoặc ngày nghỉ lễ | LocalDate / MySQL DATE |
| Giờ mở cửa hàng ngày | LocalTime, thường không cần ngày hoặc múi giờ |
| Lịch hẹn tại một địa điểm | Local date/time + ZoneId, sau đó xác định instant theo quy tắc DST |
| Thời điểm một thiết bị gửi dữ liệu | Instant, kèm metadata nguồn nếu cần |
| Thời lượng xử lý | Duration hoặc giá trị duration; không xem TIME như một instant |

Không nên lưu một giờ địa phương rồi giả định rằng nó luôn xác định duy nhất một thời điểm.

## 2. Các kiểu ngày giờ của MySQL

MySQL có các kiểu temporal với ngữ nghĩa khác nhau:

| Kiểu | Dữ liệu biểu diễn | Múi giờ và chuyển đổi | Phạm vi khái quát |
|---|---|---|---|
| DATE | Ngày lịch | Không chứa múi giờ | 1000-01-01 đến 9999-12-31 |
| TIME | Giờ hoặc thời lượng | Không phải instant có múi giờ | -838:59:59.000000 đến 838:59:59.000000 |
| DATETIME | Ngày và giờ trên đồng hồ | Lưu các thành phần ngày/giờ, không tự chuyển đổi theo session time zone | 1000-01-01 00:00:00 đến 9999-12-31 23:59:59 |
| TIMESTAMP | Thời điểm | MySQL chuyển đổi giữa session time zone và UTC khi ghi/đọc | Thông thường từ 1970-01-01 00:00:01 UTC đến 2038-01-19 03:14:07 UTC |
| YEAR | Năm | Không có múi giờ | Phạm vi phụ thuộc cú pháp và chế độ, thường 1901-2155 cùng giá trị 0000 |

Các kiểu TIME, DATETIME và TIMESTAMP hỗ trợ phần giây lẻ với precision từ 0 đến 6 chữ số, ví dụ DATETIME(6) hoặc TIMESTAMP(3). Phạm vi và một số hành vi chi tiết cần kiểm tra theo phiên bản MySQL.

### 2.1. DATE

DATE chỉ lưu ngày, không có giờ và múi giờ:

~~~sql
CREATE TABLE holidays (
    holiday_date DATE NOT NULL,
    description VARCHAR(100) NOT NULL,
    PRIMARY KEY (holiday_date)
);
~~~

DATE phù hợp với ngày sinh, ngày hiệu lực theo lịch hoặc ngày nghỉ lễ. Không nên lưu ngày sinh dưới dạng TIMESTAMP nếu nghiệp vụ không đại diện cho một thời điểm cụ thể, vì việc chuyển múi giờ có thể làm ngày hiển thị thay đổi.

### 2.2. DATETIME

DATETIME lưu các thành phần năm, tháng, ngày, giờ, phút, giây và phần giây lẻ nếu được khai báo. MySQL không tự chuyển giá trị DATETIME giữa UTC và session time zone.

~~~sql
CREATE TABLE store_schedule (
    store_id BIGINT NOT NULL,
    opens_at DATETIME NOT NULL,
    PRIMARY KEY (store_id)
);
~~~

DATETIME phù hợp với giờ địa phương hoặc giá trị ngày giờ cần giữ nguyên các thành phần đã nhập. Tuy nhiên, cột DATETIME không lưu ZoneId hoặc offset. Nếu dữ liệu là lịch hẹn theo múi giờ, lưu thêm tên múi giờ như America/New_York để có thể diễn giải lại theo quy tắc vùng.

### 2.3. TIMESTAMP

TIMESTAMP được MySQL chuyển đổi từ session time zone sang UTC khi ghi và chuyển từ UTC về session time zone khi đọc. Cột này phù hợp với thời điểm tuyệt đối khi ứng dụng và database thống nhất cách xử lý múi giờ.

~~~sql
CREATE TABLE payment_events (
    event_id BIGINT PRIMARY KEY,
    paid_at TIMESTAMP(6) NOT NULL
);
~~~

Cùng một giá trị được đọc từ hai session có time zone khác nhau có thể hiển thị thành hai giờ địa phương khác nhau, nhưng vẫn đại diện cho cùng instant.

Phạm vi TIMESTAMP hẹp hơn DATETIME đáng kể. Nếu nghiệp vụ cần lưu ngày giờ ngoài phạm vi TIMESTAMP, chẳng hạn dữ liệu lịch sử rất xa hoặc lịch tương lai nhiều thế kỷ, hãy đánh giá DATETIME và quy ước múi giờ riêng.

### 2.4. TIME

TIME biểu diễn giờ hoặc khoảng thời gian, có thể âm và có thể lớn hơn 24 giờ. Ví dụ thời lượng xử lý 27 giờ có thể được biểu diễn bằng TIME, nhưng TIME không nên được hiểu như “giờ trong ngày” có múi giờ.

~~~sql
CREATE TABLE job_metrics (
    job_id BIGINT PRIMARY KEY,
    elapsed_time TIME(3) NOT NULL
);
~~~

Nếu nghiệp vụ cần đo thời lượng dài hoặc tính toán chính xác theo mili/micro giây, cân nhắc lưu số nguyên theo đơn vị đã thống nhất hoặc dùng kiểu duration trong ứng dụng. Hãy xác định rõ cách xử lý giá trị âm và giới hạn của TIME.

## 3. Session time zone và cách MySQL chuyển đổi

MySQL có các biến múi giờ:

~~~sql
SELECT @@global.time_zone,
       @@session.time_zone,
       @@system_time_zone;
~~~

- global time zone là giá trị mặc định được dùng khi tạo session mới.
- session time zone là múi giờ đang áp dụng cho connection hiện tại.
- system time zone phản ánh múi giờ hệ điều hành mà MySQL nhận diện khi khởi động.

Thay đổi global time zone không tự thay đổi session đã mở. Connection pool có thể giữ connection lâu dài, vì vậy cần kiểm tra session time zone trên từng connection thực tế.

### 3.1. Kiểm thử TIMESTAMP và DATETIME trên hai session

Tạo bảng thử:

~~~sql
CREATE TEMPORARY TABLE temporal_probe (
    id INT PRIMARY KEY,
    ts_value TIMESTAMP(6) NOT NULL,
    dt_value DATETIME(6) NOT NULL
);
~~~

Ghi cùng một chuỗi khi session dùng UTC:

~~~sql
SET SESSION time_zone = '+00:00';

INSERT INTO temporal_probe (id, ts_value, dt_value)
VALUES (1, '2024-01-15 12:00:00.123456',
           '2024-01-15 12:00:00.123456');

SELECT ts_value, dt_value
FROM temporal_probe
WHERE id = 1;
~~~

Sau đó đổi session sang UTC+05:30 và đọc lại:

~~~sql
SET SESSION time_zone = '+05:30';

SELECT ts_value, dt_value
FROM temporal_probe
WHERE id = 1;
~~~

TIMESTAMP được hiển thị theo session time zone mới, trong khi DATETIME giữ nguyên thành phần ngày giờ đã lưu. Đây là một kiểm thử quan trọng để chứng minh ứng dụng không vô tình dựa vào múi giờ mặc định của connection.

### 3.2. NOW(), CURRENT_TIMESTAMP và UTC_TIMESTAMP

Các hàm thời gian có ngữ nghĩa khác nhau:

~~~sql
SELECT NOW(6) AS session_now,
       CURRENT_TIMESTAMP(6) AS session_current_timestamp,
       UTC_TIMESTAMP(6) AS utc_now,
       @@session.time_zone AS session_zone;
~~~

NOW() và CURRENT_TIMESTAMP() trả về thời điểm theo session time zone. UTC_TIMESTAMP() trả về giá trị theo UTC. Khi dùng default CURRENT_TIMESTAMP cho cột TIMESTAMP, cần hiểu session time zone của connection ghi dữ liệu.

Để tránh kết quả test phụ thuộc môi trường, có thể cố định session time zone:

~~~sql
SET SESSION time_zone = '+00:00';
~~~

Offset '+00:00' không cần MySQL tra cứu tên vùng trong time zone tables.

## 4. Múi giờ có tên và time zone tables

MySQL hỗ trợ múi giờ dạng offset, như '+00:00' hoặc '-05:00', và tên vùng như 'America/New_York', 'Asia/Ho_Chi_Minh'. Tên vùng có chứa quy tắc lịch sử và DST. Để MySQL xử lý tên vùng, các time zone tables phải được nạp và cập nhật.

Kiểm tra named time zone:

~~~sql
SELECT CONVERT_TZ(
    '2024-01-15 12:00:00',
    '+00:00',
    'Asia/Ho_Chi_Minh'
) AS local_time;
~~~

Nếu kết quả là NULL, nguyên nhân có thể là tên múi giờ không hợp lệ hoặc time zone tables chưa được nạp/đầy đủ.

Kiểm tra các bảng hệ thống:

~~~sql
SELECT COUNT(*) AS timezone_name_count
FROM mysql.time_zone_name;
~~~

Việc nạp time zone tables thường được thực hiện bởi quản trị viên từ dữ liệu zoneinfo của hệ điều hành bằng công cụ MySQL phù hợp với nền tảng. Sau khi cập nhật dữ liệu múi giờ, cần làm theo hướng dẫn vận hành của phiên bản MySQL và kiểm tra lại kết quả CONVERT_TZ. Không tự sửa trực tiếp các bảng time zone bằng câu UPDATE tùy ý.

### 4.1. Offset cố định và tên vùng

Offset cố định như '-05:00' chỉ mô tả độ lệch tại một thời điểm. Nó không biểu diễn toàn bộ quy tắc DST của New York. Trong mùa hè, New York thường dùng UTC-04:00; mùa đông thường dùng UTC-05:00.

Tên vùng như 'America/New_York' cho phép MySQL sử dụng quy tắc vùng nếu time zone tables đã được nạp. Với dữ liệu nghiệp vụ dài hạn, lưu ZoneId thường tốt hơn lưu một offset cố định khi cần tái hiện giờ địa phương theo luật hiện hành.

Quy tắc múi giờ có thể được cơ quan quản lý thay đổi. Hãy có kế hoạch cập nhật timezone database của hệ điều hành, MySQL và JVM; cùng một tên vùng có thể cho kết quả khác nhau giữa các bản tzdata.

## 5. Kiểm thử giờ mùa hè (DST)

DST làm đồng hồ địa phương nhảy tiến hoặc lùi. Hai trường hợp phải kiểm tra riêng:

- **Gap (giờ không tồn tại):** đồng hồ nhảy tiến, một khoảng giờ địa phương bị bỏ qua.
- **Overlap (giờ bị lặp):** đồng hồ lùi, một khoảng giờ địa phương xảy ra hai lần.

Ví dụ dùng America/New_York năm 2024:

| Sự kiện | Instant UTC | Giờ địa phương |
|---|---|---|
| Trước khi chuyển sang DST | 2024-03-10 06:30 UTC | 2024-03-10 01:30 UTC-05:00 |
| Sau khi chuyển sang DST | 2024-03-10 07:30 UTC | 2024-03-10 03:30 UTC-04:00 |
| Lần đầu giờ bị lặp | 2024-11-03 05:30 UTC | 2024-11-03 01:30 UTC-04:00 |
| Lần thứ hai giờ bị lặp | 2024-11-03 06:30 UTC | 2024-11-03 01:30 UTC-05:00 |

Hai instant khác nhau trong tháng 11 cùng được hiển thị là 01:30. Nếu chỉ lưu local datetime 2024-11-03 01:30 mà không có offset hoặc zone resolution, không thể xác định đó là lần thứ nhất hay lần thứ hai.

### 5.1. Kiểm thử chuyển đổi UTC sang giờ địa phương

Với time zone tables đã nạp, chạy:

~~~sql
SELECT
    CONVERT_TZ('2024-03-10 06:30:00', '+00:00',
               'America/New_York') AS before_spring_jump,
    CONVERT_TZ('2024-03-10 07:30:00', '+00:00',
               'America/New_York') AS after_spring_jump,
    CONVERT_TZ('2024-11-03 05:30:00', '+00:00',
               'America/New_York') AS first_fall_0130,
    CONVERT_TZ('2024-11-03 06:30:00', '+00:00',
               'America/New_York') AS second_fall_0130;
~~~

Kết quả cần cho thấy giờ địa phương nhảy từ 01:30 sang 03:30 vào mùa xuân, và hai instant khác nhau trong mùa thu cùng hiển thị 01:30 nhưng với offset khác nhau nếu ứng dụng lưu/hiển thị offset tương ứng.

### 5.2. Giờ địa phương không tồn tại

02:30 ngày 10 tháng 3 năm 2024 tại New York nằm trong gap. Khi người dùng nhập giờ này, ứng dụng phải có chính sách rõ ràng:

- Từ chối và yêu cầu chọn giờ hợp lệ.
- Tự chuyển sang thời điểm đầu tiên hợp lệ sau gap.
- Áp dụng một quy tắc nghiệp vụ đã công bố.

Không nên để hành vi ngầm của driver hoặc database quyết định nghiệp vụ. Test cần xác nhận chính sách được áp dụng nhất quán.

### 5.3. Giờ địa phương bị lặp

01:30 ngày 3 tháng 11 năm 2024 tại New York có hai offset hợp lệ. Nếu ứng dụng cần phân biệt, giao diện hoặc API phải nhận thêm offset/choice, hoặc nghiệp vụ phải quy định chọn lần sớm hơn/lần muộn hơn.

Không thể chỉ lưu local datetime rồi kỳ vọng khôi phục đúng instant về sau. Hãy lưu instant đã được resolve; nếu cần hiển thị lại theo vùng, lưu thêm ZoneId.

## 6. Kiểm thử giá trị ngày giờ biên

Kiểm thử ngày giờ cần bao phủ nhiều biên lịch và kiểu dữ liệu, không chỉ các giá trị thông thường.

### 6.1. Năm nhuận và ngày cuối tháng

Theo lịch Gregorian, năm chia hết cho 4 thường là năm nhuận, ngoại trừ năm chia hết cho 100 không phải năm nhuận trừ khi cũng chia hết cho 400.

| Ngày | Kỳ vọng |
|---|---|
| 2024-02-29 | Hợp lệ |
| 2000-02-29 | Hợp lệ |
| 1900-02-29 | Không hợp lệ |
| 2023-02-29 | Không hợp lệ |
| 2024-04-30 | Hợp lệ |
| 2024-04-31 | Không hợp lệ |

Kiểm thử bằng câu lệnh chèn có chủ đích trong môi trường test:

~~~sql
CREATE TEMPORARY TABLE date_probe (
    id INT PRIMARY KEY,
    value_date DATE
);

INSERT INTO date_probe VALUES
    (1, '2024-02-29'),
    (2, '2000-02-29'),
    (3, '2024-04-30');
~~~

Các giá trị không hợp lệ nên được thử riêng để xác nhận MySQL trả lỗi hay warning theo SQL mode. Không gộp giá trị hợp lệ và không hợp lệ vào một insert duy nhất nếu muốn xác định chính xác hành vi lỗi của từng trường hợp.

### 6.2. Cuối tháng và phép cộng tháng

Cộng một tháng vào ngày cuối tháng không đơn giản như cộng một số ngày cố định:

~~~sql
SELECT DATE_ADD('2024-01-31', INTERVAL 1 MONTH) AS leap_year_result,
       DATE_ADD('2023-01-31', INTERVAL 1 MONTH) AS common_year_result,
       DATE_ADD('2024-03-31', INTERVAL 1 MONTH) AS next_month_result;
~~~

MySQL điều chỉnh ngày kết quả về ngày cuối cùng của tháng đích khi ngày ban đầu không tồn tại ở tháng mới. Kiểm thử các trường hợp ngày 28, 29, 30, 31 và tháng 2 để tránh lỗi tính hạn thanh toán hoặc chu kỳ gia hạn.

Nếu nghiệp vụ định nghĩa “sau 30 ngày” thì dùng INTERVAL DAY; nếu định nghĩa “cùng ngày của tháng kế tiếp” thì phải xác định rõ cách xử lý ngày không tồn tại. Hai quy tắc này không tương đương.

### 6.3. Đầu và cuối ngày, tháng, năm

Các biên cần kiểm thử:

- 00:00:00 đầu ngày.
- 23:59:59 và 23:59:59.999999 cuối ngày.
- 00:00:00 ngày đầu tháng.
- Ngày cuối tháng và tháng 2.
- 31 tháng 12 chuyển sang 1 tháng 1.
- Giao điểm cuối năm nhuận.
- Khoảng thời gian cắt qua nửa đêm hoặc năm mới.

Khi lọc dữ liệu theo ngày, ưu tiên khoảng nửa mở:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2024-03-01 00:00:00'
  AND created_at <  '2024-04-01 00:00:00';
~~~

Khoảng [đầu, cuối) tránh phải đoán precision cuối ngày và hoạt động tốt với DATETIME(6)/TIMESTAMP(6). Cũng giúp optimizer sử dụng index trên cột thời gian dễ hơn so với việc bọc cột trong hàm DATE().

### 6.4. Giá trị bằng 0 và ngày không hợp lệ

MySQL có các chế độ SQL ảnh hưởng đến việc chấp nhận zero date, zero-in-date và ngày không hợp lệ. Kiểm tra cấu hình thực tế:

~~~sql
SELECT @@sql_mode;
~~~

Các mode có thể liên quan gồm STRICT_TRANS_TABLES, STRICT_ALL_TABLES, NO_ZERO_DATE, NO_ZERO_IN_DATE và ALLOW_INVALID_DATES. Tình trạng hỗ trợ hoặc cách kết hợp mode thay đổi theo phiên bản; không giả định mọi server có cùng hành vi.

Các giá trị như '0000-00-00' hoặc '2024-00-15' thường là dấu hiệu dữ liệu legacy hoặc quy ước thiếu dữ liệu. Trong schema mới, ưu tiên NULL cho giá trị chưa biết hoặc không áp dụng, và dùng constraint/nghiệp vụ để kiểm soát dữ liệu hợp lệ.

Khi kiểm thử dữ liệu sai, ghi nhận cả lỗi và warning:

~~~sql
INSERT INTO date_probe (id, value_date)
VALUES (10, '2023-02-29');

SHOW WARNINGS;
~~~

Câu INSERT có thể thất bại hoặc chuyển giá trị tùy SQL mode và cách thực thi. Cần xác minh cả trạng thái statement, số hàng thực sự ghi và warning. INSERT IGNORE có thể làm thay đổi hành vi lỗi thành warning và không nên dùng trong test tính hợp lệ cơ bản.

## 7. Kiểm thử fractional seconds

MySQL hỗ trợ precision phần giây từ 0 đến 6:

~~~sql
CREATE TEMPORARY TABLE precision_probe (
    id INT PRIMARY KEY,
    dt0 DATETIME,
    dt3 DATETIME(3),
    dt6 DATETIME(6)
);

INSERT INTO precision_probe (id, dt0, dt3, dt6)
VALUES (
    1,
    '2024-05-01 12:30:45.123456',
    '2024-05-01 12:30:45.123456',
    '2024-05-01 12:30:45.123456'
);

SELECT dt0, dt3, dt6
FROM precision_probe;
~~~

Khi cột có precision thấp hơn giá trị đầu vào, phần giây lẻ được làm tròn hoặc cắt theo SQL mode TIME_TRUNCATE_FRACTIONAL. Kiểm tra mode:

~~~sql
SELECT @@sql_mode;
~~~

Ví dụ test cần bao gồm giá trị sát ranh giới làm tròn, chẳng hạn .1234, .1235, .9994 và .9995 khi lưu vào DATETIME(3). Kiểm tra giá trị đọc lại thay vì giả định driver và server luôn cắt theo cùng một quy tắc.

Nếu ứng dụng cần độ chính xác microsecond, khai báo cột (6) và kiểm tra kiểu Java/driver có giữ precision đó. Java Instant có nanosecond precision; MySQL temporal columns tối đa microsecond. Khi lưu, dữ liệu có thể bị giảm precision. Test cần xác định quy tắc làm tròn/cắt và so sánh theo precision đã cam kết.

## 8. Kiểm thử trong Java với java.time

Java cung cấp các kiểu thời gian có ngữ nghĩa rõ:

| Java type | Ý nghĩa |
|---|---|
| LocalDate | Ngày lịch, không có giờ và zone |
| LocalTime | Giờ trên đồng hồ, không có ngày và zone |
| LocalDateTime | Ngày giờ địa phương, không có zone |
| Instant | Thời điểm tuyệt đối trên UTC timeline |
| OffsetDateTime | Ngày giờ kèm offset cố định |
| ZonedDateTime | Ngày giờ cùng ZoneId và quy tắc múi giờ |
| Duration | Khoảng thời gian theo giây/nanosecond |
| Period | Khoảng thời gian theo năm/tháng/ngày lịch |

Đừng dùng LocalDateTime để đại diện một instant nếu không có quy ước zone đi kèm. LocalDateTime không thể tự quyết định offset khi gặp DST overlap.

### 8.1. Kiểm tra gap và overlap bằng ZoneRules

Java có thể kiểm tra số offset hợp lệ cho một giờ địa phương:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZoneRules rules = zone.getRules();

LocalDateTime springGap =
    LocalDateTime.of(2024, 3, 10, 2, 30);

LocalDateTime fallOverlap =
    LocalDateTime.of(2024, 11, 3, 1, 30);

List<ZoneOffset> gapOffsets = rules.getValidOffsets(springGap);
List<ZoneOffset> overlapOffsets = rules.getValidOffsets(fallOverlap);

assertTrue(gapOffsets.isEmpty());
assertEquals(2, overlapOffsets.size());
~~~

Ý nghĩa:

- Không có offset hợp lệ: local datetime nằm trong gap.
- Một offset hợp lệ: thời điểm địa phương không mơ hồ.
- Hai offset hợp lệ: local datetime nằm trong overlap và cần chọn một offset.

Có thể kiểm tra các instant tương ứng:

~~~java
import java.util.stream.Collectors;

List<Instant> possibleInstants = overlapOffsets.stream()
    .map(offset -> fallOverlap.toInstant(offset))
    .collect(Collectors.toList());

assertEquals(2, possibleInstants.size());
assertNotEquals(possibleInstants.get(0), possibleInstants.get(1));
~~~

Chính sách chọn offset phải là quyết định nghiệp vụ. Nếu dùng ZonedDateTime.of() với local datetime mơ hồ, Java áp dụng quy tắc mặc định của API; không nên dựa vào mặc định đó nếu nghiệp vụ cần phân biệt lần sớm và lần muộn.

### 8.2. Dùng Clock cố định để test

Không để test phụ thuộc đồng hồ thực của máy chạy:

~~~java
Clock fixedClock = Clock.fixed(
    Instant.parse("2024-11-03T06:30:00Z"),
    ZoneOffset.UTC
);

Instant now = Instant.now(fixedClock);

assertEquals(
    Instant.parse("2024-11-03T06:30:00Z"),
    now
);
~~~

Tiêm Clock vào service giúp kiểm thử hạn thanh toán, hết hạn token, ngày chốt sổ và quy tắc qua nửa đêm một cách ổn định.

### 8.3. Kiểm tra ngày nhuận trong Java

~~~java
assertTrue(LocalDate.of(2024, 2, 29).isLeapYear());
assertFalse(LocalDate.of(1900, 1, 1).isLeapYear());
assertTrue(LocalDate.of(2000, 1, 1).isLeapYear());

assertThrows(
    DateTimeException.class,
    () -> LocalDate.of(2023, 2, 29)
);
~~~

Các test Java xác minh logic lịch của ứng dụng. Vẫn cần integration test với MySQL để kiểm tra cách driver bind/extract và cách server chấp nhận giá trị.

## 9. Spring Boot, Hibernate và Connector/J

Một hệ thống Spring Boot có nhiều lớp múi giờ:

1. JVM default time zone.
2. Java type và cách ứng dụng chuyển đổi dữ liệu.
3. Hibernate JDBC timezone.
4. Connector/J connection time zone và session time zone.
5. MySQL global/session time zone.
6. Named timezone rules từ timezone database của JVM, hệ điều hành và MySQL.

Nếu mỗi lớp tự chọn một giá trị, cùng một thời điểm có thể bị chuyển đổi hai lần hoặc hiển thị lệch giờ.

### 9.1. Chọn quy ước UTC cho instant

Với nghiệp vụ lưu thời điểm tuyệt đối, một cấu hình thường được cân nhắc:

~~~properties
spring.jpa.properties.hibernate.jdbc.time_zone=UTC
~~~

Thuộc tính Hibernate này điều khiển timezone được dùng khi bind/extract các JDBC temporal values có hỗ trợ Calendar. Nó không tự động đặt biến @@session.time_zone của MySQL.

Với MySQL Connector/J từ 8.0.23, có thể cấu hình rõ connection time zone và việc đồng bộ session:

~~~text
jdbc:mysql://db.example.net:3306/shop?connectionTimeZone=%2B00:00&forceConnectionTimeZoneToSession=true&preserveInstants=true
~~~

Các thuộc tính trên cần được xác minh theo đúng Connector/J version. connectionTimeZone xác định múi giờ mà driver dùng trong chuyển đổi; forceConnectionTimeZoneToSession yêu cầu driver đặt session time zone tương ứng; preserveInstants điều khiển cách driver giữ instant khi chuyển đổi giữa Java và MySQL temporal types.

Đây không phải cấu hình bắt buộc cho mọi ứng dụng. Hãy kiểm tra hành vi thực tế của kiểu Java, SQL type, driver version và server version. Không bật nhiều thuộc tính timezone mà không hiểu tác động của từng lớp.

### 9.2. Kiểm tra session time zone qua connection pool

Khi dùng HikariCP hoặc connection pool khác, connection vật lý được tái sử dụng. Kiểm tra session time zone trên connection do pool cấp:

~~~java
try (Connection connection = dataSource.getConnection();
     Statement statement = connection.createStatement();
     ResultSet rs = statement.executeQuery(
         "SELECT @@session.time_zone, @@global.time_zone")) {

    if (rs.next()) {
        String sessionZone = rs.getString(1);
        String globalZone = rs.getString(2);
        assertEquals("+00:00", sessionZone);
    }
}
~~~

Giá trị kỳ vọng phải khớp cấu hình ứng dụng. Nếu session zone thay đổi trong một request, cần khôi phục trước khi trả connection về pool. Tốt hơn là giữ một quy ước cố định cho mọi connection và không đổi time zone theo từng nghiệp vụ.

Có thể cấu hình connection initialization SQL trong pool để thiết lập session, nhưng cần xác minh nó được chạy trên mỗi physical connection mới và không bị code ứng dụng thay đổi về sau. Nếu Connector/J đã được cấu hình forceConnectionTimeZoneToSession, tránh đặt hai cơ chế mâu thuẫn.

### 9.3. Lưu lịch hẹn và múi giờ vùng

Với lịch hẹn, lưu cả instant và ZoneId nếu cần giữ ngữ nghĩa vùng:

~~~sql
CREATE TABLE appointments (
    appointment_id BIGINT PRIMARY KEY,
    starts_at_utc TIMESTAMP(6) NOT NULL,
    zone_id VARCHAR(64) NOT NULL,
    local_start DATETIME(6) NOT NULL
);
~~~

Cách thiết kế cụ thể tùy nghiệp vụ:

- starts_at_utc xác định instant đã được chốt.
- zone_id lưu vùng để hiển thị và diễn giải theo địa điểm.
- local_start giữ giờ địa phương người dùng đã chọn nếu cần audit hoặc xử lý thay đổi quy tắc.

Với lịch lặp như “09:00 mỗi thứ Hai tại Ho Chi Minh City”, chỉ lưu một instant không đủ để tạo lịch tương lai. Cần lưu quy tắc lặp, local time và ZoneId, sau đó tính instant cho từng lần chạy theo timezone rules hiện hành.

Nếu luật múi giờ thay đổi sau khi lịch đã tạo, doanh nghiệp cần quyết định giữ instant cũ hay giữ giờ địa phương theo quy tắc mới. Đây là quyết định nghiệp vụ, không thể giải quyết chỉ bằng kiểu cột.

## 10. Integration test với MySQL thật

Test bằng mock repository không thể xác nhận hành vi chuyển đổi của MySQL Server và Connector/J. Dùng MySQL Testcontainers hoặc một instance kiểm thử tương đương production.

Các bước nên có:

1. Chọn đúng MySQL version và Connector/J version.
2. Xác định SQL mode và session time zone.
3. Xác nhận named time zone tables có dữ liệu nếu test dùng ZoneId.
4. Tạo bảng DATE, DATETIME(6), TIMESTAMP(6), TIME(6).
5. Ghi giá trị qua JDBC/Hibernate.
6. Đọc lại qua cùng connection và một connection có session zone khác.
7. So sánh giá trị với kỳ vọng nghiệp vụ, không chỉ so sánh chuỗi hiển thị.
8. Kiểm tra fractional seconds, ngày nhuận, tháng cuối năm, gap và overlap.
9. Chạy test sau khi nâng Connector/J, Hibernate hoặc MySQL version.

Ví dụ kiểm tra named timezone trước test:

~~~sql
SELECT CONVERT_TZ(
    '2024-03-10 07:30:00',
    '+00:00',
    'America/New_York'
) IS NOT NULL AS timezone_data_available;
~~~

Nếu kết quả là 0, test dựa trên tên vùng chưa có điều kiện chạy hợp lệ. Hãy nạp timezone tables hoặc đánh dấu môi trường test thiếu dependency; không bỏ qua test rồi xem đó là pass.

### 10.1. Bảng dữ liệu kiểm thử gợi ý

~~~sql
CREATE TABLE temporal_cases (
    case_id INT PRIMARY KEY,
    date_value DATE NULL,
    time_value TIME(6) NULL,
    datetime_value DATETIME(6) NULL,
    timestamp_value TIMESTAMP(6) NULL
);
~~~

Tập dữ liệu nên có:

| Nhóm | Giá trị đại diện |
|---|---|
| Ngày thường | 2024-06-15 |
| Ngày nhuận | 2024-02-29 |
| Ngày không nhuận | 2023-02-28 |
| Cuối tháng | 2024-01-31, 2024-02-29 |
| Cuối năm | 2024-12-31 23:59:59.999999 |
| Đầu năm | 2025-01-01 00:00:00.000000 |
| Nửa đêm | 00:00:00 |
| Cuối ngày | 23:59:59.999999 |
| Phần giây | .000001, .123456, .999999 |
| DST gap | 2024-03-10 02:30 America/New_York |
| DST overlap | 2024-11-03 01:30 America/New_York với hai offset |
| Giá trị ngoài phạm vi TIMESTAMP | Ngày trước 1970 hoặc sau 2038 |
| Giá trị không hợp lệ | 2023-02-29, tháng 13, ngày 0, zero date |

Không phải mọi giá trị trong bảng đều nên insert thành công. Một số là test âm để xác nhận MySQL từ chối hoặc phát warning theo SQL mode và kiểu cột.

## 11. Các lỗi kiểm thử thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách chẩn đoán |
|---|---|---|
| TIMESTAMP lệch vài giờ | Session time zone hoặc JDBC timezone khác UTC | Kiểm tra @@session.time_zone, JVM zone và driver properties |
| DATETIME không đổi khi đổi session zone | Hành vi lưu literal của DATETIME | Đây là hành vi mong đợi; kiểm tra ứng dụng có đang giả định nó là instant không |
| CONVERT_TZ trả NULL | Named zone không tồn tại hoặc timezone tables thiếu | Kiểm tra mysql.time_zone_name và tên vùng |
| Lịch hẹn chạy sai khi DST | LocalDateTime không có ZoneId hoặc chưa xử lý gap/overlap | Kiểm tra ZoneRules và chính sách resolve |
| Ngày 29 tháng 2 bị từ chối | Năm không nhuận hoặc SQL mode nghiêm ngặt | Kiểm tra dữ liệu, leap year và @@sql_mode |
| Ngày sai được chấp nhận trong test | SQL mode khác production hoặc ALLOW_INVALID_DATES | Đồng bộ SQL mode và kiểm tra warning |
| Mất phần microsecond | Cột precision thấp, driver hoặc mapping làm giảm precision | Kiểm tra DATETIME(6)/TIMESTAMP(6), JDBC type và giá trị đọc lại |
| Kết quả test phụ thuộc máy chạy | Dùng system default timezone hoặc đồng hồ hiện tại | Cố định Clock, JVM zone và session zone |
| Test chạy được local nhưng lỗi container | MySQL image chưa nạp timezone tables hoặc khác SQL mode | Khởi tạo test fixture và xác minh cấu hình container |
| Dữ liệu sau 2038 không ghi được vào TIMESTAMP | Vượt phạm vi TIMESTAMP | Đánh giá DATETIME và quy ước timezone phù hợp |

## 12. Ma trận kiểm thử đề xuất

Một bộ test tốt nên kết hợp nhiều trục thay vì chỉ thử một timezone:

| Trục | Các trường hợp |
|---|---|
| Kiểu MySQL | DATE, TIME, DATETIME(0/3/6), TIMESTAMP(0/3/6) |
| Session zone | +00:00, +05:30, +07:00, SYSTEM, named zone |
| DST | Vùng không DST, gap, overlap, trước/sau chuyển đổi |
| Lịch | Năm nhuận, cuối tháng, cuối năm, nửa đêm, giá trị sai |
| SQL mode | Cấu hình production, strict, zero-date và invalid-date modes nếu được hỗ trợ |
| Java type | LocalDate, LocalTime, LocalDateTime, Instant, OffsetDateTime, ZonedDateTime |
| Driver | Connector/J version đang chạy và version mục tiêu sau nâng cấp |
| ORM | Hibernate version hiện tại và version mục tiêu |
| Kết nối | Connection mới, connection pool tái sử dụng, reconnect |
| Đường dữ liệu | JDBC trực tiếp, Hibernate/JPA, native query, stored routine nếu có |

Mỗi trường hợp cần ghi rõ:

- Giá trị đầu vào và kiểu Java.
- SQL type và precision của cột.
- JVM timezone.
- Connector/J connection time zone.
- MySQL session time zone.
- SQL mode và timezone data version.
- Giá trị được lưu và giá trị đọc lại.
- Kết quả kỳ vọng cùng sai lệch được chấp nhận nếu có.

## 13. Checklist trước khi phát hành

- [ ] Đã phân loại dữ liệu là ngày lịch, giờ địa phương, thời lượng hay instant.
- [ ] Đã chọn DATE, TIME, DATETIME hoặc TIMESTAMP đúng ngữ nghĩa.
- [ ] Đã xác định precision phần giây cần thiết.
- [ ] Đã xác minh phạm vi kiểu temporal với dữ liệu lịch sử/tương lai.
- [ ] Đã kiểm tra JVM timezone, Hibernate JDBC timezone và Connector/J properties.
- [ ] Đã xác minh @@session.time_zone trên connection pool.
- [ ] Đã nạp và kiểm tra named timezone tables nếu dùng CONVERT_TZ với tên vùng.
- [ ] Đã test DST gap và overlap bằng một vùng có chuyển giờ.
- [ ] Đã kiểm thử ngày nhuận, cuối tháng, cuối năm và nửa đêm.
- [ ] Đã kiểm thử zero date, invalid date và SQL mode của production.
- [ ] Đã kiểm thử fractional seconds ở precision thực tế.
- [ ] Đã dùng Clock cố định trong unit test.
- [ ] Đã chạy integration test trên MySQL và Connector/J tương ứng production.
- [ ] Đã quyết định cách xử lý lịch lặp khi quy tắc timezone thay đổi.
- [ ] Đã kiểm tra log, cảnh báo và dữ liệu nhạy cảm trong test output.

## 14. Tự kiểm tra

1. TIMESTAMP và DATETIME khác nhau thế nào khi session time zone thay đổi?
2. Vì sao DATE phù hợp hơn TIMESTAMP cho ngày sinh?
3. Vì sao offset cố định -05:00 không thay thế được ZoneId America/New_York?
4. DST gap và overlap khác nhau như thế nào?
5. Vì sao local datetime 2024-11-03 01:30 tại New York có thể đại diện cho hai instant?
6. MySQL cần điều kiện gì để CONVERT_TZ xử lý tên vùng?
7. Vì sao đổi global time_zone không tự thay đổi session hiện tại trong connection pool?
8. Vì sao cần kiểm thử năm 2000 và 1900 khi xử lý ngày nhuận?
9. Fractional seconds precision ảnh hưởng thế nào đến round-trip giữa Java và MySQL?
10. Hãy thiết kế test cho một lịch hẹn định kỳ lúc 02:30 tại New York, bao gồm ngày chuyển DST mùa xuân và mùa thu.

Khi kiểm thử ngày giờ, hãy cố định các yếu tố môi trường và xác định ngữ nghĩa của dữ liệu trước khi so sánh kết quả. Với instant, thống nhất UTC qua ứng dụng, driver và session; với lịch địa phương, giữ ZoneId và quy định rõ cách xử lý giờ không tồn tại hoặc bị lặp. Cuối cùng, chạy integration test trên MySQL thật để phát hiện khác biệt về session timezone, timezone tables, SQL mode và precision mà unit test đơn lẻ không thể bao quát.

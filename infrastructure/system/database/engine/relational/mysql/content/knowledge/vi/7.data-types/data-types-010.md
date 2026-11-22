# DATE, TIME, DATETIME, TIMESTAMP và YEAR

Dữ liệu thời gian xuất hiện trong hầu hết ứng dụng: ngày sinh, ngày đặt hàng, thời điểm thanh toán, giờ mở cửa, thời lượng xử lý và năm tài chính. MySQL cung cấp các kiểu `DATE`, `TIME`, `DATETIME`, `TIMESTAMP` và `YEAR` để lưu những ý nghĩa khác nhau này. Chọn sai kiểu có thể làm lệch thời điểm khi đổi múi giờ, mất độ chính xác, giới hạn phạm vi ngày hoặc khiến truy vấn theo khoảng thời gian khó tối ưu.

Bài học thuộc module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction và kiểm soát đồng thời; đồng thời thực hành đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý các vấn đề vận hành cơ sở dữ liệu quan hệ. Trong chương **Kiểu dữ liệu**, bài này giúp phân biệt ý nghĩa của từng kiểu ngày giờ và thiết kế cách lưu thời gian phù hợp với nghiệp vụ.

## 1. Trước khi chọn kiểu thời gian, hãy xác định ý nghĩa dữ liệu

Một giá trị như `2026-05-12 09:30:00` có thể biểu diễn nhiều thứ:

- Sinh nhật của một người: chỉ cần ngày, không có giờ và múi giờ.
- Một cuộc họp lúc 09:30 tại Thành phố Hồ Chí Minh: ngày và giờ địa phương có ý nghĩa nghiệp vụ.
- Thời điểm một khoản thanh toán thực sự được ghi nhận: một thời điểm duy nhất trên dòng thời gian, cần thống nhất giữa các máy chủ và người dùng ở nhiều múi giờ.
- Thời lượng một tác vụ chạy: khoảng thời gian đã trôi qua, có thể dài hơn 24 giờ hoặc âm trong một số phép tính.
- Năm tài chính: chỉ cần thành phần năm.

Không nên chọn kiểu chỉ vì giá trị đầu vào có hình dạng giống nhau. Hãy hỏi dữ liệu đang biểu diễn **ngày lịch**, **giờ trong ngày**, **thời lượng**, **thời điểm tuyệt đối** hay **năm**.

| Ý nghĩa nghiệp vụ | Kiểu thường phù hợp | Ví dụ |
|---|---|---|
| Ngày sinh, ngày phát hành hóa đơn | `DATE` | `2026-05-12` |
| Thời lượng chạy hoặc thời gian chênh lệch | `TIME` trong giới hạn của kiểu | `27:15:00` |
| Giờ địa phương có cả ngày nhưng không tự chuyển múi giờ | `DATETIME` | `2026-05-12 09:30:00` |
| Thời điểm sự kiện cần quy đổi theo múi giờ session | `TIMESTAMP` | `2026-05-12 02:30:00` UTC |
| Năm độc lập | `YEAR` | `2026` |

`DATETIME` cũng có thể lưu một thời điểm tuyệt đối nếu ứng dụng quy ước mọi giá trị đều là UTC. Trong trường hợp đó, chính ứng dụng chịu trách nhiệm chuyển đổi trước khi ghi và sau khi đọc; MySQL không tự đổi `DATETIME` theo múi giờ session.

## 2. Tổng quan năm kiểu dữ liệu

| Kiểu | Nội dung lưu | Phạm vi chính | Độ chính xác phần giây |
|---|---|---|---|
| `DATE` | Ngày lịch: năm, tháng, ngày | `1000-01-01` đến `9999-12-31` | Không có |
| `TIME` | Giờ hoặc thời lượng, có thể âm | `-838:59:59` đến `838:59:59` | Tối đa 6 chữ số microsecond |
| `DATETIME` | Ngày và giờ lịch | `1000-01-01 00:00:00` đến `9999-12-31 23:59:59` | Tối đa 6 chữ số microsecond |
| `TIMESTAMP` | Thời điểm được lưu theo UTC và hiển thị theo múi giờ session | Xấp xỉ từ năm 1970 đến tháng 1 năm 2038 | Tối đa 6 chữ số microsecond |
| `YEAR` | Thành phần năm | `1901` đến `2155`, ngoài ra có giá trị `0000` | Không có |

Các kiểu `TIME`, `DATETIME` và `TIMESTAMP` hỗ trợ fractional seconds precision (FSP) từ 0 đến 6. Nếu không chỉ định FSP, độ chính xác mặc định là 0, tức không lưu phần lẻ giây. Với `TIMESTAMP`, giới hạn cụ thể được tính theo UTC; giá trị hiển thị có thể mang ngày giờ khác tùy múi giờ session.

Giới hạn phạm vi là một yếu tố quan trọng. `TIMESTAMP` tiện cho thời điểm sự kiện nhưng không phù hợp với ngày lịch rất xa trong quá khứ hoặc tương lai. `DATETIME` có phạm vi rộng hơn và không thực hiện chuyển đổi múi giờ ngầm.

## 3. Kiểu `DATE`: chỉ lưu ngày lịch

`DATE` lưu năm, tháng và ngày, không lưu giờ, phút, giây hoặc múi giờ. Đây là lựa chọn phù hợp cho ngày sinh, ngày ký hợp đồng, ngày đến hạn, ngày nghỉ và ngày lập hóa đơn nếu nghiệp vụ chỉ quan tâm ngày lịch.

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    birth_date  DATE,
    hire_date   DATE NOT NULL,
    PRIMARY KEY (employee_id)
);

INSERT INTO employees (full_name, birth_date, hire_date)
VALUES ('Nguyễn An', '1998-04-17', '2026-05-12');

SELECT employee_id, full_name, birth_date, hire_date
FROM employees;
```

### 3.1. Literal và định dạng

Nên truyền ngày theo dạng năm-tháng-ngày:

```sql
INSERT INTO employees (full_name, birth_date, hire_date)
VALUES ('Trần Bình', '1995-11-03', '2026-05-12');
```

Không nên lưu ngày dưới dạng `VARCHAR` như `'12/05/2026'`. Chuỗi không có quy tắc ngày tháng thống nhất dễ gây nhầm lẫn giữa ngày/tháng và tháng/ngày, khó kiểm tra tính hợp lệ, khó so sánh theo lịch và không tận dụng được các hàm thời gian.

### 3.2. Khi nào không nên dùng `DATE`?

Nếu nghiệp vụ cần phân biệt hai sự kiện xảy ra cùng ngày nhưng khác thời điểm, `DATE` làm mất thông tin. Ví dụ, ngày tạo đơn hàng thường cần giờ và phút để sắp xếp hoặc kiểm tra thời hạn thanh toán. Khi đó nên chọn `DATETIME` hoặc `TIMESTAMP` theo quy ước múi giờ.

## 4. Kiểu `TIME`: giờ hoặc thời lượng

`TIME` lưu thành phần giờ, phút, giây và có thể có phần microsecond. Điểm quan trọng là `TIME` không chỉ dùng cho giờ trong ngày; MySQL còn hỗ trợ giá trị âm và giá trị vượt quá 24 giờ. Vì vậy, kiểu này thường phù hợp với **thời lượng** hoặc khoảng chênh lệch thời gian.

Ví dụ:

```sql
CREATE TABLE job_runs (
    run_id       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    started_at   DATETIME(6) NOT NULL,
    elapsed_time TIME(6) NOT NULL,
    PRIMARY KEY (run_id)
);

INSERT INTO job_runs (started_at, elapsed_time)
VALUES ('2026-05-12 09:00:00.000000', '27:15:30.250000');
```

`27:15:30` có nghĩa là 27 giờ, 15 phút, 30 giây; nó không bị diễn giải thành 03:15:30 của ngày tiếp theo. Giá trị âm như `'-02:30:00'` cũng có thể xuất hiện trong phép tính thời gian.

Phạm vi của `TIME` là khoảng `-838:59:59` đến `838:59:59`. Đây không phải kiểu lưu mọi loại thời lượng không giới hạn. Nếu cần lưu thời lượng hàng tháng, nhiều năm hoặc số mili giây lớn, nên cân nhắc số nguyên như `BIGINT` theo đơn vị đã quy ước, hoặc một mô hình dữ liệu phù hợp hơn.

### 4.1. Giờ trong ngày và thời lượng không giống nhau

`TIME` có thể lưu giờ mở cửa như `09:00:00`, nhưng nó không chứa ngày và không mang múi giờ. Nếu lưu lịch làm việc theo tuần, có thể cần kết hợp ngày trong tuần và giờ. Nếu lưu một cuộc hẹn cụ thể, cần cả ngày và giờ, thường dùng `DATETIME` cùng thông tin múi giờ địa phương khi cần.

Không dùng `TIME` để lưu thời điểm bắt đầu/kết thúc của một sự kiện nếu cần biết sự kiện thuộc ngày nào. Hai giá trị `09:00:00` ở hai ngày khác nhau không thể phân biệt nếu chỉ lưu `TIME`.

### 4.2. Chuyển đổi giữa TIME và số giây

MySQL cung cấp `TIME_TO_SEC()` và `SEC_TO_TIME()`:

```sql
SELECT TIME_TO_SEC('02:30:00') AS duration_seconds;
-- 9000

SELECT SEC_TO_TIME(9000) AS duration_value;
-- 02:30:00
```

Khi dùng `SEC_TO_TIME()`, cần lưu ý kết quả vẫn chịu giới hạn phạm vi của kiểu `TIME`.

## 5. Kiểu `DATETIME`: ngày giờ lịch không tự đổi múi giờ

`DATETIME` lưu một giá trị ngày và giờ theo lịch. Khi ghi và đọc, MySQL không tự chuyển đổi giá trị này theo `time_zone` của session.

Ví dụ:

```sql
CREATE TABLE appointments (
    appointment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id    BIGINT UNSIGNED NOT NULL,
    scheduled_at   DATETIME(6) NOT NULL,
    PRIMARY KEY (appointment_id)
);

INSERT INTO appointments (customer_id, scheduled_at)
VALUES (101, '2026-05-12 09:30:00.123456');
```

Giá trị trên có thể biểu diễn cuộc hẹn lúc 09:30:00.123456 theo giờ địa phương mà nghiệp vụ đã chọn. Nếu người dùng ở nhiều khu vực, chỉ lưu `DATETIME` có thể chưa đủ để xác định cuộc hẹn tương ứng với thời điểm tuyệt đối nào. Khi đó, nên lưu thêm định danh múi giờ khu vực như `Asia/Ho_Chi_Minh` hoặc quy ước rõ rằng `scheduled_at` luôn là UTC.

### 5.1. Phạm vi và fractional seconds

`DATETIME` có phạm vi từ `1000-01-01 00:00:00` đến `9999-12-31 23:59:59.999999` khi dùng FSP 6. Có thể khai báo độ chính xác phần giây:

```sql
CREATE TABLE audit_events (
    event_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    occurred_at DATETIME(6) NOT NULL,
    description VARCHAR(255) NOT NULL,
    PRIMARY KEY (event_id)
);
```

Ví dụ literal:

```sql
INSERT INTO audit_events (occurred_at, description)
VALUES ('2026-05-12 09:30:00.123456', 'Đăng nhập thành công');
```

Nếu chỉ cần độ chính xác đến mili giây, `DATETIME(3)` có thể đủ. Chọn FSP theo độ chính xác mà ứng dụng thực sự cần; lưu sáu chữ số phần giây làm tăng dung lượng so với giá trị không có fractional seconds.

### 5.2. Dùng DATETIME để lưu thời điểm UTC

Một hệ thống có thể chọn lưu thời điểm tuyệt đối bằng `DATETIME(6)` nhưng quy ước tất cả giá trị trong cột là UTC. Cách này có phạm vi năm rộng hơn `TIMESTAMP`, hữu ích với dữ liệu cần lưu thời điểm trước 1970 hoặc sau 2038.

Tuy nhiên, MySQL không biết `DATETIME` đó là UTC. Nếu một session đang ở `+07:00`, `NOW()` trả về giờ session; chèn `NOW()` vào cột `DATETIME` sẽ lưu đúng giá trị giờ đó, không tự chuyển về UTC. Ứng dụng phải dùng `UTC_TIMESTAMP(6)` hoặc chuyển đổi ở tầng ứng dụng một cách nhất quán.

```sql
INSERT INTO audit_events (occurred_at, description)
VALUES (UTC_TIMESTAMP(6), 'Sự kiện được ghi theo UTC');
```

Hãy ghi rõ quy ước trong tên cột hoặc tài liệu schema, ví dụ `created_at_utc`, nếu điều đó giúp người bảo trì tránh hiểu nhầm.

## 6. Kiểu `TIMESTAMP`: lưu thời điểm và chuyển đổi theo session

`TIMESTAMP` được thiết kế cho một thời điểm trên dòng thời gian. Khi ghi, MySQL chuyển giá trị từ múi giờ session sang UTC để lưu; khi đọc, MySQL chuyển từ UTC về múi giờ session hiện tại. Vì vậy, hai session có `time_zone` khác nhau có thể nhìn cùng một bản ghi `TIMESTAMP` với giờ hiển thị khác nhau, nhưng thời điểm thực tế là một.

Ví dụ:

```sql
CREATE TABLE payment_events (
    payment_event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    paid_at           TIMESTAMP(6) NOT NULL,
    amount            DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (payment_event_id)
);

SET SESSION time_zone = '+00:00';

INSERT INTO payment_events (paid_at, amount)
VALUES ('2026-05-12 02:30:00.123456', 125000.00);

SELECT paid_at FROM payment_events;

SET SESSION time_zone = '+07:00';

SELECT paid_at FROM payment_events;
```

Session UTC hiển thị `02:30:00.123456`; session `+07:00` hiển thị `09:30:00.123456`. Hai giá trị biểu diễn cùng một thời điểm.

### 6.1. Phạm vi TIMESTAMP

Trong MySQL hiện hành, phạm vi `TIMESTAMP` xấp xỉ từ `1970-01-01 00:00:01` UTC đến `2038-01-19 03:14:07` UTC. Đây là giới hạn quan trọng khi lưu dữ liệu lịch sử hoặc sự kiện có thể xảy ra trong tương lai xa.

Nếu nghiệp vụ cần lưu ngày sinh từ trước năm 1970, lịch sử hàng trăm năm hoặc lịch đặt trước năm 2040, `TIMESTAMP` có thể không phù hợp. `DATE` hoặc `DATETIME` thường thích hợp hơn tùy ý nghĩa dữ liệu.

### 6.2. Mặc định và tự cập nhật

`TIMESTAMP` thường được dùng cho cột tạo và cập nhật bản ghi. MySQL hỗ trợ `DEFAULT CURRENT_TIMESTAMP` và `ON UPDATE CURRENT_TIMESTAMP`; có thể chỉ định FSP tương ứng:

```sql
CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_id)
);
```

- Khi chèn hàng và không chỉ định `created_at`, MySQL gán thời điểm hiện tại.
- Khi cập nhật hàng và có thay đổi giá trị cột khác, `updated_at` tự được cập nhật theo định nghĩa.
- Có thể truyền giá trị tường minh nếu nghiệp vụ yêu cầu, miễn là kiểu và quyền cho phép.

`CURRENT_TIMESTAMP` là biểu thức thời gian hiện tại theo múi giờ session. Vì `TIMESTAMP` chuyển đổi theo session, hãy cấu hình session của ứng dụng thống nhất, thường là UTC, để giảm nhầm lẫn khi đọc và ghi.

### 6.3. TIMESTAMP và DATETIME khác nhau ở đâu?

| Tiêu chí | `TIMESTAMP` | `DATETIME` |
|---|---|---|
| Chuyển đổi theo session time zone | Có, chuyển UTC khi lưu và chuyển về session khi đọc | Không |
| Phạm vi năm | Xấp xỉ 1970–2038 | 1000–9999 |
| Lưu ngày giờ lịch | Có | Có |
| Phù hợp với thời điểm tuyệt đối | Có, nếu cấu hình timezone đúng | Có nếu ứng dụng quy ước và tự quản lý UTC |
| Phù hợp với giờ địa phương không quy đổi | Không phải lựa chọn tự nhiên | Có |
| Tự động gán thời điểm hiện tại | Hỗ trợ `DEFAULT CURRENT_TIMESTAMP` | Hỗ trợ `DEFAULT CURRENT_TIMESTAMP` trên MySQL hiện đại |

Không có quy tắc “luôn dùng TIMESTAMP” hoặc “luôn dùng DATETIME”. Hãy chọn dựa trên phạm vi thời gian, ý nghĩa múi giờ, độ chính xác và cách ứng dụng xử lý giá trị.

## 7. Kiểu `YEAR`: chỉ lưu năm

`YEAR` lưu một thành phần năm, không lưu tháng, ngày hoặc giờ. Phạm vi hợp lệ là `1901` đến `2155`, cùng giá trị `0000`.

Ví dụ:

```sql
CREATE TABLE fiscal_reports (
    report_id   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    fiscal_year YEAR NOT NULL,
    report_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (report_id),
    UNIQUE KEY uq_fiscal_report_year_name (fiscal_year, report_name)
);

INSERT INTO fiscal_reports (fiscal_year, report_name)
VALUES (2026, 'Báo cáo doanh thu');
```

Nên nhập năm bằng bốn chữ số hoặc số nguyên bốn chữ số. Tránh dạng năm hai chữ số vì quy tắc diễn giải thế kỷ dễ gây nhầm lẫn và không phù hợp với dữ liệu mới. `YEAR(2)` đã bị loại bỏ khỏi MySQL; không dựa vào display width cũ.

Nếu nghiệp vụ cần năm ngoài phạm vi của `YEAR`, chẳng hạn năm lịch sử trước 1901 hoặc năm dự báo sau 2155, hãy dùng kiểu số nguyên như `SMALLINT` hoặc `INT` cùng constraint/validation phù hợp. Không dùng `YEAR` chỉ vì cột có tên `year`.

Giá trị `0000` có ý nghĩa đặc biệt trong MySQL và thường không phải năm lịch hợp lệ của nghiệp vụ. Không nên dùng nó như sentinel cho “chưa biết” nếu có thể biểu diễn trạng thái đó bằng `NULL` hoặc một cột trạng thái riêng.

## 8. Fractional seconds precision

`TIME`, `DATETIME` và `TIMESTAMP` hỗ trợ FSP từ 0 đến 6:

| Khai báo | Độ chính xác | Ví dụ |
|---|---|---|
| `TIME` | Mặc định 0 | `12:30:45` |
| `TIME(3)` | Mili giây | `12:30:45.123` |
| `DATETIME(6)` | Micro giây | `2026-05-12 12:30:45.123456` |
| `TIMESTAMP(3)` | Mili giây | `2026-05-12 12:30:45.123` |

Ví dụ truy vấn:

```sql
SELECT
    CURRENT_TIMESTAMP(6) AS now_with_microseconds,
    UTC_TIMESTAMP(6) AS utc_with_microseconds,
    NOW(3) AS now_with_milliseconds;
```

Khi ghi một giá trị có nhiều chữ số phần giây hơn FSP của column, MySQL có thể làm tròn hoặc cắt phần dư theo quy tắc và SQL mode liên quan. SQL mode `TIME_TRUNCATE_FRACTIONAL` yêu cầu cắt phần dư thay vì làm tròn. Nếu ứng dụng cần so khớp timestamp chính xác giữa nhiều hệ thống, hãy thống nhất FSP và cách xử lý phần lẻ giây ở cả driver lẫn schema.

Không nên chọn FSP 6 theo thói quen nếu nguồn dữ liệu chỉ có độ chính xác đến giây. Độ chính xác cao hơn không tự làm đồng hồ hệ thống chính xác hơn; nó chỉ lưu được phần phân số mà nguồn cung cấp.

## 9. Múi giờ và các hàm thời gian

### 9.1. NOW(), CURRENT_TIMESTAMP và UTC_TIMESTAMP

Một số hàm quan trọng:

| Hàm | Kết quả |
|---|---|
| `NOW()` / `CURRENT_TIMESTAMP` | Thời điểm hiện tại theo múi giờ session. |
| `UTC_TIMESTAMP()` | Thời điểm hiện tại theo UTC. |
| `CURDATE()` / `CURRENT_DATE` | Ngày hiện tại theo múi giờ session. |
| `CURTIME()` / `CURRENT_TIME` | Giờ hiện tại theo múi giờ session. |
| `DATE(expr)` | Lấy phần ngày từ biểu thức ngày giờ. |
| `TIME(expr)` | Lấy phần giờ từ biểu thức ngày giờ. |

Kiểm tra nhanh:

```sql
SELECT
    @@session.time_zone AS session_zone,
    NOW(6) AS session_now,
    UTC_TIMESTAMP(6) AS utc_now,
    CURDATE() AS session_date,
    CURTIME(6) AS session_time;
```

Nếu `@@session.time_zone` là `'+07:00'`, `NOW()` hiển thị giờ UTC cộng bảy tiếng. `UTC_TIMESTAMP()` vẫn trả về UTC.

### 9.2. Chuyển đổi múi giờ

`CONVERT_TZ()` chuyển một giá trị ngày giờ từ múi giờ này sang múi giờ khác:

```sql
SELECT CONVERT_TZ(
    '2026-05-12 02:30:00',
    '+00:00',
    '+07:00'
) AS vietnam_local_time;
```

Kết quả là `2026-05-12 09:30:00`. Có thể dùng tên múi giờ như `'UTC'` và `'Asia/Ho_Chi_Minh'`, nhưng MySQL phải có các bảng time zone được nạp và cập nhật. Nếu bảng chưa có dữ liệu, `CONVERT_TZ()` với tên khu vực có thể trả về `NULL`.

Offset như `'+07:00'` đơn giản nhưng không mô tả quy tắc lịch sử của một khu vực. Tên múi giờ IANA phù hợp hơn khi cần tính đúng quy tắc theo từng giai đoạn. Việt Nam hiện dùng UTC+7, nhưng với dữ liệu đa quốc gia, không nên tự giả định mọi khu vực luôn có offset cố định.

### 9.3. Cộng, trừ và tính khoảng thời gian

MySQL có các hàm xử lý thời gian:

```sql
SELECT DATE_ADD('2026-05-12', INTERVAL 7 DAY) AS next_week;

SELECT DATE_SUB('2026-05-12 09:30:00', INTERVAL 2 HOUR) AS two_hours_before;

SELECT DATEDIFF('2026-05-20', '2026-05-12') AS day_difference;

SELECT TIMESTAMPDIFF(
    MINUTE,
    '2026-05-12 09:00:00',
    '2026-05-12 10:45:00'
) AS elapsed_minutes;
```

- `DATE_ADD()` và `DATE_SUB()` cộng/trừ một interval.
- `DATEDIFF()` lấy phần ngày và trả về số ngày chênh lệch; phần giờ bị bỏ qua.
- `TIMESTAMPDIFF(unit, start, end)` trả về chênh lệch theo đơn vị được chỉ định.
- `EXTRACT()` lấy một thành phần như năm, tháng, ngày hoặc giờ.

Ví dụ lấy năm và tháng:

```sql
SELECT
    EXTRACT(YEAR FROM paid_at) AS paid_year,
    EXTRACT(MONTH FROM paid_at) AS paid_month
FROM payment_events;
```

### 9.4. Định dạng để hiển thị

`DATE_FORMAT()` và `TIME_FORMAT()` chuyển giá trị thời gian thành chuỗi để hiển thị:

```sql
SELECT DATE_FORMAT(
    '2026-05-12 09:30:45.123456',
    '%d/%m/%Y %H:%i:%s.%f'
) AS display_value;
```

Một số ký hiệu thường gặp:

| Ký hiệu | Ý nghĩa |
|---|---|
| `%Y` | Năm bốn chữ số |
| `%m` | Tháng hai chữ số |
| `%d` | Ngày trong tháng |
| `%H` | Giờ 00–23 |
| `%i` | Phút |
| `%s` | Giây |
| `%f` | Microsecond |

Chỉ định dạng thành chuỗi ở lớp hiển thị hoặc khi cần xuất báo cáo. Không nên lưu kết quả `DATE_FORMAT()` trở lại column kiểu chuỗi nếu dữ liệu vẫn mang ý nghĩa ngày giờ.

## 10. Tự động gán thời gian tạo và cập nhật

Với các cột thời gian tạo/cập nhật bản ghi, có thể dùng `DEFAULT CURRENT_TIMESTAMP` và `ON UPDATE CURRENT_TIMESTAMP`:

```sql
CREATE TABLE articles (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title      VARCHAR(200) NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                  ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (article_id)
);
```

MySQL hiện đại hỗ trợ các thuộc tính tự khởi tạo và tự cập nhật cho cả `TIMESTAMP` và `DATETIME`. FSP của biểu thức `CURRENT_TIMESTAMP(fsp)` nên khớp với FSP của column.

Một số lưu ý:

- `DEFAULT CURRENT_TIMESTAMP` áp dụng khi `INSERT` không cung cấp giá trị cho cột.
- `ON UPDATE CURRENT_TIMESTAMP` cập nhật cột khi hàng có thay đổi ở cột khác theo điều kiện của MySQL.
- Nếu ứng dụng tự gán `updated_at`, hãy xác định rõ có muốn giữ cơ chế `ON UPDATE` hay không để tránh hai nơi cùng điều khiển thời gian.
- `CURRENT_TIMESTAMP` theo session time zone. Với `DATETIME`, giá trị được lưu nguyên như biểu thức trả về; với `TIMESTAMP`, giá trị được quy đổi sang UTC khi lưu.

Nếu cần lưu lịch sử mọi lần thay đổi, một cột `updated_at` duy nhất là chưa đủ. Hãy dùng bảng audit hoặc event riêng để lưu từng sự kiện.

## 11. Truy vấn theo thời gian và sử dụng index

### 11.1. Ưu tiên truy vấn theo khoảng nửa mở

Giả sử cần lấy tất cả đơn hàng trong ngày 12/05/2026. Với cột `created_at` là `DATETIME` hoặc `TIMESTAMP`, cách viết khoảng nửa mở thường rõ ràng và thân thiện với index:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at >= '2026-05-12 00:00:00'
  AND created_at <  '2026-05-13 00:00:00';
```

Khoảng `>= đầu ngày` và `< đầu ngày kế tiếp` bao gồm mọi giá trị trong ngày, kể cả phần microsecond cuối ngày. Nó cũng tránh phải tự tạo giá trị `23:59:59.999999`.

### 11.2. Tránh bọc cột được lập chỉ mục bằng hàm nếu không cần

Nếu có index trên `created_at`, điều kiện sau có thể khiến MySQL khó dùng index range thông thường vì phải áp dụng hàm lên từng giá trị cột:

```sql
-- Thường kém thuận lợi cho index trên created_at:
SELECT order_id
FROM orders
WHERE DATE(created_at) = '2026-05-12';
```

Viết thành khoảng thời gian:

```sql
SELECT order_id
FROM orders
WHERE created_at >= '2026-05-12 00:00:00'
  AND created_at <  '2026-05-13 00:00:00';
```

Sau đó dùng `EXPLAIN` để xác nhận kế hoạch thực tế. Nếu nghiệp vụ thường xuyên lọc theo ngày được suy ra từ timestamp, có thể cân nhắc generated column hoặc functional index phù hợp với phiên bản và tải truy vấn.

### 11.3. Cẩn thận với ranh giới ngày và múi giờ

Nếu `created_at` là `TIMESTAMP`, literal trong điều kiện được diễn giải theo múi giờ session rồi quy đổi theo cơ chế của kiểu. Nếu cần lấy “ngày 12/05 tại Việt Nam”, hãy xác định hai mốc đầu ngày và đầu ngày kế tiếp trong `Asia/Ho_Chi_Minh`, sau đó chuyển về UTC hoặc dùng session được đặt đúng múi giờ. Không nên lấy mốc UTC nửa đêm nếu nghiệp vụ đang hỏi ngày địa phương UTC+7.

Ví dụ chuyển hai mốc giờ Việt Nam sang UTC:

```sql
SELECT
    CONVERT_TZ('2026-05-12 00:00:00', 'Asia/Ho_Chi_Minh', '+00:00') AS start_utc,
    CONVERT_TZ('2026-05-13 00:00:00', 'Asia/Ho_Chi_Minh', '+00:00') AS end_utc;
```

Kết quả sẽ là hai mốc UTC cách nhau một ngày đối với khu vực không có chuyển đổi giờ mùa hè trong khoảng này. Với các khu vực có DST, khoảng giữa hai mốc địa phương liên tiếp có thể không đúng 24 giờ; dùng tên múi giờ khu vực và dữ liệu time zone cập nhật.

## 12. Ngày giờ không hợp lệ và SQL mode

MySQL kiểm tra giá trị ngày giờ theo kiểu dữ liệu và SQL mode. Các giá trị như tháng 13, ngày không tồn tại hoặc zero date có thể bị từ chối, tạo warning hoặc được xử lý theo quy tắc mode và phiên bản.

Không nên dựa vào các giá trị như `'0000-00-00'` hoặc `'2026-00-15'` để biểu diễn “chưa biết”. Hãy dùng `NULL` nếu dữ liệu thực sự chưa có, hoặc dùng trạng thái riêng nếu nghiệp vụ cần phân biệt nhiều tình huống.

Kiểm tra SQL mode:

```sql
SELECT @@SESSION.sql_mode;
```

Strict mode giúp từ chối nhiều giá trị sai thay vì âm thầm điều chỉnh. Các mode liên quan zero date như `NO_ZERO_DATE` và `NO_ZERO_IN_DATE` có lịch sử thay đổi/deprecation giữa các phiên bản MySQL; không nên dựa riêng vào tên mode để bảo đảm dữ liệu hợp lệ. Hãy xác minh hành vi trên phiên bản mục tiêu và dùng strict mode cùng kiểm tra đầu vào ở ứng dụng.

Khi migration dữ liệu cũ, cần thống kê và làm sạch ngày giờ không hợp lệ trước khi bật cấu hình nghiêm ngặt. Không chuyển mọi giá trị lỗi thành ngày mặc định vì điều đó có thể làm sai lịch sử nghiệp vụ.

## 13. Chọn kiểu nào cho tình huống nào?

| Tình huống | Gợi ý | Lý do |
|---|---|---|
| Ngày sinh khách hàng | `DATE` | Không có ý nghĩa giờ hoặc múi giờ. |
| Ngày hết hạn hợp đồng | `DATE` | Nghiệp vụ thường xác định theo ngày lịch. |
| Giờ mở cửa hàng ngày | `TIME` | Giờ trong ngày lặp lại, không gắn một ngày cụ thể. |
| Thời lượng chạy job 27 giờ | `TIME` nếu nằm trong phạm vi; nếu lớn hơn, dùng số nguyên theo đơn vị rõ ràng | `TIME` cho phép vượt 24 giờ nhưng có giới hạn khoảng 838 giờ. |
| Cuộc hẹn 09:30 tại một địa điểm | `DATETIME` cùng múi giờ khu vực | Giữ nguyên giờ lịch địa phương. |
| Thời điểm thanh toán hoặc log sự kiện | `TIMESTAMP` hoặc `DATETIME(6)` quy ước UTC | Cần một thời điểm tuyệt đối nhất quán. |
| Sự kiện có thể nằm ngoài phạm vi 1970–2038 | `DATETIME(6)` theo quy ước UTC hoặc mô hình phù hợp | Tránh giới hạn phạm vi của `TIMESTAMP`. |
| Năm tài chính | `YEAR` nếu nằm trong phạm vi; nếu không dùng số nguyên | Chỉ cần lưu năm. |

Trước khi chốt schema, hãy ghi rõ quy ước trong tài liệu: kiểu nào là UTC, kiểu nào là local time, session time zone được đặt ra sao và tầng nào thực hiện chuyển đổi.

## 14. Ví dụ thiết kế bảng kết hợp

Một hệ thống bán hàng có thể dùng nhiều kiểu thời gian theo ý nghĩa riêng:

```sql
CREATE TABLE customer_profiles (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name   VARCHAR(150) NOT NULL,
    birth_date  DATE,
    PRIMARY KEY (customer_id)
);

CREATE TABLE store_hours (
    store_id   BIGINT UNSIGNED NOT NULL,
    day_of_week TINYINT UNSIGNED NOT NULL,
    opens_at   TIME NOT NULL,
    closes_at  TIME NOT NULL,
    PRIMARY KEY (store_id, day_of_week)
);

CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (customer_id, created_at)
);

CREATE TABLE appointments (
    appointment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id    BIGINT UNSIGNED NOT NULL,
    local_start    DATETIME(6) NOT NULL,
    time_zone_name VARCHAR(64) NOT NULL,
    PRIMARY KEY (appointment_id)
);

CREATE TABLE fiscal_year_targets (
    fiscal_year YEAR NOT NULL,
    target_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (fiscal_year)
);
```

Trong schema trên:

- `birth_date` chỉ lưu ngày sinh.
- `opens_at` và `closes_at` là giờ lịch trong ngày.
- `created_at` và `updated_at` là thời điểm sự kiện được MySQL quản lý theo session time zone.
- `local_start` giữ ngày giờ địa phương; `time_zone_name` xác định khu vực mà giờ đó thuộc về.
- `fiscal_year` chỉ lưu năm.

Đây là ví dụ minh họa các kiểu dữ liệu, chưa phải schema sản xuất hoàn chỉnh. Một hệ thống thật cần thêm khóa ngoại, constraint cho `day_of_week`, kiểm tra giờ mở/đóng cửa, quy tắc xử lý qua đêm và chính sách cập nhật lịch hẹn.

## 15. Bài tập thực hành

### Bài tập 1: Phân loại ý nghĩa dữ liệu

Một ứng dụng quản lý nhân sự cần lưu ngày sinh, ngày bắt đầu làm việc, thời điểm nhân viên chấm công và thời lượng làm thêm.

**Yêu cầu:** chọn kiểu dữ liệu cho từng thuộc tính và giải thích vì sao không thể dùng một kiểu duy nhất cho tất cả.

### Bài tập 2: So sánh DATETIME và TIMESTAMP

Tạo bảng tạm có hai cột `DATETIME` và `TIMESTAMP`. Chèn cùng một literal khi session ở UTC, đổi session sang `+07:00` rồi đọc lại.

**Yêu cầu:** ghi lại giá trị của hai cột và giải thích cột nào thay đổi cách hiển thị.

### Bài tập 3: Fractional seconds

Tạo ba cột `DATETIME`, `DATETIME(3)` và `DATETIME(6)`. Chèn cùng một literal có sáu chữ số phần giây.

**Yêu cầu:** so sánh dữ liệu đọc lại và giải thích FSP ảnh hưởng đến độ chính xác lưu trữ thế nào.

### Bài tập 4: Tìm đơn hàng trong một ngày

Tạo index trên `orders.created_at`. Viết truy vấn lấy mọi đơn hàng trong ngày 12/05/2026 bằng khoảng nửa mở, sau đó so sánh với truy vấn dùng `DATE(created_at)`.

**Yêu cầu:** chạy `EXPLAIN` và giải thích khác biệt kế hoạch truy cập nếu có.

### Bài tập 5: Chuyển giờ địa phương sang UTC

Dùng `CONVERT_TZ()` chuyển `2026-05-12 09:30:00` từ `Asia/Ho_Chi_Minh` sang UTC.

**Yêu cầu:** kiểm tra bảng time zone của MySQL đã được nạp chưa và giải thích kết quả nếu hàm trả về `NULL`.

### Bài tập 6: Thiết kế thời gian cho lịch hẹn

Một ứng dụng đặt lịch phục vụ người dùng ở nhiều quốc gia. Người dùng chọn 09:00 ngày 12/05 tại múi giờ địa phương của họ.

**Yêu cầu:** đề xuất các cột cần lưu để giữ được giờ địa phương, múi giờ khu vực và thời điểm tuyệt đối; giải thích vì sao chỉ lưu `DATETIME` là chưa đủ nếu không có quy ước timezone.

## 16. Checklist trước khi tạo cột ngày giờ

- [ ] Xác định dữ liệu là ngày lịch, giờ trong ngày, thời lượng hay thời điểm tuyệt đối.
- [ ] Chọn `DATE`, `TIME`, `DATETIME`, `TIMESTAMP` hoặc `YEAR` theo đúng ý nghĩa.
- [ ] Kiểm tra giới hạn phạm vi của kiểu, đặc biệt giới hạn 2038 của `TIMESTAMP`.
- [ ] Chọn FSP 0–6 theo độ chính xác nguồn dữ liệu.
- [ ] Quy định UTC hay giờ địa phương cho từng cột có thành phần thời gian.
- [ ] Nếu lưu giờ địa phương, xác định có cần lưu tên múi giờ IANA hay không.
- [ ] Không dùng zero date hoặc chuỗi định dạng để biểu diễn dữ liệu chưa biết.
- [ ] Dùng `DEFAULT CURRENT_TIMESTAMP` và `ON UPDATE` có chủ đích.
- [ ] Truy vấn khoảng thời gian bằng điều kiện nửa mở khi phù hợp.
- [ ] Kiểm tra index và kế hoạch thực thi bằng `EXPLAIN`.
- [ ] Thống nhất cách chuyển đổi giữa MySQL, JDBC và ứng dụng.

## 17. Ghi nhớ

`DATE` dành cho ngày lịch; `TIME` biểu diễn giờ hoặc thời lượng trong một phạm vi hữu hạn; `DATETIME` giữ ngày giờ lịch mà không tự chuyển múi giờ; `TIMESTAMP` biểu diễn thời điểm được chuyển đổi qua UTC theo session; `YEAR` chỉ lưu năm. `TIME`, `DATETIME` và `TIMESTAMP` hỗ trợ tối đa sáu chữ số phần giây.

Thiết kế thời gian tốt bắt đầu từ ý nghĩa nghiệp vụ và quy ước timezone. Hãy thống nhất UTC cho thời điểm tuyệt đối, lưu tên múi giờ khi cần giữ giờ địa phương, chọn FSP phù hợp và truy vấn theo khoảng thời gian rõ ràng. Những quyết định này giúp dữ liệu chính xác, dễ đối chiếu và có thể tối ưu bằng index.

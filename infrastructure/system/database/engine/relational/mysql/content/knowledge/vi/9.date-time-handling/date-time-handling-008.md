# DATE_FORMAT, STR_TO_DATE và định dạng đầu vào tường minh

Ngày giờ thường đi qua nhiều định dạng khác nhau: người dùng nhập `19/11/2026`, API gửi `2026-11-19`, MySQL lưu một giá trị `DATE` hoặc `DATETIME`, còn báo cáo cần hiển thị `19 tháng 11 năm 2026`. Nếu không quy định rõ định dạng ở từng ranh giới, chuỗi ngày tháng có thể bị hiểu nhầm ngày với tháng, mất phần giây lẻ hoặc lệch thời gian do múi giờ.

MySQL cung cấp hai hàm thường dùng cho công việc này. `DATE_FORMAT()` định dạng một giá trị ngày giờ thành chuỗi để hiển thị hoặc xuất dữ liệu. `STR_TO_DATE()` phân tích một chuỗi theo format chỉ định và trả về giá trị kiểu ngày giờ. Hai hàm có hướng chuyển đổi ngược nhau, nhưng không thay thế việc thiết kế cột temporal đúng kiểu và kiểm tra dữ liệu đầu vào.

Bài học này thuộc module `DATABASE_MYSQL`, tập trung vào thiết kế và xử lý dữ liệu ngày giờ trong truy vấn, ứng dụng, báo cáo và vận hành. Mục tiêu là dùng format tường minh, tránh phụ thuộc định dạng mặc định của session hoặc ngôn ngữ máy chủ, đồng thời giữ khả năng lọc theo khoảng thời gian và sử dụng index.

Sau bài học, bạn có thể:

- Phân biệt định dạng đầu ra bằng `DATE_FORMAT()` và phân tích đầu vào bằng `STR_TO_DATE()`.
- Chọn format string đúng cho năm, tháng, ngày, giờ, phút, giây và microsecond.
- Xử lý chuỗi ngày tháng mơ hồ bằng format đầu vào tường minh.
- Hiểu ảnh hưởng của locale, hai chữ số năm và định dạng tuần.
- Phát hiện dữ liệu sai định dạng, ngày không hợp lệ và ký tự thừa.
- Xử lý múi giờ đúng với `TIMESTAMP`, `DATETIME` và `CONVERT_TZ()`.
- Viết điều kiện lọc ngày giờ giữ khả năng sử dụng index.
- Chọn đúng vị trí chuyển đổi giữa MySQL, JDBC và Java.

## 1. Hai hàm có hai mục đích khác nhau

| Hàm | Hướng chuyển đổi | Kiểu trả về | Dùng khi |
| --- | --- | --- | --- |
| `DATE_FORMAT(date, format)` | Giá trị ngày giờ → chuỗi | Chuỗi | Hiển thị, báo cáo, xuất CSV hoặc tạo nhãn |
| `STR_TO_DATE(str, format)` | Chuỗi → giá trị ngày giờ | `DATE`, `TIME` hoặc `DATETIME` tùy format | Nhập dữ liệu văn bản theo định dạng đã biết |

Ví dụ:

```sql
SELECT DATE_FORMAT(DATE '2026-11-19', '%d/%m/%Y') AS display_date;
-- Kết quả: 19/11/2026

SELECT STR_TO_DATE('19/11/2026', '%d/%m/%Y') AS parsed_date;
-- Kết quả: 2026-11-19
```

`DATE_FORMAT()` trả chuỗi, vì vậy sau khi format bạn không còn làm việc với một giá trị `DATE` thuần túy trong biểu thức đó. `STR_TO_DATE()` tạo giá trị temporal để MySQL có thể so sánh, sắp xếp và tính toán ngày giờ.

Trong ứng dụng, nếu dữ liệu đã có kiểu Java như `LocalDate`, `LocalDateTime` hoặc `Instant`, hãy truyền bằng JDBC với kiểu tương ứng. Chỉ dùng `STR_TO_DATE()` khi đầu vào thực sự là chuỗi văn bản cần phân tích.

## 2. Cú pháp cơ bản

### 2.1. DATE_FORMAT()

Cú pháp:

```sql
DATE_FORMAT(date_value, format_string)
```

Ví dụ với `DATETIME`:

```sql
SELECT DATE_FORMAT(
    '2026-11-19 14:35:08',
    '%Y-%m-%d %H:%i:%s'
) AS formatted_value;
```

Kết quả là chuỗi `2026-11-19 14:35:08`. Các thành phần format được thay bằng phần tương ứng của giá trị ngày giờ.

### 2.2. STR_TO_DATE()

Cú pháp:

```sql
STR_TO_DATE(date_string, format_string)
```

Ví dụ với định dạng ngày Việt Nam dạng ngày/tháng/năm:

```sql
SELECT STR_TO_DATE('19/11/2026', '%d/%m/%Y') AS parsed_value;
```

Kết quả là giá trị ngày `2026-11-19`. Format phải mô tả đúng thứ tự và cách viết của chuỗi đầu vào. Chuỗi `05/09/2026` không tự nói rõ `05` là ngày hay tháng; chỉ format do hợp đồng dữ liệu quy định mới làm rõ điều đó.

### 2.3. Kiểu trả về của STR_TO_DATE()

MySQL xác định kiểu kết quả dựa trên các thành phần trong format:

- Có thành phần ngày nhưng không có thành phần giờ: kết quả dạng `DATE`.
- Có thành phần giờ nhưng không có thành phần ngày: kết quả dạng `TIME`.
- Có cả thành phần ngày và giờ: kết quả dạng `DATETIME`.

Những phần không được chỉ định trong format có thể được đặt về 0. Vì vậy, không dùng format chỉ có `%m/%d` để tạo ngày nghiệp vụ hoàn chỉnh nếu năm là thành phần bắt buộc. Hãy xác định rõ các phần cần thiết và xác thực đầu vào.

## 3. Các format specifier thường dùng

Format string của MySQL sử dụng ký hiệu `%` theo sau bởi một ký tự. Các ký hiệu này có ý nghĩa cụ thể; chúng không giống hoàn toàn với `DateTimeFormatter` của Java.

### 3.1. Năm, tháng và ngày

| Specifier | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `%Y` | Năm 4 chữ số | `2026` |
| `%y` | Năm 2 chữ số | `26` |
| `%m` | Tháng 2 chữ số (`00`–`12`) | `11` |
| `%c` | Tháng dạng số không đệm số 0 | `11` |
| `%M` | Tên tháng đầy đủ theo locale | `November` |
| `%b` | Tên tháng viết tắt theo locale | `Nov` |
| `%d` | Ngày trong tháng 2 chữ số (`00`–`31`) | `09` |
| `%e` | Ngày trong tháng không đệm số 0 | `9` |
| `%D` | Ngày kèm hậu tố tiếng Anh | `9th` |
| `%j` | Ngày thứ bao nhiêu trong năm (`001`–`366`) | `323` |

### 3.2. Giờ, phút, giây và phần lẻ

| Specifier | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `%H` | Giờ 24 giờ, 2 chữ số (`00`–`23`) | `14` |
| `%k` | Giờ 24 giờ, không đệm số 0 | `14` |
| `%h`, `%I` | Giờ 12 giờ (`01`–`12`) | `02` |
| `%l` | Giờ 12 giờ, không đệm số 0 | `2` |
| `%i` | Phút (`00`–`59`) | `35` |
| `%s`, `%S` | Giây (`00`–`59`) | `08` |
| `%f` | Microsecond, 6 chữ số | `123456` |
| `%p` | Ký hiệu AM hoặc PM | `PM` |
| `%r` | Giờ 12 giờ dạng `hh:mm:ss AM/PM` | `02:35:08 PM` |
| `%T` | Giờ 24 giờ dạng `hh:mm:ss` | `14:35:08` |

Ví dụ có phần microsecond:

```sql
SELECT DATE_FORMAT(
    '2026-11-19 14:35:08.123456',
    '%Y-%m-%d %H:%i:%s.%f'
) AS value_with_microseconds;
```

Với cột `DATETIME(3)` hoặc `TIMESTAMP(3)`, độ chính xác phần giây lẻ là millisecond. `%f` biểu diễn phần microsecond với 6 chữ số; giá trị có độ chính xác thấp hơn được thể hiện với các chữ số còn lại bằng 0.

### 3.3. Thứ trong tuần và tuần trong năm

| Specifier | Ý nghĩa |
| --- | --- |
| `%a` | Tên thứ viết tắt theo locale |
| `%W` | Tên thứ đầy đủ theo locale |
| `%w` | Số thứ trong tuần: Chủ nhật = 0 đến Thứ bảy = 6 |
| `%U` | Tuần trong năm (`00`–`53`), tuần bắt đầu Chủ nhật |
| `%u` | Tuần trong năm (`00`–`53`), tuần bắt đầu Thứ hai |
| `%V` | Tuần (`01`–`53`), tuần bắt đầu Chủ nhật; dùng cùng `%X` |
| `%X` | Năm gắn với tuần bắt đầu Chủ nhật; dùng cùng `%V` |
| `%v` | Tuần (`01`–`53`), tuần bắt đầu Thứ hai; dùng cùng `%x` |
| `%x` | Năm gắn với tuần bắt đầu Thứ hai; dùng cùng `%v` |

Không nhầm năm lịch `%Y` với năm theo tuần `%X` hoặc `%x`. Một ngày ở đầu tháng 1 có thể thuộc tuần cuối của năm tuần trước; một ngày cuối tháng 12 có thể thuộc tuần đầu của năm tuần tiếp theo. Khi báo cáo theo tuần ISO hoặc quy ước tuần nghiệp vụ, hãy chọn cặp specifier phù hợp và kiểm thử ở ranh giới năm.

### 3.4. Ký tự đặc biệt và ký tự phần trăm

Ký tự không phải specifier trong format thường được giữ nguyên như dấu phân cách:

```sql
SELECT DATE_FORMAT(NOW(), '%d/%m/%Y lúc %H:%i:%s');
```

Muốn hiển thị dấu phần trăm `%` theo nghĩa đen, dùng `%%`:

```sql
SELECT DATE_FORMAT(NOW(), 'Đã xử lý 100%% vào %d/%m/%Y');
```

Không sao chép format của Java vào MySQL mà không chuyển đổi specifier. Ví dụ Java dùng `yyyy-MM-dd`, trong khi MySQL dùng `%Y-%m-%d`.

## 4. Locale và tên tháng/thứ

Các specifier `%M`, `%b`, `%W` và `%a` phụ thuộc locale `lc_time_names` của session. Kiểm tra giá trị hiện tại:

```sql
SELECT @@session.lc_time_names;
```

Có thể đổi locale cho session nếu máy chủ hỗ trợ:

```sql
SET lc_time_names = 'en_US';
SELECT DATE_FORMAT('2026-11-19', '%W, %d %M %Y');
```

Locale khác nhau có thể trả về tên tháng và thứ khác nhau. Danh sách locale hỗ trợ phụ thuộc bản cài đặt MySQL; kiểm tra tài liệu và giá trị hợp lệ trên môi trường triển khai. Đừng giả định locale mặc định của máy chủ là tiếng Việt hoặc giống locale của ứng dụng.

Với dữ liệu nhập có tên tháng, `STR_TO_DATE()` cũng cần format và locale phù hợp. Ví dụ chuỗi `19 November 2026` cần format `%d %M %Y` và locale nhận diện từ `lc_time_names`. Nếu hệ thống nhận dữ liệu từ nhiều nguồn hoặc nhiều ngôn ngữ, ưu tiên đầu vào số theo chuẩn ISO để tránh phụ thuộc locale.

## 5. Định dạng đầu vào tường minh

### 5.1. Không dựa vào thứ tự ngày/tháng mặc định

Các chuỗi sau đều có thể gây hiểu nhầm nếu không có format:

| Chuỗi | Có thể bị hiểu nhầm |
| --- | --- |
| `05/09/2026` | Ngày 5 tháng 9 hay ngày 9 tháng 5 |
| `03-04-26` | Ngày/tháng/năm hay tháng/ngày/năm; năm 2 chữ số còn có quy tắc ánh xạ |
| `11/12/2026` | Ngày 11 tháng 12 hay tháng 11 ngày 12 |

Luôn quy định format từ hợp đồng API, file import hoặc giao diện người dùng. Không đoán format dựa trên giá trị đầu tiên hoặc locale của máy chạy ứng dụng.

### 5.2. Ví dụ cho các định dạng phổ biến

| Đầu vào | Format tường minh | Kết quả mong đợi |
| --- | --- | --- |
| `2026-11-19` | `%Y-%m-%d` | `2026-11-19` |
| `19/11/2026` | `%d/%m/%Y` | `2026-11-19` |
| `11/19/2026` | `%m/%d/%Y` | `2026-11-19` |
| `19-11-2026 14:35` | `%d-%m-%Y %H:%i` | `2026-11-19 14:35:00` |
| `2026-11-19T14:35:08` | `%Y-%m-%dT%H:%i:%s` | `2026-11-19 14:35:08` |
| `2026-11-19 14:35:08.123456` | `%Y-%m-%d %H:%i:%s.%f` | Giữ phần microsecond |
| `02:35:08 PM` | `%r` | `14:35:08` |

Ví dụ truy vấn:

```sql
SELECT
    STR_TO_DATE('19/11/2026', '%d/%m/%Y') AS date_vn,
    STR_TO_DATE('11/19/2026', '%m/%d/%Y') AS date_us,
    STR_TO_DATE('2026-11-19T14:35:08', '%Y-%m-%dT%H:%i:%s') AS datetime_iso;
```

Format string phải khớp thứ tự thành phần. Dấu `T` trong chuỗi ISO ở ví dụ là ký tự phân cách tường minh; nó không phải token thời gian của MySQL.

### 5.3. Ưu tiên năm 4 chữ số

Specifier `%y` dùng quy tắc ánh xạ năm 2 chữ số: `00`–`69` được hiểu là `2000`–`2069`, còn `70`–`99` được hiểu là `1970`–`1999`. Quy tắc này có thể làm dữ liệu lịch sử bị hiểu sai nếu nguồn gửi năm rút gọn.

Với ngày tháng trao đổi giữa hệ thống, hãy yêu cầu năm 4 chữ số và dùng `%Y`. Chỉ dùng `%y` khi hợp đồng dữ liệu bắt buộc năm 2 chữ số và cả hai bên thống nhất quy tắc chuyển đổi.

## 6. Xác thực chuỗi và xử lý ngày không hợp lệ

`STR_TO_DATE()` giúp phân tích chuỗi, nhưng không thay thế hoàn toàn việc xác thực dữ liệu đầu vào. Chuỗi có thể sai thứ tự, thiếu thành phần, chứa ký tự thừa hoặc biểu diễn ngày không tồn tại.

### 6.1. Không chỉ kiểm tra kết quả khác NULL

Ví dụ đầu vào:

```sql
SELECT STR_TO_DATE('2026-11-19xyz', '%Y-%m-%d') AS parsed_value;
```

Quá trình quét có thể dừng khi không còn khớp format; phần ký tự dư ở cuối không nên được xem là đã xác thực. Vì vậy, kiểm tra `IS NOT NULL` đơn thuần chưa chứng minh toàn bộ chuỗi đầu vào hợp lệ.

Với định dạng số cố định và có quy tắc padding, có thể kiểm tra cả cấu trúc chuỗi và giá trị sau khi parse. Ví dụ với định dạng canonical `YYYY-MM-DD`, bước kiểm tra có thể gồm:

1. Kiểm tra chuỗi có đúng hình dạng 10 ký tự số và dấu gạch ở vị trí quy định.
2. Phân tích bằng `STR_TO_DATE(raw_value, '%Y-%m-%d')`.
3. Xác nhận giá trị temporal được tạo thành công.
4. Định dạng lại bằng `DATE_FORMAT(parsed_value, '%Y-%m-%d')` và so sánh với chuỗi gốc để phát hiện ký tự thừa hoặc dạng không canonical.

Round-trip là một bước kiểm tra hữu ích cho format số cố định, nhưng không thay thế kiểm tra miền ngày hợp lệ và phải xử lý lỗi parse theo phiên bản MySQL.

Ví dụ với một chuỗi đã có đúng cấu trúc:

```sql
SET @raw_date = '2026-11-19';
SET @parsed_date = STR_TO_DATE(@raw_date, '%Y-%m-%d');

SELECT
    @parsed_date AS parsed_date,
    DATE_FORMAT(@parsed_date, '%Y-%m-%d') AS canonical_value,
    BINARY @raw_date = BINARY DATE_FORMAT(@parsed_date, '%Y-%m-%d') AS exact_match;
```

`exact_match = 1` cho biết chuỗi khớp biểu diễn canonical này. Ví dụ chỉ minh họa kiểm tra chuỗi đã parse được; trên phiên bản có thể trả về ngày sai miền, vẫn phải kiểm tra ngày hợp lệ riêng.

### 6.2. Ngày không tồn tại và khác biệt phiên bản

Ví dụ `2026-02-30` có hình dạng giống ngày hợp lệ nhưng ngày 30 tháng 2 không tồn tại. Cách MySQL xử lý giá trị này phụ thuộc phiên bản:

- Từ MySQL 8.0.35, `STR_TO_DATE()` thực hiện kiểm tra phạm vi đầy đủ và báo lỗi nếu kết quả ngày không hợp lệ.
- Trước MySQL 8.0.35, việc kiểm tra phạm vi chưa đầy đủ; một số giá trị ngày không hợp lệ có thể được trả về mà không bị từ chối ngay tại hàm.

Không dựa vào việc hàm trả về giá trị để kết luận ngày hợp lệ trên mọi phiên bản. Kiểm thử hành vi trên phiên bản máy chủ thực tế, kiểm tra warning/error và xác thực ngày ở tầng ứng dụng hoặc quy trình import.

Ví dụ thử nghiệm có chủ đích trên môi trường lab:

```sql
SELECT STR_TO_DATE('2026-02-30', '%Y-%m-%d');
SHOW WARNINGS;
```

Trên phiên bản mới, câu `SELECT` có thể dừng bằng lỗi trước khi chạy `SHOW WARNINGS`; hãy bắt lỗi trong client hoặc ứng dụng để ghi nhận kết quả. Không dùng ví dụ ngày sai này trong luồng ghi dữ liệu nghiệp vụ.

### 6.3. Bảng staging cho dữ liệu import

Khi import CSV hoặc file từ hệ thống khác, giữ chuỗi gốc trong staging table để có thể điều tra dữ liệu không hợp lệ:

```sql
CREATE TABLE import_staging_dates (
    row_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_value VARCHAR(100) NOT NULL,
    PRIMARY KEY (row_id)
) ENGINE = InnoDB;

INSERT INTO import_staging_dates (source_value) VALUES
('2026-11-19'),
('2026-02-30'),
('19/11/2026'),
('2026-11-19-extra');
```

Với mỗi định dạng nguồn, xác định một parser riêng. Không dùng một format mơ hồ để thử nhiều cách rồi lấy cách đầu tiên thành công. Trong MySQL 8.0.35+, một giá trị sai miền có thể làm câu truy vấn chứa `STR_TO_DATE()` báo lỗi; quy trình import cần bắt lỗi theo từng lô hoặc parse trước trong ứng dụng để một dòng xấu không làm mất khả năng xác định dòng lỗi.

Sau khi xác thực, ghi dữ liệu vào cột `DATE`/`DATETIME` thật. Giữ `source_value` trong staging hoặc bảng lỗi theo thời hạn cần thiết để truy vết, rồi mới chuyển sang bước dọn staging.

## 7. Ngày giờ, DATETIME và TIMESTAMP

`DATE_FORMAT()` và `STR_TO_DATE()` làm việc với giá trị temporal, nhưng không tự cung cấp đầy đủ thông tin múi giờ.

### 7.1. DATETIME không tự chuyển đổi múi giờ

`DATETIME` lưu ngày giờ theo lịch, ví dụ `2026-11-19 09:00:00`. Khi đọc hoặc định dạng bằng `DATE_FORMAT()`, MySQL không tự chuyển giá trị này theo `time_zone` của session. Nếu ứng dụng coi giá trị là giờ địa phương, phải lưu kèm quy ước múi giờ ở nghiệp vụ hoặc lưu thêm zone ID phù hợp.

### 7.2. TIMESTAMP phụ thuộc múi giờ session

MySQL lưu `TIMESTAMP` theo UTC và chuyển đổi từ/đến múi giờ session khi ghi/đọc. Vì vậy, cùng một cột `TIMESTAMP` có thể được hiển thị khác nhau nếu session dùng múi giờ khác.

```sql
SELECT
    @@session.time_zone,
    created_at,
    DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS formatted_created_at
FROM orders
WHERE order_id = 1001;
```

Đặt session time zone rõ ràng trước khi định dạng hoặc xuất dữ liệu:

```sql
SET time_zone = '+00:00';
SELECT DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s')
FROM orders;
```

Nếu báo cáo cần giờ Việt Nam, dùng session timezone phù hợp hoặc chuyển đổi tường minh. `CONVERT_TZ()` cần timezone tables được nạp để nhận tên vùng như `Asia/Ho_Chi_Minh`; offset cố định không tự xử lý quy tắc DST của một vùng địa lý.

```sql
-- Đảm bảo TIMESTAMP được biểu diễn theo UTC trước khi truyền cho CONVERT_TZ.
SET time_zone = '+00:00';

SELECT DATE_FORMAT(
    CONVERT_TZ(created_at, '+00:00', 'Asia/Ho_Chi_Minh'),
    '%d/%m/%Y %H:%i:%s'
) AS created_at_vn
FROM orders;
```

Nếu `CONVERT_TZ()` trả `NULL`, kiểm tra timezone tables và tên múi giờ. Không dùng chuỗi offset cố định cho một vùng có quy tắc giờ mùa hè nếu dữ liệu cần tuân theo quy tắc địa lý.

### 7.3. STR_TO_DATE không phân tích timezone offset

Format của `STR_TO_DATE()` dùng để phân tích các thành phần ngày giờ, không phải parser ISO-8601 timezone hoàn chỉnh. Nếu chuỗi đầu vào có `Z` hoặc offset như `+07:00`, hãy tách và xử lý offset rõ ràng trong ứng dụng, hoặc parse thành `OffsetDateTime`/`Instant` bằng Java rồi ghi vào MySQL theo quy ước UTC.

Không bỏ mất offset rồi lưu phần ngày giờ còn lại như thể đó là UTC. Ví dụ `2026-11-19T09:00:00+07:00` tương ứng với `2026-11-19T02:00:00Z`, không phải `09:00:00Z`.

## 8. Truy vấn theo ngày giờ mà vẫn dùng index

`DATE_FORMAT()` rất tiện để hiển thị, nhưng không nên áp dụng hàm lên cột trong điều kiện lọc nếu mục tiêu là dùng index B-tree thông thường.

Không nên:

```sql
SELECT order_id, created_at
FROM orders
WHERE DATE_FORMAT(created_at, '%Y-%m-%d') = '2026-11-19';
```

Biểu thức áp dụng hàm lên `created_at` có thể khiến điều kiện không còn sargable với index thông thường trên cột đó.

Nên dùng khoảng thời gian nửa mở:

```sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= '2026-11-19 00:00:00'
  AND created_at <  '2026-11-20 00:00:00';
```

Điều kiện `>= đầu ngày` và `< đầu ngày kế tiếp` bao gồm toàn bộ thời điểm trong ngày, kể cả phần microsecond, mà không cần đoán thời điểm cuối ngày như `23:59:59.999999`.

Với một ngày được truyền vào từ ứng dụng, tính ngày kế tiếp ở tầng Java hoặc dùng biểu thức SQL rõ ràng. Khi cột là `TIMESTAMP`, hãy bảo đảm ranh giới đầu/cuối được tính theo múi giờ nghiệp vụ rồi chuyển thành instant phù hợp với session kết nối.

Nếu cần nhóm kết quả theo ngày để hiển thị, có thể dùng `DATE_FORMAT()` trong phần `SELECT` hoặc `GROUP BY`, nhưng hãy đánh giá kế hoạch và số lượng hàng được đọc. Với báo cáo lớn, cân nhắc cột ngày sinh ra (generated column) hoặc bảng tổng hợp nếu workload cần truy vấn lặp lại theo ngày.

## 9. So sánh format của MySQL với Java

MySQL và Java dùng hai hệ ký hiệu format khác nhau. Không chuyển nguyên chuỗi format từ lớp này sang lớp kia.

| Ý nghĩa | MySQL | Java `DateTimeFormatter` |
| --- | --- | --- |
| Năm 4 chữ số | `%Y` | `uuuu` hoặc `yyyy` tùy mục đích |
| Tháng 2 chữ số | `%m` | `MM` |
| Ngày 2 chữ số | `%d` | `dd` |
| Giờ 24 giờ | `%H` | `HH` |
| Phút | `%i` | `mm` |
| Giây | `%s` | `ss` |
| Microsecond 6 chữ số | `%f` | `SSSSSS` |
| AM/PM | `%p` | `a` |

Ví dụ Java:

```java
DateTimeFormatter formatter = DateTimeFormatter.ofPattern("dd/MM/uuuu", Locale.ROOT);
String displayDate = LocalDate.of(2026, 11, 19).format(formatter);
LocalDate parsedDate = LocalDate.parse("19/11/2026", formatter);
```

Với đầu vào dạng ISO, `LocalDate.parse("2026-11-19")` dùng ISO formatter mặc định. Với `Instant`, cần formatter có offset hoặc dùng `Instant.parse()` cho chuỗi ISO-8601 UTC. Java có thể parse và validate trước khi ghi, giúp tránh đưa chuỗi chưa xác thực vào SQL.

Nếu JDBC đã nhận `LocalDate` hoặc `LocalDateTime`, dùng `PreparedStatement.setObject()` và để driver truyền giá trị temporal. Không format thành chuỗi chỉ để parse lại trong cùng ứng dụng.

## 10. Quy trình xử lý dữ liệu ngày giờ đề xuất

Một quy trình ổn định thường gồm các bước:

1. **Xác định hợp đồng đầu vào:** format, locale, múi giờ, độ chính xác phần giây và các thành phần bắt buộc.
2. **Kiểm tra cấu trúc:** độ dài, dấu phân cách, chữ số, ký tự thừa và quy tắc padding.
3. **Phân tích:** dùng `STR_TO_DATE()` với format cụ thể hoặc parse bằng Java Time API.
4. **Kiểm tra miền:** ngày có tồn tại, giờ/phút/giây nằm trong miền, offset và zone có hợp lệ.
5. **Chuẩn hóa:** chuyển về kiểu temporal đúng ngữ nghĩa; với instant, áp dụng quy ước UTC rõ ràng.
6. **Lưu trữ:** ghi vào `DATE`, `TIME`, `DATETIME` hoặc `TIMESTAMP`, không lưu chuỗi hiển thị làm dữ liệu chính.
7. **Hiển thị/xuất:** dùng `DATE_FORMAT()` hoặc Java formatter ở lớp trình bày theo locale người nhận.
8. **Truy vấn:** lọc bằng khoảng thời gian trên cột gốc để giữ khả năng dùng index.

Quy trình import nên giữ giá trị gốc và báo được dòng lỗi. Quy trình API nên từ chối format không đúng hợp đồng thay vì cố đoán. Báo cáo cần ghi rõ timezone và locale đã sử dụng để cùng một dữ liệu có thể được tái tạo nhất quán.

## 11. Bài tập thực hành

1. Dùng `DATE_FORMAT()` hiển thị một ngày theo `dd/mm/yyyy`, một ngày theo tên tháng và một thời điểm có microsecond.
2. Dùng `STR_TO_DATE()` phân tích `19/11/2026`, `11/19/2026` và `2026-11-19T14:35:08` bằng ba format khác nhau.
3. Thử format sai thứ tự ngày/tháng và giải thích vì sao format đầu vào phải đến từ hợp đồng dữ liệu.
4. So sánh `%Y` với `%y` bằng các năm `69`, `70`, `26` và giải thích quy tắc ánh xạ năm hai chữ số.
5. Đổi `lc_time_names` sang một locale được hỗ trợ và quan sát `%M`, `%b`, `%W`, `%a`.
6. Thử chuỗi có ký tự thừa ở cuối và thiết kế bước kiểm tra để không chấp nhận đầu vào chưa được xác thực toàn bộ.
7. Thử ngày không tồn tại như `2026-02-30` trên phiên bản MySQL lab. Ghi nhận khác biệt trước/sau MySQL 8.0.35 và cách ứng dụng xử lý lỗi.
8. Lưu một thời điểm vào cột `TIMESTAMP`, truy vấn với session UTC và session `+07:00`; so sánh giá trị hiển thị.
9. So sánh `EXPLAIN` cho điều kiện dùng `DATE_FORMAT(created_at, ...)` với điều kiện khoảng nửa mở trên `created_at`.
10. Viết Java code parse `LocalDate` bằng `DateTimeFormatter`, sau đó ghi bằng JDBC `setObject()` và so sánh với cách parse bằng `STR_TO_DATE()`.

## 12. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể giải thích đúng vai trò của `DATE_FORMAT()` và `STR_TO_DATE()`, viết format string tường minh cho ngày và thời gian, xử lý locale và năm hai chữ số, phát hiện đầu vào sai hoặc ngày không tồn tại theo phiên bản MySQL, chuyển đổi múi giờ có chủ đích, và viết điều kiện lọc ngày giờ giữ khả năng dùng index. Bạn cũng cần phân biệt khi nào nên parse ở MySQL và khi nào nên dùng Java Time API trước khi truyền giá trị có kiểu qua JDBC.

# Zero date, ngày không hợp lệ và ảnh hưởng của SQL mode

MySQL có thể gặp các giá trị ngày giờ đặc biệt như **zero date** (0000-00-00), ngày thiếu thành phần (2024-00-15, 2024-02-00) hoặc ngày không tồn tại trên lịch (2024-02-31). Việc máy chủ chấp nhận, cảnh báo hay từ chối các giá trị này phụ thuộc vào kiểu cột, SQL mode, storage engine và phiên bản MySQL.

Những giá trị này thường xuất hiện khi nhập dữ liệu từ hệ thống cũ, chuyển dữ liệu từ CSV, dùng giá trị mặc định không hợp lệ hoặc ứng dụng gửi chuỗi ngày chưa được xác thực. Nếu không xử lý thống nhất, dữ liệu ngày giờ có thể gây lỗi migration, kết quả truy vấn khó hiểu, sai báo cáo và lỗi khi ánh xạ sang kiểu ngày giờ trong Java.

Trong module **DATABASE_MYSQL**, quản lý ngày giờ liên quan trực tiếp đến kiểu dữ liệu, tính toàn vẹn, transaction, truy vấn theo khoảng thời gian và vận hành. Bài học này phân biệt các loại ngày không hợp lệ, giải thích vai trò của SQL mode, hướng dẫn phát hiện dữ liệu cũ và xây dựng quy trình loại bỏ zero date an toàn.

## 1. Phân biệt zero date và ngày không hợp lệ

Không phải mọi giá trị ngày bất thường đều là cùng một loại lỗi.

| Giá trị | Phân loại | Vấn đề |
|---|---|---|
| 0000-00-00 | Zero date | Cả năm, tháng và ngày đều bằng 0 |
| 2024-00-15 | Ngày thiếu thành phần | Tháng bằng 0 |
| 2024-02-00 | Ngày thiếu thành phần | Ngày bằng 0 |
| 2024-02-31 | Ngày không tồn tại trên lịch | Tháng 2 không có ngày 31 |
| 2024-13-10 | Thành phần vượt miền | Tháng 13 không hợp lệ |
| NULL | Không có giá trị | Biểu diễn giá trị chưa biết hoặc không áp dụng |

Cần phân biệt ba trường hợp:

- **Zero date** là một giá trị đặc biệt mà MySQL có thể chấp nhận trong một số cấu hình.
- **Ngày không hợp lệ** là giá trị vi phạm lịch, ví dụ ngày 31 tháng 2.
- **NULL** là giá trị không tồn tại theo ngữ nghĩa SQL, không phải một ngày đặc biệt.

Không nên dùng zero date để biểu diễn "chưa biết", "chưa nhập" hoặc "không áp dụng". Với cột tùy chọn, hãy dùng NULL; với dữ liệu bắt buộc, yêu cầu ứng dụng cung cấp một ngày hợp lệ hoặc thiết kế trạng thái nghiệp vụ riêng.

## 2. Miền giá trị của các kiểu ngày giờ

Trước khi kiểm tra ngày không hợp lệ, cần biết giới hạn của kiểu cột.

| Kiểu | Miền giá trị thông thường trong MySQL | Đặc điểm |
|---|---|---|
| DATE | 1000-01-01 đến 9999-12-31 | Chỉ lưu ngày |
| DATETIME | 1000-01-01 00:00:00 đến 9999-12-31 23:59:59 | Lưu ngày và giờ, không tự chuyển đổi theo timezone của session |
| TIMESTAMP | Xấp xỉ 1970-01-01 00:00:01 UTC đến 2038-01-19 03:14:07 UTC | Lưu thời điểm và chuyển đổi theo timezone của session |
| TIME | -838:59:59 đến 838:59:59 | Biểu diễn thời lượng hoặc thành phần giờ, không phải ngày lịch |

Các kiểu có hỗ trợ phần giây thập phân tùy khai báo, ví dụ DATETIME(3) hoặc TIMESTAMP(6). Miền của TIMESTAMP hẹp hơn đáng kể so với DATETIME; không dùng TIMESTAMP cho ngày lịch sử hoặc tương lai nằm ngoài miền hỗ trợ.

MySQL còn có thể biểu diễn zero date hoặc ngày thiếu thành phần trong một số cấu hình. Những giá trị đó không làm thay đổi miền ngày hợp lệ và không nên được xem là dữ liệu ngày giờ bình thường.

## 3. SQL mode điều khiển việc chấp nhận ngày không hợp lệ

SQL mode thay đổi cách MySQL kiểm tra và xử lý câu lệnh. Cùng một câu INSERT có thể thành công kèm warning trong một session nhưng thất bại trong session khác.

Các mode cần hiểu:

| SQL mode | Vai trò |
|---|---|
| STRICT_TRANS_TABLES | Bật strict behavior cho transactional engine và xử lý theo quy tắc strict đối với engine khác |
| STRICT_ALL_TABLES | Bật strict behavior cho mọi storage engine |
| NO_ZERO_DATE | Kiểm soát việc chấp nhận giá trị ngày toàn số 0 |
| NO_ZERO_IN_DATE | Kiểm soát ngày có năm khác 0 nhưng tháng hoặc ngày bằng 0 |
| ALLOW_INVALID_DATES | Nới kiểm tra ngày lịch đối với DATE và DATETIME; chỉ kiểm tra tháng 1–12 và ngày 1–31 |
| IGNORE trong DML | Có thể hạ một số lỗi dữ liệu thành warning và điều chỉnh/bỏ qua hàng theo ngữ cảnh |

### 3.1. STRICT_TRANS_TABLES và STRICT_ALL_TABLES

Strict mode yêu cầu MySQL từ chối nhiều giá trị không hợp lệ hoặc bị cắt thay vì âm thầm ép về giá trị mặc định.

- Với bảng transactional như InnoDB, một lỗi dữ liệu trong câu lệnh thường làm câu lệnh thất bại; transaction có thể rollback theo ngữ cảnh.
- Với bảng non-transactional, không thể giả định toàn bộ thao tác được hoàn tác. Trong một số câu lệnh nhiều hàng, các hàng đã ghi trước khi gặp lỗi có thể vẫn còn.
- STRICT_TRANS_TABLES tập trung vào transactional engine và có quy tắc xử lý riêng cho engine non-transactional.
- STRICT_ALL_TABLES áp dụng strict behavior rộng hơn cho mọi engine, nhưng engine non-transactional vẫn không có khả năng rollback dữ liệu đã ghi.

Với ứng dụng giao dịch, nên dùng InnoDB và strict mode để phát hiện dữ liệu sai tại thời điểm ghi.

### 3.2. NO_ZERO_DATE

NO_ZERO_DATE kiểm soát việc chấp nhận 0000-00-00 hoặc zero datetime tương ứng.

Kết quả còn phụ thuộc strict mode:

- Khi strict mode cùng NO_ZERO_DATE được bật, thao tác ghi zero date thường bị từ chối với lỗi.
- Khi không bật strict mode, giá trị có thể được chấp nhận kèm warning.
- Khi dùng INSERT IGNORE hoặc UPDATE IGNORE, một số lỗi có thể bị chuyển thành warning và giá trị được xử lý theo quy tắc của câu lệnh.

Không dựa vào việc server "vẫn insert được" để kết luận zero date hợp lệ. Hãy kiểm tra warning ngay sau câu lệnh và kiểm tra SQL mode của session.

### 3.3. NO_ZERO_IN_DATE

NO_ZERO_IN_DATE xử lý ngày có năm khác 0 nhưng tháng hoặc ngày bằng 0, ví dụ 2024-00-15 và 2024-02-00.

Khi strict mode kết hợp với mode này, các giá trị có thành phần tháng/ngày bằng 0 bị từ chối. Nếu strict mode không bật, MySQL có thể chấp nhận kèm warning tùy cấu hình.

NO_ZERO_DATE và NO_ZERO_IN_DATE giải quyết hai dạng dữ liệu khác nhau. Bật một mode không có nghĩa đã xử lý đầy đủ mọi ngày thiếu thành phần hoặc ngày sai lịch.

### 3.4. ALLOW_INVALID_DATES

ALLOW_INVALID_DATES nới việc kiểm tra ngày lịch đối với cột DATE và DATETIME. MySQL vẫn kiểm tra tháng trong khoảng 1–12 và ngày trong khoảng 1–31, nhưng không kiểm tra đầy đủ số ngày tồn tại trong từng tháng.

Ví dụ, khi mode này được bật, giá trị như 2024-02-31 có thể được chấp nhận vì tháng là 2 và ngày là 31, dù ngày đó không tồn tại trên lịch. Mode này không áp dụng cho TIMESTAMP, vốn luôn yêu cầu ngày giờ hợp lệ.

Chỉ dùng ALLOW_INVALID_DATES khi có yêu cầu dữ liệu đặc thù đã được xác định rõ. Nó không phải cách khắc phục lỗi nhập ngày và không nên bật để làm cho một migration chạy qua.

### 3.5. Lưu ý về phiên bản và SQL mode mặc định

SQL mode mặc định có thể khác theo phiên bản MySQL, bản phân phối, cấu hình cài đặt và nhà cung cấp dịch vụ. Một số mode như NO_ZERO_DATE và NO_ZERO_IN_DATE đã được đánh dấu deprecated trong một số bản MySQL 8.0; trạng thái và warning cụ thể cần được kiểm tra trong tài liệu đúng phiên bản.

Điều quan trọng là kiểm tra strict mode và xác thực dữ liệu đầu vào. Không xây dựng chính sách chất lượng dữ liệu chỉ dựa vào hai mode zero-date.

## 4. Kiểm tra SQL mode đang áp dụng

SQL mode có thể được cấu hình ở cấp global và session. Session hiện tại có thể khác global do cấu hình kết nối, connection pool hoặc lệnh SET SESSION.

Chạy:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

Có thể xem riêng:

```sql
SELECT
    FIND_IN_SET('STRICT_TRANS_TABLES', @@SESSION.sql_mode)
        AS strict_trans_tables,
    FIND_IN_SET('STRICT_ALL_TABLES', @@SESSION.sql_mode)
        AS strict_all_tables,
    FIND_IN_SET('NO_ZERO_DATE', @@SESSION.sql_mode)
        AS no_zero_date,
    FIND_IN_SET('NO_ZERO_IN_DATE', @@SESSION.sql_mode)
        AS no_zero_in_date,
    FIND_IN_SET('ALLOW_INVALID_DATES', @@SESSION.sql_mode)
        AS allow_invalid_dates;
```

Giá trị lớn hơn 0 nghĩa là mode có trong danh sách session. Giá trị 0 nghĩa là không có; NULL có thể xuất hiện nếu tên mode hoặc biểu thức không được nhận diện như mong đợi.

### 4.1. Thay đổi SQL mode cho session thử nghiệm

Có thể thay đổi SQL mode trong session riêng để kiểm thử:

```sql
SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE';
```

Lệnh trên **thay thế toàn bộ danh sách SQL mode của session** bằng danh sách mẫu. Không sao chép trực tiếp vào ứng dụng production nếu chưa giữ lại các mode khác mà hệ thống cần.

Thay đổi SESSION chỉ ảnh hưởng kết nối hiện tại. SET GLOBAL sql_mode = ... tác động giá trị mặc định cho các kết nối mới, không tự thay đổi session đang mở. Cấu hình lâu dài cần được quản lý qua file cấu hình server hoặc cơ chế persistence được phiên bản hỗ trợ, có kiểm soát và review.

Với connection pool, mỗi kết nối có thể giữ session state riêng. Hãy kiểm tra SQL mode trên chính kết nối ứng dụng đang sử dụng, không chỉ trên một phiên đăng nhập DBA.

## 5. Thử nghiệm hành vi với zero date và ngày sai

Tạo bảng thử nghiệm InnoDB trong database lab:

```sql
CREATE TABLE date_mode_probe (
    id INT PRIMARY KEY,
    event_date DATE NULL,
    event_time DATETIME NULL
) ENGINE = InnoDB;
```

Trong session strict cùng các mode zero-date, thử ghi ngày hợp lệ:

```sql
INSERT INTO date_mode_probe (id, event_date, event_time)
VALUES (1, '2024-02-29', '2024-02-29 10:30:00');
```

Năm 2024 là năm nhuận nên ngày 29 tháng 2 hợp lệ.

Thử zero date:

```sql
INSERT INTO date_mode_probe (id, event_date)
VALUES (2, '0000-00-00');
```

Thử ngày thiếu tháng hoặc ngày:

```sql
INSERT INTO date_mode_probe (id, event_date)
VALUES (3, '2024-00-15');

INSERT INTO date_mode_probe (id, event_date)
VALUES (4, '2024-02-00');
```

Với strict mode và các mode zero-date tương ứng, các thao tác trên được kỳ vọng bị từ chối. Hãy quan sát mã lỗi và thông báo thực tế trên phiên bản đang chạy.

Thử ngày không tồn tại:

```sql
INSERT INTO date_mode_probe (id, event_date)
VALUES (5, '2024-02-31');
```

Khi không bật ALLOW_INVALID_DATES, MySQL kiểm tra tính hợp lệ của ngày theo lịch và từ chối ngày 31 tháng 2. Nếu bật ALLOW_INVALID_DATES, hành vi có thể khác đối với DATE/DATETIME, vì vậy hãy thử trong session lab riêng.

Ngay sau một thao tác phát warning, chạy:

```sql
SHOW WARNINGS;
```

Đừng dùng INSERT IGNORE trong bài kiểm tra đầu tiên. Nó có thể biến lỗi thành warning, khiến kết quả khác với chế độ strict thông thường.

## 6. Zero date ảnh hưởng đến truy vấn và hàm ngày giờ

Zero date không có cùng ngữ nghĩa với ngày lịch hợp lệ. Các phép toán cần ngày đầy đủ có thể trả NULL, trả kết quả đặc biệt hoặc phát warning tùy hàm và phiên bản.

Ví dụ, các phép cộng ngày/tháng và chuyển đổi timezone cần đầu vào hợp lệ. Không nên giả định mọi hàm ngày giờ sẽ xử lý zero date theo cùng một cách.

Ngày thiếu thành phần cũng gây khó khăn cho:

- DATEDIFF() và phép tính khoảng thời gian.
- DATE_ADD() hoặc DATE_SUB().
- Trích xuất năm, tháng, ngày.
- Sắp xếp và lọc theo khoảng ngày.
- Báo cáo theo tháng, quý và năm.
- Mapping sang LocalDate, LocalDateTime hoặc kiểu thời gian của driver JDBC.

Đặc biệt, một điều kiện như event_date < CURRENT_DATE() không có ý nghĩa nghiệp vụ rõ ràng nếu bảng chứa zero date dùng để biểu diễn "chưa xác định". Không nên dựa vào thứ tự sắp xếp của zero date để mã hóa trạng thái.

## 7. Phát hiện dữ liệu zero date và ngày thiếu thành phần

Trước khi bật strict mode hoặc sửa schema, cần kiểm kê dữ liệu cũ. Ví dụ bảng events có cột event_date:

```sql
SELECT
    COUNT(*) AS total_rows,
    SUM(event_date IS NULL) AS null_rows,
    SUM(
        YEAR(event_date) = 0
        AND MONTH(event_date) = 0
        AND DAYOFMONTH(event_date) = 0
    ) AS zero_date_rows,
    SUM(
        YEAR(event_date) <> 0
        AND (MONTH(event_date) = 0 OR DAYOFMONTH(event_date) = 0)
    ) AS incomplete_date_rows
FROM events;
```

Để xem các bản ghi cần xử lý:

```sql
SELECT id, event_date
FROM events
WHERE event_date IS NOT NULL
  AND (
      YEAR(event_date) = 0
      OR MONTH(event_date) = 0
      OR DAYOFMONTH(event_date) = 0
  )
ORDER BY id;
```

Các biểu thức hàm trên cột có thể khiến truy vấn audit phải quét nhiều hàng. Đây là truy vấn kiểm kê, không phải mẫu lọc hiệu năng cho luồng ứng dụng. Trên bảng lớn, hãy chạy có kế hoạch, giới hạn theo khóa hoặc phân vùng nếu phù hợp.

### 7.1. Phát hiện ngày sai lịch nếu dữ liệu được lưu bằng ALLOW_INVALID_DATES

Nếu trước đây hệ thống bật ALLOW_INVALID_DATES, dữ liệu có thể chứa ngày có tháng trong khoảng 1–12 và ngày trong khoảng 1–31 nhưng không tồn tại trên lịch. Ví dụ 2024-02-31.

Sau khi đã loại riêng zero date và ngày thiếu thành phần, có thể kiểm tra ngày lớn hơn số ngày của tháng. Ví dụ:

```sql
SELECT id, event_date
FROM events
WHERE event_date IS NOT NULL
  AND YEAR(event_date) BETWEEN 1000 AND 9999
  AND MONTH(event_date) BETWEEN 1 AND 12
  AND DAYOFMONTH(event_date) BETWEEN 1 AND 31
  AND DAYOFMONTH(event_date) >
      DAY(
          LAST_DAY(
              CONCAT(
                  LPAD(YEAR(event_date), 4, '0'), '-',
                  LPAD(MONTH(event_date), 2, '0'), '-01'
              )
          )
      );
```

Truy vấn dùng ngày đầu tháng hợp lệ để lấy ngày cuối tháng, sau đó so sánh với ngày đang lưu. Nó giúp phát hiện các trường hợp như ngày 31 tháng 2 và vẫn xét đúng tháng 2 của năm nhuận. Hãy thử với dữ liệu mẫu trên đúng phiên bản MySQL trước khi chạy kiểm kê quy mô lớn.

## 8. Làm sạch dữ liệu cũ an toàn

Không nên thay mọi zero date thành một ngày tùy ý như 1970-01-01 hoặc 2000-01-01. Một ngày giả có thể bị hiểu là ngày nghiệp vụ thật và làm sai báo cáo.

Trước khi sửa, phân loại ý nghĩa của dữ liệu:

- Nếu zero date có nghĩa "chưa biết" hoặc "chưa được cung cấp", cân nhắc chuyển thành NULL.
- Nếu nó biểu diễn một trạng thái nghiệp vụ như "chưa hoàn tất", lưu trạng thái vào cột riêng.
- Nếu dữ liệu ngày bị lỗi nhưng có thể đối chiếu nguồn gốc, đưa vào vùng cách ly và sửa theo dữ liệu gốc.
- Nếu không thể khôi phục chính xác, ghi nhận rõ chính sách xử lý và số lượng bản ghi bị ảnh hưởng.

### 8.1. Chuẩn bị cột cho NULL nếu cần

Nếu chính sách chuyển zero date thành NULL, cột phải cho phép NULL. Ví dụ minh họa:

```sql
ALTER TABLE events
    MODIFY event_date DATE NULL;
```

Trong hệ thống thực tế, câu MODIFY phải khai báo lại đầy đủ kiểu, default, comment và các thuộc tính hiện tại của cột. Không thực hiện khi chưa kiểm tra schema và phụ thuộc của ứng dụng.

### 8.2. Cập nhật các giá trị zero date

Sau khi backup và xác nhận chính sách, có thể cập nhật các giá trị zero hoặc thiếu thành phần về NULL:

```sql
UPDATE events
SET event_date = NULL
WHERE event_date IS NOT NULL
  AND (
      YEAR(event_date) = 0
      OR MONTH(event_date) = 0
      OR DAYOFMONTH(event_date) = 0
  );
```

Ví dụ này chỉ đúng nếu toàn bộ các giá trị đó thực sự có nghĩa là không có ngày. Nếu một số bản ghi mang thông tin có thể phục hồi, hãy tách chúng ra và xử lý riêng trước khi cập nhật.

Với bảng lớn, chia migration thành các lô theo primary key, theo dõi thời gian khóa, undo/redo, replication lag và dung lượng log. Không chạy một UPDATE toàn bảng trong giờ cao điểm mà chưa đo tác động.

### 8.3. Xử lý ngày sai lịch

Ngày như 2024-02-31 không thể tự động chuyển thành 2024-02-29 nếu chưa có quy tắc nghiệp vụ. Hãy đối chiếu nguồn dữ liệu hoặc đưa bản ghi vào bảng cách ly để người sở hữu dữ liệu quyết định.

Không dùng STR_TO_DATE() như một phép xác thực duy nhất mà không kiểm tra kết quả và warning. Quy tắc phân tích và kiểm tra range có thể thay đổi theo phiên bản; ứng dụng nhập liệu nên xác thực ngày bằng thư viện ngày giờ có kiểm tra lịch, sau đó gửi giá trị hợp lệ đến MySQL.

## 9. Thiết kế schema và ứng dụng để ngăn dữ liệu sai quay trở lại

### 9.1. Dùng NULL hoặc trạng thái riêng thay cho zero date

Nếu ngày không bắt buộc:

```sql
CREATE TABLE subscriptions (
    subscription_id BIGINT PRIMARY KEY,
    started_on DATE NOT NULL,
    cancelled_on DATE NULL
) ENGINE = InnoDB;
```

cancelled_on IS NULL biểu diễn chưa có ngày hủy. Nếu nghiệp vụ cần phân biệt "chưa yêu cầu hủy", "đang xử lý" và "đã hủy", hãy dùng cột trạng thái riêng thay vì gán một ngày giả.

### 9.2. Không đặt zero date làm DEFAULT

Tránh khai báo:

```sql
-- Không dùng làm mặc định
CREATE TABLE legacy_events (
    event_id BIGINT PRIMARY KEY,
    event_date DATE NOT NULL DEFAULT '0000-00-00'
);
```

Thay vào đó, cột tùy chọn có thể dùng DEFAULT NULL; cột bắt buộc nên yêu cầu ứng dụng cung cấp ngày hợp lệ hoặc dùng default hợp lệ phù hợp nghiệp vụ.

### 9.3. Xác thực ở ứng dụng và database

Ứng dụng nên parse đầu vào thành kiểu ngày giờ thực trước khi bind. Với Java:

| MySQL | Kiểu Java thường dùng |
|---|---|
| DATE | LocalDate |
| DATETIME | LocalDateTime |
| TIMESTAMP | Instant hoặc kiểu thời điểm có timezone phù hợp với thiết kế ứng dụng |
| TIME | LocalTime hoặc kiểu biểu diễn duration nếu cột lưu thời lượng |

DATETIME không tự chuyển đổi theo timezone session; TIMESTAMP được chuyển đổi giữa timezone session và UTC trong quá trình lưu/đọc. Hãy chọn kiểu Java theo ý nghĩa dữ liệu, không chỉ theo tên SQL type.

Khi dùng JDBC, bind kiểu tương ứng thay vì gửi chuỗi tùy ý:

```java
LocalDate eventDate = LocalDate.parse(inputDate);

try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO events (id, event_date) VALUES (?, ?)")) {
    ps.setLong(1, eventId);
    ps.setObject(2, eventDate);
    ps.executeUpdate();
}
```

Nếu chuỗi đầu vào không phải ngày hợp lệ, LocalDate.parse() sẽ thất bại trước khi dữ liệu được gửi đến database. Với Connector/J, mapping Java time được hỗ trợ trong các phiên bản hiện đại; hãy kiểm tra tương thích driver đang dùng và không dựa vào tùy chọn chuyển zero date thành một giá trị giả.

### 9.4. Bảo đảm session SQL mode nhất quán

Ứng dụng, migration tool, batch import và DBA console có thể dùng session khác nhau. Hãy chuẩn hóa SQL mode qua cấu hình server và cấu hình khởi tạo connection, đồng thời kiểm tra session thực tế.

Với connection pool, cần bảo đảm session không giữ một SQL mode permissive từ tác vụ trước. Khi mượn connection, ứng dụng không nên giả định mọi kết nối đều có cùng trạng thái nếu pool không reset session state.

## 10. Quy trình triển khai strict date validation

Khi muốn loại bỏ zero date và ngày không hợp lệ trong một hệ thống đang chạy, hãy đi theo từng giai đoạn:

1. **Kiểm kê SQL mode.** Lấy @@GLOBAL.sql_mode và @@SESSION.sql_mode trên server, migration tool và kết nối ứng dụng.
2. **Kiểm kê schema.** Tìm các cột DATE, DATETIME, TIMESTAMP, default zero date và cột NOT NULL có thể đang dùng giá trị giả.
3. **Kiểm kê dữ liệu.** Đếm zero date, ngày thiếu thành phần và ngày sai lịch; xuất danh sách khóa để chủ dữ liệu xác nhận.
4. **Chọn chính sách chuyển đổi.** Quyết định trường hợp nào thành NULL, trạng thái riêng, ngày được khôi phục hoặc bản ghi cách ly.
5. **Chuẩn bị schema.** Điều chỉnh nullability/default và ứng dụng theo migration đã review.
6. **Làm sạch theo lô.** Cập nhật dữ liệu có kiểm soát, ghi số hàng trước/sau và lưu audit trail.
7. **Bật strict behavior.** Thử trong staging, sau đó triển khai SQL mode nhất quán cho các kết nối.
8. **Kiểm thử nhập liệu.** Thử ngày hợp lệ, ngày nhuận, zero date, tháng/ngày bằng 0, ngày sai lịch, NULL và giá trị ngoài miền.
9. **Theo dõi warning/error.** Kiểm tra log ứng dụng, lỗi SQL, batch import và các job ETL.
10. **Xác minh sau triển khai.** Chạy lại truy vấn kiểm kê, xác nhận không còn giá trị cấm và thử backup/restore nếu migration có thay đổi dữ liệu lớn.

Không bật strict mode trên production trước khi kiểm kê dữ liệu và kiểm thử các luồng import. Các hệ thống cũ có thể phụ thuộc vào hành vi permissive; bật strict đột ngột có thể làm batch job hoặc request bắt đầu thất bại.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| 0000-00-00 tương đương NULL | Zero date là giá trị ngày đặc biệt; NULL là không có giá trị |
| Bật NO_ZERO_DATE là đủ | Cần xét strict mode, NO_ZERO_IN_DATE, ALLOW_INVALID_DATES và validation |
| ALLOW_INVALID_DATES chấp nhận mọi chuỗi bất kỳ | Mode vẫn kiểm tra tháng 1–12 và ngày 1–31; nó chỉ bỏ kiểm tra đầy đủ số ngày trong tháng |
| Ngày 2024-02-31 luôn bị từ chối | ALLOW_INVALID_DATES có thể làm DATE/DATETIME chấp nhận ngày đó |
| INSERT IGNORE là cách sửa dữ liệu | IGNORE có thể biến lỗi thành warning và che giấu dữ liệu đầu vào sai |
| Mọi engine đều rollback được khi strict mode phát lỗi | Engine non-transactional không thể hoàn tác dữ liệu đã ghi |
| SQL mode global thay đổi session đang mở | Session hiện tại có thể giữ giá trị riêng; global chủ yếu áp dụng cho kết nối mới |
| Có thể thay mọi zero date bằng ngày 1970 | Ngày giả làm sai ngữ nghĩa; dùng NULL, trạng thái riêng hoặc đối chiếu nguồn |

## 12. Ghi nhớ

- Phân biệt zero date, ngày thiếu thành phần, ngày sai lịch và NULL.
- NO_ZERO_DATE kiểm soát ngày toàn số 0; NO_ZERO_IN_DATE kiểm soát tháng/ngày bằng 0 khi năm khác 0.
- Strict mode quyết định nhiều trường hợp sai dữ liệu trở thành lỗi thay vì chỉ warning.
- ALLOW_INVALID_DATES nới kiểm tra lịch cho DATE/DATETIME nhưng không áp dụng cho TIMESTAMP.
- SQL mode có cấp global và session; luôn kiểm tra trên chính kết nối ứng dụng.
- INSERT IGNORE có thể che giấu lỗi bằng warning; hãy đọc SHOW WARNINGS.
- Không dùng zero date làm giá trị mặc định hoặc mã hóa trạng thái nghiệp vụ.
- Trước khi làm sạch, cần kiểm kê, phân loại ý nghĩa dữ liệu, backup và thử migration trên staging.
- Dùng LocalDate, LocalDateTime và kiểu thời điểm phù hợp trong Java; xác thực đầu vào trước khi bind JDBC.

Khi kiểm soát SQL mode, schema và validation ở ứng dụng, MySQL có thể từ chối dữ liệu ngày giờ sai ngay tại ranh giới ghi, giúp truy vấn thời gian, báo cáo và migration hoạt động nhất quán hơn.


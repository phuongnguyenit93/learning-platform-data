# Nạp theo lô, bỏ dòng lỗi có kiểm soát và đọc warning

Nạp dữ liệu số lượng lớn vào MySQL cần xử lý đồng thời tốc độ, chất lượng dữ liệu và khả năng chạy lại an toàn. `LOAD DATA INFILE` thường là lựa chọn hiệu quả để nạp file văn bản có cấu trúc như CSV hoặc TSV. Tuy nhiên, một lệnh nạp có thể gặp dữ liệu sai định dạng, giá trị vượt giới hạn cột, khóa trùng hoặc lỗi chuyển kiểu. Nếu chỉ thêm `IGNORE` để lệnh tiếp tục, dữ liệu bị bỏ qua có thể không được phát hiện cho tới khi ứng dụng báo cáo sai.

Quy trình đáng tin cậy cần lưu bản gốc, nạp vào vùng staging, kiểm tra warning ngay sau lệnh nạp, phân loại dòng không hợp lệ, đưa dòng lỗi vào vùng cách ly và chỉ chuyển dữ liệu hợp lệ vào bảng nghiệp vụ sau khi đối soát. Mỗi batch cần có mã nhận diện, số dòng kỳ vọng và trạng thái xử lý để có thể điều tra hoặc chạy lại mà không nhân đôi dữ liệu.

## 1. Chọn phương pháp nạp theo lô

MySQL có một số cách nạp dữ liệu thường dùng:

| Phương pháp | Phù hợp khi | Điểm cần cân nhắc |
|---|---|---|
| `LOAD DATA INFILE` | Nạp file nằm trên máy chủ MySQL hoặc filesystem mà server được phép đọc | Cần quyền `FILE`, kiểm soát `secure_file_priv` và đường dẫn server nhìn thấy |
| `LOAD DATA LOCAL INFILE` | File nằm trên máy chạy client hoặc ứng dụng import | Client gửi file qua kết nối; cần cho phép `local_infile` ở server và client, kiểm soát nguồn file và TLS khi đi qua mạng |
| Multi-row `INSERT` | Batch nhỏ, dữ liệu đã được ứng dụng kiểm tra hoặc tạo trực tiếp | Dễ tích hợp logic ứng dụng; cần giới hạn kích thước câu lệnh và số round trip |
| Công cụ ETL/CDC | Nhiều nguồn dữ liệu, mapping phức tạp, cần checkpoint hoặc biến đổi nhiều bước | Cần vận hành pipeline, theo dõi lỗi và quản lý thứ tự dữ liệu |

Với file lớn, `LOAD DATA` thường nhanh hơn việc gửi từng câu `INSERT` riêng lẻ vì giảm chi phí giao tiếp và xử lý câu lệnh. Nhưng tốc độ không phải tiêu chí duy nhất: định dạng nguồn, chất lượng dữ liệu, khả năng khôi phục, giới hạn khóa và tác động tới workload đang chạy đều phải được đánh giá.

## 2. Chuẩn bị file và cấu trúc đích

Trước khi nạp, thống nhất hợp đồng file với hệ thống xuất dữ liệu:

- Encoding, thường là `utf8mb4`, và cách xử lý BOM.
- Dấu phân tách cột, dấu bao chuỗi, ký tự escape và ký tự kết thúc dòng.
- Quy tắc biểu diễn `NULL`, chuỗi rỗng, ngày giờ, số thập phân và dấu phân cách hàng nghìn.
- Header có hay không; thứ tự và tên cột có ổn định không.
- Quy tắc về dấu nháy, xuống dòng bên trong trường văn bản và ký tự xuống dòng `LF` hoặc `CRLF`.
- Khóa định danh để phát hiện trùng và mã dòng nguồn để truy vết dữ liệu lỗi.

Không suy đoán định dạng từ vài dòng đầu. Hãy kiểm tra cả các trường hợp biên: chuỗi có dấu phẩy, dấu nháy, ký tự xuống dòng, dấu tiếng Việt, giá trị rỗng, ngày không hợp lệ và số thập phân có nhiều chữ số.

Ví dụ file CSV:

```csv
source_line_no,order_id,customer_id,amount,order_date
1,10001,501,125000.00,2026-11-18
2,10002,502,89000.50,2026-11-18
3,10003,503,invalid,2026-11-18
```

`source_line_no` được hệ thống xuất thêm để có thể xác định dòng gốc khi cần cách ly hoặc yêu cầu gửi lại. Nếu nguồn không cung cấp mã dòng, nên tạo một định danh ổn định trong bước tiền xử lý; không dựa vào số thứ tự byte vì một bản ghi CSV có thể chứa xuống dòng bên trong trường được bao dấu nháy.

Định nghĩa bảng đích với kiểu dữ liệu và ràng buộc phù hợp:

```sql
CREATE TABLE orders (
  order_id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  amount DECIMAL(14,2) NOT NULL,
  order_date DATE NOT NULL,
  PRIMARY KEY (order_id),
  KEY idx_orders_customer_date (customer_id, order_date)
) ENGINE=InnoDB;
```

Kiểu `DECIMAL` phù hợp với số tiền cần độ chính xác thập phân. Dùng kiểu ngày giờ phù hợp với ngữ nghĩa dữ liệu, tránh lưu ngày dưới dạng chuỗi chỉ để việc import dễ hơn. Ràng buộc khóa chính và unique index là lớp bảo vệ cuối cùng chống dữ liệu trùng, kể cả khi bước kiểm tra ở ứng dụng có lỗi.

## 3. LOAD DATA INFILE và LOAD DATA LOCAL INFILE

### File nằm trên máy chủ MySQL

Ví dụ:

```sql
LOAD DATA INFILE '/var/lib/mysql-files/orders.csv'
INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@source_line_no, order_id, customer_id, amount, order_date);
```

Trong ví dụ, file phải tồn tại tại đường dẫn mà tiến trình MySQL đọc được. Tài khoản chạy lệnh cần quyền `FILE` theo yêu cầu của phiên bản và thư mục có thể bị giới hạn bởi `secure_file_priv`. Kiểm tra cấu hình:

```sql
SHOW VARIABLES LIKE 'secure_file_priv';
```

Nếu `secure_file_priv` trả về một đường dẫn, thao tác import/export phía server thường bị giới hạn trong thư mục đó. Nếu giá trị là `NULL`, thao tác file phía server bị vô hiệu hóa; giá trị rỗng có nghĩa không giới hạn bởi biến này. Hãy tuân theo chính sách bảo mật của môi trường và không nới lỏng đường dẫn chỉ để import một file.

### File nằm trên máy client

Ví dụ:

```sql
LOAD DATA LOCAL INFILE '/secure/import/orders.csv'
INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@source_line_no, order_id, customer_id, amount, order_date);
```

Với `LOCAL`, đường dẫn được đọc bởi chương trình client, sau đó nội dung file được gửi tới server. Server và client phải cho phép tính năng này; biến `local_infile` và cờ hỗ trợ của driver/client cần được kiểm tra. Chỉ bật cho ứng dụng và môi trường tin cậy. Vì server có thể yêu cầu client gửi file trong quá trình kết nối, cần dùng client/driver đáng tin cậy, giới hạn quyền và bảo vệ kết nối bằng TLS khi truyền qua mạng.

`LOCAL` có một khác biệt quan trọng về xử lý lỗi: MySQL xử lý lỗi diễn giải dữ liệu và duplicate-key theo hướng tương tự `IGNORE`, nên một số dòng lỗi có thể bị chuyển thành warning và lệnh vẫn tiếp tục. Đừng giả định `LOCAL` và non-`LOCAL` có cùng hành vi khi strict SQL mode đang bật. Hãy kiểm thử với đúng phiên bản, driver, `sql_mode` và dữ liệu thực tế.

### Ánh xạ và chuyển đổi cột

File không nhất thiết có cùng thứ tự cột với bảng. Có thể nạp vào biến người dùng rồi chuyển đổi qua `SET`:

```sql
LOAD DATA LOCAL INFILE '/secure/import/orders.csv'
INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@line_no, @order_id, @customer_id, @amount, @order_date)
SET
  order_id = NULLIF(@order_id, ''),
  customer_id = NULLIF(@customer_id, ''),
  amount = NULLIF(@amount, ''),
  order_date = STR_TO_DATE(@order_date, '%Y-%m-%d');
```

Ví dụ này minh họa ánh xạ và chuyển đổi; nếu bảng đích khai báo `NOT NULL`, giá trị rỗng được chuyển thành `NULL` sẽ bị từ chối hoặc phát warning tùy chế độ và ngữ cảnh. Đối với quy trình cần kiểm soát lỗi từng dòng, nên nạp giá trị gốc vào staging dạng chuỗi trước, sau đó mới kiểm tra và chuyển kiểu. Như vậy dữ liệu gốc không bị mất khi chuyển đổi thất bại.

## 4. Nạp vào staging thay vì bảng nghiệp vụ trực tiếp

Staging là vùng tiếp nhận dữ liệu thô. Các cột nguồn được lưu dưới dạng chuỗi đủ rộng, kèm mã batch và mã dòng nguồn. Sau khi nạp, có thể kiểm tra định dạng, phát hiện trùng, phân loại lỗi và chỉ đưa dữ liệu hợp lệ vào bảng nghiệp vụ.

Ví dụ:

```sql
CREATE TABLE import_stage_orders (
  batch_id BIGINT UNSIGNED NOT NULL,
  source_line_no VARCHAR(32) NOT NULL,
  order_id_raw VARCHAR(64),
  customer_id_raw VARCHAR(64),
  amount_raw VARCHAR(64),
  order_date_raw VARCHAR(64),
  loaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (batch_id, source_line_no)
) ENGINE=InnoDB;
```

Nạp dữ liệu thô:

```sql
LOAD DATA LOCAL INFILE '/secure/import/orders.csv'
INTO TABLE import_stage_orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@line_no, @order_id, @customer_id, @amount, @order_date)
SET
  batch_id = 2026111901,
  source_line_no = @line_no,
  order_id_raw = @order_id,
  customer_id_raw = @customer_id,
  amount_raw = @amount,
  order_date_raw = @order_date;
```

Mã batch là ví dụ. Trong hệ thống thực tế, tạo mã duy nhất cho mỗi lần nhận file và lưu metadata như tên file, checksum, thời điểm nhận, nguồn gửi, số dòng kỳ vọng và trạng thái. Khóa `(batch_id, source_line_no)` giúp ngăn nạp lặp cùng dòng nếu nguồn đảm bảo số dòng ổn định.

Staging giúp phân biệt ba trạng thái:

- **Loaded:** dòng đã được nhận vào staging, chưa kết luận hợp lệ.
- **Accepted:** dòng vượt qua kiểm tra và được chuyển vào bảng đích.
- **Rejected:** dòng không hợp lệ hoặc vi phạm quy tắc nghiệp vụ, được giữ lại cùng lý do.

Không xóa file nguồn hoặc staging ngay sau khi `LOAD DATA` trả về thành công. Chỉ chuyển trạng thái batch sang hoàn tất sau khi đối soát số dòng, xử lý warning và xác minh dữ liệu đích.

## 5. Bỏ dòng lỗi có kiểm soát

MySQL có thể tiếp tục nạp khi dùng `IGNORE` trong các trường hợp được hỗ trợ, nhưng `IGNORE` không phải hệ thống quarantine. Nó không tự lưu đầy đủ nội dung dòng bị bỏ cùng lý do để đội vận hành xử lý sau đó.

Các trường hợp lỗi thường gặp:

| Loại lỗi | Ví dụ | Cách xử lý đề xuất |
|---|---|---|
| Sai kiểu dữ liệu | `amount=abc`, ngày sai định dạng | Nạp raw vào staging, kiểm tra cú pháp trước khi CAST/STR_TO_DATE |
| Vượt giới hạn | Chuỗi dài hơn cột `VARCHAR`, số vượt precision của `DECIMAL` | Xác định giới hạn hợp đồng nguồn; reject hoặc sửa mapping có kiểm soát |
| Thiếu giá trị bắt buộc | `order_id` rỗng hoặc `NULL` | Reject với lý do rõ ràng; không tự thay bằng 0 |
| Khóa trùng | `order_id` đã tồn tại | Chọn quy tắc skip, update hay từ chối theo nghiệp vụ |
| Giá trị ngoài miền | `amount` âm, trạng thái không thuộc danh sách | Kiểm tra quy tắc nghiệp vụ ở staging |
| Quan hệ không hợp lệ | `customer_id` không tồn tại | Kiểm tra tham chiếu trước khi insert; lưu reject để xử lý nguồn |

Tạo bảng lưu dòng lỗi:

```sql
CREATE TABLE import_rejected_orders (
  batch_id BIGINT UNSIGNED NOT NULL,
  source_line_no VARCHAR(32) NOT NULL,
  order_id_raw VARCHAR(64),
  customer_id_raw VARCHAR(64),
  amount_raw VARCHAR(64),
  order_date_raw VARCHAR(64),
  reject_reason VARCHAR(255) NOT NULL,
  rejected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (batch_id, source_line_no)
) ENGINE=InnoDB;
```

Ví dụ phân loại dữ liệu lỗi theo cú pháp:

```sql
INSERT INTO import_rejected_orders (
  batch_id, source_line_no, order_id_raw,
  customer_id_raw, amount_raw, order_date_raw, reject_reason
)
SELECT
  batch_id,
  source_line_no,
  order_id_raw,
  customer_id_raw,
  amount_raw,
  order_date_raw,
  CASE
    WHEN order_id_raw IS NULL OR order_id_raw NOT REGEXP '^[0-9]+$'
      THEN 'order_id không phải số nguyên dương'
    WHEN customer_id_raw IS NULL OR customer_id_raw NOT REGEXP '^[0-9]+$'
      THEN 'customer_id không phải số nguyên dương'
    WHEN amount_raw IS NULL OR amount_raw NOT REGEXP '^[0-9]+([.][0-9]{1,2})?$'
      THEN 'amount sai định dạng thập phân'
    WHEN order_date_raw IS NULL OR order_date_raw NOT REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
      THEN 'order_date sai định dạng YYYY-MM-DD'
    ELSE 'Không hợp lệ'
  END
FROM import_stage_orders
WHERE batch_id = 2026111901
  AND (
    order_id_raw IS NULL OR order_id_raw NOT REGEXP '^[0-9]+$'
    OR customer_id_raw IS NULL OR customer_id_raw NOT REGEXP '^[0-9]+$'
    OR amount_raw IS NULL OR amount_raw NOT REGEXP '^[0-9]+([.][0-9]{1,2})?$'
    OR order_date_raw IS NULL OR order_date_raw NOT REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
  );
```

Regex chỉ kiểm tra hình dạng chuỗi. Nó chưa chứng minh ngày có thật trong lịch, số nằm trong giới hạn kiểu đích hay customer tồn tại. Ví dụ `2026-02-31` có hình dạng đúng nhưng không phải ngày hợp lệ. Bổ sung kiểm tra chuyển kiểu, miền giá trị và tham chiếu trước khi đưa vào bảng nghiệp vụ.

Một cách kiểm tra số tiền và ngày trước khi insert:

```sql
SELECT
  source_line_no,
  amount_raw,
  order_date_raw,
  STR_TO_DATE(order_date_raw, '%Y-%m-%d') AS parsed_order_date
FROM import_stage_orders
WHERE batch_id = 2026111901;
```

Kiểm tra kết quả `parsed_order_date` là `NULL`, so sánh định dạng chuẩn hóa và áp dụng các giới hạn nghiệp vụ. Với dữ liệu ngày giờ có timezone, chuẩn hóa timezone theo hợp đồng nguồn trước khi ghi vào `DATETIME` hoặc `TIMESTAMP`.

Sau khi cách ly các dòng sai cú pháp, chuyển các dòng hợp lệ vào bảng đích:

```sql
INSERT INTO orders (order_id, customer_id, amount, order_date)
SELECT
  CAST(s.order_id_raw AS UNSIGNED),
  CAST(s.customer_id_raw AS UNSIGNED),
  CAST(s.amount_raw AS DECIMAL(14,2)),
  STR_TO_DATE(s.order_date_raw, '%Y-%m-%d')
FROM import_stage_orders AS s
WHERE s.batch_id = 2026111901
  AND s.order_id_raw REGEXP '^[0-9]+$'
  AND s.customer_id_raw REGEXP '^[0-9]+$'
  AND s.amount_raw REGEXP '^[0-9]+([.][0-9]{1,2})?$'
  AND s.order_date_raw REGEXP '^[0-9]{4}-[0-9]{2}-[0-9]{2}$';
```

Đây là bước minh họa. Trong production, bổ sung điều kiện ngày thực sự hợp lệ, kiểm tra giới hạn kiểu đích, tồn tại customer, duplicate và các quy tắc nghiệp vụ. Tốt nhất tạo một tập `accepted` đã được kiểm tra đầy đủ rồi mới insert, để cùng một điều kiện được dùng cho cả báo cáo số dòng và thao tác nạp.

## 6. Đọc warning ngay sau câu lệnh nạp

Sau `LOAD DATA`, MySQL trả về thông tin tổng hợp như số record đọc, số dòng bị thay thế, số dòng bị bỏ qua và số warning. Đừng chỉ kiểm tra exit code hoặc thông báo `Query OK`.

Ngay sau lệnh nạp, chạy:

```sql
SHOW COUNT(*) WARNINGS;
SHOW WARNINGS LIMIT 100;
```

`SHOW WARNINGS` hiển thị các điều kiện của câu lệnh gần nhất có phát sinh thông báo, gồm mức (`Warning`, `Error`, `Note`), mã lỗi và nội dung. Hãy lấy kết quả ngay sau lệnh import để gắn warning với đúng batch. Không chạy thêm thao tác import hoặc câu lệnh khác có thể thay thế diagnostics trước khi thu thập thông tin.

`max_error_count` giới hạn số condition được lưu để hiển thị trong diagnostics area; nó không giới hạn tổng số lỗi thực tế mà câu lệnh có thể gặp. Nếu số warning lớn hơn giới hạn lưu, `SHOW WARNINGS` chỉ hiển thị một phần. Có thể kiểm tra và điều chỉnh trong session trước khi import:

```sql
SHOW VARIABLES LIKE 'max_error_count';
SET SESSION max_error_count = 1000;
```

Chọn giới hạn vừa đủ cho quy mô batch và tài nguyên. Không đặt quá lớn một cách tùy tiện vì lưu nhiều diagnostics tiêu tốn bộ nhớ. Với file rất lớn, staging và kiểm tra theo batch giúp tránh phụ thuộc vào một danh sách warning có thể bị giới hạn.

Ví dụ warning thường gặp:

| Mã/loại thông báo | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Data truncated | Giá trị bị cắt hoặc chuyển đổi không đầy đủ | Kiểm tra độ dài cột, precision, charset và dữ liệu nguồn |
| Incorrect date value | Chuỗi ngày không chuyển được theo định dạng đích | Chuẩn hóa định dạng, kiểm tra ngày tồn tại và timezone |
| Duplicate entry | Trùng khóa chính hoặc unique index | Xác định quy tắc nghiệp vụ cho duplicate; không bỏ qua mặc định |
| Invalid integer/decimal | Có ký tự không hợp lệ hoặc vượt miền | Kiểm tra raw value và reject dòng sai |
| Column count mismatch | Số trường file không khớp mapping | Kiểm tra delimiter, enclosure, escape và header |

Warning là bằng chứng cần điều tra. Một batch có thể nạp được phần lớn dòng nhưng vẫn sai về mặt nghiệp vụ. Ghi lại warning count, mẫu warning, số dòng đọc, số dòng được nhận và số dòng bị reject vào metadata của batch.

## 7. Phân biệt IGNORE, REPLACE và xử lý duplicate

`IGNORE` và `REPLACE` ảnh hưởng cách MySQL xử lý một số lỗi và xung đột khóa trong `LOAD DATA`:

- `IGNORE` có thể bỏ qua dòng gây duplicate-key và tiếp tục xử lý các dòng khác; các lỗi diễn giải dữ liệu trong các trường hợp được hỗ trợ có thể trở thành warning.
- `REPLACE` thay dòng xung đột bằng dòng mới. Về mặt hành vi, nó có thể xóa dòng cũ rồi chèn dòng mới, ảnh hưởng trigger, khóa ngoại và cột không có trong file.
- Không dùng modifier để thay thế quy tắc nghiệp vụ. Nếu dữ liệu mới cần cập nhật một phần cột của bản ghi cũ, hãy định nghĩa rõ thao tác upsert và các cột được phép cập nhật.

Ví dụ nạp có `IGNORE`:

```sql
LOAD DATA LOCAL INFILE '/secure/import/orders.csv'
IGNORE INTO TABLE orders
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(order_id, customer_id, amount, order_date);
```

Trong ví dụ, từ `IGNORE` sau `LOCAL INFILE` là modifier xử lý lỗi/duplicate; `IGNORE 1 LINES` ở cuối là chỉ thị bỏ qua dòng header. Hai cách dùng từ `IGNORE` có mục đích khác nhau.

Nếu cần bỏ qua duplicate, phải đo số dòng skipped và đối chiếu với danh sách khóa đã tồn tại. Nếu cần cập nhật bản ghi hiện có, cân nhắc nạp vào staging rồi dùng `INSERT ... ON DUPLICATE KEY UPDATE` với danh sách cột cập nhật rõ ràng. Nếu duplicate là lỗi nguồn, đưa chúng vào reject table và yêu cầu sửa file. Không dùng `REPLACE` khi chưa đánh giá tác động của việc xóa rồi chèn lại bản ghi.

## 8. Strict SQL mode và hành vi lỗi

Strict SQL mode ảnh hưởng việc MySQL xử lý giá trị không hợp lệ hoặc thiếu trong các thao tác ghi. Kiểm tra mode hiện tại:

```sql
SELECT @@SESSION.sql_mode;
SELECT @@GLOBAL.sql_mode;
```

Các mode như `STRICT_TRANS_TABLES` và `STRICT_ALL_TABLES` ảnh hưởng việc chuyển dữ liệu sai, thiếu hoặc vượt giới hạn. Hành vi cụ thể phụ thuộc storage engine, câu lệnh và việc dùng `LOCAL`, `IGNORE` hay `REPLACE`. Không tắt strict mode trên production chỉ để lệnh import chạy qua. Điều đó có thể biến lỗi dữ liệu thành giá trị mặc định hoặc giá trị bị cắt mà không có xử lý nghiệp vụ tương ứng.

Một quy trình an toàn nên thử nghiệm cùng file mẫu trên đúng phiên bản và cấu hình `sql_mode` production. Ghi lại kết quả của cả file hợp lệ lẫn file có lỗi: lệnh dừng hay tiếp tục, transaction có rollback không, warning nào xuất hiện và bao nhiêu dòng đã được ghi. Nếu cần bảo đảm một batch chỉ được publish khi toàn bộ bước kiểm tra thành công, hãy thực hiện bước chuyển từ staging sang bảng đích trong transaction InnoDB có kiểm soát và cập nhật trạng thái batch cùng transaction đó.

Không giả định `LOAD DATA LOCAL INFILE` có cùng ngữ nghĩa lỗi với `LOAD DATA INFILE` phía server. `LOCAL` có hành vi tương tự `IGNORE` đối với một số lỗi nhập liệu và duplicate-key. Đây là lý do staging raw và kiểm tra warning rất hữu ích: dữ liệu được tiếp nhận trước, sau đó quyết định rõ dòng nào được chấp nhận.

## 9. Chia batch, transaction và khả năng chạy lại

Một file rất lớn có thể làm tăng thời gian giữ tài nguyên, dung lượng undo/redo, replication lag và thời gian rollback. Chia file thành các batch theo ranh giới bản ghi hoàn chỉnh để:

- Giới hạn dung lượng staging và lượng redo phát sinh mỗi lần.
- Có checkpoint sau từng batch và biết chính xác batch nào thành công.
- Retry một batch lỗi mà không nạp lại toàn bộ dữ liệu.
- Giảm thời gian đối soát và cách ly dòng lỗi.
- Điều chỉnh tốc độ nạp theo tải của production và replica.

Mỗi batch nên có metadata:

| Trường | Mục đích |
|---|---|
| `batch_id` | Định danh duy nhất cho lần nạp |
| `source_file` | Tên hoặc định danh file gốc |
| `source_checksum` | Phát hiện file bị thay đổi khi retry |
| `expected_rows` | Số dòng dữ liệu kỳ vọng, không tính header |
| `loaded_rows` | Số dòng được nhận vào staging |
| `accepted_rows` | Số dòng chuyển vào bảng đích |
| `rejected_rows` | Số dòng cách ly |
| `warning_count` | Tổng warning được ghi nhận từ câu lệnh nạp |
| `status` | `RECEIVED`, `LOADED`, `VALIDATED`, `PUBLISHED`, `FAILED` |

Thiết kế thao tác idempotent: cùng một batch được gửi lại không được tạo bản ghi trùng hoặc cập nhật sai. Có thể dùng khóa batch/dòng nguồn, unique key nghiệp vụ, bảng checkpoint và transaction publish. Không đánh dấu batch `PUBLISHED` trước khi dữ liệu đích và số liệu đối soát đã được commit.

Ví dụ mô hình xử lý:

```text
Nhận file + checksum
        |
        v
Tạo batch_id / trạng thái RECEIVED
        |
        v
LOAD DATA vào staging
        |
        v
Thu thập warning + số dòng
        |
        v
Validate và phân loại
      /   \
     v     v
 Reject  Accepted
   |       |
   |       v
   |   Publish vào bảng đích
   |       |
   +---+---+
       v
  Đối soát batch
       |
       v
  PUBLISHED / FAILED
```

Nếu publish gồm nhiều thao tác trên các bảng InnoDB, cân nhắc gói chúng trong transaction để dữ liệu nghiệp vụ và trạng thái batch cùng commit. Với batch rất lớn, có thể publish theo chunk nhỏ hơn, mỗi chunk có checkpoint và khóa idempotency riêng. Quyết định này cần bảo đảm consumer không đọc trạng thái batch nửa chừng.

## 10. Đối soát sau import

Không kết luận thành công chỉ dựa trên việc câu lệnh không trả lỗi. So sánh các con số:

```text
expected_rows
  = loaded_rows + rows_rejected_before_staging (nếu có)

loaded_rows
  = accepted_rows + rejected_rows + rows_pending_review
```

Các phương trình trên là mô hình quản lý batch; cần định nghĩa rõ các dòng header, dòng trống, duplicate bị bỏ và lỗi file không thể parse để không đếm hai lần.

Kiểm tra số dòng trong staging:

```sql
SELECT COUNT(*) AS loaded_rows
FROM import_stage_orders
WHERE batch_id = 2026111901;
```

Kiểm tra số dòng bị reject:

```sql
SELECT COUNT(*) AS rejected_rows
FROM import_rejected_orders
WHERE batch_id = 2026111901;
```

Kiểm tra trùng khóa trong staging:

```sql
SELECT order_id_raw, COUNT(*) AS occurrences
FROM import_stage_orders
WHERE batch_id = 2026111901
GROUP BY order_id_raw
HAVING COUNT(*) > 1;
```

Kiểm tra bản ghi tham chiếu không tồn tại:

```sql
SELECT s.source_line_no, s.customer_id_raw
FROM import_stage_orders AS s
LEFT JOIN customers AS c
  ON c.customer_id = CAST(s.customer_id_raw AS UNSIGNED)
WHERE s.batch_id = 2026111901
  AND s.customer_id_raw REGEXP '^[0-9]+$'
  AND c.customer_id IS NULL;
```

Truy vấn đối soát phải chạy trên tập dữ liệu đã được kiểm tra kiểu để tránh CAST dữ liệu lỗi. Ngoài số lượng dòng, nên đối chiếu tổng tiền, min/max ngày, số khóa duy nhất và một số mẫu bản ghi. Với dữ liệu quan trọng, dùng checksum hoặc hash theo chunk và so sánh với phía nguồn.

## 11. Bảo mật khi import

File import có thể chứa dữ liệu cá nhân, thông tin thanh toán hoặc dữ liệu nghiệp vụ nhạy cảm. Áp dụng các biện pháp sau:

- Chỉ cho tài khoản import đọc file cần thiết; quyền `FILE` không nên cấp rộng.
- Giới hạn thư mục server-side bằng `secure_file_priv` và quyền filesystem.
- Chỉ bật `local_infile` cho client/ứng dụng đáng tin cậy; tắt khi không còn nhu cầu.
- Dùng TLS khi gửi file qua mạng và xác minh danh tính server ở client.
- Mã hóa file nguồn, staging, reject table và backup theo phân loại dữ liệu.
- Không ghi toàn bộ nội dung dòng nhạy cảm vào log warning, ticket hoặc log ứng dụng nếu không cần thiết.
- Thiết lập retention và xóa an toàn cho file nguồn, file đã giải mã, staging và reject sau khi hết thời hạn.
- Theo dõi người khởi chạy import, nguồn file, checksum, thời gian, số dòng và kết quả.

Không cho phép client bất kỳ nào bật `LOCAL` tùy ý trên một máy chủ chia sẻ. Tính năng này mở rộng khả năng server yêu cầu client gửi file trong phiên kết nối; cần giới hạn theo driver, tài khoản và nguồn kết nối.

## 12. Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| `LOAD DATA INFILE` báo không thể mở file | Đường dẫn server không nhìn thấy, quyền filesystem, `secure_file_priv` | Xác minh đường dẫn trên host MySQL, quyền đọc và giá trị `secure_file_priv` |
| `LOCAL INFILE` bị từ chối | Server hoặc client không bật hỗ trợ `local_infile`, driver chặn tính năng | Kiểm tra biến server, cờ client/driver và chính sách kết nối |
| Cột bị lệch dữ liệu | Sai delimiter, enclosure, escape hoặc dòng xuống hàng trong trường | Kiểm tra định dạng file, chỉ định `FIELDS`/`LINES` rõ và thử trên bản mẫu |
| Tiếng Việt bị lỗi ký tự | Charset nguồn không khớp hoặc BOM | Xác định encoding thực, chỉ định `CHARACTER SET`, xử lý BOM có kiểm soát |
| Ngày hoặc số bị chuyển sai | Format không thống nhất, locale hoặc decimal separator | Nạp raw vào staging, chuẩn hóa rồi chuyển kiểu |
| Nhiều dòng bị skip nhưng lệnh thành công | Duplicate, `IGNORE`, `LOCAL` hoặc lỗi chuyển đổi thành warning | Đọc `SHOW WARNINGS`, so sánh `Records/Skipped/Warnings` và cách ly dòng lỗi |
| `SHOW WARNINGS` thiếu dòng | Vượt `max_error_count` | Kiểm tra tổng warning, tăng giới hạn session hợp lý hoặc chia batch nhỏ |
| Retry tạo duplicate | Batch không idempotent hoặc thiếu unique key/checkpoint | Dùng batch ID, source row ID, checksum và quy tắc upsert rõ |
| Import làm replica chậm | Batch lớn, nhiều index, redo/binlog tăng nhanh | Chia batch, điều tiết tốc độ, theo dõi applier và tải I/O |

Khi import thất bại, giữ nguyên file gốc, batch metadata, thông báo tổng hợp và warning. Không chạy lại ngay với `IGNORE` hoặc `REPLACE` khi chưa biết số dòng đã ghi. Kiểm tra trạng thái staging và bảng đích, xác định thao tác trước đó có được rollback hay đã ghi một phần, sau đó mới quyết định resume, truncate staging của batch hay tạo batch mới.

## 13. Tình huống thực hành

Một hệ thống thương mại điện tử nhận file đơn hàng hàng ngày từ đối tác. File có 500.000 dòng, một số dòng có thể sai ngày, số tiền hoặc customer ID. Yêu cầu là nạp phần hợp lệ, giữ lại dòng lỗi để đối tác sửa, đồng thời không tạo đơn trùng khi file được gửi lại.

**Bước 1 — Nhận file.** Lưu file vào vùng nhập được kiểm soát, tính checksum, đếm số dòng dữ liệu, ghi tên file và tạo `batch_id`. Giữ nguyên bản gốc để phục vụ điều tra.

**Bước 2 — Nạp raw.** Dùng `LOAD DATA LOCAL INFILE` đưa các trường vào staging dạng chuỗi. Đọc warning ngay sau câu lệnh và lưu số liệu cùng batch metadata.

**Bước 3 — Kiểm tra.** Kiểm tra định dạng ID, số tiền, ngày, customer tồn tại, duplicate trong file và duplicate với bảng đích. Ghi dòng lỗi vào `import_rejected_orders` kèm `reject_reason`.

**Bước 4 — Publish.** Chuyển các dòng hợp lệ vào `orders` trong transaction hoặc các chunk có checkpoint. Unique key trên `order_id` bảo vệ chống trùng; quy tắc duplicate được quyết định rõ theo hợp đồng với đối tác.

**Bước 5 — Đối soát.** Xác nhận `loaded = accepted + rejected + pending_review`, so sánh tổng tiền và số đơn theo ngày với file nguồn, sau đó cập nhật trạng thái batch `PUBLISHED`.

**Bước 6 — Phản hồi lỗi.** Xuất danh sách dòng bị reject với mã dòng nguồn và lý do dễ hiểu để đối tác sửa. Khi nhận file sửa, dùng batch mới có liên kết tới batch trước và chỉ nạp lại các dòng được xác định cần sửa.

## 14. Checklist trước khi chạy import production

- [ ] Định dạng file, encoding, delimiter, enclosure, escape và line ending đã được xác nhận.
- [ ] Đã kiểm tra các trường hợp chuỗi có dấu phẩy, dấu nháy, xuống dòng, `NULL` và giá trị rỗng.
- [ ] Đã chọn `INFILE` hoặc `LOCAL INFILE` theo vị trí file và chính sách bảo mật.
- [ ] Quyền `FILE`, `secure_file_priv`, `local_infile` và quyền filesystem đã được kiểm tra.
- [ ] Đã nạp thử trên staging bằng đúng MySQL version, driver và `sql_mode` production.
- [ ] Đã đọc `SHOW WARNINGS` ngay sau import và ghi nhận giới hạn `max_error_count`.
- [ ] Có batch ID, checksum, số dòng kỳ vọng và checkpoint để retry an toàn.
- [ ] Dòng lỗi được lưu cùng nội dung nguồn và lý do reject.
- [ ] Duplicate có quy tắc rõ: từ chối, bỏ qua hay cập nhật có kiểm soát.
- [ ] Đã đối soát số dòng, khóa duy nhất, tổng tiền và các quy tắc nghiệp vụ.
- [ ] Đã đánh giá tác động redo/binlog, index, lock và replication lag khi nạp batch lớn.
- [ ] File nguồn, staging, reject và file SQL trung gian được bảo vệ và có retention.

Nạp theo lô an toàn không dừng ở việc đưa file vào MySQL. Hệ thống cần chứng minh được dòng nào đã nhận, dòng nào hợp lệ, dòng nào bị loại và vì sao. Kết hợp `LOAD DATA`, staging, diagnostics, reject table, batch ID và đối soát giúp quy trình vừa nhanh vừa có thể điều tra, chạy lại và kiểm soát chất lượng dữ liệu.

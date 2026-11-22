# Strict mode, lỗi chuyển đổi và nguy cơ dữ liệu bị cắt ngắn

MySQL có thể xử lý dữ liệu không phù hợp với kiểu cột theo hai hướng: từ chối câu lệnh bằng lỗi, hoặc điều chỉnh giá trị và tiếp tục kèm cảnh báo. Hành vi này phụ thuộc vào `sql_mode`, loại câu lệnh, storage engine và cách dùng các từ khóa như `IGNORE`. Nếu không bật strict mode hoặc ứng dụng bỏ qua cảnh báo, dữ liệu sai có thể được lưu dưới dạng đã bị cắt, ép kiểu hoặc thay bằng giá trị biên.

**Strict mode** giúp MySQL từ chối nhiều giá trị không hợp lệ thay vì âm thầm sửa chúng. Hai chế độ chính là `STRICT_TRANS_TABLES` và `STRICT_ALL_TABLES`. Với phần lớn ứng dụng giao dịch dùng InnoDB, strict mode là nền tảng quan trọng để phát hiện lỗi dữ liệu sớm. Tuy vậy, nó không thay thế validation ở ứng dụng, kiểm tra nghiệp vụ hoặc quy trình nhập dữ liệu có đối soát.

## 1. SQL mode ảnh hưởng đến cách MySQL xử lý dữ liệu

`sql_mode` là biến hệ thống chứa danh sách các chế độ điều khiển cú pháp SQL và một số quy tắc xử lý dữ liệu. Ngoài strict mode, danh sách có thể bao gồm các chế độ như `ONLY_FULL_GROUP_BY`, `NO_ZERO_DATE`, `NO_ZERO_IN_DATE`, `ERROR_FOR_DIVISION_BY_ZERO` và `NO_ENGINE_SUBSTITUTION`.

Strict mode tập trung vào các giá trị không hợp lệ hoặc thiếu khi ghi dữ liệu. Ví dụ:

- Chuỗi dài hơn giới hạn của `VARCHAR(n)`.
- Giá trị số nằm ngoài miền của kiểu cột.
- Chuỗi không thể chuyển đổi thành số theo yêu cầu của cột.
- Giá trị ngày giờ không hợp lệ hoặc thiếu giá trị bắt buộc.
- Không cung cấp giá trị cho cột `NOT NULL` không có default.

Khi strict mode áp dụng, MySQL thường trả lỗi và không chấp nhận giá trị. Khi strict mode không áp dụng, MySQL có thể điều chỉnh giá trị tới dạng gần nhất được phép, lưu giá trị đó và phát warning. Hành vi cụ thể còn phụ thuộc loại lỗi và ngữ cảnh câu lệnh.

## 2. Kiểm tra SQL mode hiện tại

SQL mode có phạm vi global và session. Kiểm tra cả hai:

```sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
```

Hoặc:

```sql
SHOW GLOBAL VARIABLES LIKE 'sql_mode';
SHOW SESSION VARIABLES LIKE 'sql_mode';
```

- `GLOBAL` là giá trị mặc định được áp dụng cho các kết nối mới.
- `SESSION` là danh sách chế độ của kết nối hiện tại; nó ảnh hưởng đến câu lệnh được thực thi trong session đó.

Một ứng dụng dùng connection pool có thể giữ nhiều kết nối được tạo ở các thời điểm khác nhau. Nếu cấu hình global thay đổi, các kết nối đang tồn tại không tự động nhận lại toàn bộ session state mới. Vì vậy, hãy kiểm tra `@@SESSION.sql_mode` từ chính kết nối mà ứng dụng đang sử dụng.

Giá trị mặc định của `sql_mode` thay đổi theo phiên bản MySQL và cách đóng gói. Không nên giả định máy phát triển, staging và production có cùng danh sách mode; hãy kiểm tra và quản lý cấu hình rõ ràng.

## 3. STRICT_TRANS_TABLES và STRICT_ALL_TABLES

Hai chế độ strict khác nhau chủ yếu ở cách xử lý bảng không hỗ trợ transaction:

| Tình huống | `STRICT_TRANS_TABLES` | `STRICT_ALL_TABLES` |
| --- | --- | --- |
| Bảng transactional như InnoDB gặp giá trị không hợp lệ | Câu lệnh bị lỗi; thay đổi của câu lệnh được rollback | Câu lệnh bị lỗi; thay đổi của câu lệnh được rollback |
| Bảng nontransactional gặp lỗi ở hàng đầu tiên | Câu lệnh bị lỗi | Câu lệnh bị lỗi |
| Bảng nontransactional gặp lỗi ở hàng sau trong một lệnh nhiều hàng | MySQL có thể điều chỉnh giá trị lỗi và tiếp tục với warning | Câu lệnh dừng tại lỗi; các hàng đã ghi trước đó có thể vẫn còn |

`STRICT_TRANS_TABLES` phù hợp với hệ thống dùng chủ yếu InnoDB. `STRICT_ALL_TABLES` yêu cầu nghiêm ngặt hơn đối với bảng nontransactional, nhưng không thể rollback các hàng mà engine không hỗ trợ transaction đã ghi trước khi gặp lỗi.

Đối với InnoDB, lỗi strict trong một câu lệnh nhiều hàng làm rollback phần thay đổi của câu lệnh đó; điều này không nhất thiết đồng nghĩa toàn bộ transaction chứa câu lệnh bị rollback. Ứng dụng cần xử lý lỗi và quyết định tiếp tục hay rollback transaction theo logic nghiệp vụ.

## 4. Ví dụ: chuỗi dài hơn giới hạn cột

Tạo bảng thử nghiệm:

```sql
CREATE TABLE strict_text_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(5) NOT NULL,
    note VARCHAR(100) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Chèn giá trị dài hơn 5 ký tự:

```sql
INSERT INTO strict_text_demo (code, note)
VALUES ('MYSQL2026', 'Giá trị vượt giới hạn cột code');
```

Khi session bật strict mode, MySQL trả lỗi dạng `Data too long for column 'code'` và không chèn hàng đó. Nếu strict mode không áp dụng, MySQL có thể cắt chuỗi còn phần vừa với cột và phát warning. Giá trị đã cắt có thể mất thông tin và thậm chí trùng với mã của một bản ghi khác.

Kiểm tra ngay sau thao tác:

```sql
SHOW WARNINGS;
SELECT * FROM strict_text_demo;
```

Nếu câu lệnh đã thất bại, bảng không có hàng mới. Nếu MySQL đã chấp nhận giá trị sau khi điều chỉnh, `SHOW WARNINGS` giúp phát hiện cảnh báo và `SELECT` cho biết dữ liệu thực tế được lưu.

## 5. Ví dụ: giá trị số sai miền hoặc không chuyển đổi được

Xét bảng có cột số nguyên không dấu:

```sql
CREATE TABLE strict_number_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity INT UNSIGNED NOT NULL,
    amount DECIMAL(8, 2) NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Một số đầu vào có vấn đề:

```sql
-- Số âm không nằm trong miền của INT UNSIGNED
INSERT INTO strict_number_demo (quantity, amount)
VALUES (-3, 10.00);

-- Chuỗi không phải biểu diễn số hợp lệ
INSERT INTO strict_number_demo (quantity, amount)
VALUES ('many', 10.00);
```

Trong strict mode, các giá trị không hợp lệ thường khiến câu lệnh thất bại. Khi strict mode không áp dụng, MySQL có thể điều chỉnh giá trị về biên hợp lệ hoặc giá trị thay thế, đồng thời phát warning. Không nên dựa vào phép ép kiểu ngầm để diễn giải dữ liệu từ file hoặc API.

Đối với `DECIMAL(p,s)`, cần phân biệt giá trị vượt miền với giá trị có nhiều chữ số thập phân hơn scale. Giá trị vượt miền có thể bị từ chối trong strict mode hoặc bị điều chỉnh kèm warning trong chế độ permissive. Giá trị có phần thập phân vượt scale có thể được làm tròn theo quy tắc chuyển đổi của MySQL; hãy kiểm tra kết quả và warning trên phiên bản mục tiêu thay vì mặc định rằng mọi trường hợp đều bị cắt theo cùng một cách.

## 6. Ví dụ: ngày giờ không hợp lệ

Ngày giờ có các quy tắc kiểm tra riêng. Ví dụ:

```sql
CREATE TABLE strict_date_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_date DATE NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO strict_date_demo (event_date)
VALUES ('2026-02-31');
```

Ngày 31 tháng 2 không phải ngày hợp lệ trong lịch. Với cấu hình strict và các mode ngày tháng tương ứng, MySQL từ chối giá trị. Trong cấu hình permissive hoặc có mode nới lỏng như `ALLOW_INVALID_DATES`, một số giá trị ngày có thể được chấp nhận hoặc điều chỉnh. `ALLOW_INVALID_DATES` chỉ thực hiện kiểm tra giới hạn cơ bản của tháng và ngày, không xác minh ngày có tồn tại trong tháng cụ thể hay không.

Các mode `NO_ZERO_DATE` và `NO_ZERO_IN_DATE` điều khiển việc chấp nhận ngày toàn số 0 hoặc thành phần ngày/tháng bằng 0. Chúng có tương tác với strict mode và trạng thái deprecated/khuyến nghị có thể thay đổi theo phiên bản. Với dữ liệu nghiệp vụ, nên dùng ngày hợp lệ, `NULL` khi chưa biết ngày nếu schema cho phép, hoặc một giá trị trạng thái riêng; tránh dùng `0000-00-00` như cách biểu diễn “không có ngày”.

## 7. Cảnh báo và lỗi khác nhau thế nào?

Khi một câu lệnh ghi dữ liệu hoàn tất, MySQL có thể trả về số hàng bị ảnh hưởng và số warning. Cần đọc cả hai thay vì chỉ kiểm tra câu lệnh có trả về thành công hay không.

```sql
INSERT IGNORE INTO strict_text_demo (code, note)
VALUES ('TOO-LONG-CODE', 'Thử nghiệm warning khi ghi dữ liệu');

SHOW COUNT(*) WARNINGS;
SHOW WARNINGS;
```

Trong ví dụ này, `IGNORE` có thể khiến lỗi độ dài được chuyển thành warning và giá trị `code` bị cắt để phù hợp với `VARCHAR(5)`. Đây là lý do cần đọc diagnostics ngay sau lệnh ghi và kiểm tra giá trị thực tế trong bảng.

`SHOW WARNINGS` phải được chạy ngay sau câu lệnh cần kiểm tra, trước khi thực hiện một câu lệnh khác làm thay đổi diagnostics area. Kết quả có các cột `Level`, `Code`, `Message`; `Level` có thể là `Warning`, `Note` hoặc `Error`.

Một số mã lỗi/cảnh báo thường gặp:

| Mã | Ý nghĩa thường gặp | Cần làm gì |
| ---: | --- | --- |
| `1264` | Giá trị số vượt miền | Kiểm tra kiểu, miền giá trị và dữ liệu nguồn |
| `1265` | Dữ liệu bị điều chỉnh/cắt trong quá trình chuyển đổi | Kiểm tra độ dài, kiểu và cảnh báo |
| `1366` | Giá trị không đúng định dạng cho kiểu cột | Kiểm tra dữ liệu đầu vào và phép chuyển đổi |
| `1406` | Dữ liệu quá dài cho cột | Điều chỉnh dữ liệu hoặc giới hạn schema có căn cứ |
| `1292` | Giá trị sai định dạng khi chuyển đổi, thường gặp với số/ngày giờ | Kiểm tra format và cách parse |

Mã và thông điệp cụ thể có thể phụ thuộc câu lệnh, phiên bản và loại cột. Hãy đọc cả `Code` lẫn `Message`; không viết logic xử lý chỉ dựa vào một chuỗi thông báo cố định.

## 8. IGNORE có thể làm strict mode bớt nghiêm ngặt

`INSERT IGNORE` và `UPDATE IGNORE` có thể chuyển một số lỗi thành warning để câu lệnh tiếp tục. Với giá trị không hợp lệ, MySQL có thể điều chỉnh về giá trị gần nhất được chấp nhận hoặc bỏ qua hàng tùy loại lỗi.

Ví dụ:

```sql
INSERT IGNORE INTO strict_text_demo (code, note)
VALUES ('TOO-LONG-CODE', 'Thử nghiệm IGNORE');

SHOW WARNINGS;
SELECT * FROM strict_text_demo;
```

Ngay cả khi session đang bật strict mode, `IGNORE` có thể khiến lỗi độ dài được hạ thành warning và chuỗi bị cắt để phù hợp cột. Vì vậy, `IGNORE` không phải cách an toàn để “bỏ qua lỗi không quan trọng”. Nó có thể làm dữ liệu sai được lưu mà pipeline vẫn báo thành công.

Chỉ dùng `IGNORE` khi đã định nghĩa rõ cách xử lý từng loại lỗi, có kiểm tra warning, số hàng được thêm/cập nhật/bỏ qua và có khả năng đối soát dữ liệu nguồn. Nếu mục tiêu chỉ là tránh lỗi duplicate key, hãy cân nhắc cách xử lý xung đột rõ ràng như `ON DUPLICATE KEY UPDATE` thay vì che tất cả loại lỗi bằng `IGNORE`.

## 9. STRICT mode và LOAD DATA

Khi nạp CSV hoặc file văn bản, `LOAD DATA` cũng chịu ảnh hưởng của SQL mode và các tùy chọn `IGNORE`/`REPLACE`. Dữ liệu sai định dạng, quá dài hoặc không chuyển đổi được có thể gây lỗi hoặc warning tùy mode và câu lệnh.

Ví dụ nạp file vào bảng đích:

```sql
LOAD DATA LOCAL INFILE '/path/to/customers.csv'
INTO TABLE strict_text_demo
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
(code, note);
```

Đường dẫn file, quyền `LOCAL INFILE`, cấu hình client/server và format file cần được điều chỉnh theo môi trường. Sau khi nạp, kiểm tra số hàng, warning và dữ liệu thực tế:

```sql
SHOW COUNT(*) WARNINGS;
SHOW WARNINGS LIMIT 50;
SELECT COUNT(*) FROM strict_text_demo;
```

Không nạp thẳng dữ liệu không tin cậy vào bảng nghiệp vụ chỉ vì `LOAD DATA` chạy nhanh. Với file bên ngoài, một quy trình an toàn thường nạp vào staging table, kiểm tra định dạng và miền giá trị, phân loại hàng lỗi, sau đó mới chuyển các hàng hợp lệ vào bảng chính.

## 10. Phạm vi thay đổi SQL mode

### 10.1. Thay đổi trong session

Có thể đặt mode cho kết nối hiện tại:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

SELECT @@SESSION.sql_mode;
```

Lệnh trên thay thế toàn bộ danh sách mode của session bằng danh sách được chỉ định. Nó là ví dụ tối giản để minh họa, không nên sao chép vào ứng dụng nếu dự án đang cần các mode khác như `ONLY_FULL_GROUP_BY`. Trước khi thay đổi, hãy đọc danh sách hiện tại và xây dựng danh sách đích đầy đủ.

Thay đổi session chỉ tồn tại trong kết nối đó. Khi connection pool tạo kết nối mới, session nhận giá trị global tại thời điểm tạo hoặc cấu hình session mà ứng dụng khởi tạo.

### 10.2. Thay đổi global

Quản trị viên có thể thay đổi giá trị mặc định cho kết nối mới:

```sql
SET GLOBAL sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';

SELECT @@GLOBAL.sql_mode;
```

Lệnh này cũng thay thế toàn bộ danh sách mode global. Các session đang tồn tại không tự động đổi theo. Quyền cần thiết phụ thuộc phiên bản MySQL; các phiên bản hiện đại dùng quyền quản trị biến hệ thống như `SYSTEM_VARIABLES_ADMIN` cho thao tác này.

`SET GLOBAL` không tự đảm bảo cấu hình còn nguyên sau restart. Để duy trì lâu dài, dùng option file hoặc cơ chế persist của phiên bản hỗ trợ.

### 10.3. Persist hoặc option file

Trên MySQL 8.0 hỗ trợ `SET PERSIST`, có thể lưu giá trị global để áp dụng sau restart:

```sql
SET PERSIST sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Hoặc cấu hình trong option file của server:

```ini
[mysqld]
sql-mode=STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION
```

Các ví dụ trên cố ý chỉ liệt kê hai mode để dễ đọc; trong hệ thống thực, hãy hợp nhất với toàn bộ mode cần thiết của phiên bản và ứng dụng. Khi dùng managed database, cấu hình có thể nằm trong parameter group hoặc công cụ quản trị của nhà cung cấp.

Sau khi thay đổi, kiểm tra `@@GLOBAL.sql_mode`, tạo một kết nối mới và kiểm tra `@@SESSION.sql_mode` từ kết nối đó. Với connection pool, cần recycle hoặc khởi tạo lại connection theo quy trình triển khai để bảo đảm các session nhận cấu hình mong muốn.

## 11. Ví dụ kiểm tra STRICT_TRANS_TABLES trong thực tế

Trong môi trường lab, ghi lại mode hiện tại trước khi thử:

```sql
SELECT @@SESSION.sql_mode;
```

Đặt mode strict tối thiểu cho session lab:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
```

Thử chèn chuỗi quá dài:

```sql
INSERT INTO strict_text_demo (code, note)
VALUES ('LONGER-THAN-FIVE', 'Thử strict mode');
```

Quan sát lỗi và kiểm tra bảng:

```sql
SELECT * FROM strict_text_demo;
```

Sau đó thử `INSERT IGNORE` và đọc warning ngay sau câu lệnh. So sánh kết quả với insert thông thường. Cuối cùng, phục hồi SQL mode ban đầu trong session bằng giá trị đã ghi lại ở bước đầu, hoặc đóng kết nối lab.

Không chạy các lệnh thay đổi SQL mode global trên môi trường dùng chung chỉ để thử nghiệm. Bài lab chỉ cần thay đổi session.

## 12. Quy trình nhập dữ liệu an toàn

Khi nhận dữ liệu từ API, CSV, hệ thống cũ hoặc người dùng, nên thực hiện các bước sau:

1. **Xác định hợp đồng dữ liệu:** kiểu, độ dài, miền giá trị, timezone, định dạng ngày giờ và ý nghĩa `NULL`.
2. **Kiểm tra ở đầu vào:** validate dữ liệu theo hợp đồng trước khi ghi vào database.
3. **Dùng strict mode:** để MySQL từ chối các chuyển đổi không hợp lệ còn sót lại.
4. **Ưu tiên chuyển đổi tường minh:** dùng `CAST`, `CONVERT`, `STR_TO_DATE` hoặc logic chuẩn hóa có kiểm tra; không dựa vào ép kiểu ngầm.
5. **Tách dữ liệu thô:** nạp file không tin cậy vào staging table với cột đủ rộng hoặc kiểu văn bản phù hợp.
6. **Phân loại hàng lỗi:** ghi lại lý do, dòng nguồn và giá trị lỗi; không âm thầm bỏ dữ liệu.
7. **Chuyển hàng hợp lệ:** insert vào bảng nghiệp vụ bằng câu lệnh có kiểm soát và transaction khi phù hợp.
8. **Đối soát:** so sánh số hàng đầu vào, hợp lệ, bị từ chối, được thêm mới và được cập nhật.
9. **Lưu dấu vết:** ghi lại phiên bản schema, SQL mode, nguồn file và thời điểm chạy import.

Ví dụ một bảng staging đơn giản:

```sql
CREATE TABLE customer_import_stage (
    source_row BIGINT UNSIGNED NOT NULL,
    raw_email TEXT,
    raw_age TEXT,
    raw_created_at TEXT,
    PRIMARY KEY (source_row)
) ENGINE=InnoDB;
```

Sau khi nạp dữ liệu, có thể tìm giá trị tuổi không chuyển thành số hợp lệ:

```sql
SELECT source_row, raw_age
FROM customer_import_stage
WHERE raw_age IS NOT NULL
  AND TRIM(raw_age) <> ''
  AND TRIM(raw_age) NOT REGEXP '^[0-9]+$';
```

Với MySQL 8.0, có thể dùng `REGEXP_LIKE` thay cho toán tử `REGEXP` nếu muốn biểu đạt điều kiện rõ hơn. Kiểm tra định dạng trước khi `CAST` giúp tránh việc một chuỗi sai bị chuyển thành số 0 hoặc một giá trị khác ngoài ý muốn.

## 13. Xử lý dữ liệu lỗi bằng chuyển đổi tường minh

Không nên ghi trực tiếp dữ liệu thô vào cột có kiểu chặt nếu chưa xác nhận định dạng. Ví dụ, nếu ngày trong file có định dạng `DD/MM/YYYY`, hãy parse bằng `STR_TO_DATE` với format rõ ràng:

```sql
SELECT
    source_row,
    raw_created_at,
    STR_TO_DATE(raw_created_at, '%d/%m/%Y') AS parsed_date
FROM customer_import_stage;
```

Sau đó kiểm tra kết quả `NULL`, warning và quy tắc ngày hợp lệ trước khi insert. Không chỉ dựa vào việc `STR_TO_DATE` trả về giá trị; cần kiểm tra dữ liệu đầu vào có đúng format và không bị chuẩn hóa theo cách nghiệp vụ không mong muốn.

Với số thập phân, có thể dùng `CAST` sau khi xác thực dấu phân cách và miền giá trị. File CSV có thể dùng dấu phẩy làm dấu thập phân hoặc dấu phân cách hàng nghìn; cần chuẩn hóa format trước khi parse. Không dùng `REPLACE()` một cách mù quáng vì dấu phẩy có thể là dấu thập phân ở nguồn này và dấu phân cách cột ở nguồn khác.

## 14. Kiểm tra warning và đối soát trong ứng dụng

Ứng dụng nên coi warning là tín hiệu cần kiểm tra đối với các luồng ghi dữ liệu quan trọng. Tùy driver, warning có thể được lấy qua câu lệnh SQL hoặc API diagnostics tương ứng.

Một quy trình tối thiểu sau import:

```sql
SHOW COUNT(*) WARNINGS;
SHOW WARNINGS LIMIT 100;
```

Hãy chạy ngay sau câu lệnh ghi dữ liệu cần kiểm tra. Với import nhiều batch, cần thu thập warning và số hàng theo từng batch; không chỉ xem warning của batch cuối cùng.

Đối soát ít nhất các con số sau:

| Chỉ số | Ý nghĩa |
| --- | --- |
| Rows received | Số hàng nguồn đã nhận |
| Rows validated | Số hàng qua kiểm tra định dạng và nghiệp vụ |
| Rows rejected | Số hàng bị từ chối, kèm lý do |
| Rows inserted | Số hàng được thêm mới |
| Rows updated | Số hàng được cập nhật |
| Warnings | Số và loại cảnh báo MySQL phát ra |

Nếu hệ thống chỉ ghi nhận câu lệnh thành công mà không kiểm tra warning hoặc số hàng, dữ liệu bị cắt có thể lọt qua pipeline mà không ai phát hiện.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Bật strict mode là mọi dữ liệu sai đều bị từ chối trong mọi trường hợp | `IGNORE`, một số câu lệnh và khác biệt storage engine có thể làm thay đổi hành vi |
| `STRICT_TRANS_TABLES` và `STRICT_ALL_TABLES` giống nhau | Khác biệt quan trọng xuất hiện với bảng nontransactional và câu lệnh nhiều hàng |
| Warning không quan trọng nếu câu lệnh thành công | Warning có thể cho biết dữ liệu đã bị cắt, ép kiểu hoặc điều chỉnh |
| InnoDB rollback toàn bộ transaction khi một câu lệnh lỗi strict | Thông thường statement bị rollback; ứng dụng quyết định xử lý transaction tiếp theo |
| `INSERT IGNORE` chỉ bỏ qua duplicate key | Nó còn có thể hạ nhiều lỗi dữ liệu thành warning và điều chỉnh giá trị |
| Không có lỗi nghĩa là dữ liệu hợp lệ theo nghiệp vụ | MySQL chỉ kiểm tra theo kiểu, constraint và mode; quy tắc nghiệp vụ vẫn cần validation |
| Cấu hình global đổi là mọi kết nối đổi ngay | Session đang tồn tại giữ session state của nó |

## 16. Bài tập thực hành

1. Tạo bảng InnoDB có `VARCHAR(5)`, `INT UNSIGNED` và `DATE`; thử insert chuỗi dài, số âm và ngày không hợp lệ trong strict mode.
2. Chạy `SHOW WARNINGS` sau một câu lệnh được chấp nhận có warning; ghi lại `Level`, `Code`, `Message`.
3. Thử thay đổi `sql_mode` session để bỏ strict mode trong môi trường lab; quan sát giá trị được lưu và warning. Sau đó khôi phục mode ban đầu.
4. Thử `INSERT IGNORE` khi strict mode đang bật và giải thích vì sao kết quả khác insert thông thường.
5. So sánh `STRICT_TRANS_TABLES` và `STRICT_ALL_TABLES` trên bảng nontransactional trong một môi trường thử nghiệm riêng; kiểm tra các hàng đã ghi trước khi lỗi.
6. Nạp một file CSV có hàng hợp lệ và không hợp lệ vào staging table; phân loại hàng lỗi trước khi chuyển vào bảng chính.
7. Viết truy vấn kiểm tra dữ liệu số và ngày bằng biểu thức/format tường minh trước khi `CAST` hoặc `STR_TO_DATE`.
8. Thiết kế báo cáo import gồm số hàng nhận, hợp lệ, từ chối, insert, update và warning.

## 17. Ghi nhớ

Strict mode khiến MySQL từ chối nhiều giá trị không hợp lệ thay vì tự điều chỉnh và phát warning. `STRICT_TRANS_TABLES` áp dụng nghiêm ngặt cho bảng transactional và có cách xử lý riêng với lỗi ở các hàng sau của câu lệnh nhiều hàng trên bảng nontransactional; `STRICT_ALL_TABLES` dừng khi gặp lỗi nhưng không thể hoàn tác các hàng đã ghi bởi engine nontransactional.

`SHOW WARNINGS` cần được đọc ngay sau câu lệnh ghi dữ liệu. `INSERT IGNORE`, `UPDATE IGNORE` và một số luồng import có thể hạ lỗi thành warning hoặc điều chỉnh giá trị, vì vậy không nên dùng chúng để che lỗi dữ liệu. Hãy quản lý `sql_mode` theo session/global một cách có chủ đích, validate ở ứng dụng, chuyển đổi tường minh, dùng staging cho dữ liệu thô và đối soát cả số hàng lẫn warning trước khi coi một lần ghi/import là thành công.

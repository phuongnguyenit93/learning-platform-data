# Data too long, out of range, truncated value và strict mode

## Mục tiêu

MySQL có thể từ chối một câu lệnh khi dữ liệu vượt miền của cột, hoặc chuyển đổi và cắt bớt giá trị kèm warning tùy SQL mode và cách thực thi. Các tình huống như `Data too long`, `Out of range value` và `Data truncated` thường xuất hiện khi nhập dữ liệu, thay đổi schema hoặc kết nối ứng dụng với nguồn dữ liệu có kiểu khác. Nếu bỏ qua warning, hệ thống có thể lưu dữ liệu đã bị biến đổi mà ứng dụng vẫn báo thành công.

Bài học thuộc module **DATABASE_MYSQL**, bao quát thiết kế bảng, kiểu dữ liệu, khóa, SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Bài này hướng dẫn đọc lỗi chuyển đổi, hiểu strict SQL mode, kiểm tra miền dữ liệu trước khi ghi và xử lý an toàn khi nhập hoặc thay đổi kiểu cột.

Sau bài học, bạn có thể:

- Phân biệt lỗi vượt miền số, chuỗi quá dài và giá trị bị chuyển đổi/cắt bớt.
- Kiểm tra `sql_mode` ở cấp global và session, hiểu `STRICT_TRANS_TABLES` cùng `STRICT_ALL_TABLES`.
- Dùng `SHOW WARNINGS`, mã lỗi và truy vấn kiểm tra dữ liệu để tìm nguyên nhân.
- Xác định tác động của `INSERT IGNORE`, `UPDATE IGNORE`, `LOAD DATA` và strict mode.
- Làm sạch dữ liệu trong staging, sửa kiểu cột có kiểm soát và bảo vệ dữ liệu bằng constraint.

## 1. Ba nhóm lỗi cần phân biệt

| Nhóm | Ví dụ | Hành vi thường gặp |
|---|---|---|
| Data too long | Ghi chuỗi 20 ký tự vào `VARCHAR(8)` | Strict mode thường báo lỗi 1406; non-strict có thể cắt chuỗi và phát warning |
| Out of range | Ghi `256` vào `TINYINT UNSIGNED` hoặc `1000.00` vào `DECIMAL(5,2)` | Strict mode thường báo lỗi 1264; non-strict có thể ép về giá trị biên và phát warning |
| Data truncated / conversion | Chuyển chuỗi không hợp lệ sang số, ngày hoặc kiểu khác | Có thể báo lỗi hoặc warning 1265/1366/1292 tùy giá trị, ngữ cảnh và SQL mode |

Điều quan trọng là phân biệt **statement thất bại** với **statement hoàn tất nhưng có warning**. Một câu lệnh có warning vẫn có thể đã ghi giá trị sau khi MySQL cắt, làm tròn hoặc thay bằng giá trị biên. Vì vậy, kiểm tra số hàng bị ảnh hưởng thôi chưa đủ; cần kiểm tra warning và dữ liệu thực tế sau ghi.

## 2. Kiểm tra SQL mode

SQL mode điều khiển cách MySQL xử lý nhiều tình huống tương thích và chuyển đổi dữ liệu. Strict mode được bật khi `sql_mode` có `STRICT_TRANS_TABLES` hoặc `STRICT_ALL_TABLES`.

Kiểm tra cấu hình server và session hiện tại:

```sql
SELECT @@GLOBAL.sql_mode AS global_sql_mode,
       @@SESSION.sql_mode AS session_sql_mode;
```

`GLOBAL` là giá trị mặc định được dùng cho các session mới. `SESSION` là giá trị áp dụng cho kết nối hiện tại. Một connection pool có thể giữ session đã được tạo trước khi cấu hình global thay đổi; vì vậy, đổi global không nhất thiết cập nhật các connection đang tồn tại.

Trong nhiều bản MySQL 8.0, SQL mode mặc định bao gồm `STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, `NO_ZERO_IN_DATE`, `NO_ZERO_DATE`, `ERROR_FOR_DIVISION_BY_ZERO` và `NO_ENGINE_SUBSTITUTION`. Một số mode liên quan đến zero date đã bị deprecated trong các phiên bản mới; giá trị mặc định và mode còn hiệu lực phụ thuộc phiên bản. Luôn đọc giá trị thực tế và tài liệu của instance.

### `STRICT_TRANS_TABLES` và `STRICT_ALL_TABLES`

- `STRICT_TRANS_TABLES`: với bảng transactional như InnoDB, dữ liệu không hợp lệ khiến statement lỗi và được rollback. Với bảng nontransactional, hành vi có thể phụ thuộc vị trí hàng lỗi trong statement nhiều hàng; các hàng đã ghi không thể rollback.
- `STRICT_ALL_TABLES`: áp dụng strict behavior cho cả storage engine nontransactional. Tuy nhiên, storage engine không hỗ trợ rollback vẫn có thể giữ các hàng đã ghi trước khi lỗi xảy ra.

Trong ứng dụng dùng InnoDB, `STRICT_TRANS_TABLES` thường là lựa chọn mặc định phù hợp. Strict mode giúp phát hiện dữ liệu sai tại thời điểm ghi thay vì âm thầm biến đổi. Không tắt strict mode toàn server chỉ để một lần import hoàn tất.

## 3. Miền giá trị của kiểu số

Kiểu số có miền biểu diễn cụ thể. Giá trị nằm ngoài miền có thể gây lỗi hoặc bị ép về biên tùy SQL mode.

| Kiểu | Miền giá trị |
|---|---:|
| `TINYINT` signed | -128 đến 127 |
| `TINYINT UNSIGNED` | 0 đến 255 |
| `SMALLINT` signed | -32,768 đến 32,767 |
| `SMALLINT UNSIGNED` | 0 đến 65,535 |
| `INT` signed | -2,147,483,648 đến 2,147,483,647 |
| `INT UNSIGNED` | 0 đến 4,294,967,295 |
| `BIGINT` signed | -2^63 đến 2^63 - 1 |
| `BIGINT UNSIGNED` | 0 đến 2^64 - 1 |

`UNSIGNED` mở rộng miền dương nhưng loại bỏ số âm. Không đổi cột sang `UNSIGNED` chỉ để tăng giới hạn tối đa nếu dữ liệu hoặc nghiệp vụ có thể chứa số âm.

### `DECIMAL(M,D)`

`DECIMAL(M,D)` lưu số thập phân chính xác, trong đó `M` là tổng số chữ số và `D` là số chữ số sau dấu thập phân. Ví dụ `DECIMAL(5,2)` có miền từ `-999.99` đến `999.99`.

- `999.99` nằm trong miền.
- `1000.00` vượt miền vì cần bốn chữ số phần nguyên.
- `12.345` có nhiều chữ số thập phân hơn scale 2; MySQL chuyển đổi theo quy tắc làm tròn của kiểu đích, vì vậy cần kiểm tra kết quả thay vì giả định nó bị cắt đơn giản.

Với tiền tệ, chọn precision/scale theo giới hạn nghiệp vụ và quy tắc làm tròn. Không dùng `FLOAT` hoặc `DOUBLE` để thay cho số thập phân chính xác khi cần đối soát tiền.

## 4. Chuỗi quá dài: `VARCHAR`, `CHAR` và `TEXT`

`VARCHAR(n)` giới hạn theo số ký tự, không phải số byte. Với `utf8mb4`, một ký tự có thể chiếm tối đa bốn byte. Dù vậy, độ dài hàng và giới hạn index vẫn bị chi phối bởi số byte, row format và cấu hình InnoDB.

Ví dụ:

```sql
CREATE TABLE import_probe (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  code VARCHAR(8) CHARACTER SET utf8mb4 NOT NULL
) ENGINE = InnoDB;

INSERT INTO import_probe (code) VALUES ('ABC12345');
```

Chuỗi có 8 ký tự phù hợp. Chuỗi `ABCDEFGHI` có 9 ký tự và vượt giới hạn.

Kiểm tra độ dài dữ liệu:

```sql
SELECT code,
       CHAR_LENGTH(code) AS character_count,
       LENGTH(code) AS byte_count
FROM import_probe;
```

`CHAR_LENGTH()` đếm ký tự; `LENGTH()` đếm byte. Với dữ liệu Unicode, hai giá trị có thể khác nhau đáng kể. Khi xác minh dữ liệu nguồn trước khi nạp vào `VARCHAR(n)`, dùng `CHAR_LENGTH()` để kiểm tra giới hạn ký tự; dùng `LENGTH()`/`OCTET_LENGTH()` để đánh giá kích thước byte và các giới hạn lưu trữ liên quan.

Nếu dữ liệu thực sự cần dài hơn, cân nhắc tăng `VARCHAR(n)` hoặc dùng `TEXT` phù hợp. `TEXT` có các cấp dung lượng khác nhau (`TINYTEXT`, `TEXT`, `MEDIUMTEXT`, `LONGTEXT`), nhưng kích thước thực tế còn chịu giới hạn packet, bộ nhớ, row format và cách truy vấn. Không đổi mọi cột sang `LONGTEXT` để né lỗi vì điều đó làm yếu mô hình dữ liệu và có thể ảnh hưởng index, sort, memory và hiệu năng.

## 5. Tái hiện lỗi trong strict mode

Tạo bảng lab:

```sql
CREATE DATABASE IF NOT EXISTS strict_mode_lab;
USE strict_mode_lab;

CREATE TABLE values_probe (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  qty TINYINT UNSIGNED NOT NULL,
  amount DECIMAL(5,2) NOT NULL,
  code VARCHAR(4) CHARACTER SET utf8mb4 NOT NULL
) ENGINE = InnoDB;
```

Kiểm tra mode đang dùng:

```sql
SELECT @@SESSION.sql_mode;
```

Với strict mode bật, thử ghi số vượt miền:

```sql
INSERT INTO values_probe (qty, amount, code)
VALUES (256, 12.34, 'ABCD');
```

MySQL thường trả lỗi `1264` (`Out of range value`) cho `qty`. Với InnoDB, statement thất bại và không thêm hàng.

Thử chuỗi quá dài:

```sql
INSERT INTO values_probe (qty, amount, code)
VALUES (10, 12.34, 'ABCDE');
```

MySQL thường trả lỗi `1406` (`Data too long for column 'code'`). Không có hàng mới được thêm bởi statement thất bại.

Kiểm tra dữ liệu:

```sql
SELECT * FROM values_probe;
```

## 6. Quan sát hành vi non-strict mode trong lab

Để hiểu vì sao warning nguy hiểm, có thể tạm đổi SQL mode trong **session thử nghiệm riêng**. Lưu lại mode ban đầu:

```sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = '';
```

Thử ghi giá trị vượt miền:

```sql
INSERT INTO values_probe (qty, amount, code)
VALUES (256, 12.34, 'ABCD');

SHOW WARNINGS;
```

Trong non-strict mode, MySQL có thể ép `qty` về giá trị biên `255` và phát warning. Kiểm tra giá trị đã lưu:

```sql
SELECT *
FROM values_probe
ORDER BY id DESC
LIMIT 1;
```

Thử chuỗi quá dài:

```sql
INSERT INTO values_probe (qty, amount, code)
VALUES (10, 12.34, 'ABCDE');

SHOW WARNINGS;
```

Trong non-strict mode, MySQL có thể lưu phần chuỗi vừa với cột và phát warning. Kết quả có thể là `ABCD`, không phải chuỗi nguồn `ABCDE`.

Khôi phục mode session:

```sql
SET SESSION sql_mode = @saved_sql_mode;
```

Đây chỉ là thí nghiệm để quan sát hành vi chuyển đổi. Không dùng `sql_mode = ''` trong production hoặc pipeline nhập dữ liệu thật.

## 7. `INSERT IGNORE` và `UPDATE IGNORE`

`IGNORE` có thể hạ một số lỗi chuyển đổi dữ liệu thành warning và tiếp tục statement. Ví dụ:

```sql
INSERT IGNORE INTO values_probe (qty, amount, code)
VALUES (300, 10.00, 'TOOLONG');

SHOW WARNINGS;
```

Ngay cả khi strict mode được bật, `IGNORE` có thể khiến giá trị sai được chuyển đổi thành giá trị gần nhất có thể lưu và statement tiếp tục. Đây là hành vi cần hiểu rõ trước khi dùng trong import.

`INSERT IGNORE` còn có thể bỏ qua hàng vi phạm unique key hoặc chuyển một số lỗi thành warning. `UPDATE IGNORE` có hành vi tương tự đối với các lỗi có thể chuyển đổi. Không dùng `IGNORE` như cách “bỏ qua dữ liệu xấu” mà không có báo cáo và quy trình xử lý.

Nếu nghiệp vụ cho phép bỏ qua bản ghi lỗi, hãy lưu lại từng hàng bị loại, nguyên nhân và dữ liệu nguồn trong bảng reject/quarantine để có thể sửa và nạp lại. Không để warning biến mất trong log ứng dụng.

## 8. Warning phải được đọc ngay sau statement

MySQL cung cấp `SHOW WARNINGS` để xem warning và error của statement vừa chạy trong session hiện tại:

```sql
INSERT INTO values_probe (qty, amount, code)
VALUES (10, 10.00, 'ABCDE');

SHOW COUNT(*) WARNINGS;
SHOW WARNINGS;
```

Hãy chạy `SHOW WARNINGS` ngay sau câu lệnh cần kiểm tra, trước khi chạy câu SQL khác có thể thay đổi danh sách diagnostics. `SHOW COUNT(*) WARNINGS` cho biết số warning được ghi nhận; `SHOW WARNINGS` hiển thị level, code và message. Số dòng hiển thị bị giới hạn bởi `max_error_count`, vì vậy không nên giả định mọi warning đều xuất hiện nếu lô có quá nhiều lỗi.

Mã lỗi thường gặp:

| Mã | Ý nghĩa thường gặp | Hướng điều tra |
|---:|---|---|
| `1406` | Data too long for column | Độ dài nguồn, kiểu/độ dài đích, encoding |
| `1264` | Out of range value | Miền số, dấu, precision/scale |
| `1265` | Data truncated for column | Chuyển đổi hoặc cắt dữ liệu |
| `1366` | Incorrect value for column | Chuỗi không chuyển được sang kiểu đích hoặc ký tự không hợp lệ |
| `1292` | Incorrect date/time value hoặc conversion | Định dạng ngày giờ, timezone, SQL mode |

Mã cụ thể có thể thay đổi theo ngữ cảnh và phiên bản; đọc message đầy đủ cùng SQLSTATE và vị trí cột thay vì chỉ dựa vào mã.

## 9. Strict mode với bảng transactional và nontransactional

InnoDB hỗ trợ rollback. Khi strict mode phát hiện giá trị không hợp lệ trong một statement ghi InnoDB, statement thường thất bại và thay đổi của statement được rollback.

Với storage engine nontransactional, dữ liệu đã ghi không thể rollback. Trong một statement nhiều hàng, lỗi có thể xảy ra sau khi một số hàng đã được ghi. `STRICT_TRANS_TABLES` có quy tắc xử lý khác nhau tùy lỗi xảy ra ở hàng đầu hay hàng sau; `STRICT_ALL_TABLES` áp dụng strict behavior cho tất cả engine nhưng không thể hoàn tác dữ liệu nontransactional đã ghi trước lỗi.

Do đó:

- Ưu tiên InnoDB cho bảng nghiệp vụ cần tính nguyên tử.
- Không dựa vào một statement bulk insert như một transaction nguyên tử nếu bảng dùng engine nontransactional.
- Sau lỗi import, kiểm tra số hàng đã ghi và trạng thái dữ liệu; không chỉ nhìn exception.
- Dùng staging InnoDB để kiểm tra, chuẩn hóa và chuyển dữ liệu sang bảng đích.

## 10. Ngày giờ không hợp lệ và SQL mode

Ngày giờ cũng có thể bị từ chối hoặc chuyển đổi tùy SQL mode và phiên bản. Các mode từng được dùng để điều khiển trường hợp này gồm `NO_ZERO_DATE`, `NO_ZERO_IN_DATE` và `ALLOW_INVALID_DATES`; hai mode zero-date đã bị deprecated trong các phiên bản MySQL mới. Strict mode cũng ảnh hưởng cách xử lý giá trị ngày không hợp lệ.

Các giá trị như `0000-00-00`, ngày có tháng/ngày bằng 0 hoặc ngày không tồn tại có thể bị cảnh báo hoặc từ chối tùy mode và phiên bản. Không dựa vào zero date để biểu diễn “chưa biết”; dùng `NULL` hoặc một mô hình trạng thái rõ ràng.

Trước khi chuyển dữ liệu ngày giờ, xác định:

- Cột là ngày lịch (`DATE`), thời điểm không timezone (`DATETIME`) hay thời điểm có quy tắc timezone (`TIMESTAMP`).
- Định dạng nguồn và timezone đã biết hay chưa.
- Có giá trị zero date, ngày ngoài lịch hoặc chuỗi không parse được không.
- Độ chính xác phần giây cần giữ là 0 đến 6 chữ số.

Ví dụ kiểm tra mode và dữ liệu:

```sql
SELECT @@SESSION.sql_mode;

SELECT COUNT(*) AS zero_date_rows
FROM source_stage
WHERE date_text IN ('0000-00-00', '0000-00-00 00:00:00');
```

Trong ETL, parse ngày giờ ở bước staging bằng quy tắc tường minh, ghi lỗi parse vào reject table và chỉ nạp giá trị hợp lệ vào cột đích.

## 11. Kiểm tra dữ liệu trước khi ghi

Đừng đợi câu `INSERT` thất bại mới biết dữ liệu vượt miền. Trước khi nạp, chạy truy vấn kiểm tra theo kiểu đích.

Ví dụ dữ liệu nguồn cần chuyển vào `TINYINT UNSIGNED`:

```sql
SELECT source_id, qty
FROM source_stage
WHERE qty IS NULL
   OR qty < 0
   OR qty > 255;
```

Kiểm tra giá trị cho `DECIMAL(5,2)`:

```sql
SELECT source_id, amount
FROM source_stage
WHERE amount < -999.99
   OR amount > 999.99;
```

Kiểm tra độ dài chuỗi đích `VARCHAR(4)`:

```sql
SELECT source_id, code, CHAR_LENGTH(code) AS char_count
FROM source_stage
WHERE CHAR_LENGTH(code) > 4;
```

Kiểm tra cả `NULL`, chuỗi rỗng và khoảng trắng theo quy tắc nghiệp vụ. Nếu cột đích `NOT NULL`, tìm mọi hàng nguồn thiếu giá trị trước khi nạp. Không tự thay `NULL` bằng `0`, chuỗi rỗng hoặc ngày mặc định nếu nghiệp vụ chưa quy định.

## 12. Dùng staging và quarantine cho import

Một pipeline an toàn thường có ba khu vực:

1. **Raw/staging:** giữ nguyên giá trị nguồn ở dạng đủ rộng, thường là chuỗi hoặc kiểu ít làm mất dữ liệu trong quá trình trích xuất.
2. **Validated/normalized:** chuyển đổi theo quy tắc rõ ràng, ghi lại giá trị hợp lệ và lỗi validation.
3. **Target:** bảng nghiệp vụ với kiểu dữ liệu, constraint và index chính thức.

Ví dụ bảng staging:

```sql
CREATE TABLE stg_measurements (
  source_id VARCHAR(64) NOT NULL,
  qty_text VARCHAR(100),
  amount_text VARCHAR(100),
  code_text TEXT,
  source_row_number BIGINT
) ENGINE = InnoDB;
```

Giữ dữ liệu nguồn trước khi ép kiểu giúp có thể điều tra và nạp lại. Khi chuẩn hóa, tách hàng hợp lệ và không hợp lệ vào hai tập riêng. Bảng quarantine nên lưu source ID, raw value, tên cột, mã lỗi, message và thời điểm xử lý.

Không dùng `CAST()` như bộ lọc an toàn duy nhất. Một số phép chuyển đổi có thể trả warning hoặc giá trị thay thế; hãy kiểm tra định dạng và miền trước khi cast, đồng thời đọc diagnostics của bước chuyển đổi.

## 13. Nạp dữ liệu bằng `LOAD DATA`

`LOAD DATA [LOCAL] INFILE` có thể tăng tốc nạp CSV, nhưng vẫn chịu quy tắc chuyển đổi kiểu, SQL mode và cấu hình import.

```sql
LOAD DATA LOCAL INFILE 'measurements.csv'
INTO TABLE stg_measurements
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(source_id, qty_text, amount_text, code_text);

SHOW COUNT(*) WARNINGS;
SHOW WARNINGS;
```

`LOCAL` đọc file từ phía client và cần được cho phép ở cả client lẫn server theo cấu hình. Chỉ bật khi chính sách bảo mật cho phép. File CSV cần quy định delimiter, quote, escape, newline, encoding và cách biểu diễn `NULL`/chuỗi rỗng.

Đối với import production, nạp vào staging trước, kiểm tra warning và số hàng, sau đó mới chuyển sang bảng đích. `LOAD DATA` có thể xử lý lỗi và tiếp tục theo các tùy chọn như `IGNORE` hoặc `REPLACE`; hiểu rõ tác động trước khi dùng vì chúng có thể bỏ qua hoặc ghi đè hàng.

## 14. Sửa schema khi dữ liệu thực sự cần miền lớn hơn

Nếu dữ liệu hợp lệ theo nghiệp vụ nhưng không vừa kiểu cột, sửa schema có thể là giải pháp đúng. Trước khi `ALTER TABLE`, xác định:

- Miền tối đa/tối thiểu thực tế và miền dự kiến trong tương lai.
- Các ứng dụng, API, ORM, ETL và báo cáo phụ thuộc kiểu cũ.
- Index, foreign key, generated column và view phụ thuộc cột.
- Dung lượng, thời gian khóa/DDL và tác động lên replication.
- Kế hoạch rollback nếu thay đổi kiểu không thể đảo ngược an toàn.

Ví dụ mở rộng độ dài cột:

```sql
ALTER TABLE customers
  MODIFY external_code VARCHAR(32)
  CHARACTER SET utf8mb4
  NOT NULL;
```

Ví dụ đổi kiểu số cần đánh giá dữ liệu hiện tại trước:

```sql
ALTER TABLE inventory
  MODIFY quantity INT UNSIGNED NOT NULL;
```

Đừng chạy `ALTER TABLE` trước khi xác nhận không có giá trị âm, NULL hoặc giá trị vượt miền mới. Thay đổi kiểu có thể cần rebuild bảng, tạo tải I/O lớn hoặc ảnh hưởng thời gian truy cập tùy phiên bản và loại thay đổi.

## 15. Ràng buộc dữ liệu để ngăn lỗi tái diễn

Validation ở ứng dụng giúp phản hồi sớm, nhưng database cần ràng buộc để bảo vệ dữ liệu trước mọi writer.

Ví dụ:

```sql
CREATE TABLE inventory_safe (
  sku VARCHAR(32) NOT NULL PRIMARY KEY,
  quantity INT UNSIGNED NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  code VARCHAR(12) NOT NULL,
  CONSTRAINT chk_quantity_nonnegative CHECK (quantity >= 0),
  CONSTRAINT chk_unit_price_nonnegative CHECK (unit_price >= 0)
) ENGINE = InnoDB;
```

MySQL thực thi `CHECK` constraint từ phiên bản 8.0.16. Các phiên bản cũ hơn có thể phân tích cú pháp nhưng không thực thi constraint theo cách hiện đại. Kiểm tra phiên bản trước khi dựa vào `CHECK` để bảo vệ dữ liệu.

Kiểu dữ liệu và độ dài cột tự tạo một số giới hạn; `CHECK` bổ sung quy tắc nghiệp vụ như không âm, tỷ lệ trong khoảng hoặc giá trị thuộc miền cho phép. Constraint không thay thế quy trình xử lý lỗi import.

## 16. Xử lý lỗi trong ứng dụng JDBC

Ứng dụng Java cần phân biệt exception và warning. Với `SQLException`, ghi nhận error code, SQLSTATE và message đã làm sạch. Với statement hoàn tất có warning, đọc `SQLWarning` nếu driver cung cấp:

```java
try (PreparedStatement statement = connection.prepareStatement(
        "INSERT INTO values_probe(qty, amount, code) VALUES (?, ?, ?)")) {
    statement.setInt(1, qty);
    statement.setBigDecimal(2, amount);
    statement.setString(3, code);

    int affectedRows = statement.executeUpdate();
    for (SQLWarning warning = statement.getWarnings();
         warning != null;
         warning = warning.getNextWarning()) {
        // Ghi nhận từng warning code/message và đánh dấu bản ghi cần kiểm tra.
    }
} catch (SQLException exception) {
    int errorCode = exception.getErrorCode();
    String sqlState = exception.getSQLState();
    // Phân loại lỗi dữ liệu; không retry như lỗi mạng tạm thời.
}
```

Đối với dữ liệu vượt miền hoặc quá dài, retry cùng payload sẽ tiếp tục thất bại hoặc tiếp tục bị biến đổi. Hãy trả lỗi validation có ngữ cảnh, đưa bản ghi vào quarantine hoặc yêu cầu sửa dữ liệu nguồn.

Không log toàn bộ payload nếu có dữ liệu cá nhân, token hoặc thông tin nhạy cảm. Log source ID, tên cột, mã lỗi và giá trị đã mask khi cần điều tra.

## 17. Checklist xử lý sự cố

Khi gặp `Data too long`, `Out of range` hoặc `Data truncated`, thực hiện theo thứ tự:

1. Lấy error code, SQLSTATE, message, tên bảng/cột và câu lệnh đã làm sạch.
2. Kiểm tra `@@SESSION.sql_mode` của đúng connection gây lỗi; không chỉ xem global mode.
3. Đọc kiểu dữ liệu, signed/unsigned, precision/scale, charset/collation và độ dài cột.
4. Kiểm tra giá trị nguồn bằng `CHAR_LENGTH`, `LENGTH`, min/max và điều kiện miền.
5. Nếu statement có warning, chạy `SHOW WARNINGS` ngay trong cùng session.
6. Xác định engine transactional hay nontransactional và kiểm tra có hàng nào đã được ghi một phần không.
7. Kiểm tra `IGNORE`, `LOAD DATA`, cast hoặc implicit conversion trong pipeline.
8. Quyết định sửa dữ liệu, mở rộng schema hoặc từ chối bản ghi theo quy tắc nghiệp vụ.
9. Nạp lại từ staging, đối chiếu số hàng và giá trị thực tế sau ghi.
10. Giữ strict mode trong production và thêm validation/monitoring để lỗi không tái diễn.

## 18. Lỗi thường gặp

- **Tắt strict mode để import chạy:** dữ liệu có thể bị cắt hoặc ép về giá trị biên. Giữ raw data, sửa mapping và nạp lại bằng strict mode.
- **Chỉ nhìn số hàng insert:** statement có thể hoàn tất với warning và giá trị đã biến đổi. Kiểm tra warnings và dữ liệu đích.
- **Nhầm ký tự với byte:** `VARCHAR(n)` giới hạn ký tự, nhưng byte ảnh hưởng dung lượng hàng và index. Dùng `CHAR_LENGTH` và `LENGTH` đúng mục đích.
- **Dùng `UNSIGNED` không kiểm tra:** dữ liệu âm bị từ chối hoặc ép về 0 tùy mode. Xác minh miền nghiệp vụ trước khi đổi kiểu.
- **Dùng `INSERT IGNORE` để che lỗi:** bản ghi có thể bị cắt hoặc bỏ qua. Ghi nhận warning và quarantine dữ liệu lỗi.
- **Chỉ kiểm tra global SQL mode:** connection pool có thể giữ session với mode cũ. Kiểm tra session thực tế và recycle pool khi thay đổi cấu hình.
- **Mở rộng cột tùy tiện:** tăng storage, index và độ phức tạp mà không giải quyết nguồn dữ liệu sai. Chọn kiểu theo miền nghiệp vụ.
- **Sửa dữ liệu trực tiếp khi chưa có bản raw:** khó khôi phục giá trị gốc. Giữ staging và audit nguồn.

## 19. Bài tập thực hành

Trên một MySQL instance thử nghiệm:

1. Tạo bảng `values_probe` với `TINYINT UNSIGNED`, `DECIMAL(5,2)` và `VARCHAR(4)`.
2. Bật strict mode trong session và thử insert `qty=256`, `amount=1000.00` và chuỗi 5 ký tự; ghi nhận lỗi.
3. Tạm tắt strict mode chỉ trong session lab, lặp lại thao tác và đọc `SHOW WARNINGS`; kiểm tra giá trị thực sự được lưu.
4. Thử `INSERT IGNORE` khi strict mode bật và so sánh warning với insert thông thường.
5. Nạp dữ liệu có chuỗi Unicode nhiều byte; so sánh `CHAR_LENGTH()` và `LENGTH()`.
6. Tạo staging table, tìm các hàng vượt miền bằng truy vấn validation rồi tách sang bảng quarantine.
7. Mở rộng cột hoặc điều chỉnh kiểu sau khi chứng minh dữ liệu hợp lệ; xác minh schema và dữ liệu sau `ALTER TABLE`.
8. Viết một JDBC test đọc `SQLWarning` và phân loại `SQLException` theo error code/SQLSTATE.

**Tiêu chí hoàn thành:** bạn có thể giải thích sự khác nhau giữa error và warning, dự đoán tác động của strict mode, xác định chính xác giá trị bị cắt/ép miền và thiết kế quy trình nạp dữ liệu không âm thầm làm sai dữ liệu.

## Kết luận

`Data too long`, `Out of range` và `Data truncated` là tín hiệu cho thấy dữ liệu nguồn, kiểu cột hoặc quy tắc chuyển đổi chưa khớp. Hãy kiểm tra SQL mode của đúng session, đọc warnings ngay sau statement, xác minh miền số và độ dài chuỗi, rồi xử lý dữ liệu qua staging trước khi ghi vào bảng nghiệp vụ. Giữ strict mode, dùng InnoDB, constraint và validation rõ ràng để phát hiện dữ liệu sai tại nơi phát sinh thay vì để giá trị bị biến đổi âm thầm.

# Warning so với error và đọc SHOW WARNINGS

Bài học thuộc chương **SQL mode và ngữ nghĩa** của module `DATABASE_MYSQL`. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Khi MySQL tiếp nhận dữ liệu hoặc thực thi câu lệnh, máy chủ có thể phát sinh lỗi, cảnh báo hoặc ghi chú. Hiểu đúng mức độ của từng thông báo giúp xác định câu lệnh đã thất bại, dữ liệu có bị điều chỉnh hay không và cần xử lý tiếp như thế nào.

Sau bài này, bạn có thể phân biệt Error, Warning và Note; hiểu tác động của SQL mode và strict mode; đọc kết quả `SHOW WARNINGS` và `SHOW ERRORS`; kiểm tra số lượng condition; và xử lý các tình huống dữ liệu sai định dạng, vượt giới hạn hoặc bị chuyển đổi.

## 1. Error, Warning và Note khác nhau thế nào?

MySQL phân loại các condition phát sinh trong quá trình thực thi câu lệnh thành ba mức phổ biến:

| Mức | Ý nghĩa | Tác động thường gặp |
|---|---|---|
| **Error** | Câu lệnh gặp điều kiện khiến máy chủ không thể tiếp tục theo yêu cầu | Câu lệnh bị hủy hoặc không hoàn tất; với InnoDB, thay đổi của chính câu lệnh thường được rollback |
| **Warning** | Máy chủ phát hiện vấn đề nhưng vẫn có thể tiếp tục thực thi | Câu lệnh có thể hoàn tất; dữ liệu có thể đã bị điều chỉnh, cắt, bỏ qua hoặc thay thế |
| **Note** | Thông tin bổ sung về quá trình xử lý | Thường không làm câu lệnh thất bại hay thay đổi dữ liệu theo cách bất thường |

Ví dụ:

- Chèn số 300 vào cột `TINYINT UNSIGNED` trong strict mode có thể gây Error vì giá trị vượt giới hạn.
- Chèn cùng giá trị khi strict mode tắt có thể được điều chỉnh thành 255 và tạo Warning.
- Dùng `DROP TABLE IF EXISTS` với bảng không tồn tại có thể tạo Note để thông báo không có bảng cần xóa.

Không nên hiểu Warning là “không có vấn đề”. Một câu lệnh có thể trả về `Query OK` nhưng vẫn lưu dữ liệu đã bị cắt hoặc chuyển đổi. Nếu ứng dụng bỏ qua Warning, dữ liệu sai có thể tiếp tục đi vào các bước xử lý phía sau.

Ngược lại, Error không nhất thiết có nghĩa toàn bộ transaction đã bị rollback. Với InnoDB, lỗi của một câu lệnh thường rollback phần thay đổi của câu lệnh đó; transaction vẫn có thể còn mở. Với storage engine không hỗ trợ transaction, một câu lệnh nhiều hàng có thể để lại một phần thay đổi tùy loại lỗi và SQL mode.

## 2. SQL mode quyết định cách xử lý một số dữ liệu không hợp lệ

`sql_mode` là biến hệ thống quy định một tập các quy tắc cú pháp và ngữ nghĩa SQL. Một số mode ảnh hưởng trực tiếp đến việc MySQL trả Warning hay Error khi gặp giá trị không hợp lệ.

Kiểm tra cấu hình:

~~~sql
SELECT
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode;
~~~

- **Global SQL mode** là giá trị mặc định được áp dụng cho các session mới.
- **Session SQL mode** quyết định hành vi trong kết nối hiện tại.
- Thay đổi session chỉ ảnh hưởng kết nối hiện tại.
- Thay đổi global chỉ ảnh hưởng các kết nối mới; các session đang mở vẫn giữ giá trị riêng.

Trong MySQL 9.7, SQL mode mặc định bao gồm các mode như:

- `ONLY_FULL_GROUP_BY`
- `STRICT_TRANS_TABLES`
- `NO_ZERO_IN_DATE`
- `NO_ZERO_DATE`
- `ERROR_FOR_DIVISION_BY_ZERO`
- `NO_ENGINE_SUBSTITUTION`

Cấu hình thực tế có thể khác do tùy chọn khởi động, file cấu hình hoặc thao tác quản trị. Vì vậy, hãy kiểm tra `@@SESSION.sql_mode` trong chính kết nối đang chạy câu lệnh cần chẩn đoán.

### Strict mode

MySQL xem strict mode là trạng thái có ít nhất một trong hai mode:

- `STRICT_TRANS_TABLES`
- `STRICT_ALL_TABLES`

Strict mode kiểm soát cách xử lý giá trị không hợp lệ hoặc bị thiếu trong các câu lệnh thay đổi dữ liệu như `INSERT`, `UPDATE`, `LOAD DATA`, cũng như một số thao tác DDL.

Ví dụ về dữ liệu không hợp lệ:

- Giá trị số vượt phạm vi kiểu cột.
- Chuỗi không thể chuyển đổi đúng sang kiểu số.
- Chuỗi dài hơn giới hạn cột.
- Thiếu giá trị cho cột `NOT NULL` không có `DEFAULT`.
- Ngày giờ không hợp lệ theo các mode đang bật.

Nếu strict mode không bật, MySQL có thể điều chỉnh giá trị để phù hợp cột và phát Warning. Nếu strict mode bật, một số trường hợp tương tự được nâng thành Error.

Strict mode không biến mọi Warning thành Error. Nó áp dụng cho các nhóm lỗi dữ liệu được MySQL quy định. Chẳng hạn, một câu SELECT thực hiện phép chia cho 0 vẫn trả về NULL và Warning, ngay cả khi strict mode đang bật.

### STRICT_TRANS_TABLES và STRICT_ALL_TABLES

Hai mode này có khác biệt đáng chú ý với storage engine không hỗ trợ transaction.

| Tình huống | STRICT_TRANS_TABLES | STRICT_ALL_TABLES |
|---|---|---|
| Bảng transactional như InnoDB | Giá trị không hợp lệ gây Error và câu lệnh được rollback | Tương tự |
| Bảng nontransactional, lỗi ở hàng đầu tiên | Hủy câu lệnh | Hủy câu lệnh |
| Bảng nontransactional, lỗi ở hàng thứ hai trở đi trong câu lệnh nhiều hàng | Có thể điều chỉnh giá trị không hợp lệ về giá trị hợp lệ gần nhất và phát Warning, rồi tiếp tục | Báo Error và dừng; các hàng trước đó có thể đã được ghi, tạo kết quả một phần |

Vì vậy, strict mode không thay thế được lựa chọn storage engine. Với dữ liệu nghiệp vụ cần rollback nguyên tử, nên dùng InnoDB và tránh dựa vào hành vi của bảng nontransactional.

## 3. IGNORE có thể hạ một số Error thành Warning

Một số câu lệnh hỗ trợ từ khóa `IGNORE`, ví dụ:

- `INSERT IGNORE`
- `UPDATE IGNORE`
- `DELETE IGNORE`
- `LOAD DATA ... IGNORE`

Trong các tình huống được MySQL cho phép, `IGNORE` hạ một số Error xuống Warning để câu lệnh tiếp tục.

Ví dụ:

- Giá trị vượt phạm vi có thể được điều chỉnh về giá trị gần nhất hợp lệ.
- Chuỗi quá dài có thể bị cắt.
- Hàng vi phạm unique key có thể bị bỏ qua thay vì làm cả câu lệnh thất bại.

`IGNORE` có thể được sử dụng cùng strict mode. Khi đó, với các lỗi có thể bỏ qua, `IGNORE` được ưu tiên và điều kiện vốn gây Error có thể trở thành Warning.

Tuy nhiên, không phải mọi Error đều có thể bị bỏ qua. Lỗi cú pháp, lỗi kết nối, thiếu quyền và các lỗi không thuộc danh sách ignorable vẫn có thể làm câu lệnh thất bại.

Không nên thêm `IGNORE` chỉ để làm cho batch import “chạy hết”. Nếu dữ liệu bị cắt, thay thế hoặc bỏ qua, ứng dụng cần có quy trình kiểm tra và báo cáo các hàng bị ảnh hưởng.

## 4. SHOW WARNINGS đọc thông tin gì?

Cú pháp:

~~~sql
SHOW WARNINGS;
SHOW WARNINGS LIMIT 10;
SHOW WARNINGS LIMIT 5, 10;
SHOW COUNT(*) WARNINGS;
~~~

`SHOW WARNINGS` là một diagnostic statement, hiển thị các condition phát sinh từ câu lệnh không phải diagnostic gần nhất trong session hiện tại.

Kết quả có ba cột:

| Cột | Ý nghĩa |
|---|---|
| `Level` | Mức condition: Note, Warning hoặc Error |
| `Code` | Mã lỗi số của MySQL |
| `Message` | Nội dung mô tả condition |

Ví dụ kết quả:

~~~text
+---------+------+------------------------------------------------------+
| Level   | Code | Message                                              |
+---------+------+------------------------------------------------------+
| Warning | 1264 | Out of range value for column 'quantity' at row 1    |
| Warning | 1265 | Data truncated for column 'label' at row 1           |
+---------+------+------------------------------------------------------+
~~~

Một kết quả có `Level = Error` cũng có thể xuất hiện trong `SHOW WARNINGS` sau khi câu lệnh thất bại. Tên lệnh này không có nghĩa là nó chỉ hiển thị Warning; nó hiển thị cả Error, Warning và Note.

### Chỉ xem Error

Nếu chỉ muốn xem các Error:

~~~sql
SHOW ERRORS;
SHOW ERRORS LIMIT 10;
SHOW COUNT(*) ERRORS;
~~~

`SHOW ERRORS` tương tự `SHOW WARNINGS` nhưng chỉ trả condition có mức Error.

### Giới hạn số dòng hiển thị

`LIMIT` hoạt động giống cú pháp SELECT:

~~~sql
-- Hiển thị tối đa 10 condition đầu tiên
SHOW WARNINGS LIMIT 10;

-- Bỏ qua 5 condition đầu, lấy 10 condition tiếp theo
SHOW WARNINGS LIMIT 5, 10;
~~~

Khi một câu lệnh tạo rất nhiều Warning, kết quả hiển thị có thể không chứa toàn bộ thông báo. Cần hiểu biến `max_error_count` trước khi kết luận rằng chỉ có một số ít lỗi dữ liệu.

## 5. Đọc Warning ngay sau câu lệnh gây ra nó

Thông tin trong diagnostics area gắn với câu lệnh gần nhất. Một câu lệnh SQL thông thường tiếp theo có thể xóa condition trước đó và thay bằng condition của chính nó.

Ví dụ không nên làm:

~~~sql
INSERT INTO warning_demo (id, quantity)
VALUES (1, 300);

SELECT * FROM warning_demo;

-- Có thể đã mất thông tin của INSERT
SHOW WARNINGS;
~~~

Sau INSERT, SELECT là một nondiagnostic statement. Nó thay thế diagnostics area trước khi `SHOW WARNINGS` được gọi.

Cách đúng:

~~~sql
INSERT INTO warning_demo (id, quantity)
VALUES (1, 300);

SHOW WARNINGS;
~~~

Nếu cần đếm condition, có thể dùng diagnostic statement:

~~~sql
INSERT INTO warning_demo (id, quantity)
VALUES (1, 300);

SHOW COUNT(*) WARNINGS;
SHOW WARNINGS;
~~~

`SHOW COUNT(*) WARNINGS` cũng là diagnostic statement nên không xóa danh sách condition. Ngược lại, câu lệnh `SELECT @@warning_count` là nondiagnostic; nó có thể thay thế diagnostics area. Hãy đọc Warning trước khi chạy SELECT hoặc truy vấn thông thường khác.

### Diagnostics area là gì?

Diagnostics area là vùng thông tin mà MySQL dùng để lưu condition của câu lệnh vừa thực thi. Nó chứa số lượng condition và thông tin chi tiết cho từng condition được lưu.

Các diagnostic statement như:

- `SHOW WARNINGS`
- `SHOW ERRORS`
- `GET DIAGNOSTICS`

có thể đọc thông tin này mà không xóa condition đang có.

Các câu lệnh SQL thông thường như SELECT, INSERT, UPDATE, DELETE hoặc DDL sẽ tạo diagnostics area mới khi thực thi. Vì vậy, hãy kiểm tra ngay sau câu lệnh cần chẩn đoán.

## 6. warning_count, error_count và max_error_count

MySQL cung cấp các biến và câu lệnh để đếm condition.

| Thành phần | Ý nghĩa |
|---|---|
| `SHOW COUNT(*) WARNINGS` | Tổng số Error, Warning và Note của câu lệnh gần nhất |
| `@@warning_count` | Số condition, gồm Error, Warning và Note (trừ Note nếu `sql_notes=0`) |
| `SHOW COUNT(*) ERRORS` | Tổng số Error của câu lệnh gần nhất |
| `@@error_count` | Số Error của câu lệnh gần nhất |
| `max_error_count` | Số condition tối đa mà MySQL lưu chi tiết trong diagnostics area |
| `sql_notes` | Điều khiển việc lưu và đếm các Note |

Tên `warning_count` dễ gây nhầm: giá trị này không chỉ đếm Warning. Nó đếm tổng condition gồm Error, Warning và Note. Nếu cần đếm riêng Error, dùng `error_count` hoặc `SHOW COUNT(*) ERRORS`.

### max_error_count

Trong MySQL 9.7, `max_error_count` có giá trị mặc định 1024, phạm vi từ 0 đến 65535.

Biến này chỉ giới hạn số condition được lưu chi tiết để hiển thị bằng `SHOW WARNINGS`, `SHOW ERRORS` hoặc đọc qua `GET DIAGNOSTICS`. Nó không giới hạn số condition được đếm.

Ví dụ, nếu một câu lệnh tạo 20 Warning nhưng `max_error_count = 5`:

- `warning_count` vẫn là 20.
- Diagnostics area chỉ giữ tối đa 5 condition.
- `SHOW WARNINGS` chỉ có thể hiển thị các condition đã được lưu.

Nếu đặt `max_error_count = 0`, MySQL vẫn đếm condition nhưng không lưu nội dung chi tiết để xem lại.

Kiểm tra:

~~~sql
SHOW VARIABLES LIKE 'max_error_count';
~~~

Chỉ tăng biến này khi cần phân tích câu lệnh tạo nhiều condition. Không nên mặc định tăng tối đa trên mọi session.

### sql_notes

`sql_notes` mặc định là 1. Khi đặt bằng 0, MySQL không lưu Note và không cộng Note vào `warning_count`.

~~~sql
SELECT @@SESSION.sql_notes;

SET SESSION sql_notes = 0;
SET SESSION sql_notes = 1;
~~~

Việc tắt Note không làm Warning hoặc Error biến mất. Trong quá trình chẩn đoán, nên giữ `sql_notes = 1` để có đầy đủ thông tin.

## 7. Ví dụ: strict mode tạo Error, IGNORE tạo Warning

Bài thực hành này minh họa một giá trị vượt phạm vi và một chuỗi quá dài.

### Bước 1: tạo bảng

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_diagnostics_lab;
USE mysql_diagnostics_lab;

CREATE TABLE warning_demo (
    id INT NOT NULL PRIMARY KEY,
    quantity TINYINT UNSIGNED NOT NULL,
    label VARCHAR(5) NOT NULL
) ENGINE=InnoDB;
~~~

Cột `quantity` chỉ nhận giá trị từ 0 đến 255. Cột `label` chỉ nhận tối đa 5 ký tự.

### Bước 2: bật strict mode cho session

Lưu cấu hình hiện tại trước khi thay đổi:

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode =
    'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION';
~~~

Kiểm tra:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

### Bước 3: thử chèn dữ liệu vượt giới hạn

~~~sql
INSERT INTO warning_demo (id, quantity, label)
VALUES (1, 300, 'OK');
~~~

Vì `quantity` là `TINYINT UNSIGNED`, giá trị 300 vượt phạm vi. Trong strict mode, câu lệnh phát sinh Error và bị hủy.

Đọc condition ngay sau câu lệnh:

Hãy chạy câu INSERT lỗi riêng trước. Khi client báo Error, gửi tiếp `SHOW WARNINGS` hoặc `SHOW ERRORS` trong cùng session. Một số chế độ chạy script/batch có thể dừng ngay khi gặp Error; khi đó hãy mở kết nối tương tác hoặc cấu hình runner tiếp tục sau lỗi để đọc diagnostics.

~~~sql
SHOW WARNINGS;
SHOW ERRORS;
~~~

Bạn sẽ thấy Error tương ứng với giá trị vượt phạm vi, thường có mã 1264.

Kiểm tra dữ liệu:

~~~sql
SELECT * FROM warning_demo;
~~~

Vì bảng dùng InnoDB, câu lệnh INSERT thất bại không tạo hàng.

### Bước 4: thử INSERT IGNORE

Chèn lại dữ liệu nhưng dùng `IGNORE`:

~~~sql
INSERT IGNORE INTO warning_demo (id, quantity, label)
VALUES (1, 300, 'TOOLONG');
~~~

Trong trường hợp này, MySQL có thể điều chỉnh:

- `quantity`: từ 300 về giá trị tối đa hợp lệ là 255.
- `label`: cắt chuỗi về 5 ký tự.

Câu lệnh có thể hoàn tất với Warning thay vì Error.

Đọc thông báo ngay:

~~~sql
SHOW WARNINGS;
~~~

Kiểm tra dữ liệu đã được ghi:

~~~sql
SELECT * FROM warning_demo;
~~~

Bạn sẽ thấy hàng có `quantity = 255` và `label = 'TOOLO'`. Đây là ví dụ điển hình cho thấy `Query OK` không bảo đảm dữ liệu được lưu nguyên vẹn như đầu vào.

### Bước 5: thử SELECT tạo Warning

Strict mode không biến mọi Warning thành Error. Ví dụ:

~~~sql
SELECT 1 / 0 AS division_result;
SHOW WARNINGS;
~~~

Phép chia cho 0 trong SELECT trả về NULL và phát Warning. Câu SELECT vẫn hoàn tất.

### Bước 6: khôi phục SQL mode và dọn dẹp

Khôi phục mode ban đầu trong cùng session:

~~~sql
SET SESSION sql_mode = @saved_sql_mode;
~~~

Sau khi hoàn tất, xóa database lab:

~~~sql
DROP DATABASE mysql_diagnostics_lab;
~~~

Chỉ chạy lệnh DROP trên database lab vừa tạo. Lệnh này xóa toàn bộ bảng và dữ liệu thực hành.

## 8. Ví dụ: phân biệt Warning và Note

### Warning từ chuyển đổi dữ liệu

Nếu strict mode tắt, dữ liệu sai định dạng có thể được điều chỉnh và tạo Warning:

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;
SET SESSION sql_mode = '';

CREATE TABLE conversion_demo (
    id INT PRIMARY KEY,
    amount INT
) ENGINE=InnoDB;

INSERT INTO conversion_demo (id, amount)
VALUES (1, 'abc');

SHOW WARNINGS;
~~~

MySQL có thể chuyển chuỗi `abc` thành giá trị số mặc định phù hợp (0) và phát Warning về chuyển đổi số không hợp lệ.

Kiểm tra hàng đã lưu:

~~~sql
SELECT * FROM conversion_demo;
~~~

Khôi phục cấu hình và dọn bảng:

~~~sql
DROP TABLE conversion_demo;
SET SESSION sql_mode = @saved_sql_mode;
~~~

Thực hiện ví dụ này trong session lab riêng. Không để SQL mode rỗng trong ứng dụng hoặc hệ thống dùng chung chỉ để làm cho dữ liệu lỗi được chấp nhận.

### Note từ câu lệnh IF EXISTS

Ví dụ:

~~~sql
DROP TABLE IF EXISTS table_that_does_not_exist;
SHOW WARNINGS;
~~~

Nếu bảng không tồn tại, câu lệnh vẫn hoàn tất và MySQL có thể trả Note với mã 1051. Note cho biết đối tượng không tồn tại, nhưng `IF EXISTS` đã khiến tình huống đó không làm câu lệnh thất bại.

Nếu `sql_notes = 0`, Note không được lưu hoặc tính vào `warning_count`.

## 9. Lấy condition bằng GET DIAGNOSTICS

Ngoài `SHOW WARNINGS`, MySQL hỗ trợ `GET DIAGNOSTICS` để đọc condition trong SQL, đặc biệt hữu ích khi viết stored procedure hoặc xử lý lỗi có cấu trúc.

Đếm condition:

~~~sql
GET DIAGNOSTICS @condition_count = NUMBER;
~~~

Lấy thông tin condition đầu tiên:

~~~sql
GET DIAGNOSTICS CONDITION 1
    @sqlstate = RETURNED_SQLSTATE,
    @mysql_errno = MYSQL_ERRNO,
    @message = MESSAGE_TEXT;
~~~

Các mục thường dùng:

| Mục | Ý nghĩa |
|---|---|
| `NUMBER` | Số condition trong diagnostics area |
| `RETURNED_SQLSTATE` | SQLSTATE của condition |
| `MYSQL_ERRNO` | Mã lỗi số của MySQL |
| `MESSAGE_TEXT` | Nội dung thông báo |
| `ROW_NUMBER` | Số hàng liên quan nếu condition có thông tin này |

Ví dụ hoàn chỉnh sau một câu lệnh có Warning:

~~~sql
INSERT IGNORE INTO warning_demo (id, quantity, label)
VALUES (2, 300, 'TOOLONG');

GET DIAGNOSTICS @condition_count = NUMBER;

GET DIAGNOSTICS CONDITION 1
    @sqlstate = RETURNED_SQLSTATE,
    @mysql_errno = MYSQL_ERRNO,
    @message = MESSAGE_TEXT;

SELECT
    @condition_count AS condition_count,
    @sqlstate AS sqlstate,
    @mysql_errno AS mysql_errno,
    @message AS message;
~~~

Ở đây, `GET DIAGNOSTICS` lấy thông tin trước khi SELECT được thực thi. SELECT cuối cùng hiển thị các biến đã lưu.

Nếu một câu lệnh phát sinh nhiều condition, có thể lặp từ 1 đến `NUMBER` để lấy từng condition. Cần kiểm tra số lượng condition trước khi truy cập một vị trí cụ thể.

## 10. Xem Warning tự động trong mysql client

Khi làm việc bằng command-line client `mysql`, có thể bật chế độ hiển thị Warning ngay sau câu lệnh:

~~~text
mysql> \W
Show warnings enabled.
~~~

Sau đó, khi chạy câu lệnh tạo Warning, client sẽ hiển thị thông báo ngay sau kết quả.

Tắt chế độ này:

~~~text
mysql> \w
Show warnings disabled.
~~~

Có thể dùng lệnh client `warnings` và `nowarning` tương ứng.

Đây là tiện ích của command-line client, không phải SQL statement và không thay đổi SQL mode của server. Nếu dùng Workbench hoặc một connector khác, hãy kiểm tra khu vực thông báo của công cụ và chạy `SHOW WARNINGS` ngay sau câu lệnh cần kiểm tra.

## 11. Quy trình chẩn đoán Warning/Error trong ứng dụng

Khi một câu lệnh trả về Error hoặc Warning, hãy thực hiện theo thứ tự:

1. **Ghi nhận câu lệnh và session:** lưu SQL đã thực thi, tham số, database, user và `@@SESSION.sql_mode`. Không ghi mật khẩu hoặc dữ liệu bí mật vào log.
2. **Đọc kết quả client:** xác định câu lệnh thành công hay thất bại, số hàng ảnh hưởng và số Warning được báo.
3. **Chạy SHOW WARNINGS ngay:** không chạy SELECT hoặc câu lệnh SQL thông thường khác trước bước này.
4. **Phân loại condition:** xem Level, Code và Message; nếu cần SQLSTATE, dùng `GET DIAGNOSTICS`.
5. **Kiểm tra dữ liệu thực tế:** xác định có giá trị nào đã bị cắt, chuyển đổi, thay thế hoặc bỏ qua hay không.
6. **Kiểm tra SQL mode:** xác nhận strict mode, `IGNORE`, `sql_notes` và các mode liên quan.
7. **Sửa nguyên nhân:** kiểm tra kiểu cột, độ dài, giá trị đầu vào, charset, ngày giờ và ràng buộc dữ liệu.
8. **Kiểm thử lại:** chạy trên dữ liệu đại diện, xác nhận số hàng và nội dung đã lưu.
9. **Ghi log có cấu trúc:** lưu mã lỗi, SQLSTATE, message, câu lệnh định danh và số hàng liên quan để điều tra.

Không nên chỉ dựa vào mã trả về của driver. Một số driver có thể trả thành công khi câu lệnh có Warning; ứng dụng phải kiểm tra warning count hoặc bật cơ chế lấy thông báo phù hợp.

### Phân biệt lỗi statement và lỗi transaction

Với InnoDB, một câu lệnh INSERT nhiều hàng gặp Error do strict mode thường được rollback ở phạm vi statement. Transaction bên ngoài có thể vẫn còn hoạt động.

Ví dụ:

~~~sql
START TRANSACTION;

INSERT INTO warning_demo (id, quantity, label)
VALUES (10, 10, 'valid');

INSERT INTO warning_demo (id, quantity, label)
VALUES (11, 300, 'invalid');

-- Câu lệnh thứ hai thất bại.
-- Câu lệnh thứ nhất vẫn có thể đang nằm trong transaction.
ROLLBACK;
~~~

Nếu ứng dụng chỉ xử lý exception rồi tiếp tục mà không quyết định COMMIT hoặc ROLLBACK, transaction có thể giữ khóa hoặc trạng thái chưa hoàn tất. Cần có quy tắc xử lý transaction rõ ràng khi một câu lệnh thất bại.

## 12. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Thấy `Query OK` rồi cho rằng dữ liệu đúng | Giá trị có thể đã bị cắt hoặc điều chỉnh | Đọc Warning và kiểm tra dữ liệu đã lưu |
| Chạy SELECT trước SHOW WARNINGS | Diagnostics area đã bị thay thế | Chạy SHOW WARNINGS ngay sau câu lệnh gốc |
| Nghĩ SHOW WARNINGS chỉ hiện Warning | Bỏ sót Error hoặc Note | Đọc cột Level; dùng SHOW ERRORS khi chỉ cần Error |
| Nhầm `warning_count` là số Warning thuần túy | Đếm sai tổng condition | Nhớ rằng nó bao gồm Error, Warning và Note |
| Đặt `max_error_count=0` để giảm overhead rồi mong xem chi tiết | Không còn nội dung condition để hiển thị | Giữ giới hạn phù hợp với nhu cầu chẩn đoán |
| Dùng INSERT IGNORE cho mọi batch | Dữ liệu lỗi có thể bị sửa hoặc hàng bị bỏ qua âm thầm | Chỉ dùng khi có quy tắc chấp nhận dữ liệu và báo cáo hàng lỗi |
| Tắt strict mode trong production để tránh lỗi | Dữ liệu sai có thể được lưu dưới dạng đã điều chỉnh | Sửa dữ liệu nguồn và giữ strict mode phù hợp |
| Cho rằng Error luôn rollback toàn transaction | Transaction có thể vẫn mở và giữ lock | Xử lý COMMIT/ROLLBACK rõ ràng trong ứng dụng |
| Cho rằng strict mode nâng mọi Warning thành Error | Hiểu sai hành vi của SELECT và các condition khác | Đọc quy tắc strict mode theo nhóm thao tác và loại lỗi |

## 13. Checklist trước khi đưa xử lý dữ liệu vào production

- [ ] Đã kiểm tra `@@GLOBAL.sql_mode` và `@@SESSION.sql_mode`.
- [ ] Đã hiểu tác động của `STRICT_TRANS_TABLES` và `STRICT_ALL_TABLES`.
- [ ] Không sử dụng `IGNORE` nếu chưa có chính sách xử lý dữ liệu bị điều chỉnh hoặc bỏ qua.
- [ ] Ứng dụng ghi nhận cả số hàng ảnh hưởng và Warning count.
- [ ] Các câu lệnh quan trọng có bước đọc Warning/Error khi cần.
- [ ] Không chạy câu lệnh SQL thông thường giữa thao tác cần kiểm tra và `SHOW WARNINGS`.
- [ ] Đã cấu hình `max_error_count` đủ để chẩn đoán workload.
- [ ] Không tắt `sql_notes` nếu cần giữ thông tin Note.
- [ ] Đã phân biệt lỗi ở cấp statement và transaction.
- [ ] Đã kiểm tra dữ liệu sau import/update để phát hiện cắt hoặc chuyển đổi.
- [ ] Đã log SQLSTATE, mã MySQL và message mà không để lộ dữ liệu bí mật.
- [ ] Đã có kiểm thử cho dữ liệu vượt giới hạn, sai kiểu và giá trị NULL.

## Tài liệu tham khảo chính thức

Các hành vi trong bài được đối chiếu với **MySQL 9.7 Reference Manual** tại ngày **19-11-2026**:

1. [SHOW WARNINGS Statement](https://dev.mysql.com/doc/refman/9.7/en/show-warnings.html): cú pháp, kết quả, warning_count, max_error_count, sql_notes và hành vi diagnostic.
2. [SHOW ERRORS Statement](https://dev.mysql.com/doc/refman/9.7/en/show-errors.html): chỉ đọc các condition có mức Error.
3. [Server SQL Modes](https://dev.mysql.com/doc/refman/9.7/en/sql-mode.html): strict mode, STRICT_TRANS_TABLES, STRICT_ALL_TABLES, IGNORE và cách xử lý dữ liệu không hợp lệ.
4. [The MySQL Diagnostics Area](https://dev.mysql.com/doc/refman/9.7/en/diagnostics-area.html): cách diagnostics area được tạo, xóa và đọc.
5. [GET DIAGNOSTICS Statement](https://dev.mysql.com/doc/refman/9.7/en/get-diagnostics.html): đọc số lượng condition, SQLSTATE, mã lỗi và message.
6. [Server System Variables](https://dev.mysql.com/doc/refman/9.7/en/server-system-variables.html): phạm vi và giá trị của `max_error_count`, `sql_notes` và `sql_mode`.
7. [mysql Client Commands](https://dev.mysql.com/doc/refman/9.7/en/mysql-commands.html): bật/tắt hiển thị Warning tự động trong command-line client.


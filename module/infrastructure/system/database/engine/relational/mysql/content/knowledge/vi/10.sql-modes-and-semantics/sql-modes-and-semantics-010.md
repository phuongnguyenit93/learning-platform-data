# sql_safe_updates và phân biệt với các cờ sql_mode

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích `sql_safe_updates` bảo vệ các lệnh `UPDATE` và `DELETE` như thế nào.
- Phân biệt `sql_safe_updates` với biến `sql_mode` và các mode như `STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, `ANSI_QUOTES`.
- Kiểm tra và thay đổi `sql_safe_updates` ở phạm vi SESSION hoặc GLOBAL.
- Hiểu vì sao một câu lệnh có khóa hoặc có `LIMIT` vẫn có thể tác động quá nhiều hàng.
- Viết quy trình kiểm tra trước khi cập nhật/xóa dữ liệu và xử lý lỗi 1175.
- Nhận biết ảnh hưởng của SQL client, connection pool và môi trường triển khai tới chế độ safe updates.

## 1. sql_safe_updates dùng để làm gì?

`sql_safe_updates` là một biến hệ thống của MySQL giúp hạn chế một số câu lệnh cập nhật hoặc xóa dữ liệu có phạm vi không rõ ràng. Khi biến này được bật, MySQL từ chối các lệnh `UPDATE` hoặc `DELETE` nếu câu lệnh không sử dụng cột khóa trong điều kiện `WHERE` và cũng không có mệnh đề `LIMIT`.

Mục đích là giảm nguy cơ vô tình chạy một lệnh tác động tới toàn bộ bảng, chẳng hạn quên điều kiện lọc:

```sql
-- Có thể tác động tới mọi hàng trong bảng nếu không có safe updates
UPDATE employees
SET status = 'INACTIVE';

-- Có thể xóa mọi hàng trong bảng nếu không có safe updates
DELETE FROM employees;
```

Khi `sql_safe_updates = 1`, những câu lệnh không có `WHERE` sử dụng key và cũng không có `LIMIT` như trên sẽ bị từ chối. Cơ chế này thường trả về lỗi MySQL 1175 với thông báo liên quan đến safe update mode.

Điều cần nhớ: `sql_safe_updates` là một lớp bảo vệ chống thao tác quá rộng do sơ suất. Nó không thay thế transaction, backup, phân quyền, review SQL hoặc kiểm tra số hàng bị ảnh hưởng.

## 2. sql_safe_updates không phải là một cờ trong sql_mode

Hai khái niệm có tên gần giống nhau nhưng là hai biến hệ thống độc lập:

| Thành phần | Bản chất | Ví dụ |
|---|---|---|
| `sql_mode` | Biến hệ thống chứa danh sách các mode phân tách bằng dấu phẩy; mỗi mode thay đổi một phần quy tắc cú pháp hoặc ngữ nghĩa SQL | `STRICT_TRANS_TABLES`, `ONLY_FULL_GROUP_BY`, `ANSI_QUOTES` |
| `sql_safe_updates` | Biến hệ thống dạng bật/tắt kiểm soát một số lệnh `UPDATE`/`DELETE` không có điều kiện key hoặc `LIMIT` | `0` = tắt, `1` = bật |

Tên `sql_safe_updates` có tiền tố `sql_`, nhưng điều đó không có nghĩa nó là thành viên của danh sách `sql_mode`. Bạn không tìm `SAFE_UPDATES` trong chuỗi `@@sql_mode` và cũng không bật nó bằng cách nối `'SAFE_UPDATES'` vào `sql_mode`.

Kiểm tra cả hai riêng biệt:

```sql
SELECT
    @@SESSION.sql_mode AS session_sql_mode,
    @@SESSION.sql_safe_updates AS session_safe_updates;

SHOW SESSION VARIABLES LIKE 'sql_mode';
SHOW SESSION VARIABLES LIKE 'sql_safe_updates';
```

Kết quả `sql_mode` là một chuỗi như `ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,...` tùy phiên bản và cấu hình. `sql_safe_updates` trả về giá trị bật/tắt riêng.

### 2.1. Một số cờ sql_mode thường gặp

Các mode sau là ví dụ về thành viên thực sự của `sql_mode`:

| Mode | Tác động tổng quát |
|---|---|
| `STRICT_TRANS_TABLES` | Áp dụng kiểm tra nghiêm ngặt đối với dữ liệu không hợp lệ hoặc thiếu giá trị trên bảng transactional; hành vi với bảng nontransactional có một số khác biệt |
| `STRICT_ALL_TABLES` | Áp dụng strict handling rộng hơn cho các loại bảng; chi tiết phụ thuộc loại thao tác và engine |
| `ONLY_FULL_GROUP_BY` | Kiểm soát việc chọn cột không tổng hợp trong truy vấn `GROUP BY` |
| `ANSI_QUOTES` | Dùng dấu nháy kép để quote identifier thay vì string literal |
| `NO_ENGINE_SUBSTITUTION` | Báo lỗi khi engine được yêu cầu không khả dụng, thay vì âm thầm thay bằng engine khác trong các trường hợp được mode điều chỉnh |
| `ERROR_FOR_DIVISION_BY_ZERO` | Ảnh hưởng cách xử lý phép chia cho 0 trong các ngữ cảnh được MySQL quy định |

Danh sách mode mặc định và trạng thái hỗ trợ có thể thay đổi giữa các phiên bản MySQL. Một số mode cũ được gộp, thay đổi hoặc loại bỏ. Hãy xem chính chuỗi `@@SESSION.sql_mode` của server đang sử dụng và tài liệu đúng phiên bản.

### 2.2. Hai biến có thể được cấu hình độc lập

Ví dụ một session có strict mode nhưng không bật safe updates:

```sql
SET SESSION sql_mode = 'STRICT_TRANS_TABLES';
SET SESSION sql_safe_updates = 0;
```

Hoặc session bật safe updates mà không thay đổi danh sách SQL mode:

```sql
SET SESSION sql_safe_updates = 1;
```

Trong ứng dụng thực tế, nên tránh gán lại toàn bộ `sql_mode` chỉ để thay đổi một cờ vì có thể vô tình loại bỏ các mode đang cần. `sql_safe_updates` được quản lý bằng biến riêng.

## 3. Kiểm tra trạng thái safe updates

### 3.1. Xem giá trị SESSION và GLOBAL

```sql
SELECT
    @@GLOBAL.sql_safe_updates AS global_safe_updates,
    @@SESSION.sql_safe_updates AS session_safe_updates;
```

- `@@GLOBAL.sql_safe_updates` là giá trị mặc định ở cấp server, được dùng để khởi tạo các session mới.
- `@@SESSION.sql_safe_updates` là giá trị đang áp dụng cho connection hiện tại.

Hai giá trị có thể khác nhau. Nếu một client đã kết nối trước khi GLOBAL được thay đổi, session đó thường giữ giá trị cũ. Vì vậy, sau khi thay đổi cấu hình GLOBAL, cần kiểm tra lại các kết nối mới và các connection pool đang hoạt động.

### 3.2. Dùng SHOW VARIABLES

```sql
SHOW GLOBAL VARIABLES LIKE 'sql_safe_updates';
SHOW SESSION VARIABLES LIKE 'sql_safe_updates';
```

Nếu công cụ quản trị chỉ hiển thị giá trị session, đừng mặc định rằng đó là cấu hình global. Khi điều tra khác biệt giữa hai môi trường, lấy cả hai giá trị cùng `VERSION()` và `@@SESSION.sql_mode`.

### 3.3. Giá trị mặc định

Trong MySQL, `sql_safe_updates` mặc định thường là `OFF` (`0`). Công cụ client có thể tự bật biến này cho session, nên giá trị nhìn thấy từ MySQL Workbench hoặc một client khác có thể khác giữa các kết nối dù cấu hình server không đổi.

Không dựa vào giá trị mặc định của bản cài đặt. Hãy kiểm tra trực tiếp session mà ứng dụng hoặc công cụ đang dùng.

## 4. Bật và tắt sql_safe_updates

### 4.1. Bật cho session hiện tại

Đây là cách phù hợp để thử nghiệm hoặc bảo vệ một kết nối quản trị:

```sql
SET SESSION sql_safe_updates = 1;

SELECT @@SESSION.sql_safe_updates;
```

Giá trị `1` bật safe updates cho connection hiện tại. Các session khác không bị thay đổi.

Có thể viết ngắn:

```sql
SET sql_safe_updates = ON;
```

Trong ngữ cảnh `SET`, biến session là phạm vi mặc định nếu không chỉ định `GLOBAL`.

### 4.2. Tắt cho session hiện tại

```sql
SET SESSION sql_safe_updates = 0;
```

Chỉ tắt khi có lý do rõ ràng, đã xác định đúng bảng và phạm vi dữ liệu, đã xem trước tập hàng sẽ tác động và có phương án khôi phục. Không biến việc tắt safe updates thành thói quen mỗi khi gặp lỗi 1175.

Nếu cần tắt tạm trong một session, lưu giá trị ban đầu để khôi phục:

```sql
SET @previous_safe_updates = @@SESSION.sql_safe_updates;

-- Chỉ thực hiện sau khi đã xác minh câu lệnh và phạm vi dữ liệu
SET SESSION sql_safe_updates = 0;

-- Chạy thao tác quản trị đã được kiểm tra ở đây

-- Khôi phục trạng thái ban đầu trong cùng connection
SET SESSION sql_safe_updates = @previous_safe_updates;
```

Nếu thao tác bị lỗi giữa chừng hoặc client ngắt kết nối, hãy mở một session mới và xác minh trạng thái trước khi tiếp tục. Biến người dùng `@previous_safe_updates` chỉ tồn tại trong session đã tạo nó.

### 4.3. Đặt giá trị GLOBAL

Tài khoản có quyền quản trị biến hệ thống phù hợp có thể đặt mặc định cho các session mới:

```sql
SET GLOBAL sql_safe_updates = 1;
```

Thay đổi này không tự bật safe updates cho những session đang mở. Các kết nối mới sẽ kế thừa giá trị GLOBAL tại thời điểm tạo session, trừ khi client hoặc ứng dụng ghi đè bằng cấu hình session.

Để thay đổi có hiệu lực sau restart, cấu hình trong file `my.cnf`/`my.ini` hoặc dùng cơ chế lưu cấu hình bền vững được phiên bản hỗ trợ. Ví dụ trong file cấu hình server:

```ini
[mysqld]
sql_safe_updates = ON
```

MySQL 8.0 có `SET PERSIST` cho các biến hệ thống phù hợp:

```sql
SET PERSIST sql_safe_updates = ON;
```

`SET GLOBAL` thay đổi runtime; `SET PERSIST` vừa thay đổi runtime vừa lưu cấu hình để áp dụng sau restart. Hãy xác minh phiên bản, quyền và chính sách quản lý cấu hình trước khi dùng. Trong môi trường cloud hoặc container, nên cập nhật nguồn cấu hình chuẩn của dịch vụ để tránh bị ghi đè khi tái triển khai.

## 5. Những câu lệnh bị chặn và được phép

Giả sử có bảng:

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    department_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    last_login DATETIME NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employees_department (department_id)
) ENGINE = InnoDB;
```

Bật safe updates trong session:

```sql
SET SESSION sql_safe_updates = 1;
```

### 5.1. UPDATE không có WHERE hoặc LIMIT

```sql
UPDATE employees
SET status = 'INACTIVE';
```

Câu lệnh không có điều kiện `WHERE` và cũng không có `LIMIT`, nên bị safe update mode từ chối.

### 5.2. DELETE không có WHERE hoặc LIMIT

```sql
DELETE FROM employees;
```

Câu lệnh cũng bị từ chối vì có thể xóa toàn bộ hàng trong bảng.

### 5.3. WHERE sử dụng key

```sql
UPDATE employees
SET status = 'INACTIVE'
WHERE employee_id = 105;

DELETE FROM employees
WHERE employee_id = 105;
```

`employee_id` là primary key, được dùng trong điều kiện lọc theo cách hỗ trợ tra cứu bằng key. Những câu lệnh này đáp ứng điều kiện key của safe updates.

Một ví dụ khác sử dụng index trên `department_id`:

```sql
UPDATE employees
SET status = 'REVIEW'
WHERE department_id = 20;
```

Điều kiện sử dụng cột có index. Tuy nhiên, nếu phòng ban 20 có gần như toàn bộ nhân viên, câu lệnh vẫn có thể tác động đến rất nhiều hàng. Safe updates chỉ kiểm tra một điều kiện kỹ thuật, không hiểu ý định nghiệp vụ.

### 5.4. WHERE không dùng key và không có LIMIT

```sql
UPDATE employees
SET status = 'INACTIVE'
WHERE last_login < '2025-01-01';
```

Giả sử `last_login` không có index. Điều kiện này không dùng key và không có `LIMIT`, nên safe update mode có thể từ chối. Nếu truy vấn nghiệp vụ thường xuyên lọc theo `last_login`, có thể đánh giá việc tạo index, nhưng không tạo index chỉ để vượt qua safe updates. Cần xét workload và kế hoạch truy vấn.

### 5.5. LIMIT có thể đáp ứng điều kiện safe updates

```sql
UPDATE employees
SET status = 'INACTIVE'
WHERE last_login < '2025-01-01'
LIMIT 100;
```

Mệnh đề `LIMIT` giúp câu lệnh đáp ứng điều kiện bảo vệ dù `WHERE` không dùng key. Nhưng nó chỉ giới hạn số hàng được cập nhật; nếu không có `ORDER BY`, không nên giả định chính xác hàng nào sẽ được chọn. Câu lệnh vẫn có thể tác động đến 100 hàng ngoài dự kiến.

Với tác vụ batch, hãy chọn thứ tự và điều kiện rõ ràng:

```sql
UPDATE employees
SET status = 'INACTIVE'
WHERE last_login < '2025-01-01'
ORDER BY last_login, employee_id
LIMIT 100;
```

Tốt hơn nữa, nếu có thể xác định tập khóa chính trước, hãy lưu danh sách ID mục tiêu rồi cập nhật theo ID đó. `LIMIT` là giới hạn số lượng, không phải bằng chứng dữ liệu được chọn đúng.

## 6. Safe updates không bảo đảm câu lệnh an toàn về nghiệp vụ

Một câu lệnh có thể vượt qua safe update mode nhưng vẫn sai nghiêm trọng.

Ví dụ:

```sql
UPDATE employees
SET status = 'INACTIVE'
WHERE employee_id > 0;
```

Điều kiện có sử dụng primary key, nhưng nếu mọi ID đều dương thì câu lệnh vẫn cập nhật gần như toàn bộ bảng. Safe updates không đánh giá số hàng ước lượng, không hiểu mục tiêu nghiệp vụ và không yêu cầu xác nhận số lượng bị ảnh hưởng.

Tương tự:

```sql
DELETE FROM employees
WHERE department_id = 20
LIMIT 1000;
```

Câu lệnh có index và `LIMIT`, nhưng vẫn có thể xóa 1.000 hàng hợp lệ mà người vận hành không định xóa.

Vì vậy, hãy dùng quy trình kiểm tra độc lập:

1. Viết điều kiện `WHERE` theo khóa hoặc tiêu chí nghiệp vụ chính xác.
2. Chạy `SELECT` với cùng điều kiện để xem các hàng mục tiêu.
3. Đếm số hàng dự kiến bị tác động.
4. Kiểm tra các giá trị trước/sau và khóa chính.
5. Thực hiện trong transaction nếu engine và thao tác cho phép.
6. Kiểm tra số hàng ảnh hưởng và commit khi kết quả đúng.

Ví dụ với InnoDB:

```sql
START TRANSACTION;

SELECT employee_id, status
FROM employees
WHERE employee_id BETWEEN 100 AND 120
ORDER BY employee_id
FOR UPDATE;

UPDATE employees
SET status = 'INACTIVE'
WHERE employee_id BETWEEN 100 AND 120;

SELECT ROW_COUNT() AS affected_rows;

-- Nếu số hàng và dữ liệu đúng:
COMMIT;

-- Nếu không đúng, thay COMMIT bằng ROLLBACK trước khi kết thúc transaction.
```

Ví dụ minh họa cách khóa và kiểm tra tập hàng trong transaction. Trong quy trình thực tế, không gửi cả `COMMIT` lẫn `ROLLBACK` như một batch cố định; người vận hành chọn một trong hai sau khi xem kết quả. Transaction cần được giữ ngắn để tránh khóa dữ liệu lâu.

## 7. Quy trình xử lý lỗi 1175

Lỗi 1175 thường xuất hiện khi safe update mode đang bật và câu lệnh `UPDATE`/`DELETE` không thỏa điều kiện key hoặc `LIMIT`.

Khi gặp lỗi:

### Bước 1: Xác nhận session đang bật

```sql
SELECT @@SESSION.sql_safe_updates;
```

Nếu kết quả là `1`, safe updates đang áp dụng cho connection hiện tại.

### Bước 2: Xem lại câu lệnh và mục tiêu dữ liệu

Đừng chỉ thêm `LIMIT 1` hoặc tắt safe updates để làm lỗi biến mất. Hãy xác định bảng, điều kiện và số hàng nghiệp vụ cần thay đổi.

### Bước 3: Kiểm tra tập hàng bằng SELECT

```sql
SELECT employee_id, last_login, status
FROM employees
WHERE last_login < '2025-01-01'
ORDER BY last_login, employee_id;

SELECT COUNT(*) AS target_rows
FROM employees
WHERE last_login < '2025-01-01';
```

Nếu kết quả quá lớn hoặc không đúng, sửa điều kiện. Nếu truy vấn không sử dụng index, dùng `EXPLAIN SELECT` để hiểu access path:

```sql
EXPLAIN
SELECT employee_id
FROM employees
WHERE last_login < '2025-01-01';
```

### Bước 4: Chọn cách thực hiện phù hợp

- Nếu có khóa xác định chính xác, dùng key trong `WHERE`.
- Nếu cần batch, dùng `ORDER BY` và `LIMIT` có chủ đích, đồng thời theo dõi tiến độ.
- Nếu điều kiện lọc thường xuyên và có ý nghĩa về hiệu năng, đánh giá index phù hợp.
- Nếu thực sự cần thao tác không dùng key, chỉ tắt safe updates trong đúng session sau khi review và có biện pháp kiểm soát khác.

### Bước 5: Khôi phục cấu hình

Nếu đã tắt `sql_safe_updates` tạm thời, bật lại hoặc khôi phục giá trị cũ trong cùng session. Kiểm tra lại `@@SESSION.sql_safe_updates` trước khi kết thúc công việc.

## 8. Ảnh hưởng của SQL client và MySQL Workbench

`sql_safe_updates` là biến của MySQL Server, nhưng một client có thể bật nó khi mở connection. MySQL Workbench có tùy chọn Safe Updates trong phần SQL Editor Preferences. Khi tùy chọn này được bật, Workbench có thể thiết lập safe update mode cho session mà nó sử dụng.

Do đó, có thể xảy ra tình huống:

- Kết nối bằng terminal chạy được một câu `UPDATE`.
- Chạy cùng câu lệnh trong Workbench lại nhận lỗi 1175.
- `@@GLOBAL.sql_safe_updates` vẫn là `0`, nhưng `@@SESSION.sql_safe_updates` của Workbench là `1`.

Khi gặp khác biệt, hãy kiểm tra biến SESSION từ đúng tab/kết nối đang chạy câu lệnh. Nếu thay đổi tùy chọn Safe Updates trong Workbench, có thể cần kết nối lại để cấu hình mới được áp dụng cho session mới; hành vi cụ thể phụ thuộc phiên bản Workbench.

Không nên tắt bảo vệ toàn server chỉ để làm một client hết lỗi. Nếu chỉ một công cụ quản trị cần thay đổi hành vi, hãy điều chỉnh phạm vi client/session và vẫn giữ quy trình kiểm tra dữ liệu.

## 9. Connection pool và session state

`sql_safe_updates` có phạm vi SESSION. Nếu ứng dụng dùng connection pool, mỗi connection vật lý có thể giữ giá trị riêng. Ví dụ, một connection được khởi tạo với `sql_safe_updates = 1`, connection khác có thể đang là `0` do cấu hình khác hoặc thay đổi thủ công.

Để hành vi nhất quán:

- Đặt giá trị session trong bước khởi tạo connection của pool.
- Không thay đổi session variable tùy tiện trong một request rồi trả connection về pool mà không khôi phục.
- Nếu pool hỗ trợ reset session state, xác minh biến này có được reset hay không.
- Kiểm tra `@@SESSION.sql_safe_updates` trên connection thực tế khi điều tra lỗi.
- Không giả định thay đổi GLOBAL sẽ cập nhật các connection vật lý đã tồn tại trong pool.

Với ứng dụng nghiệp vụ, safe updates thường được cấu hình như một biện pháp bảo vệ bổ sung cho tài khoản hoặc công cụ vận hành. Không dùng nó để thay thế phân quyền: tài khoản ứng dụng vẫn cần quyền `UPDATE`/`DELETE` tối thiểu theo bảng và phạm vi công việc.

## 10. So sánh sql_safe_updates với các cơ chế bảo vệ khác

| Cơ chế | Bảo vệ điều gì? | Giới hạn |
|---|---|---|
| `sql_safe_updates` | Chặn một số UPDATE/DELETE thiếu key trong WHERE và thiếu LIMIT | Không hiểu nghiệp vụ, không giới hạn mọi câu lệnh rộng và không thay thế quyền truy cập |
| `sql_mode` strict | Kiểm soát một số dữ liệu thiếu hoặc không hợp lệ | Không ngăn cập nhật/xóa hàng loạt hợp lệ về cú pháp |
| Primary key/foreign key/unique/check | Bảo vệ định danh và một số quy tắc toàn vẹn dữ liệu | Không xác định người dùng có định cập nhật đúng tập hàng hay không |
| Transaction InnoDB | Cho phép commit/rollback một nhóm thay đổi và kiểm soát đồng thời | Cần thiết kế phạm vi, khóa và xử lý lỗi đúng; không cứu được thao tác đã commit |
| GRANT/REVOKE | Giới hạn tài khoản được phép đọc/ghi đối tượng nào | Quyền UPDATE trên bảng vẫn có thể cho phép cập nhật nhầm nhiều hàng |
| Backup và point-in-time recovery | Hỗ trợ khôi phục dữ liệu sau sự cố | Tốn thời gian và không thay thế kiểm tra trước thao tác |
| Review/preview bằng SELECT | Giúp người vận hành xác nhận tập hàng mục tiêu | Phụ thuộc quy trình và sự cẩn thận của người thực hiện |

Các cơ chế này bổ sung cho nhau. Một quy trình vận hành tốt dùng phân quyền tối thiểu, safe updates cho session quản trị, preview dữ liệu, transaction phù hợp và backup có thể khôi phục.

## 11. Những trường hợp không nên hiểu nhầm

### 11.1. SELECT không bị safe updates chặn

`sql_safe_updates` tập trung vào `UPDATE` và `DELETE`. Nó không phải giới hạn chung cho mọi truy vấn `SELECT` và không tự ngăn một truy vấn đọc toàn bộ bảng.

### 11.2. INSERT không dùng cơ chế này

`INSERT`, `REPLACE`, `TRUNCATE TABLE`, `DROP TABLE` và các DDL khác có quy tắc riêng; không dựa vào `sql_safe_updates` để bảo vệ các thao tác này. Đặc biệt, `TRUNCATE TABLE` không phải `DELETE` có `WHERE` và không được safe updates bảo vệ như lệnh DELETE thông thường.

### 11.3. Có key không có nghĩa là ít hàng

Điều kiện `WHERE id > 0` sử dụng cột khóa nhưng có thể khớp hầu hết bảng. Safe updates không phải bộ ước lượng số hàng và không thay thế việc chạy `SELECT COUNT(*)` hoặc xem dữ liệu mục tiêu.

### 11.4. Có LIMIT không có nghĩa là đúng hàng

`LIMIT 100` giới hạn số hàng được xử lý, nhưng nếu không có thứ tự xác định, tập hàng có thể không ổn định. Kết hợp `ORDER BY` với khóa ổn định và điều kiện nghiệp vụ, sau đó theo dõi từng batch.

### 11.5. Safe updates không thay thế quyền database

Nếu tài khoản không có quyền `UPDATE` hoặc `DELETE`, bật safe updates không cấp thêm quyền. Ngược lại, tài khoản có quyền ghi vẫn có thể thực hiện các thao tác mà safe updates cho phép. Hãy thiết kế `GRANT` theo nguyên tắc quyền tối thiểu.

## 12. Bộ truy vấn kiểm tra nhanh

```sql
-- Phiên bản và trạng thái SQL mode / safe updates
SELECT
    VERSION() AS server_version,
    @@GLOBAL.sql_mode AS global_sql_mode,
    @@SESSION.sql_mode AS session_sql_mode,
    @@GLOBAL.sql_safe_updates AS global_safe_updates,
    @@SESSION.sql_safe_updates AS session_safe_updates;

-- Kiểm tra riêng các cờ sql_mode
SELECT
    FIND_IN_SET('STRICT_TRANS_TABLES', @@SESSION.sql_mode) > 0
        AS strict_trans_tables_enabled,
    FIND_IN_SET('ONLY_FULL_GROUP_BY', @@SESSION.sql_mode) > 0
        AS only_full_group_by_enabled,
    FIND_IN_SET('ANSI_QUOTES', @@SESSION.sql_mode) > 0
        AS ansi_quotes_enabled;

-- Bật safe updates cho session hiện tại
SET SESSION sql_safe_updates = 1;

-- Xác nhận lại
SELECT @@SESSION.sql_safe_updates;

-- Preview một thao tác cập nhật trước khi thực hiện
SELECT employee_id, status, last_login
FROM employees
WHERE employee_id BETWEEN 100 AND 120
ORDER BY employee_id;

SELECT COUNT(*) AS rows_to_update
FROM employees
WHERE employee_id BETWEEN 100 AND 120;
```

Các câu lệnh trên dùng tên bảng minh họa `employees`; hãy thay bằng schema thực tế và chỉ chạy truy vấn đọc để preview trước khi xây dựng lệnh thay đổi dữ liệu.

## 13. Checklist trước UPDATE hoặc DELETE

- [ ] Đã xác nhận đúng server, database và session đang làm việc.
- [ ] Đã kiểm tra `@@SESSION.sql_safe_updates` và `@@SESSION.sql_mode`.
- [ ] Đã xác định rõ mục tiêu nghiệp vụ và điều kiện `WHERE`.
- [ ] Đã chạy `SELECT` với cùng điều kiện và xem các khóa chính bị tác động.
- [ ] Đã đếm số hàng dự kiến thay đổi/xóa.
- [ ] Nếu dùng key, đã xác nhận đó là key/index phù hợp và điều kiện không quá rộng.
- [ ] Nếu dùng `LIMIT`, đã chọn thứ tự ổn định và có kế hoạch batch.
- [ ] Đã cân nhắc transaction, khóa và thời gian chạy.
- [ ] Đã có backup/khả năng khôi phục phù hợp với mức độ rủi ro.
- [ ] Nếu tạm tắt safe updates, đã lưu trạng thái cũ và có bước bật lại.
- [ ] Đã kiểm tra số hàng ảnh hưởng và dữ liệu sau thao tác.

## 14. Kết luận

`sql_safe_updates` là biến hệ thống độc lập với `sql_mode`. Nó giúp chặn một số câu lệnh `UPDATE`/`DELETE` không có điều kiện sử dụng key và cũng không có `LIMIT`, nhờ đó giảm nguy cơ vô tình tác động toàn bảng. Nó có thể được bật riêng cho session, đặt mặc định ở GLOBAL hoặc lưu trong cấu hình server.

Hãy phân biệt nó với các cờ thực sự nằm trong `sql_mode`, kiểm tra giá trị SESSION từ đúng connection và không xem safe updates là bảo đảm an toàn tuyệt đối. Trước mỗi thao tác ghi/xóa, vẫn cần preview tập hàng, xác nhận số lượng, dùng transaction khi phù hợp và duy trì phương án khôi phục dữ liệu.

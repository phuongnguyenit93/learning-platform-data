# PIPES_AS_CONCAT, phép nối chuỗi và khác biệt với toán tử OR

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Một chi tiết dễ gây lỗi khi chuyển ứng dụng hoặc dùng SQL mode khác nhau là toán tử hai dấu gạch đứng ||. Trong MySQL, || mặc định là toán tử logic OR; khi bật SQL mode PIPES_AS_CONCAT, nó trở thành toán tử nối chuỗi.

Sự thay đổi này ảnh hưởng cả ý nghĩa biểu thức lẫn độ ưu tiên toán tử. Một câu SQL có thể trả kết quả khác dù văn bản truy vấn không đổi. Bài học này giải thích hai cách hiểu của ||, cách quản lý mode theo session và global, đồng thời hướng dẫn viết SQL rõ nghĩa để tránh phụ thuộc cấu hình ngầm.

## 1. Hai ý nghĩa của toán tử ||

MySQL hỗ trợ hai cách diễn giải ||, phụ thuộc SQL mode:

| Cấu hình | Ý nghĩa của || | Ví dụ |
|---|---|---|
| Không bật PIPES_AS_CONCAT | Logic OR, tương đương OR | 1 || 0 cho kết quả TRUE (1) |
| Bật PIPES_AS_CONCAT | Nối chuỗi, tương tự phép ghép chuỗi | 1 || 0 tạo chuỗi '10' |

Ví dụ trong cấu hình mặc định thường gặp:

~~~sql
SELECT 1 || 0 AS result;
-- || được hiểu là OR, kết quả là 1
~~~

Khi PIPES_AS_CONCAT được bật:

~~~sql
SELECT 1 || 0 AS result;
-- || được hiểu là nối chuỗi, kết quả là '10'
~~~

Đây là khác biệt về ngữ nghĩa, không chỉ là khác biệt cách viết. Nếu cùng một ứng dụng kết nối đến hai MySQL server có SQL mode khác nhau, câu lệnh chứa || có thể trả kết quả khác nhau.

### 1.1. OR dùng để kết hợp điều kiện

OR là toán tử logic. Biểu thức trả TRUE khi ít nhất một điều kiện đúng:

~~~sql
SELECT *
FROM users
WHERE is_active = 1
   OR is_admin = 1;
~~~

Truy vấn lấy người dùng đang hoạt động hoặc người dùng là quản trị viên. Đây là phép kết hợp điều kiện; không phải phép nối văn bản.

### 1.2. Nối chuỗi tạo ra một giá trị văn bản

Khi muốn ghép các phần văn bản, có thể dùng hàm CONCAT:

~~~sql
SELECT CONCAT('My', 'SQL') AS product_name;
-- Kết quả: MySQL
~~~

Nếu PIPES_AS_CONCAT được bật, có thể viết:

~~~sql
SELECT 'My' || 'SQL' AS product_name;
-- Kết quả: MySQL
~~~

Tuy nhiên, CONCAT thể hiện rõ ý định nối chuỗi và không phụ thuộc việc PIPES_AS_CONCAT có được bật hay không. Với mã SQL dùng chung giữa nhiều môi trường, đây thường là lựa chọn dễ bảo trì hơn.

## 2. PIPES_AS_CONCAT là SQL mode

SQL mode là tập hợp các tùy chọn cấu hình cách MySQL xử lý cú pháp, dữ liệu không hợp lệ và một số quy tắc tương thích SQL. PIPES_AS_CONCAT thay đổi ý nghĩa toán tử || để dùng nó như phép nối chuỗi.

Xem mode của session hiện tại:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

Xem mode mặc định toàn server:

~~~sql
SELECT @@GLOBAL.sql_mode;
~~~

Kiểm tra riêng mode:

~~~sql
SELECT FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0
       AS pipes_as_concat_enabled;
~~~

FIND_IN_SET trả vị trí của phần tử trong danh sách phân tách bằng dấu phẩy; kết quả lớn hơn 0 nghĩa là mode đang bật. Không nên chỉ tìm chuỗi con bằng LIKE vì kiểm tra theo phần tử chính xác rõ nghĩa hơn.

### 2.1. SQL mode theo session

Mỗi kết nối MySQL có biến SESSION sql_mode riêng. Khi đặt mode cho session, thay đổi chỉ ảnh hưởng các câu lệnh được thực hiện trên kết nối đó:

~~~sql
SET SESSION sql_mode = 'PIPES_AS_CONCAT';
~~~

Câu lệnh trên thay thế toàn bộ danh sách mode của session bằng đúng một mode. Nó có thể vô tình tắt các mode quan trọng khác như STRICT_TRANS_TABLES hoặc ONLY_FULL_GROUP_BY. Trong ứng dụng thực tế, không nên gán một danh sách rút gọn nếu mục tiêu chỉ là bổ sung một mode.

Có thể thêm mode mà vẫn giữ các mode hiện tại:

~~~sql
SET SESSION sql_mode =
  IF(
    FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(
      ',',
      NULLIF(@@SESSION.sql_mode, ''),
      'PIPES_AS_CONCAT'
    )
  );
~~~

Trước khi thay đổi, có thể lưu giá trị cũ để khôi phục:

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;

-- Thực hiện thử nghiệm hoặc công việc cần mode mới.

SET SESSION sql_mode = @saved_sql_mode;
~~~

Biến @saved_sql_mode là biến người dùng của session hiện tại. Nó không được chia sẻ với session khác và mất khi kết nối kết thúc.

### 2.2. SQL mode theo global

GLOBAL sql_mode là giá trị mặc định được dùng để khởi tạo mode cho các kết nối mới. Thay đổi global không tự thay đổi mode của các session đang tồn tại.

Ví dụ, DBA có thể bổ sung mode cho các kết nối mới:

~~~sql
SET GLOBAL sql_mode =
  IF(
    FIND_IN_SET('PIPES_AS_CONCAT', @@GLOBAL.sql_mode) > 0,
    @@GLOBAL.sql_mode,
    CONCAT_WS(
      ',',
      NULLIF(@@GLOBAL.sql_mode, ''),
      'PIPES_AS_CONCAT'
    )
  );
~~~

Lệnh này cần quyền quản trị hệ thống phù hợp, chẳng hạn SYSTEM_VARIABLES_ADMIN trên các phiên bản MySQL hiện đại hoặc quyền quản trị tương ứng của phiên bản cũ. Sau khi thay đổi, kết nối mới sẽ nhận giá trị global mới; session hiện tại vẫn giữ @@SESSION.sql_mode cũ.

Kiểm tra bằng cách mở một kết nối mới rồi chạy:

~~~sql
SELECT @@SESSION.sql_mode;
~~~

Không dùng SET GLOBAL như một cách sửa tạm cho riêng một request của ứng dụng. Thay đổi global có phạm vi ảnh hưởng đến mọi kết nối mới của instance và cần được quản trị có kiểm soát.

### 2.3. Cấu hình tồn tại sau khi khởi động lại

SET GLOBAL thay đổi giá trị runtime; không phải mọi thay đổi runtime đều tự tồn tại sau khi MySQL khởi động lại. Có thể cấu hình sql_mode trong file cấu hình máy chủ:

~~~ini
[mysqld]
sql_mode=STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION,PIPES_AS_CONCAT
~~~

Danh sách trên chỉ là ví dụ. Hãy lấy danh sách mode hiện có của môi trường, xác định các mode cần giữ và bổ sung PIPES_AS_CONCAT theo chính sách. Ghi đè sql_mode bằng một danh sách thiếu mode có thể làm thay đổi hành vi khác của ứng dụng.

MySQL 8.0 còn hỗ trợ SET PERSIST để lưu một biến hệ thống động vào cấu hình được duy trì qua lần khởi động sau. Khi sử dụng, phải đặt toàn bộ giá trị sql_mode mong muốn và có quyền phù hợp; không coi SET PERSIST là thao tác chỉ thêm một phần tử nếu biểu thức gán đang thay thế cả danh sách.

## 3. PIPES_AS_CONCAT làm thay đổi cách đọc câu SQL

### 3.1. Một biểu thức, hai kết quả

Xét:

~~~sql
SELECT 1 || 0 + 2 AS result;
~~~

Khi mode tắt, || là OR và biểu thức được xử lý như một phép logic kết hợp với phép cộng theo thứ tự ưu tiên toán tử của MySQL. Khi mode bật, || là phép nối chuỗi và có độ ưu tiên khác. Vì vậy, không nên dựa vào biểu thức hỗn hợp để suy luận kết quả giữa các môi trường.

Khi biểu thức có nhiều loại toán tử, hãy dùng ngoặc để thể hiện thứ tự tính toán mong muốn và dùng CONCAT cho thao tác nối chuỗi. Điều này làm câu lệnh dễ đọc mà không cần người đọc biết SQL mode đang bật.

### 3.2. Độ ưu tiên toán tử thay đổi

Khi PIPES_AS_CONCAT không bật, || được xử lý như OR và có độ ưu tiên của toán tử OR. Khi mode bật, || trở thành toán tử nối chuỗi và có độ ưu tiên của phép nối chuỗi theo quy tắc MySQL, cao hơn các toán tử logic AND/OR.

Hệ quả: một biểu thức không có ngoặc có thể được nhóm toán hạng khác nhau tùy mode. Ví dụ, không nên viết:

~~~sql
SELECT first_name || last_name = 'AnNguyen'
FROM users;
~~~

Trong một môi trường, biểu thức có thể được phân tích như điều kiện logic; trong môi trường khác, nó có thể là phép nối chuỗi rồi so sánh. Hãy viết rõ:

~~~sql
SELECT CONCAT(first_name, last_name) = 'AnNguyen' AS matches
FROM users;
~~~

Nếu muốn thêm dấu cách:

~~~sql
SELECT CONCAT(first_name, ' ', last_name) AS full_name
FROM users;
~~~

Đối với biểu thức điều kiện, luôn dùng từ khóa OR:

~~~sql
SELECT *
FROM users
WHERE (is_active = 1)
   OR (is_admin = 1);
~~~

Không dùng || như cách viết tắt của OR trong mã SQL mới nếu câu lệnh cần chạy trên các môi trường có SQL mode khác nhau.

## 4. Khác biệt giữa OR, CONCAT và ||

| Nhu cầu | Cách viết nên dùng | Ý nghĩa |
|---|---|---|
| Kết hợp hai điều kiện | condition_a OR condition_b | Trả kết quả logic |
| Ghép hai chuỗi | CONCAT(a, b) | Trả giá trị chuỗi |
| Ghép chuỗi có dấu phân cách và bỏ qua đối số NULL | CONCAT_WS(separator, a, b) | Trả chuỗi đã ghép |
| Dùng || để ghép chuỗi trong hệ thống đã chuẩn hóa mode | a || b với PIPES_AS_CONCAT | Phụ thuộc SQL mode |

### 4.1. OR có logic ba giá trị

OR hoạt động theo logic TRUE, FALSE và UNKNOWN. Ví dụ:

~~~sql
SELECT
    TRUE OR FALSE AS true_or_false,
    FALSE OR FALSE AS false_or_false,
    NULL OR TRUE AS unknown_or_true,
    NULL OR FALSE AS unknown_or_false;
~~~

Kết quả lần lượt là TRUE, FALSE, TRUE và UNKNOWN. Đây là logic điều kiện; không tạo ra chuỗi mới.

### 4.2. CONCAT xử lý NULL

CONCAT trả NULL nếu một trong các đối số là NULL:

~~~sql
SELECT CONCAT('An', NULL, 'Nguyen') AS full_name;
-- Kết quả: NULL
~~~

Nếu muốn bỏ qua các đối số NULL sau dấu phân cách, dùng CONCAT_WS:

~~~sql
SELECT CONCAT_WS(' ', 'An', NULL, 'Nguyen') AS full_name;
-- Kết quả: An Nguyen
~~~

Đối số separator của CONCAT_WS không được NULL; nếu separator là NULL, kết quả là NULL. Chuỗi rỗng không giống NULL và không tự bị bỏ qua. Ví dụ CONCAT_WS(' ', 'An', '', 'Nguyen') có thể tạo khoảng trắng liên tiếp.

### 4.3. Chuẩn hóa chuỗi trước khi ghép

Nếu chuỗi NULL, rỗng hoặc chỉ có khoảng trắng đều được coi là không có nội dung theo nghiệp vụ, có thể chuẩn hóa:

~~~sql
SELECT CONCAT_WS(
         ' ',
         NULLIF(TRIM(first_name), ''),
         NULLIF(TRIM(middle_name), ''),
         NULLIF(TRIM(last_name), '')
       ) AS full_name
FROM users;
~~~

TRIM loại khoảng trắng ở hai đầu theo quy tắc của hàm; NULLIF đổi chuỗi rỗng thành NULL; CONCAT_WS bỏ qua các đối số NULL. Chỉ dùng cách này nếu nghiệp vụ thực sự xem các trạng thái đó tương đương. Nếu chuỗi rỗng là giá trị có ý nghĩa, hãy giữ nguyên.

## 5. Những tình huống dễ gây lỗi khi dùng ||

### 5.1. Điều kiện WHERE

Không viết:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID' || status = 'SHIPPED';
~~~

Nếu || được hiểu là OR, câu lệnh có thể chạy như mong muốn. Nếu PIPES_AS_CONCAT được bật, || có độ ưu tiên của phép nối chuỗi và biểu thức được phân tích theo cách khác; kết quả có thể sai mục đích do so sánh và ép kiểu. Không dựa vào biểu thức này để tạo điều kiện OR.

Viết rõ:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID'
   OR status = 'SHIPPED';
~~~

Hoặc dùng IN cho tập giá trị:

~~~sql
SELECT *
FROM orders
WHERE status IN ('PAID', 'SHIPPED');
~~~

### 5.2. Ghép mã định danh

Không dựa vào || để ghép mã:

~~~sql
-- Phụ thuộc PIPES_AS_CONCAT
SELECT region_code || '-' || order_number
FROM orders;
~~~

Viết:

~~~sql
SELECT CONCAT(region_code, '-', order_number) AS order_code
FROM orders;
~~~

Nếu một thành phần có thể NULL và muốn bỏ qua thành phần đó, hãy xác định quy tắc rõ bằng CONCAT_WS hoặc COALESCE; không thay NULL bằng chuỗi rỗng một cách tự động nếu điều đó làm mất ý nghĩa.

### 5.3. Biểu thức trong SELECT, ORDER BY và GROUP BY

Một biểu thức nối chuỗi có thể được dùng làm cột kết quả, khóa sắp xếp hoặc biểu thức nhóm. Nếu dùng ||, cách phân tích có thể thay đổi theo SQL mode:

~~~sql
SELECT CONCAT(last_name, ', ', first_name) AS display_name
FROM customers
ORDER BY display_name;
~~~

Khi biểu thức được đặt tên bằng alias, có thể dùng alias trong ORDER BY. Nếu cần GROUP BY theo cùng biểu thức, có thể lặp lại biểu thức CONCAT hoặc dùng alias theo cú pháp MySQL. Dùng CONCAT giữ ý nghĩa nối chuỗi ổn định.

### 5.4. SQL động

Nếu xây dựng SQL động trong procedure hoặc ứng dụng, việc ghép chuỗi SQL phải dùng thao tác chuỗi có chủ đích. Không viết biểu thức tạo SQL bằng || nếu chưa bảo đảm mode của session thực thi:

~~~sql
SET @sql_text = CONCAT(
    'SELECT order_id FROM orders WHERE status = ',
    QUOTE('PAID')
);
PREPARE stmt FROM @sql_text;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
~~~

Ví dụ trên minh họa ghép câu SQL. Trong ứng dụng, nên dùng prepared statement với bind parameter cho giá trị thay vì nối trực tiếp input vào câu lệnh. Identifier động không bind như giá trị thông thường; cần allowlist và quote đúng cách.

## 6. Ảnh hưởng đến prepared statement và stored program

### 6.1. Prepared statement

Prepared statement được phân tích khi prepare. Vì PIPES_AS_CONCAT thay đổi cách parser hiểu ||, mode có hiệu lực tại thời điểm chuẩn bị câu lệnh có thể ảnh hưởng đến cách biểu thức được phân tích.

Ví dụ minh họa trong một session:

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode = CONCAT_WS(
    ',',
    NULLIF(@@SESSION.sql_mode, ''),
    'PIPES_AS_CONCAT'
);

PREPARE stmt FROM 'SELECT 1 || 0 AS result';
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET SESSION sql_mode = @saved_sql_mode;
~~~

Khi thử nghiệm, kiểm tra mode trước để tránh thêm trùng và bảo đảm câu lệnh được prepare trong đúng mode mong muốn. Nếu đổi mode, hãy prepare lại statement để kết quả thử nghiệm phản ánh cú pháp được phân tích dưới mode mới.

Trong ứng dụng Java, driver có thể dùng server-side hoặc client-side prepared statement tùy cấu hình. Dù cách triển khai khác nhau, vẫn nên tránh || cho mã SQL cần có ngữ nghĩa nhất quán qua các server.

### 6.2. Stored procedure và stored function

MySQL lưu SQL mode có hiệu lực khi stored procedure hoặc stored function được tạo. Khi routine chạy, nó sử dụng mode đã được ghi nhận cùng routine, thay vì mặc nhiên lấy mode hiện tại của caller cho toàn bộ cách phân tích phần thân routine.

Điều này có nghĩa routine chứa || có thể tiếp tục mang ngữ nghĩa tại thời điểm tạo ngay cả khi global/session mode của server đã thay đổi. Khi thay đổi chính sách SQL mode, hãy kiểm tra routine hiện có và xem định nghĩa bằng:

~~~sql
SHOW CREATE PROCEDURE procedure_name;
SHOW CREATE FUNCTION function_name;
~~~

Nếu cần routine dùng ngữ nghĩa khác, hãy cập nhật và tạo lại routine trong môi trường có SQL mode đã xác định. Dùng CONCAT và OR tường minh sẽ giúp routine ít phụ thuộc vào mode hơn.

### 6.3. Trigger và sự nhất quán triển khai

Trigger cũng lưu SQL mode tại thời điểm tạo. Khi di chuyển schema giữa các môi trường, cần kiểm tra SQL mode dùng khi tạo procedure, function và trigger. Một migration chạy ở hai môi trường với mode khác nhau có thể tạo các stored program có ngữ nghĩa khác nhau nếu chúng chứa toán tử phụ thuộc mode.

Kiểm tra định nghĩa trigger:

~~~sql
SHOW CREATE TRIGGER trigger_name;
~~~

Đưa SQL mode dự kiến vào quy trình triển khai và chạy migration bằng cùng cấu hình trên development, staging và production.

## 7. Cách chuyển đổi hoặc chuẩn hóa SQL mode

### 7.1. Kiểm tra trước khi thay đổi

Chạy:

~~~sql
SELECT @@GLOBAL.sql_mode AS global_mode,
       @@SESSION.sql_mode AS session_mode,
       FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0
         AS pipes_as_concat_enabled;
~~~

Lưu lại giá trị hiện tại và xác định kết nối nào cần thay đổi. Không chỉnh global chỉ để kiểm tra một truy vấn cá nhân.

### 7.2. Bật trong một session lab

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SET SESSION sql_mode =
  IF(
    FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'PIPES_AS_CONCAT')
  );

SELECT @@SESSION.sql_mode;
SELECT 1 || 0 AS concatenated_value;

SET SESSION sql_mode = @saved_sql_mode;
~~~

Sau khi khôi phục, xác minh mode không còn thay đổi so với giá trị đã lưu. Nếu session ban đầu đã bật mode, câu lệnh thêm sẽ giữ nguyên danh sách.

### 7.3. Bật cho kết nối mới

DBA có thể đặt global mode khi đã đánh giá tác động lên toàn bộ ứng dụng:

~~~sql
SET GLOBAL sql_mode =
  IF(
    FIND_IN_SET('PIPES_AS_CONCAT', @@GLOBAL.sql_mode) > 0,
    @@GLOBAL.sql_mode,
    CONCAT_WS(',', NULLIF(@@GLOBAL.sql_mode, ''), 'PIPES_AS_CONCAT')
  );
~~~

Mở kết nối mới và kiểm tra @@SESSION.sql_mode. Các kết nối cũ không tự nhận giá trị global mới. Với connection pool, cần recycle hoặc tạo lại connection theo kế hoạch để các kết nối mới nhận cấu hình.

### 7.4. Tắt mode có kiểm soát

Nếu cần bỏ PIPES_AS_CONCAT, ưu tiên khôi phục giá trị session đã lưu trong cùng kết nối:

~~~sql
SET SESSION sql_mode = @saved_sql_mode;
~~~

Nếu thay đổi cấu hình global hoặc file cấu hình, hãy xây dựng lại danh sách mode mong muốn từ cấu hình chuẩn đã quản lý. Không thay toàn bộ danh sách bằng chuỗi rỗng chỉ để tắt một mode; thao tác đó có thể làm mất các quy tắc kiểm tra dữ liệu quan trọng.

## 8. Khuyến nghị khi viết SQL

### 8.1. Dùng từ khóa OR cho logic

~~~sql
SELECT *
FROM products
WHERE category = 'BOOK'
   OR category = 'MAGAZINE';
~~~

Hoặc:

~~~sql
SELECT *
FROM products
WHERE category IN ('BOOK', 'MAGAZINE');
~~~

Từ khóa OR mô tả trực tiếp điều kiện logic và không bị thay đổi bởi PIPES_AS_CONCAT.

### 8.2. Dùng CONCAT cho nối chuỗi

~~~sql
SELECT CONCAT(order_prefix, '-', order_number) AS order_code
FROM orders;
~~~

CONCAT cho biết rõ các đối số được ghép thành chuỗi. Câu lệnh không phụ thuộc SQL mode và dễ chuyển giữa MySQL cùng các lớp truy cập dữ liệu.

### 8.3. Dùng CONCAT_WS khi cần separator

~~~sql
SELECT CONCAT_WS(
    ' / ',
    NULLIF(TRIM(country), ''),
    NULLIF(TRIM(city), ''),
    NULLIF(TRIM(district), '')
) AS address_summary
FROM customer_addresses;
~~~

CONCAT_WS phù hợp khi cần dấu phân cách và muốn bỏ qua thành phần NULL. Việc chuyển chuỗi rỗng hoặc khoảng trắng thành NULL phải theo quy tắc nghiệp vụ.

### 8.4. Dùng ngoặc khi biểu thức có nhiều toán tử

Ngoặc giúp người đọc hiểu thứ tự đánh giá và tránh phụ thuộc vào bảng precedence. Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE (status = 'PAID' OR status = 'SHIPPED')
  AND created_at >= '2026-01-01';
~~~

Không trộn || với AND, OR, phép cộng hoặc phép so sánh trong biểu thức phức tạp. Nếu || có nghĩa nối chuỗi, chuyển sang CONCAT; nếu có nghĩa logic, chuyển sang OR.

## 9. Tác động đến tính tương thích giữa môi trường

SQL mode có thể khác giữa local, test, staging, production, replica hoặc các phiên bản server. Các nguồn tạo khác biệt gồm:

- File cấu hình máy chủ khác nhau.
- Tham số khởi chạy mysqld khác nhau.
- Lệnh SET GLOBAL đã được chạy trong thời gian vận hành.
- Ứng dụng hoặc connection pool thay đổi SESSION sql_mode.
- Migration tạo stored procedure, function hoặc trigger dưới mode khác.

Với mỗi môi trường, hãy lưu lại:

~~~sql
SELECT VERSION() AS mysql_version,
       @@GLOBAL.sql_mode AS global_sql_mode,
       @@SESSION.sql_mode AS session_sql_mode;
~~~

Kiểm tra mode bằng tài khoản ứng dụng thực tế, vì session mode của ứng dụng có thể khác session của DBA. Trong hệ thống có nhiều replica, kiểm tra từng instance cần thiết và bảo đảm chính sách mode thống nhất.

Nếu mã cũ dùng || để biểu diễn OR, bật PIPES_AS_CONCAT có thể làm thay đổi kết quả hoặc khiến câu lệnh không còn đúng mục đích. Ngược lại, nếu mã dùng || để ghép chuỗi, chạy trên instance không bật mode có thể tạo kết quả logic hoặc ép kiểu ngoài dự kiến. Hãy rà soát mã nguồn, migration, view, routine và truy vấn được sinh động trước khi thay đổi mode ở quy mô toàn hệ thống.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| 1 || 0 trả 1 thay vì chuỗi 10 | Session không bật PIPES_AS_CONCAT nên || là OR | Dùng CONCAT('1', '0') hoặc kiểm tra mode |
| Điều kiện WHERE trả kết quả bất ngờ | || bị hiểu là nối chuỗi thay vì OR | Viết lại bằng từ khóa OR hoặc IN |
| SQL chạy khác nhau giữa local và production | SQL mode của hai session/instance khác nhau | So sánh @@SESSION.sql_mode và @@GLOBAL.sql_mode |
| SET SESSION không ảnh hưởng kết nối khác | SQL mode là trạng thái riêng của session | Thay đổi trên đúng connection hoặc cấu hình global cho kết nối mới |
| SET GLOBAL nhưng ứng dụng đang chạy vẫn giữ hành vi cũ | Các session hiện tại không tự nhận global mode mới | Tạo lại/recycle connection theo kế hoạch |
| Bổ sung mode làm mất strict mode | Gán một danh sách sql_mode rút gọn và ghi đè các mode cũ | Thêm phần tử có kiểm tra hoặc dùng danh sách chuẩn đầy đủ |
| Stored procedure vẫn xử lý || theo nghĩa cũ | Routine giữ SQL mode tại thời điểm tạo | Kiểm tra SHOW CREATE và tạo lại routine với mode chuẩn |
| CONCAT trả NULL | Có ít nhất một đối số NULL | Xác định ý nghĩa NULL; dùng COALESCE hoặc CONCAT_WS khi phù hợp |

Khi điều tra, luôn xác định câu lệnh chạy trong session nào, mode ở thời điểm prepare/parse là gì và routine được tạo dưới mode nào. Không kết luận từ @@GLOBAL.sql_mode nếu câu lệnh được thực thi bởi một session có mode riêng.

## 11. Bài thực hành: quan sát PIPES_AS_CONCAT

Thực hiện trong MySQL lab bằng một kết nối riêng. Bài thực hành lưu và khôi phục session mode ban đầu.

**Bước 1 — Ghi nhận cấu hình ban đầu.**

~~~sql
SET @saved_sql_mode = @@SESSION.sql_mode;

SELECT @@SESSION.sql_mode,
       FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0
         AS pipes_as_concat_enabled;
~~~

Nếu mode đã bật, ghi nhận trạng thái đó. Để quan sát hành vi mặc định OR, cần một session thử nghiệm mà mode chưa bật hoặc một kết nối lab được cấu hình không có mode này.

**Bước 2 — Thử phép OR khi mode tắt.**

~~~sql
SELECT 1 || 0 AS pipe_result,
       1 OR 0 AS explicit_or;
~~~

Khi mode tắt, hai cột có cùng ý nghĩa logic và trả TRUE (1).

**Bước 3 — Bật PIPES_AS_CONCAT cho session.**

~~~sql
SET SESSION sql_mode =
  IF(
    FIND_IN_SET('PIPES_AS_CONCAT', @@SESSION.sql_mode) > 0,
    @@SESSION.sql_mode,
    CONCAT_WS(',', NULLIF(@@SESSION.sql_mode, ''), 'PIPES_AS_CONCAT')
  );

SELECT @@SESSION.sql_mode;
~~~

**Bước 4 — Thử lại cùng biểu thức.**

~~~sql
SELECT 1 || 0 AS pipe_result,
       1 OR 0 AS explicit_or,
       CONCAT('1', '0') AS explicit_concat;
~~~

Khi mode bật, pipe_result là chuỗi 10, explicit_or vẫn là 1 và explicit_concat luôn là 10. Đây là bằng chứng hai cách viết có ngữ nghĩa khác nhau.

**Bước 5 — Thử nối tên.**

~~~sql
SELECT CONCAT_WS(' ', 'Nguyen', NULL, 'An') AS full_name;
SELECT CONCAT('Nguyen', ' ', 'An') AS full_name;
~~~

Quan sát cách CONCAT và CONCAT_WS xử lý đối số NULL.

**Bước 6 — Khôi phục session.**

~~~sql
SET SESSION sql_mode = @saved_sql_mode;
SELECT @@SESSION.sql_mode;
~~~

Đóng kết nối lab sau khi xác nhận đã khôi phục. Nếu kết nối bị đóng trước bước này, session mode sẽ mất cùng session; không có thay đổi global từ bài thực hành.

**Kết quả cần đạt:** giải thích được || có hai nghĩa theo SQL mode, biết kiểm tra và thay đổi mode của session, phân biệt session với global, hiểu tác động lên precedence và viết lại SQL bằng OR/CONCAT để giữ ngữ nghĩa ổn định.

## 12. Nguyên tắc cần ghi nhớ

- Trong MySQL, || mặc định là OR; khi bật PIPES_AS_CONCAT, nó là phép nối chuỗi.
- Mode này làm thay đổi cách parser hiểu câu lệnh và độ ưu tiên toán tử.
- @@SESSION.sql_mode quyết định hành vi của kết nối hiện tại; @@GLOBAL.sql_mode cung cấp mặc định cho kết nối mới.
- SET GLOBAL không thay đổi các session đang tồn tại; cần recycle connection nếu muốn chúng nhận mode mới.
- Thay đổi runtime không tự bảo đảm được giữ sau restart; cấu hình file hoặc SET PERSIST theo phiên bản và quyền quản trị.
- Gán lại toàn bộ sql_mode có thể vô tình tắt các mode khác; hãy giữ danh sách hiện tại khi chỉ muốn thêm một mode.
- Stored procedure, function và trigger lưu SQL mode tại thời điểm tạo; kiểm tra chúng khi chuẩn hóa cấu hình.
- Dùng OR cho điều kiện logic, CONCAT cho nối chuỗi và CONCAT_WS khi cần separator cùng quy tắc bỏ qua NULL.
- Dùng ngoặc để làm rõ biểu thức phức tạp; tránh trộn || với toán tử logic và số học.
- Kiểm tra SQL mode trên chính session ứng dụng và từng môi trường triển khai.

Viết SQL tường minh giúp ứng dụng không phụ thuộc vào cấu hình mode ngầm. Khi dùng OR cho logic và CONCAT cho chuỗi, câu lệnh giữ được ý nghĩa nhất quán giữa các session, môi trường và lần triển khai khác nhau.

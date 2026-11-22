# NULL, chuỗi rỗng, số 0 và logic ba giá trị

Trong module **DATABASE_MYSQL**, người học làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và vận hành. Khi thiết kế cột và viết điều kiện SQL, cần phân biệt rõ giá trị NULL, chuỗi rỗng và số 0. Chúng biểu diễn những trạng thái khác nhau, tham gia phép so sánh khác nhau và có thể làm thay đổi kết quả lọc, join, tổng hợp hoặc kiểm tra ràng buộc.

SQL dùng logic ba giá trị: một biểu thức điều kiện có thể là TRUE, FALSE hoặc UNKNOWN. Trong MySQL, UNKNOWN thường được biểu diễn bằng NULL. Hiểu quy tắc này giúp tránh các lỗi như truy vấn bỏ sót hàng có giá trị NULL, dùng NOT IN cho kết quả bất ngờ hoặc tính tổng sai khi dữ liệu còn thiếu.

## 1. Phân biệt NULL, chuỗi rỗng và số 0

Ba giá trị dưới đây không thể thay thế cho nhau:

| Giá trị | Ý nghĩa | Ví dụ |
|---|---|---|
| NULL | Không có giá trị được lưu, chưa biết hoặc không áp dụng theo mô hình dữ liệu | Chưa biết ngày sinh của khách hàng |
| Chuỗi rỗng | Một giá trị chuỗi có độ dài bằng 0 | Người dùng chủ động để trống ghi chú |
| Số 0 | Một giá trị số bằng 0 | Số lượng hàng trong kho hiện tại bằng 0 |

Ví dụ:

~~~sql
SELECT
    NULL IS NULL AS null_check,
    LENGTH('') AS empty_length,
    0 = 0 AS zero_check;
~~~

Kết quả cho thấy NULL là một trạng thái riêng, chuỗi rỗng có độ dài 0 và số 0 là một số hợp lệ. Trong dữ liệu nghiệp vụ, số lượng tồn kho bằng 0 khác với chưa kiểm kê; email chưa được cung cấp khác với người dùng đã nhập chuỗi rỗng.

### 1.1. NULL không phải chuỗi "NULL"

Từ khóa NULL biểu thị giá trị null. Chuỗi ký tự 'NULL' là văn bản gồm bốn ký tự. Chúng khác nhau về kiểu và cách so sánh:

~~~sql
SELECT
    NULL IS NULL AS actual_null,
    'NULL' IS NULL AS text_is_not_null,
    LENGTH('NULL') AS text_length;
~~~

Không đặt NULL trong dấu nháy khi muốn lưu giá trị null. Tương tự, không dùng chuỗi rỗng để thay thế NULL nếu nghiệp vụ cần phân biệt dữ liệu chưa biết với dữ liệu được nhập nhưng để trống.

### 1.2. Chuỗi rỗng không phải chuỗi chỉ có khoảng trắng

Chuỗi rỗng có độ dài bằng 0. Chuỗi chứa dấu cách vẫn có ký tự:

~~~sql
SELECT
    LENGTH('') AS empty_length,
    LENGTH('   ') AS spaces_length,
    CHAR_LENGTH('') AS empty_characters;
~~~

Với chuỗi đa byte, LENGTH trả số byte còn CHAR_LENGTH trả số ký tự. Cả hai trả NULL nếu đầu vào là NULL. Nếu nghiệp vụ xem chuỗi chỉ có khoảng trắng là không có nội dung, cần chuẩn hóa có chủ đích, ví dụ TRIM trước khi kiểm tra.

### 1.3. Số 0 là dữ liệu hợp lệ

Số 0 có thể mang ý nghĩa chính xác: số dư bằng 0, số lần thử bằng 0, chiết khấu 0% hoặc số lượng hiện có bằng 0. Không nên dùng 0 làm dấu hiệu "chưa biết" nếu 0 cũng là một giá trị nghiệp vụ hợp lệ.

Với cột số, hãy khai báo kiểu số và cho phép NULL khi thực sự cần biểu diễn trạng thái chưa có giá trị:

~~~sql
CREATE TABLE product_stock (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NULL,
    PRIMARY KEY (product_id)
);
~~~

Trong mô hình này, quantity = 0 có nghĩa đã biết là hết hàng; quantity IS NULL có nghĩa chưa có số liệu hoặc chưa xác định theo quy ước nghiệp vụ. Hãy ghi rõ ý nghĩa NULL trong tài liệu schema để mọi thành phần ứng dụng dùng thống nhất.

## 2. NULL và khả năng cho phép giá trị trong schema

Một cột có thể được khai báo NULL hoặc NOT NULL:

~~~sql
CREATE TABLE customer_profiles (
    customer_id BIGINT UNSIGNED NOT NULL,
    birth_date DATE NULL,
    display_name VARCHAR(150) NOT NULL,
    note VARCHAR(500) NULL,
    PRIMARY KEY (customer_id)
);
~~~

- NOT NULL yêu cầu mỗi hàng có giá trị cho cột đó.
- NULL cho phép lưu trạng thái không có giá trị.
- Nếu không ghi rõ, hành vi mặc định phụ thuộc cú pháp và kiểu khai báo; nên khai báo rõ NULL hoặc NOT NULL để schema dễ đọc.

### 2.1. DEFAULT không đồng nghĩa với thay thế NULL

DEFAULT được dùng khi câu INSERT bỏ qua cột hoặc chỉ định từ khóa DEFAULT. Nếu cột cho phép NULL, truyền NULL tường minh vẫn lưu NULL:

~~~sql
CREATE TABLE tasks (
    task_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(200) NOT NULL,
    retry_count INT NOT NULL DEFAULT 0,
    description VARCHAR(500) NULL DEFAULT NULL,
    PRIMARY KEY (task_id)
);

INSERT INTO tasks (title)
VALUES ('Import customers');

INSERT INTO tasks (title, retry_count, description)
VALUES ('Rebuild index', 0, NULL);
~~~

Ở hàng đầu tiên, retry_count nhận DEFAULT 0 và description nhận DEFAULT NULL. Ở hàng thứ hai, các giá trị 0 và NULL được truyền tường minh.

Với cột NOT NULL, chèn NULL tường minh bị từ chối trong chế độ strict phổ biến. Trong chế độ SQL không strict, MySQL có thể điều chỉnh giá trị và phát warning tùy kiểu dữ liệu; không dựa vào hành vi ép kiểu này để thiết kế ứng dụng. Hãy dùng NOT NULL cùng DEFAULT phù hợp và kiểm tra lỗi ở tầng ứng dụng.

### 2.2. PRIMARY KEY, UNIQUE và NULL

PRIMARY KEY luôn là duy nhất và không cho phép NULL. Một bảng chỉ có một primary key, có thể gồm nhiều cột.

UNIQUE index trong MySQL cho phép nhiều hàng chứa NULL ở cột được đánh index, vì NULL không được xem là bằng một giá trị NULL khác theo phép so sánh thông thường. Ví dụ:

~~~sql
CREATE TABLE user_contacts (
    contact_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NULL,
    PRIMARY KEY (contact_id),
    UNIQUE KEY uq_user_contacts_email (email)
);

INSERT INTO user_contacts (email) VALUES (NULL), (NULL);
~~~

Hai hàng có email NULL có thể cùng tồn tại. Các giá trị email không NULL vẫn phải duy nhất. Với UNIQUE index nhiều cột, quy tắc cho phép nhiều tổ hợp có chứa NULL cũng cần được tính đến khi thiết kế.

Nếu nghiệp vụ chỉ cho phép tối đa một bản ghi chưa có email, UNIQUE đơn giản không đủ để thể hiện quy tắc đó trong mọi trường hợp. Hãy cân nhắc mô hình dữ liệu, generated column hoặc cơ chế kiểm soát phù hợp với phiên bản MySQL và yêu cầu đồng thời.

## 3. So sánh với NULL: dùng IS NULL

Không dùng toán tử = hoặc <> để kiểm tra NULL:

~~~sql
-- Sai: kết quả là UNKNOWN, không tìm được hàng NULL
SELECT * FROM customer_profiles WHERE birth_date = NULL;

-- Đúng
SELECT * FROM customer_profiles WHERE birth_date IS NULL;

-- Tìm hàng có giá trị
SELECT * FROM customer_profiles WHERE birth_date IS NOT NULL;
~~~

Trong SQL, so sánh một giá trị với NULL bằng =, <>, <, >, <= hoặc >= tạo kết quả UNKNOWN. Ngay cả NULL = NULL cũng là UNKNOWN, không phải TRUE. Dùng IS NULL và IS NOT NULL để kiểm tra trạng thái null.

### 3.1. Toán tử null-safe equality <=> của MySQL

MySQL cung cấp toán tử <=> để so sánh an toàn với NULL:

~~~sql
SELECT
    NULL <=> NULL AS both_null,
    NULL <=> 10 AS one_null,
    10 <=> 10 AS equal_values,
    10 <=> 20 AS different_values;
~~~

Toán tử này trả về TRUE khi cả hai vế đều NULL hoặc hai giá trị bằng nhau; trả FALSE khi chỉ một vế NULL hoặc hai giá trị khác nhau. Khác với =, biểu thức <=> luôn trả TRUE hoặc FALSE, không trả UNKNOWN do NULL.

Ví dụ tìm các hàng có giá trị cột giống với tham số có thể NULL:

~~~sql
SELECT *
FROM customer_profiles
WHERE birth_date <=> @target_birth_date;
~~~

Nếu @target_birth_date là NULL, điều kiện tìm các hàng có birth_date NULL. Nếu tham số có ngày cụ thể, điều kiện tìm ngày bằng tham số.

Không nhầm <=> với toán tử so sánh thông thường của các hệ quản trị khác; đây là cú pháp MySQL null-safe equality.

## 4. Logic ba giá trị trong SQL

Trong điều kiện SQL, một biểu thức có thể nhận ba kết quả:

- **TRUE:** điều kiện đúng.
- **FALSE:** điều kiện sai.
- **UNKNOWN:** không thể xác định đúng hay sai, thường do có NULL tham gia phép so sánh.

Ví dụ:

~~~sql
SELECT
    5 = 5 AS is_true,
    5 = 7 AS is_false,
    NULL = 5 AS is_unknown;
~~~

Kết quả của biểu thức UNKNOWN được hiển thị như NULL.

### 4.1. Bảng chân trị của NOT

| A | NOT A |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

NOT không thể biến UNKNOWN thành TRUE hoặc FALSE. Vì vậy, NOT (column = 10) vẫn không chọn hàng có column là NULL.

### 4.2. Bảng chân trị của AND

| A | B | A AND B |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | UNKNOWN | UNKNOWN |
| FALSE | TRUE | FALSE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE |
| UNKNOWN | TRUE | UNKNOWN |
| UNKNOWN | FALSE | FALSE |
| UNKNOWN | UNKNOWN | UNKNOWN |

Chỉ cần một vế FALSE thì AND chắc chắn FALSE. Nếu không có FALSE nhưng có UNKNOWN, kết quả là UNKNOWN.

### 4.3. Bảng chân trị của OR

| A | B | A OR B |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | TRUE |
| TRUE | UNKNOWN | TRUE |
| FALSE | TRUE | TRUE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | UNKNOWN |
| UNKNOWN | TRUE | TRUE |
| UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN |

Chỉ cần một vế TRUE thì OR chắc chắn TRUE. Nếu không có TRUE nhưng có UNKNOWN, kết quả là UNKNOWN.

### 4.4. Các phép so sánh và biểu thức số học

NULL lan truyền qua nhiều phép tính và hàm:

~~~sql
SELECT
    NULL + 10 AS addition_result,
    NULL * 2 AS multiplication_result,
    NULL = 0 AS comparison_result,
    NOT (NULL = 0) AS negated_result;
~~~

Các kết quả trên đều là NULL/UNKNOWN. Vì vậy, biểu thức số học có thể tạo NULL ngay cả khi một toán hạng còn lại là số hợp lệ. Khi tính toán, cần quyết định rõ dữ liệu thiếu nên làm kết quả tiếp tục thiếu, được thay bằng giá trị mặc định hay khiến phép tính bị từ chối.

## 5. WHERE, HAVING và điều kiện UNKNOWN

WHERE chỉ giữ những hàng mà điều kiện đánh giá là TRUE. Hàng có điều kiện FALSE hoặc UNKNOWN đều bị loại:

~~~sql
SELECT customer_id, birth_date
FROM customer_profiles
WHERE birth_date <> '2000-01-01';
~~~

Truy vấn trên không trả các hàng có birth_date NULL. Phép so sánh NULL <> '2000-01-01' là UNKNOWN, nên hàng bị loại khỏi kết quả.

Nếu mục tiêu là lấy cả hàng có ngày sinh khác ngày chỉ định và hàng chưa có ngày sinh:

~~~sql
SELECT customer_id, birth_date
FROM customer_profiles
WHERE birth_date <> '2000-01-01'
   OR birth_date IS NULL;
~~~

HAVING cũng áp dụng nguyên tắc chỉ giữ nhóm có điều kiện TRUE. Nếu biểu thức aggregate trả NULL, điều kiện HAVING so sánh với số có thể trở thành UNKNOWN và nhóm bị loại.

### 5.1. NOT và điều kiện phủ định

Ví dụ dễ sai:

~~~sql
SELECT *
FROM customer_profiles
WHERE NOT (birth_date = '2000-01-01');
~~~

Người viết có thể nghĩ truy vấn lấy tất cả hàng không phải ngày 2000-01-01, bao gồm hàng chưa có ngày sinh. Thực tế, hàng NULL vẫn bị loại vì NOT UNKNOWN vẫn là UNKNOWN.

Viết rõ ý định:

~~~sql
SELECT *
FROM customer_profiles
WHERE birth_date <> '2000-01-01'
   OR birth_date IS NULL;
~~~

## 6. NOT IN và bẫy NULL

NOT IN có thể cho kết quả bất ngờ nếu danh sách hoặc subquery chứa NULL.

~~~sql
SELECT 5 NOT IN (1, 2, NULL);
~~~

Biểu thức này trả UNKNOWN. MySQL không thể xác nhận 5 khác mọi phần tử vì phép so sánh với NULL là UNKNOWN. Do đó, truy vấn sau có thể không trả hàng nào như người viết mong muốn:

~~~sql
SELECT customer_id
FROM customers
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM blocked_customers
);
~~~

Nếu subquery trả về ít nhất một NULL, điều kiện NOT IN có thể trở thành UNKNOWN đối với các giá trị không khớp khác, khiến chúng bị loại.

### 6.1. Dùng NOT EXISTS khi kiểm tra không có bản ghi liên quan

Một cách thường rõ nghĩa hơn:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers AS b
    WHERE b.customer_id = c.customer_id
);
~~~

NOT EXISTS kiểm tra có hay không hàng thỏa điều kiện tương quan. Nếu subquery không tìm thấy hàng phù hợp, biểu thức EXISTS là FALSE và NOT EXISTS là TRUE. NULL trong các hàng khác của bảng blocked_customers không tự làm hỏng phép kiểm tra như NOT IN.

Nếu c.customer_id có thể NULL, điều kiện bằng trong subquery cũng là UNKNOWN cho giá trị NULL; khi đó hàng customer có ID NULL có thể được xem là không có bản ghi khớp. Hãy quyết định rõ liệu khóa định danh có được phép NULL hay không; thông thường primary key nên NOT NULL.

Nếu vẫn dùng NOT IN, có thể lọc NULL khỏi subquery:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customers AS b
    WHERE b.customer_id IS NOT NULL
);
~~~

Hãy kiểm tra cả khả năng NULL của biểu thức bên trái. Chọn NOT EXISTS hoặc NOT IN dựa trên ý nghĩa nghiệp vụ và kế hoạch thực thi, không chỉ dựa trên thói quen.

## 7. NULL trong JOIN

Điều kiện JOIN chỉ được xem là khớp khi biểu thức ON là TRUE. Nếu phép so sánh tạo UNKNOWN do một bên NULL, hai hàng không khớp với nhau.

~~~sql
SELECT c.customer_id, c.birth_date, p.profile_id
FROM customers AS c
LEFT JOIN profiles AS p
  ON p.birth_date = c.birth_date;
~~~

Hai hàng có birth_date NULL không khớp nhau qua toán tử =. Nếu nghiệp vụ muốn NULL khớp với NULL, có thể dùng toán tử null-safe:

~~~sql
SELECT c.customer_id, c.birth_date, p.profile_id
FROM customers AS c
LEFT JOIN profiles AS p
  ON p.birth_date <=> c.birth_date;
~~~

Chỉ áp dụng cách này khi hai giá trị NULL thực sự có nghĩa là tương đương để ghép. Trong nhiều mô hình, NULL biểu thị không biết nên không thể kết luận hai hàng cùng NULL là cùng một đối tượng.

### 7.1. Điều kiện WHERE sau LEFT JOIN

Một lỗi thường gặp là đặt điều kiện trên bảng bên phải trong WHERE:

~~~sql
SELECT c.customer_id, p.profile_id
FROM customers AS c
LEFT JOIN profiles AS p
  ON p.customer_id = c.customer_id
WHERE p.status = 'ACTIVE';
~~~

Với hàng customer không có profile, các cột p được bổ sung NULL. Điều kiện p.status = 'ACTIVE' trở thành UNKNOWN nên hàng bị WHERE loại. Kết quả có thể hoạt động giống INNER JOIN đối với điều kiện đó.

Nếu muốn giữ mọi customer và chỉ ghép profile ACTIVE, đặt điều kiện vào ON:

~~~sql
SELECT c.customer_id, p.profile_id
FROM customers AS c
LEFT JOIN profiles AS p
  ON p.customer_id = c.customer_id
 AND p.status = 'ACTIVE';
~~~

Điều kiện ON quyết định hàng nào được ghép; LEFT JOIN vẫn giữ hàng bên trái khi không có hàng bên phải phù hợp.

## 8. NULL trong hàm tổng hợp và GROUP BY

Các hàm aggregate thường bỏ qua giá trị NULL ở đối số:

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(score) AS rows_with_score,
    COUNT(DISTINCT score) AS distinct_non_null_scores,
    SUM(score) AS score_sum,
    AVG(score) AS score_average,
    MIN(score) AS minimum_score,
    MAX(score) AS maximum_score
FROM exam_results;
~~~

| Hàm | Cách xử lý NULL |
|---|---|
| COUNT(*) | Đếm tất cả hàng, kể cả hàng có cột NULL |
| COUNT(column) | Chỉ đếm hàng mà column không NULL |
| COUNT(DISTINCT column) | Đếm giá trị phân biệt không NULL |
| SUM(column) | Bỏ qua NULL; trả NULL nếu không có giá trị không NULL |
| AVG(column) | Bỏ qua NULL khi tính trung bình; trả NULL nếu không có giá trị không NULL |
| MIN/MAX(column) | Bỏ qua NULL; trả NULL nếu không có giá trị không NULL |

Ví dụ, với các giá trị 10, 20 và NULL, AVG là 15 chứ không phải 10 vì hàng NULL không được tính vào mẫu số.

Nếu cần hiển thị 0 khi không có giá trị, có thể dùng COALESCE:

~~~sql
SELECT COALESCE(SUM(score), 0) AS score_sum
FROM exam_results;
~~~

Chỉ thay NULL bằng 0 ở lớp trình bày hoặc tính toán khi điều đó phù hợp với nghiệp vụ. Nếu NULL có nghĩa là chưa có dữ liệu, hiển thị 0 có thể làm người dùng hiểu nhầm rằng đã đo và kết quả bằng 0.

### 8.1. GROUP BY và DISTINCT

GROUP BY gom các hàng có giá trị NULL của cùng biểu thức vào một nhóm. DISTINCT cũng chỉ trả một đại diện NULL trong kết quả phân biệt:

~~~sql
SELECT department_id, COUNT(*) AS employee_count
FROM employees
GROUP BY department_id;

SELECT DISTINCT department_id
FROM employees;
~~~

Nhóm có department_id NULL có thể đại diện cho những hàng chưa được gán phòng ban. Nếu cần phân biệt "chưa phân công" với "không áp dụng", nên bổ sung trạng thái nghiệp vụ riêng thay vì mong đợi GROUP BY tự phân biệt các nguyên nhân NULL.

### 8.2. Sắp xếp NULL

Trong MySQL, khi sắp xếp tăng dần, NULL thường đứng trước các giá trị không NULL; khi sắp xếp giảm dần, NULL đứng sau. Nếu yêu cầu thứ tự nghiệp vụ khác, hãy biểu diễn rõ:

~~~sql
SELECT customer_id, birth_date
FROM customer_profiles
ORDER BY birth_date IS NULL, birth_date;
~~~

Biểu thức birth_date IS NULL trả 1 cho NULL và 0 cho giá trị khác, nên cách sắp xếp trên đưa giá trị có ngày lên trước, NULL xuống sau.

## 9. Các hàm xử lý NULL trong MySQL

### 9.1. COALESCE

COALESCE trả về đối số đầu tiên khác NULL:

~~~sql
SELECT COALESCE(nickname, full_name, 'Unknown') AS display_name
FROM customers;
~~~

Nếu nickname có giá trị, dùng nickname; nếu không, dùng full_name; nếu cả hai NULL, dùng 'Unknown'. COALESCE nhận nhiều đối số và tuân theo quy tắc chuyển đổi kiểu của MySQL.

### 9.2. IFNULL

IFNULL(expr1, expr2) trả expr2 khi expr1 là NULL, nếu không trả expr1:

~~~sql
SELECT IFNULL(phone_number, 'Not provided') AS phone_display
FROM customers;
~~~

IFNULL chỉ xử lý NULL. Nó không tự coi chuỗi rỗng hoặc chuỗi toàn dấu cách là NULL.

### 9.3. NULLIF

NULLIF(expr1, expr2) trả NULL nếu hai biểu thức bằng nhau, nếu khác nhau thì trả expr1:

~~~sql
SELECT NULLIF('', '') AS empty_to_null;
SELECT amount / NULLIF(quantity, 0) AS average_price
FROM order_items;
~~~

Ví dụ thứ hai tránh chia cho 0: khi quantity bằng 0, mẫu số trở thành NULL và kết quả phép chia là NULL. Ứng dụng cần quyết định cách hiển thị hoặc xử lý trường hợp không tính được.

Có thể chuẩn hóa chuỗi rỗng hoặc chỉ có khoảng trắng thành NULL nếu nghiệp vụ xem chúng tương đương với dữ liệu thiếu:

~~~sql
SELECT NULLIF(TRIM(optional_note), '') AS normalized_note
FROM form_submissions;
~~~

Không áp dụng chuẩn hóa này một cách mù quáng nếu chuỗi rỗng là một trạng thái hợp lệ và cần được giữ riêng.

### 9.4. IF và CASE

Trong MySQL, IF(condition, value_if_true, value_if_false) xem điều kiện NULL như không đúng và trả nhánh thứ ba:

~~~sql
SELECT IF(NULL, 'yes', 'no') AS if_result;
~~~

CASE WHEN chỉ chọn nhánh có điều kiện TRUE; UNKNOWN không khớp:

~~~sql
SELECT
    CASE
        WHEN score >= 50 THEN 'PASS'
        WHEN score < 50 THEN 'FAIL'
        ELSE 'NOT GRADED'
    END AS result
FROM exam_results;
~~~

Nếu score NULL, hai điều kiện so sánh đều UNKNOWN nên CASE đi vào ELSE. Đây là cách rõ ràng để thể hiện trạng thái chưa chấm.

## 10. NULL trong hàm chuỗi và biểu thức

Nhiều hàm MySQL trả NULL khi đầu vào NULL. Ví dụ CONCAT trả NULL nếu một trong các đối số là NULL:

~~~sql
SELECT CONCAT('Hello ', NULL, '!') AS greeting;
~~~

Nếu muốn bỏ qua đối số NULL khi ghép chuỗi có dấu phân cách, có thể dùng CONCAT_WS:

~~~sql
SELECT CONCAT_WS(' ', first_name, middle_name, last_name) AS full_name
FROM customers;
~~~

CONCAT_WS bỏ qua các đối số NULL sau separator; nếu separator là NULL thì kết quả là NULL. Chuỗi rỗng không bị bỏ qua theo cách tương tự NULL và có thể tạo ra dấu phân cách liền nhau. Hãy chuẩn hóa dữ liệu hoặc xử lý chuỗi rỗng nếu cần.

Đối với hàm số học và ngày giờ, cần đọc quy tắc NULL của từng hàm. Ví dụ, DATE_ADD(NULL, INTERVAL 1 DAY) trả NULL. Nếu một giá trị bắt buộc phải có để tính toán, ràng buộc NOT NULL thường tốt hơn việc để mọi truy vấn tự xử lý dữ liệu thiếu.

## 11. Boolean trong MySQL và UNKNOWN

MySQL biểu diễn TRUE và FALSE theo giá trị số 1 và 0 trong nhiều ngữ cảnh. Tuy nhiên, SQL vẫn có trạng thái UNKNOWN khi biểu thức liên quan đến NULL.

~~~sql
SELECT
    TRUE AS true_value,
    FALSE AS false_value,
    NULL AS unknown_value;
~~~

TRUE và FALSE là các literal boolean được biểu diễn như số; UNKNOWN biểu diễn NULL. Trong điều kiện, số 0 được xem là false, giá trị số khác 0 là true, còn NULL vẫn là unknown.

Không nên dựa vào ép kiểu ngầm để xác định trạng thái dữ liệu. Ví dụ, chuỗi không phải số khi được chuyển sang số có thể tạo warning hoặc lỗi tùy ngữ cảnh và SQL mode. Hãy kiểm tra dữ liệu đầu vào và dùng kiểu cột phù hợp.

Các predicate IS TRUE, IS FALSE và IS UNKNOWN trả kết quả boolean:

~~~sql
SELECT
    (NULL = 1) IS UNKNOWN AS comparison_is_unknown,
    (0 = 1) IS FALSE AS comparison_is_false,
    (1 = 1) IS TRUE AS comparison_is_true;
~~~

Các predicate này hữu ích khi kiểm tra biểu thức có thể NULL và muốn phân biệt ba trạng thái một cách tường minh.

## 12. Thiết kế dữ liệu để tránh nhập nhằng

### 12.1. Chọn NULL khi nào?

Cho phép NULL khi một thuộc tính có thể chưa biết, chưa được cung cấp hoặc không áp dụng. Ví dụ:

- Ngày kết thúc của một hợp đồng đang còn hiệu lực.
- Ngày sinh mà khách hàng không cung cấp.
- Thời điểm giao hàng chưa được xác định.
- Mã phụ không áp dụng với một loại sản phẩm.

Dùng NOT NULL khi thuộc tính bắt buộc để định danh hoặc xử lý bản ghi. Với giá trị bắt buộc nhưng có mặc định nghiệp vụ rõ ràng, có thể dùng DEFAULT phù hợp.

### 12.2. Tránh sentinel value

Không dùng các giá trị giả như 0, -1, 1900-01-01 hoặc 'N/A' để đại diện cho dữ liệu chưa biết nếu chúng có thể là giá trị hợp lệ hoặc làm sai kiểu dữ liệu. Sentinel value buộc mọi truy vấn phải nhớ một quy ước ngầm và có thể gây sai aggregate, sort, join hoặc constraint.

Nếu cần phân biệt nhiều trạng thái, hãy dùng cột trạng thái riêng:

~~~sql
CREATE TABLE deliveries (
    delivery_id BIGINT UNSIGNED NOT NULL,
    delivered_at DATETIME NULL,
    delivery_status ENUM('PENDING', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED')
        NOT NULL DEFAULT 'PENDING',
    PRIMARY KEY (delivery_id)
);
~~~

Ở đây delivered_at NULL có thể là chưa giao; delivery_status cho biết trạng thái cụ thể. Không cần đặt ngày giả để biểu diễn một trạng thái quy trình.

### 12.3. CHECK và NULL

CHECK constraint loại bỏ hàng khi biểu thức kiểm tra là FALSE. Trong MySQL, biểu thức CHECK đánh giá UNKNOWN do NULL không bị xem là vi phạm. Vì vậy:

~~~sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NULL,
    CONSTRAINT chk_quantity_nonnegative CHECK (quantity >= 0)
);
~~~

Constraint trên ngăn quantity âm nhưng vẫn cho phép quantity NULL. Nếu nghiệp vụ yêu cầu quantity luôn có giá trị và không âm, phải kết hợp NOT NULL:

~~~sql
CREATE TABLE inventory (
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT NOT NULL,
    CONSTRAINT chk_quantity_nonnegative CHECK (quantity >= 0)
);
~~~

MySQL thực thi CHECK constraint từ phiên bản 8.0.16. Với phiên bản cũ hơn, cần kiểm tra hành vi phiên bản và không giả định CHECK đang bảo vệ dữ liệu.

## 13. Bài thực hành: quan sát NULL và logic ba giá trị

Thực hiện trên database lab hoặc môi trường phát triển mà bạn được phép tạo bảng:

**Bước 1 — Tạo bảng mẫu.**

~~~sql
CREATE TABLE lab_values (
    id INT NOT NULL,
    label VARCHAR(50) NULL,
    amount DECIMAL(10,2) NULL,
    PRIMARY KEY (id)
);

INSERT INTO lab_values (id, label, amount) VALUES
    (1, NULL, NULL),
    (2, '', 0),
    (3, '   ', 10),
    (4, 'zero', 0),
    (5, 'known', 25);
~~~

**Bước 2 — So sánh các trạng thái.**

~~~sql
SELECT id,
       label,
       amount,
       label IS NULL AS label_is_null,
       label = '' AS label_is_empty,
       amount = 0 AS amount_is_zero,
       LENGTH(label) AS label_length
FROM lab_values
ORDER BY id;
~~~

Xác định hàng có label NULL, label rỗng, label chỉ có dấu cách và amount bằng 0. Ghi lại sự khác nhau giữa NULL và biểu thức FALSE/TRUE.

**Bước 3 — Quan sát UNKNOWN.**

~~~sql
SELECT
    NULL = NULL AS null_equals_null,
    NULL <> 0 AS null_not_zero,
    NOT (NULL = 0) AS not_unknown,
    (NULL = 0) IS UNKNOWN AS is_unknown;
~~~

Giải thích vì sao ba biểu thức đầu trả NULL và biểu thức cuối trả TRUE.

**Bước 4 — So sánh WHERE.**

Chạy lần lượt:

~~~sql
SELECT id FROM lab_values WHERE amount <> 0;
SELECT id FROM lab_values WHERE amount <> 0 OR amount IS NULL;
SELECT id FROM lab_values WHERE NOT (amount = 0);
~~~

So sánh các hàng được trả về: hàng amount NULL không xuất hiện ở truy vấn thứ nhất và thứ ba, nhưng xuất hiện ở truy vấn thứ hai nhờ điều kiện OR amount IS NULL.

**Bước 5 — So sánh aggregate.**

~~~sql
SELECT COUNT(*) AS all_rows,
       COUNT(amount) AS known_amounts,
       SUM(amount) AS amount_sum,
       AVG(amount) AS amount_average
FROM lab_values;
~~~

Tính tay kết quả dự kiến và so sánh với MySQL. Chú ý COUNT(*) tính mọi hàng, còn COUNT(amount) bỏ qua NULL.

**Bước 6 — Thử NOT IN với NULL.**

~~~sql
SELECT 5 NOT IN (1, 2, NULL) AS not_in_with_null,
       NOT EXISTS (
           SELECT 1
           FROM lab_values
           WHERE amount = 5
       ) AS no_matching_row;
~~~

Giải thích vì sao NOT IN có NULL có thể trả UNKNOWN trong khi NOT EXISTS vẫn trả TRUE nếu không tìm thấy hàng phù hợp.

**Bước 7 — Thử hàm xử lý NULL.**

~~~sql
SELECT id,
       COALESCE(label, '(missing)') AS coalesced_label,
       IFNULL(amount, 0) AS display_amount,
       NULLIF(label, '') AS empty_to_null
FROM lab_values
ORDER BY id;
~~~

Ghi rõ trường hợp nào được chuyển đổi và liệu cách hiển thị đó có phù hợp với ý nghĩa nghiệp vụ hay không.

**Bước 8 — Dọn dữ liệu lab.**

~~~sql
DROP TABLE lab_values;
~~~

Chỉ xóa bảng lab do bạn vừa tạo sau khi xác nhận không còn cần dữ liệu. Không chạy lệnh trên bảng dùng chung.

**Kết quả cần đạt:** phân biệt được NULL, chuỗi rỗng, chuỗi khoảng trắng và số 0; giải thích được TRUE/FALSE/UNKNOWN; viết điều kiện IS NULL chính xác; nhận diện bẫy NOT IN; hiểu ảnh hưởng của NULL đến JOIN, aggregate và CHECK.

## 14. Lỗi thường gặp và cách sửa

| Cách viết hoặc giả định sai | Hệ quả | Cách làm đúng |
|---|---|---|
| WHERE column = NULL | Điều kiện UNKNOWN, không chọn hàng NULL | Dùng WHERE column IS NULL |
| WHERE column <> value | Bỏ qua hàng có column NULL | Thêm OR column IS NULL nếu nghiệp vụ cần lấy chúng |
| NOT (column = value) | UNKNOWN vẫn là UNKNOWN; hàng NULL bị loại | Viết rõ điều kiện bao gồm IS NULL |
| NOT IN với subquery có NULL | Kết quả có thể UNKNOWN và loại nhiều hàng | Dùng NOT EXISTS hoặc lọc NULL trong subquery |
| Coi '' là NULL | Mất phân biệt giữa không nhập và nhập chuỗi rỗng | Dùng IS NULL cho NULL; kiểm tra = '' riêng |
| Dùng 0 để biểu thị chưa biết | Không phân biệt được giá trị 0 thực tế | Cho phép NULL hoặc dùng trạng thái riêng |
| Dùng IFNULL(column, 0) trong mọi phép tính | Có thể biến dữ liệu thiếu thành số đo 0 sai nghĩa | Chỉ thay NULL khi quy tắc nghiệp vụ cho phép |
| Dùng LEFT JOIN rồi lọc cột bên phải trong WHERE | Có thể loại các hàng không có bản ghi ghép | Đưa điều kiện lọc bảng phải vào ON nếu cần giữ hàng trái |
| CHECK (quantity >= 0) nhưng không khai báo NOT NULL | NULL vẫn có thể được chấp nhận | Kết hợp NOT NULL nếu giá trị bắt buộc |

## 15. Nguyên tắc cần ghi nhớ

- NULL biểu thị trạng thái không có giá trị; chuỗi rỗng và số 0 là các giá trị cụ thể.
- So sánh với NULL bằng toán tử thông thường tạo UNKNOWN; dùng IS NULL, IS NOT NULL hoặc toán tử null-safe <=> của MySQL.
- WHERE và HAVING chỉ giữ hàng/nhóm có điều kiện TRUE; FALSE và UNKNOWN đều bị loại.
- NOT UNKNOWN vẫn là UNKNOWN; phủ định điều kiện không tự bao gồm các hàng NULL.
- NOT IN đặc biệt nhạy với NULL trong danh sách hoặc subquery; NOT EXISTS thường thể hiện ý định kiểm tra vắng mặt rõ hơn.
- COUNT(*), COUNT(column), SUM và AVG xử lý NULL khác nhau; cần hiểu ý nghĩa dữ liệu trước khi thay NULL bằng 0.
- UNIQUE index cho phép nhiều NULL trong MySQL; PRIMARY KEY thì không cho phép NULL.
- CHECK không thay thế NOT NULL; điều kiện CHECK có kết quả UNKNOWN do NULL có thể vẫn được chấp nhận.
- Chọn NULL, DEFAULT, NOT NULL hoặc trạng thái riêng theo ngữ nghĩa nghiệp vụ, không dùng sentinel tùy tiện.

Khi phân biệt đúng NULL, chuỗi rỗng và số 0, đồng thời hiểu logic ba giá trị, bạn có thể viết truy vấn chính xác hơn, thiết kế constraint đúng ý nghĩa và tránh những lỗi âm thầm trong lọc dữ liệu, join và tính toán.

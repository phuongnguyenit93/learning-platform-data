# IN, BETWEEN, LIKE và ký tự đại diện

Các điều kiện IN, BETWEEN và LIKE giúp lọc dữ liệu theo tập giá trị, khoảng giá trị hoặc mẫu văn bản. Chúng xuất hiện thường xuyên trong truy vấn tìm kiếm, báo cáo và API. Dù cú pháp ngắn, mỗi toán tử có quy tắc riêng về NULL, kiểu dữ liệu, collation và khả năng sử dụng index.

Bài học thuộc phạm vi DATABASE_MYSQL: thiết kế điều kiện lọc chính xác, hiểu cách MySQL so sánh dữ liệu, đọc kế hoạch thực thi và tránh các lỗi phổ biến khi ứng dụng nhận đầu vào từ người dùng.

## 1. Chuẩn bị dữ liệu thực hành

Dùng bảng đơn hàng đơn giản để minh họa:

~~~sql
CREATE TABLE orders_demo (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    note VARCHAR(200) NULL,
    KEY idx_orders_customer (customer_id),
    KEY idx_orders_status_created (status, created_at),
    KEY idx_orders_created (created_at)
) ENGINE = InnoDB;

INSERT INTO orders_demo
    (order_id, customer_id, status, total_amount, created_at, note)
VALUES
    (1001, 10, 'NEW',       120.00, '2025-03-01 08:15:00', 'Giao giờ hành chính'),
    (1002, 11, 'PAID',      850.00, '2025-03-05 10:30:00', 'Khách thân thiết'),
    (1003, 10, 'SHIPPED',   450.00, '2025-03-12 14:20:00', 'Đã đóng gói'),
    (1004, 12, 'CANCELLED',  75.00, '2025-03-18 09:00:00', NULL),
    (1005, 13, 'PAID',     1200.00, '2025-03-25 17:45:00', 'Ưu tiên'),
    (1006, 14, 'NEW',       300.00, '2025-04-01 00:00:00', 'Đơn đầu tháng'),
    (1007, 15, 'SHIPPED',   620.00, '2025-04-02 11:10:00', NULL);
~~~

Các ví dụ bên dưới dùng MySQL 8.x và dữ liệu này. Nếu tên bảng hoặc kiểu dữ liệu trong hệ thống thật khác, hãy thay bằng schema tương ứng.

## 2. IN: kiểm tra một giá trị thuộc tập hợp

Toán tử IN kiểm tra một biểu thức có bằng một trong các giá trị trong danh sách hoặc kết quả truy vấn con hay không.

Cú pháp:

~~~sql
expression IN (value1, value2, ...)
expression IN (subquery)
~~~

Ví dụ tìm đơn hàng có trạng thái NEW hoặc PAID:

~~~sql
SELECT order_id, customer_id, status, total_amount
FROM orders_demo
WHERE status IN ('NEW', 'PAID')
ORDER BY order_id;
~~~

Truy vấn tương đương về logic với:

~~~sql
WHERE status = 'NEW'
   OR status = 'PAID'
~~~

IN thường gọn và dễ bảo trì hơn khi tập giá trị có nhiều phần tử.

### 2.1. IN với số

~~~sql
SELECT order_id, customer_id, total_amount
FROM orders_demo
WHERE customer_id IN (10, 12, 15)
ORDER BY customer_id, order_id;
~~~

Kết quả gồm đơn hàng của khách hàng 10, 12 và 15.

Các giá trị trong danh sách nên cùng kiểu hoặc có thể chuyển đổi rõ ràng sang kiểu của biểu thức. Tránh trộn số, chuỗi số và chuỗi văn bản tùy tiện vì MySQL có thể thực hiện chuyển đổi kiểu ngầm, dẫn tới kết quả ngoài dự kiến hoặc làm giảm khả năng dùng index.

### 2.2. IN với truy vấn con

Có thể lấy tập giá trị từ bảng khác:

~~~sql
SELECT order_id, customer_id, status
FROM orders_demo
WHERE customer_id IN (
    SELECT customer_id
    FROM preferred_customer
    WHERE active = 1
);
~~~

Truy vấn con phải trả về một cột cho dạng IN (subquery). Optimizer có thể chuyển một số truy vấn IN thành semijoin hoặc chiến lược tương đương, tùy cấu trúc truy vấn và phiên bản. Không giả định mọi IN subquery đều được thực thi theo cùng một cách; hãy kiểm tra EXPLAIN.

Nếu truy vấn con có thể trả về NULL, cần xem phần logic ba giá trị ở mục tiếp theo.

### 2.3. IN và NULL

SQL dùng ba trạng thái logic: TRUE, FALSE và UNKNOWN. NULL không phải một giá trị thông thường để so sánh bằng dấu bằng.

~~~sql
SELECT
    10 IN (10, 20, NULL) AS matched_value,
    30 IN (10, 20, NULL) AS unmatched_with_null,
    30 IN (10, 20) AS unmatched_without_null,
    NULL IN (10, 20) AS null_expression;
~~~

Kết quả logic:

| Biểu thức | Kết quả |
|---|---|
| 10 IN (10, 20, NULL) | TRUE |
| 30 IN (10, 20, NULL) | UNKNOWN (NULL) |
| 30 IN (10, 20) | FALSE |
| NULL IN (10, 20) | UNKNOWN (NULL) |

Nếu tìm thấy một giá trị khớp, IN trả TRUE dù danh sách có NULL. Nếu không tìm thấy giá trị khớp và danh sách có NULL, kết quả là UNKNOWN vì MySQL không thể kết luận chắc chắn rằng không có phần tử nào bằng biểu thức.

Trong WHERE, chỉ TRUE giữ lại hàng. FALSE và UNKNOWN đều bị loại.

### 2.4. NOT IN và bẫy NULL

NOT IN là phủ định của IN, vì vậy NULL trong danh sách có thể làm kết quả trở thành UNKNOWN.

~~~sql
SELECT 30 NOT IN (10, 20, NULL) AS result;
~~~

Kết quả là NULL, không phải TRUE. Đây là nguyên nhân phổ biến khiến truy vấn anti-join bất ngờ không trả hàng nào:

~~~sql
SELECT c.customer_id
FROM customer AS c
WHERE c.customer_id NOT IN (
    SELECT b.customer_id
    FROM blocked_customer AS b
);
~~~

Nếu blocked_customer.customer_id có một hàng NULL, các khách hàng không khớp có thể bị loại vì biểu thức cho UNKNOWN.

Một cách viết thường an toàn và rõ ý hơn là NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customer AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customer AS b
    WHERE b.customer_id = c.customer_id
);
~~~

Nếu khóa phía ngoài hoặc phía trong có thể NULL và nghiệp vụ muốn NULL khớp với NULL, hãy xác định rõ quy tắc và cân nhắc toán tử NULL-safe <=>. Không thay NOT IN bằng NOT EXISTS máy móc nếu ý nghĩa NULL của hai bên khác nhau.

### 2.5. IN với danh sách rỗng

SQL không nên tạo cú pháp IN (). Khi ứng dụng nhận danh sách rỗng, hãy xử lý riêng:

- Nếu danh sách rỗng có nghĩa không chọn đối tượng nào, trả kết quả rỗng hoặc thêm điều kiện luôn sai.
- Nếu danh sách rỗng có nghĩa không áp dụng bộ lọc, bỏ điều kiện IN theo quy tắc API đã định nghĩa.
- Không tạo chuỗi SQL IN () rồi trông chờ server xử lý.

Đây là quyết định nghiệp vụ ở tầng ứng dụng, không nên để hành vi ngẫu nhiên của câu lệnh quyết định.

## 3. BETWEEN: lọc theo một khoảng giá trị

BETWEEN kiểm tra biểu thức có nằm trong khoảng từ giá trị thấp đến giá trị cao hay không. Hai đầu mút đều được tính.

Cú pháp:

~~~sql
expression BETWEEN lower_bound AND upper_bound
~~~

Tương đương về logic:

~~~sql
expression >= lower_bound
AND expression <= upper_bound
~~~

Ví dụ tìm đơn hàng có tổng tiền từ 100 đến 600:

~~~sql
SELECT order_id, total_amount
FROM orders_demo
WHERE total_amount BETWEEN 100 AND 600
ORDER BY total_amount;
~~~

Đơn hàng có giá trị đúng 100 hoặc 600 cũng được tính.

### 3.1. NOT BETWEEN

NOT BETWEEN chọn giá trị nằm ngoài khoảng:

~~~sql
SELECT order_id, total_amount
FROM orders_demo
WHERE total_amount NOT BETWEEN 100 AND 600
ORDER BY total_amount;
~~~

Về logic, điều kiện tương đương:

~~~sql
total_amount < 100
OR total_amount > 600
~~~

Giá trị NULL vẫn cho UNKNOWN khi kiểm tra BETWEEN hoặc NOT BETWEEN, nên không được xem là thuộc khoảng hoặc ngoài khoảng.

### 3.2. Thứ tự hai đầu mút

MySQL không tự sắp xếp lại hai đầu mút. Nếu lower bound lớn hơn upper bound, không có giá trị nào thỏa mãn khoảng thông thường.

~~~sql
SELECT 5 BETWEEN 10 AND 1 AS reversed_range;
~~~

Kết quả là FALSE. Ứng dụng nên xác thực lower bound không lớn hơn upper bound trước khi gửi truy vấn.

### 3.3. BETWEEN với ngày DATE

Nếu cột có kiểu DATE, BETWEEN dễ diễn đạt khoảng ngày bao gồm cả hai ngày:

~~~sql
SELECT holiday_date
FROM holiday
WHERE holiday_date BETWEEN '2025-03-01' AND '2025-03-31';
~~~

Cả ngày 1 và ngày 31 đều được tính. Với cột DATE, không có thành phần giờ.

### 3.4. BETWEEN với DATETIME: lưu ý thời điểm cuối ngày

Một lỗi rất phổ biến:

~~~sql
SELECT order_id, created_at
FROM orders_demo
WHERE created_at BETWEEN '2025-03-01' AND '2025-03-31';
~~~

Literal ngày 31/03 được diễn giải là thời điểm 2025-03-31 00:00:00. Do BETWEEN bao gồm hai đầu mút, truy vấn chỉ bao gồm đúng thời điểm đầu ngày 31/03, không bao gồm các đơn hàng phát sinh sau nửa đêm trong ngày đó.

Không nên sửa bằng cách tự gõ 23:59:59.999999 vì độ chính xác fractional seconds có thể thay đổi và ranh giới cuối ngày dễ sai khi xử lý múi giờ.

Với DATETIME, hãy dùng khoảng nửa mở:

~~~sql
SELECT order_id, created_at
FROM orders_demo
WHERE created_at >= '2025-03-01 00:00:00'
  AND created_at <  '2025-04-01 00:00:00'
ORDER BY created_at;
~~~

Khoảng [start, next_start) bao gồm thời điểm bắt đầu và loại trừ thời điểm đầu của ngày kế tiếp. Cách này bao phủ toàn bộ ngày 31/03 dù cột có độ chính xác đến microsecond.

### 3.5. BETWEEN và NULL

~~~sql
SELECT
    5 BETWEEN 1 AND 10 AS inside_range,
    5 BETWEEN NULL AND 10 AS unknown_lower,
    NULL BETWEEN 1 AND 10 AS unknown_value;
~~~

Kết quả đầu là TRUE. Hai biểu thức còn lại là UNKNOWN vì một thành phần cần so sánh là NULL.

Nếu đầu mút được lấy từ tham số ứng dụng, hãy kiểm tra không NULL và đúng kiểu trước khi thực thi nếu nghiệp vụ yêu cầu khoảng đầy đủ.

## 4. LIKE: tìm kiếm theo mẫu chuỗi

LIKE so sánh chuỗi với một pattern có ký tự đại diện.

Cú pháp:

~~~sql
string_expression LIKE pattern
string_expression NOT LIKE pattern
~~~

MySQL có hai ký tự đại diện chính:

| Ký tự | Ý nghĩa |
|---|---|
| % | Khớp với không, một hoặc nhiều ký tự bất kỳ |
| _ | Khớp với chính xác một ký tự |

Ví dụ:

~~~sql
SELECT order_id, note
FROM orders_demo
WHERE note LIKE '%hành chính%';
~~~

Pattern bắt đầu và kết thúc bằng % nên có thể xuất hiện chuỗi cần tìm ở bất kỳ vị trí nào trong note.

### 4.1. Tìm chuỗi bắt đầu bằng một tiền tố

~~~sql
SELECT order_id, note
FROM orders_demo
WHERE note LIKE 'Giao%';
~~~

Giao% khớp các chuỗi bắt đầu bằng Giao, sau đó có thể là bất kỳ chuỗi ký tự nào, kể cả chuỗi rỗng.

### 4.2. Tìm chuỗi kết thúc bằng hậu tố

~~~sql
SELECT order_id, note
FROM orders_demo
WHERE note LIKE '%tiên';
~~~

Pattern bắt đầu bằng %, vì vậy tìm chuỗi kết thúc bằng tiên.

### 4.3. Tìm chuỗi chứa một từ

~~~sql
SELECT order_id, note
FROM orders_demo
WHERE note LIKE '%đóng gói%';
~~~

Pattern này tìm chuỗi con ở bất kỳ vị trí nào. Với bảng lớn, kiểu pattern này thường tốn kém vì B-tree index không thể định vị một range dựa trên tiền tố cố định ở đầu pattern.

### 4.4. Dấu gạch dưới _ khớp đúng một ký tự

~~~sql
SELECT 'A7' LIKE 'A_' AS two_char_match,
       'A77' LIKE 'A_' AS three_char_match;
~~~

Kết quả lần lượt là TRUE và FALSE. Dấu gạch dưới khớp một ký tự, không phải một byte. Với character set đa byte như utf8mb4, một ký tự Unicode được xem là một ký tự cho wildcard _.

~~~sql
SELECT
    _utf8mb4'é' LIKE _utf8mb4'_' AS one_unicode_character;
~~~

Kết quả là TRUE vì é là một ký tự Unicode dù được mã hóa bằng nhiều byte trong UTF-8.

### 4.5. Ký tự đại diện có phân biệt hoa/thường và dấu không?

Với chuỗi không nhị phân, phép so sánh LIKE chịu ảnh hưởng bởi collation. Vì vậy, LIKE 'ann%' có thể khớp Anna nếu collation không phân biệt hoa/thường.

~~~sql
SELECT
    _utf8mb4'Anna' COLLATE utf8mb4_0900_ai_ci
        LIKE _utf8mb4'ann%' COLLATE utf8mb4_0900_ai_ci AS ci_match,
    _utf8mb4'Anna' COLLATE utf8mb4_0900_as_cs
        LIKE _utf8mb4'ann%' COLLATE utf8mb4_0900_as_cs AS cs_match;
~~~

Kết quả minh họa lần lượt là TRUE và FALSE.

Tương tự, collation accent-insensitive có thể cho phép pattern không dấu khớp chuỗi có dấu theo quy tắc collation. Với dữ liệu tiếng Việt, hãy thử bộ từ có đủ dấu và kiểm tra collation cụ thể trên server. Không mặc định mọi chữ cái tiếng Việt có dấu đều tương đương với chữ không dấu.

### 4.6. Khoảng trắng cuối chuỗi trong LIKE

Đối với LIKE, khoảng trắng cuối chuỗi có ý nghĩa trong phép so khớp. Không suy luận hành vi của LIKE từ phép so sánh bằng hoặc thuộc tính PAD SPACE của collation.

~~~sql
SELECT
    'abc' = 'abc ' AS equality_result,
    'abc' LIKE 'abc ' AS like_result;
~~~

Kết quả có thể khác nhau do quy tắc xử lý khoảng trắng của hai phép so sánh. Nếu dữ liệu có khoảng trắng cuối, hãy chuẩn hóa đầu vào theo nghiệp vụ và kiểm thử bằng chính toán tử được sử dụng.

## 5. Escape ký tự đại diện khi cần tìm literal

Đôi khi người dùng muốn tìm dấu % hoặc _ như ký tự bình thường, không phải wildcard. Khi đó cần escape.

MySQL mặc định dùng backslash để escape ký tự đại diện, nhưng hành vi backslash còn liên quan tới SQL mode như NO_BACKSLASH_ESCAPES. Có thể dùng ký tự escape riêng với mệnh đề ESCAPE để biểu đạt rõ ràng hơn.

Ví dụ dùng dấu chấm than ! làm escape:

~~~sql
SELECT product_code
FROM product
WHERE product_code LIKE 'A!_%' ESCAPE '!';
~~~

Trong pattern:
- !_ biểu thị dấu gạch dưới literal.
- % ở cuối vẫn là wildcard, khớp phần còn lại.

Tìm chuỗi chứa dấu phần trăm literal:

~~~sql
SELECT product_code
FROM product
WHERE product_code LIKE '%10!%%' ESCAPE '!';
~~~

Pattern này tìm chuỗi con 10% ở bất kỳ vị trí nào.

Tìm chính xác chuỗi 100%:

~~~sql
SELECT product_code
FROM product
WHERE product_code LIKE '100!%' ESCAPE '!';
~~~

Nếu chính ký tự escape xuất hiện trong dữ liệu, escape nó bằng cách lặp đôi theo quy tắc pattern. Ví dụ với escape !, dấu !! biểu thị một dấu chấm than literal.

Khi xây dựng pattern từ đầu vào người dùng, phải escape cả ký tự escape, % và _ nếu ý nghĩa là tìm chuỗi literal. Tham số hóa câu lệnh vẫn cần thiết để ngăn SQL injection; escape wildcard giải quyết ý nghĩa pattern, không thay thế prepared statement.

## 6. Kết hợp IN, BETWEEN, LIKE với AND/OR

Các điều kiện có thể kết hợp trong một mệnh đề WHERE:

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    total_amount,
    created_at,
    note
FROM orders_demo
WHERE status IN ('PAID', 'SHIPPED')
  AND total_amount BETWEEN 300 AND 1000
  AND note LIKE '%ưu tiên%'
ORDER BY created_at DESC;
~~~

Truy vấn lọc đơn hàng theo ba tiêu chí:
- Trạng thái thuộc tập PAID hoặc SHIPPED.
- Tổng tiền trong khoảng 300 đến 1000, bao gồm hai đầu mút.
- Ghi chú chứa cụm từ ưu tiên.

### 6.1. Dùng ngoặc khi kết hợp OR

AND có độ ưu tiên cao hơn OR. Để tránh điều kiện bị hiểu khác ý định, hãy dùng ngoặc:

~~~sql
SELECT order_id, status, total_amount
FROM orders_demo
WHERE (status = 'NEW' OR status = 'PAID')
  AND total_amount >= 100;
~~~

Không viết biểu thức dài mà phụ thuộc vào việc người đọc nhớ thứ tự ưu tiên. Ngoặc làm rõ nhóm điều kiện và giảm lỗi khi sửa truy vấn.

### 6.2. NULL vẫn ảnh hưởng điều kiện kết hợp

~~~sql
SELECT order_id
FROM orders_demo
WHERE note LIKE '%ưu tiên%'
   OR note IS NULL;
~~~

Biểu thức xử lý rõ hai trường hợp: ghi chú có cụm từ cần tìm hoặc không có ghi chú.

Nếu viết chỉ note NOT LIKE '%ưu tiên%', các hàng có note NULL không được trả về vì kết quả là UNKNOWN. Nếu muốn bao gồm NULL, phải ghi rõ OR note IS NULL.

## 7. Chọn toán tử phù hợp

| Nhu cầu | Toán tử | Ví dụ |
|---|---|---|
| Một trong nhiều trạng thái | IN | status IN ('NEW', 'PAID') |
| Một trong tập giá trị từ bảng khác | IN (subquery) | customer_id IN (SELECT ...) |
| Khoảng số bao gồm hai đầu | BETWEEN | amount BETWEEN 100 AND 500 |
| Khoảng ngày DATE bao gồm ngày đầu/cuối | BETWEEN | date_col BETWEEN '2025-01-01' AND '2025-01-31' |
| Khoảng DATETIME không bỏ sót cuối ngày | >= và < | created_at >= start AND created_at < next_start |
| Bắt đầu bằng tiền tố | LIKE | code LIKE 'AB%' |
| Kết thúc bằng hậu tố | LIKE | code LIKE '%XYZ' |
| Chứa chuỗi con | LIKE | name LIKE '%hoa%' |
| Tìm literal có chứa % hoặc _ | LIKE + ESCAPE | code LIKE '%!_%' ESCAPE '!' |
| Tìm hàng không có bản ghi liên quan | NOT EXISTS | Anti-join tương quan |

## 8. Index và hiệu năng

Cách viết điều kiện ảnh hưởng tới khả năng sử dụng index. Một điều kiện đúng về kết quả vẫn có thể tạo kế hoạch thực thi đắt đỏ nếu biểu thức làm mất khả năng định vị range.

### 8.1. IN trên cột có index

~~~sql
EXPLAIN
SELECT order_id, customer_id
FROM orders_demo
WHERE customer_id IN (10, 12, 15);
~~~

Optimizer có thể dùng index để tìm các giá trị trong danh sách. Với danh sách lớn, chi phí parse, tối ưu và truy cập nhiều range có thể tăng. Khi danh sách rất lớn, cân nhắc đưa các giá trị vào temporary table hoặc bảng staging rồi JOIN.

Không có một ngưỡng số phần tử IN cố định phù hợp mọi hệ thống. Hãy đo bằng dữ liệu và workload thực tế.

### 8.2. BETWEEN trên cột có index

~~~sql
EXPLAIN
SELECT order_id, created_at
FROM orders_demo
WHERE created_at >= '2025-03-01 00:00:00'
  AND created_at <  '2025-04-01 00:00:00';
~~~

Điều kiện khoảng trên cột gốc thường có thể dùng range access. Tránh viết:

~~~sql
WHERE DATE(created_at) = '2025-03-31'
~~~

nếu muốn dùng index thông thường trên created_at, vì hàm được áp dụng lên từng giá trị cột. Thay bằng:

~~~sql
WHERE created_at >= '2025-03-31 00:00:00'
  AND created_at <  '2025-04-01 00:00:00'
~~~

### 8.3. LIKE có tiền tố cố định

~~~sql
EXPLAIN
SELECT order_id
FROM orders_demo
WHERE note LIKE 'Giao%';
~~~

Khi pattern bắt đầu bằng chuỗi cố định rồi mới đến wildcard, MySQL có thể dùng B-tree index để định vị range nếu kiểu dữ liệu, collation và kế hoạch cho phép.

### 8.4. LIKE bắt đầu bằng wildcard

~~~sql
EXPLAIN
SELECT order_id
FROM orders_demo
WHERE note LIKE '%hành chính%';
~~~

Do không có tiền tố cố định, B-tree index thông thường không thể xác định một range bắt đầu từ một giá trị cụ thể. Truy vấn thường phải kiểm tra nhiều hàng.

Nếu cần tìm kiếm chuỗi con trên tập dữ liệu lớn, hãy đánh giá FULLTEXT, n-gram parser, search engine hoặc cấu trúc tìm kiếm chuyên biệt. FULLTEXT không hoàn toàn tương đương LIKE: quy tắc token, ngôn ngữ và cách tìm cụm từ khác nhau.

### 8.5. Composite index và thứ tự cột

Với index:

~~~sql
KEY idx_orders_status_created (status, created_at)
~~~

Truy vấn sau có thể tận dụng index theo status rồi range trên created_at:

~~~sql
SELECT order_id, status, created_at
FROM orders_demo
WHERE status IN ('PAID', 'SHIPPED')
  AND created_at >= '2025-03-01'
  AND created_at <  '2025-04-01';
~~~

Composite index tuân theo leftmost-prefix principle. Nếu truy vấn chỉ lọc created_at mà không có điều kiện trên status, index ghép này có thể không phù hợp bằng index bắt đầu từ created_at.

Không tạo index cho từng toán tử một cách máy móc. Hãy dựa vào tập truy vấn thực tế, độ chọn lọc, thứ tự cột, chi phí ghi và kết quả EXPLAIN.

## 9. Kiểu dữ liệu và chuyển đổi ngầm

Các toán tử IN và BETWEEN so sánh biểu thức với danh sách hoặc hai đầu mút. Nếu kiểu dữ liệu không tương thích, MySQL có thể chuyển đổi ngầm.

Ví dụ không nên dựa vào:

~~~sql
SELECT order_id
FROM orders_demo
WHERE customer_id IN ('10', '11', '12');
~~~

Cột là BIGINT nhưng danh sách là chuỗi. MySQL có thể chuyển đổi chuỗi sang số, nhưng dữ liệu không hợp lệ hoặc chuỗi chứa ký tự khác có thể gây kết quả khó đoán và warning.

Ưu tiên:

~~~sql
SELECT order_id
FROM orders_demo
WHERE customer_id IN (10, 11, 12);
~~~

Với ngày tháng, dùng literal theo định dạng chuẩn hoặc bind tham số đúng kiểu DATE/DATETIME từ driver. Tránh so sánh ngày bằng chuỗi định dạng địa phương như 31/03/2025.

Nếu cột là VARCHAR chứa số, hãy cân nhắc sửa schema thay vì CAST cột trong mọi truy vấn. Biểu thức chuyển đổi trên cột có thể làm giảm khả năng dùng index.

## 10. Tham số hóa truy vấn trong ứng dụng

Không ghép trực tiếp đầu vào người dùng vào SQL. Dùng prepared statement để tách câu lệnh khỏi dữ liệu.

### 10.1. IN với JDBC

JDBC không cho phép một placeholder ? tự đại diện cho một danh sách giá trị tùy ý. Mỗi phần tử trong IN cần một placeholder riêng:

~~~java
List<Long> customerIds = List.of(10L, 12L, 15L);

if (customerIds.isEmpty()) {
    return List.of();
}

String placeholders = String.join(
    ",",
    Collections.nCopies(customerIds.size(), "?")
);

String sql = """
    SELECT order_id, customer_id, status
    FROM orders_demo
    WHERE customer_id IN (%s)
    ORDER BY order_id
    """.formatted(placeholders);

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (int i = 0; i < customerIds.size(); i++) {
        ps.setLong(i + 1, customerIds.get(i));
    }

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả.
        }
    }
}
~~~

Phần tạo câu lệnh chỉ tạo số lượng dấu hỏi dựa trên kích thước danh sách. Giá trị thực được bind riêng, không nối trực tiếp vào SQL. Nếu danh sách rỗng, xử lý trước khi tạo IN để tránh IN ().

Với danh sách cực lớn, hãy cân nhắc temporary table hoặc bảng staging thay vì tạo hàng nghìn placeholder.

### 10.2. BETWEEN với JDBC

~~~java
String sql = """
    SELECT order_id, created_at
    FROM orders_demo
    WHERE created_at >= ?
      AND created_at < ?
    ORDER BY created_at
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, Timestamp.valueOf("2025-03-01 00:00:00"));
    ps.setTimestamp(2, Timestamp.valueOf("2025-04-01 00:00:00"));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả.
        }
    }
}
~~~

Ví dụ dùng khoảng nửa mở để lấy toàn bộ tháng 3. Trong ứng dụng thực tế, hãy dùng kiểu thời gian phù hợp với miền dữ liệu, múi giờ nghiệp vụ và API driver.

### 10.3. LIKE với JDBC

~~~java
String sql = """
    SELECT order_id, note
    FROM orders_demo
    WHERE note LIKE ? ESCAPE '!'
    """;

String pattern = "%hành chính%";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, pattern);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc kết quả.
        }
    }
}
~~~

Prepared statement ngăn dữ liệu người dùng trở thành cú pháp SQL. Nhưng % và _ trong tham số vẫn là wildcard của LIKE. Nếu API cần tìm chuỗi literal, phải escape wildcard trước khi thêm % ở hai đầu.

Ví dụ hàm escape Java:

~~~java
static String escapeLikeLiteral(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}

String pattern = "%" + escapeLikeLiteral(userInput) + "%";
~~~

Thứ tự thay thế rất quan trọng: escape ký tự escape trước, rồi mới escape % và _. Mệnh đề SQL phải dùng cùng ký tự ESCAPE '!'.

## 11. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| NOT IN không trả hàng như mong đợi | Danh sách hoặc subquery có NULL | Dùng NOT EXISTS hoặc loại NULL có chủ đích |
| IN với NULL không tìm được hàng NULL | NULL = NULL là UNKNOWN | Dùng IS NULL riêng |
| BETWEEN bỏ sót cuối ngày | DATETIME và đầu mút ngày được hiểu là 00:00:00 | Dùng >= start AND < next_start |
| BETWEEN không bao gồm đầu mút? | Hiểu nhầm ngữ nghĩa | BETWEEN bao gồm cả hai đầu mút |
| Khoảng không hợp lệ | Lower bound lớn hơn upper bound | Xác thực đầu mút trước khi truy vấn |
| LIKE không phân biệt hoa/thường như dự kiến | Collation của cột/biểu thức là case-insensitive | Kiểm tra collation |
| LIKE tìm nhầm ký tự % hoặc _ | Wildcard chưa được escape | Dùng ESCAPE và escape đầu vào |
| LIKE '%term%' chậm | Không có tiền tố cố định để dùng B-tree range | Đánh giá FULLTEXT/search index |
| IN () gây lỗi cú pháp | Ứng dụng tạo danh sách rỗng | Xử lý danh sách rỗng trước |
| Truy vấn chậm sau CAST/DATE/LOWER | Hàm áp dụng lên cột làm giảm khả năng dùng index | Dùng điều kiện sargable hoặc thiết kế index phù hợp |
| SQL injection qua bộ lọc | Ghép đầu vào trực tiếp vào câu lệnh | Prepared statement và whitelist cấu trúc động |

## 12. Quy trình phân tích một truy vấn lọc

Khi viết truy vấn có IN, BETWEEN hoặc LIKE, hãy làm theo thứ tự:

1. Xác định kiểu dữ liệu thật của cột và kiểu tham số.
2. Xác định NULL có hợp lệ không và muốn xử lý NULL thế nào.
3. Với IN, xác định danh sách có thể rỗng hoặc chứa NULL không.
4. Với BETWEEN, xác định đầu mút có bao gồm không; nếu là DATETIME, cân nhắc khoảng nửa mở.
5. Với LIKE, xác định % và _ là wildcard hay ký tự literal.
6. Xác định collation quyết định phân biệt hoa/thường và dấu.
7. Kiểm tra index và viết điều kiện trên cột gốc khi có thể.
8. Chạy EXPLAIN trên dữ liệu đại diện.
9. Đo thời gian, số hàng đọc và kết quả thực tế.
10. Dùng prepared statement khi đầu vào đến từ ứng dụng.

## 13. Bài tập thực hành

### Bài 1: Lọc theo nhiều trạng thái

Dùng orders_demo để tìm đơn hàng có trạng thái NEW, PAID hoặc SHIPPED bằng IN. Viết lại bằng OR và so sánh kết quả.

### Bài 2: Lọc khoảng số

Tìm đơn hàng có tổng tiền từ 100 đến 600. Thử thay đổi đầu mút và xác nhận BETWEEN bao gồm hai đầu.

### Bài 3: Lọc khoảng thời gian

Tìm toàn bộ đơn hàng trong tháng 3/2025. So sánh BETWEEN '2025-03-01' AND '2025-03-31' với khoảng >= '2025-03-01' AND < '2025-04-01'. Giải thích vì sao DATETIME cần khoảng nửa mở.

### Bài 4: LIKE và wildcard

Tìm ghi chú bắt đầu bằng Giao, kết thúc bằng tiên, chứa đóng gói. Sau đó chèn một ghi chú chứa ký tự % và _, rồi viết truy vấn tìm literal bằng ESCAPE.

### Bài 5: NULL trong IN và NOT IN

Tạo bảng danh sách mã bị chặn, chèn một hàng NULL. So sánh NOT IN với NOT EXISTS. Giải thích kết quả theo logic ba giá trị.

### Bài 6: Đọc EXPLAIN

Tạo index phù hợp cho customer_id, created_at và thử các truy vấn IN, BETWEEN, LIKE 'prefix%' và LIKE '%substring%'. Ghi lại access type, key và rows ước tính.

### Bài 7: Tham số hóa

Viết JDBC PreparedStatement cho IN với số lượng customer ID thay đổi, BETWEEN theo thời gian và LIKE tìm chuỗi literal. Xử lý trường hợp danh sách rỗng và ký tự wildcard do người dùng nhập.

## 14. Checklist trước khi đưa truy vấn vào ứng dụng

- [ ] Đã xác minh kiểu dữ liệu của cột và tham số.
- [ ] Đã hiểu IN/NOT IN khi danh sách chứa NULL.
- [ ] Đã xử lý danh sách IN rỗng.
- [ ] Đã biết BETWEEN bao gồm hai đầu mút.
- [ ] Đã dùng khoảng nửa mở cho DATETIME khi lọc trọn ngày/tháng.
- [ ] Đã xác định collation và độ nhạy hoa/thường, dấu của LIKE.
- [ ] Đã escape %, _ và ký tự escape khi cần tìm literal.
- [ ] Đã kiểm tra khoảng trắng cuối chuỗi nếu dữ liệu có thể chứa chúng.
- [ ] Đã tránh áp dụng hàm không cần thiết lên cột có index.
- [ ] Đã dùng prepared statement cho giá trị đầu vào.
- [ ] Đã kiểm tra EXPLAIN và đo trên dữ liệu đại diện.
- [ ] Đã xác minh kết quả bằng các trường hợp biên: NULL, rỗng, đầu mút và giá trị không khớp.

## 15. Kết luận

IN dùng để kiểm tra một giá trị thuộc tập hợp; BETWEEN lọc khoảng có tính cả hai đầu; LIKE tìm chuỗi theo mẫu với % và _. Khi dùng chúng, cần hiểu logic NULL, kiểu dữ liệu, collation và ý nghĩa của ký tự đại diện.

Để truy vấn vừa đúng vừa hiệu quả, hãy chọn điều kiện theo kiểu dữ liệu, dùng khoảng nửa mở cho DATETIME, xử lý NULL trong NOT IN, escape wildcard khi tìm literal, tham số hóa đầu vào và kiểm tra kế hoạch thực thi. Đây là nền tảng để xây dựng chức năng tìm kiếm và lọc dữ liệu an toàn trong ứng dụng MySQL.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Comparison Functions and Operators](https://dev.mysql.com/doc/refman/8.4/en/comparison-operators.html)
- [MySQL 8.4 Reference Manual – IN() Operator](https://dev.mysql.com/doc/refman/8.4/en/comparison-operators.html#function_in)
- [MySQL 8.4 Reference Manual – BETWEEN and NOT BETWEEN](https://dev.mysql.com/doc/refman/8.4/en/comparison-operators.html#operator_between)
- [MySQL 8.4 Reference Manual – LIKE Operator](https://dev.mysql.com/doc/refman/8.4/en/string-comparison-functions.html#operator_like)
- [MySQL 8.4 Reference Manual – Pattern Matching](https://dev.mysql.com/doc/refman/8.4/en/pattern-matching.html)
- [MySQL 8.4 Reference Manual – NULL Values](https://dev.mysql.com/doc/refman/8.4/en/working-with-null.html)
- [MySQL 8.4 Reference Manual – Range Optimization](https://dev.mysql.com/doc/refman/8.4/en/range-optimization.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – Prepared Statements](https://dev.mysql.com/doc/refman/8.4/en/sql-prepared-statements.html)


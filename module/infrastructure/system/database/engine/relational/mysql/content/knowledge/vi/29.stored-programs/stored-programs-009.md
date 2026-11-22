# Function trong biểu thức SQL và giới hạn tác dụng phụ

Stored function (hàm lưu trữ) là một routine do người dùng định nghĩa trong MySQL, nhận tham số đầu vào và trả về một giá trị đơn. Khác với stored procedure được gọi bằng CALL để thực hiện một quy trình, stored function có thể xuất hiện trực tiếp trong biểu thức SQL, chẳng hạn trong SELECT, WHERE, ORDER BY hoặc biểu thức UPDATE.

Khả năng gọi hàm ngay trong câu SQL giúp đóng gói quy tắc tính toán và tái sử dụng logic. Tuy nhiên, một function có thể đọc hoặc thay đổi dữ liệu, phụ thuộc thời gian hay trạng thái session, và được gọi trong quá trình MySQL xử lý nhiều hàng. Vì vậy, cần hiểu rõ đặc tính dữ liệu, quyền thực thi và các giới hạn của stored function trước khi đặt nó vào truy vấn.

Bài học thuộc phạm vi \`DATABASE_MYSQL\`: thiết kế stored function có kết quả rõ ràng, dùng hàm trong biểu thức SQL, phân biệt hàm thuần với hàm có tác dụng phụ, hiểu giới hạn transaction và bảng, kiểm soát quyền DEFINER/INVOKER, đồng thời tránh các vấn đề hiệu năng và replication.

## 1. Stored function khác stored procedure như thế nào?

Cả stored function và stored procedure đều là stored program được lưu trong database. Chúng có thể chứa câu lệnh SQL, biến cục bộ, điều kiện và vòng lặp. Điểm khác biệt chính nằm ở cách gọi và kết quả.

| Tiêu chí | Stored function | Stored procedure |
|---|---|---|
| Cách gọi | Trong biểu thức, ví dụ \`SELECT calculate_tax(...)\` | Bằng \`CALL procedure_name(...)\` |
| Kết quả | Phải trả về một giá trị qua \`RETURN\` | Có thể trả dữ liệu qua OUT/INOUT, result set hoặc tham số |
| Tham số | Tham số của function là IN | Hỗ trợ IN, OUT, INOUT |
| Nơi sử dụng | Có thể được dùng trong biểu thức SQL ở các ngữ cảnh được phép | Không thể đặt CALL trực tiếp như một scalar expression |
| Tác dụng phụ | Có thể đọc/ghi dữ liệu trong phạm vi được phép, nhưng cần thận trọng khi gọi từ biểu thức | Phù hợp hơn cho quy trình gồm nhiều thao tác và tác dụng phụ có chủ đích |
| Giao dịch | Không được tự COMMIT/ROLLBACK hoặc quản lý transaction như một procedure | Có thể điều phối transaction theo giới hạn của stored program |

Ví dụ gọi function:

~~~sql
SELECT calculate_discount(1000.00, 10);
~~~

Ví dụ gọi procedure:

~~~sql
CALL recalculate_customer_balance(1001);
~~~

Nếu mục tiêu là tính một giá trị cho từng hàng trong truy vấn, function thường phù hợp hơn. Nếu mục tiêu là thực hiện một quy trình ghi dữ liệu, kiểm tra nhiều bước hoặc trả nhiều tập kết quả, procedure thường dễ quản lý hơn.

## 2. Cấu trúc CREATE FUNCTION

Cú pháp tổng quát:

~~~sql
CREATE
    [DEFINER = user]
    FUNCTION function_name ([parameter[,...]])
    RETURNS data_type
    [characteristic ...]
    routine_body
~~~

Các thành phần:

- \`function_name\`: tên hàm trong schema.
- Tham số: mỗi tham số có tên và kiểu dữ liệu; tham số của stored function là IN.
- \`RETURNS\`: khai báo kiểu dữ liệu của giá trị trả về.
- \`characteristic\`: mô tả tính xác định, mức truy cập dữ liệu, ngôn ngữ SQL và quyền thực thi.
- \`routine_body\`: phần thân hàm, có thể là một statement hoặc compound block BEGIN ... END.

Ví dụ hàm tính tổng tiền một dòng hàng:

~~~sql
DELIMITER //

CREATE FUNCTION calculate_line_total(
    p_quantity INT,
    p_unit_price DECIMAL(12, 2)
)
RETURNS DECIMAL(14, 2)
DETERMINISTIC
NO SQL
SQL SECURITY INVOKER
BEGIN
    RETURN p_quantity * p_unit_price;
END//

DELIMITER ;
~~~

\`DELIMITER\` là lệnh của client như mysql command-line client để thay đổi dấu kết thúc statement khi gửi định nghĩa có nhiều dấu chấm phẩy. Nó không phải một câu lệnh SQL được gửi tới server và không được lưu trong routine.

Function phải trả về kiểu đã khai báo. Khi chạy, các nhánh xử lý cần bảo đảm có đường đi tới RETURN. Với kiểu số, hãy chọn precision/scale phù hợp để tránh tràn hoặc làm tròn ngoài ý muốn.

## 3. Dùng function trong biểu thức SELECT

Function trả về scalar nên có thể được gọi trong danh sách SELECT:

~~~sql
SELECT
    order_item_id,
    quantity,
    unit_price,
    calculate_line_total(quantity, unit_price) AS line_total
FROM order_item;
~~~

Mỗi hàng kết quả có một biểu thức gọi hàm với các giá trị của hàng đó. Hàm có thể đóng gói công thức tính toán dùng lại ở nhiều truy vấn.

Có thể kết hợp với biểu thức khác:

~~~sql
SELECT
    order_item_id,
    calculate_line_total(quantity, unit_price) * 1.08 AS total_with_tax
FROM order_item;
~~~

Hãy đặt alias dễ hiểu cho cột kết quả. Nếu hàm có quy tắc làm tròn, xử lý NULL hoặc chuyển đổi kiểu dữ liệu, cần định nghĩa rõ trong hàm và kiểm thử với dữ liệu biên.

### 3.1. Function trong WHERE

Function có thể được dùng trong predicate:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
WHERE calculate_discount(total_amount, 10) >= 500;
~~~

Câu lệnh hợp lệ về mặt ý tưởng nhưng có thể khó tối ưu. Nếu function nhận cột của từng hàng làm tham số, MySQL có thể phải đánh giá function cho nhiều hàng trước khi xác định hàng thỏa điều kiện.

Khi có thể biến đổi biểu thức về phép so sánh trực tiếp trên cột, cách viết đó thường dễ tận dụng index hơn. Ví dụ, nếu hàm chỉ giảm một tỷ lệ cố định, hãy tính ngưỡng ở phía ứng dụng hoặc biểu thức hằng:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE total_amount >= 555.56;
~~~

Chỉ viết lại khi đã chứng minh phép biến đổi tương đương về kiểu dữ liệu, độ chính xác và làm tròn.

### 3.2. Function trong ORDER BY và GROUP BY

~~~sql
SELECT
    customer_id,
    calculate_customer_score(customer_id) AS score
FROM customer
ORDER BY score DESC;
~~~

Có thể dùng function trong ORDER BY để sắp xếp theo giá trị trả về. Tuy nhiên, hàm có thể được tính cho nhiều hàng và MySQL có thể cần filesort.

Tương tự, function có thể xuất hiện trong GROUP BY:

~~~sql
SELECT
    normalize_phone(phone_number) AS normalized_phone,
    COUNT(*) AS customer_count
FROM customer
GROUP BY normalize_phone(phone_number);
~~~

Nếu biểu thức hàm phức tạp và được dùng thường xuyên, cân nhắc lưu giá trị đã chuẩn hóa hoặc dùng generated column/index phù hợp. Stored function không tự tạo index trên kết quả của nó; khả năng index hóa biểu thức phụ thuộc các quy tắc riêng của functional index và generated column trong MySQL.

## 4. Function trong INSERT và UPDATE

Stored function cũng có thể cung cấp giá trị cho thao tác ghi:

~~~sql
INSERT INTO order_summary (
    order_id,
    subtotal,
    tax_amount
)
VALUES (
    1001,
    calculate_subtotal(1001),
    calculate_tax(1001)
);
~~~

Hoặc dùng trong biểu thức UPDATE:

~~~sql
UPDATE order_item
SET line_total = calculate_line_total(quantity, unit_price)
WHERE order_id = 1001;
~~~

Cần nhớ rằng function được gọi như một phần của statement đang ghi dữ liệu. Các giới hạn về bảng đang được statement sử dụng, transaction và replication vẫn áp dụng.

Nếu function chỉ tính toán từ tham số, đây thường là cách dùng đơn giản. Nếu function đọc nhiều bảng hoặc ghi dữ liệu, hãy đánh giá số lần gọi, thứ tự thực thi, lock và tác dụng phụ trước khi dùng trong một câu lệnh cập nhật hàng loạt.

## 5. Function có thể đọc dữ liệu: READS SQL DATA

Function có thể truy vấn bảng để trả về một giá trị. Ví dụ lấy hạng thành viên theo customer_id:

~~~sql
CREATE TABLE customer_profile (
    customer_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_tier VARCHAR(20) NOT NULL
) ENGINE = InnoDB;
~~~

Function:

~~~sql
DELIMITER //

CREATE FUNCTION get_customer_tier(
    p_customer_id BIGINT UNSIGNED
)
RETURNS VARCHAR(20)
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_tier VARCHAR(20) DEFAULT NULL;

    SELECT customer_tier
      INTO v_tier
      FROM customer_profile
     WHERE customer_id = p_customer_id;

    RETURN v_tier;
END//

DELIMITER ;
~~~

Gọi:

~~~sql
SELECT
    order_id,
    customer_id,
    get_customer_tier(customer_id) AS customer_tier
FROM orders;
~~~

Hàm dùng \`SELECT ... INTO\` để gán một giá trị vào biến cục bộ. Nó không phát result set ra client.

### 5.1. SELECT ... INTO phải trả tối đa một hàng

Nếu SELECT ... INTO trả nhiều hơn một hàng, MySQL báo lỗi. Ví dụ trên an toàn vì customer_id là PRIMARY KEY.

Nếu không có hàng, MySQL phát cảnh báo NOT FOUND và biến đích giữ giá trị trước đó. Vì vậy, ví dụ đã khởi tạo \`v_tier\` thành NULL. Với logic phức tạp hơn, có thể khai báo handler NOT FOUND để xử lý trường hợp không tìm thấy:

~~~sql
DECLARE v_tier VARCHAR(20) DEFAULT NULL;
DECLARE CONTINUE HANDLER FOR NOT FOUND
    SET v_tier = NULL;
~~~

Khai báo biến, condition, cursor và handler phải tuân theo thứ tự khai báo trong compound block: biến/condition trước cursor, cursor trước handler, rồi mới đến statement thực thi.

### 5.2. Hàm đọc bảng có thể tạo chi phí lặp

Trong truy vấn:

~~~sql
SELECT
    order_id,
    get_customer_tier(customer_id)
FROM orders;
~~~

Nếu truy vấn trả về 100.000 hàng, function có thể được gọi rất nhiều lần và mỗi lần lại truy vấn customer_profile. Đây là dạng chi phí tương tự N+1 query ở bên trong server.

Thường có thể viết trực tiếp bằng JOIN:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    cp.customer_tier
FROM orders AS o
LEFT JOIN customer_profile AS cp
  ON cp.customer_id = o.customer_id;
~~~

JOIN giúp optimizer nhìn thấy quan hệ dữ liệu và chọn access path tổng thể. Dùng function đọc bảng khi logic thật sự cần đóng gói và khối lượng gọi đã được đo; không dùng nó như cách thay thế JOIN cho mọi truy vấn.

## 6. Khai báo đặc tính dữ liệu của function

CREATE FUNCTION có các characteristic mô tả quan hệ của hàm với dữ liệu.

| Characteristic | Ý nghĩa |
|---|---|
| NO SQL | Hàm không chứa câu lệnh SQL |
| CONTAINS SQL | Hàm có chứa SQL nhưng không đọc/ghi dữ liệu |
| READS SQL DATA | Hàm đọc dữ liệu |
| MODIFIES SQL DATA | Hàm có thể thay đổi dữ liệu |
| DETERMINISTIC | Cùng đầu vào được khai báo sẽ cho cùng kết quả |
| NOT DETERMINISTIC | Kết quả có thể thay đổi ngay cả khi đầu vào giống nhau |

Ví dụ hàm tính toán thuần:

~~~sql
CREATE FUNCTION calculate_vat(
    p_amount DECIMAL(14, 2),
    p_rate DECIMAL(5, 2)
)
RETURNS DECIMAL(14, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_amount * p_rate / 100, 2);
~~~

Ví dụ function đọc bảng:

~~~sql
CREATE FUNCTION lookup_customer_tier(p_customer_id BIGINT UNSIGNED)
RETURNS VARCHAR(20)
NOT DETERMINISTIC
READS SQL DATA
RETURN (
    SELECT customer_tier
    FROM customer_profile
    WHERE customer_id = p_customer_id
);
~~~

Ví dụ thứ hai dùng scalar subquery trong RETURN. Truy vấn phải trả tối đa một hàng; nên có unique key bảo đảm tính duy nhất. Nếu không có hàng, kết quả là NULL; nếu có nhiều hàng, scalar subquery gây lỗi.

### 6.1. DETERMINISTIC là lời khai báo của người tạo

MySQL không phân tích toàn bộ thân hàm để chứng minh nó thực sự deterministic. Người tạo phải khai báo trung thực.

Không khai báo DETERMINISTIC cho function phụ thuộc vào:
- NOW(), CURRENT_TIMESTAMP hoặc thời điểm thực thi.
- RAND() hoặc nguồn ngẫu nhiên.
- UUID() hoặc giá trị sinh thay đổi.
- Biến session, user variable hoặc trạng thái connection.
- Dữ liệu bảng có thể thay đổi giữa các lần gọi.
- Trạng thái bên ngoài mà cùng tham số không bảo đảm cùng kết quả.

Một function chỉ tính \`p_amount * p_rate\` từ tham số có thể là DETERMINISTIC. Một function đọc giá hiện hành từ bảng sản phẩm thường không nên được mô tả là deterministic nếu kết quả phụ thuộc dữ liệu có thể thay đổi.

### 6.2. SQL data access characteristic cũng phải khai báo trung thực

Các characteristic như READS SQL DATA và MODIFIES SQL DATA mô tả loại truy cập dữ liệu của routine. Chúng không phải cơ chế sandbox tự động ngăn function thực hiện hành vi trái với khai báo.

Ví dụ, khai báo READS SQL DATA không biến một câu UPDATE trong thân hàm thành thao tác chỉ đọc. Người tạo phải mô tả đúng nội dung routine và kiểm thử quyền thực tế.

## 7. Tác dụng phụ là gì?

Tác dụng phụ (side effect) là thay đổi trạng thái bên ngoài giá trị trả về của hàm. Ví dụ:
- INSERT một dòng audit.
- UPDATE bộ đếm.
- Thay đổi trạng thái một bảng.
- Ghi nhận lần truy cập.
- Thay đổi trạng thái session hoặc tương tác với dữ liệu khác.

Một hàm tính toán thuần chỉ nhận tham số và trả kết quả thường dễ dùng trong biểu thức SQL hơn. Một hàm có tác dụng phụ khiến việc gọi hàm trong truy vấn trở nên khó dự đoán.

Ví dụ minh họa một function có ghi dữ liệu:

~~~sql
DELIMITER //

CREATE FUNCTION record_calculation(p_order_id BIGINT UNSIGNED)
RETURNS INT
MODIFIES SQL DATA
SQL SECURITY DEFINER
BEGIN
    INSERT INTO calculation_audit(order_id, recorded_at)
    VALUES (p_order_id, NOW(6));

    RETURN 1;
END//

DELIMITER ;
~~~

Function này không chỉ tính giá trị; nó còn ghi một dòng vào calculation_audit. Nếu gọi nó trong một SELECT trên nhiều hàng, tác dụng phụ có thể phát sinh nhiều lần.

Không nên dùng function kiểu này như một cách “gọi một lần cho mỗi hàng” để thực hiện quy trình ghi audit. SQL là ngôn ngữ khai báo; thứ tự và cách optimizer đánh giá biểu thức không phải hợp đồng thủ tục mà ứng dụng nên dựa vào.

## 8. Vì sao không nên đặt tác dụng phụ trong biểu thức SQL?

Giả sử:

~~~sql
SELECT
    order_id,
    record_calculation(order_id)
FROM orders
WHERE status = 'PAID';
~~~

Người viết có thể nghĩ hàm sẽ được gọi đúng một lần cho mỗi hàng hiển thị. Nhưng đây là giả định không an toàn vì:
- Optimizer có thể thay đổi kế hoạch truy cập và cách đánh giá biểu thức.
- Điều kiện lọc có thể được thực hiện trước hoặc trong quá trình lấy dữ liệu.
- Biểu thức có thể được đánh giá trong các bước trung gian khác nhau.
- Một thay đổi index hoặc kế hoạch có thể làm số lần đánh giá thay đổi.
- Retry từ client có thể chạy lại toàn bộ statement.
- Một lỗi giữa chừng có thể làm statement/transaction rollback theo engine, trong khi tác dụng phụ ngoài database không thể tự rollback.

Với các tác dụng phụ nằm trong cùng transaction InnoDB, thay đổi dữ liệu có thể được commit/rollback theo transaction của statement. Tuy nhiên, điều đó không biến số lần gọi thành một cam kết ổn định, cũng không làm cho side effect phù hợp với ngữ nghĩa truy vấn.

Nếu cần ghi audit cho các hàng được cập nhật, hãy dùng một quy trình DML rõ ràng, trigger phù hợp hoặc stored procedure điều phối transaction. Nếu cần gửi email/gọi API, dùng outbox hoặc tầng ứng dụng sau khi transaction commit; không gọi dịch vụ bên ngoài từ function trong biểu thức SQL.

## 9. Giới hạn quan trọng của stored function

Stored function có nhiều hạn chế hơn stored procedure vì nó được gọi như một phần của biểu thức SQL.

Các giới hạn chính cần nhớ:

1. Function phải trả về một giá trị scalar bằng RETURN.
2. Không được trả result set trực tiếp cho client.
3. Không được dùng dynamic SQL qua PREPARE/EXECUTE trong function.
4. Không được gọi stored procedure từ function.
5. Không được thực hiện START TRANSACTION, COMMIT hoặc ROLLBACK trong function.
6. Không được thực hiện các câu lệnh gây implicit commit.
7. Không được sửa một bảng đang được statement gọi function sử dụng.
8. Function không được đệ quy.
9. Tham số function không có mode OUT hoặc INOUT.
10. Các statement bị cấm khác được quy định trong manual cho stored function và trigger.

### 9.1. Không trả result set

Không viết SELECT trần để phát dữ liệu ra client:

~~~sql
-- Không hợp lệ trong stored function:
SELECT customer_id, customer_tier
FROM customer_profile;
~~~

Dùng SELECT ... INTO để gán một giá trị vào biến cục bộ:

~~~sql
SELECT customer_tier
INTO v_tier
FROM customer_profile
WHERE customer_id = p_customer_id;
~~~

Function trả về giá trị bằng RETURN:

~~~sql
RETURN v_tier;
~~~

Nếu cần trả nhiều hàng, dùng procedure với SELECT tạo result set hoặc truy vấn trực tiếp thay vì cố biến function thành một API trả bảng.

### 9.2. Không dùng dynamic SQL

Stored function không được dùng câu lệnh prepared statement SQL như PREPARE, EXECUTE và DEALLOCATE PREPARE. Nếu cần xây dựng câu lệnh động dựa trên tên bảng/cột, hãy dùng stored procedure hoặc tầng ứng dụng và kiểm soát identifier bằng whitelist.

### 9.3. Không gọi procedure từ function

Function có thể gọi function khác trong phạm vi các quy tắc routine, nhưng không thể gọi stored procedure bằng CALL. Nếu quy trình cần gọi nhiều thao tác hoặc procedure, hãy đặt điều phối ở procedure hoặc ứng dụng.

### 9.4. Không quản lý transaction bên trong function

Function không thể tự mở transaction, COMMIT hoặc ROLLBACK. Transaction thuộc về statement hoặc transaction của caller.

Điều này giúp function không tự ý kết thúc transaction mà truy vấn bên ngoài đang tham gia. Nếu nghiệp vụ cần nhiều bước ghi có ranh giới transaction, dùng procedure hoặc ứng dụng điều khiển transaction.

### 9.5. Không sửa bảng đang được statement gọi function sử dụng

Một stored function hoặc trigger không được sửa một bảng đang được statement gọi nó sử dụng (để đọc hoặc ghi). Ví dụ, nếu statement đang UPDATE bảng account và function được gọi trong biểu thức lại cố UPDATE chính account, MySQL có thể báo lỗi 1442.

Ví dụ về mẫu thiết kế cần tránh:

~~~sql
UPDATE account
SET balance = balance + adjust_balance(account_id)
WHERE account_id = 10;
~~~

Nếu adjust_balance() lại UPDATE account, function đang cố sửa bảng mà statement bên ngoài đã dùng. Hãy đưa logic cập nhật vào một statement rõ ràng hoặc procedure điều phối.

### 9.6. Không đệ quy

Stored function không được gọi đệ quy. Nếu cần xử lý cấu trúc cây hoặc lặp qua tập dữ liệu, cân nhắc recursive CTE, vòng lặp ở stored procedure hoặc logic ứng dụng.

## 10. SQL SECURITY DEFINER và INVOKER

Stored function có thể chạy với quyền của người định nghĩa (DEFINER) hoặc người gọi (INVOKER).

- \`SQL SECURITY DEFINER\`: function thực thi với quyền của account được chỉ định làm definer. Đây là mặc định nếu không khai báo SQL SECURITY.
- \`SQL SECURITY INVOKER\`: function thực thi với quyền của account gọi function.

### 10.1. DEFINER

Ví dụ:

~~~sql
CREATE DEFINER = 'routine_owner'@'localhost'
FUNCTION get_public_customer_name(p_customer_id BIGINT UNSIGNED)
RETURNS VARCHAR(150)
READS SQL DATA
SQL SECURITY DEFINER
BEGIN
    DECLARE v_name VARCHAR(150);

    SELECT customer_name
      INTO v_name
      FROM customer
     WHERE customer_id = p_customer_id;

    RETURN v_name;
END;
~~~

Người gọi có quyền EXECUTE trên function có thể gọi nó mà không cần trực tiếp có quyền SELECT trên bảng customer, nếu definer có quyền cần thiết và cấu hình routine cho phép.

Đây là cơ chế hữu ích để cung cấp API dữ liệu có kiểm soát, nhưng cũng là rủi ro nếu function cho phép người dùng truyền tham số để đọc hoặc thay đổi dữ liệu vượt quá phạm vi được phép.

### 10.2. INVOKER

~~~sql
CREATE FUNCTION get_customer_name(p_customer_id BIGINT UNSIGNED)
RETURNS VARCHAR(150)
READS SQL DATA
SQL SECURITY INVOKER
BEGIN
    DECLARE v_name VARCHAR(150);

    SELECT customer_name
      INTO v_name
      FROM customer
     WHERE customer_id = p_customer_id;

    RETURN v_name;
END;
~~~

Người gọi cần có quyền phù hợp để đọc customer. INVOKER phù hợp khi muốn quyền truy cập bảng được kiểm soát theo từng user gọi.

### 10.3. Nguyên tắc bảo mật

- Dùng account riêng, quyền tối thiểu làm definer.
- Tránh dùng root hoặc account quản trị làm definer.
- Chỉ cấp EXECUTE cho nhóm người dùng cần gọi function.
- Rà soát function có SQL SECURITY DEFINER và các bảng nó truy cập.
- Kiểm tra definer còn tồn tại và có quyền cần thiết sau khi triển khai/migrate.
- Không ghép chuỗi đầu vào thành SQL động; function vốn không hỗ trợ prepared dynamic SQL.
- Không trả dữ liệu nhạy cảm chỉ vì caller có quyền EXECUTE.

## 11. Quyền tạo, sửa và gọi stored function

Các quyền thường liên quan:
- CREATE ROUTINE để tạo routine.
- ALTER ROUTINE để sửa hoặc xóa routine theo quyền được cấp.
- EXECUTE để gọi routine.
- Quyền trên các đối tượng mà routine truy cập, tùy SQL SECURITY DEFINER/INVOKER.

Kiểm tra định nghĩa:

~~~sql
SHOW CREATE FUNCTION get_customer_tier;
~~~

Liệt kê routine trong schema:

~~~sql
SELECT
    ROUTINE_SCHEMA,
    ROUTINE_NAME,
    ROUTINE_TYPE,
    DATA_TYPE,
    IS_DETERMINISTIC,
    SQL_DATA_ACCESS,
    SECURITY_TYPE,
    DEFINER
FROM information_schema.routines
WHERE ROUTINE_SCHEMA = DATABASE()
  AND ROUTINE_TYPE = 'FUNCTION'
ORDER BY ROUTINE_NAME;
~~~

Cấp quyền gọi:

~~~sql
GRANT EXECUTE
ON FUNCTION app_db.get_customer_tier
TO 'report_user'@'%';
~~~

Cú pháp account và phạm vi quyền phải phù hợp môi trường thực tế. Trước khi cấp EXECUTE cho function DEFINER, hãy đọc SHOW CREATE FUNCTION và xác minh quyền mà definer đang có.

## 12. Stored function và binary logging/replication

Khi binary logging được bật, MySQL áp dụng các điều kiện bổ sung cho việc tạo stored function để hạn chế routine có thể làm replica nhận kết quả khác source.

Trong cấu hình không tin cậy creator mặc định, việc tạo function có thể yêu cầu quyền quản trị phù hợp và khai báo đặc tính xác định/truy cập dữ liệu theo quy tắc của phiên bản. Biến \`log_bin_trust_function_creators\` ảnh hưởng cách server áp dụng các điều kiện này.

Kiểm tra:

~~~sql
SELECT
    @@GLOBAL.log_bin,
    @@GLOBAL.log_bin_trust_function_creators,
    @@GLOBAL.binlog_format;
~~~

### 12.1. Vì sao DETERMINISTIC quan trọng?

Với statement-based replication, replica thực thi lại câu lệnh SQL. Nếu function phụ thuộc vào thời gian, ngẫu nhiên, session state hoặc dữ liệu không đồng nhất, kết quả trên replica có thể khác source.

Row-based replication ghi các thay đổi hàng thực tế vào binary log, giảm phụ thuộc vào việc chạy lại cùng biểu thức trên replica. Tuy nhiên, không vì thế mà có thể khai báo sai DETERMINISTIC hoặc bỏ qua yêu cầu bảo mật và quyền tạo routine.

### 12.2. Không khai báo sai để vượt qua kiểm tra

Không đánh dấu function là DETERMINISTIC chỉ để CREATE FUNCTION thành công nếu kết quả thực tế phụ thuộc trạng thái thay đổi. Khai báo sai có thể khiến MySQL đánh giá sai mức an toàn của routine và gây khác biệt khi replication.

Khi thiết kế:
- Function tính toán thuần: DETERMINISTIC và NO SQL nếu đúng.
- Function chỉ đọc bảng: READS SQL DATA; đánh giá tính xác định theo dữ liệu mà nó phụ thuộc.
- Function ghi dữ liệu: MODIFIES SQL DATA; kiểm tra replication và tác dụng phụ rất kỹ.
- Function phụ thuộc trạng thái ngoài đầu vào: thường NOT DETERMINISTIC.

Yêu cầu quyền chính xác và hành vi binlog có thể thay đổi theo phiên bản MySQL. Hãy kiểm tra manual của phiên bản server triển khai.

## 13. Hiệu năng khi gọi function trong truy vấn

Một stored function có thể được gọi nhiều lần trong một statement. Chi phí bao gồm:
- Chi phí vào/ra routine.
- Chi phí thực thi các biểu thức trong thân hàm.
- Chi phí đọc/ghi bảng mà function sử dụng.
- Chi phí khóa và kiểm tra constraint nếu có DML.
- Chi phí lặp lại theo số hàng và số lần biểu thức được đánh giá.

### 13.1. Function thuần vẫn có overhead

Ngay cả function chỉ nhân hai số cũng có overhead gọi routine so với biểu thức SQL viết trực tiếp. Nếu logic rất đơn giản và chỉ dùng một lần, viết biểu thức trực tiếp có thể rõ và nhanh hơn.

~~~sql
SELECT quantity * unit_price AS line_total
FROM order_item;
~~~

Nếu công thức được dùng ở nhiều nơi và cần một định nghĩa thống nhất, function có thể giúp bảo trì. Hãy đo khi truy vấn có hàng triệu dòng hoặc được gọi thường xuyên.

### 13.2. Function đọc bảng dễ tạo N lần lookup

Tránh:

~~~sql
SELECT
    o.order_id,
    get_customer_tier(o.customer_id)
FROM orders AS o;
~~~

khi có thể JOIN:

~~~sql
SELECT
    o.order_id,
    cp.customer_tier
FROM orders AS o
LEFT JOIN customer_profile AS cp
  ON cp.customer_id = o.customer_id;
~~~

JOIN thường cho optimizer nhiều thông tin hơn để chọn access path và join order. Function đọc bảng có thể thực hiện lookup lặp lại, khiến chi phí tăng theo số hàng.

### 13.3. Function trên cột trong WHERE có thể cản index

Ví dụ:

~~~sql
SELECT order_id
FROM orders
WHERE normalize_code(order_code) = 'ABC';
~~~

Nếu function được áp dụng lên cột, index thông thường trên order_code thường không thể dùng trực tiếp như phép so sánh sargable trên giá trị gốc.

Nếu có thể chuẩn hóa đầu vào trước khi truy vấn:

~~~sql
SELECT order_id
FROM orders
WHERE order_code = 'ABC';
~~~

Nếu logic chuẩn hóa phải được duy trì trong database, cân nhắc generated column hoặc functional index theo các quy tắc MySQL hỗ trợ; không giả định stored function bất kỳ đều có thể được dùng trực tiếp làm index expression.

### 13.4. Đo bằng EXPLAIN và EXPLAIN ANALYZE

~~~sql
EXPLAIN
SELECT
    order_id,
    calculate_line_total(quantity, unit_price)
FROM order_item
WHERE order_id >= 100000;
~~~

Trên MySQL 8.0.18 trở lên:

~~~sql
EXPLAIN ANALYZE
SELECT
    order_id,
    calculate_line_total(quantity, unit_price)
FROM order_item
WHERE order_id >= 100000;
~~~

EXPLAIN ANALYZE thực thi SELECT. So sánh thời gian, số hàng và iterator; nếu cần so sánh function với biểu thức trực tiếp, dùng cùng dữ liệu, cùng predicate và nhiều lần đo trong điều kiện tương đương.

## 14. NULL, kiểu dữ liệu và lỗi trong function

Function cần có hợp đồng rõ ràng về đầu vào và kết quả.

### 14.1. NULL propagation

Trong MySQL, phép nhân với NULL thường trả NULL:

~~~sql
SELECT calculate_line_total(2, NULL);
~~~

Kết quả sẽ là NULL nếu function chỉ RETURN \`p_quantity * p_unit_price\`.

Nếu nghiệp vụ xem giá NULL là 0, hãy thể hiện rõ:

~~~sql
RETURN p_quantity * COALESCE(p_unit_price, 0);
~~~

Không tự chuyển NULL thành 0 nếu NULL có nghĩa chưa biết hoặc thiếu dữ liệu.

### 14.2. Precision và scale

Nếu RETURNS DECIMAL(14,2), hãy kiểm tra:
- Giá trị đầu vào lớn nhất.
- Phép nhân/cộng trung gian.
- Quy tắc ROUND.
- Giá trị âm hoặc số lượng không hợp lệ.
- Chuyển đổi kiểu khi trả kết quả.

Không dùng FLOAT/DOUBLE cho tiền nếu nghiệp vụ yêu cầu phép tính thập phân chính xác.

### 14.3. SIGNAL để báo lỗi nghiệp vụ

Function có thể phát sinh lỗi có chủ đích bằng SIGNAL trong những trường hợp phù hợp:

~~~sql
IF p_quantity < 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Quantity must not be negative';
END IF;
~~~

SIGNAL dừng quá trình thực thi routine và trả lỗi cho caller. Chỉ dùng để kiểm tra điều kiện đầu vào mà function thực sự chịu trách nhiệm; không biến function thành một workflow có nhiều tác dụng phụ và nhiều nhánh lỗi.

## 15. Thay đổi và xóa function

Xem định nghĩa:

~~~sql
SHOW CREATE FUNCTION calculate_line_total;
~~~

Xóa function:

~~~sql
DROP FUNCTION IF EXISTS calculate_line_total;
~~~

MySQL hỗ trợ ALTER FUNCTION để thay đổi một số characteristic của routine, nhưng không dùng ALTER FUNCTION để thay phần thân SQL như chỉnh sửa một câu UPDATE. Khi cần thay body, thường phải DROP rồi CREATE lại hoặc triển khai theo quy trình migration phù hợp.

Trước khi thay đổi function đang được ứng dụng gọi:
- Kiểm tra các truy vấn và routine phụ thuộc.
- Xác định chữ ký tham số và kiểu trả về.
- Kiểm tra quyền EXECUTE và DEFINER.
- Lên kế hoạch tương thích khi deploy.
- Có phương án khôi phục định nghĩa cũ.

Không xóa function đang được sử dụng mà chưa xác định dependency trong ứng dụng.

## 16. Khi nào nên dùng function, procedure hay JOIN?

| Bài toán | Lựa chọn thường phù hợp | Lý do |
|---|---|---|
| Tính một giá trị từ các tham số | Stored function | Có thể dùng trực tiếp trong biểu thức |
| Chuẩn hóa hoặc chuyển đổi một giá trị | Function thuần hoặc biểu thức SQL | Kết quả dễ kiểm thử, ít tác dụng phụ |
| Đọc thuộc tính từ bảng liên quan cho nhiều hàng | JOIN | Optimizer thấy quan hệ và có thể tối ưu toàn truy vấn |
| Cập nhật nhiều bảng theo một quy trình | Procedure hoặc ứng dụng quản lý transaction | Điều phối các bước và lỗi rõ ràng |
| Trả nhiều hàng hoặc nhiều result set | SELECT trực tiếp hoặc procedure | Function chỉ trả scalar |
| Ghi audit cho thao tác cụ thể | Trigger hoặc DML/procedure có chủ đích | Gắn tác dụng phụ với sự kiện ghi rõ ràng |
| Gọi API, gửi email hoặc thao tác bên ngoài | Tầng ứng dụng/outbox | Kiểm soát retry và tác dụng phụ ngoài database |

Một function tốt thường có đầu vào, đầu ra và đặc tính dữ liệu rõ ràng. Nếu phải thêm nhiều tác dụng phụ để làm nó hữu ích, hãy xem lại liệu procedure hoặc logic ứng dụng có phù hợp hơn không.

## 17. Quy trình thiết kế stored function an toàn

1. Xác định function cần trả một scalar value hay thực hiện một quy trình.
2. Chọn kiểu RETURNS đủ precision và đúng semantics NULL.
3. Khai báo tham số IN với kiểu phù hợp.
4. Xác định function có đọc hoặc sửa dữ liệu không.
5. Khai báo DETERMINISTIC/NOT DETERMINISTIC trung thực.
6. Khai báo NO SQL, READS SQL DATA hoặc MODIFIES SQL DATA đúng thực tế.
7. Chọn SQL SECURITY DEFINER hoặc INVOKER theo mô hình quyền.
8. Kiểm tra function không dùng dynamic SQL, CALL procedure, transaction control hoặc result set.
9. Kiểm tra không sửa bảng mà statement gọi function đang sử dụng.
10. Đánh giá số lần gọi khi function được đặt trong SELECT/WHERE/ORDER BY.
11. So sánh với JOIN hoặc biểu thức trực tiếp nếu function đọc bảng hay xử lý nhiều hàng.
12. Kiểm tra binary logging và replication.
13. Cấp quyền CREATE ROUTINE/EXECUTE tối thiểu.
14. Kiểm thử NULL, dữ liệu biên, không có hàng, nhiều hàng và lỗi nghiệp vụ.
15. Đo bằng EXPLAIN/EXPLAIN ANALYZE và workload đại diện.
16. Triển khai thay đổi theo migration có kiểm soát và xác minh định nghĩa sau deploy.

## 18. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Nguyên nhân | Cách xử lý |
|---|---|---|
| Function không có RETURN trên một nhánh | Function phải trả giá trị theo RETURNS | Bảo đảm mọi đường đi hợp lệ có RETURN |
| SELECT trong function trả result set | Function không được phát result set cho client | Dùng SELECT ... INTO hoặc RETURN scalar |
| SELECT ... INTO trả nhiều hàng | Truy vấn không bảo đảm duy nhất | Dùng PRIMARY KEY/UNIQUE hoặc giới hạn logic rõ ràng |
| Function được gọi hàng triệu lần | Hàm nằm trong biểu thức theo từng hàng | Đo và cân nhắc JOIN hoặc tính trước |
| Function trong WHERE không dùng index | Hàm bọc cột làm predicate khó sargable | Viết predicate trực tiếp hoặc dùng cấu trúc index phù hợp |
| Khai báo DETERMINISTIC sai | Kết quả phụ thuộc thời gian, bảng hoặc session | Khai báo đúng bản chất và kiểm tra replication |
| READS SQL DATA nhưng thân hàm UPDATE | Characteristic khai báo sai; không phải sandbox | Sửa characteristic và kiểm tra hành vi |
| Function ghi bảng đang được statement sử dụng | Vi phạm giới hạn routine/trigger | Tách logic thành statement hoặc procedure |
| Gọi procedure từ function | CALL procedure không được phép trong function | Đưa điều phối vào procedure/caller |
| COMMIT trong function | Function không được quản lý transaction | Để caller quản lý transaction |
| Function DEFINER mở quyền quá rộng | Caller có thể gián tiếp dùng quyền definer | Dùng definer quyền tối thiểu, rà soát EXECUTE |
| Replication khác kết quả | Function không deterministic hoặc khai báo sai | Kiểm tra binlog format, đặc tính routine và dữ liệu |
| Dùng side effect trong SELECT | Số lần/thứ tự đánh giá không phải hợp đồng thủ tục | Dùng DML/procedure/outbox rõ ràng |
| Không tìm thấy routine sau deploy | Sai schema, quyền hoặc definer | SHOW CREATE FUNCTION và kiểm tra INFORMATION_SCHEMA |

## 19. Bài tập thực hành

### Bài 1: Function thuần

Tạo function calculate_line_total(quantity, unit_price) trả DECIMAL. Kiểm thử số dương, số 0, NULL, số lượng âm và giá trị lớn. Quyết định function có cần SIGNAL cho quantity âm hay không.

### Bài 2: Function trong SELECT

Dùng function tính tổng dòng cho bảng order_item. So sánh kết quả với biểu thức quantity * unit_price trực tiếp. Kiểm tra độ chính xác và thời gian trên tập dữ liệu lớn.

### Bài 3: Function trong WHERE

Tạo function chuẩn hóa mã đơn hàng rồi dùng trong WHERE. So sánh EXPLAIN với truy vấn so sánh cột trực tiếp sau khi chuẩn hóa tham số. Giải thích tác động lên index.

### Bài 4: Function đọc bảng

Tạo get_customer_tier(customer_id) dùng SELECT ... INTO. Thử trường hợp có một hàng, không có hàng và nhiều hàng. Sau đó viết lại truy vấn bằng JOIN và so sánh.

### Bài 5: SQL SECURITY

Tạo một function đọc bảng với SQL SECURITY DEFINER và một function với SQL SECURITY INVOKER. Dùng user thử nghiệm chỉ có EXECUTE để kiểm tra sự khác biệt. Không dùng tài khoản root làm definer.

### Bài 6: Đặc tính deterministic

Tạo một function chỉ tính từ tham số và một function phụ thuộc dữ liệu bảng. Khai báo đặc tính phù hợp, giải thích vì sao không thể chỉ nhìn chữ ký tham số để kết luận deterministic.

### Bài 7: Tác dụng phụ

Tạo function ghi audit trong môi trường lab. Gọi nó từ SELECT trên nhiều hàng và quan sát số dòng audit. Thử thay đổi predicate hoặc kế hoạch truy vấn; ghi nhận vì sao không nên dùng số lần gọi làm cam kết nghiệp vụ. Sau đó chuyển audit sang DML hoặc trigger phù hợp.

### Bài 8: Giới hạn function

Thử đưa PREPARE, CALL procedure, COMMIT và SELECT trần vào function. Ghi lại lỗi server trả về và đối chiếu với giới hạn stored function.

### Bài 9: Replication characteristics

Kiểm tra log_bin, binlog_format và log_bin_trust_function_creators trên môi trường thử nghiệm. Tạo function có characteristic khác nhau và quan sát điều kiện quyền/khai báo của server phiên bản đang dùng.

### Bài 10: So sánh hiệu năng

Dùng EXPLAIN ANALYZE để so sánh:
- Function tính toán thuần trong SELECT.
- Biểu thức SQL trực tiếp.
- Function đọc bảng được gọi theo từng hàng.
- JOIN trực tiếp tới bảng được function đọc.

Ghi lại số hàng, thời gian và kế hoạch.

## 20. Checklist trước khi đưa function vào ứng dụng

- [ ] Function thực sự cần trả một scalar value.
- [ ] Mọi đường thực thi đều trả giá trị đúng kiểu RETURNS.
- [ ] Tham số là IN và có kiểu dữ liệu phù hợp.
- [ ] NULL, precision, scale và làm tròn đã được định nghĩa.
- [ ] SELECT ... INTO bảo đảm tối đa một hàng.
- [ ] Không phát result set trực tiếp.
- [ ] Không dùng PREPARE/EXECUTE hoặc CALL procedure.
- [ ] Không dùng START TRANSACTION, COMMIT, ROLLBACK hoặc DDL gây implicit commit.
- [ ] Không sửa bảng mà statement gọi function đang sử dụng.
- [ ] Không dựa vào thứ tự hoặc số lần đánh giá biểu thức để thực hiện side effect.
- [ ] DETERMINISTIC/NOT DETERMINISTIC phản ánh đúng logic.
- [ ] SQL data access characteristic khai báo đúng nội dung.
- [ ] SQL SECURITY DEFINER/INVOKER được chọn theo nguyên tắc quyền tối thiểu.
- [ ] Definer còn tồn tại và có đúng quyền cần thiết.
- [ ] Quyền CREATE ROUTINE và EXECUTE được cấp có kiểm soát.
- [ ] Binary logging và replication đã được xem xét.
- [ ] Đã so sánh với JOIN hoặc biểu thức trực tiếp khi phù hợp.
- [ ] Đã đo bằng EXPLAIN/EXPLAIN ANALYZE trên dữ liệu đại diện.
- [ ] Đã kiểm thử NULL, không có hàng, nhiều hàng và lỗi nghiệp vụ.

## 21. Kết luận

Stored function là routine trả về một giá trị đơn và có thể được gọi trong biểu thức SQL. Nó phù hợp để đóng gói phép tính hoặc logic trả về scalar có đầu vào/đầu ra rõ ràng. Khi function đọc bảng, hãy cân nhắc JOIN để tránh lookup lặp theo từng hàng. Khi function có tác dụng phụ, không đặt nó trong SELECT/WHERE như một cơ chế điều khiển quy trình vì optimizer không cam kết thứ tự hay số lần đánh giá biểu thức.

Hãy khai báo đúng DETERMINISTIC và SQL data access characteristic, chọn SQL SECURITY theo nguyên tắc quyền tối thiểu, đồng thời tuân thủ giới hạn về result set, dynamic SQL, transaction, procedure call và sửa bảng đang được statement gọi function sử dụng. Với logic nhiều bước hoặc ghi dữ liệu có chủ đích, procedure, DML tường minh, trigger phù hợp hoặc tầng ứng dụng thường giúp kiểm soát transaction và retry rõ ràng hơn.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – CREATE FUNCTION Statement](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL 8.4 Reference Manual – Stored Programs Restrictions](https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html)
- [MySQL 8.4 Reference Manual – Stored Function Syntax](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html)
- [MySQL 8.4 Reference Manual – Stored Program Binary Logging](https://dev.mysql.com/doc/refman/8.4/en/stored-programs-logging.html)
- [MySQL 8.4 Reference Manual – Stored Object Access Control](https://dev.mysql.com/doc/refman/8.4/en/stored-objects-security.html)
- [MySQL 8.4 Reference Manual – Stored Routine Privileges](https://dev.mysql.com/doc/refman/8.4/en/stored-routines-privileges.html)
- [MySQL 8.4 Reference Manual – SHOW CREATE FUNCTION](https://dev.mysql.com/doc/refman/8.4/en/show-create-function.html)
- [MySQL 8.4 Reference Manual – INFORMATION_SCHEMA ROUTINES](https://dev.mysql.com/doc/refman/8.4/en/information-schema-routines-table.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)


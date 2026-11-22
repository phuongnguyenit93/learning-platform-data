# Biến cục bộ, biến người dùng và tham số IN/OUT/INOUT

## Mục tiêu bài học

Sau bài này, bạn có thể:

- Phân biệt biến cục bộ được khai báo bằng DECLARE, biến người dùng có tiền tố @ và tham số của stored routine.
- Khai báo biến trong khối BEGIN ... END, chọn kiểu dữ liệu và giá trị mặc định phù hợp.
- Hiểu phạm vi sống của biến cục bộ, cách khối lồng nhau nhìn thấy biến và rủi ro trùng tên với cột.
- Gán giá trị bằng SET và SELECT ... INTO; xử lý trường hợp truy vấn không trả hàng hoặc trả nhiều hàng.
- Sử dụng biến người dùng để trao đổi giá trị giữa các câu lệnh trong cùng một session.
- Hiểu vì sao không nên vừa đọc vừa gán cùng một biến người dùng trong một câu SQL.
- Khai báo tham số IN, OUT và INOUT của stored procedure, gọi procedure và nhận kết quả.
- Nhận biết stored function chỉ nhận tham số IN và trả kết quả bằng RETURN.
- Chọn đúng loại biến cho dữ liệu tạm trong routine, dữ liệu trao đổi với client và trạng thái theo session.

Stored program của MySQL có thể là stored procedure hoặc stored function. Routine thường nhận dữ liệu từ caller, thực hiện một chuỗi thao tác và trả kết quả. Để làm việc đó, MySQL cung cấp ba cơ chế có liên quan nhưng khác nhau: biến cục bộ, biến người dùng và tham số routine.

Biến cục bộ tồn tại trong phạm vi khối BEGIN ... END nơi nó được khai báo. Biến người dùng có tên bắt đầu bằng @ và tồn tại trong session kết nối. Tham số là dữ liệu đi qua ranh giới giữa caller và routine; stored procedure hỗ trợ IN, OUT và INOUT, còn stored function chỉ dùng tham số IN.

Nắm rõ phạm vi và hướng truyền dữ liệu giúp routine dễ đọc, tránh rò rỉ trạng thái giữa các request và tránh nhầm lẫn giữa dữ liệu đầu vào, dữ liệu đầu ra với biến tạm nội bộ.

## 1. Phân biệt ba cơ chế

| Cơ chế | Cách viết | Phạm vi | Mục đích chính |
|---|---|---|---|
| Biến cục bộ | DECLARE v_total DECIMAL(14,2) | Khối BEGIN ... END chứa khai báo và các khối con | Lưu giá trị tạm trong routine |
| Biến người dùng | @session_total | Một connection/session | Trao đổi dữ liệu giữa các câu lệnh trong cùng session hoặc giữa caller và procedure |
| Tham số routine | IN p_id INT, OUT p_count INT, INOUT p_rate DECIMAL(5,2) | Trong routine; dữ liệu được truyền qua lời gọi | Nhận đầu vào và trả đầu ra có cấu trúc |

Ví dụ ngắn:

~~~sql
-- Biến người dùng: không cần DECLARE
SET @request_id = 501;

DELIMITER $$

CREATE PROCEDURE sp_example(IN p_request_id BIGINT)
BEGIN
    -- Biến cục bộ
    DECLARE v_message VARCHAR(100) DEFAULT 'Đang xử lý';

    SET v_message = CONCAT(v_message, ': ', p_request_id);

    SELECT v_message AS message;
END$$

DELIMITER ;

CALL sp_example(@request_id);
~~~

Trong ví dụ:

- @request_id thuộc session đang chạy lệnh CALL.
- p_request_id là tham số IN nhận giá trị từ caller.
- v_message là biến cục bộ chỉ tồn tại trong lần thực thi procedure.

Đừng xem ba loại này là các cách viết khác nhau của cùng một biến. Chúng có vòng đời, cách khởi tạo và cách truyền dữ liệu khác nhau.

## 2. Khai báo biến cục bộ bằng DECLARE

Biến cục bộ chỉ được khai báo trong một khối chương trình có cấu trúc BEGIN ... END, thường là thân của procedure hoặc function.

Cú pháp:

~~~sql
DECLARE var_name [, var_name] ... type [DEFAULT value];
~~~

Ví dụ:

~~~sql
DECLARE v_order_count INT UNSIGNED DEFAULT 0;
DECLARE v_total_amount DECIMAL(14, 2) DEFAULT 0.00;
DECLARE v_customer_name VARCHAR(120);
DECLARE v_is_valid BOOLEAN DEFAULT FALSE;
~~~

Có thể khai báo nhiều biến cùng kiểu trong một câu lệnh:

~~~sql
DECLARE v_min_id, v_max_id BIGINT UNSIGNED DEFAULT 0;
~~~

Kiểu dữ liệu của biến cục bộ dùng kiểu dữ liệu MySQL hợp lệ, tương tự kiểu của tham số routine. Chọn kiểu gần với dữ liệu thật để tránh ép kiểu và tràn số ngoài dự kiến.

### 2.1. DECLARE phải nằm ở đầu khối

Khai báo biến phải xuất hiện ở đầu khối BEGIN ... END, trước các câu lệnh thực thi. Trong một stored program, biến và condition được khai báo trước cursor hoặc handler.

Ví dụ hợp lệ:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_local_variable_demo()
BEGIN
    DECLARE v_count INT UNSIGNED DEFAULT 0;
    DECLARE v_note VARCHAR(100) DEFAULT 'Bắt đầu';

    SET v_count = v_count + 1;

    SELECT v_count AS current_count, v_note AS note;
END$$

DELIMITER ;
~~~

Ví dụ không hợp lệ vì DECLARE nằm sau câu lệnh SET:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_invalid_declare()
BEGIN
    SET @started = 1;
    DECLARE v_count INT DEFAULT 0;
END$$

DELIMITER ;
~~~

Nếu cần một phạm vi con riêng, có thể tạo khối BEGIN ... END lồng nhau và đặt khai báo ở đầu khối con đó.

### 2.2. Giá trị mặc định và NULL

Nếu có DEFAULT, biến nhận giá trị được chỉ định. Giá trị mặc định có thể là một biểu thức.

Nếu không khai báo DEFAULT, giá trị ban đầu của biến cục bộ là NULL.

~~~sql
DECLARE v_attempts INT UNSIGNED DEFAULT 0;
DECLARE v_started_at DATETIME DEFAULT CURRENT_TIMESTAMP;
DECLARE v_last_message VARCHAR(200);
~~~

Trong ví dụ trên, v_last_message ban đầu là NULL. Khi dùng biến trong phép tính, cần cân nhắc cách xử lý NULL vì hầu hết phép toán số học với NULL tiếp tục cho kết quả NULL.

Ví dụ khởi tạo rõ ràng trước khi cộng:

~~~sql
SET v_attempts = v_attempts + 1;
~~~

Nếu v_attempts có giá trị ban đầu NULL, phép cộng trên cũng cho NULL. Vì vậy, hãy đặt DEFAULT phù hợp hoặc dùng COALESCE khi nhận dữ liệu có thể NULL.

### 2.3. Kiểu dữ liệu và kiểm tra giá trị

Biến cục bộ được kiểm tra kiểu dữ liệu và overflow tương tự tham số stored routine. Hãy chọn kiểu đủ miền giá trị cho nghiệp vụ.

~~~sql
DECLARE v_quantity INT UNSIGNED DEFAULT 0;
DECLARE v_unit_price DECIMAL(12, 2) DEFAULT 0.00;
DECLARE v_line_total DECIMAL(16, 2) DEFAULT 0.00;

SET v_line_total = v_quantity * v_unit_price;
~~~

Dùng DECIMAL cho tiền và giá trị cần độ chính xác thập phân. Tránh dùng FLOAT hoặc DOUBLE cho phép tính tiền nếu nghiệp vụ yêu cầu kết quả thập phân chính xác.

## 3. Phạm vi sống của biến cục bộ

Biến cục bộ chỉ có hiệu lực trong khối BEGIN ... END nơi khai báo. Khối con có thể sử dụng biến của khối cha, trừ khi khối con khai báo một biến cùng tên.

Ví dụ:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_scope_demo()
BEGIN
    DECLARE v_message VARCHAR(40) DEFAULT 'Biến ở khối ngoài';

    BEGIN
        DECLARE v_inner_count INT DEFAULT 10;

        SELECT v_message AS outer_message,
               v_inner_count AS inner_count;
    END;

    SELECT v_message AS outer_message_after_block;
END$$

DELIMITER ;
~~~

v_message được nhìn thấy từ khối con vì nó được khai báo ở khối cha. v_inner_count chỉ tồn tại trong khối con; sau END của khối con, không thể tham chiếu biến đó.

### 3.1. Tránh khai báo trùng tên với cột

Không nên đặt tên biến cục bộ giống tên cột trong bảng. Khi tên bị trùng trong một câu SQL, MySQL có thể phân giải tên thành biến cục bộ thay vì cột, khiến điều kiện lọc không làm điều bạn mong muốn.

Ví dụ dễ gây nhầm:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_bad_name_resolution()
BEGIN
    DECLARE customer_id BIGINT UNSIGNED DEFAULT 101;

    SELECT customer_id
    FROM customer
    WHERE customer_id = customer_id;
END$$

DELIMITER ;
~~~

Trong stored program, cả hai vế customer_id có thể được hiểu là biến cục bộ. Điều kiện khi đó không còn so sánh cột với biến như ý định ban đầu.

Dùng quy ước tên rõ ràng:

- p_ cho tham số, ví dụ p_customer_id.
- v_ cho biến cục bộ, ví dụ v_customer_count.
- Alias cho cột, ví dụ c.customer_id.

Cách viết rõ ràng:

~~~sql
DECLARE v_customer_id BIGINT UNSIGNED DEFAULT 101;

SELECT c.customer_id
FROM customer AS c
WHERE c.customer_id = v_customer_id;
~~~

Quy ước đặt tên không thay thế việc qualify cột bằng alias, nhưng giúp giảm nhầm lẫn khi routine dài và có nhiều bảng.

## 4. Gán giá trị cho biến cục bộ

Hai cách thường dùng là SET và SELECT ... INTO.

### 4.1. Dùng SET

SET phù hợp khi giá trị được tính từ hằng số, tham số, biến khác hoặc biểu thức.

~~~sql
DECLARE v_subtotal DECIMAL(14, 2) DEFAULT 0.00;
DECLARE v_tax_rate DECIMAL(5, 2) DEFAULT 8.00;
DECLARE v_tax_amount DECIMAL(14, 2) DEFAULT 0.00;

SET v_subtotal = 1250000.00;
SET v_tax_amount = ROUND(v_subtotal * v_tax_rate / 100, 2);
~~~

Có thể gán nhiều biến trong một câu SET:

~~~sql
SET v_subtotal = 1250000.00,
    v_tax_rate = 8.00;
~~~

### 4.2. Dùng SELECT ... INTO

SELECT ... INTO lấy giá trị từ truy vấn và gán vào biến cục bộ hoặc tham số routine.

~~~sql
DECLARE v_order_total DECIMAL(14, 2) DEFAULT 0.00;

SELECT COALESCE(SUM(o.total_amount), 0.00)
INTO v_order_total
FROM sales_order AS o
WHERE o.customer_id = p_customer_id;
~~~

Số biến ở INTO phải bằng số biểu thức trong SELECT list.

Ví dụ lấy nhiều giá trị:

~~~sql
DECLARE v_order_count INT UNSIGNED DEFAULT 0;
DECLARE v_total_amount DECIMAL(14, 2) DEFAULT 0.00;

SELECT
    COUNT(*),
    COALESCE(SUM(o.total_amount), 0.00)
INTO
    v_order_count,
    v_total_amount
FROM sales_order AS o
WHERE o.customer_id = p_customer_id;
~~~

Đặt INTO ở cuối câu SELECT là cách viết được ưu tiên:

~~~sql
SELECT o.order_status
FROM sales_order AS o
WHERE o.order_id = p_order_id
INTO v_order_status;
~~~

### 4.3. SELECT ... INTO phải xử lý số hàng

SELECT ... INTO dạng biến cần trả về đúng một hàng.

- Nếu không có hàng, MySQL phát warning 1329 (No data) và các biến giữ nguyên giá trị trước câu lệnh.
- Nếu có nhiều hơn một hàng, MySQL phát lỗi 1172 (Result consisted of more than one row).
- Nếu có khả năng trả nhiều hàng nhưng chỉ cần một hàng, dùng ORDER BY có thứ tự xác định và LIMIT 1.

Ví dụ lấy trạng thái của một đơn theo khóa chính:

~~~sql
SELECT o.order_status
INTO v_order_status
FROM sales_order AS o
WHERE o.order_id = p_order_id;
~~~

Nếu điều kiện không bảo đảm duy nhất, hãy giới hạn kết quả:

~~~sql
SELECT o.order_status
INTO v_order_status
FROM sales_order AS o
WHERE o.customer_id = p_customer_id
ORDER BY o.ordered_at DESC, o.order_id DESC
LIMIT 1;
~~~

Không dùng LIMIT 1 một cách tùy tiện nếu nghiệp vụ cần phát hiện dữ liệu trùng. Trong trường hợp đó, hãy giữ truy vấn để MySQL báo lỗi nhiều hàng hoặc chủ động kiểm tra cardinality.

### 4.4. Dùng aggregate để luôn có một hàng

Các hàm tổng hợp như COUNT(*) trả một hàng kể cả khi không có bản ghi thỏa điều kiện. Đây là cách hữu ích để gán kết quả đếm mà không gặp warning No data.

~~~sql
SELECT COUNT(*)
INTO v_order_count
FROM sales_order AS o
WHERE o.customer_id = p_customer_id;
~~~

Với SUM, AVG, MIN, MAX, kết quả có thể là NULL nếu không có hàng phù hợp. Dùng COALESCE khi muốn thay NULL bằng giá trị nghiệp vụ, ví dụ 0.

## 5. Biến người dùng có tiền tố @

Biến người dùng (user-defined variable) được viết với ký tự @ ở đầu tên:

~~~sql
SET @current_customer_id = 101;
SET @report_limit = 20;

SELECT
    @current_customer_id AS customer_id,
    @report_limit AS report_limit;
~~~

Không cần khai báo biến người dùng bằng DECLARE. Nếu đọc một biến chưa được khởi tạo, giá trị của nó là NULL.

Biến người dùng có các đặc điểm:

- Phạm vi là session/connection hiện tại.
- Session khác không thể dùng biến của session này.
- Biến được giải phóng khi client kết thúc session.
- Tên không phân biệt chữ hoa/chữ thường.
- Dùng để lưu dữ liệu, không dùng trực tiếp làm tên bảng, tên cột hoặc định danh SQL.

### 5.1. Biến người dùng tồn tại qua nhiều câu lệnh

~~~sql
SET @customer_id = 101;

SELECT
    order_id,
    total_amount
FROM sales_order
WHERE customer_id = @customer_id;

SELECT @customer_id AS customer_used;
~~~

Hai câu SELECT có thể đọc cùng biến vì chúng chạy trong cùng một session.

Nếu connection pool tái sử dụng connection cho request khác, biến người dùng vẫn tồn tại trên connection đó cho đến khi được gán lại hoặc session kết thúc. Vì vậy, không nên dựa vào giá trị @variable cũ của một request. Hãy khởi tạo rõ ràng hoặc reset biến cần dùng khi bắt đầu tác vụ.

### 5.2. Gán biến người dùng

Ưu tiên dùng SET:

~~~sql
SET @tax_rate = 8.00;
SET @subtotal = 1250000.00;
SET @tax_amount = ROUND(@subtotal * @tax_rate / 100, 2);

SELECT @tax_amount AS tax_amount;
~~~

Có thể dùng = hoặc := trong SET. Trong các câu lệnh khác SET, cú pháp gán biến kiểu cũ bằng := vẫn tồn tại để tương thích nhưng được khuyến nghị tránh trong SQL mới.

### 5.3. SELECT ... INTO biến người dùng

SELECT ... INTO có thể gán kết quả vào user variable:

~~~sql
SELECT COUNT(*)
INTO @order_count
FROM sales_order
WHERE customer_id = 101;

SELECT @order_count AS order_count;
~~~

Số hàng và cách xử lý không có hàng/nhiều hàng giống nguyên tắc SELECT ... INTO biến cục bộ. Với COUNT(*), truy vấn luôn trả một hàng.

### 5.4. Không vừa đọc vừa gán cùng biến trong một câu

Thứ tự đánh giá biểu thức có tham chiếu và gán cùng user variable là không xác định.

Không nên viết:

~~~sql
SELECT @counter, @counter := @counter + 1;
~~~

Không có bảo đảm biểu thức đọc @counter được đánh giá trước hay sau biểu thức gán.

Hãy tách thành các câu lệnh rõ ràng:

~~~sql
SET @counter = COALESCE(@counter, 0);
SET @counter = @counter + 1;
SELECT @counter AS counter_value;
~~~

Cách này dễ đọc, dễ kiểm thử và không phụ thuộc thứ tự đánh giá biểu thức.

### 5.5. Kiểu dữ liệu của user variable

User variable lưu giá trị scalar như số nguyên, DECIMAL, số thực, chuỗi nhị phân/không nhị phân hoặc NULL. Một số kiểu khác được chuyển đổi khi gán: giá trị temporal và spatial thành chuỗi nhị phân; JSON thành chuỗi với charset utf8mb4. Việc gán DECIMAL hoặc số thực không bảo toàn đầy đủ precision và scale ban đầu.

Vì vậy, dùng user variable thuận tiện cho trao đổi dữ liệu theo session và tham số CALL, nhưng tránh dùng nó làm nơi lưu trữ trung gian cho phép tính tiền cần độ chính xác cao. Trong routine, ưu tiên biến cục bộ và tham số có kiểu DECIMAL được khai báo rõ.

Kiểu của user variable được dùng trong prepared statement xác định khi statement được PREPARE và giữ nguyên ở các lần EXECUTE sau. Tương tự, kiểu của user variable dùng trong statement thuộc stored procedure được xác định ở lần gọi đầu tiên và giữ kiểu đó cho các lần gọi tiếp theo. Nếu một biến cần chứa nhiều kiểu dữ liệu khác nhau, hãy thiết kế lại cách truyền dữ liệu hoặc CAST rõ ràng.

### 5.6. User variable là giá trị, không phải tên đối tượng

User variable không thể thay trực tiếp cho tên database, bảng, cột hoặc từ khóa.

Ví dụ sau không hợp lệ:

~~~sql
SET @table_name = 'sales_order';
SELECT * FROM @table_name;
~~~

Nếu cần dynamic SQL trong stored procedure, phải tạo chuỗi câu lệnh rồi PREPARE/EXECUTE theo quy tắc riêng. Biến cục bộ và tham số routine không thể được tham chiếu trực tiếp bên trong prepared statement tạo trong routine; prepared statement có phạm vi session, có thể tồn tại sau khi routine kết thúc. Trường hợp dynamic SQL thường dùng user variable để giữ chuỗi câu lệnh hoặc giá trị bind phù hợp.

Không dùng dynamic SQL chỉ để thay một giá trị dữ liệu; parameter binding hoặc điều kiện SQL thông thường an toàn và đơn giản hơn.

## 6. Tham số stored procedure

Tham số là giao diện dữ liệu giữa caller và stored procedure. MySQL hỗ trợ ba mode:

- IN: truyền dữ liệu vào procedure.
- OUT: truyền dữ liệu từ procedure về caller.
- INOUT: truyền dữ liệu vào, cho phép procedure sửa và trả lại.

Cú pháp:

~~~sql
CREATE PROCEDURE procedure_name (
    [IN | OUT | INOUT] parameter_name data_type,
    ...
)
routine_body;
~~~

Nếu không ghi mode, tham số mặc định là IN.

Tên tham số không phân biệt chữ hoa/chữ thường. Không khai báo một biến cục bộ trùng tên tham số trong cùng phạm vi.

### 6.1. IN: tham số đầu vào

IN truyền giá trị từ caller vào procedure. Procedure có thể gán lại tham số trong thân routine, nhưng thay đổi đó không được phản ánh về biến của caller khi procedure kết thúc.

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_show_customer(
    IN p_customer_id BIGINT UNSIGNED
)
BEGIN
    DECLARE v_message VARCHAR(100) DEFAULT '';

    SET v_message = CONCAT('Customer ID = ', p_customer_id);

    SELECT
        p_customer_id AS input_customer_id,
        v_message AS message;
END$$

DELIMITER ;
~~~

Gọi procedure:

~~~sql
CALL sp_show_customer(101);
~~~

Có thể truyền literal, biểu thức hoặc biến người dùng làm IN argument:

~~~sql
SET @customer_id = 102;
CALL sp_show_customer(@customer_id);
~~~

IN phù hợp với mã khách hàng, khoảng ngày, trạng thái lọc, số lượng cần xử lý hoặc các tham số điều khiển nghiệp vụ.

### 6.2. OUT: tham số đầu ra

OUT dùng để trả giá trị từ procedure về caller.

Khi procedure bắt đầu, tham số OUT có giá trị NULL bên trong routine, bất kể biến caller đang có giá trị gì. Procedure cần gán giá trị trước khi trả về nếu muốn caller nhận được kết quả khác NULL.

Ví dụ:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_count_orders(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count INT UNSIGNED
)
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM sales_order
    WHERE customer_id = p_customer_id;
END$$

DELIMITER ;
~~~

Gọi procedure và đọc kết quả:

~~~sql
CALL sp_count_orders(101, @order_count);

SELECT @order_count AS order_count;
~~~

Ở mức SQL client, hãy truyền user variable cho tham số OUT để nhận kết quả. Nếu gọi từ một stored procedure hoặc function khác, có thể truyền tham số routine hoặc biến cục bộ thích hợp.

Nếu procedure không gán OUT parameter, giá trị trả về là NULL. Hãy thiết kế mọi nhánh xử lý để OUT parameter luôn được gán khi nghiệp vụ yêu cầu kết quả cụ thể.

### 6.3. INOUT: vừa nhận vừa trả giá trị

INOUT kết hợp hai chiều:

1. Caller khởi tạo giá trị trước khi gọi.
2. Procedure nhận giá trị đó.
3. Procedure có thể sửa giá trị.
4. Giá trị mới được trả về caller sau khi procedure kết thúc.

Ví dụ tăng một bộ đếm:

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_increment_counter(
    INOUT p_counter INT
)
BEGIN
    SET p_counter = COALESCE(p_counter, 0) + 1;
END$$

DELIMITER ;
~~~

Gọi:

~~~sql
SET @counter = 10;

CALL sp_increment_counter(@counter);

SELECT @counter AS counter_after_call;
~~~

Kết quả của @counter sau CALL là 11.

Khác với OUT, INOUT cần caller cung cấp giá trị ban đầu có ý nghĩa. Nếu caller truyền NULL, routine phải tự quyết định cách xử lý NULL.

### 6.4. So sánh IN, OUT và INOUT

| Mode | Giá trị khi vào routine | Có thể sửa trong routine | Caller nhận thay đổi |
|---|---|---|---|
| IN | Giá trị caller truyền vào | Có thể sửa bản cục bộ | Không |
| OUT | Ban đầu là NULL trong routine | Có | Có |
| INOUT | Giá trị caller truyền vào | Có | Có |

Chọn mode theo hướng dữ liệu:

- Chỉ nhận dữ liệu: IN.
- Chỉ trả kết quả: OUT.
- Nhận trạng thái ban đầu rồi trả trạng thái đã cập nhật: INOUT.

Không dùng INOUT chỉ để tránh khai báo một OUT parameter. Nếu một routine trả nhiều kết quả độc lập, nhiều OUT parameter có thể làm giao diện rõ ràng hơn.

## 7. Ví dụ hoàn chỉnh: tổng hợp đơn hàng và áp dụng mức giảm giá

Bài lab này dùng một bảng đơn giản để minh họa đồng thời:

- Tham số IN nhận mã khách hàng.
- Tham số OUT trả số đơn và tổng tiền sau giảm.
- Tham số INOUT nhận mức giảm ban đầu và trả mức giảm sau khi áp trần.
- Biến cục bộ lưu tổng tiền trước giảm.

### 7.1. Tạo dữ liệu mẫu

~~~sql
CREATE TABLE routine_order_demo (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(14, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_routine_customer (customer_id)
) ENGINE = InnoDB;

INSERT INTO routine_order_demo (
    order_id, customer_id, total_amount
)
VALUES
    (9001, 101, 1250000.00),
    (9002, 101, 2400000.00),
    (9003, 102,  890000.00),
    (9004, 101,  450000.00),
    (9005, 103, 3400000.00);
~~~

### 7.2. Tạo procedure

Mức giảm được giới hạn từ 0% đến 30%. Tổng tiền gốc được tính bằng SUM, sau đó áp dụng mức giảm đã giới hạn.

~~~sql
DELIMITER $$

CREATE PROCEDURE sp_customer_order_summary(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count INT UNSIGNED,
    OUT p_total_after_discount DECIMAL(14, 2),
    INOUT p_discount_percent DECIMAL(5, 2)
)
BEGIN
    DECLARE v_subtotal DECIMAL(14, 2) DEFAULT 0.00;

    SELECT
        COUNT(*),
        COALESCE(SUM(o.total_amount), 0.00)
    INTO
        p_order_count,
        v_subtotal
    FROM routine_order_demo AS o
    WHERE o.customer_id = p_customer_id;

    SET p_discount_percent =
        LEAST(
            GREATEST(COALESCE(p_discount_percent, 0.00), 0.00),
            30.00
        );

    SET p_total_after_discount =
        ROUND(v_subtotal * (1 - p_discount_percent / 100), 2);
END$$

DELIMITER ;
~~~

Giải thích:

- p_customer_id là IN, chỉ cung cấp dữ liệu đầu vào.
- p_order_count là OUT, nhận số đơn được đếm.
- p_total_after_discount là OUT, nhận tổng tiền sau giảm.
- p_discount_percent là INOUT, nhận mức giảm ban đầu và trả mức giảm đã giới hạn.
- v_subtotal là biến cục bộ, chỉ giữ tổng tiền gốc trong lần gọi procedure.

COUNT(*) và SUM() là các aggregate nên SELECT ... INTO trả một hàng kể cả khi khách hàng chưa có đơn. COUNT(*) trả 0, còn SUM() được COALESCE thành 0.00.

### 7.3. Gọi procedure và đọc kết quả

~~~sql
SET @order_count = -1;
SET @total_after_discount = -1.00;
SET @discount_percent = 50.00;

CALL sp_customer_order_summary(
    101,
    @order_count,
    @total_after_discount,
    @discount_percent
);

SELECT
    @order_count AS order_count,
    @total_after_discount AS total_after_discount,
    @discount_percent AS applied_discount_percent;
~~~

Với dữ liệu mẫu:

- Khách hàng 101 có 3 đơn.
- Tổng tiền trước giảm là 4,100,000.00.
- Mức giảm ban đầu 50% được giới hạn còn 30%.
- Tổng tiền sau giảm là 2,870,000.00.

Biến @order_count và @total_after_discount là OUT nên giá trị cũ của chúng không được dùng làm đầu vào cho routine. @discount_percent là INOUT nên giá trị 50.00 được truyền vào rồi được thay bằng 30.00.

### 7.4. Thử khách hàng không có đơn

~~~sql
SET @order_count = -1;
SET @total_after_discount = -1.00;
SET @discount_percent = 10.00;

CALL sp_customer_order_summary(
    999,
    @order_count,
    @total_after_discount,
    @discount_percent
);

SELECT
    @order_count,
    @total_after_discount,
    @discount_percent;
~~~

Kết quả mong đợi: số đơn bằng 0, tổng tiền sau giảm bằng 0.00, mức giảm vẫn là 10.00. Ví dụ này cho thấy aggregate giúp procedure xử lý trường hợp không có bản ghi mà không cần SELECT ... INTO trả về 0 hàng.

## 8. Tham số của stored function

Stored function nhận tham số đầu vào và trả về một giá trị bằng RETURN. Trong MySQL, tham số của function luôn được xem là IN; không khai báo OUT hoặc INOUT cho function.

Cú pháp:

~~~sql
CREATE FUNCTION function_name (
    parameter_name data_type,
    ...
)
RETURNS return_type
routine_body;
~~~

Ví dụ hàm tính giá sau giảm:

~~~sql
DELIMITER $$

CREATE FUNCTION fn_price_after_discount(
    p_price DECIMAL(14, 2),
    p_discount_percent DECIMAL(5, 2)
)
RETURNS DECIMAL(14, 2)
DETERMINISTIC
BEGIN
    DECLARE v_result DECIMAL(14, 2) DEFAULT 0.00;

    SET v_result = ROUND(
        p_price * (1 - p_discount_percent / 100),
        2
    );

    RETURN v_result;
END$$

DELIMITER ;
~~~

Gọi function trong biểu thức SQL:

~~~sql
SELECT fn_price_after_discount(1000000.00, 15.00)
    AS discounted_price;
~~~

Function không trả kết quả qua OUT parameter. Giá trị trả về phải phù hợp với kiểu dữ liệu khai báo trong RETURNS.

### 8.1. Khi nào dùng procedure, khi nào dùng function?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Nhận dữ liệu và trả nhiều giá trị | Procedure với OUT/INOUT |
| Thực hiện một chuỗi thao tác nghiệp vụ | Procedure |
| Tính một giá trị dùng trong biểu thức SQL | Function |
| Chỉ cần đầu vào và một giá trị trả về | Function thường phù hợp |
| Cần thay đổi trạng thái đầu vào và trả lại trạng thái | Procedure với INOUT |

Không nên chuyển một procedure thành function chỉ vì muốn gọi ngắn hơn. Stored function có các giới hạn thực thi riêng và chỉ trả một giá trị theo kiểu RETURNS.

## 9. Biến cục bộ và tham số trong prepared statement

Biến cục bộ và tham số routine chỉ tồn tại trong thời gian routine thực thi. Prepared statement được tạo trong stored program có phạm vi session và có thể còn tồn tại sau khi routine kết thúc.

Vì vậy, prepared statement tạo bên trong routine không thể tham chiếu trực tiếp biến cục bộ hoặc tham số routine. Khi cần dynamic SQL trong procedure, cần truyền giá trị qua user variable hoặc một cơ chế bind phù hợp với prepared statement.

Ví dụ ý tưởng:

~~~sql
SET @sql_text = 'SELECT order_id FROM routine_order_demo WHERE customer_id = ?';
PREPARE stmt FROM @sql_text;

SET @customer_id = 101;
EXECUTE stmt USING @customer_id;

DEALLOCATE PREPARE stmt;
~~~

Ví dụ này minh họa việc dùng user variable cho câu lệnh prepared. Trong routine thực tế, phải quản lý tên prepared statement, dữ liệu đầu vào và thao tác DEALLOCATE rõ ràng. Stored function và trigger có giới hạn riêng đối với SQL prepared statement.

Nếu không cần dynamic SQL, hãy dùng tham số routine và câu SQL tĩnh. Cách đó dễ kiểm tra và ít rủi ro hơn.

## 10. Những lỗi thường gặp

| Lỗi hoặc hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| Dùng DECLARE ở bất kỳ đâu trong procedure | DECLARE phải ở đầu khối BEGIN ... END | Đặt toàn bộ khai báo trước câu lệnh thực thi |
| Biến cục bộ không có DEFAULT tự bằng 0 | Giá trị ban đầu là NULL | Gán DEFAULT hoặc khởi tạo bằng SET |
| Biến cục bộ tồn tại hết session | Biến chỉ sống trong khối khai báo | Dùng user variable nếu cần chia sẻ giữa các câu lệnh cùng session |
| User variable là biến toàn server | User variable thuộc session | Không dùng để chia sẻ trạng thái giữa các connection |
| IN sửa được giá trị caller | Thay đổi IN chỉ ở trong routine | Dùng OUT hoặc INOUT nếu cần trả thay đổi |
| OUT nhận giá trị ban đầu từ caller | OUT bắt đầu là NULL trong routine | Gán giá trị cho OUT trước khi kết thúc |
| INOUT không cần khởi tạo | INOUT nhận giá trị caller truyền vào | Gán user variable trước CALL |
| Stored function có thể khai báo OUT | Function chỉ có tham số IN | Dùng procedure nếu cần OUT/INOUT |
| SELECT ... INTO có thể trả nhiều hàng | Nhiều hơn một hàng gây lỗi 1172 | Dùng aggregate hoặc điều kiện duy nhất; nếu phù hợp dùng ORDER BY và LIMIT 1 |
| SELECT ... INTO không có hàng sẽ tự gán NULL | Biến giữ nguyên giá trị trước câu lệnh và phát warning 1329 | Khởi tạo rõ và xử lý trường hợp không có hàng |
| Có thể dùng cùng tên biến và cột | MySQL có thể phân giải thành biến cục bộ | Dùng prefix p_/v_ và qualify cột bằng alias |
| Có thể vừa đọc vừa gán @var trong một SELECT | Thứ tự đánh giá không xác định | Tách thành các câu SET |
| User variable có thể làm tên bảng | User variable dùng làm giá trị, không phải identifier trực tiếp | Dùng dynamic SQL có kiểm soát khi thật sự cần |
| Prepared statement dùng trực tiếp local variable | Local variable và parameter không nằm trong phạm vi session của prepared statement | Truyền dữ liệu qua user variable hoặc bind phù hợp |

## 11. Quy trình thiết kế routine có biến và tham số rõ ràng

Khi thiết kế một procedure hoặc function mới:

1. Xác định dữ liệu caller phải cung cấp; khai báo chúng thành tham số IN.
2. Xác định kết quả caller cần nhận; dùng OUT cho các giá trị chỉ trả về.
3. Nếu caller truyền trạng thái ban đầu và cần nhận trạng thái đã cập nhật, dùng INOUT.
4. Khai báo biến tạm nội bộ bằng DECLARE với prefix v_.
5. Chọn kiểu dữ liệu và DEFAULT phù hợp; tránh để NULL ngoài ý muốn.
6. Đặt DECLARE ở đầu khối BEGIN ... END.
7. Dùng SET cho biểu thức và SELECT ... INTO cho kết quả truy vấn.
8. Bảo đảm SELECT ... INTO có cardinality đúng; xử lý trường hợp không có hàng.
9. Không đặt tên biến trùng tên cột; qualify cột bằng alias.
10. Nếu dùng OUT/INOUT ở cấp client, truyền user variable và đọc kết quả sau CALL.
11. Nếu dùng function, khai báo tham số IN và trả giá trị bằng RETURN.
12. Kiểm tra routine với dữ liệu thường, dữ liệu rỗng, NULL và giá trị biên.

Sơ đồ luồng dữ liệu:

~~~mermaid
flowchart TD
    A[Caller] --> B[IN parameters]
    A --> C[INOUT initial values]
    B --> D[Stored procedure]
    C --> D
    D --> E[Local variables DECLARE]
    E --> F[SET and SELECT INTO]
    F --> G[Business logic]
    G --> H[OUT values]
    G --> I[Updated INOUT values]
    H --> J[Caller reads results]
    I --> J
~~~

## 12. Bài tập thực hành

### Bài 1: Khai báo và khởi tạo biến cục bộ

Tạo procedure khai báo ba biến: số lượng, tổng tiền và trạng thái xử lý. Gán DEFAULT cho từng biến, sau đó dùng SET để cập nhật và SELECT để hiển thị.

### Bài 2: Phạm vi khối lồng nhau

Tạo procedure có một biến ở khối ngoài và một biến ở khối con. Thử truy cập biến khối con sau END và giải thích vì sao không hợp lệ.

### Bài 3: Truy vấn vào biến cục bộ

Dùng SELECT ... INTO để lấy tổng đơn hàng của một khách hàng. Thử customer_id tồn tại và không tồn tại; quan sát warning 1329 và giá trị biến giữ nguyên.

### Bài 4: Phát hiện nhiều hàng

Viết SELECT ... INTO theo customer_id có thể trả nhiều đơn. Quan sát lỗi 1172. Sau đó sửa bằng SUM hoặc ORDER BY ... LIMIT 1 tùy mục tiêu.

### Bài 5: Biến người dùng theo session

Tạo @customer_id, dùng nó trong hai câu SELECT và mở một connection khác để kiểm tra biến không được chia sẻ giữa các session.

### Bài 6: Tránh thứ tự đánh giá không xác định

Viết phép tăng bộ đếm bằng SET riêng biệt. So sánh với cách vừa đọc vừa gán @counter trong cùng SELECT và giải thích vì sao cách sau không an toàn.

### Bài 7: Procedure với IN và OUT

Viết procedure nhận customer_id qua IN và trả số đơn qua OUT. Gọi bằng user variable và đọc kết quả sau CALL.

### Bài 8: Procedure với INOUT

Viết procedure nhận mức giảm giá, giới hạn trong khoảng 0 đến 30 và trả lại giá trị đã giới hạn. Kiểm tra đầu vào 10, 50 và NULL.

### Bài 9: Function chỉ có IN

Viết function nhận giá gốc và phần trăm giảm, trả giá sau giảm bằng RETURN. Thử gọi function trong SELECT.

### Bài 10: Thiết kế giao diện routine

Thiết kế một procedure tính tổng tiền theo khách hàng. Phân loại từng dữ liệu thành IN, OUT, INOUT hoặc local variable và giải thích lý do chọn.

## Kết luận

Biến cục bộ, biến người dùng và tham số routine phục vụ các phạm vi dữ liệu khác nhau. DECLARE tạo biến cục bộ trong BEGIN ... END; user variable @name tồn tại trong session; tham số IN/OUT/INOUT truyền dữ liệu qua lời gọi stored procedure. Stored function chỉ dùng tham số IN và trả kết quả bằng RETURN.

Hãy dùng biến cục bộ cho tính toán nội bộ, tham số để mô tả giao diện routine và user variable khi cần trao đổi giá trị trong cùng session. Đặt tên rõ ràng, khởi tạo có chủ đích, kiểm soát cardinality của SELECT ... INTO và kiểm tra kết quả OUT/INOUT sau CALL. Những quy tắc này giúp stored program dễ đọc, dễ kiểm thử và ít phụ thuộc trạng thái kết nối.

## Tài liệu tham khảo

- MySQL 8.4 Reference Manual — Local Variable DECLARE Statement: https://dev.mysql.com/doc/refman/8.4/en/declare-local-variable.html
- MySQL 8.4 Reference Manual — Local Variable Scope and Resolution: https://dev.mysql.com/doc/refman/8.4/en/local-variable-scope.html
- MySQL 8.4 Reference Manual — Variables in Stored Programs: https://dev.mysql.com/doc/refman/8.4/en/stored-program-variables.html
- MySQL 8.4 Reference Manual — User-Defined Variables: https://dev.mysql.com/doc/refman/8.4/en/user-variables.html
- MySQL 8.4 Reference Manual — CREATE PROCEDURE and CREATE FUNCTION: https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- MySQL 8.4 Reference Manual — CALL Statement: https://dev.mysql.com/doc/refman/8.4/en/call.html
- MySQL 8.4 Reference Manual — SELECT ... INTO Statement: https://dev.mysql.com/doc/refman/8.4/en/select-into.html
- MySQL 8.4 Reference Manual — Restrictions on Stored Programs: https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html


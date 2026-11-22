# BEGIN/END, khối lồng nhau và phạm vi biến

Stored program trong MySQL dùng khối BEGIN ... END để nhóm các câu lệnh thành một thân chương trình. Bên trong khối, bạn có thể khai báo biến cục bộ, điều kiện, cursor và handler; thực thi các câu SQL; rồi tổ chức logic bằng IF, CASE và các vòng lặp. Khi một khối chứa khối khác, mỗi khối tạo ra một phạm vi khai báo riêng. Hiểu ranh giới này giúp tránh lỗi khai báo sai vị trí, dùng nhầm biến và để trạng thái rò rỉ giữa các lần gọi.

Trong module DATABASE_MYSQL, bài học này tập trung vào cú pháp khối, thứ tự khai báo, biến cục bộ và tham số routine, phạm vi của khối lồng nhau, label, cùng sự khác nhau giữa BEGIN ... END và lệnh bắt đầu transaction.

## 1. BEGIN ... END là khối lệnh

BEGIN ... END bao quanh một nhóm câu lệnh được thực thi theo thứ tự. Nó xuất hiện trong procedure, function, trigger, event và các khối lồng bên trong thân stored program.

Ví dụ tối giản:

~~~sql
BEGIN
    DECLARE v_message VARCHAR(100) DEFAULT 'Hello MySQL';
    SELECT v_message AS message;
END
~~~

Đây là phần thân minh họa bên trong stored program; BEGIN ... END compound statement không phải một script độc lập để chạy trực tiếp như SELECT ở cấp session. Khối thường có phần khai báo ở đầu, sau đó mới đến các câu lệnh thực thi. Khối có thể chứa nhiều câu lệnh SQL, câu lệnh điều khiển luồng và các khối con. Khi MySQL gặp END, phạm vi của khối hiện tại kết thúc.

BEGIN ... END trong stored program là cú pháp khối lệnh, không tự động mở transaction. Muốn bắt đầu transaction, dùng START TRANSACTION trong ngữ cảnh được phép. Không suy luận rằng cứ thấy BEGIN là dữ liệu đã được bảo vệ bởi transaction.

## 2. Tạo procedure có thân BEGIN ... END

Ví dụ một stored procedure tính tổng giá trị đơn hàng của khách hàng:

~~~sql
DELIMITER //

CREATE PROCEDURE get_customer_order_total(
    IN p_customer_id BIGINT UNSIGNED
)
BEGIN
    DECLARE v_total DECIMAL(14,2) DEFAULT 0.00;

    SELECT COALESCE(SUM(total_amount), 0.00)
    INTO v_total
    FROM orders
    WHERE customer_id = p_customer_id;

    SELECT
        p_customer_id AS customer_id,
        v_total AS order_total;
END//

DELIMITER ;
~~~

Procedure nhận tham số đầu vào, khai báo một biến cục bộ, gán kết quả truy vấn vào biến rồi trả một result set. DELIMITER là lệnh của client dòng lệnh MySQL để đổi ký tự kết thúc câu lệnh khi gửi định nghĩa routine; nó không phải câu lệnh SQL được server thực thi.

Nếu không đổi delimiter trong MySQL CLI, dấu chấm phẩy đầu tiên bên trong thân procedure có thể khiến client gửi câu lệnh CREATE PROCEDURE quá sớm. Trong MySQL Workbench hoặc công cụ khác, cách khai báo delimiter có thể khác tùy editor.

## 3. Cấu trúc tổng quát của một khối

Một khối compound statement có dạng:

~~~sql
[block_label:] BEGIN
    -- Các khai báo phải nằm ở đầu khối
    DECLARE ...;
    DECLARE ...;

    -- Các câu lệnh thực thi
    statement_1;
    statement_2;
END [block_label]
~~~

Label ở đầu và cuối là tùy chọn. Nếu đặt cả hai, tên label cuối phải khớp label đầu. Label hữu ích khi muốn chỉ rõ khối hoặc vòng lặp mà LEAVE/ITERATE tác động đến.

Các thành phần có thể xuất hiện trong thân khối:

- Khai báo biến cục bộ bằng DECLARE.
- Khai báo named condition, cursor và handler.
- Gán biến bằng SET.
- Gán kết quả truy vấn bằng SELECT ... INTO.
- Câu lệnh DML/DDL được phép trong loại routine đang viết.
- Cấu trúc điều khiển như IF, CASE, LOOP, WHILE và REPEAT.
- Khối BEGIN ... END lồng nhau.

## 4. Thứ tự khai báo trong mỗi khối

Các khai báo phải đứng trước câu lệnh thực thi đầu tiên trong cùng khối. MySQL yêu cầu thứ tự nhóm khai báo như sau:

1. Biến cục bộ và named condition.
2. Cursor.
3. Handler.

Ví dụ:

~~~sql
BEGIN
    DECLARE v_count INT DEFAULT 0;
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE no_row CONDITION FOR SQLSTATE '02000';
    DECLARE cur_orders CURSOR FOR
        SELECT order_id FROM orders;
    DECLARE CONTINUE HANDLER FOR no_row
        SET v_done = TRUE;

    -- Bắt đầu câu lệnh thực thi sau các khai báo.
    SET v_count = 0;
END
~~~

Nếu khai báo một biến sau SET, SELECT, IF hoặc câu lệnh thực thi khác trong cùng khối, routine sẽ không biên dịch. Nếu cần khai báo biến cho một phần xử lý riêng, hãy tạo một khối con BEGIN ... END rồi khai báo biến ở đầu khối con đó.

Mỗi khối lồng nhau có vùng khai báo riêng. Quy tắc thứ tự khai báo được áp dụng độc lập cho từng khối.

## 5. Khai báo biến cục bộ bằng DECLARE

Biến cục bộ được khai báo bằng cú pháp:

~~~sql
DECLARE variable_name data_type [DEFAULT value];
~~~

Ví dụ:

~~~sql
BEGIN
    DECLARE v_customer_id BIGINT UNSIGNED;
    DECLARE v_customer_name VARCHAR(120) DEFAULT '';
    DECLARE v_order_count INT DEFAULT 0;
    DECLARE v_total_amount DECIMAL(14,2) DEFAULT 0.00;
    DECLARE v_is_valid BOOLEAN DEFAULT TRUE;

    SET v_customer_id = 42;
    SET v_customer_name = 'Nguyen An';
    SET v_order_count = 3;
    SET v_total_amount = 1250.50;
END
~~~

Biến được khai báo mà không có DEFAULT bắt đầu với giá trị NULL. Nếu logic yêu cầu giá trị khởi tạo xác định, hãy khai báo DEFAULT hoặc gán rõ trước khi đọc biến.

Kiểu dữ liệu của biến nên phù hợp với cột và phép tính:

| Nhu cầu | Kiểu thường dùng |
|---|---|
| ID số nguyên không âm | BIGINT UNSIGNED |
| Số lượng | INT hoặc BIGINT |
| Tiền và số thập phân chính xác | DECIMAL(p,s) |
| Tên hoặc mã chuỗi | VARCHAR(n) |
| Ngày | DATE |
| Thời điểm không kèm timezone | DATETIME |
| Cờ logic | BOOLEAN (bí danh của TINYINT(1)) |

Biến cục bộ chỉ tồn tại trong lần thực thi routine và phạm vi khối khai báo nó. Nó không phải một cột bảng và cũng không phải session user variable.

## 6. Gán giá trị cho biến

### Dùng SET

SET là cách trực tiếp để gán một biểu thức:

~~~sql
BEGIN
    DECLARE v_subtotal DECIMAL(12,2) DEFAULT 0.00;
    DECLARE v_tax_rate DECIMAL(5,4) DEFAULT 0.1000;
    DECLARE v_tax DECIMAL(12,2) DEFAULT 0.00;

    SET v_subtotal = 250.00;
    SET v_tax = v_subtotal * v_tax_rate;
END
~~~

Có thể gán nhiều biến trong một câu SET:

~~~sql
SET v_min = 10, v_max = 100;
~~~

### Dùng SELECT ... INTO

SELECT ... INTO lấy giá trị từ truy vấn và gán vào biến:

~~~sql
BEGIN
    DECLARE v_customer_name VARCHAR(120) DEFAULT NULL;

    SELECT customer_name
    INTO v_customer_name
    FROM customers
    WHERE customer_id = 42;
END
~~~

Truy vấn nên trả đúng một hàng. Nếu không trả hàng nào, MySQL phát cảnh báo NOT FOUND và biến giữ giá trị trước đó; nếu trả nhiều hơn một hàng, MySQL báo lỗi. Vì vậy, hãy dùng khóa duy nhất trong điều kiện, aggregate phù hợp hoặc giới hạn kết quả có chủ đích. Không dùng LIMIT 1 để che một truy vấn vốn phải duy nhất nếu nghiệp vụ yêu cầu phát hiện dữ liệu trùng.

Ví dụ aggregate luôn trả một hàng:

~~~sql
SELECT COALESCE(SUM(total_amount), 0.00)
INTO v_total
FROM orders
WHERE customer_id = p_customer_id;
~~~

Khi không có đơn hàng, SUM trả NULL; COALESCE đổi thành 0 để biến nhận giá trị có ý nghĩa.

## 7. Tham số routine và biến cục bộ

Procedure có thể nhận tham số theo ba mode:

| Mode | Hướng dữ liệu | Ý nghĩa |
|---|---|---|
| IN | Caller → routine | Đầu vào; routine đọc giá trị tham số |
| OUT | Routine → caller | Routine gán kết quả để caller nhận |
| INOUT | Hai chiều | Caller truyền giá trị ban đầu, routine có thể thay đổi và trả lại |

Ví dụ procedure dùng OUT:

~~~sql
DELIMITER //

CREATE PROCEDURE count_customer_orders(
    IN p_customer_id BIGINT UNSIGNED,
    OUT p_order_count BIGINT
)
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
~~~

Gọi procedure:

~~~sql
CALL count_customer_orders(42, @order_count);
SELECT @order_count;
~~~

@order_count là session user variable dùng để nhận OUT parameter trong ví dụ gọi từ SQL client. Nó khác với biến cục bộ v_total khai báo bằng DECLARE bên trong routine.

Tham số của stored function trong MySQL là đầu vào; không khai báo mode OUT hoặc INOUT cho tham số function. Mode OUT/INOUT được dùng với stored procedure.

Ví dụ INOUT nhận giá trị ban đầu rồi trả giá trị đã thay đổi:

~~~sql
DELIMITER //

CREATE PROCEDURE apply_ten_percent_bonus(
    INOUT p_amount DECIMAL(14,2)
)
BEGIN
    SET p_amount = p_amount * 1.10;
END//

DELIMITER ;
~~~

Gọi procedure:

~~~sql
SET @amount = 100.00;
CALL apply_ten_percent_bonus(@amount);
SELECT @amount AS amount_after_bonus;
~~~

Parameter có phạm vi trong toàn bộ routine body; local variable có phạm vi trong block nơi nó được khai báo và các block con của block đó.

## 8. Phạm vi biến trong một khối

Biến chỉ có thể được tham chiếu trong khối đã khai báo và các khối con nằm bên trong nó. Khi một khối kết thúc, biến cục bộ thuộc khối đó không còn tồn tại.

Ví dụ:

~~~sql
BEGIN
    DECLARE v_outer_total DECIMAL(12,2) DEFAULT 100.00;

    SET v_outer_total = v_outer_total + 25.00;
    SELECT v_outer_total AS total_before_inner_block;

    BEGIN
        DECLARE v_inner_discount DECIMAL(12,2) DEFAULT 10.00;
        DECLARE v_inner_total DECIMAL(12,2) DEFAULT 0.00;

        SET v_inner_total = v_outer_total - v_inner_discount;
        SELECT v_inner_total AS total_after_discount;
    END;

    -- v_outer_total vẫn còn trong phạm vi.
    SELECT v_outer_total AS total_after_inner_block;

    -- v_inner_discount và v_inner_total không còn truy cập được ở đây.
END
~~~

Khối con có thể đọc biến được khai báo ở khối cha. Khối cha không thể đọc biến chỉ tồn tại trong khối con sau khi khối con kết thúc.

## 9. Biến cùng tên trong khối lồng nhau

Một khối con có thể khai báo biến trùng tên với biến ở khối cha. Khi đó, tên trong khối con tham chiếu biến được khai báo gần nhất; biến bên ngoài bị che khuất trong phạm vi trùng tên.

Ví dụ:

~~~sql
BEGIN
    DECLARE v_message VARCHAR(40) DEFAULT 'outer';

    BEGIN
        DECLARE v_message VARCHAR(40) DEFAULT 'inner';
        SELECT v_message AS current_message;
    END;

    SELECT v_message AS current_message;
END
~~~

Trong khối con, SELECT trả inner. Sau END của khối con, SELECT bên ngoài trả outer. Biến bên ngoài không bị ghi đè; nó chỉ tạm thời bị che khuất khi tra cứu tên trong khối con.

Dù MySQL cho phép cách viết này, nên tránh đặt biến lồng nhau cùng tên nếu không có lý do rõ ràng. Dùng tiền tố nhất quán như p_ cho parameter, v_ cho local variable và tên mô tả theo vai trò sẽ giúp giảm nhầm lẫn.

## 10. Khối lồng nhau để cô lập biến tạm

Khối con hữu ích khi một phần logic cần biến trung gian riêng:

~~~sql
BEGIN
    DECLARE v_order_id BIGINT UNSIGNED DEFAULT 9001;
    DECLARE v_final_amount DECIMAL(12,2) DEFAULT 0.00;

    BEGIN
        DECLARE v_subtotal DECIMAL(12,2) DEFAULT 500.00;
        DECLARE v_discount DECIMAL(12,2) DEFAULT 50.00;
        DECLARE v_tax DECIMAL(12,2) DEFAULT 45.00;

        SET v_final_amount = v_subtotal - v_discount + v_tax;
    END;

    SELECT
        v_order_id AS order_id,
        v_final_amount AS final_amount;
END
~~~

v_subtotal, v_discount và v_tax chỉ cần thiết trong phép tính nội bộ nên được đặt trong khối con. v_final_amount được khai báo ở khối cha vì cần sử dụng sau khi khối con kết thúc.

Đây là cách tổ chức phạm vi, không tạo transaction hay savepoint. Nếu một câu SQL trong khối con thay đổi dữ liệu, hiệu lực commit/rollback vẫn phụ thuộc transaction/session và engine của bảng.

## 11. Label cho BEGIN ... END

Có thể đặt label cho khối:

~~~sql
main_block: BEGIN
    DECLARE v_count INT DEFAULT 0;

    inner_block: BEGIN
        SET v_count = v_count + 1;
    END inner_block;

    SELECT v_count;
END main_block
~~~

Label đầu và cuối phải khớp nếu cùng được chỉ định. Label giúp câu lệnh điều khiển luồng tham chiếu đúng khối, đặc biệt khi có nhiều vòng lặp hoặc khối lồng nhau.

LEAVE label thoát khỏi khối hoặc vòng lặp mang label đó. Ví dụ:

~~~sql
main_block: BEGIN
    DECLARE v_amount DECIMAL(12,2) DEFAULT 0.00;

    IF v_amount <= 0 THEN
        LEAVE main_block;
    END IF;

    SELECT 'This statement is skipped';
END main_block
~~~

Khi điều kiện đúng, LEAVE main_block kết thúc khối main_block và các câu lệnh còn lại bên trong khối không được thực hiện. Nếu routine còn logic sau khối, execution tiếp tục tại câu lệnh ngay sau END.

ITERATE label dùng để bỏ phần còn lại của vòng lặp hiện tại và bắt đầu lượt kế tiếp; nó chỉ áp dụng cho LOOP, WHILE hoặc REPEAT có label phù hợp, không dùng để lặp lại một BEGIN block thông thường.

## 12. Khối BEGIN ... END bên trong IF và vòng lặp

Các cấu trúc điều khiển có thể chứa một compound block để khai báo biến riêng:

~~~sql
BEGIN
    DECLARE v_status VARCHAR(20) DEFAULT 'PENDING';

    IF v_status = 'PENDING' THEN
        BEGIN
            DECLARE v_message VARCHAR(100) DEFAULT 'Waiting for processing';
            SELECT v_message AS detail;
        END;
    ELSE
        SELECT 'No action required' AS detail;
    END IF;
END
~~~

Khối con cho phép khai báo v_message tại đúng phạm vi cần dùng. Nếu cố DECLARE biến trực tiếp sau một câu lệnh thực thi trong cùng block, MySQL sẽ báo lỗi vì khai báo không còn ở đầu block.

Ví dụ với vòng lặp:

~~~sql
BEGIN
    DECLARE v_counter INT DEFAULT 0;

    counter_loop: WHILE v_counter < 3 DO
        BEGIN
            DECLARE v_step_message VARCHAR(40);

            SET v_counter = v_counter + 1;
            SET v_step_message = CONCAT('Step ', v_counter);
            SELECT v_step_message AS progress;
        END;
    END WHILE counter_loop;
END
~~~

Mỗi lần đi vào khối con, biến v_step_message thuộc phạm vi của lần thực thi khối đó. v_counter thuộc khối ngoài nên được giữ giữa các vòng lặp.

## 13. Biến cục bộ khác session user variable

MySQL có hai loại biến thường bị nhầm:

| Đặc điểm | Local variable | User-defined variable |
|---|---|---|
| Cách khai báo | DECLARE v_name TYPE | Gán trực tiếp @name := value |
| Phạm vi | Khối/routine khai báo | Session kết nối hiện tại |
| Thời điểm tồn tại | Trong thời gian khối/routine còn hoạt động | Cho đến khi session kết thúc |
| Có cần DECLARE | Có | Không |
| Dùng cho | Trạng thái nội bộ của routine | Trao đổi giá trị trong các câu SQL cùng session |

Ví dụ session variable:

~~~sql
SET @current_customer_id = 42;

SELECT *
FROM orders
WHERE customer_id = @current_customer_id;
~~~

Trong routine, ưu tiên local variable:

~~~sql
BEGIN
    DECLARE v_customer_id BIGINT UNSIGNED DEFAULT 42;

    SELECT *
    FROM orders
    WHERE customer_id = v_customer_id;
END
~~~

Không dùng @variable thay cho biến cục bộ trong logic routine chỉ vì cú pháp ngắn hơn. User variable tồn tại theo connection; với connection pool, giá trị cũ có thể còn trên connection được tái sử dụng và gây phụ thuộc trạng thái ngoài ý muốn.

## 14. Tránh trùng tên biến với cột

Không nên đặt local variable trùng tên với cột trong câu SQL. Khi tên biến và tên cột giống nhau, quy tắc phân giải tên có thể khiến biểu thức không mang ý nghĩa mà người viết mong đợi.

Ví dụ dễ gây nhầm:

~~~sql
DECLARE customer_id BIGINT UNSIGNED;

SELECT customer_id
INTO customer_id
FROM customers
WHERE customer_id = customer_id;
~~~

Trong stored program, tên local variable không được phân giải như tên cột không định danh; biến cục bộ có thể che khuất tên cột cùng tên. Điều kiện trên vì vậy có nguy cơ so sánh biến với chính nó thay vì lọc theo cột. Viết rõ tên:

~~~sql
DECLARE v_customer_id BIGINT UNSIGNED;

SELECT c.customer_id
INTO v_customer_id
FROM customers AS c
WHERE c.customer_id = p_customer_id;
~~~

Quy ước p_ cho parameter, v_ cho local variable, alias cho bảng và qualify tên cột giúp câu SQL dễ đọc, tránh điều kiện vô tình trở thành so sánh biến với chính nó.

## 15. Khối lệnh không đồng nghĩa transaction

Ba khái niệm sau có mục đích khác nhau:

| Cú pháp | Mục đích |
|---|---|
| BEGIN ... END | Nhóm câu lệnh và tạo phạm vi biến trong stored program |
| START TRANSACTION | Bắt đầu transaction |
| COMMIT / ROLLBACK | Kết thúc transaction bằng cách xác nhận hoặc hủy thay đổi chưa commit |

Ví dụ khối có nhiều câu SQL:

~~~sql
BEGIN
    DECLARE v_count INT DEFAULT 0;

    SELECT COUNT(*)
    INTO v_count
    FROM orders;

    SELECT v_count AS order_count;
END
~~~

Khối trên không tự bắt đầu transaction. Nếu cần nhiều thao tác dữ liệu thuộc một đơn vị nguyên tử, hãy thiết kế transaction riêng theo quy tắc của stored procedure và storage engine. Cũng cần nhớ một số loại stored program như function và trigger có các giới hạn riêng đối với transaction control; không sao chép lệnh START TRANSACTION/COMMIT vào mọi loại routine.

## 16. Ví dụ procedure hoàn chỉnh dùng khối lồng nhau

Ví dụ procedure tính số tiền sau giảm giá cho một đơn hàng. Biến tổng tiền được khai báo ở khối ngoài vì cần trả kết quả; biến giảm giá tạm thời chỉ được khai báo trong khối con.

~~~sql
DELIMITER //

CREATE PROCEDURE calculate_order_net_amount(
    IN p_order_id BIGINT UNSIGNED,
    IN p_discount_rate DECIMAL(5,4),
    OUT p_net_amount DECIMAL(14,2)
)
main_block: BEGIN
    DECLARE v_subtotal DECIMAL(14,2) DEFAULT 0.00;

    IF p_discount_rate < 0 OR p_discount_rate > 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Discount rate must be between 0 and 1';
    END IF;

    SELECT COALESCE(SUM(quantity * unit_price), 0.00)
    INTO v_subtotal
    FROM order_items
    WHERE order_id = p_order_id;

    BEGIN
        DECLARE v_discount_amount DECIMAL(14,2) DEFAULT 0.00;

        SET v_discount_amount = v_subtotal * p_discount_rate;
        SET p_net_amount = v_subtotal - v_discount_amount;
    END;
END main_block//

DELIMITER ;
~~~

Gọi procedure:

~~~sql
CALL calculate_order_net_amount(9001, 0.1000, @net_amount);
SELECT @net_amount;
~~~

Ví dụ giả định bảng order_items có các cột order_id, quantity và unit_price. p_discount_rate được kiểm tra trong khoảng từ 0 đến 1; v_subtotal tồn tại trong toàn bộ main_block; v_discount_amount chỉ tồn tại trong khối con. OUT parameter p_net_amount là nơi routine đưa kết quả về caller.

Trong ứng dụng thực tế, cần xác định rõ hành vi khi order_id không tồn tại hoặc đơn hàng không có item. Aggregate SUM không có hàng đầu vào trả NULL; COALESCE trong ví dụ biến trường hợp đó thành 0.00. Quy tắc nghiệp vụ có thể yêu cầu báo lỗi thay vì trả 0, khi đó cần bổ sung kiểm tra phù hợp.

## 17. Lỗi thường gặp khi làm việc với block và variable

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| DECLARE sau câu SET/SELECT | Khai báo không nằm ở đầu khối | Chuyển DECLARE lên đầu hoặc tạo block con |
| Dùng biến khối con sau END | Biến đã ra khỏi scope | Đưa biến lên block cha nếu cần dùng tiếp |
| Vô tình che khuất biến ngoài | Biến trong và ngoài trùng tên | Đặt tên theo vai trò, dùng tiền tố |
| Dùng @variable như local variable | User variable có phạm vi session | Dùng DECLARE cho trạng thái nội bộ |
| SELECT ... INTO trả nhiều hàng | Truy vấn không bảo đảm một hàng | Dùng khóa duy nhất, aggregate hoặc xử lý nhiều hàng bằng cursor |
| SELECT ... INTO không có hàng | NOT FOUND; biến giữ giá trị trước đó | Khởi tạo rõ và xử lý NOT FOUND theo yêu cầu |
| Nhầm BEGIN với START TRANSACTION | Khối lệnh không mở transaction | Dùng transaction control trong ngữ cảnh được phép |
| Label đầu/cuối không khớp | Sai cú pháp block label | Dùng cùng một tên hoặc bỏ label cuối |
| ITERATE một block thường | ITERATE chỉ dành cho vòng lặp | Dùng LEAVE để thoát block hoặc đặt logic trong loop |
| Trùng tên biến với cột | SQL khó phân giải đúng ý định | Dùng p_/v_, alias và qualify tên cột |

## 18. Quy trình thiết kế block dễ bảo trì

1. Chia routine thành các khối theo đơn vị trách nhiệm, tránh một thân procedure quá dài.
2. Khai báo biến gần phạm vi nhỏ nhất có thể nhưng vẫn đủ để dùng.
3. Đặt toàn bộ DECLARE ở đầu từng khối và theo đúng thứ tự variables/conditions, cursors, handlers.
4. Dùng tiền tố nhất quán cho parameter và local variable.
5. Không che khuất tên biến ở block con nếu không thực sự cần.
6. Dùng SELECT ... INTO khi truy vấn bảo đảm một hàng hoặc aggregate trả một hàng.
7. Khởi tạo biến trước khi đọc để tránh phụ thuộc giá trị NULL/giá trị cũ.
8. Dùng label có ý nghĩa khi cần LEAVE/ITERATE trong cấu trúc lồng nhau.
9. Tách rõ block scope với transaction boundary.
10. Kiểm tra quyền và loại stored program trước khi thêm transaction control.
11. Kiểm tra routine bằng CALL với dữ liệu đại diện và các trường hợp biên.
12. Ghi rõ biến nào là đầu vào, biến trung gian và đầu ra để người bảo trì theo dõi luồng dữ liệu.

## 19. Bài tập thực hành

1. Tạo procedure có một tham số IN, một local variable và một SELECT ... INTO.
2. Tạo hai khối BEGIN ... END lồng nhau; khai báo biến riêng trong mỗi khối và quan sát phạm vi.
3. Khai báo cùng tên biến ở khối cha và khối con; quan sát hiện tượng shadowing.
4. Thử đặt DECLARE sau một câu SET trong cùng khối và giải thích lỗi; sau đó chuyển khai báo vào đầu block hoặc block con.
5. Tạo procedure có tham số OUT và nhận kết quả qua session variable.
6. Tạo procedure có tham số INOUT, thay đổi giá trị và kiểm tra kết quả caller nhận được.
7. Dùng label cho một block và LEAVE block khi điều kiện không hợp lệ.
8. Tạo vòng WHILE có label và dùng ITERATE để bỏ qua một lượt xử lý.
9. So sánh biến cục bộ DECLARE với user variable @name trên cùng một connection; kiểm tra trạng thái session khi connection được tái sử dụng.
10. Viết procedure tính tổng đơn hàng với block con chứa biến giảm giá, rồi giải thích vì sao biến trung gian không thể được tham chiếu sau END của block con.

Bạn hoàn thành bài khi tổ chức được stored program thành các khối rõ ràng, khai báo đúng thứ tự, giải thích được phạm vi và shadowing của biến, sử dụng được parameter IN/OUT/INOUT và phân biệt chính xác BEGIN ... END với transaction control. Các quy tắc này là nền tảng để đọc và xây dựng procedure, function, trigger, event, cursor và handler ở những bài tiếp theo.

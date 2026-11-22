# SET, SELECT INTO và quy tắc gán kết quả

Trong stored program của MySQL, biến cục bộ và tham số giúp lưu trạng thái trung gian, nhận kết quả truy vấn và điều khiển các bước xử lý. Hai cách gán thường gặp là câu lệnh SET và mệnh đề SELECT ... INTO.

Chúng có vẻ tương tự nhưng không có cùng ngữ nghĩa:

- SET gán một biểu thức cho biến hoặc tham số đã tồn tại; có thể gán nhiều biến trong một câu lệnh.
- SELECT ... INTO chạy một truy vấn và ánh xạ các giá trị của hàng kết quả vào danh sách biến.
- SELECT ... INTO cần xử lý rõ trường hợp không có hàng, đúng một hàng hoặc nhiều hơn một hàng.
- Biến cục bộ, tham số routine và user variable có phạm vi sống, kiểu dữ liệu và mục đích khác nhau.

Bài viết tập trung vào quy tắc gán kết quả trong stored program MySQL: khai báo biến, dùng SET, nhận dữ liệu bằng SELECT ... INTO, xử lý cardinality, chuyển đổi kiểu và tránh những lỗi khiến biến mang giá trị cũ hoặc kết quả không xác định.

## 1. Phạm vi của SET và SELECT ... INTO

Ví dụ sau dùng bảng đơn hàng:

~~~sql
CREATE TABLE sales_orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status_code TINYINT UNSIGNED NOT NULL,
    total DECIMAL(13, 2) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created
        (customer_id, created_at, order_id)
) ENGINE = InnoDB;
~~~

Một stored procedure có thể khai báo biến cục bộ, lấy giá trị từ tham số, truy vấn một hàng và tính kết quả:

~~~sql
DELIMITER //

CREATE PROCEDURE calculate_order_total(
    IN p_order_id BIGINT UNSIGNED,
    OUT p_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_subtotal DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_tax DECIMAL(13, 2) DEFAULT 0;

    SELECT so.total
      INTO v_subtotal
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;

    SET v_tax = ROUND(v_subtotal * 0.08, 2);
    SET p_total = v_subtotal + v_tax;
END//

DELIMITER ;
~~~

DELIMITER là lệnh của client mysql để đổi ký tự kết thúc câu lệnh khi gửi định nghĩa routine có nhiều dấu chấm phẩy bên trong. Nó không phải câu lệnh SQL được gửi nguyên văn đến server. Khi dùng GUI, migration tool hoặc driver, cách khai báo routine có thể khác; hãy làm theo cơ chế delimiter/script của công cụ đó.

Ví dụ minh họa cả hai hình thức:

- SELECT ... INTO lấy giá trị total từ hàng đơn hàng và gán vào v_subtotal.
- SET tính thuế rồi gán vào v_tax.
- SET tiếp tục gán kết quả cho tham số OUT p_total.

Ví dụ này giả định order_id tồn tại. Phần sau sẽ xử lý đầy đủ trường hợp không tìm thấy hàng.

## 2. Biến cục bộ trong stored program

Biến cục bộ được khai báo bằng DECLARE ở đầu một block BEGIN ... END, trước các câu lệnh thực thi trong block.

~~~sql
BEGIN
    DECLARE v_order_count BIGINT UNSIGNED DEFAULT 0;
    DECLARE v_total DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_note VARCHAR(200) DEFAULT '';
    DECLARE v_created_at DATETIME DEFAULT NULL;

    SET v_order_count = 0;
    SET v_total = 0;
    SET v_note = 'Chưa xử lý';
END
~~~

Trong một stored routine, DECLARE variable phải đứng trước các câu lệnh thực thi. Nếu block còn khai báo cursor hoặc handler, thứ tự khai báo cũng phải tuân theo quy tắc của MySQL: biến và điều kiện trước, cursor tiếp theo, handler sau cùng.

Tên biến nên có tiền tố nhất quán như v_ để phân biệt với:

- Cột bảng: order_id, total, created_at.
- Tham số routine: p_order_id, p_total.
- User variable: @current_order_id.

Tránh đặt biến cục bộ trùng tên cột. Khi tham chiếu cột trong query, luôn dùng alias và qualifier như so.total; cách này giảm nguy cơ tên không rõ ràng hoặc bị hiểu nhầm là biến routine.

### 2.1. Phạm vi block

Biến cục bộ chỉ tồn tại trong block nơi nó được khai báo và các block con có thể truy cập theo quy tắc scope. Khi block kết thúc, biến không còn tồn tại.

~~~sql
CREATE PROCEDURE show_local_scope()
BEGIN
    DECLARE v_message VARCHAR(50) DEFAULT 'outer';

    BEGIN
        DECLARE v_inner_message VARCHAR(50) DEFAULT 'inner';
        SET v_message = 'updated by inner block';
        SELECT v_message, v_inner_message;
    END;

    SELECT v_message;
END
~~~

Block bên trong có thể dùng biến của block ngoài. Biến khai báo bên trong không thể được tham chiếu sau khi block đó kết thúc.

### 2.2. Khai báo kiểu dữ liệu phù hợp

Kiểu của biến cục bộ được xác định lúc khai báo:

| Kiểu dữ liệu | Trường hợp thường dùng |
|---|---|
| INT, BIGINT | Số lượng, khóa định danh |
| DECIMAL(p,s) | Tiền và số thập phân cần độ chính xác |
| VARCHAR(n) | Mã, tên, chuỗi có độ dài giới hạn |
| DATE, DATETIME, TIMESTAMP | Ngày hoặc thời điểm |
| BOOLEAN | Cờ logic; trong MySQL là alias của TINYINT(1) |
| JSON | Giá trị JSON khi routine cần xử lý tài liệu JSON |

Không dùng FLOAT hoặc DOUBLE cho tiền chỉ vì chúng tiện tính toán; đây là kiểu số gần đúng. DECIMAL thường phù hợp hơn khi cần kết quả thập phân chính xác theo nghiệp vụ.

Nếu biến nhận dữ liệu từ cột DECIMAL(13,2), khai báo biến có độ chính xác và scale phù hợp để tránh làm tròn hoặc mất phần dữ liệu ngoài ý muốn.

## 3. Tham số IN, OUT và INOUT

Stored procedure có thể nhận hoặc trả dữ liệu qua tham số:

- IN: đầu vào cho routine. Bên trong routine, tham số có thể được dùng như một biến cục bộ; việc gán lại không làm thay đổi biến của caller.
- OUT: routine ghi giá trị để caller nhận sau khi procedure kết thúc.
- INOUT: caller truyền giá trị ban đầu và routine có thể cập nhật giá trị đó.

Ví dụ:

~~~sql
DELIMITER //

CREATE PROCEDURE apply_discount(
    IN p_subtotal DECIMAL(13, 2),
    IN p_discount_rate DECIMAL(5, 2),
    OUT p_final_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_discount DECIMAL(13, 2) DEFAULT 0;

    SET v_discount =
        ROUND(p_subtotal * p_discount_rate / 100, 2);

    SET p_final_total = p_subtotal - v_discount;
END//

DELIMITER ;
~~~

Gọi procedure và nhận kết quả qua user variable:

~~~sql
CALL apply_discount(1000.00, 10.00, @final_total);
SELECT @final_total;
~~~

User variable @final_total ở đây là nơi caller nhận giá trị OUT. Nó không phải biến cục bộ v_discount trong routine. OUT parameter được khởi tạo khi routine bắt đầu; dù vậy, gán giá trị đầu ra rõ ràng cho mọi nhánh giúp caller hiểu được hợp đồng kết quả.

### 3.1. Ví dụ INOUT

~~~sql
DELIMITER //

CREATE PROCEDURE add_bonus(
    IN p_bonus DECIMAL(13, 2),
    INOUT p_running_total DECIMAL(13, 2)
)
BEGIN
    SET p_running_total = p_running_total + p_bonus;
END//

DELIMITER ;
~~~

~~~sql
SET @running_total = 500.00;
CALL add_bonus(25.00, @running_total);
SELECT @running_total;
~~~

Kết quả user variable là 525.00. Caller phải truyền một biến phù hợp cho tham số OUT hoặc INOUT; không truyền một biểu thức hằng thay cho nơi nhận giá trị.

## 4. Câu lệnh SET

SET gán giá trị biểu thức cho một hoặc nhiều biến:

~~~sql
SET v_order_count = 10;
SET v_total = 1250.50;
SET v_note = 'Đã xác nhận';
SET v_total = v_total + 100.00;
~~~

Trong stored program, SET là cách rõ ràng để gán một giá trị tính toán, một literal, một tham số hoặc kết quả biểu thức cho biến cục bộ.

### 4.1. Gán nhiều biến trong một SET

~~~sql
BEGIN
    DECLARE v_subtotal DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_tax DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_grand_total DECIMAL(13, 2) DEFAULT 0;

    SET
        v_subtotal = 1000.00,
        v_tax = 80.00,
        v_grand_total = 1080.00;
END
~~~

Có thể gán nhiều biến trong cùng một câu lệnh SET. Tuy nhiên, không nên dựa vào việc đổi chỗ các biến trong một danh sách gán để thực hiện phép hoán đổi phức tạp. Khi cần trao đổi giá trị, dùng biến tạm và các câu SET tách biệt:

~~~sql
SET v_temp = v_left;
SET v_left = v_right;
SET v_right = v_temp;
~~~

Viết tách biệt giúp ý định rõ ràng và tránh phụ thuộc vào cách đánh giá biểu thức không được bảo đảm.

### 4.2. Dùng = và :=

Trong câu lệnh SET, có thể dùng dấu = hoặc := để gán:

~~~sql
SET v_total = 100.00;
SET v_total := v_total + 25.00;
~~~

Trong các biểu thức ngoài câu lệnh SET, toán tử gán của MySQL là :=. Tuy nhiên, với logic stored program, ưu tiên SET hoặc SELECT ... INTO thay vì nhúng phép gán vào một biểu thức SELECT.

Không nhầm dấu = dùng để gán trong SET với phép so sánh bằng trong điều kiện WHERE hoặc IF. Ngữ cảnh cú pháp quyết định ý nghĩa của dấu này.

### 4.3. Gán từ biểu thức

Biểu thức bên phải có thể dùng biến, tham số, hàm hoặc toán tử:

~~~sql
BEGIN
    DECLARE v_line_total DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_discount DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_final_total DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_is_large_order BOOLEAN DEFAULT FALSE;

    SET v_line_total = p_quantity * p_unit_price;
    SET v_discount = ROUND(v_line_total * p_discount_rate / 100, 2);
    SET v_final_total = v_line_total - v_discount;
    SET v_is_large_order = (v_final_total >= 10000.00);
END
~~~

Ví dụ giả định p_quantity, p_unit_price và p_discount_rate là tham số của routine bao ngoài. Kết quả của biểu thức được chuyển về kiểu đã khai báo của biến đích. Với biến BOOLEAN trong MySQL, giá trị được lưu như một giá trị số nhỏ; dùng điều kiện rõ ràng như v_final_total >= 10000.00 để tạo cờ dễ hiểu.

### 4.4. Gán NULL

Biến có thể nhận NULL nếu kiểu và ngữ cảnh cho phép:

~~~sql
SET v_customer_note = NULL;
~~~

Sau đó, kiểm tra bằng IS NULL hoặc IS NOT NULL:

~~~sql
IF v_customer_note IS NULL THEN
    SET v_customer_note = 'Không có ghi chú';
END IF;
~~~

Không dùng = NULL vì phép so sánh với NULL cho kết quả UNKNOWN, không phải TRUE hoặc FALSE.

## 5. User variable và system variable không phải biến cục bộ

MySQL có user variable với tiền tố @:

~~~sql
SET @current_order_id = 1001;
SET @running_total = 250.00;
SELECT @current_order_id, @running_total;
~~~

User variable có phạm vi session/connection. Giá trị có thể tồn tại sau khi stored procedure kết thúc và được câu lệnh tiếp theo trên cùng connection sử dụng. Khi connection đóng, user variable của session đó không còn.

So sánh:

| Đặc điểm | Local variable | User variable |
|---|---|---|
| Cách viết | v_total | @total |
| Khai báo | DECLARE trong block | Không cần DECLARE |
| Kiểu dữ liệu | Khai báo tĩnh trong routine | Kiểu gắn với giá trị được gán, có thể thay đổi |
| Phạm vi | Block/routine | Session/connection |
| Mục đích | Logic nội bộ routine | Trao đổi giá trị giữa các câu lệnh trong một session hoặc caller |
| Rủi ro | Scope và shadowing | Rò trạng thái giữa các request dùng chung connection |

Không dùng user variable thay cho local variable trong stored routine. Connection pool có thể tái sử dụng cùng connection cho nhiều request; user variable còn sót lại có thể khiến request sau đọc nhầm trạng thái nếu ứng dụng không khởi tạo lại.

### 5.1. Không gán user variable bên trong SELECT để điều khiển thứ tự

Một số câu SQL cũ dùng phép gán user variable ngay trong SELECT:

~~~sql
SELECT
    @running_total := @running_total + total,
    order_id
FROM sales_orders
ORDER BY order_id;
~~~

Không nên dựa vào thứ tự đánh giá các biểu thức có đọc và ghi cùng một user variable trong một câu SELECT. MySQL không bảo đảm thứ tự đánh giá biểu thức như một cơ chế tuần tự hóa trạng thái; kết quả có thể thay đổi theo kế hoạch hoặc phiên bản.

Nếu cần tính tổng, dùng SUM() hoặc window function phù hợp. Nếu cần cập nhật trạng thái từng bước trong stored program, dùng biến cục bộ và câu lệnh SET tách biệt.

### 5.2. System variable

System variable cấu hình hành vi server hoặc session. Có thể đọc:

~~~sql
SELECT @@session.time_zone;
SELECT @@session.sql_mode;
~~~

Một số system variable có thể được gán theo phạm vi:

~~~sql
SET SESSION time_zone = '+07:00';
~~~

SET SESSION thay đổi giá trị cho connection hiện tại. SET GLOBAL thay đổi giá trị global theo quy tắc và quyền của MySQL; không đồng nghĩa với gán biến cục bộ trong stored routine. Việc một thay đổi có tồn tại sau khi restart hay không còn phụ thuộc cách cấu hình và phiên bản.

## 6. SELECT ... INTO dùng để nhận kết quả truy vấn

SELECT ... INTO lấy các biểu thức trong một hàng kết quả và gán lần lượt vào danh sách biến:

~~~sql
SELECT
    so.customer_id,
    so.total
INTO
    v_customer_id,
    v_total
FROM sales_orders AS so
WHERE so.order_id = p_order_id;
~~~

Ánh xạ dựa trên vị trí:

- Biểu thức thứ nhất gán vào v_customer_id.
- Biểu thức thứ hai gán vào v_total.

Tên alias của cột không quyết định biến đích. Số lượng biểu thức trong SELECT phải khớp số lượng biến trong INTO.

### 6.1. INTO không trả result set cho caller

SELECT thông thường gửi result set về client:

~~~sql
SELECT so.total
FROM sales_orders AS so
WHERE so.order_id = 1001;
~~~

SELECT ... INTO gán dữ liệu cho biến và không gửi hàng kết quả đó như một result set thông thường:

~~~sql
SELECT so.total
INTO v_total
FROM sales_orders AS so
WHERE so.order_id = 1001;
~~~

Đây là khác biệt quan trọng khi viết stored procedure. Nếu muốn caller nhận dữ liệu, có thể dùng tham số OUT hoặc một SELECT riêng sau khi xử lý. Không nhầm SELECT ... INTO với SELECT dùng để trả danh sách hàng cho ứng dụng.

### 6.2. Vị trí của INTO

MySQL cho phép đặt INTO sau select list và trước FROM:

~~~sql
SELECT so.total
INTO v_total
FROM sales_orders AS so
WHERE so.order_id = p_order_id;
~~~

hoặc đặt sau phần FROM/WHERE:

~~~sql
SELECT so.total
FROM sales_orders AS so
WHERE so.order_id = p_order_id
INTO v_total;
~~~

Trong bài viết, ưu tiên cách đặt INTO ngay sau select list để dễ nhìn ánh xạ biến. Dùng nhất quán một phong cách trong cùng codebase.

## 7. SELECT ... INTO phải xử lý số hàng trả về

SELECT ... INTO không phải cách lấy tùy ý một hàng từ nhiều hàng. Kết quả phải có đúng một hàng để việc gán là không mơ hồ.

| Số hàng truy vấn trả về | Hành vi |
|---|---|
| 0 hàng | Phát sinh cảnh báo No data; trong stored program điều kiện NOT FOUND có thể được xử lý bởi handler. Biến đích không được gán giá trị mới. |
| 1 hàng | Gán các biểu thức vào các biến theo thứ tự. |
| Nhiều hơn 1 hàng | Phát sinh lỗi 1172: Result consisted of more than one row. |

Đây là quy tắc cốt lõi khi dùng SELECT ... INTO. Luôn xác định cardinality bằng khóa duy nhất, aggregate, điều kiện lọc hoặc một chiến lược chọn hàng có thứ tự.

### 7.1. Trường hợp 0 hàng: biến giữ giá trị cũ

Giả sử biến đang có giá trị 99:

~~~sql
SET v_total = 99.00;

SELECT so.total
INTO v_total
FROM sales_orders AS so
WHERE so.order_id = 999999999;
~~~

Nếu không có hàng phù hợp, SELECT ... INTO không gán NULL vào v_total; biến giữ giá trị cũ và phát sinh cảnh báo No data. Nếu code tiếp tục dùng v_total như thể truy vấn thành công, có thể xử lý nhầm đơn hàng trước đó.

Vì vậy, hãy khởi tạo biến trước truy vấn và xử lý NOT FOUND rõ ràng. Không dùng giá trị còn lại trong biến để suy đoán truy vấn có tìm thấy hàng hay không.

### 7.2. Trường hợp nhiều hàng: không dựa vào hàng đầu tiên

Truy vấn sau có thể trả nhiều hàng:

~~~sql
SELECT so.total
INTO v_total
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id;
~~~

Nếu một khách hàng có nhiều đơn, câu lệnh phát sinh lỗi 1172. MySQL không tự chọn hàng đầu tiên theo thứ tự vật lý.

Nếu nghiệp vụ cần tổng doanh thu, dùng aggregate:

~~~sql
SELECT COALESCE(SUM(so.total), 0)
INTO v_total
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id;
~~~

Nếu nghiệp vụ cần đơn mới nhất, phải xác định thứ tự và giới hạn:

~~~sql
SELECT so.total
INTO v_total
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id
ORDER BY so.created_at DESC, so.order_id DESC
LIMIT 1;
~~~

ORDER BY có khóa duy nhất làm tie-breaker giúp việc chọn hàng có tính xác định. LIMIT 1 là quyết định nghiệp vụ: lấy đúng một hàng theo thứ tự đã nêu, không phải cách che giấu lỗi cardinality khi truy vấn đáng lẽ phải trả một hàng duy nhất.

## 8. Xử lý NOT FOUND trong stored program

Khi SELECT ... INTO không tìm thấy hàng, MySQL phát sinh điều kiện NOT FOUND (SQLSTATE class 02). Trong stored program, có thể khai báo handler để xử lý trường hợp này.

Ví dụ procedure trả về cả giá trị và cờ cho biết có tìm thấy đơn hàng:

~~~sql
DELIMITER //

CREATE PROCEDURE get_order_total(
    IN p_order_id BIGINT UNSIGNED,
    OUT p_found BOOLEAN,
    OUT p_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_total DECIMAL(13, 2) DEFAULT NULL;
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_not_found = TRUE;

    SET p_found = FALSE;
    SET p_total = NULL;

    SELECT so.total
      INTO v_total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;

    IF v_not_found = FALSE THEN
        SET p_found = TRUE;
        SET p_total = v_total;
    END IF;
END//

DELIMITER ;
~~~

Nếu order_id không tồn tại:

- Handler CONTINUE bắt điều kiện NOT FOUND và đặt v_not_found = TRUE.
- Luồng thực thi tiếp tục sau câu SELECT ... INTO.
- p_found giữ FALSE và p_total giữ NULL như đã khởi tạo.

Nếu tìm thấy đúng một hàng:

- Handler không chạy.
- v_not_found vẫn FALSE.
- p_found được đặt TRUE và p_total nhận total.

Vì order_id là PRIMARY KEY, truy vấn không thể trả nhiều hơn một hàng. Nếu thay điều kiện bằng customer_id không duy nhất, lỗi 1172 vẫn cần được xử lý riêng; NOT FOUND handler không bắt lỗi nhiều hàng.

### 8.1. Vì sao phải khởi tạo biến và cờ?

Biến đích của SELECT ... INTO không được gán lại khi không có hàng. Nếu tái sử dụng biến mà không đặt lại cờ và giá trị trước truy vấn, kết quả của lần gọi trước có thể bị hiểu nhầm là kết quả của lần gọi hiện tại.

Mẫu an toàn:

1. Đặt cờ found = FALSE.
2. Đặt biến kết quả về giá trị mặc định có ý nghĩa, thường là NULL.
3. Thực hiện SELECT ... INTO.
4. Dùng handler NOT FOUND để đánh dấu không có hàng.
5. Chỉ sử dụng giá trị truy vấn khi cờ cho biết đã tìm thấy.

### 8.2. Giới hạn phạm vi của handler

Handler có phạm vi block. Trong routine lớn, nên đặt truy vấn cần xử lý NOT FOUND trong một block BEGIN ... END riêng nếu routine còn có các thao tác khác cũng có thể phát sinh NOT FOUND.

Ví dụ:

~~~sql
BEGIN
    DECLARE v_found BOOLEAN DEFAULT TRUE;
    DECLARE v_total DECIMAL(13, 2) DEFAULT NULL;

    BEGIN
        DECLARE v_not_found BOOLEAN DEFAULT FALSE;
        DECLARE CONTINUE HANDLER FOR NOT FOUND
            SET v_not_found = TRUE;

        SELECT so.total
          INTO v_total
        FROM sales_orders AS so
        WHERE so.order_id = p_order_id;

        IF v_not_found THEN
            SET v_found = FALSE;
        END IF;
    END;

    IF v_found THEN
        SET p_total = v_total;
    ELSE
        SET p_total = NULL;
    END IF;
END
~~~

Trong ví dụ, p_total là tham số OUT của routine bao ngoài. Handler ở block trong chỉ bao quanh thao tác có chủ đích. Điều này giúp tránh bắt nhầm NOT FOUND của một thao tác khác trong block lớn.

## 9. SELECT aggregate ... INTO

Aggregate không có GROUP BY thường trả một hàng ngay cả khi không có hàng nguồn:

~~~sql
SELECT
    COUNT(*),
    SUM(so.total),
    AVG(so.total)
INTO
    v_order_count,
    v_sum_total,
    v_average_total
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id;
~~~

Nếu khách hàng chưa có đơn:

- COUNT(*) trả 0.
- SUM(total) trả NULL.
- AVG(total) trả NULL.

Do đó, biến đích vẫn được gán từ một hàng aggregate, nhưng một số biểu thức có thể mang NULL.

Nếu nghiệp vụ muốn tổng bằng 0 khi không có đơn, dùng COALESCE:

~~~sql
SELECT
    COUNT(*),
    COALESCE(SUM(so.total), 0),
    COALESCE(AVG(so.total), 0)
INTO
    v_order_count,
    v_sum_total,
    v_average_total
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id;
~~~

Không nhầm hai trường hợp:

- SELECT ... INTO không có hàng nguồn và không có aggregate: điều kiện NOT FOUND xảy ra; biến giữ giá trị cũ.
- SELECT aggregate không GROUP BY: vẫn có một hàng kết quả; COUNT có thể là 0 và SUM/AVG có thể là NULL.

Nếu có GROUP BY, truy vấn có thể trả nhiều hàng hoặc không có nhóm nào. Khi đó phải áp dụng quy tắc cardinality như SELECT ... INTO thông thường.

## 10. So sánh SELECT ... INTO với SET (SELECT ...)

Có thể gán kết quả scalar subquery bằng SET:

~~~sql
SET v_total = (
    SELECT so.total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id
);
~~~

Đây là scalar subquery trong biểu thức. Hành vi khi số hàng khác một có điểm khác SELECT ... INTO:

| Tình huống | SELECT ... INTO | SET v = (SELECT ...) |
|---|---|---|
| 1 hàng | Gán giá trị | Gán giá trị |
| 0 hàng | NOT FOUND/No data; biến giữ giá trị cũ | Scalar subquery trả NULL; biến được gán NULL |
| Nhiều hàng | Lỗi 1172 | Lỗi scalar subquery trả nhiều hơn một hàng |

Khác biệt ở trường hợp 0 hàng rất quan trọng. Nếu muốn biến trở thành NULL khi không có hàng, SET với scalar subquery có thể biểu đạt điều đó trực tiếp. Nếu cần phân biệt không tìm thấy với tìm thấy giá trị NULL, cần một cờ found hoặc một cách truy vấn rõ ràng hơn.

Không chọn cú pháp chỉ vì ngắn hơn. Hãy chọn theo ý nghĩa mong muốn khi không có hàng và cách routine cần xử lý trạng thái.

### 10.1. Dùng COALESCE khi cần giá trị mặc định

~~~sql
SET v_total = COALESCE(
    (
        SELECT so.total
        FROM sales_orders AS so
        WHERE so.order_id = p_order_id
    ),
    0
);
~~~

Biểu thức trên gán 0 nếu scalar subquery trả NULL, bao gồm cả trường hợp không tìm thấy hàng và trường hợp hàng tồn tại nhưng total là NULL. Nếu hai trường hợp có ý nghĩa nghiệp vụ khác nhau, không gộp chúng bằng COALESCE.

## 11. Gán nhiều cột từ một hàng

SELECT ... INTO hữu ích khi cần lấy nhiều thuộc tính của cùng một hàng:

~~~sql
SELECT
    so.customer_id,
    so.status_code,
    so.total,
    so.created_at
INTO
    v_customer_id,
    v_status_code,
    v_total,
    v_created_at
FROM sales_orders AS so
WHERE so.order_id = p_order_id;
~~~

Số biểu thức phải khớp số biến đích. Kiểu dữ liệu của từng biểu thức phải tương thích với kiểu biến tương ứng.

Để dễ bảo trì:

- Viết danh sách SELECT và INTO theo cùng thứ tự.
- Mỗi cặp biểu thức/biến nên nằm trên một dòng tương ứng.
- Dùng alias bảng cho tất cả cột.
- Dùng tiền tố v_ cho biến và p_ cho tham số.
- Không dựa vào thứ tự cột của SELECT *.

Không dùng SELECT * INTO nhiều biến vì schema có thể thay đổi số lượng hoặc thứ tự cột, làm routine lỗi hoặc ánh xạ sai.

## 12. Quy tắc chuyển đổi kiểu khi gán

Biểu thức nguồn không nhất thiết có cùng kiểu với biến đích. MySQL chuyển đổi giá trị theo kiểu của biến và ngữ cảnh SQL.

Ví dụ:

~~~sql
DECLARE v_order_count INT DEFAULT 0;
DECLARE v_total DECIMAL(13, 2) DEFAULT 0;
DECLARE v_label VARCHAR(30) DEFAULT '';

SET v_order_count = '12';
SET v_total = '1250.75';
SET v_label = 2026;
~~~

MySQL có thể chuyển chuỗi số thành số và số thành chuỗi. Tuy nhiên, không nên dựa vào chuyển đổi ngầm nếu định dạng hoặc độ chính xác quan trọng. Hãy CAST hoặc CONVERT tường minh khi cần:

~~~sql
SET v_total = CAST(p_input_total AS DECIMAL(13, 2));
SET v_label = CAST(p_year AS CHAR(4));
~~~

### 12.1. DECIMAL và làm tròn

Biến DECIMAL có precision và scale xác định. Khi gán giá trị có nhiều chữ số thập phân hơn scale của biến, MySQL có thể làm tròn hoặc phát sinh cảnh báo/lỗi tùy giá trị, ngữ cảnh và SQL mode.

~~~sql
BEGIN
    DECLARE v_amount DECIMAL(8, 2) DEFAULT 0;
    SET v_amount = 12.3456;
END
~~~

Nếu nghiệp vụ yêu cầu quy tắc làm tròn cụ thể, hãy áp dụng ROUND() với scale rõ ràng trước khi gán:

~~~sql
SET v_amount = ROUND(p_amount, 2);
~~~

Không mặc định mọi hệ thống đều dùng cùng một SQL mode. Kiểm tra @@SESSION.sql_mode khi điều tra khác biệt giữa môi trường development, test và production.

### 12.2. Giá trị vượt miền kiểu dữ liệu

Biến INT không thể lưu mọi giá trị BIGINT; DECIMAL(8,2) không thể biểu diễn số có phần nguyên vượt giới hạn precision; VARCHAR(30) không thể giữ nguyên chuỗi dài hơn giới hạn.

Kết quả chuyển đổi có thể là warning hoặc error tùy SQL mode và trường hợp. Với routine xử lý dữ liệu tài chính hoặc dữ liệu định danh, nên:

- Khai báo kiểu đích đủ miền giá trị.
- Validate giá trị trước khi gán.
- CAST tường minh khi cần.
- Kiểm tra warning và lỗi trong môi trường thử nghiệm.
- Không dựa vào hành vi cắt cụt dữ liệu.

### 12.3. NULL và giá trị mặc định

Biến cục bộ chưa có DEFAULT được khởi tạo với NULL. Có thể khai báo giá trị mặc định:

~~~sql
BEGIN
    DECLARE v_retry_count INT DEFAULT 0;
    DECLARE v_result DECIMAL(13, 2) DEFAULT NULL;
    DECLARE v_message VARCHAR(100) DEFAULT 'Chưa xử lý';
END
~~~

Giá trị mặc định giúp routine có trạng thái ban đầu rõ ràng. Tuy nhiên, DEFAULT không thay thế việc kiểm tra kết quả truy vấn; SELECT ... INTO không có hàng vẫn cần xử lý NOT FOUND nếu routine cần phân biệt trường hợp đó.

## 13. SET biến và UPDATE cột là hai thao tác khác nhau

SET trong stored program có thể gán biến:

~~~sql
SET v_status = 2;
~~~

SET trong UPDATE dùng để cập nhật cột của bảng:

~~~sql
UPDATE sales_orders AS so
SET status_code = 2
WHERE so.order_id = p_order_id;
~~~

Hai câu lệnh không thay thế nhau:

- SET v_status = 2 chỉ thay đổi biến trong routine.
- UPDATE ... SET status_code = 2 thay đổi dữ liệu trong bảng và chịu ảnh hưởng của transaction, lock, trigger và constraint.

Nếu SELECT ... INTO lấy trạng thái hiện tại vào biến, việc cập nhật bảng vẫn cần một câu UPDATE riêng:

~~~sql
SELECT so.status_code
INTO v_status
FROM sales_orders AS so
WHERE so.order_id = p_order_id;

SET v_next_status = v_status + 1;

UPDATE sales_orders AS so
SET status_code = v_next_status
WHERE so.order_id = p_order_id;
~~~

Đoạn minh họa trên giả định hàng tồn tại và không có cạnh tranh cập nhật. Trong ứng dụng đồng thời, đọc rồi cập nhật theo hai câu riêng có thể bị race condition; cần transaction, khóa phù hợp hoặc UPDATE có điều kiện nguyên tử tùy nghiệp vụ. Chủ đề này không được giải quyết chỉ bằng quy tắc gán biến.

## 14. Tránh tên biến trùng tên cột

Stored routine cho phép tên biến và tên cột có thể giống nhau, nhưng điều đó dễ làm câu SQL khó đọc và dẫn đến tham chiếu nhầm.

Trong stored program, tên biến cục bộ có thể che khuất tên cột không được định danh rõ ràng trong một số ngữ cảnh phân giải tên. Vì vậy, không nên dựa vào việc MySQL tự suy đoán tên total đang chỉ biến hay cột.

Ví dụ dễ gây nhầm:

~~~sql
BEGIN
    DECLARE total DECIMAL(13, 2) DEFAULT 0;

    SELECT total
    INTO total
    FROM sales_orders
    WHERE order_id = p_order_id;
END
~~~

Tên total xuất hiện cả ở phía cột và biến đích. Cách viết rõ ràng hơn:

~~~sql
BEGIN
    DECLARE v_total DECIMAL(13, 2) DEFAULT 0;

    SELECT so.total
    INTO v_total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;
END
~~~

Quy ước đặt tên nên thống nhất:

| Thành phần | Quy ước ví dụ |
|---|---|
| Tham số | p_order_id |
| Biến cục bộ | v_total |
| Alias bảng | so |
| Cột | so.total |
| User variable | @caller_total |

Không dùng tên biến trùng với tên cột, kể cả khi câu SQL hiện tại vẫn biên dịch. Một thay đổi schema hoặc thêm một cột mới có thể làm code trở nên khó phân tích hơn.

## 15. Quy trình gán kết quả an toàn

Trước khi viết SELECT ... INTO, trả lời bốn câu hỏi:

1. Truy vấn có thể trả về bao nhiêu hàng?
2. Nếu không có hàng, biến cần giữ giá trị cũ, trở thành NULL hay báo lỗi nghiệp vụ?
3. Nếu có nhiều hàng, cần aggregate, chọn một hàng có thứ tự hay đây là lỗi dữ liệu?
4. Kiểu của từng biểu thức có tương thích với biến đích không?

Sau đó chọn cách gán:

| Nhu cầu | Cách phù hợp |
|---|---|
| Gán literal hoặc biểu thức | SET |
| Gán nhiều biến từ các biểu thức đã biết | SET nhiều biến |
| Lấy một hàng duy nhất từ bảng | SELECT ... INTO với khóa duy nhất |
| Lấy một hàng theo thứ tự nghiệp vụ | SELECT ... INTO kết hợp ORDER BY và LIMIT 1 |
| Lấy tổng hợp | Aggregate SELECT ... INTO |
| Không có hàng phải trở thành NULL | SET với scalar subquery hoặc xử lý NOT FOUND tường minh |
| Caller cần nhận kết quả | OUT/INOUT hoặc result set SELECT riêng |
| Cần giữ trạng thái chỉ trong routine | Local variable |
| Cần chia sẻ giá trị trong cùng session | User variable, dùng có kiểm soát |

## 16. Ví dụ tổng hợp: lấy dữ liệu và tính toán

Procedure sau lấy thông tin đơn hàng, tính thuế và trả kết quả. Ví dụ xử lý không tìm thấy hàng bằng handler:

~~~sql
DELIMITER //

CREATE PROCEDURE quote_order(
    IN p_order_id BIGINT UNSIGNED,
    IN p_tax_rate DECIMAL(5, 2),
    OUT p_found BOOLEAN,
    OUT p_subtotal DECIMAL(13, 2),
    OUT p_tax DECIMAL(13, 2),
    OUT p_grand_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_subtotal DECIMAL(13, 2) DEFAULT NULL;
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_not_found = TRUE;

    SET p_found = FALSE;
    SET p_subtotal = NULL;
    SET p_tax = NULL;
    SET p_grand_total = NULL;

    SELECT so.total
      INTO v_subtotal
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;

    IF v_not_found = FALSE THEN
        SET p_found = TRUE;
        SET p_subtotal = v_subtotal;
        SET p_tax = ROUND(v_subtotal * p_tax_rate / 100, 2);
        SET p_grand_total = p_subtotal + p_tax;
    END IF;
END//

DELIMITER ;
~~~

Gọi procedure:

~~~sql
CALL quote_order(
    1001,
    8.00,
    @found,
    @subtotal,
    @tax,
    @grand_total
);

SELECT @found, @subtotal, @tax, @grand_total;
~~~

Nếu order_id không tồn tại, @found là FALSE và các giá trị tiền là NULL. Nếu tìm thấy, routine gán lần lượt subtotal, tax và grand_total.

Ví dụ minh họa cách gán biến, không thay thế kiểm tra quy tắc thuế, tiền tệ, làm tròn hoặc quyền truy cập trong hệ thống thực tế.

## 17. Các lỗi thường gặp khi gán kết quả

| Lỗi/tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| 1329 No data | SELECT ... INTO không tìm thấy hàng | Khởi tạo biến/cờ và xử lý NOT FOUND |
| 1172 Result consisted of more than one row | SELECT ... INTO trả nhiều hàng | Dùng khóa duy nhất, aggregate hoặc ORDER BY ... LIMIT 1 theo nghiệp vụ |
| 1242 Subquery returns more than 1 row | Scalar subquery trong SET trả nhiều hàng | Sửa điều kiện, aggregate hoặc chọn một hàng có thứ tự |
| 1327 Undeclared variable | Biến chưa DECLARE hoặc sai scope/tên | Kiểm tra khai báo và phạm vi block |
| Giá trị NULL ngoài dự kiến | Biểu thức nguồn là NULL hoặc scalar subquery không có hàng | Kiểm tra NULL và quy tắc mặc định |
| Giá trị cũ được dùng lại | SELECT ... INTO không có hàng nên biến không đổi | Reset biến và cờ trước mỗi lần truy vấn |
| Cảnh báo/lỗi chuyển đổi | Kiểu đích không phù hợp, mất precision hoặc vượt miền | Khai báo kiểu đúng, validate, CAST và kiểm tra SQL mode |
| Kết quả không xác định | Gán user variable và đọc lại nó trong cùng SELECT | Dùng SET riêng hoặc logic biến cục bộ |

### 17.1. SELECT ... INTO không tìm thấy hàng

~~~sql
BEGIN
    DECLARE v_total DECIMAL(13, 2) DEFAULT 0;

    SELECT so.total
    INTO v_total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;

    SET p_result = v_total;
END
~~~

Nếu không tìm thấy đơn, v_total có thể vẫn là 0 hoặc giá trị đã có trước đó. Nếu code không kiểm tra NOT FOUND, p_result có thể nhận giá trị không phản ánh truy vấn hiện tại.

### 17.2. Dùng LIMIT 1 để che lỗi dữ liệu

~~~sql
SELECT so.status_code
INTO v_status
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id
LIMIT 1;
~~~

Truy vấn này tránh lỗi nhiều hàng, nhưng không có ORDER BY nên hàng được chọn không có thứ tự nghiệp vụ xác định. Nếu thật sự cần đơn gần nhất:

~~~sql
SELECT so.status_code
INTO v_status
FROM sales_orders AS so
WHERE so.customer_id = p_customer_id
ORDER BY so.created_at DESC, so.order_id DESC
LIMIT 1;
~~~

Nếu nghiệp vụ yêu cầu customer_id chỉ có đúng một đơn đang hoạt động, hãy bảo đảm điều kiện đó bằng constraint hoặc thiết kế dữ liệu và để lỗi nhiều hàng bộc lộ sai lệch. Đừng thêm LIMIT 1 chỉ để che vi phạm quy tắc dữ liệu.

## 18. Bài thực hành

### 18.1. Chuẩn bị dữ liệu

~~~sql
INSERT INTO sales_orders (
    order_id,
    customer_id,
    status_code,
    total,
    created_at
)
VALUES
    (1001, 501, 1, 1200.00, '2026-01-10 09:00:00'),
    (1002, 501, 2, 800.00,  '2026-01-12 10:00:00'),
    (1003, 502, 1, 250.00,  '2026-01-13 11:00:00');
~~~

### 18.2. Thực hành SET

~~~sql
DELIMITER //

CREATE PROCEDURE demo_set_assignment(
    IN p_quantity INT,
    IN p_unit_price DECIMAL(13, 2),
    OUT p_line_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_discount DECIMAL(13, 2) DEFAULT 0;
    DECLARE v_gross DECIMAL(13, 2) DEFAULT 0;

    SET v_gross = p_quantity * p_unit_price;
    SET v_discount = ROUND(v_gross * 0.05, 2);
    SET p_line_total = v_gross - v_discount;
END//

DELIMITER ;

CALL demo_set_assignment(3, 100.00, @line_total);
SELECT @line_total;
~~~

Kết quả mong đợi là 285.00: tổng gộp 300.00, chiết khấu 15.00.

### 18.3. Thực hành SELECT ... INTO với khóa duy nhất

~~~sql
DELIMITER //

CREATE PROCEDURE demo_select_into(
    IN p_order_id BIGINT UNSIGNED,
    OUT p_customer_id BIGINT UNSIGNED,
    OUT p_total DECIMAL(13, 2)
)
BEGIN
    SELECT so.customer_id, so.total
      INTO p_customer_id, p_total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;
END//

DELIMITER ;

CALL demo_select_into(1001, @customer_id, @order_total);
SELECT @customer_id, @order_total;
~~~

Với dữ liệu mẫu, kết quả là customer_id = 501 và total = 1200.00.

### 18.4. Thực hành xử lý không tìm thấy hàng

~~~sql
DELIMITER //

CREATE PROCEDURE demo_not_found(
    IN p_order_id BIGINT UNSIGNED,
    OUT p_found BOOLEAN,
    OUT p_total DECIMAL(13, 2)
)
BEGIN
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE v_total DECIMAL(13, 2) DEFAULT NULL;

    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_not_found = TRUE;

    SET p_found = FALSE;
    SET p_total = NULL;

    SELECT so.total
      INTO v_total
    FROM sales_orders AS so
    WHERE so.order_id = p_order_id;

    IF NOT v_not_found THEN
        SET p_found = TRUE;
        SET p_total = v_total;
    END IF;
END//

DELIMITER ;

CALL demo_not_found(999999, @found, @total);
SELECT @found, @total;
~~~

Kết quả mong đợi: @found = 0 và @total là NULL. Thử lại với order_id = 1001 để thấy nhánh tìm thấy hàng.

### 18.5. Câu hỏi tự kiểm tra

1. Vì sao SET phù hợp để gán kết quả biểu thức còn SELECT ... INTO phù hợp để nhận dữ liệu truy vấn?
2. SELECT ... INTO trả 0 hàng thì biến đích có tự động thành NULL không?
3. Điều gì xảy ra nếu SELECT ... INTO trả 2 hàng?
4. Khi nào nên dùng aggregate thay vì LIMIT 1?
5. Vì sao LIMIT 1 cần ORDER BY nếu muốn chọn hàng mới nhất?
6. User variable khác local variable ở phạm vi sống như thế nào?
7. Vì sao không nên gán và đọc cùng một user variable trong các biểu thức của cùng SELECT?
8. Khi nào SET với scalar subquery có hành vi khác SELECT ... INTO?

## 19. Quy tắc thiết kế nên áp dụng

- Khai báo biến cục bộ ở đầu block và chọn kiểu dữ liệu đủ miền giá trị.
- Dùng tiền tố v_ cho local variable và p_ cho tham số.
- Dùng alias bảng khi tham chiếu cột; tránh tên biến trùng tên cột.
- Dùng SET cho phép tính và gán giá trị rõ ràng.
- Dùng SELECT ... INTO khi truy vấn dự kiến trả đúng một hàng hoặc một hàng aggregate.
- Xác định cardinality bằng PRIMARY KEY, UNIQUE, aggregate hoặc điều kiện nghiệp vụ.
- Nếu chọn một hàng từ tập nhiều hàng, dùng ORDER BY có tie-breaker và LIMIT 1.
- Khởi tạo biến và cờ trước SELECT ... INTO nếu truy vấn có thể không tìm thấy hàng.
- Dùng NOT FOUND handler khi cần phân biệt không tìm thấy với một giá trị NULL.
- Không dùng LIMIT 1 để che dữ liệu vi phạm tính duy nhất.
- Dùng CAST/CONVERT hoặc ROUND khi cần kiểm soát chuyển đổi kiểu và precision.
- Hạn chế user variable trong logic routine; không phụ thuộc thứ tự đánh giá biểu thức SELECT.
- Phân biệt SET biến cục bộ với UPDATE cột bảng.

## 20. Checklist trước khi hoàn tất routine

- [ ] Mọi local variable đã được DECLARE trước câu lệnh thực thi.
- [ ] Kiểu dữ liệu, precision và scale của biến phù hợp dữ liệu nhận vào.
- [ ] Tên biến và tham số không gây nhầm với tên cột.
- [ ] SET được dùng cho phép gán và tính toán nội bộ.
- [ ] SELECT ... INTO có danh sách cột và biến đích tương ứng từng vị trí.
- [ ] Truy vấn SELECT ... INTO có cardinality được xác định.
- [ ] Trường hợp 0 hàng đã được xử lý bằng NOT FOUND hoặc cách phù hợp.
- [ ] Biến được khởi tạo trước truy vấn có thể không tìm thấy hàng.
- [ ] Trường hợp nhiều hàng không bị che giấu bằng LIMIT 1 tùy tiện.
- [ ] Aggregate và NULL được xử lý đúng nghiệp vụ.
- [ ] Chuyển đổi kiểu, làm tròn và SQL mode đã được cân nhắc.
- [ ] Không dựa vào thứ tự đánh giá phép gán user variable trong SELECT.
- [ ] OUT/INOUT được gán giá trị rõ ràng trước khi trả về.
- [ ] Đã kiểm tra cả trường hợp tìm thấy, không tìm thấy và dữ liệu bất thường.

## Kết luận

SET và SELECT ... INTO là hai công cụ nền tảng để gán kết quả trong stored program MySQL. SET phù hợp với literal, tham số và biểu thức tính toán; SELECT ... INTO phù hợp để đưa giá trị của một hàng truy vấn vào các biến.

Điểm quan trọng nhất là kiểm soát cardinality và trạng thái biến. SELECT ... INTO không có hàng sẽ không tự xóa giá trị cũ; nhiều hàng sẽ gây lỗi. Vì vậy, routine cần xác định rõ trường hợp không tìm thấy, dùng NOT FOUND handler khi phù hợp, bảo đảm truy vấn trả đúng một hàng hoặc chủ động aggregate/chọn hàng có thứ tự.

Khi kết hợp kiểu dữ liệu chính xác, quy ước tên rõ ràng, kiểm soát NULL và chuyển đổi kiểu, logic stored program sẽ dễ đọc, dễ kiểm thử và ít phát sinh lỗi dữ liệu ngoài dự kiến.

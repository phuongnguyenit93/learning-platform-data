# IF, ELSIF, CASE và nhánh điều kiện

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** PL/SQL cơ bản  
> **Mục tiêu:** Sử dụng các cấu trúc điều kiện trong PL/SQL để điều khiển luồng thực thi: IF, ELSIF, ELSE, CASE statement và CASE expression. Hiểu cách Oracle đánh giá điều kiện TRUE/FALSE/NULL, cách sắp xếp thứ tự nhánh, cách xử lý giá trị NULL, lựa chọn giữa IF và CASE, và áp dụng vào kiểm tra dữ liệu, tính toán nghiệp vụ, DML và truy vấn SQL.

## 1. Điều khiển luồng bằng điều kiện

Một chương trình thường phải chọn hành động tùy dữ liệu đầu vào hoặc trạng thái hiện tại. Ví dụ:

- Nếu số dư đủ, cho phép rút tiền; nếu không đủ, từ chối.
- Nếu điểm đạt ngưỡng cao, xếp loại A; nếu đạt ngưỡng thấp hơn, xếp loại B.
- Nếu đơn hàng đã thanh toán, chuyển sang bước giao hàng; nếu chưa, chờ thanh toán.
- Nếu một biến chưa có giá trị, yêu cầu bổ sung dữ liệu.
- Nếu nhiều điều kiện cùng có thể đúng, chọn nhánh theo thứ tự ưu tiên.

Trong PL/SQL, hai nhóm cấu trúc thường dùng là:

1. **IF statement:** thực thi một khối lệnh khi điều kiện đúng; có thể có ELSIF và ELSE.
2. **CASE:** chọn một nhánh. CASE statement điều khiển luồng trong PL/SQL; CASE expression trả về một giá trị để dùng trong biểu thức hoặc câu SQL.

Ví dụ IF:

~~~sql
DECLARE
    l_balance NUMBER := 500;
    l_withdrawal NUMBER := 200;
BEGIN
    IF l_balance >= l_withdrawal THEN
        DBMS_OUTPUT.PUT_LINE('Withdrawal allowed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Insufficient balance');
    END IF;
END;
/
~~~

Ví dụ CASE statement:

~~~sql
DECLARE
    l_status VARCHAR2(20) := 'PAID';
BEGIN
    CASE l_status
        WHEN 'NEW' THEN
            DBMS_OUTPUT.PUT_LINE('Waiting for payment');
        WHEN 'PAID' THEN
            DBMS_OUTPUT.PUT_LINE('Ready for fulfillment');
        WHEN 'CANCELLED' THEN
            DBMS_OUTPUT.PUT_LINE('Order cancelled');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Unknown status');
    END CASE;
END;
/
~~~

Điều kiện không chỉ giúp chương trình có nhiều nhánh. Nó còn làm rõ quy tắc nghiệp vụ, xử lý dữ liệu biên và ngăn thao tác không hợp lệ trước khi thực hiện DML.

## 2. IF statement

Cú pháp tổng quát:

~~~sql
IF condition THEN
    statements;
END IF;
~~~

Nếu condition là TRUE, Oracle thực thi các câu lệnh giữa THEN và END IF. Nếu condition là FALSE hoặc NULL, khối lệnh bị bỏ qua.

Ví dụ:

~~~sql
DECLARE
    l_score NUMBER := 85;
BEGIN
    IF l_score >= 50 THEN
        DBMS_OUTPUT.PUT_LINE('Passed');
    END IF;
END;
/
~~~

Nếu L_SCORE là 40, thông báo không được in. Nếu L_SCORE là NULL, biểu thức L_SCORE >= 50 có kết quả UNKNOWN/NULL và khối THEN cũng không chạy.

### 2.1. IF với ELSE

Dùng ELSE khi cần định nghĩa hành động cho mọi trường hợp còn lại:

~~~sql
IF condition THEN
    statements_if_true;
ELSE
    statements_if_not_true;
END IF;
~~~

Ví dụ:

~~~sql
DECLARE
    l_quantity NUMBER := 0;
BEGIN
    IF l_quantity > 0 THEN
        DBMS_OUTPUT.PUT_LINE('In stock');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No available quantity');
    END IF;
END;
/
~~~

Lưu ý: ELSE được thực thi khi điều kiện không TRUE, bao gồm cả FALSE và NULL. Nếu NULL có ý nghĩa riêng, phải kiểm tra nó thành một nhánh riêng.

### 2.2. IF với ELSIF

Khi có nhiều trường hợp, dùng ELSIF:

~~~sql
IF condition_1 THEN
    statements_1;
ELSIF condition_2 THEN
    statements_2;
ELSIF condition_3 THEN
    statements_3;
ELSE
    statements_default;
END IF;
~~~

Oracle kiểm tra các điều kiện theo thứ tự từ trên xuống. Nhánh đầu tiên có điều kiện TRUE được thực thi; những nhánh phía sau bị bỏ qua.

Ví dụ xếp loại:

~~~sql
DECLARE
    l_score NUMBER := 82;
    l_grade VARCHAR2(2);
BEGIN
    IF l_score >= 90 THEN
        l_grade := 'A';
    ELSIF l_score >= 80 THEN
        l_grade := 'B';
    ELSIF l_score >= 70 THEN
        l_grade := 'C';
    ELSIF l_score >= 60 THEN
        l_grade := 'D';
    ELSE
        l_grade := 'F';
    END IF;

    DBMS_OUTPUT.PUT_LINE('Grade = ' || l_grade);
END;
/
~~~

Với điểm 82, điều kiện đầu tiên FALSE, điều kiện thứ hai TRUE nên L_GRADE nhận B. Oracle không tiếp tục kiểm tra các nhánh còn lại.

### 2.3. ELSIF viết liền một từ

Từ khóa đúng trong PL/SQL là **ELSIF**:

~~~sql
ELSIF l_score >= 80 THEN
~~~

Không viết ELSEIF hoặc ELSE IF trong cùng cấu trúc IF. Mỗi ELSIF thêm một điều kiện cùng khối IF và chỉ có một END IF đóng toàn bộ cấu trúc.

### 2.4. Thứ tự điều kiện quyết định kết quả

Ví dụ sai thứ tự:

~~~sql
IF l_score >= 60 THEN
    l_grade := 'D';
ELSIF l_score >= 80 THEN
    l_grade := 'B';
ELSIF l_score >= 90 THEN
    l_grade := 'A';
END IF;
~~~

Nếu điểm là 95, điều kiện đầu tiên đã TRUE nên chương trình gán D. Các nhánh 80 và 90 không bao giờ được xét.

Sắp xếp lại từ ngưỡng cao xuống thấp:

~~~sql
IF l_score >= 90 THEN
    l_grade := 'A';
ELSIF l_score >= 80 THEN
    l_grade := 'B';
ELSIF l_score >= 60 THEN
    l_grade := 'D';
ELSE
    l_grade := 'F';
END IF;
~~~

Khi điều kiện có vùng bao phủ chồng lấn, hãy đặt nhánh cụ thể/ưu tiên cao trước. Nếu các điều kiện không chồng lấn, thứ tự vẫn nên phản ánh cách đọc nghiệp vụ.

## 3. Điều kiện BOOLEAN và giá trị NULL

Trong PL/SQL, một biểu thức điều kiện có thể mang ba trạng thái logic:

- TRUE
- FALSE
- NULL (UNKNOWN)

IF chỉ chạy nhánh THEN khi điều kiện là TRUE. FALSE và NULL đều không thỏa điều kiện.

Ví dụ:

~~~sql
DECLARE
    l_score NUMBER := NULL;
BEGIN
    IF l_score >= 50 THEN
        DBMS_OUTPUT.PUT_LINE('Passed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not passed');
    END IF;
END;
/
~~~

Kết quả là Not passed. Nhưng nếu NULL có nghĩa “chưa chấm điểm”, thông báo này chưa chính xác về nghiệp vụ.

### 3.1. Xử lý NULL thành nhánh riêng

~~~sql
DECLARE
    l_score NUMBER := NULL;
BEGIN
    IF l_score IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Score is not available');
    ELSIF l_score >= 50 THEN
        DBMS_OUTPUT.PUT_LINE('Passed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Failed');
    END IF;
END;
/
~~~

Kiểm tra NULL trước khi so sánh giúp chương trình phân biệt dữ liệu thiếu với dữ liệu có điểm thấp.

### 3.2. Không dùng phép bằng để kiểm tra NULL

Sai:

~~~sql
IF l_score = NULL THEN
    DBMS_OUTPUT.PUT_LINE('Missing');
END IF;
~~~

Đúng:

~~~sql
IF l_score IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('Missing');
END IF;
~~~

Trong PL/SQL, dùng IS NULL và IS NOT NULL cho biến nullable. Quy tắc này cũng áp dụng trong điều kiện SQL.

### 3.3. AND, OR và NOT với NULL

Logic ba giá trị ảnh hưởng đến biểu thức phức hợp:

| Biểu thức | Kết quả |
|---|---|
| TRUE AND NULL | NULL |
| FALSE AND NULL | FALSE |
| TRUE OR NULL | TRUE |
| FALSE OR NULL | NULL |
| NOT NULL | NULL |

Ví dụ:

~~~sql
DECLARE
    l_amount NUMBER := NULL;
BEGIN
    IF l_amount > 0 AND l_amount < 1000 THEN
        DBMS_OUTPUT.PUT_LINE('Within range');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not within range or missing');
    END IF;
END;
/
~~~

Điều kiện không TRUE nên ELSE chạy. Nếu cần phân biệt NULL với giá trị ngoài khoảng, hãy viết nhánh NULL riêng.

### 3.4. Biến BOOLEAN trong PL/SQL

PL/SQL hỗ trợ biến BOOLEAN:

~~~sql
DECLARE
    l_is_valid BOOLEAN;
BEGIN
    l_is_valid := TRUE;

    IF l_is_valid THEN
        DBMS_OUTPUT.PUT_LINE('Valid');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not valid');
    END IF;
END;
/
~~~

Một biến BOOLEAN có thể là TRUE, FALSE hoặc NULL. Khi chưa gán giá trị, biến BOOLEAN mặc định là NULL.

Không nhầm BOOLEAN trong PL/SQL với khả năng lưu hoặc truyền BOOLEAN qua SQL. Hỗ trợ kiểu BOOLEAN trong SQL phụ thuộc Oracle Database release; các phiên bản cũ không cho dùng BOOLEAN như kiểu cột SQL thông thường. Khi cần tương thích nhiều phiên bản, thường dùng NUMBER hoặc CHAR để lưu cờ trong bảng và chuyển đổi rõ ràng ở PL/SQL.

## 4. IF lồng nhau

Có thể đặt IF bên trong một nhánh IF khác để xử lý quy tắc nhiều tầng.

~~~sql
DECLARE
    l_is_member BOOLEAN := TRUE;
    l_order_total NUMBER := 1200;
BEGIN
    IF l_is_member THEN
        IF l_order_total >= 1000 THEN
            DBMS_OUTPUT.PUT_LINE('Member premium discount');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Member standard discount');
        END IF;
    ELSE
        IF l_order_total >= 1000 THEN
            DBMS_OUTPUT.PUT_LINE('Guest large-order offer');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Guest standard price');
        END IF;
    END IF;
END;
/
~~~

IF l_is_member là điều kiện bên ngoài; IF l_order_total là điều kiện bên trong nhánh được chọn.

### 4.1. Khi nào nên lồng IF?

IF lồng nhau phù hợp khi điều kiện bên trong chỉ có ý nghĩa sau khi điều kiện bên ngoài được thỏa mãn. Ví dụ chỉ kiểm tra quyền chi tiết sau khi xác định người dùng đã đăng nhập.

Tuy nhiên, nhiều tầng lồng nhau làm luồng khó đọc. Có thể dùng ELSIF, CASE hoặc tách thành procedure/function nhỏ nếu logic quá sâu.

### 4.2. Kiểm tra điều kiện theo thứ tự an toàn

Ví dụ kiểm tra biến trước khi sử dụng:

~~~sql
IF l_customer_id IS NOT NULL THEN
    IF l_credit_limit > 0 THEN
        -- Thực hiện xử lý tín dụng
        NULL;
    END IF;
END IF;
~~~

PL/SQL hỗ trợ short-circuit evaluation cho AND/OR trong biểu thức Boolean. Tuy nhiên, khi logic quan trọng hoặc có phép toán có thể lỗi, nên viết điều kiện rõ ràng và không dựa vào một biểu thức khó đọc để che giấu kiểm tra đầu vào.

## 5. CASE statement

CASE statement chọn một nhánh lệnh trong PL/SQL. Có hai dạng:

1. Simple CASE: so sánh một selector với các giá trị WHEN.
2. Searched CASE: đánh giá lần lượt các điều kiện WHEN.

CASE statement kết thúc bằng END CASE; khác với CASE expression chỉ kết thúc bằng END.

## 6. Simple CASE statement

Cú pháp:

~~~sql
CASE selector
    WHEN value_1 THEN
        statements_1;
    WHEN value_2 THEN
        statements_2;
    WHEN value_3 THEN
        statements_3;
    ELSE
        default_statements;
END CASE;
~~~

Oracle so sánh selector với từng giá trị WHEN. Khi tìm thấy nhánh khớp, thực thi nhánh đó rồi kết thúc CASE.

Ví dụ:

~~~sql
DECLARE
    l_payment_method VARCHAR2(20) := 'CARD';
BEGIN
    CASE l_payment_method
        WHEN 'CASH' THEN
            DBMS_OUTPUT.PUT_LINE('Collect cash');
        WHEN 'CARD' THEN
            DBMS_OUTPUT.PUT_LINE('Process card payment');
        WHEN 'BANK' THEN
            DBMS_OUTPUT.PUT_LINE('Verify bank transfer');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Unsupported payment method');
    END CASE;
END;
/
~~~

Simple CASE phù hợp khi nhiều nhánh cùng kiểm tra một biến hoặc biểu thức theo các giá trị cụ thể.

### 6.1. Simple CASE và NULL

Simple CASE dùng phép so sánh giữa selector và giá trị WHEN. NULL không bằng NULL trong phép so sánh thông thường, nên:

~~~sql
DECLARE
    l_status VARCHAR2(20) := NULL;
BEGIN
    CASE l_status
        WHEN 'OPEN' THEN
            DBMS_OUTPUT.PUT_LINE('Open');
        WHEN NULL THEN
            DBMS_OUTPUT.PUT_LINE('Missing');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Other');
    END CASE;
END;
/
~~~

Nhánh WHEN NULL không được chọn chỉ vì selector là NULL. Chương trình đi vào ELSE nếu có.

Nếu cần xử lý NULL, dùng searched CASE:

~~~sql
CASE
    WHEN l_status IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Missing');
    WHEN l_status = 'OPEN' THEN
        DBMS_OUTPUT.PUT_LINE('Open');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Other');
END CASE;
~~~

## 7. Searched CASE statement

Searched CASE không có selector chung. Mỗi WHEN chứa một điều kiện Boolean:

~~~sql
CASE
    WHEN condition_1 THEN
        statements_1;
    WHEN condition_2 THEN
        statements_2;
    WHEN condition_3 THEN
        statements_3;
    ELSE
        default_statements;
END CASE;
~~~

Các điều kiện được xét từ trên xuống. Nhánh đầu tiên có điều kiện TRUE được thực thi. Điều kiện FALSE hoặc NULL không chọn nhánh đó.

Ví dụ xếp loại đơn hàng:

~~~sql
DECLARE
    l_total NUMBER := 2500;
    l_customer_type VARCHAR2(20) := 'VIP';
BEGIN
    CASE
        WHEN l_total IS NULL THEN
            DBMS_OUTPUT.PUT_LINE('Amount is missing');
        WHEN l_total < 0 THEN
            DBMS_OUTPUT.PUT_LINE('Invalid amount');
        WHEN l_customer_type = 'VIP' AND l_total >= 2000 THEN
            DBMS_OUTPUT.PUT_LINE('VIP high-value order');
        WHEN l_total >= 2000 THEN
            DBMS_OUTPUT.PUT_LINE('High-value order');
        WHEN l_total >= 500 THEN
            DBMS_OUTPUT.PUT_LINE('Standard order');
        ELSE
            DBMS_OUTPUT.PUT_LINE('Small order');
    END CASE;
END;
/
~~~

Nhánh kiểm tra NULL và dữ liệu âm được đặt trước nhánh phân loại theo giá trị. Nếu đảo thứ tự, một giá trị bất thường có thể bị phân loại nhầm.

### 7.1. CASE statement không chạy xuyên nhiều nhánh

Khi một WHEN được chọn, CASE statement thực thi khối lệnh tương ứng rồi kết thúc CASE. Nó không tiếp tục chạy các WHEN phía sau như một số cấu trúc switch có fall-through trong ngôn ngữ khác.

Nếu cần thực thi nhiều hành động sau khi thỏa một điều kiện, đặt tất cả hành động trong cùng THEN block hoặc gọi một procedure.

### 7.2. ELSE trong CASE statement

ELSE là tùy chọn về cú pháp. Tuy nhiên, nếu bỏ ELSE và không có WHEN nào TRUE, PL/SQL phát sinh predefined exception CASE_NOT_FOUND.

Ví dụ:

~~~sql
DECLARE
    l_code VARCHAR2(10) := 'X';
BEGIN
    CASE l_code
        WHEN 'A' THEN
            DBMS_OUTPUT.PUT_LINE('Alpha');
        WHEN 'B' THEN
            DBMS_OUTPUT.PUT_LINE('Beta');
    END CASE;
END;
/
~~~

Với L_CODE là X, không nhánh nào khớp nên phát sinh CASE_NOT_FOUND.

Nếu mọi trường hợp không khớp đều có ý nghĩa hợp lệ, hãy thêm ELSE. Nếu không khớp là lỗi lập trình/nghiệp vụ, có thể cố ý bỏ ELSE và xử lý exception rõ ràng ở khối EXCEPTION.

## 8. CASE expression

CASE expression tạo ra một giá trị. Nó có thể dùng trong phép gán PL/SQL, SELECT, WHERE, ORDER BY, UPDATE hoặc INSERT.

Cú pháp searched CASE expression:

~~~sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ELSE default_result
END
~~~

Ví dụ:

~~~sql
DECLARE
    l_score NUMBER := 82;
    l_grade VARCHAR2(2);
BEGIN
    l_grade :=
        CASE
            WHEN l_score >= 90 THEN 'A'
            WHEN l_score >= 80 THEN 'B'
            WHEN l_score >= 70 THEN 'C'
            ELSE 'F'
        END;

    DBMS_OUTPUT.PUT_LINE('Grade = ' || l_grade);
END;
/
~~~

CASE expression trả về một giá trị duy nhất. Nó không chứa nhiều câu lệnh PL/SQL trong THEN như CASE statement.

### 8.1. Simple CASE expression

~~~sql
SELECT order_id,
       CASE status
           WHEN 'NEW' THEN 'Waiting'
           WHEN 'PAID' THEN 'Ready'
           WHEN 'CANCELLED' THEN 'Closed'
           ELSE 'Other'
       END AS status_label
FROM orders;
~~~

Selector STATUS được so sánh với từng giá trị WHEN; kết quả là một nhãn cho mỗi hàng.

### 8.2. Searched CASE expression

~~~sql
SELECT employee_id,
       salary,
       CASE
           WHEN salary IS NULL THEN 'MISSING'
           WHEN salary >= 10000 THEN 'HIGH'
           WHEN salary >= 5000 THEN 'MEDIUM'
           ELSE 'LOW'
       END AS salary_band
FROM employees;
~~~

Searched CASE phù hợp khi mỗi nhánh có điều kiện khác nhau hoặc cần xử lý NULL tường minh.

### 8.3. CASE expression trong UPDATE

~~~sql
UPDATE orders
SET shipping_fee =
    CASE
        WHEN total_amount >= 1000 THEN 0
        WHEN customer_type = 'VIP' THEN 10
        ELSE 25
    END
WHERE order_status = 'CONFIRMED';
~~~

Mỗi hàng được tính SHIPPING_FEE theo điều kiện tương ứng. Đây là một câu SQL set-based; không cần viết vòng lặp PL/SQL để cập nhật từng hàng.

### 8.4. CASE expression trong ORDER BY

~~~sql
SELECT order_id, status, created_at
FROM orders
ORDER BY
    CASE status
        WHEN 'URGENT' THEN 1
        WHEN 'NEW' THEN 2
        WHEN 'PAID' THEN 3
        ELSE 4
    END,
    created_at;
~~~

CASE tạo ra sort key số để sắp xếp theo thứ tự nghiệp vụ tùy chỉnh.

### 8.5. CASE expression trong conditional aggregation

~~~sql
SELECT customer_id,
       SUM(
           CASE
               WHEN status = 'PAID' THEN total_amount
               ELSE 0
           END
       ) AS paid_amount,
       SUM(
           CASE
               WHEN status = 'CANCELLED' THEN total_amount
               ELSE 0
           END
       ) AS cancelled_amount
FROM orders
GROUP BY customer_id;
~~~

CASE cho phép tổng hợp các nhóm điều kiện khác nhau trong cùng một phép GROUP BY. Khi ELSE 0, các hàng không thỏa điều kiện đóng góp 0 vào tổng.

Nếu bỏ ELSE, CASE expression không khớp sẽ trả NULL. SUM bỏ qua NULL, nên đôi khi đó là cách viết có chủ đích. Hãy chọn ELSE theo semantics mong muốn.

## 9. CASE statement và CASE expression khác nhau

| Tiêu chí | CASE statement | CASE expression |
|---|---|---|
| Mục đích | Chọn khối lệnh PL/SQL | Trả về một giá trị |
| Dùng trong | Khối PL/SQL | Biểu thức PL/SQL và SQL |
| THEN chứa | Một hay nhiều câu lệnh | Một biểu thức kết quả |
| Kết thúc | END CASE; | END |
| Không có nhánh khớp và không có ELSE | Phát sinh CASE_NOT_FOUND trong PL/SQL CASE statement | Trả về NULL |
| Ví dụ | CASE status WHEN ... THEN DBMS_OUTPUT... | CASE WHEN score >= ... THEN 'A' END |

Ví dụ statement:

~~~sql
CASE l_status
    WHEN 'OPEN' THEN
        UPDATE orders SET status = 'PROCESSING'
        WHERE order_id = l_order_id;
    WHEN 'CLOSED' THEN
        DBMS_OUTPUT.PUT_LINE('Already closed');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Other status');
END CASE;
~~~

Ví dụ expression:

~~~sql
l_label :=
    CASE l_status
        WHEN 'OPEN' THEN 'In progress'
        WHEN 'CLOSED' THEN 'Finished'
        ELSE 'Other'
    END;
~~~

Chọn statement khi cần thực thi các câu lệnh khác nhau. Chọn expression khi cần tạo một giá trị để gán, lọc, tính toán hoặc hiển thị.

## 10. IF, CASE statement và CASE expression: chọn cấu trúc nào?

| Tình huống | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Một điều kiện đúng/sai | IF | Ngắn và trực tiếp |
| Nhiều điều kiện độc lập hoặc khoảng giá trị | IF/ELSIF hoặc searched CASE | Điều kiện có thể khác nhau |
| Một biến có nhiều giá trị cụ thể | Simple CASE | Các nhánh cùng so sánh một selector |
| Nhiều điều kiện cần ưu tiên | Searched CASE hoặc IF/ELSIF | Thứ tự nhánh rõ ràng |
| Cần gán một giá trị theo điều kiện | CASE expression | Dùng được ngay trong biểu thức |
| Cần thực hiện nhiều câu lệnh theo nhánh | IF hoặc CASE statement | Mỗi nhánh chứa khối lệnh |
| Cần phân loại hàng trong SELECT/UPDATE | SQL CASE expression | Xử lý tập dữ liệu bằng SQL |

Không có quy tắc rằng CASE luôn nhanh hơn IF hoặc ngược lại. Chọn cấu trúc làm rõ nghiệp vụ, tránh lặp điều kiện và dễ kiểm thử. Với truy vấn SQL, CASE expression thường giúp xử lý nhiều hàng trong một statement.

## 11. Kết hợp điều kiện với DML và SELECT INTO

IF/CASE thường kiểm tra dữ liệu trước khi DML được thực hiện.

### 11.1. Kiểm tra số dư trước khi rút tiền

~~~sql
DECLARE
    l_balance accounts.balance%TYPE;
    l_amount NUMBER := 100;
BEGIN
    SELECT balance
    INTO l_balance
    FROM accounts
    WHERE account_id = 10
    FOR UPDATE;

    IF l_amount IS NULL OR l_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Invalid withdrawal amount');
    ELSIF l_balance IS NULL THEN
        RAISE_APPLICATION_ERROR(-20002, 'Account balance is missing');
    ELSIF l_balance < l_amount THEN
        RAISE_APPLICATION_ERROR(-20003, 'Insufficient balance');
    ELSE
        UPDATE accounts
        SET balance = balance - l_amount
        WHERE account_id = 10;
    END IF;

    COMMIT;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        ROLLBACK;
        RAISE_APPLICATION_ERROR(-20004, 'Account does not exist');
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

SELECT FOR UPDATE khóa hàng tài khoản trong lúc kiểm tra và cập nhật, giúp tránh hai transaction đồng thời cùng đọc số dư cũ rồi rút vượt số dư. Ví dụ minh họa cần được điều chỉnh cho quy tắc tiền tệ, audit và transaction boundary của hệ thống thực tế.

### 11.2. Dùng CASE expression để cập nhật nhiều nhóm

~~~sql
UPDATE employees
SET bonus_rate =
    CASE
        WHEN performance_score IS NULL THEN 0
        WHEN performance_score >= 90 THEN 0.20
        WHEN performance_score >= 80 THEN 0.15
        WHEN performance_score >= 70 THEN 0.10
        ELSE 0
    END;
~~~

Một câu UPDATE có thể áp dụng phân loại cho toàn bộ hàng. CASE expression được đánh giá cho từng hàng theo giá trị của hàng đó.

### 11.3. Lấy cờ bằng SELECT rồi dùng IF

~~~sql
DECLARE
    l_open_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO l_open_count
    FROM orders
    WHERE customer_id = 10
      AND status = 'OPEN';

    IF l_open_count > 0 THEN
        DBMS_OUTPUT.PUT_LINE('Customer has open orders');
    ELSE
        DBMS_OUTPUT.PUT_LINE('No open orders');
    END IF;
END;
/
~~~

COUNT(*) luôn trả một hàng và giá trị 0 nếu không có hàng phù hợp. Với truy vấn SELECT INTO có thể trả 0 hoặc nhiều hàng, cần hiểu và xử lý NO_DATA_FOUND/TOO_MANY_ROWS.

## 12. Phạm vi biến và khối lệnh trong từng nhánh

IF và CASE statement không tạo một scope PL/SQL độc lập cho từng THEN block. Biến được khai báo trong phần DECLARE của block bao ngoài có thể được sử dụng trong các nhánh.

~~~sql
DECLARE
    l_message VARCHAR2(100);
    l_status VARCHAR2(20) := 'PAID';
BEGIN
    IF l_status = 'PAID' THEN
        l_message := 'Payment complete';
    ELSE
        l_message := 'Payment pending';
    END IF;

    DBMS_OUTPUT.PUT_LINE(l_message);
END;
/
~~~

Nếu cần biến cục bộ riêng, có thể tạo nested block với DECLARE/BEGIN/END bên trong nhánh:

~~~sql
BEGIN
    IF condition THEN
        DECLARE
            l_local_value NUMBER := 10;
        BEGIN
            DBMS_OUTPUT.PUT_LINE(l_local_value);
        END;
    END IF;
END;
/
~~~

Nested block có scope riêng. Không thể sử dụng L_LOCAL_VALUE bên ngoài nested block đó.

## 13. Lỗi thường gặp khi viết nhánh điều kiện

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Viết ELSEIF thay cho ELSIF | Lỗi cú pháp | Dùng ELSIF |
| Thiếu THEN | Lỗi cú pháp | Mỗi IF/ELSIF/WHEN cần THEN đúng vị trí |
| Thiếu END IF | Khối IF chưa đóng | Kiểm tra cấu trúc lồng nhau |
| Dùng phép bằng với NULL | Điều kiện không TRUE | Dùng IS NULL |
| Nghĩ ELSE chỉ chạy khi FALSE | Có thể phân loại NULL sai | Kiểm tra NULL riêng |
| Đặt ngưỡng thấp trước ngưỡng cao | Nhánh đầu che nhánh sau | Sắp xếp điều kiện theo ưu tiên |
| Dùng simple CASE để so sánh khoảng | Không phù hợp cú pháp | Dùng searched CASE hoặc IF/ELSIF |
| Dùng WHEN NULL trong simple CASE để bắt NULL | Không match theo equality | Dùng searched CASE với IS NULL |
| Quên ELSE trong CASE statement | CASE_NOT_FOUND khi không nhánh nào TRUE | Thêm ELSE hoặc xử lý exception có chủ đích |
| Nhầm CASE statement với expression | Dùng nhiều câu lệnh ở nơi chỉ nhận một giá trị | Chọn đúng dạng CASE |
| CASE expression trả kết quả không tương thích datatype | Lỗi kiểu dữ liệu hoặc implicit conversion ngoài ý muốn | Dùng datatype kết quả thống nhất |
| Lặp cùng điều kiện ở nhiều nhánh | Khó bảo trì, nhánh che nhau | Gom điều kiện hoặc tách hàm |
| Lồng quá nhiều tầng IF | Luồng khó đọc và khó kiểm thử | Dùng searched CASE/ELSIF hoặc tách procedure |
| Dùng IF để cập nhật từng hàng thay vì set-based SQL | Nhiều context switch và code phức tạp | Cân nhắc CASE expression trong UPDATE |

## 14. Bài thực hành

Chạy các bài trong schema lab. Bật DBMS_OUTPUT trong công cụ SQL nếu muốn xem thông báo.

### Bài 1 — IF cơ bản

Khai báo L_SCORE bằng 75. Viết IF kiểm tra điểm từ 50 trở lên và in Passed. Thay điểm thành 30 và NULL để quan sát nhánh.

### Bài 2 — IF/ELSE

Khai báo L_QUANTITY bằng 0. Viết IF/ELSE để in In stock hoặc No stock. Sau đó đặt NULL và giải thích vì sao ELSE chạy.

### Bài 3 — ELSIF xếp loại

Dùng các ngưỡng 90, 80, 70, 60 để xếp loại A/B/C/D/F. Thử điểm 95, 80, 69 và NULL. Đặt điều kiện NULL thành nhánh đầu tiên.

### Bài 4 — Thứ tự nhánh

Viết một phiên bản sai với điều kiện L_SCORE >= 60 trước L_SCORE >= 90. Chạy với điểm 95, giải thích nhánh nào được chọn và sửa thứ tự.

### Bài 5 — Simple CASE

Khai báo L_STATUS lần lượt là NEW, PAID, CANCELLED và giá trị lạ. Dùng simple CASE statement để in thông báo. Bỏ ELSE và quan sát CASE_NOT_FOUND.

### Bài 6 — NULL trong simple CASE

Đặt L_STATUS := NULL và thử WHEN NULL. Sau đó đổi sang searched CASE với WHEN L_STATUS IS NULL. So sánh kết quả.

### Bài 7 — Searched CASE

Viết CASE statement phân loại đơn hàng theo TOTAL_AMOUNT, CUSTOMER_TYPE và trạng thái. Đảm bảo NULL và số âm được xử lý trước các ngưỡng bình thường.

### Bài 8 — CASE expression

Dùng CASE expression gán nhãn HIGH/MEDIUM/LOW vào biến PL/SQL. Sau đó đưa CASE vào SELECT để phân loại nhiều nhân viên.

### Bài 9 — CASE trong UPDATE

Tạo bảng lab có cột SCORE và GRADE. Dùng một câu UPDATE với CASE expression để cập nhật GRADE cho mọi hàng.

### Bài 10 — Conditional aggregation

Dùng SUM(CASE WHEN ...) để tính tổng đơn hàng PAID và CANCELLED theo CUSTOMER_ID. Thử ELSE 0 và bỏ ELSE để hiểu cách SUM xử lý NULL.

### Bài 11 — Kiểm tra số dư

Dùng SELECT FOR UPDATE, IF/ELSIF để kiểm tra số tiền rút NULL, không dương, vượt số dư và hợp lệ. Rollback dữ liệu sau bài thử.

### Bài 12 — Nested IF

Viết chương trình kiểm tra người dùng đã đăng nhập hay chưa, sau đó mới kiểm tra vai trò ADMIN/USER. Thử thay bằng searched CASE và so sánh độ dễ đọc.

## 15. Checklist khi viết điều kiện

- [ ] Chọn IF cho một vài nhánh lệnh hoặc CASE cho nhiều lựa chọn có cấu trúc.
- [ ] Dùng ELSIF đúng chính tả và đóng một END IF cho toàn bộ cấu trúc.
- [ ] Đặt điều kiện có độ ưu tiên cao hoặc phạm vi hẹp trước.
- [ ] Kiểm tra NULL bằng IS NULL/IS NOT NULL.
- [ ] Phân biệt FALSE với NULL nếu nghiệp vụ cần.
- [ ] Chọn simple CASE khi so sánh một selector với các giá trị cụ thể.
- [ ] Chọn searched CASE khi các nhánh là điều kiện Boolean khác nhau.
- [ ] Phân biệt CASE statement kết thúc END CASE với CASE expression kết thúc END.
- [ ] Thêm ELSE khi cần xử lý mọi trường hợp không khớp.
- [ ] Đảm bảo các nhánh CASE expression trả về datatype tương thích.
- [ ] Dùng SQL CASE expression cho phân loại/cập nhật nhiều hàng khi có thể.
- [ ] Xử lý exception của SELECT INTO và DML theo transaction boundary.
- [ ] Kiểm thử giá trị biên, NULL, giá trị bất thường và trường hợp không nhánh nào khớp.

## 16. Ghi nhớ cốt lõi

- IF thực thi khối THEN chỉ khi điều kiện là TRUE; FALSE và NULL không chọn nhánh đó.
- ELSIF thêm nhánh điều kiện vào cùng cấu trúc IF; viết liền một từ và kết thúc bằng một END IF.
- Oracle xét điều kiện từ trên xuống; nhánh TRUE đầu tiên được chọn, vì vậy thứ tự điều kiện có thể làm thay đổi kết quả.
- ELSE xử lý trường hợp không nhánh nào trước đó TRUE, bao gồm điều kiện NULL.
- PL/SQL BOOLEAN có ba trạng thái TRUE, FALSE và NULL.
- Simple CASE so sánh một selector với các giá trị WHEN; WHEN NULL không phải cách bắt selector NULL.
- Searched CASE kiểm tra các điều kiện WHEN theo thứ tự và phù hợp với khoảng giá trị, nhiều predicate hoặc xử lý NULL.
- CASE statement thực thi câu lệnh và kết thúc bằng END CASE; CASE expression trả về một giá trị và kết thúc bằng END.
- CASE statement không có ELSE và không có nhánh TRUE sẽ phát sinh CASE_NOT_FOUND; CASE expression không có ELSE trả NULL nếu không nhánh nào khớp.
- Dùng CASE expression trong SELECT, UPDATE, ORDER BY và conditional aggregation để xử lý tập dữ liệu bằng SQL.
- Viết nhánh rõ ràng, xử lý NULL có chủ đích, kiểm thử ranh giới và tránh lồng quá sâu giúp PL/SQL dễ đọc và dễ bảo trì.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/) — Conditional selection statements, IF statement, CASE statement và CASE expression.
- [Oracle Database PL/SQL Language Fundamentals](https://docs.oracle.com/en/database/) — BOOLEAN, expressions, nested blocks và exception handling.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — CASE expressions trong SELECT, UPDATE, ORDER BY và SQL conditions.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/) — CASE_NOT_FOUND và các lỗi cú pháp/kiểu dữ liệu liên quan.

Cú pháp và khả năng dùng kiểu BOOLEAN trong SQL phụ thuộc phiên bản Oracle. Khi triển khai, đối chiếu tài liệu đúng release và thử các trường hợp TRUE, FALSE, NULL, biên ngưỡng cùng nhánh ELSE trên schema lab.


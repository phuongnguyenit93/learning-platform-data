# Gán giá trị, biểu thức và xử lý NULL

Trong PL/SQL, biến lưu giá trị để chương trình tính toán, kiểm tra điều kiện và truyền dữ liệu giữa các câu lệnh. Một câu gán dùng toán tử :=. Oracle tính biểu thức ở bên phải trước, sau đó đưa kết quả vào biến hoặc thành phần có thể gán ở bên trái.

Giá trị NULL biểu thị dữ liệu chưa biết, chưa được cung cấp hoặc không áp dụng. NULL không đồng nghĩa với số 0, FALSE hoặc chuỗi có dấu cách. Khi một phép so sánh có liên quan đến NULL, kết quả có thể là UNKNOWN. Đây là lý do nhiều điều kiện PL/SQL và SQL cần viết IS NULL, COALESCE, NVL hoặc CASE một cách có chủ đích.

Bài học này giải thích cách khai báo và gán biến, kết hợp biểu thức, lấy dữ liệu bằng SELECT INTO và RETURNING INTO, quy tắc ba giá trị TRUE/FALSE/UNKNOWN, cách điều kiện hoạt động khi NULL xuất hiện và các công cụ xử lý NULL thường dùng trong Oracle.

## 1. Câu gán trong PL/SQL

Cú pháp cơ bản:

~~~sql
variable_name := expression;
~~~

Ví dụ:

~~~sql
DECLARE
    v_quantity NUMBER := 3;
    v_unit_price NUMBER := 125;
    v_total NUMBER;
BEGIN
    v_total := v_quantity * v_unit_price;
    DBMS_OUTPUT.PUT_LINE('Total = ' || v_total);
END;
/
~~~

Oracle tính v_quantity * v_unit_price trước, rồi gán kết quả 375 vào v_total.

### 1.1. := khác =

Trong PL/SQL:

- := dùng để gán giá trị cho biến.
- = dùng để so sánh bằng trong điều kiện.

~~~sql
DECLARE
    v_count NUMBER := 10;
BEGIN
    v_count := v_count + 1;       -- Gán lại giá trị.

    IF v_count = 11 THEN          -- So sánh bằng.
        DBMS_OUTPUT.PUT_LINE('Eleven');
    END IF;
END;
/
~~~

Trong câu SQL DML, cú pháp lại dùng dấu bằng ở phần SET:

~~~sql
UPDATE products
SET unit_price = unit_price * 1.05
WHERE product_id = 100;
~~~

SET unit_price = ... là cú pháp SQL cập nhật cột. Không thay dấu bằng trong SQL bằng :=.

### 1.2. Gán cho thành phần của record

Biến record có thể gán cho từng field:

~~~sql
DECLARE
    TYPE t_employee IS RECORD (
        employee_id NUMBER,
        full_name   VARCHAR2(100),
        salary      NUMBER
    );
    v_employee t_employee;
BEGIN
    v_employee.employee_id := 101;
    v_employee.full_name := 'Lan Nguyen';
    v_employee.salary := 2500;
END;
/
~~~

Vế trái có thể là biến scalar, field của record hoặc phần tử collection có thể gán. Biểu thức ở vế phải phải tương thích với kiểu dữ liệu đích.

## 2. Khai báo và khởi tạo biến

Biến PL/SQL được khai báo trong phần khai báo của block, procedure, function hoặc package. Nếu không có giá trị khởi tạo, biến scalar bắt đầu với giá trị NULL.

### 2.1. Gán giá trị ngay khi khai báo

~~~sql
DECLARE
    v_name VARCHAR2(50) := 'Oracle';
    v_count PLS_INTEGER := 0;
    v_rate NUMBER(5, 2) DEFAULT 7.5;
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_name);
    DBMS_OUTPUT.PUT_LINE(v_count);
    DBMS_OUTPUT.PUT_LINE(v_rate);
END;
/
~~~

:= và DEFAULT đều có thể dùng để đặt giá trị khởi tạo trong khai báo biến. Trong code thông thường, chọn một kiểu trình bày nhất quán.

### 2.2. Biến chưa khởi tạo có giá trị NULL

~~~sql
DECLARE
    v_amount NUMBER;
BEGIN
    IF v_amount IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Amount has not been assigned');
    END IF;
END;
/
~~~

Không nên giả định biến số chưa khởi tạo có giá trị 0 hoặc biến chuỗi chưa khởi tạo là chuỗi rỗng. Nếu chương trình cần giá trị mặc định, hãy khai báo hoặc gán rõ ràng.

### 2.3. CONSTANT

Một hằng số phải được khởi tạo khi khai báo và không được gán lại:

~~~sql
DECLARE
    c_tax_rate CONSTANT NUMBER := 0.08;
    v_net NUMBER := 1000;
    v_gross NUMBER;
BEGIN
    v_gross := v_net + (v_net * c_tax_rate);
    DBMS_OUTPUT.PUT_LINE(v_gross);
END;
/
~~~

Nếu cố gán lại c_tax_rate, PL/SQL báo lỗi vì hằng số không thể thay đổi sau khi khai báo.

### 2.4. NOT NULL cho biến

Biến khai báo NOT NULL phải có giá trị khởi tạo:

~~~sql
DECLARE
    v_status VARCHAR2(10) NOT NULL := 'NEW';
BEGIN
    v_status := 'DONE';
END;
/
~~~

Gán NULL cho biến NOT NULL gây lỗi runtime VALUE_ERROR. Chỉ dùng NOT NULL khi chương trình thật sự bảo đảm luôn có giá trị hợp lệ.

### 2.5. Dùng %TYPE để bám theo kiểu cột

Thay vì tự đoán kiểu dữ liệu, có thể khai báo biến theo cột:

~~~sql
DECLARE
    v_customer_name customers.customer_name%TYPE;
    v_credit_limit  customers.credit_limit%TYPE;
BEGIN
    NULL;
END;
/
~~~

%TYPE giúp kiểu biến đồng bộ với kiểu cột khi định nghĩa bảng thay đổi. Nó không tự áp dụng mọi constraint của cột lên biến; ví dụ biến %TYPE không mặc nhiên nhận cùng quy tắc NOT NULL của cột trong mọi trường hợp khai báo.

### 2.6. Dùng %ROWTYPE cho một hàng

~~~sql
DECLARE
    v_customer customers%ROWTYPE;
BEGIN
    SELECT *
    INTO v_customer
    FROM customers
    WHERE customer_id = 101;

    DBMS_OUTPUT.PUT_LINE(v_customer.customer_name);
END;
/
~~~

%ROWTYPE tạo record có các field tương ứng với cột của bảng hoặc view. Nó tiện cho việc lấy một hàng đầy đủ, nhưng nếu chỉ cần vài cột thì khai báo biến riêng và liệt kê cột tường minh thường giúp code rõ ràng hơn.

## 3. Biểu thức trong PL/SQL

Biểu thức là sự kết hợp của literal, biến, hằng số, toán tử và lời gọi hàm để tạo ra một giá trị.

~~~sql
DECLARE
    v_quantity NUMBER := 4;
    v_price NUMBER := 250;
    v_discount_rate NUMBER := 0.10;
    v_total NUMBER;
BEGIN
    v_total := v_quantity * v_price * (1 - v_discount_rate);
    DBMS_OUTPUT.PUT_LINE(v_total);
END;
/
~~~

Kết quả là 900.

### 3.1. Nhóm toán tử thường dùng

| Nhóm | Toán tử | Ví dụ |
| --- | --- | --- |
| Số học | +, -, *, /, ** | v_total := v_price * v_quantity; |
| Nối chuỗi | \|\| | v_full_name := v_first \|\| ' ' \|\| v_last; |
| So sánh | =, <>, !=, <, >, <=, >= | IF v_score >= 50 THEN ... |
| Logic | AND, OR, NOT | IF v_age >= 18 AND v_active = 'Y' THEN ... |
| Kiểm tra NULL | IS NULL, IS NOT NULL | IF v_code IS NULL THEN ... |
| Điều kiện tập hợp | IN, BETWEEN, LIKE | IF v_status IN ('NEW', 'OPEN') THEN ... |

Oracle hỗ trợ <> và != cho khác nhau; <> là cách viết SQL tiêu chuẩn thường được ưu tiên.

### 3.2. Dùng dấu ngoặc để thể hiện ý định

Toán tử có thứ tự ưu tiên. Khi biểu thức dài, dấu ngoặc giúp người đọc thấy rõ nhóm phép tính:

~~~sql
v_total := (v_quantity * v_unit_price)
           - (v_discount_amount + v_coupon_amount);
~~~

Đừng dựa vào trí nhớ về precedence khi biểu thức có nhiều phép toán, đặc biệt khi trộn số học, nối chuỗi và logic.

### 3.3. CASE expression trả về giá trị

CASE có thể dùng ngay trong phép gán:

~~~sql
DECLARE
    v_score NUMBER := 82;
    v_grade VARCHAR2(2);
BEGIN
    v_grade := CASE
        WHEN v_score >= 90 THEN 'A'
        WHEN v_score >= 80 THEN 'B'
        WHEN v_score >= 70 THEN 'C'
        WHEN v_score >= 60 THEN 'D'
        ELSE 'F'
    END;

    DBMS_OUTPUT.PUT_LINE(v_grade);
END;
/
~~~

Mọi nhánh trả về của CASE expression cần tương thích về kiểu dữ liệu. Nếu không có nhánh WHEN phù hợp và không có ELSE, CASE expression trả về NULL.

### 3.4. Hàm cũng là một phần của biểu thức

~~~sql
DECLARE
    v_name VARCHAR2(100) := '  lan nguyen  ';
    v_normalized VARCHAR2(100);
BEGIN
    v_normalized := INITCAP(TRIM(v_name));
    DBMS_OUTPUT.PUT_LINE(v_normalized);
END;
/
~~~

Có thể lồng hàm, nhưng biểu thức quá sâu sẽ khó đọc và khó debug. Nếu một phép tính có nhiều bước nghiệp vụ, gán vào biến trung gian với tên rõ ràng.

## 4. Kiểu dữ liệu và chuyển đổi khi gán

Giá trị biểu thức phải tương thích với kiểu của biến đích. Oracle có thể thực hiện một số implicit conversion, nhưng không nên phụ thuộc vào chuyển đổi ngầm nếu định dạng hoặc NLS có thể thay đổi.

### 4.1. Chuyển đổi tường minh

~~~sql
DECLARE
    v_amount_text VARCHAR2(30) := '1250.50';
    v_amount NUMBER(10, 2);
    v_date_text VARCHAR2(10) := '2026-11-14';
    v_order_date DATE;
BEGIN
    v_amount := TO_NUMBER(v_amount_text, '9999990D99',
                          'NLS_NUMERIC_CHARACTERS=''.,''');
    v_order_date := TO_DATE(v_date_text, 'YYYY-MM-DD');
END;
/
~~~

Định dạng và NLS rõ ràng giúp kết quả ổn định giữa session có cấu hình khác nhau. Nếu chuỗi đầu vào không đúng định dạng hoặc không chuyển đổi được, Oracle phát sinh lỗi chuyển đổi như ORA-01722 hoặc lỗi ngày tương ứng.

### 4.2. CAST

CAST chuyển một biểu thức sang kiểu được chỉ định:

~~~sql
v_amount := CAST(v_amount_text AS NUMBER);
~~~

CAST hữu ích khi muốn thể hiện kiểu kết quả trong SQL/PLSQL. Với chuỗi ngày hoặc số có định dạng cụ thể, các hàm TO_DATE, TO_NUMBER cùng format model thường rõ ý định hơn.

### 4.3. Tránh implicit conversion trong điều kiện

Không nên so sánh cột NUMBER với chuỗi tùy ý:

~~~sql
-- Không nên phụ thuộc chuyển đổi ngầm.
WHERE amount = '100'
~~~

Nên dùng literal số:

~~~sql
WHERE amount = 100
~~~

Hoặc chuyển đổi bind/string ở biên nhận dữ liệu bằng format rõ ràng. Chuyển đổi ngầm có thể phụ thuộc NLS và làm hỏng khả năng sử dụng index hoặc tạo lỗi khi dữ liệu không hợp lệ.

## 5. Gán dữ liệu từ câu SQL vào biến

### 5.1. SELECT ... INTO

Trong PL/SQL, SELECT ... INTO lấy kết quả query và gán các cột vào biến theo thứ tự:

~~~sql
DECLARE
    v_name customers.customer_name%TYPE;
    v_limit customers.credit_limit%TYPE;
BEGIN
    SELECT customer_name, credit_limit
    INTO v_name, v_limit
    FROM customers
    WHERE customer_id = 101;

    DBMS_OUTPUT.PUT_LINE(v_name || ': ' || v_limit);
END;
/
~~~

Số biểu thức trong SELECT phải khớp số biến trong INTO và kiểu dữ liệu phải tương thích.

SELECT INTO yêu cầu đúng một hàng:

- Không có hàng: PL/SQL phát sinh NO_DATA_FOUND.
- Có nhiều hơn một hàng: PL/SQL phát sinh TOO_MANY_ROWS.
- Có đúng một hàng nhưng cột chứa NULL: biến tương ứng nhận NULL.

Ví dụ xử lý không tìm thấy:

~~~sql
DECLARE
    v_name customers.customer_name%TYPE;
BEGIN
    SELECT customer_name
    INTO v_name
    FROM customers
    WHERE customer_id = 999999;

    DBMS_OUTPUT.PUT_LINE(v_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Customer does not exist');
END;
/
~~~

Đừng dùng WHEN OTHERS để che lỗi TOO_MANY_ROWS hoặc lỗi dữ liệu. Nếu nghiệp vụ cần một hàng duy nhất, hãy dùng khóa/unique constraint phù hợp hoặc xác định rõ quy tắc chọn hàng.

### 5.2. SELECT COUNT(*) INTO

Aggregate COUNT(*) không có GROUP BY trả đúng một hàng, kể cả khi không có hàng nguồn:

~~~sql
DECLARE
    v_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM customers
    WHERE status = 'ACTIVE';

    DBMS_OUTPUT.PUT_LINE(v_count);
END;
/
~~~

Nếu không có khách hàng ACTIVE, v_count nhận 0. Điều này khác với SELECT customer_name INTO ... không tìm thấy hàng, vốn phát sinh NO_DATA_FOUND.

### 5.3. Gán giá trị từ DML bằng RETURNING INTO

INSERT, UPDATE hoặc DELETE có thể trả giá trị cột vào biến bằng RETURNING INTO:

~~~sql
DECLARE
    v_new_id lab_orders.order_id%TYPE;
BEGIN
    INSERT INTO lab_orders (order_id, order_status)
    VALUES (lab_orders_seq.NEXTVAL, 'NEW')
    RETURNING order_id INTO v_new_id;

    DBMS_OUTPUT.PUT_LINE('Created order ' || v_new_id);
END;
/
~~~

Tên bảng sequence trong ví dụ là đối tượng minh họa; hãy tạo bảng/sequence tương ứng trước khi chạy. RETURNING INTO hữu ích khi cần lấy ID hoặc giá trị vừa được database tạo/cập nhật mà không cần query lại.

Với thao tác ảnh hưởng nhiều hàng, có thể dùng RETURNING BULK COLLECT INTO để nhận nhiều giá trị vào collection phù hợp. Không dùng scalar RETURNING INTO như thể nó tự gom mọi hàng bị tác động.

## 6. NULL là gì?

NULL biểu thị giá trị không xác định hoặc không có. Nó không phải:

- Số 0.
- Chuỗi có ký tự khoảng trắng.
- FALSE.
- Giá trị mặc định mà ứng dụng tự suy đoán.

Ví dụ một đơn hàng chưa có ngày giao:

~~~sql
DECLARE
    v_shipped_at DATE;
BEGIN
    IF v_shipped_at IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Not shipped yet');
    END IF;
END;
/
~~~

NULL có thể có nhiều ý nghĩa nghiệp vụ: chưa biết, chưa nhập, không áp dụng hoặc chưa phát sinh. Nếu các ý nghĩa đó cần được phân biệt, hãy dùng status/code riêng thay vì gom tất cả vào NULL.

### 6.1. NULL trong phép gán

~~~sql
DECLARE
    v_amount NUMBER := 100;
BEGIN
    v_amount := NULL;
    DBMS_OUTPUT.PUT_LINE(v_amount);
END;
/
~~~

Biến scalar cho phép NULL sẽ nhận NULL. Từ thời điểm đó, các phép toán và so sánh liên quan cần được xử lý theo quy tắc NULL.

### 6.2. Chuỗi rỗng trong Oracle

Trong Oracle Database, chuỗi ký tự có độ dài bằng 0 ('') hiện được xử lý như NULL đối với kiểu ký tự thông thường. Vì vậy:

~~~sql
DECLARE
    v_text VARCHAR2(20) := '';
BEGIN
    IF v_text IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('NULL or empty input');
    END IF;
END;
/
~~~

Một chuỗi chứa dấu cách, ví dụ ' ', không giống chuỗi rỗng. Nếu cần coi chuỗi chỉ có khoảng trắng là thiếu dữ liệu, hãy dùng TRIM rồi kiểm tra NULL:

~~~sql
IF TRIM(v_text) IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('No meaningful text');
END IF;
~~~

Oracle có ghi chú rằng cách xử lý chuỗi độ dài bằng 0 có thể thay đổi trong tương lai. Không xây dựng quy tắc nghiệp vụ quan trọng dựa trên việc chuỗi rỗng và NULL luôn đồng nhất; hãy chuẩn hóa đầu vào và lưu trạng thái rõ ràng.

## 7. Logic ba giá trị: TRUE, FALSE và UNKNOWN

Trong SQL và PL/SQL, một phép so sánh có NULL thường tạo kết quả UNKNOWN (được biểu diễn bằng NULL trong ngữ cảnh Boolean PL/SQL). Do đó, logic không chỉ có TRUE và FALSE.

### 7.1. So sánh với NULL

Các biểu thức sau không cho kết quả TRUE:

~~~sql
v_amount = NULL
v_amount <> NULL
NULL = NULL
~~~

Chúng cho kết quả UNKNOWN vì Oracle không biết hai giá trị chưa xác định có bằng nhau hay không.

Kiểm tra NULL bằng:

~~~sql
IF v_amount IS NULL THEN
    ...
END IF;
~~~

Kiểm tra có giá trị:

~~~sql
IF v_amount IS NOT NULL THEN
    ...
END IF;
~~~

### 7.2. Bảng truth table cơ bản

U dưới đây là UNKNOWN:

| A | B | A AND B | A OR B |
| --- | --- | --- | --- |
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | U | U | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | U | FALSE | U |
| U | U | U | U |

Với NOT:

| A | NOT A |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| U | U |

Một số hệ quả quan trọng:

- TRUE AND NULL là UNKNOWN.
- FALSE AND NULL là FALSE.
- TRUE OR NULL là TRUE.
- FALSE OR NULL là UNKNOWN.
- NOT NULL vẫn là UNKNOWN.

### 7.3. NULL trong IF

Trong PL/SQL, nhánh THEN chỉ chạy khi điều kiện là TRUE. Nếu điều kiện là FALSE hoặc NULL/UNKNOWN, nhánh đó không chạy:

~~~sql
DECLARE
    v_score NUMBER;
BEGIN
    IF v_score >= 50 THEN
        DBMS_OUTPUT.PUT_LINE('Pass');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not pass or score missing');
    END IF;
END;
/
~~~

Vì v_score là NULL, phép so sánh v_score >= 50 cho UNKNOWN; chương trình chạy ELSE. Nếu nghiệp vụ cần phân biệt không đạt với chưa có điểm, phải kiểm tra NULL trước:

~~~sql
IF v_score IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('Score is missing');
ELSIF v_score >= 50 THEN
    DBMS_OUTPUT.PUT_LINE('Pass');
ELSE
    DBMS_OUTPUT.PUT_LINE('Fail');
END IF;
~~~

### 7.4. NULL trong WHERE

Trong SQL, WHERE chỉ giữ hàng có điều kiện TRUE. Hàng cho FALSE hoặc UNKNOWN đều bị loại:

~~~sql
SELECT customer_id, credit_limit
FROM customers
WHERE credit_limit > 1000;
~~~

Hàng có CREDIT_LIMIT NULL không được trả về vì điều kiện là UNKNOWN. Nếu muốn lấy cả hàng chưa có hạn mức:

~~~sql
SELECT customer_id, credit_limit
FROM customers
WHERE credit_limit > 1000
   OR credit_limit IS NULL;
~~~

Đây là điểm khác với suy nghĩ NULL giống 0: nếu NULL bị coi như 0, kết quả có thể khác đáng kể.

### 7.5. CASE khi điều kiện UNKNOWN

Trong searched CASE, một WHEN chỉ được chọn khi điều kiện TRUE:

~~~sql
CASE
    WHEN v_amount > 0 THEN 'POSITIVE'
    WHEN v_amount = 0 THEN 'ZERO'
    WHEN v_amount < 0 THEN 'NEGATIVE'
    ELSE 'UNKNOWN'
END
~~~

Nếu v_amount là NULL, ba điều kiện đầu đều UNKNOWN và nhánh ELSE được chọn.

Với simple CASE:

~~~sql
CASE v_status
    WHEN 'NEW' THEN 'New'
    WHEN 'DONE' THEN 'Completed'
    ELSE 'Other'
END
~~~

Nếu muốn xử lý NULL, dùng searched CASE với WHEN v_status IS NULL. Không viết WHEN NULL với kỳ vọng nó khớp giá trị NULL, vì phép so sánh bằng NULL không trả TRUE.

## 8. NULL trong phép toán và biểu thức

### 8.1. Số học

Nếu một toán hạng số là NULL, kết quả số học thường là NULL:

~~~sql
DECLARE
    v_price NUMBER := 100;
    v_tax NUMBER;
    v_total NUMBER;
BEGIN
    v_total := v_price + v_tax;

    IF v_total IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Total is unknown');
    END IF;
END;
/
~~~

Nếu v_tax chưa được gán, tổng cũng là NULL. Nếu nghiệp vụ định nghĩa thuế chưa có bằng 0, hãy thể hiện rõ quy tắc bằng NVL hoặc COALESCE; không tự động biến mọi NULL thành 0.

### 8.2. Nối chuỗi

Oracle có quy tắc nối chuỗi đặc biệt: nối một chuỗi NULL/độ dài bằng 0 với chuỗi có nội dung sẽ cho chuỗi có nội dung đó. Ví dụ:

~~~sql
DECLARE
    v_first VARCHAR2(20) := 'Lan';
    v_middle VARCHAR2(20);
    v_full VARCHAR2(60);
BEGIN
    v_full := v_first || ' ' || v_middle;
    DBMS_OUTPUT.PUT_LINE(v_full);
END;
/
~~~

Kết quả là Lan kèm một dấu cách cuối. Điều này khác phép cộng số học. Nếu ghép nhiều field tùy chọn, cần chủ động xử lý dấu cách/dấu phân cách để tránh tên có khoảng trắng thừa.

### 8.3. Hàm aggregate và NULL

Các hàm aggregate SQL thường bỏ qua giá trị NULL:

| Biểu thức | Hành vi |
| --- | --- |
| COUNT(*) | Đếm mọi hàng |
| COUNT(column_name) | Đếm hàng có column_name khác NULL |
| SUM(column_name) | Cộng các giá trị khác NULL |
| AVG(column_name) | Tính trung bình trên các giá trị khác NULL |
| MIN(column_name), MAX(column_name) | Bỏ qua NULL khi xác định min/max |

Nếu tất cả giá trị đầu vào của SUM hoặc AVG đều NULL, kết quả aggregate có thể là NULL. COUNT(column_name) trong trường hợp đó là 0.

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(commission_pct) AS rows_with_commission,
    AVG(commission_pct) AS average_commission
FROM employees;
~~~

Không diễn giải COUNT(commission_pct) = 0 là không có nhân viên; nó chỉ có nghĩa không có hàng nào có giá trị commission khác NULL.

## 9. Các hàm xử lý NULL thường dùng

### 9.1. NVL

NVL(expr1, expr2) trả expr2 nếu expr1 là NULL; nếu không thì trả expr1.

~~~sql
DECLARE
    v_commission NUMBER;
    v_pay NUMBER;
BEGIN
    v_pay := 1000 + NVL(v_commission, 0);
END;
/
~~~

Trong SQL:

~~~sql
SELECT employee_id,
       salary + NVL(commission_pct, 0) * salary AS total_pay
FROM employees;
~~~

NVL hữu ích khi quy tắc nghiệp vụ xác định giá trị thay thế. Hãy lưu ý quy tắc chuyển đổi kiểu: Oracle chuyển expr2 theo kiểu của expr1 trong nhiều trường hợp ký tự; với số, quy tắc numeric precedence được áp dụng. Nên truyền hai biểu thức có kiểu tương thích rõ ràng.

### 9.2. NVL2

NVL2(expr1, expr2, expr3) trả expr2 nếu expr1 khác NULL, và trả expr3 nếu expr1 là NULL:

~~~sql
SELECT
    employee_id,
    NVL2(commission_pct, 'Commission eligible', 'No commission')
        AS commission_status
FROM employees;
~~~

NVL2 hữu ích khi cần chọn một trong hai kết quả dựa trên việc một biểu thức có NULL hay không.

### 9.3. COALESCE

COALESCE(expr1, expr2, ..., exprN) trả về biểu thức đầu tiên khác NULL:

~~~sql
SELECT
    customer_id,
    COALESCE(mobile_phone, work_phone, home_phone, 'No phone')
        AS contact_phone
FROM customers;
~~~

Khác NVL, COALESCE nhận nhiều đối số và là biểu thức chuẩn SQL. Oracle đánh giá theo short-circuit: dừng ở biểu thức đầu tiên khác NULL. Các biểu thức trả về phải tương thích kiểu dữ liệu.

### 9.4. NULLIF

NULLIF(expr1, expr2) trả NULL nếu hai biểu thức bằng nhau; nếu không, trả expr1:

~~~sql
SELECT
    actual_amount / NULLIF(expected_amount, 0) AS ratio
FROM payment_checks;
~~~

Nếu EXPECTED_AMOUNT = 0, mẫu trên tạo NULL thay vì chia cho 0. Nếu EXPECTED_AMOUNT vốn NULL, kết quả vẫn là NULL theo logic so sánh. NULLIF không thay thế việc xác thực dữ liệu; nó chỉ thể hiện quy tắc biểu thức.

### 9.5. CASE

CASE cho phép viết quy tắc thay thế phức tạp và dễ đọc:

~~~sql
CASE
    WHEN credit_limit IS NULL THEN 'NOT SET'
    WHEN credit_limit = 0 THEN 'ZERO'
    WHEN credit_limit < 0 THEN 'INVALID'
    ELSE 'SET'
END
~~~

Khi điều kiện liên quan NULL, IS NULL giúp tránh UNKNOWN không mong muốn.

### 9.6. DECODE

Oracle DECODE có một quy tắc đặc biệt: hai giá trị NULL được xem là bằng nhau trong phép so khớp của DECODE:

~~~sql
SELECT DECODE(optional_code,
              NULL, 'MISSING',
              'PRESENT') AS code_status
FROM source_rows;
~~~

Điều này khác phép so sánh optional_code = NULL, vốn cho UNKNOWN. DECODE là hàm Oracle lâu đời; với logic mới, CASE WHEN optional_code IS NULL THEN ... thường rõ ràng và dễ chuyển đổi giữa hệ quản trị hơn.

## 10. So sánh NULL-safe

Nhiều bài toán cần biết hai giá trị có giống nhau hay không, trong đó hai NULL cũng được coi là cùng trạng thái chưa có.

### 10.1. Mẫu điều kiện tường minh

~~~sql
IF (v_old_value = v_new_value)
   OR (v_old_value IS NULL AND v_new_value IS NULL)
THEN
    DBMS_OUTPUT.PUT_LINE('Same value');
ELSE
    DBMS_OUTPUT.PUT_LINE('Different value');
END IF;
~~~

Khi một giá trị NULL và giá trị còn lại không NULL, nhánh đầu là UNKNOWN nhưng nhánh thứ hai là FALSE; kết quả tổng thể không TRUE và đi vào ELSE. Khi cả hai NULL, nhánh thứ hai TRUE.

### 10.2. Dùng DECODE để so sánh hai giá trị

~~~sql
IF DECODE(v_old_value, v_new_value, 1, 0) = 1 THEN
    DBMS_OUTPUT.PUT_LINE('Same value');
END IF;
~~~

DECODE coi hai NULL là bằng nhau. Tuy nhiên, hãy chú ý quy tắc implicit conversion và kiểu dữ liệu của các đối số. Với điều kiện phức tạp hoặc cần tính portable, mẫu IS NULL tường minh dễ hiểu hơn.

### 10.3. Tránh dùng sentinel tùy tiện

Một cách thường thấy là thay NULL bằng một giá trị giả:

~~~sql
NVL(v_code, 'UNKNOWN')
~~~

Nếu UNKNOWN là một giá trị hợp lệ trong dữ liệu, phép thay thế tạo va chạm giữa NULL và giá trị thật. Với số, dùng -1 cũng có rủi ro tương tự nếu -1 có thể xuất hiện hợp lệ. Chỉ dùng sentinel khi domain loại trừ giá trị đó bằng constraint và quy tắc nghiệp vụ rõ ràng.

## 11. NULL trong điều kiện lọc tùy chọn

Một mẫu ứng dụng thường gặp là tham số lọc có thể NULL: NULL có nghĩa không lọc theo cột này.

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE (:p_region IS NULL OR region_code = :p_region);
~~~

Nếu :p_region là NULL, vế đầu TRUE nên query không giới hạn theo region. Nếu có giá trị, query lọc theo region đó.

Đây là mẫu tiện lợi, nhưng với bảng lớn, predicate dạng OR có thể ảnh hưởng kế hoạch thực thi và khả năng dùng index tùy bind peeking/optimizer. Với workload quan trọng, đo execution plan; có thể cần dynamic SQL có bind variables để chỉ thêm predicate khi tham số được cung cấp.

Nếu nghiệp vụ yêu cầu tìm những hàng mà REGION_CODE là NULL thì tham số NULL không thể đồng thời mang nghĩa không lọc. Hãy dùng một cờ riêng hoặc API biểu đạt rõ hai trạng thái: bỏ qua filter và lọc NULL.

## 12. Short-circuit evaluation

Trong PL/SQL, toán tử logic AND và OR có short-circuit evaluation:

- Với A AND B, nếu A là FALSE, PL/SQL không cần đánh giá B.
- Với A OR B, nếu A là TRUE, PL/SQL không cần đánh giá B.

Ví dụ:

~~~sql
IF v_denominator <> 0
   AND v_numerator / v_denominator > 10
THEN
    DBMS_OUTPUT.PUT_LINE('Ratio is large');
END IF;
~~~

Trong PL/SQL, nếu vế đầu FALSE, vế chia không được đánh giá. Tuy nhiên, không nên dựa vào thứ tự đánh giá biểu thức trong SQL query để bảo vệ một phép chuyển đổi có thể lỗi. SQL optimizer có thể biến đổi thứ tự predicate. Hãy dùng biểu thức an toàn như NULLIF, CASE hoặc validate dữ liệu để tránh lỗi ngay trong phép tính.

Ví dụ chia an toàn:

~~~sql
v_ratio := v_numerator / NULLIF(v_denominator, 0);
~~~

Nếu mẫu số là 0 hoặc NULL, kết quả là NULL; chương trình có thể kiểm tra kết quả trước khi dùng.

## 13. Lab tổng hợp: tính tổng tiền đơn hàng có NULL

Ta tạo bảng đơn hàng đơn giản:

~~~sql
CREATE TABLE lab_order_lines (
    line_id       NUMBER PRIMARY KEY,
    quantity      NUMBER,
    unit_price    NUMBER(10, 2),
    discount_rate NUMBER(5, 4),
    note          VARCHAR2(100)
);

INSERT INTO lab_order_lines VALUES (1, 2, 100, 0.10, 'Promo');
INSERT INTO lab_order_lines VALUES (2, 3, 50, NULL, 'No discount set');
INSERT INTO lab_order_lines VALUES (3, 1, 80, 0.20, NULL);
INSERT INTO lab_order_lines VALUES (4, NULL, 30, 0.00, 'Missing quantity');
COMMIT;
~~~

### 13.1. Quan sát phép tính khi NULL xuất hiện

~~~sql
SELECT
    line_id,
    quantity,
    unit_price,
    discount_rate,
    quantity * unit_price AS gross_amount,
    quantity * unit_price * (1 - discount_rate) AS net_amount
FROM lab_order_lines
ORDER BY line_id;
~~~

Kết quả dự kiến:

| LINE_ID | GROSS_AMOUNT | NET_AMOUNT | Giải thích |
| ---: | ---: | ---: | --- |
| 1 | 200 | 180 | Các toán hạng đều có giá trị |
| 2 | 150 | NULL | DISCOUNT_RATE là NULL |
| 3 | 80 | 64 | NOTE NULL không ảnh hưởng phép tính số |
| 4 | NULL | NULL | QUANTITY là NULL |

### 13.2. Áp dụng quy tắc NULL là không có giảm giá

Chỉ dùng cách này nếu nghiệp vụ xác nhận NULL discount có nghĩa là 0:

~~~sql
SELECT
    line_id,
    quantity * unit_price * (1 - NVL(discount_rate, 0))
        AS net_amount
FROM lab_order_lines
ORDER BY line_id;
~~~

Hàng 2 giờ có net amount 150. Hàng 4 vẫn NULL vì quantity chưa có giá trị; NVL chỉ xử lý discount rate.

### 13.3. Gán vào biến và xử lý trường hợp thiếu

~~~sql
DECLARE
    v_line_id NUMBER := 2;
    v_quantity lab_order_lines.quantity%TYPE;
    v_price lab_order_lines.unit_price%TYPE;
    v_discount lab_order_lines.discount_rate%TYPE;
    v_net_amount NUMBER;
BEGIN
    SELECT quantity, unit_price, discount_rate
    INTO v_quantity, v_price, v_discount
    FROM lab_order_lines
    WHERE line_id = v_line_id;

    IF v_quantity IS NULL OR v_price IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Cannot calculate: missing quantity or price');
    ELSE
        v_net_amount := v_quantity * v_price
                        * (1 - COALESCE(v_discount, 0));
        DBMS_OUTPUT.PUT_LINE('Net amount = ' || v_net_amount);
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Line not found');
END;
/
~~~

Đoạn code phân biệt hai tình huống: không tìm thấy hàng và tìm thấy hàng nhưng thiếu dữ liệu để tính. Đây là cách xử lý rõ ràng hơn việc thay mọi NULL bằng 0 ngay từ đầu.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Viết v_total = 100 để gán | Nhầm phép so sánh với phép gán | Dùng v_total := 100 |
| Dùng := trong SQL UPDATE | Nhầm cú pháp PL/SQL với SQL | Dùng SET column = expression |
| Biến chưa khởi tạo được coi là 0 | Giả định sai giá trị mặc định | Khởi tạo rõ ràng hoặc kiểm tra IS NULL |
| x = NULL không vào nhánh IF | So sánh NULL tạo UNKNOWN | Dùng x IS NULL |
| Hai NULL không được coi là bằng nhau | SQL không định nghĩa NULL = NULL là TRUE | Viết điều kiện NULL-safe hoặc dùng DECODE có chủ đích |
| Cộng số ra NULL | Một toán hạng là NULL | Xác định quy tắc nghiệp vụ rồi dùng NVL/COALESCE nếu phù hợp |
| Chuỗi có khoảng trắng cuối | Nối chuỗi với NULL vẫn giữ dấu phân cách | TRIM hoặc xây dựng chuỗi có điều kiện |
| SELECT INTO báo NO_DATA_FOUND | Query không trả hàng | Xử lý exception hoặc kiểm tra tồn tại theo nhu cầu |
| SELECT INTO báo TOO_MANY_ROWS | Query trả nhiều hơn một hàng | Dùng khóa duy nhất hoặc quy tắc chọn hàng rõ ràng |
| Chuyển chuỗi sang số lỗi | Dữ liệu không đúng format hoặc NLS | Dùng TO_NUMBER/TO_DATE với format và NLS rõ ràng |
| CASE không nhận nhánh NULL | Dùng simple CASE WHEN NULL | Dùng searched CASE với IS NULL |
| NVL thay NULL bằng giá trị gây sai nghiệp vụ | Sentinel hoặc giá trị mặc định không phù hợp | Chỉ thay NULL theo quy tắc nghiệp vụ rõ ràng |
| COUNT(column) thấp hơn COUNT(*) | COUNT(column) bỏ qua NULL | Chọn đúng kiểu đếm theo mục đích |
| Dựa vào AND trong SQL để tránh lỗi chuyển đổi | Optimizer có thể đổi thứ tự đánh giá predicate | Dùng CASE/biểu thức chuyển đổi an toàn và validate nguồn |

## 15. Bài tập thực hành

Sử dụng bảng LAB_ORDER_LINES trong mục 13.

### Bài 1 — Khai báo và gán

Khai báo biến số lượng, đơn giá và tổng tiền. Gán giá trị bằng :=, tính tổng bằng biểu thức số học và in kết quả.

### Bài 2 — Phân biệt := và =

Viết một block vừa gán v_count := v_count + 1, vừa dùng IF v_count = 5. Giải thích vai trò của hai toán tử.

### Bài 3 — SELECT INTO

Lấy QUANTITY, UNIT_PRICE và DISCOUNT_RATE của từng LINE_ID vào biến %TYPE. Thử một ID không tồn tại và một truy vấn trả nhiều hàng; xử lý NO_DATA_FOUND và TOO_MANY_ROWS.

### Bài 4 — Logic ba giá trị

Tạo biến Boolean có giá trị NULL. Thử các biểu thức TRUE AND NULL, FALSE AND NULL, TRUE OR NULL và NOT NULL. Dự đoán nhánh IF được thực hiện.

### Bài 5 — Xử lý NULL bằng hàm

Tính net amount với NVL, NVL2, COALESCE và CASE. Giải thích khi nào NULL discount được phép hiểu là 0.

### Bài 6 — So sánh NULL-safe

Viết điều kiện phát hiện hai giá trị cũ/mới giống nhau, kể cả khi cả hai cùng NULL. Thực hiện một phiên bản dùng điều kiện IS NULL và một phiên bản dùng DECODE.

### Bài 7 — Chuỗi rỗng

Gán '', ' ' và '  ' cho biến VARCHAR2. Kiểm tra IS NULL, LENGTH và TRIM. Giải thích vì sao chuỗi chỉ có dấu cách cần được chuẩn hóa riêng.

### Bài 8 — Chia an toàn

Viết biểu thức tính tỷ lệ actual / expected. Thử expected bằng 0, NULL và một số dương. Dùng NULLIF để tránh chia cho 0 và quyết định cách hiển thị kết quả NULL.

## 16. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập:

~~~sql
DROP TABLE lab_order_lines PURGE;
~~~

PURGE bỏ qua recycle bin. Không chạy trên bảng nghiệp vụ hoặc dữ liệu cần khôi phục.

## Tổng kết

Trong PL/SQL, := gán kết quả của một biểu thức vào biến; = dùng để so sánh. Biến scalar chưa khởi tạo có giá trị NULL. Dùng CONSTANT, NOT NULL, %TYPE và %ROWTYPE để thể hiện ý định và giữ kiểu dữ liệu nhất quán. SELECT INTO yêu cầu đúng một hàng, còn RETURNING INTO lấy giá trị từ DML.

NULL không phải 0 hoặc FALSE. So sánh với NULL tạo UNKNOWN, nên dùng IS NULL/IS NOT NULL; trong IF, chỉ TRUE mới chạy nhánh THEN, còn WHERE loại cả FALSE và UNKNOWN. Các hàm NVL, NVL2, COALESCE, NULLIF, CASE và DECODE có quy tắc riêng. Chỉ thay NULL bằng giá trị mặc định khi nghiệp vụ xác định rõ ý nghĩa của giá trị thay thế. Khi xử lý dữ liệu thực tế, hãy kiểm soát kiểu và format chuyển đổi, phân biệt thiếu dữ liệu với không tìm thấy hàng, và kiểm thử các trường hợp NULL một cách tường minh.

## Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Language Reference — Assignment Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/assignment-statement.html) — cú pháp gán trong PL/SQL.
- [Oracle Database PL/SQL Language Reference — Expressions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-expressions.html) — biểu thức và toán tử.
- [Oracle Database PL/SQL Language Reference — NULLs (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/nulls.html) — NULL trong PL/SQL.
- [Oracle Database SQL Language Reference — Nulls (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Nulls.html) — NULL trong SQL và điều kiện.
- [Oracle Database SQL Language Reference — NVL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NVL.html) — thay thế NULL.
- [Oracle Database SQL Language Reference — COALESCE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COALESCE.html) — chọn biểu thức đầu tiên khác NULL.
- [Oracle Database SQL Language Reference — NVL2 (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NVL2.html) — chọn kết quả theo trạng thái NULL.
- [Oracle Database SQL Language Reference — NULLIF (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NULLIF.html) — trả NULL khi hai biểu thức bằng nhau.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu PL/SQL Language Reference và SQL Language Reference đúng phiên bản, đặc biệt quy tắc Boolean, chuyển đổi kiểu, chuỗi rỗng và hành vi của các hàm xử lý NULL.

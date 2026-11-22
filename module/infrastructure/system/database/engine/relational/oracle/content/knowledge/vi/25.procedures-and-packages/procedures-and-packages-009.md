# Gọi function trong SQL, tính thuần và giới hạn tác dụng phụ

Oracle cho phép gọi stored function trong nhiều biểu thức SQL, ví dụ SELECT list, WHERE, ORDER BY, GROUP BY hoặc biểu thức của INSERT/UPDATE/MERGE. Khả năng này giúp đóng gói quy tắc tính toán và tái sử dụng logic giữa các câu SQL. Tuy nhiên, function được gọi từ SQL chạy trong một ngữ cảnh có những giới hạn riêng về kiểu dữ liệu, DML, transaction control, trạng thái package và parallel execution.

Một function phù hợp để gọi từ SQL nên có đầu vào rõ ràng, trả về kết quả dựa trên đầu vào, không thay đổi dữ liệu, không phụ thuộc trạng thái thay đổi ngoài tham số và không thực hiện các tác dụng phụ như gửi email, ghi file hoặc gọi dịch vụ bên ngoài. Đó là tư duy về **tính thuần (purity)**. Function càng gần tính thuần, kết quả càng dễ dự đoán, optimizer càng có nhiều cơ hội tối ưu và việc dùng lại trong nhiều câu SQL càng an toàn.

Sau bài học, bạn có thể:

- Tạo standalone function và package function có thể gọi từ SQL.
- Gọi function trong SELECT, WHERE và các biểu thức DML.
- Phân biệt function chỉ dùng trong PL/SQL với function có thể dùng trong SQL.
- Giải thích tính thuần, tính xác định và tác dụng phụ.
- Hiểu giới hạn DML, COMMIT/ROLLBACK, DDL và truy cập bảng đang bị thay đổi.
- Nhận biết các lỗi như ORA-14551, ORA-14552 và ORA-04091.
- Hiểu vì sao function có thể bị gọi nhiều lần, ít lần hơn dự kiến hoặc theo thứ tự khác.
- Phân biệt DETERMINISTIC với RESULT_CACHE.
- Nhận biết chi phí chuyển ngữ cảnh SQL/PLSQL và vấn đề gọi function theo từng hàng.
- Thiết kế function an toàn, kiểm thử và quản lý dependency trong package.

> Một số giới hạn về kiểu dữ liệu và khả năng gọi function từ SQL thay đổi theo phiên bản Oracle. Các ví dụ ưu tiên kiểu SQL phổ biến như NUMBER, VARCHAR2 và DATE. Hãy xác nhận cú pháp/khả năng cụ thể theo release đang sử dụng.

## 1. Function trong PL/SQL và function được gọi từ SQL

### 1.1. Function là gì?

Function là một chương trình con PL/SQL trả về một giá trị thông qua mệnh đề RETURN. Function có thể nhận tham số IN, thực hiện phép tính hoặc truy vấn dữ liệu, rồi trả kết quả cho nơi gọi.

Ví dụ function tính giá sau thuế:

```sql
CREATE OR REPLACE FUNCTION lab_price_with_tax (
    p_net_amount IN NUMBER,
    p_tax_rate   IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN p_net_amount * (1 + p_tax_rate);
END;
/
```

Có thể gọi từ PL/SQL:

```sql
DECLARE
    l_total NUMBER;
BEGIN
    l_total := lab_price_with_tax(100, 0.10);
    DBMS_OUTPUT.PUT_LINE(l_total);
END;
/
```

Vì function được lưu trong database và dùng kiểu dữ liệu tương thích SQL, nó cũng có thể được gọi trong câu SQL:

```sql
SELECT lab_price_with_tax(100, 0.10) AS gross_amount
FROM dual;
```

Kết quả là 110.

### 1.2. Function dùng trong PL/SQL không mặc nhiên dùng được trong SQL

Một function có thể hợp lệ trong PL/SQL nhưng không gọi được trực tiếp từ SQL nếu chữ ký sử dụng kiểu dữ liệu chỉ thuộc PL/SQL hoặc cấu trúc mà SQL engine không hỗ trợ trong release đó.

Ví dụ, PL/SQL BOOLEAN truyền thống là kiểu PL/SQL; trong các phiên bản Oracle trước khi SQL có kiểu BOOLEAN, không thể dùng một function trả BOOLEAN như một biểu thức SQL thông thường. Oracle Database 23ai bổ sung hỗ trợ SQL BOOLEAN, vì vậy phải xem xét phiên bản khi thiết kế chữ ký.

Tương tự, PL/SQL record, associative array hoặc kiểu collection chỉ khai báo trong block không tự trở thành kiểu dữ liệu SQL có thể truyền qua SQL engine. Khi cần dùng collection/object trong SQL, chọn kiểu SQL được tạo ở schema hoặc package/type hỗ trợ đúng theo phiên bản.

### 1.3. Standalone function

Standalone function được tạo độc lập trong schema:

```sql
CREATE OR REPLACE FUNCTION lab_normalize_code (
    p_code IN VARCHAR2
)
RETURN VARCHAR2
IS
BEGIN
    RETURN UPPER(TRIM(p_code));
END;
/
```

Gọi từ SQL:

```sql
SELECT lab_normalize_code('  ab-123  ') AS normalized_code
FROM dual;
```

Kết quả là AB-123.

### 1.4. Package function

Function cũng có thể là public subprogram trong package. Function cần xuất hiện trong package specification để code bên ngoài package gọi được:

```sql
CREATE OR REPLACE PACKAGE lab_pricing_pkg AS
    FUNCTION price_with_tax (
        p_net_amount IN NUMBER,
        p_tax_rate   IN NUMBER
    ) RETURN NUMBER;
END lab_pricing_pkg;
/

CREATE OR REPLACE PACKAGE BODY lab_pricing_pkg AS
    FUNCTION price_with_tax (
        p_net_amount IN NUMBER,
        p_tax_rate   IN NUMBER
    ) RETURN NUMBER
    IS
    BEGIN
        RETURN p_net_amount * (1 + p_tax_rate);
    END price_with_tax;
END lab_pricing_pkg;
/
```

Gọi từ SQL bằng tên package:

```sql
SELECT lab_pricing_pkg.price_with_tax(100, 0.08)
       AS gross_amount
FROM dual;
```

Function chỉ khai báo trong package body (private function) không thể được gọi trực tiếp từ SQL bên ngoài package.

## 2. Gọi function trong biểu thức SQL

### 2.1. Trong SELECT list

```sql
SELECT
    product_id,
    unit_price,
    lab_price_with_tax(unit_price, 0.08) AS price_after_tax
FROM lab_products;
```

Function được gọi để tính biểu thức cho các hàng kết quả. Nếu query trả nhiều hàng, function có thể được đánh giá nhiều lần. Không giả định một lần gọi cho toàn statement.

### 2.2. Trong WHERE

```sql
SELECT employee_id, employee_name
FROM lab_employees
WHERE lab_normalize_code(employee_code) = 'EMP-001';
```

Function trong WHERE có thể được đánh giá khi Oracle kiểm tra predicate cho các hàng ứng viên. Điều này có thể tạo chi phí lớn nếu function chứa nhiều logic hoặc truy vấn SQL bên trong.

### 2.3. Trong ORDER BY

```sql
SELECT product_id, product_name
FROM lab_products
ORDER BY lab_normalize_code(product_name);
```

Oracle có thể cần tính biểu thức để sắp xếp. Nếu function đắt và query trả nhiều hàng, hãy cân nhắc lưu giá trị chuẩn hóa, dùng biểu thức SQL trực tiếp hoặc function-based index nếu phù hợp.

### 2.4. Trong GROUP BY

```sql
SELECT
    lab_normalize_code(region_code) AS normalized_region,
    COUNT(*) AS customer_count
FROM lab_customers
GROUP BY lab_normalize_code(region_code);
```

Function được dùng để tạo khóa nhóm. Biểu thức GROUP BY cần tương thích với biểu thức SELECT theo quy tắc SQL; alias trong SELECT không phải lúc nào cũng dùng được trong GROUP BY ở mọi phiên bản/cú pháp.

### 2.5. Trong DML

Function có thể được gọi trong biểu thức của DML:

```sql
UPDATE lab_products
SET gross_price = lab_price_with_tax(net_price, tax_rate)
WHERE product_status = 'ACTIVE';
```

Ở đây function chỉ tính và trả một giá trị. DML chính là UPDATE của câu SQL bên ngoài. Function không cần tự chạy UPDATE hoặc COMMIT để tạo kết quả.

### 2.6. Trong INSERT ... SELECT

```sql
INSERT INTO lab_price_snapshot (
    product_id,
    gross_price,
    captured_at
)
SELECT
    product_id,
    lab_price_with_tax(net_price, tax_rate),
    SYSTIMESTAMP
FROM lab_products
WHERE product_status = 'ACTIVE';
```

Function được dùng như một biểu thức tính giá trị cho hàng được INSERT. Nếu query nguồn trả nhiều hàng, function có thể được gọi cho từng hàng theo cách thực thi do Oracle lựa chọn.

### 2.7. Trong MERGE

```sql
MERGE INTO lab_products t
USING lab_product_stage s
ON (t.product_id = s.product_id)
WHEN MATCHED THEN
    UPDATE SET
        t.gross_price =
            lab_price_with_tax(s.net_price, s.tax_rate)
WHEN NOT MATCHED THEN
    INSERT (
        product_id, gross_price
    )
    VALUES (
        s.product_id,
        lab_price_with_tax(s.net_price, s.tax_rate)
    );
```

Function được gọi trong biểu thức UPDATE/INSERT. Hãy giữ function không có tác dụng phụ để việc optimizer thay đổi thứ tự hoặc số lần đánh giá không làm thay đổi nghiệp vụ.

## 3. Function thuần (pure function) là gì?

### 3.1. Định nghĩa thực dụng

Một function thuần có thể hiểu là function:

- Kết quả chỉ phụ thuộc vào các tham số đầu vào.
- Cùng đầu vào trong cùng quy ước sẽ cho cùng đầu ra.
- Không thay đổi dữ liệu trong database.
- Không thay đổi package/global state.
- Không phụ thuộc vào thời gian, user hiện tại, NLS setting, session context hoặc trạng thái bên ngoài nếu các giá trị đó không nằm trong tham số.
- Không gửi email, gọi HTTP, ghi file, ghi log ngoài luồng hoặc tạo side effect khác.

Ví dụ thuần:

```sql
CREATE OR REPLACE FUNCTION lab_net_to_gross (
    p_net   IN NUMBER,
    p_rate  IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN p_net + (p_net * p_rate);
END;
/
```

Function chỉ thực hiện phép toán trên hai tham số. Cùng p_net và p_rate sẽ tạo cùng kết quả.

### 3.2. Function đọc bảng có còn thuần không?

Function đọc bảng cấu hình:

```sql
CREATE OR REPLACE FUNCTION lab_get_tax_rate (
    p_region IN VARCHAR2
)
RETURN NUMBER
IS
    l_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM lab_tax_rates
    WHERE region_code = p_region;

    RETURN l_rate;
END;
/
```

Function này không ghi dữ liệu, nhưng kết quả phụ thuộc trạng thái bảng LAB_TAX_RATES. Nếu bảng thay đổi, cùng tham số p_region có thể trả kết quả khác. Vì vậy nó không thuần theo nghĩa nghiêm ngặt “chỉ phụ thuộc tham số” và không nên gắn DETERMINISTIC nếu không có bảo đảm bổ sung.

Đọc dữ liệu không phải tác dụng phụ ghi, nhưng vẫn là một dependency bên ngoài làm kết quả thay đổi theo thời gian.

### 3.3. Tác dụng phụ là gì?

Tác dụng phụ (side effect) là hành động làm thay đổi trạng thái có thể quan sát bên ngoài kết quả trả về. Ví dụ:

- INSERT/UPDATE/DELETE vào bảng.
- Thay đổi biến package hoặc trạng thái global.
- Ghi audit/log vào bảng.
- Gọi sequence NEXTVAL.
- Gửi email hoặc gọi REST API.
- Ghi file hoặc thao tác hệ thống file.
- COMMIT/ROLLBACK transaction.
- Thay đổi session setting.

Một function trả đúng giá trị nhưng đồng thời gửi email vẫn có tác dụng phụ. Không nên gọi nó như một biểu thức SQL thuần.

### 3.4. Pure không chỉ là không có DML

Function không UPDATE bảng nhưng đọc SYSDATE, SYS_CONTEXT, package variable hoặc NLS setting vẫn có thể cho kết quả khác nhau với cùng tham số. Nếu khai báo function là deterministic hoặc dùng trong index/cache mà không tính các dependency này, kết quả có thể cũ hoặc sai.

Ví dụ function phụ thuộc thời gian:

```sql
CREATE OR REPLACE FUNCTION lab_is_expired (
    p_expiry_date IN DATE
)
RETURN NUMBER
IS
BEGIN
    IF p_expiry_date < SYSDATE THEN
        RETURN 1;
    END IF;
    RETURN 0;
END;
/
```

Cùng p_expiry_date có thể trả 0 hôm nay và 1 ngày mai. Không khai báo function này DETERMINISTIC.

## 4. Giới hạn tác dụng phụ khi function được gọi từ SQL

Oracle đặt các giới hạn cho function chạy trong SQL vì SQL engine cần một biểu thức có thể được đánh giá trong quá trình tối ưu và thực thi câu lệnh. Một function không nên âm thầm thay đổi database hoặc điều khiển transaction trong lúc Oracle đang tính kết quả truy vấn.

### 4.1. Function gọi từ SELECT không được thực hiện DML thông thường

Ví dụ function cố INSERT log:

```sql
CREATE OR REPLACE FUNCTION lab_log_and_return (
    p_value IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    INSERT INTO lab_function_log (
        value_logged,
        logged_at
    )
    VALUES (
        p_value,
        SYSTIMESTAMP
    );

    RETURN p_value;
END;
/
```

Khi gọi:

```sql
SELECT lab_log_and_return(10)
FROM dual;
```

Oracle thường báo:

```text
ORA-14551: cannot perform a DML operation inside a query
```

Lý do: SELECT được kỳ vọng đọc dữ liệu; việc một biểu thức SELECT âm thầm ghi log sẽ tạo side effect khó dự đoán. Oracle không cho DML thông thường trong function được gọi từ query.

### 4.2. Autonomous transaction là ngoại lệ kỹ thuật, không phải thiết kế mặc định

PL/SQL có PRAGMA AUTONOMOUS_TRANSACTION. Một autonomous function/procedure chạy transaction độc lập và có thể COMMIT riêng; điều này có thể cho phép ghi log từ function được gọi trong SELECT.

Ví dụ minh họa:

```sql
CREATE OR REPLACE FUNCTION lab_autonomous_log (
    p_value IN NUMBER
)
RETURN NUMBER
IS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO lab_function_log (
        value_logged,
        logged_at
    )
    VALUES (
        p_value,
        SYSTIMESTAMP
    );

    COMMIT;
    RETURN p_value;
END;
/
```

Đây là kỹ thuật đặc biệt, không phải cách nên dùng để biến một function có side effect thành function an toàn trong SQL. Nếu query đọc 1 triệu hàng, function có thể ghi log rất nhiều lần; optimizer có thể thay đổi số lần gọi; log commit độc lập ngay cả khi câu query bên ngoài thất bại hoặc transaction caller rollback.

Chỉ cân nhắc autonomous transaction cho mục tiêu hẹp như ghi diagnostic log cần tồn tại độc lập, với giới hạn số lần gọi và semantics được hiểu rõ. Không dùng nó để cập nhật business data từ một function trong SELECT.

### 4.3. Function gọi từ DML không được sửa bảng đang bị DML đó thay đổi

Giả sử UPDATE đang sửa LAB_ORDERS nhưng function được gọi trong biểu thức lại cố cập nhật chính LAB_ORDERS:

```sql
UPDATE lab_orders
SET status = lab_change_order_status(order_id)
WHERE order_date < DATE '2025-01-01';
```

Nếu LAB_CHANGE_ORDER_STATUS thực hiện truy vấn hoặc DML không hợp lệ trên chính bảng đang được câu UPDATE thay đổi, Oracle có thể báo lỗi bảng đang biến đổi:

```text
ORA-04091: table is mutating, trigger/function may not see it
```

Không thiết kế function được gọi từ DML để đọc/ghi ngược bảng đang được statement sửa. Hãy chuyển logic thành một câu SQL set-based, dùng bảng staging, hoặc tổ chức lại transaction để dữ liệu được đọc/ghi ở một bước riêng phù hợp.

### 4.4. Không COMMIT hoặc ROLLBACK trong function được gọi từ SQL

Function được gọi từ một query hoặc DML statement không được tự kết thúc transaction của câu SQL gọi nó. Cố thực hiện transaction control hoặc DDL có thể dẫn tới:

```text
ORA-14552: cannot perform a DDL, commit or rollback inside a query or DML
```

DDL thường có implicit commit, vì vậy không thực hiện DDL từ function dùng trong biểu thức SQL. Transaction thuộc quyền điều khiển của caller; procedure ở tầng điều phối thường là nơi phù hợp để quyết định COMMIT/ROLLBACK.

### 4.5. DML trên bảng khác trong function được gọi từ DML

Giới hạn bảng đang bị statement thay đổi cần được phân biệt với việc function thực hiện DML trên một bảng khác. Một số ngữ cảnh có thể cho phép tác động lên bảng khác, nhưng đó vẫn là side effect và có thể gây lỗi transaction, kết quả khó dự đoán hoặc số lần ghi không ổn định.

Thiết kế an toàn vẫn là để function gọi từ SQL chỉ tính và trả giá trị. Nếu cần ghi audit hoặc cập nhật bảng liên quan, thực hiện bằng DML tường minh ở procedure/transaction điều phối thay vì giấu trong biểu thức.

### 4.6. Giới hạn áp dụng cho cả call chain

Nếu function A gọi function B, rồi B gọi procedure C thực hiện DML, side effect vẫn phát sinh trong call chain. Không thể tránh giới hạn bằng cách chuyển DML vào một procedure con hoặc package khác.

Khi điều tra ORA-14551/ORA-14552/ORA-04091, lần theo toàn bộ call stack và xem function có gọi helper, trigger, dynamic SQL hoặc package procedure nào hay không.

## 5. SQL engine và PL/SQL engine: chi phí chuyển ngữ cảnh

Oracle có SQL engine thực thi câu SQL và PL/SQL engine thực thi block/procedure/function. Khi SQL gọi PL/SQL function, việc chuyển điều khiển giữa hai engine có chi phí. Nếu function được gọi cho nhiều hàng, chi phí này có thể tích lũy đáng kể.

### 5.1. Function theo từng hàng

Ví dụ:

```sql
SELECT
    order_id,
    lab_price_with_tax(net_amount, tax_rate)
FROM lab_orders;
```

Nếu bảng có 5 triệu hàng, function có thể được gọi nhiều lần theo số hàng cần tính. Function đơn giản chỉ nhân hai số có thể vẫn tạo overhead lớn hơn biểu thức SQL thuần:

```sql
SELECT
    order_id,
    net_amount * (1 + tax_rate) AS gross_amount
FROM lab_orders;
```

Nếu phép tính có thể biểu diễn bằng SQL trực tiếp, ưu tiên SQL set-based để tránh chuyển engine không cần thiết.

### 5.2. Function thực hiện SELECT bên trong

Function sau truy vấn bảng cấu hình:

```sql
SELECT
    order_id,
    lab_get_tax_rate(region_code)
FROM lab_orders;
```

Nếu có hàng triệu đơn hàng, function có thể thực hiện hàng triệu lần SELECT vào LAB_TAX_RATES. Đây là pattern N+1 query: một truy vấn ngoài cộng với rất nhiều truy vấn nhỏ bên trong function.

Thay bằng JOIN:

```sql
SELECT
    o.order_id,
    r.tax_rate
FROM lab_orders o
JOIN lab_tax_rates r
  ON r.region_code = o.region_code;
```

JOIN cho optimizer thấy toàn bộ quan hệ dữ liệu trong một câu SQL, tạo thêm cơ hội chọn join method, access path và join order.

### 5.3. Không lặp lại cùng phép tính trong nhiều vị trí

Ví dụ:

```sql
SELECT
    lab_expensive_calc(amount) AS calculated_value
FROM lab_orders
WHERE lab_expensive_calc(amount) > 100;
```

Không dựa vào giả định Oracle chỉ tính function một lần rồi dùng lại cho cả SELECT list và WHERE. Optimizer có thể đánh giá biểu thức ở các bước khác nhau, biến đổi query hoặc gọi function số lần khác nhau.

Nếu cần dùng một kết quả tính trung gian, cân nhắc biểu thức SQL, inline view/CTE, lưu cột đã chuẩn hóa, function-based index hoặc cơ chế result cache phù hợp. Ngay cả CTE/inline view cũng không phải cam kết tuyệt đối rằng function chỉ chạy một lần; optimizer có thể inline hoặc biến đổi query.

### 5.4. Function không phải cách thay thế JOIN

Nếu function nhận ID rồi SELECT một mô tả từ bảng khác, ví dụ GET_CUSTOMER_NAME(customer_id), việc gọi function theo từng hàng thường kém rõ ràng hơn JOIN:

```sql
-- Function lookup theo từng hàng:
SELECT
    order_id,
    lab_customer_name(customer_id)
FROM lab_orders;

-- Thể hiện quan hệ trực tiếp:
SELECT
    o.order_id,
    c.customer_name
FROM lab_orders o
JOIN lab_customers c
  ON c.customer_id = o.customer_id;
```

Function vẫn hữu ích cho quy tắc tính toán nhỏ, dùng lại được và không thuận tiện biểu diễn bằng SQL. Nhưng khi dữ liệu liên quan đã nằm trong bảng, JOIN thường là lựa chọn tốt hơn.

## 6. Oracle không bảo đảm số lần hoặc thứ tự gọi function

Một biểu thức function trong SQL không phải callback có thứ tự thực thi do người lập trình kiểm soát. Optimizer có thể:

- Đánh giá predicate trước hoặc sau một điều kiện khác.
- Đẩy predicate vào view hoặc subquery.
- Loại bỏ biểu thức không cần thiết.
- Đánh giá biểu thức ở một bước plan khác.
- Thực hiện song song hoặc theo cách khác tùy plan.
- Gọi function nhiều lần cho các hàng hoặc biểu thức khác nhau.

Vì vậy, function trong SQL không được phụ thuộc vào số lần được gọi, thứ tự được gọi hoặc việc mọi hàng chắc chắn được đánh giá.

### 6.1. Không dùng function để tạo sequence side effect

Không viết function được gọi từ SELECT để gọi NEXTVAL rồi dựa vào thứ tự các giá trị sequence phản ánh thứ tự hàng:

```sql
SELECT
    order_id,
    lab_next_business_number()
FROM lab_orders
ORDER BY order_date;
```

Optimizer không cam kết thứ tự gọi function theo ORDER BY cuối cùng. Thứ tự sắp xếp kết quả và thứ tự biểu thức được đánh giá là hai vấn đề khác nhau.

Nếu cần cấp số cho các hàng, dùng sequence trong DML có chủ đích, hoặc một quy trình INSERT/UPDATE được thiết kế rõ ràng. Không giấu thao tác sinh ID có side effect trong function dùng như biểu thức SELECT.

### 6.2. Không gửi email hoặc gọi HTTP từ function trong SELECT

Một function gọi SMTP/REST API có thể được đánh giá nhiều lần hoặc không theo thứ tự mong muốn. Nếu query bị chạy lại, parallelized hoặc optimizer thay đổi plan, số side effect có thể thay đổi.

Hãy tách việc đọc/tính dữ liệu khỏi quy trình gửi thông báo. Procedure/job/queue worker thực hiện side effect theo event ID hoặc cơ chế deduplication, thay vì gọi dịch vụ ngoài trong SELECT.

### 6.3. Không dựa vào thứ tự predicate để tránh lỗi

Ví dụ:

```sql
SELECT *
FROM lab_values
WHERE is_numeric(value_text) = 1
  AND TO_NUMBER(value_text) > 100;
```

Không giả định Oracle luôn đánh giá IS_NUMERIC trước TO_NUMBER. Optimizer có thể thay đổi thứ tự predicate; hàng có dữ liệu không chuyển được thành số vẫn có thể gây lỗi chuyển đổi.

Viết biểu thức an toàn hơn bằng CASE:

```sql
SELECT *
FROM lab_values
WHERE CASE
          WHEN VALIDATE_CONVERSION(value_text AS NUMBER) = 1
          THEN TO_NUMBER(value_text)
      END > 100;
```

VALIDATE_CONVERSION có từ các phiên bản Oracle hiện đại; nếu release không hỗ trợ, dùng CASE/biểu thức chuyển đổi an toàn phù hợp. Không dùng một function predicate làm hàng rào thứ tự đánh giá.

## 7. DETERMINISTIC: lời khai báo tính xác định

### 7.1. Cú pháp

Function có thể được khai báo DETERMINISTIC:

```sql
CREATE OR REPLACE FUNCTION lab_normalize_code (
    p_code IN VARCHAR2
)
RETURN VARCHAR2
DETERMINISTIC
IS
BEGIN
    RETURN UPPER(TRIM(p_code));
END;
/
```

DETERMINISTIC là lời cam kết của người lập trình rằng function trả cùng kết quả cho cùng bộ tham số đầu vào trong phạm vi ngữ nghĩa của function. Oracle không phân tích toàn bộ logic để chứng minh cam kết này đúng.

### 7.2. DETERMINISTIC không có nghĩa “chỉ chạy một lần”

DETERMINISTIC không bảo đảm:

- Function chỉ được gọi một lần trong statement.
- Oracle luôn cache kết quả.
- Function được gọi theo một thứ tự cụ thể.
- Mọi lần chạy của query đều dùng kết quả cũ.
- Function tự trở nên nhanh hơn.

Đây là thông tin để Oracle có thể sử dụng trong một số tối ưu hóa/cấu trúc phụ thuộc function; không dùng nó làm cơ chế điều khiển số lần gọi.

### 7.3. Không khai báo DETERMINISTIC cho function phụ thuộc trạng thái ngoài tham số

Không khai báo DETERMINISTIC nếu function phụ thuộc:

- SYSDATE, SYSTIMESTAMP hoặc thời gian hiện tại.
- Sequence NEXTVAL.
- Dữ liệu bảng có thể thay đổi.
- Package global variable có thể đổi.
- SYS_CONTEXT, SESSION_USER hoặc tenant hiện tại.
- NLS settings, time zone hoặc cấu hình session.
- File, HTTP service hoặc trạng thái bên ngoài database.

Ví dụ function đọc tỷ lệ thuế từ bảng cấu hình có thể trả kết quả khác nhau sau khi bảng thay đổi; không nên khai báo DETERMINISTIC chỉ vì cùng một vùng thường có cùng tỷ lệ trong ngày.

### 7.4. DETERMINISTIC và function-based index

Function-based index lưu kết quả của biểu thức function cho các hàng. Ví dụ:

```sql
CREATE INDEX ix_lab_customer_code_norm
ON lab_customers (lab_normalize_code(customer_code));
```

Function dùng trong function-based index phải đáp ứng các yêu cầu của Oracle, trong đó function do người dùng định nghĩa cần được khai báo DETERMINISTIC. Quan trọng hơn, function phải thật sự ổn định theo đầu vào và các quy tắc dữ liệu.

Nếu thay đổi implementation của function, index có thể vẫn chứa kết quả tính theo logic cũ. Cần xem xét rebuild index và kiểm thử query sau khi thay function. DETERMINISTIC không tự cập nhật lại các entry đã lưu.

### 7.5. DETERMINISTIC là hợp đồng

Nếu function khai báo DETERMINISTIC nhưng thực tế đọc bảng, đọc thời gian hoặc package state, Oracle có thể sử dụng kết quả theo giả định không đúng. Hậu quả có thể là kết quả sai hoặc index/materialized structure không còn nhất quán với logic mong muốn.

Chỉ khai báo khi có thể chứng minh cùng tham số luôn tạo cùng kết quả và function không có tác dụng phụ. Nếu không chắc, bỏ DETERMINISTIC.

## 8. RESULT_CACHE và khác biệt với DETERMINISTIC

### 8.1. RESULT_CACHE là cơ chế lưu kết quả

PL/SQL function có thể được khai báo RESULT_CACHE để Oracle lưu kết quả theo tham số trong result cache của instance. Khi gọi lại với cùng bộ tham số và các dependency vẫn hợp lệ, Oracle có thể trả kết quả từ cache thay vì thực thi lại thân function.

Ví dụ function đọc bảng tỷ giá:

```sql
CREATE OR REPLACE FUNCTION lab_get_exchange_rate (
    p_currency_code IN VARCHAR2
)
RETURN NUMBER
RESULT_CACHE
IS
    l_rate NUMBER;
BEGIN
    SELECT exchange_rate
    INTO l_rate
    FROM lab_exchange_rates
    WHERE currency_code = p_currency_code;

    RETURN l_rate;
END;
/
```

Oracle theo dõi dependency của result-cached function với các bảng được đọc và có thể invalidation kết quả cache khi dữ liệu dependency thay đổi. Cơ chế invalidation và điều kiện cache phụ thuộc loại object, phiên bản và môi trường.

### 8.2. RESULT_CACHE khác DETERMINISTIC

| Tiêu chí | DETERMINISTIC | RESULT_CACHE |
| --- | --- | --- |
| Ý nghĩa | Người viết cam kết cùng input cho cùng output | Oracle có cơ chế cache kết quả function |
| Oracle lưu kết quả? | Không phải cam kết lưu cache | Có cache kết quả theo cơ chế result cache |
| Dependency bảng | Không tự quản lý tính thay đổi của bảng để bảo đảm lời khai báo | Oracle theo dõi dependency được hỗ trợ và invalidation |
| Tác dụng phụ | Function phải thật sự ổn định; side effect không phù hợp | Function result cache cũng cần function an toàn, không side effect |
| Mục đích | Khai báo tính xác định, hỗ trợ một số tối ưu hóa/index | Giảm thực thi lại function có kết quả tái sử dụng |

Không dùng DETERMINISTIC như từ đồng nghĩa với RESULT_CACHE. Một function có thể deterministic nhưng Oracle không nhất thiết cache kết quả; một result-cached function có thể đọc bảng phụ thuộc và cache được invalidated khi bảng thay đổi.

### 8.3. Khi nào cân nhắc RESULT_CACHE?

- Function thực hiện phép tra cứu hoặc tính toán tương đối tốn kém.
- Cùng bộ tham số được gọi lặp lại thường xuyên.
- Dữ liệu nguồn thay đổi ít hoặc có thể chấp nhận invalidation.
- Kết quả không phụ thuộc trạng thái riêng của session.
- Kết quả đủ nhỏ và có lợi khi lưu trong shared result cache.

### 8.4. Trường hợp không phù hợp

Không dùng RESULT_CACHE nếu function phụ thuộc:

- SYSDATE/SYSTIMESTAMP hoặc dữ liệu thay đổi theo thời gian mà không được đưa vào tham số.
- Package global state.
- Session context, user/tenant hiện tại hoặc NLS setting không được xử lý đúng.
- Sequence, random number hoặc external service có kết quả thay đổi.
- Side effect cần xảy ra mỗi lần gọi.

Ví dụ function gửi email không thể được “tối ưu” bằng result cache; cache có thể làm function không chạy lại và email không được gửi, hoặc hành vi không đúng mong muốn.

### 8.5. Cache không phải cam kết nghiệp vụ

Không dựa vào việc function chắc chắn chạy hay không chạy để tạo side effect. Oracle có thể invalidate hoặc bỏ cache, instance có thể restart, và kết quả có thể được tính lại. Function result cache chỉ là tối ưu hiệu năng; không phải message queue, ledger hoặc cơ chế exactly-once.

## 9. PRAGMA RESTRICT_REFERENCES và các mức purity

Trong PL/SQL, RESTRICT_REFERENCES là pragma dùng để khai báo mức độ một function đọc/ghi database state và package state. Cơ chế này thường gặp trong package legacy hoặc một số ngữ cảnh yêu cầu compiler kiểm tra/đánh giá purity. Với các function mới, không nên thêm pragma chỉ theo thói quen; cần kiểm tra yêu cầu của Oracle release và ngữ cảnh sử dụng.

### 9.1. Bốn mức thường gặp

| Mức | Ý nghĩa |
| --- | --- |
| WNDS | Writes No Database State: không ghi database state |
| RNDS | Reads No Database State: không đọc database state |
| WNPS | Writes No Package State: không ghi package state |
| RNPS | Reads No Package State: không đọc package state |

Ví dụ function chỉ tính toán từ tham số có thể khai báo các mức phù hợp trong package specification:

```sql
CREATE OR REPLACE PACKAGE lab_math_pkg AS
    FUNCTION add_tax (
        p_amount IN NUMBER,
        p_rate   IN NUMBER
    ) RETURN NUMBER;

    PRAGMA RESTRICT_REFERENCES (
        add_tax,
        WNDS,
        RNDS,
        WNPS,
        RNPS
    );
END lab_math_pkg;
/
```

Đoạn pragma là ví dụ về khai báo purity; vị trí và yêu cầu áp dụng cụ thể cần theo cú pháp package và phiên bản Oracle đang dùng.

### 9.2. Đọc/ghi database state

Function có câu SELECT đọc bảng không đáp ứng RNDS vì nó đọc database state. Function có INSERT/UPDATE/DELETE không đáp ứng WNDS vì nó ghi database state.

Một function chỉ tính trên tham số có thể đáp ứng cả RNDS và WNDS, nếu không có truy cập database ẩn trong helper function.

### 9.3. Đọc/ghi package state

Function đọc hoặc sửa biến global được khai báo trong package có thể vi phạm RNPS hoặc WNPS tương ứng. Ví dụ:

```sql
CREATE OR REPLACE PACKAGE lab_state_pkg AS
    g_call_count PLS_INTEGER := 0;

    FUNCTION next_call_count RETURN PLS_INTEGER;
END lab_state_pkg;
/

CREATE OR REPLACE PACKAGE BODY lab_state_pkg AS
    FUNCTION next_call_count RETURN PLS_INTEGER
    IS
    BEGIN
        g_call_count := g_call_count + 1;
        RETURN g_call_count;
    END;
END lab_state_pkg;
/
```

NEXT_CALL_COUNT thay đổi package state và kết quả phụ thuộc lịch sử gọi trong session. Không coi function này là pure hoặc deterministic; không dùng làm biểu thức SQL để tạo số thứ tự nghiệp vụ.

### 9.4. Pragma không thay thế thiết kế thuần

RESTRICT_REFERENCES là khai báo/kiểm tra purity trong các ngữ cảnh mà Oracle áp dụng. Nó không làm một function có side effect trở nên an toàn, không bảo vệ khỏi tác động qua external call không được compiler phân tích đầy đủ và không thay thế việc đọc code/helper dependency. Hãy thiết kế function không có side effect trước; pragma chỉ dùng khi có yêu cầu rõ ràng.

## 10. Function và parallel SQL

Oracle có thể thực thi một số câu SQL bằng parallel execution. Nếu SQL gọi user-defined function, khả năng chạy function trong parallel worker phụ thuộc cách function được khai báo, tính chất function, loại query và phiên bản.

### 10.1. PARALLEL_ENABLE

Function có thể khai báo PARALLEL_ENABLE khi được thiết kế để thực thi an toàn bởi parallel execution servers:

```sql
CREATE OR REPLACE FUNCTION lab_parallel_net_amount (
    p_amount IN NUMBER,
    p_discount IN NUMBER
)
RETURN NUMBER
PARALLEL_ENABLE
IS
BEGIN
    RETURN p_amount * (1 - p_discount);
END;
/
```

Function này chỉ tính từ tham số, không đọc/ghi trạng thái session hoặc package. PARALLEL_ENABLE là cam kết function có thể được gọi trong môi trường parallel phù hợp; nó không bắt Oracle phải chạy query song song và không tự làm function an toàn nếu function có side effect.

### 10.2. Vì sao side effect nguy hiểm trong parallel query?

Nếu function gửi email, ghi log hoặc tăng package variable trong query parallel, các worker có thể thực thi trên các session khác nhau. Không có một biến package chung được cập nhật theo thứ tự hàng như người viết có thể tưởng tượng. Số lần gọi và thứ tự thực thi cũng không ổn định.

Không đặt side effect vào function được dùng trong parallel SQL. Tách việc đọc/tính toán khỏi ghi dữ liệu hoặc gửi message.

### 10.3. Package state và parallel execution

Package state thuộc session. Parallel execution workers có thể có session/state riêng; không dựa vào biến package để chia sẻ bộ đếm hoặc trạng thái giữa các worker. Nếu cần tổng hợp, trả dữ liệu qua SQL result, aggregate hoặc cơ chế đồng bộ được thiết kế riêng.

## 11. Quyền và dependency của SQL-callable function

### 11.1. Quyền EXECUTE

User gọi function trong SQL cần có quyền EXECUTE trên standalone function hoặc package chứa function:

```sql
GRANT EXECUTE ON lab_pricing_pkg TO app;
GRANT EXECUTE ON lab_price_with_tax TO app;
```

Tên function có thể cần schema qualification nếu không có synonym hoặc tên không được phân giải trong schema hiện tại:

```sql
SELECT data_owner.lab_price_with_tax(100, 0.08)
FROM dual;
```

### 11.2. Definer rights và invoker rights

Stored PL/SQL mặc định thường chạy với quyền của owner (AUTHID DEFINER), trừ khi khai báo AUTHID CURRENT_USER. Quyền của function ảnh hưởng tới cách Oracle kiểm tra truy cập các object mà function sử dụng.

Với definer-rights function, owner cần có các object privilege trực tiếp cho static SQL theo quy tắc PL/SQL; quyền chỉ nhận qua role thường không đủ để compile/execute static SQL trong definer-rights unit. Khi function đọc bảng cấu hình, hãy kiểm tra direct grant cho owner.

### 11.3. Function dependency và invalidation

Function có thể phụ thuộc bảng, view, package, type hoặc function khác. Thay đổi object phụ thuộc có thể làm function INVALID hoặc khiến câu SQL gọi function lỗi cho tới khi compile lại.

Kiểm tra object:

```sql
SELECT
    object_name,
    object_type,
    status
FROM user_objects
WHERE object_name IN (
    'LAB_PRICE_WITH_TAX',
    'LAB_PRICING_PKG'
);
```

Xem dependency:

```sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE name IN (
    'LAB_PRICE_WITH_TAX',
    'LAB_PRICING_PKG'
)
ORDER BY name, referenced_owner, referenced_name;
```

Dynamic SQL có thể không tạo dependency metadata đầy đủ như static SQL. Cần tìm trong source code/configuration nếu function xây SQL text lúc chạy.

## 12. Function trong SQL và function-based index

Function-based index lưu kết quả của biểu thức trên mỗi hàng để hỗ trợ tìm kiếm theo biểu thức đó.

### 12.1. Ví dụ chuẩn hóa mã

Function:

```sql
CREATE OR REPLACE FUNCTION lab_normalize_email (
    p_email IN VARCHAR2
)
RETURN VARCHAR2
DETERMINISTIC
IS
BEGIN
    RETURN LOWER(TRIM(p_email));
END;
/
```

Index:

```sql
CREATE INDEX ix_lab_email_norm
ON lab_customers (lab_normalize_email(email));
```

Truy vấn dùng cùng biểu thức:

```sql
SELECT customer_id, email
FROM lab_customers
WHERE lab_normalize_email(email) = LOWER(TRIM(:email));
```

Oracle có thể dùng function-based index nếu biểu thức, statistics và cost estimate phù hợp.

### 12.2. Function phải ổn định

Function dùng trong function-based index cần đáp ứng yêu cầu DETERMINISTIC và thực sự ổn định. Không dùng function đọc bảng tỷ giá, SYSDATE, session context hoặc package variable làm key index nếu giá trị có thể đổi mà index không được tính lại tương ứng.

Nếu sửa logic function, cân nhắc rebuild index để các giá trị biểu thức được tính lại. Việc compile lại function không tự động bảo đảm mọi index entry đã lưu phản ánh implementation mới.

### 12.3. Function trên cột có thể làm mất đường truy cập index thường

Nếu có B-tree index trên EMAIL nhưng query viết:

```sql
WHERE LOWER(TRIM(email)) = :normalized_email
```

index thường trên EMAIL có thể không được dùng như một equality lookup trực tiếp cho biểu thức đã biến đổi. Function-based index trên cùng biểu thức có thể giúp, hoặc ứng dụng có thể lưu cột normalized riêng và bảo đảm chuẩn hóa khi ghi.

### 12.4. Kiểm tra plan

```sql
EXPLAIN PLAN FOR
SELECT customer_id
FROM lab_customers
WHERE lab_normalize_email(email) = LOWER(TRIM('A@EXAMPLE.COM'));

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Không kết luận index bị bỏ qua chỉ vì plan không có INDEX RANGE SCAN; full scan có thể rẻ hơn nếu bảng nhỏ hoặc predicate chọn phần lớn hàng.

## 13. Function khai báo ngay trong câu SQL

Từ Oracle Database 12c, SQL có thể khai báo PL/SQL function cục bộ trong mệnh đề WITH của một câu truy vấn. Function này chỉ có phạm vi trong statement đó, không phải standalone function hay package function được lưu lâu dài.

Ví dụ:

```sql
WITH
    FUNCTION local_gross_price (
        p_net_amount NUMBER,
        p_tax_rate   NUMBER
    ) RETURN NUMBER
    IS
    BEGIN
        RETURN p_net_amount * (1 + p_tax_rate);
    END;
SELECT local_gross_price(100, 0.08) AS gross_amount
FROM dual;
```

Function cục bộ hữu ích khi logic chỉ cần trong một query và không cần tạo schema object. Tuy nhiên:

- Nó vẫn là PL/SQL được gọi trong SQL, nên cần tuân thủ các giới hạn side effect phù hợp.
- Không thể được gọi từ câu SQL khác ngoài statement đã khai báo.
- Không thay thế package function dùng chung.
- Cú pháp và yêu cầu client/tool có thể khác nhau theo release.

Nếu function cần tái sử dụng trong nhiều câu SQL hoặc cần quyền EXECUTE riêng, tạo standalone/package function.

## 14. Mẫu thiết kế an toàn

### 14.1. Function chỉ tính toán từ tham số

Đây là lựa chọn ưu tiên cho function được gọi từ SQL:

```sql
CREATE OR REPLACE FUNCTION lab_discounted_price (
    p_price    IN NUMBER,
    p_discount IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN p_price * (1 - p_discount);
END;
/
```

Gọi:

```sql
SELECT
    product_id,
    lab_discounted_price(unit_price, discount_rate) AS final_price
FROM lab_products;
```

Function không cần truy cập bảng, ghi log hay thay đổi trạng thái. Nếu phép tính ngắn và có thể biểu diễn trực tiếp trong SQL, so sánh với biểu thức inline để giảm overhead.

### 14.2. Dùng JOIN cho dữ liệu tra cứu

Nếu function chỉ tra một thuộc tính từ bảng khác, ưu tiên JOIN:

```sql
-- Có thể gây một lookup cho mỗi hàng:
SELECT
    o.order_id,
    lab_customer_segment(o.customer_id)
FROM lab_orders o;

-- Thể hiện quan hệ dữ liệu trực tiếp:
SELECT
    o.order_id,
    c.segment_code
FROM lab_orders o
JOIN lab_customers c
  ON c.customer_id = o.customer_id;
```

JOIN cho optimizer thấy quan hệ giữa hai bảng và thường dễ mở rộng khi cần thêm điều kiện lọc/tổng hợp.

### 14.3. Tách tính toán và ghi dữ liệu

Nếu cần tính giá trị rồi ghi kết quả, để function chỉ tính và để procedure/SQL điều phối DML:

```sql
CREATE OR REPLACE PROCEDURE recalculate_product_prices
AS
BEGIN
    UPDATE lab_products
    SET gross_price =
        lab_discounted_price(unit_price, discount_rate);
END;
/
```

Ở đây procedure thực hiện UPDATE tường minh; function chỉ trả giá trị. Caller quyết định COMMIT/ROLLBACK.

### 14.4. Ghi audit bằng DML tường minh

Không viết function trong SELECT để vừa trả kết quả vừa ghi audit. Nếu nghiệp vụ cần audit cho một lệnh cập nhật, thực hiện DML chính, chụp row count và ghi audit trong procedure:

```sql
CREATE OR REPLACE PROCEDURE deactivate_old_customers (
    p_cutoff_date IN DATE,
    p_rows_updated OUT PLS_INTEGER
)
AS
BEGIN
    UPDATE lab_customers
    SET status = 'INACTIVE'
    WHERE last_order_date < p_cutoff_date
      AND status = 'ACTIVE';

    p_rows_updated := SQL%ROWCOUNT;

    INSERT INTO lab_audit_log (
        action_name, affected_rows, created_at
    )
    VALUES (
        'DEACTIVATE_OLD_CUSTOMERS',
        p_rows_updated,
        SYSTIMESTAMP
    );
END;
/
```

Business update và audit row thuộc cùng transaction; caller có thể commit cả hai hoặc rollback cả hai.

### 14.5. Trả trạng thái nghiệp vụ bằng kiểu SQL

Nếu function cần trả trạng thái, dùng kiểu dữ liệu SQL phù hợp với phiên bản và contract của ứng dụng, ví dụ NUMBER hoặc VARCHAR2:

```sql
CREATE OR REPLACE FUNCTION lab_is_valid_amount (
    p_amount IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN CASE
        WHEN p_amount IS NOT NULL AND p_amount >= 0 THEN 1
        ELSE 0
    END;
END;
/
```

SQL:

```sql
SELECT order_id
FROM lab_orders
WHERE lab_is_valid_amount(total_amount) = 1;
```

Trong PL/SQL nội bộ, BOOLEAN có thể tự nhiên hơn; khi function cần được gọi từ SQL, chọn kiểu return được SQL hỗ trợ trong release.

## 15. Những anti-pattern nên tránh

### 15.1. DML ẩn trong function của SELECT

SELECT có vẻ chỉ đọc nhưng function âm thầm INSERT/UPDATE log hoặc business table. Kết quả là ORA-14551 hoặc cần autonomous transaction để vượt giới hạn. Tách side effect thành bước riêng.

### 15.2. Function query cùng bảng đang được DML thay đổi

Function gọi từ UPDATE/DELETE đọc hoặc ghi lại bảng đang bị statement sửa có thể gây ORA-04091. Chuyển logic sang SQL set-based, staging hoặc bước xử lý riêng.

### 15.3. Gắn DETERMINISTIC cho function phụ thuộc dữ liệu thay đổi

Đọc bảng, SYSDATE, sequence hoặc package state rồi khai báo DETERMINISTIC có thể làm Oracle dựa trên một cam kết sai. Chỉ khai báo khi kết quả thực sự chỉ phụ thuộc tham số.

### 15.4. Dùng function trong WHERE cho mọi hàng khi có thể dùng JOIN

Function tra cứu dữ liệu trong bảng khác theo từng hàng tạo nhiều lần gọi PL/SQL/SQL. Dùng JOIN hoặc biểu thức SQL set-based.

### 15.5. Dựa vào thứ tự predicate

Không giả định điều kiện kiểm tra dữ liệu hợp lệ sẽ luôn được đánh giá trước TO_NUMBER. Optimizer có thể thay đổi thứ tự predicate; viết CASE hoặc conversion an toàn.

### 15.6. Dùng package variable làm bộ đếm trong SQL

Package state thuộc session và không phải bộ đếm theo thứ tự hàng. Trong parallel execution, worker có state riêng. Nếu cần sequence, dùng sequence tường minh; nếu cần tổng hợp, dùng aggregate hoặc bảng/sequence theo semantics phù hợp.

### 15.7. Gọi external service từ function

Gửi email, gọi HTTP hoặc ghi file trong function SQL khiến số lần side effect phụ thuộc cách statement được thực thi. Dùng job, queue, outbox hoặc procedure được gọi một lần theo ranh giới nghiệp vụ.

### 15.8. Function quá lớn trong SELECT

Function chứa nhiều SELECT, nhiều nhánh PL/SQL và gọi nhiều helper có thể khó tối ưu và khó nhìn thấy chi phí trong execution plan. Chuyển phép biến đổi dữ liệu về SQL set-based nếu có thể; giữ function cho quy tắc tính toán có ranh giới rõ.

## 16. Bài thực hành: function thuần và function có tác dụng phụ

Các bước sau chạy trong schema lab. Tạo bảng một lần; đổi tiền tố nếu tên đã tồn tại.

### 16.1. Tạo bảng sản phẩm

```sql
CREATE TABLE lab_sql_products (
    product_id NUMBER(10) PRIMARY KEY,
    product_name VARCHAR2(100) NOT NULL,
    net_price NUMBER(12, 2) NOT NULL,
    tax_rate NUMBER(5, 4) NOT NULL,
    gross_price NUMBER(12, 2)
);

INSERT INTO lab_sql_products VALUES
(1, 'Keyboard', 500000, 0.08, NULL);
INSERT INTO lab_sql_products VALUES
(2, 'Monitor', 3000000, 0.10, NULL);
INSERT INTO lab_sql_products VALUES
(3, 'Mouse', 250000, 0.08, NULL);
COMMIT;
```

### 16.2. Tạo function thuần

```sql
CREATE OR REPLACE FUNCTION lab_sql_gross_price (
    p_net_price IN NUMBER,
    p_tax_rate  IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN p_net_price * (1 + p_tax_rate);
END;
/
```

Gọi từ SQL:

```sql
SELECT
    product_id,
    product_name,
    lab_sql_gross_price(net_price, tax_rate) AS gross_price
FROM lab_sql_products
ORDER BY product_id;
```

Kết quả phải là giá đã cộng thuế cho ba sản phẩm.

### 16.3. Dùng function trong UPDATE

```sql
DECLARE
    l_rows PLS_INTEGER;
BEGIN
    UPDATE lab_sql_products
    SET gross_price =
        lab_sql_gross_price(net_price, tax_rate);

    l_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('Updated rows = ' || l_rows);
END;
/
```

Kết quả mong đợi với dữ liệu mẫu: 3 hàng được UPDATE. Nếu không muốn lưu thay đổi, ROLLBACK ở caller; nếu muốn giữ, COMMIT theo quy trình lab.

### 16.4. Tạo function cố ghi log

```sql
CREATE TABLE lab_sql_function_log (
    log_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    input_value NUMBER,
    logged_at TIMESTAMP
);

CREATE OR REPLACE FUNCTION lab_sql_impure_value (
    p_value IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    INSERT INTO lab_sql_function_log (
        input_value, logged_at
    )
    VALUES (
        p_value, SYSTIMESTAMP
    );

    RETURN p_value;
END;
/
```

Thử gọi:

```sql
SELECT lab_sql_impure_value(10)
FROM dual;
```

Trong query thông thường, dự kiến nhận ORA-14551 vì function thực hiện DML. Đây là minh họa cho giới hạn side effect.

### 16.5. Thử autonomous transaction có kiểm soát

Trong schema lab, có thể tạo phiên bản autonomous để quan sát ngoại lệ kỹ thuật:

```sql
CREATE OR REPLACE FUNCTION lab_sql_autonomous_log (
    p_value IN NUMBER
)
RETURN NUMBER
IS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO lab_sql_function_log (
        input_value, logged_at
    )
    VALUES (
        p_value, SYSTIMESTAMP
    );

    COMMIT;
    RETURN p_value;
END;
/
```

Chạy SELECT function và kiểm tra log. Sau đó rollback transaction caller (nếu có) và quan sát log autonomous vẫn còn vì nó commit độc lập. Bài lab cho thấy tại sao không nên dùng autonomous transaction để ghi business data ẩn trong SELECT.

### 16.6. Thử function phụ thuộc thời gian

```sql
CREATE OR REPLACE FUNCTION lab_sql_is_past (
    p_date IN DATE
)
RETURN NUMBER
IS
BEGIN
    RETURN CASE
        WHEN p_date < SYSDATE THEN 1
        ELSE 0
    END;
END;
/
```

Gọi cùng một ngày vào các thời điểm khác nhau có thể trả kết quả khác. Không khai báo function này DETERMINISTIC và không dùng trong function-based index với giả định kết quả bất biến.

### 16.7. Dọn dữ liệu lab

Chỉ xóa các đối tượng test khi không còn cần:

```sql
DROP FUNCTION lab_sql_is_past;
DROP FUNCTION lab_sql_autonomous_log;
DROP FUNCTION lab_sql_impure_value;
DROP FUNCTION lab_sql_gross_price;
DROP TABLE lab_sql_function_log PURGE;
DROP TABLE lab_sql_products PURGE;
```

Nếu một đối tượng chưa được tạo hoặc đã xóa, câu DROP tương ứng sẽ báo lỗi. Chỉ chạy trong schema lab.

## 17. Lỗi thường gặp và hướng xử lý

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-14551 | Function được gọi từ query thực hiện DML thông thường | Bỏ DML khỏi function; tách sang procedure/transaction |
| ORA-14552 | Function được gọi từ query/DML thực hiện DDL, COMMIT hoặc ROLLBACK | Để caller điều khiển transaction và DDL |
| ORA-04091 | Function/trigger đọc hoặc sửa bảng đang bị DML thay đổi | Chuyển logic sang statement set-based hoặc bước riêng |
| ORA-06575 | Function không hợp lệ hoặc compile error | Xem USER_ERRORS, compile lại và kiểm tra dependency |
| ORA-00904 / function không được nhận diện | Tên/schema/package hoặc chữ ký không đúng | Kiểm tra owner, package spec, synonym và quyền EXECUTE |
| ORA-06553 / PLS-... khi gọi từ SQL | Kiểu tham số/return không tương thích SQL hoặc chữ ký sai | Dùng kiểu SQL được hỗ trợ trong release |
| ORA-01031 | Thiếu EXECUTE hoặc direct object privilege cho definer-rights unit | Cấp quyền phù hợp và kiểm tra AUTHID |
| Kết quả DETERMINISTIC bị cũ/sai | Function phụ thuộc bảng, thời gian, session hoặc package state | Bỏ DETERMINISTIC; xem xét cache/dependency đúng cách |
| Function gọi quá nhiều lần | SQL gọi function cho nhiều hàng/biểu thức | Dùng SQL set-based, JOIN, giảm số hàng trước khi gọi |
| Query không dùng index thường | Function bọc cột trong predicate | Cân nhắc function-based index hoặc cột normalized |
| Function có side effect chạy số lần bất ngờ | Optimizer thay đổi plan/evaluation | Loại side effect khỏi function SQL |
| Parallel query cho kết quả trạng thái không nhất quán | Function dựa package/session state hoặc side effect | Dùng function stateless, kiểm tra PARALLEL_ENABLE |

## 18. Kiểm tra function và trạng thái compile

### 18.1. Xem function trong schema

```sql
SELECT
    object_name,
    object_type,
    status
FROM user_objects
WHERE object_type IN ('FUNCTION', 'PACKAGE', 'PACKAGE BODY')
ORDER BY object_type, object_name;
```

### 18.2. Xem lỗi compile

```sql
SELECT
    name,
    type,
    line,
    position,
    text
FROM user_errors
ORDER BY name, sequence;
```

### 18.3. Compile lại function

```sql
ALTER FUNCTION lab_sql_gross_price COMPILE;
```

Với package:

```sql
ALTER PACKAGE lab_pricing_pkg COMPILE;
ALTER PACKAGE lab_pricing_pkg COMPILE BODY;
```

Compile thành công không chứng minh function thuần hoặc đúng nghiệp vụ. Cần xem code, dependency, quyền và hành vi thực thi.

### 18.4. Đo chi phí

Để so sánh function với biểu thức SQL/JOIN:

- Chạy trên cùng dữ liệu và bind values.
- So sánh execution plan và actual row counts.
- Quan sát elapsed time, CPU, buffer gets và physical reads.
- Chạy đủ nhiều lần để phân biệt parse, cache warm-up và execution.
- Kiểm tra cả độ trễ function lẫn chi phí SQL bên trong function.
- Không dùng một lần chạy đơn lẻ làm kết luận.

SQL Trace/TKPROF hoặc SQL Monitor (nếu được cấp quyền và license phù hợp) có thể giúp điều tra truy vấn phức tạp. Không bật trace diện rộng trên production nếu chưa có kế hoạch về overhead và dung lượng.

## 19. Nguyên tắc thực hành tốt

1. **Giữ function gọi từ SQL càng thuần càng tốt.** Nhận tham số, tính toán, trả kết quả.
2. **Không giấu DML trong SELECT.** Tách thay đổi dữ liệu sang procedure hoặc DML tường minh.
3. **Không COMMIT/ROLLBACK/DDL trong function SQL.** Caller điều khiển transaction.
4. **Tránh truy cập bảng đang bị statement thay đổi.** Thiết kế set-based hoặc tách bước.
5. **Dùng JOIN thay function lookup theo từng hàng.** Để optimizer nhìn thấy quan hệ dữ liệu.
6. **Không giả định số lần/thứ tự gọi.** SQL optimizer có quyền biến đổi kế hoạch.
7. **Chỉ khai báo DETERMINISTIC khi thật sự đúng.** Cùng input phải cho cùng output; không phụ thuộc trạng thái thay đổi ngoài tham số.
8. **Phân biệt RESULT_CACHE và DETERMINISTIC.** Một là cache kết quả, một là lời cam kết tính xác định.
9. **Không dùng autonomous transaction để che side effect.** Chỉ dùng cho nhu cầu độc lập hẹp như diagnostic logging đã được đánh giá.
10. **Kiểm tra kiểu dữ liệu SQL.** Chữ ký function phải tương thích với SQL engine của phiên bản.
11. **Cẩn thận với package state.** Trạng thái session làm function khó dự đoán và không phù hợp parallel execution.
12. **Dùng PARALLEL_ENABLE có trách nhiệm.** Chỉ khai báo nếu function thực sự an toàn trong parallel workers.
13. **Đánh giá function-based index.** Function phải ổn định và thay đổi logic có thể cần rebuild index.
14. **Quản lý EXECUTE privilege và direct grants.** Kiểm tra definer/invoker rights.
15. **Theo dõi dependency và compile status.** Thay bảng/package có thể làm function INVALID.
16. **Benchmark cả query và DML.** Function có thể tiện tái sử dụng nhưng tạo context switch hoặc N+1 SQL.

## 20. Câu hỏi tự kiểm tra

1. Function PL/SQL khác procedure ở điểm nào?
2. Function được tạo trong package body nhưng không có trong package spec có gọi trực tiếp từ SQL bên ngoài được không?
3. Vì sao function dùng PL/SQL-only type có thể không gọi được từ SQL?
4. Những vị trí nào trong SQL thường có thể gọi function?
5. Function thuần phụ thuộc vào yếu tố nào để trả kết quả?
6. Đọc bảng cấu hình có phải tác dụng phụ ghi không? Vì sao vẫn ảnh hưởng tính thuần?
7. Vì sao function ghi bảng được gọi từ SELECT có thể nhận ORA-14551?
8. Autonomous transaction có thể thay đổi hành vi đó như thế nào và vì sao không nên lạm dụng?
9. ORA-14552 thường liên quan hành động nào?
10. Vì sao function gọi từ UPDATE không nên truy cập bảng đang được UPDATE?
11. Vì sao side effect qua function con vẫn là side effect của call chain?
12. SQL engine/PLSQL engine context switch có thể ảnh hưởng query hàng triệu dòng như thế nào?
13. Vì sao JOIN thường tốt hơn function SELECT lookup theo từng hàng?
14. Optimizer có bảo đảm function được gọi đúng một lần cho mỗi hàng hoặc theo thứ tự ORDER BY không?
15. DETERMINISTIC có tự động cache kết quả không?
16. Những dependency nào khiến function không phù hợp DETERMINISTIC?
17. RESULT_CACHE khác DETERMINISTIC ra sao?
18. WNDS, RNDS, WNPS và RNPS mô tả điều gì?
19. PARALLEL_ENABLE có bảo đảm query chạy parallel không?
20. Vì sao function dùng trong function-based index phải ổn định và cần cân nhắc rebuild khi đổi logic?
21. Khi nào nên dùng package function và khi nào nên dùng WITH FUNCTION?
22. Những quyền nào cần kiểm tra khi user khác gọi stored function?

## 21. Mô hình ghi nhớ

```text
SQL GỌI PL/SQL FUNCTION
        |
        v
  Đầu vào SQL-compatible
        |
        v
  FUNCTION TÍNH TOÁN
        |
        +-- Pure: kết quả theo tham số
        +-- Không DML/DDL/COMMIT trong query
        +-- Không side effect ẩn
        +-- Không phụ thuộc call order/count
        |
        v
  SQL ENGINE TỐI ƯU VÀ THỰC THI
        |
        +-- Có thể gọi nhiều lần
        +-- Có thể biến đổi thứ tự đánh giá
        +-- Có thể thực thi parallel nếu phù hợp
        |
        v
  QUẢN LÝ HIỆU NĂNG
        |
        +-- SQL set-based / JOIN trước
        +-- DETERMINISTIC chỉ khi đúng
        +-- RESULT_CACHE khi có lợi
        +-- Function-based index khi cần
        |
        v
  SIDE EFFECT / TRANSACTION
        |
        +-- Procedure/DML tường minh
        +-- Caller quyết định COMMIT/ROLLBACK
        +-- Outbox/job cho external service
```

**Điểm cần nhớ:** function được gọi từ SQL nên chủ yếu là một biểu thức tính toán có thể được optimizer đánh giá theo cách của SQL. Hãy giữ function thuần, tránh DML và transaction control ẩn, không dựa vào số lần/thứ tự gọi, và ưu tiên JOIN/SQL set-based khi dữ liệu đã nằm trong bảng. DETERMINISTIC là cam kết của người viết; RESULT_CACHE là cơ chế cache; cả hai không biến một function có side effect thành function an toàn.

# SQL macro và điều kiện sử dụng theo release/update

SQL macro là cơ chế cho phép đóng gói một phần SQL thành thành phần có tham số, sau đó sử dụng thành phần đó ngay trong câu SQL gọi. Thay vì viết một PL/SQL function chạy cho từng dòng và trả về một giá trị, macro tạo ra một biểu thức SQL hoặc một query expression để Oracle mở rộng vào câu lệnh chính.

SQL macro hữu ích khi nhiều truy vấn lặp lại cùng một phép tính, bộ lọc, join hoặc cấu trúc truy vấn. Macro giúp chuẩn hóa logic, cho phép truyền tham số và để optimizer nhìn thấy SQL sau khi mở rộng. Tuy nhiên, khả năng của macro phụ thuộc mạnh vào phiên bản Oracle và Release Update (RU). Đặc biệt cần phân biệt:

- Oracle Database 19c hỗ trợ table SQL macro; cách khai báo là function PL/SQL có SQL_MACRO và macro chỉ dùng trong FROM.
- Oracle Database 21c hỗ trợ cả table macro và scalar macro qua SQL_MACRO(TABLE) hoặc SQL_MACRO(SCALAR).
- Các release 23ai có những thay đổi theo RU. Oracle công bố bản 23.26.4 cho phép dùng macro trong WITH clause; không nên suy rộng tính năng này cho mọi RU 23ai.
- Oracle AI Database 26ai bổ sung cú pháp SQL native CREATE MACRO, định nghĩa trực tiếp SQL expression/query thay vì trả SQL text từ PL/SQL function.

Một ứng dụng có thể chạy trên 19c nhưng không chạy được ví dụ scalar macro hoặc CREATE MACRO lấy từ tài liệu 21c/26ai. Vì vậy, trước khi chọn cú pháp, phải xác định đúng database release, RU, service/PDB và môi trường RAC.

## 1. SQL macro giải quyết vấn đề gì?

View thông thường đóng gói một query để tái sử dụng:

~~~sql
CREATE OR REPLACE VIEW department_totals_v AS
SELECT department_id,
       COUNT(*) AS employee_count,
       SUM(salary) AS total_salary
FROM employees
GROUP BY department_id;
~~~

View giúp không phải viết lại GROUP BY, nhưng view không nhận tham số theo cách function nhận tham số. Nếu một truy vấn muốn tính tổng từ một ngày tuyển dụng cụ thể, có thể phải lọc ở query bên ngoài hoặc viết lại logic. Với các query phức tạp có analytic function, grouping hoặc nhiều nhánh điều kiện, việc đặt filter ở đúng tầng có thể quan trọng đối với kết quả.

SQL macro cho phép định nghĩa query có tham số:

~~~sql
SELECT *
FROM employees_hired_since(DATE '2025-01-01');
~~~

Tên macro được dùng trong FROM như một table expression. Macro mở rộng thành query tương ứng, có tham số được đưa vào biểu thức SQL.

Scalar macro giải quyết một nhu cầu khác: tái sử dụng biểu thức tính toán:

~~~sql
SELECT order_id,
       net_amount(gross_amount, discount_rate) AS amount_after_discount
FROM orders;
~~~

Trong các phiên bản hỗ trợ scalar macro, net_amount có thể mở rộng thành biểu thức SQL để optimizer xử lý cùng câu query.

### 1.1 Macro không phải function trả dữ liệu từng dòng

Phân biệt các cơ chế:

| Cơ chế | Kết quả/hoạt động | Vị trí sử dụng điển hình |
|---|---|---|
| View | Một query được lưu trong database | FROM |
| SQL table macro | Query expression được mở rộng vào SQL gọi | FROM; một số release mới cho phép macro trong WITH |
| SQL scalar macro | Biểu thức SQL được mở rộng vào SQL gọi | SELECT, WHERE, GROUP BY, HAVING, ORDER BY tùy release |
| PL/SQL function thông thường | Giá trị do PL/SQL tính và trả về | Biểu thức SQL nếu kiểu và quyền phù hợp |
| Pipelined table function | PL/SQL tạo và phát các dòng qua pipeline | FROM |
| Polymorphic table function | Kết quả table shape/row behavior được điều khiển qua interface PL/SQL | FROM |
| Inline view / CTE | Query con viết trực tiếp trong câu SQL | FROM / WITH |

SQL macro không tự đọc từng dòng rồi trả từng dòng qua PL/SQL. Function macro được gọi để tạo SQL text; Oracle mở rộng phần SQL đó và thực thi query sau khi parse/optimize. Vì thế macro thường tránh được context switch SQL-to-PL/SQL trên từng dòng như một PL/SQL function thông thường.

Điều này không bảo đảm mọi macro đều nhanh hơn. Query sau khi mở rộng vẫn có thể có join lớn, cardinality estimate kém, predicate không sargable, bind sensitivity hoặc kế hoạch thực thi không tốt. Cần đo execution plan và runtime statistics.

## 2. Vòng đời của function-based SQL macro

Trong mô hình SQL_MACRO dựa trên PL/SQL function, luồng khái quát:

~~~text
Ứng dụng gửi câu SQL
        |
        v
Oracle parse câu SQL
        |
        v
Nhận diện lời gọi SQL macro
        |
        v
Chạy phần thân macro để tạo SQL text
        |
        v
Mở rộng tham số vào SQL expression/query
        |
        v
Parse và optimize SQL đã mở rộng
        |
        v
Thực thi SQL và trả kết quả
~~~

Function macro thường được xử lý trong giai đoạn parse/hard parse để tạo SQL text. Nó không được gọi như một phép tính PL/SQL cho mỗi dòng kết quả. SQL text sau khi mở rộng là phần optimizer nhìn thấy.

### 2.1 Macro trả về SQL text

Function-based SQL macro phải trả về kiểu ký tự được hỗ trợ như VARCHAR2, CHAR hoặc CLOB. Giá trị trả về là đoạn SQL hợp lệ, ví dụ:

~~~sql
RETURN q'[
    SELECT order_id, customer_id
    FROM sales.orders
]';
~~~

Đoạn text được trả về không phải dữ liệu kết quả. Nó là query expression được chèn vào câu SQL đang gọi.

### 2.2 Khi gọi function macro trực tiếp trong PL/SQL

Nếu gọi function được đánh dấu SQL_MACRO từ một block PL/SQL, function hoạt động như function thông thường trả về chuỗi ký tự; không có macro expansion như khi được tham chiếu từ SQL statement.

Ví dụ:

~~~sql
DECLARE
    l_sql VARCHAR2(4000);
BEGIN
    l_sql := employees_hired_since(DATE '2025-01-01');
    DBMS_OUTPUT.PUT_LINE(l_sql);
END;
/
~~~

Đây không phải cách chạy query macro để lấy rows. Nó chỉ gọi function và nhận SQL text theo hành vi PL/SQL thông thường. Muốn Oracle mở rộng macro, hãy gọi macro trong SQL ở vị trí được release hỗ trợ.

## 3. Điều kiện theo release và update

Đây là phần cần kiểm tra trước khi dùng SQL macro trong dự án.

### 3.1 Ma trận khả năng

| Database release/update | Function-based table macro | Function-based scalar macro | Macro trong WITH | Native CREATE MACRO |
|---|---|---|---|---|
| 19c trước RU có feature | Không nên giả định có | Không | Không | Không |
| 19c RU có hỗ trợ table macro | Có | Không | Không theo restriction trước 23.26.4 | Không |
| 21c | Có | Có | Không theo restriction trước 23.26.4 | Không |
| 23ai / 23.x trước 23.26.4 | Có | Có | Không theo restriction trước 23.26.4 | Không |
| 23.26.4 | Có | Có | Oracle công bố restriction dùng macro trong WITH được gỡ | Không |
| 26ai | Có | Có | Có | Có |

Ma trận này tách ba cơ chế khác nhau: table/scalar SQL_MACRO trên PL/SQL function, khả năng dùng macro trong WITH theo RU, và object macro được định nghĩa bằng CREATE MACRO. Không được nhìn thấy chữ "SQL macro supported" rồi kết luận mọi cú pháp đều có.

### 3.2 Oracle Database 19c

Oracle Database SQL Language Reference và PL/SQL Language Reference 19c ghi nhận table SQL macro bắt đầu được hỗ trợ ở 19c Release 19.7. Một bài viết của Oracle Developer Advocate tháng 10/2026 mô tả macro có từ 19c 19.6. Vì tài liệu Oracle công khai có khác biệt về mốc RU, hãy dùng RU được xác nhận trong tài liệu cho đúng bản cài đặt và kiểm tra bằng test trên môi trường mục tiêu; nếu cần baseline thận trọng theo SQL/PLSQL Language Reference 19c, lấy 19.7 làm mốc tài liệu.

Các đặc điểm cần nhớ ở 19c:

- Chỉ có table SQL macro.
- Macro được khai báo bằng PL/SQL function với SQL_MACRO.
- Không khai báo SCALAR.
- SQL_MACRO mặc định là table macro; cú pháp TABLE/SCALAR tường minh thuộc các release mới hơn.
- Macro chỉ được dùng trong FROM clause của query table expression.
- Không dùng macro trong SELECT list hoặc WHERE như scalar macro.
- Không dùng macro trong virtual column, function-based index, editioning view hoặc materialized view.
- Return type phải là VARCHAR2, CHAR hoặc CLOB.
- Không kết hợp SQL_MACRO với RESULT_CACHE, PARALLEL_ENABLE hoặc PIPELINED.

Ví dụ cú pháp 19c:

~~~sql
CREATE OR REPLACE FUNCTION orders_for_customer (
    p_customer_id NUMBER
)
RETURN VARCHAR2
SQL_MACRO
IS
BEGIN
    RETURN q'[
        SELECT order_id,
               customer_id,
               order_date,
               status
        FROM sales.orders
        WHERE customer_id = orders_for_customer.p_customer_id
    ]';
END;
/
~~~

Gọi:

~~~sql
SELECT order_id, order_date, status
FROM orders_for_customer(:customer_id)
ORDER BY order_date DESC;
~~~

Không viết SQL_MACRO(TABLE) trong ví dụ dành cho 19c nếu đang theo cú pháp 19c được tài liệu hóa; để mặc định table macro.

### 3.3 Oracle Database 21c

Oracle Database 21c hỗ trợ cả hai loại:

- SQL_MACRO(TABLE): macro trả table expression, dùng trong FROM.
- SQL_MACRO(SCALAR): macro trả scalar expression, dùng tại vị trí cho phép biểu thức scalar.

Ví dụ table macro:

~~~sql
CREATE OR REPLACE FUNCTION orders_for_customer (
    p_customer_id NUMBER
)
RETURN VARCHAR2
SQL_MACRO(TABLE)
IS
BEGIN
    RETURN q'[
        SELECT order_id,
               customer_id,
               order_date,
               status
        FROM sales.orders
        WHERE customer_id = orders_for_customer.p_customer_id
    ]';
END;
/
~~~

Ví dụ scalar macro:

~~~sql
CREATE OR REPLACE FUNCTION net_amount (
    p_gross_amount NUMBER,
    p_discount_rate NUMBER
)
RETURN VARCHAR2
SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[
        p_gross_amount * (1 - NVL(p_discount_rate, 0))
    ]';
END;
/
~~~

Gọi:

~~~sql
SELECT order_id,
       net_amount(gross_amount, discount_rate) AS net_amount
FROM sales.orders;
~~~

Scalar macro không dùng trong FROM như table macro. Nó được sử dụng ở các vị trí cho phép scalar expression, chẳng hạn SELECT list, WHERE, ORDER BY hoặc các biểu thức SQL khác theo quy tắc của release.

21c là innovation release. Khi triển khai hệ thống dài hạn, ngoài khả năng cú pháp cần kiểm tra cả support lifecycle và kế hoạch nâng cấp database.

### 3.4 Oracle Database 23ai và RU 23.26.4

Các release 23ai tiếp tục hỗ trợ function-based SQL macro. Một điểm thay đổi cụ thể được Oracle công bố trong bài viết ngày 21/10/2026 là từ release 23.26.4, restriction trước đó về sử dụng macro trong WITH clause được gỡ.

Điều này quan trọng khi query được tổ chức bằng common table expression:

~~~sql
WITH recent_orders AS (
    SELECT *
    FROM orders_for_customer(:customer_id)
)
SELECT customer_id,
       COUNT(*) AS order_count
FROM recent_orders
GROUP BY customer_id;
~~~

Không áp dụng ví dụ này cho mọi RU 23ai mà chưa kiểm tra. Nếu database chạy RU cũ hơn, macro trong WITH có thể bị từ chối dù cùng function macro hoạt động trong FROM của một query đơn giản.

Một số cú pháp SQL khác cũng có mốc RU riêng. Ví dụ GROUP BY ALL được bổ sung trong 23.9 theo tài liệu Oracle; đừng đưa cú pháp đó vào ví dụ được tuyên bố tương thích 19c. SQL macro có mặt không đồng nghĩa mọi cú pháp SQL mới đều có mặt.

### 3.5 Oracle AI Database 26ai và CREATE MACRO

26ai bổ sung cú pháp native CREATE MACRO. Thay vì tạo PL/SQL function trả về chuỗi SQL, macro được định nghĩa bằng SQL expression hoặc query trực tiếp.

Ví dụ table macro:

~~~sql
CREATE OR REPLACE MACRO orders_since (
    p_start_date DATE
) AS
    SELECT order_id,
           customer_id,
           order_date,
           status
    FROM sales.orders
    WHERE order_date >= p_start_date;
~~~

Gọi:

~~~sql
SELECT order_id, customer_id, status
FROM orders_since(DATE '2026-01-01');
~~~

Ví dụ scalar macro:

~~~sql
CREATE OR REPLACE MACRO price_tier (
    p_base_price NUMBER
) AS
    CASE
        WHEN p_base_price >= 1000 THEN 'PREMIUM'
        WHEN p_base_price >= 500 THEN 'STANDARD'
        WHEN p_base_price >= 100 THEN 'BASIC'
        ELSE 'ENTRY'
    END;
~~~

Gọi:

~~~sql
SELECT product_id,
       price_tier(unit_price) AS tier
FROM products;
~~~

Native macro không đặt SQL expression bên trong string literal. Oracle parse và kiểm tra SQL definition khi tạo macro. Điều này giúp phát hiện lỗi cú pháp và một số lỗi semantic sớm hơn so với function-based macro, nơi function có thể compile dù SQL text nó trả về chưa hợp lệ.

Theo hướng dẫn Oracle công bố, CREATE MACRO là cú pháp chỉ có trong 26ai. Nếu hệ thống đang chạy 19c, 21c hoặc 23ai, hãy dùng function-based SQL_MACRO phù hợp release; không copy DDL CREATE MACRO vào môi trường chưa hỗ trợ.

### 3.6 Không suy ra feature chỉ từ major version

Khi kiểm tra một database, cần ghi nhận:

- Full version và release.
- RU/RUR hoặc patch level đang cài.
- CDB/PDB và service mà ứng dụng kết nối.
- Tất cả instance trong RAC có hỗ trợ feature hay không.
- JDBC driver tương thích với database.
- Tài liệu SQL Language Reference và PL/SQL Language Reference đúng release.
- Các restriction được thêm/bỏ trong RU cụ thể.

Oracle yêu cầu trong môi trường RAC tất cả instance phải hỗ trợ macro trước khi tạo native macro. Trong rolling patch hoặc môi trường có node version khác nhau, kiểm tra trạng thái từng instance và thời điểm feature được phép dùng.

## 4. Cách tạo table SQL macro trên 19c

Table macro là dạng macro cơ bản và có mặt trong 19c RU hỗ trợ feature.

### 4.1 Ví dụ lọc đơn hàng theo khách hàng

Giả sử bảng:

~~~sql
CREATE TABLE sales.orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR2(20),
    total_amount NUMBER(12, 2)
);
~~~

Tạo macro:

~~~sql
CREATE OR REPLACE FUNCTION orders_for_customer (
    p_customer_id NUMBER
)
RETURN VARCHAR2
SQL_MACRO
IS
BEGIN
    RETURN q'[
        SELECT order_id,
               customer_id,
               order_date,
               status,
               total_amount
        FROM sales.orders
        WHERE customer_id = orders_for_customer.p_customer_id
    ]';
END;
/
~~~

Gọi:

~~~sql
SELECT order_id,
       order_date,
       status,
       total_amount
FROM orders_for_customer(1001)
ORDER BY order_date DESC;
~~~

Macro tạo một table expression tương đương inline view chứa filter. Query bên ngoài có thể tiếp tục filter, join, aggregate hoặc sort.

### 4.2 Truyền bind variable

Trong JDBC hoặc SQL client, có thể truyền bind variable:

~~~sql
SELECT order_id, status
FROM orders_for_customer(:p_customer_id);
~~~

Bind variable vẫn là bind variable trong câu SQL được mở rộng. Không nối giá trị bind vào SQL text trong thân macro.

### 4.3 Tái sử dụng filter theo trạng thái

~~~sql
CREATE OR REPLACE FUNCTION orders_by_status (
    p_status VARCHAR2
)
RETURN VARCHAR2
SQL_MACRO
IS
BEGIN
    RETURN q'[
        SELECT order_id,
               customer_id,
               order_date,
               status,
               total_amount
        FROM sales.orders
        WHERE status = orders_by_status.p_status
    ]';
END;
/
~~~

Gọi:

~~~sql
SELECT *
FROM orders_by_status(:status);
~~~

Tên tham số được tham chiếu bên trong returned SQL bằng macro name và parameter name. Cách viết có qualification giúp phân biệt parameter với column cùng tên.

### 4.4 Kết hợp macro với query bên ngoài

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders_by_status(:status)
WHERE order_date >= :from_date
GROUP BY customer_id;
~~~

Macro không thay thế khả năng viết query đầy đủ. Nó đóng gói phần logic dùng chung, còn query caller có thể áp dụng phép tính bổ sung.

## 5. Cách tạo scalar SQL macro trên 21c trở lên

Scalar macro thích hợp cho biểu thức được lặp lại trong nhiều query.

### 5.1 Tính giá sau chiết khấu

~~~sql
CREATE OR REPLACE FUNCTION net_amount (
    p_gross_amount NUMBER,
    p_discount_rate NUMBER
)
RETURN VARCHAR2
SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[
        p_gross_amount
        * (1 - NVL(p_discount_rate, 0))
    ]';
END;
/
~~~

Dùng:

~~~sql
SELECT order_id,
       gross_amount,
       discount_rate,
       net_amount(gross_amount, discount_rate) AS amount_after_discount
FROM sales.orders;
~~~

Oracle mở rộng lời gọi thành biểu thức tương ứng. Optimizer có thể phân tích biểu thức cùng query và áp dụng các phép biến đổi SQL phù hợp.

### 5.2 Chuẩn hóa mã hiển thị

~~~sql
CREATE OR REPLACE FUNCTION normalized_code (
    p_code VARCHAR2
)
RETURN VARCHAR2
SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[
        UPPER(TRIM(p_code))
    ]';
END;
/
~~~

Dùng:

~~~sql
SELECT normalized_code(product_code) AS search_code
FROM products;
~~~

Đây là biểu thức minh họa. Nếu quy tắc chuẩn hóa có liên quan Unicode, locale hoặc collation, cần định nghĩa semantics rõ ràng và kiểm tra dữ liệu thực tế. UPPER/TRIM không phải giải pháp đầy đủ cho mọi quy tắc Unicode.

### 5.3 Macro biểu thức điều kiện

~~~sql
CREATE OR REPLACE FUNCTION is_active_order (
    p_status VARCHAR2,
    p_cancelled_at DATE
)
RETURN VARCHAR2
SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[
        p_status = 'ACTIVE'
        AND p_cancelled_at IS NULL
    ]';
END;
/
~~~

Dùng:

~~~sql
SELECT order_id
FROM sales.orders
WHERE is_active_order(status, cancelled_at);
~~~

Macro giúp dùng chung quy tắc điều kiện. Nếu business rule thay đổi, sửa macro một lần và kiểm thử các query phụ thuộc.

## 6. Tham số macro được mở rộng như thế nào?

Đây là điểm rất quan trọng đối với tính đúng đắn và an toàn.

Trong function-based macro, tên tham số được đặt trong returned SQL. Oracle thay tham chiếu tham số bằng biểu thức thực tế ở nơi macro được gọi. Nếu truyền tên cột, biểu thức cột sẽ được đưa vào query. Nếu truyền bind variable, bind variable được giữ trong SQL mở rộng.

Ví dụ:

~~~sql
RETURN q'[
    SELECT *
    FROM sales.orders
    WHERE customer_id = orders_for_customer.p_customer_id
]';
~~~

Khi gọi:

~~~sql
SELECT *
FROM orders_for_customer(:customer_id);
~~~

Tham chiếu orders_for_customer.p_customer_id được mở rộng theo argument của lời gọi. Nó không phải là một giá trị PL/SQL được nối vào chuỗi trong function body.

### 6.1 Không nối tham số vào returned SQL text

Không nên viết:

~~~sql
RETURN
    'SELECT * FROM sales.orders WHERE status = '''
    || p_status
    || '''';
~~~

Cách này có nhiều vấn đề:

- Có nguy cơ SQL injection nếu giá trị đến từ input không đáng tin.
- SQL text thay đổi theo giá trị, làm giảm khả năng reuse cursor.
- Với bind variable, macro function có thể chỉ nhìn thấy giá trị tại hard parse.
- Một câu query đã parse có thể giữ text được tạo từ giá trị ở lần hard parse, dẫn tới kết quả bất ngờ khi bind thay đổi.
- Quoting dấu nháy và datatype conversion dễ sai.

Dùng tham chiếu parameter trong returned SQL:

~~~sql
RETURN q'[
    SELECT *
    FROM sales.orders
    WHERE status = orders_by_status.p_status
]';
~~~

### 6.2 Giá trị tham số chuỗi trong macro body

Trong function-based SQL macro, giá trị của tham số kiểu chuỗi có thể là NULL trong macro body để tránh việc macro body đọc rồi nối nội dung chuỗi vào SQL text. Thay vào đó, hãy tham chiếu tên tham số trong SQL được trả về.

Với tham số kiểu dữ liệu khác, giá trị có thể được quan sát trong macro body tại hard parse. Nối giá trị đó vào SQL text vẫn có thể đóng băng giá trị của lần hard parse và làm bind behavior sai. Quy tắc an toàn là không xây SQL bằng cách ghép giá trị tham số; hãy để Oracle mở rộng tham số như expression.

### 6.3 Tham số có cùng tên với cột

Giả sử bảng có cột P_STATUS và macro cũng có parameter P_STATUS. Dùng tên qualified:

~~~sql
WHERE orders_by_status.p_status = orders_by_status.p_status
~~~

Ví dụ trên cố ý cho thấy cách qualification nhưng về logic là một phép so sánh một biểu thức với chính nó, không phải query nghiệp vụ hợp lý. Trong code thực tế hãy dùng alias cho bảng và tên tham số rõ ràng:

~~~sql
WHERE o.status = orders_by_status.p_status
~~~

Với native CREATE MACRO 26ai, quy tắc phân giải tên parameter/column được tài liệu hóa riêng: nếu tên không qualification khớp cả parameter và column, Oracle ưu tiên macro parameter; có thể qualify parameter bằng macro name và column bằng table alias để tránh mơ hồ.

## 7. Macro nhận table argument

Một số table macro nhận một table expression làm tham số, từ đó tái sử dụng logic trên nhiều bảng có cấu trúc tương thích.

Ví dụ với function-based macro:

~~~sql
CREATE OR REPLACE FUNCTION take_rows (
    p_count NUMBER,
    p_source DBMS_TF.TABLE_T
)
RETURN VARCHAR2
SQL_MACRO
IS
BEGIN
    RETURN q'[
        SELECT *
        FROM p_source
        FETCH FIRST take_rows.p_count ROWS ONLY
    ]';
END;
/
~~~

Gọi:

~~~sql
SELECT *
FROM take_rows(5, sales.orders);
~~~

DBMS_TF.TABLE_T là kiểu table argument được Oracle cung cấp cho polymorphic table function và SQL macro table parameter trong các release hỗ trợ.

### 7.1 Vì sao table argument hữu ích?

Một macro có thể tái sử dụng logic cho nhiều nguồn:

~~~sql
SELECT *
FROM take_rows(10, sales.orders);

SELECT *
FROM take_rows(10, sales.customers);
~~~

Các table argument phải tương thích với query macro tham chiếu. Nếu macro chọn các cột cụ thể, các bảng truyền vào phải có cột phù hợp.

### 7.2 Cột và cấu trúc bảng

Table macro không tự biến một bảng bất kỳ thành bảng có schema mong muốn. Cần xác định:

- Tên cột mà query mở rộng tham chiếu.
- Kiểu dữ liệu tương thích.
- Alias và scope của table expression.
- Cách xử lý nếu cột không tồn tại.
- Quy tắc nếu truyền view, CTE hoặc inline view.

Với macro dùng table argument, kiểm thử cả table, view và CTE nếu release hỗ trợ. Đừng chỉ test với một bảng cụ thể rồi kết luận macro tổng quát.

### 7.3 COLUMNS pseudo-operator và danh sách cột

Function-based macro có thể dùng DBMS_TF.COLUMNS_T và COLUMNS pseudo-operator trong các tình huống cần nhận danh sách cột tại thời điểm gọi, chẳng hạn tạo grouping list hoặc sorting list động. Đây là trường hợp nâng cao, không giống scalar bind parameter thông thường.

Một số khả năng nhận column list của function-based macro không có tương đương trực tiếp trong native CREATE MACRO. Oracle SQL blog năm 2026 lưu ý native macro chưa nhận column-list parameter theo cách function-based macro làm được. Nếu bài toán cần danh sách cột động, hãy kiểm tra chính xác API DBMS_TF và cú pháp COLUMNS của release đang chạy trước khi chọn cơ chế.

Không nối raw column name từ request vào SQL. Chỉ chấp nhận danh sách cột được xác thực theo metadata/whitelist và bảo đảm caller được phép truy cập các cột đó.

## 8. SQL macro và WITH clause

Common table expression (CTE) giúp chia query phức tạp thành các phần có tên:

~~~sql
WITH recent_orders AS (
    SELECT *
    FROM sales.orders
    WHERE order_date >= :from_date
)
SELECT customer_id, COUNT(*)
FROM recent_orders
GROUP BY customer_id;
~~~

Một số release có restriction khi macro được tham chiếu trong WITH clause. Oracle công bố từ 23.26.4 restriction này được gỡ. Trước RU đó, không nên giả định mọi cách đặt macro call trong CTE đều hợp lệ.

Ví dụ ở release đã hỗ trợ:

~~~sql
WITH selected_orders AS (
    SELECT *
    FROM orders_for_customer(:customer_id)
),
summary AS (
    SELECT customer_id,
           COUNT(*) AS order_count
    FROM selected_orders
    GROUP BY customer_id
)
SELECT *
FROM summary;
~~~

Khi triển khai trên 19c hoặc RU 23ai cũ hơn, hãy thử đúng câu query trên patch level mục tiêu. Nếu không hỗ trợ, có thể đặt macro trực tiếp trong FROM của query chính hoặc viết inline view/CTE không dùng macro tùy theo khả năng release.

### 8.1 Không nhầm WITH clause với macro trong view

Một view có thể tham chiếu macro trong definition theo privilege semantics của view. CTE chỉ là cấu trúc query trong một statement. Quyền và khả năng tương thích của macro trong view không đồng nghĩa với restriction về macro call trong WITH.

## 9. Quyền và security context của SQL macro

SQL macro có hai giai đoạn quyền cần hiểu:

1. Phần thân function-based macro chạy với definer's rights để tạo SQL text.
2. SQL expression/query sau khi mở rộng được đánh giá theo invoker's rights trong ngữ cảnh SQL gọi, với ngoại lệ/chi tiết khi macro được tham chiếu trong view.

Thuộc tính AUTHID không được chỉ định cho function có SQL_MACRO. Không thêm AUTHID DEFINER hoặc AUTHID CURRENT_USER vào khai báo SQL macro.

### 9.1 Quyền trên object trong SQL mở rộng

Ví dụ macro trả:

~~~sql
RETURN q'[
    SELECT *
    FROM sales.orders
]';
~~~

User gọi macro cần có quyền truy cập các object trong expanded SQL theo security context áp dụng. Chỉ có EXECUTE trên function macro không tự cấp SELECT trên SALES.ORDERS.

Nếu macro được tham chiếu trong view, Oracle xử lý macro với quyền của view owner theo quy tắc được tài liệu hóa. Khi thiết kế view/package, cần kiểm tra cả quyền owner và quyền caller.

### 9.2 INHERIT PRIVILEGES

Oracle có kiểm tra INHERIT PRIVILEGES liên quan đến việc function macro tạo SQL text và quyền của invoker. Khi macro owner và invoker khác nhau, hãy xem yêu cầu của đúng release và xác nhận grant phù hợp. Không tự thêm grant rộng cho PUBLIC để làm lỗi biến mất.

Cần phân biệt quyền cần để tạo/execute function macro, quyền trên object được tham chiếu trong SQL mở rộng và quyền inherit liên quan đến definer/invoker context.

### 9.3 Cấp quyền dùng macro cho schema khác

Nếu macro thuộc schema khác, user gọi cần EXECUTE object privilege trên function macro theo quy tắc function-based macro. Đồng thời user cần privilege trên các object được tham chiếu trong expanded SQL.

Ví dụ owner cấp:

~~~sql
GRANT EXECUTE ON reporting.orders_for_customer TO app_runtime;
GRANT SELECT ON sales.orders TO app_runtime;
~~~

Nếu thiết kế view hoặc API nhằm giới hạn quyền truy cập, không tự động cấp SELECT trên bảng nền cho runtime user; hãy dùng view/package và kiểm tra privilege semantics của đối tượng trung gian.

### 9.4 Native CREATE MACRO trên 26ai

Theo tài liệu CREATE MACRO của 26ai:

- Tạo macro trong schema của mình cần CREATE PROCEDURE.
- Tạo macro trong schema khác cần CREATE ANY PROCEDURE hoặc quyền schema tương ứng.
- Gọi macro thuộc user khác cần EXECUTE trên macro hoặc EXECUTE ANY PROCEDURE.
- Invoker vẫn cần quyền truy cập object được tham chiếu trong expanded SQL.
- Owner macro cần quyền thích hợp trên object thuộc schema khác được tham chiếu trong definition.
- Với RAC, tất cả instance phải hỗ trợ macro trước khi tạo.

Không cấp EXECUTE ANY PROCEDURE cho ứng dụng chỉ để gọi một macro. Ưu tiên EXECUTE trên macro cụ thể.

## 10. Restriction của function-based SQL_MACRO

Các restriction sau cần được kiểm tra theo đúng release:

- Function macro phải trả VARCHAR2, CHAR hoặc CLOB.
- SQL_MACRO không kết hợp với RESULT_CACHE.
- SQL_MACRO không kết hợp với PARALLEL_ENABLE.
- SQL_MACRO không kết hợp với PIPELINED.
- Không khai báo DETERMINISTIC; SQL macro được xem là implicitly deterministic theo semantics của feature.
- Không khai báo AUTHID.
- Type method không được đánh dấu SQL_MACRO.
- Macro không dùng trong virtual column expression.
- Macro không dùng trong function-based index.
- Macro không dùng trong editioning view.
- Macro không dùng trong materialized view.
- Table macro chỉ dùng trong FROM clause của query table expression.
- Scalar macro không dùng trong FROM; nó dùng ở vị trí scalar expression.
- Scalar macro không nhận table argument.

### 10.1 Không dùng RESULT_CACHE

Không khai báo:

~~~sql
CREATE FUNCTION my_macro (...)
RETURN VARCHAR2
RESULT_CACHE
SQL_MACRO
IS
...
~~~

SQL macro và PL/SQL function result cache là hai cơ chế khác nhau. Macro tạo SQL expression; nó không cache kết quả query.

### 10.2 Không dùng PIPELINED

Table macro không phải pipelined table function. Không thêm PIPELINED hoặc PARALLEL_ENABLE vào khai báo SQL macro. Nếu cần PL/SQL phát từng dòng, đánh giá pipelined table function; nếu cần query expansion và optimizer nhìn thấy SQL, dùng macro khi release hỗ trợ.

### 10.3 Không dùng trong virtual column hoặc index

Nếu cần một biểu thức trong virtual column/function-based index, hãy dùng biểu thức SQL được hỗ trợ trực tiếp hoặc function thường có đặc tính phù hợp với index. SQL macro không phải lựa chọn thay thế tự động cho function-based index.

### 10.4 Không dùng trong materialized view

Nếu cần materialized view, viết query definition tương thích với materialized view và các restriction của query rewrite/refresh. Không giả định một query chứa macro có thể được tạo thành materialized view.

## 11. Function-based macro và native CREATE MACRO khác nhau thế nào?

| Tiêu chí | CREATE FUNCTION ... SQL_MACRO | CREATE MACRO (26ai) |
|---|---|---|
| Định nghĩa | PL/SQL function trả SQL text | Định nghĩa SQL expression/query trực tiếp |
| Có PL/SQL body | Có | Không cần |
| Kiểm tra SQL definition | Function có thể compile dù returned SQL text chưa hợp lệ; lỗi có thể xuất hiện lúc gọi | Oracle parse/semantic-check SQL khi tạo macro |
| Return type | VARCHAR2, CHAR hoặc CLOB | Không viết return type kiểu function |
| Table arguments | DBMS_TF.TABLE_T trong release hỗ trợ | TABLE parameter native với column constraint |
| Column list động | Có thể dùng COLUMNS pseudo-operator/DBMS_TF.COLUMNS_T | Không có cùng cơ chế column-list parameter như function macro |
| Dictionary | Function metadata; SQL_MACRO column không có trong một số view 19c | USER_MACROS/ALL_MACROS/DBA_MACROS và parameter views |
| Release | Table từ 19c RU hỗ trợ; scalar từ 21c | 26ai |
| Phù hợp | Tương thích hệ thống cũ hơn, logic sinh SQL động có kiểm soát | Macro SQL thông thường cần kiểm tra compile-time |

Native CREATE MACRO giúp định nghĩa dễ đọc và xác thực SQL sớm. Function-based macro vẫn có ích khi cần xây dựng SQL text có cấu trúc động được kiểm soát, chẳng hạn column list theo DBMS_TF.COLUMNS_T.

Không nên chuyển đổi toàn bộ function macro sang native macro chỉ vì cú pháp mới. Hãy xác định macro có dùng table argument, column list, dynamic SQL fragment hay behavior đặc thù không.

## 12. Macro và SQL injection

SQL macro có thể nhận tham số từ ứng dụng. Cần phân biệt hai nhóm:

- Giá trị dữ liệu: customer_id, status, ngày, số tiền. Dùng bind variable/parameter reference.
- Identifier hoặc cấu trúc SQL: tên bảng, tên cột, hướng sort, danh sách group-by. Bind variable không thể thay thế identifier; phải dùng whitelist/validation.

### 12.1 Ví dụ không an toàn

~~~sql
RETURN
    'SELECT * FROM sales.orders WHERE status = '''
    || p_status
    || '''';
~~~

Nếu p_status có ký tự nháy hoặc dữ liệu do người dùng kiểm soát, SQL text có thể bị thay đổi. Nó còn làm mỗi giá trị tạo SQL text khác nhau.

### 12.2 Ví dụ an toàn hơn

~~~sql
RETURN q'[
    SELECT *
    FROM sales.orders
    WHERE status = orders_by_status.p_status
]';
~~~

Parameter được đưa vào expanded SQL theo cơ chế macro. Khi gọi qua JDBC, bind status bằng PreparedStatement.

### 12.3 Identifier động

Nếu cần chọn sort column:

~~~sql
CASE p_sort_key
    WHEN 'ORDER_DATE' THEN
        l_order_expression := 'order_date';
    WHEN 'TOTAL_AMOUNT' THEN
        l_order_expression := 'total_amount';
    ELSE
        RAISE_APPLICATION_ERROR(-20001, 'Unsupported sort key');
END CASE;
~~~

Chỉ sử dụng identifier từ whitelist cố định. Không nối raw input từ HTTP request vào returned SQL. Nếu có thể, viết các nhánh ORDER BY rõ ràng trong SQL thay vì tạo dynamic identifier.

### 12.4 SQL injection và quyền macro owner

Macro không phải sandbox. Expanded SQL vẫn chạy với quyền của invoker hoặc security context của view theo quy tắc Oracle. Nếu macro cho phép caller chọn object/column tùy ý, có thể mở ra bề mặt truy cập dữ liệu ngoài ý định.

Hãy kiểm tra cả tính an toàn của SQL text và quyền trên object mà SQL sau mở rộng có thể tham chiếu.

## 13. Tối ưu hiệu năng và execution plan

SQL macro không tự làm query nhanh hơn. Lợi ích chính là đóng gói SQL mà vẫn để optimizer nhìn thấy expression/query sau khi mở rộng.

### 13.1 Tránh context switch theo từng dòng

Một PL/SQL function thông thường được gọi từ SQL có thể gây chuyển đổi giữa SQL engine và PL/SQL engine cho mỗi lần gọi, tùy cách optimizer xử lý. Scalar macro mở rộng thành SQL expression, giúp tránh lời gọi PL/SQL per-row cho logic có thể biểu diễn bằng SQL.

### 13.2 Predicate pushdown

Với table macro:

~~~sql
SELECT *
FROM orders_for_customer(:customer_id)
WHERE order_date >= :from_date;
~~~

Sau khi macro mở rộng, optimizer nhìn thấy query expression và có thể áp dụng các phép biến đổi như predicate pushdown nếu semantics cho phép. Hãy xem execution plan để xác nhận filter được áp dụng ở đâu.

### 13.3 SQL text shape và hard parse

Nếu function macro tạo nhiều dạng SQL text khác nhau tùy input, shared pool có thể có nhiều cursor/child cursor hơn. Hạn chế việc ghép literal hoặc thay đổi cấu trúc không cần thiết.

Dùng bind variable cho dữ liệu. Chỉ tạo nhiều SQL shape khi cấu trúc query thực sự khác nhau và có lý do hiệu năng.

### 13.4 Cardinality và statistics

Macro không tự cung cấp statistics cho query. Optimizer vẫn dựa trên table/index statistics, histograms, constraints, cardinality estimates và các yếu tố khác.

Nếu query sau expansion có plan kém:

1. Lấy SQL_ID và execution plan.
2. Xác định SQL text đã mở rộng nếu công cụ hỗ trợ.
3. Kiểm tra predicate, join order và access path.
4. Kiểm tra bind peeking/adaptive cursor sharing.
5. So sánh với query viết trực tiếp.
6. Chỉ thêm hint sau khi hiểu nguyên nhân.

### 13.5 Đo lường thay vì suy đoán

Đo cùng workload ở hai dạng:

- Query viết trực tiếp.
- Query gọi macro.

So sánh elapsed time, CPU, logical reads, physical reads, parse calls, executions và plan hash value. Dùng dữ liệu, bind distribution và concurrency tương đương.

Nếu macro chỉ giúp giảm duplicate code nhưng không thay đổi performance, đó vẫn có thể là lợi ích thiết kế hợp lý. Không tuyên bố macro nhanh hơn nếu chưa đo.

## 14. SQL macro với JDBC và Java

JDBC không có API riêng để gọi SQL macro. Ứng dụng gửi câu SQL thông thường có macro call ở vị trí được Oracle hỗ trợ.

### 14.1 Gọi table macro qua PreparedStatement

~~~java
String sql = """
    SELECT order_id, order_date, status
    FROM orders_for_customer(?)
    ORDER BY order_date DESC
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            Date orderDate = resultSet.getDate("order_date");
            String status = resultSet.getString("status");
            // Map row to application model.
        }
    }
}
~~~

Ví dụ dùng Java text block, yêu cầu Java 15 trở lên. Với Java thấp hơn, nối các dòng SQL thành String thông thường.

### 14.2 Gọi scalar macro

~~~java
String sql = """
    SELECT order_id,
           net_amount(gross_amount, discount_rate) AS net_amount
    FROM sales.orders
    WHERE customer_id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            BigDecimal netAmount =
                resultSet.getBigDecimal("net_amount");
        }
    }
}
~~~

Scalar macro chỉ dùng được nếu database release hỗ trợ scalar SQL macro. Query này không thể chạy trên 19c chỉ có table macro.

### 14.3 Bind parameter như SQL thông thường

Dùng setLong, setString, setDate, setBigDecimal hoặc setter tương ứng với datatype. Không nối giá trị vào SQL text trong Java.

Macro không loại bỏ yêu cầu bind variable. Query được mở rộng vẫn là SQL và chịu các quy tắc bind, datatype conversion, cursor sharing và SQL injection như các câu SQL khác.

### 14.4 Driver và database compatibility

Oracle JDBC driver phải tương thích với database version và datatype đang sử dụng. Macro được mở rộng ở database; driver không thực hiện expansion thay Oracle.

Nếu database báo lỗi parse hoặc macro feature không được hỗ trợ, nâng driver một mình không bổ sung feature còn thiếu ở database RU. Kiểm tra database trước, sau đó kiểm tra driver, SQL syntax và quyền.

## 15. Kiểm tra release, RU và macro metadata

### 15.1 Xem database version

~~~sql
SELECT * FROM v$version;
~~~

Nếu có quyền phù hợp, kiểm tra thêm:

~~~sql
SELECT product, version, status
FROM product_component_version
ORDER BY product;
~~~

Ghi lại toàn bộ banner/version thay vì chỉ ghi "Oracle 19c" hoặc "Oracle 23ai".

### 15.2 Xem SQL patch history

DBA có thể truy vấn:

~~~sql
SELECT
    patch_id,
    action,
    status,
    description,
    action_time
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
~~~

View này cho biết SQL patch history trong database. Đối chiếu với inventory/patch của Oracle Home khi cần. Không suy ra RU chỉ từ version major.

### 15.3 RAC và nhiều instance

~~~sql
SELECT inst_id, instance_name, version, status
FROM gv$instance
ORDER BY inst_id;
~~~

Trong RAC, cần kiểm tra mọi instance có patch/feature support phù hợp trước khi tạo macro hoặc đưa macro vào production SQL. Một rolling patch có thể tạo thời điểm các node khác nhau về capability.

### 15.4 SQL_MACRO column trong data dictionary

Trong các release mới, USER_PROCEDURES/ALL_PROCEDURES/DBA_PROCEDURES có thể có cột SQL_MACRO để nhận diện function macro. Oracle ghi chú cột này không có trong Oracle Database 19c; không viết script kiểm tra 19c giả định cột đó luôn tồn tại.

Trên 26ai native macro, có các dictionary view:

- USER_MACROS
- ALL_MACROS
- DBA_MACROS
- USER_MACRO_PARAMETERS
- ALL_MACRO_PARAMETERS
- DBA_MACRO_PARAMETERS

Native macro xuất hiện trong *_OBJECTS với OBJECT_TYPE là MACRO. Dùng đúng view theo quyền và release.

Ví dụ:

~~~sql
SELECT owner, object_name, object_type, status
FROM all_objects
WHERE object_type = 'MACRO'
ORDER BY owner, object_name;
~~~

Truy vấn macro metadata:

~~~sql
SELECT *
FROM user_macros
ORDER BY macro_name;
~~~

Tên cột cụ thể của macro dictionary cần đối chiếu SQL Reference đúng release.

### 15.5 Test feature trong schema riêng

Nếu metadata không đủ rõ, tạo một macro nhỏ trong schema test, compile và gọi thử. Không thử tạo macro mới trong schema nghiệp vụ production chỉ để dò feature.

Bài test tối thiểu nên xác nhận:

1. CREATE FUNCTION với SQL_MACRO có compile không.
2. Table macro gọi được trong FROM không.
3. Scalar macro compile/call được nếu cần.
4. Macro call trong WITH hoạt động trên RU hiện tại không.
5. Quyền trên object được tham chiếu có đúng không.
6. JDBC PreparedStatement gọi query được không.
7. RAC/PDB/service thực tế có cùng behavior không.

## 16. Ví dụ hoàn chỉnh: table macro cho báo cáo đơn hàng

Giả sử SALES.ORDERS có các cột order_id, customer_id, order_date, status và total_amount.

### 16.1 Function macro

~~~sql
CREATE OR REPLACE FUNCTION orders_in_period (
    p_from_date DATE,
    p_to_date DATE,
    p_status VARCHAR2
)
RETURN VARCHAR2
SQL_MACRO
IS
BEGIN
    RETURN q'[
        SELECT order_id,
               customer_id,
               order_date,
               status,
               total_amount
        FROM sales.orders
        WHERE order_date >= orders_in_period.p_from_date
          AND order_date < orders_in_period.p_to_date
          AND (
                orders_in_period.p_status IS NULL
                OR status = orders_in_period.p_status
              )
    ]';
END;
/
~~~

Đây là table macro theo cú pháp 19c. Với 21c trở lên có thể khai báo rõ SQL_MACRO(TABLE).

### 16.2 Gọi macro và aggregate

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders_in_period(
    DATE '2026-01-01',
    DATE '2026-02-01',
    :status
)
GROUP BY customer_id
ORDER BY total_amount DESC;
~~~

Dùng khoảng thời gian nửa mở [from_date, to_date) giúp tránh vấn đề thời gian ở cuối ngày khi order_date có phần time.

### 16.3 Test với các trường hợp

- p_status có giá trị cụ thể.
- p_status là bind NULL.
- Không có dòng trong kỳ.
- from_date bằng to_date.
- Dữ liệu có timestamp/date ở biên.
- Nhiều customer có tổng tiền bằng nhau.
- Caller có quyền SELECT trên SALES.ORDERS.
- Macro được gọi từ schema khác qua EXECUTE grant.

### 16.4 Kiểm tra SQL trực tiếp tương đương

Viết cùng query không dùng macro:

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       status,
       total_amount
FROM sales.orders
WHERE order_date >= :from_date
  AND order_date < :to_date
  AND (
        :status IS NULL
        OR status = :status
      );
~~~

So sánh row set và execution plan. Macro đúng phải tạo semantics tương đương với query trực tiếp theo cùng bind values.

## 17. Ví dụ hoàn chỉnh: scalar macro cho biểu thức tính tiền

### 17.1 Định nghĩa

~~~sql
CREATE OR REPLACE FUNCTION line_net_amount (
    p_quantity NUMBER,
    p_unit_price NUMBER,
    p_discount_rate NUMBER
)
RETURN VARCHAR2
SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[
        p_quantity
        * p_unit_price
        * (1 - NVL(p_discount_rate, 0))
    ]';
END;
/
~~~

Ví dụ này cần Oracle release hỗ trợ scalar macro, chẳng hạn 21c trở lên.

### 17.2 Sử dụng

~~~sql
SELECT line_id,
       quantity,
       unit_price,
       discount_rate,
       line_net_amount(
           quantity,
           unit_price,
           discount_rate
       ) AS net_amount
FROM order_lines;
~~~

### 17.3 Test semantics NULL và rounding

Nếu quantity, unit_price hoặc discount_rate có thể NULL, hãy xác định rõ nghiệp vụ. Macro hiện tại có thể trả NULL nếu quantity hoặc unit_price NULL; discount_rate NULL được xem như 0.

Nếu tiền cần rounding:

~~~sql
RETURN q'[
    ROUND(
        p_quantity
        * p_unit_price
        * (1 - NVL(p_discount_rate, 0)),
        2
    )
]';
~~~

Quy tắc scale/rounding nên được thống nhất với ứng dụng và datatype NUMBER. Không tự làm tròn trong Java khác quy tắc Oracle mà không có test.

## 18. Native CREATE MACRO trên 26ai

Native macro là cú pháp riêng trong 26ai. Nó không yêu cầu viết PL/SQL function để trả SQL string.

### 18.1 Table macro

~~~sql
CREATE OR REPLACE MACRO active_orders (
    p_customer_id NUMBER
) AS
    SELECT order_id,
           customer_id,
           order_date,
           status
    FROM sales.orders
    WHERE customer_id = p_customer_id
      AND status = 'ACTIVE';
~~~

Gọi:

~~~sql
SELECT *
FROM active_orders(1001);
~~~

Table macro được dùng trong FROM clause.

### 18.2 Scalar macro

~~~sql
CREATE OR REPLACE MACRO order_priority (
    p_total_amount NUMBER
) AS
    CASE
        WHEN p_total_amount >= 10000 THEN 'HIGH'
        WHEN p_total_amount >= 1000 THEN 'NORMAL'
        ELSE 'LOW'
    END;
~~~

Gọi:

~~~sql
SELECT order_id,
       order_priority(total_amount) AS priority
FROM sales.orders;
~~~

Scalar macro được dùng ở vị trí scalar expression.

### 18.3 Default parameter

~~~sql
CREATE OR REPLACE MACRO greeting (
    p_name VARCHAR2 DEFAULT 'World'
) AS
    'Hello, ' || p_name || '!';
~~~

Gọi:

~~~sql
SELECT greeting() FROM dual;
SELECT greeting('Oracle') FROM dual;
~~~

Một macro không có parameter vẫn cần gọi với cặp ngoặc theo hướng dẫn Oracle.

### 18.4 Table parameter có ràng buộc cột

Native CREATE MACRO hỗ trợ table parameter. Có thể khai báo generic table parameter hoặc ràng buộc tập cột cần có.

Mô hình minh họa:

~~~sql
CREATE OR REPLACE MACRO summarize_orders (
    p_source TABLE (
        customer_id NUMBER,
        total_amount NUMBER
    )
) AS
    SELECT customer_id,
           SUM(total_amount) AS total_amount
    FROM p_source
    GROUP BY customer_id;
~~~

Cú pháp chính xác của table parameter và column list cần đối chiếu grammar CREATE MACRO đúng 26ai release. Table argument truyền vào phải có các cột bắt buộc với kiểu dữ liệu tương thích; cột bổ sung hoặc thứ tự cột khác có thể được cho phép theo quy tắc native macro.

### 18.5 Parameter name resolution

Nếu parameter và column có cùng tên, tên không qualification có thể được phân giải thành macro parameter trước. Để tránh ambiguity:

- Qualify parameter bằng tên macro.
- Qualify column bằng table alias.
- Dùng tên parameter dễ nhận biết, chẳng hạn p_customer_id.
- Đặt alias cho bảng có tên trùng macro.

Đây là quy tắc cần lưu ý khi native macro được dùng trong query scope lớn có nhiều bảng và column name trùng nhau.

### 18.6 Compile-time validation

Native CREATE MACRO định nghĩa SQL trực tiếp nên Oracle parse và kiểm tra SQL definition khi tạo macro. So với function-based macro trả SQL text, lỗi cú pháp/semantic trong query definition có thể được phát hiện sớm hơn.

Dù vậy, compile thành công không thay thế runtime test với bind values, privilege, object data, optimizer plan và concurrency. Một query hợp lệ về cú pháp vẫn có thể sai logic hoặc chậm.

## 19. So sánh SQL macro với các lựa chọn khác

### 19.1 View

Dùng view khi:

- Query không cần tham số.
- Muốn cung cấp interface ổn định cho nhiều consumer.
- Muốn quản lý quyền qua view.
- Muốn giấu cấu trúc bảng nền.

Dùng macro khi query cần tham số hoặc biểu thức tái sử dụng cần được mở rộng vào câu SQL caller.

### 19.2 Inline view và CTE

Dùng inline view/CTE khi logic chỉ dùng một lần hoặc chỉ có một consumer. Macro phù hợp khi cùng logic được lặp lại ở nhiều câu SQL và cần quản lý tập trung.

Đừng tạo macro cho một expression rất nhỏ chỉ để tăng số object trong schema. Cần cân nhắc khả năng đọc query, dependency và cách deploy.

### 19.3 PL/SQL function thông thường

Dùng function thông thường khi cần:

- Logic thủ tục không dễ biểu diễn bằng SQL.
- Gọi package/API hoặc thao tác PL/SQL.
- Tính toán một giá trị theo thuật toán riêng.
- Tái sử dụng logic trong PL/SQL và SQL.

Dùng scalar macro khi logic có thể biểu diễn thành SQL expression và muốn optimizer nhìn thấy expression đó. Ở release mới, SQL Transpiler cũng có thể chuyển một số PL/SQL function thành SQL expression; hãy đánh giá tính năng đó riêng, không coi nó là đồng nghĩa SQL macro.

### 19.4 Pipelined table function

Pipelined table function phù hợp khi PL/SQL thực sự cần tạo từng dòng, gọi API hoặc thực hiện logic procedural. Nó có execution model và overhead khác table macro.

Nếu dữ liệu đã nằm trong bảng và có thể diễn tả bằng SELECT, table macro thường tự nhiên hơn vì trả SQL query cho optimizer.

### 19.5 Polymorphic table function

PTF phù hợp khi cần thay đổi output row shape hoặc xử lý metadata/cột qua interface PL/SQL. Table macro phù hợp khi muốn tạo query expression parameterized. Không dùng macro thay PTF nếu yêu cầu cần xử lý row metadata động mà macro không thể diễn đạt.

## 20. Quy trình triển khai SQL macro theo môi trường

### Bước 1: Xác định use case

Viết rõ macro cần đóng gói:

- Table query có tham số.
- Scalar expression.
- Table argument.
- Column list động.
- Macro dùng trong WITH.
- Native CREATE MACRO.

### Bước 2: Xác định database capability

Ghi lại full version, RU, service/PDB, RAC instance và driver. Đối chiếu release matrix và Oracle documentation.

### Bước 3: Chọn đúng cơ chế

- 19c: table function macro, không dùng scalar macro.
- 21c: table/scalar function macro.
- 23ai: kiểm tra RU cho WITH clause.
- 26ai: cân nhắc native CREATE MACRO cho SQL definition thông thường.
- Cần column-list động: đánh giá function-based macro với DBMS_TF.COLUMNS_T.

### Bước 4: Thiết kế tham số

Phân loại mỗi parameter:

- Giá trị scalar.
- Bind variable.
- Column expression.
- Table expression.
- Identifier/column list.

Không nối input thành SQL string. Với identifier, dùng whitelist và API phù hợp.

### Bước 5: Kiểm tra quyền

Xác định macro owner, invoker, view owner nếu macro nằm trong view, EXECUTE grant và quyền trên expanded SQL. Kiểm tra INHERIT PRIVILEGES theo release và schema boundary.

### Bước 6: Tạo macro trong schema test

Compile function/native macro, gọi bằng query đơn giản, sau đó test query phức tạp và nhiều caller. Không bắt đầu bằng deployment production.

### Bước 7: So sánh query trực tiếp

Viết query tương đương không macro. So sánh kết quả, NULL behavior, datatype, execution plan và bind behavior.

### Bước 8: Test JDBC

Dùng PreparedStatement và bind variable. Test đúng driver và datasource của ứng dụng. Không chỉ kiểm tra trên SQL Developer.

### Bước 9: Deploy và theo dõi

Deploy macro cùng migration, grants và dependent views/packages. Theo dõi SQL_ID, plan, parse rate, latency và lỗi invalidation sau release.

## 21. Kiểm thử và xử lý lỗi

### 21.1 Function compile được nhưng query lỗi

Với function-based macro, function body có thể compile dù returned SQL text chứa lỗi. Khi macro được gọi, Oracle mới parse SQL mở rộng và báo lỗi.

Cách xử lý:

1. Gọi macro bằng query tối giản.
2. Kiểm tra object name và alias trong returned SQL.
3. Kiểm tra parameter qualification.
4. Chạy query tương đương trực tiếp.
5. Kiểm tra privilege trên expanded SQL.
6. Kiểm tra release restriction.

### 21.2 ORA-00904 invalid identifier

Nguyên nhân thường gặp:

- Tham chiếu parameter sai tên.
- Cột không tồn tại trong table argument.
- Alias không được khai báo trong scope.
- Parameter trùng tên cột và không được qualify.
- Macro query được mở rộng ở scope khác với giả định.

Dùng alias và qualify parameter rõ ràng.

### 21.3 ORA-00942 hoặc ORA-01031

Macro không cấp quyền cho caller. Kiểm tra:

- Macro owner có quyền trên object cần thiết theo định nghĩa.
- Invoker có quyền trên expanded SQL.
- View owner nếu macro được tham chiếu trong view.
- EXECUTE privilege trên macro function/object.
- INHERIT PRIVILEGES trong cross-schema use.
- Đúng PDB/service và synonym target.

### 21.4 Macro không được nhận diện hoặc sai cú pháp

Có thể database RU không hỗ trợ feature hoặc đang dùng cú pháp của release khác.

Ví dụ thường gặp:

- Dùng SQL_MACRO(SCALAR) trên 19c.
- Dùng CREATE MACRO trên 23ai.
- Dùng macro trong WITH trên RU chưa hỗ trợ.
- Dùng SQL_MACRO(TABLE) tường minh trên 19c thay vì cú pháp mặc định table macro.
- Dùng macro trong virtual column/function-based index/materialized view.

Đối chiếu SQL Language Reference đúng release và tạo test trong schema riêng.

### 21.5 JDBC parse error

Nếu SQL client chạy được nhưng JDBC lỗi:

- Xác nhận datasource dùng đúng service/PDB.
- Xác nhận database user và current schema.
- Xác nhận driver version.
- Xác nhận SQL string và bind positions.
- Kiểm tra query macro được gửi nguyên vẹn.
- Kiểm tra JDBC không tự thêm wrapper hoặc rewrite SQL.
- Kiểm tra role/session state của connection pool.

## 22. Checklist chọn SQL macro

### Release và syntax

- [ ] Đã xác định full database version.
- [ ] Đã xác định RU/patch level.
- [ ] Đã kiểm tra đúng PDB/service.
- [ ] Đã kiểm tra mọi RAC instance.
- [ ] Đã chọn table hay scalar macro.
- [ ] Nếu 19c, dùng table macro và cú pháp tương thích.
- [ ] Nếu dùng WITH, đã xác nhận RU hỗ trợ.
- [ ] Nếu dùng CREATE MACRO, database là 26ai.
- [ ] Đã kiểm tra restriction của đúng release.

### Thiết kế macro

- [ ] Macro có use case tái sử dụng rõ.
- [ ] Query/biểu thức có thể được biểu diễn bằng SQL.
- [ ] Parameter có tên và datatype rõ.
- [ ] Parameter được tham chiếu trong returned SQL, không bị nối giá trị vào text.
- [ ] Identifier động dùng whitelist.
- [ ] Table argument có schema/column contract rõ.
- [ ] Alias và parameter qualification không mơ hồ.
- [ ] NULL, datatype conversion và date boundary đã được xác định.

### Quyền và bảo mật

- [ ] Macro owner có quyền cần thiết.
- [ ] Invoker có EXECUTE trên macro.
- [ ] Invoker có quyền trên expanded SQL.
- [ ] View owner được xem xét nếu macro nằm trong view.
- [ ] INHERIT PRIVILEGES được kiểm tra khi cần.
- [ ] Không dùng quyền ANY rộng để làm macro chạy.
- [ ] Không nối input không tin cậy vào SQL text.

### Hiệu năng và kiểm thử

- [ ] Có query trực tiếp làm baseline.
- [ ] Kết quả macro khớp query baseline.
- [ ] Đã kiểm tra execution plan.
- [ ] Đã đo logical reads, CPU và elapsed time.
- [ ] Đã test bind values khác nhau.
- [ ] Đã test JDBC với driver thực tế.
- [ ] Đã test nhiều schema/caller nếu có.
- [ ] Đã test RU/PDB/RAC tương ứng.
- [ ] Đã có migration và rollback plan.

## 23. Kết luận

SQL macro cho phép tái sử dụng SQL có tham số mà vẫn để Oracle optimizer xử lý query hoặc expression sau khi mở rộng. Table macro phù hợp với query trong FROM; scalar macro đóng gói biểu thức trong SELECT/WHERE và các vị trí scalar được phép. Macro function không phải function trả dữ liệu từng dòng, và nó không tự bảo đảm performance tốt hơn.

Khả năng sử dụng phụ thuộc release/update. Oracle 19c tập trung vào table macro; Oracle 21c hỗ trợ scalar macro; Oracle công bố RU 23.26.4 gỡ restriction về macro trong WITH clause; native CREATE MACRO thuộc 26ai. Tài liệu 19c có khác biệt công khai về mốc RU 19.6/19.7, vì vậy phải xác nhận patch level và tài liệu đúng môi trường trước khi triển khai.

Khi viết macro, hãy tham chiếu parameter trong SQL được mở rộng thay vì nối giá trị vào SQL text, kiểm tra quyền của macro owner/invoker/view owner, tránh identifier động không được whitelist và so sánh execution plan với query viết trực tiếp. Dùng macro khi nó làm logic SQL dùng chung rõ ràng hơn và release mục tiêu hỗ trợ đúng cú pháp cần thiết.

## 24. Tài liệu tham khảo

- Oracle Database 19c SQL Language Reference — Changes in This Release: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Changes-in-This-Release-for-Oracle-Database-SQL-Language-Reference.html
- Oracle Database 19c PL/SQL Language Reference — SQL_MACRO Clause: https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/SQL_MACRO_clause.html
- Oracle Database 21c PL/SQL Language Reference — SQL_MACRO Clause: https://docs.oracle.com/en/database/oracle/oracle-database/21/lnpls/sql_macro-clause.html
- Oracle AI Database 26ai PL/SQL Language Reference — SQL_MACRO Clause: https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/SQL_MACRO-clause.html
- Oracle AI Database 26ai SQL Language Reference — CREATE MACRO: https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/CREATE-MACRO.html
- Chris Saxon, Oracle Developer Advocate, How to create views with parameters in Oracle AI Database, 21 October 2026: https://blogs.oracle.com/sql/how-to-create-views-with-parameters-in-oracle-ai-database

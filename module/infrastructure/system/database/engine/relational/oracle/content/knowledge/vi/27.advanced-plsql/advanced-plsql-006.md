# PRAGMA UDF, function gọi từ SQL và điều kiện hỗ trợ theo phiên bản Oracle

Trong Oracle Database, một hàm PL/SQL có thể được gọi trực tiếp từ câu lệnh SQL. Ví dụ, một truy vấn báo cáo có thể gọi hàm tính số tiền sau thuế cho từng dòng bán hàng. Cách viết này giúp đóng gói logic và tái sử dụng, nhưng mỗi lần SQL engine gọi sang PL/SQL engine đều có chi phí chuyển ngữ cảnh. Nếu hàm được gọi cho hàng trăm nghìn hoặc hàng triệu dòng, chi phí đó có thể trở thành phần đáng kể của thời gian truy vấn.

Oracle cung cấp **PRAGMA UDF** để thông báo với PL/SQL compiler rằng một function chủ yếu được gọi từ SQL. Compiler có thể tạo cách thực thi phù hợp hơn và giảm một phần overhead khi đi qua ranh giới SQL/PLSQL. Đây là một tối ưu hóa về chi phí gọi hàm; nó không thay đổi kết quả nghiệp vụ, không biến function thành SQL expression, không cache kết quả và không loại bỏ các giới hạn của function được gọi từ SQL.

Bài học thuộc nhóm **PL/SQL nâng cao** của Database Engine Relational Oracle. Nội dung giải thích context switching, cách khai báo PRAGMA UDF, gọi function từ SELECT và DML, điều kiện tương thích về datatype/quyền/side effects, khác biệt theo phiên bản, cách đo hiệu năng và các lựa chọn thiết kế thay thế.

Sau bài này, bạn có thể:

- Giải thích vì sao SQL gọi PL/SQL function có thể phát sinh context-switch overhead.
- Nhận biết trường hợp function được gọi một lần và trường hợp được gọi nhiều lần theo từng hàng.
- Khai báo PRAGMA UDF đúng vị trí trong function.
- Dùng UDF với function độc lập hoặc function trong package.
- Phân biệt PRAGMA UDF với DETERMINISTIC, RESULT_CACHE và PRAGMA INLINE.
- Nhận diện datatype và parameter-mode phù hợp cho function được gọi từ SQL.
- Hiểu các giới hạn về DML, transaction control, DDL và side effects.
- Hiểu vì sao không được giả định SQL chỉ gọi function đúng một lần.
- Xác định phiên bản Oracle hỗ trợ PRAGMA UDF.
- Đo và so sánh hiệu năng trước/sau bằng workload tương đương.
- Quyết định khi nào nên viết lại bằng SQL thuần hoặc dùng giải pháp khác.

> **Phạm vi ví dụ:** Các câu lệnh minh họa theo Oracle Database 19c. PRAGMA UDF được giới thiệu từ Oracle Database 12c Release 1 (12.1). Ví dụ dùng NUMBER/VARCHAR2/DATE là các kiểu SQL quen thuộc; khả năng dùng BOOLEAN hoặc các kiểu PL/SQL khác trực tiếp trong SQL phụ thuộc release, đặc biệt trước và từ Oracle Database 23c/23ai.

## 1. SQL engine và PL/SQL engine

Oracle SQL và PL/SQL phối hợp chặt chẽ nhưng không phải cùng một ngôn ngữ thực thi.

- **SQL engine** phân tích và thực thi SELECT, INSERT, UPDATE, DELETE, MERGE cùng các biểu thức SQL.
- **PL/SQL engine** thực thi block, procedure, function, package và các câu lệnh điều khiển như IF, LOOP, EXCEPTION.

Khi SQL gọi một PL/SQL function, quyền điều khiển phải đi từ SQL engine sang PL/SQL engine, thực thi function, rồi quay lại SQL engine. Sự chuyển qua lại này thường được gọi là *context switch*.

### 1.1. Một function được gọi từ SELECT

Ví dụ:

~~~sql
SELECT
    order_id,
    order_total,
    calculate_net_amount(order_total, 0.10) AS net_amount
FROM orders_lab;
~~~

Nếu kết quả có 10 hàng, function có thể được gọi nhiều lần theo các hàng cần tính. Nếu kết quả có 1 triệu hàng, SQL engine có thể phải gọi PL/SQL function rất nhiều lần. Số lần gọi thực tế còn phụ thuộc cách optimizer thực thi câu SQL, biểu thức có được loại bỏ/tính lại hay không và cấu trúc truy vấn.

### 1.2. Minh họa ranh giới gọi

~~~text
                 SQL ENGINE
       SELECT ... calculate_net_amount(...)
                      |
                      | call function
                      v
                 PL/SQL ENGINE
       calculate input -> compute -> return
                      |
                      | return value
                      v
                 SQL ENGINE
       continue row processing / fetch result
~~~

Nếu SQL gọi function nhiều lần, chi phí chuyển ngữ cảnh cũng lặp lại. Với function rất nhỏ, phần overhead có thể lớn hơn chính phép tính.

### 1.3. Function càng nhỏ càng có thể thấy rõ overhead

Giả sử function chỉ thực hiện:

~~~sql
RETURN p_amount * (1 - p_tax_rate);
~~~

Phép nhân/trừ rất rẻ. Nếu mỗi lần gọi function có thêm chi phí giao tiếp giữa hai engine, tổng chi phí có thể đáng kể khi gọi theo từng hàng.

Ngược lại, nếu function thực hiện thuật toán nặng trong thời gian dài, chi phí chuyển ngữ cảnh có thể chỉ là phần nhỏ. PRAGMA UDF không phải giải pháp thay thế cho tối ưu thuật toán, SQL plan, index hoặc I/O.

## 2. PRAGMA UDF là gì?

PRAGMA UDF là compiler directive trong PL/SQL. Nó cho compiler biết function được thiết kế chủ yếu để được gọi từ SQL. Oracle có thể tối ưu cách gọi function và giảm overhead chuyển giữa SQL engine và PL/SQL engine.

### 2.1. Ý nghĩa chính

- Tối ưu đường gọi function từ SQL trong những trường hợp phù hợp.
- Có thể cải thiện truy vấn gọi function nhiều lần theo từng hàng.
- Không thay đổi chữ ký public của function.
- Không thay đổi kết quả trả về nếu function được viết đúng.
- Không bảo đảm mọi workload đều nhanh hơn.

### 2.2. PRAGMA UDF không phải một function mới

Function vẫn là PL/SQL function thông thường. Nó vẫn có parameter, return type, exception handling và dependency như trước. PRAGMA UDF chỉ là chỉ dẫn cho compiler.

### 2.3. Không phải mọi function đều cần UDF

Nên cân nhắc UDF khi:

- Function được gọi từ SQL.
- Function có thể được gọi nhiều lần trên tập kết quả lớn.
- Logic vẫn nên được đóng gói bằng PL/SQL.
- Benchmark cho thấy overhead gọi function có ý nghĩa.

Không cần thêm UDF cho mọi function chỉ vì database hỗ trợ pragma. Function chỉ được gọi một lần từ PL/SQL thường không hưởng lợi đáng kể từ mục tiêu tối ưu này.

## 3. Cú pháp và vị trí khai báo

### 3.1. Cú pháp

~~~sql
PRAGMA UDF;
~~~

Đặt pragma trong phần khai báo của function, trước phần BEGIN thực thi. Ví dụ:

~~~sql
CREATE OR REPLACE FUNCTION net_amount_udf (
    p_amount   IN NUMBER,
    p_tax_rate IN NUMBER
)
RETURN NUMBER
IS
    PRAGMA UDF;
BEGIN
    RETURN p_amount * (1 - p_tax_rate);
END net_amount_udf;
/
~~~

Function có thể được gọi từ SQL:

~~~sql
SELECT
    order_id,
    net_amount_udf(order_total, 0.10) AS net_amount
FROM orders_lab;
~~~

### 3.2. Vị trí pragma

Pragma nằm trong declarative section của function:

~~~text
CREATE FUNCTION ...
RETURN ...
IS
    declarations
    PRAGMA UDF;
BEGIN
    executable statements
END;
~~~

Không đặt PRAGMA UDF bên trong câu lệnh IF, LOOP hoặc sau BEGIN như một câu lệnh thực thi. Đây là compiler directive, không phải lời gọi runtime.

### 3.3. Function không có UDF

~~~sql
CREATE OR REPLACE FUNCTION net_amount_plain (
    p_amount   IN NUMBER,
    p_tax_rate IN NUMBER
)
RETURN NUMBER
IS
BEGIN
    RETURN p_amount * (1 - p_tax_rate);
END net_amount_plain;
/
~~~

Hai function có cùng logic. Khác biệt là net_amount_udf có pragma. Đây là cặp phù hợp để benchmark nếu được gọi từ SQL trong workload giống nhau.

### 3.4. Function trong package

PRAGMA UDF cũng có thể dùng với function được triển khai trong package body:

~~~sql
CREATE OR REPLACE PACKAGE pricing_api_lab AS
    FUNCTION net_amount (
        p_amount   IN NUMBER,
        p_tax_rate IN NUMBER
    ) RETURN NUMBER;
END pricing_api_lab;
/

CREATE OR REPLACE PACKAGE BODY pricing_api_lab AS
    FUNCTION net_amount (
        p_amount   IN NUMBER,
        p_tax_rate IN NUMBER
    ) RETURN NUMBER
    IS
        PRAGMA UDF;
    BEGIN
        RETURN p_amount * (1 - p_tax_rate);
    END net_amount;
END pricing_api_lab;
/
~~~

Gọi từ SQL:

~~~sql
SELECT
    order_id,
    pricing_api_lab.net_amount(order_total, 0.10) AS net_amount
FROM orders_lab;
~~~

Public signature nằm trong package specification; pragma được đặt trong implementation function. Caller vẫn gọi cùng tên và chữ ký như bình thường.

### 3.5. UDF không áp dụng cho procedure

PRAGMA UDF được thiết kế cho function. SQL expression cần một giá trị trả về, vì vậy không thể thay procedure bằng UDF để gọi như một biểu thức SQL. Procedure dùng cho thao tác nghiệp vụ/thủ tục; function dùng để trả một giá trị.

## 4. Khi nào function được gọi từ SQL?

Function có thể xuất hiện trong nhiều vị trí SQL nếu đáp ứng quy tắc về datatype, quyền và side effects.

### 4.1. Trong SELECT list

~~~sql
SELECT
    employee_id,
    monthly_salary,
    pricing_api_lab.net_amount(monthly_salary, 0.08) AS salary_after_tax
FROM employee_data_lab;
~~~

Đây là ví dụ điển hình: function tính một giá trị cho mỗi hàng.

### 4.2. Trong WHERE

~~~sql
SELECT employee_id, full_name
FROM employee_data_lab
WHERE pricing_api_lab.is_high_salary(monthly_salary) = 1;
~~~

Nếu function được gọi để lọc từng hàng, chi phí gọi có thể ảnh hưởng lớn. Hãy cân nhắc biểu diễn điều kiện trực tiếp bằng SQL:

~~~sql
SELECT employee_id, full_name
FROM employee_data_lab
WHERE monthly_salary >= 5000;
~~~

SQL thuần thường giúp optimizer nhìn thấy predicate rõ hơn và có thể tận dụng index.

### 4.3. Trong ORDER BY

~~~sql
SELECT employee_id, full_name
FROM employee_data_lab
ORDER BY pricing_api_lab.normalized_name(full_name);
~~~

Function có thể được gọi trong quá trình sắp xếp. Không giả định Oracle chỉ tính một lần cho mỗi hàng hoặc tái sử dụng giá trị từ SELECT list; optimizer quyết định cách thực thi.

### 4.4. Trong GROUP BY

~~~sql
SELECT
    pricing_api_lab.salary_band(monthly_salary) AS salary_band,
    COUNT(*) AS employee_count
FROM employee_data_lab
GROUP BY pricing_api_lab.salary_band(monthly_salary);
~~~

Function tham gia biểu thức nhóm. Nếu cùng biểu thức xuất hiện nhiều nơi, đừng dựa vào việc Oracle luôn chỉ gọi function một lần. Hãy xem execution plan và benchmark.

### 4.5. Trong biểu thức DML

~~~sql
UPDATE employee_data_lab
SET monthly_salary =
    pricing_api_lab.apply_raise(monthly_salary, 0.05)
WHERE department_id = 10;
~~~

Function trả giá trị được dùng làm biểu thức cập nhật. Những giới hạn về side effects và truy cập bảng vẫn áp dụng. Không dùng UDF để lén thực hiện một chuỗi DML khác bên trong function.

### 4.6. Function trong SQL không đồng nghĩa function được gọi đúng một lần

Một biểu thức function có thể xuất hiện trong SELECT, WHERE và ORDER BY. Optimizer có quyền biến đổi truy vấn, đánh giá biểu thức ở các bước khác nhau hoặc loại bỏ biểu thức không cần thiết. Vì vậy:

- Không dựa vào số lần function được gọi.
- Không dùng function SQL để tăng sequence hoặc ghi log theo số lần gọi nếu logic phụ thuộc số lần.
- Không dựa vào thứ tự đánh giá giữa hai function expression.
- Không giả định alias trong SELECT bảo đảm biểu thức chỉ được tính một lần.

Thiết kế function gọi từ SQL nên tránh side effects và chỉ trả kết quả dựa trên input/context đã được xác định.

## 5. Điều kiện để function được gọi từ SQL

PRAGMA UDF không xóa bỏ các quy tắc SQL-callable function. Function phải đáp ứng các điều kiện cơ bản của SQL engine.

### 5.1. Parameter mode

Các tham số của function được gọi từ SQL phải là tham số đầu vào phù hợp; không dùng OUT hoặc IN OUT như một cách trả thêm dữ liệu cho câu SQL.

Không thiết kế:

~~~sql
FUNCTION calculate_value (
    p_input IN NUMBER,
    p_detail OUT VARCHAR2
) RETURN NUMBER;
~~~

để gọi trực tiếp trong SELECT. Nếu cần nhiều giá trị, cân nhắc trả SQL object type/collection phù hợp, dùng nhiều scalar functions khi hợp lý, hoặc trả result set qua REF CURSOR ở API PL/SQL.

### 5.2. Datatype phải được SQL nhận diện

Function dùng trong SQL cần parameter/return type mà SQL engine hỗ trợ ở release mục tiêu. Các kiểu thông dụng gồm NUMBER, VARCHAR2, DATE, TIMESTAMP và SQL object/collection types thích hợp.

Trong Oracle 19c, PL/SQL BOOLEAN không phải SQL datatype dùng trực tiếp trong SQL expression. Vì vậy, ví dụ SQL-callable nên dùng NUMBER/CHAR để biểu diễn cờ:

~~~sql
FUNCTION is_active (
    p_status IN VARCHAR2
) RETURN NUMBER;
~~~

Quy ước có thể là 1 = active, 0 = inactive. Từ Oracle Database 23c/23ai, SQL có BOOLEAN datatype; khả năng tương tác PL/SQL/SQL được mở rộng. Khi code cần chạy nhiều release, hãy chọn contract tương thích với release thấp nhất.

### 5.3. Không trả local PL/SQL RECORD như SQL value

Một RECORD khai báo trong PL/SQL block/package không tự trở thành datatype SQL. Function được gọi trong SELECT không thể tùy ý trả một local PL/SQL record làm một cột SQL.

Nếu cần trả nhiều trường dưới dạng một giá trị SQL, cân nhắc:

- SQL object type được tạo bằng CREATE TYPE.
- Scalar columns riêng.
- SQL collection type phù hợp.
- REF CURSOR nếu API là thủ tục PL/SQL trả result set.
- JSON/XML nếu đó là contract đã được chọn.

### 5.4. Function phải có quyền truy cập object cần thiết

Function truy vấn bảng/view cần quyền phù hợp theo AUTHID:

- Mặc định stored PL/SQL unit dùng definer rights.
- Definer-rights function dùng quyền của owner theo quy tắc Oracle.
- Static SQL trong stored code cần direct object grants thích hợp; quyền chỉ có qua role không thay thế direct grant cho compile/use của definer-rights code.
- AUTHID CURRENT_USER chuyển sang invoker-rights model và cần kiểm thử bằng caller thực tế.

PRAGMA UDF không cấp thêm quyền, không bỏ qua object privilege và không thay đổi AUTHID.

### 5.5. Function phải compile hợp lệ

Kiểm tra:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_type IN ('FUNCTION', 'PACKAGE', 'PACKAGE BODY')
ORDER BY object_type, object_name;

SELECT name, type, line, position, text
FROM user_errors
ORDER BY name, type, sequence;
~~~

Function INVALID hoặc package body có lỗi sẽ không thể được gọi ổn định từ SQL.

## 6. Giới hạn về side effects và transaction

Function được gọi từ SQL nên được thiết kế như một phép tính trả về giá trị. Các side effects có thể vi phạm kỳ vọng của SQL optimizer và chịu những hạn chế riêng.

### 6.1. Không dùng function SELECT để cập nhật bảng

Ví dụ không nên:

~~~sql
CREATE OR REPLACE FUNCTION read_and_log_lab (
    p_employee_id IN NUMBER
) RETURN NUMBER
IS
BEGIN
    INSERT INTO function_log_lab(employee_id, logged_at)
    VALUES (p_employee_id, SYSTIMESTAMP);

    RETURN p_employee_id;
END;
/
~~~

Khi function được gọi từ SELECT, thao tác DML thông thường bị hạn chế và có thể phát sinh ORA-14551: cannot perform a DML operation inside a query. Có ngoại lệ kỹ thuật với autonomous transaction, nhưng không nên xem đó là cách mặc định để biến function SQL thành nơi ghi log.

### 6.2. DML trong function và autonomous transaction

Oracle cho phép một số trường hợp function dùng PRAGMA AUTONOMOUS_TRANSACTION để thực hiện transaction độc lập. Tuy nhiên, cách này thay đổi semantics:

- Dữ liệu log có thể commit dù câu SELECT bên ngoài thất bại.
- Function có thể được gọi nhiều lần hơn dự kiến.
- Kết quả truy vấn không còn là phép tính thuần.
- Transaction độc lập có thể tạo contention hoặc deadlock nếu truy cập tài nguyên liên quan.

Chỉ dùng autonomous transaction khi yêu cầu audit thật sự cần tính độc lập và đã hiểu rõ ranh giới transaction. Với function dùng trong SELECT thông thường, ưu tiên không có DML side effect.

### 6.3. Không COMMIT/ROLLBACK trong function SQL

Một function được gọi từ SQL không thể tùy tiện điều khiển transaction của câu lệnh gọi. COMMIT, ROLLBACK và các lệnh điều khiển transaction trong function thông thường bị cấm theo ngữ cảnh SQL và có thể phát sinh lỗi như ORA-14552. Không dùng function để quyết định commit transaction của caller.

### 6.4. DDL và session control không phù hợp

Không thực hiện DDL, ALTER SESSION, transaction control hoặc system control từ function được gọi trong SQL. Nếu cần thay đổi schema/session, hãy thực hiện qua procedure hoặc tầng quản trị riêng, với transaction boundary rõ ràng.

### 6.5. Function gọi từ DML có giới hạn riêng

Khi function được gọi trong một câu UPDATE/DELETE/MERGE, cần tránh đọc hoặc sửa bảng đang được câu lệnh đó tác động theo cách vi phạm quy tắc mutating/SQL-invoked function. Trường hợp cụ thể có thể dẫn đến ORA-04091 hoặc lỗi side-effect khác. Hãy đưa logic cần cập nhật vào chính câu DML, dùng trigger đúng mục đích hoặc tách thành các bước transaction được thiết kế rõ.

### 6.6. Không dựa vào thứ tự đánh giá của function

Ví dụ:

~~~sql
SELECT
    function_a(col),
    function_b(col)
FROM source_table;
~~~

Không có cam kết function_a luôn chạy trước function_b. Cũng không có cam kết function được gọi một lần cho mỗi hàng hoặc chỉ một lần khi biểu thức lặp lại. Side effect dựa trên thứ tự/số lần gọi có thể gây lỗi logic.

## 7. PRAGMA UDF có và không làm gì?

| Khả năng | PRAGMA UDF |
| --- | --- |
| Báo compiler function chủ yếu được gọi từ SQL | Có |
| Có thể giảm overhead khi SQL gọi PL/SQL | Có, tùy workload |
| Thay đổi kết quả function | Không |
| Cache kết quả theo input | Không |
| Bảo đảm function chạy đúng một lần mỗi hàng | Không |
| Làm function deterministic | Không |
| Cho phép OUT/IN OUT parameters trong SQL | Không |
| Cho phép DML/COMMIT/DDL trong SQL function | Không |
| Tự biến PL/SQL RECORD thành SQL datatype | Không |
| Thay thế SQL rewrite/index/plan tuning | Không |

PRAGMA UDF là tối ưu hóa đường gọi; các yêu cầu về tính đúng đắn, SQL compatibility, security và side effects vẫn giữ nguyên.

## 8. Phân biệt PRAGMA UDF với các pragma/feature khác

Nhiều tính năng có thể xuất hiện cùng một function nhưng giải quyết các vấn đề khác nhau.

### 8.1. UDF và DETERMINISTIC

DETERMINISTIC là lời khai báo rằng function trả cùng kết quả khi nhận cùng input trong điều kiện semantics được cam kết:

~~~sql
CREATE OR REPLACE FUNCTION normalize_code_lab (
    p_code IN VARCHAR2
) RETURN VARCHAR2
DETERMINISTIC
IS
BEGIN
    RETURN UPPER(TRIM(p_code));
END;
/
~~~

Khác biệt:

- PRAGMA UDF: tối ưu chi phí gọi function từ SQL.
- DETERMINISTIC: cam kết về tính ổn định của kết quả theo input; có thể liên quan function-based index và các tối ưu khác.

Không khai báo DETERMINISTIC nếu kết quả phụ thuộc bảng thay đổi, SYSDATE/SYSTIMESTAMP, NLS settings, application context, package state hoặc dữ liệu session. Khai báo sai có thể khiến kết quả/index không còn đúng.

DETERMINISTIC không phải cache tự động có thời hạn và không bảo đảm function chỉ được thực thi một lần.

### 8.2. UDF và RESULT_CACHE

RESULT_CACHE yêu cầu Oracle lưu kết quả function trong result cache theo cơ chế hỗ trợ:

- PRAGMA UDF tập trung giảm overhead khi gọi.
- RESULT_CACHE tập trung tái sử dụng kết quả đã tính khi cache hợp lệ.
- Một function có thể được thiết kế để dùng cả hai nếu semantics và release cho phép, nhưng hai cơ chế không thay thế nhau.

Result cache có quy tắc invalidation/dependency và tiêu thụ bộ nhớ. Không dùng cache cho kết quả phụ thuộc session hoặc dữ liệu thay đổi theo cách không được quản lý.

### 8.3. UDF và PRAGMA INLINE

PRAGMA INLINE là chỉ dẫn compiler liên quan việc inline lời gọi subprogram PL/SQL trong code PL/SQL:

- PRAGMA UDF nhắm đến function được SQL gọi.
- PRAGMA INLINE nhắm đến tối ưu lời gọi subprogram trong PL/SQL compilation.

Không dùng PRAGMA INLINE như một cách thay thế PRAGMA UDF cho SQL-to-PLSQL boundary.

### 8.4. UDF và PARALLEL_ENABLE

PARALLEL_ENABLE liên quan khả năng function tham gia xử lý parallel execution theo các điều kiện Oracle quy định. PRAGMA UDF không làm function parallel-safe. Nếu cần parallel query, phải đánh giá riêng tính an toàn, trạng thái và dependency của function.

### 8.5. UDF và SQL macro

SQL macro là một cơ chế khác: macro mở rộng thành biểu thức/query SQL để optimizer nhìn thấy logic SQL, thay vì gọi PL/SQL function cho mỗi hàng. Khả năng SQL macro phụ thuộc phiên bản và Release Update. Scalar SQL macro và table SQL macro có mốc hỗ trợ khác nhau; cần đối chiếu tài liệu release đích trước khi dùng.

Nếu logic có thể viết thành SQL expression hoặc SQL macro được hỗ trợ, giải pháp đó có thể giúp optimizer tối ưu toàn bộ biểu thức tốt hơn một function PL/SQL. PRAGMA UDF vẫn hữu ích khi cần giữ logic PL/SQL và function thực sự được gọi từ SQL.

## 9. Điều kiện hỗ trợ theo phiên bản Oracle

PRAGMA UDF được giới thiệu trong Oracle Database 12c Release 1 (12.1). Function PL/SQL vẫn có thể được gọi từ SQL trước phiên bản này; điều chưa có là pragma UDF để yêu cầu compiler tối ưu đường gọi theo tính năng đó.

| Phiên bản | PRAGMA UDF | Lưu ý |
| --- | --- | --- |
| Oracle 11g và cũ hơn | Không hỗ trợ | Stored function vẫn có thể được gọi từ SQL nếu đáp ứng quy tắc; không khai báo PRAGMA UDF |
| Oracle 12c Release 1 (12.1) | Được giới thiệu | Có thể dùng PRAGMA UDF trong function |
| Oracle 12c Release 2 (12.2) | Hỗ trợ | Vẫn phải tuân thủ SQL-callable function restrictions |
| Oracle 18c | Hỗ trợ | Kiểm tra compatibility khi triển khai code giữa môi trường |
| Oracle 19c | Hỗ trợ | Phiên bản dùng trong các ví dụ của bài |
| Oracle 21c | Hỗ trợ | Các tính năng SQL khác như SQL macro có thể có thêm lựa chọn tùy loại macro |
| Oracle 23c/23ai | Hỗ trợ | SQL/PLSQL interoperability được mở rộng, bao gồm SQL BOOLEAN; vẫn kiểm tra từng datatype/API |

### 9.1. Database version không phải compatibility setting duy nhất

Khi triển khai trong môi trường nhiều database, cần kiểm tra:

- Version chính xác của database.
- Release Update (RU) và patch level.
- COMPATIBLE initialization parameter.
- Client/driver version nếu function được gọi qua ứng dụng.
- Cấu hình compile và quyền trên schema.

Một feature xuất hiện trong release mới không có nghĩa mọi database trong cùng hệ thống đã được nâng cấp hoặc bật compatibility tương ứng.

### 9.2. Không giả định PRAGMA UDF được bỏ qua trên phiên bản cũ

Nếu source chứa PRAGMA UDF mà compile trên database không hỗ trợ, compiler có thể báo lỗi cú pháp/pragma không hợp lệ. Không nên gửi cùng một source cho nhiều release mà không có migration/version strategy.

### 9.3. Giữ source tương thích nhiều phiên bản

Nếu cần hỗ trợ cả 11g và 12c+:

- Dùng function source không có PRAGMA UDF làm baseline tương thích.
- Duy trì source variant hoặc deployment script riêng cho 12c+ nếu benchmark chứng minh có lợi.
- Không đưa pragma vào function dùng chung nếu môi trường thấp nhất không hỗ trợ.
- Kiểm thử compile trong database có version thấp nhất được cam kết.

### 9.4. BOOLEAN và SQL interoperability

Trong Oracle 19c, BOOLEAN là kiểu PL/SQL và không thể dùng trực tiếp như SQL datatype trong một SELECT thông thường. Có thể trả NUMBER hoặc CHAR để biểu diễn true/false.

Oracle Database 23c/23ai bổ sung BOOLEAN trong SQL, mở rộng khả năng tương tác. Tuy nhiên, nếu package API phải chạy trên cả 19c và 23ai, hãy giữ kiểu trả về tương thích chung hoặc tạo API riêng theo version.

## 10. Thiết kế function phù hợp với SQL

### 10.1. Ưu tiên function không có side effects

Function tốt cho SQL thường:

- Nhận input rõ ràng.
- Tính toán và trả về một giá trị.
- Không INSERT/UPDATE/DELETE.
- Không COMMIT/ROLLBACK.
- Không thay đổi package state.
- Không phụ thuộc vào thứ tự gọi.
- Không dựa vào số lần optimizer đánh giá biểu thức.

Ví dụ:

~~~sql
CREATE OR REPLACE FUNCTION normalize_email_udf (
    p_email IN VARCHAR2
) RETURN VARCHAR2
IS
    PRAGMA UDF;
BEGIN
    IF p_email IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN LOWER(TRIM(p_email));
END normalize_email_udf;
/
~~~

### 10.2. Tránh đọc dữ liệu thay đổi nếu có thể

Function tra cứu bảng cấu hình có thể tiện:

~~~sql
FUNCTION get_tax_rate(p_region_code VARCHAR2) RETURN NUMBER;
~~~

Nhưng khi được gọi cho nhiều hàng, nó có thể tạo nhiều SQL calls lồng nhau. Kết quả còn phụ thuộc dữ liệu cấu hình, quyền và transaction visibility. Nếu có thể, JOIN bảng cấu hình trực tiếp trong SQL thường rõ ràng và dễ tối ưu hơn.

### 10.3. Tránh gọi function lồng nhau quá nhiều tầng

~~~text
SQL query
  -> function A
       -> function B
            -> function C
                 -> SELECT config table
~~~

Mỗi tầng có thể tăng chi phí gọi và làm khó hiểu execution behavior. Nếu logic là phép biến đổi dữ liệu, hãy cân nhắc gộp thành một function nhỏ hoặc biểu thức SQL.

### 10.4. Xử lý NULL tường minh

SQL dùng ba giá trị logic TRUE/FALSE/UNKNOWN. Function cần xác định rõ input NULL trả gì:

~~~sql
CREATE OR REPLACE FUNCTION safe_discount_udf (
    p_amount IN NUMBER,
    p_rate IN NUMBER
) RETURN NUMBER
IS
    PRAGMA UDF;
BEGIN
    IF p_amount IS NULL OR p_rate IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN p_amount * p_rate;
END;
/
~~~

Không để caller phải đoán semantics NULL. Nếu NULL phải được coi là 0, thể hiện điều đó trong function hoặc SQL expression một cách nhất quán.

### 10.5. Kiểm soát NLS và session dependence

Kết quả function có thể thay đổi theo:

- NLS_DATE_FORMAT/NLS_NUMERIC_CHARACTERS.
- Session time zone.
- Current schema.
- Application context.
- Current user.
- Package state.
- SYSDATE/SYSTIMESTAMP.

Nếu function phụ thuộc các yếu tố này, đừng khai báo DETERMINISTIC chỉ để tạo function-based index hoặc mong cache. Truyền input tường minh và chuẩn hóa định dạng thường an toàn hơn.

## 11. Đo hiệu năng trước và sau PRAGMA UDF

Không nên kết luận UDF nhanh hơn chỉ vì compiler hỗ trợ. Hãy benchmark trên dữ liệu và câu truy vấn đại diện.

### 11.1. Tạo bảng lab

~~~sql
CREATE TABLE udf_sales_lab AS
SELECT
    LEVEL AS sale_id,
    MOD(LEVEL, 10000) + 1 AS gross_amount
FROM dual
CONNECT BY LEVEL <= 100000;
~~~

### 11.2. Tạo function không có UDF

~~~sql
CREATE OR REPLACE FUNCTION tax_net_plain_lab (
    p_amount IN NUMBER,
    p_rate IN NUMBER
) RETURN NUMBER
IS
BEGIN
    RETURN p_amount * (1 - p_rate);
END tax_net_plain_lab;
/
~~~

### 11.3. Tạo function có UDF

~~~sql
CREATE OR REPLACE FUNCTION tax_net_udf_lab (
    p_amount IN NUMBER,
    p_rate IN NUMBER
) RETURN NUMBER
IS
    PRAGMA UDF;
BEGIN
    RETURN p_amount * (1 - p_rate);
END tax_net_udf_lab;
/
~~~

### 11.4. Chạy hai truy vấn tương đương

~~~sql
SELECT SUM(tax_net_plain_lab(gross_amount, 0.10))
FROM udf_sales_lab;

SELECT SUM(tax_net_udf_lab(gross_amount, 0.10))
FROM udf_sales_lab;
~~~

Hai câu SQL thực hiện cùng phép tính trên cùng dữ liệu. Ghi nhận elapsed time, CPU, logical reads và execution plan.

### 11.5. Đo bằng PL/SQL timer

Có thể dùng DBMS_UTILITY.GET_TIME trong block lab:

~~~sql
SET SERVEROUTPUT ON

DECLARE
    l_start PLS_INTEGER;
    l_elapsed PLS_INTEGER;
    l_total NUMBER;
BEGIN
    l_start := DBMS_UTILITY.GET_TIME;

    SELECT SUM(tax_net_plain_lab(gross_amount, 0.10))
    INTO l_total
    FROM udf_sales_lab;

    l_elapsed := DBMS_UTILITY.GET_TIME - l_start;
    DBMS_OUTPUT.PUT_LINE('Plain ticks=' || l_elapsed);
    DBMS_OUTPUT.PUT_LINE('Total=' || l_total);

    l_start := DBMS_UTILITY.GET_TIME;

    SELECT SUM(tax_net_udf_lab(gross_amount, 0.10))
    INTO l_total
    FROM udf_sales_lab;

    l_elapsed := DBMS_UTILITY.GET_TIME - l_start;
    DBMS_OUTPUT.PUT_LINE('UDF ticks=' || l_elapsed);
    DBMS_OUTPUT.PUT_LINE('Total=' || l_total);
END;
/
~~~

GET_TIME trả đơn vị centiseconds theo tài liệu Oracle; đây là phép đo thô cho lab. Với workload production, dùng SQL trace, SQL Monitor, AWR/ASH theo quyền và license, hoặc công cụ benchmark được tổ chức cho phép.

### 11.6. Quy tắc benchmark

- Chạy warm-up trước khi ghi số liệu.
- Chạy nhiều vòng và so sánh median/percentile, không chọn một lần chạy thuận lợi.
- Dùng cùng dữ liệu, bind values, session settings và execution plan conditions.
- Đảo thứ tự chạy giữa các vòng để giảm bias cache.
- Không bật DBMS_OUTPUT cho từng hàng.
- Không để concurrent workload không kiểm soát làm sai phép đo.
- So sánh kết quả trả về để bảo đảm hai function có semantics giống nhau.
- Kiểm tra execution plan và SQL Monitor nếu có.

### 11.7. UDF không bảo đảm speedup

Nếu function được gọi ít lần, function làm công việc nặng hoặc truy vấn chủ yếu tốn I/O, khác biệt có thể nhỏ. Optimizer có thể đã loại bỏ một phần công việc, hoặc function body có nested SQL làm chi phí khác chiếm ưu thế. Chỉ giữ pragma khi benchmark trên workload thực tế cho thấy lợi ích hoặc có lý do kỹ thuật rõ ràng.

## 12. So sánh với viết lại bằng SQL thuần

Trước khi thêm UDF, hãy hỏi liệu logic có thể biểu diễn trực tiếp bằng SQL không.

### 12.1. Function tính thuế

Function:

~~~sql
net_amount_udf(order_total, 0.10)
~~~

SQL thuần:

~~~sql
order_total * (1 - 0.10)
~~~

Nếu logic đơn giản, SQL expression tránh gọi PL/SQL.

### 12.2. Function phân nhóm

Function:

~~~sql
salary_band(monthly_salary)
~~~

SQL:

~~~sql
CASE
    WHEN monthly_salary < 3000 THEN 'LOW'
    WHEN monthly_salary < 7000 THEN 'MID'
    ELSE 'HIGH'
END
~~~

CASE cho optimizer thấy toàn bộ điều kiện và tránh boundary call.

### 12.3. Function tra cứu tên

Function:

~~~sql
department_name(employee.department_id)
~~~

SQL JOIN:

~~~sql
SELECT e.employee_id, d.department_name
FROM employee_data_lab e
JOIN department_lab d
  ON d.department_id = e.department_id;
~~~

JOIN thường dễ tối ưu hơn việc gọi function để SELECT một hàng phòng ban cho từng nhân viên.

### 12.4. Function phức tạp cần tái sử dụng

Nếu logic quá phức tạp hoặc được nhiều ứng dụng sử dụng, PL/SQL function vẫn có thể là lựa chọn hợp lý. Khi đó:

- Giữ function stateless/pure nếu có thể.
- Thêm PRAGMA UDF nếu phiên bản hỗ trợ và workload phù hợp.
- Xem xét SQL macro nếu muốn mở rộng logic thành SQL và release hỗ trợ.
- Benchmark cả phương án function và SQL rewrite.

## 13. PRAGMA UDF, function-based index và optimizer

PRAGMA UDF không tự tạo index và không làm predicate trở thành sargable.

### 13.1. Function trong WHERE có thể cản index

~~~sql
SELECT *
FROM employee_data_lab
WHERE normalize_email_udf(work_email) = 'user@example.test';
~~~

Nếu index chỉ được tạo trên WORK_EMAIL, biểu thức function trên cột có thể khiến index thông thường không được sử dụng theo cách mong muốn. UDF chỉ giảm chi phí gọi function, không biến index trên cột gốc thành index trên biểu thức.

### 13.2. Function-based index

Nếu biểu thức được dùng thường xuyên và function đáp ứng điều kiện, có thể cân nhắc function-based index:

~~~sql
CREATE INDEX ix_employee_email_norm_lab
ON employee_data_lab(LOWER(TRIM(work_email)));
~~~

Khi truy vấn dùng biểu thức tương ứng, optimizer có thể dùng index nếu điều kiện phù hợp. Với user-defined function trong index, cần tuân thủ yêu cầu DETERMINISTIC và các quy tắc function-based index của Oracle.

### 13.3. UDF không thay thế DETERMINISTIC

Không thêm PRAGMA UDF rồi nghĩ Oracle có thể dùng kết quả cũ của function. Nếu function-based index hoặc cache yêu cầu tính deterministic, phải đáp ứng riêng yêu cầu đó.

### 13.4. Kiểm tra execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT SUM(tax_net_udf_lab(gross_amount, 0.10))
FROM udf_sales_lab;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

Execution plan cho biết cách Oracle đọc bảng và xử lý SQL ở mức plan. Nó không luôn thể hiện đầy đủ số lần function thực sự được gọi; kết hợp runtime statistics/trace khi cần.

## 14. Function gọi từ SQL và security

### 14.1. Definer rights mặc định

Stored function mặc định chạy theo quyền của owner (AUTHID DEFINER). Nếu function truy cập bảng cấu hình hoặc dữ liệu khác schema, owner cần quyền trực tiếp phù hợp cho static SQL.

### 14.2. Invoker rights

Có thể khai báo:

~~~sql
CREATE OR REPLACE FUNCTION current_user_region_lab
RETURN VARCHAR2
AUTHID CURRENT_USER
IS
    PRAGMA UDF;
BEGIN
    RETURN SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA');
END;
/
~~~

AUTHID CURRENT_USER làm function dùng invoker-rights model theo quy tắc Oracle. Đây là thay đổi security semantics, không phải tùy chọn tối ưu hiệu năng. Chỉ dùng khi thiết kế quyền yêu cầu hành vi đó.

### 14.3. Không dùng UDF để che giấu quyền truy cập

PRAGMA UDF không thay đổi privilege checks, không làm function có quyền cao hơn caller và không bỏ qua VPD/RLS hoặc security policy. Kiểm thử function bằng user thật sự sẽ gọi nó.

### 14.4. SQL-callable function và application context

Function có thể đọc SYS_CONTEXT hoặc session attributes. Nếu kết quả phụ thuộc context, cùng input vẫn có thể trả kết quả khác nhau giữa session. Không khai báo DETERMINISTIC hoặc dùng cache theo giả định chỉ input parameter quyết định kết quả nếu context không được tính vào semantics.

## 15. Phiên bản, compatibility và chiến lược triển khai

### 15.1. Kiểm tra version database

~~~sql
SELECT banner
FROM v$version;
~~~

Hoặc:

~~~sql
SELECT version
FROM product_component_version
WHERE product LIKE 'Oracle Database%';
~~~

Quyền đọc V$VERSION có thể khác nhau theo môi trường; dùng view được DBA cho phép.

### 15.2. Kiểm tra COMPATIBLE

DBA có thể kiểm tra:

~~~sql
SHOW PARAMETER compatible
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'compatible';
~~~

COMPATIBLE là một phần của database compatibility policy. Không nâng tham số này chỉ để thử PRAGMA UDF; pragma được hỗ trợ theo release của database và phải được xác nhận trong tài liệu phiên bản.

### 15.3. Triển khai nhiều môi trường

Một pipeline có thể có DEV trên 23ai, TEST trên 19c và PROD trên 19c RU cũ hơn. Không chỉ kiểm tra code trên DEV rồi triển khai nguyên trạng. Hãy:

1. Xác định version/RU của môi trường thấp nhất.
2. Xác định pragma và datatype được hỗ trợ ở môi trường đó.
3. Compile trong môi trường đại diện.
4. Chạy smoke test từ SQL.
5. Benchmark trong workload tương đương.
6. Giữ source variant nếu cần hỗ trợ version khác nhau.

### 15.4. Tương thích API và datatype

Nếu function public trả BOOLEAN hoặc type mới chỉ có trong release mới, caller 19c sẽ không compile. Có thể giữ contract chung bằng NUMBER/CHAR hoặc tạo package API theo phiên bản. UDF không giải quyết chênh lệch datatype giữa SQL engine các release.

## 16. Các lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| PLS-00710 hoặc lỗi pragma không hợp lệ | Database không hỗ trợ PRAGMA UDF hoặc pragma đặt sai vị trí | Kiểm tra version và đặt trong declarative section của function |
| Function không gọi được trong SELECT | Return/parameter type không tương thích SQL hoặc function invalid | Kiểm tra signature, datatype và USER_ERRORS |
| PLS-00306 khi gọi function | Số lượng/type đối số không khớp | Sửa lời gọi và overload |
| ORA-14551 | Function thực hiện DML trong query | Bỏ side effect hoặc tách thành procedure/transaction riêng |
| ORA-14552 | Function cố điều khiển transaction/DDL trong SQL context | Không COMMIT/ROLLBACK/DDL trong SQL-called function |
| ORA-04091 | Truy cập bảng đang mutating trong ngữ cảnh DML/trigger | Thiết kế lại SQL/trigger hoặc tách xử lý |
| Kết quả khác giữa hai lần gọi | Function phụ thuộc thời gian, session, context hoặc dữ liệu thay đổi | Làm dependency rõ ràng; không khai báo DETERMINISTIC sai |
| Thêm UDF nhưng không nhanh hơn | Function ít được gọi, bottleneck nằm ở I/O/nested SQL hoặc optimizer đã tối ưu | Benchmark và xem plan/runtime statistics |
| Function gọi nhiều lần ngoài dự kiến | SQL optimizer đánh giá biểu thức ở nhiều bước | Không phụ thuộc call count; viết function không side effect |
| Function-based index không dùng | Biểu thức không khớp hoặc function/index không đáp ứng điều kiện | Kiểm tra index definition, DETERMINISTIC và execution plan |
| Compile được ở 23ai nhưng lỗi ở 19c | Dùng datatype/feature chỉ có ở release mới | Chọn contract tương thích hoặc source theo version |

## 17. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| PRAGMA UDF biến PL/SQL thành SQL | Function vẫn là PL/SQL |
| UDF loại bỏ hoàn toàn context switch | Nó có thể giảm overhead, không bảo đảm xóa mọi chi phí |
| UDF tự cache kết quả | Không; RESULT_CACHE là cơ chế khác |
| UDF làm function deterministic | Không |
| SQL luôn gọi function đúng một lần mỗi hàng | Optimizer có thể đánh giá nhiều lần hoặc loại bỏ expression |
| UDF cho phép OUT/IN OUT trong SELECT | Không |
| UDF cho phép function ghi bảng | Không; side-effect restrictions vẫn áp dụng |
| UDF làm function-based index tự dùng được | Không; index và deterministic requirements là vấn đề riêng |
| UDF áp dụng cho procedure | Không, pragma dành cho function |
| Function SQL có thể trả mọi PL/SQL type | Return/parameter type phải được SQL hỗ trợ ở release đó |
| Có thể dùng BOOLEAN trong SQL trên Oracle 19c | BOOLEAN là PL/SQL-only trong 19c; SQL BOOLEAN có ở 23c/23ai |
| Mọi function đều nên thêm UDF | Chỉ thêm khi function được SQL gọi và benchmark/thiết kế cho thấy phù hợp |

## 18. Checklist trước khi dùng PRAGMA UDF

**Tính năng và phiên bản**

- Database có phải Oracle 12.1 trở lên không?
- RU/COMPATIBLE và datatype có phù hợp không?
- Source có phải chạy trên nhiều version không?

**Function contract**

- Function có parameter IN phù hợp không?
- Return/parameter datatype có phải SQL datatype được hỗ trợ không?
- Function có compile VALID không?
- Caller có quyền EXECUTE và function owner có direct grants cần thiết không?

**Semantics**

- Function có tránh DML, DDL và transaction control không?
- Có side effect hoặc phụ thuộc call count/order không?
- NULL, NLS, time zone và application context đã được xác định chưa?
- Có khai báo DETERMINISTIC/RESULT_CACHE đúng semantics không?

**Hiệu năng**

- Function có được gọi nhiều lần từ SQL không?
- Có thể viết lại bằng SQL thuần không?
- Đã benchmark hai phương án trên cùng dữ liệu chưa?
- Đã kiểm tra plan, CPU, elapsed time và nested SQL chưa?
- Có giữ pragma vì lợi ích đo được hoặc lý do rõ ràng không?

## 19. Bài thực hành tổng hợp

Lab này so sánh function thường và function có PRAGMA UDF.

### Bước 1 — Tạo dữ liệu

~~~sql
CREATE TABLE udf_sales_lab (
    sale_id NUMBER PRIMARY KEY,
    gross_amount NUMBER(12,2) NOT NULL
);

INSERT INTO udf_sales_lab(sale_id, gross_amount)
SELECT LEVEL, MOD(LEVEL, 10000) + 1
FROM dual
CONNECT BY LEVEL <= 100000;

COMMIT;
~~~

### Bước 2 — Function thường

~~~sql
CREATE OR REPLACE FUNCTION tax_net_plain_lab (
    p_amount IN NUMBER,
    p_rate IN NUMBER
) RETURN NUMBER
IS
BEGIN
    RETURN p_amount * (1 - p_rate);
END;
/
~~~

### Bước 3 — Function có UDF

~~~sql
CREATE OR REPLACE FUNCTION tax_net_udf_lab (
    p_amount IN NUMBER,
    p_rate IN NUMBER
) RETURN NUMBER
IS
    PRAGMA UDF;
BEGIN
    RETURN p_amount * (1 - p_rate);
END;
/
~~~

### Bước 4 — So sánh kết quả

~~~sql
SELECT SUM(tax_net_plain_lab(gross_amount, 0.10)) AS total_plain
FROM udf_sales_lab;

SELECT SUM(tax_net_udf_lab(gross_amount, 0.10)) AS total_udf
FROM udf_sales_lab;
~~~

Hai tổng phải giống nhau.

### Bước 5 — So sánh runtime

Chạy mỗi query nhiều lần, ghi elapsed time và CPU. Dùng warm-up và cùng session settings. Không kết luận từ một lần chạy.

### Bước 6 — So sánh SQL thuần

~~~sql
SELECT SUM(gross_amount * (1 - 0.10)) AS total_sql
FROM udf_sales_lab;
~~~

SQL thuần là baseline hữu ích để xem việc gọi PL/SQL function có cần thiết không.

### Bước 7 — Kiểm tra status và lỗi

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN (
    'TAX_NET_PLAIN_LAB',
    'TAX_NET_UDF_LAB'
)
ORDER BY object_name;

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('TAX_NET_PLAIN_LAB', 'TAX_NET_UDF_LAB')
ORDER BY name, sequence;
~~~

### Bước 8 — Dọn lab (tùy chọn)

~~~sql
DROP FUNCTION tax_net_plain_lab;
DROP FUNCTION tax_net_udf_lab;
DROP TABLE udf_sales_lab PURGE;
~~~

Chỉ chạy nếu chắc chắn object thuộc lab và không cần dữ liệu nữa. DROP là DDL có implicit commit.

## Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Language Reference — UDF Pragma](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/UDF-pragma.html): cú pháp và mục đích của PRAGMA UDF.
- [Oracle Database PL/SQL Language Reference — PL/SQL Functions Invoked from SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-functions-that-sql-statements-can-invoke.html): điều kiện và giới hạn của function được gọi từ SQL.
- [Oracle Database PL/SQL Language Reference — DETERMINISTIC Clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/DETERMINISTIC-clause.html): semantics của function deterministic.
- [Oracle Database PL/SQL Language Reference — RESULT_CACHE Clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/RESULT_CACHE-clause.html): PL/SQL function result cache.
- [Oracle Database PL/SQL Language Reference — Function-Based Indexes](https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/indexes.html): index trên biểu thức và yêu cầu liên quan.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): SQL datatypes và biểu thức SQL.
- [Oracle Database 23ai SQL Language Reference — Data Types](https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/Data-Types.html): datatype SQL, bao gồm BOOLEAN ở release mới.

**Nguyên tắc cần nhớ:** PRAGMA UDF báo compiler rằng function chủ yếu được gọi từ SQL và có thể giảm chi phí chuyển ngữ cảnh. Nó được hỗ trợ từ Oracle Database 12.1, nhưng không thay đổi contract, datatype restrictions, quyền hoặc giới hạn side effects của SQL-callable function. Hãy ưu tiên SQL thuần khi logic có thể biểu diễn trực tiếp; nếu vẫn cần PL/SQL function, giữ function đơn giản và không có side effects, thêm UDF khi phiên bản hỗ trợ, rồi đo trên workload thực tế.

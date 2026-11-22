# Chi phí chuyển ngữ cảnh giữa SQL và PL/SQL trong Oracle

## 1. SQL engine và PL/SQL engine

Oracle Database hỗ trợ cả SQL và PL/SQL, nhưng hai ngôn ngữ này được xử lý bởi các thành phần thực thi có vai trò khác nhau:

- **SQL engine** phân tích và thực thi câu SQL như `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, JOIN, GROUP BY và các phép toán trên tập dữ liệu.
- **PL/SQL engine** thực thi logic thủ tục như biến, phép gán, IF, LOOP, gọi procedure/function và xử lý exception.

Khi chương trình PL/SQL gọi một câu SQL, quyền điều khiển chuyển từ PL/SQL engine sang SQL engine để thực thi câu SQL, sau đó kết quả được trả về PL/SQL engine. Sự chuyển giao này được gọi là **context switch giữa SQL và PL/SQL**.

Ví dụ:

```sql
DECLARE
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM employees;

    DBMS_OUTPUT.PUT_LINE('Employees=' || v_count);
END;
/
```

Trong ví dụ, PL/SQL bắt đầu block, yêu cầu SQL engine chạy `SELECT COUNT(*)`, nhận kết quả rồi tiếp tục thực thi `DBMS_OUTPUT.PUT_LINE`.

Một lần chuyển ngữ cảnh có chi phí điều phối nhất định. Một lần chuyển thường rất nhỏ, nhưng nếu chương trình thực hiện hàng trăm nghìn hoặc hàng triệu lần, tổng chi phí có thể đáng kể. Vì vậy, khi tối ưu PL/SQL, cần chú ý số lần qua lại giữa hai engine chứ không chỉ số dòng code.

Bài học thuộc chương **PL/SQL nâng cao**, tập trung vào nguyên nhân phát sinh context switch, chi phí của xử lý từng hàng, lời gọi function PL/SQL từ SQL, cách thay bằng xử lý set-based, sử dụng `BULK COLLECT` và `FORALL`, cùng phương pháp đo hiệu năng trước và sau tối ưu.

## 2. Context switch xảy ra ở những hướng nào?

Có hai hướng chuyển ngữ cảnh thường gặp:

1. **PL/SQL gọi SQL:** PL/SQL đang chạy một block hoặc loop rồi thực hiện SQL statement. Quyền điều khiển chuyển sang SQL engine và quay lại khi statement hoàn tất hoặc trả batch kết quả.
2. **SQL gọi PL/SQL:** một câu SQL gọi stored function hoặc function trong biểu thức. SQL engine chuyển sang PL/SQL engine để chạy function rồi nhận kết quả.

### 2.1. PL/SQL gọi SQL

```sql
BEGIN
    UPDATE employees
    SET salary = salary * 1.05
    WHERE department_id = 10;
END;
/
```

Block PL/SQL gọi một câu UPDATE. SQL engine xử lý toàn bộ tập hàng phù hợp trong một statement. Đây thường là cách hiệu quả hơn việc lặp qua từng nhân viên rồi chạy một UPDATE riêng cho mỗi hàng.

### 2.2. SQL gọi PL/SQL

```sql
CREATE OR REPLACE FUNCTION employee_bonus (
    p_salary IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_salary * 0.10;
END employee_bonus;
/

SELECT employee_id,
       employee_bonus(salary) AS bonus
FROM employees;
```

SQL engine xử lý truy vấn và cần gọi function PL/SQL để tính bonus cho các hàng kết quả. Mỗi lần function được thực thi có thể cần chuyển quyền điều khiển sang PL/SQL engine và quay lại.

Không giả định function luôn được gọi đúng một lần cho mỗi hàng nhìn thấy trong kết quả. Optimizer có thể biến đổi hoặc đánh giá biểu thức theo cách khác. Điều quan trọng là một function PL/SQL dùng trong SQL có thể tạo overhead đáng kể khi được gọi lặp lại trên tập dữ liệu lớn.

### 2.3. Sơ đồ luồng thực thi

```text
PL/SQL block
    |
    | Gửi SQL statement
    v
SQL engine
    |
    | Trả kết quả / trạng thái
    v
PL/SQL block

SQL statement có gọi PL/SQL function:

SQL engine
    |
    | Gọi function
    v
PL/SQL engine
    |
    | Trả giá trị
    v
SQL engine tiếp tục xử lý query
```

Mục tiêu tối ưu là giảm các lần chuyển không cần thiết, đặc biệt trong vòng lặp lớn và biểu thức function được gọi nhiều lần.

## 3. Vì sao nhiều context switch làm chương trình chậm?

Một lần chuyển ngữ cảnh cần chi phí để chuyển quyền điều khiển, truyền tham số, nhận kết quả và tiếp tục trạng thái thực thi. Chi phí đơn lẻ thường nhỏ so với một truy vấn phức tạp, nhưng số lần lặp có thể khiến tổng thời gian tăng mạnh.

Giả sử một block xử lý 100.000 hàng và mỗi vòng lặp thực hiện một UPDATE:

```sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 50
    ) LOOP
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
```

Luồng có thể hình dung:

1. SQL engine trả một hàng cho PL/SQL loop.
2. PL/SQL lấy employee ID.
3. PL/SQL gửi một UPDATE sang SQL engine.
4. SQL engine thực thi UPDATE và trả trạng thái.
5. PL/SQL tiếp tục hàng kế tiếp.

Với tập 100.000 hàng, code có thể phát sinh rất nhiều lần gọi DML riêng. Mỗi statement còn có chi phí parse/execute, bind, kiểm tra constraint, trigger, duy trì index, redo/undo và khóa hàng tùy thao tác.

Context switch không phải chi phí duy nhất, nhưng thường là dấu hiệu của thiết kế row-by-row khiến database không tận dụng được xử lý theo tập.

## 4. Row-by-row processing: anti-pattern phổ biến

Row-by-row processing là cách lấy từng hàng về PL/SQL rồi thực hiện thao tác riêng cho hàng đó.

### 4.1. Ví dụ tăng lương từng hàng

```sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 50
    ) LOOP
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
```

Code dễ đọc khi mới học, nhưng nếu chỉ cần tăng lương 5% cho toàn bộ nhân viên của phòng ban 50 thì vòng lặp không cần thiết.

### 4.2. Viết lại bằng một câu SQL set-based

```sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = 50;
```

SQL engine xử lý toàn bộ tập hàng trong một statement. PL/SQL chỉ cần gửi một lần câu UPDATE, không phải điều phối một statement riêng cho từng employee.

### 4.3. So sánh

| Tiêu chí | Row-by-row | Set-based |
|---|---|---|
| Số lần gọi DML từ PL/SQL | Có thể một lần mỗi hàng | Một statement cho cả tập |
| Context switch | Nhiều | Ít hơn đáng kể |
| Optimizer nhìn thấy tập dữ liệu | Từng lần xử lý nhỏ | Toàn bộ điều kiện của statement |
| Khả năng tối ưu JOIN/aggregate | Hạn chế nếu code tách nhỏ | SQL engine có thể tối ưu toàn bộ |
| Mức độ phù hợp | Logic thực sự cần quyết định thủ tục theo từng hàng | Phép biến đổi có thể diễn đạt bằng SQL |

### 4.4. Không phải mọi vòng lặp đều sai

Vòng lặp có thể phù hợp khi:

- Mỗi hàng cần gọi một API hoặc xử lý thủ tục riêng.
- Logic phụ thuộc kết quả của hàng trước.
- Cần thực hiện các thao tác không thể biểu diễn bằng một câu SQL.
- Tập dữ liệu nhỏ và đơn giản.
- Đang điều phối nhiều loại công việc khác nhau.

Ngay cả trong các trường hợp đó, nếu có thể gom dữ liệu và giảm số lần gọi SQL, hãy cân nhắc bulk processing.

## 5. Dùng SQL set-based trước khi dùng bulk processing

SQL vốn được thiết kế để thao tác trên tập dữ liệu. Khi có thể diễn đạt nghiệp vụ bằng một câu SQL, hãy ưu tiên cách đó trước `BULK COLLECT` hoặc `FORALL`.

### 5.1. Dùng UPDATE thay cho loop

Row-by-row:

```sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 20
    ) LOOP
        UPDATE employees
        SET commission_pct = 0.10
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/
```

Set-based:

```sql
UPDATE employees
SET commission_pct = 0.10
WHERE department_id = 20;
```

### 5.2. Dùng MERGE thay cho nhiều lần kiểm tra rồi INSERT/UPDATE

Nếu cần đồng bộ bảng đích từ bảng nguồn, `MERGE` có thể xử lý nhiều hàng trong một statement:

```sql
MERGE INTO customer_summary target
USING (
    SELECT customer_id,
           COUNT(*) AS order_count,
           SUM(amount) AS total_amount
    FROM orders
    GROUP BY customer_id
) source
ON (target.customer_id = source.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        target.order_count = source.order_count,
        target.total_amount = source.total_amount
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        order_count,
        total_amount
    )
    VALUES (
        source.customer_id,
        source.order_count,
        source.total_amount
    );
```

Ví dụ giả định bảng `CUSTOMER_SUMMARY` có các cột tương ứng. Một MERGE xử lý toàn bộ kết quả nguồn thay vì PL/SQL lặp qua từng khách hàng rồi chạy SELECT/UPDATE/INSERT riêng.

### 5.3. Dùng CASE để biểu diễn quy tắc theo hàng

```sql
UPDATE employees
SET salary =
    CASE
        WHEN salary < 5000 THEN salary * 1.10
        WHEN salary < 10000 THEN salary * 1.07
        ELSE salary * 1.03
    END
WHERE department_id = 50;
```

Các nhánh khác nhau theo từng hàng vẫn có thể được biểu diễn trong một câu SQL bằng `CASE`, tránh loop PL/SQL.

### 5.4. Dùng analytic function thay cho tính toán tuần tự

Ví dụ xếp hạng nhân viên theo lương trong phòng ban:

```sql
SELECT employee_id,
       department_id,
       salary,
       DENSE_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank
FROM employees;
```

Nếu bài toán là xếp hạng, tổng lũy kế, trung bình trượt hoặc so sánh hàng trước/sau, analytic functions thường biểu diễn tốt hơn việc fetch từng hàng về PL/SQL và tự tính.

## 6. SQL gọi PL/SQL function theo từng hàng

Một nguồn context switch khác là gọi stored function trong SELECT, WHERE, ORDER BY hoặc biểu thức SQL.

### 6.1. Ví dụ function được gọi trong SELECT

```sql
CREATE OR REPLACE FUNCTION normalize_email (
    p_email IN VARCHAR2
) RETURN VARCHAR2
AS
BEGIN
    RETURN LOWER(TRIM(p_email));
END normalize_email;
/

SELECT customer_id,
       normalize_email(email) AS normalized_email
FROM customers;
```

Function đơn giản chỉ gọi `LOWER` và `TRIM`, vốn đã là hàm SQL. Đưa thao tác này vào PL/SQL function có thể tạo thêm chuyển ngữ cảnh mà không mang lại lợi ích đáng kể.

Nên viết trực tiếp:

```sql
SELECT customer_id,
       LOWER(TRIM(email)) AS normalized_email
FROM customers;
```

### 6.2. Function trong WHERE

```sql
SELECT order_id
FROM orders
WHERE calculate_customer_score(customer_id) >= 80;
```

Nếu function được đánh giá cho nhiều hàng, SQL engine có thể phải gọi PL/SQL engine lặp lại. Ngoài context switch, function có thể truy vấn thêm bảng, làm phát sinh SQL bên trong SQL và gây chi phí N+1.

Hãy xem có thể thay function bằng JOIN, subquery, CASE, analytic function hoặc biểu thức SQL thuần không.

### 6.3. N+1 query bên trong function

Ví dụ function tra cứu mức khách hàng:

```sql
CREATE OR REPLACE FUNCTION get_customer_level (
    p_customer_id IN NUMBER
) RETURN VARCHAR2
AS
    v_level VARCHAR2(30);
BEGIN
    SELECT customer_level
    INTO v_level
    FROM customers
    WHERE customer_id = p_customer_id;

    RETURN v_level;
END get_customer_level;
/
```

Truy vấn:

```sql
SELECT order_id,
       get_customer_level(customer_id)
FROM orders;
```

Nếu có 50.000 đơn hàng, function có thể được gọi rất nhiều lần; mỗi lần lại thực hiện một SELECT. Đây là dạng N+1: một query lấy danh sách, sau đó nhiều query nhỏ để lấy dữ liệu liên quan.

Có thể viết lại bằng JOIN:

```sql
SELECT o.order_id,
       c.customer_level
FROM orders o
JOIN customers c
  ON c.customer_id = o.customer_id;
```

JOIN giúp optimizer nhìn thấy quan hệ dữ liệu và chọn access path phù hợp cho toàn query.

### 6.4. Không giả định số lần function được gọi

Số lần thực thi function không nhất thiết bằng số hàng cuối cùng được trả về. Optimizer có thể:

- Đánh giá predicate trước hoặc sau các phép biến đổi.
- Tính lại biểu thức trong các nhánh của plan.
- Loại bỏ một số lần đánh giá nhờ biến đổi query.
- Thay đổi số lần gọi theo bind values, statistics và phiên bản.

Vì vậy, không viết function có side effect hoặc phụ thuộc vào số lần gọi khi function được dùng trong SQL.

## 7. Tránh PL/SQL function nếu biểu thức SQL đã đủ

Nếu logic chỉ gồm toán tử và hàm SQL, hãy viết trực tiếp trong SQL:

| Logic | Ưu tiên SQL |
|---|---|
| Chuẩn hóa chuỗi | `TRIM`, `LOWER`, `UPPER`, `REPLACE` |
| Kiểm tra điều kiện | `CASE`, `COALESCE`, `NVL`, `NULLIF` |
| Tính toán số học | Toán tử `+`, `-`, `*`, `/` |
| Gộp dữ liệu | `SUM`, `COUNT`, `MIN`, `MAX`, `AVG` |
| Lấy hàng ưu tiên | `ROW_NUMBER`, `RANK`, `FETCH FIRST` |
| Tra cứu dữ liệu liên quan | JOIN, scalar subquery hoặc EXISTS |
| Tính toán theo nhóm | GROUP BY và analytic functions |

Ví dụ function:

```sql
CREATE OR REPLACE FUNCTION line_total (
    p_quantity IN NUMBER,
    p_unit_price IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_quantity * p_unit_price;
END line_total;
/
```

SQL có thể tính trực tiếp:

```sql
SELECT order_line_id,
       quantity * unit_price AS line_total
FROM order_lines;
```

Nếu công thức chỉ là phép nhân, gọi PL/SQL function không cần thiết.

## 8. PRAGMA UDF cho function được gọi từ SQL

Trong một số trường hợp, function PL/SQL thực sự cần được tái sử dụng và được gọi từ SQL. Oracle cung cấp `PRAGMA UDF` để báo cho compiler biết function được dùng chủ yếu từ SQL và có thể tối ưu overhead của lời gọi.

### 8.1. Cú pháp

```sql
CREATE OR REPLACE FUNCTION normalize_customer_code (
    p_code IN VARCHAR2
) RETURN VARCHAR2
AS
    PRAGMA UDF;
BEGIN
    RETURN UPPER(TRIM(p_code));
END normalize_customer_code;
/
```

`PRAGMA UDF` nằm trong phần khai báo của function, trước `BEGIN`.

### 8.2. PRAGMA UDF có tác dụng gì?

`PRAGMA UDF` gợi ý compiler tối ưu function cho ngữ cảnh được gọi từ SQL. Trong một số workload, nó có thể giảm overhead khi SQL engine gọi PL/SQL function.

Nhưng cần hiểu giới hạn:

- Không biến function PL/SQL thành biểu thức SQL.
- Không bảo đảm loại bỏ hoàn toàn context switch.
- Không thay thế việc viết lại query set-based.
- Không làm cho function có side effect trở nên an toàn khi gọi từ SQL.
- Lợi ích phụ thuộc workload, phiên bản, kiểu tham số và cách optimizer thực thi.

### 8.3. Khi nào cân nhắc?

`PRAGMA UDF` phù hợp khi:

- Function được gọi từ SQL thường xuyên.
- Logic không dễ biểu diễn bằng SQL thuần.
- Function không gây side effect không phù hợp.
- Đã đo và xác nhận overhead function call là đáng kể.
- Phiên bản Oracle hỗ trợ pragma này.

`PRAGMA UDF` có từ Oracle Database 12c Release 1. Với hệ thống hỗ trợ nhiều phiên bản, cần xác nhận phiên bản thấp nhất trước khi triển khai.

## 9. DETERMINISTIC và RESULT_CACHE không giống PRAGMA UDF

Ba khái niệm thường bị nhầm:

| Cơ chế | Mục đích |
|---|---|
| `PRAGMA UDF` | Giúp tối ưu overhead của function được gọi từ SQL |
| `DETERMINISTIC` | Khai báo rằng cùng đầu vào thì function luôn cho cùng kết quả, theo cam kết của lập trình viên |
| `RESULT_CACHE` | Cho phép Oracle cache kết quả function theo tham số và quản lý dependency dữ liệu phù hợp |

### 9.1. DETERMINISTIC

```sql
CREATE OR REPLACE FUNCTION normalize_code (
    p_code IN VARCHAR2
) RETURN VARCHAR2
DETERMINISTIC
AS
BEGIN
    RETURN UPPER(TRIM(p_code));
END normalize_code;
/
```

`DETERMINISTIC` là cam kết của người viết function. Oracle không tự kiểm chứng rằng function thực sự deterministic. Không khai báo nếu kết quả phụ thuộc vào:

- Thời gian hiện tại.
- Sequence hoặc trạng thái session.
- Package global variables.
- NLS settings không được đưa vào tham số.
- Dữ liệu thay đổi mà function đọc nhưng không được phản ánh đúng trong hợp đồng.

Không coi DETERMINISTIC là một cache tổng quát hoặc cam kết function chỉ chạy một lần.

### 9.2. RESULT_CACHE

```sql
CREATE OR REPLACE FUNCTION get_tax_rate (
    p_region_code IN VARCHAR2
) RETURN NUMBER
RESULT_CACHE
AS
    v_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO v_rate
    FROM tax_regions
    WHERE region_code = p_region_code;

    RETURN v_rate;
END get_tax_rate;
/
```

`RESULT_CACHE` cho phép Oracle lưu kết quả function trong result cache và quản lý tính hợp lệ theo dependency dữ liệu mà Oracle theo dõi. Nó có thể giảm việc tính toán/truy vấn lặp lại khi đầu vào giống nhau và cache còn hợp lệ.

Tuy vậy, function vẫn có lời gọi từ SQL sang PL/SQL. Result cache có thể giảm công việc bên trong function, nhưng không nên mặc định rằng nó xóa hoàn toàn chi phí chuyển ngữ cảnh.

Chỉ dùng result cache khi function có hành vi phù hợp, kết quả không phụ thuộc trạng thái session không được quản lý và việc cache đem lại lợi ích đo được.

## 10. BULK COLLECT: lấy nhiều hàng trong một lần chuyển dữ liệu

Khi thực sự cần xử lý từng hàng trong PL/SQL, `BULK COLLECT` giúp lấy nhiều hàng từ SQL engine vào collection trong một lần fetch/batch, thay vì chuyển từng hàng một.

### 10.1. SELECT BULK COLLECT INTO

```sql
DECLARE
    TYPE employee_id_tab_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_tab_t IS TABLE OF employees.salary%TYPE;

    v_employee_ids employee_id_tab_t;
    v_salaries salary_tab_t;
BEGIN
    SELECT employee_id, salary
    BULK COLLECT INTO v_employee_ids, v_salaries
    FROM employees
    WHERE department_id = 50;

    DBMS_OUTPUT.PUT_LINE(
        'Fetched=' || v_employee_ids.COUNT
    );

    FOR i IN 1 .. v_employee_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(
            v_employee_ids(i) || ': ' || v_salaries(i)
        );
    END LOOP;
END;
/
```

Các collection nhận các cột theo cùng vị trí. Nếu truy vấn không trả hàng, collection rỗng; `BULK COLLECT` không phát sinh `NO_DATA_FOUND` chỉ vì không có hàng.

### 10.2. Vì sao BULK COLLECT giảm overhead?

Với fetch từng hàng, PL/SQL cần nhận nhiều kết quả nhỏ. Với bulk fetch, SQL engine trả một nhóm hàng vào collection. Việc chuyển dữ liệu được gom theo batch nên giảm số lần điều phối qua lại.

Bulk fetch không làm biến mất mọi chi phí:

- SQL vẫn phải đọc và xử lý dữ liệu.
- Collection cần bộ nhớ trong PGA.
- PL/SQL vẫn phải lặp qua các phần tử nếu logic yêu cầu xử lý từng hàng.
- Batch quá lớn có thể làm tăng bộ nhớ và ảnh hưởng các session khác.

### 10.3. Giới hạn bộ nhớ bằng LIMIT

Với tập dữ liệu lớn, không nên luôn lấy toàn bộ kết quả vào collection. Dùng explicit cursor và `FETCH BULK COLLECT ... LIMIT`:

```sql
DECLARE
    CURSOR c_employees IS
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 50
        ORDER BY employee_id;

    TYPE employee_id_tab_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_tab_t IS TABLE OF employees.salary%TYPE;

    v_employee_ids employee_id_tab_t;
    v_salaries salary_tab_t;
    c_batch_size CONSTANT PLS_INTEGER := 500;
BEGIN
    OPEN c_employees;

    LOOP
        FETCH c_employees
        BULK COLLECT INTO v_employee_ids, v_salaries
        LIMIT c_batch_size;

        EXIT WHEN v_employee_ids.COUNT = 0;

        FOR i IN 1 .. v_employee_ids.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                v_employee_ids(i) || ': ' || v_salaries(i)
            );
        END LOOP;
    END LOOP;

    CLOSE c_employees;
EXCEPTION
    WHEN OTHERS THEN
        IF c_employees%ISOPEN THEN
            CLOSE c_employees;
        END IF;
        RAISE;
END;
/
```

Mỗi lần fetch lấy tối đa 500 hàng. Batch cuối có thể ít hơn 500; khi fetch tiếp và collection rỗng, vòng lặp dừng.

### 10.4. Chọn batch size

Không có một batch size tối ưu cho mọi hệ thống. Giá trị phụ thuộc:

- Số cột và kích thước mỗi hàng.
- Tổng số hàng.
- PGA memory.
- Số session chạy đồng thời.
- Chi phí xử lý PL/SQL trên mỗi hàng.
- Khả năng và giới hạn của driver/ứng dụng nếu dữ liệu được truyền tiếp.

Hãy thử một số mức như 100, 500, 1.000 hoặc 5.000 trong môi trường đại diện rồi đo elapsed time và memory. Không chọn batch lớn chỉ vì muốn giảm số lần fetch.

## 11. FORALL: gửi DML theo mảng thay vì từng hàng

`FORALL` là câu lệnh PL/SQL dành cho bulk binding. Nó cho phép gửi một DML statement với các giá trị bind lấy từ collection qua nhiều iteration, giúp giảm chuyển ngữ cảnh so với chạy một DML riêng trong từng vòng lặp.

### 11.1. Row-by-row UPDATE

```sql
DECLARE
    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    v_ids id_tab_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM employees
    WHERE department_id = 50;

    FOR i IN 1 .. v_ids.COUNT LOOP
        UPDATE employees
        SET salary = salary * 1.05
        WHERE employee_id = v_ids(i);
    END LOOP;
END;
/
```

DML được thực hiện từng iteration từ PL/SQL. Nếu chỉ cần tăng lương tất cả nhân viên thuộc phòng ban 50, một câu UPDATE set-based vẫn tốt hơn.

### 11.2. Dùng FORALL

```sql
DECLARE
    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    v_ids id_tab_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM employees
    WHERE department_id = 50;

    IF v_ids.COUNT > 0 THEN
        FORALL i IN 1 .. v_ids.COUNT
            UPDATE employees
            SET salary = salary * 1.05
            WHERE employee_id = v_ids(i);
    END IF;

    DBMS_OUTPUT.PUT_LINE(
        'Rows affected=' || SQL%ROWCOUNT
    );
END;
/
```

`FORALL` gom các giá trị bind từ collection để thực hiện DML theo cơ chế bulk. Nó giảm overhead PL/SQL-to-SQL so với vòng lặp DML từng hàng.

### 11.3. FORALL không phải FOR loop thông thường

| FOR loop | FORALL |
|---|---|
| Thực thi các statement PL/SQL theo từng iteration | Bulk bind một DML statement với nhiều giá trị collection |
| Có thể chứa nhiều loại lệnh PL/SQL | Chỉ áp dụng cho một DML statement trong thân FORALL |
| Dễ dùng cho logic thủ tục tùy ý | Dùng khi cần DML hàng loạt theo collection |
| Thường có nhiều lần gọi SQL nếu DML từng hàng | Giảm số lần chuyển giữa PL/SQL và SQL |

Không đặt `IF`, `DBMS_OUTPUT` hoặc nhiều câu SQL tùy ý bên trong thân FORALL. Hãy chuẩn bị collection trước rồi thực hiện một DML phù hợp.

### 11.4. Các dạng chỉ số collection

FORALL có thể lặp theo:

- `1 .. collection.COUNT` khi collection dense và chỉ số liên tiếp.
- `INDICES OF collection` khi collection có chỉ số thưa.
- `VALUES OF index_collection` khi một collection chứa danh sách chỉ số cần xử lý.

Ví dụ:

```sql
FORALL i IN INDICES OF v_ids
    UPDATE employees
    SET salary = salary * 1.05
    WHERE employee_id = v_ids(i);
```

Với collection sparse, không giả định chỉ số luôn là `1 .. COUNT`. Dùng `INDICES OF` khi cần lặp qua các index thực sự tồn tại.

## 12. Kết hợp BULK COLLECT và FORALL

Đây là mẫu phổ biến khi nghiệp vụ cần đọc một tập hàng, xử lý trong PL/SQL rồi cập nhật lại nhiều hàng.

### 12.1. Ví dụ đọc và cập nhật theo batch

```sql
DECLARE
    CURSOR c_changes IS
        SELECT employee_id, new_salary
        FROM employee_salary_stage
        WHERE batch_id = 1001
        ORDER BY employee_id;

    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_tab_t IS TABLE OF employees.salary%TYPE;

    v_ids id_tab_t;
    v_new_salaries salary_tab_t;
    c_limit CONSTANT PLS_INTEGER := 500;
BEGIN
    OPEN c_changes;

    LOOP
        FETCH c_changes
        BULK COLLECT INTO v_ids, v_new_salaries
        LIMIT c_limit;

        EXIT WHEN v_ids.COUNT = 0;

        FORALL i IN 1 .. v_ids.COUNT
            UPDATE employees
            SET salary = v_new_salaries(i)
            WHERE employee_id = v_ids(i);
    END LOOP;

    CLOSE c_changes;
EXCEPTION
    WHEN OTHERS THEN
        IF c_changes%ISOPEN THEN
            CLOSE c_changes;
        END IF;
        RAISE;
END;
/
```

Ví dụ giả định có bảng staging `EMPLOYEE_SALARY_STAGE` với `BATCH_ID`, `EMPLOYEE_ID`, `NEW_SALARY`. Cursor lấy dữ liệu theo batch; mỗi lượt bulk fetch tối đa 500 hàng; FORALL thực hiện UPDATE bằng các collection tương ứng.

### 12.2. Vì sao dùng LIMIT?

Nếu bảng staging có hàng triệu bản ghi, lấy toàn bộ vào collection có thể tiêu thụ PGA lớn. LIMIT giữ bộ nhớ ở mức dễ dự đoán và cho phép xử lý từng batch.

### 12.3. Không COMMIT tùy tiện sau mỗi batch

LIMIT điều khiển kích thước collection, không tự quyết định transaction boundary. Nếu COMMIT sau mỗi batch:

- Toàn bộ quy trình không còn atomic.
- Lỗi ở batch sau không rollback được batch đã commit.
- Caller có thể nhìn thấy trạng thái dữ liệu mới chỉ được cập nhật một phần.
- Cursor đang mở qua COMMIT có thể gặp vấn đề như `ORA-01555` trong một số workload hoặc lỗi liên quan fetch/transaction tùy cách thực hiện.

Chọn transaction boundary theo yêu cầu nghiệp vụ. Nếu cần xử lý nhiều batch mà vẫn atomic, giữ transaction phù hợp và quản lý undo/redo; nếu cho phép xử lý từng batch độc lập, lưu trạng thái tiến độ và thiết kế recovery rõ ràng.

## 13. Xử lý lỗi trong FORALL với SAVE EXCEPTIONS

Khi một phần tử gây lỗi, ứng dụng cần quyết định có dừng ngay hay tiếp tục xử lý các phần tử còn lại.

### 13.1. SAVE EXCEPTIONS

`SAVE EXCEPTIONS` yêu cầu Oracle tiếp tục các iteration còn lại của FORALL, ghi nhận lỗi của từng iteration. Sau khi hoàn tất, Oracle phát sinh exception `ORA-24381` để báo rằng có ít nhất một iteration lỗi.

Ví dụ:

```sql
DECLARE
    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    v_ids id_tab_t;

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM employees
    WHERE department_id = 50;

    IF v_ids.COUNT > 0 THEN
        FORALL i IN 1 .. v_ids.COUNT SAVE EXCEPTIONS
            UPDATE employees
            SET salary = salary * 1.05
            WHERE employee_id = v_ids(i);
    END IF;
EXCEPTION
    WHEN e_bulk_errors THEN
        FOR i IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Iteration=' ||
                SQL%BULK_EXCEPTIONS(i).ERROR_INDEX ||
                ', Oracle code=' ||
                SQL%BULK_EXCEPTIONS(i).ERROR_CODE
            );
        END LOOP;
        RAISE;
END;
/
```

### 13.2. SQL%BULK_EXCEPTIONS

Trong handler của lỗi bulk:

- `SQL%BULK_EXCEPTIONS.COUNT`: số iteration bị lỗi.
- `SQL%BULK_EXCEPTIONS(i).ERROR_INDEX`: chỉ số iteration gây lỗi.
- `SQL%BULK_EXCEPTIONS(i).ERROR_CODE`: mã lỗi Oracle, thường được trả dưới dạng số dương trong thuộc tính này.

Có thể dùng `SQLERRM(-SQL%BULK_EXCEPTIONS(i).ERROR_CODE)` để lấy message tương ứng:

```sql
DBMS_OUTPUT.PUT_LINE(
    SQLERRM(-SQL%BULK_EXCEPTIONS(i).ERROR_CODE)
);
```

Nếu dùng `INDICES OF` hoặc `VALUES OF`, cần hiểu quan hệ giữa ERROR_INDEX và chỉ số collection/iteration; không mặc định đó luôn là khóa nghiệp vụ.

### 13.3. SQL%BULK_ROWCOUNT

`SQL%BULK_ROWCOUNT(i)` cho biết số hàng bị tác động bởi iteration thứ i của FORALL:

```sql
FOR i IN 1 .. v_ids.COUNT LOOP
    DBMS_OUTPUT.PUT_LINE(
        'Iteration ' || i ||
        ' affected ' || SQL%BULK_ROWCOUNT(i) || ' rows'
    );
END LOOP;
```

Đây là thông tin hữu ích khi một ID không tồn tại hoặc DML có thể tác động 0, 1 hay nhiều hàng.

### 13.4. SAVE EXCEPTIONS không tự quyết định COMMIT

Sau khi FORALL có một số iteration thành công và một số iteration lỗi, transaction vẫn cần được caller quyết định COMMIT hoặc ROLLBACK theo chính sách nghiệp vụ. Không mặc định rằng việc bắt `ORA-24381` đồng nghĩa mọi thay đổi thành công đã tự rollback.

Nếu handler ghi log rồi `RAISE;`, caller vẫn nhận lỗi bulk. Nếu handler xử lý và không re-raise, caller phải có một hợp đồng rõ ràng về những hàng thành công/thất bại và cách tiếp tục.

## 14. Cursor FOR loop và tối ưu fetch tự động

Cú pháp cursor FOR loop:

```sql
BEGIN
    FOR r IN (
        SELECT employee_id, last_name
        FROM employees
        WHERE department_id = 50
    ) LOOP
        DBMS_OUTPUT.PUT_LINE(r.employee_id || ' ' || r.last_name);
    END LOOP;
END;
/
```

Oracle có các tối ưu runtime cho cursor FOR loop, bao gồm array fetching trong các phiên bản hiện đại. Vì vậy, không nên tự viết explicit cursor chỉ để thay thế cú pháp FOR loop nếu chưa có lý do đo được.

Nhưng tối ưu fetch tự động không biến DML từng hàng trong loop thành một câu DML set-based. Nếu mỗi vòng lặp vẫn chạy UPDATE/INSERT riêng, phần DML vẫn có thể tạo nhiều context switch.

Hãy phân biệt:

- Cursor FOR loop tự động hóa việc fetch và quản lý cursor.
- `BULK COLLECT` cho phép chủ động gom nhiều hàng vào collection.
- `FORALL` gom bind values cho DML hàng loạt.
- Set-based SQL thường là lựa chọn đầu tiên nếu có thể diễn đạt toàn bộ nghiệp vụ trong một statement.

## 15. Context switch và function trong trigger

Trigger có thể gọi procedure/function PL/SQL hoặc chạy SQL. Nếu trigger row-level được kích hoạt cho hàng nghìn hàng, phần logic PL/SQL và các SQL statement bên trong trigger có thể lặp lại nhiều lần.

Ví dụ:

```sql
CREATE OR REPLACE TRIGGER trg_order_audit
AFTER UPDATE OF status
ON orders
FOR EACH ROW
BEGIN
    INSERT INTO order_status_audit (
        order_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        :OLD.order_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END trg_order_audit;
/
```

Nếu một câu UPDATE tác động 100.000 hàng, row-level trigger chạy cho từng hàng và tạo các thao tác audit tương ứng. Đây có thể là yêu cầu nghiệp vụ, nhưng cần tính chi phí của trigger vào tổng thời gian DML.

Nếu có thể thiết kế audit bằng cơ chế khác hoặc xử lý theo statement/batch mà vẫn giữ đúng yêu cầu, hãy đánh giá. Không bỏ trigger chỉ vì muốn nhanh nếu nó đang bảo vệ tính toàn vẹn hoặc audit bắt buộc.

## 16. Các tối ưu khác liên quan đến context switch

### 16.1. Giảm số lần gọi function trong SQL

Nếu cùng một biểu thức function được lặp ở nhiều nơi trong query, hãy xem có thể tính một lần trong inline view hoặc CTE không. Tuy nhiên, optimizer có thể merge hoặc biến đổi query block; không coi CTE mặc định là materialized.

Ví dụ:

```sql
WITH normalized AS (
    SELECT customer_id,
           LOWER(TRIM(email)) AS normalized_email
    FROM customers
)
SELECT customer_id, normalized_email
FROM normalized
WHERE normalized_email = LOWER(TRIM(:email));
```

Ở đây phép chuẩn hóa dùng SQL built-ins, không gọi PL/SQL function.

### 16.2. Dùng scalar subquery caching một cách thận trọng

Oracle có thể áp dụng các tối ưu như scalar subquery caching trong một số truy vấn, giúp tránh tính lại một số kết quả lặp. Nhưng hành vi phụ thuộc phiên bản, query shape và execution plan. Không dựa vào caching như bảo đảm ngữ nghĩa hoặc thay thế thiết kế set-based.

### 16.3. Function result cache

`RESULT_CACHE` có thể giúp function đọc dữ liệu tham chiếu ít thay đổi và được gọi lặp lại với cùng tham số. Nó giảm công việc tính toán/đọc dữ liệu khi cache hit, nhưng vẫn cần đo context switch và chi phí lookup cache.

### 16.4. Native compilation không phải giải pháp cho mọi context switch

PL/SQL native compilation có thể cải thiện tốc độ thực thi một số phần PL/SQL tính toán nặng, nhưng không loại bỏ bản chất chuyển quyền điều khiển giữa SQL engine và PL/SQL engine. Nếu nút thắt là hàng triệu SQL calls từ loop, cần giảm số lần gọi hoặc bulk processing trước khi nghĩ đến native compilation.

## 17. Đo lường context switch và hiệu năng

Không tối ưu chỉ dựa vào cảm giác hoặc số dòng code. Hãy đo cùng dữ liệu, cùng bind values và cùng môi trường.

### 17.1. Đo thời gian và số hàng

Ghi lại:

- Elapsed time.
- CPU time.
- Số hàng đọc và số hàng cập nhật.
- Logical reads/buffer gets.
- Physical reads nếu có.
- Redo/undo phát sinh.
- PGA memory khi dùng collection.
- Số lần thực thi SQL.

### 17.2. Xem session statistics

Nếu có quyền đọc dynamic performance views, có thể xem thống kê context switch của session:

```sql
SELECT n.name,
       s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE s.sid = TO_NUMBER(
    SYS_CONTEXT('USERENV', 'SID')
)
AND LOWER(n.name) LIKE '%context switch%'
ORDER BY n.name;
```

Tên thống kê có thể khác theo phiên bản hoặc môi trường. Có thể xem thêm các thống kê có từ khóa `PL/SQL` và `SQL`. Giá trị trong `V$SESSTAT` thường là số tích lũy của session; hãy chụp trước và sau đoạn thử nghiệm rồi lấy delta, không so sánh hai session đã chạy workload khác nhau.

Quyền truy cập `V$` views phụ thuộc tài khoản và chính sách database. Trong môi trường không có quyền, DBA có thể hỗ trợ lấy số liệu.

### 17.3. SQL Trace và TKPROF

SQL Trace ghi nhận các lần parse/execute/fetch, thời gian CPU/elapsed, logical/physical reads và thông tin wait. Có thể bật trace cho session thử nghiệm:

```sql
ALTER SESSION SET SQL_TRACE = TRUE;

-- Chạy đúng đoạn PL/SQL cần đo.

ALTER SESSION SET SQL_TRACE = FALSE;
```

Sau đó dùng TKPROF trên trace file để tổng hợp. Trace có thể ghi thông tin SQL và bind tùy cấu hình; chỉ bật trong môi trường và phạm vi phù hợp, tránh thu thập dữ liệu nhạy cảm ngoài ý muốn.

### 17.4. DBMS_HPROF

`DBMS_HPROF` là hierarchical profiler cho PL/SQL, giúp phân tích thời gian và quan hệ gọi giữa các subprogram. Nó hữu ích để tìm function/procedure nào chiếm nhiều thời gian hoặc được gọi nhiều lần.

Ví dụ khái niệm:

```sql
BEGIN
    DBMS_HPROF.START_PROFILING(
        location => 'PLSQL_PROF_DIR',
        filename => 'context_switch_test.trc'
    );

    -- Gọi chương trình cần đo ở đây.

    DBMS_HPROF.STOP_PROFILING;
END;
/
```

Directory object, quyền ghi file và các bước phân tích trace cần được cấu hình bởi DBA hoặc người quản trị môi trường. Không chạy profiling trên production diện rộng nếu chưa đánh giá overhead.

### 17.5. DBMS_XPLAN

Đối với phần SQL, bật thống kê runtime trong session thử nghiệm:

```sql
ALTER SESSION SET statistics_level = ALL;
```

Chạy truy vấn:

```sql
SELECT department_id,
       COUNT(*)
FROM employees
GROUP BY department_id;
```

Sau khi chạy trong cùng session:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

`DBMS_XPLAN` giúp xem plan của SQL statement, số hàng thực tế và buffer gets theo operation. Nó không tự thay thế PL/SQL profiler khi cần biết function nào được gọi nhiều hoặc thời gian nằm trong PL/SQL.

## 18. Thiết kế benchmark có ý nghĩa

Khi so sánh row-by-row, set-based và bulk:

1. Dùng cùng tập dữ liệu và cùng điều kiện lọc.
2. Chạy nhiều lần để giảm ảnh hưởng parse, cache và biến động hệ thống.
3. Ghi nhận số hàng thực tế được xử lý.
4. Đo elapsed time và CPU, không chỉ thời gian nhìn thấy ở client.
5. So sánh buffer gets, physical reads và redo.
6. Đo cả DML throughput, không chỉ thời gian fetch.
7. Kiểm tra transaction và kết quả dữ liệu sau mỗi cách.
8. Thử nhiều batch sizes khi dùng BULK COLLECT/FORALL.
9. Chạy với mức đồng thời gần workload thật.
10. Không dùng kết quả từ bảng rất nhỏ để kết luận cho hàng triệu hàng.

### 18.1. Bảng ghi kết quả

| Phương án | Elapsed | CPU | Buffer gets | SQL calls | PGA | Rows |
|---|---:|---:|---:|---:|---:|---:|
| Row-by-row | Đo | Đo | Đo | Đo | Đo | Đo |
| Set-based SQL | Đo | Đo | Đo | Đo | Đo | Đo |
| BULK COLLECT + FORALL | Đo | Đo | Đo | Đo | Đo | Đo |

Không có con số chuẩn chung cho mọi database. Chọn phương án dựa trên kết quả đo của workload thực tế và yêu cầu transaction.

## 19. Quy trình tối ưu một đoạn PL/SQL

Khi một procedure chạy chậm, có thể làm theo thứ tự:

1. **Xác định vùng chậm:** dùng profiler hoặc trace để biết thời gian nằm ở SQL hay PL/SQL.
2. **Tìm SQL lặp lại:** kiểm tra số lần execute và câu SQL được gọi trong loop/function.
3. **Xem có thể viết set-based:** thay loop DML bằng UPDATE/MERGE/INSERT SELECT hoặc analytic SQL.
4. **Giảm function call trong query:** dùng built-in SQL, JOIN hoặc biểu thức SQL nếu có thể.
5. **Dùng PRAGMA UDF khi phù hợp:** chỉ sau khi function cần thiết và đã đo.
6. **Bulk fetch:** dùng BULK COLLECT nếu cần đọc nhiều hàng về PL/SQL.
7. **Bulk DML:** dùng FORALL nếu cần cập nhật/insert/delete theo collection.
8. **Giới hạn bộ nhớ:** dùng LIMIT cho tập lớn.
9. **Xử lý lỗi theo batch:** cân nhắc SAVE EXCEPTIONS và chính sách commit.
10. **Đo lại:** xác nhận tốc độ cải thiện mà kết quả nghiệp vụ không đổi.

### 19.1. Câu hỏi quyết định

- Có thể thực hiện toàn bộ thay đổi bằng một SQL statement không?
- Function PL/SQL có đang được gọi cho từng hàng trong query không?
- Function có đang chạy SELECT bên trong mỗi lần gọi không?
- Nếu phải xử lý trong PL/SQL, có thể lấy theo batch không?
- DML có thể dùng FORALL không?
- Batch size có gây áp lực PGA không?
- Cần atomic toàn bộ hay chấp nhận commit theo batch?
- Có cần ghi nhận từng lỗi hay dừng ở lỗi đầu tiên?

## 20. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| Một context switch luôn rất đắt | Một lần thường nhỏ; số lần lớn mới có thể tạo overhead đáng kể |
| Mọi vòng lặp PL/SQL đều chậm | Loop chỉ đáng lo khi có SQL call lặp hoặc xử lý lớn; logic thuần PL/SQL có thể phù hợp |
| Cursor FOR loop loại bỏ mọi context switch | Nó đơn giản hóa fetch và có tối ưu array fetch; DML từng hàng bên trong vẫn có chi phí |
| BULK COLLECT luôn nhanh hơn SQL set-based | Set-based thường tốt hơn nếu nghiệp vụ có thể viết bằng SQL |
| FORALL là một UPDATE tác động cả bảng như set-based | FORALL bulk-bind một DML theo collection; nó không thay thế mọi câu UPDATE set-based |
| LIMIT tự chia transaction | LIMIT chỉ giới hạn batch fetch; không tự COMMIT |
| FORALL không có lỗi | SAVE EXCEPTIONS giúp tiếp tục và thu thập lỗi; caller vẫn cần xử lý |
| PRAGMA UDF xóa context switch | Nó có thể giảm overhead, không bảo đảm loại bỏ chuyển engine |
| DETERMINISTIC tự cache kết quả | Đây là cam kết tính xác định, không phải cơ chế cache tổng quát |
| RESULT_CACHE làm function không còn overhead | Cache giảm công việc tính toán khi hit; lời gọi function vẫn có chi phí |
| SQL gọi function đúng một lần mỗi hàng | Số lần đánh giá phụ thuộc plan và tối ưu của Oracle |
| Thêm COMMIT sau mỗi batch luôn tốt | Có thể phá tính atomic và làm recovery phức tạp |
| Trigger không ảnh hưởng hiệu năng DML | Row trigger có thể chạy cho từng hàng và làm tăng công việc |
| Native compilation sửa được N+1 SQL | Nó không loại bỏ hàng loạt SQL call hoặc context switch |

## 21. Bài thực hành tổng hợp

Các bài tập dưới đây dùng sample schema `EMPLOYEES` và có thể thay đổi dữ liệu. Chạy trong schema lab hoặc transaction thử nghiệm; ROLLBACK khi không muốn giữ thay đổi.

### Bước 1. Đo row-by-row UPDATE

```sql
BEGIN
    FOR r IN (
        SELECT employee_id
        FROM employees
        WHERE department_id = 50
    ) LOOP
        UPDATE employees
        SET salary = salary * 1.01
        WHERE employee_id = r.employee_id;
    END LOOP;
END;
/

ROLLBACK;
```

Ghi thời gian, số lần SQL execute và buffer gets.

### Bước 2. Đo set-based UPDATE

```sql
UPDATE employees
SET salary = salary * 1.01
WHERE department_id = 50;

ROLLBACK;
```

So sánh với bước 1 trên cùng dữ liệu và cùng trạng thái ban đầu.

### Bước 3. Thử BULK COLLECT và FORALL

```sql
DECLARE
    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    v_ids id_tab_t;
BEGIN
    SELECT employee_id
    BULK COLLECT INTO v_ids
    FROM employees
    WHERE department_id = 50;

    IF v_ids.COUNT > 0 THEN
        FORALL i IN 1 .. v_ids.COUNT
            UPDATE employees
            SET salary = salary * 1.01
            WHERE employee_id = v_ids(i);
    END IF;
END;
/

ROLLBACK;
```

Đo và so sánh với set-based UPDATE. Bulk có thể nhanh hơn row-by-row nhưng không nhất thiết nhanh hơn một UPDATE set-based đơn giản.

### Bước 4. Tạo function gọi từ SQL

```sql
CREATE OR REPLACE FUNCTION lab_salary_band (
    p_salary IN NUMBER
) RETURN VARCHAR2
AS
BEGIN
    IF p_salary < 5000 THEN
        RETURN 'LOW';
    ELSIF p_salary < 10000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'HIGH';
    END IF;
END lab_salary_band;
/
```

### Bước 5. Dùng function trong SELECT

```sql
SELECT employee_id,
       lab_salary_band(salary) AS salary_band
FROM employees;
```

Quan sát thời gian và số lần gọi bằng profiler/trace nếu môi trường cho phép.

### Bước 6. Viết lại bằng CASE

```sql
SELECT employee_id,
       CASE
           WHEN salary < 5000 THEN 'LOW'
           WHEN salary < 10000 THEN 'MEDIUM'
           ELSE 'HIGH'
       END AS salary_band
FROM employees;
```

So sánh kết quả và thời gian với function. Logic trong ví dụ có thể biểu diễn trực tiếp bằng SQL nên CASE là phương án đơn giản hơn.

### Bước 7. Thử PRAGMA UDF

```sql
CREATE OR REPLACE FUNCTION lab_salary_band_udf (
    p_salary IN NUMBER
) RETURN VARCHAR2
AS
    PRAGMA UDF;
BEGIN
    IF p_salary < 5000 THEN
        RETURN 'LOW';
    ELSIF p_salary < 10000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'HIGH';
    END IF;
END lab_salary_band_udf;
/
```

Chạy truy vấn với function này, đo nhiều lần và so sánh với function không có pragma. Không kết luận từ một lần chạy.

### Bước 8. Thử bulk fetch theo batch

```sql
DECLARE
    CURSOR c_emp IS
        SELECT employee_id, salary
        FROM employees
        WHERE department_id = 50;

    TYPE id_tab_t IS TABLE OF employees.employee_id%TYPE;
    TYPE salary_tab_t IS TABLE OF employees.salary%TYPE;
    v_ids id_tab_t;
    v_salaries salary_tab_t;
BEGIN
    OPEN c_emp;
    LOOP
        FETCH c_emp BULK COLLECT
        INTO v_ids, v_salaries
        LIMIT 200;

        EXIT WHEN v_ids.COUNT = 0;

        DBMS_OUTPUT.PUT_LINE('Fetched batch=' || v_ids.COUNT);
    END LOOP;
    CLOSE c_emp;
EXCEPTION
    WHEN OTHERS THEN
        IF c_emp%ISOPEN THEN
            CLOSE c_emp;
        END IF;
        RAISE;
END;
/
```

Thử các LIMIT khác nhau và ghi nhận thời gian/bộ nhớ.

### Bước 9. Xem session statistics

```sql
SELECT n.name, s.value
FROM v$sesstat s
JOIN v$statname n
  ON n.statistic# = s.statistic#
WHERE s.sid = TO_NUMBER(SYS_CONTEXT('USERENV', 'SID'))
  AND LOWER(n.name) LIKE '%context switch%'
ORDER BY n.name;
```

Chụp số liệu trước và sau từng đoạn thử nghiệm. Cần quyền đọc V$ views.

### Bước 10. Dọn function lab

Chỉ khi chắc chắn đây là các function do bạn tạo và không còn cần dùng:

```sql
DROP FUNCTION lab_salary_band;
DROP FUNCTION lab_salary_band_udf;
```

## 22. Quy tắc ghi nhớ

| Vấn đề | Cách xử lý |
|---|---|
| Nhiều UPDATE trong loop | Thử một UPDATE set-based |
| Nhiều INSERT từ một query | Dùng `INSERT INTO ... SELECT` |
| Đồng bộ nguồn/đích | Cân nhắc MERGE |
| Tính toán theo nhóm/hàng lân cận | GROUP BY hoặc analytic functions |
| Function PL/SQL trong SELECT | Thử thay bằng SQL built-ins, JOIN hoặc CASE |
| Function thật sự cần gọi từ SQL | Cân nhắc `PRAGMA UDF` sau khi đo |
| Hàm lặp lại cùng tham số | Đánh giá `RESULT_CACHE` nếu semantics phù hợp |
| Đọc nhiều hàng về PL/SQL | `BULK COLLECT` |
| Tập dữ liệu lớn | Cursor + `FETCH BULK COLLECT ... LIMIT n` |
| DML theo collection | `FORALL` |
| Một số iteration có thể lỗi | `SAVE EXCEPTIONS` và `SQL%BULK_EXCEPTIONS` |
| Kiểm tra số hàng từng DML trong FORALL | `SQL%BULK_ROWCOUNT(i)` |
| Đo context switch | Session statistics, SQL Trace, profiler |
| Xác nhận SQL plan | `DBMS_XPLAN.DISPLAY_CURSOR` |
| Xác nhận lợi ích | Benchmark cùng dữ liệu, bind và transaction |

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Context switch giữa SQL và PL/SQL là gì?

**Trả lời:** Sự chuyển quyền điều khiển giữa SQL engine và PL/SQL engine khi một engine gọi phần xử lý của engine còn lại.

**Câu 2.** Vì sao row-by-row DML có thể chậm?

**Trả lời:** Mỗi iteration có thể gọi một SQL statement riêng, tạo nhiều lần chuyển ngữ cảnh và overhead execute/bind.

**Câu 3.** Giải pháp đầu tiên khi có thể diễn đạt nghiệp vụ bằng SQL là gì?

**Trả lời:** Viết một câu SQL set-based như UPDATE, MERGE hoặc INSERT SELECT.

**Câu 4.** SQL gọi PL/SQL function có thể tạo overhead nào?

**Trả lời:** SQL engine phải chuyển sang PL/SQL engine để chạy function rồi nhận kết quả; nếu gọi lặp trên nhiều hàng, chi phí có thể tăng.

**Câu 5.** Có thể giả định function được gọi đúng một lần cho mỗi hàng không?

**Trả lời:** Không. Số lần đánh giá phụ thuộc query plan và các tối ưu của Oracle.

**Câu 6.** PRAGMA UDF có tác dụng gì?

**Trả lời:** Gợi ý compiler tối ưu function chủ yếu được gọi từ SQL, có thể giảm overhead nhưng không bảo đảm loại bỏ context switch.

**Câu 7.** DETERMINISTIC có phải result cache không?

**Trả lời:** Không. DETERMINISTIC là cam kết của lập trình viên về tính xác định của kết quả, không phải cơ chế cache tổng quát.

**Câu 8.** BULK COLLECT dùng để làm gì?

**Trả lời:** Fetch nhiều hàng từ SQL engine vào collection PL/SQL theo một batch.

**Câu 9.** Vì sao dùng LIMIT với BULK COLLECT?

**Trả lời:** Giới hạn số hàng mỗi batch để kiểm soát PGA memory và kích thước dữ liệu xử lý.

**Câu 10.** FORALL khác FOR loop thế nào?

**Trả lời:** FORALL bulk-bind một DML statement với các giá trị từ collection; FOR loop chạy các câu lệnh PL/SQL theo từng iteration.

**Câu 11.** Vì sao set-based SQL thường tốt hơn FORALL?

**Trả lời:** Set-based SQL cho phép SQL engine xử lý toàn bộ tập dữ liệu trong một statement; FORALL vẫn cần PL/SQL chuẩn bị collection và dùng khi logic cần bulk bind.

**Câu 12.** SAVE EXCEPTIONS có tác dụng gì?

**Trả lời:** Cho phép FORALL tiếp tục các iteration còn lại, lưu lỗi và phát sinh ORA-24381 sau khi hoàn tất.

**Câu 13.** SQL%BULK_EXCEPTIONS cung cấp gì?

**Trả lời:** Chỉ số iteration và mã lỗi của các lần DML thất bại trong FORALL có SAVE EXCEPTIONS.

**Câu 14.** LIMIT có tự COMMIT sau mỗi batch không?

**Trả lời:** Không. LIMIT chỉ điều khiển số hàng fetch mỗi lần; transaction boundary do chương trình/caller quản lý.

**Câu 15.** Cursor FOR loop có loại bỏ DML row-by-row không?

**Trả lời:** Không. Runtime có thể tối ưu fetch, nhưng DML riêng trong từng vòng lặp vẫn có overhead.

**Câu 16.** Dùng công cụ nào để xem PL/SQL subprogram chiếm thời gian?

**Trả lời:** Có thể dùng DBMS_HPROF hoặc profiler phù hợp; SQL Trace/TKPROF phân tích SQL calls và thời gian SQL.

**Câu 17.** Native compilation có loại bỏ context switch không?

**Trả lời:** Không. Nó có thể tăng tốc một số phần PL/SQL tính toán, nhưng không loại bỏ các SQL calls lặp lại.

## 24. Kết luận

Context switch là chi phí điều phối khi quyền thực thi chuyển giữa SQL engine và PL/SQL engine. Một lần chuyển thường nhỏ, nhưng các vòng lặp gọi SQL từng hàng hoặc function PL/SQL được gọi lặp lại trong query có thể tạo overhead lớn. Vì vậy, khi tối ưu PL/SQL, hãy tìm số lần gọi SQL/function và xác định liệu logic có thể được xử lý theo tập hay không.

Ưu tiên SQL set-based như UPDATE, MERGE, INSERT SELECT, JOIN, CASE, GROUP BY và analytic functions khi nghiệp vụ có thể biểu diễn trực tiếp. Nếu cần xử lý thủ tục theo từng hàng, `BULK COLLECT` gom dữ liệu khi fetch và `FORALL` gom bind values khi DML; dùng LIMIT để kiểm soát PGA và `SAVE EXCEPTIONS` khi cần thu thập lỗi theo iteration. Cursor FOR loop giúp code gọn và có tối ưu fetch, nhưng không tự biến DML từng hàng thành set-based.

Khi function PL/SQL thực sự cần được gọi từ SQL, có thể cân nhắc `PRAGMA UDF` hoặc `RESULT_CACHE` theo đúng semantics và sau khi đo. `DETERMINISTIC` không phải cache và không bảo đảm function chỉ chạy một lần. Dùng session statistics, SQL Trace, DBMS_HPROF và DBMS_XPLAN để xác định nút thắt, rồi benchmark cùng dữ liệu và transaction. Tối ưu tốt là giảm công việc qua lại mà vẫn giữ đúng kết quả, tính toàn vẹn và ranh giới transaction của nghiệp vụ.

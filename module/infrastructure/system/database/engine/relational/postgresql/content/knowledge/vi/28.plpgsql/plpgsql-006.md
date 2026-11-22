# RETURN, RETURN NEXT và RETURN QUERY trong PL/pgSQL

## 1. Ba câu lệnh có chữ RETURN nhưng không cùng một ý nghĩa

Trong PostgreSQL, PL/pgSQL cho phép viết hàm có biến cục bộ, điều kiện, vòng lặp và câu lệnh SQL. Khi một hàm cần trả kết quả, ba cú pháp sau thường xuất hiện:

```sql
RETURN expression;
RETURN NEXT expression;
RETURN QUERY SELECT ...;
```

Nhìn qua, cả ba có vẻ là “trả dữ liệu”. Nhưng chúng khác nhau ở **kiểu khai báo hàm**, **số lượng hàng được trả** và quan trọng nhất là **điều khiển luồng**.

Giả sử đang viết chức năng tra cứu nhân viên:

- Cần trả **một số nguyên** là tổng số người đang làm việc → `RETURN expression`.
- Cần duyệt từng nhân viên và bổ sung mỗi người vào tập kết quả → `RETURN NEXT` trong hàm `RETURNS SETOF ...`.
- Cần lấy nhiều hàng trực tiếp từ một truy vấn `SELECT` rồi đưa vào tập kết quả → `RETURN QUERY SELECT ...`.

Cơ chế:

```text
FUNCTION trả một giá trị
    |
    +-- RETURN expression
           |
           +-- tính biểu thức
           +-- kết thúc hàm ngay

FUNCTION trả tập nhiều hàng (SETOF / RETURNS TABLE)
    |
    +-- RETURN NEXT [expression]
    |      |
    |      +-- thêm một hàng
    |      +-- tiếp tục chạy lệnh tiếp theo
    |
    +-- RETURN QUERY <query>
    |      |
    |      +-- thêm 0, 1 hoặc nhiều hàng của query
    |      +-- tiếp tục chạy lệnh tiếp theo
    |
    +-- RETURN;
           |
           +-- kết thúc việc xây tập kết quả
```

**Quy tắc nền tảng:** `RETURN NEXT` và `RETURN QUERY` **không thoát khỏi hàm ngay**. Chúng nối dữ liệu vào tập kết quả đang được xây dựng. `RETURN;` không kèm biểu thức có thể được dùng để kết thúc hàm trả tập dữ liệu sau khi đã thêm đủ hàng.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Viết `RETURN expression` cho hàm trả một giá trị.
2. Phân biệt `RETURN NULL`, `RETURN;` và không trả hàng nào.
3. Sử dụng `RETURN` sớm trong các nhánh `IF`/`CASE`.
4. Hiểu xử lý `RETURN;` với hàm có `OUT`/`INOUT` parameters.
5. Viết hàm `RETURNS SETOF scalar` bằng `RETURN NEXT`.
6. Viết hàm `RETURNS TABLE(...)` bằng `RETURN NEXT;` không đối số.
7. Dùng `RETURN NEXT` với biến hàng kiểu composite.
8. Viết `RETURN QUERY SELECT ...` để trả nhiều hàng theo cách set-based.
9. Kết hợp nhiều `RETURN QUERY`, hoặc kết hợp `RETURN NEXT` và `RETURN QUERY` trong cùng một hàm.
10. Viết `RETURN QUERY EXECUTE ... USING ...` cho SQL động có tham số an toàn.
11. Hiểu tác động của `FOUND` sau `RETURN QUERY` và giới hạn của `RETURN NEXT`.
12. Xử lý mismatch kiểu trả về, bao gồm lỗi `count(*)` trả `bigint`.
13. Phân biệt `RETURNS TABLE`, `RETURNS SETOF composite` và `RETURNS SETOF record`.
14. Dùng hàm trả tập trong `FROM`, `JOIN LATERAL` và các truy vấn có bộ lọc.
15. Hiểu cơ chế materialization của PL/pgSQL set-returning functions và tác động tới `LIMIT`/bộ nhớ.
16. Thiết kế đúng volatility, bảo mật, chi phí và khả năng bảo trì khi trả tập dữ liệu.

---

## 2. Bảng so sánh nhanh

| Đặc điểm | `RETURN expression` | `RETURN NEXT` | `RETURN QUERY` |
|---|---|---|---|
| Dùng chính trong | Hàm trả một giá trị/hàng | Hàm trả tập | Hàm trả tập |
| Số hàng đóng góp | Kết quả trả của hàm scalar | Một phần tử/hàng mỗi lần gọi | 0 hoặc nhiều hàng từ query |
| Kết thúc hàm ngay? | **Có** | **Không** | **Không** |
| Lặp lại nhiều lần trong một lời gọi? | Không sau lần thực thi tới RETURN | Có | Có |
| Dùng với `RETURNS SETOF`? | Không dùng dạng `RETURN expression` để kết thúc tập | Có | Có |
| Dùng với `RETURNS TABLE`? | Dùng `RETURN;` không biểu thức để kết thúc | Có, **không truyền expression** | Có |
| Cần câu SELECT? | Không bắt buộc | Không bắt buộc | Thường có SELECT, hoặc EXECUTE |
| Dễ dùng cho tập dữ liệu truy vấn từ bảng | Không | Có nhưng phải duyệt | Thường thuận tiện nhất |
| Câu kết thúc thường gặp | Tự kết thúc | Sau vòng lặp dùng `RETURN;` | Sau truy vấn dùng `RETURN;` |

Một cách hiểu ngắn:

```text
RETURN x;       -> "Đây là kết quả của tôi. Tôi kết thúc."
RETURN NEXT x;  -> "Thêm x vào kết quả. Tôi còn chạy tiếp."
RETURN QUERY q; -> "Thêm mọi hàng của q vào kết quả. Tôi còn chạy tiếp."
RETURN;         -> "Kết thúc mà không cung cấp biểu thức mới."
```

**Cảnh báo:** câu `RETURN;` không biểu thức có ý nghĩa hợp lệ trong những loại routine cụ thể như `RETURNS void`, hàm có output parameters, hàm trả tập hoặc procedure. Không lấy nó để thay `RETURN integer_expression` trong một hàm `RETURNS integer` thông thường.

## 3. Chuẩn bị môi trường PL/pgSQL

Các ví dụ dành cho cơ sở dữ liệu PostgreSQL học tập. Đừng chạy DDL hoặc cập nhật dữ liệu của bài trên production.

Kiểm tra phiên bản:

```sql
SHOW server_version;
SHOW search_path;
```

Tạo schema riêng:

```sql
CREATE SCHEMA IF NOT EXISTS pl358;
```

PostgreSQL hỗ trợ `LANGUAGE plpgsql` trong các phiên bản hiện đại. Các routine dưới đây dùng tên có schema `pl358.` để hạn chế nhầm với object ngoài lab.

### 3.1. PL/pgSQL function: khung cơ bản

```sql
CREATE FUNCTION schema_name.function_name(
    p_input integer
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
    v_result integer;
BEGIN
    v_result := p_input * 2;
    RETURN v_result;
END;
$$;
```

- `DECLARE` khai báo biến cục bộ.
- `BEGIN ... END` là khối lệnh PL/pgSQL; riêng `BEGIN` của khối này **không đồng nghĩa** lệnh SQL bắt đầu transaction.
- `:=` gán cho biến PL/pgSQL.
- `RETURN` điều khiển việc kết thúc function.

## 4. Tạo bộ dữ liệu nhân viên dùng xuyên suốt bài

Ta sẽ có các phòng ban và nhân viên, trong đó một số nhân viên không còn hoạt động.

### 4.1. Bảng phòng ban

```sql
CREATE TABLE pl358.departments (
    department_id integer PRIMARY KEY,
    department_name text NOT NULL UNIQUE
);
```

### 4.2. Bảng nhân viên

```sql
CREATE TABLE pl358.employees (
    employee_id integer PRIMARY KEY,
    department_id integer NOT NULL
        REFERENCES pl358.departments(department_id),
    full_name text NOT NULL,
    monthly_salary numeric(12, 2) NOT NULL
        CHECK (monthly_salary >= 0),
    is_active boolean NOT NULL DEFAULT true,
    hired_on date NOT NULL
);
```

### 4.3. Dữ liệu mẫu

```sql
INSERT INTO pl358.departments(
    department_id, department_name
)
VALUES
    (10, 'Engineering'),
    (20, 'Sales'),
    (30, 'Support'),
    (40, 'Research');

INSERT INTO pl358.employees(
    employee_id,
    department_id,
    full_name,
    monthly_salary,
    is_active,
    hired_on
)
VALUES
    (101, 10, 'An',    2200.00, true,  DATE '2024-01-10'),
    (102, 10, 'Bình',  2900.00, true,  DATE '2023-03-11'),
    (103, 10, 'Chi',   3100.00, false, DATE '2022-05-08'),
    (104, 20, 'Dũng',  2500.00, true,  DATE '2024-06-15'),
    (105, 20, 'Hà',    1600.00, true,  DATE '2025-02-20'),
    (106, 30, 'Lan',   2100.00, true,  DATE '2024-09-01'),
    (107, 30, 'Minh',  1800.00, false, DATE '2025-01-17'),
    (108, 30, 'Phương',1700.00, true,  DATE '2025-08-05');
```

### 4.4. Kiểm tra tập dữ liệu

```sql
SELECT
    d.department_name,
    e.employee_id,
    e.full_name,
    e.monthly_salary,
    e.is_active
FROM pl358.employees AS e
JOIN pl358.departments AS d
    ON d.department_id = e.department_id
ORDER BY d.department_id, e.employee_id;
```

Bộ dữ liệu có:

- Engineering: 2 người active, 1 người inactive.
- Sales: 2 người active.
- Support: 2 người active, 1 người inactive.
- Research: chưa có nhân viên.

Các con số cố định này giúp dự đoán kết quả trước khi chạy hàm.

## 5. RETURN expression: kết thúc và trả một giá trị

Tạo hàm nhân đôi:

```sql
CREATE OR REPLACE FUNCTION pl358.double_number(
    p_number integer
)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN p_number * 2;
END;
$$;
```

Gọi:

```sql
SELECT pl358.double_number(21) AS result;
```

Kết quả dự kiến:

```text
result
------
42
```

Ở thời điểm `RETURN p_number * 2;`:

1. PostgreSQL đánh giá biểu thức theo kiểu kết quả thích hợp.
2. Trả giá trị cho người gọi.
3. Chấm dứt luồng thực thi hàm.

### 5.1. Lệnh sau RETURN không chạy

```sql
CREATE OR REPLACE FUNCTION pl358.return_stops_execution()
RETURNS integer
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Trước RETURN';
    RETURN 7;
    RAISE NOTICE 'Sau RETURN';
END;
$$;
```

Gọi:

```sql
SELECT pl358.return_stops_execution();
```

Kết quả số là 7. Thông báo **“Sau RETURN”** không được phát ra vì hàm đã kết thúc.

Không dùng một lệnh `RAISE NOTICE` sau RETURN như bằng chứng sẽ có hoạt động hậu xử lý.

## 6. Early RETURN trong IF/ELSIF/ELSE

Một hàm phân loại lương:

```sql
CREATE OR REPLACE FUNCTION pl358.salary_grade(
    p_salary numeric
)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_salary IS NULL THEN
        RETURN 'UNKNOWN';
    END IF;

    IF p_salary >= 2800 THEN
        RETURN 'HIGH';
    ELSIF p_salary >= 2000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'LOW';
    END IF;
END;
$$;
```

Ví dụ:

```sql
SELECT
    pl358.salary_grade(3000) AS grade_3000,
    pl358.salary_grade(2200) AS grade_2200,
    pl358.salary_grade(1500) AS grade_1500,
    pl358.salary_grade(NULL::numeric) AS grade_null;
```

Kết quả dự kiến:

| Đầu vào | Giá trị trả |
|---|---|
| 3000 | HIGH |
| 2200 | MEDIUM |
| 1500 | LOW |
| NULL | UNKNOWN |

### 6.1. Early RETURN giúp giảm lồng điều kiện

Thay vì:

```text
IF valid
  IF case A
     ...
  ELSE
     ...
  END IF
ELSE
  ...
END IF
```

có thể kiểm tra những tình huống cần kết thúc sớm:

```sql
IF invalid_input THEN
    RETURN fallback_value;
END IF;
```

Nhưng early return chỉ phù hợp khi thật sự muốn **kết thúc luôn hàm**, không phù hợp nếu cần tiếp tục bổ sung các hàng trong hàm trả tập.

## 7. Hàm scalar phải có đường trả về phù hợp

Xét hàm sai:

```sql
-- Ví dụ cố ý thiếu đường RETURN:
CREATE FUNCTION pl358.missing_return(
    p_value integer
)
RETURNS integer
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_value > 0 THEN
        RETURN p_value;
    END IF;
END;
$$;
```

Với đầu vào dương, có RETURN. Nhưng với `p_value <= 0` hoặc NULL, hàm đi tới `END` mà không có giá trị trả.

Khi đường thực thi ấy xảy ra, PL/pgSQL có thể báo lỗi dạng:

```text
control reached end of function without RETURN
```

### 7.1. Cách sửa rõ ràng

```sql
CREATE OR REPLACE FUNCTION pl358.missing_return(
    p_value integer
)
RETURNS integer
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_value > 0 THEN
        RETURN p_value;
    END IF;

    RETURN 0;
END;
$$;
```

Bây giờ mọi đường kết thúc có `RETURN expression`.

### 7.2. NULL trong IF

Trong PL/pgSQL, nhánh `IF expression THEN` chạy khi biểu thức là TRUE. FALSE hoặc NULL không làm nhánh THEN chạy.

Vì vậy phải quyết định rõ p_value=NULL có ý nghĩa gì, thay vì vô tình để nó rơi xuống cuối hàm.

## 8. RETURN NULL, RETURN 0 và RAISE EXCEPTION

Ba lựa chọn không tương đương.

```sql
RETURN NULL;
```

nghĩa là hàm scalar trả **SQL NULL**.

```sql
RETURN 0;
```

nghĩa là trả giá trị số 0.

```sql
RAISE EXCEPTION 'Invalid input';
```

nghĩa là báo lỗi và làm luồng thực thi thất bại theo semantics exception/transaction, trừ khi có khối xử lý lỗi thích hợp.

### 8.1. Ví dụ kiểm tra đầu vào

```sql
CREATE FUNCTION pl358.safe_percentage(
    p_amount numeric,
    p_total numeric
)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_total IS NULL OR p_total = 0 THEN
        RETURN NULL;
    END IF;

    IF p_amount IS NULL THEN
        RETURN NULL;
    END IF;

    RETURN round(p_amount * 100 / p_total, 2);
END;
$$;
```

### 8.2. Không dùng NULL thay lỗi nếu nghiệp vụ yêu cầu từ chối

Nếu tổng bằng 0 được coi là dữ liệu sai chứ không phải “tỷ lệ chưa xác định”, có thể dùng `RAISE EXCEPTION` với SQLSTATE thích hợp.

Quan trọng là có hợp đồng rõ: **NULL là một kết quả hợp lệ**, không phải đồng nghĩa với exception.

## 9. RETURN trong hàm RETURNS void

Có những function thực hiện tác vụ nhưng không trả dữ liệu có ý nghĩa cho caller.

Ví dụ:

```sql
CREATE FUNCTION pl358.print_department(
    p_department_id integer
)
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'Department ID: %', p_department_id;
    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT pl358.print_department(10);
```

Ở đây:

```sql
RETURN;
```

kết thúc một function `RETURNS void` mà không có biểu thức.

**Không nhầm** với `RETURN NEXT;`, vốn dùng để thêm hàng vào tập kết quả của function set-returning phù hợp.

## 10. RETURN với OUT parameters

Một function có `OUT` parameters có thể đặt kết quả qua các biến output, rồi dùng **`RETURN;` không biểu thức**.

Ví dụ đếm người active và tính tổng lương:

```sql
CREATE FUNCTION pl358.department_pay_summary(
    p_department_id integer,
    OUT active_count bigint,
    OUT salary_total numeric
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    SELECT
        count(*),
        coalesce(sum(e.monthly_salary), 0)
    INTO
        active_count,
        salary_total
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active;

    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM pl358.department_pay_summary(10);
```

Kết quả dự kiến:

| active_count | salary_total |
|---:|---:|
| 2 | 5100.00 |

### 10.1. Vì sao không viết RETURN (active_count, salary_total)?

Với một function có OUT parameters, chính các output variables biểu diễn kết quả. Trong PL/pgSQL, `RETURN` của trường hợp này không nhận biểu thức theo cách một function scalar RETURNS numeric nhận.

### 10.2. RETURN; cũng có thể kết thúc sớm

Ví dụ sau khi gán OUT values:

```sql
active_count := 0;
salary_total := 0;

IF p_department_id IS NULL THEN
    RETURN;
END IF;
```

Hàm trả các output variables hiện có tại thời điểm kết thúc. Vì vậy cần khởi tạo đầy đủ kết quả theo hợp đồng trước khi early RETURN.

### 10.3. INOUT cũng là output

`INOUT` nhận dữ liệu đầu vào và mang giá trị ra. Trong function PL/pgSQL dùng OUT/INOUT, quy tắc `RETURN;` không biểu thức cũng quan trọng.

## 11. RETURN scalar và function gọi từ SELECT

Hàm trả scalar có thể dùng ngay trong biểu thức SQL:

```sql
SELECT
    e.employee_id,
    e.full_name,
    pl358.salary_grade(e.monthly_salary)
        AS salary_grade
FROM pl358.employees AS e
ORDER BY e.employee_id;
```

Mỗi hàng kết quả có grade theo lương của nhân viên ấy.

### 11.1. Khi nào không cần PL/pgSQL?

Nếu logic chỉ là một biểu thức đơn giản, function `LANGUAGE sql` hoặc viết CASE trực tiếp trong query có thể đơn giản hơn:

```sql
SELECT
    CASE
        WHEN e.monthly_salary >= 2800 THEN 'HIGH'
        WHEN e.monthly_salary >= 2000 THEN 'MEDIUM'
        ELSE 'LOW'
    END
FROM pl358.employees AS e;
```

Chọn PL/pgSQL khi cần điều kiện/biến/vòng lặp hoặc logic procedural, không phải vì mọi phép tính đều cần BEGIN/END.

---

## 12. Chuyển sang hàm trả tập: RETURNS SETOF

`RETURNS SETOF type` khai báo một function có thể trả **nhiều phần tử/hàng** kiểu `type`.

Ví dụ:

```sql
CREATE FUNCTION pl358.active_employee_ids(
    p_department_id integer
)
RETURNS SETOF integer
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_id integer;
BEGIN
    FOR v_id IN
        SELECT e.employee_id
        FROM pl358.employees AS e
        WHERE e.department_id = p_department_id
          AND e.is_active
        ORDER BY e.employee_id
    LOOP
        RETURN NEXT v_id;
    END LOOP;

    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM pl358.active_employee_ids(10);
```

Kết quả dự kiến:

```text
active_employee_ids
-------------------
101
102
```

### 12.1. Ba bước của hàm

1. Duyệt các employee_id thỏa điều kiện.
2. Mỗi `RETURN NEXT v_id;` thêm **một phần tử integer** vào tập trả về.
3. `RETURN;` kết thúc hàm sau khi vòng lặp hoàn tất.

### 12.2. RETURN NEXT không ngắt vòng lặp

Đây là khác biệt quan trọng với `RETURN v_id;` của function scalar.

Nếu đổi nhầm:

```sql
-- Không đúng cho hàm SETOF trong ví dụ:
RETURN v_id;
```

thì không phải cách viết để “trả một hàng rồi vòng lặp tiếp tục”. Với hàm set-returning PL/pgSQL, phải dùng `RETURN NEXT` hoặc `RETURN QUERY`.

## 13. RETURN NEXT có thể trả nhiều giá trị từ một vòng lặp

Một hàm tạo dãy số đơn giản:

```sql
CREATE FUNCTION pl358.numbers_up_to(
    p_max integer
)
RETURNS SETOF integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_number integer;
BEGIN
    IF p_max IS NULL OR p_max < 1 THEN
        RETURN;
    END IF;

    FOR v_number IN 1..p_max LOOP
        RETURN NEXT v_number;
    END LOOP;

    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM pl358.numbers_up_to(4);
```

Kết quả:

```text
numbers_up_to
-------------
1
2
3
4
```

### 13.1. Empty set khi không có kết quả

```sql
SELECT *
FROM pl358.numbers_up_to(0);
```

Trả **0 hàng**, không phải một hàng chứa NULL hoặc số 0.

### 13.2. Dùng generate_series khi đơn giản hơn

Trong PostgreSQL, chức năng tạo dãy số đã có sẵn:

```sql
SELECT * FROM generate_series(1, 4);
```

Không nên tự viết PL/pgSQL loop cho một phép toán có sẵn dạng set-based chỉ vì muốn dùng RETURN NEXT. Ví dụ trên dành cho việc học điều khiển luồng.

## 14. Trả một hàng chứa NULL khác trả tập rỗng

Một hàm trả tập số nguyên có thể cố ý thêm **một phần tử NULL**:

```sql
CREATE FUNCTION pl358.one_nullable_integer()
RETURNS SETOF integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN NEXT NULL::integer;
    RETURN;
END;
$$;
```

```sql
SELECT * FROM pl358.one_nullable_integer();
```

Kết quả: **1 hàng** với giá trị SQL NULL.

So với:

```sql
CREATE FUNCTION pl358.no_integer_rows()
RETURNS SETOF integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN;
END;
$$;
```

```sql
SELECT * FROM pl358.no_integer_rows();
```

Kết quả: **0 hàng**.

### 14.1. Vì sao khác biệt này quan trọng?

Trong một báo cáo:

- **0 hàng** có thể có nghĩa “không có bản ghi phù hợp”.
- **1 hàng, cột NULL** có thể có nghĩa “có một kết quả nhưng giá trị chưa xác định”.

Không tự đổi một trường hợp sang trường hợp kia chỉ để giao diện hiện dòng trống.

## 15. RETURN NEXT với biến kiểu hàng tổng hợp

Một function có thể trả toàn bộ hàng theo kiểu bảng đã định nghĩa.

```sql
CREATE FUNCTION pl358.active_employee_rows(
    p_department_id integer
)
RETURNS SETOF pl358.employees
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_employee pl358.employees%ROWTYPE;
BEGIN
    FOR v_employee IN
        SELECT e.*
        FROM pl358.employees AS e
        WHERE e.department_id = p_department_id
          AND e.is_active
        ORDER BY e.employee_id
    LOOP
        RETURN NEXT v_employee;
    END LOOP;

    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT
    x.employee_id,
    x.full_name,
    x.monthly_salary
FROM pl358.active_employee_rows(10) AS x
ORDER BY x.employee_id;
```

Kết quả dự kiến là hai nhân viên 101 và 102.

### 15.1. %ROWTYPE có vai trò gì?

`v_employee pl358.employees%ROWTYPE;` khai báo biến với cấu trúc hàng của bảng employees, gồm các cột:

```text
employee_id
department_id
full_name
monthly_salary
is_active
hired_on
```

Vì function `RETURNS SETOF pl358.employees`, mỗi `RETURN NEXT v_employee;` thêm một hàng composite đúng cấu trúc.

### 15.2. Trả thiếu một cột không tự tạo hàng hợp lệ

Nếu chỉ `SELECT employee_id, full_name` vào một biến không tương thích với row type của bảng, không thể tự coi đó là một hàng `pl358.employees` đầy đủ. Kiểu bản ghi khi trả phải tương thích với return type được khai báo.

### 15.3. Cẩn trọng khi thay schema bảng

Nếu function trả trực tiếp row type của một bảng, việc thay đổi cấu trúc bảng có thể ảnh hưởng kết quả API và các consumer. Với API ổn định lâu dài, `RETURNS TABLE` chỉ định những cột công khai cần thiết thường dễ kiểm soát hơn.

## 16. RETURNS TABLE: khai báo tập hàng theo các cột cụ thể

Hàm có thể trả một tập hàng mà mỗi hàng có ba cột:

```sql
CREATE FUNCTION pl358.find_active_employees(
    p_department_id integer,
    p_min_salary numeric DEFAULT 0
)
RETURNS TABLE (
    employee_id integer,
    employee_name text,
    salary numeric
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.employee_id,
        e.full_name::text,
        e.monthly_salary::numeric
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
      AND e.monthly_salary >= p_min_salary
    ORDER BY e.employee_id;

    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM pl358.find_active_employees(10);
```

Kết quả dự kiến:

| employee_id | employee_name | salary |
|---:|---|---:|
| 101 | An | 2200.00 |
| 102 | Bình | 2900.00 |

Gọi với lương tối thiểu:

```sql
SELECT *
FROM pl358.find_active_employees(
    p_department_id => 20,
    p_min_salary => 2000
);
```

Kết quả: nhân viên Dũng, ID 104, lương 2500.00.

### 16.1. RETURNS TABLE tương đương hướng định nghĩa OUT columns cho tập

Các cột:

```text
employee_id integer
employee_name text
salary numeric
```

được PostgreSQL hiểu là những output parameters của kết quả, đồng thời có thể truy cập như các biến PL/pgSQL trong thân hàm.

Chính vì vậy, khi dùng `RETURN NEXT` với `RETURNS TABLE`, cú pháp khác `RETURNS SETOF integer`.

## 17. RETURN QUERY: bổ sung mọi hàng của câu SELECT

Phần quan trọng nhất của ví dụ trước:

```sql
RETURN QUERY
SELECT
    e.employee_id,
    e.full_name::text,
    e.monthly_salary::numeric
FROM pl358.employees AS e
WHERE e.department_id = p_department_id
  AND e.is_active
ORDER BY e.employee_id;
```

Ý nghĩa:

- Chạy câu SELECT.
- Mọi hàng phù hợp được **bổ sung vào tập kết quả** của function.
- Nếu SELECT không trả hàng, không thêm hàng nào.
- Sau khi thêm xong, **hàm vẫn tiếp tục thực thi** các câu lệnh phía sau.

### 17.1. RETURN QUERY không giống RETURN (SELECT ...)

Sai về ngữ nghĩa:

```sql
-- Không phải cách trả nhiều hàng trong PL/pgSQL SETOF:
RETURN (
    SELECT e.employee_id
    FROM pl358.employees AS e
);
```

Một scalar subquery có quy tắc riêng: nó không biến `RETURN expression` thành kết quả nhiều hàng. Đối với set-returning PL/pgSQL, dùng `RETURN QUERY` hoặc `RETURN NEXT`.

### 17.2. RETURN QUERY không cần vòng lặp phía PL/pgSQL

Viết:

```sql
RETURN QUERY SELECT ...;
```

thường ngắn gọn hơn duyệt từng hàng với:

```sql
FOR v_row IN SELECT ... LOOP
    RETURN NEXT v_row;
END LOOP;
```

Khi truy vấn đã xác định đầy đủ các hàng cần trả và không có quy tắc biến đổi theo từng bước, ưu tiên cách set-based.

## 18. RETURN NEXT; không đối số trong RETURNS TABLE

Với hàm `RETURNS TABLE(...)`, các output columns cũng là biến PL/pgSQL.

Ví dụ cùng logic bằng vòng lặp:

```sql
CREATE FUNCTION pl358.find_active_employees_loop(
    p_department_id integer
)
RETURNS TABLE (
    employee_id integer,
    employee_name text,
    salary numeric
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_employee pl358.employees%ROWTYPE;
BEGIN
    FOR v_employee IN
        SELECT e.*
        FROM pl358.employees AS e
        WHERE e.department_id = p_department_id
          AND e.is_active
        ORDER BY e.employee_id
    LOOP
        employee_id := v_employee.employee_id;
        employee_name := v_employee.full_name;
        salary := v_employee.monthly_salary;

        RETURN NEXT;
    END LOOP;

    RETURN;
END;
$$;
```

`RETURN NEXT;` ở đây có **dấu chấm phẩy ngay sau NEXT**, không có expression.

### 18.1. Vì sao không RETURN NEXT v_employee?

Ở dạng `RETURNS TABLE`, output parameters đã quyết định cấu trúc từng hàng. Theo quy tắc PL/pgSQL, khi có OUT parameters, `RETURN NEXT` cần được viết **không truyền expression**; nó thêm các giá trị output variables hiện hành.

Khác với:

```sql
RETURNS SETOF pl358.employees
...
RETURN NEXT v_employee;
```

vì trường hợp đó không có output parameters tách riêng và phải truyền hàng composite tương thích.

### 18.2. Gán đầy đủ output variables trước RETURN NEXT

Nếu quên:

```sql
salary := v_employee.monthly_salary;
```

thì output `salary` có thể giữ giá trị của lần trước hoặc NULL theo trạng thái biến hiện hành, dẫn đến trả sai dữ liệu.

Hãy gán **mọi cột** cần thiết cho mỗi lượt phát hàng, hoặc dùng `RETURN QUERY` khi có thể.

## 19. So sánh hai cách trả tập có cùng ý nghĩa

**Cách 1 — Loop + RETURN NEXT:**

```sql
FOR v_employee IN
    SELECT e.*
    FROM pl358.employees AS e
    WHERE e.is_active
LOOP
    employee_id := v_employee.employee_id;
    employee_name := v_employee.full_name;
    salary := v_employee.monthly_salary;
    RETURN NEXT;
END LOOP;
```

**Cách 2 — RETURN QUERY:**

```sql
RETURN QUERY
SELECT
    e.employee_id,
    e.full_name::text,
    e.monthly_salary::numeric
FROM pl358.employees AS e
WHERE e.is_active;
```

| Tiêu chí | RETURN NEXT | RETURN QUERY |
|---|---|---|
| Diễn đạt “một hàng mỗi lượt” | Trực quan | Không |
| Cần biến loop/output | Thường có | Không bắt buộc |
| Dùng SELECT tập hợp | Có thể thông qua FOR | Trực tiếp |
| Biến đổi từng hàng bằng PL/pgSQL | Dễ thể hiện | Thường đưa vào SQL expression |
| Nối nhiều nguồn kết quả | Có | Có |
| Tự kết thúc function | Không | Không |
| Phù hợp truy vấn SQL thuần có nhiều hàng | Ít gọn hơn | Thường gọn hơn |

Không khẳng định RETURN QUERY luôn nhanh hơn trong mọi trường hợp mà không đo. Nhưng về thiết kế, cách set-based đơn giản thường đáng ưu tiên khi không cần điều khiển riêng từng hàng.

## 20. Kết hợp nhiều RETURN QUERY trong một hàm

Vì `RETURN QUERY` không kết thúc hàm, có thể thêm nhiều nhóm kết quả.

Ví dụ lấy nhân viên active trước, rồi inactive:

```sql
CREATE FUNCTION pl358.employees_by_activity(
    p_department_id integer
)
RETURNS TABLE (
    employee_id integer,
    employee_name text,
    is_active boolean
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.employee_id, e.full_name::text, e.is_active
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
    ORDER BY e.employee_id;

    RETURN QUERY
    SELECT e.employee_id, e.full_name::text, e.is_active
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND NOT e.is_active
    ORDER BY e.employee_id;

    RETURN;
END;
$$;
```

Với phòng Engineering, kết quả của hai nhánh gồm:

- Active: An (101), Bình (102).
- Inactive: Chi (103).

### 20.1. Không có UNION ngầm loại trùng

Hai lệnh `RETURN QUERY` **nối** hàng vào tập kết quả, không tự loại trùng.

Nếu một nhân viên thỏa điều kiện của cả hai nhánh, có thể xuất hiện hai lần.

Muốn `DISTINCT`/`UNION`, hãy diễn đạt trực tiếp bằng SQL hoặc thêm logic riêng theo yêu cầu.

### 20.2. Thứ tự kết quả phải được bảo đảm tại nơi sử dụng

Hai truy vấn có `ORDER BY` nội bộ giúp diễn đạt thứ tự tạo dữ liệu, nhưng **không nên dựa vào thứ tự hàng từ function như một hợp đồng của truy vấn SQL bên ngoài nếu không có ORDER BY ở caller**.

Gọi rõ:

```sql
SELECT *
FROM pl358.employees_by_activity(10)
ORDER BY is_active DESC, employee_id;
```

để biểu đạt thứ tự mong muốn cho người dùng cuối.

## 21. Kết hợp RETURN NEXT và RETURN QUERY

Có thể thêm một hàng tổng hợp đầu tiên, rồi thêm các hàng truy vấn.

Ví dụ dùng một nhãn text:

```sql
CREATE FUNCTION pl358.department_messages(
    p_department_id integer
)
RETURNS SETOF text
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN NEXT
        ('Department=' || p_department_id::text);

    RETURN QUERY
    SELECT
        e.employee_id::text || ':' || e.full_name
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
    ORDER BY e.employee_id;

    RETURN NEXT 'END';

    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM pl358.department_messages(10);
```

Tập giá trị được thêm theo luồng logic gồm:

```text
Department=10
101:An
102:Bình
END
```

Nếu cần thứ tự ổn định khi trình bày, tốt hơn trả thêm cột `sort_key` và dùng ORDER BY ở caller, thay vì chỉ dựa vào thứ tự nối thêm.

### 21.1. Sử dụng kết hợp có hợp lý không?

Có, khi kết quả bản chất gồm nhiều nhóm khác nhau. Nhưng nếu cần trả header/footer và rows có kiểu khác nhau, một bảng text duy nhất có thể không phải thiết kế API tốt.

Đôi khi nên trả các tập kết quả qua JSON object có cấu trúc, một row tổng hợp hoặc hai query riêng. Chọn kiểu kết quả theo nhu cầu caller.

## 22. RETURN QUERY với JOIN, GROUP BY và aggregate

`RETURN QUERY` có thể nhận bất kỳ SELECT trả cấu trúc hàng phù hợp, không chỉ SELECT đơn bảng.

Ví dụ báo cáo theo phòng ban:

```sql
CREATE FUNCTION pl358.department_statistics()
RETURNS TABLE (
    department_id integer,
    department_name text,
    active_count bigint,
    total_salary numeric
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.department_id,
        d.department_name::text,
        count(e.employee_id)::bigint,
        coalesce(sum(e.monthly_salary), 0)::numeric
    FROM pl358.departments AS d
    LEFT JOIN pl358.employees AS e
        ON e.department_id = d.department_id
       AND e.is_active
    GROUP BY d.department_id, d.department_name
    ORDER BY d.department_id;

    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM pl358.department_statistics()
ORDER BY department_id;
```

Kết quả dự kiến:

| department_id | department_name | active_count | total_salary |
|---:|---|---:|---:|
| 10 | Engineering | 2 | 5100.00 |
| 20 | Sales | 2 | 4100.00 |
| 30 | Support | 2 | 3800.00 |
| 40 | Research | 0 | 0 |

### 22.1. Vì sao đặt e.is_active trong ON?

Muốn giữ cả phòng ban **không có nhân viên active**, điều kiện `e.is_active` nằm trong `ON` của LEFT JOIN. Nếu chuyển sang `WHERE e.is_active`, phòng Research sẽ bị loại vì các cột bên phải là NULL.

### 22.2. COUNT(e.employee_id) thay vì COUNT(*)

Với LEFT JOIN:

- `COUNT(e.employee_id)` chỉ đếm nhân viên match.
- `COUNT(*)` vẫn đếm một hàng kết quả join được bảo tồn cho phòng Research.

Dùng count theo khóa bên phải để nhận 0 đúng cho phòng không có nhân viên.

## 23. RETURN QUERY không thêm hàng khi SELECT rỗng

Gọi:

```sql
SELECT *
FROM pl358.find_active_employees(40);
```

Phòng Research chưa có nhân viên, nên `RETURN QUERY SELECT ...` thêm **0 hàng**.

Nhưng hàm không tự báo lỗi vì tập rỗng. Sau RETURN QUERY, lệnh `RETURN;` kết thúc và trả tập rỗng.

### 23.1. Không nhầm với scalar NULL

```sql
SELECT pl358.safe_percentage(10, 0);
```

là một query có thể trả **1 hàng với scalar NULL**.

```sql
SELECT *
FROM pl358.find_active_employees(40);
```

trả **0 hàng**.

### 23.2. Khi muốn một hàng mặc định

Nếu business muốn có một hàng báo “không có dữ liệu”, hãy thiết kế kiểu kết quả có trạng thái rõ ràng, ví dụ `result_status text` và cột số lượng, hoặc trả một JSON object riêng.

Không tự chèn một hàng với employee_id=NULL vào tập nhân viên mà không có quy ước API, vì nó làm cho các phép COUNT/JOIN downstream khó đoán.

## 24. Biến đặc biệt FOUND sau RETURN QUERY

PL/pgSQL có biến boolean đặc biệt `FOUND` trong ngữ cảnh thực thi function.

Với `RETURN QUERY`:

- `FOUND = TRUE` nếu câu RETURN QUERY **bổ sung ít nhất một hàng**.
- `FOUND = FALSE` nếu câu RETURN QUERY **không bổ sung hàng nào**.

Ví dụ:

```sql
CREATE FUNCTION pl358.active_employees_or_message(
    p_department_id integer
)
RETURNS SETOF text
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.full_name::text
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
    ORDER BY e.employee_id;

    IF NOT FOUND THEN
        RETURN NEXT '[NO_ACTIVE_EMPLOYEES]';
    END IF;

    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM pl358.active_employees_or_message(10);
```

kết quả gồm An, Bình.

Với department 40, SELECT rỗng, `FOUND` là FALSE; hàm thêm một dòng text `[NO_ACTIVE_EMPLOYEES]`.

### 24.1. Đọc FOUND ngay sau RETURN QUERY

Các câu lệnh khác như `SELECT INTO`, `PERFORM`, một số DML hoặc hoàn tất vòng lặp `FOR` có thể làm thay đổi `FOUND`.

Sai về mặt thiết kế:

```sql
RETURN QUERY SELECT ...;

PERFORM some_other_operation();

IF FOUND THEN
    -- Lúc này FOUND có thể phản ánh PERFORM,
    -- không còn phản ánh RETURN QUERY.
END IF;
```

Nếu cần kết quả kiểm tra, lưu `FOUND` vào biến riêng ngay sau `RETURN QUERY`:

```sql
v_had_rows := FOUND;
```

### 24.2. RETURN NEXT có thay FOUND không?

Theo semantics PL/pgSQL, `RETURN NEXT` **không** thay đổi `FOUND` như `RETURN QUERY`.

Vì vậy không viết:

```sql
RETURN NEXT x;
IF FOUND THEN ...
```

với giả định FOUND cho biết đã phát một hàng. Nó có thể đang phản ánh một câu lệnh trước đó.

## 25. RETURN QUERY EXECUTE cho SQL động

`RETURN QUERY` có thể lấy kết quả từ một câu SQL **được tạo tại runtime**:

```sql
RETURN QUERY EXECUTE command_string USING parameter_values;
```

Nó phù hợp khi phải thay đổi cấu trúc SQL, chẳng hạn chọn cột sắp xếp từ **danh sách được phép**.

### 25.1. Ví dụ sắp xếp theo cột lựa chọn

```sql
CREATE FUNCTION pl358.find_active_sorted(
    p_department_id integer,
    p_sort_column text DEFAULT 'employee_id',
    p_desc boolean DEFAULT false
)
RETURNS TABLE (
    employee_id integer,
    employee_name text,
    salary numeric
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_direction text;
BEGIN
    IF p_sort_column IS NULL
       OR p_sort_column NOT IN (
           'employee_id',
           'full_name',
           'monthly_salary'
       ) THEN
        RAISE EXCEPTION 'Unsupported sort column: %',
            p_sort_column
            USING ERRCODE = '22023';
    END IF;

    IF p_desc IS NULL THEN
        RAISE EXCEPTION 'Sort direction must not be NULL'
            USING ERRCODE = '22023';
    END IF;

    v_direction := CASE
        WHEN p_desc THEN 'DESC'
        ELSE 'ASC'
    END;

    RETURN QUERY EXECUTE format(
        'SELECT
             e.employee_id,
             e.full_name::text,
             e.monthly_salary::numeric
         FROM pl358.employees AS e
         WHERE e.department_id = $1
           AND e.is_active
         ORDER BY e.%I %s, e.employee_id ASC',
        p_sort_column,
        v_direction
    )
    USING p_department_id;

    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM pl358.find_active_sorted(
    p_department_id => 10,
    p_sort_column => 'monthly_salary',
    p_desc => true
);
```

Kết quả có hai hàng, sắp xếp từ lương cao xuống:

| employee_id | employee_name | salary |
|---:|---|---:|
| 102 | Bình | 2900.00 |
| 101 | An | 2200.00 |

### 25.2. Vì sao dùng format('%I', identifier)?

Tên cột không thể bind bằng `USING` như một giá trị SQL bình thường. `%I` quote một identifier theo quy tắc PostgreSQL. Đồng thời, tên cột phải đi qua **whitelist** trước khi đưa vào SQL động.

### 25.3. Vì sao có USING p_department_id?

Placeholder `$1` trong chuỗi query nhận giá trị từ `USING p_department_id`. Cách này tránh nối trực tiếp giá trị input vào text SQL.

### 25.4. Vì sao %s cho ASC/DESC?

`ASC` và `DESC` là từ khóa cú pháp, không phải string value hay identifier. Trong ví dụ, `v_direction` **chỉ được tạo từ boolean thành một trong hai hằng số đáng tin**. Không bao giờ thay nó bằng chuỗi điều khiển trực tiếp từ người dùng chưa kiểm tra.

## 26. SQL injection với RETURN QUERY EXECUTE

Đây là ví dụ **không an toàn**, chỉ để minh họa điều cần tránh:

```sql
-- KHÔNG dùng mẫu này với input không đáng tin:
RETURN QUERY EXECUTE
    'SELECT ... FROM pl358.employees
     WHERE full_name = ''' || p_name || '''';
```

Nếu p_name chứa dấu nháy hoặc nội dung SQL bất thường, câu lệnh có thể lỗi hoặc bị thay đổi ý nghĩa.

### 26.1. Dùng USING cho giá trị

Mẫu đúng hơn:

```sql
RETURN QUERY EXECUTE
    'SELECT
         e.employee_id,
         e.full_name::text,
         e.monthly_salary::numeric
     FROM pl358.employees AS e
     WHERE e.full_name = $1'
USING p_name;
```

### 26.2. Với identifier phải quote và whitelist

`format('%I', p_column)` quote identifier. Nhưng nếu nghiệp vụ chỉ cho sắp theo ba cột, phải **kiểm tra ba giá trị cho phép** trước. Quote đúng vẫn không chứng minh người dùng được phép đọc hoặc sắp theo mọi cột.

### 26.3. Bảo mật không dừng ở SQL injection

Một function `SECURITY DEFINER` trả dữ liệu nhân viên theo p_department_id do client nhập có thể lộ thông tin nếu không xác thực scope/role phù hợp. Dùng schema-qualified object names, grants và cơ chế phân quyền đúng ngay cả khi SQL động đã an toàn về cú pháp.

## 27. Khi nào cần RETURN QUERY EXECUTE thay RETURN QUERY?

Ưu tiên SQL tĩnh nếu query chỉ thay đổi **giá trị**:

```sql
RETURN QUERY
SELECT e.employee_id, e.full_name::text
FROM pl358.employees AS e
WHERE e.department_id = p_department_id;
```

Không cần SQL động cho p_department_id; PL/pgSQL truyền giá trị phù hợp.

Chọn dynamic SQL khi phải thay đổi **cấu trúc câu lệnh**:

- Cột sắp xếp.
- Tên bảng/partition được chọn từ metadata đáng tin.
- Danh sách cột động có cấu trúc được kiểm soát.
- Một số trường hợp cần điều khiển cách plan query theo input.

### 27.1. Dynamic SQL có chi phí

`EXECUTE` động phải xây chuỗi, parse/plan theo ngữ cảnh thích hợp và tăng độ khó kiểm chứng SQL. Đừng chọn nó chỉ vì một function có vài điều kiện lọc tùy chọn.

### 27.2. Dynamic SQL không giải quyết kiểu output

Dù query là dynamic, các hàng được trả vẫn phải **khớp chính xác với cấu trúc RETURN TYPE** của function. Nó không cho phép một function `RETURNS TABLE(id integer, name text)` lúc thì trả 2 cột, lúc thì trả 5 cột mà không có một hợp đồng result type phù hợp.

## 28. Một hàm trả tập có thể RETURN; sớm

Giả sử quy tắc không cho yêu cầu mức lương âm:

```sql
CREATE FUNCTION pl358.find_active_min_salary(
    p_min_salary numeric
)
RETURNS TABLE (
    employee_id integer,
    employee_name text
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF p_min_salary IS NULL OR p_min_salary < 0 THEN
        RETURN;
    END IF;

    RETURN QUERY
    SELECT e.employee_id, e.full_name::text
    FROM pl358.employees AS e
    WHERE e.is_active
      AND e.monthly_salary >= p_min_salary
    ORDER BY e.employee_id;

    RETURN;
END;
$$;
```

Với p_min_salary âm hoặc NULL, `RETURN;` kết thúc function và trả **tập rỗng**.

### 28.1. Trả rỗng hay báo lỗi?

Trong ví dụ trên, lựa chọn trả rỗng là một **quy ước minh họa**, không phải “best practice” bắt buộc.

Nếu input âm là sai nghiệp vụ, thiết kế tốt hơn có thể là:

```sql
IF p_min_salary IS NULL OR p_min_salary < 0 THEN
    RAISE EXCEPTION 'Invalid minimum salary'
        USING ERRCODE = '22023';
END IF;
```

Chọn rõ giữa:

- Không có kết quả hợp lệ.
- Input không hợp lệ.
- Người dùng không có quyền.
- Hệ thống gặp lỗi.

Không nên gộp mọi trường hợp thành “0 hàng” vì caller sẽ khó biết điều gì xảy ra.

## 29. Runtime row type: RETURNS TABLE yêu cầu kiểu đúng

Một lỗi phổ biến:

```text
ERROR: structure of query does not match function result type
```

Ví dụ function khai báo:

```sql
RETURNS TABLE (
    department_id integer,
    active_count integer
)
```

nhưng SELECT:

```sql
SELECT
    e.department_id,
    count(*)
FROM pl358.employees AS e
GROUP BY e.department_id;
```

`count(*)` trả **bigint**, không phải integer.

### 29.1. Cách tốt nhất: khai báo output là bigint

```sql
CREATE FUNCTION pl358.count_employees_by_department()
RETURNS TABLE (
    department_id integer,
    employee_count bigint
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.department_id, count(*)
    FROM pl358.employees AS e
    GROUP BY e.department_id
    ORDER BY e.department_id;

    RETURN;
END;
$$;
```

Kiểu output tương thích với `count(*)`.

### 29.2. Nếu thật sự cần integer

Có thể dùng:

```sql
count(*)::integer
```

nhưng phải hiểu việc ép `bigint → integer` có thể overflow nếu số lượng vượt miền integer. Không cast chỉ để che lỗi kiểu mà chưa xét miền dữ liệu.

## 30. varchar, text, numeric và các kiểu dễ nhầm

PostgreSQL có nhiều kiểu nhìn giống nhau ở biểu diễn nhưng không phải cùng row descriptor.

Ví dụ một cột:

```sql
product_name varchar(100)
```

và function output:

```sql
RETURNS TABLE(product_name text)
```

Khi dùng `RETURN QUERY SELECT product_name`, PL/pgSQL set-returning function có thể báo structure mismatch nếu query trả `character varying` trong khi output đòi `text`.

Giải pháp rõ ràng:

```sql
RETURN QUERY
SELECT p.product_name::text
FROM schema_name.products AS p;
```

### 30.1. Không dựa vào implicit cast như function scalar

Khi PostgreSQL gán giá trị vào biến scalar, có thể có những cơ chế chuyển kiểu. Nhưng `RETURN QUERY` trả **tập hàng có row descriptor**, và PL/pgSQL yêu cầu cấu trúc phải khớp với return type. Không nên giả định mọi kiểu “đọc gần giống” sẽ được tự chuyển trong kết quả nhiều cột.

### 30.2. numeric(12,2) với numeric

Cột `monthly_salary numeric(12,2)` có kiểu cơ sở `numeric`. Trong ví dụ đã dùng `::numeric` để chủ động thể hiện output, nhưng bài học chính là phải kiểm tra kiểu thực tế của từng expression trong SELECT.

### 30.3. Một SELECT đúng số cột vẫn có thể sai

Nếu function định nghĩa:

```text
(employee_id integer, employee_name text, salary numeric)
```

mà SELECT trả:

```text
(full_name text, employee_id integer, monthly_salary numeric)
```

thì **thứ tự cột sai**, dù số lượng và tên gần giống. PostgreSQL ghép cấu trúc theo vị trí/kiểu của result row; không tự suy đoán rằng cột tên employee_id nên được đổi chỗ.

## 31. Tên biến output có thể gây lỗi ambiguous column reference

Trong `RETURNS TABLE(employee_id integer, employee_name text)`, `employee_id` trở thành biến output của PL/pgSQL.

Giả sử trong query viết:

```sql
RETURN QUERY
SELECT employee_id, full_name
FROM pl358.employees;
```

PL/pgSQL có thể không phân biệt được identifier `employee_id` trong SELECT là:

- Cột `employees.employee_id`.
- Biến output `employee_id` của function.

Kết quả có thể là lỗi:

```text
column reference "employee_id" is ambiguous
```

### 31.1. Cách sửa: dùng alias rõ

```sql
RETURN QUERY
SELECT
    e.employee_id,
    e.full_name::text
FROM pl358.employees AS e;
```

Tên từ output parameters không còn cạnh tranh với `e.employee_id`.

### 31.2. Gợi ý quy ước tên

- `p_`: parameter đầu vào.
- `v_`: biến cục bộ.
- `e.`, `d.`: alias bảng.
- Output columns: tên business rõ ràng.

Không dựa vào cách cấu hình `plpgsql.variable_conflict` để che mọi sự mơ hồ; truy vấn rõ bằng alias an toàn và dễ bảo trì hơn.

## 32. RETURNS SETOF record: linh hoạt nhưng caller phải biết cấu trúc

Đôi khi function trả tập bản ghi nhưng không khai báo cấu trúc cột cố định trong `RETURNS TABLE`.

Ví dụ:

```sql
CREATE FUNCTION pl358.staff_record(
    p_department_id integer
)
RETURNS SETOF record
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.employee_id, e.full_name::text
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
    ORDER BY e.employee_id;

    RETURN;
END;
$$;
```

Vì return type chỉ là `record`, caller thường cần khai báo column definition list:

```sql
SELECT *
FROM pl358.staff_record(10)
AS s(employee_id integer, full_name text);
```

### 32.1. Đừng nhầm record với “mọi schema đều được”

Hàng trả về vẫn phải phù hợp với cấu trúc mà truy vấn của caller yêu cầu. Nếu function trả hai cột (integer,text) nhưng caller khai báo ba cột hoặc sai kiểu, sẽ có lỗi.

### 32.2. Khi nào nên dùng record?

Phù hợp cho một số function chung/công cụ metadata thực sự cần kết quả do caller xác định. Với application API có hợp đồng cột ổn định, `RETURNS TABLE` hoặc kiểu composite rõ ràng dễ dùng hơn.

## 33. RETURNS TABLE, SETOF scalar, SETOF composite và SETOF record

| Kiểu khai báo | Ví dụ | Cách trả phù hợp |
|---|---|---|
| `RETURNS integer` | Một số đếm | `RETURN 10;` |
| `RETURNS text` | Một chuỗi | `RETURN 'OK';` |
| `RETURNS void` | Không trả nội dung | `RETURN;` |
| `OUT x integer, OUT y text` | Một record output | Gán x/y rồi `RETURN;` |
| `RETURNS SETOF integer` | Dãy integer | `RETURN NEXT x;` hoặc `RETURN QUERY SELECT ...` |
| `RETURNS SETOF pl358.employees` | Nhiều hàng composite | `RETURN NEXT v_employee;` hoặc `RETURN QUERY SELECT e.* ...` |
| `RETURNS TABLE(id int, name text)` | Bảng kết quả cố định | Gán output rồi `RETURN NEXT;`, hoặc `RETURN QUERY SELECT ...` |
| `RETURNS SETOF record` | Tập record do caller mô tả | `RETURN NEXT v_record;` hoặc `RETURN QUERY ...`; caller thường khai báo columns |

### 33.1. RETURNS TABLE không phải table vật lý

Function `RETURNS TABLE(...)` không tự tạo bảng thật trong schema. Nó khai báo **cấu trúc tập kết quả**. Dữ liệu được trả qua lời gọi function, không được lưu thành một bảng vật lý nếu không có DML riêng.

### 33.2. Tránh đổi return type mà không migration

Nếu view/ORM/application phụ thuộc ba cột output, đổi thành bốn cột hoặc đổi kiểu có thể làm hỏng downstream. PostgreSQL cũng có ràng buộc với việc dùng `CREATE OR REPLACE FUNCTION` để đổi return type. Hãy xem đây là thay đổi API.

## 34. RETURN với procedure và trigger có khác không?

Bài tập trung vào **function PL/pgSQL**, nhưng chữ RETURN còn xuất hiện trong procedure và trigger.

### 34.1. Procedure

Một procedure được gọi bằng `CALL` và có thể kết thúc sớm bằng:

```sql
RETURN;
```

Không dùng `RETURN QUERY` để “trả tập bảng” từ procedure giống function `RETURNS TABLE`. Cơ chế trả OUT/INOUT của procedures khác và phụ thuộc cách gọi/phiên bản PostgreSQL.

### 34.2. Trigger function

Một trigger function:

```sql
RETURNS trigger
```

thường cần trả:

```sql
RETURN NEW;
```

hoặc:

```sql
RETURN OLD;
```

hoặc NULL tùy loại trigger và mục đích.

Với một **BEFORE ROW** trigger, return value có thể quyết định tiếp tục xử lý hàng nào hoặc bỏ qua hàng; với các dạng trigger khác, return value có semantics riêng.

Không viết `RETURN NEXT NEW;` trong một trigger function thông thường như thể trigger trả tập record.

### 34.3. Phân biệt bằng return declaration

Trước khi chọn RETURN, luôn đọc:

```text
RETURNS scalar?
RETURNS void?
RETURNS trigger?
RETURNS SETOF type?
RETURNS TABLE(...)?
PROCEDURE ...?
```

Cú pháp RETURN đúng phụ thuộc hợp đồng đã khai báo.

## 35. FOUND, SELECT INTO và RETURN QUERY: đừng trộn vai trò

Một hàm scalar thường viết:

```sql
SELECT e.full_name
INTO v_name
FROM pl358.employees AS e
WHERE e.employee_id = p_employee_id;

IF NOT FOUND THEN
    RETURN NULL;
END IF;

RETURN v_name;
```

Đây là luồng **lấy một giá trị** bằng SELECT INTO, kiểm tra FOUND, rồi RETURN.

Một hàm set-returning có thể viết:

```sql
RETURN QUERY
SELECT e.full_name
FROM pl358.employees AS e
WHERE e.department_id = p_department_id;

IF NOT FOUND THEN
    RETURN NEXT '[NO_EMPLOYEES]';
END IF;
```

Đây là luồng **lấy một tập** bằng RETURN QUERY, kiểm tra FOUND, rồi thêm hàng theo chính sách.

### 35.1. SELECT INTO không phải RETURN QUERY

`SELECT ... INTO variable` gán một hàng vào biến PL/pgSQL. Nó không tự thêm hàng vào result set của `RETURNS TABLE`.

### 35.2. PERFORM không phải RETURN QUERY

`PERFORM query;` thực thi truy vấn và bỏ đi kết quả theo ngữ nghĩa PL/pgSQL. Muốn bổ sung các hàng vào tập kết quả function, dùng `RETURN QUERY`.

### 35.3. EXECUTE ... INTO khác RETURN QUERY EXECUTE

`EXECUTE dynamic_sql INTO variable USING ...` lấy giá trị vào biến. `RETURN QUERY EXECUTE dynamic_sql USING ...` thêm hàng từ câu SQL động vào result set.

## 36. Materialization: RETURN NEXT không phải truyền một hàng ngay lập tức cho client

Một điểm hiệu năng rất quan trọng của PL/pgSQL:

> Trong cách triển khai hiện hành, kết quả của function trả tập PL/pgSQL bằng `RETURN NEXT` và `RETURN QUERY` được **tích lũy/materialize trước khi function hoàn tất**, thay vì stream một hàng tới caller ngay tại từng RETURN NEXT.

Sơ đồ:

```text
Caller SELECT * FROM function()
             |
             v
PL/pgSQL function chạy
   |
   +-- RETURN NEXT row A  --> thêm vào tuplestore
   +-- RETURN NEXT row B  --> thêm vào tuplestore
   +-- RETURN QUERY ...   --> thêm nhiều rows vào tuplestore
   |
   +-- RETURN; / tới END
             |
             v
Caller nhận tập kết quả từ function
```

### 36.1. work_mem và dữ liệu lớn

Với tập kết quả lớn, PostgreSQL có thể lưu một phần kết quả tạm ra đĩa khi vượt giới hạn bộ nhớ liên quan như `work_mem`.

Không suy luận từ từ khóa RETURN NEXT rằng client sẽ nhận ngay hàng đầu trong khi loop vẫn chạy.

### 36.2. LIMIT ngoài function chưa chắc giảm việc xây tập

Truy vấn:

```sql
SELECT *
FROM pl358.active_employee_rows(10)
LIMIT 1;
```

không nên được coi là bảo đảm PL/pgSQL function chỉ lấy một nhân viên rồi dừng loop sau `RETURN NEXT` đầu tiên. Với cơ chế materialization, function có thể tạo đầy đủ tập nội bộ trước khi caller áp LIMIT.

Nếu cần giới hạn thật sự, truyền `p_limit` vào function và áp giới hạn trong query/loop theo nghiệp vụ.

### 36.3. Nếu cần xử lý luồng thực sự

Có thể cân nhắc:

- Truy vấn SQL thông thường với `LIMIT`/keyset pagination.
- Cursor/refcursor khi kiến trúc transaction và driver phù hợp.
- Batch processing.
- SQL set-returning function có đặc tính phù hợp.
- Trả phân trang nhỏ thay vì một tập khổng lồ.

Không xem mọi SRF là cơ chế streaming chỉ vì cú pháp có từ RETURN NEXT.

## 37. Đưa LIMIT vào truy vấn bên trong hàm

Ví dụ một hàm trả nhiều hàng nhưng có giới hạn do người gọi truyền:

```sql
CREATE FUNCTION pl358.top_active_employees(
    p_department_id integer,
    p_limit integer DEFAULT 10
)
RETURNS TABLE (
    employee_id integer,
    employee_name text,
    salary numeric
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 100 THEN
        RAISE EXCEPTION 'p_limit must be between 1 and 100'
            USING ERRCODE = '22023';
    END IF;

    RETURN QUERY
    SELECT
        e.employee_id,
        e.full_name::text,
        e.monthly_salary::numeric
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND e.is_active
    ORDER BY e.monthly_salary DESC, e.employee_id
    LIMIT p_limit;

    RETURN;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM pl358.top_active_employees(10, 1);
```

Tập kết quả có **một hàng**: Bình (lương 2900).

### 37.1. LIMIT bên trong khác LIMIT bên ngoài

- `LIMIT p_limit` trong RETURN QUERY giới hạn tập mà function bổ sung.
- `LIMIT 1` của caller chỉ giới hạn kết quả truy vấn ngoài, không phải một lời hứa giảm work xây tập bên trong.

### 37.2. ORDER BY cần tie-breaker

Nếu hai nhân viên có cùng lương, `ORDER BY monthly_salary DESC` đơn lẻ không cho một thứ tự hoàn toàn ổn định. Thêm `employee_id` để phân biệt khi cần phân trang.

### 37.3. Cần phân trang sâu?

`OFFSET` lớn có thể có chi phí cao; có thể dùng keyset pagination với cặp khóa `(salary, employee_id)` phù hợp hướng sort. API function nên nhận cursor/keyset theo hợp đồng, không trả mọi hàng rồi để client cắt bớt.

## 38. RETURN QUERY hay SQL function cho SELECT đơn giản?

Hàm PL/pgSQL:

```sql
CREATE FUNCTION pl358.staff_plpgsql(
    p_department_id integer
)
RETURNS TABLE(employee_id integer, employee_name text)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.employee_id, e.full_name::text
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id;
END;
$$;
```

Hàm SQL tương đương về ý tưởng:

```sql
CREATE FUNCTION pl358.staff_sql(
    p_department_id integer
)
RETURNS TABLE(employee_id integer, employee_name text)
LANGUAGE sql
STABLE
AS $$
    SELECT e.employee_id, e.full_name::text
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id;
$$;
```

### 38.1. Khi nào dùng LANGUAGE sql?

- Thân hàm chỉ là một truy vấn đơn giản.
- Không cần IF, loop, biến hoặc exception handling procedural.
- Có cơ hội tối ưu/inlining tùy nội dung/hàm.
- Muốn code dễ đọc và gần với SQL chuẩn.

### 38.2. Khi nào dùng PL/pgSQL?

- Có nhiều nhánh nghiệp vụ.
- Cần xử lý validation phức tạp.
- Cần ghép các truy vấn theo điều kiện.
- Cần SQL động được kiểm soát.
- Cần làm việc với biến tạm và vòng lặp.

### 38.3. Không khẳng định SQL function luôn inline

Inlining phụ thuộc đặc điểm function, query và PostgreSQL planner. Cần đo trên workload thực tế; tránh suy luận “chỉ đổi ngôn ngữ hàm là chắc chắn nhanh hơn”.

## 39. Volatility: IMMUTABLE, STABLE và VOLATILE

PostgreSQL có các nhãn volatility quan trọng:

| Nhãn | Hướng dùng |
|---|---|
| `IMMUTABLE` | Với cùng input luôn cho cùng kết quả, không phụ thuộc trạng thái DB/thời gian |
| `STABLE` | Có thể đọc dữ liệu database, nhưng kết quả ổn định trong ngữ cảnh snapshot statement theo semantics |
| `VOLATILE` | Có thể thay đổi trong một câu lệnh hoặc gây side effect; là mặc định |

### 39.1. Hàm tính toán thuần

`pl358.double_number` hoặc `pl358.salary_grade` có thể `IMMUTABLE` nếu logic thuần và không phụ thuộc cấu hình thay đổi.

### 39.2. Hàm đọc bảng employees

`pl358.find_active_employees` hoặc `pl358.department_statistics` là các hàm đọc database. `STABLE` thường phù hợp trong ví dụ, không phải `IMMUTABLE`, vì dữ liệu bảng có thể thay đổi.

### 39.3. Hàm ghi dữ liệu

Một function có DML/side effects cần volatility thích hợp, thông thường `VOLATILE`. Không gán IMMUTABLE/STABLE sai để thỏa một index hoặc mong optimizer tối ưu.

### 39.4. RETURN QUERY không quyết định volatility

Một `RETURN QUERY SELECT 1` thuần có đặc tính khác `RETURN QUERY SELECT ... FROM pl358.employees`. Nhãn volatility phản ánh **toàn bộ hành vi routine**, không dựa vào việc có hay không RETURN QUERY.

## 40. Tham số mặc định và named notation trong hàm trả tập

`RETURNS TABLE` có thể dùng input default parameters giống những function khác.

Ví dụ:

```sql
CREATE FUNCTION pl358.lookup_staff(
    p_department_id integer,
    p_active_only boolean DEFAULT true,
    p_min_salary numeric DEFAULT 0
)
RETURNS TABLE (
    employee_id integer,
    employee_name text
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT e.employee_id, e.full_name::text
    FROM pl358.employees AS e
    WHERE e.department_id = p_department_id
      AND (
          NOT p_active_only
          OR e.is_active
      )
      AND e.monthly_salary >= p_min_salary
    ORDER BY e.employee_id;

    RETURN;
END;
$$;
```

Gọi theo tên:

```sql
SELECT *
FROM pl358.lookup_staff(
    p_department_id => 10,
    p_min_salary => 2500
);
```

Mặc định `p_active_only=true`, nên chỉ nhận Bình (102), không nhận Chi dù Chi có lương 3100 vì inactive.

Gọi bao gồm inactive:

```sql
SELECT *
FROM pl358.lookup_staff(
    p_department_id => 10,
    p_active_only => false,
    p_min_salary => 2500
);
```

Trả Bình (102) và Chi (103).

### 40.1. Truyền NULL khác bỏ đối số

Nếu gọi `p_active_only => NULL::boolean`, biểu thức `NOT p_active_only OR e.is_active` có SQL three-valued logic. Hợp đồng function nên định nghĩa có chấp nhận NULL hay sẽ báo lỗi/default fallback.

Không xem DEFAULT true là bảo đảm NULL sẽ được thay bằng true khi caller truyền explicit NULL.

## 41. LATERAL JOIN với hàm trả tập

Set-returning function có thể phụ thuộc một hàng từ bảng bên ngoài nhờ `LATERAL`.

Ví dụ hiển thị mỗi phòng ban và nhân viên active:

```sql
SELECT
    d.department_id,
    d.department_name,
    s.employee_id,
    s.employee_name,
    s.salary
FROM pl358.departments AS d
LEFT JOIN LATERAL
    pl358.find_active_employees(d.department_id) AS s
ON true
ORDER BY d.department_id, s.employee_id;
```

### 41.1. Vì sao LEFT JOIN LATERAL?

- Với Engineering, function trả hai hàng.
- Với Sales, function trả hai hàng.
- Với Support, function trả hai hàng.
- Với Research, function trả tập rỗng.

`LEFT JOIN LATERAL ... ON true` vẫn giữ hàng Research, với các cột `s.*` là SQL NULL.

### 41.2. CROSS JOIN LATERAL khác gì?

`CROSS JOIN LATERAL` chỉ tạo hàng khi function trả ít nhất một hàng. Research sẽ không xuất hiện.

### 41.3. Tránh N+1 ẩn trong database

Một function gọi lại một SELECT trên employees cho từng department có thể tốt với vài department, nhưng nếu có hàng chục nghìn parent rows, chi phí lặp function/query có thể lớn.

Khi có thể, một truy vấn JOIN/GROUP BY set-based thông thường có thể hiệu quả hơn. Đo bằng EXPLAIN và dữ liệu đại diện.

## 42. Hàm trả SETOF trong SELECT list và FROM

Bạn có thể gặp:

```sql
SELECT pl358.active_employee_ids(10);
```

và:

```sql
SELECT *
FROM pl358.active_employee_ids(10);
```

Các set-returning functions đã từng có nhiều chi tiết đặc biệt khi dùng trong SELECT list, nhất là khi phối hợp nhiều SRFs. Đối với code ứng dụng dễ hiểu, ưu tiên gọi trong `FROM`:

```sql
SELECT x.employee_id
FROM pl358.active_employee_ids(10)
AS x(employee_id);
```

### 42.1. Lợi ích khi dùng FROM

- Mỗi phần tử/hàng được biểu diễn thành một nguồn quan hệ.
- Dễ dùng JOIN, WHERE, ORDER BY và LIMIT.
- Dễ đặt alias cột.
- Giảm nhầm lẫn với scalar expressions.
- Khi cần kết hợp các nguồn theo hàng, `LATERAL` biểu đạt tương quan rõ.

### 42.2. Không dựa vào thứ tự không có ORDER BY

Một tập dữ liệu trong SQL không có thứ tự mặc định. Nếu kết quả để hiển thị cho user hoặc phân trang, đặt `ORDER BY` ở truy vấn cuối.

## 43. EXPLAIN cho hàm trả tập

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM pl358.find_active_employees(10, 2000);
```

Bạn có thể thấy node `Function Scan` trong một số tình huống. Kế hoạch có thể thể hiện function như một đơn vị, và không luôn phơi toàn bộ plan SQL bên trong PL/pgSQL function ở mức EXPLAIN của caller.

### 43.1. Muốn phân tích query bên trong

Tách truy vấn:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    e.employee_id,
    e.full_name::text,
    e.monthly_salary::numeric
FROM pl358.employees AS e
WHERE e.department_id = 10
  AND e.is_active
  AND e.monthly_salary >= 2000
ORDER BY e.employee_id;
```

Sau đó so với tổng chi phí gọi function, nếu muốn đánh giá overhead PL/pgSQL và khả năng tối ưu.

### 43.2. EXPLAIN ANALYZE có thể thực thi side effects

`EXPLAIN (ANALYZE)` **thực thi** câu lệnh để đo. Nếu function có DML hoặc side effects, gọi EXPLAIN ANALYZE với function có thể kích hoạt hành vi ấy.

Không tự chạy trên production để “xem plan” nếu function không thuần đọc.

### 43.3. Một lab tám nhân viên không phải performance benchmark

Nếu query nhỏ chọn Seq Scan thay vì index, đó là lựa chọn chi phí bình thường. Chỉ kết luận hiệu năng khi đã thử workload thật hoặc dữ liệu đại diện.

## 44. Hints ROWS và COST cho set-returning functions

Khi planner ước lượng function trong FROM, PostgreSQL có thông tin về:

- `COST`: chi phí ước tính của việc thực thi.
- `ROWS`: số hàng ước tính của function set-returning.

Ví dụ một khai báo:

```sql
ALTER FUNCTION pl358.find_active_employees(
    integer, numeric
)
ROWS 100
COST 100;
```

### 44.1. ROWS không phải LIMIT

`ROWS 100` **không giới hạn** function trả tối đa 100 hàng.

Nó chỉ cung cấp một ước lượng cho planner. Nếu thực tế có 100.000 hàng, function vẫn có thể trả 100.000 hàng.

Muốn giới hạn hàng, phải dùng `LIMIT`/điều kiện trong logic.

### 44.2. Đừng đặt ước lượng theo cảm tính

Sai lệch lớn giữa rows estimate và thực tế có thể khiến planner chọn join order/strategy không phù hợp. Hãy đo trên dữ liệu có phân bố điển hình trước khi thay đổi.

### 44.3. COST cũng không bảo đảm nhanh

Giảm COST metadata không làm function giảm số query, bớt CPU hoặc bớt I/O. Nó thay giả định optimizer dùng để chọn kế hoạch.

## 45. Indexing cho truy vấn được RETURN QUERY sử dụng

Ví dụ query nóng:

```sql
SELECT
    e.employee_id,
    e.full_name,
    e.monthly_salary
FROM pl358.employees AS e
WHERE e.department_id = 10
  AND e.is_active
  AND e.monthly_salary >= 2000
ORDER BY e.employee_id;
```

Nếu bảng lớn, có thể cân nhắc index:

```sql
CREATE INDEX idx_pl358_employees_active_department_salary
ON pl358.employees(
    department_id,
    monthly_salary
)
WHERE is_active;
```

Hoặc index theo sort và workload khác:

```sql
CREATE INDEX idx_pl358_employees_department_id
ON pl358.employees(
    department_id,
    employee_id
);
```

### 45.1. Index nào phù hợp?

- Điều kiện department_id equality.
- is_active thường true/false.
- monthly_salary range.
- ORDER BY employee_id.
- Số hàng mỗi phòng ban.
- Truy vấn có LIMIT hay không.
- Tần suất INSERT/UPDATE salary.

Không có một index hoàn hảo cho mọi cách lọc/sắp xếp. Kiểm tra `EXPLAIN (ANALYZE, BUFFERS)` và trade-off lưu trữ/ghi.

### 45.2. RETURN QUERY không tự index kết quả

Hàm trả bảng ảo cho caller. Nó không tạo index vật lý trên tập kết quả. Index chỉ có trên dữ liệu nguồn hoặc cấu trúc vật lý khác mà bạn chủ động thiết kế.

## 46. Security: function trả tập cũng có thể làm lộ dữ liệu

Một hàm:

```sql
CREATE FUNCTION pl358.all_employees()
RETURNS SETOF pl358.employees
...
```

nếu được cấp quyền gọi rộng và chạy với quyền mạnh có thể trả cả nhân viên ngoài phạm vi mà application dự định cho user thấy.

### 46.1. SECURITY INVOKER và SECURITY DEFINER

- Mặc định function chạy với semantics quyền của invoker.
- `SECURITY DEFINER` chạy với quyền owner theo quy tắc PostgreSQL.

Nếu dùng SECURITY DEFINER, cần đặc biệt kiểm tra:

- Ai được EXECUTE.
- Owner có quyền gì.
- `search_path` có an toàn không.
- Schema và object names có được qualify.
- Function có validate tenant/role scopes.
- RLS policy và quyền owner/bypass có tác động gì.
- Dynamic SQL có injection hoặc identifier không tin cậy không.

### 46.2. RETURN QUERY không tự áp giới hạn quyền nghiệp vụ

Câu query:

```sql
RETURN QUERY SELECT * FROM pl358.employees;
```

không biết ai đang cần chỉ xem phòng ban 10, trừ khi có policy/WHERE/kiểm soát tương ứng.

### 46.3. Không dùng parameter do client tự khai làm quyền

Nếu p_department_id đến từ client, chỉ `WHERE department_id=p_department_id` không tự chứng minh caller có quyền xem phòng ban đó.

Trong hệ thống production, gắn scope với authenticated role/claims đáng tin, và thực thi RLS/authorization đúng.

### 46.4. Trả ít cột cần thiết

Nếu chỉ hiển thị tên và ID, đừng `RETURNS SETOF employee_record` chứa lương/thông tin nhạy cảm chỉ vì tiện.

`RETURNS TABLE(employee_id integer, employee_name text)` thường giúp xác định rõ API được phép công bố, nhưng vẫn phải bảo vệ quyền truy cập hàng.

## 47. RAISE EXCEPTION, RETURN và xử lý lỗi

Một function trả tập có thể cần chặn input không hợp lệ:

```sql
IF p_department_id IS NULL THEN
    RAISE EXCEPTION 'department_id must not be NULL'
        USING ERRCODE = '22023';
END IF;

RETURN QUERY SELECT ...;
RETURN;
```

### 47.1. RETURN; không xử lý exception

Nếu một câu SQL bên trong function lỗi, việc có `RETURN;` sau nó không khiến lỗi tự động được bỏ qua. Execution nhảy theo cơ chế exception và transaction.

### 47.2. EXCEPTION block khi cần

PL/pgSQL có:

```sql
BEGIN
    ...
EXCEPTION
    WHEN unique_violation THEN
        ...
END;
```

Nhưng đừng dùng `WHEN OTHERS THEN RETURN;` để nuốt mọi lỗi rồi báo “không tìm thấy dữ liệu”. Nó có thể che database outage, lỗi schema hoặc bug quyền.

### 47.3. Phân biệt tập rỗng với lỗi

- Không có nhân viên active → trả 0 hàng có thể hợp lý.
- department_id sai kiểu hoặc ngoài phạm vi truy cập → cần xử lý khác.
- Database lỗi → phải báo lỗi/rollback, không giả vờ có 0 hàng.

## 48. Những lỗi hay gặp khi RETURN NEXT/RETURN QUERY

### Lỗi 1 — Dùng RETURN expression trong hàm RETURNS SETOF

Sai:

```sql
RETURNS SETOF integer
...
RETURN v_id;
```

Đúng:

```sql
RETURN NEXT v_id;
RETURN;
```

### Lỗi 2 — Nghĩ RETURN NEXT kết thúc hàm

Nó chỉ bổ sung hàng, code phía sau vẫn chạy.

### Lỗi 3 — Nghĩ RETURN QUERY kết thúc hàm

Nó bổ sung tập hàng; một RETURN QUERY thứ hai vẫn có thể chạy.

### Lỗi 4 — RETURN NEXT có expression trong RETURNS TABLE

Khi RETURNS TABLE tạo OUT parameters, dùng `RETURN NEXT;` không expression sau khi gán output variables.

### Lỗi 5 — Quên gán output variables mỗi vòng

Có thể khiến cột kết quả giữ giá trị từ vòng trước.

### Lỗi 6 — RETURN; trong function scalar bắt buộc trả integer

Không dùng bare RETURN thay RETURN expression cho hàm scalar thông thường.

### Lỗi 7 — Một nhánh IF của scalar function không RETURN

Có thể lỗi “control reached end of function without RETURN”.

### Lỗi 8 — Cho rằng 0 hàng = 1 hàng NULL

Hai trường hợp khác nhau ở SQL và trong JOIN/COUNT.

### Lỗi 9 — count(*) trả bigint nhưng RETURNS TABLE khai báo integer

Runtime row structure mismatch.

### Lỗi 10 — varchar tự động khớp text trong mọi RETURN QUERY

Kiểm tra row descriptor; cast tường minh nếu cần.

### Lỗi 11 — Đảo thứ tự cột output

Cấu trúc trả về cần khớp theo vị trí/kiểu, không dựa vào tên ngầm.

### Lỗi 12 — Dùng tên output giống tên cột SQL không qualify

Có thể gây ambiguous column reference.

### Lỗi 13 — Đọc FOUND quá muộn sau RETURN QUERY

Một câu PERFORM/SELECT INTO/loop tiếp theo có thể đã đổi FOUND.

### Lỗi 14 — Nghĩ RETURN NEXT thiết lập FOUND=true

Không. RETURN NEXT không đặt FOUND theo cách RETURN QUERY làm.

### Lỗi 15 — Dùng RETURN QUERY SELECT ... thay SELECT INTO cho scalar

RETURN QUERY là cơ chế trả tập; SELECT INTO dùng gán biến.

### Lỗi 16 — Dùng dynamic SQL cho mọi parameter value

Không cần nếu chỉ thay giá trị; dùng SQL tĩnh trong RETURN QUERY.

### Lỗi 17 — Ghép input trực tiếp vào RETURN QUERY EXECUTE

Có thể SQL injection; dùng USING và quote/whitelist identifiers.

### Lỗi 18 — Nghĩ RETURN QUERY EXECUTE trả được schema bất kỳ

Return row type vẫn phải tương thích với function declaration.

### Lỗi 19 — Nghĩ RETURN NEXT stream mỗi hàng tới client ngay

PL/pgSQL SRF hiện tích lũy result set trước khi function hoàn tất.

### Lỗi 20 — Đặt LIMIT bên ngoài và nghĩ hàm chỉ tạo chừng ấy hàng

Không bảo đảm. Đẩy giới hạn vào truy vấn trong function.

### Lỗi 21 — Không đặt ORDER BY ở caller khi thứ tự quan trọng

SQL result không có thứ tự mặc định bảo đảm.

### Lỗi 22 — Dùng SETOF record mà caller không khai báo column types

Có thể không xác định được structure; dùng `AS alias(column type, ...)`.

### Lỗi 23 — Không phân biệt function với procedure/trigger

RETURN semantics phụ thuộc loại routine.

### Lỗi 24 — Khai báo IMMUTABLE cho function đọc bảng

Sai volatility có thể làm optimizer đưa giả định không đúng.

### Lỗi 25 — Nghĩ ROWS 100 là giới hạn số hàng

ROWS là ước tính planner, không phải LIMIT.

### Lỗi 26 — Expose SELECT * trong SECURITY DEFINER mà thiếu scope

Có nguy cơ lộ dữ liệu; kiểm soát EXECUTE, RLS, tenant và cột được trả.

### Lỗi 27 — Nuốt exception rồi trả tập rỗng

Làm mất thông tin lỗi, che vấn đề vận hành và hạ độ tin cậy của API.

### Lỗi 28 — Chọn LOOP + RETURN NEXT dù SELECT đã làm được

Có thể làm code dài và khó tối ưu; cân nhắc RETURN QUERY hoặc SQL function.

## 49. Bài tập có đáp án

### Bài 1. Hàm trả integer nên viết gì?

**Đề:** Trả hai lần p_x.

```sql
CREATE FUNCTION pl358.exercise_double(p_x integer)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN p_x * 2;
END;
$$;
```

**Đáp án:** `RETURN expression;` vì chỉ có một scalar result.

### Bài 2. RETURN NEXT có dừng function ngay không?

**Đáp án:** không. Nó thêm một hàng vào tập kết quả rồi tiếp tục chạy statement tiếp theo.

### Bài 3. RETURN QUERY SELECT có cần LOOP không?

**Đáp án:** không. PostgreSQL thêm trực tiếp 0/nhiều hàng từ query.

### Bài 4. Bỏ qua đối số không đồng nghĩa NULL ở đâu?

**Đáp án:** với default input parameters, không truyền sẽ dùng default; explicit NULL vẫn là NULL và có thể làm filter/validation thay đổi.

### Bài 5. RETURN; trong function RETURNS SETOF có tác dụng gì?

**Đáp án:** kết thúc việc tạo tập kết quả, không bổ sung thêm một hàng.

### Bài 6. RETURN; trong RETURNS void?

**Đáp án:** kết thúc function void, không có biểu thức.

### Bài 7. RETURNS TABLE thì RETURN NEXT viết thế nào?

**Đáp án:** gán output variables, sau đó `RETURN NEXT;` không expression.

### Bài 8. RETURNS SETOF integer thì RETURN NEXT thế nào?

```sql
RETURN NEXT v_id;
```

**Đáp án:** truyền một integer tương thích.

### Bài 9. RETURNS SETOF employees có thể RETURN NEXT record không?

**Đáp án:** có, nếu record/row variable có cấu trúc tương thích với composite type `pl358.employees`.

### Bài 10. Một employee active trong phòng 10 có những ID nào?

**Đáp án:** fixture có hai nhân viên active: 101, 102.

### Bài 11. Gọi active_employee_ids cho phòng 40

```sql
SELECT *
FROM pl358.active_employee_ids(40);
```

**Đáp án:** 0 hàng.

### Bài 12. RETURN NEXT NULL::integer tạo bao nhiêu hàng?

**Đáp án:** 1 hàng chứa SQL NULL, không phải tập rỗng.

### Bài 13. RETURN QUERY SELECT ... WHERE false tạo bao nhiêu hàng?

**Đáp án:** 0 hàng.

### Bài 14. RETURN QUERY có thể gọi hai lần không?

**Đáp án:** có; mỗi lần bổ sung những hàng của query vào kết quả; không tự deduplicate.

### Bài 15. Kết hợp RETURN NEXT và RETURN QUERY được không?

**Đáp án:** được trong function `RETURNS SETOF` phù hợp. Phải bảo đảm kiểu dữ liệu tương thích.

### Bài 16. Vì sao gán OUT columns từng vòng quan trọng?

**Đáp án:** giá trị là biến sống trong function; quên gán có thể làm kết quả cột còn giá trị cũ hoặc NULL.

### Bài 17. Lấy nhân viên phòng 20 có lương >=2000

```sql
SELECT *
FROM pl358.find_active_employees(20, 2000);
```

**Đáp án:** Dũng (104), lương 2500.

### Bài 18. Tổng lương active Engineering là bao nhiêu?

**Đáp án:** 2200 + 2900 = 5100.00; Chi inactive không được tính.

### Bài 19. Tổng nhân viên active của Research?

**Đáp án:** 0; LEFT JOIN aggregate trong department_statistics vẫn trả hàng Research.

### Bài 20. Vì sao count(e.employee_id) thay count(*)?

**Đáp án:** với LEFT JOIN không match, COUNT(*) vẫn đếm một hàng bảo tồn; COUNT(non-null-key-bên-phải) trả 0.

### Bài 21. count(*) mặc định thuộc kiểu gì?

**Đáp án:** `bigint`. RETURNS TABLE khai báo integer có thể gây mismatch.

### Bài 22. Chỉnh count(*) để khớp bigint output

```sql
RETURN QUERY
SELECT e.department_id, count(*)
FROM pl358.employees AS e
GROUP BY e.department_id;
```

**Đáp án:** output count column phải là bigint.

### Bài 23. Vì sao column reference ambiguous?

**Đáp án:** output parameter names của RETURNS TABLE cũng là PL/pgSQL variables. Dùng alias bảng `e.employee_id` để loại mơ hồ.

### Bài 24. RETURN QUERY trên VARCHAR nhưng output TEXT?

**Đáp án:** có thể cần `::text` để khớp row type của function.

### Bài 25. Số lượng cột khớp, thứ tự cột sai?

**Đáp án:** vẫn có thể lỗi/nhận sai cấu trúc. Cần SELECT đúng thứ tự và kiểu mỗi cột.

### Bài 26. RETURN QUERY có đặt FOUND không?

**Đáp án:** có, TRUE nếu thêm ít nhất một hàng; FALSE nếu không có hàng.

### Bài 27. RETURN NEXT có đặt FOUND không?

**Đáp án:** không theo cách RETURN QUERY đặt FOUND. Đừng dùng FOUND để đếm hàng của RETURN NEXT.

### Bài 28. Sau RETURN QUERY chạy PERFORM rồi đọc FOUND?

**Đáp án:** FOUND có thể thuộc PERFORM, không còn phản ánh RETURN QUERY. Lưu vào biến ngay sau RETURN QUERY nếu cần.

### Bài 29. SQL động dùng USING cho gì?

**Đáp án:** truyền dữ liệu vào placeholders như `$1`, tránh ghép chuỗi input làm giá trị SQL.

### Bài 30. Động theo tên cột ORDER BY?

**Đáp án:** dùng whitelist tên cột, quote identifier bằng `format('%I',...)` và chỉ lấy hướng ASC/DESC từ danh sách giá trị đáng tin.

### Bài 31. Có nên nối p_name trực tiếp vào WHERE full_name='...' không?

**Đáp án:** không; có nguy cơ injection hoặc lỗi quote. Dùng USING.

### Bài 32. Function trả 10.000 hàng, caller LIMIT 1 thì PL/pgSQL chỉ tạo một hàng?

**Đáp án:** không có bảo đảm. PL/pgSQL SRF materialize kết quả trước khi function hoàn tất; đưa LIMIT vào query trong function.

### Bài 33. ROWS 100 nghĩa là tối đa 100 hàng?

**Đáp án:** không. Đó là estimate planner.

### Bài 34. Function đọc bảng employees nên IMMUTABLE không?

**Đáp án:** không, vì bảng có thể thay đổi. Trong các ví dụ đọc bảng dùng STABLE.

### Bài 35. Hàm có side effect nên dùng volatility nào?

**Đáp án:** thường VOLATILE, tùy semantics chính xác. Không khai báo IMMUTABLE để ép tối ưu.

### Bài 36. Cách JOIN giữ cả phòng Research?

```sql
SELECT d.department_name, s.employee_id
FROM pl358.departments AS d
LEFT JOIN LATERAL
    pl358.find_active_employees(d.department_id) AS s
ON true;
```

**Đáp án:** LEFT JOIN LATERAL bảo tồn phòng không có kết quả.

### Bài 37. CROSS JOIN LATERAL có giữ Research không?

**Đáp án:** không, nếu function trả tập rỗng cho Research.

### Bài 38. Khi nào ưu tiên LANGUAGE sql?

**Đáp án:** khi logic chỉ là SELECT set-based đơn giản, không cần PL/pgSQL procedural control.

### Bài 39. Khi nào dùng EXPLAIN (ANALYZE) cần thận trọng?

**Đáp án:** nó thực thi câu lệnh; function có DML/side effects có thể làm thay đổi dữ liệu thật.

### Bài 40. Hàm SECURITY DEFINER trả nhân viên cần bảo vệ gì?

**Đáp án:** EXECUTE grants, schema/search_path, quyền tenant/role, RLS và các cột nhạy cảm; chỉ dùng dynamic SQL đã kiểm soát.

### Bài 41. RETURN QUERY khác SELECT INTO ở đâu?

**Đáp án:** RETURN QUERY thêm tập hàng vào kết quả function; SELECT INTO gán giá trị/hàng vào biến.

### Bài 42. RETURN QUERY EXECUTE khác EXECUTE INTO?

**Đáp án:** RETURN QUERY EXECUTE thêm hàng từ SQL động vào result set; EXECUTE INTO gán kết quả vào biến.

### Bài 43. Một nhánh scalar function đi tới END không có RETURN?

**Đáp án:** có thể phát sinh lỗi “control reached end of function without RETURN”; bổ sung các đường trả rõ ràng.

### Bài 44. Trong trigger function có nên RETURN NEXT NEW?

**Đáp án:** không. Trigger thường `RETURN NEW`, `RETURN OLD` hoặc `RETURN NULL` theo ngữ nghĩa loại trigger.

### Bài 45. Tập nhân viên cần sắp theo salary DESC có nên chỉ ORDER BY trong RETURN QUERY?

**Đáp án:** query trong function có thể đặt thứ tự để phục vụ LIMIT/logic, nhưng caller cần ORDER BY cuối khi muốn bảo đảm thứ tự hiển thị/truy vấn ngoài.

## 50. Checklist khi viết function PL/pgSQL có RETURN

| Câu hỏi | Điều cần xác minh |
|---|---|
| Hàm trả scalar hay set? | Chọn đúng cú pháp RETURN |
| `RETURNS void` hay có OUT/INOUT? | Khi nào RETURN; không expression |
| Scalar function có mọi nhánh trả giá trị? | Tránh end-of-function error |
| Có chủ động phân biệt NULL/0/lỗi? | Giữ ngữ nghĩa nghiệp vụ |
| SETOF scalar trả đúng type? | RETURN NEXT expr |
| SETOF composite trả đúng row type? | Hàng đủ cột và kiểu |
| RETURNS TABLE đã gán output variables trước RETURN NEXT;? | Tránh giá trị cũ/NULL |
| Có thể thay FOR/RETURN NEXT bằng RETURN QUERY? | Đơn giản hóa set-based |
| RETURN QUERY trả đúng số cột/thứ tự/kiểu? | Tránh structure mismatch |
| Aggregate count(*) output là bigint? | Không vô tình ép integer |
| varchar/text có cần cast? | Kiểm soát row descriptor |
| Có tên output trùng tên cột? | Dùng alias trong SQL |
| Đã hiểu RETURN QUERY không kết thúc hàm? | Không vô tình thêm hàng trùng |
| Có nhiều RETURN QUERY? | Kiểm soát duplicate và business logic |
| FOUND được đọc ngay sau RETURN QUERY? | Không dùng status đã thay đổi |
| RETURN NEXT có được hiểu là streaming không? | PL/pgSQL materializes |
| Có cần giới hạn số hàng trong function? | Đặt LIMIT bên trong |
| Có ORDER BY tại caller khi cần thứ tự? | SQL không mặc định thứ tự |
| SQL động có thật sự cần? | Tránh tăng độ phức tạp |
| Dynamic values được truyền bằng USING? | Chặn SQL injection |
| Identifiers được whitelist/quote đúng? | Chặn sửa cấu trúc truy vấn |
| Có cần tối ưu query nguồn/index? | EXPLAIN trên dữ liệu đại diện |
| ROWS/COST có phản ánh thực tế? | Planner estimates không phải limits |
| Volatility khai báo đúng? | IMMUTABLE/STABLE/VOLATILE |
| Function có side effects? | EXPLAIN ANALYZE và retry cần thận trọng |
| Tập dữ liệu trả có thông tin nhạy cảm? | Grants, tenant, RLS, SECURITY DEFINER |
| Return type là API ổn định? | Migration và compatibility |
| Có test 0/1/nhiều hàng? | Edge cases cơ bản |
| Có test NULL, invalid input, duplicate, empty set? | Data correctness |
| Có test từ SQL client thực tế? | Kiểu bind và quyền caller |
| Có log/metric mà không lộ dữ liệu? | Production observability |

## 51. Tóm tắt theo tình huống

| Tình huống | Cách viết tiêu biểu |
|---|---|
| Trả số nguyên 42 | `RETURN 42;` |
| Scalar trả NULL | `RETURN NULL;` |
| Scalar kiểm tra đầu vào rồi kết thúc | `IF ... THEN RETURN ...; END IF;` |
| Function void kết thúc | `RETURN;` |
| Function có OUT parameters | Gán OUT variables → `RETURN;` |
| SETOF integer thêm một số | `RETURN NEXT v_id;` |
| SETOF composite thêm một record | `RETURN NEXT v_row;` |
| RETURNS TABLE thêm một hàng | Gán output columns → `RETURN NEXT;` |
| RETURNS TABLE thêm hàng từ SELECT | `RETURN QUERY SELECT ...;` |
| Nối nhiều tập kết quả | Nhiều `RETURN QUERY` |
| Nối một hàng đặc biệt | `RETURN NEXT ...;` cùng `RETURN QUERY ...;` |
| Kiểm tra SELECT trong RETURN QUERY có hàng | Đọc `FOUND` ngay sau câu lệnh |
| SQL động có dữ liệu bind | `RETURN QUERY EXECUTE ... USING p_value;` |
| SQL động theo cột | Whitelist + `format('%I', identifier)` |
| Trả tập rỗng ngay | `RETURN;` trong SETOF/RETURNS TABLE |
| Giới hạn hàng hiệu quả | `LIMIT` trong truy vấn của function |
| Không muốn vòng lặp PL/pgSQL | RETURN QUERY hoặc LANGUAGE sql |
| Tham số có default | `p_min_salary numeric DEFAULT 0` |
| Truy vấn hàm theo từng hàng cha | `JOIN LATERAL function(...)` |

## 52. Tài liệu chính thức để tìm hiểu thêm

Đối chiếu với tài liệu phiên bản PostgreSQL bạn đang chạy:

- [PL/pgSQL: Returning From a Function](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-STATEMENTS-RETURNING): `RETURN`, `RETURN NEXT`, `RETURN QUERY` và cách kết thúc.
- [PL/pgSQL: Control Structures](https://www.postgresql.org/docs/current/plpgsql-control-structures.html): `IF`, `FOR`, `EXIT` và điều khiển luồng.
- [PL/pgSQL: Obtaining the Result Status](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-DIAGNOSTICS): `FOUND` và trạng thái thực thi.
- [PL/pgSQL: Executing Dynamic Commands](https://www.postgresql.org/docs/current/plpgsql-statements.html#PLPGSQL-STATEMENTS-EXECUTING-DYN): `EXECUTE`, `USING`, `format`, quoting.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): `RETURNS SETOF`, `RETURNS TABLE`, `COST`, `ROWS`, volatility và security.
- [SQL Functions Returning Sets](https://www.postgresql.org/docs/current/xfunc-sql.html#XFUNC-SQL-FUNCTIONS-RETURNING-SET): so sánh với hàm LANGUAGE sql.
- [Composite Types](https://www.postgresql.org/docs/current/rowtypes.html): cấu trúc các hàng composite.
- [LATERAL Subqueries](https://www.postgresql.org/docs/current/queries-table-expressions.html#QUERIES-LATERAL): kết hợp function trả tập với bảng cha.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): quan sát plan và chi phí thực.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html): cấp quyền an toàn cho function.
- [Function Volatility](https://www.postgresql.org/docs/current/xfunc-volatility.html): IMMUTABLE/STABLE/VOLATILE.

Những đoạn SQL trong bài là **ví dụ lý thuyết và lab học tập**. Việc soạn bài không đồng nghĩa đã chạy các hàm trên một PostgreSQL instance thật; trước khi áp dụng production cần kiểm thử DDL, quyền, kiểu output và dữ liệu đại diện.

## 53. Tổng kết

Ba câu lệnh quan trọng:

```sql
-- Hàm scalar:
RETURN expression;

-- Hàm SETOF / RETURNS TABLE:
RETURN NEXT ...;

-- Hàm SETOF / RETURNS TABLE:
RETURN QUERY SELECT ...;

-- Kết thúc hàm trả tập:
RETURN;
```

Sơ đồ ghi nhớ:

```text
                 Routine cần trả gì?
                        |
            +-----------+-----------+
            |                       |
        Một giá trị             Tập nhiều hàng
            |                       |
      RETURN expr;        +---------+---------+
                          |                   |
                   Từng hàng            Từ SELECT
                          |                   |
                    RETURN NEXT           RETURN QUERY
                          |                   |
                          +---------+---------+
                                    |
                               RETURN;
                                    |
                               Hoàn tất tập
```

Những điều quan trọng nhất:

1. **`RETURN expression` kết thúc hàm scalar ngay.**
2. **`RETURN NEXT` thêm một phần tử/hàng, không kết thúc function.**
3. **`RETURN QUERY` thêm 0 hoặc nhiều hàng của một query, không kết thúc function.**
4. **`RETURN;` không biểu thức kết thúc hàm set-returning hoặc các loại function cho phép dạng ấy.**
5. **`RETURNS TABLE` dùng output variables**: với `RETURN NEXT;`, gán các biến output trước.
6. **`RETURNS SETOF scalar/composite` có thể dùng `RETURN NEXT expression;` với kiểu tương thích.
7. **Kiểu row của RETURN QUERY phải khớp** số cột, thứ tự và kiểu của return declaration.
8. **`count(*)` trả bigint**, không tự khớp integer chỉ vì kết quả nhỏ.
9. **`FOUND` sau RETURN QUERY** phản ánh có hàng hay không; RETURN NEXT không thay FOUND theo cách ấy.
10. **PL/pgSQL set-returning functions materialize kết quả**, không tự stream từng hàng cho client.
11. **`RETURN QUERY EXECUTE` phải dùng `USING` cho giá trị**, whitelist/quote identifier cho phần SQL động.
12. **Với truy vấn set-based đơn giản, ưu tiên RETURN QUERY hoặc LANGUAGE sql** thay loop thủ công.
13. **Kết quả SQL cần ORDER BY ở caller nếu yêu cầu thứ tự**, và LIMIT bên trong function nếu cần giảm lượng hàng được tạo.
14. **Volatility, grants, RLS, SECURITY DEFINER và transaction semantics** vẫn quan trọng dù function chỉ “trả dữ liệu”.

**Một câu để nhớ:** `RETURN` **kết thúc và trả một kết quả**, còn `RETURN NEXT` và `RETURN QUERY` **xây dần một tập kết quả**; chỉ khi luồng hàm kết thúc thì tập ấy mới hoàn tất cho người gọi.


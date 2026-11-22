# `IS NULL`, `IS NOT NULL` và kết quả `UNKNOWN` trong Oracle SQL

## 1. Vì sao cần hiểu `NULL` khi viết câu SELECT?

Một bảng khách hàng có thể chưa có email, một đơn hàng chưa được thanh toán có thể chưa có `paid_at`, hoặc một nhân viên chưa được gán phòng ban. Trong Oracle Database, những trường hợp chưa có giá trị xác định thường được biểu diễn bằng **`NULL`**.

`NULL` tạo ra một khác biệt quan trọng trong truy vấn SQL: nó không phải một giá trị thông thường để so sánh bằng `=` hoặc `<>`. Khi một phép so sánh có toán hạng là `NULL`, kết quả thường là **`UNKNOWN`**. Vì thế, các câu lệnh sau không có cùng ý nghĩa:

```sql
-- Sai nếu mục đích là tìm các hàng có email NULL:
SELECT customer_id, email
FROM customers
WHERE email = NULL;

-- Đúng:
SELECT customer_id, email
FROM customers
WHERE email IS NULL;
```

Tương tự, muốn tìm hàng có giá trị thì dùng `IS NOT NULL`, không dùng `<> NULL`.

Trong bài học thuộc chương **SELECT cơ bản**, bạn sẽ nắm được:

- `NULL` biểu thị điều gì và khác `0`, dấu cách hoặc chuỗi thông thường ra sao.
- Cách dùng `IS NULL` và `IS NOT NULL`.
- Vì sao SQL có ba kết quả logic `TRUE`, `FALSE`, `UNKNOWN`.
- `WHERE`, `HAVING`, `CASE`, `AND`, `OR`, `NOT` xử lý `UNKNOWN` thế nào.
- Những bẫy phổ biến với `NOT IN`, `JOIN`, hàm tổng hợp và điều kiện tùy chọn.
- Cách viết truy vấn rõ ràng khi tham số đầu vào của ứng dụng Java có thể là `null`.

Các ví dụ dùng `DUAL` hoặc bảng minh họa. Nếu tên bảng như `CUSTOMERS`, `ORDERS`, `EMPLOYEES` chưa tồn tại trong schema thực hành của bạn, hãy thay bằng bảng tương ứng mà bạn có quyền đọc.

## 2. `NULL` có nghĩa là chưa có giá trị xác định

`NULL` có thể biểu thị dữ liệu chưa được cung cấp, chưa biết, chưa áp dụng hoặc chưa được xác định. Ý nghĩa nghiệp vụ cụ thể phụ thuộc từng cột.

| Dữ liệu | Ví dụ | Ý nghĩa có thể có |
|---|---|---|
| Số tiền thanh toán | `paid_amount = NULL` | Chưa ghi nhận số tiền thanh toán |
| Ngày hoàn thành | `completed_at = NULL` | Công việc chưa hoàn thành hoặc chưa ghi nhận thời điểm |
| Email | `email = NULL` | Người dùng chưa cung cấp email |
| Mã phòng ban | `department_id = NULL` | Nhân viên chưa được gán phòng ban |
| Số lượng | `quantity = 0` | Số lượng đã xác định là không |

**`NULL` không đồng nghĩa với 0.** Số 0 là một giá trị số cụ thể, còn NULL biểu thị chưa có giá trị xác định.

### 2.1. Phân biệt NULL, 0 và dấu cách

```sql
SELECT CASE WHEN CAST(NULL AS NUMBER) IS NULL
            THEN 'NULL' ELSE 'NOT NULL' END AS null_value,
       CASE WHEN 0 IS NULL
            THEN 'NULL' ELSE 'NOT NULL' END AS zero_value,
       CASE WHEN ' ' IS NULL
            THEN 'NULL' ELSE 'NOT NULL' END AS space_value
FROM dual;
```

Ý nghĩa kết quả:

- `CAST(NULL AS NUMBER)` là NULL.
- `0` là một số có giá trị.
- `' '` là chuỗi chứa một dấu cách, không phải NULL.

Trong Oracle, chuỗi ký tự có độ dài bằng không `''` được xử lý như NULL theo hành vi hiện hành của các kiểu ký tự thông thường. Vì vậy:

```sql
SELECT CASE WHEN '' IS NULL THEN 'IS NULL'
            ELSE 'NOT NULL' END AS empty_string,
       CASE WHEN ' ' IS NULL THEN 'IS NULL'
            ELSE 'NOT NULL' END AS one_space
FROM dual;
```

Chuỗi rỗng và chuỗi gồm một dấu cách không giống nhau. Nếu ứng dụng coi chuỗi chỉ có khoảng trắng là dữ liệu chưa nhập, cần chủ động chuẩn hóa hoặc kiểm tra bằng `TRIM`; Oracle không tự coi mọi chuỗi dấu cách là NULL.

### 2.2. NULL có thể xuất hiện ở đâu?

Một giá trị NULL có thể đến từ:

- Cột cho phép NULL và lệnh `INSERT` không truyền giá trị.
- Lệnh `UPDATE` đặt cột về NULL.
- Kết quả của một biểu thức hoặc hàm không xác định được giá trị.
- Phép nối ngoài (`OUTER JOIN`) không tìm được hàng tương ứng ở phía còn lại.
- Hàm tổng hợp hoặc scalar subquery trong một số trường hợp không có giá trị đầu vào/kết quả.

Do đó, khi thấy NULL trong kết quả SELECT, không thể luôn kết luận rằng bản ghi gốc lưu NULL. Nó cũng có thể được sinh ra bởi cách truy vấn kết hợp dữ liệu.

## 3. Cách kiểm tra NULL: `IS NULL` và `IS NOT NULL`

### 3.1. Tìm hàng có giá trị NULL

Cú pháp:

```sql
expression IS NULL
```

Ví dụ:

```sql
SELECT customer_id, customer_name, email
FROM customers
WHERE email IS NULL;
```

Truy vấn trả về những khách hàng có cột `EMAIL` đang là NULL.

### 3.2. Tìm hàng không NULL

Cú pháp:

```sql
expression IS NOT NULL
```

Ví dụ:

```sql
SELECT customer_id, customer_name, email
FROM customers
WHERE email IS NOT NULL;
```

Truy vấn chỉ trả về những khách hàng có giá trị email khác NULL. Điều này **không tự đảm bảo email đúng định dạng**; một chuỗi dấu cách vẫn có thể là non-NULL.

### 3.3. Có thể kiểm tra nhiều cột trong cùng một WHERE

```sql
SELECT employee_id, first_name, phone_number, commission_pct
FROM employees
WHERE phone_number IS NULL
  AND commission_pct IS NOT NULL;
```

Ví dụ này tìm nhân viên chưa có số điện thoại nhưng có tỷ lệ hoa hồng được ghi nhận. Điều kiện `IS NULL` và `IS NOT NULL` cho kết quả xác định TRUE hoặc FALSE, nên có thể kết hợp bằng `AND`, `OR`, `NOT` một cách trực tiếp.

### 3.4. Không dùng `= NULL` hoặc `<> NULL`

| Viết | Kết quả khi cột là NULL | Cách dùng đúng |
|---|---|---|
| `email = NULL` | `UNKNOWN` | `email IS NULL` |
| `email <> NULL` | `UNKNOWN` | `email IS NOT NULL` |
| `email != NULL` | `UNKNOWN` | `email IS NOT NULL` |
| `email IS NULL` | `TRUE` nếu email NULL | Đúng |
| `email IS NOT NULL` | `TRUE` nếu email khác NULL | Đúng |

Lỗi thường gặp là câu SQL chạy mà không báo lỗi cú pháp, nhưng kết quả không có hàng nào. `WHERE email = NULL` là một ví dụ: câu truy vấn hợp lệ về cú pháp, song điều kiện không trở thành TRUE cho cả hàng có email NULL.

## 4. Logic ba giá trị: TRUE, FALSE và UNKNOWN

Trong logic thông thường, một biểu thức chỉ có thể TRUE hoặc FALSE. SQL bổ sung **UNKNOWN** để biểu diễn trường hợp chưa thể xác định đúng hay sai, thường do có NULL tham gia phép tính hoặc so sánh.

Ví dụ:

```sql
SELECT CASE WHEN 10 > 5 THEN 'TRUE'
            ELSE 'NOT TRUE' END AS known_true,
       CASE WHEN 10 < 5 THEN 'TRUE'
            ELSE 'NOT TRUE' END AS known_false,
       CASE WHEN CAST(NULL AS NUMBER) > 5 THEN 'TRUE'
            ELSE 'NOT TRUE' END AS unknown_result
FROM dual;
```

Kết quả nhánh `ELSE` ở cột cuối không có nghĩa phép so sánh là FALSE. Nó có thể là UNKNOWN. `CASE WHEN` chỉ chọn nhánh `THEN` khi điều kiện TRUE.

### 4.1. So sánh có NULL thường cho UNKNOWN

| Biểu thức | Kết quả |
|---|---|
| `5 = 5` | `TRUE` |
| `5 = 6` | `FALSE` |
| `5 = NULL` | `UNKNOWN` |
| `NULL = NULL` | `UNKNOWN` |
| `5 <> NULL` | `UNKNOWN` |
| `NULL > 0` | `UNKNOWN` |
| `NULL LIKE 'A%'` | `UNKNOWN` |
| `NULL BETWEEN 1 AND 10` | `UNKNOWN` |
| `NULL IS NULL` | `TRUE` |
| `NULL IS NOT NULL` | `FALSE` |

Điểm đặc biệt: `NULL IS NULL` là một phép kiểm tra trạng thái NULL, không phải phép so sánh hai giá trị NULL bằng toán tử `=`.

### 4.2. Bảng chân trị của AND

| A | B | `A AND B` |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE |
| TRUE | UNKNOWN | UNKNOWN |
| FALSE | TRUE | FALSE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE |
| UNKNOWN | TRUE | UNKNOWN |
| UNKNOWN | FALSE | FALSE |
| UNKNOWN | UNKNOWN | UNKNOWN |

Chỉ cần một vế FALSE là toàn bộ phép AND FALSE, kể cả vế còn lại UNKNOWN.

### 4.3. Bảng chân trị của OR

| A | B | `A OR B` |
|---|---|---|
| TRUE | TRUE | TRUE |
| TRUE | FALSE | TRUE |
| TRUE | UNKNOWN | TRUE |
| FALSE | TRUE | TRUE |
| FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | UNKNOWN |
| UNKNOWN | TRUE | TRUE |
| UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN |

Chỉ cần một vế TRUE là toàn bộ phép OR TRUE, kể cả vế còn lại UNKNOWN.

### 4.4. NOT UNKNOWN vẫn là UNKNOWN

| A | `NOT A` |
|---|---|
| TRUE | FALSE |
| FALSE | TRUE |
| UNKNOWN | UNKNOWN |

Đây là nguyên nhân `NOT (salary > 10000)` không tự chọn những hàng có `salary IS NULL`. Nếu `salary > 10000` là UNKNOWN, phủ định nó vẫn UNKNOWN.

## 5. WHERE xử lý UNKNOWN như thế nào?

Trong câu SELECT, mệnh đề `WHERE` chỉ giữ lại hàng có điều kiện là **TRUE**. Hàng có điều kiện FALSE hoặc UNKNOWN đều bị loại khỏi kết quả.

Ví dụ bảng minh họa:

| employee_id | salary |
|---:|---:|
| 101 | 12000 |
| 102 | 8000 |
| 103 | NULL |

Chạy:

```sql
SELECT employee_id, salary
FROM employees
WHERE salary > 10000;
```

Đánh giá từng hàng:

| employee_id | Biểu thức | Kết quả | Có xuất hiện? |
|---:|---|---|---|
| 101 | `12000 > 10000` | TRUE | Có |
| 102 | `8000 > 10000` | FALSE | Không |
| 103 | `NULL > 10000` | UNKNOWN | Không |

Nếu yêu cầu nghiệp vụ là “lấy nhân viên có lương không vượt quá 10.000 **hoặc chưa có lương**”, phải viết rõ:

```sql
SELECT employee_id, salary
FROM employees
WHERE salary <= 10000
   OR salary IS NULL;
```

Không viết:

```sql
-- Không tương đương với điều kiện trên:
WHERE NOT (salary > 10000)
```

Với hàng salary NULL, biểu thức bên trong là UNKNOWN; `NOT UNKNOWN` vẫn UNKNOWN nên hàng bị loại.

### 5.1. Điều kiện phủ định cần nghĩ đến NULL

Ví dụ muốn lấy đơn hàng chưa có trạng thái `CANCELLED`:

```sql
SELECT order_id, status
FROM orders
WHERE status <> 'CANCELLED';
```

Truy vấn này **không** lấy các hàng `status IS NULL`, vì `NULL <> 'CANCELLED'` là UNKNOWN. Nếu yêu cầu bao gồm cả trạng thái chưa biết:

```sql
SELECT order_id, status
FROM orders
WHERE status <> 'CANCELLED'
   OR status IS NULL;
```

Tuy nhiên, hãy xác nhận ý nghĩa nghiệp vụ. Nếu NULL có nghĩa “chưa xác minh trạng thái”, việc gộp vào nhóm “không bị hủy” có thể làm báo cáo sai. Cú pháp SQL đúng chưa đủ; cần định nghĩa đúng cách phân loại dữ liệu thiếu.

### 5.2. AND và OR khi một cột nullable

```sql
SELECT employee_id, salary, commission_pct
FROM employees
WHERE salary > 5000
  AND commission_pct > 0.1;
```

Nếu `commission_pct` NULL, điều kiện thứ hai UNKNOWN. `TRUE AND UNKNOWN` là UNKNOWN nên hàng không được chọn.

Trong trường hợp muốn lấy người có lương trên 5.000 và **hoa hồng lớn hơn 10% hoặc chưa xác định hoa hồng**, cần viết:

```sql
SELECT employee_id, salary, commission_pct
FROM employees
WHERE salary > 5000
  AND (commission_pct > 0.1 OR commission_pct IS NULL);
```

Hãy dùng ngoặc để diễn đạt nhóm điều kiện rõ ràng. `AND` có độ ưu tiên cao hơn `OR`; thiếu ngoặc có thể làm truy vấn chọn thêm hàng ngoài dự kiến.

## 6. UNKNOWN trong CASE và biểu thức điều kiện

### 6.1. Searched CASE

`CASE WHEN` chỉ coi điều kiện TRUE là khớp:

```sql
SELECT employee_id,
       CASE
           WHEN salary > 10000 THEN 'HIGH'
           WHEN salary <= 10000 THEN 'NORMAL'
           ELSE 'UNKNOWN_OR_OTHER'
       END AS salary_group
FROM employees;
```

Với `salary IS NULL`, cả hai phép so sánh đều UNKNOWN, nên không nhánh `WHEN` nào được chọn và `ELSE` được dùng.

Nếu muốn tách NULL thành nhóm riêng, nên viết tường minh:

```sql
SELECT employee_id,
       CASE
           WHEN salary IS NULL THEN 'NOT_RECORDED'
           WHEN salary > 10000 THEN 'HIGH'
           ELSE 'NORMAL'
       END AS salary_group
FROM employees;
```

Thứ tự nhánh rất quan trọng: kiểm tra NULL trước giúp biểu đạt rõ ý định và tránh dùng một phép so sánh không xác định để phân loại.

### 6.2. Simple CASE không phải cách kiểm tra NULL

Không nên viết:

```sql
CASE email
    WHEN NULL THEN 'MISSING'
    ELSE 'PRESENT'
END
```

Simple CASE so sánh biểu thức với từng giá trị `WHEN` theo ngữ nghĩa so sánh; `email = NULL` là UNKNOWN nên nhánh `WHEN NULL` không khớp như mong muốn.

Dùng searched CASE:

```sql
CASE
    WHEN email IS NULL THEN 'MISSING'
    ELSE 'PRESENT'
END
```

### 6.3. NVL, COALESCE và NULLIF

Các hàm xử lý NULL có thể hữu ích trong SELECT:

```sql
SELECT employee_id,
       NVL(commission_pct, 0) AS commission_display,
       COALESCE(phone_number, email, 'NO_CONTACT') AS contact_display
FROM employees;
```

- `NVL(expr1, expr2)` trả `expr2` khi `expr1` là NULL; nếu không trả `expr1`.
- `COALESCE(expr1, expr2, ...)` trả biểu thức đầu tiên khác NULL.
- `NULLIF(expr1, expr2)` trả NULL nếu hai biểu thức bằng nhau; nếu khác nhau trả `expr1`.

Ví dụ `NULLIF`:

```sql
SELECT NULLIF(0, 0) AS result_value,
       NULLIF(5, 0) AS second_value
FROM dual;
```

Kết quả về ý nghĩa: biểu thức đầu trả NULL, biểu thức thứ hai trả 5.

**Cẩn thận khi dùng NVL để lọc:** `NVL(salary, 0) > 10000` không giống `salary > 10000 OR salary IS NULL`; biểu thức đầu thay NULL bằng 0 nên hàng NULL bị loại. Chỉ thay thế NULL bằng giá trị mặc định khi điều đó đúng với ý nghĩa nghiệp vụ.

## 7. Bẫy `NOT IN` khi danh sách có NULL

Đây là một trong những lỗi SQL phổ biến nhất.

### 7.1. `IN` và NULL

Giả sử:

```sql
SELECT 20 IN (10, 20, NULL) AS result
FROM dual;
```

Vì có một phần tử bằng 20, biểu thức IN là TRUE.

Nhưng:

```sql
SELECT 30 IN (10, 20, NULL) AS result
FROM dual;
```

Không có phần tử nào bằng 30, nhưng phép so sánh với NULL tạo UNKNOWN. Kết quả tổng thể là UNKNOWN, không phải FALSE.

### 7.2. Vì sao NOT IN có thể trả về 0 hàng?

Ví dụ:

```sql
SELECT employee_id
FROM employees
WHERE department_id NOT IN (10, 20, NULL);
```

Với một `department_id` bằng 30, Oracle phải đánh giá tương đương:

```text
30 <> 10 AND 30 <> 20 AND 30 <> NULL
TRUE     AND TRUE     AND UNKNOWN
                       |
                       v
                    UNKNOWN
```

Kết quả là UNKNOWN, nên WHERE loại hàng đó. Những hàng có `department_id` NULL cũng không được chọn. Vì vậy, chỉ cần danh sách NOT IN chứa NULL, các giá trị không khớp có thể không được trả về như bạn dự đoán.

### 7.3. Cách khắc phục

Nếu danh sách đến từ bảng con, hãy lọc NULL khỏi tập kết quả:

```sql
SELECT e.employee_id
FROM employees e
WHERE e.department_id NOT IN (
    SELECT d.department_id
    FROM blocked_departments d
    WHERE d.department_id IS NOT NULL
);
```

Một cách thường rõ ràng hơn là dùng `NOT EXISTS`:

```sql
SELECT e.employee_id
FROM employees e
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_departments d
    WHERE d.department_id = e.department_id
);
```

`NOT EXISTS` kiểm tra không có hàng con thỏa điều kiện tương quan. Nó tránh bẫy NULL trong tập con của `NOT IN`. Tuy nhiên, nếu `e.department_id` của hàng ngoài là NULL, phép so sánh tương quan cũng không TRUE cho hàng nào; `NOT EXISTS` khi đó có thể trả TRUE. Nếu nghiệp vụ không muốn lấy nhân viên chưa có phòng ban, thêm:

```sql
AND e.department_id IS NOT NULL
```

Hãy quyết định riêng cách xử lý NULL ở **tập dữ liệu ngoài** và **tập dữ liệu con**.

## 8. NULL với hàm tổng hợp

Các hàm tổng hợp thường bỏ qua giá trị NULL ở biểu thức được tổng hợp, nhưng `COUNT(*)` đếm mọi hàng.

| Biểu thức | Cách xử lý NULL |
|---|---|
| `COUNT(*)` | Đếm tất cả hàng, kể cả hàng có cột NULL |
| `COUNT(column)` | Chỉ đếm hàng mà `column` khác NULL |
| `SUM(column)` | Bỏ qua NULL; nếu không có giá trị non-NULL thì kết quả NULL |
| `AVG(column)` | Bỏ qua NULL khi tính trung bình |
| `MIN(column)`, `MAX(column)` | Bỏ qua NULL khi tìm min/max |

Ví dụ với bảng `EMPLOYEES`:

```sql
SELECT COUNT(*) AS total_employees,
       COUNT(commission_pct) AS employees_with_commission,
       AVG(commission_pct) AS average_commission
FROM employees;
```

`COUNT(*)` đếm toàn bộ nhân viên; `COUNT(commission_pct)` chỉ đếm nhân viên có tỷ lệ hoa hồng đã ghi nhận. Nếu một nửa số nhân viên chưa có hoa hồng, `AVG` không coi họ là 0; nó tính trên các giá trị khác NULL.

### 8.1. NULL không tự được xem là 0 trong SUM/AVG

Giả sử có ba giá trị:

```text
10, 20, NULL
```

Kết quả:

- `SUM(value)` = 30.
- `AVG(value)` = 15.
- `COUNT(value)` = 2.
- `COUNT(*)` = 3.

Nếu nghiệp vụ muốn xem giá trị thiếu như 0, phải thể hiện rõ:

```sql
SELECT AVG(NVL(commission_pct, 0)) AS average_with_missing_as_zero
FROM employees;
```

Đây là **một cách tính khác** với `AVG(commission_pct)`. Không nên thay NULL bằng 0 chỉ để tránh kết quả NULL mà chưa xác định ý nghĩa thống kê.

### 8.2. SUM trên tập rỗng hoặc toàn NULL

```sql
SELECT COUNT(*) AS row_count,
       COUNT(CAST(NULL AS NUMBER)) AS non_null_count,
       SUM(CAST(NULL AS NUMBER)) AS total_value
FROM dual
WHERE 1 = 0;
```

Truy vấn không có hàng đầu vào: `COUNT(*)` trả 0, `COUNT(expr)` trả 0, còn `SUM(expr)` trả NULL. Tương tự, nếu có hàng nhưng tất cả giá trị trong biểu thức SUM đều NULL, tổng cũng có thể là NULL.

Nếu muốn hiển thị 0 thay cho tổng NULL:

```sql
SELECT NVL(SUM(amount), 0) AS total_amount
FROM payments;
```

Chỉ dùng cách này khi “không có khoản thanh toán được ghi nhận” thực sự cần hiển thị như tổng bằng 0. Trong báo cáo, NULL đôi khi mang ý nghĩa “chưa có dữ liệu”, còn 0 mang ý nghĩa “đã xác định tổng bằng không”.

### 8.3. GROUP BY và NULL

`GROUP BY` gom các hàng có giá trị NULL của cùng một biểu thức vào một nhóm:

```sql
SELECT department_id,
       COUNT(*) AS employee_count
FROM employees
GROUP BY department_id
ORDER BY department_id NULLS LAST;
```

Kết quả có thể có một nhóm `DEPARTMENT_ID` NULL chứa những nhân viên chưa được gán phòng ban. Điều này không mâu thuẫn với việc `department_id = NULL` là UNKNOWN: `GROUP BY` phân nhóm giá trị thiếu theo quy tắc riêng, không dùng phép so sánh `= NULL` để lọc.

## 9. NULL trong JOIN

### 9.1. Điều kiện JOIN bằng nhau không ghép hai NULL

Giả sử bảng nhân viên có `department_id` NULL và bảng phòng ban cũng có một hàng `department_id` NULL. Với phép nối:

```sql
SELECT e.employee_id, d.department_name
FROM employees e
JOIN departments d
  ON e.department_id = d.department_id;
```

Hàng có `e.department_id` NULL không khớp hàng `d.department_id` NULL, vì `NULL = NULL` là UNKNOWN chứ không TRUE.

Nếu nghiệp vụ muốn xem hai NULL là cùng một nhóm để nối, phải viết quy tắc null-safe riêng, ví dụ:

```sql
ON (
       e.department_id = d.department_id
    OR (e.department_id IS NULL AND d.department_id IS NULL)
)
```

Nhưng cần cân nhắc: nếu bảng `DEPARTMENTS` có nhiều hàng NULL, phép nối trên có thể làm một nhân viên NULL khớp với nhiều hàng và nhân bản kết quả. Thông thường, NULL trong khóa tham chiếu mang nghĩa “không có phòng ban”, không nên tự ghép tất cả các hàng NULL với nhau.

### 9.2. OUTER JOIN sinh NULL ở phía không khớp

```sql
SELECT e.employee_id,
       e.department_id,
       d.department_name
FROM employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id;
```

Nếu nhân viên không có phòng ban phù hợp, các cột lấy từ `d` được trả về là NULL. Có hai nguyên nhân khác nhau:

1. `e.department_id` thực sự NULL.
2. `e.department_id` có giá trị nhưng không có hàng tương ứng trong `departments` (nếu dữ liệu hoặc quan hệ cho phép trường hợp này).

Muốn tìm nhân viên không có hàng phòng ban tương ứng, có thể kiểm tra một cột khóa của bảng phải luôn non-NULL khi hàng tồn tại:

```sql
SELECT e.employee_id
FROM employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id
WHERE d.department_id IS NULL;
```

Nếu `d.department_id` là khóa chính nên không NULL, phép kiểm tra này phát hiện hàng không match. Nhưng kết quả có thể bao gồm cả nhân viên có `e.department_id` NULL; nếu cần tách riêng hai trường hợp, kiểm tra thêm cột ở bảng `e`.

### 9.3. Cẩn thận khi đặt điều kiện bảng phải trong WHERE

So sánh:

```sql
-- LEFT JOIN nhưng điều kiện WHERE loại hàng không match:
SELECT e.employee_id, d.department_name
FROM employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id
WHERE d.status = 'ACTIVE';
```

Hàng không match có `d.status` NULL; `NULL = 'ACTIVE'` là UNKNOWN nên bị WHERE loại. Truy vấn có thể hoạt động giống INNER JOIN đối với điều kiện đó.

Nếu muốn giữ mọi nhân viên và chỉ ghép thông tin phòng ban đang ACTIVE:

```sql
SELECT e.employee_id, d.department_name
FROM employees e
LEFT JOIN departments d
  ON d.department_id = e.department_id
 AND d.status = 'ACTIVE';
```

Điều kiện lọc hàng phía phải được đưa vào `ON` khi mục đích là vẫn giữ hàng trái không có đối tượng phù hợp.

## 10. NULL với BETWEEN, LIKE, IN và các phép toán

NULL có thể làm UNKNOWN trong nhiều dạng điều kiện, không chỉ toán tử `=`:

```sql
-- Nếu salary NULL, điều kiện BETWEEN là UNKNOWN.
WHERE salary BETWEEN 5000 AND 10000

-- Nếu name NULL, điều kiện LIKE là UNKNOWN.
WHERE customer_name LIKE 'A%'

-- Nếu order_date NULL, điều kiện so sánh ngày là UNKNOWN.
WHERE order_date >= DATE '2026-01-01'

-- Nếu amount NULL, phép cộng tạo NULL.
SELECT amount + 100 FROM payments;
```

### 10.1. BETWEEN

```sql
SELECT product_id, price
FROM products
WHERE price BETWEEN 100 AND 500;
```

`BETWEEN` tương đương về ý nghĩa với `price >= 100 AND price <= 500`. Nếu `price` NULL, cả hai so sánh là UNKNOWN; hàng bị loại khỏi WHERE.

### 10.2. LIKE

```sql
SELECT customer_id, customer_name
FROM customers
WHERE customer_name LIKE 'Ng%';
```

Tên NULL không khớp pattern và điều kiện là UNKNOWN. Nếu muốn hiển thị các hàng thiếu tên bên cạnh những tên bắt đầu bằng `Ng`, thêm `OR customer_name IS NULL`.

### 10.3. IN và NOT IN

```sql
WHERE status IN ('NEW', 'PAID')
```

Hàng status NULL bị loại vì kết quả UNKNOWN. Với `NOT IN`, cần đặc biệt kiểm tra danh sách có chứa NULL hay không, như phần 7 đã giải thích.

### 10.4. Phép toán số học

```sql
SELECT amount + tax AS total
FROM invoice_lines;
```

Nếu `amount` hoặc `tax` NULL, kết quả phép cộng thông thường là NULL. Muốn xem NULL như 0:

```sql
SELECT NVL(amount, 0) + NVL(tax, 0) AS total
FROM invoice_lines;
```

Đây là quyết định nghiệp vụ. Nếu NULL có nghĩa “chưa tính thuế”, thay bằng 0 có thể khiến báo cáo thể hiện sai rằng tổng đã được tính hoàn chỉnh.

## 11. ORDER BY và cách đặt NULL ở đầu/cuối

Oracle cho phép chỉ định vị trí của NULL khi sắp xếp:

```sql
SELECT employee_id, commission_pct
FROM employees
ORDER BY commission_pct ASC NULLS LAST;
```

Hoặc:

```sql
SELECT employee_id, commission_pct
FROM employees
ORDER BY commission_pct DESC NULLS FIRST;
```

Nếu không ghi rõ:

- `ASC` mặc định đặt NULL **sau** các giá trị khác (`NULLS LAST`).
- `DESC` mặc định đặt NULL **trước** các giá trị khác (`NULLS FIRST`).

Nên chỉ định `NULLS FIRST` hoặc `NULLS LAST` khi vị trí NULL có ý nghĩa với báo cáo, để tránh phụ thuộc vào mặc định và giúp người đọc hiểu ý định.

## 12. Kiểm tra NULL trong ứng dụng Java/JDBC

Một lỗi thường gặp là backend truyền Java `null` vào bind parameter rồi mong câu:

```sql
SELECT *
FROM customers
WHERE email = ?
```

trả về những hàng có `EMAIL IS NULL`. Điều đó không xảy ra: khi tham số bind là SQL NULL, phép so sánh `email = NULL` là UNKNOWN.

### 12.1. Nếu muốn tìm hàng NULL, dùng IS NULL

Nếu ứng dụng đã biết cần tìm email NULL:

```sql
SELECT customer_id, email
FROM customers
WHERE email IS NULL;
```

Không cần bind giá trị NULL cho phép `=`.

### 12.2. Nếu muốn tìm email bằng giá trị truyền vào, kể cả NULL

Một phương án là chọn câu SQL theo trạng thái tham số:

```java
String sql;

if (email == null) {
    sql = "SELECT customer_id, email FROM customers WHERE email IS NULL";
} else {
    sql = "SELECT customer_id, email FROM customers WHERE email = ?";
}

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    if (email != null) {
        ps.setString(1, email);
    }

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Xử lý hàng.
        }
    }
}
```

Đoạn code minh họa ý tưởng; giả định `connection`, `email` và transaction đã được quản lý. Giá trị không bao giờ được nối trực tiếp vào SQL.

Một cách SQL có thể diễn đạt null-safe equality:

```sql
WHERE email = :p_email
   OR (email IS NULL AND :p_email IS NULL)
```

Nếu `:p_email` là NULL, nhánh đầu UNKNOWN nhưng nhánh sau TRUE khi cột cũng NULL; nếu tham số có giá trị, phép so sánh thông thường được dùng. Trong JDBC chuẩn, placeholder thường là `?`, và bạn cần bind tham số tương ứng cho từng vị trí; việc viết hai placeholder có thể cần bind cùng giá trị hai lần.

### 12.3. Phân biệt “tham số NULL nghĩa là bỏ qua bộ lọc”

Một pattern khác:

```sql
WHERE (:p_email IS NULL OR email = :p_email)
```

Nó thường được dùng cho bộ lọc tùy chọn:

- Nếu `:p_email` NULL, vế đầu TRUE nên **không lọc theo email**.
- Nếu `:p_email` có giá trị, truy vấn lọc email bằng giá trị đó.

Đây **không phải** null-safe equality. Nó không có nghĩa “nếu tham số NULL thì tìm các hàng email NULL”; nó có nghĩa “nếu tham số NULL thì bỏ qua điều kiện email”.

Hai yêu cầu khác nhau:

| Ý định | Cách diễn đạt |
|---|---|
| Tham số NULL nghĩa là tìm hàng có cột NULL | `email IS NULL` hoặc null-safe equality |
| Tham số NULL nghĩa là không áp dụng bộ lọc | `:p_email IS NULL OR email = :p_email` |
| Tham số có giá trị thì tìm đúng giá trị | `email = :p_email` |

Đặt tên tham số và mô tả API rõ ràng để tránh việc frontend gửi NULL nhưng backend diễn giải nhầm ý nghĩa.

### 12.4. JDBC setNull và String rỗng

```java
if (email == null) {
    ps.setNull(1, java.sql.Types.VARCHAR);
} else {
    ps.setString(1, email);
}
```

`setNull` truyền giá trị SQL NULL. Chuỗi `"null"` là bốn ký tự bình thường; chuỗi `""` trong Oracle được xử lý như NULL theo hành vi hiện hành của kiểu ký tự thông thường. Nếu API cần phân biệt “không gửi field”, “gửi chuỗi rỗng” và “gửi NULL”, cần thiết kế quy ước ở tầng JSON/Java và xử lý rõ trước khi ghi database.

## 13. Một số cách kiểm tra NULL và giá trị thay thế

### 13.1. Kiểm tra một cột

```sql
SELECT COUNT(*) AS all_rows,
       COUNT(email) AS rows_with_email
FROM customers;
```

Hiệu số giữa hai kết quả cho biết số hàng có `email` NULL trong cùng tập dữ liệu, nếu không có điều kiện lọc khác.

### 13.2. Đếm riêng NULL và non-NULL

```sql
SELECT SUM(CASE WHEN email IS NULL THEN 1 ELSE 0 END) AS null_count,
       SUM(CASE WHEN email IS NOT NULL THEN 1 ELSE 0 END) AS not_null_count
FROM customers;
```

Hoặc:

```sql
SELECT
    COUNT(*) - COUNT(email) AS null_count,
    COUNT(email) AS not_null_count
FROM customers;
```

### 13.3. Tìm giá trị rỗng theo quy tắc Oracle

Vì `''` được xử lý như NULL đối với kiểu ký tự thông thường, có thể dùng:

```sql
SELECT customer_id
FROM customers
WHERE email IS NULL;
```

Nếu cần tìm chuỗi chỉ có khoảng trắng:

```sql
SELECT customer_id, email
FROM customers
WHERE email IS NOT NULL
  AND TRIM(email) IS NULL;
```

`TRIM(email)` trả NULL khi kết quả chỉ còn chuỗi rỗng sau khi loại khoảng trắng mặc định. Nếu muốn giữ hoặc loại những loại whitespace Unicode khác, cần định nghĩa quy tắc chuẩn hóa cụ thể; `TRIM` mặc định không phải bộ làm sạch mọi ký tự khoảng trắng.

### 13.4. NVL trong SELECT để dễ đọc

```sql
SELECT customer_id,
       NVL(email, '(chua cung cap)') AS email_display
FROM customers;
```

Đây là thay thế **chỉ cho kết quả hiển thị**. Cột gốc trong bảng vẫn là NULL; truy vấn không ghi giá trị mặc định vào dữ liệu.

## 14. Hiệu năng và index khi dùng IS NULL / IS NOT NULL

`IS NULL` và `IS NOT NULL` là điều kiện SQL bình thường; Oracle có thể chọn full table scan hoặc index access tùy thống kê, độ chọn lọc, loại index và kế hoạch thực thi.

Một điểm đáng chú ý: **B-tree index thông thường của Oracle không lưu entry cho hàng mà tất cả cột khóa index đều NULL**. Vì thế:

- Index B-tree một cột thường không chứa entry cho các hàng có cột đó NULL.
- Truy vấn `WHERE col IS NULL` có thể không dùng được index B-tree một cột như cách bạn kỳ vọng.
- Composite B-tree index có thể có entry khi ít nhất một thành phần khóa khác NULL; vì vậy hành vi khác với index một cột toàn NULL.
- Bitmap index và các cấu trúc index khác có đặc tính khác, nhưng lựa chọn cần phù hợp workload và môi trường.

Không nên tạo index chỉ vì thấy truy vấn có `IS NULL`. Trước tiên hãy xem:

1. Tỷ lệ hàng NULL trong cột.
2. Số lượng hàng cần trả về và độ chọn lọc.
3. Các cột khác trong điều kiện lọc và thứ tự composite index.
4. Execution plan thực tế và thống kê.
5. Tần suất ghi dữ liệu và chi phí duy trì index.

Ví dụ kiểm tra kế hoạch ở môi trường được phép:

```sql
EXPLAIN PLAN FOR
SELECT customer_id
FROM customers
WHERE email IS NULL;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

Đây là lệnh đọc/ghi plan table theo cấu hình công cụ; cần quyền phù hợp và môi trường thực hành. Không kết luận hiệu năng chỉ từ việc một index tồn tại.

## 15. Những lỗi và hiểu nhầm thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| `WHERE col = NULL` không trả hàng | Phép so sánh cho UNKNOWN | Dùng `col IS NULL` |
| `WHERE col <> NULL` không trả hàng | Phép so sánh cho UNKNOWN | Dùng `col IS NOT NULL` |
| `NOT (col > 10)` bỏ mất hàng NULL | `NOT UNKNOWN` vẫn UNKNOWN | Thêm `OR col IS NULL` nếu nghiệp vụ muốn giữ |
| `NOT IN (subquery)` bất ngờ trả 0 hàng | Tập con có NULL | Lọc NULL trong subquery hoặc dùng `NOT EXISTS` |
| `COUNT(col)` nhỏ hơn `COUNT(*)` | `COUNT(col)` bỏ qua NULL | Chọn hàm đếm theo đúng ý nghĩa |
| `AVG(col)` lớn hơn dự kiến khi có nhiều NULL | AVG bỏ qua NULL chứ không coi NULL là 0 | Xác định có cần thay NULL bằng 0 hay không |
| LEFT JOIN mất các hàng không match | Điều kiện cột bảng phải đặt trong WHERE làm UNKNOWN | Đưa điều kiện phù hợp vào ON nếu cần giữ hàng trái |
| Hai hàng NULL không match trong JOIN | `NULL = NULL` là UNKNOWN | Dùng null-safe predicate nếu thực sự muốn ghép |
| Java truyền null nhưng truy vấn `col = ?` không tìm hàng NULL | Bind NULL không làm phép `=` thành IS NULL | Chọn câu SQL `IS NULL` hoặc viết điều kiện null-safe |
| Chuỗi chỉ có dấu cách vượt qua `IS NOT NULL` | Space là giá trị non-NULL | Dùng chuẩn hóa/`TRIM` theo nghiệp vụ |
| Báo cáo hiện 0 thay vì “chưa có dữ liệu” | `NVL` thay NULL bằng 0 | Xác định ý nghĩa thống kê trước khi thay thế |

### Quy trình suy luận khi gặp NULL

Khi một truy vấn không trả về hàng như dự kiến, hãy lần lượt hỏi:

1. Cột có thực sự NULL hay chỉ chứa 0/dấu cách/chuỗi khác?
2. Biểu thức đang dùng `=`, `<>`, `>`, `BETWEEN`, `LIKE`, `IN` hay `NOT IN`?
3. Nếu có NULL, biểu thức cho TRUE, FALSE hay UNKNOWN?
4. Mệnh đề hiện tại là `WHERE`, `HAVING`, `ON`, `CASE` hay biểu thức tính toán?
5. Nghiệp vụ muốn NULL được **giữ**, **loại**, **ghép**, **thay thế** hay **xem như không áp dụng bộ lọc**?
6. Có cần xử lý riêng tham số NULL từ ứng dụng và dữ liệu NULL trong bảng không?

Đừng sửa truy vấn bằng `NVL(col, 0)` hoặc `NVL(col, 'X')` chỉ để làm mất NULL nếu chưa chứng minh giá trị thay thế không thể xung đột với dữ liệu thật.

## 16. Bài thực hành tổng hợp

Các bước dưới đây sử dụng một bảng nhỏ trong schema thực hành. Chỉ chạy DDL/DML nếu bạn có quyền tạo bảng và không dùng tên bảng trùng với dữ liệu hiện có.

### Bước 1. Tạo bảng minh họa

```sql
CREATE TABLE demo_null_select (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(80),
    salary NUMBER,
    commission_pct NUMBER,
    department_id NUMBER
);
```

### Bước 2. Chèn các trạng thái khác nhau

```sql
INSERT INTO demo_null_select VALUES (1, 'An', 12000, 0.15, 10);
INSERT INTO demo_null_select VALUES (2, 'Binh', 8000, NULL, 10);
INSERT INTO demo_null_select VALUES (3, 'Chi', NULL, 0.10, 20);
INSERT INTO demo_null_select VALUES (4, 'Dung', 5000, NULL, NULL);
INSERT INTO demo_null_select VALUES (5, 'Ha', 0, 0, 20);

COMMIT;
```

Các hàng này cố ý bao gồm:

- Giá trị NULL ở `SALARY`.
- Giá trị NULL ở `COMMISSION_PCT`.
- Giá trị NULL ở `DEPARTMENT_ID`.
- Số 0 để so sánh với NULL.

### Bước 3. Tìm nhân viên chưa có lương

```sql
SELECT employee_id, employee_name, salary
FROM demo_null_select
WHERE salary IS NULL;
```

Kết quả mong đợi: nhân viên `Chi` (ID 3).

### Bước 4. Tìm nhân viên đã có lương

```sql
SELECT employee_id, employee_name, salary
FROM demo_null_select
WHERE salary IS NOT NULL
ORDER BY salary;
```

Kết quả bao gồm nhân viên có salary bằng 0, vì 0 là giá trị khác NULL.

### Bước 5. So sánh UNKNOWN với FALSE

```sql
SELECT employee_id,
       CASE
           WHEN salary > 10000 THEN 'TRUE'
           WHEN salary <= 10000 THEN 'FALSE'
           ELSE 'UNKNOWN'
       END AS comparison_result
FROM demo_null_select
ORDER BY employee_id;
```

Nhân viên ID 3 có `salary=NULL`, vì thế cả hai so sánh đều UNKNOWN và được phân vào nhánh ELSE. Đây là cách quan sát ba trạng thái trong một truy vấn.

### Bước 6. Thử NOT và điều kiện bổ sung

```sql
-- Chỉ các hàng mà salary > 10000 là FALSE:
SELECT employee_id, salary
FROM demo_null_select
WHERE NOT (salary > 10000);

-- Bao gồm cả salary NULL:
SELECT employee_id, salary
FROM demo_null_select
WHERE NOT (salary > 10000)
   OR salary IS NULL;
```

So sánh hai kết quả và giải thích vì sao ID 3 chỉ xuất hiện ở câu thứ hai.

### Bước 7. So sánh COUNT

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(salary) AS rows_with_salary,
       COUNT(commission_pct) AS rows_with_commission
FROM demo_null_select;
```

Đối chiếu số hàng với các giá trị NULL đã chèn.

### Bước 8. Nhóm theo department_id

```sql
SELECT department_id, COUNT(*) AS employee_count
FROM demo_null_select
GROUP BY department_id
ORDER BY department_id NULLS LAST;
```

Quan sát nhóm NULL xuất hiện riêng. Điều đó không có nghĩa phép so sánh `department_id = NULL` trở thành TRUE.

### Bước 9. Dọn bảng thực hành

Chỉ khi đã xác nhận đúng bảng vừa tạo và không cần dữ liệu:

```sql
DROP TABLE demo_null_select PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu khỏi schema thực hành, không dùng recycle bin để khôi phục theo hành vi lệnh; DDL có commit ngầm. Không chạy trên bảng nghiệp vụ hoặc đối tượng dùng chung.

## 17. Quy tắc ghi nhớ khi viết SELECT

| Mục tiêu | Cách viết |
|---|---|
| Tìm cột chưa có giá trị | `WHERE col IS NULL` |
| Tìm cột đã có giá trị | `WHERE col IS NOT NULL` |
| Tìm giá trị khác một giá trị xác định và vẫn lấy NULL | `WHERE col <> :value OR col IS NULL` nếu đúng nghiệp vụ |
| Tìm giá trị trong danh sách | `WHERE col IN (...)`, đồng thời hiểu NULL trong danh sách |
| Loại các giá trị thuộc tập con | Ưu tiên xem xét `NOT EXISTS`; kiểm soát NULL ở cả hai phía |
| Phân nhóm NULL trong kết quả | `CASE WHEN col IS NULL THEN ...` |
| Đếm mọi hàng | `COUNT(*)` |
| Đếm giá trị đã ghi nhận | `COUNT(col)` |
| Hiển thị giá trị thay thế | `NVL`, `COALESCE`, `CASE` |
| Sắp xếp NULL rõ ràng | `ORDER BY col ASC NULLS LAST` hoặc lựa chọn phù hợp |
| Tìm hàng NULL từ JDBC | Câu SQL có `IS NULL`, không bind NULL vào `= ?` |
| Bỏ qua bộ lọc khi tham số NULL | `:p IS NULL OR col = :p` |

Ba nguyên tắc quan trọng:

1. **Muốn kiểm tra trạng thái NULL, dùng `IS NULL` hoặc `IS NOT NULL`.**
2. **Khi so sánh hoặc tính toán có NULL, hãy nghĩ đến UNKNOWN trước khi dự đoán kết quả WHERE.**
3. **Xác định ý nghĩa nghiệp vụ của NULL trước khi thay bằng 0, chuỗi mặc định hoặc loại khỏi báo cáo.**

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `WHERE email = NULL` có thể tìm các hàng email NULL không?

**Trả lời:** Không. Phép so sánh trả UNKNOWN; dùng `WHERE email IS NULL`.

**Câu 2.** `NULL <> 10` là TRUE hay FALSE?

**Trả lời:** UNKNOWN. Không có đủ thông tin để kết luận NULL khác 10 theo phép so sánh thông thường.

**Câu 3.** `NOT UNKNOWN` bằng gì?

**Trả lời:** UNKNOWN.

**Câu 4.** WHERE xử lý hàng có điều kiện UNKNOWN thế nào?

**Trả lời:** Loại hàng đó khỏi kết quả; chỉ hàng có điều kiện TRUE được chọn.

**Câu 5.** `salary > 10000 OR salary IS NULL` có lấy hàng salary NULL không?

**Trả lời:** Có. Vế `salary IS NULL` TRUE nên phép OR TRUE.

**Câu 6.** `salary > 10000 AND salary IS NULL` có thể TRUE không?

**Trả lời:** Không. Nếu salary NULL, vế đầu UNKNOWN và vế sau TRUE, kết quả UNKNOWN; nếu salary khác NULL, vế sau FALSE. Không có trường hợp TRUE.

**Câu 7.** Vì sao `NOT IN (10, 20, NULL)` thường không trả những giá trị 30?

**Trả lời:** Phép so sánh `30 <> NULL` là UNKNOWN; chuỗi AND của các điều kiện trở thành UNKNOWN nên WHERE loại hàng.

**Câu 8.** `COUNT(*)` và `COUNT(email)` khác nhau thế nào?

**Trả lời:** `COUNT(*)` đếm mọi hàng; `COUNT(email)` chỉ đếm giá trị email khác NULL.

**Câu 9.** Một LEFT JOIN không tìm thấy hàng bên phải. Các cột bên phải được trả về thế nào?

**Trả lời:** Oracle trả NULL cho các cột bên phải của hàng không khớp. Đây là NULL sinh ra bởi phép nối, không nhất thiết là dữ liệu gốc trong bảng phải.

**Câu 10.** Tham số JDBC `email=null` được bind vào `WHERE email = ?` có tìm hàng email NULL không?

**Trả lời:** Không. Cần dùng `IS NULL` hoặc điều kiện null-safe rõ ràng.

**Câu 11.** Pattern `:p IS NULL OR col = :p` có nghĩa là gì?

**Trả lời:** Thường là bỏ qua bộ lọc khi tham số NULL; nó không đồng nghĩa tìm các hàng có `col IS NULL`.

**Câu 12.** Vì sao `WHERE NOT (salary > 10000)` không lấy hàng salary NULL?

**Trả lời:** `salary > 10000` là UNKNOWN; `NOT UNKNOWN` vẫn UNKNOWN và WHERE loại hàng.

## 19. Kết luận

`NULL` biểu thị một giá trị chưa xác định, nên các phép so sánh thông thường như `=`, `<>`, `>`, `BETWEEN` và `LIKE` có thể trả về **`UNKNOWN`**. SQL sử dụng logic ba giá trị `TRUE`, `FALSE`, `UNKNOWN`; trong đó `NOT UNKNOWN` vẫn UNKNOWN. Mệnh đề `WHERE` chỉ giữ hàng có điều kiện TRUE, vì vậy hàng UNKNOWN bị loại giống như hàng FALSE.

Khi cần tìm giá trị thiếu, hãy dùng **`IS NULL`**; khi cần tìm giá trị đã có, dùng **`IS NOT NULL`**. Đừng thay chúng bằng `= NULL` hoặc `<> NULL`. Đồng thời, hãy xem xét NULL khi dùng `NOT IN`, `JOIN`, `CASE`, `COUNT`, `AVG`, `SUM`, sắp xếp và tham số bind từ Java. Việc dùng `NVL` hoặc `COALESCE` chỉ nên thực hiện khi giá trị thay thế đúng với ý nghĩa nghiệp vụ.

Hiểu rõ `UNKNOWN` giúp bạn dự đoán chính xác vì sao một hàng xuất hiện hoặc biến mất khỏi kết quả SELECT, viết điều kiện lọc dễ đọc hơn và tránh nhiều lỗi dữ liệu khó phát hiện trong các ứng dụng kết nối Oracle.

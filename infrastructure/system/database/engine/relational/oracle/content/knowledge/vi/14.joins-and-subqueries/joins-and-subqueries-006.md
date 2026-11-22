# Scalar subquery và điều kiện trả về tối đa một dòng trong Oracle Database

## 1. Khi nào một truy vấn con được dùng như một giá trị?

Trong một câu SQL, có lúc ta cần lấy **một giá trị** từ bảng khác để hiển thị, tính toán hoặc so sánh. Ví dụ:

- Hiển thị tên phòng ban cạnh mỗi nhân viên.
- So sánh lương nhân viên với mức lương trung bình của phòng ban đó.
- Tìm thuế suất đang áp dụng cho một mã hàng.
- Gán một giá trị vào cột khi chạy UPDATE.
- Lấy ngày giao dịch mới nhất của từng tài khoản.

Một cách diễn đạt tự nhiên là đặt truy vấn con ở vị trí biểu thức:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       (SELECT d.department_name
        FROM   departments d
        WHERE  d.department_id = e.department_id) AS department_name
FROM   employees e;
~~~

Phần nằm trong ngoặc là **scalar subquery**: truy vấn con được dùng như một giá trị vô hướng trong câu SQL bên ngoài. Oracle yêu cầu scalar subquery trả về **một cột và tối đa một dòng**:

- **Một dòng, một cột:** lấy giá trị ở cột đó.
- **Không có dòng nào:** giá trị scalar subquery là SQL NULL.
- **Nhiều hơn một dòng:** Oracle báo lỗi `ORA-01427: single-row subquery returns more than one row`.

Đây là điểm cốt lõi của bài học. Truy vấn con không tự động trở thành một giá trị chỉ vì được đặt trong ngoặc. Phải có cơ sở dữ liệu hoặc logic truy vấn bảo đảm cardinality phù hợp.

> Bài học dùng cú pháp Oracle Database 19c. Các ví dụ dùng bảng `EMPLOYEES` và `DEPARTMENTS` theo mô hình HR quen thuộc; một số phần có bộ bảng lab riêng. Hãy thay tên bảng/cột theo schema thực tế. Các lệnh CREATE/INSERT chỉ chạy trong schema lab được phép.

## 2. Scalar subquery là gì?

Theo SQL Language Reference, scalar subquery expression là một subquery trả về **một giá trị của một cột từ một dòng**. Nó phải được đặt trong cặp ngoặc riêng:

~~~sql
(SELECT select_expression
 FROM   source_table
 WHERE  condition)
~~~

Ví dụ tối giản:

~~~sql
SELECT (SELECT 'Oracle' FROM dual) AS product_name
FROM   dual;
~~~

Subquery đọc một dòng từ `DUAL`, trả một cột là chuỗi `Oracle`; câu SQL bên ngoài nhận giá trị đó như một expression.

### 2.1. Bốn trường hợp cần phân biệt

| Số cột subquery | Số dòng subquery | Kết quả khi dùng scalar subquery |
| --- | --- | --- |
| 1 | 1 | Nhận giá trị ở cột duy nhất |
| 1 | 0 | Nhận SQL NULL |
| 1 | 2 trở lên | Lỗi `ORA-01427` |
| 2 trở lên | Bất kỳ | Không phải scalar subquery hợp lệ; phải thiết kế lại để chỉ trả một biểu thức/cột |

Ví dụ một dòng:

~~~sql
SELECT (SELECT 10 FROM dual) AS value
FROM dual;
~~~

Ví dụ không có dòng:

~~~sql
SELECT (
    SELECT d.department_name
    FROM   departments d
    WHERE  d.department_id = -999
) AS department_name
FROM dual;
~~~

Kết quả của `DEPARTMENT_NAME` là NULL, bởi subquery không tìm thấy dòng nào.

Ví dụ nhiều dòng:

~~~sql
SELECT (
    SELECT e.employee_name
    FROM   employees e
    WHERE  e.department_id = 50
) AS employee_name
FROM dual;
~~~

Nếu phòng ban 50 có nhiều nhân viên, scalar subquery không thể quyết định lấy tên nào và Oracle báo `ORA-01427`.

### 2.2. Scalar subquery khác subquery trả về một tập dòng

Một subquery có thể trả nhiều dòng nếu vị trí sử dụng cho phép nhận một tập giá trị. Ví dụ:

~~~sql
SELECT employee_id, employee_name
FROM   employees
WHERE  department_id IN (
    SELECT department_id
    FROM   departments
    WHERE  location_id = 1700
);
~~~

Subquery sau `IN` là một tập giá trị; nó được phép trả nhiều dòng. Ngược lại:

~~~sql
SELECT employee_id, employee_name
FROM   employees
WHERE  department_id = (
    SELECT department_id
    FROM   departments
    WHERE  location_id = 1700
);
~~~

Subquery sau dấu `=` được dùng như **một giá trị duy nhất**. Nếu location 1700 có nhiều phòng ban, truy vấn có thể báo `ORA-01427`.

## 3. Scalar subquery xuất hiện ở những vị trí nào?

Scalar subquery hợp lệ trong phần lớn vị trí SQL cho phép một biểu thức (`expr`), miễn là tuân thủ các giới hạn của Oracle. Những vị trí thường gặp:

### 3.1. Trong SELECT list

~~~sql
SELECT e.employee_id,
       e.employee_name,
       (SELECT d.department_name
        FROM   departments d
        WHERE  d.department_id = e.department_id) AS department_name
FROM   employees e
ORDER BY e.employee_id;
~~~

Mỗi dòng nhân viên có thêm một giá trị tên phòng ban. Đây là ví dụ **correlated scalar subquery**, vì subquery tham chiếu `e.department_id` của query bên ngoài.

### 3.2. Trong WHERE để so sánh với một giá trị

~~~sql
SELECT employee_id, employee_name, salary
FROM   employees
WHERE  salary > (
    SELECT AVG(salary)
    FROM   employees
);
~~~

`AVG(salary)` là một giá trị trung bình toàn công ty. Nhân viên có lương cao hơn mức đó được chọn.

### 3.3. Trong biểu thức số học

~~~sql
SELECT e.employee_id,
       e.salary,
       e.salary - (
           SELECT AVG(e2.salary)
           FROM   employees e2
       ) AS difference_from_company_avg
FROM   employees e;
~~~

Scalar subquery trả một NUMBER và được dùng như một toán hạng trong phép trừ.

### 3.4. Trong hàm hoặc CASE expression

~~~sql
SELECT e.employee_id,
       NVL(
         (SELECT d.department_name
          FROM   departments d
          WHERE  d.department_id = e.department_id),
         'Chua gan phong ban'
       ) AS department_label
FROM employees e;
~~~

Scalar subquery nằm bên trong `NVL`. Nếu không có phòng ban tương ứng, subquery trả NULL và `NVL` trả chuỗi thay thế.

### 3.5. Trong ORDER BY

~~~sql
SELECT e.employee_id, e.employee_name
FROM   employees e
ORDER BY (
    SELECT d.department_name
    FROM   departments d
    WHERE  d.department_id = e.department_id
), e.employee_id;
~~~

Subquery được dùng làm biểu thức sắp xếp. Tuy nhiên, nếu chỉ cần sắp theo tên phòng ban và hiển thị các cột của phòng ban, JOIN thường dễ đọc hơn.

### 3.6. Trong UPDATE để gán một giá trị

~~~sql
UPDATE employees e
SET    e.salary = (
    SELECT r.new_salary
    FROM   salary_rules r
    WHERE  r.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM   salary_rules r
    WHERE  r.employee_id = e.employee_id
);
~~~

Subquery trong `SET` cần trả một giá trị cho mỗi dòng được cập nhật. `WHERE EXISTS` trong ví dụ giúp chỉ cập nhật những nhân viên có rule tương ứng. Nếu bỏ điều kiện đó, subquery không có dòng có thể trả NULL và làm cột `SALARY` thành NULL nếu cột cho phép.

## 4. Cardinality: điều kiện trả về tối đa một dòng

**Cardinality** trong ngữ cảnh này là số dòng mà subquery có thể trả về. Một scalar subquery cần cardinality không vượt quá 1.

Không phải mọi câu SQL nhìn có vẻ “tìm một nhân viên” đều bảo đảm chỉ có một dòng:

~~~sql
SELECT employee_name
FROM   employees
WHERE  department_id = 50;
~~~

Điều kiện `department_id = 50` có thể tìm thấy hàng chục nhân viên. Nếu đặt truy vấn đó vào scalar context, nó không hợp lệ khi có nhiều hơn một kết quả.

### 4.1. Dùng primary key hoặc unique key

Một predicate dựa trên đầy đủ khóa duy nhất là cách tự nhiên nhất để bảo đảm tối đa một dòng:

~~~sql
SELECT (
    SELECT d.department_name
    FROM   departments d
    WHERE  d.department_id = 50
) AS department_name
FROM dual;
~~~

Nếu `DEPARTMENT_ID` là primary key, subquery có thể trả tối đa một dòng. Nó có thể không trả dòng nào nếu ID 50 không tồn tại; khi đó giá trị là NULL.

Với bảng rule:

~~~sql
CREATE TABLE employee_salary_rule_lab (
    employee_id NUMBER PRIMARY KEY,
    new_salary  NUMBER(10,2) NOT NULL
);
~~~

Predicate `r.employee_id = e.employee_id` dựa trên primary key bảo đảm tối đa một dòng trong `EMPLOYEE_SALARY_RULE_LAB`.

**Lưu ý:** Unique constraint chỉ bảo đảm uniqueness theo đúng các cột được khai báo. Khi dùng composite unique key, phải lọc theo đầy đủ khóa nghiệp vụ phù hợp. Các cột nullable và cách xử lý NULL của Oracle cần được hiểu rõ; không tự suy rằng một predicate thiếu một phần khóa đã bảo đảm một dòng.

### 4.2. Aggregate không GROUP BY

Aggregate function không có `GROUP BY` tạo một dòng kết quả ngay cả khi tập đầu vào không có dòng:

~~~sql
SELECT (
    SELECT MAX(e.salary)
    FROM   employees e
    WHERE  e.department_id = 999
) AS highest_salary
FROM dual;
~~~

Khi không có nhân viên phòng ban 999, `MAX` trả NULL trong một dòng kết quả; scalar subquery vẫn có một giá trị.

Một số aggregate thường dùng:

| Hàm | Khi tập đầu vào rỗng, không GROUP BY | Cardinality |
| --- | --- | --- |
| `COUNT(*)` | Trả 0 | Một dòng |
| `COUNT(expr)` | Trả 0 nếu không có giá trị được đếm | Một dòng |
| `MAX(expr)` | Trả NULL | Một dòng |
| `MIN(expr)` | Trả NULL | Một dòng |
| `SUM(expr)` | Trả NULL | Một dòng |
| `AVG(expr)` | Trả NULL | Một dòng |

Ví dụ đếm số nhân viên theo phòng ban:

~~~sql
SELECT d.department_id,
       d.department_name,
       (SELECT COUNT(*)
        FROM   employees e
        WHERE  e.department_id = d.department_id) AS employee_count
FROM   departments d
ORDER BY d.department_id;
~~~

Ngay cả phòng ban không có nhân viên, subquery `COUNT(*)` vẫn trả một dòng với giá trị 0.

### 4.3. Aggregate có GROUP BY không tự bảo đảm một dòng

~~~sql
SELECT (
    SELECT e.department_id
    FROM   employees e
    GROUP BY e.department_id
) AS department_id
FROM dual;
~~~

`GROUP BY department_id` có thể tạo nhiều nhóm, mỗi nhóm một dòng. Nếu có nhiều phòng ban, scalar subquery vẫn báo `ORA-01427`.

Aggregate chỉ bảo đảm một dòng khi **không có GROUP BY** và không có cấu trúc khác làm tăng số dòng. Với `GROUP BY`, hãy kiểm tra số nhóm có thể trả về.

### 4.4. DISTINCT không phải cách sửa cardinality một cách mặc định

~~~sql
SELECT (
    SELECT DISTINCT e.department_id
    FROM   employees e
) AS department_id
FROM dual;
~~~

Nếu bảng có nhiều phòng ban khác nhau, `DISTINCT` vẫn trả nhiều dòng và scalar subquery vẫn lỗi. Nếu tất cả nhân viên đều thuộc một phòng ban, câu lệnh có thể tình cờ trả một dòng; nhưng đó không phải bảo đảm từ thiết kế dữ liệu.

`DISTINCT` chỉ đúng khi nghiệp vụ thực sự yêu cầu tập **giá trị khác nhau**. Không dùng nó để che lỗi join hoặc duplicate rows mà chưa xác định nguyên nhân.

## 5. Zero rows trả NULL: hệ quả đối với logic SQL

Quy tắc zero-row rất quan trọng:

~~~sql
SELECT (
    SELECT d.department_name
    FROM   departments d
    WHERE  d.department_id = -1
) AS department_name
FROM dual;
~~~

Subquery không trả row, vì vậy scalar expression nhận NULL. Nhưng điều đó **không có nghĩa câu SELECT bên ngoài không trả dòng**. Bên ngoài vẫn đọc `DUAL` và trả một dòng, trong đó cột `DEPARTMENT_NAME` là NULL.

### 5.1. So sánh với scalar subquery không tìm thấy row

~~~sql
SELECT employee_id, employee_name
FROM   employees e
WHERE  e.department_id = (
    SELECT d.department_id
    FROM   departments d
    WHERE  d.department_name = 'Phong ban khong ton tai'
);
~~~

Subquery không tìm thấy phòng ban nên trả NULL. Điều kiện `e.department_id = NULL` không phải TRUE; nó là UNKNOWN, vì thế `WHERE` không chọn row nào.

Đây là một khác biệt quan trọng:

- Subquery không tìm thấy row → giá trị scalar là NULL.
- Phép so sánh `= NULL` → UNKNOWN.
- `WHERE` chỉ chọn row khi predicate TRUE.

### 5.2. IS NULL không phân biệt “không có row” với “có row nhưng cột NULL”

Xét:

~~~sql
SELECT (
    SELECT d.manager_id
    FROM   departments d
    WHERE  d.department_id = 50
) AS manager_id
FROM dual;
~~~

Kết quả NULL có thể có hai nguyên nhân:

1. Không tồn tại phòng ban 50.
2. Có phòng ban 50 nhưng `MANAGER_ID` của phòng ban đó là NULL.

Chỉ kiểm tra scalar expression `IS NULL` không phân biệt được hai trường hợp.

Nếu cần phân biệt:

~~~sql
SELECT CASE
         WHEN EXISTS (
           SELECT 1
           FROM   departments d
           WHERE  d.department_id = 50
         )
         THEN 'DEPARTMENT_EXISTS'
         ELSE 'NO_DEPARTMENT'
       END AS department_state
FROM dual;
~~~

Hoặc dùng LEFT JOIN để giữ cả parent row và kiểm tra khóa của bảng con:

~~~sql
SELECT req.requested_id,
       d.department_id,
       CASE
         WHEN d.department_id IS NULL THEN 'NO_DEPARTMENT'
         WHEN d.manager_id IS NULL THEN 'NO_MANAGER'
         ELSE 'HAS_MANAGER'
       END AS manager_state
FROM   (SELECT 50 AS requested_id FROM dual) req
LEFT JOIN departments d
       ON d.department_id = req.requested_id;
~~~

Trong ví dụ này, `DEPARTMENT_ID` là khóa chính nên nếu `d.department_id` NULL thì không có dòng phòng ban được ghép.

### 5.3. NVL có thể gộp hai trạng thái khác nhau

~~~sql
NVL(
  (SELECT d.manager_id
   FROM departments d
   WHERE d.department_id = 50),
  -1
)
~~~

Biểu thức trên thay NULL bằng -1, nhưng không phân biệt được:

- Không có department 50.
- Có department 50 nhưng chưa chỉ định manager.

Nếu nghiệp vụ cần phân biệt, dùng `EXISTS`, `CASE` hoặc LEFT JOIN có cột nhận diện row. Chỉ dùng `NVL` khi hai trạng thái thực sự có cùng cách xử lý.

## 6. Correlated scalar subquery

**Correlated subquery** tham chiếu một cột từ query block bên ngoài. Giá trị trả về vì vậy phụ thuộc từng dòng của query ngoài.

Ví dụ: hiển thị mức lương trung bình của phòng ban bên cạnh từng nhân viên:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       e.department_id,
       e.salary,
       (SELECT AVG(e2.salary)
        FROM   employees e2
        WHERE  e2.department_id = e.department_id) AS department_avg
FROM   employees e
ORDER BY e.department_id, e.employee_id;
~~~

`e.department_id` thuộc query bên ngoài. `e2.department_id` thuộc subquery. Việc dùng alias giúp phân biệt cột của từng query block.

### 6.1. Tìm nhân viên có lương cao hơn trung bình phòng ban

~~~sql
SELECT e.employee_id,
       e.employee_name,
       e.department_id,
       e.salary
FROM   employees e
WHERE  e.salary > (
    SELECT AVG(e2.salary)
    FROM   employees e2
    WHERE  e2.department_id = e.department_id
)
ORDER BY e.department_id, e.salary DESC;
~~~

Subquery được liên kết với từng phòng ban của nhân viên hiện tại. Aggregate `AVG` không có `GROUP BY` luôn trả một dòng; nếu không có nhân viên phù hợp, giá trị AVG là NULL.

### 6.2. Correlation không có nghĩa optimizer bắt buộc chạy một full scan cho mỗi row

Về mặt khái niệm, correlated subquery được đánh giá theo từng dòng của query cha. Tuy nhiên, **Oracle optimizer có thể viết lại truy vấn thành JOIN hoặc một kỹ thuật tương đương** nếu điều kiện và ngữ nghĩa cho phép.

Do đó:

- Đừng kết luận mọi correlated subquery đều chậm.
- Đừng kết luận optimizer luôn chuyển nó thành JOIN.
- Xem execution plan và số liệu thực tế khi tối ưu.
- Đảm bảo predicate liên kết có index phù hợp nếu workload và selectivity cần.

Ví dụ predicate `e2.department_id = e.department_id` có thể được hỗ trợ bởi index trên `EMPLOYEES(DEPARTMENT_ID)` trong một số workload; nhưng tạo index chỉ vì thấy correlated subquery là không đủ căn cứ. Hãy xem kế hoạch và chi phí DML/storage của index.

### 6.3. Correlation và lỗi tham chiếu cột

Khi hai bảng có cùng tên cột, luôn qualify alias:

~~~sql
SELECT e.employee_id,
       (SELECT COUNT(*)
        FROM   employees e2
        WHERE  e2.manager_id = e.employee_id) AS direct_reports
FROM   employees e;
~~~

Ở đây:

- `e2.manager_id` là manager của nhân viên trong subquery.
- `e.employee_id` là ID của nhân viên hiện tại ở query ngoài.

Nếu bỏ alias, Oracle có thể phân giải tên cột theo phạm vi query blocks không như người viết dự đoán. Qualify alias giúp tránh nhầm lẫn và giảm lỗi khi schema có thêm cột cùng tên.

## 7. Scalar subquery và JOIN: chọn cách nào?

Hai cách dưới đây có thể biểu diễn cùng một yêu cầu tra cứu tên phòng ban nếu quan hệ nhân viên → phòng ban là nhiều-một và `DEPARTMENTS.DEPARTMENT_ID` là duy nhất.

**Cách scalar subquery:**

~~~sql
SELECT e.employee_id,
       e.employee_name,
       (SELECT d.department_name
        FROM departments d
        WHERE d.department_id = e.department_id) AS department_name
FROM employees e;
~~~

**Cách LEFT JOIN:**

~~~sql
SELECT e.employee_id,
       e.employee_name,
       d.department_name
FROM   employees e
LEFT JOIN departments d
       ON d.department_id = e.department_id;
~~~

### 7.1. Khác biệt khi phía tra cứu có nhiều dòng

Giả sử bảng tra cứu có hai dòng cùng thỏa điều kiện:

- Scalar subquery: báo `ORA-01427`.
- JOIN: có thể nhân đôi dòng của query ngoài.

Hai hành vi khác nhau nhưng đều làm lộ vấn đề cardinality. Scalar subquery buộc người viết giải quyết việc một giá trị không còn duy nhất; JOIN thể hiện quan hệ một-nhiều bằng nhiều dòng output.

### 7.2. Khác biệt khi không tìm thấy dòng

Trong SELECT list:

- Scalar subquery không tìm thấy dòng → giá trị expression là NULL.
- LEFT JOIN không tìm thấy dòng → các cột phía bảng phải NULL.
- INNER JOIN không tìm thấy dòng → row phía bảng ngoài bị loại.

Do đó, so sánh scalar subquery với INNER JOIN thường không tương đương khi có thể thiếu row tra cứu. LEFT JOIN gần với semantics giữ parent row của scalar subquery trong SELECT list hơn.

### 7.3. Khi nào nên chọn JOIN?

Ưu tiên JOIN khi:

- Cần lấy nhiều cột từ bảng liên quan.
- Cần lọc, nhóm, sắp xếp theo cột của bảng liên quan.
- Cần thể hiện rõ quan hệ một-một, một-nhiều hoặc nhiều-nhiều.
- Cần giữ nhiều dòng con thay vì gom chúng thành một giá trị.

Scalar subquery phù hợp khi:

- Chỉ cần một giá trị cho mỗi dòng ngoài.
- Điều kiện tra cứu có khóa duy nhất rõ ràng.
- Aggregate con tạo một scalar như COUNT/AVG/MAX.
- Biểu thức ngắn gọn, giúp query dễ đọc.

Không có quy tắc “scalar subquery luôn chậm hơn JOIN” hay “JOIN luôn nhanh hơn”. Optimizer có thể viết lại; hiệu năng phải được đo trên dữ liệu và execution plan thật.

## 8. Scalar subquery và các loại subquery khác

| Dạng | Câu hỏi nó trả lời | Cardinality | Cú pháp thường gặp |
| --- | --- | --- | --- |
| Scalar subquery | Một giá trị là gì? | Một cột, tối đa một dòng | `col = (SELECT ...)` |
| Single-row comparison subquery | Giá trị đơn thỏa phép so sánh nào? | Tối đa một dòng | `salary > (SELECT AVG(...))` |
| Multi-row subquery với IN | Giá trị có thuộc tập kết quả không? | 0 hoặc nhiều dòng | `dept_id IN (SELECT ...)` |
| ANY/SOME | Có ít nhất một giá trị trong tập làm phép so sánh TRUE không? | 0 hoặc nhiều dòng | `salary > ANY (SELECT ...)` |
| ALL | Mọi giá trị trong tập có thỏa phép so sánh không? | 0 hoặc nhiều dòng | `salary > ALL (SELECT ...)` |
| EXISTS | Có ít nhất một dòng thỏa điều kiện không? | 0 hoặc nhiều dòng | `EXISTS (SELECT 1 ...)` |
| NOT EXISTS | Không có dòng nào thỏa điều kiện? | 0 hoặc nhiều dòng | `NOT EXISTS (SELECT 1 ...)` |

### 8.1. = và IN không thể thay thế nhau tùy tiện

~~~sql
-- Subquery phải trả tối đa một giá trị:
WHERE department_id = (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
)

-- Subquery có thể trả nhiều department_id:
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
)
~~~

Nếu location 1700 có nhiều phòng ban, câu đầu có thể báo `ORA-01427`, câu sau là cách dùng tập hợp phù hợp.

### 8.2. ANY và ALL

~~~sql
-- Lương cao hơn ít nhất một nhân viên ở phòng ban 50.
SELECT e.employee_id, e.salary
FROM employees e
WHERE e.salary > ANY (
    SELECT e2.salary
    FROM employees e2
    WHERE e2.department_id = 50
);

-- Lương cao hơn tất cả nhân viên ở phòng ban 50.
SELECT e.employee_id, e.salary
FROM employees e
WHERE e.salary > ALL (
    SELECT e2.salary
    FROM employees e2
    WHERE e2.department_id = 50
);
~~~

`ANY`/`ALL` nhận tập giá trị. Chúng diễn đạt quan hệ so sánh với nhiều giá trị mà không cần ép subquery về scalar.

### 8.3. EXISTS kiểm tra sự tồn tại, không lấy giá trị

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

`EXISTS` chỉ quan tâm có row thỏa điều kiện hay không. Không cần chọn cột nào từ subquery; `SELECT 1` là quy ước phổ biến. Không dùng scalar subquery nếu mục tiêu thực chất là kiểm tra sự tồn tại.

### 8.4. Cẩn thận với NOT IN và NULL

~~~sql
SELECT d.department_id
FROM departments d
WHERE d.department_id NOT IN (
    SELECT e.department_id
    FROM employees e
);
~~~

Nếu subquery trả một giá trị NULL, `NOT IN` có thể làm điều kiện thành UNKNOWN đối với các giá trị không khớp, khiến kết quả không như mong đợi. Khi mục tiêu là “không tồn tại nhân viên tham chiếu phòng ban này”, thường dùng:

~~~sql
SELECT d.department_id
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

`NOT EXISTS` diễn tả trực tiếp sự vắng mặt của row tương ứng và tránh bẫy NULL của `NOT IN`.

## 9. ORA-01427: khi scalar subquery trả nhiều hơn một dòng

Đây là lỗi đặc trưng nhất của scalar subquery:

~~~text
ORA-01427: single-row subquery returns more than one row
~~~

Nguyên nhân: query bên ngoài cần một giá trị, nhưng subquery trả nhiều dòng. Ví dụ:

~~~sql
SELECT e.employee_id,
       (SELECT e2.employee_name
        FROM employees e2
        WHERE e2.department_id = e.department_id) AS another_employee
FROM employees e;
~~~

Một phòng ban có nhiều nhân viên nên subquery có thể trả nhiều tên.

### 9.1. Cách điều tra trước khi sửa

Không nên thêm `ROWNUM = 1` hoặc `DISTINCT` ngay khi gặp lỗi. Trước tiên chạy riêng subquery với giá trị gây lỗi:

~~~sql
SELECT e2.employee_id, e2.employee_name
FROM   employees e2
WHERE  e2.department_id = 50
ORDER BY e2.employee_id;
~~~

Sau đó hỏi:

1. Theo mô hình dữ liệu, điều kiện có **đáng lẽ duy nhất** không?
2. Có thiếu một phần khóa trong predicate JOIN/WHERE không?
3. Dữ liệu trùng là lỗi integrity hay thực sự có nhiều kết quả hợp lệ?
4. Nghiệp vụ muốn lấy một giá trị tổng hợp, một dòng theo thứ tự, hay toàn bộ tập dòng?

### 9.2. Sửa bằng khóa duy nhất nếu logic cần một row xác định

Nếu subquery cần tìm tên phòng ban của nhân viên, dùng quan hệ qua `DEPARTMENT_ID` là primary key của bảng `DEPARTMENTS`:

~~~sql
SELECT d.department_name
FROM departments d
WHERE d.department_id = :department_id;
~~~

Nếu truy vấn vẫn trả nhiều dòng, hãy kiểm tra schema, synonym, view hoặc điều kiện thực tế. Không sửa bằng cách cắt kết quả vì điều đó che mất vấn đề dữ liệu.

### 9.3. Sửa bằng aggregate nếu nghiệp vụ cần một giá trị tổng hợp

Nếu cần lương cao nhất trong phòng ban:

~~~sql
SELECT e.employee_id,
       (SELECT MAX(e2.salary)
        FROM employees e2
        WHERE e2.department_id = e.department_id) AS max_department_salary
FROM employees e;
~~~

`MAX` trả một giá trị. Đây là sửa đúng nếu yêu cầu là **mức lương cao nhất**. Nó không phải cách đúng nếu yêu cầu là lấy **một nhân viên** có mức lương đó và cần các thuộc tính khác của đúng nhân viên.

### 9.4. Sửa bằng TOP-1 có ORDER BY khi nghiệp vụ chọn một dòng theo quy tắc

Trên Oracle 12c trở lên:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       (SELECT e2.employee_name
        FROM employees e2
        WHERE e2.department_id = e.department_id
        ORDER BY e2.salary DESC NULLS LAST, e2.employee_id
        FETCH FIRST 1 ROW ONLY) AS highest_paid_colleague
FROM employees e;
~~~

`ORDER BY` định nghĩa nhân viên nào đứng đầu; `FETCH FIRST 1 ROW ONLY` giới hạn subquery còn tối đa một row. Khóa `EMPLOYEE_ID` ở cuối giúp phân xử khi hai nhân viên có cùng lương.

**Chỉ dùng cách này khi nghiệp vụ thật sự muốn một dòng đầu tiên theo thứ tự đã chọn.** Nếu phòng ban có dữ liệu trùng bất thường trong khi đáng lẽ một-một, `FETCH FIRST 1` có thể che lỗi thay vì sửa nó.

Với phiên bản trước 12c, có thể dùng inline view sắp xếp rồi giới hạn bằng `ROWNUM`:

~~~sql
SELECT e.employee_id,
       (SELECT x.employee_name
        FROM (
            SELECT e2.employee_name
            FROM employees e2
            WHERE e2.department_id = e.department_id
            ORDER BY e2.salary DESC NULLS LAST, e2.employee_id
        ) x
        WHERE ROWNUM = 1) AS highest_paid_colleague
FROM employees e;
~~~

Đây là mẫu lồng query block: sort ở inline view, giới hạn ở query block bên ngoài. Luôn kiểm tra cú pháp/khả năng correlation theo phiên bản Oracle cụ thể khi áp dụng vào query phức tạp.

### 9.5. Sửa bằng JOIN nếu thực tế cần nhiều dòng

Nếu câu hỏi là “liệt kê tất cả nhân viên cùng phòng ban”, không cần scalar subquery:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       e2.employee_id AS colleague_id,
       e2.employee_name AS colleague_name
FROM   employees e
JOIN   employees e2
       ON e2.department_id = e.department_id
      AND e2.employee_id <> e.employee_id
ORDER BY e.employee_id, e2.employee_id;
~~~

JOIN trả nhiều dòng đúng với quan hệ nhiều-nhiều giữa nhân viên trong cùng phòng ban.

## 10. Vì sao không nên chữa ORA-01427 bằng ROWNUM hoặc DISTINCT một cách máy móc?

### 10.1. ROWNUM = 1 có thể chọn tùy ý

~~~sql
SELECT (
    SELECT e.employee_name
    FROM employees e
    WHERE e.department_id = 50
      AND ROWNUM = 1
) AS employee_name
FROM dual;
~~~

Câu lệnh có thể không lỗi, nhưng không có `ORDER BY` nên không có hợp đồng xác định nhân viên nào được chọn. Kết quả có thể đổi khi access path hoặc execution plan thay đổi.

Nếu cần dòng đầu tiên theo tiêu chí:

~~~sql
SELECT (
    SELECT e.employee_name
    FROM employees e
    WHERE e.department_id = 50
    ORDER BY e.salary DESC NULLS LAST, e.employee_id
    FETCH FIRST 1 ROW ONLY
) AS employee_name
FROM dual;
~~~

### 10.2. DISTINCT có thể làm mất tín hiệu duplicate

~~~sql
SELECT (
    SELECT DISTINCT d.department_name
    FROM departments d
    WHERE d.location_id = 1700
) AS department_name
FROM dual;
~~~

Nếu nhiều phòng ban khác nhau cùng location, `DISTINCT` vẫn có thể trả nhiều tên và lỗi tiếp tục. Nếu các dòng trùng tên, `DISTINCT` gộp giá trị giống nhau, nhưng không chứng minh dữ liệu gốc là một dòng duy nhất.

Nếu nghiệp vụ cần kiểm tra uniqueness, hãy sửa JOIN condition, data model hoặc constraint. Không dùng `DISTINCT` để giấu duplicate rows mà chưa hiểu nguồn.

## 11. Scalar subquery trong DML

Scalar subquery không chỉ dùng trong SELECT. Nó còn có thể cung cấp giá trị cho một số thao tác DML.

### 11.1. UPDATE với một giá trị tra cứu

~~~sql
UPDATE employees e
SET    e.salary = (
    SELECT r.new_salary
    FROM   employee_salary_rule_lab r
    WHERE  r.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM   employee_salary_rule_lab r
    WHERE  r.employee_id = e.employee_id
);
~~~

`EMPLOYEE_ID` là primary key của bảng rule, nên subquery trả tối đa một dòng. `EXISTS` ngăn UPDATE các nhân viên không có rule. Nếu không có `WHERE EXISTS`, một scalar subquery không trả dòng có thể gán NULL cho cột đích.

### 11.2. UPDATE với aggregate

~~~sql
UPDATE departments d
SET    d.department_name =
       d.department_name || ' (' ||
       (SELECT COUNT(*)
        FROM employees e
        WHERE e.department_id = d.department_id) ||
       ')';
~~~

Ví dụ này minh họa scalar aggregate trong biểu thức cập nhật. Hãy lưu ý đây là UPDATE thật: nếu chạy nhiều lần, chuỗi tên sẽ tiếp tục nối thêm số lượng. Chỉ thực hiện trên lab hoặc trong transaction đã được kiểm soát.

### 11.3. INSERT một giá trị từ subquery

~~~sql
INSERT INTO audit_note_lab (note_id, note_text)
VALUES (
    1,
    (SELECT 'Created by Oracle SQL' FROM dual)
);
~~~

Subquery trả một cột, một dòng, vì vậy có thể cung cấp giá trị cho một cột trong `VALUES`.

### 11.4. Không nhầm scalar subquery expression với INSERT ... SELECT

~~~sql
INSERT INTO employee_archive (employee_id, employee_name)
SELECT employee_id, employee_name
FROM   employees
WHERE  department_id = 50;
~~~

Đây là **subquery làm nguồn cho INSERT**, có thể trả nhiều dòng. Nó không phải scalar subquery expression. Tương tự, subquery trong FROM là inline view, được dùng như một nguồn bảng.

## 12. Scalar subquery và SELECT INTO trong PL/SQL

Scalar subquery là biểu thức SQL. Trong PL/SQL, `SELECT ... INTO` là một cách khác để đưa kết quả query vào biến:

~~~sql
DECLARE
  l_department_name departments.department_name%TYPE;
BEGIN
  SELECT d.department_name
  INTO   l_department_name
  FROM   departments d
  WHERE  d.department_id = 50;

  DBMS_OUTPUT.PUT_LINE(l_department_name);
END;
/
~~~

`SELECT INTO` có semantics khác:

- Không có dòng: `NO_DATA_FOUND`.
- Nhiều hơn một dòng: `TOO_MANY_ROWS`.
- Đúng một dòng: gán các giá trị vào biến.

Trong khi scalar subquery:

- Không có dòng: expression trở thành NULL.
- Nhiều hơn một dòng: `ORA-01427`.
- Một dòng: expression nhận giá trị.

| Tình huống | Scalar subquery expression | PL/SQL SELECT INTO |
| --- | --- | --- |
| 0 row | NULL | `NO_DATA_FOUND` |
| 1 row | Giá trị scalar | Gán biến |
| Nhiều row | `ORA-01427` | `TOO_MANY_ROWS` |
| Nơi sử dụng | Bên trong biểu thức SQL | Statement PL/SQL |

Nếu code cần bắt riêng tình huống không tìm thấy row và xử lý bằng exception, `SELECT INTO` có thể phù hợp. Nếu cần dùng giá trị ngay trong một query lớn, scalar subquery là cách biểu diễn SQL tự nhiên.

## 13. Những nơi scalar subquery không hợp lệ trong Oracle

Oracle cho phép scalar subquery ở hầu hết vị trí cần expression, nhưng có những ngoại lệ được quy định trong SQL Language Reference. Với Oracle 19c, scalar subquery không hợp lệ:

- Là giá trị `DEFAULT` cho cột.
- Là hash expression cho cluster.
- Trong mệnh đề `RETURNING` của DML.
- Là cơ sở của function-based index.
- Trong `CHECK` constraint.
- Trong `GROUP BY`.
- Trong statement không liên quan đến query, ví dụ `CREATE PROFILE`.

Ví dụ không hợp lệ về ý tưởng:

~~~sql
CREATE TABLE order_limit_demo (
    quantity NUMBER,
    CONSTRAINT order_limit_ck
      CHECK (quantity <= (SELECT max_quantity FROM product_rules))
);
~~~

CHECK constraint không được chứa scalar subquery để tra bảng khác. Nếu muốn `quantity` tham chiếu giới hạn sản phẩm, hãy cân nhắc mô hình dữ liệu, foreign key, transaction hoặc logic ứng dụng/procedure phù hợp.

Một số giới hạn khác áp dụng cho từng loại biểu thức/query block; hãy đọc cú pháp của statement cụ thể thay vì suy từ quy tắc scalar subquery tổng quát.

## 14. Hiệu năng và execution plan

Scalar subquery có thể rất rõ ràng, nhưng một query chứa nhiều scalar subquery tương quan cần được đánh giá trên dữ liệu thực.

### 14.1. Chi phí phụ thuộc số dòng và cách optimizer xử lý

Ví dụ:

~~~sql
SELECT e.employee_id,
       (SELECT d.department_name
        FROM departments d
        WHERE d.department_id = e.department_id) AS department_name,
       (SELECT COUNT(*)
        FROM employees e2
        WHERE e2.manager_id = e.employee_id) AS direct_reports
FROM employees e;
~~~

Có hai scalar subquery tương quan. Về mặt logic, mỗi subquery phụ thuộc dòng nhân viên bên ngoài. Optimizer có thể chuyển đổi hoặc chọn phương án thực thi phù hợp; không giả định một cách cố định rằng mỗi subquery sẽ chạy full table scan cho từng row.

### 14.2. Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT e.employee_id,
       (SELECT d.department_name
        FROM departments d
        WHERE d.department_id = e.department_id) AS department_name
FROM employees e;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` cho kế hoạch dự kiến, không nhất thiết là plan thực tế với bind values và runtime statistics. Trong môi trường có quyền, có thể dùng `DBMS_XPLAN.DISPLAY_CURSOR` cùng runtime statistics để xem cursor thực thi. Không cấp quyền quản trị chỉ để chạy ví dụ này; hỏi DBA nếu cần quyền truy cập plan.

### 14.3. Những điều cần quan sát

- Có full scan lặp lại trên bảng con hay không?
- Predicate correlation có index thích hợp không?
- Số row ước lượng và số row thực tế có chênh lệch lớn không?
- Optimizer có unnest/rewrite thành JOIN hay không?
- Scalar aggregate có phải đọc nhiều dữ liệu cho mỗi parent row không?
- Có thể tính aggregate một lần theo group rồi JOIN không?

### 14.4. Viết lại bằng aggregate inline view khi phù hợp

Scalar correlated aggregate:

~~~sql
SELECT e.employee_id,
       (SELECT AVG(e2.salary)
        FROM employees e2
        WHERE e2.department_id = e.department_id) AS dept_avg
FROM employees e;
~~~

Cách viết với inline view:

~~~sql
SELECT e.employee_id,
       a.dept_avg
FROM   employees e
LEFT JOIN (
    SELECT department_id,
           AVG(salary) AS dept_avg
    FROM   employees
    GROUP BY department_id
) a
       ON a.department_id = e.department_id;
~~~

Inline view tổng hợp mỗi phòng ban một lần về mặt logic rồi JOIN kết quả với nhân viên. Hai cách có thể tương đương trong trường hợp này; optimizer cũng có thể tự viết lại. Hãy so sánh plan và kết quả, đồng thời giữ semantics khi `department_id` NULL.

## 15. NULL, aggregate và các phép so sánh trong scalar context

### 15.1. COUNT và MAX cho kết quả khác nhau khi không có row

~~~sql
SELECT
  (SELECT COUNT(*)
   FROM employees
   WHERE department_id = -999) AS employee_count,
  (SELECT MAX(salary)
   FROM employees
   WHERE department_id = -999) AS max_salary
FROM dual;
~~~

Kết quả:

| EMPLOYEE_COUNT | MAX_SALARY |
| ---: | --- |
| 0 | NULL |

Cả hai subquery đều trả một dòng vì là aggregate không GROUP BY. `COUNT(*)` trả 0; `MAX` trả NULL.

### 15.2. Scalar NULL trong phép toán

~~~sql
SELECT 100 + (
    SELECT MAX(salary)
    FROM employees
    WHERE department_id = -999
) AS calculated_value
FROM dual;
~~~

Vì subquery trả NULL, phép cộng `100 + NULL` cho kết quả NULL. Nếu nghiệp vụ muốn coi không có giá trị là 0, có thể dùng `NVL`:

~~~sql
SELECT 100 + NVL((
    SELECT MAX(salary)
    FROM employees
    WHERE department_id = -999
), 0) AS calculated_value
FROM dual;
~~~

Chỉ thay NULL bằng 0 nếu nghiệp vụ thực sự định nghĩa như vậy. “Không có bản ghi” có thể mang ý nghĩa khác “giá trị bằng 0”.

### 15.3. Scalar subquery trả NULL không phải lỗi

Một scalar subquery không có dòng là kết quả hợp lệ, không phát sinh `NO_DATA_FOUND`. Nếu logic cần coi việc không có dòng là lỗi, phải kiểm tra bằng `EXISTS`/`NOT EXISTS`, hoặc dùng `SELECT INTO` trong PL/SQL và bắt exception phù hợp.

## 16. Bộ dữ liệu lab tự chứa

Phần này tạo hai bảng đơn giản để chạy các ví dụ mà không cần schema HR. Chỉ chạy trong schema lab. Nếu tên đã tồn tại, chọn tên khác hoặc dọn object do chính bạn tạo.

### 16.1. Tạo bảng phòng ban và nhân viên

~~~sql
CREATE TABLE sq_dept_lab (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(50 CHAR) NOT NULL
);

CREATE TABLE sq_employee_lab (
    employee_id   NUMBER PRIMARY KEY,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    department_id NUMBER,
    salary        NUMBER(10,2)
);
~~~

### 16.2. Nạp dữ liệu

~~~sql
INSERT INTO sq_dept_lab VALUES (10, 'Finance');
INSERT INTO sq_dept_lab VALUES (20, 'Engineering');
INSERT INTO sq_dept_lab VALUES (30, 'Operations');

INSERT INTO sq_employee_lab VALUES (101, 'An',   10, 1200);
INSERT INTO sq_employee_lab VALUES (102, 'Binh', 10, 1800);
INSERT INTO sq_employee_lab VALUES (103, 'Chi',  20, 3500);
INSERT INTO sq_employee_lab VALUES (104, 'Dung', 20, 4200);
INSERT INTO sq_employee_lab VALUES (105, 'Em',   20, 4200);
INSERT INTO sq_employee_lab VALUES (106, 'Giang', 30, 2200);
INSERT INTO sq_employee_lab VALUES (107, 'Ha',   30, 2500);
INSERT INTO sq_employee_lab VALUES (108, 'Khanh', 99, 1600);
INSERT INTO sq_employee_lab VALUES (109, 'Linh', NULL, 1400);

COMMIT;
~~~

Lab cố ý không khai báo foreign key cho `SQ_EMPLOYEE_LAB.DEPARTMENT_ID`, để có thể quan sát:

- Phòng ban 10, 20, 30 có nhân viên.
- Nhân viên 108 tham chiếu department 99 không tồn tại.
- Nhân viên 109 có department NULL.
- Phòng ban 20 có ba nhân viên, hai người cùng lương 4200.

## 17. Thực hành scalar subquery theo từng trường hợp

### Bài A — Tra tên phòng ban

~~~sql
SELECT e.employee_id,
       e.employee_name,
       (SELECT d.department_name
        FROM sq_dept_lab d
        WHERE d.department_id = e.department_id) AS department_name
FROM sq_employee_lab e
ORDER BY e.employee_id;
~~~

Quan sát:

- Nhân viên 101–107 nhận tên phòng ban.
- Nhân viên 108 nhận NULL vì department 99 không tồn tại.
- Nhân viên 109 nhận NULL vì `department_id` là NULL.

Hai row cuối cùng có cùng giá trị scalar NULL nhưng nguyên nhân khác nhau.

### Bài B — COUNT nhân viên theo phòng ban

~~~sql
SELECT d.department_id,
       d.department_name,
       (SELECT COUNT(*)
        FROM sq_employee_lab e
        WHERE e.department_id = d.department_id) AS employee_count
FROM sq_dept_lab d
ORDER BY d.department_id;
~~~

Kết quả:

| DEPARTMENT_ID | DEPARTMENT_NAME | EMPLOYEE_COUNT |
| ---: | --- | ---: |
| 10 | Finance | 2 |
| 20 | Engineering | 3 |
| 30 | Operations | 2 |

Thử thêm phòng ban không có nhân viên để quan sát `COUNT(*) = 0`.

### Bài C — Lương cao hơn trung bình phòng ban

~~~sql
SELECT e.employee_id,
       e.employee_name,
       e.department_id,
       e.salary,
       (SELECT AVG(e2.salary)
        FROM sq_employee_lab e2
        WHERE e2.department_id = e.department_id) AS dept_avg
FROM sq_employee_lab e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM sq_employee_lab e2
    WHERE e2.department_id = e.department_id
)
ORDER BY e.department_id, e.salary DESC, e.employee_id;
~~~

Subquery trong SELECT list hiển thị trung bình; subquery trong WHERE lọc nhân viên. Hai subquery có cùng ý nghĩa nghiệp vụ nhưng được dùng ở hai vị trí khác nhau. Có thể viết lại bằng inline view tổng hợp để chỉ định nghĩa một lần.

### Bài D — Cố tình gây ORA-01427

~~~sql
SELECT (
    SELECT e.employee_name
    FROM sq_employee_lab e
    WHERE e.department_id = 20
) AS one_employee
FROM dual;
~~~

Department 20 có ba nhân viên, vì vậy subquery trả ba dòng. Scalar context yêu cầu tối đa một dòng và Oracle báo `ORA-01427`.

Chạy subquery riêng:

~~~sql
SELECT employee_id, employee_name, salary
FROM sq_employee_lab
WHERE department_id = 20
ORDER BY employee_id;
~~~

### Bài E — Chọn một nhân viên theo quy tắc rõ ràng

~~~sql
SELECT (
    SELECT e.employee_name
    FROM sq_employee_lab e
    WHERE e.department_id = 20
    ORDER BY e.salary DESC NULLS LAST, e.employee_id
    FETCH FIRST 1 ROW ONLY
) AS highest_paid_employee
FROM dual;
~~~

Hai người có lương 4200; `employee_id` nhỏ hơn được chọn do tie-breaker. Thay `ORDER BY` hoặc bỏ tie-breaker để hiểu vì sao cần định nghĩa rõ quy tắc chọn một row.

### Bài F — So sánh scalar subquery với LEFT JOIN

~~~sql
-- Scalar subquery:
SELECT e.employee_id,
       (SELECT d.department_name
        FROM sq_dept_lab d
        WHERE d.department_id = e.department_id) AS department_name
FROM sq_employee_lab e
ORDER BY e.employee_id;

-- LEFT JOIN:
SELECT e.employee_id,
       d.department_name
FROM sq_employee_lab e
LEFT JOIN sq_dept_lab d
       ON d.department_id = e.department_id
ORDER BY e.employee_id;
~~~

Hai cách giữ nhân viên không có phòng ban tương ứng. Nếu thêm duplicate department ID vào bảng tra cứu, PK sẽ chặn insert; nếu bảng không có unique key, scalar subquery có thể lỗi còn JOIN có thể nhân đôi row.

### Bài G — Dọn lab (tùy chọn)

~~~sql
-- Chỉ xóa các bảng do chính bạn tạo trong schema lab.
DROP TABLE sq_employee_lab PURGE;
DROP TABLE sq_dept_lab PURGE;
~~~

DDL có implicit commit và DROP không được hoàn tác bằng `ROLLBACK`. Bỏ qua bước này nếu muốn giữ bảng để luyện tập.

## 18. Những lỗi và cách khắc phục

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `ORA-01427` | Scalar subquery trả nhiều hơn một row | Kiểm tra dữ liệu và predicate; dùng khóa duy nhất, aggregate, TOP-1 có ORDER BY hoặc JOIN tùy nghiệp vụ |
| Subquery trả NULL dù tưởng có dữ liệu | Không có row thỏa predicate; outer reference NULL; sai alias/kiểu so sánh | Chạy riêng subquery với giá trị cụ thể; kiểm tra alias và dữ liệu |
| `IS NULL` không phân biệt được row thiếu và cột NULL | Cả hai trường hợp đều tạo scalar NULL | Dùng EXISTS hoặc LEFT JOIN với khóa để phân biệt |
| UPDATE biến cột thành NULL | Scalar subquery không tìm thấy row cho một row đích | Dùng WHERE EXISTS, NVL theo nghiệp vụ hoặc xử lý trường hợp thiếu rõ ràng |
| Scalar subquery lỗi sau khi thêm dữ liệu | Cardinality trước đây tình cờ là 1, giờ có duplicate | Kiểm tra unique key và predicate; không che lỗi bằng ROWNUM |
| Kết quả TOP-1 thay đổi | Thiếu ORDER BY hoặc thiếu tie-breaker | Định nghĩa thứ tự xác định bằng khóa phân xử |
| Query chậm | Subquery tương quan có access path không phù hợp hoặc aggregate tốn kém | Xem execution plan, index, cardinality; so sánh với JOIN/aggregate inline view |
| Cột tham chiếu bị hiểu nhầm | Tên cột trùng giữa query trong và ngoài | Qualify mọi cột bằng alias |
| `NOT IN` trả không dòng như dự kiến | Tập subquery chứa NULL | Cân nhắc NOT EXISTS và điều kiện correlation rõ ràng |

## 19. Checklist tư duy trước khi viết scalar subquery

1. **Tôi cần một giá trị hay một tập dòng?** Nếu cần tập dòng, dùng IN/EXISTS/JOIN/inline view phù hợp.
2. **Subquery chọn đúng một cột chưa?** Scalar expression chỉ nhận một giá trị.
3. **Điều kiện có bảo đảm tối đa một dòng không?** Ưu tiên PK/UNIQUE hoặc aggregate đúng mục đích.
4. **Nếu không có dòng thì NULL có đúng nghiệp vụ không?** Nếu không, phải xử lý riêng.
5. **Nếu có nhiều dòng thì điều gì đúng?** Lỗi cardinality có thể là tín hiệu lỗi dữ liệu, hay cần aggregate/top-one, hay thực chất cần JOIN.
6. **Nếu chọn một dòng, thứ tự chọn có xác định không?** Dùng ORDER BY và tie-breaker.
7. **Subquery có tương quan không?** Qualify alias và kiểm tra plan.
8. **Có thể dùng JOIN hoặc aggregate inline view rõ hơn không?** Chọn cấu trúc dễ hiểu và đúng semantics.
9. **DML có thể gán NULL khi subquery không có dòng không?** Kiểm tra UPDATE SET và phạm vi WHERE.
10. **Có phụ thuộc NULL semantics không?** Chuyển kiểu và xử lý NULL rõ ràng.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Scalar subquery phải trả bao nhiêu cột và tối đa bao nhiêu dòng?

**Câu 2.** Nếu scalar subquery không trả dòng nào, Oracle trả lỗi `NO_DATA_FOUND` hay giá trị nào?

**Câu 3.** Nếu scalar subquery trả ba dòng, lỗi Oracle thường gặp là gì?

**Câu 4.** Vì sao `SELECT MAX(salary) FROM employees WHERE department_id = -1` vẫn có thể dùng như scalar subquery dù không có nhân viên?

**Câu 5.** Aggregate có `GROUP BY department_id` có bảo đảm một dòng không?

**Câu 6.** Khi nào dùng `IN` thay vì `=` với subquery?

**Câu 7.** Tại sao `IS NULL` trên scalar subquery không phân biệt “không có row” và “cột có giá trị NULL”?

**Câu 8.** Một correlated subquery có bắt buộc Oracle chạy full scan bảng con cho mỗi row ngoài không?

**Câu 9.** Vì sao thêm `ROWNUM = 1` vào scalar subquery có thể che một vấn đề dữ liệu?

**Câu 10.** Nếu cần tên nhân viên có lương cao nhất trong một phòng ban và có thể đồng lương, cần thêm điều gì để chọn một người ổn định?

**Câu 11.** So sánh scalar subquery không tìm thấy row với LEFT JOIN không tìm thấy row.

**Câu 12.** Trong UPDATE, điều gì có thể xảy ra nếu scalar subquery trong SET không trả dòng?

<details>
<summary>Gợi ý đáp án</summary>

1. Một cột, tối đa một dòng.
2. Giá trị scalar là SQL NULL; không phát sinh `NO_DATA_FOUND` như SELECT INTO.
3. `ORA-01427: single-row subquery returns more than one row`.
4. Aggregate không GROUP BY trả đúng một dòng; `MAX` là NULL khi tập đầu vào rỗng.
5. Không. Mỗi group có thể tạo một dòng; có thể có nhiều group.
6. Khi subquery có thể trả nhiều giá trị và cần kiểm tra membership trong tập.
7. Cả hai tình huống đều cho giá trị scalar NULL; dùng EXISTS hoặc LEFT JOIN với khóa để phân biệt.
8. Không. Subquery được hiểu là correlated theo từng row, nhưng optimizer có thể rewrite thành JOIN hoặc phương án tương đương.
9. Nó chọn một row tùy access path nếu không ORDER BY, làm mất tín hiệu rằng điều kiện vốn trả nhiều dòng.
10. ORDER BY lương giảm dần và thêm khóa duy nhất làm tie-breaker; FETCH FIRST 1 ROW ONLY trên 12c+.
11. Scalar subquery cho NULL trong expression; LEFT JOIN giữ row bên ngoài và các cột phía trong là NULL; INNER JOIN có thể loại row ngoài.
12. Giá trị cột đích có thể được gán NULL; dùng EXISTS hoặc logic xử lý thiếu dữ liệu nếu cần.

</details>

## 21. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — Scalar Subquery Expressions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Scalar-Subquery-Expressions.html): định nghĩa scalar subquery, quy tắc zero-row/one-row/multi-row và vị trí không được sử dụng.
2. [Oracle Database 19c SQL Language Reference — Using Subqueries](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Using-Subqueries.html): correlated subquery, inline view, cách đặt alias và mục đích sử dụng subquery.
3. [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): biểu thức SELECT, subquery, JOIN và row limiting clause.
4. [Oracle Database 19c Database Error Messages — ORA-01427](https://docs.oracle.com/en/error-help/db/ora-01427/): nguyên nhân và hướng xử lý khi single-row subquery trả nhiều dòng.
5. [Oracle Database 19c SQL Language Reference — UPDATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/UPDATE.html): subquery trong UPDATE SET và hành vi khi subquery không trả dòng.
6. [Oracle Database 19c SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html): điều kiện kiểm tra sự tồn tại.
7. [Oracle Database 19c SQL Language Reference — IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html): membership condition với tập giá trị.
8. [Oracle Database 19c SQL Language Reference — Comparison Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Comparison-Conditions.html): so sánh với ANY/ALL và tập kết quả.
9. [Oracle Database 19c SQL Language Reference — ROWNUM Pseudocolumn](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html): giới hạn row theo query block; cần kết hợp đúng với ORDER BY nếu chọn TOP-1.
10. [Oracle Database 19c SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): execution plan, optimizer transformations và cách đánh giá hiệu năng.

**Nguyên tắc cần nhớ:** Scalar subquery là một **biểu thức một giá trị**, vì vậy phải chọn đúng **một cột và tối đa một dòng**. Khóa duy nhất và aggregate không GROUP BY là những cách bảo đảm cardinality tự nhiên. Khi không có dòng, giá trị là NULL; khi có nhiều dòng, Oracle báo `ORA-01427`. Nếu cần chọn một dòng theo thứ tự, phải nêu rõ ORDER BY và tie-breaker; nếu thực sự cần nhiều dòng, hãy dùng JOIN hoặc điều kiện tập hợp thay vì ép truy vấn thành scalar.

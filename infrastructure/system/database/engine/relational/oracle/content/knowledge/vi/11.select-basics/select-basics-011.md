# Đọc kết quả rỗng, giá trị NULL và số dòng bị nhân bản

Khi chạy một câu `SELECT` trong Oracle, kết quả có thể là **không có hàng nào**, có hàng nhưng một số cột mang giá trị **`NULL`**, hoặc có **nhiều hàng hơn dự kiến** vì phép nối dữ liệu tạo ra nhiều tổ hợp. Ba hiện tượng này thường bị gọi chung là “query trả sai dữ liệu”, nhưng nguyên nhân và cách xử lý hoàn toàn khác nhau.

Ví dụ:

- Tìm nhân viên có mã không tồn tại và nhận **0 hàng**: tập kết quả rỗng.
- Tìm thấy một nhân viên nhưng cột `MANAGER_ID` chưa được gán và nhận **1 hàng với MANAGER_ID = NULL**: kết quả có hàng, giá trị bị thiếu.
- Nối một khách hàng có ba số điện thoại với hai đơn hàng và nhận sáu hàng: **số dòng bị nhân bản do quan hệ 1-nhiều**, có thể là đúng theo quan hệ hoặc là lỗi khi thiết kế query.

Mục tiêu của bài học:

1. Phân biệt **empty result set**, **NULL**, chuỗi rỗng và LOB rỗng.
2. Hiểu cách Oracle xử lý NULL trong điều kiện, aggregate, join, subquery và hàm chuyển đổi.
3. Tìm nguyên nhân một hàng cha xuất hiện nhiều lần sau `JOIN`.
4. Chọn đúng công cụ: `IS NULL`, `COUNT`, `EXISTS`, `NOT EXISTS`, pre-aggregation, `DISTINCT` hoặc analytic function.
5. Biết cách kiểm tra từng giai đoạn để query trả đúng số hàng và đúng ý nghĩa nghiệp vụ.

## 1. Ba hiện tượng khác nhau

| Hiện tượng | Kết quả quan sát | Ý nghĩa |
| --- | --- | --- |
| **Kết quả rỗng** | Không có hàng nào được trả về | Không có hàng thỏa điều kiện hoặc nguồn dữ liệu không tạo ra hàng |
| **Có hàng chứa NULL** | Có hàng, nhưng một hay nhiều cột hiển thị `(null)` | Hàng tồn tại; giá trị của cột không được biết/không được cung cấp theo ngữ nghĩa NULL |
| **Số hàng bị nhân bản** | Một khóa cha xuất hiện ở nhiều hàng kết quả | Join tạo nhiều cặp phù hợp, hoặc phép chiếu bỏ các cột khiến các hàng khác nhau trông giống nhau |

Ba ví dụ đơn giản:

```sql
-- 0 hàng nếu không có employee_id = 999.
SELECT employee_id, full_name
FROM lab_employees
WHERE employee_id = 999;

-- Có thể trả 1 hàng; manager_id có thể là NULL.
SELECT employee_id, full_name, manager_id
FROM lab_employees
WHERE employee_id = 1;

-- Có thể trả nhiều hàng cho một employee nếu có nhiều số điện thoại.
SELECT e.employee_id, e.full_name, p.phone_number
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
WHERE e.employee_id = 1;
```

**Không có hàng** không giống **một hàng với mọi cột NULL**. Nếu ứng dụng không phân biệt hai trường hợp này, nó có thể hiển thị sai trạng thái nghiệp vụ hoặc ghi đè dữ liệu đang có.

## 2. Dữ liệu lab để tái tạo các trường hợp

Các ví dụ dùng ba bảng: phòng ban, nhân viên và số điện thoại nhân viên. Một nhân viên có thể chưa có phòng ban, chưa có lương hoặc có nhiều số điện thoại.

### 2.1. Tạo bảng trong schema thực hành

Chỉ chạy DDL dưới đây trong **schema lab do bạn sở hữu**, có quyền tạo bảng và quota tablespace. Nếu đã có bảng cùng tên, hãy dùng schema thực hành khác thay vì xóa bảng không rõ chủ sở hữu.

```sql
CREATE TABLE lab_departments (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE lab_employees (
    employee_id   NUMBER PRIMARY KEY,
    full_name     VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER,
    manager_id    NUMBER,
    salary        NUMBER(12, 2),
    active_flag   CHAR(1) DEFAULT 'Y' NOT NULL,
    CONSTRAINT fk_lab_emp_dept
        FOREIGN KEY (department_id)
        REFERENCES lab_departments (department_id),
    CONSTRAINT fk_lab_emp_manager
        FOREIGN KEY (manager_id)
        REFERENCES lab_employees (employee_id),
    CONSTRAINT ck_lab_emp_active
        CHECK (active_flag IN ('Y', 'N'))
);

CREATE TABLE lab_employee_phones (
    phone_id      NUMBER PRIMARY KEY,
    employee_id   NUMBER NOT NULL,
    phone_number  VARCHAR2(30 CHAR) NOT NULL,
    phone_type    VARCHAR2(20 CHAR),
    CONSTRAINT fk_lab_phone_employee
        FOREIGN KEY (employee_id)
        REFERENCES lab_employees (employee_id)
);
```

### 2.2. Thêm dữ liệu có chủ ý

```sql
INSERT INTO lab_departments VALUES (10, 'Kỹ thuật');
INSERT INTO lab_departments VALUES (20, 'Kinh doanh');
INSERT INTO lab_departments VALUES (30, 'Nhân sự');
INSERT INTO lab_departments VALUES (40, 'Pháp chế');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (1, 'An', 10, NULL, 5000, 'Y');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (2, 'Bình', 10, 1, 3000, 'Y');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (3, 'Chi', 10, 1, NULL, 'Y');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (4, 'Dũng', 20, NULL, 2800, 'Y');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (5, 'Hà', 20, 4, 2800, 'N');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (6, 'Lan', NULL, NULL, 1800, 'Y');

INSERT INTO lab_employee_phones VALUES (101, 1, '0900000001', 'MOBILE');
INSERT INTO lab_employee_phones VALUES (102, 1, '0280000001', 'OFFICE');
INSERT INTO lab_employee_phones VALUES (103, 2, '0900000002', 'MOBILE');
INSERT INTO lab_employee_phones VALUES (104, 4, '0900000004', 'MOBILE');
INSERT INTO lab_employee_phones VALUES (105, 4, '0280000004', 'OFFICE');

COMMIT;
```

Tập dữ liệu có các đặc điểm:

| Nhân viên | Phòng ban | Quản lý | Lương | Điện thoại |
| --- | --- | --- | ---: | ---: |
| An (1) | Kỹ thuật (10) | `NULL` | 5000 | 2 |
| Bình (2) | Kỹ thuật (10) | An (1) | 3000 | 1 |
| Chi (3) | Kỹ thuật (10) | An (1) | `NULL` | 0 |
| Dũng (4) | Kinh doanh (20) | `NULL` | 2800 | 2 |
| Hà (5) | Kinh doanh (20) | Dũng (4) | 2800 | 0 |
| Lan (6) | Chưa gán | `NULL` | 1800 | 0 |

Phòng **Pháp chế (40)** không có nhân viên. Dữ liệu này đủ để quan sát kết quả rỗng, NULL, outer join, join 1-nhiều và nhân bản do nối nhiều bảng con.

## 3. Kết quả rỗng: query không trả về hàng nào

Một result set rỗng có nghĩa **không có hàng nào thỏa điều kiện của truy vấn**. Ví dụ:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE employee_id = 999;
```

Nếu bảng không có ID 999, client hiển thị “no rows selected” hoặc một bảng kết quả không có hàng dữ liệu. Điều đó không phải lỗi SQL: câu lệnh hợp lệ và điều kiện chỉ đơn giản không tìm thấy bản ghi.

### 3.1. Phân biệt bảng rỗng với điều kiện không khớp

```sql
-- Kiểm tra số hàng của toàn bảng.
SELECT COUNT(*) AS total_rows
FROM lab_employees;

-- Kiểm tra có hàng phù hợp điều kiện hay không.
SELECT COUNT(*) AS matching_rows
FROM lab_employees
WHERE department_id = 999;
```

Với lab, kết quả lần lượt là 6 và 0. Câu truy vấn thứ hai **vẫn trả một hàng** có giá trị `MATCHING_ROWS = 0` vì `COUNT(*)` là aggregate không có `GROUP BY`. Đây là điểm rất quan trọng:

- `SELECT employee_id ... WHERE ...` có thể trả **0 hàng**.
- `SELECT COUNT(*) ... WHERE ...` không có `GROUP BY` vẫn trả **1 hàng với COUNT = 0**.

Ví dụ tiếp:

```sql
SELECT SUM(salary) AS salary_total
FROM lab_employees
WHERE department_id = 999;
```

Kết quả là **1 hàng với `SALARY_TOTAL = NULL`**, vì `SUM` trên tập không có giá trị phù hợp trả NULL. Vì vậy, đừng suy ra “SUM trả NULL” là query không có hàng; hãy quan sát **số hàng kết quả** và **giá trị cột** riêng biệt.

### 3.2. Aggregate không GROUP BY và có GROUP BY

```sql
-- Không có GROUP BY: COUNT trả một hàng, kể cả khi nguồn không có hàng.
SELECT COUNT(*) AS row_count
FROM lab_employees
WHERE department_id = 999;

-- Có GROUP BY: không có nhóm nào được tạo, nên không có hàng kết quả.
SELECT department_id, COUNT(*) AS row_count
FROM lab_employees
WHERE department_id = 999
GROUP BY department_id;
```

Truy vấn đầu trả `0`. Truy vấn sau trả **0 hàng**, vì không có đầu vào để hình thành nhóm `DEPARTMENT_ID`. Đây là khác biệt giữa **aggregate trên toàn tập** và **aggregate theo từng nhóm**.

### 3.3. `HAVING` có thể loại hết nhóm

```sql
SELECT department_id, COUNT(*) AS employee_count
FROM lab_employees
GROUP BY department_id
HAVING COUNT(*) > 100;
```

Các nhóm vẫn được tạo, nhưng không nhóm nào vượt 100 nhân viên; kết quả cuối là **0 hàng**. Nếu muốn kiểm tra vì sao, bỏ `HAVING` để xem số liệu từng nhóm trước khi lọc.

### 3.4. Phân biệt “không tìm thấy” và “không được phép nhìn thấy”

Một bảng không xuất hiện trong kết quả truy vấn có thể vì:

- Không tồn tại trong schema/PDB hiện tại.
- Có tên khác, kể cả identifier được tạo bằng dấu nháy kép.
- Bạn đang ở sai PDB hoặc schema.
- Tài khoản không có quyền truy cập, nên dictionary view theo phạm vi `USER_*`/`ALL_*` không hiển thị nó.
- Điều kiện lọc hoặc phép join loại hết các hàng.

Khi điều tra, xác nhận ngữ cảnh trước:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

Sau đó kiểm tra object trong phạm vi quyền hiện có. **0 hàng từ `ALL_TABLES` không phải bằng chứng tuyệt đối rằng table không tồn tại trên toàn database**; nó có thể nằm ngoài phạm vi bạn được phép thấy.

## 4. NULL: hàng có tồn tại nhưng giá trị không được xác định

`NULL` biểu diễn trạng thái **không có giá trị được biết/cung cấp** cho một thuộc tính. Nó không phải số 0, không phải chuỗi `'NULL'` và cũng không nhất thiết có nghĩa “không áp dụng”. Ý nghĩa nghiệp vụ phải được xác định theo cột.

Ví dụ:

```sql
SELECT employee_id, full_name, manager_id, salary
FROM lab_employees
WHERE employee_id IN (1, 3);
```

An (1) có `MANAGER_ID NULL` vì chưa có quản lý được gán. Chi (3) có `SALARY NULL` vì mức lương chưa được ghi nhận. Hai hàng đều tồn tại; chỉ một số thuộc tính chưa có giá trị.

### 4.1. NULL không bằng bất kỳ giá trị nào, kể cả NULL

Trong SQL, phép so sánh với NULL thường cho kết quả **UNKNOWN**:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE manager_id = NULL;
```

Không có hàng nào được chọn vì `manager_id = NULL` không trả `TRUE`. Kể cả:

```sql
SELECT *
FROM dual
WHERE NULL = NULL;
```

cũng không trả hàng. Để kiểm tra NULL, dùng:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE manager_id IS NULL;
```

Và để tìm người đã có quản lý:

```sql
SELECT employee_id, full_name, manager_id
FROM lab_employees
WHERE manager_id IS NOT NULL;
```

### 4.2. Logic ba giá trị: TRUE, FALSE, UNKNOWN

SQL dùng logic ba giá trị khi có NULL:

| Biểu thức | Kết quả |
| --- | --- |
| `5 = 5` | TRUE |
| `5 = 3` | FALSE |
| `5 = NULL` | UNKNOWN |
| `NULL = NULL` | UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT NULL` | FALSE |

`WHERE` và `HAVING` chỉ giữ hàng/nhóm khi điều kiện là **TRUE**. `FALSE` và `UNKNOWN` đều không được giữ.

Ví dụ:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary > 2000;
```

Chi có `SALARY NULL` nên `NULL > 2000` là UNKNOWN; Chi không được trả về. Nếu nghiệp vụ muốn bao gồm người chưa có lương để xử lý riêng, cần viết điều kiện:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary > 2000
   OR salary IS NULL;
```

### 4.3. NOT, AND và OR khi có UNKNOWN

| A | B | `A AND B` | `A OR B` | `NOT A` |
| --- | --- | --- | --- | --- |
| TRUE | UNKNOWN | UNKNOWN | TRUE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN | TRUE |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

Ví dụ, `NOT (salary > 2000)` **không bao gồm** hàng có `SALARY NULL`, vì `NOT UNKNOWN` vẫn là UNKNOWN:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE NOT (salary > 2000);
```

Nếu muốn bao gồm cả người có lương không vượt 2000 và người chưa có lương:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary <= 2000
   OR salary IS NULL;
```

### 4.4. Dùng NVL, COALESCE và NULLIF đúng ý nghĩa

**`NVL`** thay một giá trị NULL bằng giá trị mặc định:

```sql
SELECT
    employee_id,
    full_name,
    salary,
    NVL(salary, 0) AS salary_for_display
FROM lab_employees;
```

**`COALESCE`** trả về biểu thức đầu tiên không NULL:

```sql
SELECT
    employee_id,
    COALESCE(
        TO_CHAR(manager_id),
        'Chua gan quan ly'
    ) AS manager_display
FROM lab_employees;
```

**`NULLIF(a,b)`** trả NULL nếu hai biểu thức bằng nhau, nếu không trả biểu thức thứ nhất:

```sql
SELECT
    NULLIF(salary, 0) AS salary_or_null
FROM lab_employees;
```

Không dùng `NVL(salary,0)` một cách vô thức trong mọi phép tính. Nếu NULL có nghĩa **chưa biết lương**, thay bằng 0 có thể làm báo cáo tổng lương hoặc trung bình sai về mặt nghiệp vụ. Chỉ thay NULL bằng 0 khi nghiệp vụ xác định rằng “không có giá trị” phải được diễn giải như số 0.

### 4.5. NVL ở trong hay ngoài aggregate khác nhau

```sql
SELECT
    SUM(salary) AS sum_ignore_null,
    SUM(NVL(salary, 0)) AS sum_null_as_zero,
    NVL(SUM(salary), 0) AS display_sum
FROM lab_employees
WHERE department_id = 999;
```

Trong trường hợp không có hàng phù hợp:

- `SUM(SALARY)` trả NULL.
- `SUM(NVL(SALARY,0))` cũng trả NULL vì **không có hàng đầu vào** để áp dụng NVL.
- `NVL(SUM(SALARY),0)` trả 0 vì NVL được áp dụng lên kết quả aggregate NULL.

Nếu có hàng nhưng mọi giá trị salary đều NULL, `SUM(NVL(SALARY,0))` có thể trả 0, còn `SUM(SALARY)` trả NULL. Đây là hai câu hỏi nghiệp vụ khác nhau: **không có hàng** và **có hàng nhưng chưa có số liệu**.

### 4.6. Chuỗi rỗng trong Oracle

Với kiểu chuỗi ký tự SQL thông thường như `VARCHAR2`, Oracle hiện xử lý chuỗi có độ dài bằng 0 (`''`) như `NULL`:

```sql
SELECT
    CASE WHEN '' IS NULL THEN 'EMPTY_IS_NULL'
         ELSE 'NOT_NULL' END AS empty_string_test
FROM dual;
```

Khi chèn:

```sql
INSERT INTO lab_employees
    (employee_id, full_name, department_id, salary, active_flag)
VALUES
    (7, 'Quang', 10, NULL, 'Y');

COMMIT;
```

Nếu một ứng dụng gửi chuỗi rỗng cho cột `VARCHAR2` nullable, database có thể lưu NULL theo ngữ nghĩa Oracle. Đừng dùng `= ''` để tìm chuỗi rỗng; dùng `IS NULL` khi đó là cách diễn giải đúng trong Oracle. **Không khái quát quy tắc này sang mọi kiểu dữ liệu**: LOB rỗng như `EMPTY_CLOB()` khác NULL; các kiểu và hành vi tương lai cần đối chiếu tài liệu release.

### 4.7. NULL và LOB rỗng

Đối với LOB, cần phân biệt:

- `NULL`: không có locator/giá trị LOB.
- `EMPTY_CLOB()` hoặc `EMPTY_BLOB()`: locator LOB tồn tại nhưng nội dung có độ dài 0.

Ví dụ:

```sql
CREATE TABLE lab_lob_state (
    id      NUMBER PRIMARY KEY,
    content CLOB
);

INSERT INTO lab_lob_state VALUES (1, NULL);
INSERT INTO lab_lob_state VALUES (2, EMPTY_CLOB());

SELECT id,
       CASE WHEN content IS NULL THEN 'NULL'
            ELSE 'NOT NULL' END AS lob_state,
       DBMS_LOB.GETLENGTH(content) AS lob_length
FROM lab_lob_state
ORDER BY id;
```

Kết quả logic:

| ID | LOB_STATE | LOB_LENGTH |
| ---: | --- | ---: |
| 1 | NULL | NULL |
| 2 | NOT NULL | 0 |

Một số API sửa internal LOB yêu cầu locator đã khởi tạo; locator NULL không thể được coi như LOB rỗng. Ứng dụng phải xác định riêng trạng thái “chưa upload”, “upload file rỗng” và “đã upload nội dung”.

## 5. NULL trong JOIN

### 5.1. NULL không khớp với NULL bằng phép bằng thông thường

Giả sử bảng nhân viên có `DEPARTMENT_ID NULL`:

```sql
SELECT e.employee_id, e.full_name, d.department_name
FROM lab_employees e
JOIN lab_departments d
  ON d.department_id = e.department_id;
```

Nhân viên Lan không xuất hiện vì `NULL = department_id` là UNKNOWN. Inner join chỉ giữ cặp hàng mà điều kiện ON là TRUE.

### 5.2. LEFT JOIN tạo hàng bổ sung với cột NULL

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
```

Phòng Pháp chế (40) không có nhân viên nhưng vẫn xuất hiện với `E.EMPLOYEE_ID` và `E.FULL_NAME` là NULL. Những giá trị NULL này do **outer join tạo ra**, không phải hàng nhân viên thật có các cột đó NULL.

### 5.3. Điều kiện ở ON và WHERE có thể làm mất hàng outer join

Muốn giữ tất cả phòng ban, nhưng chỉ ghép nhân viên active:

```sql
SELECT d.department_id, d.department_name, e.employee_id
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

Nếu chuyển điều kiện sang WHERE:

```sql
SELECT d.department_id, d.department_name, e.employee_id
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

Các hàng outer join được bổ sung có `E.ACTIVE_FLAG NULL`; điều kiện `NULL = 'Y'` là UNKNOWN, nên bị WHERE loại. Truy vấn thứ hai vì thế không còn giữ phòng ban không có nhân viên active. Đây là nguyên nhân phổ biến của việc “LEFT JOIN mà kết quả giống INNER JOIN”.

### 5.4. Đếm hàng sau LEFT JOIN

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS joined_row_count,
    COUNT(e.employee_id) AS employee_count
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Với phòng 40:

- `COUNT(*) = 1` vì kết quả outer join có một hàng đại diện cho phòng ban.
- `COUNT(e.employee_id) = 0` vì cột khóa của phía phải là NULL trong hàng bổ sung.

Nếu cần đếm **nhân viên**, hãy đếm một cột phía phải **không NULL đối với mọi hàng thật**, thường là primary key. Không dùng `COUNT(*)` trong outer join rồi gọi kết quả đó là số nhân viên.

## 6. Số dòng bị nhân bản: hiểu quan hệ 1-nhiều

Một hàng cha xuất hiện nhiều lần sau join không nhất thiết là lỗi. Nếu một nhân viên có hai số điện thoại, join nhân viên với số điện thoại tạo **hai hàng** để biểu diễn hai cặp quan hệ.

### 6.1. Một nhân viên, nhiều điện thoại

```sql
SELECT
    e.employee_id,
    e.full_name,
    p.phone_id,
    p.phone_number,
    p.phone_type
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
WHERE e.employee_id = 1
ORDER BY p.phone_id;
```

Kết quả có hai hàng:

| EMPLOYEE_ID | FULL_NAME | PHONE_ID | PHONE_NUMBER | PHONE_TYPE |
| ---: | --- | ---: | --- | --- |
| 1 | An | 101 | 0900000001 | MOBILE |
| 1 | An | 102 | 0280000001 | OFFICE |

`EMPLOYEE_ID` lặp lại nhưng kết quả đúng: query đang trả **một hàng cho mỗi điện thoại**. Nếu màn hình chỉ muốn một dòng mỗi nhân viên, phải xác định cách biểu diễn danh sách điện thoại (aggregate, subquery, JSON/XML, hoặc chỉ chọn một loại điện thoại theo quy tắc), không đơn giản xóa các hàng tùy ý.

### 6.2. Vì sao hai bảng con 1-nhiều làm số hàng tăng theo tích?

Giả sử một nhân viên có:

- 2 số điện thoại trong `LAB_EMPLOYEE_PHONES`.
- 3 kỹ năng trong một bảng `LAB_EMPLOYEE_SKILLS`.

Nếu nối trực tiếp cả hai bảng con theo employee:

```sql
SELECT
    e.employee_id,
    p.phone_number,
    s.skill_name
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
JOIN lab_employee_skills s
  ON s.employee_id = e.employee_id
WHERE e.employee_id = 1;
```

Nếu nhân viên có 2 điện thoại và 3 kỹ năng, kết quả có **2 × 3 = 6 hàng**. Mỗi số điện thoại được kết hợp với từng kỹ năng. Đây là Cartesian multiplication **bên trong quan hệ của cùng một nhân viên**, không phải Oracle tự nhân bản sai.

Sơ đồ:

```text
                 EMPLOYEE 1
                 /       \
                /         \
       2 PHONE ROWS      3 SKILL ROWS
                \         /
                 \       /
            JOIN ON EMPLOYEE_ID
                      |
                      v
          2 x 3 = 6 combination rows
```

Nếu sau đó chạy `COUNT(p.phone_id)`, mỗi điện thoại sẽ bị đếm ba lần; chạy `SUM(p.some_amount)` có thể nhân tổng tiền lên theo số kỹ năng. Đây là lỗi báo cáo thường gặp khi nối nhiều quan hệ 1-nhiều mà không gom từng bảng con trước.

## 7. Phân biệt hàng trùng thật với hàng trông giống nhau

Có ít nhất ba khái niệm khác nhau:

1. **Duplicate key:** cùng giá trị khóa nghiệp vụ/khóa kỹ thuật xuất hiện ở nhiều hàng. Có thể vi phạm uniqueness nếu đó là key được ràng buộc.
2. **Duplicate projected rows:** các hàng khác nhau ở cột không được SELECT, nhưng phần cột được hiển thị giống nhau.
3. **Repeated parent row after join:** cùng một hàng cha ghép với nhiều hàng con, nên khóa cha lặp là đúng theo quan hệ.

Ví dụ:

```sql
SELECT e.employee_id, e.full_name
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
WHERE e.employee_id = 1;
```

Hai hàng kết quả có cùng `EMPLOYEE_ID` và `FULL_NAME` vì truy vấn bỏ qua thông tin điện thoại. Nhưng nguồn join có hai hàng con khác nhau.

Nếu thêm `DISTINCT`:

```sql
SELECT DISTINCT e.employee_id, e.full_name
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
WHERE e.employee_id = 1;
```

Kết quả còn một hàng. Điều này phù hợp **nếu mục tiêu chỉ là danh sách nhân viên có ít nhất một số điện thoại**; nhưng nó che mất số lượng điện thoại và có thể che một join sai nếu người viết không hiểu nguyên nhân.

## 8. Chọn cách truy vấn đúng theo mục tiêu

### 8.1. Chỉ cần biết có ít nhất một hàng con: dùng EXISTS

Nếu yêu cầu là “lấy nhân viên có ít nhất một số điện thoại”, đừng join rồi DISTINCT nếu không cần dữ liệu điện thoại:

```sql
SELECT e.employee_id, e.full_name
FROM lab_employees e
WHERE EXISTS (
    SELECT 1
    FROM lab_employee_phones p
    WHERE p.employee_id = e.employee_id
)
ORDER BY e.employee_id;
```

`EXISTS` kiểm tra sự tồn tại của hàng phù hợp và không nhân bản hàng nhân viên khi có nhiều điện thoại. Oracle có thể biến đổi nó thành semi-join trong execution plan.

### 8.2. Cần số lượng con: GROUP BY bảng con trước

```sql
WITH phone_counts AS (
    SELECT employee_id, COUNT(*) AS phone_count
    FROM lab_employee_phones
    GROUP BY employee_id
)
SELECT
    e.employee_id,
    e.full_name,
    NVL(pc.phone_count, 0) AS phone_count
FROM lab_employees e
LEFT JOIN phone_counts pc
  ON pc.employee_id = e.employee_id
ORDER BY e.employee_id;
```

CTE `PHONE_COUNTS` có tối đa một hàng cho mỗi `EMPLOYEE_ID`. Nối nó với nhân viên không nhân bản hàng cha. `NVL` chuyển trường hợp không có hàng trong CTE thành số 0 vì ở đây nghiệp vụ **đếm số điện thoại** và không có hàng con có nghĩa là số lượng bằng 0.

### 8.3. Nối nhiều bảng con: aggregate riêng từng bảng

Giả sử có thêm bảng `LAB_EMPLOYEE_SKILLS`. Cách an toàn cho báo cáo số lượng:

```sql
WITH phone_counts AS (
    SELECT employee_id, COUNT(*) AS phone_count
    FROM lab_employee_phones
    GROUP BY employee_id
),
skill_counts AS (
    SELECT employee_id, COUNT(*) AS skill_count
    FROM lab_employee_skills
    GROUP BY employee_id
)
SELECT
    e.employee_id,
    e.full_name,
    NVL(p.phone_count, 0) AS phone_count,
    NVL(s.skill_count, 0) AS skill_count
FROM lab_employees e
LEFT JOIN phone_counts p
  ON p.employee_id = e.employee_id
LEFT JOIN skill_counts s
  ON s.employee_id = e.employee_id
ORDER BY e.employee_id;
```

Mỗi CTE đã được thu gọn thành một hàng trên mỗi nhân viên, vì vậy phép join không tạo tích 2 × 3. **Nếu cần chi tiết từng điện thoại và từng kỹ năng trong cùng một result set**, tích tổ hợp có thể chính là kết quả mong muốn; chỉ aggregate khi nghiệp vụ cần số liệu ở cấp nhân viên.

### 8.4. Cần đúng một hàng con theo quy tắc: ROW_NUMBER

Nếu chỉ muốn **một số điện thoại ưu tiên** cho mỗi nhân viên, hãy định nghĩa thứ tự rõ ràng. Ví dụ ưu tiên MOBILE, sau đó số có ID nhỏ hơn:

```sql
WITH ranked_phones AS (
    SELECT
        p.employee_id,
        p.phone_id,
        p.phone_number,
        p.phone_type,
        ROW_NUMBER() OVER (
            PARTITION BY p.employee_id
            ORDER BY
                CASE p.phone_type
                    WHEN 'MOBILE' THEN 1
                    WHEN 'OFFICE' THEN 2
                    ELSE 3
                END,
                p.phone_id
        ) AS rn
    FROM lab_employee_phones p
)
SELECT
    e.employee_id,
    e.full_name,
    rp.phone_number,
    rp.phone_type
FROM lab_employees e
LEFT JOIN ranked_phones rp
  ON rp.employee_id = e.employee_id
 AND rp.rn = 1
ORDER BY e.employee_id;
```

`ROW_NUMBER` biến nhiều hàng con thành một hàng được chọn theo **quy tắc ưu tiên có tie-breaker**. Điều kiện `RN=1` được đặt trong `ON` để vẫn giữ nhân viên chưa có số điện thoại. Không dùng `MIN(PHONE_NUMBER)` chỉ để lấy “một số bất kỳ” nếu nghiệp vụ có quy tắc ưu tiên cụ thể.

### 8.5. Chỉ muốn loại trùng toàn bộ hàng hiển thị: DISTINCT

`DISTINCT` phù hợp khi mục tiêu thật sự là tập các giá trị duy nhất của danh sách cột được chọn:

```sql
SELECT DISTINCT department_id
FROM lab_employees
ORDER BY department_id NULLS LAST;
```

Nhưng `DISTINCT` không thể quyết định:

- Hàng nào trong nhiều hàng con nên được giữ?
- Tổng tiền phải tính một lần hay nhiều lần?
- Các cột khác nhau của hàng con sẽ được gộp như thế nào?
- Quan hệ dữ liệu có đang bị thiếu điều kiện join?

**Nếu dùng DISTINCT để che một phép join sai, kết quả có thể nhìn đúng ở màn hình nhưng tổng hợp hoặc dữ liệu chi tiết vẫn sai.**

## 9. NOT IN, NOT EXISTS và NULL

Một bẫy lớn khác là tìm những hàng **không có quan hệ** bằng `NOT IN` khi tập con có thể chứa NULL.

### 9.1. NOT IN với NULL có thể loại hết kết quả

Xét:

```sql
SELECT e.employee_id, e.full_name
FROM lab_employees e
WHERE e.employee_id NOT IN (
    SELECT manager_id
    FROM lab_employees
);
```

Subquery có các giá trị `MANAGER_ID NULL` (An, Dũng, Lan). Khi `NOT IN` được diễn giải thành chuỗi so sánh bất đẳng thức, một phần điều kiện trở thành UNKNOWN; kết quả có thể **không trả hàng nào** theo trường hợp có NULL trong danh sách.

### 9.2. Dùng NOT EXISTS cho quan hệ không tồn tại

```sql
SELECT e.employee_id, e.full_name
FROM lab_employees e
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_employees child
    WHERE child.manager_id = e.employee_id
)
ORDER BY e.employee_id;
```

Ý nghĩa: chọn nhân viên mà **không tồn tại hàng nhân viên khác tham chiếu họ làm manager**. `NULL` ở `CHILD.MANAGER_ID` không khớp `E.EMPLOYEE_ID` nên không làm hỏng logic anti-join.

Nếu dùng `NOT IN`, phải đảm bảo subquery loại NULL hoặc cột được ràng buộc NOT NULL:

```sql
SELECT e.employee_id, e.full_name
FROM lab_employees e
WHERE e.employee_id NOT IN (
    SELECT manager_id
    FROM lab_employees
    WHERE manager_id IS NOT NULL
);
```

Trong bài toán quan hệ “không có bản ghi liên quan”, `NOT EXISTS` thường diễn đạt ý định rõ hơn và tránh bẫy NULL ở subquery.

## 10. Subquery trả 0, 1 hoặc nhiều hàng

Số hàng của subquery cũng có ngữ nghĩa riêng tùy cách sử dụng.

### 10.1. Scalar subquery

Một scalar subquery được dùng như biểu thức phải trả **tối đa một giá trị**:

```sql
SELECT
    e.employee_id,
    e.full_name,
    (
        SELECT d.department_name
        FROM lab_departments d
        WHERE d.department_id = e.department_id
    ) AS department_name
FROM lab_employees e
ORDER BY e.employee_id;
```

- Subquery trả **0 hàng**: scalar value là `NULL`.
- Subquery trả **1 hàng**: lấy giá trị của hàng đó.
- Subquery trả **hơn 1 hàng**: Oracle báo `ORA-01427: single-row subquery returns more than one row`.

Vì `DEPARTMENT_ID` là primary key của bảng phòng ban, ví dụ trên có tối đa một hàng phù hợp. Nếu subquery tra một bảng không có khóa duy nhất, phải xác định quy tắc chọn hàng hoặc dùng `EXISTS`/join phù hợp; không giả định scalar subquery tự chọn hàng đầu tiên.

### 10.2. SELECT INTO trong PL/SQL

`SELECT ... INTO` của PL/SQL có hợp đồng khác với SELECT thông thường:

- 0 hàng: ném exception `NO_DATA_FOUND`.
- 1 hàng: gán giá trị vào biến.
- Hơn 1 hàng: ném `TOO_MANY_ROWS`.

Ví dụ:

```sql
DECLARE
    l_name lab_employees.full_name%TYPE;
BEGIN
    SELECT full_name
      INTO l_name
      FROM lab_employees
     WHERE employee_id = 999;

    DBMS_OUTPUT.PUT_LINE(l_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Khong tim thay nhan vien');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Dieu kien khong duy nhat');
END;
/
```

Trong ví dụ, `EMPLOYEE_ID` là primary key nên không thể có nhiều hàng phù hợp nếu ràng buộc được bảo đảm. `TOO_MANY_ROWS` vẫn là exception cần hiểu khi `SELECT INTO` truy vấn theo một cột không duy nhất.

Đừng nhầm một `SELECT` chạy trực tiếp trên SQL client trả 0 hàng với `SELECT INTO` trong PL/SQL: câu đầu hợp lệ và chỉ trả tập rỗng; câu thứ hai yêu cầu đúng một hàng nên ném exception khi không tìm thấy.

## 11. Chẩn đoán duplicate bằng cách kiểm tra từng tầng

Khi một báo cáo trả 20 hàng trong khi bạn kỳ vọng 10 nhân viên, **đừng thêm DISTINCT ngay**. Hãy tìm xem số hàng tăng ở phép join nào.

### Bước 1 — Xác định grain (đơn vị một hàng) của kết quả

Trước khi viết query, hãy nói thành câu:

- “Một hàng đại diện cho **một nhân viên**.”
- “Một hàng đại diện cho **một điện thoại**.”
- “Một hàng đại diện cho **một đơn hàng**.”
- “Một hàng đại diện cho **một nhân viên × một kỹ năng**.”

Nếu không xác định grain, không thể kết luận một hàng lặp là sai. Khóa duy nhất kỳ vọng trong kết quả là gì? `EMPLOYEE_ID` hay `(EMPLOYEE_ID, PHONE_ID)`?

### Bước 2 — Đếm nguồn trước khi join

```sql
SELECT COUNT(*) AS employee_rows
FROM lab_employees;

SELECT COUNT(*) AS phone_rows
FROM lab_employee_phones;

SELECT employee_id, COUNT(*) AS phone_count
FROM lab_employee_phones
GROUP BY employee_id
ORDER BY employee_id;
```

Nếu nguồn đã có trùng key trước join, cần điều tra ràng buộc và chất lượng dữ liệu ở bảng nguồn.

### Bước 3 — Thêm từng join và đếm số hàng

```sql
-- A: chỉ bảng nhân viên.
SELECT COUNT(*) AS rows_a
FROM lab_employees e;

-- B: thêm bảng số điện thoại.
SELECT COUNT(*) AS rows_b
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id;

-- C: chỉ xem số lượng cặp theo nhân viên.
SELECT e.employee_id, COUNT(*) AS joined_rows
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
GROUP BY e.employee_id
ORDER BY e.employee_id;
```

Nếu số hàng tăng từ 6 lên 5 trong inner join, đó là vì nhân viên không có phone bị loại và các nhân viên có nhiều phone được nhân theo số phone. Tổng số có thể nhỏ hơn số nhân viên vì join là inner, dù một số nhân viên có nhiều hàng con.

### Bước 4 — Tìm khóa xuất hiện nhiều hơn một lần

```sql
SELECT e.employee_id, COUNT(*) AS occurrences
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
GROUP BY e.employee_id
HAVING COUNT(*) > 1
ORDER BY e.employee_id;
```

Đây là phép kiểm tra **số lần khóa nhân viên xuất hiện sau join**, không phải kết luận bảng `LAB_EMPLOYEES` bị duplicate primary key. Khóa nhân viên có thể xuất hiện nhiều lần do một nhân viên có nhiều số điện thoại.

### Bước 5 — Kiểm tra dữ liệu nguồn có trùng key thật không

```sql
SELECT employee_id, COUNT(*) AS occurrences
FROM lab_employees
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

Với bảng lab có primary key, query phải không trả hàng. Nếu một bảng không có unique constraint phù hợp, đây là bước quan trọng để phát hiện duplicate key nghiệp vụ.

### Bước 6 — Kiểm tra join key và cardinality

Các câu hỏi cần đặt ra:

- Có join **đủ tất cả cột** của khóa ghép không?
- Có thiếu điều kiện nối tenant/company/partition/business unit không?
- Hai bên có thật sự là quan hệ 1-1, 1-nhiều hay nhiều-nhiều?
- Có nối hai bảng con độc lập cùng khóa cha làm nhân kết quả theo tích không?
- Có filter trên bảng phải nằm ở `WHERE` khiến outer join mất tác dụng không?
- Có dùng `DISTINCT` làm biến mất khác biệt mà người dùng cần thấy không?

Nếu khóa quan hệ gồm `(COMPANY_ID, CUSTOMER_ID)` mà chỉ join `CUSTOMER_ID`, các khách hàng cùng ID ở công ty khác nhau có thể ghép nhầm và làm nhân bản.

## 12. Các công thức kiểm tra hữu ích

### 12.1. Tìm nhóm có khóa trùng

```sql
SELECT business_key, COUNT(*) AS duplicate_count
FROM source_table
GROUP BY business_key
HAVING COUNT(*) > 1;
```

Với khóa ghép:

```sql
SELECT company_id, customer_id, COUNT(*) AS duplicate_count
FROM source_table
GROUP BY company_id, customer_id
HAVING COUNT(*) > 1;
```

### 12.2. Đếm số hàng thật ở phía phải của outer join

```sql
SELECT parent.parent_id,
       COUNT(child.child_id) AS child_count
FROM parent_table parent
LEFT JOIN child_table child
  ON child.parent_id = parent.parent_id
GROUP BY parent.parent_id;
```

Đếm bằng khóa phía phải bắt buộc có giá trị trên mọi hàng thật, thường là primary key. Tránh `COUNT(*)` nếu cần số hàng con.

### 12.3. Lấy cha có/không có con

```sql
-- Có ít nhất một con.
SELECT p.parent_id
FROM parent_table p
WHERE EXISTS (
    SELECT 1
    FROM child_table c
    WHERE c.parent_id = p.parent_id
);

-- Không có con.
SELECT p.parent_id
FROM parent_table p
WHERE NOT EXISTS (
    SELECT 1
    FROM child_table c
    WHERE c.parent_id = p.parent_id
);
```

### 12.4. Lấy một hàng con theo quy tắc

```sql
SELECT parent_id, child_id, created_at
FROM (
    SELECT c.*,
           ROW_NUMBER() OVER (
               PARTITION BY parent_id
               ORDER BY created_at DESC NULLS LAST, child_id DESC
           ) AS rn
    FROM child_table c
)
WHERE rn = 1;
```

`CHILD_ID` được dùng làm tie-breaker để lựa chọn xác định khi hai hàng có cùng `CREATED_AT`. Nếu không có khóa phụ, Oracle có thể chọn thứ tự không ổn định giữa các hàng bằng nhau.

## 13. Những lỗi thường gặp và cách đọc đúng

| Triệu chứng | Cách hiểu sai thường gặp | Cách phân tích đúng |
| --- | --- | --- |
| SQL không trả hàng | “Bảng bị mất dữ liệu” | Kiểm tra nguồn, PDB/schema, quyền và điều kiện lọc |
| COUNT trả 0 nhưng client vẫn có một dòng | “Query có một bản ghi NULL” | Đây là aggregate không GROUP BY, một hàng kết quả có COUNT = 0 |
| SUM trả NULL | “Không có hàng kết quả” | Kiểm tra số hàng; aggregate có thể trả một hàng với SUM NULL |
| Cột hiển thị `(null)` | “Bản ghi không tồn tại” | Hàng có thể tồn tại nhưng thuộc tính chưa có giá trị |
| `WHERE col = NULL` không khớp | “Oracle không nhận NULL” | Dùng `IS NULL` / `IS NOT NULL` |
| `NOT IN` không trả hàng | “Không có bản ghi nào thỏa” | Kiểm tra NULL trong tập con; cân nhắc `NOT EXISTS` |
| LEFT JOIN mất bản ghi cha không có con | “LEFT JOIN bị lỗi” | Điều kiện trên bảng phải trong WHERE đã loại hàng NULL bổ sung |
| COUNT(*) = 1 cho cha không có con | “Có một bản ghi con” | Hàng outer join bổ sung vẫn được COUNT(*) đếm |
| ID cha lặp nhiều lần sau join | “Bảng cha bị duplicate” | Kiểm tra số hàng con và grain của result set |
| SUM tiền tăng gấp đôi sau join | “SUM của Oracle sai” | Một bảng con khác nhân bản hàng chứa tiền; aggregate từng nguồn trước khi join |
| DISTINCT làm số hàng đúng | “Đã sửa dữ liệu” | DISTINCT có thể chỉ che nguyên nhân join/cardinality |
| Scalar subquery báo ORA-01427 | “Oracle tự chọn không đúng hàng” | Subquery trả nhiều hơn một hàng trong ngữ cảnh cần một giá trị |
| PL/SQL SELECT INTO báo NO_DATA_FOUND | “SELECT SQL luôn báo lỗi khi không có hàng” | SELECT thường trả tập rỗng; SELECT INTO yêu cầu đúng một hàng |

## 14. Bài tập thực hành

Hãy chạy từng câu trên dữ liệu lab, dự đoán kết quả trước và giải thích bằng số hàng/giá trị, không chỉ ghi “đúng” hoặc “sai”.

### Bài 1 — Phân biệt result set rỗng và aggregate

So sánh:

```sql
SELECT employee_id
FROM lab_employees
WHERE employee_id = 999;

SELECT COUNT(*) AS row_count
FROM lab_employees
WHERE employee_id = 999;

SELECT SUM(salary) AS salary_sum
FROM lab_employees
WHERE employee_id = 999;
```

Trả lời: câu nào trả 0 hàng, câu nào trả một hàng với số 0, câu nào trả một hàng với NULL? Vì sao?

### Bài 2 — NULL và điều kiện phủ định

So sánh:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE NOT (salary > 2000);

SELECT employee_id, full_name
FROM lab_employees
WHERE salary <= 2000 OR salary IS NULL;
```

Giải thích tại sao Chi có thể xuất hiện ở câu thứ hai nhưng không xuất hiện ở câu thứ nhất.

### Bài 3 — LEFT JOIN và COUNT

Viết query hiển thị mọi phòng ban, kể cả phòng 40, với số nhân viên. Thử lần lượt `COUNT(*)` và `COUNT(e.employee_id)`. Giải thích khác biệt.

### Bài 4 — Đếm số điện thoại mà không nhân bản nhân viên

Viết hai query:

1. Join nhân viên với điện thoại và cho thấy nhân viên An xuất hiện hai hàng.
2. Dùng `GROUP BY` trên bảng điện thoại trước khi join để trả đúng một hàng mỗi nhân viên cùng số điện thoại.

Giải thích **grain** của từng kết quả.

### Bài 5 — NOT IN và NOT EXISTS

Chạy query `NOT IN (SELECT manager_id FROM lab_employees)` và query `NOT EXISTS` ở mục 9. Ghi nhận kết quả. Sau đó thêm `WHERE manager_id IS NOT NULL` vào subquery NOT IN và so sánh.

Giải thích vai trò của UNKNOWN trong phép phủ định.

### Bài 6 — Nhân bản khi nối hai bảng con

Tạo thêm bảng lab:

```sql
CREATE TABLE lab_employee_skills (
    skill_id    NUMBER PRIMARY KEY,
    employee_id NUMBER NOT NULL
        REFERENCES lab_employees(employee_id),
    skill_name  VARCHAR2(60 CHAR) NOT NULL
);

INSERT INTO lab_employee_skills VALUES (201, 1, 'SQL');
INSERT INTO lab_employee_skills VALUES (202, 1, 'PLSQL');
INSERT INTO lab_employee_skills VALUES (203, 1, 'Java');
COMMIT;
```

Nối `LAB_EMPLOYEES`, `LAB_EMPLOYEE_PHONES` và `LAB_EMPLOYEE_SKILLS` cho employee 1. Xác nhận kết quả có 6 tổ hợp. Sau đó viết CTE đếm phone và skill riêng, join hai kết quả đếm để có **một hàng mỗi employee**.

### Bài 7 — Phân tích một báo cáo sai

Một báo cáo cần tổng số điện thoại và số kỹ năng mỗi nhân viên, nhưng query được viết:

```sql
SELECT
    e.employee_id,
    COUNT(p.phone_id) AS phone_count,
    COUNT(s.skill_id) AS skill_count
FROM lab_employees e
LEFT JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
LEFT JOIN lab_employee_skills s
  ON s.employee_id = e.employee_id
GROUP BY e.employee_id;
```

Với employee 1, hai điện thoại và ba kỹ năng làm mỗi phía bị nhân theo tổ hợp. Hãy sửa bằng hai CTE aggregate riêng trước khi join. Không dùng `COUNT(DISTINCT ...)` làm giải pháp mặc định nếu còn cần tính tổng hoặc lấy chi tiết cột khác.

## 15. Dọn dữ liệu lab

Chỉ chạy trong schema thực hành do bạn tạo:

```sql
DROP TABLE lab_employee_skills PURGE;
DROP TABLE lab_lob_state PURGE;
DROP TABLE lab_employee_phones PURGE;
DROP TABLE lab_employees PURGE;
DROP TABLE lab_departments PURGE;
```

Nếu không tạo `LAB_EMPLOYEE_SKILLS` hoặc `LAB_LOB_STATE`, bỏ qua lệnh tương ứng. Xóa bảng con trước bảng cha vì foreign key tham chiếu; `PURGE` bỏ qua recycle bin. Không dùng các lệnh này với bảng của người khác hoặc dữ liệu cần giữ.

## Tổng kết

Khi đọc một kết quả Oracle, hãy hỏi riêng ba câu:

1. **Có bao nhiêu hàng?** Không hàng nào là empty result set; một hàng có giá trị NULL vẫn là một hàng.
2. **Giá trị NULL mang ý nghĩa gì?** Nó tạo logic ba giá trị, ảnh hưởng điều kiện, aggregate, join, subquery và cách ứng dụng hiển thị. NULL khác 0, chuỗi chữ “NULL” và LOB rỗng.
3. **Một hàng kết quả đại diện cho điều gì?** Join 1-nhiều có thể lặp khóa cha đúng theo quan hệ; nối nhiều bảng con độc lập có thể nhân kết quả theo tích; chỉ dùng DISTINCT sau khi hiểu rõ grain và mục tiêu.

Với điều kiện lọc NULL, dùng `IS NULL`/`IS NOT NULL`; với quan hệ tồn tại/không tồn tại, cân nhắc `EXISTS`/`NOT EXISTS`; với số lượng con, aggregate trước khi join; với một hàng con được ưu tiên, dùng `ROW_NUMBER` với thứ tự xác định. Những cách này giải quyết nguyên nhân theo đúng ngữ nghĩa thay vì chỉ làm kết quả nhìn bớt trùng.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — Nulls (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Nulls.html) — ngữ nghĩa NULL và các phép so sánh.
- [Oracle Database SQL Language Reference — Aggregate Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html) — cách COUNT, SUM, AVG và aggregate xử lý NULL.
- [Oracle Database SQL Language Reference — Joins (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html) — inner/outer joins và điều kiện nối.
- [Oracle Database SQL Language Reference — EXISTS Condition (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html) — điều kiện tồn tại.
- [Oracle Database SQL Language Reference — IN Condition (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html) — semantics của IN/NOT IN.
- [Oracle Database PL/SQL Language Reference — SELECT INTO Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/SELECT-INTO-statement.html) — NO_DATA_FOUND và TOO_MANY_ROWS.

Khi xử lý dữ liệu thật, hãy kiểm tra đúng release Oracle, ràng buộc của bảng, cardinality quan hệ và quy tắc nghiệp vụ. Một query trả nhiều hàng có thể hoàn toàn đúng; điều quan trọng là mỗi hàng có đúng ý nghĩa mà ứng dụng cần.

# Cấu trúc SELECT và thứ tự xử lý logic các mệnh đề

Trong Oracle Database, `SELECT` là câu lệnh dùng để **truy vấn dữ liệu**. Một câu `SELECT` có thể chỉ đọc một vài cột của một bảng, nhưng cũng có thể nối nhiều bảng, lọc hàng, nhóm dữ liệu, tính tổng, loại bỏ kết quả trùng, sắp xếp và lấy một phần kết quả để phân trang.

Điểm khiến người mới học dễ nhầm là **thứ tự viết SQL không phải thứ tự xử lý logic của các mệnh đề**. Chẳng hạn, chúng ta viết `SELECT` ở đầu câu lệnh nhưng phải biết dữ liệu đến từ đâu (`FROM`) và hàng nào còn lại sau `WHERE` trước khi xác định kết quả cuối cùng của danh sách `SELECT`. Điều này giải thích nhiều lỗi thường gặp như “tại sao alias vừa khai báo trong `SELECT` không dùng được ở `WHERE`?”, “tại sao `HAVING` khác `WHERE`?” hoặc “tại sao `ROWNUM` không lấy đúng top 3 sau sắp xếp?”.

Mục tiêu của bài học:

- Đọc được cấu trúc `SELECT` phổ biến trong Oracle, kể cả các mệnh đề tùy chọn.
- Diễn giải **thứ tự xử lý logic** để dự đoán tập hàng của từng giai đoạn.
- Chọn đúng `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY` và `FETCH FIRST` cho yêu cầu cụ thể.
- Phân biệt **thứ tự logic để hiểu kết quả** với **execution plan thực tế** do Oracle Optimizer lựa chọn.
- Viết truy vấn dễ đọc, có thứ tự phân trang ổn định và tránh sai lệch do `NULL`, join hay alias.

## 1. Mẫu cấu trúc SELECT cơ bản

Một câu truy vấn Oracle thường có dạng:

```sql
SELECT [DISTINCT] expression_1 [AS alias_1],
                  expression_2 [AS alias_2],
                  ...
FROM   table_or_view [alias]
       [JOIN another_table ON join_condition]
[WHERE row_condition]
[GROUP BY grouping_expression_1, grouping_expression_2, ...]
[HAVING group_condition]
[ORDER BY sort_expression_1 [ASC | DESC] [NULLS FIRST | NULLS LAST],
          sort_expression_2, ...]
[OFFSET n ROWS]
[FETCH FIRST | NEXT m ROWS ONLY | WITH TIES];
```

**Các cặp dấu `[ ]` trong mẫu là ký hiệu tài liệu chỉ thành phần tùy chọn, không phải dấu cần nhập nguyên văn vào SQL.** Oracle có nhiều tính năng mở rộng (`WITH`, subquery, analytic functions, set operators, hierarchical queries, `MODEL`, `MATCH_RECOGNIZE`, `FOR UPDATE`...), nhưng trước tiên cần nắm khung `SELECT ... FROM ... WHERE ... GROUP BY ... HAVING ... ORDER BY ... OFFSET/FETCH`.

| Thành phần | Câu hỏi nó giải quyết | Ví dụ |
| --- | --- | --- |
| `SELECT` | Cần trả về cột/biểu thức nào? | `SELECT full_name, salary * 12 AS annual_salary` |
| `FROM` | Lấy hàng từ nguồn nào? | `FROM lab_employees e` |
| `JOIN ... ON` | Kết hợp những nguồn dữ liệu bằng quan hệ nào? | `JOIN lab_departments d ON d.department_id = e.department_id` |
| `WHERE` | Giữ lại **hàng** nào trước khi nhóm? | `WHERE e.active_flag = 'Y'` |
| `GROUP BY` | Các hàng được gom thành nhóm theo khóa nào? | `GROUP BY e.department_id` |
| `HAVING` | Giữ lại **nhóm** nào sau khi tính aggregate? | `HAVING COUNT(*) >= 2` |
| `DISTINCT` | Loại bỏ các dòng kết quả trùng nhau? | `SELECT DISTINCT department_id` |
| `ORDER BY` | Trả kết quả theo thứ tự nào? | `ORDER BY total_salary DESC` |
| `OFFSET/FETCH` | Bỏ qua bao nhiêu dòng đầu và lấy tối đa bao nhiêu dòng? | `FETCH FIRST 5 ROWS ONLY` |

Hai điểm cần ghi nhớ từ đầu:

1. `WHERE` và `HAVING` đều có thể loại bỏ dữ liệu nhưng hoạt động ở **hai cấp khác nhau**: hàng và nhóm.
2. **Không có `ORDER BY` thì Oracle không bảo đảm thứ tự các dòng trả về**, kể cả khi trước đó bạn thường thấy chúng xuất hiện theo `ID` hoặc theo thứ tự chèn.

## 2. Tạo dữ liệu mẫu để theo dõi từng bước

Các ví dụ tiếp theo dùng hai bảng nhỏ:

```text
LAB_DEPARTMENTS                      LAB_EMPLOYEES
  DEPARTMENT_ID  (PK) <------------+  EMPLOYEE_ID (PK)
  DEPARTMENT_NAME                 +-- DEPARTMENT_ID (FK, nullable)
                                     FULL_NAME
                                     SALARY (nullable)
                                     ACTIVE_FLAG ('Y' / 'N')
                                     HIRE_DATE
```

Chạy DDL và DML trong **schema thực hành riêng**, có quyền `CREATE TABLE` và quota tablespace. Nếu đã có bảng cùng tên, dùng schema lab khác; không xóa bảng ứng dụng để chạy ví dụ.

### 2.1. Tạo bảng

```sql
CREATE TABLE lab_departments (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE lab_employees (
    employee_id   NUMBER PRIMARY KEY,
    full_name     VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER,
    salary        NUMBER(12, 2),
    active_flag   CHAR(1) DEFAULT 'Y' NOT NULL,
    hire_date     DATE NOT NULL,
    CONSTRAINT fk_lab_emp_dept
        FOREIGN KEY (department_id)
        REFERENCES lab_departments (department_id),
    CONSTRAINT ck_lab_emp_active
        CHECK (active_flag IN ('Y', 'N'))
);
```

### 2.2. Thêm dữ liệu

```sql
INSERT INTO lab_departments VALUES (10, 'Kỹ thuật');
INSERT INTO lab_departments VALUES (20, 'Kinh doanh');
INSERT INTO lab_departments VALUES (30, 'Nhân sự');
INSERT INTO lab_departments VALUES (40, 'Pháp chế');

INSERT INTO lab_employees VALUES (1, 'An',   10, 2000, 'Y', DATE '2024-01-10');
INSERT INTO lab_employees VALUES (2, 'Bình', 10, 3000, 'Y', DATE '2024-02-15');
INSERT INTO lab_employees VALUES (3, 'Chi',  10, 2500, 'N', DATE '2023-09-01');
INSERT INTO lab_employees VALUES (4, 'Dũng', 20, 2800, 'Y', DATE '2024-03-04');
INSERT INTO lab_employees VALUES (5, 'Hà',   20, NULL, 'Y', DATE '2024-04-05');
INSERT INTO lab_employees VALUES (6, 'Lan',  NULL, 1800, 'Y', DATE '2024-05-10');
INSERT INTO lab_employees VALUES (7, 'Minh', 30, 3200, 'N', DATE '2023-08-11');
INSERT INTO lab_employees VALUES (8, 'Nga',  20, 2800, 'Y', DATE '2024-06-06');
INSERT INTO lab_employees VALUES (9, 'Phúc', 30, 2700, 'Y', DATE '2024-07-07');

COMMIT;
```

Các hàng quan trọng để suy luận:

| EMPLOYEE_ID | FULL_NAME | DEPARTMENT_ID | SALARY | ACTIVE_FLAG |
| ---: | --- | ---: | ---: | :---: |
| 1 | An | 10 | 2000 | Y |
| 2 | Bình | 10 | 3000 | Y |
| 3 | Chi | 10 | 2500 | N |
| 4 | Dũng | 20 | 2800 | Y |
| 5 | Hà | 20 | `NULL` | Y |
| 6 | Lan | `NULL` | 1800 | Y |
| 7 | Minh | 30 | 3200 | N |
| 8 | Nga | 20 | 2800 | Y |
| 9 | Phúc | 30 | 2700 | Y |

Bảng `LAB_DEPARTMENTS` có bốn phòng ban, trong đó **Pháp chế (40) không có nhân viên**. Nhân viên **Lan** chưa gán phòng ban; **Hà** có lương `NULL`. Các trường hợp này giúp thấy rõ tác động của `JOIN`, `COUNT` và `NULL` trong SELECT.

## 3. Thứ tự viết và thứ tự xử lý logic

Câu SQL thường được **viết** theo trình tự:

```text
SELECT -> FROM/JOIN -> WHERE -> GROUP BY -> HAVING
       -> ORDER BY -> OFFSET/FETCH
```

Để hiểu **ngữ nghĩa kết quả** của một query block, có thể tưởng tượng trình tự **xử lý logic** như sau:

```text
   FROM và JOIN ... ON
           |
           v
        WHERE
           |
           v
        GROUP BY
           |
           v
         HAVING
           |
           v
     SELECT expressions
     (kể cả analytic functions ở pha phù hợp)
           |
           v
        DISTINCT
           |
           v
        ORDER BY
           |
           v
     OFFSET / FETCH
           |
           v
      Tập kết quả
```

Đây là **mô hình tư duy**, không phải lời khẳng định Oracle thực hiện vật lý lần lượt những thao tác này từng bước. Oracle Optimizer có thể đẩy điều kiện lọc xuống table access, đảo thứ tự join, chọn hash/group aggregation, sort hoặc index scan, gộp view và thay đổi kế hoạch để giữ **ngữ nghĩa SQL** với chi phí hợp lý.

Đối với những đặc tính nâng cao, cần tinh chỉnh mô hình:

- `WITH` định nghĩa các **query block/CTE** được tham chiếu; nó **không bảo đảm được chạy và vật hóa một lần trước SELECT chính**.
- **Analytic functions** (`ROW_NUMBER`, `RANK`, `SUM(...) OVER (...)`...) được tính sau các pha `FROM`/`WHERE`/`GROUP BY`/`HAVING` trong query block, rồi mới tới `ORDER BY` cuối. Chúng không được dùng trực tiếp trong `WHERE` của cùng query block.
- `DISTINCT` loại trùng sau khi xác định các biểu thức được trả về, còn `ORDER BY` sắp xếp kết quả trước khi `FETCH` lấy một phần.
- Nếu có **subquery** hoặc **set operators** (`UNION ALL`, `UNION`, `INTERSECT`, `MINUS`...), mỗi query block có phạm vi xử lý riêng; không lấy sơ đồ đơn giản của một block để mô tả mọi phép toán lồng nhau.

## 4. Theo dấu một truy vấn hoàn chỉnh

Yêu cầu: **tìm những phòng ban có ít nhất hai nhân viên đang hoạt động; trả về số nhân viên, số người có mức lương được ghi nhận và tổng lương, sắp xếp tổng lương giảm dần, lấy hai phòng ban đầu tiên.**

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS active_employees,
    COUNT(e.salary) AS known_salaries,
    SUM(e.salary) AS total_salary
FROM lab_departments d
JOIN lab_employees e
    ON e.department_id = d.department_id
WHERE e.active_flag = 'Y'
GROUP BY d.department_id, d.department_name
HAVING COUNT(*) >= 2
ORDER BY total_salary DESC NULLS LAST, d.department_id
FETCH FIRST 2 ROWS ONLY;
```

### Pha 1 — `FROM` và `JOIN` tạo các hàng nguồn

`LAB_DEPARTMENTS` có 4 hàng; `LAB_EMPLOYEES` có 9 hàng. `INNER JOIN` với điều kiện `e.department_id = d.department_id` chỉ giữ nhân viên có phòng ban tồn tại và khớp.

| Phòng ban | Nhân viên có thể join | Số hàng sau join |
| --- | --- | ---: |
| 10 — Kỹ thuật | An, Bình, Chi | 3 |
| 20 — Kinh doanh | Dũng, Hà, Nga | 3 |
| 30 — Nhân sự | Minh, Phúc | 2 |
| 40 — Pháp chế | Không có | 0 |

Tổng cộng **8 hàng** sau `INNER JOIN`. Lan có `DEPARTMENT_ID NULL` nên không khớp bất kỳ phòng ban nào và bị loại bởi inner join. Phòng ban 40 không có nhân viên cũng không sinh hàng.

### Pha 2 — `WHERE` lọc từng hàng

`WHERE e.active_flag = 'Y'` loại hai nhân viên không hoạt động: Chi và Minh. Còn **6 hàng**:

```text
10: An (2000), Bình (3000)
20: Dũng (2800), Hà (NULL), Nga (2800)
30: Phúc (2700)
```

Điểm quan trọng: tại thời điểm suy luận `WHERE`, chưa có `COUNT(*)` hay `SUM(e.salary)` của từng nhóm. `WHERE` nhận các hàng riêng lẻ, không nhận bảng tổng hợp đã nhóm.

### Pha 3 — `GROUP BY` chia thành nhóm

`GROUP BY d.department_id, d.department_name` tạo **3 nhóm** tương ứng phòng ban 10, 20 và 30:

| DEPARTMENT_ID | Thành viên trong nhóm | `COUNT(*)` | `COUNT(e.salary)` | `SUM(e.salary)` |
| ---: | --- | ---: | ---: | ---: |
| 10 | An, Bình | 2 | 2 | 5000 |
| 20 | Dũng, Hà, Nga | 3 | 2 | 5600 |
| 30 | Phúc | 1 | 1 | 2700 |

Vì `SALARY` của Hà là `NULL`, `COUNT(*)` vẫn đếm hàng đó, nhưng `COUNT(e.salary)` **không** đếm giá trị NULL. `SUM` bỏ qua NULL; tổng lương phòng 20 là 2800 + 2800 = **5600**, không phải NULL.

### Pha 4 — `HAVING` lọc nhóm

`HAVING COUNT(*) >= 2` giữ lại nhóm 10 và 20; nhóm 30 có một nhân viên đang hoạt động nên bị loại.

### Pha 5 — `SELECT` tạo các cột kết quả

Sau nhóm/lọc nhóm, danh sách `SELECT` quyết định các cột xuất ra và đặt alias `ACTIVE_EMPLOYEES`, `KNOWN_SALARIES`, `TOTAL_SALARY`.

### Pha 6 — `ORDER BY` và `FETCH`

`ORDER BY total_salary DESC NULLS LAST, d.department_id` đưa phòng ban 20 (5600) lên trước phòng 10 (5000). `FETCH FIRST 2 ROWS ONLY` giới hạn kết quả còn tối đa hai hàng.

| DEPARTMENT_ID | DEPARTMENT_NAME | ACTIVE_EMPLOYEES | KNOWN_SALARIES | TOTAL_SALARY |
| ---: | --- | ---: | ---: | ---: |
| 20 | Kinh doanh | 3 | 2 | 5600 |
| 10 | Kỹ thuật | 2 | 2 | 5000 |

Nếu đổi thành `FETCH FIRST 1 ROW ONLY`, chỉ còn **Kinh doanh** trong kết quả. Truy vấn không đổi bản chất nhóm dữ liệu; `FETCH` chỉ lấy một phần **sau thứ tự sắp xếp được chỉ định**.

## 5. `SELECT`: chọn cột, biểu thức và alias

Để lấy các cột đơn giản:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees;
```

Để tạo một cột tính toán:

```sql
SELECT
    employee_id,
    full_name,
    salary,
    salary * 12 AS estimated_annual_salary
FROM lab_employees
WHERE salary IS NOT NULL;
```

`SALARY * 12` chỉ là một **biểu thức của truy vấn**; nó không tạo cột mới trong bảng. `AS ESTIMATED_ANNUAL_SALARY` đặt tên cột kết quả. `AS` khi đặt column alias thường là tùy chọn:

```sql
SELECT salary * 12 annual_salary
FROM lab_employees;
```

Trong Oracle, **table alias** thường viết không có từ khóa `AS`:

```sql
SELECT e.full_name, d.department_name
FROM lab_employees e
JOIN lab_departments d
  ON d.department_id = e.department_id;
```

### 5.1. `SELECT *` có nên dùng?

`SELECT *` hữu ích để khảo sát nhanh một bảng nhỏ:

```sql
SELECT * FROM lab_departments;
```

Nhưng với API và SQL được lưu lâu dài, nên liệt kê rõ các cột cần lấy. Danh sách `*` có thể thay đổi khi schema thêm cột, kéo theo dữ liệu nhạy cảm hoặc cột có kích thước lớn mà ứng dụng không cần. Trong query join, `SELECT *` còn có thể tạo tên cột trùng, làm mapping sang DTO khó đoán.

### 5.2. Alias chỉ được dùng ở phạm vi phù hợp

Ví dụ viết sai:

```sql
SELECT salary * 12 AS annual_salary
FROM lab_employees
WHERE annual_salary > 30000;
```

Ở Oracle 19c và cú pháp cơ bản, `ANNUAL_SALARY` là alias của danh sách `SELECT`; `WHERE` trong **cùng query block** chưa nhìn thấy alias đó. Oracle thường báo lỗi như `ORA-00904: invalid identifier`.

Cách 1, lặp biểu thức ở `WHERE`:

```sql
SELECT salary * 12 AS annual_salary
FROM lab_employees
WHERE salary * 12 > 30000;
```

Cách 2, đặt phép tính ở một query block bên trong:

```sql
SELECT employee_id, full_name, annual_salary
FROM (
    SELECT
        employee_id,
        full_name,
        salary * 12 AS annual_salary
    FROM lab_employees
)
WHERE annual_salary > 30000;
```

Ở query bên ngoài, `ANNUAL_SALARY` đã trở thành **cột của inline view**. Bạn cũng có thể dùng CTE (`WITH`) để đặt tên query block; không nên coi CTE luôn là bảng tạm vật lý.

**Ngoại lệ dễ thấy:** `ORDER BY` của cùng query block **thường được phép** dùng alias của cột `SELECT`:

```sql
SELECT full_name, salary * 12 AS annual_salary
FROM lab_employees
ORDER BY annual_salary DESC NULLS LAST, full_name;
```

Đó là khác biệt về ngữ nghĩa và khả năng phân giải tên, không phải Oracle “chạy SELECT hai lần”.

## 6. `FROM`, `JOIN` và thứ tự kết hợp nguồn

`FROM` xác định nguồn hàng: bảng, view, inline view, subquery factoring (`WITH`) hoặc những dạng nguồn dữ liệu mà Oracle hỗ trợ.

```sql
SELECT
    e.employee_id,
    e.full_name,
    d.department_name
FROM lab_employees e
JOIN lab_departments d
    ON d.department_id = e.department_id
ORDER BY e.employee_id;
```

Đây là **inner join**: chỉ giữ các cặp hàng thỏa điều kiện `ON`. Nhân viên Lan có `DEPARTMENT_ID NULL` không được trả về.

### 6.1. Điều kiện `ON` so với `WHERE` trong outer join

Trong **inner join**, optimizer thường có thể biến đổi nhiều điều kiện `ON` và `WHERE` mà vẫn giữ ý nghĩa. Trong **outer join**, vị trí của điều kiện có thể làm thay đổi kết quả.

Truy vấn A: lấy tất cả phòng ban, chỉ nối nhân viên đang hoạt động khi có:

```sql
SELECT d.department_id, d.department_name, e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

Phòng ban **Pháp chế (40)** vẫn xuất hiện với `E.FULL_NAME NULL`. Vì `LEFT JOIN` bảo toàn hàng bên trái, những phòng ban không có nhân viên phù hợp vẫn có một hàng kết quả được bổ sung NULL ở phía phải.

Truy vấn B: nối tất cả nhân viên trước, sau đó lọc nhân viên đang hoạt động trong `WHERE`:

```sql
SELECT d.department_id, d.department_name, e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

Hàng Pháp chế được outer join sinh ra có `E.ACTIVE_FLAG NULL`; điều kiện `NULL = 'Y'` không trả `TRUE` nên **hàng Pháp chế bị loại trong WHERE**. Query B do đó không có ý nghĩa bảo toàn mọi phòng ban như query A.

Một bộ lọc trên bảng phải được đặt ở đâu tùy nghiệp vụ. **Đừng chuyển điều kiện giữa `ON` và `WHERE` của outer join chỉ vì nhìn cú pháp có vẻ tương đương.**

### 6.2. Sai lầm thiếu điều kiện JOIN

```sql
SELECT e.full_name, d.department_name
FROM lab_employees e
CROSS JOIN lab_departments d;
```

`CROSS JOIN` tạo **Cartesian product**: 9 nhân viên × 4 phòng ban = **36 cặp** trước mọi bộ lọc. Điều này có thể đúng khi cần tổ hợp dữ liệu, nhưng thường là lỗi nếu người viết quên điều kiện quan hệ. Với dữ liệu lớn, cardinality có thể tăng đột biến.

Không được nhầm “có nhiều bảng trong `FROM`” với “Oracle sẽ tự biết phải nối chúng bằng cột `DEPARTMENT_ID` nào”.

## 7. `WHERE`: điều kiện trên từng hàng

`WHERE` loại hàng không thỏa điều kiện trước khi thực hiện `GROUP BY` ở **cùng query block**.

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE active_flag = 'Y'
  AND salary >= 2500
ORDER BY employee_id;
```

Các điều kiện có thể dùng so sánh, `BETWEEN`, `IN`, `LIKE`, `IS NULL`, `EXISTS`, subquery và các biểu thức logic. Khi dùng `AND` và `OR` phức tạp, nên đặt ngoặc để rõ ý:

```sql
SELECT employee_id, full_name, department_id, active_flag
FROM lab_employees
WHERE active_flag = 'Y'
  AND (department_id = 10 OR department_id = 20);
```

Nếu bỏ ngoặc và viết `active_flag = 'Y' AND department_id = 10 OR department_id = 20`, toán tử `AND` có độ ưu tiên cao hơn `OR`; bạn có thể vô tình lấy cả nhân viên phòng 20 **không hoạt động** nếu dữ liệu có hàng như vậy.

### 7.1. `NULL` và logic ba giá trị

Trong SQL, một điều kiện có thể cho kết quả **TRUE**, **FALSE** hoặc **UNKNOWN** (thường do `NULL`). `WHERE` chỉ giữ hàng có điều kiện đánh giá **TRUE**.

Ví dụ sai để tìm người chưa gán phòng ban:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE department_id = NULL;
```

`= NULL` không là cách kiểm tra NULL hợp lệ về mặt logic. Hãy dùng:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE department_id IS NULL;
```

Kết quả: nhân viên **Lan**. Khi tìm nhân viên có lương, dùng `SALARY IS NOT NULL`:

```sql
SELECT full_name, salary
FROM lab_employees
WHERE salary IS NOT NULL;
```

**Lưu ý Oracle:** đối với các kiểu chuỗi ký tự thông thường, Oracle hiện coi chuỗi rỗng `''` như `NULL`. Vì vậy trường hợp kiểm tra một cột `VARCHAR2` có thể khác kỳ vọng từ ngôn ngữ lập trình vốn phân biệt chuỗi rỗng với null. Đây không phải nguyên tắc để suy ra mọi kiểu dữ liệu đều xử lý chuỗi rỗng như nhau.

### 7.2. `WHERE` và các hàm aggregate

Truy vấn sau không đúng:

```sql
SELECT department_id, COUNT(*) AS employee_count
FROM lab_employees
WHERE COUNT(*) >= 2
GROUP BY department_id;
```

`COUNT(*)` cần dữ liệu **sau khi nhóm** nên không được đặt làm điều kiện nhóm trong `WHERE`. Dùng `HAVING COUNT(*) >= 2`. Nếu chỉ cần lọc nhân viên active, điều kiện `ACTIVE_FLAG = 'Y'` vẫn phải ở `WHERE` trước khi nhóm.

## 8. `GROUP BY` và `HAVING`: từ hàng thành nhóm

`GROUP BY` đặt các hàng có cùng giá trị khóa nhóm vào một nhóm để tính aggregate.

```sql
SELECT
    department_id,
    COUNT(*) AS employee_count,
    COUNT(salary) AS salary_count,
    SUM(salary) AS salary_total,
    AVG(salary) AS average_salary
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
ORDER BY department_id NULLS LAST;
```

Trên dữ liệu mẫu, kết quả có thêm **một nhóm `DEPARTMENT_ID NULL`** chứa Lan. Oracle gom các giá trị NULL của khóa nhóm vào cùng một nhóm. Với nhóm `DEPARTMENT_ID=20`, `COUNT(*)=3` nhưng `COUNT(SALARY)=2` vì Hà chưa có lương.

### 8.1. Quy tắc đối với cột trong SELECT

Trong query block có `GROUP BY`, các biểu thức không phải aggregate trong danh sách `SELECT` thông thường phải là **biểu thức nhóm hợp lệ** theo quy tắc Oracle:

```sql
SELECT department_id, COUNT(*) AS total
FROM lab_employees
GROUP BY department_id;
```

Truy vấn thường sai:

```sql
SELECT department_id, full_name, COUNT(*) AS total
FROM lab_employees
GROUP BY department_id;
```

Vì một phòng ban có nhiều `FULL_NAME`, Oracle không biết phải chọn tên của hàng nào để đại diện cho nhóm. Oracle thường trả lỗi `ORA-00979: not a GROUP BY expression` hoặc lỗi tương ứng theo release. Nếu cần từng tên thì không nhóm theo phòng ban như vậy; nếu cần một giá trị đại diện, phải **định nghĩa rõ quy tắc** như `MIN(FULL_NAME)`, `MAX(FULL_NAME)` hoặc dùng analytic/subquery.

### 8.2. `WHERE` lọc trước; `HAVING` lọc sau

```sql
SELECT
    department_id,
    COUNT(*) AS active_count
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
HAVING COUNT(*) >= 2
ORDER BY department_id;
```

Kết quả theo dữ liệu mẫu:

| DEPARTMENT_ID | ACTIVE_COUNT |
| ---: | ---: |
| 10 | 2 |
| 20 | 3 |

`WHERE` bỏ nhân viên `ACTIVE_FLAG='N'` trước khi đếm. `HAVING` sau đó loại nhóm có ít hơn hai nhân viên active. Nếu chuyển `active_flag='Y'` sang `HAVING` mà không đưa nó vào GROUP BY/aggregate, ý nghĩa và tính hợp lệ sẽ khác.

### 8.3. Alias của phép tổng hợp và phạm vi HAVING

Ở Oracle 19c, ví dụ này thường không hợp lệ:

```sql
SELECT department_id, COUNT(*) AS active_count
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
HAVING active_count >= 2;
```

Viết đúng, tương thích tốt với các release Oracle cổ điển:

```sql
SELECT department_id, COUNT(*) AS active_count
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
HAVING COUNT(*) >= 2;
```

**Ghi chú phiên bản:** Các release Oracle mới hơn như 23ai/26ai bổ sung khả năng tham chiếu một số `SELECT` aliases và vị trí trong `GROUP BY`/`HAVING` theo cú pháp được hỗ trợ. Vì vậy không nên diễn đạt “Oracle *không bao giờ* cho alias trong HAVING”. Với code cần chạy trên 19c hoặc đa phiên bản, dùng biểu thức aggregate trực tiếp trong `HAVING` hoặc query block bên ngoài là cách dễ hiểu và đáng tin cậy.

### 8.4. `COUNT(*)` khác `COUNT(column)` và `COUNT(DISTINCT column)`

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(salary) AS rows_with_salary,
    COUNT(DISTINCT department_id) AS distinct_nonnull_departments
FROM lab_employees;
```

Trên 9 hàng dữ liệu mẫu:

- `COUNT(*) = 9` vì có 9 hàng.
- `COUNT(SALARY) = 8` vì một hàng có `SALARY NULL`.
- `COUNT(DISTINCT DEPARTMENT_ID) = 3` vì có các giá trị 10, 20, 30; `NULL` không được đếm như một giá trị phòng ban.

Khác biệt này đặc biệt quan trọng khi dùng `LEFT JOIN`. Nếu muốn đếm nhân viên thực sự trong mỗi phòng ban, hãy dùng `COUNT(e.employee_id)` thay vì `COUNT(*)`:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS joined_rows,
    COUNT(e.employee_id) AS actual_employees
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Đối với Pháp chế (40), `JOINED_ROWS = 1` vì có một hàng bù NULL của outer join, còn `ACTUAL_EMPLOYEES = 0` vì `E.EMPLOYEE_ID` là NULL. Đây là khác biệt giữa **đếm hàng sau JOIN** và **đếm đối tượng bên phải thực sự khớp**.

### 8.5. Aggregate trên tập trống

Một `SUM` trên các giá trị không có dữ liệu phù hợp có thể trả `NULL`, trong khi `COUNT` thường trả 0:

```sql
SELECT
    d.department_id,
    COUNT(e.employee_id) AS staff_count,
    SUM(e.salary) AS salary_sum,
    NVL(SUM(e.salary), 0) AS salary_sum_for_display
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id
ORDER BY d.department_id;
```

Với phòng 40: `STAFF_COUNT=0`, `SALARY_SUM=NULL` và `SALARY_SUM_FOR_DISPLAY=0`. `NVL` chỉ thay NULL ở kết quả; ứng dụng cần quyết định **NULL nghĩa là “chưa biết” hay “không có”** trước khi tự thay mọi NULL thành số 0.

## 9. `DISTINCT`: loại trùng sau phép chiếu

Khi viết:

```sql
SELECT department_id
FROM lab_employees
ORDER BY department_id NULLS LAST;
```

Kết quả có nhiều hàng trùng `DEPARTMENT_ID` vì mỗi nhân viên tạo một hàng. Thêm `DISTINCT`:

```sql
SELECT DISTINCT department_id
FROM lab_employees
ORDER BY department_id NULLS LAST;
```

Bạn sẽ nhận các giá trị **10, 20, 30 và NULL**, mỗi giá trị xuất hiện một lần trong kết quả của ví dụ. `DISTINCT` dùng trên **cả bộ các biểu thức** của danh sách `SELECT`:

```sql
SELECT DISTINCT department_id, active_flag
FROM lab_employees;
```

Ở đây nó loại bỏ **cặp trùng `(DEPARTMENT_ID, ACTIVE_FLAG)`**, không có nghĩa “giữ một hàng cho mỗi DEPARTMENT_ID”. Nếu muốn lấy **một nhân viên có lương cao nhất mỗi phòng ban**, cần một quy tắc chọn hàng, thường là analytic `ROW_NUMBER()` hoặc giải pháp nhóm và join có ràng buộc hòa điểm.

Không nên dùng `DISTINCT` như cách che một `JOIN` bị nhân bản hàng do điều kiện nối sai. `DISTINCT` có thể tốn tài nguyên sort/hash và làm mất thông tin về số lượng bản ghi.

## 10. `ORDER BY`: thứ tự đầu ra không tự tồn tại

Trong SQL, kết quả không có thứ tự được đảm bảo nếu truy vấn **không quy định `ORDER BY` ở query block trả ra kết quả**.

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
ORDER BY salary DESC NULLS LAST, employee_id;
```

Các quy tắc:

- `ASC`: tăng dần; đây là hướng mặc định nếu bỏ qua.
- `DESC`: giảm dần.
- `NULLS FIRST` / `NULLS LAST`: chỉ rõ vị trí NULL. Trong Oracle, mặc định **ASC đưa NULL cuối** và **DESC đưa NULL đầu**, nhưng tốt nhất ghi rõ nếu yêu cầu nghiệp vụ quan trọng.
- Nhiều khóa sắp xếp được xét theo thứ tự từ trái qua phải. Khóa thứ hai giải quyết các hàng có cùng giá trị khóa thứ nhất.

Trong dữ liệu mẫu, Dũng và Nga cùng có lương 2800. Nếu chỉ `ORDER BY SALARY DESC`, Oracle không bảo đảm ai đứng trước. Thêm `EMPLOYEE_ID` làm tie-breaker sẽ ổn định thứ tự.

### 10.1. `ORDER BY` có thể dùng alias

```sql
SELECT
    employee_id,
    full_name,
    salary * 12 AS annual_salary
FROM lab_employees
ORDER BY annual_salary DESC NULLS LAST, employee_id;
```

Alias `ANNUAL_SALARY` được phép trong `ORDER BY` của query block, mặc dù không dùng trực tiếp được trong `WHERE` ở ví dụ Oracle 19c. Có thể viết `ORDER BY 3 DESC` để chỉ vị trí biểu thức thứ ba của danh sách `SELECT`, nhưng cách này dễ hỏng ý nghĩa khi thay đổi thứ tự cột. Ưu tiên tên/biểu thức rõ ràng trong code cần bảo trì.

### 10.2. Sắp xếp chữ và NLS

`ORDER BY FULL_NAME` khi dùng Oracle có thể chịu ảnh hưởng của collation/NLS tùy cấu hình cột/session. Sắp xếp byte (`BINARY`) và thứ tự ngôn ngữ tiếng Việt là hai chính sách khác nhau. Với dữ liệu đa ngôn ngữ, cần kiểm tra quy tắc collation phù hợp.

Nếu truy vấn để phân trang, ngoài lựa chọn collation cần có **khóa phụ duy nhất** như `EMPLOYEE_ID` để tránh các hàng bằng nhau theo collation đổi thứ tự giữa các trang.

### 10.3. `ORDER BY` trong inline view

Một `ORDER BY` đặt trong subquery có thể phục vụ một phép lấy top-N hoặc yêu cầu cụ thể của query block, nhưng **đừng giả định nó bảo đảm thứ tự hiển thị cuối cùng nếu query bên ngoài không có `ORDER BY`**. Oracle có quyền biến đổi cách thực hiện truy vấn theo ngữ nghĩa SQL. Muốn hiển thị cuối cùng theo một thứ tự, đặt `ORDER BY` tại câu SELECT trả dữ liệu ra cho client.

## 11. `OFFSET` và `FETCH FIRST`: phân trang theo thứ tự đã chọn

Từ Oracle Database 12c, cú pháp **row limiting clause** cho phép yêu cầu:

```sql
SELECT
    employee_id,
    full_name,
    salary
FROM lab_employees
ORDER BY salary DESC NULLS LAST, employee_id
FETCH FIRST 3 ROWS ONLY;
```

Với dữ liệu mẫu, ba mức lương cao nhất có thể kể cả nhân viên inactive vì truy vấn này **không lọc `ACTIVE_FLAG`**. Nếu chỉ muốn nhân viên active, bổ sung `WHERE ACTIVE_FLAG='Y'`.

### 11.1. Bỏ qua hàng đầu để lấy trang tiếp theo

```sql
SELECT
    employee_id,
    full_name,
    salary
FROM lab_employees
WHERE active_flag = 'Y'
ORDER BY salary DESC NULLS LAST, employee_id
OFFSET 2 ROWS FETCH NEXT 2 ROWS ONLY;
```

Logic:

1. Lọc nhân viên active.
2. Sắp xếp theo lương giảm dần, NULL cuối, rồi employee ID.
3. Bỏ qua hai hàng đầu của kết quả **đã sắp xếp**.
4. Lấy tối đa hai hàng tiếp theo.

`FETCH FIRST ... ROWS ONLY` và `FETCH NEXT ... ROWS ONLY` diễn đạt việc giới hạn số hàng; số lượng được lấy có thể ít hơn con số yêu cầu nếu không đủ dữ liệu. Nếu không có `ORDER BY`, trang thứ nhất/thứ hai không có thứ tự ổn định để ứng dụng dựa vào.

### 11.2. `WITH TIES` khác `ONLY`

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary IS NOT NULL
ORDER BY salary DESC
FETCH FIRST 4 ROWS WITH TIES;
```

`WITH TIES` có thể trả **hơn** bốn hàng nếu hàng tại ngưỡng cắt có cùng giá trị khóa `ORDER BY` với các hàng tiếp theo. Đối với mức lương 2800 của Dũng và Nga, kết quả có thể cùng giữ cả hai nếu ngưỡng rơi vào nhóm đồng hạng. Thêm `EMPLOYEE_ID` vào `ORDER BY` làm khóa sắp xếp trở nên duy nhất, nên thông thường không còn nhiều hàng ngang ngưỡng theo toàn bộ bộ khóa.

**`WITH TIES` cần `ORDER BY`** để xác định quan hệ đồng hạng. Không dùng `WITH TIES` khi API cam kết trả đúng kích thước trang tuyệt đối.

### 11.3. Phân trang bằng OFFSET khi dữ liệu thay đổi

Nếu có nhiều giao dịch chèn/xóa giữa hai lần người dùng bấm “Trang sau”, offset pagination có thể **bỏ sót hoặc lặp hàng** dù đã `ORDER BY` ổn định. Với dữ liệu lớn, bỏ qua `OFFSET 100000 ROWS` còn có thể tốn công duyệt nhiều hàng trước khi trả trang.

Khi yêu cầu đọc danh sách ổn định qua nhiều trang, có thể cân nhắc:

- Sử dụng khóa sắp xếp **duy nhất và cố định**.
- Sử dụng **keyset/seek pagination**: nhớ giá trị khóa của hàng cuối trang trước rồi truy vấn hàng nằm sau khóa đó.
- Cân nhắc snapshot/transaction nhất quán khi nghiệp vụ yêu cầu cùng một tập dữ liệu, thay vì mong `OFFSET` tự giữ snapshot qua nhiều HTTP requests.

## 12. Oracle `ROWNUM` và bẫy top-N

Trước cú pháp `FETCH FIRST`, Oracle thường dùng pseudocolumn **`ROWNUM`** để đánh số hàng **theo thứ tự Oracle tạo hàng trong một query block**. Nó **không tương đương** với số thứ tự sau `ORDER BY` trong cùng query block.

### 12.1. Ví dụ dễ hiểu sai

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE ROWNUM <= 3
ORDER BY salary DESC;
```

Không được hiểu câu này là “lấy ba nhân viên có lương cao nhất”. Trong một mô hình thực thi điển hình, điều kiện `ROWNUM <= 3` giới hạn những hàng Oracle chọn được trước, rồi `ORDER BY` chỉ sắp xếp **ba hàng đó**. Việc planner chọn thứ tự truy cập index có thể tình cờ cho ra cùng kết quả mong muốn, nhưng không thể dựa vào đó như hợp đồng SQL.

### 12.2. Top-N bằng inline view

```sql
SELECT employee_id, full_name, salary
FROM (
    SELECT employee_id, full_name, salary
    FROM lab_employees
    WHERE salary IS NOT NULL
    ORDER BY salary DESC, employee_id
)
WHERE ROWNUM <= 3;
```

Ở đây `ORDER BY` nằm trong **inner query block**, còn `ROWNUM` giới hạn hàng do inline view đã sắp xếp cung cấp cho **outer query block**. Cách này được dùng trong các phiên bản Oracle trước cú pháp row limiting hiện đại. Để bảo đảm thứ tự trả về cuối cùng cho client trong những truy vấn tổng quát, có thể thêm `ORDER BY salary DESC, employee_id` ở query bên ngoài.

Khi release hỗ trợ, cách dễ đọc hơn là:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary IS NOT NULL
ORDER BY salary DESC, employee_id
FETCH FIRST 3 ROWS ONLY;
```

### 12.3. Vì sao `ROWNUM > 1` thường không hoạt động như mong đợi?

```sql
SELECT employee_id
FROM lab_employees
WHERE ROWNUM > 1;
```

Không thể coi `ROWNUM` trong `WHERE` của một query block như số hàng đã được đánh liên tục rồi lấy từ hàng thứ hai trở đi: hàng đầu tiên gặp điều kiện `ROWNUM > 1` không đạt, nên không có hàng nào được nhận làm “hàng thứ nhất” để ROWNUM tiếp tục lên 2. Đây là bẫy của cách Oracle gán `ROWNUM`.

Để lấy hàng từ một vị trí trong thứ tự, dùng `OFFSET/FETCH` sau `ORDER BY` hoặc gán `ROW_NUMBER()` trong subquery rồi lọc ở outer query.

## 13. `WITH` và inline view: chia query block để suy luận dễ hơn

Một câu `SELECT` lớn có thể được viết thành các **Common Table Expressions (CTE)** bằng `WITH`:

```sql
WITH active_employees AS (
    SELECT department_id, employee_id, salary
    FROM lab_employees
    WHERE active_flag = 'Y'
),
department_totals AS (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        SUM(salary) AS total_salary
    FROM active_employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
)
SELECT
    d.department_name,
    t.employee_count,
    t.total_salary
FROM department_totals t
JOIN lab_departments d
  ON d.department_id = t.department_id
WHERE t.employee_count >= 2
ORDER BY t.total_salary DESC, d.department_id;
```

Ở query block `DEPARTMENT_TOTALS`, `EMPLOYEE_COUNT` trở thành **cột kết quả của CTE**. Query bên ngoài có thể dùng `WHERE t.employee_count >= 2` vì ở cấp ngoài đó là cột nguồn đã có, không còn là alias đang được tạo trong cùng SELECT.

**Không hiểu CTE là bảng tạm vật lý mặc định.** Optimizer có thể inline/gộp hoặc vật hóa CTE tùy ngữ nghĩa và kế hoạch. Giá trị cốt lõi của `WITH` đối với người học là **đặt tên cho các bước logic**, chia phạm vi alias và làm truy vấn dễ đọc.

### Một cách kiểm tra tư duy từng bước

Với một query phức tạp, thử liệt kê:

1. Có những **query block** nào (main query, CTE, inline view, subquery)?
2. Nguồn hàng của **từng block** là gì?
3. `WHERE` loại hàng nào trước khi group?
4. `GROUP BY` tạo bao nhiêu nhóm, và `HAVING` loại nhóm nào?
5. `SELECT` tạo ra cột/alias nào để **query block bên ngoài** có thể tham chiếu?
6. `DISTINCT`, `ORDER BY` và `FETCH` tác động vào tập kết quả cuối của **block nào**?

Quy trình này giúp tránh nhầm alias thuộc scope khác và phân biệt một predicate lọc **hàng gốc** với predicate lọc **kết quả đã tổng hợp**.

## 14. Analytic functions: một lớp quan trọng sau GROUP/HAVING

Trong SQL, **aggregate** như `SUM(salary)` thường gộp nhiều hàng thành một hàng theo nhóm. **Analytic function** như `ROW_NUMBER() OVER (...)` tính kết quả theo cửa sổ nhưng **không tự gộp mất những hàng đầu vào**.

Ví dụ đánh số nhân viên active theo mức lương trong từng phòng ban:

```sql
SELECT
    employee_id,
    full_name,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC NULLS LAST, employee_id
    ) AS rn
FROM lab_employees
WHERE active_flag = 'Y';
```

`WHERE` loại nhân viên không hoạt động trước khi analytic đánh số; `ROW_NUMBER` có `PARTITION BY department_id` chia nhân viên còn lại theo phòng ban và đánh số trong mỗi partition.

Lỗi thường gặp:

```sql
SELECT
    employee_id,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS rn
FROM lab_employees
WHERE rn = 1;
```

Không thể dùng `RN` hoặc analytic expression trực tiếp trong `WHERE` **cùng query block** theo mô hình cú pháp Oracle cơ bản. Đặt analytic ở query block trong, lọc ở ngoài:

```sql
SELECT employee_id, full_name, department_id, salary
FROM (
    SELECT
        employee_id,
        full_name,
        department_id,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC NULLS LAST, employee_id
        ) AS rn
    FROM lab_employees
    WHERE active_flag = 'Y'
)
WHERE rn = 1
ORDER BY department_id NULLS LAST, employee_id;
```

Lúc này query bên ngoài chọn **nhân viên active có lương cao nhất của mỗi phòng ban** theo tie-breaker đã định. Vì `DEPARTMENT_ID NULL` cũng được `PARTITION BY` gom cùng nhau, Lan có thể đại diện cho nhóm chưa được phân phòng nếu không bổ sung điều kiện `DEPARTMENT_ID IS NOT NULL`.

**Lưu ý release:** Các phiên bản Oracle mới có thể cung cấp cú pháp lọc kết quả analytic thuận tiện hơn (ví dụ các mở rộng window/qualify). Đối với SQL cần chạy trên 19c, inline view/CTE là cách minh họa phổ biến và tương thích.

## 15. Logical processing khác execution plan vật lý

Nếu hiểu “Oracle chạy `FROM` xong mới đụng đến `WHERE` trong mọi trường hợp” theo nghĩa **thời gian thực thi tuyệt đối**, bạn sẽ hiểu sai optimizer.

Ví dụ:

```sql
SELECT
    d.department_name,
    COUNT(*) AS active_count
FROM lab_employees e
JOIN lab_departments d
  ON d.department_id = e.department_id
WHERE e.active_flag = 'Y'
GROUP BY d.department_name
ORDER BY active_count DESC;
```

Để tạo cùng kết quả, Oracle có thể:

- Quét bảng nhân viên và **lọc `ACTIVE_FLAG='Y'` ngay tại table access**.
- Dùng **index range scan** nếu có index phù hợp và chi phí dự kiến tốt hơn full scan.
- Chọn **nested loops**, **hash join** hoặc phương thức join khác.
- Thực hiện **hash group by** hoặc **sort group by**.
- Sắp xếp cuối bằng `SORT ORDER BY`, hoặc tránh một số sort khi access path đã thỏa thứ tự cần thiết.

Điều này không làm đảo ý nghĩa `WHERE`/`GROUP BY`/`HAVING`. Các phép biến đổi optimizer phải giữ kết quả theo các quy tắc SQL và tính nhất quán giao dịch thích hợp.

### 15.1. Xem kế hoạch dự kiến

```sql
EXPLAIN PLAN FOR
SELECT d.department_name, COUNT(*) AS active_count
FROM lab_employees e
JOIN lab_departments d
  ON d.department_id = e.department_id
WHERE e.active_flag = 'Y'
GROUP BY d.department_name
ORDER BY active_count DESC;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` cho **kế hoạch dự kiến** dựa trên môi trường và thống kê lúc phân tích; nó không phải bản ghi chắc chắn của một lần chạy thật. Khi phân tích hiệu năng production, DBA có thể cần `DBMS_XPLAN.DISPLAY_CURSOR`, row counts thực tế, logical/physical I/O và thông tin thời gian của cursor được thực thi.

### 15.2. SQL là ngôn ngữ khai báo

Thay vì viết “đọc bảng A, sau đó vòng lặp 1000 lần tìm bảng B”, SQL mô tả **tập kết quả mong muốn**. Optimizer chịu trách nhiệm tìm phương án thực thi cụ thể. **Thứ tự xử lý logic** giúp người học xác minh ý nghĩa của câu truy vấn; **execution plan** giúp người quản trị/lập trình viên phân tích hiệu năng thực thi.

## 16. Các lỗi thường gặp và cách nhận diện

| Hiện tượng | Nguyên nhân điển hình | Cách viết/kiểm tra phù hợp |
| --- | --- | --- |
| `ORA-00904` khi lọc theo alias trong `WHERE` | Alias `SELECT` chưa có trong phạm vi `WHERE` của cùng block | Lặp biểu thức hoặc dùng inline view/CTE |
| `ORA-00979` với query có `GROUP BY` | Đưa cột không được nhóm/aggregate vào `SELECT` | Nhóm cột phù hợp hoặc định nghĩa aggregate |
| Không thể dùng `COUNT(*)` trong `WHERE` | Aggregate thuộc pha nhóm | Dùng `HAVING COUNT(*) ...` |
| Phòng ban không có nhân viên biến mất khỏi `LEFT JOIN` | Điều kiện trên bảng phải nằm trong `WHERE` loại hàng NULL bổ sung | Đặt điều kiện trong `ON` khi muốn bảo toàn bảng trái |
| `COUNT(*)` cho phòng ban rỗng là 1 | Hàng NULL được `LEFT JOIN` sinh ra vẫn là một hàng | `COUNT(e.employee_id)` |
| `SUM` trả NULL trong nhóm không có lương | Aggregate bỏ qua NULL, không có giá trị phù hợp để tính tổng | `NVL(SUM(...), 0)` khi nghĩa nghiệp vụ phù hợp |
| `WHERE x = NULL` không tìm được hàng | So sánh với NULL cho UNKNOWN | `WHERE x IS NULL` |
| `DISTINCT` làm biến mất số lượng bản ghi | Loại trùng toàn bộ tuple kết quả | Kiểm tra join/cardinality; không dùng như mẹo sửa join |
| `FETCH FIRST` trả hàng khó dự đoán | Thiếu `ORDER BY` hoặc thiếu tie-breaker | `ORDER BY` khóa ổn định/duy nhất |
| `ROWNUM <= 3 ORDER BY salary DESC` không cho top 3 thực | ROWNUM giới hạn trước sort của cùng block | `FETCH FIRST` hoặc inner sorted query + outer ROWNUM |
| `WHERE ROWNUM > 1` không cho trang thứ hai | Đặc điểm gán ROWNUM theo hàng được nhận | `OFFSET` hoặc subquery dùng `ROW_NUMBER` |
| Cần lọc theo `ROW_NUMBER()` nhưng query lỗi | Analytic được tính sau `WHERE` trong cùng block | Tính analytic bên trong, lọc `RN` bên ngoài |
| Kết quả từ index scan có vẻ đã sắp xếp | Trật tự vật lý không phải hợp đồng SQL | Luôn chỉ định `ORDER BY` khi cần |
| Kết quả group đúng nhưng query chạy chậm | Logical order không cho biết physical plan | Xem optimizer statistics và execution plan |
| `WHERE salary > 2500` không giữ hàng `SALARY NULL` | NULL làm điều kiện UNKNOWN | Quy định rõ chính sách xử lý NULL |
| Alias trong `HAVING` chạy ở bản mới nhưng lỗi trên 19c | Tính năng alias trong nhóm khác theo release | Dùng aggregate expression trực tiếp cho code cần đa phiên bản |

## 17. Bài tập thực hành

Tất cả bài tập sử dụng hai bảng `LAB_EMPLOYEES` và `LAB_DEPARTMENTS` ở mục 2. Hãy **dự đoán số hàng/kết quả trước**, rồi mới chạy SQL để đối chiếu.

### Bài 1 — Lọc và sắp xếp

Viết truy vấn lấy `EMPLOYEE_ID`, `FULL_NAME`, `SALARY` của nhân viên:

1. Đang hoạt động (`ACTIVE_FLAG='Y'`).
2. Có mức lương từ 2500 trở lên.
3. Sắp xếp lương giảm dần; nếu cùng lương, `EMPLOYEE_ID` tăng dần.

**Đáp án gợi ý:**

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE active_flag = 'Y'
  AND salary >= 2500
ORDER BY salary DESC, employee_id;
```

### Bài 2 — Nhóm nhân viên theo phòng ban

Viết SQL đếm nhân viên **active** theo phòng ban (kể cả người chưa được gán phòng), trả về `DEPARTMENT_ID` và `ACTIVE_COUNT`; chỉ giữ những nhóm có từ hai người.

```sql
SELECT department_id, COUNT(*) AS active_count
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
HAVING COUNT(*) >= 2
ORDER BY department_id NULLS LAST;
```

Kết quả mong đợi có phòng ban **10 và 20**. Lan tạo một nhóm `DEPARTMENT_ID NULL` với một người nên không qua `HAVING`.

### Bài 3 — Bảo toàn phòng ban rỗng

Viết một query trả cả phòng ban 40 và số nhân viên active của từng phòng ban, kể cả bằng 0. Dùng `LEFT JOIN`, đặt điều kiện active trong `ON`, rồi đếm bằng `COUNT(e.employee_id)`:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS active_count
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Kỳ vọng: 10 có 2, 20 có 3, 30 có 1 và 40 có 0. Hãy chuyển `e.active_flag = 'Y'` xuống `WHERE` rồi so sánh kết quả; giải thích bằng thứ tự logic.

### Bài 4 — Một nhân viên có lương cao nhất trong mỗi phòng

Dùng `ROW_NUMBER()` để lấy một nhân viên active có lương cao nhất trong từng phòng ban, giải quyết trùng lương bằng `EMPLOYEE_ID`. Bỏ nhóm `DEPARTMENT_ID NULL` nếu yêu cầu chỉ tính người đã có phòng ban.

```sql
SELECT employee_id, full_name, department_id, salary
FROM (
    SELECT
        employee_id,
        full_name,
        department_id,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC NULLS LAST, employee_id
        ) AS rn
    FROM lab_employees
    WHERE active_flag = 'Y'
      AND department_id IS NOT NULL
)
WHERE rn = 1
ORDER BY department_id;
```

Hãy giải thích vì sao truy vấn dùng **hai SELECT blocks** thay vì đặt `WHERE RN=1` trong block chứa hàm analytic.

### Bài 5 — Top-N và phân trang

Thực hiện ba truy vấn:

1. `FETCH FIRST 3 ROWS ONLY` sau `ORDER BY SALARY DESC NULLS LAST, EMPLOYEE_ID`.
2. `OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY` với cùng `ORDER BY`.
3. `WHERE ROWNUM <= 3 ORDER BY SALARY DESC` trong cùng block.

Ghi lại kết quả và giải thích vì sao truy vấn 3 **không được dùng làm định nghĩa top 3 mức lương cao nhất**.

### Bài 6 — Phân biệt `WHERE` và `HAVING`

Cho hai yêu cầu:

- **A:** tính trung bình lương của các nhân viên active trong từng phòng, nhưng **chỉ giữ những nhân viên có lương từ 2500 trở lên trước khi tính**.
- **B:** tính trung bình lương của **toàn bộ nhân viên active** trong từng phòng, nhưng **chỉ hiện những phòng có trung bình từ 2500 trở lên**.

Hai câu query phải khác nhau:

```sql
-- A: điều kiện trên hàng nằm ở WHERE.
SELECT department_id, AVG(salary) AS avg_salary
FROM lab_employees
WHERE active_flag = 'Y'
  AND salary >= 2500
GROUP BY department_id
ORDER BY department_id NULLS LAST;

-- B: điều kiện trên nhóm nằm ở HAVING.
SELECT department_id, AVG(salary) AS avg_salary
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
HAVING AVG(salary) >= 2500
ORDER BY department_id NULLS LAST;
```

Chú ý cả hai đều có thể gặp nhóm chứa giá trị NULL; `AVG` bỏ qua các hàng có `SALARY NULL`. Đừng chỉ nhìn các số trùng hợp giống nhau trên dữ liệu mẫu mà kết luận `WHERE` và `HAVING` thay thế được nhau.

### Bài 7 — Sửa câu SQL sai

Cho câu lệnh:

```sql
SELECT
    d.department_name,
    COUNT(*) AS staff_count,
    SUM(e.salary) AS total_salary
FROM lab_departments d
LEFT JOIN lab_employees e
    ON d.department_id = e.department_id
WHERE e.active_flag = 'Y'
  AND total_salary > 3000
GROUP BY d.department_name
ORDER BY total_salary DESC;
```

Yêu cầu thật: hiển thị **mọi phòng ban**, kể cả phòng không có nhân viên active, đồng thời có khả năng lọc phòng ban tổng lương active lớn hơn 3000 khi người dùng bật tùy chọn đó. Hãy:

1. Giải thích vì sao alias `TOTAL_SALARY` không dùng được trực tiếp trong `WHERE`.
2. Đưa điều kiện nhân viên active vào đúng vị trí để có thể bảo toàn phòng ban rỗng.
3. Dùng `COUNT(e.employee_id)` thay `COUNT(*)` nếu đếm số nhân viên thật.
4. Khi **bật** bộ lọc tổng lương, dùng `HAVING NVL(SUM(e.salary),0) > 3000`; khi **tắt**, bỏ `HAVING` để giữ toàn bộ phòng ban.

Một phiên bản **không lọc tổng lương**, bảo toàn mọi phòng ban:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS staff_count,
    NVL(SUM(e.salary), 0) AS total_salary
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
GROUP BY d.department_id, d.department_name
ORDER BY total_salary DESC, d.department_id;
```

Nếu thêm `HAVING NVL(SUM(e.salary), 0) > 3000`, các phòng không đạt ngưỡng sẽ bị loại — **đó là thay đổi theo yêu cầu lọc**, không thể đồng thời yêu cầu hiển thị mọi phòng với mọi mức tổng lương khi bộ lọc đang bật.

## 18. Dọn dữ liệu thực hành

Chỉ chạy trong **schema lab mà bạn sở hữu**, sau khi hoàn thành bài tập:

```sql
DROP TABLE lab_employees PURGE;
DROP TABLE lab_departments PURGE;
```

Xóa bảng con `LAB_EMPLOYEES` trước vì nó có foreign key tới `LAB_DEPARTMENTS`. `PURGE` bỏ qua recycle bin; đừng dùng câu lệnh này đối với bảng cần phục hồi hoặc không do bạn sở hữu.

## Tổng kết

Để hiểu một câu `SELECT` Oracle, hãy suy luận theo **dòng chảy dữ liệu**: `FROM/JOIN` xây tập hàng nguồn, `WHERE` lọc hàng, `GROUP BY` lập nhóm, `HAVING` lọc nhóm, `SELECT` tạo kết quả/alias, `DISTINCT` bỏ dòng trùng, `ORDER BY` sắp thứ tự, rồi `OFFSET/FETCH` lấy một phần kết quả. `WITH`, inline view và analytic functions mở rộng cách tổ chức query block nhưng không xóa các quy tắc về phạm vi và thứ tự logic.

Phân biệt rõ **logic SQL** với **execution plan** sẽ giúp bạn vừa viết truy vấn **đúng ý nghĩa**, vừa biết khi nào cần tra optimizer và I/O thay vì suy đoán tốc độ từ thứ tự các dòng SQL. Khi có `NULL`, outer join, aggregation, pagination hoặc alias, hãy vẽ các giai đoạn và kiểm chứng tập hàng ở từng pha trước khi kết luận kết quả.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — SELECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — cú pháp `FROM`, `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, row limiting và các giới hạn liên quan.
- [Oracle Database SQL Language Reference — Aggregate Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html) — ngữ nghĩa `COUNT`, `SUM`, `AVG` và xử lý NULL.
- [Oracle Database SQL Language Reference — Analytic Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html) — vị trí tính analytic trong một query block.
- [Oracle Database SQL Language Reference — ROWNUM Pseudocolumn (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html) — khác biệt giữa `ROWNUM` và top-N được sắp xếp.
- [Oracle Database SQL Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — optimizer, phương án join, execution plan và phân tích hiệu năng.

Khi làm việc với Oracle 23ai/26ai hoặc release khác 19c, đối chiếu tài liệu đúng release về những khả năng cú pháp mới (đặc biệt alias trong `GROUP BY`/`HAVING` và analytic filtering). Mô hình thứ tự xử lý logic vẫn là nền tảng để hiểu truy vấn.

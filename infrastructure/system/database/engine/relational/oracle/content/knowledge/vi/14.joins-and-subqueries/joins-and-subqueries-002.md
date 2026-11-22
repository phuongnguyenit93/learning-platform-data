# LEFT, RIGHT và FULL OUTER JOIN

Trong Oracle Database, **outer join** cho phép kết hợp dữ liệu từ hai nguồn mà vẫn giữ lại những hàng không tìm thấy đối tác phù hợp ở phía còn lại. Đây là khác biệt quan trọng so với **INNER JOIN**, vốn chỉ trả về những cặp hàng thỏa điều kiện nối.

Ba dạng outer join cơ bản:

- **LEFT OUTER JOIN:** giữ tất cả hàng từ nguồn bên trái; nếu không có hàng phù hợp bên phải, các cột phía phải được bổ sung NULL.
- **RIGHT OUTER JOIN:** giữ tất cả hàng từ nguồn bên phải; nếu không có hàng phù hợp bên trái, các cột phía trái được bổ sung NULL.
- **FULL OUTER JOIN:** giữ tất cả hàng từ cả hai nguồn; hàng không có đối tác được bổ sung NULL ở phía còn lại.

Từ khóa `OUTER` có thể được lược bỏ: `LEFT JOIN`, `RIGHT JOIN` và `FULL JOIN` có cùng ý nghĩa tương ứng. Trong SQL ứng dụng, nên dùng cú pháp ANSI JOIN với `ON` hoặc `USING` để thể hiện quan hệ giữa các bảng rõ ràng.

Bài học tập trung vào việc đọc đúng kết quả outer join, đặc biệt là **hàng NULL-extended**, vị trí đặt điều kiện `ON` và `WHERE`, cách tìm hàng không có đối tác, và cách tránh đếm sai hoặc nhân bản dữ liệu sau khi nối.

## 1. INNER JOIN và OUTER JOIN khác nhau thế nào?

Giả sử có hai bảng:

```text
DEPARTMENTS                         EMPLOYEES
  DEPARTMENT_ID (PK) <------------+   EMPLOYEE_ID (PK)
  DEPARTMENT_NAME                 +-- DEPARTMENT_ID (FK, nullable)
                                      FULL_NAME
```

Với `INNER JOIN`, chỉ các cặp hàng có khóa phòng ban khớp mới xuất hiện. Với `LEFT JOIN`, mọi phòng ban vẫn xuất hiện dù chưa có nhân viên. Với `FULL OUTER JOIN`, cả phòng ban không có nhân viên và nhân viên chưa gán phòng đều được giữ lại.

| Loại JOIN | Giữ toàn bộ hàng của bên trái? | Giữ toàn bộ hàng của bên phải? | Hàng không khớp |
| --- | :---: | :---: | --- |
| `INNER JOIN` | Không | Không | Bị loại |
| `LEFT OUTER JOIN` | Có | Không | Bổ sung NULL ở phía phải |
| `RIGHT OUTER JOIN` | Không | Có | Bổ sung NULL ở phía trái |
| `FULL OUTER JOIN` | Có | Có | Bổ sung NULL ở phía không khớp |

Sơ đồ khái niệm:

```text
LEFT OUTER JOIN
  Tất cả A + phần B khớp

RIGHT OUTER JOIN
  Phần A khớp + tất cả B

FULL OUTER JOIN
  Tất cả A + tất cả B
  (ghép thành cặp khi điều kiện ON là TRUE)
```

**Outer join không tự tạo dữ liệu nghiệp vụ còn thiếu.** Oracle chỉ tạo một hàng kết quả có các cột của phía không khớp mang NULL để biểu diễn rằng không tìm được hàng đối tác.

## 2. Tạo dữ liệu thực hành

Các ví dụ dùng schema lab riêng. Chạy DDL trong schema bạn sở hữu, có quyền `CREATE TABLE` và quota tablespace. Không chạy lệnh tạo/xóa bảng trên schema ứng dụng đang hoạt động.

### 2.1. Tạo hai bảng

```sql
CREATE TABLE lab_departments (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE lab_employees (
    employee_id   NUMBER PRIMARY KEY,
    full_name     VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER,
    active_flag   CHAR(1) DEFAULT 'Y' NOT NULL,
    salary        NUMBER(12, 2),
    CONSTRAINT fk_lab_employees_department
        FOREIGN KEY (department_id)
        REFERENCES lab_departments (department_id),
    CONSTRAINT ck_lab_employees_active
        CHECK (active_flag IN ('Y', 'N'))
);
```

### 2.2. Chèn dữ liệu

```sql
INSERT INTO lab_departments VALUES (10, 'Kỹ thuật');
INSERT INTO lab_departments VALUES (20, 'Kinh doanh');
INSERT INTO lab_departments VALUES (30, 'Nhân sự');
INSERT INTO lab_departments VALUES (40, 'Pháp chế');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, active_flag, salary)
VALUES (1, 'An', 10, 'Y', 5000);

INSERT INTO lab_employees
    (employee_id, full_name, department_id, active_flag, salary)
VALUES (2, 'Bình', 10, 'Y', 3000);

INSERT INTO lab_employees
    (employee_id, full_name, department_id, active_flag, salary)
VALUES (3, 'Chi', 20, 'N', 2800);

INSERT INTO lab_employees
    (employee_id, full_name, department_id, active_flag, salary)
VALUES (4, 'Dũng', NULL, 'Y', 4200);

INSERT INTO lab_employees
    (employee_id, full_name, department_id, active_flag, salary)
VALUES (5, 'Hà', 30, 'Y', NULL);

COMMIT;
```

Dữ liệu có các trường hợp cần quan sát:

| Phòng ban | Nhân viên | Trạng thái |
| --- | --- | --- |
| Kỹ thuật (10) | An, Bình | Có hai nhân viên |
| Kinh doanh (20) | Chi | Nhân viên không active |
| Nhân sự (30) | Hà | Có nhân viên, salary NULL |
| Pháp chế (40) | Không có | Phòng ban rỗng |
| Không có phòng ban | Dũng | Nhân viên có `DEPARTMENT_ID NULL` |

Phòng 40 giúp quan sát hàng không khớp ở phía nhân viên. Dũng giúp quan sát hàng không khớp ở phía phòng ban. Đây là hai hướng khác nhau của outer join.

## 3. LEFT OUTER JOIN: giữ tất cả hàng bên trái

Cú pháp:

```sql
SELECT select_list
FROM left_table l
LEFT [OUTER] JOIN right_table r
  ON join_condition;
```

Ví dụ: lấy tất cả phòng ban, kèm thông tin nhân viên nếu có:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name,
    e.active_flag
FROM lab_departments d
LEFT OUTER JOIN lab_employees e
  ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
```

Kết quả logic:

| DEPARTMENT_ID | DEPARTMENT_NAME | EMPLOYEE_ID | FULL_NAME | ACTIVE_FLAG |
| ---: | --- | ---: | --- | :---: |
| 10 | Kỹ thuật | 1 | An | Y |
| 10 | Kỹ thuật | 2 | Bình | Y |
| 20 | Kinh doanh | 3 | Chi | N |
| 30 | Nhân sự | 5 | Hà | Y |
| 40 | Pháp chế | NULL | NULL | NULL |

Phòng 40 vẫn có một hàng kết quả. Các cột `E.*` mang NULL vì không tìm thấy nhân viên phù hợp. Dũng không xuất hiện vì bảng bên trái là `LAB_DEPARTMENTS`; `LEFT JOIN` không có nghĩa là “giữ mọi hàng của cả hai bảng”.

### 3.1. Hàng NULL-extended là gì?

Với phòng ban 40, Oracle tạo hàng kết quả có dạng:

```text
D.DEPARTMENT_ID   = 40
D.DEPARTMENT_NAME = 'Pháp chế'
E.EMPLOYEE_ID     = NULL
E.FULL_NAME       = NULL
E.ACTIVE_FLAG     = NULL
E.SALARY          = NULL
```

Đây không phải một hàng nhân viên được lưu trong `LAB_EMPLOYEES`. Nó là hàng được bổ sung trong kết quả outer join để bảo toàn hàng phòng ban.

Vì vậy, khi đếm nhân viên, không nên dùng `COUNT(*)` một cách máy móc:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS joined_rows,
    COUNT(e.employee_id) AS employee_count
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Với phòng 40:

- `COUNT(*) = 1`: hàng NULL-extended vẫn là một hàng kết quả.
- `COUNT(e.employee_id) = 0`: khóa chính nhân viên là NULL trên hàng bổ sung, nên không được đếm.

Khi cần đếm hàng con, hãy đếm một cột phía con **không NULL trên mọi hàng thật**, thường là primary key.

### 3.2. Giữ phòng ban nhưng chỉ nối nhân viên active

Yêu cầu: hiển thị mọi phòng ban, nhưng chỉ nối nhân viên có `ACTIVE_FLAG = 'Y'`.

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name,
    e.active_flag
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

Kết quả vẫn có cả phòng 40. Phòng Kinh doanh (20) cũng được giữ, nhưng Chi bị loại khỏi phần ghép vì không active; do không có nhân viên active phù hợp, các cột `E.*` của phòng 20 được bổ sung NULL.

Điều kiện `E.ACTIVE_FLAG = 'Y'` được đặt trong `ON` vì nó xác định **hàng bên phải nào đủ điều kiện để ghép** với hàng phòng ban.

## 4. RIGHT OUTER JOIN: giữ tất cả hàng bên phải

Cú pháp:

```sql
SELECT select_list
FROM left_table l
RIGHT [OUTER] JOIN right_table r
  ON join_condition;
```

Để giữ tất cả nhân viên, kể cả người chưa có phòng ban:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
RIGHT OUTER JOIN lab_employees e
  ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

Kết quả có An, Bình, Chi, Dũng và Hà. Dũng xuất hiện với các cột phòng ban NULL vì `DEPARTMENT_ID` của Dũng chưa được gán.

| DEPARTMENT_ID | DEPARTMENT_NAME | EMPLOYEE_ID | FULL_NAME |
| ---: | --- | ---: | --- |
| 10 | Kỹ thuật | 1 | An |
| 10 | Kỹ thuật | 2 | Bình |
| 20 | Kinh doanh | 3 | Chi |
| NULL | NULL | 4 | Dũng |
| 30 | Nhân sự | 5 | Hà |

### 4.1. RIGHT JOIN có thể viết lại bằng LEFT JOIN

Hai câu sau tương đương về tập kết quả:

```sql
-- RIGHT JOIN
SELECT d.department_id, e.employee_id, e.full_name
FROM lab_departments d
RIGHT JOIN lab_employees e
  ON e.department_id = d.department_id;

-- Đảo vị trí nguồn và dùng LEFT JOIN
SELECT d.department_id, e.employee_id, e.full_name
FROM lab_employees e
LEFT JOIN lab_departments d
  ON d.department_id = e.department_id;
```

Nhiều nhóm phát triển thích chuẩn hóa về `LEFT JOIN` vì cách đọc “giữ bảng bên trái” nhất quán hơn. `RIGHT JOIN` vẫn hợp lệ và đôi khi đọc tự nhiên khi nguồn cần giữ lại đang được đặt bên phải trong một câu truy vấn có cấu trúc cố định.

**Không đổi thứ tự hai bảng mà quên đổi hướng outer join.** `A LEFT JOIN B` và `B LEFT JOIN A` không tương đương; câu thứ hai phải là `B RIGHT JOIN A` mới giữ cùng phía dữ liệu.

## 5. FULL OUTER JOIN: giữ tất cả hàng của cả hai phía

Cú pháp:

```sql
SELECT select_list
FROM left_table l
FULL [OUTER] JOIN right_table r
  ON join_condition;
```

Ví dụ:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
FULL OUTER JOIN lab_employees e
  ON e.department_id = d.department_id
ORDER BY d.department_id NULLS LAST, e.employee_id;
```

Kết quả có:

- Tất cả các phòng ban, kể cả Pháp chế không có nhân viên.
- Tất cả nhân viên, kể cả Dũng chưa có phòng ban.
- Các cặp phòng ban/nhân viên khớp theo `DEPARTMENT_ID`.

Kết quả minh họa:

| DEPARTMENT_ID | DEPARTMENT_NAME | EMPLOYEE_ID | FULL_NAME |
| ---: | --- | ---: | --- |
| 10 | Kỹ thuật | 1 | An |
| 10 | Kỹ thuật | 2 | Bình |
| 20 | Kinh doanh | 3 | Chi |
| 30 | Nhân sự | 5 | Hà |
| 40 | Pháp chế | NULL | NULL |
| NULL | NULL | 4 | Dũng |

Một hàng không khớp ở **bên trái** có cột phía phải NULL; một hàng không khớp ở **bên phải** có cột phía trái NULL. FULL JOIN không loại hàng nào chỉ vì không tìm thấy đối tác.

### 5.1. NULL trong khóa nối không khớp với NULL

Điều kiện:

```sql
ON e.department_id = d.department_id
```

không xem hai giá trị NULL là bằng nhau. Trong SQL, `NULL = NULL` là UNKNOWN, không phải TRUE. Vì vậy nếu cả hai bảng đều có một hàng với `DEPARTMENT_ID NULL`, hai hàng đó **không tự ghép thành một cặp**. FULL JOIN sẽ giữ mỗi hàng riêng như các hàng không khớp.

Nếu nghiệp vụ thật sự muốn coi hai NULL là cùng một nhóm, phải thiết kế điều kiện so khớp rõ ràng. Không nên thêm `OR (a.key IS NULL AND b.key IS NULL)` một cách tùy tiện, vì nhiều hàng NULL ở hai phía có thể tạo phép ghép nhiều-nhiều và nhân kết quả. Thông thường, khóa quan hệ nên là giá trị định danh không NULL; NULL biểu thị chưa có khóa liên kết.

### 5.2. Chọn khóa hiển thị cho FULL JOIN

Trong FULL JOIN, cột khóa ở bên trái có thể NULL đối với hàng chỉ tồn tại bên phải, và cột khóa ở bên phải có thể NULL đối với hàng chỉ tồn tại bên trái. Nếu muốn hiển thị một cột khóa chung:

```sql
SELECT
    COALESCE(d.department_id, e.department_id) AS department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
FULL OUTER JOIN lab_employees e
  ON e.department_id = d.department_id
ORDER BY department_id NULLS LAST, e.employee_id;
```

`COALESCE` lấy giá trị không NULL đầu tiên. Với hàng khớp, hai khóa giống nhau; với hàng phòng ban không có nhân viên, lấy khóa bên trái; với nhân viên chưa gán phòng, cả hai khóa đều NULL trong ví dụ này. Cột kết quả `DEPARTMENT_ID` do đó vẫn NULL đối với Dũng, đúng với việc Dũng chưa có phòng ban.

Nếu dùng `USING (department_id)`, Oracle cung cấp một cột nối chung trong select list thay vì hai cột khóa riêng biệt. Tuy nhiên, `USING` có quy tắc tham chiếu cột riêng; không được tiền tố cột nối bằng alias bảng trong select list. Với FULL JOIN, cần hiểu rõ giá trị khóa chung được trả ra và có thể dùng `COALESCE` tường minh nếu muốn diễn đạt ý định rõ ràng.

## 6. ON và WHERE: khác biệt quan trọng nhất của OUTER JOIN

`ON` xác định cặp hàng nào khớp trong phép JOIN. `WHERE` lọc các hàng của kết quả query block sau khi phép nối logic được hình thành. Với INNER JOIN, nhiều điều kiện có thể chuyển đổi giữa ON và WHERE mà không đổi kết quả; với OUTER JOIN, việc di chuyển điều kiện có thể làm thay đổi tập hàng được bảo toàn.

### 6.1. Điều kiện bảng phải đặt trong WHERE có thể biến LEFT JOIN thành INNER JOIN

Truy vấn:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

Phòng Pháp chế không có nhân viên, nên hàng NULL-extended có `E.ACTIVE_FLAG = NULL`. Điều kiện `NULL = 'Y'` là UNKNOWN; WHERE chỉ giữ TRUE, vì vậy hàng phòng 40 bị loại.

Phòng Kinh doanh chỉ có Chi không active; hàng Chi bị WHERE loại. Vì một hàng đã khớp ở ON nên Oracle không tạo thêm một hàng NULL-extended thay thế cho phòng 20. Kết quả không giữ được hai phòng ban này.

Nếu yêu cầu là **mọi phòng ban, kèm nhân viên active nếu có**, hãy chuyển điều kiện sang ON:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

Lúc này phòng 20 và 40 đều còn, với cột nhân viên NULL. Sự khác biệt không phải mẹo cú pháp; nó phản ánh hai yêu cầu nghiệp vụ khác nhau:

- `WHERE e.active_flag = 'Y'`: chỉ trả các hàng kết quả có nhân viên active.
- `ON ... AND e.active_flag = 'Y'`: giữ mọi phòng ban, nhưng chỉ ghép nhân viên active.

### 6.2. Thêm OR e.employee_id IS NULL không thay thế được điều kiện trong ON

Một cách sửa thường thấy:

```sql
WHERE e.active_flag = 'Y'
   OR e.employee_id IS NULL
```

Cách này giữ phòng ban thật sự không có nhân viên nào, nhưng **không giữ phòng Kinh doanh (20)** trong dữ liệu lab: Chi khớp với phòng 20 ở ON, sau đó bị WHERE loại vì không active; không có hàng NULL-extended thứ hai được tạo ra. Do đó điều kiện OR không thể thay thế yêu cầu lọc bảng phải trong ON khi cần giữ cả những cha chỉ có con không đạt bộ lọc.

### 6.3. Điều kiện trên bảng được bảo toàn có thể đặt ở WHERE

Nếu muốn chỉ hiển thị phòng ban có ID từ 20 trở lên, đây là bộ lọc trên phía trái:

```sql
SELECT d.department_id, d.department_name, e.employee_id
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE d.department_id >= 20
ORDER BY d.department_id, e.employee_id;
```

Điều kiện này loại phòng 10 theo đúng yêu cầu và vẫn giữ phòng 40. Không có quy tắc “mọi điều kiện của LEFT JOIN đều phải nằm trong ON”; vị trí phụ thuộc điều kiện áp dụng cho **hàng nào** và yêu cầu giữ lại hàng nào.

## 7. Điều kiện ON trong FULL OUTER JOIN

Với FULL JOIN, cả hai phía đều được bảo toàn. Điều kiện ON quyết định hàng nào được ghép; hàng không tìm được đối tác vẫn xuất hiện riêng.

### 7.1. FULL JOIN hai tập dữ liệu có khóa khác nhau

Một ví dụ thực tế là đối chiếu kế hoạch và số thực tế theo phòng ban. Tạo hai bảng lab độc lập:

```sql
CREATE TABLE lab_budget_plan (
    department_id NUMBER PRIMARY KEY,
    planned_amount NUMBER(12, 2)
);

CREATE TABLE lab_budget_actual (
    department_id NUMBER PRIMARY KEY,
    actual_amount NUMBER(12, 2)
);

INSERT INTO lab_budget_plan VALUES (10, 10000);
INSERT INTO lab_budget_plan VALUES (20, 15000);
INSERT INTO lab_budget_plan VALUES (30, 8000);

INSERT INTO lab_budget_actual VALUES (10, 9500);
INSERT INTO lab_budget_actual VALUES (30, 9000);
INSERT INTO lab_budget_actual VALUES (40, 7000);

COMMIT;
```

FULL JOIN cho thấy cả mã chỉ có kế hoạch và mã chỉ có thực tế:

```sql
SELECT
    COALESCE(p.department_id, a.department_id) AS department_id,
    p.planned_amount,
    a.actual_amount,
    CASE
        WHEN p.department_id IS NULL THEN 'ACTUAL ONLY'
        WHEN a.department_id IS NULL THEN 'PLAN ONLY'
        ELSE 'BOTH'
    END AS match_state
FROM lab_budget_plan p
FULL OUTER JOIN lab_budget_actual a
  ON a.department_id = p.department_id
ORDER BY department_id;
```

Kết quả:

| DEPARTMENT_ID | PLANNED_AMOUNT | ACTUAL_AMOUNT | MATCH_STATE |
| ---: | ---: | ---: | --- |
| 10 | 10000 | 9500 | BOTH |
| 20 | 15000 | NULL | PLAN ONLY |
| 30 | 8000 | 9000 | BOTH |
| 40 | NULL | 7000 | ACTUAL ONLY |

Đây là một ứng dụng phù hợp của FULL OUTER JOIN: **đối chiếu hai nguồn độc lập** để phát hiện mã chỉ xuất hiện ở một nguồn.

### 7.2. Bộ lọc có thể làm mất hàng không khớp

Nếu viết:

```sql
SELECT
    COALESCE(p.department_id, a.department_id) AS department_id,
    p.planned_amount,
    a.actual_amount
FROM lab_budget_plan p
FULL OUTER JOIN lab_budget_actual a
  ON a.department_id = p.department_id
WHERE p.planned_amount > 0;
```

Hàng chỉ có thực tế (mã 40) có `P.PLANNED_AMOUNT NULL`, nên bị WHERE loại. Query không còn giữ tất cả hàng hai phía dù vẫn viết FULL JOIN.

Nếu mục tiêu là giữ tất cả mã nhưng chỉ ghép kế hoạch có giá trị dương, điều kiện cần được thiết kế trong ON hoặc lọc nguồn trước khi FULL JOIN:

```sql
SELECT
    COALESCE(p.department_id, a.department_id) AS department_id,
    p.planned_amount,
    a.actual_amount
FROM (
    SELECT department_id, planned_amount
    FROM lab_budget_plan
    WHERE planned_amount > 0
) p
FULL OUTER JOIN lab_budget_actual a
  ON a.department_id = p.department_id
ORDER BY department_id;
```

Ở đây nguồn kế hoạch được lọc trước khi nối; mọi hàng thực tế vẫn được giữ. Nếu muốn giữ cả hàng kế hoạch có amount NULL nhưng không cho chúng khớp, hãy mô tả rõ điều kiện trong ON và kiểm tra kết quả mong muốn. Vị trí filter luôn phải bám theo ý nghĩa dữ liệu.

## 8. Tìm hàng không có đối tác

Outer join thường được dùng để tìm các hàng không có quan hệ ở phía còn lại, còn gọi là **anti-join pattern**.

### 8.1. Phòng ban không có nhân viên

```sql
SELECT
    d.department_id,
    d.department_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
```

Kết quả là phòng Pháp chế (40). Điều kiện kiểm tra `E.EMPLOYEE_ID IS NULL` dùng primary key phía phải, vốn không NULL trên một hàng nhân viên thật. Do đó NULL cho biết không có hàng nhân viên khớp.

### 8.2. Nhân viên chưa có phòng ban hợp lệ

```sql
SELECT
    e.employee_id,
    e.full_name
FROM lab_employees e
LEFT JOIN lab_departments d
  ON d.department_id = e.department_id
WHERE d.department_id IS NULL
ORDER BY e.employee_id;
```

Với dữ liệu lab, kết quả có Dũng. Điều kiện kiểm tra khóa chính `D.DEPARTMENT_ID` của bảng phòng ban; nếu không có phòng khớp, khóa này NULL trong kết quả outer join.

### 8.3. NOT EXISTS thường diễn đạt ý định rõ hơn

Hai truy vấn sau thường tương đương về mục tiêu tìm phòng ban không có nhân viên:

```sql
-- LEFT JOIN + kiểm tra khóa phía phải.
SELECT d.department_id, d.department_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE e.employee_id IS NULL;

-- NOT EXISTS.
SELECT d.department_id, d.department_name
FROM lab_departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_employees e
    WHERE e.department_id = d.department_id
);
```

`NOT EXISTS` diễn đạt trực tiếp “không có hàng con phù hợp” và tránh đưa các cột NULL-extended vào tập kết quả. Oracle Optimizer có thể biến đổi các mẫu này thành anti-join tùy query và thống kê. Không có quy tắc rằng một dạng luôn nhanh hơn; hãy đo trên dữ liệu thật.

### 8.4. Không kiểm tra cột phía phải có thể NULL trong dữ liệu thật

Nếu bảng con có cột nullable như `E.SALARY`, điều kiện:

```sql
WHERE e.salary IS NULL
```

không phân biệt được:

- Không có nhân viên khớp (hàng NULL-extended).
- Có nhân viên thật nhưng chưa ghi nhận salary.

Hãy kiểm tra một cột phía phải **được bảo đảm NOT NULL**, thường là primary key:

```sql
WHERE e.employee_id IS NULL
```

Đây là một nguyên tắc quan trọng khi dùng outer join để tìm dữ liệu thiếu.

## 9. Nối nhiều bảng và nguy cơ nhân bản hàng

Outer join vẫn tuân theo cardinality của quan hệ. Nếu một phòng ban có ba nhân viên, `LEFT JOIN` phòng ban với nhân viên sẽ tạo ba hàng cho phòng đó. Đây không phải lỗi; mỗi hàng biểu diễn một cặp phòng ban/nhân viên.

Vấn đề xuất hiện khi nối thêm nhiều bảng con độc lập.

Giả sử một nhân viên có hai số điện thoại và ba chứng chỉ. Khi nối cả hai bảng con theo `EMPLOYEE_ID`, kết quả có:

```text
1 EMPLOYEE
   |
   +--- 2 PHONE rows
   |
   +--- 3 CERTIFICATE rows

JOIN cả hai bảng con:
   2 x 3 = 6 rows
```

Nếu sau đó `COUNT(phone_id)` hoặc `SUM(phone_fee)` được tính trên tập sáu hàng, mỗi phone bị lặp ba lần. Cách xử lý là aggregate từng nguồn con về một hàng trên mỗi employee trước khi nối, hoặc chỉ nối bảng con thực sự cần chi tiết.

Ví dụ mẫu:

```sql
WITH phone_counts AS (
    SELECT employee_id, COUNT(*) AS phone_count
    FROM lab_employee_phones
    GROUP BY employee_id
),
certificate_counts AS (
    SELECT employee_id, COUNT(*) AS certificate_count
    FROM lab_employee_certificates
    GROUP BY employee_id
)
SELECT
    e.employee_id,
    e.full_name,
    NVL(p.phone_count, 0) AS phone_count,
    NVL(c.certificate_count, 0) AS certificate_count
FROM lab_employees e
LEFT JOIN phone_counts p
  ON p.employee_id = e.employee_id
LEFT JOIN certificate_counts c
  ON c.employee_id = e.employee_id
ORDER BY e.employee_id;
```

Mỗi CTE có tối đa một hàng trên mỗi employee, nên phép nối cuối không nhân số lượng phone với số lượng certificate. `NVL(...,0)` phù hợp ở đây vì số lượng hàng con không tồn tại có nghĩa là 0; nếu đang tổng hợp giá trị nghiệp vụ có thể NULL mang ý nghĩa “chưa biết”, không nên áp dụng cùng quy tắc thay thế.

## 10. USING, ON và NATURAL JOIN

### 10.1. USING khi hai bảng có cùng tên cột nối

Nếu hai bảng đều có `DEPARTMENT_ID`, có thể viết:

```sql
SELECT
    department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
USING (department_id);
```

`USING` ngắn gọn khi nối bằng một hoặc nhiều cột cùng tên. Cột nối được xem như cột chung trong select list; không viết `D.DEPARTMENT_ID` hoặc `E.DEPARTMENT_ID` để tham chiếu cột đó trong cùng ngữ cảnh `USING`. Với `ON`, bạn có thể tham chiếu từng phía riêng biệt.

Với FULL OUTER JOIN, nếu cần thể hiện rõ giá trị khóa từ cả hai phía, `COALESCE(d.department_id, e.department_id)` trong cú pháp `ON` thường dễ đọc và dễ kiểm soát hơn.

### 10.2. NATURAL JOIN cần thận trọng

`NATURAL JOIN` tự nối theo tất cả cột cùng tên giữa hai bảng:

```sql
SELECT *
FROM lab_departments
NATURAL LEFT JOIN lab_employees;
```

Ví dụ lab chỉ có một cột cùng tên là `DEPARTMENT_ID`, nhưng schema thực tế có thể thêm cột trùng tên trong tương lai. Khi đó ý nghĩa NATURAL JOIN có thể thay đổi mà câu SQL không đổi. Trong ứng dụng cần kiểm soát quan hệ rõ ràng, ưu tiên `JOIN ... ON ...`.

## 11. Oracle legacy outer join operator (+)

Các hệ thống Oracle cũ có thể gặp cú pháp:

```sql
SELECT d.department_id, d.department_name, e.employee_id
FROM lab_departments d, lab_employees e
WHERE d.department_id = e.department_id(+);
```

`(+)` là cú pháp outer join cũ của Oracle; dấu được đặt ở phía bảng có thể thiếu hàng để giữ hàng của phía còn lại. Trong ví dụ trên, nó tương đương LEFT OUTER JOIN từ departments sang employees.

Với code mới, nên dùng ANSI JOIN:

```sql
SELECT d.department_id, d.department_name, e.employee_id
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id;
```

Cú pháp `(+)` có nhiều hạn chế và quy tắc đặc biệt, nhất là khi có nhiều điều kiện nối, nhiều bảng hoặc outer join phức tạp. Không trộn cú pháp `(+)` với cú pháp ANSI JOIN trong cùng query block. Khi bảo trì SQL legacy, cần đọc đúng các điều kiện `(+)` và kiểm tra tương đương trước khi chuyển đổi; không chỉ xóa dấu cộng mà không xem lại logic.

## 12. FULL OUTER JOIN và UNION của hai LEFT JOIN

Trong các phiên bản Oracle hiện đại, `FULL OUTER JOIN` là cách trực tiếp để giữ tất cả hàng hai phía. Trong một số tình huống legacy hoặc khi cần kiểm soát riêng từng tập, có thể mô phỏng bằng hai LEFT JOIN và `UNION ALL`, nhưng phải loại phần giao nhau ở nhánh thứ hai.

Ví dụ mô phỏng full join hai bảng ngân sách:

```sql
-- Các cặp khớp và hàng chỉ có trong PLAN.
SELECT
    p.department_id,
    p.planned_amount,
    a.actual_amount
FROM lab_budget_plan p
LEFT JOIN lab_budget_actual a
  ON a.department_id = p.department_id

UNION ALL

-- Các hàng chỉ có trong ACTUAL.
SELECT
    a.department_id,
    p.planned_amount,
    a.actual_amount
FROM lab_budget_actual a
LEFT JOIN lab_budget_plan p
  ON p.department_id = a.department_id
WHERE p.department_id IS NULL;
```

Vì `DEPARTMENT_ID` là primary key và không NULL trong cả hai bảng, `P.DEPARTMENT_ID IS NULL` ở nhánh thứ hai xác định hàng actual không có plan. `UNION ALL` giữ nguyên hàng; không cần chi phí loại trùng của `UNION`.

Đây chỉ là cách mô phỏng. Nếu khóa nối nullable hoặc không duy nhất, phải thiết kế phép kiểm tra unmatched theo khóa không NULL và xử lý cardinality cẩn thận. Không nên tự thay FULL JOIN bằng UNION hai LEFT JOIN khi chưa chứng minh hai nhánh bao phủ đúng toàn bộ cặp khớp và hàng không khớp.

## 13. Thứ tự logic và execution plan

Để hiểu kết quả outer join, có thể dùng mô hình logic:

1. Lấy hàng từ các nguồn trong FROM.
2. Xác định cặp hàng khớp theo điều kiện ON.
3. Với LEFT/RIGHT/FULL JOIN, bổ sung hàng NULL-extended cho phía được bảo toàn nhưng không có đối tác.
4. Áp dụng WHERE lên kết quả query block.
5. Thực hiện GROUP BY/HAVING, SELECT, ORDER BY và row limiting theo ngữ nghĩa SQL tương ứng.

Đây là **mô hình suy luận**, không phải thứ tự vật lý bắt buộc. Oracle Optimizer có thể đổi thứ tự truy cập, chọn nested loops/hash join/merge join và đẩy predicate khi biến đổi vẫn giữ nguyên ngữ nghĩa.

Có thể xem kế hoạch dự kiến trong lab:

```sql
EXPLAIN PLAN FOR
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` cho kế hoạch dự kiến. Khi phân tích SQL chạy thật, cần xem cursor plan và runtime statistics phù hợp quyền, thay vì kết luận hiệu năng chỉ từ số dòng SQL hoặc một kế hoạch ước lượng.

## 14. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| LEFT JOIN nhưng phòng ban rỗng biến mất | Điều kiện phía phải đặt trong WHERE | Đặt điều kiện lọc hàng được ghép trong ON |
| LEFT JOIN vẫn mất phòng chỉ có nhân viên inactive | ON khớp nhân viên inactive, WHERE loại chúng sau đó | Lọc active trong ON để tạo hàng NULL-extended khi không có nhân viên active |
| COUNT(*) bằng 1 ở phòng không nhân viên | Đếm hàng NULL-extended | Đếm khóa chính phía nhân viên bằng COUNT(e.employee_id) |
| Dùng WHERE e.salary IS NULL để tìm phòng không nhân viên | Nhân viên thật cũng có thể salary NULL | Kiểm tra cột khóa NOT NULL phía phải |
| RIGHT JOIN làm mất hàng ở bảng cần giữ | Đặt bảng ở sai phía hoặc đảo JOIN không đổi LEFT/RIGHT | Xác định phía được bảo toàn trước khi viết |
| FULL JOIN không ghép hai khóa NULL | NULL = NULL là UNKNOWN | Dùng khóa liên kết có ý nghĩa; chỉ xử lý NULL match khi nghiệp vụ quy định rõ |
| FULL JOIN trả hai hàng có khóa NULL | Một hàng NULL ở mỗi nguồn không tự khớp | Kiểm tra từng nguồn; không mặc định hai NULL là cùng thực thể |
| FULL JOIN rồi WHERE lọc một phía làm mất unmatched rows | WHERE loại các hàng có cột phía đó NULL | Lọc nguồn trước hoặc đặt điều kiện match trong ON theo yêu cầu |
| Khóa cha lặp sau join | Quan hệ 1-nhiều | Xác định grain; aggregate hoặc EXISTS nếu không cần chi tiết con |
| SUM bị tăng sau khi nối hai bảng con | Join tạo tích số hàng con độc lập | Aggregate từng nguồn con trước khi join |
| DISTINCT làm query “hết trùng” nhưng tổng vẫn sai | DISTINCT che biểu hiện, không sửa cardinality | Điều tra join key và grain trước |
| NOT EXISTS/anti-join không trả kết quả mong đợi | Điều kiện tương quan sai hoặc dùng nhầm khóa nullable | Kiểm tra điều kiện tương quan và khóa |
| NATURAL JOIN đổi kết quả sau khi thêm cột | Tự nối theo mọi tên cột chung | Dùng ON tường minh |
| Chuyển (+) sang ANSI JOIN cho kết quả khác | Đặt sai vị trí điều kiện hoặc mất quy tắc outer join cũ | Chuyển từng query block và đối chiếu kết quả |

## 15. Bài tập thực hành

Sử dụng `LAB_DEPARTMENTS` và `LAB_EMPLOYEES` trong mục 2. Hãy dự đoán kết quả trước khi chạy SQL.

### Bài 1 — LEFT JOIN

Viết query trả tất cả phòng ban và nhân viên tương ứng, kể cả phòng không có nhân viên. Xác định phòng nào có các cột `EMPLOYEE_ID` và `FULL_NAME` là NULL.

### Bài 2 — RIGHT JOIN

Viết query giữ tất cả nhân viên, kể cả người chưa được gán phòng. Sau đó viết lại query bằng cách đổi thứ tự hai bảng và dùng LEFT JOIN. So sánh tập kết quả.

### Bài 3 — FULL OUTER JOIN

Viết query giữ tất cả phòng ban và tất cả nhân viên. Giải thích vì sao phòng 40 và nhân viên Dũng đều xuất hiện trong các hàng riêng.

### Bài 4 — ON so với WHERE

Viết hai câu LEFT JOIN:

1. `ACTIVE_FLAG = 'Y'` trong ON.
2. `ACTIVE_FLAG = 'Y'` trong WHERE.

So sánh phòng 20 và phòng 40. Giải thích vì sao điều kiện OR `EMPLOYEE_ID IS NULL` không giữ được phòng 20 trong trường hợp chỉ có nhân viên inactive.

### Bài 5 — Đếm nhân viên

Thêm `COUNT(*)` và `COUNT(e.employee_id)` vào báo cáo phòng ban. Xác định giá trị cho phòng 40 và giải thích.

### Bài 6 — Tìm phòng ban không có nhân viên

Viết hai phiên bản: LEFT JOIN + `WHERE e.employee_id IS NULL`, và `NOT EXISTS`. Xác nhận cả hai tìm phòng Pháp chế.

### Bài 7 — Đối chiếu kế hoạch và thực tế

Tạo hai bảng ngân sách ở mục 7.1, chạy FULL OUTER JOIN và phân loại:

- Có cả kế hoạch và thực tế.
- Chỉ có kế hoạch.
- Chỉ có thực tế.

Sau đó thêm một điều kiện WHERE trên `PLANNED_AMOUNT` và quan sát hàng actual-only biến mất.

### Bài 8 — Cardinality

Giả sử một nhân viên có hai điện thoại và ba chứng chỉ. Viết join cả hai bảng con, dự đoán số hàng, rồi aggregate từng bảng con trước khi join để trả một hàng mỗi nhân viên.

### Bài 9 — Thiết kế truy vấn đối soát

Một hệ thống có hai nguồn dữ liệu khách hàng, mỗi nguồn có `CUSTOMER_CODE`, `FULL_NAME`, `EMAIL`. Hãy viết FULL OUTER JOIN theo CUSTOMER_CODE để tìm:

- Mã có ở cả hai nguồn.
- Mã chỉ có ở nguồn A.
- Mã chỉ có ở nguồn B.
- Mã có ở cả hai nhưng email khác nhau.

Giải thích cách xử lý nếu CUSTOMER_CODE có NULL hoặc không duy nhất; không mặc định một FULL JOIN sẽ tự sửa dữ liệu khóa bị thiếu.

## 16. Dọn dữ liệu thực hành

Chỉ chạy các lệnh sau trong schema lab do bạn tạo và khi đã hoàn tất bài tập:

```sql
DROP TABLE lab_employees PURGE;
DROP TABLE lab_departments PURGE;
DROP TABLE lab_budget_plan PURGE;
DROP TABLE lab_budget_actual PURGE;
```

Nếu không tạo bảng ngân sách, bỏ qua hai lệnh DROP tương ứng. Xóa bảng con trước bảng cha vì có foreign key. `PURGE` bỏ qua recycle bin; không dùng với dữ liệu cần khôi phục hoặc bảng không thuộc quyền sở hữu của bạn.

## Tổng kết

`LEFT OUTER JOIN` giữ mọi hàng bên trái, `RIGHT OUTER JOIN` giữ mọi hàng bên phải, còn `FULL OUTER JOIN` giữ cả hai phía. Khi không có đối tác phù hợp, Oracle bổ sung NULL vào các cột của phía không khớp. Hàng NULL-extended là hàng của **kết quả JOIN**, không phải bản ghi thật được chèn vào bảng.

Điều kiện `ON` xác định hàng nào được ghép; `WHERE` lọc kết quả sau phép nối logic. Với outer join, chuyển điều kiện giữa hai vị trí có thể làm mất các hàng cần bảo toàn. Khi đếm hàng con, đếm khóa chính phía con thay vì `COUNT(*)`. Khi kết quả bị nhân bản, xác định grain và cardinality của từng quan hệ; aggregate từng nguồn con trước khi nối nếu mục tiêu là một hàng trên mỗi thực thể cha.

Outer join đặc biệt hữu ích cho báo cáo cần giữ thực thể chưa có quan hệ, đối soát hai nguồn, tìm dữ liệu thiếu và kiểm tra chất lượng dữ liệu. Chọn đúng hướng JOIN và viết điều kiện tường minh sẽ giúp kết quả phản ánh chính xác yêu cầu nghiệp vụ.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — Joins (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html) — cú pháp inner/outer join, ON, USING và các quy tắc liên quan.
- [Oracle Database SQL Language Reference — SELECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — cấu trúc query block, FROM, WHERE và các mệnh đề SELECT.
- [Oracle Database SQL Language Reference — EXISTS Condition (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html) — điều kiện tồn tại và mẫu truy vấn tương quan.
- [Oracle Database SQL Language Reference — Nulls (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Nulls.html) — logic NULL trong điều kiện nối và lọc.
- [Oracle Database SQL Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — join methods, optimizer và execution plan.

Đối với hệ thống Oracle release khác 19c, hãy đối chiếu tài liệu đúng phiên bản về cú pháp JOIN và giới hạn của cú pháp outer join legacy `(+)` trước khi chuyển đổi SQL sản xuất.

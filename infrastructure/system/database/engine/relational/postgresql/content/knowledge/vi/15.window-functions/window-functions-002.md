# Phân biệt tổng hợp theo nhóm với hàm cửa sổ trong PostgreSQL

## 1. Cùng tính tổng, nhưng hai câu hỏi dữ liệu khác nhau

Giả sử có một bảng nhân viên, mỗi nhân viên thuộc một phòng ban và có mức lương. Ta muốn biết:

- **Mỗi phòng ban có bao nhiêu nhân viên, tổng lương bao nhiêu?**
- **Mỗi nhân viên có lương bao nhiêu, đồng thời tổng lương phòng ban của người đó là bao nhiêu?**

Câu hỏi đầu cần **tổng hợp theo nhóm** với `GROUP BY`: nhiều hàng nhân viên được gom thành **một hàng cho mỗi phòng ban**.

Câu hỏi thứ hai cần **hàm cửa sổ** (*window function*) với `OVER (...)`: vẫn giữ **từng hàng nhân viên**, nhưng tính thêm số liệu của nhóm nhân viên liên quan.

Hai phép tính có thể cùng dùng hàm `SUM`, nhưng kết quả có **độ chi tiết hàng (grain)** khác nhau:

```text
DỮ LIỆU GỐC                GROUP BY dept_id
1. An   - phòng 10         phòng 10 | 3 người | 51 triệu
2. Bình - phòng 10         phòng 20 | 2 người | 50 triệu
3. Chi  - phòng 10         phòng 30 | 3 người | 40 triệu
4. Dũng - phòng 20
5. Hà   - phòng 20         8 hàng -> 3 hàng
6. Lan  - phòng 30
7. Minh - phòng 30
8. Phúc - phòng 30

                           WINDOW OVER (PARTITION BY dept_id)
                           An   | phòng 10 | 51 triệu
                           Bình | phòng 10 | 51 triệu
                           Chi  | phòng 10 | 51 triệu
                           Dũng | phòng 20 | 50 triệu
                           Hà   | phòng 20 | 50 triệu
                           Lan  | phòng 30 | 40 triệu
                           Minh | phòng 30 | 40 triệu
                           Phúc | phòng 30 | 40 triệu

                           8 hàng -> vẫn 8 hàng
```

**Quy tắc cốt lõi:** `GROUP BY` thay đổi mức chi tiết kết quả theo nhóm; hàm cửa sổ tính toán trên một tập hàng liên quan **mà không tự gom các hàng đó thành một hàng**.

Đó là khác biệt về ngữ nghĩa, không chỉ khác biệt về cú pháp.

### Bạn sẽ học được gì?

Sau bài học, bạn sẽ:

1. Phân biệt aggregate thông thường với aggregate được gọi dưới dạng window function.
2. Hiểu `GROUP BY`, `HAVING`, `OVER`, `PARTITION BY`, `ORDER BY` và window frame.
3. Giải thích vì sao `SUM(salary)` và `SUM(salary) OVER (PARTITION BY ...)` có số hàng đầu ra khác nhau.
4. Dùng hàm cửa sổ để tính tổng nhóm, tỷ trọng, trung bình nhóm, xếp hạng, tổng lũy kế và chênh lệch với hàng trước.
5. Kết hợp `GROUP BY` và window trong cùng truy vấn khi cần báo cáo “nhóm theo ngày, rồi cộng dồn các ngày”.
6. Tránh bẫy `ROWS` so với `RANGE` khi có giá trị `ORDER BY` trùng nhau.
7. Lọc các hàng dựa trên kết quả window bằng CTE/subquery đúng thứ tự.
8. Nhận diện `COUNT(*)`, `NULL`, `DISTINCT`, join một-nhiều và các bẫy tổng hợp.
9. Đọc kế hoạch PostgreSQL với `EXPLAIN` khi dữ liệu lớn.
10. Lựa chọn cách viết theo **yêu cầu số hàng kết quả**, thay vì chọn hàm dựa trên thói quen.

## 2. Dựng bộ dữ liệu thực hành PostgreSQL

Bài sử dụng hai tập dữ liệu độc lập: **nhân viên–phòng ban** và **giao dịch theo ngày**. SQL giả định bạn thực hành trên database lab và role có quyền tạo schema/bảng. Không áp dụng các câu tạo/chèn dữ liệu mẫu trực tiếp trên production.

### 2.1. Bảng phòng ban

```sql
CREATE SCHEMA IF NOT EXISTS window188;

CREATE TABLE window188.departments (
    department_id integer PRIMARY KEY,
    department_name text NOT NULL UNIQUE
);

INSERT INTO window188.departments(department_id, department_name)
VALUES
    (10, 'Kinh doanh'),
    (20, 'Kỹ thuật'),
    (30, 'Chăm sóc khách hàng'),
    (40, 'Pháp chế');
```

Phòng 40 chưa có nhân viên. Điều này sẽ giúp phân biệt báo cáo nhóm chỉ dựa trên bảng nhân viên với báo cáo nhóm muốn giữ **cả phòng trống**.

### 2.2. Bảng nhân viên

Để phép tính dễ kiểm chứng, lưu lương dưới đơn vị **triệu đồng** trong cột số nguyên `salary_million`. Đây là dữ liệu học tập, không phải hướng dẫn dùng integer triệu đồng để hạch toán mọi hệ thống tiền lương thật.

```sql
CREATE TABLE window188.employees (
    employee_id integer PRIMARY KEY,
    employee_name text NOT NULL,
    department_id integer NOT NULL
        REFERENCES window188.departments(department_id),
    salary_million integer NOT NULL
        CHECK (salary_million > 0),
    hired_on date NOT NULL
);

INSERT INTO window188.employees(
    employee_id,
    employee_name,
    department_id,
    salary_million,
    hired_on
)
VALUES
    (101, 'An',   10, 15, DATE '2026-01-10'),
    (102, 'Bình', 10, 18, DATE '2026-02-15'),
    (103, 'Chi',  10, 18, DATE '2026-03-20'),
    (104, 'Dũng', 20, 24, DATE '2026-01-05'),
    (105, 'Hà',   20, 26, DATE '2026-03-01'),
    (106, 'Lan',  30, 12, DATE '2026-02-01'),
    (107, 'Minh', 30, 12, DATE '2026-03-01'),
    (108, 'Phúc', 30, 16, DATE '2026-04-01');
```

Kiểm tra bảng gốc:

```sql
SELECT employee_id, employee_name,
       department_id, salary_million, hired_on
FROM window188.employees
ORDER BY department_id, employee_id;
```

| employee_id | employee_name | department_id | salary_million |
|---:|---|---:|---:|
| 101 | An | 10 | 15 |
| 102 | Bình | 10 | 18 |
| 103 | Chi | 10 | 18 |
| 104 | Dũng | 20 | 24 |
| 105 | Hà | 20 | 26 |
| 106 | Lan | 30 | 12 |
| 107 | Minh | 30 | 12 |
| 108 | Phúc | 30 | 16 |

Tổng lương đơn vị triệu: `15 + 18 + 18 + 24 + 26 + 12 + 12 + 16 = 141`.

### 2.3. Dữ liệu giao dịch theo ngày

Ta tạo thêm bảng để học **tổng lũy kế và window frame**:

```sql
CREATE TABLE window188.sales (
    sale_id integer PRIMARY KEY,
    sold_on date NOT NULL,
    amount integer NOT NULL CHECK (amount >= 0)
);

INSERT INTO window188.sales(sale_id, sold_on, amount)
VALUES
    (1001, DATE '2026-01-05', 100),
    (1002, DATE '2026-01-05',  40),
    (1003, DATE '2026-01-06',  20),
    (1004, DATE '2026-01-08',  60),
    (1005, DATE '2026-02-01',  90),
    (1006, DATE '2026-02-05',  10);
```

Số lượng: 6 giao dịch, tổng tiền 320 đơn vị. Ngày **05/01 có hai giao dịch**, chủ ý tạo các hàng cùng giá trị `sold_on` để quan sát khác biệt giữa window frame mặc định và `ROWS` tường minh.

**Chú ý:** Nếu chạy lại các câu `INSERT` này trên bảng lab đã có bản ghi cùng khóa chính, PostgreSQL sẽ báo lỗi trùng khóa. Hãy dùng schema lab mới hoặc reset fixture bằng quy trình được cho phép; đừng tự xóa dữ liệu không rõ chủ sở hữu.

## 3. Tổng hợp theo nhóm: GROUP BY làm thay đổi mức chi tiết

### 3.1. Một dòng kết quả cho mỗi phòng

```sql
SELECT
    department_id,
    COUNT(*) AS employee_count,
    SUM(salary_million) AS total_salary_million,
    ROUND(AVG(salary_million), 2) AS avg_salary_million
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

Kết quả:

| department_id | employee_count | total_salary_million | avg_salary_million |
|---:|---:|---:|---:|
| 10 | 3 | 51 | 17.00 |
| 20 | 2 | 50 | 25.00 |
| 30 | 3 | 40 | 13.33 |

Từ **8 hàng nhân viên**, kết quả còn **3 hàng phòng ban có nhân viên**.

Khi nhóm theo `department_id`:

- Tất cả nhân viên phòng 10 được gom thành một nhóm.
- Tất cả nhân viên phòng 20 thành nhóm thứ hai.
- Tất cả nhân viên phòng 30 thành nhóm thứ ba.
- Phòng 40 không xuất hiện, vì không có hàng nào trong bảng `employees` mang `department_id = 40`.

### 3.2. GROUP BY không bảo toàn từng nhân viên

Xét câu này:

```sql
-- Sai ngữ nghĩa GROUP BY trong PostgreSQL:
SELECT
    department_id,
    employee_name,
    SUM(salary_million)
FROM window188.employees
GROUP BY department_id;
```

Vì một nhóm phòng 10 có nhiều tên nhân viên, PostgreSQL không thể tùy tiện lấy `employee_name` nào để đại diện cho nhóm. Với schema này, câu query sẽ lỗi do cột không được nhóm hoặc tổng hợp.

Quy tắc cơ bản: trong một truy vấn có `GROUP BY`, các cột ở `SELECT` thường cần là:

- Biểu thức dùng để nhóm.
- Kết quả aggregate như `SUM`, `COUNT`, `AVG`, `MIN`, `MAX`.
- Hoặc biểu thức được PostgreSQL chấp nhận theo quy tắc **phụ thuộc hàm** phù hợp.

Không nên dựa vào “tên nhân viên đầu tiên trong nhóm” khi SQL chưa định nghĩa cách chọn.

### 3.3. GROUP BY trên nhiều cột tạo nhóm nhỏ hơn

```sql
SELECT
    department_id,
    salary_million,
    COUNT(*) AS employees_with_salary
FROM window188.employees
GROUP BY department_id, salary_million
ORDER BY department_id, salary_million;
```

Kết quả:

| department_id | salary_million | employees_with_salary |
|---:|---:|---:|
| 10 | 15 | 1 |
| 10 | 18 | 2 |
| 20 | 24 | 1 |
| 20 | 26 | 1 |
| 30 | 12 | 2 |
| 30 | 16 | 1 |

Vẫn là GROUP BY, nhưng **grain** giờ là “một hàng cho mỗi cặp phòng ban–mức lương”, không phải một hàng mỗi phòng ban.

**Mỗi cột thêm vào GROUP BY có thể làm tăng số nhóm**, vì định nghĩa khóa nhóm thay đổi.

## 4. Aggregate không GROUP BY: cả bảng thành một nhóm

Nếu chỉ muốn tổng lương của **toàn bộ bảng**:

```sql
SELECT
    COUNT(*) AS employees,
    SUM(salary_million) AS company_salary_million,
    ROUND(AVG(salary_million), 2) AS avg_salary_million
FROM window188.employees;
```

Kết quả:

| employees | company_salary_million | avg_salary_million |
|---:|---:|---:|
| 8 | 141 | 17.63 |

Không có `GROUP BY` nhưng có aggregate, vì thế toàn bộ tập hàng sau `FROM/WHERE` được xem như **một nhóm tổng hợp** và truy vấn trả một hàng.

Nếu bảng rỗng:

- `COUNT(*)` trả 0.
- `SUM` và `AVG` thường trả NULL, không tự trả 0.

Sự khác biệt này cũng sẽ xuất hiện với window aggregate khi partition không chứa giá trị phù hợp.

## 5. Hàm cửa sổ: OVER(PARTITION BY ...) giữ chi tiết từng hàng

Bây giờ cùng tính tổng và đếm theo phòng, nhưng **không gom từng nhân viên**:

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS department_employee_count,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_salary_million
FROM window188.employees
ORDER BY department_id, employee_id;
```

Kết quả:

| employee_id | employee_name | department_id | salary_million | department_employee_count | department_salary_million |
|---:|---|---:|---:|---:|---:|
| 101 | An | 10 | 15 | 3 | 51 |
| 102 | Bình | 10 | 18 | 3 | 51 |
| 103 | Chi | 10 | 18 | 3 | 51 |
| 104 | Dũng | 20 | 24 | 2 | 50 |
| 105 | Hà | 20 | 26 | 2 | 50 |
| 106 | Lan | 30 | 12 | 3 | 40 |
| 107 | Minh | 30 | 12 | 3 | 40 |
| 108 | Phúc | 30 | 16 | 3 | 40 |

Kết quả vẫn có **8 hàng**, một hàng cho từng nhân viên.

### 5.1. Ý nghĩa của PARTITION BY

`PARTITION BY department_id` chia tập hàng đầu vào của window thành các **phân vùng**:

```text
Partition 10:
  An    (15)
  Bình  (18)
  Chi   (18)
  SUM = 51, COUNT = 3

Partition 20:
  Dũng  (24)
  Hà    (26)
  SUM = 50, COUNT = 2

Partition 30:
  Lan   (12)
  Minh  (12)
  Phúc  (16)
  SUM = 40, COUNT = 3
```

Mỗi nhân viên nhận thêm kết quả của **partition chứa nhân viên đó**. Khác với GROUP BY, PostgreSQL không loại bỏ các hàng An, Bình, Chi để chỉ giữ một hàng phòng 10.

### 5.2. PARTITION BY không phải GROUP BY

Hai từ “nhóm” và “phân vùng” dễ khiến người học nhầm:

- `GROUP BY department_id` gom **nhiều hàng** thành **một hàng mỗi nhóm**.
- `OVER(PARTITION BY department_id)` cho phép **mỗi hàng** nhìn thấy các hàng liên quan trong cùng partition.

Cùng một khóa `department_id` nhưng mục đích khác nhau.

### 5.3. Nếu bỏ PARTITION BY thì sao?

```sql
SELECT
    employee_id,
    employee_name,
    salary_million,
    SUM(salary_million) OVER () AS company_total
FROM window188.employees
ORDER BY employee_id;
```

Mỗi nhân viên sẽ có `company_total = 141`.

`OVER ()` tạo một window trên **toàn bộ tập hàng đầu vào** sau các bước lọc/nhóm có liên quan của truy vấn, không chỉ tự động theo phòng ban.

## 6. So sánh trực diện: SUM thường và SUM OVER

Xét bốn câu SQL:

**A — Một tổng cho toàn bảng:**

```sql
SELECT SUM(salary_million) AS total
FROM window188.employees;
```

Trả **1 hàng**, giá trị 141.

**B — Một tổng cho mỗi phòng ban:**

```sql
SELECT department_id,
       SUM(salary_million) AS department_total
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

Trả **3 hàng**, các tổng 51, 50, 40.

**C — Tổng phòng ban gắn vào mỗi nhân viên:**

```sql
SELECT employee_id, department_id,
       SUM(salary_million) OVER (
           PARTITION BY department_id
       ) AS department_total
FROM window188.employees
ORDER BY employee_id;
```

Trả **8 hàng**, mỗi nhân viên có tổng phòng ban tương ứng.

**D — Tổng công ty gắn vào mỗi nhân viên:**

```sql
SELECT employee_id,
       SUM(salary_million) OVER () AS company_total
FROM window188.employees
ORDER BY employee_id;
```

Trả **8 hàng**, mỗi hàng có tổng 141.

Bảng tóm tắt:

| Biểu thức/cấu trúc | Phạm vi tính | Số hàng ví dụ | Mức chi tiết |
|---|---|---:|---|
| `SUM(salary)` không GROUP BY | Toàn bộ bảng sau lọc | 1 | Tổng công ty |
| `SUM(salary)` + GROUP BY dept | Mỗi phòng ban | 3 | Một hàng/phòng |
| `SUM(salary) OVER(PARTITION BY dept)` | Mỗi phòng ban | 8 | Một hàng/nhân viên |
| `SUM(salary) OVER()` | Toàn bộ tập hàng window | 8 | Một hàng/nhân viên |

**Điểm quyết định:** cần giữ hàng nhân viên để tính toán tiếp hay chỉ cần bảng tổng hợp? Hãy trả lời câu này trước khi chọn cú pháp.

## 7. GROUP BY và OVER có thể cùng tồn tại

Không có quy tắc “đã GROUP BY thì không được dùng window”. Trên thực tế, hai kỹ thuật thường được **kết hợp theo hai tầng**:

1. `GROUP BY` tạo một hàng cho mỗi phòng ban.
2. Hàm cửa sổ tính toán **trên các hàng phòng ban đã tổng hợp**.

Ví dụ tính tỷ trọng quỹ lương từng phòng trên tổng công ty:

```sql
WITH department_totals AS (
    SELECT
        department_id,
        SUM(salary_million) AS department_salary
    FROM window188.employees
    GROUP BY department_id
)
SELECT
    department_id,
    department_salary,
    SUM(department_salary) OVER () AS company_salary,
    ROUND(
        100.0 * department_salary
        / SUM(department_salary) OVER (),
        2
    ) AS percentage_of_company
FROM department_totals
ORDER BY department_id;
```

Kết quả:

| department_id | department_salary | company_salary | percentage_of_company |
|---:|---:|---:|---:|
| 10 | 51 | 141 | 36.17 |
| 20 | 50 | 141 | 35.46 |
| 30 | 40 | 141 | 28.37 |

Hàm `SUM(department_salary) OVER ()` chạy trên **ba hàng** của CTE `department_totals`. Nó không tính trên tám hàng nhân viên nữa.

### 7.1. Viết gọn trong cùng một SELECT

PostgreSQL cho phép dùng kết quả tổng hợp làm đầu vào cho hàm cửa sổ:

```sql
SELECT
    department_id,
    SUM(salary_million) AS department_salary,
    SUM(SUM(salary_million)) OVER () AS company_salary,
    ROUND(
        100.0 * SUM(salary_million)
        / SUM(SUM(salary_million)) OVER (),
        2
    ) AS percentage_of_company
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

Cách đọc biểu thức:

```sql
SUM( SUM(salary_million) ) OVER ()
     ^^^^^^^^^^^^^^^^^^^
     Tổng lương từng phòng, hình thành bởi GROUP BY

^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Window SUM tính trên các hàng phòng đã tổng hợp
```

**Không có nghĩa** PostgreSQL chạy cùng một aggregate hai lần trên cùng một tập hàng. Đây là hai cấp tính toán: aggregate bên trong tạo giá trị nhóm, window aggregate bên ngoài xử lý tập nhóm.

Với câu truy vấn phức tạp, CTE hai tầng thường dễ bảo trì hơn cách lồng biểu thức trực tiếp.

### 7.2. Điều cần tránh: tính lại trên những hàng đã nhân bản

Nếu bạn lấy `department_salary` lặp lại trên **từng nhân viên** bằng window, rồi cộng tất cả các giá trị đó:

```text
Phòng 10: 51 xuất hiện 3 lần -> cộng lại thành 153
Phòng 20: 50 xuất hiện 2 lần -> cộng lại thành 100
Phòng 30: 40 xuất hiện 3 lần -> cộng lại thành 120
Tổng các ô department_salary trên 8 hàng = 373
```

Con số **373** không phải tổng lương 141; đó là tổng của các tổng nhóm đã bị lặp theo số nhân viên.

**Quy tắc:** không `SUM` lại các chỉ số window lặp trên nhiều hàng nếu bạn muốn tổng thực tế; hãy tổng hợp ở **grain đúng** trước khi tính tỷ trọng hoặc số liệu cấp cao hơn.

## 8. HAVING lọc nhóm, WHERE lọc hàng, lọc window cần tầng truy vấn khác

Ba tình huống dễ bị trộn lẫn:

- `WHERE` lọc hàng đầu vào **trước GROUP BY/window**.
- `HAVING` lọc **nhóm đã tổng hợp**.
- Muốn lọc theo giá trị **window function**, thông thường cần subquery hoặc CTE rồi lọc ở query ngoài.

### 8.1. WHERE: chỉ xét nhân viên có lương từ 18 triệu

```sql
SELECT
    department_id,
    COUNT(*) AS employees_at_least_18,
    SUM(salary_million) AS salary_total
FROM window188.employees
WHERE salary_million >= 18
GROUP BY department_id
ORDER BY department_id;
```

Kết quả:

| department_id | employees_at_least_18 | salary_total |
|---:|---:|---:|
| 10 | 2 | 36 |
| 20 | 2 | 50 |

Phòng 30 không xuất hiện vì không có nhân viên nào lương từ 18.

### 8.2. HAVING: chỉ giữ phòng có tổng lương trên 45 triệu

```sql
SELECT
    department_id,
    SUM(salary_million) AS department_salary
FROM window188.employees
GROUP BY department_id
HAVING SUM(salary_million) > 45
ORDER BY department_id;
```

Kết quả:

| department_id | department_salary |
|---:|---:|
| 10 | 51 |
| 20 | 50 |

`HAVING` không “lọc từng nhân viên lương trên 45”, mà lọc **nhóm** có tổng lương trên 45.

### 8.3. Lọc theo trung bình phòng ban của từng nhân viên

Yêu cầu:

> “Lấy các nhân viên có lương **cao hơn mức trung bình của chính phòng họ**.”

Tính window trước:

```sql
WITH employee_with_avg AS (
    SELECT
        employee_id,
        employee_name,
        department_id,
        salary_million,
        AVG(salary_million) OVER (
            PARTITION BY department_id
        ) AS department_average
    FROM window188.employees
)
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million,
    ROUND(department_average, 2) AS department_average
FROM employee_with_avg
WHERE salary_million > department_average
ORDER BY department_id, employee_id;
```

Kết quả:

| employee_id | employee_name | department_id | salary_million | department_average |
|---:|---|---:|---:|---:|
| 102 | Bình | 10 | 18 | 17.00 |
| 103 | Chi | 10 | 18 | 17.00 |
| 105 | Hà | 20 | 26 | 25.00 |
| 108 | Phúc | 30 | 16 | 13.33 |

**Vì sao cần CTE?** Trong PostgreSQL, window functions không được sử dụng trực tiếp trong các mệnh đề `WHERE`, `GROUP BY` hoặc `HAVING` của **cùng cấp SELECT**. Chúng được tính ở giai đoạn logic sau những mệnh đề này.

### 8.4. Câu sai thường gặp

```sql
-- Không hợp lệ trong PostgreSQL:
SELECT employee_id, salary_million
FROM window188.employees
WHERE salary_million > AVG(salary_million)
    OVER (PARTITION BY department_id);
```

Một câu như vậy không được sửa bằng cách “đổi OVER sang GROUP BY” nếu vẫn cần giữ từng nhân viên. Hãy đưa phép tính window vào subquery/CTE như ví dụ trước.

## 9. Window chạy trên tập hàng đã được lọc

Điểm này rất quan trọng khi so sánh các chỉ số.

### 9.1. Lọc trước rồi tính trung bình

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    AVG(salary_million) OVER (
        PARTITION BY department_id
    ) AS avg_salary_of_filtered_rows
FROM window188.employees
WHERE salary_million >= 18
ORDER BY department_id, employee_id;
```

Vì `WHERE` chạy trước window ở cùng cấp truy vấn:

- Phòng 10 chỉ còn hai nhân viên 18 → trung bình 18, **không phải 17**.
- Phòng 20 còn hai nhân viên 24, 26 → trung bình 25.
- Phòng 30 không còn hàng, nên không có partition phòng 30 trong kết quả.

### 9.2. Tính trung bình đầy đủ rồi mới lọc nhân viên

Nếu muốn:

> “Chỉ hiện nhân viên có lương từ 18 trở lên, nhưng mức trung bình phòng ban phải tính trên **toàn bộ nhân viên**.”

dùng CTE:

```sql
WITH enriched AS (
    SELECT
        employee_id,
        department_id,
        salary_million,
        AVG(salary_million) OVER (
            PARTITION BY department_id
        ) AS full_department_avg
    FROM window188.employees
)
SELECT *
FROM enriched
WHERE salary_million >= 18
ORDER BY department_id, employee_id;
```

Bình và Chi vẫn có `full_department_avg = 17` thay vì 18.

**Bài học:** cùng một phép `AVG(...) OVER(PARTITION BY ...)` có thể cho giá trị khác nhau nếu tập hàng đầu vào bị lọc khác nhau. Luôn xác định **thời điểm và phạm vi lọc**.

## 10. PARTITION BY không phải ORDER BY

Hai mệnh đề bên trong `OVER` có vai trò riêng:

- `PARTITION BY` quyết định **những hàng nào cùng phân vùng**.
- `ORDER BY` quyết định **thứ tự logic của các hàng trong từng phân vùng**; đồng thời ảnh hưởng window frame mặc định của nhiều hàm aggregate.

Ví dụ:

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS whole_department_total,
    SUM(salary_million) OVER (
        PARTITION BY department_id
        ORDER BY employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_department_total
FROM window188.employees
ORDER BY department_id, employee_id;
```

Kết quả:

| employee_id | dept | salary | whole_department_total | running_department_total |
|---:|---:|---:|---:|---:|
| 101 | 10 | 15 | 51 | 15 |
| 102 | 10 | 18 | 51 | 33 |
| 103 | 10 | 18 | 51 | 51 |
| 104 | 20 | 24 | 50 | 24 |
| 105 | 20 | 26 | 50 | 50 |
| 106 | 30 | 12 | 40 | 12 |
| 107 | 30 | 12 | 40 | 24 |
| 108 | 30 | 16 | 40 | 40 |

Nếu chỉ muốn **tổng toàn partition lặp trên từng hàng**, không cần thêm `ORDER BY` vào `OVER`. Nếu thêm `ORDER BY`, phải suy nghĩ kỹ về **frame**, vì nhiều câu truy vấn sẽ chuyển sang tính lũy kế.

### 10.1. ORDER BY bên trong OVER không sắp xếp đầu ra cuối

```sql
SUM(salary_million) OVER (
    PARTITION BY department_id
    ORDER BY employee_id
)
```

dùng thứ tự để **tính toán window**. Nó không bảo đảm thứ tự các hàng khi gửi về client.

Muốn kết quả ổn định, dùng thêm `ORDER BY` ở cấp SELECT:

```sql
ORDER BY department_id, employee_id
```

Hai `ORDER BY` này có chức năng khác nhau.

## 11. Window frame: toàn partition hay chỉ các hàng trước?

Một window có thể được xem qua ba lớp:

```text
Tập hàng còn lại sau FROM/WHERE/GROUP BY/HAVING
             |
             +-- PARTITION BY: chia thành các phân vùng
                      |
                      +-- ORDER BY: xác định thứ tự trong phân vùng
                               |
                               +-- FRAME: phần nào của phân vùng
                                          được dùng cho phép tính hiện tại
```

Với các hàm aggregate kiểu `SUM`, `AVG`, `COUNT`, `MIN`, `MAX` được dùng ở dạng window, **frame** quyết định những hàng được tính cho hàng hiện tại trong những câu có thứ tự.

### 11.1. Không có ORDER BY trong OVER

```sql
SUM(amount) OVER ()
```

tính trên toàn bộ tập hàng của window.

```sql
SUM(amount) OVER (PARTITION BY customer_id)
```

tính trên toàn bộ partition của từng khách hàng.

### 11.2. Có ORDER BY và không viết frame

```sql
SUM(amount) OVER (ORDER BY sold_on)
```

thường dùng **frame mặc định**:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING
          AND CURRENT ROW
```

Điểm quan trọng: với `RANGE` mặc định, những hàng **cùng giá trị sắp xếp** (*peers*) cũng thuộc phần frame đến hàng hiện tại. Vì thế “tổng lũy kế” có thể **nhảy theo nhóm ngày**, không tăng từng giao dịch.

### 11.3. ROWS để cộng từng hàng theo thứ tự đã định

```sql
SUM(amount) OVER (
    ORDER BY sold_on, sale_id
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND CURRENT ROW
)
```

`ROWS` xác định khung theo **vị trí hàng**. `sale_id` làm khóa phụ để thứ tự các giao dịch có cùng ngày trở nên xác định.

Đây là mẫu thông dụng cho **running total theo từng giao dịch**.

## 12. Thực hành frame mặc định và các hàng trùng ngày

Dữ liệu bảng `sales` có hai giao dịch ngày 05/01:

```text
sale_id | sold_on     | amount
--------+-------------+-------
1001    | 2026-01-05  | 100
1002    | 2026-01-05  |  40
1003    | 2026-01-06  |  20
1004    | 2026-01-08  |  60
1005    | 2026-02-01  |  90
1006    | 2026-02-05  |  10
```

### 12.1. Dùng frame mặc định RANGE theo ngày

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        ORDER BY sold_on
    ) AS running_default
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | sold_on | amount | running_default |
|---:|---|---:|---:|
| 1001 | 2026-01-05 | 100 | 140 |
| 1002 | 2026-01-05 | 40 | 140 |
| 1003 | 2026-01-06 | 20 | 160 |
| 1004 | 2026-01-08 | 60 | 220 |
| 1005 | 2026-02-01 | 90 | 310 |
| 1006 | 2026-02-05 | 10 | 320 |

Hai hàng ngày 05/01 là peers theo `ORDER BY sold_on`. Frame mặc định bao gồm **cả hai** khi tính cho mỗi hàng trong nhóm peer, nên cả hai có kết quả 140.

### 12.2. Dùng ROWS cùng khóa thứ tự duy nhất

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_per_transaction
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | sold_on | amount | running_per_transaction |
|---:|---|---:|---:|
| 1001 | 2026-01-05 | 100 | 100 |
| 1002 | 2026-01-05 | 40 | 140 |
| 1003 | 2026-01-06 | 20 | 160 |
| 1004 | 2026-01-08 | 60 | 220 |
| 1005 | 2026-02-01 | 90 | 310 |
| 1006 | 2026-02-05 | 10 | 320 |

Giờ tổng tăng **sau từng giao dịch**, theo thứ tự được xác định bằng `sold_on, sale_id`.

### 12.3. ROWS nhưng ORDER BY không có khóa phụ

Nếu viết:

```sql
SUM(amount) OVER (
    ORDER BY sold_on
    ROWS BETWEEN UNBOUNDED PRECEDING
             AND CURRENT ROW
)
```

thì khi có hai giao dịch trùng `sold_on`, thứ tự tương đối giữa chúng **chưa được quyết định đầy đủ**. Hai hàng có thể nhận các tổng lũy kế theo thứ tự xử lý khác dự kiến.

Để kết quả xác định và dễ kiểm thử, thêm khóa có thứ tự ổn định, ví dụ `sale_id`.

### 12.4. Muốn tổng cả partition dù có ORDER BY

```sql
SELECT
    sale_id,
    amount,
    SUM(amount) OVER (
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS all_sales_total
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Mỗi hàng có `all_sales_total = 320`.

Nếu chỉ cần tổng toàn bảng lặp lại, viết `SUM(amount) OVER()` đơn giản hơn.

## 13. ROWS và RANGE không chỉ là hai cách viết giống nhau

| Đặc điểm | ROWS | RANGE |
|---|---|---|
| Cách xác định frame | Theo vị trí hàng trong thứ tự window | Theo giá trị sắp xếp/quan hệ peers và quy tắc range |
| Khi nhiều hàng có cùng ORDER BY | Có thể đi từng hàng một | Peers có thể cùng thuộc frame |
| Running total từng giao dịch | Thường dùng với khóa phụ xác định thứ tự | Có thể cộng cả nhóm cùng ngày cùng lúc |
| Dễ dự đoán khi ORDER BY có duplicate | Cần khóa phụ | Cần hiểu peers |
| Ví dụ | `ROWS UNBOUNDED PRECEDING` | `RANGE UNBOUNDED PRECEDING` |

PostgreSQL còn có chế độ `GROUPS` và các lựa chọn `EXCLUDE` cho frame trong những phiên bản hỗ trợ, nhưng để nắm cơ bản, điều cần nhất là hiểu sự khác nhau giữa **đơn vị hàng** và **nhóm giá trị sắp xếp bằng nhau**.

### 13.1. Frame theo ba giao dịch gần nhất

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        ORDER BY sold_on, sale_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS recent_three_transactions
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Kết quả dự kiến:

| sale_id | amount | recent_three_transactions |
|---:|---:|---:|
| 1001 | 100 | 100 |
| 1002 | 40 | 140 |
| 1003 | 20 | 160 |
| 1004 | 60 | 120 |
| 1005 | 90 | 170 |
| 1006 | 10 | 160 |

Ví dụ ở hàng 1004: tính 40 + 20 + 60 = 120, không tính giao dịch 1001 đã nằm ngoài frame ba hàng gần nhất.

### 13.2. Ba giao dịch khác ba ngày gần nhất

`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` là **ba hàng**, không phải ba ngày. Nếu một ngày có nhiều giao dịch hoặc có ngày không giao dịch, ba hàng có thể trải qua khoảng thời gian dài hoặc ngắn.

Muốn “ba ngày lịch gần nhất”, cần thiết kế theo **ngày** hoặc dùng frame thời gian thích hợp. Có thể tổng hợp theo ngày trước, sau đó áp dụng window trên các hàng ngày; nếu cần tính cả ngày không có dữ liệu, tạo calendar đầy đủ rồi LEFT JOIN số liệu.

## 14. Các hàm cửa sổ không phải aggregate thường

Không phải tất cả window functions đều là các hàm aggregate thông thường thêm `OVER`.

Các hàm tiêu biểu:

| Hàm | Mục đích |
|---|---|
| `ROW_NUMBER()` | Đánh số từng hàng trong partition |
| `RANK()` | Xếp hạng; các hàng đồng hạng tạo khoảng nhảy |
| `DENSE_RANK()` | Xếp hạng; không bỏ số hạng tiếp theo |
| `LAG(expression)` | Lấy giá trị từ hàng trước theo thứ tự window |
| `LEAD(expression)` | Lấy giá trị từ hàng sau |
| `FIRST_VALUE(expression)` | Lấy giá trị đầu tiên trong frame |
| `LAST_VALUE(expression)` | Lấy giá trị cuối cùng trong frame |
| `NTH_VALUE(expression,n)` | Lấy giá trị thứ n trong frame nếu có |
| `NTILE(n)` | Phân các hàng thành các nhóm gần bằng nhau theo thứ tự |

Các hàm này cho kết quả **trên từng hàng**, theo partition, thứ tự và frame thích hợp. Chúng không phải là cách tạo **một hàng mỗi nhóm** như GROUP BY.

## 15. Xếp hạng nhân viên trong phòng ban

Phòng 10 có lương: 18, 18, 15. Phòng 30 có lương: 16, 12, 12. Đây là dữ liệu tốt để so sánh cách xử lý đồng hạng.

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary_million DESC, employee_id
    ) AS row_num,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary_million DESC
    ) AS salary_rank,
    DENSE_RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary_million DESC
    ) AS dense_salary_rank
FROM window188.employees
ORDER BY department_id, salary_million DESC, employee_id;
```

Kết quả:

| employee_id | dept | salary | row_num | salary_rank | dense_salary_rank |
|---:|---:|---:|---:|---:|---:|
| 102 | 10 | 18 | 1 | 1 | 1 |
| 103 | 10 | 18 | 2 | 1 | 1 |
| 101 | 10 | 15 | 3 | 3 | 2 |
| 105 | 20 | 26 | 1 | 1 | 1 |
| 104 | 20 | 24 | 2 | 2 | 2 |
| 108 | 30 | 16 | 1 | 1 | 1 |
| 106 | 30 | 12 | 2 | 2 | 2 |
| 107 | 30 | 12 | 3 | 2 | 2 |

### 15.1. Vì sao ROW_NUMBER khác RANK?

- `ROW_NUMBER` cho **mỗi hàng một số thứ tự khác nhau**. Thêm `employee_id` vào `ORDER BY` giúp phá hòa một cách xác định.
- `RANK` cho hai người cùng lương 18 **đồng hạng 1**, người tiếp theo nhận hạng 3.
- `DENSE_RANK` cũng cho hai người lương 18 đồng hạng 1, nhưng người tiếp theo nhận hạng 2.

**Cẩn thận:** nếu viết `RANK() OVER(ORDER BY salary_million DESC, employee_id)`, hai người cùng lương nhưng khác ID sẽ **không còn đồng hạng**, vì tuple `(salary, employee_id)` đã khác nhau.

### 15.2. GROUP BY có thể thay các hàm này không?

Không trực tiếp. `GROUP BY department_id` chỉ trả một hàng mỗi phòng và không giữ danh sách từng nhân viên để gắn rank.

Muốn xếp hạng **nhân viên**, hãy giữ grain nhân viên và dùng window; muốn xếp hạng **phòng ban theo tổng lương**, hãy GROUP BY tạo các hàng phòng trước rồi RANK trên tập nhóm.

## 16. Top 1 hoặc top N theo từng nhóm

### 16.1. Chọn một nhân viên lương cao nhất mỗi phòng

```sql
WITH ranked AS (
    SELECT
        employee_id,
        employee_name,
        department_id,
        salary_million,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary_million DESC, employee_id
        ) AS rn
    FROM window188.employees
)
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million
FROM ranked
WHERE rn = 1
ORDER BY department_id;
```

Kết quả:

| employee_id | employee_name | dept | salary |
|---:|---|---:|---:|
| 102 | Bình | 10 | 18 |
| 105 | Hà | 20 | 26 |
| 108 | Phúc | 30 | 16 |

Ở phòng 10, Bình và Chi cùng lương 18. `ROW_NUMBER` với ID phụ chọn **một người xác định**, không tự trả cả hai.

### 16.2. Nếu muốn giữ mọi người đồng hạng cao nhất

Dùng `RANK()`:

```sql
WITH ranked AS (
    SELECT
        employee_id,
        employee_name,
        department_id,
        salary_million,
        RANK() OVER (
            PARTITION BY department_id
            ORDER BY salary_million DESC
        ) AS salary_rank
    FROM window188.employees
)
SELECT *
FROM ranked
WHERE salary_rank = 1
ORDER BY department_id, employee_id;
```

Kết quả gồm **Bình và Chi** ở phòng 10, **Hà** ở phòng 20 và **Phúc** ở phòng 30.

### 16.3. GROUP BY MAX có thay được không?

```sql
SELECT department_id,
       MAX(salary_million) AS max_salary
FROM window188.employees
GROUP BY department_id;
```

Truy vấn này đúng nếu chỉ cần **mức lương cao nhất mỗi phòng**; nó **không trả tên/ID nhân viên** tương ứng.

Muốn lấy hàng nhân viên, dùng window ranking, join kết quả MAX trở lại bảng gốc, `DISTINCT ON` (PostgreSQL) hoặc `LATERAL` tùy yêu cầu xử lý đồng hạng. Lựa chọn phải dựa trên cần một người hay tất cả người cùng mức lương tối đa.

## 17. LAG và LEAD: nhìn hàng trước/sau mà không tự JOIN

Xét các giao dịch được sắp theo ngày rồi theo sale_id.

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    LAG(amount) OVER (
        ORDER BY sold_on, sale_id
    ) AS previous_amount,
    LEAD(amount) OVER (
        ORDER BY sold_on, sale_id
    ) AS next_amount
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Kết quả:

| sale_id | amount | previous_amount | next_amount |
|---:|---:|---:|---:|
| 1001 | 100 | NULL | 40 |
| 1002 | 40 | 100 | 20 |
| 1003 | 20 | 40 | 60 |
| 1004 | 60 | 20 | 90 |
| 1005 | 90 | 60 | 10 |
| 1006 | 10 | 90 | NULL |

`LAG` và `LEAD` giữ mỗi giao dịch là **một hàng**, không gộp như GROUP BY. Có thể dùng để tính độ chênh:

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    amount - LAG(amount) OVER (
        ORDER BY sold_on, sale_id
    ) AS diff_from_previous_sale
FROM window188.sales
ORDER BY sold_on, sale_id;
```

Ở giao dịch đầu tiên, `LAG` không có hàng trước nên trả NULL; phép trừ tương ứng cũng NULL. Muốn chọn giá trị thay thế, có thể dùng `COALESCE` theo hợp đồng nghiệp vụ, nhưng không tự coi “không có giao dịch trước” là giá trị 0 trong mọi báo cáo.

### 17.1. Hàng trước không đồng nghĩa ngày trước

Vì ngày 05/01 có hai giao dịch, `LAG` của giao dịch thứ hai là giao dịch **cùng ngày**. Nếu yêu cầu so sánh **doanh thu ngày hôm nay với ngày trước**, hãy tổng hợp dữ liệu **một hàng mỗi ngày** trước, rồi dùng `LAG` trên tập ngày; nếu cần so sánh với hôm qua kể cả ngày không có giao dịch, cần calendar đầy đủ.

## 18. Tổng hợp theo ngày rồi tính tổng lũy kế

Một nhu cầu rất phổ biến:

> “Mỗi ngày hiển thị **tổng doanh số ngày** và **doanh số tích lũy từ đầu kỳ**.”

Nếu chỉ GROUP BY, ta có tổng từng ngày nhưng không có cột tích lũy. Nếu chỉ dùng window trên giao dịch, kết quả lại có **một hàng mỗi giao dịch**, không đúng grain một hàng/ngày.

Giải pháp: **GROUP BY trước, window sau**.

### 18.1. Dùng CTE hai tầng

```sql
WITH daily_sales AS (
    SELECT
        sold_on,
        SUM(amount) AS daily_amount
    FROM window188.sales
    GROUP BY sold_on
)
SELECT
    sold_on,
    daily_amount,
    SUM(daily_amount) OVER (
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS cumulative_amount
FROM daily_sales
ORDER BY sold_on;
```

Kết quả:

| sold_on | daily_amount | cumulative_amount |
|---|---:|---:|
| 2026-01-05 | 140 | 140 |
| 2026-01-06 | 20 | 160 |
| 2026-01-08 | 60 | 220 |
| 2026-02-01 | 90 | 310 |
| 2026-02-05 | 10 | 320 |

Bộ dữ liệu đầu vào có **6 giao dịch** nhưng GROUP BY tạo **5 ngày có giao dịch**. Window sau đó tính tích lũy trên **năm hàng ngày**.

### 18.2. Viết lồng hai phép SUM trong một SELECT

```sql
SELECT
    sold_on,
    SUM(amount) AS daily_amount,
    SUM(SUM(amount)) OVER (
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS cumulative_amount
FROM window188.sales
GROUP BY sold_on
ORDER BY sold_on;
```

Kết quả giống CTE ở trên.

Ý nghĩa:

- `SUM(amount)` bên trong tính tổng của **từng nhóm ngày**.
- `SUM(... ) OVER (...)` bên ngoài chạy trên **những hàng ngày đã GROUP BY**.

Đây là mẫu chuẩn cho báo cáo **tổng hợp theo khoảng thời gian rồi cộng dồn**.

### 18.3. Ngày không có giao dịch vẫn thiếu

Bảng kết quả trên không có ngày 07/01, vì bảng sales **không chứa giao dịch** vào ngày đó. Window function **không tự sinh những ngày vắng mặt**, và GROUP BY cũng không tự tạo nhóm rỗng.

Nếu biểu đồ phải hiển thị từng ngày liên tục, cần tạo calendar với `generate_series`, `LEFT JOIN` số liệu thực và dùng `COALESCE` trước khi tính running total.

## 19. Kết hợp generate_series, GROUP BY và window để lấp ngày trống

Ví dụ từ 05/01 đến 08/01/2026:

```sql
WITH calendar AS (
    SELECT DATE '2026-01-05' + n AS day
    FROM generate_series(0, 3) AS g(n)
),
daily_sales AS (
    SELECT
        c.day,
        COALESCE(SUM(s.amount), 0) AS daily_amount
    FROM calendar AS c
    LEFT JOIN window188.sales AS s
        ON s.sold_on = c.day
    GROUP BY c.day
)
SELECT
    day,
    daily_amount,
    SUM(daily_amount) OVER (
        ORDER BY day
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS cumulative_amount
FROM daily_sales
ORDER BY day;
```

Kết quả:

| day | daily_amount | cumulative_amount |
|---|---:|---:|
| 2026-01-05 | 140 | 140 |
| 2026-01-06 | 20 | 160 |
| 2026-01-07 | 0 | 160 |
| 2026-01-08 | 60 | 220 |

Có ba lớp rõ ràng:

1. **Calendar** tạo đủ ngày.
2. **GROUP BY** tổng hợp doanh số mỗi ngày và giữ ngày trống nhờ LEFT JOIN.
3. **Window SUM** cộng dồn các hàng ngày theo thứ tự.

### 19.1. Cẩn trọng vị trí điều kiện trên bảng giao dịch

Nếu muốn chỉ tính giao dịch `amount >= 50` nhưng vẫn giữ mọi ngày, nên đưa điều kiện vào `ON`:

```sql
LEFT JOIN window188.sales AS s
    ON s.sold_on = c.day
   AND s.amount >= 50
```

Nếu đưa `s.amount >= 50` vào `WHERE` sau LEFT JOIN, những ngày không có giao dịch đạt ngưỡng có thể bị **xóa khỏi tập ngày** trước GROUP BY/window. Điều đó làm sai biểu đồ yêu cầu hiển thị đủ ngày.

## 20. Tính tỷ lệ từng nhân viên so với phòng ban và toàn công ty

Aggregate window cho phép gắn các mẫu số khác nhau lên **cùng hàng nhân viên**:

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_salary,
    SUM(salary_million) OVER () AS company_salary,
    ROUND(
        100.0 * salary_million
        / SUM(salary_million) OVER (
            PARTITION BY department_id
        ),
        2
    ) AS pct_of_department,
    ROUND(
        100.0 * salary_million
        / SUM(salary_million) OVER (),
        2
    ) AS pct_of_company
FROM window188.employees
ORDER BY department_id, employee_id;
```

Ví dụ:

- An lương 15 trong tổng phòng 51 → `15 / 51 × 100 ≈ 29.41%`.
- An lương 15 trong tổng công ty 141 → `15 / 141 × 100 ≈ 10.64%`.
- Hà lương 26 trong tổng phòng 50 → `52.00%`.

### 20.1. Vì sao không thể thay trực tiếp bằng GROUP BY?

Nếu chỉ GROUP BY department_id, bạn không còn từng hàng nhân viên để tính tỷ trọng của riêng An, Bình hay Chi. Có thể GROUP BY để tính tổng phòng rồi **JOIN** tổng đó trở lại bảng nhân viên, nhưng window thường ngắn gọn hơn.

### 20.2. Phòng ban có tổng bằng 0

Dữ liệu lab bảo đảm `salary_million > 0` nên mẫu số trong partition luôn dương. Trong dữ liệu thật, nếu một tổng nhóm có thể bằng 0, phải tránh chia cho 0:

```sql
salary_amount
/ NULLIF(
    SUM(salary_amount) OVER (PARTITION BY department_id),
    0
)
```

`NULLIF(total,0)` trả NULL khi tổng bằng 0; phép chia cho NULL trả NULL thay vì exception. Cách hiển thị hoặc giải thích NULL cần theo nghiệp vụ.

## 21. COUNT(*) và COUNT(column) trong nhóm và window

### 21.1. Không có NULL trong khóa nhân viên

Trên bảng lab `employees`:

```sql
SELECT
    department_id,
    COUNT(*) AS all_rows,
    COUNT(employee_id) AS known_employee_ids
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

Hai số đếm bằng nhau vì `employee_id` là khóa chính NOT NULL.

### 21.2. LEFT JOIN để giữ phòng ban không có nhân viên

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS rows_after_left_join,
    COUNT(e.employee_id) AS actual_employees,
    COALESCE(SUM(e.salary_million), 0) AS salary_total
FROM window188.departments AS d
LEFT JOIN window188.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Kết quả:

| department_id | rows_after_left_join | actual_employees | salary_total |
|---:|---:|---:|---:|
| 10 | 3 | 3 | 51 |
| 20 | 2 | 2 | 50 |
| 30 | 3 | 3 | 40 |
| 40 | 1 | 0 | 0 |

Phòng 40 vẫn có **một hàng null-extended** sau LEFT JOIN, nên `COUNT(*) = 1`, nhưng `COUNT(e.employee_id) = 0`.

Đây là lỗi đếm thường gặp, bất kể sau đó dùng GROUP BY hay window.

### 21.3. Window trên tập sau LEFT JOIN

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    COUNT(*) OVER (
        PARTITION BY d.department_id
    ) AS rows_in_join_partition,
    COUNT(e.employee_id) OVER (
        PARTITION BY d.department_id
    ) AS employees_in_partition
FROM window188.departments AS d
LEFT JOIN window188.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

Với phòng 40, vẫn có một hàng kết quả:

```text
department_id       = 40
employee_id         = NULL
rows_in_join_partition = 1
employees_in_partition = 0
```

**Window không tự sửa ngữ nghĩa COUNT(*) của hàng null-extended.** Nó chỉ tính theo tập hàng mà truy vấn đã hình thành.

## 22. FILTER với aggregate thường và window aggregate

PostgreSQL hỗ trợ cú pháp `FILTER (WHERE ...)` để chọn những hàng đóng góp vào **một aggregate cụ thể**.

### 22.1. GROUP BY và FILTER

Đếm nhân viên lương ít nhất 18 triệu theo phòng:

```sql
SELECT
    department_id,
    COUNT(*) AS total_employees,
    COUNT(*) FILTER (
        WHERE salary_million >= 18
    ) AS employees_from_18
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

Kết quả:

| department_id | total_employees | employees_from_18 |
|---:|---:|---:|
| 10 | 3 | 2 |
| 20 | 2 | 2 |
| 30 | 3 | 0 |

Vẫn **một hàng mỗi phòng**.

### 22.2. Window aggregate và FILTER

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    COUNT(*) FILTER (
        WHERE salary_million >= 18
    ) OVER (
        PARTITION BY department_id
    ) AS colleagues_from_18
FROM window188.employees
ORDER BY department_id, employee_id;
```

Kết quả vẫn có **8 hàng**; mỗi nhân viên nhận số lượng người lương từ 18 trở lên trong phòng:

- Phòng 10: 2.
- Phòng 20: 2.
- Phòng 30: 0.

### 22.3. FILTER không áp dụng như nhau với mọi hàm cửa sổ

`FILTER` là cú pháp cho **aggregate functions** (bao gồm khi gọi chúng làm window aggregate), không phải cách lọc tùy ý cho `ROW_NUMBER()`, `LAG()`, `RANK()` và mọi hàm window không phải aggregate.

Ví dụ này **không hợp lệ**:

```sql
-- Không hợp lệ:
SELECT ROW_NUMBER()
       FILTER (WHERE salary_million >= 18)
       OVER (PARTITION BY department_id)
FROM window188.employees;
```

Muốn đánh số **chỉ những nhân viên lương >= 18**, hãy lọc nguồn đầu vào **trước khi tính ROW_NUMBER**, hoặc tính thứ tự trên toàn bộ nguồn rồi lọc ngoài tùy yêu cầu.

## 23. FIRST_VALUE và LAST_VALUE: hiểu frame trước khi dùng

Một ứng dụng thường cần “mức lương lớn nhất/nhỏ nhất trong phòng” hoặc “giá trị đầu/ cuối theo một thứ tự”.

Với nhóm lương của phòng 10 được sắp tăng: 15, 18, 18.

### 23.1. FIRST_VALUE lấy phần tử đầu trong frame

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    FIRST_VALUE(salary_million) OVER (
        PARTITION BY department_id
        ORDER BY salary_million, employee_id
    ) AS minimum_salary_in_order
FROM window188.employees
ORDER BY department_id, salary_million, employee_id;
```

Với phòng 10, mọi nhân viên nhận giá trị đầu là **15**. Vì first row nằm trong frame tích lũy mặc định của những hàng kế tiếp, đây là cách viết thường cho kết quả kỳ vọng trong ví dụ.

### 23.2. LAST_VALUE dễ bị hiểu nhầm

Một câu như:

```sql
LAST_VALUE(salary_million) OVER (
    PARTITION BY department_id
    ORDER BY salary_million, employee_id
)
```

**không mặc nhiên lấy hàng cuối của toàn partition**. Với frame mặc định theo thứ tự, điểm cuối frame thường là **hàng hiện tại và các peers**, nên kết quả có thể là mức lương của hàng hiện tại.

Muốn lấy phần tử cuối của toàn partition, chỉ rõ frame:

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    LAST_VALUE(salary_million) OVER (
        PARTITION BY department_id
        ORDER BY salary_million, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS highest_salary_in_partition
FROM window188.employees
ORDER BY department_id, salary_million, employee_id;
```

Khi thứ tự là lương tăng dần, phần tử cuối của partition là mức lương cao nhất.

### 23.3. Nếu chỉ cần mức lương lớn nhất, MAX đơn giản hơn

```sql
MAX(salary_million) OVER (
    PARTITION BY department_id
)
```

Tính mức lương cao nhất của toàn partition mà không phải quan tâm frame `LAST_VALUE`.

Nếu cần **tên người lương cao nhất**, phải giải quyết trường hợp đồng hạng bằng ranking, `DISTINCT ON` hoặc phương pháp lấy hàng phù hợp.

## 24. DISTINCT không thay GROUP BY, và COUNT(DISTINCT) OVER có giới hạn

### 24.1. DISTINCT loại trùng hàng kết quả

```sql
SELECT DISTINCT department_id
FROM window188.employees
ORDER BY department_id;
```

Trả ba mã phòng: 10, 20, 30.

Đây không phải phép tổng hợp tổng lương/đếm nhân viên. Nó chỉ loại các bản sao của giá trị được chọn.

### 24.2. GROUP BY linh hoạt cho aggregate theo khóa

```sql
SELECT department_id,
       COUNT(*) AS employee_count
FROM window188.employees
GROUP BY department_id;
```

Trả một hàng mỗi nhóm và có số đếm.

### 24.3. PostgreSQL không hỗ trợ DISTINCT ngay trong window aggregate thông thường

Ví dụ sau không phải cách hợp lệ để đếm số phòng phân biệt trên mỗi hàng trong PostgreSQL:

```sql
-- Không hợp lệ với PostgreSQL:
SELECT
    employee_id,
    COUNT(DISTINCT department_id) OVER ()
FROM window188.employees;
```

PostgreSQL báo giới hạn về `DISTINCT` trong hàm aggregate được dùng như window function.

Cách làm là **tách bước xác định giá trị phân biệt** rồi tính window theo grain thích hợp:

```sql
WITH distinct_departments AS (
    SELECT DISTINCT department_id
    FROM window188.employees
)
SELECT
    department_id,
    COUNT(*) OVER () AS distinct_department_count
FROM distinct_departments
ORDER BY department_id;
```

Kết quả có ba hàng, và `distinct_department_count = 3` trên từng hàng.

Nếu yêu cầu chỉ một số đếm toàn bảng, đơn giản hơn:

```sql
SELECT COUNT(DISTINCT department_id) AS distinct_departments
FROM window188.employees;
```

**Nguyên tắc:** không cố dùng window khi aggregate thông thường giải quyết đúng và ngắn gọn hơn.

## 25. NULL: tổng hợp và cửa sổ có những quy tắc chung

Khi dùng các aggregate `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, cần nhớ:

- `COUNT(*)` đếm **hàng**.
- `COUNT(column)` chỉ đếm **giá trị không NULL** của cột.
- `SUM(column)` và `AVG(column)` bỏ qua các giá trị NULL.
- Với một tập không có giá trị đầu vào không NULL, `SUM`/`AVG` có thể trả NULL.
- `COALESCE` có thể thay NULL bằng giá trị trình bày phù hợp, nhưng NULL và 0 không luôn cùng ngữ nghĩa.

Ví dụ tức thời không cần tạo bảng:

```sql
WITH data(department_id, amount) AS (
    VALUES
        (1, 10),
        (1, NULL::integer),
        (1, 20),
        (2, NULL::integer)
)
SELECT
    department_id,
    COUNT(*) AS row_count,
    COUNT(amount) AS known_amount_count,
    SUM(amount) AS amount_sum
FROM data
GROUP BY department_id
ORDER BY department_id;
```

Kết quả:

| department_id | row_count | known_amount_count | amount_sum |
|---:|---:|---:|---:|
| 1 | 3 | 2 | 30 |
| 2 | 1 | 0 | NULL |

Khi dùng `OVER(PARTITION BY department_id)` với cùng tập dữ liệu, các kết quả aggregate tương tự sẽ **lặp trên từng hàng** tương ứng, thay vì gộp còn hai hàng.

### 25.1. PARTITION BY với khóa NULL

Trong các window, những hàng có giá trị `department_id NULL` sẽ cùng thuộc một partition theo khóa phân vùng tương ứng. Đây là cách phân chia dữ liệu để tính toán, không có nghĩa phép so sánh thông thường `NULL = NULL` trả TRUE.

Nếu để khóa phân vùng có thể NULL, hãy quyết định nhóm “chưa được gán” có cần tính chung hay phải được xử lý riêng.

### 25.2. Bài toán phần tử NULL trong ORDER BY

PostgreSQL hỗ trợ `NULLS FIRST`/`NULLS LAST` trong phần thứ tự window khi cần quy tắc rõ ràng:

```sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY hired_on NULLS LAST, employee_id
)
```

Trong schema lab `hired_on` NOT NULL, nhưng với dữ liệu thực tế cho phép NULL, nên xác định vị trí NULL để thứ tự và rank không bất ngờ.

## 26. Grain của JOIN: đừng nhân số liệu trước GROUP BY hoặc window

Giả sử một nhân viên có nhiều kỹ năng và ta join:

```text
departments -> employees -> employee_skills
```

Nếu mỗi nhân viên có ba kỹ năng, bảng kết quả sau join có thể chứa **ba hàng cho một nhân viên**. Khi đó:

```sql
SUM(e.salary_million)
```

sau join có thể cộng lương cùng nhân viên **ba lần**, dù dùng GROUP BY hay window.

Một số lỗi:

- `GROUP BY department_id` sau join thành tổng lương phòng **bị phóng đại**.
- `SUM(e.salary_million) OVER(PARTITION BY department_id)` cũng bị phóng đại, đồng thời lặp kết quả trên nhiều hàng kỹ năng.
- `COUNT(*)` đếm hàng sau join, không đếm nhân viên duy nhất.

### 26.1. Cách tránh

Nếu mục tiêu là lương theo **nhân viên**, hãy cố giữ một hàng/nhân viên trước khi tổng hợp/window.

Có thể:

- Tổng hợp kỹ năng về một hàng/nhân viên **trước khi join**.
- Dùng `EXISTS` nếu chỉ cần kiểm tra nhân viên có kỹ năng nào đó.
- Dùng `COUNT(DISTINCT employee_id)` trong aggregate theo nhóm khi đúng nhu cầu, nhưng đừng xem DISTINCT là biện pháp sửa mọi lỗi.
- Tách báo cáo thành nhiều CTE có grain rõ ràng, ví dụ employee_totals và skill_counts rồi nối theo khóa duy nhất.

### 26.2. Window không tự loại trùng

Mặc dù window không “gộp hàng”, điều đó **không bảo đảm đầu vào đang là một hàng mỗi thực thể**. Nó giữ grain của các hàng đã tồn tại ở giai đoạn tính window, kể cả những hàng bị nhân do JOIN.

## 27. Đặt tên WINDOW để tái sử dụng cấu hình

Khi có nhiều hàm dùng chung partition/order, PostgreSQL hỗ trợ mệnh đề `WINDOW`:

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    SUM(salary_million) OVER dept_window AS department_total,
    AVG(salary_million) OVER dept_window AS department_average,
    COUNT(*) OVER dept_window AS department_count
FROM window188.employees
WINDOW dept_window AS (
    PARTITION BY department_id
)
ORDER BY department_id, employee_id;
```

Điều này giảm lặp cú pháp `PARTITION BY department_id` nhiều lần.

### 27.1. Window có thứ tự riêng

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    ROW_NUMBER() OVER ordered_dept AS employee_sequence,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_total
FROM window188.employees
WINDOW ordered_dept AS (
    PARTITION BY department_id
    ORDER BY employee_id
)
ORDER BY department_id, employee_id;
```

Ở đây:

- `ordered_dept` xác định thứ tự để đánh số từng nhân viên.
- Tổng phòng dùng window **không có ORDER BY** để luôn là tổng toàn partition.

**Không lạm dụng một named window có ORDER BY** cho mọi aggregate nếu có hàm muốn tổng toàn nhóm và hàm muốn tổng lũy kế. Cùng PARTITION BY nhưng **frame khác nhau** sẽ cho ý nghĩa khác.

## 28. Thứ tự logic của truy vấn trong PostgreSQL

Để hiểu GROUP BY và window, nên có một sơ đồ logic của các giai đoạn SQL:

```text
FROM / JOIN
    |
WHERE
    |
GROUP BY
    |
Các aggregate theo nhóm
    |
HAVING
    |
Tính biểu thức window trên tập hàng còn lại
    |
SELECT / biểu thức đầu ra
    |
DISTINCT (nếu có)
    |
ORDER BY đầu ra
    |
LIMIT / OFFSET
```

Đây là **mô hình ngữ nghĩa**, không phải kế hoạch thực thi vật lý cứng. PostgreSQL optimizer có thể đẩy điều kiện, sắp xếp lại thao tác hoặc bỏ bước không cần thiết khi vẫn bảo toàn kết quả.

Một số hệ quả:

1. `WHERE` không được tham chiếu trực tiếp kết quả window ở **cùng cấp SELECT**.
2. `HAVING` lọc nhóm và có thể làm thay đổi số hàng mà window nhìn thấy.
3. Nếu có GROUP BY, window xử lý **những hàng đã tổng hợp**, không còn toàn bộ hàng chi tiết.
4. `ORDER BY` ngoài cùng quyết định thứ tự hiển thị; `ORDER BY` trong `OVER` quyết định tính toán window.
5. `LIMIT` thông thường giới hạn các hàng cuối, không thay đổi kết quả `SUM(...) OVER()` được tính trên toàn bộ tập window trước đó, trừ khi bạn đặt LIMIT trong một subquery **trước** window.

### 28.1. Ví dụ LIMIT không làm tổng công ty thành tổng ba người

```sql
SELECT
    employee_id,
    salary_million,
    SUM(salary_million) OVER () AS company_salary
FROM window188.employees
ORDER BY employee_id
LIMIT 3;
```

Chỉ trả **3 hàng** đầu, nhưng trên mỗi hàng vẫn có `company_salary = 141`, không phải 51.

Nếu muốn tổng của **ba người được chọn trước**, phải lấy ba người trong subquery rồi tính window ngoài:

```sql
WITH first_three AS (
    SELECT employee_id, salary_million
    FROM window188.employees
    ORDER BY employee_id
    LIMIT 3
)
SELECT
    employee_id,
    salary_million,
    SUM(salary_million) OVER () AS selected_three_total
FROM first_three
ORDER BY employee_id;
```

Giờ mỗi hàng có `selected_three_total = 51`.

## 29. So sánh GROUP BY với JOIN kết quả tổng hợp và window

Có hai mẫu tương đương về mục tiêu khi muốn **nhân viên + tổng lương phòng ban**.

### 29.1. GROUP BY rồi JOIN trở lại

```sql
WITH department_sums AS (
    SELECT
        department_id,
        SUM(salary_million) AS department_total
    FROM window188.employees
    GROUP BY department_id
)
SELECT
    e.employee_id,
    e.employee_name,
    e.department_id,
    e.salary_million,
    ds.department_total
FROM window188.employees AS e
JOIN department_sums AS ds
    ON ds.department_id = e.department_id
ORDER BY e.department_id, e.employee_id;
```

### 29.2. Dùng window

```sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary_million,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_total
FROM window188.employees
ORDER BY department_id, employee_id;
```

Cả hai trả **8 hàng**, với tổng lương phòng 51, 50, 40 gắn vào từng nhân viên.

### 29.3. Chọn cách nào?

| Tiêu chí | GROUP BY + JOIN lại | Window |
|---|---|---|
| Diễn đạt một tổng theo phòng gắn vào mỗi nhân viên | Được | Thường ngắn hơn |
| Cần bảng tổng hợp phòng để tái sử dụng ở nhiều nơi | Thuận tiện | Không tự sinh bảng tổng hợp |
| Cần nhiều chỉ số trong cùng partition | Có thể cần nhiều biểu thức tổng hợp | Nhiều OVER dùng chung partition |
| Chỉ cần một hàng mỗi phòng | GROUP BY trực tiếp | Window tạo dư hàng nếu không xử lý tiếp |
| Cần xử lý thứ hạng/hàng trước | Có thể phức tạp | Window tự nhiên hơn |
| Hiệu năng | Phụ thuộc cách optimizer thực hiện | Phụ thuộc partition, sort, frame và plan |

Không có quy tắc “window luôn nhanh hơn GROUP BY + JOIN”. Hãy đo trên dữ liệu và truy vấn thực tế. Yêu cầu đầu ra và tính dễ hiểu là yếu tố đầu tiên.

## 30. EXPLAIN: Aggregate và WindowAgg trong PostgreSQL

PostgreSQL có thể dùng các node kế hoạch khác nhau:

- `HashAggregate`: tổng hợp theo nhóm bằng cấu trúc hash khi phù hợp.
- `GroupAggregate`: tổng hợp theo nhóm trên các hàng đã có thứ tự thích hợp.
- `WindowAgg`: tính các window functions trên tập hàng theo phân vùng/thứ tự yêu cầu.
- `Sort`: sắp xếp dữ liệu để phục vụ grouping, window ordering hoặc ORDER BY kết quả.
- `Incremental Sort`: có thể tận dụng thứ tự một phần trong một số kế hoạch.

**Các tên trên là ví dụ có thể xuất hiện, không phải cam kết** mọi PostgreSQL version hoặc mọi dữ liệu đều có đúng node như vậy.

### 30.1. Kế hoạch cho GROUP BY

```sql
EXPLAIN
SELECT department_id, SUM(salary_million)
FROM window188.employees
GROUP BY department_id;
```

Planner có thể chọn hash aggregation hoặc group aggregation tùy kích thước và thống kê.

### 30.2. Kế hoạch cho window

```sql
EXPLAIN
SELECT
    employee_id,
    department_id,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_total
FROM window188.employees;
```

Có thể thấy `WindowAgg` và bước sắp xếp dữ liệu theo khóa partition khi cần thiết.

### 30.3. GROUP BY rồi window

```sql
EXPLAIN
SELECT
    department_id,
    SUM(salary_million) AS department_total,
    SUM(SUM(salary_million)) OVER () AS company_total
FROM window188.employees
GROUP BY department_id;
```

Truy vấn có hai tầng ngữ nghĩa nên plan có thể có cả **aggregation** và **window**.

### 30.4. Đo thời gian thực tế

Trong database lab:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    employee_id,
    department_id,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_total
FROM window188.employees;
```

`EXPLAIN ANALYZE` thực thi query để đo thời gian và số hàng; ở các ví dụ `SELECT` lab này phù hợp. Không chạy tùy tiện `EXPLAIN ANALYZE` với câu DML có side effect trên production.

### 30.5. Hiệu năng phụ thuộc vào gì?

- **Số hàng đầu vào:** window có thể cần xử lý và trả nhiều hàng hơn GROUP BY.
- **Khóa partition và ORDER BY:** quyết định cách sắp xếp, khả năng tận dụng thứ tự sẵn có và số partition.
- **Frame:** window có thứ tự và frame phức tạp có thể tốn bộ nhớ/công việc hơn toàn-partition aggregate.
- **Chỉ mục:** chỉ mục theo khóa lọc/partition/order đôi khi hỗ trợ kế hoạch, nhưng không thay thế việc đo.
- **Số hàng tạo ra từ JOIN:** nếu join nhân hàng, window/aggregate phải xử lý nhiều hơn.
- **work_mem và sort spill:** một số truy vấn lớn có thể ghi dữ liệu tạm ra đĩa khi sort/window vượt giới hạn bộ nhớ phù hợp.
- **Mức độ chọn lọc:** lọc dữ liệu trước hay sau window có thể làm thay đổi cả **kết quả** lẫn chi phí.

**Không thay đổi WHERE/OVER chỉ để plan trông nhanh hơn** nếu điều đó khiến tập hàng tham gia tính toán bị thay đổi.

## 31. Khi nào chọn GROUP BY và khi nào chọn window?

| Yêu cầu | Nên ưu tiên | Lý do |
|---|---|---|
| Số nhân viên trong mỗi phòng | `GROUP BY` | Cần một hàng/phòng |
| Tổng lương toàn công ty | Aggregate không GROUP BY | Cần một con số |
| Danh sách nhân viên và tổng lương phòng trên mỗi hàng | `OVER(PARTITION BY ...)` | Giữ từng nhân viên |
| Danh sách giao dịch và tổng tiền lũy kế | Window có `ORDER BY/ROWS` | Tính qua hàng trước |
| Xếp hạng nhân viên theo lương trong phòng | `RANK/ROW_NUMBER OVER` | Giữ từng nhân viên |
| Nhân viên cao hơn trung bình phòng | Window trong CTE, lọc ngoài | Cần so sánh mỗi hàng với nhóm |
| Báo cáo tổng doanh thu từng ngày | `GROUP BY sold_on` | Một hàng/ngày |
| Doanh thu từng ngày và lũy kế qua ngày | `GROUP BY` rồi window | Hai cấp tính toán |
| Chỉ phòng có tổng lương > 45 | `HAVING` | Lọc nhóm |
| Top 1 nhân viên mỗi phòng | `ROW_NUMBER OVER` rồi `WHERE rn=1` | Chọn một hàng có quy tắc |
| Tỷ trọng tổng phòng trên tổng công ty | `GROUP BY` rồi window | Tính chỉ số trên các nhóm |
| Báo cáo có phòng trống | `departments LEFT JOIN employees` rồi GROUP BY | Phải bảo toàn nguồn phòng |
| Đếm loại trạng thái trong mỗi nhóm | `GROUP BY + FILTER` | Một hàng/nhóm, nhiều chỉ số |

### Quy tắc chọn nhanh

- **Muốn ít hàng hơn, mỗi nhóm một hàng?** Hãy nghĩ đến `GROUP BY`.
- **Muốn giữ từng hàng và gắn chỉ số nhóm/chuỗi?** Hãy nghĩ đến `OVER`.
- **Muốn vừa nhóm theo ngày vừa cộng dồn theo thời gian?** Kết hợp `GROUP BY` và `OVER` theo hai tầng.
- **Muốn chỉ giữ những hàng đạt tiêu chí window?** Tính window trước trong CTE, lọc sau ở query ngoài.

## 32. Những lỗi phổ biến cần tránh

### Lỗi 1. Nghĩ PARTITION BY giống GROUP BY

`PARTITION BY` xác định partition window nhưng không tự gom các hàng thành một.

**Hậu quả:** báo cáo mong một hàng/phòng lại trả một hàng/nhân viên.

### Lỗi 2. Dùng GROUP BY khi vẫn cần tên từng nhân viên

Khi nhóm theo phòng, chọn `employee_name` không tổng hợp thường không hợp lệ.

**Cách sửa:** giữ từng hàng nhân viên và dùng `SUM(...) OVER(PARTITION BY ...)`.

### Lỗi 3. Thêm ORDER BY vào OVER rồi tưởng vẫn là tổng toàn phòng

`SUM(salary) OVER(PARTITION BY dept ORDER BY employee_id)` có thể trở thành lũy kế theo frame mặc định, không còn tổng toàn partition lặp trên từng hàng.

**Cách sửa:** bỏ ORDER BY nếu muốn tổng toàn phòng, hoặc đặt frame `UNBOUNDED PRECEDING ... UNBOUNDED FOLLOWING`.

### Lỗi 4. Quên peers trong RANGE mặc định

Hai giao dịch cùng ngày có thể nhận cùng tổng lũy kế dù chưa phải từng giao dịch riêng.

**Cách sửa:** nếu muốn cộng từng hàng, dùng `ROWS ... CURRENT ROW` với khóa phụ duy nhất.

### Lỗi 5. Dùng ROW_NUMBER mà ORDER BY không xác định hòa

Nếu hai nhân viên bằng lương, thứ tự chọn “người đầu” có thể không ổn định khi chỉ ORDER BY lương.

**Cách sửa:** thêm `employee_id` hoặc khóa phụ ổn định cho ROW_NUMBER. Nếu cần giữ người đồng hạng, dùng RANK/DENSE_RANK theo tiêu chí đúng.

### Lỗi 6. Thêm employee_id vào RANK khiến mất đồng hạng

`RANK() OVER(ORDER BY salary DESC, employee_id)` đánh giá tuple khác nhau nên không còn cùng rank khi chỉ lương bằng nhau.

**Cách sửa:** giữ `ORDER BY salary DESC` trong RANK nếu “đồng lương là đồng hạng”.

### Lỗi 7. Đặt window trong WHERE hoặc HAVING cùng cấp

PostgreSQL không cho phép window function trực tiếp trong các mệnh đề này.

**Cách sửa:** dùng CTE/subquery để tính trước, query ngoài để lọc.

### Lỗi 8. Lọc WHERE trước rồi mong window vẫn thấy mọi hàng

`WHERE salary >= 18` làm nhân viên lương thấp biến mất trước khi tính trung bình partition.

**Cách sửa:** tính trung bình trên dữ liệu đầy đủ ở CTE, sau đó lọc kết quả ngoài.

### Lỗi 9. Lấy tổng các tổng phòng đã lặp trên mỗi nhân viên

Tổng 51 bị lặp ba lần, tổng 50 lặp hai lần, tổng 40 lặp ba lần. Cộng tất cả các ô cho 373 thay vì 141.

**Cách sửa:** tổng hợp ở grain phòng hoặc tính `SUM(SUM(salary)) OVER()` sau GROUP BY.

### Lỗi 10. Dùng COUNT(*) cho một phòng trống sau LEFT JOIN

Phòng trống vẫn có một hàng NULL mở rộng, nên COUNT(*) trả 1.

**Cách sửa:** dùng `COUNT(e.employee_id)`.

### Lỗi 11. Tưởng window tạo ngày không có giao dịch

Không có hàng ngày 07/01 trong sales thì window không tự sinh ngày đó.

**Cách sửa:** `generate_series` dựng calendar, LEFT JOIN doanh số, rồi GROUP BY và window.

### Lỗi 12. Dùng SUM trên bảng đã join một-nhiều mà không xét fan-out

Một nhân viên có nhiều hàng kỹ năng sẽ làm lương của họ bị cộng lặp.

**Cách sửa:** xác định grain, tổng hợp nguồn con trước khi join, hoặc dùng EXISTS.

### Lỗi 13. Dùng DISTINCT trong window aggregate khi PostgreSQL không hỗ trợ

`COUNT(DISTINCT x) OVER(...)` không hợp lệ trong PostgreSQL theo các phiên bản phổ biến.

**Cách sửa:** dùng aggregate thường hoặc tách bước DISTINCT vào CTE/subquery.

### Lỗi 14. Dùng LAST_VALUE mà không xem frame

`LAST_VALUE` với frame mặc định có thể trả giá trị của hàng hiện tại thay vì hàng cuối partition.

**Cách sửa:** dùng frame kết thúc `UNBOUNDED FOLLOWING` hoặc dùng `MAX/MIN OVER(PARTITION BY ...)` nếu chỉ cần cực trị.

### Lỗi 15. Tin rằng OVER ORDER BY quyết định thứ tự đầu ra

Nó quyết định thứ tự tính window, không bảo đảm thứ tự kết quả cuối.

**Cách sửa:** thêm `ORDER BY` ở cấp SELECT.

### Lỗi 16. Dùng LIMIT sau window rồi tưởng window chỉ tính các hàng hiển thị

`LIMIT 3` sau window vẫn có thể giữ tổng 141 trên mỗi hàng hiển thị.

**Cách sửa:** nếu chỉ tính trên ba hàng, chọn ba hàng trong subquery trước window.

## 33. Bài tập thực hành có lời giải

Các bài sau dùng đúng schema `window188` đã tạo ở đầu bài.

### Bài 1. Đếm số nhân viên theo phòng

**Yêu cầu:** trả một hàng/phòng có nhân viên.

```sql
SELECT
    department_id,
    COUNT(*) AS employee_count
FROM window188.employees
GROUP BY department_id
ORDER BY department_id;
```

**Đáp án:** phòng 10 có 3, phòng 20 có 2, phòng 30 có 3.

### Bài 2. Giữ tên nhân viên và số người cùng phòng

```sql
SELECT
    employee_name,
    department_id,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS department_employee_count
FROM window188.employees
ORDER BY department_id, employee_id;
```

**Đáp án:** 8 hàng. Mỗi nhân viên ở phòng 10 nhận 3, phòng 20 nhận 2, phòng 30 nhận 3.

### Bài 3. Tổng lương công ty dưới dạng một hàng

```sql
SELECT SUM(salary_million) AS company_salary
FROM window188.employees;
```

**Đáp án:** 141.

### Bài 4. Tổng lương công ty gắn vào từng nhân viên

```sql
SELECT
    employee_id,
    salary_million,
    SUM(salary_million) OVER () AS company_salary
FROM window188.employees
ORDER BY employee_id;
```

**Đáp án:** 8 hàng, mỗi hàng có company_salary = 141.

### Bài 5. Vì sao GROUP BY trả 3 hàng còn window trả 8?

**Lời giải:** GROUP BY gom mỗi phòng thành một hàng. Window tính chỉ số trên partition phòng nhưng giữ từng hàng nhân viên.

### Bài 6. Tìm phòng có tổng lương từ 50 triệu

```sql
SELECT
    department_id,
    SUM(salary_million) AS total_salary
FROM window188.employees
GROUP BY department_id
HAVING SUM(salary_million) >= 50
ORDER BY department_id;
```

**Đáp án:** phòng 10 (51), phòng 20 (50).

### Bài 7. Tìm nhân viên lương cao hơn trung bình phòng

```sql
WITH enriched AS (
    SELECT
        employee_id,
        employee_name,
        department_id,
        salary_million,
        AVG(salary_million) OVER (
            PARTITION BY department_id
        ) AS dept_avg
    FROM window188.employees
)
SELECT employee_id, employee_name, department_id
FROM enriched
WHERE salary_million > dept_avg
ORDER BY department_id, employee_id;
```

**Đáp án:** Bình, Chi, Hà, Phúc.

### Bài 8. Vì sao COUNT(*) không đúng khi phòng trống?

Phòng 40 không có nhân viên, nhưng LEFT JOIN sinh một hàng với cột employee NULL.

**Lời giải:** `COUNT(*)` đếm 1 hàng kết quả; `COUNT(e.employee_id)` đếm 0 nhân viên thật.

### Bài 9. Xếp hạng lương phòng 10

```sql
SELECT
    employee_id,
    salary_million,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary_million DESC
    ) AS rnk,
    DENSE_RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary_million DESC
    ) AS dense_rnk
FROM window188.employees
WHERE department_id = 10
ORDER BY salary_million DESC, employee_id;
```

**Đáp án:** Bình và Chi rank 1, dense rank 1; An rank 3, dense rank 2.

### Bài 10. Chọn một người lương cao nhất mỗi phòng

```sql
WITH ranked AS (
    SELECT *,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary_million DESC, employee_id
           ) AS rn
    FROM window188.employees
)
SELECT employee_name, department_id, salary_million
FROM ranked
WHERE rn = 1
ORDER BY department_id;
```

**Đáp án:** Bình, Hà, Phúc.

### Bài 11. Giữ toàn bộ người cùng hạng nhất

Thay ROW_NUMBER bằng:

```sql
RANK() OVER (
    PARTITION BY department_id
    ORDER BY salary_million DESC
)
```

rồi lọc rank = 1 ở query ngoài.

**Đáp án:** Bình, Chi, Hà, Phúc.

### Bài 12. Tính tổng giao dịch lũy kế từng hàng

```sql
SELECT
    sale_id,
    sold_on,
    amount,
    SUM(amount) OVER (
        ORDER BY sold_on, sale_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_total
FROM window188.sales
ORDER BY sold_on, sale_id;
```

**Đáp án:** 100, 140, 160, 220, 310, 320.

### Bài 13. Vì sao hai giao dịch 05/01 có thể cùng running total 140?

Với:

```sql
SUM(amount) OVER (ORDER BY sold_on)
```

frame mặc định dựa trên RANGE và gồm các hàng peers có cùng ngày 05/01.

**Lời giải:** cả hai nhận 140. Nếu cần cộng từng giao dịch, dùng ROWS và sắp thứ tự bằng `sold_on, sale_id`.

### Bài 14. Tổng ngày và lũy kế ngày

```sql
WITH daily AS (
    SELECT sold_on, SUM(amount) AS daily_total
    FROM window188.sales
    GROUP BY sold_on
)
SELECT
    sold_on,
    daily_total,
    SUM(daily_total) OVER (
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_total
FROM daily
ORDER BY sold_on;
```

**Đáp án:** ngày 05/01: 140/140; 06/01: 20/160; 08/01: 60/220; 01/02: 90/310; 05/02: 10/320.

### Bài 15. Hiển thị cả ngày 07/01 không có giao dịch

```sql
WITH calendar AS (
    SELECT DATE '2026-01-05' + n AS day
    FROM generate_series(0,3) AS g(n)
),
daily AS (
    SELECT
        c.day,
        COALESCE(SUM(s.amount),0) AS revenue
    FROM calendar AS c
    LEFT JOIN window188.sales AS s
        ON s.sold_on=c.day
    GROUP BY c.day
)
SELECT
    day,
    revenue,
    SUM(revenue) OVER (
        ORDER BY day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running
FROM daily
ORDER BY day;
```

**Đáp án:** ngày 07/01 có revenue 0, running 160.

### Bài 16. Chỉ lấy ba nhân viên đầu nhưng tổng vẫn là 141

```sql
SELECT
    employee_id,
    SUM(salary_million) OVER() AS company_total
FROM window188.employees
ORDER BY employee_id
LIMIT 3;
```

**Lời giải:** window tính trên tám nhân viên trước khi LIMIT kết quả còn ba hàng. Muốn tổng của ba người, dùng CTE chọn ba người trước rồi mới áp dụng window.

### Bài 17. Tính tỷ trọng quỹ lương từng phòng

```sql
WITH dept AS (
    SELECT department_id,
           SUM(salary_million) AS total
    FROM window188.employees
    GROUP BY department_id
)
SELECT
    department_id,
    total,
    ROUND(
        100.0 * total / SUM(total) OVER(), 2
    ) AS share_pct
FROM dept
ORDER BY department_id;
```

**Đáp án:** xấp xỉ 36.17%, 35.46%, 28.37%.

### Bài 18. Lọc theo số thứ tự trong WHERE cùng cấp có hợp lệ không?

```sql
-- Sai:
SELECT
    employee_id,
    ROW_NUMBER() OVER(
        PARTITION BY department_id
        ORDER BY employee_id
    ) AS rn
FROM window188.employees
WHERE rn = 1;
```

**Lời giải:** không. Alias ở SELECT/window không thể được `WHERE` cùng cấp dùng trực tiếp như vậy. Cần tính `rn` trong CTE/subquery rồi lọc ở query ngoài.

### Bài 19. Tại sao SUM tổng phòng lặp trên nhân viên có thể cộng thành 373?

**Lời giải:** phòng 10 tổng 51 được lặp ba lần, phòng 20 tổng 50 lặp hai lần, phòng 30 tổng 40 lặp ba lần. Cộng các giá trị đã lặp là `153 + 100 + 120 = 373`, không phải tổng lương công ty. Phải đưa dữ liệu về grain **một hàng/phòng** rồi mới cộng các tổng phòng.

### Bài 20. Hàm cửa sổ có tự làm giảm số hàng không?

**Không.** Hàm cửa sổ tự nó gắn phép tính vào các hàng ở mức chi tiết hiện tại. Tuy nhiên, **query có thể đồng thời có GROUP BY, DISTINCT hoặc LIMIT** làm thay đổi số hàng ở những giai đoạn khác; vì thế phải nhìn toàn bộ cấu trúc SQL.

## 34. Bảng ghi nhớ nhanh

| Mục đích | Cú pháp | Tác động lên số hàng |
|---|---|---|
| Tổng toàn bảng | `SELECT SUM(x) FROM t` | Thường một hàng aggregate |
| Tổng mỗi nhóm | `SELECT k, SUM(x) FROM t GROUP BY k` | Một hàng mỗi nhóm có dữ liệu |
| Tổng nhóm trên từng hàng | `SUM(x) OVER (PARTITION BY k)` | Giữ các hàng hiện tại |
| Tổng toàn bảng trên từng hàng | `SUM(x) OVER ()` | Giữ các hàng hiện tại |
| Đếm bản ghi cùng nhóm | `COUNT(*) OVER(PARTITION BY k)` | Giá trị lặp theo partition |
| Tổng lũy kế từng hàng | `SUM(x) OVER(ORDER BY t,id ROWS UNBOUNDED PRECEDING)` | Giữ từng hàng, giá trị tăng dần |
| Tổng toàn partition khi có ORDER | `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` | Mỗi hàng cùng tổng partition |
| Lọc hàng đầu vào | `WHERE ...` | Trước GROUP BY/window cùng cấp |
| Lọc nhóm | `HAVING SUM(x)>...` | Sau GROUP BY, trước window cùng cấp |
| Lọc theo kết quả window | Window trong CTE, `WHERE` ngoài | Sau khi window đã được tính |
| Đếm nhiều trạng thái mỗi nhóm | `COUNT(*) FILTER(WHERE ...)` + GROUP BY | Một hàng/nhóm |
| Đếm điều kiện trên từng hàng | `COUNT(*) FILTER(WHERE ...) OVER(PARTITION BY k)` | Mỗi hàng nhận chỉ số nhóm |
| Xếp hạng | `RANK() OVER(PARTITION BY k ORDER BY x DESC)` | Giữ từng hàng |
| Chọn top 1 | `ROW_NUMBER() OVER(...)` rồi lọc rn = 1 ở ngoài | Một hàng/nhóm nếu nhóm không rỗng |
| Giữ đồng hạng nhất | `RANK() OVER(...)` rồi lọc rank = 1 | Có thể nhiều hàng/nhóm |
| Lấy giá trị hàng trước | `LAG(x) OVER(ORDER BY t,id)` | Giữ từng hàng |
| Nhóm ngày rồi tích lũy | GROUP BY ngày trong CTE, SUM OVER ngoài | Một hàng/ngày |
| Nhóm rồi tính tỷ trọng nhóm | `SUM(SUM(x)) OVER()` hoặc CTE nhóm | Một hàng/nhóm |
| Nhìn kế hoạch tổng hợp | `EXPLAIN` với GROUP BY | Có thể HashAggregate/GroupAggregate |
| Nhìn kế hoạch cửa sổ | `EXPLAIN` với OVER | Có thể WindowAgg và Sort |

## 35. Tổng kết: xác định mức chi tiết trước khi chọn cú pháp

Để phân biệt tổng hợp theo nhóm và hàm cửa sổ trong PostgreSQL, hãy luôn bắt đầu từ câu hỏi:

> **Kết quả cần một hàng cho mỗi nhóm, hay vẫn cần một hàng cho mỗi bản ghi ban đầu?**

Nếu muốn một hàng cho mỗi phòng:

```sql
SELECT
    department_id,
    SUM(salary_million) AS department_salary
FROM window188.employees
GROUP BY department_id;
```

Kết quả có **3 hàng** trên dữ liệu mẫu.

Nếu muốn giữ mọi nhân viên và thêm tổng lương phòng:

```sql
SELECT
    employee_id,
    department_id,
    salary_million,
    SUM(salary_million) OVER (
        PARTITION BY department_id
    ) AS department_salary
FROM window188.employees;
```

Kết quả có **8 hàng**.

Nếu muốn tổng theo ngày và số tích lũy theo ngày:

```sql
WITH daily AS (
    SELECT sold_on, SUM(amount) AS daily_amount
    FROM window188.sales
    GROUP BY sold_on
)
SELECT
    sold_on,
    daily_amount,
    SUM(daily_amount) OVER (
        ORDER BY sold_on
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount
FROM daily
ORDER BY sold_on;
```

Đây là **hai tầng xử lý**, không phải hai phương pháp loại trừ nhau.

Các điều cần ghi nhớ:

1. `GROUP BY` làm thay đổi grain của truy vấn; window functions không tự gom các hàng mà gắn giá trị tính toán vào hàng hiện tại.
2. `PARTITION BY` xác định nhóm hàng mà window nhìn thấy; `ORDER BY` trong `OVER` xác định thứ tự và có thể ảnh hưởng frame.
3. Khi có `ORDER BY` trong window, frame mặc định có thể bao gồm **các hàng đồng hạng**; dùng `ROWS` và khóa phụ rõ ràng cho tổng lũy kế từng bản ghi.
4. `WHERE` và `HAVING` được áp dụng trước window trong cùng cấp SELECT; muốn lọc kết quả window, hãy dùng **CTE/subquery** rồi lọc bên ngoài.
5. GROUP BY và window **có thể kết hợp** để tính tổng theo ngày, tỷ trọng nhóm hoặc xếp hạng các nhóm đã tổng hợp.
6. `LEFT JOIN`, `COUNT(*)` và dữ liệu NULL có thể làm số liệu bị đếm nhầm; kiểm tra đúng grain và cột khóa.
7. Không cộng lại các tổng nhóm đang được lặp trên từng nhân viên, không dùng `DISTINCT` như cách che lỗi join, và không giả định window tự sinh ngày vắng dữ liệu.
8. Chỉ tối ưu hiệu năng sau khi xác định đúng ngữ nghĩa; `EXPLAIN` cho biết PostgreSQL thực hiện các bước aggregation/window ra sao trên dữ liệu thực tế.

**Một câu để nhớ:** `GROUP BY` trả lời “mỗi nhóm là bao nhiêu?”, còn hàm cửa sổ trả lời “đối với hàng này, chỉ số của nhóm hoặc các hàng liên quan là bao nhiêu?”.


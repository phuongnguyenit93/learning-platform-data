# SELF JOIN cho quan hệ trong cùng bảng

Trong cơ sở dữ liệu quan hệ, hai đối tượng có liên hệ với nhau không nhất thiết nằm ở hai bảng khác nhau. Một nhân viên và người quản lý trực tiếp của họ đều là **nhân viên**; một danh mục và danh mục cha đều là **danh mục**; một người và người giới thiệu họ đều là các bản ghi trong **cùng bảng người dùng**. Để đọc được những mối liên hệ đó bằng SQL, ta có thể **kết nối một bảng với chính nó**, gọi là **SELF JOIN**.

SELF JOIN còn hữu ích khi cần **so sánh các dòng trong cùng tập dữ liệu**, chẳng hạn tìm hai nhân viên cùng phòng ban, liệt kê cặp sản phẩm cùng loại, hoặc đối chiếu hai bản ghi theo quan hệ “bản ghi trước – bản ghi sau”.

Bài học thuộc chương **Kết nối bảng** của module Database SQL. Nội dung lấy PostgreSQL làm môi trường thực hành và dùng ví dụ nhân viên–quản lý xuyên suốt. Các dạng `INNER JOIN`, `LEFT JOIN`, điều kiện `ON` và bí danh bảng (`alias`) là kiến thức SQL rộng rãi; một số cú pháp nâng cao hoặc cách tối ưu có khác biệt giữa hệ quản trị.

## 1. SELF JOIN thực chất là gì?

**SELF JOIN không phải một từ khóa JOIN mới**. Đó là cách dùng một bảng **hai hoặc nhiều lần** trong cùng truy vấn, mỗi lần gán một **bí danh** để đại diện cho một vai trò khác nhau.

```sql
SELECT
    e.employee_id,
    e.full_name AS employee_name,
    m.full_name AS manager_name
FROM employees AS e
JOIN employees AS m
    ON e.manager_id = m.employee_id;
```

Trong ví dụ này:

- `employees AS e` là bảng `employees` nhìn từ vai trò **nhân viên**.
- `employees AS m` vẫn là bảng `employees`, nhưng nhìn từ vai trò **người quản lý**.
- `e.manager_id = m.employee_id` là quy tắc xác định một nhân viên có người quản lý nào.

```text
                 CÙNG MỘT BẢNG employees
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
       employees e                 employees m
      (nhân viên)                  (quản lý)
       manager_id ───────────────> employee_id
                        ON
```

Hai bí danh không tạo hai bản sao dữ liệu mới trong database. Chúng tạo hai **nguồn tham chiếu logic** trong câu truy vấn để SQL có thể so sánh các dòng ở hai vai trò. Cơ sở dữ liệu sẽ chọn cách thực thi vật lý phù hợp.

> Tư duy cốt lõi: **Không phải “nối bảng nào với bảng nào?” mà là “một dòng ở vai trò A liên hệ với dòng nào ở vai trò B?”**

## 2. Dữ liệu mẫu: nhân viên và người quản lý

Giả sử có bảng `employees` với các trường:

| Cột | Ý nghĩa |
|---|---|
| `employee_id` | Khóa chính xác định từng nhân viên |
| `full_name` | Tên nhân viên |
| `department` | Phòng ban |
| `manager_id` | ID của **người quản lý trực tiếp**, tham chiếu tới `employees.employee_id`; có thể `NULL` |
| `salary_million` | Lương tháng, đơn vị **triệu VND**, dùng cho ví dụ so sánh |

Dữ liệu ví dụ:

| employee_id | full_name | department | manager_id | salary_million |
|---:|---|---|---:|---:|
| 1 | An | Điều hành | `NULL` | 65 |
| 2 | Bình | Kỹ thuật | 1 | 42 |
| 3 | Chi | Kinh doanh | 1 | 43 |
| 4 | Dũng | Kỹ thuật | 2 | 35 |
| 5 | Hoa | Kỹ thuật | 2 | 48 |
| 6 | Giang | Kinh doanh | 3 | 32 |
| 7 | Huy | Kinh doanh | 3 | 46 |
| 8 | Khánh | Kỹ thuật | 4 | 26 |
| 9 | Lan | Kỹ thuật | 2 | 42 |
| 10 | Minh | Vận hành | `NULL` | 50 |
| 11 | Oanh | Vận hành | 10 | 36 |
| 12 | Phúc | Vận hành | 11 | 29 |

Ở đây:

- `manager_id = 1` nghĩa là nhân viên báo cáo trực tiếp cho An.
- `manager_id = NULL` nghĩa là **không được khai báo người quản lý trực tiếp**. Trong dữ liệu mẫu, An và Minh là hai người đứng đầu của hai nhánh quản lý.
- Một người vừa có thể là **nhân viên được quản lý**, vừa là **quản lý của nhân viên khác**. Ví dụ Dũng báo cáo cho Bình, đồng thời quản lý Khánh.
- Một người quản lý có thể có **nhiều cấp dưới**, nhưng trong mô hình `manager_id` đơn này mỗi nhân viên có **tối đa một người quản lý trực tiếp**.

Sơ đồ quan hệ:

```text
An (1)                               Minh (10)
├── Bình (2)                         └── Oanh (11)
│   ├── Dũng (4)                         └── Phúc (12)
│   │   └── Khánh (8)
│   ├── Hoa (5)
│   └── Lan (9)
└── Chi (3)
    ├── Giang (6)
    └── Huy (7)
```

Sơ đồ trên minh họa một **cấu trúc phân cấp** có hai gốc. Ta sẽ sử dụng SELF JOIN để đọc **một cấp**, **hai cấp**, đếm cấp dưới hoặc tạo những cặp người có quan hệ chung.

## 3. Tạo dữ liệu thực hành PostgreSQL

Có thể chạy đoạn sau trong một phiên PostgreSQL dành riêng cho bài tập. Sử dụng **bảng tạm** `employees`, tự biến mất khi kết nối kết thúc:

```sql
CREATE TEMP TABLE employees (
    employee_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    department TEXT NOT NULL,
    manager_id INTEGER REFERENCES employees(employee_id),
    salary_million NUMERIC(8, 2) NOT NULL,
    CONSTRAINT employees_no_direct_self_manager
        CHECK (manager_id IS NULL OR manager_id <> employee_id)
);

INSERT INTO employees
    (employee_id, full_name, department, manager_id, salary_million)
VALUES
    (1,  'An',    'Điều hành', NULL, 65),
    (2,  'Bình',  'Kỹ thuật',  1,    42),
    (3,  'Chi',   'Kinh doanh',1,    43),
    (4,  'Dũng',  'Kỹ thuật',  2,    35),
    (5,  'Hoa',   'Kỹ thuật',  2,    48),
    (6,  'Giang', 'Kinh doanh',3,    32),
    (7,  'Huy',   'Kinh doanh',3,    46),
    (8,  'Khánh', 'Kỹ thuật',  4,    26),
    (9,  'Lan',   'Kỹ thuật',  2,    42),
    (10, 'Minh',  'Vận hành',  NULL, 50),
    (11, 'Oanh',  'Vận hành',  10,   36),
    (12, 'Phúc',  'Vận hành',  11,   29);

SELECT employee_id, full_name, manager_id
FROM employees
ORDER BY employee_id;
```

Khóa ngoại `manager_id REFERENCES employees(employee_id)` là một **khóa ngoại tự tham chiếu** (*self-referencing foreign key*). Nó cho phép lưu quan hệ “một nhân viên liên hệ tới một nhân viên khác” trong cùng bảng. Ràng buộc `CHECK` cấm một người **trực tiếp làm quản lý của chính mình**.

Nhưng hai ràng buộc này **không đủ để ngăn mọi vòng lặp dài** (ví dụ A → B → C → A). Nếu mô hình yêu cầu tổ chức dạng cây không có chu trình, cần quy tắc kiểm soát bổ sung khi cập nhật cấu trúc quản lý. Phần cuối bài sẽ đề cập cách nhận biết giới hạn này.

**Lưu ý môi trường:** Nếu đang sử dụng một database có bảng thật tên `employees`, nên thực hành ở kết nối riêng hoặc đổi tên bảng tạm và các truy vấn thành `self_join_lab_employees`. Trong PostgreSQL, bảng tạm cùng tên có thể được ưu tiên khi truy vấn không ghi schema, gây nhầm với bảng thật trong phiên hiện tại.

## 4. INNER SELF JOIN: chỉ lấy nhân viên có người quản lý khớp

Yêu cầu: “Hiển thị **từng nhân viên và tên người quản lý trực tiếp**.”

```sql
SELECT
    e.employee_id,
    e.full_name AS employee_name,
    m.employee_id AS manager_id,
    m.full_name AS manager_name
FROM employees AS e
INNER JOIN employees AS m
    ON e.manager_id = m.employee_id
ORDER BY e.employee_id;
```

Trong kết quả:

| employee_id | employee_name | manager_id | manager_name |
|---:|---|---:|---|
| 2 | Bình | 1 | An |
| 3 | Chi | 1 | An |
| 4 | Dũng | 2 | Bình |
| 5 | Hoa | 2 | Bình |
| 6 | Giang | 3 | Chi |
| 7 | Huy | 3 | Chi |
| 8 | Khánh | 4 | Dũng |
| 9 | Lan | 2 | Bình |
| 11 | Oanh | 10 | Minh |
| 12 | Phúc | 11 | Oanh |

Chỉ có **10 dòng**, vì An (`1`) và Minh (`10`) có `manager_id = NULL` nên không khớp được với bất kỳ `m.employee_id` nào.

### 4.1. Đọc điều kiện `ON` theo vai trò

```sql
ON e.manager_id = m.employee_id
```

Ta tìm một dòng ở vai trò **m** sao cho **ID của nó bằng ID quản lý được lưu trên dòng e**.

Ví dụ nhân viên Khánh:

```text
e.employee_id = 8, e.full_name = 'Khánh', e.manager_id = 4
                                      │
                                      ▼
m.employee_id = 4, m.full_name = 'Dũng'
```

SQL không tự biết cột nào là khóa liên kết nếu ta không nói rõ. Bí danh `e`, `m` giúp tránh nhầm giữa `employee_id` của nhân viên và `employee_id` của người quản lý.

### 4.2. Vì sao phải dùng bí danh?

Trong SELF JOIN, cùng một tên bảng xuất hiện hai lần. Nếu viết:

```sql
-- Không nên dùng: tên employee_id, full_name mơ hồ khi cả hai phía
-- đều là employees.
-- SELECT employee_id, full_name
-- FROM employees
-- JOIN employees ON manager_id = employee_id;
```

database không thể diễn giải rõ `employee_id` nào ở vai trò nào, và nhiều hệ còn yêu cầu tên tham chiếu nguồn phải phân biệt. Viết hai alias và dùng **tên đầy đủ `e.column`, `m.column`**:

```sql
SELECT e.employee_id, e.full_name, m.full_name AS manager_name
FROM employees AS e
JOIN employees AS m
    ON e.manager_id = m.employee_id;
```

Đặt alias theo vai trò nghiệp vụ giúp truy vấn dễ đọc hơn nhiều so với `a`, `b` khi các quan hệ phức tạp. Với cặp cùng loại không có vai trò trước–sau, `a`, `b` lại có thể hợp lý.

### 4.3. SELF JOIN không có nghĩa “mỗi dòng khớp với chính nó”

“Tự nối” nghĩa là **bảng tham gia nhiều lần**, không phải tự động so từng dòng với **chính dòng đó**. Trong quan hệ quản lý, ta thường nối **dòng khác**:

```sql
e.manager_id = m.employee_id
```

Trong dữ liệu mẫu, không có người tự quản lý chính mình do ràng buộc `CHECK`. Đối với một bài toán khác, ví dụ so sánh hai sản phẩm, hai alias có thể cùng tham chiếu tới chính một sản phẩm nếu điều kiện `ON` cho phép. Muốn loại “ghép với chính nó”, cần viết điều kiện rõ ràng.

## 5. LEFT SELF JOIN: giữ cả những nhân viên không có người quản lý

Nếu yêu cầu là “Danh sách **tất cả nhân viên**, kèm tên quản lý nếu có”, INNER JOIN không phù hợp vì sẽ loại người có `manager_id = NULL`.

Dùng `LEFT JOIN`:

```sql
SELECT
    e.employee_id,
    e.full_name AS employee_name,
    m.full_name AS manager_name
FROM employees AS e
LEFT JOIN employees AS m
    ON e.manager_id = m.employee_id
ORDER BY e.employee_id;
```

Truy vấn trả **12 dòng**. Với An và Minh, cột `manager_name` là `NULL`:

| employee_id | employee_name | manager_name |
|---:|---|---|
| 1 | An | `NULL` |
| 2 | Bình | An |
| 3 | Chi | An |
| ... | ... | ... |
| 10 | Minh | `NULL` |
| 11 | Oanh | Minh |
| 12 | Phúc | Oanh |

**Bên trái là tập phải được giữ**: `employees AS e`. Với mỗi dòng `e`, PostgreSQL tìm người quản lý `m`. Nếu không tìm được, nó vẫn trả dòng `e` nhưng các cột `m` nhận `NULL`.

### 5.1. Hiển thị nhãn thay cho `NULL`

```sql
SELECT
    e.employee_id,
    e.full_name AS employee_name,
    COALESCE(m.full_name, 'Chưa có quản lý') AS manager_label
FROM employees AS e
LEFT JOIN employees AS m
    ON e.manager_id = m.employee_id
ORDER BY e.employee_id;
```

`COALESCE` thay giá trị `NULL` bằng nhãn để hiển thị. Đây chỉ là **cách trình bày**, không biến `NULL` thành một nhân viên thực.

Nếu dữ liệu không có ràng buộc khóa ngoại, `manager_name IS NULL` cũng có thể xảy ra do `manager_id` trỏ tới một ID **không tồn tại**. Vì vậy, không nên luôn diễn giải “không tìm thấy quản lý” và “không khai báo quản lý” là một trường hợp.

### 5.2. Phân biệt hai nguyên nhân không khớp

Trong mô hình mẫu có khóa ngoại, `manager_id` khác `NULL` phải tham chiếu tới nhân viên tồn tại. Nhưng khi kiểm tra dữ liệu cũ hoặc dữ liệu nhập chưa ràng buộc, ta có thể viết:

```sql
SELECT
    e.employee_id,
    e.full_name,
    e.manager_id,
    CASE
        WHEN e.manager_id IS NULL THEN 'NO_MANAGER_ASSIGNED'
        WHEN m.employee_id IS NULL THEN 'BROKEN_REFERENCE'
        ELSE 'MANAGER_FOUND'
    END AS manager_link_status
FROM employees AS e
LEFT JOIN employees AS m
    ON e.manager_id = m.employee_id
ORDER BY e.employee_id;
```

Trong dữ liệu mẫu không có `BROKEN_REFERENCE`; An và Minh được phân loại `NO_MANAGER_ASSIGNED`.

Lưu ý: truy vấn có thể giúp phát hiện tham chiếu hỏng, nhưng **không thay thế** ràng buộc khóa ngoại và quy trình kiểm tra chất lượng dữ liệu tại thời điểm ghi.

## 6. Đảo vai trò: từ người quản lý tìm các cấp dưới

Quan hệ `e.manager_id = m.employee_id` có thể được đọc từ hai hướng.

### 6.1. Một người quản lý → nhiều nhân viên

```sql
SELECT
    m.employee_id AS manager_id,
    m.full_name AS manager_name,
    e.employee_id AS report_id,
    e.full_name AS report_name
FROM employees AS m
JOIN employees AS e
    ON e.manager_id = m.employee_id
ORDER BY m.employee_id, e.employee_id;
```

Ở đây `m` là phía quản lý, `e` là phía người báo cáo. Những quản lý có nhiều cấp dưới sẽ xuất hiện **nhiều dòng**:

```text
An    → Bình
An    → Chi
Bình  → Dũng
Bình  → Hoa
Bình  → Lan
Chi   → Giang
Chi   → Huy
Dũng  → Khánh
Minh  → Oanh
Oanh  → Phúc
```

Tổng cộng vẫn là 10 quan hệ quản lý trực tiếp, nhưng **độ hạt kết quả là mỗi quan hệ quản lý–cấp dưới**, không phải mỗi quản lý.

### 6.2. Đếm số cấp dưới trực tiếp của từng người

```sql
SELECT
    m.employee_id,
    m.full_name AS manager_or_employee_name,
    COUNT(e.employee_id) AS direct_report_count
FROM employees AS m
LEFT JOIN employees AS e
    ON e.manager_id = m.employee_id
GROUP BY m.employee_id, m.full_name
ORDER BY direct_report_count DESC, m.employee_id;
```

Ví dụ:

| employee_id | full_name | direct_report_count |
|---:|---|---:|
| 2 | Bình | 3 |
| 1 | An | 2 |
| 3 | Chi | 2 |
| 4 | Dũng | 1 |
| 10 | Minh | 1 |
| 11 | Oanh | 1 |
| 5 | Hoa | 0 |
| ... | ... | ... |

Do `LEFT JOIN` giữ cả nhân viên không có cấp dưới, ta phải dùng **`COUNT(e.employee_id)`**, không mặc định dùng `COUNT(*)`:

- `COUNT(e.employee_id)` chỉ đếm những cấp dưới thực sự khớp.
- Với một quản lý không có cấp dưới, `LEFT JOIN` vẫn có **một dòng phía trái**, trong đó `e.employee_id = NULL`. `COUNT(*)` sẽ đếm dòng đó và trả **1** thay vì 0.

Với mô hình `manager_id` là một cột đơn tham chiếu tới khóa chính, mỗi nhân viên khớp tối đa một quản lý trực tiếp; vì thế phép đếm không bị trùng do quan hệ quản lý. Nhưng sau khi ghép thêm bảng một–nhiều khác, cần xem lại **độ hạt** trước khi đếm.

### 6.3. Chỉ chọn người có ít nhất hai cấp dưới

```sql
SELECT
    m.employee_id,
    m.full_name,
    COUNT(e.employee_id) AS direct_report_count
FROM employees AS m
LEFT JOIN employees AS e
    ON e.manager_id = m.employee_id
GROUP BY m.employee_id, m.full_name
HAVING COUNT(e.employee_id) >= 2
ORDER BY direct_report_count DESC, m.employee_id;
```

Kết quả: **Bình (3)**, **An (2)**, **Chi (2)**. `HAVING` lọc **nhóm quản lý** sau khi đã đếm các cấp dưới; còn `WHERE` lọc **dòng trước khi nhóm**.

## 7. SELF JOIN để so sánh nhân viên với quản lý

Khi một quan hệ trỏ đến dòng khác trong cùng bảng, ta có thể so sánh **thuộc tính của hai vai trò**, không chỉ hiển thị tên.

### 7.1. Nhân viên có lương lớn hơn người quản lý

```sql
SELECT
    e.employee_id,
    e.full_name AS employee_name,
    e.salary_million AS employee_salary,
    m.full_name AS manager_name,
    m.salary_million AS manager_salary
FROM employees AS e
JOIN employees AS m
    ON e.manager_id = m.employee_id
WHERE e.salary_million > m.salary_million
ORDER BY e.employee_id;
```

Theo dữ liệu mẫu, có hai trường hợp:

| employee_name | employee_salary | manager_name | manager_salary |
|---|---:|---|---:|
| Hoa | 48 | Bình | 42 |
| Huy | 46 | Chi | 43 |

Đây chỉ là ví dụ so sánh số học; nó **không khẳng định** nhân viên bắt buộc phải có lương thấp hơn người quản lý trong thực tế.

Muốn tìm trường hợp lương **bằng** người quản lý:

```sql
SELECT e.full_name AS employee_name, m.full_name AS manager_name
FROM employees AS e
JOIN employees AS m ON e.manager_id = m.employee_id
WHERE e.salary_million = m.salary_million;
-- Lan và Bình trong dữ liệu mẫu.
```

### 7.2. So sánh phòng ban với quản lý

Yêu cầu: “Những nhân viên làm phòng ban khác với quản lý trực tiếp của mình.”

```sql
SELECT
    e.full_name AS employee_name,
    e.department AS employee_department,
    m.full_name AS manager_name,
    m.department AS manager_department
FROM employees AS e
JOIN employees AS m
    ON e.manager_id = m.employee_id
WHERE e.department <> m.department
ORDER BY e.employee_id;
```

Với dữ liệu mẫu, Bình và Chi báo cáo cho An ở phòng Điều hành nên thuộc trường hợp khác phòng ban. Các quan hệ còn lại đều cùng phòng ban trong mô hình này.

`<>` là toán tử **khác nhau**. Nếu một trong hai thuộc tính được phép `NULL`, phép so sánh có thể trả `UNKNOWN`; muốn đối chiếu `NULL` như một trạng thái riêng, PostgreSQL cung cấp `IS DISTINCT FROM`, hoặc cần viết điều kiện tường minh theo hệ quản trị.

### 7.3. Không đánh đồng vai trò với loại bảng

Hai vai trò `e` và `m` trong cùng một câu SQL đều đọc từ bảng `employees`, nhưng có thể sử dụng **các cột khác nhau** tùy nhu cầu. Ví dụ `m.department` là phòng ban của quản lý, còn `e.department` là phòng ban của nhân viên. Việc đặt tên đầu ra như `employee_department`, `manager_department` tránh hiểu nhầm khi xem kết quả.

## 8. SELF JOIN để tìm hai dòng có chung một thuộc tính

SELF JOIN không chỉ dùng cho quan hệ cha–con. Khi cần **tạo cặp hai dòng trong cùng bảng**, ta dùng hai bí danh để so sánh.

### 8.1. Cặp nhân viên cùng phòng ban

Yêu cầu: “Liệt kê **mỗi cặp nhân viên khác nhau** thuộc cùng phòng ban, không lặp cặp đảo chiều.”

```sql
SELECT
    a.department,
    a.employee_id AS first_employee_id,
    a.full_name AS first_employee,
    b.employee_id AS second_employee_id,
    b.full_name AS second_employee
FROM employees AS a
JOIN employees AS b
    ON a.department = b.department
   AND a.employee_id < b.employee_id
ORDER BY a.department, a.employee_id, b.employee_id;
```

**Hai điều kiện có hai vai trò riêng:**

1. `a.department = b.department`: chỉ ghép những người cùng phòng.
2. `a.employee_id < b.employee_id`: chỉ giữ một chiều của mỗi cặp và **loại ghép một người với chính họ**.

Vì `employee_id` là khóa chính không `NULL`, dấu `<` đảm bảo:

```text
(2, 4) được lấy khi 2 < 4.
(4, 2) bị loại vì 4 < 2 là FALSE.
(2, 2) bị loại vì 2 < 2 là FALSE.
```

Như vậy, cặp `(Bình, Dũng)` chỉ xuất hiện một lần; sẽ không có cặp đảo ngược `(Dũng, Bình)`.

### 8.2. Đếm số cặp và độ tăng số dòng

Với một phòng có `n` nhân viên khác nhau, số cặp **không có thứ tự** là:

\[
\binom{n}{2}=\frac{n(n-1)}{2}
\]

Trong dữ liệu mẫu:

| Phòng ban | Số nhân viên | Số cặp khác nhau |
|---|---:|---:|
| Điều hành | 1 | 0 |
| Kỹ thuật | 5 | 10 |
| Kinh doanh | 3 | 3 |
| Vận hành | 3 | 3 |
| **Tổng** | **12** | **16** |

Truy vấn SELF JOIN cùng phòng ban ở trên tạo **16 cặp**. Một phòng 5 người đã tạo 10 dòng; nếu một phòng có 10.000 người, số cặp có thể tới gần 50 triệu. Do đó, nên dùng phép ghép tạo cặp khi bài toán **thật sự cần từng cặp**, không phải khi chỉ cần số người theo phòng.

Nếu chỉ cần số nhân viên từng phòng:

```sql
SELECT department, COUNT(*) AS employee_count
FROM employees
GROUP BY department
ORDER BY department;
```

Không cần SELF JOIN; `GROUP BY` trực tiếp đơn giản hơn.

### 8.3. Nếu không thêm điều kiện chống cặp trùng

```sql
-- Cảnh báo: ghép cả (a,b), (b,a) và (a,a).
SELECT a.employee_id, b.employee_id
FROM employees AS a
JOIN employees AS b
    ON a.department = b.department;
```

Với phòng có `n` người, điều kiện chỉ kiểm tra cùng phòng tạo **n × n** cặp, bao gồm mỗi người với chính họ.

Thay `a.employee_id < b.employee_id` bằng `a.employee_id <> b.employee_id` thì đã loại các cặp `(a,a)`, nhưng **vẫn còn cả `(a,b)` và `(b,a)`**. Vì thế:

| Điều kiện bổ sung | Cặp `(a,a)` | Cặp đảo `(a,b)` và `(b,a)` |
|---|---|---|
| Không có | Có | Có cả hai |
| `a.employee_id <> b.employee_id` | Không | Có cả hai |
| `a.employee_id < b.employee_id` | Không | Chỉ một chiều |

**Chọn dấu `<` khi quan hệ cặp đối xứng**, tức `(a,b)` và `(b,a)` cùng một ý nghĩa. Nếu cần hai chiều theo vai trò, chẳng hạn “người A gửi tin nhắn cho B” khác “B gửi cho A”, không nên tự loại một chiều.

## 9. Tìm đồng nghiệp có cùng người quản lý trực tiếp

Hai nhân viên được gọi là **cùng nhóm cấp dưới trực tiếp** nếu `manager_id` của họ bằng nhau và không `NULL`.

```sql
SELECT
    a.manager_id,
    a.employee_id AS first_id,
    a.full_name AS first_employee,
    b.employee_id AS second_id,
    b.full_name AS second_employee
FROM employees AS a
JOIN employees AS b
    ON a.manager_id = b.manager_id
   AND a.employee_id < b.employee_id
ORDER BY a.manager_id, a.employee_id, b.employee_id;
```

Kết quả có:

- Dưới An: `(Bình, Chi)`.
- Dưới Bình: `(Dũng, Hoa)`, `(Dũng, Lan)`, `(Hoa, Lan)`.
- Dưới Chi: `(Giang, Huy)`.

Tổng cộng **5 cặp**. Các quản lý chỉ có một cấp dưới không tạo được cặp nào theo điều kiện `<`.

### 9.1. Tại sao hai nhân viên gốc `manager_id = NULL` không ghép thành cặp?

An và Minh cùng có `manager_id = NULL`, nhưng SQL **không coi `NULL = NULL` là `TRUE`**. Vì vậy, điều kiện:

```sql
a.manager_id = b.manager_id
```

không ghép họ lại. Điều này hợp lý về nghiệp vụ: hai người không có người quản lý được ghi nhận **không có nghĩa họ cùng báo cáo cho một người**.

Trong PostgreSQL có các phép so sánh `NULL`-safe như `IS NOT DISTINCT FROM`, nhưng **không nên dùng** ở đây chỉ để tạo cặp hai gốc, bởi sẽ thay đổi ý nghĩa của “cùng người quản lý”.

Muốn hiển thị **tên người quản lý chung**, ta có thể nối thêm lần thứ ba cùng bảng:

```sql
SELECT
    m.full_name AS shared_manager,
    a.full_name AS first_employee,
    b.full_name AS second_employee
FROM employees AS a
JOIN employees AS b
    ON a.manager_id = b.manager_id
   AND a.employee_id < b.employee_id
JOIN employees AS m
    ON m.employee_id = a.manager_id
ORDER BY m.employee_id, a.employee_id, b.employee_id;
```

Ở đây có **ba vai trò** từ cùng bảng:

```text
employees a  ─┐
              ├── cùng manager_id ──> employees m
employees b  ─┘
```

Một bảng có thể tham gia nhiều lần với các alias khác nhau; SELF JOIN không bị giới hạn đúng hai lần.

### 9.2. Hai người cùng phòng chưa chắc cùng quản lý

Trong bảng mẫu, Bình, Dũng, Hoa, Khánh và Lan đều thuộc phòng Kỹ thuật. Nhưng:

- Dũng, Hoa, Lan cùng báo cáo trực tiếp cho Bình.
- Khánh báo cáo cho Dũng.
- Bình báo cáo cho An.

Điều kiện `a.department = b.department` tạo cặp **cùng phòng**, còn `a.manager_id = b.manager_id` tạo cặp **cùng quản lý trực tiếp**. Chúng phản ánh hai quan hệ khác nhau; cần dùng cột đúng với câu hỏi.

## 10. LEFT SELF JOIN và vị trí điều kiện `ON` so với `WHERE`

Một lỗi thường gặp là đặt điều kiện của bảng **bên phải** trong `WHERE` sau `LEFT JOIN`, khiến các dòng không khớp bị loại.

Yêu cầu: “Với **mọi nhân viên**, đếm số cấp dưới trực tiếp thuộc phòng Kỹ thuật.”

### 10.1. Điều kiện ở `ON` để giữ tất cả nhân viên

```sql
SELECT
    m.employee_id,
    m.full_name,
    COUNT(r.employee_id) AS engineering_report_count
FROM employees AS m
LEFT JOIN employees AS r
    ON r.manager_id = m.employee_id
   AND r.department = 'Kỹ thuật'
GROUP BY m.employee_id, m.full_name
ORDER BY m.employee_id;
```

Điều kiện `r.department = 'Kỹ thuật'` chỉ giới hạn **những dòng bên phải được ghép**, không loại những nhân viên phía trái. Kết quả vẫn có **12 dòng**, trong đó:

- Bình có **3** cấp dưới trực tiếp thuộc Kỹ thuật: Dũng, Hoa, Lan.
- Dũng có **1** cấp dưới trực tiếp thuộc Kỹ thuật: Khánh.
- Những người còn lại có **0** cấp dưới trực tiếp thuộc Kỹ thuật.

### 10.2. Cùng điều kiện ở `WHERE` làm mất dòng không khớp

```sql
SELECT
    m.employee_id,
    m.full_name,
    COUNT(r.employee_id) AS engineering_report_count
FROM employees AS m
LEFT JOIN employees AS r
    ON r.manager_id = m.employee_id
WHERE r.department = 'Kỹ thuật'
GROUP BY m.employee_id, m.full_name
ORDER BY m.employee_id;
```

Với nhân viên không có cấp dưới phù hợp, `r.department` là `NULL`; so sánh `NULL = 'Kỹ thuật'` cho `UNKNOWN`, nên `WHERE` loại dòng đó. Truy vấn thứ hai chỉ còn người **có cấp dưới Kỹ thuật**, không phải “mọi nhân viên”.

**Nguyên tắc:** với `LEFT JOIN`, đặt điều kiện kiểm soát **dòng nào ở phía phải được ghép** vào `ON` nếu vẫn muốn giữ toàn bộ phía trái. Đặt điều kiện trong `WHERE` khi thật sự muốn **lọc những dòng kết quả** sau khi nối.

## 11. SELF JOIN qua hai cấp: nhân viên, quản lý, quản lý của quản lý

Một SELF JOIN đọc được một bước quan hệ. Nếu cần hai bước từ nhân viên tới quản lý và **quản lý cấp trên** (*grandmanager*), có thể dùng cùng bảng ba lần:

```sql
SELECT
    e.employee_id,
    e.full_name AS employee_name,
    m.full_name AS direct_manager,
    gm.full_name AS manager_of_manager
FROM employees AS e
LEFT JOIN employees AS m
    ON e.manager_id = m.employee_id
LEFT JOIN employees AS gm
    ON m.manager_id = gm.employee_id
ORDER BY e.employee_id;
```

Với Khánh:

```text
Khánh (8) ──manager_id=4──> Dũng (4)
                                    │
                              manager_id=2
                                    ▼
                                 Bình (2)
```

Nên kết quả là:

| employee_name | direct_manager | manager_of_manager |
|---|---|---|
| Khánh | Dũng | Bình |
| Dũng | Bình | An |
| Hoa | Bình | An |
| Phúc | Oanh | Minh |
| An | `NULL` | `NULL` |

`LEFT JOIN` ở cả hai cấp cho phép giữ những người ở gần gốc và những người không có quản lý. Nếu dùng `INNER JOIN` ở cấp thứ hai, những người không có **quản lý của quản lý** sẽ bị loại.

### 11.1. Ba lần cùng bảng tạo ba vai trò

- `e`: người đang được báo cáo.
- `m`: người quản lý trực tiếp của `e`.
- `gm`: người quản lý trực tiếp của `m`.

Không có bảng `grandmanagers` riêng. Ta chỉ nhìn bảng nhân viên qua chuỗi quan hệ `manager_id`.

### 11.2. Có bao nhiêu cấp có thể viết bằng SELF JOIN cố định?

Một truy vấn thêm từng alias xử lý được số cấp **đã biết trước**. Muốn hiển thị 3 cấp, có thể thêm alias thứ tư; muốn 4 cấp, thêm alias thứ năm. Nhưng nếu độ sâu có thể là 2, 10 hay 50 và không biết trước, việc thêm thủ công nhiều SELF JOIN không phù hợp. Trường hợp đó cần **truy vấn đệ quy** hoặc cấu trúc dữ liệu phân cấp khác.

## 12. SELF JOIN và truy vấn đệ quy: chọn đúng công cụ

SELF JOIN thông thường xử lý tốt:

- Quan hệ **một cấp**: nhân viên → quản lý.
- Quan hệ **hai cấp cố định**: nhân viên → quản lý → quản lý của quản lý.
- So sánh **hai dòng** theo điều kiện chung.
- Đếm **cấp dưới trực tiếp**.

Nhưng câu hỏi “liệt kê **toàn bộ cấp dưới trực tiếp và gián tiếp** của Bình, bất kể sâu bao nhiêu cấp” cần đi theo quan hệ nhiều lần cho tới khi không còn nút mới.

PostgreSQL hỗ trợ `WITH RECURSIVE`:

```sql
WITH RECURSIVE org_tree AS (
    -- Gốc của nhánh muốn xem.
    SELECT
        employee_id,
        full_name,
        manager_id,
        0 AS depth,
        ARRAY[employee_id] AS visited_ids
    FROM employees
    WHERE employee_id = 2

    UNION ALL

    -- Đi từ nhân viên hiện tại tới cấp dưới trực tiếp.
    SELECT
        e.employee_id,
        e.full_name,
        e.manager_id,
        t.depth + 1,
        t.visited_ids || e.employee_id
    FROM employees AS e
    JOIN org_tree AS t
        ON e.manager_id = t.employee_id
    WHERE NOT (e.employee_id = ANY(t.visited_ids))
)
SELECT employee_id, full_name, manager_id, depth
FROM org_tree
ORDER BY depth, employee_id;
```

Kết quả của nhánh bắt đầu tại Bình (`employee_id=2`):

| employee_id | full_name | depth |
|---:|---|---:|
| 2 | Bình | 0 |
| 4 | Dũng | 1 |
| 5 | Hoa | 1 |
| 9 | Lan | 1 |
| 8 | Khánh | 2 |

`depth = 0` là chính Bình, `depth = 1` là cấp dưới trực tiếp, `depth = 2` là cấp dưới gián tiếp. Cột mảng `visited_ids` dùng tính năng của PostgreSQL để không đi lại ID đã có trên **cùng đường duyệt**, giúp tránh lặp vô hạn nếu dữ liệu có chu trình. Đây là kỹ thuật nâng cao, không phải yêu cầu bắt buộc để sử dụng SELF JOIN cơ bản.

### 12.1. Khi nào không cần đệ quy?

Nếu chỉ cần **tên người quản lý trực tiếp**, dùng SELF JOIN một cấp dễ đọc và thường hợp lý hơn. Đừng dùng truy vấn đệ quy cho một quan hệ có độ sâu cố định chỉ vì bảng có cấu trúc phân cấp.

### 12.2. Các giới hạn cần biết

- `manager_id` tự tham chiếu biểu diễn quan hệ **mỗi nhân viên tối đa một quản lý trực tiếp**. Mô hình “một nhân viên thuộc nhiều người quản lý” cần bảng liên kết như `employee_managers(employee_id, manager_id)` thay vì chỉ một cột `manager_id`.
- Khóa ngoại đảm bảo **ID được tham chiếu tồn tại**, nhưng **không đảm bảo không có chu trình dài**.
- Truy vấn đệ quy có chi phí và yêu cầu kiểm soát dữ liệu riêng, đặc biệt trên cấu trúc lớn hoặc sai định dạng.
- Không nên kết luận số cấp dưới trực tiếp bằng số cấp dưới **trực tiếp và gián tiếp**. Hai đại lượng được tính bằng logic khác nhau.

## 13. Phát hiện người không quản lý ai: `LEFT JOIN` và `NOT EXISTS`

Yêu cầu: “Những nhân viên **không có cấp dưới trực tiếp**?”

Cách 1 — `LEFT SELF JOIN`:

```sql
SELECT
    m.employee_id,
    m.full_name
FROM employees AS m
LEFT JOIN employees AS r
    ON r.manager_id = m.employee_id
WHERE r.employee_id IS NULL
ORDER BY m.employee_id;
```

Ở đây, phía trái `m` là người có thể quản lý; phía phải `r` là cấp dưới. Sau `LEFT JOIN`, nếu `r.employee_id IS NULL`, ta biết **không có cấp dưới khớp**.

Kết quả: Hoa, Giang, Huy, Khánh, Lan và Phúc — **6 nhân viên**.

Cách 2 — `NOT EXISTS`:

```sql
SELECT
    m.employee_id,
    m.full_name
FROM employees AS m
WHERE NOT EXISTS (
    SELECT 1
    FROM employees AS r
    WHERE r.manager_id = m.employee_id
)
ORDER BY m.employee_id;
```

`NOT EXISTS` hỏi “có tồn tại ít nhất một cấp dưới trực tiếp hay không?”. Nó cũng trả 6 nhân viên trong dữ liệu mẫu.

### 13.1. Đừng nhầm “không có quản lý” với “không quản lý ai”

Hai điều kiện:

```sql
-- Không có quản lý được khai báo:
WHERE e.manager_id IS NULL

-- Không có cấp dưới trực tiếp:
WHERE NOT EXISTS (
    SELECT 1 FROM employees AS r
    WHERE r.manager_id = e.employee_id
)
```

không giống nhau. An và Minh có **`manager_id IS NULL`** nhưng đều **có cấp dưới**. Khánh có quản lý là Dũng nhưng **không có cấp dưới**.

Những người không có cấp dưới đôi khi được gọi là **nút lá** trong cấu trúc cây; người không có quản lý được gọi là **nút gốc**. Gốc và lá là hai vai trò hoàn toàn khác.

## 14. Truy vấn kiểm tra dữ liệu quan hệ trong cùng bảng

SELF JOIN giúp đọc dữ liệu, đồng thời có thể hỗ trợ phát hiện quan hệ không hợp lệ.

### 14.1. Phát hiện tham chiếu tới quản lý không tồn tại

Khi chưa có hoặc tạm thời chưa áp dụng khóa ngoại:

```sql
SELECT
    e.employee_id,
    e.full_name,
    e.manager_id
FROM employees AS e
LEFT JOIN employees AS m
    ON e.manager_id = m.employee_id
WHERE e.manager_id IS NOT NULL
  AND m.employee_id IS NULL
ORDER BY e.employee_id;
```

Trong bảng mẫu, kết quả **rỗng** do khóa ngoại yêu cầu một `manager_id` khác `NULL` phải trỏ tới ID tồn tại. Truy vấn hữu ích khi kiểm tra nguồn dữ liệu legacy hoặc dữ liệu staging trước khi thêm ràng buộc.

### 14.2. Phát hiện tự quản lý trực tiếp

```sql
SELECT employee_id, full_name
FROM employees
WHERE manager_id = employee_id;
```

Với bảng mẫu, điều kiện `CHECK` không cho phép dữ liệu này, nên kết quả rỗng.

Đây là một ví dụ quan trọng: **không phải mọi quy tắc trong cùng bảng đều cần SELF JOIN**. Nếu chỉ so sánh hai cột **trên cùng một dòng**, `WHERE manager_id = employee_id` là đủ. SELF JOIN cần khi phải tìm hoặc so sánh **một dòng với dòng khác**.

### 14.3. Vòng lặp giữa nhiều nhân viên

Giả sử dữ liệu có các liên kết A → B, B → C và C → A. Mỗi `manager_id` vẫn có thể trỏ tới một ID tồn tại, và không ai trực tiếp trỏ tới chính mình. Vì vậy, khóa ngoại cùng điều kiện `manager_id <> employee_id` chưa ngăn vòng lặp này.

Việc phát hiện toàn bộ chu trình có thể cần truy vấn đệ quy, kiểm soát đường đi hoặc ràng buộc/nghiệp vụ ở tầng cập nhật. SELF JOIN hai cấp có thể phát hiện chu trình đúng hai bước trong một số cấu trúc, nhưng không tổng quát cho chu trình dài bất kỳ.

## 15. SELF JOIN với `NULL`, khóa và độ duy nhất

### 15.1. Vì sao khóa chính ở phía được tham chiếu quan trọng?

Với:

```sql
e.manager_id = m.employee_id
```

`m.employee_id` là khóa chính nên **mỗi nhân viên e có nhiều nhất một dòng m khớp**. Điều đó giúp `LEFT JOIN` trả tối đa một dòng trên mỗi nhân viên đầu vào, và `INNER JOIN` không nhân bản dòng chỉ vì phía người quản lý có ID trùng.

Nếu phía phải nối theo cột không duy nhất:

```sql
-- Không phải quan hệ quản lý, chỉ là nối các cặp cùng phòng:
SELECT a.employee_id, b.employee_id
FROM employees AS a
JOIN employees AS b
    ON a.department = b.department;
```

một dòng `a` có thể khớp **nhiều dòng b**. Đây là quan hệ nhiều–nhiều theo điều kiện `department`, khiến số dòng kết quả tăng mạnh. **Độ duy nhất của khóa nối**, không phải việc hai nguồn cùng bảng hay khác bảng, quyết định số dòng có thể được tạo.

### 15.2. `NULL` trong `manager_id`

Trong SQL:

```sql
NULL = 1       -- UNKNOWN
NULL = NULL    -- UNKNOWN
```

Đây là ý nghĩa logic, không phải cú pháp để chạy như một biểu thức độc lập ở mọi SQL client. Vì so sánh `NULL` không trả `TRUE`, một dòng có `manager_id IS NULL` sẽ không khớp qua `e.manager_id = m.employee_id`.

Dùng `LEFT JOIN` khi muốn giữ dòng này; dùng `WHERE e.manager_id IS NULL` khi muốn **chọn riêng người không khai báo quản lý**.

### 15.3. Một người có thể là quản lý và là cấp dưới

Không nên nghĩ hai bí danh `m` và `e` chia bảng thành hai tập loại trừ nhau. Trong dữ liệu mẫu, Bình:

- Là **cấp dưới** của An trong quan hệ `(Bình → An)`.
- Là **quản lý** của Dũng, Hoa, Lan trong các quan hệ khác.

Bình hoàn toàn có thể xuất hiện dưới alias `e` ở một dòng kết quả và dưới alias `m` ở nhiều dòng khác. Alias đại diện cho **vai trò trong từng lần ghép**, không phải loại nhân viên cố định.

## 16. SELF JOIN và độ hạt sau các phép nối bổ sung

Khi ghép thêm bảng khác, cần hiểu **một dòng kết quả đại diện cho gì**.

Ví dụ:

```sql
SELECT
    m.full_name AS manager_name,
    r.full_name AS report_name
FROM employees AS m
JOIN employees AS r
    ON r.manager_id = m.employee_id;
```

Mỗi dòng là một quan hệ **quản lý–cấp dưới trực tiếp**. Nếu sau đó nối `report_tasks` chứa nhiều nhiệm vụ cho từng cấp dưới:

```sql
SELECT
    m.full_name AS manager_name,
    r.full_name AS report_name,
    t.task_id
FROM employees AS m
JOIN employees AS r
    ON r.manager_id = m.employee_id
JOIN report_tasks AS t
    ON t.employee_id = r.employee_id;
```

một cấp dưới có thể xuất hiện **nhiều lần**, mỗi lần ứng với một nhiệm vụ. Khi đó, `COUNT(*)` đếm các **dòng sau JOIN**, không còn đếm số cấp dưới duy nhất.

Nếu yêu cầu là đếm cấp dưới trực tiếp, dùng bảng `employees` ở đúng độ hạt hoặc tổng hợp nhiệm vụ trước khi ghép; trong một số trường hợp có thể dùng `COUNT(DISTINCT r.employee_id)` khi đã xác định rõ lý do lặp.

**Không nên dùng `DISTINCT` như một cách chữa chung** cho lỗi nối sai. Nó có thể che quan hệ một–nhiều hợp lệ hoặc làm mất các bản ghi giống nhau nhưng khác ID.

## 17. Hiệu năng và chỉ mục khi SELF JOIN

Một SELF JOIN vẫn là một phép JOIN: hệ quản trị phải tìm những cặp dòng thỏa `ON`. Các điểm ảnh hưởng đến hiệu năng gồm:

- Số dòng của bảng.
- Tính chọn lọc và độ duy nhất của cột nối.
- Chỉ mục trên khóa được dùng để tìm dòng liên quan.
- Việc lọc `WHERE` trước/sau JOIN theo ngữ nghĩa phù hợp.
- Số cặp kết quả, đặc biệt với SELF JOIN tạo cặp cùng thuộc tính.

### 17.1. Khóa chính và khóa ngoại không đồng nghĩa đã có chỉ mục hai phía

Trong PostgreSQL, `PRIMARY KEY (employee_id)` tạo chỉ mục hỗ trợ tìm người quản lý theo `employee_id`. Nhưng khai báo **khóa ngoại `manager_id REFERENCES employees(employee_id)` không tự động tạo chỉ mục trên cột `manager_id`**.

Nếu ứng dụng thường xuyên hỏi “ai báo cáo cho quản lý này?”, chỉ mục có thể hữu ích:

```sql
CREATE INDEX idx_employees_manager_id
ON employees(manager_id);
```

Ví dụ truy vấn tận dụng điều kiện:

```sql
SELECT employee_id, full_name
FROM employees
WHERE manager_id = 2
ORDER BY employee_id;
```

Với bảng tạm chỉ có 12 dòng, cơ sở dữ liệu có thể vẫn chọn quét toàn bảng vì đơn giản hơn; điều đó không nói rằng chỉ mục luôn vô ích khi bảng thật có nhiều dòng.

### 17.2. Cặp cùng thuộc tính có thể tăng theo bình phương

SELF JOIN để tạo cặp cùng phòng cần cảnh giác khi phòng có số thành viên lớn:

```sql
SELECT a.employee_id, b.employee_id
FROM employees AS a
JOIN employees AS b
    ON a.department = b.department
   AND a.employee_id < b.employee_id;
```

Nếu nhóm có `n` dòng thì số cặp là `n(n-1)/2`. Thêm chỉ mục không loại bỏ được thực tế rằng **kết quả tự nó có thể rất lớn**. Nếu mục tiêu chỉ là phát hiện “có ít nhất hai người cùng phòng” hoặc đếm nhóm, cân nhắc `GROUP BY`, `HAVING` hay `EXISTS` thay cho liệt kê mọi cặp.

### 17.3. Xem kế hoạch thực thi khi cần

PostgreSQL hỗ trợ:

```sql
EXPLAIN
SELECT e.employee_id, m.full_name AS manager_name
FROM employees AS e
LEFT JOIN employees AS m
    ON e.manager_id = m.employee_id;
```

Kế hoạch có thể dùng nested loop, hash join hoặc phương án khác tùy dữ liệu và thống kê. **SELF JOIN không buộc** database phải thực hiện phép lặp từng dòng theo đúng cách người học tưởng tượng; SQL mô tả quan hệ cần tìm, còn bộ tối ưu chọn thuật toán.

## 18. Khác biệt với các kỹ thuật có vẻ tương tự

| Kỹ thuật | Mục tiêu | Khi nên dùng |
|---|---|---|
| **SELF JOIN** | Ghép hai hoặc nhiều **dòng/vài vai trò** trong cùng bảng | Nhân viên–quản lý, danh mục–cha, cặp đồng nghiệp |
| **JOIN hai bảng khác nhau** | Ghép các đối tượng thuộc hai loại bảng | Đơn hàng–khách hàng, đơn hàng–chi tiết |
| **`GROUP BY`** | Gộp nhiều dòng thành nhóm để tổng hợp | Đếm nhân viên từng phòng, tổng lương từng phòng |
| **`EXISTS`/`NOT EXISTS`** | Kiểm tra sự tồn tại của dòng liên quan | Ai có hoặc không có cấp dưới |
| **CTE đệ quy** | Đi qua quan hệ có độ sâu thay đổi | Tất cả cấp dưới nhiều cấp, đường dẫn danh mục |
| **Hàm cửa sổ** | Tính toán trên nhóm nhưng vẫn giữ dòng chi tiết | Xếp hạng nhân viên theo lương trong phòng |

Một SELF JOIN có thể được thay bằng một truy vấn con tương quan, `EXISTS` hay hàm cửa sổ trong một số bài toán. Nhưng các cách viết có thể **khác độ hạt**, **khác xử lý `NULL`** hoặc **khác mức độ phù hợp để trả cột của dòng liên quan**. Không có một cú pháp “luôn tốt nhất”; hãy chọn kỹ thuật khớp đúng yêu cầu.

## 19. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Không đặt hai alias cho bảng tự nối | Tên cột mơ hồ, khó phân biệt vai trò | Dùng `employees e` và `employees m`, luôn ghi `e.column`/`m.column` |
| Nối `e.employee_id = m.employee_id` khi muốn tìm quản lý | Ghép dòng với chính nó, không tìm quản lý | Dùng `e.manager_id = m.employee_id` |
| Dùng `INNER JOIN` và nghĩ đã lấy hết nhân viên | Loại người có `manager_id = NULL` | Dùng `LEFT JOIN` khi cần giữ tất cả nhân viên |
| Dùng `COUNT(*)` sau `LEFT JOIN` để đếm cấp dưới | Nhân viên không có cấp dưới có thể bị đếm thành 1 | Dùng `COUNT(r.employee_id)` |
| Đặt `r.department = ...` trong `WHERE` sau `LEFT JOIN` | Loại nhân viên không có cấp dưới khớp | Đưa bộ lọc ghép phía phải vào `ON` khi muốn giữ toàn bộ phía trái |
| Ghép hai người cùng phòng mà không loại tự ghép | Cặp `(a,a)` và cặp đảo tạo nhiều dòng | Dùng `a.employee_id < b.employee_id` cho cặp không phân biệt thứ tự |
| Chỉ dùng `a.employee_id <> b.employee_id` để chống trùng | Vẫn có cả `(a,b)` và `(b,a)` | Dùng `<` hoặc một quy tắc thứ tự duy nhất |
| Xem `manager_id = NULL` là quản lý chung | Hai người chưa có quản lý bị coi là cùng quản lý | Dùng `=` thông thường; `NULL` không phải ID quản lý |
| Nghĩ một quản lý luôn thuộc nhóm khác với nhân viên | Bỏ sót người vừa báo cáo vừa quản lý người khác | Alias biểu diễn vai trò, không phải loại người cố định |
| Dùng một SELF JOIN để tìm tất cả cấp dưới nhiều cấp | Chỉ tìm được cấp dưới trực tiếp | Dùng `WITH RECURSIVE` khi cần độ sâu bất kỳ |
| Dùng `SUM` sau JOIN một–nhiều mà không xét độ hạt | Số liệu có thể bị nhân bản | Tổng hợp đúng độ hạt, hoặc chọn nguồn phù hợp |
| Tin khóa ngoại đã ngăn mọi chu trình | Vòng A → B → C → A vẫn có thể tồn tại | Thêm kiểm soát không chu trình khi cập nhật |
| Tin khóa ngoại tự tạo chỉ mục trên `manager_id` | Truy vấn tìm cấp dưới có thể tốn công trên bảng lớn | Xem xét chỉ mục riêng theo tần suất truy vấn |

## 20. Bài tập tự luyện

Tất cả bài tập dùng bảng tạm `employees` ở mục 3. Trước khi viết SQL, hãy xác định **vai trò của từng alias** và **mỗi dòng kết quả đại diện cho gì**.

### Bài 1 — Nhân viên và quản lý

Viết truy vấn lấy `employee_id`, tên nhân viên và tên người quản lý trực tiếp, **giữ cả An và Minh**. Sắp theo `employee_id` tăng dần. Vì sao cần `LEFT JOIN`?

### Bài 2 — Nhân viên thuộc một quản lý cụ thể

Liệt kê tất cả cấp dưới **trực tiếp** của Bình (`employee_id=2`), kèm tên người quản lý, sắp theo mã cấp dưới. Dự đoán những người được trả về.

### Bài 3 — Đếm cấp dưới trực tiếp

Viết truy vấn đếm số cấp dưới trực tiếp của **mọi nhân viên**, kể cả người không quản lý ai. Vì sao `COUNT(*)` không phù hợp khi dùng `LEFT JOIN`?

### Bài 4 — Lương lớn hơn quản lý

Tìm nhân viên có `salary_million` lớn hơn người quản lý trực tiếp. Dự đoán số dòng và tên nhân viên.

### Bài 5 — Đồng nghiệp cùng quản lý

Liệt kê **mỗi cặp** nhân viên có cùng `manager_id`, không ghép một người với chính họ và không lặp cặp đảo chiều. Vì sao `a.employee_id < b.employee_id` giải quyết cả hai yêu cầu?

### Bài 6 — Cùng phòng ban

Đếm số cặp nhân viên khác nhau thuộc phòng `Kỹ thuật`. Có 5 nhân viên trong phòng đó; dự đoán số cặp trước khi viết SQL.

### Bài 7 — Cấp trên hai bậc

Viết truy vấn hiển thị nhân viên, quản lý trực tiếp và quản lý của người quản lý. Xác định **quản lý hai bậc** của Khánh và của Phúc.

### Bài 8 — Nút gốc và nút lá

Viết hai truy vấn riêng:

1. Những nhân viên **không được khai báo người quản lý**.
2. Những nhân viên **không có cấp dưới trực tiếp**.

Vì sao hai kết quả không giống nhau?

### Bài 9 — Điều kiện `ON` so với `WHERE`

So sánh hai cách lấy số cấp dưới Kỹ thuật của mọi nhân viên:

```sql
-- Cách A:
FROM employees AS m
LEFT JOIN employees AS r
    ON r.manager_id = m.employee_id
   AND r.department = 'Kỹ thuật'
```

```sql
-- Cách B:
FROM employees AS m
LEFT JOIN employees AS r
    ON r.manager_id = m.employee_id
WHERE r.department = 'Kỹ thuật'
```

Cách nào giữ đủ 12 nhân viên ở phía trái? Cách nào loại người không có cấp dưới phù hợp?

### Bài 10 — Quan hệ nhiều cấp

Muốn lấy toàn bộ cấp dưới trực tiếp **và gián tiếp** của An, liệu một SELF JOIN chỉ có hai alias có đủ không? Nêu cách dùng thích hợp và cách tránh lặp vô hạn nếu dữ liệu có chu trình.

### Bài 11 — Phát hiện dữ liệu sai

Viết câu SQL tìm các nhân viên có `manager_id` không `NULL` nhưng không tồn tại người quản lý tương ứng. Trong bảng thực hành có khóa ngoại, câu SQL sẽ cho kết quả như thế nào?

### Bài 12 — Tư duy độ hạt sau JOIN

Một người quản lý có hai cấp dưới, mỗi cấp dưới có ba nhiệm vụ trong bảng `report_tasks`. Nếu nối quản lý → cấp dưới → nhiệm vụ, kết quả có thể có bao nhiêu dòng cho người quản lý đó? Muốn đếm **số cấp dưới** thay vì **số nhiệm vụ**, bạn sẽ chọn cách tính nào?

<details>
<summary>Gợi ý đáp án</summary>

**Bài 1:** Dùng `LEFT JOIN` để giữ hai nhân viên có `manager_id = NULL`:

```sql
SELECT e.employee_id, e.full_name AS employee_name,
       m.full_name AS manager_name
FROM employees AS e
LEFT JOIN employees AS m
    ON e.manager_id = m.employee_id
ORDER BY e.employee_id;
```

**Bài 2:** Cấp dưới trực tiếp của Bình là **Dũng, Hoa, Lan**:

```sql
SELECT e.employee_id, e.full_name AS report_name,
       m.full_name AS manager_name
FROM employees AS e
JOIN employees AS m ON e.manager_id = m.employee_id
WHERE m.employee_id = 2
ORDER BY e.employee_id;
```

**Bài 3:** Mỗi dòng phải là **một nhân viên**, kể cả nhân viên có 0 cấp dưới:

```sql
SELECT m.employee_id, m.full_name,
       COUNT(r.employee_id) AS direct_report_count
FROM employees AS m
LEFT JOIN employees AS r ON r.manager_id = m.employee_id
GROUP BY m.employee_id, m.full_name
ORDER BY m.employee_id;
```

`COUNT(*)` đếm cả dòng giữ lại bởi `LEFT JOIN`, khiến người không có cấp dưới có thể bị đếm thành 1.

**Bài 4:** Hai nhân viên là **Hoa** và **Huy**:

```sql
SELECT e.full_name AS employee_name, m.full_name AS manager_name
FROM employees AS e
JOIN employees AS m ON e.manager_id = m.employee_id
WHERE e.salary_million > m.salary_million
ORDER BY e.employee_id;
```

**Bài 5:** Các cặp chỉ xuất hiện một lần nhờ ID nhỏ hơn luôn ở vị trí `a`:

```sql
SELECT a.full_name AS first_employee,
       b.full_name AS second_employee
FROM employees AS a
JOIN employees AS b
    ON a.manager_id = b.manager_id
   AND a.employee_id < b.employee_id
ORDER BY a.employee_id, b.employee_id;
```

Có **5 cặp** từ dữ liệu mẫu.

**Bài 6:** `5 * 4 / 2 = 10` cặp:

```sql
SELECT COUNT(*) AS engineering_pair_count
FROM employees AS a
JOIN employees AS b
    ON a.department = b.department
   AND a.employee_id < b.employee_id
WHERE a.department = 'Kỹ thuật';
```

**Bài 7:** Khánh → Dũng → **Bình**; Phúc → Oanh → **Minh**.

```sql
SELECT e.full_name AS employee_name,
       m.full_name AS direct_manager,
       gm.full_name AS manager_of_manager
FROM employees AS e
LEFT JOIN employees AS m ON e.manager_id = m.employee_id
LEFT JOIN employees AS gm ON m.manager_id = gm.employee_id
ORDER BY e.employee_id;
```

**Bài 8:** Hai người gốc là **An, Minh**; sáu nút lá là **Hoa, Giang, Huy, Khánh, Lan, Phúc**:

```sql
-- Gốc:
SELECT employee_id, full_name
FROM employees
WHERE manager_id IS NULL
ORDER BY employee_id;

-- Lá:
SELECT e.employee_id, e.full_name
FROM employees AS e
WHERE NOT EXISTS (
    SELECT 1 FROM employees AS r
    WHERE r.manager_id = e.employee_id
)
ORDER BY e.employee_id;
```

**Bài 9:** Cách A giữ **12 nhân viên** và đếm 0 cho người không có cấp dưới Kỹ thuật. Cách B chỉ giữ những người có ít nhất một cấp dưới Kỹ thuật; trong dữ liệu mẫu đó là **Bình và Dũng**.

**Bài 10:** Một SELF JOIN hai alias chỉ đi một bước. Dùng `WITH RECURSIVE` theo đường `r.manager_id = parent.employee_id` để đi nhiều cấp, đồng thời giữ tập ID đã thăm hoặc dùng cơ chế phát hiện chu trình phù hợp hệ quản trị. Nếu chỉ muốn **cấp dưới** mà không gồm An, bỏ dòng gốc `depth=0` trong kết quả.

**Bài 11:** Dùng `LEFT JOIN` rồi tìm người có tham chiếu nhưng không có dòng khớp:

```sql
SELECT e.employee_id, e.manager_id
FROM employees AS e
LEFT JOIN employees AS m ON e.manager_id = m.employee_id
WHERE e.manager_id IS NOT NULL
  AND m.employee_id IS NULL;
```

Kết quả rỗng với bảng mẫu có khóa ngoại hợp lệ.

**Bài 12:** Hai cấp dưới × ba nhiệm vụ mỗi người = **6 dòng** sau nối với nhiệm vụ. Muốn đếm cấp dưới, tốt nhất đếm trên quan hệ **quản lý–cấp dưới** trước khi nối nhiệm vụ, hoặc trong trường hợp phù hợp dùng `COUNT(DISTINCT report.employee_id)` sau khi đã hiểu lý do lặp.

</details>

## 21. Nguyên tắc ghi nhớ

**SELF JOIN = một bảng, nhiều vai trò, một điều kiện quan hệ.** Khi viết truy vấn, hãy bắt đầu từ ba câu hỏi:

1. **Hai vai trò là gì?** Ví dụ nhân viên `e` và quản lý `m`, hoặc hai nhân viên `a` và `b`.
2. **Điều kiện ghép nào phản ánh quan hệ thật?** Với quản lý trực tiếp: `e.manager_id = m.employee_id`; với cùng phòng: `a.department = b.department`.
3. **Kết quả cần giữ những dòng nào và ở độ hạt nào?** INNER JOIN chỉ giữ dòng có khớp; LEFT JOIN giữ toàn bộ phía trái; SELF JOIN tạo cặp có thể tăng rất nhiều dòng.

Ba mẫu nền tảng:

```sql
-- Một nhân viên kèm quản lý nếu có.
SELECT e.full_name, m.full_name AS manager_name
FROM employees AS e
LEFT JOIN employees AS m
    ON e.manager_id = m.employee_id;

-- Đếm cấp dưới trực tiếp, kể cả người có 0 cấp dưới.
SELECT m.employee_id, COUNT(r.employee_id) AS direct_report_count
FROM employees AS m
LEFT JOIN employees AS r
    ON r.manager_id = m.employee_id
GROUP BY m.employee_id;

-- Mỗi cặp nhân viên cùng phòng đúng một lần.
SELECT a.employee_id AS first_id, b.employee_id AS second_id
FROM employees AS a
JOIN employees AS b
    ON a.department = b.department
   AND a.employee_id < b.employee_id;
```

Đừng quên kiểm tra **`NULL`**, **khóa có duy nhất hay không**, **vị trí điều kiện `ON`/`WHERE`**, **độ hạt sau khi JOIN**, và **sự khác biệt giữa quan hệ một cấp với toàn bộ cấu trúc nhiều cấp**. Khi diễn đạt được hai vai trò của mỗi alias, SELF JOIN trở thành một kỹ thuật dễ đọc để mô tả và phân tích những mối liên hệ ngay trong một bảng SQL.

# LEFT JOIN, RIGHT JOIN và FULL JOIN trong PostgreSQL

## 1. Vì sao cần OUTER JOIN?

Trong cơ sở dữ liệu quan hệ, dữ liệu thường được chia thành nhiều bảng để tránh lặp thông tin và bảo đảm tính toàn vẹn. Ví dụ, bảng `departments` chứa phòng ban, còn bảng `employees` chứa nhân viên và mã phòng ban mà họ thuộc về.

Khi cần kết hợp hai bảng, câu hỏi nghiệp vụ có thể khác nhau:

- “Liệt kê **các nhân viên đã có phòng ban**” → có thể dùng `INNER JOIN`.
- “Liệt kê **mọi phòng ban**, kể cả phòng chưa có nhân viên” → `LEFT JOIN`.
- “Liệt kê **mọi nhân viên**, kể cả người chưa được gán phòng ban” → `RIGHT JOIN` hoặc viết lại thành `LEFT JOIN` với thứ tự bảng đảo ngược.
- “Liệt kê **tất cả phòng ban và tất cả nhân viên**, bao gồm những bản ghi không ghép được” → `FULL JOIN`.

Ba phép nối cuối là **outer joins**. Chúng giữ những hàng không tìm được đối tác ghép ở một hoặc cả hai phía, đồng thời điền `NULL` vào các cột của phía còn thiếu.

PostgreSQL hỗ trợ các dạng:

```sql
LEFT JOIN         -- tương đương LEFT OUTER JOIN
RIGHT JOIN        -- tương đương RIGHT OUTER JOIN
FULL JOIN         -- tương đương FULL OUTER JOIN
```

Từ khóa `OUTER` có thể bỏ qua mà không thay đổi ý nghĩa.

### Mục tiêu bài học

Sau khi học, bạn sẽ:

1. Phân biệt rõ `INNER`, `LEFT`, `RIGHT` và `FULL JOIN` bằng một bộ dữ liệu có kết quả kiểm chứng được.
2. Hiểu **bảng nào được giữ lại** và vì sao các cột phía không khớp trở thành `NULL`.
3. Viết điều kiện `ON`, `USING` và đặt bộ lọc `WHERE` đúng chỗ.
4. Đếm số bản ghi liên quan bằng `COUNT` mà không đếm nhầm hàng do outer join tạo ra.
5. Tìm bản ghi **không có đối tác** bằng anti-join hoặc `NOT EXISTS`.
6. Hiểu vì sao join một-nhiều có thể làm **tăng số hàng** trong kết quả.
7. Sử dụng `COALESCE`, `CASE`, `GROUP BY` và `ORDER BY` cùng outer join.
8. Nhận diện những tình huống một điều kiện làm outer join vô tình biến thành inner join.
9. Biết cách dùng `EXPLAIN` và chỉ mục để xem hiệu năng nối bảng.
10. Áp dụng các phép nối vào báo cáo phòng ban–nhân viên, khách hàng–đơn hàng và đối soát dữ liệu.

## 2. Bộ dữ liệu thực hành chung

Để quan sát đúng bản chất của ba phép nối, chúng ta cần có:

- Hai phòng ban **có nhân viên**.
- Hai phòng ban **không có nhân viên**.
- Một nhân viên **không thuộc phòng ban nào**.
- Một phòng ban có **nhiều nhân viên**, để thấy rõ việc nhân số hàng.

### 2.1. Sơ đồ quan hệ

```text
departments                              employees
+---------------+---------------+       +-------------+--------------+---------------+
| department_id | department_name|       | employee_id | employee_name| department_id |
+---------------+---------------+       +-------------+--------------+---------------+
|      10       | Kinh doanh    |<------+|     101     | An           |      10       |
|      20       | Kỹ thuật      |<--+    |     102     | Bình         |      10       |
|      30       | Nhân sự       |   +----|     103     | Chi          |      20       |
|      40       | Hỗ trợ        |        |     104     | Dũng         |      NULL     |
+---------------+---------------+       +-------------+--------------+---------------+

Phòng ban 10 có 2 nhân viên.
Phòng ban 20 có 1 nhân viên.
Phòng ban 30, 40 chưa có nhân viên.
Nhân viên 104 chưa được gán phòng ban.
```

Đây là quan hệ **một-nhiều**: một phòng ban có thể có nhiều nhân viên, mỗi nhân viên có tối đa một phòng ban trong mô hình đơn giản này.

### 2.2. Tạo schema và bảng

Trong một database PostgreSQL **dành riêng cho học tập**, dùng role có quyền tạo schema/bảng:

```sql
CREATE SCHEMA IF NOT EXISTS join140;

CREATE TABLE join140.departments (
    department_id bigint PRIMARY KEY,
    department_name text NOT NULL UNIQUE,
    office_city text
);

CREATE TABLE join140.employees (
    employee_id bigint PRIMARY KEY,
    employee_name text NOT NULL,
    department_id bigint
        REFERENCES join140.departments(department_id),
    is_active boolean NOT NULL,
    monthly_salary numeric(12,2) NOT NULL
        CHECK (monthly_salary >= 0)
);
```

Giải thích:

- `department_id` của `departments` là khóa chính, nên không NULL và duy nhất.
- `employees.department_id` là khóa ngoại **được phép NULL**, vì có nhân viên chưa thuộc phòng ban.
- Khóa ngoại ngăn nhân viên tham chiếu một mã phòng ban **không tồn tại**, nếu mã đó khác NULL.
- Cột `is_active` giúp thực hành sự khác nhau giữa bộ lọc đặt trong `ON` và `WHERE`.
- `monthly_salary` giúp minh họa phép tổng hợp sau outer join.

Các lệnh `CREATE TABLE` được viết cho **schema lab mới chưa có các bảng cùng tên**. Nếu bảng đã tồn tại, không tự `DROP TABLE CASCADE` để chạy lại khi chưa xác nhận dữ liệu có thể xóa.

### 2.3. Thêm dữ liệu mẫu

```sql
INSERT INTO join140.departments
    (department_id, department_name, office_city)
VALUES
    (10, 'Kinh doanh', 'Hồ Chí Minh'),
    (20, 'Kỹ thuật', 'Hà Nội'),
    (30, 'Nhân sự', 'Hồ Chí Minh'),
    (40, 'Hỗ trợ', 'Đà Nẵng');

INSERT INTO join140.employees
    (employee_id, employee_name, department_id,
     is_active, monthly_salary)
VALUES
    (101, 'An',   10,   TRUE,  15000000.00),
    (102, 'Bình', 10,   FALSE, 12000000.00),
    (103, 'Chi',  20,   FALSE, 20000000.00),
    (104, 'Dũng', NULL, TRUE,  11000000.00);
```

### 2.4. Kiểm tra dữ liệu đầu vào

```sql
SELECT department_id, department_name, office_city
FROM join140.departments
ORDER BY department_id;

SELECT employee_id, employee_name, department_id, is_active
FROM join140.employees
ORDER BY employee_id;
```

Bảng phòng ban:

| department_id | department_name | office_city |
|---:|---|---|
| 10 | Kinh doanh | Hồ Chí Minh |
| 20 | Kỹ thuật | Hà Nội |
| 30 | Nhân sự | Hồ Chí Minh |
| 40 | Hỗ trợ | Đà Nẵng |

Bảng nhân viên:

| employee_id | employee_name | department_id | is_active |
|---:|---|---:|---|
| 101 | An | 10 | true |
| 102 | Bình | 10 | false |
| 103 | Chi | 20 | false |
| 104 | Dũng | NULL | true |

**Quy ước:** bảng minh họa hiển thị `NULL` bằng chữ để dễ đọc. Trong một số công cụ, giá trị NULL có thể hiện thành ô rỗng hoặc ký hiệu khác. Chữ `NULL` trong bảng kết quả không có nghĩa đây là chuỗi văn bản `'NULL'`.

## 3. Ôn lại INNER JOIN để làm mốc so sánh

`INNER JOIN` chỉ trả các cặp hàng **khớp điều kiện nối**.

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
INNER JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
```

Kết quả:

| department_id | department_name | employee_id | employee_name |
|---:|---|---:|---|
| 10 | Kinh doanh | 101 | An |
| 10 | Kinh doanh | 102 | Bình |
| 20 | Kỹ thuật | 103 | Chi |

Có **3 hàng**:

- Phòng 10 ghép với An và Bình, tạo hai hàng.
- Phòng 20 ghép với Chi, tạo một hàng.
- Phòng 30 và 40 không có nhân viên nên biến mất khỏi kết quả.
- Dũng có `department_id = NULL` nên không khớp với phòng ban nào.

Đây là ranh giới quan trọng: `INNER JOIN` chỉ giữ **phần giao theo điều kiện nối**, còn outer join giữ thêm những hàng không tìm được cặp tương ứng.

### 3.1. Sơ đồ trực quan của các phép nối

```text
               Bảng trái (L)           Bảng phải (R)
                   _______             _______
                  /       \           /       \
                 / L-only  \_________/ R-only  \
                 \         /  MATCH  \         /
                  \_______/           \_______/

INNER JOIN : chỉ MATCH
LEFT JOIN  : L-only + MATCH
RIGHT JOIN : MATCH + R-only
FULL JOIN  : L-only + MATCH + R-only
```

Sơ đồ này chỉ minh họa **nhóm hàng được giữ**. SQL xử lý kết quả theo ngữ nghĩa tập đa hợp (*bag/multiset*), nên một hàng phía trái có thể kết hợp với **nhiều hàng** phía phải và xuất hiện nhiều lần.

## 4. LEFT JOIN: giữ tất cả hàng của bảng bên trái

### 4.1. Cú pháp

```sql
SELECT ...
FROM left_table AS l
LEFT JOIN right_table AS r
    ON join_condition;
```

Cách đọc:

1. Xét từng hàng ở **bảng bên trái**.
2. Tìm các hàng bên phải thỏa điều kiện `ON`.
3. Nếu có một hay nhiều hàng khớp, trả một hàng kết quả cho **mỗi cặp khớp**.
4. Nếu không có hàng bên phải nào khớp, vẫn trả **một hàng** chứa dữ liệu phía trái, với các cột phía phải là `NULL`.

`LEFT OUTER JOIN` và `LEFT JOIN` là hai cách viết có cùng ý nghĩa.

### 4.2. Liệt kê mọi phòng ban, kể cả phòng trống

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

Kết quả:

| department_id | department_name | employee_id | employee_name |
|---:|---|---:|---|
| 10 | Kinh doanh | 101 | An |
| 10 | Kinh doanh | 102 | Bình |
| 20 | Kỹ thuật | 103 | Chi |
| 30 | Nhân sự | NULL | NULL |
| 40 | Hỗ trợ | NULL | NULL |

Có **5 hàng kết quả**, mặc dù bảng `departments` chỉ có 4 hàng:

- Phòng 10 tạo **hai hàng** vì có hai nhân viên.
- Phòng 20 tạo **một hàng** vì có một nhân viên.
- Phòng 30 và 40 mỗi phòng tạo **một hàng NULL mở rộng** (*null-extended row*) vì không có nhân viên nào khớp.

Những hàng NULL mở rộng **không phải hàng nhân viên mới được lưu vào bảng**. Chúng chỉ là kết quả của phép nối.

### 4.3. Vì sao “giữ tất cả hàng trái” không đồng nghĩa “số hàng bằng bảng trái”?

Đối với mỗi phòng ban có `m` nhân viên khớp:

- Nếu `m > 0`, phòng ban đó góp `m` hàng kết quả.
- Nếu `m = 0`, phòng ban đó vẫn góp 1 hàng null-extended.

Ở bộ dữ liệu trên:

```text
Phòng 10: max(1, 2) = 2
Phòng 20: max(1, 1) = 1
Phòng 30: max(1, 0) = 1
Phòng 40: max(1, 0) = 1
                            ---
Tổng số hàng LEFT JOIN =     5
```

Vì thế, với một phép `LEFT JOIN` thông thường không có bộ lọc cuối loại hàng, số hàng kết quả **ít nhất** bằng số hàng của bảng trái, nhưng có thể lớn hơn rất nhiều nếu quan hệ một-nhiều hoặc nhiều-nhiều.

### 4.4. Đảo thứ tự bảng làm đổi câu hỏi

Nếu đổi bảng trái thành `employees`:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    d.department_id,
    d.department_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

Kết quả:

| employee_id | employee_name | department_id | department_name |
|---:|---|---:|---|
| 101 | An | 10 | Kinh doanh |
| 102 | Bình | 10 | Kinh doanh |
| 103 | Chi | 20 | Kỹ thuật |
| 104 | Dũng | NULL | NULL |

Lần này **mọi nhân viên** được giữ. Dũng xuất hiện dù chưa có phòng ban. Phòng Nhân sự và Hỗ trợ không xuất hiện vì chúng thuộc **bảng phải** và không có nhân viên để ghép.

**Quy tắc chọn LEFT JOIN:** xác định đối tượng phải xuất hiện **đầy đủ** trong báo cáo, rồi đặt bảng chứa đối tượng đó ở phía trái.

## 5. RIGHT JOIN: giữ tất cả hàng của bảng bên phải

### 5.1. Cú pháp

```sql
SELECT ...
FROM left_table AS l
RIGHT JOIN right_table AS r
    ON join_condition;
```

`RIGHT JOIN` bảo toàn hàng của **bảng bên phải**, bất kể bảng trái có bản ghi tương ứng hay không. Các cột của bảng trái được điền `NULL` khi không khớp.

### 5.2. Liệt kê mọi nhân viên, kể cả người không có phòng ban

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
RIGHT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

Kết quả:

| department_id | department_name | employee_id | employee_name |
|---:|---|---:|---|
| 10 | Kinh doanh | 101 | An |
| 10 | Kinh doanh | 102 | Bình |
| 20 | Kỹ thuật | 103 | Chi |
| NULL | NULL | 104 | Dũng |

Bốn nhân viên đều xuất hiện, bao gồm Dũng không có phòng ban.

### 5.3. RIGHT JOIN có thể viết lại bằng LEFT JOIN

Hai truy vấn sau có cùng logic và cùng tập đa hợp kết quả nếu giữ nguyên điều kiện nối/các cột được chọn.

Dùng `RIGHT JOIN`:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
RIGHT JOIN join140.employees AS e
    ON e.department_id = d.department_id;
```

Đổi vị trí bảng và dùng `LEFT JOIN`:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id;
```

Điểm khác biệt là **cú pháp và thứ tự bảng**, không phải khả năng biểu đạt.

Nhiều nhóm phát triển ưu tiên `LEFT JOIN` để các câu SQL dài dễ đọc từ trái sang phải. Nhưng `RIGHT JOIN` vẫn hợp lệ và có ích khi muốn giữ bố cục FROM/JOIN đang có hoặc đọc những câu truy vấn do công cụ sinh ra.

### 5.4. RIGHT JOIN không có nghĩa ưu tiên về hiệu năng

Đừng kết luận RIGHT JOIN “chậm hơn” hoặc “nhanh hơn” LEFT JOIN chỉ vì hướng viết. PostgreSQL optimizer có thể biến đổi cách biểu diễn và chọn chiến lược join phù hợp. Hiệu năng thực tế phụ thuộc cardinality, điều kiện nối, chỉ mục, thống kê và kế hoạch truy vấn.

Thực hành tốt: dùng hướng JOIN biểu đạt **ý định rõ nhất**, sau đó đo bằng `EXPLAIN` khi có vấn đề hiệu năng.

## 6. FULL JOIN: giữ những hàng có và không có đối tác từ cả hai phía

### 6.1. Cú pháp

```sql
SELECT ...
FROM left_table AS l
FULL JOIN right_table AS r
    ON join_condition;
```

`FULL OUTER JOIN` tương đương `FULL JOIN`.

Phép nối này trả:

1. Tất cả các **cặp hàng khớp** theo điều kiện `ON`.
2. Mỗi hàng bên trái **không khớp** nào, với cột bên phải là NULL.
3. Mỗi hàng bên phải **không khớp** nào, với cột bên trái là NULL.

### 6.2. Liệt kê cả phòng ban trống lẫn nhân viên chưa có phòng ban

```sql
SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id AS emp_id,
    e.employee_name
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

Kết quả:

| dept_id | department_name | emp_id | employee_name |
|---:|---|---:|---|
| 10 | Kinh doanh | 101 | An |
| 10 | Kinh doanh | 102 | Bình |
| 20 | Kỹ thuật | 103 | Chi |
| 30 | Nhân sự | NULL | NULL |
| 40 | Hỗ trợ | NULL | NULL |
| NULL | NULL | 104 | Dũng |

Có **6 hàng kết quả**:

- **3 cặp khớp** giữa phòng ban và nhân viên.
- **2 phòng ban không khớp**: 30 và 40.
- **1 nhân viên không khớp**: 104.

Có thể hình dung:

```text
FULL JOIN = MATCHED + LEFT_ONLY + RIGHT_ONLY

MATCHED    : (10,101), (10,102), (20,103)
LEFT_ONLY  : (30,NULL), (40,NULL)
RIGHT_ONLY : (NULL,104)

Tổng = 3 + 2 + 1 = 6 hàng
```

**FULL JOIN không phải CROSS JOIN.** Với 4 phòng ban và 4 nhân viên, `CROSS JOIN` sẽ tạo 16 cặp trước khi có điều kiện khác. `FULL JOIN` không ghép mọi hàng với mọi hàng; nó ghép theo `ON` và thêm những hàng chưa có đối tác.

### 6.3. Phân loại ba nhóm hàng bằng CASE

Vì `department_id` của bảng phòng ban và `employee_id` của bảng nhân viên đều là khóa chính `NOT NULL`, ta có thể dùng chính các cột này để xác định phía nào có mặt.

```sql
SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id AS emp_id,
    e.employee_name,
    CASE
        WHEN d.department_id IS NULL THEN 'EMPLOYEE_ONLY'
        WHEN e.employee_id IS NULL THEN 'DEPARTMENT_ONLY'
        ELSE 'MATCHED'
    END AS match_status
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

Kết quả ở cột `match_status`:

| dept_id | emp_id | match_status |
|---:|---:|---|
| 10 | 101 | MATCHED |
| 10 | 102 | MATCHED |
| 20 | 103 | MATCHED |
| 30 | NULL | DEPARTMENT_ONLY |
| 40 | NULL | DEPARTMENT_ONLY |
| NULL | 104 | EMPLOYEE_ONLY |

**Tại sao dùng khóa chính để phân loại?** Vì khóa chính của một hàng thật không thể NULL. Nếu chọn một cột cho phép NULL, ví dụ `office_city`, thì `office_city IS NULL` có thể có nghĩa “phòng ban có tồn tại nhưng chưa nhập thành phố” chứ không phải “không có phòng ban”.

## 7. Bảng so sánh bốn kiểu JOIN trên cùng dữ liệu

| Kiểu nối | Bảng giữ hàng | Số hàng ví dụ | Phòng 30 và 40 xuất hiện? | Dũng xuất hiện? |
|---|---|---:|---|---|
| `INNER JOIN` | Chỉ cặp khớp | 3 | Không | Không |
| `departments LEFT JOIN employees` | Mọi phòng ban | 5 | Có | Không |
| `departments RIGHT JOIN employees` | Mọi nhân viên | 4 | Không | Có |
| `departments FULL JOIN employees` | Mọi bản ghi hai phía | 6 | Có | Có |

Bảng này đúng với **bộ dữ liệu mẫu ở phần 2** và các điều kiện JOIN đã viết. Số hàng sẽ thay đổi khi dữ liệu hoặc điều kiện nối thay đổi.

### 7.1. Chọn câu SQL từ yêu cầu nghiệp vụ

| Câu hỏi nghiệp vụ | Hướng nối đề xuất |
|---|---|
| Danh sách phòng ban và nhân viên, kể cả phòng trống | `departments LEFT JOIN employees` |
| Danh sách toàn bộ nhân viên và phòng ban nếu có | `employees LEFT JOIN departments` |
| Giữ thứ tự FROM từ departments nhưng vẫn liệt kê mọi nhân viên | `departments RIGHT JOIN employees` |
| Đối soát tất cả bản ghi ở cả hai bảng, kể cả không ghép được | `FULL JOIN` |
| Chỉ những nhân viên đã được gán phòng ban | `INNER JOIN` |
| Chỉ những phòng ban chưa có nhân viên | `LEFT JOIN ... WHERE e.employee_id IS NULL` hoặc `NOT EXISTS` |
| Chỉ những nhân viên chưa có phòng ban | `employees LEFT JOIN departments ... WHERE d.department_id IS NULL` |
| Đếm nhân viên trong mọi phòng ban, kể cả số lượng 0 | `departments LEFT JOIN employees` và `COUNT(e.employee_id)` |

## 8. Hiểu rõ ON và WHERE: lỗi outer join phổ biến nhất

Trong `LEFT JOIN`, hai chỗ đặt điều kiện có thể tạo ra **hai kết quả khác nhau**:

- `ON` xác định **hàng nào được coi là khớp**.
- `WHERE` lọc **các hàng của kết quả sau phép nối**.

Sự khác nhau đặc biệt quan trọng khi bảng phải có thể không khớp.

### 8.1. Đặt bộ lọc nhân viên hoạt động trong ON

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.is_active
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
   AND e.is_active = TRUE
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

Kết quả:

| department_id | department_name | employee_id | employee_name | is_active |
|---:|---|---:|---|---|
| 10 | Kinh doanh | 101 | An | true |
| 20 | Kỹ thuật | NULL | NULL | NULL |
| 30 | Nhân sự | NULL | NULL | NULL |
| 40 | Hỗ trợ | NULL | NULL | NULL |

Giải thích:

- Phòng 10 khớp với An đang hoạt động; Bình không được xem là cặp khớp vì `is_active = FALSE`.
- Phòng 20 có Chi nhưng Chi không hoạt động, nên **không có hàng phải nào thỏa toàn bộ ON**; phòng 20 vẫn được giữ với các cột nhân viên NULL.
- Phòng 30/40 vốn chưa có nhân viên, vẫn được giữ.

`LEFT JOIN` bảo toàn các hàng phòng ban dù **không có nhân viên đang hoạt động**.

### 8.2. Chuyển cùng điều kiện sang WHERE

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.is_active
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE e.is_active = TRUE
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

Kết quả:

| department_id | department_name | employee_id | employee_name | is_active |
|---:|---|---:|---|---|
| 10 | Kinh doanh | 101 | An | true |

Tại sao phòng 20, 30 và 40 biến mất?

- Chi ở phòng 20 có `is_active = FALSE` nên bị `WHERE` loại.
- Với phòng 30/40 không có đối tác, `e.is_active` là NULL; so sánh `NULL = TRUE` trả **UNKNOWN**, không được `WHERE` giữ.
- Vì thế, điều kiện này làm câu `LEFT JOIN` **ứng xử giống INNER JOIN đối với điều kiện đang xét**.

### 8.3. Quy tắc nhớ

Nếu mục tiêu là:

> “Hiển thị **tất cả phòng ban**, và chỉ ghép **nhân viên đang hoạt động** nếu có.”

hãy đặt điều kiện nhân viên trong `ON`:

```sql
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
  ON e.department_id = d.department_id
 AND e.is_active = TRUE
```

Nếu mục tiêu là:

> “Chỉ hiển thị **những cặp phòng ban–nhân viên** mà nhân viên đang hoạt động.”

thì bộ lọc `WHERE e.is_active = TRUE` có thể đúng, dù kết quả không còn bảo toàn mọi phòng ban.

**Không phải mọi điều kiện WHERE đều làm mất outer join.** Ví dụ `WHERE d.department_id >= 20` lọc trên bảng được bảo toàn, có thể vẫn giữ những phòng ban còn lại dù không có nhân viên. Vấn đề là **điều kiện loại các hàng null-extended** ở phía không được bảo toàn.

### 8.4. Tư duy theo thứ tự xử lý logic

Một cách diễn giải hữu ích:

1. Lấy nguồn từ `FROM`.
2. Xác định cặp khớp theo `ON`.
3. Với outer join, bổ sung hàng null-extended ở phía cần bảo toàn.
4. Áp dụng bộ lọc `WHERE`.
5. Phân nhóm/tổng hợp, tính SELECT, sắp xếp và LIMIT theo các quy tắc SQL.

Thứ tự này là **mô hình logic để hiểu kết quả**, không phải cam kết PostgreSQL sẽ thực thi vật lý từng bước theo đúng thứ tự. Optimizer có thể biến đổi kế hoạch nhưng phải giữ đúng ngữ nghĩa truy vấn.

## 9. Ba trạng thái logic: TRUE, FALSE và UNKNOWN khi so sánh NULL

SQL dùng logic ba trạng thái khi so sánh giá trị có thể NULL:

| Biểu thức | Kết quả |
|---|---|
| `10 = 10` | TRUE |
| `10 = 20` | FALSE |
| `NULL = 10` | NULL/UNKNOWN |
| `NULL = NULL` | NULL/UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT NULL` | FALSE |

Trong dữ liệu mẫu:

```sql
SELECT employee_id, employee_name
FROM join140.employees
WHERE department_id = NULL;
```

**Không trả được Dũng** vì `department_id = NULL` không phải TRUE cho bất kỳ hàng nào. Phải dùng:

```sql
SELECT employee_id, employee_name
FROM join140.employees
WHERE department_id IS NULL;
```

### 9.1. NULL do không ghép được khác NULL có sẵn trong dữ liệu

Đối với `LEFT JOIN`, cột của bảng phải là NULL có thể là:

- Một cột thực sự NULL trong **hàng phải đã khớp**.
- Một cột NULL do **không có hàng phải nào khớp**.

Để nhận diện một bản ghi bên phải thực sự tồn tại, nên dùng **khóa chính NOT NULL** như `e.employee_id`.

Ví dụ:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.department_id AS employee_department_id
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

Với phòng 30/40, `e.employee_id IS NULL` là bằng chứng không có nhân viên khớp vì một hàng nhân viên thật không thể có khóa chính NULL.

### 9.2. Có nên dùng IS NOT DISTINCT FROM trong ON?

Trong PostgreSQL:

```sql
SELECT
    NULL::integer IS NOT DISTINCT FROM NULL::integer AS both_null_equal,
    NULL::integer = NULL::integer AS normal_equality;
```

Biểu thức đầu trả TRUE, biểu thức thứ hai trả NULL/UNKNOWN.

Nếu hai khóa nối đều được phép NULL **và nghiệp vụ thực sự muốn coi NULL ở hai phía là tương ứng**, `IS NOT DISTINCT FROM` có thể được cân nhắc trong một số loại join. Tuy nhiên, việc ghép các bản ghi “không có mã” với nhau có thể tạo nhiều cặp không mong muốn. Với khóa định danh, phương án tốt hơn thường là **quy định khóa NOT NULL và có giá trị rõ ràng**.

## 10. Tìm các hàng không có đối tác: anti-join

Một ứng dụng thường cần câu trả lời theo kiểu:

- Phòng ban nào **chưa có nhân viên**?
- Nhân viên nào **chưa được gán phòng ban**?
- Khách hàng nào **chưa từng có đơn hàng**?
- Sản phẩm nào **không có tồn kho tương ứng**?

Dạng này gọi là **anti-join** về mặt ngữ nghĩa: tìm những hàng không tồn tại bản ghi liên quan.

### 10.1. Phòng ban chưa có nhân viên bằng LEFT JOIN

```sql
SELECT
    d.department_id,
    d.department_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
```

Kết quả:

| department_id | department_name |
|---:|---|
| 30 | Nhân sự |
| 40 | Hỗ trợ |

Tại sao `WHERE e.employee_id IS NULL` lại đúng ở đây trong khi phần trước cảnh báo WHERE có thể phá outer join?

Vì **mục tiêu lần này chính là giữ các hàng null-extended**. Điều kiện `IS NULL` chọn những phòng ban *không có nhân viên khớp*, thay vì chọn một thuộc tính của nhân viên thật.

### 10.2. Cùng yêu cầu bằng NOT EXISTS

```sql
SELECT
    d.department_id,
    d.department_name
FROM join140.departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM join140.employees AS e
    WHERE e.department_id = d.department_id
)
ORDER BY d.department_id;
```

Kết quả cũng là phòng 30 và 40.

`NOT EXISTS` diễn đạt trực tiếp “không tồn tại hàng thỏa điều kiện tương quan”. Nó thường dễ đọc và tránh phải chọn một cột bên phải chắc chắn NOT NULL để phát hiện hàng không khớp. PostgreSQL optimizer có thể thực thi thành một kế hoạch anti join thích hợp.

### 10.3. Nhân viên chưa có phòng ban

```sql
SELECT
    e.employee_id,
    e.employee_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
WHERE d.department_id IS NULL
ORDER BY e.employee_id;
```

Kết quả: nhân viên `104 — Dũng`.

Nếu có khóa ngoại hợp lệ như trong schema lab, một `department_id` **khác NULL** phải tham chiếu phòng ban tồn tại. Vì vậy, ở bộ dữ liệu này, nhân viên không ghép được là người có `department_id NULL`. Trong bảng staging không có foreign key, một mã phòng ban sai cũng có thể tạo hàng không khớp.

### 10.4. Vì sao NOT IN có thể cho kết quả bất ngờ?

Xét:

```sql
SELECT department_id, department_name
FROM join140.departments
WHERE department_id NOT IN (
    SELECT department_id
    FROM join140.employees
)
ORDER BY department_id;
```

Subquery trả các giá trị `10, 10, 20, NULL`.

Vì có `NULL` trong tập giá trị, phép `NOT IN` có thể đánh giá thành UNKNOWN đối với các mã phòng ban không xuất hiện (30 và 40), khiến chúng **không được trả về**. Câu truy vấn trên dự kiến **không trả hàng nào** trong bộ dữ liệu lab này.

Dùng `NOT EXISTS` hoặc anti-join là cách rõ ràng hơn:

```sql
SELECT d.department_id
FROM join140.departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM join140.employees AS e
    WHERE e.department_id = d.department_id
);
```

Đừng đánh đồng `NOT IN (subquery)` với `NOT EXISTS` khi subquery có thể chứa NULL.

## 11. Đếm bản ghi liên quan: COUNT(*) khác COUNT(cột)

Giả sử báo cáo yêu cầu:

> “Mọi phòng ban phải xuất hiện; phòng nào chưa có nhân viên thì số lượng là 0.”

Có thể dùng `LEFT JOIN` và `GROUP BY`:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Kết quả:

| department_id | department_name | employee_count |
|---:|---|---:|
| 10 | Kinh doanh | 2 |
| 20 | Kỹ thuật | 1 |
| 30 | Nhân sự | 0 |
| 40 | Hỗ trợ | 0 |

### 11.1. Tại sao không dùng COUNT(*)?

```sql
SELECT
    d.department_id,
    COUNT(*) AS joined_row_count,
    COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id
ORDER BY d.department_id;
```

Kết quả:

| department_id | joined_row_count | employee_count |
|---:|---:|---:|
| 10 | 2 | 2 |
| 20 | 1 | 1 |
| 30 | 1 | 0 |
| 40 | 1 | 0 |

`COUNT(*)` đếm **mọi hàng kết quả sau join**, kể cả hàng null-extended đại diện cho phòng trống. Vì mỗi phòng trống vẫn góp một hàng, `COUNT(*)` cho 1.

`COUNT(e.employee_id)` chỉ đếm những hàng mà khóa chính của nhân viên **không NULL**, nên phòng trống cho 0.

**Nguyên tắc:** khi đếm số bản ghi thực sự khớp ở phía không được bảo toàn, hãy dùng `COUNT(pk_bên_phải)` hoặc biểu thức đếm phù hợp, không mặc định dùng `COUNT(*)`.

### 11.2. Đếm nhân viên đang hoạt động

PostgreSQL hỗ trợ `FILTER` trong aggregate:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS total_employees,
    COUNT(e.employee_id)
        FILTER (WHERE e.is_active IS TRUE) AS active_employees
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Kết quả:

| department_id | total_employees | active_employees |
|---:|---:|---:|
| 10 | 2 | 1 |
| 20 | 1 | 0 |
| 30 | 0 | 0 |
| 40 | 0 | 0 |

Ở đây ta muốn **đếm hai nhóm** trong cùng một bộ hàng, nên dùng `FILTER` rất rõ ràng.

Một hướng khác là đặt `e.is_active = TRUE` trong `ON` nếu chỉ quan tâm những nhân viên đang hoạt động và vẫn muốn giữ mọi phòng ban.

### 11.3. Tổng lương cho cả phòng trống

```sql
SELECT
    d.department_id,
    d.department_name,
    COALESCE(SUM(e.monthly_salary), 0) AS total_monthly_salary
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Kết quả dự kiến:

| department_id | total_monthly_salary |
|---:|---:|
| 10 | 27000000.00 |
| 20 | 20000000.00 |
| 30 | 0 |
| 40 | 0 |

`SUM` trên nhóm không có giá trị lương thực sẽ trả NULL; `COALESCE(..., 0)` chuyển kết quả hiển thị thành 0 theo yêu cầu báo cáo.

Nếu nghiệp vụ cần phân biệt “không có nhân viên” với “chưa xác định dữ liệu tiền lương”, không nên tự động đồng nhất NULL và 0 mà không cân nhắc.

## 12. COALESCE: hiển thị giá trị thay thế khi một phía không khớp

`COALESCE(expression1, expression2, ...)` trả giá trị đầu tiên không NULL.

Ví dụ:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    COALESCE(d.department_name, 'Chưa phân phòng') AS displayed_department
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

Kết quả:

| employee_id | employee_name | displayed_department |
|---:|---|---|
| 101 | An | Kinh doanh |
| 102 | Bình | Kinh doanh |
| 103 | Chi | Kỹ thuật |
| 104 | Dũng | Chưa phân phòng |

Câu này giúp giao diện dễ đọc hơn. Tuy nhiên:

- `COALESCE` chỉ tạo **giá trị trong kết quả truy vấn**, không tự cập nhật bảng gốc.
- Giá trị thay thế là một **quy ước trình bày**, không phải bằng chứng dữ liệu đã có.
- Với dữ liệu chứa NULL thật trong một cột mô tả, kết quả thay thế không phân biệt “bản ghi không khớp” và “bản ghi có nhưng thiếu mô tả”. Nếu cần phân biệt, dùng khóa chính của từng phía.

### 12.1. Dùng COALESCE trong FULL JOIN

Trong một số bài toán đối soát hai bảng cùng chứa mã khách hàng, có thể dùng:

```sql
SELECT
    COALESCE(a.customer_id, b.customer_id) AS customer_id,
    a.amount AS source_a_amount,
    b.amount AS source_b_amount
FROM source_a AS a
FULL JOIN source_b AS b
    ON a.customer_id = b.customer_id;
```

Câu SQL trên mang tính **khuôn mẫu**, chỉ chạy được nếu các bảng `source_a` và `source_b` có tồn tại. Nó cho thấy `COALESCE` giúp chọn ID phía có dữ liệu khi FULL JOIN tạo một phía NULL.

Trong dữ liệu lab, có thể quan sát tương tự:

```sql
SELECT
    COALESCE(d.department_id, e.department_id) AS department_id,
    d.department_name,
    e.employee_id
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY department_id NULLS LAST, e.employee_id NULLS LAST;
```

Với Dũng, cả `d.department_id` và `e.department_id` đều NULL, nên `COALESCE` vẫn là NULL. Điều đó đúng: Dũng thực sự **chưa được gán mã phòng ban**.

## 13. USING và ON trong outer join

Khi hai bảng có cột cùng tên và cần nối bằng phép bằng, PostgreSQL cho phép dùng `USING(column_name)`.

### 13.1. Viết bằng ON

```sql
SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON d.department_id = e.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

### 13.2. Viết bằng USING

```sql
SELECT
    department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    USING (department_id)
ORDER BY department_id, e.employee_id NULLS LAST;
```

Với quan hệ khóa đã chọn, hai câu có cùng ý nghĩa ghép.

Điểm cần nhớ:

- `USING (department_id)` yêu cầu **cả hai bảng đều có cột đó**.
- Với `SELECT *`, cột dùng trong `USING` thường xuất hiện **một lần** thay vì hai bản sao `d.department_id` và `e.department_id`.
- Với `FULL JOIN ... USING (key)`, cột chung trong kết quả thể hiện giá trị từ phía có mặt; về ý nghĩa tương tự việc chọn/ghép giá trị khóa phù hợp của hai phía.
- `ON` linh hoạt hơn cho điều kiện khác tên, nhiều predicate hoặc điều kiện không phải phép bằng.

### 13.3. FULL JOIN với USING

```sql
SELECT
    department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    USING (department_id)
ORDER BY department_id NULLS LAST, e.employee_id NULLS LAST;
```

Với phòng 30, 40, cột chung `department_id` lần lượt là 30 và 40 dù `e.department_id` không có hàng để cung cấp. Với Dũng, giá trị chung là NULL vì không có phòng ban trong dữ liệu nhân viên.

Nếu muốn **phân biệt rõ phía gốc của từng giá trị** khi đối soát, có thể ưu tiên `ON` và chọn riêng `d.department_id AS left_id`, `e.department_id AS right_id` cùng hai khóa chính NOT NULL.

### 13.4. Vì sao không lạm dụng NATURAL JOIN?

`NATURAL JOIN` tự tìm mọi cột trùng tên để làm điều kiện nối. Khi schema thay đổi và hai bảng vô tình có thêm cột tên giống nhau, **logic join cũng có thể đổi theo**.

Với dữ liệu nghiệp vụ quan trọng, dùng `ON` hoặc `USING` tường minh để biết chính xác các cột đang được so sánh.

## 14. FULL JOIN dùng để đối soát dữ liệu hai nguồn

Một ứng dụng thường có hai danh sách cần đối chiếu:

- Danh sách người dùng từ hệ thống A và hệ thống B.
- Số dư theo tài khoản tại hai thời điểm.
- Sản phẩm trong hệ thống bán hàng và kho.
- Mã khách hàng trong CRM và hệ thống thanh toán.

Mục tiêu là nhận diện:

1. Có ở cả hai nguồn.
2. Chỉ có ở nguồn trái.
3. Chỉ có ở nguồn phải.
4. Có ở cả hai nguồn nhưng một số giá trị khác nhau.

### 14.1. Ví dụ đối soát số dư

Tạo hai bảng nhỏ trong lab:

```sql
CREATE TABLE join140.balance_source_a (
    account_id bigint PRIMARY KEY,
    balance numeric(12,2) NOT NULL
);

CREATE TABLE join140.balance_source_b (
    account_id bigint PRIMARY KEY,
    balance numeric(12,2) NOT NULL
);

INSERT INTO join140.balance_source_a(account_id, balance)
VALUES
    (1, 100.00),
    (2, 250.00),
    (3, 300.00);

INSERT INTO join140.balance_source_b(account_id, balance)
VALUES
    (2, 250.00),
    (3, 310.00),
    (4, 400.00);
```

### 14.2. FULL JOIN phân loại kết quả

```sql
SELECT
    COALESCE(a.account_id, b.account_id) AS account_id,
    a.balance AS balance_a,
    b.balance AS balance_b,
    CASE
        WHEN a.account_id IS NULL THEN 'ONLY_B'
        WHEN b.account_id IS NULL THEN 'ONLY_A'
        WHEN a.balance IS DISTINCT FROM b.balance THEN 'VALUE_DIFF'
        ELSE 'MATCH'
    END AS reconciliation_status
FROM join140.balance_source_a AS a
FULL JOIN join140.balance_source_b AS b
    ON a.account_id = b.account_id
ORDER BY account_id;
```

Kết quả:

| account_id | balance_a | balance_b | reconciliation_status |
|---:|---:|---:|---|
| 1 | 100.00 | NULL | ONLY_A |
| 2 | 250.00 | 250.00 | MATCH |
| 3 | 300.00 | 310.00 | VALUE_DIFF |
| 4 | NULL | 400.00 | ONLY_B |

Các ý quan trọng:

- `COALESCE(a.account_id,b.account_id)` hiển thị mã tài khoản từ phía có bản ghi.
- Hai khóa chính NOT NULL giúp phân biệt bản ghi **chỉ có A** hay **chỉ có B**.
- `IS DISTINCT FROM` là phép so sánh **an toàn với NULL**, hữu ích khi dữ liệu hai nguồn có thể chứa NULL ở cột cần đối chiếu.
- Không nên dùng riêng `a.balance <> b.balance` để phát hiện mọi khác biệt nếu một bên có thể NULL, vì so sánh thông thường với NULL cho UNKNOWN.

Ở ví dụ này cột `balance` được khai báo NOT NULL, nhưng `IS DISTINCT FROM` vẫn là mẫu hữu ích khi đối soát dữ liệu có khả năng thiếu giá trị.

### 14.3. Chỉ lấy bản ghi có vấn đề

```sql
WITH reconciliation AS (
    SELECT
        COALESCE(a.account_id, b.account_id) AS account_id,
        a.balance AS balance_a,
        b.balance AS balance_b,
        CASE
            WHEN a.account_id IS NULL THEN 'ONLY_B'
            WHEN b.account_id IS NULL THEN 'ONLY_A'
            WHEN a.balance IS DISTINCT FROM b.balance
                THEN 'VALUE_DIFF'
            ELSE 'MATCH'
        END AS match_status
    FROM join140.balance_source_a AS a
    FULL JOIN join140.balance_source_b AS b
        ON a.account_id = b.account_id
)
SELECT *
FROM reconciliation
WHERE match_status <> 'MATCH'
ORDER BY account_id;
```

Kết quả gồm tài khoản 1, 3 và 4.

Đây là một trường hợp mà `FULL JOIN` rất tự nhiên: ta không muốn nguồn A hoặc nguồn B được ưu tiên; cả hai danh sách đều cần được bảo toàn để phát hiện dữ liệu thiếu.

## 15. Đặt điều kiện ở đâu khi dùng RIGHT JOIN và FULL JOIN?

### 15.1. RIGHT JOIN cũng có bẫy ON/WHERE

Giả sử yêu cầu:

> “Hiển thị mọi nhân viên, kèm thông tin phòng ban **nếu phòng đó nằm ở Hồ Chí Minh**.”

Đặt điều kiện phòng ban trong `ON`:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    d.department_name,
    d.office_city
FROM join140.departments AS d
RIGHT JOIN join140.employees AS e
    ON e.department_id = d.department_id
   AND d.office_city = 'Hồ Chí Minh'
ORDER BY e.employee_id;
```

Kết quả: tất cả bốn nhân viên vẫn có mặt.

- An, Bình có phòng Kinh doanh ở Hồ Chí Minh nên ghép được.
- Chi thuộc Kỹ thuật ở Hà Nội, **không thỏa toàn bộ ON** nên cột phòng ban trong kết quả NULL.
- Dũng chưa có phòng ban nên cột phòng ban NULL.

Như vậy, cột phòng ban NULL của Chi **không có nghĩa dữ liệu gốc không có phòng ban**: đó là kết quả của **điều kiện join**.

Nếu đặt điều kiện ở `WHERE d.office_city = 'Hồ Chí Minh'`, Chi và Dũng sẽ bị loại khỏi kết quả. Một `RIGHT JOIN` lúc này không còn giữ mọi nhân viên.

### 15.2. FULL JOIN với WHERE có thể mất một hoặc cả hai phía không khớp

Ví dụ:

```sql
SELECT
    d.department_id,
    e.employee_id
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE d.office_city = 'Hồ Chí Minh'
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

Truy vấn này chỉ giữ các hàng có thông tin phòng ban thỏa điều kiện thành phố. Những hàng mà phía phòng ban NULL, như Dũng, sẽ bị loại, dù dùng `FULL JOIN`.

Do đó, khi yêu cầu “giữ đầy đủ cả hai nguồn”, mỗi bộ lọc `WHERE` sau `FULL JOIN` cần được xem xét cẩn thận.

### 15.3. Lọc những hàng không khớp ở cả hai phía

Một câu truy vấn đối soát phổ biến:

```sql
SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id AS emp_id,
    e.employee_name
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE d.department_id IS NULL
   OR e.employee_id IS NULL
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

Kết quả gồm:

| dept_id | department_name | emp_id | employee_name |
|---:|---|---:|---|
| 30 | Nhân sự | NULL | NULL |
| 40 | Hỗ trợ | NULL | NULL |
| NULL | NULL | 104 | Dũng |

Đây là **đối xứng sai khác** (*symmetric difference*) theo điều kiện nối: giữ những hàng chỉ xuất hiện ở một phía.

## 16. JOIN một-nhiều, nhiều-nhiều và việc nhân bản hàng

### 16.1. Một-nhiều

Trong dữ liệu lab, một phòng ban có thể có nhiều nhân viên. Nếu ghép phòng 10, hàng phòng ban xuất hiện hai lần, vì hai nhân viên cùng khớp.

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE d.department_id = 10
ORDER BY e.employee_id;
```

Kết quả:

```text
department_id | department_name | employee_id
--------------+-----------------+------------
10            | Kinh doanh      | 101
10            | Kinh doanh      | 102
```

Hai hàng không phải dữ liệu bị “nhân đôi sai”. Đó là **hai cặp khớp khác nhau**.

### 16.2. Nhiều-nhiều và nguy cơ nhân số hàng rất lớn

Giả sử ta nối:

```text
departments -> employees -> employee_skills
```

Một phòng có 10 nhân viên, mỗi nhân viên 5 kỹ năng thì kết quả join có thể tạo khoảng 50 hàng cho phòng đó.

Nếu câu báo cáo lại chạy `SUM(d.department_budget)` trên từng hàng sau join, ngân sách phòng có thể bị **đếm lặp** nhiều lần. Đó là một lỗi báo cáo phổ biến gọi là **fan-out multiplication**.

Giải pháp tùy tình huống:

- Gom dữ liệu một-nhiều ở subquery/CTE **trước khi nối**.
- Dùng `COUNT(DISTINCT employee_id)` khi thật sự cần đếm các nhân viên duy nhất.
- Dùng `EXISTS` cho yêu cầu chỉ kiểm tra sự tồn tại, tránh tạo bản sao kết quả.
- Xác định đúng cấp độ dữ liệu muốn báo cáo: một hàng/phòng, một hàng/nhân viên hay một hàng/kỹ năng.

**Đừng dùng `DISTINCT` như một cách che mọi lỗi join.** Nó có thể giấu việc ghép sai và làm kết quả tổng hợp khó kiểm chứng.

### 16.3. Nguy cơ thiếu điều kiện nối

Nếu viết:

```sql
SELECT *
FROM join140.departments AS d
JOIN join140.employees AS e
    ON TRUE;
```

mọi phòng ban có thể ghép với mọi nhân viên: 4 × 4 = 16 cặp trong bộ dữ liệu này. Truy vấn không được lọc theo quan hệ phòng ban.

Một phép `JOIN` chỉ có tên đúng nhưng thiếu điều kiện nghiệp vụ vẫn có thể tạo dữ liệu sai. Khi có nhiều cột khóa, hãy ghi đủ điều kiện, ví dụ cả `tenant_id` và `department_id` trong hệ thống đa khách hàng.

## 17. Gộp trước rồi LEFT JOIN: tạo một hàng cho mỗi phòng ban

Giả sử cần thống kê nhân viên nhưng không muốn phòng ban bị lặp lại.

Cách 1: `GROUP BY` sau LEFT JOIN như phần 11.

Cách 2: **Tổng hợp nhân viên trước**, rồi nối:

```sql
WITH employee_stats AS (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        SUM(monthly_salary) AS total_salary
    FROM join140.employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
)
SELECT
    d.department_id,
    d.department_name,
    COALESCE(s.employee_count, 0) AS employee_count,
    COALESCE(s.total_salary, 0) AS total_salary
FROM join140.departments AS d
LEFT JOIN employee_stats AS s
    ON s.department_id = d.department_id
ORDER BY d.department_id;
```

Kết quả:

| department_id | employee_count | total_salary |
|---:|---:|---:|
| 10 | 2 | 27000000.00 |
| 20 | 1 | 20000000.00 |
| 30 | 0 | 0 |
| 40 | 0 | 0 |

Ở đây `employee_stats` tối đa một hàng cho mỗi `department_id`, nên khi nối với `departments` sẽ tạo đúng **một hàng mỗi phòng ban**.

Mẫu này thường hữu ích khi báo cáo phải ghép nhiều bảng chi tiết: tổng hợp mỗi nguồn về cùng “grain” trước, rồi mới join để tránh nhân chéo dữ liệu.

## 18. LEFT JOIN LATERAL: lấy một bản ghi liên quan cho mỗi hàng trái

PostgreSQL hỗ trợ `LATERAL`, cho phép subquery phía sau dùng cột của hàng phía trước trong `FROM`.

Ví dụ yêu cầu:

> “Liệt kê mọi phòng ban cùng **nhân viên có lương cao nhất** của phòng đó; nếu phòng trống thì vẫn hiển thị phòng.”

```sql
SELECT
    d.department_id,
    d.department_name,
    top_employee.employee_id,
    top_employee.employee_name,
    top_employee.monthly_salary
FROM join140.departments AS d
LEFT JOIN LATERAL (
    SELECT
        e.employee_id,
        e.employee_name,
        e.monthly_salary
    FROM join140.employees AS e
    WHERE e.department_id = d.department_id
    ORDER BY e.monthly_salary DESC, e.employee_id ASC
    LIMIT 1
) AS top_employee
    ON TRUE
ORDER BY d.department_id;
```

Kết quả:

| department_id | department_name | employee_id | employee_name | monthly_salary |
|---:|---|---:|---|---:|
| 10 | Kinh doanh | 101 | An | 15000000.00 |
| 20 | Kỹ thuật | 103 | Chi | 20000000.00 |
| 30 | Nhân sự | NULL | NULL | NULL |
| 40 | Hỗ trợ | NULL | NULL | NULL |

Giải thích:

- Subquery bên phải được viết có tương quan với `d.department_id`.
- `ORDER BY ... LIMIT 1` chọn tối đa một nhân viên cho phòng hiện tại.
- `LEFT JOIN LATERAL ... ON TRUE` vẫn giữ phòng nếu subquery không trả hàng nào.
- Phòng 30 và 40 xuất hiện với các cột nhân viên NULL.

Đây là cách rất thực dụng để thực hiện **top-1 per parent**, nhưng không bắt buộc nhanh hơn mọi phương án dùng window function. Với dữ liệu lớn, chỉ mục và phân bố dữ liệu sẽ quyết định.

## 19. FULL JOIN và UNION ALL: cách hiểu bằng hai nhánh

Có thể phân tích `FULL JOIN` thành:

1. Mọi hàng của `LEFT JOIN` từ trái sang phải.
2. Thêm những hàng **chỉ có ở bảng phải**, chưa xuất hiện trong nhánh đầu.

Ví dụ minh họa tương đương với FULL JOIN của bộ dữ liệu:

```sql
SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id AS emp_id,
    e.employee_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id

UNION ALL

SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id AS emp_id,
    e.employee_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
WHERE d.department_id IS NULL

ORDER BY dept_id NULLS LAST, emp_id NULLS LAST;
```

Giải thích:

- Nhánh 1 chứa các cặp khớp và phòng ban không có nhân viên.
- Nhánh 2 chỉ chứa nhân viên không tìm được phòng ban (trong ví dụ là Dũng).
- `UNION ALL` **giữ mọi hàng**, phù hợp ngữ nghĩa bag của JOIN.
- Bộ lọc `WHERE d.department_id IS NULL` ở nhánh 2 ngăn các cặp đã có ở nhánh 1 bị thêm lại.

**Không viết hai LEFT JOIN rồi UNION ALL tất cả hàng** mà quên lọc nhóm chỉ bên phải, vì như vậy những cặp khớp có thể bị đếm hai lần.

### 19.1. Tại sao không tùy tiện đổi UNION ALL thành UNION?

`UNION` loại các hàng kết quả trùng nhau theo bộ cột được chọn. Trong những trường hợp hai hàng dữ liệu khác nhau nhưng projection giống nhau, `UNION` có thể gộp chúng và làm mất multiplicity.

Trong khi đó `FULL JOIN` không có yêu cầu mặc định phải loại bỏ những hàng có giá trị projection giống nhau.

Nếu muốn so sánh kết quả đúng theo đa tập, `UNION ALL` cùng anti-join chính xác là cách diễn giải phù hợp hơn.

### 19.2. Có nên tự thay FULL JOIN bằng UNION ALL trong production?

Không cần thiết trừ khi có lý do rõ về tương thích, kiến trúc hoặc kế hoạch truy vấn. PostgreSQL hỗ trợ `FULL JOIN` trực tiếp; cú pháp FULL JOIN thường ngắn và biểu đạt mục đích đối soát rõ ràng hơn.

Phần phân rã thành hai nhánh chủ yếu để **hiểu bản chất phép nối**, không phải quy tắc tối ưu hóa bắt buộc.

## 20. Kết hợp nhiều OUTER JOIN trong một truy vấn

Báo cáo thực tế có thể nối:

```text
departments
   LEFT JOIN employees
   LEFT JOIN employee_profiles
   LEFT JOIN attendance_records
```

Một điều quan trọng: từng phép JOIN tạo ra kết quả trung gian; mỗi JOIN sau được áp dụng trên kết quả đã có. Nếu bảng thứ ba có nhiều bản ghi cho một nhân viên, số hàng có thể tiếp tục tăng.

### 20.1. Inner join phía sau có thể loại hàng outer join đã giữ

Giả sử có thêm bảng hồ sơ nhân viên. Một câu như:

```sql
SELECT ...
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
  ON e.department_id = d.department_id
INNER JOIN employee_profiles AS p
  ON p.employee_id = e.employee_id;
```

là **mẫu minh họa**, chỉ chạy nếu bảng `employee_profiles` có tồn tại.

Vì `INNER JOIN employee_profiles` yêu cầu tìm được `e.employee_id`, những phòng ban không có nhân viên có thể bị loại khỏi kết quả cuối, dù bước đầu đã dùng `LEFT JOIN`.

Nếu mục tiêu là giữ mọi phòng ban, cần xem lại cách đặt điều kiện, loại join ở những bước tiếp theo, hoặc tổng hợp dữ liệu con trước khi nối.

### 20.2. Dùng ngoặc để làm rõ nhóm JOIN

Với nhiều outer join, vị trí của `ON` và **thứ tự ghép bảng** có thể làm thay đổi kết quả. Không phải mọi phép outer join đều có thể tự do hoán đổi và kết hợp nhóm giống inner join.

Có thể dùng ngoặc:

```sql
FROM table_a AS a
LEFT JOIN (
    table_b AS b
    INNER JOIN table_c AS c
      ON c.b_id = b.id
) ON b.a_id = a.id
```

Đây là mẫu cú pháp, các bảng cụ thể cần tồn tại. Ngoặc giúp người đọc biết bảng B và C được ghép nội bộ trước khi toàn bộ nhóm được nối bảo toàn với A theo ngữ nghĩa câu truy vấn.

## 21. WHERE, GROUP BY, HAVING và ORDER BY trong OUTER JOIN

### 21.1. Thứ tự hiển thị không tự được bảo đảm

Dù câu `LEFT JOIN` có vẻ trả các phòng ban theo thứ tự bảng vật lý, SQL **không bảo đảm thứ tự** nếu thiếu `ORDER BY`.

```sql
SELECT d.department_id, e.employee_id
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

Khi cần phân trang, báo cáo hoặc kết quả ổn định để kiểm thử, luôn định nghĩa cách sắp xếp phù hợp.

### 21.2. NULLS FIRST và NULLS LAST

PostgreSQL hỗ trợ:

```sql
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

Điều này rất hữu ích cho FULL JOIN khi một phía không khớp làm khóa của phía kia NULL. Không nên mặc định NULL luôn đứng ở đầu hay cuối cho mọi chiều sort.

### 21.3. HAVING để tìm phòng trống

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(e.employee_id) = 0
ORDER BY d.department_id;
```

Kết quả: phòng 30 và 40.

Khác với `WHERE`, `HAVING` lọc **nhóm sau tổng hợp**. Khi bài toán là “những phòng có số nhân viên bằng 0”, `HAVING COUNT(...) = 0` là một cách diễn đạt phù hợp.

### 21.4. Đếm chỉ phòng có ít nhất hai nhân viên

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(e.employee_id) >= 2;
```

Kết quả: chỉ phòng Kinh doanh, có 2 nhân viên.

## 22. JOIN và khóa ngoại: liên quan nhưng không thay thế nhau

Trong schema lab:

```sql
employees.department_id
    REFERENCES departments.department_id
```

Khóa ngoại bảo đảm một nhân viên có `department_id` khác NULL phải tham chiếu một phòng ban tồn tại.

Nhưng khóa ngoại không buộc **mọi nhân viên phải có phòng ban**, vì cột cho phép NULL. Vì vậy Dũng không khớp với phòng nào trong JOIN.

Nếu yêu cầu mới là “mọi nhân viên bắt buộc thuộc một phòng ban”, có thể thay mô hình để cột `department_id` là `NOT NULL` và có khóa ngoại; khi đó dữ liệu hợp lệ sẽ không có nhân viên bỏ trống phòng ban.

**Tuy nhiên, ngay cả khi khóa ngoại luôn hợp lệ, LEFT JOIN từ phòng ban sang nhân viên vẫn cần thiết** nếu phòng ban được phép tồn tại mà không có nhân viên.

### 22.1. Những hàng không khớp không phải lúc nào là dữ liệu lỗi

- Phòng ban chưa tuyển nhân viên: có thể **hoàn toàn hợp lệ**.
- Nhân viên chưa phân công phòng ban: có thể **trạng thái chuyển tiếp hợp lệ**.
- Bản ghi đơn hàng không có khách hàng trong bảng staging: có thể là **dữ liệu cần điều tra**.
- Hai nguồn đối soát thiếu một tài khoản: có thể là **sự sai lệch cần xử lý**.

Outer join cho ta biết **có hoặc không có đối tác**, không tự đánh giá tình trạng đó đúng hay sai về nghiệp vụ.

## 23. Hiệu năng outer join trong PostgreSQL

Một outer join không tự động chậm hơn inner join, cũng không tự động nhanh hơn. Hiệu năng phụ thuộc lượng dữ liệu, điều kiện nối, độ chọn lọc, chỉ mục, thống kê và số hàng trả ra.

### 23.1. Xem kế hoạch bằng EXPLAIN

```sql
EXPLAIN
SELECT
    d.department_id,
    d.department_name,
    e.employee_id
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
```

PostgreSQL có thể sử dụng các chiến lược như:

- **Nested Loop Join**: duyệt một nguồn và tìm các hàng liên quan từ nguồn còn lại.
- **Hash Join**: xây bảng băm và ghép dựa trên điều kiện phù hợp.
- **Merge Join**: ghép các nguồn theo thứ tự khóa phù hợp.

Trong output plan có thể thấy các nhãn như `Hash Left Join`, `Merge Left Join` hoặc dạng kế hoạch đã được optimizer biến đổi. Với dữ liệu nhỏ, sequential scan có thể là lựa chọn rẻ nhất.

**Không suy luận hiệu năng chỉ từ từ khóa LEFT/RIGHT/FULL trong SQL.** Hãy đọc actual plan và số hàng tại các node khi cần tối ưu.

### 23.2. Chỉ mục trên khóa ngoại

PostgreSQL tạo index phù hợp để thực thi primary key/unique constraints. Nhưng **không tự tạo index trên mọi cột khóa ngoại ở bảng con**.

Với bảng `employees`, có thể cân nhắc:

```sql
CREATE INDEX idx_join140_employees_department
ON join140.employees(department_id);
```

Index này có thể hữu ích cho:

- Tra cứu nhân viên theo phòng ban.
- Một số chiến lược join từ phòng ban sang nhân viên.
- Kiểm tra hoặc xử lý các thay đổi có liên quan đến khóa ngoại ở bảng cha.

Tuy nhiên, tạo index cũng tăng dung lượng và chi phí ghi. Trên bảng nhỏ, planner có thể vẫn chọn sequential scan.

### 23.3. EXPLAIN ANALYZE có thực sự chạy truy vấn không?

Có. Với bài đọc dữ liệu lab:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    d.department_id,
    COUNT(e.employee_id)
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id;
```

`EXPLAIN ANALYZE` thực thi query để đo số hàng và thời gian thực tế. Với `SELECT` chỉ đọc như trên thì phù hợp cho lab; với `UPDATE`, `DELETE` hoặc câu lệnh có side effect, cần biện pháp bảo vệ transaction và môi trường trước khi chạy.

### 23.4. Thống kê và cardinality ước tính

Optimizer dựa vào thống kê để chọn plan. Nếu phân bố dữ liệu thay đổi mạnh sau bulk load, DBA hoặc quy trình bảo trì có thể cần `ANALYZE` theo chính sách vận hành.

Ví dụ trong lab:

```sql
ANALYZE join140.departments;
ANALYZE join140.employees;
```

Đây là thao tác cập nhật thống kê, không phải kiểm thử dữ liệu hay phương tiện bảo đảm mọi JOIN đều có plan tối ưu. Trên production cần đánh giá thời điểm và chi phí.

### 23.5. Tối ưu số hàng đầu ra

Nếu báo cáo chỉ cần biết một phòng ban **có nhân viên hay không**, không cần trả mọi nhân viên rồi dùng `DISTINCT`.

Có thể dùng:

```sql
SELECT
    d.department_id,
    d.department_name,
    EXISTS (
        SELECT 1
        FROM join140.employees AS e
        WHERE e.department_id = d.department_id
    ) AS has_employees
FROM join140.departments AS d
ORDER BY d.department_id;
```

Kết quả có **đúng một hàng mỗi phòng ban**, tránh nhân số hàng từ quan hệ một-nhiều.

## 24. Đối chiếu OUTER JOIN với các phép tập hợp

Người mới học thường nghe:

- INNER là giao.
- LEFT là phần trái và giao.
- FULL là hợp.

Đó là trực giác dễ nhớ, nhưng **chưa đầy đủ** vì SQL join hoạt động trên hàng và cặp hàng, không chỉ là phép hợp/tách giữa hai danh sách ID.

### 24.1. JOIN tạo cặp hàng, UNION gộp các hàng cùng cấu trúc

`JOIN` mở rộng số cột bằng cách kết hợp cột từ hai nguồn theo điều kiện.

`UNION` hoặc `UNION ALL` **xếp chồng hàng** của hai câu SELECT có số cột và kiểu tương thích.

Ví dụ:

```sql
SELECT employee_id, employee_name
FROM join140.employees
WHERE is_active = TRUE

UNION ALL

SELECT employee_id, employee_name
FROM join140.employees
WHERE is_active = FALSE;
```

Đây là gộp hai danh sách nhân viên theo hàng, **không** phải join với phòng ban.

### 24.2. LEFT/RIGHT/FULL không tự bỏ trùng

Nếu hai nhân viên có cùng tên, khi SELECT chỉ cột `employee_name`, có thể có nhiều hàng giá trị giống nhau dù đó là hai nhân viên khác. Outer join không tự dùng `DISTINCT`.

Muốn gộp hoặc đếm duy nhất theo khóa nào cần quyết định dựa trên nghiệp vụ, không phải vì kết quả hiển thị có hàng lặp.

## 25. Các lỗi thường gặp khi sử dụng LEFT, RIGHT và FULL JOIN

### Lỗi 1. Viết LEFT JOIN nhưng lọc bảng phải trong WHERE

```sql
SELECT ...
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE e.is_active = TRUE;
```

Điều này làm mất phòng không có nhân viên hoạt động.

**Cách sửa khi muốn giữ mọi phòng:**

```sql
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
   AND e.is_active = TRUE
```

### Lỗi 2. Đếm phòng trống bằng COUNT(*)

Vì hàng null-extended vẫn tồn tại, `COUNT(*)` đếm 1 cho phòng trống.

**Cách sửa:** `COUNT(e.employee_id)` nếu `employee_id` là khóa chính NOT NULL.

### Lỗi 3. Lọc không khớp bằng một cột có thể NULL

```sql
WHERE e.some_optional_value IS NULL
```

Có thể chọn cả hàng nhân viên đã khớp nhưng cột optional bị NULL.

**Cách sửa:** dùng `e.employee_id IS NULL` hoặc `NOT EXISTS` để xác định không có đối tác.

### Lỗi 4. Đảo bảng nhưng không xét hướng JOIN

`departments LEFT JOIN employees` giữ phòng ban; `employees LEFT JOIN departments` giữ nhân viên. Hai câu không cùng yêu cầu.

**Cách sửa:** viết câu hỏi “đối tượng nào bắt buộc xuất hiện?” trước khi chọn bảng trái.

### Lỗi 5. Tưởng RIGHT JOIN luôn cần thiết để giữ bảng phải

Nó có thể được viết lại bằng `LEFT JOIN` sau khi đảo vị trí hai bảng.

**Cách sửa:** chọn cách diễn đạt dễ đọc, không mặc định một hướng có ưu thế hiệu năng.

### Lỗi 6. Tưởng FULL JOIN là CROSS JOIN

`FULL JOIN` giữ cặp khớp và hàng không khớp; `CROSS JOIN` tạo mọi cặp giữa hai bảng.

**Cách sửa:** luôn xác định điều kiện `ON` và đối tượng đang ghép.

### Lỗi 7. Quên NULL trong điều kiện nối

`NULL = NULL` trả UNKNOWN, không phải TRUE. Một nhân viên có `department_id NULL` không tự khớp với “phòng ban NULL”.

**Cách sửa:** định nghĩa khóa rõ ràng; dùng `IS NULL` để tìm giá trị thiếu, và chỉ dùng null-safe comparison khi thực sự có ngữ nghĩa nghiệp vụ.

### Lỗi 8. Dùng NOT IN với subquery có NULL

`NOT IN` có thể không trả hàng mong muốn do logic UNKNOWN.

**Cách sửa:** ưu tiên `NOT EXISTS` hoặc LEFT anti-join khi tìm các bản ghi không có liên kết.

### Lỗi 9. Không xét bản chất một-nhiều

Một phòng ban có 10 nhân viên tạo 10 hàng khi LEFT JOIN, không phải một hàng.

**Cách sửa:** tổng hợp, EXISTS, hoặc lựa chọn một nhân viên bằng LATERAL/window function tùy yêu cầu.

### Lỗi 10. Bỏ ORDER BY

Kết quả hiển thị có thể thay đổi thứ tự khi PostgreSQL đổi kế hoạch truy vấn.

**Cách sửa:** thêm `ORDER BY` rõ ràng, cân nhắc `NULLS FIRST/LAST`.

### Lỗi 11. Dùng DISTINCT để che lỗi join

`DISTINCT` có thể làm mất các bản ghi hợp lệ khác nhau nhưng cùng projection, và không sửa quan hệ nối sai.

**Cách sửa:** kiểm tra khóa, điều kiện `ON`, cardinality trước khi quyết định cần loại trùng.

### Lỗi 12. Nối tiếp INNER JOIN làm mất hàng được bảo toàn

`LEFT JOIN` đầu tiên giữ phòng trống, nhưng `INNER JOIN` tiếp theo dựa trên cột nhân viên sẽ loại phòng trống.

**Cách sửa:** phân tích toàn chuỗi join và vị trí bộ lọc, không chỉ câu JOIN đầu tiên.

### Lỗi 13. Dùng FULL JOIN và thêm WHERE chỉ trên một phía

Điều kiện trên bảng trái có thể loại những hàng chỉ có bên phải; khi đó báo cáo không còn phản ánh đầy đủ hai nguồn.

**Cách sửa:** xác định mục tiêu đối soát, đặt điều kiện đúng phạm vi hoặc đưa điều kiện vào subquery/CTE của từng nguồn trước khi FULL JOIN.

### Lỗi 14. Nối sai cột khóa cùng tên

Một hệ thống đa tenant có thể có cùng `department_id` trong hai tenant khác nhau. Nếu chỉ nối theo `department_id`, dữ liệu có thể bị ghép sai tenant.

**Cách sửa:** dùng đủ khóa nghiệp vụ, ví dụ:

```sql
ON e.tenant_id = d.tenant_id
AND e.department_id = d.department_id
```

Cần kết hợp điều kiện nối đúng với phân quyền/RLS khi dữ liệu có nhiều tenant.

## 26. Thực hành tổng hợp: từ yêu cầu nghiệp vụ tới câu SQL

Dưới đây là các yêu cầu thường gặp. Mỗi câu sử dụng đúng dữ liệu lab đã tạo.

### Bài thực hành A. Mọi phòng ban và tên nhân viên, nếu có

```sql
SELECT
    d.department_name,
    e.employee_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

**Đáp án:** 5 hàng, bao gồm phòng Nhân sự và Hỗ trợ với tên nhân viên NULL.

### Bài thực hành B. Mọi nhân viên và tên phòng ban, nếu có

```sql
SELECT
    e.employee_name,
    d.department_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

**Đáp án:** 4 hàng, bao gồm Dũng với tên phòng ban NULL.

### Bài thực hành C. Cùng yêu cầu B nhưng dùng RIGHT JOIN

```sql
SELECT
    e.employee_name,
    d.department_name
FROM join140.departments AS d
RIGHT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

**Đáp án:** giống B.

### Bài thực hành D. Tất cả phòng ban và tất cả nhân viên

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

**Đáp án:** 6 hàng gồm ba cặp khớp, hai phòng trống và một nhân viên chưa có phòng.

### Bài thực hành E. Chỉ phòng ban chưa có nhân viên

```sql
SELECT
    d.department_id,
    d.department_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
```

**Đáp án:** phòng 30 và 40.

### Bài thực hành F. Phòng ban chưa có nhân viên đang hoạt động

```sql
SELECT
    d.department_id,
    d.department_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
   AND e.is_active = TRUE
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
```

**Đáp án:** phòng 20, 30 và 40.

Phòng 20 có Chi nhưng Chi không hoạt động, nên phòng 20 cũng thỏa yêu cầu “không có nhân viên **đang hoạt động**”.

### Bài thực hành G. Chỉ các nhân viên chưa được phân phòng

```sql
SELECT
    e.employee_id,
    e.employee_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
WHERE d.department_id IS NULL;
```

**Đáp án:** Dũng (104).

### Bài thực hành H. Số nhân viên trong mỗi phòng

```sql
SELECT
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

**Đáp án:** Kinh doanh 2; Kỹ thuật 1; Nhân sự 0; Hỗ trợ 0.

### Bài thực hành I. Tổng lương của mọi phòng ban

```sql
SELECT
    d.department_name,
    COALESCE(SUM(e.monthly_salary), 0) AS payroll
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

**Đáp án:** Kinh doanh 27 triệu, Kỹ thuật 20 triệu, Nhân sự 0, Hỗ trợ 0 (theo đơn vị tiền của dữ liệu lab).

### Bài thực hành J. Chỉ các hàng không khớp ở một trong hai phía

```sql
SELECT
    d.department_id AS dept_id,
    e.employee_id AS emp_id
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE d.department_id IS NULL
   OR e.employee_id IS NULL
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

**Đáp án:** `(30,NULL)`, `(40,NULL)` và `(NULL,104)`.

### Bài thực hành K. Phòng ban có ít nhất hai nhân viên

```sql
SELECT d.department_id, d.department_name,
       COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(e.employee_id) >= 2;
```

**Đáp án:** phòng 10 — Kinh doanh.

### Bài thực hành L. Với mỗi phòng, chọn nhân viên có lương cao nhất

Dùng `LEFT JOIN LATERAL` như phần 18.

**Đáp án:** phòng 10 → An; phòng 20 → Chi; phòng 30/40 → NULL.

## 27. Câu hỏi tự đánh giá có lời giải

### Câu 1. LEFT JOIN có luôn trả số hàng bằng bảng trái?

**Không.** Nó giữ ít nhất một hàng kết quả cho mỗi hàng trái khi chưa có bộ lọc loại bỏ; nếu một hàng trái khớp nhiều hàng phải, nó xuất hiện nhiều lần.

### Câu 2. LEFT JOIN và RIGHT JOIN có khác khả năng biểu đạt?

**Không.** `A RIGHT JOIN B` có thể viết thành `B LEFT JOIN A` với cùng điều kiện và phép chọn cột phù hợp.

### Câu 3. FULL JOIN với hai bảng không có cặp nào khớp trả gì?

Trả tất cả hàng trái (các cột phải NULL) **và** tất cả hàng phải (các cột trái NULL), trừ khi có bộ lọc cuối làm mất hàng.

### Câu 4. FULL JOIN có tự loại hàng trùng không?

**Không.** Nó giữ các cặp khớp theo bag semantics. Không mặc định có `DISTINCT`.

### Câu 5. Vì sao `WHERE e.is_active = TRUE` có thể khiến LEFT JOIN mất phòng trống?

Vì cột `e.is_active` của hàng null-extended là NULL; phép so sánh cho UNKNOWN và bị `WHERE` loại.

### Câu 6. Nếu muốn mọi phòng và chỉ những nhân viên active, lọc ở đâu?

Thường đặt `AND e.is_active = TRUE` trong `ON` để giữ các phòng không có nhân viên active.

### Câu 7. Đếm nhân viên bằng COUNT(*) hay COUNT(e.employee_id)?

Dùng `COUNT(e.employee_id)` để đếm các hàng nhân viên thực sự khớp. `COUNT(*)` còn đếm hàng NULL mở rộng của phòng trống.

### Câu 8. Tìm phòng chưa có nhân viên bằng cú pháp nào?

`LEFT JOIN ... WHERE e.employee_id IS NULL` hoặc `NOT EXISTS (...)`.

### Câu 9. Vì sao `NOT IN` có thể nguy hiểm với nullable key?

Nếu subquery trả NULL, so sánh `NOT IN` có thể thành UNKNOWN và không trả những bản ghi mong đợi.

### Câu 10. Vì sao ghép theo khóa không unique có thể tăng số hàng?

Vì mỗi hàng trái có thể khớp nhiều hàng phải và ngược lại, tạo nhiều cặp khác nhau. Cần hiểu cardinality và ràng buộc khóa.

### Câu 11. Khi đối soát hai nguồn, vì sao FULL JOIN thường phù hợp?

Vì nó giữ cả bản ghi có ở hai phía lẫn bản ghi chỉ có ở từng phía, giúp phân loại MATCHED/ONLY_A/ONLY_B.

### Câu 12. Outer join có tự bảo đảm thứ tự kết quả không?

**Không.** Dùng `ORDER BY` và xét `NULLS FIRST/LAST` nếu cần đầu ra ổn định.

## 28. Bảng tra cứu nhanh

| Tình huống | Mẫu SQL | Điều cần nhớ |
|---|---|---|
| Chỉ cặp khớp | `A INNER JOIN B ON ...` | Hàng không khớp bị loại |
| Giữ mọi A | `A LEFT JOIN B ON ...` | B có thể NULL |
| Giữ mọi B | `A RIGHT JOIN B ON ...` | A có thể NULL |
| Giữ cả A và B | `A FULL JOIN B ON ...` | Hai phía đều có thể NULL |
| Viết lại RIGHT | `B LEFT JOIN A ON ...` | Giữ ngữ nghĩa và cột đã chọn |
| Lọc B nhưng vẫn giữ mọi A | `LEFT JOIN B ON ... AND B.flag = ...` | Không đặt bừa ở WHERE |
| Chỉ A không khớp B | `A LEFT JOIN B ON ... WHERE B.pk IS NULL` | `B.pk` phải NOT NULL ở hàng thật |
| Anti-join thay thế | `WHERE NOT EXISTS (SELECT 1 FROM B WHERE ...)` | Tránh bẫy NULL của NOT IN |
| Đếm B theo mọi A | `COUNT(B.pk)` sau `LEFT JOIN` | Phòng trống trả 0 |
| Đếm có điều kiện | `COUNT(B.pk) FILTER (WHERE ...)` | Giữ logic aggregate rõ ràng |
| Tổng hợp có nhóm trống | `COALESCE(SUM(B.value), 0)` | NULL và 0 là hai ngữ nghĩa |
| Phân loại FULL | `CASE WHEN A.pk IS NULL ...` | Dùng khóa NOT NULL |
| Đồng nhất khóa báo cáo | `COALESCE(A.id, B.id)` | Chỉ chọn giá trị có mặt |
| Hai bảng có cột khóa cùng tên | `JOIN ... USING (key)` | Cột USING xuất hiện một lần khi SELECT * |
| Tìm top-1 bên phải mỗi A | `LEFT JOIN LATERAL (...) ON TRUE` | Giữ A khi subquery không có hàng |
| Xem kế hoạch | `EXPLAIN SELECT ...` | Planner có thể biến đổi join |
| Đo thực thi SELECT | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` | ANALYZE thực thi câu SQL |
| Xem thứ tự có NULL | `ORDER BY key NULLS LAST` | JOIN không bảo đảm thứ tự |
| Tránh nhân số hàng | Tổng hợp trước khi JOIN / EXISTS | Chọn đúng mức chi tiết dữ liệu |

## 29. Tổng kết

Ba phép nối ngoài của PostgreSQL khác nhau ở **phía nào được bảo toàn**:

```sql
-- Giữ tất cả phòng ban:
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
  ON e.department_id = d.department_id

-- Giữ tất cả nhân viên:
FROM join140.departments AS d
RIGHT JOIN join140.employees AS e
  ON e.department_id = d.department_id

-- Giữ tất cả hai phía:
FROM join140.departments AS d
FULL JOIN join140.employees AS e
  ON e.department_id = d.department_id
```

Khi viết và đọc câu truy vấn, hãy tự hỏi theo thứ tự:

1. **Đối tượng nào phải xuất hiện đầy đủ?** Chọn LEFT, RIGHT hay FULL theo phía cần giữ.
2. **Hai hàng được coi là khớp khi nào?** Định nghĩa đầy đủ điều kiện `ON` hoặc `USING`.
3. **Có hàng một-nhiều không?** Đừng nhầm số hàng join với số bản ghi của bảng trái.
4. **Bộ lọc ở ON hay WHERE?** Điều kiện trên phía không được bảo toàn có thể loại hàng NULL mở rộng.
5. **NULL được hiểu thế nào?** Dùng khóa chính NOT NULL để phát hiện không khớp, đừng dùng `= NULL`.
6. **Cần đếm, tổng hợp hay đối soát?** Dùng `COUNT(B.pk)`, `COALESCE`, `CASE`, `NOT EXISTS` và `FULL JOIN` đúng mục tiêu.
7. **Kết quả phải có thứ tự cố định không?** Bổ sung `ORDER BY`.
8. **Hiệu năng có thật sự là vấn đề không?** Kiểm tra số hàng, index và kế hoạch `EXPLAIN` thay vì đoán theo tên loại JOIN.

**Điểm cốt lõi:** `LEFT JOIN` giữ tất cả hàng bên trái; `RIGHT JOIN` giữ tất cả hàng bên phải; `FULL JOIN` giữ những hàng khớp và không khớp từ cả hai phía. Hiểu sâu `ON`, `WHERE`, `NULL` và cardinality sẽ giúp bạn viết các báo cáo PostgreSQL chính xác ngay cả khi quan hệ giữa các bảng không đầy đủ.


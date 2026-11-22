# NULL trong DISTINCT, GROUP BY, ORDER BY và ràng buộc UNIQUE

Trong SQL, `NULL` biểu thị một giá trị **không hiện diện hoặc chưa được xác định** theo cách hiểu của từng cột. Vì vậy, nó không phải số `0`, chuỗi rỗng `''` hay một giá trị thông thường có thể so sánh bằng dấu `=`. Điều dễ gây nhầm lẫn là **cùng một `NULL` nhưng các thao tác SQL có quy tắc xử lý khác nhau**:

- `DISTINCT` loại dòng trùng và chỉ giữ một đại diện cho các giá trị `NULL` tương ứng.
- `GROUP BY` xếp các dòng có giá trị khóa nhóm `NULL` vào cùng một nhóm.
- `ORDER BY` vẫn sắp được dòng có `NULL`, nhưng vị trí mặc định ở đầu hay cuối phụ thuộc hệ quản trị.
- `UNIQUE` kiểm soát giá trị trùng trong dữ liệu lưu trữ, nhưng quy tắc chấp nhận nhiều `NULL` khác nhau giữa các hệ quản trị và có cả tùy chọn thay đổi hành vi.

Bài học này làm rõ lý do của từng hành vi, cung cấp bảng dữ liệu và truy vấn cụ thể, đồng thời chỉ ra những sai lầm thường gặp khi thiết kế báo cáo và ràng buộc dữ liệu.

> Các truy vấn minh họa chính dùng **PostgreSQL**. `SELECT DISTINCT` và `GROUP BY` có nguyên tắc chung theo SQL; riêng thứ tự mặc định của `NULL` và hành vi `UNIQUE` cần xem đúng DBMS, phiên bản và cấu hình khi áp dụng.

## 1. Nền tảng: `NULL` không tham gia so sánh như một giá trị thường

Trong SQL, phép so sánh với `NULL` thường cho kết quả **UNKNOWN** (không xác định), không phải `TRUE` hoặc `FALSE`:

| Biểu thức | Kết quả trong logic SQL | Ý nghĩa |
|---|---|---|
| `5 = 5` | `TRUE` | Hai giá trị xác định bằng nhau |
| `5 = NULL` | `UNKNOWN` | Không thể kết luận bằng nhau |
| `NULL = NULL` | `UNKNOWN` | Không thể kết luận hai giá trị thiếu là bằng nhau |
| `NULL <> NULL` | `UNKNOWN` | Cũng không thể kết luận khác nhau |
| `NULL IS NULL` | `TRUE` | Kiểm tra có thiếu giá trị hay không |
| `5 IS NULL` | `FALSE` | Giá trị `5` không phải `NULL` |
| `NULL IS NOT DISTINCT FROM NULL` | `TRUE` | So sánh theo quy tắc “không phân biệt”, coi hai `NULL` tương ứng là cùng nhóm |
| `5 IS DISTINCT FROM NULL` | `TRUE` | Một giá trị xác định và một `NULL` được xem là khác biệt |

Hai toán tử `IS DISTINCT FROM` và `IS NOT DISTINCT FROM` được PostgreSQL hỗ trợ và có trong các môi trường SQL khác, nhưng mức hỗ trợ/cú pháp khác nhau theo DBMS.

Ví dụ PostgreSQL:

```sql
SELECT
    CAST(NULL AS INTEGER) = CAST(NULL AS INTEGER) AS equal_result,
    CAST(NULL AS INTEGER) IS NOT DISTINCT FROM CAST(NULL AS INTEGER)
        AS not_distinct_result;
```

Kết quả: `equal_result` là SQL `NULL` (đại diện `UNKNOWN`), còn `not_distinct_result` là `TRUE`.

Điểm mấu chốt: **quy tắc phát hiện giá trị trùng của `DISTINCT`, nhóm của `GROUP BY` và chính sách `UNIQUE` không đơn giản là chạy điều kiện `a = b` cho từng dòng**. Do đó, không có mâu thuẫn khi `NULL = NULL` không trả về `TRUE` nhưng hai dòng có `NULL` vẫn có thể cùng nhóm.

## 2. Dữ liệu minh họa xuyên suốt

Tạo một bảng nhân viên mẫu. Cột `department` có phòng ban chưa biết; `email` có địa chỉ chưa được cung cấp; `bonus` có khoản thưởng chưa xác định. Bảng tạm sau chỉ tồn tại trong phiên làm việc PostgreSQL hiện tại:

```sql
CREATE TEMP TABLE demo_employees (
    employee_id INTEGER PRIMARY KEY,
    department VARCHAR(30),
    email VARCHAR(255),
    bonus NUMERIC(12, 2)
);

INSERT INTO demo_employees (employee_id, department, email, bonus)
VALUES
    (1, 'Sales', 'alice@example.test',   1000.00),
    (2, 'Sales', NULL,                   NULL),
    (3, 'HR',    'bob@example.test',      800.00),
    (4, NULL,    NULL,                   200.00),
    (5, NULL,    NULL,                   NULL),
    (6, 'IT',    'charlie@example.test',  900.00),
    (7, 'Sales', 'diana@example.test',   1000.00),
    (8, 'HR',    NULL,                    800.00);
```

Dữ liệu:

| employee_id | department | email | bonus |
|---:|---|---|---:|
| 1 | Sales | alice@example.test | 1000.00 |
| 2 | Sales | `NULL` | `NULL` |
| 3 | HR | bob@example.test | 800.00 |
| 4 | `NULL` | `NULL` | 200.00 |
| 5 | `NULL` | `NULL` | `NULL` |
| 6 | IT | charlie@example.test | 900.00 |
| 7 | Sales | diana@example.test | 1000.00 |
| 8 | HR | `NULL` | 800.00 |

Có **8 dòng**, trong đó **2 dòng có `department IS NULL`**, **4 dòng có `email IS NULL`** và **2 dòng có `bonus IS NULL`**. Các giá trị lặp cố ý giúp quan sát rõ từng phép toán.

Một thao tác cơ bản trước khi đi sâu:

```sql
-- Trả về các nhân viên chưa xác định phòng ban.
SELECT employee_id
FROM demo_employees
WHERE department IS NULL
ORDER BY employee_id;
-- 4, 5

-- Sai về ý nghĩa: = NULL cho UNKNOWN nên WHERE không chọn dòng nào.
SELECT employee_id
FROM demo_employees
WHERE department = NULL;
```

Trong `WHERE`, chỉ dòng có điều kiện đánh giá thành `TRUE` mới được giữ; `FALSE` và `UNKNOWN` đều bị loại.

## 3. `DISTINCT`: nhiều `NULL` được gộp thành một đại diện

`DISTINCT` trong `SELECT` loại bỏ các **dòng kết quả trùng nhau** sau khi tính các biểu thức trong danh sách chọn. Khi xác định trùng cho mục đích này, hai giá trị `NULL` ở cùng vị trí được coi là **không phân biệt** với nhau.

### 3.1. Một cột

```sql
SELECT DISTINCT department
FROM demo_employees
ORDER BY department NULLS LAST;
```

Có **4 dòng kết quả**: `HR`, `IT`, `Sales` và **một** dòng `NULL`. Bảng nguồn có hai nhân viên chưa biết phòng ban, nhưng `DISTINCT` không trả ra hai dòng `NULL` giống nhau.

Không được hiểu điều này là phép so sánh `NULL = NULL` đã trở thành `TRUE`. Hai cơ chế có ngữ nghĩa khác nhau: `=` áp dụng logic ba giá trị; `DISTINCT` sử dụng quy tắc xác định dòng trùng để loại bản sao.

### 3.2. Nhiều cột: xét toàn bộ bộ giá trị

```sql
SELECT DISTINCT department, bonus
FROM demo_employees;
```

Có **6 tổ hợp khác nhau**:

| department | bonus | Các dòng nguồn |
|---|---:|---|
| Sales | 1000.00 | 1, 7 |
| Sales | `NULL` | 2 |
| HR | 800.00 | 3, 8 |
| `NULL` | 200.00 | 4 |
| `NULL` | `NULL` | 5 |
| IT | 900.00 | 6 |

Hai dòng chỉ bị gộp nếu **tất cả biểu thức được chọn** tương ứng không phân biệt nhau. Ví dụ, hai dòng `(Sales, 1000)` chỉ cho một dòng kết quả, nhưng `(NULL, 200)` và `(NULL, NULL)` vẫn là hai tổ hợp khác nhau vì giá trị `bonus` khác.

Nếu thêm `employee_id` vào `SELECT DISTINCT`, cả 8 dòng sẽ còn lại vì khóa định danh của mỗi nhân viên đều khác nhau.

### 3.3. `DISTINCT` và `COUNT(DISTINCT ...)` có kết quả khác nhau

Hai truy vấn sau trả lời **hai câu hỏi khác nhau**:

```sql
-- Các giá trị phòng ban xuất hiện, kể cả trường hợp chưa biết.
SELECT DISTINCT department
FROM demo_employees;

-- Đếm số giá trị phòng ban KHÁC NULL xuất hiện.
SELECT COUNT(DISTINCT department) AS known_department_count
FROM demo_employees;
```

Truy vấn thứ nhất trả về **4 dòng** vì có một đại diện `NULL`. Truy vấn thứ hai trả về **3** vì `COUNT(expression)` bỏ qua `NULL`; cùng nguyên tắc đó, `COUNT(DISTINCT expression)` đếm các giá trị **khác `NULL`** sau khi loại trùng.

Đối chiếu các phép đếm:

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(department) AS known_department_rows,
    COUNT(DISTINCT department) AS known_department_values,
    COUNT(bonus) AS known_bonus_rows,
    COUNT(DISTINCT bonus) AS known_bonus_values
FROM demo_employees;
```

| all_rows | known_department_rows | known_department_values | known_bonus_rows | known_bonus_values |
|---:|---:|---:|---:|---:|
| 8 | 6 | 3 | 6 | 4 |

Khi viết báo cáo, hãy phân biệt “**bao nhiêu phòng ban đã biết**” (`COUNT(DISTINCT department) = 3`) với “**bao nhiêu loại kết quả nếu xem chưa biết là một nhóm riêng**” (4). Đừng thay chúng cho nhau.

Nếu cần đếm các nhóm bao gồm `NULL`, có thể đếm số dòng trong một truy vấn `SELECT DISTINCT`:

```sql
SELECT COUNT(*) AS department_groups_including_null
FROM (
    SELECT DISTINCT department
    FROM demo_employees
) AS d;
-- 4
```

## 4. `GROUP BY`: các khóa nhóm `NULL` thuộc cùng một nhóm

`GROUP BY` gom các dòng có khóa nhóm **không phân biệt nhau** rồi tính các hàm tổng hợp. Nếu một cột làm khóa nhóm và có nhiều dòng `NULL`, các dòng đó cùng một nhóm, thay vì mỗi `NULL` tạo nhóm riêng.

```sql
SELECT
    department,
    COUNT(*) AS employees,
    COUNT(bonus) AS employees_with_known_bonus,
    SUM(bonus) AS total_known_bonus
FROM demo_employees
GROUP BY department
ORDER BY department NULLS LAST;
```

| department | employees | employees_with_known_bonus | total_known_bonus |
|---|---:|---:|---:|
| HR | 2 | 2 | 1600.00 |
| IT | 1 | 1 | 900.00 |
| Sales | 3 | 2 | 2000.00 |
| `NULL` | 2 | 1 | 200.00 |

Nhóm `NULL` có hai nhân viên (ID 4 và 5). `COUNT(*)` đếm cả hai; `COUNT(bonus)` chỉ đếm dòng có thưởng khác `NULL`; `SUM(bonus)` bỏ qua giá trị thưởng `NULL` trong phép cộng.

**Lưu ý quan trọng về tổng hợp:** `SUM`/`AVG`/`MIN`/`MAX` bỏ qua `NULL` khi xử lý các giá trị không thiếu; nếu không có giá trị khác `NULL` để tổng hợp, `SUM` và `AVG` trả về `NULL`, không mặc định là `0`. Trong khi đó, `COUNT(*)` đếm số dòng và `COUNT(cột)` đếm số giá trị khác `NULL`.

### 4.1. Nhóm theo nhiều cột

```sql
SELECT department, bonus, COUNT(*) AS employees
FROM demo_employees
GROUP BY department, bonus;
```

Truy vấn có **6 nhóm**, tương ứng với 6 tổ hợp trong ví dụ `SELECT DISTINCT department, bonus`. Khi nhóm nhiều cột, mỗi vị trí tương ứng đều được so sánh theo quy tắc nhóm. Vì vậy:

- `(Sales, 1000)` có 2 dòng.
- `(Sales, NULL)` có 1 dòng.
- `(HR, 800)` có 2 dòng.
- `(NULL, 200)` và `(NULL, NULL)` là **hai nhóm khác nhau**.
- `(IT, 900)` có 1 dòng.

`GROUP BY` gom dòng để tính toán; `DISTINCT` chỉ bỏ dòng kết quả trùng. Chúng có thể tạo cùng số nhóm/giá trị phân biệt trong trường hợp đơn giản, nhưng không phải hai cú pháp hoàn toàn thay thế nhau.

### 4.2. Lọc nhóm `NULL`

Dùng `IS NULL` trong `WHERE` nếu chỉ muốn tổng hợp dòng chưa biết phòng ban:

```sql
SELECT COUNT(*) AS unknown_department_employees
FROM demo_employees
WHERE department IS NULL;
-- 2
```

Hoặc giữ tất cả nhóm và đặt điều kiện cho nhóm sau khi tổng hợp:

```sql
SELECT department, COUNT(*) AS employees
FROM demo_employees
GROUP BY department
HAVING COUNT(*) >= 2
ORDER BY department NULLS LAST;
```

Kết quả có nhóm `HR`, `Sales` và nhóm `NULL` vì mỗi nhóm đều có ít nhất 2 nhân viên. `HAVING` áp dụng cho nhóm; `WHERE` lọc dòng **trước** khi nhóm.

### 4.3. `COALESCE` dùng để đặt nhãn, nhưng có thể làm nhập nhằng dữ liệu

`COALESCE(department, 'Chưa xác định')` trả về nhãn thay thế khi `department` là `NULL`:

```sql
SELECT
    COALESCE(department, 'Chưa xác định') AS department_label,
    COUNT(*) AS employees
FROM demo_employees
GROUP BY COALESCE(department, 'Chưa xác định')
ORDER BY department_label;
```

Cách này thuận tiện khi hiển thị báo cáo. Nhưng nếu bảng nguồn thực sự có phòng ban tên **“Chưa xác định”**, dòng thuộc phòng ban đó sẽ bị gộp chung với dòng có `NULL`. Nếu muốn giữ ngữ nghĩa chính xác, có thể **nhóm theo cột gốc** và chỉ áp dụng nhãn trong kết quả:

```sql
SELECT
    COALESCE(department, 'Chưa xác định') AS department_label,
    COUNT(*) AS employees
FROM demo_employees
GROUP BY department
ORDER BY department NULLS LAST;
```

Ngay cả khi đó, hai nhóm khác nhau có thể hiển thị cùng nhãn nếu dữ liệu thật chứa chuỗi thay thế. Khi cần phân biệt ở giao diện hoặc API, nên trả thêm cờ `department IS NULL` hoặc giữ nguyên giá trị gốc.

### 4.4. Trường hợp nâng cao: `ROLLUP` tạo dòng tổng cũng hiển thị `NULL`

Trong truy vấn có `ROLLUP`, một ô `NULL` ở cột nhóm có thể có hai nguyên nhân: dữ liệu gốc thiếu giá trị hoặc dòng tổng hợp không có khóa nhóm. PostgreSQL hỗ trợ `GROUPING(...)` để phân biệt:

```sql
SELECT
    department,
    GROUPING(department) AS is_grand_total,
    COUNT(*) AS employees
FROM demo_employees
GROUP BY ROLLUP (department)
ORDER BY GROUPING(department), department NULLS LAST;
```

Ở bảng mẫu, sẽ có **một dòng nhóm `department IS NULL` của dữ liệu thật** (`is_grand_total = 0`, có 2 nhân viên) và **một dòng tổng tất cả nhân viên** (`is_grand_total = 1`, có 8 nhân viên). Không nên coi mọi ô `NULL` từ `ROLLUP` đều là dữ liệu thiếu.

## 5. `ORDER BY`: `NULL` đứng trước hay sau phụ thuộc DBMS

`ORDER BY` quyết định thứ tự trả về; `NULL` vẫn có thể nằm trong cột được sắp xếp. **SQL không bảo đảm vị trí mặc định của `NULL` giống nhau trên mọi DBMS.** Đặc biệt, không được suy ra “`ASC` luôn đẩy `NULL` xuống cuối”.

Ví dụ PostgreSQL:

```sql
-- NULL đứng cuối, các khoản thưởng khác NULL tăng dần.
SELECT employee_id, bonus
FROM demo_employees
ORDER BY bonus ASC NULLS LAST, employee_id ASC;

-- NULL đứng đầu, các khoản thưởng khác NULL giảm dần.
SELECT employee_id, bonus
FROM demo_employees
ORDER BY bonus DESC NULLS FIRST, employee_id ASC;
```

Lệnh đầu cho thứ tự `employee_id` theo `bonus`: **4, 3, 8, 6, 1, 7, 2, 5**. Các khoản thưởng có cùng giá trị được sắp tiếp bằng `employee_id`, bảo đảm thứ tự ổn định trong trường hợp này.

### 5.1. Mặc định thường gặp giữa các hệ quản trị

| DBMS | `ORDER BY col ASC` mặc định | `ORDER BY col DESC` mặc định | `NULLS FIRST/LAST` trong `ORDER BY` |
|---|---|---|---|
| PostgreSQL | `NULL` cuối | `NULL` đầu | Hỗ trợ |
| Oracle Database | `NULL` cuối | `NULL` đầu | Hỗ trợ |
| MySQL | `NULL` đầu | `NULL` cuối | Không dùng trực tiếp cú pháp PostgreSQL; thường dùng biểu thức sắp xếp |
| SQL Server | `NULL` đầu | `NULL` cuối | Thường dùng biểu thức `CASE` để chỉ định vị trí |
| SQLite | `NULL` đầu | `NULL` cuối | Hỗ trợ `NULLS FIRST/LAST` từ phiên bản 3.30.0 |

Các giá trị trong bảng là **hành vi mặc định thông dụng**, còn cú pháp hỗ trợ cần kiểm tra theo phiên bản. Nếu một truy vấn được dùng bởi nhiều hệ quản trị, hãy chỉ rõ ý định sắp xếp thay vì dựa vào mặc định.

### 5.2. Cách sắp `NULL` cuối tương đối dễ chuyển DBMS

Có thể tạo khóa sắp xếp từ biểu thức `CASE`:

```sql
SELECT employee_id, bonus
FROM demo_employees
ORDER BY
    CASE WHEN bonus IS NULL THEN 1 ELSE 0 END ASC,
    bonus ASC,
    employee_id ASC;
```

Biểu thức thứ nhất trả về `0` cho khoản thưởng đã biết và `1` cho `NULL`, nên tất cả giá trị đã biết đứng trước; phần thứ hai sắp các số thưởng; phần thứ ba phân định các giá trị bằng nhau. Cách này có tính chuyển đổi tốt hơn cú pháp riêng của một DBMS, nhưng cần đánh giá hiệu năng và khả năng tận dụng chỉ mục.

Dùng `COALESCE(bonus, -1)` để ép `NULL` đứng đầu có thể sai nếu thực tế tồn tại thưởng âm `-1` hoặc nếu miền giá trị thay đổi. Dùng `CASE WHEN ... IS NULL` biểu thị rõ mục đích mà không cần giá trị giả.

### 5.3. Vì sao cần khóa sắp xếp phụ?

Nếu hai nhân viên cùng `bonus = 1000`, chỉ `ORDER BY bonus` không quy định nhân viên nào đứng trước. Tương tự, các dòng có `bonus IS NULL` vẫn bằng nhau theo khóa sắp xếp. Khi phân trang bằng `LIMIT/OFFSET`, thứ tự không ổn định có thể gây lặp hoặc bỏ sót bản ghi giữa các lần lấy trang. Thêm một khóa duy nhất như `employee_id` giúp thứ tự có thể dự đoán được cho cùng một trạng thái dữ liệu.

Ngoài ra, **không có `ORDER BY` thì thứ tự dòng trong SQL không được bảo đảm**, dù bảng có khóa chính hoặc kết quả trên môi trường thử nghiệm thường trông có thứ tự.

## 6. Ràng buộc `UNIQUE`: không nhầm với `SELECT DISTINCT`

`UNIQUE` là quy tắc **ngăn ghi dữ liệu có khóa bị coi là trùng**, khác với `SELECT DISTINCT` là thao tác **loại trùng trong kết quả truy vấn**. Các DBMS có quy tắc khác nhau về `NULL` trong khóa duy nhất.

### 6.1. PostgreSQL mặc định cho phép nhiều `NULL` trong cột `UNIQUE`

```sql
CREATE TEMP TABLE demo_contacts (
    contact_id INTEGER PRIMARY KEY,
    email VARCHAR(255) UNIQUE
);

-- PostgreSQL: hợp lệ, vì cả hai email đều NULL.
INSERT INTO demo_contacts (contact_id, email)
VALUES
    (1, NULL),
    (2, NULL),
    (3, 'anna@example.test');
```

Nếu sau đó chạy:

```sql
-- PostgreSQL: bị từ chối do trùng email khác NULL.
INSERT INTO demo_contacts (contact_id, email)
VALUES (4, 'anna@example.test');
```

Lệnh cuối báo vi phạm `UNIQUE`. Theo mặc định PostgreSQL, nhiều dòng thiếu email được chấp nhận, nhưng hai email **đã biết và giống nhau** thì không. Hành vi này cũng phổ biến ở MySQL và SQLite, nhưng **không áp dụng như vậy cho ràng buộc UNIQUE mặc định của SQL Server**.

**Ý nghĩa nghiệp vụ:** nếu email là tùy chọn nhưng mỗi email được cung cấp phải thuộc tối đa một liên hệ, cách hiểu “nhiều `NULL`; các giá trị đã biết không trùng” thường phù hợp.

### 6.2. `NOT NULL` và `UNIQUE` giải quyết hai câu hỏi khác nhau

- `NOT NULL`: mọi bản ghi **phải có** giá trị cho cột.
- `UNIQUE`: các khóa được coi là trùng **không được đồng thời tồn tại**.
- `NOT NULL UNIQUE`: giá trị vừa **bắt buộc**, vừa **không trùng**.

```sql
CREATE TABLE user_accounts (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(60) NOT NULL UNIQUE,
    email VARCHAR(255)
);
```

Ở đây, mọi tài khoản phải có `username` và không tài khoản nào được dùng trùng; `email` cho phép thiếu vì chưa yêu cầu `NOT NULL`, và ví dụ chưa thêm quy tắc duy nhất cho email.

Nếu nghiệp vụ yêu cầu email cũng bắt buộc, hãy thêm `NOT NULL` rồi chọn ràng buộc `UNIQUE` thích hợp. Không thể dùng `UNIQUE` một mình thay cho `NOT NULL` trên các hệ cho phép nhiều `NULL`.

### 6.3. PostgreSQL 15+: `UNIQUE NULLS NOT DISTINCT`

PostgreSQL từ phiên bản 15 cho phép yêu cầu coi các `NULL` là **không phân biệt** khi kiểm tra khóa duy nhất:

```sql
-- Cú pháp PostgreSQL 15 trở lên.
CREATE TABLE demo_registry (
    registry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_code TEXT,
    CONSTRAINT uq_registry_external_code
        UNIQUE NULLS NOT DISTINCT (external_code)
);
```

Với định nghĩa này, một dòng `external_code IS NULL` có thể tồn tại, nhưng **dòng thứ hai có `external_code IS NULL` sẽ vi phạm ràng buộc**, cũng như hai giá trị khác `NULL` giống nhau. Có thể dùng cùng chính sách cho chỉ mục `UNIQUE` khi thiết kế tương ứng.

Chính sách “chỉ một giá trị chưa biết trong cả bảng” không phải lúc nào hợp lý. Nếu có nhiều bản ghi chưa được gán mã, dùng mặc định nhiều `NULL` có thể phản ánh nghiệp vụ tốt hơn; nếu mã **luôn bắt buộc**, `NOT NULL UNIQUE` còn rõ nghĩa hơn.

### 6.4. Khóa `UNIQUE` gồm nhiều cột có `NULL`

Xét mã tham chiếu bên ngoài được phân vùng theo khách thuê (`tenant`):

```sql
CREATE TEMP TABLE demo_external_refs (
    record_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    external_ref TEXT,
    CONSTRAINT uq_tenant_external_ref
        UNIQUE (tenant_id, external_ref)
);

-- PostgreSQL mặc định: cả hai dòng được chấp nhận.
INSERT INTO demo_external_refs (record_id, tenant_id, external_ref)
VALUES
    (1, 10, NULL),
    (2, 10, NULL),
    (3, 10, 'EXT-001'),
    (4, 20, 'EXT-001');
```

Hai dòng `(tenant_id = 10, external_ref = NULL)` được chấp nhận theo quy tắc `UNIQUE` mặc định của PostgreSQL. Hai dòng `(10, 'EXT-001')` và `(20, 'EXT-001')` cũng không xung đột vì `tenant_id` khác nhau. Nhưng chèn thêm dòng `(10, 'EXT-001')` sẽ vi phạm `UNIQUE (tenant_id, external_ref)`.

Nếu nghiệp vụ yêu cầu **tối đa một mã chưa xác định cho mỗi tenant**, PostgreSQL 15+ có thể khai báo:

```sql
CREATE TABLE strict_external_refs (
    record_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    external_ref TEXT,
    CONSTRAINT uq_strict_tenant_external_ref
        UNIQUE NULLS NOT DISTINCT (tenant_id, external_ref)
);
```

Khi đó `(10, NULL)` chỉ được xuất hiện một lần, nhưng `(20, NULL)` vẫn có thể xuất hiện một lần vì tổ hợp khóa khác. **Không nên suy rộng quy tắc khóa ghép có `NULL` của PostgreSQL cho Oracle hoặc SQL Server**, vì các sản phẩm này có khác biệt đáng kể.

### 6.5. Hành vi `UNIQUE` theo DBMS

| DBMS | `UNIQUE` cột đơn có nhiều `NULL`? | Ghi chú |
|---|---|---|
| PostgreSQL (mặc định) | Có | PostgreSQL 15+ có `NULLS NOT DISTINCT` để thay đổi hành vi |
| MySQL | Có | Có thể có nhiều giá trị `NULL` trong chỉ mục `UNIQUE`, kể cả khóa ghép |
| SQLite | Có | Các `NULL` được xem là phân biệt khi thực thi `UNIQUE` |
| Oracle Database | Có | Khóa ghép có phần tử `NULL` có quy tắc đặc thù: các phần khóa khác `NULL` giống nhau có thể gây xung đột |
| SQL Server | Thông thường không | Ràng buộc `UNIQUE` cột đơn thường chỉ cho một `NULL`; có thể dùng **filtered unique index** nếu muốn cho phép nhiều `NULL` |

Ví dụ với SQL Server, nếu email có thể thiếu nhưng các email đã biết phải duy nhất, có thể chọn chỉ mục lọc thay vì ràng buộc `UNIQUE` trên toàn cột:

```sql
-- Cú pháp SQL Server; bảng dbo.contacts phải tồn tại
-- và không có UNIQUE constraint khác cấm nhiều NULL trên email.
CREATE UNIQUE INDEX ux_contacts_email_when_present
ON dbo.contacts (email)
WHERE email IS NOT NULL;
```

Chỉ mục này áp dụng điều kiện duy nhất cho các dòng có email đã biết. Các dòng `email IS NULL` nằm ngoài chỉ mục lọc nên có thể nhiều dòng. Với DBMS khác, cú pháp index có điều kiện và khả năng hỗ trợ khác nhau.

**Ràng buộc duy nhất còn chịu ảnh hưởng của quy tắc so sánh chuỗi:** collation, phân biệt hoa thường, khoảng trắng và chuẩn hóa dữ liệu có thể quyết định `'Alice@example.test'` và `'alice@example.test'` có bị xem là trùng hay không. Đây là vấn đề bổ sung ngoài `NULL`.

## 7. Bốn thao tác nhìn cạnh nhau

Dựa trên bảng `demo_employees`, xét một cột `department` có các giá trị `Sales`, `HR`, `IT`, `NULL` và có lặp:

| Câu lệnh | Câu hỏi thực sự | Hành vi với `NULL` |
|---|---|---|
| `SELECT DISTINCT department` | Có những giá trị phòng ban nào trong kết quả? | Chỉ hiển thị **một** đại diện `NULL` |
| `SELECT COUNT(DISTINCT department)` | Có bao nhiêu giá trị phòng ban **đã biết**? | Bỏ `NULL`, kết quả **3** |
| `GROUP BY department` | Có bao nhiêu nhân viên theo mỗi phòng ban? | Tạo **một nhóm `NULL`** có 2 nhân viên |
| `ORDER BY department` | Sắp thứ tự kết quả theo phòng ban ra sao? | Vị trí `NULL` tùy DBMS hoặc chỉ định tường minh |
| `UNIQUE (department)` | Có cho ghi nhiều nhân viên cùng phòng ban? | Đây là quy tắc lưu trữ, sẽ cấm các giá trị đã biết trùng; thường **không phù hợp** với phòng ban của nhiều nhân viên |
| `UNIQUE (email)` | Có cho phép hai liên hệ có cùng email? | Các email không `NULL` bị kiểm soát trùng; nhiều `NULL` được phép hay không tùy DBMS/chính sách |

Đặc biệt, **đừng thêm `UNIQUE` để mô phỏng `SELECT DISTINCT`**. Một bảng nhân viên cần cho phép nhiều nhân viên thuộc cùng phòng ban; ràng buộc duy nhất trên `department` sẽ chặn dữ liệu hợp lệ, trong khi `DISTINCT` chỉ giúp hiển thị danh sách phòng ban không lặp.

## 8. Các tình huống báo cáo và thiết kế thường gặp

### 8.1. Báo cáo “chưa biết phòng ban”

Nếu báo cáo cần hiển thị cả nhóm thiếu dữ liệu, hãy giữ `NULL` trong phép nhóm và hiển thị nhãn:

```sql
SELECT
    department,
    CASE
        WHEN department IS NULL THEN 'Chưa xác định'
        ELSE department
    END AS department_label,
    COUNT(*) AS employees
FROM demo_employees
GROUP BY department
ORDER BY
    CASE WHEN department IS NULL THEN 1 ELSE 0 END,
    department;
```

Giữ cả cột gốc và nhãn giúp ứng dụng biết nhóm nào thực sự là `NULL`.

### 8.2. Thống kê tỷ lệ thiếu thông tin

Đôi khi quan trọng không chỉ là có nhóm `NULL` hay không, mà còn tỷ lệ thiếu:

```sql
SELECT
    COUNT(*) AS total_employees,
    COUNT(*) - COUNT(department) AS unknown_department_count,
    100.0 * (COUNT(*) - COUNT(department))
        / NULLIF(COUNT(*), 0) AS unknown_department_percentage
FROM demo_employees;
```

Bảng mẫu có **2/8 = 25%** nhân viên chưa xác định phòng ban. `NULLIF(COUNT(*), 0)` tránh chia cho 0 khi bảng không có dòng nào. Biểu thức này phù hợp cho việc đo chất lượng dữ liệu, thay vì âm thầm thay `NULL` thành một phòng ban giả.

### 8.3. Chuyển yêu cầu nghiệp vụ thành ràng buộc

Đối với trường email, xác định rõ từng trường hợp:

- **Bắt buộc và không trùng:** `email NOT NULL UNIQUE`.
- **Có thể thiếu, email đã có phải không trùng:** dùng `UNIQUE` mặc định trên PostgreSQL/MySQL/SQLite; dùng filtered unique index thích hợp ở SQL Server.
- **Có thể thiếu nhưng chỉ chấp nhận một dòng thiếu:** cân nhắc `UNIQUE NULLS NOT DISTINCT` ở PostgreSQL 15+, nếu yêu cầu này thực sự có nghĩa.
- **Email có thể trùng vì tài khoản dùng chung một địa chỉ liên hệ:** không khai báo `UNIQUE` chỉ vì thấy email thường là định danh; trước tiên phải hiểu nghiệp vụ.

Trước khi thêm `UNIQUE` vào bảng đã có dữ liệu, cần kiểm tra dữ liệu trùng hiện hữu và hành vi `NULL` của đúng DBMS. Nếu có các giá trị vi phạm, lệnh thêm ràng buộc/chỉ mục sẽ thất bại hoặc phải giải quyết dữ liệu trước.

## 9. Các sai lầm dễ gặp

| Sai lầm | Vì sao sai | Cách xử lý |
|---|---|---|
| `WHERE col = NULL` | So sánh trả về `UNKNOWN`, không lọc đúng giá trị thiếu | `WHERE col IS NULL` |
| Cho rằng `DISTINCT` trả một dòng cho mỗi `NULL` | `DISTINCT` gộp các `NULL` tương ứng khi loại trùng | Xem `NULL` là một đại diện trong tập kết quả phân biệt |
| Xem `COUNT(DISTINCT col)` là số dòng từ `SELECT DISTINCT col` | `COUNT(DISTINCT col)` bỏ qua `NULL` | Xác định có cần đếm nhóm thiếu dữ liệu hay không |
| Nghĩ `GROUP BY` tách các dòng `NULL` riêng biệt | Các khóa nhóm `NULL` được gom lại | Dùng `COUNT(*)` và `COUNT(col)` để đo số dòng và số giá trị đã biết |
| Giả định `ORDER BY ASC` đặt `NULL` cuối trên mọi DBMS | Mặc định khác nhau theo hệ | Chỉ định `NULLS FIRST/LAST` nếu hỗ trợ hoặc dùng `CASE` |
| Sắp xếp chỉ theo cột có nhiều giá trị bằng nhau | Thứ tự giữa các dòng cùng khóa không cố định | Thêm khóa phụ duy nhất khi cần thứ tự ổn định |
| Nghĩ `UNIQUE` đồng nghĩa `NOT NULL` | Nhiều DBMS chấp nhận nhiều `NULL` trong khóa duy nhất | Khai báo `NOT NULL` khi giá trị bắt buộc |
| Nghĩ `UNIQUE` cho phép nhiều `NULL` trên mọi DBMS | SQL Server có hành vi khác | Chọn ràng buộc/chỉ mục theo sản phẩm và phiên bản |
| Dùng `COALESCE` với nhãn có thể là dữ liệu thật để nhóm | Có thể gộp hai loại dữ liệu khác nhau | Nhóm theo giá trị gốc, tạo nhãn chỉ khi hiển thị |
| Dùng `0` hoặc `''` thay cho `NULL` theo thói quen | Giá trị giả có thể mang ý nghĩa khác và làm sai thống kê | Xác định ngữ nghĩa dữ liệu thiếu rồi chọn cách lưu phù hợp |

## 10. Bài tập tự luyện có đáp án giải thích

**Bài 1.** Với bảng `demo_employees`, hai câu lệnh dưới đây trả về bao nhiêu kết quả?

```sql
SELECT DISTINCT bonus FROM demo_employees;

SELECT COUNT(DISTINCT bonus) FROM demo_employees;
```

**Đáp án:** truy vấn đầu trả **5 dòng** với `200`, `800`, `900`, `1000` và một `NULL`; truy vấn sau trả **4** vì `COUNT(DISTINCT bonus)` không đếm `NULL`.

**Bài 2.** Vì sao `GROUP BY department` chỉ có một dòng kết quả với `department IS NULL`, dù có hai nhân viên chưa biết phòng ban?

**Đáp án:** `GROUP BY` xác định cùng nhóm theo quy tắc không phân biệt giữa các khóa nhóm, nên hai `NULL` cùng một nhóm. Điều đó không khiến phép so sánh `NULL = NULL` trở thành `TRUE`.

**Bài 3.** Hãy sắp nhân viên theo thưởng giảm dần, `NULL` đứng cuối và nhân viên có cùng thưởng theo ID tăng dần, không phụ thuộc mặc định của DBMS.

**Đáp án:**

```sql
SELECT employee_id, bonus
FROM demo_employees
ORDER BY
    CASE WHEN bonus IS NULL THEN 1 ELSE 0 END,
    bonus DESC,
    employee_id ASC;
```

**Bài 4.** Tại PostgreSQL mặc định, vì sao bảng `demo_contacts` cho phép cả `(1, NULL)` và `(2, NULL)` trong cột `email UNIQUE`?

**Đáp án:** với ràng buộc `UNIQUE` mặc định, các giá trị `NULL` được xem là phân biệt để xét vi phạm duy nhất. `UNIQUE` không ép email phải có. Nếu email bắt buộc thì khai báo `NOT NULL`; nếu muốn `NULL` bị coi là trùng thì PostgreSQL 15+ có `UNIQUE NULLS NOT DISTINCT`.

**Bài 5.** Có thể dựa vào `ORDER BY department ASC` để luôn hiển thị các nhân viên chưa biết phòng ban ở cuối trên cả PostgreSQL và SQL Server không?

**Đáp án:** không. PostgreSQL mặc định đưa `NULL` cuối khi tăng dần; SQL Server mặc định đưa `NULL` đầu. Hãy dùng cú pháp chỉ định `NULLS LAST` khi hệ quản trị hỗ trợ, hoặc dùng khóa sắp xếp `CASE WHEN department IS NULL THEN 1 ELSE 0 END` để thể hiện rõ ý định.

## Kết luận

`NULL` là dấu hiệu thiếu/chưa xác định giá trị nên cần đọc theo **ngữ cảnh phép toán**: `DISTINCT` hiển thị một đại diện `NULL`, `GROUP BY` gom các `NULL` vào một nhóm, `ORDER BY` có quy tắc vị trí phụ thuộc DBMS, còn `UNIQUE` có chính sách trùng với `NULL` khác nhau giữa các hệ quản trị.

Khi thiết kế truy vấn, hãy nêu rõ muốn **giữ, bỏ, đếm, nhóm hay sắp** các bản ghi có `NULL`. Khi thiết kế bảng, hãy kết hợp `NULL`/`NOT NULL` và `UNIQUE` đúng với nghiệp vụ và kiểm tra hành vi của DBMS thực tế. Nhờ đó, báo cáo không bỏ sót dữ liệu thiếu và ràng buộc không vô tình từ chối những bản ghi hợp lệ.


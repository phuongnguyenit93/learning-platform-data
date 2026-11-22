# FIRST_VALUE, LAST_VALUE, NTH_VALUE và phạm vi cửa sổ trong Oracle

Trong Oracle Database, các hàm phân tích **`FIRST_VALUE`**, **`LAST_VALUE`** và **`NTH_VALUE`** giúp lấy một giá trị ở vị trí đầu, cuối hoặc vị trí thứ N trong một **cửa sổ (window frame)** của dữ liệu. Chúng thường được dùng để so sánh một giao dịch với giao dịch đầu tiên/cuối cùng của khách hàng, tìm mức lương cao nhất/thấp nhất theo phòng ban, lấy giá trị tại lần giao dịch thứ hai, hoặc hiển thị mốc đầu/cuối bên cạnh từng hàng mà không làm mất chi tiết dữ liệu.

Điểm khó nhất của nhóm hàm này không nằm ở tên hàm, mà ở **phạm vi cửa sổ**. Trong Oracle, nếu analytic clause có `ORDER BY` nhưng không khai báo windowing clause, khung mặc định thường là:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Điều này đặc biệt dễ gây bất ngờ với `LAST_VALUE`: nhiều người mong muốn giá trị cuối cùng của cả partition, nhưng lại nhận giá trị cuối của **khung hiện tại**. Muốn lấy giá trị cuối của toàn bộ partition, thường cần khai báo tường minh:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

Bài học trình bày cú pháp, ý nghĩa của từng hàm, sự khác nhau giữa `ROWS` và `RANGE`, cách xử lý `NULL`, tie và thứ tự xác định, cùng ví dụ SQL thực hành.

## 1. Nhắc lại analytic function và window frame

Analytic function tính toán trên một tập hàng liên quan đến hàng hiện tại nhưng vẫn giữ lại từng hàng của kết quả. Cấu trúc thường gặp:

```sql
function_name(expression)
OVER (
    PARTITION BY group_column
    ORDER BY sort_column
    windowing_clause
)
```

- `PARTITION BY`: chia dữ liệu thành các nhóm độc lập; hàm bắt đầu tính lại trong mỗi nhóm.
- `ORDER BY`: xác định thứ tự logic của các hàng trong partition.
- `windowing_clause`: giới hạn tập hàng mà hàm được phép nhìn thấy đối với hàng hiện tại.

```text
Tập dữ liệu
    |
    v
PARTITION BY (nếu có)
    |
    v
Sắp xếp từng partition theo analytic ORDER BY
    |
    v
Với từng hàng hiện tại:
    xác định window frame
    |
    v
FIRST_VALUE / LAST_VALUE / NTH_VALUE
    |
    v
Trả giá trị phân tích bên cạnh hàng hiện tại
```

Khác với `GROUP BY`, analytic function không gộp nhiều hàng thành một hàng kết quả. Ví dụ, `FIRST_VALUE(salary)` có thể trả mức lương đầu tiên của phòng ban bên cạnh **mỗi nhân viên** trong phòng ban đó.

### 1.1. Window frame là gì?

Window frame là phần hàng cụ thể được chọn trong partition để tính kết quả tại một hàng hiện tại. Với thứ tự tăng dần theo ngày, frame có thể là:

- Từ đầu partition đến hàng hiện tại.
- Từ hàng hiện tại đến cuối partition.
- Hai hàng trước đến hai hàng sau hàng hiện tại.
- Toàn bộ partition.

Một số mốc thường dùng:

| Mốc | Ý nghĩa |
|---|---|
| `UNBOUNDED PRECEDING` | Hàng đầu tiên của partition |
| `n PRECEDING` | Lùi n hàng hoặc n đơn vị sort key, tùy ROWS/RANGE |
| `CURRENT ROW` | Hàng hiện tại; với RANGE có thể bao gồm các peer cùng sort key |
| `n FOLLOWING` | Tiến n hàng hoặc n đơn vị sort key |
| `UNBOUNDED FOLLOWING` | Hàng cuối cùng của partition |

Ví dụ frame toàn partition:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

Ví dụ frame từ đầu partition đến hiện tại:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

### 1.2. Thứ tự xử lý và vị trí dùng analytic function

Trong một query block, analytic function được tính sau các bước lọc hàng `WHERE`, gom nhóm `GROUP BY` và lọc nhóm `HAVING`. Vì vậy, không thể tham chiếu alias analytic trực tiếp trong `WHERE` cùng cấp. Muốn lọc theo kết quả analytic, hãy bọc bằng inline view hoặc CTE.

```sql
WITH ranked AS (
    SELECT employee_id,
           FIRST_VALUE(salary) OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
           ) AS highest_salary
    FROM employees
)
SELECT *
FROM ranked;
```

## 2. Chuẩn bị dữ liệu thực hành

Các ví dụ dùng bảng giả `LAB_EMP_PAY_HISTORY`, gồm nhân viên, phòng ban, ngày hiệu lực và mức lương. Dữ liệu có mức lương trùng nhau và một số giá trị `NULL` để minh họa cách chọn giá trị đầu/cuối và tác động của `IGNORE NULLS`.

Chỉ tạo bảng trong schema **DEV/TEST** được cấp quyền `CREATE TABLE` và quota. Trước khi chạy DDL, xác nhận đúng service, PDB và user:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

### 2.1. Tạo bảng

```sql
CREATE TABLE lab_emp_pay_history (
    history_id    NUMBER PRIMARY KEY,
    employee_id   NUMBER NOT NULL,
    employee_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    effective_on  DATE NOT NULL,
    salary        NUMBER(12, 2)
);
```

`HISTORY_ID` xác định duy nhất một bản ghi lịch sử. Một nhân viên có thể có nhiều dòng lương theo thời gian; vì thế `EMPLOYEE_ID` không phải primary key của bảng này.

### 2.2. Nạp dữ liệu giả

```sql
INSERT ALL
    INTO lab_emp_pay_history VALUES (1, 101, 'An',    10, DATE '2026-01-01', 5000)
    INTO lab_emp_pay_history VALUES (2, 102, 'Binh',  10, DATE '2026-01-05', 6000)
    INTO lab_emp_pay_history VALUES (3, 103, 'Chi',   10, DATE '2026-01-10', 6000)
    INTO lab_emp_pay_history VALUES (4, 104, 'Dung',  10, DATE '2026-01-15', 4500)
    INTO lab_emp_pay_history VALUES (5, 105, 'Em',    10, DATE '2026-01-20', NULL)
    INTO lab_emp_pay_history VALUES (6, 201, 'Giang', 20, DATE '2026-01-02', 8000)
    INTO lab_emp_pay_history VALUES (7, 202, 'Ha',    20, DATE '2026-01-07', 7500)
    INTO lab_emp_pay_history VALUES (8, 203, 'Khanh', 20, DATE '2026-01-12', NULL)
    INTO lab_emp_pay_history VALUES (9, 204, 'Lan',   20, DATE '2026-01-17', 7000)
SELECT 1 FROM dual;

COMMIT;
```

### 2.3. Xem dữ liệu nguồn

```sql
SELECT history_id, employee_id, employee_name,
       department_id, effective_on, salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Hai phòng ban có lịch sử lương riêng. Phòng 10 có hai mức lương 6000 cùng xuất hiện vào hai ngày khác nhau; phòng 20 có hai giá trị `NULL`/không null xen kẽ. Dữ liệu này giúp quan sát cả tie lẫn null.

## 3. FIRST_VALUE: lấy giá trị đầu tiên trong window frame

Cú pháp cơ bản:

```sql
FIRST_VALUE(expression)
    [RESPECT NULLS | IGNORE NULLS]
OVER (
    [PARTITION BY ...]
    ORDER BY ...
    [windowing_clause]
)
```

`FIRST_VALUE` trả về giá trị của `expression` tại **hàng đầu tiên trong window frame** theo thứ tự được xác định bởi analytic `ORDER BY`.

### 3.1. Lấy mức lương cao nhất của mỗi phòng ban

```sql
SELECT employee_id,
       employee_name,
       department_id,
       salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS department_highest_salary
FROM lab_emp_pay_history
ORDER BY department_id, salary DESC NULLS LAST, history_id;
```

Trong mỗi phòng ban:

- Sắp xếp lương giảm dần.
- Đặt `NULL` xuống cuối để giá trị thiếu không trở thành mức cao nhất.
- `HISTORY_ID` phân định thứ tự khi lương bằng nhau.
- `FIRST_VALUE` lấy lương của hàng đầu tiên trong toàn partition.

Kết quả minh họa: phòng 10 có `DEPARTMENT_HIGHEST_SALARY = 6000` trên mọi hàng; phòng 20 có giá trị `8000` trên mọi hàng.

Ở ví dụ này, frame toàn partition được viết tường minh để ý nghĩa “giá trị cao nhất của cả phòng ban” không phụ thuộc frame mặc định. Với `FIRST_VALUE` và thứ tự giảm dần, frame mặc định từ đầu đến hiện tại vẫn chứa hàng đầu tiên nên thường cho cùng giá trị đầu tiên trên mọi hàng; nhưng khai báo rõ frame giúp người đọc hiểu đúng ý định và thuận tiện khi đổi logic.

### 3.2. Lấy giá trị đầu tiên theo thời gian

```sql
SELECT employee_id,
       employee_name,
       department_id,
       effective_on,
       salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY employee_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS first_recorded_salary
FROM employee_salary_history;
```

Truy vấn giả định một nhân viên có nhiều bản ghi lương. `FIRST_VALUE` trả mức lương ở lần ghi nhận đầu tiên theo ngày. Nếu ngày có thể trùng, thêm khóa duy nhất như `HISTORY_ID` để xác định rõ hàng đầu tiên.

### 3.3. FIRST_VALUE và NULL

Oracle mặc định dùng `RESPECT NULLS`: nếu hàng đầu tiên trong frame có giá trị expression là `NULL`, `FIRST_VALUE` trả `NULL`. Có thể dùng `IGNORE NULLS` để bỏ qua các giá trị null khi tìm giá trị đầu tiên:

```sql
SELECT employee_id,
       effective_on,
       salary,
       FIRST_VALUE(salary) IGNORE NULLS OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS first_known_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

`FIRST_VALUE(salary) IGNORE NULLS` trả mức lương không null đầu tiên theo thứ tự ngày trong toàn partition. Nếu cả partition chỉ có null, kết quả vẫn null.

## 4. LAST_VALUE: lấy giá trị cuối cùng trong window frame

Cú pháp:

```sql
LAST_VALUE(expression)
    [RESPECT NULLS | IGNORE NULLS]
OVER (
    [PARTITION BY ...]
    ORDER BY ...
    [windowing_clause]
)
```

`LAST_VALUE` trả giá trị của expression tại **hàng cuối cùng trong window frame hiện tại**. Cụm “trong window frame” rất quan trọng: frame có thể chỉ chạy từ đầu partition tới hàng hiện tại, không phải toàn partition.

### 4.1. Bẫy mặc định của LAST_VALUE

Ví dụ:

```sql
SELECT employee_id,
       department_id,
       effective_on,
       salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on
       ) AS last_salary_default_frame
FROM lab_emp_pay_history
ORDER BY department_id, effective_on;
```

Khi có `ORDER BY` nhưng không khai báo frame, Oracle mặc định frame dạng:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Do đó `LAST_VALUE` trả giá trị ở hàng cuối của **frame kết thúc tại hàng hiện tại (và các peer của nó theo RANGE)**. Với thứ tự ngày tăng dần duy nhất, hàng cuối frame thường chính là hàng hiện tại; kết quả vì thế có thể giống `SALARY` ở từng hàng, khiến người học tưởng `LAST_VALUE` không làm gì.

Đây là lỗi rất phổ biến: câu SQL chạy bình thường nhưng không trả giá trị cuối cùng của cả phòng ban như mong muốn.

### 4.2. Lấy giá trị cuối cùng của toàn partition

Muốn lấy mức lương ở hàng cuối cùng theo ngày của mỗi phòng ban, khai báo frame bao trọn partition:

```sql
SELECT employee_id,
       employee_name,
       department_id,
       effective_on,
       salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS department_last_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Ở đây:

- `UNBOUNDED PRECEDING`: bắt đầu từ hàng đầu tiên của phòng ban.
- `UNBOUNDED FOLLOWING`: kết thúc ở hàng cuối cùng của phòng ban.
- `LAST_VALUE` lấy expression tại hàng cuối cùng của frame toàn partition.

Theo dữ liệu lab, hàng cuối phòng 10 là history 5 có `SALARY = NULL`, nên `DEPARTMENT_LAST_SALARY` là NULL trên mọi hàng của phòng 10 theo mặc định `RESPECT NULLS`. Hàng cuối phòng 20 là history 9 có lương 7000, nên kết quả là 7000 trên mọi hàng phòng 20.

### 4.3. Muốn giá trị cuối cùng không NULL

Nếu nghiệp vụ muốn lấy mức lương được ghi nhận gần nhất **có giá trị**, dùng `IGNORE NULLS`:

```sql
SELECT employee_id,
       department_id,
       effective_on,
       salary,
       LAST_VALUE(salary) IGNORE NULLS OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS last_known_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Kết quả:

- Phòng 10: hàng cuối không null là history 4, mức lương 4500.
- Phòng 20: hàng cuối không null là history 9, mức lương 7000.

`IGNORE NULLS` thay đổi cách chọn hàng có expression null; nó không thay đổi dữ liệu gốc hoặc biến null thành 0.

### 4.4. LAST_VALUE với frame từ hiện tại đến cuối partition

Một cách khác để lấy giá trị cuối cùng của partition là:

```sql
LAST_VALUE(salary) OVER (
    PARTITION BY department_id
    ORDER BY effective_on, history_id
    ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
)
```

Frame này bắt đầu tại hàng hiện tại và kéo tới cuối partition. Hàng cuối của frame vẫn là hàng cuối partition, vì vậy kết quả `LAST_VALUE` có thể là cùng một giá trị trên mọi hàng. Khác biệt là tập frame không bao gồm các hàng trước hàng hiện tại; điều này quan trọng nếu kết hợp với những hàm hoặc phép tính khác. Đối với `LAST_VALUE`, cả frame toàn partition và frame từ hiện tại đến cuối đều có thể xác định cùng hàng cuối.

## 5. NTH_VALUE: lấy giá trị tại vị trí thứ N

Cú pháp tổng quát:

```sql
NTH_VALUE(expression, n)
    [FROM FIRST | FROM LAST]
    [RESPECT NULLS | IGNORE NULLS]
OVER (
    [PARTITION BY ...]
    ORDER BY ...
    [windowing_clause]
)
```

- `expression`: giá trị muốn lấy.
- `n`: vị trí bắt đầu từ 1 trong thứ tự của frame.
- `FROM FIRST`: đếm từ đầu frame; đây là mặc định.
- `FROM LAST`: đếm từ cuối frame.
- `RESPECT NULLS`: tính cả null vào vị trí; đây là mặc định.
- `IGNORE NULLS`: bỏ null khi đếm vị trí.

`NTH_VALUE` trả về giá trị ở vị trí thứ N trong **window frame của hàng hiện tại**. Nếu frame chưa chứa đủ N hàng/giá trị theo chế độ null đã chọn, kết quả có thể là NULL.

### 5.1. Lấy mức lương thứ hai cao nhất của mỗi phòng ban

```sql
SELECT employee_id,
       employee_name,
       department_id,
       salary,
       NTH_VALUE(salary, 2) FROM FIRST OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS second_salary
FROM lab_emp_pay_history
ORDER BY department_id, salary DESC NULLS LAST, history_id;
```

Frame toàn partition cho phép mỗi hàng nhìn thấy toàn bộ nhóm. Theo dữ liệu lab:

- Phòng 10: hai mức đầu là 6000 và 6000; giá trị thứ hai là 6000.
- Phòng 20: hai mức đầu là 8000 và 7500; giá trị thứ hai là 7500.

Nếu cần **giá trị lớn thứ hai khác nhau**, `NTH_VALUE` không tự loại duplicate. Có thể dùng `DENSE_RANK` hoặc tạo tập distinct trước, tùy yêu cầu.

### 5.2. Lấy giá trị thứ hai từ cuối

```sql
SELECT employee_id,
       department_id,
       salary,
       NTH_VALUE(salary, 2) FROM LAST OVER (
           PARTITION BY department_id
           ORDER BY salary ASC NULLS FIRST, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS second_from_high_end
FROM lab_emp_pay_history;
```

`FROM LAST` đếm từ cuối frame theo thứ tự được khai báo. Có thể biểu đạt cùng ý định bằng cách đổi hướng `ORDER BY` và dùng `FROM FIRST`, nhưng cần chú ý null ordering và tie. Không nên đảo sort direction mà quên đổi `NULLS FIRST/LAST`.

### 5.3. NTH_VALUE với frame mặc định có thể trả NULL ở các hàng đầu

Ví dụ:

```sql
SELECT employee_id,
       department_id,
       effective_on,
       salary,
       NTH_VALUE(salary, 2) OVER (
           PARTITION BY department_id
           ORDER BY effective_on
       ) AS second_salary_so_far
FROM lab_emp_pay_history
ORDER BY department_id, effective_on;
```

Với frame mặc định `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, các hàng đầu partition chưa có đủ hai hàng trong frame nên `NTH_VALUE(..., 2)` trả NULL. Khi frame mở rộng tới ít nhất hai hàng, hàm có thể trả giá trị thứ hai theo thứ tự. Kết quả không phải “giá trị thứ hai của cả partition” lặp trên mọi hàng.

Nếu muốn giá trị thứ hai của **toàn bộ partition**, khai báo frame đầy đủ:

```sql
NTH_VALUE(salary, 2) OVER (
    PARTITION BY department_id
    ORDER BY salary DESC NULLS LAST, history_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

### 5.4. NTH_VALUE với IGNORE NULLS

```sql
SELECT employee_id,
       department_id,
       effective_on,
       salary,
       NTH_VALUE(salary, 2) IGNORE NULLS OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS second_known_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Với `IGNORE NULLS`, Oracle bỏ qua các hàng có `SALARY IS NULL` khi xác định vị trí thứ hai. Nếu partition không có đủ hai giá trị không null, kết quả là NULL.

## 6. ROWS và RANGE: hai loại window frame khác nhau

Đây là phần nền tảng để hiểu tại sao các hàm `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` có thể trả kết quả khác nhau dù cùng `PARTITION BY` và `ORDER BY`.

### 6.1. ROWS: frame theo số hàng vật lý

`ROWS` xác định frame bằng số hàng trước/sau hàng hiện tại trong thứ tự analytic. Ví dụ:

```sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
```

nghĩa là hàng hiện tại cộng tối đa hai hàng đứng trước nó. Nếu sort key trùng, thứ tự giữa các hàng tie cần được xác định bằng cột phụ để frame không phụ thuộc vào thứ tự không xác định.

### 6.2. RANGE: frame theo giá trị logic của sort key

`RANGE` xác định frame dựa trên giá trị của biểu thức `ORDER BY`, không đơn thuần đếm hàng. Với:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

frame bao gồm các hàng từ đầu partition đến giá trị sort key hiện tại; các hàng **peer** có cùng giá trị sort key được đưa vào frame cùng nhau. Vì vậy, nếu hai hàng có cùng ngày hiệu lực, `CURRENT ROW` theo `RANGE` có thể bao gồm cả hai hàng đó.

### 6.3. Ví dụ ROWS và RANGE với tie

Giả sử dữ liệu:

| `ID` | `SCORE` |
|---:|---:|
| 1 | 10 |
| 2 | 20 |
| 3 | 20 |
| 4 | 30 |

Hai frame:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

và:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

cho phạm vi khác nhau tại các hàng có `SCORE = 20`:

| ID | SCORE | Frame ROWS (khái niệm) | Frame RANGE (khái niệm) |
|---:|---:|---|---|
| 1 | 10 | Hàng 1 | Hàng 1 |
| 2 | 20 | Hàng 1, 2 | Hàng 1, 2, 3 |
| 3 | 20 | Hàng 1, 2, 3 | Hàng 1, 2, 3 |
| 4 | 30 | Hàng 1, 2, 3, 4 | Hàng 1, 2, 3, 4 |

Ở hàng 2, `ROWS` chỉ tính đến hàng vật lý thứ hai; `RANGE` bao gồm cả peer hàng 3 có cùng `SCORE = 20`.

### 6.4. RANGE mặc định là nguyên nhân bẫy LAST_VALUE

Khi có `ORDER BY` mà không chỉ định frame, Oracle dùng frame mặc định tương đương:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Do đó, `LAST_VALUE(expr)` không tự động nhìn tới cuối partition. Nó lấy giá trị ở hàng cuối frame đang có. Để lấy giá trị cuối partition, phải dùng `UNBOUNDED FOLLOWING` hoặc một cấu trúc tương đương.

### 6.5. ROWS thường cần tie-breaker duy nhất

Nếu analytic `ORDER BY` chỉ là `ORDER BY salary DESC` và nhiều hàng có cùng lương, Oracle không có tiêu chí đầy đủ để xác định thứ tự vật lý giữa các hàng đồng hạng. Với `ROWS`, điều này có thể khiến hàng được xem là trước/sau thay đổi giữa các kế hoạch thực thi.

Để kết quả xác định, thêm khóa duy nhất:

```sql
ORDER BY salary DESC, history_id
```

Tuy nhiên, nếu mục tiêu là giữ các peer theo giá trị lương cho `RANK`, `RANGE` hoặc tie semantics, không thêm cột duy nhất vào analytic `ORDER BY` nếu nó làm thay đổi định nghĩa peer. Hãy tách thứ tự xác định của kết quả bên ngoài khỏi sort key dùng để xác định tie.

## 7. Frame toàn partition, frame lũy kế và frame trượt

Ba dạng frame thường gặp:

### 7.1. Toàn bộ partition

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

Mỗi hàng có thể nhìn thấy toàn bộ partition. Dạng này phù hợp khi cần lặp giá trị đầu/cuối/toàn partition trên mọi hàng.

### 7.2. Lũy kế từ đầu đến hiện tại

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Frame mở rộng dần khi đi qua từng hàng. Dạng này thường dùng cho running total, nhưng cũng ảnh hưởng `FIRST_VALUE`/`LAST_VALUE`/`NTH_VALUE`:

- `FIRST_VALUE` thường giữ nguyên giá trị đầu tiên trong partition.
- `LAST_VALUE` trả giá trị ở hàng hiện tại (hoặc peer cuối theo frame RANGE).
- `NTH_VALUE(..., 2)` có thể NULL ở hàng đầu tiên vì frame chưa đủ hai hàng.

### 7.3. Frame trượt

```sql
ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
```

Frame có tối đa 5 hàng: hai hàng trước, hàng hiện tại và hai hàng sau. Với `FIRST_VALUE`/`LAST_VALUE`, giá trị được chọn là đầu/cuối của đoạn trượt. Với `NTH_VALUE`, giá trị thứ N được chọn trong đoạn đó; nếu đoạn ngắn hơn N ở biên partition, kết quả có thể NULL.

Ví dụ:

```sql
SELECT history_id,
       department_id,
       effective_on,
       salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS first_salary_in_recent_3_rows,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS last_salary_in_recent_3_rows
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Ở mỗi hàng, `FIRST_VALUE` trả lương của hàng cũ nhất trong ba hàng gần nhất tính đến hàng hiện tại; `LAST_VALUE` trả lương của hàng hiện tại vì frame kết thúc ở current row. Nếu muốn frame trượt đối xứng có cả hai hàng sau, dùng `2 FOLLOWING` nhưng cần lưu ý truy vấn phải nhìn tới các hàng tương lai theo thứ tự analytic.

## 8. Quy tắc NULL: RESPECT NULLS và IGNORE NULLS

Các hàm `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` mặc định **`RESPECT NULLS`**. Điều này có nghĩa null vẫn tham gia vào việc xác định vị trí đầu/cuối/thứ N.

### 8.1. RESPECT NULLS

```sql
LAST_VALUE(salary) RESPECT NULLS OVER (
    PARTITION BY department_id
    ORDER BY effective_on, history_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

Nếu hàng cuối có `SALARY = NULL`, kết quả là NULL. `RESPECT NULLS` là mặc định, nên có thể lược bỏ từ khóa này, nhưng viết tường minh có ích trong bài học hoặc logic cần làm rõ cách xử lý dữ liệu thiếu.

### 8.2. IGNORE NULLS

```sql
LAST_VALUE(salary) IGNORE NULLS OVER (
    PARTITION BY department_id
    ORDER BY effective_on, history_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

Oracle bỏ qua hàng có expression null khi xác định giá trị cuối cùng không null trong frame. Nếu không có giá trị không null nào, kết quả vẫn NULL.

### 8.3. IGNORE NULLS không giống NVL

`IGNORE NULLS` **bỏ qua hàng null khi tìm vị trí**; `NVL`/`COALESCE` thay giá trị null bằng một biểu thức khác. Ví dụ:

```sql
FIRST_VALUE(salary) IGNORE NULLS OVER (...)
```

khác:

```sql
FIRST_VALUE(NVL(salary, 0)) OVER (...)
```

Ở biểu thức thứ hai, null đã được thay bằng 0 trước khi hàm chọn hàng đầu; 0 trở thành một giá trị thực trong logic của window function. Nếu lương 0 có ý nghĩa nghiệp vụ khác với “chưa biết lương”, hai câu truy vấn không thể thay thế nhau.

### 8.4. NULLS FIRST/LAST khác IGNORE NULLS

Hai khái niệm thường bị nhầm:

- `ORDER BY salary DESC NULLS LAST`: xác định **vị trí sắp xếp** của các hàng có salary null.
- `IGNORE NULLS`: bỏ qua các giá trị null của **expression được hàm phân tích** khi chọn first/last/nth value.

Ví dụ:

```sql
LAST_VALUE(salary) IGNORE NULLS OVER (
    PARTITION BY department_id
    ORDER BY effective_on DESC NULLS FIRST, history_id DESC
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

`NULLS FIRST` điều khiển vị trí hàng theo `EFFECTIVE_ON`; `IGNORE NULLS` áp dụng cho expression `SALARY`. Một hàng có ngày không null nhưng lương null vẫn bị bỏ qua khi chọn giá trị lương.

## 9. NTH_VALUE: vị trí thứ N và cách đếm

`NTH_VALUE(expr, n)` cần một giá trị N hợp lệ theo quy định của Oracle. N là số thứ tự dương, bắt đầu từ 1; N không phải “rank distinct” mà là vị trí của hàng/giá trị trong frame theo thứ tự.

### 9.1. NTH_VALUE không loại tie

Nếu hai hàng có cùng salary, cả hai vẫn là hai hàng riêng trong thứ tự. Ví dụ danh sách:

| Thứ tự hàng | Salary |
|---:|---:|
| 1 | 9000 |
| 2 | 8000 |
| 3 | 8000 |
| 4 | 7000 |

`NTH_VALUE(salary, 2)` trả `8000`. `NTH_VALUE(salary, 3)` cũng trả `8000`. Nếu cần mức lương cao thứ hai **khác nhau**, dùng `DENSE_RANK` hoặc distinct subquery thay vì `NTH_VALUE`.

### 9.2. FROM FIRST và FROM LAST

```sql
NTH_VALUE(salary, 2) FROM FIRST OVER (...)
```

lấy giá trị thứ hai tính từ đầu frame. Còn:

```sql
NTH_VALUE(salary, 2) FROM LAST OVER (...)
```

lấy giá trị thứ hai tính từ cuối frame. Nếu đổi chiều `ORDER BY`, thứ tự đầu/cuối cũng đổi. Hãy ghi rõ ý nghĩa bằng ngôn ngữ nghiệp vụ, ví dụ “giá trị thứ hai từ ngày sớm nhất” hay “giá trị thứ hai từ ngày gần nhất”, rồi mới chọn `ORDER BY` và `FROM`.

### 9.3. Frame chưa đủ N giá trị

Với frame lũy kế:

```sql
NTH_VALUE(salary, 3) OVER (
    PARTITION BY department_id
    ORDER BY effective_on
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

hai hàng đầu chưa có hàng thứ ba trong frame nên kết quả NULL. Từ hàng thứ ba trở đi, hàm có thể trả giá trị ở vị trí thứ ba. Nếu dùng `IGNORE NULLS`, số vị trí được đếm là các giá trị không null theo expression; frame có thể cần nhiều hơn N hàng vật lý mới có đủ N giá trị.

## 10. ORDER BY, tie và tính xác định

Các hàm value cần một thứ tự để biết đâu là đầu, cuối và thứ N. Nếu sort key không duy nhất, có thể có nhiều hàng peer. Với `ROWS`, vị trí vật lý giữa các peer có thể không xác định nếu không có tie-breaker.

### 10.1. Dùng khóa duy nhất để xác định hàng

```sql
FIRST_VALUE(salary) OVER (
    PARTITION BY department_id
    ORDER BY effective_on, history_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

`HISTORY_ID` phân định hai bản ghi có cùng ngày hiệu lực. Khi nghiệp vụ cần “bản ghi đầu tiên” duy nhất, nên có một tiêu chí phụ ổn định.

### 10.2. Không phá tie nếu tie là một phần nghiệp vụ

Nếu cần coi mọi nhân viên cùng mức lương là đồng hạng, không thêm `EMPLOYEE_ID` vào analytic `ORDER BY` của hàm rank. Với `FIRST_VALUE`/`LAST_VALUE`/`NTH_VALUE`, nếu nhiều hàng có cùng sort key và expression khác nhau, không có một “đầu tiên/cuối cùng” duy nhất nếu không định nghĩa thêm thứ tự. Hãy quyết định:

- Cần chọn **một hàng cụ thể**: thêm tie-breaker duy nhất.
- Cần giữ **peer semantics**: dùng `RANGE` khi phù hợp và hiểu các peer cùng frame; hoặc dùng ranking function để biểu đạt tie.
- Cần trả **mọi hàng đồng hạng**: không kỳ vọng `FIRST_VALUE`/`LAST_VALUE` tự trả nhiều hàng; dùng `RANK`/`DENSE_RANK` và lọc theo rank.

### 10.3. ORDER BY trong OVER khác ORDER BY cuối truy vấn

`ORDER BY` bên trong `OVER (...)` xác định thứ tự để tính hàm; nó **không đảm bảo thứ tự hàng cuối cùng** của câu SELECT. Muốn kết quả hiển thị theo phòng ban, ngày và ID, hãy thêm `ORDER BY` ở cuối:

```sql
SELECT employee_id,
       department_id,
       effective_on,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS first_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

## 11. Ví dụ nghiệp vụ thường gặp

### 11.1. So sánh lương hiện tại với lương đầu tiên của nhân viên

```sql
SELECT employee_id,
       effective_on,
       salary,
       FIRST_VALUE(salary) IGNORE NULLS OVER (
           PARTITION BY employee_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS first_known_salary,
       LAST_VALUE(salary) IGNORE NULLS OVER (
           PARTITION BY employee_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS last_known_salary
FROM employee_salary_history;
```

Truy vấn giả định bảng có nhiều bản ghi lịch sử trên mỗi nhân viên. Có thể dùng kết quả để tính mức thay đổi từ lần ghi nhận đầu tới lần ghi nhận cuối, nhưng cần quy định rõ `NULL`, ngày hiệu lực và tie.

### 11.2. Lấy giá trị đầu/cuối của chuỗi trạng thái

```sql
SELECT account_id,
       event_time,
       status,
       FIRST_VALUE(status) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS initial_status,
       LAST_VALUE(status) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS latest_status
FROM account_status_events;
```

Đây là ví dụ khái niệm với bảng event giả định. `EVENT_ID` là tie-breaker nếu nhiều sự kiện có cùng `EVENT_TIME`. Nếu status null không nên được chọn, thêm `IGNORE NULLS`.

### 11.3. Lấy mức giá thứ ba theo từng loại sản phẩm

```sql
SELECT product_id,
       category_id,
       price,
       NTH_VALUE(price, 3) FROM FIRST OVER (
           PARTITION BY category_id
           ORDER BY price DESC NULLS LAST, product_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS third_price_in_category
FROM products;
```

Mỗi hàng nhận giá trị ở vị trí thứ ba của danh sách giá trong category. Nếu category có ít hơn ba sản phẩm, kết quả có thể NULL. Nếu muốn giá khác nhau thứ ba, cần xử lý duplicate trước.

### 11.4. FIRST_VALUE và LAST_VALUE để so sánh với mức cao nhất/thấp nhất

```sql
SELECT employee_id,
       department_id,
       salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS highest_salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS lowest_salary
FROM employees;
```

Với thứ tự giảm dần, hàng đầu là mức cao nhất và hàng cuối là mức thấp nhất (null đã được đẩy xuống cuối; nếu null tồn tại, `RESPECT NULLS` có thể khiến `LAST_VALUE` là null). Nếu cần mức thấp nhất không null, dùng `IGNORE NULLS` hoặc lọc dữ liệu theo nghiệp vụ.

## 12. Các lỗi thường gặp

| Triệu chứng/nhận định | Nguyên nhân | Cách xử lý |
|---|---|---|
| `LAST_VALUE` trả giá trị giống hàng hiện tại | Frame mặc định kết thúc tại current row | Khai báo `ROWS/RANGE ... UNBOUNDED FOLLOWING` nếu cần cuối partition |
| `NTH_VALUE(..., 2)` trả NULL ở các hàng đầu | Frame lũy kế chưa chứa đủ hai vị trí | Dùng frame toàn partition nếu cần giá trị thứ hai của cả nhóm |
| `FIRST_VALUE` trả NULL dù phía sau có giá trị | Hàng đầu frame có expression NULL và mặc định RESPECT NULLS | Dùng IGNORE NULLS nếu nghiệp vụ muốn bỏ qua null |
| `LAST_VALUE` trả NULL trên cả partition | Hàng cuối partition có expression NULL | Dùng IGNORE NULLS nếu cần giá trị cuối đã biết |
| Kết quả thay đổi giữa các lần chạy khi tie | Analytic ORDER BY chưa đủ xác định | Thêm khóa phụ duy nhất nếu cần chọn một hàng cụ thể |
| Thêm ID làm mất tie | ID được đưa vào sort key dùng để xác định peer | Tách tie key trong analytic khỏi thứ tự trình bày ngoài |
| `ROWS` và `RANGE` trả kết quả khác nhau | ROWS đếm hàng; RANGE gom peer theo giá trị sort key | Chọn frame đúng ý nghĩa và kiểm thử duplicate sort key |
| Nghĩ ORDER BY trong OVER sắp kết quả cuối | Analytic ORDER BY chỉ điều khiển phép tính | Thêm ORDER BY ở cuối SELECT |
| Lọc alias analytic trực tiếp trong WHERE lỗi | WHERE được xử lý trước analytic trong query block | Bọc bằng CTE/inline view |
| NTH_VALUE trả giá trị lặp nhưng mong thứ hạng khác nhau | NTH_VALUE đếm vị trí hàng, không distinct giá trị | Dùng DENSE_RANK hoặc distinct set |
| Dùng NULLS LAST nhưng vẫn thấy NULL được chọn | NULLS LAST chỉ sắp xếp; frame vẫn chứa hàng null | Dùng IGNORE NULLS hoặc lọc null theo yêu cầu |

## 13. Bài thực hành có kiểm soát

Các bài tập dùng `LAB_EMP_PAY_HISTORY` đã tạo trong phần 2. Chỉ chạy trên schema DEV/TEST được cấp quyền và đúng PDB/service. Không chạy DDL hoặc thao tác dọn dẹp trên production.

### Bài 1 — FIRST_VALUE trên toàn partition

```sql
SELECT history_id, department_id, effective_on, salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS first_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Ghi lại giá trị đầu tiên theo ngày của mỗi phòng ban và giải thích vì sao giá trị đó được lặp trên các hàng cùng phòng ban.

### Bài 2 — LAST_VALUE mặc định và frame toàn partition

Chạy hai truy vấn:

```sql
SELECT history_id, department_id, effective_on, salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
       ) AS last_default
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

```sql
SELECT history_id, department_id, effective_on, salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS last_full_partition
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

So sánh kết quả và giải thích bẫy frame mặc định.

### Bài 3 — RESPECT NULLS và IGNORE NULLS

```sql
SELECT history_id, department_id, effective_on, salary,
       LAST_VALUE(salary) RESPECT NULLS OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS last_respect,
       LAST_VALUE(salary) IGNORE NULLS OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS last_ignore
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Giải thích vì sao phòng 10 có kết quả khác nhau giữa hai cột.

### Bài 4 — NTH_VALUE toàn partition

```sql
SELECT history_id, department_id, salary,
       NTH_VALUE(salary, 2) FROM FIRST OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS second_salary
FROM lab_emp_pay_history
ORDER BY department_id, salary DESC NULLS LAST, history_id;
```

Xác định giá trị thứ hai theo vị trí hàng, rồi giải thích vì sao tie vẫn chiếm hai vị trí.

### Bài 5 — NTH_VALUE với frame lũy kế

```sql
SELECT history_id, department_id, effective_on, salary,
       NTH_VALUE(salary, 2) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS second_so_far
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Quan sát các hàng đầu mỗi partition và giải thích vì sao chưa đủ hai hàng nên kết quả là NULL.

### Bài 6 — ROWS và RANGE khi có peer

Tạo một bảng lab nhỏ có các giá trị sort key trùng nhau, sau đó so sánh `LAST_VALUE` hoặc một aggregate analytic với:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

và:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Quan sát frame tại hàng đầu tiên trong nhóm peer và giải thích sự khác nhau giữa logical offset và physical row offset.

### Bài 7 — Phân biệt NTH_VALUE và DENSE_RANK

Với một tập lương có các giá trị `10000, 9000, 9000, 8000`, dùng `NTH_VALUE(salary, 3)` và `DENSE_RANK()`. Giải thích vì sao giá trị thứ ba theo hàng có thể là 9000 nhưng mức lương khác nhau thứ ba là 8000.

### Thu dọn dữ liệu lab

Chỉ khi xác nhận đúng bảng do mình tạo trong DEV/TEST và không có người khác sử dụng:

```sql
DROP TABLE lab_emp_pay_history PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, không đưa vào recycle bin; đây là thao tác DDL có implicit commit. Không chạy trên production hoặc bất kỳ bảng nào ngoài phạm vi bài thực hành.

## 14. Câu hỏi ôn tập

**Câu 1.** `FIRST_VALUE(salary)` trả về giá trị nào?

**Đáp án:** Giá trị expression ở hàng đầu tiên trong window frame theo thứ tự analytic `ORDER BY`.

**Câu 2.** Vì sao `LAST_VALUE` thường không trả giá trị cuối partition nếu bỏ windowing clause?

**Đáp án:** Vì frame mặc định khi có ORDER BY là `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`; frame kết thúc tại current row/peer, không kéo tới cuối partition.

**Câu 3.** Muốn `LAST_VALUE` nhìn toàn bộ partition, viết frame thế nào?

**Đáp án:** `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` (hoặc frame phù hợp tương đương).

**Câu 4.** `NTH_VALUE(expr, 2)` có nghĩa là giá trị khác nhau lớn thứ hai không?

**Đáp án:** Không. Nó là giá trị tại vị trí thứ hai trong frame; tie vẫn chiếm các vị trí riêng. Muốn mức distinct thứ hai, cân nhắc `DENSE_RANK`.

**Câu 5.** `FROM LAST` trong `NTH_VALUE` làm gì?

**Đáp án:** Đếm vị trí N từ cuối window frame thay vì từ đầu frame.

**Câu 6.** Mặc định ba hàm value xử lý NULL theo chế độ nào?

**Đáp án:** `RESPECT NULLS`; có thể chỉ định `IGNORE NULLS` để bỏ qua giá trị null của expression khi chọn vị trí.

**Câu 7.** `NULLS LAST` có giống `IGNORE NULLS` không?

**Đáp án:** Không. `NULLS LAST` sắp xếp hàng null xuống cuối; `IGNORE NULLS` bỏ qua giá trị null khi hàm xác định first/last/nth expression.

**Câu 8.** `ROWS` và `RANGE` khác nhau thế nào?

**Đáp án:** `ROWS` định nghĩa frame theo số hàng vật lý trong thứ tự; `RANGE` định nghĩa theo giá trị sort key và bao gồm các peer có cùng giá trị ở ranh giới.

**Câu 9.** Vì sao cần tie-breaker cho ROWS khi sort key không duy nhất?

**Đáp án:** Để xác định thứ tự vật lý giữa các hàng đồng hạng và làm kết quả ổn định/deterministic.

**Câu 10.** `ORDER BY` trong `OVER(...)` có sắp xếp kết quả SELECT cuối cùng không?

**Đáp án:** Không. Nó chỉ điều khiển thứ tự tính analytic function; muốn sắp kết quả hiển thị phải có ORDER BY ở query ngoài cùng.

## Kết luận

**`FIRST_VALUE`**, **`LAST_VALUE`** và **`NTH_VALUE`** chọn giá trị đầu, cuối hoặc thứ N trong **window frame hiện tại**, không mặc nhiên là toàn bộ partition. Khi có analytic `ORDER BY` mà bỏ windowing clause, Oracle dùng frame mặc định tương đương `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Đây là nguyên nhân phổ biến khiến `LAST_VALUE` chỉ trả giá trị của hàng hiện tại/peer thay vì giá trị cuối nhóm. Muốn lấy giá trị cuối toàn partition, khai báo frame tới `UNBOUNDED FOLLOWING`.

`ROWS` xác định frame theo hàng vật lý, còn `RANGE` xác định theo giá trị sort key và xử lý các peer cùng giá trị trong frame. `RESPECT NULLS` là mặc định; `IGNORE NULLS` bỏ qua null khi chọn giá trị, khác với `NULLS FIRST/LAST` chỉ quyết định vị trí sắp xếp. `NTH_VALUE` đếm vị trí hàng trong frame, không tự loại duplicate để tìm mức giá trị khác nhau thứ N. Khi thiết kế truy vấn, hãy xác định partition, sort key, tie-breaker, frame và chính sách NULL một cách tường minh; đồng thời thêm `ORDER BY` ngoài cùng nếu cần thứ tự kết quả ổn định.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c — FIRST_VALUE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FIRST_VALUE.html): cú pháp, window frame và RESPECT/IGNORE NULLS.
- [Oracle Database 19c — LAST_VALUE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LAST_VALUE.html): hành vi LAST_VALUE và lưu ý windowing clause mặc định.
- [Oracle Database 19c — NTH_VALUE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NTH_VALUE.html): FROM FIRST/FROM LAST và RESPECT/IGNORE NULLS.
- [Oracle Database 19c — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): thứ tự xử lý analytic functions, partition, order và windowing clause.
- [Oracle Database 19c — Windowing Clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): quy tắc ROWS/RANGE và frame mặc định trong analytic clause.

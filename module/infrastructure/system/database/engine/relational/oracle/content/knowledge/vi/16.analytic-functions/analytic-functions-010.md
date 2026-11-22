# KEEP (DENSE_RANK FIRST/LAST) trong phép tổng hợp Oracle

Trong Oracle Database, đôi khi ta cần tính một giá trị tổng hợp nhưng chỉ trên những hàng có thứ hạng đầu tiên hoặc cuối cùng theo một tiêu chí. Ví dụ:

- Tìm **mức lương cao nhất trong số những nhân viên được tuyển sớm nhất** của từng phòng ban.
- Tính **tổng tiền của các giao dịch có ngày mới nhất** trong mỗi tài khoản.
- Đếm **số nhân viên đồng hạng** ở mức doanh số cao nhất.
- Lấy giá trị hoa hồng nhỏ nhất trong nhóm nhân viên có tỷ lệ hoa hồng cao nhất.

Oracle cung cấp cú pháp **`KEEP (DENSE_RANK FIRST ...)`** và **`KEEP (DENSE_RANK LAST ...)`** để giải quyết các yêu cầu này. Cú pháp thường được dùng cùng hàm tổng hợp như `MIN`, `MAX`, `SUM`, `AVG` hoặc `COUNT`.

Điểm cốt lõi là `KEEP` thực hiện hai ý tưởng liên tiếp:

1. Xếp hạng các hàng theo biểu thức trong `ORDER BY` bằng `DENSE_RANK`, rồi chọn tất cả hàng thuộc hạng đầu tiên (`FIRST`) hoặc hạng cuối cùng (`LAST`).
2. Áp dụng hàm tổng hợp lên biểu thức được chỉ định, nhưng chỉ trên tập hàng vừa chọn.

Vì vậy, `KEEP` **không mặc định chọn đúng một hàng**. Nếu nhiều hàng đồng hạng ở đầu hoặc cuối, hàm tổng hợp sẽ xử lý tất cả các hàng đó. Hiểu đúng tie, `NULL`, thứ tự `ASC`/`DESC` và sự khác nhau giữa aggregate với analytic là điều cần thiết để tránh kết quả sai.

## 1. Cú pháp và ý nghĩa tổng quát

Cấu trúc thường gặp:

```sql
aggregate_function(expression)
    KEEP (
        DENSE_RANK FIRST
        ORDER BY sort_expression [ASC | DESC] [NULLS FIRST | NULLS LAST]
    )
```

Hoặc dùng `LAST`:

```sql
aggregate_function(expression)
    KEEP (
        DENSE_RANK LAST
        ORDER BY sort_expression [ASC | DESC] [NULLS FIRST | NULLS LAST]
    )
```

Có thể thêm `OVER (PARTITION BY ...)` để sử dụng dạng analytic:

```sql
aggregate_function(expression)
    KEEP (DENSE_RANK FIRST ORDER BY sort_expression)
    OVER (PARTITION BY group_expression)
```

Trong đó:

- `aggregate_function`: hàm tổng hợp áp dụng lên các hàng được giữ lại, thường là `MIN`, `MAX`, `SUM`, `AVG`, `COUNT`, `VARIANCE` hoặc `STDDEV`.
- `expression`: giá trị sẽ được tổng hợp; không nhất thiết là cột được dùng để xếp hạng.
- `DENSE_RANK FIRST`: chọn tập hàng có dense rank đầu tiên theo thứ tự đã khai báo.
- `DENSE_RANK LAST`: chọn tập hàng có dense rank cuối cùng theo thứ tự đã khai báo.
- `ORDER BY`: xác định tiêu chí và hướng xếp hạng; có thể có nhiều biểu thức.
- `OVER (PARTITION BY ...)`: chuyển phép tổng hợp thành analytic, tính riêng trong từng partition và trả kết quả bên cạnh từng hàng.

### 1.1. Quy trình hoạt động

```text
Các hàng trong một nhóm
          |
          v
Xếp hạng theo ORDER BY trong KEEP
          |
          v
DENSE_RANK FIRST hoặc DENSE_RANK LAST
          |
          v
Giữ toàn bộ hàng thuộc hạng đầu/cuối
          |
          v
Áp dụng MIN / MAX / SUM / AVG / COUNT...
          |
          v
Một giá trị tổng hợp cho nhóm/partition
```

Ví dụ:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC
)
```

Biểu thức trên **không có nghĩa** “lấy lương lớn nhất trong toàn bộ bảng”. Nó có nghĩa:

1. Tìm ngày tuyển dụng sớm nhất theo `HIRE_DATE ASC`.
2. Giữ tất cả nhân viên có ngày tuyển dụng thuộc hạng đầu tiên.
3. Tính `MAX(SALARY)` trên những nhân viên được giữ.

Nếu có ba người cùng ngày tuyển dụng sớm nhất, cả ba đều tham gia phép `MAX`.

## 2. FIRST và LAST phụ thuộc hướng ORDER BY

`FIRST` và `LAST` chỉ vị trí theo **thứ tự đã khai báo**, không phải luôn luôn là giá trị nhỏ nhất/lớn nhất theo trực giác.

| Biểu thức xếp hạng | `DENSE_RANK FIRST` chọn | `DENSE_RANK LAST` chọn |
|---|---|---|
| `ORDER BY hire_date ASC` | Ngày sớm nhất | Ngày muộn nhất |
| `ORDER BY hire_date DESC` | Ngày muộn nhất | Ngày sớm nhất |
| `ORDER BY salary ASC` | Mức lương thấp nhất | Mức lương cao nhất |
| `ORDER BY salary DESC` | Mức lương cao nhất | Mức lương thấp nhất |

Do đó, hai biểu thức sau có thể chọn cùng một nhóm hàng nếu không xét NULL:

```sql
MAX(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date DESC)
```

và:

```sql
MAX(salary) KEEP (DENSE_RANK LAST ORDER BY hire_date ASC)
```

Cả hai đều chọn các hàng có ngày tuyển dụng muộn nhất, rồi lấy mức lương cao nhất trong tập đó. Dù vậy, hãy chọn cách viết dễ đọc với nghiệp vụ và ghi rõ hướng sort.

### 2.1. Nhiều cột trong ORDER BY

Có thể xếp hạng theo nhiều tiêu chí:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST
    ORDER BY hire_date ASC, employee_id ASC
)
```

Khi đó, tập hàng được giữ là các hàng có tổ hợp sort key đứng đầu theo thứ tự từ trái sang phải. `EMPLOYEE_ID` có thể phá tie giữa những người cùng ngày tuyển dụng. Nếu `EMPLOYEE_ID` là duy nhất, kết quả thường chỉ còn một hàng ở hạng đầu tiên.

**Chú ý:** thêm cột vào `ORDER BY` có thể thay đổi tập tie. Nếu nghiệp vụ muốn tổng hợp tất cả nhân viên đồng ngày tuyển dụng, không thêm một khóa duy nhất vào thứ tự bên trong `KEEP`. Chỉ thêm tiêu chí phụ khi thực sự muốn phân định các hàng đó.

## 3. Chuẩn bị dữ liệu thực hành

Các ví dụ sử dụng bảng giả `LAB_KEEP_EMPLOYEES`, lưu thông tin nhân viên, phòng ban, ngày tuyển dụng, lương và tỷ lệ hoa hồng. Dữ liệu cố ý có nhiều người cùng ngày tuyển dụng và cùng mức lương để quan sát `DENSE_RANK FIRST/LAST` khi có tie.

Chỉ tạo bảng trong schema **DEV/TEST** được cấp quyền `CREATE TABLE` và quota. Trước khi chạy DDL, xác nhận đúng service, PDB và user:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

### 3.1. Tạo bảng lab

```sql
CREATE TABLE lab_keep_employees (
    employee_id   NUMBER PRIMARY KEY,
    employee_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    hire_date     DATE,
    salary        NUMBER(12, 2),
    commission_pct NUMBER(5, 2)
);
```

`HIRE_DATE`, `SALARY` và `COMMISSION_PCT` cho phép `NULL` để minh họa cách null tham gia vào thứ tự và phép tổng hợp. Trong hệ thống thật, cần xác định ý nghĩa nghiệp vụ của từng null; không tự coi null là 0 hoặc ngày xa trong tương lai.

### 3.2. Nạp dữ liệu giả

```sql
INSERT ALL
    INTO lab_keep_employees VALUES (101, 'An',    10, DATE '2020-01-01', 5000, 0.10)
    INTO lab_keep_employees VALUES (102, 'Binh',  10, DATE '2020-01-01', 6000, 0.20)
    INTO lab_keep_employees VALUES (103, 'Chi',   10, DATE '2021-01-01', 7000, 0.15)
    INTO lab_keep_employees VALUES (104, 'Dung',  10, DATE '2022-01-01', 6500, NULL)
    INTO lab_keep_employees VALUES (105, 'Em',    10, DATE '2022-01-01', 6800, 0.05)
    INTO lab_keep_employees VALUES (201, 'Giang', 20, DATE '2019-06-01', 8000, 0.10)
    INTO lab_keep_employees VALUES (202, 'Ha',    20, DATE '2020-06-01', 7500, NULL)
    INTO lab_keep_employees VALUES (203, 'Khanh', 20, DATE '2020-06-01', 7800, 0.20)
    INTO lab_keep_employees VALUES (204, 'Lan',   20, DATE '2021-06-01', 7200, 0.15)
    INTO lab_keep_employees VALUES (301, 'Minh',  30, DATE '2023-01-01', 6000, NULL)
    INTO lab_keep_employees VALUES (302, 'Nhi',   30, DATE '2023-01-01', 6200, 0.10)
    INTO lab_keep_employees VALUES (303, 'Oanh',  30, DATE '2024-01-01', 6100, 0.20)
    INTO lab_keep_employees VALUES (401, 'Phuc',  40, NULL,              5500, 0.12)
    INTO lab_keep_employees VALUES (402, 'Quynh', 40, NULL,              5700, 0.18)
    INTO lab_keep_employees VALUES (403, 'Son',   40, DATE '2024-05-01', 5900, 0.15)
SELECT 1 FROM dual;

COMMIT;
```

Dữ liệu có bốn phòng ban:

- Phòng 10: hai nhân viên được tuyển cùng ngày sớm nhất (01/01/2020) và hai nhân viên cùng ngày muộn nhất (01/01/2022).
- Phòng 20: hai nhân viên cùng ngày 01/06/2020.
- Phòng 30: hai nhân viên cùng ngày 01/01/2023.
- Phòng 40: hai nhân viên có `HIRE_DATE = NULL` và một nhân viên có ngày tuyển dụng xác định.

### 3.3. Xem dữ liệu nguồn

```sql
SELECT employee_id, employee_name, department_id,
       hire_date, salary, commission_pct
FROM lab_keep_employees
ORDER BY department_id, hire_date NULLS LAST, employee_id;
```

`ORDER BY` cuối chỉ sắp xếp kết quả hiển thị. Nó không quyết định cách `KEEP` xếp hạng; việc đó được quy định riêng trong `ORDER BY` nằm bên trong `KEEP`.

## 4. KEEP với GROUP BY: tổng hợp hàng đầu tiên/cuối cùng trong mỗi nhóm

Yêu cầu ví dụ: “Với mỗi phòng ban, tìm ngày tuyển dụng sớm nhất, mức lương cao nhất trong nhóm nhân viên được tuyển sớm nhất và số nhân viên cùng ngày tuyển sớm nhất.”

```sql
SELECT department_id,
       MIN(hire_date) AS earliest_hire_date,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS highest_salary_at_earliest_hire,
       MIN(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS lowest_salary_at_earliest_hire,
       COUNT(*) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS employees_at_earliest_hire
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

Phân tích:

1. `GROUP BY department_id` tạo một nhóm cho mỗi phòng ban.
2. `MIN(hire_date)` lấy ngày tuyển dụng sớm nhất của nhóm.
3. `DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST` chọn tất cả hàng có ngày tuyển dụng sớm nhất không null; nếu ngày trùng, tất cả cùng hạng đầu được giữ.
4. `MAX(salary)` lấy mức lương lớn nhất trong nhóm được giữ.
5. `MIN(salary)` lấy mức lương nhỏ nhất trong chính nhóm được giữ.
6. `COUNT(*)` đếm số hàng trong nhóm được giữ, kể cả khi một cột dữ liệu khác là null.

Kết quả theo dữ liệu lab:

| Phòng ban | Ngày tuyển sớm nhất | Lương cao nhất trong nhóm đầu | Lương thấp nhất trong nhóm đầu | Số người ở nhóm đầu |
|---:|---|---:|---:|---:|
| 10 | 2020-01-01 | 6000 | 5000 | 2 |
| 20 | 2019-06-01 | 8000 | 8000 | 1 |
| 30 | 2023-01-01 | 6200 | 6000 | 2 |
| 40 | 2024-05-01 | 5900 | 5900 | 1 |

Phòng 40 có hai `HIRE_DATE = NULL`. Do biểu thức dùng `ASC NULLS LAST`, các null được xếp sau ngày có giá trị. `DENSE_RANK FIRST` chọn ngày xác định 01/05/2024, không chọn các hàng null.

### 4.1. KEEP với LAST: nhóm nhân viên được tuyển muộn nhất

```sql
SELECT department_id,
       MAX(hire_date) AS latest_hire_date,
       MIN(salary) KEEP (
           DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
       ) AS lowest_salary_at_last_rank,
       MAX(salary) KEEP (
           DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
       ) AS highest_salary_at_last_rank,
       COUNT(*) KEEP (
           DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
       ) AS employees_at_last_rank
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

Với `ASC NULLS LAST`, `DENSE_RANK LAST` chọn ngày muộn nhất **bao gồm cả null ở vị trí cuối nếu partition có null**. Vì vậy, theo dữ liệu lab:

- Phòng 10: ngày cuối 01/01/2022; hai người Dung/Em được chọn, lương thấp nhất 6500, cao nhất 6800, số người 2.
- Phòng 20: ngày cuối 01/06/2021; Lan được chọn.
- Phòng 30: ngày cuối 01/01/2024; Oanh được chọn.
- Phòng 40: do hai ngày null được xếp cuối theo `NULLS LAST`, nhóm hạng cuối là Phuc và Quynh; `MAX(hire_date)` vẫn trả ngày 01/05/2024 nhưng `KEEP LAST` lại đang chọn các hàng có `HIRE_DATE = NULL`.

Ví dụ phòng 40 cho thấy `MAX(hire_date)` và `DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST` có thể không mô tả cùng một tập hàng nếu có null. Nếu mục tiêu là “ngày tuyển muộn nhất có giá trị”, hãy xếp `DESC NULLS LAST` và chọn `FIRST`, hoặc lọc null theo quy tắc nghiệp vụ.

## 5. FIRST/LAST với ASC và DESC trong thực tế

Khi cần nhóm ngày tuyển muộn nhất nhưng bỏ qua ngày null, biểu thức dễ đọc là:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
)
```

`DESC` đưa ngày muộn nhất lên đầu; `NULLS LAST` đảm bảo hàng thiếu ngày không được ưu tiên; `FIRST` chọn ngày muộn nhất có giá trị. Cách này thường trực quan hơn `DENSE_RANK LAST ORDER BY hire_date ASC` khi cột cho phép null.

| Mục tiêu | Biểu thức KEEP gợi ý |
|---|---|
| Giá trị tổng hợp ở ngày sớm nhất có giá trị | `... KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST)` |
| Giá trị tổng hợp ở ngày muộn nhất có giá trị | `... KEEP (DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST)` |
| Giá trị tổng hợp ở ngày lớn nhất, đồng ý coi NULL là hạng cuối | `... KEEP (DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST)` |
| Giá trị tổng hợp ở ngày nhỏ nhất, đồng ý coi NULL là hạng cuối theo DESC | `... KEEP (DENSE_RANK LAST ORDER BY hire_date DESC NULLS LAST)` |

Hãy viết đúng yêu cầu null của nghiệp vụ thay vì ghi nhớ máy móc “FIRST là nhỏ nhất, LAST là lớn nhất”.

## 6. KEEP áp dụng aggregate nào?

`KEEP` là phần bổ nghĩa cho hàm tổng hợp. Các hàm thường dùng gồm:

| Aggregate | Ý nghĩa trên tập hàng được giữ |
|---|---|
| `MIN(expr)` | Giá trị nhỏ nhất của expr trong tập tie |
| `MAX(expr)` | Giá trị lớn nhất của expr trong tập tie |
| `SUM(expr)` | Tổng expr của các hàng tie |
| `AVG(expr)` | Trung bình expr của các hàng tie |
| `COUNT(expr)` | Đếm các hàng tie có expr không null |
| `COUNT(*)` | Đếm tất cả hàng tie, không phụ thuộc expr có null hay không |
| `VARIANCE(expr)` | Phương sai của expr trong tập tie |
| `STDDEV(expr)` | Độ lệch chuẩn của expr trong tập tie |

Ví dụ với nhóm nhân viên được tuyển muộn nhất (ngày muộn nhất không null):

```sql
SELECT department_id,
       SUM(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
       ) AS total_salary_of_latest_hires,
       AVG(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
       ) AS average_salary_of_latest_hires,
       COUNT(*) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
       ) AS latest_hire_count
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

Nếu nhiều nhân viên có cùng ngày muộn nhất, `SUM` cộng tất cả lương của họ; `AVG` lấy trung bình trên các lương không null; `COUNT(*)` đếm mọi hàng thuộc ngày đó.

### 6.1. COUNT(*) và COUNT(expression) khác nhau

Giả sử các hàng được giữ có `COMMISSION_PCT` lần lượt là `0.10`, `NULL`, `0.20`:

```sql
COUNT(*) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
)
```

trả `3`, còn:

```sql
COUNT(commission_pct) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
)
```

trả `2`. `COUNT(*)` đếm hàng; `COUNT(expression)` chỉ đếm giá trị expression không null trong tập hạng đầu/cuối.

### 6.2. MIN/MAX sau KEEP không nhất thiết trả một hàng duy nhất

Giả sử hai nhân viên được tuyển cùng ngày đầu tiên, một người lương 5000 và một người lương 6000. Khi đó:

```sql
MAX(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date)
```

trả `6000`, còn:

```sql
MIN(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date)
```

trả `5000`. Cả hai đều đúng vì chúng tổng hợp trên **cùng tập tie** nhưng dùng aggregate khác nhau.

### 6.3. Khi aggregate expression toàn NULL

Nếu các hàng được giữ đều có `SALARY = NULL`:

- `MIN(salary) KEEP (...)` trả NULL.
- `MAX(salary) KEEP (...)` trả NULL.
- `SUM(salary) KEEP (...)` trả NULL.
- `AVG(salary) KEEP (...)` trả NULL.
- `COUNT(salary) KEEP (...)` trả 0.
- `COUNT(*) KEEP (...)` vẫn đếm số hàng được giữ.

Null trong **sort key** và null trong **aggregate expression** là hai vấn đề riêng. Một hàng có thể được chọn vì sort key của nó đứng đầu, nhưng expression được tổng hợp lại null.

## 7. Tie: DENSE_RANK FIRST/LAST giữ tất cả hàng đồng hạng

`DENSE_RANK` cấp cùng một hạng cho các hàng có cùng tổ hợp giá trị trong analytic/order expression. `KEEP` chọn tập hàng có hạng đầu hoặc cuối. Do đó, nếu nhiều hàng có cùng sort key ở ranh giới, **tất cả đều tham gia aggregate**.

Ví dụ:

| Nhân viên | Hire date | Salary |
|---|---|---:|
| An | 2020-01-01 | 5000 |
| Binh | 2020-01-01 | 6000 |
| Chi | 2021-01-01 | 7000 |

Biểu thức:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC
)
```

chọn An và Binh vì cả hai có ngày sớm nhất, rồi lấy `MAX(5000, 6000) = 6000`.

### 7.1. Thêm tie-breaker làm thay đổi tập được giữ

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC, employee_id ASC
)
```

Nếu `EMPLOYEE_ID` là duy nhất, chỉ một hàng được chọn ở hạng đầu. Kết quả lúc đó là lương của người có ngày tuyển sớm nhất và ID nhỏ nhất trong nhóm đó. Đây là logic khác với “tổng hợp trên tất cả nhân viên được tuyển cùng ngày sớm nhất”.

### 7.2. Nhiều cột ORDER BY tạo tie theo cả tổ hợp

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST
    ORDER BY hire_date ASC, commission_pct DESC
)
```

Hạng đầu được xác định bằng ngày tuyển sớm nhất; nếu nhiều người cùng ngày, ưu tiên commission cao hơn. Chỉ những hàng có cùng cả `HIRE_DATE` và `COMMISSION_PCT` với tổ hợp đầu tiên mới tie ở hạng đầu. Các hàng cùng ngày nhưng commission khác nhau không cùng hạng đầu.

Nếu `COMMISSION_PCT` có null, phải ghi rõ `NULLS FIRST/LAST` theo yêu cầu. Với nhiều sort key, null ordering áp dụng cho từng biểu thức.

## 8. NULL trong ORDER BY của KEEP

Oracle có thứ tự mặc định cho null:

- `ASC`: mặc định `NULLS LAST`.
- `DESC`: mặc định `NULLS FIRST`.

Vì `KEEP` chọn FIRST/LAST theo thứ tự này, null có thể trở thành nhóm được chọn nếu không khai báo rõ.

### 8.1. Chọn ngày sớm nhất không null

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
)
```

Ngày nhỏ nhất đứng đầu; ngày null xuống cuối. Nếu có ít nhất một ngày xác định, FIRST chọn ngày sớm nhất đó.

### 8.2. Chọn ngày muộn nhất không null

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
)
```

Ngày lớn nhất đứng đầu trong thứ tự giảm dần; null xuống cuối. Đây là mẫu rõ ràng để lấy dữ liệu của ngày muộn nhất đã biết.

### 8.3. LAST với ASC NULLS LAST có thể chọn NULL

```sql
MAX(salary) KEEP (
    DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
)
```

Nếu partition có `HIRE_DATE IS NULL`, nhóm null ở cuối và được `DENSE_RANK LAST` chọn. Điều này có thể không phải ý định khi người viết muốn ngày tuyển dụng muộn nhất. Hãy đổi thành `DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST` hoặc lọc null nếu đó là yêu cầu.

### 8.4. NULL trong expression được tổng hợp

Giả sử ngày tuyển dụng đầu tiên được xác định rõ nhưng lương của một số người trong nhóm đó là null. `KEEP` vẫn giữ các hàng đó theo sort key; sau đó `MIN`/`MAX`/`AVG`/`SUM` xử lý null theo quy tắc aggregate thông thường. `COUNT(*)` và `COUNT(salary)` có thể khác nhau như đã trình bày.

## 9. KEEP kết hợp GROUP BY và HAVING

`KEEP` thường xuất hiện trong câu query có `GROUP BY` để trả một dòng cho mỗi nhóm.

```sql
SELECT department_id,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS max_salary_of_earliest_hires,
       COUNT(*) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS earliest_hire_count
FROM lab_keep_employees
GROUP BY department_id
HAVING COUNT(*) >= 2
ORDER BY department_id;
```

`HAVING COUNT(*) >= 2` lọc các nhóm phòng ban có ít nhất hai hàng tổng thể. Nó không lọc số người được chọn bởi `KEEP`; nếu muốn điều kiện dựa trên số hàng ở hạng đầu, có thể lặp lại aggregate `COUNT(*) KEEP (...)` trong `HAVING`:

```sql
HAVING COUNT(*) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
) >= 2
```

Điều kiện thứ hai chỉ giữ phòng ban có ít nhất hai nhân viên đồng hạng ở ngày tuyển sớm nhất. Cần phân biệt `COUNT(*)` toàn nhóm với `COUNT(*) KEEP (...)` trên tập hạng đầu/cuối.

## 10. KEEP dưới dạng analytic với OVER(PARTITION BY)

`KEEP` có thể dùng như analytic function. Khi thêm `OVER (PARTITION BY ...)`, Oracle tính kết quả riêng cho mỗi partition và lặp kết quả trên các hàng của partition đó, thay vì gộp thành một dòng mỗi nhóm.

```sql
SELECT employee_id,
       employee_name,
       department_id,
       hire_date,
       salary,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) OVER (
           PARTITION BY department_id
       ) AS highest_salary_among_earliest_hires
FROM lab_keep_employees
ORDER BY department_id, hire_date NULLS LAST, employee_id;
```

Mỗi nhân viên vẫn xuất hiện thành một hàng. Cột `HIGHEST_SALARY_AMONG_EARLIEST_HIRES` được tính trong phòng ban của nhân viên đó và lặp lại cho mọi hàng cùng phòng ban.

### 10.1. So sánh aggregate và analytic KEEP

| Cách viết | Kết quả |
|---|---|
| `MAX(salary) KEEP (...)` trong query có `GROUP BY department_id` | Một hàng cho mỗi phòng ban |
| `MAX(salary) KEEP (...) OVER (PARTITION BY department_id)` | Giữ từng hàng nhân viên, thêm giá trị tổng hợp của phòng ban |
| `MAX(salary) KEEP (...)` không có GROUP BY/OVER | Một kết quả tổng hợp trên toàn bộ tập hàng đầu vào |

Ví dụ không có `GROUP BY`:

```sql
SELECT MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
) AS max_salary_among_earliest_hires
FROM lab_keep_employees;
```

Truy vấn trả một dòng cho toàn bảng, lấy mức lương lớn nhất trong nhóm nhân viên có ngày tuyển dụng sớm nhất toàn công ty.

### 10.2. OVER của KEEP không phải window frame của FIRST_VALUE/LAST_VALUE

Trong cú pháp analytic `KEEP`, `ORDER BY` nằm bên trong `KEEP (DENSE_RANK ...)`; `OVER` dùng để phân vùng. Không nhầm với:

```sql
LAST_VALUE(salary) OVER (
    PARTITION BY department_id
    ORDER BY hire_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

Đây là analytic value function với window frame. Còn:

```sql
MAX(salary) KEEP (
    DENSE_RANK LAST ORDER BY hire_date
) OVER (PARTITION BY department_id)
```

là aggregate được áp dụng trên tập hàng có dense rank cuối cùng của mỗi partition. Hai biểu thức có thể giải quyết các câu hỏi gần nhau nhưng ngữ nghĩa và cách xử lý tie khác nhau.

## 11. KEEP khác FIRST_VALUE, LAST_VALUE và ROW_NUMBER thế nào?

Các tên gọi dễ gây nhầm lẫn, nhưng mục đích khác nhau:

| Công cụ | Chọn gì? | Xử lý tie |
|---|---|---|
| `FIRST_VALUE(expr)` | Giá trị expr ở hàng đầu của window frame | Trả một giá trị từ hàng đầu; thứ tự tie có thể cần tie-breaker |
| `LAST_VALUE(expr)` | Giá trị expr ở hàng cuối của window frame | Trả một giá trị từ hàng cuối; phải chú ý frame mặc định |
| `NTH_VALUE(expr, n)` | Giá trị expr ở vị trí N trong frame | Đếm vị trí hàng, không aggregate tất cả tie |
| `ROW_NUMBER()` | Gán số riêng cho từng hàng | Tie vẫn bị phân thành các số khác nhau |
| `RANK()` | Gán rank cho hàng theo sort key | Hàng tie cùng rank, có khoảng trống |
| `DENSE_RANK()` | Gán dense rank cho hàng theo sort key | Hàng tie cùng rank, không có khoảng trống |
| `MAX(expr) KEEP (DENSE_RANK FIRST/LAST ...)` | Aggregate expr trên tất cả hàng thuộc hạng đầu/cuối | Tất cả hàng tie đều tham gia aggregate |

### 11.1. Khi muốn lấy toàn bộ một hàng cụ thể, dùng ROW_NUMBER

Nếu yêu cầu là “lấy một nhân viên duy nhất được tuyển sớm nhất; nếu trùng ngày thì chọn ID nhỏ nhất”, dùng:

```sql
WITH ranked AS (
    SELECT e.*,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY hire_date ASC NULLS LAST, employee_id
           ) AS rn
    FROM lab_keep_employees e
)
SELECT employee_id, employee_name, department_id,
       hire_date, salary, commission_pct
FROM ranked
WHERE rn = 1;
```

`ROW_NUMBER` chọn một hàng đầy đủ theo quy tắc tie-breaker. Nếu dùng `KEEP` riêng cho từng cột, các aggregate có thể chọn những giá trị khác nhau từ các hàng tie khác nhau.

### 11.2. Cẩn thận khi lấy nhiều cột bằng KEEP

Ví dụ:

```sql
SELECT department_id,
       MIN(employee_name) KEEP (
           DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
       ) AS selected_name,
       MAX(salary) KEEP (
           DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
       ) AS selected_salary
FROM lab_keep_employees
GROUP BY department_id;
```

Nếu có nhiều nhân viên cùng ngày cuối:

- `MIN(employee_name)` có thể lấy tên nhỏ nhất theo collation.
- `MAX(salary)` có thể lấy mức lương lớn nhất.

Hai giá trị này **không nhất thiết thuộc cùng một nhân viên**. Kết quả ghép `SELECTED_NAME` và `SELECTED_SALARY` có thể tạo thành một cặp không tồn tại trong bất kỳ hàng nguồn nào. Nếu cần các cột từ cùng một bản ghi, hãy dùng `ROW_NUMBER` với thứ tự xác định, hoặc dùng cách khác bảo đảm cùng một hàng được chọn.

### 11.3. Khi cần tất cả hàng tie, dùng DENSE_RANK analytic

Nếu muốn trả toàn bộ nhân viên thuộc ngày tuyển sớm nhất của từng phòng ban:

```sql
WITH ranked AS (
    SELECT e.*,
           DENSE_RANK() OVER (
               PARTITION BY department_id
               ORDER BY hire_date ASC NULLS LAST
           ) AS hire_rank
    FROM lab_keep_employees e
)
SELECT employee_id, employee_name, department_id, hire_date, salary
FROM ranked
WHERE hire_rank = 1
ORDER BY department_id, employee_id;
```

Đây là cách lấy **các hàng** có hạng đầu; `KEEP` phù hợp khi muốn tổng hợp một hay nhiều biểu thức trên tập hàng đó.

## 12. Nhiều tiêu chí trong KEEP và cách xác định peer

`ORDER BY` trong `KEEP` có thể chứa nhiều cột/biểu thức:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST
    ORDER BY hire_date ASC NULLS LAST,
             commission_pct DESC NULLS LAST
)
```

Oracle xếp hạng theo thứ tự từ biểu thức thứ nhất đến biểu thức tiếp theo. Ngày tuyển dụng có mức ưu tiên trước; chỉ khi ngày bằng nhau mới xét commission. Tập hàng ở dense rank đầu tiên là những hàng có cùng tổ hợp sort key đầu tiên.

Nếu commission null, `NULLS LAST` đặt null sau giá trị commission đã biết trong nhóm ngày tuyển đầu. Nếu tất cả commission của nhóm đó null, các hàng null có thể cùng tie ở hạng đầu theo tổ hợp sort key.

### 12.1. Tie không phải chỉ là cùng một cột đầu tiên

Với:

```sql
ORDER BY hire_date, commission_pct
```

hai hàng cùng `HIRE_DATE` nhưng `COMMISSION_PCT` khác nhau không đồng hạng, vì toàn bộ tổ hợp sort key khác nhau. Nếu ý định là tie chỉ theo ngày tuyển, chỉ đặt `HIRE_DATE` trong `ORDER BY` của `KEEP`.

### 12.2. Biểu thức xếp hạng

Có thể xếp hạng theo biểu thức:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST
    ORDER BY TRUNC(hire_date, 'MM') ASC NULLS LAST
)
```

Biểu thức chọn nhóm nhân viên thuộc tháng tuyển dụng sớm nhất, không phải ngày cụ thể sớm nhất. Khi dùng hàm lên cột, cân nhắc datatype, null, timezone (nếu có) và khả năng tái sử dụng index; biểu thức trong `KEEP` quyết định nhóm được chọn.

## 13. Kết hợp KEEP với các aggregate khác

### 13.1. Đếm số người đồng hạng ở mức lương cao nhất

```sql
SELECT department_id,
       MAX(salary) AS highest_salary,
       COUNT(*) KEEP (
           DENSE_RANK FIRST ORDER BY salary DESC NULLS LAST
       ) AS employees_at_highest_salary
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

`DENSE_RANK FIRST ORDER BY salary DESC NULLS LAST` chọn các hàng có mức lương cao nhất không null; `COUNT(*)` đếm tất cả hàng trong tập đó. Trong phòng ban 10, người có lương cao nhất là Chi (7000), nên số người đồng hạng cao nhất là 1. Nếu có hai người cùng lương cao nhất, count sẽ là 2.

### 13.2. Tổng hoa hồng của nhóm có lương cao nhất

```sql
SELECT department_id,
       SUM(commission_pct) KEEP (
           DENSE_RANK FIRST ORDER BY salary DESC NULLS LAST
       ) AS commission_sum_at_top_salary
FROM lab_keep_employees
GROUP BY department_id;
```

Nếu nhiều người cùng lương cao nhất, `SUM` cộng tỷ lệ hoa hồng của tất cả họ. Nếu hoa hồng một người null, `SUM` bỏ qua giá trị null đó; nếu tất cả đều null, kết quả null.

### 13.3. Trung bình lương trong nhóm tuyển muộn nhất

```sql
SELECT department_id,
       AVG(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
       ) AS avg_salary_of_latest_hire_date
FROM lab_keep_employees
GROUP BY department_id;
```

Đây là trung bình lương của tất cả nhân viên thuộc ngày tuyển muộn nhất đã biết. Nếu nhiều người cùng ngày, tất cả được đưa vào phép tính.

### 13.4. Tổng hợp theo nhóm và lọc nhóm bằng HAVING

```sql
SELECT department_id,
       COUNT(*) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS first_hire_count
FROM lab_keep_employees
GROUP BY department_id
HAVING COUNT(*) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
) >= 2
ORDER BY department_id;
```

Truy vấn chỉ giữ phòng ban có ít nhất hai nhân viên cùng ngày tuyển sớm nhất. Trong dữ liệu lab, phòng 10 và 30 có hai người ở ngày sớm nhất; phòng 20 có một; phòng 40 chỉ có một ngày xác định sớm nhất do null bị xếp cuối.

## 14. Chuyển kiểu và datatype của biểu thức

`KEEP` không thay thế quy tắc datatype của Oracle. Biểu thức tổng hợp phải phù hợp với aggregate được gọi; biểu thức `ORDER BY` phải so sánh được theo kiểu dữ liệu của nó.

### 14.1. Không so sánh ngày dưới dạng chuỗi

Không viết:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date_text ASC
)
```

nếu `HIRE_DATE_TEXT` chứa ngày dạng chuỗi không thống nhất. Thứ tự ký tự có thể không trùng thứ tự thời gian. Hãy lưu ngày bằng `DATE`/`TIMESTAMP`, hoặc parse với format rõ:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST
    ORDER BY TO_DATE(hire_date_text, 'YYYY-MM-DD') ASC NULLS LAST
)
```

Chỉ dùng ví dụ này khi toàn bộ giá trị có đúng format; dữ liệu không hợp lệ có thể làm truy vấn lỗi. Tốt hơn là kiểm soát dữ liệu tại bước nhập và dùng datatype ngày trong schema.

### 14.2. Kiểu số và độ chính xác

Nếu expression được tổng hợp là `NUMBER`, kết quả aggregate tuân theo quy tắc kiểu số của Oracle. Không đưa chuỗi tiền tệ có dấu phân cách vào `SUM`/`AVG` rồi dựa vào implicit conversion; parse thành `NUMBER` theo format/NLS rõ ràng hoặc bind số từ ứng dụng.

### 14.3. Kiểu ký tự và collation

Khi `ORDER BY` trong KEEP dùng biểu thức ký tự như `employee_name`, kết quả FIRST/LAST phụ thuộc collation/so sánh ký tự đang áp dụng. `MIN(employee_name)` cũng áp dụng quy tắc so sánh ký tự khi chọn nhỏ nhất trong tập tie. Với dữ liệu đa ngôn ngữ, cần xác định collation và test trường hợp hoa/thường, dấu và Unicode.

## 15. Hiệu năng và index

`KEEP` là cách diễn đạt ngữ nghĩa truy vấn, không phải cam kết rằng Oracle sẽ dùng một index cụ thể. Optimizer có thể chọn full table scan, index scan, sort/group operation hoặc kế hoạch khác dựa trên thống kê và cấu trúc dữ liệu.

### 15.1. Index có thể hỗ trợ nhóm và thứ tự

Với truy vấn:

```sql
SELECT department_id,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS max_salary_at_first_hire
FROM lab_keep_employees
GROUP BY department_id;
```

có thể khảo sát index trên các cột nhóm và sort key, ví dụ:

```sql
CREATE INDEX ix_lab_keep_dept_hire
ON lab_keep_employees (department_id, hire_date);
```

Đây chỉ là ứng viên để thử nghiệm. Tạo index làm tăng storage và chi phí `INSERT`/`UPDATE`/`DELETE`; không đảm bảo optimizer dùng nó hoặc loại bỏ hoàn toàn thao tác sort. Phải đo trên dữ liệu có kích thước và phân bố gần thực tế.

### 15.2. GROUP BY và KEEP có thể cần xử lý tập hàng tie

Oracle phải xác định nhóm dense rank đầu/cuối trong mỗi nhóm hoặc partition rồi tính aggregate. Khi bảng lớn và nhiều nhóm, chi phí có thể phụ thuộc số hàng, sort key, cardinality và memory/TEMP. Không nên thay `KEEP` bằng nhiều correlated subquery chỉ vì nghĩ nó sẽ nhanh hơn; hãy so sánh execution plan và số lần truy cập dữ liệu.

### 15.3. Tránh tính cùng biểu thức lặp không cần thiết

Nếu một query cần nhiều aggregate trên cùng tập tie, có thể lặp `KEEP` với cùng `ORDER BY`:

```sql
SELECT department_id,
       MIN(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST),
       MAX(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST),
       AVG(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST),
       COUNT(*) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST)
FROM lab_keep_employees
GROUP BY department_id;
```

Các biểu thức này có cùng tập hàng tie nhưng phép aggregate khác nhau. Optimizer có thể tối ưu phần công việc chung tùy kế hoạch; không giả định từng biểu thức luôn tạo một lần sort riêng hoặc luôn được gộp. Đánh giá plan khi hiệu năng quan trọng.

## 16. Các lỗi thường gặp

| Triệu chứng/nhận định | Nguyên nhân | Cách xử lý |
|---|---|---|
| `DENSE_RANK LAST ORDER BY date ASC` chọn hàng có date NULL | `ASC` mặc định đặt NULL cuối | Ghi `NULLS LAST`/`FIRST` có chủ đích; dùng `DESC NULLS LAST` + FIRST nếu cần ngày muộn nhất không null |
| Kết quả KEEP không phải một hàng duy nhất | Nhiều hàng cùng dense rank đầu/cuối | Xác định có cần tổng hợp tất cả tie hay chọn một hàng bằng ROW_NUMBER |
| Thêm ID làm kết quả thay đổi | ID phá tie trong sort key | Chỉ thêm tie-breaker khi muốn chọn một hàng cụ thể |
| Các cột được lấy bằng KEEP không cùng thuộc một nhân viên | Mỗi aggregate tính độc lập trên tập tie | Dùng ROW_NUMBER để chọn một hàng nếu cần tuple từ cùng bản ghi |
| Nhầm FIRST là luôn nhỏ nhất | FIRST phụ thuộc ASC/DESC | Kiểm tra hướng ORDER BY |
| Nhầm LAST là LAST_VALUE | KEEP LAST chọn tập dense rank cuối rồi aggregate | Phân biệt aggregate KEEP với analytic value function |
| Dùng COUNT(expr) nhưng muốn đếm tất cả hàng | COUNT(expr) bỏ qua null expression | Dùng COUNT(*) KEEP nếu cần đếm hàng |
| Muốn bỏ qua null nhưng chỉ dùng NULLS LAST | NULLS LAST chỉ sắp xếp null | Dùng IGNORE NULLS không áp dụng cho KEEP; lọc/định nghĩa sort key hoặc aggregate logic riêng |
| Nghĩ KEEP lấy N hàng đầu | FIRST/LAST chỉ chọn một mức dense rank cực trị | Dùng analytic ranking cho Top-N nhiều mức |
| Kết quả khác giữa các môi trường | Implicit conversion, NLS hoặc collation khác | Dùng datatype chuẩn và conversion tường minh |
| Dùng GROUP BY nhưng mong giữ mọi hàng nhân viên | Aggregate query gộp nhóm thành một dòng | Dùng analytic KEEP với OVER(PARTITION BY) hoặc ranking query |
| Dùng MIN/MAX aggregate thay KEEP | MIN/MAX toàn nhóm không giới hạn vào first/last rank | Dùng KEEP khi điều kiện là “trong nhóm có rank đầu/cuối” |

**Lưu ý về NULL:** cú pháp `KEEP` không có tùy chọn `IGNORE NULLS` giống `FIRST_VALUE`/`LAST_VALUE`/`NTH_VALUE`. Nếu muốn bỏ qua null ở sort key, điều khiển bằng `NULLS FIRST/LAST` hoặc lọc tập đầu vào; nếu muốn bỏ qua null ở expression tổng hợp, các aggregate như `MIN`, `MAX`, `SUM`, `AVG` và `COUNT(expr)` đã có quy tắc null riêng. `COUNT(*)` vẫn đếm mọi hàng được giữ.

## 17. Bài thực hành có kiểm soát

Các bài tập dùng `LAB_KEEP_EMPLOYEES` đã tạo trong phần 3. Chỉ chạy trên schema DEV/TEST được cấp quyền và đúng PDB/service. Không chạy DDL hoặc thao tác dọn dẹp trên production.

### Bài 1 — Lương cao nhất trong nhóm tuyển sớm nhất

```sql
SELECT department_id,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS max_salary_at_earliest_hire
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

Ghi kết quả mỗi phòng ban và giải thích vì sao phòng 10 có hai người cùng ngày tuyển sớm nhưng kết quả là một giá trị tổng hợp.

### Bài 2 — Lấy min, max và count trên cùng tập tie

```sql
SELECT department_id,
       MIN(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST) AS min_salary,
       MAX(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST) AS max_salary,
       COUNT(*) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST) AS row_count,
       COUNT(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST) AS salary_count
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

Đối chiếu `ROW_COUNT` với `SALARY_COUNT` và giải thích sự khác nhau khi expression có null.

### Bài 3 — Ngày tuyển muộn nhất không null

```sql
SELECT department_id,
       MAX(hire_date) AS latest_date,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
       ) AS max_salary_at_latest_known_date
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

So sánh với `DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST` ở phòng 40. Giải thích vì sao hai biểu thức không tương đương khi có null.

### Bài 4 — Thay đổi tie bằng tie-breaker

Chạy hai biểu thức:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
)
```

và:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST, employee_id
)
```

Giải thích vì sao phòng 10 có thể cho kết quả khác khi `EMPLOYEE_ID` được thêm vào sort key.

### Bài 5 — KEEP analytic theo partition

```sql
SELECT employee_id, employee_name, department_id, hire_date, salary,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) OVER (PARTITION BY department_id) AS first_hire_group_max_salary
FROM lab_keep_employees
ORDER BY department_id, employee_id;
```

Xác nhận số hàng đầu ra bằng số hàng bảng nguồn và quan sát giá trị được lặp theo phòng ban.

### Bài 6 — So sánh KEEP với DENSE_RANK query

Viết CTE dùng `DENSE_RANK() OVER (PARTITION BY department_id ORDER BY hire_date ASC NULLS LAST)`, lọc rank bằng 1 rồi group theo phòng ban để tính `MAX(salary)`. Đối chiếu kết quả với `MAX(salary) KEEP (...)` và giải thích hai cách biểu đạt cùng mục tiêu.

### Bài 7 — Chứng minh các cột KEEP có thể đến từ các hàng khác nhau

Trong một truy vấn, lấy `MIN(employee_name) KEEP (...)` và `MAX(salary) KEEP (...)` trên nhóm ngày tuyển muộn nhất của phòng 10. Đối chiếu hai giá trị với các hàng Dung và Em; giải thích vì sao cặp kết quả không nhất thiết là một bản ghi gốc.

### Thu dọn dữ liệu lab

Chỉ khi xác nhận đúng bảng do mình tạo trong DEV/TEST và không có người khác sử dụng:

```sql
DROP TABLE lab_keep_employees PURGE;
```

`DROP TABLE ... PURGE` xóa bảng và dữ liệu, không đưa vào recycle bin; đây là thao tác DDL có implicit commit. Không chạy trên production hoặc bất kỳ bảng nào ngoài phạm vi bài thực hành.

## 18. Câu hỏi ôn tập

**Câu 1.** `MAX(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC)` có ý nghĩa gì?

**Đáp án:** Tìm ngày tuyển dụng sớm nhất, giữ tất cả nhân viên có ngày đó, rồi lấy mức lương lớn nhất trong tập nhân viên được giữ.

**Câu 2.** `DENSE_RANK FIRST` có luôn chọn giá trị nhỏ nhất không?

**Đáp án:** Không. Nó chọn hạng đầu theo thứ tự `ORDER BY`; ASC thường đưa giá trị nhỏ lên đầu, DESC đưa giá trị lớn lên đầu.

**Câu 3.** Nếu ba nhân viên cùng ngày tuyển sớm nhất, `KEEP FIRST` giữ mấy hàng?

**Đáp án:** Cả ba hàng đồng hạng đầu. Hàm aggregate sau KEEP tính trên cả ba.

**Câu 4.** Thêm `EMPLOYEE_ID` duy nhất vào `ORDER BY` trong KEEP có thể gây tác động gì?

**Đáp án:** Nó có thể phá tie và làm tập hàng ở hạng đầu/cuối chỉ còn một hàng.

**Câu 5.** `DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST` có thể chọn hàng có hire_date NULL không?

**Đáp án:** Có. Nếu null được xếp cuối và tồn tại hàng null, nhóm null có thể là dense rank cuối cùng.

**Câu 6.** Muốn lấy giá trị tổng hợp ở ngày muộn nhất đã biết, biểu thức nào rõ ràng?

**Đáp án:** `... KEEP (DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST)`.

**Câu 7.** `COUNT(*) KEEP (...)` khác `COUNT(salary) KEEP (...)` như thế nào?

**Đáp án:** COUNT(*) đếm mọi hàng được giữ; COUNT(salary) chỉ đếm hàng có salary không null.

**Câu 8.** KEEP có tự chọn một hàng duy nhất không?

**Đáp án:** Không. Nó giữ tất cả hàng tie ở rank đầu/cuối rồi aggregate. Muốn chọn một hàng, dùng ROW_NUMBER với tie-breaker.

**Câu 9.** Có thể lấy employee_name và salary bằng hai biểu thức KEEP rồi chắc chắn chúng thuộc cùng nhân viên không?

**Đáp án:** Không nếu có tie. Mỗi aggregate có thể chọn giá trị riêng trong tập tie. Dùng ROW_NUMBER để lấy các cột từ cùng một hàng.

**Câu 10.** KEEP analytic với `OVER (PARTITION BY department_id)` khác KEEP trong GROUP BY thế nào?

**Đáp án:** GROUP BY trả một hàng mỗi phòng ban; analytic giữ từng hàng nhân viên và lặp kết quả tổng hợp của phòng ban bên cạnh mỗi hàng.

**Câu 11.** KEEP có giống LAST_VALUE không?

**Đáp án:** Không. KEEP là aggregate trên tập hàng có dense rank đầu/cuối; LAST_VALUE lấy expression tại hàng cuối window frame và phụ thuộc frame.

**Câu 12.** Muốn lấy tất cả nhân viên được tuyển sớm nhất, không tổng hợp lương, nên dùng gì?

**Đáp án:** DENSE_RANK analytic theo phòng ban rồi lọc rank = 1.

## Kết luận

**`KEEP (DENSE_RANK FIRST/LAST ORDER BY ...)` chọn tập hàng thuộc hạng đầu hoặc cuối theo một thứ tự xác định, sau đó áp dụng aggregate lên biểu thức được chọn.** `FIRST` và `LAST` phụ thuộc hướng `ASC`/`DESC`; nếu nhiều hàng đồng hạng, tất cả đều tham gia `MIN`, `MAX`, `SUM`, `AVG`, `COUNT` hoặc aggregate phù hợp. Đây là cách gọn để tính giá trị liên quan tới nhóm cực trị mà không cần viết nhiều subquery.

Khi dùng `KEEP`, hãy xác định rõ tập tie bằng toàn bộ sort key, khai báo `NULLS FIRST/LAST` có chủ đích và phân biệt null ở sort expression với null ở aggregate expression. `KEEP` trong `GROUP BY` trả một dòng mỗi nhóm; dạng analytic với `OVER (PARTITION BY ...)` giữ từng hàng và lặp giá trị theo partition. Nếu cần lấy toàn bộ cột từ cùng một hàng, dùng `ROW_NUMBER` với tie-breaker thay vì ghép nhiều aggregate KEEP có thể lấy dữ liệu từ các hàng khác nhau.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c — FIRST and LAST](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FIRST.html): cú pháp `KEEP (DENSE_RANK FIRST/LAST ...)`, aggregate và analytic usage.
- [Oracle Database 19c — DENSE_RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DENSE_RANK.html): cách xếp hạng các hàng có cùng sort key.
- [Oracle Database 19c — Aggregate Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html): quy tắc tổng hợp và xử lý NULL.
- [Oracle Database 19c — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): partition, analytic processing và cách sử dụng OVER.

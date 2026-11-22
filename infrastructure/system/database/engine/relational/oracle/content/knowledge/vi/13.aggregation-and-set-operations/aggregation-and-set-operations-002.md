# Ảnh hưởng của NULL và tập rỗng đến hàm tổng hợp

Khi viết báo cáo bằng Oracle SQL, một câu hỏi tưởng đơn giản như “tổng lương của phòng ban này là bao nhiêu?” có thể cho ra **0**, **NULL**, hoặc **không có hàng kết quả**. Những kết quả đó không đồng nghĩa với nhau. Chúng phụ thuộc vào việc truy vấn có hàng đầu vào hay không, các giá trị được tổng hợp có NULL hay không, và bạn đang tính trên toàn bộ tập dữ liệu hay trên từng nhóm.

Ví dụ:

- Không có nhân viên nào thuộc phòng ban 999: tập đầu vào của phép tổng hợp là **rỗng**.
- Có hai nhân viên thuộc phòng ban 30 nhưng cả hai chưa được ghi nhận lương: tập đầu vào có **hai hàng**, nhưng cột lương có hai giá trị NULL.
- Có ba nhân viên thuộc phòng ban 10, lương lần lượt là 1.000, NULL và 2.000: có **ba hàng**, trong đó hai giá trị lương được biết.

Oracle xử lý ba trường hợp này khác nhau:

- `COUNT(*)` đếm hàng.
- `COUNT(expression)` đếm các giá trị không NULL của biểu thức.
- `SUM`, `AVG`, `MIN`, `MAX` và nhiều hàm tổng hợp khác bỏ qua giá trị NULL.
- Với tập đầu vào không có giá trị phù hợp, nhiều aggregate trả NULL; riêng `COUNT` trả 0.
- Aggregate không có `GROUP BY` vẫn trả một hàng kết quả; truy vấn có `GROUP BY` trên tập đầu vào rỗng thường không tạo nhóm nào và trả 0 hàng.

Bài học tập trung vào cách phân biệt **tập rỗng**, **nhóm có hàng nhưng mọi giá trị đều NULL**, **giá trị tổng hợp bằng 0**, và **hàng NULL được sinh bởi OUTER JOIN**. Đây là nền tảng để viết báo cáo, KPI, thống kê và truy vấn kiểm tra chất lượng dữ liệu chính xác.

## 1. Ba trạng thái đầu vào cần phân biệt

Giả sử đang tính tổng trên cột `AMOUNT`. Có ba trạng thái đầu vào điển hình:

| Trạng thái | Các hàng đầu vào | Số hàng | Số giá trị AMOUNT không NULL |
| --- | --- | ---: | ---: |
| **Tập rỗng** | Không có hàng nào | 0 | 0 |
| **Có hàng, tất cả AMOUNT NULL** | NULL, NULL, ... | Lớn hơn 0 | 0 |
| **Có giá trị đã biết** | 1000, NULL, 2000, ... | Lớn hơn 0 | Lớn hơn 0 |

Với các aggregate cơ bản:

| Aggregate | Tập rỗng | Có hàng nhưng tất cả expression NULL | Có giá trị không NULL |
| --- | --- | --- | --- |
| `COUNT(*)` | 0 | Đếm số hàng | Đếm tất cả hàng |
| `COUNT(expr)` | 0 | 0 | Đếm giá trị expr không NULL |
| `COUNT(DISTINCT expr)` | 0 | 0 | Đếm giá trị khác nhau, bỏ NULL |
| `SUM(expr)` | NULL | NULL | Tổng các giá trị không NULL |
| `AVG(expr)` | NULL | NULL | Trung bình các giá trị không NULL |
| `MIN(expr)` | NULL | NULL | Nhỏ nhất trong các giá trị không NULL |
| `MAX(expr)` | NULL | NULL | Lớn nhất trong các giá trị không NULL |

Điểm dễ nhầm: **SUM trả NULL trong cả tập rỗng lẫn trường hợp có hàng nhưng tất cả giá trị đều NULL.** Chỉ nhìn kết quả SUM không đủ để phân biệt hai tình huống. Hãy xem thêm `COUNT(*)` và `COUNT(expr)`.

## 2. Dữ liệu lab để kiểm tra

Tạo bảng phòng ban và nhân viên trong **schema thực hành riêng** có quyền tạo bảng và quota tablespace. Các ví dụ không yêu cầu quyền DBA.

### 2.1. Tạo bảng

```sql
CREATE TABLE lab_agg_departments (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE lab_agg_employees (
    employee_id   NUMBER PRIMARY KEY,
    full_name     VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER,
    salary        NUMBER(12, 2),
    active_flag   CHAR(1) DEFAULT 'Y' NOT NULL,
    CONSTRAINT fk_lab_agg_emp_dept
        FOREIGN KEY (department_id)
        REFERENCES lab_agg_departments (department_id),
    CONSTRAINT ck_lab_agg_emp_active
        CHECK (active_flag IN ('Y', 'N'))
);
```

### 2.2. Chèn dữ liệu

```sql
INSERT INTO lab_agg_departments VALUES (10, 'Kỹ thuật');
INSERT INTO lab_agg_departments VALUES (20, 'Kinh doanh');
INSERT INTO lab_agg_departments VALUES (30, 'Nhân sự');
INSERT INTO lab_agg_departments VALUES (40, 'Pháp chế');

-- Phòng 10 có ba nhân viên, trong đó một người chưa có lương.
INSERT INTO lab_agg_employees VALUES (1, 'An',   10, 1000, 'Y');
INSERT INTO lab_agg_employees VALUES (2, 'Bình', 10, NULL, 'Y');
INSERT INTO lab_agg_employees VALUES (3, 'Chi',  10, 2000, 'N');

-- Phòng 20 không có nhân viên.

-- Phòng 30 có hai nhân viên nhưng cả hai chưa có lương.
INSERT INTO lab_agg_employees VALUES (4, 'Dũng', 30, NULL, 'Y');
INSERT INTO lab_agg_employees VALUES (5, 'Hà',   30, NULL, 'Y');

-- Phòng 40 có một nhân viên với lương bằng 0.
INSERT INTO lab_agg_employees VALUES (6, 'Lan',  40, 0, 'Y');

-- Một nhân viên chưa được gán phòng ban.
INSERT INTO lab_agg_employees VALUES (7, 'Minh', NULL, 500, 'Y');

COMMIT;
```

Tóm tắt dữ liệu:

| EMPLOYEE_ID | FULL_NAME | DEPARTMENT_ID | SALARY | Ý nghĩa |
| ---: | --- | ---: | ---: | --- |
| 1 | An | 10 | 1000 | Có lương |
| 2 | Bình | 10 | NULL | Có hàng, chưa có lương |
| 3 | Chi | 10 | 2000 | Có lương, không active |
| 4 | Dũng | 30 | NULL | Có hàng, chưa có lương |
| 5 | Hà | 30 | NULL | Có hàng, chưa có lương |
| 6 | Lan | 40 | 0 | Lương thực sự bằng 0 |
| 7 | Minh | NULL | 500 | Chưa gán phòng ban |

Như vậy:

- Phòng 10 có **3 hàng**, trong đó 2 giá trị lương đã biết.
- Phòng 20 có **0 nhân viên**.
- Phòng 30 có **2 hàng**, nhưng 0 giá trị lương đã biết.
- Phòng 40 có **1 hàng**, lương bằng số 0.
- Có một nhân viên không thuộc phòng ban nào.

Đây là các trạng thái khác nhau dù khi hiển thị báo cáo, một số ô tổng lương đều có thể trông giống nhau.

## 3. Aggregate trên toàn bộ tập đầu vào

Một câu SELECT chỉ có các hàm aggregate và **không có GROUP BY** tạo một kết quả tổng hợp cho toàn bộ tập hàng được lọc.

### 3.1. Không có hàng phù hợp

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(salary) AS known_salary_count,
    COUNT(DISTINCT salary) AS distinct_salary_count,
    SUM(salary) AS salary_sum,
    AVG(salary) AS salary_avg,
    MIN(salary) AS salary_min,
    MAX(salary) AS salary_max
FROM lab_agg_employees
WHERE department_id = 20;
```

Phòng 20 không có nhân viên. Tuy vậy, truy vấn aggregate không GROUP BY vẫn trả **một hàng kết quả**:

| ROW_COUNT | KNOWN_SALARY_COUNT | DISTINCT_SALARY_COUNT | SALARY_SUM | SALARY_AVG | SALARY_MIN | SALARY_MAX |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 0 | 0 | 0 | NULL | NULL | NULL | NULL |

Điều cần nhớ:

- `COUNT(*)` trả 0 vì không có hàng.
- `COUNT(SALARY)` trả 0 vì không có giá trị salary không NULL.
- `SUM`, `AVG`, `MIN` và `MAX` trả NULL vì không có giá trị đầu vào để tính.
- Client vẫn nhận **một hàng**, không phải result set rỗng.

### 3.2. Có hàng nhưng tất cả giá trị tổng hợp là NULL

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(salary) AS known_salary_count,
    COUNT(DISTINCT salary) AS distinct_salary_count,
    SUM(salary) AS salary_sum,
    AVG(salary) AS salary_avg,
    MIN(salary) AS salary_min,
    MAX(salary) AS salary_max
FROM lab_agg_employees
WHERE department_id = 30;
```

Phòng 30 có hai nhân viên nhưng cả hai có `SALARY NULL`:

| ROW_COUNT | KNOWN_SALARY_COUNT | DISTINCT_SALARY_COUNT | SALARY_SUM | SALARY_AVG | SALARY_MIN | SALARY_MAX |
| ---: | ---: | ---: | --- | --- | --- | --- |
| 2 | 0 | 0 | NULL | NULL | NULL | NULL |

So với phòng 20:

- `ROW_COUNT` khác nhau: 0 so với 2.
- Các aggregate dựa trên giá trị salary lại giống nhau: count salary bằng 0, sum/avg/min/max đều NULL.

Do đó, **SUM NULL không cho biết có hay không có hàng**. Muốn phân biệt, phải quan sát thêm COUNT(*).

### 3.3. Có một phần giá trị NULL

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(salary) AS known_salary_count,
    SUM(salary) AS salary_sum,
    AVG(salary) AS salary_avg,
    MIN(salary) AS salary_min,
    MAX(salary) AS salary_max
FROM lab_agg_employees
WHERE department_id = 10;
```

Phòng 10 có lương 1000, NULL và 2000:

| ROW_COUNT | KNOWN_SALARY_COUNT | SALARY_SUM | SALARY_AVG | SALARY_MIN | SALARY_MAX |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 2 | 3000 | 1500 | 1000 | 2000 |

Các hàm SUM/AVG/MIN/MAX bỏ qua hàng có salary NULL. Vì vậy:

\[
AVG(SALARY) = \frac{1000 + 2000}{2} = 1500
\]

Oracle không chia cho 3. Mẫu số của AVG là số giá trị không NULL, tương ứng với `COUNT(SALARY)`.

### 3.4. Số 0 là giá trị có thật

```sql
SELECT
    COUNT(*) AS row_count,
    COUNT(salary) AS known_salary_count,
    SUM(salary) AS salary_sum,
    AVG(salary) AS salary_avg,
    MIN(salary) AS salary_min,
    MAX(salary) AS salary_max
FROM lab_agg_employees
WHERE department_id = 40;
```

Phòng 40 có một nhân viên và salary bằng 0:

| ROW_COUNT | KNOWN_SALARY_COUNT | SALARY_SUM | SALARY_AVG | SALARY_MIN | SALARY_MAX |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 0 | 0 | 0 | 0 |

Đây là bằng chứng rõ ràng rằng **NULL khác 0**. Nếu ứng dụng tự thay NULL thành 0 khi ghi dữ liệu, nó sẽ không còn phân biệt được “chưa biết lương” với “lương bằng 0”.

## 4. COUNT(*), COUNT(expression) và COUNT(DISTINCT)

### 4.1. COUNT(*) đếm hàng

`COUNT(*)` đếm tất cả hàng của tập đầu vào, kể cả khi một số cột trong hàng là NULL:

```sql
SELECT COUNT(*) AS employee_rows
FROM lab_agg_employees
WHERE department_id = 10;
```

Kết quả là 3. Cột `SALARY` của Bình NULL không làm hàng đó biến mất khỏi phép đếm.

### 4.2. COUNT(expression) chỉ đếm giá trị không NULL

```sql
SELECT
    COUNT(*) AS employee_rows,
    COUNT(salary) AS employees_with_known_salary,
    COUNT(department_id) AS employees_assigned_to_department
FROM lab_agg_employees;
```

Ý nghĩa chung:

- `COUNT(*)` đếm hàng.
- `COUNT(SALARY)` chỉ đếm hàng có salary không NULL.
- `COUNT(DISTINCT SALARY)` đếm các giá trị salary khác nhau và không đếm NULL.

Trong một truy vấn có nhiều bảng JOIN, `COUNT(*)` đếm **hàng sau JOIN**. Nếu một nhân viên nối với ba dòng con, nhân viên đó đóng góp ba vào COUNT(*). Hãy xác định grain của result set trước khi đặt tên kết quả là “employee_count”.

### 4.3. COUNT(DISTINCT expression)

```sql
SELECT
    COUNT(*) AS employee_rows,
    COUNT(salary) AS known_values,
    COUNT(DISTINCT salary) AS distinct_known_salaries
FROM lab_agg_employees
WHERE department_id = 10;
```

Kết quả:

- 3 hàng nhân viên.
- 2 giá trị salary không NULL.
- 2 mức lương khác nhau: 1000 và 2000.

Nếu hai nhân viên cùng lương 1000, `COUNT(SALARY)` sẽ đếm cả hai, còn `COUNT(DISTINCT SALARY)` chỉ đếm một mức lương.

**NULL bị bỏ qua trong COUNT(expression), kể cả COUNT(DISTINCT expression).** Nếu cần đếm số hàng có NULL, hãy dùng `COUNT(*) - COUNT(expression)`:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(salary) AS known_salary_rows,
    COUNT(*) - COUNT(salary) AS null_salary_rows
FROM lab_agg_employees
WHERE department_id = 10;
```

Kết quả là 3, 2 và 1.

## 5. SUM, AVG, MIN và MAX bỏ qua NULL như thế nào?

### 5.1. SUM: cộng những giá trị được biết

```sql
SELECT SUM(salary) AS salary_total
FROM lab_agg_employees
WHERE department_id = 10;
```

Kết quả là 3000, vì NULL không đóng góp vào tổng. Nếu tất cả salary đều NULL hoặc không có hàng, SUM trả NULL.

Không diễn giải `SUM` NULL là “tổng bằng 0” nếu chưa xác định ngữ nghĩa nghiệp vụ. Nó có thể có nghĩa:

- Không có nhân viên.
- Có nhân viên nhưng chưa có giá trị lương nào được ghi nhận.
- Điều kiện lọc không tìm được giá trị salary không NULL.

### 5.2. AVG: mẫu số chỉ gồm giá trị không NULL

```sql
SELECT
    COUNT(*) AS employee_count,
    COUNT(salary) AS salary_count,
    SUM(salary) AS salary_sum,
    AVG(salary) AS salary_avg
FROM lab_agg_employees
WHERE department_id = 10;
```

Với phòng 10:

\[
AVG(SALARY) = \frac{SUM(SALARY)}{COUNT(SALARY)}
= \frac{3000}{2} = 1500
\]

Nếu dùng `COUNT(*)` làm mẫu số, kết quả tự tính sẽ là 1000 và không còn là ý nghĩa của `AVG(SALARY)` trong Oracle.

### 5.3. MIN và MAX: NULL không trở thành giá trị cực tiểu/cực đại

```sql
SELECT
    MIN(salary) AS minimum_salary,
    MAX(salary) AS maximum_salary
FROM lab_agg_employees
WHERE department_id = 10;
```

Kết quả 1000 và 2000. Oracle bỏ qua salary NULL khi tính MIN/MAX. Nếu mọi giá trị đều NULL hoặc không có hàng, cả hai trả NULL.

### 5.4. Các aggregate khác

Nhiều hàm aggregate khác cũng bỏ qua đối số NULL:

- `STDDEV` / `STDDEV_POP` / `STDDEV_SAMP`: độ lệch chuẩn.
- `VARIANCE` / `VAR_POP` / `VAR_SAMP`: phương sai.
- `MEDIAN`: trung vị.
- `LISTAGG`: bỏ qua giá trị measure NULL khi ghép chuỗi.
- `COUNT(DISTINCT ...)`: không đếm NULL.

Một số hàm thống kê có quy tắc riêng khi chỉ còn một giá trị đầu vào; ví dụ cách tính mẫu/tổng thể khác nhau. Khi dùng cho báo cáo chính thức, hãy đọc mô tả của chính hàm và release Oracle đang triển khai, không tự suy ra mọi hàm đều có cùng quy tắc biên.

Ví dụ LISTAGG:

```sql
SELECT
    department_id,
    LISTAGG(full_name, ', ')
        WITHIN GROUP (ORDER BY employee_id) AS employee_names
FROM lab_agg_employees
GROUP BY department_id
ORDER BY department_id NULLS LAST;
```

`LISTAGG` bỏ qua giá trị measure NULL. Nếu không có giá trị nào để ghép, kết quả aggregate là NULL. Nếu chuỗi kết quả vượt giới hạn, cần xử lý tùy chọn overflow theo release và yêu cầu ứng dụng.

## 6. Aggregate không GROUP BY và aggregate có GROUP BY

Đây là khác biệt quan trọng khi tập đầu vào rỗng.

### 6.1. Aggregate không GROUP BY trả một hàng

```sql
SELECT COUNT(*) AS row_count, SUM(salary) AS salary_sum
FROM lab_agg_employees
WHERE department_id = 999;
```

Không có nhân viên phòng 999, nhưng câu SELECT vẫn trả một hàng:

```text
ROW_COUNT | SALARY_SUM
----------+-----------
0         | NULL
```

Oracle tính aggregate cho **toàn bộ tập đầu vào**. COUNT trả 0; SUM trả NULL.

### 6.2. GROUP BY trên tập rỗng trả 0 hàng

```sql
SELECT
    department_id,
    COUNT(*) AS row_count,
    SUM(salary) AS salary_sum
FROM lab_agg_employees
WHERE department_id = 999
GROUP BY department_id;
```

Kết quả là **0 hàng**, vì không có hàng đầu vào để tạo nhóm `DEPARTMENT_ID`. Không có nhóm nào tồn tại để trả COUNT=0.

### 6.3. GROUP BY trên nhóm có hàng nhưng mọi giá trị NULL

```sql
SELECT
    department_id,
    COUNT(*) AS row_count,
    COUNT(salary) AS known_salary_count,
    SUM(salary) AS salary_sum
FROM lab_agg_employees
WHERE department_id = 30
GROUP BY department_id;
```

Kết quả có một hàng cho phòng 30:

```text
DEPARTMENT_ID | ROW_COUNT | KNOWN_SALARY_COUNT | SALARY_SUM
--------------+-----------+--------------------+-----------
30            | 2         | 0                  | NULL
```

Nhóm có tồn tại vì có hai nhân viên, nhưng không có giá trị salary nào được biết.

### 6.4. NULL trong GROUP BY tạo một nhóm

Oracle gom các hàng có cùng giá trị khóa nhóm NULL vào **một nhóm NULL**:

```sql
SELECT
    department_id,
    COUNT(*) AS employee_count,
    COUNT(salary) AS known_salary_count,
    SUM(salary) AS salary_sum
FROM lab_agg_employees
GROUP BY department_id
ORDER BY department_id NULLS LAST;
```

Hàng nhân viên Minh có `DEPARTMENT_ID NULL` sẽ tạo một nhóm riêng. Trong GROUP BY, NULL được gom cùng nhau dù phép so sánh `NULL = NULL` trong điều kiện thông thường không trả TRUE. Đây là hai ngữ cảnh SQL khác nhau.

## 7. Phân biệt tập rỗng và toàn NULL bằng COUNT

SUM, AVG, MIN và MAX có thể trả NULL trong cả hai trường hợp. Hãy kết hợp các phép đếm:

```sql
SELECT
    COUNT(*) AS input_rows,
    COUNT(salary) AS nonnull_salary_values,
    SUM(salary) AS salary_sum,
    CASE
        WHEN COUNT(*) = 0 THEN 'EMPTY INPUT'
        WHEN COUNT(salary) = 0 THEN 'ROWS EXIST, ALL SALARY NULL'
        ELSE 'HAS KNOWN SALARY'
    END AS input_state
FROM lab_agg_employees
WHERE department_id = :department_id;
```

Nếu bind `:department_id` lần lượt là 20, 30, 10:

| DEPARTMENT_ID | INPUT_ROWS | NONNULL_SALARY_VALUES | SALARY_SUM | INPUT_STATE |
| ---: | ---: | ---: | --- | --- |
| 20 | 0 | 0 | NULL | EMPTY INPUT |
| 30 | 2 | 0 | NULL | ROWS EXIST, ALL SALARY NULL |
| 10 | 3 | 2 | 3000 | HAS KNOWN SALARY |

Đây là mẫu truy vấn hữu ích cho API báo cáo. Nếu chỉ trả `SALARY_SUM`, client không thể phân biệt phòng 20 và phòng 30. Nếu trả thêm số hàng và số giá trị đã biết, client có đủ thông tin để quyết định cách hiển thị.

## 8. NVL và COALESCE: thay NULL ở đúng thời điểm

Vị trí đặt hàm thay NULL làm thay đổi kết quả aggregate.

### 8.1. NVL bên trong SUM

```sql
SELECT
    SUM(salary) AS sum_ignore_null,
    SUM(NVL(salary, 0)) AS sum_null_as_zero
FROM lab_agg_employees
WHERE department_id = 10;
```

Với phòng 10, cả hai đều bằng 3000:

- `SUM(SALARY)` bỏ qua NULL.
- `SUM(NVL(SALARY,0))` thay salary NULL của Bình bằng 0 trước khi cộng.

Hai biểu thức cho cùng tổng trong ví dụ này, nhưng không nhất thiết mang cùng ý nghĩa nghiệp vụ.

### 8.2. NVL bên ngoài SUM

```sql
SELECT
    NVL(SUM(salary), 0) AS display_salary_sum
FROM lab_agg_employees
WHERE department_id = 20;
```

Không có nhân viên phòng 20, nên SUM trả NULL; NVL ngoài cùng chuyển kết quả thành 0.

### 8.3. Bảng so sánh ba trường hợp

```sql
SELECT
    department_id,
    COUNT(*) AS row_count,
    COUNT(salary) AS known_count,
    SUM(salary) AS sum_original,
    SUM(NVL(salary, 0)) AS sum_nvl_inside,
    NVL(SUM(salary), 0) AS sum_nvl_outside
FROM lab_agg_employees
WHERE department_id IN (10, 20, 30, 40)
GROUP BY department_id
ORDER BY department_id;
```

Kết quả dự kiến:

| DEPARTMENT_ID | ROW_COUNT | KNOWN_COUNT | SUM_ORIGINAL | SUM_NVL_INSIDE | SUM_NVL_OUTSIDE |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 3 | 2 | 3000 | 3000 | 3000 |
| 30 | 2 | 0 | NULL | 0 | 0 |
| 40 | 1 | 1 | 0 | 0 | 0 |

Phòng 20 **không xuất hiện** vì đây là GROUP BY trực tiếp trên bảng nhân viên: không có hàng nên không có nhóm. Do đó không có dòng để NVL bên trong hay bên ngoài áp dụng.

Nếu truy vấn aggregate toàn tập:

```sql
SELECT
    COUNT(*) AS row_count,
    SUM(salary) AS sum_original,
    SUM(NVL(salary, 0)) AS sum_nvl_inside,
    NVL(SUM(salary), 0) AS sum_nvl_outside
FROM lab_agg_employees
WHERE department_id = 20;
```

Kết quả là `ROW_COUNT=0`, `SUM_ORIGINAL=NULL`, `SUM_NVL_INSIDE=NULL` và `SUM_NVL_OUTSIDE=0`. Lý do: SUM không có hàng để cộng, kể cả khi biểu thức bên trong có NVL.

**Quy tắc:** `NVL(SUM(x),0)` chuyển kết quả tổng NULL thành 0, bao gồm cả trường hợp không có hàng và trường hợp mọi giá trị x đều NULL. Nếu cần phân biệt hai trạng thái, luôn trả thêm `COUNT(*)` và `COUNT(x)`.

### 8.4. AVG(NVL(x,0)) khác NVL(AVG(x),0)

```sql
SELECT
    AVG(salary) AS avg_ignore_null,
    AVG(NVL(salary, 0)) AS avg_null_as_zero,
    NVL(AVG(salary), 0) AS avg_display_default
FROM lab_agg_employees
WHERE department_id = 10;
```

Phòng 10 có 1000, NULL và 2000:

- `AVG(SALARY) = 1500`: mẫu số là hai giá trị đã biết.
- `AVG(NVL(SALARY,0)) = 1000`: thay NULL bằng 0, mẫu số trở thành ba hàng.
- `NVL(AVG(SALARY),0) = 1500`: tính trung bình theo giá trị đã biết trước, chỉ thay kết quả NULL cuối cùng nếu không có giá trị nào để tính.

Đây là khác biệt có thể làm sai KPI nếu vô tình đặt NVL bên trong AVG.

## 9. NULL trong conditional aggregation

Conditional aggregation dùng CASE bên trong COUNT/SUM/AVG để tính nhiều chỉ số trong cùng một lượt truy vấn.

### 9.1. Đếm hàng thỏa điều kiện bằng COUNT(CASE ...)

```sql
SELECT
    COUNT(*) AS all_employees,
    COUNT(CASE WHEN active_flag = 'Y' THEN 1 END) AS active_employees,
    COUNT(CASE WHEN active_flag = 'N' THEN 1 END) AS inactive_employees
FROM lab_agg_employees;
```

Khi điều kiện không TRUE, CASE không có ELSE trả NULL; `COUNT(expression)` bỏ qua NULL. Vì vậy phép đếm điều kiện trả 0 nếu không có hàng nào thỏa.

### 9.2. Đếm bằng SUM của 0 và 1

```sql
SELECT
    SUM(CASE WHEN active_flag = 'Y' THEN 1 ELSE 0 END) AS active_employees,
    SUM(CASE WHEN active_flag = 'N' THEN 1 ELSE 0 END) AS inactive_employees
FROM lab_agg_employees;
```

Trên tập có hàng, mỗi hàng đóng góp 1 hoặc 0. Nhưng nếu tập đầu vào rỗng, SUM của biểu thức cũng NULL vì không có hàng nào để cộng. Nếu cần kết quả số 0 ngay cả trên tập rỗng, có thể dùng:

```sql
SELECT
    NVL(SUM(CASE WHEN active_flag = 'Y' THEN 1 ELSE 0 END), 0)
        AS active_employees
FROM lab_agg_employees
WHERE department_id = 20;
```

Hoặc dùng `COUNT(CASE WHEN ... THEN 1 END)`, vốn trả 0 trên tập đầu vào rỗng trong aggregate không GROUP BY.

### 9.3. Phân biệt không có hàng đạt điều kiện với giá trị đo bị NULL

Ví dụ tính tổng lương của nhân viên active:

```sql
SELECT
    COUNT(CASE WHEN active_flag = 'Y' THEN 1 END) AS active_rows,
    COUNT(CASE WHEN active_flag = 'Y' THEN salary END) AS active_known_salaries,
    SUM(CASE WHEN active_flag = 'Y' THEN salary END) AS active_salary_sum
FROM lab_agg_employees
WHERE department_id = :department_id;
```

Nếu phòng ban có nhân viên active nhưng tất cả salary đều NULL, `ACTIVE_ROWS` lớn hơn 0, `ACTIVE_KNOWN_SALARIES` bằng 0 và `ACTIVE_SALARY_SUM` là NULL. Nếu không có nhân viên nào phù hợp, cả hai COUNT là 0 và SUM là NULL. Kết hợp các cột này giúp client phân biệt nguyên nhân.

### 9.4. ELSE 0 có thể làm thay đổi ý nghĩa tổng

Hai biểu thức:

```sql
SUM(CASE WHEN active_flag = 'Y' THEN salary END)

SUM(CASE WHEN active_flag = 'Y' THEN salary ELSE 0 END)
```

khác nhau:

- Biểu thức đầu chỉ đưa salary của hàng active vào aggregate; các hàng khác trả NULL và bị bỏ qua.
- Biểu thức sau đưa số 0 cho hàng không active. Nếu có hàng nhưng không có nhân viên active, kết quả có thể là 0 thay vì NULL.
- Nếu các hàng active có salary NULL và không có hàng non-active đóng góp ELSE 0, tổng vẫn NULL.
- Nếu tập đầu vào rỗng, cả hai SUM vẫn NULL.

Hãy xác định KPI cần đo là “tổng các giá trị lương đã biết của nhân viên active” hay “tổng có quy ước mọi hàng không active bằng 0”. Không dùng ELSE 0 chỉ vì muốn tránh NULL ở màn hình.

## 10. OUTER JOIN tạo NULL: đếm đúng hàng con

Khi nối phòng ban với nhân viên, `LEFT JOIN` giữ phòng ban không có nhân viên và bổ sung một hàng với các cột phía nhân viên là NULL.

### 10.1. So sánh COUNT(*) và COUNT(employee_id)

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS joined_rows,
    COUNT(e.employee_id) AS employee_count,
    COUNT(e.salary) AS known_salary_count,
    SUM(e.salary) AS salary_sum
FROM lab_agg_departments d
LEFT JOIN lab_agg_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Kết quả logic:

| DEPARTMENT_ID | DEPARTMENT_NAME | JOINED_ROWS | EMPLOYEE_COUNT | KNOWN_SALARY_COUNT | SALARY_SUM |
| ---: | --- | ---: | ---: | ---: | --- |
| 10 | Kỹ thuật | 3 | 3 | 2 | 3000 |
| 20 | Kinh doanh | 1 | 0 | 0 | NULL |
| 30 | Nhân sự | 2 | 2 | 0 | NULL |
| 40 | Pháp chế | 1 | 1 | 1 | 0 |

Phòng 20 không có nhân viên:

- `COUNT(*) = 1` vì LEFT JOIN tạo một hàng NULL-extended cho phòng ban.
- `COUNT(e.employee_id) = 0` vì khóa nhân viên ở hàng bổ sung là NULL.
- `COUNT(e.salary) = 0` và `SUM(e.salary) = NULL`.

Phòng 30 có hai nhân viên thật nhưng salary đều NULL:

- `COUNT(*) = 2` và `COUNT(e.employee_id) = 2`.
- `COUNT(e.salary) = 0` và `SUM(e.salary) = NULL`.

Vì vậy, kết hợp `COUNT(e.employee_id)` và `COUNT(e.salary)` giúp phân biệt **không có nhân viên** với **có nhân viên nhưng chưa có lương**.

### 10.2. Điều kiện ở ON hay WHERE

Muốn giữ tất cả phòng ban và chỉ ghép nhân viên active:

```sql
SELECT
    d.department_id,
    COUNT(e.employee_id) AS active_employee_count
FROM lab_agg_departments d
LEFT JOIN lab_agg_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
GROUP BY d.department_id
ORDER BY d.department_id;
```

Nếu chuyển `e.active_flag = 'Y'` xuống WHERE, hàng NULL-extended của phòng không có nhân viên sẽ bị loại vì điều kiện là UNKNOWN. Kết quả không còn giữ mọi phòng ban.

Đây là lý do một truy vấn dùng LEFT JOIN vẫn có thể trả ít phòng ban hơn dự kiến. Hãy xác định bộ lọc dùng để giới hạn **hàng được ghép** (thường nằm trong ON) hay để loại **kết quả sau join** (WHERE).

### 10.3. NVL trên SUM trong outer join

```sql
SELECT
    d.department_id,
    COUNT(e.employee_id) AS employee_count,
    COUNT(e.salary) AS known_salary_count,
    SUM(e.salary) AS salary_sum,
    NVL(SUM(e.salary), 0) AS salary_sum_display
FROM lab_agg_departments d
LEFT JOIN lab_agg_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id
ORDER BY d.department_id;
```

`SALARY_SUM_DISPLAY` bằng 0 cho cả phòng 20 (không có nhân viên) và phòng 30 (có nhân viên nhưng tất cả lương NULL). Nếu báo cáo cần phân biệt, không chỉ trả cột đã NVL; hãy giữ thêm `EMPLOYEE_COUNT` và `KNOWN_SALARY_COUNT` hoặc thêm nhãn trạng thái.

## 11. HAVING và nhóm không có giá trị tổng hợp

`HAVING` lọc các nhóm sau khi aggregate được tính. Một điều kiện như `HAVING SUM(salary) > 0` không giữ nhóm mà SUM là NULL, vì `NULL > 0` là UNKNOWN.

### 11.1. Lọc nhóm có tổng lương dương

```sql
SELECT
    department_id,
    COUNT(*) AS employee_count,
    SUM(salary) AS salary_sum
FROM lab_agg_employees
GROUP BY department_id
HAVING SUM(salary) > 0
ORDER BY department_id NULLS LAST;
```

Phòng 30 bị loại vì SUM NULL; phòng 40 có SUM 0 cũng bị loại; phòng 10 có SUM 3000 được giữ. Nhóm department_id NULL của Minh có SUM 500 nên vẫn được giữ.

### 11.2. Lọc nhóm có nhân viên nhưng chưa có lương nào

```sql
SELECT
    department_id,
    COUNT(*) AS employee_count,
    COUNT(salary) AS known_salary_count,
    SUM(salary) AS salary_sum
FROM lab_agg_employees
GROUP BY department_id
HAVING COUNT(*) > 0
   AND COUNT(salary) = 0
ORDER BY department_id NULLS LAST;
```

Với truy vấn GROUP BY trực tiếp, mọi nhóm đã có ít nhất một hàng; điều kiện COUNT(*) > 0 có thể dư thừa, nhưng viết ra giúp nhấn mạnh ý nghĩa. Kết quả là phòng 30: có hai nhân viên và không có lương đã biết.

### 11.3. HAVING SUM IS NULL không đủ để phát hiện nhóm toàn NULL

```sql
SELECT department_id, COUNT(*) AS employee_count, SUM(salary) AS salary_sum
FROM lab_agg_employees
GROUP BY department_id
HAVING SUM(salary) IS NULL;
```

Trong GROUP BY trực tiếp, truy vấn này chọn nhóm có hàng nhưng mọi salary đều NULL (phòng 30). Tuy nhiên nếu dữ liệu đến từ OUTER JOIN, một nhóm phòng ban không có nhân viên cũng có SUM NULL. Khi đó cần kiểm tra thêm `COUNT(employee_id)` để phân biệt.

## 12. Aggregate sau JOIN có thể bị nhân bản

Một lỗi báo cáo phổ biến là cộng tiền sau khi nối hai bảng con độc lập. Giả sử một đơn hàng có hai dòng thanh toán và ba dòng ghi chú; nếu nối cả hai bảng con bằng `ORDER_ID`, mỗi dòng thanh toán xuất hiện ba lần.

Ví dụ khái niệm:

```text
ORDERS (một đơn hàng)
    |
    +---- PAYMENTS: 2 hàng
    |
    +---- NOTES:    3 hàng

JOIN cả hai bảng con theo ORDER_ID:
    2 x 3 = 6 hàng

SUM(payment_amount) sau JOIN có thể bị nhân 3 lần.
```

Không phải hàm SUM xử lý sai NULL; **tập đầu vào của SUM đã có nhiều bản sao hơn dự kiến**.

### 12.1. Aggregate từng bảng con trước khi JOIN

```sql
WITH payment_totals AS (
    SELECT order_id, SUM(payment_amount) AS paid_amount
    FROM order_payments
    GROUP BY order_id
),
note_counts AS (
    SELECT order_id, COUNT(*) AS note_count
    FROM order_notes
    GROUP BY order_id
)
SELECT
    o.order_id,
    NVL(p.paid_amount, 0) AS paid_amount,
    NVL(n.note_count, 0) AS note_count
FROM orders o
LEFT JOIN payment_totals p
  ON p.order_id = o.order_id
LEFT JOIN note_counts n
  ON n.order_id = o.order_id;
```

Mỗi CTE có tối đa một hàng cho mỗi order_id, nên join không nhân các dòng thanh toán với các dòng ghi chú. Nếu cần phân biệt “không có payment” với “có payment nhưng payment_amount đều NULL”, hãy đưa thêm `COUNT(*)` và `COUNT(payment_amount)` trong CTE payment_totals.

## 13. Scalar subquery và tập rỗng

Một scalar aggregate subquery không có GROUP BY vẫn trả một hàng:

```sql
SELECT
    (SELECT COUNT(*)
       FROM lab_agg_employees
      WHERE department_id = 999) AS employee_count,
    (SELECT SUM(salary)
       FROM lab_agg_employees
      WHERE department_id = 999) AS salary_sum
FROM dual;
```

Kết quả của câu SELECT ngoài:

```text
EMPLOYEE_COUNT | SALARY_SUM
---------------+-----------
0              | NULL
```

Nếu một scalar subquery **không có GROUP BY** dùng SUM/COUNT, nó trả một hàng aggregate như trên. Nếu scalar subquery có GROUP BY và không tạo nhóm nào, subquery trả 0 hàng; khi được dùng như scalar expression, giá trị tương ứng là NULL.

Ví dụ:

```sql
SELECT
    (SELECT COUNT(*)
       FROM lab_agg_employees
      WHERE department_id = 999
      GROUP BY department_id) AS grouped_count
FROM dual;
```

Subquery không tạo nhóm vì không có nhân viên phòng 999; scalar expression ở query ngoài nhận NULL. Khác biệt:

- Aggregate không GROUP BY: `COUNT(*)` trả 0.
- Aggregate có GROUP BY nhưng không có nhóm: không có hàng để lấy, scalar subquery trở thành NULL.

Đây là lý do cần nhìn **cấu trúc query block** chứ không chỉ tên hàm COUNT.

## 14. DISTINCT và NULL trong aggregate

`COUNT(DISTINCT expr)` bỏ qua NULL:

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(salary) AS nonnull_rows,
    COUNT(DISTINCT salary) AS distinct_salaries
FROM lab_agg_employees
WHERE department_id = 10;
```

Kết quả 3, 2, 2.

Trong khi đó, `SELECT DISTINCT salary` có thể trả một hàng NULL nếu dữ liệu có NULL:

```sql
SELECT DISTINCT salary
FROM lab_agg_employees
WHERE department_id = 10
ORDER BY salary NULLS LAST;
```

Kết quả có 1000, 2000 và một hàng NULL. Đừng nhầm `SELECT DISTINCT` với `COUNT(DISTINCT ...)`: phép SELECT DISTINCT giữ một đại diện NULL trong tập kết quả; COUNT DISTINCT không đếm NULL.

## 15. Hàm tổng hợp với CASE và điều kiện NULL

CASE cho phép định nghĩa chính xác giá trị nào được đưa vào aggregate.

### 15.1. Đếm nhân viên có lương đã biết theo phòng

```sql
SELECT
    department_id,
    COUNT(CASE WHEN salary IS NOT NULL THEN 1 END) AS known_salary_count,
    COUNT(CASE WHEN salary IS NULL THEN 1 END) AS missing_salary_count
FROM lab_agg_employees
GROUP BY department_id
ORDER BY department_id NULLS LAST;
```

Nhánh không khớp không có ELSE nên trả NULL; COUNT bỏ qua nó. Kết quả cho phòng 30 là 0 known và 2 missing.

### 15.2. SUM có điều kiện

```sql
SELECT
    department_id,
    SUM(CASE WHEN active_flag = 'Y' THEN salary END) AS active_salary_sum,
    COUNT(CASE WHEN active_flag = 'Y' THEN 1 END) AS active_count,
    COUNT(CASE WHEN active_flag = 'Y' THEN salary END) AS active_known_salary_count
FROM lab_agg_employees
GROUP BY department_id
ORDER BY department_id NULLS LAST;
```

Với phòng 30, có hai nhân viên active, nhưng không có salary đã biết. Kết quả `ACTIVE_COUNT=2`, `ACTIVE_KNOWN_SALARY_COUNT=0` và `ACTIVE_SALARY_SUM=NULL`.

### 15.3. Phân biệt không có hàng active và hàng active có salary NULL

Nếu một phòng có nhân viên nhưng tất cả đều inactive, `ACTIVE_COUNT` sẽ là 0 và `ACTIVE_KNOWN_SALARY_COUNT` cũng 0; tổng salary active NULL. Nếu phòng không có nhân viên, cùng ba aggregate trên cũng có thể cho 0/0/NULL trong một aggregate toàn tập. Muốn phân biệt, thêm `COUNT(*)` hoặc `COUNT(e.employee_id)`.

Đây là quy tắc tổng quát: **một aggregate được lọc bằng CASE chỉ mô tả phần dữ liệu được đưa vào hàm**, không tự cho biết có bao nhiêu hàng trong tập nguồn trước điều kiện CASE.

## 16. Lựa chọn giá trị hiển thị trong báo cáo

Không phải lúc nào báo cáo cũng nên hiển thị NULL. Nhưng nếu chuyển NULL thành 0, cần giữ thông tin trạng thái để người dùng không hiểu nhầm.

### 16.1. Một thiết kế báo cáo có trạng thái

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count,
    COUNT(e.salary) AS known_salary_count,
    SUM(e.salary) AS salary_sum,
    CASE
        WHEN COUNT(e.employee_id) = 0 THEN 'NO EMPLOYEES'
        WHEN COUNT(e.salary) = 0 THEN 'SALARY NOT RECORDED'
        ELSE 'HAS SALARY DATA'
    END AS salary_data_state,
    CASE
        WHEN COUNT(e.employee_id) = 0 THEN 0
        WHEN COUNT(e.salary) = 0 THEN NULL
        ELSE SUM(e.salary)
    END AS salary_total_for_report
FROM lab_agg_departments d
LEFT JOIN lab_agg_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Trong ví dụ:

- Phòng 20: không có nhân viên, báo cáo có thể hiển thị tổng 0 theo chính sách đã chọn.
- Phòng 30: có nhân viên nhưng chưa ghi nhận lương; giữ NULL để thể hiện chưa biết.
- Phòng 40: lương bằng 0 thật; trạng thái HAS SALARY DATA và tổng 0.

Như vậy, phòng 20 và phòng 40 cùng có giá trị hiển thị 0 nhưng **trạng thái dữ liệu khác nhau**. Phòng 30 là NULL vì chưa có giá trị lương. Đây là một thiết kế báo cáo rõ nghĩa hơn việc NVL tất cả trường hợp.

### 16.2. API nên trả cả số liệu và trạng thái

Một response báo cáo có thể chứa:

```json
{
  "departmentId": 30,
  "employeeCount": 2,
  "knownSalaryCount": 0,
  "salarySum": null,
  "salaryDataState": "SALARY_NOT_RECORDED"
}
```

Đối với phòng 20, response có thể là:

```json
{
  "departmentId": 20,
  "employeeCount": 0,
  "knownSalaryCount": 0,
  "salarySum": 0,
  "salaryDataState": "NO_EMPLOYEES"
}
```

Đây chỉ là quy ước API minh họa; điều quan trọng là backend không biến mất khác biệt giữa **không có nhân viên**, **chưa biết lương** và **lương bằng 0** nếu nghiệp vụ cần phân biệt.

## 17. Những lỗi thường gặp

| Hiện tượng | Kết luận sai thường gặp | Cách hiểu đúng |
| --- | --- | --- |
| SUM trả NULL | “Tổng bằng 0” | Có thể không có hàng hoặc mọi giá trị expression đều NULL |
| COUNT(*) trả 0 nhưng client thấy một hàng | “Có một hàng dữ liệu NULL” | Aggregate không GROUP BY trả một hàng với giá trị COUNT bằng 0 |
| GROUP BY không trả hàng | “COUNT không chạy” | Tập rỗng không tạo nhóm; không có dòng aggregate để trả |
| COUNT(*) khác COUNT(column) | “Oracle đếm thiếu” | COUNT(column) bỏ giá trị NULL; COUNT(*) đếm hàng |
| COUNT(DISTINCT column) thấp hơn COUNT(column) | “Dữ liệu mất hàng” | COUNT DISTINCT gộp giá trị trùng và bỏ NULL |
| AVG nhỏ hơn tính tay | Dùng tổng chia cho COUNT(*) | AVG chia cho số giá trị không NULL |
| SUM(NVL(x,0)) bằng 0 còn SUM(x) là NULL | “NVL chỉ đổi giao diện” | NVL bên trong thay từng giá trị trước aggregate |
| AVG(NVL(x,0)) thấp hơn AVG(x) | “Oracle tính AVG sai” | Giá trị NULL bị thay bằng 0 và tham gia mẫu số |
| LEFT JOIN cho COUNT(*) = 1 ở cha không có con | “Có một con” | Hàng NULL-extended vẫn được COUNT(*) đếm |
| LEFT JOIN có SUM NULL | “Không có con” | Có thể không có con hoặc có con nhưng tất cả measure NULL |
| Báo cáo SUM tăng sau khi thêm JOIN | “SUM bị lỗi” | Join 1-nhiều có thể nhân các hàng trước khi aggregate |
| HAVING SUM(x) > 0 loại nhóm toàn NULL | “Nhóm biến mất” | NULL > 0 là UNKNOWN, HAVING chỉ giữ TRUE |
| SELECT DISTINCT có hàng NULL nhưng COUNT DISTINCT = 0 | “Hai cách DISTINCT mâu thuẫn” | SELECT DISTINCT giữ một NULL; COUNT DISTINCT bỏ NULL |
| Aggregate scalar subquery trả NULL | “Không có row ở query ngoài” | Scalar subquery 0 hàng trở thành NULL; query ngoài vẫn có thể trả hàng |

## 18. Bài tập thực hành

Sử dụng hai bảng `LAB_AGG_DEPARTMENTS` và `LAB_AGG_EMPLOYEES` ở mục 2. Hãy dự đoán kết quả trước khi chạy.

### Bài 1 — Phân biệt tập rỗng và nhóm toàn NULL

Chạy hai truy vấn:

```sql
SELECT COUNT(*) AS row_count,
       COUNT(salary) AS known_count,
       SUM(salary) AS salary_sum
FROM lab_agg_employees
WHERE department_id = 20;

SELECT COUNT(*) AS row_count,
       COUNT(salary) AS known_count,
       SUM(salary) AS salary_sum
FROM lab_agg_employees
WHERE department_id = 30;
```

Giải thích vì sao SUM cùng NULL nhưng COUNT(*) khác nhau.

### Bài 2 — Aggregate có và không GROUP BY

Chạy:

```sql
SELECT COUNT(*), SUM(salary)
FROM lab_agg_employees
WHERE department_id = 999;

SELECT department_id, COUNT(*), SUM(salary)
FROM lab_agg_employees
WHERE department_id = 999
GROUP BY department_id;
```

Ghi số hàng của mỗi result set. Giải thích vì sao câu đầu có một hàng còn câu thứ hai không có hàng.

### Bài 3 — NULL khác 0

So sánh aggregate phòng 30 và phòng 40. Giải thích vì sao một phòng có SUM NULL, một phòng có SUM 0. Nếu thay mọi NULL bằng 0 khi nhập dữ liệu, thông tin nào bị mất?

### Bài 4 — NVL trong và ngoài AVG

Viết:

```sql
SELECT
    AVG(salary),
    AVG(NVL(salary, 0)),
    NVL(AVG(salary), 0)
FROM lab_agg_employees
WHERE department_id = 10;
```

Tính mẫu số từng biểu thức và giải thích tại sao hai kết quả AVG có thể khác.

### Bài 5 — LEFT JOIN và COUNT

Viết báo cáo cho mọi phòng ban với:

- Số nhân viên.
- Số nhân viên có lương đã biết.
- Tổng lương.
- Tổng lương hiển thị thay NULL bằng 0.

Giải thích kết quả phòng 20, 30 và 40. Phải dùng khóa phía nhân viên trong COUNT, không chỉ COUNT(*).

### Bài 6 — HAVING và NULL

Viết ba truy vấn:

1. Nhóm có `SUM(SALARY) > 0`.
2. Nhóm có nhân viên nhưng `COUNT(SALARY)=0`.
3. Nhóm có `SUM(SALARY) IS NULL`.

Sau đó thêm LEFT JOIN từ bảng phòng ban và giải thích vì sao truy vấn 3 có thể chọn cả phòng không có nhân viên.

### Bài 7 — Conditional aggregation

Tính số nhân viên active, số nhân viên inactive, số nhân viên có lương đã biết và tổng lương active cho từng phòng. Kết quả cần một hàng mỗi phòng, kể cả phòng 20 không có nhân viên.

Gợi ý: LEFT JOIN; dùng `COUNT(CASE WHEN ... THEN employee_id END)` và `SUM(CASE WHEN ... THEN salary END)`; nếu thay NULL bằng 0, giữ thêm các cột đếm để không mất trạng thái.

### Bài 8 — Phát hiện aggregate bị nhân bản

Tạo hai bảng con mô phỏng payment và note cho cùng một đơn hàng; một đơn có hai payment và ba note. Nối trực tiếp hai bảng rồi tính `SUM(payment_amount)`. Sau đó aggregate payment theo order trước khi nối note. Giải thích tại sao tổng ban đầu bị nhân ba lần.

## 19. Dọn dữ liệu lab

Chỉ xóa các bảng do bạn tạo cho bài học trong schema thực hành:

```sql
DROP TABLE lab_agg_employees PURGE;
DROP TABLE lab_agg_departments PURGE;
```

Xóa bảng con `LAB_AGG_EMPLOYEES` trước vì có foreign key tham chiếu bảng phòng ban. `PURGE` bỏ qua recycle bin; không chạy trên bảng nghiệp vụ hoặc dữ liệu cần khôi phục.

## Tổng kết

Khi dùng hàm tổng hợp trong Oracle, hãy luôn kiểm tra **số hàng đầu vào** và **số giá trị không NULL**. `COUNT(*)` đếm hàng, `COUNT(expression)` đếm giá trị không NULL, còn `SUM`/`AVG`/`MIN`/`MAX` bỏ qua NULL. Aggregate không GROUP BY vẫn trả một hàng trên tập rỗng; GROUP BY trên tập rỗng không tạo nhóm. Vì thế SUM NULL có thể có nghĩa không có hàng hoặc có hàng nhưng mọi giá trị measure đều NULL.

OUTER JOIN bổ sung hàng NULL-extended, khiến `COUNT(*)` có thể bằng 1 dù không có hàng con; hãy đếm khóa phía con. Khi nối nhiều quan hệ 1-nhiều, kiểm tra grain và aggregate từng nguồn trước khi join để tránh nhân tổng. Dùng `NVL`/`COALESCE` chỉ khi đã xác định ý nghĩa thay thế, và giữ số đếm/trạng thái nếu báo cáo cần phân biệt **không có dữ liệu**, **dữ liệu chưa được ghi nhận** và **giá trị bằng 0**.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — Aggregate Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html) — hành vi tổng hợp và xử lý NULL.
- [Oracle Database SQL Language Reference — COUNT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COUNT.html) — khác biệt COUNT(*) và COUNT(expression).
- [Oracle Database SQL Language Reference — SUM (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SUM.html) — tổng các giá trị không NULL và dạng analytic.
- [Oracle Database SQL Language Reference — AVG (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/AVG.html) — trung bình trên các giá trị hợp lệ.
- [Oracle Database SQL Language Reference — Nulls (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Nulls.html) — ngữ nghĩa NULL trong SQL.
- [Oracle Database SQL Language Reference — Joins (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html) — outer join và hàng được bổ sung.

Khi triển khai trên release Oracle khác 19c, hãy đối chiếu tài liệu đúng phiên bản, đặc biệt với các aggregate thống kê, LISTAGG, kiểu dữ liệu và cú pháp mới.

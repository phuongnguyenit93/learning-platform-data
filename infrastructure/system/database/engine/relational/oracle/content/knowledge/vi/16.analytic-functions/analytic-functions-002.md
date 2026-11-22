# Cấu trúc OVER, PARTITION BY và ORDER BY trong Oracle SQL

Hàm phân tích (analytic function) giúp tính toán trên một tập dòng có liên quan mà vẫn **giữ lại từng dòng của kết quả**. Ta có thể xếp hạng nhân viên trong phòng ban, tính tổng lương lũy kế theo ngày tuyển dụng, so sánh lương với trung bình phòng ban, tìm giá trị của dòng trước hoặc chọn hai nhân viên đứng đầu mỗi nhóm.

Trong Oracle SQL, cấu trúc `OVER(...)` xác định tập dòng và cách sắp xếp mà hàm phân tích sử dụng. Ba thành phần cần nắm là:

- `OVER`: khai báo cửa sổ (window) cho hàm phân tích.
- `PARTITION BY`: chia tập dòng thành các nhóm độc lập để tính toán.
- `ORDER BY`: xác định thứ tự dòng bên trong mỗi partition; với một số hàm tổng hợp còn xác định cửa sổ lũy kế hoặc cửa sổ trượt.

Hiểu đúng ba thành phần này giúp tránh nhầm hàm phân tích với `GROUP BY`, tránh tính tổng lặp sai, và tránh giả định thứ tự hiển thị của truy vấn chỉ vì đã viết `ORDER BY` trong `OVER`.

## 1. Hàm phân tích khác GROUP BY như thế nào?

`GROUP BY` gom nhiều dòng thành một dòng cho mỗi nhóm. Hàm phân tích tính một giá trị theo nhóm hoặc cửa sổ nhưng vẫn trả lại các dòng chi tiết.

Ví dụ, bảng nhân viên có nhiều người trong một phòng ban. Nếu dùng:

~~~sql
SELECT department_id, AVG(salary) AS department_avg_salary
FROM lab_af_employee
GROUP BY department_id;
~~~

Kết quả chỉ có một dòng cho mỗi phòng ban. Ta biết mức lương trung bình, nhưng không còn từng nhân viên trong kết quả.

Nếu dùng:

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_avg_salary
FROM lab_af_employee
ORDER BY department_id, employee_id;
~~~

Oracle vẫn trả từng nhân viên. Cột `DEPARTMENT_AVG_SALARY` lặp lại giá trị trung bình của phòng ban trên từng dòng thuộc phòng đó.

| Kỹ thuật | Kết quả | Ví dụ một dòng đại diện cho |
|---|---|---|
| `GROUP BY department_id` | Một dòng mỗi phòng ban | Một phòng ban |
| `AVG(salary) OVER (PARTITION BY department_id)` | Một dòng mỗi nhân viên, thêm giá trị trung bình phòng ban | Một nhân viên kèm thống kê phòng ban |

Đây là khác biệt quan trọng: **GROUP BY thay đổi grain của kết quả; analytic function bổ sung thông tin vào grain hiện có**.

## 2. Cú pháp OVER

Dạng tổng quát:

~~~sql
analytic_function ( [ arguments ] )
OVER (
    [ query_partition_clause ]
    [ order_by_clause ]
    [ windowing_clause ]
)
~~~

Ví dụ:

~~~sql
SUM(salary) OVER (
    PARTITION BY department_id
    ORDER BY hire_date, employee_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Đọc từ trong ra ngoài:

1. `SUM(salary)`: hàm cần tính là tổng lương.
2. `PARTITION BY department_id`: tính riêng cho từng phòng ban.
3. `ORDER BY hire_date, employee_id`: xác định thứ tự dòng trong mỗi phòng ban.
4. `ROWS BETWEEN ...`: xác định những dòng nào thuộc cửa sổ dùng để tính tổng cho dòng hiện tại.
5. `OVER(...)`: biến phép tính thành phép tính phân tích trên các dòng liên quan, giữ nguyên từng dòng đầu ra.

Không phải hàm phân tích nào cũng cần cả ba thành phần. Ví dụ:

~~~sql
COUNT(*) OVER ()
~~~

đếm toàn bộ số dòng của tập kết quả đầu vào và hiển thị cùng số đếm đó trên mỗi dòng; không có `PARTITION BY` nên toàn bộ tập là một partition, không có `ORDER BY` nên không xác định thứ tự cửa sổ.

## 3. Chuẩn bị dữ liệu thực hành

Ta dùng một bảng nhân viên có mã phòng ban, lương và ngày tuyển dụng. Dataset cố ý có nhiều nhân viên bằng lương và có hai người cùng ngày tuyển dụng để quan sát hành vi đồng hạng và cửa sổ `RANGE`.

### 3.1. Tạo bảng

Chạy trong schema lab thuộc một PDB thực hành. Nếu bảng cùng tên đã tồn tại, hãy dùng schema hoặc tên bảng khác; không ghi đè dữ liệu đang được sử dụng.

~~~sql
CREATE TABLE lab_af_employee (
    employee_id   NUMBER(5) PRIMARY KEY,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    department_id NUMBER(4) NOT NULL,
    salary        NUMBER(10,2) NOT NULL,
    hire_date     DATE NOT NULL,
    CONSTRAINT ck_lab_af_salary CHECK (salary >= 0)
);
~~~

### 3.2. Chèn dữ liệu

~~~sql
INSERT INTO lab_af_employee VALUES
  (101, 'An',   10, 9000, DATE '2022-01-10');
INSERT INTO lab_af_employee VALUES
  (102, 'Binh', 10, 7000, DATE '2022-03-15');
INSERT INTO lab_af_employee VALUES
  (103, 'Chi',  10, 7000, DATE '2022-03-15');
INSERT INTO lab_af_employee VALUES
  (104, 'Dung', 10, 5000, DATE '2023-01-20');

INSERT INTO lab_af_employee VALUES
  (201, 'Em',    20, 12000, DATE '2021-07-01');
INSERT INTO lab_af_employee VALUES
  (202, 'Giang', 20, 10000, DATE '2022-08-01');
INSERT INTO lab_af_employee VALUES
  (203, 'Hanh',  20, 10000, DATE '2022-08-01');
INSERT INTO lab_af_employee VALUES
  (204, 'Khoa',  20, 6000,  DATE '2024-02-10');

INSERT INTO lab_af_employee VALUES
  (301, 'Lan',  30, 8000, DATE '2023-05-01');
INSERT INTO lab_af_employee VALUES
  (302, 'Minh', 30, 8000, DATE '2023-06-01');
INSERT INTO lab_af_employee VALUES
  (303, 'Nam',  30, 6500, DATE '2024-04-01');

COMMIT;
~~~

### 3.3. Xem dữ liệu nguồn

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    hire_date
FROM lab_af_employee
ORDER BY department_id, employee_id;
~~~

Tóm tắt:

| EMPLOYEE_ID | EMPLOYEE_NAME | DEPARTMENT_ID | SALARY | HIRE_DATE |
|---:|---|---:|---:|---|
| 101 | An | 10 | 9000 | 2022-01-10 |
| 102 | Binh | 10 | 7000 | 2022-03-15 |
| 103 | Chi | 10 | 7000 | 2022-03-15 |
| 104 | Dung | 10 | 5000 | 2023-01-20 |
| 201 | Em | 20 | 12000 | 2021-07-01 |
| 202 | Giang | 20 | 10000 | 2022-08-01 |
| 203 | Hanh | 20 | 10000 | 2022-08-01 |
| 204 | Khoa | 20 | 6000 | 2024-02-10 |
| 301 | Lan | 30 | 8000 | 2023-05-01 |
| 302 | Minh | 30 | 8000 | 2023-06-01 |
| 303 | Nam | 30 | 6500 | 2024-04-01 |

Tổng lương từng phòng ban:

| DEPARTMENT_ID | Số nhân viên | Tổng lương | Trung bình |
|---:|---:|---:|---:|
| 10 | 4 | 28000 | 7000 |
| 20 | 4 | 38000 | 9500 |
| 30 | 3 | 22500 | 7500 |

Các mức lương trùng nhau trong phòng 10, 20 và 30 giúp minh họa `RANK`, `DENSE_RANK` và peer rows trong cửa sổ `RANGE`.

## 4. OVER không có PARTITION BY

Nếu không chỉ định `PARTITION BY`, toàn bộ tập dòng của query block là một partition.

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    SUM(salary) OVER () AS all_employee_salary,
    COUNT(*) OVER () AS all_employee_count
FROM lab_af_employee
ORDER BY employee_id;
~~~

Với dataset này, mọi dòng đều có:

- `ALL_EMPLOYEE_SALARY = 88500`
- `ALL_EMPLOYEE_COUNT = 11`

Hai giá trị được lặp trên mỗi nhân viên. Tổng lương không được cộng lại theo từng phòng ban vì không có `PARTITION BY`.

### 4.1. So sánh với aggregate thông thường

~~~sql
SELECT SUM(salary) AS all_employee_salary
FROM lab_af_employee;
~~~

Câu trên trả đúng một dòng với tổng 88500. Trong khi `SUM(salary) OVER ()` trả 11 dòng, mỗi dòng kèm tổng 88500.

## 5. PARTITION BY chia tập dòng thành các vùng độc lập

`PARTITION BY` chia dữ liệu thành các partition dựa trên giá trị một hoặc nhiều biểu thức. Hàm phân tích được tính riêng trong mỗi partition.

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    SUM(salary) OVER (
        PARTITION BY department_id
    ) AS department_total,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_average,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS department_employee_count
FROM lab_af_employee
ORDER BY department_id, employee_id;
~~~

Kết quả mong đợi:

| DEPARTMENT_ID | EMPLOYEE_NAME | SALARY | DEPARTMENT_TOTAL | DEPARTMENT_AVERAGE | DEPARTMENT_EMPLOYEE_COUNT |
|---:|---|---:|---:|---:|---:|
| 10 | An | 9000 | 28000 | 7000 | 4 |
| 10 | Binh | 7000 | 28000 | 7000 | 4 |
| 10 | Chi | 7000 | 28000 | 7000 | 4 |
| 10 | Dung | 5000 | 28000 | 7000 | 4 |
| 20 | Em | 12000 | 38000 | 9500 | 4 |
| 20 | Giang | 10000 | 38000 | 9500 | 4 |
| 20 | Hanh | 10000 | 38000 | 9500 | 4 |
| 20 | Khoa | 6000 | 38000 | 9500 | 4 |
| 30 | Lan | 8000 | 22500 | 7500 | 3 |
| 30 | Minh | 8000 | 22500 | 7500 | 3 |
| 30 | Nam | 6500 | 22500 | 7500 | 3 |

### 5.1. Nhiều cột trong PARTITION BY

Có thể chia theo nhiều cấp:

~~~sql
AVG(salary) OVER (
    PARTITION BY department_id, job_id
)
~~~

Mỗi tổ hợp `DEPARTMENT_ID` và `JOB_ID` tạo một partition. Trong ví dụ hiện tại chưa có cột `JOB_ID`; biểu thức trên chỉ minh họa cú pháp. Chỉ dùng các cột thực sự tồn tại trong schema.

Nếu một cột partition có NULL, các dòng có giá trị NULL ở cột đó thuộc cùng một nhóm partition theo giá trị biểu thức. Không có ý nghĩa “NULL bằng NULL” theo phép so sánh SQL thông thường ở đây; đây là quy tắc phân vùng của analytic function.

### 5.2. PARTITION BY không loại dòng

`PARTITION BY department_id` không làm mất nhân viên thuộc phòng ban nào đó, cũng không gộp nhân viên thành một dòng. Nó chỉ xác định phạm vi mà hàm phân tích dùng để tính.

Nếu cần loại phòng ban không hoạt động hoặc nhân viên không thỏa điều kiện, dùng `WHERE` hoặc điều kiện phù hợp ở query block bên ngoài. `PARTITION BY` không phải điều kiện lọc.

## 6. ORDER BY bên trong OVER

`ORDER BY` trong `OVER` xác định thứ tự các dòng **bên trong mỗi partition**. Nó đặc biệt quan trọng với các hàm xếp hạng, hàm truy cập dòng trước/sau và aggregate có cửa sổ.

Ví dụ xếp nhân viên theo lương giảm dần trong từng phòng ban:

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS row_num
FROM lab_af_employee
ORDER BY department_id, row_num;
~~~

Trong mỗi phòng ban, người có lương cao nhất nhận số 1. `EMPLOYEE_ID` là tiêu chí phụ để xác định thứ tự khi hai người có cùng lương.

### 6.1. ORDER BY trong OVER không sắp xếp kết quả cuối

Hai khái niệm cần tách biệt:

- `ORDER BY` **bên trong `OVER(...)`**: quyết định thứ tự tính của hàm phân tích.
- `ORDER BY` **ở cuối câu SELECT**: quyết định thứ tự dòng được trả về cho client.

Ví dụ:

~~~sql
SELECT
    employee_id,
    employee_name,
    salary,
    ROW_NUMBER() OVER (
        ORDER BY salary DESC, employee_id
    ) AS salary_position
FROM lab_af_employee;
~~~

Hàm phân tích đánh số theo lương giảm dần, nhưng nếu không có `ORDER BY` cuối câu, Oracle **không bảo đảm** các dòng được hiển thị theo `SALARY_POSITION`. Muốn hiển thị đúng thứ tự:

~~~sql
SELECT
    employee_id,
    employee_name,
    salary,
    ROW_NUMBER() OVER (
        ORDER BY salary DESC, employee_id
    ) AS salary_position
FROM lab_af_employee
ORDER BY salary_position;
~~~

Không dựa vào thứ tự vật lý, thứ tự insert hoặc index để thay thế `ORDER BY` cuối.

### 6.2. ORDER BY có thể dùng nhiều biểu thức

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC, hire_date ASC, employee_id ASC
)
~~~

Oracle so sánh theo lương trước; nếu bằng nhau, xét ngày tuyển dụng; nếu vẫn bằng nhau, xét mã nhân viên. Một thứ tự phụ đủ duy nhất giúp kết quả `ROW_NUMBER` ổn định.

### 6.3. ASC, DESC và NULLS FIRST/LAST

Có thể chỉ rõ cách đặt NULL:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC NULLS LAST, employee_id
)
~~~

Trong Oracle, mặc định NULL thường được xếp cuối với `ASC` và đầu với `DESC`. Khi cột sort có thể NULL, viết rõ `NULLS FIRST` hoặc `NULLS LAST` giúp ý định không phụ thuộc vào việc người đọc phải nhớ mặc định.

## 7. ROW_NUMBER, RANK và DENSE_RANK

Ba hàm này thường được dùng để xếp hạng, nhưng cách xử lý giá trị bằng nhau khác nhau.

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS row_number_value,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS rank_value,
    DENSE_RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS dense_rank_value
FROM lab_af_employee
ORDER BY department_id, salary DESC, employee_id;
~~~

Kết quả:

| DEPARTMENT_ID | EMPLOYEE_NAME | SALARY | ROW_NUMBER | RANK | DENSE_RANK |
|---:|---|---:|---:|---:|---:|
| 10 | An | 9000 | 1 | 1 | 1 |
| 10 | Binh | 7000 | 2 | 2 | 2 |
| 10 | Chi | 7000 | 3 | 2 | 2 |
| 10 | Dung | 5000 | 4 | 4 | 3 |
| 20 | Em | 12000 | 1 | 1 | 1 |
| 20 | Giang | 10000 | 2 | 2 | 2 |
| 20 | Hanh | 10000 | 3 | 2 | 2 |
| 20 | Khoa | 6000 | 4 | 4 | 3 |
| 30 | Lan | 8000 | 1 | 1 | 1 |
| 30 | Minh | 8000 | 2 | 1 | 1 |
| 30 | Nam | 6500 | 3 | 3 | 2 |

| Hàm | Giá trị bằng nhau | Hạng tiếp theo | Ý nghĩa |
|---|---|---|---|
| `ROW_NUMBER` | Luôn đánh số khác nhau | Liên tục 1, 2, 3... | Vị trí từng dòng |
| `RANK` | Cùng hạng | Có khoảng nhảy | Xếp hạng có đồng hạng |
| `DENSE_RANK` | Cùng hạng | Không nhảy khoảng | Xếp hạng theo mức giá trị phân biệt |

Trong `ROW_NUMBER`, nếu `ORDER BY` không tạo thứ tự duy nhất, hai dòng bằng nhau có thể nhận số thứ tự theo thứ tự không ổn định. Thêm khóa phụ như `EMPLOYEE_ID` nếu nghiệp vụ cần chọn đúng một dòng.

## 8. Top-N trong từng partition

Yêu cầu: lấy hai nhân viên có lương cao nhất ở mỗi phòng ban.

Không thể dùng trực tiếp `WHERE row_number_value <= 2` trong cùng query block tạo alias analytic. Ta dùng inline view:

~~~sql
SELECT
    ranked.department_id,
    ranked.employee_id,
    ranked.employee_name,
    ranked.salary,
    ranked.rn
FROM (
    SELECT
        e.department_id,
        e.employee_id,
        e.employee_name,
        e.salary,
        ROW_NUMBER() OVER (
            PARTITION BY e.department_id
            ORDER BY e.salary DESC, e.employee_id
        ) AS rn
    FROM lab_af_employee e
) ranked
WHERE ranked.rn <= 2
ORDER BY ranked.department_id, ranked.rn;
~~~

Kết quả có tối đa hai nhân viên mỗi phòng:

| DEPARTMENT_ID | EMPLOYEE_NAME | SALARY | RN |
|---:|---|---:|---:|
| 10 | An | 9000 | 1 |
| 10 | Binh | 7000 | 2 |
| 20 | Em | 12000 | 1 |
| 20 | Giang | 10000 | 2 |
| 30 | Lan | 8000 | 1 |
| 30 | Minh | 8000 | 2 |

Vì `ROW_NUMBER` có tiêu chí phụ `EMPLOYEE_ID`, truy vấn lấy đúng tối đa hai dòng mỗi phòng ban. Với phòng 30, Lan đứng trước Minh theo mã nhân viên.

### 8.1. Top-N có đồng hạng

Nếu yêu cầu là “lấy tất cả nhân viên có mức lương thuộc hai hạng cao nhất, kể cả đồng hạng”, dùng `DENSE_RANK`:

~~~sql
SELECT
    ranked.department_id,
    ranked.employee_name,
    ranked.salary,
    ranked.salary_rank
FROM (
    SELECT
        department_id,
        employee_name,
        salary,
        DENSE_RANK() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC
        ) AS salary_rank
    FROM lab_af_employee
) ranked
WHERE ranked.salary_rank <= 2
ORDER BY ranked.department_id, ranked.salary DESC, ranked.employee_name;
~~~

Kết quả:

- Phòng 10: An (9000), Binh và Chi (7000).
- Phòng 20: Em (12000), Giang và Hanh (10000).
- Phòng 30: Lan và Minh (8000), Nam (6500).

`DENSE_RANK <= 2` có thể trả nhiều hơn hai dòng cho một phòng. Hãy chọn hàm dựa trên định nghĩa “top hai dòng” hay “hai mức hạng”, không dựa trên tên gọi chung chung là top-N.

## 9. Aggregate analytic: tổng hợp nhưng vẫn giữ dòng chi tiết

Ta có thể dùng hàm tổng hợp cùng `OVER`:

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    SUM(salary) OVER (
        PARTITION BY department_id
    ) AS department_salary_total,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_salary_avg,
    MAX(salary) OVER (
        PARTITION BY department_id
    ) AS department_max_salary,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS department_size
FROM lab_af_employee
ORDER BY department_id, employee_id;
~~~

Mỗi nhân viên vẫn là một dòng, kèm tổng, trung bình, lương cao nhất và số nhân viên của phòng ban. Khác với `GROUP BY`, không cần JOIN ngược kết quả aggregate về bảng nhân viên.

### 9.1. So sánh lương từng người với trung bình phòng ban

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_avg,
    salary - AVG(salary) OVER (
        PARTITION BY department_id
    ) AS difference_from_avg
FROM lab_af_employee
ORDER BY department_id, employee_id;
~~~

Ví dụ:

- An có lương 9000, cao hơn trung bình phòng 10 là 2000.
- Dung có lương 5000, thấp hơn trung bình phòng 10 là 2000.
- Em có lương 12000, cao hơn trung bình phòng 20 là 2500.
- Nam có lương 6500, thấp hơn trung bình phòng 30 là 1000.

Đây là dạng báo cáo mà `GROUP BY` đơn thuần không thể vừa giữ từng nhân viên vừa đưa trung bình phòng ban lên cùng dòng.

## 10. ORDER BY kết hợp windowing clause

Với aggregate analytic, `ORDER BY` có thể xác định một **cửa sổ** quanh dòng hiện tại. Ta thường gặp:

- Tổng lũy kế (running total).
- Trung bình lũy kế.
- Tổng/trung bình trượt theo một số dòng gần nhất.
- Tổng theo một khoảng giá trị logic.

Khung cửa sổ có dạng:

~~~sql
ROWS | RANGE
BETWEEN frame_start AND frame_end
~~~

Các mốc thường gặp:

| Mốc | Ý nghĩa |
|---|---|
| `UNBOUNDED PRECEDING` | Từ đầu partition |
| `n PRECEDING` | Lùi n dòng (ROWS) hoặc khoảng giá trị (RANGE) theo quy tắc frame |
| `CURRENT ROW` | Dòng hiện tại; với RANGE có thể bao gồm các peer cùng giá trị sort |
| `n FOLLOWING` | Tiến n dòng hoặc khoảng giá trị tương ứng |
| `UNBOUNDED FOLLOWING` | Đến cuối partition |

## 11. Running total với ROWS

Tính tổng lương lũy kế theo ngày tuyển dụng trong từng phòng:

~~~sql
SELECT
    department_id,
    employee_id,
    employee_name,
    hire_date,
    salary,
    SUM(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

`ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` nghĩa là từ dòng đầu partition đến dòng hiện tại theo thứ tự analytic. Vì có `EMPLOYEE_ID` làm tiêu chí phụ, mỗi dòng có thứ tự rõ ràng.

Kết quả tính tay:

| DEPARTMENT_ID | EMPLOYEE_NAME | HIRE_DATE | SALARY | RUNNING_SALARY |
|---:|---|---|---:|---:|
| 10 | An | 2022-01-10 | 9000 | 9000 |
| 10 | Binh | 2022-03-15 | 7000 | 16000 |
| 10 | Chi | 2022-03-15 | 7000 | 23000 |
| 10 | Dung | 2023-01-20 | 5000 | 28000 |
| 20 | Em | 2021-07-01 | 12000 | 12000 |
| 20 | Giang | 2022-08-01 | 10000 | 22000 |
| 20 | Hanh | 2022-08-01 | 10000 | 32000 |
| 20 | Khoa | 2024-02-10 | 6000 | 38000 |
| 30 | Lan | 2023-05-01 | 8000 | 8000 |
| 30 | Minh | 2023-06-01 | 8000 | 16000 |
| 30 | Nam | 2024-04-01 | 6500 | 22500 |

Đối với Binh và Chi có cùng ngày tuyển dụng, `ROWS` vẫn xử lý lần lượt theo thứ tự `EMPLOYEE_ID`; running total của Binh là 16000, sau đó của Chi là 23000.

## 12. ROWS và RANGE khác nhau

Đây là khác biệt tinh tế nhưng quan trọng.

- `ROWS` xác định frame theo **số dòng vật lý trong thứ tự analytic**.
- `RANGE` xác định frame theo **giá trị logic của biểu thức ORDER BY**; những dòng có cùng giá trị sort (peer rows) có thể cùng nằm trong frame tại `CURRENT ROW`.

Với dữ liệu có ngày tuyển dụng trùng, chạy:

~~~sql
SELECT
    department_id,
    employee_id,
    employee_name,
    hire_date,
    salary,
    SUM(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS range_running_salary
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

Kết quả ở phòng 10:

| EMPLOYEE_NAME | HIRE_DATE | SALARY | RANGE_RUNNING_SALARY |
|---|---|---:|---:|
| An | 2022-01-10 | 9000 | 9000 |
| Binh | 2022-03-15 | 7000 | 23000 |
| Chi | 2022-03-15 | 7000 | 23000 |
| Dung | 2023-01-20 | 5000 | 28000 |

Hai nhân viên Binh và Chi có cùng `HIRE_DATE`; `RANGE ... CURRENT ROW` tính đến toàn bộ peer group có cùng giá trị sort, nên cả hai nhận tổng 23000. Với `ROWS` và thứ tự phụ `EMPLOYEE_ID`, giá trị của từng dòng lần lượt là 16000 và 23000.

Phòng 20 cũng có hai người cùng ngày 2022-08-01: cả Giang và Hanh nhận `RANGE_RUNNING_SALARY = 32000`, trong khi ROWS cho kết quả 22000 rồi 32000.

### 12.1. Khi nào dùng ROWS?

Dùng `ROWS` khi ý nghĩa là “tính từ N dòng trước đến dòng hiện tại”, ví dụ:

~~~sql
AVG(salary) OVER (
    PARTITION BY department_id
    ORDER BY hire_date, employee_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
~~~

Đây là trung bình của tối đa ba nhân viên trong thứ tự tuyển dụng: hai dòng trước và dòng hiện tại. Nếu partition chưa có đủ hai dòng trước, frame chỉ chứa những dòng hiện có.

### 12.2. Khi nào dùng RANGE?

Dùng `RANGE` khi ý nghĩa là cửa sổ theo giá trị sort, chẳng hạn tổng lũy kế theo thời điểm và muốn các dòng cùng thời điểm nhận cùng kết quả. `RANGE` với `UNBOUNDED PRECEDING ... CURRENT ROW` thường hữu ích khi các giá trị sort trùng cần được xử lý như một nhóm peer.

Với frame có offset như `RANGE BETWEEN INTERVAL '7' DAY PRECEDING AND CURRENT ROW`, kiểu dữ liệu và biểu thức sort phải phù hợp với quy tắc Oracle cho logical range. Cú pháp offset `RANGE` có những giới hạn riêng về số biểu thức sort; hãy kiểm tra cú pháp theo phiên bản Oracle khi dùng frame nâng cao.

### 12.3. Thứ tự không duy nhất và tính xác định

Nếu dùng `ROWS` nhưng `ORDER BY` không phân biệt được các dòng đồng hạng, thứ tự vật lý giữa các peer không được bảo đảm. Vì thế running total có thể thay đổi thứ tự giá trị giữa các dòng đồng hạng qua các kế hoạch thực thi khác nhau.

Để có kết quả ổn định, thêm khóa duy nhất:

~~~sql
ORDER BY hire_date, employee_id
~~~

Nếu nghiệp vụ muốn các dòng cùng ngày nhận cùng running total, hãy cân nhắc `RANGE` và chỉ rõ tiêu chí sort phù hợp. Không thêm khóa phụ vào RANGE một cách máy móc nếu điều đó làm thay đổi peer group cần giữ.

## 13. Default window frame khi có ORDER BY

Với các hàm tổng hợp analytic hỗ trợ windowing, khi có `ORDER BY` nhưng **không viết windowing clause**, Oracle mặc định dùng frame tương đương:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Do đó:

~~~sql
SUM(salary) OVER (
    PARTITION BY department_id
    ORDER BY hire_date
)
~~~

có thể tạo kết quả lũy kế theo RANGE, trong đó các nhân viên cùng ngày tuyển dụng nhận cùng tổng. Nếu muốn lũy kế theo từng dòng vật lý và thứ tự ổn định, viết frame `ROWS` tường minh:

~~~sql
SUM(salary) OVER (
    PARTITION BY department_id
    ORDER BY hire_date, employee_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Không nên bỏ windowing clause rồi mặc định rằng Oracle đang tính từng dòng một. Với dữ liệu có giá trị sort trùng, khác biệt giữa RANGE và ROWS có thể làm kết quả khác nhau.

## 14. Cửa sổ trượt (sliding window)

Ví dụ tính trung bình lương của tối đa ba nhân viên gần nhất theo thứ tự tuyển dụng trong mỗi phòng:

~~~sql
SELECT
    department_id,
    employee_id,
    employee_name,
    hire_date,
    salary,
    AVG(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3_rows
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

Ở mỗi dòng:

- Dòng đầu partition chỉ có một mức lương để tính trung bình.
- Dòng thứ hai có hai dòng.
- Từ dòng thứ ba trở đi, frame có tối đa ba dòng.
- Khi đi tiếp, cửa sổ trượt về phía trước; dòng cũ ra khỏi frame khi đã cách quá hai dòng.

Đây là trung bình theo **ba dòng**, không nhất thiết là trung bình của ba ngày hoặc bảy ngày. Nếu yêu cầu nghiệp vụ là “trung bình trong 30 ngày gần nhất”, cần thiết kế `RANGE` theo biểu thức ngày và khoảng thời gian phù hợp.

## 15. LAG và LEAD: truy cập dòng trước/sau

`LAG` đọc giá trị ở dòng đứng trước trong thứ tự analytic; `LEAD` đọc giá trị ở dòng tiếp theo. Chúng thường dùng để so sánh mức lương, doanh thu hoặc trạng thái giữa các thời điểm.

~~~sql
SELECT
    department_id,
    employee_id,
    employee_name,
    hire_date,
    salary,
    LAG(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
    ) AS previous_salary,
    LEAD(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
    ) AS next_salary
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

Ở dòng đầu mỗi phòng, `PREVIOUS_SALARY` là NULL vì không có dòng trước trong partition. Ở dòng cuối, `NEXT_SALARY` là NULL. NULL ở đây có nghĩa không có dòng ở vị trí đó, không nhất thiết là cột salary nguồn bị NULL.

Có thể chỉ định offset và giá trị mặc định:

~~~sql
LAG(salary, 1, 0) OVER (
    PARTITION BY department_id
    ORDER BY hire_date, employee_id
)
~~~

Nếu không có dòng trước, biểu thức trả 0 theo đối số mặc định. Chỉ dùng giá trị mặc định khi nó có ý nghĩa nghiệp vụ; thay “không có dòng trước” thành 0 có thể làm sai phép tính tiếp theo nếu 0 không phải cách biểu diễn phù hợp.

## 16. FIRST_VALUE và LAST_VALUE

`FIRST_VALUE` lấy giá trị đầu tiên trong cửa sổ; `LAST_VALUE` lấy giá trị cuối cùng trong cửa sổ. Cần chú ý window frame, đặc biệt với `LAST_VALUE`.

~~~sql
SELECT
    department_id,
    employee_id,
    employee_name,
    hire_date,
    salary,
    FIRST_VALUE(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_hire_salary,
    LAST_VALUE(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_hire_salary
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

Ở đây frame bao trùm toàn bộ partition nên mọi dòng cùng phòng có cùng giá trị đầu tiên và cuối cùng theo thứ tự tuyển dụng.

Nếu viết `LAST_VALUE(salary) OVER (PARTITION BY department_id ORDER BY hire_date, employee_id)` mà không chỉ rõ frame, default frame kết thúc ở dòng hiện tại (theo default RANGE), nên giá trị “last” có thể chỉ là giá trị cuối của frame tính đến hiện tại chứ không phải dòng cuối của cả partition. Khi cần giá trị cuối toàn partition, viết rõ:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

Đây là một ví dụ vì sao phải hiểu `ORDER BY` và windowing clause chứ không chỉ nhớ tên hàm.

## 17. NTILE và phân nhóm theo thứ tự

`NTILE(n)` chia các dòng trong mỗi partition thành tối đa n nhóm có số dòng gần bằng nhau, dựa trên thứ tự analytic:

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    NTILE(4) OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS salary_quartile
FROM lab_af_employee
ORDER BY department_id, salary DESC, employee_id;
~~~

Với `NTILE(4)`, mỗi phòng ban được chia thành tối đa bốn bucket. Phòng có bốn nhân viên thường có một người mỗi bucket; phòng có ba nhân viên chỉ có ba bucket chứa dòng. `NTILE` chia theo **số dòng**, không bảo đảm các bucket có khoảng lương bằng nhau và có thể tách những người bằng lương sang bucket khác. Nếu muốn giữ đồng hạng theo giá trị, hãy cân nhắc `RANK`/`DENSE_RANK` thay vì NTILE.

## 18. Kết hợp GROUP BY và hàm phân tích

Hàm phân tích có thể chạy trên tập kết quả đã được tổng hợp bởi `GROUP BY`. Ví dụ: tổng lương theo phòng ban, rồi xếp hạng các phòng ban theo tổng lương.

~~~sql
SELECT
    department_id,
    department_total,
    RANK() OVER (
        ORDER BY department_total DESC
    ) AS department_rank
FROM (
    SELECT
        department_id,
        SUM(salary) AS department_total
    FROM lab_af_employee
    GROUP BY department_id
) department_totals
ORDER BY department_rank;
~~~

Kết quả:

| DEPARTMENT_ID | DEPARTMENT_TOTAL | DEPARTMENT_RANK |
|---:|---:|---:|
| 20 | 38000 | 1 |
| 10 | 28000 | 2 |
| 30 | 22500 | 3 |

Có thể viết cùng ý bằng CTE:

~~~sql
WITH department_totals AS (
    SELECT
        department_id,
        SUM(salary) AS department_total
    FROM lab_af_employee
    GROUP BY department_id
)
SELECT
    department_id,
    department_total,
    RANK() OVER (
        ORDER BY department_total DESC
    ) AS department_rank
FROM department_totals
ORDER BY department_rank;
~~~

Đây là hai tầng tính toán:

1. `GROUP BY` đổi grain từ nhân viên sang phòng ban.
2. `RANK() OVER(...)` xếp hạng các dòng phòng ban đã tổng hợp.

Không đặt analytic function bên trong một analytic function khác ở cùng query block. Nếu cần dùng kết quả analytic này làm đầu vào cho analytic khác, hãy chia thành inline view hoặc CTE để tạo query block mới.

## 19. Lọc kết quả hàm phân tích

Hàm phân tích được tính sau các giai đoạn `FROM`, `WHERE`, `GROUP BY` và `HAVING` trong cùng query block. Vì vậy, không thể dùng alias analytic mới tạo trong `WHERE` cùng cấp:

~~~sql
-- Không hợp lệ theo phạm vi xử lý của query block:
SELECT
    employee_id,
    department_id,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS rn
FROM lab_af_employee
WHERE rn <= 2;
~~~

Hãy đưa analytic vào inline view rồi lọc ở query ngoài:

~~~sql
SELECT employee_id, department_id, salary, rn
FROM (
    SELECT
        employee_id,
        department_id,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM lab_af_employee
)
WHERE rn <= 2
ORDER BY department_id, rn;
~~~

Hoặc dùng CTE:

~~~sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM lab_af_employee
)
SELECT employee_id, department_id, salary, rn
FROM ranked_employees
WHERE rn <= 2
ORDER BY department_id, rn;
~~~

Ở Oracle 23c trở lên có cú pháp `QUALIFY` để lọc kết quả analytic trong một số trường hợp; với môi trường Oracle 19c/21c thường gặp, inline view hoặc CTE là cách viết tương thích phổ biến. Hãy xác nhận phiên bản database trước khi dùng cú pháp mới.

## 20. Nhiều hàm analytic trong cùng một SELECT

Một query block có thể tính nhiều hàm phân tích trên cùng hoặc khác cửa sổ:

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_avg,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS salary_rank,
    SUM(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

Ba hàm có ba mục đích:

- Trung bình phòng ban không cần thứ tự dòng.
- Xếp hạng lương cần thứ tự lương giảm dần.
- Tổng lũy kế cần thứ tự ngày tuyển dụng và frame ROWS.

Không cần tạo ba query riêng nếu các kết quả có thể tính cùng query block mà không làm thay đổi grain.

## 21. ORDER BY và tie-breaking

Một lỗi thường gặp là dùng:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

Khi nhiều người cùng lương, Oracle vẫn phải đánh số khác nhau nhưng thứ tự giữa các dòng đồng lương không được xác định duy nhất. Nếu dùng kết quả để chọn một người, ví dụ `rn = 1`, có thể chọn một trong những người đồng lương theo thứ tự không ổn định.

Nếu nghiệp vụ quy định ưu tiên nhân viên có ngày tuyển dụng sớm hơn, viết:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC, hire_date ASC, employee_id ASC
)
~~~

Nếu nghiệp vụ muốn **tất cả người đồng lương cao nhất**:

~~~sql
RANK() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

và lọc `RANK_VALUE = 1` ở query ngoài. Đừng thêm `EMPLOYEE_ID` vào ORDER BY của RANK nếu muốn giữ đồng hạng theo lương, vì thêm cột phụ có thể làm các dòng không còn peer.

## 22. NULL trong analytic ORDER BY và aggregate

Các hàm aggregate analytic như `SUM`, `AVG`, `MIN`, `MAX` thường bỏ qua giá trị NULL của biểu thức đầu vào, tương tự aggregate thông thường. `COUNT(expr)` chỉ đếm biểu thức khác NULL; `COUNT(*)` đếm dòng trong cửa sổ.

Nếu biểu thức dùng để sắp xếp có NULL, hãy xác định vị trí mong muốn:

~~~sql
RANK() OVER (
    PARTITION BY department_id
    ORDER BY commission_pct DESC NULLS LAST
)
~~~

Ví dụ trên cần có cột `COMMISSION_PCT` trong bảng thực tế; bảng lab hiện tại không có cột đó. `NULLS LAST` làm các giá trị chưa biết đứng cuối khi xếp giảm dần.

Nếu partition key là NULL, các dòng cùng giá trị partition NULL nằm trong cùng partition. Nếu `ORDER BY` có các giá trị NULL, chúng có thể trở thành peer theo quy tắc sort và ảnh hưởng `RANK`, `RANGE` hoặc các hàm lấy dòng.

## 23. Hiểu thứ tự logic và vị trí của analytic function

Một cách hình dung phổ biến về thứ tự logic của SELECT:

~~~text
FROM / JOIN
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
      |
      v
ANALYTIC FUNCTIONS
      |
      v
ORDER BY (kết quả cuối)
~~~

Sơ đồ giúp hiểu vì sao:

- Analytic function có thể dùng trên kết quả đã GROUP BY.
- WHERE cùng query block không thể lọc trực tiếp alias analytic vừa tạo.
- Query ngoài có thể lọc cột analytic của inline view.
- `ORDER BY` trong `OVER` và `ORDER BY` cuối câu có phạm vi khác nhau.

Đây là mô hình logic để hiểu ngữ nghĩa, không phải lời khẳng định rằng optimizer thực thi vật lý theo đúng thứ tự văn bản. Oracle có thể biến đổi query block, nhưng phải giữ kết quả theo ngữ nghĩa SQL.

## 24. Hiệu năng và execution plan

Hàm phân tích thường cần sắp xếp hoặc xử lý các partition. Trên bảng lớn, chi phí phụ thuộc:

- Số dòng đầu vào sau WHERE/JOIN.
- Số partition và kích thước từng partition.
- Biểu thức ORDER BY và khả năng tận dụng thứ tự/index phù hợp.
- Số lượng hàm analytic và cửa sổ khác nhau.
- Khả năng sort trong bộ nhớ hay cần temporary space.
- Statistics và phân bố dữ liệu.

Một số nguyên tắc:

1. Lọc những dòng không cần thiết bằng WHERE trước khi tính analytic, nếu đúng nghiệp vụ.
2. Chọn partition key đúng; không chia nhỏ hoặc gộp sai phạm vi.
3. Viết ORDER BY đủ để xác định thứ tự khi dùng ROW_NUMBER hoặc ROWS.
4. Chỉ dùng window frame cần thiết; không mặc định mọi bài toán đều là running total.
5. Xem execution plan và thống kê runtime trước khi thêm hint hoặc index.

### 24.1. Xem execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS rn
FROM lab_af_employee;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` cho kế hoạch ước lượng trong ngữ cảnh phân tích; nó không tự chứng minh kết quả đúng và không thay thế số liệu runtime. Khi có quyền và đã thực thi câu lệnh, `DBMS_XPLAN.DISPLAY_CURSOR` có thể cung cấp thông tin cursor và thống kê thực tế nếu được thu thập phù hợp.

Với bảng lab chỉ có 11 dòng, full table scan và sort nhỏ là bình thường. Không tạo index chỉ để buộc Oracle dùng index trong ví dụ nhỏ. Trên workload thật, đo trước và sau thay đổi bằng dữ liệu đại diện.

## 25. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ORA-30483: window functions are not allowed here` | Đặt analytic function ở vị trí không hỗ trợ, thường là WHERE/HAVING cùng query block | Đưa analytic vào inline view/CTE rồi lọc ở query ngoài |
| `ORA-00904: invalid identifier` | Tham chiếu alias/cột analytic sai phạm vi hoặc cột không tồn tại | Kiểm tra select list của query block trong |
| Top-N chọn người không ổn định | ORDER BY của ROW_NUMBER không tạo thứ tự duy nhất | Thêm khóa phụ như employee_id |
| Running total của người cùng ngày bằng nhau | Dùng RANGE hoặc default frame có peer semantics | Dùng ROWS với tie-breaker nếu cần tính từng dòng |
| LAST_VALUE không trả dòng cuối partition | Frame kết thúc ở CURRENT ROW | Chỉ rõ UNBOUNDED FOLLOWING khi cần toàn partition |
| Kết quả hiển thị không theo thứ tự analytic | Chỉ có ORDER BY trong OVER | Thêm ORDER BY ở query ngoài cùng |
| Tổng lương bị lặp khi JOIN bảng chi tiết | JOIN làm nhân dòng trước analytic aggregate | Tổng hợp về đúng grain trước khi JOIN hoặc kiểm soát cardinality |
| RANK không giữ đồng hạng như mong đợi | Đưa thêm cột tie-breaker vào analytic ORDER BY | Chỉ xếp theo các tiêu chí thực sự định nghĩa đồng hạng |
| Cửa sổ trượt có kết quả lạ | Nhầm ROWS với RANGE hoặc bỏ qua default frame | Viết windowing clause tường minh |

## 26. Bài tập thực hành

### Bài 1 — Trung bình phòng ban

Hiển thị từng nhân viên, lương và mức lương trung bình phòng ban trên cùng dòng.

**Gợi ý:** `AVG(salary) OVER (PARTITION BY department_id)`.

### Bài 2 — Xếp hạng lương

Trong từng phòng ban, xếp nhân viên theo lương giảm dần. So sánh `ROW_NUMBER`, `RANK` và `DENSE_RANK`.

**Gợi ý:** phòng 10 có hai người cùng lương 7000; quan sát hạng tiếp theo là 4 với RANK nhưng 3 với DENSE_RANK.

### Bài 3 — Top hai dòng

Lấy đúng tối đa hai nhân viên mỗi phòng ban có lương cao nhất.

**Gợi ý:** dùng ROW_NUMBER với PARTITION BY department_id và ORDER BY salary DESC, employee_id; lọc RN <= 2 ở query ngoài.

### Bài 4 — Top hai mức lương

Lấy tất cả nhân viên thuộc hai mức lương cao nhất trong từng phòng.

**Gợi ý:** DENSE_RANK theo salary DESC; lọc hạng <= 2. Số dòng có thể nhiều hơn hai.

### Bài 5 — Tổng lũy kế

Tính tổng lương lũy kế theo ngày tuyển dụng trong từng phòng ban.

**Gợi ý:** SUM(salary) OVER (PARTITION BY department_id ORDER BY hire_date, employee_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW).

### Bài 6 — So sánh ROWS và RANGE

Chạy hai truy vấn running total theo hire_date, một dùng ROWS và một dùng RANGE. Quan sát Binh/Chi và Giang/Hanh.

**Gợi ý:** ROWS với tie-breaker cho giá trị lần lượt; RANGE gom peer rows cùng ngày nên các giá trị tại peer group bằng nhau.

### Bài 7 — Lương của người trước và sau

Hiển thị lương nhân viên trước và sau trong cùng phòng theo ngày tuyển dụng.

**Gợi ý:** LAG và LEAD với PARTITION BY department_id, ORDER BY hire_date, employee_id.

### Bài 8 — Lọc analytic

Viết truy vấn lấy nhân viên đứng đầu mỗi phòng ban. So sánh người đứng đầu duy nhất theo ROW_NUMBER và tất cả người đồng hạng cao nhất theo RANK.

**Gợi ý:** tạo analytic trong inline view, lọc RN = 1 hoặc RANK_VALUE = 1 ở query ngoài.

### Bài 9 — Xếp hạng phòng ban theo tổng lương

Tổng hợp lương theo phòng ban rồi xếp hạng các phòng ban theo tổng giảm dần.

**Gợi ý:** GROUP BY trong inline view/CTE; RANK() OVER (ORDER BY department_total DESC) ở query ngoài.

## 27. Quy trình chọn OVER, PARTITION BY và ORDER BY

Khi viết một hàm phân tích, hãy trả lời các câu hỏi:

1. **Cần tính hàm nào?** SUM, AVG, COUNT, ROW_NUMBER, RANK, LAG hay LEAD?
2. **Phạm vi tính là gì?** Toàn bộ kết quả hay từng nhóm? Nếu theo nhóm, chọn PARTITION BY nào?
3. **Có cần thứ tự không?** Nếu có, ORDER BY nào phản ánh đúng thứ tự nghiệp vụ?
4. **Có cần cửa sổ con không?** Running total, rolling average hay toàn partition?
5. **ROWS hay RANGE?** Đếm theo số dòng hay theo giá trị sort/peer group?
6. **Có giá trị bằng nhau không?** Cần tie-breaker hay phải giữ đồng hạng?
7. **Có cần lọc kết quả analytic không?** Dùng inline view/CTE hoặc cú pháp QUALIFY nếu phiên bản hỗ trợ.
8. **Thứ tự hiển thị cuối là gì?** Viết ORDER BY ở query ngoài cùng.

Sơ đồ:

~~~text
Chọn analytic function
          |
          v
Chọn phạm vi PARTITION BY
          |
          v
Có cần thứ tự tính?
       /       \
     Không      Có
       |         |
       |         v
       |    Chọn ORDER BY
       |         |
       |         v
       |    Cần window frame?
       |      /       \
       |    Không      Có
       |      |         |
       |      |         v
       |      |    Chọn ROWS hoặc RANGE
       |      |         |
       +------+---------+
              |
              v
       Tính analytic
              |
              v
       Cần lọc analytic?
          /       \
        Không      Có
          |         |
          |         v
          |    Inline view / CTE
          |         |
          +----+----+
               |
               v
       ORDER BY kết quả cuối
~~~

`OVER` xác định cửa sổ mà hàm phân tích làm việc; `PARTITION BY` chia cửa sổ thành các vùng độc lập; `ORDER BY` xác định thứ tự trong từng vùng và, khi kết hợp windowing clause, xác định những dòng được tính cho mỗi kết quả. Hãy luôn phân biệt thứ tự analytic với thứ tự hiển thị, phân biệt `ROWS` với `RANGE`, và xác định rõ cách xử lý đồng hạng. Khi các lựa chọn đó phản ánh đúng yêu cầu nghiệp vụ, hàm phân tích Oracle có thể bổ sung thống kê, xếp hạng, lũy kế và so sánh dòng trước/sau mà vẫn giữ được từng dòng chi tiết.

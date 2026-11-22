# Phân biệt hàm tổng hợp và hàm phân tích theo cửa sổ trong Oracle

Khi viết báo cáo SQL, bạn thường cần trả lời hai câu hỏi khác nhau: **mỗi nhóm có tổng cộng bao nhiêu?** và **mỗi hàng đóng góp thế nào so với các hàng khác trong nhóm?** Hàm tổng hợp (*aggregate function*) giải quyết câu hỏi thứ nhất bằng cách gom nhiều hàng thành một kết quả cho mỗi nhóm. Hàm phân tích (*analytic function*, thường gọi là window function) giải quyết câu hỏi thứ hai bằng cách tính trên một cửa sổ hàng liên quan nhưng vẫn giữ các hàng của truy vấn ở mức chi tiết hiện tại.

Ví dụ bảng giao dịch có nhiều đơn cho mỗi khách hàng:

- `GROUP BY customer_id` cùng `SUM(amount)` trả một hàng cho mỗi khách hàng.
- `SUM(amount) OVER (PARTITION BY customer_id)` tính tổng của khách hàng trên từng hàng giao dịch, vì vậy vẫn thấy từng đơn hàng.

Hai biểu thức đều có thể dùng `SUM`, nhưng cách đặt và ý nghĩa của chúng khác nhau. Trong Oracle, phần `OVER(...)` biến một hàm có thể tổng hợp thành phép tính phân tích trên cửa sổ. Hiểu ranh giới này giúp tránh lỗi mất chi tiết dữ liệu, tránh JOIN vòng lại bảng chỉ để bổ sung tổng nhóm và viết báo cáo theo thứ tự thời gian chính xác.

Bài học thuộc chủ đề **Hàm phân tích** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Khác biệt về số hàng giữa aggregate và analytic.
- Cú pháp `OVER`, `PARTITION BY`, `ORDER BY` và window frame.
- Thời điểm Oracle đánh giá aggregate, analytic và các mệnh đề lọc.
- `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `LAG`, `LEAD`, running total và moving average.
- Các lỗi thường gặp về tie, NULL, frame mặc định và thứ tự kết quả.
- Cách đọc execution plan và bài thực hành SQL.

## 1. Hàm tổng hợp: gom nhiều hàng thành kết quả theo nhóm

Hàm tổng hợp nhận nhiều giá trị đầu vào và trả về một giá trị cho một tập hàng. Các hàm thường dùng:

| Hàm | Công dụng |
| --- | --- |
| `COUNT(*)` | Đếm số hàng. |
| `COUNT(expr)` | Đếm số giá trị khác NULL của biểu thức. |
| `SUM(expr)` | Tính tổng các giá trị số khác NULL. |
| `AVG(expr)` | Tính trung bình các giá trị số khác NULL. |
| `MIN(expr)` | Tìm giá trị nhỏ nhất. |
| `MAX(expr)` | Tìm giá trị lớn nhất. |
| `STDDEV(expr)` / `VARIANCE(expr)` | Tính độ lệch chuẩn / phương sai theo định nghĩa Oracle. |

Nếu không có `GROUP BY`, hàm tổng hợp thường tính trên toàn bộ tập hàng sau `FROM` và `WHERE`, rồi trả một hàng:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount
FROM orders
WHERE order_status = 'PAID';
~~~

Nếu có `GROUP BY`, Oracle chia các hàng thành nhóm theo biểu thức nhóm và trả một hàng cho mỗi nhóm:

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(amount) AS total_amount
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id;
~~~

Kết quả không còn một hàng cho mỗi đơn hàng. Mỗi `CUSTOMER_ID` chỉ còn một hàng chứa số lượng và tổng tiền của các đơn PAID thuộc khách hàng đó.

### Ví dụ dữ liệu

Giả sử bảng `LAB_ORDERS`:

| ORDER_ID | CUSTOMER_ID | ORDER_DATE | AMOUNT |
| ---: | ---: | --- | ---: |
| 101 | 10 | 2026-01-01 | 100 |
| 102 | 10 | 2026-01-03 | 50 |
| 103 | 20 | 2026-01-03 | 80 |
| 104 | 10 | 2026-01-05 | 25 |
| 105 | 20 | 2026-01-06 | 20 |

Aggregate:

~~~sql
SELECT customer_id,
       SUM(amount) AS customer_total
FROM lab_orders
GROUP BY customer_id;
~~~

Kết quả có hai hàng:

| CUSTOMER_ID | CUSTOMER_TOTAL |
| ---: | ---: |
| 10 | 175 |
| 20 | 100 |

Các hàng đơn hàng đã được gom lại. Nếu báo cáo cần vừa hiển thị từng đơn vừa có tổng của khách hàng, chỉ dùng `GROUP BY customer_id` sẽ làm mất các cột chi tiết như `ORDER_ID` và `ORDER_DATE`.

## 2. Hàm phân tích: tính trên cửa sổ nhưng giữ hàng chi tiết

Hàm phân tích thực hiện phép tính trên một tập hàng liên quan tới hàng hiện tại, gọi là **window** hoặc cửa sổ. Kết quả được gắn vào từng hàng của query block; nó không tự gom các hàng thành một hàng mỗi nhóm như `GROUP BY`.

Cú pháp tổng quát:

~~~sql
analytic_function([arguments])
    OVER (
        [PARTITION BY partition_expression, ...]
        [ORDER BY sort_expression [ASC|DESC], ...]
        [windowing_clause]
    )
~~~

- `OVER(...)` cho Oracle biết đây là phép tính phân tích.
- `PARTITION BY` chia tập hàng thành các phân vùng độc lập. Nếu bỏ qua, toàn bộ tập hàng của query block là một partition.
- `ORDER BY` xác định thứ tự logic trong mỗi partition cho những phép tính phụ thuộc thứ tự.
- Window frame (nếu có) xác định tập con hàng quanh hàng hiện tại được dùng cho phép tính.

Ví dụ:

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
       ) AS customer_total
FROM lab_orders
ORDER BY customer_id, order_date, order_id;
~~~

Kết quả vẫn có năm hàng. Ba hàng của khách hàng 10 đều hiển thị `CUSTOMER_TOTAL = 175`; hai hàng của khách hàng 20 đều hiển thị `CUSTOMER_TOTAL = 100`.

| ORDER_ID | CUSTOMER_ID | AMOUNT | CUSTOMER_TOTAL |
| ---: | ---: | ---: | ---: |
| 101 | 10 | 100 | 175 |
| 102 | 10 | 50 | 175 |
| 104 | 10 | 25 | 175 |
| 103 | 20 | 80 | 100 |
| 105 | 20 | 20 | 100 |

Khác biệt quan trọng:

| Đặc điểm | Aggregate với GROUP BY | Analytic với OVER |
| --- | --- | --- |
| Đơn vị kết quả | Một hàng cho mỗi nhóm | Giữ từng hàng đầu vào của query block hiện tại |
| Phạm vi tính | Toàn nhóm | Toàn partition hoặc window frame của hàng hiện tại |
| Chia nhóm | `GROUP BY` | `PARTITION BY` bên trong OVER |
| Sắp xếp trong phép tính | Thường không cần | Có thể dùng `ORDER BY` trong OVER |
| Dùng cho | Tổng hợp, báo cáo theo nhóm | Xếp hạng, lũy kế, so sánh hàng trước/sau, tỷ lệ trên tổng |

### Aggregate không có GROUP BY và analytic không có PARTITION BY

Hai trường hợp nhìn qua có vẻ giống nhau nhưng vẫn khác:

~~~sql
-- Một hàng duy nhất cho toàn bộ tập kết quả.
SELECT SUM(amount) AS grand_total
FROM lab_orders;

-- Tổng toàn bộ tập được lặp trên từng hàng.
SELECT order_id,
       amount,
       SUM(amount) OVER () AS grand_total
FROM lab_orders;
~~~

`SUM(amount)` trong SELECT đầu tiên trả một hàng. `SUM(amount) OVER()` trong SELECT thứ hai trả một tổng nhưng lặp lại trên từng hàng chi tiết.

## 3. PARTITION BY: chia cửa sổ theo nhóm

`PARTITION BY` chia dữ liệu thành các partition độc lập cho phép tính analytic. Nó không loại bỏ hàng và cũng không nhất thiết sắp xếp output.

~~~sql
SELECT order_id,
       customer_id,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
       ) AS total_by_customer,
       SUM(amount) OVER (
           PARTITION BY TRUNC(order_date)
       ) AS total_by_order_day
FROM lab_orders;
~~~

Trong cùng query có thể có nhiều hàm phân tích với partition khác nhau. Tổng theo khách hàng và tổng theo ngày được tính độc lập trên cùng các hàng.

### Partition nhiều cột

~~~sql
SELECT department_id,
       job_id,
       employee_id,
       salary,
       AVG(salary) OVER (
           PARTITION BY department_id, job_id
       ) AS avg_salary_by_dept_job
FROM employees;
~~~

Mỗi partition là một tổ hợp `DEPARTMENT_ID` và `JOB_ID`. Những nhân viên cùng phòng ban nhưng khác job nằm ở các partition khác nhau.

### Bỏ PARTITION BY

~~~sql
SELECT employee_id,
       salary,
       SUM(salary) OVER () AS company_payroll
FROM employees;
~~~

Khi không có `PARTITION BY`, Oracle tính trên toàn bộ tập hàng của query block. Đây là cách lặp tổng công ty trên mỗi nhân viên.

### PARTITION BY không giống GROUP BY

`GROUP BY department_id` gom nhiều nhân viên thành một hàng/phòng ban. `PARTITION BY department_id` chỉ định nhóm dùng cho phép tính analytic, còn từng nhân viên vẫn được giữ:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       SUM(salary) OVER (
           PARTITION BY department_id
       ) AS dept_payroll
FROM employees;
~~~

## 4. ORDER BY bên trong OVER và ORDER BY của truy vấn

Có hai mệnh đề ORDER BY với vai trò khác nhau:

1. `ORDER BY` bên trong `OVER(...)` quy định thứ tự **logic để tính hàm analytic**.
2. `ORDER BY` ở cuối SELECT quy định thứ tự **hiển thị kết quả** cho client.

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       amount,
       ROW_NUMBER() OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS order_sequence
FROM lab_orders
ORDER BY amount DESC;
~~~

`ORDER_SEQUENCE` được đánh theo ngày và ID trong từng khách hàng, nhưng kết quả hiển thị lại được sắp xếp theo `AMOUNT DESC`. Thứ tự bên trong OVER **không bảo đảm thứ tự hàng trả về**; muốn output có thứ tự khác, phải viết ORDER BY ngoài cùng.

### Cần tiêu chí phá hòa

Nếu nhiều hàng có cùng `ORDER_DATE`, chỉ viết:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY order_date
)
~~~

có thể tạo thứ tự không xác định giữa các hàng cùng ngày. Nếu nghiệp vụ yêu cầu kết quả lặp lại ổn định, thêm khóa duy nhất:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
)
~~~

Đây là nguyên tắc quan trọng với `ROW_NUMBER`, running total dùng `ROWS`, và mọi logic phụ thuộc vị trí hàng.

## 5. Window frame: cửa sổ cụ thể quanh hàng hiện tại

`PARTITION BY` xác định nhóm, còn window frame xác định **phần nào của partition** được dùng cho phép tính trên hàng hiện tại. Frame thường được viết với `ROWS` hoặc `RANGE`.

### ROWS: đếm theo vị trí hàng

`ROWS` xác định frame bằng số hàng vật lý trước/sau hàng hiện tại trong thứ tự analytic:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS running_total
~~~

Frame bắt đầu từ hàng đầu tiên của partition và kết thúc tại hàng hiện tại. Kết quả là tổng lũy kế.

Moving sum của ba giao dịch gần nhất (hàng hiện tại và hai hàng trước):

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
) AS moving_sum_3_rows
~~~

`ROWS` phụ thuộc thứ tự từng hàng. Nếu các khóa ORDER BY bị trùng và không có tie-breaker, hàng nào đứng trước có thể không ổn định; hãy thêm khóa duy nhất khi thứ tự có ý nghĩa.

### RANGE: xác định frame theo giá trị sort

`RANGE` xác định cửa sổ theo giá trị logic của biểu thức ORDER BY, không phải số lượng hàng. Các hàng có cùng giá trị sort (peers) được xem cùng vị trí logic.

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS running_total_by_day
~~~

Nếu một khách hàng có hai đơn cùng ngày, cả hai hàng có thể nhận cùng kết quả lũy kế kết thúc ở ngày đó, vì frame RANGE tới CURRENT ROW bao gồm các peer có cùng `ORDER_DATE`.

Với khoảng thời gian, Oracle cho phép frame RANGE theo biểu thức sort phù hợp, ví dụ:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date
    RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW
) AS rolling_7_calendar_days
~~~

Ví dụ này dùng một biểu thức ngày trong ORDER BY và cửa sổ bảy ngày lịch (ngày hiện tại cộng sáu ngày trước đó). Quy tắc cú pháp RANGE offset có một số hạn chế về số lượng/kiểu biểu thức ORDER BY; với interval offset, hãy dùng biểu thức ngày/giờ tương thích.

### UNBOUNDED, PRECEDING, FOLLOWING và CURRENT ROW

| Từ khóa | Ý nghĩa |
| --- | --- |
| `UNBOUNDED PRECEDING` | Bắt đầu từ đầu partition. |
| `n PRECEDING` | Lùi n hàng (ROWS) hoặc một khoảng giá trị (RANGE). |
| `CURRENT ROW` | Hàng hiện tại; với RANGE, bao gồm các peer cùng giá trị sort. |
| `n FOLLOWING` | Tiến n hàng hoặc khoảng giá trị về phía sau. |
| `UNBOUNDED FOLLOWING` | Kết thúc ở cuối partition. |

Ví dụ tổng toàn partition cho mọi hàng:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
~~~

Nếu không cần thứ tự hay frame, có thể viết đơn giản `SUM(amount) OVER (PARTITION BY customer_id)`.

### Frame mặc định có thể gây bất ngờ

Với nhiều hàm analytic có hỗ trợ windowing, khi có `ORDER BY` trong OVER mà không viết frame rõ ràng, Oracle dùng frame mặc định tương đương:

`RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`

Do đó biểu thức:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date
)
~~~

không phải tổng của toàn partition lặp trên mỗi hàng; nó là tổng lũy kế theo `RANGE`, bao gồm các hàng peer có cùng ngày. Muốn tổng toàn partition, bỏ ORDER BY trong OVER hoặc chỉ rõ frame đến `UNBOUNDED FOLLOWING`.

## 6. Cùng một hàm SUM nhưng hai ý nghĩa

Đây là ví dụ trung tâm để phân biệt aggregate và analytic:

~~~sql
-- Một hàng cho mỗi khách hàng.
SELECT customer_id,
       SUM(amount) AS total_amount
FROM lab_orders
GROUP BY customer_id;

-- Một hàng cho mỗi đơn hàng, kèm tổng của khách hàng.
SELECT order_id,
       customer_id,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
       ) AS total_amount
FROM lab_orders;
~~~

Biểu thức `SUM(amount)` là aggregate vì nó không có `OVER` và được dùng để gom nhóm. Biểu thức `SUM(amount) OVER(...)` là analytic vì kết quả được tính theo cửa sổ và gắn lại vào từng hàng.

### Aggregate trước, analytic sau

~~~sql
SELECT department_id,
       SUM(salary) AS dept_payroll,
       SUM(SUM(salary)) OVER () AS company_payroll,
       ROUND(
           100 * SUM(salary) / SUM(SUM(salary)) OVER (),
           2
       ) AS pct_of_company
FROM employees
GROUP BY department_id
ORDER BY department_id;
~~~

Thứ tự logic:

1. FROM/WHERE chọn nhân viên.
2. GROUP BY gom nhân viên theo phòng ban.
3. `SUM(salary)` tạo tổng từng phòng ban.
4. `SUM(SUM(salary)) OVER()` chạy analytic trên các hàng phòng ban đã tổng hợp.
5. SELECT trả một hàng/phòng ban với tổng phòng ban, tổng công ty và tỷ lệ.

`SUM(SUM(salary)) OVER()` không phải viết lặp vô nghĩa: SUM bên trong là aggregate theo nhóm; SUM bên ngoài có OVER là analytic trên tập kết quả nhóm.

## 7. Các hàm phân tích phổ biến

### ROW_NUMBER: đánh số hàng

`ROW_NUMBER()` gán số thứ tự duy nhất cho từng hàng trong partition theo ORDER BY:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS row_no
FROM employees;
~~~

Mỗi phòng ban bắt đầu từ 1. Nếu lương bằng nhau, `EMPLOYEE_ID` phá hòa để thứ tự ổn định.

Top 3 nhân viên lương cao nhất mỗi phòng ban:

~~~sql
WITH ranked_employees AS (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
           ) AS rn
    FROM employees
)
SELECT employee_id, department_id, salary
FROM ranked_employees
WHERE rn <= 3
ORDER BY department_id, rn;
~~~

### RANK và DENSE_RANK: xếp hạng có đồng hạng

Hai hàm đều cho các hàng cùng giá trị sort cùng thứ hạng, nhưng xử lý khoảng trống thứ hạng khác nhau:

| SALARY | ROW_NUMBER | RANK | DENSE_RANK |
| ---: | ---: | ---: | ---: |
| 9000 | 1 | 1 | 1 |
| 8500 | 2 | 2 | 2 |
| 8500 | 3 | 2 | 2 |
| 7000 | 4 | 4 | 3 |

- `ROW_NUMBER`: luôn là số thứ tự duy nhất; không giữ đồng hạng.
- `RANK`: hàng đồng hạng cùng rank, rank kế tiếp bị bỏ qua.
- `DENSE_RANK`: hàng đồng hạng cùng rank, rank kế tiếp tăng liên tục.

~~~sql
SELECT employee_id,
       department_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank,
       DENSE_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS dense_salary_rank
FROM employees;
~~~

Nếu yêu cầu “lấy ba người” thì `ROW_NUMBER <= 3` giới hạn số hàng. Nếu yêu cầu “lấy ba mức lương cao nhất, giữ tất cả người đồng hạng”, `DENSE_RANK <= 3` phù hợp hơn và có thể trả nhiều hơn ba hàng.

### LAG và LEAD: đọc hàng trước/sau

`LAG(expr, offset, default)` lấy giá trị từ hàng đứng trước trong thứ tự analytic; `LEAD` lấy giá trị từ hàng phía sau:

~~~sql
SELECT customer_id,
       order_id,
       order_date,
       amount,
       LAG(amount, 1, 0) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS previous_amount,
       LEAD(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS next_amount
FROM lab_orders;
~~~

Ở hàng đầu tiên của mỗi khách hàng, `LAG` trả default 0; nếu bỏ default, giá trị mặc định là NULL. Ở hàng cuối cùng, `LEAD` trả NULL nếu không có hàng sau. Đây là giá trị của hàng trước/sau theo thứ tự, không phải phép aggregate.

### FIRST_VALUE và LAST_VALUE

~~~sql
SELECT employee_id,
       department_id,
       salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS highest_salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS lowest_salary
FROM employees;
~~~

`FIRST_VALUE` lấy giá trị đầu tiên trong frame; `LAST_VALUE` lấy giá trị cuối cùng trong frame. Cần chú ý frame mặc định: nếu không khai báo frame kết thúc ở cuối partition, `LAST_VALUE` có thể trả giá trị của hàng hiện tại hoặc peer cuối trong frame hiện tại, không phải giá trị cuối toàn partition. Muốn giá trị cuối partition, chỉ rõ `UNBOUNDED FOLLOWING`.

### NTILE: chia thành các nhóm gần bằng nhau

~~~sql
SELECT employee_id,
       salary,
       NTILE(4) OVER (
           ORDER BY salary DESC, employee_id
       ) AS salary_quartile
FROM employees;
~~~

`NTILE(4)` chia các hàng thành bốn bucket có số lượng gần bằng nhau theo thứ tự. Nó không phải phân vị thống kê chính xác như `PERCENTILE_CONT`; khi số hàng không chia hết, kích thước bucket có thể chênh một hàng.

## 8. Aggregate function và analytic function không phải hai danh sách tách biệt

Nhiều hàm có thể hoạt động ở cả hai vai trò:

| Hàm | Không có OVER | Có OVER |
| --- | --- | --- |
| `SUM` | Tổng hợp thành một giá trị hoặc một giá trị/nhóm | Tổng trên partition/frame, giữ hàng |
| `AVG` | Trung bình của tập/nhóm | Trung bình trên partition/frame |
| `COUNT` | Đếm hàng/giá trị trong tập/nhóm | Đếm trên partition/frame |
| `MIN` / `MAX` | Giá trị nhỏ nhất/lớn nhất của tập/nhóm | Min/max trên partition/frame |
| `STDDEV` / `VARIANCE` | Thống kê của tập/nhóm | Thống kê trên partition/frame |

Một số hàm chủ yếu là analytic:

- `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`.
- `LAG`, `LEAD`.
- `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE`.
- Các hàm phân phối như `CUME_DIST`, `PERCENT_RANK`, `PERCENTILE_CONT` ở dạng analytic.

Điểm phân biệt không phải chỉ là tên hàm, mà là **có dùng OVER để yêu cầu tính theo cửa sổ hay không** và ngữ cảnh query block nơi hàm xuất hiện.

### COUNT(*) và COUNT(expr) trong analytic

~~~sql
SELECT employee_id,
       department_id,
       commission_pct,
       COUNT(*) OVER (
           PARTITION BY department_id
       ) AS employee_count,
       COUNT(commission_pct) OVER (
           PARTITION BY department_id
       ) AS commission_count
FROM employees;
~~~

`COUNT(*)` đếm mọi hàng trong partition. `COUNT(commission_pct)` chỉ đếm hàng có commission khác NULL. Kết quả được lặp trên mỗi nhân viên thuộc phòng ban đó.

## 9. Thời điểm đánh giá: WHERE, GROUP BY, HAVING và analytic

Hiểu thứ tự xử lý logic giúp tránh lỗi khi lọc theo kết quả analytic. Một mô hình khái quát:

~~~text
FROM / JOIN
    |
WHERE  -- loc hang dau vao
    |
GROUP BY  -- gom nhom
    |
HAVING  -- loc nhom
    |
SELECT expressions, including analytic functions
    |
ORDER BY  -- sap xep ket qua cuoi
~~~

Analytic functions được tính sau `FROM`, `WHERE`, `GROUP BY` và `HAVING` của query block hiện tại, trước ORDER BY cuối. Do đó:

- WHERE loại hàng trước khi analytic tính cửa sổ.
- GROUP BY tạo tập hàng nhóm trước khi analytic chạy trên tập nhóm đó.
- HAVING loại nhóm trước khi analytic chạy.
- Không thể dùng analytic function trực tiếp trong WHERE/GROUP BY/HAVING cùng query block theo cách thông thường.

### Vì sao không lọc ROW_NUMBER trực tiếp trong WHERE?

Ví dụ không hợp lệ:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS rn
FROM employees
WHERE rn <= 3;
~~~

Alias `RN` chưa có ở thời điểm WHERE được đánh giá; Oracle cũng không cho đặt analytic function trực tiếp trong WHERE của cùng query block. Dùng inline view hoặc CTE:

~~~sql
WITH ranked AS (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
           ) AS rn
    FROM employees
)
SELECT employee_id, department_id, salary, rn
FROM ranked
WHERE rn <= 3;
~~~

Query block bên trong tính `RN`; query block bên ngoài lọc kết quả đã có `RN`.

## 10. NULL và các trường hợp biên trong analytic

Aggregate thường bỏ qua NULL ở biểu thức đầu vào, ngoại trừ `COUNT(*)` đếm hàng. Ví dụ:

~~~sql
SELECT department_id,
       COUNT(*) AS all_employees,
       COUNT(commission_pct) AS employees_with_commission,
       AVG(commission_pct) AS avg_commission
FROM employees
GROUP BY department_id;
~~~

Các analytic aggregate như `COUNT(expr) OVER(...)` và `AVG(expr) OVER(...)` tuân theo quy tắc bỏ qua NULL tương ứng.

### NULL trong ORDER BY

Oracle cho phép chỉ định `NULLS FIRST` hoặc `NULLS LAST`:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY commission_pct DESC NULLS LAST, employee_id
)
~~~

Nếu không chỉ định, mặc định của Oracle thường là NULLS LAST cho ASC và NULLS FIRST cho DESC. Để logic xếp hạng dễ hiểu và ổn định giữa các chiều sort, hãy viết NULLS FIRST/LAST tường minh khi NULL có ý nghĩa nghiệp vụ.

### LAG/LEAD và NULL

`LAG`/`LEAD` có thể trả NULL vì:

- Không có hàng trước/sau trong partition.
- Hàng được tham chiếu có giá trị expression là NULL.
- Default được truyền vào là NULL.

Nếu cần bỏ qua các hàng mà expression NULL, Oracle hỗ trợ `IGNORE NULLS` trong các hàm thích hợp:

~~~sql
LAG(measurement) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at
)
~~~

Phân biệt `IGNORE NULLS` với default value: một bên bỏ qua hàng có giá trị NULL khi tìm vị trí trước/sau; bên kia chỉ cung cấp giá trị thay thế khi không có hàng tương ứng theo offset.

## 11. Running total, moving average và tỷ lệ trên tổng

### Tổng lũy kế theo khách hàng

~~~sql
SELECT customer_id,
       order_id,
       order_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_total
FROM lab_orders
ORDER BY customer_id, order_date, order_id;
~~~

Mỗi hàng nhận tổng tiền từ giao dịch đầu tiên của khách hàng tới giao dịch hiện tại. `ORDER_ID` là tie-breaker để thứ tự trong cùng ngày xác định.

### Moving average ba giao dịch

~~~sql
SELECT customer_id,
       order_id,
       order_date,
       amount,
       AVG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg_3_orders
FROM lab_orders;
~~~

Ở đầu partition, frame có thể có ít hơn ba hàng. AVG tính trung bình trên số giá trị khác NULL hiện có trong frame, không tự giả định đủ ba giao dịch.

### Tỷ lệ mỗi hàng trên tổng nhóm

~~~sql
SELECT order_id,
       customer_id,
       amount,
       ROUND(
           100 * amount
           / NULLIF(
               SUM(amount) OVER (PARTITION BY customer_id),
               0
           ),
           2
       ) AS pct_of_customer_total
FROM lab_orders;
~~~

`NULLIF(..., 0)` tránh lỗi chia cho 0 khi tổng nhóm bằng 0. Nếu tổng là NULL, kết quả tỷ lệ cũng có thể NULL; cần xác định quy tắc hiển thị trong báo cáo.

### So sánh với kỳ trước

~~~sql
SELECT customer_id,
       order_id,
       order_date,
       amount,
       LAG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS previous_order_amount,
       amount - LAG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS change_from_previous
FROM lab_orders;
~~~

Đây là so sánh với đơn hàng liền trước theo thứ tự, không phải so với ngày lịch trước đó. Nếu cần so sánh theo ngày, tháng hoặc kỳ kế toán, hãy tổng hợp về đúng grain thời gian trước rồi dùng LAG trên tập kỳ đã tổng hợp.

## 12. DISTINCT và analytic functions

Có thể kết hợp DISTINCT với analytic, nhưng cần hiểu DISTINCT áp dụng ở query block ngoài cùng sau khi các biểu thức SELECT được tính. Nếu analytic trả giá trị khác nhau cho từng hàng, DISTINCT không loại được các hàng đó.

~~~sql
SELECT DISTINCT
       department_id,
       SUM(salary) OVER (PARTITION BY department_id) AS dept_total
FROM employees;
~~~

Trong ví dụ này, vì chỉ chọn department và tổng phòng ban (hai biểu thức giống nhau trên các hàng trong cùng phòng), DISTINCT có thể tạo một hàng mỗi phòng ban. Tuy nhiên, nếu thêm `EMPLOYEE_ID` hoặc `ROW_NUMBER`, các hàng trở nên khác nhau và DISTINCT không còn gom được theo phòng ban.

Thông thường, nếu mục tiêu là một hàng/phòng ban, hãy cân nhắc GROUP BY thay vì dùng analytic rồi DISTINCT. Chọn cách thể hiện đúng grain của kết quả ngay từ đầu.

Một số analytic aggregate hỗ trợ `DISTINCT` trong phạm vi cú pháp riêng, nhưng có giới hạn khi kết hợp với analytic ORDER BY/window frame. Kiểm tra tài liệu của hàm và phiên bản Oracle trước khi viết `COUNT(DISTINCT x) OVER(...)`; không suy rộng rằng mọi cú pháp DISTINCT của aggregate đều hợp lệ trong analytic mode.

## 13. Hiệu năng và execution plan

Hàm phân tích thường cần sắp xếp dữ liệu theo partition/order key hoặc duy trì trạng thái cửa sổ. Chi phí phụ thuộc:

- Số hàng đầu vào sau WHERE/GROUP BY/HAVING.
- Số partition và kích thước từng partition.
- Các biểu thức PARTITION BY/ORDER BY.
- Window frame, đặc biệt các frame cần nhìn về phía sau hoặc toàn partition.
- Số hàm analytic và khả năng chia sẻ sort order giữa chúng.
- PGA/workarea, TEMP spill, parallel execution và độ rộng hàng.

### Sort cho analytic

Ví dụ `ROW_NUMBER` theo phòng ban và lương:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS rn
FROM employees;
~~~

Oracle cần tổ chức hàng theo partition và thứ tự tương ứng. Execution plan có thể chứa operation liên quan như `WINDOW SORT`, `WINDOW BUFFER` hoặc operation analytic khác tùy phiên bản và cách optimizer triển khai. Đừng giả định mọi hàm analytic luôn sinh đúng một loại operation.

Nếu nhiều analytic dùng cùng partition/order specification, Oracle có thể tận dụng thứ tự đã có thay vì thực hiện nhiều sort độc lập. Nếu specification khác nhau, có thể cần thêm bước sắp xếp.

### Index có giúp không?

Index trên các cột PARTITION/ORDER BY có thể hữu ích trong một số truy vấn, nhưng không bảo đảm bỏ được sort. Optimizer xét chi phí đọc index so với full scan, số cột cần lấy, clustering factor, độ chọn lọc và thứ tự dữ liệu. Hãy kiểm tra actual plan trước khi thêm index chỉ để phục vụ một analytic function.

### Thu thập actual plan

~~~sql
SELECT /*+ gather_plan_statistics */
       employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS rn
FROM employees;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Quan sát:

- Operation nào thực hiện sort/window?
- `E-Rows` có lệch nhiều so với `A-Rows` không?
- Bao nhiêu hàng đi vào operation analytic?
- Logical reads (`Buffers`), physical reads và elapsed time ra sao?
- Có TEMP/workarea spill không?
- Có nhiều sort vì các analytic dùng thứ tự khác nhau không?

`ALLSTATS LAST` cần thống kê thực thi được thu thập (ví dụ hint `GATHER_PLAN_STATISTICS` hoặc cấu hình phù hợp). `EXPLAIN PLAN` chỉ cho kế hoạch ước lượng, không đo số hàng thực tế hay TEMP đã dùng.

### Giảm công việc trước analytic

Nếu nghiệp vụ cho phép, lọc sớm các hàng không cần thiết bằng WHERE trước khi analytic chạy. Nếu cần tổng hợp về tháng rồi mới tính LAG, hãy GROUP BY tháng trong CTE trước. Đừng lọc bỏ các hàng cần thiết cho cửa sổ chỉ để làm truy vấn nhanh hơn; kết quả analytic sẽ thay đổi vì tập đầu vào đã đổi.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Kết quả chỉ còn một hàng mỗi nhóm | Dùng GROUP BY khi cần giữ chi tiết | Dùng analytic `... OVER(PARTITION BY ...)` nếu cần giữ từng hàng. |
| Tổng lũy kế có giá trị giống nhau cho các đơn cùng ngày | Dùng RANGE frame hoặc frame mặc định với peers | Dùng ROWS và tie-breaker nếu muốn lũy kế từng hàng. |
| `ROW_NUMBER` thay đổi giữa các lần chạy | ORDER BY trong OVER không xác định thứ tự khi tie | Thêm khóa duy nhất làm tiêu chí phá hòa. |
| Không lọc được rn trong WHERE | Analytic được tính sau WHERE | Đưa analytic vào CTE/inline view rồi lọc ở ngoài. |
| `LAST_VALUE` không trả giá trị cuối partition | Frame mặc định kết thúc tại current row | Chỉ rõ `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`. |
| ORDER BY trong OVER không sắp output | ORDER BY đó chỉ phục vụ phép tính analytic | Thêm ORDER BY ở query ngoài cùng. |
| AVG thấp/cao bất ngờ | NULL bị bỏ qua hoặc frame chỉ có một phần hàng ở biên | Kiểm tra COUNT, NULL và frame thực tế. |
| Tổng nhóm lặp trên từng hàng | Dùng SUM OVER | Đây là hành vi đúng của analytic, không phải duplicate dữ liệu. |
| TEMP tăng khi chạy analytic lớn | Sort/window workarea không đủ memory | Kiểm tra actual plan, số hàng, partition, PGA/TEMP và workload đồng thời. |
| Kết quả LAG/LEAD không như mong đợi | Thứ tự analytic hoặc partition không đúng grain | Xác định đúng partition/order và xử lý NULL/default. |

## 15. Bài thực hành tổng hợp

Các ví dụ sử dụng schema học tập có quyền `CREATE TABLE` và quota phù hợp. DDL có implicit commit trong Oracle; không chạy trên bảng nghiệp vụ thật.

### Bước 1: tạo dữ liệu giao dịch

~~~sql
CREATE TABLE lab_orders (
    order_id    NUMBER(8) PRIMARY KEY,
    customer_id NUMBER(8) NOT NULL,
    order_date  DATE NOT NULL,
    amount      NUMBER(12,2),
    status      VARCHAR2(20 CHAR)
);

INSERT INTO lab_orders VALUES (101, 10, DATE '2026-01-01', 100, 'PAID');
INSERT INTO lab_orders VALUES (102, 10, DATE '2026-01-03',  50, 'PAID');
INSERT INTO lab_orders VALUES (103, 20, DATE '2026-01-03',  80, 'PAID');
INSERT INTO lab_orders VALUES (104, 10, DATE '2026-01-05',  25, 'PENDING');
INSERT INTO lab_orders VALUES (105, 20, DATE '2026-01-06',  20, 'PAID');
INSERT INTO lab_orders VALUES (106, 20, DATE '2026-01-06', NULL, 'PENDING');
COMMIT;
~~~

### Bước 2: aggregate theo khách hàng

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       COUNT(amount) AS orders_with_amount,
       SUM(amount) AS total_amount,
       AVG(amount) AS avg_amount
FROM lab_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

Ghi lại số hàng kết quả và giải thích vì sao `COUNT(*)` khác `COUNT(amount)` ở khách hàng 20.

### Bước 3: analytic tổng nhóm nhưng giữ chi tiết

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
       ) AS customer_total
FROM lab_orders
ORDER BY customer_id, order_date, order_id;
~~~

So sánh số hàng với bước 2. Vì sao tổng khách hàng 10 xuất hiện trên ba hàng?

### Bước 4: running total và moving average

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_total,
       AVG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
           ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
       ) AS moving_avg_two_rows
FROM lab_orders
ORDER BY customer_id, order_date, order_id;
~~~

Giải thích frame ở đầu partition và tác động của amount NULL.

### Bước 5: LAG và LEAD

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       amount,
       LAG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS previous_amount,
       LEAD(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS next_amount
FROM lab_orders;
~~~

Phân biệt NULL do không có hàng trước/sau với NULL vì hàng tham chiếu có `AMOUNT` NULL.

### Bước 6: xếp hạng theo khách hàng

~~~sql
SELECT order_id,
       customer_id,
       amount,
       ROW_NUMBER() OVER (
           PARTITION BY customer_id
           ORDER BY amount DESC NULLS LAST, order_id
       ) AS row_no,
       RANK() OVER (
           PARTITION BY customer_id
           ORDER BY amount DESC NULLS LAST
       ) AS amount_rank,
       DENSE_RANK() OVER (
           PARTITION BY customer_id
           ORDER BY amount DESC NULLS LAST
       ) AS dense_amount_rank
FROM lab_orders;
~~~

Giải thích khác biệt khi hai đơn có cùng amount và khi amount NULL.

### Bước 7: lọc top-N qua CTE

~~~sql
WITH ranked_orders AS (
    SELECT order_id,
           customer_id,
           amount,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY amount DESC NULLS LAST, order_id
           ) AS rn
    FROM lab_orders
)
SELECT order_id, customer_id, amount, rn
FROM ranked_orders
WHERE rn <= 2
ORDER BY customer_id, rn;
~~~

Giải thích vì sao điều kiện `RN <= 2` được đặt ở query ngoài.

### Bước 8: tổng hợp rồi phân tích

~~~sql
SELECT customer_id,
       SUM(amount) AS customer_total,
       SUM(SUM(amount)) OVER () AS grand_total,
       ROUND(
           100 * SUM(amount) / NULLIF(SUM(SUM(amount)) OVER (), 0),
           2
       ) AS pct_of_total
FROM lab_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

Mô tả thứ tự aggregate theo khách hàng rồi analytic trên các hàng khách hàng.

### Bước 9: dọn dữ liệu

~~~sql
DROP TABLE lab_orders PURGE;
~~~

Chỉ chạy nếu đã hoàn thành bài và không cần giữ dữ liệu. `PURGE` bỏ qua Recycle Bin; DROP TABLE là DDL và không thể rollback như DML chưa commit.

## 16. Câu hỏi tự kiểm tra

1. **Aggregate với GROUP BY trả về grain nào?** Một hàng cho mỗi nhóm được xác định bởi GROUP BY.
2. **Analytic với PARTITION BY có làm mất hàng chi tiết không?** Không; nó tính trên partition và gắn kết quả vào từng hàng của query block.
3. **SUM(amount) và SUM(amount) OVER() khác nhau thế nào?** Cái đầu tổng hợp thành một giá trị/nhóm; cái sau lặp tổng toàn tập trên từng hàng.
4. **PARTITION BY khác GROUP BY ở đâu?** PARTITION BY chia cửa sổ nhưng giữ hàng; GROUP BY gom hàng thành nhóm kết quả.
5. **ORDER BY trong OVER có sắp xếp output không?** Không; cần ORDER BY ngoài cùng.
6. **ROWS khác RANGE thế nào?** ROWS tính theo vị trí hàng; RANGE theo giá trị logic của biểu thức sort và bao gồm peers theo frame.
7. **Vì sao ROW_NUMBER cần tie-breaker?** Để xác định thứ tự duy nhất khi giá trị sort chính bị trùng.
8. **RANK và DENSE_RANK khác gì?** RANK bỏ khoảng sau đồng hạng; DENSE_RANK không bỏ khoảng.
9. **LAG và LEAD dùng để làm gì?** Lấy giá trị của hàng trước/sau trong partition theo thứ tự analytic.
10. **Vì sao LAST_VALUE có thể không trả giá trị cuối partition?** Frame mặc định có thể chỉ kết thúc ở current row; cần chỉ rõ UNBOUNDED FOLLOWING.
11. **Có thể dùng analytic trực tiếp trong WHERE cùng query block không?** Không theo cú pháp thông thường; dùng inline view/CTE rồi lọc ở ngoài.
12. **WHERE có ảnh hưởng tới cửa sổ analytic không?** Có; WHERE loại hàng đầu vào trước khi analytic được tính.
13. **Có thể dùng aggregate bên trong analytic không?** Có; ví dụ `SUM(SUM(amount)) OVER()` sau khi GROUP BY.
14. **COUNT(*) OVER khác COUNT(expr) OVER thế nào?** COUNT(*) đếm mọi hàng; COUNT(expr) bỏ qua giá trị expr NULL.
15. **Vì sao analytic có thể dùng TEMP?** Sort/window workarea có thể không đủ PGA và phải spill dữ liệu trung gian.
16. **Muốn một hàng mỗi phòng ban kèm tổng công ty nên làm thế nào?** GROUP BY phòng ban rồi dùng analytic trên kết quả nhóm, ví dụ `SUM(SUM(salary)) OVER()`.

Khi lựa chọn giữa hàm tổng hợp và hàm phân tích, hãy xác định **grain của kết quả cần trả về**. Nếu cần một hàng cho mỗi nhóm, dùng aggregate và GROUP BY. Nếu cần giữ từng hàng nhưng bổ sung tổng, thứ hạng, lũy kế hoặc giá trị trước/sau, dùng analytic với OVER. Sau đó xác định partition, thứ tự và frame thật rõ; chính ba thành phần này quyết định cửa sổ mà Oracle dùng để tính trên mỗi hàng.

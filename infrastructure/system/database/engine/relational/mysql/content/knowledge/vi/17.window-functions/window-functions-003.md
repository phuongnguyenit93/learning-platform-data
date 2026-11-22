# ROW_NUMBER, RANK và DENSE_RANK

MySQL cung cấp ba hàm cửa sổ thường dùng để đánh số thứ tự và xếp hạng các hàng: `ROW_NUMBER()`, `RANK()` và `DENSE_RANK()`. Cả ba đều dùng mệnh đề `OVER()` để xác định phạm vi hàng và thứ tự so sánh. Chúng thường xuất hiện trong bảng xếp hạng, top-N theo nhóm, chọn bản ghi mới nhất cho mỗi khách hàng và xử lý dữ liệu có điểm bằng nhau.

Điểm khác biệt quan trọng nằm ở cách xử lý các hàng đồng hạng (tie/peer rows): `ROW_NUMBER()` luôn cấp số khác nhau cho từng hàng; `RANK()` cấp cùng hạng cho các hàng bằng nhau rồi bỏ qua các hạng kế tiếp; `DENSE_RANK()` cũng cấp cùng hạng nhưng không tạo khoảng trống. Muốn chọn đúng hàm, trước hết hãy xác định nghiệp vụ cần số thứ tự từng hàng hay thứ hạng theo giá trị.

Các hàm cửa sổ được hỗ trợ trong MySQL từ phiên bản 8.0. MySQL 5.7 trở xuống không hỗ trợ cú pháp window function. Bài học dùng MySQL 8.0 trở lên.

## 1. Hàm cửa sổ và cú pháp OVER()

Hàm cửa sổ tính một giá trị cho mỗi hàng dựa trên một nhóm hàng liên quan, nhưng vẫn giữ các hàng riêng lẻ trong kết quả. Khác với `GROUP BY`, nó không gộp nhiều hàng thành một hàng tổng hợp.

Cú pháp tổng quát:

```sql
window_function() OVER (
    [PARTITION BY expression [, expression ...]]
    [ORDER BY expression [ASC | DESC] [, expression ...]]
)
```

- `PARTITION BY` chia kết quả thành các nhóm độc lập; hàm được tính lại từ đầu trong từng nhóm.
- `ORDER BY` xác định thứ tự hàng dùng để đánh số hoặc xếp hạng trong mỗi nhóm.
- Nếu bỏ `PARTITION BY`, toàn bộ tập kết quả thuộc cùng một partition.
- Với các hàm xếp hạng, các hàng có cùng toàn bộ giá trị của biểu thức `ORDER BY` được gọi là peer rows (hàng đồng hạng).

Ba hàm trong bài có cú pháp không nhận đối số:

```sql
ROW_NUMBER() OVER (...)
RANK() OVER (...)
DENSE_RANK() OVER (...)
```

## 2. Chuẩn bị dữ liệu thực hành

Giả sử hệ thống lưu điểm đánh giá nhân viên theo phòng ban:

```sql
CREATE TABLE employee_scores (
    employee_id BIGINT UNSIGNED NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    department VARCHAR(50) NOT NULL,
    score DECIMAL(5, 2) NULL,
    PRIMARY KEY (employee_id),
    KEY idx_employee_scores_department_score (department, score)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;

INSERT INTO employee_scores
    (employee_id, employee_name, department, score)
VALUES
    (1, 'An',   'Sales',       95.00),
    (2, 'Bình', 'Sales',       90.00),
    (3, 'Chi',  'Sales',       90.00),
    (4, 'Dũng', 'Sales',       80.00),
    (5, 'Hoa',  'Engineering', 99.00),
    (6, 'Khoa', 'Engineering', 99.00),
    (7, 'Lan',  'Engineering', 92.00),
    (8, 'Minh', 'Engineering', 85.00);
```

Trong mỗi phòng ban có một số nhân viên đạt điểm bằng nhau. Đây là dữ liệu cần thiết để thấy sự khác nhau giữa ba hàm.

## 3. ROW_NUMBER(): đánh số riêng từng hàng

`ROW_NUMBER()` gán một số nguyên liên tiếp bắt đầu từ 1 cho mỗi hàng trong partition theo thứ tự đã khai báo. Mỗi hàng luôn có số khác nhau, kể cả khi các hàng có cùng điểm.

```sql
SELECT
    employee_id,
    employee_name,
    department,
    score,
    ROW_NUMBER() OVER (
        PARTITION BY department
        ORDER BY score DESC, employee_id ASC
    ) AS row_num
FROM employee_scores
ORDER BY department, row_num;
```

Kết quả minh họa:

| Department | Employee | Score | row_num |
| --- | --- | ---: | ---: |
| Engineering | Hoa | 99.00 | 1 |
| Engineering | Khoa | 99.00 | 2 |
| Engineering | Lan | 92.00 | 3 |
| Engineering | Minh | 85.00 | 4 |
| Sales | An | 95.00 | 1 |
| Sales | Bình | 90.00 | 2 |
| Sales | Chi | 90.00 | 3 |
| Sales | Dũng | 80.00 | 4 |

`PARTITION BY department` làm số thứ tự bắt đầu lại từ 1 ở mỗi phòng ban. `employee_id` được thêm vào sau `score` để phân định hai người cùng điểm, khiến thứ tự của `ROW_NUMBER()` xác định và lặp lại được nếu dữ liệu không đổi.

Nếu bỏ `PARTITION BY department`, MySQL đánh số toàn bộ nhân viên trong một tập duy nhất. Nếu bỏ `ORDER BY`, thứ tự đánh số không được xác định; không nên dùng kết quả đó cho nghiệp vụ cần thứ tự ổn định.

## 4. RANK(): xếp hạng và để khoảng trống sau đồng hạng

`RANK()` cấp cùng hạng cho các hàng có cùng giá trị theo toàn bộ biểu thức `ORDER BY`. Hạng kế tiếp được tính theo vị trí hàng, vì vậy sẽ có khoảng trống sau nhóm đồng hạng.

```sql
SELECT
    employee_id,
    employee_name,
    department,
    score,
    RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS score_rank
FROM employee_scores
ORDER BY department, score_rank, employee_id;
```

Kết quả minh họa:

| Department | Employee | Score | score_rank |
| --- | --- | ---: | ---: |
| Engineering | Hoa | 99.00 | 1 |
| Engineering | Khoa | 99.00 | 1 |
| Engineering | Lan | 92.00 | 3 |
| Engineering | Minh | 85.00 | 4 |
| Sales | An | 95.00 | 1 |
| Sales | Bình | 90.00 | 2 |
| Sales | Chi | 90.00 | 2 |
| Sales | Dũng | 80.00 | 4 |

Hai nhân viên Engineering cùng điểm 99 nhận hạng 1. Người tiếp theo nhận hạng 3 vì đã có hai hàng đứng trước. Tương tự, hai nhân viên Sales cùng điểm 90 nhận hạng 2 và người tiếp theo nhận hạng 4.

Đây là cách xếp hạng thường gặp trong cuộc thi hoặc bảng điểm, nơi hai người đồng điểm cùng vị trí và vị trí sau bị bỏ qua.

## 5. DENSE_RANK(): xếp hạng liên tiếp không có khoảng trống

`DENSE_RANK()` cũng cấp cùng hạng cho các hàng đồng hạng, nhưng hạng tiếp theo chỉ tăng một đơn vị, không phụ thuộc có bao nhiêu hàng trong nhóm trước.

```sql
SELECT
    employee_id,
    employee_name,
    department,
    score,
    DENSE_RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS dense_score_rank
FROM employee_scores
ORDER BY department, dense_score_rank, employee_id;
```

Kết quả minh họa:

| Department | Employee | Score | dense_score_rank |
| --- | --- | ---: | ---: |
| Engineering | Hoa | 99.00 | 1 |
| Engineering | Khoa | 99.00 | 1 |
| Engineering | Lan | 92.00 | 2 |
| Engineering | Minh | 85.00 | 3 |
| Sales | An | 95.00 | 1 |
| Sales | Bình | 90.00 | 2 |
| Sales | Chi | 90.00 | 2 |
| Sales | Dũng | 80.00 | 3 |

Nếu mục tiêu là xếp hạng các mức điểm khác nhau, `DENSE_RANK()` thường phù hợp: mức điểm cao nhất là hạng 1, mức điểm cao thứ hai là hạng 2, kể cả khi có nhiều người cùng đạt mức đầu tiên.

## 6. So sánh ba hàm trên cùng một nhóm

Với điểm số trong phòng Sales là `95, 90, 90, 80`, kết quả là:

| Score | ROW_NUMBER* | RANK | DENSE_RANK |
| ---: | ---: | ---: | ---: |
| 95 | 1 | 1 | 1 |
| 90 | 2 | 2 | 2 |
| 90 | 3 | 2 | 2 |
| 80 | 4 | 4 | 3 |

`ROW_NUMBER*` trong bảng minh họa giả định có thêm khóa phân định, chẳng hạn `employee_id`, để quyết định hàng nào nhận 2 và hàng nào nhận 3. Nếu chỉ sắp xếp theo điểm, hai hàng điểm 90 vẫn nhận số `ROW_NUMBER()` khác nhau nhưng thứ tự tương đối giữa chúng không được bảo đảm.

| Hàm | Hàng đồng hạng | Hạng sau nhóm đồng hạng | Mục đích thường gặp |
| --- | --- | --- | --- |
| `ROW_NUMBER()` | Mỗi hàng có số riêng | Luôn liên tiếp | Chọn đúng N hàng, phân trang, lấy một bản ghi theo thứ tự xác định |
| `RANK()` | Cùng hạng | Có khoảng trống | Xếp hạng theo vị trí thi đấu hoặc điểm số |
| `DENSE_RANK()` | Cùng hạng | Không có khoảng trống | Xếp hạng các mức giá trị hoặc nhóm điểm khác nhau |

## 7. Peer rows được xác định bởi toàn bộ ORDER BY trong OVER

Hai hàng được xem là đồng hạng khi tất cả biểu thức trong `ORDER BY` của cửa sổ cho giá trị bằng nhau theo quy tắc so sánh tương ứng. Ví dụ:

```sql
RANK() OVER (
    PARTITION BY department
    ORDER BY score DESC
)
```

Các nhân viên có cùng `score` trong cùng `department` là peer rows.

Nhưng nếu thêm khóa chính vào cùng cửa sổ:

```sql
RANK() OVER (
    PARTITION BY department
    ORDER BY score DESC, employee_id ASC
)
```

Mỗi hàng có `employee_id` khác nhau, nên các nhân viên cùng điểm không còn là peer rows. Kết quả `RANK()` lúc này thường trở thành các hạng riêng liên tiếp, làm mất ý nghĩa đồng hạng theo điểm.

Vì vậy:

- Với `RANK()` và `DENSE_RANK()`, chỉ đưa vào `ORDER BY` các tiêu chí thực sự định nghĩa thứ hạng nghiệp vụ.
- Với `ROW_NUMBER()`, thêm một khóa duy nhất làm tie-breaker nếu cần số thứ tự ổn định.
- Nếu cần cả thứ hạng theo điểm và thứ tự riêng cho từng hàng, tính hai hàm trong cùng truy vấn với hai định nghĩa cửa sổ khác nhau.

Ví dụ:

```sql
SELECT
    employee_id,
    employee_name,
    department,
    score,
    RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS score_rank,
    ROW_NUMBER() OVER (
        PARTITION BY department
        ORDER BY score DESC, employee_id ASC
    ) AS row_num
FROM employee_scores;
```

Truy vấn giữ được đồng hạng theo điểm, đồng thời có số thứ tự riêng và xác định cho từng nhân viên.

## 8. PARTITION BY: xếp hạng trong từng nhóm

`PARTITION BY` chia tập kết quả thành các partition độc lập. Mỗi hàm bắt đầu tính lại trong từng partition.

Ví dụ xếp hạng nhân viên trong từng phòng ban:

```sql
SELECT
    department,
    employee_name,
    score,
    RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS department_rank
FROM employee_scores;
```

Nếu bỏ `PARTITION BY`, thứ hạng được tính trên toàn công ty:

```sql
SELECT
    department,
    employee_name,
    score,
    RANK() OVER (
        ORDER BY score DESC
    ) AS company_rank
FROM employee_scores;
```

Có thể phân vùng theo nhiều cột:

```sql
RANK() OVER (
    PARTITION BY department, review_period
    ORDER BY score DESC
)
```

Khi đó, mỗi cặp `department` và `review_period` là một partition riêng. Hãy chọn cột phân vùng theo phạm vi xếp hạng của nghiệp vụ: toàn hệ thống, từng phòng ban, từng kỳ đánh giá hay từng khu vực.

## 9. ORDER BY trong OVER khác ORDER BY của truy vấn

`ORDER BY` bên trong `OVER()` xác định thứ tự để tính số thứ tự hoặc hạng. Nó **không bảo đảm thứ tự các hàng cuối cùng được trả về cho client**.

Ví dụ:

```sql
SELECT
    employee_id,
    employee_name,
    score,
    ROW_NUMBER() OVER (ORDER BY score DESC, employee_id) AS row_num
FROM employee_scores;
```

Hàm tính `row_num` theo điểm giảm dần, nhưng thứ tự hiển thị cuối cùng vẫn không được bảo đảm nếu truy vấn ngoài không có `ORDER BY`.

Muốn kết quả hiển thị theo thứ tự xếp hạng:

```sql
SELECT
    employee_id,
    employee_name,
    score,
    ROW_NUMBER() OVER (ORDER BY score DESC, employee_id) AS row_num
FROM employee_scores
ORDER BY score DESC, employee_id;
```

Với partition, có thể hiển thị theo nhóm rồi theo hạng:

```sql
SELECT
    employee_id,
    employee_name,
    department,
    score,
    DENSE_RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS score_rank
FROM employee_scores
ORDER BY department, score_rank, employee_id;
```

Đừng dựa vào thứ tự vật lý của bảng hoặc thứ tự tình cờ từ index để thay cho `ORDER BY` ngoài cùng.

## 10. Xếp hạng sau khi tổng hợp dữ liệu

Hàm cửa sổ có thể áp dụng trên kết quả đã `GROUP BY`. Ví dụ xếp hạng phòng ban theo tổng doanh thu:

Giả sử bảng đơn hàng đã lưu phòng ban ghi nhận doanh thu của từng đơn:

```sql
CREATE TABLE department_orders (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    department VARCHAR(50) NOT NULL,
    total_amount DECIMAL(13, 2) NOT NULL,
    PRIMARY KEY (id),
    KEY idx_department_orders_department (department)
) ENGINE=InnoDB;
```

```sql
SELECT
    department,
    total_revenue,
    RANK() OVER (ORDER BY total_revenue DESC) AS revenue_rank
FROM (
    SELECT
        department,
        SUM(total_amount) AS total_revenue
    FROM department_orders
    GROUP BY department
) AS department_totals
ORDER BY revenue_rank, department;
```

Derived table tạo một hàng cho mỗi phòng ban trước; hàm `RANK()` sau đó xếp hạng các tổng doanh thu. Có thể dùng CTE để trình bày cùng logic rõ hơn:

```sql
WITH department_totals AS (
    SELECT
        department,
        SUM(total_amount) AS total_revenue
    FROM department_orders
    GROUP BY department
)
SELECT
    department,
    total_revenue,
    DENSE_RANK() OVER (ORDER BY total_revenue DESC) AS revenue_rank
FROM department_totals
ORDER BY revenue_rank, department;
```

Trong truy vấn này, hai phòng ban có tổng doanh thu bằng nhau nhận cùng hạng. Nếu dùng `ROW_NUMBER()` với `department` làm tie-breaker, mỗi phòng ban sẽ có số riêng nhưng không còn biểu diễn đồng hạng.

## 11. Top-N hàng trong mỗi nhóm

Một ứng dụng phổ biến là lấy ba nhân viên đứng đầu ở từng phòng ban. Không thể lọc trực tiếp alias window function trong `WHERE` cùng query block, vì `WHERE` được xử lý trước khi giá trị window được tính. Hãy bọc truy vấn trong CTE hoặc derived table.

### 11.1. Chính xác tối đa N hàng mỗi nhóm

Dùng `ROW_NUMBER()` nếu muốn tối đa ba hàng cho mỗi phòng ban:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        employee_name,
        department,
        score,
        ROW_NUMBER() OVER (
            PARTITION BY department
            ORDER BY score DESC, employee_id ASC
        ) AS row_num
    FROM employee_scores
)
SELECT
    employee_id,
    employee_name,
    department,
    score,
    row_num
FROM ranked_employees
WHERE row_num <= 3
ORDER BY department, row_num;
```

Mỗi phòng ban trả về tối đa ba hàng. Nếu điểm thứ ba bị hòa, `employee_id` quyết định người nào nằm trong ba hàng được chọn.

### 11.2. Lấy tất cả người có thứ hạng nằm trong top N

Dùng `RANK()` nếu muốn giữ tất cả hàng đồng hạng ở các vị trí đầu:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        employee_name,
        department,
        score,
        RANK() OVER (
            PARTITION BY department
            ORDER BY score DESC
        ) AS score_rank
    FROM employee_scores
)
SELECT *
FROM ranked_employees
WHERE score_rank <= 3
ORDER BY department, score_rank, employee_id;
```

Nếu có nhiều nhân viên cùng hạng 3, tất cả đều được trả về. Kết quả có thể nhiều hơn ba hàng mỗi phòng ban.

### 11.3. Lấy top N mức giá trị khác nhau

Dùng `DENSE_RANK()` nếu muốn lấy ba mức điểm cao nhất ở mỗi phòng ban:

```sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        employee_name,
        department,
        score,
        DENSE_RANK() OVER (
            PARTITION BY department
            ORDER BY score DESC
        ) AS score_level
    FROM employee_scores
)
SELECT *
FROM ranked_employees
WHERE score_level <= 3
ORDER BY department, score_level, employee_id;
```

Truy vấn giữ tất cả nhân viên thuộc ba mức điểm cao nhất, không quan tâm mỗi mức có bao nhiêu người.

## 12. Lấy bản ghi mới nhất cho mỗi nhóm

Một mẫu khác là chọn đơn hàng mới nhất của mỗi khách hàng. Dùng `ROW_NUMBER()` để đánh số trong từng khách hàng:

```sql
WITH numbered_orders AS (
    SELECT
        id,
        customer_id,
        status,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, id DESC
        ) AS row_num
    FROM orders
)
SELECT
    id,
    customer_id,
    status,
    created_at
FROM numbered_orders
WHERE row_num = 1
ORDER BY customer_id;
```

`id DESC` phân định các đơn có cùng `created_at`. Nếu không có tie-breaker, hàng được chọn giữa các đơn cùng thời điểm có thể thay đổi giữa các lần chạy.

Nếu muốn trả về tất cả đơn đồng thời điểm mới nhất của mỗi khách hàng, dùng `RANK()` và chỉ sắp xếp theo `created_at DESC`:

```sql
WITH ranked_orders AS (
    SELECT
        id,
        customer_id,
        status,
        created_at,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC
        ) AS time_rank
    FROM orders
)
SELECT *
FROM ranked_orders
WHERE time_rank = 1;
```

Hai truy vấn giải quyết hai yêu cầu khác nhau: chọn đúng một bản ghi mới nhất hoặc giữ mọi bản ghi đồng thời điểm mới nhất.

## 13. NULL trong ORDER BY của hàm xếp hạng

MySQL xem `NULL` nhỏ hơn giá trị không `NULL` khi sắp xếp. Do đó, `ORDER BY score DESC` đặt điểm `NULL` xuống cuối; `ORDER BY score ASC` đặt `NULL` lên đầu.

Nếu nhiều hàng có `score IS NULL` và cửa sổ chỉ sắp xếp theo `score`, chúng là peer rows và nhận cùng `RANK()`/`DENSE_RANK()`. Nếu nghiệp vụ không muốn xếp hạng hàng chưa có điểm, hãy lọc chúng trước khi tính hàm:

```sql
WITH scored AS (
    SELECT
        employee_id,
        employee_name,
        department,
        score,
        RANK() OVER (
            PARTITION BY department
            ORDER BY score DESC
        ) AS score_rank
    FROM employee_scores
    WHERE score IS NOT NULL
)
SELECT *
FROM scored
ORDER BY department, score_rank, employee_id;
```

Nếu vẫn cần giữ nhân viên chưa có điểm trong kết quả nhưng không xếp họ cùng nhóm điểm, có thể tách hàng đã chấm và chưa chấm bằng truy vấn/CTE riêng hoặc tạo cột trạng thái xếp hạng rõ ràng. Không thay `NULL` bằng 0 nếu 0 là điểm hợp lệ và hai ý nghĩa cần được phân biệt.

## 14. Collation và kiểu dữ liệu ảnh hưởng peer rows

Với `ORDER BY` trên cột văn bản, collation quyết định cách so sánh. Hai chuỗi có thể được xem là bằng nhau theo collation không phân biệt hoa/thường hoặc dấu; khi đó chúng có thể là peer rows cho `RANK()` và `DENSE_RANK()`.

Ví dụ:

```sql
SELECT
    employee_id,
    employee_name,
    RANK() OVER (
        ORDER BY employee_name COLLATE utf8mb4_0900_ai_ci
    ) AS name_rank
FROM employee_scores;
```

Collation minh họa trên thuộc MySQL 8.0. Nó không phân biệt hoa/thường và dấu. Nếu cần phân biệt, hãy chọn collation phù hợp với yêu cầu và kiểm tra các collation có sẵn trên server.

Với số và ngày giờ, hãy lưu bằng kiểu dữ liệu đúng (`DECIMAL`, `DATE`, `DATETIME`, `TIMESTAMP`) thay vì chuỗi có định dạng không nhất quán. Nếu sắp xếp chuỗi biểu diễn số hoặc ngày, thứ tự từ điển có thể khác thứ tự số học/thời gian.

## 15. Hàm cửa sổ không thể lọc trực tiếp trong WHERE cùng query block

Thứ tự xử lý logic của truy vấn khiến `WHERE` được áp dụng trước khi window function tạo kết quả. Vì vậy, câu lệnh sau không hợp lệ:

```sql
-- Không hợp lệ: không thể dùng alias window trong WHERE cùng query block
SELECT
    employee_id,
    score,
    ROW_NUMBER() OVER (ORDER BY score DESC) AS row_num
FROM employee_scores
WHERE row_num <= 3;
```

Dùng CTE hoặc derived table:

```sql
WITH numbered AS (
    SELECT
        employee_id,
        score,
        ROW_NUMBER() OVER (ORDER BY score DESC, employee_id) AS row_num
    FROM employee_scores
)
SELECT employee_id, score, row_num
FROM numbered
WHERE row_num <= 3;
```

MySQL không hỗ trợ mệnh đề `QUALIFY` như một số hệ quản trị khác. CTE/derived table là cách phổ biến để lọc kết quả window function.

## 16. Hiệu năng và index cho ranking

Hàm cửa sổ có thể cần sắp xếp dữ liệu theo partition và thứ tự trong cửa sổ. Index phù hợp có thể giúp giảm công việc đọc hoặc sort trong một số truy vấn, nhưng không bảo đảm MySQL luôn tránh được bước sort.

Ví dụ truy vấn xếp hạng theo phòng ban và điểm:

```sql
SELECT
    employee_id,
    department,
    score,
    RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS score_rank
FROM employee_scores;
```

Index bắt đầu bằng `(department, score)` là ứng viên cần đánh giá. Nếu cần thứ tự ổn định cho `ROW_NUMBER()`, một index `(department, score, employee_id)` có thể phù hợp với thứ tự truy vấn, tùy chiều index và phiên bản.

Kiểm tra kế hoạch:

```sql
EXPLAIN
SELECT
    employee_id,
    department,
    score,
    RANK() OVER (
        PARTITION BY department
        ORDER BY score DESC
    ) AS score_rank
FROM employee_scores;
```

Trên MySQL 8.0.18 trở lên, có thể dùng `EXPLAIN ANALYZE` để đo số hàng và thời gian thực tế. Hãy kiểm tra lượng dữ liệu, sort, temporary table và chi phí đọc; không tạo nhiều index gần giống nhau nếu workload không chứng minh lợi ích.

## 17. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm / lỗi | Thực tế | Cách xử lý |
| --- | --- | --- |
| `ROW_NUMBER`, `RANK`, `DENSE_RANK` cho cùng kết quả | Khác nhau ở cách xử lý peer rows và khoảng trống hạng | Chọn theo yêu cầu nghiệp vụ |
| Thêm khóa chính vào ORDER BY của RANK luôn tốt | Khóa duy nhất phá nhóm đồng hạng theo điểm | Chỉ thêm tie-breaker vào `ROW_NUMBER` hoặc thứ tự hiển thị ngoài |
| ORDER BY trong OVER đảm bảo thứ tự hiển thị | Nó chỉ điều khiển phép tính cửa sổ | Thêm `ORDER BY` ở truy vấn ngoài |
| PARTITION BY giống GROUP BY | PARTITION BY không gộp các hàng thành một hàng | Dùng window function khi cần giữ chi tiết từng hàng |
| Có thể lọc alias row number trong WHERE | WHERE chạy trước window function | Bọc trong CTE hoặc derived table |
| RANK() <= 3 luôn trả đúng ba hàng mỗi nhóm | Đồng hạng có thể làm số hàng vượt ba | Dùng ROW_NUMBER nếu cần tối đa đúng N hàng |
| DENSE_RANK() <= 3 nghĩa là ba hàng | Nó lấy ba mức giá trị/hạng khác nhau | Phân biệt số hàng và số mức xếp hạng |
| Bỏ ORDER BY trong OVER vẫn có thứ tự tự nhiên | Số thứ tự không xác định | Khai báo thứ tự và tie-breaker |

## 18. Quy trình chọn hàm xếp hạng

Trước khi viết truy vấn, hãy trả lời:

1. Cần đánh số từng hàng hay xếp hạng theo giá trị?
2. Hai hàng có cùng điểm/giá trị có phải đồng hạng không?
3. Sau nhóm đồng hạng, vị trí tiếp theo có cần bỏ qua số hạng không?
4. Phạm vi xếp hạng là toàn bộ dữ liệu hay từng nhóm `PARTITION BY`?
5. `ORDER BY` trong cửa sổ có chỉ gồm tiêu chí nghiệp vụ hay đã vô tình thêm khóa duy nhất làm mất tie?
6. Nếu dùng `ROW_NUMBER()`, đã có tie-breaker duy nhất để kết quả xác định chưa?
7. Hàng có `NULL` có được xếp hạng không; vị trí NULL có phù hợp với nghiệp vụ không?
8. Cần lọc top-N hàng, top-N hạng hay top-N mức giá trị?
9. Đã bọc truy vấn trong CTE/derived table để lọc kết quả window chưa?
10. Đã kiểm tra kế hoạch thực thi và hiệu năng trên dữ liệu đại diện chưa?

## 19. Bài tập thực hành

1. Tạo bảng `employee_scores` theo ví dụ và chèn ít nhất hai nhân viên có cùng điểm trong mỗi phòng ban.
2. Tính `ROW_NUMBER()`, `RANK()` và `DENSE_RANK()` trên toàn công ty; so sánh kết quả.
3. Thêm `PARTITION BY department` và quan sát thứ hạng bắt đầu lại trong từng phòng.
4. Thêm `employee_id` vào `ORDER BY` của `RANK()`; giải thích vì sao các hàng cùng điểm không còn đồng hạng.
5. Tính đồng thời `RANK()` theo điểm và `ROW_NUMBER()` theo điểm cộng khóa chính trong cùng SELECT.
6. Lấy tối đa ba nhân viên mỗi phòng bằng `ROW_NUMBER()`.
7. Lấy tất cả nhân viên có hạng nằm trong ba vị trí đầu bằng `RANK()`; tạo trường hợp đồng hạng ở vị trí thứ ba.
8. Lấy nhân viên thuộc ba mức điểm cao nhất mỗi phòng bằng `DENSE_RANK()`.
9. Dùng `ROW_NUMBER()` để lấy đơn hàng mới nhất mỗi khách hàng; thử dữ liệu có hai đơn cùng `created_at`.
10. Thêm hàng có điểm `NULL`, kiểm tra thứ tự và thử lọc NULL trước khi xếp hạng.
11. Dùng `EXPLAIN` để xem kế hoạch truy vấn có `PARTITION BY` và `ORDER BY`; thử index phù hợp trong môi trường lab.

## 20. Ghi nhớ

`ROW_NUMBER()` cấp số liên tiếp và khác nhau cho từng hàng; `RANK()` cho các hàng đồng hạng cùng hạng rồi bỏ qua hạng kế tiếp; `DENSE_RANK()` cho đồng hạng nhưng không bỏ khoảng trống. `PARTITION BY` chia phạm vi tính toán và làm số thứ tự/hạng bắt đầu lại trong từng nhóm. `ORDER BY` trong `OVER()` xác định thứ tự tính toán, không bảo đảm thứ tự kết quả cuối cùng.

Peer rows được xác định bởi toàn bộ biểu thức `ORDER BY` trong cửa sổ. Không thêm khóa duy nhất vào `RANK()`/`DENSE_RANK()` nếu nghiệp vụ cần giữ đồng hạng; với `ROW_NUMBER()`, nên thêm tie-breaker duy nhất để kết quả ổn định. Muốn lọc top-N, dùng CTE hoặc derived table vì MySQL không cho lọc trực tiếp window alias trong `WHERE` cùng query block. Chọn hàm theo ý nghĩa xếp hạng trước, sau đó kiểm tra index và `EXPLAIN` trên MySQL 8.0 trở lên.
